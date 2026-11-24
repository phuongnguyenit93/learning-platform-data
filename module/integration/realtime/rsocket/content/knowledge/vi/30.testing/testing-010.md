# Kiểm thử xác thực, phân quyền và token hết hạn

## Mục tiêu bài học

Một RSocket server có thể nhận được request hợp lệ về mặt giao thức nhưng vẫn phải từ chối vì người gọi chưa đăng nhập, token không còn hiệu lực hoặc danh tính không có quyền gọi route. Kiểm thử bảo mật cần xác nhận cả ba lớp này, đồng thời bảo đảm request bị từ chối không chạy vào handler nghiệp vụ.

Sau bài này, bạn có thể:

- Phân biệt authentication, authorization và kiểm tra thời hạn JWT.
- Cấu hình Spring Security cho RSocket bằng `@EnableRSocketSecurity`.
- Gửi bearer token trong metadata của SETUP hoặc từng request.
- Viết integration test với `RSocketRequester`, `@SpringBootTest` và `StepVerifier`.
- Kiểm tra request không có token, token sai, token hết hạn và token thiếu authority.
- Kiểm thử quy tắc phân quyền theo route và thứ tự matcher.
- Dùng `JwtTimestampValidator` cùng `Clock` cố định để test thời gian ổn định.
- Phân biệt test dùng decoder giả với test xác minh chữ ký JWT thực.
- Kiểm tra token refresh, clock skew và hành vi khi connection được chia sẻ.

## Ba câu hỏi bảo mật phải được kiểm tra riêng

| Lớp | Câu hỏi | Ví dụ lỗi |
|---|---|---|
| Authentication | Request thuộc về ai? Credential có hợp lệ không? | Không có token, token sai chữ ký, token hết hạn |
| Authorization | Danh tính đó có quyền gọi route này không? | Có token hợp lệ nhưng thiếu `SCOPE_inventory.read` |
| Token validity | JWT có đúng thời hạn và claims được yêu cầu không? | `exp` đã qua, `nbf` ở tương lai, sai `iss` hoặc `aud` |

Một token được ký đúng vẫn có thể hết hạn. Một token còn hạn vẫn có thể thiếu quyền. Vì vậy, test chỉ kiểm tra “request có token thì thành công” chưa đủ để chứng minh hệ thống an toàn.

~~~mermaid
flowchart TD
    A[RSocket request] --> B{Có credential?}
    B -->|Không| X[Authentication failed]
    B -->|Có| C{JWT hợp lệ?}
    C -->|Không| X
    C -->|Có| D{Có authority cho route?}
    D -->|Không| Y[Authorization denied]
    D -->|Có| E[Spring handler]
    E --> F[Response]
~~~

## Cấu hình Spring Security cho RSocket

Spring Security tích hợp với RSocket qua `PayloadSocketAcceptorInterceptor`. Với JWT, DSL `.jwt(...)` đăng ký converter để đọc bearer authentication metadata và dùng `ReactiveJwtDecoder` xác minh token.

Ví dụ cấu hình server:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

@Configuration
@EnableRSocketSecurity
class RSocketSecurityConfiguration {

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
            RSocketSecurity rsocket) {

        rsocket
            .authorizePayload(authorize -> authorize
                .route("inventory.read")
                    .hasAuthority("SCOPE_inventory.read")
                .route("inventory.admin")
                    .hasAuthority("SCOPE_inventory.admin")
                .anyRequest().authenticated()
                .anyExchange().permitAll()
            )
            .jwt(Customizer.withDefaults());

        return rsocket.build();
    }
}
~~~

Các quy tắc được đánh giá theo thứ tự khai báo; quy tắc đầu tiên khớp sẽ được áp dụng. Vì vậy, route cụ thể phải đứng trước quy tắc tổng quát.

Trong ví dụ:

- `inventory.read` yêu cầu authority `SCOPE_inventory.read`.
- `inventory.admin` yêu cầu authority `SCOPE_inventory.admin`.
- Request có metadata nhưng không khớp route cụ thể phải được xác thực.
- Exchange không có request metadata được cho phép theo chính sách ví dụ.

Nếu muốn yêu cầu credential ngay khi mở connection, có thể thêm quy tắc `.setup().hasRole("SETUP")`. Khi đó client phải gửi credential có authority `ROLE_SETUP` trong SETUP. Đừng thêm quy tắc này vào test per-request authentication nếu mục tiêu là cho phép mở connection trước rồi xác thực từng request.

