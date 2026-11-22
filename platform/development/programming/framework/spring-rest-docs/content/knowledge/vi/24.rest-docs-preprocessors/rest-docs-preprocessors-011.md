# Viết preprocessor tùy biến

Các preprocessor có sẵn của Spring REST Docs như pretty print, thay header, loại header, chuẩn hóa URI và thay pattern đáp ứng nhiều nhu cầu phổ biến. Tuy nhiên, một dự án có thể cần policy riêng: chỉ mask request của API public, bỏ qua endpoint health check, chuẩn hóa correlation ID theo quy ước nội bộ hoặc gom cùng quy tắc làm sạch cho nhiều test. Khi đó có thể viết một preprocessor tùy biến để đóng gói logic của dự án và tái sử dụng trong các operation documentation.

Spring REST Docs phân biệt hai abstraction: `OperationRequestPreprocessor` xử lý request được ghi nhận và `OperationResponsePreprocessor` xử lý response được ghi nhận. Ta có thể triển khai một trong hai interface, thường bằng cách ủy quyền cho built-in preprocessors rồi bổ sung điều kiện theo contract. Cách này giữ rõ phạm vi thay đổi: preprocessor tùy biến chỉ làm việc trên message dùng tạo snippet, không thay đổi request/response thực của ứng dụng.

Bài học thuộc chương **Preprocessors** của module `SPRING_REST_DOCS`. Module tạo tài liệu REST API có thể kiểm chứng từ test HTTP bằng MockMvc, WebTestClient hoặc REST Assured, sinh snippet request, response, payload, tham số và header, rồi biên soạn Asciidoctor/Markdown và tích hợp build, CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định khi nào built-in preprocessors chưa đủ và cần policy tùy biến.
2. Phân biệt `OperationRequestPreprocessor` và `OperationResponsePreprocessor`.
3. Viết lớp preprocessor riêng bằng cách ủy quyền cho processor có sẵn.
4. Áp dụng điều kiện theo URI hoặc policy endpoint trước khi xử lý message.
5. Kết hợp custom processor với `preprocessRequest(...)` và `preprocessResponse(...)`.
6. Kiểm thử hành vi, thứ tự, trường hợp bỏ qua và dữ liệu nhạy cảm.
7. Đóng gói, tái sử dụng và bảo trì custom preprocessor.

## 2. Khi nào nên viết preprocessor tùy biến?

Trước tiên, kiểm tra built-in preprocessors. Nếu chỉ cần format JSON, bỏ một header, thay Authorization hoặc chuẩn hóa scheme/host/port, processor có sẵn thường dễ đọc và ít mã hơn.

Custom preprocessor hữu ích khi policy có một hoặc nhiều đặc điểm:

- Nhiều endpoint dùng cùng quy tắc mask, nhưng chỉ áp dụng cho một số nhóm route.
- Cần bỏ qua health check, metrics hoặc operation nội bộ.
- Giá trị cần chuẩn hóa được quyết định theo path, method hoặc header của operation.
- Dự án cần tên policy có ý nghĩa, thay vì lặp một chuỗi processor dài trong mọi test.
- Cần phối hợp nhiều built-in processors theo quy tắc thống nhất và có thể kiểm thử riêng.
- Cần logic biến đổi có cấu trúc mà processor tích hợp sẵn không biểu đạt trực tiếp.

Không nên tạo custom processor chỉ để bọc một lời gọi `prettyPrint()` nếu không có policy bổ sung. Một helper cấu hình đơn giản có thể đủ. Mục tiêu là gom một quy tắc thực sự có ý nghĩa, không tạo abstraction khó hiểu.

## 3. Các abstraction chính

Spring REST Docs cung cấp các kiểu xử lý operation:

| Kiểu | Message nhận vào | Kết quả | Wrapper trong cấu hình |
| --- | --- | --- | --- |
| `OperationRequestPreprocessor` | `OperationRequest` | Request dùng cho snippet sau xử lý | `preprocessRequest(...)` |
| `OperationResponsePreprocessor` | `OperationResponse` | Response dùng cho snippet sau xử lý | `preprocessResponse(...)` |

