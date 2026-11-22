# Thông tin tài khoản bị cũ do cache hoặc quyền bị thay đổi trong Spring Security

## 1. Bài toán chẩn đoán

Một quản trị viên vừa bỏ `ROLE_ADMIN` khỏi tài khoản Alice trong cơ sở dữ liệu, nhưng Alice vẫn truy cập được `/admin`. Người khác vừa đổi mật khẩu và thấy đăng nhập bằng mật khẩu cũ vẫn thành công. Một tài khoản bị khóa vẫn sử dụng được session cũ. Cùng một user gọi API qua node A thì bị 403, qua node B lại được 200.

Những triệu chứng này có thể cùng xuất phát từ một vấn đề: **thông tin danh tính hoặc quyền đang được sử dụng là một bản chụp cũ (stale snapshot)**. Tuy vậy, không được kết luận mọi trường hợp đều do “cache”. Trong Spring Security, dữ liệu có thể tồn tại ở nhiều lớp khác nhau:

1. **Nguồn sự thật**: database, LDAP/AD, Identity Provider (IdP), permission service.
2. **Cache của `UserDetails` / account / role**: `UserCache`, `CachingUserDetailsService`, Spring Cache `@Cacheable`, Redis, Caffeine.
3. **`Authentication` đã tạo**: principal và `GrantedAuthority` được nạp tại lần xác thực.
4. **`SecurityContext` đã lưu** trong HTTP session hoặc nơi khác.
5. **Access token / JWT / OIDC claims** đã được phát hành, có thời gian hết hạn riêng.
6. **Cache nghiệp vụ**: quyết định authorization, response cache, gateway, frontend state.
7. **Bản sao dữ liệu / hệ thống phân tán**: DB replica, LDAP replica, các node và IdP.

Mục tiêu của bài là **chẩn đoán đúng lớp gây dữ liệu cũ, sửa đúng ranh giới và kiểm thử hiệu lực của thay đổi quyền/trạng thái**. Trọng tâm Spring Boot 3.x / Spring Security 6.x / Java 17+ (Servlet), có lưu ý cho Spring Security 7.x, Resource Server và WebFlux.

Sau bài học, bạn có thể:
- Định nghĩa rõ “quyền có hiệu lực” so với “quyền mới ghi xuống DB”.
- Phân biệt cache stale với **session snapshot** và **JWT claim snapshot**.
- Đo đạc chính xác `Authentication.getAuthorities()`, thời điểm đăng nhập và phiên bản quyền.
- Thiết kế eviction sau commit, session revocation, token strategy và cache key đúng tenant.
- Viết chương trình Java 17, JUnit 5 kiểm chứng cache stale và credential erasure.
- Đánh giá các race khi thay quyền trên cluster.
- Giải thích vì sao “xóa Redis cache rồi thử lại” không phải giải pháp bảo đảm.

## 2. “Stale” là gì? Phân biệt ba thời điểm

Xét một account:

```text
T0 = 10:00:00  DB: Alice có ROLE_ADMIN
T1 = 10:00:05  Alice login, Authentication A1 có ROLE_ADMIN
T2 = 10:02:00  Admin thu hồi ROLE_ADMIN trong DB
T3 = 10:02:01  Alice dùng session A1 gọi /admin
T4 = 10:04:00  Alice logout, login mới, tạo Authentication A2
```

Có ba câu hỏi khác nhau:

- **DB lúc T3 có gì?** Tại T2 quyền đã thay đổi; nguồn sự thật hiện không còn `ROLE_ADMIN`.
- **Authentication A1 lúc T3 có gì?** Nó có thể vẫn giữ `ROLE_ADMIN` từ T1, vì một Authentication thường mang **snapshot authorities tại lúc tạo**.
- **Authentication A2 lúc T4 có gì?** Phụ thuộc loader/IdP/cache lúc login mới đã thấy dữ liệu T2 hay chưa.

Không thể chỉ đọc DB rồi khẳng định request đã dùng quyền mới. Cũng không thể chỉ đăng xuất/đăng nhập lại rồi khẳng định cache đã được làm mới: nếu loader trả snapshot cũ, **A2 cũng cũ**.

**Một số hiện tượng không phải stale bug:**
- User bị 403 vì thiếu prefix `ROLE_` dù DB đã cấp `ADMIN`: đây có thể là lỗi mapping.
- User được 200 bởi một `SecurityFilterChain` khác không áp policy: đây là lỗi rule/matcher.
- Người dùng vừa đổi role trên màn hình nhưng transaction chưa commit: DB chưa là nguồn sự thật mới.
- Hệ thống cho phép phiên cũ còn hiệu lực tới khi hết TTL theo **chính sách đã công bố**: đó là eventual revocation, cần đánh giá SLA, không tự gọi là bug nếu đúng hợp đồng.
- Frontend còn hiện menu Admin nhưng API đã trả 403: UI cache cũ, **không nhất thiết server cho phép**.

Hãy mô tả vấn đề bằng câu cụ thể: “Sau khi thu hồi quyền lúc T2, **request mới** của Alice trên session đang tồn tại phải bị 403 trong tối đa N giây.” Đó mới là tiêu chí có thể kiểm thử.

## 3. Bản đồ nơi chứa quyền và trạng thái

| Lớp | Giá trị thường giữ | Khi nào được làm mới? | Nếu cũ sẽ thấy gì? |
| --- | --- | --- | --- |
| DB / LDAP / IdP | enabled, locked, groups, roles, password hash | Update/replication của nguồn | Node đọc replica còn dữ liệu cũ |
| `UserDetailsService` | Tạo `UserDetails` từ nguồn | Khi `loadUserByUsername` thực sự chạy | Loader sai mapping hoặc dùng local copy cũ |
| `UserCache` / `@Cacheable` | `UserDetails`, role snapshot, password hash | TTL, evict, update, cache miss | Đăng nhập mới vẫn nhận role/password cũ |
| `DaoAuthenticationProvider` | Xác minh password/account checks | Mỗi authentication attempt; có thể dùng cached user | Có thể xác minh bằng snapshot cũ nếu cache chưa invalidated |
| `Authentication` | Name, `GrantedAuthority`, principal, details | Thường khi xác thực mới hoặc app chủ động thay | Role cũ trên session đang sống |
| `SecurityContextRepository` | Authentication gắn request/session | Load/save context | Request sau tiếp tục dùng snapshot session |
| OIDC/JWT access token | `sub`, `scope`, `roles`, `iat`, `exp` | Khi issuer phát token mới | Token cũ tiếp tục được Resource Server chấp nhận |
| Application authorization cache | `hasAccess(user,object)` hoặc user/tenant permissions | Theo TTL/eviction cụ thể | Quyết định allow/deny cũ dù Authentication mới |
| Gateway/CDN/UI cache | HTTP response hoặc menu | Cache headers/invalidation | Hiển thị quyền/dữ liệu cũ hoặc rò dữ liệu |
| Multi-node | Cache L1 nội bộ + Redis/DB replica | Propagation sau event/TTL | Node A và B quyết định khác nhau |

**Quy tắc chẩn đoán:** muốn biết cần evict cache nào, trước hết phải xác định request đang lấy `Authentication` từ **đâu**. Form login với session, Basic stateless và JWT Resource Server có cách nạp danh tính khác nhau.

## 4. Đường đi username/password với cache

Với Servlet username/password điển hình:

```text
POST /login
   |
   v
UsernamePasswordAuthenticationFilter
   |
   v
ProviderManager
   |
   v
DaoAuthenticationProvider
   |  +--> UserDetailsService / UserCache
   |  +--> kiểm tra account flags
   |  +--> PasswordEncoder.matches(raw, encoded)
   |  +--> tạo Authentication với authorities
   |
   v
ProviderManager erase credentials nếu bật
   |
   v
Success handler + SecurityContextRepository
   |
   v
HTTP session chứa SecurityContext (nếu session-based)
   |
   v
GET /admin sau đó:
   thường dùng Authentication đã lưu trong session
   KHÔNG tự gọi UserDetailsService để tải role mới mỗi lần
```

Tài liệu Spring Security 6.5 mô tả `CachingUserDetailsService`, `UserCache` và `@Cacheable`. Trong mô hình stateless Basic phải so password ở từng request, cache account có thể làm giảm tra cứu; trong session-based form login, `Authentication` đã lưu khiến một lần thay quyền **không tự làm lại login**.

### Những câu hỏi cần trả lời trước khi sửa

1. Có thật sự dùng `CachingUserDetailsService`, `AbstractUserDetailsAuthenticationProvider.setUserCache(...)`, `@Cacheable`, Redis hay cache custom không?
2. Cache **nạp theo username, email, account ID hay tenant + username**?
3. Cache gồm password hash, enabled/locked flags hay chỉ authorities?
4. Tài khoản vừa được cập nhật trong DB chính hay chỉ ở read replica?
5. Mỗi request đến có cookie session hay JWT? Login mới có thực sự xảy ra?
6. Có nhiều app nodes, nhiều cache instances hoặc IdP phát role từ nguồn khác không?
7. Quyền được đổi trong DB có bị custom `GrantedAuthoritiesMapper` / `JwtGrantedAuthoritiesConverter` đổi lại không?
8. Đã có cơ chế invalidation khi đổi role/disable account chưa? Nó chạy **sau commit** hay trước?
9. Nếu token được phát trước thay đổi, policy có cho token đó tiếp tục sống đến `exp` không?
10. Có khả năng UI stale nhưng server đã từ chối đúng không?

