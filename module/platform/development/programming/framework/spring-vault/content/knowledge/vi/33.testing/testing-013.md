# Kiểm thử nhiều yêu cầu đồng thời và vòng đời ApplicationContext

## 1. Vì sao cần kiểm thử cả concurrency lẫn lifecycle?

Trong **Spring Vault**, ứng dụng Java giao tiếp với HashiCorp Vault qua `VaultTemplate` (giao diện `VaultOperations`), xác thực bằng danh tính workload và tuân theo Vault policy. Một dịch vụ thực tế có thể xử lý hàng trăm request cùng lúc, trong khi token đang được làm mới, dynamic secret có lease đang được renew/rotate, hoặc Spring Boot đang khởi động/đóng `ApplicationContext`.

Kiểm thử một lời gọi `vaultOperations.read(...)` thành công **không đủ** trả lời các câu hỏi sau:

- Nhiều thread dùng **cùng một** `VaultTemplate` có trả đúng secret, không trộn state của request/tenant?
- Khi token hết hạn và nhiều thread đồng thời gọi Vault, session manager có thực hiện login/renew một cách kiểm soát?
- Cache ứng dụng có chống **cache stampede** khi nhiều request chạm cùng secret vừa hết hạn?
- Một context đã đóng có hủy scheduler/lease listeners, session token và tài nguyên do nó sở hữu hay không?
- Spring TestContext có tái sử dụng context giữa hai test, khiến trạng thái singleton hoặc token của test trước ảnh hưởng test sau?
- Khi đóng context giữa lúc các request còn chạy, hệ thống có ngừng nhận việc mới và kết thúc tác vụ đang chạy theo quy tắc rõ ràng không?

Chủ đề **“Kiểm thử nhiều yêu cầu đồng thời và vòng đời ApplicationContext”** thuộc chương **Kiểm thử** kết hợp hai trục độc lập: tính đúng đắn khi **nhiều request đồng thời**, và tính đúng đắn theo **thứ tự khởi tạo → chạy → đóng**. Các ví dụ áp dụng cho KV v2, token/lease, Transit, PKI cùng các vấn đề xử lý lỗi và giám sát trong phạm vi Spring Vault.

Sau bài này, bạn sẽ biết:

1. Thiết kế ma trận concurrent/lifecycle test phân biệt unit test, integration test và stress test.
2. Sử dụng `ExecutorService`, `CountDownLatch` và `Future.get(timeout, ...)` để tạo concurrency có kiểm soát.
3. Dùng Testcontainers Vault để kiểm thử thật mà không cần Vault production.
4. Kiểm tra đồng bộ cache, session/token refresh và những API không idempotent.
5. Quan sát Spring `SmartLifecycle`, `DisposableBean`, `ContextClosedEvent`, `@DirtiesContext` và context cache.
6. Phát hiện race condition, rò rỉ thread/lease/token, flakiness và bí mật vô tình đi vào log.

> **Ranh giới thực hành:** Tất cả token/secret trong ví dụ là giá trị thử nghiệm ở Vault dev container cô lập. Không thực hiện seal/unseal, tạo token root, revoke lease hoặc load test trên cluster Vault được chia sẻ với production.

## 2. Nắm kiến trúc trước khi chạy nhiều thread

~~~mermaid
flowchart TD
    A[Spring ApplicationContext] --> B[VaultTemplate / VaultOperations]
    A --> C[SessionManager]
    A --> D[SecretLeaseContainer nếu được khai báo]
    C --> E[ClientAuthentication / Workload Identity]
    D --> F[TaskScheduler + lease listeners]
    B --> C
    B --> G[HTTP Client + Connection Pool]
    B --> H[KV / Transit / PKI]
    A --> I[Ứng dụng: cache, pool, readiness]
    J[Concurrent request threads] --> B
    J --> I
~~~

Theo tài liệu Spring Vault, `VaultTemplate` **thread-safe sau khi được cấu hình** và có thể được chia sẻ như một singleton. Điều đó **không tự bảo đảm** mọi thành phần bạn tự viết xung quanh đều thread-safe:

| Thành phần | Điều có thể được bảo đảm | Điều vẫn phải kiểm thử |
| --- | --- | --- |
| `VaultTemplate` đã cấu hình | Có thể dùng lại giữa nhiều thread | HTTP timeout, kết nối, context auth, kết quả từng request |
| `LifecycleAwareSessionManager` | Đồng bộ các thread lấy token lúc cần login; quản lý renew theo token | Cấu hình thực, loại token, retry khi auth hỏng, shutdown |
| `SecretLeaseContainer` | Quản lý lease/rotation, hỗ trợ lifecycle và đa luồng sau khi initialized | Listener, consumer đổi credentials, việc stop/destroy, tác động lên lease |
| HTTP client/connection pool | Tùy implementation và cấu hình | Giới hạn pool, connection leak, timeout, TLS, đồng thời cao |
| Cache `Map` hoặc holder tự viết | Không có bảo đảm nếu dùng collection không đồng bộ | Đọc/ghi atomic, hết TTL, tải lại cùng lúc, memory visibility |
| Bean dùng `@RequestScope`/tenant context | Phụ thuộc phạm vi bean | Tránh chia sẻ token/path giữa tenant hoặc thread |

Đừng biến một thread-safe client thành nhiều instance theo mỗi request chỉ để tránh lỗi tự viết. Làm vậy có thể tăng số kết nối, số token đăng nhập, scheduler và chi phí tài nguyên.

### 2.1. Hai loại race condition khác nhau

**Race ở phía client:** hai thread cùng thấy cache đã hết hạn rồi gọi Vault cùng lúc; một listener rotate credentials thay đổi pool trong khi request đang dùng; singleton mutable lưu `currentTenantPath` và bị thread khác ghi đè.

**Race do vòng đời Vault:** token bị renew/revoke gần cùng thời điểm, lease expired, hoặc node leader thay đổi; request gửi đi chưa chắc đã được xử lý khi client timeout. Những lỗi này không sửa được chỉ bằng `synchronized` trên business service.

### 2.2. Sơ đồ vòng đời cần kiểm thử

