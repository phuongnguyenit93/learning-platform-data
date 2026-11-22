# Định dạng lỗi validation, lỗi liên kết và ngoại lệ nghiệp vụ trong Spring Data REST

> Phạm vi: Spring Data REST chạy trên Spring MVC. Tên lớp và API được đối chiếu với tài liệu Spring Data REST 5.1. Hãy kiểm tra lại response bằng integration test trên đúng Spring Boot, Spring Data REST và Spring Framework BOM của dự án, vì handler và media type có thể khác giữa các major version.

## 1. Mô hình phản hồi lỗi

Một response lỗi cần có hai phần ổn định: HTTP status để client quyết định cách xử lý, và body để client hiển thị hoặc ghi nhận lỗi. Spring Data REST đăng ký `RepositoryRestExceptionHandler` cho các controller của REST exporter. Với lỗi tổng quát, `ExceptionMessage` chuyển exception thành JSON-friendly object. Theo Javadoc hiện tại, phần được serialize là message của exception ngoài cùng; cause chain chỉ dành cho xử lý phía server và không được serialize ra JSON.

Các dạng lỗi thường gặp:

| Tình huống | HTTP status nên/được dùng | Body hoặc dấu hiệu cần kiểm tra |
| --- | --- | --- |
| Spring `Validator` báo lỗi ở repository event | `400 Bad Request` | `errors` là danh sách lỗi; mỗi phần tử có `entity`, `property`, `invalidValue`, `message` |
| Jakarta Bean Validation ném `ConstraintViolationException` | Thường là `400 Bad Request`; xác nhận handler của phiên bản đang chạy | Helper `ConstraintViolationExceptionMessage` có `cause` và `messages`; mỗi message có entity, property, invalidValue, message |
| JSON không đọc/parse được hoặc kiểu dữ liệu không hợp lệ | `400 Bad Request` | Thường là `{"message":"..."}` từ `ExceptionMessage`; không dùng body này để phân tích lỗi field |
| Tài nguyên hoặc đường dẫn quan hệ không tồn tại | `404 Not Found` | `ResourceNotFoundException` được gắn `@ResponseStatus(NOT_FOUND)`; body phụ thuộc handler |
| Một association chỉ nhận một URI nhưng client gửi nhiều URI | `400 Bad Request` | Tài liệu Spring Data REST quy định rõ lỗi này cho `PUT` association dạng to-one |
| Trạng thái nghiệp vụ xung đột hoặc cập nhật đồng thời | `409 Conflict` | Dùng mã lỗi nghiệp vụ ổn định; kiểm tra handler ánh xạ exception của ứng dụng |
| HTTP method hoặc media type không được hỗ trợ | `405 Method Not Allowed` hoặc `415 Unsupported Media Type` | Kiểm tra method và `Content-Type` mà endpoint công bố |

Bảng trên là hướng dẫn phân loại, không phải cam kết mọi exception của ứng dụng tự động có cùng mapping. Với exception nghiệp vụ tùy chỉnh, hãy khai báo mapping tường minh và khóa hành vi bằng test.

## 2. Validation trên repository resource

### 2.1. Đăng ký Spring Validator theo event

Spring Data REST gọi validator thông qua `ValidatingRepositoryEventListener`. Cách đơn giản nhất là đặt tên bean theo mẫu `<event><DomainType>Validator`. Ví dụ `beforeCreatePersonValidator` chạy trước khi tạo `Person`; dùng `beforeSavePersonValidator` nếu cần kiểm tra cả thao tác cập nhật.

```java
import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component("beforeCreatePersonValidator")
public class BeforeCreatePersonValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return Person.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Person person = (Person) target;

        if (person.getEmail() == null || !person.getEmail().contains("@")) {
            errors.rejectValue("email", "email.invalid", "Email không hợp lệ");
        }
    }
}
```

Khi cần gắn validator thủ công, triển khai `RepositoryRestConfigurer` và thêm validator vào đúng event:

```java
@Configuration
public class RestValidationConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureValidatingRepositoryEventListener(
            ValidatingRepositoryEventListener listener) {
        listener.addValidator("beforeSave", new BeforeSavePersonValidator());
    }
}
```

Các event thường dùng gồm `beforeCreate`, `beforeSave`, `beforeLinkSave` và `beforeDelete`. Chọn event đúng với thao tác cần bảo vệ. Validator phải trả về `true` trong `supports` cho đúng domain type; nếu không, Spring Data REST sẽ không áp dụng validator đó.

