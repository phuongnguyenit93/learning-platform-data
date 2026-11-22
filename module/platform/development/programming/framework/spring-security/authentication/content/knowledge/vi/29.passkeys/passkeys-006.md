# Lưu user entity, credential và quản lý nhiều passkey của một tài khoản

Một tài khoản ứng dụng có thể sở hữu **nhiều passkey**: ví dụ một passkey trên điện thoại, một passkey trong trình quản lý mật khẩu và một passkey trên khóa bảo mật phần cứng. Khi triển khai đăng nhập WebAuthn/Passkey trong Spring Security, bài toán dữ liệu không chỉ là “lưu public key” mà còn là **giữ mối liên hệ ổn định giữa tài khoản ứng dụng, WebAuthn user entity và từng credential**, để đăng nhập, liệt kê, đặt nhãn, thu hồi và khôi phục tài khoản mà không gán nhầm passkey cho người khác.

Trong Spring Security 6.5 (Servlet), hai kho lưu trữ chính là:

- `PublicKeyCredentialUserEntityRepository`: lưu **WebAuthn user entity** của một tài khoản.
- `UserCredentialRepository`: lưu các **CredentialRecord**, có thể có nhiều bản ghi liên kết với **một user entity**.

Bài học giải thích mô hình 1:N, dữ liệu cần/không được lưu, hành vi nhiều passkey, các repository JDBC mặc định, ví dụ **Java 17+ / Spring Boot 3.5 / Spring Security 6.5** và API quản lý passkey có kiểm tra quyền sở hữu. Nội dung liên quan WebAuthn **Servlet**; khi dùng Spring Security 7.x cần đối chiếu dependency/API đúng nhánh, đặc biệt module WebAuthn đã được đóng gói khác.

## 1. Ba đối tượng dễ bị nhầm

### 1.1. Application user — tài khoản nghiệp vụ

Tài khoản trong hệ thống có thể chứa:

- `account_id`/ID nội bộ bền vững (ví dụ UUID);
- `username`, email đã xác minh, tên hiển thị;
- trạng thái hoạt động/khóa, tenant;
- vai trò/`GrantedAuthority` và dữ liệu hồ sơ.

Tài khoản này thường được quản lý bởi bảng `app_users` và `UserDetailsService` hoặc một identity service riêng. Nó tồn tại **độc lập** với phương thức đăng nhập: cùng một tài khoản có thể vừa có password, vừa có 2 passkey.

**Không nhầm `UserDetails` của Spring Security với `PublicKeyCredentialUserEntity` của WebAuthn.** Hai kiểu có trách nhiệm khác nhau. UserDetails mô tả user và quyền dùng trong xác thực/ủy quyền; WebAuthn user entity là đối tượng định danh được gửi vào quá trình tạo credential.

### 1.2. PublicKeyCredentialUserEntity — định danh user trong WebAuthn

Theo WebAuthn, user entity có ba thuộc tính cơ bản:

| Thuộc tính / Java API | Ý nghĩa | Quy tắc lưu |
| --- | --- | --- |
| `getId()` → `Bytes` | **User handle** dạng byte không trong suốt, định danh ổn định của tài khoản ở phạm vi Relying Party (RP) | Sinh ngẫu nhiên an toàn, duy nhất trong RP, tối đa 64 byte; không thay mỗi lần tạo passkey |
| `getName()` → `String` | Tên tài khoản người dùng đọc được, ví dụ `alice` | Không coi là khóa bảo mật chính; có thể đổi theo chính sách tên |
| `getDisplayName()` → `String` | Nhãn người dùng dễ đọc, ví dụ “Alice Nguyễn” | Dùng cho UI, không dùng để xác minh quyền sở hữu |

`PublicKeyCredentialUserEntityRepository` có các thao tác `findByUsername(String)`, `findById(Bytes)`, `save(PublicKeyCredentialUserEntity)` và `delete(Bytes)`. Với cùng một account, các lần đăng ký tiếp theo nên **tái sử dụng user handle hiện có** thay vì tạo một ID WebAuthn mới mỗi lần.

**Tại sao không dùng email làm user handle?** Email có thể đổi và lộ thông tin cá nhân. WebAuthn yêu cầu handle không chứa thông tin trực tiếp nhận dạng người dùng; nên dùng byte ngẫu nhiên, lưu mapping bền vững giữa handle và tài khoản.

### 1.3. CredentialRecord — một passkey được đăng ký

`CredentialRecord` đại diện **một public-key credential** đã được xác minh khi đăng ký. Một user entity có thể liên kết 0, 1 hoặc N CredentialRecord.

| Field / getter trong Spring Security 6.5 | Mục đích |
| --- | --- |
| `getCredentialId()` → `Bytes` | Định danh credential, dùng để tìm đúng public key và gỡ đúng bản ghi |
| `getUserEntityUserId()` → `Bytes` | Khóa liên kết đến **user handle** của WebAuthn user entity |
| `getPublicKey()` | Public key dạng COSE để xác minh chữ ký ở các lần đăng nhập |
| `getSignatureCount()` | Bộ đếm chữ ký nếu authenticator hỗ trợ, hữu ích cho phát hiện dấu hiệu bất thường |
| `getLabel()` | Nhãn con người nhập để phân biệt passkey, ví dụ “Security key dự phòng” |
| `getCreated()` / `getLastUsed()` | Thời điểm tạo và dùng gần nhất để hiển thị/quản trị |
| `getTransports()` | Hint về transport do authenticator công bố, không phải bằng chứng nhận diện thiết bị |
| `isBackupEligible()` / `isBackupState()` | Trạng thái hỗ trợ backup/sync và backup hiện tại |
| `isUvInitialized()` | Thông tin đã có user verification trong đời credential theo dữ liệu được ghi nhận |
| `getAttestationObject()` / `getAttestationClientDataJSON()` | Dữ liệu attestation lúc đăng ký, tùy chính sách lưu/đánh giá |

**Không lưu private key của passkey trên server.** Authenticator hoặc nền tảng quản lý passkey giữ phần private key; server giữ credential ID, public key và metadata phục vụ xác minh. “Passkey nằm trong database server” nghĩa là **bản ghi công khai của credential**, không phải sao chép secret từ điện thoại.

### 1.4. Sơ đồ quan hệ

~~~text
Application Account: account_id = 7f42...             (business identity)
    │
    │ ánh xạ ổn định: một tài khoản
    ▼
WebAuthn User Entity: id = opaque userHandle           (1)
    name        = "alice"
    displayName = "Alice"
    │
    │ getUserEntityUserId() = userEntity.getId()
    ├────────────── Credential Record A                (N)
    │                 credentialId = bytes-A
    │                 label = "Điện thoại"
    │                 publicKey = COSE-A
    │                 created/lastUsed/signCount/BE/BS
    │
    ├────────────── Credential Record B
    │                 credentialId = bytes-B
    │                 label = "Khóa bảo mật dự phòng"
    │                 publicKey = COSE-B
    │
    └────────────── Credential Record C
                      credentialId = bytes-C
                      label = "Trình quản lý passkey"
                      publicKey = COSE-C
~~~

**Bất biến quan trọng:**