~~~mermaid
sequenceDiagram
    participant Spring as ApplicationContext
    participant Session as SessionManager
    participant Lease as SecretLeaseContainer
    participant Vault as Vault test container
    Spring->>Session: Khởi tạo bean/session config
    Spring->>Lease: afterPropertiesSet / start
    Lease->>Vault: Lấy secret có lease nếu đã đăng ký
    Note over Spring,Vault: Context hoạt động, nhiều request đồng thời
    Spring->>Session: Lấy session token khi request cần
    Session->>Vault: Login / renew theo auth strategy
    Spring->>Lease: Context close -> stop/destroy
    Lease->>Vault: Dừng renew; destroy có thể revoke lease
    Spring->>Session: destroy -> dừng refresh / revoke token khi áp dụng
~~~

Sơ đồ thể hiện **trách nhiệm** chứ không phải cam kết thứ tự callback cố định giữa mọi bean. Thứ tự đóng thực tế phụ thuộc quan hệ dependency, `SmartLifecycle` phase, scheduler và cách khai báo bean.

## 3. Ma trận kiểm thử tối thiểu

| Trục kiểm thử | Điều kiện | Assertion chính |
| --- | --- | --- |
| KV đọc cùng lúc | 32–100 lời gọi vào cùng path | Tất cả đọc đúng, không lỗi đồng thời, không lộ token |
| Nhiều tenant | Thread A đọc path A, B đọc path B theo quyền hợp lệ | Không trả nhầm dữ liệu giữa tenant |
| Cache cold start | N request cùng chạm một cache key | Một lần load nếu contract yêu cầu single-flight |
| Token login đồng thời | N thread gọi Vault khi session chưa có token | Số login có giới hạn theo SessionManager thực |
| Token renew/fail | Token gần hết hạn, Vault trả auth lỗi tạm thời | Re-login/renew theo policy, không tạo vòng lặp |
| KV write xung đột | Hai writer cùng sửa cùng key | CAS/versioning bảo đảm không ghi đè im lặng |
| PKI/SecretID cấp phát | N yêu cầu thực sự có chủ đích | Mỗi kết quả có identity riêng; không retry mù khi timeout |
| Lease listener | Renew/rotate/expire xảy ra gần lúc đọc | Consumer nhận snapshot hợp lệ, không dùng credential quá hạn |
| Startup | Context vừa tạo, workload identity đúng | Bean sẵn sàng trước khi traffic; không login vô hạn |
| Shutdown | Context close khi không có request | Scheduler/listeners dừng, tài nguyên sở hữu được giải phóng |
| Shutdown khi đang có request | Request đang chờ I/O | Đóng graceful theo deadline; không deadlock |
| TestContext cache | Hai test dùng cùng config | Hiểu được tái sử dụng context; không giả định khởi tạo hai lần |
| Test isolation | Test có sửa singleton/Vault state | Dọn state, dùng context riêng khi thật sự cần |
| Load/performance | Tăng concurrency tới mức dự kiến | p95/p99, timeout, pool saturation, số login và retry phù hợp |

Tách **độ đúng** và **tải**: test 48 tác vụ đồng thời có thể tìm data race, nhưng không phải benchmark throughput. Load test còn cần môi trường riêng, warm-up, số lần chạy, ramp-up và giới hạn tài nguyên.

## 4. Chuẩn bị môi trường integration test với Testcontainers Vault

Sử dụng **Testcontainers for Java** để chạy HashiCorp Vault dev mode trong Docker tại môi trường test. Docker cần hoạt động trong máy/CI. Dependency thường gồm JUnit Jupiter, Spring Vault, Spring Test hoặc Spring Boot Test, Testcontainers `testcontainers-vault` và `junit-jupiter`; các version nên được khóa bằng BOM của dự án thay vì copy một version bất kỳ từ bài.

Ví dụ test container cấp một token root **chỉ dùng trong container test cô lập** và tạo KV v2 tại mount mặc định `secret/`:

~~~java
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.vault.VaultContainer;

import java.net.URI;

import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTemplate;

@Testcontainers
class VaultConcurrentReadIT {

    private static final String TOKEN = "test-only-root-token";
    private static final String PATH = "secret/data/race";

    @Container
    static final VaultContainer<?> VAULT =
            new VaultContainer<>("hashicorp/vault:1.20")
                    .withVaultToken(TOKEN)
                    .withInitCommand(
                            "kv put secret/race value=expected");

    private static VaultOperations operations;

    @BeforeAll
    static void createClient() {
        URI baseUri = URI.create(VAULT.getHttpHostAddress());

        // TokenAuthentication dùng token thử nghiệm cố định;
        // không đo login/renew của workload thực.
        operations = new VaultTemplate(
                VaultEndpoint.from(baseUri),
                new TokenAuthentication(TOKEN));
    }

    // Test chạy đồng thời được trình bày ở phần kế tiếp.
}
~~~

**Các điều kiện sử dụng ví dụ:**

- `VaultContainer` trong test dev mode có token dùng để setup. **Không dùng root token trong ứng dụng thật**; test xác thực/ACL cần tạo workload role/token riêng và kiểm tra `403`.
- `hashicorp/vault:1.20` là một **tag minh họa**, nên khóa theo phiên bản Vault và Testcontainers mà CI hỗ trợ; không dùng tag `latest` cho test tái lập.
- `VaultContainer.getHttpHostAddress()` thường là HTTP vì đây là dev container. **Production phải dùng HTTPS và CA tin cậy.** Không đưa HTTP test endpoint vào application configuration production.
- Lệnh `kv put secret/race ...` chạy khi container khởi động để đặt dữ liệu. Với KV v2, API đọc của Java là `secret/data/race`; nếu mount KV không phải v2 thì phải điều chỉnh setup.
- `VaultTemplate(endpoint, TokenAuthentication)` là cấu hình nhẹ để kiểm tra data operations; nó **không phải** test riêng cho `LifecycleAwareSessionManager`, token rotation hoặc AppRole/Kubernetes auth.
- Với `@SpringBootTest`, có thể dùng `@DynamicPropertySource` hoặc `@ServiceConnection` theo Boot/version để truyền endpoint tới ứng dụng, nhưng cần biết ứng dụng dùng Spring Vault trực tiếp hay Spring Cloud Vault Config Data. Không thay endpoint bằng system property toàn cục giữa các test chạy song song.

### 4.1. Isolation và cleanup

**Không dùng chung cùng một secret path để thực hiện test ghi và test đọc song song** nếu những test đó giả định dữ liệu bất biến. Nếu chạy JUnit parallel mode, hãy dùng path riêng cho từng test hoặc per-class container, hoặc dọn dữ liệu theo thứ tự có kiểm soát.

