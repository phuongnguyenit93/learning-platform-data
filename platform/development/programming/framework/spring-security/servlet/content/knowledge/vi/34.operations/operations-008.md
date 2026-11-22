# Giới hạn thử đăng nhập, chống dò tài khoản và phối hợp với hạ tầng

**Ngữ cảnh:** Vận hành và bảo vệ ứng dụng **Spring Security Servlet/Spring MVC**, Java 17+, Spring Boot 3.x, Spring Security 6.x. Chủ đề không chỉ là “cho phép tối đa N lần nhập sai mật khẩu”: một hệ thống phải phân biệt brute force, password spraying, credential stuffing, **dò tài khoản (account enumeration)**, áp dụng giới hạn ở nhiều lớp, tránh vô tình khóa người dùng hợp lệ, và đo lường/ứng phó khi traffic đi qua CDN, WAF, reverse proxy, API gateway hoặc Identity Provider (IdP).

Các giá trị limit trong ví dụ là **giả định dành cho học tập**, không phải ngưỡng khuyến nghị cố định cho mọi tổ chức. Cấu hình thực tế cần dựa trên tần suất truy cập hợp lệ, loại tài khoản, quy mô NAT/mobile network, rủi ro tài khoản, chi phí thử nghiệm và telemetry.

## 1. Hiểu đúng các mối đe dọa

| Hành vi | Cách attacker thử | Vì sao chỉ giới hạn theo username hoặc IP chưa đủ |
| --- | --- | --- |
| **Brute force** | Thử rất nhiều mật khẩu cho một tài khoản. | Giới hạn chỉ IP có thể bị vượt bằng botnet; giới hạn chỉ account dễ bị lợi dụng để gây từ chối dịch vụ. |
| **Password spraying** | Thử một vài mật khẩu phổ biến trên rất nhiều tài khoản. | Mỗi account ít lần nên account-level threshold có thể không phát hiện; cần tín hiệu IP/ASN/campaign. |
| **Credential stuffing** | Dùng danh sách email:mật khẩu lộ từ hệ thống khác. | Mỗi cặp có thể chỉ thử một lần; cần thiết bị, hành vi, IP reputation, mật khẩu đã lộ và MFA/passkeys. |
| **Account enumeration** | Phân biệt username/email có tồn tại qua login, signup, reset, API. | Chặn nhiều request không tự xóa được sự khác nhau về status, body, thời gian xử lý và email side effects. |
| **Distributed low-and-slow** | Nhiều IP/máy, mỗi nguồn gửi ít request kéo dài. | Cần aggregation dài hạn, phát hiện bất thường và quản lý rủi ro theo danh tính/nguồn. |
| **Resource exhaustion** | Gửi nhiều request tốn CPU hashing, truy vấn DB hoặc gọi IdP. | Chặn quá muộn sau authentication sẽ không tiết kiệm đủ tài nguyên. |

**Phân biệt authentication với authorization:** login limiter giảm tốc độ **thử xác thực**; sau khi login, Spring Security vẫn phải kiểm tra authorities, ownership và tenant/resource boundaries. Rate limiting **không** biến một tài khoản hợp lệ thành “được phép làm tất cả”.

### 1.1 Những điểm dễ bị dò tài khoản

Dò tài khoản có thể xảy ra ở nhiều endpoint:

- `POST /login`: “Sai mật khẩu” so với “Không tồn tại tài khoản”.
- `POST /forgot-password`: “Đã gửi email” so với “Không có email này”.
- `POST /signup`: “Email đã được sử dụng”.
- `POST /mfa/verify` hoặc `/mfa/setup`: khác biệt giữa account có MFA/chưa có MFA.
- `POST /unlock-account`, gửi lại email xác minh, mời thành viên, liên kết OAuth2/OIDC.
- API hỏi người dùng hoặc endpoint kiểm tra username availability.
- Khác biệt **đo được**, không chỉ văn bản: HTTP status, redirect `Location`, header, response size, thời gian, số lần gửi mail, thông báo ngoài băng và cả cách limiter tăng counter.

Do đó cần chính sách **account-neutral** xuyên suốt các luồng nhạy cảm, nhưng không làm hỏng UX hợp pháp hay đưa ra lời khẳng định sai. Ví dụ endpoint quên mật khẩu có thể phản hồi “Nếu có tài khoản phù hợp, chúng tôi sẽ gửi hướng dẫn” dù email không tồn tại.

### 1.2 Một số lỗi ngược đời

- **Khóa tài khoản ngay sau ba lần sai** có thể giúp attacker cố tình khóa hàng nghìn tài khoản có thật (denial-of-service/lockout abuse).
- **Chỉ khóa theo IP** có thể chặn cả văn phòng, trường học hoặc mạng di động dùng chung NAT.
- **Chỉ khóa theo username** dễ bị spraying trên nhiều username.
- **Tin mọi `X-Forwarded-For`** cho phép attacker giả IP, bypass rate limit hoặc làm người khác bị khóa.
- **Trả 404 nếu không có tài khoản, 401 nếu sai mật khẩu** biến endpoint thành công cụ enumeration.
- **Test chỉ một instance** nhưng deploy nhiều replicas với bộ đếm local có thể khiến mỗi replica cấp một quota riêng.

## 2. Phòng thủ nhiều lớp, mỗi lớp làm đúng việc

```text
Internet / botnets / người dùng thật
             │
             ▼
CDN / edge / WAF / bot management
  - per-source request-rate & bot signals
  - IP/ASN/reputation, geo anomalies (nếu có chính sách)
  - traffic shaping, challenge khi phù hợp
             │ [trusted forwarding/trace headers]
             ▼
Ingress / Load Balancer / API Gateway
  - kết nối TLS, kích thước request, timeout
  - rate limit theo route/client và bảo vệ upstream
  - bỏ header nguồn giả, giới hạn request bursts
             │
             ▼
Spring Security Servlet app (nhiều replicas)
  - route-specific login attempt control
  - account + source + device/session risk signals
  - generic authentication-failure messages
  - MFA/passkeys/step-up, audit, metrics
             │
             ├── shared counter (Redis/DB phù hợp)
             │
             └── Identity Provider / User store
                   - verify password / SSO / MFA
                   - lock/recovery/risk policy chính thức
```

**Edge/WAF** nhìn được traffic rộng và giúp giảm CPU/DB load trước khi request tới Java. Nhưng edge không luôn biết account identity hoặc kết quả authentication đáng tin.

**Gateway/Ingress** điều tiết route, kết nối và tài nguyên. Gateway có thể áp dụng token bucket theo client/IP/path nhưng cũng có nguy cơ đánh đồng user sau NAT. Nó không thay thế kiểm tra account state và auth policy.

