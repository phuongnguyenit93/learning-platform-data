# `validate`, `validateProperty` và `validateValue` trong Bean Validation

## 1. Bài toán: kiểm tra cả đối tượng, một thuộc tính hay giá trị sắp nhập?

Giả sử một form đăng ký trong ứng dụng Spring có ba thông tin: tên tài khoản, mật khẩu, tuổi, cùng địa chỉ liên hệ. Khi người dùng nhấn **Gửi**, backend cần kiểm tra toàn bộ đối tượng; khi người dùng rời khỏi ô **mật khẩu**, giao diện chỉ muốn kiểm tra thuộc tính này; khi người dùng mới gõ một giá trị nhưng chưa gán vào bean, backend muốn kiểm tra **giá trị giả định**.

Jakarta Bean Validation phân biệt chính xác ba tình huống thông qua giao diện **`jakarta.validation.Validator`**:

- **`validate(object, groups...)`**: kiểm tra **đối tượng hiện có**, các constraint áp dụng ở mức lớp, các thuộc tính, và các đối tượng lồng nhau được đánh dấu cascade bằng `@Valid`.
- **`validateProperty(object, propertyName, groups...)`**: kiểm tra **thuộc tính của một đối tượng hiện có** bằng những constraint gắn với thuộc tính đó, lấy giá trị thực đang nằm trong bean.
- **`validateValue(beanType, propertyName, candidate, groups...)`**: kiểm tra **một giá trị dự kiến** theo constraint được khai báo trên thuộc tính của một lớp, không yêu cầu có bean và không gán giá trị này vào bean.

Đây là **Bean Validation** theo chuẩn Jakarta (API 3.x thường đi với Spring Framework 6 / Spring Boot 3), khác với phương thức `validate(Object, Errors)` trong giao diện `org.springframework.validation.Validator` của Spring. Một dự án Spring cũ có thể dùng package `javax.validation.*`; không trộn lẫn `javax` và `jakarta` khi chọn dependency.

Ví dụ gọi ngắn:

```java
Set<ConstraintViolation<RegistrationForm>> all = validator.validate(form);
Set<ConstraintViolation<RegistrationForm>> current =
        validator.validateProperty(form, "password");
Set<ConstraintViolation<RegistrationForm>> candidate =
        validator.validateValue(RegistrationForm.class, "password", "123");
```

Đoạn trên chỉ minh họa API; các lớp `RegistrationForm`, `validator` và import được định nghĩa đầy đủ ở phần chạy thử.

## 2. Cơ chế chung của `jakarta.validation.Validator`

Một bean chứa constraint bằng annotation như `@NotNull`, `@NotBlank`, `@Size`, `@Min`, `@Email`, `@Pattern`, hoặc custom constraint do dự án định nghĩa. Constraint có thể nằm ở field, getter, kiểu dữ liệu, phần tử container hoặc mức lớp, tùy `@Target` của annotation.

`Validator` không tự tạo hay thay đổi dữ liệu. Nó tra cứu **constraint metadata**, chọn nhóm (validation group), thực hiện `ConstraintValidator` của những constraint liên quan, rồi trả về một `Set<ConstraintViolation<T>>`. Tập rỗng nghĩa là các constraint đã được thực thi trong phạm vi yêu cầu đều đạt; **không đồng nghĩa mọi quy tắc nghiệp vụ của ứng dụng đã được kiểm tra**.

Một `ConstraintViolation` có thể cung cấp:

| Thành phần | Ý nghĩa |
| --- | --- |
| `getPropertyPath()` | Đường dẫn đến constraint bị vi phạm, ví dụ `password` hoặc `address.street` |
| `getMessage()` | Thông báo sau khi nội suy, có thể phụ thuộc locale |
| `getMessageTemplate()` | Mẫu thông báo trước khi nội suy |
| `getInvalidValue()` | Giá trị vi phạm; cần cẩn trọng với dữ liệu nhạy cảm |
| `getConstraintDescriptor()` | Metadata của constraint và các thuộc tính như `min`, `max` |
| `getRootBeanClass()` | Lớp bean gốc được dùng làm ngữ cảnh validation |
| `getRootBean()` | Đối tượng bean gốc khi có instance; có thể là `null` với `validateValue` |