### Cấu hình ReactiveJwtDecoder

Với issuer hỗ trợ discovery/JWK Set, Spring Security có thể tạo decoder từ issuer URI:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoders;

@Configuration
class JwtConfiguration {

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        return ReactiveJwtDecoders.fromIssuerLocation(
            "https://idp.example.com/issuer"
        );
    }
}
~~~

Decoder production cần xác minh chữ ký bằng khóa tin cậy và các claim cần thiết. Resource Server JWT mặc định kiểm tra các timestamp như `exp`, `nbf` và issuer khi được cấu hình tương ứng. Nếu hệ thống yêu cầu audience cụ thể, hãy thêm validator cho `aud`; không giả định kiểm tra issuer tự động kiểm tra mọi claim nghiệp vụ.

Spring Boot có thể tự cấu hình phần RSocket Security khi các dependency phù hợp được đưa vào application context. Nếu không dùng Boot auto-configuration, cần đăng ký `SecuritySocketAcceptorInterceptor` với RSocket server customizer.

## Gửi token trong SETUP hay trong từng request?

RSocket cho phép gửi authentication metadata ở hai phạm vi.

### Authentication tại SETUP

Dùng khi một connection chỉ đại diện cho một danh tính, ví dụ một thiết bị di động hoặc một service account:

~~~java
import io.rsocket.metadata.WellKnownMimeType;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.BearerTokenAuthenticationEncoder;
import org.springframework.security.rsocket.metadata.BearerTokenMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

MimeType authenticationMimeType = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString()
);

RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies ->
        strategies.encoder(new BearerTokenAuthenticationEncoder())
    )
    .setupMetadata(new BearerTokenMetadata(accessToken), authenticationMimeType)
    .tcp("localhost", 7000);
~~~

`BearerTokenMetadata` là wrapper mà Spring Security cung cấp; `BearerTokenAuthenticationEncoder` mã hóa wrapper theo Bearer Authentication Metadata Extension. Dùng encoder này trong `RSocketStrategies` khi client gửi bearer token bằng API Spring.

Token được dùng để xác thực connection khi SETUP. Các request sau đó dùng identity gắn với session theo cấu hình bảo mật.

### Authentication tại request time

Dùng khi một connection được chia sẻ bởi nhiều người dùng hoặc token có thể thay đổi giữa các request:

~~~java
import org.springframework.security.rsocket.metadata.BearerTokenMetadata;
import reactor.core.publisher.Mono;

MimeType authenticationMimeType = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString()
);

Mono<InventoryView> result = requester
    .route("inventory.read")
    .metadata(new BearerTokenMetadata(accessToken), authenticationMimeType)
    .data(new InventoryQuery("SKU-42"))
    .retrieveMono(InventoryView.class);
~~~

Với cách này, mỗi request có thể mang token riêng. Đây là lựa chọn phù hợp để test token hết hạn hoặc quyền khác nhau trên cùng một RSocket connection.

**Lưu ý về token hết hạn:** nếu token chỉ được gửi trong SETUP, việc JWT hết hạn sau khi session đã được xác thực không đồng nghĩa RSocket tự đóng connection hoặc tự xác thực lại ở từng request. Nếu cần áp dụng thời hạn token cho từng thao tác, hãy gửi credential ở request time hoặc xây dựng chính sách giới hạn tuổi session và tái xác thực rõ ràng.

## Tạo handler để kiểm thử

Ví dụ service expose hai route với quyền khác nhau:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

record InventoryQuery(String sku) {}
record InventoryView(String sku, int available) {}

@Controller
class InventoryController {

    @MessageMapping("inventory.read")
    Mono<InventoryView> read(InventoryQuery query) {
        return Mono.just(new InventoryView(query.sku(), 12));
    }

    @MessageMapping("inventory.admin")
    Mono<InventoryView> adminRead(InventoryQuery query) {
        return Mono.just(new InventoryView(query.sku(), 12));
    }
}
~~~

Trong test, `inventory.read` và `inventory.admin` là hai route có cùng kiểu payload nhưng yêu cầu authority khác nhau. Điều này giúp kiểm tra authorization độc lập với business logic.

## Kiểm thử qua RSocket server thật trong Spring Boot

Unit test cho validator hoặc authorization rule hữu ích, nhưng integration test qua transport còn xác nhận metadata được encode, server nhận đúng payload, security interceptor được gắn vào RSocket server và route thực sự bị chặn.

