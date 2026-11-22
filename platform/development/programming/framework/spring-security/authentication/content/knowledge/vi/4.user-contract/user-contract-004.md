# InMemoryUserDetailsManager cho ví dụ và kiểm thử

## 1. Vì sao Spring Security có kho người dùng trong bộ nhớ?

`InMemoryUserDetailsManager` là một triển khai **không bền vững (non-persistent)** của `UserDetailsManager` trong Spring Security. Thay vì đọc tài khoản từ bảng SQL, LDAP hoặc hệ thống danh tính bên ngoài, nó giữ thông tin người dùng trong bộ nhớ của tiến trình ứng dụng. Công cụ này đặc biệt phù hợp với **ví dụ học tập, ứng dụng mẫu, bản thử nghiệm cục bộ và các bài test cần một kho tài khoản có thể kiểm soát**.

Điều quan trọng là hiểu đúng trách nhiệm:

- `InMemoryUserDetailsManager` **lưu, tìm và quản lý `UserDetails`**: username, mật khẩu đã mã hóa một chiều, trạng thái tài khoản và danh sách authorities.
- `DaoAuthenticationProvider` **xác thực username/password**: tải `UserDetails` qua manager và gọi `PasswordEncoder.matches(...)`, đồng thời kiểm tra trạng thái account.
- `AuthenticationManager` (thường là `ProviderManager`) **điều phối** lời gọi provider và trả `Authentication` đã xác thực hoặc báo thất bại.
- `SecurityFilterChain`/các filter bảo mật trong ứng dụng web **nhận request, thiết lập `SecurityContext` và áp dụng chính sách truy cập**.

Vì vậy, thêm một `InMemoryUserDetailsManager` không đồng nghĩa tự động có controller đăng nhập, API đăng ký hoặc session HTTP. Nó là **một nguồn tài khoản cụ thể**, tham gia vào luồng xác thực khi ứng dụng cấu hình những thành phần thích hợp.

Mục tiêu của bài này là dùng đúng manager đó cho **các ví dụ và kiểm thử có thể lặp lại**, phân biệt kiểm thử kho người dùng với kiểm thử quá trình xác thực thật, đồng thời biết khi nào không nên sử dụng nó.

## 2. Các hợp đồng liên quan

Quan hệ kiểu dữ liệu:

```text
UserDetailsService
  └── UserDetailsManager extends UserDetailsService
        ├── InMemoryUserDetailsManager
        ├── JdbcUserDetailsManager
        └── các triển khai khác

InMemoryUserDetailsManager
  ├── loadUserByUsername(username)
  ├── userExists(username)
  ├── createUser(user)
  ├── updateUser(user)
  ├── deleteUser(username)
  ├── changePassword(oldPassword, newPassword)
  └── updatePassword(user, encodedNewPassword)
       (theo hợp đồng UserDetailsPasswordService)
```

Trong Spring Security 6.5.11, `InMemoryUserDetailsManager` triển khai cả `UserDetailsManager` và `UserDetailsPasswordService`. Nó hỗ trợ khởi tạo bằng **mảng `UserDetails`**, `Collection<UserDetails>`, `Properties` hoặc constructor rỗng.

Các thao tác quan trọng:

| API | Vai trò | Điều cần biết trong test |
| --- | --- | --- |
| `new InMemoryUserDetailsManager(users...)` | Nạp một số tài khoản mẫu khi tạo đối tượng. | Tạo fixture ngắn, kiểm soát được dữ liệu ban đầu. |
| `loadUserByUsername("lan")` | Lấy `UserDetails` theo username; không tìm thấy thì ném `UsernameNotFoundException`. | Chỉ kiểm tra tải dữ liệu, **không tự xác thực mật khẩu**. |
| `userExists("lan")` | Kiểm tra manager đang có user hay không. | Không suy ra được user có đăng nhập được hay không. |
| `createUser(user)` | Thêm user trong bộ nhớ hiện tại. | Chỉ dùng dữ liệu thử nghiệm đã chuẩn bị. |
| `updateUser(user)` | Thay thông tin user (quyền, cờ enabled, hash…). | Có thể mô phỏng account bị khóa/vô hiệu hóa. |
| `deleteUser("lan")` | Xóa user khỏi store. | Xác nhận user không còn được manager tìm thấy. |
| `updatePassword(user, encodedPassword)` | Thay chuỗi mật khẩu **đã mã hóa** cho user cụ thể. | Không truyền raw password vào tham số này. |
| `changePassword(old, new)` | API đổi mật khẩu cho chủ thể hiện hành theo cấu hình. | Có ngữ cảnh/manager và điều kiện xác thực; tránh dùng bừa trong test độc lập. |

