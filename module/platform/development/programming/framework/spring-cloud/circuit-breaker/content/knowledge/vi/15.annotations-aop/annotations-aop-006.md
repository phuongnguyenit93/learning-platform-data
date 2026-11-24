# Thứ tự aspect khi kết hợp Retry, Bulkhead và TimeLimiter

Trong Spring Boot, Resilience4j có thể áp dụng `@Retry`, `@Bulkhead` và `@TimeLimiter` bằng Spring AOP. Khi nhiều annotation cùng bảo vệ một phương thức, các aspect sẽ bọc lời gọi theo một thứ tự nhất định. Thứ tự đó quyết định mỗi lần retry có phải xin lại bulkhead permit hay không, thời gian chờ của TimeLimiter áp dụng cho từng lần thử hay toàn bộ chuỗi, và permit được giữ trong thời gian backoff hay được trả ngay sau mỗi lần thử.

Không nên suy ra thứ tự thực thi từ vị trí các annotation được viết trong mã nguồn. Spring AOP sắp xếp advice theo order của aspect. Cần chọn thứ tự dựa trên mục tiêu bảo vệ, cấu hình rõ ràng và kiểm chứng bằng integration test với đúng phiên bản Resilience4j đang dùng.

## 1. Aspect tạo thành các lớp bọc quanh lời gọi

Hãy xem một phương thức gọi dịch vụ kho hàng:

```java
@Retry(name = "inventory")
@Bulkhead(name = "inventory")
@TimeLimiter(name = "inventory")
public CompletableFuture<InventoryResult> fetch(String sku) {
    return CompletableFuture.supplyAsync(
        () -> inventoryClient.fetch(sku),
        inventoryExecutor
    );
}
```

Khi ba aspect được sắp xếp theo thứ tự `Retry` → `Bulkhead` → `TimeLimiter`, cấu trúc lời gọi tương đương:

```text
Retry(
  Bulkhead(
    TimeLimiter(
      fetchFromDependency()
    )
  )
)
```

Aspect ngoài cùng nhận lời gọi trước và gọi tiếp aspect bên trong. Khi tác vụ hoàn tất hoặc phát sinh lỗi, kết quả đi ngược ra ngoài. Vì vậy, aspect ngoài có thể quan sát kết quả đã được các aspect bên trong xử lý.

Spring sử dụng quy tắc `Ordered`: giá trị order nhỏ hơn có precedence cao hơn. Với around advice, aspect có precedence cao hơn thường nằm ở lớp ngoài; nó chạy trước khi đi vào lời gọi và hoàn tất sau khi các lớp bên trong trả kết quả. Các thuộc tính order của Resilience4j cho phép điều chỉnh precedence của từng aspect. Thứ tự khai báo annotation trên phương thức không thay thế cấu hình này.

## 2. Chọn mục tiêu trước khi đặt thứ tự

Ba cơ chế có trách nhiệm khác nhau:

| Cơ chế | Trách nhiệm | Câu hỏi cần trả lời |
| --- | --- | --- |
| `Retry` | Thử lại khi kết quả thuộc nhóm lỗi được phép retry | Một yêu cầu có tối đa bao nhiêu lần thử và khoảng nghỉ bao lâu? |
| `Bulkhead` | Giới hạn số tác vụ đồng thời hoặc số thread/queue dành cho dependency | Một dependency được phép chiếm bao nhiêu năng lực xử lý? |
| `TimeLimiter` | Giới hạn thời gian chờ của `Future` hoặc `CompletionStage` | Mỗi lần thử hoặc toàn bộ chuỗi retry được phép kéo dài bao lâu? |

Thứ tự aspect không chỉ là chi tiết triển khai. Nó định nghĩa phạm vi mà mỗi cơ chế bảo vệ. Ví dụ, Bulkhead nằm ngoài Retry sẽ giữ một permit trong cả chuỗi thử lại; Bulkhead nằm trong Retry sẽ cấp và trả permit theo từng lần thử. TimeLimiter nằm trong Retry sẽ áp dụng timeout riêng cho mỗi lần thử; TimeLimiter nằm ngoài Retry có thể giới hạn toàn bộ chuỗi nếu phương thức trả về một stage đại diện cho toàn bộ quá trình retry.

## 3. Thứ tự thường dùng: Retry → Bulkhead → TimeLimiter

