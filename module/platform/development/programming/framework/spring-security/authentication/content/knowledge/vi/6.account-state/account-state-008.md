# Thay đổi trạng thái sau đăng nhập và giới hạn của việc chỉ kiểm tra lúc đăng nhập

Một người dùng đăng nhập thành công lúc 09:00. Đến 09:05, quản trị viên **khóa tài khoản**, **vô hiệu hóa người dùng**, **thu hồi vai trò ADMIN** hoặc **đặt lại mật khẩu**. Đến 09:06, trình duyệt vẫn gửi cookie của phiên vừa được cấp, hoặc một mobile app gửi access token đã phát trước đó. Request mới có bị từ chối không?

**Không thể kết luận từ việc “Spring Security đã kiểm tài khoản lúc đăng nhập”.** Xác minh thông tin đăng nhập tại T0 và duy trì quyền sử dụng phiên/token tại T1 là hai quyết định khác nhau. Với một phiên HTTP stateful, `SecurityContext` thường chứa `Authentication` và danh sách authorities đã được xác thực **ở thời điểm trước đó**. Nếu ứng dụng không có cơ chế kiểm lại, làm mới hoặc thu hồi, việc đổi trạng thái trong database chưa chắc thay đổi principal đang nằm trong session. Với JWT tự chứa, chữ ký đúng và `exp` chưa đến **không chứng minh** tài khoản vẫn enabled hoặc role chưa bị thu hồi.

Bài học thuộc phần **Trạng thái tài khoản** trong *Spring Security - authentication*, tập trung vào vòng đời **sau đăng nhập**: giới hạn của status check, session snapshot, bearer token, thu hồi và phiên bản bảo mật, lựa chọn điểm kiểm lại và cách thử trên Java 17+/Spring Boot 3.x.

## 1. Mục tiêu

Sau bài này, bạn sẽ:

1. Phân biệt **account status**, **credential status**, **authentication/session status** và **authorization state** ở từng thời điểm.
2. Giải thích thời điểm các cờ `UserDetails` được `DaoAuthenticationProvider` kiểm và lý do chúng không tự “đẩy” thay đổi vào `SecurityContext` đã lưu.
3. Dự đoán tác động của disable, lock, password reset, role removal, account expiry, user deletion và tenant membership removal đối với phiên/token đã cấp.
4. Phân biệt form login + `HttpSession`, HTTP Basic, remember-me, JWT, opaque token và refresh token.
5. Chọn giải pháp kiểm lại: session invalidation, version/epoch, per-request revalidation, short TTL, online introspection và kiểm quyền sát thời điểm tác vụ nhạy cảm.
6. Chạy ví dụ Java 17+ cho version checking, đồng thời chạy integration test Spring Security chứng minh **đổi trạng thái sau login** chặn request tiếp theo.
7. Thiết kế kiểm thử cho cache, nhiều node, độ trễ revoke và request đang chạy.

## 2. Bản chất: kiểm credential lúc login khác với kiểm trạng thái ở request sau

### 2.1 Luồng xác thực username/password điển hình

```text
POST /login: username + raw password
     |
     v
UsernamePasswordAuthenticationFilter
     |
     v
AuthenticationManager / ProviderManager
     |
     v
DaoAuthenticationProvider
     +--> UserDetailsService.loadUserByUsername(username)
     |       -> password hash, account flags, authorities
     +--> Kiểm status của account
     +--> PasswordEncoder.matches(raw, encoded)
     +--> Kiểm credentials còn hiệu lực
     |
     v
Authentication thành công
     +--> principal + authorities đã xác định
     |
     v
SecurityContext được lưu trong HttpSession (nếu stateful)
     |
     v
GET /api/report với session cookie cũ
     -> lấy SecurityContext đã lưu
     -> áp authorization từ Authentication hiện có
     -> KHÔNG MẶC ĐỊNH query lại UserDetailsService mỗi lần
```

Bản ghi của user trong database chỉ là **nguồn dữ liệu ở thời điểm provider tải nó**. Một `Authentication` được đánh dấu authenticated sau khi kiểm đúng credential; `authentication.isAuthenticated()` không tự thực hiện SQL mới. Khi truy cập request sau bằng cookie phiên, Spring Security có thể lấy object/serialized snapshot trong session. Nếu không có kiểm trạng thái bổ sung, giá trị như `ROLE_ADMIN` có thể giữ nguyên dù admin đã xóa role trong DB.

### 2.2 Ý nghĩa bốn cờ UserDetails

| Phương thức | Nếu trả `false` | Hiệu ứng khi provider phù hợp đang xác thực |
| --- | --- | --- |
| `isEnabled()` | Account disabled | Thường từ chối bằng `DisabledException`. |
| `isAccountNonLocked()` | Account locked | Thường từ chối bằng `LockedException`. |
| `isAccountNonExpired()` | Account hết hạn | Thường từ chối bằng `AccountExpiredException`. |
| `isCredentialsNonExpired()` | Credential hết hạn | Thường từ chối bằng `CredentialsExpiredException`. |

Các phương thức này có thể được kiểm bởi `DaoAuthenticationProvider`/account status checkers khi chạy **một lần xác thực**. Chúng không tự động khiến mọi phiên đã cấp bị vô hiệu hóa. Nếu `UserDetailsService` có cache stale, thậm chí một lần xác thực mới cũng có thể dùng trạng thái cũ; phải xét freshness của cache.

Đặc biệt, `isAccountNonLocked()==false` nghĩa là **bị khóa** (tên có phủ định); không đảo ngược semantics khi map từ cột `locked` trong DB.

### 2.3 Trục thời gian và câu hỏi cần trả lời

