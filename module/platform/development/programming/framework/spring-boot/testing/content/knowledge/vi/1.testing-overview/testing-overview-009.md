# Lộ trình kiểm thử: từ Java thuần đến tích hợp nhiều thành phần trong Spring Boot

## 1. Vì sao cần học theo thứ tự này?

Một ứng dụng Spring Boot có nhiều lớp trách nhiệm: quy tắc nghiệp vụ, service điều phối, HTTP controller, ánh xạ JSON, bảo mật, cấu hình Spring, truy cập cơ sở dữ liệu và đôi khi là API hoặc message broker bên ngoài. Không có một loại test nào kiểm tra hiệu quả tất cả trách nhiệm ấy. Cách học hợp lý là **bắt đầu từ hành vi nhỏ nhất có thể xác minh độc lập**, sau đó chủ động mở rộng ranh giới test khi cần bằng chứng về sự phối hợp.

Mô hình tư duy:

```text
Quy tắc Java thuần
    ↓ thêm cộng tác viên giả lập
Service + mock/fake (vẫn không khởi động Spring)
    ↓ thêm một phần hạ tầng Spring
Web slice / persistence slice
    ↓ ghép các bean và lớp ứng dụng thực
@SpringBootTest + MockMvc + cơ sở dữ liệu
    ↓ ghép thêm môi trường triển khai và phụ thuộc thật
HTTP trên cổng thực + database/container + các hệ thống liên quan
```

“Lớn hơn” không đồng nghĩa “tốt hơn”. Test nhỏ thường nhanh, ít nhiễu, chỉ ra lỗi gần nguyên nhân; test tích hợp rộng phát hiện lỗi kết nối mà unit test không thể thấy. Bộ kiểm thử tốt kết hợp cả hai theo rủi ro của hệ thống.

| Mức | Đối tượng và ranh giới | Spring context | Bằng chứng chính | Không chứng minh được |
| --- | --- | --- | --- | --- |
| 1. Unit Java thuần | Hàm, quy tắc, đối tượng miền | Không | Logic, biên dữ liệu, ngoại lệ | Dependency injection, HTTP, SQL |
| 2. Unit với mock/fake | Service và các cổng phụ thuộc giả | Không | Quyết định của service, lời gọi cộng tác viên | Hợp đồng thực giữa các bean, DB |
| 3. Slice | Một phần web, JPA, JSON... | Có, chỉ phần cần thiết | Mapping, validation, serialization, query/mapping JPA | Toàn luồng ứng dụng |
| 4. Tích hợp ứng dụng | Controller → service → repository → DB | Có, gần/toàn bộ | Cấu hình bean và dữ liệu đi xuyên lớp | Tương tác thật với dịch vụ chưa nối |
| 5. Tích hợp hạ tầng/luồng | HTTP thật, DB/container, hàng đợi hoặc API giả lập có giao thức | Có và hạ tầng liên quan | Cấu hình môi trường, giao thức, giao dịch, lỗi kết nối | Mọi vấn đề của production |

**Câu hỏi quyết định loại test:** “Nếu lỗi này xảy ra, lớp nhỏ nhất nào đủ tái hiện và chứng minh nó?” Chỉ mở rộng phạm vi khi ranh giới mới có hành vi cần xác minh.

## 2. Chuẩn bị tối thiểu trước khi viết test

Với Java 17+ và dự án Spring Boot có JUnit Jupiter, Mockito và các thư viện test từ bộ phụ thuộc phù hợp của phiên bản Spring Boot đang dùng, đặt mã nguồn theo cấu trúc quen thuộc:

```text
src/
├── main/java/example/
│   ├── ShippingFee.java
│   └── CheckoutService.java
└── test/java/example/
    ├── ShippingFeeTest.java
    └── CheckoutServiceTest.java
```

Trong dự án Gradle dùng Spring Boot 3.x, cấu hình phổ biến là:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là đoạn cấu hình minh họa, thêm vào build hiện có nếu dự án chưa khai báo tương đương; không tự tạo hai khối `dependencies` hoặc `test` trùng lặp. Với Spring Boot 4.x, các starter test theo chức năng có thể tách riêng; kiểm tra dependency và package annotation theo phiên bản thực tế.

Chạy test bằng Gradle Wrapper của chính dự án:

```bash
./gradlew test
./gradlew test --tests example.ShippingFeeTest
```

