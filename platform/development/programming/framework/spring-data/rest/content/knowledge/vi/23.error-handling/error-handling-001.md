# Cơ chế RepositoryRestExceptionHandler và phạm vi xử lý ngoại lệ

Spring Data REST có cơ chế xử lý ngoại lệ dành cho các controller mà framework dùng để export Spring Data repository thành REST resource. Thành phần trung tâm là \`RepositoryRestExceptionHandler\`, một Spring MVC \`@ControllerAdvice\` do Spring Data REST cung cấp.

Điều quan trọng là hiểu đúng phạm vi của handler này. Nó giúp chuyển lỗi phát sinh trong luồng xử lý Spring Data REST thành HTTP response phù hợp. Nó không phải một bộ xử lý ngoại lệ toàn cục cho mọi controller, service, tác vụ nền hay lỗi bảo mật trong toàn bộ ứng dụng.

## 1. RepositoryRestExceptionHandler là gì?

Lớp có tên đầy đủ:

~~~java
org.springframework.data.rest.webmvc.RepositoryRestExceptionHandler
~~~

Spring Data REST đăng ký lớp này như một controller advice. API Javadoc hiện hành thể hiện selector:

~~~java
@ControllerAdvice(basePackageClasses = RepositoryRestExceptionHandler.class)
public class RepositoryRestExceptionHandler {
    // Các phương thức xử lý ngoại lệ của framework.
}
~~~

Hai điểm đáng chú ý:

- Đây là thành phần do Spring Data REST quản lý và cung cấp sẵn. Ứng dụng không cần tự tạo instance hay gọi trực tiếp lớp này.
- \`basePackageClasses\` giới hạn advice theo package chứa lớp được chỉ định. Mục đích của lớp này là xử lý ngoại lệ cho Spring Data REST controllers.

Khi một request đi qua controller của Spring Data REST và phát sinh ngoại lệ thuộc phạm vi xử lý của framework, handler có thể chuyển ngoại lệ thành HTTP status cùng response body phù hợp. Nhờ đó client nhận được lỗi HTTP thay vì phải xử lý exception Java trực tiếp.

Không nên dựa vào chi tiết triển khai nội bộ của lớp framework như một API nghiệp vụ. Nếu ứng dụng cần một mã lỗi hoặc payload ổn định riêng, hãy định nghĩa hợp đồng lỗi ở tầng ứng dụng và bổ sung handler có phạm vi rõ ràng.

## 2. Request đi qua đâu trước khi exception được xử lý?

Một request tới repository resource thường đi qua các bước khái quát:

~~~text
HTTP request
     |
     v
Spring MVC DispatcherServlet
     |
     v
Spring Data REST HandlerMapping
     |
     v
Spring Data REST repository controller
     |
     v
Repository / conversion / validation / persistence
     |
     +---- thành công ----> HTTP response
     |
     +---- exception ----> HandlerExceptionResolver
                              |
                              v
                     RepositoryRestExceptionHandler
                              |
                              v
                     HTTP status + error response
~~~

Sơ đồ cho thấy exception handler là một phần của pipeline xử lý request MVC. Nó không bắt mọi lỗi xuất hiện ở bất kỳ đâu trong JVM.

Ví dụ, nếu một repository REST endpoint cố chuyển chuỗi thành kiểu dữ liệu không hợp lệ, hoặc thao tác lưu gặp lỗi ràng buộc dữ liệu, ngoại lệ có thể được xử lý trong pipeline Spring Data REST. Ngược lại, lỗi phát sinh trong một scheduled job không có HTTP request thì không có HTTP response để handler này chuyển đổi.

## 3. Phạm vi xử lý: Spring Data REST controllers

API Javadoc mô tả \`RepositoryRestExceptionHandler\` là exception handler cho Spring Data REST controllers. Phạm vi này gắn với controller và request mapping thuộc Spring Data REST.

Các trường hợp điển hình nằm trong phạm vi:

- Request tới collection resource được export từ repository.
- Request tới item resource như GET, PUT, PATCH hoặc DELETE.
- Request tới finder/search resource được export.
- Request tới association resource do Spring Data REST quản lý.
- Custom endpoint được tích hợp vào Spring Data REST bằng \`@RepositoryRestController\`.

Không nên hiểu phạm vi này là “mọi code dùng Spring Data repository”. Việc một service gọi cùng một repository interface không tự biến lời gọi đó thành request của Spring Data REST.

## 4. Phân biệt @RepositoryRestController và @RestController

Đây là ranh giới rất quan trọng khi thêm endpoint tùy chỉnh.

### @RepositoryRestController

Dùng \`@RepositoryRestController\` khi endpoint tùy chỉnh cần tham gia môi trường Spring Data REST. Controller được phục vụ dưới API base path đã cấu hình trong \`RepositoryRestConfiguration.setBasePath\` và có thể tận dụng cấu hình, message converters, exception handling cùng các tích hợp của Spring Data REST.

~~~java
@RepositoryRestController
class ProductOperationsController {

    private final ProductRepository repository;

    ProductOperationsController(ProductRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/products/search/active")
    ResponseEntity<?> findActiveProducts() {
        return ResponseEntity.ok(repository.findByActiveTrue());
    }
}
~~~

Ví dụ minh họa endpoint tùy chỉnh đặt trong URI space của Spring Data REST. Khi cần trả representation theo HAL, hãy dùng các kiểu Spring HATEOAS phù hợp như \`EntityModel\` hoặc \`CollectionModel\`, đồng thời tạo link theo cấu hình của API.

### @RestController

Controller Spring MVC thông thường:

~~~java
@RestController
@RequestMapping("/internal/reports")
class ReportController {

    @GetMapping
    List<ReportDto> getReports() {
        // Xử lý endpoint MVC thông thường.
        return List.of();
    }
}
~~~

Nếu dùng \`@Controller\` hoặc \`@RestController\` thông thường cho endpoint ứng dụng, endpoint đó nằm ngoài phạm vi tích hợp của Spring Data REST, bao gồm request handling, message converters và exception handling của framework.

Endpoint này vẫn có thể được xử lý bởi cơ chế exception handling thông thường của Spring MVC, chẳng hạn \`@ExceptionHandler\` trong controller hoặc \`@ControllerAdvice\` / \`@RestControllerAdvice\` do ứng dụng định nghĩa. Chỉ cần không mặc định rằng nó sẽ nhận cùng hành vi của \`RepositoryRestExceptionHandler\`.

| Loại endpoint | Cơ chế phù hợp |
|---|---|
| Repository resource được export tự động | Spring Data REST controller và \`RepositoryRestExceptionHandler\` |
| Custom endpoint cần tích hợp Spring Data REST | \`@RepositoryRestController\` |
| Endpoint MVC thông thường | \`@RestController\` / \`@Controller\` và exception advice của ứng dụng |
| Service được gọi trực tiếp | Xử lý exception ở caller hoặc tầng nghiệp vụ |
| Scheduled job / message consumer | Cơ chế xử lý lỗi của tác vụ nền |
| Authentication / authorization trong security filter chain | Cấu hình Spring Security như \`AuthenticationEntryPoint\` và \`AccessDeniedHandler\` |

## 5. Các lỗi thường gặp trong repository REST

Handler mặc định của framework xử lý các exception phù hợp với luồng Spring Data REST và ánh xạ chúng sang HTTP response. Tùy loại lỗi và phiên bản Spring Data REST, status và body cụ thể có thể khác nhau.

Các nhóm lỗi thường cần phân tích gồm:

| Nhóm lỗi | Ví dụ | Ý nghĩa HTTP thường gặp |
|---|---|---|
| Không tìm thấy tài nguyên | Item URI không tồn tại | 404 Not Found |
| Request không hợp lệ | JSON sai cú pháp, kiểu dữ liệu không chuyển đổi được | 400 Bad Request |
| Method không được hỗ trợ | Gọi method HTTP không được endpoint hỗ trợ | 405 Method Not Allowed |
| Media type không hỗ trợ | Content-Type hoặc Accept không phù hợp | 415 Unsupported Media Type hoặc 406 Not Acceptable tùy tình huống |
| Vi phạm ràng buộc dữ liệu | Unique constraint hoặc foreign key constraint | Có thể là 409 Conflict hoặc status khác tùy mapping |
| Xung đột cập nhật | Optimistic locking failure | Thường biểu diễn xung đột, nhưng cần kiểm tra mapping của phiên bản |
| Lỗi ngoài dự kiến | Null pointer hoặc lỗi lập trình | Thường là 500 Internal Server Error |

Bảng trên là định hướng phân loại lỗi HTTP, không phải cam kết rằng mọi exception class đều luôn ánh xạ một-một tới status được liệt kê. Hãy kiểm thử mapping thực tế trong phiên bản Spring Data REST mà ứng dụng đang dùng.

Một số lỗi còn được xử lý ở tầng khác trước khi tới controller advice:

- Lỗi xác thực request hoặc chuyển đổi dữ liệu có thể phát sinh trong quá trình bind body/parameter.
- Lỗi validation có thể được phát hiện qua validator và cơ chế validation của Spring Data REST.
- Lỗi xác thực người dùng và phân quyền có thể bị chặn trong Spring Security filter chain trước khi controller chạy.
- Lỗi trong serialization response có thể xảy ra sau khi logic controller đã hoàn tất.

Do đó, khi một lỗi không đi vào \`RepositoryRestExceptionHandler\`, hãy kiểm tra request mapping, filter chain, binding, validation và serialization trước khi kết luận handler bị lỗi.

## 6. Thêm exception handler riêng cho nghiệp vụ

Ứng dụng thường cần trả mã lỗi ổn định cho các tình huống domain cụ thể, ví dụ mã sản phẩm đã tồn tại hoặc trạng thái đơn hàng không cho phép chuyển tiếp.

Có thể định nghĩa exception riêng:

~~~java
public class DuplicateProductCodeException extends RuntimeException {

    public DuplicateProductCodeException(String code) {
        super("Product code already exists: " + code);
    }
}
~~~

Sau đó định nghĩa response lỗi của ứng dụng:

~~~java
public record ApiError(
        String code,
        String message
) {}
~~~

Và đăng ký advice giới hạn vào custom Spring Data REST controller:

~~~java
@RestControllerAdvice(annotations = RepositoryRestController.class)
public class RepositoryApiExceptionHandler {

    @ExceptionHandler(DuplicateProductCodeException.class)
    public ResponseEntity<ApiError> handleDuplicateCode(
            DuplicateProductCodeException exception) {

        ApiError body = new ApiError(
                "PRODUCT_CODE_DUPLICATE",
                "Mã sản phẩm đã tồn tại."
        );

        return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
    }
}
~~~

Ví dụ trên minh họa cách giới hạn custom advice theo controller có annotation \`@RepositoryRestController\`. Nếu muốn giới hạn theo package, có thể dùng \`basePackageClasses\` với một marker class thuộc package chứa các controller cần xử lý:

~~~java
@RestControllerAdvice(basePackageClasses = RepositoryApiMarker.class)
public class RepositoryApiExceptionHandler {
    // Các @ExceptionHandler của ứng dụng.
}
~~~

Chọn selector dựa trên phạm vi thật sự cần áp dụng. Một advice không có selector có thể áp dụng rộng hơn dự kiến tới nhiều controller trong ứng dụng.

### Có nên ghi đè RepositoryRestExceptionHandler?

Thông thường không cần tự tạo lại hoặc subclass lớp nội bộ của framework. Hãy bổ sung một \`@ControllerAdvice\` / \`@RestControllerAdvice\` cho exception nghiệp vụ của ứng dụng.

Khi nhiều advice cùng có thể xử lý một exception, thứ tự ưu tiên và mức độ cụ thể của handler có ảnh hưởng đến kết quả. Có thể dùng \`@Order\` khi cần xác định thứ tự giữa các advice, nhưng nên tránh các handler tổng quát bắt mọi \`Exception\` với phạm vi chồng lấn.

Một số nguyên tắc:

- Chỉ bắt exception mà handler thực sự chịu trách nhiệm.
- Ưu tiên xử lý exception domain cụ thể trước exception tổng quát.
- Không trả HTTP 200 cho một request thất bại.
- Không làm lộ stack trace, SQL, tên bảng, token hoặc dữ liệu nhạy cảm trong response.
- Giữ response contract ổn định với \`code\` máy đọc được và \`message\` an toàn cho client.
- Ghi log ở server với correlation/request ID để điều tra chi tiết.

## 7. Phân biệt HTTP exception handling với transaction rollback

Một điểm dễ hiểu nhầm là handler chuyển exception thành HTTP response không có nghĩa nó quyết định database commit hay rollback.

Hai cơ chế có nhiệm vụ khác nhau:

- Exception handler quyết định cách exception được biểu diễn thành HTTP status và response body.
- Transaction manager quyết định commit hoặc rollback dựa trên transaction boundary, exception type, rollback rules và propagation.

Ví dụ, một service đã commit transaction rồi mới phát sinh lỗi khi serialize response. Handler có thể trả HTTP 500, nhưng dữ liệu đã commit không tự động được khôi phục.

Tương tự, nếu custom exception handler bắt exception rồi trả response thành công, transaction có thể không nhận được tín hiệu lỗi để rollback. Không nên dùng việc đổi status trong controller advice như một cơ chế điều khiển transaction.

Khi cần đảm bảo transaction thất bại nếu nghiệp vụ không hợp lệ, hãy để exception phù hợp truyền ra khỏi transactional boundary hoặc cấu hình rollback rule có chủ đích. Kiểm thử cả HTTP response lẫn dữ liệu sau request.

## 8. Phân biệt lỗi HTTP với lỗi Security

Spring Security thường xử lý authentication và authorization trong filter chain trước khi request đến controller.

Hai loại lỗi phổ biến:

- 401 Unauthorized: request chưa có thông tin xác thực hợp lệ hoặc chưa được xác thực theo yêu cầu.
- 403 Forbidden: người dùng đã được xác thực nhưng không có quyền thực hiện thao tác.

Các response này thường được cấu hình qua \`AuthenticationEntryPoint\` và \`AccessDeniedHandler\`, tùy cách cấu hình security. Không nên cố xử lý mọi lỗi 401/403 bằng \`RepositoryRestExceptionHandler\`, vì request có thể chưa đến MVC controller advice.

Nếu muốn định dạng error body đồng nhất giữa lỗi repository REST và lỗi security, hãy cấu hình hai pipeline trả về cùng schema ở mức hợp đồng API, nhưng vẫn giữ đúng trách nhiệm của từng pipeline.

## 9. Kiểm thử phạm vi và mapping của exception handler

Cách đáng tin cậy nhất là kiểm thử qua HTTP endpoint thực tế bằng Spring MVC test, chẳng hạn MockMvc.

Ví dụ kiểm tra exception nghiệp vụ trên custom repository REST controller:

~~~java
mockMvc.perform(
        post("/api/products/search/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"code":"P-001"}
                    """)
)
.andExpect(status().isConflict())
.andExpect(jsonPath("$.code").value("PRODUCT_CODE_DUPLICATE"));
~~~

Đường dẫn và payload trong ví dụ cần điều chỉnh theo mapping thật của ứng dụng.

Bộ test nên bao gồm:

1. Repository resource tự động: gây lỗi không tìm thấy entity và xác nhận HTTP 404.
2. Repository resource: gửi JSON không hợp lệ và xác nhận lỗi binding được biểu diễn đúng.
3. Ràng buộc database: gây vi phạm constraint và kiểm tra status/body thực tế.
4. Custom \`@RepositoryRestController\`: ném exception domain và xác nhận custom advice bắt đúng.
5. MVC \`@RestController\` thông thường: xác nhận handler MVC của ứng dụng được sử dụng theo phạm vi đã thiết kế.
6. Security filter chain: xác nhận lỗi 401/403 được xử lý bởi security handler.
7. Transaction: sau response lỗi, đọc lại dữ liệu để xác nhận commit/rollback theo yêu cầu.
8. Nhiều controller advice: xác nhận đúng handler được chọn khi exception có thể khớp nhiều advice.

Không chỉ kiểm tra status code. Hãy xác nhận Content-Type, error code, message an toàn, và trạng thái dữ liệu sau request. Điều này giúp phát hiện trường hợp HTTP response báo lỗi nhưng dữ liệu đã được ghi, hoặc response báo thành công trong khi nghiệp vụ chưa hoàn tất.

## 10. Checklist lựa chọn đúng cơ chế

- [ ] Request có thực sự đi qua Spring Data REST repository controller không?
- [ ] Endpoint tùy chỉnh đã dùng \`@RepositoryRestController\` nếu cần tích hợp với Spring Data REST chưa?
- [ ] Nếu là MVC controller thông thường, đã có \`@ControllerAdvice\` / \`@RestControllerAdvice\` phù hợp chưa?
- [ ] Lỗi có xảy ra trong Security filter chain trước khi vào MVC không?
- [ ] Exception domain đã được ánh xạ thành status và error code rõ ràng chưa?
- [ ] Advice có selector giới hạn đúng package/controller không?
- [ ] Có nhiều advice cùng bắt exception không, và thứ tự đã được kiểm thử chưa?
- [ ] Response có vô tình để lộ chi tiết nội bộ không?
- [ ] Transaction rollback đã được xác minh độc lập với HTTP status chưa?
- [ ] Integration test đã bao phủ cả repository resource tự động và custom endpoint chưa?

## 11. Kết luận về phạm vi

\`RepositoryRestExceptionHandler\` là cơ chế xử lý ngoại lệ dành cho Spring Data REST controllers. Nó giúp chuyển lỗi của luồng repository REST thành HTTP response. Custom endpoint dùng \`@RepositoryRestController\` có thể tận dụng môi trường Spring Data REST, trong khi \`@Controller\` / \`@RestController\` thông thường thuộc phạm vi xử lý MVC của ứng dụng.

Muốn API có error contract riêng, hãy thêm controller advice với selector rõ ràng và exception domain cụ thể. Muốn xử lý lỗi bảo mật, tác vụ nền hoặc transaction, hãy dùng cơ chế tương ứng của từng tầng. Kiểm thử qua HTTP và xác nhận dữ liệu sau request để bảo đảm phạm vi xử lý lỗi đúng với thiết kế.

## Tài liệu tham khảo

- Spring Data REST API — RepositoryRestExceptionHandler: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/RepositoryRestExceptionHandler.html
- Spring Data REST Reference — Overriding Spring Data REST Response Handlers: https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html
- Spring Framework Reference — Error Responses and @ControllerAdvice: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html

