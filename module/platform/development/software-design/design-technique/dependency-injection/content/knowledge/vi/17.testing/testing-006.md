# Kiểm tra lỗi, timeout và trường hợp phụ thuộc không sẵn sàng

Một đối tượng được cấp dependency đúng cách qua constructor vẫn có thể gặp lỗi khi sử dụng dependency đó. Ví dụ, `ShippingQuoteService` nhận `RateGateway` hợp lệ, nhưng dịch vụ báo giá từ xa có thể **timeout**, từ chối kết nối, trả dữ liệu không hợp lệ hoặc ngừng hoạt động giữa lúc xử lý.

Đây là lý do **kiểm thử Dependency Injection (DI)** không nên chỉ dừng ở việc chứng minh “constructor nhận đúng interface”. Thiết kế DI tốt còn cho phép chúng ta **thay một cộng tác viên thật bằng fake có hành vi lỗi được kiểm soát**; từ đó kiểm tra rằng service có phản ứng đúng trong từng tình huống bất thường.

Trong chương **Kiểm thử** của module Dependency Injection, bài học này tập trung vào ba nhóm tình huống:

1. **Lỗi:** đầu vào sai, phụ thuộc ném lỗi đã dự kiến hoặc lỗi lập trình không nên bị che giấu.
2. **Timeout:** cộng tác viên không hoàn thành trong khoảng thời gian/giới hạn mà ứng dụng cho phép.
3. **Phụ thuộc không sẵn sàng:** tài nguyên từ xa bị ngắt kết nối, từ chối kết nối, service unavailable hoặc hạ tầng chưa sẵn sàng.

Ta sẽ dùng **Java 17 thuần** để kiểm thử bằng fake, không cần DI container hay mock framework. Các ví dụ cũng tách rõ **quyết định nghiệp vụ khi lỗi** khỏi **cơ chế thực thi deadline và quản lý tài nguyên**.

## 1. Phải phân loại lỗi trước khi quyết định xử lý

Không phải mọi exception đều có cùng ý nghĩa. Trong ứng dụng xử lý nghiệp vụ, tối thiểu cần phân biệt:

| Nhóm | Ví dụ | Ý nghĩa | Phản ứng thường phù hợp |
|---|---|---|---|
| **Đầu vào không hợp lệ** | `quantity <= 0`, thiếu mã đơn | Caller gửi dữ liệu sai hợp đồng | Từ chối sớm; không gọi dependency từ xa |
| **Không tìm thấy dữ liệu nghiệp vụ** | Không có sản phẩm, đơn không tồn tại | Kết quả nghiệp vụ có thể được dự kiến | Trả kết quả/từ chối theo hợp đồng use case |
| **Timeout** | Quá thời hạn chờ phản hồi | Không có kết quả kịp thời; chưa chắc phía xa không xử lý | Áp dụng chính sách timeout, cancellation/retry nếu an toàn |
| **Phụ thuộc không sẵn sàng** | Connection refused, service unavailable | Không thể dùng collaborator tại thời điểm đó | Fail fast, trả lỗi tạm thời hoặc degrade có chủ đích |
| **Dữ liệu phản hồi sai hợp đồng** | Phí âm, thiếu trường bắt buộc | Kết quả từ collaborator không hợp lệ | Báo lỗi tích hợp/contract; không tự coi là timeout |
| **Lỗi lập trình / invariant** | `NullPointerException`, trạng thái nội bộ sai | Có thể là bug hoặc tiền điều kiện chưa được bảo vệ | Giữ nguyên tín hiệu lỗi; không bắt rồi biến thành thành công |

**Timeout không đồng nghĩa chắc chắn thao tác ở phía xa đã thất bại.** Nếu yêu cầu chuyển tiền timeout sau khi gửi, máy chủ có thể đã hoàn tất giao dịch dù client không nhận phản hồi. Vì vậy không được tự động retry mọi thao tác, nhất là thao tác gây side effect, nếu chưa có idempotency key và chính sách đối soát phù hợp.

Ngược lại, không phải lỗi nào cũng cần dừng toàn bộ ứng dụng. Một dịch vụ chỉ cung cấp *ước tính phí giao hàng* có thể cho phép trả **ước tính tạm thời**, nhưng hệ thống trừ tiền hoặc xác minh quyền truy cập có thể cần **fail closed**, không được tự giả định thành công.

## 2. DI làm các tình huống lỗi kiểm thử được như thế nào?

Không có DI, service có thể tự tạo client hoặc tra cứu một registry toàn cục:

```java
// Phác họa phản ví dụ: dependency bị tạo bên trong use case.
final class ShippingQuoteService {
    Quote quote(QuoteRequest request) {
        RateGateway gateway = new HttpRateGateway(/* config */);
        return gateway.fetch(request);
    }
}
```

Khi muốn mô phỏng timeout, test sẽ phải điều khiển network, thay đổi cấu hình toàn cục hoặc phụ thuộc vào server thật. Test dễ chậm và khó ổn định.

Với constructor injection, service chỉ biết hợp đồng:

```java
final class ShippingQuoteService {
    private final RateGateway gateway;

    ShippingQuoteService(RateGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
    }
}
```

Test có thể truyền từng fake:

```java
RateGateway healthy = request -> new RemoteRate(25_000L);

RateGateway timeout = request -> {
    throw new RateTimedOutException("simulated timeout");
};

RateGateway unavailable = request -> {
    throw new RateUnavailableException("simulated outage");
};
```

