# getSuppressedFields và theo dõi trường bị loại bỏ trong Spring DataBinder

## 1. Tại sao phải theo dõi trường bị chặn khi binding?

Giả sử một endpoint cho người dùng tự sửa hồ sơ với hai thuộc tính được phép cập nhật: `displayName` và `email`. Đối tượng Java lại có thêm `role` và `internalNote`, những thuộc tính chỉ hệ thống được phép quản lý. Một request gửi lên:

```text
displayName=Lan
email=lan@example.org
role=ADMIN
internalNote=overwrite
```

Nếu dùng property binding lên object có setter cho cả bốn trường mà không giới hạn đầu vào, client có thể cố thay đổi dữ liệu không nằm trong form. Spring `DataBinder` cho phép cấu hình **allowlist** và/hoặc **denylist** để loại các trường ngoài chính sách binding. Những tên trường bị loại được lưu vào `BindingResult` và có thể đọc bằng:

```java
String[] suppressed =
    binder.getBindingResult().getSuppressedFields();
```

Kết quả trên là **danh sách tên trường bị từ chối trong quá trình binding**, không phải danh sách giá trị bị từ chối và cũng không phải danh sách validation errors. Nó hữu ích cho kiểm tra đầu vào, quan sát dấu hiệu mass assignment và kiểm thử chính sách field binding.

Mục tiêu bài học là hiểu chính xác khi nào một trường bị suppressed, cách đọc `getSuppressedFields()`, cách quyết định có từ chối toàn request hay không, và giới hạn của cơ chế này.

## 2. Những API tham gia

| API | Vai trò |
| --- | --- |
| `DataBinder.setAllowedFields(String... fields)` | Đăng ký các tên/pattern **được phép** bind bằng cơ chế property binding. |
| `DataBinder.setDisallowedFields(String... fields)` | Đăng ký các tên/pattern **không được phép** bind bằng property binding. |
| `DataBinder.bind(PropertyValues)` | Thực hiện bind các cặp tên/giá trị vào target, có bước kiểm tra allowed/disallowed fields. |
| `DataBinder.getBindingResult()` | Trả `BindingResult` ghi nhận lỗi và các thông tin về quá trình binding. |
| `BindingResult.getSuppressedFields()` | Trả `String[]` gồm **tên trường** đã bị ngăn khỏi binding. |
| `BindingResult.recordSuppressedField(String field)` | API ghi nhận trường bị loại, thường do chính binder gọi khi phát hiện giá trị nhắm tới field không được phép. |
| `BindingResult.hasErrors()` | Kiểm tra lỗi binding/validation; không đồng nghĩa kiểm tra suppressed fields. |
| `DataBinder.setDeclarativeBinding(true)` | Từ Spring 6.1, có thể hạn chế property binding theo cách khai báo tường minh, bên cạnh constructor binding. |

Các interface/class ở đây thuộc namespace `org.springframework.validation.*` và `org.springframework.beans.*`. `BindingResult` mở rộng `Errors`, nhưng `getSuppressedFields()` là **thông tin riêng cho quá trình binding** chứ không phải một `FieldError`.

### Hai loại kết quả phải kiểm tra độc lập

```java
BindingResult result = binder.getBindingResult();

boolean hasBindingOrValidationErrors = result.hasErrors();
boolean hasSuppressedFields = result.getSuppressedFields().length > 0;
```

Có thể xảy ra:

- `hasErrors() == false` nhưng `hasSuppressedFields == true`: các input được cho phép bind thành công, trong khi request có thêm field bị chặn.
- `hasErrors() == true` và `hasSuppressedFields == false`: ví dụ giá trị `age=abc` không chuyển được thành `int` nhưng không vi phạm danh sách allowed fields.
- Cả hai đều `true` hoặc cả hai đều `false`.

**Không dùng `hasErrors()` thay cho kiểm tra `getSuppressedFields()`.** Một request chỉ chứa thêm field bị chặn có thể không tạo `FieldError` hay `ObjectError` nào.

## 3. Cơ chế Spring loại bỏ các field

Với đường **property binding**, ta có thể hình dung luồng xử lý:

```text
PropertyValues từ request / form / map
              |
              v
      DataBinder.bind(...)
              |
              v
  Kiểm tra allowed / disallowed
        |               |
        | được phép     | không được phép
        v               v
 Kiểm tra required   Loại khỏi dữ liệu sẽ bind
 / conversion          |
        |               v
        |       BindingResult.recordSuppressedField(name)
        v
 Gán vào property
        |
        v
BindingResult: errors + suppressed field names
```