Không dùng `SecurityContextHolder.clearContext()` trong một request rồi kết luận đã logout tất cả session: nó chỉ thao tác trên context hiện hành của thread theo cơ chế thường dùng.

## 5. Caching `UserDetails`: hai phương án thông dụng

### 5.1. `CachingUserDetailsService`

Spring Security cung cấp `org.springframework.security.authentication.CachingUserDetailsService` để bọc một `UserDetailsService` và lưu `UserDetails` thông qua `UserCache`. Mục tiêu là tránh load từ datasource ở những lần authentication sau.

Khái niệm:

```text
loadUserByUsername("alice")
        |
        v
UserCache lookup
        |
        +--> HIT: lấy UserDetails đã lưu
        |
        `--> MISS: delegate UserDetailsService -> cache -> trả user
```

`UserCache` là abstraction; phương thức nạp/xóa entry có thể dựa trên implementation, ví dụ `SpringCacheBasedUserCache` sử dụng Spring Cache. Không được suy rằng evict một cache có tên “users” sẽ tự xóa mọi `UserCache` đang hoạt động.

### 5.2. Spring Cache `@Cacheable`

Một phương án khác:

```java
@Cacheable(cacheNames = "userDetailsByUsername", key = "#p0")
public UserDetails loadUserByUsername(String username) {
    return repositoryLookup(username);
}
```

Đây là **snippet** yêu cầu `@EnableCaching`, bean được Spring quản lý, cache manager và lookup thực. `#p0` là tham số đầu tiên của method.

**Cảnh báo 1 — self-invocation:** Spring Cache dùng proxy theo mặc định. Một method trong cùng bean gọi `this.loadUserByUsername(...)` có thể **bỏ qua proxy cache**, khiến hit/miss và eviction không như dự định.

**Cảnh báo 2 — object mutable:** cache chứa `UserDetails` thực, mà `Authentication` lại tham chiếu chính object đó, có thể bị **xóa password hash khỏi object cache** khi `ProviderManager` erase credentials. Tình trạng này không phải dữ liệu cũ đơn thuần; nó có thể khiến login tiếp theo thất bại.

**Cảnh báo 3 — cache key sai:** nếu username không globally unique ở nhiều tenant, key chỉ username có thể trộn role/identity giữa tenants. Cache security-sensitive phải được scope theo định danh ổn định được **server xác minh**.

**Cảnh báo 4 — TTL:** TTL 5 phút cho phép snapshot cũ tồn tại đến 5 phút ở những đường đọc cache (và còn có thể lâu hơn trên session/token). TTL không bảo đảm thu hồi quyền ngay lập tức.

## 6. Vì sao credential erasure liên quan đến cache stale?

Spring Security `ProviderManager` mặc định có `eraseCredentialsAfterAuthentication=true`. Sau khi thành công, nó gọi `eraseCredentials()` nếu result `Authentication` hỗ trợ `CredentialsContainer`. `UsernamePasswordAuthenticationToken` cũng có thể chuyển việc erase xuống principal/details phù hợp. `org.springframework.security.core.userdetails.User` thực thi `CredentialsContainer`.

Nếu `Authentication.getPrincipal()` tham chiếu **cùng một `User` mutable** mà cache giữ:

```text
Cached User instance U:
 U.username = alice
 U.password = $2a$...
 U.authorities = [ROLE_USER]
          |
          +--> provider trả Authentication(principal=U)
                         |
                         v
              ProviderManager.eraseCredentials()
                         |
                         v
                   U.password = null
                         |
                         v
    Cache vẫn trỏ U với password null
    -> đăng nhập lần sau có thể thất bại
```

Tài liệu Spring Security có hai hướng xử lý:

- Có thể **tắt erase credentials** trong một thiết kế cache giữ cùng `UserDetails`, nhưng điều này làm credentials tồn tại lâu hơn ở Authentication/session và cần review bảo mật.
- **Ưu tiên giảm chia sẻ object**: cache một bản snapshot độc lập, rồi dựng `UserDetails` mới mỗi lần xác thực; hoặc custom provider trả principal không chứa password hash, không làm biến đổi cached user.

**Không dùng** `setEraseCredentialsAfterAuthentication(false)` như một “sửa nhanh” khi chưa hiểu loại secret đang nằm trong principal/session. Trong ứng dụng thật, nên giữ hash an toàn ở kho riêng, không giữ raw password và test lần login thứ hai sau lần đầu.

Đây là một nguyên nhân thường gặp của lỗi **“lúc đầu đăng nhập được, sau đó đột nhiên BadCredentialsException dù mật khẩu không đổi”** sau khi bật cache.

## 7. Một thiết kế cache an toàn hơn: snapshot bất biến và principal mới

Thay vì cache `User` mutable của Spring Security, có thể cache **dữ liệu nguồn bất biến** rồi xây `UserDetails` mới theo mỗi authentication attempt.

Ví dụ snapshot:

```java
package example.stale;

import java.util.Set;

public record AccountSnapshot(
        String username,
        String encodedPassword,
        boolean enabled,
        boolean locked,
        Set<String> authorities,
        long securityVersion) {

    public AccountSnapshot {
        authorities = Set.copyOf(authorities);
    }
}
```

**Lưu ý:** record vẫn chứa **password hash**, không phải dữ liệu công khai. Cache snapshot phải có TTL, giới hạn quyền truy cập, encryption-at-rest nếu yêu cầu, và quy trình invalidate password/factor thay đổi. `Set.copyOf` giúp tập quyền không bị mutate vô tình; `String` là immutable nhưng không đảm bảo erase hash khỏi RAM.

Service cached lookup (snippet trong ứng dụng có repository thật):

```java
package example.stale;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CachedAccountSnapshotService {

    private final AccountRepository repository;

    public CachedAccountSnapshotService(AccountRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "accountSecurity", key = "#p0")
    public AccountSnapshot findByUsername(String username) {
        return repository.findSnapshotByUsername(username)
            .orElseThrow(() -> new
                org.springframework.security.core.userdetails
                    .UsernameNotFoundException("Not found"));
    }
}
```

`AccountRepository` là **interface nghiệp vụ cần triển khai**; file trên chỉ có ý nghĩa trong project có repository và cache manager. `findSnapshotByUsername` phải xác định **đúng tenant** trong hệ thống đa tenant, hoặc thiết kế key theo account ID/tenant.

Tạo `UserDetails` riêng trên mỗi lần gọi:

```java
package example.stale;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.stereotype.Service;

@Service
public class SnapshotUserDetailsService implements UserDetailsService {

    private final CachedAccountSnapshotService snapshots;

    public SnapshotUserDetailsService(
            CachedAccountSnapshotService snapshots) {
        this.snapshots = snapshots;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        AccountSnapshot s = snapshots.findByUsername(username);

        return User.withUsername(s.username())
            .password(s.encodedPassword())
            .disabled(!s.enabled())
            .accountLocked(s.locked())
            .authorities(s.authorities().toArray(String[]::new))
            .build();
    }
}
```

**Điểm then chốt:** `CachedAccountSnapshotService` và `SnapshotUserDetailsService` là **hai bean khác nhau**. Gọi qua bean cached service sẽ đi qua Spring Cache proxy. Mỗi lần `UserDetailsService` được thực sự gọi, nó tạo `User` **mới**; nếu principal bị erase sau login, bản snapshot trong cache không bị đụng.

Thiết kế trên tránh **chia sẻ object**, nhưng **không tự giải quyết stale securityVersion/roles**: nếu cache chưa invalidate, `AccountSnapshot` vẫn cũ. Phải bổ sung cơ chế eviction đúng thời điểm.

### Cấu hình cache tối thiểu

Trong cấu hình Spring Boot đã có `spring-context-support` phù hợp và cache manager:

```java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CachingConfig {}
```

Nếu có `spring-boot-starter-cache` và provider (Caffeine/Redis) phù hợp, ứng dụng có thể dùng cache. `@EnableCaching` **không tự chọn TTL**; TTL và sizing do cache provider quyết định. Không dùng một global cache vô hạn cho security data.

## 8. Java 17 độc lập: tái hiện chính xác cache stale và session stale

Chương trình sau dùng **Java 17 thuần JDK**; không cần Spring/DB. Nó mô phỏng nguồn sự thật, cache và một Authentication snapshot đã được tạo từ login. Mục tiêu là chứng minh bằng code rằng **evict cache không đổi một phiên đã tồn tại**.

Tạo file `StaleAuthorityDemo.java`:

```java
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class StaleAuthorityDemo {

    record Account(
            String username, Set<String> roles, long version) {
        Account {
            roles = Set.copyOf(roles);
        }
    }

    record LoginSnapshot(
            String username, Set<String> roles, long version) {}

    private final Map<String, Account> database =
        new ConcurrentHashMap<>();

    private final Map<String, Account> cache =
        new ConcurrentHashMap<>();

    void changeRoles(String username, Set<String> roles) {
        Account old = database.get(username);
        database.put(
            username,
            new Account(username, roles, old.version() + 1)
        );
    }

    void evict(String username) {
        cache.remove(username);
    }

    LoginSnapshot login(String username) {
        Account user = cache.computeIfAbsent(
            username, database::get
        );
        if (user == null) {
            throw new IllegalArgumentException("No such test user");
        }
        return new LoginSnapshot(
            user.username(), user.roles(), user.version()
        );
    }

    static String oneRole(LoginSnapshot snapshot) {
        return snapshot.roles().iterator().next();
    }

    public static void main(String[] args) {
        StaleAuthorityDemo app = new StaleAuthorityDemo();
        app.database.put(
            "alice",
            new Account("alice", Set.of("ROLE_READER"), 1)
        );

        LoginSnapshot oldSession = app.login("alice");

        app.changeRoles("alice", Set.of("ROLE_AUDITOR"));
        LoginSnapshot beforeEvict = app.login("alice");

        app.evict("alice");
        LoginSnapshot afterEvict = app.login("alice");

        System.out.println(
            "initial=" + oneRole(oldSession)
        );
        System.out.println(
            "new-login-before-evict=" + oneRole(beforeEvict)
        );
        System.out.println(
            "new-login-after-evict=" + oneRole(afterEvict)
        );
        System.out.println(
            "existing-session=" + oneRole(oldSession)
        );
        System.out.println(
            "session-stale=" + (
                oldSession.version() !=
                    app.database.get("alice").version()
            )
        );
    }
}
```

