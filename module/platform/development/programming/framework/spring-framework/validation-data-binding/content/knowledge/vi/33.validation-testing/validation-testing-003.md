# Kiểm thử DataBinder với giá trị đúng, sai kiểu và thiếu trường

## 1. Mục tiêu bài học

Trong Spring Framework, `org.springframework.validation.DataBinder` là thành phần nhận các giá trị theo tên property, thực hiện **binding** vào đối tượng Java và thu thập lỗi qua `BindingResult`. Thử nghiệm một form trong trình duyệt chỉ cho biết hành vi cuối của HTTP API; test trực tiếp `DataBinder` giúp tách rõ **lỗi chuyển kiểu**, **lỗi thiếu trường**, **lỗi validation nghiệp vụ** và **trường bị từ chối binding**.

Sau bài này, bạn có thể:

1. Tạo binder độc lập cho một JavaBean bằng `new DataBinder(target, objectName)`.
2. Gửi dữ liệu mô phỏng request bằng `MutablePropertyValues` và gọi `binder.bind(values)`.
3. Kiểm tra trường hợp đúng: `String "3"` được chuyển thành `Integer 3` mà không có lỗi.
4. Kiểm tra sai kiểu: `"abc"` không chuyển thành `Integer`, tạo `FieldError` với mã tổng quát `typeMismatch`.
5. Kiểm tra trường bắt buộc bị thiếu: `setRequiredFields("quantity")` tạo lỗi `required` ngay trong binding.
6. Phân biệt “không gửi trường” với “gửi trường rỗng”, “giá trị `null`” và “đã bind nhưng sai quy tắc nghiệp vụ”.
7. Tự gọi `binder.validate()` để chạy Spring `Validator` đã đăng ký và tách lỗi validation khỏi lỗi binding.
8. Kiểm tra `setAllowedFields(...)` và `getSuppressedFields()`, tránh over-posting khi test.
9. Viết test JUnit 5 có thể chạy bằng Maven, không phụ thuộc web server hoặc database.

**Thông điệp quan trọng:** `DataBinder#bind(...)` **không đồng nghĩa** với `DataBinder#validate()`. Một object đã bind thành công có thể vẫn vi phạm nghiệp vụ; một object thiếu trường có thể chưa có `FieldError` nếu bạn chưa cấu hình `requiredFields` hoặc validator tương ứng.

## 2. DataBinder và các lớp tham gia

### 2.1. Những API cần biết

| API | Vai trò |
| --- | --- |
| `DataBinder` | Cấu hình và thực hiện property binding, validation |
| `MutablePropertyValues` | Tập cặp tên property/giá trị đầu vào, tương tự form parameters |
| `DataBinder#bind(PropertyValues)` | Gán dữ liệu vào target, có thể ghi lỗi binding |
| `DataBinder#setRequiredFields(...)` | Khai báo property phải có trong lần bind |
| `DataBinder#setAllowedFields(...)` | Giới hạn các property có thể được gán |
| `DataBinder#setValidator(...)` | Chọn validator áp dụng sau khi chủ động gọi `validate()` |
| `DataBinder#validate()` | Chạy validator đã đăng ký và bổ sung lỗi |
| `DataBinder#getBindingResult()` | Đọc đối tượng `BindingResult` chứa lỗi, trạng thái field |
| `BindingResult#getFieldError("quantity")` | Lấy lỗi đầu tiên của field được chỉ định |
| `FieldError#getCode()` | Lấy mã lỗi tổng quát, ví dụ `typeMismatch` |
| `FieldError#getCodes()` | Lấy dãy mã cho cơ chế i18n, từ cụ thể tới tổng quát |
| `FieldError#isBindingFailure()` | Phân biệt lỗi binding/conversion với lỗi được reject qua validation |
| `BindingResult#getSuppressedFields()` | Tên các property input bị binder loại theo field restrictions |

`DataBinder` nằm trong `spring-context` và dùng được ngoài web environment. `WebDataBinder` mở rộng nó cho Spring MVC, nên test trực tiếp `DataBinder` là cách tốt để kiểm chứng **cơ chế cốt lõi** mà không cần khởi động Spring Boot.

### 2.2. Dòng xử lý cơ bản

```text
new OrderForm()
      |
      v
new DataBinder(orderForm, "orderForm")
      |
      +-- setAllowedFields("code", "quantity")
      +-- setRequiredFields("code", "quantity")
      +-- setValidator(new OrderValidator())
      |
      v
MutablePropertyValues: code="OR-101", quantity="3"
      |
      v
binder.bind(values)
      |
      +-- loại field không được phép => suppressedFields
      +-- kiểm tra required fields => FieldError("required")
      +-- chuyển kiểu và gọi setters => có thể FieldError("typeMismatch")
      |
      v
binder.validate()   <-- BƯỚC RIÊNG
      |
      +-- chạy Spring Validator / ghi FieldError từ rejectValue()
      |
      v
BindingResult: field errors, global errors, suppressed fields
```

Đây là luồng của **property binding trên một JavaBean có setter**. `DataBinder` từ Spring 6.1 còn hỗ trợ constructor binding qua `construct(...)`, nhưng nó có cách tạo target và xét tham số khác với `bind(PropertyValues)`.

Không cần Spring MVC controller để chạy các test JUnit ở mục 7.

## 3. Test đầu tiên: dữ liệu đúng

Giả sử object:

```java
public class OrderForm {
    private String code;
    private Integer quantity;

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
```

Đây là fragment JavaBean (mỗi class public cần file phù hợp); ví dụ chạy hoàn chỉnh dùng một nested static class trong `DataBinderDemo.java`.

