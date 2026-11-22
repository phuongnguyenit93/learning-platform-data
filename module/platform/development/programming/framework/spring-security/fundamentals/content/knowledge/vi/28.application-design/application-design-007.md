# Lập bảng endpoint công khai, endpoint được bảo vệ và thao tác nhạy cảm

> **Ngữ cảnh:** thiết kế ứng dụng REST bằng **Java 17+, Spring Boot 3.x, Spring Security 6.x (Servlet/Spring MVC)**. Trọng tâm là biến danh sách API thực tế thành **ma trận endpoint có chính sách bảo vệ kiểm chứng được**: endpoint nào thật sự công khai, endpoint nào cần đăng nhập, ai được tác động lên dữ liệu nào và thao tác nào đòi hỏi lớp bảo vệ bổ sung vì rủi ro cao. Bảng endpoint phải được đối chiếu với cả `SecurityFilterChain`, method security, chính sách dữ liệu và kiểm thử, không được xem là một tài liệu trang trí.

## 1. Vì sao phải lập bảng trước khi viết cấu hình bảo mật?

Ứng dụng phát triển dần thường có rất nhiều route: API đọc danh mục, xem hồ sơ, cập nhật đơn hàng, quản trị, đăng ký, đổi mật khẩu, nhận webhook, upload file và tạo báo cáo. Nếu chỉ cấu hình những URL mà lập trình viên “nhớ là cần bảo vệ”, một endpoint mới có thể vô tình thừa hưởng `permitAll` hoặc được phép truy cập chỉ vì “đã đăng nhập” nhưng không được kiểm tra quyền sở hữu tài nguyên.

Ví dụ, hai endpoint đều yêu cầu đăng nhập:

- `GET /api/orders/o-1`: xem dữ liệu đơn hàng; người dùng thường chỉ được xem **đơn của mình**.
- `DELETE /api/admin/orders/o-1`: xóa đơn; đây là thao tác **nhạy cảm** vì làm mất dữ liệu, có thể cần vai trò admin, kiểm toán và phê duyệt.

Một điều kiện `anyRequest().authenticated()` có thể chặn anonymous, nhưng **chưa phân biệt được quyền xem của chủ đơn với quyền xóa của admin**. Ngược lại, `permitAll()` chỉ cho phép không cần identity, **không nói rằng endpoint không nhạy cảm**: yêu cầu đặt lại mật khẩu hay webhook có thể công khai ở ranh giới HTTP nhưng vẫn đòi hạn chế abuse hoặc kiểm chứng chữ ký.

**Mục tiêu học tập:** bạn sẽ biết thu thập danh sách endpoint, phân loại rủi ro, quyết định actor và chính sách dữ liệu, chuyển ma trận thành cấu hình Spring Security, bảo vệ theo object ở service, áp dụng CSRF khi phù hợp, dùng kiểm thử positive/negative để chống lộ endpoint và duy trì bảng khi API thay đổi.

## 2. Ba trục phân loại cần tách biệt

### Trục A — Ai được đi qua ranh giới authentication?

| Nhãn đề xuất | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **PUBLIC** | Không cần phiên/user login để gọi chức năng | `GET /catalog`; `POST /auth/password-reset/request` |
| **AUTHENTICATED** | Phải có `Authentication` của user hợp lệ | `GET /api/me` |
| **ROLE / AUTHORITY** | Ngoài đăng nhập, cần role/scope/permission được chỉ định | `DELETE /api/admin/orders/{orderId}` cần `ROLE_ADMIN` |
| **RESOURCE-SCOPED** | Cần kiểm tra quyền trên **đối tượng** cụ thể như chủ đơn, tenant, phòng ban | `GET /api/orders/{orderId}` chỉ owner hoặc admin |
| **MACHINE / WEBHOOK** | Thường không có user-session, nhưng phải xác minh chữ ký/token/mTLS hoặc trust boundary | `POST /webhooks/payment` |

Một endpoint có thể đồng thời thuộc các chính sách kết hợp, ví dụ AUTHENTICATED + RESOURCE-SCOPED + tenant constraint. Với API dùng JWT, có thể dùng scope `SCOPE_orders.read` thay vì role; đừng đánh đồng `hasRole("ADMIN")` với `hasAuthority("SCOPE_admin")`.

### Trục B — Chức năng nhạy cảm đến mức nào?

Độ nhạy cảm phụ thuộc **hậu quả khi bị lạm dụng**, không chỉ HTTP method:

- **Thấp:** đọc dữ liệu công khai không ảnh hưởng trạng thái; vẫn cần giới hạn tải hợp lý.
- **Trung bình:** đọc hoặc chỉnh dữ liệu cá nhân của chính mình, xem thông tin nghiệp vụ nội bộ.
- **Cao:** thay đổi quyền, xuất dữ liệu hàng loạt, hủy/xóa giao dịch, hoàn tiền, thay mật khẩu, thay email hoặc khóa tài khoản.
- **Rất cao / đặc quyền:** quản lý khóa xác thực, secret, cấp quyền quản trị, thanh toán hoặc xóa dữ liệu lớn; thường cần step-up MFA, phê duyệt nhiều người, giới hạn phạm vi, audit và rollback khi phù hợp.

**PUBLIC không đồng nghĩa LOW RISK.** `POST /auth/password-reset/request` có thể bị lạm dụng để spam hoặc dò account dù không yêu cầu login. `POST /webhooks/provider` có thể không có cookie nhưng phải xác minh request từ nguồn hợp lệ và chống replay. Tên “public” trên bảng phải đi kèm một cột **biện pháp bảo vệ bổ sung**.

### Trục C — Thao tác có tác dụng phụ không?

