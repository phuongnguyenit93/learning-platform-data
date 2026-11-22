# setRequiredFields và lỗi thiếu trường khi property binding trong Spring Framework

Khi nhận form, ứng dụng thường cần phân biệt **client không gửi một trường bắt buộc** với **client đã gửi trường đó nhưng dữ liệu không hợp lệ**. Spring cung cấp **DataBinder.setRequiredFields(String...)** để kiểm tra các trường cần hiện diện trong tập giá trị đầu vào của **property binding**. Nếu không đáp ứng yêu cầu, binder tạo **FieldError** mang mã **required** (với **DefaultBindingErrorProcessor**), và bên gọi có thể đọc lỗi qua **BindingResult**.

Ví dụ, form đăng ký bắt buộc gửi **email**. Dù đối tượng Java đã có giá trị **email** từ trước, request chỉ chứa **displayName** vẫn vi phạm quy tắc **“phải gửi email ở lượt bind này”**. Ngược lại, request gửi **email=abc** được xem là có giá trị để bind: bản thân **setRequiredFields(...)** không kiểm tra cấu trúc địa chỉ email. Muốn đánh giá ý nghĩa dữ liệu, ứng dụng cần validation riêng.

Bài này tập trung đúng vào **DataBinder.bind(PropertyValues)** và **WebDataBinder property binding**, nêu rõ trường hợp thiếu, rỗng, loại lỗi, tương tác với allowed fields, cách tích hợp Spring MVC và các ranh giới với Bean Validation/constructor binding/JSON.

## 1. Hợp đồng của setRequiredFields(...)

Trên **org.springframework.validation.DataBinder**, những API chính là:

~~~java
binder.setRequiredFields("email", "displayName");
String[] configured = binder.getRequiredFields();
binder.bind(propertyValues);
BindingResult result = binder.getBindingResult();
~~~

Đoạn trên là minh họa trong một phương thức có **binder** và **propertyValues** phù hợp; cần import **org.springframework.validation.DataBinder** và **BindingResult**. **setRequiredFields(...)** nhận danh sách tên property bắt buộc cho **mỗi lần** binder thực hiện **bind(PropertyValues)**. Không cần thêm annotation trên field để làm cho kiểm tra này có hiệu lực.

Đặt cấu hình trước khi bind:

~~~java
RegistrationForm form = new RegistrationForm();
DataBinder binder = new DataBinder(form, "registrationForm");
binder.setRequiredFields("email");
binder.bind(new MutablePropertyValues(Map.of("displayName", "Lan")));
~~~

Trong đoạn minh họa, **RegistrationForm** là JavaBean và **MutablePropertyValues** chứa dữ liệu của request. Vì input không có property **email**, Spring ghi lỗi **required** cho field này. Kể cả khi **form.getEmail()** đã có giá trị khác **null** trước lúc bind, dữ liệu **không được gửi** vẫn không thỏa quy tắc của binder.

Những khía cạnh thiết yếu của hợp đồng:

- Tên yêu cầu là **tên property/path nhận trong PropertyValues**, ví dụ **email**, **address.city**, không phải tên cột database.
- Kiểm tra gắn với **lượt bind cụ thể**. Nó không chứng minh object đã đầy đủ sau các bước xử lý khác và không tự tạo request field bị thiếu.
- Một request có thể thiếu **nhiều** required fields. Spring ghi các lỗi tương ứng trong **BindingResult**, không chỉ trả về một boolean.
- **getRequiredFields()** giúp quan sát cấu hình hiện tại; gọi **setRequiredFields(...)** với danh sách mới thay cấu hình các required fields trên binder đó.
- Đây là **quy tắc của property binding** qua **bind(PropertyValues)**. Nó không áp dụng cho **DataBinder.construct(ValueResolver)**, vì constructor binding có cơ chế lấy tham số cần thiết riêng.
- **setRequiredFields(...) không tự chạy Bean Validation**. Ngay cả khi required fields đủ, phải gọi validator hoặc kích hoạt **@Valid/@Validated** theo đường xử lý tương ứng nếu cần kiểm tra ràng buộc nội dung.

Tên **required** ở đây nói về *input phải có mặt và không được xem là rỗng theo quy tắc của binder*. Đừng hiểu nó như một annotation đa năng kiểm tra mọi giá trị Java.

## 2. Spring coi trường nào là “thiếu”?

Điểm dễ gây nhầm là Javadoc nhấn mạnh **trường không có trong danh sách PropertyValues**, nhưng implementation **DataBinder.checkRequiredFields(...)** trong Spring 6.x còn xem một số giá trị **được gửi nhưng rỗng** như missing.

