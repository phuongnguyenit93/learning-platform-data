# Kiểm tra trực tiếp với `validateObject` từ Spring Framework 6.1

Khi đã có một đối tượng Java trong bộ nhớ và chỉ muốn kiểm tra các quy tắc của một **Spring `Validator`**, bạn không nhất thiết phải tạo `DataBinder` hay tự khởi tạo `Errors`. Từ **Spring Framework 6.1**, giao diện `org.springframework.validation.Validator` có phương thức mặc định:

~~~java
Errors validateObject(Object target);
~~~

Cách dùng cốt lõi:

~~~java
Errors errors = validator.validateObject(input);
if (errors.hasErrors()) {
    // Từ chối đầu vào và xử lý các lỗi đã ghi nhận.
}
~~~

Phương thức này gọi logic validation sẵn có, tạo và trả về một `Errors` mới để bạn có thể đọc kết quả ngay. Đây là lựa chọn gọn cho **kiểm tra một đối tượng độc lập sau khi đối tượng đã được tạo**, chẳng hạn trước khi chạy một use case. Nó không tự bind request, không tự chuyển chuỗi thành số và không thay cho toàn bộ vòng đời validation của Spring MVC.

## 1. Trước và sau Spring 6.1: thay đổi nằm ở đâu?

Giao diện `Validator` của Spring vốn có hai phương thức chính:

~~~java
boolean supports(Class<?> clazz);
void validate(Object target, Errors errors);
~~~

- `supports(Class<?>)` cho biết validator dành cho loại đối tượng nào.
- `validate(Object, Errors)` kiểm tra đối tượng, rồi gọi `errors.rejectValue(...)` cho lỗi trường hoặc `errors.reject(...)` cho lỗi toàn đối tượng.

Trước Spring 6.1, để kiểm tra trực tiếp một object ngoài cơ chế bind, thường phải tự cung cấp một `Errors`:

~~~java
// Cách truyền thống: tự tạo nơi lưu lỗi.
Errors errors = new BeanPropertyBindingResult(input, "input");
validator.validate(input, errors);

if (errors.hasErrors()) {
    // Xử lý lỗi.
}
~~~

Từ Spring 6.1, cách ngắn hơn là:

~~~java
// Spring Framework 6.1+.
Errors errors = validator.validateObject(input);

if (errors.hasErrors()) {
    // Xử lý lỗi.
}
~~~

Không cần thay đổi cách viết validator: việc triển khai `validate(Object, Errors)` vẫn là nền tảng. `validateObject` là **default method trên chính Spring `Validator`**, vì vậy validator hiện có có thể sử dụng trực tiếp khi chạy với phiên bản tương thích, miễn là logic validator thích hợp với kiểu `Errors` đơn giản mà phương thức cung cấp.

Về cơ chế, có thể hình dung logic mặc định của Spring 6.1 tương đương:

~~~java
default Errors validateObject(Object target) {
    Errors errors = new SimpleErrors(target);
    validate(target, errors);
    return errors;
}
~~~

Đây là mã minh họa cách ủy quyền đã được công bố trong API Spring, không phải một hàm cần tự chép vào dự án. `SimpleErrors` quản lý danh sách lỗi riêng cho một đối tượng ở mức cao nhất. **Mỗi lần gọi `validateObject` tạo một `Errors` mới** và chạy lại validator.

Một điểm quan trọng: phương thức mặc định **không tự gọi `supports(target.getClass())`** trước khi chuyển đối tượng sang `validate(target, errors)`. Người gọi vẫn phải chọn validator phù hợp cho loại object, hoặc sử dụng validator có cơ chế kiểm tra kiểu đầu vào.

## 2. Ví dụ đầy đủ chạy được với Java 17 và Spring 6.1

Ta kiểm tra một lịch đặt phòng họp có ba thuộc tính:

- `title` phải chứa ký tự không phải khoảng trắng;
- `startHour` trong khoảng từ 0 đến 23, `endHour` trong khoảng từ 1 đến 24;
- `startHour` phải nhỏ hơn `endHour`.

Hai nhóm quy tắc khác nhau sẽ tạo ra **field error** và **global error**. Ví dụ dùng factory `Validator.forInstanceOf(...)` (cũng có trong Spring 6.1) để viết validator theo kiểu cụ thể mà không cần lớp triển khai riêng.

