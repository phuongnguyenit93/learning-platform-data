# Thu hồi phiên sau khóa tài khoản, đổi mật khẩu hoặc sự cố bảo mật

## 1. Vì sao khóa tài khoản hoặc đổi mật khẩu chưa chắc đăng xuất những thiết bị cũ?

Một ứng dụng sử dụng **Spring Security + HTTP session** thường xác thực username/password **một lần khi login**. Sau đó, mỗi request mang session cookie; Spring Security khôi phục `Authentication` từ `SecurityContext` đã lưu. Vì vậy, thay đổi record người dùng trong database **không mặc nhiên xóa** những session đã được tạo.

Ví dụ:

1. Alice đăng nhập trên laptop và điện thoại; server lưu hai phiên đã xác thực.
2. Quản trị viên khóa tài khoản Alice, hoặc Alice đổi mật khẩu.
3. Hệ thống cập nhật `locked=true` hoặc password hash mới.
4. Laptop tiếp tục gửi cookie của phiên cũ. Nếu context vẫn tồn tại và ứng dụng không có cơ chế kiểm tra lại trạng thái tài khoản, request **có thể tiếp tục được chấp nhận**.

Điểm mấu chốt: `UserDetailsService.loadUserByUsername(...)` và `PasswordEncoder.matches(...)` thường chạy khi **xác thực lần đầu**. Một session đã đăng nhập có thể mang principal/authorities được lưu từ lần trước. Việc thay password hay khóa account ảnh hưởng đến **lần xác thực mới**, nhưng **không tự thu hồi** tất cả kết quả xác thực cũ.

Bài học giải quyết đúng ba yêu cầu:

- **Khóa tài khoản:** ngăn login mới và vô hiệu các session đang tồn tại.
- **Đổi/đặt lại mật khẩu:** yêu cầu người dùng xác thực lại theo chính sách; nếu bị nghi lộ mật khẩu, thu hồi các phiên cũ và credential dài hạn liên quan.
- **Sự cố bảo mật:** thu hồi đúng phạm vi (một session, mọi session của user, một nhóm user hoặc phạm vi hệ thống) và bảo đảm kết quả trên nhiều instance.

**Phạm vi kỹ thuật:** Spring Boot 3.x, Spring Security 6.x, Spring Session 3.x, Servlet/Spring MVC và Java 17+. Trọng tâm là **session-based authentication**. Cuối bài có phần phân biệt với JWT, refresh token, remember-me, OAuth2 và WebSocket, vì các cơ chế này không tự bị vô hiệu chỉ bằng cách xóa HTTP session.

## 2. Phân biệt bốn việc thường bị gọi chung là “logout”

| Thao tác | Có tác dụng gì? | Không tự bảo đảm điều gì? |
|---|---|---|
| `SecurityContextHolder.clearContext()` | Xóa identity khỏi phạm vi thực thi/request hiện tại | Không xóa mọi session của user trên thiết bị khác |
| `request.getSession(false).invalidate()` | Vô hiệu **session hiện tại** mà request đang sử dụng | Không biết mọi session của cùng user |
| `SessionInformation.expireNow()` (Spring Security `SessionRegistry`) | Đánh dấu một session là expired trong registry; filter phù hợp có thể chặn ở request sau | Không nhất thiết xóa ngay session khỏi kho lưu tập trung hay dừng request đang chạy |
| `SessionRepository.deleteById(sessionId)` (Spring Session) | Xóa session cụ thể khỏi kho phiên mà `SessionRepository` quản lý | Không tự thu hồi JWT/access token/refresh token hoặc chấm dứt request đang xử lý |

Một yêu cầu “đăng xuất tất cả thiết bị” phải biết **tất cả các session cần thu hồi** và có quyền xóa/vô hiệu hóa chúng trong kho session mà mọi instance dùng chung.

Không nên dùng `SecurityContextHolder.clearContext()` như lời giải duy nhất cho một sự kiện khóa tài khoản: method này chỉ tác động tới context được gắn với thread/request hiện tại. Nếu đang xử lý sự kiện quản trị ở phiên của admin, nó thậm chí có thể xóa nhầm context của admin trong request đó mà **không** chạm các phiên của người bị khóa.

### Khi nào phiên mất hiệu lực trong thực tế?

Có ít nhất ba mốc thời gian:

- **T0 — trạng thái tài khoản thay đổi:** database đã ghi locked hoặc password revision mới.
- **T1 — các bản ghi session bị thu hồi:** session IDs liên quan được xóa hoặc đánh dấu expired trong kho session.
- **T2 — request sau đó được kiểm tra:** request tiếp theo với session cookie cũ không còn tải được context hợp lệ và nhận yêu cầu đăng nhập lại.

Một request đã tải context **trước T0/T1** có thể vẫn đang chạy. Xóa session không “quay ngược thời gian” hoặc tự hủy HTTP request đang thực thi. Vì vậy, với tác vụ nhạy cảm như chuyển tiền/xóa dữ liệu, cần kiểm tra lại trạng thái tài khoản hoặc một **authentication version/security stamp** tại điểm có ý nghĩa, không chỉ dựa vào thao tác xóa session.

## 3. Cơ chế mặc định của Spring Security không thay thế thu hồi từ xa

Với form login chuẩn, `UsernamePasswordAuthenticationFilter` thường xác thực bằng `AuthenticationManager`, lưu kết quả vào `SecurityContextRepository` và dùng session cookie để nhận diện request tiếp theo. `UserDetailsService` có thể tải mật khẩu hash, cờ `accountNonLocked` và authorities khi login. Nếu chỉ sửa `UserDetailsService`/record trong DB mà không đổi nơi lưu session, các browser đã đăng nhập vẫn có khả năng tải context cũ.

Spring Security có `SessionRegistry` để theo dõi session và hỗ trợ concurrent session control, ví dụ:

```java
List<SessionInformation> active =
    sessionRegistry.getAllSessions(principal, false);

for (SessionInformation info : active) {
    info.expireNow();
}
```

