# Phân biệt bind thành công với dữ liệu đạt yêu cầu nghiệp vụ trong Spring MVC

Một HTTP request được chuyển thành đối tượng Java mà không báo lỗi **chưa đủ** để khẳng định yêu cầu có thể được thực hiện. Trong Spring MVC, cần tách ba câu hỏi: *hệ thống đã đọc và chuyển dữ liệu được chưa?*; *giá trị có đáp ứng các ràng buộc khai báo không?*; và *thao tác có được phép theo quy tắc nghiệp vụ, trạng thái hiện tại hay không?*

Ví dụ, API nhận yêu cầu đặt 5 chỗ. Số 5 hoàn toàn chuyển được thành **Integer**, cũng đáp ứng ràng buộc **@Min(1)**, nhưng phải bị từ chối nếu sự kiện chỉ còn 3 chỗ. Đây là trường hợp **binding thành công, validation kiểu dữ liệu thành công, nghiệp vụ không chấp nhận**.

## 1. Ba tầng kiểm tra có mục đích khác nhau

| Tầng | Câu hỏi | Ví dụ lỗi | Thành phần thường phụ trách |
| --- | --- | --- | --- |
| **Binding / deserialization** | Dữ liệu HTTP có đọc được và ánh xạ sang kiểu/thuộc tính Java không? | **seats=abc** không đổi được sang số; JSON sai cú pháp | **WebDataBinder**, **ConversionService** cho form; **HttpMessageConverter** (thường Jackson) cho JSON |
| **Input/Bean Validation** | Sau khi tạo đối tượng, giá trị có thỏa điều kiện khai báo của yêu cầu không? | **seats=0** vi phạm **@Min(1)**; **customer** toàn khoảng trắng vi phạm **@NotBlank** | **jakarta.validation**, **@Valid**, **@Validated**, **Validator** |
| **Business validation / domain invariant** | Với tài khoản, tài nguyên và trạng thái hiện tại, thao tác có hợp lệ không? | Đặt 5 chỗ khi chỉ còn 3; đăng ký trùng mã; chuyển trạng thái không được phép | Service, domain model, policy, repository và ràng buộc nhất quán trong DB |

**Phân biệt quan trọng:**

- **Bind thành công** chỉ nói rằng bước ánh xạ được thực hiện theo cấu hình hiện có. Nó không đảm bảo mọi trường mà client gửi đều được sử dụng, mọi trường bắt buộc đều hiện diện, hay giá trị có ý nghĩa nghiệp vụ.
- **Bean Validation thành công** nói rằng **những constraint đã khai báo và thực sự được kích hoạt** đều đạt. Nó không tự biết tồn kho, quyền sở hữu, hạn mức đang dùng hoặc trạng thái giao dịch trong database.
- **Nghiệp vụ thành công** còn cần kiểm tra quy tắc theo ngữ cảnh và thường cần bảo đảm tính nguyên tử khi cập nhật dữ liệu. Ngay cả khi đã qua service, thao tác ghi vẫn có thể thất bại do cạnh tranh đồng thời hoặc ràng buộc cơ sở dữ liệu.

Không nên gọi chung ba tầng là “validate dữ liệu” rồi suy ra một tầng đã thay thế cho tầng khác.

## 2. Luồng xử lý request: lỗi có thể xảy ra ở đâu?

Luồng điển hình khi xử lý một POST trong Spring MVC:

~~~text
HTTP request
   |
   +-- Đọc tham số form / đọc JSON body
   |       |
   |       +-- Không đọc/chuyển kiểu được --> lỗi binding/deserialize
   |       |
   |       +-- Tạo/điền được object Java
   |                    |
   |                    +-- @Valid / @Validated / Spring Validator
   |                    |       |
   |                    |       +-- Sai constraint --> lỗi input validation
   |                    |
   |                    +-- Service / domain
   |                            |
   |                            +-- Vi phạm quy tắc/ngữ cảnh --> lỗi nghiệp vụ
   |                            |
   |                            +-- Transaction / cập nhật DB
   |                                    |
   |                                    +-- Xung đột/ràng buộc DB --> xử lý nhất quán
   |                                    |
   |                                    +-- Thành công --> response thành công
~~~

Đây là luồng logic, không phải cam kết rằng mọi ứng dụng dùng đúng một exception hay một HTTP status. Cơ chế xử lý khác nhau giữa **@ModelAttribute** và **@RequestBody**, giữa việc có hoặc không có **BindingResult**, giữa ràng buộc trên object và method validation.

### Form data: @ModelAttribute