Cấu trúc dự án:

~~~text
spring-direct-validation/
├── pom.xml
└── src/main/java/demo/DirectValidationDemo.java
~~~

Tạo tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-direct-validation</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.15</version>
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
                    <mainClass>demo.DirectValidationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tạo tệp `src/main/java/demo/DirectValidationDemo.java`:

~~~java
package demo;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public class DirectValidationDemo {

    public static final class MeetingSlot {
        private final String title;
        private final int startHour;
        private final int endHour;

        public MeetingSlot(String title, int startHour, int endHour) {
            this.title = title;
            this.startHour = startHour;
            this.endHour = endHour;
        }

        public String getTitle() {
            return title;
        }

        public int getStartHour() {
            return startHour;
        }

        public int getEndHour() {
            return endHour;
        }
    }

    private static final Validator SLOT_VALIDATOR =
            Validator.forInstanceOf(MeetingSlot.class, (slot, errors) -> {
                if (slot.getTitle() == null || slot.getTitle().isBlank()) {
                    errors.rejectValue(
                            "title", "title.required",
                            "Tiêu đề không được trống");
                }

                if (slot.getStartHour() < 0 || slot.getStartHour() > 23) {
                    errors.rejectValue(
                            "startHour", "startHour.range",
                            "Giờ bắt đầu phải từ 0 đến 23");
                }

                if (slot.getEndHour() < 1 || slot.getEndHour() > 24) {
                    errors.rejectValue(
                            "endHour", "endHour.range",
                            "Giờ kết thúc phải từ 1 đến 24");
                }

                if (slot.getStartHour() >= slot.getEndHour()) {
                    errors.reject(
                            "time.order",
                            "Giờ kết thúc phải sau giờ bắt đầu");
                }
            });

    private static void report(String label, MeetingSlot slot) {
        Errors errors = SLOT_VALIDATOR.validateObject(slot);
        System.out.println(label + ": errors=" + errors.getErrorCount());

        errors.getFieldErrors().forEach(error ->
                System.out.println(
                        "FIELD " + error.getField() + ": "
                                + error.getDefaultMessage()));

        errors.getGlobalErrors().forEach(error ->
                System.out.println(
                        "GLOBAL " + error.getCode() + ": "
                                + error.getDefaultMessage()));
    }

    public static void main(String[] args) {
        report("OK", new MeetingSlot("Họp nhóm", 9, 10));
        report("BAD", new MeetingSlot(" ", 11, 10));

        try {
            SLOT_VALIDATOR
                    .validateObject(new MeetingSlot(" ", 11, 10))
                    .failOnError(IllegalArgumentException::new);
        } catch (IllegalArgumentException exception) {
            System.out.println("THROWN: "
                    + exception.getClass().getSimpleName());
        }
    }
}
~~~

Tại thư mục dự án, với **JDK 17+** và Maven, chạy:

~~~bash
mvn -q compile exec:java
~~~

Kết quả mong đợi:

~~~text
OK: errors=0
BAD: errors=2
FIELD title: Tiêu đề không được trống
GLOBAL time.order: Giờ kết thúc phải sau giờ bắt đầu
THROWN: IllegalArgumentException
~~~

Ở lần đầu, lịch họp 9–10 giờ có tiêu đề hợp lệ, nên không phát sinh lỗi. Ở lần thứ hai, `title` chỉ gồm khoảng trắng và giờ kết thúc sớm hơn giờ bắt đầu; validator ghi **một lỗi thuộc tính** và **một lỗi toàn đối tượng**, nên `getErrorCount()` bằng 2. Cuối cùng, `failOnError(...)` chuyển kết quả không hợp lệ thành một ngoại lệ. Chương trình chỉ in tên ngoại lệ; phần mô tả chi tiết có thể phụ thuộc cách `Errors` tạo bản tóm tắt.

Ví dụ dùng validator được tạo bằng `Validator.forInstanceOf`. Nếu dự án đang có lớp `implements Validator` truyền thống, vẫn gọi được `validateObject` như vậy mà không cần factory. `forInstanceOf` chỉ giúp rút gọn cách khai báo validator và kiểm tra kiểu mà validator hỗ trợ.

