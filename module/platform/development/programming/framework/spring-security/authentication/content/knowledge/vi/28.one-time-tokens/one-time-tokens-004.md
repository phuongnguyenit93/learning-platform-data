# OneTimeTokenService: tạo, lưu và tiêu thụ token dùng một lần trong Spring Security

## 1. Mục tiêu và phạm vi

**One-Time Token (OTT)** trong Spring Security là một giá trị bí mật được cấp cho một mục đích xác thực, gắn với danh tính người dùng và thời điểm hết hạn; sau lần sử dụng hợp lệ đầu tiên, giá trị ấy không được dùng để xác thực lần thứ hai. Trường hợp thường gặp là **magic link** gửi qua email: người dùng yêu cầu một đường dẫn đăng nhập, mở email, rồi gửi token từ đường dẫn tới ứng dụng.

Trọng tâm của bài là interface **`OneTimeTokenService`** và trọn vòng đời **tạo → lưu → chuyển giao → kiểm tra/tiêu thụ → xác thực**, trong module *Spring Security - authentication*, nhóm *Token dùng một lần*. Sau bài học, bạn cần:

1. Gọi đúng `generate(GenerateOneTimeTokenRequest)` và `consume(OneTimeTokenAuthenticationToken)`, hiểu các kiểu dữ liệu và ý nghĩa khi token không hợp lệ.
2. Phân biệt trách nhiệm của `OneTimeTokenService`, `OneTimeTokenGenerationSuccessHandler`, `OneTimeTokenAuthenticationProvider` và `UserDetailsService`.
3. Lựa chọn `InMemoryOneTimeTokenService` hay `JdbcOneTimeTokenService`, biết ràng buộc khi triển khai nhiều node và khi ứng dụng khởi động lại.
4. Giải thích được vì sao “single use” phải **nguyên tử (atomic)** khi hai request sử dụng cùng một token đồng thời.
5. Thiết kế token đủ entropy, TTL ngắn, bảo vệ khi lưu/chuyển giao, xử lý token hết hạn/đã dùng/không tồn tại và lỗi gửi email.
6. Cấu hình Spring Security Servlet và hiểu phiên bản Reactive WebFlux tương ứng; thực hành Java 17+ và kiểm thử vòng đời.

**Baseline thực hành:** Spring Security **6.5.x** (chức năng có từ 6.4), Spring Boot **3.5.x**, Java 17+. Với Spring Security 7.x, đối chiếu javadoc theo phiên bản trước khi tái sử dụng mã; ví dụ Servlet và WebFlux không được trộn lẫn. Bài chỉ nói về OTT phục vụ đăng nhập, không biến mọi loại mã OTP, password reset và OAuth token thành một cơ chế duy nhất.

## 2. OTT không phải TOTP, HOTP, access token hay session

| Loại | Nơi tạo / kiểm tra | Quy tắc dùng | Ví dụ |
| --- | --- | --- | --- |
| **Spring Security One-Time Token** | Server tạo; `OneTimeTokenService` lưu và consume | Dùng tối đa một lần trong TTL, thường gắn username | Magic link đăng nhập |
| **TOTP** | Client authenticator và server cùng tính từ secret + thời gian | Mã thay đổi theo cửa sổ thời gian; kiểm soát replay tùy triển khai | Ứng dụng Authenticator |
| **HOTP** | Client/server dựa trên secret + counter | Đồng bộ counter, chống dùng lại theo chính sách | OTP counter-based |
| **OAuth access token** | Authorization Server phát hành; Resource Server kiểm tra | Thường sử dụng được nhiều lần tới khi hết hạn/thu hồi | Bearer token gọi API |
| **HTTP session cookie** | Ứng dụng / session store quản lý | Nhận diện phiên đã được tạo; có thể sống qua nhiều request | `JSESSIONID`, `SESSION` |

Spring Security OTT **không yêu cầu người dùng cài ứng dụng OTP hoặc chia sẻ trước một khóa TOTP**. Server phát hành token và phải chuyển token cho chủ tài khoản bằng một kênh phù hợp như email. Mặc định framework không thể biết email nào đúng, cần cấu hình success handler/dịch vụ gửi riêng.

Token OTT chỉ là **credential ngắn hạn để đạt được một lần đăng nhập**. Sau khi xác thực thành công, ứng dụng thường tạo SecurityContext và phiên đăng nhập như quy tắc Spring Security hiện hành. Token OTT không trở thành session cookie, và việc đã tiêu thụ token không có nghĩa phiên vừa tạo cũng chỉ dùng được một lần.

Cũng cần tách mục đích **password reset** và **email verification**: dù cùng thiết kế một lần, chúng có audience/purpose, endpoint, chính sách kiểm tra danh tính và hậu quả khác nhau. Không tái sử dụng token “login” để tự động đổi mật khẩu, đổi email hoặc kích hoạt quyền nhạy cảm.

## 3. API OneTimeTokenService và các kiểu liên quan

Theo javadoc Spring Security 6.5, interface nằm ở:

```java
org.springframework.security.authentication.ott.OneTimeTokenService
```

Hợp đồng cốt lõi:

```java
// Hình dạng API để giải thích; khai báo trong framework, không tự định nghĩa lại.
public interface OneTimeTokenService {
    OneTimeToken generate(GenerateOneTimeTokenRequest request);
    @Nullable
    OneTimeToken consume(OneTimeTokenAuthenticationToken authenticationToken);
}
```

Các kiểu quan trọng:

| Kiểu | Vai trò | Dữ liệu/đặc điểm |
| --- | --- | --- |
| `GenerateOneTimeTokenRequest` | Yêu cầu phát hành | `getUsername()`, `getExpiresIn()`; constructor `(String)` và `(String, Duration)` |
| `OneTimeToken` | Token đã tạo hoặc được consume thành công | `getTokenValue()`, `getUsername()`, `getExpiresAt()` |
| `DefaultOneTimeToken` | Implementation thông dụng của `OneTimeToken` | Constructor `(String token, String username, Instant expireAt)` |
| `OneTimeTokenAuthenticationToken` | Authentication request mang giá trị token | `unauthenticated(String)` hoặc `new OneTimeTokenAuthenticationToken(String)`; `getTokenValue()` |
| `OneTimeTokenService` | Sinh, lưu và tiêu thụ | `generate(...)` trả token không null; `consume(...)` trả token hoặc null |
| `OneTimeTokenAuthenticationProvider` | Đăng nhập bằng token | Gọi service để consume, sau đó dùng `UserDetailsService` để nạp user/authorities |
| `OneTimeTokenGenerationSuccessHandler` | Chuyển token sau generate | Gửi mail/SMS theo ứng dụng; **không tự xác thực user** |