Ví dụ form gửi **seats=abc** vào thuộc tính **Integer seats**. Spring sử dụng cơ chế binding/conversion và có thể ghi lỗi **typeMismatch** vào **BindingResult**. Nếu controller khai báo **BindingResult** ngay sau đối tượng **@ModelAttribute**, nó có thể đọc lỗi và trả lại màn hình nhập liệu. Nếu thêm **@Valid**, các lỗi constraint cũng có thể được tập hợp trong cùng **BindingResult**.

Vì vậy, **bindingResult.hasErrors()** có nghĩa là “có lỗi trong kết quả binding/validation”, **không có nghĩa mọi lỗi đều do binding**. Khi cần phân biệt, kiểm tra **FieldError.isBindingFailure()** đối với lỗi ở field:

~~~java
// Đoạn minh họa bên trong một @Controller;
// Form, registrationService và view "registration-form" là thành phần của ứng dụng.
@PostMapping("/registrations/form")
public String submit(
        @Valid @ModelAttribute("form") Form form,
        BindingResult result) {

    if (result.hasErrors()) {
        boolean hasConversionError = result.getFieldErrors().stream()
                .anyMatch(FieldError::isBindingFailure);
        // hasConversionError giúp chẩn đoán nhóm lỗi;
        // result còn có thể chứa lỗi @NotNull, @Min, @NotBlank...
        return "registration-form";
    }

    registrationService.register(form); // vẫn cần kiểm tra nghiệp vụ
    return "redirect:/registrations/success";
}
~~~

Với đoạn minh họa trên, phải import **org.springframework.validation.BindingResult**, **org.springframework.validation.FieldError**, **jakarta.validation.Valid**, **org.springframework.web.bind.annotation.ModelAttribute** và **PostMapping** trong controller thực tế. Không đặt tham số khác xen giữa **form** và **BindingResult**. Một số giá trị không có trong request có thể giữ **null** hoặc giá trị mặc định; binder cũng có thể bỏ qua/suppress trường không cho bind. Vì vậy cần thiết kế request DTO rõ ràng, khai báo constraint phù hợp và xem **getSuppressedFields()** nếu có chính sách allowed fields.

### JSON: @RequestBody

Với JSON, **HttpMessageConverter** phải deserialize body trước khi Bean Validation diễn ra. JSON sai cú pháp hoặc giá trị không chuyển được sang kiểu trường có thể làm phát sinh **HttpMessageNotReadableException**; controller thường chưa được gọi, nên không thể giả định sẽ tìm thấy lỗi đó trong **BindingResult** của handler.

Sau khi deserialize thành công, **@Valid @RequestBody** mới kích hoạt constraint trên DTO khi có Bean Validation provider. Nếu vi phạm ràng buộc trên đối tượng và không có tham số **Errors/BindingResult** phù hợp ngay sau đó, Spring MVC thường báo **MethodArgumentNotValidException** và mặc định trả HTTP 400. Nếu controller dùng method validation do có constraint trực tiếp trên tham số method, đường đi có thể phát sinh **HandlerMethodValidationException**. Cần viết error handling tương ứng với chữ ký controller thực tế.

**@Valid** kích hoạt kiểm tra constraint đã khai báo; bản thân nó không suy ra quy tắc như “người dùng được phép đặt tối đa số chỗ còn lại”.

## 3. Một tình huống, ba kết quả rất khác nhau

Giả sử request DTO có **customer: String** và **seats: Integer**, yêu cầu tên không rỗng và số chỗ ít nhất 1; kho chỉ còn 3 chỗ.

| Payload gửi lên | Ánh xạ sang Java | Constraint đầu vào | Quy tắc còn chỗ | Kết luận |
| --- | --- | --- | --- | --- |
| **{"customer":"Lan","seats":"abc"}** | Thất bại chuyển chuỗi “abc” thành Integer (JSON) | Chưa đến bước này | Chưa chạy | Lỗi đọc/chuyển dữ liệu |
| **{"customer":" ","seats":2}** | Thành công | **@NotBlank** thất bại | Chưa chạy | Không đạt input validation |
| **{"customer":"Lan","seats":0}** | Thành công | **@Min(1)** thất bại | Chưa chạy | Không đạt input validation |
| **{"customer":"Lan"}** | Thành công, **seats=null** | **@NotNull** thất bại | Chưa chạy | Thiếu dữ liệu bắt buộc |
| **{"customer":"Lan","seats":5}** | Thành công | Thành công | Thất bại vì còn 3 | **Dữ liệu hợp lệ về hình thức nhưng yêu cầu sai nghiệp vụ** |
| **{"customer":"Lan","seats":2}** | Thành công | Thành công | Thành công khi còn 3 | Có thể tiếp tục ghi, còn 1 chỗ |