Với property đã đăng ký required, hành vi thông thường:

| Giá trị của property trong lượt bind | Kết quả kiểm tra required | Lý do |
| --- | --- | --- |
| Không xuất hiện trong **PropertyValues** | Lỗi **required** | Không tìm thấy input field |
| Có tên field, giá trị Java **null** | Lỗi **required** | Không có giá trị |
| **""** (chuỗi rỗng) | Lỗi **required** | Không có văn bản |
| **"   "** hoặc chỉ có ký tự whitespace | Lỗi **required** | **StringUtils.hasText(...)** trả false |
| **String[]** độ dài 0 | Lỗi **required** | Không có phần tử |
| **String[]** với phần tử đầu rỗng/whitespace | Lỗi **required** | Binder kiểm tra phần tử đầu cho trường hợp mảng chuỗi |
| **"abc"** hoặc **"0"** | Qua kiểm tra required | Có văn bản; nội dung có đúng kiểu/ý nghĩa hay không là chuyện khác |
| **false**, **0** dạng số, collection không null | Không tự coi là missing chỉ vì giá trị “falsey” hoặc rỗng | Cơ chế này không thay thế validator cho mọi loại dữ liệu |

**Ví dụ cần nhớ:** **email=abc** có mặt và không rỗng, nên **setRequiredFields("email")** không báo missing, dù **abc** không phải địa chỉ email hợp lệ. Một **Integer quantity = -2** có thể đã qua bước required sau khi được gửi, nhưng vẫn cần **@Min(1)**. Một **List** rỗng nhưng khác null không được kiểm tra giống một **String** rỗng theo logic này; nếu danh sách cần ít nhất một phần tử, dùng **@NotEmpty** hoặc quy tắc tương đương.

Đối với **String[]**, implementation kiểm tra **phần tử đầu**. Nếu phần tử đầu trắng nhưng phần tử sau có văn bản, required vẫn có thể thất bại. Đó là lý do không nên dùng tập hợp nhiều giá trị bất thường để “lách” quy tắc. Nên định nghĩa rõ form field nào là một giá trị, field nào là nhiều giá trị, rồi validate kiểu đích.

### Có dữ liệu cũ vẫn có thể bị báo thiếu

Giả sử object đang có:

~~~java
form.setEmail("old@example.com");
~~~

Nhưng request mới chỉ gửi:

~~~text
displayName=Lan
~~~

Nếu binder được cấu hình **setRequiredFields("email")**, nó kiểm tra tập property values của **request hiện tại** và ghi **required**. Đây không phải kiểm tra **form.getEmail() == null** sau khi bind. Với một lượt bind thiếu required field, giá trị cũ có thể vẫn còn trên target; **hasErrors()** mới là dấu hiệu quan trọng để không tiếp tục xử lý.

Chính vì thế, **setRequiredFields** phù hợp khi API/form yêu cầu gửi lại trường ở **mỗi request**, còn với một thao tác **PATCH** cập nhật một phần, ép mọi lượt phải gửi đủ các trường có thể là quyết định thiết kế sai.

## 3. Luồng nội bộ của DataBinder: lỗi được tạo trước khi gán

Với một **DataBinder** áp dụng giá trị thuộc tính, luồng chính của **doBind(MutablePropertyValues)** là:

~~~text
DataBinder.bind(PropertyValues)
         |
         v
Sao chép/chuẩn hóa tập PropertyValues để xử lý
         |
         v
checkAllowedFields(...)   --> loại input field không được phép
         |
         v
checkRequiredFields(...)  --> tìm các required fields không có/rỗng
         |                    |
         |                    +-- tạo FieldError, code "required"
         |                    +-- loại PropertyValue rỗng tương ứng
         v
applyPropertyValues(...)  --> chuyển kiểu và gán các property còn lại
         |                    |
         |                    +-- có thể thêm lỗi typeMismatch / methodInvocation
         v
BindingResult             --> chứa các lỗi binding
         |
         v
Validation nếu được kích hoạt riêng --> có thể bổ sung lỗi constraint
~~~

Từ thứ tự này có ba kết luận:

**Thứ nhất, required check dựa trên input sau khi lọc allowed fields.** Nếu bạn đánh dấu **email** là required nhưng **setAllowedFields(...)** không cho phép email, input email có thể bị loại trước khi required check chạy. Kết quả là **required** vẫn xuất hiện, dù client đã gửi email. Vì vậy khi sử dụng đồng thời **allowedFields** và **requiredFields**, phải đảm bảo các required fields thực sự nằm trong phạm vi được phép bind.

