# Đảm bảo stop observation trong mọi nhánh

Một dịch vụ Spring Boot đo thời gian thanh toán bằng Micrometer Observation. Request thành công có span rõ ràng và timer bình thường, nhưng khi xảy ra exception hoặc client hủy yêu cầu, một số span kéo dài bất thường, còn dashboard thiếu số liệu của các giao dịch thất bại. Một nguyên nhân phổ biến là **Observation đã được bắt đầu nhưng không được kết thúc ở mọi đường thực thi**.

Trong module **SPRING_BOOT_OBSERVABILITY**, việc thiết lập metrics, logs và distributed tracing bằng Micrometer Observation chỉ đáng tin cậy nếu vòng đời của từng thao tác được quản lý đúng. `start()`, `openScope()`, `error()` và `stop()` mang những trách nhiệm khác nhau. Đặc biệt, một observation không được `stop()` sẽ khiến các `ObservationHandler` không có cơ hội xử lý sự kiện kết thúc như mong đợi: timer có thể không được ghi nhận đầy đủ, span có thể không đóng và dữ liệu điều tra độ trễ bị sai lệch.

Bài này nằm trong chương **Vòng đời observation**, tập trung vào câu hỏi thực hành: **làm thế nào bảo đảm mỗi observation được start sẽ được stop đúng một lần, đúng lúc, trên tất cả nhánh thành công, lỗi, trả về sớm, bất đồng bộ và hủy thao tác?**

Sau bài học, bạn có thể:

1. Phân biệt `stop()` với việc đóng `Scope`, kết thúc HTTP request và xuất trace.
2. Áp dụng `observe(...)` hoặc `try/finally` để quản lý vòng đời của mã đồng bộ.
3. Không để sót `stop()` khi có `return` sớm, exception, fallback hoặc nhiều nhánh điều kiện.
4. Đặt điểm `stop()` theo **thời điểm công việc thực sự kết thúc** trong `CompletableFuture` và Reactor `Mono`.
5. Xử lý tình huống retry, timeout, cancellation và callback chạy nhiều lần mà không dừng observation quá sớm hoặc lặp lại.
6. Kiểm chứng vòng đời qua handler, metrics, traces và log correlation thay vì chỉ nhìn request trả về thành công.

## 1. Một observation được start phải có điểm kết thúc xác định

Micrometer Observation mô tả một hoạt động có tên, ví dụ `inventory.reserve` hoặc `checkout.pay`. Mỗi lần thực thi tạo một occurrence riêng với thời điểm bắt đầu, ngữ cảnh, key-value và kết quả.

Vòng đời tối thiểu:

```text
                   Lifetime của Observation
createNotStarted()  start()                                 stop()
       |               |=======================================|
                       |  openScope()            closeScope()  |
                       |       |----------------------|         |
                       |     công việc đang thực thi             |
                       |                                           |
                 handler.onStart(...)                    handler.onStop(...)
```

- `createNotStarted(...)` chỉ tạo đối tượng; không mặc nhiên bắt đầu đo.
- `start()` chuyển observation sang trạng thái đang hoạt động, thông báo cho những handler phù hợp.
- `openScope()` đặt observation vào ngữ cảnh hiện hành của đoạn thực thi; hữu ích cho quan hệ cha–con của trace và correlation với logging.
- `Scope.close()` đóng *scope*, không thay thế `Observation.stop()`.
- `stop()` đánh dấu kết thúc **lifetime** và cho phép handler xử lý điểm cuối, ví dụ cập nhật timer hoặc kết thúc span.

Không nên suy luận rằng một request HTTP hoàn tất sẽ tự động dừng **custom observation** do bạn tạo thủ công. Tương tự, không nên coi việc scope bị đóng là observation đã hoàn tất.

### 1.1. Bất biến vòng đời

Đối với mỗi occurrence được start thành công, hãy thiết kế mã thỏa ba điều kiện:

| Điều kiện | Ý nghĩa | Nếu vi phạm |
| --- | --- | --- |
| **Có chủ sở hữu** | Một đoạn mã chịu trách nhiệm quản lý điểm kết thúc observation | Nhiều tầng cùng nghĩ tầng khác sẽ `stop()` |
| **Kết thúc trong mọi đường đi** | Thành công, `return`, exception, fallback và cancellation đều có đường kết thúc | Các lần lỗi bị thiếu trong duration/trace |
| **Kết thúc đúng một lần, đúng thời điểm** | `stop()` phản ánh thao tác thật sự hoàn tất | Dừng sớm làm duration ngắn giả; dừng lặp làm callback/meter khó dự đoán |

`stop()` không tự bảo đảm telemetry đã đến backend. Với metrics còn có registry/exporter; với tracing còn có sampler, bridge, exporter, collector và hệ thống lưu trữ. Nhưng nếu observation không đi qua vòng đời hợp lệ ngay từ ứng dụng, những bước phía sau khó có đủ thông tin chính xác.

## 2. Ưu tiên `observe(...)` cho thao tác đồng bộ

