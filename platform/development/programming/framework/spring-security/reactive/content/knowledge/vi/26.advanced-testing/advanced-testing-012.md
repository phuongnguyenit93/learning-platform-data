# Kiểm thử thời hạn token, timeout, hủy đăng ký và phản hồi đã bắt đầu trong Spring Security WebFlux

## 1. Mục tiêu và ranh giới

Bài này tập trung vào bốn nhóm tình huống dễ bị bỏ sót khi kiểm thử bảo mật **reactive**: token hết hạn, thao tác vượt thời gian cho phép, subscriber hủy đăng ký (cancellation), và lỗi xảy ra sau khi HTTP response đã được commit. Mục tiêu là chứng minh **hệ thống phát ra đúng tín hiệu, trả đúng phản hồi khi còn có thể, dọn dẹp tài nguyên và không che giấu lỗi bảo mật**.

Ví dụ giả định Java 17+, Spring Boot 3.3.x, Spring Security 6.x, Spring WebFlux, Reactor và JUnit 5. Phân biệt các lớp kiểm thử:

- **Token/validator**: xác minh chữ ký, `exp`, `nbf`, issuer, audience, sai lệch đồng hồ và mã lỗi của decoder thật.
- **Chuỗi bảo mật HTTP**: kiểm tra kết quả của `SecurityWebFilterChain` khi `ReactiveJwtDecoder` trả JWT hợp lệ hoặc phát lỗi xác thực.
- **Reactive signal**: kiểm tra `onNext`, `onError`, `onComplete`, `cancel` và tác dụng của `timeout`.
- **HTTP response**: kiểm tra thời điểm commit và giới hạn sửa status/header sau commit.

Không đánh đồng `WebTestClient` với `StepVerifier`: công cụ đầu quan sát giao thức HTTP, công cụ sau quan sát tín hiệu của Publisher. Trong WebFlux, `cancel` là tín hiệu từ downstream đến upstream; nó không phải một HTTP response có status cố định.

## 2. Mô hình dòng xử lý và kỳ vọng

Một request được xử lý theo ý niệm sau:

~~~text
HTTP request
  -> WebFilter / SecurityWebFilterChain
  -> xác thực Bearer token (ReactiveJwtDecoder)
  -> phân quyền
  -> handler tạo Mono/Flux
  -> ghi status, header và body
  -> response committed -> hoàn tất / lỗi / client ngắt kết nối
~~~

Ở từng thời điểm cần đặt câu hỏi: **token đã được kiểm tra chưa, publisher đã được subscribe chưa, thời gian đang tính cho công đoạn nào, response đã committed chưa, và ai phát tín hiệu cancel?**

| Tình huống | Quan sát quyết định | Kết quả cần chứng minh |
| --- | --- | --- |
| Token hết hạn khi xác thực | Decoder/validator từ chối token | Thường HTTP 401 và challenge `WWW-Authenticate: Bearer`; không chạy nội dung endpoint bảo vệ |
| Token hợp lệ nhưng thiếu quyền | Đã xác thực, phân quyền từ chối | HTTP 403, phân biệt rõ với 401 |
| Công đoạn chưa xong khi hết hạn chờ | Publisher phát `TimeoutException`, hoặc nhánh fallback | HTTP status theo chính sách lỗi nếu **chưa** commit; xác minh timeout upstream và cleanup |
| Subscriber hủy đăng ký | `doOnCancel` hoặc `doFinally(CANCEL)` | Dừng luồng downstream, giải phóng subscription/tài nguyên; không kỳ vọng một status HTTP từ tín hiệu này |
| Lỗi sau khi đã ghi byte/flush đầu tiên | `ServerHttpResponse.isCommitted() == true` | Không sửa được status thành 401/403/5xx; kiểm tra logging, cleanup và kết thúc kết nối an toàn |

**401, 403, 408, 503 và 504 không thể dùng thay nhau.** 401 là không xác thực được; 403 là thiếu quyền sau xác thực. Một timeout ứng dụng có thể được ánh xạ thành 503 hoặc mã khác theo hợp đồng API; 504 thường do gateway/proxy trả cho upstream timeout, còn 408 liên quan thời gian nhận request. Không mặc định mọi `TimeoutException` sẽ trở thành 504.

## 3. Kiểm thử hết hạn JWT có kiểm soát thời gian