**Thứ hai, khi Spring xác định một required field rỗng, nó ghi lỗi rồi loại giá trị đó khỏi tập PropertyValues sẽ được gán.** Ví dụ request gửi **email="   "** nhưng target trước đó có **email="old@example.com"**, target có thể tiếp tục giữ **old@example.com** sau bind, trong khi **BindingResult** vẫn có lỗi **required**. Không đọc giá trị target cuối cùng rồi kết luận rằng required đã thành công.

**Thứ ba, lỗi required và lỗi chuyển kiểu khác nhau.** Với **age=abc** khi **age** là **Integer**, field **age** đã *có mặt*, vì vậy không bị báo thiếu đơn thuần; bước chuyển kiểu có thể tạo lỗi **typeMismatch**. Cả hai loại lỗi đi qua **BindingResult**, nhưng nguyên nhân và thông báo cho người dùng nên khác nhau.

Trong Spring MVC, **WebDataBinder** còn có bước xử lý field markers/defaults cho form trước khi gọi binding cơ sở, ví dụ các tên tham số có tiền tố đặc biệt phục vụ checkbox. Vì vậy ở một HTTP form cụ thể, kiểm tra tập property values **đã qua WebDataBinder** chính xác hơn việc chỉ xem raw request string.

## 4. BindingResult, FieldError và mã required

**setRequiredFields(...)** không ném một exception ở từng lỗi thiếu thông thường. Lỗi được đưa tới **BindingErrorProcessor** mà DataBinder cấu hình; implementation mặc định **DefaultBindingErrorProcessor** gọi **processMissingFieldError(...)** để tạo **FieldError** với mã **required**.

Các API quan sát:

~~~java
BindingResult result = binder.getBindingResult();

boolean hasErrors = result.hasErrors();
int missingOrOtherErrors = result.getErrorCount();

FieldError emailError = result.getFieldError("email");
if (emailError != null) {
    String primaryCode = emailError.getCode();
    String[] resolvableCodes = emailError.getCodes();
}
~~~

Đây là **đoạn minh họa** với import **BindingResult** và **FieldError** của Spring. **getCode()** thường là mã chung **required** cho lỗi missing field mặc định; **getCodes()** cung cấp danh sách mã mở rộng để tra thông báo theo object/field/type. Ví dụ object tên **registrationForm**, field **email** kiểu **String** có thể cho các mã theo thứ tự ưu tiên gần như:

~~~text
required.registrationForm.email
required.email
required.java.lang.String
required
~~~

Danh sách chính xác phụ thuộc **MessageCodesResolver** được cấu hình. Mã lỗi do tùy chỉnh **BindingErrorProcessor** hoặc validator cũng có thể khác.

Vì vậy, khi render form hoặc xây JSON error, nên dùng message resolving của ứng dụng (chẳng hạn **MessageSource**) thay vì hiển thị tên exception hay mã kỹ thuật không giải thích được gì. Ví dụ **messages_vi.properties**:

~~~properties
required.registrationForm.email=Bạn cần nhập địa chỉ email.
required.email=Vui lòng cung cấp email.
required=Trường bắt buộc chưa được cung cấp.
typeMismatch=Giá trị nhập có định dạng không phù hợp.
~~~

**required** khác **typeMismatch**:

| Lỗi | Được phát hiện ở đâu | Ví dụ | Hướng giải thích |
| --- | --- | --- | --- |
| **required** | Required fields check (hoặc custom validation cố tình dùng cùng mã) | **email** vắng mặt hoặc whitespace | Trường bắt buộc cần được cung cấp |
| **typeMismatch** | Chuyển kiểu/gán property | **age=abc** với **Integer age** | Giá trị không chuyển được sang kiểu yêu cầu |
| **methodInvocation** | Lỗi khi gọi setter theo cơ chế Spring property access | Setter từ chối giá trị hoặc lỗi invocation | Kiểm tra setter/logic property |
| **NotBlank / NotNull / Size...** | Bean Validation khi được kích hoạt | Chuỗi rỗng, thiếu, vượt độ dài | Không đạt constraint được khai báo |
| Mã lỗi nghiệp vụ tùy chỉnh | Service/domain/validator do ứng dụng tạo | Email đã đăng ký, không đủ quyền | Xử lý theo quy tắc nghiệp vụ |

