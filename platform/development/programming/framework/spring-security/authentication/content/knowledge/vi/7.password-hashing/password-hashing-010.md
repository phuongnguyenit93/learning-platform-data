# NoOpPasswordEncoder và giới hạn của cấu hình minh họa

## 1. Mục đích của bài học

Trong ví dụ Spring Security, bạn có thể gặp cấu hình cho phép một tài khoản đăng nhập bằng mật khẩu viết thẳng trong mã nguồn hoặc bằng chuỗi `{noop}demo-password`. Cách này làm bài hướng dẫn ngắn và dễ chạy, nhưng cũng có thể tạo ra một hiểu lầm nguy hiểm: **đăng nhập thành công không đồng nghĩa mật khẩu được lưu trữ an toàn**.

`NoOpPasswordEncoder` là triển khai `PasswordEncoder` **không thực hiện băm, thêm salt hoặc làm mật khẩu khó đoán hơn**. Với cách lưu trực tiếp, đầu ra của `encode(rawPassword)` về cơ bản vẫn là chính mật khẩu người dùng nhập. `matches(raw, stored)` kiểm tra hai chuỗi có giống nhau hay không. Spring Security đánh dấu class này **`@Deprecated`** và xác định nó chỉ dành cho tình huống legacy hoặc kiểm thử, không bảo đảm an toàn để lưu trữ mật khẩu thật.

Bài viết tập trung vào:

1. `NoOpPasswordEncoder` làm gì và **không làm gì**.
2. Sự khác nhau giữa `NoOpPasswordEncoder.getInstance()`, chuỗi `{noop}...` và `DelegatingPasswordEncoder`.
3. Tại sao cấu hình demo chạy được nhưng không được xem là cấu hình production.
4. Ví dụ Java 17+ chạy được với Spring Security 6.5.11, vừa thể hiện cơ chế insecure vừa thể hiện thay thế bằng BCrypt.
5. Cách kiểm thử, xử lý thông báo lỗi encoder và chuyển dữ liệu plaintext/legacy sang hash phù hợp mà không vô tình mở lỗ hổng.

Phạm vi thuộc nhóm **Băm mật khẩu** của Spring Security. Các bước xác thực qua `DaoAuthenticationProvider` chỉ được giới thiệu để cho thấy một mật khẩu plaintext vẫn có thể được framework xác minh, chứ không phải để xây một hệ thống đăng nhập đầy đủ có session, CSRF và giao diện web.

## 2. Mật khẩu dạng rõ khác với hash như thế nào?

Giả sử mật khẩu demo là `DemoPass123!`. Với một encoder mạnh có salt như BCrypt, giá trị được lưu sẽ là một **password verifier một chiều**. Với NoOp, giá trị được lưu vẫn là chuỗi dễ đọc.

| Tiêu chí | `NoOpPasswordEncoder` | `BCryptPasswordEncoder` hoặc encoder thích nghi phù hợp |
| --- | --- | --- |
| `encode("DemoPass123!")` | Trả `DemoPass123!`. | Trả password hash có cấu trúc và salt, thay đổi theo từng lần encode. |
| Thêm salt ngẫu nhiên | **Không**. | Có, theo thuật toán tương ứng. |
| Cấu hình chi phí tính toán (work factor) | **Không**. | Có thể điều chỉnh chi phí xác minh. |
| Khôi phục mật khẩu từ dữ liệu DB | Chính mật khẩu đã nằm ở đó. | Không có thao tác giải mã trực tiếp; vẫn cần chống đoán offline. |
| Khi DB bị lộ | Mật khẩu được tiết lộ ngay lập tức. | Attacker thấy hash và phải tấn công đoán mật khẩu; mức bảo vệ tùy mật khẩu/thuật toán/work factor. |
| Sử dụng production | **Không phù hợp**. | Có thể phù hợp nếu lựa chọn tham số và vận hành đúng. |
| Test nhanh rất nhỏ | Có thể dùng khi cố ý thử luồng bằng dữ liệu giả, không triển khai ra ngoài. | Vẫn nên dùng khi test liên quan mật khẩu thật. |

**Điều NoOp không làm:** không mã hóa hai chiều, không SHA-256, không BCrypt, không PBKDF2, không salt, không bảo vệ trước một bản dump dữ liệu. Gọi method có tên `encode` không biến mật khẩu thành dữ liệu bí mật.

Có ba rủi ro rất thực tế:

- Nếu bảng `users` có cột `password_hash` nhưng thực tế lưu plaintext, **tên cột không làm dữ liệu an toàn**.
- Nếu tài khoản sử dụng lại mật khẩu ở dịch vụ khác, kẻ lấy được plaintext có thể thử chiếm thêm tài khoản ngoài ứng dụng.
- Nếu một môi trường demo vô tình được bật trên production hoặc truy cập được từ Internet, username/password hard-code là một đường đăng nhập có thể bị lạm dụng.

Dữ liệu demo giả lập vẫn cần được cách ly khỏi dữ liệu thật. Không đưa tài khoản mẫu có quyền cao, password chung hoặc endpoint debug ra môi trường public.

## 3. Hợp đồng `PasswordEncoder` và hành vi của NoOp

`PasswordEncoder` là interface trong gói `org.springframework.security.crypto.password`. Hai method cốt lõi:

```java
String encode(CharSequence rawPassword);

boolean matches(CharSequence rawPassword, String encodedPassword);
```

- `encode`: tạo giá trị lưu trữ từ mật khẩu đầu vào.
- `matches`: kiểm tra password do người dùng gửi có khớp với giá trị đã lưu hay không.
- `upgradeEncoding(String encodedPassword)`: phương thức hỗ trợ đánh giá cần nâng cấp cách lưu; mức độ hữu ích tùy encoder và wrapper.

Đối với NoOp, ta có thể minh họa đơn giản:

```java
PasswordEncoder noop = NoOpPasswordEncoder.getInstance();

String stored = noop.encode("DemoPass123!");
System.out.println(stored.equals("DemoPass123!")); // true

System.out.println(noop.matches("DemoPass123!", stored)); // true
System.out.println(noop.matches("wrong-password", stored)); // false
```

Đây là **đoạn trích** cần import `PasswordEncoder` và `NoOpPasswordEncoder`. Điều cần chú ý không phải ba boolean mà là **mật khẩu gốc đã được lưu y nguyên**. Chính tính đơn giản ấy giúp giải thích API và khiến cách dùng này không an toàn.

### 3.1. Lấy instance đúng API

`NoOpPasswordEncoder` là singleton; cách lấy được tài liệu hóa:

```java
@SuppressWarnings("deprecation")
PasswordEncoder noop = NoOpPasswordEncoder.getInstance();
```

