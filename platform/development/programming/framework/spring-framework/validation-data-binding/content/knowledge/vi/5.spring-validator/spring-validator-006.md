# Tổ hợp validator bằng ủy quyền cho bộ kiểm tra con trong Spring Framework

Khi đối tượng đầu vào có nhiều phần, viết toàn bộ quy tắc kiểm tra trong một lớp `Validator` dễ tạo ra phương thức dài, phụ thuộc chặt vào cấu trúc dữ liệu và khó tái sử dụng. Spring cho phép **validator cha (composite/parent validator)** ủy quyền các quy tắc riêng cho **validator con (delegate/child validator)**. Mỗi validator con biết cách kiểm tra một đối tượng hoặc một nhóm quy tắc; validator cha điều phối lời gọi và tập hợp lỗi.

Bài này tập trung vào **`org.springframework.validation.Validator`**, `Errors`, `ValidationUtils.invokeValidator(...)` và đường dẫn lỗi lồng nhau. Đây là cách tổ hợp validator theo giao diện Spring; khác với cơ chế validation lồng nhau tự động của Jakarta Bean Validation qua `@Valid`.

## 1. Vì sao cần tổ hợp validator?

Giả sử biểu mẫu tạo khách hàng có dữ liệu:

```text
Customer
├── firstName
├── email
└── address
    ├── city
    └── postalCode
```

Có hai nhóm trách nhiệm: thông tin khách hàng (`firstName`, `email`) và địa chỉ (`city`, `postalCode`). Thay vì ép `CustomerValidator` biết tất cả các trường, ta tách thành:

- `CustomerFieldsValidator` chỉ kiểm tra các trường đơn giản của `Customer`.
- `AddressValidator` chỉ kiểm tra `Address` và không cần biết nó đang nằm bên trong `Customer`.
- `CustomerValidator` kiểm tra điều kiện kết hợp (ví dụ `address` bắt buộc) rồi **ủy quyền** cho hai validator con.

```text
                           CustomerValidator
                          /                 \
               cùng đối tượng          đối tượng lồng nhau
                       /                       \
     CustomerFieldsValidator              AddressValidator
            Customer                          Address
                       \                       /
                        \                     /
                        cùng một Errors / BindingResult
                              |
                     firstName, email,
                   address.city, address.postalCode
```

Tất cả lỗi được gom trong **một bộ `Errors` thuộc đối tượng gốc**. Tầng gọi (controller, service hoặc chương trình kiểm thử) không phải ghép các danh sách lỗi thủ công.

## 2. Hợp đồng của Spring Validator

Giao diện cơ bản có hai phương thức:

```java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
```

Đây là **chữ ký rút gọn để học**, `Validator` thực tế nằm trong thư viện Spring. `supports` cho biết validator có chấp nhận kiểu dữ liệu đầu vào không. `validate` ghi lỗi vào đối tượng `Errors` mà phía gọi truyền vào; giá trị trả về là `void`, không phải `boolean`.

Cách cài đặt thông dụng:

```java
@Override
public boolean supports(Class<?> clazz) {
    return Customer.class.isAssignableFrom(clazz);
}
```

Chiều kiểm tra `Customer.class.isAssignableFrom(clazz)` cho phép nhận `Customer` và các lớp con của nó. Đảo chiều hai vế có thể khiến validator nhận sai kiểu. `supports` cần phù hợp với kiểu đối tượng thực mà `validate` ép kiểu.

`Errors` cung cấp hai cách ghi lỗi:

- `errors.rejectValue("email", "email.required", "Email is required")`: lỗi của một trường. Kết quả thường là `FieldError`, có đường dẫn trường và mã lỗi.
- `errors.reject("customer.invalid", "Customer is invalid")`: lỗi ở cấp đối tượng, không gắn một trường riêng (thường gọi là *global error*).

Ngoài ra, `ValidationUtils.rejectIfEmptyOrWhitespace(...)` là tiện ích kiểm tra trường `null`, rỗng hoặc chỉ toàn khoảng trắng, rồi gọi `rejectValue` khi cần. Mã lỗi như `email.required` có thể được ánh xạ qua `MessageSource` để tạo thông báo phù hợp ngôn ngữ; thông báo mặc định trong ví dụ giúp kết quả dễ đọc khi chưa cấu hình bundle.

