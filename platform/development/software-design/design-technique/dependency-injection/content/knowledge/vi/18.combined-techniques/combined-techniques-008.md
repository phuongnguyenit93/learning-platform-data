# Tránh đưa hạ tầng logging, cache hoặc retry làm lộ chi tiết không cần thiết

## 1. Bài toán: kết hợp kỹ thuật mà không làm rò rỉ chi tiết hạ tầng

Trong **Dependency Injection (DI)**, một thành phần nhận các phụ thuộc từ bên ngoài thay vì tự tạo chúng. **Inversion of Control (IoC)** giúp chuyển việc chọn và lắp ghép implementation về **composition root**. Với **constructor injection**, những phụ thuộc thật sự cần cho công việc của lớp được thể hiện qua constructor, tạo điều kiện thay thế bằng Java thuần trước khi dùng DI container.

Khi ứng dụng phát triển, chúng ta thường cần thêm **logging**, **cache** và **retry**. Đây là các mối quan tâm mang tính hạ tầng hoặc xuyên suốt nhiều thành phần (*cross-cutting concerns*). Nếu đưa chúng vào từng lớp nghiệp vụ một cách tùy tiện, code có thể biến thành:

```java
// Anti-pattern minh họa; không phải đoạn mã chạy độc lập.
final class PriceService {
    private final RemotePriceClient client;
    private final Logger logger;
    private final CacheManager cache;
    private final RetryTemplate retryTemplate;

    long getPrice(String tenantId, String sku) {
        logger.info("Calling price API for " + tenantId + "/" + sku);
        String key = tenantId + ":" + sku;
        Long hit = cache.get(key);
        if (hit != null) {
            return hit;
        }

        long value = retryTemplate.execute(
                () -> client.fetchPrice(tenantId, sku));
        cache.put(key, value);
        return value;
    }
}
```

Có thể thấy lớp vừa quyết định **giá cần tra**, vừa biết API cache, logger, tên key, client từ xa và cách lặp khi lỗi. Hậu quả gồm:

- Đổi thư viện log, cache hoặc retry kéo theo thay đổi code nghiệp vụ.
- Khó kiểm thử quy tắc giá một cách độc lập vì lớp phải dựng thêm nhiều công cụ hạ tầng.
- Dễ ghi nhầm tenant ID, thông tin khách hàng, token hoặc toàn bộ request vào log.
- Có nguy cơ cache dùng sai khóa dẫn tới dữ liệu của tenant này xuất hiện ở tenant khác.
- Retry có thể làm lặp các thao tác có side effect, gây thanh toán/trừ kho hai lần.
- Khi nhiều lớp tự retry, số lần gọi mạng có thể tăng theo cấp số nhân.
- Scope và ownership của client/cache/executor không rõ ai tạo, ai đóng.

**Mục tiêu của bài học không phải “cấm tuyệt đối logging, cache, retry trong mọi lớp”.** Mục tiêu là giữ **ranh giới trách nhiệm**: logic nghiệp vụ biết những khái niệm nghiệp vụ thực sự cần, còn quyết định về adapter, cache policy, retry policy, telemetry và lifecycle được đặt tại nơi phù hợp.

Kết thúc bài, bạn có thể:

1. Phân biệt logging kỹ thuật với sự kiện nghiệp vụ/audit bắt buộc.
2. Dùng **Decorator** kết hợp constructor injection để thêm logging, cache và retry mà không sửa service.
3. Chọn vị trí decorator ở composition root và giải thích tác động của **thứ tự bọc**.
4. Nhận diện các rủi ro caching (khóa, scope, stale data, invalidation) và retry (transient error, idempotency, timeout, backoff).
5. Viết và kiểm thử object graph bằng Java thuần, trước khi cân nhắc interceptor, AOP hoặc DI container.

## 2. Xác định ranh giới: nghiệp vụ cần gì, hạ tầng cung cấp gì?

Giả sử `PriceService` cần giá đơn vị của một sản phẩm để tính tổng tiền. Hợp đồng mà nghiệp vụ dùng có thể rất nhỏ:

```java
interface PriceLookup {
    long priceVnd(PriceKey key);
}
```

`PriceService` chỉ cần `PriceLookup`. Nó không cần biết dữ liệu đến từ HTTP, database, cache hay một fake trong test; cũng không cần biết thư viện log hoặc retry.

```text
                       Composition Root
                        chọn/lắp ghép
                             |
                             v
                 TracingPriceLookup
                             |
                             v
                 CachingPriceLookup
                             |
                             v
                 RetryingPriceLookup
                             |
                             v
                 RemotePriceAdapter
                             |
                             v
                    (hệ thống ngoài)

                  PriceService
                       |
                 PriceLookup
               (hợp đồng nghiệp vụ)
```

Cả `TracingPriceLookup`, `CachingPriceLookup`, `RetryingPriceLookup` và `RemotePriceAdapter` đều triển khai **cùng một hợp đồng `PriceLookup`**. Composition root ghép chúng lại rồi inject **một** `PriceLookup` vào `PriceService`.

Đây là sự kết hợp giữa:

- **Dependency Inversion Principle (DIP):** nghiệp vụ phụ thuộc hợp đồng phù hợp, không phụ thuộc lớp HTTP/cache/log cụ thể.
- **Decorator:** thêm hành vi trước/sau lời gọi qua một lớp có cùng interface.
- **Constructor injection:** truyền dependency rõ ràng, tránh tìm kiếm ngầm qua registry/container.
- **Composition root:** chọn implementation và thứ tự decorator ở ranh giới khởi động.

### 2.1. Không phải hạ tầng nào cũng cần một interface tùy biến

Một lớp nghiệp vụ không nhất thiết phải tạo interface cho từng thao tác nhỏ hay cho mọi thư viện. Nếu logging chỉ phục vụ chẩn đoán nội bộ, có thể đặt ở adapter, decorator hoặc cơ chế instrumentation tại ranh giới thích hợp.

Ngược lại, nếu một thao tác như **ghi sự kiện thanh toán đã xác nhận** là yêu cầu nghiệp vụ bắt buộc, nó có thể cần một hợp đồng nghiệp vụ tường minh như `PaymentAuditRecorder`. Không được tùy tiện bỏ thao tác audit chỉ vì xem đó là “logging kỹ thuật”. Điểm khác nhau là:

| Nội dung | Logging kỹ thuật | Audit/sự kiện nghiệp vụ |
| --- | --- | --- |
| Mục tiêu | Chẩn đoán, quan sát latency, lỗi gọi dependency. | Ghi nhận sự kiện mà nghiệp vụ hoặc quy định yêu cầu. |
| Ví dụ | `price.lookup.failed`, thời lượng gọi API. | `PAYMENT_CAPTURED`, `ORDER_APPROVED`. |
| Có cần xuất hiện ở use case? | Thường có thể đặt ở decorator/adapter. | Có thể là một bước bắt buộc của luồng nghiệp vụ. |
| Nếu hệ thống ghi lỗi | Thường không nên tự ý thay đổi kết quả nghiệp vụ; phải có chính sách quan sát phù hợp. | Có thể ảnh hưởng tính đúng đắn, transaction hoặc trạng thái nghiệp vụ. |
| Dữ liệu trong event | Giới hạn metadata đã được cho phép. | Theo hợp đồng audit và quy tắc bảo mật/lưu trữ cụ thể. |

Như vậy, **không dùng “ẩn hết trong decorator” để che một side effect nghiệp vụ bắt buộc**. Cần biết điều gì thuộc chính sách nghiệp vụ và điều gì chỉ là cơ chế triển khai.

## 3. Chọn cách kết hợp: Decorator, Adapter, Factory hay Interceptor?

| Kỹ thuật | Trách nhiệm | Dùng khi |
| --- | --- | --- |
| **Adapter** | Chuyển giao diện ứng dụng sang SDK/HTTP/SQL cụ thể. | Kết nối hạ tầng và giữ chi tiết thư viện ngoài lớp nghiệp vụ. |
| **Decorator** | Bọc một interface và thêm hành vi như cache, retry hoặc tracing. | Muốn thêm tính năng qua composition mà không sửa lớp sử dụng dependency. |
| **Factory/Provider** | Tạo instance theo thời điểm, cấu hình hoặc scope. | Dependency cần tạo muộn, riêng cho request/task hoặc thay đổi theo cấu hình. |
| **Interceptor/AOP** | Chèn hành vi theo điểm cắt mà framework hỗ trợ. | Nhiều thành phần cần instrumentation đồng nhất và nhóm chấp nhận sự phụ thuộc vào cơ chế framework. |
| **Composition root** | Quyết định dùng implementation nào và ghép các lớp trên. | Tại bootstrap hay ranh giới lắp ghép được kiểm soát. |

Không nên thêm cả bốn cơ chế cho một use case nhỏ. Với Java thuần, **Decorator + constructor injection + một composition root rõ ràng** thường đã đủ để học và kiểm chứng các ranh giới.

### 3.1. Lợi ích và giới hạn của decorator

Decorator giúp lớp sử dụng chỉ thấy `PriceLookup`, nhưng nó **không tự giải quyết**:

- Cache key đúng theo tenant, vùng giá, tiền tệ hoặc quyền truy cập;
- Việc invalidation/TTL/giới hạn bộ nhớ;
- Điều kiện retry an toàn và ngân sách thời gian;
- Việc ghi log không chứa bí mật;
- Thread safety, lifecycle hoặc thứ tự shutdown.

Mỗi decorator phải có **contract và chính sách rõ ràng**, được kiểm thử như một thành phần riêng. Nếu decorator chỉ che một behavior phức tạp mà không có ownership hay tài liệu, kiến trúc cũng có thể trở nên khó hiểu.

## 4. Ví dụ Java thuần: service không biết logging, cache và retry

Ta xây một chương trình tra giá sản phẩm theo tenant. `PriceService` chỉ nhận `PriceLookup`; composition root tạo ba decorator để bổ sung hành vi.

**Các giả định của ví dụ:**

- `PriceLookup.priceVnd(...)` là thao tác **đọc**, không thay đổi trạng thái bên ngoài, và an toàn để gọi lại nếu adapter báo lỗi tạm thời theo contract minh họa.
- Giá cố định `125.000 VND` là dữ liệu giả. Adapter không gọi HTTP thật.
- Cache dạng `HashMap` chỉ để chạy **đơn luồng**, không có TTL hoặc giới hạn kích thước; không được mang nguyên xi vào server production.
- Trace chỉ ghi **mã sự kiện cố định**, không ghi tenant ID, SKU, credential hay exception message.
- `RetryPause` là điểm injection để quan sát lần retry, **không tự ngủ/chờ**. Production cần backoff, deadline và cơ chế hủy có kiểm soát.