Cả ba cùng thực hiện interface `RateGateway`. Sự thay đổi nằm ở **cách collaborator phản hồi**, không nằm ở cách tạo service. Composition root production có thể truyền implementation HTTP thật, còn test truyền lambda/fake.

Điểm cần nhớ: **DI chỉ tạo điều kiện thay thế dependency; chính sách phản ứng khi lỗi vẫn phải được định nghĩa trong use case hoặc collaborator chuyên trách.** Một fake ném exception chưa đủ; test phải khẳng định kết quả, ngoại lệ, số lần gọi và tài nguyên được giải phóng phù hợp với hợp đồng.

## 3. Thiết kế chính sách fallback không che giấu sự cố

Trong ví dụ, tính năng báo giá vận chuyển có hai kiểu kết quả:

- **Giá xác nhận (confirmed):** nhận được giá từ `RateGateway`.
- **Giá ước tính (estimated):** tạm tính bằng chính sách địa phương khi gateway timeout hoặc không sẵn sàng.

Đây là **quyết định nghiệp vụ có điều kiện**: kết quả ước tính phải được gắn nhãn, không được trình bày như một mức giá đã xác nhận. Ở bước thanh toán cuối cùng, hệ thống có thể yêu cầu lấy lại giá xác nhận thay vì dùng ước tính.

Bảng hành vi mong đợi:

| Tình huống | Có gọi fallback? | Kết quả cần thấy |
|---|---:|---|
| Gateway trả giá hợp lệ | Không | `CONFIRMED`, đúng giá từ gateway |
| Gateway ném lỗi timeout đã phân loại | Có | `ESTIMATED_TIMEOUT`, có nhãn là ước tính |
| Gateway báo không sẵn sàng | Có | `ESTIMATED_UNAVAILABLE`, có nhãn là ước tính |
| Request sai | Không | Ném `IllegalArgumentException` trước khi gọi gateway |
| Gateway trả dữ liệu vi phạm hợp đồng | Không mặc định | Báo lỗi thay vì âm thầm chuyển sang giá khác |
| Có bug bất ngờ trong service | Không | Lỗi phải được nhìn thấy để sửa |

Nếu fallback bản thân thất bại, ta không nên chuyển một lỗi thành công giả. Ví dụ estimator trả số âm thì đó là lỗi của chính sách dự phòng, không phải giá hợp lệ.

**Không nên dùng `catch (Exception ignored)` hoặc `catch (RuntimeException e)` để luôn trả một con số.** Cách đó che cả lỗi lập trình, lỗi cấu hình, gián đoạn luồng và những thay đổi contract chưa được xử lý.

## 4. Ví dụ Java 17 hoàn chỉnh: xử lý lỗi được phân loại

Lưu **toàn bộ** chương trình sau vào `FailureHandlingDemo.java`. Chương trình chứa interface, các exception có ý nghĩa, service với chính sách fallback rõ ràng, và một adapter có khả năng giới hạn thời gian chờ. Không cần Spring, JUnit hay thư viện ngoài.