**Chính xác tên tham số `consume`:** Trong Spring Security 6.5, nó nhận **`OneTimeTokenAuthenticationToken`**, không nhận `ConsumeOneTimeTokenRequest` và không nhận raw `String`. Đây là khác biệt dễ gây lỗi compile nếu nhìn nhầm API của thư viện khác.

Ví dụ gọi service theo hợp đồng, **trích đoạn Java** đặt trong class có `OneTimeTokenService service`:

```java
OneTimeToken issued = service.generate(
        new GenerateOneTimeTokenRequest("alice", Duration.ofMinutes(5)));

String tokenValue = issued.getTokenValue();
Instant expiry = issued.getExpiresAt();

OneTimeTokenAuthenticationToken presented =
        OneTimeTokenAuthenticationToken.unauthenticated(tokenValue);

OneTimeToken consumed = service.consume(presented);

if (consumed == null) {
    // Không tìm thấy, đã hết hạn, đã dùng, hoặc không hợp lệ.
    // Phản hồi phải fail closed; không tạo phiên đăng nhập.
}
```

Đoạn trên cần import từ `org.springframework.security.authentication.ott`, `java.time.Duration` và `java.time.Instant`. Nó minh họa API của service, **không phải controller hoặc chương trình chạy độc lập**.

Một `OneTimeToken` đã phát hành không có nghĩa đã xác thực; trạng thái được xác thực sau khi hệ thống kiểm tra token, ánh xạ đúng user và chạy những bước authentication còn lại.

## 4. Luồng end-to-end: generate, persist, deliver, consume

```text
User/browser                    Spring Security Servlet                    Storage / Mail
     |                                   |                                     |
     | POST /ott/generate                |                                     |
     | username=alice + CSRF             |                                     |
     |---------------------------------->| GenerateOneTimeTokenFilter           |
     |                                   | Resolve GenerateOneTimeTokenRequest   |
     |                                   | OneTimeTokenService.generate(...)     |
     |                                   |------------------------------------->| Save token + expiry
     |                                   |<-------------------------------------|
     |                                   | OneTimeTokenGenerationSuccessHandler |
     |                                   |------------------------------------->| Send magic link
     |<-------- generic confirmation ----|                                     |
     |                                   |                                     |
     |  User opens magic link            |                                     |
     | GET /login/ott?token=...          |                                     |
     |---------------------------------->| Render submit page; fill token form  |
     |  User submits POST /login/ott     |                                     |
     |  + CSRF token                     |                                     |
     |---------------------------------->| OneTimeTokenAuthenticationFilter     |
     |                                   | OneTimeTokenAuthenticationProvider   |
     |                                   | OneTimeTokenService.consume(...)      |
     |                                   |------------------------------------->| Atomically claim/delete if valid
     |                                   |<-------------------------------------|
     |                                   | UserDetailsService -> authorities     |
     |                                   | Establish authenticated session      |
     |<------------ login result -------|                                     |
```

Các bước cần hiểu:

1. **Generate**: nhận username/identifier đã chuẩn hóa và duration, tạo một giá trị ngẫu nhiên khó đoán, tính expiry và ghi trạng thái vào nơi lưu trữ.
2. **Persist**: dữ liệu tối thiểu giúp tra được token, danh tính gắn với token, thời gian hết hạn và trạng thái tiêu thụ; storage phải có tính nhất quán cần thiết.
3. **Deliver**: gửi URL hoặc token tới kênh người dùng kiểm soát. Spring Security không tự gửi email thay ứng dụng.
4. **Submit**: browser lấy token từ magic link và gửi POST đến login processing endpoint; trình duyệt có thể đi qua một trang trung gian trước khi submit.
5. **Consume**: service xác minh token còn tồn tại/chưa hết hạn/chưa dùng rồi **đánh dấu đã dùng hoặc xóa nguyên tử**. Chỉ một request được nhận dữ liệu valid.
6. **Authenticate**: provider tìm user/authorities theo username đã gắn với token; policy account như locked/disabled/expired vẫn có thể chặn đăng nhập.
7. **Session**: sau khi xác thực, Spring Security quản lý SecurityContext, session/cookie, logout và authorization riêng.

**Tách rõ hiệu ứng phụ:** Email được gửi **sau khi** token đã tạo; không coi gửi thành công là token đã được tiêu thụ. Nếu gửi thất bại, record có thể tồn tại tới expiry/cleanup. Nếu người dùng mở mail nhiều lần, chỉ một lần consume thành công.

## 5. Sinh token an toàn: entropy, TTL và danh tính

### 5.1. Giá trị token cần khó đoán

Mục tiêu của bearer-style magic link token là người ngoài không thể đoán trong TTL. `InMemoryOneTimeTokenService` mặc định dùng UUID ngẫu nhiên; khi tự implement, dùng `SecureRandom` với ít nhất 128 bit entropy, thường chọn 256 bit, mã hóa Base64 URL-safe không padding.

Ví dụ Java 17+ độc lập chỉ minh họa **sinh giá trị**, chưa lưu hoặc phát hành session. File `TokenValueDemo.java`:

```java
import java.security.SecureRandom;
import java.util.Base64;

public class TokenValueDemo {
    private static final SecureRandom RANDOM = new SecureRandom();

    static String newToken() {
        byte[] random = new byte[32];  // 256-bit random secret
        RANDOM.nextBytes(random);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(random);
    }

    public static void main(String[] args) {
        String value = newToken();
        System.out.println("characters=" + value.length());
        // Không in value vào console/log.
    }
}
```

Chạy:

```bash
javac TokenValueDemo.java
java TokenValueDemo
```

**Stdout chính xác** (số ký tự, không phải giá trị ngẫu nhiên):

```text
characters=43
```

Không dùng `Math.random()`, `Random` thường, counter tăng dần, timestamp hay chuỗi email được hash đơn thuần để làm token đăng nhập. UUID của default service là cách framework triển khai; ví dụ `SecureRandom` ở trên chỉ dành cho **custom storage/service** có yêu cầu về dạng token riêng.

### 5.2. Thời gian sống rõ ràng

`GenerateOneTimeTokenRequest(String, Duration)` cho phép khai báo TTL của request. Trong luồng sinh token mặc định, tài liệu Spring Security mô tả TTL thông thường **5 phút**; một ứng dụng có thể chỉnh request resolver. Không giả định mọi custom service đều áp dụng TTL mặc định y hệt khi chưa kiểm tra implementation.

