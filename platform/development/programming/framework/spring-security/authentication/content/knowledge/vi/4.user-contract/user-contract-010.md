# Bộ nhớ đệm UserDetails và việc làm mới dữ liệu sau thay đổi tài khoản

> **Ngữ cảnh:** Spring Security — authentication, nhóm **Hợp đồng người dùng**. Bài này tập trung vào việc `UserDetails` có thể được cache trong quá trình xác thực username/password, dữ liệu nào trở nên cũ sau khi đổi tài khoản, cách chủ động làm mới/loại bỏ cache và vì sao xóa cache **không đồng nghĩa** thu hồi session hoặc access token đã phát hành. Ví dụ chạy độc lập dùng Java 17, Spring Security 6.3.x và Gradle.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt `UserDetails`, `UserDetailsService`, `UserCache`, `CachingUserDetailsService`, `Authentication`, `SecurityContext` và token/phiên đăng nhập.
2. Mô tả chính xác cách `DaoAuthenticationProvider` và `AbstractUserDetailsAuthenticationProvider` lấy dữ liệu từ cache, kiểm credential, và xử lý khi mật khẩu không khớp.
3. Hiểu cấu hình mặc định `NullUserCache`: **Spring Security không tự bật một kho cache `UserDetails` hữu hiệu cho mọi ứng dụng**.
4. Dự đoán tác động của việc đổi mật khẩu, khóa/mở khóa tài khoản, xóa người dùng, đổi role, authorities, tenant hoặc hạn tài khoản khi có bản `UserDetails` cũ.
5. Chủ động dùng `UserCache.removeUserFromCache(username)`, cập nhật đúng cache layer sau giao dịch và thiết kế phương án cho nhiều instance.
6. Hiểu vì sao cache invalidation không tự cập nhật `Authentication` trong session, remember-me hay claims của JWT đang lưu hành.
7. Chạy một ví dụ Java 17 dùng `DaoAuthenticationProvider` với cache có chủ đích; quan sát số lần tải người dùng và kết quả trước/sau khi evict.

## 2. UserDetails chứa gì, và vì sao lại có cache?

Trong mô hình xác thực tên đăng nhập/mật khẩu, `UserDetailsService.loadUserByUsername(username)` trả `UserDetails` để provider có dữ liệu kiểm chứng. `UserDetails` thường mô tả:

- Username định danh trong kho tài khoản.
- Mật khẩu **đã được encode/hash** để `PasswordEncoder` kiểm mật khẩu nhập vào.
- Các cờ trạng thái như `isEnabled()`, `isAccountNonLocked()`, `isAccountNonExpired()`, `isCredentialsNonExpired()`.
- Tập `GrantedAuthority` thể hiện role/quyền theo cơ chế ánh xạ của ứng dụng.

Dữ liệu gốc có thể ở database, LDAP hoặc dịch vụ danh tính. Mỗi lần `loadUserByUsername` được gọi có thể tốn truy vấn DB hoặc request mạng. Cache `UserDetails` giúp giảm chi phí tra cứu nếu **nhiều lần xác thực** cần cùng dữ liệu tài khoản.

Tuy nhiên, `UserDetails` là **ảnh chụp của tài khoản tại thời điểm được tải**. Nếu bản gốc đổi sau khi cache đã lưu, snapshot vẫn có thể chứa mật khẩu hash, trạng thái khóa hoặc authority cũ. Đây là đặc tính cần quản trị rõ, nhất là khi đổi quyền/quản trị viên khóa tài khoản.

### Sơ đồ hai nguồn dữ liệu

~~~mermaid
flowchart LR
    R["Authentication request"] --> P["DaoAuthenticationProvider"]
    P --> C{"UserCache có username?"}
    C -->|Hit| U["Cached UserDetails"]
    C -->|Miss| S["UserDetailsService"]
    S --> DB["Kho tài khoản gốc"]
    S --> U2["UserDetails mới"]
    U2 --> C2["Có thể lưu vào UserCache"]
    U --> V["Kiểm trạng thái và mật khẩu"]
    C2 --> V
    V --> A["Authentication thành công hoặc exception"]
~~~

Sơ đồ mô tả đường chính. Trên **cache hit nhưng password không khớp**, provider chuẩn có thể **tải lại `UserDetailsService` để thử lần nữa** nhằm xét mật khẩu vừa thay đổi. Hành vi đặc biệt đó được phân tích ở mục 4.

## 3. Bốn lớp trạng thái rất dễ bị nhầm

| Lớp | Lưu cái gì? | Tồn tại đến khi nào? | Thay đổi tài khoản có tự cập nhật? |
| --- | --- | --- | --- |
| **Kho dữ liệu tài khoản** | Bản gốc username, hash mật khẩu, enabled/locked, authorities, tenant | Theo giao dịch nghiệp vụ | Đây là nơi thay đổi được ghi nhận |
| **`UserCache` hoặc cache của `UserDetailsService`** | Bản `UserDetails` vừa tải (có thể chứa hash password và authorities) | Cho đến eviction, expiration/TTL hoặc lỗi bộ nhớ | **Không có bảo đảm tự làm mới** khi DB đổi |
| **`Authentication` trong `SecurityContext`** | Principal, trạng thái xác thực, authorities đã chọn | Thường theo HTTP request hoặc session | Không tự đổi chỉ vì `UserCache` bị xóa |
| **Access token/JWT đã phát hành** | Claims, subject, scope/role, issuer, audience, expiration | Theo vòng đời token và kiểm soát thu hồi áp dụng | JWT tự chứa không sửa lại claim khi DB/cache đổi |

**Bốn câu hỏi riêng:**
1. “Database đã cập nhật chưa?”
2. “Lần authentication **mới** có lấy `UserDetails` mới chưa?”
3. “Session đang hoạt động có còn authorities cũ không?”
4. “API có còn chấp nhận token đã phát hành không?”

