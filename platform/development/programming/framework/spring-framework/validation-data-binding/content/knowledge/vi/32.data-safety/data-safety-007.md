# Phân biệt chuẩn hóa, validation, escaping và phân quyền trong Spring Framework

## 1. Mục tiêu: bốn lớp phòng vệ giải quyết bốn câu hỏi khác nhau

Khi Spring MVC nhận dữ liệu từ trình duyệt, JSON API, webhook hay ứng dụng khác, cùng một chuỗi có thể đi qua nhiều bước. Bốn thuật ngữ thường bị trộn lẫn là **chuẩn hóa (normalization)**, **validation (kiểm tra hợp lệ)**, **escaping/encoding (mã hóa đầu ra theo ngữ cảnh)** và **authorization (phân quyền)**. Chúng không thay thế được cho nhau.

Ví dụ người dùng gửi tên hiển thị chứa:

```text
  <img src=x onerror=alert(1)>  
```

Khi lưu hoặc hiển thị, ứng dụng cần trả lời nhiều câu hỏi độc lập:

- Dữ liệu có khoảng trắng đầu/cuối, cách biểu diễn Unicode hay định dạng nào cần **chuẩn hóa nhất quán** không?
- Độ dài, kiểu, ký tự hoặc quy tắc nghiệp vụ có **được chấp nhận** không?
- Khi render tên vào HTML, nó có bị trình duyệt hiểu như mã HTML/JavaScript thay vì văn bản không? Đây là trách nhiệm của **escaping/encoding tại nơi xuất dữ liệu**.
- Người gửi có thật sự **được phép sửa profile có ID này** không? Đây là trách nhiệm của authentication/authorization.

**Một chuỗi hợp lệ về cú pháp vẫn có thể gây XSS khi được đưa vào HTML không escape; một chuỗi đã escape vẫn có thể thuộc tài khoản người khác; một người đăng nhập vẫn có thể không được sửa mọi tài nguyên.**

Bài học dùng Java 17+, Spring Boot 3.5.x, Spring MVC, Jakarta Bean Validation, Spring Security và Thymeleaf để làm rõ thứ tự, phạm vi, điểm kiểm tra và các bẫy bảo mật thường gặp. Đây không phải hướng dẫn triển khai một hệ thống production đầy đủ; phần ví dụ minh họa có user in-memory và chỉ chạy loopback.

## 2. Bảng so sánh nhanh

| Lớp | Câu hỏi | Ví dụ | Thời điểm chính | Không thay thế được |
| --- | --- | --- | --- | --- |
| **Normalization** | “Cùng một giá trị được biểu diễn nhất quán chưa?” | `strip()` khoảng trắng, Unicode NFC, chuẩn hóa mã định danh | Trước những phép so sánh/validation cần quy ước thống nhất | Không chặn XSS, SQL injection hay truy cập trái phép |
| **Validation** | “Giá trị có phù hợp contract và business rules không?” | `@NotBlank`, `@Size`, `@Email`, kiểm tra miền giá trị | Sau parse/binding và sau normalization được thiết kế | Không xác thực quyền sở hữu; không mã hóa output |
| **Escaping/encoding** | “Dữ liệu được biểu diễn an toàn ở **ngữ cảnh đầu ra này** chưa?” | Thymeleaf `th:text` cho HTML text; JSON serializer cho JSON | Ngay trước khi đưa dữ liệu vào HTML/JS/URL/CSS/SQL sink theo API phù hợp | Không làm input hợp lệ hoặc cho phép thao tác |
| **Authorization** | “Principal hiện tại có quyền làm hành động này trên resource/field này không?” | Ownership/tenant check, `@PreAuthorize`, policy service | Trước khi đọc thông tin nhạy cảm hoặc thay đổi trạng thái | Không kiểm tra định dạng và không chống XSS |
| **Authentication** (đi cùng phân quyền) | “Người gọi là ai?” | Session login, OIDC, access token | Trước authorization | Đăng nhập không đồng nghĩa có mọi quyền |

Với SQL, biện pháp chính không phải HTML escaping mà là **parameterized query/prepared statement**. Với HTML phong phú do người dùng được phép nhập, một lớp riêng là **HTML sanitization** bằng thư viện chuyên dụng; nó cũng không thay authorization.

## 3. Chuỗi xử lý thực tế trong Spring MVC

Với form được bind bằng `@ModelAttribute`, một thiết kế dễ hiểu là:

```text
HTTP request
   |
   +-- Security filter chain: xác thực, kiểm tra truy cập sơ bộ, CSRF
   |
   v
DispatcherServlet -> HandlerMapping -> @ModelAttribute
   |
   +-- WebDataBinder: chuyển kiểu / @InitBinder / normalization theo field
   |      (chỉ bind những thuộc tính được phép)
   |
   +-- Jakarta Bean Validation / Spring Validator
   |      @NotBlank, @Size, custom constraints
   |
   v
Controller / service
   |
   +-- Authorization theo owner/tenant/role/action
   |      (kiểm tra resource cụ thể, không dựa trên hidden field)
   |
   +-- Thực thi nghiệp vụ / lưu trữ dữ liệu đã được chấp nhận
   |
   v
View template / JSON serializer / các sink khác
   |
   +-- Encoding/escaping đúng context khi xuất
   v
HTTP response
```

Đây là **mô hình trách nhiệm**, không phải lời hứa rằng mọi endpoint đều tuần tự chính xác như sơ đồ. Spring Security có thể chặn request trước khi vào MVC; phương thức `@PreAuthorize` kiểm tra trước khi thân service được gọi; validation có thể chạy theo đường `@Valid`/`@Validated` hoặc method validation. Với `@RequestBody` JSON, Jackson decode body qua `HttpMessageConverter`, không đi qua cùng property-binding pipeline như form `@ModelAttribute`.

**Thứ tự “normalization trước validation” là một lựa chọn phải được triển khai có chủ đích.** Nếu normalize trong service **sau** khi `@Valid` đã chạy tại controller, những constraints đã kiểm tra dữ liệu gốc, không phải dữ liệu đã chuẩn hóa. Ví dụ chạy đầy đủ sẽ đặt normalization ngay tại field binding để Bean Validation nhìn thấy giá trị nhất quán.

## 4. Normalization: làm nhất quán, không “làm sạch mọi nguy cơ”

### 4.1. Ví dụ Unicode NFC

Một ký tự có dấu có thể có nhiều biểu diễn Unicode. Chẳng hạn ký tự `é` có thể là một code point dựng sẵn, hoặc `e` + combining acute accent.