Một token có `expiresAt`: cần kiểm tra dùng cùng nguồn thời gian đáng tin và điều kiện **hiện tại trước expiry**. Ví dụ phép kiểm tra được thể hiện bằng toán tử `now.isBefore(expiresAt)`; ở đúng expiry phải coi là hết hạn. Múi giờ phải biểu diễn qua `Instant`/UTC thay vì so chuỗi ngày giờ locale.

### 5.3. Danh tính gắn với token

`getUsername()` trong `OneTimeToken` là username định danh mà service/provider dùng để tìm `UserDetails`; nó không phải bằng chứng người yêu cầu ở form sở hữu email. Trong triển khai có nhiều tenant, cần ánh xạ và xác minh namespace/tenant qua directory đáng tin, tránh nhập một email bất kỳ rồi cho đăng nhập vào tài khoản khác cùng username.

Không nhận user ID từ tham số POST tiêu thụ token để thay thế username đã lưu. Token tự chọn danh tính theo record lúc cấp. Thí dụ nếu request consume mang `tokenValue` hợp lệ cho Alice nhưng body chứa `username=bob`, hệ thống không được dùng Bob.

## 6. Lưu trữ: InMemoryOneTimeTokenService

Spring Security Servlet có implementation:

```java
import org.springframework.security.authentication.ott.InMemoryOneTimeTokenService;
import org.springframework.security.authentication.ott.OneTimeTokenService;

OneTimeTokenService service = new InMemoryOneTimeTokenService();
```

Theo javadoc, implementation này dùng `ConcurrentHashMap` để giữ token đã tạo và `UUID` ngẫu nhiên làm token value; expired tokens có cơ chế dọn khi số lượng token đạt ngưỡng implementation. `consume` trả token khi còn hợp lệ hoặc `null` khi không thể dùng.

**Ưu điểm:** không cần database, tiện thử nghiệm chức năng/đọc API, dễ dùng cho một instance trong môi trường demo.

**Giới hạn quan trọng:**

- Lưu trong bộ nhớ của **một process**. Nếu restart/roll deployment, token chưa dùng sẽ mất.
- Khi dùng 2+ application replicas độc lập, request generate ở node A rồi consume ở node B có thể không thấy token. Sticky session không phải biện pháp bảo đảm tốt cho magic link được mở từ trình duyệt/thiết bị khác.
- TTL không có nghĩa record luôn được xóa chính xác tại thời điểm hết hạn; kiểm tra expiry tại consume và dọn record là hai việc khác nhau.
- Không coi default memory store là giải pháp phân tán có transactional guarantees xuyên node.
- Khả năng khôi phục, audit, giới hạn số token trên user và chính sách phát hành lại cần thiết kế bổ sung.

Trong ứng dụng một node chỉ dùng để học, default memory service giúp tập trung vào luồng API. Khi chuyển sang production nhiều node hoặc cần token tồn tại qua restart, chọn persistence chia sẻ.

## 7. JdbcOneTimeTokenService cho lưu trữ chung

Spring Security Servlet có `JdbcOneTimeTokenService`, nhận `JdbcOperations` (thường là `JdbcTemplate`):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.authentication.ott.JdbcOneTimeTokenService;
import org.springframework.security.authentication.ott.OneTimeTokenService;

// Trích đoạn trong class @Configuration:
@Bean
OneTimeTokenService oneTimeTokenService(JdbcOperations jdbc) {
    return new JdbcOneTimeTokenService(jdbc);
}
```

Đây là **trích đoạn Spring bean**, cần một `DataSource` và `JdbcOperations` thực sự được Spring Boot cấu hình. `JdbcOneTimeTokenService` yêu cầu bảng theo schema do Spring Security cung cấp ở classpath:

```text
classpath:org/springframework/security/core/ott/jdbc/one-time-tokens-schema.sql
```

Bạn phải tạo/migrate schema **trước khi** dùng service. Javadoc có thể cung cấp tên resource cho schema tham chiếu; khi triển khai PostgreSQL/MySQL/SQL Server, đối chiếu kiểu dữ liệu/index/DDL với dialect, cách quản lý migration và artifact phiên bản bạn dùng. Không tự đoán tên cột rồi cấu hình repository dựa trên một DDL tự viết chưa kiểm tra.

### 7.1. Dependency JDBC

Trong Spring Boot 3.5.x Servlet:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2' // Chỉ ví dụ H2 local; production chọn driver thật
}
```

Có thể dùng Flyway/Liquibase hoặc migration của tổ chức. Spring Security không tự biến một service bean thành một hệ thống migration hoàn chỉnh. Việc phát hành schema phải được kiểm soát khi deploy nhiều node; không để mọi node tự chạy DDL xung đột.

### 7.2. Cần hiểu hàm cleanup

`JdbcOneTimeTokenService` có `cleanupExpiredTokens()` và `setCleanupCron(String)`; tài liệu API mô tả lịch cleanup mặc định chạy định kỳ, có thể thay đổi/đưa vào scheduler quản trị riêng. Cleanup chỉ giúp giải phóng storage; **không** được thay thế điều kiện kiểm tra expiry ngay khi consume.

Nếu một token đã hết hạn nhưng record chưa được xóa, `consume` vẫn phải coi nó không hợp lệ. Nếu token đã được tiêu thụ thành công, không phụ thuộc cleanup chạy sau mới ngăn replay.

### 7.3. JDBC production không tự giải quyết toàn bộ rủi ro

Dùng chung database giúp cả node A và B nhìn cùng record, nhưng bạn vẫn cần đo:

- Transaction isolation và **atomic claim/consume** giữa các request đồng thời.
- Chi phí DB query/index trên token, contention, TTL cleanup và độ trễ.
- Bảo vệ dữ liệu token ở DB, backup, replica, logs và query tracing.
- Đảm bảo email gửi sau generate không khiến token bị lộ trong queue hoặc log.
- Quy định phát hành nhiều token cho một user: cho phép nhiều token còn hạn hay thu hồi token cũ khi phát hành mới? Đây là lựa chọn nghiệp vụ, không thể suy ra từ tên class.

Kiểm tra cách implementation JDBC của **đúng Spring Security version** thao tác transaction và bảo vệ token at rest. Đừng mặc định rằng một implementation đã hash/HMAC token trước khi lưu nếu tài liệu của phiên bản ấy không bảo đảm.

## 8. “Dùng một lần” là yêu cầu atomic: chống hai request đồng thời

### 8.1. Race condition kinh điển

Một custom service sai có thể làm:

```java
// PSEUDOCODE - KHÔNG AN TOÀN, KHÔNG DÙNG TRONG PRODUCTION.
Token row = repository.findByValue(rawToken);
if (row != null && !row.isUsed() && row.getExpiresAt().isAfter(now)) {
    repository.markUsed(row.getId());
    return row;
}
return null;
```

Hai request A/B có thể cùng đọc `isUsed=false` trước khi request nào cập nhật. Cả hai đều có thể được chấp nhận, phá tính một lần. `synchronized` trên một JVM cũng không bảo vệ khi nhiều replica.

```text
Time    Request A                 Request B
 t1     READ token: unused
 t2                               READ token: unused
 t3     UPDATE used=true
 t4                               UPDATE used=true
 t5     return valid              return valid   <- REPLAY THÀNH CÔNG
```

### 8.2. Claim token trong một thao tác DB nguyên tử

Với PostgreSQL, **minh họa SQL theo dialect**, một giải pháp custom là xóa record và nhận về dữ liệu nếu nó còn hạn:

```sql
-- Ví dụ thiết kế riêng; KHÔNG phải SQL mặc định của JdbcOneTimeTokenService.
DELETE FROM app_login_tokens
WHERE token_hash = :token_hash
  AND expires_at > CURRENT_TIMESTAMP
RETURNING user_id, tenant_id, expires_at;
```

Một row chỉ được một transaction xóa thành công; request tiếp theo không còn row để trả. Câu lệnh này giả định token đã được lookup bằng hash/HMAC và dữ liệu bảng hợp lệ. SQL khác có thể dùng `SELECT ... FOR UPDATE` trong transaction rồi `DELETE`, hoặc một conditional `UPDATE ... WHERE consumed_at IS NULL ... RETURNING` tùy DB. Không tách read/check/write thành các operation độc lập không có transaction hoặc không có điều kiện tranh chấp.

**Kiểm tra account ở thời điểm đăng nhập:** Có thể token được consume trước khi `UserDetailsService` phát hiện user đã bị khóa/xóa; khi đó token đã bị đốt và đăng nhập thất bại. Đây là hành vi an toàn theo hướng fail closed, không phải lý do tự khôi phục lại token đã tiêu thụ.

### 8.3. Các bất biến nên đưa vào test

1. `generate` trả token không null, có username/expiry/giá trị.
2. Consume token hợp lệ trả đúng username **duy nhất một lần**.
3. Consume lại cùng token sau đó trả `null` (hoặc `Mono.empty()` ở reactive).
4. Consume giá trị không tồn tại/không đúng phải thất bại, không tạo authentication.
5. Token hết hạn phải thất bại, dù record chưa được dọn.
6. Hai request consume cạnh tranh cùng một token có **đúng một winner** ở mọi instance/node liên quan.
7. Thời điểm chính xác ở ngưỡng `expiresAt` phải thống nhất.
8. Token cho user A không thể được replay/đổi thành user B bằng request parameter.

## 9. Bảo vệ token khi lưu, truyền và hiển thị

### 9.1. Có nên lưu raw token?

Nếu kẻ tấn công đọc được database chứa raw token chưa dùng, họ có thể chiếm phiên tương lai trong TTL. Với **custom service**, nên cân nhắc lưu **digest được thiết kế phù hợp**, ví dụ `HMAC-SHA-256` với server-side secret/pepper bảo vệ riêng, hoặc SHA-256 khi raw token thực sự có đủ entropy và thiết kế threat model cho phép. Lookup token bằng digest, không phải cleartext:

```text
raw token  --HMAC with server secret--> token_hash
             |                              |
       deliver to user              persist in database
       (không log)                   (không lưu raw token)
```

Những điểm cần tính khi custom storage:

- Key/pepper của HMAC nằm trong secret manager, không trong DB dump; hỗ trợ rotation và versioning.
- Raw token vẫn phải đi qua kênh delivery, nhưng không đi vào metrics, exception text, audit log hoặc tracing span.
- Query bằng digest có index phù hợp; so sánh với một hệ thống lưu plaintext phải có phép đo và policy bảo vệ backup/replica.
- Dùng một digest method nhất quán cho generate/consume, không dùng `String.hashCode()` (không phải hàm băm mật mã).
- Nếu token chỉ có entropy thấp, việc hash đơn thuần không cứu được khỏi brute force; trước hết phải tăng entropy.

**Không tuyên bố `JdbcOneTimeTokenService` mặc định đã dùng HMAC** nếu chưa xác minh source của phiên bản được triển khai. Yêu cầu lưu hashed token có thể dẫn đến quyết định viết custom `OneTimeTokenService`.

### 9.2. Magic link có token trong URL: giới hạn rủi ro

Magic link thường có dạng:

```text
https://accounts.example.org/login/ott?token=<secret>
```

Giá trị sau dấu `?token=` là credential nhạy cảm. Nó có thể xuất hiện trong browser history, reverse-proxy access logs, referrer headers, email security scanners, screenshots hoặc analytics. Cần thiết kế:

- Bắt buộc HTTPS trên public domain; validate public base URL từ cấu hình tin cậy thay vì ghép `Host` request không kiểm soát.
- Hạn chế/khử query logging ở proxy/app; không đưa token vào hệ thống analytics hoặc tracking.
- Trang chứa token phải tránh third-party scripts, pixel, image từ domain ngoài; dùng `Referrer-Policy: no-referrer` hoặc policy nghiêm ngặt.
- `GET /login/ott?token=...` chỉ nên **hiển thị form** và đưa token vào form; **POST /login/ott` mới là bước thực sự consume** theo flow mặc định. Điều này giảm rủi ro email link preview/bot tự mở GET rồi tiêu thụ token.
- CSRF token hợp lệ vẫn cần cho POST theo cấu hình Spring Security; không tắt CSRF toàn ứng dụng vì magic link.
- Sau khi login, redirect tới URL sạch, xóa token khỏi thanh địa chỉ qua flow frontend phù hợp; không đưa credential sang referrer/Location tùy ý.
- TTL ngắn, dùng tối đa một lần và rate limiting phát hành/tiêu thụ, không để thử đoán token tốc độ cao.

Không hứa hẹn “URL hoàn toàn bí mật” nếu công nghệ browser/email vẫn có các bề mặt rò rỉ; phải giảm thời gian sống và bề mặt ghi log.

## 10. Spring Security Servlet: tích hợp với form và filters

### 10.1. DSL

Spring Security 6.5 hỗ trợ:

```java
// Trích đoạn trong SecurityFilterChain; formLogin là tùy chọn phù hợp UI demo.
http
    .formLogin(Customizer.withDefaults())
    .oneTimeTokenLogin(ott -> ott
        .tokenGenerationSuccessHandler(myHandler));