**Spring Security/ứng dụng** có ngữ nghĩa nghiệp vụ: username canonicalized, đăng nhập thất bại/thành công, MFA status, tenant, account sensitivity. Nó nên thực thi các quyết định phụ thuộc tài khoản và gửi telemetry đã kiểm soát.

**IdP** nếu thực hiện password authentication thì IdP là nơi trực tiếp quan sát failed credentials và có thể đã có lockout/risk protection. Khi ứng dụng là **OAuth2/OIDC Client**, backend Spring thường **không nhận mật khẩu người dùng**; rate limit theo `POST /login` của local form auth không bao phủ màn hình đăng nhập tại IdP.

**Bộ đếm dùng chung** đảm bảo các replicas cùng thấy quota. Nếu chọn một bộ đếm memory riêng trên mỗi node, limit tính theo toàn hệ thống gần như tăng theo số node hoặc có thể bị bypass qua load-balancing.

### 2.1 Đặt giới hạn ở đâu?

| Lớp | Key/signal phù hợp | Điểm mạnh | Rủi ro/cần lưu ý |
| --- | --- | --- | --- |
| CDN/WAF | IP, ASN, route, reputation, bot fingerprint | Bảo vệ sớm, quy mô lớn | False positive, privacy, nguồn IP sau proxy. |
| API gateway | Source, path, authenticated API client | Chống burst, bảo vệ upstream | Dùng chung IP/NAT; không đủ tín hiệu account. |
| App trước password hashing | Source + username canonicalized + risk | Giảm tốn CPU khi có burst | Dễ bị dùng gây account lockout nếu hard-block. |
| App sau AuthenticationFailure | Kết quả auth đáng tin + account/risk | Phân biệt success/failure, telemetry tốt | Hash/DB/IdP đã tốn chi phí; phải tránh lộ account existence. |
| IdP | User, network, MFA, compromised credentials | Chính sách đăng nhập tập trung | Cần phối hợp callback và UX; tránh áp limit trùng, xung đột. |
| Redis/shared store | Atomic counters, TTL, cross-node | Thống nhất nhiều replicas | Latency/outage, hot keys, vận hành/HA. |

Khuyến nghị thiết kế là **nhiều tín hiệu vừa phải** thay vì một hard lockout duy nhất, phối hợp giám sát và nâng mức xác thực khi cần. Không đặt quota thấp đến mức người thật bị loại hàng loạt bởi mạng chung.

## 3. Chọn khóa giới hạn: IP, tài khoản, kết hợp và hành vi

### 3.1 Theo IP

Ví dụ `ip:203.0.113.10` giới hạn tổng số request đăng nhập từ một nguồn trong một cửa sổ thời gian. Nó giảm burst đơn giản nhưng:

- Một địa chỉ IP có thể đại diện cho nhiều người dùng thật do NAT/VPN/carrier gateway.
- Botnet có thể dùng hàng nghìn IP.
- Client IP phía sau ingress có thể là **địa chỉ của proxy**, không phải người dùng.
- IPv6 có nhiều địa chỉ trong cùng mạng; chính sách tiền tố/aggregation phải được đánh giá để tránh trừng phạt sai.

IP nên được dùng cùng risk signals, không là định danh tài khoản.

### 3.2 Theo tài khoản (hoặc tên đăng nhập được khai báo)

Ví dụ `acct:HMAC(normalizedUsername)` quản lý mật độ thử mật khẩu cho cùng tên đăng nhập. Điều cần lưu ý:

- Dùng **cùng quy tắc canonicalization** với hệ thống user lookup. Nếu username phân biệt chữ hoa/thường mà limiter không phân biệt, hai user khác nhau có thể chung bucket; nếu hệ thống không phân biệt mà limiter phân biệt, attacker có thể đổi case để bypass.
- **Tạo bucket cho cả username không tồn tại**; nếu limiter chỉ tăng counter khi account có thật, response/rate behavior có thể tiết lộ sự tồn tại.
- Chặn cứng theo tên tài khoản cho phép attacker khiến victim không thể đăng nhập. Thay vì lockout vĩnh viễn, cân nhắc progressive delay, step-up, quota theo IP+account và cơ chế recovery hợp lý.
- Key theo tên đăng nhập thô (email/phone) lưu trong Redis hoặc log có thể làm lộ dữ liệu cá nhân; dùng key dạng **HMAC với secret** khi hệ thống cần hạn chế lộ PII. SHA-256 không khóa của email phổ biến vẫn có thể bị đoán qua dictionary.

### 3.3 Kết hợp nhiều chiều

Một mô hình thường theo dõi:

1. **Per-IP:** bảo vệ burst từ một nguồn (có kiểm soát NAT).
2. **Per-account:** bảo vệ một identity trước nhiều IP.
3. **Per-IP + account:** tìm các cặp lặp lại và tránh block cả IP nếu có vài user riêng biệt.
4. **Per-device/session:** hỗ trợ đánh giá rủi ro, nhưng client identifier có thể bị thay đổi/giả mạo.
5. **Global/campaign:** số lượng username khác nhau bị thử, tỷ lệ fail, ASN/reputation và cùng password-pattern theo chính sách riêng tư phù hợp (không lưu mật khẩu để “nhóm” raw secret).

Không dùng cookie device ID làm bằng chứng chắc chắn “đây là user” vì attacker có thể xóa/thay cookie. Fingerprinting có thể ảnh hưởng quyền riêng tư và độ chính xác; cân nhắc pháp lý/vận hành trước khi áp dụng.

### 3.4 Dữ liệu nào được phép ghi log?

Nên ghi các **sự kiện tổng hợp an toàn**: thời gian, loại auth flow, decision (allow/throttle/challenge), route, lý do phân loại, trace ID, IP/ASN đã được xử lý theo chính sách và account-key giả danh (pseudonymized) nếu cần.

**Không log** password, Authorization header, session cookie, reset token, OTP, client secret hoặc raw form body. Tránh ghi username/email thô vào dashboard phổ biến. Hạn chế quyền xem logs và thiết lập retention.

## 4. Cơ chế giới hạn: fixed window, sliding window và token bucket

| Thuật toán | Cách hoạt động | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| **Fixed window counter** | Tối đa N lần trong từng cửa sổ thời gian. | Dễ hiểu, rẻ, demo tốt. | Có burst ngay ranh giới cửa sổ: gần 2N trong thời gian ngắn. |
| **Sliding window** | Đếm sự kiện trong khoảng “T giây gần nhất” hoặc xấp xỉ. | Công bằng hơn theo thời gian thực. | Tốn bộ nhớ/logic phức tạp hơn. |
| **Token bucket** | N tokens, nạp lại theo tốc độ; mỗi request tiêu một token. | Cho burst hợp lý và giới hạn tốc độ trung bình. | Cần đồng bộ thời gian/counters và chọn quota cẩn thận. |
| **Leaky bucket/queue** | Xử lý ở tốc độ xác định hoặc từ chối khi đầy. | Làm mượt tải. | Xếp hàng quá lâu có thể làm login timeout. |
| **Progressive backoff** | Delay/challenge tăng theo rủi ro và thất bại. | Giảm brute force không khóa cứng ngay. | Cần UX, fairness, tính toán risk, tránh enumeration. |
| **Hard lockout** | Khóa account sau một số lần thất bại. | Có tác dụng trong một số môi trường rủi ro cao. | Có thể bị lạm dụng gây denial-of-service; phải có quy trình mở khóa. |

