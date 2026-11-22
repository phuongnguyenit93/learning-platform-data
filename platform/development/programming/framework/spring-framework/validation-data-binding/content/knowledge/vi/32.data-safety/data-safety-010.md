# Rà soát thay đổi mô hình để không mở thêm trường binding ngoài ý muốn

## 1. Vấn đề: thêm một setter cũng có thể mở thêm bề mặt tấn công

Trong Spring Framework, một thay đổi rất nhỏ trên Java model có thể làm thay đổi những gì HTTP client được phép tác động. Khi handler nhận `@ModelAttribute` và sử dụng **property binding**, Spring đọc tên tham số request, tìm property tương ứng rồi gọi setter hoặc đi qua nested property path. Theo mặc định, một `WebDataBinder` có thể bind mọi property có thể truy cập phù hợp với input.

Giả sử ban đầu có model:

~~~java
public class Account {
    private String displayName;

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String value) {
        this.displayName = value;
    }
}
~~~

Controller nhận:

~~~java
@PostMapping("/account/edit")
public String edit(@ModelAttribute Account account) {
    // Cập nhật hồ sơ.
    return "ok";
}
~~~

Request `displayName=Lan` có thể gán `displayName`. Một pull request khác thêm:

~~~java
private boolean verified;

public boolean isVerified() { return verified; }
public void setVerified(boolean verified) {
    this.verified = verified;
}
~~~

Người sửa model chỉ định dùng `verified` cho một quy trình quản trị. Nhưng nếu controller vẫn property-bind trực tiếp từ request, dữ liệu `verified=true` nay có một setter mới để khớp. Bề mặt binding đã thay đổi **mà controller không đổi một dòng nào**.

Đây là **mass assignment**, còn gọi *over-posting*: client gửi tên thuộc tính mà product không định cho phép chỉnh sửa; framework tự động gán vì đối tượng có đường ghi tương ứng.

**Mục tiêu của bài** là hình thành một quy trình code review/kiểm thử giúp:
1. Nhận diện mọi thay đổi của model/DTO có thể làm rộng input contract.
2. Khóa việc bind vào đúng fields được phép, ngay cả khi model có setter mới.
3. Phân biệt setter/property binding, constructor binding và JSON deserialization.
4. Kiểm soát nested properties, indexed paths, headers và path variables.
5. Thiết kế regression tests khiến một “setter vô hại” không âm thầm biến thành quyền chỉnh sửa mới.
6. Không nhầm ràng buộc `@Valid` với authorization, và không dựa vào blacklist như lớp bảo vệ chính.

Nội dung tập trung **Spring Framework 6.2, Java 17 và Spring Boot 3.5.7**. Ví dụ runnable dùng Spring MVC, nhưng các nguyên tắc về `DataBinder`, model design và input DTO cũng quan trọng trong WebFlux.

## 2. Hiểu đúng các đường dữ liệu vào object

### 2.1. `@ModelAttribute` với property binding

Khi controller có:

~~~java
@PostMapping("/profiles")
public String update(@ModelAttribute("profileForm") ProfileForm form) {
    return "done";
}
~~~

Spring MVC có thể lấy các request parameters, gồm query/form fields, đồng thời URI template variables và headers theo quy tắc nguồn phù hợp, để khởi tạo/gán vào model attribute. Nếu object có writable properties tương ứng, tên field có thể được bind.

Ví dụ form:

~~~text
displayName=Lan
contactEmail=lan@example.com
verified=true
preferences.notificationsEnabled=false
items[0].price=0
~~~

`verified`, `preferences.notificationsEnabled` và `items[0].price` đều phải nằm trong threat model; client không bị giới hạn bởi những ô input hiện diện trong HTML giao diện. Người dùng có thể tự thêm query/form parameters.

**Mặc định không nên xem setters của entity/domain model là public API.** Setter có thể phục vụ database mapping, tests hoặc business code, nhưng không có nghĩa client được phép gọi gián tiếp qua binder.

### 2.2. Constructor binding

Spring Framework 6.1+ có constructor binding cho `@ModelAttribute`. Spring tìm các constructor parameters cần thiết, resolve chúng từ request values và tạo object. Điều này hữu ích cho immutable DTO:

~~~java
public record ProfileChanges(
        String displayName,
        String contactEmail) {
}
~~~

Constructor làm rõ danh sách nhận input và tránh setter tùy ý. **Nhưng thêm constructor parameter/record component mới cũng là mở input contract.** Nếu thêm `boolean verified` vào record, constructor binding có thể nhận thêm `verified=true`. PR phải rà soát constructor signatures/record components, không chỉ setters.

Có thể điều khiển việc property binding bằng:

~~~java
@InitBinder("profileForm")
void init(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
~~~

Khi `declarativeBinding=true`, constructor binding vẫn dùng các parameters của constructor, còn property binding chỉ được phép nếu có `allowedFields` được cấu hình. Điều này **không phải whitelist cho constructor parameters**. Thiết kế constructor chỉ nhận những thông tin thực sự công khai là bước riêng.

### 2.3. JSON `@RequestBody` không theo allowlist của form binder

~~~java
@PostMapping("/api/profiles")
public void update(@Valid @RequestBody ProfileJsonInput body) {
    // ...
}
~~~

Spring MVC đọc JSON thông qua `HttpMessageConverter`/Jackson. Jackson có quy tắc properties/constructors/deserialization riêng; `WebDataBinder#setAllowedFields` cho property binding của `@ModelAttribute` **không tự lọc các JSON properties**.

Do đó có hai bề mặt phải rà soát độc lập:
- **Form/query/model attribute:** JavaBean/constructor binding, `WebDataBinder` và `@InitBinder`.
- **JSON body:** Jackson DTO, record constructor, setters, fields/creators và Jackson configuration.

Cùng một Java class được dùng cho cả hai đường là dấu hiệu cần xem xét nghiêm túc. Nếu có thể, tạo **input DTO riêng cho từng use case** và chỉ chứa các trường product muốn cho sửa.

### 2.4. Validation và authorization không thay thế nhau

~~~java
@NotNull
private Boolean verified;
~~~

Annotation này chỉ kiểm tra giá trị có tồn tại; nó **không xác định caller có quyền đặt `verified=true` hay không**. `@Min`, `@Pattern`, `@Email`, `@Valid` đều có nhiệm vụ validation, không biến setter thành quyền truy cập an toàn.

Quy trình an toàn:

~~~text
HTTP request
    |
    v
Dedicated input DTO / constructor contract
    |
    v
Allowed property paths (nếu cần setter binding)
    |
    v
Conversion + Bean Validation
    |
    v
Authenticated principal + authorization
    |
    v
Service áp các fields đã được phép lên domain entity
    |
    v
Response DTO riêng, không serialize entity tùy tiện
~~~

## 3. Phân loại thay đổi model trong pull request

### 3.1. Ma trận rủi ro

| Thay đổi trong PR | Rủi ro binding | Cần kiểm tra |
| --- | --- | --- |
| Thêm `setVerified(boolean)` vào entity | Setter mới có thể nhận `verified=true` | Có controller `@ModelAttribute Entity`? Có whitelist không? |
| Thêm `setRole(String)` | Client có thể đề xuất quyền cao hơn | Không bind role; cấp role ở service có kiểm tra quyền |
| Thêm `setOwnerId(...)` | Người dùng có thể đổi ownership | ID thuộc phạm vi từ path/principal và authorization |
| Thêm `setInternalNote(...)` | Dữ liệu nội bộ trở thành writable | DTO public có chứa field này không? |
| Thêm component `verified` vào record constructor | Constructor binding mở input mới | Rà constructor/`@BindParam` và input contract |
| Thêm nested `preferences`/`settings` | Có thể xuất hiện các đường `settings.admin` | Rà wildcard/nested allowedPaths |
| Đổi type `String` thành `List<X>` | Mở indexed paths | Kiểm tra auto-grow, count, conversion và whitelist |
| Mở rộng `setAllowedFields("address*")` | Wildcard cho thêm fields tương lai | Thu hẹp paths cụ thể |
| Đổi `@ModelAttribute` sang `@RequestBody` | Chuyển sang quy tắc của Jackson | Test cả JSON unknown fields và permissions |
| Thêm `@JsonProperty`/`@JsonAlias`/creator | Thêm tên JSON input hoặc alias | Rà cả tên chính và tên alias |
| Thêm `@BindParam` cho constructor | Đổi key HTTP được nhận | Test tên field công khai và quyền sửa |
| Bỏ `setDeclarativeBinding(true)` | Có thể mở lại property binding | Regression test cho extra setters |
| Bỏ `@ModelAttribute(binding=false)` | Model object có thể bắt đầu bị bind | Xác nhận contract thật sự cần |
| Thêm `@ControllerAdvice @InitBinder` global | Thay đổi binder policy nhiều controller | Test phạm vi advice và thứ tự cấu hình |
| Thêm custom converter hoặc formatter | Chuỗi trước đây không hợp lệ nay có thể bind | Rà giá trị hợp lệ, field scope và validation |

**Điều kiện kích hoạt review:** không đợi đến khi file controller thay đổi. Bất cứ thay đổi nào ở model, DTO, constructor, setter, nested type, converter, serializer hoặc binder config đều có thể thay đổi hợp đồng input.

### 3.2. Review một diff cụ thể

Trước thay đổi:

~~~java
public class ProfileForm {
    private String displayName;
    private String contactEmail;
    // Getter/setter cho hai property.
}
~~~

Sau thay đổi:

~~~java
public class ProfileForm {
    private String displayName;
    private String contactEmail;
    private boolean verified;
    private String timezone;
    // Getter/setter cho cả bốn property.
}
~~~

Hai fields mới không nhất thiết đều nguy hiểm như nhau:
- `verified` là **protected state**: tuyệt đối không cho người dùng thay đổi chỉ bằng sửa hồ sơ.
- `timezone` có thể là **public profile preference**, nhưng chưa chắc endpoint chỉnh sửa hiện tại đã được quyền nhận. Chỉ cho phép sau khi API contract/product yêu cầu.

Review phải trả lời **"Ai, qua endpoint nào, được sửa field nào?"**, không chỉ `"Field này có @NotNull không?"`. Trạng thái mới mặc định nên **không bind** cho đến khi có quyết định rõ và test tương ứng.

## 4. Lớp bảo vệ đầu tiên: dedicated input DTO

Không expose trực tiếp entity:

~~~java
// Anti-pattern: entity có cả fields phục vụ nội bộ.
@PostMapping("/account/edit")
public void edit(@ModelAttribute AccountEntity entity) {
    accountRepository.save(entity);
}
~~~

Ngay cả khi code này ngắn, mỗi setter mới trên `AccountEntity` có thể thay đổi input contract. Entity còn có thể chứa nested relations, role, owner, billing status và state phục vụ persistence.

Thay bằng request DTO cố định:

~~~java
public record UpdateProfileRequest(
        String displayName,
        String contactEmail) {
}
~~~

Trong service, tìm entity đã tồn tại **theo authenticated principal hoặc một ID đã kiểm tra quyền**, rồi áp dụng đúng những fields thuộc operation:

~~~java
// Minh họa method, không phải file Java độc lập.
public void updateProfile(Account account, UpdateProfileRequest input) {
    account.changeDisplayName(input.displayName());
    account.changeContactEmail(input.contactEmail());
    // Không động đến role, ownerId, verified, billingState.
}
~~~

Không dùng thư viện mapping với cấu hình “copy mọi property cùng tên” từ DTO sang entity nếu sau này DTO có field mới sẽ tự map. Một mapper whitelist, method mapping thủ công hoặc mapper được kiểm tra bằng contract tests an toàn hơn.

### 4.1. Separate DTO không tự đảm bảo mãi mãi

Khi một developer thêm field vào input DTO, surface lại có thể mở. Vì vậy:
- Review tất cả additions vào constructor components, setters, Jackson creators và aliases.
- Duy trì danh sách fields public được approved theo operation.
- Khi mở field mới, cập nhật authorization và tests một cách **có chủ đích**.
- Với Jackson, kiểm soát unknown-field policy (`FAIL_ON_UNKNOWN_PROPERTIES` hoặc tương đương) nếu cần fail-fast.
- Không dùng `@JsonIgnore` rải rác trên entity để thay dedicated DTO; một annotation bị bỏ có thể làm field lộ.

### 4.2. Đừng dùng output DTO làm input DTO

API response có thể hiển thị `verified`, `accountId` hoặc `role`. Điều đó **không có nghĩa** client được gửi lại chúng trong update request. Tách:

~~~text
ProfileResponse:
  accountId, displayName, contactEmail, verified, role

UpdateProfileInput:
  displayName, contactEmail
~~~

Việc dùng một class cho cả đọc và ghi thường tạo áp lực thêm property phục vụ UI, rồi không ai nhận ra setter đó đã trở thành input.

## 5. Lớp bảo vệ thứ hai: `setAllowedFields` cho property binding

Khi cần mutable JavaBean form, dùng một allowlist cụ thể:

~~~java
@InitBinder("profileForm")
void initProfileBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAllowedFields("displayName", "contactEmail");
}
~~~

### 5.1. Hai cơ chế phối hợp