```java
import java.text.Normalizer;

String composed = "Café";
String decomposed = "Cafe\u0301";

System.out.println(composed.equals(decomposed)); // false

String normalized = Normalizer.normalize(
    decomposed, Normalizer.Form.NFC);
System.out.println(composed.equals(normalized)); // true
```

Đây là đoạn Java minh họa. `java.text.Normalizer.Form.NFC` dùng **canonical composition**. Nó giúp các cách biểu diễn tương đương có thể so sánh, validate, index hoặc cache nhất quán hơn khi đó là chính sách của domain.

**NFC không phải một bộ lọc XSS.** Chuỗi `<script>` vẫn chứa các ký tự có ý nghĩa HTML sau normalization.

### 4.2. Trim/strip và giới hạn ngữ nghĩa

`String#strip()` bỏ những Unicode whitespace ở hai đầu theo định nghĩa `Character.isWhitespace`. Nó không xóa mọi ký tự vô hình, không thể thay thế chính sách về control characters và không tự giải quyết Unicode confusables.

Ví dụ:

```java
public static String normalizeDisplayName(String raw) {
    if (raw == null) {
        return null;
    }
    return Normalizer.normalize(
        raw.strip(), Normalizer.Form.NFC);
}
```

Đây là fragment, cần import `java.text.Normalizer`. Với domain “tên hiển thị”, trim hai đầu và NFC có thể là quy tắc hợp lý. Với password, chữ ký số, API token, mã thanh toán, serialized payload hoặc văn bản có ý nghĩa về khoảng trắng, **không được tự động normalize/strip** nếu protocol không quy định.

### 4.3. NFKC, case folding, URL decoding và canonicalization

- **NFC/NFD** là Unicode canonical normalization; **NFKC/NFKD** là compatibility normalization, có thể làm mất những phân biệt ký tự có ý nghĩa. Không dùng NFKC mặc định cho mọi input.
- **Case folding** hoặc `toLowerCase(Locale.ROOT)` hữu ích cho một số mã định danh không phân biệt hoa/thường. Nó không phải một thuật toán chính xác cho mọi ngôn ngữ và không nên áp dụng bừa bãi cho tên người.
- **URL percent-decoding** chỉ làm ở tầng protocol phù hợp và theo số lần xác định. Double-decoding có thể làm biến đổi đường dẫn ngoài ý muốn hoặc gây bypass các kiểm tra.
- **Path canonicalization** cần xác định path thực nằm trong root directory được phép; chỉ thay chuỗi `../` bằng chuỗi rỗng là không an toàn, nhất là khi có symlink và encoding khác.
- **File names, emails, domain names, internationalized identifiers** có các tiêu chuẩn/điều kiện riêng; không có một `normalize(String)` thần kỳ phù hợp cho tất cả.

**Nguyên tắc:** Chọn dạng chuẩn cho từng field, kiểm tra theo dạng chuẩn đó, lưu/so sánh nhất quán; không normalize lại tùy tiện ở nhiều tầng theo những quy tắc khác nhau.

### 4.4. Chuẩn hóa có thể làm thay đổi kết quả validation

Nếu người dùng gửi:

```text
"  Alice  "
```

và form yêu cầu tên từ 1–80 ký tự, bạn phải định nghĩa xem khoảng trắng hai đầu có được tính hay không. Nếu chính sách là bỏ khoảng trắng, validator nên xem `"Alice"`.

Ngược lại, nếu validate trên raw value rồi mới strip, có thể phát sinh chênh lệch độ dài, uniqueness và dữ liệu persisted. Quy tắc này đặc biệt quan trọng với Unicode normalization, vì số lượng UTF-16 code units hoặc số code points có thể thay đổi.

Lưu ý `@Size(max=80)` trên `String` đếm độ dài `CharSequence` của Java (thường là UTF-16 code units), **không phải số grapheme clusters người dùng nhìn thấy**. Nếu business cần giới hạn “ký tự hiển thị”, phải thiết kế phép đếm phù hợp riêng.

## 5. Validation: kiểm tra contract, không kiểm tra quyền một cách tự động

### 5.1. Bean Validation trên input DTO

```java
public class ProfileForm {

    @NotBlank
    @Size(max = 80)
    private String displayName;

    // Getters, setters, constructor...
}
```

Khi form có `@Valid @ModelAttribute("form") ProfileForm form`, Spring MVC dùng validator đã đăng ký (thường `LocalValidatorFactoryBean` khi Jakarta provider có mặt) để tạo lỗi `FieldError` trong `BindingResult`.

- `@NotBlank` kiểm tra chuỗi có chứa ký tự không phải khoảng trắng theo constraint contract.
- `@Size(max=80)` kiểm tra độ dài tối đa.
- Custom validator có thể kiểm tra reserved name, định dạng mã, điều kiện giữa các field hoặc các business invariants phù hợp.

**Validation có thể chấp nhận dữ liệu có ý nghĩa HTML.** Một tên hiển thị gồm dấu `<` và `>` không tự tạo XSS nếu được render đúng cách; không nên áp dụng blacklist cấm mọi dấu ngoặc nhọn hay ký tự có dấu chỉ để “chống XSS”.

### 5.2. Kiểm tra cú pháp, ngữ nghĩa và ngữ cảnh

| Loại kiểm tra | Ví dụ | Mục tiêu |
| --- | --- | --- |
| Syntactic | Email trông giống địa chỉ hợp lệ, mã theo regex | Nhận định dạng có ý nghĩa |
| Structural | Số phần tử, nested DTO, độ dài chuỗi, enum value | Không nhận cấu trúc bất thường |
| Semantic | Ngày bắt đầu không sau ngày kết thúc | Đảm bảo quy tắc giữa các giá trị |
| Business | Đơn không được chuyển trạng thái đã hủy | Kiểm tra invariant và workflow |
| Authorization | User A có được sửa đơn của B không? | **Kiểm tra quyền, là lớp riêng** |

Một request có thể “valid” ở cả bốn loại đầu nhưng vẫn phải từ chối vì người gửi không có quyền.

### 5.3. @Valid không phải phép màu

- Không tự cho biết caller có sở hữu entity hay không.
- Không tự chặn mass assignment nếu bind thẳng request vào entity nhiều fields.
- Không encode output hay tạo CSP.
- Không ngăn SQL injection nếu sau đó ghép chuỗi raw vào SQL.
- Không bảo đảm không có race condition nếu business rule cần transaction.
- Không thay thế xác thực JWT/session hoặc CSRF protection.