`@SuppressWarnings("deprecation")` chỉ tắt cảnh báo của compiler cho một vị trí cụ thể. Nó **không sửa lỗ hổng bảo mật**, không biến NoOp thành công nghệ phù hợp cho production và không có lý do sử dụng để che cảnh báo trong ứng dụng thật.

Không cần tạo subclass, không tìm constructor `new NoOpPasswordEncoder()`. Class trong Spring Security 6.5.11 là `final`, constructor không công khai, sử dụng `getInstance()`.

### 3.2. So sánh có phân biệt ký tự

NoOp so sánh chuỗi, nên `DemoPass123!` và `demopass123!` là hai giá trị khác nhau. Không tự lower-case/trim mật khẩu để làm cho test pass: password là **credential**, không phải username cần canonicalization.

```java
PasswordEncoder noop = NoOpPasswordEncoder.getInstance();

boolean ok = noop.matches("DemoPass123!", "DemoPass123!");
boolean bad = noop.matches("demopass123!", "DemoPass123!");
```

Tuy nhiên, **so chuỗi plaintext** không có nghĩa cơ chế này cung cấp một verifier password có chi phí phù hợp hoặc chống tấn công offline. `matches` có thể trả đúng `true` nhưng quyết định lưu trữ plaintext đã sai ngay từ trước.

## 4. `{noop}` là gì, có mã hóa mật khẩu không?

Spring Security hỗ trợ `DelegatingPasswordEncoder`, cho phép lưu mật khẩu theo cấu trúc:

```text
{id}encodedPassword
```

`id` là **tên bộ mã hóa được chọn**; phần sau là dữ liệu của encoder đó. Ví dụ:

```text
{noop}DemoPass123!
{bcrypt}$2a$...
{pbkdf2@SpringSecurity_v5_8}...
```

Trong chuỗi đầu tiên:

- `{noop}` là **nhãn định tuyến**.
- `DemoPass123!` vẫn là **mật khẩu dạng rõ**.
- Không có salt, hash hoặc cơ chế làm khó đoán password.
- `DelegatingPasswordEncoder` đọc `id=noop` và chuyển phần mật khẩu sang `NoOpPasswordEncoder` để kiểm tra.

**Ranh giới quan trọng:** bản thân `NoOpPasswordEncoder` **không xử lý prefix `{noop}` theo cú pháp delegate**. Nếu sử dụng trực tiếp:

```java
PasswordEncoder noop = NoOpPasswordEncoder.getInstance();

noop.matches("DemoPass123!", "DemoPass123!");       // true
noop.matches("DemoPass123!", "{noop}DemoPass123!"); // false
```

Nhưng với encoder được tạo bởi factory mặc định của Spring Security 6.5:

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

encoder.matches("DemoPass123!", "{noop}DemoPass123!"); // true
```

`DelegatingPasswordEncoder` nhận diện prefix, lấy phần bên phải và gọi đúng encoder. Không có bước nào ở đây biến dữ liệu `{noop}DemoPass123!` thành hash.

### 4.1. Tại sao framework vẫn hỗ trợ `{noop}`?

Trong lịch sử Spring Security, trước phiên bản 5.0, cấu hình mặc định từng sử dụng NoOp. Khi khuyến nghị lưu trữ thay đổi, nhiều hệ thống đã có dữ liệu mật khẩu theo các kiểu cũ. Framework không thể đột ngột bỏ mọi cơ chế legacy mà không gây mất khả năng đăng nhập.

`DelegatingPasswordEncoder` cho phép:

1. **Đọc dữ liệu cũ** bằng encoder phù hợp với ID cũ.
2. **Ghi dữ liệu mới** bằng encoder hiện hành mạnh hơn.
3. **Nâng cấp dần** khi có cơ hội xác thực thành công và đã cấu hình dịch vụ cập nhật hash.

Có hỗ trợ backward compatibility **không phải** Spring Security khuyến khích lưu plaintext mới. Trong tài liệu Spring Security 6.5, factory mặc định thường **encode mới bằng BCrypt** nhưng vẫn có thể **match `{noop}`** cho legacy/demo.

### 4.2. Quy tắc prefix trong thực tế

| Giá trị ở DB | Encoder trực tiếp | Delegating encoder mặc định | Đánh giá |
| --- | --- | --- | --- |
| `DemoPass123!` | NoOp so chuỗi dạng rõ được. | Không có `{id}`: thường ném `IllegalArgumentException` vì id null. | Plaintext legacy, rất rủi ro. |
| `{noop}DemoPass123!` | NoOp trực tiếp xem prefix là ký tự của chuỗi, nên raw không khớp. | Tách `id=noop` và kiểm tra plaintext. | Cũng không an toàn dù có prefix. |
| `{bcrypt}$2a$...` | NoOp trực tiếp không thể kiểm chứng password theo cách băm. | Tách `id=bcrypt`, dùng BCrypt. | Có thể phù hợp với policy hiện hành. |
| `{argon2}...` | NoOp không biết thuật toán. | Chỉ hoạt động nếu registry có encoder/định dạng tương ứng. | Phụ thuộc cấu hình và tham số. |
| `{unknown}...` | NoOp không có cơ chế định tuyến. | Mặc định có thể báo không có encoder mapped. | Phải xử lý format/version; không đoán bừa. |

Tiền tố là **metadata chọn thuật toán**, không phải lớp bảo vệ riêng. Thêm `{noop}` vào dữ liệu plaintext còn khiến một encoder đa thuật toán nhận biết và tiếp tục chấp nhận plaintext, **không khắc phục rủi ro lưu trữ**.

## 5. `User.withDefaultPasswordEncoder()` không giống NoOp

Một đoạn cấu hình học Spring Security khác thường xuất hiện:

```java
UserDetails learner = User.withDefaultPasswordEncoder()
    .username("learner")
    .password("DemoPass123!")
    .roles("READER")
    .build();
