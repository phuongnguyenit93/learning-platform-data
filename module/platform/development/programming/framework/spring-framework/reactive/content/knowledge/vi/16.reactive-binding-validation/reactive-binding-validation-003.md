# Constructor binding và giới hạn thuộc tính được phép cập nhật trong Spring WebFlux

## 1. Vấn đề bảo mật: mass assignment / over-posting

Một controller thường nhận dữ liệu do client gửi để tạo hoặc cập nhật tài nguyên. Nếu Spring bind request trực tiếp vào một object có nhiều thuộc tính hơn những gì endpoint cho phép, client có thể thử gửi thêm các trường mà giao diện bình thường không hiển thị.

Ví dụ một entity tài khoản:

~~~java
public class Account {
    private Long id;
    private String displayName;
    private String email;
    private String role;
    private boolean enabled;
    private boolean emailVerified;
    private Long ownerId;

    // getters và setters
}
~~~

Endpoint chỉ định cho người dùng đổi tên và email:

~~~text
POST /accounts/42/edit

displayName=Alice
email=alice@example.com
role=ADMIN
enabled=true
ownerId=1
~~~

Nếu bind thẳng vào một object có setter cho tất cả các thuộc tính, các trường như `role`, `enabled` hoặc `ownerId` có thể bị thay đổi dù chức năng chỉ định cho phép sửa tên và email. Đây là nhóm lỗi thường gọi là **mass assignment**, **over-posting** hoặc **broken object property level authorization**.

Điều quan trọng là phân biệt ba câu hỏi:

1. **Binding**: client đã gửi giá trị nào và Spring đưa chúng vào object ra sao?
2. **Validation**: giá trị có đúng định dạng và quy tắc dữ liệu không?
3. **Authorization / business rule**: người dùng hiện tại có quyền sửa thuộc tính hoặc tài nguyên đó không?

Một giá trị hợp lệ về kiểu và validation vẫn có thể **không được phép cập nhật**. Ví dụ chuỗi `ADMIN` là một role hợp lệ, nhưng người dùng thông thường không có quyền tự gán role đó.

Spring cung cấp hai công cụ quan trọng để kiểm soát binding:

- **Constructor binding**: chỉ tạo object từ những tham số mà constructor khai báo.
- **`WebDataBinder.setAllowedFields(...)`**: dùng allowlist để giới hạn các property được phép nhận dữ liệu khi property/setter binding được bật.

Với dữ liệu web, ưu tiên DTO dành riêng cho request và constructor bất biến; nếu thật sự cần property binding, hãy khai báo danh sách cho phép cụ thể.

## 2. Data binding trong WebFlux áp dụng cho loại request nào?

Trong controller có annotation, `@ModelAttribute` là điểm vào phổ biến cho data binding. Spring WebFlux có thể bind các nguồn sau vào model object:

- Form data, ví dụ `application/x-www-form-urlencoded`.
- Query parameters trong URL.
- URI path variables.
- Request headers theo quy tắc binding của Spring.

Khi các nguồn có cùng tên, **form data và query parameters có ưu tiên cao hơn URI variables và headers**; URI variables và headers chỉ được dùng khi không bị request parameters cùng tên ghi đè. Header name được xử lý bằng cách bỏ dấu gạch nối.

Ví dụ:

~~~java
@PostMapping("/tenants/{tenantId}/profile")
Mono<String> update(
        @ModelAttribute ProfileForm form) {
    return Mono.just(form.toString());
}
~~~

Với `@ModelAttribute`, Spring tạo hoặc lấy object model, rồi bind các giá trị request phù hợp vào object đó.

**Không nhầm `@ModelAttribute` với `@RequestBody`.**

| Cách nhận dữ liệu | Cơ chế chính | Ví dụ |
| --- | --- | --- |
| `@ModelAttribute` | `WebDataBinder`: constructor binding và/hoặc property binding | Form, query parameter, URI variable, header |
| `@RequestBody` | `HttpMessageReader` và HTTP message codec để giải mã body | JSON/XML thành DTO |
| `@RequestParam` | Bind một query parameter (hoặc map query parameters) | `?page=2` |
| `@PathVariable` | Lấy giá trị URI template variable | `/orders/{id}` |

**`allowedFields` là cấu hình của WebDataBinder cho property binding của model attribute. Nó không phải allowlist tự động cho JSON được giải mã qua `@RequestBody`.** Với JSON, vẫn cần request DTO riêng, kiểm soát kiểu dữ liệu được deserialize và mapping rõ ràng sang command/domain object.

Trong functional endpoint, WebFlux có API `ServerRequest.bind` và các overload tương ứng để bind dữ liệu. Các nguyên tắc thiết kế object và giới hạn input vẫn cần được áp dụng ở ranh giới đó.

## 3. Hai chiến lược binding: constructor và property

Spring `DataBinder` hỗ trợ hai cách tạo/cập nhật object.

### 3.1. Constructor binding

Constructor binding lấy giá trị request theo tên tham số constructor rồi gọi constructor để tạo object. Với một Java record:

~~~java
public record ChangeEmailForm(
        String currentEmail,
        String newEmail) {
}
~~~

Spring có thể tạo object từ các giá trị `currentEmail` và `newEmail`. Những request parameter khác như `role` hoặc `enabled` không phải tham số constructor nên không được đưa vào object qua constructor binding.

