# Đọc kết quả validation và quyết định có tiếp tục nghiệp vụ hay không

Trong Spring Framework, việc bind dữ liệu vào đối tượng Java **không đồng nghĩa với việc dữ liệu đã hợp lệ**, và việc đối tượng vượt qua validation **không đồng nghĩa với việc nghiệp vụ chắc chắn được phép thực hiện**. Ở cuối luồng xử lý input, ứng dụng cần đọc kết quả, chặn nhánh không hợp lệ, rồi mới gọi use case/service có tác dụng thay đổi trạng thái.

Mục tiêu của bài này là trả lời ba câu hỏi: **đọc kết quả ở đâu**, **đọc những gì**, và **dựa vào kết quả đó quyết định dừng hay tiếp tục thế nào**. Phạm vi là Spring Validation/Data Binding (đặc biệt `DataBinder`, `Errors`, `BindingResult` và Spring MVC); các quy tắc nghiệp vụ sâu hơn vẫn thuộc tầng application/domain.

## 1. Thứ tự xử lý và ranh giới quyết định

~~~text
Input từ người dùng
    |
    v
Giải mã/đọc request và bind vào DTO (có thể phát sinh lỗi chuyển kiểu)
    |
    v
Áp dụng các validator phù hợp (có thể phát sinh lỗi ràng buộc)
    |
    v
Đọc Errors / BindingResult
    |
    +-- Có lỗi? -- Có --> Trả thông báo lỗi phù hợp; DỪNG use case ghi dữ liệu
    | 
    +-- Không
          |
          v
    Kiểm tra điều kiện nghiệp vụ và quyền thực hiện
          |
          +-- Không đạt --> Từ chối bằng kết quả nghiệp vụ thích hợp
          |
          +-- Đạt --> Thực thi service / transaction --> Trả kết quả thành công
~~~

Cần phân biệt:

- **Lỗi đọc/chuyển đổi dữ liệu**: chuỗi `"abc"` không đổi được sang `Integer`, JSON sai cú pháp, hoặc định dạng request không phù hợp. Không phải mọi lỗi đều đi đến cùng một `BindingResult`: lỗi giải mã JSON có thể khiến controller chưa được gọi.
- **Lỗi validation**: dữ liệu đã đọc được nhưng vi phạm ràng buộc như bắt buộc nhập, độ dài, khoảng giá trị, hoặc quan hệ giữa các trường. Chúng thường được ghi thành `FieldError` hoặc `ObjectError`.
- **Lỗi nghiệp vụ/ủy quyền**: đầu vào hợp lệ về cấu trúc nhưng hết tồn kho, trùng mã trong hệ thống, vượt hạn mức, không đủ quyền, hoặc trạng thái đơn hàng không cho phép thao tác. Phải kiểm tra ở đúng tầng và không mặc định biến tất cả thành lỗi nhập liệu.

Nguyên tắc cốt lõi: **chỉ gọi nhánh có side effect sau khi đã xử lý hết lỗi đầu vào**. Việc đọc một DTO hoặc gọi getter là an toàn; lưu DB, gửi email, trừ tiền, phát sự kiện hay gọi API ghi dữ liệu trước khi kiểm tra lỗi sẽ gây hậu quả khó hoàn tác.

## 2. Đọc `BindingResult` đúng cách

`org.springframework.validation.Errors` cung cấp các phép kiểm tra lỗi và truy xuất thông tin; `BindingResult` mở rộng `Errors`, thường do `DataBinder` hoặc Spring MVC cung cấp. Sau khi gọi `binder.bind(...)` và `binder.validate()`, lấy kết quả bằng `binder.getBindingResult()`. Trong MVC, khai báo tham số `BindingResult` hoặc `Errors` **ngay sau** tham số cần được bind/validate.