Nếu công việc thực thi đồng bộ và kết thúc khi lời gọi hàm trả về hoặc ném lỗi, dùng API `observe(...)` là cách đơn giản để tránh quên dừng:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class StockService {
    private final ObservationRegistry registry;
    private final StockGateway gateway;

    public StockService(ObservationRegistry registry, StockGateway gateway) {
        this.registry = registry;
        this.gateway = gateway;
    }

    public boolean reserve(String sku, int quantity) {
        return Observation.createNotStarted("inventory.reserve", registry)
                .lowCardinalityKeyValue("operation", "reserve")
                .lowCardinalityKeyValue("dependency", "inventory")
                .observe(() -> gateway.reserve(sku, quantity));
    }
}

// Mẫu giao diện; ứng dụng cung cấp implementation dưới dạng Spring bean.
interface StockGateway {
    boolean reserve(String sku, int quantity);
}
```

Một lời gọi `observe(...)` bao công việc bằng vòng đời cần thiết: start observation, mở scope, thực thi lambda, ghi nhận exception theo cơ chế API và đóng scope/stop khi công việc kết thúc. Khi `gateway.reserve(...)` trả `true`, `false` hoặc ném exception, việc dọn dẹp của API vẫn được thực hiện.

Lưu ý:

- Không tự gọi thêm `start()` hoặc `stop()` trên cùng observation được đưa vào `observe(...)`.
- `false` là một kết quả nghiệp vụ; nó **không tự động là exception**. Nếu cần tỷ lệ từ chối đặt chỗ, hãy định nghĩa tín hiệu outcome tương ứng.
- `observe(...)` thích hợp khi **lambda thực sự đại diện toàn bộ công việc cần đo**. Nếu lambda chỉ khởi tạo công việc rồi trả ngay một future, lifetime này sẽ không bao gồm thời gian xử lý future.
- Không đặt dữ liệu thay đổi vô hạn như `sku`, `userId`, `orderId`, token hoặc URL động vào low-cardinality key-value.

### 2.1. Trả về sớm vẫn phải kết thúc

Ví dụ một thao tác cần kiểm tra điều kiện rồi có thể kết thúc ngay:

```java
public boolean reserveIfAvailable(String sku, int quantity) {
    return Observation.createNotStarted("inventory.reserve", registry)
            .lowCardinalityKeyValue("operation", "reserve")
            .observe(() -> {
                if (quantity <= 0) {
                    return false;   // Observation vẫn được dừng.
                }
                if (!gateway.exists(sku)) {
                    return false;   // Observation vẫn được dừng.
                }
                return gateway.reserve(sku, quantity);
            });
}
```

Nhánh `return false` nằm **bên trong** lambda; API phụ trách kết thúc observation sau khi lambda hoàn tất. Cách này giảm xác suất một nhánh mới được thêm về sau mà quên dọn dẹp.

## 3. Nếu quản lý thủ công, đặt `stop()` trong `finally`

Đôi khi bạn cần điều khiển scope, ghi nhãn outcome trước khi dừng hoặc có nhiều bước muốn tách riêng. Khi đó, dùng `try-with-resources` cho scope và `finally` cho observation.

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class ReservationService {
    private final ObservationRegistry registry;
    private final ReservationGateway gateway;

    public ReservationService(ObservationRegistry registry,
                              ReservationGateway gateway) {
        this.registry = registry;
        this.gateway = gateway;
    }

    public ReservationResult reserve(String sku) {
        Observation observation =
                Observation.createNotStarted("inventory.reserve", registry)
                        .lowCardinalityKeyValue("dependency", "inventory")
                        .start();

        try (Observation.Scope scope = observation.openScope()) {
            ReservationResult result = gateway.reserve(sku);

            observation.lowCardinalityKeyValue(
                    "outcome", result.accepted() ? "accepted" : "rejected");

            return result; // finally vẫn chạy trước khi trả ra ngoài.
        } catch (RuntimeException | Error failure) {
            observation.error(failure);
            observation.lowCardinalityKeyValue("outcome", "error");
            throw failure;
        } finally {
            observation.stop();
        }
    }
}

record ReservationResult(boolean accepted) { }

interface ReservationGateway {
    ReservationResult reserve(String sku);
}
```

Mẫu này dùng Java 17+ và các dependency Spring Boot/Micrometer Observation tương thích. Ví dụ định nghĩa `ReservationGateway` tối giản để tập trung vào lifecycle.

Phân tích từng nhánh:

1. **Thành công:** `gateway.reserve` trả kết quả; nhãn `outcome` được gắn; `return` xảy ra nhưng Java vẫn gọi `finally` nên observation được dừng.
2. **Bị từ chối hợp lệ:** `accepted=false` vẫn đi theo nhánh thành công về mặt Java, nhưng mang `outcome=rejected`; observation được stop.
3. **Exception:** `catch` gọi `observation.error(failure)` để handler có thể nhận thông tin lỗi; sau đó ném lại. `finally` vẫn stop.
4. **Lỗi khi mở hoặc đóng scope:** nếu ném `RuntimeException` hoặc `Error` trong phạm vi `try`, khối `catch`/`finally` vẫn xử lý. Điều này không có nghĩa mọi lỗi từ handler hoặc exporter đều có thể phục hồi an toàn.
5. **Kết thúc scope:** `try-with-resources` đóng scope trước khi `finally` gọi `stop()`.