Constructor binding phù hợp với object:

- Có trạng thái bất biến sau khi tạo.
- Có constructor khai báo đúng tập dữ liệu client được phép cung cấp.
- Không có setter công khai để request thay đổi các thuộc tính khác sau khi tạo.
- Được thiết kế riêng cho một use case cụ thể, ví dụ `ChangeEmailForm`, `CreateOrderCommand` hoặc `UpdateDisplayNameRequest`.

Spring có thể bind vào Java record hoặc class có constructor phù hợp. Constructor binding cũng hỗ trợ object lồng nhau; các giá trị nested được tạo đệ quy theo property path. Tham số kiểu `List`, `Map` và array có thể được chuyển từ chuỗi đơn hoặc nhận qua key dạng chỉ số/entry như `items[2].name` và `labels[locale]`.

**Constructor binding không tự xác minh quyền nghiệp vụ.** Nếu bạn đưa `role` vào constructor của một DTO dành cho người dùng thông thường, bạn đã mở rộng input contract. Hãy chỉ khai báo những trường endpoint thật sự chấp nhận.

### 3.2. Property binding

Property binding tạo object (thường bằng constructor không tham số), rồi gán giá trị vào các JavaBean property thông qua setter.

~~~java
public class ChangeEmailForm {
    private String currentEmail;
    private String newEmail;

    public String getCurrentEmail() {
        return currentEmail;
    }

    public void setCurrentEmail(String currentEmail) {
        this.currentEmail = currentEmail;
    }

    public String getNewEmail() {
        return newEmail;
    }

    public void setNewEmail(String newEmail) {
        this.newEmail = newEmail;
    }
}
~~~

Property binding linh hoạt cho form truyền thống, nhưng nếu target object có nhiều setter, request có thể thử gán thêm những property không thuộc form. Đây là lý do phải dùng DTO có phạm vi hẹp hoặc allowlist.

### 3.3. Mặc định Spring áp dụng cả hai

Theo mặc định, `DataBinder` áp dụng **constructor binding và property binding**. Điều đó có nghĩa chỉ tạo một immutable constructor object là chưa đủ nếu bạn lại đưa một bean mutable nhiều setter vào cùng đường binding.

Để điều khiển rõ hơn, Spring có `declarativeBinding`:

~~~java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
~~~

Khi bật `declarativeBinding`:

- **Constructor binding luôn được áp dụng.**
- **Property/setter binding chỉ được áp dụng khi có `allowedFields` được cấu hình.**

Đây là cơ chế hữu ích để mặc định chỉ nhận những input được khai báo qua constructor; nếu một form cụ thể cần setter binding, hãy mở nó bằng allowlist riêng.

## 4. Thiết kế DTO bất biến cho constructor binding

Một request DTO tốt nên thể hiện chính xác hợp đồng input của endpoint.

Ví dụ:

~~~java
public record CreateProfileForm(
        String displayName,
        String email) {
}
~~~

DTO này chỉ nhận `displayName` và `email`. Nếu entity Account còn có `id`, `role`, `enabled`, `ownerId`, các thuộc tính đó không xuất hiện trong constructor nên không được client điều khiển qua DTO.

Sau khi bind, service có thể tạo domain command hoặc gọi nghiệp vụ:

~~~java
@PostMapping("/profiles")
Mono<ProfileResponse> create(
        @Valid @ModelAttribute CreateProfileForm form) {

    CreateProfileCommand command =
            new CreateProfileCommand(
                    form.displayName(),
                    form.email());

    return profileService.create(command);
}
~~~

Đây là **đoạn minh họa**, giả định có `ProfileResponse`, `CreateProfileCommand` và `profileService`. Không map request trực tiếp vào entity persistence nếu entity chứa các thuộc tính nội bộ hoặc quyền hạn.

### 4.1. Tên tham số constructor và `-parameters`

Mặc định, Spring tìm giá trị theo tên tham số constructor. Để giữ parameter name trong bytecode, compiler cần lưu metadata tên tham số (ví dụ cờ `-parameters`).

Với Maven Compiler Plugin, có thể cấu hình:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <maven.compiler.parameters>true</maven.compiler.parameters>
</properties>
~~~

Với tên request khác tên Java, dùng `@BindParam`:

~~~java
public record CreateProfileForm(
        @BindParam("display-name") String displayName,
        @BindParam("email-address") String email) {
}
~~~

Client gửi:

~~~text
display-name=Alice
email-address=alice@example.com
~~~

Spring ánh xạ `display-name` vào constructor argument `displayName` và `email-address` vào `email`. `@BindParam` có thể đặt trên constructor parameter hoặc field tương ứng; đây là annotation trong `org.springframework.web.bind.annotation`.

Nếu cần quy tắc tên riêng trên toàn hệ thống, `DataBinder` còn hỗ trợ `NameResolver` để xác định tên lookup của constructor argument. Với phần lớn ứng dụng, `@BindParam` tường minh và dễ kiểm tra hơn.

### 4.2. Constructor lồng nhau và collection

Constructor binding có thể tạo nested object:

~~~java
public record AddressForm(
        String city,
        String postalCode) {
}

public record CreateCustomerForm(
        String name,
        AddressForm address) {
}
~~~