**Không có thuật toán nào tự giải quyết account enumeration.** Cần điều chỉnh response và luồng ứng dụng độc lập với quota.

**Không có threshold “chuẩn” cho tất cả:** ví dụ “5 lần/phút” chỉ để có kết quả test định lượng. Production phải đo legitimate error rate, tỷ lệ shared IP, số lần login trong giờ cao điểm, traffic của bot và phản ứng khi tăng false positives.

### 4.1 HTTP response khi bị chặn

Thông thường có thể dùng `429 Too Many Requests` và header `Retry-After` để client biết thử lại; ở đây 429 có nghĩa **đang điều tiết**, không tự tiết lộ account tồn tại hay không.

```http
HTTP/1.1 429 Too Many Requests
Content-Type: text/plain; charset=UTF-8
Retry-After: 60

Yêu cầu đang được giới hạn. Vui lòng thử lại sau.
```

Tránh cung cấp thông tin nhạy cảm kiểu “Tài khoản alice có 4 lần sai, còn 1 lần”. Với API login và UI, response body, cấu trúc, thông báo, chuyển hướng và retry behavior cần xem xét **account-neutral**. Header retry chính xác đến mili giây, khác nhau cho account có/không có, cũng có thể tạo side channel.

**Quan trọng:** 429 không thay thế 401/403. Khi request không chạm quota, kết quả auth sai có thể là 401 với API hoặc 302 tới trang login với Spring form login. Với browser login, 403 còn có thể là lỗi CSRF.

## 5. Java 17 độc lập: bộ đếm fixed-window có kiểm thử được

Trước khi tích hợp Spring Security, tạo một mô hình **Java SE chạy được** để hiểu concurrency và cửa sổ thời gian. Mã dùng `ConcurrentHashMap.compute` để thay đổi counter theo từng key một cách atomic trong cùng JVM, nhận thời điểm qua tham số để test không phụ thuộc đồng hồ.

**`src/main/java/com/example/limit/FixedWindowLimiter.java`**

```java
package com.example.limit;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

public final class FixedWindowLimiter {

    private record Window(long startMillis, int count) {}

    private final ConcurrentHashMap<String, Window> windows =
        new ConcurrentHashMap<>();
    private final int maxAttempts;
    private final long windowMillis;

    public FixedWindowLimiter(int maxAttempts, long windowMillis) {
        if (maxAttempts <= 0 || windowMillis <= 0) {
            throw new IllegalArgumentException("limits must be positive");
        }
        this.maxAttempts = maxAttempts;
        this.windowMillis = windowMillis;
    }

    public boolean tryAcquire(String key, long nowMillis) {
        AtomicBoolean allowed = new AtomicBoolean(false);

        windows.compute(key, (k, previous) -> {
            Window current = previous;
            if (current == null
                    || nowMillis < current.startMillis()
                    || nowMillis - current.startMillis() >= windowMillis) {
                current = new Window(nowMillis, 0);
            }

            if (current.count() >= maxAttempts) {
                return current;
            }

            allowed.set(true);
            return new Window(
                current.startMillis(),
                current.count() + 1
            );
        });

        return allowed.get();
    }

    public static void main(String[] args) {
        FixedWindowLimiter limiter =
            new FixedWindowLimiter(3, 60_000);

        for (int n = 1; n <= 4; n++) {
            System.out.println("alice-" + n + "=" +
                limiter.tryAcquire("acct:alice", 1_000));
        }

        System.out.println("bob=" +
            limiter.tryAcquire("acct:bob", 1_000));

        System.out.println("alice-new-window=" +
            limiter.tryAcquire("acct:alice", 61_000));
    }
}
```

Biên dịch từ thư mục gốc project với JDK 17+ (class này **không** phụ thuộc Spring):

```bash
javac -d out src/main/java/com/example/limit/FixedWindowLimiter.java
java -cp out com.example.limit.FixedWindowLimiter
```

**Stdout chính xác:**

```text
alice-1=true
alice-2=true
alice-3=true
alice-4=false
bob=true
alice-new-window=true
```

Giải thích:

- Alice được 3 lần trong cửa sổ bắt đầu ở millisecond 1000; lần thứ tư bị từ chối.
- Key của Bob có counter độc lập.
- 61000 trừ 1000 bằng 60000 ms: cửa sổ cũ hết hạn, Alice được phép lần mới.
- `ConcurrentHashMap.compute` bảo đảm cập nhật một key có tính atomic trong **cùng JVM**.
- `AtomicBoolean` chỉ mang kết quả ra khỏi lambda; không phải bộ đếm truy cập toàn cục.

**Giới hạn nghiêm trọng của mô hình demo:**

1. Map không **evict** key cũ; kẻ tấn công tạo vô số username giả có thể làm tăng bộ nhớ không giới hạn. Production cần TTL/eviction và giới hạn tài nguyên.
2. Mỗi instance có map riêng; không phù hợp nhiều replicas.
3. Đồng hồ system clock có thể nhảy; thuật toán bảo vệ bằng reset khi thời gian đi lùi, nhưng production nên chọn nguồn thời gian/đồng bộ nhất quán (đặc biệt khi dùng Redis).
4. Fixed window có burst ở ranh giới.
5. API `tryAcquire` đếm **mọi attempt**, kể cả thành công; không tự xử lý success/failure, MFA hay rủi ro.
6. Nếu attacker tự do gửi usernames khác nhau, account key không chặn spraying; cần phối hợp per-IP/global risk.

Class này dùng để học/test logic, **không được quảng cáo là bộ rate limiter production**.

## 6. Gắn limiter vào Spring Security Servlet trước form login

Spring Security form login mặc định xử lý `POST /login` bằng `UsernamePasswordAuthenticationFilter`. Một `OncePerRequestFilter` được đặt **trước filter đó** có thể từ chối request bị throttle **trước khi password verification tiêu tốn CPU/DB**.

Cấu hình sau giới hạn theo IP và username đã normalize. Nó cố tình dùng **map in-memory** để minh họa điểm chặn request; phải thay bằng backend shared store hoặc gateway-aware limiter trước khi chạy nhiều replicas ở production.

### 6.1 LoginThrottleFilter.java

**`src/main/java/com/example/limit/LoginThrottleFilter.java`**