Lệnh chạy:

```bash
javac StaleAuthorityDemo.java
java StaleAuthorityDemo
```

**stdout kỳ vọng chính xác:**

```text
initial=ROLE_READER
new-login-before-evict=ROLE_READER
new-login-after-evict=ROLE_AUDITOR
existing-session=ROLE_READER
session-stale=true
```

Giải thích:
1. Lần đầu nạp account version 1 vào cache; phiên cũ có `ROLE_READER`.
2. DB đổi sang version 2/`ROLE_AUDITOR`, nhưng cache chưa đổi: **login mới vẫn thấy cũ**.
3. Sau eviction, lần login mới đọc DB version 2, authorities mới.
4. Phiên đã tạo ở version 1 **không bị sửa**; cần chính sách reauthentication/reload/revocation riêng.

**Giới hạn:** đây là một mô hình Java thread-safe đơn giản để giải thích thời điểm, không phải password verifier, không có `HttpSession`, không có transaction hay JWT. `Set` ở ví dụ chỉ có một role để stdout xác định. Trong sản phẩm thật có thể có nhiều roles và một chuỗi kiểm tra authorization phức tạp hơn.

## 9. “Cache đã xóa nhưng quyền vẫn cũ”: xác định đúng lớp

Một kịch bản phổ biến:

```text
DB quyền đã đổi
   |
   +-- Cache UserDetails: đã evict
   |
   +-- Authentication A1 trong SecurityContext/HttpSession:
   |          vẫn có ROLE_ADMIN từ lần login trước
   |
   +-- JWT đã ký chứa roles: ["ADMIN"] đến giờ hết hạn
   |
   `-- App permission cache: vẫn có allow=true
```

Tại sao `@CacheEvict("accountSecurity")` không đủ?

- Nó chỉ tác động tới **cache có đúng tên/manager** đó.
- `Authentication` đã nằm trong `SecurityContextRepository` không đọc lại `UserDetailsService` cho mỗi request.
- JWT self-contained giữ claims trong token đang được người dùng cầm; xóa Redis user cache không sửa bytes JWT.
- Nếu còn cache quyền ở service hoặc gateway, kết quả authorization vẫn có thể cũ.
- Nếu eviction chỉ chạy ở node A, node B có thể giữ local Caffeine cache.

**Quy tắc ba phép thử:**

| Phép thử | Nếu còn stale | Nghi ngờ ưu tiên |
| --- | --- | --- |
| A. Cùng session cũ gọi endpoint | Cũ, nhưng login mới đã mới | Snapshot session / application authorization cache |
| B. Logout, đăng nhập mới bằng user thật | Vẫn cũ, nhưng DB mới | `UserDetails` cache, IdP, role mapper, DB replica |
| C. Gửi **access token mới** thay token cũ | Token cũ có quyền cũ, token mới đúng | JWT/issuer snapshot theo thiết kế |
| D. Gọi node A rồi B với cùng kiểm thử | Một node cũ | Cache L1, replication lag, deployment version/feature flag |

Đừng “fix” bằng cách refresh UI nhiều lần khi chưa biết request nào thực sự được server authorizing.

## 10. `SecurityContext`, HTTP session và quyền đã nạp

Trong servlet form login, sau khi authentication thành công, kết quả được lưu trong `SecurityContext` theo cơ chế session/repository. Các request tiếp theo thường khôi phục **cùng ý nghĩa Authentication**, gồm tập authorities từ lúc login.

Ví dụ:

```text
POST /login
    user=alice, authorities=[ROLE_ADMIN], securityVersion=12
    |
    v
HttpSession S1 -> SPRING_SECURITY_CONTEXT -> Authentication A1
    |
    v
Admin đổi DB authorities=[ROLE_USER], securityVersion=13
    |
    v
GET /admin với JSESSIONID=S1
    |
    v
SecurityContext A1 vẫn có ROLE_ADMIN
    |
    v
hasRole("ADMIN") vẫn có thể trả ALLOW
```

Lưu ý: session serialization, copy-on-save hoặc repository tùy chỉnh có thể thay hình dạng object được lưu. Điểm quan trọng là **authorization đang dùng snapshot đã xác thực**, không phải nó phải là cùng object Java trong mọi server.

### Thay role trong DB có tự cập nhật session không?

**Không có bảo đảm mặc định.** `DaoAuthenticationProvider` chủ yếu dùng khi **thực hiện authentication**. `authorizeHttpRequests` và `@PreAuthorize` thường đánh giá `Authentication` hiện tại. Chúng không tự động truy vấn role repository mỗi request chỉ vì user đang tồn tại trong session.

### Cách xử lý phù hợp với yêu cầu

- **Rủi ro thấp:** cho session cũ tồn tại đến TTL hoặc lần login kế tiếp nếu sản phẩm chấp nhận.
- **Quyền nhạy cảm:** thu hồi session hiện có khi role bị thay đổi, buộc đăng nhập lại.
- **Phải cập nhật gần thời gian thực:** dùng `securityVersion`/`permissionsVersion` hoặc policy check ở request boundary để từ chối Authentication cũ.
- **Permission theo từng object:** truy vấn policy engine/dữ liệu mới theo resource thay vì chỉ dựa vào role snapshot.

Không trực tiếp mutate `authentication.getAuthorities()` từ một thread admin vào object session khác. `Authentication`/`GrantedAuthority` có thể được dùng đồng thời; đột ngột sửa object chia sẻ có thể tạo race. **Invalidate/re-authenticate** hoặc tạo Authentication mới thông qua flow được kiểm soát an toàn hơn.

## 11. Spring Security 6: custom login và việc lưu context

Nếu ứng dụng tự viết controller/filter đăng nhập, trong Spring Security 6.x `SecurityContextHolderFilter` chủ yếu **đọc** context từ `SecurityContextRepository`; việc muốn nó có hiệu lực trên request sau cần **lưu tường minh**.

Snippet Servlet cho một authentication **đã được kiểm chứng**:

```java
Authentication authenticated =
    authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            username, password
        )
    );

SecurityContext context =
    SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(
    context,
    request,
    response
);
```

Đây là **snippet đặt trong code server** đã có `AuthenticationManager`, `SecurityContextRepository`, `HttpServletRequest`, `HttpServletResponse` và xử lý session strategy/CSRF/session fixation phù hợp. Nó không phải controller đầy đủ. Không tạo token authenticated trực tiếp từ username mà chưa qua provider.

**Hai lỗi cần phân biệt:**
- **Context không được lưu** → user bị logout/anonymous ở request sau, không phải quyền stale.
- **Context được lưu nhưng không được thu hồi sau thay quyền** → user tiếp tục mang authorities cũ.

Khi nâng cấp Spring Security major/minor, kiểm tra lại thiết kế repository và filter chain, không giả định mọi ví dụ từ bản 5.x có cùng persistence semantics.

## 12. Session revocation: logout một phiên khác với thu hồi toàn bộ

`SecurityContextHolder.clearContext()` chỉ xóa context trong phạm vi xử lý hiện tại của thread, **không** duyệt mọi HTTP session của user.

`session.invalidate()` trên request hiện tại chỉ vô hiệu hóa **session đó**, không tự động vô hiệu hóa những session khác của cùng account trên các thiết bị.

Với nhu cầu **logout all sessions khi đổi password/role**, cần session index hoặc repository cho phép tìm session theo principal/account:

- Có thể dùng `SessionRegistry` và cơ chế quản lý phiên của Spring Security Servlet khi cấu hình/kiến trúc phù hợp.
- Với Spring Session (Redis/JDBC), lựa chọn repository hỗ trợ tìm session theo principal, xác thực semantics xóa session và triển khai node/namespace đúng.
- Trên cluster, registry in-memory tại một instance **không biết toàn bộ session** các node khác.
- Khi quyền bị thu hồi khẩn cấp, chỉ expire-mark một session chưa chắc làm mọi request đang chạy bị dừng tức thì; cần policy kiểm tra tại thao tác quan trọng.
- Đối với đăng nhập federated/OIDC, logout phiên app không mặc nhiên hủy phiên IdP hoặc token ở các client khác.

### Session version check

Một cách thường dùng là lưu **security version** trong principal/session tại login, ví dụ `securityVersion=12`, và lưu `currentSecurityVersion=13` ở account repository sau thay quyền. Trước một thao tác nhạy cảm:

```text
if session.securityVersion < account.currentSecurityVersion:
    deny / require reauthentication
else:
    apply role + permission policy