Request có thể dùng property path tương ứng như `name`, `address.city` và `address.postalCode`.

Collection cũng có thể nhận giá trị theo cấu trúc:

~~~text
tags=java,reactive,spring
addresses[0].city=Hanoi
addresses[1].city=DaNang
labels[locale]=vi-VN
~~~

Cần nhớ rằng nested DTO cũng là một phần của input contract. Không đưa object domain rộng hoặc collection không giới hạn vào constructor chỉ vì Spring có thể bind được. Giới hạn kích thước, số phần tử và cấu trúc nested theo nhu cầu endpoint.

## 5. `declarativeBinding` và cách kết hợp constructor với allowlist

Một cấu hình thường dùng:

~~~java
@Controller
class ProfileController {

    @InitBinder
    void enableDeclarativeBinding(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
~~~

Khi đó:

| Target object | `allowedFields` | Hành vi |
| --- | --- | --- |
| Immutable record có constructor | Không cần | Constructor binding tạo object |
| DTO có constructor rõ ràng | Không cần cho constructor inputs | Chỉ tham số constructor được dùng để tạo object |
| Bean mutable có no-arg constructor và setter | Không có | Property binding bị tắt khi declarative binding bật |
| Bean mutable có no-arg constructor và setter | Có allowlist | Property binding chỉ nhận property được phép |

**Điểm quan trọng:** `allowedFields` giới hạn **property binding**, không phải danh sách loại bỏ các tham số constructor. Nếu constructor của bạn nhận `role`, thì `role` vẫn là input constructor hợp lệ dù allowlist property không có `role`. Vì vậy, constructor DTO vẫn phải được thiết kế đúng phạm vi.

Một cấu hình declarative toàn cục có thể đặt trong `@ControllerAdvice` để áp dụng cho nhiều controller. Tuy nhiên, cần kiểm tra phạm vi advice và những model attribute đang dùng setter binding; cách an toàn là chỉ bật allowlist cho đúng form cần property binding.

## 6. Giới hạn property binding bằng `setAllowedFields`

Nếu phải dùng bean mutable, khai báo **allowlist tích cực**:

~~~java
@Controller
class ChangeEmailController {

    @InitBinder("changeEmailForm")
    void initBinder(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
        binder.setAllowedFields(
                "currentEmail",
                "newEmail");
    }
}
~~~

Trong ví dụ này:

- `changeEmailForm.currentEmail` được phép bind.
- `changeEmailForm.newEmail` được phép bind.
- Các property khác không nằm trong allowlist không được property binding.
- Tên field được so khớp **phân biệt chữ hoa/chữ thường**.

Tên trong `@InitBinder("changeEmailForm")` phải tương ứng với model attribute name:

~~~java
@PostMapping("/change-email")
Mono<String> change(
        @ModelAttribute("changeEmailForm")
        ChangeEmailForm form) {
    // ...
}
~~~

Nếu bỏ tên model attribute, binder có thể áp dụng cho các model attribute trong phạm vi controller. Cấu hình có tên giúp tránh vô tình áp dụng allowlist của một form cho một form khác.

### 6.1. Phạm vi của `@InitBinder`

- Đặt `@InitBinder` trong `@Controller` để áp dụng tại controller đó.
- Dùng `@InitBinder("attributeName")` để giới hạn theo tên model attribute.
- Đặt trong `@ControllerAdvice` để chia sẻ cấu hình cho nhiều controller phù hợp.
- Mỗi request dùng một `WebDataBinder` riêng; cấu hình binder không phải một object mutable dùng chung giữa mọi request.

Khi cấu hình global, hãy xem xét mọi form trong phạm vi advice. Một allowlist phù hợp cho `ProfileEditForm` có thể làm hỏng binding của `SearchForm` nếu áp dụng nhầm.

### 6.2. Property path và wildcard

`allowedFields` hỗ trợ property path, không chỉ tên field cấp cao nhất.

| Pattern | Ý nghĩa |
| --- | --- |
| `displayName` | Property cấp cao nhất `displayName` |
| `address.city` | Property `city` trong object `address` |
| `addresses[0].city` | Property `city` của phần tử index 0 |
| `labels[locale]` | Entry có key `locale` trong map `labels` |
| `labels*` | Các entry/index thuộc property `labels` theo wildcard |
| `*Address` | Tên property kết thúc bằng `Address` |

Wildcard `*` là wildcard theo quy tắc pattern của Spring, **không phải regex tùy ý**. Property path nested, indexed và map dùng cùng cú pháp như thao tác đọc/ghi JavaBean property.

Với dữ liệu nhạy cảm, ưu tiên tên property cụ thể:

~~~java
binder.setAllowedFields(
        "displayName",
        "address.city",
        "address.postalCode");
~~~

Hạn chế allowlist rộng như `*`, `account*` hoặc `*Id` nếu endpoint không thực sự cần mọi property phù hợp. Một wildcard có thể vô tình mở rộng quyền binding khi DTO được thêm field trong tương lai.

### 6.3. Vì sao allowlist tốt hơn denylist?

Có thể cấu hình `setDisallowedFields` để liệt kê những field bị cấm, nhưng denylist dễ bị bỏ sót: khi domain object có thêm field mới, field mới có thể tự trở thành input nếu không được thêm vào danh sách cấm.

**Allowlist mô tả chính xác những gì endpoint cho phép.** Tài liệu Spring Framework hiện tại ghi nhận `disallowedFields` đã deprecated trong Spring Framework 7.1 vì dễ lệch với các property thực tế theo thời gian. Nên ưu tiên `setAllowedFields` và DTO có phạm vi nhỏ.

## 7. Kiểm tra các field đã bị chặn

Khi property binding gặp field không nằm trong allowlist, binder loại field đó khỏi danh sách property values và ghi nhận nó trong `BindingResult` dưới dạng suppressed field.

Ví dụ:

~~~java
@PostMapping("/edit")
Mono<ResponseEntity<?>> edit(
        @Valid @ModelAttribute("profileEditForm")
        ProfileEditForm form,
        BindingResult result) {

    String[] suppressed = result.getSuppressedFields();

    if (suppressed.length > 0) {
        // Có request cố bind field không được phép.
    }

    // ...
}
~~~

`BindingResult.getSuppressedFields()` hữu ích để:

- Phát hiện client gửi field ngoài allowlist.
- Ghi log bảo mật ở mức phù hợp.
- Từ chối request nếu hợp đồng yêu cầu không được có field thừa.
- Viết test xác nhận `role` hoặc `enabled` đã bị chặn.

**Phân biệt constructor binding và property binding:** các tham số không dùng đến trong constructor binding được bỏ qua vì chúng không phải constructor argument. Không nên giả định mọi extra parameter bị constructor binding bỏ qua sẽ xuất hiện trong `getSuppressedFields()`. Danh sách suppressed fields phản ánh các field bị chặn trong quá trình property binding.

Nếu API cần từ chối mọi key lạ ngay cả khi chỉ dùng constructor binding, cần một bước kiểm tra input keys riêng theo contract hoặc một cơ chế request validation phù hợp. Constructor binding bảo vệ object khỏi việc gán các property ngoài constructor, nhưng tự nó không phải một hệ thống phát hiện mọi tham số thừa.

## 8. Binding, conversion và validation là ba bước khác nhau

Một request có thể thất bại ở nhiều giai đoạn:

1. **Binding**: Spring xác định input nào đi vào model object.
2. **Type conversion**: chuyển chuỗi thành kiểu Java, ví dụ `"42"` thành `Long`.
3. **Validation**: kiểm tra ràng buộc dữ liệu, ví dụ `@NotBlank`, `@Email`, `@Size` hoặc custom validator.

Ví dụ:

~~~java
public record CreateProfileForm(
        @NotBlank
        @Size(max = 80)
        String displayName,

        @NotBlank
        @Email
        String email) {
}
~~~

Controller:

~~~java
@PostMapping("/profiles")
Mono<String> create(
        @Valid @ModelAttribute CreateProfileForm form) {
    return Mono.just("accepted:" + form.displayName());
}
~~~

`@Valid` kích hoạt validation sau khi binding. Nó **không thay thế allowlist** và không xác nhận user có quyền sửa property.

Trong WebFlux, nếu binding/validation lỗi và không có `BindingResult` kề ngay sau argument `@ModelAttribute`, mặc định `WebExchangeBindException` được phát sinh. Có thể khai báo `BindingResult` ngay sau model attribute để xử lý lỗi trong controller:

~~~java
@PostMapping("/profiles")
Mono<String> create(
        @Valid @ModelAttribute CreateProfileForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return Mono.error(
                new IllegalArgumentException("Invalid form"));
    }

    return Mono.just("accepted");
}
~~~

Đây là ví dụ minh họa; ứng dụng thực tế nên chuyển lỗi sang response 400 phù hợp bằng error handler/advice hoặc trả một response lỗi có cấu trúc. Không nên ném một exception tổng quát chỉ để minh họa trong production.

Nếu dùng reactive wrapper như `@ModelAttribute Mono<Account>`, WebFlux cũng hỗ trợ kiểu reactive đó; lỗi binding có thể được xử lý trong pipeline theo cách phù hợp.

## 9. Constructor binding không thay thế authorization

Ngay cả khi DTO chỉ nhận đúng hai trường, service vẫn phải xác minh quyền đối với tài nguyên.

Ví dụ:

~~~java
Mono<Profile> update(
        Long profileId,
        ChangeEmailForm form,
        AuthenticatedUser currentUser) {

    return profileRepository.findById(profileId)
        .switchIfEmpty(Mono.error(new ProfileNotFoundException()))
        .flatMap(profile ->
            authorizationService
                .checkCanChangeEmail(currentUser, profile)
                .then(profileService.changeEmail(
                        profile, form.newEmail())));
}
~~~

Đây là **mã minh họa**; các service và exception cần được định nghĩa. Việc constructor không nhận `role` không chứng minh người dùng có quyền đổi email của profile được chỉ định.

Các nguyên tắc:

- Không nhận `ownerId`, `tenantId`, `role`, `enabled` hoặc `emailVerified` từ form thông thường nếu user không được phép tự quyết định.
- Lấy user hiện tại từ security context đã xác thực, không tin ID quyền hạn client gửi.
- Kiểm tra quyền đối với resource cụ thể trong service/use case.
- Dùng DTO riêng cho từng thao tác: `CreateAccountForm`, `ChangeEmailForm`, `AdminChangeRoleCommand`.
- Chỉ endpoint quản trị được bảo vệ mới nhận các trường quản trị; vẫn cần authorization kiểm tra role hiện tại.

**Allowlist là một lớp phòng vệ của binding, không phải toàn bộ mô hình phân quyền.**

## 10. `@ModelAttribute` không phải cơ chế giới hạn field của JSON `@RequestBody`

Một lỗi cấu hình phổ biến là thêm:

~~~java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email");
}
~~~