1. `account_id` ứng dụng có **một** WebAuthn user handle ổn định trong một RP.
2. `credentialId` định danh **một credential**, không phải ID user hay ID điện thoại.
3. Mỗi credential phải trỏ về **đúng user handle**; không gán lại credential ID từ user A sang user B dựa vào email hoặc tên hiển thị.
4. Một user có thể có N credentials. Xóa một credential **không xóa user entity** hoặc các credential khác.
5. User handle không được tái sử dụng cho một tài khoản người khác khi tài khoản cũ bị xóa.
6. `label` chỉ là metadata để hiển thị, không quyết định quyền sở hữu, tính hợp lệ của signature hay cấp role.

## 2. Nhiều passkey khác với passkey được đồng bộ

Một tài khoản có thể đăng ký **nhiều credential IDs** bằng nhiều authenticator. Tuy nhiên, passkey trong trình quản lý mật khẩu hoặc hệ sinh thái thiết bị có thể **được đồng bộ giữa các thiết bị**. Khi được sync, **cùng một credential** có thể xuất hiện trên hai thiết bị nhưng phía RP vẫn chỉ lưu **một CredentialRecord** vì credential ID/public key không đổi.

| Tình huống | Số CredentialRecord điển hình | Ý nghĩa |
| --- | --- | --- |
| Đăng ký lần 1 trên điện thoại | 1 | Tạo credential A |
| Đăng ký lần 2 trên security key | 2 | Tạo credential B độc lập |
| Đăng ký lần 3 trong passkey manager | 3 | Tạo credential C độc lập |
| Passkey C đồng bộ sang laptop | **Vẫn 3** | Không nhất thiết tạo credential mới ở server |
| Người dùng đổi nhãn credential B | Vẫn 3 | Chỉ đổi metadata label |
| Người dùng thu hồi credential A trên RP | Còn 2 | Xác thực bằng A phải bị server từ chối |
| Người dùng gỡ bản sao đã sync trên một thiết bị | Có thể vẫn 3 | Việc xóa bản sao cục bộ không nhất thiết thu hồi credential ở RP |

Vì vậy **không dùng tên thiết bị làm khóa chính**. Tên “iPhone của tôi” do user nhập là metadata, có thể trùng hoặc không còn đúng sau khi đổi thiết bị. Nếu muốn thống kê số thiết bị có bản sao synced passkey, server thường **không có bằng chứng đầy đủ** để suy ra từ số CredentialRecord.

`backupEligible` (BE) cho biết khả năng được sao lưu/đồng bộ, `backupState` (BS) cho biết trạng thái backup được báo cáo. Đây là tín hiệu bổ sung, **không** phải bằng chứng chính xác “credential hiện nằm trên bao nhiêu máy”. Với passkey sync, `signatureCount` đôi khi bằng 0 hoặc không tăng đơn điệu giữa thiết bị; không tự động khóa mọi tài khoản chỉ vì counter không tăng, mà cần chính sách dựa trên loại authenticator và kết quả validator.

## 3. Lược đồ dữ liệu: ánh xạ đúng, không tự dựng lại schema Spring

### 3.1. Mô hình logic của hệ thống

Dưới đây là **mô hình quan hệ khái niệm**, **không phải DDL chính thức của `Jdbc*Repository`**:

~~~text
APPLICATION_USER
  account_id       PK
  username         UNIQUE
  email_verified
  enabled
      │ 1
      ▼ 1
WEBAUTHN_USER_ENTITY
  user_handle      PK, UNIQUE, opaque bytes
  account_id       UNIQUE -> APPLICATION_USER
  name
  display_name
      │ 1
      ▼ N
WEBAUTHN_CREDENTIAL
  credential_id    PK, opaque bytes
  user_handle      FK -> WEBAUTHN_USER_ENTITY
  public_key_cose
  signature_count
  label
  created_at, last_used_at
  backup_eligible, backup_state, transports, ...
~~~

Một database production phải ràng buộc:

- `credential_id` **UNIQUE** toàn hệ thống RP.
- `user_handle` **UNIQUE** cho user entity, và mapping tới đúng `account_id` ổn định.
- Mỗi credential lưu user handle đã được xác minh trong registration, có khóa ngoại hoặc kiểm tra toàn vẹn tương đương.
- Tên label không cần UNIQUE và không nên là khóa truy vấn xác thực.
- Chuỗi public key, credential id và handle cần lưu dạng binary/base64url có quy tắc mã hóa nhất quán; đừng biến byte thành Java `String` theo charset mặc định.

Trong ứng dụng nhiều tenant, thiết kế namespace rõ ràng: một RP có `rpId` nhất định, danh tính account có thể cần kết hợp tenant+account ID. Không tái sử dụng user handle giữa các tenant/tài khoản chỉ vì trùng email.

### 3.2. Spring Security 6.5 đã có JDBC repositories

Spring Security 6.4 đưa WebAuthn/Passkey vào framework cùng repository **in-memory**. Spring Security **6.5 bổ sung triển khai JDBC**:

- `JdbcPublicKeyCredentialUserEntityRepository`;
- `JdbcUserCredentialRepository`.

Javadoc chỉ rõ các bảng cần được tạo từ resource:

~~~text
classpath:org/springframework/security/user-entities-schema.sql
classpath:org/springframework/security/user-credentials-schema.sql
~~~

Đây mới là **schema thực tế được các lớp JDBC mặc định mong đợi**. Không lấy bảng khái niệm ở mục 3.1 rồi tự tạo và kỳ vọng những câu SQL của `JdbcUserCredentialRepository` tự khớp. Muốn đổi tên bảng/cấu trúc, cần implementation repository riêng hoặc sửa đúng câu SQL theo API hỗ trợ của phiên bản.

Hai repo lưu khác nhau:

| Repository | Tác vụ |
| --- | --- |
| `PublicKeyCredentialUserEntityRepository` | `findByUsername`, `findById`, `save`, `delete` user entity |
| `UserCredentialRepository` | `findByCredentialId`, `findByUserId`, `save`, `delete` credential |
| `UserDetailsService` của ứng dụng | Ánh xạ username với user, trạng thái account, quyền nghiệp vụ |

**Không nhầm user schema** của `JdbcUserDetailsManager` với hai schema WebAuthn ở trên. Dùng JDBC WebAuthn **không tự khiến** user/password/roles của ứng dụng chuyển sang JDBC; chúng là các storage concerns độc lập.

### 3.3. Default in-memory dùng để thử, JDBC dùng cho shared state

| Lựa chọn | Điểm mạnh | Giới hạn |
| --- | --- | --- |
| `MapPublicKeyCredentialUserEntityRepository` và `MapUserCredentialRepository` | Đơn giản, phù hợp sample/test | Không bền vững qua restart và không chia sẻ giữa các node |
| `JdbcPublicKeyCredentialUserEntityRepository` và `JdbcUserCredentialRepository` | Có thể lưu chung qua nhiều instance khi dùng cùng database | Cần schema/migration, transaction, backup, availability, giới hạn truy cập |
| Custom repositories | Kết nối mô hình user/credential hiện có | Phải tự đảm bảo hợp đồng Spring, atomicity, uniqueness, ACL, concurrent updates |

Nếu server chạy 3 replica mà mỗi replica giữ in-memory repository riêng, registration đi qua node A còn login đi qua node B có thể không tìm được credential. Session sticky không phải cách duy nhất hay đầy đủ để giải quyết vấn đề; cần **shared credential persistence** và cấu hình challenge/session đúng.

### 3.4. Quy tắc không mất handle khi đổi username

Giả sử user `alice` đổi username thành `alice.new`. **Không tạo user handle mới và bỏ các credential cũ**. Thay đổi nên được điều phối theo workflow có transaction:

1. Xác minh tài khoản đã đăng nhập và quyền đổi username.
2. Thay thông tin hiển thị/tên nghiệp vụ theo policy.
3. Cập nhật mapping `username → WebAuthn user entity` nhưng **giữ nguyên `userEntity.getId()`**.
4. Đảm bảo mọi CredentialRecord còn tham chiếu đúng handle.
5. Kiểm tra đăng nhập bằng cả các passkey đã đăng ký trước đó.
6. Nếu tên user dùng làm key trong repository, tránh trạng thái tạm có cả tên cũ và tên mới gây trùng hoặc lộ danh tính.

Cần kiểm tra semantics cụ thể của `save` và `delete` khi tự triển khai repository hoặc làm migration; không giả định thao tác `save` của mỗi JDBC backend sẽ tự cập nhật mọi bảng user/tenant theo ý ứng dụng.

## 4. Luồng registration phải giữ user entity ổn định

### 4.1. Đăng ký passkey đầu tiên

~~~text
User alice đã đăng nhập bằng phương thức bootstrap an toàn
           │
           ▼
POST /webauthn/register/options + CSRF
           │
           ▼
Spring WebAuthn: lấy/khởi tạo user entity của alice
   userHandle = opaque bytes U (giữ ổn định)
   challenge và rpId/origin policy
           │
           ▼
Browser navigator.credentials.create(options)
           │ authenticator tạo key pair
           │ private key ở authenticator; public key đi về server
           ▼
POST /webauthn/register + CSRF
           │
           ▼
Spring xác minh challenge, origin, rpId, attestation/chính sách
           │
           ▼
UserCredentialRepository.save(CredentialRecord A)
   credentialId = A
   userEntityUserId = U
   publicKey = publicKeyA
           │
           ▼
Trang quản lý hiển thị: "Passkey A"
~~~

Theo tài liệu Spring Security 6.5 Servlet, registration gồm **`POST /webauthn/register/options`** để lấy options, sau đó **`POST /webauthn/register`** để hoàn thành đăng ký. Các request POST cần **CSRF token** phù hợp khi CSRF bật. Thư viện/filters chịu trách nhiệm kiểm tra dữ liệu WebAuthn; không tự tin payload do JavaScript gửi chỉ vì UI đã chạy thành công.

### 4.2. Đăng ký passkey thứ hai

Khi alice đăng ký bằng security key khác:

- `PublicKeyCredentialUserEntityRepository.findByUsername("alice")` phải trả **cùng user handle U**.
- Authenticator sinh **credentialId B** và publicKeyB khác.
- `UserCredentialRepository.save(B)` lưu thêm một record: `B.userEntityUserId == U`.
- **Không** thay thế record A bằng B; **không** xóa A khi user đăng ký B.
- Khi tạo options cho credential mới, `excludeCredentials` có thể chỉ ra ID đã đăng ký để giảm đăng ký trùng credential trên authenticator; không nên tự đặt danh sách từ input chưa xác minh của client.

Những thao tác sinh/đăng ký của Spring cần bảo đảm **người đang thao tác** là tài khoản mục tiêu, đặc biệt khi application có endpoint “thêm passkey cho user X”. Không lấy user ID tùy ý trong request body và gắn credential mới vào người khác; dùng principal xác thực hiện tại và chính sách re-authentication/step-up khi cần.

### 4.3. Authentication bằng một trong các passkey

~~~text
Login: POST /webauthn/authenticate/options + CSRF
      ↓ challenge duy nhất / RP ID
Browser navigator.credentials.get(options)
      ↓ chọn bất kỳ credential A hoặc B có sẵn
POST /login/webauthn + assertion
      ↓ tra credentialId (A hoặc B)
UserCredentialRepository.findByCredentialId(...)
      ↓ publicKeyA/publicKeyB + userHandle U
Relying Party kiểm tra signature, challenge, origin, rpIdHash,
UP/UV và các yêu cầu policy
      ↓ xác định U → alice
Spring Authentication + quyền ứng dụng
      ↓
Authenticated session
~~~

Một tài khoản có hai passkey không có nghĩa cần **dùng cả hai cùng lúc**. Theo thiết kế phổ biến, một assertion hợp lệ từ **bất kỳ credential chưa thu hồi** của alice là đủ để xác thực tài khoản alice. Các mức đảm bảo/step-up riêng có thể đặt điều kiện bổ sung.

## 5. Ví dụ Spring Boot 3.5 + Spring Security 6.5 (Servlet, JDBC)

Ví dụ này cung cấp cấu hình **WebAuthn + JDBC user entity/credential** và một endpoint quản lý passkey. Mã Java dùng package `example.passkeys`; đặt các file đúng tên/package vào project Spring Boot 3.5 có Java 17+. **Không có private key server hay credential thật** được tạo sẵn; để thử registration/authentication phải dùng browser WebAuthn hỗ trợ và một authenticator.

**Điều kiện:** JDK 17+, Spring Security **6.5.x**, Spring Boot 3.5.x, HTTPS ở production. Demo local dùng `localhost` và H2 in-memory; H2 chỉ minh họa JDBC repository, **không phải persistence production**.

### 5.1. Dependency Gradle