Lưu đoạn sau vào `InfrastructureDecoratorDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

// Giá trị khóa bất biến: cache phải xét cả tenant và sản phẩm.
final class PriceKey {
    final String tenantId;
    final String sku;

    PriceKey(String tenantId, String sku) {
        if (tenantId == null || tenantId.trim().isEmpty()
                || sku == null || sku.trim().isEmpty()) {
            throw new IllegalArgumentException("INVALID_PRICE_KEY");
        }
        this.tenantId = tenantId;
        this.sku = sku;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof PriceKey)) {
            return false;
        }
        PriceKey that = (PriceKey) other;
        return tenantId.equals(that.tenantId)
                && sku.equals(that.sku);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, sku);
    }

    @Override
    public String toString() {
        return "PriceKey{[REDACTED]}";
    }
}

// Hợp đồng ứng dụng. Không lộ HTTP, cache hay thư viện log.
interface PriceLookup {
    long priceVnd(PriceKey key);
}

final class PriceService {
    private final PriceLookup lookup;

    PriceService(PriceLookup lookup) {
        this.lookup = Objects.requireNonNull(lookup, "lookup");
    }

    long totalVnd(PriceKey key, int quantity) {
        Objects.requireNonNull(key, "key");
        if (quantity <= 0) {
            throw new IllegalArgumentException("INVALID_QUANTITY");
        }
        return Math.multiplyExact(lookup.priceVnd(key), quantity);
    }
}

// Chỉ lỗi thuộc nhóm tạm thời mới được retry trong ví dụ.
final class TransientPriceFailure extends RuntimeException {
    TransientPriceFailure() {
        super("PRICE_SOURCE_TEMPORARILY_UNAVAILABLE");
    }
}

// Adapter giả lập: thất bại một số lần đầu rồi trả giá.
final class FlakyPriceAdapter implements PriceLookup {
    private int failuresRemaining;
    int calls;

    FlakyPriceAdapter(int failuresBeforeSuccess) {
        if (failuresBeforeSuccess < 0) {
            throw new IllegalArgumentException("INVALID_FAILURE_COUNT");
        }
        this.failuresRemaining = failuresBeforeSuccess;
    }

    @Override
    public long priceVnd(PriceKey key) {
        Objects.requireNonNull(key, "key");
        calls++;
        if (failuresRemaining > 0) {
            failuresRemaining--;
            throw new TransientPriceFailure();
        }
        return 125_000L;
    }
}

// Không lộ scheduler/Thread.sleep cho nghiệp vụ.
interface RetryPause {
    void beforeRetry(int nextAttempt);
}

// Decorator: retry đúng loại lỗi và giới hạn tổng số lần gọi.
final class RetryingPriceLookup implements PriceLookup {
    private final PriceLookup delegate;
    private final int maxAttempts;
    private final RetryPause pause;

    RetryingPriceLookup(PriceLookup delegate, int maxAttempts,
                        RetryPause pause) {
        this.delegate = Objects.requireNonNull(delegate, "delegate");
        this.pause = Objects.requireNonNull(pause, "pause");
        if (maxAttempts < 1) {
            throw new IllegalArgumentException("INVALID_MAX_ATTEMPTS");
        }
        this.maxAttempts = maxAttempts;
    }

    @Override
    public long priceVnd(PriceKey key) {
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                return delegate.priceVnd(key);
            } catch (TransientPriceFailure transientFailure) {
                if (attempt == maxAttempts) {
                    throw transientFailure;
                }
                pause.beforeRetry(attempt + 1);
            }
        }
        throw new AssertionError("UNREACHABLE");
    }
}

// Decorator: cache CHỈ kết quả trả về thành công.
// Demo đơn luồng, KHÔNG TTL, KHÔNG giới hạn kích thước.
final class CachingPriceLookup implements PriceLookup {
    private final PriceLookup delegate;
    private final Map<PriceKey, Long> cache = new HashMap<>();

    CachingPriceLookup(PriceLookup delegate) {
        this.delegate = Objects.requireNonNull(delegate, "delegate");
    }

    @Override
    public long priceVnd(PriceKey key) {
        Objects.requireNonNull(key, "key");
        Long cached = cache.get(key);
        if (cached != null) {
            return cached;
        }

        long price = delegate.priceVnd(key);
        cache.put(key, price);
        return price;
    }
}

// Hợp đồng trace chỉ nhận MÃ SỰ KIỆN, không nhận input nghiệp vụ.
interface TraceSink {
    void event(String eventCode);
}

final class TracingPriceLookup implements PriceLookup {
    private final PriceLookup delegate;
    private final TraceSink trace;

    TracingPriceLookup(PriceLookup delegate, TraceSink trace) {
        this.delegate = Objects.requireNonNull(delegate, "delegate");
        this.trace = Objects.requireNonNull(trace, "trace");
    }

    @Override
    public long priceVnd(PriceKey key) {
        trace.event("price.lookup.started");
        try {
            long price = delegate.priceVnd(key);
            trace.event("price.lookup.succeeded");
            return price;
        } catch (RuntimeException failure) {
            trace.event("price.lookup.failed");
            throw failure;
        }
    }
}

public class InfrastructureDecoratorDemo {
    public static void main(String[] args) {
        // Composition root: quyết định implementation, thứ tự, policy.
        FlakyPriceAdapter remote = new FlakyPriceAdapter(2);
        List<Integer> retryAttempts = new ArrayList<>();

        RetryPause pause = nextAttempt -> retryAttempts.add(nextAttempt);
        TraceSink trace = code -> System.out.println("TRACE " + code);

        PriceLookup source = new TracingPriceLookup(
                new CachingPriceLookup(
                        new RetryingPriceLookup(remote, 3, pause)),
                trace);

        PriceService service = new PriceService(source);
        PriceKey key = new PriceKey("tenant-A", "SKU-42");

        System.out.println("Total 1: " + service.totalVnd(key, 2));
        System.out.println("Total 2: " + service.totalVnd(key, 1));
        System.out.println("Adapter calls: " + remote.calls);
        System.out.println("Retry attempts: " + retryAttempts);
    }
}
```

Biên dịch và chạy với JDK:

```bash
javac InfrastructureDecoratorDemo.java
java InfrastructureDecoratorDemo
```

Đầu ra dự kiến:

```text
TRACE price.lookup.started
TRACE price.lookup.succeeded
Total 1: 250000
TRACE price.lookup.started
TRACE price.lookup.succeeded
Total 2: 125000
Adapter calls: 3
Retry attempts: [2, 3]
```

**Diễn giải:**

1. Lần `totalVnd` đầu tiên không có cache, gọi adapter. Adapter báo lỗi tạm thời hai lần, decorator retry thêm lần thứ hai và thứ ba; lần thứ ba thành công với giá `125.000`.
2. `CachingPriceLookup` chỉ lưu **kết quả thành công**, nên lần tra giá thứ hai với cùng `PriceKey` không gọi adapter nữa.
3. `TracingPriceLookup` ở **ngoài cùng** ghi một cặp sự kiện cho **mỗi lần service gọi lookup**, dù lần đầu adapter có ba attempt.
4. `PriceService` không biết retry, cache hit, logging hay tên thư viện. Nó chỉ gọi `PriceLookup` và nhân với số lượng.
5. Không có mã `tenant-A` hoặc `SKU-42` trong các dòng TRACE; key có `toString()` đã ẩn giá trị trong trường hợp vô tình in object.

