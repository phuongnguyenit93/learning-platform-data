# Dữ liệu ngẫu nhiên có thể tái hiện và kiểm soát thời gian

Trong chương **Bộ kiểm thử và CI** của module **SPRING_SECURITY_TESTING**, bộ test không chỉ cần phát hiện lỗi xác thực hoặc phân quyền; nó còn phải **tái hiện được thất bại** trên máy lập trình viên và CI. Hai nguồn gây test chập chờn (*flaky test*) là dữ liệu sinh ngẫu nhiên không lưu seed và các phép so sánh thời gian phụ thuộc đồng hồ thật. Ví dụ, một JWT được tạo sát thời điểm hết hạn có thể hợp lệ ở máy cục bộ nhưng bị từ chối trên CI; một tenant ID tạo ngẫu nhiên có thể tình cờ trùng fixture khác; hoặc bài test tạo subject mới mỗi lần nhưng không lưu dữ liệu cần để chạy lại.

Trong Spring Security Test, các fixture như `@WithMockUser`, `jwt()`, `opaqueToken()`, `oidcLogin()` trên Servlet/MockMvc hay `mockJwt()`, `mockOpaqueToken()`, `mockOidcLogin()` trên Reactive/WebTestClient giúp kiểm tra hành vi **sau xác thực**. Để chúng đáng tin cậy, cần dữ liệu có thể tái tạo, thời gian được kiểm soát, ma trận ca được phép/bị từ chối rõ ràng và kết quả không phụ thuộc thứ tự chạy test. Khi mục tiêu là kiểm tra decoder, introspection hoặc OIDC callback thật, phải bổ sung token ký bằng khóa test/provider stub; một mock principal không thay thế việc xác thực thật.

## 1. Những dạng không ổn định cần loại bỏ

| Dấu hiệu | Nguyên nhân tiềm ẩn | Hậu quả đối với test bảo mật |
| --- | --- | --- |
| Test thất bại một lần rồi không tái hiện được | `new Random()` không cố định seed, `UUID.randomUUID()` dùng trong dữ liệu cần replay | Không biết principal, tenant và resource ID của lần lỗi |
| JWT gần hết hạn lúc request tới filter | Dùng `Instant.now()` nhiều lần và không xét clock skew | Kết quả 200/401 thay đổi theo tốc độ máy, tải CI |
| Test dùng ngày/giờ hệ thống | `LocalDate.now()` và default timezone | Quy tắc hạn dùng đổi kết quả theo múi giờ hoặc thời điểm chạy |
| Kiểm thử async bằng `Thread.sleep(...)` | Scheduler/CPU/GC không có thời hạn cố định | Test thành công hoặc thất bại do timing, không do quyền |
| Test được phép lúc chạy riêng, thất bại khi chạy song song | Dùng cùng seed và cùng khóa/ID DB cho nhiều test | Va chạm dữ liệu, rò `SecurityContext` hoặc dirty fixture |
| CI báo lỗi nhưng thiếu thông tin | Không xuất seed, case ID, clock, timezone | Không có cách chạy lại tình huống trước đó |
| Kiểm tra JWT expired bằng `mockJwt()` | Mock đưa authentication đã được xác thực vào context | Không chứng minh `JwtDecoder` kiểm tra `exp`/`nbf` |

**Mục tiêu không phải loại bỏ tất cả sự ngẫu nhiên.** Mục tiêu là để mỗi biến ngẫu nhiên **có nguồn seed rõ ràng** và mỗi quy tắc thời gian **có mốc tham chiếu được kiểm soát**. Cần phân biệt dữ liệu ngẫu nhiên cho fixture với tính ngẫu nhiên **mang yêu cầu bảo mật mật mã**: tuyệt đối không dùng `java.util.Random` hoặc `SplittableRandom` để tạo secret, session token hoặc key phục vụ triển khai thực.

## 2. Mô hình một test có thể tái hiện

Một test tái hiện được thường có bốn phần:

```text
Test case (ID cố định)
    |
    +--> Seed cố định hoặc được ghi lại
    |       +--> subject, resource ID, tenant, status fixture
    |
    +--> Clock/ZoneId cố định
    |       +--> nbf, exp, thời hạn nghiệp vụ, ranh giới ngày
    |
    +--> Security mechanism đúng
    |       +--> jwt(), opaqueToken(), oidcLogin(), mockJwt() ...
    |
    +--> Assertion độc lập
            +--> HTTP 200/401/403 và body chính xác
            +--> Quyền và tenant chính xác
            +--> Không có dữ liệu/tác dụng phụ trái phép
```

Thông tin đủ để tái chạy một ca thất bại thường là **test class, test method/case ID, seed, clock instant, timezone, phiên bản cấu hình security** và trạng thái fixture đầu vào. Không bao giờ ghi client secret, private key, Bearer token thật hoặc thông tin người dùng thật để đổi lấy khả năng tái hiện.

## 3. Sinh fixture ngẫu nhiên bằng seed rõ ràng

Trong Java, `SplittableRandom` phù hợp để sinh dữ liệu giả có tính **quyết định** (*deterministic*) khi được khởi tạo cùng seed và các lời gọi xảy ra cùng thứ tự. Ví dụ một factory cho fixture người dùng:

```java
import java.util.SplittableRandom;

record SecurityFixture(
    String subject,
    String tenantId,
    String documentId
) {}

final class SecurityFixtures {
    private final SplittableRandom random;

    SecurityFixtures(long seed) {
        this.random = new SplittableRandom(seed);
    }

    SecurityFixture next() {
        int id = random.nextInt(100_000, 1_000_000);
        return new SecurityFixture(
            "sub-fixture-" + id,
            "tenant-fixture-" + id,
            "doc-fixture-" + id
        );
    }
}
```

Với cùng seed và cùng phiên bản thuật toán/mã fixture, `new SecurityFixtures(17L).next()` tạo cùng ba giá trị qua mỗi lần chạy. Các tên/ID trong ví dụ **không phải** credential, mật khẩu hay token. Nếu bộ test cần hai tenant khác nhau, tạo ID phân biệt có chủ đích, thay vì hy vọng hai số ngẫu nhiên không trùng:

```java
SecurityFixture base = new SecurityFixtures(17L).next();
String allowedTenant = base.tenantId();
String forbiddenTenant = base.tenantId() + "-other";

assertNotEquals(allowedTenant, forbiddenTenant);
```

Nếu yêu cầu sự kiện phải **không trùng trong database** khi nhiều job CI cùng chạy, seed cố định **không bảo đảm tính duy nhất toàn hệ thống**. Hãy cô lập schema/database của từng job, namespace fixture theo test case, hoặc cleanup theo khóa thuộc riêng test. Đừng để việc “tái hiện được” biến thành va chạm khi chạy song song.

### Lấy seed từ JVM property và in ra khi thất bại

```java
@Test
void sameSeedReproducesPrincipalAndResource(TestReporter reporter) {
    long seed = Long.getLong("test.seed", 910_007L);
    SecurityFixture fixture = new SecurityFixtures(seed).next();

    reporter.publishEntry("test.seed", Long.toString(seed));
    reporter.publishEntry("test.case", "principal-and-resource");

    assertTrue(fixture.subject().startsWith("sub-fixture-"),
        "Reproduce with -Dtest.seed=" + seed);
    assertTrue(fixture.documentId().startsWith("doc-fixture-"));
}
```

`TestReporter` là parameter injection của JUnit Jupiter. `Long.getLong("test.seed", 910_007L)` đọc **system property** (không phải environment variable) và lấy giá trị mặc định nếu property chưa được cấu hình. Chú ý cú pháp: `Long.getLong` không dùng để đọc một chuỗi số tùy ý như `Long.parseLong`; nó lấy property theo **tên key**.

Đối với các bài test quan trọng, hãy ghi thêm seed trong **assertion message** hoặc thông tin report CI. Nếu test fail trong một lượt chạy không có property, dùng đúng seed đã log để chạy lại trên máy cục bộ. **Không cần dump toàn bộ JWT hoặc thông tin đăng nhập** để xác minh seed.

## 4. Tránh phụ thuộc vào thứ tự sinh và thứ tự chạy test

Một seed cố định có thể vẫn cho kết quả không ổn định nếu nhiều test chia sẻ **cùng instance mutable `Random`**: test A gọi `nextInt()` trước hay sau test B sẽ thay đổi dữ liệu đầu vào. Việc chạy parallel cũng làm thứ tự tiêu thụ khác nhau.

**Sai:** dùng một generator global chia sẻ:

```java
static final SplittableRandom GLOBAL_RANDOM = new SplittableRandom(17L);

// Hai test cùng gọi GLOBAL_RANDOM.nextInt().
// Kết quả mỗi test phụ thuộc vào thứ tự các lời gọi.
```

**Đúng:** tạo generator mới **trong từng ca kiểm thử** hoặc gán seed riêng cho mỗi case:

```java
@ParameterizedTest(name = "seed={0}")
@ValueSource(longs = {17L, 101L, 20261125L})
void fixtureShapeDoesNotDependOnPreviousTests(long caseSeed) {
    SecurityFixture f = new SecurityFixtures(caseSeed).next();

    assertFalse(f.subject().isBlank());
    assertFalse(f.tenantId().isBlank());
    assertFalse(f.documentId().isBlank());
}
```

Khi dùng property-based testing hoặc fuzzing, mỗi thất bại cần lưu **seed, dữ liệu đã thu nhỏ (*shrunk counterexample*) và các tham số case**. Khi muốn fuzz nhiều vòng, có thể dẫn xuất seed riêng từ seed của run và index cố định của ca test; tránh dựa vào thứ tự chạy hoặc một biến đếm toàn cục. Dữ liệu fuzz phải tôn trọng ràng buộc cần thiết của domain, ví dụ ID đúng định dạng, thời gian hợp lệ, tenant đúng/sai có chủ đích, authority phân biệt rõ.

**Quan trọng về mật mã:** thuật toán PRNG có seed xác định phù hợp cho *identifier fixture*. Nó **không** phù hợp để tạo password thực, CSRF secret, OAuth2 state/nonce cho production hoặc private key mật mã cần bảo vệ. Với test chữ ký, dùng khóa riêng chỉ dành cho test và không dùng lại trên môi trường triển khai; nếu test cần kiểm chứng độ ngẫu nhiên bảo mật, thực hiện bằng `SecureRandom` và assertion theo hợp đồng mật mã, không ép sản phẩm tạo secret dự đoán được.