```java
import java.util.Objects;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class FailureHandlingDemo {

    // Dữ liệu của một lần yêu cầu báo giá.
    record QuoteRequest(String zone, int weightKg) {
        QuoteRequest {
            if (!"LOCAL".equals(zone) && !"REMOTE".equals(zone)) {
                throw new IllegalArgumentException("Unknown zone");
            }
            if (weightKg <= 0) {
                throw new IllegalArgumentException(
                    "weightKg must be positive");
            }
        }
    }

    // Contract phản hồi của gateway.
    record RemoteRate(long amountVnd) {
        RemoteRate {
            if (amountVnd < 0) {
                throw new IllegalArgumentException(
                    "Remote rate must not be negative");
            }
        }
    }

    enum QuoteKind {
        CONFIRMED,
        ESTIMATED_TIMEOUT,
        ESTIMATED_UNAVAILABLE
    }

    record Quote(long amountVnd, QuoteKind kind) {
        Quote {
            if (amountVnd < 0) {
                throw new IllegalArgumentException(
                    "Quote must not be negative");
            }
            Objects.requireNonNull(kind, "kind");
        }
    }

    // Lỗi hạ tầng đã được adapter phân loại.
    static final class RateTimedOutException extends RuntimeException {
        RateTimedOutException(String message) {
            super(message);
        }

        RateTimedOutException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class RateUnavailableException extends RuntimeException {
        RateUnavailableException(String message) {
            super(message);
        }

        RateUnavailableException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    @FunctionalInterface
    interface RateGateway {
        RemoteRate fetch(QuoteRequest request);
    }

    @FunctionalInterface
    interface EstimatePolicy {
        long estimate(QuoteRequest request);
    }

    static final class ShippingQuoteService {
        private final RateGateway gateway;
        private final EstimatePolicy estimator;

        ShippingQuoteService(
                RateGateway gateway, EstimatePolicy estimator) {
            this.gateway = Objects.requireNonNull(gateway, "gateway");
            this.estimator = Objects.requireNonNull(
                estimator, "estimator");
        }

        Quote quote(QuoteRequest request) {
            Objects.requireNonNull(request, "request");

            try {
                RemoteRate rate = Objects.requireNonNull(
                    gateway.fetch(request),
                    "gateway must not return null");
                return new Quote(
                    rate.amountVnd(), QuoteKind.CONFIRMED);
            } catch (RateTimedOutException timeout) {
                return estimate(
                    request, QuoteKind.ESTIMATED_TIMEOUT);
            } catch (RateUnavailableException unavailable) {
                return estimate(
                    request, QuoteKind.ESTIMATED_UNAVAILABLE);
            }
        }

        private Quote estimate(
                QuoteRequest request, QuoteKind reason) {
            long amount = estimator.estimate(request);
            if (amount < 0) {
                throw new IllegalStateException(
                    "Estimator returned a negative amount");
            }
            return new Quote(amount, reason);
        }
    }

    // Adapter minh họa cơ chế chờ có thời hạn ở biên hạ tầng.
    static final class TimeoutRateGateway implements RateGateway {
        private final RateGateway delegate;
        private final ExecutorService executor;
        private final long timeoutMillis;

        TimeoutRateGateway(
                RateGateway delegate,
                ExecutorService executor,
                long timeoutMillis) {
            this.delegate = Objects.requireNonNull(
                delegate, "delegate");
            this.executor = Objects.requireNonNull(
                executor, "executor");
            if (timeoutMillis <= 0) {
                throw new IllegalArgumentException(
                    "timeoutMillis must be positive");
            }
            this.timeoutMillis = timeoutMillis;
        }

        @Override
        public RemoteRate fetch(QuoteRequest request) {
            final Future<RemoteRate> future;

            try {
                future = executor.submit(
                    () -> delegate.fetch(request));
            } catch (RejectedExecutionException rejected) {
                throw new RateUnavailableException(
                    "Rate executor is unavailable", rejected);
            }

            try {
                return future.get(
                    timeoutMillis, TimeUnit.MILLISECONDS);

            } catch (TimeoutException timeout) {
                future.cancel(true);
                throw new RateTimedOutException(
                    "Rate lookup exceeded " + timeoutMillis + " ms",
                    timeout);

            } catch (InterruptedException interrupted) {
                future.cancel(true);
                Thread.currentThread().interrupt();
                // Không biến cancellation của caller thành giá dự phòng.
                throw new IllegalStateException(
                    "Caller interrupted while waiting for rate",
                    interrupted);

            } catch (ExecutionException execution) {
                Throwable cause = execution.getCause();
                if (cause instanceof RuntimeException runtime) {
                    throw runtime;
                }
                if (cause instanceof Error fatal) {
                    throw fatal;
                }
                throw new RateUnavailableException(
                    "Unexpected checked gateway failure", cause);
            }
        }
    }

    public static void main(String[] args) {
        // Composition root: tạo executor và cấp dependency.
        ExecutorService ioExecutor = Executors.newFixedThreadPool(2);

        try {
            RateGateway remote = request ->
                new RemoteRate(
                    Math.addExact(
                        12_000L,
                        Math.multiplyExact(
                            request.weightKg(), 3_000L)));

            RateGateway limited = new TimeoutRateGateway(
                remote, ioExecutor, 500);

            EstimatePolicy localEstimate = request ->
                Math.addExact(
                    10_000L,
                    Math.multiplyExact(
                        request.weightKg(), 2_000L));

            ShippingQuoteService service =
                new ShippingQuoteService(
                    limited, localEstimate);

            System.out.println(
                service.quote(new QuoteRequest("LOCAL", 3)));

        } finally {
            // Demo: không để thread pool tồn tại sau chương trình.
            ioExecutor.shutdownNow();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac FailureHandlingDemo.java
java FailureHandlingDemo
```

Kết quả dự kiến khi gateway trả lời kịp thời:

```text
Quote[amountVnd=21000, kind=CONFIRMED]
```

Kết quả cho thấy composition root chọn một `RateGateway` cụ thể, bọc nó bằng adapter timeout, rồi cấp adapter và `EstimatePolicy` cho `ShippingQuoteService`. Service không cần biết HTTP, executor hoặc cách mở kết nối.

### Đọc các ranh giới trách nhiệm trong ví dụ

`QuoteRequest` là dữ liệu của **từng lần gọi**. Việc kiểm tra zone và khối lượng không liên quan đến kết nối mạng, nên được thực hiện ngay khi tạo request.

`RateGateway` là **hợp đồng hành vi**. Trong production, implementation có thể dùng HTTP client thực với connect/read timeout được cấu hình. Trong test, lambda hoặc fake có thể trả giá hoặc ném một exception đã phân loại.

`TimeoutRateGateway` là **adapter hạ tầng** có nhiệm vụ giới hạn thời gian chờ. Nó không quyết định có được trả ước tính hay không; trách nhiệm đó thuộc chính sách của `ShippingQuoteService`.

`EstimatePolicy` được inject riêng. Test có thể thay nó bằng fake để xác minh **khi nào fallback được gọi**, thay vì phải đoán xem con số trả về đến từ nguồn nào.

`QuoteKind` giúp caller biết giá là **xác nhận** hay **ước tính vì sự cố**. Không có chuyện service lặng lẽ thay giá nhưng vẫn tuyên bố đã nhận phản hồi thật.

### Giới hạn có chủ đích của adapter thời gian chờ

`Future.get(timeout, ...)` giới hạn **thời gian thread gọi chờ kết quả**, nhưng `future.cancel(true)` chỉ gửi tín hiệu interrupt cho tác vụ. Nó **không bảo đảm socket hay tác vụ bên dưới ngừng ngay**, nếu code I/O không hỗ trợ hủy hoặc không kiểm tra interruption. Vì vậy:

- Với HTTP client, database driver hoặc message client thật, cần cấu hình **timeout ở chính client/transport** theo API được hỗ trợ.
- Với tổng request deadline, có thể cần kết hợp connect timeout, read/request timeout và ngân sách thời gian còn lại; chỉ một con số chờ tại wrapper không bảo đảm giới hạn toàn bộ quy trình.
- Executor phải có chính sách về kích thước pool, hàng đợi, khi quá tải và shutdown. `newFixedThreadPool(2)` trong ví dụ có hàng đợi không giới hạn; đây là **lựa chọn tối giản để minh họa**, không phải cấu hình chịu tải mặc định cho production.
- `ExecutorService` được tạo tại composition root; `TimeoutRateGateway` chỉ **mượn** nó, nên adapter không tự đóng executor dùng chung.
- Trong thực tế, `shutdownNow()` là yêu cầu hủy best-effort, không bảo đảm mọi task đã kết thúc. Shutdown có thể phải chờ có deadline và báo lỗi nếu tài nguyên chưa dừng.

Điểm quan trọng nhất: **kiểm thử lỗi không được giả định mọi timeout đều có thể chủ động ngắt sạch tác vụ xa**, và không được dùng kết quả timeout để kết luận phía xa chưa thực hiện side effect.

## 5. Kiểm thử bằng fake: mỗi nhánh có một kết quả xác định

Lưu `FailureHandlingCheck.java` cạnh file ví dụ. Chương trình này dùng `main` và `AssertionError`, không cần JUnit. Test chủ động cho fake ném exception để kiểm tra **chính sách phản ứng**, không phụ thuộc độ trễ thật của mạng hoặc scheduler.

```java
import java.util.concurrent.atomic.AtomicInteger;

public final class FailureHandlingCheck {
    public static void main(String[] args) {
        var request = new FailureHandlingDemo.QuoteRequest(
            "LOCAL", 2);

        AtomicInteger fallbackCalls = new AtomicInteger();
        FailureHandlingDemo.EstimatePolicy fakeEstimate = input -> {
            fallbackCalls.incrementAndGet();
            if (!"LOCAL".equals(input.zone())
                    || input.weightKg() != 2) {
                throw new AssertionError(
                    "Unexpected request passed to fallback");
            }
            return 15_000L;
        };

        // 1. Thành công: không được gọi fallback.
        AtomicInteger gatewayCalls = new AtomicInteger();
        FailureHandlingDemo.RateGateway healthy = input -> {
            gatewayCalls.incrementAndGet();
            return new FailureHandlingDemo.RemoteRate(21_000L);
        };

        var healthyService = new FailureHandlingDemo.ShippingQuoteService(
            healthy, fakeEstimate);

        var confirmed = healthyService.quote(request);
        if (confirmed.amountVnd() != 21_000L
                || confirmed.kind()
                    != FailureHandlingDemo.QuoteKind.CONFIRMED
                || gatewayCalls.get() != 1
                || fallbackCalls.get() != 0) {
            throw new AssertionError(
                "Healthy path used fallback or wrong amount");
        }

        // 2. Timeout: cho phép ước tính nhưng phải gắn nhãn.
        FailureHandlingDemo.RateGateway timedOut = input -> {
            throw new FailureHandlingDemo.RateTimedOutException(
                "simulated deadline");
        };

        var timeoutService = new FailureHandlingDemo.ShippingQuoteService(
            timedOut, fakeEstimate);
        var timeoutResult = timeoutService.quote(request);

        if (timeoutResult.amountVnd() != 15_000L
                || timeoutResult.kind()
                    != FailureHandlingDemo.QuoteKind.ESTIMATED_TIMEOUT
                || fallbackCalls.get() != 1) {
            throw new AssertionError(
                "Timeout policy was not applied");
        }

        // 3. Phụ thuộc không sẵn sàng: lý do phải phân biệt timeout.
        FailureHandlingDemo.RateGateway unavailable = input -> {
            throw new FailureHandlingDemo.RateUnavailableException(
                "simulated outage");
        };

        var unavailableService =
            new FailureHandlingDemo.ShippingQuoteService(
                unavailable, fakeEstimate);
        var unavailableResult = unavailableService.quote(request);

        if (unavailableResult.amountVnd() != 15_000L
                || unavailableResult.kind()
                    != FailureHandlingDemo.QuoteKind.ESTIMATED_UNAVAILABLE
                || fallbackCalls.get() != 2) {
            throw new AssertionError(
                "Unavailable policy was not applied");
        }

        // 4. Bug không nằm trong nhóm đã cho phép fallback.
        FailureHandlingDemo.RateGateway buggy = input -> {
            throw new IllegalStateException("programming bug");
        };

        boolean bugPropagated = false;
        try {
            new FailureHandlingDemo.ShippingQuoteService(
                buggy, fakeEstimate).quote(request);
        } catch (IllegalStateException expected) {
            bugPropagated =
                "programming bug".equals(expected.getMessage());
        }

        if (!bugPropagated || fallbackCalls.get() != 2) {
            throw new AssertionError(
                "Unexpected exception was hidden");
        }

        // 5. Request sai phải bị từ chối khi tạo,
        // không biến thành sự cố từ gateway.
        boolean invalidRejected = false;
        try {
            new FailureHandlingDemo.QuoteRequest(
                "LOCAL", 0);
        } catch (IllegalArgumentException expected) {
            invalidRejected = true;
        }
        if (!invalidRejected) {
            throw new AssertionError("Invalid request was accepted");
        }

        // 6. Fallback lỗi không được biến thành một báo giá giả.
        FailureHandlingDemo.EstimatePolicy brokenEstimate =
            input -> -1L;

        boolean badEstimateRejected = false;
        try {
            new FailureHandlingDemo.ShippingQuoteService(
                timedOut, brokenEstimate).quote(request);
        } catch (IllegalStateException expected) {
            badEstimateRejected = expected.getMessage()
                .contains("negative amount");
        }
        if (!badEstimateRejected) {
            throw new AssertionError(
                "Invalid fallback price was accepted");
        }

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac FailureHandlingDemo.java FailureHandlingCheck.java
java FailureHandlingCheck
```