Trên Windows PowerShell, dùng `.\gradlew.bat test` hoặc `.\gradlew.bat test --tests example.ShippingFeeTest`. Các lệnh trên giả định dự án đã cấu hình JUnit Platform và dependency; không cần khởi động ứng dụng Spring Boot để chạy hai bài unit test đầu tiên. Với Maven, lệnh phổ biến là `mvn test` nếu build đã cấu hình test engine tương ứng.

Mỗi test nên theo cấu trúc **Arrange – Act – Assert**: chuẩn bị dữ liệu, thực hiện một hành vi, kiểm tra một kết quả có ý nghĩa. Tên test mô tả quy tắc, ví dụ `freeShippingAtThreshold` thay vì `test1`.

## 3. Chặng 1 — Unit test hoàn toàn không có Spring

Giả sử phí vận chuyển là 30.000 đồng nếu tổng đơn hàng dưới 500.000 đồng, miễn phí từ 500.000 đồng; tổng âm không hợp lệ. Đây là quy tắc thuần, không cần bean, database hay mock.

**Tệp `src/main/java/example/ShippingFee.java`:**

```java
package example;

public final class ShippingFee {
    private ShippingFee() {}

    public static long forSubtotal(long subtotal) {
        if (subtotal < 0) {
            throw new IllegalArgumentException("subtotal must be non-negative");
        }
        return subtotal >= 500_000L ? 0L : 30_000L;
    }
}
```

**Tệp `src/test/java/example/ShippingFeeTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingFeeTest {
    @ParameterizedTest
    @CsvSource({
        "0, 30000",
        "499999, 30000",
        "500000, 0",
        "800000, 0"
    })
    void calculatesFeeAtBoundaries(long subtotal, long expectedFee) {
        assertEquals(expectedFee, ShippingFee.forSubtotal(subtotal));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> ShippingFee.forSubtotal(-1L));
    }
}
```

Hai tệp này có thể biên dịch và chạy trong dự án đã khai báo JUnit Jupiter. Riêng `ShippingFee.java` có thể biên dịch bằng `javac src/main/java/example/ShippingFee.java`; tệp test cần JUnit trên test classpath nên hãy dùng build tool. Không có stdout nghiệp vụ: test thành công được runner báo là **passed**, số liệu/thông điệp cụ thể phụ thuộc Gradle và phiên bản.

Điểm học được:

- Kiểm tra **phân vùng tương đương** và **giá trị biên** (499.999 và 500.000) thay vì chỉ một đầu vào “đẹp”.
- Xác minh cả đường đi hợp lệ và ngoại lệ, không khởi động `ApplicationContext`.
- Không gắn `@SpringBootTest` vào một quy tắc Java thuần: nó tăng thời gian và nguồn gây lỗi mà không thêm bằng chứng.
- Quy tắc về tiền ở đây dùng `long` với đơn vị đồng nguyên; khi có số lẻ hoặc nhiều tiền tệ, chọn mô hình tiền tệ/`BigDecimal` và cách làm tròn được quy định, không mặc định dùng `double`.

**Điều kiện qua chặng:** bạn chỉ được từng test nào phát hiện thay đổi ở ngưỡng 500.000, chỉ ra lý do không cần Spring và thêm được một ca biên mới.

## 4. Chặng 2 — Unit test service với Mockito, vẫn không cần Spring

Service thường phải quyết định **khi nào** gọi các phụ thuộc. Ví dụ checkout gọi cổng thanh toán rồi lưu mã biên nhận. Ta kiểm tra quyết định điều phối bằng các cộng tác viên giả, không thực hiện thanh toán hoặc ghi database.

**Tệp `src/main/java/example/CheckoutService.java`:**

```java
package example;

import java.util.Objects;

public final class CheckoutService {
    public interface PaymentGateway {
        String charge(long amount);
    }

    public interface ReceiptStore {
        void save(String receiptId);
    }

    private final PaymentGateway gateway;
    private final ReceiptStore store;

    public CheckoutService(PaymentGateway gateway, ReceiptStore store) {
        this.gateway = Objects.requireNonNull(gateway);
        this.store = Objects.requireNonNull(store);
    }

    public String checkout(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        String receiptId = gateway.charge(amount);
        store.save(receiptId);
        return receiptId;
    }
}
```