Xóa `UserCache` trả lời **chủ yếu câu hỏi 2**. Không được quảng bá việc evict cache là “logout tất cả”, “thu hồi token” hay “đổi quyền có hiệu lực ngay ở mọi request”.

### `Authentication` khác `UserDetails`

`Authentication` kết quả có thể giữ `UserDetails` làm `principal` và lưu một **bản authorities** tại thời điểm xác thực. Ngay cả khi lần xác thực sau trả authorities mới, một `Authentication` cũ đã lưu trong phiên không nhất thiết được thay thế. Với ứng dụng dùng `SessionCreationPolicy.STATELESS` và HTTP Basic, credentials được gửi ở từng request nên `DaoAuthenticationProvider` thường chạy lại, lúc này cache `UserDetails` ảnh hưởng trực tiếp hơn.

## 4. Mặc định của Spring Security: cache không tự bật theo ý bạn

`AbstractUserDetailsAuthenticationProvider` (lớp cha của `DaoAuthenticationProvider`) tích hợp giao diện `UserCache` để tìm/lưu/xóa `UserDetails`. **Mặc định là `NullUserCache`**, tức là thao tác lấy luôn không có cache hit hữu hiệu; mỗi lần xác thực username/password qua provider thường truy vấn `UserDetailsService`. Lý do: trong ứng dụng web có session, `SecurityContext` thường được khôi phục từ phiên và không cần xác thực lại mật khẩu mỗi request.

Các API chủ chốt:

~~~java
public interface UserCache {
    UserDetails getUserFromCache(String username);
    void putUserInCache(UserDetails user);
    void removeUserFromCache(String username);
}
~~~

Đây là **chữ ký API rút gọn** (không phải toàn bộ source của thư viện).

- `getUserFromCache(username)`: trả snapshot đã cache hoặc `null` nếu không có/hết hạn.
- `putUserInCache(user)`: lưu snapshot có key thường là `user.getUsername()`.
- `removeUserFromCache(username)`: xóa snapshot tương ứng; không thay đổi DB và không can thiệp session.

Khi muốn cache thật, cần cấu hình rõ `provider.setUserCache(...)` với một triển khai cache; ví dụ `SpringCacheBasedUserCache` chuyển tiếp thao tác tới Spring Cache (`Cache`). Spring Cache có nhiều backend khác nhau; mỗi loại có hỗ trợ TTL, eviction, consistency và multi-node khác nhau.

**Đừng nhầm `CachingUserDetailsService` với `UserCache` của provider:**

- `CachingUserDetailsService` bọc một `UserDetailsService` và cũng có `setUserCache(...)` riêng; theo mặc định wrapper này cũng bắt đầu bằng `NullUserCache`.
- `AbstractUserDetailsAuthenticationProvider.setUserCache(...)` cache tại **bước provider** trước khi cần gọi `UserDetailsService`.
- Nếu một ứng dụng cấu hình **cả hai lớp cache**, phải biết chính xác lớp nào giữ snapshot và phải invalidation **tất cả lớp liên quan** khi tài khoản đổi. Evict ở provider nhưng wrapper `CachingUserDetailsService` còn snapshot cũ thì lần tải lại vẫn có thể trả dữ liệu cũ.

**Khuyến nghị kiến trúc học tập:** bắt đầu với **một cache có chủ sở hữu rõ ràng**. Chỉ thêm cache thứ hai sau khi đã đo hiệu năng và có chiến lược đồng bộ trạng thái nhất quán.

## 5. Chu trình cache khi một authentication diễn ra

Dưới đây là luồng thường gặp với `DaoAuthenticationProvider` và cache được cấu hình:

~~~text
1. Filter tạo UsernamePasswordAuthenticationToken chưa xác thực.
2. Provider kiểm UserCache theo username.
3. Cache miss:
   - loadUserByUsername(username) từ nguồn dữ liệu;
   - kiểm các cờ trạng thái tài khoản và credential;
   - nếu thành công, có thể putUserInCache(UserDetails).
4. Cache hit:
   - dùng UserDetails snapshot từ cache;
   - kiểm trạng thái và mật khẩu trên snapshot;
   - nếu credential không khớp, provider chuẩn có đường tải lại user để thử lần nữa.
5. Nếu xác thực thành công, trả Authentication result với authorities.
6. ProviderManager có thể eraseCredentials() trên result sau thành công.
7. Filter/caller quyết định lưu kết quả vào SecurityContext.
~~~

### 5.1. Cache hit không có nghĩa bỏ kiểm mật khẩu

Cache `UserDetails` **không phải “đã login”**. Với cơ chế `DaoAuthenticationProvider`, khi một authentication mới được thực hiện, `PasswordEncoder.matches(rawPassword, cachedEncodedPassword)` vẫn cần thành công. Đừng viết custom provider chỉ kiểm “username tồn tại trong cache” rồi trả authenticated.

### 5.2. Cache miss và password sai

Provider có thể tải `UserDetails` rồi phát hiện password sai. Authentication thất bại và không phát hành kết quả đã xác thực. Không coi cache một password hash như bằng chứng đã xác thực.

### 5.3. Cache hit nhưng credential không khớp: có thể reload

`AbstractUserDetailsAuthenticationProvider` có cơ chế **thử tải lại người dùng qua `UserDetailsService`** khi đang dùng cached `UserDetails` mà `AuthenticationException` xuất hiện ở quá trình kiểm tra. Mục đích quan trọng là tránh từ chối sai một **mật khẩu vừa được thay đổi** chỉ vì cached hash cũ.

Ví dụ:

- Cache còn hash cho mật khẩu **cũ**.
- Kho gốc vừa đổi sang hash của mật khẩu **mới**.
- Người dùng thử mật khẩu **mới** → so với hash cũ trong cache bị sai → provider có thể tải bản gốc mới và kiểm lần nữa → thành công nếu trạng thái và policy đều hợp lệ.

**Nhưng chiều ngược lại không an toàn nếu thiếu invalidation:**

