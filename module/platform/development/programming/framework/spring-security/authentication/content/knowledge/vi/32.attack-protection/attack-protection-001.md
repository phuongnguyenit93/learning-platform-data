# Brute force, password spraying và credential stuffing: nhận diện và phòng thủ trong Spring Security

## 1. Mục tiêu

Các cuộc tấn công vào **điểm đăng nhập bằng mật khẩu** không nhất thiết khai thác lỗi mật mã. Chúng tận dụng việc hệ thống cho phép thử thông tin đăng nhập nhiều lần, người dùng chọn mật khẩu yếu hoặc tái sử dụng mật khẩu đã bị lộ ở dịch vụ khác.

Ba kiểu thường gặp:
- **Brute force / password guessing:** thử nhiều mật khẩu đối với một tài khoản hoặc một tập tài khoản nhỏ.
- **Password spraying:** thử một hay vài mật khẩu phổ biến trên **nhiều tài khoản**, thường với tốc độ thấp cho mỗi account để tránh bị khóa theo tài khoản.
- **Credential stuffing:** thử **các cặp username/password đã bị lộ từ một vụ rò rỉ khác**, tận dụng thói quen tái sử dụng mật khẩu. Đây không nhất thiết là đoán mật khẩu mới.

Ba kiểu khác nhau về mẫu phân bố, mục tiêu và tín hiệu phát hiện. Điểm phòng thủ chung là **không tin rằng một giới hạn theo IP hay một khóa tài khoản đơn lẻ đã đủ**.

Sau bài học, bạn có thể phân loại ba kiểu tấn công, đọc các dấu hiệu trong dữ liệu đăng nhập, thiết kế rate limit nhiều chiều, hiểu ưu/nhược của account lockout, kết hợp MFA/passkeys, cấu hình Spring Security Servlet và xây dựng bộ test không tấn công hệ thống thật.

> **Phạm vi:** bài tập trung vào phòng thủ cho ứng dụng sở hữu endpoint xác thực username/password, ví dụ `POST /login`. Với OAuth2/OIDC SSO, password được kiểm tra tại nhà cung cấp định danh (IdP), nên các chính sách chống thử mật khẩu phải được thực thi chủ yếu ở IdP, đồng thời ứng dụng vẫn bảo vệ callback/session và giám sát bất thường. Không lấy mã demo làm một WAF hoặc hệ anti-bot production.

## 2. Phân biệt chính xác ba kiểu tấn công

### 2.1. Brute force: nhiều ứng viên mật khẩu cho cùng tài khoản

Ví dụ log tổng hợp **giả định**, không hiển thị mật khẩu thực:

~~~text
10:00 user=alice source=A result=FAIL
10:01 user=alice source=A result=FAIL
10:02 user=alice source=A result=FAIL
10:03 user=alice source=A result=FAIL
10:04 user=alice source=A result=FAIL
~~~

Ở đây một account chịu nhiều lần thất bại trong thời gian ngắn. Tấn công có thể dùng từ điển mật khẩu, các biến thể của mật khẩu phổ biến hoặc nhiều nguồn IP. Nếu hệ thống chỉ chặn một source IP, attacker có thể đổi IP và tiếp tục nhắm vào cùng account.

**Tín hiệu phòng thủ:** số lần thử theo account, tỷ lệ thất bại, tốc độ và sự thay đổi nguồn; không chỉ số lần thử theo một IP.

### 2.2. Password spraying: một vài mật khẩu trên nhiều tài khoản

Ví dụ log giả định:

~~~text
10:00 user=alice source=B result=FAIL
10:01 user=bob   source=B result=FAIL
10:02 user=carol source=B result=FAIL
10:03 user=dave  source=B result=FAIL
10:04 user=erin  source=B result=FAIL
~~~

Mỗi account chỉ có một lần thất bại, nhưng một nguồn đang chạm tới **nhiều tài khoản khác nhau**. Nếu attacker phân tán qua proxy, mỗi IP cũng có thể có ít request. Giới hạn “5 lần sai mỗi account rồi khóa” có thể **không phát hiện spraying sớm**, vì mỗi username chưa vượt ngưỡng.

**Tín hiệu phòng thủ:** số account khác nhau bị thử theo source/IP pool/ASN/device/browser signal và các cửa sổ thời gian; phát hiện *campaign* theo toàn hệ thống, không chỉ nhìn từng account.

### 2.3. Credential stuffing: cặp credential từ vụ lộ dữ liệu khác

Ví dụ giả định:

~~~text
10:00 account=alice source=C result=FAIL
10:01 account=bob   source=C result=SUCCESS
10:02 account=carol source=D result=FAIL
10:03 account=dave  source=D result=SUCCESS
~~~

Mỗi account có thể chỉ bị thử **một cặp** đã lộ. Tỷ lệ login thành công có thể đáng chú ý; sau đó thường xuất hiện hành vi bất thường ở session mới như thay email, thay mật khẩu, tải dữ liệu hoặc tạo token.

**Tín hiệu phòng thủ:** lượng login qua nhiều account, thành công từ thiết bị/IP bất thường, cặp credential bị lộ (dựa trên cơ chế kiểm tra an toàn), hành vi hậu đăng nhập và kết quả MFA. Không ghi password vào log để “phát hiện password giống nhau”.

### 2.4. Bảng so sánh

| Tiêu chí | Brute force | Password spraying | Credential stuffing |
|---|---|---|---|
| Đầu vào | Nhiều ứng viên password | Một/vài mật khẩu phổ biến | Nhiều cặp username/password đã lộ |
| Độ phân tán theo account | Thường tập trung | Rộng, ít thử mỗi account | Rộng, có thể chỉ một thử mỗi account |
| Giới hạn theo account | Có tác dụng mạnh | Có thể khó nhận ra | Có thể không chặn thử đầu tiên |
| Giới hạn theo IP | Hữu ích nếu tập trung IP | Hữu ích nếu không phân tán | Dễ bị qua mặt với proxy phân tán |
| MFA/passkey | Giảm nguy cơ takeover | Giảm nguy cơ takeover | Đặc biệt quan trọng khi password bị tái sử dụng |
| Quan sát cần thiết | Account velocity | Distinct accounts per source/campaign | Credential reuse signals + successful anomalies |
| Rủi ro phụ | Khóa nhầm account / DoS | Khóa hàng loạt nếu policy cứng | Account takeover bằng password đúng |

