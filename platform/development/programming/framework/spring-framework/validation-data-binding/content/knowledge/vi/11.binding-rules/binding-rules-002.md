# setDisallowedFields và giới hạn của danh sách loại trừ

## 1. Tại sao cần kiểm soát các trường được bind?

Khi Spring Framework nhận tham số biểu mẫu, `DataBinder` có thể ánh xạ mỗi tên tham số vào một JavaBean property, chuyển kiểu rồi gọi setter tương ứng. Ví dụ `displayName=Lan` có thể gọi `setDisplayName("Lan")`. Với `@ModelAttribute` trong Spring MVC, cơ chế này được sử dụng để tạo và điền form/command object.

Vấn đề xuất hiện khi đối tượng đích còn có các thuộc tính **không dành cho client chỉnh sửa**, như `role`, `admin`, `ownerId`, `approved` hoặc `version`. Không có ô nhập trên giao diện không đồng nghĩa với việc client không thể gửi tham số mang tên thuộc tính đó.

Ví dụ một HTTP form cố gửi:

~~~text
displayName=Lan
role=ADMIN
admin=true
~~~

Nếu object có các setter tương ứng và không giới hạn property binding, client có thể cố làm thay đổi cả tên lẫn quyền. Đây là rủi ro *mass assignment*: hệ thống vô tình cho dữ liệu bên ngoài điều khiển những field nằm ngoài hợp đồng nghiệp vụ.

`setDisallowedFields(String... patterns)` là tính năng của `org.springframework.validation.DataBinder` cho phép khai báo **những tên property/path cần loại khỏi lượt property binding**. Ví dụ:

~~~java
DataBinder binder = new DataBinder(form, "profile");
binder.setDisallowedFields("role", "admin");
~~~

Khi bind, Spring chặn các field khớp `role` hoặc `admin`. Những field còn lại, chẳng hạn `displayName`, vẫn có thể được gán nếu property writable và giá trị phù hợp.

Điểm quan trọng: đây là **danh sách loại trừ** (*denylist*). Nó liệt kê những gì đã biết là bị cấm. Nó không định nghĩa toàn bộ những gì được phép, nên một thuộc tính mới được thêm vào model có thể được bind nếu không được cập nhật vào danh sách chặn.

## 2. Luồng DataBinder xử lý field bị cấm

Trong property binding, binder thường đi qua các bước:

~~~text
       Dữ liệu request / PropertyValues
                    |
                    v
           DataBinder / WebDataBinder
                    |
       Kiểm tra allowed/disallowed fields
                    |
         +----------+----------+
         |                     |
  Field bị loại           Field được phép
         |                     |
   Không gọi setter       Type conversion
   để gán field đó              |
         |               Gán giá trị hoặc
   Ghi tên field          ghi binding error
   vào suppressed               |
         |                     |
         +----------+----------+
                    |
                    v
              BindingResult
         getSuppressedFields()
         getFieldErrors()
         hasErrors()
~~~

Các khái niệm phải phân biệt:

- **Suppressed field**: bị loại theo chính sách allowed/disallowed. Nó không được gán bởi lượt property binding này.
- **Binding error**: một field được chấp nhận nhưng không chuyển/gán được. Ví dụ `age=abc` khi property có kiểu `Integer` có thể sinh lỗi `typeMismatch`.
- **Validation error**: giá trị sau khi bind không thỏa các ràng buộc, ví dụ `@NotBlank` hoặc `@Min(1)`.
- **Unknown field**: tên không tương ứng property trên target; hành vi tùy `ignoreUnknownFields` và cơ chế truy cập thuộc tính.

**Field bị suppressed thường không tự sinh `FieldError`.** Do đó `BindingResult.hasErrors()` có thể là `false` mặc dù client đã gửi field mà binder không cho phép. Nếu API yêu cầu từ chối request chứa field ngoài hợp đồng, ứng dụng phải kiểm tra `getSuppressedFields()` riêng.

`setDisallowedFields` cần được thiết lập **trước** `bind(...)`. Cấu hình mặc định không có disallowed pattern, nghĩa là không có danh sách cấm bổ sung từ API này.

## 3. Cú pháp tên và pattern