```

Các filter/chức năng chính thường gồm:

- `GenerateOneTimeTokenFilter` nhận `POST /ott/generate` theo mặc định, tạo `GenerateOneTimeTokenRequest` và gọi service.
- `OneTimeTokenGenerationSuccessHandler` nhận token đã được generate để quyết định giao token (email/SMS) rồi phản hồi chung.
- `DefaultOneTimeTokenSubmitPageGeneratingFilter` hỗ trợ `GET /login/ott` để hiển thị trang nhập token, tự điền nếu query chứa token.
- `OneTimeTokenAuthenticationFilter` xử lý `POST /login/ott` (CSRF theo policy), tạo authentication request.
- `OneTimeTokenAuthenticationProvider` dùng service để **consume** rồi dùng `UserDetailsService` để xác thực user và nạp authorities.
- `SecurityContext` và session được tạo/quản lý theo security chain như một đăng nhập thành công thông thường.

**Cần phân biệt GET và POST:** URL magic link `GET /login/ott?token=...` không nên bị coi như đã đăng nhập ngay; POST của form mới kích hoạt xác thực. Nếu tự viết trang submit, nhớ gửi cả token và CSRF token. Đừng viết một controller GET tự consume token chỉ để bỏ một bước, vì mail scanners/crawlers có thể mở link.

### 10.2. Chỉ bean service chưa đủ để gửi email

Nếu chỉ cấu hình:

```java
http.oneTimeTokenLogin(Customizer.withDefaults());
```

Spring Security không thể tự biết người dùng nào có địa chỉ email gì và cách gửi. Đăng ký `OneTimeTokenGenerationSuccessHandler`, hoặc chỉ định trực tiếp trong DSL; kiểm soát mapping username → verified email thuộc directory tin cậy. `OneTimeTokenService` không nên bị nhồi trách nhiệm gửi email, render HTML, redirect browser hoặc tạo session.

## 11. Demo Spring Boot Servlet đầy đủ: tạo token và gửi qua local SMTP

Đây là demo **Spring Boot 3.5.x + Spring Security 6.5.x, Java 17+** cho một user `alice`. Nó dùng default in-memory service; việc gửi email đi đến **mail testing server** ở máy local. Demo tách riêng trách nhiệm tạo/lưu (Spring) và gửi (ứng dụng), không trả raw token trong HTTP response. Muốn chạy đầy đủ phải có SMTP capture server lắng nghe cổng `1025` (ví dụ Mailpit/MailHog) và hộp thư demo; thông số/URL dưới đây chỉ dành cho localhost.

### 11.1. Gradle dependencies

Trong dự án Spring Boot đã có plugin Boot và Java toolchain phù hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

### 11.2. application.yml

Lưu `src/main/resources/application.yml`:

```yaml
server:
  port: 8080
spring:
  mail:
    host: localhost
    port: 1025
app:
  ott:
    base-url: "http://localhost:8080"
    recipient: "alice@example.test"
```

Khi đưa lên production, `base-url` phải là hostname HTTPS public đã cấu hình/được kiểm soát, recipient phải lấy từ thông tin email **đã xác minh** của tài khoản và SMTP phải có chính sách xác thực/TLS. Không dùng constant `alice@example.test` để gửi cho mọi username.

### 11.3. Java source

Đặt file `src/main/java/demo/ott/OttApplication.java`:

```java
package demo.ott;

import java.security.Principal;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.ott.OneTimeTokenGenerationSuccessHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

@SpringBootApplication
public class OttApplication {

    public static void main(String[] args) {
        SpringApplication.run(OttApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}local-demo-only")
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    OneTimeTokenGenerationSuccessHandler magicLinkMailer(
            MailSender mailSender,
            @Value("${app.ott.base-url}") String baseUrl,
            @Value("${app.ott.recipient}") String demoRecipient) {

        return (request, response, oneTimeToken) -> {
            // Demo chỉ có account alice; response cho các username là như nhau.
            if ("alice".equals(oneTimeToken.getUsername())) {
                String magicLink = UriComponentsBuilder
                        .fromUriString(baseUrl)
                        .path("/login/ott")
                        .queryParam("token", oneTimeToken.getTokenValue())
                        .build()
                        .encode()
                        .toUriString();

                SimpleMailMessage message = new SimpleMailMessage();
                message.setFrom("no-reply@example.test");
                message.setTo(demoRecipient);
                message.setSubject("Your one-time sign-in link");
                message.setText("Open the following link to sign in: "
                        + magicLink);

                mailSender.send(message);
            }
            response.sendRedirect(request.getContextPath() + "/ott/sent");
        };
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            OneTimeTokenGenerationSuccessHandler magicLinkMailer)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/ott/sent", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .oneTimeTokenLogin(ott -> ott
                        .tokenGenerationSuccessHandler(magicLinkMailer))
                .build();
    }

    @RestController
    static class Pages {
        @GetMapping("/")
        String home() {
            return "Visit /login to request a one-time sign-in link.";
        }

        @GetMapping("/ott/sent")
        String sent() {
            return "If the account is eligible, a sign-in link was sent.";
        }

        @GetMapping("/private")
        String privatePage(Principal principal) {
            return "Hello, " + principal.getName();
        }
    }
}
```

**Giải thích:**

- `OneTimeTokenService` default được Spring Security lựa chọn khi không khai báo service bean riêng. Nó tạo/lưu token; mail handler chỉ nhận token đã tạo.
- `OneTimeTokenGenerationSuccessHandler` dùng URI lấy từ **cấu hình server**, tránh trust một `Host` header tùy ý khi tạo link; nó gửi link đến recipient demo rồi redirect về một trang thông báo chung.
- `UserDetailsService` xác định user `alice`; khi token được consume thành công, Spring Security vẫn phải tìm user/authorities.
- `password("{noop}...")` chỉ dành cho môi trường local minh họa và hỗ trợ form login; magic link không dựa vào việc gửi mật khẩu trong email. Production dùng password encoder phù hợp, hoặc thiết kế passwordless riêng.
- Đây là demo **không có rate limit, delivery retry/outbox hay SMTP production**. Lỗi SMTP sẽ làm request phát hành thất bại, nhưng token đã tạo có thể còn trong storage tới expiry; cần error handling cho kênh gửi riêng trong production.
- `/ott/sent` trả cùng thông báo để hạn chế rò rỉ account existence; nếu SMTP errors tạo phản hồi khác nhau giữa user tồn tại/không tồn tại, cần xử lý để phản hồi vẫn đồng nhất.
- Không log URL hoặc token. Local mail capture UI chỉ để kiểm tra trên máy dev, không đưa token thật lên screenshot hay analytics.

### 11.4. Chạy và quan sát

Khởi chạy SMTP test server trên `localhost:1025` bằng công cụ bạn chọn, sau đó chạy:

```bash
./gradlew bootRun
```

Windows dùng `gradlew.bat bootRun`. Mở `http://localhost:8080/login`, gửi **yêu cầu tạo token** cho username `alice` theo form do Spring Security tạo. Kiểm tra email capture tool nhận magic link; mở link:

```text
http://localhost:8080/login/ott?token=<giá-trị-từ-email-test>
```

Trang submit mặc định phát hiện query `token` rồi điền form. Submit POST hợp lệ có CSRF token để đăng nhập; sau thành công, gọi `GET /private` và kỳ vọng body:

```text
Hello, alice
```

Mở lại link và submit một lần nữa **trong phiên trình duyệt sạch**: phải từ chối token đã dùng. Không có stdout ổn định cho lệnh generate vì giá trị token được sinh ngẫu nhiên. Nếu bạn đang **đã đăng nhập** và mở lại token cũ, trạng thái session hiện tại có thể che giấu kết quả; hãy dùng incognito/đăng xuất và kiểm tra auth flow thực sự.

Với người dùng không tồn tại, handler demo không gửi email và redirect về cùng thông báo. Đây là cách mô tả response chung, không bảo đảm timing/network patterns đã hoàn toàn chống user enumeration.

## 12. Tách interface khỏi implementation: custom OneTimeTokenService

Bạn nên viết service riêng khi cần một hoặc nhiều yêu cầu:

- Lưu **digest/HMAC** thay cho raw token.
- Lưu ở PostgreSQL/Redis với transaction/Lua/conditional update nguyên tử.
- Thực thi TTL, per-tenant context, purpose binding hoặc chính sách thu hồi token cũ khi cấp lại.
- Áp dụng giới hạn số token chưa dùng trên user, khả năng giám sát lifecycle hoặc audit metadata.
- Đồng bộ multi-instance và xử lý rotation của digest key an toàn.

Một thiết kế tối thiểu cho custom service (chỉ là **pseudo API**, không compile trực tiếp):

```java
// PSEUDOCODE: phác họa trách nhiệm, không phải file Java runnable.
OneTimeToken generate(GenerateOneTimeTokenRequest request) {
    String secret = secureRandomBase64Url();
    Instant expiresAt = clock.instant().plus(request.getExpiresIn());
    repository.insert(
            hmacSha256(secret), request.getUsername(), expiresAt);
    return new DefaultOneTimeToken(
            secret, request.getUsername(), expiresAt);
}

OneTimeToken consume(OneTimeTokenAuthenticationToken authentication) {
    String digest = hmacSha256(authentication.getTokenValue());
    // Một lệnh DB atomic: chỉ lấy row còn hạn và chưa dùng.
    StoredToken claimed = repository.deleteAndReturnIfValid(digest);
    if (claimed == null) {
        return null;
    }
    return new DefaultOneTimeToken(
            authentication.getTokenValue(),
            claimed.username(), claimed.expiresAt());
}
```

**Các ràng buộc implement phải thỏa:**

1. Generate phải lưu record thành công trước khi trả token cho success handler. Nếu insert DB thất bại, không gửi link hứa hẹn sử dụng được.
2. `consume` không bao giờ “kiểm tra rồi mới đánh dấu” bằng hai thao tác không transaction.
3. Ngoài TTL, có thể kiểm tra `purpose`, tenant, session binding và trạng thái account theo hợp đồng ứng dụng. Không reuse digest của loại token khác vào cùng namespace.
4. Không nhồi gửi email vào DB transaction giữ row lock lâu; sử dụng outbox/queue khi cần độ tin cậy.
5. Không trả ra `DefaultOneTimeToken` sau một database update mà chưa kiểm tra số row update thành công.
6. Cần thống nhất nếu generate lại token mới thì token cũ vẫn dùng được hay bị thu hồi; thể hiện rõ trong schema và test.
7. Hash/HMAC/secret rotation/expiry kiểm tra phải nhất quán trên các node.

Ví dụ pseudo không phải code để copy thẳng vào một project: `repository`, `secureRandomBase64Url` và `hmacSha256` ở đây là các abstraction cần tự triển khai và kiểm thử.

## 13. Reactive WebFlux: ReactiveOneTimeTokenService

Ứng dụng WebFlux dùng interface **khác**, ở package `org.springframework.security.authentication.ott.reactive`:

```java
// Hình dạng hợp đồng reactive, dùng để giải thích.
public interface ReactiveOneTimeTokenService {
    Mono<OneTimeToken> generate(GenerateOneTimeTokenRequest request);
    Mono<OneTimeToken> consume(OneTimeTokenAuthenticationToken authenticationToken);
}
```

Khác biệt quan trọng: token không hợp lệ được biểu diễn bằng **`Mono.empty()`**, không phải `null` của interface Servlet. Default `InMemoryReactiveOneTimeTokenService` chỉ phù hợp tương ứng với lưu trữ trong một process; ứng dụng cần DB phân tán có thể implement với R2DBC/reactive client, bảo đảm tính atomic.

### Cấu hình WebFlux

```java
// Trích đoạn trong @Configuration có @Bean và các import phù hợp.
@Bean
SecurityWebFilterChain webFluxSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/", "/ott/sent").permitAll()
                    .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(Customizer.withDefaults())
            .build();
}
```

Nếu cần thay service có thể khai báo `@Bean ReactiveOneTimeTokenService` hoặc gọi `.oneTimeTokenLogin(ott -> ott.tokenService(customReactiveService))` theo API phiên bản đang dùng. Để gửi magic link trong reactive application, implement `ServerOneTimeTokenGenerationSuccessHandler`:

```java
// Trích đoạn interface handler:
Mono<Void> handle(ServerWebExchange exchange, OneTimeToken token);
```

Nội dung gửi email phải dùng client reactive đúng nghĩa hoặc được cô lập khỏi event loop theo chính sách; đừng gọi SMTP/JDBC blocking trực tiếp trong WebFlux handler. Nếu thư viện gửi email blocking là bắt buộc, dùng `Mono.fromRunnable(...).subscribeOn(Schedulers.boundedElastic())` trong một publisher được ghép đúng; không tự `subscribe()` rồi return success trước khi gửi xong.

