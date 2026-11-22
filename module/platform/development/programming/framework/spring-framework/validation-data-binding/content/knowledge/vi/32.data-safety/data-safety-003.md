# Constructor binding và giới hạn bề mặt có thể thay đổi trong Spring Data Binding

## 1. Vấn đề bảo mật: HTTP input có thể thay đổi những gì?

**Data binding** giúp Spring chuyển request parameters, form fields và một số nguồn dữ liệu HTTP thành Java object. Tiện ích này trở thành rủi ro khi target có những thuộc tính **không được phép cho client chỉnh sửa** nhưng vẫn có thể bị gán từ request.

Ví dụ ứng dụng có entity:

~~~java
public class Account {
    private Long id;
    private String displayName;
    private String contactEmail;
    private String role;
    private boolean locked;
    private Long tenantId;

    // getters, setters và logic persistence ...
}
~~~

Đây là **snippet mô tả entity**, chưa phải file độc lập. Giao diện “Chỉnh sửa hồ sơ” chỉ hiển thị `displayName` và `contactEmail`. Client ác ý vẫn có thể gửi thêm:

~~~http
POST /accounts/7/profile
Content-Type: application/x-www-form-urlencoded

displayName=Lan&contactEmail=lan@example.com&role=ADMIN&locked=false&tenantId=999
~~~

Nếu controller bind trực tiếp request vào `Account` có public setters cho `role`, `locked` và `tenantId`, Spring **có thể gán cả những field mà UI không hiển thị**. Đây là rủi ro **mass assignment / overposting / unsafe object binding**.

**Điều cần giới hạn không phải chỉ là input hợp lệ về kiểu hoặc định dạng; đó là *bề mặt có thể thay đổi* (mutable surface)**: tập field, nested property, collection element hoặc constructor argument mà client được quyền cung cấp.

Các lớp bảo vệ liên quan nhưng không thay thế nhau:

1. **Input DTO/command object chuyên biệt**: chỉ khai báo những giá trị client được phép gửi.
2. **Constructor binding**: chọn đúng các tham số constructor cần thiết, thay vì gán tùy ý mọi setter.
3. **`DataBinder#setDeclarativeBinding(true)`**: đưa binder vào chế độ khai báo, chỉ cho constructor binding và property binding đã được cho phép.
4. **`WebDataBinder#setAllowedFields(...)`**: giới hạn property/setter binding khi vẫn cần bean mutable.
5. **Validation** (`@Valid`, `@NotBlank`, `@Email`, ...): kiểm tra dữ liệu có hợp lệ hay không; **không** quyết định ai có quyền sửa thuộc tính.
6. **Authorization và cập nhật chọn lọc ở service/domain layer**: bảo đảm user có quyền sửa đúng resource và chỉ ghi những trường được phép.

**Bài học chính:** constructor binding giảm diện tích có thể bị thay đổi **khi constructor/DTO được thiết kế đúng**. Nó không tự động biến mọi constructor argument thành “được phép”. Nếu đưa `role` hoặc `tenantId` vào constructor nhận HTTP input, client vẫn có thể cung cấp chúng.

## 2. Spring phân biệt constructor binding và property binding thế nào?

Spring `DataBinder`/`WebDataBinder` cung cấp hai hướng đi riêng:

| Đặc điểm | Constructor binding | Property/setter binding |
| --- | --- | --- |
| Đích | Tham số của data/primary constructor | JavaBean properties, setters hoặc direct field access nếu được cấu hình |
| Dữ liệu được tìm | Theo tên constructor argument (có thể tùy biến bằng `@BindParam`) | Theo tên property path từ request |
| Bề mặt được xem xét | Các tham số xuất hiện trong constructor được chọn, kể cả nested constructor binding phù hợp | Các property có thể ghi trong target/object graph |
| Với Java record | Rất phù hợp: record canonical constructor khai báo rõ schema input | Record không có setters cho components; nhưng đừng suy rộng sang mọi nested mutable object |
| Với JavaBean có no-arg constructor | Constructor không tạo ra field values; thường cần setter binding | Dùng setters để cập nhật field |
| Kiểm soát | Thiết kế constructor + DTO chỉ có các tham số công khai | `setAllowedFields`, dedicated DTO, field access policy |
| Input thừa | Constructor binding chỉ sử dụng những values cần cho constructor; extra inputs có thể bị bỏ qua | Mặc định có thể gán mọi property match và được phép |
| Security caveat | Constructor chứa field nhạy cảm thì vẫn nhận giá trị nhạy cảm | Public setters/nested paths có thể mở rộng quyền sửa |

Theo tài liệu Spring Framework 6.1/6.2, **mặc định có thể áp dụng cả constructor binding lẫn property binding**. Vì vậy, đừng hiểu “Spring tìm được primary constructor” là “mọi setter binding sau đó chắc chắn bị tắt”. Với object có setters, cấu hình binder vẫn quan trọng.

### Luồng khái quát khi nhận `@ModelAttribute`

~~~text
Request: displayName=Lan, contactEmail=lan@example.com,
         role=ADMIN, locked=false
        |
        v
Spring @ModelAttribute argument resolver
        |
        +--> Tạo hoặc lấy target object
        |      |
        |      +--> Constructor binding:
        |             chỉ các constructor parameters cần thiết
        |
        +--> Property binding:
        |      có thể áp dụng tiếp nếu binder cho phép
        |
        +--> @Valid / @Validated (nếu khai báo)
        |
        +--> BindingResult
        |
        v
Controller nhận command object đã bind
        |
        v
Service kiểm tra quyền, chỉ cập nhật các field cho phép
~~~

Trong ứng dụng Servlet Spring MVC, `@ModelAttribute` có thể đọc request parameters gồm query/form, và có thể bổ sung URI path variables hoặc headers theo quy tắc ưu tiên của Spring. Những nguồn này **đều là input không đáng tin**, không thể tự biến thành quyền truy cập nhờ đứng trong path hay header.

## 3. Constructor binding với Java record: khai báo input contract rõ ràng

Thay vì bind trực tiếp `Account`, dùng record chỉ nhận hai trường cho phép:

~~~java
public record AccountChangeForm(
        @NotBlank String displayName,
        @NotBlank @Email String contactEmail) {
}
~~~

Khi một handler khai báo:

~~~java
@PostMapping("/accounts/{id}/profile")
ResponseEntity<?> change(
        @PathVariable long id,
        @Valid @ModelAttribute("changeForm")
                AccountChangeForm form,
        BindingResult errors) {
    // ...
}
~~~

Spring MVC có thể tạo `AccountChangeForm` qua constructor từ các input names `displayName`, `contactEmail`, rồi validate record.

Form:

~~~text
displayName=Lan
contactEmail=lan@example.com
role=ADMIN
locked=false
tenantId=999
~~~