rồi nghĩ mọi JSON body của controller đều bị giới hạn còn hai field. Điều đó không đúng: `@RequestBody` trong WebFlux được giải mã bởi `HttpMessageReader`/codec, không đi qua cùng quy trình `@ModelAttribute` data binding.

Với JSON, nên dùng DTO rõ ràng:

~~~java
public record UpdateProfileJson(
        @NotBlank String displayName,
        @Email String email) {
}

@PostMapping(path = "/profiles/json",
             consumes = MediaType.APPLICATION_JSON_VALUE)
Mono<ProfileResponse> updateJson(
        @Valid @RequestBody UpdateProfileJson request) {
    // Map request sang command nghiệp vụ.
}
~~~

Đây là ví dụ minh họa; cần định nghĩa `ProfileResponse` và phần mapping service. Các field của record tạo ra cấu trúc JSON input mà endpoint hỗ trợ. Không đưa entity có quyền quản trị vào tham số `@RequestBody` chỉ vì Jackson có thể deserialize nó.

Nếu cần từ chối JSON có field không biết, cấu hình chính sách unknown-property của JSON codec/ObjectMapper phù hợp với ứng dụng và test nó; `allowedFields` của `WebDataBinder` không tự thực hiện việc đó.

## 11. Chương trình Spring Boot WebFlux Java 17+ có thể chạy