`DataBinder` kiểm tra từng tên thuộc tính trước khi áp dụng các giá trị lên target. Nếu không được phép:

1. Property value tương ứng bị loại khỏi danh sách sẽ bind.
2. Tên field được ghi vào `BindingResult` bằng cơ chế `recordSuppressedField(...)`.
3. Setter/property đó không được cập nhật bởi giá trị đã bị loại.
4. Request không tự động bị Spring chuyển thành validation error chỉ vì có suppressed field.

Spring xử lý binding từ `MutablePropertyValues` và có phương thức nội bộ `checkAllowedFields(...)`. Khi triển khai dựa trên Spring MVC, `WebDataBinder` kế thừa cơ chế từ `DataBinder`.

**Phạm vi chính xác:** cơ chế `setAllowedFields`/`setDisallowedFields` này áp dụng cho **property binding thông qua `bind(PropertyValues)`**. Nó không dùng để giới hạn trực tiếp các tham số của **constructor binding** bằng `construct(ValueResolver)`, vì constructor binding chỉ tìm những giá trị cần cho các tham số constructor đã được khai báo. Với constructor binding, hãy thiết kế DTO/constructor để chỉ tiếp nhận những giá trị người dùng được phép cung cấp.

## 4. Allowlist: chỉ bind những trường đã công bố

Ví dụ:

```java
DataBinder binder = new DataBinder(profile, "profile");
binder.setAllowedFields("displayName", "email");
binder.bind(propertyValues);
```

Spring chỉ cho phép property binding đến `displayName` và `email`. Nếu input có `role`, `internalNote`, cả hai sẽ bị suppressed. Cách này phù hợp với form nhập liệu có phạm vi rõ ràng.

**Mặc định**, khi không cấu hình `allowedFields`, Spring không giới hạn property binding bằng một allowlist cụ thể; vì thế nên chủ động cấu hình cho những model chứa dữ liệu nhạy cảm hoặc sử dụng một DTO chuyên biệt chỉ chứa các trường cho phép.

### Pattern trong setAllowedFields

Spring hỗ trợ tên field chính xác và wildcard đơn giản, ví dụ:

```java
binder.setAllowedFields(
    "displayName",
    "email",
    "address.street",
    "address.city",
    "phones[*]"
);
```

Đoạn trên là minh họa cho một model có các thuộc tính tương ứng. Với danh sách/array/map cần xem pattern nào thực tế khớp với đường dẫn do binder nhận, chẳng hạn `phones[0]` hoặc `map[key]`. Javadoc mô tả wildcard dạng `xxx*`, `*xxx`, `*xxx*`, `xxx*yyy`; không nên mặc định Spring hiểu toàn bộ cú pháp regex hay Ant path patterns.

Với nested object, cần thận trọng với pattern quá rộng:

```java
binder.setAllowedFields("address.*");
```

Pattern này có thể chấp nhận nhiều thuộc tính con hơn dự kiến. Nếu object `address` sau này bổ sung một setter nhạy cảm, allowlist quá rộng có thể vô tình mở quyền binding cho field đó. Ưu tiên tên cụ thể, hoặc dùng DTO đầu vào tách biệt.

### Case sensitivity

Ở Spring Framework 6.1, so khớp **allowed field patterns phân biệt chữ hoa/thường**. Ví dụ pattern `"email"` không nên được hiểu là tự động cấp phép mọi biến thể viết hoa. Các tên property Java cũng cần khớp đúng cách Spring diễn giải, bao gồm nested/indexed paths.

## 5. Denylist: chỉ chặn các trường đã chỉ định

Ví dụ:

```java
DataBinder binder = new DataBinder(profile, "profile");
binder.setDisallowedFields("role", "internalNote");
binder.bind(propertyValues);
```

Các trường `role` và `internalNote` bị loại khỏi property binding, còn những field khác vẫn có thể được xử lý. Cách này giúp minh họa cơ chế suppressed fields nhưng **dễ sót** trường nhạy cảm mới được thêm vào object trong tương lai.

Theo Javadoc Spring 6.1:

- Matching của **disallowed field patterns không phân biệt chữ hoa/thường**; các pattern được canonicalize và chuyển thành lowercase trong triển khai mặc định.
- Matching của **allowed field patterns phân biệt chữ hoa/thường**.
- **Denylist có quyền ưu tiên**: một tên khớp disallowed pattern sẽ bị chặn ngay cả khi nó cũng khớp allowed pattern.

Ví dụ để chỉ rõ thứ tự ưu tiên:

```java
binder.setAllowedFields("displayName", "role");
binder.setDisallowedFields("role");
```

Với input `role=ADMIN`, `role` vẫn bị suppressed. Không có quy tắc "allowlist ghi sau sẽ mở khóa denylist". Các quy tắc lọc nên được thiết kế nhất quán, tránh dùng đồng thời hai danh sách phức tạp nếu không thực sự cần.

**Định hướng an toàn:** với dữ liệu form đến từ client, thường nên dùng một **allowlist cụ thể** hoặc DTO đầu vào chỉ chứa field được phép. Denylist dễ thiếu các field mới. Ngoài cơ chế binding, hệ thống vẫn cần authorization ở tầng nghiệp vụ để quyết định ai được thay đổi tài nguyên nào.

## 6. Ví dụ Java 17 chạy được: hai trường bị suppressed

Chương trình sau sử dụng **Spring Framework 6.1.14**, không cần Spring Boot web server. Ta cố tình tạo form có các setter dành cho thuộc tính nhạy cảm để thấy rõ việc `DataBinder` ngăn các giá trị ngoài allowlist.

Cấu trúc:

```text
suppressed-fields-demo/
├── pom.xml
└── src/main/java/demo/SuppressedFieldsDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>suppressed-fields-demo</artifactId>
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

File `src/main/java/demo/SuppressedFieldsDemo.java`:

```java
package demo;

import java.util.Arrays;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public final class SuppressedFieldsDemo {

    public static final class ProfileForm {
        private String displayName;
        private String email;
        private String role = "USER";
        private String internalNote = "server-only";

        public String getDisplayName() {
            return displayName;
        }
        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }

        public String getEmail() {
            return email;
        }
        public void setEmail(String email) {
            this.email = email;
        }

        public String getRole() {
            return role;
        }
        public void setRole(String role) {
            this.role = role;
        }

        public String getInternalNote() {
            return internalNote;
        }
        public void setInternalNote(String internalNote) {
            this.internalNote = internalNote;
        }
    }

    private static String suppressed(BindingResult result) {
        String[] fields = result.getSuppressedFields().clone();
        Arrays.sort(fields); // Thứ tự ổn định khi in ra.
        return Arrays.toString(fields);
    }

    public static void main(String[] args) {
        ProfileForm first = new ProfileForm();
        DataBinder allowBinder = new DataBinder(first, "profile");
        allowBinder.setAllowedFields("displayName", "email");

        MutablePropertyValues incoming = new MutablePropertyValues();
        incoming.add("displayName", "Lan");
        incoming.add("email", "lan@example.org");
        incoming.add("role", "ADMIN");
        incoming.add("internalNote", "overwrite");

        allowBinder.bind(incoming);
        BindingResult firstResult = allowBinder.getBindingResult();

        System.out.println("ALLOWLIST");
        System.out.println("displayName=" + first.getDisplayName());
        System.out.println("email=" + first.getEmail());
        System.out.println("role=" + first.getRole());
        System.out.println("internalNote=" + first.getInternalNote());
        System.out.println("suppressed=" + suppressed(firstResult));
        System.out.println("hasErrors=" + firstResult.hasErrors());

        // Trường có mặt trong allowlist vẫn bị chặn nếu denylist cấm.
        ProfileForm second = new ProfileForm();
        DataBinder bothBinder = new DataBinder(second, "profile");
        bothBinder.setAllowedFields("displayName", "role");
        bothBinder.setDisallowedFields("role");

        MutablePropertyValues secondInput = new MutablePropertyValues();
        secondInput.add("displayName", "Mai");
        secondInput.add("role", "ADMIN");

        bothBinder.bind(secondInput);

        System.out.println("ALLOW_AND_DENY");
        System.out.println("displayName=" + second.getDisplayName());
        System.out.println("role=" + second.getRole());
        System.out.println("suppressed="
                + suppressed(bothBinder.getBindingResult()));
    }
}
```

Trong thư mục `suppressed-fields-demo`, chạy với JDK 17+ và Maven đã cấu hình:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.SuppressedFieldsDemo
```