## 3. Đọc kết quả trả về từ `validateObject`

`validateObject` trả **`org.springframework.validation.Errors`**, là API quan sát và ghi nhận lỗi của Spring. Không nên ép kiểu kết quả sang `BindingResult` vì thực thi mặc định dùng `SimpleErrors`, không phải một đối tượng binder.

| Phương thức | Khi sử dụng |
| --- | --- |
| `hasErrors()` | Kiểm tra nhanh có bất kỳ lỗi nào hay không; quyết định chặn luồng xử lý. |
| `getErrorCount()` | Lấy tổng số lỗi field + global, ví dụ trong test hoặc báo cáo. |
| `getFieldErrors()` | Lấy các lỗi gắn với tên thuộc tính, tiện trả lỗi cho từng ô input. |
| `getFieldError("title")` | Lấy lỗi đầu tiên của riêng trường `title`, có thể bằng `null`. |
| `getGlobalErrors()` | Lấy lỗi không gắn riêng vào một thuộc tính, ví dụ quy tắc start/end. |
| `getAllErrors()` | Lấy toàn bộ lỗi dưới dạng các `ObjectError` và `FieldError`. |
| `getObjectName()` | Tên đối tượng mà kết quả đang mô tả. |
| `failOnError(IllegalArgumentException::new)` | Không làm gì nếu hợp lệ; nếu có lỗi thì ném exception được tạo từ chuỗi tóm tắt lỗi. |

Trong một `FieldError`:

~~~java
Errors errors = SLOT_VALIDATOR.validateObject(
        new MeetingSlot(" ", 11, 10));

errors.getFieldErrors().forEach(error -> {
    String field = error.getField();
    String code = error.getCode();
    String message = error.getDefaultMessage();
    // Đưa field/code/message vào cấu trúc phản hồi phù hợp.
});
~~~

`getCode()` là mã lỗi phục vụ xử lý hoặc tra cứu thông điệp; `getDefaultMessage()` là thông điệp dự phòng, có thể bằng `null` nếu validator không cung cấp. Phần hiển thị cho người dùng có thể dùng `MessageSource` để bản địa hóa theo mã lỗi. Không dùng nguyên chuỗi thông báo đã dịch như một điều kiện điều khiển nghiệp vụ.

Khi cần **ném lỗi ngay** thay vì tự phân nhánh:

~~~java
SLOT_VALIDATOR.validateObject(slot)
        .failOnError(IllegalArgumentException::new);
~~~

`failOnError` là phương thức mặc định của `Errors`, cũng xuất hiện từ Spring Framework 6.1. Hàm được truyền vào nhận một chuỗi tóm tắt lỗi và tạo một ngoại lệ. Có thể dùng `IllegalStateException::new` hoặc factory ngoại lệ của ứng dụng nếu đó là cách tầng gọi quản lý lỗi. Đừng dùng exception ở một ranh giới cần thu thập **nhiều lỗi để hiển thị cùng lúc** mà không có handler chuyển đổi phù hợp.

### Tại sao vẫn có `supports(Class<?>)`?

`supports` vẫn là hợp đồng quan trọng của Spring `Validator`: nó cho các thành phần điều phối biết validator xử lý kiểu nào. Với một lớp tự triển khai:

~~~java
@Override
public boolean supports(Class<?> clazz) {
    return MeetingSlot.class.isAssignableFrom(clazz);
}
~~~

Nhưng hãy nhớ phương thức mặc định `validateObject(target)` đơn thuần tạo `SimpleErrors` rồi gọi `validate(target, errors)`; bản thân nó **không gọi `supports` như một bước lọc bắt buộc**. Nếu đưa sai loại object vào một validator cast trực tiếp, có thể xảy ra `ClassCastException`. Trong mã gọi trực tiếp, cần chọn validator đúng kiểu, hoặc dùng factory kiểu hóa như `forInstanceOf`/`forType` với ý nghĩa hỗ trợ kiểu thích hợp.

## 4. Điểm giới hạn quan trọng của `SimpleErrors`

