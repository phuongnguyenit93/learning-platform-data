# Thử lại có giới hạn theo cơ chế của adapter hoặc ứng dụng

## 1. Mục tiêu bài học

Trong Spring Cloud Function, logic nghiệp vụ có thể được xây dựng bằng `Supplier`, `Function` và `Consumer`, đăng ký trong `FunctionCatalog`, ghép thành pipeline và gọi qua Java, HTTP, hệ thống sự kiện hoặc serverless. Khi vận hành, lời gọi tới database có thể timeout, HTTP client có thể gửi lại yêu cầu và broker có thể giao lại message. Nếu không giới hạn retry hoặc retry sai vị trí, hệ thống có thể nhân tải, ghi trùng và khó xác định trạng thái xử lý.

Trong chương **Độ tin cậy**, bài **Thử lại có giới hạn theo cơ chế của adapter hoặc ứng dụng** giải thích cách thiết kế retry có chủ đích và không đánh đồng các cơ chế của từng adapter.

Sau bài này, bạn có thể:

- Phân biệt lần thực thi đầu, retry, redelivery, reinvocation và Reactor resubscription.
- Xác định lớp sở hữu retry: application, HTTP client, Spring Cloud Stream binder hoặc nền tảng serverless.
- Chỉ retry lỗi có khả năng tạm thời và biết xử lý khi hết lượt.
- Thiết lập số lượt, backoff, jitter, timeout, deadline và retry budget.
- Dùng `retryWhen` của Reactor cho đúng Publisher và đúng loại lỗi.
- Tránh retry cả pipeline khiến side effect đã commit bị lặp lại.
- Thiết kế idempotency key, uniqueness và transaction tại storage.
- Kiểm thử số attempts, lỗi cuối, tác dụng phụ và hành vi của adapter thật.

> **Lưu ý:** Spring Cloud Function cung cấp hợp đồng và composition của các hàm, **không tự định nghĩa một chính sách retry thống nhất** cho HTTP, messaging hay serverless. Retry cụ thể phụ thuộc vào ứng dụng, adapter, binder, phiên bản và cấu hình triển khai.

## 2. Retry có giới hạn là gì?

**Retry** là gọi lại một thao tác thất bại với kỳ vọng nguyên nhân có thể tự hồi phục. Một chính sách retry đáng tin cậy phải trả lời:

1. **Khi nào retry?** Lọc theo loại lỗi hoặc tín hiệu hạ tầng.
2. **Retry bao nhiêu lần?** Phân biệt tổng `attempts` với số `retries`.
3. **Chờ bao lâu?** Fixed delay, exponential backoff, jitter.
4. **Retry cái gì?** Chỉ lời gọi DB hay cả `validate|price|save`?
5. **Có đủ thời gian không?** Deadline, timeout và retry budget.
6. **Hết lượt thì sao?** Truyền lỗi, trả response, DLQ/quarantine hoặc khôi phục.
7. **Chạy lại có an toàn không?** Idempotency và trạng thái commit.

Ví dụ:

~~~text
Attempt 1 (lần đầu)  → timeout
Đợi 100 ms
Attempt 2 (retry #1) → timeout
Đợi 200 ms
Attempt 3 (retry #2) → thành công

Tổng: 3 attempts = 1 lần đầu + 2 retries.
~~~

Tên cấu hình có thể dùng semantics khác nhau. Ví dụ `maxAttempts=3` trong một hệ thống thường chỉ *tổng số lần thử*, còn `Retry.max(2)` của Reactor cho phép *hai lần retry thêm*. Không nên hoán đổi hai con số mà không kiểm tra ý nghĩa.

### 2.1. Retry, redelivery và resubscription khác nhau

| Khái niệm | Điều gì diễn ra? | Ai kiểm soát? |
|---|---|---|
| Local retry | Gọi lại một thao tác cụ thể | Application/library |
| Reactor retry | Subscribe lại Publisher upstream | `retry`/`retryWhen` |
| Broker redelivery | Message được giao lại sau lỗi hoặc chưa ack | Broker/binder |
| Serverless reinvocation | Nền tảng gọi lại handler | Trigger/cloud platform |
| HTTP resend | Client gửi request mới sau timeout | Client/SDK/người dùng |

Một consumer có thể thử xử lý message ba lần **trong cùng một lần nhận**, rồi broker vẫn giao lại message đó ở vòng sau. Giới hạn retry nội bộ không có nghĩa message chỉ được thấy đúng ba lần trên toàn hệ thống.

## 3. Phân loại lỗi trước khi retry

Retry cùng input sai không chữa được validation error. Hãy xác định rõ loại lỗi.

| Loại lỗi | Ví dụ | Retry cùng input? | Lý do |
|---|---|---|---|
| Input invalid | Quantity 0, JSON sai cấu trúc | Thường không | Dữ liệu không đổi |
| Authorization | Không có quyền | Thường không | Không thay chính sách quyền |
| Conflict | Cùng key nhưng payload khác | Không mù quáng | Cần quyết định nghiệp vụ |
| Lỗi lập trình | `NullPointerException` không dự kiến | Thường không | Lặp bug vẫn lỗi |
| Hạ tầng tạm thời | DB timeout, HTTP 503 | Có điều kiện | Dịch vụ có thể phục hồi |
| Rate limit | HTTP 429 | Có điều kiện | Tuân theo `Retry-After` và giới hạn |
| Timeout sau commit | Mất response ghi DB | Chỉ nếu idempotent | Có thể đã lưu thành công |
| Client cancellation | Ngắt kết nối | Không mặc định | Có thể không cần kết quả |

Đây là nguyên tắc, không phải luật bất biến. Một HTTP 404 có thể tạm thời trong hệ thống eventual consistency nhưng chỉ retry khi có lý do nghiệp vụ vững chắc.

### 3.1. Không coi mọi Exception là transient

~~~java
try {
    store.save(quote);
} catch (Exception ex) {
    // Sai: thử lại bất kể nguyên nhân, không giới hạn.
}
~~~

Ngoại lệ có thể biểu thị dữ liệu sai, conflict unique key, network timeout hay bug. Một adapter storage nên phân loại lỗi hạ tầng **thật sự có thể phục hồi** và giữ cause. Không đổi mọi exception thành “temporary” chỉ để bộ lọc retry chấp nhận.

## 4. Chọn tầng sở hữu retry

Một yêu cầu có thể đi qua nhiều tầng:

~~~text
HTTP client / SDK       (có thể retry)
         |
         v
HTTP adapter / gateway  (có thể timeout)
         |
         v
Spring Cloud Function
validate → calculate → save
                          |
                          v
                  DB client (có thể retry)

Hoặc một đường khác:

Broker → Stream binder → Function → Store
Cloud trigger → Serverless adapter → Function → Store
~~~

Không phải mọi tầng trong sơ đồ cùng tồn tại trong một request. Phải xác định đường thực tế đang dùng.

### 4.1. Application-level retry

Ứng dụng có thể:

- Gắn Reactor `retryWhen(...)` trên một `Mono`/`Flux`.
- Dùng wrapper gọi lại một port I/O.
- Cấu hình HTTP client/SDK để retry một outbound request.
- Dùng Spring Retry khi dự án có dependency/cấu hình phù hợp.

Ưu điểm là biết được ngữ nghĩa lỗi và có thể giới hạn retry vào một thao tác. Nhược điểm là dễ gây **nested retries** nếu adapter cũng thử lại.

### 4.2. Adapter-level retry

Adapter hoặc nền tảng có thể quản lý retry/redelivery:

- Spring Cloud Stream consumer binding có chính sách retry theo binding.
- HTTP client hoặc gateway có thể resend request.
- Serverless trigger có thể gọi lại invocation.
- Broker có thể giao lại message khi consumer không xác nhận.

Adapter hiểu delivery lifecycle nhưng có thể không biết DB đã commit hay lỗi validation không nên retry. Vì vậy cần truyền đúng loại lỗi, idempotency và kiểm thử transport.

### 4.3. Phối hợp nhiều tầng

**Nên xác định một tầng retry chính cho mỗi phạm vi thất bại.** Nếu hai tầng cùng retry, kiểm tra giới hạn tổng.

~~~text
HTTP client: tối đa 3 attempts
DB wrapper: tối đa 3 attempts cho mỗi request

=> Một yêu cầu logic có thể gây tối đa 9 lần gọi DB.
~~~

Nếu còn broker redelivery hoặc một outer retry khác, số lần thực thi có thể tăng tiếp. Sự cố thực tế có thể kết thúc sớm hơn, nhưng thiết kế phải lường kịch bản xấu nhất.

## 5. Backoff, jitter, timeout và deadline

Retry dồn dập có thể khiến một dịch vụ đang quá tải nhận thêm nhiều yêu cầu ngay khi nó yếu nhất.

| Chiến lược | Hành vi | Đánh đổi |
|---|---|---|
| Retry ngay | Không đợi | Dễ gây tải dồn |
| Fixed delay | Mỗi lần đợi bằng nhau | Đơn giản nhưng dễ đồng bộ thời điểm |
| Exponential backoff | Khoảng đợi tăng dần | Giảm sức ép khi lỗi kéo dài |
| Backoff + jitter | Khoảng đợi có dao động ngẫu nhiên | Giảm hiện tượng retry đồng loạt |
| Server-directed | Tôn trọng `Retry-After` nếu phù hợp | Cần giới hạn/kiểm chứng delay |

Ví dụ một lịch exponential:

~~~text
Retry #1: 100 ms
Retry #2: 200 ms
Retry #3: 400 ms
Retry #4: 800 ms
Dừng tăng khi đạt trần, ví dụ 2 giây.
~~~

Jitter làm khoảng chờ thực tế dao động quanh lịch cơ sở. Tổng thời gian xử lý còn gồm **thời gian từng attempt**, không chỉ backoff.

### 5.1. Giới hạn bằng deadline tổng

Nếu invocation còn 500 ms trước timeout nhưng cấu hình backoff lên tới 2 giây, retry không thể hoàn tất đúng hạn.

~~~text
Tổng thời gian ≈ thời gian các attempts
               + tổng thời gian backoff
               + overhead/cleanup/response
~~~

Cần dừng trước deadline đủ sớm để gửi response hoặc ack và lưu trạng thái cần thiết. Một timeout đặt ngoài pipeline có thể hủy subscription, nhưng chưa chắc hủy được side effect blocking đã commit.

### 5.2. Retry storm và retry budget

Hàng nghìn request cùng retry ba lần vẫn có thể nhân tải lên nhiều lần. Backoff/jitter chỉ là một phần giải pháp. Khi cần, dùng rate limit, concurrency limit, circuit breaker, retry budget và cảnh báo theo tỷ lệ retry so với request gốc.

**Ngân sách retry phải được xem ở cấp hệ thống**, không chỉ một phương thức Java.

## 6. Ví dụ xuyên suốt: báo giá và ranh giới lưu dữ liệu

Ta xây dựng pipeline nhận một yêu cầu đơn hàng, xác thực, tính báo giá và lưu. Dữ liệu được chia thành kiểu trước/sau validation.

~~~java
package example.functions;

public final class OrderModels {

    private OrderModels() {}

    public record OrderRequest(
            String orderId,
            Integer quantity) {}

    public record ValidatedOrder(
            String orderId,
            int quantity) {}

    public record Quote(
            String orderId,
            int quantity,
            long totalVnd) {}
}
~~~

Quy tắc ví dụ:

- `orderId` có dạng `ORD-<số>`, chẳng hạn `ORD-42`.
- `quantity` là số nguyên 1..100.
- Đơn giá cố định 125.000 VND.
- Cùng `orderId` và cùng kết quả ghi lại **không tạo bản ghi thứ hai**.
- Cùng `orderId` nhưng nội dung khác là conflict.
- Lỗi validation không được retry; lỗi storage transient có thể retry giới hạn.

~~~text
OrderRequest
     |
     v
validateOrder          (thuần, lỗi input không retry)
     |
     v
calculateQuote         (thuần, không ghi DB)
     |
     v
saveQuote              (side effect, có thể transient)
     |
     v
Hoàn tất hoặc báo lỗi cho adapter
~~~

### 6.1. Ba loại exception ứng dụng

~~~java
package example.functions;

public final class OrderErrors {

    private OrderErrors() {}

    public static class InvalidOrderException
            extends RuntimeException {
        public InvalidOrderException(String message) {
            super(message);
        }
    }

    public static class QuoteConflictException
            extends RuntimeException {
        public QuoteConflictException(String message) {
            super(message);
        }
    }

    public static class TransientStoreException
            extends RuntimeException {
        public TransientStoreException(
                String message, Throwable cause) {
            super(message, cause);
        }
    }
}
~~~

Các loại này biểu thị ý nghĩa chứ không chỉ bọc mọi exception. Adapter JDBC/JPA phải chỉ chuyển những lỗi **được phân loại là tạm thời** thành `TransientStoreException`, còn conflict dữ liệu giữ nguyên loại riêng.

## 7. Function thuần và port ghi

Đăng ký hai Function tính toán:

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.InvalidOrderException;

@Configuration
public class QuoteFunctions {

    @Bean
    public Function<OrderRequest, ValidatedOrder> validateOrder() {
        return input -> {
            if (input == null
                    || input.orderId() == null
                    || !input.orderId().matches("ORD-[0-9]+")
                    || input.quantity() == null
                    || input.quantity() < 1
                    || input.quantity() > 100) {
                throw new InvalidOrderException(
                        "OrderRequest khong hop le");
            }

            return new ValidatedOrder(
                    input.orderId(), input.quantity());
        };
    }

    @Bean
    public Function<ValidatedOrder, Quote> calculateQuote() {
        return order -> new Quote(
                order.orderId(),
                order.quantity(),
                Math.multiplyExact(
                    (long) order.quantity(), 125_000L));
    }
}
~~~

Các Function không phụ thuộc database, broker, HTTP hay scheduler. Với input giống nhau, chúng tạo kết quả như nhau hoặc từ chối theo cùng quy tắc.

Port ghi:

~~~java
package example.functions;

import example.functions.OrderModels.Quote;

public interface QuoteStore {
    void save(Quote quote);
}
~~~

Đăng ký một Consumer cuối nếu muốn sử dụng composition:

~~~java
package example.functions;

import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.Quote;

@Configuration
public class QuoteSinkFunctions {

    @Bean
    public Consumer<Quote> saveQuote(QuoteStore store) {
        return store::save;
    }
}
~~~

### 7.1. Bản lưu in-memory chống trùng để học/test

~~~java
package example.functions;

import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.QuoteConflictException;

@Component
public class InMemoryQuoteStore implements QuoteStore {

    private final ConcurrentHashMap<String, Quote> entries =
            new ConcurrentHashMap<>();

    @Override
    public void save(Quote quote) {
        if (quote == null || quote.orderId() == null) {
            throw new IllegalArgumentException(
                    "Quote khong hop le");
        }

        Quote old = entries.putIfAbsent(
                quote.orderId(), quote);

        if (old != null && !old.equals(quote)) {
            throw new QuoteConflictException(
                    "Cung orderId nhung quote khac nhau");
        }
    }

    public Quote find(String orderId) {
        return entries.get(orderId);
    }

    public int size() {
        return entries.size();
    }

    public void clear() {
        entries.clear();
    }
}
~~~

`putIfAbsent` nguyên tử trong **một JVM**, nhưng không lưu bền vững và không bao phủ nhiều replica. Trong production cần unique constraint/upsert nguyên tử/transaction tại storage thật. Ví dụ không giả định có “exactly-once”.

### 7.2. Ghi lại cùng Quote khác với ghi ID đã bị tái sử dụng

| Yêu cầu | Kết quả in-memory |
|---|---|
| `ORD-42`, quantity 2 lần đầu | Lưu một Quote |
| Lặp `ORD-42`, quantity 2 | Không tạo bản ghi thứ hai |
| `ORD-42`, quantity 3 | Conflict, không âm thầm overwrite |
| `ORD-43`, quantity 2 | Tạo Quote khác |

Đây là quy tắc idempotency minh họa. Nếu ứng dụng thực cho phép cập nhật đơn, phải định nghĩa **version/operation khác** thay vì coi mọi cập nhật là replay.

## 8. Ghép logic bằng FunctionCatalog

Tra cứu phần tính toán qua Spring Cloud Function:

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Service;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.Quote;

@Service
public class QuotePreviewService {

    private final FunctionCatalog catalog;

    public QuotePreviewService(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public Quote preview(OrderRequest request) {
        Function<OrderRequest, Quote> pipeline = catalog.lookup(
                "validateOrder|calculateQuote");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "Missing quote pipeline");
        }

        return pipeline.apply(request);
    }
}
~~~

Biểu thức `validateOrder|calculateQuote` có hợp đồng `Function<OrderRequest,Quote>`. Đó là lõi nghiệp vụ có thể tái sử dụng từ HTTP, message hoặc serverless.

Nếu muốn ghép thêm `saveQuote`:

~~~java
import java.util.function.Consumer;

Consumer<OrderModels.OrderRequest> record =
        catalog.lookup("validateOrder|calculateQuote|saveQuote");

if (record == null) {
    throw new IllegalStateException("Missing record pipeline");
}

record.accept(new OrderModels.OrderRequest("ORD-42", 2));
~~~

Đoạn trên minh họa cách tra cứu trong một method đã được inject `FunctionCatalog catalog`. Vì Consumer cuối không trả giá trị, hợp đồng tổng thể là `Consumer<OrderRequest>`.

**Không có retry chỉ vì đã ghép `validateOrder|calculateQuote|saveQuote`.** `FunctionCatalog` không quyết định số attempts, backoff hoặc DLQ.

### 8.1. Cấu hình chọn pipeline khác cấu hình retry

~~~yaml
spring:
  cloud:
    function:
      definition: "validateOrder|calculateQuote|saveQuote"
~~~

`spring.cloud.function.definition` chọn hàm hoặc composition để adapter sử dụng. Nó không tự tạo HTTP endpoint, destination broker, lịch poll hay retry policy. Mỗi adapter có cơ chế riêng và cần kiểm thử trên phiên bản thực tế.

## 9. Application-level retry với Reactor

Nếu `QuoteStore.save` có thể là I/O blocking, có thể dùng `Mono.fromRunnable` để trì hoãn lời gọi và `Schedulers.boundedElastic()` để không chặn event loop.

~~~java
package example.functions;

import java.time.Duration;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.util.retry.Retry;

import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.TransientStoreException;

@Service
public class QuoteWriter {

    private final QuoteStore store;

    public QuoteWriter(QuoteStore store) {
        this.store = store;
    }

    public Mono<Void> saveWithRetry(Quote quote) {
        return Mono.<Void>fromRunnable(() -> store.save(quote))
                .subscribeOn(Schedulers.boundedElastic())
                .retryWhen(
                    Retry.backoff(2, Duration.ofMillis(100))
                        .maxBackoff(Duration.ofSeconds(1))
                        .jitter(0.5)
                        .filter(error ->
                            error instanceof TransientStoreException));
    }
}
~~~

Phân tích:

- `Mono.fromRunnable` trì hoãn việc `store.save` đến subscription.
- `subscribeOn(boundedElastic)` cô lập I/O blocking, **không biến client blocking thành non-blocking**.
- `Retry.backoff(2, ...)` cho tối đa **hai lần retry thêm**, tức tối đa ba attempts cho một subscription nếu đều thất bại.
- `maxBackoff` giới hạn khoảng đợi; `jitter(0.5)` thêm dao động để giảm retry đồng loạt.
- `filter` chỉ cho phép retry `TransientStoreException`. `InvalidOrderException` và `QuoteConflictException` không được retry bởi policy này.
- Khi hết lượt, Reactor truyền lỗi terminal; dạng exception cuối cùng có thể là wrapper retry exhausted tùy policy/version. Nếu cần xác định hợp đồng lỗi, phải thiết kế rõ cách unwrap/convert và test.

`Mono<Void>` phát `onComplete` khi lưu thành công, hoặc `onError` khi thất bại; nó không phát một giá trị Quote. Adapter dùng Publisher phải đợi kết thúc/quan sát lỗi theo contract, không coi việc tạo Mono là đã lưu thành công.

### 9.1. Chỉ retry lời gọi lưu, không tự retry validation

Ghép phần lõi rồi mới gọi `QuoteWriter`:

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.Quote;

@Service
public class QuoteWorkflow {

    private final FunctionCatalog catalog;
    private final QuoteWriter writer;

    public QuoteWorkflow(
            FunctionCatalog catalog,
            QuoteWriter writer) {
        this.catalog = catalog;
        this.writer = writer;
    }

    public Mono<Quote> process(OrderRequest request) {
        Function<OrderRequest, Quote> core = catalog.lookup(
                "validateOrder|calculateQuote");

        if (core == null) {
            throw new IllegalStateException(
                    "Missing quote pipeline");
        }

        // Validation/tính toán đồng bộ xảy ra trước khi tạo Mono ghi.
        Quote quote = core.apply(request);

        return writer.saveWithRetry(quote)
                .thenReturn(quote);
    }
}
~~~

Với code này, `process(invalidInput)` ném `InvalidOrderException` ngay, trước khi gọi writer. Với input hợp lệ, nó trả `Mono<Quote>`; chỉ khi subscription chạy mới bắt đầu lưu và retry riêng bước `save`.

Việc một service trả `Mono` nhưng vẫn có validation ném trực tiếp có thể là lựa chọn hợp lệ nếu được ghi rõ. Nếu muốn **mọi lỗi đi qua `onError`**, hãy trì hoãn cả bước core một cách chủ động; xem mục tiếp.

### 9.2. Thống nhất lỗi reactive bằng defer khi cần

~~~java
public Mono<Quote> processDeferred(OrderRequest request) {
    return Mono.defer(() -> {
        Function<OrderRequest, Quote> core = catalog.lookup(
                "validateOrder|calculateQuote");

        if (core == null) {
            return Mono.error(
                    new IllegalStateException(
                        "Missing quote pipeline"));
        }

        Quote quote = core.apply(request);
        return writer.saveWithRetry(quote).thenReturn(quote);
    });
}
~~~

Đặt đoạn method vào `QuoteWorkflow` đã khai báo field `catalog` và `writer`. Bên trong `defer`, nếu `core.apply` ném lỗi thông thường, Reactor truyền lỗi đó như `onError` lúc subscribe.

**Cẩn thận với phạm vi retry:** `writer.saveWithRetry(quote)` chỉ retry thao tác lưu, nhưng nếu một caller gắn `.retryWhen(...)` **ngoài `processDeferred`**, toàn bộ nội dung `defer` có thể chạy lại, bao gồm lookup, validation và tính toán. Nếu core có side effect ẩn, hậu quả càng khó dự đoán.

## 10. Lỗi ở pha apply và lỗi ở pha subscribe

Trong Java imperative:

~~~java
Function<OrderModels.OrderRequest, OrderModels.Quote> core =
        new QuoteFunctions().validateOrder()
            .andThen(new QuoteFunctions().calculateQuote());

core.apply(new OrderModels.OrderRequest("ORD-42", 0));
// Ném InvalidOrderException ngay.
~~~

Trong Reactor:

~~~java
Mono<OrderModels.Quote> deferred = Mono.fromCallable(
        () -> core.apply(
            new OrderModels.OrderRequest("ORD-42", 0)));
~~~

Lỗi trong Callable thường xuất hiện như `onError` khi subscribe. Điều này khác với:

~~~java
Mono<OrderModels.Quote> eager = Mono.just(
        core.apply(new OrderModels.OrderRequest("ORD-42", 0)));
~~~

Ở bản `eager`, Java phải tính đối số `core.apply(...)` trước khi gọi `Mono.just` nên exception có thể xảy ra **ngay tại assembly**.

Chọn vị trí retry phải hiểu lỗi có xuất hiện trong Publisher hay **trước khi Publisher được tạo**. Không thể đặt `retryWhen` cho một Publisher chưa được trả vì lời gọi đã ném trực tiếp.

## 11. Retry khi đã hết số lượt

Không nên nuốt lỗi sau lượt cuối:

~~~java
try {
    // Thực hiện lời gọi lưu
} catch (Exception ignored) {
    // Sai: caller tưởng thành công dù lưu chưa xong.
}
~~~

Với Reactor, khi `retryWhen` không còn cho phép thử lại, Publisher phải phát một terminal error (hoặc được chuyển sang một kết quả **được nghiệp vụ cho phép**). Không mặc định `onErrorReturn(quote)` có nghĩa Quote đã lưu thành công.

### 11.1. Phân loại lỗi cuối cùng

| Lỗi cuối | Hành động ứng dụng phù hợp |
|---|---|
| Validation | Từ chối input; không retry |
| Conflict | Báo conflict; không overwrite |
| Storage transient hết lượt | Báo tạm không khả dụng, có thể chuyển sang công việc bền vững |
| Unknown commit | Tra cứu theo idempotency key; không đoán chưa ghi |
| Lỗi lập trình | Ghi nhận/khắc phục code, không che giấu bằng fallback giả |

Nếu cần truyền lỗi gốc sau khi hết lượt Reactor, có thể chọn biến thể xử lý `onRetryExhaustedThrow(...)` trên `RetrySpec` khi phù hợp với phiên bản, đồng thời giữ cause và kiểm thử error contract. Không dựa duy nhất vào việc parse chuỗi thông báo exception để biết đó là timeout hay validation.

## 12. Retry per-item hay toàn bộ Flux?

Trong một pipeline reactive nhận nhiều event, vị trí `retryWhen` ảnh hưởng trực tiếp đến việc **phần tử nào bị xử lý lại**.

### 12.1. Retry bên ngoài có thể phát dữ liệu cũ lần nữa

~~~java
import reactor.core.publisher.Flux;

Flux<Integer> parsed = Flux.just("1", "bad", "3")
        .map(Integer::parseInt)
        .retry(1);
~~~

Subscriber có thể quan sát:

~~~text
onNext(1)
onNext(1)
onError(NumberFormatException)
~~~

Do `retry(1)` subscribe lại toàn bộ upstream, `1` được phát lần hai. Không có cơ chế tự giữ trạng thái “đã xử lý phần tử đầu” khi dùng retry mặc định.

Nếu sau `map` có `doOnNext(store::save)`, side effect cho phần tử trước lỗi cũng có thể lặp lại. Với dữ liệu nghiệp vụ, cần idempotency và phân định phạm vi.

### 12.2. Chỉ retry tác vụ bất đồng bộ của từng phần tử

Ví dụ mỗi message cần gọi một remote service độc lập:

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Flux<String> responses = Flux.just("ORD-1", "ORD-2")
        .concatMap(orderId ->
            remoteService.fetch(orderId)
                .retryWhen(
                    Retry.backoff(2, Duration.ofMillis(100))
                        .filter(error ->
                            error instanceof TransientRemoteException)));
~~~

`remoteService.fetch` là một port giả định trả `Mono<String>`; `TransientRemoteException` là loại lỗi mà adapter đã phân loại là tạm thời. Đoạn mã minh họa sẽ cần những dependency này trong ứng dụng thật.

Với cấu trúc trên, retry của `ORD-2` nằm **trong inner Mono** dành cho `ORD-2`, thay vì tự động phát lại kết quả `ORD-1`. Tuy nhiên, nếu một inner Mono lỗi sau khi hết lượt và không có xử lý per-item, Flux bên ngoài vẫn thường kết thúc bằng `onError`. Muốn các message độc lập tiếp tục, cần quy tắc xử lý lỗi của từng inner.

### 12.3. Cách ly lỗi một message không đồng nghĩa bỏ qua âm thầm

~~~java
Flux<String> responses = Flux.just("ORD-1", "ORD-2")
        .concatMap(orderId ->
            remoteService.fetch(orderId)
                .retryWhen(
                    Retry.max(2).filter(error ->
                        error instanceof TransientRemoteException))
                .onErrorResume(error -> {
                    // Đây chỉ là ví dụ; production phải lưu/quan sát lỗi.
                    return Mono.empty();
                }));
~~~

Ở đây, lỗi sau retry được biến thành một inner Mono rỗng, nên Flux có thể tiếp tục phần tử tiếp theo. Điều này chỉ hợp lệ khi hệ thống cho phép **không phát output** cho message lỗi và đã có cơ chế quarantine/metrics/DLQ. Không mặc định việc biến lỗi thành `Mono.empty()` sẽ báo chính xác cho broker rằng message cần được đưa vào dead-letter.

### 12.4. flatMap, concatMap và concurrency

- `concatMap` xử lý các inner Publisher theo thứ tự, dễ kiểm soát side effect tuần tự.
- `flatMap` có thể xử lý đồng thời; cần giới hạn concurrency và hiểu thứ tự phát kết quả.
- `flatMapSequential` có thể chạy đồng thời nhưng phát theo thứ tự nguồn, đổi lại có buffering.
- Khi có retry trong mỗi inner, tổng số request đến dependency có thể tăng cùng với concurrency.

Chọn operator theo yêu cầu thứ tự, tải và semantics của nghiệp vụ, không chỉ vì cần “bắt được lỗi”.

## 13. Spring Cloud Stream: retry tại consumer binding

Khi dùng Spring Cloud Function với Spring Cloud Stream, một `Consumer<OrderRequest>` có thể được bind tới nguồn message. Tùy binder/phiên bản, Spring Cloud Stream cung cấp cơ chế **consumer retry** ở tầng binding cho các đường xử lý imperative.

Để minh họa **retry do binder sở hữu**, ta dùng một Consumer đồng bộ gọi core và port ghi nhưng **không tự bọc retry**:

~~~java
package example.functions;

import java.util.function.Consumer;
import java.util.function.Function;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;

@Configuration
public class StreamOrderHandler {

    @Bean
    public Consumer<OrderRequest> processOrder(
            @Qualifier("validateOrder")
            Function<OrderRequest, ValidatedOrder> validate,
            @Qualifier("calculateQuote")
            Function<ValidatedOrder, Quote> calculate,
            QuoteStore store) {

        return request -> {
            ValidatedOrder valid = validate.apply(request);
            Quote quote = calculate.apply(valid);
            store.save(quote);
        };
    }
}
~~~

Consumer đồng bộ chỉ trả về sau khi các phương thức ở trên kết thúc hoặc ném lỗi. Điều đó giúp binder có cơ hội quan sát kết quả lời gọi theo contract dành cho consumer imperative.

### 13.1. Cấu hình max-attempts theo binding

Ví dụ YAML minh họa theo quy ước của Spring Cloud Stream 4.x:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: quote-service
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 5000
            back-off-multiplier: 2.0
~~~

Giải thích:

- `processOrder-in-0` là tên input binding theo quy ước functional cho bean `processOrder`.
- `max-attempts: 3` biểu thị tối đa ba lần xử lý trong cơ chế retry consumer được áp dụng, gồm lần đầu và những lần thử thêm.
- Các property `back-off-*` thiết lập khoảng đợi và hệ số tăng cho cơ chế tương ứng.
- `group` quan trọng với semantics subscriber/consumer group của binder, nhưng không phải cơ chế chống ghi trùng ở database.

**Cần kiểm tra trên binder/version thực tế:** Một số binder, loại Function reactive, cấu hình retry/error handler hoặc cách xử lý lỗi có thể dùng cơ chế khác, bỏ qua một số property chung hoặc cần cấu hình riêng. Ví dụ YAML không phải lời bảo đảm mọi broker sẽ thực hiện đúng cùng lịch retry.

### 13.2. Đừng bật retry cả trong binder lẫn consumer mà không có kế hoạch

Nếu binder thực hiện tối đa 3 attempts và bên trong `processOrder` lại gọi `store.save` với 3 attempts, một message có thể gây tối đa 9 lần gọi storage trước khi binder kết luận thất bại.

Trong nhiều trường hợp, **chọn một tầng chính** là hợp lý:

- Binder retry toàn consumer khi operation tương đối ngắn, idempotent và mọi lỗi được phân loại đúng.
- Application retry **riêng một dependency** khi cần bộ lọc lỗi giàu ngữ nghĩa và không muốn lặp toàn Function.
- Có thể phối hợp hai tầng nếu đã tính tổng ngân sách và trường hợp commit chưa rõ, đồng thời có metrics phân tách rõ.

### 13.3. Binder retry không đồng nghĩa broker redelivery

Sau khi binder hết attempts, điều gì xảy ra phụ thuộc error handling và broker:

- Lỗi có thể được đưa tới một error channel/handler.
- Một số binder hỗ trợ dead-letter topic/queue khi cấu hình riêng.
- Message có thể bị requeue/redeliver hoặc bị xử lý theo chính sách khác.
- Hành vi ack/nack phụ thuộc binder và loại consumer.

Không xem `max-attempts: 3` là “đảm bảo message sẽ xử lý tối đa đúng ba lần trong suốt vòng đời” hoặc “sau ba lần chắc chắn nằm trong DLQ”.

## 14. Dead-letter và poison message sau khi hết lượt

**Poison message** là message luôn thất bại với cùng dữ liệu, ví dụ sai schema hoặc `quantity=0`. Nếu adapter retry vô hạn, nó có thể chiếm tài nguyên và cản trở những message khác.

~~~text
Broker
  |
  v
Deserialize
  |
  +-- invalid schema ------------> reject / quarantine / DLQ
  |
  v
Validate
  |
  +-- invalid business input ----> reject / quarantine / DLQ
  |
  v
Persist
  |
  +-- transient failure
          |
          v
      limited attempts
          |
          +-- thành công --------> ack theo binder
          |
          +-- hết lượt ----------> error policy / DLQ / alert
~~~

Cần chọn rõ:

1. Có cho phép bỏ qua message sai không?
2. Có phải lưu lỗi ở DLQ/quarantine để xử lý lại thủ công không?
3. Lỗi lưu tạm thời sau hết lượt sẽ được requeue hay chuyển vào hàng lỗi?
4. Có đảm bảo message ID/correlation ID và thông tin cần điều tra không?
5. Khi replay DLQ, làm sao tránh ghi trùng với những lần đã commit?

Spring Cloud Function không trực tiếp định nghĩa DLQ. Cấu hình DLQ, retry error handler và ack phải theo **binder cụ thể**; không tự sáng tạo một property chung rồi giả định nó hoạt động ở mọi môi trường.

### 14.1. Lỗi payload sai có thể xảy ra trước Function

Nếu JSON không deserialize được thành `OrderRequest`, lỗi có thể xuất hiện **ở converter**, trước khi `validateOrder` được gọi. Khi đó, bộ lọc exception viết trong `QuoteWriter` không thể xử lý lỗi này. Tầng adapter phải có chiến lược riêng cho lỗi chuyển đổi.

### 14.2. Reactive function và consumer retry

Với `Function<Flux<T>,Flux<R>>` hoặc `Consumer<Flux<T>>`, subscription và tín hiệu lỗi có thể được quản lý khác với Consumer đồng bộ. Không nên coi cơ chế retry của binding imperative mặc định bao trùm mọi lỗi phát sau subscription.

Khi dùng reactive Function, cần kiểm thử:

- Ai subscribe nguồn?
- `onError` có được truyền tới binder không?
- Retry xảy ra cho một phần tử, toàn Flux hay cả message delivery?
- Có backpressure, buffering và redelivery nào phát sinh?
- Error/ack xảy ra ở thời điểm nào so với side effect?

Nếu một Consumer tự gọi `subscribe()` rồi trả `accept(...)` ngay, binder có thể không nhìn thấy kết quả bất đồng bộ cuối cùng. Không dùng kiểu này làm nền tảng bảo đảm retry/ack nếu chưa hiểu contract adapter.

## 15. HTTP: retry thuộc client hay phía server?

Trong ứng dụng HTTP, hai phía có trách nhiệm khác nhau:

- **HTTP server/adapter** nhận request, gọi Function, xử lý kết quả/lỗi và trả response.
- **HTTP client/SDK** có thể tự động gửi lại request nếu timeout, mất kết nối hoặc nhận mã trạng thái cho phép retry.
- **Application** phía server có thể retry outbound call đến dependency, nhưng không nên tự xử lý lại toàn bộ request nghiệp vụ mà không có idempotency.

### 15.1. Timeout không chứng minh server chưa làm gì

~~~text
Client --- POST /quotes ---> Server
                              |
                              v
                          save DB (commit)
                              |
                    Response bị mất trên mạng
                              |
Client thấy timeout và retry POST /quotes
~~~

Nếu request thứ hai tạo thêm bản ghi, hệ thống sai dù request đầu đã thành công.

Với API có side effect, dùng một **idempotency key ổn định** qua các lần resend, chẳng hạn `orderId` hoặc một header do API định nghĩa. Server phải kiểm tra key và payload trong storage có khả năng cưỡng chế tính duy nhất.

### 15.2. Khi nào HTTP client nên retry?

| Tình huống | Hướng xử lý |
|---|---|
| Không kết nối được tới server | Có thể retry có giới hạn |
| HTTP 503/502/504 | Có thể retry theo policy và deadline |
| HTTP 429 | Tôn trọng `Retry-After` nếu hợp lệ và có ngân sách |
| HTTP 400 do validation | Không retry cùng payload |
| HTTP 401/403 | Không dùng retry để né bảo mật |
| HTTP 409 conflict | Không retry mù quáng |
| POST đã ghi nhưng response mất | Chỉ resend an toàn với idempotency |

HTTP method không thay thế hoàn toàn hiểu biết nghiệp vụ. GET thường được thiết kế an toàn và idempotent, còn POST có side effect cần đặc biệt thận trọng. Một client có thể retry request ngay cả khi server không cài bất kỳ retry policy nào.

### 15.3. Spring Cloud Function web adapter không tự là HTTP client

`spring.cloud.function.definition` chọn Function được công bố, không cấu hình HTTP client retry hay tự bảo đảm response status cụ thể. Nếu dự án dùng WebClient, RestClient hoặc SDK khác để gọi outbound, hãy cấu hình retry **ở client đó** theo phiên bản và ngữ nghĩa request, không nhầm với FunctionCatalog.

## 16. Serverless: retry theo trigger và giới hạn invocation

Một nền tảng serverless có thể gọi lại function khi invocation thất bại hoặc timeout, nhưng **chính sách khác nhau giữa loại trigger**.

~~~text
Cloud event / queue / HTTP
          |
          v
Serverless adapter
          |
          v
validate → calculate → save
          |
          +-- lỗi → trigger-specific retry / DLQ / failure policy
~~~

Các tình huống cần tính tới:

- Invocation được gọi lại với cùng event ID.
- Mã nguồn chạy ở instance mới, nên cache/in-memory dedupe không đáng tin.
- Lệnh lưu DB có thể đã commit trước khi invocation bị timeout.
- Mỗi invocation có deadline và số lượng concurrency do nền tảng quản lý.
- Handler có thể được gọi qua synchronous HTTP hoặc async queue, với chính sách retry khác nhau.

Không dùng mặc định một `Retry.backoff` dài hơn thời gian còn lại của invocation. Nếu còn 300 ms và một lần backoff cần 1 giây, retry cục bộ sẽ chỉ làm phí thời gian hoặc dẫn đến timeout.

### 16.1. Cấu hình ứng dụng không thay thế trigger

Spring Cloud Function adapter phục vụ việc ánh xạ event/payload tới bean. Số lần cloud platform thử lại, timeout, dead-letter destination và cách nhận trạng thái thất bại thuộc cấu hình trigger/platform.

Vì vậy, cần test **đúng loại trigger đang sử dụng**, không khẳng định “serverless luôn retry ba lần” hay “serverless không bao giờ retry”.

### 16.2. Retry toàn invocation có thể lớn hơn retry Java

Nếu application dùng tối đa 3 attempts cho lưu DB và nền tảng gọi lại cùng invocation thêm 2 lần, cùng yêu cầu logic có thể dẫn tới nhiều lần lưu. Số lần thực tế còn phụ thuộc error handling và trigger; nhưng cách chống trùng phải chịu được trường hợp message/event được gọi lại sau timeout.

## 17. Supplier, Function và Consumer: vị trí retry khác nhau

Spring Cloud Function cho phép ghép nhiều dạng hàm:

~~~text
Supplier<T> → Function<T,R> ⇒ Supplier<R>
Function<T,R> → Consumer<R> ⇒ Consumer<T>
Supplier<T> → Consumer<T> ⇒ Runnable
~~~

Các hợp đồng trên mô tả cấu trúc phép ghép. Khả năng adaptation và cách kích hoạt với từng adapter cần được xác minh theo phiên bản.

### 17.1. Không retry Supplier bừa bãi nếu mỗi get nhận event mới

~~~java
import java.util.function.Supplier;

Supplier<OrderModels.OrderRequest> next =
        () -> queueClient.poll();
~~~

`queueClient` là dependency minh họa. Nếu mỗi lần `get()` lấy **một message khác**, retry toàn `Supplier|get|process` có thể lấy một message mới chứ không thử lại đúng message thất bại.

Khi lỗi nằm ở xử lý một item, cần giữ định danh và payload ổn định, cùng cơ chế ack/requeue của nguồn. Không giả định `Supplier.get()` luôn trả cùng dữ liệu.

### 17.2. Consumer trả void không có nghĩa mọi side effect đã xong

~~~java
import java.util.function.Consumer;

Consumer<OrderModels.Quote> save =
        quote -> quoteStore.save(quote);
~~~

Nếu `quoteStore.save` đồng bộ, `accept` trả về sau khi lời gọi hoàn tất hoặc ném lỗi. Nhưng nếu Consumer khởi động công việc bất đồng bộ rồi trả ngay, adapter có thể không quan sát được lỗi cuối cùng.

Phải chọn loại Function và vòng đời subscription/ack phù hợp. Không giả định một `Consumer<Flux<T>>` tự subscribe là cách có retry an toàn.

### 17.3. Composition không tự tạo retry

`FunctionCatalog.lookup("validateOrder|calculateQuote|saveQuote")` xác định **thứ tự xử lý**, không định nghĩa số lượt thử. Nếu adapter muốn quản lý retry cho chuỗi này, cần bảo đảm exception/error signal được truyền đúng cho adapter; nếu ứng dụng quản lý retry của `saveQuote`, cần tránh lớp adapter lặp lại cùng thao tác ngoài ngân sách.

## 18. Idempotency là điều kiện của retry an toàn

Một phép tính thuần có thể chạy lại mà không tự thay đổi storage. Một lệnh ghi hoặc phát sự kiện thì khác: cùng yêu cầu được gọi lại có thể tạo thêm tác dụng phụ nếu không bảo vệ.

### 18.1. Định nghĩa idempotency theo thao tác nghiệp vụ

**Idempotency** trong xử lý request/event thường có nghĩa: gửi lại **cùng một yêu cầu** với **cùng định danh** không tạo thêm hiệu ứng nghiệp vụ so với lần đầu thành công.

Ví dụ:

~~~text
Request: orderId=ORD-42, quantity=2

Lần 1: lưu Quote(ORD-42,2,250000)
Lần 2: nhận ra cùng orderId và cùng payload
        → trả/kết thúc như lần đã xử lý, không tạo bản ghi mới

Request khác: orderId=ORD-42, quantity=3
        → conflict, không lặng lẽ coi là retry giống lần đầu
~~~

Tính thuần và idempotency không đồng nhất. `calculateQuote` thuần nhưng phép `f(f(x))` không nhất thiết có ý nghĩa; `saveQuote` không thuần nhưng có thể idempotent nếu storage áp đặt tính duy nhất và so sánh payload.

### 18.2. Khóa phải ổn định qua các lần thử

Một HTTP POST có thể dùng `Idempotency-Key` hoặc một `orderId` do nghiệp vụ quản lý. Một event có thể dùng `eventId` cộng phiên bản xử lý. Nhưng yêu cầu quan trọng là:

- Cùng yêu cầu **giữ nguyên key** qua client retry, broker redelivery và serverless reinvocation.
- Key không được tạo mới ngẫu nhiên mỗi lần retry.
- Key phải đủ phạm vi để tránh va chạm giữa tenant/operation khi cần.
- Storage phải biết **cùng key cùng nội dung** và **cùng key nhưng nội dung khác**.
- Key không thay thế kiểm tra quyền hoặc xác thực nguồn input.

Nếu hệ thống xử lý nhiều loại operation, `orderId` có thể chưa đủ; cần kết hợp operation type/version hoặc một request ID có phạm vi thích hợp.

### 18.3. Unique constraint quan trọng hơn SELECT rồi INSERT

Giả sử hai worker đồng thời:

~~~text
Worker A: SELECT ... WHERE order_id='ORD-42' → không thấy
Worker B: SELECT ... WHERE order_id='ORD-42' → không thấy
Worker A: INSERT → thành công
Worker B: INSERT → có thể ghi trùng nếu storage không giới hạn
~~~

Chỉ kiểm tra trước khi ghi không ngăn race condition. Database nên cưỡng chế tính duy nhất bằng index/constraint và thao tác ghi nguyên tử, kèm transaction phù hợp.

Một ví dụ SQL khái niệm (cú pháp cụ thể phụ thuộc database):

~~~sql
CREATE TABLE quote (
    order_id VARCHAR(64) PRIMARY KEY,
    quantity INTEGER NOT NULL,
    total_vnd BIGINT NOT NULL
);
~~~

Có primary key giúp ngăn nhiều dòng cùng `order_id`, nhưng implementation vẫn phải xử lý trường hợp tồn tại:

- Nếu payload giống hệt, có thể coi là replay thành công.
- Nếu payload khác, trả conflict.
- Nếu lệnh ghi báo timeout, **tra cứu lại theo key** khi cần xác nhận trạng thái.

### 18.4. Idempotency không làm mọi side effect thành exactly-once

Một Consumer có thể lưu DB idempotent nhưng còn gửi email, tính phí hoặc publish event. Mỗi side effect có định nghĩa “một lần” khác nhau.

Ví dụ:

~~~text
DB ghi Quote: idempotent
Email gửi thông báo: vẫn có thể gửi 2 bản nếu retry
Message published: có thể bị phát lại
~~~

Nếu yêu cầu toàn bộ workflow đáng tin cậy, cần quản lý riêng ranh giới email/event, có dedupe, outbox hoặc cơ chế điều phối phù hợp.

## 19. Transactional outbox khi cần lưu DB và phát sự kiện

Xét workflow:

~~~text
validate → calculate → save Quote (COMMIT) → publish QuoteCreated
~~~

Nếu process dừng sau commit nhưng trước publish, database có bản ghi nhưng downstream chưa nhận thông báo. Nếu retry cả pipeline, thao tác ghi có thể an toàn nhờ idempotency, nhưng việc publish vẫn có nguy cơ thiếu hoặc trùng.

Một mẫu phổ biến:

~~~text
Trong cùng transaction DB:
    - UPSERT/INSERT Quote theo key
    - INSERT OutboxEvent(quoteId,eventId,payload)
COMMIT
           |
           v
Outbox publisher đọc các bản ghi cần phát
           |
           v
Broker
           |
           v
Consumer downstream xử lý duplicate theo eventId
~~~

Outbox gắn ý định publish với commit nghiệp vụ. Worker gửi có thể phát lại khi timeout. Vì broker/downstream vẫn có thể nhận trùng, **consumer phía nhận** cần idempotency khi phù hợp.

### 19.1. Retry ở bước outbox khác retry toàn nghiệp vụ

Nếu lỗi thuộc quá trình phát outbox, không nên mặc định gọi lại `validateOrder|calculateQuote|saveQuote`. Có thể chỉ retry thao tác publish outbox theo policy, vì dữ liệu nghiệp vụ đã commit.

Điều này minh họa lợi ích của việc chia pipeline thành các trách nhiệm có ranh giới rõ, thay vì ghép mọi side effect vào một Function và gắn retry cuối chuỗi.

## 20. Retry với timeout, circuit breaker và giới hạn đồng thời

Retry không thể thay thế timeout. Một attempt treo vô hạn khiến chính sách “thử lại tối đa ba lần” không bao giờ bước sang attempt thứ hai.

### 20.1. Mỗi attempt cần timeout riêng khi phù hợp

~~~text
Attempt #1: chờ tối đa 500 ms
Backoff: 100 ms
Attempt #2: chờ tối đa 500 ms
Backoff: 200 ms
Attempt #3: chờ tối đa 500 ms

Cần còn đủ ngân sách cho response/ack.
~~~

Thời gian tổng tối đa phụ thuộc implementation, scheduler, cancellation và overhead. Một timeout trên Publisher không chắc hủy ngay một lời gọi JDBC blocking đang chạy; phải kiểm tra timeout hỗ trợ tại client/driver và vòng đời kết nối.

### 20.2. Thứ tự timeout và retry của Reactor

Hai cách đặt operator sau không có cùng ý nghĩa:

~~~java
Mono<String> a = remoteCall
        .timeout(Duration.ofMillis(500))
        .retryWhen(retryPolicy);

Mono<String> b = remoteCall
        .retryWhen(retryPolicy)
        .timeout(Duration.ofMillis(500));
~~~

Trong đó `remoteCall` là `Mono<String>` của dependency, `retryPolicy` là `Retry` đã cấu hình. Với `a`, timeout nằm trong upstream được retry và thường áp dụng cho **từng attempt**. Với `b`, timeout bao toàn bộ chuỗi bao gồm những lần retry và backoff.

Cần xác định ngữ nghĩa mong muốn. Một thiết kế có thể có **timeout per-attempt** và **deadline tổng** ở tầng ngoài, nhưng phải kiểm soát thứ tự và lỗi cuối cùng.

### 20.3. Circuit breaker và rate limit

Khi dependency thất bại trên diện rộng, retry có thể làm tăng quá tải. Một circuit breaker có thể từ chối nhanh khi hệ thống đang hỏng; rate/concurrency limit ngăn số request đồng thời vượt khả năng.

Nếu circuit breaker mở, không nên mặc định retry ngay nhiều lần với cùng kết quả từ chối. Policy nên xét lỗi circuit-open, tổng deadline và ngân sách hệ thống. Các cơ chế này thường nằm ở HTTP client/adapter I/O, không phải mọi Function thuần.

## 21. Cấu hình retry bằng ứng dụng Java imperative

Không phải dự án nào cũng dùng Reactor. Nếu phần lưu đồng bộ và dự án chủ động dùng Spring Retry, có thể cấu hình một `RetryTemplate` cho lời gọi cụ thể.

> Ví dụ dưới đây yêu cầu dependency Spring Retry tương thích (ví dụ `org.springframework.retry:spring-retry`, cùng dependency AOP khi dùng cơ chế annotation). API builder có thể khác theo phiên bản; cần kiểm tra trong dự án.

~~~java
package example.functions;

import org.springframework.retry.support.RetryTemplate;
import org.springframework.stereotype.Service;

import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.TransientStoreException;

@Service
public class BlockingQuoteWriter {

    private final QuoteStore store;
    private final RetryTemplate retry;

    public BlockingQuoteWriter(QuoteStore store) {
        this.store = store;

        this.retry = RetryTemplate.builder()
                .maxAttempts(3)
                .exponentialBackoff(100, 2.0, 1000)
                .retryOn(TransientStoreException.class)
                .build();
    }

    public void save(Quote quote) {
        retry.execute(context -> {
            store.save(quote);
            return null;
        });
    }
}
~~~

Cấu hình `maxAttempts(3)` ở đây biểu thị tổng số lần thử, gồm lần đầu. Phương thức `retryOn` chỉ cho phép retry exception thuộc loại đã chọn. Với lỗi khác, nó truyền lỗi theo cơ chế bình thường.

**Không dùng wrapper blocking này trên event loop** nếu nó đợi backoff và gọi JDBC blocking. Nếu ứng dụng reactive, nên dùng ranh giới I/O/scheduler phù hợp hoặc client thực sự reactive.

### 21.1. Tránh retry ở proxy lẫn trong method

Nếu còn thêm `@Retryable` trên cùng thao tác và Spring Retry dùng AOP proxy, một lời gọi có thể có hai cơ chế retry. Đặc biệt lời gọi nội bộ `this.someMethod()` có thể không đi qua proxy tùy cơ chế AOP, khiến retry không chạy theo kỳ vọng.

Hãy có **một chính sách có thể quan sát được**, kiểm thử số lượt và không dựa vào việc annotation chắc chắn có tác dụng khi thiếu dependency/cấu hình.

### 21.2. Không dùng Thread.sleep trong Function reactive

Một vòng lặp thủ công gọi `Thread.sleep` giữa các attempts có thể chặn thread xử lý request/message. Nó còn khó hủy khi client đã timeout và dễ làm sai tổng deadline.

Với imperative service, một thư viện retry có kiểm soát và cơ chế timeout ở driver/client thường an toàn hơn; với Reactor, dùng `retryWhen` và scheduling phù hợp.

## 22. Bảng lựa chọn cơ chế retry

| Tình huống | Cơ chế ưu tiên cần cân nhắc | Lưu ý bắt buộc |
|---|---|---|
| Gọi DB trực tiếp từ service đồng bộ | RetryTemplate hoặc cơ chế storage có giới hạn | Chỉ transient, idempotent |
| Gọi API bất đồng bộ trong Reactor | `retryWhen` tại inner Publisher | Timeout, jitter, concurrency |
| HTTP client gọi endpoint khác | Retry ở client/SDK | Chỉ status/network phù hợp; deadline |
| Consumer imperative của Spring Cloud Stream | Binder retry theo binding | Phân loại lỗi, binder-specific DLQ/ack |
| Function reactive nhận Flux qua binder | Policy của adapter + per-item operator | Test subscription/error propagation |
| Serverless handler | Trigger retry hoặc app retry ngắn | Deadline, event ID, idempotency |
| Supplier chủ động poll | Chính sách nguồn/adapter | Không lấy event mới khi retry item cũ |
| Lỗi validation | Không retry cùng input | Trả/cách ly lỗi rõ ràng |
| Mất response sau commit | Retry idempotent hoặc tra cứu trạng thái | Unique key, transaction |
| Publish event sau DB commit | Outbox + publisher retry | Dedupe downstream |

**Không có một lựa chọn tối ưu cho mọi trường hợp.** Số attempts thấp nhưng phạm vi quá rộng có thể nguy hiểm hơn số attempts cao hơn nhưng giới hạn ở một thao tác thuần. Hãy thiết kế dựa vào ranh giới side effect và trách nhiệm của từng adapter.

### 22.1. Ví dụ hai phương án thay thế, không nên tự động cộng dồn

Phương án A:

~~~text
processOrder Consumer đồng bộ
  → binder retry maxAttempts=3
  → QuoteStore.save không có retry riêng
~~~

Phương án B:

~~~text
processOrder Consumer hoặc Function reactive
  → binder/application có policy rõ
  → QuoteWriter.retryWhen chỉ retry DB I/O
  → adapter không lặp vô hạn toàn pipeline
~~~

Nếu kết hợp cả A và B, phải ghi rõ lý do, tổng attempts, deadline, idempotency và đường lỗi khi hết lượt.

## 23. Quan sát retry trong production

Không chỉ đo “hàm thành công hay thất bại”. Cần biết hệ thống đã thử bao nhiêu lần, vì sao và tổng thời gian.

Các metric/log nên có:

- `requestId`/`eventId` hoặc idempotency key (đã được kiểm soát để không lộ dữ liệu nhạy cảm).
- Tên operation và bước bị retry, ví dụ `quoteStore.save`.
- Loại lỗi đã được phân loại: invalid, conflict, transient, unknown.
- `attemptIndex`, tổng attempts, backoff và thời gian thực thi.
- Tỷ lệ thành công sau retry, tỷ lệ hết lượt và lượng message vào DLQ.
- Số lần redelivery/reinvocation nếu adapter hỗ trợ ghi nhận.
- Thời gian từ lúc nhận đến lúc ack hoặc trả response.
- Số conflict/số duplicate được dedupe tại storage.

### 23.1. Không log ở mỗi tầng cùng một exception

Một lỗi có thể đi từ database qua retry wrapper, FunctionCatalog và adapter. Nếu mọi nơi đều log stack trace, bạn có thể tạo hàng chục log cho một yêu cầu.

Thay vào đó:

1. Ở retry wrapper, đo số attempts và loại lỗi.
2. Ở ranh giới cuối, log sự kiện thất bại có correlation ID và trạng thái cuối.
3. Ở tầng adapter, ghi mã phản hồi/ack/DLQ theo chính sách.
4. Chỉ log payload nếu được phép, ưu tiên định danh và các field đã giảm thiểu dữ liệu nhạy cảm.

### 23.2. Alert theo tỷ lệ thay vì chỉ tổng lỗi

Nếu tỷ lệ request thành công vẫn cao nhưng retries tăng gấp nhiều lần, dependency có thể đang suy giảm trước khi outage rõ ràng. Theo dõi p95/p99 latency, số attempts trung bình, retry exhaustion và queue lag sẽ có ích hơn chỉ đếm HTTP 500.

### 23.3. Khi nào không nên retry nữa?

Một hệ thống có thể dừng retry sớm vì:

- Đã quá deadline tổng.
- Error không thuộc danh sách có thể retry.
- Circuit breaker đang mở hoặc đã hết retry budget.
- Client đã hủy và không còn nhu cầu xử lý (tùy nghiệp vụ).
- Tác vụ đã commit, cần trả cứu trạng thái thay vì ghi lại.
- Event đã được xử lý theo idempotency key.

Điều này giúp retry là **cơ chế phục hồi có điều kiện**, không phải một vòng lặp bắt buộc đến khi đủ số lượt.

## 24. Unit test: kiểm tra số attempts và loại lỗi được retry

Kiểm thử retry phải xác minh **số lần thật sự gọi dependency**, không chỉ kết quả thành công cuối. Dùng JUnit 5 và `reactor-test` cho các ví dụ sau.

### 24.1. Test thành công sau hai lỗi transient

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.test.StepVerifier;

import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.TransientStoreException;

class QuoteWriterRetryTest {

    @Test
    void retriesTwiceThenSucceeds() {
        AtomicInteger attempts = new AtomicInteger();

        QuoteStore flaky = quote -> {
            int attempt = attempts.incrementAndGet();

            if (attempt < 3) {
                throw new TransientStoreException(
                        "Temporary DB timeout",
                        new IllegalStateException("timeout"));
            }
        };

        QuoteWriter writer = new QuoteWriter(flaky);
        Quote quote = new Quote("ORD-501", 2, 250_000L);

        StepVerifier.create(writer.saveWithRetry(quote))
                .verifyComplete();

        assertEquals(3, attempts.get());
    }
}
~~~

Test này xác nhận `QuoteWriter` đã gọi port tối đa ba lần: lần đầu, retry 1, retry 2. Vì `QuoteWriter` dùng backoff/jitter và scheduler thật, test có thể có độ trễ nhỏ. Khi cần test timing phức tạp, dùng virtual time theo mục 25.

### 24.2. Lỗi conflict không được retry

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.QuoteConflictException;

class ConflictNotRetriedTest {

    @Test
    void conflictFailsAfterOneAttempt() {
        AtomicInteger attempts = new AtomicInteger();

        QuoteStore conflicting = quote -> {
            attempts.incrementAndGet();
            throw new QuoteConflictException(
                    "Same key, different payload");
        };

        QuoteWriter writer = new QuoteWriter(conflicting);

        StepVerifier.create(writer.saveWithRetry(
                new Quote("ORD-502", 2, 250_000L)))
                .expectError(QuoteConflictException.class)
                .verify();

        assertEquals(1, attempts.get());
    }
}
~~~

Điểm mấu chốt: `filter` trong `retryWhen` phải loại `QuoteConflictException`. Nếu mọi exception đều được retry, test này sẽ phát hiện số attempts tăng ngoài mong đợi.

### 24.3. Sau khi hết lượt vẫn báo lỗi

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.TransientStoreException;

class RetryExhaustionTest {

    @Test
    void stopsAfterRetryBudget() {
        AtomicInteger attempts = new AtomicInteger();

        QuoteStore unavailable = quote -> {
            attempts.incrementAndGet();
            throw new TransientStoreException(
                    "Still unavailable",
                    new IllegalStateException("timeout"));
        };

        QuoteWriter writer = new QuoteWriter(unavailable);

        StepVerifier.create(writer.saveWithRetry(
                new Quote("ORD-503", 2, 250_000L)))
                .expectError()
                .verify();

        assertEquals(3, attempts.get());
    }
}
~~~

Test cố ý không giả định class của exception cuối vì Reactor có thể wrap retry exhaustion tùy policy/version. Nếu hợp đồng ứng dụng yêu cầu exception gốc, cấu hình `onRetryExhaustedThrow` và test **chính xác** kiểu lỗi cùng cause.

### 24.4. Lỗi validation không được đi tới store

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.InvalidOrderException;

class ValidationBoundaryTest {

    @Test
    void invalidOrderIsNotPersisted() {
        QuoteFunctions functions = new QuoteFunctions();

        Function<OrderRequest, Quote> core =
                functions.validateOrder()
                         .andThen(functions.calculateQuote());

        AtomicInteger saves = new AtomicInteger();

        Consumer<Quote> store =
                quote -> saves.incrementAndGet();

        Consumer<OrderRequest> pipeline =
                request -> store.accept(core.apply(request));

        assertThrows(InvalidOrderException.class,
                () -> pipeline.accept(
                    new OrderRequest("ORD-504", 0)));

        assertEquals(0, saves.get());
    }
}
~~~

Lỗi invalid phải bị từ chối **trước side effect**, không chỉ không được retry. Assert số lần `store` gọi bằng 0 là bảo đảm quan trọng.

### 24.5. Test idempotency khi cùng yêu cầu bị gửi lại

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.QuoteConflictException;

class QuoteStoreIdempotencyTest {

    @Test
    void repeatedSameRequestCreatesOneEntry() {
        InMemoryQuoteStore store = new InMemoryQuoteStore();

        Quote quote = new Quote("ORD-505", 2, 250_000L);

        store.save(quote);
        store.save(quote);

        assertEquals(1, store.size());
        assertEquals(quote, store.find("ORD-505"));
    }

    @Test
    void sameKeyWithDifferentPayloadIsConflict() {
        InMemoryQuoteStore store = new InMemoryQuoteStore();

        store.save(new Quote("ORD-505", 2, 250_000L));

        assertThrows(QuoteConflictException.class,
                () -> store.save(
                    new Quote("ORD-505", 3, 375_000L)));

        assertEquals(1, store.size());
    }
}
~~~

Bộ test này chỉ xác nhận behavior của **một JVM**. Nó không chứng minh transaction, uniqueness hoặc trạng thái commit khi process chết trong database production.

## 25. Kiểm thử thời gian retry bằng StepVerifier virtual time

Với exponential backoff dài, test dùng thời gian thật có thể chậm và không ổn định. Reactor `StepVerifier.withVirtualTime` cho phép kiểm tra retry có delay mà không phải thật sự đợi từng giây.

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

class RetryVirtualTimeTest {

    @Test
    void succeedsAfterTwoVirtualDelays() {
        AtomicInteger attempts = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Mono.fromCallable(() -> {
                    int n = attempts.incrementAndGet();
                    if (n < 3) {
                        throw new IllegalStateException(
                                "Temporary failure");
                    }
                    return "saved";
                }).retryWhen(
                    Retry.fixedDelay(2, Duration.ofSeconds(1))))
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(2))
                .expectNext("saved")
                .verifyComplete();

        assertEquals(3, attempts.get());
    }
}
~~~