Trong `build.gradle` của project đã có Spring Boot plugin/BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    // Theo tài liệu Spring Security 6.5 Servlet:
    implementation 'com.webauthn4j:webauthn4j-core:0.29.7.RELEASE'

    runtimeOnly 'com.h2database:h2'  // Chỉ dành cho lab local.
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-boot-starter-security` đã kéo `spring-security-web` trong ứng dụng servlet; `webauthn4j-core` được tài liệu 6.5 yêu cầu như trên. **Không sao chép nguyên dependency này sang Spring Security 7.x**: tài liệu nhánh 7.x mô tả module `spring-security-webauthn` và các phụ thuộc khác. Với mỗi nhánh, hãy dùng đúng BOM và docs đã chọn.

### 5.2. DataSource và khởi tạo schema cho lab

Tệp `src/main/resources/application.properties`:

~~~properties
server.port=8080

spring.datasource.url=jdbc:h2:mem:passkey_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:org/springframework/security/user-entities-schema.sql,classpath:org/springframework/security/user-credentials-schema.sql
~~~

Với dependencies đúng và các resource SQL tồn tại trong phiên bản, Spring Boot chạy initialization scripts trên H2 lab. Nếu script/schema không tương thích database đang dùng, **đừng bỏ schema hay nuốt lỗi**; kiểm tra SQL và triển khai migration tương ứng bằng Flyway/Liquibase cho PostgreSQL/MySQL/production.

Lưu ý:

- Hai resource trên thuộc storage **user entity/credential** của Spring Security, không tạo bảng application user với password/roles.
- H2 `mem` mất dữ liệu khi ứng dụng dừng; muốn kiểm tra persistence qua restart hãy dùng database bền vững và giữ nguyên schema.
- Production không tự chạy DDL tạo bảng mỗi lần startup; quản lý schema qua migration versioned, backup/restore, quyền tài khoản DB tối thiểu và kiểm soát truy cập.

### 5.3. Security và JDBC repository beans

Tệp `src/main/java/example/passkeys/PasskeyApplication.java`:

~~~java
package example.passkeys;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasskeyApplication {
    public static void main(String[] args) {
        SpringApplication.run(PasskeyApplication.class, args);
    }
}
~~~

Tệp `src/main/java/example/passkeys/PasskeySecurityConfig.java`:

~~~java
package example.passkeys;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.webauthn.management.JdbcPublicKeyCredentialUserEntityRepository;
import org.springframework.security.web.webauthn.management.JdbcUserCredentialRepository;

@Configuration(proxyBeanMethods = false)
public class PasskeySecurityConfig {

    @Bean
    JdbcPublicKeyCredentialUserEntityRepository webAuthnUsers(
            JdbcOperations jdbc) {
        return new JdbcPublicKeyCredentialUserEntityRepository(jdbc);
    }

    @Bean
    JdbcUserCredentialRepository webAuthnCredentials(JdbcOperations jdbc) {
        return new JdbcUserCredentialRepository(jdbc);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService applicationUsers(PasswordEncoder passwordEncoder) {
        // Demo: password bootstrap chỉ dành cho môi trường local.
        // Production: thay bằng account database / identity provider.
        UserDetails student = User.withUsername("student")
                .password(passwordEncoder.encode("local-demo-change-me"))
                .roles("USER")
                .build();

        return new InMemoryUserDetailsManager(student);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/settings/passkeys/**").authenticated()
                .anyRequest().authenticated());

        http.formLogin(Customizer.withDefaults());

        // Localhost được browser hỗ trợ như secure context đặc biệt.
        // Production: rpId("example.com")
        //             .allowedOrigins("https://app.example.com")
        http.webAuthn(webAuthn -> webAuthn
                .rpId("localhost")
                .allowedOrigins("http://localhost:8080"));

        // Không disable CSRF; WebAuthn registration/authentication có POST.
        return http.build();
    }
}
~~~

**Tại sao phải có cả `UserDetailsService` lẫn hai WebAuthn repositories?**

`UserDetailsService` trong ví dụ cung cấp account `student` để bootstrap qua form login và quyền `ROLE_USER`. `JdbcPublicKeyCredentialUserEntityRepository` lưu user handle WebAuthn; `JdbcUserCredentialRepository` lưu credential public keys. Hai JDBC beans **không** thay thế kho account nghiệp vụ. Việc dùng cùng `username` để ánh xạ là thỏa thuận giữa hai phần, phải duy trì nhất quán.

**Cảnh báo version:** hai lớp JDBC phía trên là API **Since 6.5**. Nếu dùng Spring Security 6.4, tính năng passkeys đã có nhưng không thể mong các lớp JDBC này tồn tại. Khi dùng WebFlux, không tự copy `HttpSecurity`/`SecurityFilterChain` Servlet.

## 6. API liệt kê và thu hồi passkey đã đăng ký

Sau khi đăng nhập, người dùng cần màn hình:

| Tên passkey | Tạo lúc | Dùng gần nhất | Trạng thái | Thao tác |
| --- | --- | --- | --- | --- |
| Điện thoại | 2026-08-01 | 2026-11-01 | Có thể sync | Gỡ |
| Khóa bảo mật dự phòng | 2026-09-15 | 2026-10-20 | Device-bound | Gỡ |
| Trình quản lý passkey | 2026-10-02 | 2026-11-05 | Đã sync | Gỡ |

Bảng là **dữ liệu minh họa**. Tên/khả năng backup không chứng minh thiết bị cụ thể đang tồn tại ở đâu. Không cho người dùng khác liệt kê passkey của tài khoản này; không bao giờ trả raw public key/attestation nếu UI chỉ cần tên và ngày.

### 6.1. Các nguyên tắc quản lý

1. Lấy **username từ `Authentication` đã xác thực**, không lấy `userId` tùy ý trong query/body.
2. Tìm user entity hiện tại qua `findByUsername`, lấy `userEntity.getId()`.
3. Liệt kê `findByUserId(userEntity.getId())`; không truy vấn tất cả passkeys rồi lọc trên client.
4. Khi gỡ, tìm record theo `credentialId` và xác minh `record.getUserEntityUserId().equals(userEntity.getId())` **trước khi** gọi `delete`.
5. Không gỡ passkey cuối cùng nếu hệ thống không có cách đăng nhập/khôi phục khác; demo dưới đây áp dụng chính sách chặn gỡ credential cuối.
6. Việc gỡ là thao tác nhạy cảm: production nên yêu cầu **recent authentication/step-up**, giữ CSRF và audit (không log raw credential ID).
7. Với nhiều request đồng thời, production cần cơ chế atomic ownership/revocation phù hợp DB; kiểm tra-đợi-xóa trên hai câu lệnh riêng có thể gặp race khi có cập nhật cạnh tranh.

### 6.2. Controller Java 17+ có kiểm tra ownership

Tệp `src/main/java/example/passkeys/PasskeyManagementController.java`:

~~~java
package example.passkeys;

import java.time.Instant;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.webauthn.api.Bytes;
import org.springframework.security.web.webauthn.api.CredentialRecord;
import org.springframework.security.web.webauthn.api.PublicKeyCredentialUserEntity;
import org.springframework.security.web.webauthn.management.PublicKeyCredentialUserEntityRepository;
import org.springframework.security.web.webauthn.management.UserCredentialRepository;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/settings/passkeys")
public class PasskeyManagementController {

    private final PublicKeyCredentialUserEntityRepository users;
    private final UserCredentialRepository credentials;

    public PasskeyManagementController(
            PublicKeyCredentialUserEntityRepository users,
            UserCredentialRepository credentials) {
        this.users = users;
        this.credentials = credentials;
    }

    @GetMapping
    public List<PasskeySummary> list(Authentication authentication) {
        PublicKeyCredentialUserEntity owner =
                users.findByUsername(authentication.getName());

        if (owner == null) {
            return List.of();
        }

        return credentials.findByUserId(owner.getId())
                .stream()
                .map(record -> new PasskeySummary(
                        record.getCredentialId().toBase64UrlString(),
                        record.getLabel(),
                        record.getCreated(),
                        record.getLastUsed(),
                        record.isBackupEligible(),
                        record.isBackupState()))
                .toList();
    }

    @DeleteMapping("/{credentialId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(
            @PathVariable String credentialId,
            Authentication authentication) {

        Bytes id;
        try {
            id = Bytes.fromBase64(credentialId);
        } catch (IllegalArgumentException invalidId) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        if (id == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }

        PublicKeyCredentialUserEntity owner =
                users.findByUsername(authentication.getName());
        if (owner == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }

        CredentialRecord record = credentials.findByCredentialId(id);
        if (record == null
                || !owner.getId().equals(record.getUserEntityUserId())) {
            // Giống nhau cho "không tồn tại" và "không thuộc tài khoản".
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }

        // Chính sách demo: luôn giữ ít nhất một passkey.
        // Production cần xét phương án recovery/password riêng.
        if (credentials.findByUserId(owner.getId()).size() <= 1) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT,
                    "Cannot remove the last passkey in this demo");
        }

        credentials.delete(id);
    }

    public record PasskeySummary(
            String credentialId,
            String label,
            Instant created,
            Instant lastUsed,
            boolean backupEligible,
            boolean backupState) {
    }
}
~~~

**API được dùng và đã có ở Spring Security 6.5:**

- `PublicKeyCredentialUserEntityRepository.findByUsername(String)` và `getId()`;
- `UserCredentialRepository.findByUserId(Bytes)`, `findByCredentialId(Bytes)`, `delete(Bytes)`;
- `CredentialRecord.getUserEntityUserId()`, `getLabel()`, `getCreated()`, `getLastUsed()`, `isBackupEligible()`, `isBackupState()`;
- `Bytes.fromBase64(String)` và `toBase64UrlString()`.

`PasskeySummary` là Java `record` (hỗ trợ từ Java 16, hoạt động trên Java 17), chỉ hiển thị metadata. Token người dùng, public key, raw assertion và attestation **không** được trả trong list.

**Giới hạn của demo:** dù controller có ownership check, đây chưa phải tính năng quản trị production hoàn chỉnh: chưa thêm xác thực lại trước thao tác gỡ, chưa có audit, rate limit, locking/câu SQL xóa theo `credential_id + user_handle` atomic và chưa bảo đảm người dùng còn một kênh recovery độc lập. Ngoài ra, đường dẫn chứa raw credential ID có thể lộ trong access logs; production phải che/sử dụng ID thay thế nếu cần.

### 6.3. Điểm riêng của version 6.5.10 trở lên

Spring Security 6.5.10 có `CredentialRecordOwnerAuthorizationManager` trong package `org.springframework.security.web.webauthn.management`, triển khai `AuthorizationManager<Bytes>` để hỗ trợ kiểm tra quyền sở hữu credential. Nó là một lựa chọn defense-in-depth khi thiết kế endpoint quản lý.

**Không thay quyền sở hữu bằng việc credential ID “khó đoán”.** Credential ID có tính ngẫu nhiên cao nhưng có thể rò rỉ qua log, analytics, request history hoặc tài khoản bị lộ. Việc gỡ passkey là thao tác cập nhật state nhạy cảm, phải kiểm tra **user đang đăng nhập sở hữu credential đó**. Trong ví dụ trên, check được thực hiện thủ công trước khi xóa; với các phiên bản hỗ trợ authorization manager, có thể tích hợp thành rule riêng theo kiến trúc.

### 6.4. Phản hồi API và CSRF

Ví dụ sau khi alice có hai passkey:

~~~http
GET /settings/passkeys HTTP/1.1
Host: localhost:8080
Cookie: JSESSIONID=<lab-session>
~~~

Body JSON **minh họa**; ID thực là Base64url của credential bytes, không phải các chuỗi tên thiết bị:

~~~json
[
  {
    "credentialId": "AQIDBAUGBwgJCgsMDQ4PEA",
    "label": "Điện thoại",
    "created": "2026-10-01T00:00:00Z",
    "lastUsed": "2026-11-05T08:30:00Z",
    "backupEligible": true,
    "backupState": true
  },
  {
    "credentialId": "EA8ODQwLCgkIBwYFBAMCAQ",
    "label": "Khóa bảo mật dự phòng",
    "created": "2026-10-03T00:00:00Z",
    "lastUsed": "2026-10-20T08:00:00Z",
    "backupEligible": false,
    "backupState": false
  }
]
~~~

Một request xóa cần phiên đã xác thực và CSRF token khi CSRF bật:

~~~http
DELETE /settings/passkeys/AQIDBAUGBwgJCgsMDQ4PEA HTTP/1.1
Host: localhost:8080
Cookie: JSESSIONID=<lab-session>
X-CSRF-TOKEN: <csrf-token-from-app>
~~~

Nếu credential này thuộc tài khoản hiện tại và user còn ít nhất một credential khác, controller trả **204 No Content**. Nếu credential chưa tồn tại/không thuộc người đang đăng nhập, trả 404; nếu là credential cuối theo policy demo, trả 409 Conflict. Quy tắc check ownership phải luôn làm ở server, không tin UI chỉ hiển thị nút gỡ của mình.

### 6.5. Gắn thêm metadata mà không phá credential

Ứng dụng có thể cho phép người dùng **đổi nhãn** hoặc ghi chú passkey:

- Nhãn cần validate độ dài/ký tự, chống XSS khi render HTML, không cho markup/script không được sanitize.
- Đổi nhãn **không đổi** `credentialId`, `userEntityUserId`, `publicKey` hay `signatureCount`.
- Với Spring Security 6.5, `ImmutableCredentialRecord.fromCredentialRecord(record)` cho phép tạo builder từ một record hiện có; builder có `label(String)` và `build()`. Sau đó lưu lại qua `UserCredentialRepository.save(...)` theo semantics implementation đang dùng.
- Phải xác minh ownership và cơ chế cập nhật atomic trước khi ghi. Không tự động làm mất thay đổi `lastUsed` hoặc `signatureCount` đồng thời được cập nhật bởi login khác.
- Không dùng một nhãn do client đưa vào làm selector duy nhất cho câu lệnh xóa.

Mô tả đoạn Java **bên trong một service đã có `record` và repository, không phải chương trình độc lập**:

~~~java
CredentialRecord renamed =
        ImmutableCredentialRecord.fromCredentialRecord(record)
                .label("Khóa bảo mật dự phòng")
                .build();

credentials.save(renamed);
~~~

Các import cần thêm từ `org.springframework.security.web.webauthn.api.ImmutableCredentialRecord`. Khi sử dụng snippet trong thực tế, **trước đó phải** tra record và kiểm tra chủ sở hữu với user hiện tại, xác nhận yêu cầu đổi nhãn hợp lệ và xử lý concurrency. Không có phép kiểm tra này, một endpoint đổi nhãn bằng credential ID đoán được cũng có thể thành lỗ hổng IDOR.

## 7. Chạy demo và kiểm thử bằng browser

### 7.1. Chuẩn bị

1. Dùng project Gradle Spring Boot 3.5/JDK 17 và thêm các file ở mục 5/6.
2. Chạy với `./gradlew bootRun` (Windows: `gradlew.bat bootRun`).
3. Mở browser hỗ trợ WebAuthn/passkey tại `http://localhost:8080`. `localhost` là ngoại lệ secure context được trình duyệt hỗ trợ; trên hostname/IP tùy ý cần HTTPS thực, RP ID và origin khớp.
4. Truy cập `/login` và đăng nhập tài khoản demo **student** với mật khẩu demo chỉ dùng local (`local-demo-change-me`).
5. Khi đã đăng nhập, dùng trang đăng ký WebAuthn mặc định của framework tại `/webauthn/register` (hoặc UI quản lý của app) để đăng ký một passkey; browser phải có authenticator/platform prompt.
6. Đăng ký lần hai với **authenticator khác**. Với cùng một tài khoản, bạn sẽ có ít nhất hai credential records nếu việc tạo credential thứ hai thành công.
7. Gọi `GET /settings/passkeys` trong browser session đã đăng nhập, kiểm tra có hai record riêng nhưng cùng user owner.
8. Gỡ một credential qua UI gửi DELETE + CSRF; danh sách còn một credential. Đăng xuất và thử đăng nhập bằng credential đã bị gỡ: phải thất bại; credential còn lại vẫn đăng nhập được.

