# DelegatingReactiveAuthenticationManager và việc phối hợp nhiều manager trong Spring Security WebFlux

## 1. Mục tiêu của bài học

Một ứng dụng **Spring Security WebFlux** có thể hỗ trợ nhiều cơ chế xác thực cùng lúc: username/password, API key của service account, JWT bearer token, opaque token hoặc một challenge tùy chỉnh. Mỗi cơ chế có loại `Authentication`, logic kiểm tra credential, nơi lưu danh tính và quy tắc lỗi riêng. Thay vì viết một khối `if/else` khổng lồ hoặc vô tình để mọi manager xử lý mọi token, Spring Security cung cấp **`DelegatingReactiveAuthenticationManager`** để phối hợp nhiều `ReactiveAuthenticationManager` theo thứ tự.

Sau khi học xong, bạn có thể:

1. Nắm đúng hợp đồng `ReactiveAuthenticationManager.authenticate(Authentication)` trả `Mono<Authentication>`.
2. Phân biệt rõ **`Mono.just(authenticated)`**, **`Mono.empty()`** và **`Mono.error(AuthenticationException)`**.
3. Dùng `DelegatingReactiveAuthenticationManager` để chọn manager phù hợp với một loại token và fallback khi manager trước **không xác định được** kết quả.
4. Hiểu **`setContinueOnError(false)` mặc định** và vì sao bật `true` có thể tạo lỗ hổng fallback nếu cấu hình sai.
5. Tạo manager riêng cho API key, kết hợp với manager cho username/password mà không nhầm nghĩa vụ kiểm tra credential.
6. Kết nối manager tổng hợp với `AuthenticationWebFilter` và `ServerAuthenticationConverter` trong hệ thống WebFlux Servlet-free.
7. Khi nào nên chọn `ReactiveAuthenticationManagerResolver` hoặc nhiều `SecurityWebFilterChain` thay vì một delegating manager.
8. Viết kiểm thử Reactor `StepVerifier` xác nhận thứ tự, fallback, lỗi, cancellation và kết quả xác thực.

Ví dụ dùng **Java 17+, Spring Security 6.5.x, Reactor 3.x và Maven**. Phần thực hành chính là **chương trình Java chạy được**, không cần web server; sau đó có hướng dẫn tích hợp WebFlux. Đây không phải mã Servlet `AuthenticationManager` / `UsernamePasswordAuthenticationFilter`.

## 2. Bức tranh tổng thể

Một request WebFlux được chuyển thành token chưa xác thực, rồi đưa cho một reactive manager:

~~~text
HTTP request
      |
      v
Spring WebFlux / SecurityWebFilterChain
      |
      v
AuthenticationWebFilter
      |
      v
ServerAuthenticationConverter.convert(exchange)
      |
      +-- Mono.empty() => không có request xác thực cho filter này
      |
      +-- Mono.error(...) => lỗi parse/conversion
      |
      +-- Mono<Authentication> chưa xác thực
                    |
                    v
        DelegatingReactiveAuthenticationManager
                    |
        +-----------+-----------+
        |                       |
        v                       v
 API key manager         Password manager
 (manager thứ 1)          (manager thứ 2)
        |                       |
        +-- Mono.empty() ------>+-- xử lý token password
        |                       |
        +-- Mono.just(...)      +-- Mono.just(...)
        |      |                        |
        |      +---- thành công --------+
        |
        +-- Mono.error(...) -> lỗi mặc định, không fallback
                    |
                    v
        AuthenticationWebFilter
         +-- success handler, security context
         +-- failure handler cho AuthenticationException
                    |
                    v
           Authorization / controller
~~~

**Ba tầng khác nhau:**
- **Converter** hỏi: request HTTP này có mang credential cho cơ chế tôi hỗ trợ không? Nếu không, có thể trả `Mono.empty()` **mà chưa gọi manager**.
- **Manager** hỏi: đối tượng `Authentication` này thuộc giao thức của tôi không? Nếu không, trả `Mono.empty()` để manager sau được xem xét. Nếu có nhưng credential sai, trả `Mono.error(...)`.
- **Delegator** chỉ điều phối nhiều manager; nó **không** tự xác minh password, decode JWT hay xác định role. Kết quả quyền phải đến từ manager đã xác minh danh tính.

## 3. Hợp đồng ReactiveAuthenticationManager

Giao diện cốt lõi của Spring Security:

~~~java
@FunctionalInterface
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
~~~

Ý nghĩa kết quả:

| Kết quả của một manager | Cách hiểu | Delegating manager mặc định |
| --- | --- | --- |
| `Mono.just(authenticatedResult)` | Manager đã xác thực thành công và trả danh tính đáng tin | Dừng; trả kết quả này |
| `Mono.empty()` | Manager không thể xác định kết quả, ví dụ token không thuộc loại hỗ trợ | Tiếp tục thử manager tiếp theo |
| `Mono.error(new BadCredentialsException(...))` | Manager nhận trách nhiệm cho token nhưng credential sai | Dừng và truyền lỗi theo mặc định |
| `Mono.error(new AuthenticationServiceException(...))` | Lỗi hệ thống xác thực/nguồn dữ liệu | Truyền lỗi theo mặc định; không giả làm kết quả trống |
| `Mono.just(tokenChuaXacThuc)` | Sai hợp đồng nếu dùng như một thành công | Phải tránh; chỉ phát authenticated token sau kiểm chứng |

**Không nhầm `null` với `Mono.empty()`.** Phương thức reactive phải trả về một `Mono` hợp lệ; không viết `return null;`. Nếu không hỗ trợ loại `Authentication`, dùng `Mono.empty()`.

**Không nhầm `Mono.empty()` với “password sai”.** Nếu nhận loại username/password của mình và xác định password sai, trả `Mono.error(new BadCredentialsException(...))`. Nếu bạn đổi lỗi sai thành empty để cho manager khác xử lý thì có thể tạo đường vòng vô tình chấp nhận credential vốn đã bị từ chối.

### Tính lazy của Mono

Phần lớn pipeline Reactor là **lazy**: việc gọi `authenticate(...)` tạo publisher, còn logic trong `Mono.defer(...)` hoặc `Mono.fromCallable(...)` chạy khi có **subscription**. `AuthenticationWebFilter` sẽ subscribe như một phần luồng request. Trong test, `StepVerifier` là subscriber; trong chương trình CLI đơn giản, `block()` được dùng **chỉ tại điểm khởi chạy CLI**.

Không gọi `block()`, `blockOptional()`, `Thread.sleep()` hoặc chạy JDBC blocking trực tiếp trên event-loop Netty của WebFlux. Nếu tích hợp nguồn dữ liệu blocking, cần một cách offload có giới hạn và kiểm soát tải; lý tưởng hơn là dùng reactive driver/repository.

## 4. DelegatingReactiveAuthenticationManager hoạt động như thế nào?

API của Spring Security 6.5 có các constructor:

~~~java
new DelegatingReactiveAuthenticationManager(
    apiKeyManager,
    passwordManager
);

// Hoặc một List theo đúng thứ tự:
new DelegatingReactiveAuthenticationManager(
    List.of(apiKeyManager, passwordManager)
);
~~~

Nó nhận **các `ReactiveAuthenticationManager` theo thứ tự được đưa vào**. Tài liệu chính thức mô tả:

- Khi `continueOnError=false` (mặc định), thử các manager cho tới **kết quả không rỗng đầu tiên**; lỗi không được tự động coi là một kết quả “không hỗ trợ”.
- Khi `continueOnError=true`, thử tiếp tới **kết quả đầu tiên vừa không rỗng, vừa không lỗi**. Điều này thay đổi chính sách fallback khi một manager trả `Mono.error`.
- `setContinueOnError(boolean)` có từ Spring Security 6.3; hãy kiểm tra phiên bản khi áp dụng cho code cũ.

### Ví dụ với token theo loại

~~~text
Delegates: [ApiKeyManager, PasswordManager]

Case A: ApiKeyAuthenticationToken("valid")
  ApiKeyManager -> Mono.just(authenticated)
  PasswordManager không được gọi

Case B: UsernamePasswordAuthenticationToken("alice", password)
  ApiKeyManager -> Mono.empty()
  PasswordManager -> Mono.just(authenticated)

Case C: ApiKeyAuthenticationToken("wrong-key")
  ApiKeyManager -> Mono.error(BadCredentialsException)
  PasswordManager KHÔNG được thử mặc định

Case D: Một loại Authentication mà cả hai đều không hiểu
  ApiKeyManager -> Mono.empty()
  PasswordManager -> Mono.empty()
  Tập manager không xác định được kết quả
~~~

Thứ tự rất có ý nghĩa nếu **nhiều manager hỗ trợ cùng một loại token**. Khi manager trước thành công, kết quả của manager sau không được gọi để “bổ sung” quyền. Delegating manager không hợp nhất hai danh tính hoặc cộng authorities; nó tìm **một** kết quả authentication hoàn chỉnh.

### Vì sao nên dùng token riêng cho mỗi giao thức?

Nếu bạn dùng `UsernamePasswordAuthenticationToken` để mang cả API key, OTP, SSO code, nhiều manager có thể cùng nhận loại token mà lại hiểu credential theo cách khác nhau. Dễ xảy ra fallback ngoài dự kiến, ví dụ manager A từ chối username/password nhưng manager B lại diễn giải password như mã API.

Thiết kế tốt:
- `ApiKeyAuthenticationToken` cho API key, manager A chỉ kiểm tra class này.
- `UsernamePasswordAuthenticationToken` cho username/password, manager B chỉ kiểm tra class này.
- `JwtAuthenticationToken` hoặc authentication token tương ứng với JWT resource server, đi qua manager/decoder chuyên dụng.

Một lớp token cụ thể giúp loại credential là thành phần của **hợp đồng xác thực**, thay vì đoán dựa trên chuỗi hoặc các header tùy tiện ở tầng manager.

## 5. Quy tắc “không hỗ trợ” khác với “thất bại”

Ví dụ Java rút gọn cho một manager chỉ hiểu token API key:

~~~java
@Override
public Mono<Authentication> authenticate(Authentication candidate) {
    if (!(candidate instanceof ApiKeyToken request)) {
        return Mono.empty(); // Không thuộc loại mình xử lý.
    }

    return Mono.defer(() -> {
        if (!isValidKey(request)) {
            return Mono.error(
                new BadCredentialsException("Invalid credentials"));
        }
        return Mono.just(verifiedServiceAuthentication(request));
    });
}
~~~

**Đây là đoạn mã minh họa**, chưa định nghĩa `ApiKeyToken`, `isValidKey`, `verifiedServiceAuthentication`; bản chạy đầy đủ ở mục 7.

Những lỗi phổ biến:

~~~java
// SAI: mọi credential sai đều biến thành "không biết".
return verifyKey(input)
    .onErrorResume(error -> Mono.empty());

// SAI: token không phải loại hỗ trợ nhưng vẫn cố cast.
ApiKeyToken key = (ApiKeyToken) authentication;

// SAI: một manager nhận hết mà chưa kiểm tra token class.
if (authentication.getCredentials() != null) {
    return Mono.just(authentication);
}

// SAI: tạo Authentication authenticated trước khi thực sự kiểm tra.
return Mono.just(
    UsernamePasswordAuthenticationToken.authenticated(
        request.getPrincipal(), null, request.getAuthorities()));
~~~

Không dùng `onErrorResume(e -> Mono.empty())` như một “cách chống sập request”: nó che lỗi, biến credential sai hoặc lỗi nội bộ thành fallback sang manager sau. Đặc biệt tránh việc manager sau dễ dãi cấp quyền mà manager trước đã từ chối.

## 6. Quy tắc chọn thứ tự và fallback an toàn

### Nên đặt manager nào trước?

Nếu các manager **không có loại token giao nhau**, thứ tự ít ảnh hưởng về mặt kết quả, nhưng vẫn ảnh hưởng đến việc đo lường, logging và chi phí tạo publisher. Thường đặt manager chuyên biệt, rẻ và thường xuyên được dùng trước; tránh làm tác vụ I/O đắt tiền chỉ để phát hiện token không thuộc loại.

Nếu nhiều manager có thể xử lý cùng một loại token:
1. Viết rõ ai có quyền xác minh token đó.
2. Dùng issuer, tenant, client ID hoặc phạm vi tài nguyên đã được xác minh để chọn một manager hợp lệ.
3. Đảm bảo manager trước không “nhường” credential sai bằng `Mono.empty()`.
4. Kiểm tra hành vi khi manager đầu tiên thành công, thất bại, không tìm thấy danh tính hoặc lỗi backend.
5. Tránh `continueOnError=true` trừ khi có lý do bảo mật và kiểm thử chứng minh fallback an toàn.

### Tại sao continueOnError=true nguy hiểm?

Giả sử manager A kiểm tra API key của tenant A và phát `BadCredentialsException` khi key sai. Manager B cũng nhận cùng loại token nhưng có logic yếu hơn hoặc bản sao credential cũ. Nếu bật:

~~~java
DelegatingReactiveAuthenticationManager manager =
    new DelegatingReactiveAuthenticationManager(managerA, managerB);
manager.setContinueOnError(true);
~~~

thì khi manager A báo lỗi, delegator **có thể tiếp tục** đến manager B và chấp nhận kết quả sau đó. Đó là **hành vi có chủ đích của tùy chọn**, không phải lỗi Spring Security. Nhưng ứng dụng phải chứng minh một lỗi của A được phép chuyển sang B. Phần lớn trường hợp xác thực đa giao thức nên giữ mặc định `false` và phân biệt rõ token type.

**Không hiểu nhầm:** `setContinueOnError(true)` không làm kết quả đã authenticated của manager trước bị thay bằng manager sau. Nó chỉ thay đổi cách xử lý khi có lỗi. Khi một manager thành công, delegator dừng và trả kết quả thành công đầu tiên.

### Trường hợp “không thuộc trách nhiệm của tôi”

Nếu manager A chỉ nhận API key và đầu vào là username/password, trả `Mono.empty()` là đúng. Nếu manager A nhận API key nhưng record không tồn tại và policy xác định đây là API key không hợp lệ, thường phải trả `Mono.error(BadCredentialsException)`, không tự nhường cho manager khác. Nếu quản lý nhiều kho key có quyền fallback được duyệt, có thể dùng một dispatcher/manager duy nhất với quy tắc định tuyến rõ hơn.

## 7. Bài thực hành Java 17 chạy được