Testcontainers tự quản lý vòng đời container qua JUnit extension khi dùng `@Container`. Nếu tự `start()` thủ công, phải `stop()` trong `finally` hoặc `@AfterAll`. Tránh đẩy token test vào log hay artifact CI chỉ vì nó không phải production: thói quen logging có thể lan sang môi trường thật.

## 5. Kiểm thử nhiều yêu cầu đồng thời trên cùng `VaultTemplate`

Thêm method test sau vào `VaultConcurrentReadIT` ở mục 4. Sử dụng **một** singleton `operations`, pool 12 worker, 48 tác vụ đọc KV v2, latch cho phép bắt đầu gần như cùng lúc và timeout cho từng `Future`.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.vault.support.VaultResponse;

// Method trong class VaultConcurrentReadIT ở mục 4:
@Test
void readsFromSharedVaultTemplateAreConsistent() throws Exception {

    int tasks = 48;
    ExecutorService pool = Executors.newFixedThreadPool(12);
    CountDownLatch gate = new CountDownLatch(1);
    List<Future<String>> results = new ArrayList<>();

    try {
        for (int i = 0; i < tasks; i++) {
            results.add(pool.submit(() -> {
                gate.await();

                VaultResponse response = operations.read(PATH);
                assertNotNull(response);
                assertNotNull(response.getData());

                // KV v2: response.data.data.value
                Object nested = response.getData().get("data");
                assertInstanceOf(Map.class, nested);

                Map<?, ?> values = (Map<?, ?>) nested;
                return String.valueOf(values.get("value"));
            }));
        }

        gate.countDown();

        for (Future<String> result : results) {
            assertEquals(
                    "expected",
                    result.get(10, TimeUnit.SECONDS));
        }
    } finally {
        pool.shutdownNow();
        assertTrue(
                pool.awaitTermination(5, TimeUnit.SECONDS),
                "Worker pool leaked threads");
    }
}
~~~

**Assertion mà test này thực sự chứng minh:** cùng một instance `VaultOperations` xử lý được nhiều lệnh đọc và tất cả nhận đúng giá trị tại path test; tác vụ kết thúc trong deadline. Test **không chứng minh** hiệu năng ở production, tính an toàn của cache tự viết hay số lần login khi token có TTL, vì đang dùng `TokenAuthentication` cố định.

Các lưu ý về tính xác định:

- Một `CountDownLatch(1)` làm các tác vụ đang có worker chờ chung; với 48 tác vụ và 12 worker, **không có nghĩa 48 request thực sự đồng thời**. Nếu cần đo đúng 48 in-flight requests, phải có 48 worker hoặc thiết kế nonblocking và xác nhận bằng server-side instrumentation.
- Không chỉ đếm số task đã tạo rồi gọi đó là concurrency. Đo thời gian bắt đầu, số in-flight cao nhất và kết quả của từng task.
- `Future.get(timeout, ...)` bảo vệ test khỏi đợi vô hạn ở tầng test, nhưng **không thay thế HTTP connect/read timeout** trên Spring Vault client. `shutdownNow()` không bảo đảm hủy ngay một I/O bị block.
- Để giảm flakiness, chọn timeout rộng hơn mức mà container CI dự kiến và ghi lỗi theo dạng metadata; đừng log nguyên Vault response hay token khi assertion fail.
- Nếu cần đo throughput, chạy benchmark riêng, có warm-up và ghi giới hạn pool/Vault CPU.

## 6. Cache single-flight: thử race ở lớp ứng dụng, không đổ lỗi cho Vault

Một vấn đề quen thuộc: nhiều request thấy cache hết hạn cùng lúc, tất cả tự gọi `vault.read(...)`. `VaultTemplate` vẫn thread-safe, nhưng việc **cache stampede** khiến Vault bị tăng tải và đẩy latency lên cao.

Giả sử một class chịu trách nhiệm tải giá trị một lần:

~~~java
import java.util.Objects;
import java.util.function.Supplier;

public final class LoadOnce<T> {

    private final Supplier<T> loader;
    private volatile T value;

    public LoadOnce(Supplier<T> loader) {
        this.loader = Objects.requireNonNull(loader);
    }

    public T get() {
        T snapshot = value;
        if (snapshot != null) {
            return snapshot;
        }

        synchronized (this) {
            if (value == null) {
                T loaded = Objects.requireNonNull(
                        loader.get(), "Secret loader returned null");
                value = loaded;
            }
            return value;
        }
    }
}
~~~

Đây chỉ là ví dụ **load-once**, không có TTL/rotation. Dùng nó cho KV tĩnh trong bài test; **không** dùng vô hạn cho credentials có lease, certificate sắp hết hạn hoặc secret cần cập nhật.

Test concurrent để kiểm tra single-flight:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

class LoadOnceConcurrencyTest {

    @Test
    void concurrentFirstUseLoadsExactlyOnce() throws Exception {
        AtomicInteger loads = new AtomicInteger();
        CountDownLatch release = new CountDownLatch(1);

        LoadOnce<String> secret = new LoadOnce<>(() -> {
            loads.incrementAndGet();
            return "test-only-value";
        });

        ExecutorService pool = Executors.newFixedThreadPool(16);
        List<Future<String>> results = new ArrayList<>();

        try {
            for (int i = 0; i < 64; i++) {
                results.add(pool.submit(() -> {
                    release.await();
                    return secret.get();
                }));
            }

            release.countDown();

            for (Future<String> result : results) {
                assertEquals("test-only-value",
                        result.get(5, TimeUnit.SECONDS));
            }
            assertEquals(1, loads.get());
        } finally {
            pool.shutdownNow();
            assertTrue(pool.awaitTermination(5, TimeUnit.SECONDS));
        }
    }
}
~~~

**Vì sao cần `volatile`?** Một thread ghi value và thread khác đọc mà không đồng bộ đúng có thể gặp vấn đề *memory visibility*. Double-checked read với `volatile` và khóa giúp bảo đảm chỉ một load hợp lệ được công bố cho các thread khác.

Nếu loader thất bại, `value` giữ `null`; lần tiếp theo có thể thử tải lại. Với secret thật, cần chính sách lỗi, timeout, jitter/backoff và cache TTL/refresh rõ ràng. Nếu secret bị rotate, phải công bố **snapshot mới atomically**, không sửa nhiều field riêng lẻ làm consumer nhìn một tập credential không nhất quán.