- Cache vẫn giữ hash cũ.
- Người dùng thử **mật khẩu cũ** → khớp ngay hash trong cache → provider có thể xác thực thành công **mà không cần tải DB mới**.
- Vì vậy cơ chế reload sau cache mismatch **không thay thế** việc xóa cache khi mật khẩu đổi.

Điểm này thường khó nhận ra nếu chỉ test “mật khẩu mới đăng nhập được” mà không test “mật khẩu cũ chắc chắn bị từ chối”.

### 5.4. Cache hit và tài khoản vừa bị khóa

Nếu snapshot cũ còn `enabled=true`, nhưng kho gốc đã đặt `enabled=false`, request có credential khớp cache có thể vượt qua kiểm tra **trạng thái cũ**. Provider không có cách biết DB đã đổi nếu snapshot vẫn còn hợp lệ trong cache.

Vì vậy các cập nhật nhạy cảm như **disable, lock, revoke, đổi quyền và đổi mật khẩu** cần đường invalidation hoặc một lớp kiểm tra trạng thái mới hơn theo mức độ bảo đảm mong muốn.

## 6. Những thay đổi tài khoản cần xử lý thế nào?

| Thay đổi ở kho gốc | Nguy cơ với cached UserDetails | Hành động bắt buộc hoặc cần cân nhắc |
| --- | --- | --- |
| Đổi mật khẩu | Cache còn hash cũ; password cũ có thể tiếp tục được chấp nhận | Evict ngay snapshot cũ; xác định chính sách session/token hiện có |
| Khóa tài khoản (`accountNonLocked=false`) | Request mới có thể vẫn thấy account unlocked | Evict; cân nhắc thu hồi session/token nếu yêu cầu khóa phải có hiệu lực tức thì |
| Vô hiệu hóa (`enabled=false`) | Cache có thể vẫn hiển thị enabled | Evict; kiểm các phiên hiện hữu và tài nguyên cần chặn |
| Đổi role/authorities | Lần login mới có thể nhận role cũ | Evict; cập nhật chính sách đối với phiên/token đang lưu hành |
| Gỡ quyền thuộc tenant | Cache hoặc `Authentication` cũ có thể chứa quyền tenant không còn hợp lệ | Evict cache, thêm kiểm quyền tài nguyên từ nguồn đáng tin; xử lý session/token |
| Xóa tài khoản | Cache vẫn có bản user dù kho gốc đã xóa | Evict và vô hiệu các trạng thái truy cập liên quan |
| Đổi username/key | Entry cũ vẫn còn ở key username cũ | Evict **cả key cũ và key mới** theo logic định danh thực tế; tránh nhầm hai danh tính |
| Reset MFA hoặc thay đổi assurance | Cached UserDetails không thể đại diện đầy đủ cho toàn bộ bằng chứng MFA | Thu hồi/step-up theo phiên, IdP và policy; không chỉ evict UserDetails |
| Đổi thông tin profile chỉ để hiển thị | Có thể hiện tên/email cũ | Quyết định chấp nhận độ trễ nhất định hoặc làm mới theo yêu cầu hiển thị |

**Chủ sở hữu thay đổi rất quan trọng:** nếu admin UI, tác vụ nền, LDAP sync và webhook IdP đều có thể sửa tài khoản, mọi đường ghi phải có quy tắc invalidation tương ứng. Nếu chỉ controller “đổi mật khẩu” evict cache nhưng job đồng bộ quyền thì không, hệ thống vẫn có cửa sổ stale data.

## 7. Invalidation là một phần của nghiệp vụ cập nhật tài khoản

Một nguyên tắc hữu ích:

> **Sau khi cập nhật tài khoản được xác nhận thành công ở nguồn gốc, những lần xác thực mới phải được thiết kế để thấy trạng thái phù hợp với cam kết bảo mật của hệ thống.**

### 7.1. Tại sao thứ tự “ghi DB → evict cache” quan trọng?

Giả sử code xóa cache **trước** khi thay đổi được commit, rồi một request đồng thời tải user từ DB với dữ liệu cũ và nạp lại cache. Sau đó commit mới hoàn tất nhưng cache lại giữ bản cũ. Đây là một race condition điển hình.

Đường đơn giản với store đã có transaction:

~~~text
BEGIN TRANSACTION
  UPDATE account SET enabled = false WHERE id = ...
COMMIT thành công
  -> evict/refresh cache entry của account
  -> thông báo các instance/region cache liên quan nếu có
  -> thực thi chính sách revoke session/token theo yêu cầu
~~~

**Lưu ý:** gửi eviction **sau commit** giảm khả năng cache bị nạp lại từ dữ liệu chưa commit. Tuy nhiên giữa commit và eviction vẫn tồn tại một cửa sổ ngắn, và event có thể bị mất/đến trễ. Với hệ thống cần khóa ngay lập tức, phải có ràng buộc mạnh hơn (chẳng hạn kiểm version/revocation tại request, cơ chế phân tán đáng tin và chính sách fail closed), không chỉ phụ thuộc một sự kiện best effort.

### 7.2. Cập nhật cache tập trung trong application service

Dạng pseudocode (không phải chương trình Java độc lập):

~~~java
@Transactional
public void changeUserRole(String username, String newRole) {
    repository.updateRole(username, newRole);
    domainEvents.publish(new AccountChanged(username));
}

// Listener sau commit, chạy trong cùng ứng dụng:
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(AccountChanged event) {
    userCache.removeUserFromCache(event.username());
}
~~~

Các biến `repository`, `domainEvents`, `userCache` là dependency được cấu hình thực tế; `AccountChanged` là event ứng dụng tự định nghĩa. Đoạn này **minh họa thời điểm**; cần import, constructor/DI, event publication khi có transaction và test. `@TransactionalEventListener` chạy sau commit khi event được phát trong transaction thích hợp; **nó không tự tạo một hệ thống event phân tán bền vững** và không bảo đảm các process khác đã evict.