Với dependency có thể thử lại an toàn, một cách ghép thường hữu ích là:

```text
Retry
  └── Bulkhead
        └── TimeLimiter
              └── Lời gọi dependency
```

Luồng thực thi:

1. Retry bắt đầu một lần thử.
2. Bulkhead xin một permit; nếu hết năng lực và không được chờ, lời gọi bị từ chối.
3. TimeLimiter đặt giới hạn thời gian cho tác vụ của lần thử đó.
4. Lời gọi dependency hoàn tất hoặc timeout.
5. Bulkhead trả permit khi lần thử hoàn tất.
6. Retry quyết định dừng hay chờ backoff rồi bắt đầu lần thử tiếp theo.

Ưu điểm là thời gian backoff không giữ bulkhead permit. Mỗi lần thử phải xin lại permit, nên những request khác có cơ hội sử dụng năng lực khi request trước đang nghỉ giữa các lần retry. TimeLimiter giới hạn riêng từng lần thử.

Đổi lại, tổng thời gian có thể dài hơn timeout của một lần thử. Ví dụ ba lần thử, mỗi lần tối đa 800 ms, cộng backoff 100 ms và 200 ms, có thể kéo dài khoảng 2,7 giây chưa tính thời gian xếp hàng và xử lý phụ. Nếu API chỉ có deadline hai giây, cần thêm deadline tổng thể ở tầng request hoặc đặt một giới hạn ngoài toàn bộ chuỗi.

## 4. Cấu hình order tường minh

Ví dụ dưới đây đặt Retry ở ngoài cùng, Bulkhead ở giữa và TimeLimiter ở trong cùng. Các thuộc tính order được khai báo ở cấp cấu hình tương ứng:

```yaml
resilience4j:
  retry:
    retryAspectOrder: 1
    instances:
      inventory:
        maxAttempts: 3
        waitDuration: 100ms
        enableExponentialBackoff: true
        exponentialBackoffMultiplier: 2
        retryExceptions:
          - java.util.concurrent.TimeoutException
        ignoreExceptions:
          - io.github.resilience4j.bulkhead.BulkheadFullException
  bulkhead:
    bulkheadAspectOrder: 2
    instances:
      inventory:
        maxConcurrentCalls: 20
        maxWaitDuration: 0ms
  timelimiter:
    timeLimiterAspectOrder: 3
    instances:
      inventory:
        timeoutDuration: 800ms
        cancelRunningFuture: true
```

Trong quy tắc order của Spring, `1` có precedence cao hơn `2`, và `2` cao hơn `3`; do đó Retry là aspect ngoài cùng trong ví dụ. Hãy kiểm tra các thuộc tính order được hỗ trợ bởi starter Resilience4j của phiên bản dự án và tránh dùng cùng một giá trị order cho các aspect cần có thứ tự xác định.

`maxAttempts: 3` bao gồm lần gọi ban đầu và tối đa hai lần thử lại. Backoff tăng theo hệ số 2: khoảng nghỉ dự kiến là 100 ms rồi 200 ms. `retryExceptions` chỉ cho phép retry timeout được chỉ định. `BulkheadFullException` bị bỏ qua để tránh retry ngay một lỗi từ chối do hết năng lực; retry tức thời trong trường hợp này thường làm tăng cạnh tranh và tải.

`maxConcurrentCalls: 20` giới hạn số lời gọi đồng thời qua semaphore bulkhead. `maxWaitDuration: 0ms` yêu cầu không chờ lấy permit khi đã hết chỗ. `timeoutDuration: 800ms` giới hạn thời gian chờ cho mỗi tác vụ bất đồng bộ được bọc bởi TimeLimiter. Cấu hình này cần được điều chỉnh theo năng lực dependency và deadline nghiệp vụ.

## 5. Gắn annotation vào phương thức bất đồng bộ

`@TimeLimiter` của Resilience4j được thiết kế cho `Future`/`CompletionStage` và các kiểu bất đồng bộ mà integration hỗ trợ. Phương thức dưới đây trả về `CompletableFuture`, dùng executor được quản lý sẵn và đặt cả ba annotation trên cùng một Spring bean method:

```java
import io.github.resilience4j.bulkhead.annotation.Bulkhead;
import io.github.resilience4j.bulkhead.annotation.Bulkhead.Type;
import io.github.resilience4j.retry.annotation.Retry;
import io.github.resilience4j.timelimiter.annotation.TimeLimiter;
import org.springframework.stereotype.Service;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

@Service
public class InventoryGateway {

    private final InventoryClient inventoryClient;
    private final Executor inventoryExecutor;

    public InventoryGateway(
            InventoryClient inventoryClient,
            Executor inventoryExecutor) {
        this.inventoryClient = inventoryClient;
        this.inventoryExecutor = inventoryExecutor;
    }

    @Retry(name = "inventory")
    @Bulkhead(name = "inventory", type = Type.SEMAPHORE)
    @TimeLimiter(name = "inventory")
    public CompletableFuture<InventoryResult> fetch(String sku) {
        return CompletableFuture.supplyAsync(
            () -> inventoryClient.fetch(sku),
            inventoryExecutor
        );
    }
}
```

Ví dụ giả định phiên bản Resilience4j đang dùng hỗ trợ kết hợp các aspect này với `CompletableFuture` và semaphore bulkhead. Cần dùng starter Spring Boot Resilience4j phù hợp, bật Spring AOP theo yêu cầu của phiên bản và cấu hình executor có giới hạn. Không dùng `CompletableFuture.supplyAsync(...)` mà bỏ qua executor trong ứng dụng có tải thực vì common pool không phải giới hạn bulkhead của dependency.

Nếu chọn `Bulkhead.Type.THREADPOOL`, cấu hình thread pool bulkhead và queue riêng. Không coi `THREADPOOL` và semaphore là cùng một cơ chế: semaphore giới hạn số lời gọi đang giữ permit; thread-pool bulkhead phân lập việc thực thi bằng pool và queue có giới hạn. Hãy chọn một loại theo mô hình thực thi của dependency.

### Với phương thức đồng bộ blocking

Nếu phương thức trả về trực tiếp `InventoryResult` và gọi HTTP client blocking, `@Retry` và `@Bulkhead` có thể bảo vệ lời gọi đồng bộ. Tuy nhiên, không giả định `@TimeLimiter` sẽ tự chuyển một phương thức blocking bất kỳ sang executor hoặc ngắt thread đang chờ. Đặt connect/response/read timeout trực tiếp trên HTTP client. Nếu cần dùng TimeLimiter, chuyển tác vụ sang `Future`/`CompletionStage` bằng executor có giới hạn hoặc dùng API client bất đồng bộ.

## 6. Khi Bulkhead nằm ngoài Retry

Một lựa chọn khác là:

```text
Bulkhead
  └── Retry
        └── TimeLimiter
              └── Lời gọi dependency
```

Khi đó một permit được giữ trong toàn bộ chuỗi retry, bao gồm thời gian chờ backoff. Cách này giới hạn số workflow đang xử lý dependency, kể cả khi chúng đang nghỉ giữa các lần thử. Nó có thể phù hợp khi muốn giới hạn toàn bộ giao dịch logic hoặc tránh quá nhiều workflow cùng retry.

Nhược điểm là permit bị chiếm trong lúc không có request thực tế đang chạy. Nếu nhiều workflow cùng chờ backoff, bulkhead có thể hết permit và từ chối request mới dù dependency đang rảnh. Điều này làm giảm thông lượng và tăng số lỗi `BulkheadFullException`.

| Tiêu chí | Retry ngoài Bulkhead | Bulkhead ngoài Retry |
| --- | --- | --- |
| Phạm vi permit | Một permit cho mỗi lần thử | Một permit cho cả chuỗi retry |
| Permit trong backoff | Được trả trước khi nghỉ | Vẫn được giữ |
| Tác động đến request mới | Permit có thể được dùng lại giữa các lần thử | Ít slot hơn khi nhiều workflow đang backoff |
| Phù hợp khi | Muốn giới hạn concurrency của từng lần gọi dependency | Muốn giới hạn concurrency của toàn bộ workflow |

Không có một thứ tự đúng cho mọi hệ thống. Hãy xác định Bulkhead đang bảo vệ tài nguyên nào: request tới dependency hay toàn bộ quy trình nghiệp vụ.

## 7. Khi TimeLimiter nằm ngoài Retry

Nếu TimeLimiter là aspect ngoài cùng, cấu trúc sẽ là:

```text
TimeLimiter
  └── Retry
        └── Bulkhead
              └── Lời gọi dependency
```

Với phương thức bất đồng bộ, TimeLimiter ngoài cùng có thể giới hạn thời gian hoàn tất của toàn bộ chuỗi retry. Khi hết deadline, caller nhận timeout ngay cả khi Retry còn lần thử hoặc backoff chưa hoàn tất. Cách này phù hợp khi yêu cầu nghiệp vụ có một ngân sách thời gian tổng thể nghiêm ngặt.

Trong cấu trúc này, TimeLimiter ngoài không tự cấp timeout riêng cho từng lần gọi dependency. Nếu một lần thử có thể treo lâu, cần timeout ở HTTP client hoặc một giới hạn theo từng lần thử bên trong chuỗi. Không nên chỉ dựa vào deadline tổng thể nếu các tác vụ bên dưới không phản ứng với cancellation.

So sánh hai lựa chọn:

| Cấu trúc | Ý nghĩa timeout | Hệ quả |
| --- | --- | --- |
| `Retry(Bulkhead(TimeLimiter(call)))` | Timeout riêng cho từng lần thử | Tổng thời gian có thể lớn hơn một timeout; cần deadline tổng ở tầng ngoài nếu có SLA |
| `TimeLimiter(Retry(Bulkhead(call)))` | Timeout cho toàn bộ chuỗi retry | Giới hạn tổng thời gian caller chờ; cần timeout client hoặc per-attempt timeout nếu từng request có thể treo |

Không nên xếp hai TimeLimiter chỉ để “an toàn hơn” nếu không xác định rõ mỗi cái quản lý deadline nào. Nếu cần cả timeout từng lần thử và deadline tổng, đặt một timeout ở client cho mỗi request mạng và một deadline tổng ở tầng workflow; tài liệu hóa rõ hai giới hạn đó.

## 8. Thứ tự ảnh hưởng đến loại lỗi mà Retry nhìn thấy

Retry chỉ nên lặp lại lỗi có khả năng tạm thời và có thể thử lại an toàn. Khi Bulkhead nằm bên trong Retry, lỗi `BulkheadFullException` đi ra khỏi Bulkhead tới Retry. Nếu không bỏ qua lỗi này, Retry có thể liên tục thử lại trong lúc hệ thống vẫn không có permit, tạo thêm tải và trì hoãn request.

Tương tự, nếu circuit breaker được thêm vào chuỗi, không nên retry `CallNotPermittedException` khi breaker đang `OPEN`. Việc thử lại ngay không làm dependency khỏe hơn và có thể tạo vòng lặp từ chối. Chỉ retry lỗi timeout hoặc lỗi mạng được chọn, với số lần thử nhỏ và backoff có jitter.

Đối với command có side effect, timeout có thể xảy ra sau khi dependency đã thực hiện thao tác nhưng phản hồi bị mất. Retry command chỉ an toàn khi có idempotency key được phía nhận thực thi bền vững. Không retry lỗi nghiệp vụ vĩnh viễn như dữ liệu không hợp lệ, quyền truy cập bị từ chối hoặc trạng thái không cho phép.

Fallback nên được đặt tại một tầng có trách nhiệm rõ ràng, thường sau khi các lần retry đã hết. Tránh khai báo nhiều fallback trên các aspect cùng phương thức mà không hiểu thứ tự xử lý; một fallback bên trong có thể biến lỗi thành thành công và khiến Retry bên ngoài không còn nhận ra lỗi để thử lại.

## 9. AOP chỉ áp dụng khi lời gọi đi qua Spring proxy

Các annotation Resilience4j được áp dụng qua Spring AOP. Vì vậy, đối tượng cần được Spring quản lý và lời gọi phải đi qua proxy. Một lời gọi nội bộ trong cùng instance như `this.fetch(sku)` thường không đi qua proxy, nên aspect có thể không chạy.

Ví dụ cấu trúc dễ bỏ qua AOP:

```java
@Service
public class InventoryService {

    public InventoryResult load(String sku) {
        // Self-invocation: gọi trực tiếp trong cùng object.
        return fetchProtected(sku).join();
    }

    @Retry(name = "inventory")
    @Bulkhead(name = "inventory")
    @TimeLimiter(name = "inventory")
    public CompletableFuture<InventoryResult> fetchProtected(String sku) {
        // ...
    }
}
```