- `GET`/`HEAD` thường dùng cho đọc, không tạo thay đổi trạng thái nghiệp vụ. Chúng vẫn có thể trả dữ liệu nhạy cảm.
- `POST`/`PUT`/`PATCH`/`DELETE` thường có tác dụng phụ; ngoài phân quyền cần xác định **CSRF** theo mô hình cookie/browser, kiểm tra đầu vào, idempotency, chống replay, transaction, audit.
- Không suy “POST luôn nhạy cảm” hoặc “GET luôn an toàn”. `GET /admin/export?all=true` có thể trả dữ liệu rất nhạy cảm; `POST /search` có thể chỉ đọc nhưng vẫn có chi phí/abuse. Cách thiết kế nên phản ánh semantics và policy thực sự.
- Không vô tình thực hiện thay đổi trạng thái bằng `GET` vì preload, crawler, cache, link preview hoặc CSRF assumptions có thể khiến hành động chạy ngoài ý muốn.

## 3. Mẫu bảng inventory nên có những cột nào?

Mỗi dòng phải mô tả **một tổ hợp HTTP method + đường dẫn + chức năng**, không chỉ một prefix mơ hồ. Một mẫu hữu ích:

| Cột | Ý nghĩa / câu hỏi |
| --- | --- |
| **Method + path** | `GET /api/orders/{orderId}`, khác `POST /api/orders/{orderId}/cancel` |
| **Mục đích** | Người dùng làm được gì, side effect cụ thể là gì? |
| **Công khai?** | PUBLIC, cần đăng nhập, máy-máy, hoặc cần role |
| **Principal / authority** | Ai có thể gọi? `ROLE_ADMIN`, `SCOPE_orders.read`, service identity nào? |
| **Ràng buộc đối tượng** | Owner/tenant/đơn vị, quan hệ được ủy quyền, trạng thái tài khoản? |
| **Độ nhạy cảm** | LOW / MEDIUM / HIGH / CRITICAL + lý do |
| **Dữ liệu vào/ra** | PII, dữ liệu tiền, token; giới hạn phân trang, file, trường output |
| **Tác dụng phụ** | Có ghi database, gửi email, chạy job, tạo file hay thay quyền không? |
| **CSRF / replay / idempotency** | Browser cookie có CSRF? Request có cần idempotency key hoặc chống replay? |
| **Abuse controls** | Rate limit, quota, CAPTCHA/challenge, audit event, MFA/step-up |
| **Tầng enforcement** | Request matcher, `@PreAuthorize`, policy service, SQL query, gateway |
| **Bằng chứng kiểm thử** | Anonymous, sai quyền, đúng quyền, cross-tenant, CSRF, bất biến nghiệp vụ |
| **Owner và tình trạng review** | Nhóm sở hữu endpoint, ngày review, lý do thay đổi policy |

Không nhất thiết mỗi dự án phải có mọi cột trên một bảng ngang rất rộng: có thể dùng bảng tổng hợp và policy sheet/phụ lục riêng. Nhưng **phải lưu được quyết định**, người chịu trách nhiệm và cách test. Hai endpoint cùng path nhưng khác method có thể có rủi ro khác hẳn nhau, nên không gộp.

## 4. Ví dụ lập bảng trước khi triển khai

Bối cảnh: ứng dụng bán hàng có người dùng `alice`/`bob`, quản trị viên `admin` và hai đơn hàng mẫu. Đây là **ma trận thiết kế** gồm cả endpoint được code trong ví dụ và endpoint minh họa cho tương lai.

### 4.1. Endpoint sẽ triển khai trong mã ở mục 6

| Method & endpoint | Mức tiếp cận | Phân quyền trên tài nguyên | Nhạy cảm / tác dụng phụ | Bổ sung / phép thử chính |
| --- | --- | --- | --- | --- |
| `GET /catalog` | PUBLIC | Không cần user | LOW, chỉ đọc danh mục công khai | Anonymous 200; không trả thông tin riêng |
| `GET /api/me` | AUTHENTICATED | Chỉ trả danh tính của **request hiện tại** | MEDIUM, dữ liệu cá nhân tối thiểu | Anonymous 401; user 200 |
| `GET /api/orders/{orderId}` | AUTHENTICATED | **Owner hoặc ADMIN** tại service | HIGH, đọc đơn riêng/PII | Bob không đọc đơn Alice (403); Alice 200 |
| `POST /api/orders/{orderId}/cancel` | AUTHENTICATED | **Owner hoặc ADMIN** tại service | HIGH, chuyển trạng thái đơn | Kiểm tra CSRF, trạng thái OPEN, audit, transaction khi production |
| `DELETE /api/admin/orders/{orderId}` | `ROLE_ADMIN` ở HTTP **và** service | Admin cho phép, nhưng vẫn kiểm tra trạng thái/dữ liệu | HIGH/CRITICAL, xóa bản ghi | 403 cho user, 204 cho admin; audit/approval/soft-delete ở production |
| **Tất cả method/path khác** | DENY BY DEFAULT | Không áp dụng | Không tự động mở thêm API | Authenticated caller cũng bị từ chối |

**Lưu ý quan trọng:** hàng `GET /api/orders/{orderId}` yêu cầu đăng nhập ở `SecurityFilterChain`, nhưng **kiểm tra owner/tenant** được làm ở service. Nếu chỉ viết `authenticated()` mà không có kiểm tra object, user B có thể thử ID đơn của user A (BOLA/IDOR). Row policy là một phần của chính sách bảo mật, không phải một tùy chọn “nếu có thời gian”.

### 4.2. Các endpoint không triển khai trong mã demo nhưng cần có trong bảng thật