```java
package com.example.limit;

import java.io.IOException;
import java.util.Locale;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public final class LoginThrottleFilter extends OncePerRequestFilter {

    // Chỉ là số liệu demo; cần hiệu chỉnh trước production.
    private final FixedWindowLimiter byIp =
        new FixedWindowLimiter(20, 60_000);
    private final FixedWindowLimiter byAccount =
        new FixedWindowLimiter(5, 60_000);

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !"POST".equals(request.getMethod())
            || !"/login".equals(request.getServletPath());
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        long now = System.currentTimeMillis();

        // RemoteAddr là peer kết nối; sau proxy có thể là IP của proxy.
        String ip = request.getRemoteAddr();
        String supplied = request.getParameter("username");

        // Chỉ dùng lower-case nếu hệ thống login dùng cùng quy tắc.
        String account = supplied == null
            ? ""
            : supplied.strip().toLowerCase(Locale.ROOT);

        if (account.length() > 128) {
            account = "<oversized>";
        }

        // Đếm cả account có thật lẫn account chưa tồn tại.
        boolean allowedIp = byIp.tryAcquire("ip:" + ip, now);
        boolean allowedAccount =
            byAccount.tryAcquire("acct:" + account, now);

        if (!allowedIp || !allowedAccount) {
            response.setStatus(429);
            response.setHeader("Retry-After", "60");
            response.setContentType("text/plain; charset=UTF-8");
            response.getWriter().write(
                "Yêu cầu đang được giới hạn. Vui lòng thử lại sau."
            );
            return;
        }

        chain.doFilter(request, response);
    }
}
```

**Điểm an toàn tương đối của snippet:** không tra DB để biết account tồn tại trước khi rate-limit; account key được dùng cho mọi giá trị username (kể cả không tồn tại). Nó kiểm tra cả per-IP và per-account, không đọc `X-Forwarded-For` trực tiếp từ caller. Mã giới hạn **trước** password verification.

**Chưa đủ cho production:** dùng username thô trong map, không TTL eviction, dùng một IP có thể là IP gateway/proxy, không phân biệt các loại auth flows, không có circuit breaker khi store lỗi, chưa có audit và không có cơ chế challenge/soft backoff. Đây là filter minh họa có chủ đích.

### 6.2 SecurityConfig.java

**`src/main/java/com/example/limit/SecurityConfig.java`**

```java
package com.example.limit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication
    .UsernamePasswordAuthenticationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .addFilterBefore(
                new LoginThrottleFilter(),
                UsernamePasswordAuthenticationFilter.class
            );

        return http.build();
    }
}
```

**Giải thích:**

- `formLogin(...)` bật login page mặc định và xử lý `POST /login`; request credentials mặc định là form parameters `username`/`password`.
- `LoginThrottleFilter` chỉ chạy với `POST /login`, không chặn các GET assets. Route `/login` được `permitAll` để khách chưa login được gửi credentials; **permitAll không bypass filter throttle**.
- `addFilterBefore(..., UsernamePasswordAuthenticationFilter.class)` đặt limiter trước bước Spring Security kiểm tra password.
- Mã dùng `new LoginThrottleFilter()` trực tiếp trong filter chain thay vì khai báo đồng thời một `Filter @Bean` và đăng ký lại; điều này tránh một lỗi **double registration** khi Spring Boot tự đăng ký servlet filter rồi Spring Security cũng thêm nó.
- CSRF mặc định **vẫn bật**. Với HTTP POST login từ browser, frontend phải gửi CSRF token phù hợp. MockMvc test cần `with(csrf())` khi mục tiêu là rate-limit, không phải CSRF.
- Ở production, có thể chọn không tiết lộ account state trong lỗi login, dùng `AuthenticationFailureHandler`, `AuthenticationSuccessHandler` và `AuthenticationEventPublisher`/events cho metrics theo kết quả. **Đừng chỉ lưu số lần sai password nếu trước lúc kiểm tra đã chịu CPU hashing quá lớn**.

### 6.3 Application.java

**`src/main/java/com/example/limit/Application.java`**

```java
package com.example.limit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

Dùng Spring Initializr tạo Gradle project với **Spring Boot 3.x**, Java 17+ và dependencies **Spring Web**, **Spring Security**, **Spring Boot Starter Test**. Thêm test support:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây là phần `dependencies`, giữ plugins/repositories của project do Initializr tạo. Với ứng dụng có repository người dùng thật, cấu hình `UserDetailsService` và `PasswordEncoder` tương ứng. Khi chỉ dùng auto-config demo, Spring Boot có thể tạo một default user và log password khởi tạo trong môi trường dev; **không đưa cơ chế user mặc định này vào production**.

### 6.4 Request flow

```text
POST /login + CSRF token + form username/password
      │
      ▼
Spring Security FilterChain
      │
      ├── CSRF check: request phải hợp lệ
      │
      └── LoginThrottleFilter (trước UsernamePasswordAuthenticationFilter)
             │
             ├── allowed → UsernamePasswordAuthenticationFilter
             │                   │
             │                   ├── authentication success
             │                   └── authentication failure (mặc định redirect)
             │
             └── limited → 429 / Retry-After / generic message
