# Giữ logic xác thực, phân quyền và nghiệp vụ ở các thành phần phù hợp

> Phạm vi: thiết kế ứng dụng Java 17+ với Spring Boot 3.x, Spring Security 6.x trên nền Servlet/Spring MVC. Bài học giải thích cách phân chia trách nhiệm giữa **authentication** (xác thực danh tính), **authorization** (phân quyền) và **business rules** (quy tắc nghiệp vụ); minh họa một API có kiểm tra quyền trên từng đối tượng và kiểm tra điều kiện tính giá. Không giả định mọi quyết định liên quan người dùng đều là quyết định bảo mật.

## 1. Ba câu hỏi khác nhau

Giả sử ứng dụng có API xem báo giá của đơn hàng. Người dùng `alice` yêu cầu xem đơn hàng `A-100` và áp dụng mức giảm giá 10%. Hệ thống cần trả lời:

1. **Xác thực (authentication):** Ai gửi yêu cầu? Mật khẩu/token/phiên có chứng minh được đó là `alice` không?
2. **Phân quyền (authorization):** Danh tính đó có quyền **xem báo giá của đơn hàng `A-100`** không? Chủ sở hữu hoặc quản trị viên có thể được phép; người dùng khác bị chặn.
3. **Nghiệp vụ (business):** Với đơn hàng người gọi có quyền xem, có thể giảm 10% không? Ví dụ quy định mức giảm tối đa 20% và đơn đã giao không được tính lại giá có giảm.

Ba câu hỏi có thể cùng xảy ra trong một request nhưng **phải có chủ thể chịu trách nhiệm riêng**. Đừng trả “sai mật khẩu” cho người dùng đã xác thực nhưng thiếu quyền; cũng đừng biến lỗi “đơn đã giao, không được giảm giá” thành một lỗi thiếu role.

| Loại quyết định | Dữ liệu/điều kiện chính | Nơi phù hợp | Phản hồi điển hình |
| --- | --- | --- | --- |
| Authentication | Username/password, token, chữ ký, trạng thái tài khoản | Filter và `AuthenticationManager` / `AuthenticationProvider` / `UserDetailsService` tùy cơ chế | HTTP 401 với HTTP Basic/Bearer; form login có thể redirect |
| Authorization ở HTTP | Endpoint nào cần đăng nhập? Đường dẫn nào chỉ dành cho admin? | `SecurityFilterChain`, `authorizeHttpRequests`, `AuthorizationManager` | Thường 401 nếu chưa xác thực, 403 nếu đã xác thực nhưng không được phép |
| Authorization ở phương thức/tài nguyên | Người dùng có role/scope phù hợp? Có sở hữu đối tượng không? | `@PreAuthorize`, `@PostAuthorize`, `AuthorizationManager`/policy bean | Thường 403 khi đã xác thực nhưng thiếu quyền |
| Business validation | Trạng thái đơn hàng, hạn mức giảm giá, tồn kho, giá trị hợp đồng, hạn thanh toán | Domain/service và các domain object | 400, 409, 422 hoặc mã nghiệp vụ phù hợp; không mặc nhiên 401/403 |
| Truy cập dữ liệu | Truy vấn và lưu dữ liệu đã được yêu cầu | Repository/data access, transaction và cơ chế thực thi chính sách dữ liệu | Tùy kết quả nghiệp vụ; truy vấn không tự thay thế kiểm tra quyền |
| Chuyển ngoại lệ thành HTTP | Định dạng phản hồi security hoặc lỗi miền nghiệp vụ | `AuthenticationEntryPoint`, `AccessDeniedHandler`; `@RestControllerAdvice` cho lỗi MVC/domain | Nhất quán mà không lộ thông tin nhạy cảm |

**Quy tắc tự hỏi khi phân loại:** “Nếu đổi danh tính người gọi, quyết định này có đổi không?” Nếu có, nó có thể là authorization. “Nếu mọi người đều có quyền, trạng thái giao dịch này có vẫn cấm thao tác không?” Nếu có, đó thường là business rule. Có những tình huống kết hợp (hạn mức theo vai trò, quy tắc duyệt nhiều cấp); hãy mô hình hóa rành mạch phần chính sách truy cập và phần ràng buộc miền nghiệp vụ thay vì trộn trong controller.

## 2. Các thành phần Spring Security nên làm việc gì?

### Authentication: xác minh danh tính