Sự tiện lợi của `validateObject` đến từ việc Spring tự tạo một `SimpleErrors`. Nhưng **`SimpleErrors` được thiết kế cho một đối tượng cấp cao nhất**, có hạn chế so với `BeanPropertyBindingResult` hoặc `DataBinder`.

### 4.1. Không hỗ trợ nested-path navigation

Ví dụ validator của `Order` cần gọi validator của `Address` bằng cách:

~~~java
// Minh họa đoạn validator lồng nhau (không phải ví dụ chạy độc lập).
try {
    errors.pushNestedPath("address");
    addressValidator.validate(order.getAddress(), errors);
} finally {
    errors.popNestedPath();
}
~~~

Luồng `pushNestedPath("address")`/`popNestedPath()` đòi hỏi `Errors` hỗ trợ chuyển ngữ cảnh nested path. `SimpleErrors` không hỗ trợ thao tác này; lời gọi có thể ném `UnsupportedOperationException`. Vì vậy **không nên dùng `validateObject` trực tiếp cho validator phụ thuộc nested path**.

Nếu cần validation của đối tượng lồng nhau, tạo một `Errors` có khả năng bind/điều hướng thuộc tính:

~~~java
// Dùng các import Spring tương ứng; đoạn trích nằm trong ứng dụng.
Errors errors = new BeanPropertyBindingResult(order, "order");
orderValidator.validate(order, errors);
~~~

Sau đó có thể dùng `errors.hasErrors()`, `getFieldErrors()` như bình thường. Với request thực tế còn có giai đoạn bind/conversion, dùng `DataBinder`/`WebDataBinder` hoặc tích hợp chuẩn Spring MVC.

Không nên cho rằng mọi validator viết cho `BeanPropertyBindingResult` đều tự động tương thích với `SimpleErrors`. Kiểm tra xem nó có dùng `pushNestedPath`, `setNestedPath` hoặc cần trạng thái liên quan đến binding hay không.

### 4.2. Không thực hiện data binding, chuyển kiểu hay ghi lỗi chuyển đổi

`validateObject` chỉ **kiểm tra object đang có**; nếu người dùng nhập chuỗi `"abc"` ở trường số, phương thức này không chuyển chuỗi thành số và cũng không tạo lỗi `typeMismatch` như `DataBinder` có thể làm. Các lỗi bind cần được thu thập ở bước bind riêng.

So sánh hai luồng:

~~~text
A. Đối tượng Java đã có sẵn:
   object -> validator.validateObject(object) -> Errors
                    |
             đọc lỗi / failOnError

B. Dữ liệu web/form cần bind:
   request/raw values -> DataBinder/WebDataBinder
                      -> conversion + binding errors
                      -> validation
                      -> BindingResult
                      -> xử lý lỗi hoặc tiếp tục
~~~

Trong trường hợp B, một luồng lập trình trực tiếp với `DataBinder` có thể là:

~~~java
// Đoạn trích; target và properties do ứng dụng chuẩn bị.
DataBinder binder = new DataBinder(target, "target");
binder.setValidator(validator);
binder.bind(properties);
binder.validate();

BindingResult result = binder.getBindingResult();
if (result.hasErrors()) {
    // Bao gồm lỗi bind và lỗi validation đã được đăng ký.
}
~~~

`DataBinder.validate()` và `Validator.validateObject(...)` **không phải hai tên gọi cho cùng một quy trình**. Cái đầu dựa trên ngữ cảnh binder và trả kết quả thông qua `BindingResult`; cái sau tạo một `SimpleErrors` độc lập cho một lần kiểm tra.

### 4.3. Không tự chạy Jakarta Bean Validation cho mọi đối tượng

`org.springframework.validation.Validator` là API của Spring, khác với `jakarta.validation.Validator`. Đừng nhầm:

~~~java
// Spring Validator: trả Errors.
org.springframework.validation.Errors errors =
        springValidator.validateObject(input);
~~~

với:

~~~java
// Jakarta Bean Validation: trả Set<ConstraintViolation<T>>.
// Đoạn trích, cần jakarta.validation.Validator đã cấu hình.
var violations = jakartaValidator.validate(input);
~~~