Tạo dữ liệu và bind:

```java
OrderForm form = new OrderForm();
DataBinder binder = new DataBinder(form, "orderForm");

MutablePropertyValues values = new MutablePropertyValues();
values.add("code", "OR-101");
values.add("quantity", "3");

binder.bind(values);

BindingResult result = binder.getBindingResult();
System.out.println(form.getQuantity()); // 3
System.out.println(result.hasErrors()); // false
```

Điều cần hiểu:

- `MutablePropertyValues` mang giá trị `quantity` là **String**.
- `OrderForm.quantity` là **Integer**.
- Spring dùng các khả năng type conversion/property editors phù hợp trong `DataBinder` để gán Integer.
- Một binder vừa tạo không tự gọi Bean Validation chỉ vì class có `@Min` hoặc `@NotNull`. Cần cấu hình và kích hoạt validation theo đường phù hợp.

Test nên kiểm tra **kiểu Java đích**, không chỉ so sánh string: `assertEquals(Integer.valueOf(3), form.getQuantity())`. Đó là bằng chứng conversion đã xảy ra.

## 4. Test sai kiểu: String không chuyển được sang Integer

Thay `quantity="3"` bằng `quantity="abc"`:

```java
MutablePropertyValues values = new MutablePropertyValues();
values.add("code", "OR-101");
values.add("quantity", "abc");

binder.bind(values);
FieldError error =
    binder.getBindingResult().getFieldError("quantity");
```

Ở đường property binding mặc định, Spring ghi lỗi conversion vào `BindingResult` thay vì biến ngay mọi `TypeMismatchException` thành exception thoát khỏi `bind()`.

Các assertions cần thiết:

```java
assertNotNull(error);
assertEquals("typeMismatch", error.getCode());
assertTrue(error.isBindingFailure());
assertNull(form.getQuantity());
```

Đây là các fragments JUnit; cần khai báo `binder`, `form` và static imports. Bản runnable ở mục 7.

### 4.1. Tại sao isBindingFailure() quan trọng?

`FieldError#isBindingFailure()` trả biết lỗi phát sinh khi chuyển/gán dữ liệu vào target, phân biệt với lỗi do `errors.rejectValue(...)` trong validator. Với `quantity="abc"`, Spring chưa có `Integer` hợp lệ để `@Min(1)` hoặc custom min validator đánh giá.

Một số lỗi binding thường gặp:

| Tình huống | Mã lỗi tổng quát điển hình |
| --- | --- |
| Không có required field | `required` |
| Giá trị không chuyển được về target type | `typeMismatch` |
| Setter/property method phát sinh exception | `methodInvocation` |

Mã lỗi thực tế phụ thuộc `BindingErrorProcessor` và `MessageCodesResolver` đang dùng. Các tên trong bảng là mặc định của Spring. Một `FieldError` còn có `getCodes()` là dãy mã dùng cho localization, không chỉ một String.

### 4.2. Không dựa vào rejected value cho logic nghiệp vụ

Với type mismatch, `FieldError#getRejectedValue()` có thể chứa dữ liệu text bị từ chối. Nó hữu ích khi debug/test nhưng không nên tự động đưa vào log hoặc HTTP response, vì có thể chứa token, email, số tài khoản hoặc dữ liệu nhạy cảm.

Để trả lỗi API, nên ánh xạ `typeMismatch` thành mã lỗi public ổn định và thông báo phù hợp locale.

## 5. Test thiếu trường với setRequiredFields

Spring phân biệt **property không có mặt trong dữ liệu đầu vào** với **giá trị property đang null**.

Cấu hình:

```java
DataBinder binder = new DataBinder(new OrderForm(), "orderForm");
binder.setRequiredFields("code", "quantity");
```

Gửi chỉ `code`, không có `quantity`:

```java
MutablePropertyValues values = new MutablePropertyValues();
values.add("code", "OR-101");

binder.bind(values);

FieldError error =
    binder.getBindingResult().getFieldError("quantity");
```

Khi `quantity` thuộc `requiredFields` nhưng không có trong tập values của lần bind, default binding error processor tạo lỗi có code `required`. Target vẫn có `quantity == null` vì không có dữ liệu để gán.

**Đây là kiểm tra ở bước binding**, không phải Jakarta `@NotNull` và không cần gọi `binder.validate()` mới tạo `required`.

### 5.1. Thiếu trường mà không setRequiredFields

Một binder khác:

```java
DataBinder binder = new DataBinder(new OrderForm(), "orderForm");

MutablePropertyValues values = new MutablePropertyValues();
values.add("code", "OR-101");

binder.bind(values);
```

Nếu không có required fields hoặc validator đã chạy, `quantity` có thể giữ `null` và `BindingResult#hasErrors()` vẫn là `false`. Điều này hoàn toàn phù hợp với cơ chế: **không gửi field không tự là lỗi** nếu contract chưa yêu cầu.

Khi không cấu hình `requiredFields` nhưng muốn chặn missing quantity, có thể sử dụng:

- `@NotNull`/Jakarta Bean Validation, được kích hoạt sau binding.
- Spring `Validator` tự viết rồi gọi `binder.validate()`.
- Required argument semantics của web annotations, ví dụ một `@RequestParam(required=true)` trong MVC; đây là cơ chế khác với generic `DataBinder`.

### 5.2. “Thiếu”, “rỗng” và “sai kiểu” không đồng nghĩa

