# Ngưỡng lời gọi chậm không tự dừng lời gọi đang chạy

Trong Spring Cloud Circuit Breaker với Resilience4j, `slowCallDurationThreshold` giúp nhận diện một lời gọi mất quá nhiều thời gian. Khi lời gọi hoàn tất, circuit breaker ghi nhận nó là lời gọi chậm và cập nhật `slowCallRate`. Nếu tỷ lệ lời gọi chậm đạt ngưỡng, breaker có thể chuyển từ `CLOSED` sang `OPEN` để chặn các lời gọi mới. Tuy nhiên, ngưỡng này **không tự dừng lời gọi đang chạy**.

Để giới hạn thời gian chờ, cần một cơ chế timeout như `TimeLimiter` cho tác vụ bất đồng bộ hoặc timeout được hỗ trợ trực tiếp bởi HTTP/RPC client. Ba cơ chế có liên quan nhưng đảm nhiệm các việc khác nhau: circuit breaker đánh giá sức khỏe của dependency, TimeLimiter giới hạn thời gian chờ của tác vụ, còn client timeout giới hạn thời gian chờ ở tầng kết nối và truyền dữ liệu.

## 1. Ngưỡng lời gọi chậm chỉ phân loại kết quả

Resilience4j đo thời gian thực thi của lời gọi được bảo vệ. `slowCallDurationThreshold` xác định thời lượng từ đó một lời gọi được phân loại là chậm. `slowCallRateThreshold` đặt tỷ lệ lời gọi chậm tối đa có thể chấp nhận trong sliding window trước khi circuit breaker mở.

Ví dụ cấu hình:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 50
        failureRateThreshold: 50
```

Với cấu hình này, một lời gọi kéo dài hơn một giây được xem là chậm. Nếu ít nhất năm lời gọi đã được ghi nhận và tỷ lệ lời gọi chậm đạt 50% trong cửa sổ, circuit breaker có thể chuyển sang `OPEN`. Cơ chế này đánh giá kết quả và thời lượng sau khi lời gọi kết thúc; nó không gửi tín hiệu hủy tới HTTP client, không ngắt thread và không giải phóng socket của lời gọi còn đang chờ.

Hãy hình dung dependency mất tám giây mới trả lời. Với `slowCallDurationThreshold: 1s`, lời gọi vẫn có thể tiếp tục chờ đủ tám giây. Khi nó hoàn tất, circuit breaker mới có đủ thời gian thực thi để ghi nhận đây là một lời gọi chậm. Những yêu cầu mới có thể bị chặn sau khi tỷ lệ chậm đạt ngưỡng, nhưng các lời gọi đã được cho phép trước đó vẫn tiếp tục chạy.

## 2. Phân biệt slow-call threshold, TimeLimiter và client timeout

| Cơ chế | Mục đích | Tác động lên lời gọi đang chạy |
| --- | --- | --- |
| `slowCallDurationThreshold` | Phân loại lời gọi chậm để tính `slowCallRate` | Không tự dừng lời gọi; chỉ ghi nhận thời lượng khi có kết quả |
| `slowCallRateThreshold` | Quyết định khi nào tỷ lệ lời gọi chậm đủ cao để mở circuit breaker | Chặn lời gọi mới sau khi breaker mở; không hủy lời gọi đã được cho phép |
| Resilience4j `TimeLimiter` | Giới hạn thời gian chờ của `Future` hoặc `CompletionStage` | Hoàn tất thao tác được bọc bằng timeout; có thể yêu cầu hủy `Future` tùy cấu hình |
| HTTP/RPC client timeout | Giới hạn thời gian kết nối, chờ phản hồi hoặc đọc dữ liệu ở tầng truyền tải | Client có thể kết thúc thao tác I/O theo khả năng của implementation |

Các cơ chế này bổ sung cho nhau. Slow-call threshold giúp phát hiện dịch vụ đang chậm và mở mạch khi có đủ bằng chứng. TimeLimiter giúp caller không phải chờ vô hạn đối với tác vụ bất đồng bộ. Timeout của client đặt giới hạn thực tế cho thao tác mạng, chẳng hạn connect timeout, response timeout hoặc read timeout.

Không nên đặt `slowCallDurationThreshold` thay cho timeout. Nếu chỉ có ngưỡng lời gọi chậm, thread xử lý vẫn có thể bị giữ trong thời gian dài và nhiều lời gọi chậm có thể cùng chiếm hết thread pool.

## 3. TimeLimiter hoạt động với tác vụ bất đồng bộ

Resilience4j TimeLimiter hỗ trợ các kiểu tác vụ dựa trên `Future` và `CompletionStage`. Nó lên lịch một mốc timeout. Nếu tác vụ chưa hoàn tất khi hết thời gian, kết quả được hoàn tất bằng lỗi timeout. Tùy cấu hình, TimeLimiter cũng yêu cầu hủy `Future` đang chạy.

Ví dụ cấu hình cho instance `inventory`:

```yaml
resilience4j:
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
```

`timeoutDuration` là thời gian tối đa caller chờ kết quả của tác vụ được bọc. `cancelRunningFuture` cho biết TimeLimiter có yêu cầu hủy future khi timeout hay không. Việc hủy này là một tín hiệu tới tác vụ; nó không bảo đảm mọi thao tác I/O bên dưới đã dừng. Thread đang chạy phải có khả năng phản ứng với interrupt hoặc client phải hỗ trợ hủy request.

### Ví dụ với Future và executor

Đối với tác vụ blocking chưa có API bất đồng bộ, có thể chạy tác vụ trong executor và bọc `Future` bằng TimeLimiter:

```java
import io.github.resilience4j.timelimiter.TimeLimiter;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;