Ví dụ này minh họa hai endpoint:

1. `POST /api/profiles/create` dùng **record constructor binding**. Request chỉ tạo `CreateProfileForm` từ hai constructor argument.
2. `POST /api/profiles/{id}/edit` dùng **mutable form + allowlist**. Chỉ `displayName` và `email` được property binding; `role` và `enabled` bị suppressed.

Yêu cầu: **JDK 17+**, **Maven 3.6.3+**, **Spring Boot 4.1.2**. Boot BOM quản lý các phiên bản Spring Framework và thư viện đi kèm.

Cấu trúc dự án:

~~~text
webflux-binding-demo/
  pom.xml
  src/main/java/example/binding/BindingDemoApplication.java
  src/main/java/example/binding/ProfileController.java
~~~

### 11.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webflux-binding-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.parameters>true</maven.compiler.parameters>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 11.2. Ứng dụng khởi động

**src/main/java/example/binding/BindingDemoApplication.java**

~~~java
package example.binding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BindingDemoApplication.class, args);
    }
}
~~~

### 11.3. Controller, record và mutable form

**src/main/java/example/binding/ProfileController.java**

~~~java
package example.binding;

import java.util.Arrays;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.BindParam;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/profiles")
public class ProfileController {

    // Bật declarative binding cho các model attribute trong controller.
    @InitBinder
    void enableDeclarativeBinding(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }

    // Chỉ cho property binding hai field của form chỉnh sửa.
    @InitBinder("profileEditForm")
    void configureProfileEdit(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "email");
    }

    public record CreateProfileForm(
            @BindParam("display-name")
            @NotBlank
            @Size(max = 80)
            String displayName,

            @BindParam("email-address")
            @NotBlank
            @Email
            String emailAddress) {
    }

    public record CreateResponse(
            String displayName,
            String emailAddress) {
    }

    public record EditResponse(
            long id,
            String displayName,
            String email,
            String role,
            boolean enabled) {
    }

    public record ErrorResponse(
            String error,
            List<String> details,
            List<String> suppressedFields) {
    }

    public static class ProfileEditForm {
        @NotBlank
        @Size(max = 80)
        private String displayName;

        @NotBlank
        @Email
        private String email;

        // Các trường nội bộ không thuộc allowlist.
        private String role = "USER";
        private boolean enabled;

        public ProfileEditForm() {
        }

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

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }
    }

    @PostMapping(
            path = "/create",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<ResponseEntity<Object>> create(
            @Valid
            @ModelAttribute("createProfileForm")
            CreateProfileForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            return Mono.just(ResponseEntity.badRequest().body(
                    (Object) new ErrorResponse(
                            "invalid input",
                            describeErrors(result),
                            List.of())));
        }

        return Mono.just(ResponseEntity.ok(
                (Object) new CreateResponse(
                        form.displayName(),
                        form.emailAddress())));
    }

    @PostMapping(
            path = "/{id}/edit",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<ResponseEntity<Object>> edit(
            @PathVariable long id,
            @Valid
            @ModelAttribute("profileEditForm")
            ProfileEditForm form,
            BindingResult result) {

        String[] suppressed = result.getSuppressedFields();
        Arrays.sort(suppressed);

        if (result.hasErrors() || suppressed.length > 0) {
            return Mono.just(ResponseEntity.badRequest().body(
                    (Object) new ErrorResponse(
                            "invalid or unsupported input",
                            describeErrors(result),
                            List.of(suppressed))));
        }

        return Mono.just(ResponseEntity.ok(
                (Object) new EditResponse(
                        id,
                        form.getDisplayName(),
                        form.getEmail(),
                        form.getRole(),
                        form.isEnabled())));
    }

    private List<String> describeErrors(BindingResult result) {
        return result.getFieldErrors().stream()
                .map(error ->
                        error.getField() + ":" + error.getCode())
                .toList();
    }
}
~~~