| Input | Tình huống | Điều cần test |
| --- | --- | --- |
| Không có key `quantity` | Missing property | Nếu `setRequiredFields("quantity")`, kiểm tra `required` |
| `quantity=""` | Key tồn tại với chuỗi rỗng | Kết quả phụ thuộc conversion/required processing; test thực tế |
| `quantity="abc"` | Có chuỗi nhưng không parse được Integer | `typeMismatch` |
| `quantity="0"` | Chuyển được Integer, nhưng có thể sai nghiệp vụ | `binder.validate()` tạo `minQuantity` hoặc `@Min` |
| `quantity="3"` | Chuyển kiểu hợp lệ | Field có giá trị Integer 3 |
| `quantity=null` trong target trước bind | Trạng thái Java ban đầu | Không đồng nghĩa client gửi null |
| `quantity=" 3 "` | Có whitespace | Cách parse phụ thuộc conversion service; nên kiểm thử chính sách normalize |

**Không khẳng định mọi empty String sẽ luôn chuyển sang null theo mọi converter.** Với dữ liệu HTTP, giá trị rỗng còn chịu cơ chế argument resolver và converter của MVC. Bài này dùng test có/không có key rõ ràng để tránh nhầm missing với blank.

### 5.3. Kiểu Integer hay int?

Trong form DTO, dùng `Integer` thay vì primitive `int` khi bạn cần phân biệt “chưa có dữ liệu” với “đã nhập số 0”. Nếu dùng `int`, giá trị mặc định Java là 0 và có thể bị nhầm là input thực sự.

`@NotNull` không có tác dụng hữu ích với primitive vì primitive không thể null. Khi thiết kế DTO và tests, chọn kiểu dữ liệu phù hợp với semantics của missing field.

## 6. Binding khác validation: test hai bước

Một Spring `Validator` có thể kiểm tra rằng quantity không null và không dưới 1:

```java
public final class OrderValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return OrderForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        OrderForm form = (OrderForm) target;

        if (errors.hasFieldErrors("quantity")) {
            return; // Đã có lỗi binding; tránh ghi lỗi nghiệp vụ gây nhiễu.
        }
        if (form.getQuantity() == null) {
            errors.rejectValue("quantity", "requiredByValidator");
        } else if (form.getQuantity() < 1) {
            errors.rejectValue("quantity", "minQuantity");
        }
    }
}
```

Đây là fragment; cần imports cho `Validator`, `Errors` và class `OrderForm`. Bản đầy đủ nằm ở mục 7.

Kết nối validator:

```java
binder.setValidator(new OrderValidator());
binder.bind(values);

// Sau bind: chỉ có binding errors.
// Sau validate: thêm semantic validation errors.
binder.validate();

BindingResult result = binder.getBindingResult();
```

Trường hợp `quantity="0"`:

1. Binder parse được `"0"` thành Integer 0, nên không có lỗi `typeMismatch`.
2. Khi `validate()` chạy, validator kiểm tra `0 < 1` và gọi `errors.rejectValue("quantity","minQuantity")`.
3. `FieldError#getCode()` là `minQuantity`, và `isBindingFailure()` thường là `false` vì lỗi do validator reject, không phải conversion failure.

Nếu chỉ gọi `bind()` mà không gọi `validate()`, lỗi `minQuantity` sẽ không tự xuất hiện trong generic DataBinder.

### 6.1. DataBinder không tự chạy @Valid

Trong Spring MVC, controller có `@Valid @ModelAttribute(...)` sẽ kích hoạt validation thông qua infrastructure. Nhưng generic `DataBinder` được tự tạo trong test **không tự biết `@Valid` hay Bean Validation provider** trừ khi bạn gắn validator và gọi `validate()`.

Nếu muốn test Jakarta constraints trực tiếp, có thể dùng `LocalValidatorFactoryBean` (với Jakarta Bean Validation provider trong classpath) rồi gọi `binder.setValidator(beanValidator); binder.validate();`. Đây là một setup rộng hơn; mẫu runnable ở đây dùng Spring `Validator` thuần để tách các cơ chế thật rõ.

### 6.2. Tránh lỗi chồng lỗi giả tạo

Khi quantity sai kiểu `"abc"`, target.quantity có thể còn null. Nếu custom validator thấy null rồi thêm cả `requiredByValidator`, test hoặc API sẽ có hai lỗi cho một nguyên nhân. Vì vậy ví dụ dùng `errors.hasFieldErrors("quantity")` để bỏ qua kiểm tra nghiệp vụ trên field đã lỗi binding.

Đó là **quyết định của custom validator trong ví dụ**, không phải một hành vi mà mọi Bean Validation provider tự áp dụng. Khi test kết hợp, hãy xác định chính sách lỗi của ứng dụng và đừng phụ thuộc vào thứ tự error objects nếu không cần.

## 7. Ví dụ chạy độc lập: Java 17, Spring Framework 6.2 và JUnit 5

### 7.1. Cấu trúc

```text
data-binder-tests/
├── pom.xml
└── src/
    ├── main/java/demo/binding/
    │   └── DataBinderDemo.java
    └── test/java/demo/binding/
        └── DataBinderDemoTest.java
```

Chỉ có một file chương trình và một file test. Không cần Spring Boot, database hoặc server vì trọng tâm là API `DataBinder`.

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>demo</groupId>
  <artifactId>data-binder-tests</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.8</version>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.12.2</version>
      <scope>test</scope>
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
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.2</version>
      </plugin>
    </plugins>
  </build>
</project>
```

Vì Spring DataBinder thuộc Spring Framework core/context infrastructure, `spring-context` và các dependencies transitive cung cấp classes cần thiết. JUnit Jupiter nằm ở test scope. Java 17 là mức tương thích cho Spring Framework 6.x.

### 7.3. DataBinderDemo.java

```java
package demo.binding;