Trường hợp `start()` tự ném exception vì một handler bất thường cần được kiểm tra riêng: không nên giả định observation đã start thành công. Mẫu trên áp dụng cho observation đã được start thành công; đối với thao tác thông thường, hãy dựa vào API/framework có vòng đời quản lý sẵn thay vì tự xây dựng cơ chế phục hồi ở tầng instrumentation.

### 3.1. Vì sao không gọi `stop()` ở cuối hàm?

Đoạn sau nhìn có vẻ hợp lý nhưng sai:

```java
Observation observation = Observation
        .createNotStarted("checkout.pay", registry).start();

if (paymentAlreadyCompleted) {
    return receipt; // Bỏ qua stop().
}

chargeCard();        // Nếu ném exception, cũng bỏ qua stop().
observation.stop();
return receipt;
```

Đặt `stop()` ở một dòng cuối chỉ bao phủ đường chạy đi tới dòng đó. Một `return` mới, `throw`, timeout hoặc lỗi dependency có thể bỏ qua hoàn toàn.

Sửa bằng `try/finally`:

```java
Observation observation = Observation
        .createNotStarted("checkout.pay", registry).start();

try (Observation.Scope scope = observation.openScope()) {
    if (paymentAlreadyCompleted) {
        return receipt;
    }

    chargeCard();
    return receipt;
} catch (RuntimeException | Error failure) {
    observation.error(failure);
    throw failure;
} finally {
    observation.stop();
}
```

Nếu cần nhiều method trả về kiểu khác nhau, không nhất thiết đưa toàn bộ logic vào một hàm khổng lồ; điều cốt lõi là **mỗi nhánh phải nằm trong cùng một cơ chế cleanup có chủ sở hữu rõ ràng**.

### 3.2. Đừng `return`, `throw` hoặc ghi đè kết quả tùy ý trong `finally`

`finally` là nơi dọn dẹp, không nên được dùng để thay đổi logic nghiệp vụ:

```java
try {
    return gateway.reserve(sku);
} finally {
    observation.stop();
    // Không: return false;
    // Không: throw new IllegalStateException("cleanup");
}
```

Một `return` trong `finally` có thể che mất exception thật; một exception mới từ cleanup cũng có thể thay thế exception ban đầu. Nếu dự án có custom ObservationHandler hoặc exporter có khả năng ném lỗi trong quá trình cleanup, cần áp dụng chính sách xử lý lỗi telemetry thống nhất thay vì tự nuốt mọi exception.

## 4. Phân biệt lifetime, scope và việc ghi nhận lỗi

Có ba hành động dễ bị gộp làm một:

| Hành động | Chịu trách nhiệm | Có thay thế `stop()` không? |
| --- | --- | --- |
| `observation.error(exception)` | Gắn lỗi vào context, báo thông tin lỗi cho handler | Không |
| `scope.close()` | Khôi phục ngữ cảnh hiện hành trên luồng thực thi | Không |
| `observation.stop()` | Kết thúc lifetime của occurrence và kích hoạt callback kết thúc | Chính là thao tác cần bảo đảm |

Ví dụ:

```text
request được nhận
  |
  +-- checkout observation START
  |     |
  |     +-- scope OPEN
  |     |    |
  |     |    +-- gọi payment API
  |     |         |
  |     |         +-- timeout -> error(timeout)
  |     |
  |     +-- scope CLOSE
  |
  +-- checkout observation STOP
  |
request trả lỗi cho client
```

Trong hệ thống có tracing handler, mở scope giúp log phát ra trong giai đoạn xử lý nhìn thấy trace/span context đang hoạt động; đóng scope giúp tránh để ngữ cảnh cũ ảnh hưởng công việc kế tiếp trên cùng thread. Cả hai thao tác vẫn khác thời điểm dừng lifetime.

Một lỗi nghiệp vụ như `payment declined` có thể cần tag `outcome=declined` chứ không nhất thiết cần exception. Ngược lại, exception thật nên được chuyển đến `observation.error(...)` khi bạn tự quản lý vòng đời, để handler có đủ bằng chứng xử lý.

### 4.1. Chọn thời điểm gắn tag

Một số tag cố định có thể biết **trước start**, ví dụ `operation=reserve`. Tag kết quả chỉ biết **sau khi công việc chạy**, ví dụ `outcome=accepted|rejected|error`; hãy gắn **trước stop** nếu muốn handler dùng chúng khi hoàn tất.

```java
Observation observation = Observation
        .createNotStarted("inventory.reserve", registry)
        .lowCardinalityKeyValue("operation", "reserve")
        .start();

try (Observation.Scope scope = observation.openScope()) {
    boolean accepted = gateway.reserve(sku, quantity);
    observation.lowCardinalityKeyValue(
            "outcome", accepted ? "accepted" : "rejected");
    return accepted;
} catch (RuntimeException | Error e) {
    observation.error(e);
    observation.lowCardinalityKeyValue("outcome", "error");
    throw e;
} finally {
    observation.stop();
}
```

Tùy loại handler, convention và thời điểm đọc context, việc thêm tag sau `start()` có thể có ý nghĩa khác nhau. Hãy kiểm tra đầu ra ở backend mục tiêu; tránh gắn thêm tag sau khi observation đã stop rồi kỳ vọng timer/span đã export tự thay đổi.

## 5. Bảng kiểm các nhánh đồng bộ thường bị bỏ sót