**Tệp `src/test/java/example/CheckoutServiceTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class CheckoutServiceTest {
    @Test
    void chargesThenStoresReceipt() {
        var gateway = mock(CheckoutService.PaymentGateway.class);
        var store = mock(CheckoutService.ReceiptStore.class);
        when(gateway.charge(120_000L)).thenReturn("pay-42");

        var service = new CheckoutService(gateway, store);
        String result = service.checkout(120_000L);

        assertEquals("pay-42", result);
        verify(gateway).charge(120_000L);
        verify(store).save("pay-42");
    }

    @Test
    void invalidAmountDoesNotTouchDependencies() {
        var gateway = mock(CheckoutService.PaymentGateway.class);
        var store = mock(CheckoutService.ReceiptStore.class);
        var service = new CheckoutService(gateway, store);

        assertThrows(IllegalArgumentException.class,
                () -> service.checkout(0L));
        verifyNoInteractions(gateway, store);
    }
}
```

Mockito tạo giả lập và ghi nhận tương tác; đối tượng `CheckoutService` vẫn được tạo bằng `new`. Test này xác minh rằng service trả về đúng mã, truyền đúng số tiền và không gọi phụ thuộc khi đầu vào sai. Nó **không** xác minh rằng database nhận được một hàng, HTTP trả mã 201, cổng thanh toán thật hoạt động hay Spring wiring đúng.

Phân biệt công cụ:

- **Stub** trả dữ liệu đã định; **mock** thường còn để xác minh tương tác.
- **Fake** là hiện thực giản lược có hành vi, ví dụ kho biên nhận trong `Map`. Fake hữu ích khi muốn kiểm tra trạng thái thay vì số lần gọi.
- Hãy mock các **ranh giới do mình kiểm soát** (cổng thanh toán, đồng hồ, gateway) và kiểm tra kết quả quan sát được. Tránh mock mọi đối tượng giá trị, DTO, collection hoặc từng phương thức nội bộ.
- Với một chuỗi phụ thuộc dài, test chỉ xác minh `verify(...)` chưa chắc phản ánh kết quả nghiệp vụ; ưu tiên assert đầu ra/trạng thái trước, verify lời gọi quan trọng sau.

**Điều kiện qua chặng:** test chạy mà không có Spring; bạn giải thích được phụ thuộc nào giả, loại lỗi nào có thể phát hiện và vì sao vẫn cần test với adapter thật.

## 5. Chặng 3 — Thêm Spring có chọn lọc: test slice

**Slice test** tải một lát cắt của Spring context để kiểm tra hành vi framework tại ranh giới cụ thể, thường nhanh và dễ chẩn đoán hơn chạy toàn ứng dụng. Slice không phải “unit test thuần”: nó có Spring, nhưng cố tình không tải tất cả bean.

### 5.1. Lát cắt HTTP với `@WebMvcTest`

Giả sử khi ghép ứng dụng, `CheckoutController` nhận `POST /checkout?amount=120000` và gọi `CheckoutService`. Controller minh họa:

```java
@RestController
@RequestMapping("/checkout")
class CheckoutController {
    private final CheckoutService service;

    CheckoutController(CheckoutService service) {
        this.service = service;
    }

    @PostMapping
    ResponseEntity<Map<String, String>> create(@RequestParam long amount) {
        String id = service.checkout(amount);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("receiptId", id));
    }
}
```

Test MVC slice minh họa cho Spring Boot 3.4+ với Spring Framework 6.2+ (cần thêm imports tương ứng):

```java
@WebMvcTest(CheckoutController.class)
class CheckoutControllerWebTest {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    CheckoutService service;

    @Test
    void returns201AndReceiptId() throws Exception {
        when(service.checkout(120_000L)).thenReturn("pay-42");

        mvc.perform(post("/checkout").param("amount", "120000"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.receiptId").value("pay-42"));
    }
}
```

Ở đây `MockMvc` đi qua hệ thống xử lý request MVC, mapping và chuyển response của Spring, **không mở HTTP server thật**; `CheckoutService` là mock bean. Cần import static `post`, `status`, `jsonPath` từ Spring MockMvc, `when` từ Mockito cùng các annotation đúng package.

**Lưu ý phiên bản:** trong Spring Boot 3.3 và cũ hơn, cách phổ biến là `@MockBean` của Spring Boot; Spring Framework 6.2+ có `@MockitoBean` và Spring Boot mới ưu tiên cơ chế này. Spring Boot 4.x thay đổi một số package/dependency test theo module; đối chiếu phiên bản dự án trước khi sao chép imports. Nếu Spring Security filter được bật trong slice, request cần danh tính/CSRF phù hợp; lỗi 401/403 có thể là chính sách security chứ không phải mapping.