import java.util.Arrays;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.Validator;

public class DataBinderDemo {

    public static class OrderForm {
        private String code;
        private Integer quantity;

        public OrderForm() {
        }

        public String getCode() {
            return code;
        }

        public void setCode(String code) {
            this.code = code;
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }
    }

    public static class OrderValidator implements Validator {

        @Override
        public boolean supports(Class<?> type) {
            return OrderForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            OrderForm form = (OrderForm) target;

            if (errors.hasFieldErrors("quantity")) {
                return;
            }

            if (form.getQuantity() == null) {
                errors.rejectValue("quantity", "requiredByValidator");
            } else if (form.getQuantity() < 1) {
                errors.rejectValue("quantity", "minQuantity");
            }
        }
    }

    // Mỗi test/case phải dùng một binder và target mới.
    public static DataBinder newBinder(OrderForm target,
                                       boolean requiredFields) {
        DataBinder binder = new DataBinder(target, "orderForm");

        binder.setAllowedFields("code", "quantity");
        if (requiredFields) {
            binder.setRequiredFields("code", "quantity");
        }
        binder.setValidator(new OrderValidator());

        return binder;
    }

    public static MutablePropertyValues values(
            String code, String quantity) {

        MutablePropertyValues pvs = new MutablePropertyValues();

        if (code != null) {
            pvs.add("code", code);
        }
        if (quantity != null) {
            pvs.add("quantity", quantity);
        }

        return pvs;
    }

    private static String errorCode(
            BindingResult result, String field) {

        FieldError error = result.getFieldError(field);
        return error == null ? "none" : error.getCode();
    }

    private static void validCase() {
        OrderForm target = new OrderForm();
        DataBinder binder = newBinder(target, true);

        binder.bind(values("OR-101", "3"));
        binder.validate();

        System.out.println(
            "VALID | code=" + target.getCode()
            + " | quantity=" + target.getQuantity()
            + " | errors=" + binder.getBindingResult().getErrorCount());
    }

    private static void wrongTypeCase() {
        OrderForm target = new OrderForm();
        DataBinder binder = newBinder(target, true);

        binder.bind(values("OR-101", "abc"));

        System.out.println(
            "WRONG_TYPE | quantity=" + target.getQuantity()
            + " | error=" + errorCode(
                binder.getBindingResult(), "quantity"));
    }

    private static void missingRequiredCase() {
        OrderForm target = new OrderForm();
        DataBinder binder = newBinder(target, true);

        // Không thêm key quantity vào MutablePropertyValues.
        binder.bind(values("OR-101", null));

        System.out.println(
            "MISSING_REQUIRED | quantity=" + target.getQuantity()
            + " | error=" + errorCode(
                binder.getBindingResult(), "quantity"));
    }

    private static void missingWithoutRuleCase() {
        OrderForm target = new OrderForm();
        DataBinder binder = newBinder(target, false);

        binder.bind(values("OR-101", null));

        System.out.println(
            "MISSING_WITHOUT_RULE | quantity=" + target.getQuantity()
            + " | errors=" + binder.getBindingResult().getErrorCount());

        // Khi chủ động validate(), custom Validator mới ghi lỗi.
        binder.validate();
        System.out.println(
            "MISSING_AFTER_VALIDATE | error=" + errorCode(
                binder.getBindingResult(), "quantity"));
    }

    private static void invalidBusinessCase() {
        OrderForm target = new OrderForm();
        DataBinder binder = newBinder(target, true);

        binder.bind(values("OR-101", "0"));
        binder.validate();

        System.out.println(
            "SEMANTIC_INVALID | quantity=" + target.getQuantity()
            + " | error=" + errorCode(
                binder.getBindingResult(), "quantity"));
    }

    private static void suppressedFieldCase() {
        OrderForm target = new OrderForm();
        DataBinder binder = newBinder(target, true);

        MutablePropertyValues pvs = values("OR-101", "3");
        pvs.add("role", "ADMIN");

        binder.bind(pvs);

        String[] suppressed =
            binder.getBindingResult().getSuppressedFields();
        Arrays.sort(suppressed);

        System.out.println(
            "SUPPRESSED | fields=" + String.join(",", suppressed)
            + " | errors=" + binder.getBindingResult().getErrorCount());
    }

    public static void main(String[] args) {
        validCase();
        wrongTypeCase();
        missingRequiredCase();
        missingWithoutRuleCase();
        invalidBusinessCase();
        suppressedFieldCase();
    }
}
```

### 7.4. Giải thích thiết kế chương trình

- `OrderForm` có constructor mặc định và setters, đúng hình thức JavaBeans property binding.
- `DataBinderDemo#values(...)` tạo **MutablePropertyValues mới** mỗi lần để tránh trường hợp binder thay đổi một instance dùng lại.
- `newBinder(...)` cho phép bật/tắt `requiredFields` trong những test riêng. `setAllowedFields("code","quantity")` ngăn ngoài danh sách.
- `OrderValidator` kiểm tra `quantity` null hoặc nhỏ hơn 1 **khi validate() được gọi**, không trong `bind()`.
- `wrongTypeCase()` không gọi `validate()` để khẳng định `typeMismatch` là lỗi binding thuần.
- `missingRequiredCase()` không gọi `validate()`: lỗi `required` đến từ cấu hình binder.
- `missingWithoutRuleCase()` cho thấy bước bind không báo lỗi khi thiếu field nếu không cấu hình required; sau `validate()` mới có `requiredByValidator`.
- `suppressedFieldCase()` cho thấy input `role` bị allowlist loại bỏ và xuất hiện trong suppressed fields **mà không tự sinh FieldError**.

