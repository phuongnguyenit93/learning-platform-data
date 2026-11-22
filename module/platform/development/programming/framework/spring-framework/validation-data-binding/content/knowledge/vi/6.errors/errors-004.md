# `reject` và `rejectValue`: mã lỗi, tham số và thông báo mặc định trong Spring Framework

Trong Spring Framework, `Errors` là giao diện ghi nhận và truy vấn lỗi của **một đối tượng đang được kiểm tra**. Hai phương thức `reject(...)` và `rejectValue(...)` giúp validator chủ động thêm lỗi vào đối tượng `Errors` mà không cần ném exception mỗi khi dữ liệu không hợp lệ. Chúng lưu **thông tin lỗi có cấu trúc** để ứng dụng tra cứu, hiển thị thông báo, dịch theo ngôn ngữ và quyết định có tiếp tục xử lý nghiệp vụ hay không.

Bài này tập trung vào cách dùng chính xác hai phương thức, đặc biệt là ba thành phần quan trọng: **`errorCode` (mã lỗi), `errorArgs` (tham số thông báo) và `defaultMessage` (thông báo dự phòng)**. Ví dụ sử dụng Java 17 và Spring Framework 6.x; các khái niệm cũng áp dụng cho Spring MVC qua `BindingResult`.

## 1. Vị trí của `reject` và `rejectValue` trong luồng validation

`Errors` nằm trong package `org.springframework.validation`. `BindingResult` là một giao diện mở rộng `Errors`, đồng thời cung cấp thông tin liên quan đến binding như giá trị bị từ chối (`rejectedValue`), các field bị suppressed, và mô hình lỗi để render view.

Một luồng phổ biến:

```text
HTTP request / Java object
             |
             v
    Data binding / conversion
             |
             v
       Object đích
             |
             v
      Validator.validate(target, errors)
             |
      +------+------+
      |             |
      v             v
 errors.reject   errors.rejectValue
 (toàn object)     (một field)
      |             |
      +------+------+
             v
  Errors / BindingResult lưu ObjectError và FieldError
             |
             v
  Kiểm tra hasErrors(), getAllErrors(), ...
             |
             v
  Dịch thông điệp bằng MessageSource khi cần
             |
             v
  Phản hồi form/API hoặc cho phép nghiệp vụ tiếp tục
```

Cần phân biệt hai thời điểm: lỗi chuyển kiểu do **data binding** có thể được ghi trước khi validator chạy (ví dụ chuỗi `"abc"` không chuyển được thành `int`); còn lỗi nghiệp vụ do validator tự tạo bằng `reject`/`rejectValue`. Một `BindingResult` có thể chứa cả hai.

Khi gọi `reject(...)`, đối tượng đích **không tự thay đổi**; khi gọi `rejectValue(...)`, Spring **không tự sửa** giá trị field. Đây là thao tác ghi nhận lỗi, không phải thao tác bind, sửa dữ liệu, ném HTTP exception hay gửi response ngay lập tức.

## 2. Khác nhau giữa `reject` và `rejectValue`

| Tiêu chí | `errors.reject(...)` | `errors.rejectValue(...)` |
| --- | --- | --- |
| Phạm vi | Lỗi cho **toàn bộ object** (global/object error) | Lỗi gắn với **một field/path** của object |
| Trường hợp điển hình | Ngày bắt đầu sau ngày kết thúc; hai trường mâu thuẫn; đơn hàng không được phép | `age` ngoài khoảng; `email` sai định dạng; `lines[0].quantity` không hợp lệ |
| Đối tượng lỗi | `ObjectError` | `FieldError` (là một dạng `ObjectError`) |
| Cách đọc | `getGlobalErrors()`, `getGlobalError()` | `getFieldErrors()`, `getFieldError("age")` |
| Có tên field không? | Không; gắn với object name | Có; `FieldError.getField()` trả về path |
| Mã gợi ý | `order.invalidDateRange`, `booking.unavailable` | `quantity.range`, `email.invalid` |
| Tham số và fallback | Có | Có |

Ví dụ, chỉ xét tính hợp lệ của một thuộc tính:

```java
if (form.getQuantity() <= 0) {
    errors.rejectValue(
        "quantity",
        "quantity.positive",
        "Số lượng phải lớn hơn 0"
    );
}
```

Nếu quy tắc liên quan nhiều thuộc tính:

```java
if (form.getStartDate().isAfter(form.getEndDate())) {
    errors.reject(
        "dateRange.invalid",
        "Ngày bắt đầu phải không sau ngày kết thúc"
    );
}
```

Hai đoạn trên là **minh họa trong một validator**, giả định `form` có các getter tương ứng và `errors` là `Errors` hợp lệ. Với lỗi liên trường, có thể gắn lỗi vào một field để giao diện tô sáng, nhưng `reject` diễn tả chính xác hơn khi lỗi thuộc **quan hệ giữa các field hoặc toàn bộ đối tượng**.