## 3. Hai kiểu ủy quyền phải phân biệt

### 3.1. Ủy quyền cùng đối tượng (same-target delegation)

Nhiều validator cùng nhận `Customer` nhưng kiểm tra các nhóm quy tắc khác nhau:

```java
ValidationUtils.invokeValidator(customerFieldsValidator, customer, errors);
```

Bộ lỗi vẫn đang ở đường dẫn gốc (`errors.getNestedPath()` thường là `""`), nên validator con có thể gọi `rejectValue("firstName", ...)` trực tiếp.

`ValidationUtils.invokeValidator(...)` thực hiện kiểm tra tương thích qua `supports` trước khi gọi `validate`. Nếu validator không hỗ trợ kiểu đối tượng, đó là **lỗi cấu hình/lập trình** và nó có thể ném `IllegalArgumentException`; không nên biến nhầm lỗi này thành “đầu vào không hợp lệ”.

### 3.2. Ủy quyền cho đối tượng con (nested-object delegation)

`AddressValidator` chỉ biết các tên trường `city` và `postalCode` của `Address`. Để đưa lỗi vào đúng nhánh `address` của `Customer`, validator cha tạm thêm tiền tố vào `Errors`:

```java
errors.pushNestedPath("address");
try {
    ValidationUtils.invokeValidator(addressValidator, customer.getAddress(), errors);
} finally {
    errors.popNestedPath();
}
```

Nhờ đó, khi `AddressValidator` ghi lỗi trường `city`, bộ lỗi gốc nhận đường dẫn **`address.city`**. `pushNestedPath` và `popNestedPath` chỉ đổi **ngữ cảnh đường dẫn lỗi**, không đổi đối tượng gốc mà `Errors` đang liên kết. Với `BeanPropertyBindingResult`, `getFieldValue("city")` dưới đường dẫn này truy cập thuộc tính `address.city` từ đối tượng gốc.

Phải dùng `try/finally` để luôn khôi phục đường dẫn, kể cả khi validator con ném exception. Nếu quên `popNestedPath`, lỗi ghi sau đó có thể bị gắn nhầm tiền tố `address.`.

**Quan trọng:** Nếu `customer.getAddress() == null`, phải quyết định rõ đó có là lỗi bắt buộc hay không rồi **không gọi** `AddressValidator` với `null`. Ví dụ dưới đây ghi `address.required` một lần; nếu địa chỉ không bắt buộc, có thể bỏ qua validation của nhánh đó.

## 4. Ví dụ hoàn chỉnh, chạy được trên Java 17 và Spring 6

Ví dụ sau chạy trong ứng dụng console, không cần Spring Boot, máy chủ HTTP hoặc Bean Validation provider. Nó minh họa trực tiếp `org.springframework.validation.Validator` và cách ủy quyền, nên giúp quan sát lỗi rõ ràng trước khi tích hợp vào MVC.

Tạo dự án Gradle với `settings.gradle`:

```groovy
rootProject.name = 'spring-validator-composition'
```

Và `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.validation.ValidationCompositionDemo'
}
```

Thư viện `spring-context` chứa các lớp `org.springframework.validation` dùng trong ví dụ và kéo theo những thành phần Spring cần thiết. Nếu dự án đã dùng Spring Boot và cơ chế quản lý phiên bản dependency, nên dùng phiên bản Spring Framework do Boot quản lý thay vì gắn cứng phiên bản như trong dự án console độc lập này.

Tạo tệp `src/main/java/demo/validation/ValidationCompositionDemo.java`:

```java
package demo.validation;

import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public class ValidationCompositionDemo {

    // JavaBean đơn giản: BeanPropertyBindingResult đọc thuộc tính qua getter.
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
        private final String firstName;
        private final String email;
        private final Address address;

        public Customer(String firstName, String email, Address address) {
            this.firstName = firstName;
            this.email = email;
            this.address = address;
        }

        public String getFirstName() {
            return firstName;
        }

        public String getEmail() {
            return email;
        }

        public Address getAddress() {
            return address;
        }
    }

    // Validator con A: cùng đối tượng Customer.
    static final class CustomerFieldsValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return Customer.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "firstName", "firstName.required",
                    "First name is required");
            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "email", "email.required",
                    "Email is required");
        }
    }

    // Validator con B: chỉ biết đối tượng Address.
    static final class AddressValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return Address.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "city", "city.required",
                    "City is required");
            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "postalCode", "postalCode.required",
                    "Postal code is required");
        }
    }

    // Validator cha: phối hợp hai trách nhiệm bằng ủy quyền.
    static final class CustomerValidator implements Validator {
        private final Validator customerFieldsValidator;
        private final Validator addressValidator;

        public CustomerValidator(Validator customerFieldsValidator,
                                 Validator addressValidator) {
            this.customerFieldsValidator =
                    Objects.requireNonNull(customerFieldsValidator);
            this.addressValidator = Objects.requireNonNull(addressValidator);

            if (!customerFieldsValidator.supports(Customer.class)) {
                throw new IllegalArgumentException(
                        "Customer fields validator must support Customer");
            }
            if (!addressValidator.supports(Address.class)) {
                throw new IllegalArgumentException(
                        "Address validator must support Address");
            }
        }

        @Override
        public boolean supports(Class<?> type) {
            return Customer.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Customer customer = (Customer) target;

            // Cùng target, không cần thay đổi nested path.
            ValidationUtils.invokeValidator(
                    customerFieldsValidator, customer, errors);

            Address address = customer.getAddress();
            if (address == null) {
                errors.rejectValue("address", "address.required",
                        "Address is required");
                return;
            }

            // Khác target: đổi ngữ cảnh lỗi sang nhánh address.
            errors.pushNestedPath("address");
            try {
                ValidationUtils.invokeValidator(
                        addressValidator, address, errors);
            } finally {
                errors.popNestedPath();
            }
        }
    }

    public static void main(String[] args) {
        Validator customerValidator = new CustomerValidator(
                new CustomerFieldsValidator(),
                new AddressValidator());

        List<Customer> samples = List.of(
                new Customer("An", "an@example.com",
                        new Address("Hanoi", "10000")),
                new Customer(" ", "", new Address(" ", "")),
                new Customer("Mai", "mai@example.com", null));

        for (int index = 0; index < samples.size(); index++) {
            Customer customer = samples.get(index);
            BeanPropertyBindingResult errors =
                    new BeanPropertyBindingResult(customer, "customer");

            ValidationUtils.invokeValidator(
                    customerValidator, customer, errors);

            // Kiểm tra parent đã khôi phục nested path.
            if (!errors.getNestedPath().isEmpty()) {
                throw new IllegalStateException("Nested path was not reset");
            }

            List<FieldError> fieldErrors = errors.getFieldErrors()
                    .stream()
                    .sorted(Comparator.comparing(FieldError::getField))
                    .toList();

            System.out.println("Sample " + (index + 1) + ": "
                    + fieldErrors.size() + " error(s)");
            for (FieldError error : fieldErrors) {
                System.out.println("  " + error.getField()
                        + " -> " + error.getDefaultMessage());
            }
        }
    }
}
```

Chạy bằng Gradle Wrapper nếu dự án có wrapper (`./gradlew run` trên Unix hoặc `gradlew.bat run` trên Windows); nếu đã cài Gradle và không dùng wrapper, chạy `gradle run`. Gradle tải các dependency từ Maven Central nếu môi trường cho phép.

Đầu ra của phương thức `main`, bên cạnh dòng tác vụ do Gradle tự in:

```text
Sample 1: 0 error(s)
Sample 2: 4 error(s)
  address.city -> City is required
  address.postalCode -> Postal code is required
  email -> Email is required
  firstName -> First name is required
Sample 3: 1 error(s)
  address -> Address is required
```

Đầu ra được sắp xếp bằng `Comparator.comparing(FieldError::getField)` để ví dụ có thứ tự ổn định. Bản thân Spring không cam kết sắp xếp `FieldError` theo thứ tự tên trường.

### Phân tích kết quả từng trường hợp

**Sample 1:** `CustomerFieldsValidator` không ghi lỗi; `AddressValidator` cũng không ghi lỗi. Cả hai đã được gọi thông qua validator cha trên cùng một `Errors`, nên `getFieldErrors()` rỗng.