**Không gõ thủ công một JSON giả rồi gửi `POST /webauthn/register` để “tạo passkey”**. Registration cần `navigator.credentials.create` từ WebAuthn API và response hợp lệ có attestation/challenge; signature không thể giả bằng một file JSON thuần.

### 7.2. Những điểm phải quan sát

- `GET /settings/passkeys` không tạo authentication; endpoint trả danh sách dựa trên user đã đăng nhập.
- `POST /webauthn/register/options` tạo registration challenge, được lưu để đối chiếu theo repository/chế độ session đã cấu hình. Mặc định có phần state trong HTTP session; với cluster cần session/challenge consistency.
- `POST /webauthn/register` chỉ được chấp nhận khi client response hợp lệ, origin/rpId chính xác, user đang đăng nhập có quyền đăng ký.
- `POST /webauthn/authenticate/options` tạo authentication challenge; `POST /login/webauthn` xác minh assertion qua public key đã lưu.
- Gỡ passkey trên server **không buộc authenticator hoặc hệ sinh thái sync xóa private key**. Browser có thể vẫn thấy passkey cũ trong danh sách, nhưng server không còn credential record để xác minh nó.
- Nếu server restart trong lab dùng H2 `mem`, tất cả credential records demo bị mất; không có nghĩa cơ chế passkey không hỗ trợ persistence, mà vì ta chọn database in-memory.