## 3. Các overload chính xác của API

`Errors` có các dạng phương thức sau:

```java
// Global error:
void reject(String errorCode);
void reject(String errorCode, String defaultMessage);
void reject(String errorCode, Object[] errorArgs, String defaultMessage);

// Field error:
void rejectValue(String field, String errorCode);
void rejectValue(String field, String errorCode, String defaultMessage);
void rejectValue(
    String field,
    String errorCode,
    Object[] errorArgs,
    String defaultMessage
);
```

Đây là **chữ ký khái quát** để học API, không phải mã nguồn độc lập: trong các bản Spring mới, một số tham số/overload cho phép `null` và một số overload có implementation mặc định trong interface.

Ý nghĩa từng đối số:

- `field`: tên thuộc tính được kiểm tra, ví dụ `"quantity"`, `"address.city"`, `"lines[1].sku"`. Phương thức `reject` không có đối số này.
- `errorCode`: mã biểu thị nguyên nhân, ví dụ `"quantity.range"`. Thông thường đây là **message key**, không phải câu thông báo hiển thị trực tiếp.
- `errorArgs`: mảng đối tượng được dùng để thay thế các placeholder như `{0}` và `{1}` trong mẫu thông báo bằng cơ chế `MessageFormat`. Có thể truyền `null` khi không cần tham số.
- `defaultMessage`: câu dự phòng khi không tìm thấy message key phù hợp qua `MessageSource`. Có thể truyền `null` nếu ứng dụng không cần fallback, nhưng lúc đó phải xử lý tình huống tra cứu không tìm thấy thông điệp.
- `getObjectName()` trên `Errors` trả tên đối tượng gốc mà Spring gắn vào thông tin lỗi, ví dụ `"bookingForm"`.

Ví dụ đầy đủ nhất của mỗi loại:

```java
errors.reject(
    "booking.unavailable",
    new Object[] { "VIP" },
    "Gói {0} hiện không khả dụng"
);

errors.rejectValue(
    "quantity",
    "quantity.range",
    new Object[] { 1, 10 },
    "Số lượng hợp lệ từ {0} đến {1}"
);
```

Hai lời gọi thêm lỗi nhưng không ngay lập tức tra cứu `MessageSource`. Việc chọn ngôn ngữ và chuyển placeholder thành chuỗi thường xảy ra ở bước **giải quyết thông điệp** trong tầng view/API hoặc khi gọi `messageSource.getMessage(error, locale)`.

### 3.1. Vì sao đặt mã lỗi thay vì viết trực tiếp tiếng Việt?

Giả sử mã `quantity.range` dùng cho cả tiếng Việt và tiếng Anh:

```properties
# messages_vi.properties
quantity.range.bookingForm.quantity=Số lượng phải từ {0} đến {1}
quantity.range=Số lượng nằm ngoài giới hạn
```

```properties
# messages_en.properties
quantity.range.bookingForm.quantity=Quantity must be between {0} and {1}
quantity.range=Quantity is outside the allowed range
```

Các snippet trên là **ví dụ nội dung resource bundle**, không phải cấu hình project bắt buộc. Nếu cấu hình basename là `messages` và có message resolver tương thích, cùng một `errorCode` có thể cho kết quả phù hợp `Locale`. Không đưa câu thông báo đã dịch vào `errorCode`, vì khi đó khó phân loại lỗi, dịch, thay đổi câu chữ và mở rộng cấu trúc mã.

### 3.2. Mã lỗi nên đặt như thế nào?

Tốt nhất chọn code biểu đạt quy tắc cụ thể, ổn định:

| Mã | Quy tắc tương ứng |
| --- | --- |
| `required` hoặc `field.required` | Giá trị bắt buộc |
| `quantity.range` | Khoảng số lượng cho phép |
| `booking.unavailable` | Trạng thái booking không phù hợp |
| `dateRange.invalid` | Khoảng thời gian mâu thuẫn |
| `email.duplicate` | Email đã tồn tại theo quy tắc ứng dụng |
| `order.line.limit` | Số dòng đơn hàng vượt giới hạn |

Một validator có thể dùng cùng một code cho nhiều object; `MessageCodesResolver` sẽ bổ sung ngữ cảnh tên object/field để chọn câu thông báo cụ thể. Không phụ thuộc vào việc string code tự động đồng nghĩa với HTTP status hoặc mã lỗi API đã công bố.

## 4. Spring mở rộng `errorCode` thành các mã thông điệp ra sao?

Khi dùng `BindingResult` triển khai tiêu chuẩn như `BeanPropertyBindingResult`, Spring thường dùng `DefaultMessageCodesResolver` để tạo **danh sách mã ứng viên** từ `errorCode` ban đầu.