```

Tên method có thể gây hiểu lầm. Trong Spring Security 6.5.11:

- `User.withDefaultPasswordEncoder()` dùng encoder được tạo từ `PasswordEncoderFactories.createDelegatingPasswordEncoder()`.
- Bản ghi password được builder tạo thường ở dạng **`{bcrypt}...`**, không phải `{noop}DemoPass123!`.
- Nhưng password gốc `DemoPass123!` **vẫn xuất hiện trong source code** và được đưa vào bộ nhớ lúc ứng dụng chạy.
- Vì thế API được đánh dấu **deprecated/unsafe cho production**, chỉ nhằm tiện cho hướng dẫn bắt đầu hoặc demo.

Vậy có **hai hình thức nguy hiểm khác nhau**:

1. `NoOpPasswordEncoder`: dữ liệu lưu trữ trực tiếp là plaintext.
2. `User.withDefaultPasswordEncoder()`: dữ liệu lưu trữ được băm nhưng **plaintext hard-code trong chương trình/source**.

Không được kết luận “đã dùng BCrypt nên an toàn” khi mật khẩu mặc định, hard-coded hoặc có thể lấy từ source/decompiled artifact. Cách thích hợp trong production là tạo password hash ngoài luồng khởi động/cấu hình demo, quản lý bí mật qua cơ chế đáng tin cậy, và không cấp tài khoản mẫu truy cập công khai.

## 6. Ví dụ thực hành an toàn hơn: ghi bằng BCrypt, không dùng NoOp

Spring Security khuyến nghị dùng hàm băm mật khẩu thích nghi một chiều và hiệu chỉnh work factor trên hạ tầng thật. Một ví dụ đơn giản:

```java
PasswordEncoder encoder = new BCryptPasswordEncoder();

String storedHash = encoder.encode("DemoPass123!");

// Kiểm tra password luôn qua matches, không encode thêm rồi so chuỗi.
boolean accepted = encoder.matches("DemoPass123!", storedHash);
boolean rejected = encoder.matches("wrong", storedHash);
```

Với BCrypt:

- `storedHash` là verifier có salt, không phải password gốc.
- Mỗi lần `encode` thường cho chuỗi khác vì salt ngẫu nhiên.
- `matches` dùng thông số có trong định dạng hash để xác minh.
- Chi phí tính toán có thể điều chỉnh và cần benchmark phù hợp.
- Không log password thô hoặc đưa hash ra API.

**Quan trọng:** dùng trực tiếp `BCryptPasswordEncoder` thì giá trị DB thường có dạng `$2a$...`/`$2b$...` mà **không có `{bcrypt}` prefix**. Nếu dùng `DelegatingPasswordEncoder` để ghi, chuỗi sẽ có prefix `{bcrypt}...` để chọn đúng encoder. Hai định dạng **không thể hoán đổi tùy ý**; phải thống nhất cách lưu và bean/registry dùng để verify.

Dù đã dùng hash thích nghi, vẫn cần chống credential stuffing, rate limiting, quy trình đổi/reset password, MFA khi phù hợp, quyền tối thiểu và giám sát đăng nhập. Password encoder giải quyết **an toàn dữ liệu lưu trữ**, không thay thế toàn bộ bảo mật đăng nhập.

## 7. Ví dụ Java 17+ chạy được: NoOp, `{noop}` và BCrypt trong cùng bài

Đây là chương trình **console độc lập** với **Java 17+**, Gradle và Spring Security **6.5.11**, cho phép quan sát cả hành vi NoOp lẫn lựa chọn tốt hơn.

**Chỉ chạy trong môi trường học tập/test tách biệt.** Password và user trong mã là dữ liệu giả, không đưa vào source của sản phẩm vận hành. Đoạn mã cố ý chứa trường hợp không an toàn để người học nhận biết và xử lý.

### 7.1. Cấu trúc thư mục

```text
noop-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/NoOpDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'noop-demo'
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
}