| Method & endpoint dự kiến | Vì sao cần chú ý? | Chính sách đề xuất |
| --- | --- | --- |
| `POST /auth/password-reset/request` | Public nhưng có thể spam hoặc dò username | Thông báo công khai chung, rate limit theo nhiều chiều, OTP/reset token một lần, TTL, audit; không log token |
| `POST /auth/password-reset/confirm` | Không có session user nhưng có bằng chứng reset | Xác minh token ngẫu nhiên đủ mạnh, TTL, one-time use, chống replay, thay session/credential cần thiết |
| `POST /webhooks/payment` | Nhận request từ đối tác, không dùng session người dùng | Kiểm tra signature/mTLS theo hợp đồng, timestamp/replay window, idempotency, giới hạn body, audit; không mặc nhiên `permitAll` là đủ |
| `POST /api/admin/users/{id}/grant-role` | Thay quyền, hậu quả lan rộng | ADMIN + phân tách nhiệm vụ, step-up MFA/approval tùy rủi ro, audit bất biến, tránh tự cấp quyền quá mức |
| `GET /api/admin/exports` hoặc `POST /api/admin/exports` | Xuất dữ liệu hàng loạt dù chỉ “đọc” | Restrict scope, authorization từng dataset, rate/quota, watermark/audit, retention và bảo vệ file xuất |
| `POST /api/payments/refunds` | Hoàn tiền/đổi số dư | Role + hạn mức giao dịch + step-up/dual-control, idempotency key, chống replay, giao dịch và audit |
| `GET /actuator/health` | Thường dùng cho monitoring | Chỉ tiết lộ thông tin sức khỏe cần thiết; các actuator khác phải được đánh giá riêng |
| `/swagger-ui/**` và `/v3/api-docs/**` | Tài liệu API có thể phơi bày cấu trúc hệ thống | Quyết định công khai hay chỉ nội bộ, áp đúng security ở môi trường thực |
| `/ws/**`, GraphQL, gRPC, background jobs | Không phải mọi entrypoint là HTTP MVC controller | Inventory riêng cho handshake/subscription/operation, consumer message, actor và policy |

Những endpoint này là **gợi ý thiết kế**, **không tự xuất hiện** trong ứng dụng demo. Khi triển khai phải quyết định method/path thực, format dữ liệu, cơ chế xác thực, bảo mật ở gateway/service và test tương ứng.

## 5. Từ inventory thành quy tắc Spring Security

### 5.1. Bảo vệ HTTP theo method + path

Trong Spring Security 6, `HttpSecurity.authorizeHttpRequests(...)` khai báo các rule:

```java
.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/catalog").permitAll()
        .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
        .requestMatchers(HttpMethod.GET, "/api/orders/{orderId}")
                .authenticated()
        .requestMatchers(HttpMethod.POST,
                "/api/orders/{orderId}/cancel").authenticated()
        .requestMatchers(HttpMethod.DELETE,
                "/api/admin/orders/{orderId}").hasRole("ADMIN")
        .anyRequest().denyAll())
```

Đây là **mảnh cấu hình**; mã chạy đầy đủ ở mục 6. Một vài lưu ý bắt buộc:

- `requestMatchers(HttpMethod.GET, ...)` chỉ khớp **GET**, không mặc nhiên mở POST/DELETE cùng URL. Rule cụ thể nên đứng trước fallback.
- `hasRole("ADMIN")` yêu cầu authority `ROLE_ADMIN` theo prefix mặc định; `hasAuthority("SCOPE_orders.write")` sẽ kiểm tra chuỗi authority chính xác. Đừng tự thêm `ROLE_` khi gọi `hasRole`.
- `anyRequest().denyAll()` khiến các endpoint/method không được liệt kê không tự mở chỉ vì người gọi đăng nhập. Điều này tạo áp lực review/ cập nhật inventory khi có route mới.
- `permitAll()` là một **quyết định authorization**, không tắt mọi filter. Gửi HTTP Basic header sai ngay cả tới endpoint public có thể bị authentication filter từ chối trước khi đến `permitAll`.
- Nếu có **nhiều `SecurityFilterChain`**, thứ tự `@Order` + `securityMatcher` chọn chain trước, sau đó những `requestMatchers` bên trong **chain đã chọn** được xét. Một route không match chain nào có nguy cơ không được Spring Security bảo vệ, nên cần xem coverage tổng thể.
- Một bảng inventory hoàn chỉnh cần xem cả context path, servlet mapping, trailing slash, HTTP methods, CORS/preflight, dispatcher ERROR/FORWARD và endpoint do framework/actuator sinh ra khi liên quan.

### 5.2. Request-level chưa đủ cho owner/tenant

Rule `authenticated()` ở `GET /api/orders/{orderId}` chỉ kiểm tra đã có identity. Nó **không biết** đơn `o-1` thuộc Alice hay Bob. Cần method-level policy tại service hoặc ràng buộc dữ liệu được kiểm tra trong mọi đường gọi.

Với Spring Security 6, có thể bật `@EnableMethodSecurity` rồi dùng:

```java
@PreAuthorize("hasRole('ADMIN') or "
        + "@orderPolicy.isOwner(authentication, #orderId)")
public OrderView get(@P("orderId") String orderId) {
    return store.find(orderId).orElseThrow(OrderMissing::new);
}
```

Đây là mảnh mã minh họa trong `OrderService`; class và import đầy đủ nằm ở mục 6. `@P("orderId")` cung cấp tên tham số cho SpEL, tránh phụ thuộc hoàn toàn vào cờ compiler. `orderPolicy` trả về **quyết định truy cập**, không tin owner ID do client tự khai.