Ở web boundary, validation lỗi thường được xử lý qua `BindingResult` hoặc ngoại lệ tương ứng. Nếu `BindingResult` ngay sau form object, controller phải tự kiểm tra `errors.hasErrors()` trước khi lưu dữ liệu; chỉ khai báo `@Valid` mà vẫn tiếp tục lưu là một lỗi nghiêm trọng.

### 5.4. Validation theo fail-safe và over-posting

Một DTO đầu vào nên chỉ chứa thuộc tính được phép cập nhật. Với property binding, `WebDataBinder#setAllowedFields(...)` thêm hàng rào cho field allowlist; `BindingResult#getSuppressedFields()` cho biết các fields bị suppress.

Khi request gửi `role=ADMIN` nhưng form chỉ cho `displayName`, nên từ chối hoặc bỏ qua có chủ đích, **không bao giờ cập nhật role chỉ vì client gửi**. Dùng DTO riêng và explicit service mapping cho những thay đổi được phép.

## 6. Escaping/encoding: bảo vệ đúng sink, càng sát đầu ra càng tốt

### 6.1. Khái niệm

**Output encoding** biến dữ liệu thành biểu diễn không bị trình thông dịch của ngữ cảnh đích hiểu như cú pháp thực thi. Trong HTML text node, dấu `<` phải được mã hóa khi cần để nó hiển thị là ký tự văn bản, không tạo thẻ.

Ví dụ giá trị người dùng:

```text
<img src=x onerror=alert(1)>
```

Khi render như văn bản HTML một cách an toàn, kết quả HTML source sẽ gần như:

```html
&lt;img src=x onerror=alert(1)&gt;
```

Trình duyệt hiển thị các ký tự `<img ...>` như text; không tạo phần tử `img` để chạy event handler.

**Không nên lưu trước một chuỗi HTML-escaped vào database như thể đó là “đã được làm sạch vĩnh viễn”.** Nếu sau đó bạn render nó vào JSON, URL hoặc email, encoding của HTML text không tương ứng; thậm chí trong HTML có thể bị double-escape.

### 6.2. Thymeleaf th:text và th:utext

Với Spring MVC server-rendered template:

```html
<p th:text="${profile.displayName}">Example</p>
```

`th:text` xuất dữ liệu với HTML escaping. Trái lại:

```html
<!-- Cẩn thận: th:utext xuất HTML không escape. -->
<p th:utext="${profile.displayName}">Example</p>
```

`th:utext` chỉ dành cho nội dung **HTML đã được tin cậy/sanitized bằng chính sách rõ ràng**, không đưa raw input từ người dùng vào đó. Thymeleaf 3.1 có các giới hạn expression evaluation ở ngữ cảnh nguy hiểm, nhưng không thể coi đó là thay thế cho output encoding.

Trong frontend JavaScript:

- Dùng `textContent` để đưa dữ liệu vào text node.
- Tránh `innerHTML` với chuỗi không tin cậy.
- Nếu bắt buộc hiển thị rich HTML, sanitize theo allowlist tags/attributes/URLs bằng thư viện uy tín (ví dụ OWASP Java HTML Sanitizer), có tests cho malformed markup.
- Hạn chế inline event-handler attributes và tạo script từ chuỗi dữ liệu.

### 6.3. Context cụ thể quyết định encoding cụ thể

| Sink/ngữ cảnh | Cách xử lý chủ yếu | Vì sao HTML escaping đơn thuần chưa đủ |
| --- | --- | --- |
| HTML text node | HTML text encoding, template `th:text` | Không để biến thành thẻ |
| HTML attribute value | Quoted attribute + attribute encoding, template framework | Không để phá dấu quote/chèn attribute khác |
| URL path/query | URL encoding từng component + validate scheme/origin | HTML escaping không mã hóa URL components |
| JavaScript literal | Serialize JSON an toàn cho ngữ cảnh JS hoặc tách data khỏi code | HTML escaping không đồng nghĩa JS string escaping |
| CSS | CSS-safe encoding / tránh đưa raw input vào style | CSS có parser/sinks riêng |
| JSON HTTP response | JSON serializer, content type đúng | Không nối JSON string thủ công |
| SQL parameter | Prepared statement / parameter binding | **SQL injection không được giải quyết bằng HTML escaping** |
| Shell command | Tránh shell; dùng ProcessBuilder args cố định nếu cần | HTML escape không có ý nghĩa với shell |
| HTML rich text | Sanitization chuyên dụng rồi encoding đúng nơi render | Escaping toàn bộ sẽ mất format, sanitizer phải chống injection |
| Log | Structured logging + kiểm soát CR/LF/PII theo sink | Không tùy tiện ghi secret/rejected values |

**Không có một hàm escape(String) dùng chung cho mọi đầu ra.** Dùng đúng API của thư viện/framework tại từng sink; OWASP nhấn mạnh output encoding phải phù hợp context.

### 6.4. XSS protection bổ sung

Content Security Policy (CSP), Trusted Types (nếu môi trường hỗ trợ), template autoescaping, không dùng inline script và security headers là defense-in-depth. CSP không sửa được việc server dùng `th:utext` để chèn HTML không tin cậy. Đồng thời XSS không chỉ là `<script>`: event handlers, URL schemes, DOM sinks và parser contexts cũng quan trọng.

### 6.5. SQL injection là bài toán khác

Ví dụ nguy hiểm:

```java
String sql = "SELECT * FROM profiles WHERE username = '" + username + "'";
```

Kể cả username đã vượt qua `@Size`, chuỗi vẫn có thể thay đổi SQL syntax nếu bị nối như trên. Dùng parameter binding:

```java
PreparedStatement statement =
    connection.prepareStatement(
        "SELECT * FROM profiles WHERE username = ?");
statement.setString(1, username);
```

Hai fragment có biến `username`/`connection` chưa được định nghĩa, dùng để so sánh. Prepared statements tách query syntax khỏi data values. **Không** tự HTML-encode hoặc tự escape dấu quote để chống SQL injection.

## 7. Authorization: ai được làm gì trên tài nguyên nào?

### 7.1. Authentication khác authorization

- **Authentication** xác minh chủ thể, ví dụ người dùng `alice` đã đăng nhập.
- **Authorization** xem `alice` có quyền **đọc/sửa profile ID 1**, **đổi role**, **truy cập tenant khác** hoặc **xuất dữ liệu nhạy cảm** không.

Một người có role `USER` không tự được sửa mọi profile. Kiểm tra “đã đăng nhập” không thay thế kiểm tra ownership/tenant; đây là nguy cơ **IDOR/BOLA**.

Ví dụ:

```text
GET /profiles/1   -> Alice (owner) có thể xem
GET /profiles/2   -> Alice không được xem nếu profile 2 thuộc Bob
POST /profiles/2  -> Alice không được cập nhật dù dữ liệu hợp lệ
```

### 7.2. Bảo vệ nhiều tầng

Spring Security cung cấp:

- **Request-level rules** qua `SecurityFilterChain` và `authorizeHttpRequests`: chặn anonymous cho API riêng tư.
- **Method-level rules** qua `@EnableMethodSecurity` + `@PreAuthorize`: bảo vệ service method theo quyền và resource ID.
- Policy ở service/domain/data-access: tránh tự lấy owner từ HTTP form, tránh bypass khi một service được gọi từ controller khác.
- CSRF protection cho các trình duyệt có authentication tự động gửi qua cookie/session; đây là **một lớp khác với authorization**.

Spring Security Starter không tự bật `@PreAuthorize` cho mọi method nếu chưa có `@EnableMethodSecurity`. Các method không gắn authorization rule vẫn cần được bảo vệ bởi policy đúng chỗ.

### 7.3. Kiểm tra trước khi side effect

Không cập nhật database rồi mới dùng `@PostAuthorize` để phát hiện caller không được phép. Nếu một transaction đã thay đổi trạng thái, hậu kiểm tra có thể quá muộn hoặc khó đảm bảo rollback theo mọi trường hợp. Với write operations, ưu tiên `@PreAuthorize`/policy check **trước** khi sửa object; sau đó dùng transaction và invariants ở domain.

### 7.4. Deny by default và least privilege

Giữ mặc định **deny by default**: request chưa có policy phải bị từ chối thay vì vô tình public. Quyền nên đủ hẹp cho nhiệm vụ. Kiểm tra trên **mọi request** và mọi đường gọi có thể gây side effects, không chỉ nút “Save” trên UI.

Không dùng `ownerId` trong form như bằng chứng. Chính server cần biết owner từ dữ liệu đã xác thực, policy và entity record. Không trộn “đăng nhập thành công” với “được sửa entity này”.

## 8. Chương trình mẫu hoàn chỉnh: Spring MVC + Security + Thymeleaf

Chương trình này minh họa cả bốn lớp trên một màn hình sửa tên hiển thị. Data store là bộ nhớ cục bộ để tập trung vào luồng và tránh cấu hình database; request thật vẫn đi qua Spring MVC/Security.

**Thiết kế:**

- `GET /profiles/{id}`: chỉ chủ sở hữu đã xác thực mới xem được.
- `POST /profiles/{id}`: nhận **DTO chỉ có `displayName`**, chuẩn hóa bằng `@InitBinder` trước khi `@Valid`, kiểm tra `@NotBlank`/`@Size`, sau đó cập nhật qua service được `@PreAuthorize` bảo vệ.
- Thymeleaf `th:text` in dữ liệu đã lưu thành **HTML text được escape**, không render thẻ.
- Binder allowlist `displayName`; `role=ADMIN` do client gửi sẽ bị suppress và request bị từ chối.
- CSRF mặc định của Spring Security vẫn bật; form POST phải gửi token hợp lệ.
- Account cố định: profile 1 thuộc `alice`, profile 2 thuộc `bob`.

**Giới hạn rõ ràng:** ví dụ dùng mật khẩu `{noop}` và in-memory identities chỉ để học trên máy local. Không triển khai vào môi trường có thể truy cập công khai; production cần identity provider, password encoder, audit, DB, rate limiting và các chính sách khác.

### 8.1. Cấu trúc dự án

```text
profile-security-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/profile/
    │   │   ├── ProfileDemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── Profile.java
    │   │   ├── ProfileStore.java
    │   │   ├── ProfilePermission.java
    │   │   ├── ProfileService.java
    │   │   ├── ProfileForm.java
    │   │   ├── SafeText.java
    │   │   └── ProfileController.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/profile.html
    └── test/
        └── java/demo/profile/ProfileSecurityTest.java
```

### 8.2. pom.xml — Java 17 và Spring Boot 3.5.6

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>profile-security-demo</artifactId>
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
      <artifactId>spring-boot-starter-thymeleaf</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
      <scope>test</scope>
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
```

### 8.3. application.properties

```properties
# Lab only: không mở ra mạng.
server.address=127.0.0.1
server.port=8080

# Trong lab hiển thị template cập nhật ngay, hữu ích khi học.
spring.thymeleaf.cache=false
```

Không dùng credential demo hoặc cấu hình này như bộ bảo vệ môi trường production. Loopback giúp giảm phơi nhiễm mạng; các test an ninh vẫn là yêu cầu riêng.

### 8.4. ProfileDemoApplication.java

```java
package demo.profile;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class ProfileDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProfileDemoApplication.class, args);
    }
}
```

`@EnableMethodSecurity` kích hoạt xử lý `@PreAuthorize` trên Spring-managed services. Không dùng `@Validated` làm thay thế: validation và authorization là hai hệ thống khác.

### 8.5. SecurityConfig.java

```java
package demo.profile;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        // CSRF được bật theo mặc định; cố tình không tắt.
        return http.build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}demo-alice")
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password("{noop}demo-bob")
                .roles("USER")
                .build());
    }
}
```

Ở đây:

- Tất cả endpoint ngoài trang login/error yêu cầu đã đăng nhập.
- Login form do Spring Security cung cấp; session/cookie được quản lý bởi security framework.
- Quyền sửa **một profile cụ thể** không được xác định ở request path rule mà ở service method security.
- `{noop}` là password encoder không hash, **chỉ dùng cho demo loopback**; production dùng encoder thích hợp và hệ thống danh tính quản lý.
- CSRF không bị tắt. Một POST dùng session phải mang token hợp lệ, dù user đã đăng nhập.

### 8.6. Profile.java

```java
package demo.profile;

public record Profile(
        long id,
        String owner,
        String displayName) {
}
```

Record là value object immutable, không cho client bind/sửa một property `role`. Trong project thật có thể là JPA entity, nhưng HTTP input vẫn nên là DTO riêng.

### 8.7. ProfileStore.java

```java
package demo.profile;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
public class ProfileStore {

    private final ConcurrentMap<Long, Profile> data =
        new ConcurrentHashMap<>(Map.of(
            1L, new Profile(1L, "alice", "Alice"),
            2L, new Profile(2L, "bob", "Bob")
        ));

    public Optional<Profile> find(long id) {
        return Optional.ofNullable(data.get(id));
    }