application {
    mainClass = 'demo.NoOpDemo'
}
```

### 7.2. File `src/main/java/demo/NoOpDemo.java`

```java
package demo;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.NoOpPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public final class NoOpDemo {

    // Giá trị giả chỉ phục vụ demo. Tuyệt đối không dùng credential cố định
    // như thế này cho người dùng thật hoặc trên môi trường public.
    private static final String DEMO_PASSWORD = "DemoPass123!";

    @SuppressWarnings("deprecation")
    public static void main(String[] args) {
        PasswordEncoder noop = NoOpPasswordEncoder.getInstance();

        // 1. NoOp giữ nguyên mật khẩu; không có hash, salt, work factor.
        String unsafeStored = noop.encode(DEMO_PASSWORD);

        System.out.println("noop.storesPlaintext="
                + unsafeStored.equals(DEMO_PASSWORD));
        System.out.println("noop.matchesCorrect="
                + noop.matches(DEMO_PASSWORD, unsafeStored));
        System.out.println("noop.matchesWrong="
                + noop.matches("wrong-password", unsafeStored));
        System.out.println("noop.acceptsPrefixDirectly="
                + noop.matches(DEMO_PASSWORD, "{noop}" + DEMO_PASSWORD));

        // 2. DelegatingPasswordEncoder đọc ID, nhưng ghi mới bằng bcrypt.
        PasswordEncoder delegating =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        String legacyStored = "{noop}" + DEMO_PASSWORD;
        System.out.println("delegate.acceptsLegacyPlaintext="
                + delegating.matches(DEMO_PASSWORD, legacyStored));
        System.out.println("delegate.rejectsWrongPlaintext="
                + delegating.matches("wrong-password", legacyStored));
        System.out.println("delegate.legacyNeedsUpgrade="
                + delegating.upgradeEncoding(legacyStored));

        String modernStored = delegating.encode(DEMO_PASSWORD);
        System.out.println("delegate.newIsBcrypt="
                + modernStored.startsWith("{bcrypt}"));
        System.out.println("delegate.matchesNew="
                + delegating.matches(DEMO_PASSWORD, modernStored));

        // Chuỗi không prefix {id} khiến delegating mặc định không biết
        // dùng encoder nào; KHÔNG sửa bằng cách bật NoOp toàn cục.
        try {
            delegating.matches(DEMO_PASSWORD, DEMO_PASSWORD);
            System.out.println("delegate.noId=unexpected-success");
        } catch (IllegalArgumentException ex) {
            System.out.println("delegate.noId=IllegalArgumentException");
        }

        // 3. Provider vẫn có thể xác thực user legacy {noop} nếu registry
        // giữ decoder đó. Điều này KHÔNG đồng nghĩa bảo vệ plaintext.
        UserDetails legacy = User.withUsername("legacy")
                .password(legacyStored)
                .roles("READER")
                .build();

        UserDetails modern = User.withUsername("modern")
                .password(modernStored)
                .roles("READER")
                .build();

        InMemoryUserDetailsManager store =
                new InMemoryUserDetailsManager(legacy, modern);

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(store);
        provider.setPasswordEncoder(delegating);

        AuthenticationManager manager = new ProviderManager(provider);

        Authentication legacyResult = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "legacy", DEMO_PASSWORD));

        System.out.println("provider.legacyAuthenticated="
                + legacyResult.isAuthenticated());

        try {
            manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "modern", "wrong-password"));
            System.out.println("provider.wrongPassword=unexpected-success");
        } catch (BadCredentialsException ex) {
            System.out.println("provider.wrongPassword=BadCredentialsException");
        }

        Authentication modernResult = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "modern", DEMO_PASSWORD));

        System.out.println("provider.modernAuthenticated="
                + modernResult.isAuthenticated());

        boolean readerAuthority = modernResult.getAuthorities().stream()
                .anyMatch(a -> "ROLE_READER".equals(a.getAuthority()));
        System.out.println("provider.modernReaderRole=" + readerAuthority);
    }
}
```

**Lưu ý về compiler:** `NoOpPasswordEncoder` và `getInstance()` là deprecated; `@SuppressWarnings("deprecation")` trong demo chỉ nhằm giữ trọng tâm đầu ra, không làm code trở nên an toàn.

### 7.3. Chạy chương trình

Cần JDK 17+ và Gradle phiên bản hỗ trợ Java 17 hoặc một Gradle Wrapper tương thích. Từ thư mục chứa `build.gradle`:

```bash
gradle run --quiet
```

**Các dòng stdout từ chương trình** theo Spring Security 6.5.11, không kể log của Gradle:

```text
noop.storesPlaintext=true
noop.matchesCorrect=true
noop.matchesWrong=false
noop.acceptsPrefixDirectly=false
delegate.acceptsLegacyPlaintext=true
delegate.rejectsWrongPlaintext=false
delegate.legacyNeedsUpgrade=true
delegate.newIsBcrypt=true
delegate.matchesNew=true
delegate.noId=IllegalArgumentException
provider.legacyAuthenticated=true
provider.wrongPassword=BadCredentialsException
provider.modernAuthenticated=true
provider.modernReaderRole=true
```

Không in giá trị BCrypt hash vì salt của nó là ngẫu nhiên nên hash thay đổi giữa các lần chạy. Đầu ra ở trên kiểm tra **các thuộc tính ổn định** (đúng/sai, tiền tố, tên loại lỗi).

### 7.4. Vì sao kết quả như vậy?

- **`noop.storesPlaintext=true`:** phép encode NoOp trả chính giá trị gốc; không có password hashing.
- **`noop.matchesCorrect`/`matchesWrong`:** NoOp chỉ so chuỗi, không đối chiếu hash.
- **`noop.acceptsPrefixDirectly=false`:** prefix `{noop}` chỉ được hiểu bởi encoder có cơ chế delegation; NoOp trực tiếp không bóc prefix.
- **`delegate.acceptsLegacyPlaintext=true`:** factory mặc định còn hỗ trợ ID `noop` để đọc dữ liệu cũ/demo; không được nhầm với việc mặc định **ghi** bằng NoOp.
- **`delegate.legacyNeedsUpgrade=true`:** ID cũ khác ID ghi mới `bcrypt` nên wrapper đánh dấu cần nâng cấp, nhưng chưa có thao tác ghi DB nào xảy ra.
- **`delegate.newIsBcrypt=true`:** encoder mới của factory mặc định dùng BCrypt và thêm tiền tố `{bcrypt}`.
- **`delegate.noId=IllegalArgumentException`:** khi bản ghi không có `{id}` và không cấu hình fallback, delegating không thể chọn encoder. Đây là tín hiệu dữ liệu/cấu hình cần điều tra.
- **`provider.legacyAuthenticated=true`:** `DaoAuthenticationProvider` vẫn có thể cấp authentication sau khi password của legacy khớp bằng NoOp. Kết quả “đăng nhập được” **không thể chứng minh mật khẩu lưu trữ an toàn**.
- **`provider.wrongPassword=BadCredentialsException`:** tài khoản modern có hash phù hợp, nhưng mật khẩu nhập sai nên provider từ chối.
- **`provider.modernReaderRole=true`:** authority được lấy từ `UserDetails` do hệ thống cung cấp, không từ role client tự khai.

Bài demo **không tạo HTTP session** hoặc endpoint login. Với ứng dụng web, các filter và cấu hình `SecurityContext` chịu trách nhiệm nhận request, cập nhật trạng thái và áp dụng chính sách truy cập; `PasswordEncoder` không quản lý các phần đó.

## 8. Chỉ dùng NoOp trong phạm vi minh họa đã được kiểm soát

Có thể gặp các mẫu sau trong tài liệu học tập:

```java
// Ví dụ cố ý INSECURE, chỉ phục vụ hiểu cơ chế:
@Bean
PasswordEncoder passwordEncoder() {
    return NoOpPasswordEncoder.getInstance();
}
```

Hoặc:

```java
UserDetails demoUser = User.withUsername("student")
        .password("{noop}DemoOnly123!")
        .roles("READER")
        .build();
```

**Đừng bê nguyên hai đoạn này vào production.** Đoạn đầu làm encoder áp dụng plaintext cho mọi user đi qua bean đó; đoạn thứ hai lưu password có thể đọc ngay nếu dữ liệu bị lộ. Một project học dù dùng `localhost` vẫn có thể bị publish qua tunnel, reverse proxy, IDE sharing hoặc cấu hình deploy nhầm.

Nếu cần một minh họa thật ngắn, nên:

1. Dùng user và password giả, chỉ trong bài học/unit test cụ thể.
2. Cấu hình cô lập trong test source/test profile, không đưa vào default production profile.
3. Tốt hơn là vẫn xây fixture với `BCryptPasswordEncoder` hoặc `DelegatingPasswordEncoder` để test phản ánh thực tế.
4. Không cho demo account quyền administrator mặc định.
5. Không sử dụng lại password demo ở bất kỳ hệ thống thật.
6. Bảo đảm CI/CD không vô tình bật profile test, và scan artifact/config trước khi phát hành.
7. Có bài test cấu hình production xác nhận password encoder không phải NoOp và dữ liệu password mới không ở dạng rõ.

### Profile trong Spring Boot không phải bức tường bảo mật

Ví dụ `@Profile("test")` có thể giúp cô lập bean NoOp nhưng **không tự bảo đảm an toàn** nếu profile bị bật nhầm trong môi trường public:

```java
// CHỈ là trích đoạn cảnh báo, không phải cấu hình khuyến nghị:
@Configuration
@Profile("test")
class InsecureOnlyForTests {