### 6.1. Kiểm thử invalidation và TTL

Với cache TTL, dùng `Clock.fixed(...)` hoặc fake `Clock` có thể điều khiển thay vì `Thread.sleep`. Các assertion quan trọng:

1. Trước TTL: nhiều thread chỉ thấy snapshot hợp lệ, không tạo lượt đọc dư.
2. Đúng thời điểm hết hạn: tối đa một lượt refresh trên mỗi key/JVM nếu contract là single-flight.
3. Reload thất bại: cache có giữ bản cũ không? **Chỉ nếu policy stale-if-error cho phép**, không tự kéo dài hạn.
4. Khi invalidate: request tiếp theo tải đúng version mới.
5. Tenant A và B: key cache và quyền Vault không bị trộn; không dùng field mutable `currentTenant` trên singleton.

## 7. SessionManager: đồng thời login, renew và re-auth

Spring Vault dùng `SessionManager` để lấy token cho các lệnh Vault. `LifecycleAwareSessionManager` được thiết kế **thread-safe**, đồng bộ những thread cùng yêu cầu token khi session chưa có token và lên lịch renew khi token có TTL/renewability thích hợp. Nó cũng hỗ trợ hủy state và revoke một số loại token khi context đóng.

**Hai bài test khác nhau:**

| Test | Dùng authentication gì? | Kỳ vọng |
| --- | --- | --- |
| Concurrent KV read với token cố định | `TokenAuthentication("test-token")` | HTTP/read đúng dưới tải; **không** chứng minh login/renew |
| Concurrent first login | AppRole/Kubernetes auth thử nghiệm cấp `LoginToken` | N thread đồng thời không gây N login dư khi session manager cấu hình đúng |
| Token renewal | LoginToken renewable TTL ngắn | Gia hạn gần expiry, hạn không tụt đến 0 khi vẫn có khả năng renew |
| Token hết hạn/revoked | Token bị expire/revoke trong test | Reauthenticate theo strategy hoặc trả lỗi có kiểm soát |
| Session shutdown | Context sở hữu session manager được đóng | Scheduler dừng; token được revoke nếu loại token và cấu hình cho phép |

**Lưu ý loại token:** `TokenAuthentication` trả `VaultToken` chung, còn các phương thức login có thể trả `LoginToken`. Với session manager lifecycle, token được tạo bởi login và có điều kiện phù hợp có thể bị revoke khi session đóng. Không suy rằng **mọi** token tĩnh bị revoke; token của ứng dụng production phải tuân theo cơ chế xác thực thực tế.

### 7.1. Thiết kế kiểm thử số lần login

Để quan sát đúng concurrency của login:

1. Cấu hình Vault dev/test với **AppRole test riêng**, SecretID ngắn hạn và policy chỉ cho phép KV test.
2. Tạo một `LifecycleAwareSessionManager` **duy nhất**, cùng một `VaultTemplate` trong context test.
3. Gắn một `ClientAuthentication` test wrapper tăng `AtomicInteger loginAttempts` khi `login()` được gọi và ủy quyền cho auth thật. Không log RoleID, SecretID hoặc token.
4. Sử dụng latch để N worker cùng yêu cầu `getSessionToken()` hoặc đọc một secret khi context mới khởi tạo.
5. Kiểm tra token hợp lệ và `loginAttempts` không tăng tỷ lệ thuận với N trong một đợt khởi tạo bình thường.
6. Lặp lại với token sắp hết hạn; đợi điều kiện qua Awaitility có deadline thay vì `Thread.sleep` tùy ý.
7. Đóng context và kiểm tra scheduler/worker không còn tạo renewal calls.

Không cứng hóa assertion “chính xác một login cho mọi tình huống” khi test mô phỏng logout, retry lỗi auth, token bị revoke hoặc client thực sự có nhiều session độc lập. Định nghĩa kỳ vọng theo số **session manager** đang được test, loại token và đường lỗi thực tế.

### 7.2. Lỗi đồng thời khi token rotate

Những thay đổi state sau đây cần có test:

- Token cũ đang dùng cho một số request trong khi token mới vừa được công bố.
- Token hết hạn đúng lúc một loạt request bắt đầu.
- Vault tạm sealed hoặc HA failover làm renew thất bại; ứng dụng không tạo hàng loạt vòng login không giới hạn.
- Client cố đọc bằng token thiếu policy: nhận 403 và **không** retry liên tục với cùng credential.
- Khi context đóng, renewal task không tiếp tục chạy và không phát sinh token ngoài chủ đích.

Kiểm thử concurrency chỉ qua một token root dev mode sẽ bỏ qua hầu hết các tình huống này.

## 8. LeaseContainer và listener chạy trên thread khác

Với dynamic credentials, Spring Vault có `SecretLeaseContainer`, hỗ trợ request secret có lease, renewal/rotation và phát các sự kiện qua `LeaseListener`/`LeaseErrorListener`. Listener có thể được gọi trên thread khởi động hoặc worker thread dùng cho refresh; vì thế consumer không được giả định callback luôn chạy trên request thread.

Ví dụ thiết kế một holder atomically công bố snapshot:

~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class DatabaseIdentityHolder {

    private final AtomicReference<Identity> current =
            new AtomicReference<>();

    public void install(Identity next) {
        current.set(Objects.requireNonNull(next));
    }

    public Identity requireCurrent(Instant now) {
        Identity snapshot = current.get();

        if (snapshot == null || !snapshot.expiresAt().isAfter(now)) {
            throw new IllegalStateException(
                    "No valid database credential available");
        }

        return snapshot;
    }

    public record Identity(
            String username,
            String password,
            Instant expiresAt) {

        @Override
        public String toString() {
            return "Identity[REDACTED]";
        }
    }
}
~~~

**Không dùng holder này để thay toàn bộ cơ chế pool rotation.** Khi credentials đổi, phải tái cấu hình `DataSource`/connection pool (hoặc tái tạo pool) một cách đồng bộ; kết nối đã mở có thể vẫn dùng tài khoản cũ. TTL của snapshot và `expiresAt` chỉ là ví dụ để kiểm tra; thời điểm hết hạn thực cần dựa trên lease metadata và tình trạng revoke/renew.

