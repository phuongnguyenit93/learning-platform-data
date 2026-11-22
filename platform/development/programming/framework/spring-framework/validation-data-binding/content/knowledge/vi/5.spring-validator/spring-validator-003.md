# Spring Validator: `validate()` và cách ghi lỗi vào `Errors`

Trong Spring Framework, một đối tượng có thể **nhận dữ liệu hợp lệ về kiểu nhưng vẫn vi phạm quy tắc nghiệp vụ**: tên chỉ chứa khoảng trắng, số lượng vượt giới hạn, ngày kết thúc trước ngày bắt đầu. `org.springframework.validation.Validator` cho phép đặt các quy tắc đó trong một thành phần riêng. Phương thức `validate(Object target, Errors errors)` **không trả về danh sách lỗi**; nó nhận bộ thu thập `Errors` và **ghi các lỗi phát hiện được vào đó**. Sau khi chạy, controller, `DataBinder` hoặc service đọc lại lỗi để quyết định xử lý tiếp.

Bài này tập trung vào cách triển khai `validate()`, chọn `rejectValue()` hoặc `reject()`, kiểm tra lỗi và tích hợp với Spring MVC.

## 1. Hợp đồng của `Validator`

Interface cốt lõi:

~~~java
package org.springframework.validation;

public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
~~~

- `supports(Class<?> clazz)` cho biết validator **có hỗ trợ kiểu đối tượng** được yêu cầu hay không. Cách viết thường dùng là `MyForm.class.isAssignableFrom(clazz)` nếu chấp nhận cả lớp con, hoặc so sánh `equals` nếu chỉ muốn đúng một lớp.
- `validate(Object target, Errors errors)` kiểm tra `target`, rồi gọi các phương thức của `errors` để **đăng ký từng vi phạm**. Giá trị trả về là `void`; dữ liệu lỗi nằm trong đối tượng `Errors` do bên gọi cung cấp.
- Validator nên coi những lỗi input thông thường là **kết quả kiểm tra**, không ném exception cho mỗi lỗi dữ liệu. Exception phù hợp hơn với trường hợp chương trình dùng sai API hoặc trạng thái hệ thống bất thường.
- `validate()` không được mặc định gọi chỉ vì bạn khai báo một class implements `Validator`. Cần gọi trực tiếp hoặc đăng ký validator với `DataBinder`/Spring MVC để nó được thực thi trong luồng tương ứng.

Sơ đồ luồng:

~~~text
Dữ liệu request / đối tượng Java
                 |
        [binding, nếu có]
                 |
          target đã tạo
                 |
        Validator.validate(target, errors)
                 |
       +---------+----------+
       |                    |
  Điều kiện đạt         Điều kiện sai
  Không ghi lỗi        errors.rejectValue(...)
                       errors.reject(...)
       |                    |
       +----------+---------+
                  |
      Errors / BindingResult
                  |
        hasErrors(), getFieldErrors(),
        getGlobalErrors(), getAllErrors()
                  |
     Hiển thị form / trả HTTP 400 / xử lý tiếp
~~~

`Errors` là **giao diện báo và đọc lỗi**. `BindingResult` **mở rộng `Errors`**, bổ sung thông tin liên quan đến binding (ví dụ tên model, giá trị binding, thông tin field và model). Vì vậy một `BindingResult` có thể truyền vào tham số `Errors` của `validate()`. Việc ghi lỗi thông qua `Errors` không phụ thuộc controller sẽ hiển thị HTML hay trả JSON.

## 2. Ghi lỗi field bằng `rejectValue()`

Khi vi phạm gắn với **một thuộc tính cụ thể**, gọi:

~~~java
errors.rejectValue("customerName", "booking.customerName.required");

errors.rejectValue(
        "seats",
        "booking.seats.range",
        new Object[] {1, 8},
        "Số chỗ phải từ 1 đến 8.");
~~~

Ý nghĩa của các đối số:

| Đối số | Ý nghĩa |
| --- | --- |
| `field` | Tên property **trên đối tượng đang được validate**, ví dụ `"customerName"` hoặc `"seats"`; hỗ trợ đường dẫn nested khi mô hình phù hợp |
| `errorCode` | Mã lỗi logic như `booking.seats.range`; dùng để phân loại và tra thông báo |
| `errorArgs` | Tham số có thể được chèn vào thông báo từ resource bundle, ví dụ min=1, max=8 |
| `defaultMessage` | Thông báo dự phòng nếu không tìm được bản dịch theo mã lỗi |

`rejectValue()` tạo `FieldError` và thêm vào danh sách lỗi. Nó **không tự kết thúc phương thức `validate()`**, **không tự trả HTTP 400** và cũng **không sửa giá trị field**. Muốn ghi nhiều vi phạm thì tiếp tục kiểm tra và gọi các hàm đăng ký lỗi khác.

`errorCode` là mã do ứng dụng định nghĩa. Spring có thể mở rộng mã thành các ứng viên cụ thể theo tên object/field/kiểu thông qua `MessageCodesResolver`. Với object tên `bookingForm`, một lỗi `booking.seats.range` trên field `seats` có thể được tra với key riêng như `booking.seats.range.bookingForm.seats`, sau đó đến các key tổng quát. Không cần ghép trước toàn bộ key vào mã truyền cho `rejectValue()`.

Để kiểm tra field có lỗi hay không:

~~~java
if (errors.hasFieldErrors("seats")) {
    // Đã có ít nhất một lỗi liên quan đến seats.
}
~~~

Một field có thể có **nhiều lỗi**. `getFieldError("seats")` chỉ lấy một lỗi, còn `getFieldErrors("seats")` lấy danh sách. Khi trả lỗi cho người dùng, nên quyết định rõ cần trả tất cả lỗi hay lỗi ưu tiên; không vô tình làm mất các lỗi khác.

## 3. Ghi lỗi cấp đối tượng bằng `reject()`

Một số điều kiện liên quan **nhiều field cùng lúc**, nên không có một field duy nhất chịu trách nhiệm. Ví dụ ngày rời đi phải sau hoặc bằng ngày đến:

~~~java
if (arrivalDate != null && departureDate != null
        && departureDate.isBefore(arrivalDate)) {
    errors.reject(
            "booking.dates.order",
            "Ngày rời đi không được trước ngày đến.");
}
~~~

`reject(errorCode, defaultMessage)` đăng ký **`ObjectError`** ở cấp đối tượng. Lỗi này xuất hiện trong `errors.getGlobalErrors()`, còn lỗi của một field nằm trong `errors.getFieldErrors()`. `errors.getAllErrors()` gồm cả hai loại.

Chọn vị trí báo lỗi dựa trên cách người dùng cần sửa dữ liệu:

- Tên khách trống → field `customerName` → `rejectValue("customerName", ...)`.
- Số chỗ không thuộc khoảng 1–8 → field `seats` → `rejectValue("seats", ...)`.
- Cặp ngày mâu thuẫn → object `bookingForm` → `reject(...)`; nếu thiết kế UI muốn gắn rõ ở field ngày rời đi, có thể chọn `rejectValue("departureDate", ...)` thay vì một lỗi global.

Đừng gắn mọi quy tắc vào một field bất kỳ chỉ để dễ render. Việc phân loại đúng giúp client hiển thị lỗi cạnh trường phù hợp hoặc ở đầu form.

## 4. Dùng `ValidationUtils` cho kiểm tra trống

Spring có tiện ích:

~~~java
ValidationUtils.rejectIfEmpty(
        errors, "customerName", "booking.customerName.required");

ValidationUtils.rejectIfEmptyOrWhitespace(
        errors, "customerName", "booking.customerName.required");
~~~

`rejectIfEmpty()` đánh dấu `null` hoặc chuỗi rỗng `""`; `rejectIfEmptyOrWhitespace()` còn đánh dấu chuỗi chỉ có khoảng trắng như `"   "`. Các overload cho phép cung cấp `errorArgs` và `defaultMessage` khi cần.