Các dependency test thường gồm:

- `spring-boot-starter-rsocket` cho RSocket server/requester.
- `spring-boot-starter-security` cho nền tảng Spring Security.
- `spring-security-rsocket` và `spring-security-messaging` cho RSocket authentication/authorization integration.
- `spring-boot-starter-oauth2-resource-server` cho JWT decoder và xác minh chữ ký/claims.
- `spring-boot-starter-test` cho JUnit Jupiter, AssertJ và Spring Test.

Ví dụ Maven (các phiên bản được quản lý bởi Spring Boot BOM):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-rsocket</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-rsocket</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-messaging</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Dùng dependency management của Spring Boot để giữ Spring Framework, Spring Security, Reactor và RSocket ở các phiên bản tương thích.

### Khởi động server trên port ngẫu nhiên

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import io.rsocket.metadata.WellKnownMimeType;
import org.springframework.security.rsocket.metadata.BearerTokenAuthenticationEncoder;
import org.springframework.security.rsocket.metadata.BearerTokenMetadata;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = "spring.rsocket.server.port=0")
@Import(TestJwtDecoderConfiguration.class)
class RSocketSecurityIntegrationTests {

    private static final MimeType AUTHENTICATION_MIME =
        MimeTypeUtils.parseMimeType(
            WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString()
        );

    @LocalRSocketServerPort
    int port;

    RSocketRequester requester;

    @BeforeEach
    void connect(@Autowired RSocketRequester.Builder requesterBuilder) {
        requester = requesterBuilder
            .rsocketStrategies(strategies ->
                strategies.encoder(new BearerTokenAuthenticationEncoder())
            )
            .tcp("localhost", port);
    }

    @AfterEach
    void close() {
        if (requester != null) {
            requester.dispose();
        }
    }
}
~~~

`spring.rsocket.server.port=0` yêu cầu hệ điều hành cấp một port trống. `@LocalRSocketServerPort` đưa port thực tế vào test. Requester có thể được tái sử dụng để gửi nhiều request với token khác nhau.

### Helper gửi request có hoặc không có token

~~~java
private Mono<InventoryView> call(String route, String token) {
    RSocketRequester.RequestSpec request = requester.route(route);

    if (token != null) {
        request = request.metadata(
            new BearerTokenMetadata(token),
            AUTHENTICATION_MIME
        );
    }

    return request
        .data(new InventoryQuery("SKU-42"))
        .retrieveMono(InventoryView.class);
}
~~~

Đây là phần helper của test class ở trên. Metadata mặc định của Spring requester là composite metadata, cho phép route và bearer authentication cùng nằm trong request.

## Ma trận test authentication và authorization

Một bộ test cơ bản nên bao gồm:

| Tình huống | Credential | Authority | Kết quả mong đợi |
|---|---|---|---|
| Không gửi token | Không có | Không có | Bị từ chối |
| Token sai hoặc không giải mã được | Không hợp lệ | Không xác định | Bị từ chối |
| Token hợp lệ gọi route read | Còn hạn | `SCOPE_inventory.read` | Thành công |
| Token read gọi route admin | Còn hạn | Chỉ có `SCOPE_inventory.read` | Bị từ chối |
| Token admin gọi route admin | Còn hạn | Có `SCOPE_inventory.admin` | Thành công |
| Token hết hạn gọi route read | Hết hạn | Có scope read trong claim | Bị từ chối |
| Token có `nbf` ở tương lai | Chưa có hiệu lực | Có scope | Bị từ chối |
| Token sai issuer hoặc audience | Sai claim | Có scope | Bị từ chối theo validator |

Authentication thành công không có nghĩa authorization thành công. Test “read token gọi admin route” là test quan trọng để phát hiện cấu hình chỉ kiểm tra `authenticated()` mà quên quyền cụ thể.

### Test token hợp lệ và quyền đúng

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

@Test
void readScopeCanAccessInventoryRead() {
    StepVerifier.create(
        call("inventory.read", "valid-read")
    )
    .assertNext(view -> {
        assertThat(view.sku()).isEqualTo("SKU-42");
        assertThat(view.available()).isEqualTo(12);
    })
    .verifyComplete();
}
~~~

Test này xác nhận request đã qua authentication, route authorization, payload decoding và handler.

### Test thiếu token