**Không phân loại chắc chắn chỉ bằng một dòng log.** Một tập hợp nhiều thất bại trên nhiều account có thể là spraying hoặc stuffing không thành công. Cần thêm dấu hiệu lịch sử và hành vi; không suy đoán password từ log.

## 3. Tác động lên hệ thống và người dùng

Hậu quả không chỉ là “tìm được password”:
1. **Account takeover (ATO):** attacker login vào account có mật khẩu bị đoán/trùng với dữ liệu lộ.
2. **Lộ dữ liệu hoặc giao dịch trái phép:** lấy token, tải báo cáo, thay địa chỉ/email hoặc tạo API key trong quyền của tài khoản.
3. **Denial of service do khóa tài khoản:** một cơ chế lockout quá cứng có thể biến spraying thành công cụ khóa hàng nghìn người dùng hợp lệ.
4. **Tăng tải hạ tầng:** password hashing đúng chuẩn (bcrypt/Argon2id/PBKDF2) tốn tài nguyên; request hàng loạt có thể tiêu thụ CPU/DB pool.
5. **User enumeration:** HTTP status, thông báo hoặc thời gian xử lý khác nhau giữa “user không tồn tại” và “password sai” có thể giúp lập danh sách account.
6. **Nhiễu vận hành:** hàng triệu login fail gây cảnh báo giả, tăng log/cost, làm khó phát hiện thành công bất thường.

Nếu attacker vượt qua mật khẩu nhưng còn phải qua MFA, sự kiện **password đúng nhưng MFA thất bại** rất đáng lưu ý. Nên có alert theo rủi ro, bảo đảm không tiết lộ credential hay thông tin riêng tư cho người không có quyền.

## 4. Mô hình phòng thủ nhiều lớp

Một sơ đồ chức năng:

~~~text
Internet / browser
        |
        v
Edge / gateway / WAF
    - TLS, IP/ASN reputation, burst rate limit
    - bot mitigation khi cần
        |
        v
Spring Security login entry point
    - CSRF cho browser login
    - per-account + per-source attempt limiter
    - username canonicalization nhất quán
        |
        v
AuthenticationManager / PasswordEncoder
    - mật khẩu lưu dạng hash phù hợp
    - generic authentication failures
        |
        v
Risk decision + MFA / passkey
    - step-up cho tình huống nhạy cảm
    - không tin device/header client tự khai
        |
        v
Session / authorization
    - rotate session sau login
    - kiểm tra quyền và trạng thái account
        |
        v
Audit/metrics/incident response
    - failure/success/lockout/rate limited
    - suspicious-success monitoring
~~~

Mỗi lớp phục vụ mục tiêu riêng. **WAF không biết hoàn toàn trạng thái account**; Spring Security không có đủ dữ liệu toàn bộ ASN/proxy; DB transaction không thay anti-bot; CAPTCHA không thay MFA.

### 4.1. Các điểm phải thực thi chính sách

- `POST /login` và các API password authentication khác.
- Endpoint mobile/API có thể có form JSON riêng.
- Đăng nhập admin, VPN/SSO, IdP nếu đây là nơi mật khẩu được kiểm tra.
- Các luồng đổi mật khẩu, forgot password, OTP/recovery và cấp session/token khi có khả năng bị automation.
- Các đường fallback (HTTP Basic, legacy endpoint, test accounts) không được bỏ qua limiter.
- API đã login vẫn phải kiểm tra authorization: việc chặn đăng nhập không chữa lỗi BOLA/IDOR.

## 5. Rate limiting: không khóa vào một chiều

### 5.1. Hai bucket độc lập: account và source

Một cấu hình hiệu quả thường đặt **hai điều kiện riêng biệt**:
- **Theo account:** giới hạn số lần thử vào một định danh user, **bất kể IP**. Giảm brute force phân tán.
- **Theo nguồn:** giới hạn số lần một nguồn thử vào **nhiều account**, bất kể username. Giảm spraying/stuffing tập trung.

~~~text
request(username = alice, source = 203.0.113.8)
                  |
                  +--> ACCOUNT bucket "alice"
                  |
                  +--> SOURCE bucket "203.0.113.8"
                  |
                  +--> BOTH allow? → tiếp tục kiểm tra password
                        bất kỳ bucket nào vượt ngưỡng → throttle
~~~

**Sai lầm rất phổ biến:** chỉ dùng một khóa giới hạn ghép `IP:username`. Một IP có thể thử nhiều username; mỗi tổ hợp có quota riêng nên tổng số request rất lớn. Tương tự, botnet phân tán IP có thể thử cùng account từ nhiều IP. Hai bucket **không thay thế nhau**.

### 5.2. Bucket thứ ba cho campaign

Với các cuộc tấn công phân tán, nên có detection aggregate:
- `distinct_account_count` theo source/ASN/cluster trong cửa sổ ngắn và dài;
- số lượng cặp source-account mới, đặc biệt từ hạ tầng proxy hoặc cloud;
- tỷ lệ 401/403/429 và login success từ thiết bị chưa từng thấy;
- mức tăng của captcha/MFA failures;
- token/session hoạt động bất thường sau một lần password thành công.

Không tự tin `User-Agent`, `X-Device-ID`, `X-Forwarded-For` do client khai; chúng có thể bị giả. Dữ liệu từ proxy tin cậy và correlation nhiều chiều có giá trị hơn một trường đơn lẻ.

### 5.3. Sliding window và token bucket

| Thuật toán | Cách hoạt động | Ưu/nhược |
|---|---|---|
| Fixed window | Đếm request trong từng khoảng cố định | Dễ làm nhưng burst ở ranh giới cửa sổ |
| Sliding window log/counter | Đếm trong khoảng trượt | Chính xác hơn, chi phí lưu/truy vấn |
| Token bucket | Có sức chứa burst và tốc độ nạp lại | Cân bằng ngưỡng bùng nổ và tốc độ trung bình |
| Leaky bucket | Làm đều luồng hoặc xếp hàng | Hữu ích kiểm soát tốc độ, cần backpressure |
| Progressive delay | Tăng độ trễ theo rủi ro/số lần sai | Tránh hard lock nhưng có thể giữ thread nếu triển khai sai |