Đừng dựa vào **hasErrors()** một mình để kết luận tất cả lỗi đều là missing field. Hãy duyệt **getFieldErrors()** hoặc kiểm tra **getFieldError("email")**, **getCodes()** và nguồn sinh lỗi.

## 5. Ví dụ Java 17+ chạy độc lập: missing, blank, dữ liệu cũ và nội dung không hợp lệ

Dùng **Spring Framework 6.2.10** trong chương trình console, không cần HTTP server. Ví dụ cho thấy:

1. Không gửi **email** → **required**.
2. Gửi **email** chỉ chứa khoảng trắng → **required**.
3. Gửi email có văn bản → không có lỗi required.
4. Object đã có email cũ nhưng request không gửi email → **required**, email cũ vẫn còn.
5. Gửi chuỗi không phải email **abc** → required vẫn qua vì có văn bản.
6. Gửi **String[]** với phần tử đầu rỗng → **required**.

Tạo cấu trúc:

~~~text
required-fields-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── RequiredFieldsDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>required-fields-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/RequiredFieldsDemo.java**:

~~~java
package demo;

import java.util.Map;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public final class RequiredFieldsDemo {

    public static void main(String[] args) {
        run("missing", values("displayName", "Ada"), null);
        run("blank", values("email", "   "), null);
        run("present", values("email", "ada@example.com"), null);
        run("preFilledMissing",
                values("displayName", "Ada"), "old@example.com");
        run("nonEmailText", values("email", "abc"), null);

        MutablePropertyValues firstArrayElementEmpty =
                new MutablePropertyValues();
        firstArrayElementEmpty.add(
                "email", new String[] {"", "ada@example.com"});
        run("arrayFirstEmpty", firstArrayElementEmpty, null);
    }

    private static MutablePropertyValues values(String key, String value) {
        return new MutablePropertyValues(Map.of(key, value));
    }

    private static void run(
            String label, MutablePropertyValues input, String oldEmail) {

        RegistrationForm form = new RegistrationForm();
        form.setEmail(oldEmail);

        DataBinder binder = new DataBinder(form, "registrationForm");
        binder.setAllowedFields("email", "displayName");
        binder.setRequiredFields("email");

        binder.bind(input);
        BindingResult result = binder.getBindingResult();
        FieldError error = result.getFieldError("email");

        System.out.println(label
                + ": errors=" + result.hasErrors()
                + ", code=" + (error == null ? "none" : error.getCode())
                + ", email=" + form.getEmail());
    }

    public static final class RegistrationForm {
        private String email;
        private String displayName;

        public RegistrationForm() {
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }
    }
}
~~~

Từ thư mục chứa **pom.xml**, với **JDK 17+** và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.RequiredFieldsDemo
~~~

**Các dòng do chính chương trình in ra**, không bao gồm log phụ thuộc công cụ build:

~~~text
missing: errors=true, code=required, email=null
blank: errors=true, code=required, email=null
present: errors=false, code=none, email=ada@example.com
preFilledMissing: errors=true, code=required, email=old@example.com
nonEmailText: errors=false, code=none, email=abc
arrayFirstEmpty: errors=true, code=required, email=null
~~~

Phân tích kết quả:

- **missing:** chỉ có **displayName**, nên **email** không có trong PropertyValues; **DefaultBindingErrorProcessor** ghi lỗi required.
- **blank:** có **email**, nhưng **"   "** thiếu nội dung theo **StringUtils.hasText**; Spring loại PropertyValue rỗng khỏi lượt gán và thêm lỗi required.
- **present:** giá trị email có văn bản nên bind vào field **email** và **hasErrors() == false**. Đoạn code chưa chạy Bean Validation.
- **preFilledMissing:** dù **RegistrationForm.email** ban đầu là **old@example.com**, việc request không gửi email vẫn vi phạm required; Spring không xóa giá trị đã có trên target vì thiếu trường, nên chính **BindingResult** mới cho biết lượt bind lỗi.
- **nonEmailText:** **abc** được xem là “có mặt”, binder không thực thi quy tắc định dạng email; phải dùng **@Email**, custom validator hoặc kiểm tra chuyên biệt nếu cần.
- **arrayFirstEmpty:** implementation kiểm tra phần tử đầu của **String[]**, nên phần tử đầu **""** khiến field bị coi là thiếu, kể cả phần tử sau có văn bản.

**Lưu ý tính độc lập:** mỗi case tạo **RegistrationForm** và **DataBinder** mới, nên lỗi không tích lũy giữa các case. Phần ví dụ này chứng minh quy tắc required của property binding, chưa có HTTP, JSON, validation annotations hay lưu cơ sở dữ liệu.