Nếu việc cập nhật ở hệ thống ngoài (IdP/LDAP) không có cùng transaction DB, thiết kế event/outbox, retry/idempotency và reconciliation riêng. Với yêu cầu bảo mật mạnh, có thể cần đồng bộ trạng thái truy cập qua một nguồn version/revocation nhất quán khi mỗi request được xử lý.

### 7.3. Evict hay update trực tiếp cache?

- **Evict** thường dễ an toàn hơn: khi cần xác thực lần sau, provider tải lại bản chuẩn từ `UserDetailsService`.
- **Update trực tiếp** có thể giảm cache miss, nhưng phải chắc snapshot mới đã chứa **toàn bộ** trạng thái tài khoản đúng và không có sự kiện cũ ghi đè sự kiện mới.
- **TTL** là tuyến phòng vệ thứ hai, không thay thế evict chủ động khi đổi mật khẩu/khóa tài khoản.
- **Version stamp** (ví dụ accountVersion/securityVersion) giúp phát hiện dữ liệu cũ; riêng việc lưu version trong cache mà không kiểm version authoritative sẽ **không** bảo đảm dữ liệu mới.

### 7.4. Trường hợp nhiều replica/microservice

Với cache local riêng từng JVM, `removeUserFromCache` trên instance A **không xóa entry của B và C**. Lựa chọn thường gặp:

1. Dùng cache phân tán với cơ chế invalidation phù hợp và quyền truy cập được bảo vệ.
2. Phát sự kiện account-changed/revoked tới tất cả instance, có retry, idempotency và cơ chế phát hiện sự kiện bỏ sót.
3. Dùng thời hạn ngắn, kiểm version hoặc trạng thái thu hồi từ nơi đáng tin cho các thao tác nhạy cảm.
4. Giảm cache hoặc tắt cache trên những đường xác thực đòi nhất quán mạnh.

Ngay cả shared cache cũng cần hiểu consistency, replication lag, cache stampede và race khi cập nhật. Đừng tuyên bố “đã invalidate” nếu chỉ có một instance nhận event. Theo dõi metrics về cache hit/miss, eviction và thời điểm trạng thái mới có hiệu lực.

## 8. Demo Java 17: cache hit, quyền cũ, khóa account, đổi password

Ví dụ này chạy dưới dạng **Java console**, dùng `DaoAuthenticationProvider` thật để kiểm hash BCrypt, `SpringCacheBasedUserCache` và `ConcurrentMapCache`. Nó **không dùng Spring MVC/SecurityFilterChain** vì mục tiêu là quan sát hợp đồng `UserDetails` tại provider một cách độc lập.

Đặc biệt, ta gọi `provider.setForcePrincipalAsString(true)` để kết quả Authentication dùng **String username** làm principal trong demo, tránh result giữ tham chiếu trực tiếp tới đối tượng `UserDetails` cached khi `ProviderManager` xóa credentials. Đó là một lựa chọn thí nghiệm có chủ đích; ứng dụng thực thường muốn principal là `UserDetails` và cần cách copy/erase credential phù hợp hơn.

### 8.1. Cấu trúc dự án

~~~text
user-details-cache-lab/
├── settings.gradle
├── build.gradle
└── src/main/java/example/usercache/
    └── UserCacheLab.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'user-details-cache-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.3.5'
    implementation 'org.springframework.security:spring-security-crypto:6.3.5'
    implementation 'org.springframework:spring-context:6.1.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.usercache.UserCacheLab'
}
~~~

Các phiên bản chỉ dùng để cố định môi trường demo. Trong ứng dụng Spring Boot thực, ưu tiên dùng dependency management/BOM tương thích và các bản vá bảo mật thích hợp thay vì trộn các phiên bản framework tùy ý.

### 8.2. UserCacheLab.java hoàn chỉnh

`src/main/java/example/usercache/UserCacheLab.java`:

~~~java
package example.usercache;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserCache;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.core.userdetails.cache.SpringCacheBasedUserCache;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public class UserCacheLab {

    // Snapshot bất biến mô phỏng một dòng trong database.
    record Account(
            String username, String encodedPassword, boolean enabled,
            List<String> authorities) {}

    static final class AccountStore implements UserDetailsService {
        private final Map<String, Account> accounts =
                new ConcurrentHashMap<>();
        private final AtomicInteger loads = new AtomicInteger();
        private final PasswordEncoder encoder;

        AccountStore(PasswordEncoder encoder) {
            this.encoder = encoder;
            accounts.put("lan", new Account(
                    "lan", encoder.encode("old-pass"), true,
                    List.of("reports.read")));
        }

        @Override
        public UserDetails loadUserByUsername(String username)
                throws UsernameNotFoundException {
            loads.incrementAndGet();
            Account account = accounts.get(username);
            if (account == null) {
                throw new UsernameNotFoundException("Unknown user");
            }
            return User.withUsername(account.username())
                    .password(account.encodedPassword())
                    .disabled(!account.enabled())
                    .authorities(account.authorities()
                            .toArray(String[]::new))
                    .build();
        }

        int loadCount() {
            return loads.get();
        }

        // Từng thay đổi mô phỏng đã được commit vào store authoritative.
        void changeAuthority(String username, String authority) {
            accounts.computeIfPresent(username, (key, old) ->
                    new Account(old.username(), old.encodedPassword(),
                            old.enabled(), List.of(authority)));
        }

        void setEnabled(String username, boolean enabled) {
            accounts.computeIfPresent(username, (key, old) ->
                    new Account(old.username(), old.encodedPassword(),
                            enabled, old.authorities()));
        }

        void changePassword(String username, String rawNewPassword) {
            String encoded = encoder.encode(rawNewPassword);
            accounts.computeIfPresent(username, (key, old) ->
                    new Account(old.username(), encoded,
                            old.enabled(), old.authorities()));
        }
    }

    static void attempt(
            String label, AuthenticationManager manager,
            AccountStore store, String password) {
        Authentication input =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "lan", password);

        try {
            Authentication result = manager.authenticate(input);
            List<String> authorities = result.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList();
            System.out.println(label + " => OK "
                    + authorities + " loads=" + store.loadCount());
        }
        catch (AuthenticationException ex) {
            System.out.println(label + " => "
                    + ex.getClass().getSimpleName()
                    + " loads=" + store.loadCount());
        }
    }

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        AccountStore store = new AccountStore(encoder);
        UserCache cache = new SpringCacheBasedUserCache(
                new ConcurrentMapCache("user-details"));

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider();
        provider.setUserDetailsService(store);
        provider.setPasswordEncoder(encoder);
        provider.setUserCache(cache);

        // Chỉ để demo: result principal là username String, tránh chia sẻ
        // cùng instance UserDetails với cache khi manager erase credentials.
        provider.setForcePrincipalAsString(true);

        AuthenticationManager manager =
                new ProviderManager(List.of(provider));

        attempt("first-login", manager, store, "old-pass");
        attempt("cached-login", manager, store, "old-pass");

        store.changeAuthority("lan", "reports.admin");
        attempt("role-changed-without-evict",
                manager, store, "old-pass");

        cache.removeUserFromCache("lan");
        attempt("role-after-evict",
                manager, store, "old-pass");

        store.setEnabled("lan", false);
        attempt("disabled-without-evict",
                manager, store, "old-pass");

        cache.removeUserFromCache("lan");
        attempt("disabled-after-evict",
                manager, store, "old-pass");

        store.setEnabled("lan", true);
        store.changePassword("lan", "new-pass");
        cache.removeUserFromCache("lan");
        attempt("old-password-after-evict",
                manager, store, "old-pass");
        attempt("new-password",
                manager, store, "new-pass");

        store.changePassword("lan", "latest-pass");
        attempt("previous-password-with-stale-cache",
                manager, store, "new-pass");

        cache.removeUserFromCache("lan");
        attempt("previous-password-after-evict",
                manager, store, "new-pass");
        attempt("latest-password",
                manager, store, "latest-pass");
    }
}
~~~