**Ba hợp đồng khác nhau:** `UserDetailsService` chỉ **đọc** user; `UserDetailsManager` bổ sung **tạo/sửa/xóa**; `UserDetailsPasswordService` hỗ trợ cập nhật password hash. `InMemoryUserDetailsManager` hỗ trợ cả ba vai trò, nhưng chúng đều thao tác trên **bộ nhớ của instance đang sử dụng**.

### `UserDetails` chứa gì?

Một tài khoản điển hình được tạo bằng builder:

```java
UserDetails lan = User.withUsername("lan")
    .password(encoder.encode("DemoPass123!"))
    .roles("READER")
    .disabled(false)
    .build();
```

Bản ghi này cung cấp:

- `getUsername()` và `getPassword()` (giá trị password **đã mã hóa**, không nên lưu plaintext).
- `getAuthorities()`: builder `roles("READER")` tạo authority `ROLE_READER`.
- Các cờ `isEnabled()`, `isAccountNonLocked()`, `isAccountNonExpired()`, `isCredentialsNonExpired()` phục vụ kiểm tra tài khoản khi xác thực.

`User` của Spring Security là một triển khai `UserDetails` phổ biến. Nó không thay thế entity `Customer`/`Employee` của nghiệp vụ, cũng không đòi ứng dụng phải dùng Spring Data JPA.

## 3. Tại sao manager này phù hợp cho bài học và kiểm thử?

Một test tốt cần **đầu vào rõ ràng, kết quả có thể dự đoán và không phụ thuộc hệ thống bên ngoài**. Dùng kho in-memory giúp:

1. Tạo user có tên, quyền và trạng thái cụ thể ngay trong fixture; không cần tạo schema SQL hay LDAP.
2. Thực hiện kiểm tra `loadUserByUsername`, `userExists`, `createUser`, `updateUser`, `deleteUser` mà không chạm dữ liệu thật.
3. Kết hợp `DaoAuthenticationProvider` + `PasswordEncoder` để **kiểm tra đường xác thực username/password thực**, gồm mật khẩu sai hoặc tài khoản disabled.
4. Tạo một `InMemoryUserDetailsManager` **mới cho mỗi test**, tránh tình trạng test trước đã xóa/đổi quyền làm test sau sai.
5. Dùng trong bản demo Spring Boot khi mục tiêu là giải thích filter, role, 401/403 mà chưa cần xây database.

Đổi lại, mỗi lần ứng dụng khởi động lại và tạo manager mới, dữ liệu động trong RAM sẽ mất; các instance ứng dụng khác nhau không tự đồng bộ với nhau. Vì vậy **không dùng làm nguồn tài khoản bền vững cho môi trường vận hành nhiều instance**.

## 4. Ví dụ Java 17+ chạy độc lập: tạo user, xác thực, sửa và xóa

Ví dụ này dùng **Java 17+, Gradle và Spring Security 6.5.11**. Đây là chương trình console hoàn chỉnh, không cần Spring Boot hoặc web server. Nó thực hiện cả hai loại việc để làm rõ sự khác nhau:

- **Quản lý tài khoản** qua `InMemoryUserDetailsManager`.
- **Xác thực thật** qua `DaoAuthenticationProvider` và `ProviderManager`, dùng BCrypt để kiểm tra mật khẩu.

Cấu trúc dự án:

```text
memory-users-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/MemoryUsersDemo.java
    └── test/java/demo/InMemoryUsersTest.java
```

### 4.1. Cấu hình Gradle

`settings.gradle`:

```groovy
rootProject.name = 'memory-users-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

application {
    mainClass = 'demo.MemoryUsersDemo'
}

test {
    useJUnitPlatform()
}
```

Với dự án thật có Spring Boot dependency management, hãy để Boot quản lý phiên bản Security tương thích, tránh tự ép một số phiên bản khác nhau của các module Security. Các version cụ thể ở đây chỉ nhằm bảo đảm ví dụ console có một tổ hợp rõ ràng.

### 4.2. Chương trình `MemoryUsersDemo.java`