Các interface thuộc package preprocessing của Spring REST Docs. Một implementation nhận operation message và trả về operation message được dùng tiếp ở bước tạo snippet. Không nhầm chúng với Servlet Filter, Spring MVC Interceptor hay WebFlux filter; các thành phần kia tham gia xử lý request/response runtime của ứng dụng.

Static import thường dùng với MockMvc:

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
```

Kiểu trả về và chữ ký interface cần đối chiếu với version Spring REST Docs mà dự án đang dùng. Dựa trên public API của dependency đã pin; không phụ thuộc lớp implementation nội bộ.

## 4. Mẫu custom request preprocessor bằng delegation

Một cách an toàn để bắt đầu là tạo lớp policy riêng, bên trong dùng built-in request processor. Ví dụ, API public cần thay token và correlation ID, đồng thời bỏ Cookie và header trace nội bộ.

```java
import java.net.URI;

import org.springframework.restdocs.operation.OperationRequest;
import org.springframework.restdocs.operation.preprocess.OperationRequestPreprocessor;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

public final class PublicRequestPreprocessor
        implements OperationRequestPreprocessor {

    private final OperationRequestPreprocessor delegate;

    public PublicRequestPreprocessor() {
        this.delegate = preprocessRequest(
            modifyHeaders()
                .set("Authorization", "Bearer <access-token>")
                .set("X-Correlation-Id", "docs-correlation-id")
                .build(),
            removeHeaders("Cookie", "X-Internal-Trace")
        );
    }

    @Override
    public OperationRequest preprocess(OperationRequest request) {
        URI uri = request.getUri();

        // Bỏ qua endpoint health; snippet của endpoint này không cần policy public.
        if (uri.getPath() != null && uri.getPath().startsWith("/actuator/health")) {
            return request;
        }

        return this.delegate.preprocess(request);
    }
}
```

Lớp này đóng gói policy của dự án và áp dụng điều kiện theo URI. Phần biến đổi header được ủy quyền cho built-in processor. Với route health check, processor trả lại request được ghi nhận mà không áp dụng policy này. Nếu route đó có thể chứa dữ liệu nhạy cảm, phải xác định policy an toàn riêng thay vì vô tình để lộ header.

### 4.1. Vì sao dùng delegation?

Delegation giúp:

- Tái sử dụng hành vi thư viện cung cấp.
- Tránh tự sao chép và dựng lại HTTP message.
- Giữ policy của dự án trong một lớp có tên dễ hiểu.
- Kiểm tra điều kiện áp dụng độc lập với chi tiết biến đổi header.
- Điều chỉnh chuỗi built-in khi contract thay đổi.

Custom wrapper không nhất thiết phải tự tạo lại `OperationRequest`. Chỉ thực hiện biến đổi trực tiếp trên operation object khi built-in không đáp ứng và đã hiểu rõ public API của phiên bản thư viện.

## 5. Mẫu custom response preprocessor

Response có policy riêng: loại Set-Cookie và header nội bộ, thay request ID động bằng giá trị ổn định, rồi định dạng body. Có thể đóng gói như sau:

```java
import org.springframework.restdocs.operation.OperationResponse;
import org.springframework.restdocs.operation.preprocess.OperationResponsePreprocessor;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