| Nhánh | Điều dễ sai | Hướng xử lý |
| --- | --- | --- |
| Xử lý thành công | Đặt `stop()` ở cuối nhưng sau này thêm nhánh mới | Dùng `observe(...)` hoặc `finally` |
| `return` sớm | Trả trước khi chạy cleanup | Đặt toàn bộ quyết định bên trong `try` hoặc lambda `observe` |
| Exception | `throw` bỏ qua stop hoặc không gắn lỗi | `catch` → `error` → rethrow; `finally` → `stop` |
| Fallback | Catch exception, trả dữ liệu mặc định mà không báo gì | Ghi outcome/fallback riêng; stop trong finally |
| Điều kiện đầu vào không hợp lệ | Start quá sớm khiến metric bao cả validation không cần thiết | Xác định rõ ranh giới phép đo; nếu đã start thì vẫn phải stop |
| Retry | Mỗi lần thử mở observation nhưng chỉ stop một lần cuối | Phân biệt observation tổng và observation từng attempt |
| Timeout | Hàm trả timeout nhưng công việc nền vẫn chạy | Chọn ranh giới đo rõ ràng: client-facing timeout hay actual work |
| Cleanup tự ném lỗi | Exception mới che exception chính | Chuẩn hóa xử lý lỗi hạ tầng quan sát, không `return` trong `finally` |

Một nguyên tắc thiết kế thực dụng: **Observation thuộc về nơi tạo ra nó**. Nơi khác có thể thêm key-value hoặc event nếu được cho phép, nhưng không nên tự dừng observation của caller khi không nắm chắc ranh giới lifetime.

## 6. Với `CompletableFuture`: đừng stop ngay khi vừa lên lịch công việc

Đây là lỗi phổ biến trong mã bất đồng bộ:

```java
public CompletableFuture<Receipt> payAsync() {
    return Observation.createNotStarted("checkout.pay", registry)
            .observe(() -> paymentClient.payAsync());
}
```

Lệnh trên kết thúc observation ngay sau khi `payAsync()` **trả về đối tượng future**. Công việc ở tầng payment có thể vẫn chạy thêm hàng trăm mili giây hoặc vài giây. Kết quả là timer/span của `checkout.pay` phản ánh thời gian *khởi tạo* lời gọi bất đồng bộ, không phải thời gian đến khi kết quả hoàn tất.

### 6.1. Gắn điểm stop vào terminal completion của future

Ví dụ sau giả định `PaymentClient.payAsync()` trả về `CompletableFuture<Receipt>` và cung cấp cách kiểm soát cleanup khi có callback hoàn tất:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public class PaymentOrchestrator {
    private final ObservationRegistry registry;
    private final PaymentClient client;

    public PaymentOrchestrator(ObservationRegistry registry,
                               PaymentClient client) {
        this.registry = registry;
        this.client = client;
    }

    public CompletableFuture<Receipt> payAsync() {
        Observation observation =
                Observation.createNotStarted("checkout.pay.async", registry)
                        .lowCardinalityKeyValue("dependency", "payment")
                        .start();

        AtomicBoolean stopped = new AtomicBoolean(false);

        Runnable stopOnce = () -> {
            if (stopped.compareAndSet(false, true)) {
                observation.stop();
            }
        };

        try {
            CompletableFuture<Receipt> source;

            // Scope của phần khởi tạo; future vẫn chạy sau khi scope đóng.
            try (Observation.Scope scope = observation.openScope()) {
                source = client.payAsync();
            }

            return source.whenComplete((receipt, failure) -> {
                try (Observation.Scope scope = observation.openScope()) {
                    if (failure != null) {
                        observation.error(failure);
                    }
                } finally {
                    stopOnce.run();
                }
            });
        } catch (RuntimeException | Error setupFailure) {
            observation.error(setupFailure);
            stopOnce.run();
            throw setupFailure;
        }
    }
}

interface PaymentClient {
    CompletableFuture<Receipt> payAsync();
}