```java
package demo;

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
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public final class MemoryUsersDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();

        // Dữ liệu mẫu được băm trước khi nạp vào kho.
        UserDetails lan = User.withUsername("lan")
                .password(encoder.encode("DemoPass123!"))
                .roles("READER")
                .build();

        InMemoryUserDetailsManager store =
                new InMemoryUserDetailsManager(lan);

        System.out.println("lan.exists=" + store.userExists("lan"));
        System.out.println("missing.exists=" + store.userExists("missing"));

        UserDetails loaded = store.loadUserByUsername("lan");
        System.out.println("lan.name=" + loaded.getUsername());
        System.out.println("lan.hashMatches=" + encoder.matches(
                "DemoPass123!", loaded.getPassword()));
        System.out.println("lan.hashRejectsWrong=" + !encoder.matches(
                "wrong-password", loaded.getPassword()));

        // Chỉ khi manager/provider xác thực mới có Authentication đáng tin cậy.
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(store);
        provider.setPasswordEncoder(encoder);
        AuthenticationManager authenticationManager =
                new ProviderManager(provider);

        Authentication result = authenticationManager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "lan", "DemoPass123!"));

        System.out.println("login.authenticated=" + result.isAuthenticated());
        System.out.println("login.name=" + result.getName());
        System.out.println("login.reader=" + result.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .anyMatch("ROLE_READER"::equals));

        try {
            authenticationManager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "lan", "wrong-password"));
        } catch (BadCredentialsException ex) {
            System.out.println("wrongPassword=BadCredentialsException");
        }

        // Tạo một user mới trong cùng store.
        store.createUser(User.withUsername("mai")
                .password(encoder.encode("MaiPass123!"))
                .roles("EDITOR")
                .build());
        System.out.println("mai.exists=" + store.userExists("mai"));

        // Mô phỏng tài khoản bị vô hiệu hóa; giữ hash/role cũ.
        UserDetails mai = store.loadUserByUsername("mai");
        store.updateUser(User.withUserDetails(mai)
                .disabled(true)
                .build());

        System.out.println("mai.enabled="
                + store.loadUserByUsername("mai").isEnabled());

        try {
            authenticationManager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "mai", "MaiPass123!"));
        } catch (DisabledException ex) {
            System.out.println("disabledUser=DisabledException");
        }

        store.deleteUser("mai");
        System.out.println("mai.existsAfterDelete="
                + store.userExists("mai"));
    }
}
```

Trong terminal ở thư mục `memory-users-demo`, dùng JDK 17+ và Gradle/Gradle Wrapper tương thích:

```bash
gradle run --quiet
```

Các dòng do chương trình in ra theo thứ tự (không bao gồm log từ Gradle hoặc thư viện nếu có):

```text
lan.exists=true
missing.exists=false
lan.name=lan
lan.hashMatches=true
lan.hashRejectsWrong=true
login.authenticated=true
login.name=lan
login.reader=true
wrongPassword=BadCredentialsException
mai.exists=true
mai.enabled=false
disabledUser=DisabledException
mai.existsAfterDelete=false
```

### 4.3. Giải thích tại sao kết quả trên đúng

**`lan.exists` và `missing.exists`:** `userExists` chỉ hỏi xem có bản ghi trong manager. Nó không so mật khẩu và không tạo `Authentication`.

**`loadUserByUsername`:** trả `UserDetails` có password hash. `encoder.matches("DemoPass123!", storedHash)` trả true vì hash tương ứng; chuỗi sai không khớp. Không in hash/mật khẩu thô ra log.

**`login.authenticated=true`:** kết quả đến từ `ProviderManager`/`DaoAuthenticationProvider`. Provider thực sự so raw password với hash rồi xây authenticated token, bao gồm authorities từ `UserDetails`. `ROLE_READER` phát sinh từ `roles("READER")`.

**`wrongPassword`:** mật khẩu sai làm provider ném `BadCredentialsException` thay vì trả token đã xác thực.

**`createUser`, `updateUser`, `deleteUser`:** thay đổi bản ghi **trong instance store**. Khi `mai` bị disabled, `DaoAuthenticationProvider` từ chối dù password đúng; sau khi xóa, `userExists("mai")` là false.

**Một cảnh báo về đối tượng `Authentication`:** token `result` đã xác thực được tạo **trước** khi thay đổi tài khoản khác. Kết quả xác thực hoặc session đã tồn tại không nhất thiết tự cập nhật mọi thay đổi sau đó trong user store. Khi kiểm thử việc khóa/xóa account, cần xác định test đang kiểm tra **lần đăng nhập mới** hay **tác động tới phiên đã đăng nhập**, bởi hai hành vi khác nhau.

### 4.4. Vì sao không dùng `User.withDefaultPasswordEncoder()`?

Spring Security có builder tiện cho ví dụ đơn giản, nhưng `User.withDefaultPasswordEncoder()` được đánh dấu không an toàn cho production và đã deprecated trong API hiện hành. Trong bài này, tạo rõ bean/đối tượng `PasswordEncoder`, dùng `encoder.encode(...)` để lưu hash, rồi dùng **cùng loại encoder** cho provider. Cách đó giúp nhìn thấy ranh giới trách nhiệm và tránh tạo thói quen lưu password sai.

## 5. Kiểm thử JUnit 5: mỗi bài test có một store mới

Phần quan trọng của đề bài không chỉ là demo chạy một lần mà còn phải biết **tạo fixture an toàn cho kiểm thử tự động**. File tiếp theo có thể chạy với cấu hình Gradle ở trên.

`src/test/java/demo/InMemoryUsersTest.java`:

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

final class InMemoryUsersTest {