`setDisallowedFields(...)` nhận tên property hoặc mẫu `*` theo quy tắc simple pattern matching của Spring. Đây **không phải biểu thức chính quy** (regular expression).

| Pattern | Ví dụ trường khớp | Ý nghĩa cần chú ý |
|---|---|---|
| `"role"` | `role` | Tên cụ thể, không tự bao phủ mọi nested path |
| `"admin"` | `admin`, `ADMIN` | Disallowed matching không phân biệt hoa/thường |
| `"secret*"` | `secret`, `secretKey` | Chặn các tên bắt đầu bằng `secret` |
| `"*Password"` | `oldPassword`, `temporaryPassword` | Chặn những tên kết thúc tương ứng |
| `"address.*"` | `address.street`, `address.ownerId` | Mẫu dành cho property path lồng nhau |
| `"items[*].ownerId"` | `items[0].ownerId`, `items[7].ownerId` | Dấu `*` khớp vị trí chỉ số trong path |
| `"*role*"` | Nhiều tên có chứa `role` | Dễ chặn nhầm field hợp lệ |

Tên property có thể ở dạng `address.ownerId`, `items[0].approved` hoặc `metadata[key]` tùy kiểu object, nested bean, List hay Map. Một cấu hình chỉ cấm `"role"` **không tự bảo đảm** chặn mọi đường dẫn như `"account.role"` hoặc `"items[0].role"`.

Các mẫu có dấu `*` cũng có thể khớp nhiều tên hơn dự kiến. Vì vậy cần kiểm tra bằng đúng property path mà ứng dụng nhận; đừng giả định denylist là một công cụ phân tích toàn bộ object graph hoặc quyền nghiệp vụ.

### Phân biệt hoa/thường và mức ưu tiên

Theo hợp đồng Spring Framework 6.x:

- `setDisallowedFields` so khớp **không phân biệt hoa/thường**.
- `setAllowedFields` so khớp **phân biệt hoa/thường**.
- Nếu một field đồng thời khớp allowed và disallowed pattern, **disallowed thắng**: field vẫn bị loại.

Ví dụ:

~~~java
binder.setAllowedFields("displayName", "email", "role");
binder.setDisallowedFields("role");
~~~

`role` vẫn bị loại; `displayName` và `email` được phép nếu không bị pattern cấm khác chặn. Với một endpoint chỉ cho sửa tên và email, viết thẳng `setAllowedFields("displayName", "email")` thường rõ ràng hơn.

Việc disallowed matching không phân biệt chữ hoa giảm một kiểu né tránh đơn giản, nhưng **không bảo vệ các property mới hoặc alias/path chưa liệt kê**. Nếu tự override `isAllowed(...)` trong subclass, cần giữ hợp đồng so khớp và ưu tiên của Spring.

## 4. Ví dụ Java 17+: denylist bỏ sót thuộc tính mới

Chương trình sau minh họa rủi ro cụ thể. Một form có bốn property:

- `displayName`: người dùng được sửa.
- `role` và `admin`: thuộc tính có quyền hạn, được denylist chặn.
- `canExport`: property nhạy cảm **được thêm sau** nhưng denylist không cập nhật.

Ta dùng cùng một tập input để so sánh denylist và allowlist. Ví dụ chạy bằng Java 17+ với Spring Framework 6.2.x; không cần tạo server hoặc database.

Cấu trúc thư mục:

~~~text
binding-policy-demo/
├── pom.xml
└── src/main/java/demo/BindingPolicyDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>binding-policy-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/demo/BindingPolicyDemo.java`:

~~~java
package demo;

import java.util.Arrays;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public final class BindingPolicyDemo {

    public static final class ProfileForm {
        private String displayName = "Guest";
        private String role = "USER";
        private boolean admin;
        private boolean canExport;

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }

        public String getRole() {
            return role;
        }

        public void setRole(String role) {
            this.role = role;
        }

        public boolean isAdmin() {
            return admin;
        }

        public void setAdmin(boolean admin) {
            this.admin = admin;
        }

        public boolean isCanExport() {
            return canExport;
        }

        public void setCanExport(boolean canExport) {
            this.canExport = canExport;
        }
    }

    static MutablePropertyValues request() {
        MutablePropertyValues values = new MutablePropertyValues();
        values.add("displayName", "Lan");
        values.add("role", "ADMIN");
        values.add("admin", "true");
        values.add("canExport", "true");
        return values;
    }

    static String suppressed(BindingResult result) {
        String[] fields = result.getSuppressedFields();
        Arrays.sort(fields);
        return Arrays.toString(fields);
    }

    public static void main(String[] args) {
        ProfileForm denyTarget = new ProfileForm();
        DataBinder deny = new DataBinder(denyTarget, "profile");
        deny.setDisallowedFields("role", "admin");
        deny.bind(request());

        System.out.println("deny.name=" + denyTarget.getDisplayName());
        System.out.println("deny.role=" + denyTarget.getRole());
        System.out.println("deny.admin=" + denyTarget.isAdmin());
        System.out.println("deny.canExport=" + denyTarget.isCanExport());
        System.out.println("deny.suppressed="
                + suppressed(deny.getBindingResult()));
        System.out.println("deny.hasErrors="
                + deny.getBindingResult().hasErrors());

        ProfileForm allowTarget = new ProfileForm();
        DataBinder allow = new DataBinder(allowTarget, "profile");
        allow.setAllowedFields("displayName");
        allow.bind(request());

        System.out.println("allow.name=" + allowTarget.getDisplayName());
        System.out.println("allow.role=" + allowTarget.getRole());
        System.out.println("allow.admin=" + allowTarget.isAdmin());
        System.out.println("allow.canExport=" + allowTarget.isCanExport());
        System.out.println("allow.suppressed="
                + suppressed(allow.getBindingResult()));

        ProfileForm upperTarget = new ProfileForm();
        DataBinder upper = new DataBinder(upperTarget, "profile");
        upper.setDisallowedFields("role");

        MutablePropertyValues upperRequest =
                new MutablePropertyValues();
        upperRequest.add("ROLE", "ADMIN");
        upper.bind(upperRequest);

        System.out.println("uppercase.role=" + upperTarget.getRole());
        System.out.println("uppercase.suppressed="
                + suppressed(upper.getBindingResult()));
    }
}
~~~

Chạy với Maven và JDK 17+:

~~~bash
cd binding-policy-demo
mvn -q compile exec:java -Dexec.mainClass=demo.BindingPolicyDemo
~~~

Những dòng do chương trình in ra:

~~~text
deny.name=Lan
deny.role=USER
deny.admin=false
deny.canExport=true
deny.suppressed=[admin, role]
deny.hasErrors=false
allow.name=Lan
allow.role=USER
allow.admin=false
allow.canExport=false
allow.suppressed=[admin, canExport, role]
uppercase.role=USER
uppercase.suppressed=[ROLE]
~~~

Maven có thể có log riêng tùy môi trường; đoạn trên thể hiện kết quả của `System.out.println` trong mã Java.

**Cách đọc kết quả:**

1. Denylist chặn `role` và `admin`, target giữ giá trị `"USER"` và `false`.
2. `canExport=true` vẫn được gán vì field này không nằm trong denylist. Chỉ thêm một property mới có setter đã làm rộng phạm vi input mà endpoint có thể nhận.
3. `getSuppressedFields()` chứa `admin` và `role` nhưng `hasErrors()` vẫn là `false` vì chúng không tự tạo lỗi binding.
4. Khi dùng allowlist chỉ có `displayName`, cả `role`, `admin` và `canExport` đều bị chặn. Field mới mặc định không được bind.
5. Input viết hoa `ROLE` vẫn bị denylist `role` loại, minh họa quy tắc matching không phân biệt chữ hoa/thường.

Chương trình cố ý dùng form có nhiều setter để thấy cơ chế lọc. **Không nên dùng kiểu form có field quyền hạn như vậy làm DTO nhập liệu thực tế.**

## 5. getSuppressedFields và quyết định xử lý request

Sau `bind(...)`, lấy danh sách bị loại:

~~~java
BindingResult result = binder.getBindingResult();
String[] suppressedFields = result.getSuppressedFields();

if (suppressedFields.length > 0) {
    // Có field bị loại bởi chính sách allowed/disallowed.
}
~~~

Các tên trường trong mảng là thông tin chẩn đoán và kiểm soát input. Chúng không phải danh sách lỗi validation, không chứa mặc định toàn bộ giá trị người dùng đã gửi, và không tự làm request thất bại.

Một chính sách có thể chọn **bỏ qua** field ngoài hợp đồng hoặc **từ chối** request. Với endpoint thay đổi dữ liệu nhạy cảm, việc từ chối input vượt hợp đồng thường giúp phát hiện lỗi client hoặc hành vi không mong muốn. Trường hợp nào chọn cách nào phải được thể hiện rõ trong API contract và kiểm thử.

Ví dụ:

~~~java
if (result.getSuppressedFields().length > 0) {
    throw new IllegalArgumentException("Trường đầu vào không được phép");
}
if (result.hasErrors()) {
    // Báo lỗi chuyển kiểu hoặc validation.
}
~~~

Đây là đoạn code minh họa quy tắc; trong Spring MVC, nếu cần HTTP 400 hãy dùng response/exception mapping phù hợp thay vì mặc định mọi `IllegalArgumentException` sẽ trở thành 400.

Đừng coi `getSuppressedFields().length == 0` là bằng chứng object an toàn. Ví dụ denylist bỏ sót `canExport` nên nó không bị suppressed, trong khi việc bind nó lại là điều không mong muốn.

## 6. @ModelAttribute và @InitBinder trong Spring MVC

Khi xử lý form hoặc query parameters bằng `@ModelAttribute`, Spring MVC sử dụng `WebDataBinder`. Có thể thiết lập disallowed fields thông qua `@InitBinder`:

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@Controller
class ProfileController {

    @InitBinder("profile")
    void configure(WebDataBinder binder) {
        binder.setDisallowedFields("role", "admin");
    }

    // Một handler nhận @ModelAttribute("profile") ...
}
~~~

Tên `"profile"` định hướng cấu hình tới model attribute tương ứng; không tự áp dụng cho mọi handler, mọi model attribute hoặc mọi cơ chế nhập dữ liệu.

Một cấu hình ưu tiên an toàn hơn:

~~~java
@InitBinder("profile")
void configure(WebDataBinder binder) {
    binder.setAllowedFields("displayName");
}
~~~

Với endpoint thực tế, nên dùng **form DTO riêng** cho use case, ví dụ:

~~~java
import jakarta.validation.constraints.NotBlank;

public class ChangeDisplayNameForm {
    @NotBlank
    private String displayName;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
~~~

DTO này không có `role` hoặc `admin` để bind. Khi model thật của hệ thống thêm field nội bộ, API đổi tên hiển thị không tự mở rộng theo.

### Kiểm tra riêng suppressed và lỗi khác trong handler

~~~java
import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.server.ResponseStatusException;

@Controller
class ChangeDisplayNameController {

    private final ProfileService service;

    ChangeDisplayNameController(ProfileService service) {
        this.service = service;
    }

    @InitBinder("profile")
    void configure(WebDataBinder binder) {
        binder.setAllowedFields("displayName");
    }

    @PostMapping("/profile/display-name")
    String submit(
            @Valid @ModelAttribute("profile") ChangeDisplayNameForm form,
            BindingResult errors) {

        if (errors.getSuppressedFields().length > 0) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Field không được phép");
        }
        if (errors.hasErrors()) {
            return "profile/edit";
        }

        service.changeDisplayName(form.getDisplayName());
        return "redirect:/profile";
    }
}
~~~

Đây là **mã tích hợp**, không phải chương trình có thể chạy độc lập với `javac`: dự án cần có `ProfileService`, view, Spring MVC và Bean Validation provider. Nếu bảo vệ CSRF được bật, form thực tế còn cần CSRF token.

Chú ý `BindingResult` đứng **ngay sau** `@ModelAttribute` tương ứng. Nhánh nghiệp vụ chỉ chạy khi không có field bị suppressed và không có lỗi binding/validation. Service còn phải xác minh người gọi được phép sửa profile cụ thể.

## 7. Giới hạn quan trọng: JSON @RequestBody

Denylist của `WebDataBinder` dành cho **property binding** và không được xem là bộ lọc JSON cho mọi endpoint.

~~~java
@PostMapping("/profile")
void update(@RequestBody ProfileRequest request) {
    // HTTP message conversion, thường qua Jackson.
}
~~~

Với `@RequestBody`, JSON được deserialize qua `HttpMessageConverter`, thường dùng Jackson. Cấu hình `setDisallowedFields` của WebDataBinder **không trực tiếp kiểm soát các thuộc tính được Jackson đọc từ JSON** như một danh sách cấm toàn cục.

Với JSON, hãy dùng DTO chỉ khai báo những field mà API chấp nhận, cấu hình cách xử lý unknown fields theo hợp đồng, dùng validation và kiểm soát mapping/authorization tại service. Nếu cần từ chối JSON chứa property lạ, đó là một chính sách deserialization riêng, không phải `getSuppressedFields()` của `@ModelAttribute`.

## 8. Giới hạn quan trọng: constructor binding

Spring Framework hỗ trợ hai hướng chính:

- **Constructor binding**: tạo object thông qua constructor và các argument cần thiết.
- **Property binding**: gán các property bằng setter/field access sau khi đã có object.

`setDisallowedFields` kiểm soát danh sách field cho **property binding**. Nó **không phải danh sách cấm chung cho các argument trong `DataBinder.construct(...)`**. DTO immutable có constructor chỉ chứa đầu vào cần thiết là một ranh giới phù hợp hơn.

Ở Spring Framework 6.2, có thể cấu hình `setDeclarativeBinding(true)` để property binding chỉ hoạt động khi có allowed fields, trong khi constructor binding vẫn được hỗ trợ:

~~~java
@InitBinder
void configure(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
~~~

Cần áp dụng theo phiên bản Spring và thiết kế object thực tế. Cấu hình này không thay thế Bean Validation, kiểm tra quyền, hoặc bảo vệ cơ chế JSON do Jackson thực hiện.

## 9. Các giới hạn bảo mật và bảo trì của danh sách loại trừ

### 9.1. Thêm field mới vào model

Một lớp lúc đầu chỉ có `displayName`, `role` và `admin`; denylist có `"role", "admin"`. Khi lập trình viên thêm `canExport` mà không rà soát mọi endpoint dùng lớp, field mới có thể bind được. Cấu hình ban đầu không thay đổi nhưng phạm vi dữ liệu nhận từ bên ngoài đã tăng.

Vì vậy nên tránh chia sẻ trực tiếp entity hoặc model nội bộ làm command object cho nhiều endpoint với các quyền sửa khác nhau.

### 9.2. Nested property và collection

Denylist `"role"` không mặc nhiên chặn các đường dẫn như:

~~~text
account.role
items[0].role
items[1].role
metadata[role]
~~~

Với object graph có những property này, cần xem từng path và pattern phù hợp. Cố dùng wildcard rộng như `"*role*"` có thể chặn nhầm field khác. Cách ít sai sót hơn là chỉ định đầu vào được phép và giới hạn kiểu DTO lồng nhau.

### 9.3. Chọn sai vị trí @InitBinder

Một `@InitBinder("profile")` không tự cấu hình mọi attribute có tên khác, cũng không tự thay đổi cơ chế JSON. Khi rà soát một endpoint, cần xác minh data thực sự đi qua binder đã được cấu hình. Đừng cho rằng chỉ có phương thức trong controller là đủ chứng minh chính sách đang áp dụng.

### 9.4. Khác biệt giữa “field được phép bind” và “được phép chỉnh sửa resource”

Dù `displayName` nằm trong allowlist, client vẫn không được sửa tài khoản của người khác. Authorization phụ thuộc người gọi, resource, trạng thái và nghiệp vụ. Nó phải được kiểm tra ở service hoặc lớp bảo mật, **không thể suy ra từ tên field**.

### 9.5. Kiểm soát tài nguyên

Property paths có thể gồm nested objects hoặc collection indexes. Nếu cần bind danh sách, giới hạn auto-grow, độ sâu đối tượng và kích thước request. Ví dụ:

~~~java
binder.setAllowedFields("items[*].name", "items[*].quantity");
binder.setAutoGrowCollectionLimit(20);
~~~

`setAutoGrowCollectionLimit` hữu ích để giảm nguy cơ tạo collection quá lớn qua indexed property path; nó không thay cho validation số dòng hoặc chống mọi tác động của object graph phức tạp.

### 9.6. Log thông tin bị chặn

`getSuppressedFields()` cho biết **tên**, không mặc định là nội dung field. Không nên log nguyên request hoặc rejected values nhạy cảm chỉ để kiểm tra denylist; áp dụng giới hạn số lượng, độ dài và redaction khi ghi log.

## 10. So sánh các tùy chọn DataBinder liên quan

| API hoặc cấu hình | Mục đích | Khác biệt cần nhớ |
|---|---|---|
| `setDisallowedFields` | Loại những property path nằm trong denylist | Field mới không tự bị chặn |
| `setAllowedFields` | Chỉ nhận các property path trong allowlist | An toàn hơn khi target có property mới |
| `getSuppressedFields` | Lấy tên các field bị loại | Không tự sinh FieldError/HTTP 400 |
| `getFieldErrors` và `hasErrors` | Kiểm tra lỗi binding/validation | Không thay thế suppressed checks |
| `setRequiredFields` | Quy định field nào cần có trong input | Không quyết định field được người dùng sửa |
| `setIgnoreUnknownFields` | Xử lý tên property không tồn tại | Unknown field khác với suppressed field |
| `setIgnoreInvalidFields` | Xử lý một số nested path không truy cập được | Không phải chính sách quyền |
| `setAutoGrowNestedPaths` | Tạo nested object/collection khi có thể | Có thể làm tăng bề mặt property path |
| `setAutoGrowCollectionLimit` | Giới hạn collection tự mở rộng | Không thay cho hạn mức nghiệp vụ |
| `setDeclarativeBinding(true)` | Hạn chế setter binding theo allowed fields | Không phải bộ lọc JSON hoặc authorization |

Một field có thể được phép bind nhưng giá trị sai kiểu, tạo `FieldError`. Một field khác bị denylist chặn hoàn toàn có thể không tạo lỗi nào. Trường thứ ba có thể không tồn tại và bị bỏ qua theo cấu hình unknown fields. Ba tình huống phải được phân biệt trong xử lý request và trong test.

## 11. Những lỗi thường gặp

**Lỗi 1: Chỉ đặt denylist rồi coi endpoint đã an toàn.** Denylist dễ bỏ sót field mới hoặc nested path. Ưu tiên DTO riêng và allowlist.

**Lỗi 2: Chỉ gọi `hasErrors()`.** Field bị suppressed có thể không tạo binding error, như kết quả `deny.hasErrors=false` trong ví dụ. Nếu muốn từ chối field ngoài hợp đồng, phải kiểm tra `getSuppressedFields()`.

**Lỗi 3: Nhầm `"role"` với mọi đường dẫn role.** `account.role` hoặc `items[0].role` là các tên field khác. Xác minh mô hình nested và pattern bằng test.

**Lỗi 4: Dùng wildcard như regex.** `*` là wildcard của Spring simple matching, không phải biểu thức regex. Pattern quá rộng còn có thể chặn nhầm.

**Lỗi 5: Không phân biệt hoa/thường.** Trong Spring 6.x, disallowed matching không phân biệt hoa/thường, allowed matching có phân biệt. Đừng tự viết lại quy tắc khác nếu không có lý do.

**Lỗi 6: Nghĩ @InitBinder chặn JSON @RequestBody.** Deserialization JSON đi qua HTTP message converter; cần DTO và chính sách JSON riêng.

**Lỗi 7: Cho request bind trực tiếp entity JPA/Hibernate.** Entity có thể có ID, owner, status và quan hệ nội bộ; việc thêm setter vô tình mở rộng bề mặt nhập liệu. Dùng input DTO và mapping có kiểm soát.

**Lỗi 8: Quên kiểm tra quyền.** Tên field được bind không chứng minh người dùng có quyền thay đổi bản ghi tương ứng. Service cần authorization rõ ràng.

**Lỗi 9: Ghi log mọi giá trị bị từ chối.** Một field có thể chứa token, password hoặc thông tin cá nhân; log tối thiểu và tránh đưa input nhạy cảm vào response.

## 12. Kiểm thử nên thực hiện

| Đầu vào và cấu hình | Điều cần kiểm tra |
|---|---|
| `displayName=Lan` | Bind tên thành công |
| Deny `role`, gửi `role=ADMIN` | Target role không đổi, field xuất hiện trong suppressed |
| Deny `role`, gửi `ROLE=ADMIN` | Matching không phân biệt hoa/thường |
| Deny `role,admin`, gửi `canExport=true` | Field mới có thể lọt nếu không có trong denylist |
| Allow `displayName`, gửi `canExport=true` | Field mới bị suppressed |
| Field đồng thời nằm trong allowed và disallowed | Disallowed ưu tiên |
| Field bị suppressed nhưng không sai kiểu | `hasErrors()` có thể vẫn `false` |
| Field được phép, gửi `age=abc` cho `Integer` | Binding error riêng, không nhầm với suppressed |
| Nested `items[0].ownerId` | Đúng pattern cấm và không sửa field do server quản lý |
| JSON `@RequestBody` có field ngoài hợp đồng | Chính sách Jackson/DTO xử lý riêng |
| Người dùng sửa resource không có quyền | Service từ chối dù field hợp lệ |
| Input ngoài hợp đồng bị từ chối | Không gọi thao tác ghi dữ liệu |

Trong test, `getSuppressedFields()` không nên được kiểm tra theo thứ tự sẵn có; có thể sort hoặc so khớp như một tập hợp. Nên có test hồi quy khi thêm field mới vào model, vì đó là tình huống dễ khiến denylist trở nên thiếu.

Ví dụ assertion khi đặt trong một test có các kiểu của chương trình ở mục 4:

~~~java
ProfileForm form = new ProfileForm();
DataBinder binder = new DataBinder(form, "profile");
binder.setDisallowedFields("role");

MutablePropertyValues values = new MutablePropertyValues();
values.add("role", "ADMIN");
binder.bind(values);

boolean unchanged = "USER".equals(form.getRole());
boolean suppressed = java.util.Arrays.asList(
        binder.getBindingResult().getSuppressedFields()).contains("role");

if (!unchanged || !suppressed) {
    throw new AssertionError("Role không được chặn đúng");
}
~~~

Đoạn này minh họa assertion trong môi trường test đã có imports và `ProfileForm`; nếu dùng JUnit có thể thay bằng các assertion của thư viện đó.

## 13. Cách lựa chọn trong dự án

Để thiết kế an toàn một endpoint nhận dữ liệu từ client:

1. Xác định **đúng tập property client được phép gửi** theo use case; tạo request DTO riêng.
2. Với `@ModelAttribute` và setter/property binding, ưu tiên `setAllowedFields(...)`.
3. Khi phù hợp, dùng DTO bất biến và constructor binding, cân nhắc `setDeclarativeBinding(true)` theo phiên bản Spring.
4. Nếu phải dùng `setDisallowedFields` vì tương thích hoặc chính sách bổ sung, hãy test field mới, nested paths, wildcard, case sensitivity và mức ưu tiên với allowlist.
5. Kiểm tra riêng `getSuppressedFields()` và `hasErrors()` nếu hợp đồng yêu cầu phát hiện input ngoài phạm vi.
6. Với `@RequestBody` JSON, sử dụng cơ chế DTO/deserialization riêng.
7. Tầng service xác minh quyền, business invariants và chỉ gán những thuộc tính được phép lên entity.
8. Áp dụng giới hạn request size, collection auto-grow và log an toàn.

**Ý chính:** `setDisallowedFields` trả lời câu hỏi “đã biết những field nào cần cấm?”. Đây là lớp bảo vệ có ích, nhưng một input contract thường dễ kiểm soát hơn khi trả lời rõ “chỉ những field nào được phép nhận?” bằng DTO và `setAllowedFields`.

### Tài liệu chính thức để tra cứu

- Spring Framework Reference — Web MVC, `@InitBinder` và Model Design.
- Spring Framework Reference — Core Technologies, Validation và Data Binding.
- Spring Framework Javadoc — `DataBinder#setDisallowedFields`, `DataBinder#setAllowedFields`, `DataBinder#isAllowed`.
- Spring Framework Javadoc — `BindingResult#getSuppressedFields`.