**Ví dụ tham khảo**, không phải chuẩn áp dụng mọi hệ thống: một account chỉ được 5 lần thử burst và nạp lại 1 lần/phút; một nguồn có thể có 20 lần burst và nạp lại 1 lần/3 giây. Production chọn theo lưu lượng và risk model; phải đo false positives, đăng nhập từ mạng doanh nghiệp dùng chung IP, IPv6/proxy và khả năng lockout DoS.

### 5.4. Rate limit phải nhất quán giữa replica

In-memory `ConcurrentHashMap` **không chia sẻ dữ liệu** giữa các instance. Trong production dùng Redis/DB/gateway có thao tác nguyên tử (Lua script, transaction, token bucket của platform) và TTL/quota; phân biệt:
- cập nhật bucket atomically để hai request song song không vượt ngưỡng;
- hết hạn state tránh memory exhaustion;
- failure mode khi Redis/gateway lỗi: fail-safe/step-up/giới hạn chặt hơn theo policy, không âm thầm biến mọi login thành không giới hạn;
- kiểm tra thời gian giữa các node;
- nếu hai bucket bị trừ từng cái riêng, một bucket có thể tiêu hao ngay cả khi bucket còn lại đã từ chối. Đó là hành vi bảo thủ chấp nhận được nếu đã được định nghĩa; nếu muốn all-or-nothing cần atomic multi-key policy.

## 6. Account lockout: cân bằng chống đoán và tránh DoS

**Account lockout** dừng hoặc trì hoãn xác thực sau số lần thất bại. NIST SP 800-63B-4 có giới hạn trên cho số lần xác thực thất bại liên tiếp đối với một authenticator trong ngữ cảnh tuân thủ tương ứng; **con số tối đa không phải ngưỡng đề xuất dùng nguyên xi cho mọi app**.

Các yếu tố thiết kế:
- *threshold*: số lần sai trước khi throttle/lock;
- *observation window*: khoảng quan sát, ví dụ 15 phút;
- *lock duration*: thời gian trì hoãn hoặc khóa tạm;
- *reset semantics*: login thành công, recovery hoặc admin reset ảnh hưởng counter ra sao;
- *scope*: theo account, credential, nguồn và/hoặc policy rủi ro.

**Nhược điểm:** nếu lockout cứng xảy ra chỉ vì attacker thử sai, đối thủ có thể cố tình khóa account của nạn nhân. Do đó:
- ưu tiên progressive delay, risk-based challenge hoặc step-up trước hard lock dài;
- không tiết lộ account tồn tại khi trả “đã khóa” cho người chưa xác thực;
- không cho phép CAPTCHA bị bypass từ API client khác;
- có self-service recovery an toàn và audit;
- quản trị viên/đối tác tích hợp có policy phù hợp mà không miễn trừ khỏi giám sát.

Nếu user legitimate bị throttle, màn hình có thể thông báo chung “Có quá nhiều yêu cầu, vui lòng thử lại sau” nhưng không tiết lộ ngưỡng chính xác hoặc lý do rủi ro nội bộ. Đừng đặt một đồng hồ đếm ngược quá chính xác giúp bot tối ưu lịch thử.

## 7. MFA, passkeys và chống credential reuse

### 7.1. MFA giải quyết điểm yếu gì?

MFA yêu cầu một yếu tố độc lập bổ sung sau password. Với credential stuffing, password có thể **đúng** vì bị lộ tại nơi khác; MFA có thể ngăn login nếu attacker không giữ yếu tố bổ sung. Tuy nhiên:
- MFA bằng SMS/OTP có thể bị phishing hoặc tấn công luồng recovery.
- Push approval có rủi ro “MFA fatigue”; cần chống spam và number matching nếu dùng.
- TOTP tốt hơn chỉ dùng password nhưng có thể bị phishing proxy theo thời gian thực.
- **FIDO2/WebAuthn passkeys** gắn chứng thực với RP ID/origin, hỗ trợ chống phishing tốt hơn password/OTP; vẫn cần bảo vệ enrollment, recovery và session.
- Nếu hệ thống có recovery yếu, attacker có thể đi đường vòng quanh MFA.

### 7.2. Password policy và breached-password screening

- Chấp nhận password/passphrase đủ dài, không ép các quy tắc phức tạp gây tái sử dụng mật khẩu dự đoán.
- Kiểm tra password mới/được thay có trong tập password đã lộ hay quá phổ biến, qua dịch vụ privacy-preserving hoặc danh sách tin cậy; **không gửi raw password cho API không tin cậy**.
- Lưu mật khẩu bằng thuật toán password hashing thích hợp có work factor như Argon2id/bcrypt/PBKDF2, không SHA-256 trần hoặc reversible encryption.
- Không ép đổi mật khẩu định kỳ vô lý nếu không có dấu hiệu compromise theo policy; khi phát hiện password thật sự lộ, yêu cầu thay và thu hồi phiên/tokens liên quan.
- Người dùng dùng password manager tạo password riêng cho từng dịch vụ sẽ giảm nguy cơ credential stuffing.

### 7.3. Phát hiện sau login

Một login trả `SUCCESS` không chứng minh an toàn nếu credential bị lộ. Với login từ thiết bị/nơi mới, ứng dụng có thể:
- đòi MFA/step-up trước thao tác đổi email, đổi password, thêm API key hoặc thanh toán;
- gửi cảnh báo đăng nhập bất thường tới liên hệ đã xác minh;
- hiển thị lịch sử đăng nhập/session cho người dùng và khả năng thu hồi phiên;
- kiểm tra hành vi bất thường và áp dụng giới hạn giao dịch.

Lưu ý tránh thông báo quá nhiều khi password sai: attacker có thể biến nó thành spam hoặc làm người dùng phớt lờ cảnh báo quan trọng.

## 8. Thông báo lỗi và chống user enumeration

