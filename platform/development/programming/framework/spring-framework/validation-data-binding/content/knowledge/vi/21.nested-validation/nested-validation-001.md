# `@Valid` trên thuộc tính tham chiếu tới đối tượng con trong Bean Validation

## 1. Mục tiêu và tình huống thực tế

Trong ứng dụng Spring, một đối tượng nhận dữ liệu thường chứa các đối tượng con. Ví dụ `OrderForm` chứa `Customer`, còn `Customer` chứa `Address`:

```text
OrderForm
├── orderCode
└── customer                  <- @Valid trên thuộc tính tham chiếu
    ├── name                  <- @NotBlank
    └── address               <- @Valid trên thuộc tính tham chiếu
        ├── city              <- @NotBlank
        └── zip               <- @Pattern
```

Khi validate `OrderForm`, các constraint nằm trên `Customer` hoặc `Address` **không tự động được duyệt chỉ vì các object đó có mặt trong Java object graph**. `@Valid` đánh dấu điểm cần **cascaded validation** (kiểm tra lan truyền), để Bean Validation đi tiếp từ đối tượng cha sang đối tượng con. Mỗi cạnh tham chiếu cần đi qua đều phải được đánh dấu phù hợp nếu muốn validation tiếp tục sâu hơn.

Ví dụ:

```java
public class OrderForm {
    @Valid
    private Customer customer;
}

public class Customer {
    @NotBlank
    private String name;

    @Valid
    private Address address;
}

public class Address {
    @NotBlank
    private String city;
}
```

Đây là **đoạn minh họa cấu trúc**, chưa phải chương trình Java độc lập; cần import `jakarta.validation.Valid`, `jakarta.validation.constraints.NotBlank` và các class tương ứng. Khi cả `OrderForm.customer` và `Customer.address` đều có `@Valid`, gọi `validator.validate(order)` có thể phát hiện `customer.name` và `customer.address.city` cùng với các lỗi ở đối tượng gốc.

Sau bài này, bạn cần:
- Nắm được ý nghĩa của `@Valid` trên **field/getter tham chiếu tới bean con** và cách đi qua nhiều cấp.
- Phân biệt `@Valid` với `@NotNull`, constraint đặt trực tiếp trên field, và `@Validated`/validation groups.
- Đọc đúng đường dẫn lỗi (`ConstraintViolation.getPropertyPath()`) ở object lồng nhau và trong Spring `BindingResult`.
- Hiểu sự khác nhau giữa validate một object bằng Jakarta Validation và binding/validation trong Spring MVC.
- Viết được kiểm thử đối tượng con hợp lệ, không hợp lệ, `null`, bỏ sót `@Valid`, collections và trường hợp vòng tham chiếu.

Phạm vi trọng tâm là **kiểm tra lồng nhau qua thuộc tính tham chiếu**. Ví dụ về collection và group conversion sẽ hỗ trợ hiểu cơ chế nhưng không thay thế tình huống field trỏ đến một bean con.

## 2. `@Valid` là gì, và nó không phải gì?

API Jakarta:

```java
import jakarta.validation.Valid;
```

`@Valid` là **marker annotation để yêu cầu lan truyền validation** vào đối tượng được tham chiếu. Nó không có thuộc tính `message`, `value`, `groups` hay `payload` như những constraint kiểu `@NotBlank`, `@Min` hoặc `@Size`; bản thân `@Valid` **không tạo ra lỗi “invalid”**.

Xem hai kiểu annotation:

```java
@NotNull(message = "Customer is required")
@Valid
private Customer customer;
```

- `@NotNull` kiểm tra bản thân thuộc tính `customer` có khác null hay không.
- `@Valid` yêu cầu validate constraint **bên trong** instance `Customer` nếu instance tồn tại.
- Nếu `customer == null`, Jakarta Bean Validation **bỏ qua cascading**, không đi sâu, nên chỉ `@NotNull` sinh vi phạm.
- Nếu `customer != null` nhưng `customer.name` trống, chỉ có `@Valid` trên cạnh `customer` mới khiến validator được gọi từ `OrderForm` đi tới `@NotBlank` ở `Customer.name`.
- Nếu `customer != null` và mọi constraint trong `Customer` hợp lệ, `@Valid` không sinh thêm vi phạm.

Đối chiếu bốn trường hợp:

| Khai báo | `customer == null` | `customer.name` vi phạm |
| --- | --- | --- |
| `private Customer customer;` | Không lỗi từ field này | Không được duyệt đến `Customer` |
| `@NotNull private Customer customer;` | Có lỗi `customer` | Không được duyệt đến `Customer` |
| `@Valid private Customer customer;` | Không lỗi do `@Valid` | Có lỗi `customer.name` |
| `@NotNull @Valid private Customer customer;` | Có lỗi `customer` | Có lỗi `customer.name` khi object con tồn tại |

Vì vậy, **`@Valid` không đồng nghĩa `@NotNull`**. Nếu API bắt buộc có đối tượng địa chỉ, phải nêu rõ yêu cầu bằng `@NotNull` trên tham chiếu. Việc thêm `@NotNull` bên trong `Address.city` không làm `address == null` bị bắt lỗi, vì lúc đó `Address` không được duyệt.

### 2.1. `@Valid` trên field hay getter?

Cả khai báo trên field và getter JavaBean đều là các vị trí hỗ trợ trong Jakarta Validation:

```java
@Valid
private Address address;

// Hoặc theo phong cách property:
@Valid
public Address getAddress() {
    return address;
}
```

