# Đánh giá chi phí băm mật khẩu, xác minh JWT và introspection trong Spring Security WebFlux

> **Mạch học:** Spring Security - reactive → Quan sát và hiệu năng. Mục tiêu là đo đúng chi phí của ba cơ chế xác thực thường gặp, xác định chúng ảnh hưởng thế nào đến độ trễ và thông lượng của ứng dụng WebFlux, rồi tối ưu có kiểm soát mà vẫn giữ nguyên các thuộc tính bảo mật.

## 1. Ba cơ chế, ba loại chi phí

Trong một hệ thống dùng OAuth2 Resource Server hoặc đăng nhập bằng mật khẩu, không thể lấy cùng một con số “thời gian xác thực” để so sánh mọi yêu cầu: cơ chế thực thi, tần suất và vị trí tiêu thụ tài nguyên khác nhau.

| Cơ chế | Thực hiện khi nào? | Chi phí nổi bật | Phần có thể phát sinh I/O | Điều tuyệt đối không đánh đổi |
| --- | --- | --- | --- | --- |
| Băm/xác minh mật khẩu bằng BCrypt, Argon2id, PBKDF2 | Thường ở login, đăng ký, đổi mật khẩu; **không** cần chạy lại cho mọi request đã dùng access token | CPU; riêng Argon2 còn có chi phí bộ nhớ rõ rệt; worker/scheduler queue | Tải bản ghi người dùng từ DB | Không hạ cost đến mức yếu chỉ để đạt RPS; không đưa hash lên event loop |
| JWT access token (JWS) | Thường ở mỗi request được xác thực, nếu không có tầng reuse kết quả | Parse/kiểm tra claims, xác minh chữ ký RSA/ECDSA/thuật toán được phép; chi phí CPU nhỏ nhưng có thể đáng kể ở RPS lớn | Lấy JWKS khi khởi tạo, cache miss hoặc xoay khóa | Không bỏ kiểm tra chữ ký/issuer/audience/thời gian; không chấp nhận thuật toán do token tự quyết |
| Opaque token introspection (RFC 7662) | Resource Server hỏi Authorization Server để biết token còn hoạt động và quyền liên quan | HTTP/TLS, mạng, connection pool, độ trễ và khả năng chịu tải của IdP | **Thông thường mỗi lần introspect là một lệnh gọi HTTP**, trừ khi có cache/chính sách khác | Không biến lỗi IdP thành “allow”; giới hạn cache theo yêu cầu thu hồi token |

**Không kết luận “JWT luôn nhanh hơn introspection” một cách tuyệt đối:** JWT thường tránh round-trip mạng cho mỗi request khi JWKS đã có trong cache, nhưng phép so sánh phụ thuộc cách triển khai, token format, loại khóa, thuật toán, độ phức tạp claims, network, cache và chính sách revocation. JWT không tự đáp ứng thu hồi ngay lập tức; introspection thường cập nhật trạng thái token tốt hơn theo thời điểm hỏi, nhưng tăng phụ thuộc mạng.

Một request có thể gồm nhiều chi phí:

~~~text
Client → Netty/WebFlux
       → SecurityWebFilterChain
         ├─ Bearer JWT: parse → lấy key đã cache / fetch JWKS → verify signature
         │              → validate issuer, audience, exp, nbf → SecurityContext
         ├─ Opaque token: HTTP introspection → active + authorities → SecurityContext
         └─ Username/password login: tra user → passwordEncoder.matches(...)
                                            → tạo phiên/token
       → Controller → Service → R2DBC/WebClient → Response
~~~

JWT và opaque token ở sơ đồ là **hai đường xác thực access token thay thế theo cấu hình**, không mặc định chạy cả hai trên một request. Password hashing thường thuộc luồng login riêng. Cần phân biệt đo **chi phí thành phần** với **latency end-to-end** mà người dùng cảm nhận.

## 2. Định nghĩa chỉ số và thiết kế phép đo

### 2.1 Chỉ số bắt buộc

