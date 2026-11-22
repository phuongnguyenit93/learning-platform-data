# UserDetailsPasswordService và nâng cấp giá trị băm sau đăng nhập

**Module:** Spring Security – authentication. **Nhóm kiến thức:** Nâng cấp mật khẩu.

## 1. Bài toán: xác thực được mật khẩu cũ nhưng không muốn tiếp tục lưu hash cũ

Một hệ thống đang vận hành có thể có nhiều thế hệ mật khẩu:

- Một tài khoản cũ lưu password dưới định dạng `{noop}...`, SHA/MD5 cũ hoặc một hash PBKDF2/scrypt/bcrypt với thông số thấp. `{noop}` và các digest nhanh **không đủ an toàn** cho lưu mật khẩu production.
- Tài khoản mới đã dùng encoder mạnh hơn, ví dụ bcrypt với work factor phù hợp.
- Hệ thống đã thay `PasswordEncoder` để **đọc được hash cũ nhưng tạo hash mới theo policy hiện tại**.
- Người dùng đăng nhập với **mật khẩu gốc đúng**; đây là một thời điểm hiếm hoi server nhận được raw password hợp lệ để có thể tính lại hash an toàn.

Mục tiêu là: **sau một lần đăng nhập thành công**, nếu hash hiện tại cần nâng cấp, ứng dụng tạo hash mới từ raw password vừa được kiểm tra và lưu vào kho tài khoản mà không bắt người dùng đổi mật khẩu thủ công.

Spring Security cung cấp ba thành phần ghép với nhau:

1. `PasswordEncoder`, nhất là `DelegatingPasswordEncoder`, **kiểm tra password** và báo `upgradeEncoding(storedHash)`.
2. `DaoAuthenticationProvider` **điều phối xác thực username/password** và có điểm móc (hook) gọi nâng cấp ở nhánh thành công.
3. `UserDetailsPasswordService` **ghi hash mới** vào nơi lưu user và trả về `UserDetails` sau cập nhật.

Đây là kỹ thuật **rehash-on-login** (nâng cấp giá trị băm khi đăng nhập), không phải cơ chế có thể giải mã hash đã lưu. Nếu người dùng không đăng nhập lại, server không biết raw password và không thể tự suy ra password để rehash; khi cần loại bỏ hash quá yếu có thể phải dùng quy trình reset password được xác minh.

> **Nguyên tắc:** Việc nâng cấp hash phải xảy ra **sau khi credential hợp lệ và account được phép xác thực**. Không dùng dữ liệu từ request chưa xác thực để ghi password mới. Không được để nâng cấp ghi đè password vừa reset ở giao dịch khác.

## 2. Các khái niệm cần phân biệt

| Thành phần | Hợp đồng chính | Vai trò trong quá trình nâng cấp |
| --- | --- | --- |
| `UserDetailsService` | `loadUserByUsername(username)` | **Đọc** username, password hash, trạng thái và authorities phục vụ xác thực |
| `PasswordEncoder` | `matches(raw, stored)`, `encode(raw)`, `upgradeEncoding(stored)` | Đối chiếu hash cũ; quyết định cần nâng cấp; tạo hash theo policy mới |
| `DaoAuthenticationProvider` | `authenticate(...)` | Xác minh mật khẩu, trạng thái và chỉ kích hoạt hook nâng cấp ở luồng thành công |
| `UserDetailsPasswordService` | `updatePassword(user, encodedNewPassword)` | **Lưu** giá trị băm mới; trả `UserDetails` sau cập nhật |
| `ProviderManager` | `authenticate(...)` | Điều phối provider và thường xóa credentials khỏi kết quả đã xác thực |
| `UserDetailsManager` | `createUser`, `updateUser`, `changePassword`,... | Quản trị tài khoản; **khác mục đích** hook nâng cấp hash |
| Domain repository/DAO | Các thao tác lưu có transaction/version | Thực thi cập nhật bền vững, chống race condition và invalidation cache |

**Không đồng nhất:**

- `UserDetailsService` chỉ biết **đọc** thông tin; không thể tự lưu hash mới nếu bạn chưa cung cấp cơ chế ghi.
- `UserDetailsPasswordService` không nhận raw password để tự kiểm tra; nó nhận một **hash mới đã được encoder tạo**.
- `UserDetailsManager.changePassword(old, new)` là hành động người dùng tự đổi mật khẩu, thường gắn với người dùng hiện tại trong `SecurityContext`; không phải cùng contract với nâng cấp hash do provider kích hoạt.
- `PasswordEncoder.upgradeEncoding(...) == true` chỉ là **tín hiệu**. Không có adapter ghi hoặc không có hook được cấu hình thì database có thể hoàn toàn không thay đổi.

## 3. Hợp đồng UserDetailsPasswordService

Package: `org.springframework.security.core.userdetails`. Interface có một phương thức:

~~~java
public interface UserDetailsPasswordService {
    UserDetails updatePassword(UserDetails user, String newPassword);
}
~~~

Theo Javadoc Spring Security 6.5:

- Tham số `user`: thông tin tài khoản cần cập nhật. Trong ứng dụng nhiều tenant, cần đảm bảo định danh user ở đây trỏ đúng account/tenant đã được xác minh.
- `newPassword`: **password đã encode bằng PasswordEncoder đang cấu hình**, ví dụ `{bcrypt}$2a$...`; **không phải raw password**.
- Tác dụng: thay hash trong kho tài khoản (database, directory hoặc store tương đương).
- Trả về: **`UserDetails` đã được cập nhật** với hash mới.

Ví dụ về một implementation thường được nhắc đến là `InMemoryUserDetailsManager`, vừa triển khai `UserDetailsManager` vừa triển khai `UserDetailsPasswordService`. Nó phù hợp để minh họa/test nhưng không phải database lưu trữ bền vững.

**Một vài quy tắc khi tự triển khai:**

1. Không gọi `encoder.encode(newPassword)` một lần nữa trong `updatePassword`, vì `newPassword` đã là **hash**; double hashing làm người dùng không thể đăng nhập bằng raw password ban đầu.
2. Không chấp nhận một username/tenant lấy tùy ý từ client làm đích cập nhật. Đích phải là tài khoản đã được provider xác minh.
3. Chỉ thay **password hash và metadata liên quan**. Không vô tình reset authorities, trạng thái khóa, flags, tenant membership hay profile.
4. Trả về một `UserDetails` hợp lệ, đồng bộ với hash mới và chính sách authorities; không trả `null`.
5. Có chiến lược chống ghi đè đồng thời bởi password reset/password change, xử lý transaction, audit và cache invalidation.
6. Không đưa raw password, hash mới hoặc object `UserDetails` đầy đủ vào log/trace/API response.