Hai đoạn trên dùng để minh họa **hai cách thay thế**; trong thực tế nên chọn quy ước rõ ràng cho model. Đừng đặt annotation trùng lặp ở cả field và getter một cách vô ý rồi tưởng việc duyệt sẽ theo thứ tự hai lần có ích. Provider xác định cách khai báo và metadata; kiểm thử trên class thật.

Với Spring data binding, getter và setter của JavaBean giúp mapper/binder đọc ghi property. Jakarta Bean Validation vẫn có thể đọc field private được annotate; đây là cơ chế khác với việc Spring cần setter/binding strategy để điền dữ liệu.

## 3. Cơ chế cascaded validation từng bước

Giả sử:

```java
class OrderForm {
    @NotBlank
    String orderCode;
    @Valid
    Customer customer;
}

class Customer {
    @NotBlank
    String name;
    @Valid
    Address address;
}

class Address {
    @NotBlank
    String city;
}
```

Khi gọi:

```java
Set<ConstraintViolation<OrderForm>> errors =
        validator.validate(order);
```

Đây là **mã minh họa**; cần `Validator`, `ConstraintViolation` thuộc Jakarta Validation, các class đã định nghĩa, và instance `validator`, `order` thực tế.

Trình tự logic:

1. Validator bắt đầu tại `OrderForm`, đánh giá các constraint áp dụng lên chính đối tượng gốc, ví dụ `@NotBlank` trên `orderCode`.
2. Thấy `OrderForm.customer` đánh dấu `@Valid`; nếu giá trị không null, validator di chuyển tới đối tượng `Customer`.
3. Đánh giá constraint trên `Customer`, ví dụ `@NotBlank` ở `name`.
4. Thấy `Customer.address` đánh dấu `@Valid`; nếu giá trị không null, tiếp tục tới `Address`.
5. Đánh giá `@NotBlank` trên `Address.city` và các constraint khác.
6. Tạo các `ConstraintViolation<OrderForm>` với path tính **từ root được validate**, ví dụ `customer.name` và `customer.address.city`.

Đây là **mô hình giải thích đường đi**; chuẩn không bảo đảm constraint sẽ được thực thi theo thứ tự 1 → 6 như khi đọc code. `Set<ConstraintViolation<T>>` **không bảo đảm thứ tự phần tử**. Khi cần log, output hoặc test ổn định, sắp xếp theo property path và thông tin constraint trước khi hiển thị.

### 3.1. Thiếu `@Valid` ở một cạnh thì sao?

Nếu chỉ `OrderForm.customer` có `@Valid`, còn `Customer.address` không có:

```text
OrderForm --@Valid--> Customer --(không có @Valid)--> Address
                     |
                     +-- name được validate
                         address.city không được duyệt đến
```

Dù `Address.city` có `@NotBlank`, gọi `validator.validate(order)` **không tự động truy cập tất cả property của mọi object trong graph**. Nó chỉ kiểm tra các cạnh cascade đã khai báo (và các constraint áp dụng trên giá trị hiện tại).

Ngược lại, nếu gọi trực tiếp `validator.validate(address)`, constraint của `Address` vẫn được kiểm tra vì `address` lúc này là root, không cần một parent có `@Valid`.

### 3.2. Một đối tượng con lồng nhau có thể vừa bị constraint, vừa được cascade

```java
@NotNull(message = "Address is required")
@Valid
private Address address;
```

`@NotNull` áp lên tham chiếu `Address`; `@Valid` đi sâu kiểm tra `city`, `zip` khi non-null. Bài học này khác với `@NotEmpty` dùng cho chuỗi/collection và cũng khác `@Size`, vốn không kiểm tra nội dung từng object con.

## 4. `propertyPath` và lỗi nested object

Lỗi trong object con vẫn được trả về dưới dạng một `ConstraintViolation` thuộc lần validate root. Ví dụ `Address.zip = "12x"` bị `@Pattern(regexp = "\\d{5}")` khi có `@Valid` ở cả hai cạnh:

```text
root                         = OrderForm
propertyPath.toString()      = customer.address.zip
invalidValue                 = "12x"
message                      = "ZIP must contain 5 digits"
```

`getPropertyPath()` trả về `jakarta.validation.Path`, **không phải chỉ một chuỗi**. `Path.Node` có `getName()`, `getKind()`, `isInIterable()`, `getIndex()` và `getKey()` khi cần xử lý path có cấu trúc.

Với nested object đơn giản, `Path.toString()` thường thành chuỗi bằng dấu chấm. Với collection hoặc Map, có thể xuất hiện index/key, container element node hoặc các đoạn path tùy provider; **đừng giả định** mọi đường dẫn là danh sách field ngăn bởi dấu chấm.

Các API hữu ích:

```java
violation.getRootBean();        // instance OrderForm gốc
violation.getLeafBean();        // instance gần nơi constraint được đánh giá
violation.getPropertyPath();    // đường dẫn từ root đến vị trí vi phạm
violation.getInvalidValue();    // giá trị được đánh giá bởi constraint
violation.getMessage();         // thông báo sau interpolation
violation.getMessageTemplate(); // mẫu trước interpolation
```

Đây là các biểu thức minh họa trên một instance `ConstraintViolation<?>` đã có. `getInvalidValue()` không nhất thiết là String hay property cuối cùng trong mọi loại constraint: constraint cấp class có thể có invalid value là cả bean con, kể cả khi custom validator thêm một property node vào path.

Nếu dùng đường dẫn lỗi cho giao diện, cần ánh xạ nó tới tên field public của form/API. `customer.address.zip` là path Bean Validation, không nhất thiết là JSON Pointer `/customer/address/zip` hay tên input trong UI.