| API | Ý nghĩa và cách dùng |
| --- | --- |
| `hasErrors()` | Cổng quyết định chung: có ít nhất một lỗi bind/validation thì chưa được thực hiện use case. |
| `getErrorCount()` | Tổng số lỗi; hữu ích cho thống kê/quan sát, không thay thế nội dung từng lỗi. |
| `getFieldErrors()` / `getFieldError("quantity")` | Lỗi gắn với trường; có thể lấy tên trường, mã lỗi, thông điệp mặc định. |
| `getGlobalErrors()` | Lỗi ở mức đối tượng, ví dụ khoảng ngày bắt đầu/kết thúc không hợp lệ. |
| `getAllErrors()` | Gộp lỗi trường và lỗi toàn đối tượng để xây dựng phản hồi. |
| `hasFieldErrors("quantity")` | Hỏi nhanh một trường có lỗi hay không, ví dụ để hiển thị dưới input tương ứng. |
| `getSuppressedFields()` | Danh sách trường bị loại khỏi quá trình bind khi áp dụng giới hạn bind; cần xem xét riêng, không mặc định xem là tương đương với `hasErrors()`. |

Một `FieldError` kế thừa `ObjectError`. `getCode()` trả mã lỗi cụ thể; `getCodes()` có thể chứa nhiều mã theo mức độ ưu tiên để tra thông điệp theo locale; `getDefaultMessage()` là thông điệp mặc định, có thể là `null`. Đừng ràng buộc luồng nghiệp vụ vào chuỗi thông báo đã dịch; hãy dùng mã/trạng thái có ý nghĩa, còn thông điệp phục vụ người dùng.

`hasErrors()` là điều kiện đủ để **chặn tiếp tục**, nhưng `!hasErrors()` chỉ cho biết **các kiểm tra đã thực sự chạy** không báo lỗi. Nó không tự bảo đảm quyền truy cập, tính duy nhất tại DB, hay tính bất biến nghiệp vụ.

## 3. Ví dụ Java 17 chạy được: hai nhánh từ cùng một kết quả

Ví dụ này dùng trực tiếp Spring `DataBinder`, không cần máy chủ HTTP. Bộ nhận dữ liệu bind `customer` và `quantity`, chạy `OrderValidator`, kiểm tra `BindingResult` rồi mới cho phép `OrderService` lưu. Cấu trúc dự án:

~~~text
validation-decision/
├── pom.xml
└── src/main/java/demo/ValidationDecisionDemo.java
~~~

Tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>validation-decision</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.ValidationDecisionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tạo `src/main/java/demo/ValidationDecisionDemo.java`:

~~~java
package demo;

import java.util.Map;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public class ValidationDecisionDemo {
    public static final class OrderInput {
        private String customer;
        private Integer quantity;

        public String getCustomer() {
            return customer;
        }

        public void setCustomer(String customer) {
            this.customer = customer;
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }
    }

    public static final class OrderValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return OrderInput.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            OrderInput input = (OrderInput) target;

            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "customer", "customer.required",
                    "Tên khách hàng bắt buộc");

            if (input.getQuantity() == null || input.getQuantity() <= 0) {
                errors.rejectValue(
                        "quantity", "quantity.positive",
                        "Số lượng phải lớn hơn 0");
            }
        }
    }

    public static final class OrderService {
        private int saved;

        public void create(OrderInput order) {
            saved++;
            System.out.println(
                    "SAVED: " + order.getCustomer() + " x" + order.getQuantity());
        }
    }

    private static void handle(Map<String, String> raw, OrderService service) {
        OrderInput input = new OrderInput();
        DataBinder binder = new DataBinder(input, "order");
        binder.setValidator(new OrderValidator());

        binder.bind(new MutablePropertyValues(raw));
        binder.validate();

        BindingResult result = binder.getBindingResult();
        if (result.hasErrors()) {
            System.out.println("REJECTED: " + result.getErrorCount());
            result.getFieldErrors().forEach(error ->
                    System.out.println(
                            error.getField() + ": " + error.getDefaultMessage()));
            return; // Không gọi service khi dữ liệu không hợp lệ.
        }

        service.create(input);
    }

    public static void main(String[] args) {
        OrderService service = new OrderService();

        handle(Map.of("customer", "Mai", "quantity", "2"), service);
        handle(Map.of("customer", "   ", "quantity", "0"), service);

        System.out.println("TOTAL_SAVED=" + service.saved);
    }
}
~~~

Với **JDK 17+** và **Maven** trong thư mục `validation-decision`, chạy:

~~~bash
mvn -q compile exec:java
~~~

Kết quả tiêu chuẩn:

~~~text
SAVED: Mai x2
REJECTED: 2
customer: Tên khách hàng bắt buộc
quantity: Số lượng phải lớn hơn 0
TOTAL_SAVED=1
~~~