**Vì sao đoạn code phản ánh hành vi cache?**

- `AccountStore` là **source of truth** mô phỏng: mỗi `loadUserByUsername` tăng bộ đếm `loads`.
- Mỗi lần gọi `loadUserByUsername` trả **`UserDetails` snapshot mới** theo bản `Account` hiện tại, không trả đối tượng có thể bị sửa ngầm bởi nơi khác.
- `SpringCacheBasedUserCache` lưu snapshot trong `ConcurrentMapCache`. Đây là **cache local demo**, không có TTL/multi-node/transaction hay bảo đảm bảo mật production.
- `DaoAuthenticationProvider` thật kiểm BCrypt và account status. Không có provider giả “accept all”.
- `ProviderManager` xóa credentials trong `Authentication` kết quả theo mặc định nếu hỗ trợ; `setForcePrincipalAsString(true)` giúp tránh để chính instance `UserDetails` cached nằm trong result principal của demo.
- Các thay đổi role/disable/password được thực hiện **cố tình không evict** ở vài bước để cho thấy rủi ro, rồi gọi `removeUserFromCache("lan")` để thử lại.

### 8.3. Chạy chương trình

Từ thư mục `user-details-cache-lab`, sử dụng Java 17+ và Gradle tương thích (hoặc Gradle Wrapper):

~~~bash
gradle run --quiet
~~~

Với Gradle Wrapper, dùng `./gradlew run --quiet`, trên Windows có thể dùng `.\gradlew.bat run --quiet`.

**Kết quả của các dòng `System.out.println` trong `main`** (số lần tải gốc đo qua `loadCount`):

~~~text
first-login => OK [reports.read] loads=1
cached-login => OK [reports.read] loads=1
role-changed-without-evict => OK [reports.read] loads=1
role-after-evict => OK [reports.admin] loads=2
disabled-without-evict => OK [reports.admin] loads=2
disabled-after-evict => DisabledException loads=3
old-password-after-evict => BadCredentialsException loads=4
new-password => OK [reports.admin] loads=5
previous-password-with-stale-cache => OK [reports.admin] loads=5
previous-password-after-evict => BadCredentialsException loads=6
latest-password => OK [reports.admin] loads=7
~~~

**Diễn giải từng nhóm kết quả:**

1. `first-login` tải store một lần. `cached-login` dùng snapshot trong cache nhưng **vẫn kiểm password với hash đã cache**.
2. Đổi role ở store không động chạm cache, nên `role-changed-without-evict` vẫn nhận `reports.read` (role cũ). Sau eviction, request mới nhận `reports.admin`.
3. Disable account ở store nhưng không evict, nên `disabled-without-evict` vẫn xác thực theo snapshot enabled=true. Sau eviction, `DaoAuthenticationProvider` ném `DisabledException`.
4. Đổi mật khẩu sang `new-pass` và evict: `old-pass` bị từ chối; `new-pass` được chấp nhận.
5. Đổi tiếp sang `latest-pass` **nhưng không evict**, snapshot vẫn chứa hash `new-pass`. Mật khẩu `new-pass` vẫn được chấp nhận trong lần xác thực mới; sau eviction, mật khẩu cũ bị từ chối và `latest-pass` được chấp nhận.

**Quan sát để học:** đếm lần tải là chỉ số cho cache hit/miss, **không phải** chỉ số cho tổng số lần kiểm BCrypt. Với password đúng trên cache hit, provider có thể vẫn kiểm password. Với password sai trên cache hit, provider có thể tải lại từ nguồn gốc và kiểm tiếp. Không khẳng định mọi kết quả thất bại tăng load đúng một lần trong mọi cấu hình/custom provider.

### 8.4. Thay một bước để kiểm nhánh reload khi password mismatch