## 5. Ví dụ Java 17+ đầy đủ: hai cấp `@Valid`, giá trị null và tích hợp Spring

Ví dụ dùng **Jakarta Validation 3.0, Hibernate Validator 8.0.2.Final** làm provider, **Spring Framework 6.2.14** làm adapter để minh họa `BindingResult`. Chương trình chạy độc lập bằng Maven, không cần khởi động Spring Boot hay HTTP server.

Tình huống:
- `OrderForm.orderCode` có `@Size(min = 3)`.
- `OrderForm.customer` có `@NotNull @Valid`.
- `Customer.name` có `@NotBlank`.
- `Customer.address` có `@NotNull @Valid`.
- `Address.city` có `@NotBlank`; `Address.zip` có `@Pattern` yêu cầu đúng 5 chữ số.
- Có thêm `OrderWithoutCascade` không đặt `@Valid`, để chứng minh chỉ chứa tham chiếu không khiến validation đi sâu.

### 5.1. Tạo `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>nested-valid-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.2.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish</groupId>
            <artifactId>jakarta.el</artifactId>
            <version>4.0.2</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.14</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`hibernate-validator` cung cấp provider Jakarta Bean Validation; `jakarta.el` hỗ trợ hệ thống nội suy thông báo theo cấu hình; `spring-context` chứa adapter Spring cần cho phần tích hợp. Trong ứng dụng Spring Boot, thường để BOM của Boot quản lý các phiên bản tương thích và thêm `spring-boot-starter-validation` thay vì tự đóng đinh tất cả các dependency như ví dụ.

### 5.2. Tạo `src/main/java/demo/NestedValidationDemo.java`

```java
package demo;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.beanvalidation.SpringValidatorAdapter;

public final class NestedValidationDemo {

    public static final class Address {
        @NotBlank(message = "City is required")
        private String city;

        @Pattern(regexp = "\\d{5}", message = "ZIP must contain 5 digits")
        private String zip;

        public Address(String city, String zip) {
            this.city = city;
            this.zip = zip;
        }

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }

        public String getZip() {
            return zip;
        }

        public void setZip(String zip) {
            this.zip = zip;
        }
    }

    public static final class Customer {
        @NotBlank(message = "Name is required")
        private String name;

        @NotNull(message = "Address is required")
        @Valid
        private Address address;

        public Customer(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

    public static final class OrderForm {
        @Size(min = 3, message = "Order code needs 3 characters")
        private String orderCode;

        @NotNull(message = "Customer is required")
        @Valid
        private Customer customer;

        public OrderForm(String orderCode, Customer customer) {
            this.orderCode = orderCode;
            this.customer = customer;
        }

        public String getOrderCode() {
            return orderCode;
        }

        public void setOrderCode(String orderCode) {
            this.orderCode = orderCode;
        }

        public Customer getCustomer() {
            return customer;
        }

        public void setCustomer(Customer customer) {
            this.customer = customer;
        }
    }

    public static final class OrderWithoutCascade {
        // Cố ý không có @Valid.
        private Customer customer;

        public OrderWithoutCascade(Customer customer) {
            this.customer = customer;
        }

        public Customer getCustomer() {
            return customer;
        }

        public void setCustomer(Customer customer) {
            this.customer = customer;
        }
    }

    private static void require(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Customer invalidCustomer =
                new Customer(" ", new Address("", "12x"));
        OrderForm invalidOrder =
                new OrderForm("A", invalidCustomer);

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Set<ConstraintViolation<OrderForm>> errorSet =
                    validator.validate(invalidOrder);
            List<ConstraintViolation<OrderForm>> errors =
                    new ArrayList<>(errorSet);
            errors.sort(Comparator.comparing(
                    v -> v.getPropertyPath().toString()));

            require(errors.size() == 4, "Expected four violations");
            for (ConstraintViolation<OrderForm> error : errors) {
                System.out.println(error.getPropertyPath()
                        + " => " + error.getMessage());
            }

            // Spring chuyển các violation về FieldError.
            BeanPropertyBindingResult bindingResult =
                    new BeanPropertyBindingResult(invalidOrder, "order");
            new SpringValidatorAdapter(validator)
                    .validate(invalidOrder, bindingResult);

            require(bindingResult.getFieldErrorCount() == 4,
                    "Expected four field errors");

            FieldError zipError =
                    bindingResult.getFieldError("customer.address.zip");
            require(zipError != null, "Nested ZIP field error missing");
            System.out.println(
                    "springFieldErrors=" + bindingResult.getFieldErrorCount());
            System.out.println("springZipField=" + zipError.getField());

            // @Valid không tự từ chối null; @NotNull làm việc đó.
            OrderForm nullCustomer = new OrderForm("ORD-123", null);
            Set<ConstraintViolation<OrderForm>> nullErrors =
                    validator.validate(nullCustomer);
            require(nullErrors.size() == 1, "Expected one required error");
            require("customer".equals(nullErrors.iterator().next()
                    .getPropertyPath().toString()),
                    "Expected customer required error");
            System.out.println("nullCustomerErrors=" + nullErrors.size());

            // Không có @Valid trên parent -> không đi tới constraint của child.
            Set<ConstraintViolation<OrderWithoutCascade>> uncascaded =
                    validator.validate(new OrderWithoutCascade(invalidCustomer));
            require(uncascaded.isEmpty(), "Unexpected cascade");
            System.out.println("withoutCascadeErrors=" + uncascaded.size());

            // Có đủ @Valid, mọi field con hợp lệ -> không có vi phạm.
            OrderForm validOrder = new OrderForm(
                    "ORD-123",
                    new Customer("Lan", new Address("Hanoi", "12345")));
            require(validator.validate(validOrder).isEmpty(),
                    "Expected fully valid order");
            System.out.println("validOrderErrors=0");
            System.out.println("CHECKS: PASS");
        }
    }
}
```

