# `setDeclarativeBinding`: kiểm soát ý định data binding trong Spring

## 1. Vấn đề: dữ liệu request không phải mọi thuộc tính đều được phép gán

Khi Spring MVC nhận dữ liệu từ một form hoặc query parameter, framework có thể ánh xạ các cặp tên–giá trị lên JavaBean thông qua **data binding**. Nếu đối tượng có setter `setAdmin(boolean)` hoặc `setRole(String)`, client có thể thử gửi các tham số `admin=true` hay `role=ADMIN` ngay cả khi giao diện HTML không hiển thị các trường đó.

Ví dụ một request giả định:

~~~http
POST /profiles
Content-Type: application/x-www-form-urlencoded

displayName=Lan&admin=true&role=ADMIN
~~~

Vấn đề không nằm ở nút bấm hay việc ẩn input trong HTML: **client có thể tự tạo request**. Nếu Spring bind thẳng dữ liệu không tin cậy vào một đối tượng có các property nhạy cảm, các giá trị ngoài ý định người thiết kế có thể bị thay đổi. Đây là dạng rủi ro thường gọi là **mass assignment** hoặc **over-posting**.

Từ **Spring Framework 6.1**, `org.springframework.validation.DataBinder` có API:

~~~java
binder.setDeclarativeBinding(true);
~~~

Cờ `declarativeBinding` giúp áp dụng binding theo nguyên tắc **chỉ những đầu vào được khai báo có chủ đích mới được đưa vào đối tượng**: constructor binding được dùng khi luồng tạo đối tượng gọi nó, còn property/setter binding chỉ thực hiện khi danh sách `allowedFields` đã được cấu hình. Đây là điểm khác biệt quan trọng so với kiểu bind rộng vào các setter mặc định.

**Ý chính:** `setDeclarativeBinding(true)` không phải một annotation validation, không xác thực người dùng, không cấp quyền và không tự loại bỏ mọi lỗ hổng bảo mật. Nó điều chỉnh **phạm vi gán giá trị** ở tầng data binding; authorization vẫn phải được kiểm tra ở tầng nghiệp vụ.

## 2. Hai cách binding mà Spring hỗ trợ

Spring phân biệt hai cơ chế:

| Cơ chế | Dữ liệu nào được dùng? | Đối tượng chịu tác động | Cách kiểm soát |
| --- | --- | --- | --- |
| **Constructor binding** | Các tham số trùng tên tham số constructor (hoặc theo cơ chế đặt tên được cấu hình) | Tạo đối tượng từ constructor/record | Thiết kế constructor/DTO chỉ nhận trường đầu vào dự kiến |
| **Property binding** (setter binding) | Các tên property có thể ghi như `displayName`, `role`, `address.city` | Gán lên JavaBean đã tồn tại | `setAllowedFields(...)` hoặc cơ chế hạn chế tương đương |

Ví dụ constructor binding với Java 17 record:

~~~java
public record ChangeEmailRequest(String oldEmail, String newEmail) {}
~~~

Nếu Spring MVC tạo record này bằng constructor, các tham số được dùng để tạo nó là `oldEmail` và `newEmail`. Các tham số `admin`, `role` của request không tự xuất hiện trong record chỉ vì client gửi thêm chúng.

Ngược lại, JavaBean mutable có thể có nhiều setter phục vụ các luồng khác nhau:

~~~java
public class UserAccount {
    private String displayName;
    private boolean admin;

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String name) { displayName = name; }

    public boolean isAdmin() { return admin; }
    public void setAdmin(boolean admin) { this.admin = admin; }
}
~~~

Nếu bind toàn bộ property không hạn chế, `admin=true` có thể gọi được setter tương ứng. Thực tế nên **không** dùng trực tiếp entity JPA/domain có nhiều property nội bộ làm `@ModelAttribute` cho form công khai.

Trong Spring MVC, thông thường luồng `@ModelAttribute` có thể thực hiện **cả constructor binding lẫn property binding**. Vì vậy một record/DTO chỉ khai báo trường cần nhập thường là phương án an toàn và dễ kiểm soát hơn một object domain có nhiều setter.

## 3. `setDeclarativeBinding(true)` thay đổi quy tắc gì?

Cấu hình mặc định của `DataBinder` cho `declarativeBinding` là `false`. Khi bật `true`, hành vi có thể tóm tắt như sau:

| Cấu hình | Constructor binding | Property/setter binding |
| --- | --- | --- |
| `declarativeBinding=false`, chưa gọi `setAllowedFields` | Được hỗ trợ khi cơ chế tạo object sử dụng constructor binding | Có thể bind các property có thể ghi phù hợp dữ liệu đầu vào |
| `declarativeBinding=false`, có `setAllowedFields("displayName")` | Được hỗ trợ | Chỉ các property khớp allowlist |
| `declarativeBinding=true`, **không có** `setAllowedFields` | Vẫn được hỗ trợ khi luồng gọi constructor binding | **Không thực hiện** property binding |
| `declarativeBinding=true`, có `setAllowedFields("displayName")` | Vẫn được hỗ trợ | **Chỉ** property `displayName` (và các đường dẫn khớp cấu hình) được bind |

Ý nghĩa của API:

~~~java
DataBinder binder = new DataBinder(existingObject);
binder.setDeclarativeBinding(true);
~~~

Trong ví dụ trên, `existingObject` đã được tạo trước khi constructor của `DataBinder` được gọi. Vì vậy, khi sau đó gọi `binder.bind(propertyValues)`, **bạn đang thử property binding**, không phải tự động kích hoạt constructor binding. Khi chưa cấu hình `allowedFields`, binder bỏ qua bước property binding.

Để cho phép một tập nhỏ property:

~~~java
binder.setDeclarativeBinding(true);
binder.setAllowedFields("displayName", "timeZone");
binder.bind(propertyValues);
~~~

Lúc này `displayName` và `timeZone` được phép gán nếu các property tồn tại và có thể ghi. Các tham số khác như `admin` hay `role` không nằm trong allowlist nên không được gán bằng property binding.

Cần phân biệt rõ hai điều:

1. **Bật declarative binding** không có nghĩa chỉ các field xuất hiện trong HTML được phép bind. HTML là thông tin client có thể thay đổi; danh sách được phép phải nằm trong **cấu hình phía server** hoặc chữ ký constructor.
2. **Bật declarative binding** không có nghĩa framework tự suy ra một allowlist thông minh từ tên form. Nếu muốn dùng setter binding, bạn phải **chỉ định rõ `setAllowedFields`**.

## 4. Ví dụ Java 17+ có thể chạy: ba tình huống cùng một request

Ví dụ dưới đây tái hiện dữ liệu gửi từ client và so sánh ba cách cấu hình `DataBinder`:

- Mặc định không giới hạn setter.
- Bật declarative binding nhưng không khai báo allowlist.
- Bật declarative binding và chỉ cho phép `displayName`.

Dùng **Spring Framework 6.2.x**, Java 17+. Đặt toàn bộ mã sau vào file `src/main/java/DeclarativeBindingDemo.java` trong dự án Maven có dependency `spring-context`.

~~~java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

public final class DeclarativeBindingDemo {

    public static class AccountForm {
        private String displayName;
        private boolean admin;
        private String role = "USER";

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }

        public boolean isAdmin() {
            return admin;
        }

        public void setAdmin(boolean admin) {
            this.admin = admin;
        }

        public String getRole() {
            return role;
        }

        public void setRole(String role) {
            this.role = role;
        }
    }

    private static MutablePropertyValues input() {
        MutablePropertyValues values = new MutablePropertyValues();
        values.add("displayName", "Lan");
        values.add("admin", "true");
        values.add("role", "ADMIN");
        return values;
    }

    private static void show(String label, AccountForm form) {
        System.out.println(label
                + ": name=" + form.getDisplayName()
                + ", admin=" + form.isAdmin()
                + ", role=" + form.getRole());
    }

    public static void main(String[] args) {

        // Trường hợp 1: property binding mặc định.
        AccountForm defaultForm = new AccountForm();
        DataBinder defaultBinder =
                new DataBinder(defaultForm, "accountForm");
        defaultBinder.bind(input());
        show("default", defaultForm);

        // Trường hợp 2: bật declarative binding,
        // không cấu hình allowedFields.
        AccountForm strictForm = new AccountForm();
        DataBinder strictBinder =
                new DataBinder(strictForm, "accountForm");
        strictBinder.setDeclarativeBinding(true);
        strictBinder.bind(input());
        show("declarativeOnly", strictForm);

        // Trường hợp 3: cho phép đúng displayName.
        AccountForm allowedForm = new AccountForm();
        DataBinder allowedBinder =
                new DataBinder(allowedForm, "accountForm");
        allowedBinder.setDeclarativeBinding(true);
        allowedBinder.setAllowedFields("displayName");
        allowedBinder.bind(input());
        show("allowedName", allowedForm);
    }
}
~~~

