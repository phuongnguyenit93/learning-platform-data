# PasswordEncoder và kiểm tra mật khẩu mà không so khớp chuỗi hash cố định

## 1. Vì sao một bài kiểm thử mật khẩu có thể sai dù ứng dụng đúng?

Xét một đoạn kiểm thử có vẻ hợp lý:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();
String encoded = encoder.encode("correct-password");

// Cách kiểm thử không phù hợp:
assertThat(encoded).isEqualTo("$2a$10$motChuoiHashBCryptCoDinh...");
~~~

Bài test này phụ thuộc vào **một chuỗi hash cụ thể**. Với BCrypt, mỗi lần mã hóa một mật khẩu, bộ mã hóa thông thường tạo **salt ngẫu nhiên**. Do đó, hai lần gọi `encode("correct-password")` có thể tạo hai hash khác nhau dù cả hai đều hợp lệ và đều khớp cùng mật khẩu. Nếu so sánh nguyên chuỗi đầu ra với một giá trị cố định, test có thể thất bại chỉ vì salt thay đổi.

Điều ứng dụng thực sự cần xác nhận là: **mật khẩu do người dùng nhập có khớp với hash đang lưu hay không?** Spring Security cung cấp `PasswordEncoder.matches(rawPassword, encodedPassword)` để thực hiện kiểm tra này.

Bài học thuộc chương **Kiểm thử thành phần** của mô-đun **SPRING_SECURITY_TESTING**. Mô-đun hướng tới xác minh xác thực, phân quyền và bảo vệ HTTP thật bằng `spring-security-test` trên ứng dụng Servlet và Reactive, bao gồm `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext` và JWT/OAuth2/OIDC giả lập. Trong bài này, ta tập trung kiểm thử `PasswordEncoder` và cách kết quả ảnh hưởng tới `DaoAuthenticationProvider`, sau đó đối chiếu với kiểm thử HTTP.

Sau bài học, bạn có thể:

- Giải thích sự khác nhau giữa mật khẩu thô, hash lưu trữ, salt và phép so khớp.
- Kiểm tra `encode(...)`/`matches(...)` dựa trên **hành vi**, không phụ thuộc hash cố định.
- Viết test cho mật khẩu đúng, sai, dữ liệu Unicode và hai lần encode có salt khác nhau.
- Sử dụng `DelegatingPasswordEncoder` với định dạng `{id}hash`; hiểu vai trò của `upgradeEncoding(...)` khi thay đổi chính sách mật khẩu.
- Xác minh `DaoAuthenticationProvider` sử dụng bộ mã hóa đã cấu hình, rồi kiểm chứng luồng HTTP với `MockMvc`/`WebTestClient`.

## 2. Hợp đồng của PasswordEncoder

Trong Spring Security, giao diện `org.springframework.security.crypto.password.PasswordEncoder` cung cấp ba thao tác chính:

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);

    boolean matches(CharSequence rawPassword, String encodedPassword);

    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

| Phương thức | Đầu vào | Kết quả và mục đích |
| --- | --- | --- |
| `encode(rawPassword)` | Mật khẩu thô | Tạo hash để lưu, có thể chứa thông tin salt và tham số thuật toán |
| `matches(rawPassword, encodedPassword)` | Mật khẩu thô người dùng nhập và **hash đã lưu** | `true` nếu mật khẩu hợp lệ với hash; `false` nếu không khớp đối với định dạng được encoder hỗ trợ |
| `upgradeEncoding(encodedPassword)` | Hash hiện có | Cho biết hash có nên được tạo lại theo chính sách mã hóa hiện tại hay không |

`PasswordEncoder` phục vụ **băm mật khẩu theo một chiều**, không cung cấp thao tác giải mã để khôi phục mật khẩu từ hash. Trong quy trình đăng nhập, mã nguồn phải truyền mật khẩu **thô** vào tham số thứ nhất của `matches(...)` và giá trị hash **được lưu từ trước** vào tham số thứ hai.

Ví dụ kiểm tra đúng:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();