### 5.3. Chạy chương trình

Trong thư mục chứa `pom.xml` (Java 17+ và Maven):

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=demo.NestedValidationDemo
```

Phần stdout do chương trình tạo ra, sau khi bỏ các log khởi động thư viện nếu có:

```text
customer.address.city => City is required
customer.address.zip => ZIP must contain 5 digits
customer.name => Name is required
orderCode => Order code needs 3 characters
springFieldErrors=4
springZipField=customer.address.zip
nullCustomerErrors=1
withoutCascadeErrors=0
validOrderErrors=0
CHECKS: PASS
```

**Giải thích đầu ra:**
- `orderCode` vi phạm constraint trên root.
- Hai vi phạm `customer.address.city`, `customer.address.zip` chỉ xuất hiện vì **hai chặng** `OrderForm.customer` và `Customer.address` đều có `@Valid`.
- `customer.name` là constraint của con `Customer`; `@Valid` ở `OrderForm.customer` đủ để duyệt tới đây.
- `SpringValidatorAdapter` ghi nhận cùng bốn vi phạm qua `BindingResult`. Path của lỗi ZIP có thể lấy bằng `FieldError.getField()`.
- Với `nullCustomer`, `@Valid` bỏ qua tham chiếu null, nhưng `@NotNull` báo thiếu customer.
- Với `OrderWithoutCascade`, chỉ có trường `Customer` chứa object sai mà không có `@Valid`, nên validator không lan truyền tới child và kết quả rỗng.
- Với `validOrder`, mọi constraint gốc và con đều hợp lệ; kết quả rỗng.

Trong chương trình, `errors` được **sắp xếp theo đường dẫn** trước khi in để stdout ổn định. Bản thân Jakarta Validation trả về một `Set` không bảo đảm thứ tự.

Mã dùng thông báo tiếng Anh tường minh để tránh thay đổi output bởi bundle hoặc locale. Ứng dụng thực tế có thể quốc tế hóa message bằng resource bundle và `MessageInterpolator`.

## 6. Spring MVC: validate DTO lồng nhau khi nhận request

Một DTO dùng trong Spring MVC có thể như sau (đây là **trích đoạn**, cần constructor/getter/setter thích hợp):

```java
public class CheckoutForm {
    @NotNull(message = "Customer is required")
    @Valid
    private CustomerForm customer;
}

public class CustomerForm {
    @NotBlank
    private String name;

    @NotNull
    @Valid
    private AddressForm address;
}

public class AddressForm {
    @NotBlank
    private String street;
}
```

Các import là `jakarta.validation.Valid`, `jakarta.validation.constraints.NotNull` và `jakarta.validation.constraints.NotBlank`. Trong Spring Framework 6+ các API Jakarta dùng namespace `jakarta.*`; các dự án Spring Framework 5.x cũ thường thuộc hệ sinh thái `javax.validation.*`.

Ví dụ controller cho HTML form (mã **minh họa**, cần Spring Web MVC):

```java
@PostMapping("/checkout")
public String submit(
        @Valid @ModelAttribute("checkout") CheckoutForm checkout,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "checkout/form";
    }
    return "checkout/success";
}
```

Các import controller:
- `jakarta.validation.Valid`
- `org.springframework.web.bind.annotation.PostMapping`
- `org.springframework.web.bind.annotation.ModelAttribute`
- `org.springframework.validation.BindingResult`

Với Bean Validation provider đã được Spring MVC tích hợp, `@Valid` **trước tham số root** kích hoạt validation trên `CheckoutForm`. Sau đó `@Valid` **trên field `customer` và `address`** điều khiển lan truyền xuống con. Đây là **hai vai trò khác nhau ở hai vị trí annotation**:

```text
@Valid @ModelAttribute CheckoutForm    -> kiểm tra root khi nhận request
    @Valid CustomerForm customer        -> cascade root -> customer
        @Valid AddressForm address      -> cascade customer -> address