```

Có thể chỉ cần kiểm tra tại route nhạy cảm hoặc dùng một `AuthorizationManager` có khả năng đọc version từ nguồn đáng tin. Đọc từ cache version cũng có rủi ro stale; nguồn version phải có SLA phù hợp.

Không lưu một boolean `rolesFresh=true` do browser tự gửi. Version trong token/session phải được hệ thống tin cậy ký/lưu; giá trị `currentSecurityVersion` phải đến từ authoritative store hoặc cache có chính sách nhất quán.

## 13. Eviction cache: đúng key, đúng thời điểm, đúng các node

### 13.1. Một lệnh `evict` cần chính xác

Với Spring Cache:

```java
Cache cache = cacheManager.getCache("accountSecurity");
if (cache != null) {
    cache.evict(username);
}
```

Đây là **snippet server-side**, không phải chương trình độc lập. `username` phải được chuẩn hóa và map đúng cache key; cache name `accountSecurity` phải đúng với tên dùng trong `@Cacheable`. Trong multi-tenant, không xóa theo username toàn cục rồi coi là đủ.

`@CacheEvict(cacheNames="accountSecurity", key="#p0")` có thể giảm boilerplate, nhưng cần lưu ý:
- Method được gọi qua Spring proxy (self-invocation thường không kích hoạt advice).
- `beforeInvocation=false` là mặc định, nghĩa eviction sau khi method hoàn tất thành công, **không tự chứng minh sau DB commit** nếu có các advice/transaction boundaries khác.
- Nếu transaction rollback, không được để cache chứa phiên bản cho dữ liệu chưa commit.
- `@CachePut` cập nhật cache nhưng không tương đương việc thu hồi session/token cũ.
- Bỏ quên một cache cấp hai như `permissionsByAccountId` vẫn khiến authorization cũ.

### 13.2. Evict sau khi commit

Giả sử update role trong transaction:

```text
BEGIN
    UPDATE account_roles ...
    publish "AccountSecurityChanged"
COMMIT
    -> evict đúng cache entries
    -> phát revocation event tới các instance
```

Spring hỗ trợ `@TransactionalEventListener(phase=AFTER_COMMIT)` để xử lý sự kiện **sau commit thành công** trong giao dịch đang quản lý:

```java
public record AccountSecurityChanged(
        String accountId,
        String username,
        long newVersion) {}
```

```java
@Component
public class LocalSecurityCacheInvalidator {
    private final CacheManager cacheManager;