Đây là **đoạn minh họa bên trong service có `sessionRegistry` và `principal`**, không phải chương trình Java chạy độc lập. `expireNow()` đánh dấu session expired; nếu `ConcurrentSessionFilter` được cấu hình đúng, request sau với session đó bị xử lý như phiên hết hạn. Nó không tương đương với `HttpSession.invalidate()` được gọi ngay trên mọi thiết bị.

**Ranh giới cần nhớ:**

- `SessionRegistryImpl` mặc định lưu thông tin trong bộ nhớ một JVM. Khi chạy nhiều instance, registry cục bộ không tự thấy session của node khác.
- Nếu dùng `SessionRegistryImpl` với principal tự viết, `equals/hashCode` phải ổn định để tra đúng user; sự kiện hủy session và tracking cũng phải được cấu hình đúng.
- Cấu hình `maximumSessions(1)` chỉ là chính sách số phiên đăng nhập đồng thời; nó **không tự thu hồi tất cả phiên sau đổi mật khẩu/khóa account**.
- Nếu muốn xóa session server-side ngay trong kho dùng chung, Spring Session cung cấp `SessionRepository` và khả năng tìm session theo principal.

### Sử dụng Spring Session để tìm session của một user

`FindByIndexNameSessionRepository<S extends Session>` mở rộng `SessionRepository`:

```java
Map<String, ? extends Session> sessions =
    repository.findByPrincipalName("alice");

for (String sessionId : sessions.keySet()) {
    repository.deleteById(sessionId);
}
```

Đoạn mã minh họa này giả định biến `repository` có kiểu tương thích với `FindByIndexNameSessionRepository`. Các API quan trọng:

- `findByPrincipalName(username)` trả map `sessionId → Session` có index principal name tương ứng.
- `deleteById(id)` xóa session theo ID khỏi repository. Request sau mang cookie cũ không còn khôi phục được session ấy.
- Khi Spring Session tích hợp với Spring Security theo luồng chuẩn, principal name thường được index từ `SPRING_SECURITY_CONTEXT`.
- Với authentication tùy chỉnh/không lưu context chuẩn, bạn cần xác minh rằng **principal index thực sự được cập nhật**; nếu không, `findByPrincipalName(...)` có thể trả map rỗng dù một số session tồn tại.

Các implementation có khả năng index bao gồm `JdbcIndexedSessionRepository` và `RedisIndexedSessionRepository`. Không phải mọi `SessionRepository` đều hỗ trợ tìm theo principal. Với cluster, cần kho phiên dùng chung và behavior nhất quán giữa các node.

**Chọn định danh ổn định:** nếu email/username có thể đổi, chỉ dựa vào chuỗi username trong session cũ dễ bỏ sót. Production nên có account ID bất biến trong principal/index hoặc có mapping nhất quán khi rename account; phải kiểm chứng mapping thực tế thay vì chỉ tin tên trường.

## 4. Chính sách thu hồi theo loại sự kiện

| Sự kiện | Đổi dữ liệu tài khoản | Xử lý session | Những credential khác cần xem xét |
|---|---|---|---|
| Admin khóa account | Ghi locked/disabled bền vững | Thu hồi **tất cả** session thuộc account; chặn login mới | API keys, refresh tokens, remember-me, service credentials |
| User tự đổi password | Hash password mới, tăng security revision | Thường thu hồi các phiên khác, hoặc tất cả theo chính sách và mức rủi ro | Refresh tokens/remember-me, thiết bị đã lưu credentials |
| Reset password vì nghi lộ | Hash password mới, tăng revision; xác minh user | **Thu hồi tất cả** phiên, yêu cầu đăng nhập lại | Thu hồi refresh tokens, đổi API keys nếu cùng sự cố |
| Phát hiện session cookie bị đánh cắp | Đánh dấu sự cố, tùy mức độ khóa account | Thu hồi session bị nghi lộ hoặc tất cả session user | Kiểm tra IP/device, token và hoạt động bất thường |
| Credential store/issuer bị xâm nhập | Xoay khóa/cấu hình, đánh giá phạm vi | Thu hồi session theo phạm vi ảnh hưởng | JWT signing keys, introspection, refresh-token families |
| Logout thường | Không nhất thiết đổi password/account status | Vô hiệu session **hiện tại** | Nếu user muốn “logout all”, phải có lệnh thu hồi rộng hơn |

**Không dùng một nút “logout all” để tuyên bố đã xử lý mọi dạng token.** HTTP session, refresh token, bearer JWT, OAuth2 access token và WebSocket connection có vòng đời khác nhau. Phải xác định hệ thống thực sự đã phát gì cho client.

### Tại sao phải cập nhật trạng thái trước khi xóa session?

Nếu khóa tài khoản, hãy **ghi trạng thái locked trước**, rồi yêu cầu thu hồi session. Khi đó login mới bị từ chối ngay, dù việc tìm/xóa session mất thêm thời gian. Với đổi mật khẩu, ghi hash mới và tăng security revision trước rồi revoke các session cũ.

Tuy nhiên đây không phải một giao dịch nguyên tử xuyên suốt account DB và session store. Nếu ghi account thành công nhưng kho session lỗi, hệ thống vẫn còn phiên cũ. Cần cơ chế xử lý thất bại: retry có kiểm soát, audit, sự kiện/outbox sau commit, cảnh báo và **kiểm tra revision/trạng thái ở request** để hạn chế cửa sổ rủi ro.

## 5. Ví dụ thực hành: thu hồi tất cả phiên bằng Spring Session JDBC

Chúng ta xây ứng dụng demo có hai tài khoản:

- `alice / alice-secret`: user thường, role `ROLE_USER`, có thể đăng nhập từ nhiều browser.
- `admin / admin-secret`: role `ROLE_ADMIN`, được phép gọi hai endpoint quản trị mô phỏng sự kiện lock hoặc password reset.

Đây là **tài khoản local mẫu**, không dùng mật khẩu này ngoài máy học. Form login chuẩn tạo session, Spring Session JDBC lưu session ở H2 và đánh index principal. Một service quản trị dùng `FindByIndexNameSessionRepository` để tìm/xóa phiên của Alice.