JWT dùng `exp` (expiration time), thường được biểu diễn bằng NumericDate tính bằng giây Unix. `nbf` là thời điểm chưa được dùng trước đó; `iat` là thời điểm phát hành, **không tự nó thay thế kiểm tra `exp`**. Tại đúng ranh giới `exp`, token được xem là hết hiệu lực theo phép so sánh thời gian, nhưng nhiều validator có cấu hình **clock skew** (dung sai lệch đồng hồ). Vì vậy phải xác định clock skew thực tế trước khi đặt kỳ vọng tại biên.

Ma trận quan trọng: token còn hạn, `exp` ở quá khứ xa hơn clock skew, `exp` sát biên, `nbf` ở tương lai, chữ ký sai, issuer/audience sai, thiếu bearer token, và người dùng hợp lệ nhưng thiếu authority. Đảm bảo JWT có chữ ký và claim thực sự đi qua decoder ở các ca kiểm tra crypto/claim.

Có hai mức thử nghiệm, không được nhầm:

1. **Kiểm tra decoder thật**: tạo JWT đã ký bằng khóa dành riêng cho test; cấu hình cùng issuer/audience, thuật toán và bộ validator như production; dùng đồng hồ cố định khi validator/hạ tầng hỗ trợ; chứng minh `exp` và `nbf` được từ chối thực sự. Tránh `Thread.sleep` để đợi token hết hạn. Nếu phải kiểm tra sát biên thời gian, quản lý Clock/validator có thể tiêm thời gian hoặc dùng token với thời điểm đủ xa giới hạn dung sai.
2. **Kiểm tra chuỗi HTTP**: stub `ReactiveJwtDecoder` trả lỗi để chứng minh Spring Security chuyển lỗi xác thực thành 401, không chạy handler. Stub ở đây **không chứng minh** bộ validator thật có xử lý thời hạn đúng.

Ví dụ kiểm thử HTTP hoàn chỉnh dưới đây đặt trong một ứng dụng Spring Boot WebFlux có các starter WebFlux, Security, OAuth2 Resource Server và test. Với Spring Boot 3.3, `@MockBean` là lựa chọn phù hợp; ở các phiên bản mới hơn có thể dùng annotation mock được hỗ trợ tương ứng.

~~~java
package demo.security;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidationException;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.mockito.Mockito.when;

@WebFluxTest(controllers = JwtExpiryHttpTest.SecretController.class)
@Import(JwtExpiryHttpTest.TestSecurity.class)
class JwtExpiryHttpTest {

    @Autowired
    WebTestClient client;

    @MockBean
    ReactiveJwtDecoder decoder;