    public LocalSecurityCacheInvalidator(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onSecurityChange(AccountSecurityChanged event) {
        Cache users = cacheManager.getCache("accountSecurity");
        if (users != null) {
            users.evict(event.username());
        }

        Cache permissions =
            cacheManager.getCache("permissionsByAccountId");
        if (permissions != null) {
            permissions.evict(event.accountId());
        }
    }
}
```

Imports:

```java
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
```

Hai khối trên là **snippet thuộc hai file Java khác nhau** và cần code phát event tại transaction thay quyền. Trong ứng dụng thật:
- Bảo đảm event được publish trong transaction thực.
- Kiểm tra listener chạy sau commit và không mất sự kiện khi process crash.
- Với các cache nhiều node, local listener **chỉ ảnh hưởng process hiện tại**.
- Nếu cần reliability/ordering mạnh, dùng **transactional outbox**, event bus và consumer idempotent, theo dõi retry và dead-letter.
- Quy trình revocation session/token phải phối hợp với việc thay version/cache, không chỉ evict dữ liệu account.

**Đừng nhầm `@TransactionalEventListener(AFTER_COMMIT)` với một cơ chế distributed event bus tự động.**

### 13.3. Chiến lược trên cluster

| Chiến lược | Ưu điểm | Giới hạn |
| --- | --- | --- |
| Chỉ TTL ngắn | Đơn giản, ít coupling | Có cửa sổ quyền cũ đến hết TTL |
| Distributed Redis cache | Các node dùng chung store | Vẫn có local L1 caches, session/JWT snapshots |
| Pub/Sub invalidation | Có thể gần realtime | Thông điệp có thể mất nếu không durable; phải retry/resync |
| Outbox + consumers | Có thể audit/retry/đảm bảo truyền sự kiện tốt hơn | Phức tạp hơn, cần theo dõi lag |
| Version check trước quyết định nhạy cảm | Có thể chặn nhanh quyền cũ | Thêm lookup và điểm nghẽn; nguồn version phải tin cậy |
| Revoke session + token | Mạnh với user nguy cơ cao | Phải bao phủ mọi clients, nodes và token type |
| Không cache quyền nhạy cảm | Dễ nhất quán hơn | Tăng latency/DB load |

Không có một lựa chọn tốt nhất cho mọi hệ thống; phải bắt đầu từ **SLA thu hồi quyền** (ngay lập tức, vài giây, phút, hay chỉ từ lần login mới).

## 14. Chẩn đoán quyền cũ ở OAuth2 Resource Server và JWT

JWT access token tự mang claims đã ký. Ví dụ tại lúc phát token:

```json
{
  "iss": "https://idp.example.org",
  "sub": "alice",
  "aud": ["reports-api"],
  "iat": 1793940000,
  "exp": 1793940900,
  "scope": "reports:read admin"
}
```

**Các timestamp chỉ mang tính minh họa**, không dùng để xác định thời gian hiện tại. Nếu issuer phát token trước khi Alice bị thu hồi `admin`, resource server xác minh JWT vẫn có thể nạp `SCOPE_admin` cho đến khi token hết hạn, trừ khi có thêm kiểm soát revocation/version.

Trong Spring Security Resource Server, `JwtAuthenticationProvider` dùng `JwtDecoder` xác minh token, `JwtAuthenticationConverter` dựng authorities từ claims; mặc định scope/scp thường thành `SCOPE_...`. **`DaoAuthenticationProvider` / `UserDetailsService` không mặc nhiên chạy trên mỗi JWT request**.

Do đó:
- Xóa `UserDetails` cache của login password **không sửa JWT đã phát**.
- Xóa HTTP session của ứng dụng khác **không tự thu hồi JWT**.
- Sửa `roles` trong database **không thay đổi byte của JWT đang lưu ở client**.
- Chuyển role mapping trên resource server có thể thay **cách diễn giải claims**, nhưng chỉ có hiệu lực khi converter chạy theo config mới; không được âm thầm biến một token thiếu quyền thành có quyền.
- Refresh token có thể cấp access token mới mang quyền mới **nếu issuer tải trạng thái account hiện hành**; nếu issuer cũng giữ claims cũ, token mới vẫn stale.
- JWT session cũ có thể tiếp tục hợp lệ khi tài khoản bị disabled nếu server chỉ xác minh signature/`exp`/`iss` mà không check account state/revocation.

### Lựa chọn cho yêu cầu thu hồi quyền

1. **Access token ngắn hạn** + refresh token có rotation/revalidation: giới hạn cửa sổ stale nhưng không cho phép thu hồi ngay trong thời hạn token.
2. **Token revocation** dựa `jti`/token hash hoặc auth-version, kiểm tra tại API boundary: có chi phí lookup; định nghĩa consistency rõ.
3. **OAuth2 introspection / opaque tokens**: kiểm tra trạng thái token qua authorization server hoặc cache introspection có TTL chấp nhận được.
4. **Version claim** (`security_version`) trong token và so với version server hiện hành tại API: token cũ bị chặn khi version tăng.
5. **Policy/permission check động** cho hành động nhạy cảm: không chỉ tin các roles đã đóng băng trong JWT.
6. **Issuer push events** cho các consumers nếu kiến trúc yêu cầu, với cơ chế retry và kiểm chứng.

Một token còn hạn không đương nhiên nên được chấp nhận mãi; đó là **quyết định kiến trúc**. Khi cần khóa tài khoản khẩn cấp, ưu tiên một ranh giới có revocation hiệu lực theo SLA đã định.

## 15. SSO/OIDC, SAML, LDAP: nguồn quyền có thể nằm ngoài ứng dụng

Một số luồng không dùng `DaoAuthenticationProvider`:

- **OIDC login**: principal/authorities có thể được dựng từ ID Token/UserInfo, groups của IdP hoặc mapper riêng; app session có thể giữ kết quả tại lúc login.
- **SAML2 login**: response/assertion và local authorities mapper có thể tạo session snapshot; chỉnh LDAP group sau đó không thay assertion đã nhận.
- **LDAP bind/search**: LDAP groups/attributes có thể cache phía app, directory client, LDAP proxy hoặc replica. Account lock trong LDAP không tự làm mất session app đã cấp.
- **OAuth2 access token**: scopes đến từ issuer; resource server xác minh token, có thể không gọi LDAP/DB ở mỗi request.
- **Passkey/WebAuthn**: xác thực credential bằng public key không tự đồng nghĩa tải lại role mới từ repository nếu session hoặc mapper đã lưu quyền cũ.

Để chẩn đoán, hãy ghi ra **nguồn authority đang thực sự dùng**: `Authentication.getClass()`, loại principal, group mapper, issuer/subject và nơi lưu. Không đụng từng cache một cách ngẫu nhiên.

### OIDC và việc “logout IdP”

Đăng xuất một phiên tại Identity Provider không mặc nhiên xóa:
- Session cookie của RP/app nếu không triển khai Single Logout/back-channel/front-channel theo contract.
- Access token đã được cấp và đang sống.
- Tài khoản/role snapshot trong cache ứng dụng.

Nếu ứng dụng muốn thu hồi ngay quyền của người vừa bị gỡ khỏi nhóm ở IdP, cần hợp đồng provisioning/deprovisioning, session termination hoặc fresh authorization check; không chỉ hiển thị lại màn hình đăng nhập.

## 16. Mapping quyền đúng chưa? Tránh chẩn đoán nhầm stale cache

**Có lúc quyền không hề cũ** mà ứng dụng đọc sai định dạng.

Ví dụ DB có `ADMIN` nhưng Spring rule gọi:

```java
.requestMatchers("/admin/**").hasRole("ADMIN")
```

`hasRole("ADMIN")` mặc định kiểm tra authority `ROLE_ADMIN`, không phải string `ADMIN` thuần. Với JWT resource server, scope `reports:read` thường thành `SCOPE_reports:read`, không phải `ROLE_reports:read`.

| Nguồn | Giá trị đã nạp | Rule | Kết quả kỳ vọng |
| --- | --- | --- | --- |
| `User.withUsername(...).roles("ADMIN")` | `ROLE_ADMIN` | `hasRole("ADMIN")` | Có thể cho qua |
| `.authorities("ADMIN")` | `ADMIN` | `hasRole("ADMIN")` | Không đúng theo prefix mặc định |
| JWT `"scope":"reports:read"` | `SCOPE_reports:read` | `hasAuthority("SCOPE_reports:read")` | Có thể cho qua |
| DB roles mảng `[USER, AUDITOR]` mapper sang `ROLE_...` | `ROLE_USER`, `ROLE_AUDITOR` | `hasRole("ADMIN")` | Không |
| Claim `roles:["ADMIN"]` nhưng converter không đọc | Có thể chỉ có scope authorities | `hasRole("ADMIN")` | Không, nếu chưa map |

Một account trong DB vừa được cấp ADMIN nhưng session không có role, hãy phân loại:

```text
(1) DB/snapshot source có ADMIN?
(2) Loader/mapper trả ROLE_ADMIN?
(3) Authentication mới có ROLE_ADMIN?
(4) Authentication trong session hiện tại có ROLE_ADMIN?
(5) AuthorizationManager dùng rule đúng và chain đúng?
```

Nếu (1) có, (2) không: nguồn/mapping/cache. Nếu (2) có, (3) không: provider/mapper. Nếu (3) có, (4) không: phiên cũ. Nếu (4) có, (5) từ chối: matcher/rule/method security hoặc chính sách khác.

### Kiểm tra `@PreAuthorize` và custom permission evaluator

Ngoài URL rules, method security có thể dùng:

```java
@PreAuthorize("hasAuthority('SCOPE_reports:read')")
public Report readReport(String id) { ... }
```

Nếu dùng custom `PermissionEvaluator` hoặc `AuthorizationManager`, nó có thể **có cache quyết định riêng**, độc lập với UserDetails. Test phải bao phủ cả layer này. Ngược lại, một controller `permitAll` không thể được bảo vệ chỉ bằng việc xóa cache user.

## 17. Runbook chẩn đoán theo triệu chứng

| Triệu chứng | Phép thử ngắn | Nghi ngờ chính |
| --- | --- | --- |
| Đã thu hồi ADMIN nhưng tab cũ vẫn vào được | Login mới từ browser riêng | `Authentication` trong session còn quyền cũ |
| Login mới vẫn nhận role cũ | Đối chiếu loader và cache hit/DB version | `UserDetails`/role cache hoặc IdP/replica |
| Một node cập nhật, node khác chưa | Gắn node id trong telemetry nội bộ | L1 cache, propagation, deployment mismatch |
| Đổi mật khẩu nhưng mật khẩu cũ vẫn đăng nhập được | Test **login mới** với password cũ (tài khoản thử) | Cache password hash cũ/IdP khác |
| Login đầu được, login sau sai password | Kiểm tra cached `UserDetails.getPassword()` | Cached mutable `User` bị erase credentials |
| Đã disable account nhưng session cũ vẫn 200 | Dùng session cũ và session mới | Thiếu session revocation/version check |
| `@PreAuthorize` không thấy quyền mới | Inspect authorities của Authentication | Session snapshot hoặc custom method auth cache |
| JWT cũ còn được admin quyền | Decode **an toàn** claims + iat/exp, verify issuer | Token có quyền cũ; thiếu revocation |
| JWT mới cũng còn quyền cũ | So claims issuer vừa phát | IdP/authorization server claims cache |
| UI menu vẫn có Admin nhưng API 403 | Gọi API trực tiếp bằng test client | Frontend/browser cache cũ, không phải server authorization |
| DB đã đúng nhưng role đổi trễ | Đọc primary/replica có kiểm soát | Replication lag / transaction order |
| Một tenant thấy quyền tenant khác | Test theo account/tenant key | Cache key hoặc query thiếu tenant isolation |
| Logout rồi vẫn dùng Bearer token được | Gửi JWT còn hạn tới resource server test | Logout session không revoke token |
| Chỉ API cũ có quyền lỗi | Xem SecurityFilterChain / matcher | Cấu hình bảo vệ không nhất quán |

**Không dùng dữ liệu khách hàng thật để thử các khả năng bypass.** Dùng test accounts được tổ chức cho phép, role/tenants giả lập và môi trường staging có kiểm soát.

## 18. Phương pháp thu thập bằng chứng, không ghi lộ secrets

Khi có incident “quyền chưa cập nhật”, nên lưu trong telemetry có phân quyền:

- Request trace ID, endpoint và loại request.
- `Authentication` implementation name, principal **internal ID** và tenant ID đã xác minh.
- Danh sách authorities **đã chuẩn hóa**, hoặc hash/phiên bản/tập quyền rút gọn trong môi trường nhạy cảm.
- Thời điểm authentication (`auth_time` nếu có nguồn đáng tin) và session/security version.
- Cache name, key **đã pseudonymize**, hit/miss, TTL, node/instance ID.
- Version của account/permissions tại DB và lần cuối cập nhật.
- Token `iat`, `exp`, issuer/audience và `jti` **đã băm/mã hóa phù hợp**; không lưu raw JWT.
- Authorization decision allow/deny và rule/method đã áp dụng.
- Event invalidation: thay đổi lúc nào, event xuất bản/nhận lúc nào, độ trễ đến từng node.
- Transaction commit time và read-replica lag khi cần.

**Tuyệt đối tránh** log:
- Raw passwords, password hashes, OTP, recovery codes.
- `Authorization` header, `JSESSIONID`, refresh tokens, raw JWT.
- Full `UserDetails.toString()` nếu custom principal chứa PII/secret.
- Toàn bộ session/claims JSON nếu không có lý do hợp pháp và kiểm soát quyền đọc.

Khi debug, ưu tiên một endpoint nội bộ có role bảo trì, trả metadata vừa đủ và bị khóa ở production; không tạo API công khai `"getUserAuthorities?email=..."` vì nó có thể bị dùng để dò membership/role.

## 19. JUnit 5: component test tái hiện role stale rồi sửa bằng eviction

Ví dụ dưới đây dùng **Spring Security thật**, không cần Spring Boot server. Nó có một database giả bằng `ConcurrentHashMap`, một cache snapshot riêng, `DaoAuthenticationProvider` và `ProviderManager`. Mục đích: chứng minh quyền cũ khi cache chưa evict, quyền mới sau eviction, session/authentication cũ vẫn giữ snapshot và dữ liệu cached không bị `eraseCredentials()` phá.

Tạo file `src/test/java/example/stale/StaleAuthoritiesComponentTest.java`:

```java
package example.stale;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.*;

class StaleAuthoritiesComponentTest {

    record AccountData(
        String hash, Set<String> authorities, boolean enabled, long version) {
        AccountData {
            authorities = Set.copyOf(authorities);
        }
    }

    private final Map<String, AccountData> database =
        new ConcurrentHashMap<>();
    private final Map<String, AccountData> cache =
        new ConcurrentHashMap<>();

    private final PasswordEncoder encoder =
        new BCryptPasswordEncoder(4); // Test-only cost.

    private AuthenticationManager manager;

    @BeforeEach
    void setUp() {
        database.clear();
        cache.clear();
        database.put(
            "alice",
            new AccountData(
                encoder.encode("old-password"),
                Set.of("ROLE_READER"),
                true,
                1
            )
        );

        UserDetailsService loader = username -> {
            AccountData data = cache.computeIfAbsent(
                username,
                key -> database.get(key)
            );
            if (data == null) {
                throw new UsernameNotFoundException("Not found");
            }
            // Mỗi request/attempt có UserDetails mới; cached data không
            // bị xóa password hash khi ProviderManager erase credentials.
            return User.withUsername(username)
                .password(data.hash())
                .disabled(!data.enabled())
                .authorities(data.authorities().toArray(String[]::new))
                .build();
        };

        DaoAuthenticationProvider dao =
            new DaoAuthenticationProvider(loader);
        dao.setPasswordEncoder(encoder);
        manager = new ProviderManager(List.of(dao));
    }

