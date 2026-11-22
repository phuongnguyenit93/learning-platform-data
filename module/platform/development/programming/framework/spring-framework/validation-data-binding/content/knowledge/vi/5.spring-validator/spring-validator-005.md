# Phân biệt lỗi một trường với lỗi toàn đối tượng trong Spring Validator

## 1. Hai loại lỗi trả lời hai câu hỏi khác nhau

Trong ứng dụng Spring, khi kiểm tra một form hoặc một đối tượng nghiệp vụ, không phải lỗi nào cũng thuộc về một thuộc tính riêng lẻ. Ví dụ người dùng đặt phòng với các trường `guestName`, `checkIn` và `checkOut`:

- `guestName` chỉ chứa khoảng trắng: lỗi thuộc chính trường `guestName`.
- `checkOut` không nằm sau `checkIn`: dữ liệu **kết hợp của cả đơn đặt phòng** không hợp lệ; có thể ghi lỗi toàn đối tượng để hiển thị thông báo chung.
- Nếu `checkIn` bị thiếu: lỗi có thể gắn với trường `checkIn`, dù hệ thống cần ngày này để tiếp tục kiểm tra quy tắc giữa hai ngày.

Spring Validation biểu diễn sự khác biệt bằng hai loại chính:

| | Lỗi một trường (*field error*) | Lỗi toàn đối tượng (*global/object error*) |
| --- | --- | --- |
| Câu hỏi | Trường nào của đối tượng không hợp lệ? | Quy tắc chung nào của đối tượng không được thỏa mãn? |
| API ghi lỗi | `Errors.rejectValue(field, code, ...)` | `Errors.reject(code, ...)` |
| Đối tượng kết quả | `FieldError` | `ObjectError` |
| Có tên thuộc tính? | Có: `getField()` | Không có một trường cụ thể; chỉ có `getObjectName()` |
| Tập kết quả | `getFieldErrors()` | `getGlobalErrors()` |
| Ví dụ | Tên khách trống, số lượng âm, sai kiểu của trường ngày | Khoảng ngày không hợp lệ, tổng phân bổ không bằng 100%, trạng thái nhiều trường mâu thuẫn |
| Cách trình bày thường gặp | Bên cạnh input tương ứng | Phía trên form hoặc ở phần lỗi chung |

Cả hai loại đều là **validation errors trong mô hình `org.springframework.validation.Errors`**, thường được thu thập vào `BindingResult`. Không nên hiểu "lỗi toàn đối tượng" là một exception làm ứng dụng sập. Đó là một lỗi có cấu trúc, được trả về để ứng dụng quyết định hiển thị hoặc xử lý.

**Quy tắc thực dụng:** ghi field error nếu người dùng có thể xác định rõ một input cần sửa; ghi global error khi không thể hoặc không nên quy trách nhiệm cho một input cụ thể. Một quy tắc phụ thuộc nhiều trường **không bắt buộc** phải ghi global error: cách gắn lỗi là quyết định thiết kế của validator.

## 2. Những interface và class Spring dùng

Spring cung cấp hợp đồng kiểm tra đối tượng:

```java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
```

Đây là cấu trúc rút gọn của `org.springframework.validation.Validator`, chỉ dùng để giải thích. Trong phương thức `validate`, validator đọc `target` rồi gọi một trong hai hướng:

```java
errors.rejectValue("guestName", "guest.required");
errors.reject("booking.invalidDates");
```

- `rejectValue("guestName", "guest.required")` đăng ký một `FieldError` có field là `guestName`. Mã `guest.required` được Spring sử dụng để tra thông điệp từ `MessageSource`.
- `reject("booking.invalidDates")` đăng ký một `ObjectError` cho đối tượng đang được validate, không gắn với field cụ thể.
- Có overload nhận `errorArgs` và `defaultMessage` để cung cấp tham số và thông điệp dự phòng, chẳng hạn `reject("booking.invalidDates", "Ngày trả phải sau ngày nhận")`.
- `ValidationUtils.rejectIfEmptyOrWhitespace(errors, "guestName", "guest.required")` là tiện ích Spring để thêm field error khi giá trị null, rỗng hoặc chỉ chứa khoảng trắng.