- `setDeclarativeBinding(true)`: ưu tiên hợp đồng constructor, không tự mở setter binding nếu không có `allowedFields`.
- `setAllowedFields(...)`: chỉ những property paths thuộc allowlist được gán bằng property binding.

Theo Spring Framework 6.2, mặc định allowed fields là **mọi fields**, và matching allowlist **phân biệt hoa/thường**. Các patterns chấp nhận `*`, ví dụ `name*` hoặc `*Address`, nhưng wildcard rộng khiến một setter mới vô tình khớp.

Với model ở mục 3, whitelist:

~~~text
displayName
contactEmail
~~~

không cho:
- `verified`.
- `timezone`.
- `role`.
- `ownerId`.
- `settings.admin`.
- Các nested indexed paths chưa được duyệt.

Nếu cần mở `timezone` sau khi product duyệt, thay đổi phải tường minh:

~~~java
binder.setAllowedFields(
        "displayName", "contactEmail", "timezone");
~~~

Và bổ sung tests positive/negative/authorization tương ứng.

### 5.2. `getSuppressedFields()` là tín hiệu đáng quan tâm

Spring có:

~~~java
String[] suppressed =
        binder.getBindingResult().getSuppressedFields();
~~~

Các fields bị chặn bởi whitelist được liệt kê tại đây. **`getSuppressedFields()` không nhất thiết tạo `FieldError` hoặc làm `hasErrors()` thành true.** Vì thế nếu muốn reject request cố gửi protected input, cần kiểm tra riêng.

Ví dụ handler:

~~~java
@PostMapping("/form")
public ResponseEntity<?> update(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        BindingResult errors) {

    if (errors.getSuppressedFields().length > 0) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "UNEXPECTED_FIELDS"));
    }
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_INPUT"));
    }
    // Gọi service ...
}
~~~

Đoạn trên là minh họa một phần controller; bản đầy đủ ở mục 9. **Không trả nguyên suppressed field names** nếu chúng có thể chứa Map keys/email/token do client kiểm soát; dùng mã lỗi chung hoặc canonicalize paths an toàn.

### 5.3. `setIgnoreUnknownFields(false)` không đủ

`DataBinder#setIgnoreUnknownFields(false)` có thể khiến binding unknown property báo lỗi, nhưng điều đó **không chặn drift khi thêm setter mới**: field `verified` từng là unknown, nay có setter thì không còn unknown nữa.

Vì vậy "reject unknown" không thay "only approved fields". Cũng đừng mặc định `@Valid` sẽ phát hiện việc client cố đổi trường nhạy cảm: nếu setter nhận Boolean hợp lệ thì validation có thể hoàn toàn pass.

### 5.4. Không dùng denylist làm phòng tuyến chính

~~~java
binder.setDisallowedFields(
        "role", "verified", "ownerId");
~~~

Danh sách này **chỉ liệt kê những gì ta nhớ phải chặn**. Khi model thêm `isStaff`, `billingEnabled` hay `transferOwner`, blacklist cũ không tự cập nhật. Spring chính thức khuyến nghị allowlist thay `disallowedFields`; đã từng có các bản vá cho trường hợp bypass kiểm tra trường cấm.

Ví dụ, advisory Spring `CVE-2025-22233` mô tả các bản 6.2.0–6.2.6 chịu ảnh hưởng và chỉ ra 6.2.7 là bản sửa. Bài học không phải sử dụng CVE để thay review, mà là **không lấy denylist mong manh làm security boundary**; sử dụng phiên bản Spring được duy trì và chủ động cập nhật bản vá.

## 6. Constructor binding cũng phải được kiểm tra khi model thay đổi

Một record:

~~~java
public record ProfileCommand(
        String displayName,
        String contactEmail) {
}
~~~

không có setter nên giới hạn property binding. Với Spring constructor binding, mỗi thành phần là một input candidate. Nếu PR thêm:

~~~java
public record ProfileCommand(
        String displayName,
        String contactEmail,
        boolean verified) {
}
~~~

thì input contract **đã thay đổi**, dù `setDeclarativeBinding(true)` vẫn bật. Constructor arguments phải được review giống public fields.

### 6.1. `@BindParam` và đổi tên input

~~~java
public record ProfileCommand(
        @BindParam("display-name") String displayName,
        String contactEmail) {
}
~~~

`@BindParam` từ Spring Framework 6.1 có thể đặt ở constructor parameter/field tương ứng, cho phép một tên request như `display-name` ánh xạ tới `displayName`. Khi thêm/đổi annotation, client có thể được phép gửi **một key mới**. Cần test tên input cũ/mới, tính tương thích và authorization.

### 6.2. Indexed constructor arguments

Trong Spring Framework 6.2, constructor binding hỗ trợ List/Map/array với indexed/keyed paths như `items[0].code` hoặc `preferences[theme]`. Nếu PR thêm List vào constructor, cần rà:
- Collection length và index ranges.
- Nested child types và constructors.
- Which fields are actual public input.
- Giới hạn resource/JSON hoặc form field count.
- Quy tắc không để client chỉ định owner/price/role.

`allowedFields` cho property binding **không tự áp dụng như whitelist của constructor**. Hãy giữ constructor DTO nhỏ, giới hạn type và test khai báo input có chủ đích.

### 6.3. `@ModelAttribute(binding=false)` khi chỉ đọc object

Có những handler nhận object đã được tải và không muốn bind request lên nó. Spring hỗ trợ:

~~~java
@ModelAttribute(value = "account", binding = false)
Account account
~~~

Đây là đoạn parameter minh họa; Spring cần account tồn tại trong model hoặc được resolve phù hợp. `binding=false` có ý nghĩa **không áp request property binding cho attribute này**; nó không tự tải account và không kiểm tra quyền. Dùng khi cần đọc một model object do server kiểm soát, đồng thời thực hiện update qua một DTO riêng.

## 7. Nested properties, wildcards và map keys trong PR

### 7.1. Một setter lồng nhau có thể mở nhiều đường vào

Giả sử model có:

~~~java
public class Preferences {
    private boolean notificationsEnabled;
    private boolean administrativeAlerts;

    public boolean isNotificationsEnabled() {
        return notificationsEnabled;
    }
    public void setNotificationsEnabled(boolean value) {
        notificationsEnabled = value;
    }

    public boolean isAdministrativeAlerts() {
        return administrativeAlerts;
    }
    public void setAdministrativeAlerts(boolean value) {
        administrativeAlerts = value;
    }
}
~~~

Nếu `ProfileForm` expose `getPreferences()` và binder có thể đi vào nested object, các paths như:

~~~text
preferences.notificationsEnabled=true
preferences.administrativeAlerts=true
~~~