### 2.2. Cấu trúc lỗi validation

Khi Spring `Validator` thêm lỗi vào `Errors`, Spring Data REST ném `RepositoryConstraintViolationException`. API hiện tại cung cấp `RepositoryConstraintViolationExceptionMessage` và nested `ValidationError`; các field có thể được client dùng để đánh dấu field sai:

```json
{
  "errors": [
    {
      "entity": "Person",
      "property": "email",
      "invalidValue": "email-sai",
      "message": "Email không hợp lệ"
    }
  ]
}
```

Đây là ví dụ minh họa cấu trúc, không phải chuỗi message cố định. `entity`, tên property và message phụ thuộc domain model, validator và `MessageSource`. Với lỗi toàn object được tạo bằng `errors.reject(...)`, property có thể không có giá trị.

Spring Data REST cũng có helper riêng cho `jakarta.validation.ConstraintViolationException`: `ConstraintViolationExceptionMessage` cung cấp `cause` và danh sách `messages`; mỗi `ConstraintViolationMessage` có `entity`, `property`, `invalidValue` và `message`. Nếu dự án dùng Spring Data REST cũ, namespace validation có thể là `javax.validation` thay vì `jakarta.validation`; dùng đúng namespace theo dependency đang quản lý.

Không nên đưa giá trị nhạy cảm như mật khẩu, token hoặc dữ liệu cá nhân vào response lỗi. Vì payload validation có thể chứa `invalidValue`, hãy kiểm tra field nào được phản hồi ra ngoài và dùng DTO/handler tùy chỉnh nếu cần che giá trị.

## 3. Lỗi liên kết association và URI tham chiếu

### 3.1. Dùng link và đúng media type

Spring Data REST biểu diễn quan hệ bằng link HAL trong `_links`. Client nên bắt đầu từ root resource, đọc relation được công bố rồi theo link đó; không tự ghép URL theo giả định về tên repository hoặc association. Đường dẫn còn có thể chịu ảnh hưởng của `spring.data.rest.base-path` và `@RestResource`.

Association resource có các thao tác chính:

- `GET` đọc trạng thái association.
- `PUT` gắn resource được chỉ ra bởi URI vào association; request body dùng `text/uri-list`.
- `POST` thêm phần tử vào association dạng collection; request body cũng dùng `text/uri-list`.
- `DELETE` gỡ liên kết nếu association cho phép thao tác đó.

Ví dụ gắn một địa chỉ vào quan hệ to-one `address` của người dùng:

```bash
curl -i -X PUT "http://localhost:8080/people/1/address" \
  -H "Content-Type: text/uri-list" \
  --data-binary "http://localhost:8080/addresses/42"
```

Với association to-one, body phải chứa đúng một URI. Gửi nhiều URI cho một quan hệ to-one sẽ nhận `400 Bad Request`. Với association collection, dùng `POST` để thêm một phần tử; dùng `PUT` khi cần gửi tập URI muốn gắn theo semantics của endpoint.

### 3.2. Phân biệt lỗi URI và lỗi association

Khi nhận lỗi liên kết, kiểm tra theo thứ tự:

1. URI có đúng host, scheme, base path và path segment được API công bố không.
2. Resource cha có tồn tại không; ID có đúng kiểu và đúng cách chuyển đổi của repository không.
3. Relation có xuất hiện trong `_links` của resource cha không; tên relation có bị đổi bởi `@RestResource` không.
4. URI đích có trỏ đến item resource được export không và item đó có tồn tại không.
5. Request có dùng `Content-Type: text/uri-list` cho association `PUT`/`POST` không; body có một URI trên mỗi dòng không.

`ResourceNotFoundException` của Spring Data REST được đánh dấu `404 Not Found`. Status này phù hợp khi server xác định resource hoặc route association không tồn tại. Không nên mặc định mọi URI sai đều trả cùng một body: lỗi parse URI, sai media type, sai cardinality và không tìm thấy resource có thể đi qua các handler khác nhau. Hãy tái hiện từng trường hợp bằng MockMvc trên đúng phiên bản dự án.

## 4. Ngoại lệ nghiệp vụ và chuẩn hóa response

### 4.1. Chọn status theo ý nghĩa nghiệp vụ