```

`BindingResult` nên đặt **ngay sau tham số** mà nó nhận lỗi. Khi có lỗi nested như `customer.address.street`, có thể lấy bằng `errors.getFieldError("customer.address.street")` hoặc danh sách `errors.getFieldErrors()`.

### 6.1. Nếu không có `BindingResult` theo sau?

Spring MVC có thể ném exception do validation, thường là `MethodArgumentNotValidException` khi xác thực từng đối số command object; trong trường hợp kích hoạt **method validation** trên các parameter trực tiếp hoặc return value, có thể là `HandlerMethodValidationException`. Loại exception phụ thuộc method signature và đường validation thực tế. Với form cần hiển thị lại lỗi, nhận `BindingResult` hợp lệ ngay sau model là một cách xử lý chủ động.

Đối với `@RequestBody`, Jackson (hoặc HTTP message converter được cấu hình) deserialize JSON thành Java object trước khi validation; nested `@Valid` vẫn mang ý nghĩa cascade, nhưng lỗi **không parse được JSON** là lỗi đọc message khác với violation trên object đã deserialize.

### 6.2. Spring không tự validate mọi object ngay sau khi `bind`

Khi sử dụng `DataBinder` thủ công, `binder.bind(propertyValues)` chủ yếu thực hiện binding. Muốn chạy Bean Validation, phải cấu hình validator rồi gọi:

```java
binder.setValidator(localValidatorOrSpringAdapter);
binder.bind(propertyValues);
binder.validate();
BindingResult errors = binder.getBindingResult();
```

Đây là **trích đoạn**, `localValidatorOrSpringAdapter` phải là instance `org.springframework.validation.Validator` hợp lệ. Trong Spring MVC, hạ tầng xử lý `@Valid`/`@Validated` thường gọi validation theo workflow của controller; không áp đặt cùng mặc định cho mọi DataBinder do ứng dụng tự tạo.

Tách hai loại lỗi:
- **Binding/conversion:** không chuyển được `"abc"` thành `Integer`, lỗi kiểu `typeMismatch`.
- **Bean Validation:** bind thành object thành công nhưng không thỏa `@NotBlank`, `@Size`, `@Pattern` ở root/con.

Cả hai có thể xuất hiện trong `BindingResult`; không phải mọi `FieldError` đều bắt nguồn từ Jakarta `ConstraintViolation`.

## 7. Các trường hợp `null`, object thiếu và DTO chưa được bind đầy đủ

Có ba tình huống hay bị nhầm:

1. **Con là `null`, chỉ có `@Valid`:** validator **bỏ qua** traversal, nên không tạo lỗi từ constraint của con.
2. **Con là `null`, có `@NotNull @Valid`:** `@NotNull` trên **tham chiếu cha** tạo violation `customer`; validator không tạo thêm lỗi cho `customer.name` vì không có instance Customer.
3. **Con tồn tại nhưng field bên trong null/trống:** nếu đã cascade tới con, constraint như `@NotBlank`, `@NotNull` trên field con sẽ chạy và sinh lỗi path lồng nhau.

Ví dụ:

```text
customer = null
  -> @Valid: không lỗi
  -> @NotNull @Valid: "customer" sai

customer = Customer(name = null, address = null)
  -> @NotBlank Customer.name: sai tại "customer.name"
  -> @NotNull Customer.address: sai tại "customer.address"
  -> @Valid Customer.address: không đi sâu vì null
```

**Đừng tạo object con rỗng chỉ để ép nested constraints chạy** nếu nghiệp vụ thực sự cho phép không có con. Hãy biểu diễn rõ **required vs optional**, rồi chọn `@NotNull` và `@Valid` tương ứng.

Lưu ý riêng: gọi `validator.validate(null)` với **root argument null** không tương đương cascade qua một field null; API validator yêu cầu đối tượng root hợp lệ và có thể ném `IllegalArgumentException`. Quy tắc “bỏ qua null” ở đây áp dụng cho **tham chiếu con khi cascade**.

### 7.1. Optional và `@Valid`

`Optional<Customer>` có thể chứa giá trị trống hoặc object con, và Jakarta Bean Validation 2.0+/3.0 có cơ chế **value extraction** cho một số container tiêu chuẩn. Khi dùng các kiểu wrapper/container, có thể khai báo annotation trên type argument như `Optional<@Valid Customer>` tùy khả năng của provider. Tuy nhiên, một `Optional` rỗng và một field bắt buộc phải có Customer là hai yêu cầu khác nhau; cần constraint thích hợp lên giá trị/khả năng hiện diện.

Với DTO thông thường của form/Jackson, cân nhắc dùng tham chiếu trực tiếp `Customer` có `@NotNull @Valid` nếu điều đó làm hợp đồng rõ hơn. Không tự động thay mọi field nullable bằng `Optional` trong class DTO.

## 8. Cascade qua `List`, `Map`, array và nhiều cấp

Dù bài học trọng tâm là thuộc tính **tham chiếu đến một đối tượng con**, cùng nguyên tắc dùng được với các quan hệ có nhiều con. Jakarta Validation hỗ trợ cascaded validation trên container tiêu chuẩn bằng annotation ở container hoặc tại **type argument**.

Ví dụ cho danh sách item:

```java
public class OrderForm {
    private List<@Valid LineItem> items;
}

public class LineItem {
    @Min(1)
    private int quantity;
}
```

Đây là **mã cấu trúc minh họa**; cần import `java.util.List`, `jakarta.validation.Valid`, `jakarta.validation.constraints.Min`. Nếu `items` chứa một `LineItem(quantity=0)`, đường dẫn có thể như `items[0].quantity`, với index lấy qua cấu trúc `Path.Node` của Jakarta Validation. Tên node container hiển thị chính xác phụ thuộc provider và kiểu collection.

Một cách khai báo thường gặp khác cho cascaded collection là:

```java
@Valid
private List<LineItem> items;
```

Đối với provider hỗ trợ type-use (Jakarta Bean Validation 2.0+), khai báo `List<@Valid LineItem>` giúp chỉ rõ rằng **phần tử** được cascade. Hãy chọn một quy ước thay vì gắn `@Valid` lặp trên cả container và type argument mà không có mục đích rõ.

- `@Valid` **không buộc** collection phải tồn tại hoặc có phần tử. Muốn bắt buộc không rỗng, dùng `@NotEmpty` ở collection theo hợp đồng.
- `@Valid` **không buộc** từng phần tử khác null: muốn vậy có thể dùng `List<@NotNull @Valid LineItem>`; lưu ý node lỗi và provider.
- `List<@NotBlank String>` kiểm tra **từng phần tử String** qua constraint type-use; nó không phải cascaded validation vào bean con vì String không phải bean có field con.
- Với `Map<K,V>`, validation có thể áp trên key/value bằng annotation phù hợp; đường dẫn có thể chứa Map key. Không suy diễn path Map luôn giống path List.

### 8.1. Đa cấp phải khai báo cascade ở mỗi cạnh

Ví dụ:

```text
CheckoutRequest
  -> @Valid order
       -> @Valid customer
            -> @Valid address
                 -> @NotBlank street