**Sample 2:** `firstName` và `email` trống ở đối tượng gốc; `city` và `postalCode` chỉ chứa khoảng trắng hoặc rỗng ở địa chỉ. Tổng cộng **4 lỗi**, trong đó hai lỗi lồng nhau có tiền tố `address.`. Nếu quên `pushNestedPath`, validator con sẽ tìm `city`/`postalCode` ở đối tượng `Customer` và có thể gây lỗi truy cập thuộc tính hoặc gắn sai đường dẫn.

**Sample 3:** `address == null`. Validator cha ghi đúng **một lỗi** ở `address` và không ủy quyền sang `AddressValidator`. Vì vậy không có lỗi `address.city` hoặc `address.postalCode` được tạo ra từ một địa chỉ không tồn tại.

## 5. Đi sâu vào cơ chế gom lỗi

Trong ví dụ, `BeanPropertyBindingResult(customer, "customer")` giữ tham chiếu đến **Customer gốc**. Khi validator cha lần lượt gọi validator con, cả hai nhận chính instance `errors` này. Mỗi lệnh `rejectValue` thêm một `FieldError` với thông tin hữu ích:

| Thuộc tính của FieldError | Ý nghĩa |
| --- | --- |
| `getField()` | Tên trường đầy đủ, ví dụ `address.city`. |
| `getCode()` và `getCodes()` | Mã lỗi được giải quyết bởi `MessageCodesResolver`, có thể gồm biến thể theo tên đối tượng/trường/kiểu. |
| `getDefaultMessage()` | Thông báo dự phòng trong ví dụ. |
| `getRejectedValue()` | Giá trị không hợp lệ khi có thể xác định; cần chú ý khi log hay trả lỗi vì có thể nhạy cảm. |
| `getObjectName()` | Tên đối tượng gốc, ở đây là `customer`. |

`errors.hasErrors()` trả lời có bất kỳ lỗi nào; `errors.hasFieldErrors("address.city")` hoặc `errors.getFieldErrors("address.city")` giúp kiểm tra đúng nhánh. `errors.getGlobalErrors()` chỉ chứa lỗi cấp đối tượng, không thay thế `getFieldErrors()`.

Lưu ý rằng `Errors` **không an toàn cho đa luồng**: mỗi lần kiểm tra cần một instance riêng. Validator không lưu `Errors` hay đối tượng request vào field dùng chung; nhờ vậy các validator kiểu singleton trong Spring có thể tái sử dụng giữa các request nếu bản thân các phụ thuộc của chúng an toàn.

## 6. Tổ hợp nhiều validator cùng kiểu thành một bộ

Không phải lúc nào dữ liệu cũng có quan hệ cha–con. Đôi khi bạn muốn một tập validator đều kiểm tra cùng loại `Customer`: một lớp kiểm tra tên, một lớp kiểm tra email và một lớp kiểm tra quy tắc nhất quán giữa hai trường.

Có thể tổ chức danh sách các validator con và lần lượt gọi chúng qua `ValidationUtils.invokeValidator(...)`. Đoạn sau là **biến thể cấu trúc**, minh họa riêng, không cần thêm vào chương trình hoàn chỉnh phía trên:

```java
final class CompositeCustomerValidator implements Validator {
    private final List<Validator> delegates;

    CompositeCustomerValidator(List<Validator> delegates) {
        this.delegates = List.copyOf(delegates);
        for (Validator delegate : this.delegates) {
            if (!delegate.supports(ValidationCompositionDemo.Customer.class)) {
                throw new IllegalArgumentException(
                        "Delegate must support Customer");
            }
        }
    }

    @Override
    public boolean supports(Class<?> type) {
        return ValidationCompositionDemo.Customer.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        for (Validator delegate : delegates) {
            ValidationUtils.invokeValidator(delegate, target, errors);
        }
    }
}
```

Để biên dịch độc lập đoạn biến thể này, cần thêm imports cho `java.util.List`, `org.springframework.validation.Validator`, `Errors`, `ValidationUtils` và đặt trong package truy cập được `ValidationCompositionDemo.Customer`. Mỗi delegate trong danh sách phải **hỗ trợ cùng đối tượng `Customer`**. Không đưa `AddressValidator` trực tiếp vào danh sách cùng-target rồi truyền `Customer`: `supports` sẽ từ chối. Với validator của đối tượng lồng nhau, vẫn phải có nhánh ủy quyền và `pushNestedPath` như ví dụ chính.