```text
09:00     Login hợp lệ: enabled=true, role=ADMIN
  |
09:01     Server lưu Authentication phiên S với ROLE_ADMIN
  |
09:05     Admin đặt enabled=false hoặc xóa ROLE_ADMIN trong DB
  |
09:06     Client gửi cookie phiên S gọi /api/admin
           |
           +-- Chỉ kiểm lúc login?  Có thể vẫn authenticated + role cũ
           +-- Session bị revoke?  Không còn dùng được phiên S
           +-- Revalidate mỗi request?  Thấy trạng thái mới và từ chối
           +-- JWT chỉ kiểm exp?  Có thể vẫn dùng tới khi token hết hạn
```

Thay một hàng trong DB lúc 09:05 **không phải** hành động tương đương “xóa session của mọi browser, thu hồi mọi access token, cập nhật mọi cache và dừng mọi request đang chạy”. Những hệ quả đó cần được cài bằng cơ chế có chủ đích.

## 3. Bốn loại trạng thái phải được định nghĩa riêng

**Account state:** account có tồn tại, enabled, locked, non-expired và còn membership tenant không.

**Credential state:** mật khẩu có được reset, password hash có bị lộ, MFA đã thay đổi, API key hoặc refresh token còn hiệu lực không.

**Authentication/session state:** cookie/session ID có còn hợp lệ không, version lúc cấp có còn được chấp nhận không, token hết hạn hay bị revoke chưa, người dùng đã reauthenticate khi cần chưa.

**Authorization state:** principal còn được thực hiện hành động này trên **đối tượng và tenant cụ thể** không; role/permission được cấp lúc nào, quyết định có cần tra nguồn live không.

Một user có thể **đã authenticated nhưng không authorized**; một JWT có chữ ký hợp lệ có thể vẫn vi phạm account policy; một session hết hạn có thể buộc login lại dù account vẫn enabled. Không gộp tất cả vào một boolean `loggedIn`.

### 3.1 Ma trận sự kiện sau login

| Thay đổi | Đăng nhập mới | Session cũ nếu không có revoke/freshness | JWT tự chứa nếu chỉ kiểm signature/exp | Việc cần cân nhắc |
| --- | --- | --- | --- | --- |
| `enabled=false` | Thường bị chặn bởi provider | Có thể vẫn hoạt động | Có thể hoạt động đến `exp` | Revoke/invalidate hoặc kiểm enabled/version. |
| `accountLocked=true` | Provider có status checker từ chối | Chưa chắc bị ảnh hưởng | Chưa chắc bị ảnh hưởng | Định nghĩa lock áp dụng cho cả phiên hiện có hay không. |
| `accountExpired=true` | Provider thường từ chối | Snapshot có thể chưa cập nhật | Claim vẫn còn hạn | Kiểm hạn account tại điểm phù hợp. |
| Password/credential expired | Login bằng password cũ có thể bị chặn | Session cũ có thể còn | JWT thường không biết tuổi password | Buộc reauthentication/rotation theo chính sách. |
| Password reset vì sự cố | Hash cũ bị thay | Cookie đã cấp không tự biến mất | JWT không tự invalid | Thu hồi session, refresh grant, tokens theo policy. |
| Xóa role ADMIN | Login mới thường có authorities mới | Phiên cũ có thể vẫn có `ROLE_ADMIN` | Claims quyền cũ tồn tại | Version quyền, refresh principal, kiểm live authorization. |
| Xóa account khỏi DB | Lookup mới không thấy user | Object principal cũ có thể còn | JWT cũ vẫn verify được | Từ chối account không còn và revoke phiên. |
| Xóa membership tenant | Login/switch tenant mới phải từ chối | Session của tenant cũ có thể còn | Tenant claim cũ có thể còn | Membership check/revocation theo tenant + account. |
| Enable lại sau disable | Có thể login mới | Phiên đã revoke **không nên sống lại** | Token đã revoke không nên hoạt động lại | Security version/epoch tăng đơn điệu. |

**Yêu cầu vận hành phải nói rõ sự kiện nào gây “logout all”, sự kiện nào chỉ làm thay đổi quyền, và thay đổi phải có hiệu lực trong bao lâu.** Một hệ thống thông tin nội bộ ít rủi ro có thể chấp nhận TTL ngắn; tác vụ quản trị tài chính thường cần nguồn quyền mới hơn.

## 4. Phân biệt các cơ chế session/token

### 4.1 Form login + HttpSession

Sau khi login bằng form, cơ chế Spring Security có thể lưu `SecurityContext` vào `HttpSession` thông qua `SecurityContextRepository`. Request sau mang cookie phiên và khôi phục context. Trong cấu hình thông dụng, **đường đi này không tự gọi `PasswordEncoder.matches` hoặc nạp lại `UserDetails` ở mọi request**.

- Session timeout kiểm **tuổi phiên**, không phải trạng thái account hiện hành.
- Logout/invalidate phía server vô hiệu session ID được thu hồi; xóa cookie tại client **không làm bản sao cookie bị đánh cắp mất hiệu lực**.
- `SessionCreationPolicy` và `SecurityContextRepository` quyết định cách lưu; custom login cần lưu context đúng theo API tương ứng, nhất là với Spring Security 6.
- Session fixation/CSRF/XSS protection vẫn cần thiết, nhưng không giải quyết role snapshot stale.
- Với Spring Session/Redis hoặc cluster, invalidation phải đúng shared store; đừng coi phiên nằm duy nhất trong bộ nhớ một JVM.

### 4.2 HTTP Basic