import java.time.Duration;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeoutException;

public class InventoryGateway {

    private final ExecutorService workers = Executors.newFixedThreadPool(20);
    private final ScheduledExecutorService timer =
        Executors.newScheduledThreadPool(1);

    private final TimeLimiter timeLimiter = TimeLimiter.of(
        TimeLimiterConfig.custom()
            .timeoutDuration(Duration.ofSeconds(2))
            .cancelRunningFuture(true)
            .build()
    );

    public InventoryResult fetch(String sku) throws Exception {
        Callable<InventoryResult> limitedCall =
            TimeLimiter.decorateFutureSupplier(
                timeLimiter,
                timer,
                () -> workers.submit(() -> inventoryClient.fetch(sku))
            );

        return limitedCall.call();
    }
}
```

Đoạn mã minh họa cách ghép API; `inventoryClient` cần được inject và các executor cần được quản lý vòng đời như bean hoặc tài nguyên ứng dụng. Khi quá hai giây, caller nhận lỗi timeout. Với `cancelRunningFuture(true)`, TimeLimiter gọi cơ chế hủy trên `Future` do executor trả về.

Không nên tạo executor mới cho mỗi request. Dùng một executor có giới hạn, theo dõi queue và số thread đang hoạt động. Nếu tác vụ không phản ứng với interrupt, thread có thể vẫn tiếp tục chạy sau khi caller đã nhận timeout. Khi đó các tác vụ cũ vẫn tiêu thụ tài nguyên và có thể làm cạn thread pool.

### CompletionStage khi client đã hỗ trợ async

Nếu client trả về `CompletionStage`, không cần chuyển tác vụ sang một thread blocking chỉ để dùng TimeLimiter:

```java
import io.github.resilience4j.timelimiter.TimeLimiter;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ScheduledExecutorService;
import java.util.function.Supplier;