    @Bean
    PasswordEncoder passwordEncoder() {
        return NoOpPasswordEncoder.getInstance();
    }
}
```

Nếu dự án cần kiểm thử độ an toàn của cấu hình hiện thực, tốt hơn dùng **encoder thích nghi trong test integration**, và chọn cost factor/test fixtures sao cho test có tốc độ phù hợp mà không biến cấu hình production thành insecure.

**Không dùng NoOp chỉ để làm mọi bài test nhanh hơn** nếu bài test đang xác minh hash, migration, account state hoặc chính sách bảo mật. Những test ấy phải đi qua encoder thật để có ý nghĩa.

## 9. Ba tình huống test phải phân biệt

| Kiểu test | Có gọi `PasswordEncoder.matches` thật không? | NoOp có phù hợp? | Điều test chứng minh |
| --- | --- | --- | --- |
| `@WithMockUser` / `.with(user(...))` | Thường **không**; security context được dựng giả. | Không cần NoOp. | Kiểm tra authorization/controller với principal được cấp sẵn. |
| Unit test riêng logic định tuyến/adapter không quan tâm hash | Có thể không hoặc dùng fake. | Có thể minh họa, nhưng phải giới hạn rõ. | Hợp đồng nghiệp vụ/lookup, không chứng minh an toàn lưu password. |
| Test login qua `DaoAuthenticationProvider` / `AuthenticationManager` thật | **Có**. | Nếu dùng NoOp, không kiểm tra thực tế encoder production. | Cơ chế xác thực và trạng thái account theo cấu hình test. |
| HTTP login qua `MockMvc` cùng Spring Security filter chain | Có nếu đi qua provider thật theo cấu hình. | Nên dùng encoder production hoặc profile test hợp lý. | Hành vi từ HTTP đến provider, thất bại, quyền và status. |

### Một test “pass” có thể chứng minh điều gì?

Nếu test có:

```java
assertTrue(NoOpPasswordEncoder.getInstance()
        .matches("test123", "test123"));
```

nó chỉ chứng minh **hai chuỗi giống nhau**. Nó **không** chứng minh ứng dụng có password hashing đủ an toàn. Cũng không chứng minh auth endpoint có chống brute force, account lockout, MFA hoặc chính sách nâng cấp hash.

Một bài kiểm thử hữu ích hơn là xác nhận bất biến bảo mật của code dùng để **ghi password mới**:

```java
// Trích đoạn JUnit trong test class đã có PasswordEncoder encoder.
String encoded = encoder.encode("DemoOnly123!");

assertNotEquals("DemoOnly123!", encoded);
assertTrue(encoder.matches("DemoOnly123!", encoded));
assertFalse(encoder.matches("wrong", encoded));
```

Nếu dùng `DelegatingPasswordEncoder`, nên test ID prefix thuộc danh sách thuật toán được phép theo policy, thay vì chỉ kiểm tra `encoded != raw`; một encoder yếu vẫn có thể thêm prefix mà không băm. Với BCrypt và salt ngẫu nhiên, không assert literal hash cố định.

### Kiểm thử production không có NoOp

Có thể viết một test kiểm tra cấu hình khi tạo application context:

```java
// Trích đoạn Spring Boot integration test: đã inject PasswordEncoder.
@Test
void productionEncoderMustNotStorePlaintext() {
    String raw = "RandomTestPassword!42";
    String stored = passwordEncoder.encode(raw);

    assertNotEquals(raw, stored);
    assertTrue(passwordEncoder.matches(raw, stored));
    assertFalse(passwordEncoder.matches("wrong-password", stored));
}
```

Đoạn này **chưa kiểm tra toàn bộ bảo mật** vì vẫn có encoder yếu có thể thêm prefix. Nên bổ sung kiểm tra `{id}` theo allow-list hoặc thuộc tính hash thích nghi và test luồng cập nhật mật khẩu thật qua service/repository. Nếu ứng dụng cho phép legacy `{noop}` để đọc, test phải phân biệt **khả năng đọc legacy** với **quy định ghi mới tuyệt đối không dùng NoOp**.

## 10. Xử lý lỗi “There is no PasswordEncoder mapped for the id null”

Một tình huống hay gặp khi nâng cấp Spring Security:

```text
java.lang.IllegalArgumentException:
There is no PasswordEncoder mapped for the id "null"
```

Nguyên nhân thường gặp là database đang lưu:

```text
DemoPass123!
```

trong khi ứng dụng dùng `DelegatingPasswordEncoder`, vốn cần prefix `{id}` để biết dữ liệu được tạo bởi thuật toán nào.

**Sai cách:** thêm bean toàn cục `NoOpPasswordEncoder` hoặc cấu hình fallback về NoOp chỉ để login chạy trở lại, mà không hiểu dữ liệu cũ. Điều đó có thể làm toàn bộ hệ thống xác thực chấp nhận plaintext hoặc khiến code mới tiếp tục ghi password ở dạng rõ.

**Cách xử lý đúng theo trình tự:**

1. Xác định cấu hình encoder thật đang chạy ở từng ứng dụng/instance.
2. Kiểm kê **định dạng dữ liệu** trong DB: plaintext, BCrypt, PBKDF2, các ID khác hoặc dữ liệu bị lỗi.
3. Phân loại chính xác. Ví dụ hash BCrypt bắt đầu `$2a$...` không có prefix khác với plaintext; không được đánh đồng.
4. Định nghĩa registry decoder tương thích với dữ liệu cũ và encoder mạnh cho mọi bản ghi mới.
5. Di chuyển dữ liệu theo kế hoạch rõ ràng, có backup, logging tối thiểu và kiểm tra đa phiên bản.
6. Nếu có plaintext legacy, xử lý như **một nguy cơ đã phơi lộ**: hạn chế truy cập, xác định thời điểm và phạm vi lộ, cân nhắc buộc reset password.
7. Thử login và quy trình update/reset trong staging với dữ liệu thử nghiệm, không dump plaintext production vào log hoặc tài liệu.
8. Có chiến lược gỡ bỏ hỗ trợ NoOp/format cũ khi không còn bản ghi cần xác minh.

### Tại sao `setDefaultPasswordEncoderForMatches(NoOpPasswordEncoder...)` là rủi ro?

`DelegatingPasswordEncoder` cho phép chỉ định fallback khi ID không nhận diện được. Nếu fallback là NoOp:

- Dữ liệu **không có ID** có thể bị so như plaintext.
- Sai định dạng có thể bị chấp nhận ngoài ý muốn.
- Lỗi cấu hình/dữ liệu bị che thay vì được phát hiện.
- Các hệ thống với nhiều ứng dụng và database có thể đi vào hai chính sách khác nhau.

Chỉ nên xem fallback là một công cụ tương thích legacy **có giới hạn thời gian, dữ liệu, kiểm thử và kiểm soát truy cập rõ ràng** — không phải một cấu hình mặc định để bỏ qua mọi lỗi encoder. Với hệ thống có dữ liệu phức tạp, tốt hơn tạo **đường migration có kiểm soát theo record/profile** thay vì thử một loạt encoder không xác định.

## 11. Chuyển dữ liệu `{noop}`/plaintext sang hash có chi phí

Có hai dạng dữ liệu legacy thường gặp:

```text
A. Dạng rõ không có prefix:
   password_column = "DemoPass123!"