1. **Latency:** p50, p95, p99 (ms) theo request và riêng từng operation; tách success/failure, cold/warm và timeout.
2. **Thông lượng:** request/s (RPS), login/s, lần verify JWT/s, introspection/s ở mức tải ổn định; ghi đồng thời concurrency và số client ảo.
3. **Tài nguyên:** CPU % và CPU-time, heap, off-heap/direct memory, GC pause, allocation, số thread, queue/rejections của scheduler chạy password hash.
4. **Network/IdP:** connection reuse, connection pending, DNS/TLS handshake, server response time, timeout, HTTP 429/5xx, cache hit/miss của key/JWKS.
5. **Sức khỏe reactive:** Netty event-loop bị block hay không, thời gian chờ worker, pending requests, lỗi timeout/cancel; kiểm tra thread dump/JFR/BlockHound trong môi trường thử nghiệm.
6. **Tính đúng đắn:** token sai chữ ký, sai issuer/audience, hết hạn; password sai; introspection active=false phải bị từ chối đúng chính sách ngay cả dưới tải.

**Định nghĩa latency:** bao gồm thời gian queue khi đo từ request HTTP đến response. Đo riêng “thời gian thực thi hàm hash” có thể cho 80 ms trong khi p99 HTTP lên vài giây vì hàng đợi. Chỉ số trung bình che đuôi latency. p95 của các tầng **không thể cộng trực tiếp** để suy ra p95 tổng request; phải đo end-to-end.

### 2.2 Ba nhóm kịch bản cần tách

- **Baseline:** cùng một máy/phiên bản JDK, cùng kích cỡ khóa/hash cost, không có request đồng thời, warm-up thích hợp; nhằm hiểu thời gian một operation.
- **Steady load:** tăng tải từng bậc, cố định đủ lâu để CPU, pool và queue ổn định, quan sát điểm p95/p99 tăng dốc hoặc timeout bắt đầu xuất hiện.
- **Stress/failure:** IdP chậm/429/5xx, cache JWKS miss, key rotation, scheduler hash bị đầy, connection pool cạn, token sai nhiều, spike login; kiểm tra fail-closed và khả năng phục hồi.

Ghi lại JDK, phiên bản Spring Security, CPU/cores và giới hạn container, memory, thuật toán/hash cost, RSA/ECDSA key length, mạng đến IdP, pool, timeout, tỷ lệ token hợp lệ/không hợp lệ, chiều dài token, cache và phân phối request. So sánh phải dùng cùng dữ liệu thử nghiệm. Không dùng token thật hoặc mật khẩu thật cho benchmark.

### 2.3 Một công thức để giải thích hàng đợi

Ở trạng thái ổn định, Little’s law cho xấp xỉ **L = λ × W** (số công việc đang ở hệ thống ≈ thông lượng × thời gian lưu trong hệ thống). Ví dụ introspection trung bình mất 0,08 giây và có 250 request/s thì trung bình khoảng **20 lời gọi đồng thời** đang chờ hoàn tất, nếu từng request cần một introspection và bỏ qua các bước khác. Nếu hệ thống có giới hạn concurrent thấp hơn nhu cầu hoặc network/IdP chậm thêm, request sẽ dồn queue. Con số này là để lập giả thuyết đo, không phải kích thước pool mặc định nên áp dụng.

## 3. Password hashing: cố ý tốn tài nguyên, nhưng không làm nghẽn event loop

BCrypt, Argon2id và PBKDF2 là các thuật toán password hashing/KDF với **tham số chi phí**; hàm này có mục tiêu làm tấn công thử mật khẩu hàng loạt đắt đỏ. BCrypt có work factor; Argon2id có memory/time/parallelism; PBKDF2 có iteration count. Các tham số không cùng đơn vị và không thể so sánh chỉ bằng một số “cost 12” hoặc “100000 iterations”. Cần chọn thuật toán và tham số theo chính sách bảo mật hiện hành, đo trên hạ tầng production-like, lập kế hoạch tăng cost khi phần cứng thay đổi.

Cần đo **encode** (đăng ký/đổi mật khẩu) và **matches** (đăng nhập). Phần lớn login hiện hữu đo matches; lookup user từ DB phải tách riêng để phân biệt CPU hashing với I/O. Trường hợp user không tồn tại có thể dùng dummy hash cùng mức cost nhằm giảm chênh lệch thời gian và chống dò tài khoản, đồng thời cần rate limit chống lạm dụng. Không log mật khẩu thô, không đưa mật khẩu/hash vào metric tags.

### 3.1 Mẫu xử lý đúng trong WebFlux

~~~java
package example.security;