## 8. Kiểm thử quyền sở hữu và nhiều credential

### 8.1. JUnit test controller không cần browser

Ví dụ JUnit 5/Mockito trong project có `spring-boot-starter-test`. Test giả lập repository để cô lập phép kiểm tra ownership. Nó **không chứng minh WebAuthn signature/challenge verification** — phần đó cần integration/e2e test.

Tệp `src/test/java/example/passkeys/PasskeyManagementControllerTest.java`:

~~~java
package example.passkeys;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.web.webauthn.api.Bytes;
import org.springframework.security.web.webauthn.api.CredentialRecord;
import org.springframework.security.web.webauthn.api.PublicKeyCredentialUserEntity;
import org.springframework.security.web.webauthn.management.PublicKeyCredentialUserEntityRepository;
import org.springframework.security.web.webauthn.management.UserCredentialRepository;
import org.springframework.web.server.ResponseStatusException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class PasskeyManagementControllerTest {

    @Test
    void oneUserCanListTwoCredentials() {
        PublicKeyCredentialUserEntityRepository users =
                mock(PublicKeyCredentialUserEntityRepository.class);
        UserCredentialRepository credentials =
                mock(UserCredentialRepository.class);

        Bytes userHandle = Bytes.random();
        Bytes credentialA = Bytes.random();
        Bytes credentialB = Bytes.random();

        PublicKeyCredentialUserEntity owner =
                mock(PublicKeyCredentialUserEntity.class);
        when(users.findByUsername("student")).thenReturn(owner);
        when(owner.getId()).thenReturn(userHandle);

        CredentialRecord a = mock(CredentialRecord.class);
        when(a.getCredentialId()).thenReturn(credentialA);
        when(a.getLabel()).thenReturn("Phone");
        when(a.getCreated()).thenReturn(Instant.parse("2026-10-01T00:00:00Z"));

        CredentialRecord b = mock(CredentialRecord.class);
        when(b.getCredentialId()).thenReturn(credentialB);
        when(b.getLabel()).thenReturn("Backup key");
        when(b.getCreated()).thenReturn(Instant.parse("2026-10-02T00:00:00Z"));

        when(credentials.findByUserId(userHandle))
                .thenReturn(List.of(a, b));

        PasskeyManagementController controller =
                new PasskeyManagementController(users, credentials);

        var auth = new TestingAuthenticationToken("student", "unused");
        var result = controller.list(auth);

        assertEquals(2, result.size());
        assertEquals("Phone", result.get(0).label());
        assertEquals("Backup key", result.get(1).label());
    }

    @Test
    void cannotDeleteCredentialOwnedByAnotherUser() {
        PublicKeyCredentialUserEntityRepository users =
                mock(PublicKeyCredentialUserEntityRepository.class);
        UserCredentialRepository credentials =
                mock(UserCredentialRepository.class);

        Bytes currentUserId = Bytes.random();
        Bytes otherUserId = Bytes.random();
        Bytes credentialId = Bytes.random();

        PublicKeyCredentialUserEntity currentUser =
                mock(PublicKeyCredentialUserEntity.class);
        when(users.findByUsername("student")).thenReturn(currentUser);
        when(currentUser.getId()).thenReturn(currentUserId);

        CredentialRecord someoneElsesPasskey =
                mock(CredentialRecord.class);
        when(someoneElsesPasskey.getUserEntityUserId())
                .thenReturn(otherUserId);
        when(credentials.findByCredentialId(credentialId))
                .thenReturn(someoneElsesPasskey);

        PasskeyManagementController controller =
                new PasskeyManagementController(users, credentials);
        var auth = new TestingAuthenticationToken("student", "unused");

        assertThrows(ResponseStatusException.class, () ->
                controller.delete(
                        credentialId.toBase64UrlString(), auth));

        verify(credentials, never()).delete(any(Bytes.class));
    }
}
~~~

Chạy trong Gradle project:

~~~bash
./gradlew test --tests example.passkeys.PasskeyManagementControllerTest
~~~

Kết quả mong đợi: hai test pass nếu mã cấu hình/controller đúng; Gradle có thể in `BUILD SUCCESSFUL`, nhưng log cụ thể tùy phiên bản Gradle và thiết lập CI. Test xác minh: (1) cùng một user handle có thể truy vấn hai credential; (2) người dùng không thể gỡ credential mang owner khác. Nó **chưa** thử HTTP/CSRF, recent-login, SQL transaction, thực tế của WebAuthn crypto hoặc browser-origin.

### 8.2. Ma trận test chức năng/bảo mật

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| P01 | User A đăng ký credential A1 | User entity A tồn tại và A1 trỏ về handle của A |
| P02 | Cùng user A đăng ký A2 | A1 vẫn tồn tại; A2 có credential ID riêng; cả hai trỏ về handle A |
| P03 | User B đăng ký B1 | Handle B khác handle A; A không thấy B1 |
| P04 | Đăng nhập bằng A1 | Xác thực tài khoản A, không phải tài khoản B |
| P05 | Đăng nhập bằng A2 | Vẫn xác thực tài khoản A |
| P06 | API list của A | Chỉ trả các credential của A |
| P07 | A cố gỡ credential B1 bằng ID bị lộ | Bị từ chối; dữ liệu B không thay đổi |
| P08 | A gỡ A1 khi vẫn có A2 | A1 không dùng đăng nhập được; A2 vẫn dùng được |
| P09 | A gỡ credential cuối | Áp dụng policy 409/recovery; tránh tự khóa tài khoản |
| P10 | Thêm passkey rồi sửa label | Chỉ đổi label; credentialId/publicKey/userHandle giữ nguyên |
| P11 | Hai passkey có label trùng | Không nhập nhằng vì mọi thao tác dùng credential ID |
| P12 | Đổi username/displayName | Handle ổn định; A1/A2 tiếp tục hoạt động sau migration |
| P13 | Gửi credential ID giả/không có trong DB | 404/chặn, không truy vấn/gỡ dữ liệu user khác |
| P14 | Registration thiếu CSRF hoặc không authenticated | Bị chặn |
| P15 | Gỡ credential thiếu CSRF trong session browser | Bị chặn |
| P16 | Login assertion sai challenge/origin/rpId | Xác thực thất bại |
| P17 | Login assertion chữ ký sai | Xác thực thất bại, không tạo SecurityContext hợp lệ |
| P18 | Registration trùng credential ID | Không tạo hai bản ghi định danh mơ hồ, kiểm unique constraint |
| P19 | Chạy hai node, shared DB | Credential đăng ký ở node A dùng được ở node B với session/challenge setup đúng |
| P20 | Restart DB bền vững | Credential và user handle vẫn tồn tại, không cần đăng ký lại |
| P21 | Backup-state thay đổi | UI/metadata cập nhật theo validator, không gán nhầm thành thiết bị mới |
| P22 | Hai DELETE cuối cùng đồng thời | Production không tự xóa hết mọi phương thức khi policy bảo vệ last credential |
| P23 | Mất thiết bị có synced passkey | Xác định chính sách revoke toàn credential và đăng ký lại, không chỉ gỡ một bản sao |
| P24 | User account bị khóa/xóa | Không còn đăng nhập được; xóa credential theo workflow có audit/retention |
| P25 | Không có passkey sau bootstrap | Login password/recovery (nếu được cho phép) vẫn theo policy, không lỗi NullPointer |