### Thử giá trị null tường minh

Nếu muốn kiểm tra thêm Java **null** trong PropertyValues (khác với chuỗi chữ **"null"**), có thể thêm case:

~~~java
MutablePropertyValues input = new MutablePropertyValues();
input.add("email", null);
run("explicitNull", input, null);
~~~

Đoạn nằm trong cùng class **RequiredFieldsDemo**; **run(...)** phải có quyền truy cập như trong code trên. Kết quả là **errors=true**, **code=required**, **email=null**. **Map.of("email", null)** không hợp lệ trong Java và ném exception trước khi Spring bind, nên ví dụ dùng **MutablePropertyValues.add(...)**.

## 6. Tích hợp Spring MVC bằng @InitBinder

Trong ứng dụng Spring MVC có form:

~~~text
POST /registrations
Content-Type: application/x-www-form-urlencoded

displayName=Lan
~~~

Một controller có thể yêu cầu **email** xuất hiện trong property binding của model attribute **registrationForm**:

~~~java
@Controller
class RegistrationController {

    @InitBinder("registrationForm")
    void customize(WebDataBinder binder) {
        binder.setAllowedFields("email", "displayName");
        binder.setRequiredFields("email");
    }

    @PostMapping("/registrations")
    String register(
            @ModelAttribute("registrationForm") RegistrationForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            return "registration-form";
        }

        // Ở ứng dụng thật: kiểm tra thêm nội dung và quy tắc nghiệp vụ,
        // rồi gọi service để xử lý yêu cầu đăng ký.
        return "redirect:/registrations/success";
    }
}
~~~

Đây là **mã minh họa đặt trong một ứng dụng Spring MVC có sẵn**, không phải class chạy độc lập. **RegistrationForm** là JavaBean ở ví dụ trước hoặc DTO riêng cùng cấu trúc; cần import **Controller**, **InitBinder**, **PostMapping**, **ModelAttribute**, **WebDataBinder**, **BindingResult**. Template **registration-form** và route thành công chỉ là các thành phần giả định của ứng dụng web.

Ý nghĩa từng phần:

- **@InitBinder("registrationForm")** áp dụng cấu hình cho binder của model attribute có tên đó. Tên trong **@ModelAttribute("registrationForm")** phải khớp.
- **binder.setRequiredFields("email")** yêu cầu input form có email trong lần bind. Nó có hiệu lực ở **binding phase**, không cần **@Valid** để tạo lỗi required.
- **binder.setAllowedFields(...)** thu hẹp những property mà client được quyền bind. Required field **email** được đưa vào allowed fields để tránh tự chặn.
- **BindingResult** phải đứng ngay sau tham số model attribute tương ứng; controller đọc **hasErrors()** và trả lại form khi có lỗi binding.
- Nếu không cung cấp **BindingResult/Errors** ở vị trí phù hợp, Spring MVC xử lý lỗi qua cơ chế exception/response tương ứng; không nên giả định controller vẫn đi tiếp như lúc không có lỗi.

**@Valid/@Validated** có thể được bổ sung khi cần Bean Validation, nhưng mục đích khác với **setRequiredFields**. Nếu một ứng dụng sử dụng constructor binding thay cho property binding, phải xem xét lại chỗ áp dụng required fields vì cấu hình này dành cho **bind(PropertyValues)**. Với **@RequestBody JSON**, HTTP message converter thường deserialize object bằng Jackson; **setRequiredFields** trên WebDataBinder không phải công tắc chung cho việc bắt buộc có JSON field.

### Khi kết hợp với @Valid

Giả sử DTO có:

~~~java
public class RegistrationForm {
    @jakarta.validation.constraints.NotBlank
    @jakarta.validation.constraints.Email
    private String email;

    // getters/setters...
}
~~~

Đây là **đoạn minh họa**, muốn chạy phải khai báo Bean Validation provider (ví dụ dùng **spring-boot-starter-validation** trong dự án Spring Boot) và kích hoạt validation ở handler:

~~~java
@PostMapping("/registrations")
String register(
        @jakarta.validation.Valid
        @ModelAttribute("registrationForm") RegistrationForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "registration-form";
    }
    return "redirect:/registrations/success";
}
~~~