public final class PublicResponsePreprocessor
        implements OperationResponsePreprocessor {

    private final OperationResponsePreprocessor delegate;

    public PublicResponsePreprocessor() {
        this.delegate = preprocessResponse(
            modifyHeaders()
                .set("X-Request-Id", "docs-request-id")
                .build(),
            removeHeaders("Set-Cookie", "X-Internal-Node"),
            prettyPrint()
        );
    }

    @Override
    public OperationResponse preprocess(OperationResponse response) {
        return this.delegate.preprocess(response);
    }
}
```

Lớp này đặt tên cho policy response và dùng lại built-in processors. Nếu một endpoint cần giữ Set-Cookie vì tài liệu hóa cookie authentication, không áp dụng policy public mặc định; tạo policy chuyên biệt hoặc cho phép cấu hình rõ ràng.

## 6. Dùng custom processor trong document(...)

Với MockMvc, truyền instance vào wrapper tương ứng:

```java
mockMvc.perform(
        get("/api/orders/{id}", 42L)
            .header("Authorization", "Bearer docs-test-token")
            .header("Cookie", "SESSION=test-session")
            .header("X-Correlation-Id", "run-91382")
    )
    .andExpect(status().isOk())
    .andExpect(header().exists("X-Request-Id"))
    .andDo(document("orders-get",
        preprocessRequest(new PublicRequestPreprocessor()),
        preprocessResponse(new PublicResponsePreprocessor())
    ));