Những dòng chương trình in ra (không tính log của Maven/Spring nếu có):

```text
ALLOWLIST
displayName=Lan
email=lan@example.org
role=USER
internalNote=server-only
suppressed=[internalNote, role]
hasErrors=false
ALLOW_AND_DENY
displayName=Mai
role=USER
suppressed=[role]
```

**Phân tích:**

1. Bốn cặp tên/giá trị được gửi cho binder đầu tiên. Hai tên `displayName` và `email` khớp allowlist, nên setter của chúng được gọi.
2. `role` và `internalNote` không nằm trong allowlist, nên dữ liệu tương ứng bị loại trước khi ghi vào target.
3. Hai thuộc tính bị chặn vẫn giữ giá trị khởi tạo ở phía server: `role=USER` và `internalNote=server-only`.
4. `getSuppressedFields()` cung cấp hai **tên field**, không chứa `"ADMIN"` hay `"overwrite"`. Chương trình sort bản sao mảng để kết quả ổn định; thứ tự field suppression không nên được dùng như giao ước nghiệp vụ.
5. `firstResult.hasErrors()` là `false` vì các field hợp lệ được bind thành công, và suppression tự nó không đăng ký `FieldError`. Đây là điểm quan trọng nhất của bài.
6. Trong binder thứ hai, `role` xuất hiện **đồng thời** trong allowlist và denylist. Denylist thắng, nên `role` tiếp tục là `USER` và `getSuppressedFields()` chứa `role`.

Ví dụ không chạy validator; nó kiểm tra **quy tắc property binding**. Nếu cần validation nghiệp vụ, đăng ký Spring `Validator` hoặc Jakarta Validation adapter phù hợp rồi gọi validation hoặc để Spring MVC kích hoạt.

## 7. Cách theo dõi field bị loại bỏ sau binding

`BindingResult.getSuppressedFields()` trả về một mảng `String[]`. Từ API, cách kiểm tra đơn giản nhất là:

```java
BindingResult result = binder.getBindingResult();
String[] suppressed = result.getSuppressedFields();

if (suppressed.length > 0) {
    // Ghi nhận dấu hiệu đầu vào không nằm trong chính sách binding.
}
```

Đoạn này minh họa sau khi binder đã xử lý request. Có hai cách xử lý phổ biến:

### A. Ghi nhận rồi tiếp tục xử lý phần dữ liệu hợp lệ

Với một giao diện cũ có thể gửi field không còn được hỗ trợ, hệ thống có thể cần theo dõi trong giai đoạn chuyển đổi. Khi đó có thể log **tên field** và cho phép xử lý các field còn hợp lệ, nếu chính sách API cho phép. Phải hiểu rằng một tên không còn hỗ trợ cũng có thể là lỗi tương thích client, không nhất thiết là một cuộc tấn công.

Ví dụ:

```java
String[] fields = result.getSuppressedFields();

if (fields.length > 0) {
    logger.warn("Rejected bind field names: {}", Arrays.toString(fields));
}
```

Đây là snippet cần một logger `SLF4J` và import `java.util.Arrays`. Ở hệ thống thực, dùng log có cấu trúc, kết hợp route/correlation ID để điều tra, và kiểm soát dung lượng log.

### B. Từ chối toàn request khi thấy field bị chặn

Với API yêu cầu hợp đồng input nghiêm ngặt, policy có thể quyết định trả **HTTP 400 Bad Request** ngay khi request có suppressed field. Ví dụ trong controller, kiểm tra trước khi lưu dữ liệu vào database hoặc gọi service có side effect.

```java
if (result.getSuppressedFields().length > 0) {
    throw new IllegalArgumentException(
        "Request contains fields that are not bindable"
    );
}
```

Đoạn minh họa trên là Java thuần; trong Spring MVC nên ánh xạ exception sang HTTP response phù hợp hoặc chủ động dùng `ResponseStatusException`. Mã trên **không** làm DataBinder tự ném exception; chính ứng dụng chủ động quyết định.

### Nên log những gì?