Nếu giao diện trả các thông điệp khác nhau:
- “Không có tài khoản alice”;
- “Mật khẩu sai của alice”;
- “Tài khoản alice đã bị khóa”;

thì nó tiết lộ trạng thái account cho người chưa được xác thực. Các khác biệt về **HTTP status, thời gian xử lý và redirect** cũng có thể là kênh rò rỉ.

Quy tắc:
- với login sai, trả thông báo chung kiểu **“Thông tin đăng nhập không hợp lệ”**;
- tránh trả user ID có tồn tại hay không;
- form login redirect có thể về `/login?error`, nhưng không gắn reason cụ thể vào URL;
- khi rate limited, có thể dùng `429 Too Many Requests` với thông báo chung; đừng công khai bucket nào vượt hoặc số lần còn lại;
- nếu thực hiện dummy password hash để giảm timing enumeration, đo hiệu quả và chi phí CPU; không làm cho attacker dễ ép server tính hash vô hạn;
- kiểm tra mọi đường login/forgot-password/signup để tránh các discrepancy khác nhau.

Lỗi thông tin đăng nhập và lỗi rate-limit không nhất thiết phải có cùng status, nhưng **không được biến sự khác biệt thành cách dò tồn tại account**.

## 9. Kiến trúc Spring Security Servlet

Trong Spring Security 6.x, `UsernamePasswordAuthenticationFilter` tiếp nhận form POST login rồi dùng `AuthenticationManager` / `AuthenticationProvider` để kiểm tra username và password.

~~~text
POST /login (username/password + CSRF)
        |
        v
Spring Security filter chain
   - CSRF / session context handling
   - custom LoginThrottleFilter
        |  account bucket AND source bucket?
        |    NO → 429, dừng trước password hashing
        |    YES
        v
UsernamePasswordAuthenticationFilter
        |
        v
AuthenticationManager / ProviderManager
        |
        v
DaoAuthenticationProvider + UserDetailsService + PasswordEncoder
        |
        +---- FAIL → AuthenticationFailureHandler / auth events
        |
        +---- SUCCESS → AuthenticationSuccessHandler / session
        v
Protected endpoints + security logging/metrics
~~~

**Chức năng của các lớp:**
- `OncePerRequestFilter`: có thể dùng để giới hạn request **trước** bước xác minh password.
- `AuthenticationFailureHandler`: xử lý kết quả login fail, không thay thế pre-auth limiter; nếu request bị filter chặn trước đó thì failure handler chưa được gọi.
- `AuthenticationSuccessHandler`: điều hướng/hậu xử lý sau login thành công; không tự bỏ phiên/CSRF protection.
- `AuthenticationEventPublisher` + `@EventListener`: phát/nhận sự kiện authentication cho giám sát khi được cấu hình phù hợp.
- `DaoAuthenticationProvider`: dùng `UserDetailsService` và `PasswordEncoder`; không cần custom password comparison bằng so sánh chuỗi thường.
- `SecurityContext`: chỉ chứa authenticated principal/authorities sau khi xác thực thành công; limiter không tạo authentication.

**Quan trọng:** Spring Security không mặc nhiên cung cấp chính sách chống credential stuffing hoàn chỉnh chỉ vì `formLogin()` được bật. Các quyết định rate limit/risk/MFA và thu thập tín hiệu phải được tích hợp riêng hoặc thông qua IdP/gateway.

## 10. Ví dụ Spring Boot 3.x + Spring Security 6.x + Java 17

Mẫu sau là một **demo phòng thủ**, không thực hiện thử mật khẩu tự động. Mỗi request `POST /login` được xét hai token buckets độc lập: theo username và theo source IP. Khi một trong hai không còn quota, filter trả 429 trước khi `UsernamePasswordAuthenticationFilter` kiểm tra password. Mỗi request được đếm, không chỉ lần sai; vì vậy mẫu giới hạn tổng tốc độ, phù hợp cho minh họa pre-auth throttling.

**Giới hạn demo:** bucket nằm trong RAM, không chia sẻ qua cluster, không tự dọn key và không thay công cụ phát hiện spraying/stuffing phân tán. Để production cần Redis/gateway limiter có quota atomically, eviction/TTL, chuẩn hóa identity và correlation đa chiều. Các ngưỡng số chỉ là minh họa.

### 10.1. Cấu trúc project

~~~text
login-defense-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/logindefense/
    │   │   ├── LoginDefenseApplication.java
    │   │   ├── LoginAttemptGuard.java
    │   │   ├── LoginThrottleFilter.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── ProfileController.java
    │   └── resources/application.yml
    └── test/java/com/example/logindefense/
        └── LoginAttemptGuardTest.java
~~~

### 10.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>login-defense-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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
~~~

Dự án dùng `spring-boot-starter-security` và password encoder chuẩn của Spring. Không tự dùng SHA-256 trần hoặc so sánh password plaintext.

### 10.3. `application.yml`

~~~yaml
server:
  port: 8080

demo:
  user:
    password: ${DEMO_USER_PASSWORD}
~~~

Khi chạy, cung cấp `DEMO_USER_PASSWORD` từ biến môi trường. Demo local chỉ tạo tài khoản `alice`; không dùng credential test ở production và không in password ra log.

### 10.4. `LoginDefenseApplication.java`

~~~java
package com.example.logindefense;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoginDefenseApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginDefenseApplication.class, args);
    }
}
~~~

### 10.5. `LoginAttemptGuard.java`: hai token buckets độc lập

~~~java
package com.example.logindefense;

import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Component;

@Component
public final class LoginAttemptGuard {

    private final ConcurrentMap<String, TokenBucket> byAccount =
            new ConcurrentHashMap<>();
    private final ConcurrentMap<String, TokenBucket> bySource =
            new ConcurrentHashMap<>();