String rawPassword = "correct-password";
String storedHash = encoder.encode(rawPassword); // Giả lập giá trị lưu DB.

boolean allowed = encoder.matches("correct-password", storedHash); // true
boolean denied = encoder.matches("wrong-password", storedHash);    // false
~~~

Không viết `encoder.matches(encoder.encode(input), storedHash)`: tham số thứ nhất phải là **mật khẩu thô**, không phải hash mới. Cũng không dùng `encoder.encode(input).equals(storedHash)` để kiểm tra đăng nhập. Các cách này có thể từ chối mật khẩu đúng khi thuật toán dùng salt ngẫu nhiên.

## 3. BCrypt, salt và lý do hash không cố định

BCrypt là một thuật toán băm mật khẩu có cơ chế salt và tham số chi phí tính toán (*work factor*). Salt giúp hai tài khoản dùng cùng mật khẩu không nhất thiết có cùng hash; độ khó tính toán khiến việc thử nhiều mật khẩu trở nên tốn kém hơn. BCrypt cũng thiết kế để có thể điều chỉnh chi phí theo năng lực phần cứng.

~~~mermaid
flowchart TD
    A["Mật khẩu thô: correct-password"] --> B["BCryptPasswordEncoder.encode"]
    B --> C["Tạo salt ngẫu nhiên cho lần encode này"]
    C --> D["BCrypt với work factor đã cấu hình"]
    D --> E["Hash A: lưu cùng dữ liệu salt/chi phí"]
    A --> F["Một lần encode khác"]
    F --> G["Salt khác"]
    G --> H["Hash B: có thể khác Hash A"]
    E --> I["matches(correct-password, Hash A) = true"]
    H --> J["matches(correct-password, Hash B) = true"]
~~~

Một chuỗi BCrypt thông thường có phần nhận dạng phiên bản, tham số chi phí và dữ liệu băm/salt được mã hóa. Đừng giả định toàn bộ cấu trúc hoặc prefix chi tiết luôn giống nhau giữa các thuật toán, phiên bản và cấu hình.

Hai điều có thể cùng đúng:

~~~text
hashA != hashB
matches("correct-password", hashA) == true
matches("correct-password", hashB) == true
~~~

Vì vậy, **giá trị hash không phải kết quả mong đợi cố định** trong kiểm thử hành vi. Giá trị mong đợi chính là `matches(...)` trả đúng `true` hoặc `false`.

> Các ví dụ trong bài sử dụng mật khẩu giả dành riêng cho test. Ứng dụng thật cần quản lý mật khẩu, cấu hình encoder và thông tin xác thực theo chính sách bảo mật; không ghi mật khẩu thô hoặc header Authorization vào log.

## 4. Ma trận kiểm thử PasswordEncoder

Trước khi viết test, hãy tách các trường hợp quan trọng:

| Tình huống | Thiết lập | Assertion đúng |
| --- | --- | --- |
| Mật khẩu đúng | `storedHash = encoder.encode(raw)` | `encoder.matches(raw, storedHash)` là `true` |
| Mật khẩu sai | Sử dụng lại hash của mật khẩu đúng | `encoder.matches(wrongRaw, storedHash)` là `false` |
| Mật khẩu cùng nội dung được encode hai lần | Gọi `encode(raw)` hai lần | Mỗi hash đều phải xác minh được cùng `raw`; với BCrypt thông thường hash có salt khác nhau |
| Hash tồn tại từ lần chạy trước hoặc từ database | Dùng hash do hệ thống lưu từ trước | Một encoder tương thích vẫn xác minh được mật khẩu thô |
| Mật khẩu có Unicode hoặc khoảng trắng | Encode rồi kiểm tra lại đúng chuỗi | `matches(...)` không tự đổi nội dung, bỏ dấu hoặc `trim()` |
| Mật khẩu bị thay đổi một ký tự | Dùng hash của chuỗi gốc | Kết quả `false` |
| Hash dùng thuật toán/chi phí cũ | Dùng encoder phù hợp với định dạng cũ | Sau xác minh thành công, cân nhắc `upgradeEncoding(...)` |
| Hash hỏng hoặc không thuộc định dạng hỗ trợ | Gọi decoder với dữ liệu không hợp lệ | Xử lý an toàn theo hợp đồng triển khai; có thể trả `false` hoặc báo lỗi định dạng |