Một MVC slice kiểm tra route, status, body, JSON, validation, xử lý lỗi (ví dụ `@ControllerAdvice`) và filter được cấu hình; không chứng minh logic service thật hay dữ liệu JPA.

### 5.2. Lát cắt persistence với `@DataJpaTest`

Dùng `@DataJpaTest` khi muốn kiểm tra mapping entity, repository, câu query, constraint và tương tác JPA. Ví dụ sau **chỉ là trích đoạn**: dự án cần sẵn `ReceiptEntity` với constructor tương ứng và `ReceiptJpaRepository` với `findByGatewayId`.

```java
@DataJpaTest
class ReceiptJpaRepositoryTest {
    @Autowired
    ReceiptJpaRepository repository;

    @Test
    void canFindPersistedReceipt() {
        repository.saveAndFlush(new ReceiptEntity("pay-42"));

        assertThat(repository.findByGatewayId("pay-42"))
                .isPresent();
    }
}
```

Phần lớn cấu hình `@DataJpaTest` mặc định dùng database nhúng khi có driver thích hợp, test có transaction và rollback sau mỗi test. Tùy dự án, chọn database thật hoặc Testcontainers để kiểm tra tính tương thích SQL, migration, constraint và cách database sản xuất xử lý dữ liệu. H2 không luôn tái hiện đúng hành vi PostgreSQL/MySQL (kiểu dữ liệu, cú pháp, transaction, index).

Chọn slice theo ranh giới:

| Muốn xác minh | Điểm bắt đầu |
| --- | --- |
| Route, status, JSON/validation trong Servlet MVC | `@WebMvcTest` + `MockMvc` |
| Entity, repository, JPA query | `@DataJpaTest` |
| Reactive WebFlux HTTP handling | `@WebFluxTest` + `WebTestClient` |
| Cấu hình JSON riêng | JSON test slice phù hợp phiên bản |
| Chỉ một hàm hoặc service điều phối | JUnit/Mockito thuần, chưa cần slice |

Các slice khác nhau không tự ghép với nhau thành full integration test. Nếu lỗi chỉ xuất hiện khi service, repository, transaction và controller cùng chạy, hãy mở rộng ranh giới.

**Điều kiện qua chặng:** bạn chỉ ra được một điều MVC slice bảo đảm, một điều JPA slice bảo đảm và ít nhất một điều chúng không thể bảo đảm khi chạy riêng.

## 6. Chặng 4 — Tích hợp nhiều lớp thật trong cùng ứng dụng

Đến đây, ta muốn kiểm tra một luồng: **request → controller → service → adapter lưu trữ → JPA repository → database**. Đây là điểm phù hợp để dùng `@SpringBootTest`; nó dựng application context gần với ứng dụng thực. Có thể dùng `@AutoConfigureMockMvc` để kiểm tra luồng MVC mà không cần mở TCP port.

Để ví dụ nối được các chặng, ứng dụng cần cung cấp bean thật cho `CheckoutService` và `ReceiptStore` (adapter của `ReceiptJpaRepository`), còn `PaymentGateway` là cổng có thể thay bằng mock trong test. Các đoạn controller và repository ở trên là **thành phần minh họa phải được triển khai/ghép trong dự án**, không phải một ứng dụng hoàn chỉnh chỉ bằng cách sao chép riêng test dưới đây.

```java
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class CheckoutFlowIT {
    @Autowired
    MockMvc mvc;

    @Autowired
    ReceiptJpaRepository receipts;

    @MockitoBean
    CheckoutService.PaymentGateway gateway;

    @BeforeEach
    void cleanData() {
        receipts.deleteAll();
    }

    @Test
    void httpCheckoutPersistsReceipt() throws Exception {
        when(gateway.charge(120_000L)).thenReturn("pay-42");

        mvc.perform(post("/checkout").param("amount", "120000"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.receiptId").value("pay-42"));

        assertThat(receipts.findByGatewayId("pay-42"))
                .isPresent();
    }
}
```

Test này có sức mạnh ở **chỗ ghép thật**: nếu thiếu bean, sai cấu hình mapping, lỗi chuyển dữ liệu, repository không lưu hoặc transaction/configuration sai, nó có cơ hội phát hiện. Cổng thanh toán vẫn là mock có chủ đích vì không nên gọi hệ thống thanh toán thật trong CI.