Kết quả dự kiến: `PASS`.

Test này chứng minh đồng thời:

1. Đường thành công **không dùng fallback**.
2. Timeout và unavailable đều được xử lý theo **những nhãn kết quả khác nhau**.
3. Lỗi lập trình không bị bắt nhầm thành một báo giá hợp lệ.
4. Đầu vào sai bị từ chối bằng hợp đồng dữ liệu, trước khi có lời gọi hạ tầng.
5. Fallback phải tuân thủ bất biến của chính nó.

Trong môi trường test chuyên nghiệp, các điều kiện tương tự có thể được viết bằng JUnit, AssertJ hoặc mock framework, nhưng **constructor injection** vẫn là nền tảng cho khả năng thay cộng tác viên.

## 6. Kiểm tra timeout mà không viết test chậm và dễ lỗi

Một cách kiểm thử thiếu ổn định là làm fake `Thread.sleep(1000)` rồi đoán rằng thao tác phải timeout sau vài chục mili giây. Kết quả phụ thuộc tải CPU, scheduler, tốc độ máy CI và việc thread có bị gián đoạn hay không.

Hãy **tách hai loại test**:

| Loại test | Muốn chứng minh | Cách phù hợp |
|---|---|---|
| **Unit test chính sách khi timeout** | Service bắt đúng `RateTimedOutException` và thực hiện fallback đã quy định | Fake ném exception ngay lập tức, không chờ thời gian thực |
| **Test adapter deadline** | Adapter có thật sự giới hạn thời gian chờ và gửi yêu cầu hủy không? | Fake có thể bị chặn bằng `CountDownLatch`, đồng bộ hóa rõ, timeout đủ biên |
| **Integration test với transport** | Connect/read timeout và cancellation của HTTP/database client có hoạt động? | Test server hoặc hạ tầng kiểm soát được, có giới hạn thời gian tổng |
| **End-to-end dưới tải** | Hệ thống xử lý outage và cạn tài nguyên thế nào? | Test kịch bản quá tải, queue, thread pool và quan sát tài nguyên |

Nếu dùng `Clock` hoặc nguồn thời gian trừu tượng, một số logic liên quan tới **deadline nghiệp vụ** có thể được kiểm tra bằng clock cố định hoặc clock điều khiển được. Tuy nhiên, **đo thời gian chờ của I/O thực** không đơn giản chỉ cần thay `Clock`: cơ chế timeout của `Future.get` hoặc client transport sử dụng đồng hồ và lịch thực thi riêng. Đừng gắn unit test chính sách với đồng hồ thật khi không cần.

### Lưu ý về cancellation và interruption

Trong adapter ví dụ, `InterruptedException` được xử lý bằng cách:

```java
future.cancel(true);
Thread.currentThread().interrupt();
throw new IllegalStateException(
    "Caller interrupted while waiting for rate", interrupted);
```

Ta **khôi phục interrupt flag** để lớp phía trên có thể nhận biết lời gọi đã bị ngắt. Service chỉ catch `RateTimedOutException` và `RateUnavailableException`, nên nó không coi một lần caller bị cancel là lý do tự động trả giá ước tính.

Ở hệ thống bất đồng bộ, cancellation có thể được thể hiện bằng `CancellationException`, cancellation token, future bị hủy hoặc cơ chế riêng của framework. Ngữ nghĩa cụ thể cần được nêu trong contract và test; tránh bắt mọi lỗi rồi tiếp tục thực hiện nghiệp vụ đã bị hủy.

## 7. Kiểm tra dependency không sẵn sàng ở những thời điểm khác nhau

Một dependency có thể không sẵn sàng **trước khi lắp graph**, **trong quá trình khởi động** hoặc **sau khi ứng dụng đã phục vụ request**.

### Trường hợp A — Thiếu dependency ngay khi lắp ghép

`ShippingQuoteService` cần hai collaborator bắt buộc:

```java
new ShippingQuoteService(null, estimator);
```

Constructor từ chối `null` bằng `Objects.requireNonNull`. Đây là **lỗi lắp ghép/cấu hình**, không phải “remote unavailable”. Không nên cho phép tạo service không hợp lệ rồi fallback trong lần gọi đầu tiên.

Một DI container cũng có thể báo thiếu registration khi khởi động hoặc khi resolve, tùy cách cấu hình và eager/lazy initialization. Việc bắt lỗi sớm tới đâu cần kiểm tra theo container cụ thể.

### Trường hợp B — Hạ tầng không sẵn sàng lúc startup

Composition root có thể thực hiện readiness check trước khi mở listener hoặc worker:

```text
Đọc cấu hình
     │
     ▼
Tạo RateGateway, EstimatePolicy, ShippingQuoteService
     │
     ▼
Kiểm tra những dependency bắt buộc cho việc nhận công việc
     │
     ├── lỗi bắt buộc → không mở nhận việc; cleanup tài nguyên đã tạo
     │
     └── đạt yêu cầu → mở nhận request/queue
```

Có những hệ thống chấp nhận hoạt động suy giảm ngay từ startup; có hệ thống phải từ chối nhận việc khi database chính không kết nối được. **Mức độ bắt buộc của dependency là quyết định nghiệp vụ**, không phụ thuộc interface có được inject hay không.