Tiện ích đọc giá trị field thông qua `Errors`, vì vậy **không cần tự trích property** để gọi hàm. Tuy nhiên, nó không thay cho các quy tắc như kiểm tra khoảng số, ràng buộc giữa các ngày hoặc kiểm tra nghiệp vụ phức tạp. Với field không phải chuỗi, cần hiểu rõ thế nào là "trống" trong mô hình dữ liệu.

Có thể viết trực tiếp:

~~~java
if (form.getCustomerName() == null
        || form.getCustomerName().isBlank()) {
    errors.rejectValue("customerName", "booking.customerName.required");
}
~~~

Cả hai cách hợp lệ; `ValidationUtils` thuận tiện khi kiểm tra những thuộc tính đã có trong `Errors`.

## 5. Ví dụ Java 17+ hoàn chỉnh: validator ghi ba lỗi

Ví dụ sau dùng **Spring Framework 6.x**, không cần khởi động web server. Đặt vào file `src/main/java/BookingDemo.java` trong một dự án Maven có dependency `org.springframework:spring-context` (hoặc ứng dụng Spring Boot đã có `spring-boot-starter-web`). Đây là **một file Java hoàn chỉnh có `main`**, có thể chạy khi classpath đã chứa thư viện Spring tương ứng.

~~~java
import java.time.LocalDate;

import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.BindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public class BookingDemo {

    static final class BookingForm {
        private String customerName;
        private Integer seats;
        private LocalDate arrivalDate;
        private LocalDate departureDate;

        public String getCustomerName() {
            return customerName;
        }

        public void setCustomerName(String customerName) {
            this.customerName = customerName;
        }

        public Integer getSeats() {
            return seats;
        }

        public void setSeats(Integer seats) {
            this.seats = seats;
        }

        public LocalDate getArrivalDate() {
            return arrivalDate;
        }

        public void setArrivalDate(LocalDate arrivalDate) {
            this.arrivalDate = arrivalDate;
        }

        public LocalDate getDepartureDate() {
            return departureDate;
        }

        public void setDepartureDate(LocalDate departureDate) {
            this.departureDate = departureDate;
        }
    }

    static final class BookingValidator implements Validator {

        @Override
        public boolean supports(Class<?> clazz) {
            return BookingForm.class.isAssignableFrom(clazz);
        }

        @Override
        public void validate(Object target, Errors errors) {
            BookingForm form = (BookingForm) target;

            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "customerName", "booking.customerName.required");

            Integer seats = form.getSeats();
            if (seats == null) {
                errors.rejectValue(
                        "seats",
                        "booking.seats.required",
                        "Vui lòng nhập số chỗ.");
            } else if (seats < 1 || seats > 8) {
                errors.rejectValue(
                        "seats",
                        "booking.seats.range",
                        new Object[] {1, 8},
                        "Số chỗ phải từ 1 đến 8.");
            }

            LocalDate arrival = form.getArrivalDate();
            LocalDate departure = form.getDepartureDate();
            if (arrival != null && departure != null
                    && departure.isBefore(arrival)) {
                errors.reject(
                        "booking.dates.order",
                        "Ngày rời đi không được trước ngày đến.");
            }
        }
    }

    public static void main(String[] args) {
        BookingForm form = new BookingForm();
        form.setCustomerName("   ");
        form.setSeats(0);
        form.setArrivalDate(LocalDate.of(2025, 6, 12));
        form.setDepartureDate(LocalDate.of(2025, 6, 10));

        BindingResult result =
                new BeanPropertyBindingResult(form, "bookingForm");

        Validator validator = new BookingValidator();
        if (!validator.supports(form.getClass())) {
            throw new IllegalArgumentException("Unsupported target type");
        }

        validator.validate(form, result);

        System.out.println("hasErrors=" + result.hasErrors());
        System.out.println("errorCount=" + result.getErrorCount());

        for (FieldError fieldError : result.getFieldErrors()) {
            System.out.println("FIELD " + fieldError.getField()
                    + ": " + fieldError.getCode());
        }
        for (ObjectError objectError : result.getGlobalErrors()) {
            System.out.println("OBJECT " + objectError.getCode());
        }
    }
}
~~~