```

Assertions được thực hiện trên exchange của test. Request preprocessor làm sạch request snippet; response preprocessor chuẩn hóa response snippet. Instance có thể được tạo trực tiếp hoặc quản lý bằng factory/helper dùng chung trong test support.

### 6.1. Chỉ dùng một phía khi cần

Không bắt buộc mỗi operation phải có cả hai loại:

```java
.andDo(document("products-get",
    preprocessResponse(new PublicResponsePreprocessor())
));
```

Nếu request không có dữ liệu cần thay, không cần thêm request processor. Tương tự, operation chỉ cần mask token trong request có thể chỉ dùng custom request preprocessor.

## 7. Điều kiện hóa policy theo operation

Custom processor có thể quyết định có áp dụng delegate hay không dựa trên message được ghi nhận. Ví dụ request processor ở trên bỏ qua path health check. Điều kiện có thể dựa vào:

- Path hoặc URI pattern.
- HTTP method nếu operation API cung cấp thông tin đó.
- Header có mặt trong message được ghi nhận.
- Nhóm endpoint public/internal được cấu hình trong test support.

Điều kiện cần đơn giản, xác định và có test. Tránh kiểm tra hostname máy chạy để quyết định có mask hay không; kết quả khi đó có thể khác giữa local và CI. Ưu tiên policy dựa trên contract hoặc cấu hình tài liệu hóa.

### 7.1. Không bỏ qua làm sạch chỉ vì route nội bộ

Nếu một route bị bỏ qua, cần chắc chắn snippet của route đó không thể chứa secret. Bỏ qua policy không đồng nghĩa dữ liệu tự động an toàn. Có thể dùng policy khác cho operation nội bộ, nhưng phải quyết định rõ header nào được giữ và header nào cần xóa.

## 8. Viết custom transformation thực sự

Delegation là lựa chọn tốt khi chỉ cần phối hợp built-ins. Khi cần biến đổi dữ liệu mà built-in không thể biểu đạt, có thể tự triển khai logic theo public API của `OperationRequestPreprocessor` hoặc `OperationResponsePreprocessor`.

Một custom transformation nên:

1. Đọc message đầu vào nhưng không sửa collection hoặc mảng byte dùng chung tại chỗ.
2. Chỉ tạo thay đổi ở những phần được yêu cầu.
3. Giữ nguyên method, URI path, status, content type và dữ liệu không liên quan.
4. Trả về operation message mới theo factory/builder công khai của đúng version thư viện.
5. Không phụ thuộc implementation class nội bộ hoặc constructor package-private.
6. Có test chứng minh phần được thay và phần được giữ nguyên.

```java
// Skeleton khái niệm: cách tạo OperationRequest mới phụ thuộc public API
// của phiên bản Spring REST Docs đang được dự án sử dụng.
final class CustomRequestPreprocessor
        implements OperationRequestPreprocessor {

    @Override
    public OperationRequest preprocess(OperationRequest request) {
        // 1. Đọc URI, headers, method, parameters và content.
        // 2. Tạo bản sao theo public factory/builder của version thư viện.
        // 3. Chỉ thay trường cần thiết.
        // 4. Trả về OperationRequest mới.
        return request;
    }
}
```

Đây là skeleton định hướng, chưa phải implementation biến đổi hoàn chỉnh. Cần kiểm tra chữ ký factory/builder trong dependency version đang dùng trước khi viết phần tạo operation mới. Nếu thay đổi chỉ là header hoặc pattern phổ biến, built-in processors thường ít rủi ro hơn.

## 9. Kiểm thử custom preprocessor

Đừng chỉ xác nhận endpoint test thành công. Cần kiểm tra riêng policy và snippet output. Với custom wrapper dùng built-ins, documentation test nên xác nhận:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Request có Authorization test | Snippet hiển thị placeholder, không có token test |
| Request có Cookie | Cookie không xuất hiện nếu policy yêu cầu remove |
| Request thuộc health path | Nhánh skip chạy đúng; output vẫn an toàn |
| Response có request ID động | Snippet có ID mẫu đã cấu hình |
| Response có Set-Cookie | Header bị loại khỏi raw response snippet theo policy |
| JSON response | Body vẫn hợp lệ và dễ đọc |
| Header/field thuộc contract | Descriptor mô tả đúng và không mâu thuẫn raw snippet |

Có thể test processor bằng unit test với operation fixture nếu dự án có cách tạo message ổn định theo public API. Integration/documentation test vẫn quan trọng vì kiểm tra cả recorder, processor và snippet output.

### 9.1. Kiểm tra snippet dẫn xuất

Sau khi chạy test, đọc các file liên quan:

```text
target/generated-snippets/orders-get/
├── http-request.adoc
├── http-response.adoc
├── curl-request.adoc
├── httpie-request.adoc
├── request-headers.adoc
└── response-headers.adoc
```

Tên file phụ thuộc descriptor và cấu hình. Tìm token fixture, cookie, ID ngẫu nhiên hoặc hostname nội bộ trong toàn bộ thư mục output. Kiểm tra cả HTML/PDF sau render nếu snippet được include vào tài liệu.

## 10. Xử lý lỗi và giới hạn

| Vấn đề | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Custom processor không được gọi | Truyền nhầm vào request/response wrapper hoặc chưa gắn vào document | Kiểm tra đúng nhánh và operation recorder |
| Token vẫn xuất hiện | Delegate chưa thay đúng header hoặc snippet khác còn giữ dữ liệu | Kiểm tra raw, cURL và HTTPie |
| Endpoint bị bỏ qua nhưng có secret | Điều kiện skip quá rộng hoặc dữ liệu đầu vào không an toàn | Thu hẹp điều kiện; không skip policy bảo vệ |
| Response header bị mất ngoài dự kiến | Dùng nhầm response policy cho operation đặc biệt | Tạo policy riêng theo contract |
| Snippet khác local và CI | Policy phụ thuộc host/môi trường hoặc dữ liệu động | Dùng fixture và cấu hình ổn định |
| Custom code làm mất metadata | Tự dựng operation message không giữ đủ thuộc tính | Dùng built-in/delegation hoặc sao chép đầy đủ bằng public API |
| Descriptor không khớp snippet | Processor thay/xóa thành phần được mô tả | Đồng bộ descriptor với contract và bản ghi cuối |
| Dùng implementation class nội bộ | Phụ thuộc chi tiết version | Chỉ dùng public API của dependency đang pin |

Không dùng custom processor để biến status lỗi thành thành công, tự thêm field còn thiếu, sửa URI sai hoặc xóa dấu vết của response không an toàn. Những việc đó làm tài liệu mất tính kiểm chứng.

## 11. Tái sử dụng và quản lý cấu hình

Một dự án có thể đặt custom processors trong test support package:

```text
src/test/java/
└── com/example/docs/
    ├── preprocessor/
    │   ├── PublicRequestPreprocessor.java
    │   └── PublicResponsePreprocessor.java
    └── OrdersDocumentationTests.java