Lưu ý supplier truyền cho `withVirtualTime` **xây dựng Publisher bên trong callback**, để scheduler của các operator thời gian được tạo trong bối cảnh virtual time. Ví dụ dùng `Retry.fixedDelay` cho lịch dễ tính, không có jitter.

### 25.1. Virtual time không thay được integration test I/O

Virtual time kiểm tra lịch retry ở tầng Reactor, nhưng **không mô phỏng được**:

- Database commit và mất xác nhận.
- Broker redelivery, ack và DLQ.
- Cloud invocation timeout thực.
- Thread JDBC blocking không hủy được đúng thời điểm.
- Rate limit hoặc circuit breaker được điều phối từ một service bên ngoài.

Cần kiểm thử các failure mode này ở ranh giới integration phù hợp.

### 25.2. Kiểm tra retryWhen theo loại lỗi

Đừng chỉ có test `transient → success`. Nên có cả:

- `invalid → fail ngay`.
- `conflict → fail ngay`.
- `transient luôn thất bại → dừng khi hết lượt`.
- `transient hồi phục sau retry → thành công`.
- `unknown error → không tự bị gán thành transient`.
- `timeout sau commit → retry idempotent hoặc tra cứu trạng thái`.

Đó là ma trận tối thiểu để ngăn một thay đổi refactor vô ý biến retry thành `catch-all`.