### 7.5. Chạy chương trình

Yêu cầu Java 17+, Maven 3.x, kết nối Maven repository để tải dependencies lần đầu. Trong thư mục chứa `pom.xml`:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java \
  -Dexec.mainClass=demo.binding.DataBinderDemo
```

Các dòng `System.out.println` từ mã demo có dạng sau, không tính Maven/plugin logging:

```text
VALID | code=OR-101 | quantity=3 | errors=0
WRONG_TYPE | quantity=null | error=typeMismatch
MISSING_REQUIRED | quantity=null | error=required
MISSING_WITHOUT_RULE | quantity=null | errors=0
MISSING_AFTER_VALIDATE | error=requiredByValidator
SEMANTIC_INVALID | quantity=0 | error=minQuantity
SUPPRESSED | fields=role | errors=0
```

Trường hợp `SUPPRESSED` có `errors=0` là một bài học bảo mật quan trọng. Nếu API muốn từ chối request mang field ngoài allowlist, phải **chủ động kiểm tra `getSuppressedFields()`** và quyết định HTTP 4xx/không thực hiện side effects. `hasErrors() == false` không có nghĩa toàn bộ input client gửi đã được chấp nhận.

### 7.6. DataBinderDemoTest.java — kiểm thử JUnit 5

```java
package demo.binding;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

class DataBinderDemoTest {

    @Test
    void validInputConvertsStringToInteger() {
        DataBinderDemo.OrderForm target = new DataBinderDemo.OrderForm();
        DataBinder binder = DataBinderDemo.newBinder(target, true);

        binder.bind(DataBinderDemo.values("OR-101", "3"));
        binder.validate();

        assertFalse(binder.getBindingResult().hasErrors());
        assertEquals("OR-101", target.getCode());
        assertEquals(Integer.valueOf(3), target.getQuantity());
    }

    @Test
    void incompatibleTypeCreatesTypeMismatch() {
        DataBinderDemo.OrderForm target = new DataBinderDemo.OrderForm();
        DataBinder binder = DataBinderDemo.newBinder(target, true);

        binder.bind(DataBinderDemo.values("OR-101", "abc"));

        BindingResult result = binder.getBindingResult();
        FieldError error = result.getFieldError("quantity");

        assertNotNull(error);
        assertEquals("typeMismatch", error.getCode());
        assertTrue(error.isBindingFailure());
        assertNull(target.getQuantity());
        assertEquals(1, result.getErrorCount());
    }

    @Test
    void missingConfiguredFieldCreatesRequiredErrorDuringBind() {
        DataBinderDemo.OrderForm target = new DataBinderDemo.OrderForm();
        DataBinder binder = DataBinderDemo.newBinder(target, true);

        binder.bind(DataBinderDemo.values("OR-101", null));

        FieldError error =
            binder.getBindingResult().getFieldError("quantity");

        assertNotNull(error);
        assertEquals("required", error.getCode());
        assertNull(target.getQuantity());
        assertEquals(1, binder.getBindingResult().getErrorCount());
    }

    @Test
    void missingFieldCanBeSilentUntilValidation() {
        DataBinderDemo.OrderForm target = new DataBinderDemo.OrderForm();
        DataBinder binder = DataBinderDemo.newBinder(target, false);

        binder.bind(DataBinderDemo.values("OR-101", null));
        assertFalse(binder.getBindingResult().hasErrors());

        binder.validate();

        FieldError error =
            binder.getBindingResult().getFieldError("quantity");

        assertNotNull(error);
        assertEquals("requiredByValidator", error.getCode());
        assertFalse(error.isBindingFailure());
    }

    @Test
    void numericValueCanBindButFailSemanticValidation() {
        DataBinderDemo.OrderForm target = new DataBinderDemo.OrderForm();
        DataBinder binder = DataBinderDemo.newBinder(target, true);

        binder.bind(DataBinderDemo.values("OR-101", "0"));
        assertFalse(binder.getBindingResult().hasErrors());

        binder.validate();

        assertEquals(Integer.valueOf(0), target.getQuantity());
        FieldError error =
            binder.getBindingResult().getFieldError("quantity");
        assertNotNull(error);
        assertEquals("minQuantity", error.getCode());
        assertFalse(error.isBindingFailure());
    }

    @Test
    void additionalFieldIsSuppressedAndMustBeCheckedExplicitly() {
        DataBinderDemo.OrderForm target = new DataBinderDemo.OrderForm();
        DataBinder binder = DataBinderDemo.newBinder(target, true);

        MutablePropertyValues input =
            DataBinderDemo.values("OR-101", "3");
        input.add("role", "ADMIN");

        binder.bind(input);

        assertEquals(
            0, binder.getBindingResult().getErrorCount());
        assertEquals(
            1, binder.getBindingResult().getSuppressedFields().length);
        assertEquals(
            "role",
            binder.getBindingResult().getSuppressedFields()[0]);
        assertEquals(Integer.valueOf(3), target.getQuantity());
    }
}
```

Các test không cần Spring application context, `@SpringBootTest`, `MockMvc` hay H2. Mỗi test khởi tạo target/binder mới, tránh state bị ảnh hưởng bởi test khác.

### 7.7. Chạy và đọc kết quả test

```bash
mvn -q test
```

Nếu chạy thành công, Maven trả **exit code 0**. Với chế độ quiet `-q`, không nên giả định sẽ có một stdout cố định như “6 tests passed”; có thể kiểm tra các báo cáo XML/TXT do Surefire tạo trong `target/surefire-reports`.

Test suite này gồm **6 test methods**:

1. Binding và conversion hợp lệ.
2. Sai kiểu tạo `typeMismatch`.
3. Thiếu required field tạo `required`.
4. Thiếu field không bị xem là lỗi cho tới lúc custom validation chạy.
5. Giá trị số hợp lệ về kiểu nhưng sai rule `minQuantity`.
6. Field ngoài allowlist xuất hiện trong suppressed fields mà không tự tạo binding error.

Các expected values đã được viết rõ trong assertions, thay vì phụ thuộc thứ tự log hoặc text của exception.

## 8. Chiến lược kiểm thử theo lớp

### 8.1. Unit test DataBinder (không web server)

Ưu điểm:

- Nhanh, ít dependency, không cần Spring container.
- Phân biệt conversion, missing, validator và suppress trong một lớp hẹp.
- Dễ kiểm tra `FieldError#getCode()`, `getCodes()`, `getRejectedValue()`, `isBindingFailure()`.
- Dễ tạo fresh binder cho từng case, giảm flaky tests.

