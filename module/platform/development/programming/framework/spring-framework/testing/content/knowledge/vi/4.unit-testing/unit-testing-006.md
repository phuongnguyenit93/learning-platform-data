# Thay đồng hồ, bộ sinh ID và dữ liệu ngẫu nhiên bằng phụ thuộc kiểm soát được

Unit test cần cho cùng một đầu vào và cùng điều kiện ban đầu một kết quả có thể dự đoán. Tuy nhiên, nhiều thao tác trong ứng dụng phụ thuộc vào những nguồn thay đổi theo thời gian hoặc theo môi trường: thời điểm hiện tại, UUID mới, số ngẫu nhiên, mã xác nhận, giá trị jitter khi retry hoặc dữ liệu fixture được sinh tự động. Nếu code gọi trực tiếp `Instant.now()`, `UUID.randomUUID()` hay `ThreadLocalRandom.current()` ở nhiều nơi, test khó chủ động chọn giá trị và thường phải chờ, đoán hoặc kiểm tra những điều kiện quá rộng.

Giải pháp là đưa các nguồn không xác định đó thành **phụ thuộc có thể tiêm (injectable dependencies)**. Ứng dụng thật nhận implementation sử dụng đồng hồ hệ thống, bộ sinh ID hoặc nguồn ngẫu nhiên phù hợp. Unit test thay chúng bằng `Clock.fixed`, ID cố định, fake hoặc bộ sinh có seed đã biết. Khi đó test có thể kiểm tra chính xác thời điểm, mã định danh và nhánh logic mà không cần dựa vào thời gian thực hay may rủi.

## 1. Nhận diện nguồn không xác định trong code

Những lời gọi sau thường làm test khó lặp lại:

```java
Instant createdAt = Instant.now();
LocalDate today = LocalDate.now();
long now = System.currentTimeMillis();

UUID id = UUID.randomUUID();
int retrySlot = ThreadLocalRandom.current().nextInt(1, 6);
String token = generateRandomToken();
```

Mỗi lần chạy, giá trị có thể khác nhau. Một test kiểm tra ngày hết hạn có thể qua hôm nay nhưng thất bại vào ngày mai. Một test so sánh toàn bộ entity có thể thất bại vì ID mới hoặc timestamp khác. Một test retry có thể chỉ gặp nhánh delay ngắn trong một số lần chạy, khiến nhánh biên khó tái hiện.

Không phải mọi lời gọi ngẫu nhiên đều cần thay thế. Nếu thuật toán được kiểm thử độc lập và tính ngẫu nhiên là chính đối tượng cần kiểm tra, có thể dùng kiểm thử thống kê hoặc property-based testing. Nhưng với unit test nghiệp vụ, thường ta muốn kiểm tra phản ứng của hệ thống trước một thời điểm, ID hoặc giá trị ngẫu nhiên cụ thể. Những nguồn đó nên được kiểm soát qua dependency.

Ba nhóm thường gặp:

| Nguồn | Ví dụ | Cách kiểm soát trong test |
|---|---|---|
| Thời gian | `Instant.now()`, `LocalDate.now()`, thời điểm hết hạn | Tiêm `java.time.Clock`, dùng `Clock.fixed()` |
| ID | `UUID.randomUUID()`, sequence sinh mã | Tiêm `IdGenerator`, trả ID cố định hoặc chuỗi ID đã định trước |
| Ngẫu nhiên | `Random`, `ThreadLocalRandom`, jitter, dữ liệu test ngẫu nhiên | Tiêm abstraction hẹp hoặc bộ sinh có seed cố định |

Mục tiêu không phải biến mọi hàm tiện ích thành interface. Chỉ tách những nguồn làm thay đổi kết quả theo thời gian, môi trường hoặc trạng thái bên ngoài và cần được điều khiển trong test.

## 2. Tiêm `Clock` để kiểm soát thời gian

Java cung cấp `java.time.Clock` chính xác cho mục đích này. Thay vì gọi trực tiếp `Instant.now()` hoặc `LocalDate.now()`, code nhận một `Clock` và đọc thời gian từ clock đó.

```java
import java.time.Clock;
import java.time.Instant;

class ExpirationService {
    private final Clock clock;

    ExpirationService(Clock clock) {
        this.clock = clock;
    }

    Instant currentTime() {
        return Instant.now(clock);
    }
}
```

Trong ứng dụng thật, cung cấp một clock dùng đồng hồ hệ thống. Với ứng dụng Spring, có thể khai báo bean:

```java
@Configuration
class TimeConfiguration {
    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Service nhận `Clock` qua constructor như mọi dependency khác:

```java
@Service
class SubscriptionService {
    private final Clock clock;

    SubscriptionService(Clock clock) {
        this.clock = clock;
    }

    Subscription renew(Subscription subscription, Duration duration) {
        Instant renewedAt = Instant.now(clock);
        return subscription.renew(renewedAt, duration);
    }
}
```

`Clock.systemUTC()` cung cấp thời gian hiện tại theo UTC. Việc dùng `Instant` để lưu một thời điểm tuyệt đối giúp tránh nhầm lẫn giữa thời điểm và múi giờ hiển thị. Nếu nghiệp vụ cần ngày theo múi giờ của cửa hàng hoặc người dùng, hãy chuyển đổi rõ ràng bằng `ZoneId` thay vì ngầm dựa vào timezone mặc định của máy chạy test.

### 2.1. Dùng `Clock.fixed()` trong unit test

`Clock.fixed(instant, zone)` tạo một clock luôn trả về cùng một thời điểm. Đây là lựa chọn phù hợp nhất cho phần lớn test liên quan đến ngày tạo, thời điểm cập nhật, thời hạn, ngày hiệu lực và điều kiện hết hạn.

```java
class ExpirationServiceTest {
    private static final Instant NOW =
            Instant.parse("2026-11-12T08:30:00Z");

    @Test
    void considersSubscriptionExpiredAtItsExpirationInstant() {
        Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
        ExpirationService service = new ExpirationService(clock);
        Subscription subscription = new Subscription(
                NOW.minus(Duration.ofDays(1)), NOW);

        boolean expired = service.isExpired(subscription);

        assertThat(expired).isTrue();
    }
}
```

Điểm quan trọng là test tự chọn mốc thời gian. Không cần `Thread.sleep`, không phụ thuộc ngày trên máy CI và không có nguy cơ chạy qua nửa đêm giữa hai assertion.

Khi kiểm tra ranh giới, hãy xác định rõ quy tắc nghiệp vụ. Ví dụ, một subscription hết hạn khi `now` bằng `expiresAt` hay chỉ khi `now` lớn hơn `expiresAt`? Test nên có các trường hợp trước, đúng tại và sau mốc:

```java
@Test
void checksExpirationBoundary() {
    Instant expiresAt = Instant.parse("2026-11-12T08:30:00Z");

    assertThat(serviceWithClock(expiresAt.minusMillis(1))
            .isExpired(expiresAt)).isFalse();
    assertThat(serviceWithClock(expiresAt)
            .isExpired(expiresAt)).isTrue();
    assertThat(serviceWithClock(expiresAt.plusMillis(1))
            .isExpired(expiresAt)).isTrue();
}
```

`serviceWithClock` ở đây là helper của test tạo service với `Clock.fixed` tương ứng. Ba trường hợp xác định chính xác điều kiện `<`, `<=` hoặc `>` trong quy tắc hết hạn.

### 2.2. Dùng `Clock.offset()` khi cần dịch thời gian

`Clock.offset(baseClock, duration)` tạo clock có thời gian lệch một khoảng so với clock nền. Nó hữu ích khi cần tạo một mốc khác từ cùng một thời điểm tham chiếu:

```java
Instant base = Instant.parse("2026-11-12T08:30:00Z");
Clock baseClock = Clock.fixed(base, ZoneOffset.UTC);
Clock fiveMinutesLater = Clock.offset(baseClock, Duration.ofMinutes(5));

assertThat(Instant.now(fiveMinutesLater))
        .isEqualTo(base.plus(Duration.ofMinutes(5)));
```

Clock offset vẫn cố định nếu clock nền là fixed. Nó không tự chạy thời gian theo đồng hồ thật. Điều này rất hữu ích cho test cần so sánh nhiều mốc mà vẫn giữ kết quả lặp lại.

### 2.3. Khi cần đồng hồ có thể tiến lên

Một số test kiểm tra nhiều thao tác theo thời gian, chẳng hạn tạo token rồi kiểm tra token hết hạn sau vài phút. Có thể dùng hai `Clock.fixed` riêng cho hai giai đoạn, hoặc viết một clock có thể điều khiển trong test. Ví dụ sau là một implementation nhỏ chỉ dành cho test:

```java
final class AdjustableClock extends Clock {
    private Instant currentInstant;
    private final ZoneId zone;

    AdjustableClock(Instant initialInstant, ZoneId zone) {
        this.currentInstant = initialInstant;
        this.zone = zone;
    }