Sau khi `new-password` đã thành công và cache đang giữ hash `new-pass`, có thể chạy kịch bản **đổi mật khẩu sang `latest-pass` mà chưa evict**, rồi **thử `latest-pass` trước** (khác với thứ tự `main` hiện tại):

~~~java
store.changePassword("lan", "latest-pass");
// Chưa removeUserFromCache(...)
attempt("new-password-on-stale-cache",
        manager, store, "latest-pass");
~~~

Provider thấy cache hit nhưng hash cũ không khớp `latest-pass`. Với triển khai `AbstractUserDetailsAuthenticationProvider` chuẩn, nó có thể tải dữ liệu mới qua `UserDetailsService` và xác thực bằng hash mới; nhờ vậy mật khẩu mới có thể hoạt động trước khi evict. **Điều này không chứng minh cache cũ đã được vô hiệu an toàn**. Bài test bắt buộc thêm là thử lại password cũ để kiểm liệu policy thu hồi đã có hiệu lực hay chưa.

Nhánh trên là **đoạn thay thế một phần của `main`**, không phải chương trình độc lập thứ hai. Hành vi cache cụ thể phụ thuộc phiên bản và provider; nếu custom provider thay đổi contract, phải kiểm lại.

## 9. Vấn đề ít thấy: eraseCredentials() có thể tác động cache

`ProviderManager` mặc định có `eraseCredentialsAfterAuthentication=true`. Sau khi nhận result thành công, nó yêu cầu xóa credentials nếu result hỗ trợ `CredentialsContainer`. Nếu `Authentication` result có principal là **cùng instance `UserDetails` đang nằm trong cache**, và principal triển khai cơ chế erase credentials, hash password của snapshot có thể bị xóa.

Tình huống dễ gây nhầm:

~~~text
UserDetailsService -> UserDetails instance U có passwordHash
UserCache lưu đúng tham chiếu U
DaoAuthenticationProvider trả Authentication(principal = U)
ProviderManager gọi eraseCredentials() trên Authentication result
  -> có thể xóa passwordHash trong U
Lần xác thực sau cache hit U không còn hash cần để so mật khẩu
~~~

**Không được giải quyết bằng cách mặc định tắt xóa credential ở production.** Có một số chiến lược tùy nhu cầu:

- Không cache `UserDetails` khi chi phí tra cứu chấp nhận được; giữ `NullUserCache`.
- Cache snapshot riêng và trả **bản sao phù hợp** làm principal cho `Authentication` result, để lệnh xóa credential không đụng instance cached.
- Với nhu cầu chỉ dùng username string, có thể cấu hình `setForcePrincipalAsString(true)` giống demo; điều này **đổi kiểu principal**, nên không áp dụng bừa vào ứng dụng đang cần `@AuthenticationPrincipal UserDetails`.
- Nếu thật sự phải thay đổi `eraseCredentialsAfterAuthentication`, đánh giá đầy đủ rủi ro giữ credential trong bộ nhớ, logging và session; đây không phải lựa chọn mặc định.

Dù cache chỉ lưu hash thay vì raw password, hash vẫn là dữ liệu nhạy cảm. Bảo vệ bộ nhớ/cache server, quyền vận hành và kênh truyền; tránh log toàn bộ object `UserDetails`.

## 10. Session và JWT vẫn có thể mang dữ liệu cũ sau khi evict

### 10.1. Ứng dụng dùng session

Browser đăng nhập bằng form/OIDC, phiên lưu `SecurityContext`. Sau khi admin đổi role, xóa `UserCache` **không tự sửa** authorities trong `Authentication` đã tồn tại trong session. Một request sau có thể được xử lý dựa trên session mà không gọi lại `UserDetailsService`.

Các cách xử lý tùy nhu cầu:

- Vô hiệu hóa/thu hồi session của user sau thay đổi nhạy cảm.
- Kiểm securityVersion hoặc trạng thái tài khoản mới nhất ở những request quan trọng.
- Yêu cầu đăng nhập lại/step-up trước thao tác nhạy cảm.
- Tách quyết định permission theo tài nguyên khỏi dữ liệu role cũ trong session.

Một chương trình quản lý session phải bảo đảm thu hồi qua **mọi node hoặc session store** liên quan. Không hứa “xóa UserCache là mọi phiên logout”.

### 10.2. API dùng JWT bearer access token

Resource Server có thể xác minh JWT bằng chữ ký, issuer, audience và thời hạn mà **không gọi `UserDetailsService` mỗi request**. Vì thế evict `UserCache` có thể **không ảnh hưởng gì** đến quyền đã ký trong JWT còn hạn.

Nếu cần thu hồi gần như tức thời, xem xét token lifetime ngắn, introspection/opaque token, cơ chế token revocation/denylist, hoặc kiểm securityVersion với nguồn trạng thái đáng tin trên request quan trọng. Không tự suy diễn `exp` là “hủy ngay khi đổi role”.

### 10.3. Remember-me và authentication mới

Remember-me có cơ chế cookie/token và có thể nạp lại user khi khôi phục đăng nhập, nhưng hành vi phụ thuộc loại remember-me service, token store và cấu hình. Invalidate `UserDetails` cache chỉ giải quyết **một phần đường dữ liệu**; phải kiểm thêm cơ chế thu hồi remember-me, session và credential reset.

### 10.4. Vai trò của authorization

`UserDetails.getAuthorities()` chỉ là một nguồn authority tại thời điểm xác thực. Các nghiệp vụ phức tạp thường phải kiểm quyền trên tài nguyên, tenant, ownership hoặc entitlement mới nhất. Việc cached role “ADMIN” còn cũ không nên là cơ sở duy nhất cho quyết định có tác động cao.

## 11. Thiết kế cache: TTL, consistency, ownership và metrics

### 11.1. Khi nào nên bật?

**Có thể phù hợp:** API nhận username/password trên mỗi request, nguồn user remote/LDAP chậm, chi phí tra cứu lớn và ứng dụng có khả năng invalidation rõ ràng.