## 26. Integration test FunctionCatalog và giới hạn của test

Một Spring Boot application trong cùng package:

~~~java
package example.functions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QuoteApplication {

    public static void main(String[] args) {
        SpringApplication.run(QuoteApplication.class, args);
    }
}
~~~

Khi các bean `QuoteFunctions`, `QuoteSinkFunctions`, `InMemoryQuoteStore`, `QuoteWorkflow` cùng dependency Spring Cloud Function/Boot Test được đăng ký, có thể kiểm tra composition:

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.InvalidOrderException;

@SpringBootTest(classes = QuoteApplication.class)
class QuoteCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    InMemoryQuoteStore store;

    @Test
    void calculatesQuoteByComposedName() {
        Function<OrderRequest, Quote> pipeline = catalog.lookup(
                "validateOrder|calculateQuote");

        assertNotNull(pipeline);

        assertEquals(
                new Quote("ORD-601", 2, 250_000L),
                pipeline.apply(new OrderRequest("ORD-601", 2)));
    }

    @Test
    void invalidOrderDoesNotReachConsumer() {
        Consumer<OrderRequest> pipeline = catalog.lookup(
                "validateOrder|calculateQuote|saveQuote");

        assertNotNull(pipeline);

        assertThrows(InvalidOrderException.class,
                () -> pipeline.accept(
                    new OrderRequest("ORD-602", 0)));

        assertNull(store.find("ORD-602"));
    }

    @Test
    void repeatedConsumerInvocationIsIdempotent() {
        Consumer<OrderRequest> pipeline = catalog.lookup(
                "validateOrder|calculateQuote|saveQuote");

        assertNotNull(pipeline);

        OrderRequest request = new OrderRequest("ORD-603", 2);

        pipeline.accept(request);
        pipeline.accept(request);

        assertEquals(
                new Quote("ORD-603", 2, 250_000L),
                store.find("ORD-603"));
    }
}
~~~