- **Nên:** tên field bị loại, tên endpoint/form, định danh request đã khử thông tin nhạy cảm, số lượng field, version API.
- **Không nên mặc định:** giá trị raw của field, request body đầy đủ, cookie, token, mật khẩu, dữ liệu cá nhân hoặc thông tin chưa được lọc.
- **Cần cân nhắc:** tên field do client cung cấp vẫn là input không tin cậy; cần giới hạn độ dài, khử ký tự điều khiển khi đưa vào log để tránh log injection và tránh tạo lượng dữ liệu log không giới hạn.
- **Không suy diễn:** một trường bị suppressed có thể xuất phát từ client cũ, lỗi frontend, automation hoặc hành vi thăm dò. Cần kết hợp các bằng chứng khác trước khi kết luận có tấn công.

Có thể đưa số lượng bị chặn vào metric nội bộ, nhưng không mặc định công khai danh sách tên field nhạy cảm ra response cho người dùng cuối.

## 8. Spring MVC: theo dõi thông qua @InitBinder và BindingResult

Trong ứng dụng web sử dụng `@ModelAttribute`, Spring MVC tạo một `WebDataBinder` cho quá trình binding. Ta có thể cấu hình allowlist bằng `@InitBinder`; sau đó đọc suppressed fields từ tham số `BindingResult`.

Ví dụ **minh họa tích hợp**, giả sử đã có `ProfileForm` và một Spring MVC application:

```java
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.server.ResponseStatusException;

@Controller
class ProfileController {

    @InitBinder("profile")
    void restrictProfileBinding(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "email");
    }

    @PostMapping("/profile")
    String updateProfile(
            @ModelAttribute("profile") ProfileForm form,
            BindingResult errors) {

        if (errors.getSuppressedFields().length > 0) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Unsupported profile fields"
            );
        }

        if (errors.hasErrors()) {
            return "profile-form";
        }

        // Gọi service cập nhật các trường đã được phân quyền.
        return "profile-saved";
    }
}
```

Đoạn này **không phải** file Java chạy độc lập ở mục 6. Nó cần `ProfileForm`, dependency Spring Web MVC, controller scanning, routing và một ứng dụng chạy web. `BindingResult` nằm **ngay sau** tham số `@ModelAttribute` để đọc đúng kết quả binding của object đó.

Trong ví dụ:

1. `@InitBinder("profile")` cấu hình allowlist cho model attribute mang tên `profile`.
2. Spring MVC chuyển các form/query parameters tới `WebDataBinder` theo quy trình model attribute binding.
3. Field nằm ngoài allowlist bị suppressed; tên field hiện trong `BindingResult.getSuppressedFields()`.
4. Controller chủ động trả lỗi client nếu policy không cho phép ignored fields.
5. Nếu không có suppression nhưng có binding/validation errors, controller xử lý form như bình thường.
6. Khi dữ liệu hợp lệ, tầng service vẫn phải xác minh quyền cập nhật hồ sơ của người dùng hiện tại.

### @RequestBody có đi qua cùng đường này?

Không nên suy luận rằng mọi JSON key lạ trong `@RequestBody` đều xuất hiện ở `getSuppressedFields()`. Với request JSON, Spring MVC thường dùng `HttpMessageConverter` (ví dụ Jackson) để deserialize body. Unknown JSON properties và cấu hình JSON binding do converter xử lý; chúng **không nhất thiết** đi qua `DataBinder.bind(PropertyValues)`. `getSuppressedFields()` chủ yếu có ý nghĩa khi đang dùng cơ chế **property binding** của `DataBinder`/`WebDataBinder`, chẳng hạn `@ModelAttribute`.

Nếu ứng dụng cần kiểm soát và theo dõi JSON fields, hãy dùng DTO, JSON deserialization settings và các kiểm tra schema/authorization phù hợp. Không coi `getSuppressedFields()` như hệ thống phát hiện tất cả unknown keys của mọi định dạng request.

## 9. Suppressed fields khác unknown fields và binding errors

Ba hiện tượng khác nhau cần được phân biệt:

| Hiện tượng | Ví dụ | Spring thường xử lý |
| --- | --- | --- |
| **Suppressed field** | `role` có setter nhưng không nằm trong `setAllowedFields(...)` | Bỏ property value khỏi binding và ghi **tên field** vào `getSuppressedFields()`. |
| **Unknown property** | Input có `obsoleteField` nhưng model không có thuộc tính đó; không bị allow/deny filter bắt trước | Theo `setIgnoreUnknownFields(...)`, mặc định có thể bỏ qua; không thể coi mọi unknown property đều là suppressed field. |
| **Binding/conversion error** | `age=abc` nhưng property Java có kiểu `Integer` | Thường phát sinh `FieldError` với mã như `typeMismatch`; xem `hasErrors()` và `getFieldErrors()`. |

