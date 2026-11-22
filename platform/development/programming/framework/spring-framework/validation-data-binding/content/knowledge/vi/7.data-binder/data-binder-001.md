# Khởi tạo `DataBinder` với `target` và `objectName` trong Spring Framework

## 1. Mục tiêu của bài học

`org.springframework.validation.DataBinder` là thành phần cốt lõi trong cơ chế **data binding** của Spring: nhận các giá trị đầu vào được biểu diễn theo tên thuộc tính, chuyển đổi kiểu khi cần và gán lên một đối tượng đích. Đối tượng đích được gọi là **`target`**; tên logic dùng để định danh đối tượng trong kết quả binding được gọi là **`objectName`**.

Ví dụ một form đăng ký có các trường `name` và `age`. Spring có thể nhận hai giá trị chuỗi `"Mai"` và `"23"` rồi gán vào một JavaBean với thuộc tính `String name` và `int age`. Bước khởi tạo binder xác định **gán vào đối tượng nào** và **gọi đối tượng đó là gì khi ghi nhận kết quả/lỗi**.

Sau bài này, bạn có thể:

- Phân biệt chính xác hai constructor `new DataBinder(target)` và `new DataBinder(target, objectName)`.
- Chọn `target` phù hợp và hiểu đối tượng đã tồn tại được cập nhật như thế nào.
- Giải thích cách `objectName` xuất hiện trong `BindingResult`, field errors và khóa model.
- Thực hiện trọn vẹn quy trình khởi tạo → cấu hình → bind → đọc kết quả.
- Nhận biết trường hợp đặc biệt `target == null` và lý do không thể dùng nó như một JavaBean sẵn có.
- Tránh các lỗi bảo mật do bind trực tiếp dữ liệu không tin cậy lên đối tượng chứa trường nhạy cảm.

## 2. Hai constructor và ý nghĩa tham số

Hai cách khởi tạo phổ biến trong Spring Framework 6.x:

```java
DataBinder binder1 = new DataBinder(target);
DataBinder binder2 = new DataBinder(target, "registrationForm");
```

Chữ ký về mặt API:

```java
public DataBinder(@Nullable Object target)
public DataBinder(@Nullable Object target, String objectName)
```

| Tham số | Vai trò | Khi nào chọn |
| --- | --- | --- |
| `target` | Đối tượng được binder thao tác, thường là JavaBean/DTO đã tạo. `getTarget()` trả về đối tượng mà binder đang bao bọc. | Khi đã có instance cần nhận giá trị từ map/property values. |
| `objectName` | Tên logic để `BindingResult` và các cơ chế báo lỗi nhận diện đối tượng. `getObjectName()` trả về tên này. | Khi muốn tên có ý nghĩa như `"registrationForm"` hay `"searchCriteria"`. |
| Bỏ `objectName` | Spring dùng `DataBinder.DEFAULT_OBJECT_NAME`, có giá trị `"target"`. | Demo đơn giản hoặc khi không cần tên cụ thể. |

**`objectName` không phải** tên class Java, tên biến, bean ID trong Spring container, URL route hay tên bảng database. Nó cũng **không tự quyết định đối tượng được tạo**. Phần quyết định đối tượng chịu tác động là `target`.

Ví dụ:

```java
RegistrationForm form = new RegistrationForm();
DataBinder binder = new DataBinder(form, "registrationForm");
```

Trong ví dụ này:

- `form` là đối tượng thật, có các field và getter/setter.
- `"registrationForm"` là tên logic được binder dùng khi báo kết quả.
- `new DataBinder(...)` **chỉ khởi tạo binder**; chưa đọc HTTP request, chưa gán thuộc tính và chưa tự chạy validation.
- Sau khi gọi `bind(...)`, binder cập nhật **cùng instance `form`** nếu các property hợp lệ và có thể ghi.

## 3. Cách chọn `target`

### 3.1. Đối tượng đã được khởi tạo

Một trường hợp thông dụng là truyền instance DTO kiểu JavaBean:

```java
public class RegistrationForm {
    private String name;
    private int age;

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public int getAge() { return age; }
    public void setAge(int age) { this.age = age; }
}
```

Tạo binder:

```java
RegistrationForm form = new RegistrationForm();
DataBinder binder = new DataBinder(form, "registrationForm");
```

`DataBinder` mặc định dùng **JavaBeans property access** (getters/setters và property descriptors) khi property binding. Vì vậy, đối tượng nên có property ghi được theo quy tắc JavaBeans. Field `private` mà không có setter thích hợp **không tự được ghi trực tiếp** trong chế độ mặc định.

Nếu đã có giá trị khởi tạo, chỉ những property được bind thành công mới thay đổi giá trị tương ứng. Điều đó có thể hữu ích cho default; tuy nhiên binding trên một instance đã có trạng thái cũng có nguy cơ ghi đè dữ liệu cũ, nên cần chủ động chọn các field được phép.

### 3.2. Điều gì xảy ra nếu `target` là `null`?

Javadoc của `DataBinder` cho phép `target` là `null`. Nhưng điều đó **không có nghĩa** `binder.bind(propertyValues)` sẽ tự biết phải tạo JavaBean loại nào.

Hai mục đích đặc biệt:

1. Binder chỉ dùng để **chuyển đổi một giá trị đơn** thông qua cơ chế chuyển kiểu, thay vì gán thuộc tính lên JavaBean.
2. Từ Spring Framework **6.1**, có thể bắt đầu với `target == null`, khai báo kiểu đích bằng `setTargetType(ResolvableType)`, rồi gọi `construct(ValueResolver)` để tạo đối tượng theo constructor binding. Khi tạo thành công, `getTarget()` mới chứa instance đã tạo.

Sơ đồ của trường hợp constructor binding (mô tả API, không phải ví dụ đầy đủ):

```text
new DataBinder(null, "registrationForm")
               |
               v
setTargetType(ResolvableType.forClass(RegistrationForm.class))
               |
               v
construct(valueResolver cung cấp giá trị theo tên tham số)
               |
               v
getBindingResult() kiểm tra lỗi / getTarget() lấy instance được tạo
```

Đường đi này khác với kiểu **property binding vào một đối tượng đã có**. Bài này tập trung vào việc khởi tạo binder cho instance sẵn có; constructor binding là khả năng bổ sung cần biết để không kết luận sai rằng mọi `null target` đều bất hợp lệ.

Không truyền `RegistrationForm.class` làm `target` rồi kỳ vọng binder tạo `RegistrationForm`: đối số đó là một đối tượng `Class<?>`, không phải form instance mong muốn.

## 4. Cách chọn `objectName` và ảnh hưởng đến lỗi

`objectName` là **tên của đối tượng được bind**, không phải đường dẫn thuộc tính.

```java
DataBinder binder = new DataBinder(form, "registrationForm");
```

Nếu input là hai key `name` và `age`, bạn vẫn truyền key đúng tên property:

```java
MutablePropertyValues values = new MutablePropertyValues();
values.add("name", "Mai");
values.add("age", "23");
binder.bind(values);
```

Không đổi thành `"registrationForm.name"` chỉ vì `objectName` là `"registrationForm"`. Binder sẽ hiểu một chuỗi có dấu chấm là **property path lồng nhau**; nếu `RegistrationForm` không có property `registrationForm`, binding không hoạt động như mong đợi.

`objectName` ảnh hưởng trực tiếp đến:

- `binder.getObjectName()`.
- `binder.getBindingResult().getObjectName()`.
- `ObjectError.getObjectName()` và `FieldError.getObjectName()`.
- Khóa model dùng để hiển thị đối tượng và lỗi, theo dạng `objectName` và `BindingResult.MODEL_KEY_PREFIX + objectName` (tiền tố thường là `"org.springframework.validation.BindingResult."`).
- Phần tên đối tượng trong các mã thông báo lỗi có ngữ cảnh, chẳng hạn mã cho `typeMismatch` có thể bao gồm tên form và field.

Ví dụ ý nghĩa khi hiển thị kết quả:

| Binder | `getObjectName()` | Khóa kết quả lỗi trong model |
| --- | --- | --- |
| `new DataBinder(form)` | `target` | `org.springframework.validation.BindingResult.target` |
| `new DataBinder(form, "registrationForm")` | `registrationForm` | `org.springframework.validation.BindingResult.registrationForm` |
| `new DataBinder(form, "profileEdit")` | `profileEdit` | `org.springframework.validation.BindingResult.profileEdit` |

Dùng tên có ý nghĩa giúp phân biệt nhiều form trong một màn hình. Một `objectName` cố định, dễ hiểu cũng thuận tiện khi dùng thông báo lỗi và kiểm thử. Không nên tạo tên ngẫu nhiên hoặc dùng dữ liệu nhạy cảm làm `objectName`.

## 5. Quy trình chuẩn: khởi tạo → cấu hình → bind → kiểm tra

```text
1. Tạo target: new RegistrationForm()
2. Tạo binder: new DataBinder(target, "registrationForm")
3. Thiết lập conversion / allowed fields / validator (nếu cần)
4. Chuẩn bị PropertyValues: {name: "Mai", age: "23"}
5. binder.bind(propertyValues)
6. BindingResult result = binder.getBindingResult()
7. result.hasErrors() / result.getFieldErrors() / result.getSuppressedFields()
8. Nếu hợp lệ, sử dụng target đã được gán giá trị
```

Điểm quan trọng là mỗi bước giải quyết một công việc riêng:

- **Constructor** gắn binder với target và objectName.
- **Cấu hình** xác định các property được bind, kiểu chuyển đổi và cách xác thực.
- **`bind(PropertyValues)`** thực hiện ánh xạ/convert/gán dữ liệu, có thể tạo lỗi binding.
- **`getBindingResult()`** trả về nơi tích lũy kết quả và lỗi.
- **`validate()`**, nếu bạn đã cấu hình validator và muốn gọi, là bước khác với `bind()`. Khởi tạo binder bằng constructor không tự chạy validator.

`DataBinder` không phải kho lưu trữ trạng thái nghiệp vụ. Nó chỉ giúp đi từ dữ liệu đầu vào đến đối tượng, nên sau binding và validation ứng dụng vẫn cần kiểm tra business rules tại service/domain.

## 6. Ví dụ đầy đủ có thể chạy: khởi tạo, bind, kiểm tra tên và target

Ví dụ dưới đây dùng **Java 17** và **Spring Framework 6.2.6**, không yêu cầu servlet container hay Spring Boot: chỉ cần dependency `spring-context` (và các transitive dependencies). Tạo cấu trúc:

```text
data-binder-demo/
  pom.xml
  src/main/java/demo/DataBinderInitDemo.java
```

**`pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>data-binder-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/DataBinderInitDemo.java`:**

```java
package demo;

import java.util.Arrays;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public class DataBinderInitDemo {

    // JavaBean làm target; các setter được dùng cho property binding.
    public static class RegistrationForm {
        private String name;
        private int age;
        private String role = "USER";

        public String getName() { return name; }
        public void setName(String name) { this.name = name; }

        public int getAge() { return age; }
        public void setAge(int age) { this.age = age; }

        public String getRole() { return role; }
        public void setRole(String role) { this.role = role; }
    }

    public static void main(String[] args) {
        RegistrationForm form = new RegistrationForm();

        // (1) Cung cấp CHÍNH instance nhận dữ liệu và tên logic.
        DataBinder binder = new DataBinder(form, "registrationForm");

        // (2) Chỉ cho bind hai thuộc tính do form công khai.
        binder.setAllowedFields("name", "age");

        // (3) Giá trị nguồn là chuỗi, age cần chuyển sang int.
        MutablePropertyValues input = new MutablePropertyValues();
        input.add("name", "Mai");
        input.add("age", "23");
        input.add("role", "ADMIN");  // Không được phép gán qua binder.

        // (4) Bind cập nhật instance form đã cung cấp.
        binder.bind(input);

        // (5) Đọc kết quả; tên object được giữ xuyên suốt.
        BindingResult result = binder.getBindingResult();
        System.out.println("sameTarget=" + (binder.getTarget() == form));
        System.out.println("objectName=" + binder.getObjectName());
        System.out.println("resultName=" + result.getObjectName());
        System.out.println("name=" + form.getName());
        System.out.println("age=" + form.getAge());
        System.out.println("role=" + form.getRole());
        System.out.println("errors=" + result.getErrorCount());
        System.out.println("suppressed="
                + Arrays.toString(result.getSuppressedFields()));

        // (6) Constructor một đối số sử dụng objectName mặc định.
        DataBinder defaultBinder = new DataBinder(new RegistrationForm());
        System.out.println("defaultName=" + defaultBinder.getObjectName());

        // (7) Đầu vào sai kiểu được ghi thành field error.
        DataBinder badBinder =
                new DataBinder(new RegistrationForm(), "registrationForm");
        badBinder.setAllowedFields("age");

        MutablePropertyValues badInput = new MutablePropertyValues();
        badInput.add("age", "not-a-number");
        badBinder.bind(badInput);

        System.out.println("ageTypeError="
                + badBinder.getBindingResult().hasFieldErrors("age"));
    }
}
```