    @Test
    void expiredJwtReturns401WithBearerChallenge() {
        when(decoder.decode("expired")).thenReturn(
            Mono.error(new JwtValidationException(
                "JWT expired",
                List.of(new OAuth2Error(
                    "invalid_token", "JWT expired", null))
            ))
        );

        client.get()
            .uri("/private")
            .headers(h -> h.setBearerAuth("expired"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueMatches(
                HttpHeaders.WWW_AUTHENTICATE, "Bearer.*");
    }

    @Test
    void acceptedJwtReachesProtectedHandler() {
        Jwt accepted = Jwt.withTokenValue("accepted")
            .header("alg", "HS256")
            .claim("sub", "alice")
            .issuedAt(Instant.parse("2026-01-01T00:00:00Z"))
            .expiresAt(Instant.parse("2099-01-01T00:00:00Z"))
            .build();
        when(decoder.decode("accepted")).thenReturn(Mono.just(accepted));

        client.get()
            .uri("/private")
            .headers(h -> h.setBearerAuth("accepted"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("protected");
    }

    @RestController
    static class SecretController {
        @GetMapping("/private")
        Mono<String> secret() {
            return Mono.just("protected");
        }
    }

    @Configuration
    @EnableWebFluxSecurity
    static class TestSecurity {
        @Bean
        SecurityWebFilterChain webFluxSecurity(ServerHttpSecurity http) {
            return http
                .authorizeExchange(ex -> ex
                    .pathMatchers("/private").authenticated()
                    .anyExchange().permitAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                    .jwt(Customizer.withDefaults()))
                .build();
        }
    }
}
~~~

Ở test đầu, tín hiệu lỗi của decoder khiến middleware xác thực trả 401; handler không có cơ hội tạo dữ liệu bảo vệ. Test thứ hai chứng minh một JWT **được stub cho phép** đi qua chuỗi HTTP. Nó không xác minh chữ ký hoặc thời điểm `exp` của decoder thật. Có thể thêm `AtomicInteger` trong controller test để khẳng định handler không bị gọi với token hỏng, nhưng không lưu trạng thái chia sẻ giữa các test gây phụ thuộc thứ tự.

Với đường dẫn yêu cầu authority, thêm một trường hợp JWT được decoder chấp nhận nhưng scope/role thiếu: `authenticated()` chưa đủ để tạo 403; cấu hình `hasAuthority(...)` hoặc quy tắc phân quyền thực tế rồi mới khẳng định 403. Dùng `SecurityMockServerConfigurers.mockJwt()` để thử phân quyền là phù hợp, nhưng cơ chế này cũng không kiểm tra hết hạn/chữ ký JWT.

## 4. Kiểm thử timeout: thời điểm bắt đầu, tầng gây lỗi và fallback

Ba timeout độc lập cần phân biệt:

- **Xác thực token**: truy vấn khóa JWKS, opaque-token introspection hoặc backend xác thực từ xa có thể chậm. Trường hợp này phải kiểm thử timeout và cách ánh xạ lỗi ngay tại adapter xác thực; không tự gọi mọi timeout là token hết hạn.
- **Xử lý nghiệp vụ reactive**: `Mono.timeout`/`Flux.timeout` đặt hạn trên luồng; khi hết hạn thường hủy subscription upstream và phát `TimeoutException`. Fallback bằng `onErrorResume` chỉ được dùng khi chính sách nghiệp vụ cho phép.
- **Client/gateway**: `WebTestClient.responseTimeout(...)` hoặc reverse proxy ngừng chờ là giới hạn phía quan sát/gateway; không chứng minh server đã xử lý một `TimeoutException` hoặc đã cleanup đúng.

Với `StepVerifier.withVirtualTime`, phải **tạo Publisher trong supplier** để các scheduler thời gian của Reactor được thay bằng virtual scheduler ngay lúc lắp pipeline. Có thể test trong vài mili giây thực mà vẫn mô phỏng hàng giây/giờ. Cần nhớ `timeout` kiểm soát khoảng đợi giữa các tín hiệu theo overload đang dùng: `Mono.timeout(Duration)` kiểm soát sự xuất hiện tín hiệu đầu/terminal; `Flux.timeout(Duration)` còn có ý nghĩa cho khoảng ngắt giữa các `onNext`.

Ví dụ runnable cho timeout và cancellation:

~~~java
package demo.security;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReactiveSignalsTest {

    @Test
    void timeoutProducesExplicitFallback() {
        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(10))
                    .timeout(Duration.ofSeconds(3))
                    .onErrorResume(TimeoutException.class,
                        error -> Mono.just(-1L)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(3))
            .expectNext(-1L)
            .verifyComplete();
    }

    @Test
    void cancellingSubscriberCancelsUpstream() {
        AtomicReference<SignalType> terminalSignal =
            new AtomicReference<>();

        StepVerifier.withVirtualTime(() ->
                Flux.interval(Duration.ofSeconds(1))
                    .doFinally(terminalSignal::set))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(2))
            .expectNext(0L, 1L)
            .thenCancel()
            .verify();

        assertEquals(SignalType.CANCEL, terminalSignal.get());
    }
}
~~~

Trong test timeout, publisher gốc sẽ phát `0` sau 10 giây ảo, nhưng timeout xảy ra sau 3 giây ảo nên nhánh fallback phát `-1` rồi `onComplete`. Trong test cancellation, hai giá trị `0, 1` đến sau 1 và 2 giây ảo; `thenCancel()` hủy subscription và `doFinally` nhận `CANCEL`. Cần thêm một test **không có fallback** bằng `expectError(TimeoutException.class)` nếu hợp đồng yêu cầu lỗi đi lên.

Khi biến một lỗi thành HTTP response, đặt `onErrorResume` hoặc `onErrorMap` ở lớp có chính sách xử lý rõ ràng, và kiểm tra body/status thực tế bằng `WebTestClient`. Không dùng `onErrorReturn` để biến lỗi xác thực thành dữ liệu “thành công”; điều đó có thể làm lộ endpoint mà đáng ra cần từ chối.

## 5. Hủy đăng ký và giải phóng tài nguyên

Trong Reactive Streams, `Subscription.cancel()` là tín hiệu downstream không còn muốn nhận dữ liệu. Ví dụ: client đóng kết nối khi đang tải streaming response, `take(n)` đã đủ dữ liệu, hoặc `timeout` hủy upstream chậm. Sau khi hủy, không nên giả định client sẽ nhận được body lỗi mới. Hủy subscription cũng **không phải** lệnh ngắt tức thời bảo đảm dừng mọi I/O ngoài Reactor, đặc biệt khi có đoạn code blocking hay lời gọi dịch vụ ngoài không hỗ trợ cancellation.

Cần kiểm tra các điểm có ý nghĩa nghiệp vụ:

1. Publisher ở upstream nhận cancel: dùng `doOnCancel`, `doFinally(SignalType.CANCEL)`, hoặc Publisher có hook lifecycle.
2. Tài nguyên được thu hồi: kết nối, file, lock, stream, tác vụ nền. Với tài nguyên reactive, thiết kế cleanup thông qua `usingWhen` hoặc API quản lý vòng đời tương ứng; phân biệt cleanup khi complete/error/cancel.
3. Không phát thêm side effect có thể tránh được sau khi cancel. Với thao tác đã được gửi ra hệ thống khác, cancellation **không đồng nghĩa rollback**; cần tính idempotency/compensation nếu nghiệp vụ đòi hỏi.
4. Tránh `block()`, `Thread.sleep()` trên event-loop: các thao tác này khiến timeout/cancellation khó có hiệu lực và gây nghẽn luồng.

Đối với HTTP streaming/SSE, `WebTestClient` có thể nhận một phần `FluxExchangeResult`, subscribe, rồi dispose/cancel; tuy nhiên thời điểm network chuyển tín hiệu đóng kết nối đến server phụ thuộc transport. Kiểm thử cleanup ổn định nên đặt assertion ở Publisher hoặc service được instrument, sau đó thêm integration test qua HTTP để xác minh lifecycle trên runtime thực. Không khẳng định một status như “499” là hợp đồng chuẩn: đó là mã phi tiêu chuẩn của một số proxy/logging layer.

## 6. Response đã commit: vì sao không thể đổi sang 401/500?

Trong HTTP, khi status/header đã được gửi (hoặc response được commit bởi cơ chế ghi), server không thể quay lại đổi status ở giữa response. WebFlux cung cấp `ServerHttpResponse.isCommitted()`. Với `writeWith` hoặc `writeAndFlushWith`, commit có thể xảy ra trước khi toàn bộ body hoàn tất. `beforeCommit(...)` là hook để cấu hình thông tin **trước** thời điểm này; nó không cho phép viết lại một response đã gửi.

Kiểm thử nhỏ dưới đây dùng mock response của Spring WebFlux. Nó xác thực việc ghi body commit response và `setStatusCode` bị từ chối sau đó.

~~~java
package demo.security;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CommittedResponseTest {

    @Test
    void committedResponseCannotChangeStatus() {
        MockServerWebExchange exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/stream").build());
        ServerHttpResponse response = exchange.getResponse();

        response.setStatusCode(HttpStatus.OK);
        DataBuffer body = response.bufferFactory().wrap(
            "part-1".getBytes(StandardCharsets.UTF_8));

        StepVerifier.create(response.writeWith(Mono.just(body)))
            .verifyComplete();

        assertTrue(response.isCommitted());
        assertFalse(response.setStatusCode(HttpStatus.UNAUTHORIZED));
    }
}
~~~

Phép kiểm tra `setStatusCode(...)` trả `false` chứng minh **không thể thay mã trạng thái ở giai đoạn đã commit**; không có nghĩa status bên client sẽ được sửa thành 401. Trong thực tế, lỗi sau byte đầu tiên của SSE/stream thường cần ghi nhận vào telemetry, hủy subscription, đóng hoặc kết thúc stream theo giao thức ứng dụng. Không giả định `@ControllerAdvice` hay `ServerAuthenticationEntryPoint` luôn có thể tạo JSON lỗi mới sau commit.

Về thiết kế, mọi bước xác thực/phân quyền cần thiết cho việc cấp dữ liệu phải hoàn tất **trước khi gửi byte đầu**. Nếu một stream chạy rất lâu và chính sách đòi hỏi kiểm tra hiệu lực phiên/token liên tục, phải mô tả rõ cơ chế tái kiểm tra hoặc giới hạn thời lượng kết nối; JWT đã được kiểm tra khi kết nối bắt đầu không tự động bị decoder kiểm tra lại trên mỗi phần tử.

## 7. Thử nghiệm theo lớp và ma trận hồi quy

| Ca | Cấu hình kích thích | Assertion nên có |
| --- | --- | --- |
| JWT vừa được chấp nhận | Decoder thật chấp nhận chữ ký và claim, hoặc stub ở HTTP-test | HTTP 200 và body đúng; phân biệt rõ lớp đang test |
| JWT quá hạn | `exp` ngoài dung sai lệch đồng hồ; decoder thật hoặc lỗi `JwtValidationException` có chủ ý | HTTP 401, challenge Bearer, handler không thực hiện |
| JWT chưa đến thời điểm dùng | `nbf` vượt thời điểm hiện tại và skew | Decoder từ chối; không coi là thiếu authority |
| Đã xác thực nhưng thiếu quyền | JWT hợp lệ, policy `hasAuthority` | HTTP 403 |
| Chậm ở decoder/introspection | Upstream chậm hoặc Publisher có timeout được cấu hình | Lỗi timeout theo policy; không nhầm với `exp`; tài nguyên upstream được hủy khi phù hợp |
| Chậm ở handler | `Mono.delay`/Publisher test có virtual time | `TimeoutException` hoặc fallback đã định nghĩa; status HTTP theo mapper trước commit |
| Cancel giữa stream | Subscriber chủ động `thenCancel` hoặc dispose | `doFinally(CANCEL)`, cleanup, không side effect thừa |
| Lỗi sau chunk đầu tiên | Chủ động commit/flush rồi phát `onError` | `isCommitted()` đúng, không sửa status/header, không cố ghi hai body |
| Hoàn tất bình thường | Publisher `onComplete` | Không gắn nhầm kết quả cleanup thành `CANCEL` |
| Race giữa timeout/cancel/complete | Chọn lịch scheduler có thể kiểm soát | Một terminal outcome theo contract; cleanup chạy một lần; tránh assertion phụ thuộc mili giây thực |

Tùy độ phức tạp, đặt tên test phản ánh đúng phạm vi: `expiredJwtReturns401`, `timeoutCancelsUpstream`, `clientCancelClosesResource`, `committedResponseRejectsStatusChange`. Với timeout từ gateway/client, bổ sung test riêng ở tầng triển khai thực tế và không ép test Reactor giả lập xác nhận hành vi proxy.

## 8. Phụ thuộc, cách chạy và điều cần QA

Trong dự án Gradle Groovy dùng Spring Boot, các phụ thuộc mẫu:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`spring-boot-starter-test` cung cấp JUnit Jupiter, Spring Test, Reactor Test và Mockito trong cấu hình Boot thông dụng. Ví dụ nằm trong package `demo.security`, bên trong một ứng dụng Spring Boot đã có cấu hình chính. Chạy `./gradlew test --tests 'demo.security.*'` nếu tên task/module và cấu hình test của dự án cho phép; với multi-project, dùng task path tương ứng. Các code block là **ba file test độc lập**, không gộp ba khai báo `package` vào cùng một file.

Khi QA, kiểm tra:

- Không dùng token/khóa thật trong log, fixture hoặc thông báo assertion; khóa thử nghiệm chỉ dành cho test.
- `exp`, `nbf`, clock skew và đơn vị giây/mili giây được xác định rõ; tránh kiểm thử thời gian thực dễ chập chờn.
- Test HTTP có decoder stub được ghi rõ là test mapping, không được báo cáo như test chữ ký/validator thật.
- `@WithMockUser`, `mockJwt()` và mock authentication context dùng cho thử phân quyền, không thay thế decoder validation.
- `TimeoutException` xuất hiện ở lớp nào, fallback là chủ ý hay không, và pipeline có hủy upstream hay không.
- Đường cancel, error và complete đều đóng tài nguyên phù hợp; cleanup không chạy trùng gây side effect.
- Chỉ assert status/header lỗi khi response **chưa commit**; sau commit dùng assertion về trạng thái commit, telemetry và lifecycle.
- Bảo đảm mọi Publisher được subscribe trong test; không dùng `Thread.sleep` để kiểm tra một hành vi có thể mô phỏng bằng virtual time.
- Trong môi trường HTTP thực, đưa ra thêm kiểm thử integration cho streaming, proxy timeout và đóng kết nối khi các hành vi đó là yêu cầu sản phẩm.

**Điểm cốt lõi:** token hết hạn là quyết định **xác thực**; timeout là quyết định **thời gian chờ**; cancellation là tín hiệu **vòng đời subscription**; response committed là **ranh giới giao thức HTTP**. Tách bốn cơ chế này thành test độc lập và kiểm tra điểm giao nhau mới phát hiện được lỗi bảo mật reactive mà happy-path không thể bộc lộ.