Bài thực hành thiết kế **hai `ReactiveAuthenticationManager` riêng**:
- `ApiKeyManager`: nhận `ApiKeyToken`; xác minh một key demo; trả `ROLE_SERVICE`.
- `PasswordManager`: nhận `UsernamePasswordAuthenticationToken`; xác minh password demo bằng BCrypt; trả `ROLE_USER`.

Hai manager được gắn vào `DelegatingReactiveAuthenticationManager` theo thứ tự. Chương trình chạy CLI dùng `block()` tại hàm `main` chỉ để in kết quả; trong hệ thống WebFlux thật **không dùng `block()` ở request thread**.

Key, username và password trong mã sau **chỉ là dữ liệu bài học**. Production phải đọc user/account từ kho tin cậy, có hash/secret management, tenant isolation, account status, rate limiting và audit an toàn. Không hard-code credential trong ứng dụng thật.

### 7.1. Cấu trúc dự án

~~~text
reactive-delegating-demo/
├── pom.xml
└── src/
    ├── main/java/demo/reactive/ReactiveManagersDemo.java
    └── test/java/demo/reactive/ReactiveManagersDemoTest.java
~~~

### 7.2. Maven

File `pom.xml`. Spring Boot BOM chỉ dùng quản lý các dependency tương thích; **không khởi động web server** trong CLI:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>reactive-delegating-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-core</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-crypto</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.3. Mã nguồn đầy đủ

Tạo `src/main/java/demo/reactive/ReactiveManagersDemo.java`:

~~~java
package demo.reactive;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Collection;
import java.util.List;

