# Bộ nhớ đệm UserDetails và xử lý thay đổi quyền, khóa tài khoản trong Spring Security Servlet

## 1. Vì sao đây là một vấn đề bảo mật, không chỉ là tối ưu hiệu năng?

Trong Spring Security trên **Servlet stack** (Spring MVC, Servlet container, `SecurityFilterChain`), `UserDetailsService.loadUserByUsername(username)` thường đọc thông tin tài khoản từ cơ sở dữ liệu hoặc một identity store. Gọi lặp lại kho dữ liệu có chi phí; bộ nhớ đệm (cache) có thể giảm độ trễ đăng nhập và số lần truy vấn.

Nhưng dữ liệu được cache không chỉ gồm tên hiển thị. Một `UserDetails` thường chứa **mật khẩu đã băm, authorities/roles, cờ enabled/locked, trạng thái hết hạn tài khoản hoặc credential**. Khi quản trị viên tước quyền, khóa tài khoản hoặc người dùng đổi mật khẩu, bản đã lưu trong cache có thể trở nên **lỗi thời (stale)**. Nếu authentication pipeline vẫn dựa vào bản cũ, hệ thống có thể cho phép một lần xác thực mà đáng lẽ phải bị chặn.

Thêm một vấn đề độc lập: ngay cả khi `UserDetails` cache đã được xóa, **`Authentication` đang nằm trong `SecurityContext` của phiên đã đăng nhập có thể vẫn giữ quyền cũ**. Vì thế phải phân biệt:

1. Dữ liệu tài khoản chuẩn (database/identity provider).
2. `UserDetails` và các cache dùng khi **xác thực**.
3. `Authentication` đã tạo và được lưu/phục hồi qua **session/security context**.
4. Access token tự chứa quyền (ví dụ JWT), nếu ứng dụng cũng có API stateless.
5. Chính sách kiểm tra quyền hoặc khóa tài khoản **tại thời điểm request**.

**Luận điểm cốt lõi:** xóa cache giúp những lần tải dữ liệu và xác thực **sau đó** có thể nhìn thấy trạng thái mới. Nó **không tự thu hồi mọi phiên đăng nhập hoặc access token đã phát hành**.

Sau bài học, bạn có thể lựa chọn khi nào cần cache `UserDetails`, thiết kế invalidation nhất quán cho role/lock/password change, hiểu hệ quả của cache nhiều lớp, và kiểm thử quyền mới cho cả **lần đăng nhập tiếp theo** lẫn **phiên đã đăng nhập**.

## 2. `UserDetailsService`, `UserDetails` và `Authentication` khác nhau ra sao?

Trên Servlet stack với username/password, một luồng thông dụng là:

```text
POST /login hoặc request có HTTP Basic credential
                  |
                  v
        Authentication filter
                  |
          AuthenticationManager
                  |
           DaoAuthenticationProvider
                  |
       UserCache (nếu được cấu hình)
          | miss           | hit
          v                |
   UserDetailsService      |
          |                |
   database/identity store |
          |                |
          +-------+--------+
                  |
        UserDetails + password hash
        + authorities + trạng thái tài khoản
                  |
     xác minh mật khẩu + account status checks
                  |
           Authentication thành công
                  |
           SecurityContextHolder
                  |
     session / request lifecycle (tùy cấu hình)
                  |
           AuthorizationFilter
```

Sơ đồ là **luồng chức năng**, không khẳng định tất cả filter hoạt động y hệt nhau với mọi cơ chế. `DaoAuthenticationProvider` là provider quen thuộc cho `UserDetailsService`; OAuth2, JWT hoặc cơ chế xác thực khác có pipeline riêng.

Phân biệt các đối tượng:

| Đối tượng | Chức năng | Có thể chứa gì? | Thời điểm dễ bị stale |
| --- | --- | --- | --- |
| Tài khoản trong kho dữ liệu chuẩn | Nguồn sự thật | Trạng thái enabled/locked, password hash, role, tenant, version | Khi có bản sao hoặc giao dịch chưa commit |
| `UserDetailsService` | Tải thông tin người dùng theo username | Trả `UserDetails`, có thể dùng repository hoặc cache | Nếu dùng `@Cacheable`, cache riêng hay dữ liệu đọc replica trễ |
| `UserCache` ở provider | Tái sử dụng `UserDetails` giữa các lần xác thực | `UserDetails` đã tải ở lần trước | Sau thay đổi role, khóa tài khoản, đổi password |
| `Authentication` | Kết quả xác thực của một principal | Principal và authorities được snapshot tại lúc xác thực | Khi tài khoản bị sửa sau login |
| `SecurityContext` | Chứa `Authentication` hiện hành | Principal và authorities của request/phiên | Session còn sống và không được tái thẩm định |
| Self-contained token | Chứng nhận trạng thái tại thời điểm phát hành | Claims như `sub`, role, `exp` | Khi claims cũ vẫn hợp lệ đến lúc hết hạn/thu hồi |

Với form login dùng session, Spring Security có thể phục hồi `Authentication` từ session trên request kế tiếp mà **không chạy lại `UserDetailsService`**. Với HTTP Basic, mỗi request thường mang lại credentials và cơ chế xác thực hoạt động theo cấu hình filter/context; việc cache là một quyết định khác. Không nên suy từ "có cache UserDetails" sang "mọi request đều đọc cache".

## 3. Account status và authorities được kiểm tra ở đâu?

`UserDetails` mô tả không chỉ danh tính mà còn trạng thái account:

```java
interface UserDetails {
    String getUsername();
    String getPassword();
    Collection<? extends GrantedAuthority> getAuthorities();

    boolean isEnabled();
    boolean isAccountNonLocked();
    boolean isAccountNonExpired();
    boolean isCredentialsNonExpired();
}
```

Đoạn trên là **chữ ký tối giản để học**, không phải định nghĩa đầy đủ interface của một phiên bản Spring Security cụ thể. Khi `DaoAuthenticationProvider` xác thực username/password, các bước pre/post account checks trong họ `AbstractUserDetailsAuthenticationProvider` có thể từ chối tài khoản không thỏa các cờ này.