Lưu ý trong một Spring context có nhiều Function bean, cần chọn đúng definition khi gắn adapter thực tế. Test trên tra cứu catalog tường minh nên không tự xác minh binder đang dùng `processOrder` hoặc expression nào trong cấu hình production.

### 26.1. Test này chứng minh gì và chưa chứng minh gì?

| Test | Đã xác minh | Chưa xác minh |
|---|---|---|
| Unit `QuoteFunctions` | Validation/tính toán độc lập | Runtime catalog, binder |
| Unit `QuoteWriter` | Số attempts tại ứng dụng | Actual DB commit, binder retry |
| Unit `InMemoryQuoteStore` | Dedupe trong JVM | Multiple replica và persistence |
| Catalog integration | Tên/kiểu/thứ tự composition | HTTP status, broker ack |
| HTTP integration | Request body, status, retry client | Broker DLQ hoặc serverless trigger |
| Broker integration | Binder attempts, ack, redelivery, DLQ | Cloud invocation policy |
| Serverless integration | Event mapping, timeout, reinvocation | Transaction của database |
| Fault-injection DB | Ghi nguyên tử, xung đột, commit không rõ | Hoàn toàn mọi sự cố thực tế |

Khi production dùng database thật và nhiều instance, cần test concurrent requests và unique constraint, không chỉ dùng `ConcurrentHashMap`.