Khi dùng `DataBinder` hoặc Spring MVC, kết quả thường là `BindingResult`. Các phương thức đáng nhớ:

```text
errors.hasErrors()
errors.getErrorCount()
errors.getAllErrors()         -> List<ObjectError>, gồm cả FieldError
errors.hasFieldErrors()
errors.getFieldErrors()       -> List<FieldError>
errors.getFieldErrors("guestName")
errors.getFieldError("guestName")
errors.getFieldErrorCount()
errors.hasGlobalErrors()
errors.getGlobalErrors()      -> List<ObjectError>, chỉ lỗi toàn đối tượng
errors.getGlobalError()
errors.getGlobalErrorCount()
```

`FieldError` **kế thừa** `ObjectError`, do đó danh sách `getAllErrors()` chứa được cả hai kiểu. Nhưng `getGlobalErrors()` đã lọc ra lỗi toàn đối tượng; đừng tự coi mọi `ObjectError` trong `getAllErrors()` đều là global error. Nếu muốn trình bày riêng, lấy `getFieldErrors()` và `getGlobalErrors()`.

Các phần tử lỗi có những thuộc tính chung:

- `getObjectName()`: tên object được Spring đặt khi binding, chẳng hạn `booking`; **không phải** tên class Java nhất thiết.
- `getCode()`: mã lỗi chính do validator truyền vào, ví dụ `guest.required`.
- `getCodes()`: dãy mã ưu tiên dùng để tra thông điệp, có thể gồm biến thể theo object/field/type.
- `getArguments()`, `getDefaultMessage()`: đối số và thông điệp dự phòng, tùy cách khai báo lỗi.
- Riêng `FieldError.getField()`: đường dẫn thuộc tính liên quan.
- Riêng `FieldError.getRejectedValue()`: giá trị đã bị từ chối nếu Spring lưu được.
- Riêng `FieldError.isBindingFailure()`: cho biết lỗi phát sinh trong binding (chẳng hạn sai chuyển đổi kiểu) hay không; một lỗi do `rejectValue` trong validator thông thường không phải binding failure.

Không mặc định `getDefaultMessage()` luôn có nội dung: nếu khi `reject`/`rejectValue` chỉ truyền error code, có thể cần `MessageSource` để có thông điệp thân thiện.

## 3. Lỗi một trường: khi một thuộc tính có vấn đề

Ví dụ một form đăng ký cần có tên khách:

```java
@Override
public void validate(Object target, Errors errors) {
    ValidationUtils.rejectIfEmptyOrWhitespace(
        errors, "guestName", "guest.required"
    );
}
```

Khi `guestName` là `"   "`, helper sẽ đăng ký field error. Với `BindingResult result`, ta có thể lấy:

```java
FieldError error = result.getFieldError("guestName");
if (error != null) {
    System.out.println(error.getField());
    System.out.println(error.getCode());
}
```

Giả sử đã import `org.springframework.validation.FieldError` và validation được thực hiện trên đối tượng phù hợp, hai dòng được in là:

```text
guestName
guest.required
```

Lỗi trường có các đặc điểm đáng chú ý:

1. **Liên kết chính xác với input**: UI có thể hiển thị lỗi ngay cạnh `guestName` và đánh dấu trường này.
2. **Có thể có nhiều lỗi trên cùng một field**: `@NotBlank` và `@Size` hoặc các validator tự viết có thể tạo nhiều thông báo. `getFieldError("guestName")` chỉ lấy lỗi đầu; `getFieldErrors("guestName")` lấy danh sách.
3. **Có đường dẫn lồng nhau**: ví dụ `address.street`. Khi sử dụng `Errors.pushNestedPath(...)`, Spring tự tính đường dẫn hiện tại; validator cần hiểu tên thuộc tính thực tế.
4. **Không chỉ do constraint**: lỗi chuyển đổi giá trị khi binding, chẳng hạn nhập `"abc"` vào trường kiểu số, cũng thường được biểu diễn bằng `FieldError` với mã dạng `typeMismatch`.
5. **Không nhất thiết có giá trị đã từ chối trong output**: giá trị có thể nhạy cảm (mật khẩu, token, thông tin cá nhân). Tránh log hoặc gửi `getRejectedValue()` nguyên trạng.

Lỗi field do **binding/conversion** và lỗi field do **validation** có cùng loại kết quả nhưng nguồn gốc khác nhau. `isBindingFailure()` giúp phân biệt, đặc biệt khi thiết kế API error response.

## 4. Lỗi toàn đối tượng: khi một quy tắc chung bị vi phạm

Hãy xét form đặt phòng có hai ngày riêng lẻ đều là ngày hợp lệ, nhưng `checkOut` lại trước hoặc bằng `checkIn`. Vấn đề nằm ở **quan hệ giữa các giá trị**:

```java
Booking booking = (Booking) target;
if (booking.getCheckIn() != null
        && booking.getCheckOut() != null
        && !booking.getCheckOut().isAfter(booking.getCheckIn())) {
    errors.reject(
        "booking.invalidDates",
        "Ngày trả phòng phải sau ngày nhận phòng"
    );
}
```

`reject(...)` không cần field name. `BindingResult.getGlobalErrors()` sẽ chứa một `ObjectError` có `getObjectName()` tương ứng với object được bind; mã lỗi là `booking.invalidDates`.

Những tình huống thường hợp lý để dùng global error:

- Đơn đặt phòng có `checkIn` và `checkOut` không tạo thành khoảng thời gian hợp lệ.
- Một biểu mẫu yêu cầu chọn ít nhất một trong nhiều phương thức liên hệ.
- Một lệnh chuyển tiền có nguồn, đích và hạn mức dẫn đến kết hợp không hợp lệ.
- Một cấu hình có nhiều tùy chọn riêng lẻ hợp lệ nhưng xung đột khi bật cùng nhau.
- Một đơn hàng có tổng phân bổ tỷ lệ từ nhiều dòng không bằng 100%.

Cần phân biệt **lỗi tổng thể** với **thông báo ngoại lệ ứng dụng**. Global error là dữ liệu validation; controller có thể hiển thị form cùng thông điệp và cho phép người dùng sửa. Không cần ném exception chỉ để diễn tả một lỗi validation thông thường.

### Luật nhiều trường có thể gắn với một field

Nếu UI cho phép người dùng sửa chủ yếu `checkOut`, bạn cũng có thể chủ động chọn field error:

```java
errors.rejectValue(
    "checkOut",
    "booking.invalidDates",
    "Ngày trả phòng phải sau ngày nhận phòng"
);
```

Điều này **vẫn là luật phụ thuộc hai trường** nhưng được ghi thành `FieldError` của `checkOut`. Vì vậy không thể quyết định loại lỗi chỉ bằng cách đếm số trường mà một quy tắc đọc. Nên cân nhắc vị trí hướng dẫn người dùng sửa và cách API/frontend tiêu thụ lỗi.

## 5. Ví dụ hoàn chỉnh Java 17: tạo cả FieldError và ObjectError

Ví dụ sau dùng **Spring Framework `Validator` và `DataBinder`**, không cần Spring Boot web server hoặc Jakarta Validation provider. Java 17+ và Maven là đủ. Điều đó cho thấy hai loại lỗi là một phần của mô hình validation riêng của Spring.

Cấu trúc:

```text
spring-error-kinds/
├── pom.xml
└── src/main/java/demo/FieldVsGlobalErrorDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-error-kinds</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/FieldVsGlobalErrorDemo.java`:

```java
package demo;

import java.time.LocalDate;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public class FieldVsGlobalErrorDemo {

    public static final class Booking {
        private final String guestName;
        private final LocalDate checkIn;
        private final LocalDate checkOut;

        public Booking(String guestName, LocalDate checkIn,
                       LocalDate checkOut) {
            this.guestName = guestName;
            this.checkIn = checkIn;
            this.checkOut = checkOut;
        }

        public String getGuestName() {
            return guestName;
        }

        public LocalDate getCheckIn() {
            return checkIn;
        }

        public LocalDate getCheckOut() {
            return checkOut;
        }
    }

    public static final class BookingValidator implements Validator {

        @Override
        public boolean supports(Class<?> type) {
            return Booking.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Booking booking = (Booking) target;

            // Một trường không hợp lệ -> FieldError.
            ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "guestName", "guest.required"
            );

            // Khi thiếu ngày, báo đúng trường để người dùng sửa.
            if (booking.getCheckIn() == null) {
                errors.rejectValue("checkIn", "checkIn.required");
            }
            if (booking.getCheckOut() == null) {
                errors.rejectValue("checkOut", "checkOut.required");
            }

            // Quan hệ giữa hai trường không hợp lệ -> ObjectError.
            // Chỉ so sánh khi đã có cả hai ngày.
            if (booking.getCheckIn() != null
                    && booking.getCheckOut() != null
                    && !booking.getCheckOut()
                        .isAfter(booking.getCheckIn())) {
                errors.reject(
                    "booking.invalidDates",
                    "Ngày trả phải sau ngày nhận"
                );
            }
        }
    }

    private static void show(String label, Booking booking) {
        DataBinder binder = new DataBinder(booking, "booking");
        binder.addValidators(new BookingValidator());
        binder.validate();

        BindingResult result = binder.getBindingResult();

        System.out.println(label);
        for (FieldError error : result.getFieldErrors()) {
            System.out.println("FIELD " + error.getField()
                    + " -> " + error.getCode());
        }
        for (ObjectError error : result.getGlobalErrors()) {
            System.out.println("GLOBAL " + error.getObjectName()
                    + " -> " + error.getCode());
        }
        System.out.println("counts: field="
                + result.getFieldErrorCount()
                + ", global=" + result.getGlobalErrorCount()
                + ", all=" + result.getErrorCount());
    }

    public static void main(String[] args) {
        show("Invalid", new Booking(
            "   ",
            LocalDate.of(2026, 11, 15),
            LocalDate.of(2026, 11, 14)
        ));

        show("Valid", new Booking(
            "Lan",
            LocalDate.of(2026, 11, 14),
            LocalDate.of(2026, 11, 15)
        ));
    }
}
```