| Giá trị | Khi `false` | Ý nghĩa cần nhớ |
| --- | --- | --- |
| `isEnabled()` | Tài khoản bị vô hiệu hóa; thường phát sinh `DisabledException` | Không phải `hasRole`; đây là **trạng thái account** |
| `isAccountNonLocked()` | Tài khoản bị khóa; thường phát sinh `LockedException` | Khóa để chặn lần xác thực mới, chưa chắc chặn session đang tồn tại |
| `isAccountNonExpired()` | Tài khoản hết hạn; thường phát sinh `AccountExpiredException` | Cần chính sách expiry và luồng mở lại cụ thể |
| `isCredentialsNonExpired()` | Credential hết hạn; thường phát sinh `CredentialsExpiredException` | Khác với việc account hết hạn |
| `getAuthorities()` | Danh sách quyền thay đổi | Không đồng nghĩa cờ account bị khóa; quyền được xét tại authorization |

Trong Spring Security, `hasRole("ADMIN")` thường kiểm tra authority `ROLE_ADMIN`; `hasAuthority("ROLE_ADMIN")` so khớp trực tiếp chuỗi authority. Khi sửa quyền, phải đồng bộ **dữ liệu nguồn, cache và authentication/session cần áp dụng quyền mới**. Khi khóa tài khoản, cũng cần quyết định liệu phải thu hồi quyền truy cập của phiên đang hoạt động ngay hay chỉ từ lần đăng nhập mới.

Không đưa flag `locked=true` vào một hệ thống **chỉ** lưu role mà kỳ vọng `DaoAuthenticationProvider` tự biết. Provider cần được `UserDetailsService` trả về `UserDetails` có trạng thái đúng.

## 4. Có những bộ nhớ đệm nào?

### 4.1. `UserCache` ở `DaoAuthenticationProvider`

Họ `AbstractUserDetailsAuthenticationProvider` có khái niệm `UserCache` để lưu và lấy `UserDetails` giữa các lần authentication. Các thao tác quan trọng của interface:

```java
UserDetails getUserFromCache(String username);
void putUserInCache(UserDetails user);
void removeUserFromCache(String username);
```

Đây là **chữ ký tham khảo**; chỉ sử dụng trong code sau khi import đúng `org.springframework.security.core.userdetails.UserCache`. Hai triển khai đáng biết:

- **`NullUserCache`**: không lưu dữ liệu; đây là lựa chọn mặc định của `AbstractUserDetailsAuthenticationProvider` trong cấu hình thông dụng.
- **`SpringCacheBasedUserCache`**: liên kết `UserCache` với abstraction `org.springframework.cache.Cache` để có thể dùng triển khai cache thực tế.

Muốn `DaoAuthenticationProvider` cache `UserDetails`, phải chủ động cấu hình một `UserCache` có lưu trữ. Không khẳng định "Spring Security luôn cache `UserDetails`" chỉ vì thấy `UserDetailsService` trong code.

Đừng nhầm **cache UserDetails của provider** với **cache tại service/repository** hoặc cache của database. Nếu có hai cache độc lập, xóa một cache **không bảo đảm** cache còn lại trả dữ liệu mới.

### 4.2. Cache tại `UserDetailsService`

Một ứng dụng có thể dùng `@Cacheable` hoặc cache thủ công:

```java
// Fragment minh họa trong một Spring bean.
@Cacheable(cacheNames = "accountDetails", key = "#username")
public UserDetails loadUserByUsername(String username) {
    return accountRepository.findByUsername(username)
        .map(this::toUserDetails)
        .orElseThrow(() -> new UsernameNotFoundException("Not found"));
}
```

Cần repository, cấu hình caching (`@EnableCaching` và `CacheManager` hoặc cơ chế tương đương) và bean được gọi qua Spring proxy. Đây **không phải chương trình độc lập**. Với Spring AOP cache, tự gọi method `@Cacheable` từ một method khác trong **cùng bean** có thể không đi qua proxy nên không áp dụng cache như bạn nghĩ.

Đặc biệt, username nên được **chuẩn hóa nhất quán** trước khi làm cache key nếu chính sách account không phân biệt hoa/thường. Ứng dụng đa tenant phải đưa **tenant identity** vào key; nếu chỉ cache theo username `"admin"` nhưng hai tenant đều có user này, có nguy cơ trả nhầm `UserDetails` của tenant khác.

### 4.3. Cache phía identity provider hoặc persistence

LDAP, distributed cache, DB second-level cache hoặc một service trung gian có thể có độ trễ đồng bộ riêng. Nếu nhiều lớp cùng lưu user, hãy vẽ được từng lớp, key, TTL, chủ sở hữu và sự kiện invalidate. Một `removeUserFromCache(username)` ở JVM A không tự động làm dữ liệu mới xuất hiện trong JVM B nếu dùng cache local độc lập.

## 5. Vì sao cache sai gây ra sự cố thực tế?

Giả sử thông tin trong database thay đổi:

```text
t0: alice, ROLE_ADMIN, enabled=true, accountNonLocked=true
t1: Alice đăng nhập thành công; UserDetails có ROLE_ADMIN.
t2: Admin tước ROLE_ADMIN ở database.
t3: Alice đăng nhập lại, provider lấy UserDetails cũ từ cache.
t4: Alice vẫn được xem có ROLE_ADMIN nếu stale data được dùng.
```

Hoặc một tình huống tương tự:

```text
t0: bob, accountNonLocked=true
t1: Bob đăng nhập và có phiên HTTP session đang hoạt động.
t2: Hệ thống khóa bob, accountNonLocked=false.
t3: UserDetails cache không bị xóa -> lần xác thực mới có thể đọc cờ cũ.
t4: Dù đã xóa cache, session từ t1 vẫn có thể còn Authentication hợp lệ.
```

Bởi vậy, cần hỏi **hai câu độc lập**:

1. *Các lần xác thực mới có nhận được dữ liệu cập nhật không?* → Đảm bảo source-of-truth commit và invalidate/tải lại `UserDetails` đúng.
2. *Các phiên/token đã phát hành có bị áp dụng chính sách mới không?* → Thiết kế thu hồi session, token, kiểm tra lại account state hoặc policy authorization tại request.

Nếu yêu cầu an toàn là "thu hồi quyền admin tối đa sau N giây", chỉ thêm `@CacheEvict` và hy vọng request hiện tại sẽ tự đổi authority là **chưa đủ**.

## 6. Cache, thay đổi role và khóa account: ma trận hiệu lực

| Hành động | UserDetails cache cần xử lý? | Authentication trong session cũ? | Token tự chứa claims? |
| --- | --- | --- | --- |
| Thêm quyền `ROLE_REPORTER` | Xóa/tải mới để login sau nhận quyền | Quyền mới thường **chưa có** tới khi refresh/re-auth | Claim cũ không có quyền mới |
| Tước `ROLE_ADMIN` | Xóa ngay theo policy | Có thể **vẫn giữ quyền admin cũ** nếu không tái thẩm định | Role claim cũ vẫn có thể dùng đến khi hết hạn/thu hồi |
| Đặt `accountNonLocked=false` | Xóa, để lần auth mới bị pre-check từ chối | Phiên cũ **không tự bị khóa** | Access token hiện hữu thường không tự biến mất |
| Đặt `enabled=false` | Xóa/tải lại | Phải quyết định và triển khai revoke/check khi request | Cần revocation, introspection, short TTL hoặc version check |
| Thay password hash | Xóa để login mới kiểm tra hash mới | Phiên cũ có thể vẫn hợp lệ nếu không thu hồi | Token cũ có thể vẫn hợp lệ |
| Xóa account | Xóa cả cache và dữ liệu phụ thuộc | Có thể cần invalidation session/remember-me | Cần chính sách token revocation |
| Thay metadata UI không ảnh hưởng quyền | Tùy dữ liệu nào được cache | Không nhất thiết thu hồi phiên | Không nhất thiết ảnh hưởng token |

Một triển khai tốt phải định nghĩa **mục tiêu nhất quán** trước khi chọn giải pháp. Với thông tin hiển thị ít nhạy cảm có thể chấp nhận TTL ngắn; với khóa vì bị chiếm đoạt tài khoản hoặc thu hồi quyền đặc biệt, cần độ trễ hiệu lực đã được đo và kiểm thử chặt hơn.

## 7. Thiết kế invalidation: sau commit, mọi node, đúng khóa

Quy trình cập nhật tài khoản thường gồm:

```text
Admin hoặc policy engine yêu cầu thay đổi
                |
        Kiểm tra quyền thực hiện thay đổi
                |
        Transaction thay đổi account/roles
                |
        Commit thành công ở database
                |
        Invalidate các cache UserDetails liên quan
                |
        Phát sự kiện tới mọi instance (nếu cache local)
                |
        Thực hiện chiến lược revoke/refresh session và token
                |
        Ghi audit event, theo dõi độ trễ hiệu lực
```

Các quy tắc nền tảng:

1. **Invalidate bằng đúng cache key**: username đã chuẩn hóa, tenant và những khóa phụ liên quan. Nếu lookup theo email/ID cũng được cache thì thay đổi username/email phải xóa cả các key tương ứng.
2. **Đặt invalidation sau giao dịch commit thành công**: nếu xóa cache trước commit, một request đồng thời có thể nạp lại bản cũ, rồi commit mới hoàn tất và cache giữ bản cũ. Khi dùng Spring transaction, có thể kích hoạt invalidate sau commit hoặc qua sự kiện/outbox nhất quán.
3. **Đảm bảo multi-node**: một `ConcurrentMapCache` trong instance A không tự cập nhật B. Dùng Redis/distributed cache hoặc thông điệp invalidation đáng tin; cân nhắc duplicate, retry và mất thông điệp.
4. **TTL không thay cho invalidation có chủ đích**: TTL là lớp giới hạn thời gian stale trong điều kiện bình thường, không phải cam kết thu hồi tức thì. Với dữ liệu rủi ro cao, cần read-through/revalidate hoặc cơ chế version.
5. **Tránh cache poisoning**: chỉ đưa `UserDetails` được trả về từ nguồn dữ liệu đáng tin cậy vào cache. Không nhận `roles`, `enabled` hoặc `locked` từ request và ghi chúng như trạng thái đã xác minh.
6. **Không cache password plaintext**: nếu cache password hash, bảo vệ cache như dữ liệu nhạy cảm, hạn chế quyền truy cập/log, encrypt transport khi dùng cache ngoài tiến trình.
7. **Thận trọng với cache objects có thể bị sửa**: nhiều implementation `UserDetails` đồng thời là `CredentialsContainer`; có thể bị xóa credentials sau authentication bởi `ProviderManager`. Cache cùng một instance mutable và trả lại nó làm principal có thể dẫn đến cached password rỗng. Dùng immutable value/copy hợp lý hoặc thiết kế cache đúng contract; đừng tắt credential erasure một cách máy móc mà chưa đánh giá bảo mật.
8. **Tránh negative caching kéo dài**: lưu kết quả "không tồn tại" lâu có thể cản trở người dùng mới hoặc khóa nhầm khi tạo account; message login cũng không được tiết lộ tài khoản có tồn tại hay không.

**Đừng giả định cache invalidation và database commit là một thao tác nguyên tử.** Trong hệ thống phân tán, nếu cần bảo đảm nghiêm ngặt, hãy thiết kế version check tại điểm quyết định bảo mật hoặc chặn request trong khoảng chuyển trạng thái theo chính sách cụ thể.

## 8. Java 17+ thuần: minh họa vì sao phải invalidate cache

Trước khi cấu hình Spring, ta có thể chạy một ví dụ Java đơn giản để thấy stale data. Đây là chương trình **độc lập, chạy được bằng `javac`/`java`**, mô phỏng bản sao thông tin account; nó **không phải implementation thực của `UserDetails`**.