```

Thiếu `@Valid` ở bất kỳ cạnh nào trên đường đi sẽ khiến validation khởi đầu từ `CheckoutRequest` **không đi tới** các constraint nằm phía sau cạnh đó. Ngược lại, khi validate trực tiếp một object ở giữa, quá trình bắt đầu ở object đó và áp dụng các annotation được khai báo từ vị trí root mới.

### 8.2. Vòng tham chiếu không gây lặp vô hạn

Object graph Java có thể chứa vòng:

```text
Parent -> Child -> Parent -> Child -> ...
```

Jakarta Validation quy định provider phải tránh vòng lặp vô hạn trong cascaded validation. Theo từng **navigation path**, một instance đã gặp không bị duyệt lặp vô hạn trong cùng đường. Cơ chế này không đồng nghĩa “mỗi instance chỉ được validate đúng một lần trên toàn graph”: cùng một object có thể đi qua nhiều đường tham chiếu khác nhau và sinh các path lỗi phù hợp.

Do đó không viết custom `ConstraintValidator` tự duyệt cả graph vô hạn khi `@Valid` có thể giải quyết bài toán. Với mô hình graph lớn, cũng cần cân nhắc hiệu năng và vòng đời request; chỉ đánh dấu cascade ở những quan hệ cần kiểm tra thực sự.

## 9. Validation groups và `@ConvertGroup` khi cascade

Mặc định, khi gọi:

```java
validator.validate(order);
```

Bean Validation kiểm tra nhóm `Default`. Khi cascade, nhóm validation đang dùng **được truyền xuống** object con, trừ khi bạn cấu hình group conversion.

Điểm dễ nhầm: `@Valid` **không nhận `groups`**:

```java
@Valid  // Hợp lệ, chỉ đánh dấu cascade.
private Address address;
```

Nếu muốn kiểm tra constraint con bằng một group khác với group của cha, dùng `@ConvertGroup` tại cạnh có `@Valid`. Ví dụ **cấu trúc minh họa**, chưa phải class độc lập:

```java
public interface Detailed {}

public class Address {
    @NotBlank(groups = Detailed.class)
    private String street;
}