public CompletionStage<InventoryResult> fetchAsync(String sku) {
    Supplier<CompletionStage<InventoryResult>> request =
        () -> inventoryClient.fetchAsync(sku);

    return timeLimiter.executeCompletionStage(timer, request);
}
```

Trong ví dụ, `inventoryClient.fetchAsync(...)` đại diện cho API client trả về `CompletionStage`. TimeLimiter giới hạn thời gian hoàn tất stage mà caller quan sát. Khả năng hủy request bên dưới vẫn phụ thuộc vào implementation của stage và client; hãy kiểm tra xem việc cancel stage có truyền tới request mạng hay chỉ làm stage phía ứng dụng hoàn tất sớm.

## 4. Vì sao cancel(true) không phải bảo đảm dừng I/O?

Khi `cancelRunningFuture` bật, TimeLimiter yêu cầu hủy future. Với `Future` do `ExecutorService.submit(...)` trả về, thao tác hủy có thể gửi interrupt tới thread đang chạy. Tuy nhiên:

- Code blocking chỉ dừng khi API đang gọi phản ứng với interrupt hoặc kiểm tra trạng thái interrupt.
- Một số thư viện I/O không hủy socket ngay khi thread bị interrupt.
- `CompletableFuture.cancel(true)` không có nghĩa là thread đang thực thi computation chắc chắn bị interrupt.
- Nếu HTTP client có cơ chế cancel request riêng, cần xác minh cancellation signal được truyền tới client.

Vì vậy, timeout ở tầng client vẫn rất quan trọng. Hãy đặt connect timeout để giới hạn thời gian thiết lập kết nối, response/read timeout để giới hạn thời gian chờ dữ liệu, và deadline tổng thể phù hợp với ngân sách độ trễ của request nghiệp vụ. Tên và cách hoạt động của các thuộc tính tùy HTTP/RPC client đang dùng.

Ví dụ về quan hệ thời gian:

```text
Request nghiệp vụ bắt đầu
       |
       +---- HTTP connect timeout
       |
       +---- HTTP response/read timeout
       |
       +---- TimeLimiter timeout (2 giây)
       |          |
       |          +--> Caller nhận TimeoutException
       |          +--> Có thể yêu cầu cancel Future
       |
       +---- Dependency thực sự kết thúc (có thể muộn hơn nếu không hủy được)
```

Nếu TimeLimiter kết thúc ở hai giây nhưng I/O vẫn chạy thêm mười giây, caller đã được giải phóng nhưng tài nguyên thực thi vẫn có thể bị giữ. Timeout chỉ hiệu quả đầy đủ khi cơ chế bên dưới thực sự dừng hoặc giới hạn được thao tác.

## 5. Kết hợp TimeLimiter với CircuitBreaker

Circuit breaker và TimeLimiter giải quyết hai vấn đề khác nhau. TimeLimiter làm cho tác vụ được bọc kết thúc bằng timeout khi vượt thời hạn. Circuit breaker ghi nhận timeout đó như một kết quả lỗi nếu exception được phân loại là failure, đồng thời có thể ghi nhận lời gọi là chậm nếu thời lượng đo được vượt `slowCallDurationThreshold`.

Ví dụ cấu hình:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 60
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
```

Trong ví dụ, lời gọi hoàn tất sau 1,5 giây có thể được ghi nhận là chậm nhưng vẫn thành công. Lời gọi chưa hoàn tất sau hai giây sẽ bị TimeLimiter kết thúc bằng timeout. Nếu timeout exception được circuit breaker ghi nhận, nó làm tăng failure rate; tùy thời gian circuit breaker quan sát và cách ghép decorator, nó cũng có thể được phân loại là lời gọi chậm.

Khi ghép các decorator hoặc integration, bảo đảm circuit breaker quan sát kết quả của thao tác đã áp dụng timeout để timeout được tính vào thống kê lỗi. Thứ tự bọc ảnh hưởng đến thời lượng và exception mà mỗi cơ chế quan sát. Với Spring Cloud CircuitBreaker Resilience4j, dùng cấu hình `resilience4j.timelimiter.instances` theo cùng ID với circuit breaker và kiểm tra hành vi thực tế của API đồng bộ hoặc reactive mà ứng dụng sử dụng. Không giả định mọi lời gọi đồng bộ đều tự động được chuyển sang executor để TimeLimiter có thể ngắt chúng.

Nếu ứng dụng dùng Spring Cloud factory cho tác vụ bất đồng bộ, chọn API hoặc overload hỗ trợ `Future`/`CompletionStage` theo phiên bản đang dùng. Với lời gọi blocking trực tiếp, cấu hình timeout tại HTTP client và cân nhắc executor có giới hạn nếu cần chuyển tác vụ sang bất đồng bộ.

## 6. Với lời gọi reactive, timeout phát tín hiệu hủy upstream