### 8.1. Test callback đúng dữ liệu và đúng thread-safety

Trong test unit, dùng fake event publisher và hai thread: một thread gọi `install(newIdentity)` nhiều lần, thread kia gọi `requireCurrent(...)`. Kỳ vọng luôn thấy **một snapshot đầy đủ**; không bao giờ thấy username mới kết hợp password cũ.

Trong integration test với Vault/DB test:

1. Tạo secrets engine database và role test có TTL ngắn, giới hạn số kết nối.
2. Đăng ký `RequestedSecret` vào container, lắng nghe created/renewed/expired/error events.
3. Chờ event bằng `CountDownLatch`/Awaitility với deadline, **không ngủ vô hạn**.
4. Xác minh consumer/pool đã cài credential phù hợp trước khi báo readiness.
5. Đóng context và xác minh không còn lịch renew, listener không tiếp tục nhận event mới.
6. Xem lease ở Vault theo audit/endpoint test; **không log** password hoặc lease token.

Phân biệt `stop()` và `destroy()`: theo API Spring Vault, `stop()` dừng renewal/rotation và event publishing nhưng **không tự expire active leases**; `destroy()` dừng và **có thể revoke những lease mà container đang quản lý**. Vì vậy đóng context có thể làm credential được cấp không dùng được nữa — phải bảo đảm lease không bị chia sẻ vô ý giữa các context đang chạy.

## 9. Vòng đời `ApplicationContext`: tạo, start, close

Spring Vault hoạt động được không cần Spring context, nhưng khi `VaultTemplate`, `SessionManager` và `SecretLeaseContainer` được đăng ký thành **Spring-managed beans**, chúng có thể tham gia vòng đời IoC: khởi tạo, start, stop và destroy.

| Giai đoạn | Cơ chế Spring | Điều cần quan sát |
| --- | --- | --- |
| **Bean construction** | Constructor, `@Bean` factory | Cấu hình endpoint, TLS, auth, scheduler và secrets engine đúng |
| **Initialization** | `@PostConstruct`, `InitializingBean.afterPropertiesSet()` | Không tạo lịch nền hai lần hoặc dùng bean chưa sẵn sàng |
| **Start** | `Lifecycle`/`SmartLifecycle` | Lease container hoạt động khi context bắt đầu |
| **Running** | Thread/request, scheduler, events | Mọi request và callback xử lý thread-safety |
| **Context closing** | `ContextClosedEvent`, `SmartLifecycle.stop()` | Ngừng nhận việc mới, quản lý request in-flight |
| **Bean destruction** | `@PreDestroy`, `DisposableBean.destroy()`/destroy method | Dừng schedulers, đóng HTTP resources, revoke khi policy cho phép |

**Đừng chủ động gọi `afterPropertiesSet()`, `start()`, `destroy()` của bean đã được Spring quản lý từ test thông thường** mà không xác định lifecycle: như vậy có thể start hai lần hoặc revoke lease/token trước khi context thực sự đóng.

### 9.1. Một lifecycle test độc lập, không cần Vault

Ví dụ dùng bean implements `SmartLifecycle` để chứng minh start khi context refresh và stop khi context close. Việc tách khỏi Vault làm test ổn định, giúp kiểm chứng cơ chế Spring trước khi kiểm tra resource thật:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

class ContextLifecycleUnitTest {

    @Test
    void closesLifecycleBeansExactlyOnce() {
        TestProbe probe;

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(TestConfig.class)) {

            probe = context.getBean(TestProbe.class);

            assertTrue(probe.isRunning());
            assertEquals(1, probe.starts.get());
            assertEquals(0, probe.stops.get());
        }

        assertFalse(probe.isRunning());
        assertEquals(1, probe.starts.get());
        assertEquals(1, probe.stops.get());
    }

    @Configuration
    static class TestConfig {
        @Bean
        TestProbe probe() {
            return new TestProbe();
        }
    }

    static class TestProbe implements SmartLifecycle {

        final AtomicInteger starts = new AtomicInteger();
        final AtomicInteger stops = new AtomicInteger();
        private volatile boolean running;

        @Override
        public void start() {
            starts.incrementAndGet();
            running = true;
        }

        @Override
        public void stop() {
            running = false;
            stops.incrementAndGet();
        }

        @Override
        public boolean isRunning() {
            return running;
        }
    }
}
~~~

`SmartLifecycle` mặc định hỗ trợ auto-start trong context phù hợp; ví dụ này không khai báo phase đặc biệt. Trong Spring Framework, `AnnotationConfigApplicationContext` refresh khi được tạo bằng constructor nhận config class, và `close()` từ try-with-resources kích hoạt lifecycle stop.

**Giới hạn:** Test này chứng minh callback Spring với một bean giả, **không chứng minh** token Vault được revoke, lease được hủy hay HTTP connection pool được giải phóng. Cần integration test riêng cho các tài nguyên đó.

### 9.2. Bean lifecycle thực của Spring Vault

Một mẫu quản lý lease hợp lý (chỉ bật khi môi trường test đã provision database secrets engine):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.lease.SecretLeaseContainer;

@Configuration
class LeaseIntegrationConfiguration {

    @Bean
    ThreadPoolTaskScheduler vaultLeaseScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("vault-lease-test-");
        return scheduler;
    }

    @Bean
    SecretLeaseContainer secretLeaseContainer(
            VaultOperations operations,
            ThreadPoolTaskScheduler vaultLeaseScheduler) {

        SecretLeaseContainer container = new SecretLeaseContainer(
                operations, vaultLeaseScheduler);

        // Chỉ tồn tại nếu Vault test có database role đã cấu hình!
        container.requestRotatingSecret("database/creds/orders-test");
        return container;
    }
}
~~~

Nếu Spring quản lý bean, nó tự thực thi `InitializingBean`/`SmartLifecycle`/`DisposableBean` theo lifecycle, không cần test gọi thủ công. Khi context đóng, container có thể revoke lease của nó; nếu role/database test chưa tồn tại thì bean start sẽ báo lỗi, **không nên “sửa” bằng cách bỏ test cleanup**.

Dùng cấu hình này trong một test riêng với Vault và database fixture test. Không đặt nó vào bài concurrency KV cơ bản vì Testcontainers Vault dev mode không tự dựng database secrets engine/role.

### 9.3. SessionManager cần được sở hữu bởi đúng context