record Receipt(String reference) { }
```

Bản này thể hiện hai tình huống:

1. **Khởi tạo future thất bại ngay:** `catch` ghi nhận lỗi và dừng observation.
2. **Future nguồn hoàn tất:** callback `whenComplete` ghi nhận lỗi nếu có và gọi `stopOnce`, kể cả khi callback có exception.

`AtomicBoolean` ở đây cung cấp cơ chế **chỉ một bên có quyền thực hiện stop**, cần thiết nếu các đường kết thúc có thể cạnh tranh nhau. Dù vậy, đây là mẫu dạy về vòng đời, chưa phải một lớp orchestration hoàn chỉnh cho mọi hệ thống future.

**Cần phân biệt hủy future với dừng tác vụ thật.** Hủy một `CompletableFuture` phụ thuộc không nhất thiết hủy công việc đang chạy ở dependency. Một future có thể chuyển sang trạng thái completed/cancelled trong khi tác vụ phía sau vẫn còn đang thực thi. Nếu mục tiêu là đo thời gian *cho đến khi người dùng nhận kết quả hoặc timeout*, bạn có thể kết thúc observation ở ranh giới đó. Nếu mục tiêu là đo *thời gian xử lý thực tế của dependency*, phải gắn stop vào tín hiệu hoàn tất của chính công việc đó. Với cancellation, hãy định nghĩa rõ cơ chế truyền yêu cầu hủy và đường cleanup riêng.

Điểm này quan trọng đối với distributed tracing: span của lời gọi client có thể kết thúc ở lúc timeout, còn công việc phía server vẫn tiếp tục; hai span có thể khác thời lượng một cách hợp lý.

### 6.2. Scope không tự đi qua thread mới

Scope được mở tại thread chạy `payAsync()` rồi được đóng tại đó. Khi callback chạy trên thread khác, context của scope **không tự động được kế thừa trong mọi trường hợp**. Ví dụ mở scope trong callback giúp gắn observation hiện hành tại chỗ callback; nhưng nó không bảo đảm các bước xử lý *bên trong* `PaymentClient` đã nhận đúng trace context.

Khi dùng Spring Boot, hãy kiểm chứng instrumentation của HTTP client, propagation header (`traceparent`), executor và Micrometer Context Propagation. Gắn `stop()` đúng lúc giải quyết lifecycle; **truyền trace context** qua các ranh giới thực thi là trách nhiệm khác.

## 7. Với Reactor: dừng observation khi stream kết thúc hoặc bị cancel

Trong ứng dụng Spring WebFlux/Reactor, `Mono` và `Flux` là các publisher; một publisher lạnh (cold publisher) chỉ thực thi khi có subscription. Việc tạo publisher không đồng nghĩa công việc đã chạy.

Đoạn sau dễ sai:

```java
public Mono<Receipt> payReactive() {
    return Observation.createNotStarted("checkout.pay.reactive", registry)
            .observe(() -> paymentClient.payReactive());
}
```

Observation có thể kết thúc ngay sau khi trả về `Mono`, trước khi subscriber kích hoạt lời gọi thực tế.

### 7.1. Tạo Observation cho từng subscription, dừng ở `doFinally`

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import reactor.core.publisher.Mono;

public class ReactivePaymentService {
    private final ObservationRegistry registry;
    private final ReactivePaymentClient client;

    public ReactivePaymentService(ObservationRegistry registry,
                                  ReactivePaymentClient client) {
        this.registry = registry;
        this.client = client;
    }

    public Mono<Receipt> pay() {
        return Mono.defer(() -> {
            Observation observation = Observation
                    .createNotStarted("checkout.pay.reactive", registry)
                    .lowCardinalityKeyValue("dependency", "payment")
                    .start();

            try {
                return client.pay()
                        .doOnError(observation::error)
                        .doFinally(signalType -> observation.stop());
            } catch (RuntimeException | Error setupFailure) {
                observation.error(setupFailure);
                observation.stop();
                throw setupFailure;
            }
        });
    }
}

interface ReactivePaymentClient {
    Mono<Receipt> pay();
}
```

Vì Observation được tạo *bên trong* `Mono.defer(...)`, mỗi subscription bình thường có occurrence riêng. `doFinally` là hook chạy sau khi publisher nhận terminal signal:

- `ON_COMPLETE`: hoàn tất thành công, kể cả Mono rỗng.
- `ON_ERROR`: hoàn tất bằng lỗi, thường đã được ghi bởi `doOnError`.
- `CANCEL`: subscription bị hủy; vẫn cần cleanup.

Đây là minh họa một thao tác reactive đơn giản; các operator khác (`retry`, `timeout`, `share`, `cache`) và vị trí lắp chúng có thể thay đổi *vòng đời thực sự được đo*. Chẳng hạn nếu `retry` nằm **bên trong** chuỗi được bao bởi observation, một observation có thể đo tổng các lần thử; nếu `retry` nằm ngoài và subscribe lại `Mono.defer`, mỗi lần thử có thể tạo occurrence mới.

**Hạn chế của ví dụ:** `doFinally` đảm bảo hook cleanup cho chuỗi có subscription hợp lệ, nhưng **không tự truyền scope qua Reactor Context** và không tự instrument các lời gọi downstream. Nếu cần trace xuyên operator hoặc xuyên thread, hãy sử dụng integration context propagation của Reactor/Micrometer và đo kết quả thực tế. Với các pipeline phức tạp, xác định rõ phần nào của chuỗi thuộc observation, vì downstream có thể còn các operator chạy sau `doFinally`.

### 7.2. Cancellation có phải lỗi không?

Không mặc định. Một client đóng kết nối có thể khiến subscription bị cancel, nhưng không nhất thiết là exception do nghiệp vụ gây ra. Nếu cancellation là tín hiệu cần theo dõi, hãy định nghĩa outcome riêng như `outcome=cancelled` hoặc meter chuyên biệt với số giá trị hữu hạn. Một số môi trường có thể chuyển timeout thành `TimeoutException`, một số trường hợp chuyển thành cancel; không ép mọi cancellation thành `error` nếu chưa xác định ý nghĩa.

Trong thực tế, khi việc hủy signal không thể dừng công việc thật ở backend, hãy quan sát **hai ranh giới**:

- Thời gian từ khi client yêu cầu đến lúc client nhận timeout/hủy.
- Thời gian tác vụ thật thực thi cho đến khi hệ thống ngừng xử lý/hoàn tất.

Đây là hai phép đo khác nhau và cần tên observation khác nhau nếu muốn đối chiếu.

## 8. Retry, timeout và nhiều lớp instrumentation