Từ thư mục `spring-error-kinds`, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.FieldVsGlobalErrorDemo
```

Các dòng do chương trình in (thông báo logging từ thư viện, nếu có, không được tính):

```text
Invalid
FIELD guestName -> guest.required
GLOBAL booking -> booking.invalidDates
counts: field=1, global=1, all=2
Valid
counts: field=0, global=0, all=0
```

Diễn giải từng bước:

1. `DataBinder` quản lý đối tượng `Booking` và đặt tên object là `booking`. Đây là tên được trả về trong `ObjectError.getObjectName()`.
2. `binder.addValidators(new BookingValidator())` đăng ký validator có `supports(Booking.class)` trả `true`.
3. `binder.validate()` yêu cầu Spring chạy validator; đối tượng lỗi được truyền vào `validate`.
4. `guestName` toàn khoảng trắng nên `rejectIfEmptyOrWhitespace` tạo `FieldError`. Lỗi xuất hiện qua `getFieldErrors()` với field `guestName`.
5. `checkOut` trước `checkIn` nên `reject` tạo `ObjectError` toàn đối tượng, được trả qua `getGlobalErrors()`.
6. `getErrorCount()` là tổng hai loại: `1 + 1 = 2`. Khi booking hợp lệ, tất cả danh sách rỗng.

Đây là ví dụ **tạo dữ liệu Java rồi gọi validation**; nó không thực hiện web binding từ một HTTP request. Khi một request thực sự đi qua Spring MVC, hệ thống có thể ghi thêm field error ngay trong bước binding/conversion trước khi các luật validator được xét.

### Thử đổi cách gắn lỗi

Hãy đổi duy nhất dòng:

```java
errors.reject(
    "booking.invalidDates",
    "Ngày trả phải sau ngày nhận"
);
```

thành:

```java
errors.rejectValue(
    "checkOut", "booking.invalidDates",
    "Ngày trả phải sau ngày nhận"
);
```

Chương trình lúc này sẽ có **hai field errors** (ở `guestName` và `checkOut`), **không có global error**, trong ca `Invalid`. Mã rule vẫn giống nhau; phân loại kết quả thay đổi do API ghi lỗi được lựa chọn. Đây là cách đơn giản nhất để quan sát bản chất của hai loại.

## 6. Kiểm tra kết quả mà không nhầm hai loại lỗi

Giả sử biến `result` có kiểu `BindingResult`:

```java
boolean anyError = result.hasErrors();
boolean fieldError = result.hasFieldErrors();
boolean globalError = result.hasGlobalErrors();

int total = result.getErrorCount();
int fieldCount = result.getFieldErrorCount();
int globalCount = result.getGlobalErrorCount();
```

Các API trên cho phép xây dựng phần xử lý lỗi mà không cần đọc chuỗi `toString()` của `BindingResult`.

Ví dụ cách tách dữ liệu thành hai nhóm trình bày:

```java
for (FieldError field : result.getFieldErrors()) {
    String property = field.getField();
    String code = field.getCode();
    // Đưa thông báo đến input tương ứng.
}

for (ObjectError global : result.getGlobalErrors()) {
    String code = global.getCode();
    // Đưa thông báo vào khu vực lỗi chung của form.
}
```

Đây là các đoạn minh họa đặt trong method đã có `result`; không phải chương trình chạy độc lập.

Nếu chỉ dùng:

```java
for (ObjectError error : result.getAllErrors()) {
    System.out.println(error.getCode());
}
```

bạn sẽ có **toàn bộ lỗi**, nhưng mất ý nghĩa phân vùng nếu không kiểm tra `error instanceof FieldError`. Không được gọi `getField()` trực tiếp trên biến khai báo là `ObjectError`. Trong thực tế, hai phương thức `getFieldErrors()` và `getGlobalErrors()` thường rõ ràng hơn.

### FieldError không phải lúc nào cũng là lỗi do validator tự viết

Trong Spring MVC, khi người dùng nhập `"abc"` vào trường `age` kiểu `Integer`, hệ thống có thể tạo `FieldError` có `isBindingFailure() == true` ngay trong quá trình chuyển đổi dữ liệu. Một lỗi `@Min(18)` hoặc `errors.rejectValue("age", ...)` xảy ra khi giá trị kiểu số đã được tạo và được kiểm tra; thông thường `isBindingFailure() == false`.

Vì vậy khi hiển thị lỗi, nên dựa trên API và error code để có thông điệp phù hợp; không suy ra rằng **mọi** `FieldError` đều được sinh ra từ `Validator.validate`.

## 7. Mã lỗi, thông điệp và cách Spring phân giải

Một lỗi có **error code** và có thể có **default message**. Không nên lưu sẵn cả câu tiếng Việt vào mọi nơi gọi validator nếu ứng dụng cần đa ngôn ngữ; ưu tiên mã lỗi ổn định và cấu hình thông điệp.

Ví dụ một đoạn validator:

```java
errors.rejectValue(
    "guestName", "guest.required",
    "Tên khách không được bỏ trống"
);
errors.reject(
    "booking.invalidDates",
    "Ngày trả phải sau ngày nhận"
);
```

Spring có `MessageCodesResolver` để sinh các biến thể mã. Với object name `booking` và field `guestName`, resolver mặc định có thể thử các khóa theo độ cụ thể giảm dần, ví dụ:

```properties
guest.required.booking.guestName=Tên khách không được để trống
guest.required.guestName=Vui lòng nhập tên khách
guest.required=Trường này là bắt buộc