Nếu chỉ tạo `Validator.forInstanceOf(...)` như ví dụ, annotation `@NotNull`/`@Size` trên DTO **không tự được chạy**; bạn phải viết logic validator hoặc cấu hình adapter/provider Bean Validation thích hợp. Trái lại, Spring có tích hợp Bean Validation qua `LocalValidatorFactoryBean`/các cơ chế MVC khi được cấu hình, nhưng đó là một triển khai validator cụ thể, không phải hành vi mặc định của mọi `Validator`.

### 4.4. Không thay cho quyết định nghiệp vụ

Nếu `errors.hasErrors()` bằng `false`, điều đó chỉ có nghĩa *các quy tắc mà validator đã chạy không tạo lỗi*. Nó không bảo đảm người gọi có quyền, tài nguyên còn tồn tại, giá trị còn duy nhất trong DB hay điều kiện giao dịch còn đúng. Kiểm tra cần thiết vẫn phải nằm tại service/domain/transaction thích hợp.

Một mẫu sử dụng trước side effect:

~~~java
// Đoạn trích của application service.
Errors errors = bookingValidator.validateObject(request);
if (errors.hasErrors()) {
    return BookingResult.invalid(errors.getAllErrors());
}

return bookingService.reserve(request);
~~~

Ở ví dụ này, `BookingResult` và `bookingService` là thành phần minh họa của ứng dụng. Điều quan trọng là **từ chối trước khi gọi thao tác đặt chỗ**.

## 5. Khi nào nên chọn `validateObject`?

| Tình huống | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| Object Java đã được tạo và cần chạy validator đơn giản ở tầng service | `validator.validateObject(object)` | Ít boilerplate, tự tạo `Errors` cho lần kiểm tra. |
| Cần nhanh chóng ném exception nếu object sai | `validator.validateObject(object).failOnError(...)` | Một lệnh rõ ràng, dùng chung cơ chế báo lỗi của Spring. |
| Validator cần `pushNestedPath`/`popNestedPath` để kiểm tra đối tượng con | `validator.validate(object, new BeanPropertyBindingResult(...))` | Cần `Errors` hỗ trợ nested paths. |
| Phải chuyển raw form values sang DTO và ghi lỗi conversion | `DataBinder`/`WebDataBinder` | Có ngữ cảnh binding và `BindingResult`. |
| Xử lý `@Valid @ModelAttribute` hoặc `@Valid @RequestBody` trong Spring MVC | Cơ chế validation của MVC + `BindingResult`/exception handler | Spring quản lý resolver, binding, validation và đường trả HTTP. |
| Dùng các constraint annotations `@NotNull`, `@Min`, `@Pattern` | Jakarta Bean Validation provider/adapter thích hợp | Annotation-based validation là cơ chế riêng cần cấu hình. |

Không có yêu cầu phải “nâng cấp toàn bộ code sang `validateObject`” từ Spring 6.1. Nếu validator vốn cần binder hoặc nested path, cách cũ vẫn đúng. Giá trị của phương thức mới nằm ở **trường hợp kiểm tra trực tiếp** với những validator phù hợp.

## 6. Viết test cho hai nhánh và cho giới hạn hỗ trợ

Với `validateObject`, test nên đảm bảo hành vi thật của validator, không chỉ việc phương thức trả một `Errors`.

**Ca hợp lệ:**

~~~java
// Đoạn trích có thể đưa vào một test JUnit 5 đã cấu hình.
Errors result = SLOT_VALIDATOR.validateObject(
        new MeetingSlot("Review", 8, 9));

assertFalse(result.hasErrors());
assertEquals(0, result.getErrorCount());
~~~

**Ca có cả lỗi field và global:**

~~~java
Errors result = SLOT_VALIDATOR.validateObject(
        new MeetingSlot("", 11, 10));

assertTrue(result.hasErrors());
assertTrue(result.hasFieldErrors("title"));
assertTrue(result.hasGlobalErrors());
assertEquals(2, result.getErrorCount());
~~~

**Ca exception:**

~~~java
assertThrows(IllegalArgumentException.class,
        () -> SLOT_VALIDATOR
                .validateObject(new MeetingSlot("", 11, 10))
                .failOnError(IllegalArgumentException::new));
~~~