Trong Reactor, toán tử `timeout(...)` giới hạn thời gian chờ của publisher. Khi quá hạn, subscriber nhận lỗi timeout và Reactor gửi tín hiệu cancel tới upstream:

```java
import java.time.Duration;
import reactor.core.publisher.Mono;

public Mono<InventoryResult> fetchInventory(String sku) {
    return inventoryClient.fetch(sku)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(
            java.util.concurrent.TimeoutException.class,
            error -> Mono.just(InventoryResult.unavailable(sku))
        );
}
```

Đây là ví dụ dùng timeout ở tầng Reactor. Với Resilience4j, có thể cấu hình TimeLimiter và tích hợp reactive phù hợp; chọn một nơi quản lý deadline nhất quán để tránh nhiều timeout chồng lấn mà không rõ cái nào tạo lỗi. Tín hiệu cancel chỉ có tác dụng nếu publisher và HTTP client upstream hỗ trợ hủy. Nếu publisher bọc một tác vụ blocking không thể interrupt, công việc bên dưới vẫn có thể tiếp tục.

Không gọi `block()` trong event loop để biến một lời gọi reactive thành đồng bộ. Việc đó có thể giữ event loop trong thời gian chờ và làm ảnh hưởng các request khác. Dùng API non-blocking của client, timeout của transport và các operator reactive phù hợp.

## 7. Đặt các ngưỡng theo ngân sách độ trễ

Các giá trị cần được chọn cùng nhau dựa trên thời gian mà luồng nghiệp vụ có thể chờ. Ví dụ, nếu API tổng thể có deadline ba giây và cần giữ một giây cho xử lý còn lại, lời gọi inventory không nên có timeout vượt quá hai giây.

| Thuộc tính | Ví dụ | Vai trò |
| --- | ---: | --- |
| `slowCallDurationThreshold` | 800 ms | Đánh dấu lời gọi đã bắt đầu chậm so với mục tiêu |
| `timeoutDuration` | 1,5 s | Giới hạn thời gian chờ của tác vụ bất đồng bộ |
| HTTP response/read timeout | 1,4 s | Giới hạn chờ phản hồi ở tầng HTTP client |
| API deadline | 3 s | Ngân sách tổng thể của request nghiệp vụ |

Các giá trị trên chỉ minh họa thứ tự và quan hệ. Timeout của HTTP client thường cần nhỏ hơn hoặc bằng TimeLimiter để thao tác I/O kết thúc trước khi caller hết hạn. Slow-call threshold có thể nhỏ hơn timeout để phát hiện suy giảm trước khi lời gọi bị timeout. API deadline phải tính cả thời gian xử lý nội bộ, retry, serialize và các dependency khác.

Tránh đặt timeout của từng dependency bằng toàn bộ deadline của API. Nếu một request tuần tự gọi ba dịch vụ, mỗi dịch vụ chờ tối đa ba giây sẽ khiến thời gian tổng vượt xa deadline. Hãy truyền hoặc tính ngân sách thời gian còn lại cho mỗi dependency, và cân nhắc không retry khi thời gian còn lại không đủ.

## 8. Kiểm thử chứng minh slow-call threshold không hủy lời gọi

Một kiểm thử cần phân biệt hai điều: circuit breaker ghi nhận một lời gọi chậm sau khi nó hoàn tất, và TimeLimiter có thể kết thúc việc chờ trước khi tác vụ hoàn tất. Với API native, có thể dùng latch để giữ supplier đang chạy lâu hơn ngưỡng:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

CountDownLatch started = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);
ExecutorService executor = Executors.newSingleThreadExecutor();

CircuitBreaker breaker = CircuitBreaker.of(
    "inventory",
    CircuitBreakerConfig.custom()
        .slowCallDurationThreshold(Duration.ofMillis(100))
        .slowCallRateThreshold(50)
        .slidingWindowSize(1)
        .minimumNumberOfCalls(1)
        .build()
);

Future<String> call = executor.submit(() -> breaker.executeSupplier(() -> {
    started.countDown();
    try {
        release.await();
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException(ex);
    }
    return "ok";
}));