**Cần cân nhắc kỹ hoặc không bật:** ứng dụng dùng session (không gọi provider mỗi request), tài khoản thay đổi trạng thái/quyền thường xuyên, chính sách revoke tức thì hoặc chưa có đường evict từ tất cả actor có thể sửa user.

Hãy **đo** load count, latency và số lần cache hit trước khi thêm cache. Không hy sinh yêu cầu cập nhật trạng thái bảo mật chỉ để giảm một truy vấn.

### 11.2. Cache key và phạm vi danh tính

`UserCache` chuẩn tìm bằng `username`. Trong hệ thống nhiều tenant/realm/issuer có thể có hai “alex” khác nhau, phải thiết kế namespace người dùng để tránh cache collision. Không giả định username một chuỗi là duy nhất toàn hệ thống. Có thể cần normalize key hoặc chọn một layer cache khác có key đầy đủ (`tenant, realm, subject`) kèm provider tương ứng.

Đừng dùng email có thể thay đổi làm key mà không có quy tắc migration/eviction key cũ. Đừng để một tenant đọc `UserDetails` của tenant khác vì cùng username.

### 11.3. TTL không phải cơ chế thu hồi tức thì

Ví dụ TTL 5 phút nghĩa snapshot có thể cũ gần 5 phút **nếu không có eviction**. Với password reset hoặc account disable, cửa sổ đó có thể không chấp nhận được. TTL ngắn làm giảm thời gian stale tối đa trong điều kiện bình thường, nhưng vẫn cần xử lý cache nạp lại sau sự kiện, đồng bộ clock và chính sách failover.

### 11.4. Cache observability và bảo mật

Nên đo:

- `user_cache_hit`, `user_cache_miss`, `user_cache_eviction`;
- `user_details_load_count` và latency tải user;
- độ trễ từ account update commit đến khi mọi đường xác thực quan trọng thấy giá trị mới;
- số event invalidation thất bại, thứ tự event và độ trễ giữa các instance;
- tỷ lệ thất bại xác thực do locked/disabled/bad credentials (giữ privacy, không log raw username hoặc secret nếu không cần).

**Không log:** mật khẩu dạng bản rõ, password hash, token bearer, remember-me cookie, PII/claim nhạy cảm hoặc toàn bộ `UserDetails.toString()`. Cache có thể chứa secret derivations; giới hạn quyền đọc/ghi và đặt thời hạn lưu phù hợp.

## 12. Test các điều kiện không được bỏ sót

Để bảo đảm cập nhật tài khoản có hiệu lực, chỉ test “cache miss nhanh hơn” là chưa đủ. Các case tối thiểu:

| Test | Bước | Kỳ vọng |
| --- | --- | --- |
| Cache hit | Xác thực cùng username/password 2 lần với cache bật | `UserDetailsService` có thể chỉ tải một lần; cả hai đều kiểm password |
| Cập nhật role **không** evict | Cache role A, DB đổi role B, xác thực lại | Có thể vẫn nhận role A, cho thấy stale risk |
| Cập nhật role **có** evict | Cache role A, DB đổi B, evict, xác thực lại | Nhận role B |
| Disable account | Cache enabled=true, DB disable, evict, xác thực | Bị từ chối bằng trạng thái account mới |
| Reset password | DB đổi hash, evict, thử password cũ và mới | Password cũ bị từ chối, password mới thành công |
| Nhánh mismatch reload | Cache hash cũ, DB đổi hash mới nhưng chưa evict | Password mới có thể dẫn tới tải mới; vẫn phải kiểm password cũ |
| Concurrent update/cache fill | Simulate user load cạnh commit + eviction | Không để snapshot cũ sống vô thời hạn; có biện pháp version/consistency |
| Multi-instance | Update account trên node A, xác thực trên B/C | B/C cũng thấy chính sách mới trong SLA |
| Existing session | Đổi quyền và evict cache, dùng session cũ | Hiểu và kiểm chính sách refresh/thu hồi session riêng |
| JWT còn hạn | Đổi quyền và evict UserCache, gửi JWT cũ | Kiểm policy token revocation/authorization riêng |
| Cache credential erasure | Xác thực và xác thực lại liên tiếp | Không hỏng cached encoded password do chia sẻ principal reference |
| Key change/tenant | Đổi username hoặc cùng name khác tenant | Evict đúng key, không nhầm principal giữa các realm |

Một test hợp lệ cho phần cache phải thực sự gọi **authentication provider với credential**. `@WithMockUser` giúp kiểm authorization ở tầng khác, nhưng bỏ qua đường lấy `UserDetails` và `PasswordEncoder` nên không xác minh được cache này.

## 13. Các lỗi phổ biến

1. **Tưởng Spring Security luôn cache `UserDetails`.** Default `NullUserCache` không tạo cache hit hữu hiệu.
2. **Chỉ cache theo `@Cacheable` mà không có `@CacheEvict` tương ứng.** Bản role/password/status có thể tồn tại sau khi DB đổi.
3. **Evict trước transaction commit.** Request song song có thể nạp lại dữ liệu cũ vào cache.
4. **Chỉ evict ở một node.** Replica khác vẫn xác thực theo cached snapshot.
5. **Cho rằng password mới đăng nhập được nghĩa password cũ đã bị thu hồi.** Cơ chế fallback reload trên mismatch không bảo đảm chiều ngược lại.
6. **Chỉ test account enabled sau khi xóa cache.** Quên test trường hợp cached enabled=true vẫn còn trên node khác.
7. **Lẫn cache UserDetails với session/JWT.** Xóa cache không thay đổi kết quả đã lưu/phát hành.
8. **Cache cùng object principal rồi eraseCredentials.** Có thể làm mất hash cần so ở lần xác thực sau.
9. **Tắt `eraseCredentialsAfterAuthentication` vô điều kiện.** Giữ credential trong object lâu hơn cần thiết.
10. **Tin TTL là đủ cho yêu cầu khóa ngay.** TTL vẫn có stale window và race.
11. **Để hai người từ các tenant khác nhau dùng cùng key cache username.** Có thể nhầm authority và account status.
12. **Không phân biệt cache provider và cache UserDetailsService.** Xóa một lớp nhưng lớp kia trả snapshot cũ.
13. **Cache `Authentication` như thể đó là bản ghi account sống.** Authentication chứa kết quả của một lần chứng thực, không tự giám sát DB.
14. **Cập nhật role nhưng chỉ kiểm quyền ở UI.** API còn phải phân quyền trên resource/tenant bằng policy đáng tin.