- Dữ liệu request vi phạm quy tắc field hoặc invariant có thể kiểm tra trước khi lưu: trả `400` cùng lỗi field qua `Validator`.
- Resource không tồn tại: trả `404`.
- Lệnh hợp lệ về cú pháp nhưng không thể thực hiện ở trạng thái hiện tại, hoặc có xung đột cập nhật: trả `409`.
- Người gọi không có quyền thực hiện: trả `403`.
- Lỗi ngoài dự kiến: trả `500`, log đầy đủ ở server và không đưa stack trace/SQL ra client.

Đừng dùng `500` cho một điều kiện nghiệp vụ mà client có thể xử lý. Cũng đừng chuyển mọi `DataIntegrityViolationException` thành `400` một cách máy móc: cần phân biệt lỗi input có thể sửa với xung đột dữ liệu hoặc trạng thái đã thay đổi.

### 4.2. Dùng ProblemDetail cho endpoint tùy chỉnh

Từ Spring Framework 6 trở lên, có thể trả `ProblemDetail` theo Problem Details for HTTP APIs; Spring Framework hiện tại hỗ trợ RFC 9457. `ProblemDetail` có các trường chuẩn như `type`, `title`, `status`, `detail`, `instance`; có thể thêm extension property như `code` để client xử lý theo mã ổn định. Với Spring Framework cũ hơn, dùng DTO lỗi riêng có các field tương đương.

Khi viết endpoint tùy chỉnh nằm trong URI space của Spring Data REST, dùng `@RepositoryRestController`. Annotation này cho phép endpoint dùng base path, message converters và exception handling của Spring Data REST. Controller `@RestController` thông thường nằm ngoài phạm vi tích hợp đó.

```java
@RepositoryRestController
public class OrderCommandController {

    private final OrderService orderService;

    public OrderCommandController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping("/orders/{id}/confirm")
    public ResponseEntity<Void> confirm(@PathVariable Long id) {
        orderService.confirm(id);
        return ResponseEntity.noContent().build();
    }

    @ExceptionHandler(OrderCannotBeConfirmedException.class)
    public ResponseEntity<ProblemDetail> handleCannotConfirm(
            OrderCannotBeConfirmedException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "Đơn hàng không ở trạng thái cho phép xác nhận.");
        problem.setTitle("Không thể xác nhận đơn hàng");
        problem.setProperty("code", "ORDER_NOT_CONFIRMABLE");

        return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
    }
}
```

`@ExceptionHandler` đặt trong controller trên xử lý exception phát sinh từ handler method của controller đó. Nếu exception phát sinh trong luồng của repository endpoint mặc định, chẳng hạn từ repository event handler, hãy kiểm tra thứ tự và phạm vi của `@ControllerAdvice` so với `RepositoryRestExceptionHandler`; không giả định advice của một controller khác sẽ thắng. Dùng integration test để xác nhận mapping thực tế.

Response minh họa cho lệnh không hợp lệ ở trạng thái hiện tại:

```json
{
  "type": "about:blank",
  "title": "Không thể xác nhận đơn hàng",
  "status": 409,
  "detail": "Đơn hàng không ở trạng thái cho phép xác nhận.",
  "code": "ORDER_NOT_CONFIRMABLE"
}
```

Giữ `code` ổn định qua các lần đổi câu chữ hoặc ngôn ngữ. `detail` dành cho người đọc; client nên rẽ nhánh theo HTTP status và `code`, không parse message. Không trả `exception.getMessage()` nếu message có thể chứa SQL, tên bảng, dữ liệu nhạy cảm hoặc thông tin nội bộ.

## 5. Kiểm thử hợp đồng lỗi bằng MockMvc

Kiểm thử HTTP thực tế thay vì chỉ gọi validator hoặc service trực tiếp. Ví dụ khung test dưới đây giả định ứng dụng đã export `PersonRepository`, association `address` là to-one và custom endpoint xác nhận đơn hàng đã được đăng ký:

```java
@SpringBootTest
@AutoConfigureMockMvc
class SpringDataRestErrorTest {

    @Autowired MockMvc mockMvc;
    @Autowired ObjectMapper objectMapper;

    @Test
    void invalidPersonReturnsFieldErrors() throws Exception {
        Person invalid = new Person("An", "email-sai");

        mockMvc.perform(post("/people")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(invalid)))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].property").value("email"))
            .andExpect(jsonPath("$.errors[0].message").exists());
    }

    @Test
    void toOneAssociationRejectsMultipleUris() throws Exception {
        // Fixture phải tạo trước person 1 và hai address được tham chiếu.
        mockMvc.perform(put("/people/1/address")
                .contentType(MediaType.parseMediaType("text/uri-list"))
                .content("http://localhost:8080/addresses/10\\nhttp://localhost:8080/addresses/11"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void missingPersonReturnsNotFound() throws Exception {
        mockMvc.perform(get("/people/999999"))
            .andExpect(status().isNotFound());
    }

    @Test
    void businessConflictReturnsProblemDetail() throws Exception {
        mockMvc.perform(post("/orders/1/confirm"))
            .andExpect(status().isConflict())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.status").value(409))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_CONFIRMABLE"));
    }
}
```