Nếu ứng dụng tự tạo `LifecycleAwareSessionManager` bằng toán tử `new` bên ngoài Spring rồi truyền vào VaultTemplate, context có thể không biết để gọi `destroy()`. Ngược lại, khi đăng ký session manager làm bean độc lập, lifecycle có thể xử lý token renewal/revocation phù hợp.

Những assertion cần có:

- Một context mới dùng session manager của **chính nó** (không chia sẻ mutable manager toàn cục giữa test class hoặc tenant).
- Context close hủy lịch renew/token theo loại token và cấu hình thực, không tiếp tục gọi Vault sau khi shutdown.
- Nếu có `SecretLeaseContainer`, scheduler thuộc context được đóng/không tiếp tục tạo task.
- Không tạo nhiều session manager chỉ vì nhiều thread hoặc nhiều bean cần `VaultOperations`.

Đừng kỳ vọng một token do `TokenAuthentication` cấu hình tĩnh luôn bị revoke khi context close. Loại token và `ClientAuthentication` quyết định hành vi đó.

## 10. Spring TestContext cache có thể làm hỏng giả định của test

Với `@SpringBootTest`, Spring TestContext **cache ApplicationContext** và tái sử dụng giữa các test có cấu hình tương đương. Điều đó tiết kiệm chi phí startup nhưng có hệ quả:

- Hai method của cùng một test class thường cùng dùng một context.
- Hai class có cấu hình context giống nhau **có thể** dùng chung instance bean; chúng không tự tạo session manager mới.
- Context có thể đóng khi `@DirtiesContext` đánh dấu dirty, khi cache bị evict (LRU), hoặc lúc JVM shutdown.
- Vì vậy `@AfterEach` **không phải** là lúc context tự động đóng; một test assert "destroy đã xảy ra sau method" thường sai.
- Các thay đổi vào singleton/static state, fake scheduler, Vault path và token test có thể lọt sang test khác.

### 10.1. Dùng `@DirtiesContext` đúng lúc

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

@SpringBootTest
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class VaultSessionLifecycleIT {

    @Test
    void canUseVaultSessionWithinContext() {
        // Thực hiện request/test với workload auth giả lập hoặc Vault test.
        // Context sẽ bị loại khỏi cache/đóng SAU class test.
    }
}
~~~

`@DirtiesContext` đánh dấu context “dirty”, khiến framework đóng context đó và tạo mới khi test tiếp theo cần cùng cấu hình. **Đừng dùng đại trà** vì khởi động lại Vault-integrated contexts có thể chậm, tạo nhiều token/leases và khiến test suite thiếu ổn định.

Với test cần **chứng minh chính xác thứ tự close/destroy**, dùng `AnnotationConfigApplicationContext` trong `try-with-resources` như mục 9 hoặc tự kiểm soát context trong một integration test cô lập. Với Spring Boot context có nhiều bean, kiểm tra hiệu ứng bên ngoài (lease scheduler không tiếp tục, token không còn hợp lệ khi cần) thay vì chỉ so số callback của một mock.

### 10.2. Context cache và Testcontainers lifecycle

Một lỗi thường gặp:

- Test class A tạo **static VaultContainer** rồi Spring context được cache.
- Test class A kết thúc, container bị dừng theo lifecycle của JUnit.
- Test class B tái dùng Spring context cũ nhưng endpoint Vault không còn chạy.
- Kết quả là timeout/connection refused không liên quan race condition của `VaultTemplate`.

Giải pháp: **căn chỉnh vòng đời container và vòng đời cached context**. Có thể dùng một container dành cho toàn test suite với quản lý startup/shutdown thống nhất, hoặc cấu hình context/test class tách biệt và `@DirtiesContext` khi endpoint thay đổi. Không đổi `spring.cloud.vault.uri` hoặc static connection properties sau khi context đã được tạo rồi cho rằng mọi bean sẽ tự cập nhật.

## 11. Đóng context khi còn request đang chạy: xác định hợp đồng graceful shutdown

Đây là một tình huống nâng cao hơn việc đóng context không tải. Một request Java có thể đang chờ Vault HTTP response, trong khi Spring nhận tín hiệu shutdown.

~~~text
T0: Request A bắt đầu đọc KV qua VaultTemplate
T1: Spring nhận shutdown, readiness ngừng nhận request mới
T2: Request A còn đang chờ network
T3: SecretLeaseContainer.stop()/session cleanup bắt đầu
T4: Request A kết thúc hoặc timeout theo giới hạn
T5: Bean destruction hoàn tất, process dừng
~~~

**Thứ tự T3/T4 là phần thiết kế của ứng dụng**, không có một cam kết phổ quát rằng mọi in-flight request luôn xong trước khi session manager bị destroy. Điều này phụ thuộc web server graceful shutdown, `SmartLifecycle` phase, dependency graph, HTTP client timeout và framework version.

Kiểm thử cần xác định chính sách:

1. Khi shutdown bắt đầu, readiness chuyển sang không nhận traffic mới.
2. Request đang chạy hoặc **hoàn thành trong deadline**, hoặc thất bại có kiểm soát.
3. Không còn tác vụ scheduled renew/rotate chạy sau khi resource được destroy.
4. Không có double revoke/duplicate login do callback stop/destroy và retry handler chạy chồng nhau.
5. Thread pool, connection pool và scheduler không còn giữ JVM sống vô hạn.
6. Lỗi timeout/shutdown không đưa token, SecretID, database password vào log.

**Không nên** gọi `context.close()` đồng thời trên nhiều thread trong test mà không có lý do đặc biệt, rồi kỳ vọng tất cả callback được gọi theo lịch trình cụ thể. Muốn chứng minh shutdown an toàn, sử dụng fake blocking resource có latch, mở context test riêng, bắt đầu task, phát signal close và kiểm tra deadline/cleanup.

### 11.1. Test kỹ thuật điều phối với latch

Một pattern:

~~~java
CountDownLatch entered = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);

// Fake HTTP client/secret loader:
// entered.countDown();
// release.await();

// Test:
// 1. Start worker -> assertTrue(entered.await(2, SECONDS));
// 2. Đóng context theo thread riêng với deadline.
// 3. release.countDown() trong finally để không treo test.
// 4. Chờ worker và context-close Future đều xong.
// 5. Kiểm tra callbacks/events/threads không rò rỉ.
~~~