Trong test xác thực thật, ta nên tạo hash động từ mật khẩu đã biết và kiểm tra các tính chất của nó. Trường hợp cần cố định một hash đầu vào để kiểm thử **tương thích dữ liệu cũ** là ngoại lệ có chủ đích: test đó đang xác minh khả năng đọc định dạng lưu trữ cũ, chứ không assert rằng `encode(...)` mới phải trả về đúng chuỗi cố định.

## 5. Kiểm thử BCryptPasswordEncoder bằng JUnit 5

Đoạn sau là một lớp test độc lập, dùng JUnit Jupiter và AssertJ. Dependency cung cấp `BCryptPasswordEncoder` là Spring Security Crypto, thường đã nằm trong `spring-boot-starter-security`.

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.assertj.core.api.Assertions.assertThat;

class PasswordEncoderComponentTest {

    private final PasswordEncoder encoder = new BCryptPasswordEncoder();

    @Test
    void validPasswordMatchesFreshlyEncodedHash() {
        String raw = "correct-password";
        String storedHash = encoder.encode(raw);

        assertThat(storedHash).isNotEqualTo(raw);
        assertThat(encoder.matches(raw, storedHash)).isTrue();
    }

    @Test
    void incorrectPasswordDoesNotMatchStoredHash() {
        String storedHash = encoder.encode("correct-password");

        assertThat(encoder.matches("wrong-password", storedHash)).isFalse();
        assertThat(encoder.matches("correct-password!", storedHash)).isFalse();
    }

    @Test
    void twoHashesOfSamePasswordCanDifferButBothAreValid() {
        String raw = "correct-password";
        String firstHash = encoder.encode(raw);
        String secondHash = encoder.encode(raw);

        // BCrypt tạo salt mới cho mỗi lần encode.
        assertThat(firstHash).isNotEqualTo(secondHash);
        assertThat(encoder.matches(raw, firstHash)).isTrue();
        assertThat(encoder.matches(raw, secondHash)).isTrue();
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "mat-khau-dai-123",
            "Mật khẩu có dấu",
            " space before and after "
    })
    void supportsExactPasswordInputIncludingUnicodeAndSpaces(String raw) {
        String storedHash = encoder.encode(raw);

        assertThat(encoder.matches(raw, storedHash)).isTrue();
    }

    @Test
    void doesNotIgnorePasswordWhitespace() {
        String storedHash = encoder.encode(" exact-password ");

        assertThat(encoder.matches("exact-password", storedHash)).isFalse();
        assertThat(encoder.matches(" exact-password ", storedHash)).isTrue();
    }

    @Test
    void hashCanBeVerifiedByAnotherCompatibleEncoderInstance() {
        PasswordEncoder encoderForRegistration = new BCryptPasswordEncoder();
        PasswordEncoder encoderForLogin = new BCryptPasswordEncoder();

        String storedHash =
                encoderForRegistration.encode("correct-password");

        assertThat(encoderForLogin.matches(
                "correct-password", storedHash)).isTrue();
    }
}
~~~

Điểm quan trọng là mọi assertion thành công đều gọi `matches(raw, storedHash)`. Hash được tạo **ngay trong test** để test không phụ thuộc vào salt do lần chạy trước sinh ra.

Kiểm thử `firstHash != secondHash` phản ánh cách BCrypt tạo salt ngẫu nhiên. Về mặt toán học, xác suất hai lần dùng trùng salt là rất nhỏ nhưng không tuyệt đối bằng không; nếu hệ thống đặt yêu cầu kiểm thử không phụ thuộc xác suất, có thể bỏ assertion về hai chuỗi khác nhau và chỉ kiểm tra cả hai hash đều khớp.