public class Customer {
    @Valid
    @ConvertGroup(from = Default.class, to = Detailed.class)
    private Address address;
}
```

Các import:
- `jakarta.validation.Valid`
- `jakarta.validation.groups.ConvertGroup`
- `jakarta.validation.groups.Default`
- `jakarta.validation.constraints.NotBlank`

Khi validate `Customer` với group `Default`, cạnh `address` chuyển group được dùng cho `Address` sang `Detailed`. Không có `@ConvertGroup`, constraint chỉ gắn `Detailed` sẽ không chạy khi yêu cầu nhóm `Default` (trừ khi một quy tắc group inheritance/sequence khác được cấu hình).

**Quy tắc chính:** `@ConvertGroup` cần gắn với một phần tử được đánh dấu `@Valid`, và phép chuyển đổi áp dụng **trên từng cạnh cascade**, không phải một biến đổi toàn cục cho mọi bean. Nếu cấu hình nhiều luật chuyển đổi có cùng `from`, provider có thể ném `ConstraintDeclarationException`.

Trong Spring, `@Validated` giúp chỉ định group trên điểm bắt đầu validation của controller/service; `@Valid` trên property con vẫn điều khiển **việc đi sâu**. `@Validated` của Spring không tự thay thế `@Valid` trên mỗi cạnh.

## 10. Những trường hợp nâng cao cần hiểu đúng

### 10.1. `@Valid` trên đối tượng root khác với `@Valid` ở thuộc tính tham chiếu

Hai vị trí thường xuất hiện đồng thời:

```java
public Response submit(@Valid @RequestBody OrderForm order) { ... }
```

và:

```java
public class OrderForm {
    @Valid
    private Customer customer;
}
```

Annotation trên **parameter root** thông báo cho hạ tầng Spring cần validate đối tượng nhận được. Annotation trên **property con** điều khiển traversal từ root sang Customer. Nếu bỏ annotation ở parameter mà không có cơ chế validation khác, Spring MVC có thể không yêu cầu validation của root. Nếu bỏ annotation trên property, Spring chỉ kiểm tra constraint root chứ không đi xuống `Customer`.

Trong Jakarta API trực tiếp `validator.validate(order)`, bản thân lời gọi đã khởi động validation root; không cần gắn `@Valid` lên biến cục bộ `order`.

### 10.2. Lỗi cấp class bên trong object con

Một custom constraint cấp class như `@ValidPeriod` trên `Address`/`Reservation` có thể báo vi phạm ở **node bean** khi parent cascade tới child. Khi đó path có thể dừng ở tên object con (`customer.address`) thay vì một field cụ thể, trừ khi custom validator chủ động gọi `ConstraintValidatorContext.addPropertyNode(...)` để gắn lỗi vào field.

`ConstraintViolation.getInvalidValue()` của một lỗi cấp class thường là **toàn bộ child bean**, không phải một String trong nó. Do vậy không tự serialize hay log toàn bộ invalidValue; object có thể mang dữ liệu nhạy cảm.

### 10.3. Persistence/JPA và Spring MVC là các điểm kích hoạt khác nhau

`@Valid` trên một association trong DTO HTTP quyết định cascading khi validate DTO. `@Valid` trong entity cũng có thể được đánh giá khi ứng dụng hoặc JPA provider thực hiện Bean Validation ở một lifecycle hook đã cấu hình. **Đừng nhầm** JPA `CascadeType.PERSIST`/`MERGE` với Jakarta Validation `@Valid`: một cơ chế quản lý vòng đời entity, một cơ chế duyệt constraint.

Không nên phụ thuộc duy nhất vào frontend validation hoặc cho rằng gọi repository `.save(...)` luôn thực hiện đúng toàn bộ graph validation bạn mong muốn; cần kiểm thử đường lưu dữ liệu và thiết lập validation thực tế của ứng dụng.

### 10.4. Khi nào không nên cascade?

Nếu child là object dùng chung có nhiều constraint không liên quan đến request hiện tại, đánh dấu `@Valid` toàn bộ có thể làm form bị từ chối bởi những field không nhập trong ngữ cảnh này. Giải pháp có thể là:
- Thiết kế DTO riêng cho endpoint và ràng buộc đúng yêu cầu dữ liệu đầu vào.
- Dùng validation groups/group conversion có chủ đích.
- Chỉ đánh dấu những quan hệ cần cascade, tránh object graph khổng lồ.
- Tách validation cú pháp dữ liệu khỏi invariant nghiệp vụ cần nhiều service/database.

Những lựa chọn này cần dựa trên hợp đồng request thực tế, không dùng `@Valid` cho mọi field tham chiếu một cách máy móc.

## 11. Ma trận kiểm thử cho `@Valid` lồng nhau

| Trường hợp | Dữ liệu hoặc cấu hình | Kỳ vọng |
| --- | --- | --- |
| Không cascade | Parent có child sai nhưng **không** gắn `@Valid` ở property | Chỉ constraint của parent được kiểm tra |
| Cascade một cấp | Parent gắn `@Valid`, child.name `@NotBlank` và rỗng | Vi phạm ở `child.name` |
| Cascade hai cấp | Parent → child → address đều có `@Valid` | Vi phạm có path như `child.address.city` |
| Thiếu `@Valid` cấp hai | Chỉ parent → child có cascade | Constraint ở address không được duyệt từ parent |
| Con null, chỉ `@Valid` | `child = null` | Không sinh lỗi do cascade |
| Con null, `@NotNull @Valid` | `child = null` | Một lỗi tại `child` của `@NotNull` |
| Con tồn tại, nội dung sai | `child.name = " "` | Vi phạm `@NotBlank` ở child |
| Child hợp lệ | Root và tất cả child hợp lệ | Tập `ConstraintViolation` rỗng |
| Collection có child sai | `List<@Valid LineItem>` với quantity 0 | Path xác định item/index và property lỗi |
| Phần tử collection null | `List<@Valid Item>` chứa `null` | Null được bỏ qua nếu không có `@NotNull` trên phần tử |
| Group mặc định | Validate root ở `Default` | Child nhận `Default` nếu không có conversion |
| Group conversion | `@Valid @ConvertGroup(Default → Detailed)` | Child dùng group `Detailed` tại cạnh đó |
| Object có vòng | A → B → A, các cạnh được cascade | Provider ngăn lặp vô hạn theo navigation path |
| Binding sai kiểu | String không parse được thành kiểu số của child | Spring có thể sinh `typeMismatch`, không phải nested Bean Validation violation |
| MVC request | `@Valid @ModelAttribute`, `BindingResult` ngay sau | Các lỗi nested được ghi nhận ở field path tương ứng |
| JSON request | `@Valid @RequestBody` với object JSON lồng nhau | Deserialize trước, rồi validate object graph nếu hợp lệ |
| Validation provider vắng mặt | Có annotation nhưng không có Jakarta implementation thích hợp | Không thể giả định ứng dụng chạy validation tự động |
| Namespace sai | Trộn `javax.validation` và `jakarta.validation` | Provider/hạ tầng có thể không nhận đúng annotation |
| Dữ liệu nhạy cảm | Child có password/token | Không xuất nguyên `getInvalidValue()` hoặc `FieldError.getRejectedValue()` ra log/API |

### 11.1. Test hành vi bằng property path thay vì thứ tự

Đoạn code sau nằm trong test có sẵn `validator` và `order`, **không phải chương trình độc lập**:

```java
Set<ConstraintViolation<OrderForm>> violations =
        validator.validate(order);

boolean hasCityError = violations.stream().anyMatch(v ->
        "customer.address.city".equals(
                v.getPropertyPath().toString()));