HTTP Basic thường gửi `Authorization: Basic ...` cho **mỗi request**. Trong flow stateless phù hợp, provider có cơ hội kiểm credential và account status nhiều lần, khác một session form login đã tạo. Nhưng nếu hệ thống dùng cache stale, custom manager hoặc lưu authentication giữa request thì không được hứa “HTTP Basic luôn đọc DB mới nhất”. HTTP Basic chỉ mã hóa Base64, **không bảo mật nếu thiếu HTTPS**.

### 4.3 Remember-me

Remember-me cookie có thể tạo một cơ chế đăng nhập lại khi session hết. Disable/password reset có cần revoke persistent remember-me token? Phải xét cấu hình; chỉ invalidate một session **không bảo đảm** cookie remember-me sẽ không phục hồi quyền sau đó. Với sự cố credential, quy trình thu hồi nên xem cả session, remember-me, refresh grant và SSO.

### 4.4 JWT bearer

Spring Security Resource Server JWT có thể verify signature và các điều kiện `iss`/`exp`/`nbf` theo cấu hình. Đây là **kiểm tính hợp lệ của token**, không mặc định query DB để thấy user vừa disabled hoặc role vừa bị thu hồi. Các quyền trong JWT là snapshot của lần phát hành cho đến khi hết hạn hoặc bị API từ chối bởi cơ chế bổ sung.

- Access token ngắn giúp **giảm cửa sổ stale**, không phải immediate revocation.
- Denylist theo `jti`, grant revocation hoặc auth-version check yêu cầu nguồn trạng thái tin cậy mà API thực sự kiểm.
- `aud`, tenant, scope/permissions cần validator phù hợp; decode Base64 không phải verify.
- Refresh-token revocation ngăn cấp token mới, nhưng **không tự hủy** access JWT cũ nếu API chỉ kiểm chữ ký/exp.

### 4.5 Opaque token và introspection

Một opaque token thường được resource server hỏi tới authorization server để biết có `active` hay không. Revoke ở issuer **có thể** phát huy nhanh nếu resource server dùng introspection đủ mới. Nhưng cache introspection, timeout và chính sách của issuer quyết định độ trễ thực tế. Không mặc định opaque token bảo đảm thu hồi 0 giây trên mọi cụm máy.

## 5. Thiết kế chính sách freshness và revocation

### 5.1 Một cam kết có thể đo được

Ví dụ yêu cầu có kiểm chứng:

> Khi thao tác disable account được commit vào kho trạng thái authoritative, mọi request **bắt đầu sau khi trạng thái mới có thể quan sát tại nguồn kiểm tin cậy** phải bị từ chối. Với request đã vượt điểm kiểm trước commit, hệ thống định nghĩa giới hạn và cơ chế riêng.

Một ví dụ khác: “Role ADMIN thu hồi có hiệu lực tối đa 10 giây tại mọi API; thao tác chuyển tiền yêu cầu kiểm quyền live trong transaction”. Cần ghi rõ thời điểm bắt đầu đo, phạm vi node/cache và cách test. **“Tức thì” là một yêu cầu kiến trúc, không phải thuộc tính mặc định của `UserDetails`.**

### 5.2 Các phương án và đánh đổi

| Phương án | Cơ chế | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| Chỉ check lúc login | Provider nạp user/status rồi tạo session snapshot | Ít truy vấn sau login | Thay đổi DB có thể không tác động tới session. |
| Timeout session ngắn | Idle/absolute expiry | Giới hạn vòng đời | Không phản ứng ngay khi role bị thu hồi. |
| Push session invalidation | Sự kiện admin change hủy/expire session | Giảm độ trễ | Cần session registry/shared store đủ bao phủ, retry sự kiện. |
| Per-request state check | Mỗi request đọc enabled/locked/version đáng tin | Thấy thay đổi tại lần kiểm kế tiếp | Tốn I/O, cache stale/outage và in-flight race. |
| Auth version/epoch | Session/token mang version lúc cấp; so với version hiện tại | Một cơ chế revoke nhất quán cho nhiều sự kiện | Phải tăng version ở **mọi** sự kiện cần revoke; cần nguồn mới. |
| Refresh authorities | Tạo lại principal hoặc kiểm quyền mới | Không nhất thiết logout khi role đổi | Có thể cấp quyền bất ngờ; cần policy reauth/step-up. |
| JWT ngắn + refresh revoke | Hết hạn access nhanh, dừng token mới | Scale và latency tốt | JWT cũ có thể tiếp tục tới `exp`. |
| Online token introspection | API hỏi trạng thái issuer/grant | Thu hồi tập trung | Tăng phụ thuộc mạng/cache/failure mode. |
| Authorization tại service | Kiểm account/tenant/object gần lúc thực thi | Bảo vệ nghiệp vụ nhạy cảm | Cần transaction/consistency và thiết kế race rõ. |

Tổ hợp thường hợp lý là **TTL phù hợp + account authVersion + event invalidation + kiểm quyền sát giao dịch nhạy cảm**. Không có một filter đủ giải quyết tất cả cơ chế đăng nhập và mọi tài nguyên.

### 5.3 Auth version không phải password

Mỗi account có `auth_version` (hoặc `sessions_valid_after`):

```text
Lúc login:
  accountId=101 enabled=true auth_version=7
  session.authVersion=7

Admin disable:
  accountId=101 enabled=false auth_version=8

Request cũ:
  version trong session = 7
  version authoritative = 8
  -> từ chối, hủy phiên theo policy.

Admin enable lại:
  accountId=101 enabled=true auth_version=9
  session cũ vẫn version 7 -> từ chối.
```

Version không xác thực raw password lần hai. Nó chỉ là **điều kiện còn tin kết quả authentication đã cấp hay không**. Chỉ so `enabled` là chưa đủ để tránh “hồi sinh” cookie cũ sau disable → enable. Với đa tenant, role/membership version có thể scoped theo `(tenantId,accountId)`; dùng đúng ID ổn định, không chỉ email hiển thị.