Các dòng được xét **độc lập**, với kho ban đầu luôn có 3 chỗ. Ứng dụng thực tế còn phải xét xác thực, phân quyền, trạng thái sự kiện và các cạnh tranh đồng thời. Một field lạ hoặc field không được bind có thể bị từ chối hay bị bỏ qua tùy cấu hình; tuyệt đối không coi “không có lỗi chuyển kiểu” là bằng chứng mọi trường từ client đã được chấp nhận.

## 4. Ví dụ chạy được: binding và Bean Validation đều đạt, business rule vẫn chặn

Ví dụ tối giản dưới đây dùng **Java 17**, **Spring Boot 3.4.13**, Spring MVC và Jakarta Bean Validation. Để tái hiện độc lập, tạo hai tệp đúng vị trí. Dùng **starter-validation** để có Bean Validation provider; nếu thiếu dependency này, không được giả định **@Valid** đã thực thi constraint.

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>binding-vs-business</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/DemoApplication.java**

~~~java
package demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

// DTO chỉ ràng buộc dữ liệu đầu vào, không chứa trạng thái kho.
record ReservationRequest(
        @NotBlank String customer,
        @NotNull @Min(1) Integer seats
) {}

record ReservationResponse(String status, int remainingSeats) {}

@RestController
class ReservationController {
    private final SeatInventory inventory;

    ReservationController(SeatInventory inventory) {
        this.inventory = inventory;
    }

    @PostMapping("/reservations")
    ResponseEntity<ReservationResponse> create(
            @Valid @RequestBody ReservationRequest request) {
        // Dòng này chỉ chạy sau khi deserialize và object validation thành công.
        // Dù vậy, yêu cầu vẫn có thể vi phạm số chỗ còn lại.
        int remaining = inventory.reserve(request.seats());
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new ReservationResponse("ACCEPTED", remaining));
    }
}

@Service
class SeatInventory {
    private int availableSeats = 3;

    // synchronized chỉ minh họa atomicity trong MỘT tiến trình JVM.
    synchronized int reserve(int requestedSeats) {
        if (requestedSeats > availableSeats) {
            throw new SeatsUnavailableException(requestedSeats, availableSeats);
        }
        availableSeats -= requestedSeats;
        return availableSeats;
    }
}

class SeatsUnavailableException extends RuntimeException {
    SeatsUnavailableException(int requested, int available) {
        super("Requested %d seat(s); only %d available"
                .formatted(requested, available));
    }
}

@RestControllerAdvice
class ReservationErrorHandler {
    @ExceptionHandler(SeatsUnavailableException.class)
    ResponseEntity<Map<String, String>> onNoSeats(SeatsUnavailableException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(Map.of(
                        "code", "SEATS_UNAVAILABLE",
                        "message", ex.getMessage()
                ));
    }
}
~~~

Chạy trong thư mục chứa **pom.xml** với JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Gửi các yêu cầu dưới đây bằng một HTTP client (các lệnh **curl** dùng cú pháp shell POSIX). **Khởi động lại ứng dụng giữa các ca độc lập** để đặt lại tồn kho về 3 chỗ.

~~~bash
# Case A: mọi tầng đạt; tạo đăng ký 2 chỗ.
curl -i -X POST http://localhost:8080/reservations \
  -H 'Content-Type: application/json' \
  -d '{"customer":"Lan","seats":2}'

# Case B: deserialize được nhưng sai constraint @Min.
curl -i -X POST http://localhost:8080/reservations \
  -H 'Content-Type: application/json' \
  -d '{"customer":"Lan","seats":0}'

# Case C: deserialize được, @Valid đạt, quy tắc tồn kho từ chối.
curl -i -X POST http://localhost:8080/reservations \
  -H 'Content-Type: application/json' \
  -d '{"customer":"Lan","seats":5}'

# Case D: không chuyển được "abc" sang Integer.
curl -i -X POST http://localhost:8080/reservations \
  -H 'Content-Type: application/json' \
  -d '{"customer":"Lan","seats":"abc"}'
~~~

**Kết quả chính xác cần kiểm tra theo hợp đồng ví dụ:**

- **A → HTTP 201**, body JSON gồm **status = "ACCEPTED"** và **remainingSeats = 1**.
- **B → HTTP 400**, do **@Min(1)**. Body lỗi mặc định phụ thuộc cấu hình Spring Boot nên không ấn định nội dung.
- **C → HTTP 409**, body JSON gồm **code = "SEATS_UNAVAILABLE"** và **message = "Requested 5 seat(s); only 3 available"**. Đây là bằng chứng rõ nhất rằng bind và Bean Validation có thể thành công nhưng yêu cầu vẫn bị từ chối.
- **D → HTTP 400** do lỗi đọc/chuyển JSON, trước khi gọi controller. Nội dung body lỗi mặc định cũng phụ thuộc cấu hình.