Giải thích từng bước:

1. `DataBinder` chuyển chuỗi `"2"` thành `Integer` và gán các thuộc tính qua setter; sau đó `validate()` gọi `OrderValidator`. Nếu không gọi `validate()` trong ví dụ thủ công này thì không có kiểm tra quy tắc của `OrderValidator`.
2. Lần đầu không có lỗi nên `service.create(input)` chạy đúng một lần.
3. Lần sau `customer` chỉ có khoảng trắng và `quantity = 0`, validator đăng ký hai `FieldError`. Lệnh `return` cắt nhánh, ngăn `service.create(...)`.
4. `TOTAL_SAVED=1` minh họa bất biến cần bảo vệ: input bị từ chối không tạo thêm bản ghi. `OrderService` ở đây chỉ đếm và in ra màn hình; trong ứng dụng thật việc lưu DB xảy ra bên trong service/transaction.

Nếu chuỗi số lượng không chuyển đổi được (ví dụ `"abc"`), binding có thể đăng ký lỗi kiểu `typeMismatch` trong `BindingResult`. Khi viết validator, cần tính đến thuộc tính có thể vẫn là `null` và tránh dereference gây `NullPointerException` hoặc thông báo lỗi trùng lặp. Thông thường chỉ nên tiếp tục sang bước nghiệp vụ nếu **toàn bộ** lỗi bind và validation đã được xử lý.

## 4. Nhánh quyết định trong Spring MVC

Với form HTML (được bind vào `@ModelAttribute`), cách xử lý phổ biến là **trả lại form kèm lỗi** và không gọi service:

~~~java
// Đoạn trích từ một @Controller; OrderForm và orderService
// được định nghĩa ở phần còn lại của ứng dụng.
@PostMapping("/orders/form")
public String submit(@Valid @ModelAttribute("order") OrderForm form,
                     BindingResult result) {
    if (result.hasErrors()) {
        return "orders/form";
    }
    orderService.create(form);
    return "redirect:/orders";
}
~~~

Điều kiện bắt buộc của chữ ký phương thức trên là `BindingResult` **đứng ngay sau** `@Valid @ModelAttribute("order") OrderForm`. Template có thể đọc các field errors để đánh dấu trường sai và giữ lại dữ liệu hợp lệ đã nhập. Việc trả về form là một lựa chọn của controller, không phải hành vi tự động của `BindingResult`.

Với REST JSON, có thể chặn tại controller và trả `400 Bad Request` có cấu trúc, thay vì tiếp tục tạo tài nguyên:

~~~java
// Đoạn trích minh họa, cần Spring MVC, Bean Validation provider,
// OrderApplicationService và các import tương ứng trong ứng dụng.
record CreateOrderRequest(
        @NotBlank String customer,
        @NotNull @Min(1) Integer quantity) {}

record InputIssue(String field, String message) {}

@RestController
class OrderController {
    private final OrderApplicationService service;

    OrderController(OrderApplicationService service) {
        this.service = service;
    }

    @PostMapping("/orders")
    ResponseEntity<?> create(@Valid @RequestBody CreateOrderRequest input,
                             BindingResult result) {
        if (result.hasErrors()) {
            var issues = result.getAllErrors().stream()
                    .map(error -> new InputIssue(
                            error instanceof FieldError field
                                    ? field.getField() : "_global",
                            error.getDefaultMessage()))
                    .toList();
            return ResponseEntity.badRequest().body(issues);
        }

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(service.create(input));
    }
}
~~~

`@Valid` cần một Bean Validation provider được cấu hình (với Spring Boot 3.x, thường là dependency `spring-boot-starter-validation`). Những annotation trong ví dụ dùng namespace `jakarta.validation.*`. Mẫu REST ở trên là **đoạn controller minh họa**, không phải file Java chạy độc lập; ví dụ `DataBinder` ở mục 3 là chương trình chạy đầy đủ.