**Giới hạn bảo mật:** việc `PriceKey.toString()` không in tenant/SKU **không** có nghĩa hệ thống không lưu giá trị đó trong bộ nhớ, heap dump hoặc cache. Nếu các giá trị là dữ liệu nhạy cảm, vẫn cần chính sách truy cập, lưu giữ, telemetry và vòng đời phù hợp.

## 5. Thứ tự decorator có làm thay đổi hành vi không?

**Có.** Tất cả decorator cùng triển khai một interface, nhưng vị trí trong object graph ảnh hưởng kết quả quan sát được.

### 5.1. Trace ở ngoài cache, retry ở trong cache

```text
Service
  -> Tracing
       -> Cache
            -> Retry
                 -> Remote
```

- Mọi lần gọi `PriceLookup` qua service đều được ghi trace, kể cả cache hit.
- Cache hit bỏ qua adapter và retry hoàn toàn.
- Retry chỉ hoạt động khi phải lấy dữ liệu mới; các attempt bên trong được gom vào một lời gọi logic nhìn từ trace ngoài.
- Nếu muốn biết số **attempt thực tế**, cần instrumentation ở adapter hoặc riêng decorator retry, không suy ra từ số `price.lookup.started`.

Đây là thứ tự của ví dụ và thường phù hợp khi trace ở cấp **thao tác logic**; tuy nhiên không phải lựa chọn duy nhất.

### 5.2. Cache ở ngoài trace

```text
Service
  -> Cache
       -> Tracing
            -> Retry
                 -> Remote
```

Khi cache hit, lời gọi kết thúc trước khi đến trace, nên event `price.lookup.started` **không xuất hiện**. Cấu hình này có thể phù hợp nếu mục tiêu là ghi số lần truy cập backend thay vì số lần use case yêu cầu tra giá.

### 5.3. Retry ở ngoài cache

```text
Service
  -> Retry
       -> Cache
            -> Remote
```

Đường lỗi của cache, lớp delegate và chính sách lưu cache có thể bị thực thi lại. Có tình huống hợp lệ, nhưng cần phân biệt liệu lỗi xảy ra ở backend, trong cache hay ở quá trình serialize. Một lỗi dữ liệu hoặc lỗi cấu hình cache thường **không nên retry một cách vô điều kiện**.

Đối với nhiều hệ thống, retry được đặt **sát adapter ngoại vi** để lựa chọn chính xác những lỗi kết nối tạm thời mà adapter hiểu được. Tuy vậy, nếu nhiều tầng client/framework đã tự retry, thêm decorator ngoài có thể làm số lần gọi thực tăng quá mức.

### 5.4. Không tự suy rằng mọi decorator giao hoán

Với hai decorator `A` và `B`, thông thường `A(B(x))` **không tương đương** `B(A(x))`. Điều đó có thể thể hiện qua:

- Số lần ghi log, metric hoặc tracing span;
- Thời lượng đo được (tính cả retry hay chỉ một attempt);
- Số lần gọi adapter;
- Cache có lưu kết quả của lần retry cuối hay của một attempt thất bại;
- Khi nào exception được phát ra;
- Thứ tự cleanup của tài nguyên.

**Composition root nên thể hiện thứ tự một cách dễ đọc và có test xác minh các bất biến quan trọng**, thay vì phụ thuộc vào thứ tự interceptor không được bảo đảm bởi framework.

## 6. Logging và tracing: không để chi tiết hạ tầng tràn vào nghiệp vụ

### 6.1. Chỉ ghi những dữ liệu thật sự cần thiết

Một logger trực tiếp trong service không phải lúc nào cũng sai. Nhưng nếu service phải biết SDK tracing, định dạng span, metric label hoặc internal HTTP status, ranh giới đã bắt đầu bị lẫn.

Một cách tổ chức là:

- **Service:** trả về kết quả, ném lỗi theo hợp đồng nghiệp vụ, có thể phát sự kiện nghiệp vụ quan trọng qua một port tường minh.
- **Tracing decorator:** ghi những mốc kỹ thuật như start/success/failure, duration hoặc attempt count đã được phép.
- **Adapter:** chuyển exception của SDK ngoài thành loại lỗi phù hợp với ranh giới và bổ sung metadata đã được rà soát.
- **Composition root:** chọn `TraceSink` và chính sách log phù hợp với môi trường.

Trong demo, `TraceSink` chỉ nhận mã sự kiện, không nhận `PriceKey` hay exception. Điều này giới hạn nguy cơ vô tình nối token, URL hoặc tham số khách hàng vào log.

Đối với production, có thể muốn gắn correlation ID. Khi làm vậy cần xác định **ID nào được phép log**, tránh đưa user token/session cookie/authorization header hoặc dữ liệu người dùng vào event hay metric label.

### 6.2. Không nuốt hoặc làm méo lỗi nghiệp vụ chỉ vì log

Một sai lầm thường gặp là:

```java
// Mẫu cần tránh: ngoại lệ mất ngữ nghĩa và log lộ chi tiết.
try {
    return remote.call();
} catch (Exception ex) {
    logger.error("Failed: " + ex.getMessage());
    return 0; // Giá giả có thể đi tiếp như một giá thật.
}
```

`remote` và `logger` là các đối tượng giả định. Đoạn này vừa có thể log message chứa secret, vừa biến lỗi hệ thống thành giá `0` hợp lệ giả tạo. Nếu yêu cầu nghiệp vụ cho phép fallback, hãy biểu diễn fallback như một **chính sách có chủ đích và kiểm thử riêng**, không dùng giá trị “tiện tay”.

Trong ví dụ Java, `TracingPriceLookup` **ném lại cùng RuntimeException**. Tuy nhiên, nếu chính `TraceSink.event(...)` ném exception thì vẫn có thể làm thay đổi kết quả hoặc che lỗi gốc. Một hệ thống production phải quy định chính sách khi telemetry hỏng (cô lập tác động, đệm/bỏ sự kiện có giám sát hoặc coi là lỗi bắt buộc tùy contract). Không nên giả định mọi framework log đều hoàn toàn không gây lỗi.

### 6.3. Logging kỹ thuật không thay thế audit đáng tin cậy