    private PasswordEncoder encoder;
    private InMemoryUserDetailsManager users;
    private AuthenticationManager authenticationManager;

    @BeforeEach
    void setUp() {
        // Không chia sẻ static store giữa các @Test.
        encoder = new BCryptPasswordEncoder();
        users = new InMemoryUserDetailsManager(
                User.withUsername("lan")
                        .password(encoder.encode("DemoPass123!"))
                        .roles("READER")
                        .build()
        );

        DaoAuthenticationProvider dao = new DaoAuthenticationProvider(users);
        dao.setPasswordEncoder(encoder);
        authenticationManager = new ProviderManager(dao);
    }

    @Test
    void loadsTheExpectedUserAndEncodedPassword() {
        UserDetails found = users.loadUserByUsername("lan");

        assertEquals("lan", found.getUsername());
        assertTrue(encoder.matches("DemoPass123!", found.getPassword()));
        assertFalse(encoder.matches("wrong", found.getPassword()));
        assertEquals("ROLE_READER",
                found.getAuthorities().iterator().next().getAuthority());
    }

    @Test
    void realProviderAcceptsCorrectCredentials() {
        Authentication verified = authenticationManager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "lan", "DemoPass123!"));

        assertTrue(verified.isAuthenticated());
        assertEquals("lan", verified.getName());
    }

    @Test
    void realProviderRejectsWrongPassword() {
        assertThrows(BadCredentialsException.class, () ->
                authenticationManager.authenticate(
                        UsernamePasswordAuthenticationToken.unauthenticated(
                                "lan", "wrong-password")));
    }

    @Test
    void disabledAccountCannotAuthenticate() {
        UserDetails before = users.loadUserByUsername("lan");
        users.updateUser(User.withUserDetails(before)
                .disabled(true)
                .build());

        assertFalse(users.loadUserByUsername("lan").isEnabled());

        assertThrows(DisabledException.class, () ->
                authenticationManager.authenticate(
                        UsernamePasswordAuthenticationToken.unauthenticated(
                                "lan", "DemoPass123!")));
    }

    @Test
    void createUpdateAndDeleteChangeOnlyThisFixture() {
        users.createUser(User.withUsername("mai")
                .password(encoder.encode("MaiPass123!"))
                .roles("EDITOR")
                .build());

        assertTrue(users.userExists("mai"));

        UserDetails before = users.loadUserByUsername("mai");
        users.updateUser(User.withUserDetails(before)
                .authorities("catalog:write")
                .build());

        assertEquals("catalog:write",
                users.loadUserByUsername("mai").getAuthorities()
                        .iterator().next().getAuthority());

        users.deleteUser("mai");
        assertFalse(users.userExists("mai"));
        assertThrows(UsernameNotFoundException.class,
                () -> users.loadUserByUsername("mai"));
    }
}
```

Chạy các test:

```bash
gradle test
```

**Kết quả kỳ vọng:** cả năm `@Test` đều pass và Gradle hoàn thành task `test` thành công; số dòng log, thời gian chạy và định dạng báo cáo phụ thuộc môi trường. Không cần kết nối DB hay HTTP server. Bài test thứ hai và thứ ba **thực sự gọi provider để kiểm chứng password**, vì vậy chúng kiểm tra một đường xác thực rõ ràng hơn chỉ gọi `loadUserByUsername`.

### Vì sao tạo fixture trong `@BeforeEach`?

- Mỗi test nhận **một manager và một `PasswordEncoder` riêng**.
- Test xóa `mai` không ảnh hưởng test load `lan`.
- Tài khoản bị disabled trong một test không làm test khác thất bại ngẫu nhiên.
- Không phụ thuộc thứ tự JUnit chạy các test.
- Không cần khôi phục cơ sở dữ liệu, rollback transaction hoặc làm sạch Redis.

Trong test có nhiều luồng hoặc chạy song song, vẫn phải quan tâm trạng thái chia sẻ nếu bạn cố ý dùng **chung một manager**. `@BeforeEach` giúp cô lập fixture theo instance test, nhưng không tự sửa một thiết kế test sử dụng static/global/shared Spring context và có các mutation cạnh tranh.

## 6. Dùng trong ứng dụng Spring Boot: cấu hình bean cho môi trường demo

Trong ứng dụng Spring Boot Servlet đã có `spring-boot-starter-web` và `spring-boot-starter-security`, có thể cấu hình `InMemoryUserDetailsManager` làm bean `UserDetailsService` hoặc bean theo đúng kiểu triển khai:

```java
// Trích đoạn @Configuration trong ứng dụng Spring Boot đã có dependencies;
// cần import @Bean, @Configuration, @Profile, User,
// PasswordEncoder, BCryptPasswordEncoder, InMemoryUserDetailsManager.
@Configuration
class DemoUsersConfig {