Ví dụ:

```java
binder.setIgnoreUnknownFields(true); // Mặc định của DataBinder.
```

Cấu hình này **khác** `setAllowedFields(...)`: nó liên quan đến những property không tồn tại trên model. Nếu một tên đã bị chặn bởi allowlist, nó có thể được ghi là suppressed trước khi Spring thử truy cập thuộc tính đó. Nếu một tên được phép nhưng model không có property tương ứng, cách xử lý phụ thuộc cờ ignore unknown fields và cơ chế property access.

Do đó không dùng `getSuppressedFields()` làm bộ đếm hoàn chỉnh của mọi input lạ hoặc mọi dữ liệu không được chấp nhận.

### Suppressed fields có tạo FieldError không?

Thông thường **không**. `DataBinder.checkAllowedFields(...)` bỏ các property values không được phép và ghi vào tập suppressed field names. Đây là một loại **metadata về binding**. Một error do validator hoặc conversion lại được biểu diễn bằng `FieldError`/`ObjectError`. Nếu ứng dụng muốn coi suppression là một lỗi request, hãy tự định nghĩa policy trả 400 hoặc cơ chế báo lỗi riêng.

### getSuppressedFields có phải chứa các giá trị bị từ chối?

Không. Phương thức trả **tên trường**. Điều này giúp theo dõi mà không cần chuyển raw giá trị vào log. Tuy nhiên, chỉ tên field cũng có thể tiết lộ cấu trúc API nếu trả cho client; cân nhắc nội dung response.

## 10. Nested paths, collections và wildcard: kiểm soát đúng phạm vi

Spring hỗ trợ các đường dẫn thuộc tính lồng nhau, indexed và map keys:

```text
address.city
address.country
items[0].sku
items[1].quantity
preferences[theme]
```

Khi thiết lập allowlist, nên gắn pattern với những đường dẫn thực sự được phép, ví dụ:

```java
binder.setAllowedFields(
    "displayName",
    "address.city",
    "address.country",
    "items[*].sku"
);
```

Đây là snippet minh họa; model cần có các field, getter/setter/collection phù hợp. Wildcard của Spring là **simple matching**, không phải regex. Cần kiểm thử pattern trên những input nested/indexed thực tế mà frontend có thể gửi.

Những điều cần kiểm tra:

- Tên field trong `getSuppressedFields()` là đường dẫn property Spring ghi nhận; không nên giả định nó luôn là tên đơn hoặc luôn xuất hiện đúng thứ tự request.
- Pattern `address.*` có thể bao gồm field mới của `address` nếu model phát triển. Cụ thể hóa danh sách nếu đó là dữ liệu có quyền truy cập chặt.
- `items[*].sku` và `items[0].sku` có tính bao phủ khác nhau; kiểm tra wildcard theo Javadoc và test.
- Tên map key và biểu thức indexed có thể bị canonicalize. Cần so sánh trên tên chuẩn mà Spring sử dụng, không dựa vào suy đoán chuỗi request raw.
- Với input rất lớn hoặc indexes bất thường, giới hạn kích thước và khả năng auto-grow collection; suppression không phải cơ chế chống lạm dụng bộ nhớ.
- Đừng đưa toàn bộ field path từ client vào log mà không giới hạn số ký tự và lượng dữ liệu.

## 11. Declarative binding từ Spring 6.1

Spring Framework 6.1 cung cấp:

```java
binder.setDeclarativeBinding(true);
```

Theo Javadoc, cấu hình này giới hạn đường bind theo hướng:

- **Constructor binding** được áp dụng cho các constructor parameters đã công bố.
- **Property binding** chỉ áp dụng khi cấu hình các `allowedFields` được cho phép.

Ví dụ trong một controller:

```java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAllowedFields("displayName", "email");
}
```

Đây là snippet cần đặt trong controller hoặc `@ControllerAdvice`, cùng import phù hợp. Kết hợp này giúp tổ chức quy tắc binding một cách tường minh.

**Giới hạn cần hiểu khi giám sát:** nếu declarative binding tắt hẳn đường property binding vì không có allowlist, không nên suy ra rằng tất cả key request ngoài constructor đều sẽ được ghi trong `getSuppressedFields()`. Cơ chế ghi suppressed fields chủ yếu đến từ bước kiểm tra các property values trong `checkAllowedFields(...)`; một đường xử lý không tiến hành bước ấy không nhất thiết tạo danh sách tên bị chặn. Hãy coi `getSuppressedFields()` là chỉ báo của **những trường đã được binder ghi nhận là suppressed**, không phải nhật ký hoàn chỉnh mọi đầu vào đã bỏ qua.

