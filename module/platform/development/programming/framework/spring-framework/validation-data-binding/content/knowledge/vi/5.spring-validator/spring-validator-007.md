# pushNestedPath và popNestedPath khi kiểm tra đối tượng lồng với Spring Validator

Trong Spring Framework, một `Validator` có thể kiểm tra đối tượng gốc và giao việc kiểm tra một thuộc tính kiểu object cho validator khác. Chẳng hạn, `Customer` có `Address address`; validator của `Address` chỉ biết các field `city` và `postalCode`, trong khi lỗi trả về cho người dùng cần chỉ rõ `address.city` và `address.postalCode`. Hai phương thức **`Errors.pushNestedPath(String)`** và **`Errors.popNestedPath()`** giúp tái sử dụng validator con trong đúng ngữ cảnh mà không phải tự ghép đường dẫn ở từng câu lệnh.

Bài này giải thích cơ chế stack đường dẫn lồng, thứ tự push/validate/pop, cách xử lý dữ liệu con `null`, ví dụ Java 17 chạy được với Spring và các lỗi phổ biến. Đối tượng được kiểm tra bằng giao diện `org.springframework.validation.Validator`, không cần có một HTTP request; Spring MVC có thể sử dụng cùng cơ chế khi xử lý dữ liệu form.

## 1. Vấn đề: lỗi của object con cần mang đường dẫn từ object gốc

Giả sử dữ liệu có cấu trúc:

```text
Customer
├── fullName = "Lan"
├── address: Address
│   ├── city = ""
│   └── postalCode = "12"
└── contactEmail = "lan@example.org"
```

Trong `AddressValidator`, việc kiểm tra đơn giản nhất là:

```java
ValidationUtils.rejectIfEmptyOrWhitespace(errors, "city", "required");
```

Nhưng khi `Address` là một phần của `Customer`, field có lỗi cần được ghi với tên đầy đủ **`address.city`**, vì người dùng hoặc ứng dụng nhận kết quả đang xử lý object gốc. Với các mức lồng sâu hơn, ta có những tên như `billingAddress.country.code` hoặc `items[0].name`.

Một cách dễ làm sai là viết cứng `"address.city"` trong `AddressValidator`. Cách đó khiến validator chỉ dùng được khi object nằm dưới thuộc tính `address`, và sai khi tái sử dụng trong `shippingAddress` hoặc `billingAddress`.

Giải pháp của Spring là giữ **đường dẫn hiện tại** trong `Errors`. Validator con chỉ sử dụng tên property tương đối như `"city"`. Validator cha chuyển ngữ cảnh trước khi gọi, rồi khôi phục sau khi gọi.

## 2. Các thành phần liên quan

| Thành phần | Trách nhiệm |
| --- | --- |
| `org.springframework.validation.Validator` | Định nghĩa `supports(Class<?>)` và `validate(Object, Errors)`; mã kiểm tra object và báo lỗi |
| `org.springframework.validation.Errors` | Nhận lỗi object/field; duy trì nested path và hỗ trợ tra cứu lỗi |
| `BindingResult` | Mở rộng `Errors` với thông tin kết quả binding, thường được dùng trong Spring MVC hoặc `DataBinder` |
| `BeanPropertyBindingResult` | Triển khai `BindingResult` dùng truy cập JavaBean, hỗ trợ field lồng nhau |
| `ValidationUtils.rejectIfEmptyOrWhitespace(...)` | Tra giá trị field và thêm lỗi khi giá trị `null`, rỗng hoặc chỉ có khoảng trắng |
| `ValidationUtils.invokeValidator(...)` | Kiểm tra target phù hợp với `supports(...)` rồi gọi validator tương ứng |

Chữ **nested path** ở đây là đường dẫn định danh một property bên trong object, không phải thư mục trên ổ đĩa, không phải URL và cũng không phải hành động tạo object con. Việc `pushNestedPath("address")` không tự gọi `getAddress()`, không gán dữ liệu vào field, không thay target gốc của `BeanPropertyBindingResult`; nó thay đổi **ngữ cảnh ghi/đọc lỗi theo tên field**.

## 3. `pushNestedPath`, `popNestedPath` và `getNestedPath`

### `pushNestedPath(String subPath)`

Đẩy đường dẫn hiện tại vào stack rồi chuyển sang đường dẫn con. Nếu đang ở root (`""`), gọi:

```java
errors.pushNestedPath("address");
```

thì `errors.getNestedPath()` trở thành `"address."`. Khi đang ở `"customer."` và push `"address"`, đường dẫn mới là `"customer.address."`. Spring quản lý dấu chấm phân tách; thông thường truyền **tên đoạn** `"address"`, không tự ghép `"."` vào mọi nơi.

Trong ngữ cảnh `"address."`, lệnh:

```java
errors.rejectValue("city", "required");
```

ghi một `FieldError` có `getField()` là `"address.city"`. Mã lỗi `"required"` là một mã logic để giải quyết thông điệp; nó **không phải** tên field.

### `popNestedPath()`

Khôi phục đường dẫn **ngay trước lần push tương ứng**:

```java
errors.pushNestedPath("address");
try {
    // Kiểm tra các field của address
} finally {
    errors.popNestedPath();
}
```

Sau khi pop, `getNestedPath()` trở lại `""` nếu trước đó đang ở root. Nếu trước push đang ở `"customer."`, kết quả được khôi phục thành `"customer."`; pop không nhất thiết đưa về root.

**Quy tắc bắt buộc:** một lần push thành công cần một lần pop tương ứng. Đặt pop trong `finally` để vẫn khôi phục đường dẫn khi validator con phát sinh exception. Nếu gọi `popNestedPath()` mà chưa có đường dẫn trước đó trong stack, Spring sẽ báo `IllegalStateException`.

### Bảng chuyển trạng thái của stack

| Hành động | `getNestedPath()` | Field tương đối `"city"` được hiểu là |
| --- | --- | --- |
| Ban đầu | `""` | `city` |
| `pushNestedPath("address")` | `"address."` | `address.city` |
| `pushNestedPath("billing")` | `"address.billing."` | `address.billing.city` |
| `popNestedPath()` | `"address."` | `address.city` |
| `popNestedPath()` | `""` | `city` |

Ví dụ mức `"address.billing."` chỉ minh họa cấu trúc đường dẫn; để `rejectValue("city", ...)` kiểm tra giá trị thành công với `BeanPropertyBindingResult`, object đích phải thật sự có property path tương ứng.

**Chú ý:** `popNestedPath()` chỉ khôi phục ngữ cảnh, **không xóa những `FieldError` đã ghi** và không hoàn tác giá trị object. Các lỗi mang tên `address.city` vẫn tồn tại sau khi trở về root.

## 4. Mẫu chuẩn khi một validator gọi validator con

Tách hai nhiệm vụ:

- `CustomerValidator` biết object gốc chứa field `address`.
- `AddressValidator` chỉ biết các thuộc tính của `Address`: `city`, `postalCode`.

Mẫu gọi quan trọng:

```java
if (customer.getAddress() == null) {
    errors.rejectValue("address", "address.required");
} else {
    errors.pushNestedPath("address");
    try {
        ValidationUtils.invokeValidator(
                addressValidator, customer.getAddress(), errors);
    } finally {
        errors.popNestedPath();
    }
}
```

Vì sao cần từng dòng:

1. **Kiểm tra `null` trước khi push.** Nếu `customer.getAddress()` chưa có object, ghi lỗi `address` ở cấp cha. Gọi validator con với `null` có thể không phù hợp với contract và sinh lỗi thay vì tạo `FieldError` hữu ích.
2. **Push đúng field của cha.** `"address"` là tên property trên `Customer`, không phải tên class `Address`.
3. **Truyền object con làm target cho validator con.** `ValidationUtils.invokeValidator(addressValidator, customer.getAddress(), errors)` sẽ kiểm tra tính tương thích qua `supports` rồi gọi `validate`.
4. **Truyền cùng một `Errors`.** Validator con thêm lỗi vào cùng kết quả gốc; nested path khiến field ngắn trở thành field đầy đủ.
5. **Pop trong `finally`.** Các phép kiểm tra tiếp theo của cha, chẳng hạn `"contactEmail"`, phải trở về cấp gốc. Nếu thiếu pop, `"contactEmail"` có thể bị hiểu nhầm thành `"address.contactEmail"`.

Với object con không rỗng, `AddressValidator` có thể viết độc lập:

```java
@Override
public void validate(Object target, Errors errors) {
    Address address = (Address) target;
    ValidationUtils.rejectIfEmptyOrWhitespace(
            errors, "city", "city.required");
    if (address.getPostalCode() == null
            || !address.getPostalCode().matches("\\d{5}")) {
        errors.rejectValue("postalCode", "postalCode.invalid");
    }
}
```

Ở đây validator con **không biết** mình đang phục vụ `address`, `shippingAddress` hay `billingAddress`. Nếu cha push tên nào trước khi gọi, lỗi được ghi với tiền tố tương ứng. `ValidationUtils.rejectIfEmptyOrWhitespace` tra cứu giá trị qua `Errors`, nên với `BeanPropertyBindingResult`, object gốc phải có đường dẫn tương ứng.

## 5. Ví dụ chạy được bằng Java 17 và Spring Framework

Ví dụ dùng **Spring Core Validation**, không cần chạy server web. Nó tạo `Customer`, dùng `BeanPropertyBindingResult` giữ kết quả, gọi hai validator và in những field có lỗi theo đúng thứ tự.

Tạo một thư mục dự án Gradle với cấu trúc:

```text
nested-validator-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/NestedValidationDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'nested-validator-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
}

application {
    mainClass = 'example.NestedValidationDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Spring Framework 6.x yêu cầu Java 17 trở lên; ví dụ cố định phiên bản `6.2.12` để môi trường chạy dễ tái lập. Gradle sẽ lấy các dependency bắc cầu của `spring-context` từ Maven Central. Dùng một JDK 17+ và Gradle tương thích; dự án có Gradle wrapper thì thay `gradle` bằng `./gradlew`.

**`src/main/java/example/NestedValidationDemo.java`**

```java
package example;

import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public class NestedValidationDemo {

    public static final class Address {
        private final String city;
        private final String postalCode;

        public Address(String city, String postalCode) {
            this.city = city;
            this.postalCode = postalCode;
        }

        public String getCity() {
            return city;
        }

        public String getPostalCode() {
            return postalCode;
        }
    }

    public static final class Customer {
        private final String fullName;
        private final Address address;
        private final String contactEmail;

        public Customer(
                String fullName, Address address, String contactEmail) {
            this.fullName = fullName;
            this.address = address;
            this.contactEmail = contactEmail;
        }

        public String getFullName() {
            return fullName;
        }

        public Address getAddress() {
            return address;
        }

        public String getContactEmail() {
            return contactEmail;
        }
    }

    public static final class AddressValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return Address.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Address address = (Address) target;

            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "city", "city.required");

            if (address.getPostalCode() == null
                    || !address.getPostalCode().matches("\\d{5}")) {
                errors.rejectValue("postalCode", "postalCode.invalid");
            }
        }
    }

    public static final class CustomerValidator implements Validator {
        private final Validator addressValidator = new AddressValidator();

        @Override
        public boolean supports(Class<?> type) {
            return Customer.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Customer customer = (Customer) target;

            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "fullName", "fullName.required");

            if (customer.getAddress() == null) {
                errors.rejectValue("address", "address.required");
            } else {
                errors.pushNestedPath("address");
                try {
                    ValidationUtils.invokeValidator(
                            addressValidator, customer.getAddress(), errors);
                } finally {
                    errors.popNestedPath();
                }
            }

            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "contactEmail", "contactEmail.required");
        }
    }

    public static void main(String[] args) {
        Customer customer = new Customer(
                "  ", new Address(" ", "12"), "");
        BeanPropertyBindingResult errors =
                new BeanPropertyBindingResult(customer, "customer");

        new CustomerValidator().validate(customer, errors);

        System.out.println(
                "nestedPathAfter=[" + errors.getNestedPath() + "]");
        System.out.println(
                "fields=" + errors.getFieldErrors().stream()
                        .map(FieldError::getField).toList());
        System.out.println(
                "fieldErrorCount=" + errors.getFieldErrorCount());

        Customer noAddress = new Customer(
                "Lan", null, "lan@example.org");
        BeanPropertyBindingResult missingErrors =
                new BeanPropertyBindingResult(noAddress, "customer");

        new CustomerValidator().validate(noAddress, missingErrors);
        System.out.println(
                "missingAddressFields="
                        + missingErrors.getFieldErrors().stream()
                                .map(FieldError::getField).toList());
    }
}
```

Chạy từ thư mục dự án:

```bash
gradle -q run
```

**Stdout dự kiến** (với JDK 17+ và dependency như trên):

```text
nestedPathAfter=[]
fields=[fullName, address.city, address.postalCode, contactEmail]
fieldErrorCount=4
missingAddressFields=[address]
```

Giải thích từng kết quả:

- `fullName` là field cấp gốc, chứa toàn khoảng trắng, bị `rejectIfEmptyOrWhitespace` từ chối.
- `address.city` là lỗi của field `city` trong `AddressValidator`, được gắn tiền tố `address.` nhờ `pushNestedPath`.
- `address.postalCode` là lỗi của `postalCode="12"`, không thỏa regex năm chữ số.
- `contactEmail` vẫn là field cấp gốc vì `popNestedPath()` đã chạy trước khi validator cha kiểm tra email.
- `nestedPathAfter=[]` chứng minh đường dẫn trở về chuỗi rỗng (`""`); không có chuyện lỗi đã ghi biến mất.
- Khi `address == null`, code ghi một lỗi cho field `address` và không gọi validator con, tránh kiểm tra property không tồn tại.

Các class mẫu có field `final` và getter, vì ví dụ **chỉ validate object đã được khởi tạo**. Chúng không cần setter để minh họa nested validation. Nếu dùng chính các class này làm đối tượng nhận **property binding** từ form, cần xem xét thêm constructor binding hoặc chọn DTO mutable có setter phù hợp. `pushNestedPath` không quyết định cách object được khởi tạo.

## 6. Vì sao không nên viết đường dẫn đầy đủ ngay trong validator con?

Xem hai cách viết:

```java
// Cách gắn cứng vị trí của Address trong Customer:
errors.rejectValue("address.city", "city.required");