Test Unicode hoặc khoảng trắng không có nghĩa mọi ứng dụng nên cho phép mọi định dạng mật khẩu. Nó chứng minh encoder xử lý **đúng chuỗi đầu vào được truyền vào**. Quy tắc chuẩn hóa, độ dài tối đa và kiểm tra mật khẩu của hệ thống nên được quy định riêng và kiểm thử độc lập; không tự động `trim()` mật khẩu khi xác thực nếu chính sách không yêu cầu.

## 6. Sử dụng DelegatingPasswordEncoder và tiền tố {id}

Ứng dụng có thể thay đổi thuật toán hoặc chi phí băm theo thời gian. Spring Security cung cấp `DelegatingPasswordEncoder` để chọn đúng bộ mã hóa dựa trên tiền tố nhận dạng thuật toán:

~~~text
{bcrypt}<bcrypt-hash>
{pbkdf2}<pbkdf2-hash>
{argon2}<argon2-hash>
~~~

Đây là cú pháp mô tả; dữ liệu sau tiền tố phụ thuộc từng encoder. Không tự ghép chuỗi như thế này trong code sản xuất nếu bộ mã hóa đã chịu trách nhiệm sinh định dạng lưu trữ.

Thông thường, có thể tạo encoder mặc định:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
class PasswordConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
~~~

Trong cấu hình Spring Security phổ biến hiện nay, encoder do `PasswordEncoderFactories.createDelegatingPasswordEncoder()` tạo sẽ mã hóa mật khẩu mới bằng BCrypt, kèm prefix `{bcrypt}`. Khi `matches(...)`, nó dùng `{id}` trong hash đã lưu để chọn encoder tương ứng.

Ví dụ kiểm thử không phụ thuộc toàn bộ hash:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.assertj.core.api.Assertions.assertThat;

class DelegatingPasswordEncoderTest {

    @Test
    void writesAlgorithmIdAndVerifiesPassword() {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        String storedHash = encoder.encode("correct-password");

        assertThat(storedHash).startsWith("{bcrypt}");
        assertThat(encoder.matches(
                "correct-password", storedHash)).isTrue();
        assertThat(encoder.matches(
                "wrong-password", storedHash)).isFalse();
    }
}
~~~

Assertion `startsWith("{bcrypt}")` kiểm tra **chính sách cấu hình thuật toán** hiện tại của factory. Nếu một ngày dự án cố ý chuyển thuật toán mã hóa mặc định, hãy cập nhật test chính sách cùng cấu hình. Đừng yêu cầu toàn bộ hash phía sau `{bcrypt}` cố định.

### Khi dữ liệu cũ không có {id}

Một hash BCrypt thuần thường bắt đầu bằng marker của BCrypt thay vì `{bcrypt}`. Nếu gửi hash không có tiền tố vào một `DelegatingPasswordEncoder` mặc định, encoder có thể không xác định được ID và báo lỗi. Những cách xử lý phù hợp tùy tình huống:

- Di chuyển dữ liệu lưu trữ cũ sang định dạng có `{id}` đúng với thuật toán ban đầu, sau khi xác minh nguồn gốc hash.
- Xây dựng cơ chế tương thích được kiểm soát cho dữ liệu cũ, rồi loại bỏ khi chuyển đổi hoàn tất.
- Sau đăng nhập thành công, tạo lại hash theo chính sách hiện tại nếu cần.

Không nên sửa lỗi bằng cách mặc định xem mọi hash không nhận diện được là mật khẩu thô hoặc tự động cho phép đăng nhập. Nếu sử dụng cơ chế fallback, phải kiểm thử những định dạng được phép một cách tường minh.

### Nâng cấp chi phí mã hóa

`upgradeEncoding(...)` là tín hiệu gợi ý hash hiện tại có nên nâng cấp theo encoder đang cấu hình. Chẳng hạn, một hash BCrypt được tạo với work factor thấp hơn có thể cần được băm lại với chi phí mới. Việc mã hóa lại chỉ thực hiện được khi ứng dụng có mật khẩu thô hợp lệ, ví dụ **sau khi người dùng đăng nhập thành công**.

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder(12);