Trong ví dụ, `load(...)` gọi trực tiếp phương thức cùng object. Hãy tách phương thức được bảo vệ sang một Spring bean khác và inject bean đó, hoặc thiết kế ranh giới gọi để request đi qua proxy. Không nên dựa vào việc gọi `this` để kích hoạt aspect.

## 10. Kiểm chứng thứ tự bằng integration test

Đừng chỉ kiểm tra phương thức trả về đúng kết quả. Hãy kiểm tra các hệ quả mà thứ tự aspect tạo ra:

1. **Số lần thử:** cấu hình `maxAttempts: 3`, cho dependency timeout và xác minh số lần gọi không vượt quá ba.
2. **Permit theo từng lần thử:** giữ request đầu bằng latch, xác minh bulkhead đạt giới hạn; sau khi request kết thúc và trước lần thử tiếp theo, kiểm tra permit được trả theo cấu trúc đã chọn.
3. **Timeout:** cho dependency không hoàn tất và xác minh caller nhận timeout theo giới hạn từng lần thử hoặc deadline tổng.
4. **Backoff:** ghi timestamp giữa các lần thử để xác minh khoảng nghỉ và jitter trong biên cho phép.
5. **Lỗi bị bỏ qua:** làm Bulkhead hết permit và xác minh Retry không lặp `BulkheadFullException` nếu chính sách yêu cầu bỏ qua.
6. **AOP proxy:** gọi qua Spring bean được inject; tránh kiểm thử bằng cách tự tạo object bằng `new` nếu mục tiêu là xác minh aspect.

Có thể ghi trace theo từng mốc để đọc thứ tự thực tế:

```text
retry.attempt-1
bulkhead.acquire
timelimiter.start
dependency.start
timelimiter.timeout
bulkhead.release
retry.backoff
retry.attempt-2
bulkhead.acquire
timelimiter.start
dependency.start
dependency.complete
bulkhead.release
retry.complete
```

Trace trên minh họa `Retry(Bulkhead(TimeLimiter(call)))`. Nếu Bulkhead ở ngoài Retry, chỉ có một lần `bulkhead.acquire` trước attempt đầu và `bulkhead.release` sau khi toàn bộ retry hoàn tất. Nếu TimeLimiter ở ngoài Retry, chỉ có một mốc bắt đầu deadline cho toàn chuỗi. Dùng counter, event listener hoặc mock ở ranh giới dependency để đối chiếu; không suy luận thứ tự chỉ từ thứ tự dòng annotation.

## 11. Quy tắc lựa chọn

- Dùng `Retry → Bulkhead → TimeLimiter` khi muốn giới hạn từng lần thử, trả permit trong thời gian backoff và đặt timeout riêng cho từng attempt.
- Dùng `Bulkhead → Retry → TimeLimiter` khi muốn giới hạn số workflow đang retry và chấp nhận giữ permit trong thời gian backoff.
- Dùng `TimeLimiter → Retry → Bulkhead` khi cần deadline tổng cho chuỗi bất đồng bộ; bổ sung timeout client hoặc per-attempt timeout nếu cần giới hạn từng request mạng.
- Chỉ retry lỗi tạm thời, giới hạn `maxAttempts`, dùng backoff/jitter và bỏ qua lỗi từ chối năng lực như `BulkheadFullException` nếu retry không giúp ích.
- Chỉ dùng `@TimeLimiter` với kiểu trả về bất đồng bộ được integration hỗ trợ; với blocking client, cấu hình timeout tại client.
- Bảo đảm lời gọi đi qua Spring proxy và các aspect dùng order khác nhau, tường minh.
- Kiểm thử số lần gọi, concurrency, thời gian chờ, permit và fallback để xác nhận cấu trúc thực tế.

Thứ tự aspect là một phần của chính sách chịu lỗi. Khi chọn đúng phạm vi cho từng lớp, Retry không tạo tải lặp không cần thiết, Bulkhead giới hạn đúng tài nguyên và TimeLimiter áp dụng deadline đúng nơi. Cấu hình order tường minh cùng integration test giúp hành vi đó có thể dự đoán và duy trì giữa các lần nâng cấp Spring Boot hoặc Resilience4j.