### 8.1. Retry: đo tổng thời gian và từng attempt

Ví dụ một thao tác thanh toán thử tối đa ba lần:

```text
checkout.pay (observation tổng)
    |
    +-- payment.attempt #1 -> timeout -> stop
    +-- backoff 200 ms
    +-- payment.attempt #2 -> 503     -> stop
    +-- backoff 400 ms
    +-- payment.attempt #3 -> OK      -> stop
checkout.pay -> stop
```

Có thể dùng một observation tổng `checkout.pay` để đo thời gian thực tế người dùng chờ, bao gồm retry/backoff. Nếu cần chẩn đoán từng attempt, tạo observation con `payment.attempt` cho **mỗi attempt** bằng `observe(...)` hoặc `try/finally` ngay tại vòng lặp.

Đừng chỉ tạo một child observation trước vòng lặp rồi dừng sau attempt đầu tiên, cũng đừng start mới cho attempt tiếp theo mà quên stop occurrence trước đó. Số lần retry có thể là metric/tags riêng với tập giá trị giới hạn; tránh dùng ID của mỗi request làm metric label.

### 8.2. Timeout: xác định thứ gì đã kết thúc

Một timeout ở gateway có thể xảy ra trước khi Spring Boot xử lý xong. Nếu bạn dừng custom observation ở thời điểm request bị hủy, nó mô tả vòng đời gắn với request. Nhưng nếu một tác vụ được tách ra để chạy nền và sống lâu hơn request, cần đo tác vụ đó bằng observation **riêng**, có chủ sở hữu và stop tại completion thật sự.

Không dùng `Thread.sleep(...)`, callback hoặc scheduler chỉ để “dừng hộ” observation sau một khoảng thời gian cố định mà không xem công việc có kết thúc hay chưa. Làm vậy có thể biến các request chậm thành timer ngắn giả.

### 8.3. Instrumentation của framework và custom code

Spring Boot Actuator, HTTP server/client instrumentation và một số integration Micrometer đã tạo observation tại ranh giới sẵn có. Bạn không cần tạo thêm observation thủ công chỉ để đo lại cùng một HTTP call nếu không có câu hỏi nghiệp vụ riêng.

Ví dụ phân tầng hợp lý:

| Ranh giới | Loại instrumentation | Điểm stop dự kiến |
| --- | --- | --- |
| HTTP server request | Framework instrumentation | Khi xử lý request hoàn tất theo ranh giới framework |
| `checkout.place-order` | Custom nghiệp vụ | Khi toàn bộ nghiệp vụ đặt đơn hoàn tất |
| HTTP client payment call | HTTP client instrumentation | Khi lời gọi client kết thúc/thất bại theo ranh giới client |
| Background reconciliation job | Custom công việc nền | Khi job thực sự hoàn tất hoặc bị hủy |

Một trace có nhiều span là điều bình thường nếu các span mô tả **các công việc khác nhau**. Nếu thấy nhiều span gần như giống hệt ở cùng một ranh giới, hãy xem lại việc instrument trùng.

## 9. `stop()` ảnh hưởng tới metrics, traces và logs như thế nào?

Observation có thể có nhiều handler, tùy cấu hình `ObservationRegistry`:

| Tín hiệu | Vai trò của start/stop | Dấu hiệu khi kết thúc sai |
| --- | --- | --- |
| **Metrics** | Metrics handler thường đo khoảng thời gian từ start đến stop và cập nhật meter ở lúc kết thúc | Timer count/duration có thể thiếu các lần lỗi hoặc phản ánh thời gian quá ngắn |
| **Tracing** | Tracing handler có thể tạo và kết thúc span, gắn error/tags | Span không thấy, chưa đóng đúng lúc hoặc duration không phản ánh ranh giới đã định |
| **Logs** | Scope/tracing context giúp log phát trong công việc có traceId/spanId khi cấu hình | Log sau khi scope đóng mất correlation; log không tự được tạo chỉ vì stop |
| **Exporter/collector** | Nhận dữ liệu từ registry/bridge và gửi tới backend | Có stop đúng vẫn có thể thiếu dữ liệu vì sampling, lỗi exporter hoặc backend |

Điều quan trọng: **stop đúng là điều kiện cần, chưa đủ để thấy telemetry trên dashboard**. Một trace đã bị sampling loại vẫn có thể làm đúng lifecycle; một meter bị lọc hoặc registry không được export cũng có thể không xuất hiện ở backend. Vì vậy khi kiểm tra phải tách ba lớp:

1. **Mã ứng dụng:** Có start, scope và stop tại đúng ranh giới không?
2. **Instrumentation:** Registry có handler/convention phù hợp không? Tag có đúng không?
3. **Pipeline dữ liệu:** Metrics registry, tracing bridge, exporter, collector và hệ thống lưu trữ có hoạt động không?

### 9.1. Ví dụ cấu hình trong Spring Boot 3.x

Với Spring Boot 3.x được quản lý dependency qua Spring Boot BOM, Actuator cung cấp nhiều tích hợp quan sát:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<!-- Thêm khi muốn xuất Prometheus metrics -->
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>

<!-- Thêm khi muốn tracing qua OpenTelemetry -->
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>