**Thứ tự phần tử của `Set` không được bảo đảm.** Không dựa vào thứ tự duyệt violation để định nghĩa thứ tự hiển thị. Nếu cần stdout/test ổn định, chủ động sắp xếp theo đường dẫn hoặc khóa thích hợp.

### 2.1. Null, chuỗi rỗng và kiểm tra nhiều constraint

Nhiều annotation **cho phép `null`**, vì chúng chỉ kiểm tra giá trị khi có dữ liệu: chẳng hạn `@Size(min=8)` không thay thế `@NotNull`; `@Min(18)` trên `Integer` không tự từ chối `null`. Ngược lại, `@NotNull` từ chối `null` nhưng cho phép `""` và `"  "`; `@NotBlank` chỉ áp dụng cho `CharSequence` và từ chối `null`, rỗng hoặc toàn khoảng trắng.

Ví dụ:

```java
@NotBlank
@Size(min = 3, max = 30)
private String username;
```

Tên tài khoản phải có ký tự không phải khoảng trắng và độ dài trong giới hạn. Nếu giá trị là `"a"`, `@NotBlank` đạt nhưng `@Size(min=3)` thất bại. Nếu giá trị `null`, cả tính hợp lệ và số violation còn phụ thuộc vào các constraint được chọn và cách cấu hình kiểm tra; không nên suy ra chỉ một violation luôn được tạo.

### 2.2. Vi phạm constraint khác lỗi binding

`Validator` nhận các giá trị Java đã có kiểu phù hợp. Nó **không tự chuyển** `"twenty"` thành `int`, không đảm nhiệm HTTP request binding và không sửa giá trị người dùng nhập. Trong Spring MVC, `DataBinder`/`ConversionService` chuyển đổi dữ liệu trước, sau đó Bean Validation kiểm tra ràng buộc; `BindingResult` có thể chứa cả lỗi binding lẫn validation.

Khi dùng `validateValue`, cần cung cấp giá trị có kiểu tương thích với constraint. Truyền kiểu không phù hợp có thể dẫn đến ngoại lệ cấu hình/kiểu dữ liệu thay vì một violation đẹp đẽ. Validate giá trị nhập thô thường cần bước parse/conversion riêng.

## 3. `validate(object, groups...)`: kiểm tra toàn bộ bean và đối tượng được cascade

Định nghĩa rút gọn:

```java
<T> Set<ConstraintViolation<T>> validate(
        T object, Class<?>... groups);
```

Framework chọn những constraint áp dụng cho kiểu runtime và nhóm được yêu cầu; mặc định, khi không truyền nhóm nào, nhóm `jakarta.validation.groups.Default` được dùng.

Về phạm vi, `validate(form)` có thể xét:

1. Constraint của các property trên form (field hoặc getter có annotation).
2. Constraint của chính kiểu form ở **class level**, ví dụ kiểm tra `startDate <= endDate`.
3. Constraint trên **đối tượng con** khi liên kết được đánh dấu `@Valid`; đường dẫn lỗi có thể là `address.street`.
4. Constraint trên phần tử container, ví dụ `List<@NotBlank String> tags`, và cascade phần tử như `List<@Valid Address>` khi được hỗ trợ.
5. Nhóm validation và quy tắc group conversion/sequence được khai báo.

Ví dụ phân biệt cascade:

```java
class Customer {
    @NotBlank String name;
    @Valid Address address;
}
class Address {
    @NotBlank String street;
}
```

Nếu `address.street` trống và `address` khác `null`, `validate(customer)` có thể báo violation `address.street`; một annotation `@Valid` trên field chỉ bật duyệt sang đối tượng con, **bản thân nó không phải constraint bắt buộc khác `null`**. Nếu `address == null`, cần `@NotNull` riêng để cấm null; `@Valid` không từ chối null.

**Khi dùng:** validate toàn bộ DTO/command object trước khi xử lý yêu cầu, validate cấu hình được tải từ nguồn ngoài, validate bean trước khi lưu trạng thái quan trọng, hoặc chạy kiểm thử các ràng buộc tổng thể.

**Lưu ý:** không thay thế quyền truy cập, xác thực người dùng, kiểm tra database unique, transaction hay quy tắc miền nghiệp vụ. Đừng dùng `validate` rồi giả định trạng thái không thể thay đổi trước khi sử dụng.