// Cách tái sử dụng được trong AddressValidator:
errors.rejectValue("city", "city.required");
```

Ở root, cách thứ nhất có thể tạo lỗi `address.city`. Nhưng nếu cha **đã push `"address"`**, việc viết `"address.city"` trong validator con có nguy cơ dẫn đến `address.address.city`: đường dẫn đầy đủ bị ghép hai lần.

Với `AddressValidator` có tên field tương đối, cùng logic có thể dùng cho hai thuộc tính:

```java
errors.pushNestedPath("billingAddress");
try {
    ValidationUtils.invokeValidator(
            addressValidator, customer.getBillingAddress(), errors);
} finally {
    errors.popNestedPath();
}

errors.pushNestedPath("shippingAddress");
try {
    ValidationUtils.invokeValidator(
            addressValidator, customer.getShippingAddress(), errors);
} finally {
    errors.popNestedPath();
}
```

Hai đoạn này là **minh họa tích hợp**, giả định `Customer` có `getBillingAddress()` và `getShippingAddress()` trả về object không `null`; chúng không nằm trong chương trình độc lập ở phần 5. Khi đối tượng và đường dẫn hợp lệ, lỗi có dạng `billingAddress.city` hoặc `shippingAddress.city` mà không sửa code của `AddressValidator`.

Điểm mấu chốt: **validator con nhận target con nhưng ghi lỗi vào kết quả gốc với tiền tố động**. Nhờ vậy logic kiểm tra dữ liệu không phụ thuộc chặt vào vị trí chứa dữ liệu trong object cha.

## 7. Lồng nhiều cấp và tính chất LIFO

Với cây thuộc tính:

```text
Order
└── customer
    └── address
        └── city