### 26.2. Kiểm thử đúng binding processOrder-in-0

Nếu chạy qua Spring Cloud Stream với `definition: processOrder`, bài test adapter nên gửi message thật hoặc dùng test binder/harness phù hợp phiên bản, sau đó cố tình gây lỗi transient và kiểm tra:

1. Function được gọi bao nhiêu lần trong **một lần delivery**?
2. Sau hết lượt, message đi đâu — error handler, DLQ hay requeue?
3. Có redelivery ở lượt nhận tiếp theo không?
4. Ack xảy ra trước hay sau khi side effect hoàn tất?
5. Khi cùng message được phát lại, storage có giữ một kết quả không?
6. Khi validation lỗi, policy có tránh retry vô hạn không?

**Không thể kết luận tính năng binder hoạt động chỉ vì một unit test gọi `Consumer.accept(...)` ba lần.** Test phải sử dụng đúng cơ chế adapter mà ứng dụng triển khai.

## 27. Những lỗi thiết kế retry thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Validation error bị thử lại nhiều lần | Retry không lọc exception | Loại lỗi input khỏi retry |
| `maxAttempts=3` nhưng thấy nhiều hơn ba lần gọi | Binder retry + app retry + broker redelivery | Phân biệt các tầng và tổng attempts |
| HTTP POST gây hai bản ghi | Client resend sau timeout | Idempotency key và unique constraint |
| `retryWhen` làm phát lại phần tử cũ | Resubscribe cả Flux | Đặt retry trong per-item inner Mono |
| Retry phát sinh nhiều request đồng thời | Không có backoff/jitter/concurrency limit | Backoff, jitter, rate limit |
| Chưa thấy retry dù có `retryWhen` | Publisher chưa subscribe hoặc lỗi ném trước khi tạo Publisher | Test subscription, dùng defer/fromCallable khi phù hợp |
| Lỗi DB không được lọc đúng | Exception bị wrap/đổi loại | Bảo toàn cause và phân loại tại adapter |
| Hết lượt nhưng API vẫn trả thành công | `onErrorReturn`/catch nuốt lỗi | Trả trạng thái thất bại đúng |
| Consumer tự subscribe rồi return | Binder không quan sát terminal signal | Tuân theo subscription contract |
| Backoff kéo dài quá deadline | Thiếu ngân sách thời gian | Cấu hình timeout và total deadline |
| Retry làm lỗi nặng thêm khi service down | Retry storm | Circuit breaker, concurrency limit, retry budget |
| Message poison lặp không ngừng | Không có policy DLQ hoặc requeue phù hợp | Phân biệt lỗi cố định, quarantine/DLQ |
| Dùng in-memory dedupe trong serverless | Instance thay đổi hoặc mất state | Idempotency tại storage bền vững |
| Ghi DB rồi publish event mất message | Hai side effect không trong một transaction | Outbox hoặc cơ chế nhất quán phù hợp |
| `@Retryable` không kích hoạt như mong đợi | Proxy/AOP hoặc self-invocation | Kiểm tra dependency, proxy boundary và integration test |