### 5.4 Atomic update và source-of-truth

Nếu admin xóa role nhưng quên tăng version, session chứa role cũ có thể tiếp tục hoạt động. Nếu tăng version thành công nhưng cập nhật quyền thất bại, user có thể bị logout không cần thiết. Nên cập nhật trạng thái, role và epoch trong **transaction nhất quán**:

```sql
-- Minh họa cho một schema accounts(account_id,enabled,auth_version)
UPDATE accounts
SET enabled = FALSE,
    auth_version = auth_version + 1
WHERE account_id = ?;
```

Với role removal, thay đổi role table và tăng version trong cùng transaction theo dialect/hạ tầng tương ứng. Sử dụng unique/foreign key, optimistic locking hoặc outbox khi cần phát event tới node khác. Mốc commit và độ trễ replica/cache phải được đưa vào SLA, không coi một event gửi thành công là mọi API đã nhận.

## 6. Java 17+ độc lập: minh họa version và việc không hồi sinh session

Đoạn dưới **chạy chỉ với JDK 17+**, không phụ thuộc Spring. Đây không phải chức năng authentication thật; nó giúp xác nhận logic của security version.

File `StateVersionDemo.java`:

```java
public final class StateVersionDemo {

    record State(boolean enabled, long version) {}

    static boolean accepts(State current, long sessionVersion) {
        return current.enabled()
                && current.version() == sessionVersion;
    }

    public static void main(String[] args) {
        State atLogin = new State(true, 1);
        long oldVersion = atLogin.version();

        System.out.println("before-change=" + accepts(atLogin, oldVersion));

        State disabled = new State(false, 2);
        System.out.println("after-disable=" + accepts(disabled, oldVersion));

        State enabledAgain = new State(true, 3);
        System.out.println("old-session-after-enable="
                + accepts(enabledAgain, oldVersion));
        System.out.println("new-session-after-enable="
                + accepts(enabledAgain, enabledAgain.version()));
    }
}
```

Lệnh:

```bash
javac StateVersionDemo.java
java StateVersionDemo
```

Stdout chính xác:

```text
before-change=true
after-disable=false
old-session-after-enable=false
new-session-after-enable=true
```

**Bài học:** Khi account enabled lại, một phiên *mới* được cấp version 3 có thể hợp lệ, nhưng phiên version 1 vẫn bị từ chối. Đây là semantics phù hợp cho revocation mạnh hơn điều kiện “enabled=true”.

## 7. Spring Boot 3.x chạy được: kiểm status/version của session cũ

Bài thực hành dùng **Spring Boot 3.3.13, Spring Security 6.x và Java 17+** với form login và `HttpSession`. Một kho account in-memory thread-safe lưu `enabled`, `authVersion`, password verifier và authorities. Khi login thành công, principal custom chứa version snapshot. Filter nằm trong **Spring Security chain**, sau khi context đã được nạp và trước `AuthorizationFilter`, sẽ kiểm nguồn trạng thái hiện hành:

- Account bị disable hoặc đã bị xóa: hủy session và trả HTTP 401.
- Version khác snapshot: hủy session và yêu cầu login lại.
- Trạng thái còn hợp lệ: request tiếp tục tới authorization như bình thường.

Ví dụ này **không có public endpoint đổi role/disable user**. Integration test gọi trực tiếp bean quản lý account như một hành động quản trị đáng tin. Trong production phải thay in-memory store bằng DB/shared source có transactional update và consistency phù hợp.

### 7.1 Cấu trúc dự án và Gradle

```text
session-state-lesson/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/SessionStateApplication.java
    └── test/java/demo/SessionStateTest.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'session-state-lesson'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Các version được ghim để tái hiện ví dụ, **không phải khuyến nghị chọn nhánh đã hết vòng hỗ trợ để phát triển production mới**. Khi triển khai sản phẩm, dùng dòng Spring Boot/Spring Security đang được hỗ trợ và kiểm API tương thích.

### 7.2 Ứng dụng Spring Security Servlet

File `src/main/java/demo/SessionStateApplication.java`:

```java
package demo;