có thể được xử lý trong property binding tùy cấu trúc target. Nếu PR thêm setter `setAdministrativeAlerts` thì **ngay cả nested object** cũng phải được rà.

Không nên cho:

~~~java
binder.setAllowedFields("preferences*");
~~~

vì wildcard có thể bao phủ future nested properties. Chỉ chọn field được duyệt:

~~~java
binder.setAllowedFields(
        "displayName",
        "contactEmail",
        "preferences.notificationsEnabled");
~~~

### 7.2. Collection index và Map key

Form names có thể là:

~~~text
addresses[0].city=Hanoi
addresses[0].ownerId=another-user
labels[public].name=Important
labels[secret@example.com].name=Unexpected
~~~

Để cho người dùng sửa city mà không cho sửa ownership, chỉ chọn pattern tương ứng:

~~~java
binder.setAllowedFields("addresses[*].city");
binder.setAutoGrowCollectionLimit(10);
~~~

**Lưu ý:** dùng hai lời gọi `setAllowedFields` liên tiếp sẽ **thay thế danh sách cũ**, không phải cộng thêm. Nếu muốn nhiều fields, hãy truyền chúng trong **cùng một lần gọi**:

~~~java
binder.setAllowedFields(
        "displayName",
        "contactEmail",
        "addresses[*].city");
~~~

`setAutoGrowCollectionLimit(10)` giới hạn một số tình huống auto-grow list/array; nó **không phải quota tổng HTTP body**, không giới hạn mọi map keys, không ngăn client gửi hàng nghìn field names. Cần body size/parameter count/index/depth limits ở tầng web/proxy và tests boundary.

Khi Map keys do người dùng kiểm soát, tên path tự nó có thể chứa email/token. Không echo toàn bộ suppressed paths hay rejected values trong error body/logs.

### 7.3. Header và URI variable cũng nằm trong threat model

Trong annotated Spring MVC 6.2, model attribute binding có thể tham gia lấy dữ liệu từ:
- request parameters (query/form).
- URI template variables.
- headers được xử lý tên để phù hợp property names, theo điều kiện nguồn không bị request parameters ghi đè.

Không dùng `@ModelAttribute` làm nguồn xác thực ownership, role hay tenant ID. Nếu đường dẫn có `/accounts/{accountId}`, inject `@PathVariable` riêng, xác thực caller có quyền với ID đó, rồi gọi service. Client có thể cung cấp query/form field trùng tên; không dựa vào precedence ngầm định để quyết định quyền.

## 8. JSON model drift: Jackson có bề mặt riêng

### 8.1. Vì sao `setAllowedFields` không bảo vệ JSON?

Với:

~~~java
public class JsonAccountInput {
    private String displayName;
    private boolean verified;

    public void setDisplayName(String value) {
        displayName = value;
    }
    public void setVerified(boolean value) {
        verified = value;
    }
}
~~~

Jackson có thể deserialize JSON:

~~~json
{"displayName":"Lan","verified":true}
~~~

thành `JsonAccountInput` có `verified=true`, dù một controller khác có `@InitBinder` với allowlist. Đây là **anti-pattern minh họa**, không phải endpoint an toàn.

Cách tốt: JSON DTO chỉ chứa properties cho phép, ví dụ record `JsonProfileInput(String displayName, String contactEmail)`. Khi thêm record component, reviewer phải hỏi: "trường này có trở thành JSON input không?".

### 8.2. Fail unknown JSON fields khi cần

Jackson thường có cấu hình quyết định unknown JSON keys được bỏ qua hay báo lỗi. Với Spring Boot, có thể bật fail-fast:

~~~properties
spring.jackson.deserialization.fail-on-unknown-properties=true
~~~

Khi đó JSON gửi `"verified":true` vào record **không có** field `verified` có thể bị từ chối bằng lỗi body không đọc được (HTTP 400). Điều này giúp phát hiện client gửi ngoài contract, nhưng **không giải quyết drift nếu ai đó thêm field `verified` vào chính input DTO**: field mới trở thành known property. Vì vậy vẫn cần review schema/constructor và regression tests.

Nếu API cần cho phép unknown fields để tương thích phiên bản cũ, vẫn an toàn khi deserialize vào DTO có các fields được duyệt và **không tự map unknown data sang domain**. Chọn strict hay tolerant JSON theo product contract, không coi strict mode thay security review.

### 8.3. Các annotation/creator làm thay đổi quyền nhận input

Khi PR thêm hoặc sửa:
- `@JsonProperty`, `@JsonAlias`.
- `@JsonCreator` và constructor parameters.
- Setter được Jackson nhìn thấy.
- Field visibility rules.
- Custom deserializer.
- Map/`JsonNode`/`Object` nhận input không cấu trúc.
- Các polymorphic type/`@JsonTypeInfo`.
- Global ObjectMapper configuration.

hãy xem đó là **API surface change**. Không assume một Java class chỉ nhận tên property đúng như tên getter; aliases/creators có thể thêm public input names.

### 8.4. Không dùng deserialization để cấp quyền

`@JsonIgnore` và read-only properties có thể giúp giới hạn mapping, nhưng authorization không thuộc Jackson. Nếu người dùng gửi profile của tài khoản khác qua `accountId`, việc JSON parse thành công không xác nhận họ có quyền sửa; service phải xác thực principal, tenant và ownership.

## 9. Project chạy được: Spring Boot 3.5.7 / Java 17

Ví dụ sau minh họa **một DTO mutable cố tình có thêm setter trong quá trình refactor**, được bảo vệ bằng `@InitBinder` và `allowedFields`; đồng thời có một JSON input record với strict unknown-field handling. Các tests bao phủ cả lỗi và happy path.

### 9.1. Cấu trúc project

~~~text
pom.xml
src/main/
  java/com/example/bindingreview/
    BindingReviewApplication.java
    ProfileForm.java
    JsonProfileInput.java
    ProfileUpdateService.java
    ProfileController.java
    SafeErrorAdvice.java
  resources/
    application.properties
src/test/java/com/example/bindingreview/
  ProfileBindingContractTest.java
  ProfileHttpSecurityTest.java
~~~

Trong production, **không để các field protected xuất hiện trên input DTO**. `ProfileForm` ở đây cố ý chứa `verified` và `timezone` để kiểm chứng rằng một setter mới **không được phép tự mở** trên endpoint form hiện tại.

### 9.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>model-binding-review</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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
</project>
~~~

Dùng Spring MVC Servlet stack, không thêm `spring-boot-starter-webflux` trong ví dụ này. `spring-boot-starter-validation` cung cấp Jakarta provider, `spring-boot-starter-test` chứa JUnit 5 và MockMvc.

### 9.3. Main application