Các test trên là **đoạn trích dành cho lớp test**, không được đưa vào file demo ở mục 2 nếu chưa thêm JUnit dependency, static imports và visibility thích hợp. Nếu test từ lớp ngoài thì cần đưa validator vào phạm vi truy cập phù hợp.

Trường hợp dự án có validator lồng nhau, cần test riêng đường `pushNestedPath` với `BeanPropertyBindingResult`. Không cố ép `SimpleErrors` thực thi hành vi mà API tuyên bố không hỗ trợ.

## 7. Lỗi phổ biến khi dùng API mới

1. **Ép kiểu `Errors` thành `BindingResult`**: kết quả mặc định của `validateObject` là `SimpleErrors`; cast sang `BindingResult` có thể gây `ClassCastException`.
2. **Tưởng `validateObject` đã bind dữ liệu web**: nó không lấy raw request và không phát hiện lỗi type conversion; phải bind trước ở nơi phù hợp.
3. **Gọi với sai kiểu đối tượng**: phương thức mặc định không tự kiểm tra `supports(...)`; hãy chọn đúng validator và tránh cast mù.
4. **Đưa validator phụ thuộc nested path vào `validateObject`**: `SimpleErrors` không cung cấp nested-path navigation; sử dụng một `Errors` có hỗ trợ tương ứng.
5. **Ném exception rồi lại bỏ qua**: `failOnError` ném ngoại lệ khi có lỗi. Handler hoặc tầng gọi phải thể hiện lỗi theo contract; không để phần ghi dữ liệu tiếp tục.
6. **Tưởng validator Spring tự thực thi mọi annotation Jakarta**: cần provider/adapter Bean Validation nếu muốn dùng constraint annotations.
7. **Dùng thông điệp hiển thị làm mã nghiệp vụ**: `getDefaultMessage()` có thể thay đổi theo ngôn ngữ/cấu hình; sử dụng error code rõ ràng.
8. **Không kiểm tra lỗi trước side effect**: `validateObject` chỉ hữu ích nếu lỗi thực sự khiến luồng bị từ chối trước khi ghi DB/gửi sự kiện.
9. **Tái sử dụng `Errors` giữa nhiều object hoặc luồng**: `validateObject` trả một kết quả mới mỗi lần; dùng kết quả đúng cho đối tượng tương ứng. `Errors` không được thiết kế cho truy cập đồng thời nhiều luồng.

## 8. Checklist áp dụng trong dự án

Khi cần validation trực tiếp từ Spring 6.1, có thể đi theo thứ tự:

1. Chọn đúng `org.springframework.validation.Validator` cho lớp đối tượng đang có; kiểm tra `supports(...)` nếu việc lựa chọn validator là động.
2. Xác nhận validator không phụ thuộc vào nested-path navigation hoặc ngữ cảnh binding mà `SimpleErrors` không có.
3. Gọi `Errors errors = validator.validateObject(object)`.
4. Dùng `hasErrors()` để phân nhánh, `getFieldErrors()`/`getGlobalErrors()` để tạo phản hồi, hoặc `failOnError(...)` để phát sinh ngoại lệ có chủ đích.
5. Chỉ tiếp tục các bước nghiệp vụ sau khi input hợp lệ và đã qua các kiểm tra quyền, trạng thái, bất biến liên quan.
6. Test cả nhánh thành công, lỗi nhiều trường, lỗi global, exception, và đường binder riêng nếu ứng dụng nhận request thô.

Ví dụ tối giản cần ghi nhớ:

~~~java
Errors result = validator.validateObject(input);
result.failOnError(IllegalArgumentException::new);
// Chỉ đi tới dòng này nếu validator không ghi nhận lỗi.
~~~

### Tài liệu Spring chính thức

- [Spring Framework — Validation Using Spring’s Validator Interface](https://docs.spring.io/spring-framework/reference/6.1/core/validation/validator.html)
- [Spring 6.1 — `Validator.validateObject(Object)` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/validation/Validator.html)
- [Spring 6.1 — `SimpleErrors` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/validation/SimpleErrors.html)
- [Spring 6.1 — `Errors.failOnError(...)` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/validation/Errors.html)
- [Spring 6.1 — `BeanPropertyBindingResult` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/validation/BeanPropertyBindingResult.html)