Không tự động bỏ qua một delegate chỉ vì các delegate trước đã ghi lỗi. Việc có chạy toàn bộ để báo các lỗi cùng lúc hay dừng sớm vì lý do cụ thể là quyết định thiết kế. Dừng sớm thường làm giao diện khó sử dụng vì người dùng chỉ thấy từng lỗi lần lượt. Tuy nhiên, nên bỏ qua bước phụ thuộc vào dữ liệu chưa tồn tại hoặc chưa hợp lệ để tránh exception và thông báo sai.

## 7. Kiểm tra đường dẫn lồng nhau cho danh sách và nhiều cấp

Nếu đối tượng cha có địa chỉ giao hàng `shippingAddress` và địa chỉ thanh toán `billingAddress`, cùng một `AddressValidator` có thể được dùng lại cho từng nhánh. Mỗi lần cần thiết lập đúng đường dẫn trước khi ủy quyền:

```java
errors.pushNestedPath("shippingAddress");
try {
    ValidationUtils.invokeValidator(addressValidator,
            order.getShippingAddress(), errors);
} finally {
    errors.popNestedPath();
}

errors.pushNestedPath("billingAddress");
try {
    ValidationUtils.invokeValidator(addressValidator,
            order.getBillingAddress(), errors);
} finally {
    errors.popNestedPath();
}
```

Đoạn này là minh họa cú pháp cho một đối tượng `order` và validator đã được khai báo ở nơi khác; chỉ gọi khi từng địa chỉ **không null**. Đường dẫn trong kết quả lần lượt có dạng `shippingAddress.city` và `billingAddress.city`. Có thể đưa kiểm tra null thành một hàm phụ để không lặp mã, nhưng đường dẫn và chính sách bắt buộc của từng nhánh vẫn phải rõ ràng.

Với cấu trúc sâu hơn, gọi `pushNestedPath("shippingAddress")` rồi `pushNestedPath("contact")` tạo đường dẫn có dạng `shippingAddress.contact.*`; phải cân bằng từng `push` với một `pop` trong `finally`. Với collection, đường dẫn có thể bao gồm index như `items[0].code`, nhưng cần bảo đảm đối tượng gốc và `Errors` hỗ trợ truy cập thuộc tính tương ứng.

Nếu bạn đã sử dụng `DirectFieldBindingResult` thay cho `BeanPropertyBindingResult` thì cách đọc giá trị trường dựa trên field thay vì getter. Chọn cơ chế binding phù hợp cấu trúc dữ liệu, nhất quán với cách Spring đọc các thuộc tính cần kiểm tra.

## 8. Tích hợp vào DataBinder và Spring MVC

### 8.1. DataBinder thuần

Khi không muốn tự tạo `BindingResult`, bạn cũng có thể đăng ký validator cha cho `DataBinder`:

```java
Customer customer = new Customer(
        " ", "", new Address("", ""));

DataBinder binder = new DataBinder(customer, "customer");
binder.setValidator(new CustomerValidator(
        new CustomerFieldsValidator(), new AddressValidator()));
binder.validate();

BindingResult result = binder.getBindingResult();
// result.getFieldErrors() chứa lỗi từ các validator con.
```

Đây là **đoạn trích**, cần dùng các lớp `Customer`, `Address` và validator trong ví dụ, cùng imports của Spring cho `DataBinder` và `BindingResult`. Trong file ví dụ, các validator được khai báo bên trong `ValidationCompositionDemo` nên phải gọi đúng tên lồng nhau hoặc đặt đoạn mã trong cùng lớp. Kết quả của `binder.validate()` được gom về một `BindingResult`; với code này, việc binding giá trị HTTP chưa diễn ra vì ta truyền sẵn đối tượng Java.

### 8.2. Ở controller của Spring MVC

Khi đã có Spring bean `CustomerValidator`, có thể thêm nó vào binder của một controller bằng `@InitBinder`:

```java
@InitBinder("customer")
void initCustomerBinder(WebDataBinder binder) {
    binder.addValidators(customerValidator);
}
```