```

Đây là cách kiểm tra rõ vị trí lỗi mà không dựa trên thứ tự trả về của `Set`. Nếu path liên quan container element, cần cân nhắc dùng `Path.Node` để xác nhận index/key/kind thay vì assert text phụ thuộc provider.

### 11.2. Test thay đổi từng cạnh

Một kiểm thử rất có giá trị là tạo **cùng một child sai** và hai parent:
- Parent A có `@Valid` → có vi phạm ở child.
- Parent B không có `@Valid` → không có vi phạm ở child từ lần validate parent.

Kiểm thử này chỉ ra **ý nghĩa của marker `@Valid`** rõ hơn việc chỉ chạy một trường hợp lỗi mặc định. Ví dụ chương trình ở mục 5 có `OrderWithoutCascade` để làm điều đó.

## 12. Lỗi thường gặp và cách xử lý

**1. “Con có `@NotBlank` rồi, sao Spring không báo?”** Vì parent thiếu `@Valid` trên thuộc tính tham chiếu hoặc không có validation entry point ở root. Kiểm tra cả `@Valid` trên controller argument và `@Valid` trên từng cạnh object graph.

**2. “Đặt `@Valid` trên `Customer.address` nhưng `OrderForm.customer` không có.”** Validation bắt đầu từ `OrderForm` sẽ không bao giờ tới `Customer` để thấy annotation ở cấp tiếp theo. Chỉ một annotation ở object sâu không thể bù cho cạnh ở phía trên.

**3. “`@Valid` không bắt được `customer = null`.”** Đây là hành vi chuẩn: null reference bị bỏ qua. Dùng `@NotNull @Valid` nếu con bắt buộc tồn tại.

**4. “Con null rồi mà muốn báo hết lỗi của các field bên trong.”** Không có object để validate, nên các constraint bên trong không chạy. Định nghĩa lỗi thiếu object tại property cha; đừng tạo vô số lỗi tưởng tượng cho field chưa tồn tại.

**5. “Sao lỗi lại là `customer.address.zip` thay vì `zip`?”** Validator trả path tính từ root của lời gọi. Để hiển thị trong form, ánh xạ nested path đúng; nếu validate riêng `Address`, path chỉ là `zip`.

**6. “Gọi `DataBinder.bind()` nhưng không có lỗi `@NotBlank`.”** Binding không mặc nhiên chạy validation trong mọi cách dùng. Đăng ký Spring validator phù hợp rồi gọi `validate()` hoặc dùng hạ tầng Spring MVC `@Valid`/`@Validated`.

**7. “Bị lỗi ngay lúc bind JSON, không có `ConstraintViolation`.”** Parser/deserializer có thể thất bại trước khi hình thành object Java. Tách lỗi JSON syntax/type mismatch khỏi Bean Validation.

**8. “Cùng một object con được validate hai lần hoặc gặp vòng.”** Jakarta provider phải ngăn vòng lặp vô hạn, nhưng nhiều đường dẫn hợp lệ tới cùng instance có thể tạo vi phạm theo mỗi đường. Đừng giả định global visited-set một lần duy nhất trên toàn graph.

**9. “Thêm `@Validated` cho một field con là đủ.”** `@Validated` là annotation của Spring thường dùng chỉ định validation groups tại điểm gọi phù hợp; trường tham chiếu con cần cơ chế cascade của Jakarta `@Valid`.

**10. “Gắn mọi DTO tham chiếu bằng `@Valid` rồi phát sinh lỗi không liên quan.”** Giới hạn graph hoặc dùng DTO/group đúng nghiệp vụ; chọn đường cascade cần thiết thay vì validate cả mô hình domain bất kể request.

**11. “Chỉ kiểm thử field trực tiếp.”** Bài này nhấn mạnh path nested, null parent, thiếu annotation trên một cạnh, collection và Spring `BindingResult`; thiếu những case đó khó phát hiện lỗi cấu hình.

**12. “Trộn `javax.validation.Valid` với `jakarta.validation.constraints.*`.”** Spring Framework 6+ sử dụng Jakarta namespace; với ứng dụng Spring Framework 5 hãy chọn API/provider tương ứng. Đọc dependency tree và import thay vì đổi một phần package.

## 13. Checklist trước khi dùng trong dự án

- [ ] Xác định **root validation entry point**: Jakarta `Validator.validate`, Spring MVC `@Valid`, `@Validated`, hoặc gọi `DataBinder.validate()`.
- [ ] Đặt `@Valid` trên **mỗi thuộc tính tham chiếu** cần đi từ parent đến child, kể cả nhiều cấp.
- [ ] Đặt `@NotNull` trên tham chiếu **nếu và chỉ nếu** child bắt buộc tồn tại.
- [ ] Kiểm tra constraints trên child và kiểu dữ liệu đúng với provider/Jakarta phiên bản đang dùng.
- [ ] Kiểm tra root, child rỗng, child null, thiếu `@Valid`, nested path và một trường hợp hoàn toàn hợp lệ.
- [ ] Với `List`/`Map` có bean con, đặt `@Valid` đúng nơi cần cascade và test index/key.
- [ ] Nếu dùng groups, xác định group đi qua từng cạnh; chỉ dùng `@ConvertGroup` khi có yêu cầu rõ.
- [ ] Khi tích hợp Spring MVC, xác nhận `BindingResult`/exception phù hợp và phân biệt binding error với constraint violation.
- [ ] Giữ dữ liệu nhạy cảm ngoài error response/log; không xuất nguyên cả object trong `invalidValue`.
- [ ] Không dựa vào thứ tự `ConstraintViolation` hay thứ tự validation; khi cần output ổn định, sắp xếp.
- [ ] Test runtime với đúng dependency Spring/Jakarta Validation provider và endpoint thực tế.

## Tài liệu chính thức

- Jakarta Bean Validation 3.0 Specification — Cascaded Validation / Object Graph Validation: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation 3.0 API — `@Valid`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Valid.html
- Jakarta Validation 3.0 API — `ConstraintViolation`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintViolation.html
- Spring Framework 6.2 — Bean Validation: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 — MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — MVC Validator Configuration: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html
- Spring Framework 6.2 — `SpringValidatorAdapter`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/beanvalidation/SpringValidatorAdapter.html
- Hibernate Validator 8 Reference Guide — Cascaded validation: https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/