    void advance(Duration duration) {
        currentInstant = currentInstant.plus(duration);
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId zone) {
        return new AdjustableClock(currentInstant, zone);
    }

    @Override
    public Instant instant() {
        return currentInstant;
    }
}
```

Test có thể điều khiển mốc thời gian mà không chờ:

```java
@Test
void expiresTokenAfterConfiguredDuration() {
    AdjustableClock clock = new AdjustableClock(
            Instant.parse("2026-11-12T08:30:00Z"), ZoneOffset.UTC);
    TokenService service = new TokenService(clock, Duration.ofMinutes(10));

    Token token = service.issue();
    assertThat(service.isValid(token)).isTrue();

    clock.advance(Duration.ofMinutes(10));

    assertThat(service.isValid(token)).isFalse();
}
```

Implementation trên không đồng bộ giữa nhiều luồng. Chỉ dùng nó trong test chạy tuần tự; nếu test cần truy cập từ nhiều thread, hãy bảo vệ instant bằng `AtomicReference` hoặc dùng một clock test có hỗ trợ thread safety. Trong đa số unit test, hai clock fixed thường đơn giản hơn.

### 2.4. Phân biệt `Instant`, `LocalDate` và timezone

Một lỗi phổ biến là dùng `LocalDateTime.now()` trực tiếp trong code nghiệp vụ. `LocalDateTime` không chứa timezone hay offset, vì vậy một giá trị như `2026-11-12T08:00` không xác định được thời điểm tuyệt đối nếu thiếu múi giờ.

Với thời điểm tạo bản ghi, thời hạn token hoặc timestamp sự kiện, thường nên dùng `Instant`:

```java
Instant createdAt = clock.instant();
```

Với ngày nghiệp vụ theo một vùng cụ thể, hãy truyền `ZoneId` rõ ràng:

```java
LocalDate businessDate = LocalDate.now(clock.withZone(
        ZoneId.of("Asia/Ho_Chi_Minh")));
```

Test cần kiểm tra các trường hợp đổi ngày hoặc daylight saving time nên cố định cả instant và zone. Không dựa vào timezone mặc định của máy developer hoặc CI.

## 3. Tiêm bộ sinh ID

Một service thường cần ID để tạo entity, event hoặc request. Nếu service tự gọi `UUID.randomUUID()`, test khó khẳng định chính xác ID đã được gắn vào đối tượng và truyền qua các bước xử lý.

Tạo một abstraction nhỏ thể hiện đúng nhu cầu của ứng dụng:

```java
@FunctionalInterface
interface IdGenerator {
    UUID nextId();
}
```

Implementation dùng UUID ngẫu nhiên trong môi trường thật:

```java
@Component
class UuidIdGenerator implements IdGenerator {
    @Override
    public UUID nextId() {
        return UUID.randomUUID();
    }
}
```

Service phụ thuộc vào `IdGenerator`:

```java
@Service
class InvoiceService {
    private final IdGenerator idGenerator;
    private final Clock clock;
    private final InvoiceRepository invoices;

    InvoiceService(IdGenerator idGenerator,
                   Clock clock,
                   InvoiceRepository invoices) {
        this.idGenerator = idGenerator;
        this.clock = clock;
        this.invoices = invoices;
    }

    Invoice createInvoice(CustomerId customerId) {
        Invoice invoice = new Invoice(
                idGenerator.nextId(), customerId, clock.instant());
        return invoices.save(invoice);
    }
}
```

Trong unit test, dùng lambda vì `IdGenerator` là functional interface:

```java
@Test
void createsInvoiceWithGeneratedIdAndControlledTimestamp() {
    UUID expectedId = UUID.fromString(
            "123e4567-e89b-12d3-a456-426614174000");
    Instant expectedTime = Instant.parse("2026-11-12T08:30:00Z");
    IdGenerator ids = () -> expectedId;
    Clock clock = Clock.fixed(expectedTime, ZoneOffset.UTC);
    InvoiceRepository repository = new InMemoryInvoiceRepository();
    InvoiceService service = new InvoiceService(ids, clock, repository);

    Invoice invoice = service.createInvoice(new CustomerId("customer-7"));

    assertThat(invoice.id()).isEqualTo(expectedId);
    assertThat(invoice.createdAt()).isEqualTo(expectedTime);
    assertThat(repository.findById(expectedId)).contains(invoice);
}
```

Ví dụ dùng repository trong bộ nhớ để minh họa cách kiểm soát phụ thuộc; trong test thực tế, có thể dùng fake phù hợp với hợp đồng repository hoặc mock nếu mục tiêu là xác nhận lời gọi. Điểm chính là ID và thời gian do test chọn, nên assertion không cần biết UUID được tạo ngẫu nhiên như thế nào.

### 3.1. Dùng Mockito hoặc bộ sinh ID theo chuỗi

Nếu service cần gọi ID generator nhiều lần, Mockito có thể trả các ID theo thứ tự:

```java
UUID firstId = UUID.fromString("123e4567-e89b-12d3-a456-426614174001");
UUID secondId = UUID.fromString("123e4567-e89b-12d3-a456-426614174002");