**Điều gì xảy ra trong controller?**

- `CreateProfileForm` là record nên dữ liệu được tạo qua constructor. `@BindParam` ánh xạ tên form có dấu gạch nối sang tên tham số Java.
- `declarativeBinding=true` giữ constructor binding và không tự bật property binding khi không có allowlist.
- `ProfileEditForm` có constructor không tham số và setter, nên đây là form mutable cần property binding.
- `@InitBinder("profileEditForm")` cho phép đúng hai property `displayName` và `email`.
- Nếu client gửi thêm `role` hoặc `enabled`, binder ghi nhận các field đó trong `BindingResult.getSuppressedFields()`; endpoint trả 400.
- Validation vẫn chạy trên các field được bind. Allowlist không thay thế `@NotBlank` hoặc `@Email`.

### 11.4. Chạy chương trình

Tại thư mục chứa `pom.xml`:

~~~bash
mvn clean package
mvn spring-boot:run
~~~

Mặc định server lắng nghe tại port 8080.

**Thử constructor binding:**

~~~bash
curl -i -X POST http://localhost:8080/api/profiles/create \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "display-name=Alice" \
  --data-urlencode "email-address=alice@example.com" \
  --data-urlencode "role=ADMIN"
~~~

Response body dự kiến:

~~~json
{
  "displayName": "Alice",
  "emailAddress": "alice@example.com"
}
~~~

`role=ADMIN` không phải constructor argument của `CreateProfileForm` nên không trở thành thuộc tính của form. Record chỉ chứa hai giá trị đã khai báo.

**Thử property binding với field ngoài allowlist:**

~~~bash
curl -i -X POST http://localhost:8080/api/profiles/42/edit \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "displayName=Alice" \
  --data-urlencode "email=alice@example.com" \
  --data-urlencode "role=ADMIN" \
  --data-urlencode "enabled=true"
~~~

Response body dự kiến:

~~~json
{
  "error": "invalid or unsupported input",
  "details": [],
  "suppressedFields": [
    "enabled",
    "role"
  ]
}
~~~

`displayName` và `email` được bind. `role` và `enabled` không được gán vào bean; chúng xuất hiện trong danh sách suppressed và endpoint từ chối request.

**Thử dữ liệu không hợp lệ:**

~~~bash
curl -i -X POST http://localhost:8080/api/profiles/create \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "display-name=" \
  --data-urlencode "email-address=not-an-email"
~~~

Request không vượt qua validation `@NotBlank` và `@Email`. Controller trả HTTP 400 cùng các mã lỗi field được Spring cung cấp. Thứ tự field error có thể phụ thuộc quá trình binding/validation; không nên dựa vào thứ tự đó làm hợp đồng API.

Đây là demo tập trung vào binding và allowlist, chưa lưu dữ liệu vào database. Trong ứng dụng thực tế, sau khi binding/validation thành công, service vẫn cần kiểm tra quyền, thực hiện nghiệp vụ và chỉ cập nhật đúng cột/thuộc tính được phép.

## 12. BindingResult, suppressed fields và lỗi mặc định trong WebFlux

Có hai nhóm kết quả cần quan sát:

| Tình huống | Kết quả |
| --- | --- |
| Không chuyển được `"abc"` thành `Long` | Binding/type conversion error |
| `@NotBlank` hoặc `@Email` không đạt | Validation error |
| Request cố set property không có trong allowlist | Suppressed field |
| Constructor thiếu giá trị bắt buộc hoặc nested conversion lỗi | Constructor binding error trong BindingResult |
| Không có `BindingResult` kề sau `@ModelAttribute` | Mặc định có thể phát `WebExchangeBindException` |

`BindingResult` phải được khai báo **ngay sau** argument `@ModelAttribute` mà nó đại diện:

~~~java
@PostMapping("/edit")
Mono<String> update(
        @Valid @ModelAttribute("form") ProfileEditForm form,
        BindingResult result) {
    // Xử lý lỗi và suppressed fields tại đây.
}
~~~

Nếu có nhiều model attribute, mỗi `BindingResult` cần đứng ngay sau argument tương ứng. Đừng đặt một tham số khác ở giữa.

Trong ứng dụng cần kiểm soát bảo mật, hãy quyết định rõ chính sách đối với suppressed fields:

- **Bỏ qua có kiểm soát**: phù hợp với một số form tương thích ngược, nhưng phải log/quan trắc nếu cần.
- **Từ chối request**: phù hợp khi client gửi field ngoài contract hoặc có dấu hiệu cố thay đổi thuộc tính nhạy cảm.
- **Ghi nhận sự kiện bảo mật**: cân nhắc rate, privacy và tránh log toàn bộ payload chứa dữ liệu cá nhân.

Không phản hồi stack trace hoặc chi tiết nội bộ của binder cho client.

## 13. Cập nhật một phần (PATCH) cần semantics rõ ràng

