# Phương thức an toàn chỉ dùng cho hành động đọc

## Mục tiêu học tập

Sau bài học thuộc chương **Cơ chế CSRF**, người học có thể:

- Phân biệt **phương thức HTTP an toàn** (*safe method*) với phương thức **không an toàn** (*unsafe method*) và với tính chất **idempotent**.
- Giải thích vì sao các phương thức `GET`, `HEAD`, `OPTIONS` và `TRACE` được coi là an toàn theo ngữ nghĩa HTTP, đồng thời biết giới hạn bảo mật riêng của `TRACE`.
- Chỉ ra nguyên tắc **GET và HEAD không được thực hiện hành động làm thay đổi trạng thái nghiệp vụ theo ý định của client**, kể cả khi endpoint có tên như “logout”, “delete” hoặc “confirm”.
- Phân tích hệ quả khi dùng GET để đổi trạng thái: browser có thể tải liên kết, hình ảnh, tài nguyên nhúng, crawler hoặc cơ chế prefetch mà **không có CSRF token**.
- Hiểu nguyên tắc mặc định của Spring Security: `CsrfFilter` trên **Servlet** và `CsrfWebFilter` trên **Reactive/WebFlux** thường không yêu cầu CSRF token với các phương thức an toàn, còn `POST`, `PUT`, `PATCH`, `DELETE` thường cần token.
- Thiết kế endpoint Spring MVC/WebFlux cho thao tác **đọc** và **ghi** theo đúng phương thức, dùng form POST có token khi cần thay đổi dữ liệu.
- Viết kiểm thử để xác nhận GET không gây thay đổi nghiệp vụ và request ghi thiếu/sai CSRF token bị từ chối; phân biệt lỗi CSRF, xác thực, CORS và phân quyền.

## 1. Vì sao cơ chế CSRF dựa vào ngữ nghĩa HTTP?

Giả sử một ứng dụng cho phép xóa phương thức xác thực đa yếu tố bằng URL:

~~~http
GET /security/disable-mfa HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_OF_ALICE
~~~

Nếu một request GET **thực hiện ngay việc tắt MFA**, ứng dụng có rủi ro nghiêm trọng. Người dùng không nhất thiết đã chủ động bấm nút “Tắt MFA” trong giao diện hợp lệ; trình duyệt có thể truy cập URL do liên kết từ một website khác, một công cụ tự động tải trước hoặc một phần mềm quét liên kết. Tùy chính sách cookie, request có thể mang phiên đăng nhập.

Trong khi đó, Spring Security **mặc định không đòi CSRF token trên GET** vì ngữ nghĩa chuẩn của GET là **truy xuất biểu diễn tài nguyên**, không phải yêu cầu thay đổi trạng thái.

Điều này tạo ra một **hợp đồng quan trọng** giữa thiết kế HTTP và lớp bảo vệ CSRF:

> **Phương thức an toàn được dành cho yêu cầu đọc/quan sát tài nguyên. Nếu ứng dụng muốn client thực hiện một thay đổi nghiệp vụ, nó phải sử dụng phương thức không an toàn phù hợp và áp dụng các kiểm tra bảo mật cần thiết, trong đó có CSRF khi có credential trình duyệt tự gửi.**

Lỗi nằm ở **endpoint sử dụng sai HTTP method**, không phải ở việc Spring Security “quên” kiểm tra CSRF trên GET.

Bài học thuộc module **SPRING_SECURITY_HTTP_PROTECTION**, nơi các lớp bảo vệ HTTP và trình duyệt như CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và quản lý session được kết hợp để bảo vệ cả ứng dụng **Servlet** lẫn **Reactive**.

## 2. “An toàn” có nghĩa là gì?

Theo ngữ nghĩa HTTP, một request method là **safe** nếu client **không yêu cầu và không kỳ vọng** một thay đổi trạng thái trên máy chủ như kết quả có chủ đích của request đó. Điều này đôi khi được diễn đạt đơn giản là **“chỉ dùng cho hành động đọc”**.

Tuy nhiên cần hiểu chính xác:

- **GET đọc dữ liệu** có thể phát sinh **log truy cập, metric, truy vết, tăng bộ đếm thống kê kỹ thuật hoặc tính toán cache** như một hệ quả phụ do server quản lý. Những tác động phụ ngẫu nhiên/không do client yêu cầu **không tự làm thay đổi định nghĩa safe**.
- Nhưng **GET /transfer?amount=1000**, **GET /delete?id=5**, **GET /approve?order=123**, **GET /logout** mà thực sự thay đổi trạng thái người dùng là **vi phạm hợp đồng safe** nếu các endpoint đó thực hiện hành động ngay.
- Tên endpoint hoặc đường dẫn không quyết định tính an toàn: **hành vi thực tế của code** mới là yếu tố cần kiểm tra.
- “Safe” là khái niệm về **ngữ nghĩa request**, **không đồng nghĩa** endpoint tự động an toàn trước mọi tấn công. Một GET đọc dữ liệu riêng tư vẫn cần xác thực/phân quyền và phòng vệ chống rò rỉ dữ liệu.

### 2.1. Bốn phương thức được coi là an toàn

| Phương thức | Mục đích chuẩn | Hành vi ứng dụng nên thực hiện | Ghi chú bảo mật |
|---|---|---|---|
| **`GET`** | Yêu cầu biểu diễn của tài nguyên | Đọc trang, lấy danh sách hoặc xem chi tiết | Không thực hiện xóa, mua hàng, đổi quyền, logout hay hành động ghi |
| **`HEAD`** | Như GET nhưng không gửi response body | Kiểm tra metadata, tồn tại tài nguyên, ETag hoặc lần sửa đổi | Handler dùng chung logic với GET cũng phải **không gây thay đổi nghiệp vụ** |
| **`OPTIONS`** | Hỏi về tùy chọn giao tiếp của tài nguyên/server | Trả các phương thức/khả năng, hỗ trợ CORS preflight | Preflight **không được thực hiện hành động nghiệp vụ** |
| **`TRACE`** | Chẩn đoán vòng lặp request | Nếu hỗ trợ, phản chiếu thông điệp request theo ngữ nghĩa chuẩn | Thường nên **vô hiệu hóa trong production** để giảm nguy cơ phản chiếu thông tin nhạy cảm; được liệt kê là safe **không có nghĩa nên bật** |