Giới hạn: test kiểu này **không chứng minh** Spring MVC đã chọn đúng controller, `@InitBinder` được framework gọi hoặc HTTP status được trả đúng. Nó kiểm tra trực tiếp code bạn thiết lập trên binder trong test.

### 8.2. MVC integration test

Trong một Spring Boot MVC project, dùng `MockMvc` để xác nhận:

- `@InitBinder("orderForm")` thực sự áp dụng cho đúng model attribute.
- `@Valid`/`@Validated` kích hoạt validator phù hợp.
- `BindingResult` đứng ngay sau parameter cần bắt lỗi.
- HTTP body, status và content type đúng API contract.
- Validation/parse failures không ghi dữ liệu.
- Field ngoài allowlist bị từ chối theo policy.

Ví dụ chữ ký controller:

```java
@PostMapping("/orders")
public ResponseEntity<?> submit(
        @Valid @ModelAttribute("orderForm") OrderForm form,
        BindingResult errors) {

    if (errors.getSuppressedFields().length > 0) {
        return ResponseEntity.badRequest().body("EXTRA_FIELDS");
    }
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body("INVALID");
    }
    return ResponseEntity.ok("ACCEPT");
}
```

Đây là **fragment MVC**, cần imports và các lớp/configuration tương ứng. Generic `DataBinder` được tạo trong mục 7 không tự gắn vào controller bằng cách đặt một phương thức tên `newBinder`. Nếu muốn MVC dùng các rules đó, phải cấu hình qua `@InitBinder`/MVC binding infrastructure hoặc validation configuration phù hợp.

Ví dụ `@InitBinder` cần thiết trong MVC:

```java
@InitBinder("orderForm")
void initOrderForm(WebDataBinder binder) {
    binder.setAllowedFields("code", "quantity");
    binder.setRequiredFields("code", "quantity");
    binder.addValidators(orderValidator);
}
```

Fragment này nằm trong controller, với `orderValidator` là Spring-managed bean. Dùng `addValidators` để giữ global validators có sẵn; dùng `setValidator` một cách không chủ đích có thể thay danh sách validation mặc định. Khi `@InitBinder` đã được áp dụng, MVC sẽ thực hiện binding và kích hoạt validation nếu argument annotation yêu cầu.

### 8.3. @RequestBody JSON không cùng binding path

Với:

```java
@PostMapping("/api/orders")
public ResponseEntity<?> submit(
        @Valid @RequestBody OrderRequest body) {
    // ...
    return ResponseEntity.ok().build();
}
```

JSON được giải mã qua HTTP message converters (thường Jackson), không dùng property binding từ `MutablePropertyValues` theo cùng cách như `@ModelAttribute`. Vì vậy:

- `setRequiredFields(...)` của `DataBinder` không phải cơ chế quyết định Jackson có cho phép missing JSON fields.
- `@NotNull`/constructor validation trong DTO và Jackson config mới là điểm cần kiểm thử cho JSON.
- Lỗi JSON parse có thể là `HttpMessageNotReadableException` trước khi Bean Validation chạy.
- `setAllowedFields(...)` không nên được coi là hàng rào duy nhất chống mass assignment qua JSON.

Không lấy một unit test `DataBinder#bind` làm bằng chứng cho endpoint `@RequestBody`.

## 9. Assertions nào đáng tin và assertions nào dễ giòn?

### 9.1. Assert error code thay vì localized default message

Nên:

```java
assertEquals("typeMismatch", error.getCode());
assertEquals("required", missingError.getCode());
```

Hạn chế:

```java
assertEquals(
    "Failed to convert property value of type ...",
    error.getDefaultMessage());
```

Dòng sau là fragment về một kiểu assertion **dễ giòn**, không phải thông báo chính xác bắt buộc của Spring. Wording có thể thay theo Spring version, `MessageSource`/locale hoặc custom binding error processor.

Nếu ứng dụng thực sự có hợp đồng message text, hãy test i18n ở tầng riêng với `MessageSource`/locale xác định.

### 9.2. Assert field, code và count có chủ đích

Một lỗi có thể chứa dãy mã:

```text
typeMismatch.orderForm.quantity
typeMismatch.quantity
typeMismatch.java.lang.Integer
typeMismatch
```

Đó là **ví dụ điển hình** khi target object name là `orderForm` và field type là `Integer`. Nếu bạn cấu hình `MessageCodesResolver` khác, dãy có thể khác. `FieldError#getCode()` thường trả mã tổng quát cuối cùng.

Trong unit test không phụ thuộc quy ước mã chi tiết, assert code chung và field name. Trong i18n-specific tests, test toàn bộ `getCodes()` khi đó chính là contract cần bảo vệ.