Bổ sung fixture cho repository và service theo cấu trúc test của dự án. Nếu `base-path` được cấu hình, thêm prefix đó vào URL. Khi kiểm thử response validation, chỉ assert các field hợp đồng cần thiết; tránh khóa test vào câu chữ message mặc định có thể được dịch qua `MessageSource`.

Checklist cho mỗi test:

- Assert chính xác status code, không chỉ `is4xxClientError()`.
- Assert `Content-Type` và các field JSON mà client thực sự sử dụng.
- Với association, kiểm tra cả đúng media type, cardinality và URI đích.
- Với lỗi nghiệp vụ, assert `code` ổn định và status tương ứng.
- Xác nhận request thất bại không ghi hoặc thay đổi dữ liệu.
- Xác nhận response không chứa stack trace, SQL, tên class nội bộ hoặc dữ liệu nhạy cảm.

## 6. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| POST/PUT trả `400` nhưng chỉ có `message`, không có `errors` | JSON parse/type conversion thất bại trước khi validator chạy, hoặc validator chưa được đăng ký | Kiểm tra request JSON, bean name, component scan, `supports` và event `beforeCreate`/`beforeSave` |
| Validator chạy khi tạo nhưng không chạy khi sửa | Chỉ đăng ký `beforeCreate` | Đăng ký thêm `beforeSave` nếu quy tắc cũng áp dụng cho update |
| Association trả `404` | Sai base path, relation, item ID hoặc resource chưa được export/tồn tại | Đọc `_links` từ root và resource cha; xác minh URI đích |
| Association trả `400` | Body không đúng định dạng hoặc gửi nhiều URI cho association to-one | Dùng `text/uri-list`; gửi đúng một URI cho to-one |
| Association trả `415` | `Content-Type` không được endpoint hỗ trợ | Dùng `text/uri-list` cho association `PUT`/`POST` |
| Ngoại lệ nghiệp vụ thành `500` | Chưa có handler phù hợp hoặc exception phát sinh trong luồng repository mặc định | Phân loại exception, thêm mapping phù hợp và kiểm tra thứ tự `@ControllerAdvice` bằng MockMvc |
| Response lộ thông tin database | Message của exception ngoài cùng chứa chi tiết nội bộ | Tạo message an toàn, log cause ở server và trả `code` công khai |

Khi debug, ghi log correlation/request ID, exception type và stack trace ở server. Client chỉ cần status, error code và detail đã được làm sạch. Không bật hiển thị stack trace trong response production để tìm nguyên nhân.

## 7. Tài liệu tham khảo chính thức

- [Spring Data REST — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html): đăng ký validator theo bean name và `RepositoryRestConfigurer`.
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): HTTP method, media type và status code của collection, item và association resource.
- [Spring Data REST — Overriding response handlers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html): dùng `@RepositoryRestController`, base path và tích hợp exception handling.
- [RepositoryRestExceptionHandler Javadoc](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/RepositoryRestExceptionHandler.html): handler cho controller của Spring Data REST.
- [RepositoryConstraintViolationException Javadoc](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/RepositoryConstraintViolationException.html): exception được ném khi Spring `Validator` báo lỗi.
- [RepositoryConstraintViolationExceptionMessage.ValidationError Javadoc](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/support/RepositoryConstraintViolationExceptionMessage.ValidationError.html): field của từng validation error.
- [ConstraintViolationExceptionMessage Javadoc](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/support/ConstraintViolationExceptionMessage.html): cấu trúc `cause` và `messages` cho Jakarta validation exception.
- [ResourceNotFoundException Javadoc](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/ResourceNotFoundException.html): mapping `NOT_FOUND`.
- [ExceptionMessage Javadoc](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/support/ExceptionMessage.html): cách serialize exception message và loại bỏ cause chain khỏi JSON.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse`, RFC 9457, `ResponseEntityExceptionHandler` và tùy biến message.