when(idGenerator.nextId()).thenReturn(firstId, secondId);
```

Hoặc viết fake nhỏ dùng queue để thể hiện rõ mỗi lần gọi sẽ nhận giá trị nào:

```java
final class SequenceIdGenerator implements IdGenerator {
    private final Queue<UUID> ids;

    SequenceIdGenerator(UUID... ids) {
        this.ids = new ArrayDeque<>(List.of(ids));
    }

    @Override
    public UUID nextId() {
        UUID next = ids.poll();
        if (next == null) {
            throw new IllegalStateException("No test ID configured");
        }
        return next;
    }
}
```

Fake chủ động báo lỗi nếu code gọi nhiều lần hơn dự kiến. Không nên âm thầm sinh UUID thật khi queue hết, vì như vậy test sẽ quay lại trạng thái không xác định và che mất một tương tác ngoài dự kiến.

### 3.2. ID do database tạo

Không phải mọi ID đều do service tạo. Nếu database hoặc persistence provider sinh ID, hãy để repository integration test xác nhận mapping và việc lưu/đọc ID. Unit test service không cần giả lập cơ chế sequence của database nếu service không sở hữu cơ chế đó.

Phân biệt rõ:

- ID do nghiệp vụ yêu cầu service tạo: tiêm `IdGenerator` và kiểm tra ID được truyền vào entity hoặc event.
- ID do database sinh: kiểm tra qua test persistence với database phù hợp.
- ID do hệ thống ngoài cấp: mô hình hóa client/port tương ứng và giả lập phản hồi trong unit test.

Không khẳng định một UUID cụ thể là duy nhất chỉ vì test dùng một giá trị cố định. Test đang kiểm tra luồng truyền và lưu ID, còn tính duy nhất của bộ sinh thật cần được kiểm chứng theo hợp đồng và cơ chế tạo ID ở môi trường tương ứng.

## 4. Kiểm soát nguồn ngẫu nhiên

Giá trị ngẫu nhiên có thể ảnh hưởng đến lựa chọn thuật toán, retry delay, phân bổ mẫu, mã xác nhận hoặc dữ liệu fixture. Nếu service trực tiếp lấy số ngẫu nhiên từ một API toàn cục, test khó yêu cầu một nhánh cụ thể.

Một cách là tiêm abstraction hẹp chỉ chứa thao tác mà nghiệp vụ cần:

```java
@FunctionalInterface
interface RandomIntSource {
    int nextInt(int origin, int bound);
}
```

Implementation cho giá trị ngẫu nhiên thông thường có thể dùng `ThreadLocalRandom`:

```java
@Component
class ThreadLocalRandomIntSource implements RandomIntSource {
    @Override
    public int nextInt(int origin, int bound) {
        return ThreadLocalRandom.current().nextInt(origin, bound);
    }
}
```

Service chỉ biết đến `RandomIntSource`, không phụ thuộc cách implementation lấy số:

```java
class RetryDelayPolicy {
    private final RandomIntSource random;

    RetryDelayPolicy(RandomIntSource random) {
        this.random = random;
    }

    Duration nextDelay() {
        int millis = random.nextInt(100, 501);
        return Duration.ofMillis(millis);
    }
}
```

Trong Java, cận dưới của `nextInt(origin, bound)` được bao gồm, cận trên bị loại trừ. Do đó ví dụ trên tạo delay từ 100 đến 500 milliseconds. Unit test có thể ép nguồn ngẫu nhiên trả về giá trị biên:

```java
@Test
void usesTheConfiguredMinimumDelay() {
    RetryDelayPolicy policy = new RetryDelayPolicy((origin, bound) -> origin);

    assertThat(policy.nextDelay()).isEqualTo(Duration.ofMillis(100));
}