Ví dụ object name là `bookingForm` và gọi:

```java
errors.reject("booking.unavailable", null, "Không thể đặt chỗ");
```

Global error có các code theo thứ tự cụ thể tới tổng quát:

```text
booking.unavailable.bookingForm
booking.unavailable
```

Nếu gọi:

```java
errors.rejectValue(
    "quantity",
    "quantity.range",
    new Object[] { 1, 10 },
    "Số lượng hợp lệ từ {0} đến {1}"
);
```

Và field `quantity` có kiểu `int`, các mã ứng viên thường là:

```text
quantity.range.bookingForm.quantity
quantity.range.quantity
quantity.range.int
quantity.range
```

Spring thử các mã từ **cụ thể đến tổng quát**, vì vậy key `quantity.range.bookingForm.quantity` có thể được ưu tiên hơn `quantity.range`. Mã chính xác của biến thể kiểu (`int` hay `java.lang.Integer`) tùy loại field Java được khai báo; ví dụ trên giả định primitive `int`.

**Đối với nested path/indexed field**, danh sách code có thể dài hơn. Chẳng hạn `lines[0].quantity` có thể có các biến thể gắn với index và biến thể tổng quát bỏ index (`lines.quantity`), giúp một message áp dụng cho mọi dòng. Số lượng, thứ tự và formatter của các code thay đổi nếu cấu hình `MessageCodesResolver` khác; đừng hard-code rằng mọi lỗi field đều có đúng bốn code.

Phân biệt:

- `errorCode` là chuỗi tác giả validator truyền vào, ví dụ `quantity.range`.
- `ObjectError.getCodes()` hoặc `FieldError.getCodes()` là **mảng các code ứng viên** mà Spring lưu để tra cứu message.
- `getCode()` trả một code đơn lẻ đại diện theo API, không thể hiện toàn bộ độ ưu tiên. Khi cần giải thích chi tiết hoặc kiểm thử fallback, xem `getCodes()`.
- `MessageSource` lựa chọn thông báo theo **danh sách ứng viên và Locale**, không phải mặc định in `errorCode` ra màn hình.

## 5. `errorArgs` và cách thay thế tham số

`errorArgs` là một `Object[]` ứng với những vị trí `{0}`, `{1}`, ... trong chuỗi message. Ví dụ:

```java
errors.rejectValue(
    "quantity",
    "quantity.range",
    new Object[] { 1, 10 },
    "Số lượng phải từ {0} đến {1}"
);
```

Thông điệp có thể là:

```text
Số lượng phải từ 1 đến 10
```

Nếu cấu hình resource bundle:

```properties
quantity.range.bookingForm.quantity=Số lượng tối thiểu {0}, tối đa {1}
```

thì cùng lỗi đó, khi tra message, sẽ ưu tiên:

```text
Số lượng tối thiểu 1, tối đa 10
```

**Tham số được truyền theo vị trí, không phải theo tên.** Nếu đảo thứ tự `new Object[] { 10, 1 }`, câu hiển thị sẽ sai mặc dù bản thân mã lỗi vẫn đúng.

### 5.1. Đối số chứa nhãn field có thể dịch được

`errorArgs` còn có thể chứa đối tượng implement `MessageSourceResolvable` để nội suy **một thông điệp khác**, ví dụ nhãn tên trường. Đây là kỹ thuật hữu ích cho câu như `"Trường 'Số lượng' phải từ 1 đến 10"`.

```java
import org.springframework.context.support.DefaultMessageSourceResolvable;

Object quantityLabel = new DefaultMessageSourceResolvable(
    "label.bookingForm.quantity",
    "Số lượng"
);

errors.rejectValue(
    "quantity",
    "quantity.range",
    new Object[] { quantityLabel, 1, 10 },
    "{0} phải từ {1} đến {2}"
);
```

Đoạn code này minh họa cách tạo đối số có thể resolve. Với key `label.bookingForm.quantity=Số lượng` và `quantity.range.bookingForm.quantity={0} phải từ {1} đến {2}`, `MessageSource` có thể đưa ra câu hoàn chỉnh theo locale. Trong dự án thật, cấu hình resolver và cách xây dựng placeholder phải đồng nhất.

### 5.2. `MessageFormat` có quy tắc riêng

Các placeholder dùng ký pháp của `java.text.MessageFormat`. Điều đó kéo theo:

1. `{0}` là đối số đầu, `{1}` là đối số thứ hai. Thiếu đối số sẽ không tạo được câu hoàn chỉnh như mong muốn.
2. Dấu nháy đơn có vai trò escape trong `MessageFormat`: nếu thông báo chứa nháy đơn phải dùng escape thích hợp (thường viết hai dấu `''` để in một dấu `'`).
3. Có thể dùng định dạng số/ngày phù hợp với `Locale` trong pattern, nhưng hãy kiểm thử thực tế thay vì tự định dạng số thành string rồi giả định mọi locale giống nhau.
4. Đối số có thể đến từ client. Không dùng `errorArgs` để tạo HTML chưa escape rồi nhúng trực tiếp vào trang; template/view phải escape output.