~~~java
// src/main/java/com/example/bindingreview/BindingReviewApplication.java
package com.example.bindingreview;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingReviewApplication {
    public static void main(String[] args) {
        SpringApplication.run(BindingReviewApplication.class, args);
    }
}
~~~

### 9.4. `ProfileForm`: nhìn thấy drift khi thêm setters

~~~java
// src/main/java/com/example/bindingreview/ProfileForm.java
package com.example.bindingreview;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class ProfileForm {

    @NotBlank
    @Size(max = 80)
    private String displayName;

    @NotBlank
    @Email
    private String contactEmail;

    // Giả định một PR khác thêm hai setters này.
    // Cả hai chưa được duyệt cho endpoint chỉnh sửa hồ sơ.
    private boolean verified;
    private String timezone;

    public ProfileForm() {}

    public String getDisplayName() {
        return displayName;
    }
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getContactEmail() {
        return contactEmail;
    }
    public void setContactEmail(String contactEmail) {
        this.contactEmail = contactEmail;
    }

    public boolean isVerified() {
        return verified;
    }
    public void setVerified(boolean verified) {
        this.verified = verified;
    }

    public String getTimezone() {
        return timezone;
    }
    public void setTimezone(String timezone) {
        this.timezone = timezone;
    }
}
~~~

`@NotBlank`/`@Email`/`@Size` chỉ kiểm tra dữ liệu công khai; không có constraint nào cấp quyền cho client gán `verified`. Mặc định `verified=false` và `timezone=null`. Sau khi form binding có whitelist, chúng phải giữ nguyên, dù request gửi cùng tên.

**Trong dự án thật**, thay vì dùng một DTO chứa các trường protected để thử nghiệm mãi mãi, hãy loại chúng khỏi input DTO. Demo giữ lại để làm một test minh họa về regression/security contract.

### 9.5. JSON record chỉ nhận public input

~~~java
// src/main/java/com/example/bindingreview/JsonProfileInput.java
package com.example.bindingreview;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record JsonProfileInput(
        @NotBlank @Size(max = 80) String displayName,
        @NotBlank @Email String contactEmail) {
}
~~~

Khi Jackson đọc JSON, chỉ có hai record components được dự kiến là input. Nếu ai đó thêm `boolean verified` vào record, chính file này sẽ hiện ra trong PR và tests schema phải được cập nhật có xét duyệt.

### 9.6. Service chỉ áp đúng hai fields

~~~java
// src/main/java/com/example/bindingreview/ProfileUpdateService.java
package com.example.bindingreview;

import org.springframework.stereotype.Service;
import java.util.Map;

@Service
public class ProfileUpdateService {

    public Map<String, Object> update(
            String displayName, String contactEmail) {

        // Giả lập entity do server tải sau bước authorization.
        Account account = new Account();
        account.changeContact(displayName, contactEmail);

        return Map.of(
                "displayName", account.displayName,
                "contactEmail", account.contactEmail,
                "role", account.role,
                "verified", account.verified);
    }

    private static final class Account {
        private String displayName = "Old";
        private String contactEmail = "old@example.com";
        private final String role = "USER";
        private final boolean verified = false;

        void changeContact(String name, String email) {
            this.displayName = name;
            this.contactEmail = email;
        }
    }
}
~~~

Không có database trong demo; nó mô phỏng dữ liệu đã được chọn an toàn. Trong production, service phải xác minh principal/tenant/ownership trước khi sửa entity thật. Điều quan trọng ở đây là service **chỉ nhận/copy hai giá trị đã được duyệt**, không dùng `BeanUtils.copyProperties(request, entity)` hoặc generic mapper có nguy cơ tự copy properties mới.

Response chứa `role=USER` và `verified=false` chỉ để test không thể đổi protected state. Hệ thống thật cần response DTO riêng và xem xét field nào có thể công khai.

### 9.7. Controller: `@InitBinder` giữ contract bất biến

~~~java
// src/main/java/com/example/bindingreview/ProfileController.java
package com.example.bindingreview;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/profiles")
public class ProfileController {

    private final ProfileUpdateService service;

    public ProfileController(ProfileUpdateService service) {
        this.service = service;
    }

    @InitBinder("profileForm")
    void configure(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
        binder.setAllowedFields(
                "displayName", "contactEmail");
    }

    @PostMapping(path = "/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> updateForm(
            @Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult errors) {

        // Suppressed property không mặc nhiên là FieldError.
        if (errors.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                    .body(Map.of("code", "UNEXPECTED_FIELDS"));
        }

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("code", "INVALID_INPUT"));
        }

        return ResponseEntity.ok(
                service.update(
                        form.getDisplayName(),
                        form.getContactEmail()));
    }

    @PostMapping(path = "/json",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> updateJson(
            @Valid @RequestBody JsonProfileInput input) {

        return ResponseEntity.ok(
                service.update(
                        input.displayName(),
                        input.contactEmail()));
    }
}
~~~

Giải thích:
1. `@InitBinder("profileForm")` áp cho binder của đúng model attribute tên `profileForm`.
2. `setDeclarativeBinding(true)` giữ contract explicit về setter binding.
3. `setAllowedFields("displayName","contactEmail")` chỉ cho phép hai properties được duyệt.
4. Nếu client gửi thêm `verified`/`timezone`, binder ghi suppressed fields. Handler trả 400 **mà không echo tên field hay raw value**.
5. Nếu input công khai sai `@NotBlank`/`@Email`, `BindingResult` ở ngay sau form giúp trả `INVALID_INPUT`.
6. JSON endpoint dùng `JsonProfileInput` riêng; form allowlist **không phải** JSON filter. JSON unknown-field handling ở mục tiếp theo.
7. Service chỉ xử lý displayName/contactEmail; authorization cho entity thật vẫn phải có ở production.

### 9.8. JSON strict mode và error advice không lộ internals

**`src/main/resources/application.properties`:**

~~~properties
spring.jackson.deserialization.fail-on-unknown-properties=true
server.error.include-message=never
server.error.include-stacktrace=never
server.error.include-binding-errors=never
~~~

Strict JSON khiến input có `verified` ngoài `JsonProfileInput` được báo lỗi thay vì bỏ qua. Hai nhóm protection khác nhau: **DTO bảo vệ domain field**, còn **strict mode** giúp phát hiện client gửi ngoài contract.

**`SafeErrorAdvice.java`:**

~~~java
// src/main/java/com/example/bindingreview/SafeErrorAdvice.java
package com.example.bindingreview;

import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;

@RestControllerAdvice
public class SafeErrorAdvice {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, String>> invalidJson(
            HttpMessageNotReadableException ignored) {

        // Không trả Jackson parser exception / raw JSON.
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_JSON"));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> invalidObject(
            MethodArgumentNotValidException ignored) {

        // Không trả FieldError.rejectedValue.
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_INPUT"));
    }
}
~~~