@Test
void usesTheLargestAllowedDelay() {
    RetryDelayPolicy policy = new RetryDelayPolicy((origin, bound) -> bound - 1);

    assertThat(policy.nextDelay()).isEqualTo(Duration.ofMillis(500));
}
```

Fake trả đúng giá trị được chọn, vì vậy test tập trung vào cách service xử lý giá trị đó. Nếu muốn kiểm tra nguồn random được gọi với khoảng đúng, có thể dùng Mockito verify hoặc một fake ghi lại `origin` và `bound`.

### 4.1. Dùng seed cố định cho thuật toán cần chuỗi ngẫu nhiên

Khi cần một chuỗi giá trị ngẫu nhiên có thể tái tạo, dùng bộ sinh pseudo-random với seed cố định. `java.util.Random` phù hợp cho ví dụ đơn giản và triển khai `java.util.random.RandomGenerator` trên Java 17 trở lên:

```java
Random random = new Random(20261112L);

int first = random.nextInt(100);
int second = random.nextInt(100);
```

Với cùng implementation và cùng seed, chuỗi kết quả của `Random` có thể tái tạo. Điều này hữu ích khi kiểm thử thuật toán xử lý nhiều giá trị hoặc sinh fixture lặp lại. Seed nên được ghi rõ trong test để người đọc có thể tái hiện tình huống.

Không dùng một seed cố định để kiểm tra rằng thuật toán thật sự có phân phối ngẫu nhiên đúng. Test với seed chỉ kiểm tra một chuỗi đầu vào cụ thể. Muốn kiểm tra thuộc tính thống kê cần nhiều mẫu, tiêu chí thống kê phù hợp và kiểm soát flakiness; phần đó thường là một dạng test riêng.

Nếu ứng dụng dùng `RandomGenerator` từ Java 17, có thể tiêm interface này và tạo generator xác định trong unit test:

```java
RandomGenerator random = new Random(20261112L);
```

Không nên giả định mọi implementation `RandomGenerator` đều thread-safe. Nếu generator là singleton dùng chung trong Spring và được gọi đồng thời, hãy chọn implementation phù hợp với concurrency hoặc bọc nguồn random theo thread. Với test, một generator riêng cho mỗi test giúp tránh việc một test tiêu thụ mất số của test khác.

### 4.2. Phân biệt pseudo-random và randomness bảo mật

`Random`, `ThreadLocalRandom` và nhiều generator khác phục vụ mục đích mô phỏng hoặc lựa chọn ngẫu nhiên thông thường. Chúng không thay thế nguồn entropy bảo mật khi tạo password reset token, session secret, API key hoặc nonce chống đoán.

Với dữ liệu nhạy cảm cần khó dự đoán, dùng `SecureRandom` hoặc API bảo mật được nền tảng khuyến nghị. Không thay `SecureRandom` bằng `new Random(seed)` trong production để làm test dễ hơn. Hãy đưa thao tác tạo token qua interface riêng, rồi dùng giá trị token cố định trong unit test. Test đang xác nhận token được sử dụng và truyền đúng; thuộc tính bảo mật của implementation cần được kiểm tra riêng.

Ví dụ:

```java
@FunctionalInterface
interface ResetTokenGenerator {
    String nextToken();
}

@Component
class SecureResetTokenGenerator implements ResetTokenGenerator {
    private final SecureRandom secureRandom = new SecureRandom();

    @Override
    public String nextToken() {
        byte[] bytes = new byte[32];
        secureRandom.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }
}
```

Trong unit test, thay `ResetTokenGenerator` bằng `() -> "test-token-001"`. Không cần gọi `SecureRandom` để kiểm tra service đã lưu token, đặt thời hạn hoặc gửi link reset đúng địa chỉ.

## 5. Tổ chức phụ thuộc trong ứng dụng Spring

Các dependency có thể được cung cấp qua constructor injection như những thành phần khác. Ví dụ, `Clock` được khai báo thành bean cấu hình, còn `IdGenerator` và `RandomIntSource` có implementation `@Component`:

```java
@Configuration
class RuntimeDependencyConfiguration {
    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}

@Component
class UuidIdGenerator implements IdGenerator {
    @Override
    public UUID nextId() {
        return UUID.randomUUID();
    }
}
```

Một service nhận các dependency cần thiết qua constructor:

```java
@Service
class VerificationService {
    private final Clock clock;
    private final IdGenerator ids;
    private final ResetTokenGenerator tokens;

    VerificationService(Clock clock,
                        IdGenerator ids,
                        ResetTokenGenerator tokens) {
        this.clock = clock;
        this.ids = ids;
        this.tokens = tokens;
    }