```

**Không hiểu nhầm:** status `429` được phát **trước khi kiểm tra password**, nên nó không nói “account tồn tại” hay “password đúng/sai”. Filter demo cũng không reset counter sau login thành công, tránh rủi ro test/logic giấu một phần hành vi. Policy production nên xác định rõ cách cập nhật counter khi success, thất bại, step-up, lockout, captcha, và khi user đổi IP.

## 7. Kiểm thử HTTP với MockMvc: blocked, allowed và CSRF

Mục tiêu kiểm tra **năm lần đăng nhập đầu** với một username trong cửa sổ thời gian vẫn đi qua `UsernamePasswordAuthenticationFilter`, còn lần tiếp theo trả 429 **trước** xác thực. Vì demo dùng giới hạn account 5 và IP 20, kết quả xác định khi chỉ dùng một username/test case.

**`src/test/java/com/example/limit/LoginThrottleFilterTest.java`**

```java
package com.example.limit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request
    .MockHttpServletRequestBuilder;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class LoginThrottleFilterTest {

    @Autowired
    MockMvc mvc;

    private MockHttpServletRequestBuilder login(String username) {
        return post("/login")
            .param("username", username)
            .param("password", "invalid-for-demo")
            .with(csrf())
            .with(request -> {
                request.setRemoteAddr("192.0.2.20");
                return request;
            });
    }

    @Test
    void sixthAttemptGets429WithoutAccountLookup() throws Exception {
        for (int i = 0; i < 5; i++) {
            // Spring formLogin mặc định redirect khi login sai.
            mvc.perform(login("unknown@example.test"))
                .andExpect(status().is3xxRedirection());
        }

        mvc.perform(login("unknown@example.test"))
            .andExpect(status().isTooManyRequests())
            .andExpect(header().string("Retry-After", "60"));
    }

    @Test
    void missingCsrfIsRejectedBeforeLogin() throws Exception {
        mvc.perform(post("/login")
                .param("username", "new-user@example.test")
                .param("password", "invalid-for-demo"))
            .andExpect(status().isForbidden());
    }
}
```

**Điều kiện thử:** Spring Security filter chain phải được MockMvc tích hợp, ví dụ `@SpringBootTest` + `@AutoConfigureMockMvc` như trên. Test không yêu cầu một user thật vì cả năm lần đầu dùng username chưa tồn tại; form login mặc định xử lý thất bại bằng redirect. Tên test không chứng minh account lookup **không xảy ra** trong năm lần đầu; nó chỉ chứng minh **request thứ sáu bị chặn tại limiter** và username không tồn tại cũng được giới hạn như mọi username. Muốn xác minh số lần truy cập user store hoặc PasswordEncoder, dùng test spy/instrumentation phù hợp.

**Quan trọng với song song tests:** filter giữ state trong context; nếu nhiều tests dùng chung username/key và chạy cùng lúc, sẽ có xung đột. Dùng test identifiers riêng, dọn context hoặc thiết kế clock/store mock resettable ở unit test. Không dùng việc tăng threshold làm cách “chữa” một test bị flaky.

### 7.1 Tính chất account-neutral cần kiểm tra thêm

Bộ test trên chưa so sánh **tài khoản có thật vs không tồn tại**. Ở production, cần có một fixture user thật (ví dụ `alice`) và user không tồn tại, cùng password sai, xác minh:

- cùng kiểu HTTP status/redirect và thông báo công khai;
- không cho biết “không có tài khoản” hoặc “account đã bị khóa” nếu không có chính sách cho phép;
- quy tắc throttle/challenge nhất quán, không tự khác vì account lookup có kết quả;
- không khác biệt bất thường về response headers, sizes và timing distribution;
- email/SMS reset flows không tiết lộ account presence qua response.

**Timing:** đo bằng phân phối trên nhiều lần và môi trường ổn định, không đòi hai request luôn có cùng microsecond latency. Khi user có thật phải chạy PasswordEncoder đắt còn user không tồn tại trả về rất nhanh, attacker có thể dùng thống kê để dò account. Spring Security có các cơ chế giảm timing difference cho một số provider; nếu custom authentication tự viết, cần tính đến đường password hashing dummy và DB lookup ổn định **mà không tự tạo nguồn DoS mới**. Không tuyên bố bảo đảm “constant time” nếu chưa có bằng chứng.

### 7.2 Unit test clock/threshold độc lập

Với `FixedWindowLimiter`, test không dùng `Thread.sleep`:

```java
@Test
void resetsOnlyAfterWindowExpires() {
    FixedWindowLimiter limit = new FixedWindowLimiter(2, 1000);

    assertTrue(limit.tryAcquire("acct:a", 10_000));
    assertTrue(limit.tryAcquire("acct:a", 10_001));
    assertFalse(limit.tryAcquire("acct:a", 10_999));
    assertTrue(limit.tryAcquire("acct:a", 11_000));
    assertTrue(limit.tryAcquire("acct:b", 10_999));
}
```

Đây là **JUnit test method snippet**, cần đặt trong một class test có imports `@Test` và JUnit assertions. Cố định thời gian làm test bền hơn test đợi clock thật. Kiểm tra thêm race bằng concurrent submissions nếu limiter production dùng shared store.

## 8. Đảm bảo account enumeration không rò qua response

### 8.1 Một thông điệp lỗi chung

Với Spring form login, thông báo có thể là:

> “Thông tin đăng nhập không hợp lệ.”

Không phân biệt “không có email này”, “sai mật khẩu”, “account bị disable” trên một trang public **nếu không có lý do/chính sách chấp nhận rò thông tin đó**. Điều này không có nghĩa backend không lưu các nguyên nhân chi tiết trong một audit stream có quyền truy cập hạn chế.

Với password reset:

> “Nếu thông tin phù hợp với một tài khoản, chúng tôi sẽ gửi hướng dẫn.”

Đảm bảo response không đổi chỉ vì account không tồn tại, kể cả code status, redirect, cấu trúc JSON, các header public và hành vi rate limiter. **Không hứa “đã gửi email” khi không có account** theo nghĩa khẳng định một hành động đã xảy ra; thông điệp điều kiện chính xác hơn.

### 8.2 Các ngóc ngách gây enumeration

| Vị trí | Lỗi thường gặp | Cách giảm rủi ro |
| --- | --- | --- |
| Login failure | “Username not found” khác “wrong password”. | Generic failure, đo timing, cùng policy attempts. |
| Reset password | 404 nếu không có email. | Generic 2xx/202 response theo contract, enqueue email chỉ khi thích hợp. |
| Signup | Báo email đã đăng ký khi không cần thiết. | Quy trình đăng ký an toàn, tránh tiết lộ tùy thiết kế UX. |
| MFA challenge | Gửi challenge chỉ khi account có thật, response khác rõ. | Đưa MFA sau bước xác minh account; generic pre-auth UX. |
| Throttle quota | Key chỉ tạo cho account có thật; Retry-After khác. | Ghi counter cho mọi identifier, phản hồi account-neutral. |
| Error pages | Stack trace/exception message có username, user status. | Normalize external errors, redaction, audit nội bộ. |
| Password hash timing | Unknown user bỏ qua hash, known user chạy BCrypt. | Dùng framework providers hoặc dummy verify phù hợp, đo trên môi trường thực. |
| SSO/OIDC login mapping | Trả lỗi chi tiết “email chưa liên kết” hoặc user state. | Privacy-preserving error UX, account-linking policy, logs hạn chế. |

### 8.3 Có nên chặn cứng theo account?

Hard lock có thể phù hợp theo mô hình rủi ro nhất định, nhưng không nên là phản ứng duy nhất. Attacker chỉ cần gửi nhiều sai password cho victim đã biết username để khiến victim bị khóa; với hệ thống lớn, điều này tạo outage bằng “password spray ngược”.

Các lựa chọn bổ sung: hạn chế tốc độ theo account + source, tăng delay, yêu cầu step-up/risk-based challenge, cảnh báo khi có nhiều nguồn lạ, yêu cầu xác minh kênh tin cậy trước khi unlock. Đảm bảo bộ phận hỗ trợ/khôi phục không tạo ra **account enumeration** mới.

**CAPTCHA** chỉ nên là một tín hiệu/challenge trong hệ thống phòng thủ: bot có thể giải hoặc thuê giải, và CAPTCHA có chi phí UX, accessibility, privacy. CAPTCHA không thay thế rate limit, MFA/passkeys hoặc giám sát credential stuffing.

## 9. Vận hành nhiều replicas: Redis counter atomic, TTL và failover

Trong ứng dụng chạy nhiều instance, cần central store hoặc distributed limiter. Ví dụ fixed-window dùng **Redis Lua** để `INCR + PEXPIRE` atomic, giảm race và tránh key không có TTL.

**`login_counter.lua`** (minh họa thuật toán Redis; không yêu cầu Spring Boot tự biết chạy file này):

```lua
local key = KEYS[1]
local maximum = tonumber(ARGV[1])
local windowMillis = tonumber(ARGV[2])