B. Dạng rõ với prefix:
   password_column = "{noop}DemoPass123!"
```

Cả hai đều chứa **mật khẩu có thể đọc**; prefix không tạo sự khác biệt về bảo mật lưu trữ. Nhu cầu là đưa về một dạng hash mạnh, ví dụ:

```text
C. Dạng mới:
   password_column = "{bcrypt}$2a$..."
```

Có hai hướng chuyển đổi phải xem xét riêng.

### 11.1. Nâng cấp khi đăng nhập thành công

Khi hệ thống vẫn đọc được hash cũ qua `DelegatingPasswordEncoder`, sau một lần xác minh password đúng, chương trình có quyền truy cập tạm thời vào raw password trong luồng xác thực. Lúc đó có thể **encode lại bằng thuật toán hiện hành** rồi cập nhật bản ghi.

Với `DaoAuthenticationProvider`, có thể cấu hình `UserDetailsPasswordService`:

```java
// Mã tích hợp, không phải chương trình console độc lập.
// users: UserDetailsService truy vấn kho tài khoản;
// updater: UserDetailsPasswordService cập nhật hash vào kho;
// encoder: DelegatingPasswordEncoder có registry decoder cũ và encoder mới.
DaoAuthenticationProvider dao = new DaoAuthenticationProvider(users);
dao.setPasswordEncoder(encoder);
dao.setUserDetailsPasswordService(updater);
```

Trình tự khái quát:

```text
User nhập username/password
    |
    v
DaoAuthenticationProvider tải UserDetails
    |
    v
encoder.matches(rawPassword, oldStored)
    |
    +-- Sai: không nâng cấp, từ chối login
    |
    +-- Đúng:
          |
          +--> encoder.upgradeEncoding(oldStored) ?
                 |
                 +-- false: giữ hash phù hợp
                 |
                 +-- true:
                       newStored = encoder.encode(rawPassword)
                       UserDetailsPasswordService.updatePassword(
                           user, newStored)
                       |
                       v
                 Lưu hash mới theo transaction an toàn
```

**Không phải cứ `upgradeEncoding(...) == true` là database được cập nhật tự động.** Provider phải có một dịch vụ update phù hợp và chương trình phải bảo đảm logic concurrency, transaction, revocation/expiry và logging an toàn.

Nếu có nhiều session hoặc reset password đồng thời, một login cũ không được ghi đè mật khẩu vừa được reset. Dùng optimistic locking/version hoặc câu lệnh update có điều kiện theo record/version của hash cũ. Trong quá trình rolling deploy, mọi node còn hoạt động phải biết đọc hash theo ID mới.

### 11.2. Xử lý plaintext offline

Khác với bcrypt, dữ liệu legacy plaintext **có thể chuyển thành hash mới mà không đợi user đăng nhập**, vì raw password đang có sẵn. Tuy nhiên đó **không phải lợi thế cần giữ**: việc database từng chứa mật khẩu dạng rõ là một tình trạng rủi ro, và dữ liệu có thể đã bị đọc trước khi migration.

Nếu chọn batch rehash:

1. Giới hạn quyền truy cập DB và bản backup chứa plaintext, chỉ xử lý trong môi trường và quy trình an toàn.
2. Xác minh trường nào thật sự là plaintext, trường nào là hash có/không có prefix; không encode nhầm hash như raw.
3. Tạo hash mới với encoder hiện hành và ghi nguyên tử, giữ khả năng rollback hợp lệ mà không tạo thêm bản sao plaintext.
4. Ghi số lượng bản ghi chuyển đổi và tình trạng lỗi, **không log raw password**.
5. Dọn bỏ tệp tạm, dump, trace, bản backup dễ truy cập chứa plaintext theo chính sách bảo mật và lưu trữ.
6. Xem xét reset password cho user, đặc biệt nếu có dấu hiệu hoặc không loại trừ được nguy cơ lộ dữ liệu.

Rehash offline **không thể thu hồi những mật khẩu đã có thể bị lộ**. Vì vậy đánh giá sự cố và thông báo người dùng theo chính sách tổ chức có thể cần được thực hiện song song.

### 11.3. Đừng sửa prefix không có kế hoạch

Một số sai lầm:

- Đổi `DemoPass123!` thành `{bcrypt}DemoPass123!` mà không thực hiện BCrypt: chắc chắn sai format.
- Thêm `{noop}` vào mọi bản ghi khi DB đang chứa cả BCrypt và PBKDF2: làm mất khả năng xác thực password hợp lệ.
- Xóa `{noop}` rồi coi chuỗi còn lại là hash: giá trị còn lại là plaintext.
- Dùng cùng ID `bcrypt` cho các profile không tương thích: khiến dữ liệu cũ không đọc được.
- Hash một lần rồi hash tiếp **encoded hash như raw password** trong quá trình cập nhật: làm password gốc không còn khớp.
- Thay password encoder production nhưng không cấu hình đồng thời bên đăng ký, đổi password, reset password và login.

**Một migration tốt phải bảo toàn tính đúng đắn của password authentication**, xử lý được concurrent writes và làm giảm dần sự hiện diện của plaintext thay vì để legacy sống mãi.

## 12. Cấu hình Spring Boot minh họa và lựa chọn phù hợp hơn

### 12.1. Không nên dùng bean NoOp toàn cục

**Mẫu phải tránh ở production:**

```java
@Configuration
class UnsafePasswordConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return NoOpPasswordEncoder.getInstance();
    }
}
```

Đoạn trên là **trích đoạn** của một project đã có imports/configuration, không phải chương trình độc lập. Nó có thể làm việc tạo password mới tiếp tục lưu plaintext nếu service gọi bean này để encode.

### 12.2. Bean theo chính sách hiện đại

Ví dụ điển hình cho ứng dụng đang dùng Spring Security 6.5:

```java
@Configuration
class SafePasswordConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
```

Bean này thường ghi password mới với prefix `{bcrypt}` và hỗ trợ nhiều ID legacy để match, bao gồm `noop` nếu registry mặc định có mapping đó. **Có bean “safe” không có nghĩa mọi bản ghi DB đều an toàn**, bởi hệ thống vẫn có thể còn dữ liệu `{noop}...`. Sau khi migration, cần kế hoạch loại bỏ khả năng chấp nhận ID plaintext khỏi đường production theo chính sách, thay vì chỉ dựa mã hóa mới.

Cấu hình này là **trích đoạn Spring Boot**, yêu cầu các imports `Configuration`, `Bean`, `PasswordEncoder`, `PasswordEncoderFactories` và các bean user store/security chain thích hợp. Nó không tự tạo endpoint REST đăng nhập.

### 12.3. Registry không đọc `noop` khi đã kết thúc migration

Nếu không còn bất kỳ bản ghi legacy plaintext, có thể xây một registry **chỉ chứa encoder đã được phê duyệt**:

```java
PasswordEncoder encoder = new DelegatingPasswordEncoder(
        "bcrypt",
        Map.of("bcrypt", new BCryptPasswordEncoder()));