    public boolean allow(String submittedUsername, String remoteAddress) {
        if (submittedUsername == null || remoteAddress == null) {
            return false;
        }

        String account = submittedUsername.trim()
                .toLowerCase(Locale.ROOT);

        if (account.isBlank() || account.length() > 150) {
            return false;
        }

        // Source bucket: burst 20, refill 1 request / 3 seconds.
        TokenBucket sourceBucket = bySource.computeIfAbsent(
                remoteAddress, key -> new TokenBucket(20, 1.0 / 3.0));

        // Account bucket: burst 5, refill 1 request / 60 seconds.
        TokenBucket accountBucket = byAccount.computeIfAbsent(
                account, key -> new TokenBucket(5, 1.0 / 60.0));

        // Two INDEPENDENT checks: never use one "IP:username" key.
        boolean sourceAllowed = sourceBucket.take();
        boolean accountAllowed = accountBucket.take();
        return sourceAllowed && accountAllowed;
    }

    static final class TokenBucket {
        private final double capacity;
        private final double refillPerSecond;
        private double tokens;
        private long lastNanos;

        TokenBucket(int capacity, double refillPerSecond) {
            this.capacity = capacity;
            this.refillPerSecond = refillPerSecond;
            this.tokens = capacity;
            this.lastNanos = System.nanoTime();
        }

        synchronized boolean take() {
            long now = System.nanoTime();
            long elapsedNanos = Math.max(0L, now - lastNanos);
            double elapsedSeconds = elapsedNanos / 1_000_000_000.0;
            tokens = Math.min(
                    capacity, tokens + elapsedSeconds * refillPerSecond);
            lastNanos = now;

            if (tokens < 1.0) {
                return false;
            }
            tokens -= 1.0;
            return true;
        }
    }
}
~~~

**Phân tích:**
- `byAccount` bảo vệ một user khỏi nguồn IP phân tán; `bySource` bảo vệ hệ thống khỏi một source thử hàng loạt username.
- `synchronized take()` giúp cập nhật token **nguyên tử trong một JVM cho một bucket**; không có tính nguyên tử xuyên replica.
- Trừ hai bucket không được gom trong cùng transaction; nếu account bucket từ chối thì source bucket vẫn có thể bị trừ, làm chính sách bảo thủ hơn. Với ứng dụng thật phải mô tả rõ semantics và xem xét atomic multi-key logic.
- Các ngưỡng 5 và 20 ở đây dùng để học về burst; **không phải giới hạn mặc định do Spring Security hoặc NIST quy định**.
- `toLowerCase(Locale.ROOT)` chỉ là cách chuẩn hóa ví dụ cho username demo. Với username/email thật, chuẩn hóa phải phù hợp **cùng chính sách lookup trong UserDetailsService**, không tự xóa dấu chấm hoặc `+` của email.
- Map sẽ tăng mãi nếu attacker gửi vô số usernames/IPs. Production bắt buộc có expiration/maximum size và quota ở lớp edge để chống memory DoS.
- Source key lấy từ kết nối thực đến ứng dụng. Khi backend nằm sau proxy, không tin `X-Forwarded-For` do client tự gửi; cần trusted proxy configuration hoặc thực thi limit ở gateway.

### 10.6. `LoginThrottleFilter.java`

~~~java
package com.example.logindefense;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

public final class LoginThrottleFilter extends OncePerRequestFilter {

    private final LoginAttemptGuard guard;

    public LoginThrottleFilter(LoginAttemptGuard guard) {
        this.guard = guard;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        boolean loginPost = "POST".equalsIgnoreCase(
                request.getMethod())
                && "/login".equals(request.getServletPath());

        if (!loginPost) {
            chain.doFilter(request, response);
            return;
        }

        String username = request.getParameter("username");
        String source = request.getRemoteAddr();

        if (!guard.allow(username, source)) {
            response.setStatus(429);
            response.setHeader("Cache-Control", "no-store");
            response.setContentType("text/plain;charset=UTF-8");
            response.getWriter().write(
                    "Too many requests. Please try again later.");
            return;
        }

        chain.doFilter(request, response);
    }
}
~~~

- `getServletPath()` phù hợp demo chạy root context; nếu app dùng custom servlet mapping/context hoặc login processing URL khác, cần cấu hình matcher đúng.
- `request.getParameter("username")` đúng với form login mặc định. Nếu app dùng JSON login, filter này **không đọc JSON**; thiết kế limiter phù hợp authentication endpoint JSON.
- Không đưa password vào limit key, log hoặc response.
- Khi từ chối, filter trả `429` trước khi password được hash. Đây không phải `AuthenticationFailureHandler` thông thường, vì Spring chưa thử xác thực.
- Filter được khởi tạo trực tiếp trong `SecurityFilterChain`, **không đăng ký như servlet `@Component Filter`** để tránh chạy hai lần.

### 10.7. `SecurityConfiguration.java`