    @Bean
    @Profile("demo")
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    @Profile("demo")
    InMemoryUserDetailsManager demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("student")
                        .password(encoder.encode("DemoOnly123!"))
                        .roles("READER")
                        .build(),
                User.withUsername("mentor")
                        .password(encoder.encode("DemoAdmin123!"))
                        .roles("MENTOR")
                        .build()
        );
    }
}
```

Đây là **trích đoạn bean, chưa phải ứng dụng độc lập**. Cần lớp `@SpringBootApplication`, `SecurityFilterChain` phù hợp và các controller để chạy web. Ví dụ dùng `@Profile("demo")` để thể hiện rõ ràng môi trường demo; thực tế còn phải quản lý profile, secrets và cấu hình phát hành. Không bật profile demo trên hệ thống public chỉ vì ứng dụng đang gặp lỗi xác thực.

Với cấu hình username/password thông dụng, Spring Security có thể sử dụng `UserDetailsService` này cùng `DaoAuthenticationProvider`; nhưng cách ứng dụng dựng `AuthenticationManager` và chính sách HTTP phải được kiểm tra theo cấu hình dự án. **Tạo `InMemoryUserDetailsManager` không tự làm ra form login hay endpoint REST.**

### So sánh hai trạng thái

**Không có Bean nguồn người dùng tùy chỉnh:** trong một số cấu hình Spring Boot web có Spring Security, Boot tạo user mặc định phục vụ chạy thử nếu các điều kiện auto-configuration được đáp ứng.

**Có Bean `InMemoryUserDetailsManager`:** ứng dụng cung cấp nguồn tài khoản riêng; trường hợp này thường khiến cấu hình user mặc định của Boot nhường chỗ theo điều kiện auto-configuration. Tuy nhiên bean nguồn user và bean `SecurityFilterChain` là hai phần cấu hình riêng; đừng suy ra chỉ từ việc khai báo filter rằng Boot đã không còn tạo user mặc định.

Nếu ứng dụng có nhiều nguồn xác thực (DB + test users, LDAP + local, OAuth2/OIDC + password), cần quản lý rõ bean/provider nào được kích hoạt theo profile, qualifier và cách chọn `AuthenticationManager`. Không tạo username mặc định trùng user thật ngoài ý muốn.

## 7. Ba kiểu kiểm thử dễ nhầm: mock user, store thật và HTTP thật

Một kết quả test xanh có giá trị khi bạn biết **đường xử lý mà test đã đi qua**.

| Cách kiểm thử | Nguồn principal | Có thật sự kiểm tra password qua `DaoAuthenticationProvider`? | Phù hợp khi |
| --- | --- | --- | --- |
| `@WithMockUser` hoặc `MockMvc.with(user(...))` | Spring Security Test tạo principal/`Authentication` giả lập. | **Không.** Không yêu cầu user tồn tại trong store. | Test authorization, controller/method security cần user/role xác định. |
| `@WithUserDetails("lan")` | Spring Security Test tải `UserDetails` qua bean `UserDetailsService` có tên/qualifier phù hợp. | **Không tự kiểm tra raw password** qua login flow. | Test code phụ thuộc custom `UserDetails`, kiểm tra authority/principal đã nạp. |
| JUnit test gọi `AuthenticationManager.authenticate(...)` | Store thật và provider thật, như `InMemoryUsersTest`. | **Có.** | Test cấu hình username/password, encoder, account flags. |
| `MockMvc` gửi HTTP Basic hoặc form-login với filter chain thật | Request thực được xử lý qua Spring Security filter + provider theo cấu hình. | **Có thể có**, khi test kết nối đúng filter/manager/nguồn user thật. | Test toàn bộ HTTP authentication, 401/403, success/failure và quyền endpoint. |

### `@WithMockUser` không phụ thuộc `InMemoryUserDetailsManager`

Ví dụ minh họa trong một Spring test class có tích hợp Spring Security Test:

```java
@Test
@WithMockUser(username = "lan", roles = "READER")
void canOpenReaderEndpointAsMockedUser() throws Exception {
    mockMvc.perform(get("/documents"))
            .andExpect(status().isOk());
}
```

Đây là **đoạn trích**, yêu cầu `mockMvc` đã cấu hình Spring Security và controller `/documents` tồn tại. Nó **không** xác minh rằng `lan` có trong `InMemoryUserDetailsManager`, password lưu đúng hash hay provider từ chối password sai. `@WithMockUser` tạo principal cho test, không phải chạy quy trình đăng nhập.

### `@WithUserDetails` gọi bean `UserDetailsService`

```java
@Test
@WithUserDetails("lan")
void knowsThePrincipalFromTheConfiguredUserStore() {
    Authentication current =
            SecurityContextHolder.getContext().getAuthentication();

    assertEquals("lan", current.getName());
}
```

Đoạn trích này cần Spring Security Test integration, bean `UserDetailsService` có user `lan` và các import tương ứng. Nó nạp `UserDetails`, rồi thiết lập `SecurityContext` cho test. Nó **không bắt client nhập mật khẩu**. Đối với custom principal class, `@WithUserDetails` hữu ích hơn `@WithMockUser` vì principal đến từ service của ứng dụng.

### Khi cần test login HTTP

Trong ứng dụng Spring MVC có Spring Security FilterChain đã được tích hợp vào `MockMvc`, hãy gửi thông tin xác thực từ request:

```java
// Trích đoạn trong MockMvc test đã @Autowired MockMvc,
// có @SpringBootTest/@AutoConfigureMockMvc hoặc cấu hình tương đương.
// Cần static imports: get, httpBasic, status.
mockMvc.perform(get("/documents")
        .with(httpBasic("lan", "DemoPass123!")))
        .andExpect(status().isOk());