    public Profile require(long id) {
        return find(id).orElseThrow(
            () -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Profile not found"));
    }

    public Profile rename(long id, String displayName) {
        Profile updated = data.computeIfPresent(
            id,
            (key, old) -> new Profile(
                old.id(), old.owner(), displayName));

        if (updated == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Profile not found");
        }
        return updated;
    }
}
```

`ConcurrentHashMap#computeIfPresent` thay giá trị một key theo thao tác atomic của map. Demo này không có persistence/tenant DB; trong production cần transactional store và giải quyết race conditions, ownership, locking khi phù hợp.

### 8.8. ProfilePermission.java — policy dựa trên owner thật

```java
package demo.profile;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("profilePermission")
public class ProfilePermission {

    private final ProfileStore store;

    public ProfilePermission(ProfileStore store) {
        this.store = store;
    }

    public boolean owns(long id, Authentication authentication) {
        if (authentication == null
                || !authentication.isAuthenticated()) {
            return false;
        }

        return store.find(id)
            .map(profile ->
                profile.owner().equals(authentication.getName()))
            .orElse(false);
    }
}
```

Policy lấy owner từ dữ liệu **server-side**, không đọc một `owner` field trong request. Với tài nguyên không tồn tại hoặc không thuộc caller, expression trả `false`. Như vậy app có thể từ chối mà không tiết lộ tài nguyên nào tồn tại; status 403/404 cụ thể tùy policy API.

### 8.9. ProfileService.java — authorization trước khi truy cập/sửa

```java
package demo.profile;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;

@Service
public class ProfileService {

    private final ProfileStore store;

    public ProfileService(ProfileStore store) {
        this.store = store;
    }

    @PreAuthorize("@profilePermission.owns(#id, authentication)")
    public Profile read(@P("id") long id) {
        return store.require(id);
    }

    @PreAuthorize("@profilePermission.owns(#id, authentication)")
    public Profile changeName(
            @P("id") long id,
            String displayName) {
        return store.rename(id, displayName);
    }
}
```

`@P("id")` làm tên parameter hiện rõ cho method-security expression `#id`. Đây là `org.springframework.security.core.parameters.P`, **không phải annotation query parameter của JDBC**.

Nhờ `@PreAuthorize`, lời gọi từ controller qua Spring-managed service proxy được kiểm tra **trước khi thân method chạy**. `@EnableMethodSecurity` trong app đã bật cơ chế này.

**Lưu ý AOP:** Gọi `this.changeName(...)` từ một method khác cùng class có thể bypass proxy-based method security. Hãy đặt policy trong tầng được thực thi chắc chắn, gọi qua bean proxy hoặc thêm kiểm tra domain-level; đừng coi annotation là bảo vệ tuyệt đối trong mọi dạng self-invocation.

### 8.10. ProfileForm.java — DTO và Jakarta Validation

```java
package demo.profile;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class ProfileForm {

    @NotBlank
    @Size(max = 80)
    private String displayName;

    public ProfileForm() {
    }

    public ProfileForm(String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

Không có `role`, `owner` hoặc `verified` trong DTO. Việc client tự gửi một trong những thuộc tính đó không có nghĩa nó có quyền làm thay đổi profile.

### 8.11. SafeText.java — normalization trước validation

```java
package demo.profile;

import java.text.Normalizer;

public final class SafeText {

    private SafeText() {
    }

    public static String normalizeDisplayName(String raw) {
        if (raw == null) {
            return null;
        }
        return Normalizer.normalize(
            raw.strip(), Normalizer.Form.NFC);
    }

    public static void main(String[] args) {
        String composed = "Café";
        String decomposed = "Cafe\u0301";

        System.out.println(
            "same-before=" + composed.equals(decomposed));

        System.out.println(
            "same-after=" + composed.equals(
                normalizeDisplayName("  " + decomposed + "  ")));
    }
}
```

Có thể chạy riêng class này sau khi compile để kiểm tra Unicode NFC:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java \
  -Dexec.mainClass=demo.profile.SafeText
```

Output chính xác từ hai lời gọi `System.out.println` (không tính log Maven):

```text
same-before=false
same-after=true
```

Đây chỉ là normalization, không phải validation, sanitization hay escaping.

### 8.12. ProfileController.java — ghép bốn lớp đúng nơi

```java
package demo.profile;

import java.beans.PropertyEditorSupport;

import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
@RequestMapping("/profiles")
public class ProfileController {

    private final ProfileService service;

    public ProfileController(ProfileService service) {
        this.service = service;
    }

    @InitBinder("form")
    void initFormBinder(WebDataBinder binder) {
        // Chỉ chấp nhận đúng một property từ request.
        binder.setAllowedFields("displayName");

        // PropertyEditor thuộc binder của request, không dùng state
        // mutable dùng chung giữa các request.
        binder.registerCustomEditor(
            String.class,
            "displayName",
            new PropertyEditorSupport() {
                @Override
                public void setAsText(String text) {
                    setValue(SafeText.normalizeDisplayName(text));
                }
            });
    }

    @GetMapping("/{id}")
    public String show(
            @PathVariable("id") long id,
            Model model) {

        Profile profile = service.read(id); // @PreAuthorize
        model.addAttribute("profile", profile);
        model.addAttribute(
            "form", new ProfileForm(profile.displayName()));

        return "profile";
    }

    @PostMapping("/{id}")
    public String update(
            @PathVariable("id") long id,
            @Valid @ModelAttribute("form") ProfileForm form,
            BindingResult errors,
            Model model,
            HttpServletResponse response,
            RedirectAttributes redirect) {

        // Không hiển thị dữ liệu profile nếu caller chưa được phép.
        Profile profile = service.read(id); // @PreAuthorize

        if (errors.getSuppressedFields().length > 0) {
            errors.reject(
                "extraFields", "Biểu mẫu chứa trường không được phép");
            response.setStatus(
                HttpServletResponse.SC_BAD_REQUEST);
        }

        if (errors.hasErrors()) {
            model.addAttribute("profile", profile);
            return "profile";
        }

        // @PreAuthorize một lần nữa tại method ghi dữ liệu.
        service.changeName(id, form.getDisplayName());
        redirect.addFlashAttribute("saved", true);
        return "redirect:/profiles/" + id;
    }
}
```

Tách rõ trách nhiệm:

1. `@InitBinder("form")` cấu hình **normalization và allowlist** cho đúng form; Java property editor được gắn trước bước validation trên form.
2. `@Valid` xác nhận tên sau normalization không blank và độ dài không vượt 80.
3. `BindingResult errors` đứng **ngay sau** `ProfileForm form`; controller không lưu khi có lỗi.
4. `service.read(id)` và `service.changeName(id,...)` đều có **authorization theo resource ID thực**. Không dùng ID gửi trong form như bằng chứng ownership.
5. Nếu request thêm `role=ADMIN`, binder suppress field; controller chủ động trả status 400. Validation thông thường không tự trả 400 khi có `BindingResult` liền kề; vì vậy code phải chọn response phù hợp.
6. **Escaping không nằm trong controller và không diễn ra lúc lưu**. Nó diễn ra khi Thymeleaf render output ở template.

Một request có `displayName="   "` được chuẩn hóa thành chuỗi rỗng trước `@NotBlank`. Kẻ gửi request thêm field ngoài allowlist sẽ nhận 400 thay vì tạo side effect. Trong ví dụ, lỗi validation bình thường được render lại cùng view (thường là HTTP 200 theo kiểu server-rendered form); nếu API yêu cầu 422/400 cho validation thì thay đổi HTTP contract có chủ đích.

### 8.13. templates/profile.html — escaping tại output sink

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Profile</title>
</head>
<body>
    <h1>Chỉnh sửa hồ sơ</h1>