Sự kiện `price.lookup.succeeded` không chứng minh một giao dịch nghiệp vụ đã được ghi nhận bền vững. Nếu cần audit bắt buộc cho thanh toán hoặc thao tác thay đổi quyền, hãy xây một use case/port tương ứng và xét transaction, consistency, retention và phân quyền. Logging của decorator chỉ là quan sát kỹ thuật theo hợp đồng đã chọn.

## 7. Cache: tối ưu hóa phải tôn trọng ngữ nghĩa dữ liệu

Cache có thể tăng tốc đọc, nhưng **dữ liệu cache sai còn nguy hiểm hơn không có cache**. Trước khi thêm `CachingPriceLookup`, phải xác định:

### 7.1. Cache key phải đủ bối cảnh

Ví dụ dùng `PriceKey(tenantId, sku)` và triển khai `equals/hashCode` theo **cả hai trường**. Nếu chỉ dùng `sku`, tenant B có thể nhìn thấy giá của tenant A trong trường hợp giá tùy tenant.

Trong ứng dụng thật, khóa có thể còn cần currency, khu vực, phân khúc khách hàng, chính sách giảm giá, phiên bản cấu hình hoặc quyền xem dữ liệu. Mỗi yếu tố **thực sự ảnh hưởng kết quả** phải được xét trong chiến lược key.

Không nối các giá trị tùy ý thành `tenant + ":" + sku` nếu không có quy tắc escaping/canonicalization rõ; hai cặp giá trị khác nhau có thể tạo cùng chuỗi khóa. Một kiểu khóa bất biến với `equals/hashCode` phù hợp thường dễ kiểm tra hơn.

**Nhưng “đủ khóa” không đồng nghĩa “được phép giữ dữ liệu”.** Tenant ID/SKU có thể là dữ liệu nhạy cảm; cache cần quyền truy cập và retention phù hợp.

### 7.2. Thời hạn, invalidation và tính đúng đắn

`HashMap` trong demo **không có TTL, không giới hạn dung lượng và không invalidation**. Nó chỉ minh họa vị trí decorator. Production thường cần:

- Quy định khi nào giá bị coi là cũ và được phép trả giá cũ trong bao lâu.
- Vô hiệu hóa hoặc cập nhật cache khi giá thay đổi.
- Giới hạn số entry/dung lượng, eviction và giám sát hit/miss.
- Giải quyết lỗi đồng thời khi nhiều request cùng miss (*cache stampede*).
- Tránh cache response cá nhân hóa dưới khóa quá rộng.
- Quy định cache lỗi, kết quả rỗng hoặc dữ liệu bị từ chối: mặc định demo **không cache exception**.

Khi giá quyết định thanh toán thật, có thể phải kiểm tra lại giá/phiên bản giá tại thời điểm chốt giao dịch. **Cache không tự bảo đảm tính nhất quán với nguồn dữ liệu**.

### 7.3. Scope và thread safety

`HashMap` trong ví dụ không thread-safe khi bị nhiều thread truy cập/ghi đồng thời. Nếu wrapper được dùng chung trong web server, cần triển khai cache phù hợp với concurrency, chính sách key/TTL và lifecycle. Chuyển sang `ConcurrentHashMap` là một bước kỹ thuật nhưng **không tự giải quyết** cache stampede, TTL, versioning, dữ liệu nhạy cảm hoặc consistency.

Một cache dùng cho request có ranh giới khác cache application-wide; giữ dữ liệu người dùng qua request sau có thể vi phạm yêu cầu tách biệt. Composition root hoặc scope boundary phải chọn đúng thời gian sống cho cache, chứ `Map` không tự quyết định được.

## 8. Retry: chỉ lặp các thao tác an toàn, đúng loại lỗi

Retry là nơi dễ gây lỗi nghiệp vụ nghiêm trọng nhất khi được áp dụng tùy tiện.

### 8.1. Lỗi nào đáng thử lại?

Những lỗi có thể mang tính tạm thời:

- Timeout hoặc mất kết nối ngắn hạn;
- Throttling/busy có tín hiệu retry theo contract;
- Backend tạm thời không sẵn sàng.

Những lỗi **không nên retry mù quáng**:

- Input không hợp lệ, thiếu quyền, sai token hoặc lỗi cấu hình;
- Một lỗi nghiệp vụ vĩnh viễn như “sản phẩm không tồn tại” nếu contract không nói nó có thể thay đổi ngay;
- Lỗi lập trình như `NullPointerException` hoặc vi phạm invariant.

Trong demo, `RetryingPriceLookup` chỉ bắt `TransientPriceFailure`. `IllegalArgumentException` không bị retry. Một adapter thật cần **phân loại lỗi ở biên** và hiểu đúng semantics của API ngoài; đừng bắt mọi `RuntimeException` rồi retry.

### 8.2. Idempotency và side effect

Đọc giá trong ví dụ được giả định an toàn để gọi lại. Nhưng giả định này **không áp dụng cho mọi thao tác**.

Nếu retry `PaymentGateway.capture(...)`, request trước có thể đã được backend xử lý thành công nhưng response bị mất. Gọi lại có thể ghi nợ hai lần nếu backend không có bảo đảm idempotency.

Một luồng có side effect chỉ nên retry khi **contract và cơ chế idempotency** đã rõ (ví dụ idempotency key ổn định được hệ thống nhận và xử lý đúng, transaction hoặc giao thức có khả năng khử trùng lặp). Việc chỉ thêm decorator retry không tạo ra các bảo đảm đó.

### 8.3. Tổng số attempt và backoff

Trong ví dụ, `maxAttempts = 3` có nghĩa **tối đa ba lần gọi tổng cộng**, không phải “một lần đầu cộng thêm ba lần retry”. Danh sách `[2, 3]` ghi thời điểm chuyển sang attempt thứ hai và thứ ba.

Production thường cần:

- **Exponential backoff có jitter** hoặc chính sách theo `Retry-After`, tránh đồng loạt retry.
- **Timeout/deadline tổng** cho cả lời gọi logic, không chỉ từng attempt.
- Cơ chế hủy và tôn trọng thread interruption nếu có chờ.
- Giới hạn số attempt và khả năng mở circuit khi backend gặp sự cố dài.
- Observability phân biệt **logical call count** với **backend attempt count**.
- Tránh retry ở nhiều tầng mà không phối hợp.