`TRACE` xuất hiện trong danh sách phương thức safe và danh sách Spring Security mặc định bỏ qua CSRF, nhưng nó có những rủi ro riêng. Không bật TRACE chỉ vì nó được gọi là an toàn; kiểm soát tại web server, proxy, firewall hoặc cấu hình container phù hợp.

### 2.2. Những phương thức thường thay đổi trạng thái

| Phương thức | Ngữ nghĩa thường gặp | Safe? | Idempotent theo ngữ nghĩa HTTP? | CSRF với cấu hình mặc định? |
|---|---|---|---|---|
| `GET` | Đọc tài nguyên | **Có** | Có | Thường không yêu cầu token |
| `HEAD` | Đọc metadata/headers | **Có** | Có | Thường không yêu cầu token |
| `OPTIONS` | Kiểm tra khả năng giao tiếp | **Có** | Có | Thường không yêu cầu token |
| `TRACE` | Chẩn đoán request | **Có** | Có | Thường không yêu cầu token |
| `POST` | Yêu cầu xử lý có thể tạo/thay đổi trạng thái | Không | Không bảo đảm | **Thường yêu cầu token** |
| `PUT` | Tạo hoặc thay thế trạng thái tài nguyên đích | Không | **Có** | **Thường yêu cầu token** |
| `PATCH` | Sửa một phần tài nguyên | Không | Không bảo đảm | **Thường yêu cầu token** |
| `DELETE` | Xóa liên kết/tài nguyên đích | Không | **Có** | **Thường yêu cầu token** |

Bảng mô tả **ngữ nghĩa chuẩn** và hành vi CSRF mặc định thường gặp; ứng dụng có thể tùy chỉnh matcher hoặc có thêm phương thức mở rộng.

**Điểm dễ nhầm:** **Idempotent khác Safe**.

- **Idempotent:** Gửi cùng một request một lần hay nhiều lần có cùng **tác động dự kiến lên trạng thái server**. Ví dụ `DELETE /cart/items/7` có thể xóa một mục ở lần đầu, các lần sau không làm nó bị xóa thêm lần nữa.
- **Safe:** Client không yêu cầu thay đổi trạng thái có chủ đích. `DELETE` có thể idempotent nhưng **không safe** vì nó yêu cầu xóa dữ liệu.
- Vì vậy **không được bỏ CSRF cho PUT/DELETE chỉ vì chúng idempotent**.

Một request `GET` có thể trả về dữ liệu khác nhau giữa hai lần gọi do dữ liệu bên ngoài thay đổi; điều đó không tự làm nó thành phương thức không an toàn.

## 3. Vì sao GET đặc biệt nguy hiểm nếu bị dùng để thay đổi dữ liệu?

### 3.1. Browser và các hệ thống thường truy cập GET mà không có hành động xác nhận

GET có thể được phát sinh từ nhiều nguồn:

- Người dùng mở liên kết bằng một cú nhấp hoặc dán URL vào thanh địa chỉ.
- Website ngoài tạo link, iframe, ảnh hoặc tài nguyên nhúng trỏ tới ứng dụng đích.
- Browser, proxy, extension hoặc client được cấu hình **prefetch/prerender**.
- Công cụ tìm kiếm/crawler, bot kiểm tra liên kết và phần mềm xem trước đường dẫn.
- Các hệ thống cache hoặc cơ chế tự động theo dõi tài nguyên.

Những thành phần này có thể phát request GET vì chúng **giả định GET chỉ đọc**. Chúng không có trách nhiệm hiểu việc một backend vô tình dùng GET để xóa dữ liệu hoặc sửa quyền truy cập.

Một ví dụ thiết kế sai:

~~~html
<a href="/cart/checkout?confirm=true">Thanh toán ngay</a>
~~~

Nếu `GET /cart/checkout?confirm=true` thực sự trừ tiền/đặt hàng, một tác nhân tải trước link có thể gây hậu quả không mong đợi. Đổi tên URL thành `/confirmCheckout` không sửa được vấn đề; cần chuyển **hành động có tác động** sang phương thức và quy trình bảo mật phù hợp.

### 3.2. Cookie SameSite=Lax không đảm bảo chặn GET cross-site

Một số trình duyệt có thể gửi cookie `SameSite=Lax` trong **điều hướng cấp cao cross-site dùng phương thức an toàn**, ví dụ mở một link GET dẫn đến ứng dụng đích.

~~~html
<!-- Minh họa URL có tác động sai thiết kế -->
<a href="https://app.example.com/security/disable-mfa">
  Xem chính sách bảo mật
</a>
~~~

Nếu ứng dụng xử lý GET này bằng cách tắt MFA và browser gửi cookie phiên, một điều hướng vốn được coi là “chỉ đọc” có thể trở thành CSRF.

Đường tấn công cụ thể còn phụ thuộc cookie `Domain`/`Path`/`Secure`/`SameSite`, browser, việc URL có được theo hay không, và điều kiện xác thực khác. Không nên khẳng định cookie luôn được gửi với mọi GET cross-site. Điều chắc chắn là **SameSite không thể sửa một endpoint GET được thiết kế sai ngữ nghĩa**.

### 3.3. CORS không phải tường bảo vệ cho GET có tác động

CORS chủ yếu kiểm soát việc JavaScript ở origin khác có thể truy cập phản hồi và một số request cần preflight. Một điều hướng GET hoặc yêu cầu tải ảnh liên trang có thể được browser gửi **mà JavaScript ở site nguồn không được đọc response**.

Nếu server thực hiện hành động **ngay khi nhận GET**, việc trang ngoài không đọc được response không ngăn tác động đó.

Kết luận: **đừng dùng CORS hoặc việc response không đọc được để biện minh cho endpoint GET thay đổi trạng thái**.