    VerificationRequest createRequest() {
        return new VerificationRequest(ids.nextId(), tokens.nextToken(),
                clock.instant());
    }
}
```

Unit test có thể khởi tạo service trực tiếp với dependency cố định mà không cần khởi động Spring:

```java
@Test
void createsRequestWithControlledValues() {
    Instant now = Instant.parse("2026-11-12T08:30:00Z");
    UUID id = UUID.fromString("123e4567-e89b-12d3-a456-426614174010");

    VerificationService service = new VerificationService(
            Clock.fixed(now, ZoneOffset.UTC),
            () -> id,
            () -> "test-token-001");

    VerificationRequest request = service.createRequest();

    assertThat(request.id()).isEqualTo(id);
    assertThat(request.token()).isEqualTo("test-token-001");
    assertThat(request.createdAt()).isEqualTo(now);
}
```

Constructor injection làm rõ những nguồn biến đổi mà service cần. Nó cũng giúp unit test không phải mock toàn bộ Spring container. Chỉ dùng `@SpringBootTest` hoặc test slice khi mục tiêu là kiểm tra wiring bean, cấu hình hoặc tích hợp giữa các thành phần.

### 5.1. Thay dependency trong Spring integration test

Nếu cần xác nhận Spring wiring với clock cố định, có thể cung cấp bean thay thế trong test context bằng `@TestConfiguration` và `@Primary`:

```java
@SpringBootTest
@Import(FixedTimeTestConfiguration.class)
class SubscriptionIntegrationTest {
    @Autowired
    private SubscriptionService subscriptions;

    @Test
    void recordsTheConfiguredInstant() {
        // Kiểm tra hành vi tích hợp tại mốc thời gian cố định.
    }
}

@TestConfiguration
class FixedTimeTestConfiguration {
    @Bean
    @Primary
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2026-11-12T08:30:00Z"), ZoneOffset.UTC);
    }
}
```

Đây là cách thay bean trong test context. Nếu ứng dụng đã có nhiều bean `Clock`, cần xác định qualifier hoặc chính sách primary rõ ràng để tránh injection mơ hồ. Không nên thay toàn bộ context chỉ để kiểm tra một phép tính thời gian đơn giản; unit test với `Clock.fixed` thường gọn hơn.

Với ID generator hoặc token generator, có thể cung cấp test bean `@Primary` tương tự. Đảm bảo test context không vô tình đưa fake cố định vào profile production. Test configuration nên nằm trong source test và được import rõ ràng.

## 6. Kiểm tra ngày hết hạn, retry và dữ liệu được tạo

Khi đã kiểm soát các nguồn đầu vào, test có thể mô tả những trường hợp biên trực tiếp.

### 6.1. Timestamp và thời hạn

Giả sử service tạo token có thời hạn 15 phút. Test cần xác nhận `expiresAt` được tính từ thời điểm do clock cung cấp:

```java
@Test
void setsTokenExpirationFromInjectedClock() {
    Instant now = Instant.parse("2026-11-12T08:30:00Z");
    Clock clock = Clock.fixed(now, ZoneOffset.UTC);
    TokenService service = new TokenService(clock, Duration.ofMinutes(15));

    Token token = service.issue();

    assertThat(token.createdAt()).isEqualTo(now);
    assertThat(token.expiresAt()).isEqualTo(now.plus(Duration.ofMinutes(15)));
}
```

Test không cần kiểm tra thời điểm hiện tại của máy. Nếu logic có làm tròn xuống đầu ngày hoặc chuyển múi giờ, hãy bổ sung test cho timezone và thời điểm sát ranh giới ngày.

### 6.2. Retry delay và jitter

Jitter giúp phân tán các lần retry để nhiều client không cùng gọi lại dịch vụ ở một thời điểm. Unit test nên kiểm tra công thức và giới hạn của delay bằng nguồn random được kiểm soát:

```java
@Test
void capsRetryJitterAtConfiguredMaximum() {
    RandomIntSource maximumValue = (origin, bound) -> bound - 1;
    RetryDelayPolicy policy = new RetryDelayPolicy(maximumValue);

    Duration delay = policy.nextDelay();

    assertThat(delay).isEqualTo(Duration.ofMillis(500));
}
```

Ngoài giá trị lớn nhất, cần kiểm tra giá trị nhỏ nhất, cách xử lý bound không hợp lệ và cách kết hợp jitter với backoff cơ sở. Không dùng `Thread.sleep(delay)` trong unit test để chờ retry thật; hãy kiểm tra delay được tính hoặc dùng scheduler/clock có thể điều khiển nếu cần kiểm tra việc lên lịch.

### 6.3. ID và event

Nếu service tạo ID rồi phát event, hãy cấp một ID cố định và kiểm tra event chứa đúng ID đó:

```java
UUID expectedId = UUID.fromString(
        "123e4567-e89b-12d3-a456-426614174020");