Tạo `pom.xml` mẫu dưới đây ở gốc project:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>declarative-binding-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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
~~~

Chạy với JDK 17+ và Maven:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=DeclarativeBindingDemo
~~~

Kết quả chuẩn từ đoạn Java đã cho:

~~~text
default: name=Lan, admin=true, role=ADMIN
declarativeOnly: name=null, admin=false, role=USER
allowedName: name=Lan, admin=false, role=USER
~~~

Giải thích:

1. **`default`:** `DataBinder` thực hiện property binding đến tất cả setter khớp; `displayName`, `admin` và `role` được gán. Trường hợp này cho thấy nguy cơ nếu object có các setter không dành cho client.
2. **`declarativeOnly`:** cờ `true` không có `allowedFields` khiến `bind(...)` không gán property nào trên **object đã tồn tại**. `displayName` vẫn là `null`, `admin` vẫn là `false`, `role` vẫn là `"USER"`.
3. **`allowedName`:** declarative binding có allowlist `displayName`, nên tên thay đổi thành `Lan`; hai field `admin`/`role` không thay đổi.

Đây là chương trình Java hoàn chỉnh trong **một file** nhưng cần thư viện Spring trên classpath; `javac DeclarativeBindingDemo.java` độc lập không biên dịch được nếu chưa thêm dependencies.

**Điểm thường bị hiểu sai:** Trường hợp `declarativeOnly` không phải minh chứng rằng constructor binding đã chạy. Trong code, ba `AccountForm` đều được tạo bằng `new AccountForm()` **trước** khi binder nhận dữ liệu. Ví dụ này chỉ minh họa ảnh hưởng lên property binding. Luồng constructor binding thật được trình bày ở phần kế tiếp.

## 5. Constructor binding vẫn được phép

Đối với đối tượng được tạo từ constructor/record, có thể để Spring MVC đọc đúng các tham số mà constructor khai báo:

~~~java
public record ChangeEmailInput(
        String oldEmail,
        String newEmail) {
}
~~~

Trong controller Spring MVC, một cấu hình rõ ràng là:

~~~java
@Controller
class ChangeEmailController {

    @InitBinder("changeEmailInput")
    void configure(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }

    @PostMapping("/email/change")
    String changeEmail(
            @ModelAttribute("changeEmailInput") ChangeEmailInput input,
            BindingResult bindingResult) {

        if (bindingResult.hasErrors()) {
            return "change-email-form";
        }

        // Service sẽ xác thực chủ thể, kiểm tra email cũ,
        // thực hiện authorization, validation và cập nhật.
        return "redirect:/email/change/success";
    }
}
~~~

Đây là **đoạn tích hợp Spring MVC**, không phải một chương trình standalone. Cần imports `org.springframework.stereotype.Controller`, `org.springframework.web.bind.annotation.InitBinder`, `org.springframework.web.bind.annotation.PostMapping`, `org.springframework.web.bind.annotation.ModelAttribute`, `org.springframework.web.bind.WebDataBinder` và `org.springframework.validation.BindingResult`; ứng dụng cần Spring MVC và view/template tương ứng.

Trong luồng `@ModelAttribute`, Spring có thể dùng constructor `ChangeEmailInput(String oldEmail, String newEmail)` để tạo record theo dữ liệu request. Dù client gửi `admin=true` hoặc `role=ADMIN`, record này **không có tham số constructor cho chúng** và không có setter tương ứng. Bật declarative binding không cản trở constructor binding, đồng thời tránh property binding ngoài ý định.

Để Spring đọc đúng tên tham số constructor của **class Java thông thường**, hãy biên dịch với khả năng giữ tên tham số (thường thông qua `-parameters`) theo yêu cầu framework/cấu hình build. Với record, tên record component được lưu trong metadata thích hợp. Khi tên tham số HTTP khác tên constructor, có thể dùng `@BindParam` của Spring trên tham số/field ở phiên bản hỗ trợ:

~~~java
public record ChangeEmailInput(
        @BindParam("old-email") String oldEmail,
        @BindParam("new-email") String newEmail) {
}
~~~

`@BindParam` ở ví dụ trên thuộc `org.springframework.web.bind.annotation.BindParam`. Đây là snippet riêng minh họa ánh xạ tên; không khai báo cả hai phiên bản record cùng tên trong một project.

**Không hiểu nhầm constructor binding là an toàn tuyệt đối.** Nếu constructor của object lại chứa `boolean admin` hoặc `String role`, thì đó là **đầu vào đã được khai báo** và có thể bị bind từ request. Vì vậy constructor/record/DTO phải **chỉ khai báo những giá trị client thực sự được phép cung cấp**.

## 6. Khi nào cần `setAllowedFields` cùng `setDeclarativeBinding`?

Một form mutable thường phải nhận một số property qua setter:

~~~java
public class ProfileForm {
    private String displayName;
    private String timeZone;
    private boolean admin;

    // Constructors, getters, setters...
}
~~~

Giả sử chỉ `displayName` và `timeZone` là dữ liệu cho phép người dùng sửa. Cấu hình tại controller:

~~~java
@Controller
class ProfileController {

    @InitBinder("profileForm")
    void initProfileBinder(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
        binder.setAllowedFields("displayName", "timeZone");
    }

    @PostMapping("/profile")
    String update(
            @ModelAttribute("profileForm") ProfileForm form,
            BindingResult bindingResult) {

        if (bindingResult.hasErrors()) {
            return "profile-form";
        }
        // Ánh xạ thủ công dữ liệu được phép sang domain entity,
        // kèm kiểm tra quyền và quy tắc nghiệp vụ.
        return "redirect:/profile";
    }
}
~~~

Đây là snippet minh họa cấu hình Spring MVC: `ProfileForm` cần khai báo đầy đủ getters/setters thực tế; view và service không được bao gồm. `@InitBinder("profileForm")` chỉ áp dụng cho model attribute tên `profileForm` trong controller này; tên phải thống nhất với `@ModelAttribute("profileForm")`.

Khi đó:

| Tham số request | Hành vi setter binding |
| --- | --- |
| `displayName=Lan` | Được phép |
| `timeZone=Asia/Ho_Chi_Minh` | Được phép |
| `admin=true` | Không được gán bằng property binding |
| `role=ADMIN` | Không được gán bằng property binding |

Đặt allowlist theo **đường dẫn property JavaBean**, không dựa trên nhãn hiển thị form. Nếu property là nested field, đường dẫn có thể là `address.city` hoặc `addresses[0].city`. Các pattern `*` cũng được hỗ trợ nhưng nên dùng tiết chế: `address*` có thể cho phép nhiều thuộc tính bên dưới hơn dự định. Ưu tiên tên field chính xác khi có thể.

Hãy lưu ý:

- `allowedFields` áp dụng cho **property binding**. Nó không phải danh sách whitelist của các **constructor arguments**; constructor sử dụng các tham số mà constructor yêu cầu.
- Allowlist nên bao gồm những field thật sự có thể được client cập nhật, không bao gồm khóa định danh, quyền, vai trò, số dư hoặc trạng thái do server quyết định chỉ vì object có setter.
- Nếu mục tiêu là tạo một object mới đơn giản, DTO/record constructor-only có thể dễ kiểm soát hơn phối hợp nhiều setter.
- Nếu phải dùng domain entity có quan hệ và nested object phức tạp, hãy tránh bind trực tiếp nếu không kiểm soát được toàn bộ đường dẫn và danh sách property.

## 7. Cấu hình phạm vi: `@InitBinder` trong controller hay `@ControllerAdvice`?

### Cấu hình cục bộ

~~~java
@Controller
class OrderController {