~~~java
@Test
void anonymousRequestCannotAccessProtectedRoute() {
    StepVerifier.create(
        call("inventory.read", null)
    )
    .expectError()
    .verify(Duration.ofSeconds(5));
}
~~~

Test token không giải mã được:

~~~java
@Test
void unknownTokenCannotAccessProtectedRoute() {
    StepVerifier.create(
        call("inventory.read", "not-in-test-token-map")
    )
    .expectError()
    .verify(Duration.ofSeconds(5));
}
~~~

RSocket không trả HTTP status 401 như REST endpoint. Lỗi bảo mật được chuyển thành lỗi của RSocket interaction; phía client thường quan sát một exception từ remote peer. Vì vậy, test nên xác nhận interaction thất bại và kiểm tra nguyên nhân ở server log/diagnostic nếu cần phân biệt authentication với authorization.

### Test token hợp lệ nhưng thiếu quyền

~~~java
@Test
void readScopeCannotAccessAdminRoute() {
    StepVerifier.create(
        call("inventory.admin", "valid-read")
    )
    .expectError()
    .verify(Duration.ofSeconds(5));
}
~~~

Token vẫn được xác thực thành công nhưng thiếu `SCOPE_inventory.admin`. Handler admin không được chạy. Nếu cần xác minh điều này, có thể dùng spy/mock cho service nghiệp vụ và xác nhận method không được gọi.

### Test quyền admin

~~~java
@Test
void adminScopeCanAccessAdminRoute() {
    StepVerifier.create(
        call("inventory.admin", "valid-admin")
    )
    .assertNext(view ->
        assertThat(view.available()).isEqualTo(12)
    )
    .verifyComplete();
}
~~~

Các test này dùng cùng một connection và thay token trên từng request. Điều đó xác nhận authorization được thực hiện theo credential gắn với request.

## Tạo test JWT có thời hạn xác định

Không dùng `Instant.now()` độc lập ở nhiều chỗ trong test hết hạn. Đồng hồ thật khiến test dễ dao động khi chạy chậm hoặc khi máy CI lệch giờ.

Dùng `Clock.fixed(...)` để kiểm soát thời điểm xác minh. `JwtTimestampValidator` cho phép đặt clock và clock skew:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class JwtExpiryTests {

    private static final Instant NOW =
        Instant.parse("2030-01-01T12:00:00Z");

    @Test
    void rejectsExpiredJwt() {
        Jwt expired = Jwt.withTokenValue("expired-token")
            .header("alg", "RS256")
            .subject("alice")
            .issuedAt(NOW.minusSeconds(300))
            .expiresAt(NOW.minusSeconds(1))
            .claim("scope", "inventory.read")
            .build();

        JwtTimestampValidator validator =
            new JwtTimestampValidator(Duration.ZERO);

        validator.setClock(Clock.fixed(NOW, ZoneOffset.UTC));

        assertThat(validator.validate(expired).hasErrors()).isTrue();
    }
}
~~~

Ở đây, token hết hạn trước thời điểm cố định một giây. Clock skew bằng zero giúp kết quả không phụ thuộc khoảng dung sai mặc định.

Có thể kiểm tra token còn hạn:

~~~java
@Test
void acceptsJwtWithinItsValidityWindow() {
    Jwt valid = Jwt.withTokenValue("valid-token")
        .header("alg", "RS256")
        .subject("alice")
        .issuedAt(NOW.minusSeconds(300))
        .expiresAt(NOW.plusSeconds(300))
        .claim("scope", "inventory.read")
        .build();

    JwtTimestampValidator validator =
        new JwtTimestampValidator(Duration.ZERO);

    validator.setClock(Clock.fixed(NOW, ZoneOffset.UTC));

    assertThat(validator.validate(valid).hasErrors()).isFalse();
}
~~~

Hai test trên kiểm tra timestamp validator. Chúng không kiểm tra chữ ký JWT vì object `Jwt` đã được tạo trực tiếp trong test. Chữ ký phải được kiểm tra ở test riêng với decoder thật và khóa test.

## Đưa kiểm tra hết hạn vào RSocket integration test

Có thể thay decoder production bằng một decoder test chuyên biệt để tập trung kiểm tra luồng RSocket authentication và authorization. Decoder test tạo JWT fixture và áp dụng timestamp validator với clock cố định.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Map;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;

import reactor.core.publisher.Mono;

@TestConfiguration
class TestJwtDecoderConfiguration {