mockMvc.perform(get("/documents")
        .with(httpBasic("lan", "wrong-password")))
        .andExpect(status().isUnauthorized());
```

Kết quả phụ thuộc **HTTP Basic đã bật**, user/role được nạp, endpoint và rule phù hợp. Chỉ khi những điều kiện ấy đúng, bài test mới thực sự chứng minh đường xác thực web. Với `MockMvc` dùng `formLogin()`, phải chú ý URL login, CSRF và session; với server chạy thật, bảo đảm credentials đi qua HTTPS.

**Ghi nhớ:** một request với `.with(user("lan"))` không đi qua kiểm tra password như `.with(httpBasic("lan", "..."))` trong filter chain HTTP Basic. Cả hai hữu ích nhưng **trả lời những câu hỏi kiểm thử khác nhau**.

## 8. Những tình huống test nên có để tránh hiểu sai

### Test nguồn dữ liệu

- User được tạo có username, password hash, authorities và trạng thái đúng.
- Tải username không tồn tại ném `UsernameNotFoundException`.
- `userExists` thay đổi đúng sau `createUser`/`deleteUser`.
- `updateUser` cập nhật authorities/disabled đúng theo fixture.
- Nếu dùng `updatePassword`, truyền **hash mới đã encode** và kiểm tra bằng `encoder.matches(...)`.

### Test xác thực thật

- Password đúng tạo token đã xác thực và principal mong đợi.
- Password sai bị từ chối bằng `BadCredentialsException`.
- User disabled/locked/expired không được provider cho đăng nhập.
- Quyền sau xác thực đến từ `UserDetails`, không đến từ role client tự gửi.
- Không có `Authentication` thành công khi user không tồn tại; theo mặc định provider thường che thành `BadCredentialsException`.

### Test authorization

- Guest không được vào URL cần `authenticated()`.
- User có `ROLE_READER` truy cập tài nguyên reader được phép.
- User thiếu quyền bị chặn theo policy.
- Quyền sở hữu tài nguyên vẫn được kiểm tra ở tầng nghiệp vụ.
- Test bằng mock user chỉ chứng minh kiểm tra authorization trong test, không chứng minh kho user hoặc password encoder.

Những trường hợp trên là **danh mục gợi ý**, không bắt buộc thêm tất cả vào ví dụ nhỏ ở phần 5. Chọn test theo hành vi cần chứng minh thay vì viết test chỉ lặp lại implementation.

## 9. Mật khẩu, quyền và trạng thái: nguyên tắc an toàn ngay cả khi đang demo

### Mật khẩu demo có thể giả nhưng cơ chế kiểm tra nên thật

Không lưu mật khẩu plaintext vào `UserDetails.password` trong demo có dùng `DaoAuthenticationProvider` thực. Một mẫu phù hợp:

```java
PasswordEncoder encoder = new BCryptPasswordEncoder();
String storedHash = encoder.encode("DemoOnly123!");
UserDetails demoUser = User.withUsername("student")
    .password(storedHash)
    .roles("READER")
    .build();
```

Hash BCrypt thường khác nhau sau mỗi lần `encode` do salt; test đúng phải dùng `matches(raw, hash)`, **không** so hai hash bằng `equals`. Không đưa mật khẩu mẫu vào code production hoặc log request.

Nếu dùng `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, các hash được tạo thường có tiền tố `{bcrypt}`; nếu dùng trực tiếp `BCryptPasswordEncoder`, hash không có tiền tố đó. Đừng trộn dạng hash và encoder mà không kiểm tra định dạng.

### `roles` khác `authorities`

```java
User.withUsername("lan")
    .password(encodedPassword)
    .roles("READER")
    .build();
// authority: ROLE_READER

User.withUsername("mai")
    .password(encodedPassword)
    .authorities("document:write")
    .build();
// authority: document:write
```