Để minh họa chống request dùng context cũ, principal chứa `credentialRevision`. Mỗi lần lock/reset sẽ tăng revision; một filter sau khi khôi phục session kiểm tra principal revision với account state hiện hành và từ chối nếu không khớp. **Demo dùng account store trong memory**, chỉ phù hợp **một process**; ở production revision phải đến từ database/cache chia sẻ và phải có chiến lược đồng bộ.

### 5.1. Cấu trúc dự án

```text
src/
  main/
    java/com/example/revoke/
      RevokeApplication.java
      AccountDirectory.java
      SessionRevoker.java
      AccountEvents.java
      AccountRevisionFilter.java
      SecurityConfig.java
      ApiController.java
      AdminController.java
    resources/application.properties
  test/
    java/com/example/revoke/SessionRevocationHttpTest.java
```

Dùng Java 17, Spring Boot **3.5.x** và Spring Security/Spring Session phiên bản do Spring Boot quản lý. Trong một dự án Gradle có Boot plugin và wrapper, dependency như sau:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.session:spring-session-jdbc'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot plugin/BOM phải được cấu hình trong build hiện có để resolve version. Đừng trộn Spring Boot 4.x/Spring Security 7.x vào project 3.x khi dùng nguyên ví dụ này; tùy phiên bản API có thay đổi.

File `src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:sessiondemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.session.jdbc.initialize-schema=always
server.servlet.session.timeout=30m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

`spring.session.jdbc.initialize-schema=always` tạo bảng Spring Session cho demo H2. **Không tự bật `always` và sử dụng H2 in-memory như vậy trong production**: dùng DB lâu dài, migration/schema management, timeout/TTL, connection pool và chính sách backup phù hợp. Spring Session thường dùng cookie tên `SESSION` thay vì `JSESSIONID` mặc định của servlet container.

### 5.2. Spring Boot entrypoint

File `src/main/java/com/example/revoke/RevokeApplication.java`:

```java
package com.example.revoke;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RevokeApplication {
    public static void main(String[] args) {
        SpringApplication.run(RevokeApplication.class, args);
    }
}
```

### 5.3. Tài khoản và credential revision

File `src/main/java/com/example/revoke/AccountDirectory.java`:

```java
package com.example.revoke;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public class AccountDirectory implements UserDetailsService {

    private record Account(
        String passwordHash,
        String role,
        boolean locked,
        long revision
    ) {}

    // Demo only: trạng thái account không bền vững, không chia sẻ giữa node.
    private final Map<String, Account> accounts =
        new ConcurrentHashMap<>();
    private final PasswordEncoder encoder;

    public AccountDirectory(PasswordEncoder encoder) {
        this.encoder = encoder;
        accounts.put("alice", new Account(
            encoder.encode("alice-secret"), "USER", false, 1L));
        accounts.put("admin", new Account(
            encoder.encode("admin-secret"), "ADMIN", false, 1L));
    }

    public static final class VersionedUser extends User {
        private static final long serialVersionUID = 1L;
        private final long revision;

        VersionedUser(String username, Account account) {
            super(
                username,
                account.passwordHash(),
                true,  // enabled
                true,  // accountNonExpired
                true,  // credentialsNonExpired
                !account.locked(),
                AuthorityUtils.createAuthorityList("ROLE_" + account.role())
            );
            this.revision = account.revision();
        }

        public long revision() {
            return revision;
        }
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        Account data = accounts.get(username);
        if (data == null) {
            throw new UsernameNotFoundException("Unknown account");
        }
        return new VersionedUser(username, data);
    }

    public boolean isCurrent(VersionedUser principal) {
        Account current = accounts.get(principal.getUsername());
        return current != null
            && !current.locked()
            && current.revision() == principal.revision();
    }

    public void lock(String username) {
        accounts.compute(username, (name, current) -> {
            if (current == null) {
                throw new IllegalArgumentException("Unknown account");
            }
            return new Account(
                current.passwordHash(), current.role(), true,
                current.revision() + 1);
        });
    }

    public void resetPassword(String username, String rawPassword) {
        if (rawPassword == null || rawPassword.length() < 12) {
            throw new IllegalArgumentException(
                "A demo password needs at least 12 characters");
        }
        String newHash = encoder.encode(rawPassword);
        accounts.compute(username, (name, current) -> {
            if (current == null) {
                throw new IllegalArgumentException("Unknown account");
            }
            return new Account(
                newHash, current.role(), current.locked(),
                current.revision() + 1);
        });
    }
}
```

Tại sao revision có giá trị?

- `DaoAuthenticationProvider` tải `VersionedUser` khi login; nó kiểm tra hash, trạng thái account và trả authentication có principal đáng tin.
- `VersionedUser.revision()` là số phiên bản ở **thời điểm đăng nhập**.
- Khi khóa/reset password, state mới tăng revision. Một authentication cũ không còn trùng state mới.
- Filter ở dưới so sánh revision khi có request. Ngay cả khi xóa session chậm hoặc registry/index chưa kịp đồng bộ, context cũ có thể bị từ chối.

**Không dùng password hash làm security stamp** và không đưa password hoặc dữ liệu bí mật vào cookie/response. Demo dùng một `long revision` để dễ hiểu; production nên dùng account ID bất biến và revision lưu bền vững trong DB, có index/cache invalidation phù hợp.

### 5.4. Tìm và xóa session của principal

File `src/main/java/com/example/revoke/SessionRevoker.java`:

```java
package com.example.revoke;

import java.util.List;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;

@Service
public class SessionRevoker {

    private final FindByIndexNameSessionRepository<? extends Session> sessions;

    public SessionRevoker(
            FindByIndexNameSessionRepository<? extends Session> sessions) {
        this.sessions = sessions;
    }