import jakarta.annotation.PreDestroy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration
class PasswordConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        // Giá trị 12 chỉ là một cấu hình tham khảo, phải benchmark và rà soát chính sách.
        return new BCryptPasswordEncoder(12);
    }
}

@Service
public class ReactivePasswordVerifier {
    private final PasswordEncoder encoder;
    private final Scheduler worker =
            Schedulers.newBoundedElastic(8, 200, "password-hash");

    public ReactivePasswordVerifier(PasswordEncoder encoder) {
        this.encoder = encoder;
    }

    public Mono<Boolean> matches(String rawPassword, String storedHash) {
        return Mono.fromCallable(() -> encoder.matches(rawPassword, storedHash))
                .subscribeOn(worker);
    }

    @PreDestroy
    public void close() {
        worker.dispose();
    }
}
~~~

Ở đây **Mono.fromCallable** hoãn việc tính hash đến lúc subscribe; **subscribeOn(worker)** chuyển công việc CPU-bound đồng bộ ra khỏi event-loop. Bounded scheduler đặt giới hạn số worker và tác vụ đợi, nhưng **không thay thế rate limit/concurrency limit ở cửa vào**. Khi queue đầy hoặc bị reject, hệ thống phải có cách trả lỗi/throttle có kiểm soát; không chuyển ngược phép hash lên Netty thread. Một scheduler riêng để đo giúp tách backlog của hash khỏi công việc blocking khác; cấu hình 8/200 chỉ để minh họa, phải dựa vào CPU/memory budget và benchmark.

**Sai:**

~~~java
// Ví dụ phản diện: phép matches() chạy đồng bộ ngay trong đường xử lý reactive.
// Không sao chép vào handler production.
public Mono<Boolean> unsafe(String raw, String hash, PasswordEncoder encoder) {
    return Mono.just(encoder.matches(raw, hash));
}
~~~

**Cũng sai:** tự gọi **subscribe()** trong handler rồi trả response trước khi hash hoàn tất; dùng **block()** trên event loop; chạy Argon2 nhiều instance đồng thời đến mức hết memory; cố giảm work factor khi hệ thống cần thêm thông lượng mà không cân nhắc hậu quả bảo mật.

### 3.2 Đo và diễn giải

Thực hiện bài đo với ít nhất hai cost được tổ chức cho môi trường thử nghiệm, chẳng hạn BCrypt cost 10 và cost 12, trên phần cứng mục tiêu; dùng mật khẩu và salt ngẫu nhiên của fixture, bảo đảm cả hai lệnh hash tương ứng với stored hash đã tạo. Kết quả minh họa có thể cho thấy cost tăng làm CPU time tăng mạnh; **không đặt kỳ vọng ms cố định** vì CPU, JVM warm-up, giới hạn container và tải nền thay đổi. Ngoài p95 của matches, phải đo **login/s, CPU%, queue wait, rejection, heap/RSS**. Với Argon2id, đo RSS/direct/native memory trong tải đồng thời; heap usage một mình không phản ánh tất cả áp lực bộ nhớ.

## 4. Xác minh JWT: CPU local, phụ thuộc JWKS ở đường lạnh

Với signed JWT/JWS, Resource Server phải giải mã cấu trúc có giới hạn hợp lý, chọn key từ tập key tin cậy, xác minh chữ ký đúng thuật toán được cho phép, kiểm tra issuer, audience, exp, nbf và các claims/policy ứng dụng. Chỉ Base64-decoding payload hoặc đọc claim là **không đủ để xác thực token**. Một token có chữ ký hợp lệ vẫn có thể không hợp lệ với API này do sai issuer/audience, hết hạn hoặc thiếu scope.

Phân tách phép đo:

1. **Warm verification:** đã có JWK/key trong cache, cùng thuật toán, xác minh chữ ký + validation claims.
2. **Cold start/cache miss:** discovery/JWKS retrieval, DNS/TLS/network, parse JWK và verify; có thể phát sinh spike.
3. **Key rotation:** token có **kid** mới trong JWK set được cập nhật, token cũ còn hợp lệ trong chuyển tiếp; bảo đảm không fetch vô hạn khi attacker gửi kid ngẫu nhiên.
4. **Token từ chối:** bad signature, alg không được phép, wrong issuer/audience, expired; lưu ý lối exit sớm có latency khác nên không trộn tỷ lệ failure một cách mù quáng.
5. **Kích thước token và số claim:** đo thêm parse time, headers size và mạng; càng nhiều claims không đồng nghĩa công việc mã hóa tăng tuyến tính đơn giản.