**Vấn đề quan trọng:** method security dùng proxy. Phải gọi method được bảo vệ qua Spring bean/proxy; tự gọi `this.get(...)` trong cùng instance có thể không chạy interceptor. Thêm test từ controller qua service để chứng minh policy được thực thi, đồng thời bảo vệ những lối gọi khác của service từ job/message listener theo nhu cầu.

### 5.3. Mức nhạy cảm cao cần nhiều hơn một role

Một endpoint xóa đơn dùng `hasRole("ADMIN")` mới là **cổng vào**. Hệ thống thật có thể còn cần:

- Admin phải thuộc tenant/đơn vị thích hợp; role toàn hệ thống không mặc nhiên áp dụng cho mọi tenant.
- Hành động giá trị cao cần step-up MFA, xác nhận lại danh tính hoặc phê duyệt của người khác.
- Quy định “không xóa đơn đã thanh toán” là **business rule**, không phải thay thế authorization.
- Audit event chứa actor, operation, resource ID đã được xử lý theo chính sách dữ liệu, kết quả, thời điểm và correlation ID; không log password/token.
- Soft delete, retention/legal hold, idempotency, transaction/locking khi ghi, khôi phục và phản hồi lỗi phù hợp.
- Giới hạn tần suất, phát hiện hành vi bất thường và cảnh báo lạm dụng.

**Ví dụ runnable chỉ minh họa role + method security + CSRF + một invariant đơn giản.** Nó **không** triển khai MFA, phê duyệt hai người, durable audit log hoặc persistence. Không đưa ứng dụng demo vào production chỉ vì test pass.

## 6. Ví dụ hoàn chỉnh Java 17+: ma trận -> code

### 6.1. Phụ thuộc

Tạo dự án Spring Boot 3.x với Java 17+ và Spring MVC. Trong `build.gradle` đã có plugin Spring Boot, thêm khối:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây là khối `dependencies`, **không phải toàn bộ file Gradle**. Ví dụ dùng `InMemoryUserDetailsManager` và `ConcurrentHashMap` để tránh phụ thuộc database. Mọi user/password và đơn hàng đều là dữ liệu học tập.

### 6.2. Mã ứng dụng chạy được trong một file

Tạo file **`src/main/java/demo/DemoApplication.java`**:

```java
package demo;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
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
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/catalog")
                                .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/me")
                                .authenticated()
                        .requestMatchers(HttpMethod.GET,
                                "/api/orders/{orderId}")
                                .authenticated()
                        .requestMatchers(HttpMethod.POST,
                                "/api/orders/{orderId}/cancel")
                                .authenticated()
                        .requestMatchers(HttpMethod.DELETE,
                                "/api/admin/orders/{orderId}")
                                .hasRole("ADMIN")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

enum OrderStatus {
    OPEN, SHIPPED, CANCELLED
}

record OrderView(String id, String owner, OrderStatus status) {
}

class OrderMissing extends RuntimeException {
}

class OrderConflict extends RuntimeException {
}

@Repository
class OrderStore {
    private final Map<String, OrderView> orders =
            new ConcurrentHashMap<>();

    OrderStore() {
        reset();
    }

    synchronized void reset() {
        orders.clear();
        orders.put("o-1", new OrderView(
                "o-1", "alice", OrderStatus.OPEN));
        orders.put("o-2", new OrderView(
                "o-2", "bob", OrderStatus.SHIPPED));
    }

    Optional<OrderView> find(String id) {
        return Optional.ofNullable(orders.get(id));
    }

    synchronized OrderView cancel(String id) {
        OrderView order = orders.get(id);
        if (order == null) {
            throw new OrderMissing();
        }
        if (order.status() != OrderStatus.OPEN) {
            throw new OrderConflict();
        }
        OrderView changed = new OrderView(
                order.id(), order.owner(), OrderStatus.CANCELLED);
        orders.put(id, changed);
        return changed;
    }

    synchronized void delete(String id) {
        if (orders.remove(id) == null) {
            throw new OrderMissing();
        }
    }
}

@Component("orderPolicy")
class OrderPolicy {
    private final OrderStore store;

    OrderPolicy(OrderStore store) {
        this.store = store;
    }

    public boolean isOwner(Authentication authentication, String orderId) {
        return authentication != null
                && store.find(orderId)
                        .map(order ->
                                order.owner().equals(authentication.getName()))
                        .orElse(false);
    }
}

@Service
class OrderService {
    private final OrderStore store;

    OrderService(OrderStore store) {
        this.store = store;
    }

    @PreAuthorize("hasRole('ADMIN') or "
            + "@orderPolicy.isOwner(authentication, #orderId)")
    public OrderView get(@P("orderId") String orderId) {
        return store.find(orderId).orElseThrow(OrderMissing::new);
    }

    @PreAuthorize("hasRole('ADMIN') or "
            + "@orderPolicy.isOwner(authentication, #orderId)")
    public OrderView cancel(@P("orderId") String orderId) {
        return store.cancel(orderId);
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void delete(@P("orderId") String orderId) {
        store.delete(orderId);
    }
}

@RestController
class DemoController {
    private final OrderService orderService;

    DemoController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/catalog")
    public String catalog() {
        return "public-catalog";
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/api/orders/{orderId}")
    public OrderView get(@PathVariable String orderId) {
        return orderService.get(orderId);
    }

    @PostMapping("/api/orders/{orderId}/cancel")
    public OrderView cancel(@PathVariable String orderId) {
        return orderService.cancel(orderId);
    }

    @DeleteMapping("/api/admin/orders/{orderId}")
    public ResponseEntity<Void> delete(@PathVariable String orderId) {
        orderService.delete(orderId);
        return ResponseEntity.noContent().build();
    }
}

@RestControllerAdvice
class ApiErrors {
    @ExceptionHandler(OrderMissing.class)
    ResponseEntity<Map<String, String>> notFound() {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("code", "order_not_found"));
    }

    @ExceptionHandler(OrderConflict.class)
    ResponseEntity<Map<String, String>> conflict() {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(Map.of("code", "invalid_order_state"));
    }
}
```

