# Quốc tế hóa thông báo mà không đổi danh tính lỗi

Một ứng dụng thương mại điện tử phục vụ người dùng tiếng Việt và tiếng Anh. Khi số lượng hàng tồn không đủ, API trả thông báo tiếng Việt **“Số lượng sản phẩm không đủ”** hoặc tiếng Anh **“Insufficient stock”** tùy ngôn ngữ được yêu cầu. Nếu ứng dụng di động nhận diện lỗi bằng cách so sánh nguyên văn thông báo, chỉ cần người dùng đổi ngôn ngữ, ứng dụng có thể ngừng hiển thị nút điều chỉnh giỏ hàng. Một bản dịch được biên tập lại cũng có thể vô tình làm hỏng luồng xử lý lỗi.

Giải pháp là **tách danh tính lỗi ổn định dành cho máy** khỏi **thông điệp thay đổi theo ngôn ngữ dành cho con người**. Trong REST API, mã trạng thái HTTP, loại vấn đề (problem type), mã lỗi ứng dụng và các trường dữ liệu có cấu trúc phải giữ nguyên ý nghĩa; phần tiêu đề, mô tả và hướng dẫn được bản địa hóa khi cần.

Bài này thuộc chương **Lỗi API** của module **INTEGRATION_API_REST**. Người học thực hành thiết kế hợp đồng lỗi theo HTTP và **Problem Details (RFC 9457)**, dùng **Accept-Language**, **Content-Language**, catalog bản dịch, Java/Spring và OpenAPI; đồng thời kiểm tra ảnh hưởng đến cache, bảo mật, logging, retry và tính tương thích của client.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt rõ **danh tính lỗi**, **trạng thái HTTP**, **nội dung có cấu trúc** và **thông báo cho người dùng**.
2. Giải thích vì sao một lỗi nghiệp vụ phải giữ nguyên **problem type** và **application error code** ở mọi locale.
3. Thiết kế content negotiation cho ngôn ngữ bằng **Accept-Language**, ghi ngôn ngữ phản hồi bằng **Content-Language** và xử lý fallback nhất quán.
4. Tạo response **application/problem+json** có các trường tiêu chuẩn và extension có thể xử lý bằng máy.
5. Triển khai message catalog, resolver locale và exception handler trong **Spring Boot 3 / Spring Framework 6**.
6. Quốc tế hóa lỗi validation, liên thông giữa microservice và kiểm thử client mà không phụ thuộc nội dung bản dịch.

## 2. “Danh tính lỗi” là gì?

Một lỗi có thể được mô tả ở nhiều lớp:

| Lớp | Ví dụ | Có thay đổi theo ngôn ngữ? | Ai sử dụng? |
|---|---|---|---|
| **HTTP status** | 409 Conflict | **Không** | HTTP client, retry policy, observability |
| **Problem type URI** | https://api.example.test/problems/stock-conflict | **Không** | Client phân loại loại vấn đề theo RFC 9457 |
| **Application error code** | STOCK_CONFLICT | **Không** | Web/mobile SDK, rule xử lý nghiệp vụ, support |
| **Trường dữ liệu có cấu trúc** | availableQuantity: 2 | Tên trường và ngữ nghĩa **không**; định dạng hiển thị có thể khác | UI, workflow, automation |
| **Problem title** | Không đủ hàng / Insufficient stock | **Có** | Giao diện người dùng, hỗ trợ |
| **Problem detail** | Chỉ còn 2 sản phẩm / Only 2 items remain | **Có** | Người dùng và người xử lý sự cố |
| **HTTP reason phrase** | Conflict | Không dùng làm danh tính ứng dụng | Công cụ/debug; không phải hợp đồng phân loại nghiệp vụ |
| **Trace/request ID** | 01HZX... | **Không** | Liên kết log, trace và yêu cầu hỗ trợ |

**Nguyên tắc:** client xử lý theo dữ liệu ổn định như **status + type + code**, sau đó mới hiển thị văn bản. Mô tả tiếng Việt hay tiếng Anh không được quyết định client phải làm gì.

Ví dụ, cùng một tình huống **stock conflict** có thể dẫn đến thao tác “giảm số lượng hoặc chọn cửa hàng khác”. Client nên dựa vào mã **STOCK_CONFLICT**, số lượng có cấu trúc và các quyền hợp lệ; không tìm từ “hàng” hoặc “stock” trong chuỗi văn bản.

### 2.1. Ba lỗi dễ bị nhầm thành một

- **Trạng thái HTTP:** cho biết ý nghĩa chung của kết quả ở tầng giao thức, ví dụ **400** request không hợp lệ, **404** không tìm thấy resource, **409** xung đột trạng thái hiện tại, **422** nội dung đúng cú pháp nhưng không xử lý được theo điều kiện ngữ nghĩa, **429** vượt hạn mức, **503** tạm không phục vụ được.
- **Danh tính lỗi ứng dụng:** phân biệt những tình huống có thể cùng HTTP status, ví dụ **ORDER_VERSION_CONFLICT** và **STOCK_CONFLICT** đều có thể được thiết kế dùng 409.
- **Thông điệp:** cách giải thích lỗi cho một người dùng cụ thể bằng ngôn ngữ dễ hiểu. Câu chữ có thể sửa để thân thiện hoặc phù hợp văn hóa, trong khi hợp đồng máy giữ nguyên.

Không cần tạo một HTTP status mới cho từng lỗi nghiệp vụ; cũng không nên gom mọi lỗi vào HTTP 200 rồi yêu cầu client đọc trường message để biết có lỗi hay không.

### 2.2. Danh tính ổn định không đồng nghĩa giữ mã mãi mãi trong mọi trường hợp

Một mã lỗi là **hợp đồng công khai** khi client đã dựa vào nó. Nếu bản chất nghiệp vụ thay đổi đến mức mã cũ không còn đúng, hãy bổ sung mã mới, cập nhật tài liệu và lộ trình tương thích. **Không tái sử dụng cùng mã cho một lỗi khác** chỉ vì tên cũ có vẻ còn tiện. Việc dịch lại một câu chữ **không phải** lý do tạo mã mới.

## 3. RFC 9457: Problem Details và phần được phép dịch

**RFC 9457 — Problem Details for HTTP APIs** chuẩn hóa một dạng payload mô tả lỗi, thường dùng media type **application/problem+json**. Các member tiêu chuẩn thường gặp:

| Member | Ý nghĩa | Quy tắc i18n |
|---|---|---|
| **type** | URI nhận diện **loại vấn đề** | Giữ một URI ổn định giữa các locale |
| **title** | Mô tả ngắn, dễ đọc của loại vấn đề | Có thể dịch; theo RFC nên ổn định giữa các lần xảy ra cùng type, **ngoại trừ localization** |
| **status** | HTTP status dạng số, phản ánh status của phản hồi | Không dịch, phải đồng bộ với status thực |
| **detail** | Mô tả dễ đọc về lần lỗi cụ thể | Có thể dịch và nội suy dữ liệu đã được phép công khai |
| **instance** | URI xác định một lần xảy ra lỗi hoặc vị trí liên quan | URI/identifier không bị thay đổi theo câu chữ; tránh rò thông tin |

Các trường như **code**, **traceId**, **violations**, **currentVersion** là **extension members**, cần được mô tả rõ trong hợp đồng của chính API. Một response không nhất thiết phải có đủ mọi member tiêu chuẩn; đừng tự coi mọi trường trên là bắt buộc của RFC.

### 3.1. Cùng lỗi, hai biểu diễn ngôn ngữ

Client yêu cầu tiếng Việt:

~~~http
POST /v1/reservations HTTP/1.1
Host: api.example.test
Accept: application/problem+json, application/json
Accept-Language: vi-VN,vi;q=0.9,en;q=0.5
Content-Type: application/json

{"productId":"p-42","quantity":3}
~~~

Giả sử sản phẩm đang xung đột trạng thái giữ hàng, response có thể là:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Content-Language: vi
Cache-Control: no-store
Vary: Accept-Language

{
  "type": "https://api.example.test/problems/stock-conflict",
  "title": "Không đủ hàng",
  "status": 409,
  "detail": "Số lượng còn lại không đáp ứng yêu cầu.",
  "code": "STOCK_CONFLICT",
  "availableQuantity": 2,
  "traceId": "trace-7c91"
}
~~~

Cùng lỗi với người dùng chọn tiếng Anh:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Content-Language: en
Cache-Control: no-store
Vary: Accept-Language

{
  "type": "https://api.example.test/problems/stock-conflict",
  "title": "Insufficient stock",
  "status": 409,
  "detail": "The remaining quantity cannot fulfill this request.",
  "code": "STOCK_CONFLICT",
  "availableQuantity": 2,
  "traceId": "trace-7c91"
}
~~~

**Những giá trị không đổi:** 409, URI loại lỗi, code, tên các key JSON, số lượng 2 và ý nghĩa nghiệp vụ. **Những giá trị đổi:** title, detail, Content-Language. Hai response là minh họa cho **cùng điều kiện lỗi**, không ngụ ý một trace ID ngoài thực tế sẽ luôn dùng lại giữa các request khác nhau.