Ví dụ cấu hình **Resource Server JWT** cho Spring Boot WebFlux:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/realms/demo
~~~

Ở chế độ JWT, Spring Security sẽ xác minh token thông qua một **ReactiveJwtDecoder** phù hợp; issuer URI có thể cần metadata/discovery để tìm JWKS. Với yêu cầu **audience**, phải cấu hình validator/policy của API tương ứng; đừng mặc định chỉ có chữ ký đúng là đủ. Ví dụ khi chủ động dựng decoder:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
public class JwtDecoderConfig {
    private static final String ISSUER = "https://issuer.example.test/realms/demo";
    private static final String JWKS_URI = ISSUER + "/protocol/openid-connect/certs";
    private static final String EXPECTED_AUDIENCE = "notes-api";

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder.withJwkSetUri(JWKS_URI).build();

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(EXPECTED_AUDIENCE)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error("invalid_token",
                                        "Token has the wrong audience", null));

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER), audience));
        return decoder;
    }
}
~~~

Đoạn cấu hình minh họa cho một JWK endpoint do IdP quản lý và một audience cố định. URI và thuật toán được phép phải theo IdP thực tế; không tải JWK từ URL do token tự cung cấp. Nếu đã có **issuer-uri** auto-configuration, không copy thêm bean decoder tùy ý khi không có nhu cầu; bean tự định nghĩa có thể thay đường cấu hình tự động. Kích hoạt HTTP security/oauth2ResourceServer như đường bảo mật ứng dụng quy định.

**Lưu ý đo:** chỉ dùng cùng một token hợp lệ trong test throughput đo verify local; khi kiểm hiệu năng JWKS cache hoặc rotation phải kiểm soát key set/ID của token rõ ràng. Không cache “JWT đã verify = được phép mọi lần” vô thời hạn vì exp, thay đổi quyền, blacklist và revocation có thể yêu cầu thời hạn/chính sách khác.

## 5. Opaque-token introspection: latency, pool và độ sẵn sàng của IdP

Resource Server gửi opaque token tới endpoint introspection của Authorization Server bằng credential kênh server-to-server theo RFC 7662; kết quả thường gồm **active**, sub, scope, exp và các thông tin được phép cung cấp. Introspection có thể có chi phí network + TLS, hàng đợi tại IdP, database/cache của IdP và xử lý response. Đo thực tế phụ thuộc khoảng cách vùng, connection reuse, DNS, pool và chính sách IdP.

Ví dụ cấu hình **opaque-token Resource Server**, dùng độc lập với lựa chọn JWT ở mục trước:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://issuer.example.test/oauth2/introspect
          client-id: resource-server
          client-secret: YOUR_SECRET_FROM_SECRET_MANAGER
~~~

Đây là cấu trúc minh họa; đưa secret qua secret manager/biến môi trường, không commit chuỗi bí mật trong file. Trong WebFlux, dùng **ReactiveOpaqueTokenIntrospector**/client HTTP reactive được cấu hình đúng, tái sử dụng connection pool và đặt connect/response/read timeout phù hợp; không gọi **RestTemplate**, blocking **HttpClient.send()** hay **block()** trên Netty event-loop.

### 5.1 Các kịch bản nhất thiết phải thử

| Tình huống | Quan sát kỳ vọng |
| --- | --- |
| Token active=true và endpoint IdP khỏe | API cấp quyền theo scope/claims thực trả về; ghi latency, RPS và pool |
| Token active=false/expired | API từ chối dù endpoint trả HTTP 200; không lấy active=false thành success |
| IdP chậm hơn timeout | Resource Server **fail closed**, không tự cho qua; ghi timeout và tỷ lệ HTTP lỗi phù hợp |
| IdP HTTP 429/5xx hoặc mất mạng | Không cho qua; lỗi phụ thuộc dịch vụ được ghi nhận riêng với invalid token khi có thể |
| Không reuse connection | Latency tăng vì kết nối/TLS; đo pool hit và connect time |
| Introspection có cache TTL | Kiểm tra hạn token, stale permission, revoke; có bài test token bị revoke ngay sau lần cache |
| Burst nhiều token độc lập | Connection pending, số request tới IdP, trạng thái 429/rate limit, queue/timeout |