Dùng **latch và timeout** thay vì `Thread.sleep(1000)` để tạo race window; một test chỉ thành công tình cờ do lịch thread của máy phát triển không đủ tin cậy. Nếu cố ý tạo crash/timeout của Vault, chỉ thực hiện trên container test, không ảnh hưởng dịch vụ thật.

## 12. Bảo vệ tính nhất quán của thao tác Vault dưới concurrency

Không phải mọi lệnh Vault giống nhau về idempotency:

| Loại thao tác | Khi nhiều thread gọi | Tiêu chí test |
| --- | --- | --- |
| KV v2 **GET** | Các thread có thể đọc song song | Trả đúng value/version được mong đợi |
| KV v2 **write** | Hai writer có thể tạo hai version, ghi đè không mong đợi | Dùng CAS để kiểm tra version và lỗi conflict |
| Transit encrypt | Các lần encrypt thường tạo ciphertext khác nhau | Round-trip decrypt đúng; không assert ciphertext string bằng nhau |
| Transit decrypt | Cùng ciphertext và context thường cho cùng plaintext | Không lẫn context/tenant; không log plaintext |
| AppRole SecretID issue | Mỗi request có thể tạo SecretID mới | Đếm issuance, audit và cleanup, không retry mù |
| PKI issue | Mỗi request có thể sinh key pair/chứng thư với serial khác | Certificate/key khớp từng request; không share private key giữa thread |
| Database credentials dynamic | Mỗi issuance có thể tạo user/lease mới | Không nhân số issuance do retry/cache stampede |
| Response wrapping unwrap | Token chỉ dùng một lần | Chỉ một consumer lấy payload; các consumer khác thất bại rõ |

**Ví dụ conflict KV v2:** hai thread cùng đọc version 7; cả hai gửi write yêu cầu CAS=7. Theo cơ chế CAS, chỉ một write có thể thành công, write còn lại bị từ chối vì version đã đổi. Đó là **điều mong đợi**, không phải lỗi thread-safety của Spring Vault. Với Spring Vault, có thể dùng API versioned KV phù hợp hoặc HTTP request mang tùy chọn CAS; điều cần assert là lỗi conflict được phân biệt với lỗi Vault sealed/auth.

**Ví dụ Transit:** nếu dùng context cho key derivation, nhiều request không được chia sẻ mutable field `currentContext`; context phải là giá trị thuộc từng request. Với PKI, một lần issue trả private key của đúng certificate vừa cấp; không log hoặc giữ private key của request khác trong singleton.

## 13. Làm test ổn định: tránh flakiness và tài nguyên bị rò rỉ

### 13.1. Các anti-pattern thường gặp

| Anti-pattern | Vấn đề | Thay bằng |
| --- | --- | --- |
| `Thread.sleep(...)` để “đợi một chút” | CI chạy chậm/nhanh khác nhau | Latch, Awaitility, điều kiện có deadline |
| Dùng `ConcurrentHashMap` nhưng lưu object mutable không thread-safe | Collection thread-safe không làm object bên trong an toàn | Immutable snapshots/atomic publication |
| Tạo một `VaultTemplate` mới mỗi request | Pool/session/token tăng vô hạn | Reuse singleton đúng scope |
| Test concurrency bằng một request/luồng | Không kích hoạt race | N task có start gate và in-flight instrumentation |
| Dùng `Future.get()` không timeout | Test có thể treo vô hạn | `get(timeout, unit)` + HTTP timeout |
| Dùng static/shared secret giữa test | Tests ảnh hưởng nhau | KV path/test namespace riêng |
| Tắt `@DirtiesContext` dù đã làm hỏng singleton context | Test sau nhận state cũ | Isolate state, `@DirtiesContext` khi cần |
| Gắn `@DirtiesContext` cho mọi method | Context churn và chậm, nhiều token/lease | Chỉ dùng khi thực sự đòi fresh context |
| Test lease/renew bằng root token tĩnh | Không cover login/renew | Workload auth + LoginToken TTL ngắn |
| Không dừng `ExecutorService` | Leaked threads, JVM không thoát | `shutdownNow()`/`awaitTermination()` trong finally |
| Log raw `VaultResponse` khi assert fail | Lộ token/private key/test secrets | Assertion trên metadata và marker giả |
| Retry mọi thao tác khi failover | Cấp nhiều credential/PKI cert | Retry theo idempotency và deadline |

### 13.2. Kiểm soát thời gian

Đặt deadline ở cả **HTTP client** (connect/read timeout), **task** (`Future.get` hoặc Awaitility), và **test method** (JUnit `@Timeout`) nếu cần. Mỗi lớp có vai trò khác nhau:

- HTTP timeout giúp request không chiếm connection lâu quá quy định.
- Future timeout giúp test phát hiện blocking/chờ vô hạn.
- `@Timeout` giúp test suite thoát khi logic điều phối gặp deadlock.
- Sau timeout cần cleanup resource; chỉ hủy `Future` không chứng minh underlying I/O đã dừng.

Với bộ test stress, chạy lại ở các mức thread (1, 2, 8, 32), lặp nhiều lần và ghi số thất bại, latency p50/p95/p99, số login/lease operations. Nếu test thỉnh thoảng fail, thu **thread dump và telemetry đã che secret**; đừng tăng timeout vô hạn rồi coi như đã sửa race.

### 13.3. Theo dõi resource leak

Các kiểm tra hữu ích sau mỗi test hoặc sau context close:

- Không còn thread tên `vault-lease-test-...` hoặc scheduler tự tạo **thuộc context đã đóng**.
- Không còn login/renew requests phát sinh sau khi đã destroy session manager.
- Số HTTP connection đang mở trở về baseline sau khi graceful close và idle timeout phù hợp.
- Listener không tiếp tục được gọi sau khi container stop/destroy.
- Token/lease ở Vault được revoke theo **đúng cấu hình**, không vô tình revoke token tĩnh dùng chung hoặc credentials của context khác.
- Không còn test container chiếm tài nguyên sau suite; log CI không có secret.
- Context cache không giữ Spring beans trỏ tới container đã bị dừng.

Không assert “mọi thread của JVM phải biến mất”: JUnit, Spring và Testcontainers có thể có worker/global threads hợp lệ. Chỉ đếm thread/resource **do test/application tạo và sở hữu**.

## 14. Bảo mật và giám sát trong kiểm thử đồng thời