## 4. `validateProperty(object, propertyName, groups...)`: kiểm tra một thuộc tính đang tồn tại

Định nghĩa rút gọn:

```java
<T> Set<ConstraintViolation<T>> validateProperty(
        T object, String propertyName, Class<?>... groups);
```

Với `form.getPassword()` đang là `"123"` và field `password` có `@Size(min=8)`, lệnh `validator.validateProperty(form, "password")` kiểm tra **giá trị hiện thời** của field đó. Không cần validation toàn bộ form.

Phạm vi hẹp có một khác biệt dễ bỏ sót:

- Chỉ các constraint được gắn với **thuộc tính được chọn** được áp dụng.
- **Không thực hiện cascaded validation theo `@Valid`**, kể cả thuộc tính đang chọn là đối tượng con.
- Không đánh giá các constraint cấp lớp/cross-field của bean cha chỉ vì chúng có thể liên quan đến field đang chọn.
- Không tự đi xuyên đường dẫn nested như một traversal hoàn chỉnh của `validate`; không giả định chuỗi `"address.street"` được hỗ trợ như một property name. Nếu cần kiểm tra nested property đơn lẻ, lấy bean con rồi gọi `validateProperty(address, "street")`, hoặc validate toàn root bean.
- `propertyName` cần xác định một property hợp lệ của kiểu được validate. Tên sai/đối tượng `null` có thể dẫn đến `IllegalArgumentException` thay vì `Set` rỗng.

Ví dụ, nếu `RegistrationForm.address` chỉ được đánh dấu `@Valid`, còn constraint `@NotBlank` nằm trên `Address.street`, thì:

```java
validator.validate(form);                       // có thể thấy address.street
validator.validateProperty(form, "address");    // không cascade -> tập rỗng
validator.validateProperty(form, "password");   // kiểm tra password hiện có
```

**Khi dùng:** giao diện muốn kiểm tra nhanh một field đã được bind vào model, bước wizard chỉ có một thuộc tính cần báo lỗi, hoặc nghiệp vụ chỉ muốn hỏi constraint cục bộ cho một property cụ thể.

**Không nên dùng một mình** để kết luận cả form hợp lệ, đặc biệt khi có constraint phụ thuộc nhiều thuộc tính, class-level constraint và các bean lồng nhau. Trước khi xử lý/lưu dữ liệu quan trọng, vẫn cần validation với phạm vi thích hợp.

## 5. `validateValue(beanType, propertyName, candidate, groups...)`: kiểm tra giá trị giả định

Định nghĩa rút gọn:

```java
<T> Set<ConstraintViolation<T>> validateValue(
        Class<T> beanType, String propertyName, Object value,
        Class<?>... groups);
```

`validateValue` dựa vào metadata constraint khai báo trên thuộc tính của **lớp** `beanType`. Nó kiểm tra `candidate` **như thể** giá trị đó sẽ được đặt vào property, nhưng không có instance bean và không cập nhật state.

```java
validator.validateValue(
        RegistrationForm.class, "password", "123");

validator.validateValue(
        RegistrationForm.class, "password", "strong-password");
```

Trường hợp đầu sẽ vi phạm `@Size(min=8)`; trường hợp sau đạt constraint này. Các property khác trên bean không được quan sát hay thay đổi.

Hệ quả:

- **Không cần khởi tạo `RegistrationForm`** và không đụng tới mật khẩu hiện đang nằm trên một instance cụ thể.
- **Không cascade `@Valid`** sang các object nested được truyền làm candidate. Ví dụ `validateValue(RegistrationForm.class, "address", new Address(""))` cho kết quả rỗng nếu `address` không có constraint trực tiếp, dù `Address.street` có `@NotBlank`.
- **Không đánh giá class-level/cross-field constraint**, vì không có trạng thái của các property khác để đối chiếu. Một rule như “ngày kết thúc phải sau ngày bắt đầu” không thể được đảm bảo bằng `validateValue` cho một field.
- Giá trị đầu vào nên đã là đúng kiểu đích (hoặc null khi kiểm tra nullability). `validateValue` không thay `ConversionService` hoặc JSON deserializer.
- Với custom constraint cần truy cập các property khác, bản thân một `validateValue` cho một field không cung cấp bean thật; nếu logic cần toàn context, thiết kế cross-field class-level validator và gọi `validate(object)`.