import java.io.IOException;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class SessionStateApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionStateApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    AccountStore accountStore(PasswordEncoder encoder) {
        return new AccountStore(encoder);
    }

    @Bean
    UserDetailsService userDetailsService(AccountStore store) {
        return store::loadForLogin;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AccountStore store) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/api/me").authenticated()
                        .requestMatchers("/api/manage")
                            .hasAuthority("ROLE_MANAGER")
                        .anyRequest().denyAll())
                .formLogin(form -> form.permitAll())
                .logout(logout -> logout.permitAll())
                .addFilterBefore(
                        new StateRefreshFilter(store),
                        AuthorizationFilter.class)
                .build();
    }

    record AccountRow(
            String hash,
            boolean enabled,
            long authVersion,
            Set<String> authorities) {
    }

    static final class AccountStore {
        private final ConcurrentMap<String, AccountRow> rows =
                new ConcurrentHashMap<>();

        AccountStore(PasswordEncoder encoder) {
            rows.put("alice", new AccountRow(
                    encoder.encode("local-demo-password"),
                    true, 1L, Set.of("ROLE_USER")));
        }

        UserDetails loadForLogin(String username) {
            AccountRow record = rows.get(username);
            if (record == null) {
                throw new UsernameNotFoundException("Unknown user");
            }

            List<GrantedAuthority> authorities = record.authorities()
                    .stream()
                    .sorted()
                    .map(SimpleGrantedAuthority::new)
                    .map(x -> (GrantedAuthority) x)
                    .toList();

            // Một UserDetails mới mỗi lần: không dùng lại cached User
            // đã có thể bị ProviderManager.eraseCredentials() tác động.
            return new VersionedUser(
                    username, record.hash(), record.enabled(),
                    record.authVersion(), authorities);
        }

        AccountRow current(String username) {
            return rows.get(username);
        }

        void disable(String username) {
            rows.computeIfPresent(username, (key, previous) ->
                    new AccountRow(
                            previous.hash(), false,
                            previous.authVersion() + 1,
                            previous.authorities()));
        }

        void grantManager(String username) {
            rows.computeIfPresent(username, (key, previous) -> {
                Set<String> roles = new java.util.HashSet<>(
                        previous.authorities());
                roles.add("ROLE_MANAGER");
                return new AccountRow(
                        previous.hash(),
                        previous.enabled(),
                        previous.authVersion() + 1,
                        Set.copyOf(roles));
            });
        }
    }

    static final class VersionedUser extends User {
        private static final long serialVersionUID = 1L;
        private final long authVersion;

        VersionedUser(
                String username,
                String encodedPassword,
                boolean enabled,
                long authVersion,
                Collection<? extends GrantedAuthority> authorities) {
            super(username, encodedPassword,
                    enabled, true, true, true, authorities);
            this.authVersion = authVersion;
        }

        long getAuthVersion() {
            return authVersion;
        }
    }

    static final class StateRefreshFilter
            extends OncePerRequestFilter {
        private final AccountStore store;

        StateRefreshFilter(AccountStore store) {
            this.store = store;
        }

        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain chain) throws ServletException, IOException {

            Authentication auth =
                    SecurityContextHolder.getContext().getAuthentication();

            if (auth != null && auth.isAuthenticated()
                    && auth.getPrincipal() instanceof VersionedUser user) {

                AccountRow current = store.current(user.getUsername());
                boolean revoked = current == null
                        || !current.enabled()
                        || current.authVersion() != user.getAuthVersion();

                if (revoked) {
                    SecurityContextHolder.clearContext();
                    HttpSession session = request.getSession(false);
                    if (session != null) {
                        session.invalidate();
                    }
                    response.sendError(
                            HttpServletResponse.SC_UNAUTHORIZED,
                            "Sign in again");
                    return;
                }
            }

            chain.doFilter(request, response);
        }
    }
}

@RestController
class AccountController {

    @GetMapping("/api/me")
    Map<String, Object> me(Authentication auth) {
        return Map.of(
                "username", auth.getName(),
                "authorities", auth.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .sorted().toList());
    }

    @GetMapping("/api/manage")
    String manage() {
        return "manager";
    }
}
```

Giải thích kỹ:

- `UserDetailsService` trả **instance mới** `VersionedUser` khi login, có enabled và version từ store. Khi provider xác thực, password được kiểm bằng `PasswordEncoder`; demo không bao giờ trả mật khẩu hoặc hash ra controller.
- `VersionedUser extends User` giữ snapshot `authVersion`. Nếu `ProviderManager` erase credentials trên principal, store vẫn giữ hash trong `AccountRow` độc lập.
- `StateRefreshFilter` được tạo trực tiếp trong `SecurityFilterChain`, không đăng ký thêm thành Servlet `@Component`; tránh filter bị tự đăng ký lần thứ hai ngoài chain.
- Với form login stateful, context đã được nạp khi filter đặt trước `AuthorizationFilter` chạy. Filter chỉ kiểm các authentication có principal đúng kiểu `VersionedUser`. Nếu ứng dụng còn JWT/OIDC hoặc chain khác, phải có cơ chế kiểm tương ứng; filter này **không bảo vệ mọi principal type**.
- Hủy `HttpSession` làm mất security context của session trong demo. Chỉ `SecurityContextHolder.clearContext()` không đủ để xóa mọi session trên server/distributed store.
- `formLogin` giữ cơ chế CSRF mặc định của Spring Security. Demo **không tắt CSRF** để giúp chạy test cho dễ; test dùng helper form login chuyên dụng.
- Không giữ raw password trong session để “kiểm lại” mỗi request. Session status/version được kiểm so với account store, còn password chỉ được kiểm lúc flow đăng nhập tương ứng.

### 7.3 Integration test qua Spring Security filter chain

File `src/test/java/demo/SessionStateTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SessionStateTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    SessionStateApplication.AccountStore accounts;

    private MockHttpSession login() throws Exception {
        MvcResult result = mvc.perform(
                formLogin().user("alice").password("local-demo-password"))
                .andExpect(status().is3xxRedirection())
                .andReturn();
        return (MockHttpSession) result.getRequest().getSession(false);
    }

    @Test
    void disableAfterLoginRejectsOldSession() throws Exception {
        MockHttpSession session = login();

        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"));

        accounts.disable("alice");

        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void changingRoleInvalidatesOldSessionUntilRelogin()
            throws Exception {
        MockHttpSession previousSession = login();

        mvc.perform(get("/api/manage").session(previousSession))
                .andExpect(status().isForbidden());

        accounts.grantManager("alice"); // Tăng version + đổi role.

        mvc.perform(get("/api/me").session(previousSession))
                .andExpect(status().isUnauthorized());

        MockHttpSession newSession = login();

        mvc.perform(get("/api/manage").session(newSession))
                .andExpect(status().isOk());
    }
}
```

`formLogin()` thuộc `spring-security-test` giúp gửi form login qua filter chain với CSRF phù hợp, thay vì lách protection. Hai test độc lập: `@DirtiesContext` khởi tạo lại store giữa các phương thức. **Kết quả mong đợi** là test pass nếu project được tạo đúng; đây không phải tuyên bố đã chạy build trong môi trường người học.

### 7.4 Chạy và giải thích output

Nếu đã có Gradle wrapper cho project:

```bash
./gradlew test
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat bootRun
```

Nếu Gradle đã cài nhưng project chưa có wrapper, dùng `gradle test`/`gradle bootRun`. Vì app import Spring Boot/Security, lệnh `javac SessionStateApplication.java` **không đủ** nếu thiếu dependency classpath. Java demo `StateVersionDemo.java` ở phần 6 mới là ví dụ JDK thuần có stdout chính xác.

Kỳ vọng qua integration test:

| Giai đoạn | Version/state | HTTP |
| --- | --- | --- |
| Login Alice | Enabled, version 1, ROLE_USER | Redirect login thành công. |
| `GET /api/me` với session mới | Version 1 chưa đổi | 200, username Alice. |
| `GET /api/manage` với role USER | Thiếu ROLE_MANAGER | 403 (authenticated nhưng không authorized). |
| Admin disable sau login | Enabled=false, version tăng | Request tiếp theo với session cũ: 401. |
| Admin cấp ROLE_MANAGER, version tăng | Old session vẫn version 1 | Request từ old session: 401. |
| Alice login mới sau cấp role | New principal có version và role mới | `GET /api/manage`: 200. |

Để *tự nhìn giới hạn của chỉ kiểm lúc login* trong một thí nghiệm local, có thể bỏ **riêng** dòng đăng ký `.addFilterBefore(...)` rồi chạy lại test: session đã cấp trước khi store đổi có thể vẫn dùng principal/authorities snapshot. Đây là bài quan sát **không phải cấu hình an toàn để deploy**.

### 7.5 Những giới hạn có chủ đích của demo

Đây là **một JVM**: không có DB, cache phân tán, request dài, user deletion endpoint, multi-tenancy hoặc bearer tokens. Cách filter chỉ hỗ trợ `VersionedUser` trong form-login chain. Trong ứng dụng có nhiều `SecurityFilterChain`, mỗi chain/manager cần policy tương ứng. Nếu tài khoản bị revoke ngay sau khi request đã qua filter, thao tác phía sau **có thể vẫn chạy**; xem phần 8.4 về TOCTOU.

## 8. Production: biến phiên bản thành hợp đồng dữ liệu đáng tin

### 8.1 Gắn version với account ID ổn định

Đừng chỉ dùng display name/email dễ đổi để tìm state khi principal đã được xác thực. Trong database có thể lưu:

```sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    login_name VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL,
    locked BOOLEAN NOT NULL,
    auth_version BIGINT NOT NULL
);