Nếu chỉ có thông điệp tĩnh không placeholder, dùng overload ngắn `reject("code", "Default")` hoặc `rejectValue("field", "code", "Default")` để code dễ đọc.

## 6. Vai trò thật sự của `defaultMessage`

Khi không tìm được mã phù hợp, `MessageSource` có thể dùng `defaultMessage` nằm trong `ObjectError`/`FieldError`.

Ví dụ:

```java
errors.rejectValue(
    "coupon",
    "coupon.unusable",
    new Object[] { "SAVE" },
    "Mã {0} chưa được chấp nhận"
);
```

Nếu không có key nào tương ứng trong message source, kết quả sau giải quyết thông điệp có thể là:

```text
Mã SAVE chưa được chấp nhận
```

**`getDefaultMessage()` không đồng nghĩa với thông điệp hiển thị đã được resolve.** Thông thường nó cho biết mẫu fallback được lưu cùng lỗi, ví dụ `"Mã {0} chưa được chấp nhận"`. Muốn được xử lý theo `Locale`, thay tham số và ưu tiên resource bundle, hãy dùng `MessageSource.getMessage(error, locale)` (vì `ObjectError` là `MessageSourceResolvable`) hoặc cơ chế render lỗi tương ứng của Spring MVC.

Nếu không có message key lẫn fallback khả dụng, tra cứu thông điệp có thể báo `NoSuchMessageException` (tùy overload/cấu hình). Không nên phụ thuộc vào việc Spring sẽ tự hiện `errorCode` như câu thân thiện cho người dùng.

### 6.1. Fallback không che giấu lỗi cấu hình

Một fallback hợp lệ giúp UI vẫn có thông báo khi thiếu file ngôn ngữ; tuy nhiên nó không chứng minh rằng key đã được dịch đúng. Khi localization là yêu cầu sản phẩm, nên kiểm thử cả ngôn ngữ mặc định và ít nhất một ngôn ngữ thứ hai để phát hiện thiếu key.

Không nhét thông tin nhạy cảm vào `defaultMessage` (email cá nhân, token, exception trace, SQL), vì message có thể được đưa ra response/UI hoặc log nếu ứng dụng sử dụng tùy tiện.

## 7. Ví dụ Java 17 chạy độc lập: global error, field error, args và fallback

Ví dụ dùng `BeanPropertyBindingResult` để tạo đối tượng lỗi cho `BookingForm` và `StaticMessageSource` để mô phỏng resource bundle tại chỗ. Không cần khởi động Spring MVC hoặc web server. Ví dụ này tập trung vào **đăng ký lỗi và resolve thông báo**, không có bước HTTP binding hay ghi database.

Tạo cấu trúc thư mục:

```text
errors-demo/
├── pom.xml
└── src/main/java/example/RejectDemo.java
```

`pom.xml` (Java 17, Spring Framework 6.2.10):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>errors-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.10</version>
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
        <version>3.5.1</version>
        <configuration>
          <mainClass>example.RejectDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

`src/main/java/example/RejectDemo.java`:

```java
package example;

import java.util.Locale;

import org.springframework.context.support.StaticMessageSource;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;

public class RejectDemo {

    public static class BookingForm {
        private int quantity = 0;
        private String coupon = "SAVE";

        public int getQuantity() { return quantity; }
        public void setQuantity(int quantity) { this.quantity = quantity; }

        public String getCoupon() { return coupon; }
        public void setCoupon(String coupon) { this.coupon = coupon; }
    }

    public static void main(String[] args) {
        BookingForm form = new BookingForm();
        BeanPropertyBindingResult errors =
            new BeanPropertyBindingResult(form, "bookingForm");

        errors.rejectValue(
            "quantity",
            "quantity.range",
            new Object[] { 1, 10 },
            "Số lượng phải từ {0} đến {1}"
        );

        errors.reject(
            "booking.unavailable",
            new Object[] { "VIP" },
            "Gói {0} không khả dụng"
        );

        errors.rejectValue(
            "coupon",
            "coupon.unusable",
            new Object[] { "SAVE" },
            "Mã {0} chưa được chấp nhận"
        );

        Locale vi = Locale.forLanguageTag("vi");
        StaticMessageSource messages = new StaticMessageSource();

        messages.addMessage(
            "quantity.range.bookingForm.quantity",
            vi,
            "Số lượng hợp lệ: từ {0} đến {1}"
        );
        messages.addMessage(
            "booking.unavailable.bookingForm",
            vi,
            "Gói {0} đã hết chỗ"
        );
        // Cố tình không tạo message cho coupon.unusable
        // để chứng minh defaultMessage được sử dụng.

        FieldError quantity = errors.getFieldError("quantity");
        ObjectError booking = errors.getGlobalError();
        FieldError coupon = errors.getFieldError("coupon");

        System.out.println(quantity.getCodes()[0]);
        System.out.println(booking.getCodes()[0]);
        System.out.println(messages.getMessage(quantity, vi));
        System.out.println(messages.getMessage(booking, vi));
        System.out.println(messages.getMessage(coupon, vi));
        System.out.println(errors.getGlobalErrorCount());
        System.out.println(errors.getFieldErrorCount());
        System.out.println(errors.hasErrors());
    }
}
```