booking.invalidDates.booking=Ngày trả phải sau ngày nhận
booking.invalidDates=Khoảng ngày không hợp lệ
```

Các dòng trên là ví dụ nội dung `messages.properties` trong một ứng dụng Spring đã cấu hình `MessageSource` phù hợp. Spring chọn thông điệp qua hệ thống message codes; thứ tự và dạng code thực tế phụ thuộc resolver và ngữ cảnh. Đừng phụ thuộc vào một chuỗi cụ thể mà không kiểm tra cấu hình đang sử dụng.

Điểm khác biệt:

- Field error có thể sinh mã chứa **tên object + tên field + kiểu field**, giúp dùng thông điệp riêng cho một input.
- Global error thường liên quan **tên object + mã quy tắc**, vì không có một field cụ thể.
- `error.getCode()` trả mã chính; `error.getCodes()` trả dãy mã đã được resolve. Hai phương thức phục vụ hai mục đích khác nhau.
- `error.getDefaultMessage()` là thông điệp dự phòng; UI nên cân nhắc `MessageSource`/`BindingResult` để hỗ trợ locale thay vì hiển thị nguyên error code.

Nếu API REST trả thông tin validation, có thể dùng một cấu trúc rõ ràng:

```json
{
  "fieldErrors": [
    {"field": "guestName", "code": "guest.required"}
  ],
  "globalErrors": [
    {"code": "booking.invalidDates"}
  ]
}
```

Đây là **định dạng API tự thiết kế**, không phải JSON response mặc định mà mọi ứng dụng Spring tự sinh ra. Backend có thể bổ sung message đã bản địa hóa và request correlation ID; nên tránh đưa trực tiếp rejected value nhạy cảm ra ngoài.

## 8. Khi tích hợp vào Spring MVC

Trong Spring MVC, `WebDataBinder` kế thừa cơ chế binding và validation. Một validator tùy biến có thể được thêm bằng `@InitBinder`; trong action, `BindingResult` được đặt **ngay sau** đối số được validate để controller xử lý lỗi tại chỗ.

Ví dụ khung code sau **chỉ minh họa controller**, giả sử ứng dụng đã có lớp JavaBean `BookingForm` với getter/setter và `BookingFormValidator` triển khai Spring `Validator` hỗ trợ chính kiểu `BookingForm`:

```java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@Controller
class BookingController {

    @InitBinder("bookingForm")
    void initBinder(WebDataBinder binder) {
        binder.addValidators(new BookingFormValidator());
    }