    @InitBinder
    void initBinder(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
~~~

Mẫu này áp dụng cho các binder thuộc controller. Nó phù hợp nếu bạn muốn quản lý quy tắc cho từng controller, đặc biệt khi có nhiều loại form với chính sách khác nhau.

### Cấu hình dùng chung

~~~java
@ControllerAdvice
class GlobalBindingPolicy {

    @InitBinder
    void initBinder(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
~~~

`@ControllerAdvice` thuộc `org.springframework.web.bind.annotation.ControllerAdvice`. Khi dùng chung, cấu hình có thể áp dụng rộng cho nhiều annotated controller, hoặc thu hẹp phạm vi bằng selector của `@ControllerAdvice`.

Một cấu hình toàn cục tạo ra **thay đổi hành vi đáng kể**: các form mutable phụ thuộc setter binding trước đó có thể ngừng nhận input nếu không có `allowedFields` tương ứng. Do đó, nên:

1. Kiểm kê các endpoint có `@ModelAttribute`.
2. Xác định loại object nào đã dùng constructor binding và loại nào cần setter binding.
3. Chuyển các form thích hợp sang DTO/record có constructor rõ ràng.
4. Cấu hình allowlist cho những object buộc phải nhận dữ liệu bằng setter.
5. Chạy lại integration test cho các request hợp lệ và request gửi thêm field không mong muốn.

Bật cờ global không phải thao tác an toàn theo kiểu “thêm một dòng là xong”; nó cần kiểm chứng hành vi của các form cũ.

## 8. Khác gì với `setAllowedFields`, `setDisallowedFields` và `@ModelAttribute(binding=false)`?

| Công cụ | Phạm vi ảnh hưởng | Điểm khác biệt |
| --- | --- | --- |
| `setDeclarativeBinding(true)` | Chiến lược data binding trên binder | Constructor binding vẫn được sử dụng khi có; chỉ thực hiện property binding nếu có allowlist |
| `setAllowedFields("a", "b")` | Tập field cho property binding | Cho phép các property path khớp danh sách; có tác dụng kiểm soát setter binding dù không bật declarative |
| `setDisallowedFields("admin")` | Các field bị chặn trong property binding | Blacklist dễ thiếu field khi mô hình phát triển; không phải chiến lược ưu tiên |
| `@ModelAttribute(binding=false)` | Tham số model attribute cụ thể | Không thực hiện binding request vào attribute đó theo chỉ định, khác với cho phép constructor binding kèm setter allowlist |
| `@Valid` / `@Validated` | Validation sau binding | Kiểm tra ràng buộc, **không** quyết định các field nào được phép setter binding |
| Phân quyền trong service/security layer | Trách nhiệm người gọi và thao tác nghiệp vụ | Quyết định user có được sửa dữ liệu không, **không** thay bằng danh sách field bind |

**`setAllowedFields` không phải mới xuất hiện cùng `setDeclarativeBinding`.** Trước Spring 6.1, bạn đã có thể cấu hình allowlist để giới hạn property binding. Điểm thêm của declarative binding là **mặc định không thực hiện property binding nếu chưa khai báo allowlist**, giúp tránh vô tình mở rộng phạm vi vì quên cấu hình tại một binder.

`setDisallowedFields` là cơ chế denylist. Rủi ro là khi model có thêm các field nhạy cảm, denylist cũ không tự biết để thêm tên field mới. Spring hiện ưu tiên constructor binding, input DTO riêng hoặc `allowedFields` vì các phương án này thể hiện ý định rõ ràng hơn.

**`@ModelAttribute(binding=false)` không đồng nghĩa với `setDeclarativeBinding(true)`.** Nếu model attribute đã được truy xuất từ model/session và bạn không muốn request thay đổi nó, `binding=false` có thể thích hợp; trong khi declarative binding điều chỉnh cách binder chấp nhận trường trong một luồng binding được phép.

## 9. Những điều `declarativeBinding` không làm

Để tránh cảm giác an toàn sai, cần xác định ranh giới của tính năng.

### Không tự thực hiện validation

Một field được phép bind nhưng có giá trị sai kiểu, ví dụ `age=abc` cho `Integer age`, có thể tạo lỗi chuyển kiểu trong `BindingResult`. Giá trị đúng kiểu nhưng vi phạm quy tắc như `age=16` khi cần >=18 phải có validator hoặc Jakarta Bean Validation tương ứng.

~~~java
@PostMapping("/profile")
String submit(@Valid @ModelAttribute("profileForm") ProfileForm form,
              BindingResult errors) {
    if (errors.hasErrors()) {
        return "profile-form";
    }
    return "redirect:/profile";
}
~~~

Snippet cần Jakarta Validation provider cho các constraint `@NotBlank`, `@Min`... nếu muốn kiểm tra chúng. `@Valid` không tự là allowlist; nó chỉ khởi chạy cơ chế kiểm tra phù hợp.

### Không xác thực hoặc phân quyền

Ngay cả khi input chỉ có `displayName`, người dùng A không được tự thay đổi hồ sơ người dùng B. Service vẫn phải tìm đối tượng bằng định danh từ nguồn tin cậy, kiểm tra người dùng hiện tại và quyền thao tác, rồi áp dụng những cập nhật được phép.

Không dùng `setDeclarativeBinding(true)` để thay thế `@PreAuthorize`, policy trong service hoặc kiểm tra resource ownership. Ngược lại, `@PreAuthorize` cũng không mặc định ngăn binder gán property không dự kiến; hai lớp bảo vệ giải quyết các vấn đề khác nhau.

### Không tự biến request JSON thành property binding của `DataBinder`

Với `@RequestBody`, payload JSON thường được giải mã bởi `HttpMessageConverter`/Jackson để tạo object, theo cơ chế khác với `@ModelAttribute`. `WebDataBinder.setDeclarativeBinding(true)` **không phải** bộ lọc thuộc tính JSON tổng quát cho mọi endpoint.

Vì vậy:

~~~java
@PostMapping("/users")
ResponseEntity<Void> create(@RequestBody CreateUserRequest request) {
    // DTO JSON phải được thiết kế và xác thực riêng.
    return ResponseEntity.ok().build();
}
~~~

Đây là snippet cho request body, không phải ví dụ áp dụng `declarativeBinding`. Khi muốn kiểm soát JSON, dùng DTO chỉ chứa trường client được phép cung cấp, cấu hình Jackson phù hợp, validation và phân quyền ở service.

### Không tự báo HTTP 400 cho mọi trường bị bỏ qua

Trong property binding có allowlist, `BindingResult.getSuppressedFields()` có thể cho biết các field đã bị bỏ qua do cấu hình allowed/disallowed. Nhưng **không nên dựa vào nó như một nhật ký an ninh đầy đủ**, nhất là khi declarative binding không có allowlist khiến bước property binding bị bỏ qua toàn bộ.

Nếu chính sách API yêu cầu từ chối request có field lạ hoặc trường bị chặn, cần chủ động kiểm tra input/contract và quyết định status hoặc validation response. Mặc định việc bỏ qua property không phải lúc nào cũng là lỗi trong `BindingResult.hasErrors()`.

## 10. `BindingResult`, suppressed fields và các ngoại lệ

Khi property binding thực sự diễn ra với allowlist, các field không khớp có thể được ghi vào danh sách **suppressed fields**:

~~~java
BindingResult result = binder.getBindingResult();

if (result.getSuppressedFields().length > 0) {
    // Có property names đã bị loại khỏi phép bind.
    // Tùy chính sách, ghi log an toàn hoặc từ chối request.
}

if (result.hasErrors()) {
    // Lỗi binding hoặc validation khác (nếu đã chạy validation).
}
~~~

Đây là đoạn minh họa trong bối cảnh có binder và import `org.springframework.validation.BindingResult`. Ba khái niệm cần phân biệt:

1. **Allowed fields**: cấu hình chỉ định property nào có quyền setter binding.
2. **Suppressed fields**: những tên property bị loại bởi quá trình lọc field khi property binding được thực thi.
3. **Binding errors**: lỗi gán/chuyển kiểu/required field được ghi trong `BindingResult`; nếu có validation, các lỗi validation cũng được thêm vào kết quả.

Với cấu hình `setDeclarativeBinding(true)` nhưng **không** `allowedFields`, Spring có thể bỏ qua toàn bộ lời gọi property binding ngay từ đầu. Bởi vậy, không được kết luận rằng `getSuppressedFields()` sẽ luôn liệt kê mọi tham số bị bỏ qua trong chế độ này.

Cũng không xem việc `getSuppressedFields().length==0` hoặc `!result.hasErrors()` là bằng chứng request không chứa input ngoài ý định; việc kiểm tra một HTTP contract nghiêm ngặt cần thiết kế riêng.

**Thứ tự kiểm tra:** trước khi cập nhật domain object, kiểm tra lỗi conversion/validation, xác thực người dùng và quyền thao tác, rồi áp dụng dữ liệu từ DTO hoặc allowlisted fields. Nếu endpoint quan tâm field lạ, hãy có chính sách rõ ràng thay vì trông chờ binder tự ném exception.

## 11. Các tình huống cụ thể: trước và sau

### Tình huống A: người dùng sửa tên nhưng gửi thêm quyền admin

Input:

~~~text
displayName=Lan
admin=true
role=ADMIN
~~~

- **Không giới hạn property binding** vào `AccountForm` mutable có setter: cả ba giá trị có thể được gán.
- **Declarative binding, không allowedFields** trên đối tượng đã tồn tại: không property nào được setter-bind, kể cả `displayName`.
- **Declarative binding, allowedFields("displayName")**: `displayName` được gán, `admin` và `role` giữ nguyên.

Đây chính là ba kịch bản từ chương trình Java.

### Tình huống B: record chỉ có hai tham số constructor

Input:

~~~text
oldEmail=old@example.com
newEmail=new@example.com
admin=true
~~~

Nếu record khai báo chỉ `oldEmail` và `newEmail`, constructor binding chỉ dùng các tham số cần thiết để tạo record. `admin` không trở thành property của record. Với `setDeclarativeBinding(true)`, Spring không tiếp tục setter-binding các property tùy ý trên record.

Nhưng service **vẫn phải kiểm tra** người gửi có quyền đổi email, giá trị cũ có đúng và email mới có hợp lệ hay không.

### Tình huống C: nested fields trong mẫu địa chỉ

Input:

~~~text
address.city=Ha Noi
address.country=VN
address.internalFlag=true
~~~

Nếu chỉ cho phép `address.city` và `address.country`, hãy liệt kê rõ hai đường dẫn này trong `setAllowedFields`. Dùng wildcard rộng `address*` có thể vô tình cho phép `address.internalFlag` hoặc thuộc tính mới về sau. Nested path cần đối tượng con phù hợp và có thể bị ảnh hưởng bởi cấu hình auto-grow; tránh cho phép các cấu trúc lớn không giới hạn.

### Tình huống D: bật chế độ global rồi form cũ ngừng hoạt động

Một form mutable trước kia dựa vào setter binding nhưng controller không có `setAllowedFields`. Sau khi thêm:

~~~java
@ControllerAdvice
class BindingPolicy {
    @InitBinder
    void initBinder(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
~~~

các property của form có thể không còn được gán như trước. Đây có thể là **tác dụng mong muốn về an toàn**, nhưng là **breaking change về hành vi form** nếu chưa migrate. Hãy bổ sung DTO/record hoặc allowlist phù hợp, rồi kiểm tra lại các endpoint với request thực tế.

## 12. Kiểm thử bảo mật và hồi quy

Kiểm thử nên tập trung vào hành vi cuối cùng của đối tượng và dữ liệu được lưu, thay vì chỉ nhìn vào trang HTML. Với ví dụ Java, ba dòng stdout kiểm tra ba chế độ. Trong ứng dụng MVC, nên có test cho ít nhất các trường hợp:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Form hợp lệ với các field cho phép | Field được gán đúng và nghiệp vụ thành công nếu các điều kiện khác cũng đạt |
| Form chứa `admin=true` nhưng không có quyền sửa admin | Field nhạy cảm không được thay đổi, ngay cả khi controller nhận input |
| Declarative binding không có allowlist trên form chỉ hỗ trợ setter | Không vô tình setter-bind property |
| Declarative binding có allowlist chính xác | Chỉ các property tương ứng có thể thay đổi |
| Record/DTO constructor binding | Đối tượng nhận các tham số được khai báo trong constructor |
| Constructor/record vô tình có tham số nhạy cảm | Test phát hiện thiết kế DTO sai; đừng coi cờ declarative là bảo vệ cho tham số constructor |
| Property allowed nhưng nhập sai kiểu | BindingResult có lỗi, nghiệp vụ không lưu dữ liệu chưa hợp lệ |
| Property allowed nhưng vi phạm `@NotBlank`/`@Min` | Validation (khi được kích hoạt) ngăn xử lý dữ liệu |
| API dùng `@RequestBody` JSON | Kiểm tra DTO/Jackson/validation riêng, không giả định chính sách của `WebDataBinder` |
| Sau khi chuyển sang `@ControllerAdvice` global | Các controller cũ vẫn nhận đủ field dự kiến, field bất ngờ không được bind |

Để xác nhận trực tiếp cấu hình binder:

~~~java
DataBinder binder = new DataBinder(new AccountForm());
binder.setDeclarativeBinding(true);
binder.setAllowedFields("displayName");

System.out.println(binder.isDeclarativeBinding()); // true
System.out.println(
        java.util.Arrays.toString(binder.getAllowedFields()));
// [displayName]
~~~

Đây là snippet chạy trong cùng dự án của `DeclarativeBindingDemo`, với import `DataBinder` và có thể tham chiếu `DeclarativeBindingDemo.AccountForm` từ class khác. Nó xác nhận **cấu hình**, nhưng phải đi kèm test `bind(...)` để xác nhận hành vi bảo vệ dữ liệu thật.

Nên có integration test cố ý gửi nhiều field lạ, nested path và value đã được encode. Đồng thời phải kiểm tra dữ liệu sau khi service lưu, bởi một controller đúng allowlist nhưng service ghi sai entity vẫn có thể tạo lỗ hổng.

## 13. Lỗi hiểu nhầm thường gặp

| Nhầm lẫn | Thực tế và cách sửa |
| --- | --- |
| “Bật declarative binding là form tự hoạt động với mọi setter cũ” | Không. Property binding yêu cầu `allowedFields` được cấu hình; nếu không form mutable có thể không nhận dữ liệu |
| “Chỉ field xuất hiện trên HTML mới bind được” | Client có thể tự gửi thêm parameter; server phải kiểm soát bằng DTO/constructor/allowlist |
| “`setAllowedFields` giới hạn cả constructor parameter” | Không. Nó giới hạn property binding; constructor có danh sách tham số riêng |
| “Chỉ cần bỏ `admin` khỏi form” | Không đủ nếu setter vẫn bind được; không dùng trực tiếp entity/domain nhiều property |
| “Declarative binding là validation” | Không. Validation kiểm tra giá trị sau khi nhận; binding xác định field nào được gán |
| “`BindingResult.hasErrors()` chắc chắn true khi client gửi field bị chặn” | Không phải luôn vậy; suppressed fields và errors là hai khái niệm khác |
| “`getSuppressedFields()` là danh sách mọi tham số không được dùng” | Không phải nhật ký đầy đủ; khi property binding không chạy, có thể không có các tên đó |
| “Cấu hình `@InitBinder` sẽ chặn cả JSON `@RequestBody`” | Không. JSON deserialize có đường xử lý riêng |
| “Constructor binding luôn an toàn” | Chỉ khi constructor/DTO khai báo đúng các input được phép và service vẫn phân quyền |
| “Đã có `setDisallowedFields("admin")` thì sau này thêm field mới vẫn an toàn” | Blacklist dễ bỏ sót; ưu tiên định nghĩa trường cho phép |
| “Bật global ở `@ControllerAdvice` không ảnh hưởng controller cũ” | Có thể làm thay đổi hành vi form; cần test hồi quy |

## 14. Checklist triển khai thực tế

- Thiết kế DTO/record chuyên dụng cho từng form, ưu tiên constructor binding khi phù hợp.
- Chỉ dùng property binding cho những field thật sự cần; bật `setDeclarativeBinding(true)` và khai báo allowlist tối thiểu.
- Không đưa các trường quyền, vai trò, owner, số dư, trạng thái hệ thống vào DTO từ client nếu không thật sự cần.
- Giới hạn nested/indexed property path và kích thước dữ liệu có thể bind; tránh wildcard quá rộng.
- Phân biệt các request `@ModelAttribute` với `@RequestBody`; không áp dụng nhầm binder config cho JSON.
- Kiểm thử input hợp lệ, field bất ngờ, lỗi chuyển kiểu, validation, quyền sở hữu và cập nhật cuối cùng vào database.
- Khi áp dụng cấu hình global, rà soát controller/form cũ và bổ sung test hồi quy trước khi phát hành.

**Kết luận:** `setDeclarativeBinding(true)` đưa việc xác định **ý định nhận dữ liệu** thành nguyên tắc mặc định của binder: constructor binding dùng những tham số khai báo trong constructor, còn setter binding chỉ chạy khi đã có `allowedFields`. Tính năng này rất hữu ích để giảm rủi ro mass assignment, nhưng phải đi cùng **DTO phù hợp, allowlist chặt chẽ, validation và authorization**.

## Tài liệu tham khảo

- [Spring Framework 6.2 — `@InitBinder` và Model Design](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework — Data Binding, Model Design](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring Framework — Constructor Binding và Property Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [`DataBinder` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.html)