Chạy tại thư mục `errors-demo`:

```bash
mvn -q compile exec:java
```

`stdout` dự kiến (không tính log Maven nếu môi trường in thêm):

```text
quantity.range.bookingForm.quantity
booking.unavailable.bookingForm
Số lượng hợp lệ: từ 1 đến 10
Gói VIP đã hết chỗ
Mã SAVE chưa được chấp nhận
1
2
true
```

Giải thích:

1. `getCodes()[0]` của field ưu tiên key `quantity.range.bookingForm.quantity`; global ưu tiên `booking.unavailable.bookingForm`.
2. `StaticMessageSource` tìm thấy hai key cụ thể và thay các đối số ở `{0}`, `{1}`.
3. Không có message cho `coupon.unusable` và các biến thể; `defaultMessage` được dùng và `"SAVE"` được đưa vào `{0}`.
4. Có **một global error** và **hai field errors**; `hasErrors()` là `true`.
5. `rejectValue` không hề đổi `BookingForm.quantity` từ 0 thành số khác; lỗi chỉ được lưu vào `BeanPropertyBindingResult`.
6. Demo dùng một class công khai `RejectDemo`, còn `BookingForm` là nested class nên lưu toàn bộ mã Java trong một file đúng tên; Maven dependency `spring-context` kéo theo các thành phần Spring validation cần dùng.

Trong ứng dụng thực tế, thay `StaticMessageSource` bằng `MessageSource` được cấu hình bởi Spring và resource bundles; tránh tạo/dạy Spring message source mới cho từng request.

## 8. Viết `Validator` sử dụng hai phương thức

Validator của Spring Core dùng interface `org.springframework.validation.Validator` với hai phương thức `supports(Class<?>)` và `validate(Object, Errors)`. Ví dụ:

```java
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public class BookingValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return BookingForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        BookingForm form = (BookingForm) target;

        if (form.getQuantity() < 1 || form.getQuantity() > 10) {
            errors.rejectValue(
                "quantity",
                "quantity.range",
                new Object[] { 1, 10 },
                "Số lượng phải từ {0} đến {1}"
            );
        }

        if ("VIP".equals(form.getPackageName())
                && form.isPromotionClosed()) {
            errors.reject(
                "booking.unavailable",
                new Object[] { "VIP" },
                "Gói {0} hiện chưa thể đặt"
            );
        }
    }
}
```

Đây là **đoạn minh họa cần tích hợp**: `BookingForm` trong validator này phải có thêm `getPackageName()` và `isPromotionClosed()`, và phải được định nghĩa tại đúng package/import. Nó không phải phần tiếp theo có thể copy thẳng vào demo ở mục 7. Quy tắc toàn object dùng `reject`; quy tắc riêng `quantity` dùng `rejectValue`.

Đừng gọi `reject(...)` với một mã lỗi rồi cho rằng nó tự tạo `FieldError`; và đừng gọi `rejectValue(...)` với tên field không tồn tại mà mong Spring lặng lẽ bỏ qua. Việc truy cập một property path sai hoặc target không phù hợp có thể gây lỗi truy cập property tùy implementation.

### 8.1. Trợ giúp cho trường bắt buộc

Spring có `ValidationUtils.rejectIfEmpty(...)` và `ValidationUtils.rejectIfEmptyOrWhitespace(...)` để tránh lặp đoạn kiểm tra chuỗi rỗng:

```java
ValidationUtils.rejectIfEmptyOrWhitespace(
    errors,
    "customerName",
    "customerName.required",
    "Vui lòng nhập tên khách hàng"
);
```

Đây là helper ở `org.springframework.validation.ValidationUtils`. Nó nhận tên field, code và fallback, và đăng ký field error khi điều kiện tương ứng thỏa. Không phải mọi loại đối tượng đều mang nghĩa “empty” giống nhau; dùng helper đúng với property được kiểm tra.

### 8.2. Nested path phải tính đến ngữ cảnh