local count = redis.call('INCR', key)

if count == 1 then
    redis.call('PEXPIRE', key, windowMillis)
end

local remainingMillis = redis.call('PTTL', key)

if count > maximum then
    return {0, count, remainingMillis}
end

return {1, count, remainingMillis}
```

Ví dụ gọi trong một môi trường test có Redis và script nằm trong working directory:

```bash
redis-cli --eval login_counter.lua login:ip:example , 5 60000
```

Script trả array gồm `allowed` (1/0), số đếm và TTL ms. Kết quả phụ thuộc trạng thái Redis lúc chạy; không in ra một output cố định. Key `login:ip:example` **chỉ là tên demo**; production cần namespacing cho environment/app/route, TTL, data retention, key cardinality và HMAC cho account identifiers.

**Vì sao dùng Lua:** `INCR` và `PEXPIRE` trong script chạy như một thao tác atomic tại Redis; hai lệnh rời rạc có thể gặp sự cố sau `INCR` trước khi set TTL, để lại key không hết hạn. Với hệ thống lớn còn cần kiểm tra Redis HA/cluster, load, hot key, memory eviction, clock, network partitions và failover behavior.

**Lua trên vẫn là fixed window**, có burst tại ranh giới và trả count/TTL nội bộ. **Không đưa count theo tài khoản vào public HTTP response** nếu nó có thể tạo side channel. Áp dụng sliding/token bucket khi cần độ mượt, và dựa vào provider/library phù hợp thay vì tự viết thuật toán phân tán phức tạp không kiểm thử.

### 9.1 Quyết định khi shared store không hoạt động

| Lựa chọn | Lợi ích | Nguy cơ |
| --- | --- | --- |
| **Fail open**: cho request qua khi Redis lỗi | Người dùng thật tiếp tục login. | Attacker có thể vượt quota đúng lúc store hỏng, CPU/IdP bị tấn công. |
| **Fail closed**: chặn login khi Redis lỗi | Giảm bề mặt brute force. | Có thể tạo outage đăng nhập hàng loạt khi Redis/network lỗi. |
| **Fallback có giới hạn** | Giữ được một phần availability và protection. | Phức tạp, mỗi replica có quota riêng, cần circuit breaker/monitoring. |

Chọn policy theo độ nhạy login, khả năng MFA, rủi ro operational, SLO và quy trình ứng phó. **Không** chọn fail-open/fail-closed một cách ngầm định. Theo dõi cache/store errors và cảnh báo; tránh tạo retry storm làm Redis khó hồi phục.

### 9.2 Tránh “mất counter” khi scale

- Test cả nhiều instances đi qua cùng key và cùng cửa sổ; tổng requests được cho phép phải theo policy của toàn hệ thống.
- Kiểm tra replica restart không reset limit nếu policy yêu cầu thống nhất; counter trong-memory chắc chắn reset khi process restart.
- Test hai requests concurrent vượt threshold; server-side atomicity phải bảo đảm không cấp quá nhiều tokens.
- Đo overhead mỗi login attempt, P95/P99 Redis latency, error rate và mạng.
- Xác định key TTL/capacity; attacker có thể tạo vô số usernames/random IDs để làm đầy Redis nếu không giới hạn cardinality.
- Cân nhắc auth request có source/account key không chuẩn, rất dài, Unicode khác nhau; chuẩn hóa trước khi keying và có input length bounds.

## 10. Reverse proxy và IP thật: chỉ tin những hop đáng tin

Một kiến trúc phổ biến:

```text
Internet client
    │ (IP thực)
    ▼
CDN/WAF ── X-Forwarded-For? ──> Ingress ──> Spring Boot
                                         request.getRemoteAddr()
                                         có thể = IP ingress