Tạo tệp `AccountCacheDemo.java`:

```java
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class AccountCacheDemo {
    record Account(Set<String> roles, boolean locked) {
        Account {
            roles = Set.copyOf(roles);
        }
    }

    public static void main(String[] args) {
        Map<String, Account> database = new ConcurrentHashMap<>();
        Map<String, Account> cache = new ConcurrentHashMap<>();

        database.put("alice", new Account(Set.of("ADMIN"), false));

        Account before = cache.computeIfAbsent("alice", database::get);
        System.out.println("before: " + before.roles().contains("ADMIN")
            + ", locked=" + before.locked());

        database.put("alice", new Account(Set.of("USER"), true));

        Account stale = cache.computeIfAbsent("alice", database::get);
        System.out.println("stale: " + stale.roles().contains("ADMIN")
            + ", locked=" + stale.locked());

        cache.remove("alice");

        Account fresh = cache.computeIfAbsent("alice", database::get);
        System.out.println("fresh: " + fresh.roles().contains("ADMIN")
            + ", locked=" + fresh.locked());
    }
}
```

Lệnh chạy:

```bash
javac AccountCacheDemo.java
java AccountCacheDemo
```

**Stdout chính xác** của ví dụ trên:

```text
before: true, locked=false
stale: true, locked=false
fresh: false, locked=true
```

Bài tập mô phỏng cho thấy thay database không làm đối tượng `Account` đã nằm trong map cache tự thay đổi. Trong Spring Security, `UserDetails` cũng chỉ là dữ liệu được tải theo một thời điểm, vì thế **phải gắn thao tác ghi với invalidation hoặc cơ chế version phù hợp**. Chương trình này không mô phỏng session hoặc JWT; đó là một lớp vấn đề khác.

## 9. Spring Boot 3.x / Spring Security 6.x: ví dụ cache UserDetails và xóa khi cập nhật

Ví dụ sau minh họa `DaoAuthenticationProvider` với `SpringCacheBasedUserCache`. Nó dùng một "repository" bằng `ConcurrentHashMap` cho dễ chạy, **không thay thế database trong production**. Các `UserDetails` được tạo bằng một `record` immutable để không chia sẻ một đối tượng mutable giữa cache và principal.

Trong dự án Spring Boot 3.x có Gradle plugin và dependency management, thêm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Tạo tệp `src/main/java/example/accountcache/AccountCacheApplication.java`:

```java
package example.accountcache;

import java.util.Map;
import java.util.Set;
import java.util.Collection;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.UnaryOperator;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserCache;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.core.userdetails.cache.SpringCacheBasedUserCache;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AccountCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccountCacheApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserCache userCache() {
        // Cache local chỉ để minh họa, không đồng bộ nhiều application nodes.
        return new SpringCacheBasedUserCache(
            new ConcurrentMapCache("userDetails"));
    }

    @Bean
    AuthenticationManager authenticationManager(
            AccountDirectory directory,
            PasswordEncoder encoder,
            UserCache userCache) {

        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(directory);
        provider.setPasswordEncoder(encoder);
        provider.setUserCache(userCache);

        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain chain(
            HttpSecurity http,
            AuthenticationManager authenticationManager) throws Exception {

        return http
            .authenticationManager(authenticationManager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}

@Service
class AccountDirectory implements UserDetailsService {

    private final Map<String, AccountRecord> accounts =
        new ConcurrentHashMap<>();
    private final UserCache cache;

    AccountDirectory(PasswordEncoder encoder, UserCache cache) {
        this.cache = cache;
        accounts.put("learner", new AccountRecord(
            "learner", encoder.encode("demo-pass"),
            true, true, Set.of(new SimpleGrantedAuthority("ROLE_USER"))
        ));
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        AccountRecord user = accounts.get(username);
        if (user == null) {
            throw new UsernameNotFoundException("User not found");
        }
        return user;
    }

    void grantAdmin(String username) {
        update(username, old -> new AccountRecord(
            old.username(), old.password(),
            old.enabled(), old.accountNonLocked(),
            Set.of(new SimpleGrantedAuthority("ROLE_USER"),
                   new SimpleGrantedAuthority("ROLE_ADMIN"))
        ));
    }

    void lock(String username) {
        update(username, old -> new AccountRecord(
            old.username(), old.password(),
            old.enabled(), false, old.authorities()
        ));
    }

    private void update(String username,
                        UnaryOperator<AccountRecord> change) {
        AccountRecord updated =
            accounts.computeIfPresent(username, (key, old) -> change.apply(old));

        if (updated == null) {
            throw new UsernameNotFoundException("User not found");
        }

        // Quan trọng: evict đúng key sau khi nguồn dữ liệu đã cập nhật.
        cache.removeUserFromCache(username);
    }

    record AccountRecord(
            String username,
            String password,
            boolean enabled,
            boolean accountNonLocked,
            Set<GrantedAuthority> authorities
    ) implements UserDetails {

        AccountRecord {
            authorities = Set.copyOf(authorities);
        }

        @Override
        public String getUsername() { return username; }

        @Override
        public String getPassword() { return password; }

        @Override
        public Collection<? extends GrantedAuthority> getAuthorities() {
            return authorities;
        }

        @Override
        public boolean isEnabled() { return enabled; }

        @Override
        public boolean isAccountNonLocked() {
            return accountNonLocked;
        }

        @Override
        public boolean isAccountNonExpired() { return true; }

        @Override
        public boolean isCredentialsNonExpired() { return true; }
    }
}

@RestController
class AccountController {

    @GetMapping("/me")
    String me(Authentication authentication) {
        return "hello " + authentication.getName();
    }

    @GetMapping("/admin")
    String admin() {
        return "admin area";
    }
}
```

### Phân tích code