    <p>Chủ sở hữu:
        <span th:text="${profile.owner}">owner</span>
    </p>

    <p>Tên hiện tại:
        <span id="currentName"
              th:text="${profile.displayName}">name</span>
    </p>

    <p th:if="${saved}">Đã lưu.</p>

    <form method="post"
          th:action="@{/profiles/{id}(id=${profile.id})}"
          th:object="${form}">

        <label for="displayName">Tên hiển thị</label>
        <input id="displayName" type="text"
               th:field="*{displayName}" maxlength="80"/>

        <p th:if="${#fields.hasErrors('displayName')}"
           th:errors="*{displayName}">Invalid name</p>

        <p th:if="${#fields.hasGlobalErrors()}">
            Biểu mẫu chứa thuộc tính không được phép.
        </p>

        <button type="submit">Lưu</button>
    </form>
</body>
</html>
```

Khi `profile.displayName` chứa chuỗi giống HTML, `th:text` xuất nó thành văn bản **được HTML-escaped**. Nó không tạo thẻ `img` và không kích hoạt `onerror`. Đây mới là chỗ output encoding nên được thực hiện.

`th:field` hỗ trợ render input value theo ngữ cảnh attribute. `th:action` dùng URL expression của Thymeleaf; với Spring Security CSRF mặc định, sự tích hợp của Spring/Thymeleaf qua `RequestDataValueProcessor` hỗ trợ đưa CSRF hidden input vào HTML form POST. Hãy xác nhận token thực tế xuất hiện trong HTML đã render và được gửi lại khi submit.

**Không thay `th:text` bằng `th:utext` cho dữ liệu người dùng.** Đừng xây một string HTML trong controller rồi đưa vào view như “đã được sanitize” nếu chưa có hợp đồng rich HTML rõ ràng.

## 9. Chạy dự án và quan sát kết quả

Ở thư mục chứa `pom.xml`:

```bash
mvn -q spring-boot:run
```

Truy cập trình duyệt trên **cùng máy**:

```text
http://127.0.0.1:8080/profiles/1
```

App chuyển tới login form nếu chưa đăng nhập. Dùng user demo:

```text
username: alice
password: demo-alice
```

Sau khi đăng nhập, trang profile của Alice hiện ra. Thử:

1. Nhập tên `"  Café  "` (hoặc một ký tự `é` dạng decomposed) và bấm Lưu. Normalizer bỏ khoảng trắng hai đầu và dùng NFC; kết quả được hiển thị thống nhất.
2. Nhập một chuỗi toàn khoảng trắng. `@NotBlank` phát hiện lỗi sau normalization; không ghi dữ liệu.
3. Nhập một chuỗi dài hơn 80 UTF-16 code units sau normalization. `@Size(max=80)` phát hiện lỗi. Trình duyệt có thể giới hạn input do `maxlength=80`, nhưng backend vẫn phải tự kiểm tra khi request bị chỉnh.
4. Nhập text `<img src=x onerror=alert(1)>`. Nếu còn trong giới hạn độ dài, ứng dụng có thể lưu nguyên ký tự có ý nghĩa HTML như **dữ liệu văn bản**, nhưng view `th:text` hiển thị chúng như text, không tạo image element.
5. Đăng xuất, đăng nhập `bob / demo-bob` và mở `/profiles/1`. Method security từ chối vì Bob không phải owner của profile 1. Bob chỉ được xem/sửa `/profiles/2`.

Không dùng HTML injection trong bối cảnh ngoài ứng dụng lab; ở đây mục đích chỉ để xác minh output encoding của template.

### 9.1. CSRF token và curl

Với form login + session và CSRF bật, một lệnh `curl -X POST` trực tiếp **không có CSRF token hợp lệ** thường nhận HTTP 403 trước khi vào controller. Đây là hành vi đúng, không phải lỗi của Bean Validation hay ownership check.

Để kiểm thử endpoint qua HTTP tự động, nên dùng `MockMvc` với security test support `with(csrf())`, hoặc điều khiển browser đã đăng nhập để gửi form có hidden token. **Không tắt CSRF chỉ để ví dụ curl dễ chạy** khi authentication dựa trên session/cookie.

### 9.2. Phân biệt từng thất bại qua HTTP

| Thử nghiệm | Lớp quyết định | Kết quả đáng mong đợi |
| --- | --- | --- |
| Anonymous mở `/profiles/1` | Authentication/request security | Redirect tới trang login |
| Bob mở profile của Alice | Authorization ở service | 403 hoặc chính sách conceal phù hợp |
| Alice POST không CSRF | CSRF filter | 403 |
| Alice gửi `displayName="   "` | Normalization + validation | View form có lỗi, không update |
| Alice gửi `role=ADMIN` ngoài form | Binder allowlist + kiểm tra suppressed fields | 400, không update |
| Alice gửi HTML-like text hợp lệ | Validation + output escaping | Lưu text theo contract, hiển thị inert |
| Alice gửi script qua JavaScript sink không escape | Context-specific output handling (nếu code tạo sink sai) | Có nguy cơ XSS; không có sink ấy trong mẫu |
| Alice thay ID trong URL sang 2 | Authorization theo owner | Không sửa được Bob |
| Code ghép input vào SQL | Query building | Cần prepared statements, không nhờ HTML escaping |

## 10. Kiểm thử tự động với MockMvc và Spring Security Test

Ví dụ file `src/test/java/demo/profile/ProfileSecurityTest.java` dưới đây kiểm thử bốn lớp bằng request thật qua Spring MVC/Security filters.

```java
package demo.profile;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode =
    DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ProfileSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "alice")
    void normalizationAndEscaping() throws Exception {
        mvc.perform(post("/profiles/1")
                .with(csrf())
                .param("displayName",
                    "  <img src=x onerror=alert(1)>  "))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/profiles/1"));

        mvc.perform(get("/profiles/1"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("&lt;img")))
            .andExpect(content().string(not(
                containsString("<img src=x onerror=alert(1)>"))));
    }

    @Test
    @WithMockUser(username = "alice")
    void disallowedFieldsRejected() throws Exception {
        mvc.perform(post("/profiles/1")
                .with(csrf())
                .param("displayName", "New name")
                .param("role", "ADMIN"))
            .andExpect(status().isBadRequest());

        // Request bị từ chối: tên vẫn là Alice.
        mvc.perform(get("/profiles/1"))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("Alice")));
    }

    @Test
    @WithMockUser(username = "bob")
    void cannotEditOtherUsersProfile() throws Exception {
        mvc.perform(post("/profiles/1")
                .with(csrf())
                .param("displayName", "Stolen"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void missingCsrfIsForbidden() throws Exception {
        mvc.perform(post("/profiles/1")
                .param("displayName", "New name"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void blankAfterNormalizationDoesNotUpdate() throws Exception {
        mvc.perform(post("/profiles/1")
                .with(csrf())
                .param("displayName", "   "))
            .andExpect(status().isOk());

        mvc.perform(get("/profiles/1"))
            .andExpect(content().string(containsString("Alice")));
    }
}
```

**Chú ý khi copy import:** Java không cho xuống dòng tùy ý trong một `import static` theo các vị trí trình bày kỳ lạ; các dòng `import static org.springframework...` trong khối này được ngắt thành hai dòng tại dấu phân cách whitespace sau tên package khi trình bày. Dù Java cho whitespace/newline giữa các tokens, cách chắc chắn nhất trong IDE là để **mỗi import trên một dòng**. Để tránh phụ thuộc cách paste, có thể thay toàn bộ nhóm import static bằng import chuẩn một dòng, được liệt kê theo tên class ngay bên dưới:

```java
// Danh sách để IDE auto-import, không phải file Java độc lập:
// org.hamcrest.Matchers.containsString
// org.hamcrest.Matchers.not
// SecurityMockMvcRequestPostProcessors.csrf
// MockMvcRequestBuilders.get
// MockMvcRequestBuilders.post
// MockMvcResultMatchers.content
// MockMvcResultMatchers.redirectedUrl
// MockMvcResultMatchers.status
```

Chạy:

```bash
mvn -q test
```

Khi tests pass, Maven thường không in ứng dụng stdout riêng vì các assertions không gọi `System.out.println`. Không mô tả một chuỗi “5 tests PASS” như stdout cố định của Maven; kiểm tra exit code 0 và test report để xác nhận.

**Mức độ chứng minh:**

- Test normalization + XSS chỉ xác nhận dữ liệu bị HTML-escaped khi render; không dùng test này làm chứng cứ cho mọi JavaScript/CSS/URL sink khác.
- Test rejected fields xác nhận binder allowlist chạy và không lưu profile.
- Test Bob xác nhận owner authorization ở service.
- Test CSRF xác nhận filter bảo vệ form POST.
- Test blank xác nhận normalization diễn ra trước validation.
- `@DirtiesContext` giúp mỗi test có in-memory data riêng, tránh phụ thuộc thứ tự chạy.

Trong dự án thật nên có thêm tests cho context-specific DOM sinks, concurrency, IDOR/BOLA, và tất cả đường update service/async khác.

## 11. Lỗi phổ biến khi kết hợp các lớp

### 11.1. “Đã validate nên không cần escape”

Sai. Một value hợp lệ có thể chứa dấu `<`, `"` hoặc `'`. Validation giải quyết business contract; output encoder giải quyết cú pháp của parser HTML/JS/URL. Ngay cả dữ liệu đã lấy từ database cũng cần coi là không tin cậy trước khi hiển thị vì có thể đã được lưu qua endpoint khác (stored XSS).

### 11.2. “Đã escape nên không cần validate”

Sai. Một email đã HTML-escaped vẫn có thể không đúng email; một số lượng âm được escape vẫn là sai business invariant. Không dùng encoding thay cho range checks, enum allowlists, payload size limits và cross-field constraints.

### 11.3. “Chỉ cần normalize và lọc chữ script”

Sai. XSS có nhiều context và biểu thức hơn `<script>`. Một regex blacklist bỏ chữ “script” không xử lý event handlers, URL schemes, SVG, CSS hoặc DOM sink. Normalization còn có thể tạo các chuỗi tương đương mới; phải thiết kế validation và output encoding đúng nơi.

### 11.4. “Người dùng đã login nên được sửa resource”

Sai. Authentication xác định identity, còn authorization cần kiểm tra **ownership/tenant/action**. Đổi URL từ `/profiles/1` sang `/profiles/2` không được tạo quyền cập nhật người khác.

### 11.5. “Ẩn role field trong form là an toàn”

Sai. Client có thể tự thêm `role=ADMIN`. Dùng DTO/allowlist/explicit mapping và authorization, không bind entity có property nhạy cảm từ request. Cẩn thận với `@RequestBody` JSON: Jackson deserialization có cơ chế khác `@ModelAttribute`, `setAllowedFields` của form binder không đủ bảo vệ mọi JSON property.

### 11.6. “Sanitize HTML một lần rồi dùng mọi nơi”

Sai. Nếu ứng dụng cho phép rich HTML, sanitizer phải xử lý đúng HTML policy và output sink vẫn phải được thiết kế an toàn. Một HTML snippet có thể không hợp lệ để đưa vào attribute, inline JS hay URL. Không có một “safe string” phổ quát.

### 11.7. “@PreAuthorize là đủ ngay cả khi gọi nội bộ trong cùng class”

Sai với proxy-based method security thông thường: self-invocation có thể bypass proxy. Hãy đặt policy ở service boundary thực sự được gọi qua Spring bean, thêm authorization ở domain/data access hoặc dùng cơ chế phù hợp cho kiến trúc.

### 11.8. “Dùng th:utext để hỗ trợ tên có dấu”

Sai. Unicode tiếng Việt hiển thị bình thường qua `th:text` khi encoding charset đúng. `th:utext` bật unescaped HTML, không phải tính năng hỗ trợ Unicode.

### 11.9. “Tắt CSRF là một tối ưu performance”

Không mặc định đúng. Với browser/session cookie, CSRF là lớp chống request giả mạo và độc lập với validation/authorization. Chỉ cân nhắc thay đổi CSRF strategy nếu authentication model và threat model chứng minh hợp lý; không tắt chỉ để POST test chạy dễ hơn.

### 11.10. “Escaping HTML có thể dùng cho SQL”

Sai. SQL có parser và escaping conventions riêng; dùng parameter binding/prepared statements. Còn URL path traversal cần path/URI rules, command injection cần tránh shell, JSON cần serializer đúng chuẩn.

## 12. Checklist code review và bài tập

Khi review một Spring MVC endpoint nhận dữ liệu:

1. Xác định rõ **nguồn dữ liệu không tin cậy**: body, query, path, headers, database, message queue, third-party API.
2. Dữ liệu có cần **normalization** không? Quy tắc đó có biến đổi ý nghĩa password/token/mã định danh không?
3. Normalization diễn ra **trước validation và comparison** trên đúng đường nhận request chưa?
4. Dữ liệu có DTO riêng và **chỉ những field cần thiết** không?
5. Có `@Valid`/`@Validated` hoặc validation chủ động phù hợp? Có xử lý `BindingResult` khi có lỗi không?
6. Giá trị được lưu/cập nhật bởi principal nào? **Quyền owner/tenant/action** kiểm tra ở đâu?
7. Với writes, policy được kiểm tra trước side effects chưa? Có đường service call nào bỏ qua proxy không?
8. Request-level rules có **deny-by-default** không?
9. Browser form/cookie có CSRF protection không? Token được đưa vào POST thế nào?
10. Dữ liệu ra HTML, attribute, JS, CSS, URL, JSON, SQL hoặc log qua sink nào?
11. Output encoding/serializer có **đúng ngữ cảnh** không? Có `th:utext` hoặc `innerHTML` đưa raw text không?
12. Nếu cho rich HTML, sanitizer dùng allowlist và có test HTML malformed chưa?
13. Nếu build SQL, đã dùng prepared statements thay vì nối input chưa?
14. Có regression tests với input Unicode decomposed, blank, quá dài, dữ liệu giống HTML, field `role` thừa, ID resource của người khác không?
15. Logs/error responses có lộ token, password, rejected values, stack trace không?

### Bài tập A — phân loại lớp phòng vệ

Cho các tình huống:

| Yêu cầu | Lớp chính |
| --- | --- |
| Loại bỏ khoảng trắng hai đầu tên hiển thị theo policy | Normalization |
| Từ chối tên rỗng sau trim | Validation |
| Từ chối role lạ ngoài enum/domain contract | Validation |
| Không cho user thường thay role dù role `ADMIN` là giá trị hợp lệ | Authorization + DTO/allowlist |
| Hiển thị chuỗi chứa `<img>` dưới dạng text trong HTML | Output encoding |
| Từ chối Bob cập nhật profile ID của Alice | Authorization |
| Trả JSON có dấu nháy kép trong tên | JSON serialization |
| Chạy SELECT bằng username | SQL parameter binding |
| Form POST không có CSRF token hợp lệ | CSRF protection |
| Cần giữ rich HTML hợp lệ nhưng loại event handlers | HTML sanitization chuyên dụng |

### Bài tập B — tìm lỗi trong code

Đoạn sau cố tình không an toàn:

```java
@PostMapping("/accounts/{id}")
public String update(@PathVariable long id,
                     @Valid @ModelAttribute Account entity,
                     Model model) {

    repository.save(entity);
    model.addAttribute("html",
        "<div>" + entity.getDisplayName() + "</div>");
    return "account";
}
```

Vấn đề:

- Dùng entity làm input object có thể mở mass assignment.
- Không xác minh user có quyền cập nhật account ID đó.
- `@Valid` không chặn việc cập nhật role nhạy cảm nếu constraints cho phép.
- Ghép raw displayName vào HTML nếu view xuất bằng unescaped mechanism có thể tạo XSS.
- Không phân biệt source ID từ URL với data object đã bind (có thể không đồng nhất).
- Không có xử lý rõ ràng lỗi validation/binding và authorization.

Hướng sửa: DTO chuyên biệt, normalization trước validation theo policy, service kiểm tra owner/tenant và chỉ map allowed fields, chuẩn hóa phản hồi lỗi, render field bằng escaped text, test request cố tình gửi thêm thuộc tính nhạy cảm.

## 13. Tổng kết

**Normalization** đảm bảo đầu vào có dạng biểu diễn nhất quán theo domain. **Validation** xác nhận dữ liệu có đúng cấu trúc và quy tắc hay không. **Escaping/output encoding** giữ dữ liệu thành dữ liệu tại **ngữ cảnh đầu ra cụ thể** thay vì biến thành HTML/JavaScript/SQL syntax (SQL cần parameterization). **Authorization** kiểm tra người gọi có quyền trên **hành động và tài nguyên** thực tế hay không; nó dựa trên authentication nhưng không đồng nghĩa với authentication.

Trong Spring MVC, có thể dùng `WebDataBinder`/converter để chuẩn hóa field trước `@Valid`; dùng input DTO và `BindingResult` để xử lý validation; dùng Thymeleaf `th:text` hoặc serializer đúng sink khi xuất dữ liệu; dùng Spring Security `SecurityFilterChain` và `@PreAuthorize` cùng domain policy để bảo vệ resource. **Chỉ khi các lớp được kết hợp đúng vị trí** ứng dụng mới có thể chống cả dữ liệu sai, injection và truy cập trái phép mà vẫn giữ những dữ liệu hợp lệ như tên Unicode có dấu.

## Tài liệu tham khảo

- OWASP — Input Validation Cheat Sheet (normalization/canonicalization, schema validation): https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html
- OWASP — Cross Site Scripting Prevention Cheat Sheet (context-sensitive output encoding): https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
- OWASP — Authorization Cheat Sheet (deny-by-default, least privilege, every request): https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP — Mass Assignment Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html
- OWASP — SQL Injection Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html
- Spring Framework 6.2 — `@InitBinder` and data binding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework 6.2 — `@ModelAttribute` arguments and security: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 — Bean Validation integration: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Security — Method Security and `@PreAuthorize`: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Spring MVC integration and defense-in-depth: https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html
- Spring Security — CSRF protection for forms: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Thymeleaf 3.1 — `th:text` escaping vs `th:utext`: https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html
- Unicode Standard Annex #15 — Unicode normalization forms: https://www.unicode.org/reports/tr15/