Kết quả stdout chính xác của ví dụ, với các library Spring Framework 6.x tương thích:

~~~text
hasErrors=true
errorCount=3
FIELD customerName: booking.customerName.required
FIELD seats: booking.seats.range
OBJECT booking.dates.order
~~~

Giải thích từng bước:

1. `BeanPropertyBindingResult(form, "bookingForm")` tạo đối tượng thu thập lỗi cho form có tên `bookingForm`. Nó triển khai `Errors`, nên có thể truyền cho `validate()`.
2. Chuỗi `"   "` làm `rejectIfEmptyOrWhitespace` ghi một `FieldError` cho `customerName`.
3. `seats=0` nằm ngoài khoảng 1–8, nên ghi một `FieldError` khác cho `seats`.
4. `departureDate` sớm hơn `arrivalDate`, nên ghi một `ObjectError` bằng `reject`.
5. `getFieldErrors()` trả hai lỗi field, `getGlobalErrors()` trả một lỗi toàn object; tổng `getErrorCount()` là 3.

Các giá trị trên là mã kỹ thuật, vì chương trình in `getCode()`. Khi kết hợp `MessageSource`, cùng một lỗi có thể cho thông báo tiếng Việt/tiếng Anh theo locale; việc dịch không làm thay đổi cách `validate()` ghi lỗi.

Có thể chạy trong ứng dụng Maven chứa Spring như sau (sau khi đặt file đúng đường dẫn và thêm `spring-context` vào dependencies):

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=BookingDemo
~~~

Lệnh dùng Maven/Java đã cài đặt và cần dependency Spring trên classpath. Đây **không phải mã chạy bằng `javac BookingDemo.java` đơn thuần**, bởi `Errors`, `Validator` và `BeanPropertyBindingResult` nằm trong thư viện Spring.

## 6. Ai cung cấp `Errors` khi gọi `validate()`?

### 6.1. Gọi trực tiếp trong service hoặc bài thử

Chính bên gọi có thể khởi tạo `BeanPropertyBindingResult` như ví dụ trên, rồi gọi `validator.validate(form, result)`. Cách này hữu ích khi cần kiểm tra một object độc lập, chưa qua HTTP hoặc bước binding.

Lưu ý: nếu tự gọi `validate()`, chính bạn phải xử lý `result.hasErrors()`. Spring **không tự chuyển lỗi thành exception hoặc response** ở luồng gọi thủ công này.

### 6.2. Qua `DataBinder`

`DataBinder` quản lý việc binding và có một `BindingResult` đi kèm. Bạn đăng ký validator rồi yêu cầu binder chạy validation:

~~~java
BookingDemo.BookingForm form = new BookingDemo.BookingForm();
form.setCustomerName("   ");
form.setSeats(0);

DataBinder binder = new DataBinder(form, "bookingForm");
binder.addValidators(new BookingDemo.BookingValidator());
binder.validate();

BindingResult result = binder.getBindingResult();
System.out.println(result.hasErrors()); // true
~~~

Đoạn này minh họa trong **cùng project** với `BookingDemo`; cần import `org.springframework.validation.DataBinder` và `org.springframework.validation.BindingResult`. `binder.validate()` gọi các validator đã đăng ký; lỗi được thêm vào `binder.getBindingResult()`. Khi có property values từ request, binder có thể thực hiện binding trước validation; các lỗi conversion cũng có thể tồn tại trong cùng `BindingResult`.

Có thể dùng `setValidator(...)` để đặt một validator, hoặc `addValidators(...)` để bổ sung nhiều validator. Trước khi đăng ký với binder, bảo đảm `supports(target.getClass())` phù hợp; nếu validator không hỗ trợ kiểu target, quá trình cấu hình/kiểm tra có thể thất bại. Nếu binder đã có validator (chẳng hạn bộ kiểm tra Bean Validation), cân nhắc `addValidators` để giữ các quy tắc đang có.

### 6.3. Qua Spring MVC: controller nhận `BindingResult`