    static final Instant NOW =
        Instant.parse("2030-01-01T12:00:00Z");

    @Bean
    @Primary
    ReactiveJwtDecoder testJwtDecoder() {
        JwtTimestampValidator timestamps =
            new JwtTimestampValidator(Duration.ZERO);

        timestamps.setClock(Clock.fixed(NOW, ZoneOffset.UTC));

        Map<String, Jwt> tokens = Map.of(
            "valid-read",
            jwt("valid-read", "alice", "inventory.read",
                NOW.plusSeconds(300)),
            "valid-admin",
            jwt("valid-admin", "admin", "inventory.admin",
                NOW.plusSeconds(300)),
            "expired-read",
            jwt("expired-read", "alice", "inventory.read",
                NOW.minusSeconds(1))
        );

        return token -> {
            Jwt jwt = tokens.get(token);

            if (jwt == null) {
                return Mono.error(new BadJwtException("Unknown test token"));
            }

            OAuth2TokenValidatorResult result = timestamps.validate(jwt);

            if (result.hasErrors()) {
                return Mono.error(new BadJwtException("JWT timestamp invalid"));
            }

            return Mono.just(jwt);
        };
    }

    private static Jwt jwt(
            String token,
            String subject,
            String scope,
            Instant expiresAt) {

        return Jwt.withTokenValue(token)
            .header("alg", "RS256")
            .subject(subject)
            .issuedAt(NOW.minusSeconds(60))
            .expiresAt(expiresAt)
            .claim("scope", scope)
            .build();
    }
}
~~~

Test configuration đã được gắn vào integration test bằng `@Import(TestJwtDecoderConfiguration.class)` ở phần khởi tạo server.

Test expired token:

~~~java
@Test
void expiredTokenCannotAccessProtectedRoute() {
    StepVerifier.create(
        call("inventory.read", "expired-read")
    )
    .expectError()
    .verify(Duration.ofSeconds(5));
}
~~~

Decoder ở ví dụ này là fixture kiểm thử: token string chỉ là khóa tra cứu JWT được tạo sẵn, và validator kiểm tra claim thời gian. Nó không xác minh chữ ký, issuer hoặc audience. Cách này cô lập việc truyền authentication metadata qua RSocket và kiểm tra quyết định từ chối token hết hạn.

Không dùng decoder giả làm bằng chứng rằng xác minh JWT production đã an toàn. Cần thêm test decoder thật ở phần tiếp theo.

## Kiểm tra chữ ký, issuer và audience bằng decoder thật

Test tích hợp với decoder thật cần dùng JWT được ký bằng private key test và decoder chỉ tin cậy public key tương ứng, hoặc dùng test Authorization Server/JWK Set. Không dùng token `alg=none` hay decoder chấp nhận mọi chữ ký.

Các trường hợp nên kiểm tra:

- Chữ ký đúng với khóa tin cậy.
- Chữ ký bị sửa hoặc ký bằng khóa không được tin cậy.
- `iss` đúng và sai.
- `aud` có và không chứa audience của RSocket service.
- `exp` còn hạn và đã hết hạn.
- `nbf` đã có hiệu lực và còn ở tương lai.
- Signing key rotation: decoder nhận khóa mới từ JWK Set theo cấu hình.

Ví dụ decoder từ issuer trong production:

~~~java
@Bean
ReactiveJwtDecoder jwtDecoder() {
    return ReactiveJwtDecoders.fromIssuerLocation(
        "https://idp.example.com/issuer"
    );
}
~~~

Nếu có yêu cầu audience, thêm `OAuth2TokenValidator<Jwt>` kiểm tra claim `aud` bên cạnh validator mặc định cho issuer và timestamp. Dùng cùng decoder production trong integration test để xác nhận chữ ký và claim thật được kiểm tra. Test fixture ở phần trước chỉ phù hợp cho test RSocket security flow.

## Kiểm tra clock skew và thời điểm hết hạn

Các máy trong hệ thống phân tán có thể lệch đồng hồ. Spring Security dùng `JwtTimestampValidator` để kiểm tra `exp` và `nbf`, đồng thời hỗ trợ clock skew.

Ví dụ cấu hình dung sai 30 giây:

~~~java
JwtTimestampValidator timestamps =
    new JwtTimestampValidator(Duration.ofSeconds(30));
~~~

Nếu clock skew được bật, token vừa qua thời điểm `exp` trong khoảng dung sai có thể vẫn được chấp nhận. Vì vậy, test nên bao gồm:

| Thời điểm của JWT so với clock | Clock skew | Kết quả mong đợi |
|---|---:|---|
| Còn hạn 60 giây | 0 giây | Hợp lệ |
| Hết hạn 1 giây | 0 giây | Không hợp lệ |
| Hết hạn 10 giây | 30 giây | Có thể vẫn được chấp nhận trong dung sai |
| Hết hạn 31 giây | 30 giây | Không hợp lệ |
| `nbf` ở tương lai 1 giây | 0 giây | Chưa hợp lệ |
| `nbf` ở tương lai 31 giây | 30 giây | Chưa hợp lệ |

Giá trị clock skew cần phản ánh độ lệch đồng hồ thực tế của hạ tầng. Không tăng dung sai chỉ để test pass hoặc để che lỗi đồng bộ thời gian.

## Test authentication tại SETUP và request time

Hai mô hình cần bộ test riêng.

### SETUP authentication

Kiểm tra:

1. Client không có credential bị từ chối ngay khi mở connection nếu policy yêu cầu SETUP authority.
2. Credential SETUP hợp lệ tạo được session.
3. Credential SETUP thiếu authority không được phép mở session.
4. Token hết hạn trước SETUP bị từ chối.
5. Khi token hết hạn sau khi session đã mở, hành vi phải khớp chính sách tuổi session và tái xác thực của ứng dụng.

### Request-time authentication

Kiểm tra:

1. Có thể mở connection nếu policy cho phép SETUP không xác thực.
2. Request không có token bị từ chối.
3. Request có token hợp lệ được xử lý.
4. Token thiếu authority bị từ chối theo route.
5. Token hết hạn bị từ chối dù connection vẫn mở.
6. Token mới có thể được dùng trên request tiếp theo nếu client đã refresh token.
7. Hai người dùng với quyền khác nhau trên cùng connection vẫn nhận quyết định authorization riêng.

Đối với connection dùng chung, test request-time authentication đặc biệt quan trọng. Không giả định danh tính của người đầu tiên mở connection sẽ phù hợp với tất cả người dùng sử dụng connection đó.

## Kiểm thử token refresh

Giả sử frontend hoặc service lấy access token mới sau khi token cũ hết hạn. Client nên gửi token mới ở request tiếp theo:

~~~java
Mono<InventoryView> readWithToken(
        RSocketRequester requester,
        String token) {

    return requester
        .route("inventory.read")
        .metadata(new BearerTokenMetadata(token), AUTHENTICATION_MIME)
        .data(new InventoryQuery("SKU-42"))
        .retrieveMono(InventoryView.class);
}
~~~

Một test refresh có thể mô phỏng:

1. Gửi request với token còn hạn và nhận thành công.
2. Gửi request với token đã hết hạn và xác nhận bị từ chối.
3. Thay token bằng token mới còn hạn.
4. Gửi lại request trên connection đang mở và xác nhận thành công.

Không retry mù quáng một request nghiệp vụ chỉ vì token hết hạn. Hãy refresh credential rồi gửi lại theo chính sách idempotency của thao tác; nếu server có thể đã commit trước khi response bị mất, phải dùng command ID hoặc idempotency key.

## Phân biệt lỗi authentication và authorization trong test

Hai lỗi có thể cùng xuất hiện dưới dạng RSocket remote error ở client, nhưng nguyên nhân khác nhau:

| Tình huống | Thành phần từ chối | Cách chẩn đoán |
|---|---|---|
| Không có token | Authentication | Kiểm tra metadata và policy authenticated |
| Token sai chữ ký | JWT decoder | Kiểm tra key, algorithm và decoder |
| Token hết hạn | Timestamp validator | Kiểm tra `exp`, clock và skew |
| Sai issuer/audience | JWT claim validator | Kiểm tra `iss`, `aud` và cấu hình service |
| Token hợp lệ nhưng thiếu scope | Authorization | Kiểm tra authority mapping và route rule |
| Token đủ scope nhưng route sai | Route mapping hoặc authorization matcher | Kiểm tra route metadata và thứ tự rule |

Không nên kiểm tra duy nhất chuỗi thông báo exception ở client vì cách đóng gói lỗi có thể thay đổi theo phiên bản và transport. Dùng assertion thành công/thất bại ở client, đồng thời kiểm tra decoder, security event hoặc log phía server để xác nhận đúng nguyên nhân.