Constructor binding phù hợp khi tập input có cấu trúc rõ, nhưng PATCH có một bài toán riêng: **field không được gửi** khác với **field được gửi nhưng có giá trị null**.

Ví dụ:

~~~json
{
  "displayName": null
}
~~~

Client có thể đang muốn xóa tên, hoặc vô tình gửi null; trong khi nếu không có key `displayName` thì có thể nghĩa là “giữ nguyên”. Một DTO đơn giản với nullable field có thể không diễn tả đầy đủ hai trạng thái đó.

Các cách thiết kế:

- Dùng command riêng cho từng thao tác rõ ràng, ví dụ `ChangeDisplayName` hoặc `ChangeEmail`.
- Dùng kiểu biểu diễn ba trạng thái: absent, present-null, present-value nếu contract cho phép null.
- Dùng JSON Merge Patch/JSON Patch khi cần semantics patch chuẩn và có hỗ trợ đúng.
- Chỉ áp dụng các field thực sự được gửi và đã được authorization cho phép.
- Tránh bind PATCH trực tiếp vào entity persistence đang có state cũ.

Với PUT, xác định rõ đây là thay thế toàn bộ representation hay chỉ một phần theo contract. Không để việc Spring bỏ qua field không có mặt quyết định thay cho semantics API.

## 14. Những lỗi thường gặp

| Sai lầm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Bind thẳng JPA/Hibernate entity vào `@ModelAttribute` | Client có thể thử cập nhật field nội bộ hoặc nested property | Tạo request DTO dành riêng cho use case |
| Nghĩ record tự bảo vệ dù controller vẫn dùng mutable bean khác | Setter binding vẫn có thể mở rộng input | Dùng DTO immutable và/hoặc `declarativeBinding` |
| Chỉ đặt `allowedFields` nhưng không hiểu constructor binding | Constructor arguments vẫn là input hợp lệ | Thiết kế constructor đúng contract; dùng declarative binding |
| Dùng `disallowedFields` để cấm vài field | Dễ quên field mới khi model thay đổi; đã deprecated trong Spring 7.1 | Ưu tiên positive allowlist |
| Allowlist wildcard quá rộng | Có thể vô tình mở property mới | Khai báo path cụ thể và review khi DTO thay đổi |
| Nghĩ `allowedFields` giới hạn JSON `@RequestBody` | JSON đi qua HTTP message codec | Dùng JSON DTO, cấu hình deserialization và mapping riêng |
| Nghĩ `@Valid` chặn mass assignment | Validation chỉ kiểm tra quy tắc dữ liệu | Kiểm soát binding và authorization riêng |
| Nghĩ field suppressed tự động gây 400 | Suppressed field được ghi nhận; ứng dụng quyết định chính sách | Kiểm tra `getSuppressedFields()` nếu cần từ chối |
| Nghĩ constructor binding phát hiện mọi key lạ | Constructor chỉ lấy tham số cần thiết; extra key có thể bị bỏ qua | Kiểm tra request keys riêng nếu contract yêu cầu strict |
| Đặt `BindingResult` xa `@ModelAttribute` | Spring không liên kết đúng binding result với argument | Đặt ngay sau argument cần xử lý |
| Dùng cùng DTO cho profile user và admin | Mở rộng input contract ngoài nhu cầu endpoint | Tách form/command theo use case và authorization |
| Cho client gửi `ownerId` hoặc `role` rồi tin giá trị | IDOR/BOLA và privilege escalation | Lấy identity đáng tin cậy, authorize trong service |
| Coi PATCH nullable field là đủ | Không phân biệt absent và explicit null | Thiết kế semantics patch ba trạng thái hoặc command riêng |

## 15. Kiểm thử constructor binding và allowlist

Một test có giá trị nên kiểm tra **giá trị được chấp nhận và giá trị bị chặn**, không chỉ kiểm tra endpoint trả 200.

### 15.1. Test constructor binding

Gửi form gồm các trường hợp lệ và một trường thừa `role`. Xác nhận:

- `displayName` và `emailAddress` có trong response.
- Không có field `role` trong DTO/response.
- Constructor không tạo ra thuộc tính quản trị từ input không khai báo.

### 15.2. Test allowlist property binding

Gửi form có `displayName`, `email`, `role` và `enabled`. Xác nhận:

- Hai field được cho phép được bind.
- `role` và `enabled` nằm trong `getSuppressedFields()`.
- Giá trị nội bộ mặc định của bean không bị thay đổi.
- Nếu policy yêu cầu, endpoint trả 400 khi có suppressed field.

### 15.3. Test nested property path

Nếu allowlist có `address.city` hoặc `items[0].name`, cần test cả path được phép lẫn sibling/entry không được phép. Một allowlist cấp cao nhất như `address` có thể mở nhiều property lồng nhau hơn mong muốn.

### 15.4. Test validation và authorization riêng

- Empty string, email sai và độ dài vượt giới hạn phải tạo validation error.
- User không có quyền cập nhật resource phải bị từ chối dù dữ liệu bind và validation đều thành công.
- Thay `ownerId`, `role` hoặc tenant ID không được giúp truy cập dữ liệu ngoài quyền.
- Test cả request form/query và JSON body vì chúng đi qua các cơ chế khác nhau.