Đoạn mã chỉ minh họa builder, `encodedPassword` phải là giá trị hợp lệ. `hasRole("READER")` theo quy ước mặc định kiểm tra `ROLE_READER`, còn `hasAuthority("document:write")` kiểm tra chính xác chuỗi đã cung cấp. Đừng gán `ROLE_ADMIN` vào mọi account test chỉ để làm mọi kiểm thử pass.

### Trạng thái tài khoản phải được test qua provider khi cần

Gọi `users.loadUserByUsername("lan").isEnabled()` cho biết dữ liệu fixture đúng. Nhưng để kết luận “user disabled không thể đăng nhập”, cần thử `AuthenticationManager.authenticate(...)` và xác minh kết quả bị từ chối. Không lẫn kiểm tra object và kiểm tra quyết định bảo mật.

### Quản lý vòng đời test

- Ưu tiên fixture tạo trong `@BeforeEach` và chỉ tồn tại trong test.
- Không dùng một manager có thể bị sửa chung bởi các test chạy song song khi không chủ đích.
- Không giữ mật khẩu demo trong biến global có vòng đời lâu hơn bài test.
- Nếu test sử dụng Spring ApplicationContext cache, việc sửa bean `InMemoryUserDetailsManager` có thể tồn tại sang bài test khác chia sẻ context; cô lập, tái tạo hoặc reset fixture theo thiết kế.
- Tránh tin vào thứ tự thực hiện JUnit và tránh test dựa vào dữ liệu do một test khác tạo.

## 10. Khi nào nên rời bỏ InMemoryUserDetailsManager?

`InMemoryUserDetailsManager` được tài liệu Spring Security mô tả là kho **không bền vững** dành chủ yếu cho **testing và demonstration**. Hãy cân nhắc chuyển sang database/directory/IdP nếu yêu cầu bao gồm:

- Dữ liệu tài khoản không mất khi restart hoặc scale ứng dụng nhiều instance.
- Quy trình đăng ký, khôi phục mật khẩu, khóa/mở tài khoản và lịch sử thay đổi.
- Audit, migration, quản lý quyền dài hạn hoặc quản lý danh tính tập trung.
- Đồng bộ với hệ thống nghiệp vụ/LDAP/OIDC/SSO.
- Thay đổi người dùng phải nhất quán qua nhiều phiên, nhiều server và nhiều lần deploy.

Có thể giữ interface `UserDetailsService` và thay implementation bằng adapter đọc DB/LDAP trong trường hợp username/password. Lớp authentication/provider có thể tiếp tục dùng nếu cơ chế không đổi; nhưng kiến trúc JWT/OIDC có thể cần một authentication flow khác. Đừng coi `InMemoryUserDetailsManager` là cơ sở dữ liệu production “đủ tốt nếu ít người dùng”: nó không có bảo đảm bền vững và quy trình quản trị danh tính tương ứng.

## 11. Các lỗi thường gặp

1. **“InMemoryUserDetailsManager tự kiểm tra mật khẩu.”** Không. Nó tải user, còn provider/encoder kiểm chứng credentials.
2. **“`loadUserByUsername` tìm được user là đã login.”** Không. Đây chỉ là dữ liệu phục vụ xác thực.
3. **“`@WithMockUser` chứng minh user có trong store.”** Không. Test này có thể pass dù manager rỗng.
4. **“`@WithUserDetails` xác thực mật khẩu người dùng.”** Không; nó nạp principal và thiết lập context cho test.
5. **“Test `userExists` đủ để kết luận tài khoản đăng nhập được.”** Không; user có thể disabled, locked hoặc mật khẩu không khớp.
6. **“Lưu plaintext cho nhanh vì chỉ là test.”** Có thể dẫn tới cấu hình không thực tế và lỗi khi dùng BCrypt/Delegating encoder; nên băm trong các ví dụ xác thực thật.
7. **“Dùng cùng một store mutable cho toàn bộ test suite.”** Dẫn tới phụ thuộc thứ tự và lỗi khi chạy song song; tạo fixture riêng.
8. **“Tắt kiểm tra bảo mật để test pass.”** Không sửa `hasRole` thành `permitAll` hay bỏ filter khỏi MockMvc nếu mục tiêu là test security.
9. **“Thay đổi user trong store là các session cũ tự bị thu hồi.”** Không chắc; session/context có thể giữ identity/authority từ lần xác thực trước.
10. **“Thêm bean `InMemoryUserDetailsManager` sẽ tự sinh login REST API.”** Không. Nó cung cấp nguồn account; login/filter/controller là phần khác.
11. **“Mọi ứng dụng Boot có spring-security đều tự có user demo mãi mãi.”** Điều kiện Boot auto-config khác nhau khi ứng dụng cung cấp bean xác thực hoặc dùng module OAuth2/Resource Server.
12. **“`changePassword` và `updatePassword` nhận input tương đương nhau.”** Hai API có hợp đồng/ngữ cảnh khác nhau; `updatePassword` nhận password **đã encode**.
13. **“`roles("ADMIN")` và `authorities("ADMIN")` giống nhau.”** `roles` thêm tiền tố `ROLE_` theo convention; `authorities` dùng đúng chuỗi.
14. **“Mất user sau restart là bug.”** Đây là đặc tính in-memory: dữ liệu không có storage bền vững.
15. **“Cấu hình profile demo có thể triển khai công khai.”** Một profile có tài khoản mẫu/credential mẫu phải được kiểm soát nghiêm ngặt, không cho phép vô tình kích hoạt trên production.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Có `InMemoryUserDetailsManager` chứa user `lan` và password hash. Vì sao gửi mật khẩu sai vẫn bị chặn?