**Cache introspection là quyết định bảo mật:** cache có thể giảm round-trip nhưng trì hoãn hiệu lực revoke/đổi quyền. TTL phải hữu hạn, không vượt exp, cân đối với SLA thu hồi quyền; một số chính sách không cho cache. Nếu cache key dựa trên token, không log raw token; coi token như credential. Dùng HTTPS và client authentication; tuyệt đối không introspect bằng request gửi token tới URL do client chỉ định.

**Hành vi khi IdP lỗi:** có thể trả 503 cho dependency unavailable tùy architecture, nhưng không chuyển sang anonymous/allow-all hoặc lấy quyền từ cache đã quá hạn. Nếu HTTP lỗi chính xác bị framework chuyển thành 401, phân biệt qua internal metrics/tracing để đội vận hành biết đây là lỗi IdP chứ không phải người dùng gõ sai credential.

## 6. Bài thực hành Java 17 độc lập: tách ba đặc tính chi phí

Phần này là **bài đo nhỏ chạy được bằng JDK 17+**, không cần IdP thật hoặc dịch vụ production. Nó tách:

- **PBKDF2WithHmacSHA256** tiêu thụ CPU và đại diện cho nhóm password KDF; đây **không phải** con số thay thế cho BCrypt/Argon2 production.
- **SHA256withRSA (RS256) Signature.verify** với key đã có sẵn; chỉ đo phần cryptographic signature của một JWS fixture, **chưa** xác minh JWT claims, alg allowlist, JWK trust hay thời hạn.
- **HTTP introspection mock** trên 127.0.0.1 với độ trễ server cố ý; minh họa network+remote response. Mock luôn trả active=true, không triển khai OAuth2 introspection, TLS hoặc client authentication.

Lưu tệp dưới tên **SecurityCostExercise.java** (tên tệp trùng public class):