~~~java
package com.example.logindefense;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.user.password}") String password) {
        var alice = User.withUsername("alice")
                .password(encoder.encode(password))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            LoginAttemptGuard guard) throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error").permitAll()
                        .requestMatchers("/me").authenticated()
                        .anyRequest().denyAll())
                .formLogin(Customizer.withDefaults())
                .addFilterBefore(
                        new LoginThrottleFilter(guard),
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
~~~

- `formLogin` kích hoạt trang login mặc định và cơ chế kiểm tra password của Spring; code không tự so sánh string password.
- Filter đặt **trước** `UsernamePasswordAuthenticationFilter`; `anyRequest().denyAll()` chặn các route không được công bố.
- **Giữ CSRF protection mặc định** cho form browser. Khi login qua trang `/login` do Spring sinh, form có CSRF token tương ứng; request curl không có CSRF có thể bị 403 trước khi đến password verifier, không phải minh chứng rate limit.
- `PasswordEncoderFactories` tạo delegating encoder dùng password hash phù hợp; production cần thiết lập work factor và chính sách cập nhật encoder cụ thể.
- Khi bị rate limit, không phân biệt username tồn tại hay không trong response.

### 10.8. `ProfileController.java`

~~~java
package com.example.logindefense;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {
    @GetMapping("/me")
    public Map<String, Object> me(Authentication authentication) {
        return Map.of(
                "username", authentication.getName(),
                "authenticated", authentication.isAuthenticated());
    }
}
~~~

Endpoint này dành cho xác minh session sau login; không log/hiển thị password hoặc security context đầy đủ.

### 10.9. Chạy demo trong local browser

Linux/macOS:

~~~bash
export DEMO_USER_PASSWORD='local-test-password-only'
mvn spring-boot:run
~~~

PowerShell:

~~~powershell
$env:DEMO_USER_PASSWORD = "local-test-password-only"
mvn spring-boot:run
~~~

Mật khẩu trên chỉ là ví dụ local, **không dùng ở môi trường có người khác truy cập**. Mở `http://localhost:8080/login` trong browser, nhập username `alice` với password demo, sau đó truy cập `http://localhost:8080/me`. Khi login hợp lệ, nhận JSON tương đương:

~~~json
{"username":"alice","authenticated":true}
~~~

Thứ tự khóa JSON không cố định. Khi có nhiều request `POST /login` trong một cửa sổ ngắn vượt quota, filter có thể trả HTTP `429`. Không cần thử mật khẩu của bên thứ ba; tất cả kiểm thử chỉ trên account demo sở hữu bởi người phát triển.

**Lưu ý:** Việc limit áp dụng cho **mỗi attempt**, kể cả đúng password. Điều này tránh một số race trong mô hình demo, nhưng có thể gây UX không tốt khi login hợp lệ bị từ chối vì quota. Production cân nhắc giới hạn linh hoạt, risk scoring, MFA/step-up và cơ chế hỗ trợ người dùng mà không mở bypass.

## 11. Kiểm thử bằng JUnit 5 cho hai bucket độc lập

Thêm file `src/test/java/com/example/logindefense/LoginAttemptGuardTest.java`:

~~~java
package com.example.logindefense;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class LoginAttemptGuardTest {

    @Test
    void sixthRapidAttemptForSameAccountIsLimited() {
        LoginAttemptGuard guard = new LoginAttemptGuard();

        for (int i = 0; i < 5; i++) {
            assertTrue(guard.allow("alice", "source-" + i));
        }

        assertFalse(guard.allow("alice", "fresh-source"));
    }

    @Test
    void sourceSweepingManyAccountsIsLimited() {
        LoginAttemptGuard guard = new LoginAttemptGuard();

        for (int i = 0; i < 20; i++) {
            assertTrue(guard.allow("account-" + i, "same-source"));
        }

        assertFalse(guard.allow("account-20", "same-source"));
    }

    @Test
    void usernameNormalizationUsesSameAccountBucket() {
        LoginAttemptGuard guard = new LoginAttemptGuard();

        for (int i = 0; i < 5; i++) {
            assertTrue(guard.allow("ALICE", "source-" + i));
        }

        assertFalse(guard.allow("alice", "another-source"));
    }

    @Test
    void badUsernameIsRejected() {
        LoginAttemptGuard guard = new LoginAttemptGuard();
        assertFalse(guard.allow("", "source"));
        assertFalse(guard.allow(null, "source"));
    }
}
~~~

Chạy từ thư mục project:

~~~bash
mvn test
~~~

**Kỳ vọng**: 4 tests PASS, số lượng test/format stdout phụ thuộc Maven Surefire/JUnit version. Đây là test chính sách **burst trong một JVM**, không chứng minh chống botnet/cross-instance/lockout DoS. Vì bucket sẽ nạp thêm theo thời gian thực, không dùng test có sleep dài hoặc phụ thuộc tường minh vào tốc độ CPU; để kiểm thử refill lâu dài một cách quyết định, nên inject monotonic clock/ticker trong implementation.

### Kiểm thử request bằng MockMvc hoặc browser

Kiểm tra ít nhất:
1. `GET /login` hiển thị form có CSRF.
2. `POST /login` thiếu CSRF bị chặn theo policy.
3. Login hợp lệ với `alice` và password demo tạo session.
4. Login sai tạo generic error, không lộ “user exists” hay loại exception.
5. Khi vượt account bucket, dù request đến từ nhiều nguồn test khác nhau, trả `429`.
6. Khi vượt source bucket, dù username thay đổi, trả `429`.
7. Bypass qua `/login` URL khác, mixed case path, JSON login, SSO fallback phải được ngăn theo cấu hình thực.
8. Body/header quá dài, duplicate parameters hoặc username malformed không làm hỏng parser hoặc cấp unlimited bucket.
9. Khi limiter store lỗi, có hành vi được đánh giá; không âm thầm mở cổng không giới hạn.
10. Khi logout/session đã hết hạn, endpoint `/me` không trả nội dung xác thực.

**Không dùng kiểm thử tự động vào dịch vụ người khác hoặc production không được cấp phép.** Một test phòng thủ có thể dùng fake users và in-process MockMvc để đánh giá mà không cần tạo lưu lượng nguy hiểm.

## 12. Bổ sung failure/success telemetry trong Spring Security

Giới hạn request trước authentication giúp giảm tải, nhưng để phát hiện credential stuffing **có password đúng**, vẫn cần sự kiện login success/failure.

Spring Security có `AuthenticationFailureHandler`, `AuthenticationSuccessHandler` và cơ chế authentication events. Với cấu hình phù hợp, có thể khai báo:

~~~java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher applicationEventPublisher) {
    return new DefaultAuthenticationEventPublisher(
            applicationEventPublisher);
}
~~~

Đoạn trên là **mảnh cấu hình mở rộng**, cần import `org.springframework.security.authentication.AuthenticationEventPublisher`, `DefaultAuthenticationEventPublisher` và `org.springframework.context.ApplicationEventPublisher`. Khi muốn dùng `@EventListener` với `AuthenticationFailureBadCredentialsEvent` hoặc `AuthenticationSuccessEvent`, đăng ký publisher và kiểm tra thực tế event nào được phát từ authentication manager của bạn.

**Đừng dựa riêng vào failure events:** request bị `LoginThrottleFilter` trả 429 **chưa đi qua AuthenticationManager**, nên sẽ không tự phát AuthenticationFailureEvent. Filter/gateway phải phát metrics `login_throttled` độc lập. Event handler cũng không được log `Authentication.getCredentials()`, raw password hay toàn bộ `Authentication.toString()`.