Ví dụ: một client retry 3 attempt và một decorator ngoài cũng retry 3 attempt có thể sinh **tối đa 9 lần gọi backend** cho một yêu cầu logic, chưa tính các proxy khác. Retry càng nhiều không đồng nghĩa hệ thống càng bền vững.

**`RetryPause` trong demo cố ý không ngủ để test xác định.** Nó là seam để đưa vào chiến lược chờ, không phải chính sách retry đầy đủ cho production.

## 9. Kiểm thử bằng fake: xác minh decorator không làm rò chi tiết

Unit test có thể tự tạo object graph với fake và spy, không cần DI container, mạng hoặc thư viện mock. Tạo file `InfrastructureDecoratorTest.java` cạnh `InfrastructureDecoratorDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

final class RecordingTraceSink implements TraceSink {
    final List<String> events = new ArrayList<>();

    @Override
    public void event(String code) {
        events.add(code);
    }
}

final class RecordingRetryPause implements RetryPause {
    final List<Integer> nextAttempts = new ArrayList<>();

    @Override
    public void beforeRetry(int nextAttempt) {
        nextAttempts.add(nextAttempt);
    }
}

final class PermanentFailurePriceAdapter implements PriceLookup {
    int calls;

    @Override
    public long priceVnd(PriceKey key) {
        calls++;
        throw new IllegalArgumentException("PERMANENT_PRICE_ERROR");
    }
}

public class InfrastructureDecoratorTest {
    static void check(boolean condition, String description) {
        if (!condition) {
            throw new AssertionError(description);
        }
    }

    public static void main(String[] args) {
        // Lắp graph cho test: adapter fake + decorator thật.
        FlakyPriceAdapter flaky = new FlakyPriceAdapter(2);
        RecordingTraceSink traces = new RecordingTraceSink();
        RecordingRetryPause retries = new RecordingRetryPause();

        PriceLookup graph = new TracingPriceLookup(
                new CachingPriceLookup(
                        new RetryingPriceLookup(flaky, 3, retries)),
                traces);
        PriceService service = new PriceService(graph);

        PriceKey tenantA = new PriceKey("tenant-A", "SKU-42");
        check(service.totalVnd(tenantA, 2) == 250_000L,
                "Sai tổng tiền lần đầu");
        check(service.totalVnd(new PriceKey(
                "tenant-A", "SKU-42"), 1) == 125_000L,
                "Sai giá lần hai");

        // Cache hit: không gọi lại adapter, không retry thêm.
        check(flaky.calls == 3,
                "Cache hit vẫn gọi backend");
        check(retries.nextAttempts.equals(Arrays.asList(2, 3)),
                "Số lần retry không đúng");
        check(traces.events.equals(Arrays.asList(
                "price.lookup.started", "price.lookup.succeeded",
                "price.lookup.started", "price.lookup.succeeded")),
                "Trace của logical calls không đúng");

        // Khóa phải chứa tenant: tenant khác tạo một cache miss.
        check(service.totalVnd(
                new PriceKey("tenant-B", "SKU-42"), 1) == 125_000L,
                "Sai giá tenant khác");
        check(flaky.calls == 4,
                "Cache key bị lẫn giữa các tenant");

        // Kiểm tra log không in raw key.
        for (String event : traces.events) {
            check(!event.contains("tenant-A")
                    && !event.contains("tenant-B")
                    && !event.contains("SKU-42"),
                    "Trace làm lộ dữ liệu của request");
        }

        // Lỗi vĩnh viễn không bị retry và không được cache.
        PermanentFailurePriceAdapter permanent =
                new PermanentFailurePriceAdapter();
        RecordingRetryPause noRetry = new RecordingRetryPause();
        RecordingTraceSink failureTrace = new RecordingTraceSink();

        PriceLookup permanentGraph = new TracingPriceLookup(
                new CachingPriceLookup(
                        new RetryingPriceLookup(permanent, 3, noRetry)),
                failureTrace);
        boolean rejected = false;
        try {
            new PriceService(permanentGraph).totalVnd(
                    new PriceKey("tenant-A", "SKU-X"), 1);
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        check(rejected, "Lỗi vĩnh viễn bị nuốt");
        check(permanent.calls == 1 && noRetry.nextAttempts.isEmpty(),
                "Đã retry lỗi không được phép retry");
        check(failureTrace.events.equals(Arrays.asList(
                "price.lookup.started", "price.lookup.failed")),
                "Không báo đúng một logical failure");

        // Lỗi tạm thời quá giới hạn attempt phải được ném ra.
        FlakyPriceAdapter unavailable = new FlakyPriceAdapter(10);
        RecordingRetryPause exhaustedRetry = new RecordingRetryPause();
        PriceLookup limited = new RetryingPriceLookup(
                unavailable, 3, exhaustedRetry);
        boolean exhausted = false;
        try {
            limited.priceVnd(new PriceKey("tenant-A", "SKU-Y"));
        } catch (TransientPriceFailure expected) {
            exhausted = true;
        }
        check(exhausted && unavailable.calls == 3,
                "Không giới hạn số attempt");
        check(exhaustedRetry.nextAttempts.equals(Arrays.asList(2, 3)),
                "Retry attempt vượt giới hạn");

        // Validation xảy ra trước khi gọi adapter.
        int callsBeforeInvalid = flaky.calls;
        boolean invalidQuantityRejected = false;
        try {
            service.totalVnd(tenantA, 0);
        } catch (IllegalArgumentException expected) {
            invalidQuantityRejected = true;
        }
        check(invalidQuantityRejected
                        && flaky.calls == callsBeforeInvalid,
                "Validation không chặn lời gọi backend");

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac InfrastructureDecoratorDemo.java InfrastructureDecoratorTest.java
java InfrastructureDecoratorTest
```

Kết quả mong đợi: `PASS`.

### 9.1. Bài test chứng minh điều gì?