**Không** mang Servlet `JdbcOneTimeTokenService` và `UserDetailsService` đồng bộ vào một WebFlux pipeline rồi coi nó là reactive vì được bọc trong `Mono.just(...)`. Reactive persistence/identity lookup cần được thiết kế và cấu hình riêng.

## 14. Unit test với InMemoryOneTimeTokenService: vòng đời một lần

Để kiểm tra API trực tiếp, bổ sung trong Gradle project Spring Boot:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Tạo `src/test/java/demo/ott/OneTimeTokenServiceTest.java`:

```java
package demo.ott;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.ott.GenerateOneTimeTokenRequest;
import org.springframework.security.authentication.ott.InMemoryOneTimeTokenService;
import org.springframework.security.authentication.ott.OneTimeToken;
import org.springframework.security.authentication.ott.OneTimeTokenAuthenticationToken;

import static org.junit.jupiter.api.Assertions.*;

class OneTimeTokenServiceTest {

    @Test
    void tokenCanBeConsumedExactlyOnce() {
        var service = new InMemoryOneTimeTokenService();
        OneTimeToken issued = service.generate(
                new GenerateOneTimeTokenRequest(
                        "alice", Duration.ofMinutes(5)));

        var request = OneTimeTokenAuthenticationToken
                .unauthenticated(issued.getTokenValue());

        OneTimeToken first = service.consume(request);
        OneTimeToken second = service.consume(request);

        assertNotNull(first);
        assertEquals("alice", first.getUsername());
        assertNull(second);
    }

    @Test
    void expiredTokenIsRejected() {
        var service = new InMemoryOneTimeTokenService();
        Instant t0 = Instant.parse("2026-01-01T10:00:00Z");
        service.setClock(Clock.fixed(t0, ZoneOffset.UTC));

        OneTimeToken issued = service.generate(
                new GenerateOneTimeTokenRequest(
                        "alice", Duration.ofSeconds(30)));

        service.setClock(Clock.fixed(
                t0.plusSeconds(31), ZoneOffset.UTC));

        var request = OneTimeTokenAuthenticationToken
                .unauthenticated(issued.getTokenValue());

        assertNull(service.consume(request));
    }

    @Test
    void unknownTokenIsRejected() {
        var service = new InMemoryOneTimeTokenService();

        var request = OneTimeTokenAuthenticationToken
                .unauthenticated("missing-token");

        assertNull(service.consume(request));
    }
}
```

Chạy:

```bash
./gradlew test --tests demo.ott.OneTimeTokenServiceTest
```

Kỳ vọng **ba tests PASS** khi dependency Spring Security 6.5/Boot 3.5 tương ứng. Test dùng `Clock.fixed(...)` để không phải `Thread.sleep` và để expiry kiểm chứng được; đây là unit test của default in-memory service, **không chứng minh** database/JDBC hoặc email delivery thực tế.

Một test concurrency bổ sung nên tạo một token và phát nhiều thread cùng gọi `consume` từ một barrier, rồi assert tổng số lần trả token khác null là **1**. Với persistence multi-instance, chạy cùng bài test trên hai process khác nhau hướng tới một DB chia sẻ; một bài test single JVM không thể chứng minh atomicity liên node.

## 15. Kiểm thử tích hợp của generate, delivery và login

Để biết toàn bộ flow hoạt động, cần kiểm tra những thứ unit test service chưa bao gồm:

| Tình huống | Cách kích hoạt | Tiêu chí |
| --- | --- | --- |
| Generate hợp lệ | Submit `POST /ott/generate` với CSRF token | Một token được tạo/lưu, handler gửi tới đúng verified contact |
| Username không tồn tại | Submit một identifier không tồn tại | Phản hồi chung, không tiết lộ account existence qua body/status/timing dễ thấy |
| Magic link mới | Mở link, submit `POST /login/ott` hợp lệ | User có account phù hợp đăng nhập; authorities đúng |
| Replay | Submit token đã dùng lần nữa, trong một phiên mới | Không tạo authentication mới |
| Expiry | Đặt clock/TTL ngắn và submit sau expiry | Không xác thực dù record chưa cleanup |
| Sai token | Thay một ký tự token | Không xác thực; không lộ lý do chi tiết |
| Hai request đồng thời | Submit cùng token song song | Đúng một request thành công |
| Restart/replica | Generate A, consume B; restart giữa chừng | Memory mất token; shared JDBC hoạt động theo policy |
| Account bị khóa sau generate | Khóa user trước consume | Login bị từ chối; không nâng quyền |
| SMTP lỗi | Mô phỏng mail service timeout/5xx | Không trả token trong response, có metric/fallback; record sẽ hết hạn hoặc bị thu hồi |
| Mail preview bot | Bot chỉ GET link | Token **chưa bị consume** nếu dùng flow form POST chuẩn |
| CSRF | POST generate/login thiếu token theo policy | Bị chặn, không âm thầm tắt toàn bộ CSRF |
| Token/URL logging | Kiểm tra proxy/app/observability | Không ghi raw token vào log/trace |
| Email đổi/tenant | Một username ở nhiều tenant, email chưa verified | Không gửi hoặc ánh xạ sai danh tính |
| Multiple pending tokens | Generate 2 link cho một user | Quy tắc cho phép nhiều hay invalidate token cũ được kiểm chứng |

Có thể dùng `MockMvc` và `spring-security-test` để kiểm tra filter/controller/CSRF, nhưng fake mail server và database thật cần integration test riêng. Test phải kiểm tra **kết quả xác thực**, không chỉ status redirect hoặc email đã được gửi.

## 16. Những lỗi phổ biến và cách xử lý

### “Tạo token được nhưng nhấn link không đăng nhập”

Kiểm tra form GET `/login/ott` có tồn tại, và browser có submit **POST `/login/ott`** với token/CSRF hợp lệ không. Đừng giả định GET đã consume token. Kiểm tra username lưu trong token có khớp `UserDetailsService` và account không bị disabled/locked. Trong multi-replica, xem request generate/consume có tới hai JVM dùng memory service không.

### “Token có thể đăng nhập hai lần”

Đo xem bạn đang kiểm tra token bằng `findByValue` rồi mới `markUsed` hay không. Thiếu tính atomic có thể dẫn tới replay khi concurrent. Cần fix ở storage transaction/conditional update, không chỉ thêm kiểm tra `isUsed` ở controller. Với duplicate POST sequential, default service phải trả invalid sau lần đầu.

### “Token hết hạn vẫn tồn tại trong DB”