**Không suy ra WebAuthn security từ test mock repository.** Test phải bao gồm bài tích hợp browser + authenticator hoặc fixture WebAuthn hợp lệ, path bị từ chối và recovery policy.

## 9. Xóa credential, xóa user và khôi phục tài khoản

### 9.1. Xóa một credential

Xóa qua `UserCredentialRepository.delete(credentialId)` sau khi kiểm tra ownership khiến server **không còn public key** tương ứng để xác minh credential đó. Các credential khác của user không bị xóa. Tuy nhiên thao tác này **không** gửi lệnh buộc điện thoại/trình quản lý mật khẩu xóa private key hoặc bản sao đã sync, nên UI cần giải thích rõ “gỡ khỏi tài khoản này”.

### 9.2. Xóa toàn bộ user entity

Khi tài khoản bị xóa theo quy trình ứng dụng:

1. Xác định account ID và user handle qua mapping đáng tin.
2. Xác định tất cả `CredentialRecord` với `findByUserId(handle)`.
3. Thu hồi/xóa hoặc ẩn an toàn các credentials theo policy và chuẩn bị audit không chứa secret.
4. Xử lý user entity qua `PublicKeyCredentialUserEntityRepository.delete(handle)` theo semantics repository/DB và thứ tự khóa ngoại.
5. Xóa/ẩn application user và các phiên có thể còn hoạt động, dùng transaction/retention có kiểm soát.

Đừng xóa user entity trước khi xử lý các credential records nếu điều đó tạo ra orphan hoặc vi phạm foreign key. Đừng gán handle cũ cho tài khoản mới; các credential từng được đăng ký bằng handle ấy không bao giờ được liên kết sang người khác.

### 9.3. Khôi phục khi mất tất cả passkey

Đừng thiết kế “passwordless” đồng nghĩa với “không có cách recovery nào”. Những cách phổ biến có thể gồm:

- Passkey dự phòng trên security key ở nơi an toàn.
- Kênh đăng nhập đã xác minh (nếu chấp nhận password/SSO), rồi thêm credential mới.
- Quy trình recovery bảo mật cao, kiểm tra nhiều bằng chứng và chống social engineering.
- Chính sách thu hồi credential bị mất, đóng session liên quan và thông báo thay đổi bảo mật.

**Không cho phép đăng ký passkey mới chỉ bằng cách nhập email**; nếu recovery chấp nhận một lời khai chưa xác minh, attacker có thể gắn passkey của họ vào account nạn nhân. Đặc biệt, đổi email/recovery method là thao tác có nguy cơ chiếm đoạt tài khoản, nên có xác thực bổ sung và thông báo bảo mật.

### 9.4. Credential sync và cách trả lời câu hỏi “mất một máy”

Nếu một passkey đã sync sang nhiều thiết bị, việc thu hồi **credential ID trên server** chặn tất cả bản sao cùng credential khi gọi RP đó (bất kể private key còn nằm trên thiết bị nào). Nếu chỉ bỏ passkey khỏi một thiết bị nhưng credential còn trong hệ sync khác, RP có thể vẫn chấp nhận assertion. Vì vậy phải phân biệt “gỡ trên điện thoại”, “xóa trong passkey manager”, “gỡ quyền đăng nhập ở server”.

## 10. Lưu ý bảo mật và vận hành nâng cao

### 10.1. RP ID và origin

WebAuthn có ràng buộc **Relying Party ID** (`rpId`) và origin. Với domain thực, ví dụ:

~~~java
http.webAuthn(webAuthn -> webAuthn
        .rpId("example.com")
        .allowedOrigins("https://app.example.com"));
~~~

Đây là **snippet đặt trong cấu hình `SecurityFilterChain`**, không phải file Java độc lập. Nếu chạy ở domain khác với cấu hình, browser có thể chặn tạo credential hoặc server từ chối assertion. Không đưa RP ID/origin do caller tự cung cấp vào cấu hình tin cậy. Giao thức WebAuthn yêu cầu secure context; localhost thường là ngoại lệ cho lab, production dùng HTTPS.

### 10.2. Thông tin cần bảo vệ trong DB

Private key không nằm ở server, nhưng database vẫn là dữ liệu bảo mật quan trọng:

- Public key, credential ID, user handle và metadata có thể cho phép theo dõi/liên kết tài khoản.
- Dữ liệu attestation và transport có thể cung cấp dấu hiệu về thiết bị; hạn chế thời gian giữ và quyền đọc.
- Bản ghi `lastUsed`/IP/user agent nếu ứng dụng bổ sung là dữ liệu hành vi; cân nhắc quyền riêng tư.
- Cần bảo vệ integrity của mapping: attacker đổi `userEntityUserId` hoặc chèn public key có thể thực hiện chiếm quyền xác thực.
- Audit nên ghi **hash/mã tham chiếu nội bộ** thay vì raw credential ID/response. Không log assertion, clientDataJSON đầy đủ nếu không cần.

### 10.3. Transaction và cạnh tranh

Trong môi trường có nhiều node, các thao tác có rủi ro race:

- Hai registration với credential ID trùng: DB UNIQUE constraint phải chặn trạng thái bất nhất.
- Hai DELETE đồng thời: kiểm tra “còn ít nhất một passkey” rồi xóa hai credential khác nhau có thể làm user mất tất cả passkey. Nếu policy ngăn việc đó, phải dùng transaction/lock hoặc một câu lệnh có điều kiện đảm bảo bất biến.
- Đổi label và login cập nhật `signatureCount/lastUsed` đồng thời: ghi toàn record cũ có thể che thay đổi mới. Cần optimistic locking/version hoặc update có điều kiện/field-specific.
- Đổi username và registration đồng thời: phải giữ handle, mapping nhất quán trong một transaction.
- Cache credential stale: vừa revoke xong, một node khác không được tiếp tục chấp nhận public key cache lâu hơn chính sách.

Một demo chạy single-thread hoặc repository mock không kiểm chứng được những tình huống này.

### 10.4. Sign count và flag backup

Dữ liệu `signCount` có thể giúp phát hiện thiết bị bị sao chép trong một số loại authenticator, nhưng khả năng đồng bộ passkey có thể khiến counter bằng 0 hoặc khác nhau giữa bản sao. Không dùng một so sánh đơn giản “counter không tăng = tài khoản bị hack” cho mọi authenticator. Các cờ BE/BS do authenticator ký trong dữ liệu WebAuthn có thể giúp phân loại cách backup, **không** chứng minh số lượng thiết bị hay mức độ tin cậy tuyệt đối.

### 10.5. Quản lý nhãn và thiết bị

- User có thể đặt nhãn tự do; giới hạn độ dài, escape HTML và tránh XSS.
- Không hiển thị chính xác serial thiết bị/bí mật metadata nếu không cần.
- Nếu muốn gợi ý “platform/roaming”, dùng tín hiệu WebAuthn transport/attachment phù hợp và ghi rõ có thể không chính xác.
- Khi có nhiều passkey, khuyến nghị thêm một phương thức dự phòng độc lập thay vì chỉ dùng một thiết bị.
- Thay đổi nhãn không cần tạo credential mới; xóa và đăng ký mới sẽ có **credential ID/public key khác**.