Khi tái sử dụng validator con, có thể tạm đẩy một đường dẫn:

```java
errors.pushNestedPath("address");
try {
    errors.rejectValue(
        "city",
        "city.required",
        "Thành phố là bắt buộc"
    );
} finally {
    errors.popNestedPath();
}
```

Với `Errors` implementation hỗ trợ nested path, field error sẽ có path `address.city`. Luôn dùng `finally` để trả context về trạng thái trước đó. `reject(...)` vẫn đăng ký global error cho object gốc; nếu muốn báo lỗi cụ thể tại một object con, cân nhắc `rejectValue` với path thích hợp thay vì kỳ vọng `reject` tự biến thành một field error.

Theo Javadoc các bản mới, `rejectValue` với field rỗng/`null` có thể biểu thị chính object hiện hành và trong một số tình huống tạo global error; để rõ ý định, ứng dụng thường nên dùng `reject` cho lỗi ở root và `rejectValue("field", ...)` cho field có tên.

## 9. Dùng với Spring MVC và `BindingResult`

Trong Spring MVC, handler thường nhận `BindingResult` hoặc `Errors` **ngay sau** tham số dữ liệu được bind/validate:

```java
@PostMapping("/bookings")
public String submit(
        @Validated @ModelAttribute("bookingForm") BookingForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return "booking/edit";
    }

    bookingService.save(form);
    return "redirect:/bookings";
}
```

Đây là mã tích hợp; cần controller, service, form model và imports tương ứng. `@Validated` kích hoạt validation đã được cấu hình phù hợp (chẳng hạn Spring Validator đăng ký bằng `@InitBinder` hoặc Jakarta Bean Validation). Nếu handler muốn tự thêm lỗi nghiệp vụ sau khi bind, có thể gọi `result.reject(...)`/`result.rejectValue(...)` rồi kiểm tra `hasErrors()`. Ví dụ:

```java
if (!availabilityService.isAvailable(form)) {
    result.reject(
        "booking.unavailable",
        new Object[] { form.getPackageName() },
        "Gói {0} không khả dụng"
    );
}

if (result.hasErrors()) {
    return "booking/edit";
}
```

Một số cách sử dụng cần tránh:

- `BindingResult` phải đứng ngay sau tham số mà nó mô tả, không đặt ở cuối signature sau các tham số khác.
- Nếu handler dùng `@RequestBody` thì cơ chế đọc JSON không phải property binding theo tên form field; tuy nhiên validation errors và `BindingResult` vẫn có thể được dùng trong cấu hình/hình thức handler phù hợp.
- Không gọi service lưu dữ liệu trước khi kiểm tra `result.hasErrors()`, nếu lỗi có khả năng ảnh hưởng tính hợp lệ của nghiệp vụ.
- Nếu cần hiển thị thông báo, phải render/resolve lỗi theo ngôn ngữ; `result.toString()` chỉ phù hợp cho chẩn đoán chứ không phải câu UI thân thiện.

### 9.1. Hiển thị global và field error

Với Spring MVC template, ý tưởng cơ bản là:

```text
Global errors:
  "Gói VIP đã hết chỗ" -> đặt ở đầu form

Field errors:
  "Số lượng hợp lệ: từ 1 đến 10" -> đặt gần ô quantity
  "Mã SAVE chưa được chấp nhận" -> đặt gần ô coupon
```

Trong Thymeleaf có Spring integration, các biểu thức lỗi ví dụ là:

```html
<form th:object="\${bookingForm}" method="post">
  <div th:if="\${#fields.hasGlobalErrors()}"
       th:each="error : \${#fields.globalErrors()}"
       th:text="\${error}"></div>

  <label>Số lượng</label>
  <input th:field="*{quantity}">
  <span th:if="\${#fields.hasErrors('quantity')}"
        th:errors="*{quantity}"></span>
</form>
```

Đây là fragment template, cần cấu hình Thymeleaf/Spring MVC và object `bookingForm` thực sự được cung cấp. Các giá trị lỗi phải được escape bởi template engine phù hợp; tránh tự xây HTML bằng nối chuỗi từ nội dung client.

### 9.2. Khi trả API JSON

Trong REST API, có thể chuyển lỗi thành dữ liệu JSON gồm `code`, `field` (nếu có), `message` đã resolve và metadata an toàn. Ví dụ **minh họa shape**, không phải hợp đồng tự sinh của Spring:

```json
{
  "errors": [
    {
      "code": "quantity.range",
      "field": "quantity",
      "message": "Số lượng phải từ 1 đến 10"
    },
    {
      "code": "booking.unavailable",
      "field": null,
      "message": "Gói VIP đã hết chỗ"
    }
  ]
}
```