Trong ứng dụng Servlet, một filter xác thực đọc cơ chế HTTP thích hợp, tạo đối tượng `Authentication` chưa xác thực và nhờ `AuthenticationManager` kiểm chứng. `ProviderManager` có thể điều phối một hoặc nhiều `AuthenticationProvider`. Với username/password thông thường, `DaoAuthenticationProvider` kết hợp `UserDetailsService` và `PasswordEncoder` là lựa chọn sẵn có.

- `UserDetailsService`: tải thông tin tài khoản từ nguồn dữ liệu tin cậy.
- `PasswordEncoder`: đối chiếu mật khẩu thô với hash; không tự so sánh password plaintext.
- `AuthenticationProvider`: thực hiện kiểm chứng credential cho loại `Authentication` hỗ trợ.
- `SecurityContextHolder`: cung cấp ngữ cảnh chứa `Authentication` đã thiết lập cho luồng thực thi; thông thường filter/framework quản lý.
- `AuthenticationEntryPoint` và failure handler: quyết định phản hồi khi cần/không thể xác thực.

Khi ứng dụng chỉ đổi cách lưu người dùng, **ưu tiên viết `UserDetailsService`** và tận dụng `DaoAuthenticationProvider`. Chỉ viết provider/filter tùy chỉnh nếu loại credential hoặc quá trình xác thực thực sự đòi hỏi. Service tính tiền không cần biết cách giải mã HTTP Basic hay xác minh chữ ký JWT.

### Authorization: quyết định ai được làm gì

Có hai mức phổ biến:

1. **Request-level security** trong `HttpSecurity.authorizeHttpRequests(...)`: ví dụ mọi đường dẫn `/admin/**` yêu cầu `ROLE_ADMIN`; các API khác yêu cầu đã đăng nhập.
2. **Method/object-level security**: bảo vệ lời gọi service với `@PreAuthorize`, policy bean hoặc `AuthorizationManager`, ví dụ “chỉ chủ đơn hàng hoặc admin được tính báo giá đơn này”.

Spring Security 6 hỗ trợ `@EnableMethodSecurity` để bật các annotation như `@PreAuthorize`. Spring Boot starter security **không mặc định bật method security**. Chính sách tại service có giá trị khi service được gọi từ REST controller, job, message listener hoặc các đường gọi khác; không chỉ khi đi qua một URL duy nhất.

Policy có thể đọc dữ liệu cần thiết như ownerId, tenantId, trạng thái hiển thị; nhưng nó nên trả về một **quyết định cấp quyền**, không tự tính tiền, thay đổi đơn hàng hoặc làm toàn bộ nghiệp vụ. Khi quy tắc phức tạp, tách thành một bean có tên và unit test được.

### Business: bảo đảm bất biến của miền nghiệp vụ

Service/domain kiểm tra các điều kiện vẫn tồn tại ngay cả khi actor đã có quyền: số tiền không âm, mức giảm tối đa, đơn đã chốt không được chỉnh sửa, tồn kho đủ, trạng thái chuyển hợp lệ.

Các lỗi này thường cần một domain exception và mapping HTTP riêng; chẳng hạn đơn không thể tính lại do đã giao là `409 Conflict` trong API minh họa. **Admin không tự nhiên được bỏ qua mọi quy tắc nghiệp vụ**: được phép thực hiện một thao tác không có nghĩa thao tác ấy hợp lệ với mọi trạng thái dữ liệu.

## 3. Trật tự kiểm tra và luồng xử lý

Luồng đơn giản hóa của ví dụ:

```text
HTTP GET /orders/A-100/quote?discountPercent=10
      |
      v
SecurityFilterChain / HTTP Basic
  - Không có credential hoặc sai credential -> yêu cầu xác thực / 401
  - Credential hợp lệ -> Authentication đã xác thực
      |
      v
Authorization ở URL: anyRequest().authenticated()
      |
      v
@RestController: nhận orderId, discountPercent; gọi service
      |
      v
Proxy @PreAuthorize trên QuoteService
  - ADMIN hoặc chủ đơn -> tiếp tục
  - Không có quyền -> AccessDeniedException -> thường 403
      |
      v
QuoteService: kiểm tra ràng buộc nghiệp vụ
  - Giảm giá ngoài 0..20 -> 400
  - Đơn SHIPPED nhưng vẫn giảm > 0 -> 409
  - Đơn không tồn tại (người có quyền kiểm tra) -> 404
  - Hợp lệ -> tính giá, trả Quote -> 200
```