### 9.3. Không phụ thuộc thứ tự lỗi

Nếu form có nhiều lỗi, dùng `getFieldErrors()` rồi nhóm/sắp xếp trước khi so sánh. Đừng dựa vào việc validator khác nhau sẽ luôn ghi lỗi theo đúng thứ tự mà người phát triển tưởng tượng.

Ví dụ:

```java
List<String> codes = result.getFieldErrors().stream()
    .map(e -> e.getField() + ":" + e.getCode())
    .sorted()
    .toList();
```

Đây là fragment, cần import `List` và đối tượng `result` đã có. Với tests chỉ kiểm tra một field, `getFieldError("quantity")` đơn giản và rõ ý hơn.

### 9.4. Assert không có side effect khi lỗi

Trong MVC integration, ngoài HTTP 400 hoặc validation error, phải kiểm tra database/service không nhận lệnh ghi nếu binder có lỗi hoặc suppressed fields. Một hệ thống có thể trả lỗi đúng nhưng đã mutate managed JPA entity trước khi kiểm tra `BindingResult` — đây là lý do nên bind vào DTO, không vào domain entity trực tiếp.

## 10. Các tình huống biên mở rộng

### 10.1. Gửi key có giá trị null thay vì bỏ key

Trong generic `MutablePropertyValues`, có thể đưa property tồn tại với value Java `null`:

```java
MutablePropertyValues pvs = new MutablePropertyValues();
pvs.add("code", "OR-101");
pvs.add("quantity", null);
```

Case này **khác** việc không có key `quantity`. Tùy quy tắc `requiredFields` và binding processor, kết quả có thể được xem là missing hoặc chuyển/gán null. Để biết contract đúng cho app, hãy thêm test tách biệt và không suy đoán từ chữ `null` trong target.

### 10.2. Chuỗi rỗng và whitespace

Với `quantity=""` hoặc `quantity="  "`, conversion service/property editor có thể chuyển sang null hoặc phát lỗi tùy target type và cấu hình. Vì vậy cần test riêng:

```java
pvs.add("quantity", "");
pvs.add("quantity", "  ");
```

Hai dòng ở trên thể hiện **hai case thay thế**, không nên add cả hai property vào cùng `MutablePropertyValues` nếu mục tiêu là test độc lập. Khi dùng Spring MVC, `StringTrimmerEditor`, formatters hoặc custom converters có thể thay đổi kết quả; chuẩn hóa cần có policy rõ.

### 10.3. Unknown fields và ignoreUnknownFields

Mặc định binder có thể bỏ qua property không tồn tại khi `ignoreUnknownFields=true`. Nếu muốn phát hiện input lạ, cần chọn chiến lược:

- Dùng `setAllowedFields(...)` để loại và kiểm tra `getSuppressedFields()`.
- Cân nhắc `setIgnoreUnknownFields(false)` khi contract cần chặn unknown property; hành vi exception khác với suppressed fields nên cần test tách biệt.
- Thiết kế request DTO tối thiểu, không có các setters nhạy cảm.

**Không đồng nhất** “unknown property” với “known property nhưng không được phép gán”: hai trường hợp có thể đi qua đường lỗi khác.

### 10.4. Primitive vs wrapper

Nếu `quantity` là `int`, target mới có giá trị mặc định 0. Với `Integer`, target chưa bind có thể giữ null. Khi test missing fields, phải biết chính xác target đã được khởi tạo thế nào, không kết luận chỉ từ một số `0` trong kết quả.

### 10.5. Nested properties và collection

Một form có `address.zipCode` hoặc `items[0].quantity` cần chuẩn bị nested object hoặc xem xét `autoGrowNestedPaths`, collection limits, allowedFields và error field paths. Khi test:

- Case nested target chưa được tạo.
- Case collection index không hợp lệ/quá lớn.
- Case custom converter sai kiểu tại nested field.
- Case field ngoài allowlist ở đường dẫn lồng nhau.

Các đường nested có thể làm tăng bề mặt mass assignment; không cho bind toàn bộ object graph tùy ý.

### 10.6. Declarative/constructor binding

Spring Framework 6.1+ hỗ trợ `DataBinder#setDeclarativeBinding(true)`, khiến property binding chỉ chạy khi có allowed fields tường minh; constructor binding vẫn có quy tắc riêng. Tests dùng `bind(PropertyValues)` lên JavaBean với setters **không trực tiếp kiểm thử** `construct(ValueResolver)` của immutable DTO.

Với Java record/input constructor có các tham số, hãy viết test cho constructor binding riêng, không chỉ đổi `OrderForm` thành record rồi giữ nguyên `binder.bind(...)`. Một binder được tạo với target `null` và target type cần `setTargetType(...)`, `construct(...)` theo API Spring 6.1+.

### 10.7. Kiểm thử converter/formatter tùy chỉnh

Nếu có `Converter<String, OrderId>` hoặc `Formatter<LocalDate>` custom, cấu hình `ConversionService`/formatter cho binder trong test để tái lập cách MVC parse. Test các giá trị hợp lệ, sai định dạng, giới hạn, locale và null handling. Không mặc nhiên cho rằng generic binder dùng mọi custom converter do Spring Boot autoconfigure ở một MVC ApplicationContext khác.