```

Cần imports `Map`, `PasswordEncoder`, `DelegatingPasswordEncoder` và `BCryptPasswordEncoder`. Khi đó giá trị `{noop}...` sẽ không được chấp nhận vì thiếu mapping `noop`. **Chỉ áp dụng sau khi đã xác minh dữ liệu và các ứng dụng khác đều tương thích**, không xóa decoder khi vẫn còn user chưa được chuyển đổi.

Đây là ví dụ registry tối thiểu, không khẳng định chỉ BCrypt mới an toàn. Các ứng dụng có thể dùng Argon2id, scrypt hoặc PBKDF2 theo policy/hạ tầng thực tế. Nếu hỗ trợ nhiều thuật toán, mỗi ID nên có một ý nghĩa rõ ràng và stable; chỉ các thuật toán được chấp thuận mới được dùng cho password mới.

## 13. Tính đúng đắn của bài demo và ranh giới bảo mật

Một trong những lý do NoOp còn được nhắc tới là **tốc độ và sự đơn giản**: người học không phải tạo hash chỉ để hiểu `UserDetailsService` và `AuthenticationManager`. Nhưng sự tiện lợi ấy chỉ có giá trị trong **môi trường đã bị giới hạn**.

Một bài demo có thể kiểm tra thành công:

```text
client credentials = "learner / demo-password"
UserDetailsService trả user có password = "{noop}demo-password"
DelegatingPasswordEncoder chọn "noop"
NoOpPasswordEncoder so chuỗi đúng
DaoAuthenticationProvider trả Authentication đã xác thực
```

Kết quả xác thực **đúng theo cấu hình**; cấu hình **không an toàn để dùng với tài khoản thật**.

Phân biệt ba thuộc tính:

| Thuộc tính | Câu hỏi | NoOp có đáp ứng không? |
| --- | --- | --- |
| **Functional correctness** | Username và password demo có đi qua provider, lỗi sai mật khẩu có bị từ chối? | Có thể có. |
| **Password storage security** | DB bị lộ thì password có được bảo vệ bằng one-way adaptive hashing? | **Không**. |
| **Application security** | Có TLS, CSRF/rate limiting đúng, MFA, session protection, kiểm tra quyền, audit? | **NoOp không đảm nhiệm** bất kỳ cơ chế nào trong số đó. |

Một hệ thống không thể lấy việc “test login pass” để kết luận mọi lớp bảo mật đều đạt. Cách kiểm thử và cấu hình phải tương ứng với mục đích.

### Demo dùng HTTP Basic có làm NoOp an toàn hơn không?

Không. HTTP Basic gửi credential trong header theo encoding Base64 (không phải mã hóa mật mã), thường yêu cầu HTTPS để bảo vệ trên đường truyền. Ngay cả nếu kết nối dùng TLS đúng, **mật khẩu vẫn có thể nằm dạng rõ trong database** khi dùng NoOp. Bảo vệ transmission và bảo vệ password at rest là **hai bài toán khác nhau**.

### Demo chỉ trên localhost có an toàn tuyệt đối?

Không. Localhost giúp hạn chế phạm vi truy cập trong nhiều tình huống, nhưng còn rủi ro từ tài khoản mẫu bị commit lên repository, tự động deploy nhầm, container lộ port, bản chụp log hoặc người dùng sau copy code mẫu. Hướng dẫn học cần gắn cảnh báo, còn ứng dụng thật cần cơ chế cấu hình không thể vô tình bật NoOp.

## 14. Những sai lầm thường gặp

1. **“`encode` nghĩa là mật khẩu đã băm.”** Sai với NoOp: output vẫn là raw password.
2. **“`{noop}` là mã hóa.”** Sai: đó là ID chọn encoder, mật khẩu sau prefix vẫn ở dạng rõ.
3. **“Có `DelegatingPasswordEncoder` nên database toàn hash mạnh.”** Sai: factory có thể match dữ liệu legacy `{noop}`.
4. **“`NoOpPasswordEncoder.getInstance()` là lựa chọn mặc định Spring Security mới.”** Sai: chỉ dành legacy/test; factory mặc định từ Spring Security 5+ dùng delegation và chọn encoder hiện hành để ghi.
5. **“Dùng `User.withDefaultPasswordEncoder()` tức NoOp.”** Sai: builder tạo hash qua DelegatingPasswordEncoder; nhưng vẫn không phù hợp production vì hard-coded raw password.
6. **“Dữ liệu có prefix `{bcrypt}` thì chắc chắn là BCrypt hash.”** Chưa chắc nếu dữ liệu bị sửa sai format; phải thực sự tạo bằng encoder tương ứng.
7. **“NoOp trực tiếp hiểu `{noop}`.”** Sai: prefix được xử lý bởi delegating, NoOp so chuỗi phía dưới.
8. **“Chỉ có một tài khoản demo nên không cần lo.”** Một user có quyền vẫn là cửa vào nếu được triển khai public.
9. **“Bỏ cảnh báo `@Deprecated` bằng annotation là an toàn.”** Sai: annotation chỉ ảnh hưởng compiler warning.
10. **“Đổi bean sang BCrypt thì mọi mật khẩu cũ tự chuyển.”** Sai: cần decoder đúng profile và kế hoạch migration/update.
11. **“Password raw lưu DB nhưng HTTPS che hết rồi.”** HTTPS bảo vệ đường truyền, không bảo vệ dữ liệu đã lưu.
12. **“Cho phép fallback NoOp cho mọi hash thiếu ID để nhanh sửa lỗi.”** Có thể làm dữ liệu sai format được chấp nhận như plaintext và che sự cố.
13. **“Dùng `@WithMockUser` chứng minh password encoder.”** Sai: mock thường bỏ qua provider và password matching.
14. **“`UserDetailsService` tìm đúng user nên password đã được xác thực.”** Không: service tải record, provider/encoder mới verify.
15. **“Đăng nhập được nghĩa user có quyền truy cập mọi tài nguyên.”** Không: authentication và authorization là các bước riêng.
16. **“Có thể dùng cùng mật khẩu demo làm password admin.”** Không: credential mẫu không được sử dụng cho tài khoản thật.
17. **“Hash password trong log không sao vì không phải plaintext.”** Không: hash là password verifier nhạy cảm và hỗ trợ tấn công đoán offline khi bị lộ.
18. **“Lưu plaintext rồi sau này mới băm là không có vấn đề.”** Rủi ro lộ dữ liệu đã tồn tại từ lúc đầu; rehash không xóa quá khứ.
19. **“Thay prefix một phát là migration thành công.”** Không: prefix phải phản ánh đúng thuật toán thật sự đã tạo giá trị.
20. **“NoOp có thể dùng làm encoder cho mọi integration test.”** Nếu test mục tiêu là security/hash/migration, nó không kiểm chứng hệ thống production.
21. **“Chỉ cần bật profile test, mọi secret demo được cách ly.”** Profile có thể bị kích hoạt nhầm; còn cần ràng buộc deploy và test kiểm tra.
22. **“BCrypt bảo đảm mọi password đều mạnh.”** Password yếu vẫn dễ đoán hơn; cần thêm password policy phù hợp, chống credential stuffing và MFA khi thích hợp.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `NoOpPasswordEncoder.encode("abc123")` trả điều gì? Vì sao không an toàn?

**Đáp án:** Về cơ bản trả chính `abc123`. Kẻ có bản ghi DB đọc được mật khẩu mà không cần brute force hash.

**Câu 2.** `{noop}abc123` khác `abc123` ở điểm nào?

**Đáp án:** Prefix `{noop}` dùng cho `DelegatingPasswordEncoder` chọn đúng decoder. Cả hai vẫn có raw password; prefix không tạo bảo vệ mật mã.

**Câu 3.** Vì sao `noop.matches("abc123", "{noop}abc123")` trả false nhưng delegating có thể trả true?

**Đáp án:** NoOp trực tiếp so toàn bộ chuỗi; delegating tách `{noop}` rồi đưa phần `abc123` cho NoOp.

**Câu 4.** Sau khi chuyển sang factory delegating, bản ghi `{noop}abc123` có bị từ chối tự động không?

**Đáp án:** Không. Registry mặc định có thể vẫn hỗ trợ `noop` để đọc legacy; chỉ việc ghi password mới thường dùng BCrypt. Muốn loại bỏ plaintext cần migration và thu hẹp registry theo policy.

**Câu 5.** `User.withDefaultPasswordEncoder()` có tương đương NoOp không?

**Đáp án:** Không. Nó tự encode bằng DelegatingPasswordEncoder (thường là BCrypt trong Spring Security 6.5). Nhưng raw password hard-coded trong code nên API không dành production.

**Câu 6.** Nếu thấy “There is no PasswordEncoder mapped for the id null”, có nên gắn `NoOpPasswordEncoder` cho toàn hệ thống?

**Đáp án:** Không. Phải xác minh định dạng DB, phân loại hash/legacy và có kế hoạch chuyển đổi. Bật NoOp toàn cục có thể chấp nhận hoặc tiếp tục ghi plaintext.

**Câu 7.** `upgradeEncoding("{noop}abc123")` trả true có tự cập nhật DB không?

**Đáp án:** Không. Nó là tín hiệu nâng cấp; cần luồng xác thực thành công, encoder mới và dịch vụ ghi hash với transaction/concurrency control.

**Câu 8.** Khi plaintext legacy có sẵn ở DB, có thể hash offline không?

**Đáp án:** Có thể, nhưng việc plaintext từng tồn tại là rủi ro và không thể đảo ngược mọi hậu quả nếu đã bị đọc. Cần bảo vệ quá trình migration, đánh giá khả năng lộ và chính sách reset password.

**Câu 9.** Unit test `@WithMockUser` xanh có chứng minh `BCryptPasswordEncoder` chạy không?

**Đáp án:** Không. Nó có thể thiết lập context trực tiếp; test password phải đi qua provider/encoder thật.

**Câu 10.** Tại sao HTTPS không đủ để làm `NoOpPasswordEncoder` an toàn?

**Đáp án:** HTTPS bảo vệ credential khi truyền qua mạng. NoOp vẫn lưu password nguyên bản trong DB, đây là vấn đề riêng về bảo vệ dữ liệu khi lưu.

**Câu 11.** Nên kiểm tra điều gì trước khi gỡ decoder `noop`?

**Đáp án:** Không còn bản ghi plaintext cần dùng, mọi node ứng dụng đọc được format mới, có kế hoạch rollback, xử lý tài khoản chưa đăng nhập và các luồng reset/update.

**Câu 12.** Khi demo thật sự cần đơn giản, nên làm gì?

**Đáp án:** Tạo password hash bằng BCrypt/DelegatingPasswordEncoder cho fixture hoặc dùng một cấu hình NoOp được cô lập chặt cho test học tập, tuyệt đối không cho nó đi vào môi trường công khai.

## 16. Tài liệu tham khảo chính thức

- [Spring Security 6.5.11 — NoOpPasswordEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/NoOpPasswordEncoder.html): class deprecated, singleton `getInstance()`, chỉ dùng legacy/testing.
- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): lịch sử NoOp, password hash thích nghi, `DelegatingPasswordEncoder`, `{id}` và cảnh báo cấu hình plaintext.
- [Spring Security 6.5 — In-Memory Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/in-memory.html): `InMemoryUserDetailsManager`, `User.withDefaultPasswordEncoder()` và giới hạn demo.
- [Spring Security 6.5.11 — PasswordEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/PasswordEncoder.html): `encode`, `matches` và `upgradeEncoding`.
- [Spring Security 6.5.11 — DelegatingPasswordEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html): versioned IDs, registry, default fallback và upgrade.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): cách provider tải `UserDetails` và đối chiếu password.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): thuật toán lưu mật khẩu thích nghi, work factor, salt, migration.
- [Spring Security 6.5.11 — User API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.html): builder `withDefaultPasswordEncoder` và cảnh báo raw password hard-coded.

**Kết luận:** `NoOpPasswordEncoder` tồn tại vì mục đích tương thích cũ và đơn giản hóa một số bài demo, nhưng **không thực hiện bảo vệ mật khẩu khi lưu**. Prefix `{noop}` chỉ định tuyến tới cơ chế này; không phải hash. Trong ứng dụng thật, phải dùng encoder thích nghi với format/version thống nhất, kiểm thử được đường đăng nhập thật, quản lý nâng cấp dữ liệu legacy và gỡ dần khả năng chấp nhận plaintext theo một kế hoạch an toàn.