### 3.2. Tại sao không dịch problem type URI?

Các URI như:

~~~text
https://api.example.test/problems/stock-conflict
https://api.example.test/vi/loi/khong-du-hang
https://api.example.test/en/errors/insufficient-stock
~~~

nếu cùng được dùng như **type** sẽ khiến client có thể xem thành **ba danh tính khác nhau**. Hãy dùng một type URI duy nhất, ví dụ URI thứ nhất. **Tài liệu tại URI** có thể trả nội dung tiếng Việt hoặc tiếng Anh tùy negotiation, hoặc cung cấp đường dẫn tới tài liệu bản địa hóa. Việc thay ngôn ngữ của trang giải thích không được làm thay đổi giá trị **type** trong API contract.

Không nên để nội dung **title** trở thành khóa máy: một bản chỉnh sửa “Không đủ số lượng hàng” thay cho “Không đủ hàng” không được ảnh hưởng tính đúng của ứng dụng.

## 4. Chọn ngôn ngữ thông báo bằng HTTP

### 4.1. Accept-Language là sở thích ngôn ngữ, không phải danh tính lỗi

Client có thể gửi:

~~~http
Accept-Language: vi-VN,vi;q=0.9,en-US;q=0.7,en;q=0.5
~~~

Đây là danh sách ưu tiên với **quality values (q)**; mức q cao thường ưu tiên hơn. Ngôn ngữ dùng các tag theo **BCP 47**, ví dụ **vi**, **vi-VN**, **en**, **en-US**. Server nên có chính sách matching/fallback rõ ràng; không được tự đoán ngôn ngữ từ IP và coi đó là hợp đồng bắt buộc.

Một chính sách giả định của API:

1. Danh mục hỗ trợ tiếng Việt (**vi**) và tiếng Anh (**en**).
2. Nếu client đề nghị **vi-VN**, chọn bản dịch **vi**; nếu **en-US** hoặc **en-GB**, chọn **en** khi phù hợp.
3. Nếu header không có hoặc mọi lựa chọn đều không khớp, trả ngôn ngữ mặc định đã công bố, ví dụ **vi**.
4. Nếu thiếu một bản dịch cụ thể, lấy bản dự phòng có kiểm soát; log/metric thiếu bản dịch nội bộ, không trả tên translation key cho khách.
5. Gửi **Content-Language** phản ánh ngôn ngữ thực tế đã dùng, ngay cả khi ngôn ngữ khác với mong muốn ban đầu.

Đây là một **chính sách ứng dụng**, không phải thuật toán duy nhất RFC áp đặt. Phạm vi locale, ưu tiên khi nhiều ngôn ngữ có cùng q, xử lý wildcard và fallback theo vùng phải được thống nhất, kiểm thử.

### 4.2. Phân biệt Accept, Accept-Language và Content-Language

| HTTP field | Client/server dùng làm gì? | Ví dụ |
|---|---|---|
| **Accept** | Client nêu media type mong muốn | application/problem+json |
| **Accept-Language** | Client nêu ngôn ngữ ưu tiên của representation | vi-VN,vi;q=0.9 |
| **Content-Type** | Server chỉ ra loại dữ liệu response | application/problem+json |
| **Content-Language** | Server chỉ ra ngôn ngữ người dùng mục tiêu của nội dung trả về | vi |
| **Vary** | Cho cache biết những request header ảnh hưởng cách chọn representation | Accept-Language |

**Accept-Language không thay cho Accept.** Một client muốn tiếng Anh nhưng chỉ chấp nhận XML thì server vẫn cần xem xét **media type negotiation** hoặc trả lỗi phù hợp nếu không cung cấp định dạng được yêu cầu. Không tự biến nội dung JSON thành HTML vì tiêu đề đã được dịch.

### 4.3. Vary và bảo vệ dữ liệu riêng

Nếu response có thể được cache dùng lại và nội dung khác nhau theo Accept-Language, **Vary: Accept-Language** giúp cache không tái sử dụng nhầm bản tiếng Việt cho người yêu cầu tiếng Anh. Tuy nhiên, Vary **không phải giải pháp bảo vệ dữ liệu cá nhân**.

Đối với lỗi gắn với tài khoản, tồn kho đặt hàng hoặc quyền truy cập, chính sách đơn giản và an toàn thường là **Cache-Control: no-store**. Nếu một API thực sự cache response có bản dịch công khai, phải thiết kế cache key và Vary đúng ở **CDN/gateway/cache của ứng dụng**, kiểm tra cả trường hợp cache tùy biến không tuân theo cơ chế HTTP.

### 4.4. Không lạm dụng header và tham số ngôn ngữ

Header **Accept-Language** do client cung cấp có thể dài, không đúng cú pháp hoặc chứa danh sách nhiều ngôn ngữ. Server cần giới hạn input và chỉ chọn trong danh mục hỗ trợ; không dùng nguyên chuỗi header để tạo đường dẫn file bản dịch hoặc làm nhãn metric có số giá trị không giới hạn.

Nếu sản phẩm có **ngôn ngữ tài khoản** và **ngôn ngữ thiết bị** khác nhau, cần quyết định thứ tự ưu tiên có chủ đích, ví dụ một ứng dụng đặt ngôn ngữ theo tài khoản, nhưng client vẫn gửi Accept-Language tương ứng. Tránh có nhiều nguồn ưu tiên ngầm khiến web và mobile nhận thông điệp khác nhau.

## 5. Thiết kế bộ mã lỗi và catalog bản dịch

### 5.1. Bộ mã lỗi ổn định

Một bảng hợp đồng ví dụ:

| Code ổn định | Type ổn định | HTTP | Ý nghĩa nghiệp vụ |
|---|---|---:|---|
| **STOCK_CONFLICT** | /problems/stock-conflict | 409 | Hàng có thể đặt không đáp ứng yêu cầu |
| **ORDER_VERSION_CONFLICT** | /problems/order-version-conflict | 409 | Trạng thái đơn thay đổi trong khi người dùng cập nhật |
| **ORDER_NOT_FOUND** | /problems/order-not-found | 404 | Không tìm thấy đơn thuộc phạm vi có thể truy cập |
| **VALIDATION_FAILED** | /problems/validation-failed | 400 | Dữ liệu request sai ràng buộc đầu vào |
| **RATE_LIMITED** | /problems/rate-limited | 429 | Vượt giới hạn request đã định nghĩa |
| **SERVICE_TEMPORARILY_UNAVAILABLE** | /problems/temporarily-unavailable | 503 | Dịch vụ tạm không phục vụ được |

Trong thực tế, cần chọn status dựa trên **ngữ nghĩa chính xác**: một lỗi “không đủ hàng” có thể là 409 khi xung đột trạng thái resource đang đặt, hoặc một mã khác nếu domain/contract định nghĩa điều kiện khác. Bảng này là một thiết kế nhất quán để học, không phải quy tắc rằng mọi lỗi hết hàng bắt buộc là 409.

Với **ORDER_NOT_FOUND**, API cần cân nhắc bảo mật: không cho phép khách phân biệt “đơn của người khác” với “đơn không tồn tại” nếu chính sách yêu cầu che giấu sự tồn tại của resource.

### 5.2. Catalog message tách khỏi code

Lưu bản dịch theo key có tính tổ chức, không lưu chuỗi tiếng Việt trực tiếp ở enum lỗi:

~~~properties
# i18n/api-errors_vi.properties
errors.stock.title=Không đủ hàng
errors.stock.detail=Số lượng còn lại không đáp ứng yêu cầu.
errors.orderVersion.title=Đơn hàng đã thay đổi
errors.orderVersion.detail=Vui lòng tải lại đơn hàng và thử lại.
errors.notFound.title=Không tìm thấy đơn hàng
errors.notFound.detail=Không tìm thấy đơn hàng trong phạm vi được phép truy cập.
errors.validation.title=Dữ liệu yêu cầu không hợp lệ
errors.validation.detail=Vui lòng kiểm tra các trường được đánh dấu.
errors.unavailable.title=Dịch vụ tạm thời không khả dụng
errors.unavailable.detail=Vui lòng thử lại sau.
validation.NotBlank=Trường này không được để trống.
validation.Size=Độ dài của trường không hợp lệ.
validation.default=Giá trị không hợp lệ.
~~~

~~~properties
# i18n/api-errors_en.properties
errors.stock.title=Insufficient stock
errors.stock.detail=The remaining quantity cannot fulfill this request.
errors.orderVersion.title=The order has changed
errors.orderVersion.detail=Reload the order and try again.
errors.notFound.title=Order not found
errors.notFound.detail=The order was not found within your access scope.
errors.validation.title=Invalid request data
errors.validation.detail=Review the highlighted fields.
errors.unavailable.title=Service temporarily unavailable
errors.unavailable.detail=Please try again later.
validation.NotBlank=This field must not be blank.
validation.Size=This field has an invalid length.
validation.default=Invalid value.
~~~