`ExceptionTranslationFilter` chuyển các ngoại lệ bảo mật như `AuthenticationException`, `AccessDeniedException` ở luồng được bảo vệ thành phản hồi phù hợp thông qua entry point/denied handler; **nó không phải bộ kiểm tra quyền**. Lỗi miền nghiệp vụ từ controller/service thường được `@RestControllerAdvice` ánh xạ thành response. Không nên dùng một `@ControllerAdvice` chung để thay thế toàn bộ security exception handling vì nhiều lỗi xuất hiện trước Spring MVC.

Các mã HTTP ở đây là **hành vi kỳ vọng theo cấu hình HTTP Basic của ví dụ**; với form login, session, OAuth2 Resource Server hoặc cấu hình handler khác có thể có cách phản hồi khác.

## 4. Ví dụ chạy được: xem báo giá chỉ khi có quyền

### 4.1. Yêu cầu

Một kho đơn hàng thử nghiệm gồm hai bản ghi:

| Đơn | Chủ sở hữu | Trạng thái | Giá trước giảm |
| --- | --- | --- | --- |
| `A-100` | `alice` | `OPEN` | 100.00 |
| `B-200` | `bob` | `SHIPPED` | 80.00 |

Tài khoản demo:

| Người dùng | Mật khẩu demo | Role |
| --- | --- | --- |
| `alice` | `alice-pass` | `ROLE_USER` |
| `bob` | `bob-pass` | `ROLE_USER` |
| `admin` | `admin-pass` | `ROLE_ADMIN` |

Quy tắc:

- Người dùng phải xác thực qua HTTP Basic.
- Chỉ **chủ đơn** hoặc **admin** được xem/tính báo giá của đơn đó.
- Mức giảm hợp lệ nằm trong **0–20%**.
- Đơn `SHIPPED` không được áp dụng mức giảm lớn hơn 0, **kể cả admin**.
- API chỉ **đọc và tính toán** báo giá; `GET` không làm thay đổi trạng thái hay dữ liệu.
- Đơn không tồn tại: với caller đã qua chính sách (như admin), trả 404; với người chưa có quyền truy cập đối tượng, policy có thể trả 403 để không lộ sự tồn tại của ID.

Mô hình này có chủ ý: xác thực do Spring Security và `UserDetailsService` đảm nhiệm, quyền chủ đơn ở policy, tính giá và quy tắc trạng thái ở service. Repository chỉ lưu/tra dữ liệu.

### 4.2. Phụ thuộc

Tạo dự án Spring Boot 3.x sử dụng Java 17+ và Gradle, trong `build.gradle` đã cấu hình plugin Boot và quản lý phiên bản. Phần `dependencies` cần:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây chỉ là **khối phụ thuộc**, không phải toàn bộ file Gradle. Không thêm `spring-boot-starter-data-jpa` vì ví dụ dùng repository trong bộ nhớ.

### 4.3. Một file Java hoàn chỉnh

Tạo đúng file `src/main/java/demo/DemoApplication.java`:

```java
package demo;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Map;
import java.util.Optional;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration
@EnableMethodSecurity
class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-pass"))
                        .roles("USER").build(),
                User.withUsername("bob")
                        .password(encoder.encode("bob-pass"))
                        .roles("USER").build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin-pass"))
                        .roles("ADMIN").build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

enum OrderStatus {
    OPEN, SHIPPED
}

record DemoOrder(
        String id, String owner, OrderStatus status, BigDecimal subtotal) {
}

@Repository
class OrderRepository {
    private final Map<String, DemoOrder> orders = Map.of(
            "A-100", new DemoOrder(
                    "A-100", "alice", OrderStatus.OPEN,
                    new BigDecimal("100.00")),
            "B-200", new DemoOrder(
                    "B-200", "bob", OrderStatus.SHIPPED,
                    new BigDecimal("80.00"))
    );

    Optional<DemoOrder> findById(String id) {
        return Optional.ofNullable(orders.get(id));
    }
}

@Component("orderAccess")
class OrderAccess {
    private final OrderRepository repository;

    OrderAccess(OrderRepository repository) {
        this.repository = repository;
    }

    public boolean isOwner(Authentication authentication, String orderId) {
        return authentication != null
                && repository.findById(orderId)
                        .map(order -> order.owner()
                                .equals(authentication.getName()))
                        .orElse(false);
    }
}

record PriceQuote(
        String orderId,
        String owner,
        OrderStatus status,
        BigDecimal subtotal,
        int discountPercent,
        BigDecimal payable) {
}

class OrderNotFound extends RuntimeException {
    OrderNotFound(String message) {
        super(message);
    }
}

class BusinessRuleViolation extends RuntimeException {
    BusinessRuleViolation(String message) {
        super(message);
    }
}

@Service
class QuoteService {
    private final OrderRepository repository;

    QuoteService(OrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasRole('ADMIN') or "
            + "@orderAccess.isOwner(authentication, #orderId)")
    public PriceQuote calculate(
            @P("orderId") String orderId,
            int discountPercent) {

        if (discountPercent < 0 || discountPercent > 20) {
            throw new IllegalArgumentException(
                    "discountPercent must be between 0 and 20");
        }

        DemoOrder order = repository.findById(orderId)
                .orElseThrow(() -> new OrderNotFound(
                        "Order not found"));

        if (order.status() == OrderStatus.SHIPPED
                && discountPercent > 0) {
            throw new BusinessRuleViolation(
                    "Shipped orders cannot receive a discount");
        }

        BigDecimal rate = BigDecimal.valueOf(discountPercent)
                .movePointLeft(2);
        BigDecimal payable = order.subtotal()
                .multiply(BigDecimal.ONE.subtract(rate))
                .setScale(2, RoundingMode.HALF_UP);

        return new PriceQuote(
                order.id(), order.owner(), order.status(),
                order.subtotal(), discountPercent, payable);
    }
}

@RestController
class OrderController {
    private final QuoteService quoteService;

    OrderController(QuoteService quoteService) {
        this.quoteService = quoteService;
    }

    @GetMapping("/orders/{orderId}/quote")
    PriceQuote quote(
            @PathVariable String orderId,
            @RequestParam(defaultValue = "0") int discountPercent) {
        return quoteService.calculate(orderId, discountPercent);
    }
}

@RestControllerAdvice
class ApiErrorHandler {
    @ExceptionHandler(OrderNotFound.class)
    ResponseEntity<Map<String, String>> notFound(OrderNotFound error) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("error", "not_found",
                        "message", error.getMessage()));
    }

    @ExceptionHandler(BusinessRuleViolation.class)
    ResponseEntity<Map<String, String>> conflict(
            BusinessRuleViolation error) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(Map.of("error", "business_rule",
                        "message", error.getMessage()));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> badRequest(
            IllegalArgumentException error) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(Map.of("error", "invalid_input",
                        "message", error.getMessage()));
    }
}
```

**Đặc điểm biên dịch:** `DemoApplication` là lớp `public` duy nhất; `SecurityConfig`, `OrderRepository`, `OrderAccess`, `QuoteService`, `OrderController` và `ApiErrorHandler` là các lớp top-level không `public` cùng package `demo`. `record` yêu cầu Java 16+ và chạy tốt trên Java 17. Spring Boot component scan bắt đầu từ package `demo` nên thấy các bean này.

**Điều cần quan sát trong mã:**

- `SecurityConfig.users(...)` tạo các tài khoản demo với BCrypt; `UserDetailsService` cung cấp dữ liệu cho cơ chế xác thực username/password tiêu chuẩn của Spring Security. Không viết password check trong controller.
- `securityFilterChain(...)` yêu cầu đăng nhập ở tầng HTTP; `httpBasic(...)` kích hoạt cơ chế xác thực Basic.
- `@EnableMethodSecurity` kích hoạt bảo vệ theo phương thức.
- `@PreAuthorize(...)` được đặt trên **phương thức public của service**. Policy gọi bean `orderAccess`. Annotation `@P("orderId")` giúp SpEL tham chiếu tham số `#orderId` ổn định ngay cả khi cách biên dịch parameter name khác nhau.
- `OrderAccess.isOwner(...)` chỉ trả quyết định sở hữu; không tính giá, không thay trạng thái đơn hàng.
- `QuoteService.calculate(...)` kiểm tra dữ liệu và bất biến miền nghiệp vụ sau khi người gọi qua phép kiểm tra quyền; được phép xem không bảo đảm mã giảm giá hợp lệ.
- `ApiErrorHandler` chỉ ánh xạ lỗi domain/đầu vào sang JSON. Không có `@ExceptionHandler(AccessDeniedException.class)` để chen ngang bộ xử lý lỗi bảo mật.

### 4.4. Chạy và kiểm tra kết quả

Trong thư mục dự án Spring Boot đã có Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Khi ứng dụng chạy ở `http://localhost:8080` (nếu chưa đổi `server.port`), thử các yêu cầu:

```bash
curl -i "http://localhost:8080/orders/A-100/quote?discountPercent=10"
curl -i -u alice:wrong \
  "http://localhost:8080/orders/A-100/quote?discountPercent=10"
curl -i -u alice:alice-pass \
  "http://localhost:8080/orders/A-100/quote?discountPercent=10"
curl -i -u bob:bob-pass \
  "http://localhost:8080/orders/A-100/quote?discountPercent=10"
curl -i -u admin:admin-pass \
  "http://localhost:8080/orders/A-100/quote?discountPercent=10"
curl -i -u bob:bob-pass \
  "http://localhost:8080/orders/B-200/quote?discountPercent=10"
curl -i -u bob:bob-pass \
  "http://localhost:8080/orders/B-200/quote?discountPercent=0"
curl -i -u alice:alice-pass \
  "http://localhost:8080/orders/A-100/quote?discountPercent=30"
curl -i -u admin:admin-pass \
  "http://localhost:8080/orders/MISSING/quote?discountPercent=0"
```

Trên PowerShell, gọi `curl.exe` thay `curl` nếu `curl` đang là alias của `Invoke-WebRequest`. Những dấu `\` cuối dòng ở đoạn trên là cú pháp tiếp dòng của Bash; trên PowerShell hãy viết mỗi lệnh `curl.exe` trên **một dòng**, hoặc dùng backtick PowerShell theo quy tắc của shell.

| Tình huống | HTTP kỳ vọng | Nguyên nhân |
| --- | --- | --- |
| Không credential | 401 | Chưa xác thực; Basic yêu cầu credentials |
| `alice` gửi sai mật khẩu | 401 | Lỗi authentication |
| `alice` gọi `A-100`, giảm 10% | 200, `payable=90.00` | Đúng chủ đơn; phép tính hợp lệ |
| `bob` gọi `A-100` | 403 | Đã xác thực nhưng không sở hữu và không là admin |
| `admin` gọi `A-100`, giảm 10% | 200, `payable=90.00` | Role admin được qua policy, sau đó quy tắc nghiệp vụ hợp lệ |
| `bob` gọi `B-200`, giảm 10% | 409 | Chủ đơn được phép, nhưng đơn `SHIPPED` vi phạm business rule |
| `bob` gọi `B-200`, giảm 0% | 200, `payable=80.00` | Chủ đơn và không vi phạm quy tắc giảm giá |
| `alice` gọi `A-100`, giảm 30% | 400 | Đầu vào vượt phạm vi kinh doanh 0..20 |
| `admin` gọi ID `MISSING` | 404 | Qua authorization nhờ role admin, nhưng không có đơn |

Ví dụ JSON ở phản hồi thành công (thứ tự các trường có thể khác):

```json
{
  "orderId": "A-100",
  "owner": "alice",
  "status": "OPEN",
  "subtotal": 100.00,
  "discountPercent": 10,
  "payable": 90.00
}
```

Đây là một API **tính giá nhưng không cập nhật dữ liệu**. Do chỉ dùng `GET`, ví dụ không phải tắt CSRF để thử với curl. Với `POST`/`PUT`/`DELETE` hoặc xác thực bằng cookie/session, cần thiết kế CSRF theo mô hình sử dụng; đừng tự thêm `csrf.disable()` chỉ vì gặp 403. HTTP Basic vẫn cần HTTPS khi triển khai thực tế; ví dụ mật khẩu trên localhost chỉ phục vụ học tập.

## 5. Tại sao không đặt tất cả vào controller?

Ví dụ thiếu phân chia trách nhiệm:

```java
// Minh họa cách làm không nên áp dụng nguyên xi:
@GetMapping("/orders/{id}/quote")
public Object quote(String id, String username, String password) {
    // Controller tự kiểm tra password, tự so sánh chủ đơn,
    // rồi tự tính tiền và quyết định status HTTP.
    return null;
}
```

Đây là **đoạn phản ví dụ không độc lập**, không thuộc chương trình chạy ở mục 4. Nó làm cho authentication, authorization, nghiệp vụ và xử lý HTTP dính chặt vào một endpoint. Hậu quả:

- Có thể có endpoint thứ hai quên kiểm tra mật khẩu hoặc quyền.
- Đường gọi từ job/service khác có thể bỏ qua kiểm tra đặt riêng trong controller.
- Muốn đổi kiểu xác thực từ Basic sang JWT phải sửa cả logic tính tiền.
- Business rule không thể test độc lập với HTTP/security.
- Các loại lỗi bị trộn lẫn, khiến client không phân biệt được 401, 403 và lỗi nghiệp vụ.

Trong cách tách lớp, controller nhận đầu vào và gọi service; Spring Security quản lý identity; policy đánh giá quyền; service/domain kiểm tra luật tính giá; repository lưu dữ liệu; advice xử lý ngoại lệ domain. Controller có thể kiểm tra hình thức input, nhưng đừng đặt toàn bộ kiểm chứng danh tính hay luật tài chính ở đó.

**Cũng không nên dồn tất cả vào `AuthenticationProvider`.** Provider chỉ cần biết credential có thể xác thực hay không, không cần biết đơn `A-100` đã giao hoặc mức giảm có vượt 20% hay không. Auth provider trả về danh tính và quyền cơ bản; các quyết định truy cập từng đối tượng được làm sau đó.

## 6. Method security: điểm mạnh và giới hạn

### Vì sao nên bảo vệ tại service?

Nếu đặt quy tắc ở `requestMatchers("/orders/**").hasRole("USER")`, tài khoản `bob` vẫn có `ROLE_USER` và có thể vượt qua tầng URL để xem đơn của `alice`. Phép kiểm tra role tổng quát **không thay thế** kiểm tra chủ sở hữu tài nguyên.

`@PreAuthorize("hasRole('ADMIN') or @orderAccess.isOwner(authentication, #orderId)")` kiểm tra theo từng lần gọi phương thức và từng `orderId`. Role admin vượt qua kiểm tra sở hữu, nhưng **không vượt qua quy tắc đơn đã giao** trong `QuoteService`.

### Những lưu ý về proxy

Method security mặc định áp dụng thông qua Spring AOP/proxy:

- Method phải được gọi qua bean do Spring quản lý. Tự `new QuoteService(...)` có thể bỏ qua interceptor.
- Lời gọi **từ một method tới một method khác trong cùng instance** (`this.calculate(...)`) thường không đi qua proxy, nên `@PreAuthorize` ở method đích có thể không chạy. Tách method có trách nhiệm riêng sang bean phù hợp hoặc tái thiết kế lời gọi qua proxy đúng cách.
- Với cấu hình proxy thông thường, các method private/final có giới hạn về việc intercept; ưu tiên service public và kiểm tra bằng integration test.
- Phải bật `@EnableMethodSecurity`; chỉ thêm `@PreAuthorize` vào mã nhưng không bật tính năng sẽ không tạo bảo vệ mong đợi.
- Tên tham số trong SpEL cần được discover đúng; ví dụ dùng `@P("orderId")` thay vì phụ thuộc hoàn toàn vào flag `-parameters` của compiler.

### Những lưu ý về dữ liệu và transaction

Policy dùng `OrderRepository` để tra owner rồi service cũng tra dữ liệu. Trong hệ thống thật, truy vấn quyền và cập nhật dữ liệu có thể xảy ra ở hai thời điểm khác nhau. Nếu có thao tác **ghi** nhạy cảm, cần thiết kế đồng bộ với transaction/locking/version hoặc ràng buộc update ở database để tránh trạng thái thay đổi giữa lúc check và lúc write (race condition). Một lời gọi `@PreAuthorize` đơn lẻ không đảm bảo tính nguyên tử của nghiệp vụ.

Với hệ thống nhiều tenant, tenantId và quyền chia sẻ cũng cần được áp dụng chặt chẽ khi query/update; không suy ra rằng chỉ cần kiểm tra owner ở controller là đủ. Có thể dùng query đã lọc theo danh tính/tenant trong repository hoặc policy ở service tùy yêu cầu; vẫn phải giữ ranh giới trách nhiệm rõ.

## 7. Ngoại lệ: security error khác domain error

Các ngoại lệ quan trọng:

| Tình huống | Loại lỗi phù hợp | Tầng xử lý |
| --- | --- | --- |
| Mật khẩu sai/credential không hợp lệ | `AuthenticationException` và kiểu con thích hợp | Authentication manager/filter và failure handling |
| Người đã xác thực nhưng thiếu quyền tài nguyên | `AccessDeniedException` hoặc kết quả deny từ method security | Authorization, `AccessDeniedHandler` |
| Tham số giảm giá ngoài 0..20 | `IllegalArgumentException` trong demo; thực tế có thể dùng validation/domain error cụ thể | Business/validation, `@RestControllerAdvice` |
| Đơn đã giao không được giảm | `BusinessRuleViolation` | Service/domain, `@RestControllerAdvice` thành 409 |
| Không tìm thấy đơn sau khi đã qua policy | `OrderNotFound` | Service/repository, `@RestControllerAdvice` thành 404 |
| Dịch vụ xác thực ngoài timeout | Ngoại lệ hạ tầng/xác thực phù hợp, ghi nhận sự cố an toàn | Authentication integration/operations; không giả làm sai password |
| Database lỗi khi tính giá | Lỗi hạ tầng, timeout hoặc API 5xx theo contract | Service/repository/observability; không giả làm 403 |

Không nên bắt `Exception` chung để trả 401 hoặc 403: hành vi này che khuất lỗi lập trình, lỗi database, lỗi nghiệp vụ. Ngược lại, nếu trong controller `@ExceptionHandler` cố bắt hết lỗi bảo mật, nhiều trường hợp filter chặn trước controller sẽ không đi qua handler ấy.

**Thứ tự xử lý có ý nghĩa:** nếu khách chưa có quyền gọi method, `@PreAuthorize` chặn trước khi service tính giá. Vì vậy một `bob` không có quyền xem `A-100` nhận 403 dù gửi mức giảm 30%; không dùng thông điệp business “giảm giá quá lớn” để tiết lộ thông tin của đơn họ không có quyền truy cập. Nếu admin tra ID không tồn tại, ví dụ trả 404 vì admin đã vượt qua policy. Với API công khai, chiến lược trả 403 hay 404 để tránh suy đoán tồn tại đối tượng phải được quyết định thống nhất và kiểm thử.

## 8. Kiểm thử độc lập từng trách nhiệm

### Kiểm thử hành vi qua Spring Security và MVC

Với dependency `spring-security-test` từ mục 4, tạo `src/test/java/demo/OrderSecurityTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderSecurityTest {
    @Autowired
    MockMvc mvc;

    @Test
    void unauthenticatedUserGets401() throws Exception {
        mvc.perform(get("/orders/A-100/quote"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void ownerCanReadQuote() throws Exception {
        mvc.perform(get("/orders/A-100/quote")
                        .with(httpBasic("alice", "alice-pass"))
                        .param("discountPercent", "10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("alice"))
                .andExpect(jsonPath("$.discountPercent").value(10));
    }

    @Test
    void anotherUserGets403() throws Exception {
        mvc.perform(get("/orders/A-100/quote")
                        .with(httpBasic("bob", "bob-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void forbiddenBusinessTransitionGets409() throws Exception {
        mvc.perform(get("/orders/B-200/quote")
                        .with(httpBasic("bob", "bob-pass"))
                        .param("discountPercent", "10"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error").value("business_rule"));
    }

    @Test
    void invalidPercentGets400() throws Exception {
        mvc.perform(get("/orders/A-100/quote")
                        .with(httpBasic("alice", "alice-pass"))
                        .param("discountPercent", "30"))
                .andExpect(status().isBadRequest());
    }
}
```

Chạy trong dự án bằng:

```bash
./gradlew test
```

Đây là **kiểm thử tích hợp**: nó xác nhận filter/HTTP Basic, method security và business error cùng hoạt động. Cần kiểm thử thêm admin đủ quyền nhưng vẫn bị business rule, user sai mật khẩu, trường hợp orderId không tồn tại và các đường gọi service ngoài controller.

### Kiểm thử từng phần độc lập

- **Authentication**: kiểm tra password đúng/sai, tài khoản bị khóa/disable, credential hết hạn hoặc token không hợp lệ; không dùng bài test giảm giá để chứng minh bcrypt đúng.
- **Authorization policy**: unit test `OrderAccess.isOwner(...)` với authentication `alice`, `bob` và ID thiếu; tích hợp thêm `@PreAuthorize` và role admin để tránh bỏ qua proxy.
- **Business rule**: kiểm tra mức giảm -1, 0, 10, 20, 21; trạng thái `OPEN` và `SHIPPED`; kiểm tra kết quả `BigDecimal` và quy tắc làm tròn. Nên thiết kế domain logic tách khỏi framework để test không cần Spring context khi ứng dụng lớn dần.
- **HTTP mapping**: kiểm tra 401/403 từ security handler, 400/409/404 từ domain advice, body JSON không chứa stack trace/token/hash.
- **Data/integration**: với database thật, kiểm tra transaction, race condition, isolation và ràng buộc tenant/owner ở query phù hợp.

## 9. Những lỗi thiết kế thường gặp

1. **Cho controller tự so mật khẩu** rồi tạo `Authentication` đã xác thực. Hệ quả: lặp logic, bỏ qua manager/filter và tăng nguy cơ tạo token giả. Hãy dùng hệ thống authentication của Spring Security.
2. **Đặt kiểm tra owner trong business validation rồi trả lỗi “đơn không hợp lệ”**. Quyền xem đối tượng là chính sách authorization; cần từ chối đúng, hạn chế rò rỉ existence.
3. **Coi có `ROLE_USER` là có quyền xem mọi đơn**. Quyền theo đối tượng cần owner/tenant/resource policy hoặc một mô hình permission tương ứng.
4. **Coi admin là có thể bỏ qua mọi luật giao dịch**. Admin có thể được cấp quyền gọi thao tác; nghiệp vụ vẫn kiểm tra trạng thái và bất biến.
5. **Chỉ đặt `@PreAuthorize` ở controller** mà service còn được gọi bởi job/message listener không có kiểm tra. Đặt policy ở biên service đủ rộng và kiểm thử các lối gọi khác.
6. **Quên `@EnableMethodSecurity` hoặc gọi nội bộ bypass proxy**. Annotation có thể hiện diện nhưng không bảo vệ đường gọi thực tế.
7. **Bắt mọi lỗi thành 403**, kể cả lỗi kho dữ liệu hoặc giảm giá vượt hạn mức. Cần phân loại exception và HTTP status theo trách nhiệm.
8. **Cho controller/repository quyết định mọi luật nghiệp vụ**. Controller nên điều phối HTTP, repository tập trung truy cập dữ liệu, service/domain bảo vệ invariant.
9. **Dùng giá trị `double` cho tiền** rồi so sánh trực tiếp. Ví dụ sử dụng `BigDecimal` và cách làm tròn rõ ràng; sản phẩm thật cần thêm currency, tax, rule version và policy rounding được thống nhất.
10. **Tắt CSRF để chữa lỗi 403** mà không xét cơ chế cookie/session; điều này có thể mở lỗ hổng ở ứng dụng trình duyệt. Ví dụ chỉ làm read-only GET để tập trung phân tầng.
11. **Tin username/role/orderOwner do client gửi** mà không đối chiếu principal được xác minh và dữ liệu phía server.
12. **Cấp quyền trước khi kiểm tra tenant hoặc tài nguyên**: trong ứng dụng đa tenant, cả quyền chung và phạm vi dữ liệu cần được áp dụng ở nơi có dữ liệu đúng.
13. **Viết provider tùy chỉnh cho cả nghiệp vụ**: `AuthenticationProvider` không phải lớp quyết định giảm giá, tồn kho hay trạng thái hợp đồng.

## 10. Bài tập vận dụng

1. Người dùng chưa gửi HTTP Basic credential gọi `GET /orders/A-100/quote`. Đường xử lý nào trả lỗi và mã gì?
2. `bob` có `ROLE_USER` nhưng truy cập đơn của `alice`. Vì sao kiểm tra `authenticated()` ở tầng HTTP vẫn cho đi tiếp, còn `@PreAuthorize` từ chối?
3. `admin` có quyền xem `B-200` nhưng yêu cầu giảm 10%. Vì sao hệ thống vẫn trả 409?
4. Nếu di chuyển quy tắc “đã giao thì không giảm” vào `OrderAccess.isOwner`, thiết kế sẽ có vấn đề gì?
5. Nếu chuyển từ HTTP Basic sang Bearer JWT nhưng giữ cùng chính sách owner/admin và tính giá, lớp nào nên thay đổi nhiều nhất?
6. Nếu một method trong `QuoteService` gọi `this.calculate(...)`, có chắc `@PreAuthorize` được áp dụng không? Cần kiểm chứng ở đâu?
7. Với một thao tác thanh toán có ghi database, chỉ `@PreAuthorize` kiểm tra owner trước transaction có đủ an toàn khi ownership thay đổi đồng thời không?
8. Trong danh sách status 401, 403, 400, 404, 409, hãy ghép status với từng trách nhiệm và giải thích tại sao một status không luôn tương ứng duy nhất một loại Java exception.

**Gợi ý:** (1) authentication entry point, thường 401 với Basic; (2) request-level chỉ biết đã đăng nhập, method-level biết resource; (3) authorization không xóa bỏ domain rule; (4) lẫn policy và invariant; (5) authentication filter/provider/decoder, còn domain nên giữ nguyên; (6) self-invocation có thể bypass proxy, cần integration test; (7) cần transaction/locking/database condition phù hợp; (8) phân biệt nguyên nhân và lớp xử lý, không suy status từ tên exception một cách máy móc.

## Nguồn tham khảo chính thức

- [Spring Security 6.5 — Servlet Architecture, SecurityFilterChain và ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Method Security, @EnableMethodSecurity và @PreAuthorize](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — In-Memory Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/in-memory.html)
- [Spring Security 6.5 — Password Storage và PasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)