Để Spring MVC dùng custom `Validator` cho model attribute, cấu hình ở `@InitBinder` rồi đánh dấu đối tượng cần validation. Ví dụ sau là **mã tích hợp**: tách `BookingForm` và `BookingValidator` ở mục 5 thành các class độc lập trong cùng package, rồi dùng trong controller.

~~~java
@Controller
class BookingController {

    private final BookingValidator bookingValidator;

    BookingController(BookingValidator bookingValidator) {
        this.bookingValidator = bookingValidator;
    }

    @InitBinder("bookingForm")
    void initBookingBinder(WebDataBinder binder) {
        binder.addValidators(bookingValidator);
    }

    @PostMapping("/bookings")
    String submit(
            @Validated @ModelAttribute("bookingForm") BookingForm form,
            BindingResult errors,
            Model model) {

        if (errors.hasErrors()) {
            model.addAttribute("validationErrors", errors.getAllErrors());
            return "booking-form";
        }

        return "redirect:/bookings/success";
    }
}
~~~

Các type/annotation của đoạn tích hợp thuộc Spring MVC: `org.springframework.stereotype.Controller`, `org.springframework.web.bind.annotation.InitBinder`, `PostMapping`, `ModelAttribute`, `org.springframework.web.bind.WebDataBinder`, `org.springframework.validation.annotation.Validated`, `BindingResult` và `org.springframework.ui.Model`. `BookingValidator` phải là Spring bean hoặc được tạo/đăng ký phù hợp để inject.

**Điều kiện cần kiểm tra:**

- `@Validated` trên model attribute là tín hiệu yêu cầu validation sau binding; ở các trường hợp phổ biến, `@Valid` từ Jakarta cũng kích hoạt cơ chế validation tương ứng. Không chỉ khai báo `@InitBinder` rồi giả định mọi request sẽ được validate.
- `BindingResult errors` cần nằm **ngay sau đối số `BookingForm form`** mà nó phục vụ. Nếu không có `BindingResult` ở vị trí phù hợp, luồng lỗi của Spring MVC có thể chuyển sang exception thay vì đi vào nhánh hiển thị lại form.
- `@InitBinder("bookingForm")` giới hạn cấu hình này cho model attribute có tên `bookingForm`. Tên phải khớp `@ModelAttribute("bookingForm")`.
- `BindingResult` có thể chứa cả lỗi binding/conversion lẫn lỗi do custom validator ghi. Controller nên sử dụng kết quả tổng hợp.
- Với form trả lại view, template cần hiển thị cả `getFieldErrors()` và `getGlobalErrors()` theo cách phù hợp, đồng thời escape nội dung người dùng nhập.

Nếu muốn **gọi thủ công** ngay trong handler, có thể dùng `bookingValidator.validate(form, errors)` rồi kiểm tra `errors.hasErrors()`. Cách này chủ động hơn nhưng phải tránh vô tình gọi validation hai lần khi đã bật validation tự động qua `@Validated`/`@Valid`.

## 7. Đọc chính xác dữ liệu lỗi đã ghi

Một `FieldError` có thể cung cấp:

~~~java
FieldError fieldError = result.getFieldError("seats");
if (fieldError != null) {
    String objectName = fieldError.getObjectName(); // "bookingForm"
    String field = fieldError.getField();           // "seats"
    String errorCode = fieldError.getCode();        // "booking.seats.range"
    String[] candidates = fieldError.getCodes();   // các mã được phân giải
    Object rejected = fieldError.getRejectedValue();
    boolean conversionFailed = fieldError.isBindingFailure();
}
~~~

`getCode()` là một mã lỗi chính, còn `getCodes()` có thể chứa **nhiều ứng viên** phục vụ tra thông báo. `getRejectedValue()` phản ánh giá trị bị từ chối trong ngữ cảnh binding/validation, nhưng **không nên ghi trực tiếp vào log hoặc trả client** nếu có mật khẩu, token hay thông tin cá nhân. `isBindingFailure()` giúp nhận biết lỗi xuất phát từ quá trình binding thay vì lỗi business validation do `rejectValue()` thêm vào.