when(idGenerator.nextId()).thenReturn(expectedId);

service.createOrder(command);

ArgumentCaptor<OrderCreated> captor =
        ArgumentCaptor.forClass(OrderCreated.class);
verify(eventPublisher).publishEvent(captor.capture());
assertThat(captor.getValue().orderId()).isEqualTo(expectedId);
```

Như vậy test xác nhận ID đi qua đúng ranh giới. Không cần kiểm tra UUID có được tạo bằng thuật toán cụ thể nào trong unit test service.

## 7. Kiểm soát dữ liệu ngẫu nhiên trong test fixture

Một số test tạo dữ liệu lớn bằng random để tránh nhập tay nhiều record. Nếu mỗi lần chạy sinh ra dữ liệu khác nhau, lỗi có thể khó tái hiện và khó đọc. Ưu tiên fixture tường minh khi số trường hợp ít:

```java
Customer customer = new Customer(
        "customer-42", "Lan", "lan@example.test", LocalDate.of(1995, 4, 12));
```

Fixture tường minh cho người đọc biết ngay dữ liệu nào có ý nghĩa. Với nhiều trường hợp, có thể dùng builder hoặc factory nhận seed:

```java
final class CustomerFixtureFactory {
    private final Random random;

    CustomerFixtureFactory(long seed) {
        this.random = new Random(seed);
    }