**Kiểm tra tính runnable:** chỉ `DemoApplication` là lớp `public`; các class/enum/record khác cùng package `demo` và không khai báo `public`. Spring Boot quét `@Configuration`, `@Repository`, `@Component`, `@Service` và `@RestController` bên dưới package demo. `record`, `ConcurrentHashMap` và cú pháp Java phù hợp Java 17. Tất cả endpoint dùng `HttpMethod` và các annotation Spring MVC có đầy đủ import trong file.

### 6.3. Vai trò của từng lớp đối chiếu với bảng

**`SecurityConfig`** quyết định mức bảo vệ ban đầu theo HTTP method + path:

- `GET /catalog` được `permitAll`.
- `GET /api/me` và các route đơn hàng của user bắt buộc có identity.
- `DELETE /api/admin/orders/{orderId}` yêu cầu role admin ở URL.
- Các đường dẫn không được inventory liệt kê rơi vào `denyAll`.

**`OrderPolicy` và `OrderService`** quyết định quyền theo object:

- `OrderPolicy.isOwner(...)` tra owner từ dữ liệu phía server. Client không thể tự gửi owner khác để chiếm quyền.
- `@PreAuthorize` cho phép admin **hoặc** owner ở hai method get/cancel, và chỉ admin ở delete. Nếu người dùng gọi trực tiếp service qua đường xử lý khác, chính sách method vẫn có tác dụng khi lời gọi đi qua Spring-managed proxy.
- `OrderStore.cancel(...)` bảo vệ invariant `OPEN -> CANCELLED`. Đơn `SHIPPED` không được hủy bằng operation này: trả 409, kể cả khi owner/admin có quyền gọi.
- `OrderStore.delete(...)` thực sự xóa khỏi bộ nhớ để minh họa tác dụng phụ; **không** đại diện cho một thiết kế xóa dữ liệu production. Thực tế cần kiểm toán, phục hồi/soft delete, transaction/locking và kiểm tra domain/retention.

**`DemoController`** chỉ chuyển request vào service và trả dữ liệu cần thiết. **`ApiErrors`** ánh xạ lỗi domain (404/409), không bắt toàn bộ `AccessDeniedException` hay `AuthenticationException` để sửa status của security filters.

**Bảo vệ CSRF:** cấu hình giữ mặc định Spring Security, không có `csrf.disable()`. Với unsafe HTTP methods như POST/DELETE, kiểm thử phải gửi CSRF token qua helper. HTTP Basic ở môi trường browser vẫn có thể liên quan CSRF; quyết định tắt/giữ cho một API machine-to-machine stateless cần đánh giá mô hình credential và trust boundary riêng. Không dùng một dòng cấu hình “tắt hết CSRF để curl chạy” làm hướng dẫn mặc định.

## 7. Kiểm thử từ bảng: mỗi hàng đều có positive + negative

### 7.1. Chuẩn bị tests