Các quyết định cần nêu rõ:

1. `@SpringBootTest` mặc định dùng `webEnvironment = MOCK`; nó tạo mock web environment nếu là web app, **không khởi động server thật**. `@AutoConfigureMockMvc` thêm công cụ gửi request trong cùng tiến trình.
2. `@SpringBootTest(webEnvironment = RANDOM_PORT)` mới khởi động server HTTP ở cổng ngẫu nhiên; dùng HTTP client phù hợp để kiểm tra đường truyền thật.
3. `@ActiveProfiles("test")` chỉ chọn profile; nó không tự bảo đảm DB test, credentials hay dịch vụ ngoài đã được cách ly. Cần cấu hình datasource, secrets giả, endpoint test và tài nguyên phù hợp.
4. Khi đặt `@Transactional` lên Spring test, transaction ở luồng test thường rollback sau test; với `RANDOM_PORT`, client/server chạy ở các thread và transaction khác nhau nên **rollback của test không tự rollback dữ liệu server đã commit**.
5. Lựa chọn dọn dữ liệu phải phù hợp mức test: rollback, transaction riêng, truncate/schema riêng, dữ liệu duy nhất hoặc container cô lập. Không dựa vào thứ tự chạy test.
6. Nếu có Spring Security, test cả quyền được phép và bị từ chối; không tắt filter chỉ để làm xanh bài kiểm tra vốn được thiết kế để xác minh security.

**Điều kiện qua chặng:** bạn có ít nhất một test chứng minh kết quả quan sát được ở hai lớp thật (ví dụ HTTP 201 **và** biên nhận lưu trong DB), đồng thời xác định rõ phần phụ thuộc đang giả lập.

## 7. Chặng 5 — Gắn phụ thuộc thật và kiểm tra giao thức/môi trường

Khi rủi ro nằm ở khác biệt giữa môi trường và bản giả, mở rộng test tới thành phần hạ tầng. Ví dụ: service kết nối PostgreSQL thật, migration chạy khi khởi động, query dùng kiểu JSONB, Redis cache, Kafka publish/consume, HTTP client có timeout/retry.

**Testcontainers** giúp cấp phát database/broker trong container cho test. Với Spring Boot có hỗ trợ service connection, một skeleton PostgreSQL là:

```java
@Testcontainers
@SpringBootTest
@AutoConfigureMockMvc
class CheckoutPostgresIT {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // @Autowired MockMvc, repository và các @Test tương tự luồng ở chặng 4.
}
```

Đây là **skeleton minh họa**, không phải tệp test độc lập: cần dependencies Testcontainers/JUnit integration, PostgreSQL driver, hỗ trợ Spring Boot Testcontainers, Docker/container runtime và lớp ứng dụng thích hợp. `@ServiceConnection` có thể cung cấp connection details cho auto-configuration; khi tích hợp công nghệ/phiên bản chưa hỗ trợ cơ chế này, `@DynamicPropertySource` là một cách cấu hình động khác. Kiểm tra imports chính xác trong phiên bản đang sử dụng.

Phân chia việc gì nên thật, việc gì nên giả:

- **Database thật qua container:** phù hợp với truy vấn đặc thù, migration, schema/constraint, isolation và transaction.
- **HTTP service ngoài:** ưu tiên mock server/WireMock chạy với HTTP thật để xác minh URL, method, headers, payload, mã lỗi, timeout và retry; không gọi API bên thứ ba hay production ngoài ý muốn.
- **Message broker thật qua container:** phù hợp khi cần chứng minh serialization, topic/queue, consumer group, retry/DLQ và tính bất đồng bộ; mock publisher đơn thuần chỉ chứng minh lời gọi.
- **HTTP server thật:** dùng `RANDOM_PORT` khi cần kiểm tra socket, filter container, cookie, redirect, network serialization; `MockMvc` đủ cho phần lớn hợp đồng MVC nội bộ.
- **End-to-end giao diện/người dùng:** chỉ thêm khi cần xác minh tương tác qua UI hoặc chuỗi dịch vụ triển khai; số lượng thường ít vì chạy chậm và dễ nhiễu.

Ví dụ bài kiểm tra toàn luồng checkout có thể phát hiện các lỗi mà từng unit test không thấy: JSON đầu vào không bind được, transaction không commit, repository lưu sai currency/id, migration thiếu index/constraint, cổng HTTP gửi header sai, hoặc consumer đọc message khác schema.