Một `ObjectError` có `getObjectName()`, `getCode()`, `getCodes()` và `getDefaultMessage()`, nhưng không có field hay rejected value. Vì thế muốn xuất một response thống nhất, thường phân nhánh theo `instanceof FieldError` thay vì ép mọi lỗi thành field error.

Ví dụ mô hình JSON do ứng dụng có thể tự xây dựng:

~~~json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {"field": "customerName", "code": "booking.customerName.required"},
    {"field": "seats", "code": "booking.seats.range"},
    {"field": null, "code": "booking.dates.order"}
  ]
}
~~~

Đây là **hình dạng response do ứng dụng định nghĩa**, không phải cấu trúc JSON mà `Errors` tự gửi ra. Việc chuyển `Errors` thành HTTP response thuộc trách nhiệm controller/exception handler.

## 8. Ánh xạ mã lỗi thành thông báo hiển thị

`rejectValue(...)` và `reject(...)` **lưu mã lỗi và default message**, chứ không tự xuất câu đã dịch. Bên trình bày có thể gọi `MessageSource` với chính `FieldError` hoặc `ObjectError` để thử tuần tự các mã đã phân giải:

~~~java
for (ObjectError error : result.getAllErrors()) {
    String userMessage = messageSource.getMessage(error, locale);
    // Dùng userMessage trong view hoặc response.
}
~~~

Đây là đoạn tích hợp, cần một bean `MessageSource`, một `Locale` tương ứng request và imports Spring. Một số key resource bundle ví dụ:

~~~properties
booking.customerName.required=Vui lòng nhập tên khách.
booking.seats.required=Vui lòng nhập số chỗ.
booking.seats.range=Số chỗ phải từ {0} đến {1}.
booking.dates.order=Ngày rời đi không được trước ngày đến.
~~~

Với lỗi `seats`, arguments `{1, 8}` được truyền từ `rejectValue` vào thông báo. Không nối message bằng tay trong validator; để resolver và bundle đảm nhiệm bản dịch và lựa chọn fallback. Khi dùng `MessageFormat`, chú ý cú pháp placeholder và dấu nháy đơn trong thông báo.

Có thể dùng key tổng quát hoặc key theo tên object + field để phân biệt câu chữ ở các màn hình. Kết quả dịch và cơ chế `MessageCodesResolver` không thay đổi nguyên tắc chính: **validator chỉ đăng ký lỗi; tầng trình bày chọn câu hiển thị**.

## 9. Lỗi nested object và nhiều validator

Nếu object chứa object con như `bookingForm.guest.address`, field path có thể dùng ký pháp dot, ví dụ `"guest.address.city"`, với điều kiện cấu trúc target và cơ chế binding hỗ trợ. Khi gọi validator chuyên trách cho object con, có thể dùng nested path của `Errors`:

~~~java
try {
    errors.pushNestedPath("guest");
    ValidationUtils.invokeValidator(guestValidator, form.getGuest(), errors);
} finally {
    errors.popNestedPath();
}
~~~

Đây là đoạn minh họa trong một validator lớn, giả định `form.getGuest()` khác `null` và `guestValidator.supports(...)` đúng. Khi nested path đang là `guest`, lỗi field `"email"` từ validator con được gắn thành `"guest.email"`. Phải phục hồi path trong `finally` để các lỗi tiếp theo không bị gắn sai tiền tố. Nếu object con `null`, hãy xử lý quy tắc thiếu object con trước khi gọi validator của nó.

**Nhiều validator có thể cùng ghi vào một `BindingResult`.** Đừng xóa hoặc tạo lại collector bên trong một validator: thao tác đó có thể khiến mất các lỗi binding đã tồn tại hoặc các lỗi từ validator khác. Mỗi validator nên chỉ thêm các lỗi thuộc trách nhiệm của nó.

## 10. Các tình huống lỗi thường gặp và cách kiểm tra