Trong thư mục `data-binder-demo`, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.DataBinderInitDemo
```

**Stdout mong đợi** (không tính log của Maven khi cấu hình khác `-q`):

```text
sameTarget=true
objectName=registrationForm
resultName=registrationForm
name=Mai
age=23
role=USER
errors=0
suppressed=[role]
defaultName=target
ageTypeError=true
```

Đọc kết quả:

1. `sameTarget=true` xác nhận constructor giữ **đúng cùng instance**; `bind()` không tạo `RegistrationForm` mới.
2. `objectName` và `resultName` giống nhau: tên logic đi vào `BindingResult`.
3. Chuỗi `"23"` được chuyển sang `int` khi bind; `name` được gán trực tiếp.
4. Client thử gửi `role=ADMIN` nhưng `setAllowedFields` loại key đó ra; target vẫn giữ `role=USER`. `getSuppressedFields()` cho biết field đã bị chặn.
5. Constructor một tham số tự chọn `"target"` làm tên.
6. Khi `age` có chuỗi không chuyển được thành số, binder ghi lỗi vào `BindingResult`; không nên tiếp tục use case như thể đối tượng đã nhận dữ liệu đầy đủ.

Với mã này, **không cần gọi `validate()` để có lỗi chuyển kiểu**: lỗi conversion được ghi trong quá trình `bind()`. Ngược lại, những ràng buộc nghiệp vụ hoặc Jakarta Bean Validation không tự chạy khi chỉ gọi `bind()`.

## 7. `BindingResult` sử dụng `objectName` như thế nào?

Khi tạo binder:

```java
DataBinder binder = new DataBinder(form, "registrationForm");
BindingResult result = binder.getBindingResult();
```

Ta có thể kiểm tra các thông tin:

```java
String objectName = result.getObjectName();
Object target = result.getTarget();
boolean hasErrors = result.hasErrors();
```

Khi một giá trị không chuyển được, Spring lưu một `FieldError`. Thông tin hữu ích gồm:

- `fieldError.getObjectName()`: tên logic form, ví dụ `"registrationForm"`.
- `fieldError.getField()`: tên property bị lỗi, ví dụ `"age"`.
- `fieldError.getRejectedValue()`: dữ liệu đã bị từ chối, ví dụ `"not-a-number"` (cần xử lý an toàn nếu chứa dữ liệu nhạy cảm).
- `fieldError.getCode()` và `getCodes()`: mã/mã dự phòng phục vụ ánh xạ thông báo lỗi hoặc i18n.

Với tên custom, khi dùng `result.getModel()`, mô hình kết quả có thể chứa một entry của object dưới key `"registrationForm"` và một entry của `BindingResult` dưới key `"org.springframework.validation.BindingResult.registrationForm"`. Chính cơ chế đặt tên này giúp view hiển thị đúng lỗi của đúng form.

**Không nhầm `objectName` với `field`**:

| Thuộc tính | Ví dụ | Diễn giải |
| --- | --- | --- |
| Object name | `registrationForm` | Đối tượng/form nào được xử lý |
| Field name | `age` | Property nào trong đối tượng |
| Rejected value | `not-a-number` | Giá trị đầu vào không phù hợp |
| Error code | `typeMismatch` | Loại thất bại của bước binding |

Nếu gọi `new DataBinder(form, "profileForm")` rồi bind key `"age"`, tên property vẫn là `"age"`. Việc đổi objectName **không thay đổi đường đi đến field và cũng không thay đổi class target**.

## 8. Sử dụng với Spring MVC: không nhất thiết tự gọi constructor

Khi xử lý request có `@ModelAttribute`, Spring MVC thường **tạo và cấu hình một `WebDataBinder`** thông qua hạ tầng argument resolution. `WebDataBinder` kế thừa `DataBinder` và bổ sung đặc điểm phù hợp với môi trường web.

Ví dụ minh họa trong một controller Spring MVC (phụ thuộc controller và form class của ứng dụng):

```java
@Controller
class RegistrationController {