```

**`request.getRemoteAddr()` trả địa chỉ peer kết nối mà servlet container biết.** Nếu kết nối tới app đến từ ingress, giá trị này có thể là IP ingress, dẫn tới **mọi user chung một quota**. Mặt khác, đọc thẳng header `X-Forwarded-For` hoặc `Forwarded` từ request của Internet **không an toàn**, vì client có thể tự đặt header đó khi proxy chưa chuẩn hóa.

Chỉ lấy địa chỉ gốc khi:

1. Biết chính xác các proxies/load balancers được phép truy cập backend và thứ tự chuỗi hop.
2. Ingress/WAF **xóa hoặc ghi đè** forwarded headers do client cung cấp nếu không thuộc trust policy.
3. Backend **không thể bị truy cập trực tiếp** để bypass ingress.
4. Cấu hình trusted proxy/forwarded-header processing trong hạ tầng/container được kiểm chứng; không bật “tin mọi proxy” theo mặc định.
5. Có test giả mạo `X-Forwarded-For: 1.2.3.4` để bảo đảm request không đổi bucket tùy ý.

Spring Boot có những cấu hình hỗ trợ forwarded headers cho URL/proxy behavior, nhưng **bật forward headers không tự chứng minh header là đáng tin**. Trust boundary phải được thực thi ở tầng mạng/ingress và lựa chọn parser phù hợp.

### 10.1 Tránh đếm lặp ở edge và app

Một request có thể bị chặn tại WAF trước khi đến Spring, hoặc Spring trả 429 sau khi gateway đã cho qua. Nếu mỗi lớp có threshold khác nhau, UI có thể gặp hành vi khó giải thích. Nên dùng:

- Request ID/correlation ID không chứa secrets đi xuyên các lớp.
- Metric rõ **nguồn quyết định**: `edge_limit`, `gateway_limit`, `app_login_limit`, `idp_risk_challenge`.
- Contract HTTP thống nhất: 429 với thông báo hợp lý, Retry-After nếu phù hợp, không công bố account state.
- Dashboard nhận biết tỷ lệ chặn/false positives/latency của mỗi lớp.
- Quy trình phối hợp on-call khi tăng threshold hay phát hiện chiến dịch tấn công; không để đội edge/app tự thay đổi quota đối nghịch.

## 11. Đăng nhập qua OAuth2/OIDC và MFA: vị trí giới hạn khác local form

### 11.1 Form login do Spring Security kiểm tra password

Với `UsernamePasswordAuthenticationFilter` và `UserDetailsService`, ứng dụng trực tiếp nhận form username/password. App-level filter trước `POST /login` có thể giảm số lần password hashing. Đối với password failures, server nên có generic failure handler và audit nội bộ.

### 11.2 OAuth2 Login / OIDC SSO

Nếu web app dùng `oauth2Login()` ở Spring Security, **password được nhập tại IdP**, không phải tại ứng dụng client. App nên:

- Để **IdP** quản lý password brute force, credential stuffing, MFA và primary login policy.
- Giới hạn bất thường ở **authorization initiation** (`/oauth2/authorization/{registrationId}`) theo source/session khi có nguy cơ redirect abuse, nhưng tránh chặn user hợp lệ.
- Giám sát callback `/login/oauth2/code/{registrationId}` và lỗi state/missing session; đừng chặn callback hợp lệ chỉ vì một per-IP bucket quá thấp, đặc biệt khi nhiều user sau NAT.
- Không dùng rate limiting làm lý do **bỏ state, nonce, PKCE hay token validation**. Những bước bảo vệ giao thức vẫn bắt buộc theo flow.
- Phối hợp IdP khi có account lockout, risk-based MFA, session lifetime và account recovery. App-side 429 không thể thay thế chính sách IdP.

### 11.3 MFA, OTP và passkeys

- OTP verification cần giới hạn số lần thử/đoán mã theo **challenge/session/account** với TTL, không chỉ IP.
- Backup/recovery codes phải one-time use, giới hạn thử, bảo vệ như credential có giá trị cao.
- Passkeys/WebAuthn giảm khả năng credential phishing, nhưng registration, login initiation, recovery, session và abuse endpoints vẫn cần rate control theo rủi ro.
- Nếu dùng step-up sau rủi ro cao, server phải quyết định sau kiểm tra policy; không tin field do client gửi như `mfaPassed=true`.
- Account recovery có thể là con đường tấn công dễ hơn login; áp dụng generic responses, rate limiting, xác minh mạnh và audit.

## 12. Quan sát hệ thống: metrics, logs, alert và xử lý sự cố

Các metrics nên tách biệt:

| Metric | Mục đích |
| --- | --- |
| `auth_attempts_total{flow,outcome}` | Nhận biết tổng số yêu cầu và tỉ lệ lỗi theo form/SSO/MFA. |
| `auth_throttled_total{layer,reason}` | Phân biệt 429 từ edge/gateway/app/IdP. |
| `auth_failure_ratio` | Tìm bất thường tỉ lệ fail, phân biệt lỗi UX với attack. |
| `distinct_account_keys_per_source` | Phát hiện password spraying (trên dữ liệu đã pseudonymize). |
| `distinct_sources_per_account` | Phát hiện brute force phân tán. |
| `login_latency_seconds` | Đo overhead hashing/Redis/IdP. |
| `rate_store_errors_total` | Biết Redis/throttle store bị lỗi và policy fallback được áp dụng. |
| `false_positive_reports` | Giảm chặn nhầm người dùng thật, đặc biệt IP NAT. |
| `mfa_challenge_rate` và `recovery_attempts` | Quan sát bước thay thế khi primary login bị tấn công. |

**Không dùng username/email/IP làm Prometheus label trực tiếp**: cardinality rất lớn, lộ dữ liệu cá nhân và khiến monitoring backend quá tải. Nhãn metrics nên có **nhóm có giới hạn** (flow/layer/outcome/risk bucket); dữ liệu điều tra chi tiết cần vào audit store có ACL và retention phù hợp.

### 12.1 Tín hiệu của từng kiểu tấn công

- **Brute force một account:** lượng failure trên một account key tăng nhanh, nhiều password attempts, có thể từ nhiều IP.
- **Spraying:** một nguồn hoặc nhóm nguồn thử nhiều account khác nhau với tần suất nhỏ per account, failure ratio cao.
- **Credential stuffing:** nhiều tổ hợp tài khoản/mật khẩu được thử, có thể kèm một số success đáng ngờ; cần correlate account takeover signals sau login.
- **Enumeration:** traffic tập trung lookup/reset/signup, nhiều usernames, khác biệt response/timing bị khai thác.
- **Khóa nhầm:** tăng 429 trên mạng chung, tăng support tickets, người thật báo không đăng nhập được.

Hệ thống phát hiện không nên chỉ dựa trên số lượng request: bot có thể hoạt động chậm, user thật cũng có thể đăng nhập lại nhiều lần do lỗi ứng dụng.

### 12.2 Khi có cảnh báo

1. Xác minh layer tạo 429, profile traffic, affected population và hoạt động Redis/IdP.
2. Phân biệt tấn công với regression UX, client retry loop, mobile app lỗi hoặc mạng NAT.
3. Nếu là attack, điều chỉnh edge/gateway/app theo playbook; có thể thêm challenge/MFA, chặn nguồn rõ ràng, bảo vệ reset/MFA endpoints.
4. Nếu là false positive, nới quota có kiểm soát, bổ sung exemption dựa trên tín hiệu đáng tin (không phải user-supplied header), xem tác động lên accounts nhạy cảm.
5. Nếu rate-store outage, kích hoạt fallback đã định trước và theo dõi auth failure rate/DB CPU.
6. Phân tích account takeover signs, session anomalies, credential reset và audit; tuân thủ quy trình ứng phó sự cố.
7. Sau sự cố, bổ sung regression/chaos tests và điều chỉnh baseline, không chỉ tăng threshold rồi đóng ticket.

## 13. Các trường hợp kiểm thử quan trọng trước khi production

### 13.1 Bảo vệ quota

| Trường hợp | Thử nghiệm | Kết quả cần quan sát |
| --- | --- | --- |
| Trong quota | 1–N attempts cùng key | Đi đến authentication; response theo credential hợp lệ/sai. |
| Vượt quota | N+1 attempt | 429/challenge theo policy; không làm tốn chi phí auth nặng. |
| Hết cửa sổ | Request sau TTL | Được xử lý theo counter mới. |
| Nhiều tài khoản từ một IP | Thử usernames khác nhau | Per-IP/behavior rule vẫn phát hiện spraying; tránh chặn toàn bộ NAT tùy tiện. |
| Một account từ nhiều IP | Phân tán attempts | Account-level/campaign rule vẫn quan sát. |
| Hai replicas | Request luân phiên qua 2 backend | Tổng quota đúng, không nhân đôi theo instance. |
| Concurrent requests | Gửi vượt threshold đồng thời | Counter atomic, không cấp vượt quota ngoài policy. |
| Redis unavailable | Ngắt Redis tạm thời | Hành vi fail-open/closed/fallback theo playbook, có metrics. |
| Clock boundary | Attempts gần TTL | Không bị bypass lớn do fixed-window boundary hoặc có rule bổ sung. |
| Key explosion | Random usernames rất nhiều | Bộ nhớ TTL/eviction/capacity không bị cạn. |

### 13.2 Chống dò tài khoản

| Test | Điều mong muốn |
| --- | --- |
| Username có thật + sai password | Public response không tiết lộ trạng thái account. |
| Username không có + sai password | Cùng thông điệp/status/redirect có chủ đích. |
| Username có thật + hết quota | Không công bố quota account-specific nếu làm lộ presence. |
| Username không có + hết quota | Không có ngoại lệ bất thường chỉ vì DB lookup fail. |
| Quên mật khẩu có/không có email | Generic response, không rò account existence. |
| Tài khoản locked/disabled | UX phù hợp policy, không có thông tin ngoài ý muốn cho attacker. |
| Email/username khác case, whitespace, Unicode | Same canonicalization với user store; không bypass quota. |
| Oversized/invalid identifier | Giới hạn input, tránh memory/key explosion và response chi tiết. |
| Sai CSRF hoặc request không hợp lệ | Chặn đúng layer, không ghi log password, không sai lệch auth metrics. |
| Header `X-Forwarded-For` giả | Không thể chọn arbitrary source bucket. |

### 13.3 Kiểm thử trải nghiệm người dùng thật

- Người dùng gõ sai hai lần rồi đăng nhập đúng: không bị phạt quá mức.
- Người dùng sau NAT chung với nhiều người: quota nguồn không chặn cả mạng một cách bất hợp lý.
- User dùng screen reader hoặc không giải được CAPTCHA: có đường thay thế phù hợp.
- Client gặp 429: không retry liên tục ngay lập tức; xử lý Retry-After/backoff và hiển thị thông điệp rõ ràng.
- Session đã authenticated không bị chặn nhầm bởi limiter login; không dùng quota của `POST /login` để áp cho mọi API.
- MFA hoặc account recovery không vô tình bypass bộ đếm primary login hoặc tạo đường enumeration mới.
- Ops có thể xác định **ai/cái gì tạo 429** mà không cần xem mật khẩu hay sensitive headers.

## 14. Những lỗi triển khai hay gặp

| Dấu hiệu | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Bot đổi `X-Forwarded-For` để né limiter | Backend tin header do client tự gửi. | Chỉ trust hops/proxies đã cấu hình; strip/overwrite header ngoài ingress. |
| Tăng replicas làm attacker được nhiều attempts | Counter local per JVM. | Shared Redis/gateway quotas, test cross-node. |
| Người dùng cả văn phòng bị 429 | Dựa hoàn toàn vào IP NAT. | Kết hợp account/session/risk signals, nới IP thresholds hợp lý. |
| Người dùng bị khóa do kẻ khác thử sai | Account hard lockout dễ DoS. | Soft backoff, step-up, risk scoring, recovery, monitoring. |
| Dò tài khoản được qua `Retry-After` | Counter chỉ tạo cho account có thật. | Tạo counter trước lookup, account-neutral responses. |
| Dò tài khoản được qua latency | Unknown user trả lỗi nhanh hơn password hash. | Rà custom auth provider, dummy hash/constant-shape path, đo thống kê. |
| POST login trả 403 dù dưới quota | CSRF filter chặn trước login. | Xác minh CSRF token; không tắt CSRF. |
| Login đúng nhưng vẫn 429 | Demo đếm mọi attempts, không reset sau success. | Thiết kế success/failure policy có kiểm soát; không reset bừa gây bypass. |
| Redis hết memory | Keys theo raw usernames vô hạn, không TTL. | Bounded key cardinality, TTL, HMAC keys, capacity/eviction policy. |
| 429 có nhưng DB vẫn quá tải | Chặn quá muộn sau hashing hoặc IdP call. | Edge prefilter + application pre-auth gate, đo DB CPU. |
| Throttling login IdP không hiệu quả | Ứng dụng chỉ điều tiết local `POST /login`; password ở IdP. | Phối hợp rate controls tại IdP và OIDC initiation/callback. |
| CAPTCHA gây nhiều bỏ cuộc | Mọi user đều bị challenge quá sớm. | Risk-based trigger, accessibility, measurement. |
| Monitoring bùng cardinality | Username/IP là metric labels. | Low-cardinality labels và chi tiết vào audit store có ACL. |
| Thêm whitelist theo header `X-Internal-User` | Caller có thể tự gửi header. | Dùng mTLS/service identity, network trust và proxy-enforced metadata. |

## 15. Checklist vận hành và thiết kế

1. Xác định auth flows: local form, JSON login API, OAuth2/OIDC SSO, password reset, MFA, passkeys, service authentication.
2. Thống kê traffic thật, độ rộng NAT/proxy và baseline thất bại trước khi chọn threshold/algorithm.
3. Áp nhiều key: IP, account, IP+account, campaign/ASN, nhưng bảo vệ khỏi account lockout abuse.
4. Đồng bộ canonicalization với user store; không dùng raw username/email trong logs/metrics không được bảo vệ.
5. Dùng generic public errors cho account existence; test cả status, body, redirects, headers, timing, reset paths.
6. Bật CSRF đúng cho browser form/session; không dùng rate limiting để thay authentication/CSRF protection.
7. Đặt limiter đủ sớm trước hashing/DB/IdP khi cần, nhưng thu thập auth result sau đó để phát hiện campaign.
8. Dùng shared atomic store cho nhiều replicas; đặt TTL/eviction, chọn fail-open/closed/fallback trước khi có outage.
9. Chỉ tin forwarded IP sau proxy/ingress đã xác minh và chặn direct backend bypass.
10. Phối hợp CDN/WAF/gateway/IdP/app qua trace IDs, thống nhất 429/Retry-After và phân biệt layer quyết định.
11. Theo dõi false positives, brute force/spraying/stuffing signals, Redis errors, user recovery và SLO.
12. Test concurrency, multi-instance, clock boundary, key explosion, fake forwarded headers và lỗi infrastructure.
13. Dùng MFA/passkeys và bảo vệ recovery; không chỉ dựa vào CAPTCHA hay quota.
14. Tài liệu hóa incident playbook và cơ chế điều chỉnh ngưỡng có review, audit và rollback.

**Ghi nhớ:** Giới hạn thử đăng nhập hiệu quả là **một chiến lược phòng thủ nhiều lớp**, không phải một counter trong một JVM. Spring Security Servlet có thể chặn sớm trên `POST /login`, nhưng account enumeration cần response/account state nhất quán; brute force phân tán cần shared counters và signals; NAT/reverse proxy đòi hỏi trust boundary rõ; còn OAuth2/OIDC login phải phối hợp với chính IdP. Test phải bao phủ **quyền truy cập, trải nghiệm người thật, nhiều replicas và các tình huống hạ tầng lỗi**, không chỉ “lần thứ sáu trả 429”.