## Những lỗi cấu hình thường gặp

### Dùng `permitAll()` trước route cần bảo vệ

Authorization rules được đánh giá theo thứ tự. Một matcher tổng quát đặt trước có thể khớp trước route cụ thể. Đặt route nhạy cảm lên trước và kiểm tra cả route không có rule riêng.

### Chỉ kiểm tra authenticated mà quên authority

`authenticated()` chỉ yêu cầu danh tính đã được xác thực. Nó không đảm bảo user có scope hoặc role cần thiết. Dùng `hasAuthority`, `hasRole` hoặc custom authorization phù hợp.

### Dùng nhầm MIME type

Bearer token phải dùng RSocket Authentication Metadata Extension:

```text
message/x.rsocket.authentication.v0
```

Dùng MIME type chuẩn từ `WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION`. Không dùng hằng `BearerTokenMetadata.BEARER_AUTHENTICATION_MIME_TYPE` đã deprecated.

### Token hết hạn nhưng connection vẫn dùng được

Nếu chỉ xác thực ở SETUP, request tiếp theo có thể tiếp tục dùng identity đã thiết lập theo session policy. Nếu yêu cầu kiểm tra expiry mỗi lần gọi, gửi token trong request metadata và test trên cùng connection.

### Test chỉ dùng decoder giả

Decoder giả giúp kiểm tra route và security interceptor nhưng không xác minh chữ ký JWT, issuer, audience hoặc JWK rotation. Bổ sung test với decoder thật và khóa test.

### Dùng đồng hồ thật trong test expiry

Test có thể chập chờn khi chạy chậm hoặc clock lệch. Dùng `Clock.fixed` và đặt clock skew rõ ràng.

### Nhầm lỗi RSocket với HTTP 401/403

RSocket TCP không có HTTP status code. Client nhận lỗi interaction/protocol; không viết assertion dựa trên status HTTP cho test TCP. Với WebSocket, HTTP status chỉ áp dụng ở handshake, không thay thế lỗi authorization sau khi RSocket session đã được thiết lập.

## Checklist kiểm thử trước production

1. Request không có token bị từ chối ở route cần bảo vệ?
2. Token sai định dạng hoặc không giải mã được bị từ chối?
3. Chữ ký, issuer và audience được xác minh bằng decoder thật?
4. Token hết hạn và token chưa tới `nbf` bị từ chối?
5. Clock skew được test với clock cố định?
6. Token hợp lệ nhưng thiếu scope bị từ chối?
7. Token có đúng scope được phép gọi route tương ứng?
8. Route admin không bị matcher tổng quát cho phép?
9. Handler nghiệp vụ không chạy khi authentication hoặc authorization thất bại?
10. SETUP auth và request-time auth được test riêng?
11. Token refresh được kiểm tra trên connection đang mở?
12. Lỗi ở client được đối chiếu với nguyên nhân tại server?
13. Integration test chạy qua transport RSocket thật và không chỉ gọi method handler?
14. Test decoder giả được tách biệt khỏi test chữ ký và claim production?

Kiểm thử bảo mật RSocket phải xác nhận token được xác thực, route được phân quyền và thời hạn JWT được kiểm tra theo đúng phạm vi connection hoặc request. Dùng integration test với RSocketRequester để kiểm tra luồng thực, StepVerifier để xác nhận kết quả reactive và Clock cố định để test expiry ổn định. Kết hợp decoder giả cho test luồng bảo mật với decoder thật cho chữ ký và claims giúp phát hiện cả lỗi cấu hình RSocket lẫn lỗi xác minh JWT.

## Tài liệu tham khảo

- [Spring Security Reference: RSocket Security](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html)
- [Spring Security API: RSocketSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/rsocket/RSocketSecurity.html)
- [Spring Security Reference: OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security API: JwtTimestampValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtTimestampValidator.html)
- [Spring Framework Reference: RSocketRequester](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Boot API: LocalRSocketServerPort](https://docs.spring.io/spring-boot/docs/3.2.11/api/org/springframework/boot/test/rsocket/server/LocalRSocketServerPort.html)
- [Spring Boot Reference: Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot RSocket security integration test example](https://github.com/spring-projects/spring-boot/blob/main/spring-boot-tests/spring-boot-smoke-tests/spring-boot-smoke-test-rsocket/src/test/java/smoketest/rsocket/SampleRSocketApplicationTests.java)