Readiness check thành công chỉ cho biết tình trạng **ở thời điểm kiểm tra**. Nó không đảm bảo dependency còn sẵn sàng sau 10 giây. Lúc vận hành, service vẫn phải xử lý lỗi tại điểm sử dụng.

### Trường hợp C — Mất kết nối giữa lúc xử lý

Ngay cả sau khi graph đã lắp hợp lệ, `RateGateway.fetch(...)` có thể timeout hoặc từ chối kết nối. Đó là lý do cần unit test các nhánh lỗi ở `ShippingQuoteService` và integration test cho adapter/network client.

Nếu phụ thuộc là kho giao dịch bắt buộc, ứng dụng có thể trả trạng thái lỗi tạm thời và đánh dấu không ready, **không được bịa kết quả thành công**. Nếu phụ thuộc là nguồn thông tin bổ sung, hệ thống có thể bỏ qua với nhãn degraded theo chính sách. Quyết định phải được tài liệu hóa và kiểm thử riêng.

## 8. Retry: thử lại không phải phản ứng mặc định với mọi lỗi

Retry có thể hữu ích trước lỗi **tạm thời**, nhưng có rủi ro:

- Tăng tải lên hệ thống đang sự cố.
- Kéo dài thời gian chờ và vượt deadline của request.
- Lặp lại thao tác có side effect.
- Làm mất khả năng phân biệt lỗi cấu hình vĩnh viễn với lỗi tạm thời.

Một chính sách retry cần tối thiểu:

1. **Điều kiện được phép retry:** timeout/unavailable có thể retry nếu nghiệp vụ và transport cho phép; lỗi input không nên retry.
2. **Số lần và ngân sách thời gian:** giới hạn số lần thử, kiểm soát timeout tổng và backoff.
3. **Idempotency:** nếu request có tác dụng phụ, phải biết retry có an toàn không.
4. **Quan sát:** log/metrics để biết số lần thử và kết quả cuối cùng.
5. **Cancellation:** khi caller hủy hoặc deadline tổng hết, không tiếp tục retry vô hạn.

Sơ đồ:

```text
Caller yêu cầu
      │
      ▼
Kiểm tra input
      │
      ▼
Gọi dependency
      │
      ├── thành công ───────────────► trả kết quả thật
      │
      ├── lỗi không retry được ────► báo lỗi / chính sách riêng
      │
      └── lỗi tạm thời
              │
              ├── còn ngân sách + retry an toàn
              │          │
              │          └── backoff → gọi lại
              │
              └── hết ngân sách ───► fallback hoặc báo lỗi rõ
```

Nếu thêm retry vào ví dụ báo giá, nên cân nhắc một `RetryingRateGateway` bọc `RateGateway` ở **tầng hạ tầng**. `ShippingQuoteService` vẫn tập trung vào quyết định nghiệp vụ cuối cùng: trả giá thật hay giá ước tính được gắn nhãn. Việc lựa chọn adapter và policy retry diễn ra tại **composition root**.

Đừng áp dụng retry trực tiếp lên toàn bộ `ShippingQuoteService.quote(...)` nếu điều đó có thể khiến cả phần nghiệp vụ hoặc thao tác ghi nhận bị thực hiện nhiều lần ngoài ý muốn.

## 9. Fallback, circuit breaker và trạng thái suy giảm

Timeout và unavailable thường đi cùng các cơ chế chịu lỗi khác, nhưng các khái niệm này không đồng nghĩa:

| Cơ chế | Vai trò | Điều cần kiểm thử |
|---|---|---|
| **Timeout/deadline** | Giới hạn thời gian chờ | Trả lỗi đúng loại khi quá hạn; không giữ vô hạn thread/tài nguyên |
| **Retry** | Thử lại những lỗi tạm thời có thể retry | Số lần tối đa, backoff, không retry lỗi input/cancellation |
| **Circuit breaker** | Tạm chặn lời gọi tới dependency đang lỗi nhiều | Ngưỡng mở, thời gian thử lại, trạng thái half-open và metrics |
| **Fallback** | Cung cấp hành vi thay thế được nghiệp vụ cho phép | Chỉ kích hoạt với lỗi đúng loại; gắn nhãn kết quả; không che bug |
| **Bulkhead** | Giới hạn ảnh hưởng của dependency tới tài nguyên chung | Độ lớn pool/queue, lỗi quá tải, giải phóng slot |
| **Readiness** | Xác định khả năng tiếp tục nhận công việc | Chế độ degraded, stop/resume admission khi điều kiện thay đổi |

Không nên thêm đủ mọi cơ chế chỉ để làm ứng dụng “ổn định hơn”. Mỗi cơ chế có trạng thái, deadline và lỗi riêng. Một circuit breaker mở có thể báo lỗi *đã từ chối gọi* mà không hề chạm tới network; application cần quyết định trường hợp đó có được xử lý như unavailable hay không.

Với chức năng báo giá, fallback là **ước tính**, không phải phí cuối cùng. Với xác minh tài khoản, phân quyền hay thanh toán, fallback có thể bị cấm. **Chính sách chịu lỗi phải phù hợp với hậu quả nghiệp vụ của một kết quả sai.**

## 10. Kiểm thử tương tác và tài nguyên khi dependency lỗi

Không chỉ kiểm tra giá trị trả về, ta còn cần xét **hành vi phụ**:

- Service có gọi gateway **một lần** hay vô tình gọi nhiều lần?
- Khi gateway thành công, estimator có bị gọi không cần thiết không?
- Khi gateway ném lỗi, service có giữ resource, lock hoặc thread chưa được đóng không?
- Khi một lời gọi bị cancel, các thao tác tiếp theo có còn được phép chạy không?
- Khi shutdown, ai dừng request/worker trước và ai đóng client/executor sau?

Nếu một collaborator có session ngắn hạn, có thể bọc nó bằng `AutoCloseable`:

```java
interface RateSession extends AutoCloseable {
    long fetchAmount(String zone);

    @Override
    void close();
}

interface RateSessionFactory {
    RateSession open();
}

final class SessionBasedRateGateway {
    private final RateSessionFactory sessions;

    SessionBasedRateGateway(RateSessionFactory sessions) {
        this.sessions = Objects.requireNonNull(sessions);
    }

    long fetchAmount(String zone) {
        try (RateSession session = sessions.open()) {
            return session.fetchAmount(zone);
        }
    }
}
```

*Đoạn này minh họa cấu trúc khi đã có `import java.util.Objects;`, không thuộc file demo chính.*

Một fake session có thể tăng các bộ đếm `open`, `fetch` và `close`. Để mô phỏng lỗi, cho `fetchAmount(...)` ném exception. Test cần xác nhận `close()` vẫn chạy đúng một lần. `try-with-resources` hỗ trợ việc đó; nếu `close()` cũng ném exception, lỗi đóng có thể được đưa vào `suppressed exceptions`.

Nếu `sessions.open()` thất bại **trước khi trả về session**, factory có trách nhiệm dọn những tài nguyên đã cấp phát một phần. Nếu client hoặc executor là **dùng chung toàn ứng dụng**, một request không được tự đóng nó khi gặp timeout; việc đóng thuộc composition root/container khi shutdown, sau khi các công việc liên quan đã dừng.

## 11. Bảng ca kiểm thử có thể áp dụng cho mọi dependency

Một ma trận nhỏ giúp tránh chỉ test “happy path”:

| ID | Điều kiện đưa vào fake | Kỳ vọng chính | Kỳ vọng phụ |
|---|---|---|---|
| T1 | Trả kết quả hợp lệ | Trả kết quả xác nhận | Không gọi fallback |
| T2 | Ném timeout đã phân loại | Kết quả lỗi hoặc fallback được cho phép | Gắn nhãn timeout, không che giấu |
| T3 | Ném unavailable | Kết quả lỗi hoặc chế độ suy giảm đúng policy | Gắn nhãn unavailable |
| T4 | Ném lỗi không dự kiến | Không tuyên bố thành công | Lỗi được giữ, có khả năng quan sát |
| T5 | Trả dữ liệu sai contract | Từ chối dữ liệu | Không biến dữ liệu sai thành kết quả hợp lệ |
| T6 | Input sai | Từ chối trước khi gọi remote | Gateway không được gọi |
| T7 | Fallback thất bại | Báo lỗi fallback | Không che bằng giá trị mặc định vô căn cứ |
| T8 | Retry đang chạy bị cancel | Dừng theo chính sách cancellation | Không tiếp tục gọi remote vô hạn |
| T9 | Task timeout nhưng transport chưa hủy được | Trả lỗi thời hạn, quản lý tài nguyên có giới hạn | Không cạn thread/queue sau nhiều lỗi |
| T10 | Startup readiness thất bại | Không mở nhận việc | Cleanup các tài nguyên đã tạo |
| T11 | Request hỏng giữa session | Đóng request/session đúng owner | Không đóng tài nguyên dùng chung của app |

Không phải mọi hàng đều cần viết trong **một** unit test. Nên đặt test chính sách trong lớp nghiệp vụ, test deadline trong adapter, và test resource/lifecycle tại ranh giới composition. Cách chia này vừa kiểm thử đầy đủ vừa giảm test phụ thuộc vào network hoặc thời gian thực.

## 12. Những hiểu nhầm thường gặp

| Hiểu nhầm hoặc cách làm sai | Hệ quả | Cách cải thiện |
|---|---|---|
| “Đã inject đúng dependency thì không cần test lỗi” | Bỏ qua outage và timeout ở runtime | Test các nhánh lỗi qua fake và adapter |
| Dùng `Thread.sleep` dài trong mọi unit test timeout | Test chậm, flaky trong CI | Fake ném timeout ngay để test policy; test timer riêng |
| Bắt mọi `RuntimeException` rồi trả fallback | Che lỗi lập trình và hợp đồng sai | Chỉ catch các lỗi có chính sách xử lý rõ |
| Timeout thì chắc chắn phía xa không xử lý | Có thể retry trùng thao tác | Dùng idempotency/đối soát cho tác vụ có side effect |
| Gọi `Future.cancel(true)` là chắc chắn dừng I/O | Task có thể vẫn giữ socket/thread | Dùng timeout transport, cancellation thực tế và pool giới hạn |
| Mỗi request tự tạo executor mới | Tốn thread, khó shutdown | Inject/executor do root sở hữu hoặc client chuyên dụng |
| Retry mọi lỗi không giới hạn | Thêm tải và tăng độ trễ | Giới hạn lần thử, deadline, backoff và lỗi được phép retry |
| Luôn fallback khi xác minh quyền hoặc thanh toán | Kết quả sai gây hậu quả nghiêm trọng | Fail closed khi nghiệp vụ yêu cầu |
| Test chỉ kiểm tra không ném exception | Không thấy kết quả bị gắn nhãn sai | Assert value, kind, interaction count và side effect |
| Coi readiness startup là đảm bảo không bao giờ lỗi | Lỗi hạ tầng có thể xảy ra sau startup | Xử lý lỗi tại điểm sử dụng và theo dõi health |
| Service tự gọi container để lấy fake | Ẩn phụ thuộc và làm test khó thiết lập | Constructor injection tường minh |
| Quên đóng session sau khi timeout/lỗi | Rò tài nguyên | Thiết kế ownership và kiểm tra close ở đường lỗi |