```

Đặt tên theo policy và phạm vi áp dụng, không theo chi tiết implementation mơ hồ. Nếu nhiều module dùng cùng policy, cân nhắc một test-support library chung khi version Spring REST Docs và quy tắc bảo mật được quản lý thống nhất.

Các nguyên tắc quản lý:

- Ưu tiên constructor không trạng thái hoặc immutable configuration.
- Không lưu dữ liệu request/response giữa các lần gọi.
- Không dùng mutable static state để truyền dữ liệu giữa test.
- Làm rõ policy mặc định và ngoại lệ của từng endpoint.
- Xem thay đổi policy như thay đổi nội dung công khai của tài liệu.
- Đọc diff snippet trong code review để thấy tác động.

## 12. Tích hợp vào Asciidoctor và CI

Custom processor không thay đổi cách biên soạn tài liệu. Test vẫn sinh snippet vào output directory, Asciidoctor/Markdown vẫn include các file tương ứng. Điều cần thêm là xác minh policy được gọi và output an toàn trước khi render/publish.

```text
Clean generated snippets
          │
          ▼
Run documentation tests
          │
          ▼
Apply custom request/response preprocessors
          │
          ▼
Verify snippets and scan sensitive values
          │
          ▼
Render Asciidoctor / Markdown
          │
          ▼
Review HTML/PDF artifact
          │
          ▼
Publish
```

Nếu test bị skip, custom processor không chạy và output cũ có thể còn trong thư mục. Clean output trước test, chạy test bắt buộc trong lifecycle tài liệu và chỉ render từ snippet của lần build hiện tại.

## 13. Bài thực hành

Tạo hai custom preprocessors cho API orders:

- Request policy thay Bearer token bằng placeholder, chuẩn hóa correlation ID và loại Cookie.
- Response policy thay request ID thành giá trị mẫu, loại Set-Cookie và header node nội bộ, rồi định dạng JSON.
- Endpoint health check không áp dụng policy request public nhưng phải có quy tắc an toàn riêng.

**Nhiệm vụ:**

1. Viết `PublicRequestPreprocessor` triển khai `OperationRequestPreprocessor` và delegate built-ins.
2. Viết `PublicResponsePreprocessor` triển khai `OperationResponsePreprocessor`.
3. Thêm điều kiện rõ cho path health check và xác nhận nhánh skip.
4. Gắn hai processor vào documentation test bằng `preprocessRequest(...)` và `preprocessResponse(...)`.
5. Assertion status, body và header trên response thật.
6. Chạy test và kiểm tra request/response, cURL, HTTPie và descriptor snippets.
7. Thêm unit/integration test cho policy nếu có thể tạo operation fixture bằng public API của version thư viện.
8. Kiểm tra không còn token, Cookie hoặc metadata nội bộ trong output không được phép công bố.
9. Render Asciidoctor và review HTML/PDF.
10. Chạy clean build trong CI để bảo đảm snippet được tái tạo.

**Tiêu chí hoàn thành:** custom class có trách nhiệm rõ; policy request/response tách biệt; nhánh điều kiện có test; message thật được assertion; snippet an toàn và thống nhất với descriptor; build tái lập được.

## 14. Ghi nhớ

- Viết custom preprocessor khi cần policy riêng hoặc logic có điều kiện mà built-in chưa biểu đạt tốt.
- `OperationRequestPreprocessor` và `OperationResponsePreprocessor` xử lý hai loại operation message khác nhau.
- Custom wrapper có thể ủy quyền cho `preprocessRequest(...)` hoặc `preprocessResponse(...)` đã kết hợp built-in processors.
- Đặt policy theo contract và endpoint; điều kiện skip phải rõ và không làm lộ secret.
- Khi tự tạo operation message mới, chỉ dùng public factory/builder của đúng version thư viện và giữ đầy đủ metadata.
- Assertion kiểm tra request/response thật; preprocessor chỉ chuẩn hóa bản ghi snippet.
- Unit/integration test và review mọi snippet dẫn xuất giúp phát hiện lỗi policy trước khi publish.