// storedHash: mật khẩu đã băm trước đây, được lấy từ kho lưu trữ.
if (encoder.matches(rawPassword, storedHash)
        && encoder.upgradeEncoding(storedHash)) {
    String upgradedHash = encoder.encode(rawPassword);
    // Lưu upgradedHash theo cơ chế cập nhật an toàn của ứng dụng.
}
~~~

Đoạn trên minh họa nhánh xử lý, không phải một chương trình độc lập vì `rawPassword` và `storedHash` đến từ luồng ứng dụng. Không tăng work factor tùy ý trong mọi lần chạy test; chi phí băm cao có thể làm tăng đáng kể thời gian chạy. Chọn mức phù hợp với tài nguyên và chính sách vận hành.

## 7. Kiểm thử PasswordEncoder khi được DaoAuthenticationProvider sử dụng

Kiểm thử `PasswordEncoder` trực tiếp chỉ chứng minh `encode/matches` hoạt động đúng. Trong ứng dụng Servlet, `DaoAuthenticationProvider` thường gọi `UserDetailsService` để lấy hash và gọi `PasswordEncoder.matches(...)` để quyết định xác thực. Cần có một bài test đi qua provider để phát hiện lỗi **dùng sai encoder**, lưu sai định dạng hoặc chuyển nhầm mật khẩu.

Ví dụ sau dùng Spring Security thật, không mock `PasswordEncoder`:

~~~java
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.InMemoryUserDetailsManager;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class PasswordAuthenticationComponentTest {

    private ProviderManager manager;

    @BeforeEach
    void setUp() {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        InMemoryUserDetailsManager users = new InMemoryUserDetailsManager(
                User.withUsername("lan")
                        .password(encoder.encode("correct-password"))
                        .roles("READER")
                        .build());

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        manager = new ProviderManager(List.of(provider));
    }

    private Authentication login(String password) {
        return manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "lan", password));
    }

    @Test
    void correctPasswordAuthenticatesWithExpectedAuthority() {
        Authentication result = login("correct-password");

        assertThat(result.isAuthenticated()).isTrue();
        assertThat(result.getName()).isEqualTo("lan");
        assertThat(result.getAuthorities())
                .extracting(GrantedAuthority::getAuthority)
                .containsExactly("ROLE_READER");
    }

    @Test
    void wrongPasswordIsRejectedByRealPasswordEncoder() {
        assertThatThrownBy(() -> login("wrong-password"))
                .isInstanceOf(BadCredentialsException.class);
    }

    @Test
    void differentCapitalizationIsNotTheSamePassword() {
        assertThatThrownBy(() -> login("Correct-Password"))
                .isInstanceOf(BadCredentialsException.class);
    }
}
~~~

Ở `setUp()`, hash được tạo động, cùng thuật toán và định dạng với cấu hình xác thực. `DaoAuthenticationProvider` nhận mật khẩu thô từ token chưa xác thực rồi tự kiểm tra bằng encoder. Test không cần biết giá trị hash, nhưng vẫn kiểm chứng được kết quả xác thực thực và authorities.

> Ví dụ sử dụng constructor `DaoAuthenticationProvider(UserDetailsService)` của các phiên bản Spring Security hiện đại. Với bản cũ dùng API khởi tạo khác, cần điều chỉnh phần tạo provider theo phiên bản dự án.

**Khi nào nên mock PasswordEncoder?** Nếu đang kiểm tra riêng điều phối của một lớp tự viết, mock có thể hữu ích để xác nhận lớp truyền đúng tham số vào `matches(...)`. Tuy nhiên, mock kiểu `when(matches(any(), any())).thenReturn(true)` khiến test đăng nhập thành công ngay cả khi mật khẩu sai, không có ý nghĩa để khẳng định BCrypt hoặc cấu hình xác thực hoạt động. Với mục tiêu bài này, ưu tiên encoder thật.

## 8. Đưa kiểm thử đến tầng HTTP bằng spring-security-test

Trong ứng dụng **Servlet**, kiểm thử qua `MockMvc` sẽ phát hiện thêm các lỗi như filter không được kích hoạt, sai `AuthenticationManager`, sai encoder được inject hoặc endpoint được mở ngoài ý muốn.