### 27.1. Sai lầm: retry để “tăng độ tin cậy” bất kể nghiệp vụ

Không phải phép thử lại nào cũng tốt. Ví dụ một lệnh chuyển tiền hoặc gửi email có thể đã thành công trước khi trả timeout; nếu caller lặp lại mà không có idempotency, thiệt hại có thể lớn hơn lỗi ban đầu.

Độ tin cậy được cải thiện khi **phục hồi lỗi tạm thời mà vẫn giữ đúng trạng thái**, không phải khi số lượng retry càng cao càng tốt.

### 27.2. Sai lầm: thời gian đợi được tính nhưng thời gian I/O thì không

Một policy có hai backoff 100 ms và 200 ms không có nghĩa tổng xử lý chỉ thêm 300 ms. Nếu mỗi attempt chờ timeout 5 giây, ba attempts có thể mất hơn 15 giây. Cần tổng hợp:

~~~text
attempt 1 timeout + wait + attempt 2 timeout + wait
+ attempt 3 timeout + overhead + response/ack
~~~

Với deadline ngắn hơn, hãy dừng sớm thay vì để request bị hủy giữa một thao tác ghi.

### 27.3. Sai lầm: đổi mọi exception thành lỗi hạ tầng tạm thời

Trong code:

~~~java
catch (Exception ex) {
    throw new OrderErrors.TransientStoreException(
            "Temporary", ex);
}
~~~

Mã này có thể gán nhãn retry cho `IllegalArgumentException`, `QuoteConflictException` hoặc bug. Một adapter lưu dữ liệu nên phân loại **dựa trên loại lỗi thật của database/client**, không gán “temporary” theo mặc định.