    public int revokeAll(String principalName) {
        // Copy ID trước khi sửa repository; không lặp trực tiếp map đang thay đổi.
        List<String> ids = List.copyOf(
            sessions.findByPrincipalName(principalName).keySet()
        );

        for (String id : ids) {
            sessions.deleteById(id);
        }

        // Số bản ghi được chọn để xóa; không phải cam kết
        // rằng mọi request đang chạy đã dừng.
        return ids.size();
    }
}
```

Trong cấu hình Boot 3.5.x + `spring-session-jdbc`, `JdbcIndexedSessionRepository` triển khai `FindByIndexNameSessionRepository`. Sau khi Spring Security lưu `SecurityContext` vào HTTP session, Spring Session có thể index tên principal. `findByPrincipalName("alice")` phải trả các session đang gắn với Alice, rồi `deleteById(...)` xóa các bản ghi đó khỏi kho JDBC.

Đừng lưu session IDs vào một static `Map<username, sessionId>` tự viết: cách này sai với nhiều device, concurrent login, restart và nhiều application instance. Dùng repository có index hoặc một mô hình session inventory được quản lý nhất quán.

Một giới hạn cần thừa nhận: những session do cơ chế xác thực khác tạo nhưng **không có principal index** sẽ không được tìm thấy. Việc revoke phải đi kèm test xác nhận index nhận diện đủ session, không chỉ dựa vào tên API.

### 5.5. Kết hợp thay đổi tài khoản và thu hồi

File `src/main/java/com/example/revoke/AccountEvents.java`:

```java
package com.example.revoke;

import org.springframework.stereotype.Service;

@Service
public class AccountEvents {

    private final AccountDirectory accounts;
    private final SessionRevoker sessions;

    public AccountEvents(AccountDirectory accounts, SessionRevoker sessions) {
        this.accounts = accounts;
        this.sessions = sessions;
    }

    public int lockAndRevoke(String username) {
        // Chặn login mới và làm revision trong các session cũ bị stale.
        accounts.lock(username);
        return sessions.revokeAll(username);
    }