Dọn record hết hạn không phải là điều kiện quyết định validity. Kiểm tra so sánh `Instant` trong consume, cron cleanup, đồng hồ của node và policy TTL. Tránh trừ/đổi timezone bằng string locale.

### “Ở local chạy, lên production token mất ngẫu nhiên”

Default `InMemoryOneTimeTokenService` không chia sẻ trạng thái giữa node và mất dữ liệu khi restart. Dùng JDBC/shared store hoặc lựa chọn routing/lifecycle có lý do rõ; chạy integration test đa instance.

### “Ứng dụng gửi mail cho username không có tài khoản”

Tách bước kiểm tra verified account/contact ở delivery handler/directory. Phản hồi request vẫn chung để giảm enumeration. Không tự gửi mail tới email string người dùng nhập chỉ vì nó trùng `getUsername()`.

### “Magic link bị bot/bộ lọc email sử dụng mất”

Kiểm tra có custom endpoint GET tự consume không. Giữ GET chỉ hiển thị trang submit, dùng POST để xác thực; thiết kế defense bổ sung nếu mail provider thực hiện form submission hoặc prefetch đặc biệt. TTL/rate-limit và email template không nhúng tracking third-party.

### “Token bị lộ trong logs”

Kiểm tra reverse proxy query logging, Java access log, tracing, Sentry, browser monitoring, mail capture và exception handler. Token raw là credential; không log `getTokenValue()`, không echo trong response hoặc phát tán URL đầy đủ. Thiết lập `Referrer-Policy`, TLS và URL sạch sau login.

### “Muốn thay TTL nhưng token vẫn chỉ sống 5 phút”

Tạo request với duration đúng, hoặc cấu hình request resolver của Spring Security theo API phiên bản. Nếu dùng custom service, kiểm tra service có thật sự dùng `request.getExpiresIn()` và mọi node có đồng hồ hợp lệ; không chỉ đổi text hiển thị trong email.

### “Dùng JdbcOneTimeTokenService nhưng báo table not found”

Chưa apply schema classpath chuẩn hoặc migration chưa chạy trên đúng database/schema. Kiểm tra datasource, SQL dialect, database permissions và migration version; không giả định Boot tự tạo bảng chỉ vì có JDBC bean.

### “Email gửi xong nhưng login báo invalid”

Có thể token đã hết hạn, bị consume trước, DB transaction rollback, link bị cắt/encode sai, hoặc gửi xong mới deploy restart memory store. Quan sát log **không chứa token**, dùng correlation ID/token record ID đã băm đúng chính sách để xác định vấn đề.

## 17. Checklist production trước khi bật đăng nhập bằng token một lần

1. **Cấu hình đúng phiên bản:** Spring Security ≥ 6.4 và dùng `oneTimeTokenLogin` đúng Servlet/Reactive API; kiểm tra method signatures từ javadoc phiên bản thực tế.
2. **Cấp token:** `SecureRandom` hoặc implementation đủ entropy, TTL ngắn, username/tenant/purpose phù hợp, giới hạn số yêu cầu/người dùng/IP.
3. **Storage:** chọn shared store cho nhiều replicas, đánh giá backup/replication, expiry cleanup, transaction isolation và atomic consume.
4. **At rest:** xem xét digest/HMAC và key rotation; không giả định default JDBC lưu hash; bảo vệ DB access, backup và query log.
5. **Delivery:** chỉ gửi tới verified contact, tránh user enumeration, theo dõi SMTP/outbox failures; không trả raw token cho requester.
6. **Request flow:** POST generate/submit với CSRF theo policy; GET magic link chỉ render form; hạn chế email scanners làm token bị tiêu thụ.
7. **Browser/security headers:** HTTPS, domain đã đăng ký/tin cậy, Referrer-Policy, CSP phù hợp và không có third-party script/pixel trên trang chứa token.
8. **Authentication:** consume xong vẫn kiểm tra user/account state và authorities; không lấy username từ request body lúc consume để thay thế identity trong record.
9. **Replay:** test đồng thời 2+ request, đa node; không cho token đã dùng “sống lại” qua retry/transaction rollback.
10. **Expiry/reissue:** quy định rõ token cũ khi tạo link mới, thời điểm đồng hồ, cleanup, notification và xử lý account bị khóa.
11. **Logging:** không log token, magic link đầy đủ, email/phone nhạy cảm hoặc security credentials; ghi metric an toàn về tạo/gửi/dùng/thất bại.
12. **Kiểm thử:** JUnit service, web filter/CSRF, delivery, restart, race condition, DB failover, timeout và user enumeration.
13. **Giám sát:** theo dõi tỷ lệ tạo/gửi/tiêu thụ thành công, số token hết hạn, replay bị chặn, mail latency và storage errors.

**Điểm mấu chốt:** `OneTimeTokenService` chịu trách nhiệm **tạo và quản lý vòng đời token**, `OneTimeTokenGenerationSuccessHandler` chịu trách nhiệm **giao token**, còn `OneTimeTokenAuthenticationProvider` chịu trách nhiệm **sử dụng token đã được consume để xác thực tài khoản**. Tính một lần được bảo đảm tại thao tác consume nguyên tử trong storage, không phải chỉ bằng một flag trên giao diện.

## 18. Tài liệu chính thức

- [Spring Security 6.5 – One-Time Token Login (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html): DSL, trang login, generate/submit, gửi magic link, custom service.
- [OneTimeTokenService API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/OneTimeTokenService.html): chữ ký chính xác `generate`/`consume`.
- [GenerateOneTimeTokenRequest API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/GenerateOneTimeTokenRequest.html): username và expiration duration.
- [OneTimeTokenAuthenticationToken API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/OneTimeTokenAuthenticationToken.html): credential dùng khi consume.
- [OneTimeToken API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ott/OneTimeToken.html): token value, username, expiresAt.
- [InMemoryOneTimeTokenService API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/InMemoryOneTimeTokenService.html): UUID, in-memory behavior và `setClock`.
- [JdbcOneTimeTokenService API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/JdbcOneTimeTokenService.html): JDBC schema, `cleanupExpiredTokens` và lịch cleanup.
- [OneTimeTokenAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ott/OneTimeTokenAuthenticationProvider.html): consume token và nạp user/authorities.
- [Spring Security 6.5 – One-Time Token Login (Reactive)](https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/onetimetoken.html): ReactiveOneTimeTokenService và ServerOneTimeTokenGenerationSuccessHandler.
- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): khuyến nghị bảo vệ link/token dùng một lần, TTL, response chung, giới hạn brute force.