- `AccountDirectory` là `UserDetailsService`. Ở production, `loadUserByUsername` đọc repository/database, tạo snapshot authorities và status từ các bản ghi đã được commit.
- `SpringCacheBasedUserCache` được cắm trực tiếp vào `DaoAuthenticationProvider`. Mỗi lần cache miss, provider có thể gọi `loadUserByUsername`; sau khi authenticate thành công, thông tin account có thể được giữ cho lần sau.
- `DaoAuthenticationProvider` kiểm tra **password hash** với `PasswordEncoder`, sau đó kiểm tra account status; khi `accountNonLocked=false`, lần xác thực mới phải bị từ chối.
- `AccountRecord` immutable, không triển khai `CredentialsContainer`. Điều này tránh tình huống password hash trong cùng instance cached principal bị xóa trong cơ chế credential erasure sau authentication. Với đối tượng mutable khác, phải thiết kế copy/cache phù hợp.
- `grantAdmin` và `lock` là các method package-private **chỉ để test**. Không mở endpoint public cho client tùy ý gọi hai method này. Muốn thao tác quản trị thật, phải kiểm tra quyền và audit; update phải nằm trong transaction và invalidation xảy ra đúng thời điểm.
- `accounts.computeIfPresent` bảo vệ một bước thay đổi map trong **một JVM**, không tạo transaction giữa DB, cache và session. Một thiết kế phân tán phải giải quyết race, distributed invalidation và session revocation riêng.
- Demo dùng `HTTP Basic` ở local để quan sát **mỗi lần cung cấp credentials**. Với browser/production phải dùng HTTPS và đánh giá CSRF/session/threat model theo cơ chế thực tế; không dùng mật khẩu demo ở production.
- Cấu hình chỉ cho GET `/me` hoặc `/admin`, các endpoint khác đều `denyAll`. Không mở API ghi trực tiếp để người ngoài thao tác quyền.

### Chạy và quan sát

Tại root dự án đã có Gradle wrapper, chạy:

```bash
./gradlew bootRun
```

Windows PowerShell: `./gradlew.bat bootRun`.

Ở trạng thái khởi tạo, `learner` có `ROLE_USER`, không bị khóa:

```bash
curl -i -u learner:demo-pass http://localhost:8080/me
curl -i -u learner:demo-pass http://localhost:8080/admin
```

Kết quả **dự kiến**: GET `/me` → 200 với body `hello learner`; GET `/admin` → **403** do thiếu `ROLE_ADMIN`. Khi code test thay đổi dữ liệu nguồn và invalidate cache, request mới có thể nhận `ROLE_ADMIN`; khi tiếp tục lock, lần cung cấp Basic credentials mới bị từ chối.

Vì `grantAdmin` và `lock` không phải HTTP endpoints, hãy chạy test dưới đây để thực hiện chuỗi thay đổi; không thử gọi `POST /admin/grant` vì demo **không có route đó**.

## 10. Kiểm thử bằng MockMvc: thêm role rồi khóa tài khoản

Thêm test dependencies:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Tạo `src/test/java/example/accountcache/AccountCacheSecurityTest.java`:

```java
package example.accountcache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccountCacheSecurityTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    AccountDirectory accounts;

    @Test
    void changesAreVisibleToNewAuthenticationAfterCacheEviction()
            throws Exception {

        // Auth thành công nhưng chưa có ROLE_ADMIN.
        mvc.perform(get("/admin")
                .with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isForbidden());

        // Thay roles tại nguồn dữ liệu, xóa UserDetails cache.
        accounts.grantAdmin("learner");

        // Lần xác thực mới phải nhìn thấy quyền admin.
        mvc.perform(get("/admin")
                .with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin area"));

        // Khóa tài khoản và xóa UserDetails cache lần nữa.
        accounts.lock("learner");

        // Lần xác thực mới với HTTP Basic bị từ chối.
        mvc.perform(get("/me")
                .with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isUnauthorized());
    }
}
```

Lệnh chạy:

```bash
./gradlew test
```

Các assertion và status phía trên là **kết quả dự kiến**, chưa được thực thi trong tài liệu. Bài test đơn kiểm tra quyền trước/sau `grantAdmin`, rồi xác nhận khóa account chặn một lần xác thực mới. Nó **không chứng minh** session đang tồn tại bị thu hồi, cũng không kiểm chứng distributed cache hoặc JWT.

Một test bổ sung rất nên có cho production là cố ý **bỏ invalidation** trong một fixture riêng, chứng minh trạng thái cũ có thể tiếp tục được trả từ cache; sau đó bật invalidation để xác định lỗi đã được khắc phục. Tránh thực hiện "bài test gây lỗi" này trên môi trường sử dụng chung hoặc ghi đè cấu hình production.

## 11. Phân biệt cache UserDetails với phiên đã đăng nhập

Khi sử dụng form login có session, sau đăng nhập `SecurityContext` được lưu theo chính sách repository/session. `Authentication.getAuthorities()` của phiên đó thường là **snapshot** tại thời điểm authentication:

```text
t0: UserDetails = ROLE_ADMIN
    -> form login tạo Authentication(ROLE_ADMIN)
    -> session S giữ Authentication này

t1: Database bị đổi thành ROLE_USER
    -> invalidate UserDetails cache

t2: Browser gửi cookie session S, không đăng nhập lại
    -> SecurityContext phục hồi Authentication(ROLE_ADMIN)
    -> role có thể vẫn là ROLE_ADMIN
```

Vì vậy, **tước quyền có tác động ngay** cần một chính sách cho active sessions. Tùy yêu cầu:

- **Buộc đăng nhập lại**: thu hồi/expire sessions của người dùng, khiến request tiếp theo không còn authentication đã lưu. Tài khoản bị khóa sẽ không qua được lần login tiếp theo khi account state được tải mới.
- **Tái tải authorities**: tại request quan trọng hoặc trong một authorization strategy chuyên dụng, so khớp với nguồn quyền đủ mới. Tránh đọc database ở mọi URL vô tội vạ; có thể dùng version, cache ngắn TTL, policy engine hoặc cơ chế event push.
- **Phân tách quyền dài hạn và quyền tài nguyên**: `hasRole("ADMIN")` chỉ là coarse-grained role; các điều kiện ownership, tenant, approval cần kiểm tra ở domain/service theo dữ liệu hiện hành.
- **Dùng `SessionRegistry` hoặc session store**: hỗ trợ tìm session và đánh dấu hết hạn/invalidate trong các kiến trúc phù hợp; nhưng chi tiết phụ thuộc session tracking và cluster setup.