**Đáp án:** Manager chỉ cung cấp `UserDetails`. `DaoAuthenticationProvider` dùng `PasswordEncoder.matches(...)` để so raw password với hash; nếu không khớp, quá trình xác thực thất bại.

**Câu 2.** Test dùng `@WithMockUser(username="lan")` pass nhưng `users.userExists("lan")` là false. Có mâu thuẫn không?

**Đáp án:** Không. `@WithMockUser` dựng principal/`SecurityContext` giả lập; test không bắt buộc user tồn tại trong kho.

**Câu 3.** Muốn kiểm tra `DaoAuthenticationProvider` từ chối tài khoản disabled thì nên làm thế nào?

**Đáp án:** Tạo user trong manager, cập nhật `disabled(true)` và gọi `AuthenticationManager.authenticate(...)` với mật khẩu đúng; xác minh ném `DisabledException`.

**Câu 4.** Một test sửa role `lan` sang `ROLE_ADMIN` khiến test khác pass sai. Nguyên nhân?

**Đáp án:** Các test chia sẻ mutable store hoặc cached Spring context. Tạo fixture mới cho từng test hoặc kiểm soát cô lập/reset rõ ràng.

**Câu 5.** Khi `deleteUser("lan")` đã chạy, user với session đang mở có bị logout ngay lập tức không?

**Đáp án:** Không được giả định như vậy. `deleteUser` chỉ xóa bản ghi khỏi store; hành vi session/revocation phụ thuộc cơ chế ngữ cảnh và chính sách phiên của ứng dụng.

**Câu 6.** Vì sao trong test dùng `encoder.matches(...)` thay vì tạo hash mới rồi so chuỗi?

**Đáp án:** BCrypt dùng salt ngẫu nhiên; hai lần `encode` của cùng password có thể cho hai hash khác nhau. `matches` là API kiểm chứng đúng.

**Câu 7.** Mục đích của `userExists` khác `loadUserByUsername` như thế nào?

**Đáp án:** `userExists` trả boolean cho câu hỏi có user hay không; `loadUserByUsername` trả `UserDetails` hoặc ném `UsernameNotFoundException`. Cả hai không tự đánh giá mật khẩu.

**Câu 8.** Khi nào cần dùng MockMvc với `httpBasic(...)` thay cho `@WithMockUser`?

**Đáp án:** Khi cần kiểm tra đường request HTTP qua filter chain và việc xác minh username/password thực, thay vì chỉ kiểm tra logic authorization với identity giả lập.

## 13. Tài liệu chính thức

- [Spring Security 6.5.11 – InMemoryUserDetailsManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/provisioning/InMemoryUserDetailsManager.html): constructor, `UserDetailsManager`, `UserDetailsPasswordService` và các thao tác quản lý user.
- [Spring Security – Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/): cấu hình user in-memory và cách liên kết với authentication.
- [Spring Security – UserDetailsService](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html): vai trò nguồn cung cấp thông tin user cho `DaoAuthenticationProvider`.
- [Spring Security 6.5.11 – DaoAuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html): `UserDetailsService` và `PasswordEncoder` trong xác thực thật.
- [Spring Security – Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser` và `@WithUserDetails`.
- [Spring Security – Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/): tích hợp MockMvc với security filters và request post-processors.
- [Spring Security 6.5.11 – UserDetails API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.html): xây tài khoản và các thuộc tính trạng thái.

**Kết luận:** `InMemoryUserDetailsManager` giúp xây kho tài khoản mẫu rõ ràng, thao tác linh hoạt và cô lập cho các bài test. Để kiểm thử password thật, kết hợp nó với `DaoAuthenticationProvider` và `PasswordEncoder`; để kiểm tra riêng quyền truy cập, dùng test mock đúng mục đích. Trong ứng dụng thật, hãy luôn phân biệt nguồn người dùng in-memory với một hệ quản trị danh tính bền vững và phân biệt dữ liệu user với một phiên đăng nhập đã được xác thực.