```

Có thể push hai lần, rồi pop theo thứ tự ngược lại:

```java
errors.pushNestedPath("customer");
try {
    errors.pushNestedPath("address");
    try {
        errors.rejectValue("city", "city.required");
        // FieldError.field == "customer.address.city"
    } finally {
        errors.popNestedPath(); // Trở lại "customer."
    }
} finally {
    errors.popNestedPath(); // Trở lại ""
}
```

Đoạn trên **chỉ minh họa** cách đường dẫn được ghép; để chạy trực tiếp với `BeanPropertyBindingResult`, object gốc cần có getter cho `customer.address.city`. `Errors` có stack dạng LIFO (*last in, first out*): push sau thì pop trước.

Không được gọi một lần `popNestedPath()` với hy vọng xóa toàn bộ đường dẫn nhiều cấp; nó khôi phục **một tầng stack**. Nếu mỗi helper validate đều nhận cùng một `Errors`, helper nào tự push cũng phải tự pop, kể cả khi có exception.

## 8. `setNestedPath` khác gì `pushNestedPath`?

Cả hai liên quan tới ngữ cảnh property path nhưng khác cách quản lý trạng thái:

| Phương thức | Ý nghĩa | Khi nào dùng |
| --- | --- | --- |
| `setNestedPath("address")` | Đặt lại nested path hiện tại thành một đường dẫn xác định | Mã chủ động quản lý trạng thái, biết trước giá trị cần đặt |
| `pushNestedPath("address")` | Lưu đường dẫn hiện tại vào stack rồi đi xuống một nhánh | Một validator cha tạm thời gọi validator con |
| `popNestedPath()` | Lấy lại đường dẫn trước lần push gần nhất | Trả về trạng thái ban đầu trong `finally` |
| `getNestedPath()` | Xem nested path hiện tại, thường kết thúc bằng dấu chấm | Debug, test, kiểm tra trạng thái sau khi validate |

Với luồng validator lồng nhiều tầng, `pushNestedPath` + `popNestedPath` giúp tránh phải tự lưu chuỗi cũ rồi gọi `setNestedPath(oldPath)`. Đừng tùy tiện trộn `setNestedPath` với push/pop khi bạn chưa xác định rõ ai sở hữu trạng thái đường dẫn. Nếu nhiều validator chia sẻ một `Errors`, hãy giữ contract cân bằng push/pop.

## 9. Liên hệ với Spring MVC, DataBinder và Bean Validation

Trong Spring MVC, một controller có thể nhận:

```java
@PostMapping("/customers")
public String submit(
        @ModelAttribute("customer") CustomerForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "customer-form";
    }
    return "success";
}
```

Đây là **đoạn minh họa**, cần đặt trong một controller Spring MVC, import annotation/class phù hợp và cấu hình view. Để chạy Spring `Validator` thủ công, có thể gọi validator trong controller hoặc đăng ký với `WebDataBinder` theo phạm vi controller. Sau khi validator chạy, `BindingResult.getFieldErrors()` cho phép giao diện hiển thị lỗi của `address.city` cạnh input mang tên tương ứng. Tên field đầy đủ cũng giúp ánh xạ lỗi về form, JSON response hoặc các trường hợp kiểm thử.

Phân biệt các cơ chế:

- **Data binding**: đọc request, chuyển kiểu và gán vào object; có thể xuất hiện lỗi như `typeMismatch`.
- **Spring `Validator`**: triển khai `supports` và `validate`, có thể dùng `Errors.rejectValue(...)` cùng `pushNestedPath/popNestedPath`.
- **Jakarta Bean Validation**: dùng constraint như `@NotBlank`, `@Size`, `@Valid`; khi được Spring tích hợp, lỗi có thể xuất hiện trong `BindingResult`. Phần lớn trường hợp dùng cascade `@Valid` không đòi bạn tự gọi `pushNestedPath`.

Không nên gọi `pushNestedPath` chỉ để sửa lỗi tên field khi object thực tế không có thuộc tính con. Đường dẫn lỗi phải tương ứng với mô hình dữ liệu mà controller/binder và giao diện cùng hiểu.

## 10. Lỗi phổ biến và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Sau khi validate địa chỉ, lỗi email thành `address.contactEmail` | Thiếu `popNestedPath()` | Bọc validator con bằng `try/finally` |
| Một lỗi thành `address.address.city` | Validator con viết sẵn tiền tố `address.` dù cha đã push | Trong validator con chỉ dùng `"city"` |
| `IllegalStateException` khi pop | Gọi pop nhiều hơn số lần push thành công | Mỗi push thành công đi với một pop |
| `UnsupportedOperationException` khi push | Triển khai `Errors` đang dùng không hỗ trợ nested path | Dùng implementation phù hợp, như `BeanPropertyBindingResult`, và kiểm tra contract |
| Exception khi đọc `address.city` | `address == null` hoặc đường dẫn property không tồn tại/không truy cập được | Kiểm tra null, thiết kế model/getter đúng, báo lỗi field cha |
| `AddressValidator` từ chối target | `supports(Address.class)` trả false hoặc truyền nhầm class | Kiểm tra `supports` và object được chuyển cho validator |
| Lỗi hiển thị sai input | Tên field từ `FieldError.getField()` không khớp tên input | Đồng bộ tên form và property path |
| Lỗi con biến mất sau pop? | Hiểu nhầm pop là xóa lỗi | Pop chỉ đổi ngữ cảnh; xem `getFieldErrors()` |
| Validator đã push nhưng nhánh exception thoát sớm | Pop nằm cuối hàm thay vì `finally` | Đặt pop trong `finally` ngay sau push |
| Nhiều thread cùng dùng chung một `Errors` | `Errors` và trạng thái nested path được dùng như mutable context | Tạo hoặc lấy một kết quả riêng cho mỗi lượt validate, không chia sẻ giữa request/thread |

Một điểm tinh tế: `Errors.rejectValue(...)` và `ValidationUtils.rejectIfEmptyOrWhitespace(...)` làm việc với field path và có thể truy cập giá trị trên object để tạo thông tin lỗi. Nếu object lồng là `null` hoặc đường dẫn không tồn tại, việc chỉ thêm một prefix không thể chữa được cấu trúc đối tượng thiếu. Khi field con vắng mặt, thường tốt hơn là báo lỗi ở field cha trước khi đi xuống.

## 11. Kiểm thử đúng đường dẫn và bảo đảm luôn phục hồi

Với `CustomerValidator` ở ví dụ, có thể kiểm thử các bất biến sau:

1. Đối tượng sai `city` nhưng có `address` khác `null` → `getFieldError("address.city")` khác `null`.
2. Sai `postalCode` → `getFieldError("address.postalCode")` khác `null`.
3. Sai `contactEmail` sau khi validator con chạy → lỗi đúng tên `"contactEmail"`, không có tiền tố `"address."`.
4. Sau `validate` → `errors.getNestedPath().equals("")` khi bắt đầu từ root.
5. `address == null` → có lỗi `"address"`; validator con không được gọi.
6. Nếu validator con ném exception, mã cha vẫn phục hồi nested path nhờ `finally`; có thể kiểm tra bằng một fake validator cố tình ném `IllegalArgumentException`.

Ví dụ assertion cho một trường hợp sau khi gọi validator (Java 17, có thư viện Spring, đoạn code dùng biến `errors` như phần 5):

```java
assert errors.getFieldError("address.city") != null;
assert errors.getFieldError("address.postalCode") != null;
assert errors.getFieldError("contactEmail") != null;
assert errors.getNestedPath().isEmpty();
```

Lệnh `assert` trong Java bị tắt theo mặc định; muốn chạy các assertion này bằng JVM, bật `-ea` hoặc dùng JUnit/AssertJ trong một test thực tế. Khi kiểm tra riêng việc phục hồi sau exception, lưu ý assertion về số lỗi có thể khác tùy nơi validator con ném lỗi; bất biến quan trọng là đường dẫn đã được pop.

### Bài tự luyện

Cho `Order` có `billingAddress` và `shippingAddress`, cả hai cùng kiểu `Address` có `city`. Viết `AddressValidator` chỉ kiểm tra field tương đối `"city"`. Trong `OrderValidator`, gọi `pushNestedPath("billingAddress")` trước validator con thứ nhất và `pushNestedPath("shippingAddress")` trước validator con thứ hai; cả hai đều có `finally` pop. Nếu cả hai thành phố rỗng, giải thích vì sao nhận hai `FieldError` có tên khác nhau.

**Đáp án định hướng:** vì `Errors` ghép đường dẫn đang active với tên tương đối `"city"`, kết quả là `billingAddress.city` và `shippingAddress.city`. Khi mỗi lần pop hoàn tất, lần validate tiếp theo bắt đầu với context gốc. Đó là lợi ích quan trọng nhất của stack nested path: **tái sử dụng validator con và giữ tên lỗi chính xác trên object gốc**.

## Tài liệu tham khảo chính thức

- [Spring Framework — Validation Using Spring's Validator Interface](https://docs.spring.io/spring-framework/reference/core/validation/validator.html): mẫu validator con với `pushNestedPath` và `popNestedPath`.
- [Spring Framework — Errors API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/Errors.html): contract của nested-path stack, `getNestedPath`, `rejectValue` và `FieldError`.
- [Spring Framework — ValidationUtils API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/ValidationUtils.html): `invokeValidator` và `rejectIfEmptyOrWhitespace`.
- [Spring Framework — BeanPropertyBindingResult API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/BeanPropertyBindingResult.html): cơ chế quản lý lỗi và truy cập property JavaBean, kể cả nested property.