### 27.4. Sai lầm: dùng một số lượt cấu hình cho mọi transport

HTTP client, Spring Cloud Stream binder và serverless platform có lifecycle khác nhau. Một tham số `max-attempts` của binder không có nghĩa cloud platform sẽ dừng reinvocation theo đúng giới hạn đó.

Hãy có bảng policy theo từng ranh giới, lưu cùng tài liệu vận hành hoặc cấu hình triển khai, để người vận hành biết message đã được thử ở đâu và vì sao.

## 28. Checklist thiết kế trước production

### 28.1. Hợp đồng lỗi

- [ ] Đã phân biệt input invalid, conflict, transient dependency và unknown error.
- [ ] Lỗi không thể tự phục hồi không bị retry vô hạn.
- [ ] Exception của dependency được chuyển loại có kiểm soát, giữ cause khi cần.
- [ ] Sau khi hết lượt, lỗi được truyền hoặc ánh xạ thành kết quả thất bại đúng nghiệp vụ.

### 28.2. Giới hạn và phạm vi

- [ ] Đã định nghĩa tổng attempts và số retries trong từng cơ chế.
- [ ] Có backoff/jitter thích hợp, giới hạn khoảng đợi tối đa.
- [ ] Có deadline tổng, timeout mỗi attempt và ngân sách response/ack.
- [ ] Đã xác định **ai sở hữu retry chính** ở mỗi đường gọi.
- [ ] Đã tính số lần gọi tối đa do nhiều tầng retry/redelivery tạo ra.
- [ ] `retryWhen` chỉ bao Publisher phù hợp, không vô tình lặp side effect khác.

### 28.3. An toàn dữ liệu

- [ ] Idempotency key ổn định qua request resend, broker redelivery và reinvocation.
- [ ] Storage có unique constraint hoặc thao tác ghi nguyên tử phù hợp.
- [ ] Cùng key nhưng payload khác được báo xung đột rõ.
- [ ] Lỗi không rõ commit được xác minh bằng key/trạng thái thay vì giả định chưa ghi.
- [ ] Nếu ghi DB và publish event, có mô hình nhất quán/outbox khi cần.
- [ ] Consumer downstream có chính sách dedupe nếu message có thể giao trùng.

### 28.4. Adapter và kiểm thử

- [ ] Đã kiểm tra binding name, binder và retry policy thực tế.
- [ ] Đã test converter, ack, requeue và DLQ trên broker tương ứng.
- [ ] Đã test HTTP client retry sau timeout, cùng idempotency key.
- [ ] Đã test serverless trigger timeout/reinvocation nếu có.
- [ ] Với Reactor, đã test subscription, error signal và per-item vs outer retry.
- [ ] Đã test thành công sau retry, không retry lỗi vĩnh viễn và exhaustion.
- [ ] Metrics/trace cho attempts, backoff và failures đủ để điều tra.

Một hệ thống chỉ có unit test thành công của Function thuần vẫn chưa chứng minh retry production an toàn. Cần kiểm thử đúng các ranh giới bị lỗi và cách adapter phục hồi.

## 29. Bài tập thực hành

**Bài 1 — Đếm đúng số attempts.** Một ứng dụng dùng `Retry.max(2)` và binder dùng `max-attempts: 3`. Khi cả hai thật sự retry trên cùng lời gọi và không có redelivery thêm, một message có thể dẫn đến tối đa bao nhiêu lần gọi dependency? Vì sao?

**Bài 2 — Phân loại lỗi.** Cho bốn lỗi: `InvalidOrderException`, `QuoteConflictException`, `TransientStoreException` và một `NullPointerException` không dự kiến. Hãy chọn lỗi nào nên được bộ lọc retry của bước lưu chấp nhận.

**Bài 3 — Bảo vệ POST.** Client gửi yêu cầu tạo Quote, server commit DB nhưng response mất. Client resend. Hãy thiết kế idempotency key và quy tắc khi cùng key có payload khác.

**Bài 4 — Retry per-item.** Với `Flux.just("1", "bad", "3").map(Integer::parseInt).retry(1)`, hãy dự đoán các tín hiệu. Vì sao `1` có thể được phát hai lần?

**Bài 5 — Backoff.** Có ba retries với exponential backoff cơ sở 100 ms và hệ số 2. Hãy nêu lịch đợi trước jitter, rồi giải thích vì sao cần thêm deadline tổng.

**Bài 6 — Binder-level retry.** Viết cấu hình `max-attempts: 3` cho input binding `processOrder-in-0`. Nó áp dụng cho loại Function nào trong ví dụ và vì sao không tự bảo đảm DLQ?

**Bài 7 — Serverless.** Một handler mất kết nối sau DB commit, nền tảng gọi lại event ở instance khác. Vì sao bộ nhớ in-memory không đủ chống trùng?

**Bài 8 — Timeout scope.** So sánh `source.timeout(500ms).retryWhen(policy)` với `source.retryWhen(policy).timeout(500ms)`. Cấu hình nào giới hạn một attempt, cấu hình nào thường giới hạn toàn chuỗi?

**Bài 9 — Application vs adapter.** Một Consumer đồng bộ nhận message từ Kafka. Hãy đề xuất một cấu hình chọn binder retry, và một cấu hình khác chọn retry riêng DB trong ứng dụng. Khi phối hợp cả hai, phải tính gì?

**Bài 10 — Outbox.** Pipeline lưu DB rồi phát event. Process chết sau commit nhưng trước publish. Retry toàn pipeline có chắc giải quyết được không? Outbox giúp gì?

**Bài 11 — Unit test.** Viết một test `StepVerifier` cho transient failure hai lần rồi thành công lần thứ ba, và một test conflict không được retry. Cần assertion nào ngoài kết quả terminal?

**Bài 12 — Retry exhaustion.** Vì sao không nên `onErrorReturn(savedQuote)` khi thao tác lưu hết lượt? Có những trạng thái nào cần phân biệt?

**Bài 13 — Supplier.** Một `Supplier<OrderRequest>` gọi `queue.poll()` mỗi lần `get()`. Khi xử lý thất bại, retry cả Supplier có thể gặp vấn đề gì?

**Bài 14 — Reactive Consumer.** Một `Consumer<Flux<T>>` tự gọi `subscribe()` rồi trả về ngay. Nó có thể làm sai ack/retry của binder ra sao?

**Bài 15 — Observability.** Đề xuất năm trường log/metric giúp phân biệt một HTTP client resend với một binder redelivery và một application retry.

### Gợi ý đáp án

- **Bài 1:** Có thể tối đa 3 × 3 = **9 lần** nếu binder thực hiện ba attempts, mỗi lần ứng dụng có một attempt đầu và hai retries, chưa tính broker redelivery sau đó.
- **Bài 2:** Chỉ `TransientStoreException` khi đã được phân loại thật sự là transient; các lỗi còn lại không retry mù quáng.
- **Bài 3:** Dùng `orderId` hoặc idempotency key bền vững, unique constraint, cùng key+cùng dữ liệu trả kết quả cũ; cùng key+payload khác báo conflict.
- **Bài 4:** `onNext(1)`, `onNext(1)` rồi `onError(NumberFormatException)`; `retry(1)` subscribe lại toàn nguồn.
- **Bài 5:** 100, 200, 400 ms trước jitter; cần cộng thời gian mỗi attempt và chừa ngân sách response/ack.
- **Bài 6:** Đặt dưới `spring.cloud.stream.bindings.processOrder-in-0.consumer.max-attempts`; áp dụng khi binder/version hỗ trợ retry cho Consumer imperative, còn DLQ là chính sách binder riêng.
- **Bài 7:** Instance mới không chia sẻ state, process chết làm mất cache; cần idempotency ở storage bền vững và key ổn định.
- **Bài 8:** Timeout trước `retryWhen` thường là per-attempt; timeout sau retry thường bao toàn quá trình, gồm delay.
- **Bài 9:** Chọn binder retry hoặc ứng dụng retry riêng I/O; nếu phối hợp, tính tổng attempts, deadline, chính sách lỗi và idempotency.
- **Bài 10:** Không chắc vì đã có commit; outbox ghi ý định publish cùng transaction DB và cho worker phát lại.
- **Bài 11:** Kiểm tra cả `verifyComplete`/`expectError` và `assertEquals(n, attempts.get())`.
- **Bài 12:** Có thể chưa lưu, đã commit nhưng mất ack hoặc storage vẫn không khả dụng; không trả success giả.
- **Bài 13:** Có thể lấy event mới thay vì thử lại event cũ; cần giữ payload/id ổn định và theo cơ chế ack/requeue nguồn.
- **Bài 14:** Binder có thể coi `accept` hoàn tất trước khi async Publisher xong, không thấy lỗi đúng thời điểm.
- **Bài 15:** Ví dụ `requestId`, `eventId`, `attemptIndex`, `retryOwner`, `operationName`, `errorCategory`, `deliveryCount` hoặc `finalOutcome`.

## 30. Ghi nhớ

- **Retry có giới hạn** phải xác định rõ loại lỗi, số attempts, backoff/jitter, phạm vi, deadline và hành vi khi hết lượt.
- `Retry.max(2)` thường cho **hai lần retry thêm**; `max-attempts: 3` của một consumer binding thường biểu thị **ba lần xử lý tổng** trong cơ chế binder đang áp dụng.
- Spring Cloud Function giúp xây dựng và ghép `Supplier`/`Function`/`Consumer`; retry thuộc **ứng dụng, adapter, binder, SDK hoặc nền tảng** theo từng đường gọi.
- Đặt `retryWhen` ở đúng Publisher. Retry toàn Flux có thể phát lại phần tử trước lỗi; retry per-item cần ranh giới riêng cho từng message.
- Lỗi validation, xung đột và bug không nên bị retry mù quáng. Timeout/503 có thể retry nếu có ngân sách và thao tác an toàn.
- **Idempotency tại storage**, unique constraint và transaction là nền tảng để chịu được resend/redelivery sau khi commit chưa rõ.
- Khi cần ghi DB rồi publish event, transactional outbox có thể giúp giảm nguy cơ mất event; downstream vẫn phải sẵn sàng cho duplicate.
- Spring Cloud Stream binding retry, HTTP resend và serverless reinvocation có semantics riêng; **đừng cộng dồn mà không kiểm soát**.
- Kiểm thử phải đo attempts thực tế, error signal, trạng thái side effect và vòng đời ack/DLQ trên adapter triển khai, không chỉ kiểm tra Function thuần.