Giả sử ứng dụng Spring Boot có `SecurityFilterChain` bật HTTP Basic; `/api/profile` tồn tại và yêu cầu đăng nhập; test context có tài khoản `lan` với password hash được tạo bằng encoder cùng cấu hình và mật khẩu thô `correct-password`. Khi đó:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordHttpSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void correctBasicCredentialsCanAccessProfile() throws Exception {
        mockMvc.perform(get("/api/profile")
                        .with(httpBasic("lan", "correct-password")))
                .andExpect(status().isOk());
    }

    @Test
    void wrongBasicCredentialsReturnUnauthorized() throws Exception {
        mockMvc.perform(get("/api/profile")
                        .with(httpBasic("lan", "wrong-password")))
                .andExpect(status().isUnauthorized());
    }
}
~~~

Đây là mẫu test tích hợp **phụ thuộc endpoint và cấu hình ứng dụng**; cần cung cấp các bean thực và test users như giả định. HTTP Basic thông thường trả `401 Unauthorized` khi mật khẩu không hợp lệ. Với form login có thể xảy ra chuyển hướng; cơ chế xác thực hoặc `AuthenticationEntryPoint` tùy chỉnh có thể dẫn đến mã HTTP khác. `403 Forbidden` thường phản ánh vấn đề phân quyền khi người dùng đã xác thực, hoặc các điều kiện bảo mật khác như CSRF.

`@WithMockUser` và `user(...)` của `spring-security-test` cho phép kiểm tra endpoint với một `Authentication` đã được dựng sẵn. **Chúng bỏ qua bước kiểm tra mật khẩu thật.** Một test dùng `@WithMockUser(username = "lan")` có thể qua ngay cả khi dữ liệu hash trong hệ thống sai hoặc `PasswordEncoder` chưa được đăng ký đúng.

### Với ứng dụng Reactive

Trong WebFlux, việc xác thực tên người dùng/mật khẩu có thể dùng `UserDetailsRepositoryReactiveAuthenticationManager` phối hợp với `ReactiveUserDetailsService` và `PasswordEncoder`. Kiểm thử qua `WebTestClient` giúp xác nhận request HTTP đi qua chuỗi bảo mật Reactive đã cấu hình:

~~~java
webTestClient.get()
        .uri("/api/profile")
        .headers(headers ->
                headers.setBasicAuth("lan", "wrong-password"))
        .exchange()
        .expectStatus().isUnauthorized();
~~~

Đoạn này là phần thân của một bài test có `webTestClient` được gắn với ứng dụng Reactive, endpoint và HTTP Basic đã được cấu hình. Các tiện ích giả lập của `spring-security-test` dành cho WebFlux vẫn có ích để kiểm tra quyền, nhưng nếu muốn khẳng định `PasswordEncoder` thật được dùng, cần gửi dữ liệu đăng nhập qua cơ chế xác thực thực của ứng dụng.

### JWT, OAuth2 và OIDC có dùng PasswordEncoder không?

`PasswordEncoder` chủ yếu phục vụ xác thực **mật khẩu được lưu dưới dạng hash**. Trong resource server xác minh JWT, `JwtDecoder` và validator chịu trách nhiệm xác minh token, chứ không tự động so khớp mật khẩu người dùng với hash từ `UserDetailsService`. Tương tự, các tiện ích `jwt()`, `oauth2Login()` và `oidcLogin()` giả lập ngữ cảnh người dùng/token để kiểm thử phân quyền; chúng không chứng minh bước xác thực mật khẩu hoặc luồng giao thức thật đã hoạt động.

## 9. Những lỗi thường gặp

**So sánh nguyên chuỗi BCrypt hash với một giá trị cố định.** Salt ngẫu nhiên có thể khiến `encode(...)` trả hash khác ở mỗi lần gọi. Test nên dựa vào `matches(...)`, trừ trường hợp chủ đích kiểm tra khả năng đọc một định dạng dữ liệu cũ.