### Giá trị trả về có ý nghĩa gì?

Provider có thể sử dụng `UserDetails` được trả về trong phần hoàn tất xác thực. Tuy nhiên, không nên xây nghiệp vụ dựa trên giả định rằng **mọi implementation của `Authentication.getPrincipal()` chắc chắn chứa bản hash mới**: việc tạo principal còn tùy `AbstractUserDetailsAuthenticationProvider`, tùy cấu hình `forcePrincipalAsString` và cơ chế xóa credentials ở `ProviderManager`.

**Nguồn kiểm chứng việc lưu thành công là kho tài khoản được đọc lại sau transaction**, không phải `principal.getPassword()` sau login. Password trong principal có thể đã bị xóa để bảo vệ credentials.

## 4. Chính xác khi nào DaoAuthenticationProvider gọi nâng cấp?

Luồng mẫu cho một request username/password trong Spring Security Servlet:

~~~text
POST /login
    |
    v
UsernamePasswordAuthenticationFilter
    |
    v
AuthenticationManager -> ProviderManager
    |
    v
DaoAuthenticationProvider
    |
    +--> UserDetailsService.loadUserByUsername(username)
    |        -> UserDetails(passwordHash, flags, authorities)
    |
    +--> kiểm tra trạng thái account (pre-check)
    |
    +--> PasswordEncoder.matches(raw, storedHash)
    |          | false
    |          v
    |      BadCredentialsException -> login FAILED
    |
    +--> kiểm tra credential/account (post-check)
    |          | failed
    |          v
    |      AuthenticationException -> login FAILED
    |
    +--> nhánh tạo authentication thành công
               |
               +--> checker password bị lộ nếu có cấu hình
               |
               +--> có UserDetailsPasswordService?
               |          |
               |          +--> upgradeEncoding(storedHash)?
               |                      |
               |                      +--> false: giữ hash
               |                      |
               |                      +--> true:
               |                           encode(raw đã xác minh)
               |                           updatePassword(user, newEncoded)
               |
               v
         authenticated Authentication
               |
               v
      ProviderManager eraseCredentials()
               |
               v
         SecurityContext/session
~~~

**Điểm móc kỹ thuật:** Trong triển khai `DaoAuthenticationProvider` phiên bản 6.5, logic nâng cấp nằm trong quá trình `createSuccessAuthentication(...)`. Provider dùng raw credentials vừa được xác minh, gọi `PasswordEncoder.upgradeEncoding(existingEncodedPassword)` khi có password service phù hợp, tạo hash mới bằng `encode(raw)` rồi gọi `userDetailsPasswordService.updatePassword(user, newHash)`.

Điều kiện quan trọng cần cùng thỏa mãn:

- Request được xử lý bởi **`DaoAuthenticationProvider` đó**, với `UserDetailsService` và `PasswordEncoder` khớp định dạng dữ liệu.
- Password đã **được kiểm tra đúng**, account pass các checks và login đi tới nhánh thành công. Với tính năng kiểm tra password bị lộ nếu cấu hình, failure cũng không đi tới nhánh rehash.
- Password hash cũ có thể dùng để đánh giá `upgradeEncoding`.
- Provider **đã gắn** một `UserDetailsPasswordService` thực sự lưu dữ liệu, chứ không phải hook bỏ trống.
- `upgradeEncoding(stored)` trả `true` theo chính sách encoder hiện tại.

**Không có nghĩa** mỗi lần gọi `AuthenticationManager.authenticate(...)` đều rehash. Khi hash đã đạt policy, provider không cần tạo salt/hash mới. Khi mật khẩu sai, tài khoản khóa/disabled, hoặc một custom provider không dùng hook này, không nên có thao tác nâng cấp từ nhánh nói trên.

### Một số điều không tự động xảy ra

- Spring không thể rehash toàn bộ account không đăng nhập vì không có raw password.
- Hook không tự xác định schema/column và transaction cho repository tùy biến.
- `PasswordEncoder` không tự ghi database.
- Không phải mọi `AuthenticationProvider` như JWT/OIDC/LDAP hoặc một provider custom đều dùng `UserDetailsPasswordService`.
- Việc rehash **không tự động** thu hồi session, refresh token, JWT hoặc xác minh lại role trên mọi request.
- Việc thay hash **không tự động** tăng bcrypt cost hay đổi thuật toán nếu policy encoder vẫn như cũ.

## 5. PasswordEncoder.upgradeEncoding được hiểu thế nào?

### 5.1. Ba thao tác khác nhau

~~~java
String stored = "{noop}old-password"; // CHỈ ví dụ legacy, không an toàn

boolean correct = encoder.matches("old-password", stored);
boolean outdated = encoder.upgradeEncoding(stored);

String encodedNew = encoder.encode("old-password");
~~~

Đây là **đoạn minh họa**, chưa có khai báo/import `encoder`. Với `PasswordEncoderFactories.createDelegatingPasswordEncoder()` ở Spring Security 6.5, chuỗi `{noop}...` có thể match, được đánh giá cần upgrade vì ID khác chuẩn tạo mới `bcrypt`, rồi encoder tạo hash mới bắt đầu bằng `{bcrypt}`.

| Phương thức | Có xác minh mật khẩu không? | Có tạo hash mới không? | Có lưu database không? |
| --- | --- | --- | --- |
| `matches(raw, stored)` | **Có** | Không | Không |
| `upgradeEncoding(stored)` | **Không** | Không | Không |
| `encode(raw)` | Không tự biết raw có hợp lệ với account hay không | **Có** | Không |
| `updatePassword(user, encodedNew)` | Không thay việc xác minh của provider | Không cần tự encode | **Có**, nếu adapter lưu đúng |

**Không dùng `upgradeEncoding` như bằng chứng password đúng.** Kẻ lạ có thể gửi bất kỳ raw password nào và một stored hash cũng có thể được đánh giá “cần nâng cấp”. Quyết định rehash phải đặt sau `matches` thành công và các account checks.

### 5.2. DelegatingPasswordEncoder và {id}

Dữ liệu hash dạng:

~~~text
{id}encodedPassword
~~~

Trong factory Spring Security 6.5, `idForEncode` mặc định là `bcrypt`. Những account cũ có ID khác (ví dụ `{noop}`, `{pbkdf2}`, `{scrypt}`) có thể được đối chiếu bằng mapping tương thích, nhưng `upgradeEncoding` sẽ yêu cầu đổi sang chuẩn encode hiện tại nếu ID khác.