Test concurrency tạo nhiều logs và exceptions hơn bình thường. Những thông tin quan sát an toàn:

| Tín hiệu | Ý nghĩa | Tránh log |
| --- | --- | --- |
| `vault_request_duration_seconds{operation}` | Latency của KV/Transit/PKI | Plaintext, key, path tenant |
| `vault_inflight_requests` | Số request đang chạy, đo mức concurrency thật | Token hoặc identity nội bộ |
| `vault_auth_login_attempts_total` | Phát hiện login storm | Client token/SecretID |
| `vault_token_renew_errors_total` | Auth/renew failure | Raw auth response |
| `vault_lease_events_total{type}` | Created, renewed, expired, error | Lease ID/password |
| `vault_context_close_duration_seconds` | Shutdown mất bao lâu | Raw exception/body |
| `vault_cache_loads_total` | Kiểm tra cache stampede | Cache value/secret |
| `vault_retry_attempts_total{operation}` | Retry storm ở failover | Raw HTTP body |

Các tag `operation`, `outcome` và `event_type` nên là enum/allowlist; không dùng token, username, SecretID, context Transit hoặc private key làm metric label. Spring Vault có thể phát auth/lease events trên background threads, nên việc ghi metrics và cập nhật state từ listener cũng cần thread-safe.

## 15. Bài thực hành tổng hợp

### 15.1. Điều kiện trước khi bắt đầu

Có Docker, JUnit Jupiter, Spring Vault, Testcontainers Vault và một ứng dụng Java test không trỏ production. Dùng fixture trong mục 4, sau đó tạo cấu hình workload-auth/role/database riêng khi chuyển sang test token/lease.

### 15.2. Các bước

1. Chạy `VaultConcurrentReadIT` ở mục 5 với 48 task; xác nhận mọi result đúng và pool kết thúc.
2. Tăng pool từ 12 lên 24 thread, giữ tổng task 48; so latency và số request in-flight, không nhầm task count với concurrency thật.
3. Thay cache không đồng bộ vào `LoadOnceConcurrencyTest` và quan sát số lần loader tăng; sửa lại double-check + volatile, chứng minh chỉ load một lần.
4. Tạo secret KV v2 khác cho tenant B; chạy 2 luồng đồng thời theo danh tính/path đã xác thực và kiểm tra không có cross-tenant leak.
5. Tạo AppRole test có LoginToken ngắn hạn; kiểm tra nhiều thread cùng vào `getSessionToken()` khi chưa có token, đếm số login.
6. Mô phỏng token hết hạn hoặc Vault tạm không reachable; xác nhận retry bounded/không gọi login vô hạn.
7. Chạy `ContextLifecycleUnitTest`; chứng minh `start()` rồi `stop()` đúng một lần khi close.
8. Với fixture DB test, khởi chạy `SecretLeaseContainer`; quan sát created/renew/expire events với latch và dừng container bằng context close.
9. Bật Spring TestContext caching cho hai class cùng cấu hình; quan sát bean được dùng lại. Thử `@DirtiesContext` để xác minh context mới và thời điểm destroy.
10. Giả lập request blocked khi shutdown, kiểm tra graceful stop và timeout theo điều kiện đã định nghĩa.
11. Mô phỏng hai writer KV v2 với CAS cùng version; xác minh chỉ một ghi được chấp nhận.
12. Thu metrics in-flight, auth login count, pool saturation và leaked tasks; bảo đảm không có token/secret trong logs.

### 15.3. Checklist trước khi coi test hoàn thành

- [ ] Test dùng Vault container/dev độc lập, không bao giờ chạm cluster production.
- [ ] `VaultTemplate` được chia sẻ như một instance đã cấu hình, không dựng lại theo từng request.
- [ ] Test thật sự tạo concurrency có kiểm soát bằng latch, đo in-flight và có timeout.
- [ ] Mọi request nhận đúng dữ liệu; test tenant tránh trộn context/path/token.
- [ ] Cache single-flight không tạo hàng loạt reads; TTL/refresh có kiểm thử riêng.
- [ ] Login/renew được test bằng auth có vòng đời, không chỉ root token tĩnh.
- [ ] Dynamic lease tests kiểm tra cập nhật consumer và lifecycle stop/destroy.
- [ ] Bean lifecycle test xác nhận start/stop; integration test xác nhận token/lease cleanup thật.
- [ ] `@DirtiesContext` chỉ dùng khi cần; TestContext cache và Vault container lifecycle được đồng bộ.
- [ ] Shutdown có deadline và xử lý request in-flight rõ, không deadlock/leak.
- [ ] PKI/SecretID/dynamic credential issue không bị retry mù trong stress test.
- [ ] Assertions và logs chỉ dùng metadata; không rò rỉ private key, password, token, plaintext.
- [ ] Test có cleanup `ExecutorService`, container, temporary paths và tài nguyên bên ngoài.
- [ ] Số liệu p95/p99 và số login/lease/refresh được dùng để điều tra, không dùng mỗi test pass để suy ra đủ hiệu năng.

## 16. Tài liệu tham khảo

- Spring Vault, [Introduction to VaultTemplate](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html) — thread-safety và vòng đời beans/session manager.
- Spring Vault, [Authentication Methods](https://docs.spring.io/spring-vault/reference/vault/authentication.html) — token renewal và `LifecycleAwareSessionManager`.
- Spring Vault, [LifecycleAwareSessionManager Java API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/LifecycleAwareSessionManager.html) — đồng bộ login, token renew và destroy.
- Spring Vault, [SecretLeaseContainer Java API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretLeaseContainer.html) — thread-safety, `start`, `stop`, `destroy` và lease listeners.
- Spring Vault, [VaultTemplate Java API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTemplate.html) — client constructors và `VaultOperations`.
- Testcontainers for Java, [HashiCorp Vault Module](https://java.testcontainers.org/modules/vault/) — `VaultContainer`, init commands và HTTP API test.
- Spring Framework, [TestContext Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html) — cache, context close và reuse.
- Spring Framework, [`@DirtiesContext`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html) — invalidation và đóng context trong test.
- Spring Framework, [Lifecycle and SmartLifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html) — callback khởi tạo và hủy bean.
- HashiCorp Vault, [Lease, Renew, and Revoke](https://developer.hashicorp.com/vault/docs/concepts/lease) và [KV v2 API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2) — hành vi lease và concurrency với version/CAS.