    @PostMapping("/bookings")
    String submit(
            @Validated @ModelAttribute("bookingForm") BookingForm form,
            BindingResult errors,
            Model model) {

        if (errors.hasErrors()) {
            model.addAttribute("fieldErrors", errors.getFieldErrors());
            model.addAttribute("globalErrors", errors.getGlobalErrors());
            return "booking-form";
        }

        // Lưu booking theo nghiệp vụ của ứng dụng.
        return "booking-success";
    }
}
```

Lưu ý cho ví dụ controller:

- `BookingForm` và `BookingFormValidator` cần được tự định nghĩa trong ứng dụng; đoạn này không thay thế chương trình độc lập ở mục 5.
- `@Validated` yêu cầu chạy validation tại entry point này; validator đã đăng ký qua `@InitBinder` được tham gia khi binder thực hiện validation.
- Tên `@InitBinder("bookingForm")` cần khớp tên model attribute cần cấu hình; `supports` phải đúng với loại đối tượng nhận được.
- Đặt `BindingResult` ngay sau `@ModelAttribute`. Nếu đặt sai vị trí, Spring có thể không liên kết kết quả như mong muốn và lỗi validation có thể đi qua hướng exception.
- Trang `booking-form` quyết định cách hiển thị. Với field error, hiển thị cạnh trường tương ứng; với global error, hiển thị vùng thông báo chung.

Nếu controller sử dụng Jakarta Validation (`@Valid`, `@NotBlank`, custom class-level constraint), Spring có thể chuyển `ConstraintViolation` thành lỗi trong `BindingResult` qua adapter `LocalValidatorFactoryBean`. Thông thường property-level violation trở thành field error và object-level violation không có property path trở thành global error. Tuy nhiên **đường dẫn thuộc tính của violation mới quyết định cách ánh xạ**: một class-level constraint tùy biến có thể tạo violation gắn vào field bằng cách xây dựng property node.

Do đó, đừng nhầm:

- `org.springframework.validation.FieldError`/`ObjectError` là **mô hình báo lỗi Spring**.
- `jakarta.validation.ConstraintViolation` là **mô hình kết quả Jakarta Validation**.
- Hai mô hình có thể được adapter kết nối, nhưng không phải cùng một class.

## 9. Chọn lỗi field hay lỗi global trong trường hợp khó

### Trường hợp A: Địa chỉ email sai định dạng

Quy tắc chỉ đọc `email`, có input tương ứng. Ghi `rejectValue("email", "email.invalid")` để người dùng sửa tại đúng ô.

### Trường hợp B: Ngày kết thúc phải sau ngày bắt đầu

Quy tắc đọc `startDate` và `endDate`. Nếu form thiết kế để người dùng sửa ngày kết thúc, gắn vào `endDate` bằng `rejectValue` có thể dễ hiểu. Nếu quy tắc diễn tả một khoảng thời gian tổng thể, ghi `reject("dateRange.invalid")` cũng hợp lý. Không có quy tắc framework bắt buộc mọi cross-field validation phải là global.

### Trường hợp C: Một trong hai kênh liên hệ bắt buộc

Nếu `phone` và `email` đều trống, ghi global error giúp diễn đạt yêu cầu "cung cấp ít nhất một cách liên hệ". Nếu giao diện muốn highlight cả hai field, có thể ghi hai field errors, nhưng nên tránh khiến người dùng hiểu nhầm cả hai trường đều bắt buộc.

### Trường hợp D: Mã giảm giá không hợp lệ với toàn đơn hàng

Nếu lỗi phát sinh do trạng thái đơn, tổng tiền và chính sách mã giảm giá, một global error có thể hợp lý. Nếu người dùng chỉ cần thay mã trong input `couponCode`, field error cũng có thể hữu ích. Thiết kế hướng dẫn người dùng sửa lỗi là yếu tố quyết định.

### Trường hợp E: Lỗi hệ thống hoặc database không sẵn sàng

Đây thường là **application/infrastructure failure**, không phải validation error của dữ liệu người dùng. Đừng ép thành `errors.reject("system.failure")` chỉ để tận dụng `BindingResult`; cần đường xử lý exception/phản hồi lỗi thích hợp.

Một checklist ngắn khi chọn:

1. Có xác định được **một field mà người dùng nên sửa** không?
2. Lỗi có mô tả **tính không hợp lệ của cả object hoặc tổ hợp thuộc tính** không?
3. UI và API sẽ trình bày lỗi ở vị trí nào để người dùng hiểu đúng?
4. Mã lỗi có ổn định và đủ rõ để localize/kiểm thử không?
5. Có nguy cơ lộ dữ liệu nhạy cảm từ `rejectedValue` hoặc thông điệp lỗi không?

## 10. Lỗi thường gặp

1. **Gọi `reject(...)` khi muốn tô đỏ một input.** Lỗi bị ghi thành global, không có `getField()` để chỉ ra input.
2. **Gọi `rejectValue(...)` với field name sai.** Đường dẫn phải tương ứng property mà Spring có thể truy cập; sai có thể dẫn tới lỗi truy cập property hoặc lỗi được gắn không đúng chỗ.
3. **Tưởng object-level rule bắt buộc tạo global error.** Luật nhiều trường có thể được gắn field nếu lựa chọn này giúp người dùng sửa đúng nơi.
4. **Chỉ gọi `getFieldErrors()` rồi kết luận form hợp lệ.** Có thể vẫn có global errors; dùng `hasErrors()` để xét tổng thể.
5. **Dùng `getAllErrors()` rồi cast mọi phần tử sang `FieldError`.** Danh sách còn chứa `ObjectError` thực sự; cast không kiểm tra có thể gây `ClassCastException`.
6. **Hiểu `getObjectName()` là tên thuộc tính gây lỗi.** Object name xác định target binding (ví dụ `booking`), không phải `guestName`.
7. **Trộn lỗi binding và lỗi validation.** Lỗi `typeMismatch` có thể được tạo trước validation; `FieldError.isBindingFailure()` cho thông tin hữu ích.
8. **Đặt `BindingResult` sai vị trí trong phương thức controller.** Spring MVC yêu cầu kết quả nằm sau đối số được bind/validate tương ứng nếu muốn xử lý tại chỗ.
9. **Chỉ hiển thị lỗi trường và bỏ lỗi global.** Các quy tắc tổng thể có thể bị che giấu khỏi người dùng.
10. **Hiển thị mã lỗi thô hoặc rejected value cho client.** Dùng `MessageSource` để dịch thông điệp; tránh đưa dữ liệu nhạy cảm ra log hoặc API.

## 11. Tự kiểm tra

1. `errors.rejectValue("quantity", "quantity.invalid")` tạo loại lỗi nào? Lấy danh sách tương ứng bằng API gì?
2. `errors.reject("order.totalMismatch")` khác thế nào? `getObjectName()` có nghĩa gì?
3. Vì sao `getAllErrors()` có thể trả cả `FieldError` dù kiểu khai báo phần tử là `ObjectError`?
4. Với hai trường `startDate` và `endDate` sai thứ tự, khi nào hợp lý gắn lỗi vào `endDate` thay vì tạo global error?
5. Người dùng nhập chữ vào ô số, Spring thường ghi lỗi thuộc loại nào và `isBindingFailure()` giúp gì?
6. Nếu `getFieldErrorCount() == 0` nhưng `getGlobalErrorCount() == 1`, `hasErrors()` sẽ trả kết quả gì?
7. Trong Spring MVC, phải đặt `BindingResult` ở đâu để xử lý lỗi của `@ModelAttribute` tại controller?

**Kết luận:** Field error chỉ ra *thuộc tính* có lỗi và thường được tạo bằng `rejectValue(...)`; global error diễn đạt *đối tượng hoặc quy tắc chung* không hợp lệ và được tạo bằng `reject(...)`. Cả hai đều nằm trong `BindingResult`. Khi xử lý và hiển thị, luôn kiểm tra cả hai nhóm và chọn cách gắn lỗi theo điều người dùng cần sửa.

## Tài liệu tham khảo

- Spring Framework — Validation, Data Binding, and Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation.html
- Spring Framework — Resolving Error Codes to Error Messages: https://docs.spring.io/spring-framework/reference/core/validation/error-code-resolution.html
- Spring Framework 6.1 — `Errors` interface: https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/validation/Errors.html
- Spring Framework — `FieldError` và `ObjectError`: https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/validation/FieldError.html và https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/validation/ObjectError.html