| Dấu hiệu | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `validate()` không được gọi | Chỉ implements interface, chưa đăng ký/gọi, hoặc thiếu tín hiệu validation ở controller | Cấu hình `DataBinder`/`@InitBinder` và `@Validated`/`@Valid` đúng ngữ cảnh, hoặc gọi trực tiếp |
| `ClassCastException` ở đầu `validate()` | Validator được dùng cho target sai kiểu | Cài `supports()` nhất quán, dùng validator đúng model |
| Exception khi `rejectValue("field", ...)` | Field không tồn tại hoặc đường dẫn nested không hợp lệ trong đối tượng/binder | Kiểm tra JavaBean property, tên field thực tế và nested path |
| Form có lỗi nhưng không hiển thị | Controller/view chỉ đọc một loại lỗi hoặc sai tên field | Xem `hasErrors()`, `getFieldErrors()`, `getGlobalErrors()` |
| Lỗi từ conversion bị lẫn với validation | Binder và validator cùng ghi vào một `BindingResult` | Phân biệt `FieldError.isBindingFailure()` và mã lỗi như `typeMismatch` |
| Cùng một vi phạm xuất hiện hai lần | Custom validator bị gọi cả tự động lẫn thủ công, hoặc nhiều validator trùng quy tắc | Kiểm tra đường gọi và chỉ đăng ký quy tắc ở nơi cần |
| Field có giá trị `null` gây lỗi trong điều kiện | Dereference trước khi kiểm tra `null` | Kiểm tra bắt buộc trước; dùng nhánh riêng cho so sánh khoảng |
| Lỗi field bị gắn vào object con sai | `pushNestedPath` không được `popNestedPath` | Dùng cặp push/pop trong `try/finally` |
| Không hiển thị được thông báo bản địa hóa | Thiếu key bundle, sai tên object/field hoặc thiếu locale phù hợp | Kiểm tra `error.getCodes()`, `MessageSource` và fallback |
| Log chứa dữ liệu nhạy cảm | In toàn bộ `BindingResult` hoặc `getRejectedValue()` | Chỉ log mã lỗi, field không nhạy cảm và thông tin đã lọc |

**Tự kiểm thử ba trường hợp trọng yếu:**

1. **Input hợp lệ:** `customerName="An"`, `seats=2`, ngày rời đi sau ngày đến → `errors.hasErrors() == false` và `getErrorCount() == 0`.
2. **Nhiều lỗi field + object:** dữ liệu trong `BookingDemo` → đúng 2 `FieldError` và 1 `ObjectError`, không có exception do vi phạm nghiệp vụ.
3. **Conversion error trước validation:** gửi `seats=abc` vào form dùng `Integer` → binder có thể thêm `typeMismatch`; custom validator không được giả định mọi field đã chuyển kiểu thành công. Dùng `BindingResult` tổng hợp để hiển thị đúng nguồn lỗi.

Khi viết unit test với Spring Test hoặc JUnit, có thể tạo `BeanPropertyBindingResult` trực tiếp, gọi `validate` rồi assert `hasFieldErrors("seats")`, `getGlobalErrorCount()` và mã lỗi. Việc test ở mức object giúp bắt lỗi quy tắc mà không phải khởi động server.

## 11. Checklist khi triển khai

- `supports()` xác định đúng kiểu target; `validate()` kiểm tra object và gọi `rejectValue` cho field, `reject` cho vi phạm cấp object.
- Truyền cùng một `Errors`/`BindingResult` xuyên suốt bước binding và validation; không làm mất lỗi đã có.
- Phân biệt kiểm tra thiếu dữ liệu, sai khoảng giá trị, ràng buộc giữa field và lỗi chuyển kiểu; có kiểm tra `null` trước khi so sánh.
- Controller chỉ xử lý tiếp khi `!errors.hasErrors()`; khi có lỗi, hiển thị/trả đủ lỗi field và global.
- Mã lỗi ổn định, message đọc được, dữ liệu nhạy cảm không bị lộ; kiểm thử cả input hợp lệ và nhiều vi phạm đồng thời.

Tài liệu tham khảo chính thức: [Validation Using Spring’s Validator Interface](https://docs.spring.io/spring-framework/reference/core/validation/validator.html) và [Java Bean Validation – Configuring a DataBinder](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html).