Đây là ví dụ Spring **.properties UTF-8**. Với Java/Spring, phải cấu hình message source phù hợp và kiểm tra encoding khi build/deploy. Không thay đổi **STOCK_CONFLICT** khi biên tập câu tiếng Việt; translation key nội bộ có thể thay đổi khi refactor catalog miễn **contract công khai** không đổi.

### 5.3. Nội suy tham số mà không làm sai dữ liệu

Thông điệp có thể có tham số với **cùng message key** trong các file locale:

~~~properties
# Trong catalog vi
errors.stock.quantity=Chỉ còn {0} sản phẩm.

# Trong catalog en
errors.stock.quantity=Only {0} items remain.
~~~

Giá trị **availableQuantity** vẫn nên có trường JSON **dạng số** riêng để client tự render khi cần. Nếu thông điệp có số, ngày, tiền tệ hoặc số nhiều phức tạp, cân nhắc cơ chế định dạng bản địa hóa phù hợp thay vì nối chuỗi thủ công. **MessageFormat** của Java có quy tắc quote/dấu nháy riêng; với thông điệp dài và nhiều quy tắc số nhiều, phải kiểm thử mọi locale.

Tuyệt đối không đưa exception message, SQL, token, email của người khác hoặc dữ liệu chưa được kiểm tra vào template public. Message i18n là **giao diện với người dùng**, không phải log kỹ thuật.

## 6. Giữ cùng lỗi qua vòng đời API

### 6.1. Không làm mới code do wording thay đổi

Giả sử bản đầu hiển thị **“Đơn hàng đã được cập nhật”**, bản sau sửa thành **“Đơn hàng vừa thay đổi. Hãy tải lại để tiếp tục.”**. Hai thông báo cùng đại diện cho **ORDER_VERSION_CONFLICT** với **409** và cùng type URI. SDK không cần nâng phiên bản chỉ vì câu chữ thay đổi.

### 6.2. Không tái sử dụng code để che hành vi nghiệp vụ mới

Nếu hệ thống chuyển từ “hết hàng” sang “cần xác nhận tuổi người mua”, hành vi client phải khác. Không dùng **STOCK_CONFLICT** với câu chữ mới để tiết kiệm một enum. Hãy bổ sung code/type riêng và xác định status đúng; giữ cách xử lý cũ cho những client còn sử dụng contract cũ nếu cần.

### 6.3. Một loại lỗi có nhiều lần xảy ra

Các lần xảy ra khác nhau có thể có **instance**, **traceId** hoặc giá trị số lượng khác nhau, nhưng vẫn có chung **type** và **code**. Đây là phân biệt quan trọng giữa **problem type** với **problem occurrence** của RFC 9457.

### 6.4. Không biến bản dịch thành quy tắc điều hướng

Client cần phản ứng như sau:

~~~text
if problem.code == "ORDER_VERSION_CONFLICT":
    reloadOrder()
    showLocalizedConflictGuidance()
else if problem.code == "STOCK_CONFLICT":
    refreshStock()
    offerQuantityAdjustment()
else:
    showGenericError()
~~~

Không so sánh chuỗi **“Không đủ hàng”**, **“Insufficient stock”** hay tìm keyword trong detail. Nếu client không nhận ra code mới, nó vẫn phải có phương án hiển thị lỗi chung an toàn theo HTTP status và nội dung con người được server gửi.

## 7. Triển khai Spring Boot 3: chọn locale và bản dịch

Ví dụ này dùng **Spring MVC**, **Spring Framework 6**, **ProblemDetail** và **MessageSource**. Các class minh họa nằm cùng package; phần persistence, security, retry và hệ thống quan sát được giản lược để tập trung vào i18n của hợp đồng lỗi.

### 7.1. Khai báo locale resolver và message source

~~~java
import java.util.List;
import java.util.Locale;
import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.ReloadableResourceBundleMessageSource;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.i18n.AcceptHeaderLocaleResolver;

@Configuration
class ApiLocaleConfig {
    @Bean
    LocaleResolver localeResolver() {
        AcceptHeaderLocaleResolver resolver =
                new AcceptHeaderLocaleResolver();

        resolver.setSupportedLocales(List.of(
                Locale.forLanguageTag("vi"),
                Locale.ENGLISH
        ));
        resolver.setDefaultLocale(Locale.forLanguageTag("vi"));
        return resolver;
    }

    @Bean
    MessageSource messageSource() {
        ReloadableResourceBundleMessageSource source =
                new ReloadableResourceBundleMessageSource();
        source.setBasename("classpath:i18n/api-errors");
        source.setDefaultEncoding("UTF-8");
        source.setFallbackToSystemLocale(false);
        return source;
    }
}
~~~