Với `@Valid @RequestBody` hoặc `@Valid @ModelAttribute`, nếu không nhận `Errors`/`BindingResult` liền kề và validation tham số đơn lẻ thất bại, Spring MVC thường ném `MethodArgumentNotValidException`; mặc định lỗi validation của request body dẫn đến HTTP 400. Có thể xử lý nhất quán bằng `@RestControllerAdvice` và `@ExceptionHandler`. Nếu có ràng buộc được khai báo trực tiếp trên tham số phương thức khiến **method validation** được áp dụng, Spring MVC có thể ném `HandlerMethodValidationException`; hệ thống xử lý lỗi tập trung cần tính đến cả hai trường hợp.

Một request chứa JSON sai cú pháp, trường có kiểu không thể deserialize, hoặc không có body khi body bắt buộc có thể thất bại **trước lúc controller nhận được `BindingResult`** (ví dụ `HttpMessageNotReadableException`). Do đó, quy tắc “`if (result.hasErrors())`” trong controller không thay thế việc xử lý exception ở lớp request mapping/conversion.

## 5. Quyết định nào thuộc validation, quyết định nào thuộc nghiệp vụ?

Bản thân `BindingResult` ghi các lỗi kiểm tra/binding; nó **không phải phiếu thông hành cho mọi thao tác**. Nên xử lý theo những lớp rõ ràng:

| Tình huống | Quyết định | Nơi xử lý thường gặp |
| --- | --- | --- |
| Thiếu `customer` hoặc `quantity <= 0` | Dừng; phản hồi lỗi theo trường | Bean Validation/Spring `Validator`, controller |
| Chuỗi `quantity = "abc"` không bind được | Dừng; báo lỗi kiểu dữ liệu | Binding/conversion hoặc JSON conversion handler |
| `startDate > endDate` | Dừng; trả lỗi mức đối tượng hoặc trường liên quan | Validator kiểm tra nhiều trường |
| Dữ liệu hợp lệ nhưng sản phẩm hết hàng | Không tạo đơn; phản hồi xung đột/không đáp ứng điều kiện nghiệp vụ | Application/domain service |
| Mã phải duy nhất nhưng bị trùng khi hai request chạy đồng thời | Từ chối thao tác xung đột; giữ ràng buộc ở DB | Domain/service + unique constraint/transaction |
| Người dùng không được phép tạo đơn | Từ chối theo cơ chế xác thực/phân quyền | Security/application service |

HTTP 400 là lựa chọn thông dụng cho request không hợp lệ. HTTP 409 thường hợp lý cho xung đột trạng thái/duy nhất; HTTP 403 cho thiếu quyền; HTTP 422 có thể được quy ước cho một số lỗi ngữ nghĩa của request. Các mã 409/422 là **chính sách API ứng dụng**, không phải kết quả Spring Validation tự động suy ra từ `hasErrors()`.

Nếu validator kiểm tra dữ liệu bên ngoài (ví dụ gọi DB để xác nhận tên tài khoản chưa tồn tại), vẫn phải duy trì ràng buộc và kiểm tra cần thiết tại service/DB: kết quả “chưa trùng” ở thời điểm validation có thể không còn đúng khi ghi. Transaction giúp bảo vệ một số bất biến, nhưng việc xử lý xung đột cụ thể tùy hạ tầng lưu trữ.

## 6. Thiết kế phản hồi lỗi để phía gọi có thể sửa được

Một API nên trả lỗi có cấu trúc ổn định, chẳng hạn:

~~~json
{
  "code": "INVALID_INPUT",
  "errors": [
    {
      "field": "customer",
      "code": "customer.required",
      "message": "Tên khách hàng bắt buộc"
    },
    {
      "field": "quantity",
      "code": "quantity.positive",
      "message": "Số lượng phải lớn hơn 0"
    }
  ]
}
~~~

Đây là **mẫu contract của ứng dụng**, không phải body mặc định do Spring tự tạo. Với lỗi ở mức đối tượng, có thể dùng `field: null` hoặc một giá trị quy ước như `"_global"` và ghi rõ quy ước cho frontend. Giữ `code` ổn định cho chương trình xử lý; `message` có thể được bản địa hóa. Không nên lộ stack trace, class nội bộ, dữ liệu bí mật hoặc toàn bộ rejected value trong phản hồi.

Với form, mục tiêu là render lại input và thông báo gắn đúng trường. Với REST, mục tiêu là status chính xác, mã lỗi ổn định và danh sách lỗi đủ để client biết cần sửa gì. Trong cả hai trường hợp, **bảo đảm không có side effect trước nhánh từ chối** quan trọng hơn hình thức hiển thị.