Đây là **đoạn cấu hình trong controller**, giả định `customerValidator` đã được tiêm vào constructor và hỗ trợ đối tượng được bind với tên `customer`. Một tham số như `@Valid @ModelAttribute("customer") CustomerForm form` sẽ kích hoạt validation trong luồng MVC và đặt lỗi vào `BindingResult` nếu chữ ký controller khai báo `BindingResult` ngay sau tham số cần kiểm tra. Trong ứng dụng thực tế, `CustomerForm` cần là kiểu có thể bind từ request và được validator hỗ trợ; lớp `Customer` immutable dùng trong demo console không có setter nên không phải ví dụ điển hình cho form binding.

`binder.addValidators(...)` bổ sung validator vào những validator hiện có; `binder.setValidator(...)` thay thế validator đang đặt. Dùng `addValidators` khi muốn kết hợp kiểm tra đang có (chẳng hạn Bean Validation) với quy tắc Spring Validator; tránh chạy một quy tắc hai lần bằng hai cơ chế khác nhau. `@InitBinder` có phạm vi theo controller/đối tượng mà nó áp dụng, không tự biến validator thành toàn cục.

Spring cũng hỗ trợ kiểm tra từ `@RequestBody` và Jakarta Bean Validation. Tuy nhiên, việc dùng `@Valid` cho một trường lồng nhau trong DTO của Jakarta **không tự gọi** một lớp `org.springframework.validation.Validator` do bạn viết. Muốn có hành vi ủy quyền kiểu bài này, cần đăng ký/triệu gọi validator Spring trong luồng phù hợp.

## 9. Cách thiết kế tổ hợp dễ bảo trì

**Mỗi validator chỉ chịu trách nhiệm về một nhóm quy tắc có lý do thay đổi riêng.** `AddressValidator` chỉ biết cấu trúc và ràng buộc của `Address`; nó không cần biết cha là `Customer`, `Order` hay một đối tượng khác. Validator cha chỉ kiểm tra sự tồn tại của nhánh, chọn delegate và thiết lập đường dẫn.

**Kiểm tra `supports` ngay khi lắp ghép.** Constructor của validator cha từ chối một delegate không hỗ trợ kiểu cần kiểm tra, nên lỗi cấu hình được phát hiện sớm. `ValidationUtils.invokeValidator` còn kiểm tra lại tương thích ở thời điểm gọi.

**Không tạo lại delegate cho mỗi request.** Khi dùng Spring IoC, có thể khai báo các validator là bean, tiêm qua constructor, và để validator cha gọi chúng. Các validator nên không mang trạng thái mutable của request; `Errors` phải được tạo riêng cho mỗi lần kiểm tra.

**Phân biệt kiểm tra đầu vào và kiểm tra nghiệp vụ.** Kiểm tra trường bắt buộc hoặc quan hệ cục bộ giữa các trường thích hợp ở `Validator`. Những phép kiểm tra phụ thuộc cơ sở dữ liệu, danh tính, transaction hoặc tình trạng tài nguyên thường phải nằm ở service/domain phù hợp; tránh gọi API mạng chậm hoặc truy cập dữ liệu không kiểm soát bên trong validator dùng khi bind biểu mẫu.

**Đặt mã lỗi ổn định.** Sử dụng mã như `address.required` và thông báo được giải quyết qua `MessageSource`, thay vì để phía client phụ thuộc vào một chuỗi tiếng Anh cố định. Khi xây API, không ghi/hiển thị lại `rejectedValue` nếu có mật khẩu, mã định danh nhạy cảm hoặc dữ liệu riêng tư.

## 10. Kiểm thử các tình huống quan trọng

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Đối tượng hợp lệ | Không có `FieldError` hoặc lỗi cấp đối tượng. |
| Trường gốc trống | Lỗi gắn đúng `firstName`/`email`. |
| Trường địa chỉ trống | Lỗi gắn đúng `address.city`/`address.postalCode`. |
| Địa chỉ `null` | Chỉ có lỗi `address` nếu nhánh đó bắt buộc; không ném exception. |
| Nhiều lỗi ở nhiều nhánh | Tất cả có mặt trong **cùng một** `BindingResult`. |
| Một delegate sai kiểu | Bị từ chối bằng lỗi cấu hình thay vì trả lỗi nhập liệu. |
| Delegate gây exception | `errors.getNestedPath()` được khôi phục nhờ `finally`. |
| Chạy đồng thời nhiều request | Không chia sẻ `Errors`/đối tượng request giữa các luồng. |
| Dùng `@InitBinder` | Validator được gắn đúng object name; lỗi có thể truy cập qua `BindingResult`. |