**Không có constructor parameter** `role`, `locked` hoặc `tenantId`, nên constructor binding của `AccountChangeForm` **không lấy** chúng. Tuy nhiên, **đừng dựa chỉ vào sự bất biến của record để tuyên bố toàn ứng dụng đã chống mass assignment**:

- Đảm bảo target thực sự là **input DTO**, không phải entity có data constructor chứa server-owned fields.
- Bật **`declarativeBinding`** ở binder khi muốn bảo đảm không có property binding ngoài chủ đích.
- Đừng đưa mutable entity, `Map<String,Object>` mở hoặc graph quá rộng vào một record constructor rồi coi đó là “được khóa”.
- Kiểm tra chính sách riêng cho **JSON `@RequestBody`**, bởi đó là Jackson decoding, không phải cùng đường `WebDataBinder`.
- Ở service layer, vẫn phải kiểm tra quyền với account ID và người dùng hiện tại; một DTO nhỏ **không thay thế authorization**.

### Constructor được chọn

Spring có thể tạo object bằng default constructor hoặc “primary/data constructor”. Theo tài liệu DataBinder, constructor binding dựa vào **tên tham số constructor** được lưu trong bytecode, `@ConstructorProperties` hoặc cơ chế nhận diện tương ứng. Java record có canonical constructor và metadata components rõ ràng, phù hợp cho ví dụ.

Nếu một class có nhiều constructor chồng lấn hoặc default constructor, Spring có thể ưu tiên default constructor và sau đó setter binding. **Không suy rằng Spring tự chọn constructor có nhiều tham số nhất**. Thiết kế command object đơn giản, có một data constructor rõ ràng, là cách hạn chế sự mơ hồ.

Với class thường, khi cần reflection-based parameter names, hãy bảo đảm build giữ tên tham số (ví dụ compiler `-parameters`) hoặc dùng annotations được Spring hỗ trợ. Nếu thiếu thông tin tên, constructor binding có thể không lấy đúng input.

## 4. `setDeclarativeBinding(true)`: điểm cắt quan trọng

Từ **Spring Framework 6.1**, `DataBinder` có:

~~~java
binder.setDeclarativeBinding(true);
~~~

Ý nghĩa chính xác (theo Javadoc):

- Cho phép **constructor binding**.
- Chỉ thực hiện **property binding** khi đã cấu hình `allowedFields` tương ứng.
- Mặc định của cờ này là **`false`**, nên không thể mặc định tin rằng property binding đã bị chặn.

Ví dụ trong controller:

~~~java
@InitBinder("changeForm")
void configureChangeForm(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
~~~

Bằng `@InitBinder("changeForm")`, cấu hình được áp dụng cho binder của model attribute có tên **`changeForm`**. Đây là phạm vi model attribute, không phải whitelist field name.

### Bảng hành vi cần phân biệt

| `declarativeBinding` | `allowedFields` | Hành vi property/setter binding | Constructor binding |
| --- | --- | --- | --- |
| `false` (mặc định) | Không cấu hình | Có thể bind các writable properties phù hợp | Có thể chạy khi tạo target |
| `false` | `{"nickname","language"}` | Chỉ các property được cho phép | Có thể chạy khi tạo target |
| **`true`** | **Không có allowlist** | **Không chạy property binding** | Vẫn chạy khi tạo target |
| **`true`** | **`{"nickname","language"}`** | **Chỉ bind các property trong allowlist** | Vẫn chạy khi tạo target |

**Cạm bẫy:** Một JavaBean có **no-arg constructor** và chỉ có setters sẽ **không được điền thuộc tính** nếu đặt `setDeclarativeBinding(true)` mà không thêm `allowedFields`. Đó không phải “Spring tự động bind constructor cho mọi setter properties”. Hãy chọn đúng một trong hai cách:

1. Chuyển input sang record/immutable command object có data constructor phù hợp.
2. Giữ JavaBean mutable nhưng khai báo `allowedFields` tường minh.

### Có thể cấu hình global không?

Có. `@ControllerAdvice` có thể chứa `@InitBinder` để áp dụng binder policy trên nhiều controllers, hoặc Spring có `ConfigurableWebBindingInitializer` để cấu hình chung. Tuy nhiên, bật global declarative binding có thể làm các form JavaBean hiện hữu **đột nhiên không nhận setter values**. Muốn áp dụng toàn hệ thống, cần inventory, migration plan và regression tests; với một bài học đơn, `@InitBinder("changeForm")` cục bộ sẽ dễ kiểm soát hơn.

Không sửa global configuration chỉ để khắc phục một form nếu chưa đánh giá tác động lên toàn bộ routes.

## 5. `setAllowedFields` cho form mutable: allowlist tốt hơn blacklist

Giả sử một form vẫn cần JavaBean setters để tương thích UI:

~~~java
public class PreferencesForm {
    private String nickname;
    private String language;
    private boolean admin;

    // public getters/setters...
}
~~~

Khi xử lý request, ứng dụng chỉ cho client thay đổi `nickname` và `language`. Có thể cấu hình:

~~~java
@InitBinder("preferencesForm")
void configurePreferences(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAllowedFields("nickname", "language");
}
~~~

Giờ client gửi `admin=true` không được setter-binding qua binder này. Quan trọng:

- `setAllowedFields` kiểm soát **property binding**, không đảm bảo mọi constructor arguments bị kiểm soát. Không đưa `admin` vào một data constructor nhận input.
- Allowlist áp dụng cho **property paths**, có thể gồm nested/indexed paths. Kiểm tra chính xác path và pattern, tránh `"*"` quá rộng.
- `setDisallowedFields("admin")` là **blacklist** dễ quên khi thêm field mới, alias hoặc nested path. Spring khuyến nghị **allowedFields** rõ ràng thay cho cách dựa vào blacklist.
- Không dựa vào việc UI ẩn field, HTML disabled control, hoặc JavaScript frontend filter. HTTP client có thể tạo request tùy ý.

### `BindingResult#getSuppressedFields()`

Khi property binding được thực hiện với `allowedFields`, những field không được phép có thể xuất hiện trong:

~~~java
String[] rejectedFields =
        bindingResult.getSuppressedFields();
~~~

Vì thế, nếu policy yêu cầu **từ chối toàn request khi có tham số bị cố tình overpost**, controller có thể làm:

~~~java
if (bindingResult.hasErrors()
        || bindingResult.getSuppressedFields().length > 0) {
    return ResponseEntity.badRequest()
            .body("INVALID_PREFERENCES");
}
~~~

Đây là snippet trong controller. **Không trả tên/raw value của field bị suppressed** nếu chúng là thông tin nội bộ hoặc dữ liệu nhạy cảm. Code chạy đầy đủ ở phần 9 có nhánh này.

**Giới hạn cực kỳ quan trọng:** Nếu `declarativeBinding=true` mà **không cấu hình `allowedFields`**, Spring có thể **bỏ qua hoàn toàn bước property binding**; vì vậy không thể mặc định xem `getSuppressedFields()` là một cơ chế phát hiện tất cả input thừa trong kiểu constructor-only. **Constructor binding bỏ qua những input không cần**, chứ không phải một validator “cấm mọi key lạ”. Muốn API từ chối unknown input, cần thiết kế thêm policy/kiểm tra input keys ở điểm thích hợp.

### Biến thể nested/collection

Ví dụ một form có cấu trúc:

~~~text
address.city=Da Nang
address.postalCode=550000
role.name=ADMIN
items[0].quantity=2
items[1].quantity=3
~~~

Nếu chỉ cho phép địa chỉ và số lượng sản phẩm, hãy nghĩ đến một DTO dành riêng và allowlist theo paths:

~~~java
binder.setAllowedFields(
        "address.city",
        "address.postalCode",
        "items*.quantity");
~~~

Đây là **snippet về policy**, không phải cam kết wildcard hoạt động giống regex; pattern cụ thể được `DataBinder#setAllowedFields` định nghĩa. Nên kiểm thử cả `items[0].quantity`, `items[1].quantity` và các biến thể indexed/mapped path, đặc biệt khi cấu trúc có auto-grow. Không dùng `"address*"` nếu object `address` chứa các field bí mật hoặc server-only.

Giới hạn kích thước collection, chiều sâu nesting và payload size cũng rất quan trọng để tránh DoS. Kiểm tra `setAutoGrowCollectionLimit` và input size limits khi ứng dụng bind cấu trúc phức tạp.

## 6. Bề mặt “mutable” không chỉ nằm ở setter

### 6.1. Constructor có field nhạy cảm vẫn nguy hiểm

Đoạn code sau là **ví dụ sai về thiết kế**:

~~~java
// Đừng dùng kiểu này làm DTO nhận HTTP input.
public record DangerousAccountCommand(
        String displayName,
        String role,
        boolean locked) {
}
~~~

Dù record hoàn toàn immutable, request `role=ADMIN&locked=false` vẫn có thể đi vào **constructor parameters**. Bất biến ở thời điểm sau khởi tạo **không đồng nghĩa input contract an toàn**.

Cách sửa:

~~~java
public record ChangePublicProfile(
        @NotBlank String displayName) {
}
~~~

`role` và `locked` được lấy từ **account đang lưu** hoặc security context bên server, và không xuất hiện trong DTO đầu vào.

### 6.2. Nested mutable object có thể mở rộng phạm vi

Một record như:

~~~java
public record BadInput(
        AccountEntity account) {
}
~~~

vẫn có thể mở một object graph quá rộng nếu Spring được phép thực hiện nested constructor binding hoặc các resolver liên quan. Không “gói” entity có trường nhạy cảm vào record rồi coi đó là an toàn. Dùng nested input DTO nhỏ:

~~~java
public record AddressInput(
        String city,
        String postalCode) {
}

public record UpdateProfileInput(
        String displayName,
        AddressInput address) {
}
~~~

Với collections/maps, cũng cần chọn type của **phần tử**. Một `List<AccountEntity>` có thể nguy hiểm như một entity đơn; thay bằng `List<AccountReferenceInput>` nếu chỉ muốn lấy ID và phải kiểm tra quyền riêng cho từng ID.

### 6.3. Type conversion cũng không phải authorization

Khi Spring parse `@PathVariable Long accountId` hoặc `@ModelAttribute` chứa một value object ID, phép chuyển kiểu chỉ xác nhận **hình thức của ID**. Nó không xác nhận user được xem/sửa account đó. Ví dụ `accountId=7` và `accountId=8` đều có thể là số hợp lệ, nhưng chỉ một tài khoản thuộc quyền của người dùng.

Không nên làm:

~~~java
// Sai về quyền hạn nếu chỉ tin vào ID client.
Account account = repository.findById(accountId)
        .orElseThrow();
account.setRole(request.getRole());
repository.save(account);
~~~

Snippet cố ý minh họa anti-pattern, không phải code chạy độc lập. Hãy kiểm tra ownership/tenant/permissions trong service và chỉ cập nhật field đã được phép.

## 7. `@BindParam`, tên tham số và model attribute binding

Constructor binding lấy giá trị theo tên parameter. Spring hỗ trợ `@BindParam` để ánh xạ tên request khác tên Java:

~~~java
public final class ContactForm {

    private final String contactEmail;

    public ContactForm(
            @BindParam("contact-email")
            String contactEmail) {
        this.contactEmail = contactEmail;
    }

    public String getContactEmail() {
        return contactEmail;
    }
}
~~~

Đây là một **snippet class** cần import `org.springframework.web.bind.annotation.BindParam`. Khi request có `contact-email=lan@example.com`, constructor có thể nhận giá trị qua tham số `contactEmail`. Không cần tạo Java property tên chứa dấu gạch ngang.

**Cảnh báo bảo mật:** `@BindParam` chỉ **đổi tên key dùng cho một constructor argument**. Nó không giới hạn quyền sửa thuộc tính và không làm cho dữ liệu từ key `contact-email` đáng tin. Nếu constructor có tham số `role`, client vẫn có thể cung cấp khi được resolve.

Với Java class thường, để tránh lệ thuộc vào tên tự đoán, giữ compiler parameter metadata (ví dụ `-parameters`) hoặc dùng `@ConstructorProperties`/`@BindParam` theo API Spring phù hợp. Với record, canonical constructor thường cung cấp tên components mà framework có thể dùng.

### Nếu object đã ở trong Model/Session

`@ModelAttribute` có thể lấy object có sẵn từ Model, SessionAttributes hoặc converter phù hợp chứ không phải lúc nào cũng xây mới bằng constructor. Khi đó **property binding** lên object mutable có sẵn có thể quan trọng hơn.

Nếu một object đã được lấy từ DB và chỉ cần truyền vào handler mà **không cho request bind vào object ấy**, có thể dùng:

~~~java
@ModelAttribute("account")
public Account loadAccount(@PathVariable long id) {
    return accountService.findForAuthorizedUser(id);
}

@PostMapping("/accounts/{id}/action")
public ResponseEntity<?> action(
        @ModelAttribute(binding = false) Account account) {
    // Account lấy từ server và không được request property-bind.
    return ResponseEntity.ok().build();
}
~~~

Đây là **snippet kiến trúc**, chưa khai báo `Account`, service và controller imports. `binding=false` ngăn data binding cho argument này; service vẫn phải kiểm tra quyền, và đoạn code không được hiểu là tự tạo authentication/authorization. Với ứng dụng thật, tránh để entity được render/serialize trực tiếp ra client nếu có field server-only.

## 8. `@ModelAttribute` khác `@RequestBody`: cùng DTO nhưng pipeline khác

**Spring MVC `@ModelAttribute`:**

- Dùng `WebDataBinder`, constructor binding và có thể property binding.
- Nhận form/query request parameters (và có thể path/header theo quy tắc Spring).
- `@InitBinder`, `setDeclarativeBinding`, `setAllowedFields` áp dụng cho binder này.
- `@Valid` có thể đưa errors vào `BindingResult`, nếu đặt ngay sau parameter.
- Nếu không có `BindingResult` liền kề, một individual argument validation failure thường dẫn đến `MethodArgumentNotValidException`.

**Spring MVC `@RequestBody`:**

- JSON được đọc qua `HttpMessageConverter`/Jackson.
- Jackson có cách riêng để chọn constructor/creator và xử lý unknown JSON properties.
- **`setDeclarativeBinding(true)` và `setAllowedFields(...)` của WebDataBinder không phải JSON property allowlist**.
- Chỉ dùng request DTO riêng cũng làm giảm surface, nhưng nếu cần **từ chối key JSON thừa**, phải cấu hình Jackson/deserialization và tests cho hợp đồng JSON.
- `@Valid @RequestBody` vẫn có thể dùng Spring Validator/Bean Validation sau khi object đã được deserialize.

Ví dụ:

~~~java
@PostMapping(path = "/profile-json",
             consumes = MediaType.APPLICATION_JSON_VALUE)
ResponseEntity<?> json(
        @Valid @RequestBody AccountChangeForm form) {
    // Jackson tạo record từ JSON, không dùng setter-binding
    // của @ModelAttribute để chọn các thuộc tính.
    return ResponseEntity.ok().build();
}
~~~

Snippet dành cho controller. Trong ứng dụng Spring Boot, chính sách mặc định với **unknown JSON properties** có thể khác theo ObjectMapper, annotations và version. **Không dùng việc JSON vô tình bỏ qua key lạ để kết luận API đã thực thi một strict input schema**. Kiểm thử rõ nếu bạn muốn trả 400 với mọi unknown key.

### Không dùng entity JPA làm request DTO

JPA entities thường có no-arg constructor, setters và nhiều quan hệ lồng nhau để phục vụ persistence. Đây là cấu trúc không phù hợp cho một form public có bề mặt nhỏ. Dùng:

~~~text
HTTP form/JSON
  -> request DTO/record (chỉ field public)
  -> @Valid + conversion
  -> authentication/authorization
  -> service: load existing entity
  -> update explicit allowed fields
  -> save
  -> response DTO riêng
~~~

Trong hướng cập nhật này, `role`, `tenantId`, `accountId`, `locked` được server quản lý, không lấy từ request DTO chỉ vì client gửi thêm keys.

## 9. Ví dụ chạy được: Spring Boot 3.2+, Java 17+, REST form và JSON

Demo gồm **hai dạng binding**:

1. `AccountChangeForm` là record có constructor chỉ nhận hai thuộc tính công khai; binder áp dụng **constructor-only**.
2. `PreferencesForm` là JavaBean có setters; binder chỉ cho phép hai property bằng **`allowedFields`** và từ chối request có suppressed fields.

Demo có thêm endpoint JSON để minh họa Jackson `@RequestBody` **không dùng property allowlist của form binder**.

**Giới hạn quan trọng:** Để chạy không cần database, `AccountService` tạo một snapshot demo hiện có và trả snapshot mới; **không lưu thật, không xác thực user**. Trong production, phải thay bằng repository/service thực với authentication, authorization, tenant isolation, optimistic locking/transactions khi phù hợp. Demo chỉ chứng minh **bề mặt binding**, không chứng minh bảo mật toàn ứng dụng.

### 9.1. Maven dependencies

Tạo project Spring Boot **3.2+** (Spring Framework **6.1+**), Java 17+, Maven. Dùng parent/BOM Spring Boot và các dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Dự án cần Maven plugin/parent của Spring Boot theo setup thông thường. Không thêm security starter vào demo để tests chỉ đo binding behavior; khi bật security trên production, cần xác thực và CSRF policy riêng.

Các Java files dưới `src/main/java/com/example/safebinding/`; file test dưới `src/test/java/com/example/safebinding/`.

### 9.2. `SafeBindingApplication.java`

~~~java
package com.example.safebinding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeBindingApplication {

    public static void main(String[] args) {
        SpringApplication.run(SafeBindingApplication.class, args);
    }
}
~~~

### 9.3. `AccountChangeForm.java`: input record bất biến

~~~java
package com.example.safebinding;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public record AccountChangeForm(
        @NotBlank String displayName,
        @NotBlank @Email String contactEmail) {
}
~~~

**Chỉ hai constructor parameters**. Không có `role`, `locked`, `tenantId` hoặc `id` trong DTO. Ràng buộc `@NotBlank`/`@Email` là validation; chúng **không cấp quyền**. Nếu form hợp lệ, service mới quyết định account nào được sửa.

### 9.4. `PreferencesForm.java`: JavaBean mutable có field không cho sửa

~~~java
package com.example.safebinding;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public class PreferencesForm {

    @NotBlank
    private String nickname;

    @NotBlank
    @Pattern(regexp = "vi|en")
    private String language;

    private boolean admin;

    public PreferencesForm() {
    }

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }

    public String getLanguage() {
        return language;
    }

    public void setLanguage(String language) {
        this.language = language;
    }

    public boolean isAdmin() {
        return admin;
    }

    public void setAdmin(boolean admin) {
        this.admin = admin;
    }
}
~~~