## 11. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Đăng ký passkey thứ hai làm passkey thứ nhất mất | App đang lưu 1 credential trên mỗi user hoặc update nhầm key | Kiểm mapping 1:N và khóa chính `credentialId` |
| Hai người cùng thấy một passkey | Dùng email/name làm user handle, mapping sai hoặc bỏ ownership check | Kiểm ID opaque, khóa ngoại và quyền tại server |
| Đăng ký thành công nhưng restart mất passkey | Dùng Map repository hoặc H2 `mem` | Dùng JDBC + DB bền vững, migration đúng |
| Node A đăng ký nhưng node B không login được | Token/challenge session không chia sẻ hoặc credential repo in-memory | Kiểm shared DB và session/challenge store |
| `JdbcUserCredentialRepository` lỗi SQL/table missing | Chưa tạo `user-credentials-schema.sql` hoặc sai dialect | Chạy đúng schema/migrations, kiểm DB user privileges |
| IDE không tìm được `JdbcPublicKeyCredentialUserEntityRepository` | Đang dùng Spring Security 6.4 | Nâng 6.5+ hoặc custom implementation |
| WebAuthn options 403 | Thiếu CSRF token hoặc chưa authenticated khi registration | Kiểm Spring CSRF và user session |
| Browser không hiện passkey prompt | Origin/RP ID sai, không có secure context, thiết bị không hỗ trợ | Kiểm HTTPS/localhost, rpId, browser support |
| Credential hợp lệ nhưng xác thực bị từ chối | Sai challenge/origin/rpId hoặc record/publicKey không khớp | Kiểm verify request và record storage, không bypass validation |
| DELETE của người khác thành công | IDOR do tin credential ID và bỏ owner check | Kiểm `userEntityUserId == current userHandle` ở server |
| Sau xóa server UI vẫn gợi ý passkey cũ | Credential còn trong trình quản lý passkey ở client | Giải thích revoke ở RP khác với delete local |
| User mất mọi passkey sau hai DELETE song song | Check last-passkey không atomic | DB locking/transaction/conditional delete |
| User đổi username rồi passkey không dùng được | Tạo user handle mới hoặc mapping cũ không cập nhật | Giữ handle và migration mapping |
| Số thiết bị trong UI khác số record | Một passkey synced trên nhiều thiết bị | Không suy số thiết bị từ credential record |
| “Signature counter” không tăng | Passkey synced hoặc authenticator không hỗ trợ bộ đếm | Xử lý dựa theo RP policy và WebAuthn semantics |

## 12. Câu hỏi tự kiểm tra

1. Vì sao application user, WebAuthn user entity và credential không phải ba tên cho cùng một đối tượng?
2. Thuộc tính nào dùng để liên kết `CredentialRecord` với `PublicKeyCredentialUserEntity`? Thuộc tính nào dùng tìm đúng credential?
3. User handle có nên là email không? Vì sao?
4. Một account có 3 credentials thì repository nào phải trả về danh sách có 3 phần tử?
5. Hai thiết bị dùng cùng passkey đã sync có chắc tạo hai credential IDs trên server không?
6. Vì sao chỉ kiểm tra “credential ID khó đoán” không đủ để cho phép DELETE?
7. Sau khi xóa credential trên RP, private key có tự biến mất khỏi thiết bị/sync manager không?
8. Khi đổi username, những gì phải được giữ nguyên để passkey cũ vẫn dùng được?
9. In-memory repository khác JDBC về điều gì khi triển khai 3 replicas?
10. Vì sao test “gỡ passkey cuối cùng bị 409” ở một request không chứng minh an toàn với hai DELETE đồng thời?
11. `getLabel()` có vai trò gì? Có được dùng label làm khóa chính không?
12. Khi người dùng có 2 credential độc lập, xác thực bằng credential thứ hai cần quyền riêng hay vẫn map về cùng application user?

**Đáp án định hướng:** (1) account nghiệp vụ / user handle WebAuthn / bản ghi public-key; (2) `userEntityUserId` và `credentialId`; (3) không, vì lộ thông tin và thay đổi; (4) `UserCredentialRepository.findByUserId(handle)`; (5) không; (6) cần owner ACL + CSRF/re-auth; (7) không; (8) opaque user handle và mapping/credential records; (9) JDBC shared persistence, in-memory per instance; (10) race TOCTOU; (11) nhãn UI, không phải selector; (12) cùng user handle nên cùng tài khoản, nếu Relying Party xác minh assertion thành công.

## 13. Checklist triển khai thực tế

- [ ] Có mô hình **application account → 1 user entity → N credentials**, mapping bền vững.
- [ ] User handle opaque, duy nhất, không chứa PII, không tự thay mỗi lần registration.
- [ ] Credential ID unique, public key/COSE và metadata lưu đúng kiểu; server không có private key.
- [ ] Đăng ký credential mới không ghi đè credential cũ.
- [ ] Đọc/đổi nhãn/gỡ credential đều dựa trên principal đang đăng nhập và kiểm owner phía server.
- [ ] Có policy không tự khóa tài khoản khi gỡ passkey cuối; recovery/step-up/audit đầy đủ.
- [ ] Chọn đúng Spring Security version; với 6.5 JDBC repositories, chạy đúng schema/resources và migrations.
- [ ] Có database shared khi chạy cluster và kiểm challenge/session consistency.
- [ ] Có test 2+ passkeys cùng tài khoản, cross-user IDOR, duplicate, expired challenge, signing, revocation.
- [ ] Có bảo vệ HTTPS, RP ID, allowed origin, CSRF và quyền truy cập credential management.
- [ ] Có test concurrency cho thao tác xóa/đổi nhãn, không chỉ test tuần tự.
- [ ] Hiểu synced passkey không tương đương nhiều DB credentials hoặc nhiều thiết bị chắc chắn.
- [ ] Có quy trình user rename, account deletion, recovery và backup/restore dữ liệu WebAuthn.

## 14. Tài liệu tham khảo

- [Spring Security 6.5 — Passkeys (Servlet, WebAuthn)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html)
- [Spring Security 6.5 — WebAuthn What's New: JDBC persistence](https://docs.spring.io/spring-security/reference/6.5/whats-new.html)
- [Spring Security 6.5 — PublicKeyCredentialUserEntityRepository API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/web/webauthn/management/PublicKeyCredentialUserEntityRepository.html)
- [Spring Security 6.5 — UserCredentialRepository API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/web/webauthn/management/UserCredentialRepository.html)
- [Spring Security 6.5 — CredentialRecord API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/webauthn/api/CredentialRecord.html)
- [Spring Security 6.5 — Bytes API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/webauthn/api/Bytes.html)
- [Spring Security 6.5 — JdbcUserCredentialRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/webauthn/management/JdbcUserCredentialRepository.html)
- [Spring Security 6.5 — CredentialRecordOwnerAuthorizationManager](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/web/webauthn/management/CredentialRecordOwnerAuthorizationManager.html)
- [Spring Security 6.4 GA — Passkey support introduced](https://spring.io/blog/2024/11/19/spring-security-6-4-goes-ga/)
- [MDN — Passkeys: create multiple and backup](https://developer.mozilla.org/en-US/docs/Web/Security/Authentication/Passkeys)
- [W3C Web Authentication specification](https://www.w3.org/TR/webauthn-3/)