~~~java
import com.sun.net.httpserver.HttpServer;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.security.Signature;
import java.time.Duration;
import java.util.Arrays;
import java.util.Base64;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class SecurityCostExercise {
    @FunctionalInterface
    interface CheckedOperation {
        void run() throws Exception;
    }

    static byte[] derive(char[] password, byte[] salt)
            throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(password, salt, 120_000, 256);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    static void sample(String label, int warmup, int count, CheckedOperation op)
            throws Exception {
        for (int i = 0; i < warmup; i++) {
            op.run();
        }
        long[] durationNs = new long[count];
        for (int i = 0; i < count; i++) {
            long start = System.nanoTime();
            op.run();
            durationNs[i] = System.nanoTime() - start;
        }
        Arrays.sort(durationNs);
        int p50 = (int) Math.ceil(count * 0.50) - 1;
        int p95 = (int) Math.ceil(count * 0.95) - 1;
        System.out.printf(Locale.ROOT,
                "%s: n=%d, p50=%.3f ms, p95=%.3f ms%n",
                label, count, durationNs[p50] / 1_000_000.0,
                durationNs[p95] / 1_000_000.0);
    }

    static String urlPart(String input) {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(input.getBytes(StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        char[] password = "training-password-only".toCharArray();
        byte[] salt = new byte[16];
        new SecureRandom().nextBytes(salt);
        byte[] expected = derive(password, salt);

        sample("PBKDF2 verify", 3, 16, () -> {
            byte[] actual = derive(password, salt);
            if (!MessageDigest.isEqual(expected, actual)) {
                throw new IllegalStateException("Wrong password fixture");
            }
        });

        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair keys = generator.generateKeyPair();

        String jwsInput = urlPart("{\"alg\":\"RS256\",\"typ\":\"JWT\"}")
                + "."
                + urlPart("{\"iss\":\"https://issuer.test\",\"sub\":\"alice\","
                          + "\"aud\":\"notes-api\",\"exp\":1893456000}");
        byte[] message = jwsInput.getBytes(StandardCharsets.US_ASCII);
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(keys.getPrivate());
        signer.update(message);
        byte[] signed = signer.sign();

        sample("RS256 signature only", 100, 1000, () -> {
            Signature verifier = Signature.getInstance("SHA256withRSA");
            verifier.initVerify(keys.getPublic());
            verifier.update(message);
            if (!verifier.verify(signed)) {
                throw new IllegalStateException("Bad JWT signature fixture");
            }
        });

        ExecutorService pool = Executors.newFixedThreadPool(2);
        HttpServer mock = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        mock.setExecutor(pool);
        mock.createContext("/introspect", exchange -> {
            try {
                if (!"POST".equals(exchange.getRequestMethod())) {
                    exchange.sendResponseHeaders(405, -1);
                    return;
                }
                try {
                    Thread.sleep(25); // Chỉ nằm trong mock server của CLI demo.
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
                byte[] data = "{\"active\":true,\"sub\":\"alice\"}"
                        .getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type", "application/json");
                exchange.sendResponseHeaders(200, data.length);
                try (var output = exchange.getResponseBody()) {
                    output.write(data);
                }
            } finally {
                exchange.close();
            }
        });
        mock.start();

        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(1))
                    .build();
            URI uri = URI.create(
                    "http://127.0.0.1:" + mock.getAddress().getPort()
                    + "/introspect");
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(2))
                    .header("Content-Type",
                            "application/x-www-form-urlencoded")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            "token=demo-opaque-token"))
                    .build();

            sample("Mock introspection HTTP", 5, 25, () -> {
                // Blocking send() chỉ dùng trong CLI để tạo baseline;
                // production WebFlux phải dùng client reactive.
                HttpResponse<String> response = client.send(
                        request, HttpResponse.BodyHandlers.ofString());
                if (response.statusCode() != 200
                        || !response.body().contains("\"active\":true")) {
                    throw new IllegalStateException(
                            "Mock introspection response invalid");
                }
            });
        } finally {
            mock.stop(0);
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy khi có JDK 17+:

~~~bash
javac --add-modules jdk.httpserver SecurityCostExercise.java
java --add-modules jdk.httpserver SecurityCostExercise
~~~

Dạng output (các giá trị millisecond **thay đổi theo máy và lượt chạy**, không đưa số giả làm số đo):

~~~text
PBKDF2 verify: n=16, p50=<measured ms>, p95=<measured ms>
RS256 signature only: n=1000, p50=<measured ms>, p95=<measured ms>
Mock introspection HTTP: n=25, p50=<measured ms>, p95=<measured ms>
~~~

Với fixture, thường thấy JWT signature warm có thời gian nhỏ hơn password KDF, trong khi introspection mock bị chi phối bởi sleep 25ms cộng network local. Đây là kết quả **định tính phải được kiểm chứng trên máy chạy**, không bảo đảm thứ hạng trong mọi thuật toán và môi trường. Phép đo nhỏ dùng System.nanoTime chỉ thích hợp làm lab/quan sát ban đầu; 16 hoặc 25 mẫu không đủ để ước lượng p99 production đáng tin, và chạy tuần tự không cho biết saturation ở concurrency cao.

### 6.1 Từ lab tới benchmark đáng tin

Để benchmark primitives, nên dùng **JMH** với warm-up/forks, Blackhole hoặc kiểm tra kết quả, thông số đầu vào có kiểm soát; tránh JIT dead-code elimination và phân biệt setup key/hash với thao tác cần đo. Để benchmark WebFlux end-to-end, dùng công cụ phát tải như k6/Gatling/wrk ở môi trường cô lập với token fixture. Không dùng JMH thay cho thử nghiệm network và connection pool; không dùng một lần đo trực tiếp bằng System.nanoTime để ra quyết định chính sách mật khẩu.

## 7. Gắn metrics đúng điểm, tránh làm sai dữ liệu đo

Micrometer có thể đo riêng thời gian mỗi operation bằng **Timer.Sample** từ lúc subscribe đến khi terminal signal; ở WebFlux phải đo thao tác reactive, tránh bọc một Mono đã được subscribe ở nơi khác.

Ví dụ helper (dùng trong project có Micrometer, Spring Boot Actuator/Reactor):

~~~java
package example.security;

import java.util.function.Supplier;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import reactor.core.publisher.Mono;

public final class AuthenticationTimers {
    private final MeterRegistry registry;

    public AuthenticationTimers(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> Mono<T> measure(
            String operation, Supplier<Mono<T>> work) {
        return Mono.defer(() -> {
            Timer.Sample sample = Timer.start(registry);
            return Mono.defer(work).doFinally(signal ->
                    sample.stop(Timer.builder("security.auth.operation")
                            .tag("operation", operation)
                            .tag("signal", signal.name())
                            .register(registry)));
        });
    }
}
~~~

Cách gọi tại điểm đang có sẵn nghiệp vụ (minh họa, không ghép thành một controller độc lập):

~~~java
// Mỗi operation chỉ được thực thi một lần trong pipeline thật.
Mono<Boolean> matching = timers.measure(
        "password_matches",
        () -> passwordVerifier.matches(rawPassword, storedHash));

Mono<org.springframework.security.oauth2.jwt.Jwt> validatedJwt =
        timers.measure("jwt_decode", () -> jwtDecoder.decode(bearerToken));

Mono<org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal> principal =
        timers.measure("introspection",
                () -> introspector.introspect(opaqueToken));
~~~

Các biến **timers, passwordVerifier, jwtDecoder, introspector, rawPassword, storedHash, bearerToken, opaqueToken** là dependency/input đã có trong ứng dụng; snippet thứ hai chỉ minh họa cách bọc pipeline, không phải chương trình chạy độc lập. Không tự decode/introspect **thêm một lần** chỉ để đo metric, vì như vậy tăng chi phí và có thể đổi ý nghĩa bảo mật. Tên operation là một tập **hằng số nhỏ**, signal có giá trị hữu hạn. Tránh gắn JWT/raw token, username, userId, tenantId, URL có ID hoặc message ngoại lệ tự do vào label: cardinality cao và có nguy cơ lộ credential. Span tracing có thể ghi issuer/provider đã chuẩn hóa, nhưng không ghi token.

Cần đặt thêm metrics tại **HTTP layer** và tại **đường ra IdP** để phân biệt chậm trong pool chờ, chậm network và chậm sau authentication. Với password hash, riêng Timer của matches không ghi được queue wait nếu timer bắt đầu sau khi worker nhận task; helper bọc publisher như trên tính từ subscribe, hữu ích để quan sát queue. Có thể bổ sung JFR/thread dump/profiler để xác nhận nguồn CPU/blocked event loop.

## 8. Kế hoạch thử tải so sánh công bằng

Dùng cùng máy/chế độ JVM, dữ liệu fixture và profile tải; chạy riêng:

**Bài A – Password login.** Seed tài khoản demo với hash được tạo sẵn ở từng cost. Thử 1, 2, 4, 8, 16 login đồng thời (điều chỉnh theo tài nguyên), đo login/s, p95/p99, CPU/RSS, worker active/queued/rejected. Không dùng password encode mỗi request khi flow thật chỉ matches; không đánh đồng DB lookup với hash nếu chưa đo riêng. Thử login sai và account không tồn tại để đánh giá password enumeration, cost và rate limiting.

**Bài B – JWT resource server.** Gửi request API nhẹ nhất có bảo vệ auth với signed JWT đúng issuer/audience. Đo token RS256 warm key ở các mức RPS, sau đó cold start/JWKS miss/key rotation và JWT sai chữ ký/expired/audience. Để kiểm tra cost của riêng security, đối chiếu cùng route kiểm thử không có backend DB nặng nhưng **không triển khai bypass security ở production**. Giữ payload/response như nhau và đọc CPU/netty metrics.

**Bài C – Opaque introspection.** Dùng IdP thử nghiệm hoặc mock HTTP có điều chỉnh latency 10/50/100ms, timeout, trả 429/5xx; đo RPS, timeouts, connection pool, p95/p99 end-to-end, IdP requests/s và CPU của resource server. Thử cache off/on chỉ khi policy cho phép, rồi revoke một token đã cache và đo độ trễ hết hiệu lực quyền. Mô phỏng outage phải kiểm tra **không cấp quyền trái phép**.

**Bài D – Hỗn hợp.** Phối hợp tỷ lệ thực (chẳng hạn JWT 95%, login 5%; tỷ lệ chỉ là fixture, không phải quy luật) và burst login. Vì hashing có chi phí CPU lớn và JWT/IdP tranh chấp tài nguyên, cần xem login spike ảnh hưởng p99 request thường như thế nào. Trong hệ thống nhiều node, đo cả từng instance và giới hạn chung của IdP.

Thu kết quả vào một bảng có cùng đơn vị:

| Test/run | Mode/params | RPS | Concurrent | HTTP p50/p95/p99 ms | Op p95 ms | CPU / RSS | Failure / timeout | Ghi chú |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1 | BCrypt cost đã chọn | đo | đo | đo | hash matches | đo | đo | Scheduler queue |
| B1 | JWT RS256, warm JWKS | đo | đo | đo | jwt decode | đo | đo | Key cache |
| B2 | JWT RS256, cold/rotation | đo | đo | đo | jwt decode | đo | đo | JWKS fetch |
| C1 | Introspection cache off | đo | đo | đo | introspection | đo | đo | IdP latency/pool |
| C2 | Introspection cache TTL có kiểm soát | đo | đo | đo | introspection | đo | đo | Revoke freshness |

Các ô “đo” là **mẫu bảng ghi kết quả**, không phải số liệu đã đo. Chỉ kết luận bottleneck khi có bằng chứng CPU profile, latency breakdown hoặc queue/pool correlation; một p95 cao không chứng minh ngay hash hay JWT là nguyên nhân.

## 9. Lỗi đo lường và vận hành thường gặp

- **So sánh khác loại workload:** lấy “một lần matches” so với “một HTTP request end-to-end”, hoặc so với một introspection giả lập không có TLS, rồi kết luận cơ chế nào tốt hơn tuyệt đối.
- **Không warm-up:** thời gian JIT/JWK fetch/khởi tạo pool bị trộn với steady-state; ngược lại chỉ chạy warm case khiến bỏ sót rủi ro xoay khóa và khởi động.
- **Đo blocking tại event loop:** wrapper Reactor không làm phép toán blocking tự thành non-blocking; phải dùng boundary hợp lý và giám sát.
- **Bỏ qua hàng đợi:** p95 của CPU operation thấp nhưng latency HTTP lớn do boundedElastic/connection pool chờ.
- **Đặt mọi cost lên cùng Scheduler:** login spike chiếm worker của công việc I/O blocking khác; cần capacity planning, rate-limit và tách tài nguyên khi có chứng cứ.
- **Tối ưu bằng bỏ validation:** bỏ kiểm tra aud/exp/issuer/alg hoặc chấp nhận access khi introspection timeout là lỗi bảo mật, dù benchmark trông nhanh hơn.
- **Cache không có chính sách:** JWT JWKS key cache khác hẳn cache quyền truy cập hoặc introspection active; TTL của quyền liên quan trực tiếp revocation.
- **Báo cáo chỉ average:** không phản ánh p99, tail latency khi I/O chậm, GC pause hoặc hàng đợi bùng phát.
- **Bỏ qua kiểu lỗi và dữ liệu thử:** tỉ lệ token invalid, short-circuit và credential không hợp lệ làm số đo thay đổi, không thể so hai cấu hình khi workload lệch.
- **Thao tác thử với IdP production:** load test có thể làm rate-limit hoặc tác động người dùng khác; dùng sandbox và giới hạn đã được phê duyệt.

## 10. Checklist hoàn thành bài Knowledge

Có thể coi bài thực hành đạt khi học viên trình bày được: (1) khác biệt chi phí CPU/memory của password KDF, CPU/crypto của JWT và network/IdP của introspection; (2) lý do password matches phải ra khỏi Netty event-loop; (3) cold/warm JWKS và key rotation làm phép đo JWT thay đổi; (4) cách kiểm tra introspection timeout/fail-closed và tác động cache lên revoke; (5) p50/p95/p99, throughput, concurrency và queue/pool/CPU quan trọng hơn một số trung bình; (6) cách chạy lab JDK 17 và nêu đúng giới hạn synthetic benchmark; (7) cách bọc operation bằng Micrometer và tránh đưa credential vào metrics; (8) phương pháp thử tải có scenario, tham số, tính đúng đắn bảo mật và bằng chứng để quyết định tối ưu.

**Nguyên tắc áp dụng:** giữ nguyên chính sách xác thực và an toàn mật khẩu, cô lập các phép đo, xác nhận nguồn bottleneck, sau đó tối ưu queue, threading, connection reuse, caching được phép hoặc capacity của hạ tầng. Mọi thay đổi hiệu năng phải được kiểm thử lại về hành vi security, thời hạn token và thu hồi quyền.