~~~text
DB trước:  {noop}legacy123           (chỉ ví dụ, plaintext nguy hiểm)
LOGIN:     raw = legacy123 -> matches = true
UPGRADE:   encoder.upgradeEncoding("{noop}...") = true
ENCODE:    encoder.encode(raw) -> {bcrypt}$2a$10$...
DB sau:    {bcrypt}$2a$10$...
~~~

Giá trị `{bcrypt}$2a$10$...` ở trên là **sơ đồ**, không phải hash cụ thể. BCrypt tạo salt ngẫu nhiên nên không nên viết unit test so sánh hash nguyên văn.

Ngay cả với cùng ID `bcrypt`, `BCryptPasswordEncoder.upgradeEncoding(...)` có thể phát hiện work factor của hash cũ thấp hơn strength cấu hình hiện tại. Với các encoder khác, semantics của `upgradeEncoding` tùy implementation; **không được tự giả định** mọi `PasswordEncoder` đều nhận biết mọi thay đổi policy.

### 5.3. Thiếu prefix hoặc ID chưa được map

Dữ liệu `$2a$10$...` không có `{bcrypt}`, hoặc `{unknown}payload`, có thể khiến `DelegatingPasswordEncoder.matches(...)` ném `IllegalArgumentException` khi không có encoder cho ID đó. Do đó, nâng cấp bằng hook **không tự xử lý** một record mà hệ thống chưa xác thực được.

Cần tìm đúng định dạng legacy trước, bổ sung tiền tố metadata được xác minh hoặc sử dụng fallback **có giới hạn, có audit và kế hoạch loại bỏ**, rồi mới dùng rehash-on-login. Không đặt `NoOpPasswordEncoder` làm fallback cho dữ liệu không xác định chỉ để “đăng nhập được”.

## 6. Demo Java 17 chạy được: nâng cấp đúng một lần sau login hợp lệ

Demo này dùng **Spring Security Core 6.5.11** với `DaoAuthenticationProvider`, `ProviderManager`, `PasswordEncoderFactories` và `InMemoryUserDetailsManager`.

Nó thể hiện 4 điều:

1. Sai mật khẩu không kích hoạt `updatePassword`.
2. Đăng nhập hợp lệ với hash cũ `{noop}` kích hoạt **đúng một lần** cập nhật sang `{bcrypt}`.
3. Đăng nhập lần nữa bằng cùng raw password thành công nhưng **không cập nhật lại** hash đã đạt policy.
4. Một provider **không có UserDetailsPasswordService** vẫn có thể cho login legacy thành công, nhưng **không tự lưu hash mới**.

> Dùng `{noop}` chỉ để chứng minh migration. Đây là kiểu lưu plaintext **không được dùng để tạo tài khoản mới trong production**. Demo không phải mô hình phân tán/database/HTTP.

### 6.1. Cấu trúc

~~~text
password-upgrade-demo/
├── build.gradle
└── src/main/java/example/PasswordUpgradeDemo.java
~~~

**File `build.gradle`:**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'example.PasswordUpgradeDemo'
}
~~~

**File `src/main/java/example/PasswordUpgradeDemo.java`:**

~~~java
package example;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsPasswordService;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public final class PasswordUpgradeDemo {

    private static Authentication login(
            AuthenticationManager manager, String user, String password) {
        return manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        user, password));
    }

    public static void main(String[] args) {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails legacy = User.withUsername("lan")
                .password("{noop}legacy-123")
                .roles("READER")
                .build();

        // Kho tài khoản in-memory dành riêng cho ví dụ.
        InMemoryUserDetailsManager users =
                new InMemoryUserDetailsManager(legacy);

        // Tách UserDetails dùng khi authenticate khỏi đối tượng ở kho.
        // Nhờ vậy cơ chế eraseCredentials không xóa nhầm hash của store.
        UserDetailsService loader = username ->
                User.withUserDetails(
                        users.loadUserByUsername(username)).build();

        AtomicInteger updates = new AtomicInteger();

        UserDetailsPasswordService updater = (user, encodedHash) -> {
            UserDetails saved = users.updatePassword(user, encodedHash);
            updates.incrementAndGet();
            // Trả bản sao dành riêng cho authentication.
            return User.withUserDetails(saved).build();
        };

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(loader);
        provider.setPasswordEncoder(encoder);
        provider.setUserDetailsPasswordService(updater);

        AuthenticationManager manager = new ProviderManager(provider);

        String initialHash = users.loadUserByUsername("lan").getPassword();
        System.out.println("before.legacy="
                + initialHash.startsWith("{noop}"));
        System.out.println("before.needsUpgrade="
                + encoder.upgradeEncoding(initialHash));

        // Lần đầu với password sai: không được nâng cấp.
        try {
            login(manager, "lan", "wrong");
            System.out.println("wrong=unexpected-success");
        } catch (BadCredentialsException expected) {
            System.out.println("wrong=BadCredentialsException");
        }
        System.out.println("afterWrong.updates=" + updates.get());

        // Password đúng: provider match, encode lại rồi gọi updater.
        Authentication first = login(manager, "lan", "legacy-123");
        String migratedHash =
                users.loadUserByUsername("lan").getPassword();

        System.out.println("first.authenticated="
                + first.isAuthenticated());
        System.out.println("first.updates=" + updates.get());
        System.out.println("first.bcrypt="
                + migratedHash.startsWith("{bcrypt}"));
        System.out.println("first.matches="
                + encoder.matches("legacy-123", migratedHash));
        System.out.println("first.needsUpgrade="
                + encoder.upgradeEncoding(migratedHash));
        System.out.println("first.roleReader="
                + first.getAuthorities().stream().anyMatch(a ->
                        "ROLE_READER".equals(a.getAuthority())));

        // Lần login đúng kế tiếp không cần encode lại.
        Authentication second = login(manager, "lan", "legacy-123");
        System.out.println("second.authenticated="
                + second.isAuthenticated());
        System.out.println("second.updates=" + updates.get());

        // Nếu KHÔNG gắn password service thì không tự lưu hash mới.
        InMemoryUserDetailsManager noUpdaterStore =
                new InMemoryUserDetailsManager(
                        User.withUsername("mai")
                                .password("{noop}other-legacy")
                                .roles("USER")
                                .build());

        UserDetailsService noUpdaterLoader = username ->
                User.withUserDetails(
                        noUpdaterStore.loadUserByUsername(username)).build();

        DaoAuthenticationProvider withoutUpdater =
                new DaoAuthenticationProvider(noUpdaterLoader);
        withoutUpdater.setPasswordEncoder(encoder);

        AuthenticationManager noUpdaterManager =
                new ProviderManager(withoutUpdater);

        Authentication legacyLogin =
                login(noUpdaterManager, "mai", "other-legacy");
        System.out.println("withoutUpdater.authenticated="
                + legacyLogin.isAuthenticated());
        System.out.println("withoutUpdater.stillLegacy="
                + noUpdaterStore.loadUserByUsername("mai")
                        .getPassword().startsWith("{noop}"));
    }
}
~~~