`SessionInformation.expireNow()` trong mô hình session concurrency không phải là thao tác xóa mọi cookie/token ngay lập tức. Nó đánh dấu session để cơ chế liên quan xử lý khi request tiếp theo đi qua các filter/session registry phù hợp. Với multi-node, muốn revoke đáng tin cần shared session store hoặc cơ chế đồng bộ phù hợp. Không gọi một method của `SessionRegistry` rồi kết luận mọi phiên/tất cả token đã mất hiệu lực.

### Session revocation là chính sách chứ không phải tác dụng phụ

Nên quyết định cụ thể cho từng loại thay đổi:

| Thay đổi | Phương án phiên đã đăng nhập |
| --- | --- |
| Tước quyền admin | Thu hồi phiên hoặc bắt đánh giá lại quyền trước các thao tác admin; có thể cần revoke ngay |
| Khóa do nghi ngờ chiếm đoạt | Thu hồi mọi session phù hợp, vô hiệu hóa remember-me và token, chặn credential mới |
| Đổi mật khẩu theo yêu cầu người dùng | Tùy sản phẩm: giữ phiên hiện tại nhưng thu hồi phiên khác, hoặc thu hồi tất cả |
| Thêm quyền thông thường | Có thể yêu cầu login lại hoặc refresh authorities; không tự cấp role khi chưa re-evaluate |
| Vô hiệu hóa account | Chặn cả lần đăng nhập mới và quyền truy cập của phiên còn hiệu lực theo SLA |
| Đổi tên hiển thị | Không nhất thiết cần thu hồi session nếu quyền không đổi |

**Lưu ý:** "logout" của browser chỉ xóa/vô hiệu phiên theo cơ chế logout được cấu hình và thường tác động lên một phiên hiện tại. Không mặc định logout một browser đồng nghĩa thu hồi tất cả sessions trên mọi thiết bị.

## 12. Stateless token và JWT: cache UserDetails không phải nơi kiểm soát duy nhất

Trong API dùng OAuth2 Resource Server với JWT, request có thể được xác thực bằng việc kiểm tra chữ ký, issuer, audience, `exp` và chuyển đổi claims thành authorities. Nếu hệ thống **không dùng `UserDetailsService`** cho luồng bearer này, thao tác `UserCache.removeUserFromCache(username)` không liên quan đến việc JWT đang lưu `ROLE_ADMIN`.

Ví dụ:

```text
12:00 JWT phát hành: sub=alice, roles=[ADMIN], exp=12:15
12:02 database: roles=[USER]
12:03 xóa mọi UserDetails cache
12:04 JWT cũ vẫn có thể được chấp nhận và có claim ADMIN
      nếu hệ thống chỉ kiểm tra chữ ký và thời hạn.
```

Cách giảm độ trễ thu hồi tùy kiến trúc:

1. **Access token ngắn hạn** kết hợp refresh token rotation và chính sách thu hồi refresh token; giới hạn khoảng tồn tại của claims cũ, không phải thu hồi tức thì.
2. **Opaque token + introspection** hoặc kiểm tra central token/session state để ra quyết định theo trạng thái mới; đánh đổi network latency/availability.
3. **Token revocation list** theo `jti`/session ID, có TTL theo exp; phải thiết kế đủ nhanh và đồng nhất qua các instance.
4. **Account/permission version**: token chứa `version`, phía resource server kiểm tra version hiện hành (hoặc version cache có invalidation và SLA đã được xác định). Bản thân version **không có tác dụng** nếu resource server không kiểm tra.
5. **Policy check tại request** cho hành động nhạy cảm; tách việc xác thực token khỏi việc cho phép thao tác cụ thể.

Tránh một câu trả lời cứng nhắc "chỉ giảm JWT TTL là đủ" nếu yêu cầu là khóa tài khoản ngay, hoặc "dùng blacklist" mà không tính được quy mô, độ trễ đọc và cơ chế fail-closed khi dependency lỗi.

## 13. Multi-instance, concurrent updates và ranh giới giao dịch

Trong một máy local, `cache.removeUserFromCache(username)` ngay sau `accounts.put` có thể đủ để minh họa. Production thường có nhiều instance:

```text
Node A (request cập nhật):
  DB COMMIT account.locked = true
  evict cache trên A
  publish AccountChanged(accountId, version=13)

Message bus / distributed cache invalidation
  -> node B evict
  -> node C evict

Trong lúc đó:
  active sessions/tokens được xử lý theo policy revoke/refresh
```

Các rủi ro phải thiết kế:

- **Race "read cũ rồi ghi lại cache"**: request B đọc bản cũ từ replica hoặc transaction chưa commit, sau đó populate cache **sau** lệnh invalidate. Có thể cần version check, đọc nguồn có tính nhất quán phù hợp, hoặc cache entry có revision.
- **Message delivery at-least-once**: event invalidation có thể đến lặp lại; `evict` cần idempotent. Nếu mất message, TTL ngắn và reconcile/scan giúp giảm rủi ro nhưng không bảo đảm tức thời.
- **Event sai thứ tự**: event version 12 có thể đến sau version 13. Tránh cho phép một event cũ ghi đè trạng thái mới.
- **Partial failure**: database commit thành công nhưng message bus lỗi. Nếu yêu cầu nghiêm ngặt, cân nhắc transactional outbox và retry; đo tỷ lệ event chưa được xử lý.
- **Cache key theo tenant**: cùng username thuộc nhiều tenant không được trùng key. Nếu provider `UserCache` chỉ key theo username, thiết kế namespace hoặc provider isolation sao cho không trộn dữ liệu.
- **Account-status check nằm trong authentication pipeline**: đọc cache đúng sau thay đổi bảo vệ **lần authentication mới**. Muốn bảo vệ active session thì phải có bước kiểm tra bổ sung.