Advice chỉ phục vụ demo; trong product nên chuẩn hóa ProblemDetail, mã lỗi, issue path an toàn và nhiều locale. Nhưng không trả toàn bộ `BindingResult`/`ConstraintViolation` hoặc exception message ra public response. Strict JSON violation vì unknown `verified` được xử lý an toàn bằng code `INVALID_JSON`.

## 10. Kiểm thử: phát hiện setter drift trước khi lên production

### 10.1. Unit test trực tiếp trên WebDataBinder và JavaBean descriptors

~~~java
// src/test/java/com/example/bindingreview/ProfileBindingContractTest.java
package com.example.bindingreview;

import org.junit.jupiter.api.Test;
import org.springframework.beans.BeanUtils;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.web.bind.WebDataBinder;

import java.beans.PropertyDescriptor;
import java.util.Arrays;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProfileBindingContractTest {

    @Test
    void unprotectedPropertyBindingSeesNewSetter() {
        ProfileForm form = new ProfileForm();
        WebDataBinder open =
                new WebDataBinder(form, "profileForm");

        open.bind(new MutablePropertyValues(
                Map.of("verified", "true")));

        // Chứng minh bề mặt tấn công nếu không whitelist.
        assertTrue(form.isVerified());
    }

    @Test
    void guardedBinderSuppressesUndeclaredFields() {
        ProfileForm form = new ProfileForm();
        WebDataBinder guarded =
                new WebDataBinder(form, "profileForm");

        new ProfileController(new ProfileUpdateService())
                .configure(guarded);

        guarded.bind(new MutablePropertyValues(Map.of(
                "displayName", "Lan",
                "contactEmail", "lan@example.com",
                "verified", "true",
                "timezone", "Sensitive-zone"
        )));

        assertEquals("Lan", form.getDisplayName());
        assertEquals("lan@example.com", form.getContactEmail());
        assertFalse(form.isVerified());
        assertNull(form.getTimezone());

        Set<String> suppressed = Set.copyOf(Arrays.asList(
                guarded.getBindingResult().getSuppressedFields()));
        assertEquals(Set.of("verified", "timezone"), suppressed);
        assertFalse(guarded.getBindingResult().hasErrors());
        // Suppressed fields tự chúng không phải validation errors.
    }

    @Test
    void anyNewWritablePropertyRequiresReview() {
        Set<String> actualWritable = Arrays.stream(
                BeanUtils.getPropertyDescriptors(ProfileForm.class))
                .filter(p -> p.getWriteMethod() != null)
                .map(PropertyDescriptor::getName)
                .collect(Collectors.toSet());

        assertEquals(Set.of(
                "displayName", "contactEmail", "verified", "timezone"),
                actualWritable,
                "A setter changed the binding surface: review policy and tests");
    }

    @Test
    void serviceCanOnlyApplyPublicFields() {
        Map<String, Object> output =
                new ProfileUpdateService().update(
                        "Lan", "lan@example.com");

        assertEquals("Lan", output.get("displayName"));
        assertEquals("lan@example.com",
                output.get("contactEmail"));
        assertEquals("USER", output.get("role"));
        assertEquals(false, output.get("verified"));
    }
}
~~~

**Điểm quan trọng của test reflection:** nếu developer thêm một setter mới, ví dụ `setBillingEnabled(boolean)`, tập writable properties thay đổi và test thứ ba **fail**, buộc reviewer phân loại field và cập nhật danh sách được kiểm tra một cách có chủ đích. Đây không phải hệ thống bảo mật tự động; nó là **CI tripwire** báo thay đổi bề mặt model.

Với dự án dùng Lombok `@Data`, `@Setter`, builder, record, Kotlin data class hoặc Jackson visibility config, review phải kiểm tra **generated properties và JSON creators** tương ứng, không chỉ Java source setter methods. JavaBean descriptor test bao phủ setter surface của `ProfileForm`, **không** thay thế contract test của JSON.

### 10.2. MockMvc integration tests cho form và JSON