### 6.2. Chạy

Từ thư mục `password-upgrade-demo`, sử dụng **JDK 17+** và một bản Gradle tương thích:

~~~bash
gradle -q run
~~~

Nếu dự án có Gradle Wrapper, dùng `./gradlew -q run`; trên Windows sử dụng `gradlew.bat -q run`. Lần đầu Gradle có thể cần tải thư viện từ Maven Central.

**Stdout từ chương trình** (không tính log riêng của Gradle nếu cấu hình môi trường in thêm thông báo):

~~~text
before.legacy=true
before.needsUpgrade=true
wrong=BadCredentialsException
afterWrong.updates=0
first.authenticated=true
first.updates=1
first.bcrypt=true
first.matches=true
first.needsUpgrade=false
first.roleReader=true
second.authenticated=true
second.updates=1
withoutUpdater.authenticated=true
withoutUpdater.stillLegacy=true
~~~

### 6.3. Giải thích từng nhóm kết quả

- `before.legacy=true`: kho đang có hash `{noop}...`. Đây là dữ liệu mẫu **không an toàn** nhưng giúp thấy quá trình nâng cấp.
- `before.needsUpgrade=true`: encoder tạo mới theo `bcrypt`, nên định dạng `noop` bị đánh dấu cũ.
- `wrong=BadCredentialsException` và `afterWrong.updates=0`: mật khẩu sai không đưa provider vào nhánh nâng cấp.
- `first.authenticated=true`, `first.updates=1`: provider đã kiểm tra mật khẩu, gọi adapter ghi hash mới và hoàn tất login.
- `first.bcrypt=true` và `first.matches=true`: bản ghi trong kho giờ chứa bcrypt hash mới, raw password vẫn đối chiếu thành công.
- `first.needsUpgrade=false`: hash mới phù hợp ID/cost của policy hiện tại.
- `first.roleReader=true`: authorities vẫn giữ role do kho cấp; nâng cấp hash không có nghĩa cấp quyền mới.
- `second.updates=1`: lần đăng nhập tiếp không ghi hash mới nếu `upgradeEncoding` trả false.
- `withoutUpdater.stillLegacy=true`: **chỉ cấu hình PasswordEncoder là chưa đủ** để tự ghi lại hash sau login.

**Vì sao loader/updater tạo bản sao?** `ProviderManager` mặc định xóa credentials ở `Authentication` thành công. Nếu principal chia sẻ cùng object `UserDetails` với kho/cache, việc xóa credential có thể làm mất hash đang lưu. Demo tạo `User.withUserDetails(...).build()` để không dùng chung object mutable giữa nơi lưu và principal. Trong sản phẩm, nguyên tắc tương tự áp dụng cho cache `UserDetails` và object trả cho provider.

**Demo không chứng minh tính an toàn concurrent của database.** `InMemoryUserDetailsManager` được dùng đơn luồng và không có transactional storage; phần tiếp theo thiết kế riêng việc update có điều kiện cho môi trường thật.

## 7. Tích hợp Spring Boot: khai báo encoder, reader và password updater

Trong ứng dụng Spring Boot Servlet dùng username/password, ví dụ cấu hình sau là **mã minh họa tích hợp**, không phải chương trình Java độc lập: nó cần repository/service, transaction, Spring configuration, các imports và `SecurityFilterChain` đầy đủ.

~~~java
@Configuration
class AuthenticationBeans {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    DaoAuthenticationProvider daoAuthenticationProvider(
            UserDetailsService userDetailsService,
            UserDetailsPasswordService passwordUpdater,
            PasswordEncoder passwordEncoder) {

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(userDetailsService);
        provider.setPasswordEncoder(passwordEncoder);
        provider.setUserDetailsPasswordService(passwordUpdater);
        return provider;
    }
}
~~~

Điều quan trọng:

- Bean `passwordEncoder` phải là **cùng policy** được dùng để tạo password lúc đăng ký, đổi password và kiểm tra lúc login.
- `userDetailsService` đọc dữ liệu từ kho tài khoản. Không trả nguyên JPA entity có quan hệ/phần dữ liệu nghiệp vụ lớn làm principal chỉ vì tiện.
- `passwordUpdater` phải là implementation thật của `UserDetailsPasswordService` và ghi dữ liệu vào đúng nguồn mà reader sẽ đọc lại.
- Provider phải được **đăng ký vào đúng AuthenticationManager/SecurityFilterChain** đang xử lý login. Có bean trong application context không chứng minh một filter khác đang dùng bean đó.
- Nếu hệ thống có nhiều manager, chain, provider hoặc dùng OAuth2/LDAP, không giả định hook nâng cấp của DAO provider chạy ở tất cả đường đăng nhập.

### Ví dụ service lưu hash trong database (phác thảo)

~~~java
// MÃ MINH HỌA kiến trúc, KHÔNG độc lập biên dịch.
// Giả định repository hỗ trợ so sánh passwordHash/version,
// và AuthUserDetails là projection UserDetails của ứng dụng.
@Service
public class DatabasePasswordUpdater implements UserDetailsPasswordService {

    private final AccountRepository accounts;