Trường **email** có thể sinh mã lỗi required từ binding khi thiếu, hoặc mã constraint tương ứng từ validation nếu dữ liệu đã được bind nhưng vi phạm ràng buộc. Spring MVC có cơ chế xử lý cả hai qua **BindingResult**, song nguồn phát sinh là khác nhau; đừng suy luận chỉ từ **hasErrors()** rằng một trong hai cơ chế đã thay thế cơ chế còn lại. **@NotBlank** kiểm tra giá trị của object sau binding; **setRequiredFields** kiểm tra sự hiện diện/độ rỗng của input ở lượt bind.

## 7. So sánh setRequiredFields với những cơ chế “bắt buộc” khác

| Cơ chế | Kiểm tra ở đâu | Bắt buộc điều gì? | Phạm vi cần lưu ý |
| --- | --- | --- | --- |
| **DataBinder.setRequiredFields("email")** | Property values trong **bind(PropertyValues)** | Field phải xuất hiện và không rỗng theo logic required của binder | Không tự kiểm tra định dạng email; không áp dụng constructor binding |
| **@NotNull** | Bean Validation trên giá trị thuộc tính | Giá trị object không được **null** | **""** hoặc **" "** vẫn khác null |
| **@NotBlank** | Bean Validation trên **CharSequence** | Không null, không rỗng hoặc chỉ whitespace | Không nhất thiết yêu cầu field được gửi mới ở request hiện tại nếu object đã có giá trị |
| **@NotEmpty** | Bean Validation | Chuỗi, collection, map hoặc array không rỗng | Không đồng nghĩa kiểm tra nội dung từng phần tử |
| **@Email** | Bean Validation | Nội dung có định dạng email theo provider/constraint | Không kiểm tra email có tồn tại trong hệ thống |
| **@RequestParam(required = true)** | Spring MVC method argument resolver | Request parameter bắt buộc theo cách phân giải đối số | Đường đi exception riêng, không phải setRequiredFields của model attribute |
| **@RequestBody(required = true)** | Spring MVC đọc request body | Body phải được cung cấp theo hợp đồng argument | Không đảm bảo mọi trường JSON bên trong body đều có |
| Custom service/domain validation | Application service và domain | Quy tắc phụ thuộc trạng thái, quyền, dữ liệu hiện tại | Cần xử lý giao dịch/đồng thời khi cập nhật |

### Ba ví dụ không tương đương

**A. Form không gửi email, target ban đầu có email cũ.**

- **setRequiredFields("email")** báo thiếu input.
- **@NotNull** trên target có thể vẫn đạt vì target đã có email cũ.
- Điều đó cho thấy **“request phải gửi trường”** và **“object cuối cùng có giá trị”** là hai điều kiện khác nhau.

**B. Form gửi email=abc.**

- Required check đạt vì có văn bản.
- **@Email** có thể phát hiện định dạng không hợp lệ nếu Bean Validation chạy.
- Service vẫn có thể từ chối nếu email đã được người khác đăng ký.

**C. Form gửi quantity=-1.**

- Required check cho field quantity có thể đạt vì đã nhận một giá trị.
- **@Min(1)** phát hiện âm nếu validation được kích hoạt.
- Khi tạo đơn hàng, service còn kiểm tra giới hạn mua và tồn kho. Không một annotation đơn giản nào tự bảo vệ mọi giao dịch đồng thời.

## 8. Tương tác với allowedFields, disallowedFields và tên đường dẫn

Một cấu hình dễ gặp:

~~~java
DataBinder binder = new DataBinder(form, "registrationForm");
binder.setAllowedFields("displayName");  // KHÔNG bao gồm email
binder.setRequiredFields("email");
binder.bind(new MutablePropertyValues(Map.of(
        "email", "ada@example.com",
        "displayName", "Ada"
)));
~~~

Dù request gửi email, **checkAllowedFields(...)** loại **email** khỏi danh sách đầu vào được phép bind trước khi **checkRequiredFields(...)** chạy. Kết quả có thể bao gồm **getSuppressedFields()** chứa email và **getFieldError("email")** có mã required. Đây là lỗi cấu hình của ứng dụng chứ không phải lỗi của người dùng. Nếu email thực sự là field được phép gửi và bắt buộc phải gửi, cấu hình nhất quán:

~~~java
binder.setAllowedFields("email", "displayName");
binder.setRequiredFields("email");
~~~

Không bật quyền bind vào các field nhạy cảm chỉ để tránh missing error; hãy thiết kế request DTO và danh sách required sao cho phù hợp với những gì người dùng thật sự được phép sửa.

### Nested field: address.city

Nếu yêu cầu một đường dẫn như:

~~~java
binder.setRequiredFields("address.city");
~~~