## 14. Câu hỏi tự kiểm tra

**Câu 1:** `DaoAuthenticationProvider` có mặc định cache mọi user qua `UserCache` không?  
**Đáp án:** Không. `AbstractUserDetailsAuthenticationProvider` mặc định dùng `NullUserCache`. Phải cấu hình cache cụ thể nếu muốn cache hit thực.

**Câu 2:** Sau khi đổi password, thử password mới có thể thành công dù cache còn hash cũ. Có cần evict không?  
**Đáp án:** Có. Trên cache mismatch, provider chuẩn có thể tải dữ liệu mới để xác thực; nhưng password cũ **có thể vẫn khớp cached hash**. Evict và kiểm lại cả chiều từ chối password cũ.

**Câu 3:** Admin disable account, request mới vẫn đăng nhập được bằng password trước đó. Lỗi có thể ở đâu?  
**Đáp án:** `UserCache` còn snapshot `enabled=true`, có instance chưa nhận eviction hoặc session/token cũ còn hiệu lực. Cần kiểm từng layer và thời điểm invalidation.

**Câu 4:** Sau khi `removeUserFromCache("lan")`, một browser có session đã xác thực vẫn xem được dữ liệu. Có nhất thiết là bug cache không?  
**Đáp án:** Không. Session có thể chứa `Authentication` và authorities cũ, không gọi lại provider. Phải có chính sách session invalidation/refresh hoặc authorization kiểm trạng thái mới nếu cần.

**Câu 5:** Một hệ thống lưu JWT role ADMIN đã ký, sau đổi quyền USER chỉ evict UserCache. JWT cũ có tự đổi role không?  
**Đáp án:** Không. JWT tự chứa giữ claims đã ký cho đến khi hết hạn hoặc bị cơ chế kiểm/revocation từ chối; cần thiết kế riêng.

**Câu 6:** Vì sao cache hit vẫn phải kiểm password?  
**Đáp án:** Cache lưu dữ liệu account, không phải bằng chứng caller đã xác thực. Mỗi lần username/password authentication mới phải kiểm credential.

**Câu 7:** Evict cache sau commit có giải quyết mọi race không?  
**Đáp án:** Không. Vẫn có cửa sổ giữa commit và eviction, event trễ/mất, replica khác và concurrent refill. Yêu cầu mạnh cần version/revocation/consistency phù hợp.

**Câu 8:** Cache principal là UserDetails, sau authentication password hash bị xóa. Làm gì?  
**Đáp án:** Kiểm reference sharing và `eraseCredentials`; cân nhắc cache snapshot riêng, trả principal copy, principal string khi phù hợp hoặc tắt cache. Không mặc định giữ raw/encoded credentials trong result vô hạn.

**Câu 9:** Với đa tenant cùng username “alex”, cache dựa trên username thuần có đủ không?  
**Đáp án:** Không khi username chưa được đảm bảo duy nhất qua namespace. Cần thiết kế định danh/realm/tenant và key phù hợp, tránh gán sai authorities.

## 15. Checklist áp dụng vào hệ thống thật

Trước khi cấu hình cache `UserDetails`, hãy xác nhận:

- **Đúng điểm cache:** tại provider, tại `CachingUserDetailsService` hay cả hai? Ai sở hữu?
- **Đúng key:** username có duy nhất qua tenant/realm? Có thay đổi/rename không?
- **Đúng dữ liệu:** snapshot gồm hash, enabled, locked, expired, authorities nào?
- **Đúng đường cập nhật:** tất cả luồng admin, user, sync, batch và IdP đều phát tín hiệu invalidation?
- **Đúng thứ tự commit:** DB commit thành công trước khi evict, có xử lý race/event loss không?
- **Đúng phạm vi:** mọi replica/region cache cần thiết đều thấy thay đổi trong thời gian cho phép?
- **Đúng credential policy:** password cũ bị từ chối sau reset? account disable có hiệu lực theo SLA?
- **Đúng phiên/token:** đã quyết định xử lý session, remember-me và JWT hiện hữu chưa?
- **Đúng lifecycle:** tránh principal cached bị erase credentials, có TTL và eviction metrics?
- **Đúng test:** bao gồm trước/sau evict, concurrency, multi-node, session/JWT và kiểm quyền bản ghi.

**Điểm cốt lõi:** `UserCache` tối ưu việc **tìm dữ liệu người dùng cho một lần xác thực mới**; nó không phải cơ chế thu hồi tất cả quyền truy cập. Khi tài khoản đổi, cập nhật dữ liệu gốc, chủ động làm mới đúng lớp cache, và áp dụng chính sách phiên/token/quyền tài nguyên phù hợp. Hệ thống an toàn phải kiểm cả hai câu: **“Lần xác thực mới đã thấy dữ liệu mới chưa?”** và **“Quyền truy cập đang tồn tại có còn được phép không?”**

### Tài liệu tham khảo chính thức

- `UserCache` API, Spring Security 6.3: https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/core/userdetails/UserCache.html
- `AbstractUserDetailsAuthenticationProvider` (cache default, reload on mismatch): https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html
- `SpringCacheBasedUserCache`: https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/core/userdetails/cache/SpringCacheBasedUserCache.html
- `CachingUserDetailsService`: https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/authentication/CachingUserDetailsService.html
- `DaoAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/passwords/dao-authentication-provider.html
- `UserDetails`: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/passwords/user-details.html