Đặt các file **api-errors_vi.properties** và **api-errors_en.properties** từ mục 5 dưới **src/main/resources/i18n/**. Có thể thêm **api-errors.properties** cho bản dự phòng mặc định. Khi đăng ký bean tên **messageSource**, chú ý Spring Boot có cơ chế tự cấu hình MessageSource riêng; dự án nên chọn một cách quản trị catalog thống nhất để tránh vô tình có nhiều nguồn cấu hình khác nhau.

**AcceptHeaderLocaleResolver** dựa vào Accept-Language và danh sách locale hỗ trợ. Ở ví dụ, **vi** là ngôn ngữ mặc định; **en** được hỗ trợ, trong khi các biến thể vùng cần được kiểm thử để xác nhận fallback đúng theo phiên bản Spring và chính sách đã chọn. Resolver này không dùng để thay locale của request bằng cách setLocale ở phía server; client cần gửi Accept-Language phù hợp hoặc hệ thống triển khai một chính sách chọn locale khác rõ ràng.

Nếu dùng ngôn ngữ tài khoản, không nên để một request tự sửa locale toàn hệ thống. Ngôn ngữ được chọn cho response phải là **giá trị theo request**, không phải một mutable singleton dùng chung cho nhiều người dùng.

### 7.2. Enum lỗi giữ type, status và message key

~~~java
import org.springframework.http.HttpStatus;

enum PublicApiError {
    STOCK_CONFLICT(
        HttpStatus.CONFLICT,
        "stock-conflict",
        "errors.stock"
    ),
    ORDER_VERSION_CONFLICT(
        HttpStatus.CONFLICT,
        "order-version-conflict",
        "errors.orderVersion"
    ),
    ORDER_NOT_FOUND(
        HttpStatus.NOT_FOUND,
        "order-not-found",
        "errors.notFound"
    ),
    VALIDATION_FAILED(
        HttpStatus.BAD_REQUEST,
        "validation-failed",
        "errors.validation"
    ),
    SERVICE_TEMPORARILY_UNAVAILABLE(
        HttpStatus.SERVICE_UNAVAILABLE,
        "temporarily-unavailable",
        "errors.unavailable"
    );

    final HttpStatus status;
    final String slug;
    final String messagePrefix;

    PublicApiError(
            HttpStatus status,
            String slug,
            String messagePrefix) {
        this.status = status;
        this.slug = slug;
        this.messagePrefix = messagePrefix;
    }
}

class ApiException extends RuntimeException {
    private final PublicApiError error;

    ApiException(PublicApiError error) {
        super(error.name());
        this.error = error;
    }

    PublicApiError error() {
        return error;
    }
}
~~~

Các giá trị enum **STOCK_CONFLICT** và **ORDER_VERSION_CONFLICT**, status và slug type URI thuộc **contract công khai**. Ngược lại, **messagePrefix** chỉ là key nội bộ để tra bản dịch. Có thể tổ chức key khác đi mà không đổi danh tính lỗi.

Ví dụ một reservation service có thể ném:

~~~java
if (availableQuantity < requestedQuantity) {
    throw new ApiException(PublicApiError.STOCK_CONFLICT);
}
~~~

Business logic quyết định có thật sự hết hàng hay không. Một lỗi runtime bất ngờ **không được tùy tiện map thành STOCK_CONFLICT** để hiển thị thông báo dễ nghe; sự phân loại sai sẽ làm client xử lý sai nghiệp vụ.

### 7.3. RestControllerAdvice tạo Problem Details đã dịch

~~~java
import jakarta.servlet.http.HttpServletRequest;
import java.net.URI;
import java.util.Locale;
import org.springframework.context.MessageSource;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiErrorHandler {
    private final MessageSource messages;

    ApiErrorHandler(MessageSource messages) {
        this.messages = messages;
    }

    @ExceptionHandler(ApiException.class)
    ResponseEntity<ProblemDetail> onApiException(
            ApiException exception,
            HttpServletRequest request,
            Locale locale) {

        PublicApiError error = exception.error();
        ProblemDetail problem = createProblem(error, locale);

        // Chỉ đưa đường dẫn vào instance khi phù hợp với policy bảo mật.
        problem.setInstance(URI.create(request.getRequestURI()));

        Object traceId = request.getAttribute("trustedTraceId");
        if (traceId instanceof String id && !id.isBlank()) {
            problem.setProperty("traceId", id);
        }

        return response(problem, error, locale);
    }

    ProblemDetail createProblem(PublicApiError error, Locale locale) {
        String title = messages.getMessage(
                error.messagePrefix + ".title",
                null,
                "Request could not be completed",
                locale
        );
        String detail = messages.getMessage(
                error.messagePrefix + ".detail",
                null,
                "The request could not be completed.",
                locale
        );

        ProblemDetail problem =
                ProblemDetail.forStatusAndDetail(error.status, detail);
        problem.setType(URI.create(
                "https://api.example.test/problems/" + error.slug
        ));
        problem.setTitle(title);
        problem.setProperty("code", error.name());
        return problem;
    }

    ResponseEntity<ProblemDetail> response(
            ProblemDetail problem,
            PublicApiError error,
            Locale locale) {

        return ResponseEntity.status(error.status)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .header(
                        HttpHeaders.CONTENT_LANGUAGE,
                        locale.toLanguageTag()
                )
                .header(HttpHeaders.VARY, HttpHeaders.ACCEPT_LANGUAGE)
                .cacheControl(CacheControl.noStore())
                .body(problem);
    }
}
~~~

Handler trên giữ **status/type/code** ở cùng một nơi và chỉ lấy **title/detail** từ MessageSource. Trường **trustedTraceId** là thuộc tính minh họa do một filter/trace middleware đáng tin cậy đặt vào request; nếu chưa có cơ chế đó thì trường có thể vắng mặt. Không tự coi một chuỗi trace ID do client gửi là đã được kiểm tra.

Trong ứng dụng thật cần quyết định rõ:

- **Locale được chọn:** phản ánh bản dịch thực sự được dùng, kể cả khi thiếu file locale và phải fallback.
- **Missing translations:** không để client thấy tên key như **errors.stock.title**; ghi metric/log nội bộ và dùng một câu dự phòng được duyệt.
- **An toàn URI instance:** đường dẫn có thể chứa ID nhạy cảm; cần cân nhắc rút gọn hoặc bỏ trường tùy chính sách.
- **Đúng status:** không để một exception handler khác bọc response và đổi HTTP status nhưng giữ field status cũ.
- **Nơi phát lỗi:** gateway/WAF có thể phát 4xx/5xx trước khi vào Spring, vì vậy cần hợp đồng lỗi riêng hoặc chuẩn hóa ở edge nếu muốn nhất quán.

**Giới hạn quan trọng của ví dụ:** truyền Locale vào handler là cách Spring MVC thường cung cấp locale đã resolve. Khi fallback **từng key** sang catalog của ngôn ngữ khác, header Content-Language của ví dụ sẽ vẫn phản ánh locale request; để phản ánh chính xác ngôn ngữ nội dung, cần giải pháp kiểm tra độ đầy đủ catalog hoặc một translation service trả cả **text + effectiveLocale**. Cách đơn giản cho production là **không publish catalog thiếu key** và kiểm tra lúc build/test.

### 7.4. Trả lỗi validation với định danh từng vi phạm

Khi request có nhiều trường sai, một mã chung **VALIDATION_FAILED** giúp client nhận dạng loại lỗi, còn danh sách **violations** cho biết lỗi cụ thể theo trường. **Field name** và **reason code** cần ổn định; **message** được dịch.

~~~json
{
  "type": "https://api.example.test/problems/validation-failed",
  "title": "Dữ liệu yêu cầu không hợp lệ",
  "status": 400,
  "detail": "Vui lòng kiểm tra các trường được đánh dấu.",
  "code": "VALIDATION_FAILED",
  "violations": [
    {
      "field": "shippingAddress",
      "reason": "REQUIRED",
      "message": "Trường này không được để trống."
    },
    {
      "field": "contactName",
      "reason": "INVALID_LENGTH",
      "message": "Độ dài của trường không hợp lệ."
    }
  ]
}
~~~

Phiên bản tiếng Anh **giữ nguyên field/reason/code**, chỉ dịch title/detail/message. Nếu frontend muốn đưa lỗi xuống đúng ô nhập liệu, nó dựa vào **field**; nếu muốn chọn biểu tượng/hành động, dùng **reason**. Không tách tên trường bằng cách phân tích câu “Tên người nhận không được bỏ trống”.

Minh họa một handler có thể bổ sung vào **ApiErrorHandler** ở trên:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.MethodArgumentNotValidException;

@ExceptionHandler(MethodArgumentNotValidException.class)
ResponseEntity<ProblemDetail> onValidation(
        MethodArgumentNotValidException exception,
        Locale locale) {

    PublicApiError error = PublicApiError.VALIDATION_FAILED;
    ProblemDetail problem = createProblem(error, locale);

    List<Map<String, String>> violations =
            exception.getBindingResult().getFieldErrors().stream()
                    .map(fieldError -> {
                        String constraint = fieldError.getCode() == null
                                ? "Unknown"
                                : fieldError.getCode();
                        String reason = switch (constraint) {
                            case "NotBlank", "NotNull" -> "REQUIRED";
                            case "Size" -> "INVALID_LENGTH";
                            default -> "INVALID";
                        };
                        String translationKey = switch (reason) {
                            case "REQUIRED" -> "validation.NotBlank";
                            case "INVALID_LENGTH" -> "validation.Size";
                            default -> "validation.default";
                        };
                        String message = messages.getMessage(
                                translationKey,
                                null,
                                "Invalid value.",
                                locale
                        );
                        return Map.of(
                                "field", fieldError.getField(),
                                "reason", reason,
                                "message", message
                        );
                    })
                    .toList();

    problem.setProperty("violations", violations);
    return response(problem, error, locale);
}
~~~

Đoạn code ở trên là **một method được đặt bên trong class ApiErrorHandler**, không phải một Java file độc lập. Để dùng thật, cần bổ sung import trong cùng class và mở rộng cho các lỗi validation khác như **HandlerMethodValidationException**, lỗi JSON không đọc được, lỗi kiểu dữ liệu ở path/query, lỗi constraint ở cấp object và lỗi business validation.

Lưu ý **không gửi rejectedValue mặc định** vào response vì có thể chứa mật khẩu, token, thông tin cá nhân hoặc nội dung dài. Khi cần đưa **giới hạn min/max** cho UI, hãy xuất **dữ liệu có cấu trúc** được phép công khai và giữ kiểu dữ liệu đúng.

### 7.5. Kiểm tra nhiều lỗi mà không lẫn bản dịch

Trường hợp người dùng đặt locale tiếng Anh, một validation message có sẵn từ thư viện trong môi trường mặc định tiếng Việt có thể không cùng ngôn ngữ với phần title. Nếu muốn nhất quán, hãy **chọn nguồn translation có kiểm soát** cho các lỗi công khai và map từ validation constraint sang code công khai, thay vì đưa thẳng **exception.getMessage()** hoặc **FieldError.getDefaultMessage()** ra client.

Với câu có biến động số nhiều hoặc giống ngữ pháp khác nhau, cần catalog đủ khả năng biểu diễn điều đó; không ghép một chuỗi tiếng Việt/Anh cố định vào tên field. Một số trường hợp cần hiển thị **tên trường** đã dịch ở UI, nhưng tên trường trong JSON vẫn phải giữ nguyên.

## 8. OpenAPI: tài liệu hóa cấu trúc máy và ví dụ bản dịch

OpenAPI nên tài liệu hóa **cùng một response schema** cho mọi ngôn ngữ. Bản tiếng Việt/Anh là ví dụ của cùng cấu trúc, không tạo ra hai loại lỗi riêng biệt.

~~~yaml
openapi: 3.0.3
info:
  title: Reservation API
  version: 1.0.0
paths:
  /v1/reservations:
    post:
      summary: Reserve inventory
      parameters:
        - in: header
          name: Accept-Language
          required: false
          description: Preferred response language (vi or en)
          schema:
            type: string
            example: vi-VN,vi;q=0.9,en;q=0.5
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [productId, quantity]
              properties:
                productId:
                  type: string
                quantity:
                  type: integer
                  minimum: 1
      responses:
        '201':
          description: Reservation created
        '409':
          description: Inventory cannot satisfy request
          headers:
            Content-Language:
              description: Language of response text
              schema:
                type: string
                example: vi
            Vary:
              description: Representation may vary by language
              schema:
                type: string
                example: Accept-Language
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
              examples:
                vi:
                  value:
                    type: https://api.example.test/problems/stock-conflict
                    title: Không đủ hàng
                    status: 409
                    detail: Số lượng còn lại không đáp ứng yêu cầu.
                    code: STOCK_CONFLICT
                en:
                  value:
                    type: https://api.example.test/problems/stock-conflict
                    title: Insufficient stock
                    status: 409
                    detail: The remaining quantity cannot fulfill this request.
                    code: STOCK_CONFLICT
components:
  schemas:
    ApiProblem:
      type: object
      required: [type, title, status, code]
      properties:
        type:
          type: string
          format: uri
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
        instance:
          type: string
          format: uri-reference
        code:
          type: string
          description: Stable application error identifier
        traceId:
          type: string
~~~

Các **required** trong schema là **quyết định của API ví dụ**, không phải tất cả member đều bắt buộc theo RFC 9457. Khi dùng OpenAPI 3.0, hỗ trợ **uri-reference** của một số validator hoặc generator cần kiểm chứng; có thể thay bằng mô tả kiểu string nếu công cụ không hiểu format. Mục tiêu là hợp đồng thống nhất, không phụ thuộc vào một tính năng generator chưa được kiểm thử.

**Không dùng schema theo tên bản dịch** như VietnameseError, EnglishError nếu chúng chỉ khác title/detail. SDK cần kiểu **ApiProblem** và bảng **code/type** ổn định. Một số API có nhiều loại extension khác nhau có thể dùng oneOf/discriminator theo **code** khi cần, nhưng không dùng **locale** để phân loại lỗi nghiệp vụ.

### 8.1. Tài liệu mã lỗi có thể version hóa

Một bảng công khai nên chứa:

- Mã HTTP, problem type URI, application code, trường cấu trúc và điều kiện phát lỗi.
- Hành vi client hợp lệ: hiển thị, tải lại tài nguyên, giảm số lượng, chờ, hoặc liên hệ hỗ trợ.
- Retry policy nếu có, idempotency và khả năng kết quả chưa rõ.
- Locale được hỗ trợ và fallback; cách xử lý nếu client không gửi Accept-Language.
- Chính sách tương thích khi thêm code mới, đổi wording hoặc thay cấu trúc.

Việc dịch tài liệu cũng cần tuân theo nguyên tắc này: trang tiếng Anh và tiếng Việt có thể diễn đạt khác nhau, nhưng cùng xác định một contract.

## 9. Ai chịu trách nhiệm dịch lỗi: server, client hay gateway?

Trong hệ thống có web, mobile, server-to-server và microservice, một câu hỏi thiết kế quan trọng là **thành phần nào chọn ngôn ngữ và xuất thông điệp cuối cùng**. Không có một câu trả lời tối ưu cho tất cả sản phẩm, nhưng phải có **ranh giới trách nhiệm rõ ràng**.

### 9.1. Cách A: server trả title/detail đã dịch

**Luồng:** client gửi Accept-Language → REST API chọn locale → MessageSource sinh title/detail → client hiển thị.

Phù hợp khi nhiều client cần thông điệp thống nhất, bên thứ ba không có catalog nội bộ hoặc ứng dụng muốn quản lý nội dung hỗ trợ tại một nơi. Nhưng server phải kiểm soát catalog và fallback đầy đủ; một web app nhiều ngôn ngữ vẫn cần quản lý các thông điệp UI của riêng nó.

Ưu điểm: API công bố ví dụ phản hồi theo locale; client đơn giản hơn; đối tác có thể hiển thị detail được trả về. Nhược điểm: server phải triển khai, kiểm thử và phát hành bản dịch; thay lời thoại cần quy trình điều phối.

### 9.2. Cách B: server trả code + dữ liệu, client tự dịch

**Luồng:** REST API trả code/type và biến số có cấu trúc; web/mobile tra catalog của mình, chọn locale của giao diện và render thông điệp.

Phù hợp khi giao diện cần kiểm soát ngôn từ, bố cục và ngữ pháp phức tạp. Server vẫn nên trả **Problem Details hợp lệ** với title/detail an toàn và có ý nghĩa làm fallback; client có thể ưu tiên bản dịch UI theo code.

Ưu điểm: sản phẩm kiểm soát trải nghiệm ngôn ngữ và có thể hoạt động offline. Nhược điểm: mỗi client phải đồng bộ catalog, xử lý mã mới và có thể chênh lệch wording giữa các phiên bản. Không nên chỉ trả một **translation key nội bộ** rồi coi đó là hợp đồng công khai, trừ khi tổ chức chủ động thiết kế và quản trị key đó như một API contract ổn định.

### 9.3. Cách C: kết hợp hai mô hình

Trong nhiều REST API, cách thực tế là:

1. Server trả **HTTP status + type + code + machine-readable fields + localized title/detail**.
2. Web/mobile ưu tiên UX copy do sản phẩm quản lý cho một số code đặc biệt, đồng thời có fallback hiển thị detail của server.
3. Partner/CLI có thể hiển thị nội dung do server trả mà không phải nhân bản toàn bộ catalog.
4. **Mọi client xử lý logic theo mã ổn định**, độc lập ai là bên render thông báo.

Đây là cách tách **khả năng vận hành và tính tương thích** khỏi **lựa chọn trình bày**.

### 9.4. Microservice không nên lan truyền message của nhau làm contract

Xét:

~~~mermaid
sequenceDiagram
    actor U as Khách
    participant G as Public API / BFF
    participant O as Order Service
    participant I as Inventory Service
    U->>G: POST /orders + Accept-Language: vi
    G->>O: Lệnh đặt hàng + trace context
    O->>I: Reserve stock
    I-->>O: code=STOCK_CONFLICT, available=2
    O-->>G: code=STOCK_CONFLICT, available=2
    G-->>U: 409 + Problem Details tiếng Việt
~~~

Trong hệ thống nội bộ, Inventory Service có thể giao tiếp bằng **error code và tham số có cấu trúc**. Public API/BFF chọn ngôn ngữ và biểu diễn cuối cùng theo policy của sản phẩm. Nếu mỗi microservice tự chọn một locale khác nhau, client có thể nhận một response pha tiếng Anh, tiếng Việt hoặc tiếng khác trong cùng một lần xử lý.

**Khi downstream là đối tác bên ngoài:** đối tác có thể chỉ trả status và một message không ổn định. Adapter phải **map tình huống đã hiểu** sang mã lỗi nội bộ ổn định, không lấy nguyên văn thông điệp của đối tác làm **code** hoặc đưa vào response công khai mà không kiểm soát. Nếu không đủ bằng chứng để phân loại, trả lỗi dependency chung phù hợp và ghi chi tiết kỹ thuật ở log nội bộ.

### 9.5. Xử lý tác vụ bất đồng bộ

Một job chạy nền hoặc webhook đến sau nhiều giờ thường **không còn HTTP Accept-Language của request ban đầu**. Đừng cố suy luận locale từ thread hiện tại. Nếu một thông báo sau này cần được bản địa hóa (email, push, lịch sử sự kiện), có thể:

- Lưu **error code và tham số có cấu trúc** trong job/event, sau đó render theo ngôn ngữ hiện tại của người nhận.
- Hoặc lưu **locale đã được người dùng chọn khi tạo yêu cầu**, khi nghiệp vụ cần cố định ngôn ngữ cho bản ghi/biên nhận.
- Với email gửi cho nhiều người nhận, chọn locale **theo từng người nhận**, không gắn một chuỗi dịch duy nhất vào sự kiện nghiệp vụ dùng chung.

Trong mọi trường hợp, **dữ liệu sự kiện và audit phải giữ mã lỗi ổn định** để có thể phân tích xuyên ngôn ngữ và qua các bản cập nhật bản dịch.

## 10. Bảo mật và quyền riêng tư trong thông báo đa ngôn ngữ

Một câu văn được dịch đúng vẫn có thể là lỗi bảo mật nếu nó tiết lộ những chi tiết không nên công khai.

### 10.1. Phân loại trước khi dịch

| Loại thông tin | Có nên đưa vào detail công khai? | Giải thích |
|---|---|---|
| Mô tả chung về lỗi request | Thường có | Giúp người dùng sửa request |
| Tên trường được phép chỉnh sửa | Có thể | Tránh lộ những field nội bộ hoặc trường không được quyền xem |
| Số lượng còn có thể mua | Chỉ khi nghiệp vụ cho phép | Có thể nhạy cảm theo cửa hàng/khách hàng |
| Stack trace, class, SQL, connection URL | **Không** | Thuộc thông tin nội bộ và có thể rò hạ tầng |
| Token, mật khẩu, khóa, cookie | **Không** | Không được xuất trong lỗi/log |
| Email, số điện thoại của người khác | **Không** | Vi phạm phạm vi quyền dữ liệu |
| ID request/trace được kiểm soát | Có thể | Hỗ trợ điều tra, không làm lộ định danh nhạy cảm |
| Trạng thái tồn tại của resource không có quyền truy cập | Theo policy che giấu | Có thể cố ý trả 404 nhất quán |

Ví dụ API đăng nhập không nên trả hai loại lỗi chi tiết khác nhau **“Tài khoản không tồn tại”** và **“Sai mật khẩu”** nếu điều đó cho phép dò tìm user account. Đổi sang tiếng Anh không làm thay đổi yêu cầu bảo mật này: cả hai ngôn ngữ phải bảo đảm cùng mức **information disclosure**.

### 10.2. Không truyền exception message vào bản dịch

Sai lầm phổ biến:

~~~java
// Không nên đưa exception message không kiểm soát ra API public.
problem.setDetail(exception.getMessage());
~~~

Thay vào đó, dùng một **public error category** được phê duyệt:

~~~java
// Chỉ public code và message đã được chọn từ catalog.
problem.setProperty("code", error.name());
problem.setDetail(safeLocalizedDetail);
// Stack trace, upstream response, SQL... chỉ có trong log được phân quyền.
~~~

**Message injection / XSS:** nếu detail chứa tên sản phẩm hoặc giá trị người dùng nhập vào, cần giới hạn độ dài và kiểm tra phạm vi dữ liệu. Frontend phải hiển thị như **text**, không chèn raw HTML vào DOM. Bản dịch không được biến input thành một đoạn HTML được tin cậy.

### 10.3. Locale là input không đáng tin cậy

Không xây tên file bằng cách nối thẳng toàn bộ chuỗi **Accept-Language** từ request. Chỉ chọn những locale trong danh sách được phép, giới hạn số phần tử/kích thước header, và không chạy logic đặc biệt dựa trên một tag tùy ý. Không dùng locale làm quyền truy cập hoặc dấu hiệu xác minh danh tính người dùng.

### 10.4. Không dịch máy móc các giá trị dùng cho logic

Tránh dịch:

- Application code, reason code, HTTP status và JSON property names.
- Enum nghiệp vụ trong payload khi là **dữ liệu máy** (ví dụ **PENDING**, **PAID**).
- Order ID, transaction ID, trace ID, idempotency key.
- ISO timestamp trong dữ liệu máy hoặc số lượng dưới dạng JSON number.

UI có thể **định dạng bản địa hóa** khi hiển thị tiền, ngày giờ, tên trạng thái hoặc số thập phân; điều này không làm thay đổi kiểu dữ liệu và ý nghĩa của trường API. Đừng biến **availableQuantity: 2** thành chuỗi tiếng Việt **“2 sản phẩm”** nếu client cần dùng giá trị đó để tính toán.

## 11. Observability: theo dõi lỗi xuyên locale

Tách log/metric kỹ thuật khỏi nội dung hiển thị là yêu cầu vận hành, không chỉ là lựa chọn UX.

### 11.1. Log nên dựa trên code ổn định

Một sự kiện log rút gọn:

~~~json
{
  "timestamp": "2026-11-18T10:50:00Z",
  "route": "POST /v1/reservations",
  "httpStatus": 409,
  "problemType": "https://api.example.test/problems/stock-conflict",
  "errorCode": "STOCK_CONFLICT",
  "locale": "vi",
  "traceId": "trace-7c91"
}
~~~

Nếu một người dùng tiếng Anh nhận cùng loại lỗi, metric **errorCode=STOCK_CONFLICT** vẫn giống hệt. Nhờ vậy có thể thống kê số lần hết hàng mà không phải cộng nhiều chuỗi bản dịch và phiên bản wording khác nhau.

### 11.2. Không dùng title/detail làm metric label

Những nhãn có số lượng giá trị thấp và được kiểm soát thường phù hợp:

- HTTP status, method, route template.
- Application error code đã được công bố.
- Một vài nhóm locale đã chuẩn hóa nếu mục đích phân tích thực sự cần.

**Không nên gắn detail đã nội suy**, email, user ID, URL có ID riêng hoặc nguyên chuỗi Accept-Language làm label. Chúng tạo **cardinality rất cao**, tăng chi phí, gây rò dữ liệu và làm dashboard khó dùng.

### 11.3. Cùng code giúp đo hiệu quả bản dịch

Có thể đo:

- Tỷ lệ lỗi theo **code**, không phụ thuộc ngôn ngữ.
- Tỷ lệ response phải fallback vì thiếu key, theo locale đã biết.
- Tỷ lệ client không nhận diện được code mới (nếu có telemetry phù hợp).
- Tỷ lệ người dùng sửa request thành công sau khi thấy thông báo.
- Tần suất phiên dịch thay đổi copy hoặc khiến giao diện bị cắt dòng.

Nếu wording được đổi để người dùng dễ hiểu hơn, đó là **thay đổi nội dung hiển thị**. Nên đánh giá bằng hành vi người dùng; không làm tăng giảm số lượng code hoặc tự thay đổi retry policy.

## 12. Kiểm thử hợp đồng và quốc tế hóa

Test cần chứng minh đồng thời **hai điều**: thông điệp có thể khác nhau giữa các locale, còn **danh tính lỗi và cấu trúc máy vẫn đúng**.

### 12.1. Ma trận kiểm thử

| Kịch bản | Đầu vào | Kết quả mong đợi |
|---|---|---|
| Tiếng Việt | Accept-Language: vi | title/detail tiếng Việt, Content-Language phù hợp |
| Tiếng Anh | Accept-Language: en | title/detail tiếng Anh, Content-Language phù hợp |
| Biến thể vùng | Accept-Language: vi-VN hoặc en-US | Chọn locale hỗ trợ theo policy, không đổi code/type |
| Ưu tiên q | vi;q=0.4,en;q=0.9 | Chọn tiếng Anh nếu danh mục hỗ trợ và negotiation đúng |
| Thiếu header | Không gửi Accept-Language | Dùng ngôn ngữ mặc định đã công bố |
| Locale không hỗ trợ | Accept-Language: fr | Fallback an toàn, không trả tên translation key |
| Missing key | Cố ý bỏ một bản dịch trong test | Build/test báo thiếu hoặc fallback theo policy; không rò key |
| Validation nhiều field | Gửi request thiếu dữ liệu | field/reason/code ổn định; chỉ message thay đổi |
| 401/403/404 | Truy cập resource không có quyền | Nội dung hai locale không tiết lộ thêm thông tin |
| Cache | Gọi cùng URI với vi rồi en qua gateway | Không trả nhầm bản dịch hoặc dữ liệu của người khác |
| Mã lỗi mới | Client cũ không biết code | Fallback hiển thị chung, không crash |
| Đồng thời nhiều user | Gửi song song vi/en | Không lẫn locale giữa các request |
| Job bất đồng bộ | Email/push sau vài giờ | Chọn locale theo policy lưu trên job hoặc người nhận |

Với bảng này, các yêu cầu thực tế cần có **test data, build version, owner, tiêu chí PASS/FAIL và bằng chứng**; ma trận là hướng dẫn xây bài test chứ không có nghĩa test đã được chạy.

### 12.2. Ví dụ MockMvc kiểm tra hai ngôn ngữ

Với controller test có thể tạo tình huống ném **ApiException(STOCK_CONFLICT)**, cách kiểm tra:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ErrorLocalizationTest {
    @Autowired
    MockMvc mvc;

    @Test
    void sameIdentityForVietnameseAndEnglish() throws Exception {
        String input = """
                {"productId":"p-42","quantity":3}
                """;

        mvc.perform(post("/v1/reservations")
                .header("Accept-Language", "vi")
                .contentType(MediaType.APPLICATION_JSON)
                .content(input))
           .andExpect(status().isConflict())
           .andExpect(header().string("Content-Language", "vi"))
           .andExpect(jsonPath("$.code").value("STOCK_CONFLICT"))
           .andExpect(jsonPath("$.status").value(409))
           .andExpect(jsonPath("$.type").value(
                "https://api.example.test/problems/stock-conflict"))
           .andExpect(jsonPath("$.title").value("Không đủ hàng"));

        mvc.perform(post("/v1/reservations")
                .header("Accept-Language", "en")
                .contentType(MediaType.APPLICATION_JSON)
                .content(input))
           .andExpect(status().isConflict())
           .andExpect(header().string("Content-Language", "en"))
           .andExpect(jsonPath("$.code").value("STOCK_CONFLICT"))
           .andExpect(jsonPath("$.status").value(409))
           .andExpect(jsonPath("$.type").value(
                "https://api.example.test/problems/stock-conflict"))
           .andExpect(jsonPath("$.title").value("Insufficient stock"));
    }
}
~~~

**Điều kiện để test này chạy:** phải có endpoint **POST /v1/reservations** với service/stub được chuẩn bị để cố ý trả STOCK_CONFLICT cho payload ví dụ; cấu hình LocaleResolver, MessageSource và ApiErrorHandler như các phần trước. Đoạn test là **mẫu**, chưa bao gồm controller/service/stub nên không tự chạy độc lập. Trong dự án thật, nên bổ sung test song song nhiều locale và tình huống fallback/thiếu key.

Test **không nên** dùng sự khác biệt trong title để kết luận đó là hai lỗi khác nhau. Assertion về title chứng minh bản dịch, còn assertion về **code/type/status** chứng minh tính tương thích.

### 12.3. Kiểm thử thiếu key trước khi triển khai

Một quality gate của quá trình build có thể:

1. Xác định tập **message keys** bắt buộc từ bảng code lỗi công khai.
2. So sánh sự hiện diện của từng key trong mỗi locale được hỗ trợ.
3. Kiểm tra placeholder giống nhau về **số lượng, thứ tự và kiểu tham số**; không để bản tiếng Anh có {1} khi chỉ truyền {0}.
4. Kiểm tra encoding UTF-8, ký tự đặc biệt, tiếng Việt có dấu và quy tắc MessageFormat.
5. Chạy contract tests với cả bản dịch và fallback, bao gồm thời điểm response do **gateway** tự phát sinh.

Không nên chỉ phát hiện key thiếu khi khách hàng lần đầu chọn một ngôn ngữ ít dùng. Với các locale có bản dịch chưa hoàn chỉnh, phải công bố rõ chính sách fallback và không gửi header Content-Language gây hiểu sai.

### 12.4. Kiểm thử qua đường gateway và CDN

@RestControllerAdvice chỉ xử lý lỗi **đã tới Spring**. Ví dụ, một API gateway có thể tự trả **401**, **403**, **429**, **502**, **503** hoặc **504**. Nếu yêu cầu hệ thống là một định dạng Problem Details nhất quán, cần kiểm thử các lỗi do gateway phát sinh:

- Gateway có giữ **code/type ổn định** giữa locale không?
- Lỗi do chính gateway tạo có được ánh xạ vào catalog chung hay một public code phù hợp không?
- Header **Content-Language** và **Cache-Control** có đúng không?
- Không biến một lỗi **401/403** thành thông tin cho phép đoán người dùng/tài nguyên tồn tại.
- Client không hiểu một lỗi edge mới có fallback an toàn hay không?

Đây là **kiểm thử tích hợp**. Một unit test cho MessageSource không chứng minh CDN hoặc WAF sẽ tuân theo cùng contract.

## 13. Chuyển đổi từ API cũ mà không phá vỡ client

Giả sử API phiên bản cũ chỉ trả:

~~~json
{
  "error": "Sản phẩm không đủ số lượng",
  "message": "Vui lòng giảm số lượng trong giỏ hàng"
}
~~~

Một số client dùng chuỗi **error** để phân loại, số khác hiển thị **message**. Việc đổi ngay cả hai thành tiếng Anh theo Accept-Language có thể làm những client cũ không nhận ra lỗi.

### 13.1. Lộ trình migration được khuyến nghị

**Giai đoạn 1 — Thêm danh tính ổn định:** bổ sung **code** và **type**, giữ trường lỗi cũ trong thời gian tương thích đã công bố; cập nhật tài liệu rằng trường legacy không được dùng để phân loại. Chọn HTTP status đúng cho từng trường hợp.

**Giai đoạn 2 — Nâng SDK/client:** chuyển tất cả nhánh xử lý lỗi sang **code/type/status**. Xây fallback khi gặp code chưa biết. Nếu UI cần localized string, sử dụng title/detail hoặc catalog phía client.

**Giai đoạn 3 — Bắt đầu negotiation ngôn ngữ:** chỉ áp dụng khi hợp đồng đã được thông báo và client cũ không còn dựa vào chuỗi tiếng Việt mặc định, hoặc thêm phiên bản/endpoint tương thích tách biệt. Kiểm thử bản dịch và quan sát client theo phiên bản.

**Giai đoạn 4 — Chuẩn hóa Problem Details:** sử dụng **application/problem+json** cho lỗi theo hợp đồng được version hóa. Nếu thay media type hoặc schema làm client cũ không parse được, phải dùng biện pháp tương thích rõ ràng thay vì giả định rằng mọi client chấp nhận JSON nào cũng giống nhau.

**Giai đoạn 5 — Dọn legacy sau thời hạn:** chỉ loại bỏ trường cũ khi có bằng chứng client đã nâng cấp hoặc chính sách hỗ trợ đã hết hiệu lực; lưu ADR và thông báo thay đổi breaking change.

Một response chuyển tiếp trong giai đoạn đầu có thể là:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json
Cache-Control: no-store

{
  "error": "Sản phẩm không đủ số lượng",
  "message": "Vui lòng giảm số lượng trong giỏ hàng",
  "code": "STOCK_CONFLICT",
  "type": "https://api.example.test/problems/stock-conflict"
}
~~~

Không tuyên bố đây là **Problem Details RFC 9457** nếu media type và cấu trúc chưa tuân theo hợp đồng mới. Khi hoàn tất migration, dùng một dạng public contract được tài liệu hóa và kiểm thử thực tế, hạn chế hỗ trợ song song quá nhiều cấu trúc lâu dài.

### 13.2. Thay đổi nào là breaking?

| Thay đổi | Tác động tương thích thường gặp |
|---|---|
| Sửa câu chữ title/detail trong một locale | **Không nên** ảnh hưởng logic client đúng chuẩn; vẫn cần review UX |
| Thêm locale mới, giữ fallback cũ | Thường tương thích, nhưng phải kiểm tra negotiation/cache |
| Thêm error code mới cho tình huống mới | Client cần fallback; có thể ảnh hưởng client chỉ xử lý whitelist |
| Đổi **STOCK_CONFLICT** thành tên khác | **Breaking** nếu client dùng code cũ |
| Đổi type URI nhưng vẫn cùng lỗi | **Breaking** với client dùng type để nhận diện |
| Đổi 409 thành 200 hoặc 422 | Có thể **breaking** với retry, exception handling và SDK |
| Đổi kiểu dữ liệu **availableQuantity** từ number sang localized string | **Breaking** với consumer dùng dữ liệu máy |
| Đổi media type/schema mà client không hỗ trợ | Có thể **breaking** dù thông điệp vẫn là tiếng Việt |

Vì vậy, muốn i18n an toàn phải xác định **đường ranh giữa presentation và contract** trước khi bắt đầu dịch. “Chỉ sửa lời nhắn” sẽ trở thành breaking change nếu hệ thống cũ đã lấy lời nhắn làm khóa nghiệp vụ.

## 14. Các anti-pattern cần tránh

### 14.1. So sánh chuỗi thông điệp để xử lý lỗi

~~~javascript
// Fragile: chỉ cần đổi bản dịch là nhánh xử lý không còn chạy.
if (error.message === "Không đủ hàng") {
  showAdjustCartDialog();
}

// Stable: xử lý theo code công khai.
if (error.code === "STOCK_CONFLICT") {
  showAdjustCartDialog();
}
~~~

Chủ động thêm lỗi mới vào bảng code hoặc tài liệu; không dùng regex kiểm tra những từ như **invalid**, **expired**, **không hợp lệ** trong detail.

### 14.2. Dịch luôn mã lỗi

Sai:

~~~json
{"code":"KHONG_DU_HANG","message":"Không đủ hàng"}
~~~

Nếu cùng lỗi lại trả **INSUFFICIENT_STOCK** cho người dùng tiếng Anh, danh tính không ổn định. Hãy chọn một mã công khai nhất quán và giữ nguyên ở mọi locale:

~~~json
{"code":"STOCK_CONFLICT","message":"Không đủ hàng"}
~~~

### 14.3. Mỗi lần dịch tạo một type URI mới

Problem type phân loại lỗi. URI dịch theo ngôn ngữ biến một loại lỗi thành nhiều loại và làm SDK/analytics phân mảnh. Tài liệu về type có thể được bản địa hóa, **type URI trong response giữ nguyên**.

### 14.4. Trả một thông điệp lỗi nội bộ đã dịch nhầm ra ngoài

Một thông điệp database như **Duplicate key value violates unique constraint** không phải câu giúp người dùng sửa lỗi, có thể chứa thông tin schema. Cần map sang lỗi công khai có nguyên nhân rõ ràng, ví dụ **ORDER_VERSION_CONFLICT**, hoặc lỗi chung an toàn khi chưa biết.

### 14.5. Bản dịch không đầy đủ làm lộ key

Nếu một locale thiếu **errors.orderVersion.detail**, đừng trả nguyên key đó trong trường detail. Thiết lập fallback có thông điệp an toàn và kiểm tra catalog trước release. Với response pha nhiều ngôn ngữ, chọn cách báo cáo Content-Language thận trọng và sửa catalog.

### 14.6. Lưu locale trên biến toàn cục chia sẻ giữa request

Khi hai request vi và en chạy đồng thời, mutable global có thể làm người dùng nhận ngôn ngữ của nhau. Locale phải gắn **đúng request context** hoặc đúng notification recipient; không lưu thành một giá trị thay đổi được của toàn application.

### 14.7. Dùng Vary như một cơ chế phân quyền

**Vary: Accept-Language** chỉ hỗ trợ lựa chọn representation theo ngôn ngữ tại cache tuân chuẩn. Nó không thay cho **Cache-Control: private/no-store**, kiểm tra authorization, tenant isolation và cơ chế bảo vệ dữ liệu cá nhân.

### 14.8. Mã lỗi gắn với bản dịch thay vì hành động

Không thiết kế code như **DISPLAY_RED_TOAST**, **MESSAGE_FOR_VIETNAMESE** hoặc **PLEASE_TRY_AGAIN**. Chúng mô tả giao diện hoặc wording hơn là bản chất lỗi. Một code tốt diễn đạt **điều kiện có thể nhận diện, hành vi nào cần xử lý và phạm vi nghiệp vụ**.

### 14.9. Chỉ quốc tế hóa lỗi từ Spring

Lỗi do **API gateway, WAF, proxy** tạo ra có thể đi thẳng tới client mà không qua **@RestControllerAdvice**. Nếu yêu cầu nền tảng là contract lỗi đồng nhất, phải chuẩn hóa ở mọi tầng trả HTTP response hoặc nêu rõ ngoại lệ trong tài liệu.

## 15. Bài tập: thiết kế API lỗi đa ngôn ngữ cho đơn hàng

Một ứng dụng giao hàng phục vụ **vi**, **en** và dự định mở rộng thêm một ngôn ngữ thứ ba. Hệ thống có ba tình huống:

- Khách cập nhật đơn hàng bằng phiên bản cũ.
- Người dùng nhập địa chỉ giao hàng rỗng.
- Dịch vụ báo giá vận chuyển tạm thời không sẵn sàng.

Nhóm phát triển hiện trả:

~~~json
{"error": "Đơn đã thay đổi", "message": "Hãy tải lại đơn"}
~~~

App Android cũ kiểm tra giá trị **error** để quyết định tải lại đơn; app iOS chỉ hiển thị **message**. Hệ thống có Spring API, API gateway trả lỗi 503 khi không có upstream khả dụng, và một worker gửi email thông báo sau khi đặt hàng.

### 15.1. Nhiệm vụ

1. Xác định **HTTP status, problem type URI và code ổn định** cho ba tình huống.
2. Viết hai payload **application/problem+json** cho lỗi cập nhật đơn, tương ứng tiếng Việt và tiếng Anh; chỉ rõ trường nào đổi.
3. Thiết kế header **Accept-Language**, **Content-Language**, **Cache-Control**, **Vary**; nêu chính sách khi locale không được hỗ trợ.
4. Thiết kế validation **violations** để frontend đánh dấu đúng **shippingAddress** mà không phân tích bản dịch.
5. Đề xuất cách xử lý lỗi 503 do **gateway tự tạo** để client nhận danh tính lỗi ổn định.
6. Lập kế hoạch nâng cấp Android/iOS mà không gây hỏng app cũ; mô tả khi nào được phép dịch trường error legacy.
7. Với worker gửi email sau nhiều giờ, chọn locale dựa trên thông tin nào? Những gì phải lưu vào event để không mất danh tính lỗi?
8. Nêu ít nhất năm kiểm thử chứng minh hai ngôn ngữ khác câu chữ nhưng cùng logic nghiệp vụ.

### 15.2. Một lời giải tham khảo

| Tình huống | HTTP | Type URI | Code |
|---|---:|---|---|
| Cập nhật đơn từ phiên bản cũ | **409** | /problems/order-version-conflict | ORDER_VERSION_CONFLICT |
| Địa chỉ giao hàng rỗng | **400** | /problems/validation-failed | VALIDATION_FAILED |
| Dịch vụ báo giá tạm không khả dụng | **503** theo hợp đồng được chọn | /problems/temporarily-unavailable | SERVICE_TEMPORARILY_UNAVAILABLE |

Với lỗi version conflict, một response tiếng Việt:

~~~json
{
  "type": "https://api.example.test/problems/order-version-conflict",
  "title": "Đơn hàng đã thay đổi",
  "status": 409,
  "detail": "Vui lòng tải lại đơn hàng và thử lại.",
  "code": "ORDER_VERSION_CONFLICT",
  "currentVersion": 12
}
~~~

Bản tiếng Anh:

~~~json
{
  "type": "https://api.example.test/problems/order-version-conflict",
  "title": "The order has changed",
  "status": 409,
  "detail": "Reload the order and try again.",
  "code": "ORDER_VERSION_CONFLICT",
  "currentVersion": 12
}
~~~

Server chỉ trả **currentVersion** nếu người gọi được phép xem phiên bản đó. Các giá trị **409, type, code, currentVersion** không bị dịch. Nếu dùng ETag và If-Match theo hợp đồng HTTP, khi precondition thất bại có thể phù hợp hơn với **412 Precondition Failed**; bài tập chọn 409 cho **business-level version conflict** để minh họa, không phủ nhận 412 trong trường hợp dùng HTTP conditional request.

Với validation, danh sách có thể là:

~~~json
{
  "code": "VALIDATION_FAILED",
  "violations": [
    {
      "field": "shippingAddress",
      "reason": "REQUIRED",
      "message": "Trường này không được để trống."
    }
  ]
}
~~~

Đây là **trích đoạn extension fields**, không phải một Problem Details đầy đủ; khi trả thật cần thêm status/type/title và media type như hợp đồng.

Đối với gateway 503, hãy cấu hình lớp gateway phát một **errorCode/type** công khai nếu khả năng cho phép, hoặc dùng gateway error-response mapping đã được kiểm thử; không hy vọng Spring sẽ xử lý lỗi khi request chưa đến nó. Bản dịch có thể được thực hiện ở gateway hoặc ở một lớp xử lý lỗi thống nhất, nhưng phải giữ cùng code.

Android cũ cần nâng cấp sang đọc **code** trước; trong giai đoạn tương thích giữ **error** cũ theo contract. iOS chỉ hiển thị có thể chấp nhận message được dịch nếu parse và display an toàn, nhưng vẫn phải test các phần màn hình/flow liên quan. Sau khi biết tỷ lệ phiên bản đã được chuyển đổi, mới xác nhận thời hạn bỏ trường legacy.

Worker lưu **event type/error code, tham số có cấu trúc, người nhận và lựa chọn locale theo policy**; không lưu một message tiếng Việt để dùng lại cho mọi người. Cần kiểm tra fallback trong trường hợp người dùng đổi ngôn ngữ sau khi tạo đơn.

Kiểm thử tiêu biểu: vi/en trên cùng lỗi; Accept-Language ưu tiên q; locale unsupported; không có header; nhiều request song song; validation giữ field/reason; gateway tạo 503; cache không rò ngôn ngữ/dữ liệu; client cũ và client mới xử lý cùng lỗi.

## 16. Checklist trước khi phát hành API đa ngôn ngữ

- [ ] Mỗi lỗi có **HTTP status**, **problem type URI**, **application code** và hành vi client được công bố rõ.
- [ ] **Type/code/status** và tên JSON property **không đổi** theo locale.
- [ ] **Title/detail/violation.message** có thể dịch; **field/reason/ID/numeric fields** giữ ngữ nghĩa và kiểu dữ liệu.
- [ ] Có **Accept-Language**, chính sách locale được hỗ trợ và fallback rõ ràng; **Content-Language** phản ánh nội dung thực tế.
- [ ] **Accept** và **Content-Type** được xử lý độc lập với lựa chọn ngôn ngữ.
- [ ] **Cache-Control**, **Vary** và cache key được kiểm chứng trên đường qua CDN/gateway; không lưu lỗi cá nhân nhạy cảm ngoài ý muốn.
- [ ] Catalog bản dịch có cùng các key, placeholder và quy tắc định dạng; không để lộ key thiếu cho client.
- [ ] Bản dịch và dữ liệu nội suy không tiết lộ thông tin nội bộ, PII, token hoặc resource không có quyền truy cập.
- [ ] Spring exception handler không map mọi exception thành cùng mã hoặc làm sai HTTP status.
- [ ] Validation trả **field/reason** ổn định để frontend xử lý không phụ thuộc câu chữ.
- [ ] Error do gateway tạo được kiểm thử; không giả định mọi request lỗi đều đến Spring.
- [ ] Log/trace/metric nhóm theo **error code và route template**, không dùng localized detail làm metric label.
- [ ] Có test cho **vi/en, fallback, thiếu key, concurrent requests, client cũ, cache, validation và gateway**.
- [ ] OpenAPI trình bày một schema lỗi ổn định với ví dụ đa ngôn ngữ; SDK có fallback khi gặp code mới.
- [ ] Khi thay nội dung bản dịch, nhóm kiểm tra UX và security, nhưng **không đổi danh tính lỗi**.

## 17. Tài liệu tham khảo

- **RFC 9457 — Problem Details for HTTP APIs**: chuẩn hóa type, title, status, detail, instance và extension members; https://www.rfc-editor.org/rfc/rfc9457.html
- **RFC 9110 — HTTP Semantics**: mã trạng thái, content negotiation, Accept-Language và Content-Language; https://www.rfc-editor.org/rfc/rfc9110.html
- **RFC 4647 — Matching of Language Tags**: các phương pháp matching language tag; https://www.rfc-editor.org/rfc/rfc4647.html
- **RFC 5646 — Tags for Identifying Languages**: cấu trúc language tags/BCP 47; https://www.rfc-editor.org/rfc/rfc5646.html
- **RFC 9111 — HTTP Caching**: cache key, Vary và cache behavior; https://www.rfc-editor.org/rfc/rfc9111.html
- **Spring Framework — MessageSource**: cơ chế tra và định dạng message theo locale; https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- **Spring Framework — Web MVC**: locale resolution, exception handling và ProblemDetail; https://docs.spring.io/spring-framework/reference/web/webmvc.html
- **OpenAPI Specification**: mô tả response, schema, examples và parameters; https://spec.openapis.org/oas/latest.html

**Nguyên tắc cốt lõi:** quốc tế hóa chỉ thay đổi **cách diễn đạt lỗi cho người đọc**, không thay đổi **lỗi đó là gì đối với máy**. Khi giữ nguyên HTTP status, problem type, application error code, schema và dữ liệu có cấu trúc, API có thể phục vụ nhiều ngôn ngữ, đổi wording, nâng cấp giao diện hoặc mở rộng thị trường mà không phá vỡ logic client, kiểm thử, phân tích vận hành và hợp đồng tích hợp.