CREATE TABLE account_roles (
    account_id BIGINT NOT NULL,
    role VARCHAR(100) NOT NULL,
    PRIMARY KEY (account_id, role),
    FOREIGN KEY (account_id) REFERENCES accounts(account_id)
);
```

Đây là SQL minh họa cho database có dialect tương ứng, chưa phải schema production đầy đủ. Ứng dụng multi-tenant có thể cần `tenant_id`, composite uniqueness, phiên bản membership tách riêng, FK tenant/account và authorization theo đối tượng.

Lúc login, principal snapshot nên giữ account ID (+ tenant ID nếu có), auth version và authorities được xác minh. Filter/policy service query current state bằng **ID từ principal tin cậy**:

```sql
SELECT enabled, locked, auth_version
FROM accounts
WHERE account_id = ?;
```

Không lấy `accountId`, `tenantId` hoặc `authVersion` từ header `X-User`/`X-Auth-Version` của client mà coi là sự thật. Một token có version claim đã ký **vẫn cần so với version authoritative** nếu mục tiêu là revoke sau lúc cấp.

### 8.2 Cập nhật và thu hồi phải có ranh giới giao dịch

Ví dụ disable + tăng epoch trong cùng update:

```sql
UPDATE accounts
SET enabled = FALSE,
    auth_version = auth_version + 1
WHERE account_id = ?;
```

Với role revocation, xóa role và tăng account/membership version trong một transaction phù hợp. Nếu DB commit thành công nhưng event invalidation thất bại, một node cache có thể tiếp tục trả stale state; cần outbox/retry/TTL và một cách quan sát được độ trễ thực tế. Không coi `userExists()` hay update cache ngoài transaction là đủ bảo đảm.

### 8.3 Cache và distributed state

Giả sử API cache trạng thái 60 giây, nhưng chính sách yêu cầu disable có hiệu lực dưới 5 giây. Nếu không có invalidation đáng tin, TTL 60 giây **không đáp ứng** cam kết. Cần xác định source authoritative, max stale time, replication lag và fail mode khi nó không sẵn sàng.

Cache key trong hệ thống multi-tenant phải bao gồm namespace, ví dụ `(tenantId, accountId)`; không chỉ `username` nếu tên trùng tổ chức. `UserDetails` có thể chứa password verifier và bị `ProviderManager.eraseCredentials()` tác động; không vô tình dùng chung mutable principal đã erase với cached account verifier.

### 8.4 Filter đầu request không giải quyết mọi race

Tại T1 filter kiểm account còn enabled. Tại T2 admin revoke role. Tại T3 business service vẫn commit một giao dịch nhạy cảm. **Chỉ có check tại T1 không chứng minh quyết định ở T3 vẫn được phép**.

Với nghiệp vụ có yêu cầu mạnh, nên kết hợp authorization sát thời điểm ghi, transaction/optimistic locking và điều kiện dữ liệu:

```sql
-- Minh họa ý tưởng kiểm quyền ngay khi thực thi,
-- cần điều chỉnh tenant/owner/transaction theo hệ thống thật.
UPDATE approvals
SET status = 'APPROVED'
WHERE approval_id = ?
  AND EXISTS (
      SELECT 1
      FROM accounts a
      JOIN account_roles r ON r.account_id = a.account_id
      WHERE a.account_id = ?
        AND a.enabled = TRUE
        AND a.locked = FALSE
        AND r.role = 'ROLE_APPROVER'
  );