    Customer nextCustomer(int index) {
        int age = 18 + random.nextInt(60);
        return new Customer(
                "customer-" + index,
                "Customer " + index,
                "customer" + index + "@example.test",
                LocalDate.of(2000, 1, 1).minusYears(age));
    }
}
```

Khi test thất bại, seed và index giúp tạo lại cùng chuỗi fixture. Tuy nhiên, dữ liệu random không nên làm mờ điều kiện của test. Nếu đang kiểm tra trường hợp email rỗng, số tiền âm hoặc ngày sát ranh giới, hãy ghi trực tiếp giá trị đó thay vì hy vọng generator tình cờ tạo ra.

Không dùng dữ liệu random để kiểm tra một thuộc tính cần giá trị chính xác nếu test không lưu lại seed và đầu vào. Một test flaky thường khó chẩn đoán hơn test có fixture hơi dài nhưng rõ ràng.

### 7.1. Property-based testing và seed tái hiện lỗi

Property-based testing tạo nhiều đầu vào để kiểm tra một thuộc tính tổng quát, chẳng hạn tổng các phần được phân bổ luôn bằng tổng ban đầu hoặc parser không chấp nhận chuỗi sai định dạng. Đây là tình huống mà random data có thể hữu ích.

Để kết quả có thể kiểm tra lại:

- Chọn framework có cơ chế ghi seed khi test thất bại.
- Giữ lại seed và trường hợp đầu vào gây lỗi trong báo cáo CI.
- Dùng khả năng shrinking nếu framework hỗ trợ để rút gọn đầu vào phức tạp thành ví dụ nhỏ nhất có thể tái hiện.
- Tách property-based test khỏi unit test ví dụ tường minh, để mục tiêu và thời gian chạy được nhận biết rõ.

Seed cố định giúp tái hiện một chuỗi sinh dữ liệu; nó không thay thế việc lưu đầu vào lỗi. Khi framework hỗ trợ replay bằng seed, hãy dùng đúng cơ chế replay mà framework cung cấp.

## 8. Những điều không nên làm

### Không gọi thời gian hệ thống trực tiếp ở nhiều lớp

Nếu service, entity factory và helper đều gọi `Instant.now()` độc lập, test chỉ kiểm soát được một phần. Hãy truyền cùng một `Clock` đến nơi cần thời gian để toàn bộ thao tác dùng chung mốc tham chiếu.

### Không dùng `Thread.sleep` để làm thời gian trôi qua

Sleep làm test chậm và phụ thuộc scheduler của hệ điều hành. Dùng `Clock.fixed`, clock có thể điều khiển hoặc scheduler giả lập để dịch chuyển thời gian mà không phải chờ thực.

### Không so sánh ID ngẫu nhiên với một literal không thể kiểm soát

Nếu ID do service sinh, tiêm generator. Nếu ID do database sinh, kiểm tra nó ở tầng persistence. Không giả định UUID thật sẽ có cùng giá trị qua các lần chạy.

### Không dùng một generator có trạng thái chung cho nhiều test

Nếu một test tiêu thụ vài số random, test tiếp theo có thể nhận chuỗi khác. Tạo generator riêng cho mỗi test hoặc reset bằng seed đã biết. Khi chạy song song, tránh chia sẻ generator mutable nếu implementation không bảo đảm thread safety.

### Không thay randomness bảo mật bằng pseudo-random

Token xác thực, secret và giá trị chống đoán cần nguồn bảo mật như `SecureRandom`. Kiểm soát service bằng cách thay abstraction tạo token trong test, không làm yếu implementation production.

### Không mock quá sâu implementation của JDK

Thay vì mock `Instant.now()` hoặc static method `UUID.randomUUID()`, hãy thiết kế dependency ở ranh giới của ứng dụng: `Clock`, `IdGenerator`, `ResetTokenGenerator` hoặc `RandomIntSource`. Dependency tường minh dễ đọc, ít phụ thuộc công cụ mock static và áp dụng được cả trong production.

## 9. Quy trình áp dụng vào một service

Khi gặp một service có thời gian, ID hoặc randomness, có thể thực hiện theo trình tự sau:

1. Tìm những lời gọi trực tiếp như `now()`, `randomUUID()`, `new Random()` hoặc `ThreadLocalRandom.current()`.
2. Xác định nguồn đó có ảnh hưởng đến quy tắc nghiệp vụ hoặc assertion không.
3. Chọn abstraction nhỏ nhất: `Clock` cho thời gian, `IdGenerator` cho ID, interface chuyên biệt cho token hoặc số random.
4. Tiêm dependency qua constructor; cung cấp implementation mặc định phù hợp cho ứng dụng thật.
5. Trong unit test, dùng giá trị cố định, fake theo chuỗi hoặc seed tường minh.
6. Kiểm tra các trường hợp biên: trước/đúng tại/sau thời hạn, ID được truyền qua đúng nơi, random đạt min/max và các nhánh xử lý tương ứng.
7. Với test Spring integration, thay bean ở test context chỉ khi mục tiêu là kiểm tra wiring hoặc hành vi tích hợp.

Sau khi thay thế, mỗi test nên tự tạo nguồn thời gian, ID và random riêng. Điều này tránh phụ thuộc vào thứ tự test và giúp chạy song song an toàn hơn.

## 10. Bảng chọn công cụ

| Nhu cầu | Production | Unit test |
|---|---|---|
| Thời điểm hiện tại | `Clock.systemUTC()` | `Clock.fixed()` |
| Dịch chuyển thời gian trong test | Không cần trong production | `Clock.offset()` hoặc clock test có thể điều khiển |
| ID UUID do ứng dụng tạo | `UUID.randomUUID()` bên trong `IdGenerator` | Lambda trả UUID cố định hoặc fake theo chuỗi |
| ID do database tạo | Cơ chế ID của database/persistence | Repository integration test |
| Random thông thường | `ThreadLocalRandom` hoặc generator phù hợp với tải | Fake trả giá trị xác định hoặc `Random` với seed cố định |
| Token/secret bảo mật | `SecureRandom` qua abstraction tạo token | Generator giả trả token test cố định |
| Fixture số lượng lớn | Factory có quy tắc dữ liệu rõ ràng | Seed cố định, ghi lại seed/đầu vào lỗi |

## 11. Nguyên tắc cần nhớ

- Thời gian, ID và dữ liệu ngẫu nhiên là các nguồn đầu vào có thể làm unit test khó lặp lại.
- Tiêm `Clock` thay cho việc gọi trực tiếp đồng hồ hệ thống; `Clock.fixed()` giúp kiểm tra chính xác ranh giới thời gian.
- Tiêm `IdGenerator` nếu service sở hữu việc tạo ID; để database test kiểm tra ID do database sinh.
- Dùng fake hoặc seed cố định để kiểm soát random; ưu tiên fixture tường minh khi một vài giá trị cụ thể là đủ.
- Giữ nguồn random bảo mật như `SecureRandom` cho token và secret; không đổi yêu cầu bảo mật chỉ để test thuận tiện.
- Mỗi test nên tự sở hữu nguồn phụ thuộc có trạng thái, không dựa vào việc test khác đã tiêu thụ hoặc reset nó.

Khi các nguồn không xác định được đưa thành dependency, test có thể chọn chính xác thời điểm, ID và giá trị random cần thiết. Điều này giúp kiểm tra logic nghiệp vụ tại các mốc biên, tái hiện lỗi dễ dàng và giữ cho unit test nhanh, ổn định trong mọi môi trường chạy.