## 8. Thứ tự thực hành đề xuất

Hãy dùng **một câu chuyện nghiệp vụ xuyên suốt**, bổ sung hạ tầng từng chặng để nhìn rõ khi nào một lỗi xuất hiện. Với tình huống checkout:

| Bước | Việc làm | Tiêu chí hoàn thành |
| --- | --- | --- |
| 1 | Viết test cho tính phí vận chuyển ở các giá trị biên | Test chạy không cần Spring; thay sai ngưỡng thì test đỏ |
| 2 | Test checkout service với mock payment/store | Chứng minh đúng số tiền, mã nhận và không gọi ngoài khi đầu vào sai |
| 3 | Tạo MVC slice cho endpoint checkout | Chứng minh request, response, validation và status 4xx/2xx |
| 4 | Tạo JPA slice cho biên nhận | Ghi/đọc thật, phát hiện lỗi mapping hoặc query |
| 5 | Ghép `@SpringBootTest` + `MockMvc` + DB test | Một request đi qua controller, service, repository và xác nhận DB |
| 6 | Thay DB test bằng PostgreSQL Testcontainers | Phát hiện khác biệt SQL/schema/migration với DB thực |
| 7 | Kiểm tra HTTP outbound/broker và một luồng lỗi có chủ đích | Xác minh giao thức, timeout/retry hoặc event propagation |

Không nhất thiết mọi dự án cần cả bảy bước. Một library xử lý thuật toán có thể tập trung bước 1–2; service có database và tích hợp ngoài cần nhiều hơn ở 4–7. Chọn theo **hậu quả khi lỗi lọt qua**, không đặt chỉ tiêu “tất cả test đều phải chạy Spring”.

### Thực hành thêm: cùng một bug, ba nơi bắt

Giả sử gửi amount = 0 làm hệ thống vẫn tạo thanh toán.

1. Unit test `CheckoutServiceTest` đỏ nếu service không chặn amount ≤ 0.
2. MVC slice có thể đỏ nếu API phải từ chối 400 nhưng controller thiếu validation/exception mapping. Chỉ mock service trả bình thường sẽ không tự chứng minh quy tắc domain.
3. Full integration test có thể chứng minh request 400 **và** database không tăng số biên nhận; đây là bằng chứng bảo vệ dữ liệu toàn luồng.

Ba lớp này trả lời ba câu hỏi khác nhau. Đừng coi ba bài test giống hệt nhau là cần thiết; hãy chọn assertion đặc trưng cho từng ranh giới.

## 9. Mẹo để test nhanh, đáng tin và có giá trị

### Thiết kế dữ liệu và cô lập

- Tạo dữ liệu tối thiểu cần cho từng test bằng factory/builder rõ nghĩa. Tránh fixture chung có quá nhiều mặc định ẩn.
- Mỗi test có thể chạy độc lập và theo thứ tự bất kỳ; không để test A chuẩn bị dữ liệu cho test B.
- Cố định thời gian bằng `Clock` được tiêm vào service; tránh phụ thuộc `LocalDateTime.now()`, timezone hoặc thời điểm CI.
- Dùng id duy nhất, transaction rollback đúng chỗ hoặc dọn database theo ranh giới; không dùng chung DB production.
- Với hệ bất đồng bộ, chờ theo điều kiện có giới hạn thời gian (polling/Awaitility), không dùng `Thread.sleep` cố định để đoán lúc message đã xử lý.
- Đặt timeout hợp lý cho HTTP/DB; giả lập lỗi mạng và xác minh hành vi retry/idempotency nếu nghiệp vụ yêu cầu.
- Nếu test phụ thuộc Testcontainers, đánh dấu rõ yêu cầu Docker/runtime trong hướng dẫn chạy CI.

### Hiệu năng và cấu trúc suite

- Giữ unit test thuần làm tuyến phản hồi nhanh khi lập trình; gom integration test nặng theo pipeline/hồ sơ thực thi phù hợp.
- Spring TestContext có cơ chế cache context; cấu hình/profile/mock khác nhau có thể làm tăng số context phải tải. Đừng dùng `@DirtiesContext` khi không thực sự cần reset context.
- Dùng `@SpringBootTest` khi phải chứng minh tương tác nhiều bean; dùng slice khi đủ chứng minh hợp đồng web/JPA; dùng plain JUnit khi chỉ cần logic.
- Nếu tách nhiệm vụ `integrationTest` trong Gradle thì cần cấu hình source set/test suite tương ứng; lệnh `./gradlew integrationTest` không phải task mặc định được bảo đảm trong mọi dự án.