Thông thường chọn một **mã công khai ổn định** cho client, không phụ thuộc hoàn toàn vào thông điệp dịch hoặc chuỗi nội bộ như `quantity.range.bookingForm.quantity`. Không trả giá trị bị từ chối nếu nó là mật khẩu, token hoặc thông tin nhạy cảm. Đối với lỗi bind/validation theo HTTP, tầng exception handler có thể chuyển thành HTTP 400 (tùy thiết kế endpoint), không phải bản thân `reject` quyết định status.

## 10. Đọc lại thông tin lỗi để xử lý

`Errors` hỗ trợ các phương thức:

```java
errors.hasErrors();
errors.getErrorCount();
errors.hasGlobalErrors();
errors.getGlobalErrorCount();
errors.getGlobalErrors();
errors.hasFieldErrors();
errors.getFieldErrorCount();
errors.getFieldErrors();
errors.getFieldError("quantity");
errors.getFieldErrors("quantity");
errors.getAllErrors();
```

Ví dụ duyệt từng nhóm (mã nằm trong một handler/validator test có `Errors errors`):

```java
for (ObjectError global : errors.getGlobalErrors()) {
    System.out.println(global.getCodes()[0]);
}
for (FieldError field : errors.getFieldErrors()) {
    System.out.println(field.getField() + ": " + field.getCode());
}
```

`FieldError` có các thông tin như `getField()`, `getRejectedValue()` và `isBindingFailure()` (phân biệt một lỗi binding với lỗi validation). Trong khi đó `ObjectError` có `getObjectName()`, `getCodes()`, `getArguments()`, `getDefaultMessage()`. Việc truy vấn lỗi giúp tạo phản hồi chính xác, nhưng tránh log nguyên giá trị input nhạy cảm.

**Đếm lỗi**: `getErrorCount()` là tổng số field errors và global errors. Một field có thể có nhiều lỗi (ví dụ vừa vi phạm format vừa vi phạm business rule). `hasErrors()` cho biết tồn tại ít nhất một lỗi, không chứng minh toàn bộ việc bind/validation đã chạy theo ý định.

## 11. Phân biệt các kiểu lỗi gần nhau

| Trường hợp | Nên dùng | Lý do |
| --- | --- | --- |
| `quantity=0` nhưng yêu cầu từ 1–10 | `rejectValue("quantity", "quantity.range", ...)` | Một thuộc tính vi phạm giới hạn |
| `startDate > endDate` | `reject("dateRange.invalid", ...)` | Quy tắc liên quan hai field |
| `password` và `confirmPassword` không khớp | `reject("password.mismatch", ...)` hoặc `rejectValue("confirmPassword", ...)` khi UI cần gắn lỗi trực tiếp | Thiết kế lỗi theo trải nghiệm xử lý |
| `age=abc` khi `age` là `int` | Lỗi binding/typeMismatch do framework ghi nhận | Không cần validator tự chuyển `String` sang `int` |
| Field `email` trống | `ValidationUtils.rejectIfEmptyOrWhitespace(...)` hoặc `rejectValue(...)` | Mục tiêu gắn lỗi vào field |
| Không tìm thấy message code | `defaultMessage`, nếu có | Fallback cho hiển thị, không làm biến mất lỗi |
| Một property không nằm trong `allowedFields` | Cấu hình binding và kiểm tra suppressed fields | Không đánh đồng field bị loại với `FieldError` |

## 12. Lỗi thường gặp và cách phòng tránh

**1. Nhầm mã lỗi với câu thông báo.** `errors.reject("Số lượng không hợp lệ")` chỉ tạo một mã lỗi có nội dung chuỗi đó; không thiết kế được i18n rõ ràng. Dùng `quantity.invalid` và đặt thông điệp trong message bundle.

**2. Nghĩ `reject` làm lỗi field.** `reject("email.invalid")` là global error dù tên code có chữ `email`. Muốn gắn với ô email, dùng `rejectValue("email", "email.invalid")`.

**3. Đặt sai tên field.** `rejectValue("customer.address", ...)` khác `rejectValue("customer.address.city", ...)`. Tên field phải phù hợp với property model và nested context, nếu không có thể gặp lỗi truy cập property hoặc đưa lỗi nhầm vị trí.

**4. Truyền sai số lượng hoặc thứ tự arguments.** Với message `"{0} nằm trong khoảng {1}–{2}"` cần ba đối số đúng thứ tự. Compiler không tự đối chiếu nội dung resource bundle với `errorArgs`.

**5. Dùng `getDefaultMessage()` để hiển thị trực tiếp.** Chuỗi đó có thể chứa `{0}` chưa được thay, chưa theo Locale và không ưu tiên message bundle. Dùng `MessageSource` hoặc template integration.

**6. Không cung cấp fallback và chưa có message key.** Khi thông điệp không tìm được, resolver có thể ném `NoSuchMessageException`. Duy trì fallback có ý nghĩa và kiểm thử bundle/locale.