Để chắc chắn C thực sự thuộc nhóm business error, đặt breakpoint hoặc log ở **SeatInventory.reserve(...)**: B và D không đi tới đây, còn C đi tới đây và bị chặn bởi kiểm tra **requestedSeats > availableSeats**. Code trên là ví dụ học tập dùng bộ đếm trong bộ nhớ; khi triển khai nhiều instance hoặc lưu DB, **synchronized** của một JVM không đủ bảo vệ tồn kho toàn hệ thống.

## 5. Thiết kế tầng chịu trách nhiệm kiểm tra

Một thiết kế thường dễ hiểu và dễ kiểm thử:

1. **Request DTO / adapter** mô tả dữ liệu client được phép gửi và các ràng buộc ít phụ thuộc trạng thái, chẳng hạn **@NotNull**, **@NotBlank**, **@Size**, **@Min**, định dạng ngày tháng.
2. **Controller** chọn cơ chế đọc dữ liệu (**@ModelAttribute** hoặc **@RequestBody**), bật **@Valid/@Validated** khi cần, chuyển dữ liệu hợp lệ cho service; trả thông báo lỗi đầu vào dễ hiểu.
3. **Application service / domain** kiểm tra quyền thao tác, khả năng thực hiện, trạng thái chuyển đổi, tính duy nhất theo ngữ cảnh, hạn mức, tồn kho, thời điểm hiệu lực. Đặt quy tắc thiết yếu ở tầng có thể được gọi từ cả HTTP, message consumer và batch job.
4. **Repository / transaction / database** bảo vệ bất biến trong lúc ghi. Ví dụ **UNIQUE** constraint cho mã nghiệp vụ, optimistic locking, cập nhật tồn kho có điều kiện, hoặc khóa giao dịch phù hợp. Kiểm tra “còn hàng” rồi ghi ở hai thao tác không nguyên tử vẫn có nguy cơ oversell.

Một quy tắc không nhất thiết thuộc cố định một tầng: **định dạng email** phù hợp với constraint trên DTO; **email chưa được người khác sử dụng** phụ thuộc dữ liệu hiện tại và phải tính tới tranh chấp giữa hai request. Tùy trường hợp có thể viết custom validator, nhưng không nên dùng annotation để che giấu một thao tác truy vấn/ghi dữ liệu có side effect hoặc bỏ qua việc bảo đảm nhất quán ở DB.

**Phân quyền** cũng khác với validation: request có **userId** đúng kiểu và đúng định dạng vẫn có thể bị từ chối nếu caller không sở hữu tài nguyên đó. Không tin vào một cờ **isAdmin**, **price**, **ownerId** do client tự khai khi quyết định quyền hoặc số tiền; các giá trị nhạy cảm phải được xác lập và kiểm tra phía server.

## 6. Chọn cách biểu diễn lỗi cho đúng bản chất

| Tình huống | Thường xử lý ở đâu | HTTP status gợi ý cho REST API |
| --- | --- | --- |
| Body JSON sai cú pháp hoặc không deserialize được | Framework / exception handler | **400 Bad Request** |
| Vi phạm constraint đầu vào, chẳng hạn giá trị âm hoặc thiếu trường bắt buộc | **@Valid**, **BindingResult**, validation handler | **400 Bad Request**; một số API chọn **422** theo hợp đồng riêng |
| Quy tắc xung đột với trạng thái hiện tại: hết chỗ, phiên bản dữ liệu cũ | Service/domain + exception mapping | **409 Conflict** khi đúng nghĩa xung đột trạng thái |
| Caller không được phép thao tác | Security/authorization | **403 Forbidden** (hoặc **401** nếu chưa xác thực, theo cơ chế bảo mật) |
| Tài nguyên được tham chiếu không tồn tại | Service/repository | **404 Not Found** khi phù hợp resource contract |
| Vi phạm ràng buộc khi ghi đồng thời | Transaction/DB + xử lý exception có chủ đích | Mapping theo bản chất lỗi và hợp đồng API; không mặc nhiên quy mọi lỗi DB về 400 |