## 7. Những lỗi triển khai thường gặp

- **Chỉ bind mà quên validate**: trong luồng `DataBinder` thủ công, `binder.bind(...)` không tự thay cho `binder.validate()`; `hasErrors() == false` lúc đó có thể chỉ nói rằng việc bind không báo lỗi.
- **Đặt `BindingResult` sai chỗ**: trong Spring MVC, `BindingResult` phải ngay sau đối tượng tương ứng. Nếu không, controller có thể không bắt được lỗi theo cách mong đợi.
- **Gọi service rồi mới kiểm tra `hasErrors()`**: có thể tạo dữ liệu sai hoặc phát sự kiện dù cuối cùng HTTP báo lỗi.
- **Chỉ xem `getFieldErrors()`**: sẽ bỏ sót `getGlobalErrors()` ở các ràng buộc liên trường; dùng `getAllErrors()` khi phản hồi cần đủ lỗi.
- **Đồng nhất “valid” với “authorized/business success”**: validation không thay kiểm tra quyền, trạng thái, tồn kho và bất biến DB.
- **Giả định mọi request lỗi đều tới controller**: lỗi đọc body/convert JSON có thể xảy ra trước đó và cần exception handler.
- **Dùng `getDefaultMessage()` làm mã trạng thái**: chuỗi này có thể đổi do localization; dùng code/status rõ ràng.
- **Ghi log cả `getRejectedValue()` hoặc request raw**: có thể lộ mật khẩu, token, dữ liệu cá nhân; chỉ ghi thông tin tối thiểu và đã loại dữ liệu nhạy cảm.
- **Bind trực tiếp mọi thuộc tính của entity**: tạo nguy cơ sửa trường ngoài ý muốn. Dùng DTO chuyên biệt, giới hạn field được bind khi phù hợp, rồi ánh xạ có kiểm soát sang domain model.

## 8. Kiểm tra một luồng hoàn chỉnh

Khi kiểm thử controller/use case, nên quan sát cả **kết quả trả về** lẫn **số lần side effect**:

| Input/điều kiện | Kết quả mong đợi | Có gọi service ghi dữ liệu? |
| --- | --- | --- |
| Đúng định dạng, đạt validation và được phép thực thi | Thành công, ví dụ `201 Created` khi tạo mới | Có, đúng một lần |
| Thiếu trường bắt buộc | Lỗi trường, thường `400` | Không |
| Sai kiểu hoặc body JSON không đọc được | Lỗi input/conversion, thường `400` | Không |
| Sai quan hệ giữa các trường | Lỗi mức đối tượng/trường, thường `400` | Không |
| Đạt validation nhưng vi phạm bất biến nghiệp vụ | Kết quả từ chối nghiệp vụ, ví dụ `409` | Không tạo trạng thái thành công |
| Hai thao tác cùng cạnh tranh một giá trị unique | Một thao tác có thể thắng, thao tác còn lại nhận xung đột phù hợp | Không có bản ghi trùng |

Có thể mock service để xác minh `verifyNoInteractions(service)` trong nhánh đầu vào không hợp lệ; ở kiểm thử tích hợp cần kiểm tra DB không bị thay đổi. Điều này xác minh đúng mục tiêu của bước “đọc kết quả và quyết định”: **lỗi bị chặn trước khi nghiệp vụ được thực thi**.

## 9. Ghi nhớ khi áp dụng

Thứ tự triển khai đáng tin cậy là **bind → validate → đọc `BindingResult` → dừng nếu có lỗi → kiểm tra quy tắc nghiệp vụ/quyền → thực thi**. Trong controller, nhánh từ chối phải xuất hiện trước lời gọi service; trong service, các bất biến nghiệp vụ phải tiếp tục được bảo vệ dù request đã qua validation. Nếu controller không được gọi do lỗi converter hoặc lỗi method validation, hãy để exception handler phản hồi đồng nhất.

Tài liệu Spring chính thức để tra cứu chi tiết API và điều kiện kích hoạt:

- [Validation và `DataBinder`](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [`@ModelAttribute` và `BindingResult` trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [`@RequestBody` và xử lý lỗi validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Phân biệt argument validation và method validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