Có thể dùng **WebTestClient** để gửi HTTP request thực tới ứng dụng WebFlux; test xác nhận binding, validation, response status và body ở cùng một đường xử lý mà client sử dụng.

## 16. Checklist trước khi đưa binding lên production

- [ ] Mỗi endpoint có request DTO riêng, chỉ gồm các trường client được phép gửi.
- [ ] Ưu tiên record/immutable DTO và constructor binding.
- [ ] Cân nhắc bật `binder.setDeclarativeBinding(true)` tại phạm vi phù hợp.
- [ ] Nếu dùng setter binding, khai báo `setAllowedFields` cụ thể.
- [ ] Review nested property path, collection index, map key và wildcard.
- [ ] Không bind trực tiếp domain/persistence entity có nhiều thuộc tính nội bộ.
- [ ] Phân biệt `@ModelAttribute` với `@RequestBody` JSON.
- [ ] Kiểm tra `BindingResult` và suppressed fields theo chính sách API.
- [ ] Dùng `@Valid`/`@Validated` cho validation, nhưng không nhầm với authorization.
- [ ] Lấy user/tenant từ identity đã xác thực và kiểm tra quyền trên từng resource.
- [ ] Thiết kế rõ semantics PUT/PATCH, đặc biệt absent so với null.
- [ ] Test field hợp lệ, field ngoài allowlist, nested path, validation và quyền truy cập.
- [ ] Không ghi log toàn bộ payload nhạy cảm hoặc trả lỗi binder nội bộ cho client.

## 17. Tự kiểm tra

**Câu 1.** Constructor binding khác property binding ở đâu?

Constructor binding tạo object từ các argument của constructor; property binding tạo/nhận object rồi gán giá trị vào JavaBean setter/property.

**Câu 2.** Vì sao Java record thường phù hợp cho request DTO?

Record có constructor rõ ràng và trạng thái bất biến; tập constructor component thể hiện trực tiếp các input mà endpoint chấp nhận.

**Câu 3.** Spring mặc định bật constructor binding hay property binding?

Theo mặc định, cả hai được áp dụng. Có thể dùng `setDeclarativeBinding(true)` để luôn dùng constructor binding và chỉ bật property binding khi khai báo `allowedFields`.

**Câu 4.** `setAllowedFields("displayName", "email")` có giới hạn tham số constructor không?

Không. Nó là allowlist cho property binding. Constructor arguments vẫn phải được kiểm soát bằng chính thiết kế constructor/DTO.

**Câu 5.** Khi bật declarative binding và không cấu hình allowedFields, setter binding có chạy không?

Không. Constructor binding vẫn chạy; property binding chỉ được áp dụng có điều kiện khi có allowlist.

**Câu 6.** `@BindParam("display-name")` dùng để làm gì?

Ánh xạ tên request `display-name` vào constructor parameter có tên Java khác, ví dụ `displayName`.

**Câu 7.** `getSuppressedFields()` có luôn liệt kê mọi query parameter không được constructor sử dụng không?

Không. Nó phản ánh field bị suppress trong property binding. Extra parameter không phải constructor argument có thể bị bỏ qua mà không xuất hiện ở danh sách này.

**Câu 8.** `allowedFields` có giới hạn JSON `@RequestBody` không?

Không. JSON body được giải mã qua HTTP message codec; cần DTO và chính sách deserialization riêng.

**Câu 9.** `@Valid` có ngăn người dùng tự gửi `role=ADMIN` không?

Không. Validation kiểm tra dữ liệu; allowlist/constructor DTO giới hạn input và authorization quyết định user có quyền thực hiện thay đổi hay không.

**Câu 10.** Vì sao positive allowlist tốt hơn denylist?

Vì allowlist mô tả rõ tập field được phép; khi model có thêm property, property mới không tự được mở chỉ vì chưa được thêm vào danh sách cấm.

## 18. Tài liệu tham khảo chính thức

- [Spring Framework — WebFlux Data Binding](https://docs.spring.io/spring-framework/reference/web/webflux/data-binding.html): phạm vi @ModelAttribute, model design, constructor binding, allowlist và declarative binding.
- [Spring Framework — Core Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): constructor binding, property binding, nested property path, type conversion.
- [Spring Framework — @ModelAttribute trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/modelattrib-method-args.html): nguồn dữ liệu request, @BindParam, BindingResult và validation.
- [Spring Framework — DataBinder trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-initbinder.html): @InitBinder, phạm vi cấu hình binder và Converter/Formatter.
- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html): DataBinder, Validator và vai trò validation trong các tầng.
- [Spring Framework — BindParam JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/BindParam.html): annotation cho tên request constructor parameter.
- [Spring Framework — BindingResult JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/BindingResult.html): errors và suppressed fields.
- [Spring Boot System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): Java và build tool requirements cho phiên bản Boot được chọn.

**Ghi nhớ:** Constructor binding giới hạn input theo những tham số constructor đã khai báo; `declarativeBinding` giữ constructor binding và chỉ bật setter binding khi có `allowedFields`. Khi cần property binding, dùng allowlist theo property path cụ thể và kiểm tra suppressed fields. Hãy dùng DTO riêng cho từng use case, phân biệt `@ModelAttribute` với JSON `@RequestBody`, và luôn xử lý validation, authorization cùng semantics cập nhật ở các tầng riêng.