Tạo **`src/test/java/demo/EndpointInventoryTest.java`**. Dùng `spring-boot-starter-test` và `spring-security-test` đã khai báo.

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class EndpointInventoryTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    OrderStore store;

    @BeforeEach
    void resetData() {
        store.reset();
    }

    @Test
    void catalogIsPublic() throws Exception {
        mvc.perform(get("/catalog"))
                .andExpect(status().isOk())
                .andExpect(content().string("public-catalog"));
    }

    @Test
    void profileRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongCredentialsCannotReadProfile() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "wrong-pass")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUserCanReadOwnProfile() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void ownerCanReadOwnOrder() throws Exception {
        mvc.perform(get("/api/orders/o-1")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("alice"))
                .andExpect(jsonPath("$.status").value("OPEN"));
    }

    @Test
    void otherUserCannotReadOrderByGuessingId() throws Exception {
        mvc.perform(get("/api/orders/o-1")
                        .with(httpBasic("bob", "bob-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadOrderWhenPolicyAllows() throws Exception {
        mvc.perform(get("/api/orders/o-1")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    void stateChangeWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/orders/o-1/cancel")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void ownerCanCancelOpenOrderWithCsrf() throws Exception {
        mvc.perform(post("/api/orders/o-1/cancel")
                        .with(httpBasic("alice", "alice-pass"))
                        .with(csrf()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("CANCELLED"));
    }

    @Test
    void otherUserCannotCancelOrderEvenWithCsrf() throws Exception {
        mvc.perform(post("/api/orders/o-1/cancel")
                        .with(httpBasic("bob", "bob-pass"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void ownerCannotCancelShippedOrder() throws Exception {
        mvc.perform(post("/api/orders/o-2/cancel")
                        .with(httpBasic("bob", "bob-pass"))
                        .with(csrf()))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code")
                        .value("invalid_order_state"));
    }

    @Test
    void normalUserCannotUseAdminDelete() throws Exception {
        mvc.perform(delete("/api/admin/orders/o-1")
                        .with(httpBasic("alice", "alice-pass"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanDeleteOrderWithCsrf() throws Exception {
        mvc.perform(delete("/api/admin/orders/o-1")
                        .with(httpBasic("admin", "admin-pass"))
                        .with(csrf()))
                .andExpect(status().isNoContent());

        mvc.perform(get("/api/orders/o-1")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isNotFound());
    }

    @Test
    void unknownEndpointIsDeniedEvenWhenAuthenticated()
            throws Exception {
        mvc.perform(get("/unlisted")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden());
    }
}
```

Đây là **một test class đầy đủ**. `@BeforeEach` đặt lại dữ liệu để các test POST/DELETE không làm kết quả của test kế tiếp phụ thuộc thứ tự. Đây là reset trong bộ nhớ demo, không phải chiến lược giao dịch cho database production. Nếu dự án chạy test song song và dùng chung application context, cần cô lập storage/context phù hợp thay vì dựa vào reset global.

Chạy các test bằng Gradle Wrapper:

```bash
./gradlew test
```

Chạy riêng class:

```bash
./gradlew test --tests demo.EndpointInventoryTest
```

Trên PowerShell:

```powershell
.\gradlew.bat test --tests demo.EndpointInventoryTest
```

Không có stdout cố định vì Gradle/JUnit có thể hiển thị khác nhau; với **đúng code và dependencies**, kết quả kỳ vọng là toàn bộ assertions pass.

### 7.2. Đối chiếu coverage với từng dòng inventory

| Dòng inventory | Test cho phép | Test từ chối / edge case |
| --- | --- | --- |
| `GET /catalog` | `catalogIsPublic` | Đảm bảo body không chứa dữ liệu riêng; thử method khác nếu cần |
| `GET /api/me` | `authenticatedUserCanReadOwnProfile` | `profileRequiresAuthentication`, `wrongCredentialsCannotReadProfile` |
| `GET /api/orders/{orderId}` | `ownerCanReadOwnOrder`, `adminCanReadOrderWhenPolicyAllows` | `otherUserCannotReadOrderByGuessingId` |
| `POST /api/orders/{orderId}/cancel` | `ownerCanCancelOpenOrderWithCsrf` | Thiếu CSRF, sai owner, trạng thái `SHIPPED` |
| `DELETE /api/admin/orders/{orderId}` | `adminCanDeleteOrderWithCsrf` | `normalUserCannotUseAdminDelete` |
| `anyRequest().denyAll()` | Không cần positive case cho fallback | `unknownEndpointIsDeniedEvenWhenAuthenticated` |

**Phải kiểm tra cả quyền theo đối tượng**: nếu chỉ test admin có quyền và anonymous không có quyền, có thể bỏ sót lỗi người dùng A đọc đơn của B. Bài test IDOR/BOLA rất quan trọng cho các hệ thống có tài nguyên gắn owner/tenant.

**Phải kiểm tra CSRF riêng**: `stateChangeWithoutCsrfIsRejected` cho thấy request bị chặn dù user có credential đúng; `ownerCanCancelOpenOrderWithCsrf` là đối chứng chứng minh logic nghiệp vụ vẫn chạy khi token hợp lệ. HTTP 403 do CSRF **không chứng minh** role hay object policy đã từ chối.

**Không mặc định sử dụng `@WithMockUser` để kiểm tra password**: nó giúp kiểm tra authorization nhưng không chạy luồng kiểm tra credential thực. Ví dụ dùng `httpBasic(...)` đi qua HTTP Basic authentication filter; cần test riêng login/password khi cơ chế xác thực thay đổi.

## 8. Đọc ma trận ra HTTP behavior

Trong ví dụ, các phản hồi dự kiến:

| Request | HTTP | Vì sao? |
| --- | --- | --- |
| Anonymous `GET /catalog` | 200 | PUBLIC |
| Anonymous `GET /api/me` | 401 | HTTP Basic yêu cầu đăng nhập |
| Alice sai mật khẩu `GET /api/me` | 401 | Authentication thất bại |
| Alice đúng mật khẩu `GET /api/me` | 200 | Authenticated |
| Alice `GET /api/orders/o-1` | 200 | Owner |
| Bob `GET /api/orders/o-1` | 403 | Đã xác thực, thiếu quyền trên resource |
| Admin `GET /api/orders/o-1` | 200 | Policy cho phép admin |
| Alice `POST /api/orders/o-1/cancel` **thiếu CSRF** | 403 | `CsrfFilter` từ chối trước khi gọi service |
| Alice `POST .../cancel` **có CSRF** | 200 | Owner + OPEN -> CANCELLED |
| Bob `POST /api/orders/o-1/cancel` có CSRF | 403 | Không phải owner |
| Bob `POST /api/orders/o-2/cancel` có CSRF | 409 | Có quyền, nhưng đơn `SHIPPED` |
| Alice `DELETE /api/admin/orders/o-1` có CSRF | 403 | Thiếu `ROLE_ADMIN` |
| Admin `DELETE /api/admin/orders/o-1` có CSRF | 204 | Được phép, xóa bản ghi demo |
| Alice `GET /unlisted` | 403 | Fallback denyAll |

Mã 401/403 ở đây là **kỳ vọng với HTTP Basic và cấu hình minh họa**. Với form login, anonymous có thể redirect tới `/login` thay vì 401; JWT/Bearer có challenge khác. Các handler/tùy biến có thể đổi HTTP response. Đừng lấy một status code làm lý do duy nhất để phân loại loại lỗi: 403 có thể do CSRF hoặc authorization, 409 thường phản ánh domain conflict.

### 8.1. Thử nhanh những GET bằng curl

Sau khi chạy:

```bash
./gradlew bootRun
```

Mặc định ứng dụng ở `http://localhost:8080` nếu chưa đổi cổng.

```bash
curl -i http://localhost:8080/catalog
curl -i http://localhost:8080/api/me
curl -i -u alice:alice-pass http://localhost:8080/api/me
curl -i -u alice:alice-pass http://localhost:8080/api/orders/o-1
curl -i -u bob:bob-pass http://localhost:8080/api/orders/o-1
curl -i -u admin:admin-pass http://localhost:8080/api/orders/o-1
```

Trên PowerShell dùng `curl.exe` nếu `curl` là alias của `Invoke-WebRequest`. **Không kỳ vọng POST/DELETE bằng curl chỉ có Basic credential sẽ thành công:** trong ví dụ còn yêu cầu CSRF token, nên các thao tác đó được thử qua MockMvc `.with(csrf())`. Với giao diện/browser thực, tích hợp CSRF token đúng cơ chế; với API machine-to-machine dùng token không tự được browser gửi, chính sách CSRF có thể khác sau khi phân tích threat model, không tắt tùy tiện.

## 9. Quy trình tạo và bảo trì ma trận trên dự án thật

### Bước 1 — Thu thập endpoint từ nhiều nguồn

- Mã Spring MVC: `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping`, `@DeleteMapping`, `@RequestMapping` ở cả class và method; nhớ kết hợp prefix của controller.
- `RequestMappingHandlerMapping` hoặc Spring Actuator mappings khi được bật và bảo vệ phù hợp; đối chiếu với OpenAPI/Swagger, gateway routes, reverse proxy, servlet mappings.
- Spring Security `SecurityFilterChain`, `securityMatcher`, `requestMatchers`, method security, custom `AuthorizationManager`, role/scope policy.
- Các đầu vào ngoài MVC: GraphQL, gRPC, WebSocket, webhook handlers, scheduled jobs, message consumers, file uploads/downloads, static files, monitoring endpoints.

Đừng chỉ lấy OpenAPI làm nguồn tuyệt đối: một endpoint có thể tồn tại trong code nhưng chưa được mô tả ở tài liệu. Ngược lại, tài liệu có thể còn route cũ đã xóa. Bảng chính thức nên có **quy trình đối chiếu liên tục** với routing/runtime.

### Bước 2 — Phân loại dữ liệu và tác dụng phụ

Với mỗi method + path, ghi dữ liệu được đọc/ghi, ai sở hữu, mức nhạy cảm, hệ thống bên ngoài bị tác động (email, thanh toán, export, job), quyền cấp trên có thể bỏ qua gì và invariant nào **không được bỏ qua**. Phân biệt thao tác “xem giao dịch” với “hoàn tiền” dù cùng `/payments/{id}`.

### Bước 3 — Mô hình principal và phạm vi quyền

Xác định actor: anonymous, end user, admin theo tenant, support, system client. Định nghĩa role/scope/permission và **resource ownership**. Kiểm tra quan hệ chia sẻ, ủy quyền thay mặt, data scoping theo tenant, account trạng thái khóa hoặc suspended. Không lấy tenantId/ownerId do client gửi làm sự thật khi principal đã xác minh cho biết phạm vi khác.

### Bước 4 — Dựng cơ chế bảo vệ theo tầng

1. `SecurityFilterChain`: chọn authentication mechanism, áp request-level method/path policy, deny by default và CSRF/CORS/session theo kiến trúc.
2. Method/Service: object/tenant authorization, kiểm tra đúng Spring-managed proxy hoặc chính sách ở entrypoint service.
3. Domain: invariant về trạng thái, hạn mức, điều kiện giao dịch; không trộn mọi lỗi thành 403.
4. Data access: truy vấn đã lọc tenant/ownership khi phù hợp, parameterized SQL, transaction/locking để tránh TOCTOU.
5. Hạ tầng: rate limit, MFA/step-up, signature verification, audit logging, retention, secret handling và monitoring.

**Không có một annotation nào giải quyết toàn bộ các tầng.** Có `@PreAuthorize` không bảo đảm request body hợp lệ; có JWT không bảo đảm người gọi được xem mọi object; có CSRF không bảo đảm chống BOLA.

### Bước 5 — Thiết kế test từ ma trận, không test ngẫu hứng

Với mỗi dòng, tối thiểu ghi:

- **Positive:** actor hợp lệ với dữ liệu hợp lệ được phép.
- **Anonymous:** không credential; phải từ chối đúng khi endpoint private.
- **Wrong role/scope:** người đã đăng nhập nhưng thiếu authority.
- **Wrong owner/tenant:** có role tổng quát nhưng truy cập object của người khác.
- **Wrong HTTP method:** path đúng nhưng method không được liệt kê; phải fail-closed.
- **Invalid input/state:** request đã qua bảo mật nhưng vi phạm domain rule được trả lỗi đúng.
- **CSRF/replay:** trên unsafe endpoints có cơ chế cần thiết, thiếu token/chữ ký/idempotency bị từ chối.
- **Data minimization:** response không chứa field/tài liệu thừa; API public không rò PII.
- **Audit/abuse:** nhạy cảm cao có event, rate-limit, step-up hoặc approval theo chính sách.

Tự động hóa kiểm tra “có controller mapping mới nhưng chưa có row inventory” trong CI nếu hệ thống hỗ trợ. Không nhất thiết auto-generate toàn bộ policy từ một bảng thiếu ngữ nghĩa; bảng vẫn cần review của người hiểu rủi ro.

### Bước 6 — Review mỗi khi hệ thống thay đổi

Phải cập nhật bảng khi thêm endpoint, đổi HTTP method/path, mở role, đổi dữ liệu trả về, đổi owner/tenant rule, thêm client, thay gateway hoặc enable Actuator. Kiểm tra lại cả positive/negative tests trước release.

Trong code review, các thay đổi từ `denyAll` sang `permitAll`, từ role cụ thể sang `authenticated()` hoặc từ owner-scoped sang unrestricted data access cần được **đánh giá như thay đổi bảo mật**, không chỉ thay đổi cú pháp.

## 10. Những sai lầm cần tránh

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Chỉ ghi “`/api/**` — cần login” | Không biết endpoint nào chỉ dành admin hoặc chủ dữ liệu | Liệt kê method + path + object policy + sensitivity |
| Coi mọi `GET` là public | GET cũng có thể xuất PII, báo cáo, secret | Phân loại theo dữ liệu và actor, không theo method một mình |
| Coi `permitAll` = an toàn | Public reset/webhook vẫn có thể bị abuse | Rate limit, token/signature, chống replay, audit phù hợp |
| Mọi route private chỉ dùng `authenticated()` | User hợp lệ có thể đọc resource người khác | Kiểm tra owner/tenant ở service/data layer |
| Dùng `hasRole("ADMIN")` rồi bỏ domain validation | Admin vẫn có thể thao tác trên trạng thái không hợp lệ | Bảo vệ invariant tại service/domain |
| Ghép `/**.permitAll()` trước rule nhạy cảm | First matching authorization rule có thể mở mọi URL | Specific rules trước và `anyRequest().denyAll()` |
| Không có catch-all chain khi dùng nhiều `SecurityFilterChain` | Request không match chain có thể không được bảo vệ | Kiểm tra chain coverage và fallback an toàn |
| Thêm endpoint nhưng không có negative test | Mở quyền sai khó phát hiện | Duy trì test matrix trong CI |
| Test chỉ bằng `@WithMockUser` | Không chứng minh Basic/JWT/form login thực sự hoạt động | Test filter/manager bằng HTTP credentials/token |
| Quên CSRF khi POST/DELETE với browser | Request có thể bị giả mạo qua browser | Giữ CSRF hoặc thiết kế stateless token policy có đánh giá rủi ro |
| Đặt `@PreAuthorize` trên method được gọi bằng `this.method()` | Self-invocation có thể bỏ qua proxy | Tách service/proxy và kiểm thử integration |
| Chọn status 404 để “chắc chắn không lộ dữ liệu” mà vẫn để query lộ qua timing/body | Information disclosure vẫn có thể tồn tại | Thiết kế chính sách 403/404 thống nhất, hạn chế oracle |
| Không inventory Actuator/Swagger/webhook | Surface thực rộng hơn controller chính | Kiểm kê toàn bộ entrypoint đang bật |
| Ghi mật khẩu/token trong audit | Audit trở thành điểm rò rỉ dữ liệu | Ghi actor/action/result/code theo schema an toàn |
| Không quản lý owner/reviewer | Bảng nhanh chóng lỗi thời | Gắn ownership, PR/release gate, cập nhật tự động nếu phù hợp |

## 11. Câu hỏi thực hành và đáp án định hướng

1. `GET /catalog` và `POST /auth/password-reset/request` đều public. Chúng có cùng độ nhạy cảm không? Cần kiểm soát bổ sung gì cho chức năng reset?
2. Vì sao `GET /api/orders/{id}` chỉ có `authenticated()` là chưa đủ? Nếu Bob đoán ID của Alice, kiểm tra ở tầng nào?
3. `POST /api/orders/o-1/cancel` và `GET /api/orders/o-1` có thể có chính sách khác nhau như thế nào dù chung một tài nguyên?
4. Admin đã xác thực và có quyền gọi `DELETE` nhưng đơn đã thanh toán không được xóa theo policy sản phẩm. Đây là authorization hay business rule?
5. Vì sao một đường dẫn lạ không nên mặc định rơi vào `authenticated()` trong ứng dụng đòi kiểm soát chặt? `denyAll` giúp gì?
6. Nếu POST chuyển trạng thái không có CSRF token và trả 403, có thể khẳng định `@PreAuthorize` đã từ chối không?
7. Điều gì có thể xảy ra khi service method có `@PreAuthorize` nhưng bị gọi trực tiếp bằng `this.cancel(...)`?
8. API export không đổi database. Vì sao nó vẫn có thể là HIGH/CRITICAL?
9. Một webhook không dùng username/password có thật sự “không cần bảo vệ” chỉ vì được đánh dấu PUBLIC ở gateway không?
10. Nếu hệ thống có nhiều tenant, người dùng gửi `tenantId=other` trong request, server nên dựa trên dữ liệu nào để quyết định quyền?
11. Nêu ba negative tests ngoài “anonymous bị chặn” để phát hiện lỗi phân quyền ở endpoint hủy đơn.
12. Khi một developer thêm `PATCH /api/orders/{id}`, cần cập nhật những thành phần và bằng chứng nào trước khi release?
13. Khi API chỉ trả HTTP 401/403 nhưng không biết rule nào áp dụng, cần đối chiếu những thông tin gì?
14. Nếu dùng JWT scope thay vì user role, điều gì trong inventory cần thay đổi và điều gì vẫn giữ nguyên?

**Gợi ý trả lời:** (1) không, reset cần chống enumeration/rate limit/token TTL; (2) BOLA/IDOR, object policy; (3) GET chỉ đọc, POST có side effect + CSRF/domain; (4) domain invariant; (5) fail-closed cho route chưa review; (6) không, `CsrfFilter` có thể chặn trước; (7) self-invocation bypass proxy; (8) rủi ro rò dữ liệu lớn; (9) cần ký request và chống replay; (10) principal/tenant binding tin cậy; (11) wrong owner, wrong role, missing CSRF, invalid state; (12) policy, owner/tenant, CSRF, validation, test matrix, audit; (13) chain matcher, filter, authentication và authorization rule; (14) scope syntax đổi, resource ownership và phân loại rủi ro vẫn cần.

## Tài liệu chính thức và bảo mật

- [Spring Security 6.5 — Authorize HTTP Requests: method/path matcher, denyAll, permitAll](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Method Security: @EnableMethodSecurity và @PreAuthorize](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — Multiple SecurityFilterChain, securityMatcher](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — MockMvc CSRF Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)