    public DatabasePasswordUpdater(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    @Transactional
    public UserDetails updatePassword(UserDetails user, String encodedNew) {
        AuthUserDetails current = (AuthUserDetails) user;

        int updated = accounts.updatePasswordIfVersionMatches(
                current.userId(),
                current.tenantId(),
                current.passwordVersion(),
                current.getPassword(),
                encodedNew);

        if (updated != 1) {
            throw new IllegalStateException(
                    "Password changed concurrently; reload required");
        }

        return current.withPasswordAndVersion(
                encodedNew, current.passwordVersion() + 1);
    }
}
~~~

Trong ví dụ này, `AccountRepository`, `AuthUserDetails` và method `withPasswordAndVersion` là **abstractions do dự án tự định nghĩa**, không phải API có sẵn trong Spring Security. Cách ném exception khi conflict là một lựa chọn bảo thủ; sản phẩm cần định nghĩa cách ghi audit, retry, yêu cầu reauthentication và mapping lỗi công khai phù hợp, tránh lộ password/version.

**Không sử dụng `updateUser` ghi đè cả entity từ dữ liệu cũ.** Provider quan tâm đến password hash, còn authorities/trạng thái/tenant có thể đã thay đổi bởi giao dịch khác. Update chuyên biệt nên **chỉ đổi cột password hash và password version**, không chạm quyền và cờ khóa.

## 8. SQL cập nhật có điều kiện để tránh khôi phục mật khẩu cũ

### 8.1. Race condition rất dễ bỏ sót

Hai request cùng lúc:

~~~text
Request A: user login bằng password cũ
   |
   +-- đọc hash v7 -> matches(rawOld, v7) = true
   |
   +-- bắt đầu tính hash mạnh hơn từ rawOld
                                Request B: user reset password
                                   |
                                   +-- xác minh recovery
                                   +-- ghi hash mới của rawNew, version v8
   |
   +-- A ghi đè hash v7-upgraded từ rawOld (nếu UPDATE vô điều kiện)
   |
   v
Password đã reset bị vô tình thay ngược lại password cũ!
~~~

Đây không chỉ là vấn đề consistency thông thường mà có thể là **lỗ hổng bảo mật**: người dùng vừa reset password để ứng phó tài khoản bị chiếm nhưng request login cũ ghi đè nó.

### 8.2. Compare-and-swap (CAS) trên phiên bản/hash

Giả sử bảng `accounts` có `id`, `tenant_id`, `password_hash`, `password_version`. Câu SQL minh họa:

~~~sql
UPDATE accounts
SET password_hash = :newHash,
    password_version = password_version + 1
WHERE id = :userId
  AND tenant_id = :tenantId
  AND password_version = :expectedVersion
  AND password_hash = :expectedOldHash;
~~~

Chỉ khi **số dòng bị ảnh hưởng = 1** mới xác nhận update. Nếu `0`, có thể user bị xóa/đổi tenant, mật khẩu đã reset hoặc có một cuộc đua khác. Không thử `UPDATE accounts SET password_hash = :newHash WHERE id = ...` để “chắc chắn thành công”, vì nó loại bỏ bảo vệ cạnh tranh.

**Kiểm soát nguyên tử:** `password_version` và hash phải được đổi cùng một transaction. Các thao tác thay password khác (self-service change, admin reset, revoke vì compromise) cũng cần tăng version hoặc một security stamp tương đương, để kiểm soát stale operations.

**Số phiên bản và cache:** Sau commit, invalidation `UserDetails` cache phải hoạt động; nếu có replica lag hoặc stale cache repopulation, cân nhắc đọc primary/version fencing. Không để credential cache chứa cùng mutable `UserDetails` bị `eraseCredentials` làm mất hash.

### 8.3. Một conflict nên dẫn đến kết quả gì?

Không có một cách xử lý đúng cho mọi ứng dụng:

- **Chính sách nghiêm:** từ chối phiên login hiện tại, yêu cầu xác thực lại bằng password mới. Phù hợp khi vừa có reset/thu hồi tài khoản quan trọng.
- **Chính sách có kiểm tra lại:** tải bản account mới, xác minh lại raw password của request và các trạng thái/authorities mới, rồi quyết định có tiếp tục không. **Không** tái ghi hash cũ theo vòng retry vô điều kiện.
- **Chính sách chấp nhận không nâng cấp:** chỉ khi chứng minh không có xung đột bảo mật (ví dụ một request khác đã nâng đúng cùng password/policy) và app có đủ dữ liệu đánh giá; cần audit/race tests.

Với implementation `UserDetailsPasswordService` có hợp đồng đơn giản, lỗi ghi có thể làm luồng login thất bại hoặc phát sinh lỗi nội bộ tùy provider/filter. Đừng lặng lẽ “return user” sau khi database write thất bại rồi báo “hash đã nâng cấp”. Phải biết tính nhất quán/độ ưu tiên bảo mật của nghiệp vụ.

## 9. UserDetailsPasswordService khác chức năng đổi mật khẩu thông thường

### 9.1. Rehash-on-login

- **Tác nhân:** xác thực username/password thành công.
- **Raw password:** vừa được request gửi và provider kiểm tra.
- **Ngữ nghĩa:** **giữ nguyên mật khẩu mà người dùng biết**, chỉ thay cách lưu bằng hash an toàn hơn.
- **Đích:** account đã được `UserDetailsService`/provider xác minh.
- **Hook:** `UserDetailsPasswordService.updatePassword(user, encodedNew)`.
- **Trải nghiệm:** người dùng thường không phải biết có migration.

### 9.2. User tự đổi password

- **Tác nhân:** người dùng đang đăng nhập và yêu cầu đổi mật khẩu từ rawOld sang rawNew.
- **Bảo vệ:** xác thực lại oldPassword, MFA/step-up nếu cần, kiểm tra password policy, chống reuse, CSRF/cookie session, audit.
- **Giá trị lưu:** hash được tạo từ **mật khẩu mới**, không phải rawOld.
- **Interface:** tùy app, có thể dùng `UserDetailsManager.changePassword(oldPassword, encodedNew)` hoặc service nghiệp vụ.
- **Session/token:** có thể cần invalidate các session khác, revoke refresh token theo chính sách.

### 9.3. Reset vì quên/compromise

- **Tác nhân:** luồng recovery bằng token one-time/verified ownership hoặc admin được authorize.
- **Không yêu cầu:** biết password cũ.
- **Yêu cầu:** xác minh quyền khôi phục, TTL, chống abuse, audit, session/refresh token revocation.
- **Vấn đề:** bảo vệ chống race với rehash-on-login, dùng version/CAS và chính sách thu hồi mạnh khi account bị chiếm.

| Tiêu chí | Rehash-on-login | Change password | Reset password |
| --- | --- | --- | --- |
| Raw password dùng để encode | **Raw đã đăng nhập thành công** | **Raw mới do user chọn** | **Raw mới sau recovery** |
| Người dùng đổi bí mật đăng nhập? | **Không** | **Có** | **Có** |
| Cần old password đúng? | Đã được kiểm chứng khi login | Thường cần reauth | Không, nhưng cần bằng chứng recovery |
| Ghi vào kho | `UserDetailsPasswordService` | `UserDetailsManager`/app service | Recovery service |
| Bắt buộc quản lý session/token? | Theo risk/policy | Theo risk/policy | Nên có quy trình thu hồi rõ ràng |
| Cần tránh stale overwrite? | **Rất cần** | **Rất cần** | **Rất cần** |

Đừng đổi logic `updatePassword` thành “tự đổi mật khẩu” chỉ vì tên method giống nhau. Đây là một **hook nội bộ của provider**, không phải API public để client tự yêu cầu thay password.

## 10. Tương tác với các loại PasswordEncoder và chính sách migrate

### 10.1. Trường hợp thường gặp

| Dữ liệu đang lưu | Encoder đang dùng | Kết quả khi đăng nhập hợp lệ và updater đã gắn |
| --- | --- | --- |
| `{noop}legacy` | Delegating factory mặc định bcrypt | Có thể match, báo cần upgrade, lưu `{bcrypt}...` |
| `{pbkdf2}...` định dạng được map | Delegating có PBKDF2 legacy + bcrypt mặc định | Match nếu payload hợp lệ, sau đó rehash sang bcrypt |
| `{bcrypt}...` với cost đúng cấu hình | BCrypt/Delegating cùng policy | `upgradeEncoding` thường false, không update |
| `{bcrypt}...` cost thấp hơn strength mới | BCrypt được cấu hình strength cao hơn | Có thể báo true, rehash với cost mới |
| Không có `{id}`, format không nhận diện | Delegating không fallback | Thường không match/throw, **không tự nâng cấp** |
| `{unknown}...` chưa được map | Delegating không hỗ trợ ID | Không được ép chấp nhận hoặc bỏ qua xác minh |
| Account dùng external IdP/LDAP | Provider khác DAO username/password | Không mặc nhiên chạy hook này |

Các hàng ở trên phụ thuộc chính xác configuration/format và implementation; cần kiểm tra Spring Security version, mapping và encoder hiện hành trong ứng dụng thật.

### 10.2. Khi tăng bcrypt strength

Ví dụ đang lưu `{bcrypt}` với cost 10, rồi bạn cấu hình encoder bcrypt strength 12. BCrypt hash cũ chứa cost trong payload và vẫn có thể được xác minh; `upgradeEncoding` của BCrypt có thể trả true nếu cost lưu thấp hơn chuẩn mới.

Khi nâng cost, **không nhất thiết phải đổi prefix ID** từ `bcrypt` sang ID mới. Nhưng các node cũ/mới có cấu hình khác trong rolling deployment cần hiểu dữ liệu và hành vi nâng cấp; không tạo vòng rehash không cần thiết. Benchmark cost CPU dưới tải login, tránh để rehash-on-login làm đột biến latency/DoS tại thời điểm nhiều người dùng truy cập.

### 10.3. Thay đổi thuật toán

Nếu chuyển sang Argon2/PBKDF2/scrypt, cấu hình `DelegatingPasswordEncoder` với `idForEncode` mới và map chứa các encoder cũ **trước khi** ghi hash mới. Các node trong cụm phải có khả năng **đọc định dạng mới** trong giai đoạn chuyển đổi.

Chiến lược phổ biến là **dual-read, single-write**:

1. Deploy khả năng `matches` cả ID cũ và mới lên tất cả node.
2. Sau khi xác minh rollout, chuyển `idForEncode` sang ID mới.
3. Khi users login thành công, hook dần lưu hash mới.
4. Đo coverage; account chưa quay lại có thể cần password reset theo deadline.
5. Sau khi hoàn tất migration và hết cửa sổ rollback, có thể loại bỏ encoder legacy nếu policy cho phép.

**Không** loại bỏ mapping cũ trước khi các account cũ còn sử dụng nó, nếu bạn chưa có kế hoạch reset. **Không** bật `NoOpPasswordEncoder` làm policy tạo mật khẩu mới.

## 11. Cache UserDetails và credential erasure: một bẫy khó thấy

`ProviderManager` mặc định thực hiện `eraseCredentials()` trên kết quả xác thực nếu đối tượng hỗ trợ `CredentialsContainer`. Mục tiêu là xóa raw credentials và phần nhạy cảm khỏi authentication/session sau khi login.

Nhưng nếu object `UserDetails` vừa được đưa vào principal **cũng chính là object nằm trong cache**, thao tác xóa credential có thể khiến bản cache bị mất password hash. Sau đó login lần hai bằng raw password hợp lệ không còn đối chiếu được.

~~~text
Cache<UserDetails> giữ object U(passwordHash)
                       |
                       +--> DaoAuthenticationProvider dùng U
                                  |
                                  +--> Authentication.principal = U
                                  |
                                  v
                       ProviderManager.eraseCredentials()
                                  |
                                  v
                       U.password = null
                                  |
                                  v
                       Cache cũng giữ U(password=null)
~~~

**Trong quá trình nâng cấp** còn có rủi ro cache giữ hash cũ:

- DB đã nâng hash, cache có thể vẫn chứa hash cũ và cờ/trạng thái cũ.
- Một request login khác có thể tải bản hash cũ từ cache và kích hoạt update lần hai hoặc tạo cuộc đua với password reset.
- Nếu updater trả về chính object cache rồi provider xóa credential, hash trong cache có thể thành null.
- Distributed cache có thể có stale copies ở node khác ngay cả khi một node đã update database.

**Hướng xử lý:** Trả `UserDetails` mới tách khỏi cache object, evict hoặc version-fence cache sau commit, thiết kế TTL và transaction. Trong demo, loader/updater đều trả bản sao `User` mới để tránh mất hash trong store. Không tắt toàn bộ `eraseCredentialsAfterAuthentication` chỉ để “chữa” cache mà chưa đánh giá lại việc raw credentials lưu lâu trong memory/session.

## 12. Cách lưu hash trong JDBC/JPA/LDAP

### JDBC/JPA

Với bảng tài khoản tự quản:

- Hash là dữ liệu một chiều được sinh bởi `PasswordEncoder`, ví dụ có tiền tố `{bcrypt}`.
- Column phải đủ dài cho mọi định dạng bạn dự kiến hỗ trợ, tránh lưu hash bị cắt. `VARCHAR(255)` chỉ là một gợi ý thường gặp; chọn theo định dạng, schema và tương lai.
- Kho phải đảm bảo `UserDetailsService` đọc **đúng giá trị** vừa ghi.
- Sử dụng ID ổn định và tenant scope được xác minh để update; tránh dùng username hiển thị có thể đổi giữa lúc login và commit.
- Cần transaction, version/CAS, conflict handling và audit; không ghi raw password/hash vào log.
- Nếu dùng JPA entity có optimistic locking (`@Version`), hãy kiểm tra semantics: cập nhật một entity cũ không được ghi đè các trường roles/flags đã thay đổi; update chuyên biệt theo password version có thể phù hợp hơn.
- Nếu database đọc từ replica, phải xử lý replication lag để không xác thực/rehash lại theo snapshot cũ.

### LDAP hoặc IdP ngoài

Không giả định LDAP/IdP hỗ trợ đọc hash ra ngoài rồi write theo semantics tương tự JDBC. Một external identity provider có thể không cho ứng dụng truy cập raw hash hoặc không cho đổi mật khẩu qua `UserDetailsPasswordService`. Nếu đang dùng LDAP bind hoặc OIDC, đường xác thực chính thường **khác DaoAuthenticationProvider đọc password hash cục bộ**, nên không tự động có rehash-on-login như bài này.

Tài khoản domain nội bộ có thể lưu thêm mật khẩu local cho một flow riêng; phải phân định rõ nguồn sự thật và tránh “copy mật khẩu” từ IdP mà không có quyền/thiết kế bảo mật.

## 13. Triệu chứng, nguyên nhân và cách gỡ

| Triệu chứng | Nguyên nhân có khả năng | Hướng kiểm tra |
| --- | --- | --- |
| Login đúng, hash `{noop}` vẫn còn | Chưa gắn `UserDetailsPasswordService` hoặc provider khác đang xử lý | Kiểm tra provider đang dùng, cấu hình `setUserDetailsPasswordService`, kho readback |
| `upgradeEncoding` true nhưng không thấy UPDATE | Chỉ gọi encoder trực tiếp, chưa có hook ghi, lỗi transaction hoặc bean không được dùng | Kiểm tra hook, SQL affected row, commit và lỗi runtime |
| Password mới đăng nhập không được sau update | Double-encode `newPassword` hoặc hash bị cắt/format sai | Xác nhận `newPassword` đã encode, không encode thêm, DB giữ nguyên chuỗi |
| Hash cũ không có prefix `{id}` | Delegating không biết chọn encoder | Migrate metadata đúng algorithm hoặc reset password, không fallback tùy tiện |
| Unknown ID ném exception | Node chưa biết mapping, rollout chưa đồng bộ | Deploy dual-read, kiểm tra version/map và dữ liệu đã lưu |
| Lần đầu login được, lần hai thất bại với cache | Credential erasure làm null hash của shared object | Copy `UserDetails`, cache invalidation và test login lặp lại |
| Sau reset password, mật khẩu cũ hoạt động trở lại | Rehash-on-login ghi đè password mới từ request cũ | CAS/password version/transaction và conflict policy |
| Role/locked flag trở lại trạng thái cũ | Update toàn bộ entity từ snapshot cũ | Cập nhật riêng password hash/version, bảo toàn account state |
| CPU/latency login tăng vọt sau rollout | Đổi algorithm/cost tạo rehash hàng loạt | Benchmark, quan sát SLO, capacity, điều chỉnh rollout/rate limit |
| Không có hash upgrade cho JWT login | DAO username/password không được gọi | Xem đúng authentication mechanism; không áp công cụ sai giao thức |
| Login fail khi account bị khóa nhưng hash không đổi | Đây là behavior đúng | Không rehash từ request không pass account checks |
| Adapter update trả null | Vi phạm contract trả `UserDetails` | Trả object hợp lệ có password hash mới, test integration |
| Migrate thiếu tenant scope | Update nhầm tài khoản cùng username của tenant khác | Dùng stable userId + verified tenantId |
| Hash vẫn yếu cho users vắng mặt lâu | Rehash-on-login chỉ tác động người quay lại | Lập deadline reset và retire encoder cũ |
| Exception chi tiết xuất hiện trong response | Nội bộ đang lộ lý do/format password | Public error generic, audit an toàn |

## 14. Kiểm thử có ý nghĩa

### Unit: encoder

- `matches(raw, storedLegacy)` đúng với định dạng legacy bạn **thực sự** hỗ trợ.
- `upgradeEncoding(storedLegacy)` true; `upgradeEncoding(newHash)` false khi cùng policy/cost.
- `encode(raw)` tạo định dạng mới và `matches(raw, encode(raw))` true.
- ID thiếu/không được map phải được xử lý đúng chính sách, không tự fallback sang plaintext.
- PasswordEncoder không log raw/hash và không tạo hash mới bằng digest nhanh.

### Integration: provider + password updater

1. Tạo account với hash legacy, password đúng, account enabled/unlocked.
2. Login sai password: không gọi `updatePassword`, hash không đổi, không tạo authenticated result.
3. Login đúng: gọi `updatePassword` một lần, hash mới được lưu, khớp raw password, retained authorities/flags đúng.
4. Login tiếp: không update lại nếu hash đã đạt policy.
5. Không gắn updater: login có thể thành công nhưng hash không tự lưu lại.
6. Account disabled/locked/expired: không rehash và không được xác thực.
7. Updater ném lỗi/DB timeout: không báo thành công giả; thực hiện failure policy.
8. Reset password song song với rehash: hash mới sau reset không bị thay bởi hash của old password.
9. Cache user & credentials erasure: login nhiều lần vẫn đúng, cache không mất hash và invalidation có hiệu lực.
10. Multiple SecurityFilterChain/AuthenticationManager: xác minh **đúng provider** được gọi.
11. Multiple nodes: triển khai hỗ trợ ID mới trên toàn cụm trước khi tạo hash mới; replica lag không gây sai.
12. Kiểm tra SQL affected row = 1 và `password_version` tăng đúng.

### Vận hành

- Metric số `upgradeEncoding == true` và `updatePassword` thành công/thất bại, theo algorithm ID không kèm password hash.
- Tỉ lệ account còn hash legacy, tiến độ nâng cấp, user vắng mặt lâu, số lần reset bắt buộc.
- p95/p99 latency login và CPU/memory của encoder khi workload tăng.
- Số conflict CAS và khả năng rollback mà không tái kích hoạt password cũ.
- Audit tối thiểu: accountId nội bộ, lý do upgrade, encoder-id trước/sau, version, request ID (không ghi credential).
- Test bí mật ở mọi môi trường: stdout/log không in raw password, encoded hash, session cookie và bearer tokens.

**Test qua luồng login thực** (`SecurityFilterChain`/`AuthenticationManager`), không chỉ unit-test một bean service. Nếu `DaoAuthenticationProvider` được khởi tạo nhưng filter thực chạy provider khác, migration sẽ không kích hoạt.

## 15. Checklist thiết kế trước production

1. Đã xác định **nguồn lưu hash chính**, policy algorithm, cost và ID của các phiên bản cũ/mới.
2. `PasswordEncoder` đang dùng ở **đăng ký, đổi password và login** có mapping tương thích và policy tạo mới thống nhất.
3. Có triển khai `UserDetailsPasswordService` ghi đúng **encoded hash**, không double-encode.
4. Đã cấu hình password service trên **DaoAuthenticationProvider thực tế** và đúng chain/manager.
5. Trạng thái locked, disabled, expired, credentials expired và compromised password vẫn được kiểm tra; failure không rehash.
6. Không phụ thuộc vào việc đọc `principal.getPassword()` sau login; đọc lại kho để kiểm chứng.
7. Cập nhật hash dùng **transaction + CAS/version** để không ghi đè reset password/đổi password concurrent.
8. Adapter chỉ cập nhật hash và metadata, không overwrite role/tenant/status/domain profile.
9. Cache `UserDetails` invalidated sau commit, principal không chia sẻ mutable credential container với cache.
10. Khoá tài khoản/đổi password/incident có policy session và token revocation riêng; không trộn với rehash-on-login.
11. Cột dữ liệu đủ dài và không cắt tiền tố `{id}`, salt, cost và payload.
12. Rolling deploy: tất cả node đọc được format mới **trước khi** bất kỳ node nào ghi format mới.
13. Audit, metric, rollback, deadline xử lý account legacy và reset cho user không quay lại được định nghĩa.
14. Test tốc độ encode/matches dưới tải thật; không đẩy cost vượt tài nguyên và tạo DoS.
15. Không log hash/raw password, không lộ chi tiết thuật toán hoặc trạng thái account trong lỗi login công khai.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao Spring Security cần `UserDetailsPasswordService` nếu đã có `PasswordEncoder`?  
**Trả lời:** Encoder chỉ tạo/kiểm tra hash và đánh giá cần upgrade; nó không biết lưu vào database nào. Password service cung cấp thao tác cập nhật trong kho account.

**Câu 2.** `updatePassword(user, newPassword)` nhận raw hay encoded password?  
**Trả lời:** **Encoded password** do encoder tạo, không phải raw. Không encode một lần nữa trong implementation.

**Câu 3.** `upgradeEncoding("{noop}legacy")` true. Có được cập nhật hash ngay trước khi kiểm tra mật khẩu không?  
**Trả lời:** Không. Provider phải xác thực raw password và trạng thái account trước; chỉ rehash sau khi credential hợp lệ.

**Câu 4.** Login với `{noop}` thành công nhưng DB vẫn có `{noop}`. Có mâu thuẫn không?  
**Trả lời:** Không. Có thể đang dùng encoder hiểu legacy nhưng chưa cấu hình `UserDetailsPasswordService` hoặc filter đi qua provider khác.

**Câu 5.** Vì sao return `UserDetails` mới có ích?  
**Trả lời:** Contract yêu cầu object đã cập nhật; đồng thời có thể tránh dùng chung mutable principal với cache/store làm `eraseCredentials` xóa nhầm hash.

**Câu 6.** Hai request login và password reset chạy đồng thời; vì sao UPDATE vô điều kiện nguy hiểm?  
**Trả lời:** Rehash raw password cũ có thể ghi đè hash mới sau reset, làm password cũ sống lại. Cần CAS/version và conflict policy.

**Câu 7.** Mọi user có được nâng hash ngay sau khi deploy encoder mới không?  
**Trả lời:** Không. Chỉ các user đăng nhập qua luồng có hook và đủ điều kiện mới được nâng; user vắng mặt có thể cần reset.

**Câu 8.** Có thể dùng `UserDetailsManager.changePassword` thay hoàn toàn cho hook này không?  
**Trả lời:** Không nên đánh đồng. `changePassword` thuộc luồng người dùng đổi mật khẩu của chính họ; `updatePassword` là hook cập nhật **hash của mật khẩu đã xác minh** sau login.

**Câu 9.** Hash bcrypt đã có ID `{bcrypt}` có thể vẫn cần nâng cấp không?  
**Trả lời:** Có. Khi work factor thấp hơn cấu hình mới, `BCryptPasswordEncoder.upgradeEncoding` có thể yêu cầu rehash dù ID không đổi.

**Câu 10.** Sau rehash cần logout tất cả session/JWT không?  
**Trả lời:** Không có quy tắc bắt buộc từ hook. Rehash chỉ thay cách lưu cùng mật khẩu; session/token revocation là policy riêng. Nếu có nghi ngờ compromise/reset thì yêu cầu thu hồi khác.

## 17. Tài liệu tham khảo

- [Spring Security 6.5 – DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): `UserDetailsService`, `PasswordEncoder` và luồng xác thực username/password.
- [DaoAuthenticationProvider API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html): `setUserDetailsPasswordService`, `createSuccessAuthentication` và cấu hình password encoder.
- [UserDetailsPasswordService API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html): phương thức `updatePassword(UserDetails,String)` và định nghĩa “encoded password”.
- [InMemoryUserDetailsManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/provisioning/InMemoryUserDetailsManager.html): implementation vừa hỗ trợ `UserDetailsService` vừa hỗ trợ `UserDetailsPasswordService` cho demo/test.
- [Spring Security 6.5 – Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): `DelegatingPasswordEncoder`, format `{id}encodedPassword`, adaptive hashing và work factor.
- [PasswordEncoder API 6.5](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/PasswordEncoder.html): `encode`, `matches`, `upgradeEncoding`.
- [Spring Security – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `ProviderManager` và bảo vệ credentials.
- [OWASP – Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): password hashing, work factor, legacy migration và nâng cấp thuật toán.

**Ghi nhớ:** Một chu trình rehash-on-login đáng tin cậy phải có **xác minh password thành công → `upgradeEncoding` báo cần nâng cấp → `encode(raw hợp lệ)` → `UserDetailsPasswordService.updatePassword(user, encodedNew)` → lưu có điều kiện/commit và vô hiệu cache thích hợp**. Nâng hash không đổi mật khẩu người dùng; điều nguy hiểm nhất là nhầm raw/encoded, chưa gắn đúng updater hoặc ghi đè mật khẩu mới hơn do race condition.