**Hash lại mật khẩu nhập vào rồi so sánh bằng equals.** `encode(input).equals(storedHash)` có thể trả `false` dù mật khẩu đúng. Thay bằng `matches(input, storedHash)`.

**Truyền nhầm thứ tự tham số matches.** Hàm nhận mật khẩu thô trước, hash lưu trữ sau. Đảo vị trí có thể làm việc xác thực thất bại hoặc gây lỗi định dạng.

**Không dùng cùng cấu hình encoder cho đăng ký và đăng nhập.** Dữ liệu được lưu ở định dạng này nhưng luồng xác thực dùng encoder khác hoặc thiếu `{id}` cần thiết sẽ khiến người dùng hợp lệ bị từ chối. Kiểm tra cả nhánh tạo hash và nhánh xác thực trong test tích hợp.

**Mock PasswordEncoder luôn trả true.** Một test như vậy không phát hiện được mật khẩu sai, hash không hợp lệ hoặc cấu hình encoder lỗi. Chỉ mock khi mục tiêu là kiểm tra một tương tác riêng, không phải chứng minh tính đúng của xác thực.

**Dùng @WithMockUser để kết luận mật khẩu đã được kiểm tra.** Annotation này tạo sẵn `SecurityContext` cho kiểm thử phân quyền và bỏ qua mã xác thực mật khẩu. Dùng provider thật hoặc gửi yêu cầu HTTP với Basic/form login phù hợp.

**Ghi password thô hoặc toàn bộ header Basic vào log.** Dữ liệu test nên dùng bí mật giả; log không nên chứa credentials thật. Test có thể xác minh thông điệp lỗi không vô tình trả mật khẩu.

**Tăng work factor quá cao cho mọi test.** Mỗi lần gọi `encode/matches` BCrypt đều tiêu tốn CPU. Dùng encoder thật cho những test có giá trị kiểm chứng bảo mật, chọn chi phí phù hợp và không tạo hàng trăm phép băm không cần thiết trong test setup.

**Tự động loại bỏ khoảng trắng hoặc sửa chữ hoa/chữ thường.** Thay đổi chuỗi mật khẩu trước khi `matches(...)` có thể làm sai hợp đồng đăng nhập hoặc gây hành vi bất ngờ. Nếu ứng dụng có chính sách xử lý đầu vào cụ thể, hãy kiểm chứng chính sách đó riêng.

## 10. Bài thực hành

1. Viết một test gọi `BCryptPasswordEncoder.encode("same-password")` hai lần. Kiểm chứng mỗi hash đều cho `matches("same-password", hash) == true`, rồi giải thích vì sao không cần lưu sẵn hash mẫu trong assertion.
2. Dùng `PasswordEncoderFactories.createDelegatingPasswordEncoder()` tạo hash đăng ký và lưu nó vào `InMemoryUserDetailsManager`. Viết hai test qua `DaoAuthenticationProvider`: mật khẩu đúng được xác thực, mật khẩu sai nhận `BadCredentialsException`.
3. Viết một test với mật khẩu có dấu và khoảng trắng đầu/cuối. Thử thay đổi một ký tự hoặc bỏ một khoảng trắng, rồi xác minh `matches(...)` từ chối.
4. Giả lập dữ liệu BCrypt cũ được mã hóa với mức chi phí thấp hơn. Dùng `upgradeEncoding(...)` để xác định có cần nâng cấp và giải thích lúc nào có thể tạo hash mới.
5. Kiểm tra một endpoint bảo vệ bằng `MockMvc` sử dụng `httpBasic(...)`. Thay test đó bằng `@WithMockUser` và nêu lý do test sau không phát hiện được cấu hình `PasswordEncoder` sai.

Khi kiểm thử mật khẩu trong Spring Security, tiêu chí quan trọng là **mật khẩu đúng được chấp nhận, mật khẩu sai bị từ chối và định dạng hash có thể được xác minh theo cấu hình**. Lấy hành vi của `matches(...)` làm chuẩn giúp bộ kiểm thử ổn định trước salt ngẫu nhiên và vẫn phát hiện được các lỗi thực sự trong luồng xác thực.