<!-- Export traces tới collector qua OTLP -->
<dependency>
    <groupId>io.opentelemetry</groupId>
    <artifactId>opentelemetry-exporter-otlp</artifactId>
</dependency>
```

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
```

Khi chạy trong môi trường lab, gọi một endpoint dẫn tới `inventory.reserve` rồi xem:

```bash
curl -fsS http://localhost:8080/actuator/metrics
curl -fsS http://localhost:8080/actuator/metrics/inventory.reserve
curl -fsS http://localhost:8080/actuator/prometheus
```

Meter chỉ xuất hiện khi thao tác đã được thực thi và có metrics handler phù hợp. Trong môi trường thực, không công khai các endpoint Actuator nếu chưa có bảo vệ network và phân quyền phù hợp.

**Chú ý phiên bản:** Spring Boot 4.x có thay đổi starter và cấu hình OTLP/tracing so với 3.x. Khi áp dụng, đối chiếu tài liệu chính thức của đúng phiên bản đang chạy. Ý nghĩa `start`/`scope`/`stop` và yêu cầu quản lý lifetime vẫn là trọng tâm.

## 10. Cách chứng minh mọi nhánh đã dừng observation

Không nên kiểm chứng bằng cách “gọi API thấy 200 là xong”. Tạo các nhánh có kiểm soát, đo cả callback lifecycle lẫn tín hiệu đầu ra.

### 10.1. Gắn handler để quan sát start và stop

Trong một ví dụ thử nghiệm độc lập, có thể đăng ký handler đếm callback:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import java.util.concurrent.atomic.AtomicInteger;

final class LifecycleProbe
        implements ObservationHandler<Observation.Context> {

    final AtomicInteger started = new AtomicInteger();
    final AtomicInteger stopped = new AtomicInteger();

    @Override
    public boolean supportsContext(Observation.Context context) {
        return true;
    }

    @Override
    public void onStart(Observation.Context context) {
        started.incrementAndGet();
    }

    @Override
    public void onStop(Observation.Context context) {
        stopped.incrementAndGet();
    }
}

// Trong thử nghiệm độc lập:
ObservationRegistry registry = ObservationRegistry.create();
LifecycleProbe probe = new LifecycleProbe();
registry.observationConfig().observationHandler(probe);

Observation.createNotStarted("demo.operation", registry)
        .observe(() -> "completed");