thì property input mà binder tìm là **address.city**. Client chỉ gửi **address.street** không đáp ứng yêu cầu đó, dù đối tượng **address** đã tồn tại. Ngược lại, việc có **address.city** trong PropertyValues không khẳng định bind thành công: Spring còn phải duyệt object trung gian **address**, có thể tự tạo nếu được phép và khởi tạo được, rồi chuyển/gán giá trị.

**setRequiredFields không phải wildcard validation cho mọi field lồng nhau.** Các tên required được so sánh theo tên property đã chuẩn hóa; muốn yêu cầu nhiều field phải liệt kê những tên thực tế tương ứng. Với collection **addresses[0].city**, cần thiết kế số lượng/index hợp lệ và quy tắc validation riêng, không dùng một tên chung mơ hồ để thay thế kiểm tra cấu trúc collection.

### Đối tượng có field bị ignored/suppressed

Nếu kết quả cho thấy **result.getSuppressedFields()** không rỗng, hãy kiểm tra liệu request đang cố gán field không cho phép. Lỗi cấu hình **allowedFields** và lỗi **required** có thể xuất hiện cùng lúc; xử lý đúng nguyên nhân thay vì chỉ đổi thông báo “bạn quên nhập email”.

## 9. Những bẫy thường gặp trong HTTP form

**Checkbox không được tick thường không sinh parameter.** Một checkbox HTML thông thường có thể bị vắng khỏi request khi không chọn. Nếu gọi **setRequiredFields("subscribed")** để bắt buộc *người dùng đã thấy/đồng ý điều khoản*, phải phân biệt “checkbox vắng mặt”, “đã gửi false”, và “đã tick true”. Required check chỉ đo sự hiện diện/độ rỗng theo dạng input; nó không tự diễn giải **false** là vi phạm điều khoản. **WebDataBinder** có cơ chế field marker/default cho checkbox, vì thế cần kiểm thử request thực tế trước khi kết luận.

**Field ẩn không làm dữ liệu đáng tin.** Đưa **email** hoặc **role** vào hidden input có thể khiến required check qua, nhưng client vẫn sửa được. Kiểm tra quyền, chủ sở hữu và dữ liệu do server quyết định ở tầng phù hợp.

**Trường required không phù hợp với PATCH.** Khi cập nhật một phần, client có quyền chỉ gửi field cần thay đổi; ép **email** xuất hiện ở mọi lượt có thể từ chối request hợp lệ. Phân biệt DTO cho create/replace/partial update hoặc dùng validation groups/kiểm tra phù hợp.

**Tên của form field phải khớp property.** Nếu HTML gửi **contactEmail** nhưng binder bắt buộc **email**, required check tìm **email** và báo thiếu. Sửa ánh xạ form/DTO, không nới lỏng lỗi mà chưa điều tra.

**Một trường present có thể vẫn không gán được.** Dữ liệu sai kiểu gây **typeMismatch** trong binding; getter/setter lỗi gây lỗi property access. Required check đạt không bảo đảm mọi property đã được set thành công.

**Báo thiếu rồi vẫn ghi dữ liệu.** Property binding có thể đã gán những field khác trước khi trả **BindingResult**; nó không phải transaction có rollback. Dừng xử lý nghiệp vụ khi còn lỗi, dùng DTO riêng rồi mới chuyển sang domain command.

**Kỳ vọng setRequiredFields tự kích hoạt khi chỉ dùng annotation.** Phải cấu hình binder thật sự được framework sử dụng hoặc gọi binder thủ công. Một **DataBinder** khác hoặc một **@RequestBody** JSON không tự nhận cấu hình chỉ vì có một bean dùng ở nơi khác.

**Tùy biến BindingErrorProcessor không tính đến error contract.** Nếu thay default processor, mã/loại lỗi có thể thay đổi. UI và test phải dựa trên error contract mà ứng dụng chủ động thiết kế, không mặc nhiên rằng mọi implementation đều tạo cùng FieldError.

## 10. Thiết kế phản hồi lỗi

Trong form MVC, thông thường controller có **BindingResult** ngay sau **@ModelAttribute**, sau đó trả lại template để hiển thị lỗi tại field liên quan. Với REST API, việc biến lỗi thành **400 Bad Request**, **ProblemDetail** hoặc cấu trúc JSON khác do **exception handler/response contract** quyết định; bản thân **setRequiredFields** không trả một HTTP status.

Một biểu diễn lỗi JSON có thể gồm:

~~~json
{
  "type": "validation_error",
  "errors": [
    {
      "field": "email",
      "code": "required",
      "message": "Vui lòng cung cấp email."
    }
  ]
}
~~~

Đây là **định dạng đề xuất**, không phải body mặc định cố định của Spring MVC. Không trả stack trace hoặc thông tin nội bộ. Khi localize, ưu tiên mã lỗi ổn định **required** kèm tên field, còn message được tra từ **MessageSource** theo locale.

Nếu có nhiều lỗi cùng lúc, trả tập lỗi phù hợp để client sửa một lần; ví dụ email thiếu và age sai kiểu. Đừng gộp mọi FieldError thành cùng một câu **“request không hợp lệ”** mà bỏ tên trường và mã lỗi nếu người dùng cần phản hồi cụ thể.

## 11. Test matrix cho required fields

Một bộ kiểm thử sát hành vi Spring nên bao gồm cả **unit test cho DataBinder** và **MVC integration test** nếu có controller.

| Test | Input / trạng thái ban đầu | Kỳ vọng |
| --- | --- | --- |
| Missing | PropertyValues không chứa **email** | **FieldError(email)** mã **required** |
| Explicit null | PropertyValues chứa **email = null** | **required** |
| Empty String | **email = ""** | **required** |
| Whitespace String | **email = "   "** | **required** |
| String[] empty | **email = new String[0]** | **required** |
| First array element blank | **email = ["", "abc"]** | **required** |
| Present text | **email = "abc"** | Không có lỗi required; format phải kiểm riêng |
| Existing value, request missing | Target **email = "old@example.com"**, request thiếu email | **required** dù target còn giá trị cũ |
| Allowed vs required conflict | Required email nhưng allowlist không có email | Email bị loại; cần phát hiện cấu hình sai |
| Nested path | Required **address.city**, request chỉ gửi **address.street** | Lỗi required cho **address.city** |
| Type mismatch | Required **age**, request **age=abc** cho Integer | Field có mặt nhưng có thể sinh **typeMismatch** |
| PATCH scenario | Chỉ cập nhật displayName | Không cấu hình email required nếu hợp đồng cho phép bỏ qua |
| JSON input | **@RequestBody** thiếu email | Phải kiểm bằng JSON deserialization/Bean Validation phù hợp; không kết luận setRequiredFields đã chạy |

Các kiểm thử cần quan sát cả **FieldError.getCode()** và giá trị target sau bind. Trường hợp email là blank nhưng target đã có giá trị cũ cho thấy ý nghĩa của bước Spring **loại PropertyValue không hợp lệ khỏi lượt gán**. Với test MVC, xác nhận **@InitBinder** thực sự được gọi cho đúng model attribute và **BindingResult** được đặt ngay sau tham số tương ứng.

## 12. Checklist áp dụng đúng

Trước khi chọn **setRequiredFields(...)**, hãy tự hỏi:

1. Nguồn dữ liệu có đi qua **DataBinder.bind(PropertyValues)** hay không? Với constructor binding hoặc JSON body, cần cơ chế khác.
2. Yêu cầu “bắt buộc” nghĩa là **field phải được gửi trong request** hay chỉ là **object cuối cùng phải có giá trị hợp lệ**? Hai mục tiêu có thể dẫn đến kết quả khác.
3. Tên required field có khớp property path thực tế và nằm trong danh sách **allowedFields** không?
4. Input từ HTML form có các cơ chế **field markers/defaults**, multi-value arrays hoặc checkbox không?
5. Sau binding, code có kiểm tra **BindingResult** trước khi ghi nghiệp vụ không?
6. Nếu dữ liệu có mặt nhưng không hợp lệ về nội dung, đã có **@NotBlank**, **@Email**, **@Min**, Spring Validator hoặc logic domain phù hợp chưa?
7. Nếu cần thông báo cho người dùng, ứng dụng đã ánh xạ mã lỗi **required** ra thông điệp dễ hiểu theo locale chưa?

Nhớ rằng **“required trong property binding”** là một quy tắc về **giá trị đầu vào của lượt bind**. Nó bổ sung cho chuyển kiểu, validation và domain rules, nhưng không tự thay thế ba cơ chế đó.

## Tài liệu chính thức

- [Spring Framework 6.2.10 — DataBinder API: setRequiredFields, checkRequiredFields, bind](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2.10 — DefaultBindingErrorProcessor](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/validation/DefaultBindingErrorProcessor.html)
- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring MVC — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring MVC — @ModelAttribute method arguments và BindingResult](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — Jakarta Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