import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DelegatingReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class ReactiveManagersDemo {

    private ReactiveManagersDemo() {
    }

    /**
     * Authentication token dành riêng cho API key.
     * final để loại token được hỗ trợ không âm thầm đổi theo subclass.
     */
    public static final class ApiKeyToken
            extends AbstractAuthenticationToken {

        private final Object principal;
        private String apiKey;

        private ApiKeyToken(
                Object principal,
                String apiKey,
                Collection<? extends GrantedAuthority> authorities,
                boolean authenticated) {

            super(authorities);
            this.principal = principal;
            this.apiKey = apiKey;
            // Factory private kiểm soát việc tạo authenticated token.
            super.setAuthenticated(authenticated);
        }

        public static ApiKeyToken unauthenticated(String key) {
            return new ApiKeyToken(
                "unverified-service", key, List.of(), false);
        }

        private static ApiKeyToken verified(String serviceName) {
            return new ApiKeyToken(
                serviceName,
                null, // Không đưa secret sang token thành công.
                List.of(new SimpleGrantedAuthority("ROLE_SERVICE")),
                true);
        }

        @Override
        public Object getPrincipal() {
            return principal;
        }

        @Override
        public Object getCredentials() {
            return apiKey;
        }

        @Override
        public void eraseCredentials() {
            super.eraseCredentials();
            this.apiKey = null;
        }

        @Override
        public void setAuthenticated(boolean authenticated) {
            if (authenticated) {
                throw new IllegalArgumentException(
                    "Unverified token cannot be marked trusted");
            }
            super.setAuthenticated(false);
        }
    }

    /**
     * Manager thứ nhất: CHỈ biết ApiKeyToken.
     */
    public static final class ApiKeyManager
            implements ReactiveAuthenticationManager {

        private static final String DEMO_KEY = "demo-service-key";

        @Override
        public Mono<Authentication> authenticate(Authentication candidate) {
            // Không cast và không phát error khi token lạ.
            if (!(candidate instanceof ApiKeyToken request)) {
                return Mono.empty();
            }

            // defer: việc kiểm tra chỉ chạy lúc có subscription.
            return Mono.defer(() -> {
                if (request.isAuthenticated()
                        || !(request.getCredentials()
                             instanceof String supplied)
                        || supplied.isBlank()) {

                    return Mono.error(
                        new BadCredentialsException(
                            "Invalid credentials"));
                }

                byte[] expected =
                    DEMO_KEY.getBytes(StandardCharsets.UTF_8);
                byte[] actual =
                    supplied.getBytes(StandardCharsets.UTF_8);

                if (!MessageDigest.isEqual(expected, actual)) {
                    return Mono.error(
                        new BadCredentialsException(
                            "Invalid credentials"));
                }

                // Chỉ kiểm chứng thành công mới phát trusted principal.
                return Mono.just(
                    (Authentication) ApiKeyToken.verified(
                        "service-client"));
            });
        }
    }

    /**
     * Manager thứ hai: CHỈ biết username/password.
     * BCrypt được chạy ngoài event-loop trong demo.
     */
    public static final class PasswordManager
            implements ReactiveAuthenticationManager {

        private final PasswordEncoder encoder =
            new BCryptPasswordEncoder();

        // Demo: tạo 1 lần khi xây manager.
        // Production đọc password hash đã lưu ổn định từ DB/IdP.
        private final String passwordHash =
            encoder.encode("learn-password");

        @Override
        public Mono<Authentication> authenticate(Authentication candidate) {
            if (!(candidate instanceof UsernamePasswordAuthenticationToken
                    request)) {
                return Mono.empty();
            }

            return Mono.fromCallable(() -> {
                if (request.isAuthenticated()
                        || !"alice".equals(request.getPrincipal())
                        || !(request.getCredentials()
                             instanceof String password)
                        || !encoder.matches(password, passwordHash)) {

                    throw new BadCredentialsException(
                        "Invalid credentials");
                }

                return (Authentication)
                    UsernamePasswordAuthenticationToken.authenticated(
                        "alice",
                        null,
                        List.of(
                            new SimpleGrantedAuthority("ROLE_USER")
                        )
                    );
            }).subscribeOn(Schedulers.boundedElastic());
        }
    }

    public static ReactiveAuthenticationManager manager() {
        return new DelegatingReactiveAuthenticationManager(
            new ApiKeyManager(),
            new PasswordManager()
        );
    }

    public static void main(String[] args) {
        ReactiveAuthenticationManager manager = manager();

        // CHỈ CLI dùng block để in ra các kết quả.
        Authentication api = manager.authenticate(
            ApiKeyToken.unauthenticated("demo-service-key")
        ).block();

        Authentication password = manager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "learn-password")
        ).block();

        System.out.println("api-principal=" + api.getName());
        System.out.println("api-authenticated=" + api.isAuthenticated());
        System.out.println("password-principal=" + password.getName());
        System.out.println(
            "password-authenticated=" + password.isAuthenticated());

        try {
            manager.authenticate(
                ApiKeyToken.unauthenticated("wrong-key")
            ).block();
        } catch (BadCredentialsException ex) {
            System.out.println(
                "bad-key=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

### 7.4. Lệnh chạy và kết quả

Trong thư mục dự án (JDK 17+ và Maven đã cài):

~~~bash
mvn -q -DskipTests compile
mvn -q -Dexec.mainClass=demo.reactive.ReactiveManagersDemo exec:java
~~~

Các dòng **chương trình chủ động in ra**:

~~~text
api-principal=service-client
api-authenticated=true
password-principal=alice
password-authenticated=true
bad-key=BadCredentialsException
~~~

Maven/Logback/Reactor có thể phát thêm dòng log hoặc warning tùy môi trường. Phần `bad-key` minh họa quy tắc quan trọng: API key sai gây `Mono.error` và không bị chuyển tiếp sang PasswordManager trong cấu hình mặc định.

**Điểm cần lưu ý:** chương trình dùng `block()` trong `main` để chờ hai kết quả và in stdout. Đây là hành vi chấp nhận được trong một **ứng dụng dòng lệnh**, không phải phương án triển khai trong event-loop HTTP WebFlux.

### 7.5. Vì sao ví dụ đáp ứng hợp đồng?

**Phân biệt token bằng class.** `ApiKeyManager` kiểm tra `instanceof ApiKeyToken`. `PasswordManager` kiểm tra `instanceof UsernamePasswordAuthenticationToken`. Vì vậy yêu cầu password được manager đầu tiên nhường đúng cách qua `Mono.empty()`.

**Không nhầm sai credential với không hỗ trợ.** Khi `ApiKeyToken` có key sai, `ApiKeyManager` trả `Mono.error(BadCredentialsException)`. Không cho manager khác “chữa” lỗi bằng cách hiểu credential sai theo giao thức khác.

**Kết quả trusted từ server.** Token đầu vào luôn được tạo với `authenticated=false`. Sau xác minh, server tự chọn `principal` và `authorities`. Không tin role/header do client tự gửi.

**Tách secret ra khỏi kết quả.** `ApiKeyToken.verified(...)` và `UsernamePasswordAuthenticationToken.authenticated(...)` trả credentials `null`. Nếu phải giữ credential trong request token, hạn chế lifetime và không log giá trị.

**Reactor không bị chặn bởi BCrypt trên event-loop.** `PasswordManager` đặt việc `matches(...)` vào `Schedulers.boundedElastic()`. Đây là giải pháp trình bày khái niệm; production vẫn cần rate limiting và kiểm soát số authentication đồng thời, hoặc dùng built-in reactive manager theo luồng chuẩn để tránh tự viết xử lý password.

**Không sử dụng `AuthenticationManager` đồng bộ của Servlet.** Toàn bộ delegator làm việc với `Mono<Authentication>`, không trả kết quả synchronous cho filter WebFlux.

## 8. Kiểm thử Reactor StepVerifier

Kiểm thử quan trọng nhất không chỉ là “manager trả một principal”, mà là **thứ tự gọi các delegate** và **khả năng phân biệt empty/error**.

File `src/test/java/demo/reactive/ReactiveManagersDemoTest.java`:

~~~java
package demo.reactive;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DelegatingReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class ReactiveManagersDemoTest {

    private static Authentication apiRequest(String key) {
        return ReactiveManagersDemo.ApiKeyToken.unauthenticated(key);
    }

    private static Authentication passwordRequest(String password) {
        return UsernamePasswordAuthenticationToken.unauthenticated(
            "alice", password);
    }

    @Test
    void apiKeyIsAuthenticatedByFirstManager() {
        StepVerifier.create(
            ReactiveManagersDemo.manager().authenticate(
                apiRequest("demo-service-key")))
            .assertNext(auth -> {
                assertEquals("service-client", auth.getName());
                assertTrue(auth.isAuthenticated());
                assertNull(auth.getCredentials());
                assertTrue(auth.getAuthorities().stream().anyMatch(
                    a -> a.getAuthority().equals("ROLE_SERVICE")));
            })
            .verifyComplete();
    }

    @Test
    void passwordFallsThroughFirstManagerToSecond() {
        StepVerifier.create(
            ReactiveManagersDemo.manager().authenticate(
                passwordRequest("learn-password")))
            .assertNext(auth -> {
                assertEquals("alice", auth.getName());
                assertTrue(auth.isAuthenticated());
                assertTrue(auth.getAuthorities().stream().anyMatch(
                    a -> a.getAuthority().equals("ROLE_USER")));
            })
            .verifyComplete();
    }

    @Test
    void unsupportedTypeReturnsEmptyInsteadOfCastError() {
        var foreign = new AnonymousAuthenticationToken(
            "test-key", "guest",
            List.of(new SimpleGrantedAuthority("ROLE_GUEST")));

        StepVerifier.create(
            ReactiveManagersDemo.manager().authenticate(foreign))
            .verifyComplete();
    }

    @Test
    void firstEmptyLetsSecondRun() {
        AtomicInteger secondCalls = new AtomicInteger();

        ReactiveAuthenticationManager empty = auth -> Mono.empty();

        ReactiveAuthenticationManager second = auth -> {
            secondCalls.incrementAndGet();
            return Mono.just(
                UsernamePasswordAuthenticationToken.authenticated(
                    "fallback", null, List.of()));
        };

        var manager = new DelegatingReactiveAuthenticationManager(
            empty, second);

        StepVerifier.create(manager.authenticate(
                passwordRequest("anything")))
            .assertNext(auth ->
                assertEquals("fallback", auth.getName()))
            .verifyComplete();

        assertEquals(1, secondCalls.get());
    }

    @Test
    void firstSuccessStopsLaterManager() {
        AtomicInteger laterCalls = new AtomicInteger();

        ReactiveAuthenticationManager later = auth -> {
            laterCalls.incrementAndGet();
            return Mono.error(
                new IllegalStateException("Must not be invoked"));
        };

        var manager = new DelegatingReactiveAuthenticationManager(
            new ReactiveManagersDemo.ApiKeyManager(), later);

        StepVerifier.create(manager.authenticate(
                apiRequest("demo-service-key")))
            .assertNext(auth -> assertTrue(auth.isAuthenticated()))
            .verifyComplete();

        assertEquals(0, laterCalls.get());
    }

    @Test
    void invalidApiKeyDoesNotFallThroughByDefault() {
        AtomicInteger laterCalls = new AtomicInteger();

        ReactiveAuthenticationManager later = auth -> {
            laterCalls.incrementAndGet();
            return Mono.empty();
        };

        var manager = new DelegatingReactiveAuthenticationManager(
            new ReactiveManagersDemo.ApiKeyManager(), later);

        StepVerifier.create(manager.authenticate(
                apiRequest("wrong-key")))
            .expectError(BadCredentialsException.class)
            .verify();

        assertEquals(0, laterCalls.get());
    }

    @Test
    void explicitContinueOnErrorCanAcceptLaterResult() {
        // CỐ Ý minh họa RỦI RO; không copy thành auth policy production.
        AtomicInteger laterCalls = new AtomicInteger();

        ReactiveAuthenticationManager permissive = auth -> {
            laterCalls.incrementAndGet();
            return Mono.just(
                UsernamePasswordAuthenticationToken.authenticated(
                    "fallback-user", null, List.of()));
        };

        var manager = new DelegatingReactiveAuthenticationManager(
            new ReactiveManagersDemo.ApiKeyManager(),
            permissive);

        manager.setContinueOnError(true);

        StepVerifier.create(manager.authenticate(
                apiRequest("wrong-key")))
            .assertNext(auth ->
                assertEquals("fallback-user", auth.getName()))
            .verifyComplete();

        assertEquals(1, laterCalls.get());
    }

    @Test
    void wrongPasswordIsAuthenticationFailure() {
        StepVerifier.create(
            ReactiveManagersDemo.manager().authenticate(
                passwordRequest("incorrect")))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void missingApiKeyIsAuthenticationFailure() {
        StepVerifier.create(
            ReactiveManagersDemo.manager().authenticate(
                apiRequest("")))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void allEmptyMeansNoManagerRecognizedToken() {
        ReactiveAuthenticationManager first = auth -> Mono.empty();
        ReactiveAuthenticationManager second = auth -> Mono.empty();
        var manager = new DelegatingReactiveAuthenticationManager(
            first, second);

        StepVerifier.create(manager.authenticate(
                passwordRequest("ignored")))
            .verifyComplete();
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Kỳ vọng:** 10 test pass khi project được dựng đúng và Maven tải các dependency. Đây là mã thực hành để người học chạy; không phải kết quả test đã được thực thi trong hệ thống sản xuất.

### Các bất biến của bài test

| Test | Ý nghĩa |
| --- | --- |
| `apiKeyIsAuthenticatedByFirstManager` | API key đúng trả trusted service principal và `ROLE_SERVICE` |
| `passwordFallsThroughFirstManagerToSecond` | Manager 1 trả empty cho token password, manager 2 xác thực |
| `unsupportedTypeReturnsEmptyInsteadOfCastError` | Token không thuộc hai giao thức không gây `ClassCastException` |
| `firstEmptyLetsSecondRun` | `Mono.empty()` thực sự cho phép fallback |
| `firstSuccessStopsLaterManager` | Một kết quả thành công dừng việc duyệt các delegate |
| `invalidApiKeyDoesNotFallThroughByDefault` | `Mono.error()` dừng fallback theo mặc định |
| `explicitContinueOnErrorCanAcceptLaterResult` | Bật tùy chọn làm thay đổi ranh giới bảo mật; test cố tình biểu diễn nguy cơ |
| `wrongPasswordIsAuthenticationFailure` | Password sai không biến thành empty |
| `missingApiKeyIsAuthenticationFailure` | Đúng token type nhưng credential thiếu bị từ chối |
| `allEmptyMeansNoManagerRecognizedToken` | Toàn bộ delegate không xác định được sẽ không tự sinh trusted identity |

Test `explicitContinueOnErrorCanAcceptLaterResult` **không phải khuyến nghị bật `true`**: nó minh họa rõ rằng lỗi ở delegate đầu có thể được vượt qua bởi delegate sau. Chỉ áp dụng chính sách fallback sau lỗi khi đã kiểm chứng từng điều kiện, loại credential và ranh giới tenant/issuer.

## 9. Dùng manager có sẵn cho username/password trong WebFlux

Bài CLI tự viết `PasswordManager` để nhìn rõ hợp đồng `Mono`, nhưng production không nên mặc định tự triển khai toàn bộ password authentication. Spring Security cung cấp `UserDetailsRepositoryReactiveAuthenticationManager`, dùng `ReactiveUserDetailsService` để kiểm tra username/password qua `PasswordEncoder`.

Đoạn cấu hình **minh họa**, không độc lập:

~~~java
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

PasswordEncoder encoder = new BCryptPasswordEncoder();

var users = new MapReactiveUserDetailsService(
    User.withUsername("alice")
        .password(encoder.encode("learn-password"))
        .roles("USER")
        .build()
);

var passwordManager =
    new UserDetailsRepositoryReactiveAuthenticationManager(users);
passwordManager.setPasswordEncoder(encoder);

ReactiveAuthenticationManager manager =
    new DelegatingReactiveAuthenticationManager(
        apiKeyManager, passwordManager);
~~~

Trong đoạn trên, biến `apiKeyManager` là manager API key đã được tạo ở phần trước. Khi ghép vào dự án thật, các bean/user store cần được tiêm qua DI và quản lý lifecycle của Spring.

**Điểm cần lưu ý:** `MapReactiveUserDetailsService` chỉ thích hợp cho demo hoặc quy mô hẹp. Sản phẩm thực tế nên dùng repository/IdP đáng tin và bảo đảm các thao tác bên dưới thực sự reactive hoặc được offload đúng; lưu password hash và thông tin trạng thái account theo quy trình chuẩn.

Nếu tích hợp một manager đồng bộ cũ, Spring Security có `ReactiveAuthenticationManagerAdapter` để bọc `AuthenticationManager`, nhưng cần cấu hình scheduler và cân nhắc blocking. Không gọi trực tiếp `blockingManager.authenticate(...)` trên event-loop.

## 10. Ghép manager vào AuthenticationWebFilter trong WebFlux

Ở HTTP layer, `AuthenticationWebFilter` là WebFlux tương đương về mục đích với các authentication filter của Servlet, nhưng nó làm việc với `ServerWebExchange` và `Mono`.

Các API chính:

~~~java
AuthenticationWebFilter filter =
    new AuthenticationWebFilter(reactiveManager);

filter.setRequiresAuthenticationMatcher(requestMatcher);
filter.setServerAuthenticationConverter(converter);
filter.setSecurityContextRepository(contextRepository);
filter.setAuthenticationSuccessHandler(successHandler);
filter.setAuthenticationFailureHandler(failureHandler);
~~~

**Đây là mẫu API**, các biến `reactiveManager`, `requestMatcher`, `converter`, `contextRepository` và handlers cần được cung cấp.

Luồng:

1. `setRequiresAuthenticationMatcher` quyết định filter có áp dụng cho request không.
2. `ServerAuthenticationConverter.convert(ServerWebExchange)` đọc credential và trả `Mono<Authentication>` **chưa xác thực**, hoặc `Mono.empty()` nếu không có cơ chế login phù hợp.
3. `AuthenticationWebFilter` gửi token đến `ReactiveAuthenticationManager` tổng hợp.
4. Nếu thành công, filter đặt kết quả trong **`ReactiveSecurityContextHolder`** và gọi success handler; cách lưu giữa request phụ thuộc `ServerSecurityContextRepository`.
5. Nếu authentication lỗi, failure handler trả status/response thích hợp.

**Hai vị trí trả empty có ý nghĩa khác:**

~~~text
Converter -> Mono.empty()
    : Không tạo Authentication để gửi vào manager.
      Không có authentication attempt của filter đó.

Manager -> Mono.empty()
    : Đã có Authentication, nhưng manager hiện tại không nhận trách
      nhiệm; DelegatingReactiveAuthenticationManager có thể thử tiếp.
~~~

Đừng để converter đọc sai header rồi tạo `Authentication` không liên quan; đừng để manager đọc trực tiếp HTTP headers bằng thread-local hoặc tìm `HttpServletRequest` trong WebFlux.

## 11. Ví dụ cấu hình HTTP với một converter cho hai kiểu credential

Đây là **đoạn tích hợp minh họa** dùng trong một ứng dụng Spring Boot WebFlux; không phải file có thể biên dịch cùng `pom.xml` CLI ở mục 7 nếu chưa thêm web dependencies và class Spring Configuration.

Bổ sung dependency phù hợp trong ứng dụng WebFlux:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
~~~

Không thêm `spring-boot-starter-web` vào demo WebFlux này nếu không có chủ đích, vì Spring Boot có quy tắc chọn web application type khi cả MVC và WebFlux cùng có mặt.

Cấu hình giả định lớp `ReactiveManagersDemo` ở mục 7 có trong cùng module/classpath:

~~~java
package demo.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.security.web.server.authentication.ServerHttpBasicAuthenticationConverter;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;
import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
public class ExampleWebFluxSecurity {

    @Bean
    ReactiveAuthenticationManager reactiveManager() {
        return ReactiveManagersDemo.manager();
    }

    @Bean
    SecurityWebFilterChain apiChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager manager) {

        AuthenticationWebFilter filter =
            new AuthenticationWebFilter(manager);

        // Chỉ áp dụng cho /api/**.
        filter.setRequiresAuthenticationMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**"));

        var basicConverter =
            new ServerHttpBasicAuthenticationConverter();

        ServerAuthenticationConverter converter = exchange -> {
            var headers = exchange.getRequest().getHeaders();
            String apiKey = headers.getFirst("X-API-Key");
            String authorization =
                headers.getFirst("Authorization");

            // Không cho request chỉ định đồng thời hai cơ chế.
            if (apiKey != null && authorization != null) {
                return Mono.error(new BadCredentialsException(
                    "Ambiguous credentials"));
            }

            if (apiKey != null) {
                return Mono.just(
                    ReactiveManagersDemo.ApiKeyToken.unauthenticated(
                        apiKey));
            }

            // HTTP Basic converter trả UsernamePasswordAuthenticationToken
            // hoặc Mono.empty nếu header Basic không xuất hiện.
            return basicConverter.convert(exchange);
        };

        filter.setServerAuthenticationConverter(converter);

        // Header-based stateless API: không ghi HTTP session.
        filter.setSecurityContextRepository(
            NoOpServerSecurityContextRepository.getInstance());

        filter.setAuthenticationFailureHandler((webFilter, error) -> {
            var response = webFilter.getExchange().getResponse();
            response.setStatusCode(HttpStatus.UNAUTHORIZED);
            return response.setComplete();
        });

        return http
            .securityMatcher(
                ServerWebExchangeMatchers.pathMatchers("/api/**"))
            .authorizeExchange(ex -> ex
                .anyExchange().authenticated())
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .exceptionHandling(ex -> ex.authenticationEntryPoint(
                (exchange, error) -> {
                    var response = exchange.getResponse();
                    response.setStatusCode(HttpStatus.UNAUTHORIZED);
                    return response.setComplete();
                }))
            .addFilterAt(filter, SecurityWebFiltersOrder.AUTHENTICATION)
            .build();
    }
}
~~~

**Giải thích cấu hình:**

- `AuthenticationWebFilter` được chèn tại `SecurityWebFiltersOrder.AUTHENTICATION`.
- `X-API-Key` tạo `ApiKeyToken`, `Authorization: Basic ...` được converter có sẵn chuyển thành `UsernamePasswordAuthenticationToken`.
- Nếu có cả hai loại credential, filter trả lỗi thay vì tùy tiện ưu tiên một header, tránh confusion attack.
- `DelegatingReactiveAuthenticationManager` định tuyến dựa trên class token, không trực tiếp đọc HTTP request.
- `NoOpServerSecurityContextRepository` minh họa cơ chế stateless: kết quả xác thực nằm trong **request hiện tại**, không tự duy trì session cho request sau.
- `.httpBasic(...disable())` tắt filter Basic mặc định để tránh việc nó cùng xử lý header trước custom filter; converter Basic ở đây được gọi từ **filter tự tạo**.
- `.formLogin(...disable())` tránh filter login khác tranh xử lý request.
- Failure handler và entry point cùng trả 401 thống nhất; lỗi auth không tiết lộ secret hay chi tiết account.

**Giới hạn:** đây là đoạn cấu hình dành cho module WebFlux có dependency thích hợp. Ứng dụng còn cần controller `/api/**` và chính sách CSRF dựa trên threat model. Nếu hoàn toàn stateless và credentials chỉ được gửi trong headers không tự đính kèm, CSRF policy có thể khác; **không** tắt CSRF một cách vô điều kiện nếu ứng dụng còn dùng session cookie hoặc form login ở chain khác.

### Ví dụ gọi HTTP

Sau khi có controller `GET /api/me` yêu cầu đã xác thực, hai request tương ứng:

~~~bash
curl -i http://localhost:8080/api/me \
  -H 'X-API-Key: demo-service-key'
~~~

~~~bash
curl -i -u alice:learn-password \
  http://localhost:8080/api/me
~~~

Nếu authentication thành công, controller có thể thấy `service-client`/`ROLE_SERVICE` ở request API key hoặc `alice`/`ROLE_USER` ở request Basic. Đây là hành vi dự kiến **khi controller và cấu hình WebFlux đã được xây dựng đầy đủ**, không phải output của chương trình CLI chỉ có `pom.xml` ở mục 7.

**Cảnh báo:** HTTP Basic gửi credentials bằng Base64 trong header, không phải encryption. Chỉ dùng qua HTTPS. API key cũng là credential bearer; cần lưu hash/key ID trên server, áp dụng rotation, rate limiting và không ghi log raw headers.

## 12. ReactiveAuthenticationManagerResolver khi nào tốt hơn delegating?

`DelegatingReactiveAuthenticationManager` phù hợp khi bạn có **một token được gửi cho danh sách manager có thứ tự**, và mỗi manager có quy tắc tự nhận trách nhiệm.

Nhưng trong ứng dụng phức tạp, quyết định chọn manager đôi khi phải dựa vào **ngữ cảnh của request**:

- Multi-tenant, mỗi tenant có kho xác thực riêng.
- JWT đến từ nhiều authorization server/issuer.
- Định tuyến theo host/path đã cấu hình hoặc client registration.
- API version/region khác nhau cần policy riêng.
- Cơ chế dùng certificate hoặc mTLS do gateway/ingress xác minh.

Khi đó `ReactiveAuthenticationManagerResolver<ServerWebExchange>` cho phép chọn một manager phù hợp với request/issuer context, thay vì đưa mọi token cho tất cả manager.

~~~java
// Minh họa ý tưởng, chưa phải cấu hình độc lập.
ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver =
    exchange -> {
        String path = exchange.getRequest().getPath().value();

        if (path.startsWith("/tenant-a/")) {
            return Mono.just(managerForTenantA);
        }
        if (path.startsWith("/tenant-b/")) {
            return Mono.just(managerForTenantB);
        }
        return Mono.empty();
    };

AuthenticationWebFilter filter =
    new AuthenticationWebFilter(resolver);
~~~

**Giới hạn bảo mật:** path hoặc header do client gửi **chưa chắc là nguồn tin cậy** cho tenant/issuer. Resolver phải dùng một cơ chế định tuyến được phê duyệt và manager được chọn phải **xác minh lại token, chữ ký, issuer, audience, tenant**. Đặc biệt không lấy nguyên một `iss` claim từ JWT chưa xác minh và cấp quyền dựa trên claim đó; bất kỳ lựa chọn decoder nào cũng phải dùng allowlist và xác minh chữ ký/claims của đúng issuer.

### Delegating và resolver không loại trừ nhau

Bạn có thể dùng resolver chọn manager theo tenant, rồi bên trong mỗi tenant manager có một delegating manager riêng cho API key/username-password. Nhưng cần kiểm soát số lượng manager, resource sử dụng và cache; không tạo một full manager chain mới cho mỗi HTTP request không cần thiết.

## 13. Một lựa chọn khác: nhiều SecurityWebFilterChain

Spring Security WebFlux hỗ trợ nhiều `SecurityWebFilterChain`, mỗi chain có matcher và thứ tự (ví dụ `@Order`).

~~~text
/api/partners/** -> chain A: API key
/api/users/**    -> chain B: JWT bearer
/web/**          -> chain C: form login, session/CSRF
~~~

Trường hợp này, chính **chain selection** giới hạn những filter và policy được áp dụng. Nếu hai chain có matcher chồng lấn, chain ưu tiên cao hơn có thể “nuốt” request, gây bỏ qua cơ chế định dùng ở chain sau. Luôn viết integration tests cho matcher và thứ tự.

Chọn:
- **DelegatingReactiveAuthenticationManager:** nhiều manager có thể xử lý cùng một luồng authentication với token classes khác nhau.
- **ReactiveAuthenticationManagerResolver:** chọn manager theo ngữ cảnh exchange/token issuer/tenant.
- **Nhiều SecurityWebFilterChain:** phân tách toàn bộ chính sách bảo mật theo path/host, including CSRF, entrypoint, session và authentication filters.
- **DelegatingServerAuthenticationConverter:** kết hợp nhiều cách đọc credential từ một exchange, **không** thay cho việc phối hợp manager.

Đừng trộn ba cấp phối hợp này thành một sự kiện “manager tự tìm filter”. Mỗi cấp xử lý một trách nhiệm riêng.

## 14. Reactive không đồng nghĩa với cho phép blocking

### Với I/O

Ứng dụng WebFlux xử lý request trên event-loop; nếu một manager thực hiện `jdbcRepository.findBy...` đồng bộ hoặc gọi HTTP client blocking trên event-loop, throughput và latency có thể giảm mạnh.

Tùy nguồn dữ liệu:
- R2DBC/repository reactive: compose `Mono`/`Flux` trực tiếp.
- WebClient: dùng HTTP nonblocking và giới hạn timeout/retry.
- Hệ thống chỉ có JDBC/SDK blocking: offload đến scheduler phù hợp hoặc dùng `ReactiveAuthenticationManagerAdapter` có scheduler theo API; giới hạn concurrent requests.
- BCrypt/Argon2 password hashing: CPU-cost cao; dùng worker scheduler/policy tài nguyên phù hợp và rate limiting.

### Vì sao không dùng block() trong authenticate()?

~~~java
// SAI trong request path WebFlux:
@Override
public Mono<Authentication> authenticate(Authentication authentication) {
    UserRecord user = repository.findById(...).block();
    return Mono.just(toAuthentication(user));
}
~~~

`block()` có thể gây lỗi trên thread nonblocking hoặc làm nghẽn event-loop. Cách đúng là compose:

~~~java
// Minh họa, repository và toAuthentication được định nghĩa trong ứng dụng.
@Override
public Mono<Authentication> authenticate(Authentication authentication) {
    return reactiveRepository.findUser(authentication.getName())
        .flatMap(user -> verifyCredential(user, authentication))
        .map(this::toAuthentication);
}
~~~

Nếu có thao tác blocking không thể thay thế, phải offload có kiểm soát và hiểu scheduler. Không dùng `parallel()` hoặc `subscribe()` thủ công trong manager chỉ để biến blocking thành nonblocking; tự subscribe sẽ phá context, lỗi, cancellation và khả năng kiểm soát request.

### Timeout và lỗi backend

Khi IdP/DB gặp timeout, hãy trả một lỗi xác thực **đúng ngữ nghĩa và có observability**, không biến tất cả thành `Mono.empty()` cho manager sau tiếp tục. `AuthenticationServiceException` phù hợp hơn `BadCredentialsException` nếu hệ thống backend lỗi; UI/public API vẫn có thể chỉ trả thông điệp chung để không lộ thông tin.

Việc `retryWhen` không giới hạn trên login path có thể gây khuếch đại tải và credential brute-force. Cần retry policy có giới hạn hoặc fail-closed, circuit breaker khi thích hợp và test cancellation/timeouts.

## 15. Bảo mật: principal, authorities và ranh giới tin cậy

Một manager tạo kết quả `Authentication` đã xác thực phải:

1. Xác minh credentials thật, không chỉ kiểm tra token class.
2. Tạo principal từ danh tính server/IdP đã tin cậy, không lấy role từ input client.
3. Đặt authorities theo policy, ví dụ `ROLE_SERVICE` cho service account và `ROLE_USER` cho user.
4. Không giữ raw API key/password trong trusted token khi không cần.
5. Kiểm tra account status, tenant, issuer/audience đối với token phù hợp.
6. Không cho một manager thuộc tenant A “nhường” token sai sang tenant B và được cấp quyền chéo.
7. Đảm bảo `Mono.just(authResult)` thực sự là kết quả trusted, không trả lại đối tượng unauthenticated ban đầu như một kết quả thành công.
8. Phân biệt authn và authorization: được xác thực không đồng nghĩa có quyền vào mọi endpoint.

Với WebFlux, security context theo **Reactor context**, không đơn giản là `ThreadLocal` của `SecurityContextHolder` Servlet. Nếu bạn dùng `subscribe()` hoặc tự tạo thread ở giữa luồng, context propagation có thể bị mất. Hãy để `AuthenticationWebFilter` và framework quản lý propagation.

### Quy tắc về ghi log

Không log:
- `Authorization` header, API key, password, bearer token.
- Raw `Authentication.getCredentials()`.
- Signed JWT đầy đủ hoặc refresh token.
- Exception message chứa dữ liệu nhạy cảm từ backend.

Nên log metadata an toàn như loại token, manager name, outcome, request ID, subject đã xác minh, tenant/issuer đã validate và thời gian xử lý. Nếu ghi label “manager A denied”, tuyệt đối không đưa raw secret vào log.

## 16. Những tình huống dễ nhầm trong dự án thật

### 16.1. Tại sao manager 2 không được gọi dù manager 1 từ chối user?

Nếu manager 1 trả `Mono.error(BadCredentialsException)`, delegator **mặc định dừng**. Đây là hợp đồng expected: credential thuộc loại đó đã được manager 1 xử lý và xác định sai. Muốn fallback do **không hỗ trợ token**, manager 1 phải trả `Mono.empty()` *trước khi* kiểm chứng credential mà nó không có trách nhiệm.

### 16.2. Có nên bật continueOnError để luôn có cơ hội login?

Không nên mặc định. Một manager bị từ chối vì account locked, password sai hoặc token bị thu hồi là lý do quan trọng để chặn, không phải gợi ý thử một provider yếu hơn. Nếu cần high availability, nên xử lý sự cố backend tại tầng hạ tầng hoặc cơ chế chuyển vùng có cùng chính sách xác thực, thay vì mở fallback ngẫu nhiên giữa các cơ chế.

### 16.3. Tại sao một Mono empty từ converter khác empty từ manager?

Converter không tạo token nên filter không gọi bất kỳ manager nào. Trong khi đó, manager empty xảy ra **sau khi đã có token**, và delegator có thể thử manager tiếp theo. Hai bước nằm ở những lớp trách nhiệm khác nhau.

### 16.4. Nếu nhiều manager cùng nhận UsernamePasswordAuthenticationToken?

Thứ tự quyết định ai thành công trước. Rủi ro: cùng một username/password được hiểu khác ở các backend, hoặc fallback bypass account status của một store. Nên phân tách bằng token subtype hoặc chọn manager qua resolver/context đã được verify. Không lấy `username.endsWith("@tenant")` từ input client làm bằng chứng identity thuộc tenant đó mà thiếu kiểm tra.

### 16.5. Vì sao không dùng ProviderManager của Servlet?

`ProviderManager`/`AuthenticationProvider` là API synchronous trả `Authentication` và thường được dùng trong Servlet. `DelegatingReactiveAuthenticationManager`/`ReactiveAuthenticationManager` trả `Mono<Authentication>`. WebFlux filter cần reactive interface. Nếu phải tái sử dụng hệ thống synchronous cũ, cần adapter/scheduler thay vì ép kiểu hoặc block() trên Netty threads.

### 16.6. Dùng JWT manager cùng password manager có vấn đề gì?

Không phải bản thân việc cùng tồn tại là vấn đề. Vấn đề là dữ liệu JWT phải được validate signature, issuer/audience, token type/expiry và scope; không thể chỉ parse `sub` hoặc `roles` từ chuỗi token rồi cho manager trả `Mono.just`. Thông thường hãy dùng `oauth2ResourceServer().jwt()` và decoder chuẩn, hoặc manager resolver cho đa issuer thay vì xây JWT signature verification bằng tay.

### 16.7. Có thể có cả form login stateful và API stateless không?

Có. Nhưng HTTP session/CSRF/cookie và header-based bearer/API key có threat model khác nhau. Nên dùng các `SecurityWebFilterChain` riêng nếu policy khác biệt, hoặc thiết kế matcher và repository rõ trong cùng chain. Một `DelegatingReactiveAuthenticationManager` **không** tự quản lý session, CSRF hay logout.

### 16.8. Nếu tất cả manager trả empty thì sao?

Đó là trường hợp không manager nào cung cấp được kết quả. Delegator không tự tạo authenticated user. Ở HTTP layer cần để authentication filter/entry point/authorization từ chối theo policy, thường là 401 khi protected endpoint không có danh tính. Không coi “empty” là thành công.

### 16.9. Mono.just từ manager đầu nhưng authenticated=false có được không?

Đó là thiết kế sai. ReactiveAuthenticationManager được kỳ vọng trả một đối tượng kết quả khi xác thực thành công; manager phải kiểm chứng credential và xây trusted result. Không dựa vào delegator để kiểm tra lại cờ `authenticated` thay cho logic của manager.

### 16.10. Lỗi manager sau có được bỏ qua bởi manager trước thành công không?

Manager trước đã thành công sẽ dừng quá trình; manager sau không cần được gọi. Nếu bạn chạy song song các manager rồi ghép bằng `Mono.firstWithSignal`, đó là một semantics khác và có thể dễ gây race/bypass. Delegator được thiết kế để duyệt theo thứ tự, không “đua” giữa các backend xác thực.

## 17. Checklist thiết kế và review

- [ ] Mỗi cơ chế authentication có loại token rõ ràng, không dùng sai token username/password cho API key hoặc JWT.
- [ ] Mỗi `ReactiveAuthenticationManager` trả `Mono.empty()` **chỉ** khi không thể xử lý hoặc không xác định kết quả theo hợp đồng.
- [ ] Credential thuộc loại được hỗ trợ nhưng sai phải phát `Mono.error(AuthenticationException)`.
- [ ] Manager không trả `null` hoặc tự tạo trusted principal trước khi kiểm chứng.
- [ ] `DelegatingReactiveAuthenticationManager` có thứ tự delegate được xác định và kiểm thử.
- [ ] Giữ `setContinueOnError(false)` mặc định trừ khi security review phê duyệt chính sách khác.
- [ ] Đã test first success stops, first empty continues, first error stops, all empty và fallback nếu có cấu hình bật.
- [ ] HTTP converter chỉ tạo token khi request có credential đúng format, không “ăn” request của filter khác.
- [ ] AuthenticationWebFilter có matcher/manager/success-failure handler đúng chain.
- [ ] Khi cần phân tách theo tenant/issuer, đánh giá `ReactiveAuthenticationManagerResolver` hoặc multi-chain.
- [ ] Mọi JWT/access token được xác minh bằng decoder/validator được bảo trì; issuer/audience và tenant policy rõ.
- [ ] Không có blocking DB/SDK trong Netty event-loop; dùng reactive driver hoặc adapter/scheduler có giới hạn.
- [ ] Password được hash bằng PasswordEncoder phù hợp, có rate limiting/lockout chính sách và audit.
- [ ] Authorities do server quyết định; credentials không lộ trong trusted token, log hoặc HTTP response.
- [ ] Stateless vs stateful rõ ràng; không mong delegating manager tự lưu session/CSRF.
- [ ] Integration tests kiểm tra đúng 401/403, header conflict, không có credential, token hết hạn và policy từng chain.

## 18. Câu hỏi tự kiểm tra

1. Vì sao `Mono.empty()` từ manager API key có ý nghĩa khác `Mono.error(BadCredentialsException)`?
2. Theo mặc định, một lỗi ở manager đầu tiên có cho phép manager thứ hai thử credential đó không?
3. `setContinueOnError(true)` có thể dẫn đến loại bypass nào khi hai manager hỗ trợ cùng token?
4. Làm sao để manager API key và manager password không tranh xử lý cùng `Authentication`?
5. `AuthenticationWebFilter` gọi manager trước hay sau `ServerAuthenticationConverter`?
6. Converter trả `Mono.empty()` có dẫn đến mọi manager được gọi hay không?
7. Vì sao không dùng `block()` trong Netty event-loop của WebFlux?
8. Spring Security cung cấp class built-in nào để xác thực username/password với `ReactiveUserDetailsService`?
9. Khi nào `ReactiveAuthenticationManagerResolver<ServerWebExchange>` tốt hơn một delegator?
10. Khi nào nhiều `SecurityWebFilterChain` tốt hơn một chain có nhiều manager?
11. Nếu JWT có chữ ký hợp lệ nhưng sai `aud` hoặc `iss`, có được fallback sang password manager không?
12. Vì sao một kết quả từ `Mono.just(auth)` phải có principal/authorities đã được kiểm chứng?
13. Nếu mọi manager trả `Mono.empty()`, delegator có cấp quyền anonymous user tự động không?
14. Việc dùng `Mono.firstWithSignal` để chọn manager có tương đương delegating theo thứ tự không?
15. Làm thế nào kiểm thử rằng manager sau không bị gọi khi manager trước đã thành công hoặc phát lỗi?

## 19. Tài liệu chính thức

1. Spring Security 6.5 — `DelegatingReactiveAuthenticationManager`, constructors, `setContinueOnError`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/DelegatingReactiveAuthenticationManager.html
2. Spring Security 6.5 — `ReactiveAuthenticationManager` interface: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html
3. Spring Security 6.5 — `AuthenticationWebFilter` và các bước convert/authentication: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
4. Spring Security 6.5 — `ServerAuthenticationConverter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html
5. Spring Security 6.5 — WebFlux Security Configuration, multiple chains: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
6. Spring Security 6.5 — `UserDetailsRepositoryReactiveAuthenticationManager`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html
7. Spring Security 6.5 — `ReactiveAuthenticationManagerAdapter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManagerAdapter.html
8. Spring Security 6.5 — Reactive Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
9. Reactor Core — Mono và việc xử lý empty/error: https://projectreactor.io/docs/core/release/reference/
10. Reactor Test — StepVerifier: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html

**Thông điệp cần nhớ:** `DelegatingReactiveAuthenticationManager` điều phối **các manager theo thứ tự**, chứ không tự xác minh credentials. `Mono.empty()` nghĩa là “tôi không xác định được, hãy thử cơ chế khác”; `Mono.error()` nghĩa là “cơ chế đã từ chối hoặc gặp lỗi” và **mặc định không fallback**. Kết hợp token types rõ ràng, phản hồi lỗi đúng ngữ nghĩa và test thứ tự là nền tảng để hỗ trợ nhiều cơ chế xác thực reactive mà không làm yếu chính sách bảo mật.