### 3.4. Sơ đồ hậu quả

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant X as Website khác / cơ chế tải liên kết
    participant B as Trình duyệt
    participant S as Ứng dụng Spring

    U->>B: Đang có phiên đăng nhập
    X-->>B: Liên kết GET tới endpoint nhạy cảm
    B->>S: GET /security/disable-mfa + cookie nếu được phép gửi
    S->>S: Endpoint được triển khai sai: đổi trạng thái
    S-->>B: Phản hồi HTTP
    Note over S: Mặc định CSRF không kiểm tra GET
    Note over U,S: Kết quả có thể xảy ra mà không có POST + CSRF token
~~~

Sơ đồ mô tả **lỗi ở thiết kế endpoint**; không có nghĩa Spring Security mặc định cung cấp endpoint `/security/disable-mfa`.

## 4. Cách thiết kế đúng: GET đọc, POST/PUT/PATCH/DELETE ghi

Giả sử người dùng muốn thay đổi chế độ hiển thị tài khoản từ `light` sang `dark`.

**Thiết kế sai:**

~~~http
GET /settings/theme?value=dark HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A
~~~

Nếu request này **thay đổi cài đặt ngay lập tức**, nó không còn là một GET an toàn. Query string chỉ là cách đưa dữ liệu vào URL, **không biến hành động ghi thành hành động đọc**.

**Thiết kế phù hợp:**

~~~http
GET /settings/theme HTTP/1.1
Host: app.example.com
~~~

Trả form hoặc thông tin theme hiện tại.

~~~http
POST /settings/theme HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A
Content-Type: application/x-www-form-urlencoded

theme=dark&_csrf=VALID_CSRF_TOKEN
~~~

Server kiểm tra quyền và token rồi mới lưu giá trị.

Với API:

~~~http
GET /api/preferences HTTP/1.1
Host: app.example.com
~~~

Trả tài nguyên hiện tại mà không sửa dữ liệu.

~~~http
PUT /api/preferences HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A
Content-Type: application/json
X-CSRF-TOKEN: VALID_CSRF_TOKEN

{"theme":"dark"}
~~~

`PUT` là phương thức không an toàn, dù thường idempotent, nên vẫn thuộc phạm vi kiểm tra CSRF mặc định. Client cũng phải gửi credential xác thực và được phân quyền thích hợp.

### 4.1. Nếu GET chỉ hiển thị trang xác nhận thì sao?

Một GET có thể **hiển thị form để người dùng xác nhận hành động**, miễn nó chưa thực hiện hành động. Ví dụ:

- `GET /account/delete/confirm`: chỉ hiển thị thông tin hậu quả và nút xác nhận.
- `POST /account/delete`: nhận request xác nhận, kiểm tra CSRF và xác thực bổ sung nếu nghiệp vụ yêu cầu, rồi mới xóa dữ liệu.
- `GET /logout` trong những cấu hình Spring Security mặc định: có thể cung cấp **trang xác nhận**.
- `POST /logout`: thực hiện logout khi request hợp lệ.

Việc hiển thị form xác nhận qua GET không tự làm thay đổi trạng thái. Nhưng nếu handler GET “vừa hiển thị form vừa xóa trước một phần dữ liệu”, nó vẫn không phù hợp với safe semantics.

### 4.2. Nếu hành động rất nhỏ thì có thể dùng GET không?

Không. Đổi trạng thái “đã đọc”, bật/tắt feature, bấm like, xóa một dòng, áp mã khuyến mại, xác nhận email hay thay quyền đều là **hành động nghiệp vụ có tác động** nếu client chủ ý yêu cầu nó.

Ngoại lệ cần phân tích riêng là các tác động kỹ thuật thụ động như logging, tính cache hoặc metric mà server tự thực hiện khi đọc. **Chúng không tạo ra một ngoại lệ cho phép dùng GET làm thao tác nghiệp vụ cập nhật dữ liệu.**

### 4.3. Link kích hoạt POST bằng JavaScript có đủ không?

Một cách làm có thể là nút `button` gọi `fetch("/account/delete", {method:"POST",...})` với token CSRF đúng. Nhưng **không nên phụ thuộc hoàn toàn vào JavaScript** nếu form POST HTML thuần có thể đáp ứng yêu cầu.

Ví dụ nút logout an toàn và hoạt động không cần JavaScript:

~~~html
<form method="post" action="/logout">
  <input type="hidden" name="_csrf" value="TOKEN_DO_SERVER_CAP">
  <button type="submit">Đăng xuất</button>
</form>
~~~

Trong hệ thống thật, giá trị `TOKEN_DO_SERVER_CAP` phải được render bằng CSRF token của request/phiên, không dùng chuỗi cố định trong code.

## 5. Spring Security mặc định áp dụng CSRF theo HTTP method ra sao?

### 5.1. Mặc định trên Servlet

Với Spring Security Servlet, `CsrfFilter` sử dụng cơ chế matcher để xác định request nào phải có CSRF token. Quy tắc mặc định thường **không yêu cầu token cho**:

- `GET`;
- `HEAD`;
- `TRACE`;
- `OPTIONS`.

Các phương thức khác, điển hình `POST`, `PUT`, `PATCH`, `DELETE`, thường **cần CSRF token**. Với endpoint dùng cookie hoặc cơ chế xác thực do browser tự gửi, đó là một giả định cần giữ.

~~~mermaid
flowchart TD
    A[Request HTTP] --> B{Phương thức an toàn theo matcher mặc định?}
    B -- GET/HEAD/OPTIONS/TRACE --> C[Không yêu cầu CSRF token]
    B -- POST/PUT/PATCH/DELETE --> D[Yêu cầu CSRF token theo cấu hình]
    C --> E[Tiếp tục các bước bảo mật khác]
    D --> F{Token hợp lệ?}
    F -- Không --> G[Từ chối, thường 403]
    F -- Có --> E
    E --> H[Authentication, authorization và nghiệp vụ]
~~~

Điểm cần nhấn mạnh là **“không yêu cầu CSRF token” không có nghĩa “không cần bảo vệ khác”**. GET đọc dữ liệu tài khoản vẫn phải qua xác thực/phân quyền nếu dữ liệu không công khai.