```

Số row thay đổi phải được kiểm; nếu 0, xử lý theo API/business policy. Đừng bỏ tenant predicate ở hệ thống đa tenant; câu SQL trên chỉ là ví dụ logic, không phải chính sách object-level hoàn chỉnh.

## 9. SessionRegistry, logout all và giới hạn của invalidation

Spring Security cung cấp session-management và `SessionRegistry`, nhưng **`maximumSessions` không tự đồng nghĩa revoke tất cả session khi user bị disable**.

- `SessionRegistryImpl` trong JVM có thể theo dõi principal → sessions, nhưng không mặc định là registry chia sẻ toàn cluster.
- `HttpSessionEventPublisher` có thể được dùng để đưa lifecycle events cho registry trong cấu hình tương thích.
- `SessionInformation.expireNow()` thường **đánh dấu** session để cơ chế filter xử lý khi request tiếp theo; không giết ngay các request đang chạy. Cần cấu hình session concurrency/expired-session handling phù hợp và test.
- Với Spring Session/Redis hoặc hệ session store phân tán, cần API/session registry phù hợp và kiểm thực tế node B sau khi node A revoke.
- Principal equality/hashCode có thể ảnh hưởng registry keys; custom principal nên có định danh ổn định.
- Hủy `HttpSession` và xóa `SecurityContextHolder` trong thread chỉ giải quyết phần session tương ứng, không tự thu hồi refresh token, JWT hay SSO session bên IdP.

**Hai chiến lược bổ trợ:** *push* event invalidate sessions ngay khi thay đổi; *pull* per-request authVersion/status check nếu event bị mất hoặc đến trễ. Khi policy yêu cầu độ trễ nhỏ, việc test đa node mới đủ chứng minh cam kết.

## 10. JWT/opaque token và thu hồi có kiểm soát

Khi dùng JWT, nên xác định rõ hệ thống chỉ chấp nhận token đúng chữ ký/issuer/audience/lifetime hay còn đòi trạng thái tài khoản mới nhất. JWT có thể giữ `roles=["ADMIN"]` đến expiration sau khi DB đã xóa quyền. Các giải pháp:

| Giải pháp | Phạm vi từ chối | Đánh đổi |
| --- | --- | --- |
| `jti` denylist | Một token cụ thể | Cần lưu/đồng bộ state revocation và TTL đến expiration. |
| Grant/session ID revoke | Một grant hoặc nhóm token | API phải thực sự kiểm grant, không chỉ token signature. |
| `auth_version` claim vs DB | Tất cả token mang version cũ | Nguồn version phải đủ mới và được check ở resource server. |
| Membership version | Các token/sessions trong một tenant/membership | Cần subject+tenant scoped đúng. |
| Access JWT TTL ngắn | Giới hạn stale window | Không bảo đảm immediate revoke. |
| Opaque introspection | Trạng thái theo authorization server | Phụ thuộc issuer, cache TTL, network và failure mode. |

Refresh-token rotation/revoke giúp hạn chế cấp access token tương lai, nhưng không vô hiệu hóa tự động access JWT cũ ở API nếu API chỉ verify chữ ký. Với incident response, liệt kê **web sessions, remember-me, refresh grants, access tokens, API keys, external IdP sessions** và policy revoke từng loại.

## 11. Các hiểu nhầm cần tránh

1. **“isEnabled() đã checked lúc login nên request ngày mai cũng checked.”** Sai với phiên stateful thông thường: context có thể chỉ là snapshot.
2. **“isAuthenticated() luôn gọi lại AuthenticationManager.”** Sai; nó là trạng thái trên object, không phải thao tác xác minh lại.
3. **“Đổi password là mọi cookie và JWT hết hiệu lực.”** Sai nếu không có explicit revocation.
4. **“Tắt account trong DB là lập tức dừng mọi HTTP request.”** Không với request đã vượt check hoặc cache phân tán còn stale.
5. **“Chỉ cần expireNow() là global logout.”** Session marker không bảo đảm xử lý trên mọi node/in-flight request.
6. **“JWT đúng chữ ký đồng nghĩa user hiện vẫn có role.”** Claims có thể là snapshot.
7. **“Cho phép lại account thì cookie cũ có thể tái sử dụng.”** Không nên nếu policy đã revoke; authVersion cần tăng đơn điệu.
8. **“Refresh authorities từ DB là đủ cho mọi giao dịch.”** Object-level ownership/tenant, in-flight race và policy authorization vẫn cần kiểm riêng.
9. **“Chỉ thêm một filter là bảo vệ mọi authentication mechanism.”** Không nếu principal khác kiểu, security chain khác hoặc endpoint stateless không đi qua filter.
10. **“Khi DB outage, có thể bỏ kiểm để app khỏi lỗi.”** Với chức năng nhạy cảm, fail-open có thể vô hiệu toàn bộ chính sách revoke.

## 12. Ma trận kiểm thử

| Test | Kiểm tra |
| --- | --- |
| Login khi enabled=true | Authentication thành công, principal/authorities đúng. |
| Disable sau login, giữ cookie cũ | Request mới bị từ chối theo policy, session không còn được dùng. |
| Lock sau login | Kiểm chính sách có chặn phiên hiện có hay không. |
| Account expired sau login | Context/token cũ bị từ chối hoặc giới hạn theo SLA đã viết. |
| Password reset | Cookie và refresh grants cũ được xử lý đúng chính sách. |
| Role ADMIN bị xóa | Phiên cũ không tiếp tục dùng quyền cao ngoài freshness SLA. |
| Role ADMIN được cấp | Quyền mới chỉ xuất hiện theo chính sách refresh/reauth, không tự thay role snapshot tùy tiện. |
| User bị xóa | Context cũ không tiếp tục được dùng khi current account không tồn tại. |
| Disable rồi enable | Phiên/token đã revoke **không hồi sinh**. |
| JWT vẫn chưa tới `exp` | Kiểm revocation/version/freshness nếu hợp đồng yêu cầu. |
| Opaque token bị revoke | Kiểm introspection cache và thời điểm hiệu lực. |
| Multi-node A/B/C | Revoke ở B phải chặn các request từ node khác trong SLA. |
| Cache TTL lớn hơn SLA | Test phơi bày độ trễ sai; không báo revoke tức thì. |
| Request dài sau revoke | Kiểm policy transactional authorization sát lúc commit. |
| Status source bị timeout | Không fail open đối với hành động nhạy cảm. |
| User thuộc nhiều tenant | Quyền/phiên bản scoped theo tenant; không lộ role tenant khác. |
| Logout một browser | Bản sao cookie đó bị từ chối phía server. |
| Logout all | Các session/refresh grants/token thuộc phạm vi cam kết đã xử lý. |
| Custom SecurityContextRepository | Xóa/lưu context đúng API, không còn session mồ côi. |
| Audit/logging | Có actor/action/timestamp mà không lộ cookie/password/hash/token. |

Không chỉ unit test `accounts.disable(...)`. Ít nhất phải test qua security filter chain và response HTTP; khi có cache/cluster, cần integration test trên hạ tầng gần production để xác nhận thời gian thu hồi.

## 13. Bài tập có đáp án

**Câu 1.** Alice đăng nhập lúc 09:00 và `enabled=true`. Admin disable lúc 09:05; Alice vẫn gọi endpoint với cookie cũ và được 200. Lý do khả dĩ?

**Đáp án:** `SecurityContext` đã lưu trong session có snapshot authentication và không tự query database ở request sau. Cần revoke session hoặc status/version check.

**Câu 2.** `Authentication.isAuthenticated()` là true. Có kết luận tài khoản hiện chưa bị khóa được không?

**Đáp án:** Không. Nó không tự kiểm account status mới nhất.

**Câu 3.** Role ADMIN đã bị thu hồi trong DB, nhưng `Authentication.getAuthorities()` ở session cũ vẫn có `ROLE_ADMIN`. Có phải lỗi của `hasRole("ADMIN")`?

**Đáp án:** Không. Authorization dùng authorities trong context nếu không có cơ chế làm mới/thu hồi. Cần giải quyết freshness, không chỉ thay matcher.

**Câu 4.** AuthVersion lúc cấp session là 4; sau disable là 5; sau enable là 6. Version 4 có hợp lệ trở lại không?

**Đáp án:** Không. Chỉ session mới được cấp sau bước cho phép và có version phù hợp mới hợp lệ.

**Câu 5.** JWT còn 30 phút tới `exp`; user đã bị disabled. Resource server chỉ verify chữ ký/`exp`. JWT tự bị từ chối không?

**Đáp án:** Không. Cần policy token revoke/version check hoặc chấp nhận thời gian stale đến expiration đã được đánh giá.

**Câu 6.** Vì sao test session với form login khác test HTTP Basic?

**Đáp án:** Form login thường duy trì authentication bằng session cookie, còn HTTP Basic có thể gửi credentials mỗi request. Hai flow có tần suất kiểm credential/account khác nhau tùy cấu hình.

**Câu 7.** Admin thay role và tăng authVersion trong DB nhưng API đọc replica trễ 20 giây, còn yêu cầu revoke dưới 5 giây. Có đáp ứng không?

**Đáp án:** Không. Phải dùng nguồn đọc đủ mới, cache invalidation hoặc thiết kế consistency phù hợp.

**Câu 8.** Filter kiểm enabled trước khi vào controller; sau đó quyền bị thu hồi trước lúc ghi tiền. Filter đã đủ chưa?

**Đáp án:** Chưa nếu cam kết giao dịch không commit sau revoke. Cần kiểm permission/status sát thời điểm thao tác trong transaction hoặc cơ chế tương đương.

**Câu 9.** Khi người dùng bấm “đăng xuất mọi thiết bị”, chỉ cần xóa cookie ở trình duyệt hiện tại?

**Đáp án:** Không. Phải thu hồi các phiên server-side và credential tiếp tục cấp phiên/token theo phạm vi hệ thống cam kết.

## 14. Tài liệu tham khảo

- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `AuthenticationManager`, `SecurityContextHolder`.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): trạng thái/credential khi xác thực username/password.
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html): lưu và khôi phục `SecurityContext`.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): session lifecycle, concurrent sessions, explicit-save.
- [Spring Security — UserDetails API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetails.html): bốn trạng thái tài khoản và credential.
- [Spring Security — Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): kiểm JWT và token validators.
- [Spring Security — Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): token introspection.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session timeout, lifecycle và revocation.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): kiểm quyền, least privilege, deny by default.

**Kết luận:** Xác thực thành công là sự kiện có **thời điểm**; trạng thái account, credential và quyền có thể đổi sau đó. Không nên trông chờ một lần check lúc login tự làm mất hiệu lực mọi session/JWT đã cấp. Hãy chọn **nguồn trạng thái đáng tin, thời gian hiệu lực, cơ chế thu hồi/kiểm lại và điểm kiểm quyền nghiệp vụ**, rồi thử request cũ sau khi account đã đổi, không chỉ thử login mới.