    public int resetPasswordAndRevoke(
            String username, String newPassword) {
        accounts.resetPassword(username, newPassword);
        return sessions.revokeAll(username);
    }
}
```

Đây là orchestration của sự kiện bảo mật, không phải callback tự động của `PasswordEncoder`. Ứng dụng thật phải gọi logic này từ các workflow có thẩm quyền (account lock, password change, reset, incident response), có xác thực/ủy quyền người thực hiện, audit, retry khi kho session lỗi và xử lý cạnh tranh với login mới.

**Về thứ tự:** đổi state/revision trước, xóa session sau. Trong ví dụ, nếu xóa JDBC thất bại, revision guard vẫn từ chối context cũ **ở các request sau** trong cùng JVM. Trong production, phải lưu revision ở kho dùng chung, đọc/đồng bộ đúng trên mọi node, và không bỏ qua lỗi thu hồi.

### 5.6. Chặn principal cũ ở mỗi request

File `src/main/java/com/example/revoke/AccountRevisionFilter.java`:

```java
package com.example.revoke;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class AccountRevisionFilter extends OncePerRequestFilter {

    private final AccountDirectory accounts;

    public AccountRevisionFilter(AccountDirectory accounts) {
        this.accounts = accounts;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication != null && authentication.isAuthenticated()
                && authentication.getPrincipal()
                    instanceof AccountDirectory.VersionedUser user
                && !accounts.isCurrent(user)) {

            SecurityContextHolder.clearContext();

            HttpSession session = request.getSession(false);
            if (session != null) {
                session.invalidate();
            }

            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        chain.doFilter(request, response);
    }
}
```

Filter này được gắn **trước `AuthorizationFilter`** ở cấu hình bên dưới. Lúc đó Spring Security đã có cơ hội tải `SecurityContext` từ session, nên filter có thể kiểm tra revision của principal trước khi quyết định cho vào endpoint bảo vệ.

Nó không phải token revocation cho mọi loại principal: ví dụ chỉ nhận `AccountDirectory.VersionedUser` của form login demo. Nếu một filter khác tạo principal kiểu khác, phải định nghĩa chính sách riêng và kiểm tra không có bypass. Hãy bảo đảm các luồng nhạy cảm sử dụng nguồn revision tin cậy.

Với hành động đặc biệt quan trọng, **đừng chỉ dựa vào filter một lần ở đầu request**: một thao tác kéo dài có thể đã qua filter trước khi account bị khóa. Business service nên xác minh lại account/revision ngay trước khi commit hành động hoặc dùng cơ chế transaction/authorization phù hợp.

### 5.7. Cấu hình SecurityFilterChain và Spring Security form login

File `src/main/java/com/example/revoke/SecurityConfig.java`:

```java
package com.example.revoke;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    AuthenticationManager authenticationManager(
            AccountDirectory accounts, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(accounts);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager manager,
            AccountDirectory accounts) throws Exception {

        http
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/csrf", "/login", "/error").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/admin/accounts/**")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .exceptionHandling(errors -> errors
                .defaultAuthenticationEntryPointFor(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED),
                    new AntPathRequestMatcher("/api/**")
                )
            )
            // CSRF vẫn bật mặc định cho form login và admin POST.
            .addFilterBefore(
                new AccountRevisionFilter(accounts),
                AuthorizationFilter.class
            );

        return http.build();
    }
}
```

- `formLogin` chuẩn chịu trách nhiệm xác thực, thực thi session strategy và lưu `SecurityContext`. Ở đây không cần tự viết JSON login hay tự gọi `saveContext`.
- `IF_REQUIRED` cho phép lưu login vào session; **không** dùng `STATELESS` cho demo này.
- Endpoint admin yêu cầu `ROLE_ADMIN`; người dùng Alice không thể tự gọi HTTP POST quản trị.
- CSRF được giữ mặc định. Dù admin đã đăng nhập bằng cookie, POST lock/reset vẫn phải có CSRF token hợp lệ.
- Với `/api/**`, client chưa đăng nhập nhận `401` để dễ kiểm tra; giao diện form `/login` vẫn phục vụ login tương tác.
- `AccountRevisionFilter` được tạo bằng `new` trong security chain, **không** gắn `@Component` vào chính filter để tránh bị Servlet container đăng ký thêm một lượt ngoài security chain.
- Trong một ứng dụng dùng nhiều `SecurityFilterChain`, phải kiểm tra filter và chính sách này có mặt ở **mọi chain có thể khôi phục session liên quan**, không chỉ một nhóm URL.

### 5.8. Endpoint thử nghiệm và endpoint sự kiện có quyền quản trị

File `src/main/java/com/example/revoke/ApiController.java`:

```java
package com.example.revoke;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/csrf")
    public CsrfToken csrf(CsrfToken token) {
        return token;
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }
}
```

File `src/main/java/com/example/revoke/AdminController.java`:

```java
package com.example.revoke;

import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AdminController {

    private final AccountEvents events;

    public AdminController(AccountEvents events) {
        this.events = events;
    }

    public record ResetRequest(String newPassword) {}

    @PostMapping("/admin/accounts/{username}/lock")
    public Map<String, Object> lock(@PathVariable String username) {
        int targeted = events.lockAndRevoke(username);
        return Map.of(
            "event", "account_locked",
            "sessionsTargeted", targeted
        );
    }

    @PostMapping(
        path = "/admin/accounts/{username}/reset-password",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Map<String, Object> resetPassword(
            @PathVariable String username,
            @RequestBody ResetRequest body) {

        int targeted =
            events.resetPasswordAndRevoke(username, body.newPassword());

        return Map.of(
            "event", "password_reset",
            "sessionsTargeted", targeted
        );
    }
}
```

Các endpoint quản trị chỉ dành cho **thử nghiệm local có kiểm soát**. Trong production, chức năng đổi mật khẩu của user cần xác thực lại người thao tác, chính sách MFA/rate limit, kiểm tra độ mạnh password, luồng reset có token một lần và log sự kiện. Quản trị viên không nên có endpoint đặt lại mật khẩu tùy ý nếu chưa có kiểm soát chính sách/approval phù hợp.

Để tránh trả về danh sách session ID nhạy cảm, endpoint demo chỉ trả `sessionsTargeted`; số này là số ID được chọn để xóa, **không** chứng minh đã chấm dứt mọi request đang chạy. Với username không tồn tại, demo ném `IllegalArgumentException`; ứng dụng production cần ánh xạ lỗi có kiểm soát và tránh để lỗi thô lộ nội bộ.

## 6. Kiểm chứng qua hai trình duyệt và một sự kiện bảo mật

### 6.1. Trước khi lock: hai session vẫn hợp lệ

Chạy ứng dụng (trong dự án có Boot Gradle wrapper):

```bash
./gradlew bootRun
```

Windows PowerShell: `.\gradlew.bat bootRun`.

Mở hai cửa sổ trình duyệt **có kho cookie độc lập** (ví dụ browser thông thường và private window). Mỗi cửa sổ:

1. Truy cập `http://localhost:8080/login`.
2. Đăng nhập bằng `alice` / `alice-secret`.
3. Gọi `http://localhost:8080/api/me` và xác nhận HTTP `200` với JSON chứa `"user":"alice"`.

Mỗi browser có session cookie riêng. Với Spring Session JDBC, cookie thường tên `SESSION`; dữ liệu phiên nằm trong bảng `SPRING_SESSION` và `SPRING_SESSION_ATTRIBUTES` của H2. Cookie chứa session ID, không chứa password hay toàn bộ SecurityContext.

### 6.2. Thực hiện lock từ admin

Dùng browser thứ ba đã đăng nhập bằng `admin` / `admin-secret`. Vì CSRF bật, phải gửi token hợp lệ khi gọi POST admin. Để thử bằng curl Bash với cookie jar riêng:

```bash
# Lấy CSRF token + session cookie cho admin client.
curl -sS -c admin-cookies.txt -b admin-cookies.txt \
  http://localhost:8080/csrf > admin-csrf.json

TOKEN=$(jq -r '.token' admin-csrf.json)

# Form login chuẩn, không gửi JSON ở /login.
curl -i -c admin-cookies.txt -b admin-cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  --data-urlencode 'username=admin' \
  --data-urlencode 'password=admin-secret' \
  http://localhost:8080/login

# Sau khi login, lấy token CSRF mới vì token cũ có thể bị xóa.
TOKEN=$(curl -sS -c admin-cookies.txt -b admin-cookies.txt \
  http://localhost:8080/csrf | jq -r '.token')

curl -i -c admin-cookies.txt -b admin-cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -X POST http://localhost:8080/admin/accounts/alice/lock
```

**Kết quả dự kiến:** POST quản trị trả `200`, body gồm `"event":"account_locked"` và số session được chọn. Hai browser Alice gọi lại `/api/me` sẽ không được nhận diện bằng phiên cũ (dự kiến `401` từ cấu hình API). Alice thử đăng nhập mới bằng password trước đây cũng thất bại vì tài khoản đã `locked`.

Với demo H2 in-memory, mọi session biến mất khi tiến trình dừng; đây **không** phải cách thu hồi phiên production. Việc đóng browser hoặc xóa cookie trên thiết bị admin cũng không thu hồi cookie trên hai thiết bị Alice. Kho session tập trung mới là nơi có thể xóa phiên từ xa.

### 6.3. Reset password thay vì lock

Trên một lần chạy mới của ứng dụng (để reset trạng thái demo), Alice có thể login trên hai thiết bị. Admin gọi:

```bash
# Đã login và có admin-cookies.txt từ bước trước.
TOKEN=$(curl -sS -c admin-cookies.txt -b admin-cookies.txt \
  http://localhost:8080/csrf | jq -r '.token')

curl -i -c admin-cookies.txt -b admin-cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"newPassword":"a-new-secret-password"}' \
  http://localhost:8080/admin/accounts/alice/reset-password
```

Kết quả: hash/password revision thay đổi, tất cả session Alice tìm được bị xóa. Browser Alice dùng cookie cũ nhận `401` cho `/api/me`; login lại với password cũ thất bại, login với password mới thành công (nếu account chưa bị khóa). Nếu vừa gọi lock trước đó, account vẫn locked; reset password trong demo **không tự mở khóa**. Đây là chính sách an toàn: password reset và unlock là hai sự kiện riêng.

**Tại sao không dùng một “log out user” bằng cách xóa cookie trên client admin?** Vì server không thể dùng response gửi cho browser admin để xóa cookie nằm trong browser Alice. Điều cần xóa là **session phía server**, theo các ID gắn với Alice.

## 7. Kiểm thử tự động qua HTTP thực: hai client, một session store

Thay vì chỉ unit-test `revokeAll` trả số ID, bài test dưới đây chạy Spring Boot trên random port. Mỗi `HttpClient` có `CookieManager` riêng, đại diện một browser. Vì dùng HTTP thực, ta kiểm tra được cookie, login chuẩn, session JDBC và request sau khi thu hồi.

File `src/test/java/com/example/revoke/SessionRevocationHttpTest.java`:

```java
package com.example.revoke;

import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SessionRevocationHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    @Autowired
    AccountEvents events;

    private HttpClient client() {
        return HttpClient.newBuilder()
            .cookieHandler(new CookieManager(
                null, CookiePolicy.ACCEPT_ALL))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();
    }

    private URI uri(String path) {
        return URI.create("http://localhost:" + port + path);
    }

    private HttpResponse<String> get(HttpClient client, String path)
            throws Exception {
        return client.send(
            HttpRequest.newBuilder(uri(path)).GET().build(),
            HttpResponse.BodyHandlers.ofString());
    }

    private String csrf(HttpClient client) throws Exception {
        HttpResponse<String> response = get(client, "/csrf");
        assertEquals(200, response.statusCode());
        return mapper.readTree(response.body())
            .get("token").asText();
    }

    private HttpResponse<String> login(HttpClient client, String password)
            throws Exception {
        String form = "username=alice&password=" +
            URLEncoder.encode(password, StandardCharsets.UTF_8);

        return client.send(
            HttpRequest.newBuilder(uri("/login"))
                .header("Content-Type",
                    "application/x-www-form-urlencoded")
                .header("X-CSRF-TOKEN", csrf(client))
                .POST(HttpRequest.BodyPublishers.ofString(form))
                .build(),
            HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void passwordResetAndLockRevokeExistingSessions() throws Exception {
        HttpClient laptop = client();
        HttpClient phone = client();

        // Hai browser có session cookie độc lập.
        assertEquals(302, login(laptop, "alice-secret").statusCode());
        assertEquals(302, login(phone, "alice-secret").statusCode());
        assertEquals(200, get(laptop, "/api/me").statusCode());
        assertEquals(200, get(phone, "/api/me").statusCode());

        // Đổi password làm session cũ không còn được chấp nhận.
        int targeted = events.resetPasswordAndRevoke(
            "alice", "a-new-secret-password");
        assertTrue(targeted >= 2);

        assertEquals(401, get(laptop, "/api/me").statusCode());
        assertEquals(401, get(phone, "/api/me").statusCode());

        // Password mới cho phép tạo phiên mới.
        HttpClient freshBrowser = client();
        assertEquals(302,
            login(freshBrowser, "a-new-secret-password").statusCode());
        assertEquals(200, get(freshBrowser, "/api/me").statusCode());

        // Khóa account thu hồi luôn phiên mới.
        int afterLock = events.lockAndRevoke("alice");
        assertTrue(afterLock >= 1);
        assertEquals(401, get(freshBrowser, "/api/me").statusCode());

        // Khi locked, login mới bị từ chối theo form-login failure.
        HttpClient newBrowser = client();
        HttpResponse<String> failure =
            login(newBrowser, "a-new-secret-password");
        assertEquals(302, failure.statusCode());
        assertTrue(failure.headers()
            .firstValue("Location").orElse("")
            .contains("/login?error"));
        assertEquals(401, get(newBrowser, "/api/me").statusCode());
    }
}
```

Chạy:

```bash
./gradlew test
```

Windows: `.\gradlew.bat test`.

Test này kiểm tra các điều quan trọng:

- Hai HTTP client độc lập cùng có session đã xác thực.
- Một sự kiện password reset khiến **cả hai client** không dùng được session cũ.
- Password mới có thể login lại khi tài khoản không bị khóa.
- Khóa tài khoản hủy phiên hiện hành và chặn cả login mới.
- Session JDBC index thực sự tìm được ít nhất hai phiên; nếu `findByPrincipalName` không index được, test sẽ phát hiện qua `targeted`.

Đây là ví dụ integration test dành cho project Boot 3.x có build phù hợp; trạng thái in-memory của `AccountDirectory` có thể ảnh hưởng nếu thêm test khác dùng chung application context. Khi mở rộng test suite, cần reset fixture hoặc dùng context riêng cho các ca thay đổi account. Test này chỉ có **một** test case thay đổi state theo thứ tự rõ ràng.

## 8. Vì sao chỉ xóa session vẫn chưa đảm bảo mọi hành động dừng lập tức?

Giả sử request A đã lấy `SecurityContext` và qua `AuthorizationFilter` ở thời điểm 10:00:00. Sau đó admin khóa account lúc 10:00:01. A đang chạy service mất 15 giây và commit dữ liệu lúc 10:00:15.

Thao tác `deleteById(sessionId)` lúc 10:00:01 giúp **request đến sau** không tải được session, nhưng không tự dừng A đã bắt đầu. Một filter kiểm tra revision ở đầu request cũng không bảo đảm A không tiếp tục nếu revision đổi **sau khi filter đã chạy**.

Nếu cần hiệu lực mạnh cho giao dịch nhạy cảm, hệ thống phải xác định điểm kiểm soát:

- Kiểm tra lại account status/security revision khi thực thi business command và ngay trước khi commit tác vụ có rủi ro.
- Thực hiện truy vấn/khóa cập nhật nhất quán trong transaction hoặc optimistic locking theo model dữ liệu.
- Khi sự cố lớn, có thể bật chế độ block giao dịch/risk hold trong hệ thống backend, thay vì chỉ trông chờ tầng HTTP auth.
- Đảm bảo event revoke phát **sau** khi transaction đổi trạng thái account đã commit; có cơ chế retry/outbox và alert khi delete session thất bại.
- Khi chạy cluster, version guard cần dữ liệu **chung** có giới hạn độ trễ cache. Nếu cache stale lâu, việc check revision không tạo “thu hồi tức thì” như kỳ vọng.

**Cam kết thực tế nên ghi rõ:** “các request mới bị từ chối sau khi session đã bị xóa hoặc revision mới đã được nhận biết” là cam kết có thể test. “Mọi request đã bắt đầu tự hủy tức khắc” không phải tác dụng mặc định của Spring Session.

## 9. Thu hồi khi ứng dụng có nhiều instance

### Với HttpSession trong memory của Servlet container

Nếu mỗi node giữ session local, một ứng dụng chạy 3 node có thể không biết tất cả session khác node. `SessionRegistryImpl` in-memory cũng không chia sẻ toàn bộ registry. Xóa session trên node A không bảo đảm xóa được session thuộc node B.

### Với Spring Session JDBC hoặc Redis

Spring Session thay `HttpSession` bằng repository dùng kho dữ liệu ngoài. Khi tất cả node dùng chung repository/schema/namespace, xóa session ở node A có thể khiến request tiếp theo ở node B không tải được session đã xóa.

Cần kiểm tra:

- Cùng dữ liệu store và namespace; không vô tình chia tách theo deployment.
- Principal index có đủ session và dùng định danh bất biến.
- Đồng bộ dữ liệu session, serialization và expiration/cleanup phù hợp.
- Hệ thống có bao nhiêu backend phát credentials khác ngoài session (API gateways, auth proxies, token services).
- Ở Redis/eventual processing, hiểu độ trễ index/event và cơ chế retry; không suy luận mọi backend có tính nhất quán mạnh như nhau.
- Có telemetry phù hợp để xác nhận số session tìm thấy, số xóa, lỗi kho phiên và request bị chặn sau đó mà **không** ghi session ID thô.

Đối với nghiệp vụ yêu cầu thu hồi thật nhanh, việc **tăng credential revision trên account store chung** và kiểm tra ở request quan trọng là lớp bổ sung hữu ích, vì không phụ thuộc hoàn toàn vào một lần liệt kê session.

## 10. SessionRegistry.expireNow và SessionRepository.deleteById khác nhau

| Tiêu chí | `SessionRegistry.expireNow` | Spring Session `deleteById` |
|---|---|---|
| Nguồn session ID | `SessionRegistry.getAllSessions(principal, ...)` | `FindByIndexNameSessionRepository.findByPrincipalName(...)` |
| Tác động | Đánh dấu expired trong registry | Xóa bản ghi session từ kho repository |
| Khi request cũ bị từ chối | Khi filter hỗ trợ xử lý expired session ở request kế tiếp | Khi request sau không thể tải session đã xóa |
| Có sẵn tracking toàn cluster? | `SessionRegistryImpl` mặc định không | Có thể nếu các node dùng kho chung/index đúng |
| Yêu cầu cấu hình đi kèm | Tracking session, event listener, `ConcurrentSessionFilter` khi dùng expire flow | Spring Session repository/filter, principal index, kho lưu chung |
| Có xóa JWT/refresh token? | Không | Không |
| Có chấm dứt request đã khởi chạy? | Không | Không |

Nếu đã dùng concurrent sessions với `maximumSessions(...)`, hãy đọc và tuân thủ cơ chế `SessionRegistry` của cấu hình thực tế. Nếu mục tiêu là thu hồi session từ xa, một kho Spring Session hỗ trợ index có thể cho phép xóa trực tiếp. Hai phương án không nhất thiết loại trừ nhau, nhưng không nên duy trì hai nguồn “sự thật về session” mà không có quy tắc đồng bộ.

## 11. Token, remember-me và WebSocket không tự mất hiệu lực khi xóa session

### HTTP Basic

Client có thể gửi lại `Authorization: Basic base64(username:password)` ở request sau. Sau đổi mật khẩu, password cũ sẽ bị từ chối **nếu** nguồn dữ liệu xác thực thực sự đã được cập nhật. Nhưng nếu account vẫn còn password hợp lệ ở nơi khác, Basic vẫn đăng nhập lại. Xóa session không thay thế việc cập nhật nguồn credentials.

### JWT access token

Một JWT được ký hợp lệ, chưa hết hạn, có issuer/audience đúng có thể tiếp tục được resource server stateless chấp nhận dù HTTP session đã bị xóa. Muốn thu hồi ngay cần một trong các thiết kế phù hợp: access token ngắn hạn và kiểm tra revision/user status, denylist theo token ID, token introspection có trạng thái, hoặc xoay signing key theo phạm vi ảnh hưởng. Cách nào cũng có trade-off hiệu năng/độ trễ/bộ nhớ.

**Không mặc định mật khẩu đổi sẽ tự làm mọi JWT cũ hết hạn.**

### Refresh token và OAuth2/OIDC

Refresh tokens thường do Authorization Server hoặc token store chuyên trách quản lý. Phải thu hồi refresh-token family/session của authorization server theo event; chỉ xóa session tại Resource Server không đủ. Nếu có API token OAuth2, cân nhắc token revocation/introspection theo protocol và chính sách cụ thể.

### Remember-me

Remember-me cookie/token có thể xác thực lại user sau khi HTTP session bị xóa. Nếu ứng dụng dùng persistent remember-me tokens, cần vô hiệu các token liên quan (hoặc thiết kế security revision/rotation). Nếu không, browser có thể tạo lại một phiên từ remember-me sau revocation.

### WebSocket và kết nối dài

Một WebSocket/SSE đã được xác thực khi handshake có thể tiếp tục hoạt động sau khi session HTTP bị xóa nếu ứng dụng không tích hợp cơ chế close connection, session invalidation events hoặc authorization lại trên message. Spring Session có integration cho WebSocket; hãy kiểm tra cơ chế được sử dụng thực tế.

### Cookie trên browser

Bạn không thể xóa trực tiếp cookie trong browser của người dùng khác bằng cách gửi response cho admin. Xóa server-side session làm cookie cũ **không còn hiệu lực** khi sử dụng, còn browser có thể vẫn giữ cookie cho tới khi hết hạn/xóa. Phản hồi của browser sở hữu cookie có thể nhận `Set-Cookie` để dọn dẹp khi nó gọi API.

## 12. Quy trình ứng phó sự cố bảo mật

Một playbook thu hồi phiên nên có các bước rõ ràng:

1. **Xác định phạm vi:** session ID cụ thể, user ID, nhóm tenant hay toàn bộ hệ thống. Ghi lại lý do, actor, correlation/event ID và thời điểm.
2. **Chặn tạo credential mới khi cần:** khóa account, disable access, reset password hoặc rotate khóa liên quan theo quyết định bảo mật.
3. **Ghi trạng thái/revision bền vững:** đây là cơ sở để mọi node bác bỏ context cũ.
4. **Thu hồi session được lập chỉ mục:** liệt kê theo principal/account ID; xóa khỏi kho phiên tập trung; xử lý lỗi và retry có giới hạn.
5. **Thu hồi các token khác:** refresh token, remember-me, API key, OAuth grants, bearer token theo kiến trúc.
6. **Thông báo/tạo yêu cầu xác thực lại:** UX nên giải thích phiên đã hết hiệu lực, tránh lộ chi tiết sự cố cho client không được phép.
7. **Đo và kiểm chứng:** yêu cầu mới dùng cookie/token cũ phải bị từ chối; tài khoản bị khóa không thể login; nếu đổi password, credentials cũ bị từ chối và credentials mới hoạt động theo chính sách.
8. **Giám sát hậu sự kiện:** tìm session bất thường còn tồn tại, request đang xử lý, endpoint ít dùng, lệch đồng bộ giữa các node, WebSocket và token không bị thu hồi.

Với sự cố quy mô lớn, “thu hồi mọi session” có thể gây tải cao và làm gián đoạn người dùng. Thiết kế theo batch/rate limit, kiểm soát retry, ưu tiên đối tượng rủi ro và dùng **revocation epoch** tập trung khi muốn vô hiệu đồng loạt mà không phải xóa từng ID ngay lập tức. Không quét/xóa database một cách mù quáng khi chưa biết namespace hoặc phạm vi.

## 13. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Account locked nhưng cookie cũ vẫn vào API | Session cũ còn `SecurityContext`; chưa revoke hay chưa check account version | Gọi lại API bằng browser từng login trước lock |
| `findByPrincipalName(...)` trả rỗng | Principal index không được tạo, sai username/account ID, store khác | Kiểm tra session store và nguyên tắc index từ context |
| Admin gọi revoke trả 200 nhưng user vẫn login được | Chưa cập nhật account locked/password, hoặc credentials khác vẫn hợp lệ | Thử login mới bằng cơ chế cũ và cơ chế khác |
| Xóa session A nhưng user còn một browser khác | Chỉ xóa current session, chưa liệt kê mọi session | Tạo 2 cookie jar độc lập rồi test |
| Request vẫn hoàn thành sau revoke | Đã bắt đầu trước khi bị thu hồi | Kiểm tra tại business action/transaction boundary |
| Ứng dụng nhiều node revoke không đồng đều | Session store/registry cục bộ, eventual index/cache | Kiểm tra routing, store chung, invalidation events |
| Đổi password xong JWT vẫn vào API | Resource server kiểm token độc lập với password | Kiểm tra exp, introspection, revision, token revocation |
| Xóa session nhưng browser tự đăng nhập lại | Remember-me hoặc SSO đang active | Thu hồi remember-me/OIDC session phù hợp |
| `SessionInformation.expireNow()` nhưng DB vẫn có session | Registry chỉ đánh dấu expired để xử lý ở request sau | Kiểm tra `ConcurrentSessionFilter` và cơ chế registry |
| GET protected trả `403` thay vì `401` | CSRF, thiếu quyền hoặc entry point khác | Phân biệt authentication, authorization và filter chain |
| Password reset khi đang locked vẫn không login được | Demo reset không tự unlock | Xác minh policy unlock/approval riêng |
| Người dùng bị đá ra nhưng request khác mới login ngay | Revocation race với login mới | Dùng account revision, ghi state trước và kiểm soát creation |

## 14. Checklist áp dụng trong dự án thật

- [ ] Xác định chính xác session store (Servlet local, Redis, JDBC) và các instance cùng dùng một nguồn.
- [ ] Có thể tìm **tất cả** session theo principal/account ID ổn định; đã test index với hai thiết bị.
- [ ] Khi lock/reset, account state/security revision thay đổi trước rồi phiên cũ mới bị thu hồi.
- [ ] Lỗi delete/list sessions không bị nuốt; có retry/outbox, cảnh báo và theo dõi kết quả.
- [ ] Ngăn login mới khi locked/disabled; password mới được hash bằng encoder phù hợp.
- [ ] Request mới dùng session cookie cũ bị từ chối; không chỉ kiểm tra response của admin.
- [ ] Đối với hành động nhạy cảm, có kiểm tra lại trạng thái/revision khi commit để giảm rủi ro request đang chạy.
- [ ] Các node dùng chung account revision hoặc có cơ chế cập nhật cache với độ trễ được kiểm soát.
- [ ] Refresh token, remember-me, JWT, API key và WebSocket được xem xét riêng.
- [ ] Mọi endpoint lock/reset được bảo vệ bởi role, xác minh actor, CSRF (với cookie), rate limit, audit; không lộ session ID hoặc raw credentials trong log.
- [ ] Có test đa thiết bị, restart node, session timeout, race và lỗi kho session.
- [ ] Thông báo cho user khi cần đăng nhập lại, nhưng không tiết lộ chi tiết nhạy cảm của sự cố cho người không có quyền.

**Ghi nhớ:** **Khóa account** kiểm soát lần xác thực tiếp theo; **thu hồi session** làm vô hiệu những lần đăng nhập đã được lưu; **security revision và kiểm tra tại request/business boundary** giúp thu hẹp khoảng trống do cạnh tranh và session cũ. Trong một sự cố thật, phải xử lý thêm mọi cơ chế cấp credential đang được sử dụng.

### Tài liệu tham khảo

- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Concurrent Sessions Control](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html#_configuring_concurrent_session_control)
- [Spring Session 3.5 — Spring Boot JDBC](https://docs.spring.io/spring-session/reference/3.5/guides/boot-jdbc.html)
- [Spring Session — Find Sessions by Username](https://docs.spring.io/spring-session/reference/guides/boot-findbyusername.html)
- [FindByIndexNameSessionRepository API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/FindByIndexNameSessionRepository.html)
- [JdbcIndexedSessionRepository API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/jdbc/JdbcIndexedSessionRepository.html)