## 5. Kiểm soát thời gian bằng `Clock` thay vì gọi `Instant.now()` tùy tiện

Giả sử hệ thống có quyền truy cập tài liệu trong khoảng `[notBefore, expiresAt)`: được phép tại chính `notBefore` và **không còn hợp lệ từ đúng `expiresAt`**. Việc liên tục gọi `Instant.now()` trong service làm test phải chờ đồng hồ hoặc chọn thời điểm may rủi.

Nên tiêm `java.time.Clock` vào logic nghiệp vụ:

```java
import java.time.Clock;
import java.time.Instant;

final class AccessWindowPolicy {
    private final Clock clock;

    AccessWindowPolicy(Clock clock) {
        this.clock = clock;
    }

    boolean isActive(Instant notBefore, Instant expiresAt) {
        Instant now = clock.instant();
        return !now.isBefore(notBefore) && now.isBefore(expiresAt);
    }
}
```

Với `Clock.fixed(...)`, test kiểm tra chính xác các thời điểm biên:

```java
@Test
void timeWindowHasDeterministicBoundaries() {
    Instant start = Instant.parse("2026-06-01T10:00:00Z");
    Instant end = start.plusSeconds(600);

    AccessWindowPolicy before = new AccessWindowPolicy(
        Clock.fixed(start.minusNanos(1), ZoneOffset.UTC));
    AccessWindowPolicy atStart = new AccessWindowPolicy(
        Clock.fixed(start, ZoneOffset.UTC));
    AccessWindowPolicy beforeEnd = new AccessWindowPolicy(
        Clock.fixed(end.minusNanos(1), ZoneOffset.UTC));
    AccessWindowPolicy atEnd = new AccessWindowPolicy(
        Clock.fixed(end, ZoneOffset.UTC));

    assertFalse(before.isActive(start, end));
    assertTrue(atStart.isActive(start, end));
    assertTrue(beforeEnd.isActive(start, end));
    assertFalse(atEnd.isActive(start, end));
}
```

Không cần `Thread.sleep(...)`, không phụ thuộc thời gian CI chạy, và phép thử **bắt được lỗi `<=` so với `<`** ở mốc hết hạn. Đây là ưu điểm lớn nhất của kiểm soát thời gian: khả năng kiểm tra **ranh giới pháp lý/nghiệp vụ** thay vì chọn các thời điểm cách nhau tùy ý.

### Đưa Clock vào Spring application context

Ở ứng dụng thật:

```java
@Configuration(proxyBeanMethods = false)
class AppClockConfiguration {
    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Khi cần clock cố định trong bộ test tích hợp:

```java
@TestConfiguration(proxyBeanMethods = false)
class FrozenClockTestConfiguration {

    @Bean
    @Primary
    Clock fixedClockForTest() {
        return Clock.fixed(
            Instant.parse("2026-06-01T10:00:00Z"),
            ZoneOffset.UTC);
    }
}
```

Với `@SpringBootTest`, import cấu hình test (chẳng hạn `@Import(FrozenClockTestConfiguration.class)`) và đảm bảo code nghiệp vụ nhận `Clock` qua constructor. Bean `@Primary` là một **bean riêng ưu tiên tiêm**, không sửa đồng hồ hệ thống. Nếu ứng dụng tự dùng `Instant.now()` thay vì injected clock, cấu hình trên **không điều khiển** các lời gọi đó. Không dùng `TimeZone.setDefault(...)` hoặc thay đổi JVM/global state giữa các test song song để mô phỏng thời gian.

## 6. Định nghĩa rõ thời hạn bảo mật và clock skew

Quy tắc thời gian dễ bị nhầm lẫn:

| Trường dữ liệu | Ý nghĩa thường gặp | Kiểm tra nên thực hiện |
| --- | --- | --- |
| `nbf` (*not before*) | Token không được chấp nhận trước thời điểm này | Trước ranh giới bị từ chối, tại/sau ranh giới theo validator và skew |
| `exp` (*expires at*) | Sau thời điểm hết hạn token không còn hợp lệ | Test hết hạn cách đủ xa khỏi skew; kiểm tra mốc biên nếu clock được kiểm soát |
| `iat` (*issued at*) | Thời điểm token được phát hành | Xác nhận policy thời gian phù hợp, không tự suy ra mọi issuer đều có cùng skew |
| Thời hạn session | Session idle/absolute timeout | Thiết lập expiry và đồng hồ/clock ở đúng session store |
| Thời hạn nghiệp vụ | Tenant contract, invite, signed URL, one-time action | Tiêm `Clock` vào service/policy, test hai phía của ranh giới |
| Timestamp của database | `CURRENT_TIMESTAMP`, trigger hoặc default trong SQL | Kiểm soát/quan sát đồng hồ **database**, không mặc định là JVM Clock |

Spring Security thường có **clock skew/leeway** khi xác minh JWT/OIDC. Điều này không có nghĩa ta được bỏ qua ranh giới. Cần phân biệt:

1. **Business Clock:** clock được tiêm vào service/application policy của bạn.
2. **Token Validator Clock:** clock thực tế được `JwtDecoder`/`JwtTimestampValidator` hoặc OIDC decoder/validator sử dụng.
3. **Database Clock:** thời gian của DB server khi SQL/trigger tính expiration.
4. **Scheduler/Virtual Clock:** thời gian điều khiển `Mono.delay` và các toán tử Reactor.

Điều khiển `Clock.fixed(...)` cho service **không tự động** điều khiển đồng hồ của JWT validator, database hoặc Reactor scheduler. Với test decoder JWT thực tế, cấu hình validator/clock theo khả năng phiên bản Spring Security đang dùng; hoặc dùng token được ký bằng khóa test có `nbf`/`exp` cách xa mốc thời gian hiện tại và skew cho các test thành công/thất bại. Kiểm tra audience (`aud`) cũng cần validator/chính sách audience **được cấu hình thực sự**, vì không phải mọi decoder mặc định đều bắt buộc kiểm tra audience của ứng dụng. Nếu test sát đúng biên thời gian, phải kiểm soát **chính clock mà validator đang đọc**; không dùng `mockJwt()` rồi suy luận validator đã được kiểm tra.

## 7. MockMvc: fixture có seed, clock cố định và kiểm tra quyền

Giả sử API Servlet `GET /api/leases/{id}` cho phép principal JWT có authority `SCOPE_leases.read` đọc lease thuộc đúng tenant, miễn lease chưa hết hạn. Một hợp đồng minh họa:

| Trường hợp | HTTP | Dữ liệu lease |
| --- | --- | --- |
| Anonymous | 401 với bearer entry point | Không tiết lộ dữ liệu |
| JWT giả đã xác thực nhưng thiếu authority | 403 | Không tiết lộ dữ liệu |
| Có authority nhưng tenant sai | 404 theo policy tránh lộ ID | Không tiết lộ dữ liệu tenant khác |
| Đúng tenant nhưng lease hết hạn | 410 theo hợp đồng minh họa | Không trả nội dung đã hết hạn |
| Đúng tenant, đủ quyền, chưa hết hạn | 200 | Trả lease ID và tenant chính xác |

Endpoint có thể triển khai bằng `@AuthenticationPrincipal Jwt` cùng repository/tầng service được bảo vệ:

```java
record Lease(String id, String tenantId, Instant expiresAt) {}
record LeaseView(String id, String tenantId) {}