    private Authentication login(String password) {
        return manager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", password
            )
        );
    }

    private Set<String> authorities(Authentication auth) {
        return auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());
    }

    @Test
    void newLoginSeesNewRolesOnlyAfterEviction() {
        Authentication first = login("old-password");
        assertEquals(Set.of("ROLE_READER"), authorities(first));

        AccountData old = database.get("alice");
        database.put(
            "alice",
            new AccountData(
                old.hash(),
                Set.of("ROLE_AUDITOR"),
                true,
                old.version() + 1
            )
        );

        Authentication staleNewLogin = login("old-password");
        assertEquals(
            Set.of("ROLE_READER"), authorities(staleNewLogin)
        );

        cache.remove("alice");
        Authentication freshNewLogin = login("old-password");
        assertEquals(
            Set.of("ROLE_AUDITOR"), authorities(freshNewLogin)
        );

        // Authentication được tạo trước khi đổi quyền vẫn không thay.
        assertEquals(Set.of("ROLE_READER"), authorities(first));
    }

    @Test
    void disableMustInvalidateLoadedAccountForNewLogin() {
        Authentication first = login("old-password");
        assertTrue(first.isAuthenticated());

        AccountData old = database.get("alice");
        database.put(
            "alice",
            new AccountData(
                old.hash(),
                old.authorities(),
                false,
                old.version() + 1
            )
        );

        // Chỉ chứng minh cửa sổ stale của cache: vẫn login được.
        assertTrue(login("old-password").isAuthenticated());

        cache.remove("alice");

        assertThrows(
            DisabledException.class,
            () -> login("old-password")
        );
    }

    @Test
    void passwordChangeNeedsCacheInvalidation() {
        login("old-password"); // Populate cache.
        AccountData old = database.get("alice");

        database.put(
            "alice",
            new AccountData(
                encoder.encode("new-password"),
                old.authorities(),
                true,
                old.version() + 1
            )
        );

        // Trước eviction, cache còn hash password cũ.
        assertTrue(login("old-password").isAuthenticated());
        assertThrows(
            BadCredentialsException.class,
            () -> login("new-password")
        );

        cache.remove("alice");

        assertThrows(
            BadCredentialsException.class,
            () -> login("old-password")
        );
        assertTrue(login("new-password").isAuthenticated());
    }

    @Test
    void credentialErasureCannotMutateCachedSnapshot() {
        Authentication result = login("old-password");

        assertNull(result.getCredentials());
        assertTrue(result.getPrincipal() instanceof UserDetails);
        assertNull(
            ((UserDetails) result.getPrincipal()).getPassword()
        );

        AccountData cached = cache.get("alice");
        assertNotNull(cached);
        assertNotNull(cached.hash());
        assertTrue(encoder.matches("old-password", cached.hash()));

        // Lần login thứ hai không bị hỏng vì object cache độc lập.
        assertTrue(login("old-password").isAuthenticated());
    }
}
```

Chạy trong dự án Spring Boot 3.x/Gradle có `spring-boot-starter-security`, `spring-boot-starter-test`:

```bash
./gradlew test --tests example.stale.StaleAuthoritiesComponentTest
```

**Kỳ vọng:** 4 `@Test` pass. Chúng cố tình mô phỏng **cửa sổ bảo mật khi chưa evict** để phát hiện bản chất stale. Trong production, không chấp nhận việc mật khẩu cũ còn đăng nhập được như một feature; phải đưa invalidation vào workflow thật.

### Tại sao đây là test đáng tin hơn `@WithMockUser`?

`@WithMockUser(roles="ADMIN")` dựng sẵn một Authentication giả, không gọi `UserDetailsService`, không kiểm tra password hash hoặc cache. Test mục 19 thực sự gọi `DaoAuthenticationProvider` qua `ProviderManager`, đọc role từ loader (đang cố ý có cache), rồi quan sát authorities và erasure.

**Nhưng test này không bao phủ HTTP session/JWT.** Để kiểm tra phiên cũ, cần test filter chain/session riêng, hoặc dùng version check ở resource. Không sửa kết quả test để giả vờ `Authentication` cũ tự đổi sau eviction.

## 20. HTTP integration tests: phân biệt cache miss và session đang tồn tại

Một test end-to-end cho form login nên có chuỗi:

```text
1. Tạo account test Alice: ROLE_ADMIN, enabled=true, version=1.
2. Browser A (cookie jar A) đăng nhập Alice và GET /admin -> 200.
3. Admin thay role Alice thành ROLE_USER, version=2, COMMIT.
4. Invalidate UserDetails/permission caches trên các node.
5. Browser A GIỮ JSESSIONID cũ, GET /admin.
6. Browser B (cookie jar B) đăng nhập Alice MỚI, GET /admin.
7. So sánh từng kết quả với revocation policy.
```

Nếu chính sách **phải thu hồi ngay**, cả bước 5 và 6 đều phải từ chối quyền admin. Nếu app chỉ evict `UserDetails`, bước 6 có thể đúng còn bước 5 vẫn 200.

### MockMvc: login, kiểm tra session cũ/mới

Đoạn sau là **snippet** để đặt trong integration test của một app **có form login và `MockMvc` thực**, repository account test có thể cập nhật role, eviction service đã được triển khai:

```java
MvcResult first = mvc.perform(
        formLogin().user("alice").password("test-password"))
    .andExpect(authenticated().withUsername("alice"))
    .andReturn();

MockHttpSession oldSession =
    (MockHttpSession) first.getRequest().getSession(false);

// Thay role qua service nghiệp vụ rồi commit/invalidate.
// accountService.replaceAuthorities("alice", Set.of("ROLE_USER"));

MvcResult second = mvc.perform(
        formLogin().user("alice").password("test-password"))
    .andExpect(authenticated().withUsername("alice"))
    .andReturn();

MockHttpSession newSession =
    (MockHttpSession) second.getRequest().getSession(false);

assertNotEquals(oldSession.getId(), newSession.getId());
```

Imports (trong class test có `mvc` và các beans cần thiết):

```java
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
```

Đây chỉ là **sườn kiểm tra session isolation**: phải bổ sung bước thay quyền thực, kiểm tra `get("/admin").session(oldSession)` và `get("/admin").session(newSession)` theo policy sau commit. Không được bỏ bước đó rồi gọi là test quyền stale đã hoàn thành.

**Một lỗi test phổ biến:** dùng `@WithMockUser` cho `/admin` sau khi thay role; test sẽ dựa trên authority fixture, không kiểm tra session/login thực tế.

### Với Resource Server

Dùng hai access tokens thuộc **cùng account**:
- Token T1 được cấp trước khi bỏ quyền.
- Token T2 được cấp sau khi bỏ quyền.
- Gửi T1/T2 đến API, kiểm tra issuer/audience/exp/role và HTTP 200/403.
- Nếu policy yêu cầu revoke T1 ngay, xác minh revocation/version logic; chỉ so T2 là chưa đủ.
- Không dùng `.jwt()` mock test để tuyên bố đã kiểm tra chữ ký hay việc issuer phát claim mới; nó chỉ giúp test authorization với claims giả.

## 21. Race conditions: quyền thay đổi và login diễn ra đồng thời

Giả sử:

```text
Thread LOGIN                         Thread ADMIN
------------                         ------------
load UserDetails version 5
                                     BEGIN
                                     UPDATE roles -> version 6
                                     COMMIT
authenticate with version 5
save HTTP session -> AUTH version 5
                                     publish invalidation event