Các field log bảo mật hợp lý:
- thời điểm UTC, request ID/correlation ID;
- result `SUCCESS`, `BAD_CREDENTIALS`, `RATE_LIMITED`, `MFA_FAILED`, `CHALLENGE_REQUIRED`;
- account ID đã hash/pseudonymized nếu policy cho phép, không log email nguyên văn nếu không cần;
- trusted remote IP/ASN/region theo policy privacy;
- source system, tenant, risk score/bucket category (chỉ trong log nội bộ);
- session ID **không được log plaintext**, thay bằng correlation ID không thể làm credential;
- không có raw password, token, CSRF token, Authorization/Cookie header.

## 13. Phát hiện theo số liệu thực

### 13.1. Theo account

- Số lần thất bại trong 1/5/15 phút.
- Tỷ lệ fail/success và số IP/thiết bị mới.
- Password đúng nhưng MFA thất bại.
- Login thành công rồi ngay lập tức thay password/email, thêm API key hoặc tạo session mới bất thường.
- Những lần throttle hoặc lockout liên tiếp làm user hợp lệ bị gián đoạn.

### 13.2. Theo source/campaign

- Số **tài khoản khác nhau** một source thử trong thời gian ngắn/dài.
- Số nguồn khác nhau nhắm cùng một tài khoản.
- Số request/độ trễ từ một ASN, cloud hosting hay proxy network.
- Sự thay đổi của tỷ lệ 401, 403, 429 và tỷ lệ login success.
- Mức đồng thời/pattern automation, CAPTCHA solve rate, lượng token từ bot mitigation.
- Tỷ lệ thành công từ các account trước đây hiếm khi đăng nhập.

### 13.3. Theo tenant / sản phẩm

- Campaign nhắm hàng loạt user của một tổ chức.
- Tăng đột biến account takeover indicators sau một thông báo breach.
- So sánh rủi ro admin vs user thông thường.
- Lượng password reset/recovery ngay sau cảnh báo login.
- Số người dùng bị false positive vì NAT của văn phòng hoặc shared mobile carrier.

**Không cần lưu password để phân biệt spraying và stuffing**. Sự khác biệt được suy luận từ nguồn dữ liệu rò rỉ, đặc tính chiến dịch, mức thành công và correlation hợp lệ. Thu thập theo nguyên tắc tối thiểu dữ liệu, retention rõ ràng và quyền truy cập giới hạn.

## 14. Tình huống đánh đổi: không có một ngưỡng cố định cho tất cả

### Tình huống A: một account bị thử nhiều lần

Nếu `alice` có nhiều login fail, dù đổi IP, per-account bucket tiến tới throttle. Có thể thêm delay hoặc yêu cầu MFA/step-up sau khi vượt ngưỡng. **Không tự động khóa vĩnh viễn account Alice** chỉ từ dấu hiệu bên ngoài.

### Tình huống B: một IP thử nhiều account

Nếu nhiều username khác nhau cùng source, per-source bucket và distinct-account detector cảnh báo. Không chờ mỗi user đạt ngưỡng 5 lần vì spraying có thể chỉ thử một password trên mỗi account.

### Tình huống C: nhiều proxy thử credential rò rỉ, một lần/user

Per-account bucket có thể không kích hoạt; per-IP cũng có thể không. Cần correlation trên ASN/device/session/login velocity, breached-password checks, MFA và hành vi sau login. **Một login password đúng chưa đủ để chứng minh là chủ account hợp lệ**.

### Tình huống D: shared IP văn phòng

Một IP của trường học/công ty có hàng trăm người đăng nhập hợp lệ, per-IP quá thấp sẽ tạo 429 hàng loạt. Điều chỉnh thresholds/allowlisting có kiểm soát dựa trên trusted edge, bổ sung per-account limit và risk signals; không mở toàn bộ giới hạn vì một shared IP.

### Tình huống E: attacker gây account lockout DoS

Attacker cố tình gửi sai password vào nhiều account để kích hoạt khóa cứng. Thay hard lock dài bằng progressive delay, risk-based controls và recovery. Thiết kế phân biệt login tự nguyện với traffic đáng ngờ mà vẫn bảo vệ brute-force.

## 15. Lỗi phổ biến khi triển khai

1. **Chỉ rate limit theo IP:** botnet/proxy rotation vẫn có thể nhắm một account.
2. **Chỉ rate limit theo username:** spraying/stuffing mỗi account một lần rất khó bị chặn.
3. **Chỉ dùng key `IP:username`:** tạo quota riêng cho vô hạn tổ hợp.
4. **Bucket RAM cho cluster:** mỗi pod có quota riêng; tăng pod vô tình tăng khả năng thử.
5. **Không giới hạn kích thước key map:** attacker tạo nhiều username giả làm memory DoS.
6. **Dùng `X-Forwarded-For` từ client tự gửi:** có thể giả source và bypass theo IP.
7. **Khóa cứng account trong nhiều giờ chỉ vì thử sai:** trở thành denial of service.
8. **CAPTCHA là biện pháp duy nhất:** có thể bị vượt, gây accessibility issues.
9. **MFA có đường reset/recovery yếu:** attacker bypass bằng khôi phục account.
10. **Giữ mật khẩu bị lộ nhưng chỉ tăng độ phức tạp:** vẫn dễ bị stuffing nếu password đã đúng; cần phát hiện breached password và MFA.
11. **Trả thông báo khác nhau cho user không tồn tại và password sai:** hỗ trợ enumeration.
12. **Log raw password/token hoặc toàn bộ request:** gây rò rỉ credential nghiêm trọng.
13. **Dùng số lượng failure làm tiêu chí duy nhất:** credential stuffing có thể thành công ở lần đầu.
14. **Quên path JSON/mobile/legacy Basic:** attacker chọn đường không có limiter.
15. **Giới hạn sau password hashing:** không giảm nhiều tải CPU do bot gây ra.
16. **Thiếu test đồng thời:** race trong Redis/DB có thể cho phép vượt ngưỡng.
17. **Trộn IP của proxy với IP người dùng:** cả hệ thống bị coi là một nguồn.
18. **Tin User-Agent/device ID như danh tính đã chứng thực:** dữ liệu client có thể spoof.
19. **Không có cảnh báo user sau login bất thường:** hậu quả ATO kéo dài.
20. **Tin Spring formLogin mặc định đã chống mọi bot:** cần policy bổ sung ở login, gateway, IdP và domain.