`admin` cố ý có setter để mô phỏng một DTO kế thừa/legacy có nhiều writable fields; endpoint chỉ được nhận `nickname`, `language`. **Đừng xem class này là model lý tưởng cho production**: nên bỏ hẳn `admin` khỏi request DTO nếu có thể. Chúng ta giữ nó trong demo để **kiểm chứng `setAllowedFields` thật sự chặn field overposting**.

### 9.5. `AccountSnapshot.java`: đối tượng do server quản lý

~~~java
package com.example.safebinding;

public record AccountSnapshot(
        long id,
        String displayName,
        String contactEmail,
        String role,
        boolean locked) {
}
~~~

Type này **không được dùng làm `@ModelAttribute` hoặc `@RequestBody`**. Nó chỉ đại diện snapshot có các field do server kiểm soát. Demo trả `role`/`locked` để test dễ nhìn. Trong API production, không trả các trường nhạy cảm/không cần thiết chỉ để chứng minh chúng không bị sửa.

### 9.6. `AccountService.java`: cập nhật chọn lọc sau khi bind

~~~java
package com.example.safebinding;

import org.springframework.stereotype.Service;

@Service
public class AccountService {

    public AccountSnapshot updatePublicProfile(
            long accountId, AccountChangeForm input) {

        // DEMO: giả lập account đã được load từ server.
        // Production: authenticate, authorize, load + persist.
        AccountSnapshot existing = new AccountSnapshot(
                accountId,
                "Existing",
                "existing@example.com",
                "MEMBER",
                true);

        // Chỉ thay đổi hai trường có trong input contract.
        return new AccountSnapshot(
                existing.id(),
                input.displayName(),
                input.contactEmail(),
                existing.role(),
                existing.locked());
    }
}
~~~