- `PriceService` tính tổng dựa trên **giá do dependency cung cấp**; không có kiến thức về cache hay retry.
- Với cùng tenant/SKU, kết quả thành công được cache; hai lần gọi logic chỉ cần ba backend attempts vì lần đầu hai lần thất bại rồi thành công.
- Thay tenant tạo một cache miss; kết quả không bị chia sẻ dựa trên SKU đơn lẻ.
- Trace ghi **mốc logic** mà không đưa input thật vào event.
- Lỗi vĩnh viễn được ném ra ngay, không bị retry; lỗi tạm thời dừng ở giới hạn attempt.
- Validation của service từ chối quantity không hợp lệ **trước khi** gọi lookup.

**Giới hạn:** test không chứng minh thread safety của cache, tính đúng đắn của giá production, timeout mạng, idempotency của payment API hoặc cơ chế log/tracing thực tế. Những đặc điểm đó cần integration test, test đồng thời và kiểm thử adapter với môi trường an toàn.

### 9.2. Nên bổ sung những test nào cho hệ thống thật?

| Rủi ro | Cách kiểm chứng |
| --- | --- |
| Giá thay đổi, cache stale | Fake clock hoặc test TTL/invalidation với nguồn giá có version. |
| Nhiều request cùng miss | Concurrency test kiểm tra cache stampede và giới hạn số lần gọi backend. |
| Lỗi hạ tầng khác nhau | Stub timeout, 401, 429, 5xx; xác minh chỉ retry lỗi được phép. |
| Deadline bị vượt | Fake clock/scheduler kiểm tra tổng thời gian và hủy retry. |
| Telemetry gặp sự cố | Cho TraceSink ném lỗi; xác minh chính sách đã định về tác động tới nghiệp vụ. |
| Token/PII trong exception | Dùng marker giả để kiểm tra log, cause chain, tracing attributes và response mapper. |
| Layered retry | Instrument adapter thật để đếm số outbound attempts. |
| Tài nguyên đóng sớm | Test lifecycle/shutdown khi có nhiều request đang chạy. |

## 10. Scope, lifecycle và ownership khi ghép nhiều decorator

Một decorator **giữ tham chiếu** tới delegate. Giữ tham chiếu không đồng nghĩa sở hữu quyền đóng tài nguyên đó.

Trong demo:

- `PriceService` *mượn* `PriceLookup`; không gọi `close()`.
- `TracingPriceLookup` tham chiếu `TraceSink`; không khởi tạo hay quản lý lifecycle của hệ thống tracing.
- `CachingPriceLookup` sở hữu map minh họa, nhưng không sở hữu tài nguyên hạ tầng dùng chung.
- `RetryingPriceLookup` giữ `RetryPause`; phiên bản production có thể cần scheduler/executor được sở hữu tại một scope xác định.
- `FlakyPriceAdapter` không nắm kết nối thật. Nếu thay bằng HTTP client/pool thực, composition root hoặc lifecycle manager phải đóng đúng tài nguyên sau khi ngừng tiếp nhận và xử lý xong các request phụ thuộc.

### 10.1. Không trộn scope theo request vào decorator dùng chung

Một `CachingPriceLookup` dùng chung trong application có thể chứa dữ liệu của nhiều tenant. Điều này chỉ an toàn nếu cache key, phân quyền, retention và concurrency đã được thiết kế đúng. Không truyền một `RequestContext` cụ thể vào singleton decorator rồi giữ nó suốt ứng dụng.

Nếu lookup phụ thuộc quyền/người dùng hiện tại, dữ liệu context nên được truyền qua tham số phù hợp, hoặc tạo graph theo request với scope chính xác. Một factory/provider có thể giúp tạo dependency ngắn hạn, nhưng cần contract ownership và không biến thành Service Locator.

### 10.2. Những thành phần phải thread-safe?

Nếu nhiều request truy cập cùng graph:

- Chính `PriceService` trong demo không có field thay đổi sau constructor, nhưng khả năng dùng đồng thời còn phụ thuộc delegate.
- `CachingPriceLookup` dùng `HashMap` mutable, **không thread-safe**.
- `FlakyPriceAdapter` có bộ đếm và số lần lỗi mutable, chỉ dành cho demo đơn luồng.
- `TracingPriceLookup` không lưu state theo request, nhưng `TraceSink` phải hỗ trợ cách sử dụng đồng thời theo contract.
- `RetryPause` production cần tuân theo quy tắc concurrency, ngắt/hủy và deadline.

DI/container không tự biến các object được inject thành thread-safe. Scope singleton càng khiến nhiều lời gọi cùng chia sẻ instance, nên yêu cầu concurrency càng cần được nêu rõ.

### 10.3. Thứ tự đóng khác thứ tự bọc

Lúc tạo graph, root có thể xây từ `RemotePriceAdapter` rồi bọc retry, cache, trace. Lúc shutdown, cần xét **tài nguyên nào còn phụ thuộc vào tài nguyên nào để hoàn thành cleanup**, chứ không chỉ đảo ngược một cách máy móc thứ tự lớp wrapper.

Với HTTP client, metrics exporter và cache có scheduler, hãy quy định ai sở hữu `close()` và tránh đóng trùng cùng một tài nguyên vì nhiều decorator cùng thấy nó. Dừng công việc đang chạy trước khi đóng các dependency dùng chung.

## 11. Khi nào không cần decorator và khi nào có thể dùng framework?

Không phải mọi logging/cache/retry đều đáng tách thành một decorator:

- Một lệnh log cục bộ giải thích quyết định nghiệp vụ có thể thuộc service nếu nó không gây phụ thuộc hạ tầng không cần thiết và không làm lộ dữ liệu.
- Cache **thuật toán thuần nội bộ** như memoization của một phép tính giá trị không nhất thiết cần một interface hạ tầng.
- Một client SDK có retry đáng tin cậy và đã được cấu hình đúng có thể không cần thêm retry decorator.
- Một framework có thể hỗ trợ interceptor/AOP, filter, cache annotation hoặc resilience policy. Các cơ chế này hữu ích khi được quản lý tập trung và có test kiểm tra thứ tự/phạm vi thật sự.

Tuy nhiên, khi dùng framework:

1. **Không đặt dependency container toàn cục vào service** để tự lấy logger, cache, retry handler.
2. **Kiểm chứng cơ chế proxy:** self-invocation, phương thức không được intercept, thứ tự interceptor và exception mapping có thể ảnh hưởng hành vi tùy framework.
3. **Xác định annotation nào mang chính sách kỹ thuật, chính sách nào mang ngữ nghĩa nghiệp vụ**. Một cache annotation trên truy vấn có dữ liệu tenant không được bỏ qua cache key và scope.
4. **Kiểm tra retry ở tất cả tầng**: SDK, client, service, proxy, queue và gateway; giới hạn tổng attempts.
5. **Đo performance và failure mode thật**, không mặc định framework sẽ đúng khi cấu hình xong.

Java thuần đặc biệt hữu ích để thấy rằng DI container **không phải điều kiện bắt buộc của DI**, và trách nhiệm thiết kế nằm ở hợp đồng cùng cách lắp ghép.

## 12. Quy trình refactor một service đang trộn logging/cache/retry

Giả sử một lớp `InventoryService` trực tiếp import HTTP client, cache manager và retry SDK. Có thể refactor từng bước:

1. **Xác định hành vi nghiệp vụ:** service cần thông tin tồn kho hay cần tự quản lý mạng? Định nghĩa một port `InventoryReader` với dữ liệu vào/ra phù hợp.
2. **Tạo adapter hạ tầng:** `HttpInventoryReader` triển khai port, giữ mã HTTP, xác thực, timeout và mapping exception của SDK.
3. **Chọn kỹ thuật ở ranh giới:** nếu cần cache, tạo `CachingInventoryReader`; nếu retry là an toàn, tạo `RetryingInventoryReader`; nếu cần trace, tạo `TracingInventoryReader`.
4. **Chốt contract:** lựa chọn cache key theo tenant/warehouse/product, TTL/invalidation, lỗi được retry, số attempt, deadline, dữ liệu được phép log, ownership và scope.
5. **Lắp tại composition root:** inject chuỗi đã chọn vào `InventoryService`; loại bỏ import hạ tầng không còn dùng trong service.
6. **Kiểm thử theo nhiều tầng:** unit test nghiệp vụ với fake `InventoryReader`; test decorator bằng fake/clock; integration test cho HTTP adapter thật và cấu hình retry/cache.
7. **Giám sát sau triển khai:** tách logical call khỏi backend attempt, theo dõi cache hit/miss, latency, retry exhaustion và lỗi cleanup. Điều chỉnh policy dựa trên số liệu thật.

Đừng biến việc tách decorator thành mục tiêu tự thân. Nếu một lớp nhận quá nhiều dependency hoặc các policy xung đột, hãy xem lại trách nhiệm service và các ranh giới nghiệp vụ trước khi bổ sung thêm abstraction.

## 13. Bài tập thực hành: báo giá và xác nhận thanh toán

**Bối cảnh:** một ứng dụng có `QuoteService` để đọc giá tham khảo, và `PaymentService` để tạo giao dịch thanh toán. `QuoteService` dùng API đọc giá dễ bị timeout; `PaymentService` gọi API có side effect, có hỗ trợ idempotency key. Dữ liệu giá phụ thuộc tenant, currency và price-list version.

Hãy hoàn thành:

1. **Thiết kế hợp đồng:** định nghĩa `QuoteReader` và `PaymentGateway` theo ý nghĩa nghiệp vụ. Cho biết service nào nên được phép biết raw HTTP status hoặc SDK exception.
2. **Lắp graph báo giá:** tạo `HttpQuoteReader`, `RetryingQuoteReader`, `CachingQuoteReader` và `TracingQuoteReader`. Vẽ thứ tự mà bạn chọn và giải thích nó ảnh hưởng hit/miss, số attempt và trace như thế nào.
3. **Thiết kế cache key:** phải có tối thiểu tenant, currency, product và price-list version. Quy định TTL, invalidation, dung lượng và xử lý thay đổi giá.
4. **Chọn retry policy:** chỉ rõ nhóm lỗi được retry, tổng attempts, timeout/deadline, backoff và cách đo số lần backend thật được gọi. Nêu trường hợp không retry.
5. **Bảo vệ dữ liệu trong telemetry:** định nghĩa mã event và metadata được phép log; giải thích vì sao không dump toàn bộ token/request/exception.
6. **Phân tích thanh toán:** có được áp `RetryingQuoteReader` trực tiếp cho `PaymentGateway.capture` không? Cần bảo đảm idempotency nào và cần test gì khi request thành công nhưng response bị mất?
7. **Viết test Java thuần:** fake adapter thất bại hai lần rồi thành công; assert số attempt, cache hit, keys khác tenant/currency, event log và lỗi cuối cùng.
8. **Quản lý lifecycle:** ai tạo/đóng HTTP client, cache scheduler, metrics exporter? Làm sao ngăn shutdown đóng client khi request còn chạy?
9. **Cân nhắc framework:** nếu DI container/AOP có cache và retry annotation, cần xác minh thứ tự interception, self-invocation và tương thích với scope như thế nào?

**Gợi ý đối chiếu:** `QuoteService` chỉ thấy `QuoteReader`, còn composition root chọn adapter/decorator. Cache key phải bao gồm mọi yếu tố ảnh hưởng giá và quyền truy cập; retry chỉ áp dụng trên thao tác an toàn theo contract. Thanh toán có side effect cần idempotency key được phía nhận tôn trọng, cơ chế xác minh trạng thái và test mất response; không thể dựa vào `catch(timeout) { retry(); }` đơn thuần. Telemetry giới hạn dữ liệu theo allowlist; integration test vẫn cần để kiểm chứng HTTP, status mapping, timeout và resource cleanup thực tế.

**Điểm cần nhớ:** Kết hợp logging, cache và retry với DI là cách **đưa cơ chế hạ tầng ra khỏi logic nghiệp vụ**, không phải giấu mọi thứ vào một container. Hãy giữ hợp đồng nhỏ theo nhu cầu sử dụng, lắp adapter và decorator ở composition root, xác định rõ chính sách cache/retry/log, kiểm thử bằng Java thuần và quản lý scope/vòng đời. Chỉ sau khi hiểu những ranh giới này mới dùng DI container hoặc interceptor để giảm phần wiring lặp lại.