**7. Quên rằng lỗi có thể đến từ binding.** Validator có thể thấy số mặc định `0` dù người dùng nhập chuỗi `abc` sai kiểu. Nếu có lỗi binding ở field, tránh ghi đè nghĩa lỗi bằng một báo lỗi nghiệp vụ thiếu bối cảnh; đọc `BindingResult` trước.

**8. Kiểm tra `hasErrors()` quá sớm.** Nếu tiếp tục gọi `rejectValue` sau khi xử lý nghiệp vụ đã chạy, ứng dụng có thể cập nhật dữ liệu trước khi nhận ra lỗi. Tập trung validation trước side effects.

**9. Không xử lý nested-path stack.** Khi dùng `pushNestedPath` cho validator con, thiếu `popNestedPath` khiến các lỗi sau đó bị gắn vào path sai; dùng `try/finally`.

**10. Đưa dữ liệu nhạy cảm vào thông điệp.** `errorArgs` và `defaultMessage` có thể đi vào response/log; chỉ đưa dữ liệu an toàn, hoặc che giấu nếu cần.

**11. Bám vào duy nhất một mã cụ thể.** Nếu chỉ định nghĩa `quantity.range.bookingForm.quantity`, việc đổi tên model attribute thành `checkoutForm` có thể khiến thông điệp riêng không còn được tìm thấy. Có fallback tổng quát như `quantity.range` khi hợp lý.

**12. Dùng ngoại lệ để thay thế mọi lỗi form.** Với validation thông thường, `reject`/`rejectValue` tích lũy nhiều lỗi cho người dùng sửa trong một lần. Exception phù hợp với failure không thể tiếp tục theo thiết kế; không cần ném exception cho từng field sai hợp lệ.

## 13. Tự kiểm tra với ba tình huống

### Tình huống A — Chọn loại lỗi

Object `ReservationForm` có `attendees` và `maxCapacity`. Nếu chỉ `attendees = -1`, gọi gì? Nếu `attendees = 5` nhưng chỗ còn lại chỉ 3, gọi gì?

**Gợi ý:** `rejectValue("attendees", "attendees.positive", ...)` phù hợp cho giới hạn của một field. Nếu quy tắc về khả năng đặt chỗ phụ thuộc trạng thái/tồn kho của toàn booking, có thể dùng `reject("reservation.capacityExceeded", ...)`; khi UI cần gắn lỗi ngay ô `attendees`, `rejectValue` cũng là lựa chọn hợp lý.

### Tình huống B — Giải thích độ ưu tiên mã

Validator gọi `rejectValue("quantity", "quantity.range", new Object[]{1,10}, "Số lượng không hợp lệ")` trên object name `bookingForm`. Resource bundle có:

```properties
quantity.range.bookingForm.quantity=Số lượng từ {0} đến {1}
quantity.range=Giá trị vượt giới hạn
```

**Đáp án:** với default resolver và đúng kiểu field, mã cụ thể đầu tiên được chọn; thông báo là `"Số lượng từ 1 đến 10"`. Nếu xóa key cụ thể và không có key ưu tiên khác, resolver có thể dùng `quantity.range`, trả `"Giá trị vượt giới hạn"`. Mẫu fallback chỉ dùng khi không tìm được code phù hợp.

### Tình huống C — Phát hiện lỗi trong API

Cho đoạn:

```java
errors.reject("age.invalid", "Tuổi không hợp lệ");
System.out.println(errors.getFieldError("age") != null);
```

**Đáp án:** với `Errors` chưa có lỗi field nào trước đó, biểu thức in `false`, vì `reject` thêm **global error**. Việc code chứa chữ `age` không khiến Spring tạo `FieldError`.

## 14. Tài liệu tham khảo chính thức

- Spring Framework Reference — [Validation using Spring's Validator Interface](https://docs.spring.io/spring-framework/reference/core/validation/validator.html): triển khai `Validator`, `Errors`, `ValidationUtils` và nested validation.
- Spring Framework Javadoc — [`Errors`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/Errors.html): các overload `reject`/`rejectValue`, `errorArgs`, `defaultMessage`, global/field errors.
- Spring Framework Javadoc — [`DefaultMessageCodesResolver`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DefaultMessageCodesResolver.html): quy tắc mở rộng message code, thứ tự tìm cho object/field và indexed path.
- Spring Framework Javadoc — [`ObjectError`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/ObjectError.html), [`FieldError`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/FieldError.html): thông tin lỗi có cấu trúc.
- Spring Framework Reference — [Spring MVC validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): phối hợp `@Validated`/`@Valid` với `BindingResult`.
- Spring Framework Javadoc — [`MessageSource`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/MessageSource.html): cách resolve message theo mã, tham số và locale.