## 13. Bài tập thực hành

**Bài tập 1 — Không gọi fallback khi thành công.** Dựa trên `FailureHandlingCheck`, tạo fake gateway trả giá 0 VND và fake estimator tăng counter. Kiểm tra kết quả `CONFIRMED` và counter của estimator bằng 0. Giải thích vì sao giá bằng 0 là hợp lệ theo contract của ví dụ, dù hệ thống thực tế có thể yêu cầu giá dương.

**Bài tập 2 — Phản hồi sai hợp đồng.** Tạo `RateGateway` trả `null`. Kiểm tra `ShippingQuoteService.quote(...)` không trả ước tính mà báo lỗi. Phân tích vì sao dữ liệu không hợp lệ khác với timeout và không được dùng fallback một cách mặc định.

**Bài tập 3 — Phân biệt timeout với unavailable.** Viết một fake ném `RateTimedOutException` và một fake ném `RateUnavailableException`. Khẳng định hai loại `QuoteKind` khác nhau. Nếu muốn hiển thị thông báo cho người dùng, viết một lớp trình bày nhận `QuoteKind` thay vì để use case phải in trực tiếp.

**Bài tập 4 — Trường hợp bị ngắt.** Viết test cho adapter có công việc bị chặn và caller bị interrupt. Kiểm tra interrupt flag được khôi phục và service không biến cancellation thành kết quả `ESTIMATED_TIMEOUT`. Dùng cơ chế đồng bộ như `CountDownLatch` để biết task đã bắt đầu, tránh dựa vào `Thread.sleep`.

**Bài tập 5 — Thử retry có giới hạn.** Viết một `RetryingRateGateway` nhận `RateGateway`, giới hạn tối đa hai lần thử và chỉ retry lỗi unavailable có thể thử lại. Dùng fake đếm số lần gọi để kiểm tra khi thành công ở lần thứ hai, khi thất bại cả hai lần và khi request bị cancel. Chưa cần backoff thực trong unit test; có thể inject một `Sleeper` fake hoặc scheduler trừu tượng.

**Bài tập 6 — Resource cleanup.** Thêm session factory và fake session có bộ đếm `close`. Cho `fetch` ném timeout. Kiểm tra session được đóng, đồng thời executor dùng chung vẫn còn do application root quản lý.

**Bài tập 7 — Thảo luận nghiệp vụ.** So sánh hai chức năng: hiển thị **ước tính phí vận chuyển** và thực hiện **chuyển khoản ngân hàng**. Chức năng nào có thể có fallback? Chức năng nào cần idempotency khi retry? Nêu điều kiện để người dùng không hiểu nhầm kết quả tạm thời là kết quả cuối cùng.

### Tự kiểm tra

1. DI giúp kiểm thử dependency không sẵn sàng bằng cách nào?
2. Vì sao unit test policy timeout không cần chờ một mạng thật bị trễ?
3. Timeout khác unavailable ở điểm nào, và có thể xử lý giống nhau trong mọi nghiệp vụ không?
4. Vì sao cần phân biệt kết quả `CONFIRMED` với `ESTIMATED_TIMEOUT`?
5. Nếu caller bị ngắt trong lúc chờ `Future.get`, có nên âm thầm trả ước tính không?
6. Vì sao retry thao tác có side effect sau timeout tiềm ẩn nguy cơ thực hiện trùng?
7. Ai chịu trách nhiệm đóng một executor dùng chung và ai đóng session theo request?
8. Một DI container tự động giải quyết constructor có thay thế kiểm thử timeout và cleanup không?

**Gợi ý:** (1) inject fake có hành vi lỗi; (2) fake ném exception ngay để thử logic, còn timer được test riêng; (3) timeout là không có kết quả kịp hạn, unavailable là không thể sử dụng dependency, chính sách tùy nghiệp vụ; (4) caller phải biết độ tin cậy của giá; (5) không mặc định, cần tôn trọng cancellation; (6) phía xa có thể đã xử lý; (7) owner ứng dụng và owner request tương ứng; (8) không.

## Ghi nhớ

- **Constructor injection giúp kiểm thử lỗi có thể lặp lại:** thay collaborator bằng fake trả thành công, ném timeout, báo unavailable hoặc phát sinh lỗi không dự kiến.
- **Phân loại lỗi trước khi quyết định xử lý.** Đầu vào sai, timeout, unavailable và bug không phải một nhóm; chỉ fallback khi chính sách nghiệp vụ cho phép.
- **Timeout không chứng minh thao tác từ xa thất bại.** Cancellation, retry và idempotency phải được thiết kế theo tác dụng phụ thực tế.
- **Tách unit test policy khỏi test deadline/transport.** Fake ném lỗi để test hành vi; test việc chờ/hủy và quản lý pool ở tầng adapter hoặc integration.
- **Scope và ownership vẫn quan trọng khi có sự cố:** request đóng tài nguyên của request, còn composition root/container quản lý các client và executor dùng chung.
- **Java thuần đủ để thực hành DI có kiểm thử:** dùng constructor injection, fake, bộ đếm tương tác, kết quả có nhãn và test các nhánh lỗi trước khi mở rộng sang DI container.