```

Dù cache eviction chạy sau commit, login có thể tạo Authentication từ snapshot được lấy **trước** thay đổi. Nếu hệ thống đòi **thu hồi mạnh**, cần thêm bước chặn khi sử dụng version cũ, không chỉ evict cho lần load sau.

Một hướng:
- Mỗi thay đổi bảo mật tăng `securityVersion` một cách nguyên tử.
- Mỗi `Authentication`/session chứa version lúc xác thực.
- Khi request nhạy cảm bắt đầu, so với version authoritative hiện tại.
- Nếu version thấp hơn, từ chối và yêu cầu reauthentication.
- Khi API thực hiện thao tác dài/nhạy cảm, cân nhắc kiểm tra lại tại **ranh giới commit nghiệp vụ** để tránh time-of-check/time-of-use.
- Với token, issuer gắn security version hoặc API đọc account version theo token subject.
- Event consumers dùng version **đơn điệu**: event cũ không được ghi đè bản mới.

Không “sửa” bằng cách gọi `evict()` hai lần và hy vọng race biến mất; điều cần thiết là **một bất biến consistency có thể xác minh**.

### Vì sao `@CacheEvict` không tạo tính nguyên tử toàn hệ thống?

Transaction database và cache (đặc biệt Redis/Caffeine) thường không nằm trong **cùng một giao dịch ACID**. Có cửa sổ giữa DB commit và cache invalidation. Event delivery có thể trễ hoặc sai thứ tự. Với quyền cực nhạy cảm, một authoritative version check hoặc cơ chế session/token revocation đáng tin sẽ cung cấp bảo đảm tốt hơn TTL đơn thuần.

## 22. Kiểm tra bất đồng bộ trên nhiều instance

Bài test chỉ chạy một Spring Boot instance khó tái hiện:

```text
T1 node-A cached Alice v5
T2 node-B cached Alice v5
T3 role updated to v6
T4 event delivered to A, B chưa nhận
T5 request A -> role v6
T6 request B -> role v5
```

### Kịch bản test staging có kiểm soát

1. Khởi chạy hai instance với cache local L1 và cùng database test.
2. Cho Alice đăng nhập/gọi permission endpoint qua cả A và B để warm-up cache.
3. Đổi quyền qua một đường quản trị đáng tin, chờ DB COMMIT.
4. Gửi request mới tới từng instance, lưu node ID và authority version.
5. Xác minh propagation trong SLA, ví dụ **N giây được chính sách định nghĩa**.
6. Thử consumer tạm offline rồi reconnect: có replay/resync/outbox không?
7. Thử event đến sai thứ tự: v8 trước v7; v7 không được đè quyền mới.
8. Đối chiếu session cũ và JWT cũ riêng, không ngộ nhận cache-node đã giải quyết tất cả.
9. Test cache miss khi primary/replica lag và retry; dữ liệu không được bốc nhầm tenant.
10. Bảo đảm test không xóa cache dùng chung với production hoặc khiến users thật bị logout.

Lỗi distributed stale không nhất thiết có nguyên nhân “Spring Security framework bug”; có thể là **hệ thống invalidation nằm ngoài framework** chưa đáp ứng yêu cầu nhất quán.

## 23. Thiết kế key và cache security-sensitive

Một key không đủ phân biệt đối tượng có thể biến stale data thành **cross-user privilege leak**:

```text
Cache key = username
Tenant A: username=admin, ROLE_ADMIN
Tenant B: username=admin, ROLE_USER
```

Nếu cả hai cùng key `admin`, `UserDetails` của tenant A có thể được trả cho tenant B. Đây không chỉ là lỗi quyền chậm cập nhật mà là lỗi cách ly tenant nghiêm trọng.

Các quy tắc:
- Sử dụng **stable account ID** kết hợp **tenant ID** khi hệ thống multi-tenant.
- Kiểm tra tenant membership theo dữ liệu server/IdP đã xác minh, không nhận bất kỳ `X-Tenant` header tự khai.
- Key cho permission decision cache cần gồm principal/account, tenant, resource, action, policy version và các điều kiện ảnh hưởng kết quả.
- Tránh key chỉ gồm `ROLE_ADMIN` hoặc `/api/resource` cho quyết định quyền cá nhân.
- Không dùng raw JWT/password làm cache key/log.
- Có invalidation khi account rename, merge, role change hoặc tenant movement.
- Tránh cache các kết quả “allow” vô thời hạn mà không gắn phiên bản policy.
- Giám sát memory growth và cache eviction rate để không dẫn đến OOM hoặc tăng latency bất thường.

**Lưu ý:** `UserDetailsService.loadUserByUsername` chỉ có tham số username theo interface. Nếu sản phẩm có username trùng giữa tenant, phải có contract định danh đầy đủ ở layer xác thực và repository; việc ngầm lấy tenant từ một static/thread-local không được quản lý chặt có thể tạo cross-tenant data leak.

## 24. Cache TTL, negative cache và read replica

### TTL nên dựa trên rủi ro

| Loại dữ liệu | Rủi ro nếu stale | Hướng bảo vệ |
| --- | --- | --- |
| Display name/avatar | Thường thấp | TTL dài hơn nếu UX cho phép |
| `enabled` / `locked` | Cao: user bị khóa vẫn login | Evict ngay, version/revocation cho phiên đang sống |
| Password hash | Cao: mật khẩu cũ tiếp tục được xác minh | Evict sau password change, session/token policy |
| Roles quản trị | Cao: quyền bị thu hồi vẫn có hiệu lực | Session revoke hoặc version check, evict trên mọi node |
| Feature flags giao diện | Thường trung bình/thấp | Cache + server authorization độc lập |
| Scope trong access token | Có thể cao | Short-lived token + revocation/claims refresh |
| Public metadata | Thường thấp | Có thể cache mạnh hơn, không trộn với authorization |

**Không nên sử dụng một TTL mặc định chung cho password hash, roles và avatar** nếu SLA và rủi ro khác nhau.

### Negative caching

Cache “username không tồn tại” cũng có thể gây lỗi: account vừa được tạo vẫn không đăng nhập được cho đến khi negative entry hết hạn; hoặc username đổi nhưng cache âm còn lưu. Negative caching phải có TTL/eviction thích hợp và không trở thành **user enumeration oracle** qua response khác biệt.

### Read replica lag

Một số hệ thống cập nhật account vào primary nhưng `UserDetailsService` đọc replica. Ngay cả khi cache bị xóa, replica vẫn có role cũ, khiến cache nhanh chóng **được lấp lại bằng giá trị stale**. Cần đo:
- Commit LSN/version ở primary.
- Phiên bản trả từ replica.
- Phân phối read-your-writes cho security-sensitive changes.
- Cache refill sau eviction khi replica chưa đồng bộ.

Nếu revoke quyền phải có hiệu lực tức thời, hãy đọc authoritative store cho các quyết định quan trọng hoặc dùng cơ chế version/revocation đáp ứng SLA, thay vì chỉ giảm TTL.

## 25. WebFlux và Redis: cùng vấn đề nhưng ngữ cảnh khác

Trong WebFlux:
- Authentication nằm trong **Reactor Context** (`ReactiveSecurityContextHolder`), không chỉ `SecurityContextHolder` `ThreadLocal`.
- Dữ liệu `ReactiveUserDetailsService` có thể được cache trong một reactive lookup hoặc kho khác.
- `SecurityWebFilterChain` và `ServerSecurityContextRepository` có semantics reactive.
- Một `Mono<UserDetails>`/`Mono<Permission>` bị `.cache()` ở phạm vi singleton có thể trở thành dữ liệu dùng chung không đúng account nếu không có scoping.
- Redis hoặc HTTP session reactive vẫn có TTL và revocation constraints.
- Không gọi `.block()` trong event loop để buộc đọc role mới; dùng reactive datasource hoặc policy phù hợp.

**Phép chẩn đoán vẫn giống nhau:** kiểm tra nguồn dữ liệu, cache, authenticated principal snapshot, session/token, policy mapper và request thực. Nhưng **API không tương đương Servlet**; đừng copy `HttpSecurity`/`SecurityFilterChain` vào WebFlux đang dùng `ServerHttpSecurity`/`SecurityWebFilterChain`.

## 26. Những anti-pattern cần tránh

**Sai 1: “Đổi quyền xong chỉ cần xóa cache.”**  
Không đủ nếu session/JWT đã cấp còn role cũ. Xác định revocation SLA và xử lý toàn bộ đường vào.

**Sai 2: “Mọi request đều tự gọi `UserDetailsService`.”**  
Sai trong session-based login; nhiều request chỉ khôi phục Authentication từ session.

**Sai 3: “JWT sẽ tự phản ánh role mới trong DB.”**  
JWT self-contained giữ claims đã ký đến hết hạn trừ khi có layer revocation/version/policy check.

**Sai 4: “Tắt `eraseCredentialsAfterAuthentication` cho khỏi lỗi.”**  
Có thể khiến credentials lưu lâu hơn; ưu tiên copy/snapshot độc lập để cache không bị mutate.

**Sai 5: “Dùng `@CacheEvict` là chắc chắn eviction sau commit.”**  
Không mặc định đảm bảo mọi tầng transaction/distributed cache; review advice ordering và event timing.

**Sai 6: “Một node đã nhận event nghĩa tất cả nodes đã cập nhật.”**  
L1 caches và event propagation cần quan sát/retry/resync.

**Sai 7: “Dùng `SecurityContextHolder.clearContext()` để logout mọi thiết bị.”**  
Chỉ thao tác context cục bộ, không thu hồi tất cả sessions/JWT.

**Sai 8: “Session logout sẽ vô hiệu hóa JWT.”**  
Không có bảo đảm; token vẫn có `exp` riêng và cơ chế revocation riêng.

**Sai 9: “Test chỉ `@WithMockUser` là đủ.”**  
Nó giả lập Authentication, không kiểm tra cache/loader/login/session thật.

**Sai 10: “Một quyền có trong DB thì `hasRole` chắc chắn thấy.”**  
Cần kiểm tra prefix `ROLE_` và mapping; JWT scope có prefix `SCOPE_` theo cấu hình mặc định.

**Sai 11: “Tạo thêm `synchronized` là hết stale.”**  
Đồng bộ một process không cập nhật cache node khác, session đã cấp hoặc JWT.

**Sai 12: “Lấy quyền từ header client để refresh UI nhanh.”**  
Không bao giờ cấp quyền từ `X-Role`/JSON field không được xác minh.

**Sai 13: “Đẩy role vào Redis cùng key username ở mọi tenant.”**  
Có thể trộn identities và quyền nhiều tenant; key phải có account/tenant scope.

**Sai 14: “Giảm TTL là giải quyết tức thì.”**  
TTL chỉ giới hạn thời gian stale của **một cache**, không xử lý session, JWT hay replication lag.

**Sai 15: “Nếu user vừa đổi role, mutate Authentication ở mọi request.”**  
Tự sửa các object mutable chia sẻ dễ gây race và không giải quyết issuer/token. Thiết kế reauthentication/revocation/version check rõ hơn.

## 27. Quy trình điều tra ngắn theo thứ tự

Khi nhận ticket “quyền không cập nhật”, dùng một checklist có thể tái lập:

1. **Ghi lại kỳ vọng:** quyền nào thay, bởi ai, thời điểm commit nào, thời hạn hiệu lực theo policy.
2. **Xác định endpoint:** đang bị 200, 401, 403 hay UI chỉ hiển thị sai?
3. **Xác định authentication mechanism:** form session, Basic, JWT, SSO, opaque token, WebFlux?
4. **Ghi fingerprint an toàn:** principal ID, authorities, tenant, auth type, `securityVersion`, issuedAt/`iat`, node ID, trace ID.
5. **Đối chiếu database primary và source of truth**: role/version/flags mới thật sự đã commit?
6. **Truy vết loader/cache:** cache nào hit, key nào, snapshot version bao nhiêu, TTL còn lại bao lâu?
7. **Thử login mới từ client riêng** mà không dùng session/cookie cũ; ghi kết quả authorities.
8. **Thử session/token cũ** riêng để phát hiện snapshot chưa revoke.
9. **Đối chiếu mapper/rule:** `ROLE_`/`SCOPE_`, `GrantedAuthoritiesMapper`, `JwtGrantedAuthoritiesConverter`, method security, matcher chain.
10. **Thử từng app node** và backend replica theo test account; đánh giá propagation.
11. **Sửa đúng lớp**: evict cache sau commit, revoke sessions/tokens, version check, hoặc sửa mapping/DB replica.
12. **Thêm test regression** cho cả login mới, phiên cũ và token cũ; đo SLA chứ không chỉ một request thành công.

### Ví dụ kết luận có thể hành động

**Trường hợp 1:** “DB v18, cache v17; logout/login mới vẫn v17.”  
Hướng sửa: cache invalidation hoặc cache refill/replica, không đụng session đầu tiên.

**Trường hợp 2:** “DB v18, cache v18, login mới đúng; session cũ vẫn v17.”  
Hướng sửa: session revocation hoặc version check, không cần xóa cache thêm lần nữa.

**Trường hợp 3:** “Resource Server thấy JWT `iat` trước thu hồi, `exp` còn 20 phút; token mới đúng.”  
Hướng sửa: revocation/short TTL/authorization động theo SLA; không chỉnh `DaoAuthenticationProvider`.

**Trường hợp 4:** “Authentication có `SCOPE_read`, rule đòi `ROLE_read`.”  
Hướng sửa: mapper hoặc rule authorization, không phải cache.

**Trường hợp 5:** “Node A v18, node B v17; chỉ B có cache hit.”  
Hướng sửa: phân phối invalidation/TTL hoặc centralized version, không bắt user thử lại ngẫu nhiên.

## 28. Bảng kiểm QA khi sửa lỗi

### Dữ liệu và cache

- [ ] Source of truth có version/updatedAt và commit order rõ ràng.
- [ ] Caching configuration hiện hành được inventory: `UserCache`, Spring Cache, Redis, Caffeine, local map.
- [ ] Cache keys phân biệt tenant + account; không dùng user-controlled role/tenant.
- [ ] Eviction đúng tên cache/key, thực sự xảy ra sau commit và trên các node liên quan.
- [ ] Cơ chế hồi phục nếu event lost/misordered có monitoring và replay/resync.
- [ ] Password hash ở cached snapshot không bị `ProviderManager` erase qua shared object.
- [ ] Negative cache và DB replica không giữ snapshot cũ quá SLA.
- [ ] Permission cache/decision cache có invalidation riêng.
- [ ] TTL security data được chọn theo rủi ro, không dùng mặc định vô hạn.

### Authentication/session/token

- [ ] Đăng nhập **mới** nhận roles/flags/password hash đúng.
- [ ] Session **đã tồn tại** được revoke/re-auth hoặc version-checked theo policy.
- [ ] `SecurityContextRepository` custom không lưu context sai account/session.
- [ ] Password change/disable account làm session/remember-me tokens hết hiệu lực theo policy.
- [ ] JWT cũ không được dùng cho hành động nhạy cảm nếu revocation SLA yêu cầu.
- [ ] Refresh token phát token mới bằng dữ liệu account hiện hành, không copy roles cũ vô hạn.
- [ ] SSO/IdP group mapping được đối chiếu ở cả nơi cấp token lẫn nơi nhận.
- [ ] Không có endpoint legacy hoặc filter chain khác bỏ qua cơ chế thu hồi.
- [ ] `@PreAuthorize` và object-level permission kiểm tra đúng principal/tenant.
- [ ] Account bị disable không thể bypass bằng passkey/OTT/SSO/recovery yếu hơn.

### Kiểm thử và vận hành

- [ ] JUnit component tests có stale cache trước eviction, fresh load sau eviction.
- [ ] Test việc xóa credentials không phá cached data.
- [ ] HTTP tests có hai browser/session độc lập; phân biệt old/new session.
- [ ] Token tests gồm T1 trước thu hồi và T2 sau thu hồi.
- [ ] Cluster tests có ít nhất hai nodes và trường hợp event đến chậm.
- [ ] Test role revoke, role grant, password change, account disable/lock và tenant change.
- [ ] Đo propagation lag và authorization deny/allow trong SLA.
- [ ] Không log secrets/PII; có trace ID/actor/version/cache hit metadata đủ điều tra.
- [ ] Không tắt password hash/credential erasure chỉ để làm test pass.
- [ ] Đã review race giữa login và role update, cache miss sau replica lag.
- [ ] Có runbook khi cần revoke khẩn cấp, bao gồm session và token paths.

## 29. Câu hỏi tự kiểm tra

**Câu 1:** Sau khi thu hồi `ROLE_ADMIN`, xóa `UserDetails` cache, nhưng browser vẫn vào `/admin` được. Bước kế tiếp nên kiểm tra gì?

**Đáp:** Kiểm tra `Authentication` đã lưu trong session và policy revoke/version. Eviction cache không tự thay authorities của session cũ.

**Câu 2:** Logout rồi login mới vẫn thấy role cũ. Có chắc do session không?

**Đáp:** Không. Cần kiểm tra loader, cache hit/miss, DB primary/replica, IdP claims và role mapper. Session cũ đã không còn nhưng nguồn login mới có thể vẫn stale.

**Câu 3:** Lần login đầu được, lần login thứ hai thất bại sau khi bật cache. Vì sao?

**Đáp:** Có thể cached `UserDetails` và authentication principal tham chiếu cùng `User` mutable; `ProviderManager.eraseCredentials()` xóa password trên object trong cache. Dùng snapshot độc lập và principal mới.

**Câu 4:** Người dùng cầm JWT còn hạn chứa role `ADMIN`. Gỡ role trong DB rồi xóa Redis cache có sửa JWT không?

**Đáp:** Không. JWT chứa claims đã ký. Cần token revocation/version check/TTL hoặc reauthorization phù hợp.

**Câu 5:** Vì sao `@CacheEvict` ở một service nội bộ có thể không hoạt động?

**Đáp:** Khi dùng Spring AOP proxy mặc định, self-invocation trong cùng bean không đi qua proxy; cache advice có thể không chạy.

**Câu 6:** Cùng user ở node A bị 403, node B được 200 sau khi thu hồi quyền. Đầu tiên nên so gì?

**Đáp:** Session/token đang dùng, Authentication version, cache hit/miss, node ID, source replica và việc phân phối invalidation event; không quy hết cho Spring Security.

**Câu 7:** Vì sao quyền `ADMIN` trong DB có thể không thỏa `hasRole("ADMIN")`?

**Đáp:** Vì `hasRole` mặc định đòi authority `ROLE_ADMIN`. Nếu mapper chỉ tạo `ADMIN`, đây là lỗi mapping, không phải stale cache.

**Câu 8:** Có nên xóa toàn bộ Redis trên production mỗi lần đổi role không?

**Đáp:** Không. Nó có thể gây tải, ảnh hưởng session/data khác và vẫn không sửa JWT/session. Nên invalidate đúng key, đúng cache, đúng thời điểm.

**Câu 9:** Trong session login, có thể lấy `SecurityContextHolder.clearContext()` làm “logout all devices” không?

**Đáp:** Không. Nó chỉ xóa context trong luồng hiện tại; phải dùng cơ chế session/token revocation thực sự.

**Câu 10:** Vì sao cần security version khi đã dùng TTL cache rất ngắn?

**Đáp:** TTL cache không xử lý snapshot trên session/JWT và có race. Version check giúp định nghĩa điều kiện từ chối Authentication cũ tại ranh giới cần bảo đảm.

## 30. Tổng kết

Khi thấy thông tin account/quyền bị cũ, hãy **xác định snapshot đang được dùng** trước khi chỉnh cấu hình:

- **Cache `UserDetails` cũ** khiến **authentication mới** vẫn nạp dữ liệu cũ.
- **`Authentication`/session cũ** khiến **request trên phiên đang sống** tiếp tục mang authorities cũ dù database và cache đã cập nhật.
- **JWT/SSO claims cũ** khiến resource server tiếp tục chấp nhận một tập quyền đã được phát hành trước thay đổi.
- **Permission/data cache, multi-node, DB replica** có thể làm quyết định khác nhau giữa request/instance.
- **Lỗi mapper/authorization rule** có thể giống cache stale nhưng thực chất quyền mới không được ánh xạ đúng.

Biện pháp cần gắn với **SLA quyền có hiệu lực**: update nguồn sự thật, invalidate đúng cache **sau commit**, đồng bộ/quan sát các node, thu hồi session/token hoặc so security version ở nơi cần bảo đảm. Với Spring Security, việc bật `@Cacheable`, `SessionRegistry`, hay JWT Resource Server không tự giải quyết toàn bộ bài toán này.

Kiểm thử phải gồm **login mới, session cũ, token cũ, cache hit/miss, thay role/password/account status và nhiều nodes**. Chỉ khi test cả đường cấp Authentication và đường authorization đang hoạt động, hệ thống mới có thể khẳng định quyền được thu hồi hay cập nhật đúng thời hạn.

## 31. Tài liệu tham khảo chính thức

- Spring Security 6.5 — Caching `UserDetails`: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/caching.html
- Spring Security 6.5 — Authentication Architecture / `ProviderManager` erasure: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 — Session Management migrations / explicit context save: https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html
- Spring Security 6.5 — `UserDetails` và credentials management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details.html
- Spring Security — OAuth2 Resource Server JWT authorities and claims: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Framework — Cache Annotations (`@Cacheable`, `@CacheEvict`, proxies): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Transaction-bound Events (`@TransactionalEventListener`): https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Session — HTTP Session and indexed session repositories: https://docs.spring.io/spring-session/reference/http-session.html
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