### Tại sao constructor binding không bị kiểm soát bởi setAllowedFields?

`construct(ValueResolver)` lấy những giá trị cần cho constructor parameters; `setAllowedFields(...)` điều khiển đường **property binding**. Nếu một DTO constructor chứa tham số `role` và client cung cấp `role=ADMIN`, việc đặt property allowlist không tự động xóa vai trò đó khỏi chữ ký constructor. Thiết kế DTO chỉ có các constructor arguments client được phép cấp, và gán vai trò thực tế từ server.

Đây cũng là lý do **giới hạn dữ liệu ở DTO** thường dễ kiểm soát hơn bind trực tiếp vào domain/JPA entity vốn có nhiều setter và quan hệ nội bộ.

## 12. Theo dõi trong môi trường production

Một policy thực tế nên xác định rõ:

1. **Phạm vi input**: endpoint nào dùng `@ModelAttribute`/property binding, endpoint nào dùng JSON converter.
2. **Chính sách chấp nhận**: danh sách field nào được phép sửa trong từng use case; ưu tiên DTO riêng.
3. **Hành vi khi thấy suppressed**: từ chối request, hoặc trong giai đoạn chuyển đổi có thể chỉ ghi nhận và cảnh báo.
4. **Observability**: route template, correlation ID, số field bị chặn và các tên field đã được giới hạn/sanitize; tránh log giá trị bí mật.
5. **Kiểm thử hồi quy**: khi thêm property vào DTO/domain, gửi input cố thay đổi property đó và xác minh dữ liệu server không bị đổi.
6. **Authorization**: xác minh người dùng có quyền sửa bản ghi/tài nguyên; allowlist không quyết định quyền truy cập giữa các đối tượng.
7. **Giám sát**: biến động số request bị chặn có thể phát hiện lỗi frontend hoặc hành vi thăm dò, nhưng không tự động kết luận đó là tấn công.

Ví dụ pseudo-logic tại một tầng ứng dụng đã có binder/result:

```java
String[] suppressed = result.getSuppressedFields();

if (suppressed.length != 0) {
    // Increment metric for route + reason "field_suppressed".
    // Log bounded, sanitized field names; no raw values.
    // Reject request if the endpoint contract requires strict fields.
}
```

Đây là pseudocode, phần ghi metric/log tùy hệ thống. Không dùng chính dữ liệu raw client làm label có cardinality không giới hạn cho metrics; dùng route template hoặc nhóm nguyên nhân đã chuẩn hóa.

### Nên kiểm thử những trường hợp nào?

| Test case | Kỳ vọng |
| --- | --- |
| Chỉ gửi `displayName` và `email` trong allowlist | Binder cập nhật hai field, suppressed rỗng. |
| Gửi thêm `role` ngoài allowlist | `role` không đổi; `getSuppressedFields()` chứa `role`. |
| `role` vừa có trong allowlist vừa bị deny | Denylist ưu tiên, `role` vẫn bị suppressed. |
| Gửi giá trị sai kiểu cho field được phép | Có binding error phù hợp; không nhất thiết có suppressed field. |
| Gửi unknown field khi không có allowlist | Kết quả phụ thuộc `ignoreUnknownFields`; không mặc định coi là suppressed. |
| Gửi nested/indexed field | Kiểm tra đúng đường dẫn và pattern cho phép. |
| Client gửi key khác chữ hoa/thường | Kiểm tra case-sensitive allowlist và case-insensitive denylist trên phiên bản Spring đang chạy. |
| Dùng `@RequestBody` JSON | Kiểm tra cấu hình Jackson/DTO riêng; không phụ thuộc `getSuppressedFields()`. |
| Dùng constructor binding | Kiểm tra chữ ký constructor và các field được lấy từ request. |

## 13. Các nhầm lẫn và lỗi phổ biến