Độ trễ "quyền đổi trong database → không còn request nào dùng quyền cũ" phải được đo bằng test trên các node, không chỉ bằng việc thấy log `evicted userDetails`.

## 14. Quy trình thay đổi trạng thái tài khoản an toàn

### Tước quyền hoặc đổi vai trò

1. Xác thực và phân quyền **người ra lệnh thay đổi**; có audit và kiểm tra tenant/ownership.
2. Cập nhật role/authority trong transaction.
3. Sau commit, invalidate cache đúng account/tenant trên tất cả nơi dùng `UserDetails`.
4. Quyết định **session policy**: expire sessions, tái nạp authorities hoặc kiểm tra policy tại request.
5. Với JWT/opaque token, thực hiện token revocation/version check theo SLA.
6. Đo: trong tối đa bao lâu endpoint từng được `ROLE_ADMIN` cho phép phải bắt đầu trả 403/401? Viết test tương ứng.

### Khóa hoặc vô hiệu hóa tài khoản

1. Ghi `locked=true` hoặc `enabled=false` trong nguồn sự thật với lý do và thời điểm.
2. Invalidate mọi cache chứa status/credentials.
3. Chặn lần xác thực tiếp theo thông qua `UserDetails` mới và provider checks.
4. Thu hồi/expire active sessions, remember-me và refresh tokens nếu policy yêu cầu "khóa ngay".
5. Đối với token self-contained còn sống, dùng một trong các cơ chế revocation hoặc request-time checks.
6. Ghi audit mà không lộ mật khẩu/token; xác nhận UI, API và các node cùng thực thi chính sách.

### Đổi mật khẩu

1. Xác minh quyền đổi mật khẩu hoặc reset token hợp lệ; lưu password hash đúng encoder.
2. Commit hash mới và invalidate cache UserDetails.
3. Quyết định thu hồi các phiên khác và token dựa vào threat model.
4. Kiểm thử password cũ bị từ chối ở lần xác thực mới, password mới được chấp nhận; tránh thông báo có tính xác nhận username tồn tại.
5. Cân nhắc remember-me persistent tokens phải được quản lý/thu hồi riêng, không chỉ qua UserCache.

## 15. Các kiểm thử cần có trước khi triển khai

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Lần authentication đầu và lần sau | Cache hit/miss theo thiết kế, không để lộ hash/token trong log |
| Tước quyền tại DB sau khi cache đã warm | New login/auth nhận authorities đã cập nhật, không nhận stale role |
| Lock/disable tài khoản khi cache đã warm | New auth nhận `LockedException`/`DisabledException` hoặc response thích hợp, không đi vào tài nguyên |
| Đổi password khi cache đã warm | Password cũ bị từ chối sau thay đổi; password mới được chấp nhận |
| Session đã đăng nhập trước khi tước quyền | Phù hợp SLA revoke/refresh và không còn thao tác admin ngoài dự kiến |
| Multi-node A/B với cache local | Invalidation tới B; không còn cửa sổ stale lớn hơn SLA |
| Transaction rollback hoặc publish event lỗi | Không invalidate sớm rồi nạp dữ liệu cũ; retry/reconcile có hiệu lực |
| Username có tenant hoặc case normalization | Không trả UserDetails của tenant/account khác |
| Thao tác khóa account đồng thời với request | Phân tích race, version và policy cho những request đang chạy |
| Remember-me/JWT/access token | Biện pháp revoke riêng được áp dụng, không phụ thuộc xóa UserDetails cache |
| Admin grant/revoke nhiều role | Authorization không dùng snapshot cũ quá thời hạn cho phép |
| Authentication error reporting | Không tiết lộ rõ user tồn tại hay bị khóa cho người ngoài nếu không được phép |
| Stress test cache | Giới hạn số entry, TTL, stale ratio, DB load; hiệu năng không phá mục tiêu bảo mật |

Dùng integration test cho authentication/authorization; test độc lập cho repository/cache; và end-to-end test thực sự chạy qua nhiều service instance nếu hệ thống phân tán. Với Spring Security, mã HTTP của một lỗi auth còn phụ thuộc entry point và access-denied handler: không biến 401/403 thành kết luận tuyệt đối nếu response đã được tùy biến.

## 16. Các nhầm lẫn hay gặp

### "Spring Security tự cache UserDetails mặc định"

Không nên giả định như vậy. `AbstractUserDetailsAuthenticationProvider` thường dùng `NullUserCache` trừ khi bạn cấu hình cache. Nếu thấy DB không bị gọi mỗi request, nguyên nhân có thể là **session chứa Authentication**, không phải provider UserCache đang có hit.

### "Evict UserDetails thì session cũ lập tức mất quyền"

Sai. `SecurityContext` đã lưu chứa `Authentication` với authorities riêng. Cần revoke session hoặc kiểm tra lại quyền để hiệu lực theo chính sách.

### "Khóa tài khoản là đủ để mọi access token mất hiệu lực"

Sai với nhiều hệ thống JWT stateless. Token đã ký và chưa hết hạn có thể còn được chấp nhận cho đến khi policy revocation hoặc version check có hiệu lực.

### "TTL 5 phút đảm bảo khóa ngay"

TTL chỉ giới hạn tuổi thọ entry trong cache (tùy implementation). Nó không bảo đảm chính sách khóa trong giây đầu tiên, chưa kể session cũ. Đối với nghiệp vụ rủi ro, phải có SLA và biện pháp áp dụng phù hợp.

### "Đăng nhập thành công nghĩa là quyền được cập nhật cho mọi request"

Không đúng. `Authentication` thường giữ các authorities được tải tại **lần auth đó**. Quyền mới/thay đổi chỉ được nhìn thấy khi cơ chế tương ứng refresh hoặc revalidate.

### "Chỉ gọi `removeUserFromCache` ở node xử lý lệnh là đủ"