interface LeaseRegistry {
    Optional<Lease> findByIdAndTenantId(String id, String tenantId);
}

@RestController
class LeaseController {
    private final LeaseRegistry leases;
    private final Clock clock;

    LeaseController(LeaseRegistry leases, Clock clock) {
        this.leases = leases;
        this.clock = clock;
    }

    @GetMapping("/api/leases/{id}")
    @PreAuthorize("hasAuthority('SCOPE_leases.read')")
    LeaseView read(@PathVariable String id,
                   @AuthenticationPrincipal Jwt jwt) {
        String tenant = jwt.getClaimAsString("tenant_id");
        if (tenant == null || tenant.isBlank()) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }
        Lease lease = leases.findByIdAndTenantId(id, tenant)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
        if (!clock.instant().isBefore(lease.expiresAt())) {
            throw new ResponseStatusException(HttpStatus.GONE);
        }
        return new LeaseView(lease.id(), lease.tenantId());
    }
}
```

Đây là ví dụ tập trung vào **contract**; bộ test tích hợp phải cung cấp `LeaseRegistry` (repository/in-memory fixture phù hợp), cấu hình `SecurityFilterChain` cho resource server JWT, bật `@EnableMethodSecurity`, và cố định `Clock` như mục 5. Điều kiện authority được kiểm tra bởi **method security**, trong khi claim tenant và thời hạn được kiểm tra bởi controller. Test chỉ kiểm chứng method security khi gọi controller/service qua Spring bean proxy.

Một ca được phép trong MockMvc:

```java
@Test
void seededLeaseCanBeReadByMatchingTenant() throws Exception {
    long seed = Long.getLong("test.seed", 910_007L);
    SecurityFixture fixture = new SecurityFixtures(seed).next();

    leasesForTest.save(new Lease(
        fixture.documentId(),
        fixture.tenantId(),
        Instant.parse("2026-06-01T10:10:00Z")));

    mvc.perform(get("/api/leases/{id}", fixture.documentId())
            .with(jwt().jwt(token -> token
                .subject(fixture.subject())
                .claim("tenant_id", fixture.tenantId()))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_leases.read"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(fixture.documentId()))
        .andExpect(jsonPath("$.tenantId").value(fixture.tenantId()));
}
```

Ví dụ giả định `leasesForTest.save(...)` là cổng seed fixture mà lớp test cung cấp và `Clock` của ứng dụng cố định tại `2026-06-01T10:00:00Z`. Dữ liệu phải được setup/cleanup độc lập cho từng test; việc chọn ID ngẫu nhiên có seed không thay thế cleanup. `jwt()` của `SecurityMockMvcRequestPostProcessors` tạo authentication JWT giả, **không kiểm tra signature hoặc expiration**.

### Ca âm tính với cùng seed

Chạy lại **cùng fixture** nhưng đổi **một điều kiện**:

```java
// Thiếu quyền: người dùng đã xác thực, scope không đủ.
mvc.perform(get("/api/leases/{id}", fixture.documentId())
        .with(jwt().jwt(token -> token
            .subject(fixture.subject())
            .claim("tenant_id", fixture.tenantId()))
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_profile.read"))))
    .andExpect(status().isForbidden());

// Đủ quyền nhưng tenant khác: không truy cập chéo tenant.
mvc.perform(get("/api/leases/{id}", fixture.documentId())
        .with(jwt().jwt(token -> token
            .subject(fixture.subject())
            .claim("tenant_id", fixture.tenantId() + "-other"))
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_leases.read"))))
    .andExpect(status().isNotFound());
```

Các đoạn trên nằm trong test đã seed lease và có biến `fixture`. Nếu dùng `@WithMockUser` thay `jwt()` trong controller nhận `Jwt`, principal sai kiểu; test không còn chứng minh claim JWT/tenant. Nếu quyền được xác định bởi mapper từ JWT `scope`, việc gọi `.authorities(...)` chỉ kiểm tra **rule sau khi cấp quyền**, không chứng minh mapper; thêm test riêng cho converter/decoder.

## 8. Mock JWT và token có thời hạn thực sự: hai bài test khác nhau

Khi một test gọi:

```java
mvc.perform(get("/api/leases/fixture-id")
        .with(jwt().jwt(token -> token
            .claim("exp", Instant.parse("2020-01-01T00:00:00Z")))));
```

đó **không phải** test khẳng định JWT hết hạn bị từ chối: `jwt()` đã cài sẵn authentication vào request, bỏ qua bước giải mã/xác minh chữ ký, thời hạn, issuer và audience. Với WebFlux, `mockJwt()` có giới hạn tương tự. Một test đúng về token validation phải gửi:

```http
GET /api/leases/fixture-id HTTP/1.1
Authorization: Bearer <signed-jwt-from-test-key>
```

Phần `<signed-jwt-from-test-key>` chỉ là placeholder, **không phải giá trị token có thể dùng ngay**. Bộ test cần tạo JWS được ký bằng **private key test**, cung cấp public key test cho `JwtDecoder` và để Spring Security chạy validator của phiên bản đang dùng. Chuẩn bị ba nhóm:

- JWT hợp lệ với `iss`, `aud`, `nbf`, `exp` và chữ ký đúng; yêu cầu được phép nếu có authority và tenant phù hợp.
- JWT hết hạn hoặc chưa có hiệu lực, nằm **ngoài clock skew**; bị từ chối ở tầng xác thực, thường 401.
- JWT sai chữ ký, issuer hoặc audience; bị từ chối, không bao giờ vào nhánh trả dữ liệu bảo vệ.

Với mock principal, test dữ liệu/tầng quyền dễ tái hiện. Với token ký thật, test xác thực phải cố định hoặc kiểm soát đúng clock của decoder, để lỗi không phụ thuộc máy CI chạy nhanh hay chậm. Đừng giảm mức kiểm tra bảo mật chỉ để loại bỏ flaky test.

Tương tự, `opaqueToken()`/`mockOpaqueToken()` không kiểm tra introspection HTTP; `oidcLogin()`/`mockOidcLogin()` không kiểm tra nonce, token exchange, issuer hoặc chữ ký ID token. Khi test thời hạn session, token hoặc OIDC, chọn **đúng tầng** và dùng stub phù hợp.

## 9. Reactive: `StepVerifier.withVirtualTime` để không đợi đồng hồ thật

Trong WebFlux, nhiều tác vụ tạo `Mono` hoặc `Flux` có delay, retry/backoff, expiry window hoặc timeout. Nếu test chờ `Mono.delay(Duration.ofMinutes(10))` bằng thời gian thực thì sẽ rất chậm; nếu dùng `Thread.sleep` ngắn rồi đoán kết quả, test không ổn định.

Reactor Test hỗ trợ **virtual time**:

```java
@Test
void delayedPublisherCompletesWithoutTenRealMinutes() {
    StepVerifier.withVirtualTime(() ->
            Mono.delay(Duration.ofMinutes(10))
                .thenReturn("completed"))
        .expectSubscription()
        .expectNoEvent(Duration.ofMinutes(9))
        .thenAwait(Duration.ofMinutes(1))
        .expectNext("completed")
        .verifyComplete();
}
```

Điểm quan trọng: phải **tạo publisher bên trong supplier** của `withVirtualTime(...)` để các toán tử dùng scheduler thích hợp có thể được điều khiển. Nếu publisher/scheduler đã được khởi tạo trước khi virtual scheduler được cài, test có thể vẫn đợi thời gian thật.

### Đừng nhầm virtual scheduler với `Clock` của business policy

`StepVerifier.withVirtualTime` điều khiển scheduler của **những toán tử Reactor dùng scheduler được ảo hóa**; nó không thay đổi `Instant.now()`, `Clock.systemUTC()`, timestamp của database hay clock của JWT decoder. Một service kiểm tra `expiresAt` bằng `Clock` tiêm vào vẫn cần `Clock.fixed`. Nếu service vừa dùng `Mono.delay` vừa gọi `Clock.instant()`, bộ test phải kiểm soát **cả hai nguồn thời gian** hoặc thiết kế lại để dùng một abstraction thời gian thống nhất.

Với API WebFlux đã cấu hình `SecurityWebFilterChain`, request test nên xác nhận cả response và dữ liệu:

```java
webTestClient.mutateWith(mockJwt()
        .jwt(token -> token
            .subject(fixture.subject())
            .claim("tenant_id", fixture.tenantId()))
        .authorities(new SimpleGrantedAuthority(
            "SCOPE_leases.read")))
    .get().uri("/api/leases/{id}", fixture.documentId())
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.id").isEqualTo(fixture.documentId());
```

Đoạn này thuộc test WebFlux có endpoint hợp đồng tương tự `LeaseController`, `fixture` đã seed và `WebTestClient` bind vào application context có `springSecurity()` hoặc được Spring Boot test cấu hình sẵn. Nếu gọi server qua `bindToServer()`, các mock configurer phía test không tự truyền authentication qua socket: gửi JWT fixture thực qua Bearer header để kiểm tra server.

Test publisher trong service có method security cần `@EnableReactiveMethodSecurity` và có `Authentication` trong `ReactiveSecurityContextHolder` khi subscribe. Một `Mono` chỉ được tạo mà không subscribe thì chưa chứng minh phần bảo vệ có thực thi; dùng `StepVerifier` để kiểm tra `onNext`, `onComplete` hoặc `onError(AccessDeniedException)` và side effects.

## 10. Không dùng sleep hoặc đồng hồ thật để kiểm tra async/security

Một số kỹ thuật chờ có thể tái hiện:

| Công việc | Nên dùng | Tránh |
| --- | --- | --- |
| Spring MVC `Callable`/`DeferredResult` | `request().asyncStarted()` rồi `asyncDispatch(...)` và assert kết quả cuối | Chỉ assert bắt đầu async hoặc `Thread.sleep` |
| `CompletableFuture` | `get(timeout, unit)` và assert value/exception | Kiểm tra `future != null` hoặc `isDone()` tức thời |
| `Mono`/`Flux` hữu hạn | `StepVerifier.expectNext(...).verifyComplete()` | Chỉ `assertNotNull(publisher)` |
| Reactor delay/backoff | `StepVerifier.withVirtualTime(...)` | Đợi hàng giây/phút bằng đồng hồ thật |
| Worker chờ tín hiệu | `CountDownLatch`, `Sinks.One`, controlled executor có timeout | `Thread.sleep(100)` phụ thuộc scheduler |
| JWT decoder `exp/nbf` | Clock của validator/test token ngoài skew | Mock JWT rồi tuyên bố đã test decoder |

Giới hạn chờ **hữu hạn** vẫn quan trọng ngay cả khi dữ liệu và Clock đã cố định. Ví dụ test có thể dùng `future.get(3, TimeUnit.SECONDS)` cho một tác vụ fixture ngắn, hoặc `StepVerifier.verify(Duration.ofSeconds(5))` cho stream hữu hạn. Giới hạn là **bảo vệ khỏi test bị treo**, không phải mốc để chứng minh quy tắc expiration. Trong CI chậm, tăng timeout hợp lý nhưng không thay thế bằng retry test vô hạn để che lỗi.

## 11. Timezone, DST, locale và clock của database

Một timestamp `Instant` biểu diễn thời điểm tuyệt đối, khác với `LocalDateTime` không gắn múi giờ. Các lỗi thường gặp là so sánh thời điểm hết hạn bằng `LocalDateTime.now()` trên máy CI có timezone khác, hoặc chuyển `2026-03-29 02:30` trong vùng có DST dù giờ đó có thể không tồn tại.

**Nguyên tắc thực hành:**

1. Lưu thời điểm bảo mật như `exp`, `nbf`, created-at, expires-at bằng `Instant` hoặc kiểu có offset/timezone rõ ràng.
2. Sử dụng `Clock.systemUTC()` ở runtime khi phù hợp; trong test, tạo `Clock.fixed(instant, ZoneOffset.UTC)` để không phụ thuộc timezone máy.
3. Nếu yêu cầu nghiệp vụ dựa trên **ngày của địa phương**, tính `LocalDate.now(clock.withZone(zone))` với `ZoneId` được lựa chọn tường minh, chẳng hạn múi giờ của tenant; test riêng trường hợp chuyển ngày/DST.
4. Khi database dùng `CURRENT_TIMESTAMP`, trigger hay TTL server-side, `Clock.fixed` của Java **không điều khiển** đồng hồ database; phải xác định chính thời gian mà câu SQL sử dụng và kiểm tra tại tầng DB nếu cần.
5. Không gọi `TimeZone.setDefault(...)` trong một test chạy song song với test khác; đây là JVM global state dễ tạo lỗi do thứ tự chạy.

Ví dụ chính sách “hết hạn cuối ngày theo timezone tenant” có thể tách độc lập:

```java
boolean expiresAfterToday(
        LocalDate endDate, ZoneId tenantZone, Clock clock) {
    LocalDate today = LocalDate.now(clock.withZone(tenantZone));
    return !today.isAfter(endDate);
}
```

Hãy thử `today == endDate` và `today == endDate.plusDays(1)` với fixed Clock. Nếu ngày kết thúc được hiểu là hết hạn **tại đầu ngày hôm sau**, xác định rõ việc dùng phép so sánh ngày và tránh trộn `LocalDateTime` thiếu timezone vào dữ liệu token.

## 12. CI: truyền seed và môi trường kiểm thử rõ ràng

Với dự án dùng Gradle, có thể **chuyển JVM system property** từ lệnh Gradle sang JVM chạy test. Ví dụ Kotlin DSL cho task test:

```kotlin
tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    systemProperty(
        "test.seed",
        System.getProperty("test.seed", "910007")
    )
    systemProperty("user.timezone", "UTC")
}
```

Chạy với seed mặc định hoặc seed của ca từng thất bại:

```bash
./gradlew test -Dtest.seed=910007
./gradlew test -Dtest.seed=314159
```

Trên Windows có thể dùng `.\gradlew.bat test -Dtest.seed=314159`. Đoạn Gradle là **mẫu cấu hình trong tài liệu**, không phải chỉ thị phải chỉnh build hiện tại của module. Nếu dự án dùng Maven/JUnit launcher khác, bảo đảm property được chuyển vào **test JVM thực sự**, không chỉ JVM của công cụ build.

Trên CI, cần lưu ít nhất:

- Tên bài test thất bại và case ID.
- Seed được sử dụng hoặc danh sách seed đã thử.
- Mốc `Clock` và `ZoneId` được tiêm vào policy liên quan.
- Loại database/test container (nếu dùng), phiên bản JDK và dependency framework ở mức cần tái hiện.
- HTTP status, assertion thất bại và loại exception **đã loại bỏ bí mật nhạy cảm**.

Nếu chạy nhiều seed trong pipeline, nên có một tập **regression seeds cố định** chạy ở mọi pull request, thêm một tập seed fuzz theo lịch/nhánh riêng, và lưu lại seed khi thất bại. Đừng coi chạy lại test nhiều lần đến khi xanh là “sửa flaky test”; khi test fail, seed phải dẫn tới cùng điều kiện để tìm nguyên nhân.

### Ví dụ ma trận trên CI

```text
PR gate:
  - Unit/security tests: seed=17, 101, 910007
  - Fixed Clock for business time boundaries
  - HTTP allowed/denied matrix
  - Database isolated per worker

Nightly:
  - Property-based/fuzz seeds, lưu seed khi lỗi
  - Token validation với khóa test và issuer test
  - Stress/concurrency tests được cô lập

Failure report:
  - class + method + case index
  - seed + fixed instant + zone
  - status/exception và trạng thái dữ liệu không nhạy cảm
```

## 13. Các ca âm tính phải thay đổi một yếu tố ở mỗi lần kiểm tra

Với cùng principal/resource ID lấy từ seed, cùng clock và cùng trạng thái database, hãy tạo ma trận:

| Ca kiểm thử | Thay đổi có chủ đích | Kỳ vọng |
| --- | --- | --- |
| Happy path | Authority đúng, tenant đúng, thời điểm nằm trong hạn | 200 và body/side effect đúng |
| Anonymous | Bỏ xác thực | 401 với Bearer/Basic entry point; không lộ dữ liệu |
| Thiếu authority | Giữ subject/tenant nhưng đổi `SCOPE_leases.read` thành scope khác | 403; không truy cập tài nguyên |
| Sai tenant | Giữ scope và subject, đổi `tenant_id` | 404/403 theo policy, không lộ dữ liệu tenant khác |
| Claim tenant thiếu/sai kiểu | Giữ các phần còn lại | Bị từ chối theo contract |
| Business expiry vừa trước biên | Fixed Clock = `expiresAt - 1ns` | Được phép nếu business rule định nghĩa khoảng mở bên phải |
| Business expiry đúng tại biên | Fixed Clock = `expiresAt` | Hết hạn theo contract `[start, end)` |
| JWT decoder từ chối token hết hạn | **Không dùng mock**; gửi JWT ký test với exp ngoài skew | Authentication fail, thường HTTP 401 |
| Token sai issuer/audience/chữ ký | Không dùng mock; token fixture đi qua decoder | Authentication fail, không gọi business logic |
| Opaque token không còn active | Introspection stub `active:false`, không dùng `mockOpaqueToken()` | Không xác thực, không có side effect |
| OIDC nonce không khớp | Provider stub/Authorization Code flow, không dùng `mockOidcLogin()` | Không tạo phiên OIDC thành công |

**Một thay đổi mỗi ca** giúp phân biệt: nếu vừa thay seed, đổi tenant, đổi authority và đổi thời gian, một lỗi 403/401 có thể do nhiều nguyên nhân và không chứng minh điều kiện được nhắm đến. Ở nhóm integration có database, kiểm tra thêm dữ liệu không bị thay đổi đối với request bị từ chối.

## 14. Các lỗi khó phát hiện khi test song song

| Lỗi | Cách khắc phục |
| --- | --- |
| Cùng fixed ID ở hai test tạo unique constraint violation | Mỗi test dùng schema riêng/namespace fixture; cleanup theo khóa sở hữu |
| Cùng generator bị dùng ở nhiều thread | Tạo generator riêng trên từng test/case; seed tách biệt |
| Test thay đổi `Clock` singleton mutable trong một context được cache | Ưu tiên Clock bất biến/test context riêng, hoặc fixture clock được reset và không dùng song song |
| Test thay đổi default timezone/locale JVM | Tiêm `ZoneId`/`Clock` hoặc cô lập JVM, không sửa global state khi chạy parallel |
| Dùng transaction rollback của test để nghĩ request HTTP thật đã rollback | Phân biệt transaction phía test/server; kiểm tra DB sau commit/rollback với session độc lập |
| Rò `SecurityContextHolder` thread-local qua worker pool | Dùng cơ chế propagation và cleanup đúng, test hai user khác nhau |
| Reactor virtual scheduler bị cài/giữ từ test trước | Tạo publisher trong supplier và dọn/reset scheduler theo quy trình của Reactor Test |
| Retry test đến khi pass | Ghi seed, clock, fixture, tìm root cause; không chấp nhận flaky test trong security gate |

Mục tiêu là **tính quyết định ở tầng dữ liệu và thời gian** đồng thời vẫn kiểm tra bất biến an toàn dưới concurrency. Các race condition thật cần những bài test riêng với barrier/latch, Testcontainers hoặc đồng bộ có chủ đích; chỉ cố định seed không loại trừ mọi race condition.

## 15. Bài thực hành: tái hiện lỗi 401/403 và expiry trên CI

Tạo một API bảo vệ tài liệu hoặc lease: `GET /api/leases/{id}` với `SCOPE_leases.read` và `tenant_id`, cùng một rule hạn dùng `expiresAt`. Dữ liệu thuộc một test database/registry cô lập.

1. **Baseline:** dùng seed `910007` tạo subject, tenant và document ID. Ghi seed vào report, tạo lease còn hạn dưới `Clock.fixed(2026-06-01T10:00:00Z)`.
2. **Được phép:** dùng MockMvc `jwt()` (hoặc WebTestClient `mockJwt()`), authority đúng và tenant đúng; assert status 200, subject/ID/tenant đúng với fixture.
3. **Thiếu quyền:** chỉ đổi authority sang `SCOPE_profile.read`; assert 403 và không có dữ liệu nào bị tiết lộ.
4. **Sai tenant:** giữ authority nhưng đổi tenant; assert 403/404 theo policy, không truy cập dữ liệu tenant khác.
5. **Ranh giới thời gian:** tạo hai test clock `expiresAt.minusNanos(1)` và `expiresAt`. Test thứ nhất được phép, test thứ hai bị từ chối/hết hạn. Không sử dụng `sleep`.
6. **Tái hiện theo seed:** chạy lại test với `-Dtest.seed=910007`; đổi sang một seed khác, bảo đảm các bất biến quyền và thời gian vẫn đúng.
7. **Reactive:** thêm một `Mono.delay` và `StepVerifier.withVirtualTime`; kiểm tra kết quả được phát và hoàn tất mà không đợi thời gian thật.
8. **JWT thật:** viết test tích hợp riêng tạo JWT được ký bằng khóa test và có `exp` vượt qua clock skew; xác nhận token hết hạn bị 401 **không dùng `jwt()`/`mockJwt()`**.
9. **Thử CI parallel:** chạy các case trên cùng CI job với nhiều worker/test JVM; nếu va chạm ID, sửa fixture isolation thay vì bỏ seed.
10. **Kiểm tra khả năng chẩn đoán:** cố ý làm một ca fail, xác nhận báo cáo cho phép tái chạy đúng class/method/seed/clock mà không tiết lộ bí mật.

### Tiêu chí hoàn thành

- Mọi fixture ngẫu nhiên quan trọng dùng seed xác định, tái hiện được và **ghi seed khi test lỗi**.
- Không có test nào phụ thuộc vào thứ tự tiêu thụ generator dùng chung hoặc dữ liệu còn lại của lần chạy trước.
- Logic thời hạn nghiệp vụ dùng `Clock` có thể tiêm vào và kiểm tra chính xác thời điểm biên.
- Không nhầm `Clock.fixed` của service, Reactor virtual time, clock của JWT decoder và clock của database.
- Có cả test được phép và bị từ chối (401/403, tenant sai, expiry), không chỉ test 200.
- Các test mock principal được phân biệt rõ với token/OIDC/introspection validation thật.
- CI có thể chạy lại seed thất bại và không đưa credential, key hay token triển khai vào fixture/log.

## Ghi nhớ

**Dữ liệu ngẫu nhiên hữu ích cho coverage, nhưng phải có seed để tái hiện; thời gian hữu ích cho bảo mật, nhưng phải được kiểm soát đúng nơi nó được đọc.** Trong **SPRING_SECURITY_TESTING**, tạo fixture bằng PRNG có seed riêng cho từng case, kiểm tra quyền và tenant với cả nhánh được phép/bị từ chối, dùng `Clock.fixed` cho hạn dùng nghiệp vụ và `StepVerifier.withVirtualTime` cho các toán tử Reactor cần scheduler. Không dùng mock JWT/OAuth2/OIDC để khẳng định thời hạn, chữ ký hoặc issuer đã được validator thật xác minh. Khi CI thất bại, class/method, seed, thời điểm, timezone và dữ liệu fixture không nhạy cảm phải đủ để tái chạy; không được đổi tính đúng đắn của bảo vệ HTTP lấy một bộ test chỉ “thỉnh thoảng xanh”.