// Sau lời gọi đồng bộ:
// probe.started.get() == 1
// probe.stopped.get() == 1
```

Đoạn minh họa trên cần được đặt trong class/phương thức thử nghiệm phù hợp, không phải một file Java hoàn chỉnh có thể biên dịch ngay. Nếu framework đã đăng ký handler khác, đừng thay registry chung của production bằng registry thử nghiệm chỉ để đếm.

### 10.2. Ma trận nhánh cần quan sát

| Kịch bản chủ động tạo | Kết quả mong đợi về vòng đời | Điều cần đối chiếu thêm |
| --- | --- | --- |
| Xử lý thành công | 1 start, 1 stop | Duration/timer và log/trace mẫu |
| Trả về sớm do validate | 1 start, 1 stop nếu observation đã start | Outcome không bị gộp nhầm với exception |
| Exception từ dependency | 1 start, 1 error, 1 stop nếu handler ghi nhận error | Exception còn được truyền đúng cho caller |
| Fallback sau exception | 1 start, 1 stop | Business fallback được đo theo định nghĩa |
| Future hoàn tất trễ | Stop tại completion đã chọn, không phải lúc trả future | So sánh duration với wall-clock |
| Future khởi tạo thất bại | 1 start, 1 stop | Lỗi được ghi nhận |
| Reactive completion | Mỗi subscription 1 start, 1 stop | Chú ý retry/subscribe lại |
| Reactive error | Mỗi subscription 1 start, 1 stop | Error signal được ghi nhận |
| Reactive cancellation | Scope/observation được cleanup tại cancellation của chuỗi đo | Tác vụ downstream có thật sự bị hủy hay vẫn chạy? |
| Race giữa timeout và callback | Chủ sở hữu kết thúc rõ ràng; không stop hai lần | Dùng guard/cơ chế đồng bộ khi cần |

Khi đối chiếu lifecycle, **kiểm tra số start/stop theo cùng một observation occurrence** chứ không chỉ so tổng toàn hệ thống. Nếu có nhiều request chạy đồng thời, tổng số có thể trùng nhau dù một observation bị dừng hai lần còn observation khác bị bỏ sót.

### 10.3. Dấu hiệu từ hệ thống đang vận hành

- Số request tại gateway lớn hơn nhiều so với timer count của custom observation: có thể request chưa vào nhánh instrumentation, bị trả sớm, hoặc không stop; cũng có thể khác mẫu số đo.
- Trace có span thiếu thời gian/kết thúc bất thường: kiểm tra scope, start/stop, callback hoàn tất, sampling và exporter.
- Log có `traceId` nhưng không tìm thấy trace: có thể trace bị sampling loại, backend thiếu dữ liệu hoặc trace context bị đứt; chưa thể kết luận observation chưa stop.
- p99 của custom async step luôn nhỏ hơn rất nhiều so với client latency: kiểm tra có phải observation chỉ đo thời gian tạo future/Mono không.
- Metric tag `outcome` thiếu cho một số nhánh: kiểm tra thứ tự gắn tag trước stop, nhánh exception và việc handler dùng context ở thời điểm nào.

## 11. Bài thực hành: tìm nhánh bị rò lifetime

Giả sử bạn nhận mã sau:

```java
public String fulfill(String orderId) {
    Observation observation = Observation
            .createNotStarted("order.fulfill", registry)
            .start();

    if (orderId == null) {
        return "INVALID";
    }

    try (Observation.Scope scope = observation.openScope()) {
        return fulfillmentService.fulfill(orderId);
    } catch (RuntimeException e) {
        return "FALLBACK";
    }
}
```

Hãy chỉ ra ít nhất bốn vấn đề:

1. Observation đã start nhưng không có `stop()` ở bất kỳ nhánh nào.
2. `return "INVALID"` trước `try` khiến nhánh kiểm tra đầu vào không đi qua cleanup.
3. Nhánh exception trả fallback nhưng không có `observation.error(e)` hoặc tín hiệu riêng mô tả fallback.
4. Không có chủ sở hữu rõ ràng cho việc stop khi thêm các nhánh mới; trace/timer có thể thiếu dữ liệu.

Một cách sửa bằng `try/finally`:

```java
public String fulfill(String orderId) {
    Observation observation = Observation
            .createNotStarted("order.fulfill", registry)
            .lowCardinalityKeyValue("operation", "fulfill")
            .start();

    try (Observation.Scope scope = observation.openScope()) {
        if (orderId == null) {
            observation.lowCardinalityKeyValue("outcome", "invalid");
            return "INVALID";
        }

        try {
            String result = fulfillmentService.fulfill(orderId);
            observation.lowCardinalityKeyValue("outcome", "completed");
            return result;
        } catch (RuntimeException failure) {
            observation.error(failure);
            observation.lowCardinalityKeyValue("outcome", "fallback");
            return "FALLBACK";
        }
    } finally {
        observation.stop();
    }
}
```

Ví dụ chỉ minh họa lifecycle. Khi xây dựng ứng dụng thật, hãy xác định fallback nào có thể chấp nhận, lỗi nào cần trả ra client và thông tin nào được phép đưa vào metrics/logs. `orderId` là dữ liệu động, không được dùng làm metric label.

### Câu hỏi tự kiểm tra

**Câu 1.** Nếu `Scope.close()` đã chạy nhưng `Observation.stop()` chưa được gọi, observation đã hoàn tất chưa?

**Đáp án:** Chưa. Scope đóng ngữ cảnh hiện hành; stop kết thúc lifetime và thông báo cho handler. Hai cơ chế phải được quản lý đúng.

**Câu 2.** Vì sao `observe(() -> client.callAsync())` có thể cho duration sai?

**Đáp án:** Lambda có thể trả ngay một future/publisher trước khi công việc kết thúc. Observation sẽ đo thời gian tạo hoặc lên lịch lời gọi. Hãy gắn điểm dừng vào tín hiệu hoàn tất thực sự theo ranh giới được định nghĩa.

**Câu 3.** Khi Reactor chain bị cancel, có nên để observation chờ mãi cho đến lúc hoàn tất tự nhiên?

**Đáp án:** Không. Subscription đã kết thúc cần có cleanup, ví dụ `doFinally`. Tuy nhiên phải xác định nó đang đo thời gian subscription hay công việc thật, bởi cancellation không luôn dừng được tác vụ ở backend.

**Câu 4.** Có nên dùng một tag `orderId` trên timer để tìm những đơn bị timeout?

**Đáp án:** Không. ID động gây cardinality rất cao và có thể chứa dữ liệu cần bảo vệ. Dùng tag kết quả có tập giá trị hữu hạn; dùng log/trace correlation với chính sách dữ liệu phù hợp để điều tra từng request.

## 12. Các nguyên tắc cần mang vào production

- **Xác định ranh giới phép đo trước khi start:** request, bước nghiệp vụ, mỗi attempt, toàn bộ chuỗi retry hay tác vụ nền là các lifetime khác nhau.
- **Có một nơi chịu trách nhiệm stop:** dùng `observe(...)` cho đồng bộ, `try/finally` khi tự điều khiển, terminal callback hoặc `doFinally` khi bất đồng bộ/reactive.
- **Bao phủ mọi đường đi:** early return, exception, fallback, timeout, cancellation, retry và shutdown; không để chỗ nào dựa vào việc “sau này sẽ có ai đó stop”.
- **Đóng scope và stop đúng vai trò:** scope phục vụ current context; stop phục vụ lifetime. Tăng tính tin cậy của trace/log còn cần propagation qua thread, HTTP và message broker.
- **Ghi lỗi và outcome có ngữ nghĩa:** phân biệt exception với business rejection; gắn low-cardinality keys ổn định trước khi handler hoàn tất.
- **Đối chiếu bằng nhiều tín hiệu:** metrics đo tần suất/thời lượng, traces đo đường đi mẫu, logs cung cấp sự kiện; sampling và exporter có thể khiến backend không lưu mọi trace.
- **Chứng minh bằng từng nhánh:** quan sát start/stop trên cùng occurrence và so duration với công việc thật, nhất là async/reactive.

### Tài liệu tham khảo

- [Micrometer — Observation API và khái niệm cơ bản](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer — Observation components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)