~~~java
// src/test/java/com/example/bindingreview/ProfileHttpSecurityTest.java
package com.example.bindingreview;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProfileHttpSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validFormEditsOnlyPublicFields() throws Exception {
        mvc.perform(post("/api/profiles/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Lan")
                .param("contactEmail", "lan@example.com"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.contactEmail")
                    .value("lan@example.com"))
            .andExpect(jsonPath("$.role").value("USER"))
            .andExpect(jsonPath("$.verified").value(false));
    }

    @Test
    void extraFormSettersAreRejected() throws Exception {
        mvc.perform(post("/api/profiles/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Lan")
                .param("contactEmail", "lan@example.com")
                .param("verified", "true")
                .param("timezone", "Sensitive-zone"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("UNEXPECTED_FIELDS"))
            .andExpect(content().string(not(
                    containsString("Sensitive-zone"))));
    }

    @Test
    void invalidFormStillRunsBeanValidation() throws Exception {
        mvc.perform(post("/api/profiles/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", " ")
                .param("contactEmail", "bad-email"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }

    @Test
    void jsonUnknownProtectedFieldIsNotAccepted()
            throws Exception {
        mvc.perform(post("/api/profiles/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"displayName":"Lan",
                     "contactEmail":"lan@example.com",
                     "verified":true}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }

    @Test
    void validJsonHasOnlyExpectedPublicInput()
            throws Exception {
        mvc.perform(post("/api/profiles/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"displayName":"Lan",
                     "contactEmail":"lan@example.com"}
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.role").value("USER"))
            .andExpect(jsonPath("$.verified").value(false));
    }

    @Test
    void invalidJsonValueIsValidated() throws Exception {
        mvc.perform(post("/api/profiles/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"displayName":"",
                     "contactEmail":"bad-email"}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }
}
~~~

**Kết quả kỳ vọng:** 10 JUnit tests PASS (4 `ProfileBindingContractTest` + 6 `ProfileHttpSecurityTest`) với Spring Boot 3.5.7 và cấu trúc project đúng như trên. Đây là **dự kiến qua phân tích API/code**, chưa phải kết quả Maven đã thực thi.

Chạy:

~~~bash
mvn test
~~~

Chạy riêng contract tests:

~~~bash
mvn -Dtest=ProfileBindingContractTest test
~~~

Chạy server:

~~~bash
mvn spring-boot:run
~~~

Gửi request hợp lệ:

~~~bash
curl -i -X POST http://localhost:8080/api/profiles/form \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "displayName=Lan" \
  --data-urlencode "contactEmail=lan@example.com"
~~~

Response JSON kỳ vọng (không cam kết thứ tự keys):

~~~json
{
  "displayName": "Lan",
  "contactEmail": "lan@example.com",
  "role": "USER",
  "verified": false
}
~~~

Thử extra field:

~~~bash
curl -i -X POST http://localhost:8080/api/profiles/form \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "displayName=Lan" \
  --data-urlencode "contactEmail=lan@example.com" \
  --data-urlencode "verified=true"
~~~

Kết quả dự kiến HTTP 400, body `{"code":"UNEXPECTED_FIELDS"}`. Nếu controller bỏ whitelist, `verified` có setter và có thể nhận true như unit test `unprotectedPropertyBindingSeesNewSetter` đã minh họa.

### 10.3. Vì sao chỉ test status 400 không đủ?

Nếu chỉ assert request xấu trả 400, bạn có thể bỏ sót:
- Input ngoài hợp đồng bị bind rồi một constraint khác mới từ chối.
- Protected field bị gán nhưng service sau đó ghi đè ngẫu nhiên.
- Mapping mới copy thêm fields vào domain mà HTTP test không quan sát.
- JSON unknown keys từng fail nhưng sau PR thêm component thành known.
- Một controller khác thiếu `@InitBinder` vẫn nhận field protected.

Vì vậy cần kết hợp **contract test**, **binder test**, **HTTP-level test**, **service mapping test** và (ở production) **authorization test**. Tối thiểu phải có một test chứng minh field protected **không thay đổi** sau khi gửi payload ác ý.

## 11. Quy trình review PR/CI dành cho model changes

### Bước 1 — Xác định mọi đường binding

Tìm tất cả chỗ class đó xuất hiện:
- `@ModelAttribute` trong MVC/WebFlux annotated controllers.
- `@RequestBody`/`@RequestPart` và JSON DTO mapping.
- Custom `WebDataBinder`, `@InitBinder`, `@ControllerAdvice`.
- Constructor binding, record, `@BindParam`.
- Custom setters được tạo bởi Lombok/Kotlin.
- Generic mapper, form-to-entity converters và code copy properties.
- Tầng service/domain nhận nguyên object từ request.

Không chỉ grep controller trực tiếp: một object cũng có thể được resolve từ model/session hoặc bị dùng bởi method khác.

### Bước 2 — Lập bảng trường public/protected

| Field | Ai được cung cấp? | Public input? | Nơi xác minh |
| --- | --- | --- | --- |
| `displayName` | Người sở hữu profile | Có, sau auth | DTO + binder + service |
| `contactEmail` | Người sở hữu profile | Có, sau auth | DTO + validator + service |
| `timezone` | Product chưa duyệt | Chưa | Regression test |
| `verified` | Quy trình server/admin | Không | Service-only, no setter binding |
| `role` | Server/admin theo policy | Không | Security/authorization |
| `ownerId` | Server/principal/path đã xác minh | Không do form tự chọn | Service permission check |
| `billingState` | Hệ thống billing | Không | Domain invariant |

Bảng này có thể sống trong API schema/code ownership documentation; trong PR cần cập nhật đúng nơi nếu quyết định mở một field. Không dùng các annotations như `@NotNull` hoặc tên biến để suy ra quyền.

### Bước 3 — Duyệt mọi đường dẫn property mới

Rà:
- New setters, record components, constructor parameters.
- Nested objects, collections, map properties.
- `@JsonProperty`, `@JsonAlias`, polymorphism và creator metadata.
- `@BindParam` và field-name aliases.
- Binder allowlist patterns, đặc biệt wildcard `*`.
- `setDeclarativeBinding` và `@ModelAttribute(binding=false)`.
- ConversionService/custom editors có thể làm một giá trị trước đây không parse được nay parse được.
- Model attributes được load từ database/session rồi bị bind lại.

Đừng chỉ hỏi "field mới có trong HTML form không?". HTML không giới hạn HTTP request do client tự tạo.

### Bước 4 — Update tests trước khi merge

Ít nhất:
1. Request chỉ có fields public được chấp nhận.
2. Request cố gửi mỗi protected field vẫn không thay đổi protected state.
3. Field mới ngoài allowlist bị reject hoặc ignore theo contract.
4. JSON body có extra property hoạt động theo policy (strict/tolerant).
5. Nested/indexed/map key paths vượt phạm vi không bind.
6. Constructor DTO thay đổi phải làm fail test schema/contract đến khi review.
7. Validation vẫn áp cho các fields công khai.
8. Service không copy all-properties từ input sang entity.
9. Caller khác role/tenant không sửa được object không sở hữu.

### Bước 5 — Review compatibility và migration

Mở một field mới là **thay đổi API**, không chỉ thêm Java property:
- Client cũ có tiếp tục hoạt động?
- Client mới gửi field không có ở backend cũ thì được bỏ qua hay bị reject?
- Rollout nhiều phiên bản backend có cần feature flag?
- Optional field null/default semantics là gì?
- Nếu mở field như `timezone`, nó có được chuyển thành service update một cách an toàn chưa?
- Bản dịch error message và tài liệu OpenAPI có cập nhật không?

Không chỉ mở wildcard để "tránh lỗi client mới" khi triển khai rolling upgrades; việc mở toàn bộ field tương lai là một tradeoff bảo mật không cần thiết.

### Bước 6 — Cập nhật security review khi đổi version/framework

Một nâng cấp Spring/Jackson có thể đổi matching/property introspection/constructor behavior. Review bản vá bảo mật, thử malicious payloads và chạy regression tests trong context thật. `disallowedFields` có lịch sử các security advisories; dedicated DTO/allowlist và tests giúp giảm sự phụ thuộc vào blacklist behavior.

## 12. Các bẫy khiến review bỏ sót input surface

| Tình huống | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| Controller không đổi, chỉ entity có setter mới | Binder tự match field mới | Không bind entity trực tiếp; DTO + allowlist |
| Có `@Valid` nên tưởng đã an toàn | Validation không quyết định quyền | Authorization, DTO mapping |
| Chỉ dùng `setDisallowedFields` | Mỗi field mới lại cần nhớ chặn | `setAllowedFields` explicit |
| `setIgnoreUnknownFields(false)` | Setter mới biến unknown thành known | Contract test + allowlist |
| `allowedFields("settings*")` | Wildcard khớp future nested fields | Liệt kê cụ thể approved paths |
| Gọi `setAllowedFields` hai lần | Lần sau thay danh sách trước | Gộp toàn bộ paths trong một call |
| Chỉ đọc `errors.hasErrors()` | Suppressed input không là FieldError | Kiểm tra `getSuppressedFields()` |
| Record immutable nên bỏ qua review | Thêm constructor component mở input mới | Test constructor contract |
| `@RequestBody` mà dựa vào `@InitBinder` | Jackson JSON dùng cơ chế khác | JSON DTO/strict policy |
| JSON unknown-field fail nên yên tâm | Thêm property vào DTO khiến field thành known | Schema diff gate |
| Dùng output DTO làm input DTO | Output fields không đồng nghĩa editable | Separate read/write DTO |
| Nested collection mới có setter | Mở `items[0].price` hoặc Map keys | Path allowlist + size limits |
| Dùng mapper copy mọi property | DTO mới có field là entity cũng bị cập nhật | Explicit service mapping |
| ID chủ sở hữu nằm trong body | Client tự chọn đối tượng/tenant | Dựa vào principal/path đã authorize |
| Chỉ test UI HTML | Client tự gửi HTTP parameters bất kỳ | HTTP negative tests |
| Một controller khác không có binder rule | Protection chỉ ở phạm vi local | Test mọi entrypoint hoặc scoped advice |
| Log suppressed field paths raw | Map keys có thể mang email/token | Redact/canonicalize logs |
| Chỉ xem source code getters | Lombok/Jackson có thể tạo accessors/aliases | Inspect effective runtime binding contract |
| Test chỉ dùng happy path | Không bắt được mass assignment | Fuzz unauthorized property names |

## 13. Bài tập tự luyện

1. Thêm `boolean billingEnabled` và setter vào `ProfileForm`, chạy test reflection. Giải thích vì sao test fail là **tín hiệu review**, không phải lỗi test cần xóa.
2. Giữ whitelist không đổi rồi gửi `billingEnabled=true` qua form; kiểm tra suppressed fields, response 400 và domain state không thay đổi.
3. Product chấp thuận `timezone` là public preference. Cập nhật DTO/allowlist/service/test theo cách tường minh và giữ `verified` protected.
4. Chuyển mutable `ProfileForm` thành immutable record, bật `setDeclarativeBinding(true)`. Thử thêm constructor component protected và giải thích vì sao flag không đủ ngăn.
5. Tạo nested `preferences.notificationsEnabled` và `preferences.administrativeAlerts`. Chỉ cho bind notifications; thử broad wildcard rồi sửa.
6. Gửi JSON chứa unknown `verified` với strict mode bật và tắt. Xác nhận khi JSON input DTO chứa `verified` mới thì strict mode **không còn chặn** key đó.
7. Dùng `@BindParam("display-name")` trên record component và viết test cho tên HTTP được chấp nhận.
8. Dùng hai controller cùng DTO; đặt local `@InitBinder` ở một controller, rồi test controller kia để thấy protection **không tự lan**.
9. Tạo property trong Map có key là email; kiểm tra policy xử lý path/rejected values không làm rò thông tin trong response/log.
10. Viết architecture rule hoặc test sinh danh sách writable bean properties và JSON input properties. Khi thêm property mới, CI phải bắt reviewer xác nhận contract.
11. Kiểm tra API có `@ModelAttribute(binding=false)`: bỏ flag trong một nhánh test và quan sát hành vi khác, sau đó khôi phục.
12. Review một dự án có generic `BeanUtils.copyProperties`, xác định những fields tương lai có thể vô tình được chuyển qua domain.

## 14. Checklist trước khi approve model-change PR

- [ ] Liệt kê endpoints dùng class đổi, gồm `@ModelAttribute`, `@RequestBody`, constructor bind, JSON creators và shared DTOs.
- [ ] Class là dedicated input DTO, không phải domain/JPA entity hoặc response DTO dùng lại tùy tiện.
- [ ] Tất cả setters/record components/constructor args mới đã được phân loại là public hay protected.
- [ ] Có `@InitBinder`/`setAllowedFields` cho mọi case bắt buộc property binding, không rely vào denylist.
- [ ] `setDeclarativeBinding(true)` được áp khi muốn giới hạn setter binding; constructor parameters cũng được review.
- [ ] Wildcard/nested/indexed allowed paths không vô tình nhận protected future fields.
- [ ] Không đọc `hasErrors()` như phép thay thế kiểm tra `getSuppressedFields()`.
- [ ] `@Valid` dùng cho data constraints, authorization đặt ở service/security boundary.
- [ ] JSON `@RequestBody` có DTO riêng và unknown-field policy phù hợp; không mong `allowedFields` xử lý JSON.
- [ ] Service chỉ copy các fields được duyệt; role/owner/verified/billingState không đến từ HTTP form hay JSON.
- [ ] Có tests phản chứng cho setters mới, nested paths, JSON unknown keys và regression của permissions.
- [ ] Có schema/reflection/contract test khiến thay đổi input surface được nêu rõ khi CI chạy.
- [ ] Không echo raw suppressed fields, rejected values, Map keys nhạy cảm trong response/logs.
- [ ] Đã kiểm tra bản vá Spring/Jackson, compatibility và rollout nếu mở một field có chủ đích.
- [ ] Documentation, OpenAPI và thông báo lỗi phản ánh đúng contract mới.

## 15. Kết luận

**Một field mới không được xem là editable chỉ vì nó xuất hiện trong Java model.** Trong Spring Framework, setters, constructor parameters, nested properties và Jackson inputs là những bề mặt cần review như API endpoints. Bảo vệ lâu dài nhất là:

1. **Dedicated input DTO** chỉ gồm các fields được phép.
2. **Explicit allowlist** khi property binding vẫn cần.
3. **Declarative/constructor binding** có constructor contract được review.
4. **Service mapping tường minh** sau khi xác thực và phân quyền.
5. **Negative regression tests** làm CI cảnh báo khi xuất hiện setter/field mới.
6. **Review các đường form và JSON riêng** để không tạo lỗ hổng từ giả định sai.

Nếu một PR thêm setter mà không cập nhật được input contract, authorization và tests, hãy coi đó là thay đổi **chưa được xét duyệt**, không phải tự động mở quyền chỉnh sửa.

## 16. Tài liệu tham khảo

- Spring Framework 6.2 — MVC `@InitBinder`, model design, `allowedFields`, `declarativeBinding`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework 6.2 — MVC `@ModelAttribute` và constructor/property binding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 — MVC Data Binding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html
- Spring Framework 6.2 — Core DataBinder Javadoc: https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.2 — `@BindParam` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/web/bind/annotation/BindParam.html
- Spring Framework 6.2 — MVC `@RequestBody`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework 6.2 — WebFlux DataBinder safety: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-initbinder.html
- Spring Security Advisory — CVE-2025-22233: https://spring.io/security/cve-2025-22233/
- Spring Security Advisory — CVE-2024-38820: https://spring.io/security/cve-2024-38820/
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- OWASP — Mass Assignment Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html