**Status code phải phản ánh hợp đồng API và loại lỗi thực tế**; không mặc định mọi business exception là 409. Trả **error code** ổn định và message đủ an toàn cho client; tránh trả stack trace, SQL hoặc dữ liệu nhạy cảm. Nếu ứng dụng hỗ trợ **ProblemDetail**, có thể chuẩn hóa cách diễn đạt lỗi và phần thông tin mở rộng.

Trong web form, trả cùng view với **BindingResult** thường hợp lý hơn chuyển thành JSON 400. Khi thêm business error vào form, có thể dùng **result.rejectValue(...)** hoặc **result.reject(...)**, nhưng phải phân biệt nguồn lỗi khi log và kiểm thử: lỗi ấy được service phát hiện **sau** khi bind và Bean Validation đã đạt, không phải bằng chứng data binding thất bại.

## 7. Những hiểu lầm và lỗi triển khai phổ biến

**“Java object đã được tạo thì request hợp lệ.”** Sai: một object vẫn có thể chứa null, chuỗi trắng, giá trị mặc định hoặc thuộc tính bị bỏ qua. Chỉ đọc request không tự động chứng minh tính đầy đủ.

**“Gắn @Valid là đủ cho nghiệp vụ.”** Sai: **@Valid** chỉ chạy các constraint tương ứng, không biết tồn kho hay quyền sở hữu nếu chưa có logic xác thực. Cũng cần provider và annotation đặt đúng vị trí.

**“hasErrors() luôn là lỗi parse.”** Sai: **BindingResult** có thể mang cả lỗi binding lẫn Bean Validation. Phân tích từng **FieldError**, **isBindingFailure()**, mã lỗi và giai đoạn phát sinh.

**“Bắt được mọi lỗi JSON trong BindingResult.”** Sai: **HttpMessageConverter** có thể thất bại trước khi tạo được DTO. Hãy kiểm soát **HttpMessageNotReadableException** ở đường xử lý lỗi phù hợp.

**“Chỉ dùng @Min(1) là đủ cho Integer bắt buộc.”** Sai: hầu hết constraint như **@Min** không tự bác bỏ **null**. Kết hợp **@NotNull** khi field là bắt buộc; dùng **Integer** nếu cần phân biệt thiếu/null với số 0.

**“Không có @Valid mà vẫn không lỗi tức là đã validate.”** Sai: mapping có thể thành công mà không kích hoạt Bean Validation. Xác minh cấu hình và test thực tế.

**“Kiểm tra tồn kho trước khi save là chắc chắn.”** Sai trong hệ thống đồng thời nếu bước kiểm tra và cập nhật không được bảo vệ bằng giao dịch/điều kiện cập nhật/khóa thích hợp; hai request có thể cùng đọc “còn 1 chỗ” rồi cùng ghi.

**“Cho bind trực tiếp entity sẽ thuận tiện hơn.”** Có nguy cơ **mass assignment/over-posting** các thuộc tính như role, ownerId, status. Ưu tiên DTO riêng; nếu dùng property binding, giới hạn trường được bind bằng **allowedFields** hoặc thiết kế constructor binding phù hợp.

## 8. Cách kiểm thử để không nhầm tầng

Nên viết test độc lập cho từng ranh giới:

- **Binding/deserialization:** gửi giá trị sai kiểu hoặc JSON hỏng; xác nhận controller/service không xử lý nghiệp vụ.
- **Bean Validation:** dữ liệu đọc được nhưng vi phạm **@NotNull**, **@NotBlank**, **@Min**; xác nhận trả lỗi đầu vào và không cập nhật kho.
- **Business validation:** gửi DTO đúng constraint nhưng vi phạm trạng thái thực tế (ví dụ yêu cầu 5 khi còn 3); xác nhận service từ chối, trạng thái không đổi và API trả mã lỗi phù hợp.
- **Happy path:** request hợp lệ, còn đủ chỗ, cập nhật đúng một lần và response có dữ liệu đúng.
- **Concurrency:** mô phỏng hai request cạnh tranh chỗ cuối cùng ở tầng giao dịch/DB để đảm bảo tổng số ghế được giữ không vượt số có sẵn.

Câu hỏi tự kiểm tra: *Nếu đổi giá trị **seats** từ chuỗi “abc” thành số 5, tại sao lỗi phải chuyển từ tầng deserialize sang tầng service?* Vì với **5**, Java và Bean Validation đã có đủ thông tin để chấp nhận kiểu và giới hạn tối thiểu; chỉ dữ liệu tồn kho mới quyết định yêu cầu được thực hiện hay không.

## Tài liệu chính thức

- [Spring MVC — @ModelAttribute và BindingResult](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC — @RequestBody và conversion/validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring MVC — Validation và các exception theo chữ ký method](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Jakarta Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