try {
    assertThat(started.await(1, TimeUnit.SECONDS)).isTrue();
    // Giữ supplier chờ ít nhất 150 ms, lâu hơn ngưỡng 100 ms.
    assertThat(release.await(150, TimeUnit.MILLISECONDS)).isFalse();
    assertThat(call.isDone()).isFalse();
    release.countDown();
    assertThat(call.get(1, TimeUnit.SECONDS)).isEqualTo("ok");
    assertThat(breaker.getMetrics().getNumberOfSlowCalls()).isEqualTo(1);
} finally {
    release.countDown();
    executor.shutdownNow();
}
```

Đoạn mã minh họa cần đặt trong test có quản lý executor và timeout chờ để tránh treo nếu assertion thất bại. Khi supplier còn chờ `release`, circuit breaker không tự giải phóng nó chỉ vì đã vượt 100 ms. Sau khi supplier hoàn tất, metric mới phản ánh lời gọi chậm.

Một bài kiểm thử TimeLimiter riêng có thể dùng `Future` chưa hoàn tất và xác minh caller nhận timeout sau thời hạn đã cấu hình. Nếu kiểm tra `cancelRunningFuture`, xác minh cả trạng thái future lẫn việc tác vụ thực sự dừng; không chỉ dựa vào `Future.isCancelled()` vì trạng thái cancelled không chứng minh I/O bên dưới đã ngừng.

## 9. Những lỗi thường gặp

- **Dùng `slowCallDurationThreshold` như timeout:** lời gọi vẫn chạy cho đến khi client hoàn tất hoặc tự timeout.
- **Bọc tác vụ blocking nhưng không có executor phù hợp:** thread gọi vẫn bị chặn hoặc thread pool mới bị cạn khi dependency chậm.
- **Cho rằng `cancelRunningFuture: true` chắc chắn đóng socket:** hủy Future chỉ yêu cầu hủy tác vụ; client và code bên dưới phải hỗ trợ cancellation.
- **Không đặt timeout tại HTTP/RPC client:** caller có thể nhận timeout nhưng I/O vẫn tiêu thụ tài nguyên.
- **Đặt TimeLimiter dài hơn deadline nghiệp vụ:** tầng gọi bên ngoài đã hết hạn trước khi dependency được giải phóng.
- **Để retry tiếp tục sau timeout:** các lần thử mới có thể làm tăng tải lên dependency đang suy giảm; cần giới hạn số lần retry và deadline còn lại.
- **Nhầm lời gọi chậm với lời gọi thất bại:** một lời gọi chậm vẫn có thể trả về thành công; failure rate và slow-call rate là hai chỉ số riêng.

## 10. Quy tắc triển khai

- Dùng `slowCallDurationThreshold` để phát hiện độ trễ bất thường và giúp circuit breaker mở khi tỷ lệ lời gọi chậm vượt ngưỡng.
- Dùng TimeLimiter cho `Future` hoặc `CompletionStage` khi cần giới hạn thời gian chờ của tác vụ bất đồng bộ.
- Đặt connect, response/read timeout hoặc deadline ở HTTP/RPC client để giới hạn thao tác I/O thực tế.
- Chỉ bật `cancelRunningFuture` khi hiểu rõ tác vụ và client phản ứng thế nào với cancellation.
- Dùng executor có giới hạn cho tác vụ blocking được chuyển sang bất đồng bộ; theo dõi queue và thread đang chạy.
- Với Reactor, dùng timeout/cancel non-blocking và client hỗ trợ cancellation; không chặn event loop.
- Kiểm thử riêng hành vi phân loại lời gọi chậm, timeout, cancellation và chuyển trạng thái circuit breaker.

Ngưỡng lời gọi chậm cho biết dependency đã phản hồi chậm đến mức nào; nó không phải lệnh dừng công việc. Kết hợp circuit breaker, TimeLimiter và timeout ở client theo cùng ngân sách độ trễ giúp ứng dụng vừa phát hiện suy giảm, vừa giới hạn thời gian chờ và kiểm soát tài nguyên đang bị giữ bởi lời gọi chưa hoàn tất.