    @InitBinder("registrationForm")
    void configureBinder(WebDataBinder binder) {
        binder.setAllowedFields("name", "age");
    }

    @PostMapping("/registration")
    String submit(
            @Valid @ModelAttribute("registrationForm") RegistrationForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "registration-form";
        }
        return "registration-success";
    }
}
```

Các import tương ứng là `org.springframework.stereotype.Controller`, `org.springframework.web.bind.annotation.InitBinder`, `org.springframework.web.bind.annotation.PostMapping`, `org.springframework.web.bind.annotation.ModelAttribute`, `org.springframework.web.bind.WebDataBinder`, `org.springframework.validation.BindingResult` và `jakarta.validation.Valid`. Đoạn controller cần view và môi trường Spring MVC để chạy; **không phải chương trình Java độc lập**.

Trong ví dụ:

- `@ModelAttribute("registrationForm")` đặt tên cho model attribute mà Spring MVC xử lý.
- `@InitBinder("registrationForm")` cấu hình binder gắn với tên đó; ta điều chỉnh binder mà Spring MVC cung cấp.
- `BindingResult` đặt ngay sau tham số `@ModelAttribute` nhận lỗi binding/validation của chính attribute ấy.
- `@Valid` kích hoạt validation khi có provider và cấu hình tương ứng. Nếu không cần validation, binding vẫn là một bước riêng.

**Không nên tự tạo `new DataBinder(...)` trong controller rồi cho rằng binder đó tự thay thế binder mà Spring MVC đang dùng.** Tạo thủ công thích hợp cho code xử lý dữ liệu ngoài MVC, thử nghiệm hoặc các trường hợp custom binding thực sự cần thiết. Trong controller MVC, ưu tiên `@InitBinder` và cơ chế framework có sẵn.

## 9. Cấu hình binder sau khi khởi tạo

Constructor chỉ xác định target và objectName; cấu hình cụ thể thường được đặt **trước `bind()`**.

| API | Mục đích |
| --- | --- |
| `setAllowedFields("name", "age")` | Chỉ bind các property được liệt kê, đặc biệt có ích khi dữ liệu đến từ người dùng |
| `setDisallowedFields(...)` | Loại các field cụ thể; dùng danh sách cho phép thường an toàn và rõ ràng hơn |
| `setRequiredFields("name")` | Yêu cầu có một số field trong quá trình binding; semantics khác `@NotBlank` |
| `setConversionService(...)` | Dùng conversion service cho chuyển kiểu |
| `addCustomFormatter(...)` / `registerCustomEditor(...)` | Hỗ trợ kiểu dữ liệu hoặc định dạng cần chuyển riêng |
| `setValidator(...)` và `validate()` | Thiết lập rồi chạy validation; không tự được thực thi bởi constructor |
| `initDirectFieldAccess()` | Chuyển sang chế độ truy cập field trực tiếp nếu thực sự cần, thay cho cơ chế JavaBeans property mặc định |

**Chú ý về thứ tự:** trước hết tạo `target` và binder, kế đến thiết lập các lựa chọn an toàn, rồi mới gọi `bind`. Nếu cấu hình `allowedFields` *sau* khi bind, dữ liệu đã có thể được gán trước khi chính sách được áp dụng.

Với target là DTO cập nhật hồ sơ, không nên đưa toàn bộ entity chứa `role`, `ownerId`, `balance` hoặc `approvalStatus` làm binder target khi nhận dữ liệu không tin cậy. Việc giới hạn field là phòng vệ bổ sung; tốt nhất thiết kế DTO chỉ có những thuộc tính thực sự được phép sửa.

## 10. So sánh những cách khởi tạo phổ biến

| Cách viết | Đặc điểm | Trường hợp phù hợp |
| --- | --- | --- |
| `new DataBinder(form)` | Target sẵn có; tên mặc định `"target"` | Demo đơn giản, tiện ích không cần định danh riêng |
| `new DataBinder(form, "registrationForm")` | Target sẵn có; tên logic rõ ràng | Form/DTO có binding result và thông báo lỗi dễ nhận diện |
| `new DataBinder(null, "rawValue")` | Không có target JavaBean sẵn có | Trường hợp chỉ cần chuyển đổi giá trị; không gọi property binding như thể có target |
| `new DataBinder(null, "registrationForm")` + `setTargetType(...)` + `construct(...)` | Dùng constructor binding tạo target; khả năng từ Spring 6.1 | Input immutable/constructor-based có ValueResolver phù hợp |
| `@ModelAttribute("registrationForm")` trong MVC | MVC quản lý binder và lifecycle | Phần lớn controller nhận form/query parameters |

`DataBinder` **không phải singleton service** nên không nên tái sử dụng một binder mutable giữa nhiều request. Tạo binder gắn với đối tượng và phạm vi xử lý cụ thể, tránh chia sẻ target mutable giữa các luồng không được đồng bộ.

## 11. Những nhầm lẫn cần tránh

### 11.1. Nhầm `target` với một class

**Sai ý định:**

```java
DataBinder binder = new DataBinder(RegistrationForm.class, "registrationForm");
```

Câu trên đưa `Class<RegistrationForm>` làm target, không tạo form. Với property binding hãy viết:

```java
RegistrationForm form = new RegistrationForm();
DataBinder binder = new DataBinder(form, "registrationForm");
```

Nếu muốn constructor binding theo API mới, cần `null target`, `setTargetType`, `ValueResolver` và `construct` theo contract của phiên bản Spring đang dùng.

### 11.2. Cho rằng `objectName` phải khớp tên class

`objectName = "registrationForm"` hợp lệ dù target là `RegistrationForm`, `SignupDto` hoặc một type phù hợp khác. Tên phải rõ nghĩa cho consumers của lỗi/model; **không bị ép bằng tên class**.

### 11.3. Cho rằng khởi tạo binder tự chạy binding

Tạo `new DataBinder(form, "registrationForm")` không sửa dữ liệu. Chỉ `bind(propertyValues)` hoặc constructor-binding API tương ứng mới thực hiện việc nhận giá trị. Cần kiểm tra `BindingResult` sau bước đó.

### 11.4. Cho rằng `objectName` là prefix khi gửi input

Nếu form có property `name`, input key là `"name"`. Đổi key thành `"registrationForm.name"` không tự làm Spring hiểu đó là cùng property; cú pháp dấu chấm ám chỉ nested property path.

### 11.5. Bỏ qua `BindingResult`

Binder có thể ghi field error khi chuyển kiểu thất bại. Nếu tiếp tục xử lý đối tượng không hoàn chỉnh, hệ thống dễ lưu trạng thái sai hoặc ném exception ở tầng sau. Sau binding, kiểm tra lỗi và trường bị từ chối.

### 11.6. Bind mọi field từ người dùng

Nếu class có setter cho `role` hoặc `admin`, binder có khả năng gán nếu không có giới hạn thích hợp. Dùng DTO và `setAllowedFields`/điều khiển field; không xem constructor là hàng rào bảo mật.

### 11.7. Nhầm `bind` và `validate`

`bind` làm conversion/property assignment; `validate` gọi validator đã cấu hình. `@Valid` trong MVC có thể khiến framework chạy validation, nhưng với `new DataBinder(...)` dùng thủ công, bạn phải tự quyết định việc cấu hình/gọi validation.

### 11.8. Phụ thuộc vào tên mặc định khi model có nhiều form

Tên mặc định `"target"` dùng được nhưng thiếu ngữ nghĩa. Nếu có nhiều kết quả binding trong một view, dùng objectName rõ ràng để dễ tránh nhầm các key kết quả.

## 12. Câu hỏi tự kiểm tra

**1. `new DataBinder(form, "signup")` có tạo `form` mới không?** Không. Nó bao bọc instance đã có. `getTarget() == form` là phép kiểm tra cùng tham chiếu.

**2. `getObjectName()` trả gì với `new DataBinder(form)`?** `"target"`, theo `DataBinder.DEFAULT_OBJECT_NAME`.

**3. Nếu objectName là `"signup"`, phải bind key `"signup.email"` hay `"email"`?** Thường là `"email"` nếu target có property `email`; objectName chỉ định danh đối tượng.

**4. Binder có tự gán giá trị sau constructor không?** Không. Với property binding phải gọi `bind(...)`; với constructor binding, phải thiết lập type và gọi `construct(...)` theo API tương ứng.

**5. Một form có `age:int` và nhận chuỗi `"abc"` thì kiểm tra ở đâu?** Sau `bind(...)`, kiểm tra `binder.getBindingResult()`, đặc biệt field error cho `age`.

**6. `objectName` có ảnh hưởng thông báo lỗi không?** Có; nó xuất hiện trong đối tượng lỗi, model key và có thể trong message codes. Nó không làm thay đổi giá trị field hay class của target.

**7. Có nên tạo một binder dùng chung cho tất cả request không?** Không nên. Binder và target có trạng thái mutable gắn với lần binding; tạo theo phạm vi sử dụng.

**8. Khi nào `target = null` hợp lệ?** Khi không cần bean target hoặc dùng cơ chế constructor binding được API phiên bản Spring hỗ trợ; không coi `null` là một JavaBean có sẵn để property binding.

## 13. Checklist áp dụng vào dự án

1. Xác định chính xác **instance hoặc type** cần bind và cơ chế muốn dùng (property binding hay constructor binding).
2. Với property binding, khởi tạo DTO trước; tạo `new DataBinder(dto, "meaningfulName")`.
3. Đặt `objectName` ổn định và dễ hiểu, nhất quán với attribute/BindingResult trong nơi sử dụng.
4. Cấu hình allowed fields, conversion và validator **trước** thao tác bind.
5. Bind các key theo property path của target; đừng tự thêm objectName vào key.
6. Đọc `BindingResult`, xử lý conversion/binding errors và suppressed fields; chạy validation khi cần.
7. Chỉ đưa đối tượng đã được kiểm tra đến use case. Business rules và các ràng buộc lưu trữ vẫn phải được kiểm tra ở những tầng tương ứng.

**Ghi nhớ:** `target` trả lời câu hỏi **“ghi vào đối tượng nào?”**; `objectName` trả lời **“gọi đối tượng đó là gì khi báo kết quả/lỗi?”**. Constructor chỉ thiết lập bối cảnh; thao tác binding và kiểm tra lỗi xảy ra sau đó.

## Nguồn tham khảo chính thức

- [Spring Framework 6.2.6 – `DataBinder` Javadoc](https://www.springframework.org/spring/docs/6.2.6/javadoc-api/org/springframework/validation/DataBinder.html): hai constructor, `DEFAULT_OBJECT_NAME`, `getTarget`, `getObjectName`, `bind` và `BindingResult`.
- [Spring Framework Reference – Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): property binding, constructor binding, JavaBeans, conversion và đặc điểm của `target == null`.