Không đủ khi các node dùng local cache độc lập. Phải đồng bộ invalidation hoặc sử dụng cache chia sẻ có cơ chế nhất quán theo thiết kế.

### "Có thể tắt `eraseCredentialsAfterAuthentication` cho cache chạy"

Đó có thể là một workaround trong một số cấu hình nhưng làm tăng thời gian tồn tại của thông tin credential trong object. Ưu tiên mô hình cache hợp đồng rõ, immutable/copy phù hợp và cân nhắc cẩn thận bảo mật; không vô hiệu hóa credential cleanup chỉ để che một lỗi thiết kế.

### "Lỗi stale là lỗi phân quyền URL"

Không nhất thiết. URL policy `hasRole` có thể hoàn toàn đúng, nhưng `Authentication` hoặc `UserDetails` chứa authorities cũ. Khi debug, kiểm tra **nguồn role**, **trạng thái cache**, **Authentication hiện tại**, **session/token** và **authorization rule** theo thứ tự.

## 17. Bài tập kiểm tra hiểu bài

**Câu 1.** `DaoAuthenticationProvider` dùng `SpringCacheBasedUserCache` với TTL 10 phút. User được khóa ngay sau khi đã login. Tại sao một request dùng cookie session cũ có thể vẫn vào được `/me`?

**Đáp án:** Session có thể phục hồi `Authentication` đã tạo trước khi khóa mà không tải lại `UserDetails`. TTL hoặc evict chỉ tác động tới lớp user-details cache, không tự hủy session.

**Câu 2.** Quản trị viên tước `ROLE_ADMIN`, commit database thành công và gọi `removeUserFromCache("alice")` ở node A. Node B có một local cache khác. Cần làm gì?

**Đáp án:** Phải invalidate cache ở B (qua event/distributed cache/version), đồng thời xử lý active sessions/tokens và kiểm thử độ trễ revoke theo SLA.

**Câu 3.** Một developer đặt `@Cacheable("users")` trên `loadUserByUsername` và `UserCache` ở `DaoAuthenticationProvider`. Khi role thay đổi, chỉ xóa provider cache có đủ không?

**Đáp án:** Chưa chắc. Lần cache miss ở provider có thể lấy tiếp `UserDetails` cũ từ cache ở service. Cần định nghĩa một chủ sở hữu cache hoặc invalidate mọi lớp liên quan.

**Câu 4.** Khi account bị khóa, `UserDetails.isAccountNonLocked()` nên trả giá trị nào? Thay đổi đó tác động trực tiếp nhất vào lúc nào?

**Đáp án:** Trả `false`. Provider account-status checks sẽ từ chối lần username/password authentication mới khi nhận được `UserDetails` cập nhật. Active sessions có chính sách xử lý riêng.

**Câu 5.** Có thể dùng `Authentication.getAuthorities()` của session làm "nguồn sự thật" cho quyền sau khi admin đã sửa roles không?

**Đáp án:** Không nếu nghiệp vụ yêu cầu quyền cập nhật tức thời: session có thể chứa snapshot cũ. Cần refresh/revoke hoặc đánh giá lại quyền từ nguồn policy đủ mới.

**Câu 6.** Trong ứng dụng đa tenant, cả tenant A và B đều có username `"supervisor"`. Cache key là username trần. Lỗi có thể xảy ra?

**Đáp án:** Hai bản ghi có thể dùng chung key, dẫn tới nhầm UserDetails và roles giữa các tenant. Key và domain of trust phải chứa tenant context đáng tin cậy; không lấy tenant ID do client tự khai mà không kiểm tra.

**Câu 7.** JWT cũ chứa claim `roles=["ADMIN"]` và còn hạn 15 phút. Xóa `UserDetails` cache có vô hiệu hóa JWT không?

**Đáp án:** Không, nếu resource server chỉ xác minh chữ ký/hạn và đọc role claim mà không tra lại trạng thái tài khoản. Cần chiến lược token revocation/version/short TTL phù hợp SLA.

## 18. Checklist thiết kế trước khi bật cache

- [ ] Xác định chính xác **cache layer** nào lưu `UserDetails` và ai là chủ sở hữu invalidation.
- [ ] Có `enabled`, `accountNonLocked`, `accountNonExpired`, `credentialsNonExpired` và authorities được tải từ nguồn đáng tin.
- [ ] Cache key được chuẩn hóa, có tenant namespace khi cần; không có cross-tenant collision.
- [ ] Cache không lưu plaintext credential, không log password hash hoặc `Authentication` toàn bộ.
- [ ] Sau commit đổi role/lock/password, cache liên quan bị invalidate đúng account.
- [ ] Multi-node/distributed invalidation và trường hợp mất event/rollback đã được kiểm thử.
- [ ] Có chiến lược rõ cho **active sessions** khi quyền bị tước hoặc account bị khóa.
- [ ] Có chiến lược riêng cho JWT, remember-me và refresh token.
- [ ] SLA revoke được đo, không chỉ tuyên bố "TTL ngắn là đủ".
- [ ] Integration test mô tả được before/after trên authentication mới và phiên cũ.

## Kết luận

Bộ nhớ đệm `UserDetails` cải thiện hiệu năng khi nhiều lần xác thực phải tải cùng account. Nhưng **stale roles, stale lock flags và stale password hash** là rủi ro bảo mật thật. `UserCache.removeUserFromCache(username)`, service cache invalidation, đồng bộ nhiều node và giao dịch sau commit giúp **lần xác thực mới** nhìn thấy dữ liệu đúng.

Để thay đổi quyền hoặc khóa tài khoản có hiệu lực với **phiên đang hoạt động**, cần thêm revoke/refresh session, token policy và/hoặc kiểm tra lại quyền tại request theo yêu cầu nghiệp vụ. Nắm rõ ranh giới giữa **UserDetails**, **Authentication**, **SecurityContext** và **token** là điều kiện để thiết kế đúng thay vì chỉ bật một annotation cache rồi coi như hoàn thành.