**Khi dùng:** validate một input thử nghiệm trước khi tạo object, kiểm tra candidate trong bước nhập liệu theo thuộc tính, hỗ trợ form metadata, hoặc kiểm thử rule của field khi không muốn khởi tạo bean.

### 5.1. So sánh trực tiếp ba phương thức

| Đặc điểm | `validate` | `validateProperty` | `validateValue` |
| --- | --- | --- | --- |
| Tham số chính | Bean instance | Bean instance + tên field | Bean class + tên field + candidate |
| Đọc giá trị từ bean | Có | Có, tại field được chọn | Không |
| Cần instance | Có | Có | Không |
| Kiểm tra nhiều property | Có | Không | Không |
| Constraint cấp lớp | Có | Không | Không |
| Cascade `@Valid` | Có | Không | Không |
| Kiểm tra constraint của field | Có | Có | Có |
| Dùng nhóm custom | Có | Có | Có |
| Tự gán giá trị/convert | Không | Không | Không |
| Trả `Set<ConstraintViolation<T>>` | Có | Có | Có |
| Trường hợp điển hình | Gửi form, kiểm tra object graph | Kiểm tra field đã lưu trong bean | Kiểm tra candidate trước khi gán |

Một ví dụ giúp nhớ: với `form.password = "123"`:

- `validate(form)` có thể báo mật khẩu, tên tài khoản và địa chỉ.
- `validateProperty(form, "password")` chỉ xét mật khẩu hiện tại `"123"`.
- `validateValue(RegistrationForm.class, "password", "long-enough")` chỉ xét giá trị mới `"long-enough"`; `form.password` vẫn là `"123"`.

## 6. Ví dụ Java 17+ đầy đủ: kiểm tra kết quả và phân biệt group/cascade

Ví dụ dùng **Jakarta Bean Validation** với **Hibernate Validator 8.x** làm provider. Spring Framework không bắt buộc có mặt trong chương trình độc lập; phần sau sẽ hướng dẫn cách dùng cùng `Validator` trong Spring MVC.

### 6.1. Tạo dự án Maven

Tạo `pom.xml` ở thư mục làm việc:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>validator-methods-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.1.Final</version>
        </dependency>
    </dependencies>
</project>
```

Dependency `hibernate-validator` kéo theo Jakarta Validation API và các dependency cần thiết. Để chạy CLI nhỏ này mà không cần thư viện Jakarta Expression Language (EL), ví dụ chủ động dùng `ParameterMessageInterpolator` của Hibernate Validator; với ứng dụng dùng message template có biểu thức EL, cần cấu hình EL tương ứng. `ParameterMessageInterpolator` là chi tiết provider, không thuộc giao diện Bean Validation chuẩn.

### 6.2. Tạo chương trình `ValidatorMethodsDemo.java`

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import jakarta.validation.groups.Default;

import org.hibernate.validator.HibernateValidator;
import org.hibernate.validator.messageinterpolation.ParameterMessageInterpolator;

import java.util.List;
import java.util.Set;

public class ValidatorMethodsDemo {

    // Nhóm nghiệp vụ bổ sung: chỉ kiểm tra tuổi khi yêu cầu nhóm này.
    public interface AgePolicy {}

    public static final class Address {
        @NotBlank
        private final String street;

        public Address(String street) {
            this.street = street;
        }
    }

    public static final class RegistrationForm {
        @NotBlank
        private final String username;

        @Size(min = 8)
        private final String password;

        @Min(value = 18, groups = AgePolicy.class)
        private final int age;

        @Valid
        private final Address address;

        public RegistrationForm(
                String username, String password, int age, Address address) {
            this.username = username;
            this.password = password;
            this.age = age;
            this.address = address;
        }

        public String getPassword() {
            return password;
        }
    }

    private static void show(
            String name, Set<? extends ConstraintViolation<?>> violations) {
        List<String> paths = violations.stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .toList();
        System.out.println(name + " -> " + violations.size() + " " + paths);
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory = Validation
                .byProvider(HibernateValidator.class)
                .configure()
                .messageInterpolator(new ParameterMessageInterpolator())
                .buildValidatorFactory()) {

            Validator validator = factory.getValidator();

            RegistrationForm form = new RegistrationForm(
                    "", "123", 16, new Address(""));

            show("validate(Default)", validator.validate(form));
            show("validate(AgePolicy)",
                    validator.validate(form, AgePolicy.class));
            show("validate(Default, AgePolicy)",
                    validator.validate(form, Default.class, AgePolicy.class));

            show("validateProperty(password)",
                    validator.validateProperty(form, "password"));
            show("validateProperty(address)",
                    validator.validateProperty(form, "address"));

            show("validateValue(password=123)",
                    validator.validateValue(
                            RegistrationForm.class, "password", "123"));
            show("validateValue(password=long-enough)",
                    validator.validateValue(
                            RegistrationForm.class, "password", "long-enough"));
            show("validateValue(age=16, AgePolicy)",
                    validator.validateValue(
                            RegistrationForm.class, "age", 16, AgePolicy.class));
            show("validateValue(address)",
                    validator.validateValue(
                            RegistrationForm.class, "address", new Address("")));

            System.out.println("originalPassword=" + form.getPassword());
        }
    }
}
```