1. **Chỉ kiểm tra `BindingResult.hasErrors()`.** Suppression thường không được ghi thành validation error; phải kiểm tra `getSuppressedFields()` riêng.
2. **Dùng `setDisallowedFields("role")` rồi quên các thuộc tính nhạy cảm mới.** Denylist có thể bỏ sót khi model phát triển; ưu tiên allowlist hoặc DTO chuyên biệt.
3. **Bind trực tiếp vào JPA entity.** Entity thường có nhiều thuộc tính, quan hệ và setter không nên mở cho client; dùng request DTO với phạm vi rõ ràng.
4. **Tin rằng `getSuppressedFields()` cho biết toàn bộ input bất thường.** Unknown properties, JSON deserialization, constructor binding và các đường xử lý khác không nhất thiết được ghi trong mảng này.
5. **Gửi danh sách field bị suppressed cho người dùng cuối mà không cân nhắc.** API có thể vô tình để lộ tên property nội bộ; trả lỗi chung và giữ chi tiết cần thiết ở log có kiểm soát.
6. **Log raw rejected values.** `getSuppressedFields()` trả tên, không trả giá trị; đừng tự thu lại toàn request chỉ để log, đặc biệt khi có credential hoặc thông tin cá nhân.
7. **Sử dụng wildcard quá rộng.** `address.*` hoặc `*` có thể cho phép field mới không được thiết kế để sửa.
8. **Nhầm `setIgnoreUnknownFields` với `setAllowedFields`.** Một flag điều khiển unknown property; flag kia giới hạn danh sách field có quyền bind.
9. **Coi suppression là authorization.** Nó bảo vệ bề mặt property binding, nhưng không xác minh người dùng có quyền sửa bản ghi hoặc vai trò nào.
10. **Không tái kiểm tra sau khi mở rộng model.** Thêm setter mới vào class có thể làm đổi phạm vi binding; test allowlist giúp ngăn hồi quy.
11. **So sánh thứ tự mảng suppressed fields trong test.** Nên sort hoặc so sánh theo tập tên; nghiệp vụ không nên phụ thuộc thứ tự ghi nhận.
12. **Cố áp dụng allowlist của property binding cho constructor parameters.** Hai cơ chế binding dùng đường xử lý khác nhau; constructor phải được thiết kế để chỉ lấy đúng các trường mong muốn.

## 14. Câu hỏi tự kiểm tra

1. `BindingResult.getSuppressedFields()` trả về kiểu gì? Nó chứa tên field hay giá trị của input?
2. Vì sao một request có `role=ADMIN` bị chặn vẫn có thể khiến `BindingResult.hasErrors()` trả `false`?
3. Khi `role` có trong cả `setAllowedFields` và `setDisallowedFields`, kết quả là gì?
4. `setAllowedFields` và `setDisallowedFields` khác nhau về phạm vi field mặc định và tính phân biệt hoa/thường ra sao?
5. `setIgnoreUnknownFields(true)` có bảo đảm mọi key lạ đều xuất hiện trong `getSuppressedFields()` không? Vì sao?
6. Trường hợp nào nên trả HTTP 400 khi có suppressed field, trường hợp nào có thể chỉ giám sát trong giai đoạn chuyển đổi?
7. Vì sao không nên bind thẳng vào entity có setter `setRole` hoặc `setBalance`?
8. Trong `@ModelAttribute`, cách lấy suppressed fields từ controller là gì và `BindingResult` phải đặt ở đâu?
9. Vì sao `@RequestBody` JSON với unknown property không phải lúc nào cũng đi qua `DataBinder.getSuppressedFields()`?
10. Với Spring 6.1 `setDeclarativeBinding(true)`, tại sao không thể xem mảng suppressed là bản ghi đầy đủ của mọi key mà client gửi?

**Ghi nhớ:** `DataBinder` có thể chặn các field không nằm trong chính sách **property binding**; `BindingResult.getSuppressedFields()` cho biết **tên những field đã bị binder ghi nhận là suppressed**. Kết quả này không tự động là binding error hay validation error. Để theo dõi và bảo vệ ứng dụng, hãy dùng allowlist/DTO rõ ràng, kiểm tra suppressed fields độc lập với `hasErrors()`, và đặt chính sách xử lý/log phù hợp ở entry point.

## Tài liệu tham khảo

- Spring Framework 6.1 — DataBinder Javadoc: https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.1 — BindingResult Javadoc: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/validation/BindingResult.html
- Spring Framework 6.1 — AbstractBindingResult Javadoc: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/validation/AbstractBindingResult.html
- Spring Framework — Data Binding / Model Design: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
- Spring Framework — Validation, Data Binding and Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation.html