Code giữ nguyên **`id`, `role`, `locked`** từ server-side snapshot, không đọc chúng từ form. Với ứng dụng thật, trước khi gọi update phải kiểm tra người dùng hiện tại có quyền sửa đúng account ID và tenant. API có role hay account ID không có nghĩa chúng là bằng chứng xác thực.

### 9.7. `AccountController.java`: hai binder policies trong cùng controller

~~~java
package com.example.safebinding;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api")
public class AccountController {

    private final AccountService accountService;

    public AccountController(AccountService accountService) {
        this.accountService = accountService;
    }

    @InitBinder("changeForm")
    public void bindImmutableProfile(WebDataBinder binder) {
        // Chỉ constructor binding cho AccountChangeForm.
        binder.setDeclarativeBinding(true);
    }

    @InitBinder("preferencesForm")
    public void bindMutablePreferences(WebDataBinder binder) {
        // Cho phép setter binding của hai property, không phải admin.
        binder.setDeclarativeBinding(true);
        binder.setAllowedFields("nickname", "language");
    }

    @PostMapping(
            path = "/accounts/{id}/profile",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> updateProfileForm(
            @PathVariable("id") long id,
            @Valid @ModelAttribute("changeForm")
                    AccountChangeForm change,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("code", "INVALID_PROFILE"));
        }