**Cách chạy** với JDK 17+ và Maven cài sẵn:

Bash (Linux/macOS):

```bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
CP="$(cat classpath.txt)"
javac -encoding UTF-8 -cp "$CP" ValidatorMethodsDemo.java
java -cp ".:$CP" ValidatorMethodsDemo
```

PowerShell (Windows):

```powershell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
$cp = (Get-Content -Raw classpath.txt).Trim()
javac -encoding UTF-8 -cp $cp ValidatorMethodsDemo.java
java -cp ".;$cp" ValidatorMethodsDemo
```

**Stdout kỳ vọng** (không tính cảnh báo/log khởi động provider hoặc tải dependency):

```text
validate(Default) -> 3 [address.street, password, username]
validate(AgePolicy) -> 1 [age]
validate(Default, AgePolicy) -> 4 [address.street, age, password, username]
validateProperty(password) -> 1 [password]
validateProperty(address) -> 0 []
validateValue(password=123) -> 1 [password]
validateValue(password=long-enough) -> 0 []
validateValue(age=16, AgePolicy) -> 1 [age]
validateValue(address) -> 0 []
originalPassword=123
```

### 6.3. Phân tích từng kết quả

- `validate(Default)` trả ba property `username`, `password` và `address.street`. Nested path xuất hiện vì `address` được gắn `@Valid`; constraint `@Min` trên `age` chỉ thuộc nhóm `AgePolicy` nên chưa chạy.
- `validate(AgePolicy)` trả một violation cho `age`; các constraint thuộc `Default` không tự động chạy khi chỉ yêu cầu nhóm custom này.
- `validate(Default, AgePolicy)` chạy cả hai tập nhóm, trả bốn đường dẫn.
- `validateProperty(password)` kiểm tra `@Size(min=8)` trên đúng giá trị hiện có là `"123"`.
- `validateProperty(address)` trả rỗng vì property `address` không có constraint trực tiếp, chỉ có `@Valid` để cascade trong `validate`.
- `validateValue(password=123)` thất bại, trong khi candidate `"long-enough"` đạt `@Size(min=8)`, dù field thật của form chưa đổi.
- `validateValue(age=16, AgePolicy)` thất bại vì nhóm được truyền đúng.
- `validateValue(address)` không cascade sang `Address.street` nên trả rỗng.
- `originalPassword=123` chứng minh các lời gọi validate không làm biến đổi instance.

Để stdout nhất quán giữa môi trường, chương trình chỉ in số violation và các property path đã **sắp xếp**, thay vì in `Set` theo thứ tự ngẫu nhiên hoặc thông báo có thể thay đổi theo locale. Nhớ rằng một field có thể tạo nhiều violation nếu nó có nhiều constraint thất bại; số violation không mặc định bằng số field lỗi.

## 7. Validation groups: một nhóm khác có thể cho kết quả khác