Khi dùng JUnit, nên kiểm tra trực tiếp `errors.hasFieldErrors("address.city")`, `errors.getFieldErrorCount()` và `errors.getNestedPath()`. Không kiểm tra thứ tự trả về của lỗi nếu chương trình không có bước sắp xếp rõ ràng.

## 11. Các lỗi phổ biến và cách khắc phục

1. **Truyền sai kiểu cho delegate:** `AddressValidator` cần `Address`, không nhận `Customer`. Kiểm tra `supports` và lời gọi `invokeValidator`.
2. **Quên `pushNestedPath`:** `AddressValidator` gọi `rejectValue("city", ...)` nhưng `Errors` đang trỏ về gốc; đường dẫn lỗi sai hoặc việc đọc giá trị trường thất bại.
3. **Quên `popNestedPath`:** các lỗi ghi sau bị dính tiền tố của nhánh trước. Luôn đặt `pop` trong `finally`.
4. **Gọi validator con với `null`:** validator ép kiểu/đọc thuộc tính có thể gây lỗi. Quyết định chính sách `null` ở validator cha.
5. **Mỗi delegate tạo một `Errors` riêng và bỏ qua kết quả:** tầng gọi không nhìn thấy đủ lỗi. Truyền chung một `Errors` khi cấu trúc cho phép.
6. **Dùng `reject(...)` cho một lỗi trường:** lỗi chỉ nằm ở cấp đối tượng. Dùng `rejectValue(...)` để có `FieldError` gắn đúng field.
7. **Gộp quy tắc lặp lại:** cùng một trường bị kiểm tra hai lần bởi hai delegate, sinh hai lỗi giống nhau. Quy hoạch trách nhiệm không trùng lặp.
8. **Nhầm `@Valid` với Spring Validator:** `@Valid` của Jakarta không tự thực thi các lớp delegate Spring tùy chỉnh chưa được đăng ký.
9. **Chia sẻ `Errors` trong bean singleton:** trạng thái lỗi giữa các request có thể chồng lên nhau. Validator giữ phụ thuộc; `Errors` sống theo từng request.
10. **Không kiểm tra lỗi binding/chuyển kiểu:** validator không thay thế được việc chuyển dữ liệu từ chuỗi HTTP thành kiểu Java phù hợp.

## 12. Câu hỏi tự luyện

1. Nếu `CustomerValidator` gọi `AddressValidator` mà không dùng `pushNestedPath("address")`, chuyện gì có thể xảy ra khi validator con kiểm tra trường `city`?
2. Vì sao cần `try/finally` ngay cả khi `AddressValidator` chỉ có vài dòng?
3. Nếu cùng một `AddressValidator` được tái sử dụng cho địa chỉ giao hàng và địa chỉ thanh toán, cần thay đổi điều gì trong đường dẫn của `Errors`?
4. Khi `address == null`, validator cha nên ghi lỗi gì, và khi nào có thể bỏ qua?
5. Một danh sách validator con cùng kiểm tra `Customer` khác gì việc ủy quyền cho `AddressValidator`?
6. Khi nào nên kiểm tra thông tin trong Spring Validator và khi nào cần kiểm tra ở service/domain?

Nếu tự giải thích được rằng **validator cha quyết định gọi ai và thiết lập ngữ cảnh, validator con xử lý quy tắc riêng, còn `Errors` tích lũy tất cả kết quả**, bạn đã nắm cơ chế tổ hợp bằng ủy quyền.

**Tham khảo:**
- [Spring Framework 6.2 — Validation Using Spring's Validator Interface](https://docs.spring.io/spring-framework/reference/6.2/core/validation/validator.html)
- [Spring Framework 6.2 — Resolving Codes to Error Messages](https://docs.spring.io/spring-framework/reference/6.2/core/validation/conversion.html)
- [Spring — ValidationUtils Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/ValidationUtils.html)
- [Spring — Errors Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/Errors.html)