        // Đây chỉ là demo; authorization phải làm ở service thật.
        return ResponseEntity.ok(
                accountService.updatePublicProfile(id, change));
    }

    @PostMapping(
            path = "/preferences",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> updatePreferences(
            @Valid @ModelAttribute("preferencesForm")
                    PreferencesForm form,
            BindingResult errors) {

        if (errors.hasErrors()
                || errors.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                    .body(Map.of("code", "INVALID_PREFERENCES"));
        }

        return ResponseEntity.ok(Map.of(
                "nickname", form.getNickname(),
                "language", form.getLanguage(),
                "admin", form.isAdmin()));
    }

    @PostMapping(
            path = "/accounts/{id}/profile-json",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> updateProfileJson(
            @PathVariable("id") long id,
            @Valid @RequestBody AccountChangeForm change) {

        // Jackson deserializes @RequestBody.
        // @InitBinder allowedFields is not its JSON input allowlist.
        return ResponseEntity.ok(
                accountService.updatePublicProfile(id, change));
    }
}
~~~

**Đọc kỹ những khác biệt trong code:**

- `@InitBinder("changeForm")` được ghép với `@ModelAttribute("changeForm")`. Flag `true` cho **constructor binding**, không cho property binding tùy ý.
- `AccountChangeForm` có **hai** components; input `role=ADMIN` hay `locked=false` không trở thành field trong record, nên không đi tới service update.
- `@InitBinder("preferencesForm")` ghép với `@ModelAttribute("preferencesForm")`. Với `setAllowedFields("nickname","language")`, property binding chỉ áp dụng cho hai field này.
- `BindingResult` ở **ngay sau đối tượng `@ModelAttribute`** cho phép controller xử lý lỗi validation/binding.
- Ở `/preferences`, `getSuppressedFields()` được kiểm tra để **trả 400** khi có overposted setter property. Không đưa giá trị bị từ chối ra JSON.
- `/profile-json` dùng `@RequestBody` và Jackson; dù DTO giống nhau, policy `WebDataBinder` của `@ModelAttribute` **không phải** JSON-deserializer policy.
- Dù form được bind an toàn, authorization vẫn chưa có trong demo; không dùng endpoint này cho người dùng thật trước khi thêm kiểm tra quyền.

## 10. Kiểm thử tích hợp bằng MockMvc: “không bind” khác “không hợp lệ”

Tạo `src/test/java/com/example/safebinding/SafeBindingApplicationTest.java`:

~~~java
package com.example.safebinding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class SafeBindingApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void recordConstructorBindsOnlyPublicFields() throws Exception {
        mvc.perform(post("/api/accounts/7/profile")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan")
                    .param("contactEmail", "lan@example.com"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.displayName").value("Lan"))
                .andExpect(jsonPath("$.contactEmail")
                        .value("lan@example.com"))
                .andExpect(jsonPath("$.role").value("MEMBER"))
                .andExpect(jsonPath("$.locked").value(true));
    }

    @Test
    void overpostedRoleAndLockedCannotChangeServerState()
            throws Exception {
        mvc.perform(post("/api/accounts/7/profile")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan")
                    .param("contactEmail", "lan@example.com")
                    .param("role", "ADMIN")
                    .param("locked", "false")
                    .param("tenantId", "999"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.role").value("MEMBER"))
                .andExpect(jsonPath("$.locked").value(true))
                .andExpect(jsonPath("$.id").value(7));
    }

    @Test
    void recordConstructorDoesNotAcceptIdOverpost()
            throws Exception {
        mvc.perform(post("/api/accounts/7/profile")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan")
                    .param("contactEmail", "lan@example.com")
                    .param("id", "999"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(7));
    }

    @Test
    void invalidDisplayNameFailsBeanValidation()
            throws Exception {
        mvc.perform(post("/api/accounts/7/profile")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "")
                    .param("contactEmail", "lan@example.com"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_PROFILE"));
    }

    @Test
    void malformedEmailFailsBeanValidation()
            throws Exception {
        mvc.perform(post("/api/accounts/7/profile")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan")
                    .param("contactEmail", "not-an-email"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_PROFILE"));
    }

    @Test
    void missingConstructorArgumentFailsValidation()
            throws Exception {
        mvc.perform(post("/api/accounts/7/profile")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_PROFILE"));
    }

    @Test
    void allowedMutableFieldsAreBound() throws Exception {
        mvc.perform(post("/api/preferences")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("nickname", "Mai")
                    .param("language", "vi"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.nickname").value("Mai"))
                .andExpect(jsonPath("$.language").value("vi"))
                .andExpect(jsonPath("$.admin").value(false));
    }

    @Test
    void disallowedAdminSetterIsSuppressedAndRejected()
            throws Exception {
        mvc.perform(post("/api/preferences")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("nickname", "Mai")
                    .param("language", "vi")
                    .param("admin", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_PREFERENCES"));
    }

    @Test
    void invalidLanguageFailsValidation() throws Exception {
        mvc.perform(post("/api/preferences")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("nickname", "Mai")
                    .param("language", "xx"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_PREFERENCES"));
    }

    @Test
    void missingMutableFieldFailsValidation() throws Exception {
        mvc.perform(post("/api/preferences")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("language", "vi"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_PREFERENCES"));
    }

    @Test
    void validJsonRecordUsesJackson() throws Exception {
        mvc.perform(post("/api/accounts/7/profile-json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "displayName":"Lan",
                              "contactEmail":"lan@example.com"
                            }
                            """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.role").value("MEMBER"))
                .andExpect(jsonPath("$.displayName").value("Lan"));
    }

    @Test
    void invalidJsonRecordUsesBodyValidation() throws Exception {
        mvc.perform(post("/api/accounts/7/profile-json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "displayName":"",
                              "contactEmail":"not-an-email"
                            }
                            """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void mismatchedContentTypeIsUnsupported()
            throws Exception {
        mvc.perform(post("/api/accounts/7/profile")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"displayName":"Lan"}
                            """))
                .andExpect(status().isUnsupportedMediaType());
    }
}
~~~

**13 integration tests** được thiết kế cho demo. Với Spring Boot 3.2+ MVC/Validation/Test:

- Test overposting **không yêu cầu** constructor-only endpoint trả 400 với mọi key thừa. Nó kiểm chứng rằng **server-owned fields vẫn giữ nguyên** khi request gửi `role=ADMIN`/`locked=false`.
- Test `/preferences` ngược lại chủ động trả **400** khi có suppressed property. Đó là policy của controller, không phải kết luận rằng constructor binding cũng làm vậy.
- Tests `@Valid` xác nhận input DTO được kiểm tra sau khi bind.
- Test JSON cho thấy Jackson có thể đọc record với constructor của riêng nó; binder allowlist form không phải JSON input whitelist.
- HTTP 415 test chỉ xác minh `consumes` contract.

Chạy:

~~~bash
./mvnw test -Dtest=SafeBindingApplicationTest
~~~

Trên Windows có Maven wrapper:

~~~powershell
mvnw.cmd test -Dtest=SafeBindingApplicationTest
~~~

Nếu có Maven toàn cục, dùng `mvn test -Dtest=SafeBindingApplicationTest`. Những test này không yêu cầu database/remote APIs. **Không coi việc test pass là chứng minh authorization**: service mô phỏng đã cố ý không triển khai security.

### Kết quả điển hình

| Request | HTTP | Điều đáng kiểm chứng |
| --- | --- | --- |
| Form hợp lệ `displayName=Lan&contactEmail=lan@example.com` | 200 | DTO nhận hai field công khai. |
| Form thêm `role=ADMIN&locked=false&tenantId=999` | 200 | `role=MEMBER`, `locked=true`, `id` vẫn từ path. |
| Form thêm `id=999`, URL `/accounts/7` | 200 | Snapshot vẫn có `id=7`. |
| `displayName=""` hoặc email sai | 400 | `@Valid` phát hiện input lỗi. |
| Preferences hợp lệ | 200 | Chỉ nickname/language được bind, admin vẫn false. |
| Preferences thêm `admin=true` | 400 | Property không nằm trong allowlist bị suppressed. |
| Preferences `language=xx` | 400 | `@Pattern` fail. |
| JSON record hợp lệ | 200 | Jackson deserialize, validation thành công. |
| JSON record sai constraint | 400 | Bean Validation trên `@RequestBody`. |
| JSON gửi vào mapping chỉ nhận form | 415 | Media type không hỗ trợ. |

Với dữ liệu thực, không trả `role`, `locked` hay `tenantId` nếu public API không cần; demo có chúng để **minh họa rõ tính bất biến của server-owned state**.

## 11. Unit test cho chính `DataBinder#setDeclarativeBinding`

Để kiểm tra sự khác biệt của cờ `declarativeBinding` **không qua HTTP**, dùng `DataBinder` trên JavaBean mutable.

Tạo file `src/test/java/com/example/safebinding/DataBinderPolicyTest.java`:

~~~java
package com.example.safebinding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class DataBinderPolicyTest {

    @Test
    void declarativeModeWithoutAllowedFieldsSkipsSetters() {
        PreferencesForm form = new PreferencesForm();
        DataBinder binder = new DataBinder(form, "preferencesForm");

        binder.setDeclarativeBinding(true);
        binder.bind(new MutablePropertyValues(Map.of(
                "nickname", "Lan",
                "admin", "true")));

        // No constructor arguments on this mutable bean;
        // declarative mode does not setter-bind these inputs.
        assertNull(form.getNickname());
        assertFalse(form.isAdmin());
    }

    @Test
    void allowedFieldsEnableOnlySelectedSetterBinding() {
        PreferencesForm form = new PreferencesForm();
        DataBinder binder = new DataBinder(form, "preferencesForm");

        binder.setDeclarativeBinding(true);
        binder.setAllowedFields("nickname");

        binder.bind(new MutablePropertyValues(Map.of(
                "nickname", "Lan",
                "admin", "true")));

        assertEquals("Lan", form.getNickname());
        assertFalse(form.isAdmin());
        assertArrayEquals(new String[] {"admin"},
                binder.getBindingResult().getSuppressedFields());
    }

    @Test
    void unconstrainedPropertyBindingCanSetSensitiveSetter() {
        PreferencesForm form = new PreferencesForm();
        DataBinder binder = new DataBinder(form, "preferencesForm");

        // Anti-pattern: default mode without allowedFields.
        binder.bind(new MutablePropertyValues(Map.of(
                "nickname", "Lan",
                "admin", "true")));

        // Demonstrates WHY a binder policy matters.
        assertEquals("Lan", form.getNickname());
        assertTrue(form.isAdmin());
    }
}
~~~

Đây là **ba tests minh họa hành vi binder**, không phải đề xuất sử dụng binder thiếu allowlist trong production. Test thứ ba cố ý tạo một binding không an toàn để **chứng minh bề mặt setter mặc định**; việc assert `admin==true` là dự kiến trong test anti-pattern.

Chạy chỉ unit tests:

~~~bash
./mvnw test -Dtest=DataBinderPolicyTest
~~~

Hoặc chạy cả **16 tests** (13 MVC + 3 binder):

~~~bash
./mvnw test -Dtest=SafeBindingApplicationTest,DataBinderPolicyTest
~~~

Kết quả của `DataBinder.bind(...)` không tự chứng minh Bean Validation `@NotBlank` đã chạy: để kiểm tra constraints, cần đăng ký validator/gọi `validate()` trong unit test hoặc dùng `@Valid` trên MVC handler như ở phần 10.

## 12. Trường hợp đặc biệt: constructor-only có thể bỏ qua input thừa

Trong một số hệ thống, policy yêu cầu **cấm hoàn toàn unknown parameters**, không chỉ ngăn chúng thay đổi state. Cần phân biệt:

- **Không có bề mặt để gán**: record constructor chỉ chứa hai fields và mọi field khác không được sử dụng.
- **Phát hiện có extra key**: request parser/argument resolver/validation policy quan sát toàn bộ keys và so với whitelist.
- **Từ chối bằng HTTP 400**: controller/advice trả lỗi khi phát hiện key ngoài schema.

`setDeclarativeBinding(true)` đảm bảo hạn chế property binding; nó **không phải một thiết bị xác thực schema input keys**. Đừng viết test “unknown key chắc chắn 400” nếu code chỉ dùng constructor-only binding và không có policy riêng.

Nếu cần strict form input contract, có thể:

1. Định nghĩa allowlist input keys cho route, có xét field markers, indexed paths và framework parameters.
2. Dùng filter/interceptor/service parser thích hợp để so sánh request names, trả 400 nếu xuất hiện key ngoài.
3. Vẫn dùng dedicated input DTO và declarative binding để bảo vệ state ngay cả khi filter bị cấu hình sai.
4. Viết tests với query/form mix, duplicate keys, casing, percent-encoding, nested paths và multipart.

Với JSON, strict unknown fields thường được cấu hình **ở Jackson/ObjectMapper** (hoặc annotation cụ thể), không phải bằng `WebDataBinder#setAllowedFields`. Hãy cân nhắc backwards compatibility trước khi bật reject-unknown toàn API.

### Constructor có thể nhận collection/nested arguments

Spring constructor binding hỗ trợ lists, maps, arrays và indexed keys trong những trường hợp phù hợp. Ví dụ input name:

~~~text
items[0].sku=P01
items[0].quantity=2
items[1].sku=P02
items[1].quantity=3
~~~

Đừng cho rằng vì top-level DTO là record thì không có cách nào tạo graph con. Nếu command constructor khai báo `List<ItemInput>`, framework có thể tạo nhiều `ItemInput` từ các indexed request values.

Bề mặt cho phép cần xem **từng nested DTO/constructor component**, không chỉ top-level class. Giới hạn collection growth, nesting depth và request size; không cho phép nested entity có `role`/`tenantId` chỉ vì nó nằm trong list.

## 13. Phân biệt bảo vệ bằng binding với các tầng khác

### 13.1. Validation không loại bỏ mass assignment

~~~java
public record UnsafeUpdate(
        @NotBlank String displayName,
        @NotBlank String role) {
}
~~~

Nếu role `"ADMIN"` là chuỗi không trống, `@NotBlank` **đạt**. Nhưng đó vẫn là giá trị client **không được phép tự đặt**. Không thể dùng `@Valid` để thay policy field-level authorization.

### 13.2. Authorization không thay thế schema nhỏ

Ngay cả khi client đã đăng nhập, user có thể chỉ được phép đổi email, không phải role hay tenant. “Đã xác thực” ≠ “được phép sửa mọi field”. Service phải kiểm tra action/resource/tenant và update **chọn lọc** các field đã được approved.

### 13.3. Concurrency, idempotency và transaction

Một request bind đúng DTO vẫn có thể ghi đè thay đổi từ request khác. Nếu dữ liệu cần tránh lost update, cân nhắc optimistic locking (`@Version`) hoặc concurrency policy trong service. Không có cơ chế constructor binding nào tự giải quyết race conditions.

Với patch/partial update, cần phân biệt:

- field **không gửi**;
- field **gửi null/blank**;
- field muốn **xóa giá trị**.

Một record chứa nullable components đơn giản có thể không đủ để phân biệt ba trạng thái. Có thể dùng DTO patch chuyên biệt với presence tracking, JSON Patch/Merge Patch và rules rõ ràng. Đừng suy rằng constructor binding tự giải quyết semantics PATCH.

### 13.4. Tránh bind entity đang quản lý bởi JPA

Một entity có thể đang ở trong persistence context. Property binding trực tiếp lên entity có thể khiến thay đổi của client được dirty-check và flush dù controller chưa gọi setter thủ công. Đây là rủi ro nghiêm trọng vì bề mặt thay đổi ngầm. Dùng input DTO, load entity ở service dưới quyền thích hợp rồi gán **từng field cho phép**.

### 13.5. Không dựa vào field visibility/HTML disabled

HTML field `disabled` hoặc hidden input vẫn là dữ liệu client có thể sửa/gửi thủ công. Java field `private` cũng có thể có public setter; Spring BeanWrapper có thể dùng setter đó. Bảo vệ phải nằm tại **server input contract và service**, không nằm ở widget frontend.

## 14. Bảo mật message, logs và error handling

Nếu client cố gửi `role=ADMIN` hoặc field lạ, tránh ghi toàn bộ form/query vào log:

~~~java
// Không nên dùng ở production:
logger.warn("Rejected input = {}", request.getParameterMap());
logger.warn("Validation result = {}", bindingResult);
~~~

Thông báo an toàn hơn:

~~~java
logger.warn("Rejected profile update: route={}, code={}",
        "/api/accounts/{id}/profile",
        "INVALID_INPUT");
~~~

Đây là snippet có `logger` giả định. Không đưa password, token, email hoặc rejected values vào telemetry mặc định. Nếu muốn lưu audit event vì overposting, phân loại theo mã và metadata an toàn, tuân thủ retention/access policy.

Với `BindingResult`, có thể nhận errors từ conversion/validation nhưng không nên serialize thẳng toàn bộ `FieldError` vì `getRejectedValue()` có thể chứa dữ liệu nhạy cảm. Response public dùng mã chung hoặc danh sách field names đã whitelist.

### Phân biệt mã HTTP

| Nguyên nhân | HTTP phù hợp thường gặp |
| --- | --- |
| Missing `displayName`, `@NotBlank` fail | 400 |
| Invalid email/locale format | 400 |
| Setter overposting theo policy yêu cầu từ chối | 400 |
| Client không có quyền sửa account | 403 (hoặc policy phù hợp để không lộ resource) |
| Account ID không tồn tại | 404 |
| Concurrent update conflict | 409 |
| Lỗi DB/implementation | 5xx |

Không tự convert mọi lỗi thành 400. Đặc biệt, fail authorization phải được kiểm tra độc lập với form binding.

## 15. Spring WebFlux và Java record

Spring WebFlux cũng có `@ModelAttribute` và `WebDataBinder`, hỗ trợ constructor binding và cơ chế giới hạn property binding. Các nguyên tắc **dedicated DTO, declarative binding, allowedFields và authorization** vẫn áp dụng, nhưng nguồn HTTP input và exception pipeline **khác Servlet MVC**:

- WebFlux `@RequestParam` **chỉ lấy query parameters**; form data có thể bind qua `@ModelAttribute` hoặc đọc bằng `ServerWebExchange#getFormData()`.
- WebFlux validation có `WebExchangeBindException` và có thể có `HandlerMethodValidationException` theo signature/version.
- JSON `@RequestBody Mono<Dto>` dùng reactive codecs/`HttpMessageReader` chứ không phải setter binding của `@ModelAttribute`.
- Converter/validator trong WebFlux nên nhanh, không làm JDBC/HTTP blocking trên event loop.

Bài chạy đầy đủ ở phần 9 dùng **Servlet MVC + MockMvc**, vì thế không dùng các tests ấy làm bằng chứng WebFlux form binding có semantics giống MVC. Với WebFlux, hãy viết `WebTestClient` integration tests tương ứng và xác minh binder policy cho từng endpoint.

## 16. Các lỗi thường gặp và cách khắc phục

| Anti-pattern | Rủi ro | Cách sửa |
| --- | --- | --- |
| `@ModelAttribute AccountEntity account` trên form chỉnh tên | Client có thể gửi `role`/`locked`/`tenantId`. | Dedicated request DTO, update chọn lọc trong service. |
| Constructor record chứa `role` hoặc `tenantId` | Client vẫn bind được các constructor arguments đó. | Chỉ đưa public mutable fields vào constructor. |
| Có primary constructor nên nghĩ setters bị vô hiệu hóa | Mặc định Spring có thể áp dụng **cả constructor lẫn property binding**. | `setDeclarativeBinding(true)` và/hoặc `setAllowedFields`. |
| Bật declarative mode trên bean no-arg nhưng không allowlist | Không nhận setter fields dù UI gửi đúng. | Đổi sang data constructor hoặc thêm `allowedFields`. |
| Dùng blacklist `setDisallowedFields("role")` | Khi entity thêm field mới, blacklist không bao phủ. | Allowlist rõ ràng; ưu tiên DTO nhỏ. |
| Dùng `setAllowedFields` để “khóa” constructor argument | Allowed fields áp dụng cho property binding, không chặn dữ liệu trong constructor. | Thiết kế constructor/DTO đúng contract. |
| Dùng `getSuppressedFields()` làm detector unknown key ở mọi mode | Constructor-only không hứa trả tất cả unknown input trong suppressed list. | Strict request-keys validator độc lập nếu cần. |
| Nghĩ `@Valid` chặn người dùng tự đổi role | Validation kiểm tra format/invariant, không quyết định quyền. | Authorization ở service; DTO không có role. |
| Cho rằng request ID trong path là ID đáng tin | Path variable vẫn do client chọn. | Kiểm tra ownership/tenant và resource access. |
| Dùng binder allowlist để bảo vệ Jackson `@RequestBody` | JSON dùng deserializer, không đi qua property binder tương ứng. | DTO + Jackson policy + tests. |
| Cho nested entity/map tự do vào DTO | Bề mặt thay đổi mở rộng sang object graph. | Nested DTO nhỏ; limit path, collection và size. |
| Bật global `declarativeBinding` mà không test | Các form JavaBeans có thể ngừng setter binding. | Migration plan, endpoint tests, áp dụng có chủ đích. |
| Response trả nguyên entity/BindingResult | Lộ server-owned fields hoặc rejected input. | Response DTO + redaction/whitelist. |
| Viết tests chỉ cho UI hợp lệ | Không phát hiện overposting bằng HTTP client tùy ý. | Thêm tests gửi role, locked, tenant, indexed paths. |

## 17. Checklist trước khi phát hành

- [ ] Input form và JSON dùng **dedicated DTO**, không bind JPA entity/domain object quá rộng.
- [ ] DTO/constructor **không chứa** `role`, `tenantId`, `locked`, `isAdmin` hoặc server-owned ID khi client không được phép đặt.
- [ ] Kiểm tra cả nested DTO, collections và constructor args để tránh mở surface qua object graph.
- [ ] Với `@ModelAttribute` muốn constructor-only, áp dụng `@InitBinder` + `setDeclarativeBinding(true)` trên đúng model attribute.
- [ ] Với mutable JavaBean, cấu hình `setAllowedFields` tường minh và kiểm thử suppressed fields.
- [ ] Không nhầm `allowedFields` (property binding) với allowlist constructor parameters.
- [ ] Không nhầm việc **bỏ qua input thừa** với chính sách **trả 400 khi có unknown key**.
- [ ] Nếu cần strict schema, có input-key validation/Jackson config riêng và regression tests.
- [ ] Với record/class constructor, tên parameters và `@BindParam` được biên dịch/đọc đúng.
- [ ] `@Valid`/`@Validated` kiểm tra format/business constraints cục bộ sau binding, không thay thế authorization.
- [ ] Service load resource dưới authentication/authorization phù hợp và chỉ gán approved fields.
- [ ] Có tests form happy path, overposted role/locked/tenant/id, missing/invalid values, mutable allowlist và JSON.
- [ ] Bảo vệ JPA managed entities khỏi request binding, kiểm soát transaction, concurrency và PATCH semantics.
- [ ] Response dùng DTO riêng, không lộ server-owned fields hay rejected values.
- [ ] Với WebFlux, test riêng bằng `WebTestClient` và không blocking trong converter/validator.
- [ ] Cấu hình binder global phải có migration plan và regression tests để tránh làm form cũ mất dữ liệu.

**Kết luận:** Spring constructor binding là công cụ mạnh để **thu hẹp bề mặt HTTP input được phép gán**. Nhưng **bản thân constructor không phân quyền**: chỉ những arguments xuất hiện trong một **request DTO được thiết kế đúng** mới nên do client cung cấp. Kết hợp `setDeclarativeBinding(true)` để tránh setter binding ngoài chủ đích, `setAllowedFields` nếu còn JavaBean mutable, `@Valid` để kiểm tra dữ liệu và **authorization + selective update** ở service để bảo vệ trạng thái server. Thiết kế đó giải quyết mass assignment tốt hơn nhiều so với việc chỉ ẩn ô form hoặc blacklist một vài field.

## Tài liệu tham khảo

- Spring Framework Reference 6.2 — **MVC @ModelAttribute Argument** (constructor/property binding, `@BindParam`): https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework Reference 6.2 — **MVC @InitBinder và Model Design** (allowedFields, declarative binding): https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework Reference — **Core Data Binding** (constructor vs property): https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html
- Spring Framework Javadoc 6.2 — **DataBinder#setDeclarativeBinding / setAllowedFields**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework Reference — **MVC Data Binding** (nội dung bảo mật và property paths): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
- Spring Framework Reference 6.2 — **WebFlux @ModelAttribute**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/modelattrib-method-args.html
- Spring Framework Reference — **MVC Validation**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- OWASP Cheat Sheet — **Mass Assignment**: https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html