Cả ba phương thức nhận đối số `Class<?>... groups`. Khi **không** chỉ định nhóm, nhóm mặc định `Default` được áp dụng. Khi **chỉ định** nhóm custom, đừng mặc định nhóm `Default` vẫn chạy kèm: ví dụ `validator.validate(form, AgePolicy.class)` chỉ chạy constraint thuộc nhóm `AgePolicy` (hoặc các constraint liên quan qua kế thừa/chuyển đổi nhóm/sequence theo metadata).

```java
public interface Create {}
public interface Update {}

@NotBlank(groups = Create.class)
private String initialPassword;

@NotNull(groups = {Create.class, Update.class})
private Long accountId;
```

Đây là đoạn minh họa trong bean, không phải tệp biên dịch độc lập. Nếu muốn luôn kiểm tra một constraint trong cả hai tác vụ, chỉ định đúng nhóm hoặc thiết kế group sequence phù hợp. Group có thể kế thừa, và `@GroupSequence` có quy tắc thứ tự/điều kiện dừng theo nhóm. Group sequence khác hẳn việc truyền nhiều nhóm thông thường, và khi dùng nhiều nhóm không có sequence thì không đảm bảo thứ tự thực thi.

**Cascade và group conversion:** trong `validate(root)`, `@Valid` có thể chuyển nhóm khi đi xuống object lồng bằng `@ConvertGroup`; đó là tính năng cascade. Với `validateProperty` và `validateValue`, không có cascade, nên không thể dùng hai phương thức này để xác thực toàn bộ hiệu ứng `@ConvertGroup` của cây đối tượng.

**Kiểm tra theo giai đoạn:** form nhập nhiều bước có thể gọi `validateProperty` hoặc `validateValue` để phản hồi nhanh, nhưng trước khi lưu nên `validate(form, relevantGroups...)` để chạy cả constraint mức lớp và nested. Nếu cần quy tắc "chỉ update thì được để trống một field", xác định chính sách groups và constraint rõ ràng, tránh lấy một group tùy ý rồi kết luận toàn bean hợp lệ.

## 8. Tích hợp trong Spring Framework / Spring MVC

### 8.1. Hai giao diện có tên `Validator` dễ nhầm

- `jakarta.validation.Validator`: API Jakarta, có `validate`, `validateProperty`, `validateValue`, trả `Set<ConstraintViolation<T>>`.
- `org.springframework.validation.Validator`: API Spring, có `supports(Class<?>)` và `validate(Object, Errors)`, ghi lỗi vào `Errors`/`BindingResult`.

`org.springframework.validation.beanvalidation.LocalValidatorFactoryBean` là cầu nối quan trọng: nó tích hợp provider Bean Validation vào cơ chế validation Spring và có thể được sử dụng qua giao diện Jakarta. Trong dự án Spring Boot 3.x, starter `spring-boot-starter-validation` thông thường cung cấp Jakarta Validation API + provider; cần kiểm tra dependency thật của dự án. Việc import nhầm interface là một nguyên nhân phổ biến khiến IDE báo không tìm thấy `validateValue`.

Để viết service gọi cả ba API, inject rõ giao diện Jakarta:

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import org.springframework.stereotype.Service;
import java.util.Set;

@Service
public class RegistrationValidationService {
    private final Validator validator;

    public RegistrationValidationService(Validator validator) {
        this.validator = validator;
    }

    public Set<ConstraintViolation<RegistrationForm>> checkAll(
            RegistrationForm form) {
        return validator.validate(form);
    }

    public Set<ConstraintViolation<RegistrationForm>> checkField(
            RegistrationForm form, String propertyName) {
        return validator.validateProperty(form, propertyName);
    }