### Lỗi thường gặp và cách sửa đúng tầng

| Hiện tượng | Nguyên nhân thường gặp | Cách xác minh/sửa |
| --- | --- | --- |
| Unit test nhỏ khởi động rất lâu | Gắn `@SpringBootTest` không cần thiết | Bỏ context, tạo đối tượng bằng `new` |
| MVC slice lỗi không tìm được service bean | Slice không quét service thông thường | Cấp mock hoặc test configuration đúng ranh giới |
| Test service pass nhưng REST trả 404/400 | Mock chỉ xác minh service, không kiểm tra MVC mapping/binding | Thêm `@WebMvcTest` |
| JPA test pass trên H2 nhưng production fail | Dialect/schema/transaction khác DB thật | Testcontainers với loại DB tương đương |
| Integration test bất định khi chạy theo nhóm | State tồn dư, dữ liệu trùng, phụ thuộc thời gian/thứ tự | Cô lập dữ liệu và nguồn thời gian |
| `@Transactional` vẫn để lại dữ liệu sau HTTP thật | Server transaction khác transaction ở test thread | Dọn DB rõ ràng hoặc cô lập schema/container |
| Request nhận 401/403 | Security filter, authentication hoặc CSRF | Thiết lập security test đúng chính sách, kiểm tra expected status |
| Test verify mock pass nhưng dữ liệu sai | Chỉ assert lời gọi, thiếu kết quả quan sát được | Assert response, trạng thái hoặc record thực |

Đừng nhầm **coverage cao** với **bằng chứng đủ**: coverage chỉ cho biết đoạn mã được chạy, không bảo đảm assertion kiểm tra đúng quy tắc. Khi fix một bug, ưu tiên bổ sung test có khả năng tái hiện bug trước khi sửa, rồi giữ test đó chống hồi quy.

## 10. Bản đồ chọn test và checklist tự đánh giá

```text
Muốn kiểm tra một quy tắc thuần?
  └─ Có → JUnit thuần, bảng giá trị biên.
  └─ Không: service có phụ thuộc?
       └─ Có, chỉ cần quyết định của service → JUnit + mock/fake.
       └─ Cần xác minh framework (HTTP/JPA)?
            └─ Một lát cắt → @WebMvcTest / @DataJpaTest.
            └─ Nhiều lớp trong một request → @SpringBootTest + MockMvc.
                 └─ Cần giao thức/DB/mạng thật → RANDOM_PORT / Testcontainers /
                    mock server / broker theo đúng rủi ro.
```

Trước khi coi một cấp học đã hoàn thành, tự trả lời:

- Test đang xác minh **hành vi nào** và assertion nào chứng minh hành vi ấy?
- Những lớp/thành phần nào **thực**, lớp nào là mock/fake? Có vô tình mock mất chính thứ cần kiểm tra không?
- Lỗi được phát hiện có thuộc ranh giới test hiện tại không, hay nên thêm một slice/integration test?
- Dữ liệu, thời gian, network, profile, secrets và thứ tự chạy đã được cô lập đủ để chạy lại ở CI?
- Nếu test xanh nhưng production sai, **khoảng trống bằng chứng** còn lại là gì?
- Một bài tích hợp nặng đang phát hiện lỗi phối hợp riêng có, hay chỉ lặp lại unit test đã đủ?

**Kết quả cần đạt:** học viên có thể bắt đầu từ kiểm thử Java không cần Spring, chủ động thêm Mockito để cô lập dependency, chọn đúng slice để kiểm tra adapter/framework, sau đó dựng luồng nhiều lớp và mở rộng đến database/giao thức thật khi rủi ro yêu cầu. Giá trị của lộ trình nằm ở việc **biết vì sao phải mở rộng ranh giới test**, đồng thời giữ những bài test đơn giản nhất có thể.

## Tài liệu chính thức để đối chiếu theo phiên bản

- Spring Boot — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Spring Boot — Testcontainers: https://docs.spring.io/spring-boot/reference/testing/testcontainers.html
- Spring Framework — Mockito bean overrides: https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html
- JUnit User Guide: https://docs.junit.org/current/user-guide/
- Testcontainers Java: https://java.testcontainers.org/