## 11. Lỗi thường gặp khi kiểm thử

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `quantity=abc` ném exception ngoài test thay vì ghi lỗi | Test dùng converter trực tiếp hoặc binding config custom | Gọi `binder.bind(...)` và kiểm tra `BindingResult`; phân biệt conversion thuần |
| Thiếu quantity nhưng không có lỗi | Không cấu hình `setRequiredFields` và chưa validate | Test missing riêng, thêm `requiredFields` hoặc validator |
| Giá trị 0 không bị từ chối | Conversion thành công, chưa gọi `validate()` | Gắn `Validator` và gọi `validate()` |
| Test `@NotNull` không chạy với generic binder | Chưa cài Bean Validation provider/validator | Tạo `LocalValidatorFactoryBean`/khởi tạo provider và gọi validate |
| Có cả `typeMismatch` và `requiredByValidator` | Validator chạy trên field đã lỗi conversion | Kiểm tra `errors.hasFieldErrors(field)` nếu policy cần tránh trùng |
| Form primitive int có 0 dù không gửi | Primitive default value | Dùng `Integer` nếu cần biểu diễn missing |
| `getFieldError(...)` trả null nhưng test dereference | Field không có lỗi hoặc binder config không khớp | `assertNotNull` trước khi kiểm tra code |
| Test compare thông báo tiếng Anh bị fail theo locale | Dùng `getDefaultMessage()` làm contract | Test code; kiểm tra i18n ở tầng riêng |
| Thêm role field nhưng `hasErrors()` vẫn false | Suppressed fields không tự là FieldError | Kiểm tra `getSuppressedFields()` |
| @InitBinder không có tác dụng trong test thuần | Generic `DataBinder` không tự gọi controller annotations | Dùng MockMvc integration test |
| JSON endpoint có hành vi khác form test | Jackson decoder khác property binder | Test riêng @RequestBody/Jackson |
| Dùng lại MutablePropertyValues giữa tests | Binder có thể lọc/sửa danh sách values | Tạo fresh instance cho mỗi lần bind |
| Test order errors thay đổi theo implementation | Phụ thuộc thứ tự tạo FieldErrors | Sort hoặc assert theo field |
| Gọi validate() nhiều lần sinh lỗi trùng | Validator không idempotent hoặc được chạy lặp | Xác định số lần validate, tạo binder mới mỗi test |
| Bind trực tiếp vào entity rồi mới kiểm tra lỗi | State có thể đã thay đổi trước khi kiểm tra | Dùng DTO và chặn lưu/flush khi lỗi |

## 12. Checklist kiểm tra trước khi kết luận test đạt

1. Có JavaBean target với getters/setters hoặc chế độ binding được cấu hình rõ.
2. Mỗi case tạo target và DataBinder mới; không dùng chung mutable state.
3. Input `MutablePropertyValues` được tạo mới cho từng lần bind.
4. Với successful conversion, assert **target value và type**, không chỉ `hasErrors() == false`.
5. Với invalid type, assert field, code `typeMismatch` và `isBindingFailure()`.
6. Với missing required, assert binder được cấu hình `setRequiredFields` **trước** `bind()`.
7. Có test missing **không** required để hiểu khác biệt.
8. Với semantic violation, assert lỗi chỉ xuất hiện sau khi gọi `validate()`.
9. Kiểm tra không tiếp tục nghiệp vụ khi lỗi binding/validation.
10. Kiểm tra `getSuppressedFields()` và không xem `hasErrors()==false` là chấp nhận mọi input.
11. Với MVC integration, kiểm tra `@InitBinder` scope, `@ModelAttribute` name, `BindingResult` placement và status.
12. Với `@RequestBody` JSON, test decode/constraints riêng; không dựa vào `MutablePropertyValues`.
13. Không serialize `FieldError#getRejectedValue()` vào public HTTP response.
14. Không assert lời nhắn lỗi localized trong unit test core binder nếu mục tiêu chỉ là error code.
15. Chạy Maven test suite với exit code 0; khi cần rà soát kết quả chi tiết, xem `target/surefire-reports`.

## 13. Tổng kết

**`DataBinder#bind(...)`** xử lý binding/conversion và có thể ghi `typeMismatch` hoặc `required` vào `BindingResult`. **`setRequiredFields(...)`** quyết định field nào phải xuất hiện khi property binding, còn **`DataBinder#validate()`** là bước riêng để áp dụng những Spring `Validator` đã đăng ký.

Một bộ kiểm thử tốt không gộp mọi lỗi thành “invalid input”, mà tách ít nhất: **giá trị đúng**, **sai kiểu**, **thiếu required field**, **missing nhưng chưa có rule**, **đúng kiểu nhưng sai validation**, và **field ngoài allowlist**. Java 17/JUnit 5 sample ở mục 7 tạo binder mới cho mỗi case, assert mã lỗi bền vững và không phụ thuộc HTTP/web server.

Khi mở rộng sang Spring MVC, nhớ kiểm tra hạ tầng `@InitBinder`/`@Valid`/`BindingResult` và HTTP response qua MockMvc. Đừng dùng unit test binder làm thay thế mọi integration/security test.

## Tài liệu tham khảo chính thức

- Spring Framework 6.2 — Validation, Data Binding and Type Conversion: https://docs.spring.io/spring-framework/reference/6.2/core/validation.html
- Spring Framework 6.2 — Data Binding, constructor vs property binding: https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html
- Spring Framework 6.2 — Configuring DataBinder and Validator: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 Javadoc — `DataBinder`, `setRequiredFields`, `bind`, `validate`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.2 Javadoc — `BindingResult`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/BindingResult.html
- Spring Framework 6.2 Javadoc — `FieldError`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/FieldError.html
- Spring Framework 6.2 Javadoc — `DefaultBindingErrorProcessor`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/DefaultBindingErrorProcessor.html
- Spring Framework 6.2 — `@InitBinder` in MVC: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework 6.2 — `@ModelAttribute` and security: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/