    public Set<ConstraintViolation<RegistrationForm>> checkCandidate(
            String candidatePassword) {
        return validator.validateValue(
                RegistrationForm.class, "password", candidatePassword);
    }
}
```

Đây là **đoạn tích hợp**: dự án Spring cần cung cấp bean `Validator` của Jakarta, `RegistrationForm` và dependency Bean Validation. Trong sản phẩm thực tế, không cho client tự chọn tên `propertyName` không giới hạn; định nghĩa danh sách field hợp lệ để tránh mở rộng không chủ ý bề mặt kiểm tra và tiết lộ metadata.

### 8.2. Tự động validation trong controller

Với một form đã bind vào bean:

```java
@PostMapping("/registrations")
public ResponseEntity<?> create(
        @Valid @ModelAttribute RegistrationForm form,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return ResponseEntity.badRequest()
                .body(bindingResult.getFieldErrors().stream()
                        .map(e -> e.getField() + ": " + e.getCode())
                        .toList());
    }

    return ResponseEntity.ok().build();
}
```

Đây là đoạn minh họa trong `@Controller`/`@RestController`, không phải một chương trình Java độc lập; cần import đúng các kiểu Spring MVC, Jakarta `@Valid` và model có thể được Spring bind (constructor/getter/setter hoặc binder tương ứng). Với form có bean immutable, cần cấu hình binding constructor phù hợp; không suy ra code immutable ở mục 6 tự được MVC bind từ mọi loại request.

- `@Valid` kích hoạt Bean Validation trên đối tượng được bind, mặc định dùng nhóm `Default`; đây là con đường validation **toàn đối tượng** theo cấu hình của Spring.
- `@Validated(SomeGroup.class)` của Spring cho phép chọn group khi validation đối tượng; cần nêu rõ group mong muốn.
- `BindingResult` đặt **ngay sau** tham số model tương ứng để controller có thể đọc lỗi của chính nó; lỗi chuyển kiểu, binding và constraint có thể cùng xuất hiện.
- Spring MVC có thể trả các exception khác nhau theo việc dùng `@ModelAttribute`, `@RequestBody`, method validation và chữ ký controller. Không giả định mọi validation failure tự động có cùng JSON/body/status nếu chưa định nghĩa exception handler.

`@RequestBody` JSON được deserializer (thường Jackson) chuyển thành object trước khi chạy validation. Khả năng `@Valid` kiểm tra DTO đã đọc thành công không có nghĩa Bean Validation xử lý JSON syntax/type conversion. Với method parameter/return value constraints còn có **executable validation** (thường dùng `ExecutableValidator` hoặc tích hợp Spring), phạm vi khác với ba phương thức dành cho bean property trong bài.

### 8.3. Đưa violation về thông báo cho UI

Mỗi violation có `propertyPath`, `message` và thông tin constraint. Ứng dụng nên chuyển chúng thành mã lỗi/ngữ nghĩa giao diện tương ứng, tránh trả ra class, mật khẩu, giá trị raw nhạy cảm hoặc message nội bộ. Đối với Spring MVC, `BindingResult.getFieldErrors()` và `getGlobalErrors()` phân biệt lỗi gắn với field và lỗi cấp object.

Mọi kiểm tra candidate bằng `validateValue` chỉ mang tính hỗ trợ phản hồi sớm. Khi chấp nhận yêu cầu, vẫn cần xác thực trạng thái cuối của object sau khi bind, áp dụng các group cần thiết và kiểm tra các ràng buộc nghiệp vụ không biểu đạt được bằng annotation.

## 9. Những trường hợp dễ hiểu sai

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `validateProperty(form, "address")` trả rỗng dù `address.street` rỗng | `@Valid` không cascade trong `validateProperty` | Dùng `validate(form)` hoặc validate riêng bean `address` |
| `validateValue` trả rỗng, nhưng gửi cả form lại bị từ chối | Rule ở class-level hoặc nested không được xét khi chỉ kiểm tra candidate | Xác thực cả bean trong bước cuối |
| Gọi `validate(form, Create.class)` làm bỏ qua `@NotBlank` không khai báo groups | Constraint nằm ở `Default` | Chọn nhóm đúng hoặc đưa constraint vào nhóm phù hợp |
| `@Size(min=8)` không báo lỗi khi mật khẩu `null` | `@Size` cho phép null | Thêm `@NotNull` hoặc `@NotBlank` |
| `@NotNull` không từ chối chuỗi toàn dấu cách | `@NotNull` chỉ cấm null | Dùng `@NotBlank` với chuỗi |
| `getPropertyPath()` không có field rõ ràng | Class-level constraint có thể gắn ở node đối tượng | Xử lý cả global errors, không chỉ field errors |
| Số lỗi/test thay đổi thứ tự | `Set<ConstraintViolation<?>>` không đảm bảo thứ tự | Sort theo path và mã constraint |
| Gọi `validateValue` bằng String cho property kiểu khác và nhận exception | Bean Validation không đảm nhiệm convert | Parse/bind về kiểu Java đúng trước |
| `Validator` không có `validateProperty` | Import `org.springframework.validation.Validator` | Import `jakarta.validation.Validator` khi cần API Jakarta |
| Dùng `javax.validation.*` cùng Spring 6/Jakarta provider | Không tương thích namespace/dependency | Đồng bộ Jakarta API, provider và bản Spring |
| Kiểm tra một property mà vẫn mong rule liên quan property khác chạy | `validateProperty` loại class-level/cross-field | Dùng `validate` để đánh giá toàn bean |
| Hiển thị nguyên `getInvalidValue()` cho client | Có thể lộ mật khẩu, token hoặc dữ liệu nhạy cảm | Trả mã/thông báo an toàn, không log giá trị bí mật |
| Gọi validation liên tục với provider factory mới cho mỗi input | Bootstrap metadata/provider tốn tài nguyên | Tái sử dụng `ValidatorFactory`/`Validator` hoặc bean được container quản lý |
| Mong Bean Validation sửa lỗi dữ liệu | Validation không mutate bean | Sửa dữ liệu bằng normalization/conversion trước, sau đó validate |

### Kiểm thử cần có cho cả ba API

1. Bean có nhiều lỗi thuộc các property khác nhau: `validate` trả tập vi phạm toàn diện trong nhóm đã chọn.
2. Bean con có `@Valid` và constraint: `validate(root)` thấy nested path, `validateProperty(root, "child")` không cascade.
3. Giá trị ứng viên hợp lệ/không hợp lệ: `validateValue` thay đổi kết quả theo candidate, **bean gốc không đổi**.
4. Kiểm thử `Default` và một nhóm custom: chứng minh group selection thực tế.
5. Kiểm thử null, rỗng, khoảng trắng, giá trị sai kiểu, tên property không tồn tại và constraint metadata sai.
6. Constraint cấp lớp phụ thuộc hai field: chỉ `validate` toàn bean mới có đủ context.
7. Trường hợp HTTP: binding lỗi, Bean Validation lỗi và kết quả `BindingResult`; bảo đảm lỗi được trả theo hợp đồng API.
8. Constraint bổ sung vào bean theo thời gian: kiểm thử cuối phải còn bao phủ validation toàn object để các rule mới không bị bỏ sót.

## 10. Cách quyết định sử dụng

Khi viết code, tự hỏi:

1. **Tôi đã có instance bean đầy đủ và cần kết luận nó hợp lệ chưa?** → `validator.validate(bean, groups...)`.
2. **Tôi chỉ muốn kiểm tra giá trị của một property hiện nằm trong bean?** → `validator.validateProperty(bean, "property", groups...)`.
3. **Tôi chưa tạo/không muốn thay đổi bean, chỉ cần kiểm tra một giá trị mới theo annotation của field?** → `validator.validateValue(Bean.class, "property", candidate, groups...)`.
4. **Rule liên quan nhiều field hoặc bean con?** → dùng `validate` toàn đối tượng (hoặc một validator nghiệp vụ phù hợp); hai API field-level không xác nhận được rule liên kết.
5. **Ngữ cảnh là Spring MVC?** → ưu tiên validation tích hợp `@Valid`/`@Validated` và xử lý `BindingResult` cho bước submit; dùng ba phương thức Jakarta trực tiếp khi thực sự cần kiểm tra thủ công, theo từng field hoặc candidate.

Điểm cốt lõi: **`validate` nhìn toàn bộ đối tượng và graph được cascade; `validateProperty` đọc một field hiện tại; `validateValue` thử một giá trị giả định từ metadata của field.** Chúng chia sẻ hệ thống constraint và group, nhưng **khác phạm vi dữ liệu và đặc biệt khác ở khả năng cascade**. Chọn sai phạm vi có thể dẫn đến kết luận “hợp lệ” khi thực tế chỉ có một ô nhập liệu được kiểm tra.

### Tài liệu tham khảo

- Jakarta Validation 3.0, giao diện `Validator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/validator
- Jakarta Validation 3.0 Specification — object graph, property, value validation: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Hibernate Validator 8.x Reference Guide: https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/
- Spring Framework — Bean Validation integration: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC — Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