## 16. Ma trận kiểm thử phòng thủ

| Trường hợp | Điều muốn xác minh |
|---|---|
| Một account nhiều lần thử, cùng IP | Per-account limit chặn burst |
| Một account nhiều lần thử, khác IP | Per-account limit vẫn chặn |
| Nhiều account, cùng IP | Per-source limit vẫn chặn |
| Nhiều account, nhiều IP, tốc độ thấp | Campaign detector/correlation phát hiện |
| Một login đúng password nhưng MFA sai | Không tạo authenticated session, có risk signal |
| Một login đúng password trên thiết bị lạ | MFA/step-up hoặc risk policy đúng |
| User không tồn tại vs password sai | Message/status/timing không tiết lộ account |
| Login thiếu CSRF | Browser form bị CSRF policy chặn |
| Request có username quá dài | Bị giới hạn trước khi ghi state vô hạn |
| User nhập email khác hoa/thường | Canonicalization theo contract chung |
| User `alice` qua `/login` và JSON login | Cùng chính sách cho mọi entry point |
| Shared IP có nhiều user hợp lệ | False positives được đo và hiệu chỉnh |
| Burst ở ranh giới phút | Sliding/token bucket không hở fixed-window burst |
| Nhiều request đồng thời trên cùng bucket | Không vượt quota do race |
| 3 instance + một Redis | Giới hạn toàn cluster, không nhân quota theo instance |
| Redis/gateway lỗi | Không âm thầm mở vô hạn; policy dự phòng được test |
| Account bị hard-lock do attacker | Có khôi phục và phòng DoS |
| CAPTCHA không thể hoàn tất | Không bỏ hẳn authentication controls hoặc accessibility |
| Filter chặn request 429 | Có metrics throttle ngay cả khi không có authentication failure event |
| Login success rồi hành vi rủi ro | Audit/alert/step-up ở endpoint nhạy cảm |
| Session cũ sau reset/compromise | Được invalidated/revalidated theo policy |
| Password reset/forgot-password | Không tạo đường enumeration/bypass limit |
| API key/SSO/legacy Basic | Có chính sách phù hợp thay vì bypass |
| Log và tracing | Không chứa raw password, CSRF token, session ID hoặc bearer token |

**Đo lường false positives cùng detection rate**: cấu hình chặn sạch bot nhưng làm hàng loạt người dùng hợp lệ không vào được hệ thống không phải thiết kế thành công. Áp dụng rollout theo audit-only → challenge/soft throttle → block, giám sát tỷ lệ lỗi và có rollback plan.

## 17. Checklist production

- [ ] Tất cả điểm xác thực username/password đều được kiểm kê, bao gồm mobile, API, admin, fallback.
- [ ] Có rate limit độc lập theo account và source; không chỉ ghép IP:username.
- [ ] Có phát hiện spraying/stuffing phân tán bằng tín hiệu aggregate và cửa sổ ngắn/dài.
- [ ] Limiter được chia sẻ giữa replica, cập nhật nguyên tử, TTL/eviction và giới hạn dung lượng.
- [ ] Origin IP được xác định qua trusted proxy, không tin header client.
- [ ] Threshold, window, delay, CAPTCHA và lockout được đo false positives/DoS.
- [ ] Không để attacker khóa vĩnh viễn người dùng chỉ bằng thử sai password.
- [ ] MFA/passkey được yêu cầu phù hợp rủi ro, nhất là admin và login lạ.
- [ ] Password được lưu bằng strong password hash; password bị lộ được sàng lọc khi đổi/đặt mới.
- [ ] Error message/login status không hỗ trợ enumeration.
- [ ] CSRF/session fixation/cookie security vẫn được bảo vệ trong browser login.
- [ ] Authentication success/failure và throttled request đều có metrics riêng.
- [ ] Không log raw password, header Authorization, Cookie/session ID hoặc các token bí mật.
- [ ] Có alert cho abnormal success, MFA failure, session takeover, thay email/password.
- [ ] Có quy trình incident response: buộc reset/thu hồi session/token, liên hệ người dùng, tăng kiểm soát tạm thời.
- [ ] Đã test concurrency, multi-replica, store outage, NAT/shared IP, browser accessibility.
- [ ] Trường hợp IdP/SSO: policy được bật ở nơi thực tế kiểm tra password.

## 18. Ghi nhớ

- **Brute force:** nhiều password nhắm vào **một account** → per-account velocity là tín hiệu chính.
- **Password spraying:** một/vài password nhắm vào **nhiều account** → xem distinct accounts/source/campaign.
- **Credential stuffing:** sử dụng **credential pairs đã rò rỉ** → một lần thử có thể thành công; MFA/passkey và phát hiện bất thường sau login rất quan trọng.

**Giải pháp không nằm ở một ngưỡng cố định:** kết hợp hai bucket độc lập account + source, correlation ở edge và ứng dụng, MFA/WebAuthn, breached-password screening, thông báo lỗi chung, audit an toàn và cơ chế không biến login throttling thành công cụ DoS. Spring Security cung cấp điểm mở rộng để tích hợp các lớp này, nhưng chính sách phát hiện và lưu trạng thái chống automation vẫn cần được thiết kế riêng.

## 19. Tài liệu tham khảo

1. [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): phân loại brute force/spraying/stuffing, login throttling, lockout, generic errors, logging.
2. [OWASP — Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html): MFA, IP intelligence, device signals, detection, defense in depth.
3. [OWASP — Bot Management and Anti-Automation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Bot_Management_and_Anti-Automation_Cheat_Sheet.html): edge/application/backend layers, per-account vs per-source quotas.
4. [NIST SP 800-63B-4 — Authentication and Authenticator Management](https://pages.nist.gov/800-63-4/sp800-63b.html): online guessing/throttling controls và giới hạn thử thất bại.
5. [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): `UsernamePasswordAuthenticationFilter`, authentication success/failure handler.
6. [Spring Security 6.5 — Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html): `DefaultAuthenticationEventPublisher`, success/failure events.
7. [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`, `AuthenticationProvider`, `SecurityContext`.
8. [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): secure password hashing và work factor.
9. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): login security logs và loại bỏ thông tin bí mật.