Một cấu hình Servlet minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(Customizer.withDefaults()) // Giữ chính sách CSRF mặc định.
            .build();
    }
}
~~~

Không cần tự định nghĩa một matcher chỉ để lặp lại các phương thức an toàn mặc định. Việc tùy chỉnh không cần thiết có thể khiến các endpoint mới hoặc phương thức ít gặp bị bỏ sót.

### 5.2. Mặc định trên Reactive/WebFlux

Với Reactive, `CsrfWebFilter` và `ServerHttpSecurity` cung cấp hành vi tương tự về phân loại method:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {
        return http
            .authorizeExchange(authorize -> authorize
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

Một GET qua WebFlux vẫn có thể bị chặn bởi **authentication/authorization**, dù không cần token CSRF. Một POST không mang token hợp lệ thường bị chặn ở CSRF, tùy security chain/entry point thực tế.

### 5.3. Matcher cấu hình riêng có thể thay đổi hành vi

Người phát triển có thể thay matcher để bỏ qua một số endpoint hoặc định nghĩa phạm vi CSRF khác. Vì vậy nếu quan sát `POST /settings` không cần token, đừng kết luận Spring Security mặc định bỏ qua POST; hãy xác minh:

1. Request có đi qua `SecurityFilterChain`/`SecurityWebFilterChain` dự kiến không?
2. CSRF có bị tắt trong chain đó không?
3. Có matcher `ignoringRequestMatchers`/tương đương bỏ qua URL không?
4. Có security chain khác áp dụng trước hoặc phạm vi `securityMatcher` không?
5. Request được reverse proxy chuyển tiếp với method/path nào?

**Không nên chỉ dựa vào việc endpoint có annotation `@GetMapping` hay `@PostMapping` để suy luận filter đã áp dụng như thế nào.** Filter đọc HTTP request thực tế trước khi controller xử lý.

### 5.4. Tại sao không “sửa” GET có tác động bằng cách bắt GET gửi CSRF token?

Có thể về mặt kỹ thuật cấu hình CSRF matcher để yêu cầu token trên GET. Nhưng điều này **không phải giải pháp ưu tiên** cho endpoint GET sai ngữ nghĩa:

- Browser, crawler, prefetch và hệ thống cache vẫn mặc định xem GET là thao tác đọc.
- Nhiều link GET thông thường sẽ không mang token, gây vỡ tương thích và khó sử dụng.
- Nếu token được đưa vào URL để GET “mang token”, giá trị có nguy cơ lộ qua lịch sử, log và `Referer`.
- Các lớp khác dựa trên chuẩn HTTP (cache, retry, navigation) vẫn chịu ảnh hưởng từ việc một GET có tác động.

Cách giải quyết đúng là **chuyển hành động sang POST/PUT/PATCH/DELETE phù hợp** và giữ CSRF protection cho các request có credential tự động gửi.

## 6. Ví dụ Spring MVC: đọc bằng GET, cập nhật bằng POST

Ví dụ tối giản sau dùng một kho dữ liệu trong bộ nhớ để minh họa HTTP semantics. Đây **không phải mẫu lưu trữ production**; production cần service, database, kiểm tra quyền và các bảo vệ phù hợp.

~~~java
import java.security.Principal;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/preferences")
class PreferencesController {

    private final Map<String, String> themeByUser =
            new ConcurrentHashMap<>();

    record ThemeInput(String theme) {}

    @GetMapping
    Map<String, String> read(Principal principal) {
        // Chỉ đọc: không ghi themeByUser hoặc cập nhật sở thích.
        String theme = themeByUser.getOrDefault(
                principal.getName(), "light");
        return Map.of("theme", theme);
    }

    @PostMapping
    ResponseEntity<Void> change(
            Principal principal,
            @RequestBody ThemeInput input) {
        String requested = input.theme();
        if (!Set.of("light", "dark").contains(requested)) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Theme không hợp lệ");
        }

        // Hành động ghi nằm trong POST.
        themeByUser.put(principal.getName(), requested);
        return ResponseEntity.noContent().build();
    }
}
~~~

Giả sử controller này được bảo vệ bởi cấu hình `SecurityFilterChain` ở mục 5:

- `GET /api/preferences` chỉ đọc theme của người dùng đã xác thực; **không cần CSRF token** nhưng vẫn phải được phân quyền.
- `POST /api/preferences` thay theme; **cần CSRF token** nếu chain đang bật CSRF theo mặc định.
- Với body JSON, client phù hợp thường gửi token trong **HTTP header** vì handler CSRF không tự tìm token từ một thuộc tính tùy ý trong JSON body.

Request hợp lệ:

~~~http
POST /api/preferences HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A
Content-Type: application/json
X-CSRF-TOKEN: TOKEN_HOP_LE

{"theme":"dark"}
~~~

`TOKEN_HOP_LE` là ký hiệu cho token thực do Spring Security phát hành và được request handler chấp nhận. Nếu người dùng thiếu quyền, token đúng **vẫn không thay** authentication/authorization.

### 6.1. Trường hợp form server-rendered

Đối với màn hình cài đặt:

~~~html
<!-- GET /settings: trả trang form đọc cài đặt hiện tại -->
<form action="/settings/theme" method="post">
  <label for="theme">Chế độ hiển thị</label>
  <select id="theme" name="theme">
    <option value="light">Sáng</option>
    <option value="dark">Tối</option>
  </select>

  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">
  <button type="submit">Lưu cài đặt</button>
</form>
~~~

Thymeleaf sẽ thay các thuộc tính `th:name` và `th:value` bằng tên/value của CSRF token được framework cung cấp. Với tích hợp có `th:action`, CSRF field có thể được thêm tự động; khi viết thủ công cần kiểm tra HTML cuối cùng để tránh trùng trường.

`GET /settings` chỉ hiển thị giao diện; **POST /settings/theme** thực hiện thay đổi sau bước CSRF. Không dùng `GET /settings/theme?value=dark` để thay thế POST.

### 6.2. Phân biệt GET có query parameter với GET có tác động

Query parameters hoàn toàn có thể xuất hiện trong một yêu cầu đọc:

~~~http
GET /products?category=book&sort=price HTTP/1.1
~~~

Đây vẫn là GET an toàn nếu server chỉ trả dữ liệu đã lọc/sắp xếp.

Ngược lại:

~~~http
GET /orders/42?status=paid HTTP/1.1
~~~

không thể coi là an toàn nếu server thực sự đổi trạng thái đơn hàng sang `paid` chỉ vì query parameter. **Cấu trúc URL không quyết định tính an toàn; code nghiệp vụ mới quyết định.**

## 7. Ví dụ Spring WebFlux: giữ ngữ nghĩa safe dù dùng reactive

Trong WebFlux, phương thức GET cũng chỉ nên đọc. Việc handler trả `Mono` hoặc `Flux` không thay đổi ngữ nghĩa HTTP.

~~~java
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/preferences")
class ReactivePreferencesController {

    private final Map<String, String> themeByUser =
            new ConcurrentHashMap<>();

    record ThemeInput(String theme) {}

    @GetMapping
    Mono<Map<String, String>> read(ServerWebExchange exchange) {
        return exchange.getPrincipal().map(principal ->
            Map.of("theme",
                themeByUser.getOrDefault(principal.getName(), "light")));
    }

    @PostMapping
    Mono<ResponseEntity<Void>> change(
            ServerWebExchange exchange,
            @RequestBody Mono<ThemeInput> input) {

        return Mono.zip(exchange.getPrincipal(), input)
            .map(tuple -> {
                String requested = tuple.getT2().theme();
                if (!Set.of("light", "dark").contains(requested)) {
                    throw new ResponseStatusException(
                            HttpStatus.BAD_REQUEST, "Theme không hợp lệ");
                }

                themeByUser.put(tuple.getT1().getName(), requested);
                return ResponseEntity.<Void>noContent().build();
            });
    }
}
~~~

Trong ví dụ:

- Handler GET chỉ đọc một cấu trúc dữ liệu.
- Handler POST xác minh input và thực hiện thay đổi trong nhánh được subscribe.
- Security WebFilterChain của WebFlux chịu trách nhiệm xác thực/phân quyền và CSRF bên ngoài handler.
- Bản demo dùng map trong bộ nhớ, **không thay thế** lưu trữ production hoặc kiểm tra quyền chi tiết.

Nếu một reactive handler GET gọi một dịch vụ có side effect, chẳng hạn `Mono.fromRunnable(() -> updateDatabase())`, **việc trả Mono không làm side effect ấy trở nên an toàn**. Phải xét hành vi thực tế khi publisher được subscribe.

## 8. HEAD, OPTIONS và TRACE: những điểm không nên bỏ qua

### 8.1. HEAD phải giữ ngữ nghĩa đọc

Một request HEAD hỏi metadata như status, content type, ETag, length theo cách không lấy response body. Spring MVC thường hỗ trợ xử lý HEAD tương ứng với handler GET khi phù hợp; điều này càng khiến việc GET có side effect trở nên nguy hiểm: một yêu cầu kiểm tra tài nguyên cũng có thể kích hoạt logic không mong muốn.

Ví dụ:

~~~http
HEAD /documents/123 HTTP/1.1
Host: app.example.com
~~~

Ứng dụng có thể xác minh tài liệu tồn tại và trả metadata mà **không chuyển tài liệu sang trạng thái “đã duyệt”**, không đánh dấu thanh toán hoàn tất hoặc xóa tài nguyên.

Một thao tác đọc có thể tạo log truy cập hoặc metric, nhưng không nên vô tình **thực hiện chức năng nghiệp vụ có tác động**.

### 8.2. OPTIONS và CORS preflight

Browser có thể gửi một preflight request:

~~~http
OPTIONS /api/preferences HTTP/1.1
Host: api.example.com
Origin: https://ui.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

OPTIONS ở đây hỏi server xem JavaScript từ origin nguồn có thể thực hiện một request cross-origin với method/header mong muốn không. **Preflight không phải POST nghiệp vụ**, nên không được dùng nó để cập nhật dữ liệu.

Quan trọng:

- Server xử lý `OPTIONS`/preflight theo cấu hình CORS.
- Sau khi preflight thành công (nếu cần), browser mới gửi **POST thật**.
- POST vẫn cần xác thực/phân quyền và CSRF token nếu ứng dụng dùng credential trình duyệt tự gửi.
- Việc preflight không đòi CSRF token **không có nghĩa POST tương ứng không đòi token**.

Khi gặp lỗi, phải phân biệt **CORS preflight bị chặn** với **POST đến server nhưng bị CSRF từ chối**. Hai vấn đề có cách khắc phục khác nhau.

### 8.3. TRACE là safe theo ngữ nghĩa nhưng có rủi ro riêng

TRACE vốn dùng để kiểm tra vòng lặp HTTP bằng cách phản chiếu request. Nếu được bật, nó có thể tạo khả năng **phản chiếu các phần của request**, bao gồm những thông tin cần bảo vệ khi cấu hình sai. Vì vậy các hệ thống production thường vô hiệu hóa TRACE ở web server/proxy/container.

**Không bật TRACE để “hoàn thiện danh sách safe methods”**. Việc Spring Security mặc định không yêu cầu CSRF cho TRACE không loại bỏ nhu cầu hạn chế phương thức này.

## 9. Method override và những chỗ dễ bỏ sót

### 9.1. HTML form chỉ hỗ trợ GET và POST trực tiếp

Form HTML thông thường dùng `method="get"` hoặc `method="post"`. Nếu ứng dụng muốn thao tác PUT/PATCH/DELETE từ form, có thể dùng một cơ chế **method override** hoặc gửi request qua JavaScript.

Ví dụ nhiều framework có thể cho form POST mang hidden parameter xác định phương thức đích, tùy bộ lọc được cấu hình:

~~~html
<form method="post" action="/documents/123">
  <input type="hidden" name="_method" value="DELETE">
  <input type="hidden" name="_csrf" value="TOKEN_DO_SERVER_CAP">
  <button type="submit">Xóa tài liệu</button>
</form>
~~~

Khi cơ chế override được bật, cần đảm bảo **thứ tự filter và cách framework xác định method thực tế** không tạo đường bỏ qua CSRF. Bản thân `_method` không phải token CSRF. Request vẫn phải mang token hợp lệ và người dùng cần quyền xóa.

Không tự triển khai biến thể nguy hiểm cho phép `GET /documents/123?_method=DELETE` thực hiện xóa; đó vẫn là request GET do trình duyệt/crawler có thể truy cập.

### 9.2. Các endpoint có tác động ẩn trong GET

Khi review code, tìm những pattern như:

- `GET /logout` thực hiện đăng xuất ngay;
- `GET /account/disable-mfa`, `GET /roles/grant` hoặc `GET /admin/ban?id=...`;
- `GET /payment/confirm` trừ tiền hoặc hoàn tất đơn hàng chỉ dựa vào việc URL được truy cập;
- `GET /notifications/mark-all-read` đánh dấu đã đọc theo ý định của người dùng;
- `GET /subscriptions/unsubscribe` thực hiện hủy đăng ký ngay khi bot xem trước link.

Với những đường dẫn được gửi qua email (xác thực email, hủy đăng ký, xác nhận giao dịch), **link scanner/bot có thể GET URL trước người dùng**. Một thiết kế thận trọng có thể dùng GET để hiển thị trang mô tả và xác nhận, sau đó yêu cầu POST hoặc cơ chế ràng buộc hành động phù hợp. Việc dùng một secret trong URL không tự sửa vấn đề tác động phụ của GET và còn tạo nguy cơ lộ secret qua URL.

### 9.3. “Đăng nhập bằng GET” có phải ngoại lệ?

**Hiển thị form login bằng GET** là an toàn về ngữ nghĩa vì chỉ trình bày giao diện. **Gửi username/password để tạo session đăng nhập** là hành động thay đổi trạng thái xác thực, thường được thực hiện bằng POST.

Tương tự, trong một số luồng OAuth/OIDC, callback GET nhận code để hoàn tất xác thực theo giao thức và được bảo vệ bằng `state`, PKCE/nonce và cơ chế chuyên biệt. Đây là trường hợp **luồng giao thức có ngữ nghĩa riêng**, không phải giấy phép thiết kế mọi endpoint nghiệp vụ thay đổi trạng thái bằng GET. Khi xây ứng dụng cần phân biệt endpoint OAuth callback với endpoint GET tùy ý của chính mình.

## 10. Kiểm thử: bảo đảm GET không làm thay đổi dữ liệu

Chỉ kiểm tra **GET trả HTTP 200** là chưa đủ. Một endpoint có thể trả 200 đồng thời đã ghi database. Cần kiểm thử **trạng thái trước và sau**.

### 10.1. Ma trận kiểm tra

| Kịch bản | Phương thức | CSRF token | Kỳ vọng |
|---|---|---|---|
| Xem thông tin | `GET` | Không có | Được xử lý nếu được cấp quyền; **không thay đổi trạng thái** |
| Xem headers | `HEAD` | Không có | Không thay đổi nghiệp vụ |
| CORS preflight | `OPTIONS` | Không có | Trả chính sách CORS, không thực hiện POST nghiệp vụ |
| Tạo mới | `POST` | Thiếu | Thường bị chặn bởi CSRF với cấu hình mặc định |
| Cập nhật | `PUT`/`PATCH` | Thiếu/sai | Thường bị chặn bởi CSRF với cấu hình mặc định |
| Xóa | `DELETE` | Thiếu/sai | Thường bị chặn bởi CSRF với cấu hình mặc định |
| Cập nhật đúng | `POST`/`PUT`/`PATCH` | Token hợp lệ | Có thể qua bước CSRF; vẫn cần authorization/validation |
| GET có query `?theme=dark` | `GET` | Không có | Chỉ trả dữ liệu, **không được đổi theme** |
| Đường dẫn “logout” bằng GET | `GET` | Không có | Không thực hiện đăng xuất trực tiếp ở thiết kế an toàn |

Kết quả status code cụ thể còn phụ thuộc authentication entry point và security chain. `403` có thể do CSRF hoặc authorization; `401` thường liên quan xác thực; lỗi CORS trong browser có thể xuất hiện trước khi POST thật được gửi.

### 10.2. Kiểm thử Servlet bằng MockMvc

Giả sử ứng dụng có `PreferencesController` như ở mục 6, đã bật Spring Security và thêm dependency `spring-security-test`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SafeMethodsServletTests {

    @Autowired MockMvc mvc;

    @Test
    void getDoesNotUpdatePreferences() throws Exception {
        mvc.perform(get("/api/preferences")
                .with(user("reader-1"))
                .param("theme", "dark"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.theme").value("light"));

        mvc.perform(get("/api/preferences")
                .with(user("reader-1")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.theme").value("light"));
    }

    @Test
    void postWithoutCsrfTokenIsRejected() throws Exception {
        mvc.perform(post("/api/preferences")
                .with(user("writer-1"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"theme\":\"dark\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfTokenPassesCsrfCheck() throws Exception {
        mvc.perform(post("/api/preferences")
                .with(user("writer-2"))
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"theme\":\"dark\"}"))
            .andExpect(status().isNoContent());
    }
}
~~~

Test dùng user khác nhau nhằm tránh các test ghi cùng một giá trị dùng chung trong demo map. Trong hệ thống thực, nên dùng test database/snapshot hoặc service fake để đối chiếu **không có thao tác ghi**. Test `with(csrf().asHeader())` mô phỏng token hợp lệ, không thay thế bài kiểm thử browser thực tế lấy token qua form/cookie.

Nếu GET được triển khai sai nhưng chỉ tăng một bộ đếm hoặc gọi một dịch vụ khác, test trả JSON chưa chắc phát hiện. Cần bổ sung assertion trên kho dữ liệu, sự kiện nghiệp vụ, audit có ý nghĩa, queue hoặc phương thức ghi được gọi.

### 10.3. Kiểm thử Reactive bằng WebTestClient

Ví dụ với ứng dụng WebFlux có controller mục 7 và `spring-security-test`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class SafeMethodsReactiveTests {

    @Autowired ApplicationContext context;

    WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void getReadsWithoutChangingTheme() {
        client().mutateWith(mockUser("reader-2"))
            .get().uri("/api/preferences?theme=dark")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.theme").isEqualTo("light");
    }

    @Test
    void postWithoutCsrfTokenIsRejected() {
        client().mutateWith(mockUser("writer-3"))
            .post().uri("/api/preferences")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"theme\":\"dark\"}")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void postWithCsrfTokenIsAllowedPastCsrfLayer() {
        client().mutateWith(mockUser("writer-4"))
            .mutateWith(csrf())
            .post().uri("/api/preferences")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"theme\":\"dark\"}")
            .exchange()
            .expectStatus().isNoContent();
    }
}
~~~

Giả định endpoint reactive trả `200` cho GET và `204` cho POST. Nếu dùng service/validation khác, hãy điều chỉnh assertion. `mutateWith(csrf())` là helper test cho security web filter, không tự chứng minh browser đã nhận/đính kèm CSRF token theo giao diện thực.

### 10.4. Kiểm thử browser, crawler và prefetch

Trong môi trường được phép:

1. Đăng nhập vào tài khoản thử nghiệm, ghi nhận trạng thái ban đầu (theme, MFA, quyền, số đơn hàng…).
2. Gửi GET trực tiếp đến tất cả URL được xem là chỉ đọc, kể cả các tham số đáng ngờ như `action=delete` hoặc `status=approved`.
3. Kiểm tra **trạng thái dữ liệu phía server trước và sau**; GET không được thực hiện yêu cầu ghi.
4. Kiểm tra các link ở giao diện có đang vô tình kích hoạt thay đổi dữ liệu không.
5. Kiểm tra headless crawler/link preview hoặc prefetch trong test environment nếu ứng dụng có tính năng đó.
6. Với POST/PUT/PATCH/DELETE của trình duyệt, thử thiếu CSRF token và token sai; yêu cầu phải bị chặn nếu thuộc phạm vi bảo vệ.
7. Thử token hợp lệ và đủ quyền, xác nhận thao tác được thực hiện như thiết kế.
8. Đối chiếu chính sách `SameSite` của cookie và kiểm tra request cross-site thật bằng DevTools; đừng suy luận từ HTTP client có thể tùy ý gắn header `Cookie`.

Chỉ nên thực hiện các ca thử có khả năng gây tác động trong môi trường thử nghiệm hoặc nơi có quyền. Nếu phát hiện GET có side effect ở hệ thống thật, tránh thử lặp lại gây thay đổi dữ liệu; ưu tiên review code và tạo regression test cô lập.

## 11. Chẩn đoán các xung đột bảo mật thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| GET có tác động nhưng không bị CSRF chặn | GET nằm trong danh sách safe mặc định | **Sửa endpoint sang method ghi**; không chỉ mở rộng matcher để chặn GET |
| Một link trong email bị bot truy cập trước và “xác nhận” hành động | GET thực hiện ngay hành động | Tách GET hiển thị trang và POST xác nhận hoặc luồng có ràng buộc rõ ràng |
| POST trả `403` sau khi sửa từ GET | Client chưa gửi CSRF token | Render token vào form hoặc dùng header tương ứng |
| API GET trả `401`/redirect login | GET không cần CSRF nhưng vẫn yêu cầu authentication | Cấp credential hợp lệ; không tắt auth |
| PUT/DELETE không bị yêu cầu CSRF | Chain/matcher đang bỏ qua hoặc CSRF tắt | Kiểm tra phạm vi chain, matcher, credential browser tự gửi |
| OPTIONS preflight bị `401`/`403` | CORS chưa được xử lý đúng vị trí hoặc bị chặn bởi auth | Sửa CORS/security filter order; không bỏ CSRF cho POST |
| Browser GET từ site ngoài không gửi cookie | `SameSite`/chính sách cookie, host/path/protocol | Phân tích cookie; vẫn phải giữ GET read-only |
| HEAD gây cập nhật dữ liệu | Chia sẻ code có side effect với GET | Sửa logic đọc, kiểm thử HEAD và trạng thái sau request |
| TRACE có thể truy cập và phản chiếu dữ liệu | Phương thức chẩn đoán đang được bật ngoài ý muốn | Vô hiệu/giới hạn TRACE ở các lớp thích hợp |
| Client gửi POST bằng body nhưng backend nhận GET | HTML form thiếu `method="post"` hoặc client gửi sai | Kiểm tra request thực tế, sửa method đúng |
| Lỗi sau khi dùng method override | Filter order hoặc cấu hình parse method không thống nhất | Kiểm tra method thực tế tại security chain và handler |
| Thử `csrf()` trong unit test pass nhưng browser vẫn lỗi | Test không mô phỏng cookie, form/header hoặc session lifecycle | Thêm browser/integration test lấy token thật |

**Không coi việc không bị CSRF chặn là bằng chứng một API an toàn.** Một request `GET` thiếu auth vẫn có thể bị từ chối; một `POST` không cần CSRF có thể do cấu hình matcher, hoặc thực sự là API bearer-only đã được đánh giá. Phải xét cả **ngữ nghĩa HTTP, cách xác thực và các filter đang hoạt động**.

## 12. Những nhận định sai thường gặp

### “GET là an toàn nên có thể đặt hành động xóa dữ liệu vào GET”

**Sai.** GET chỉ được coi là safe khi ứng dụng tôn trọng ngữ nghĩa đọc. Đặt chức năng xóa vào GET là phá vỡ giả định quan trọng của browser, crawler, cache và CSRF filter.

### “PUT và DELETE là idempotent nên không cần CSRF token”

**Sai.** Idempotency liên quan đến tác động dự kiến khi lặp request; cả PUT và DELETE vẫn **được client yêu cầu thay đổi trạng thái**, nên không safe và thường cần CSRF token khi dùng credential trình duyệt tự gửi.

### “Cookie SameSite=Lax sẽ chặn mọi request GET từ trang khác”

**Sai.** Lax có thể cho phép cookie ở một số điều hướng cấp cao bằng GET. Ngoài ra có sự khác nhau giữa **same-site** và **same-origin**.

### “OPTIONS không yêu cầu CSRF token tức là CORS đã bảo vệ luôn POST”

**Sai.** OPTIONS preflight chỉ hỏi chính sách cross-origin. POST thực tế vẫn cần kiểm tra token và quyền khi áp dụng.

### “Chỉ cần đặt CSRF token trên link GET nhạy cảm”

**Không phải giải pháp đúng mặc định.** Token trong URL dễ bị lộ; GET có tác động vẫn vi phạm ngữ nghĩa, dễ bị trình duyệt và hệ thống trung gian xử lý như một hành động đọc.

### “An toàn nghĩa là không có bất kỳ tác động phụ nào trên server”

**Không hoàn toàn.** Logging/metric/cache có thể là tác động phụ không được client yêu cầu. Điều cần ngăn là các **thay đổi nghiệp vụ có chủ đích** như xóa, cập nhật, cấp quyền hoặc giao dịch.

### “Reactively returning Mono makes GET safe”

**Sai.** Một publisher reactive thực hiện lệnh ghi khi được subscribe vẫn là hành động ghi. Ngữ nghĩa safe/unsafe dựa trên hành vi của endpoint chứ không dựa vào stack.

## 13. Câu hỏi tự đánh giá

**Tình huống A.** Ứng dụng có `GET /orders/42/approve`; truy cập URL là đơn hàng chuyển sang “Đã duyệt”. Bộ lọc CSRF mặc định không chặn request. Vấn đề chính là gì?

**Đáp án:** Endpoint dùng GET để thay đổi trạng thái. Cần chuyển sang POST/PATCH phù hợp, bảo vệ bằng CSRF khi có credential browser tự gửi và kiểm tra quyền của người duyệt.

**Tình huống B.** `DELETE /api/items/7` là idempotent; một người dùng khác gửi request xóa bằng browser. Có thể miễn CSRF vì idempotent không?

**Đáp án:** Không. DELETE vẫn là unsafe; idempotency không thay tính chất thay đổi trạng thái. Cần đánh giá CSRF dựa trên cách credential được gửi.

**Tình huống C.** Một SPA gọi `OPTIONS /api/preferences` trước khi POST. Server phải yêu cầu CSRF token trên OPTIONS không?

**Đáp án:** Thông thường không. OPTIONS là preflight/safe method; nhưng POST thật vẫn cần CSRF token nếu endpoint có credential browser tự động gửi và chain bảo vệ CSRF.

**Tình huống D.** API chỉ dùng JWT trong `Authorization` do client chủ động thêm, không có cookie/session/Basic tự gửi. POST của API có bắt buộc cần CSRF token không?

**Đáp án:** Theo mô hình CSRF dựa trên credential tự gửi, có thể không cần ở những endpoint được xác minh **bearer-only**; nhưng yêu cầu đó khác với việc phân loại POST là unsafe. Vẫn cần xác thực/phân quyền, chống lộ token/XSS và xác nhận không có đường xác thực cookie khác.

**Tình huống E.** Một hệ thống tăng bộ đếm metric mỗi khi nhận GET. Có vi phạm safe semantics không?

**Đáp án:** Không tự động. Metric/log kỹ thuật có thể là tác động phụ không do client yêu cầu. Nhưng nếu GET cố ý tăng số dư, thay tiến độ học tập, gửi email, đánh dấu đã đọc hay thay dữ liệu nghiệp vụ thì phải xem lại thiết kế.

**Tình huống F.** Trang đặt một link `GET /logout` và browser có `SameSite=Lax`. Vì sao cách thiết kế này vẫn đáng lo?

**Đáp án:** Điều hướng cấp cao bằng GET có thể gửi cookie Lax; nếu GET thực hiện logout thì một liên kết ngoài có thể gây đăng xuất. Luồng chuẩn nên dùng POST logout với token, còn GET có thể hiển thị xác nhận.

## Kết luận

**Phương thức HTTP an toàn chỉ dùng cho yêu cầu đọc/quan sát**, không được dùng để yêu cầu thay đổi trạng thái nghiệp vụ. Theo ngữ nghĩa HTTP, `GET`, `HEAD`, `OPTIONS` và `TRACE` là các phương thức safe, nhưng `TRACE` thường nên bị vô hiệu hóa vì rủi ro phản chiếu dữ liệu. Ngược lại, `POST`, `PUT`, `PATCH`, `DELETE` là những phương thức không an toàn dù một số có tính **idempotent**.

Spring Security **Servlet** (`CsrfFilter`) và **Reactive/WebFlux** (`CsrfWebFilter`) thường **không đòi CSRF token cho các phương thức safe** theo mặc định. Đây không phải một lỗ hổng của framework mà là một giả định kiến trúc: GET/HEAD/OPTIONS/TRACE không được thực hiện các hành động có tác động do client yêu cầu. Khi một endpoint GET bị dùng để xóa, thanh toán, thay quyền hoặc logout, cách sửa đúng là **đưa thao tác sang phương thức ghi phù hợp**, giữ CSRF token cho các request cần bảo vệ và kiểm thử trạng thái trước/sau.

Những ràng buộc này phối hợp với CORS, SameSite cookie, security headers, CSP, HSTS, HTTP firewall, quản lý session và phân quyền để tạo nên hệ thống phòng vệ HTTP đáng tin cậy trong **SPRING_SECURITY_HTTP_PROTECTION**.

## Nguồn tham khảo

- [RFC 9110 — HTTP Semantics, Safe Methods](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.1): định nghĩa safe method, tác động phụ không do client yêu cầu và yêu cầu với owner tài nguyên.
- [RFC 9110 — Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2): sự khác nhau giữa idempotent và safe.
- [Spring Security — CSRF Protection, Servlet](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): mặc định kiểm tra unsafe methods, token repository và request handling.
- [Spring Security — CSRF Protection, WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): CSRF protection ở Reactive stack.
