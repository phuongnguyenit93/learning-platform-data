# Đơn vị ghi nhận của một subscription so với từng phần tử Flux

Trong ứng dụng reactive, một `Flux` có thể phát ra một phần tử, nhiều phần tử hoặc không có phần tử nào. Khi bọc toàn bộ `Flux` bằng circuit breaker, cần hiểu circuit breaker đang bảo vệ một lần thực thi của publisher hay từng thao tác độc lập bên trong luồng. Sự khác biệt này ảnh hưởng trực tiếp đến số lời gọi được ghi nhận, failure rate, số quyền trong `HALF_OPEN` và cách đọc metrics.

Với Resilience4j Reactor, circuit breaker đặt quanh một `Flux` thường ghi nhận **một lần thực thi cho mỗi subscription**. Nó không tự động xem mỗi tín hiệu `onNext` là một lời gọi độc lập. Một subscription có thể phát ra hàng trăm phần tử nhưng vẫn chỉ tạo một kết quả hoàn tất hoặc thất bại cho circuit breaker. Nếu mỗi phần tử cần gọi một dịch vụ phụ thuộc riêng, hãy bọc từng lời gọi con bằng circuit breaker để mỗi thao tác có kết quả thống kê riêng.

Đây là điểm quan trọng khi triển khai Spring Cloud CircuitBreaker cho các luồng reactive: cần xác định ranh giới của một lời gọi phụ thuộc trước khi quyết định đặt circuit breaker ở đâu.

## 1. Reactive Streams có subscription và tín hiệu phần tử

Theo mô hình Reactive Streams, một `Publisher` nhận một hoặc nhiều `Subscriber`. Mỗi lần `subscribe()` tạo một subscription. Trong subscription đó, publisher có thể phát ra các tín hiệu:

- `onNext(value)`: phát một phần tử dữ liệu.
- `onComplete()`: kết thúc luồng bình thường.
- `onError(error)`: kết thúc luồng bằng lỗi.
- `cancel()`: subscriber yêu cầu hủy việc nhận dữ liệu.

Với `Flux<T>`, một subscription có thể phát ra 0..N tín hiệu `onNext`, sau đó kết thúc bằng `onComplete` hoặc `onError` nếu không bị hủy. Với `Mono<T>`, một subscription phát tối đa một phần tử rồi kết thúc.

Circuit breaker là cơ chế bảo vệ một thao tác hoặc lời gọi có kết quả thành công/thất bại. Khi áp dụng Reactor operator của Resilience4j lên `Flux`, operator tham gia vào quá trình subscribe và theo dõi kết quả kết thúc của subscription. Các phần tử `onNext` được chuyển tiếp; chúng không tự động làm tăng số lời gọi thành công.

| Khái niệm | Ý nghĩa trong Reactive Streams | Ý nghĩa khi có circuit breaker bao quanh publisher |
|---|---|---|
| Subscription | Một lần subscriber đăng ký nhận dữ liệu từ publisher. | Thường là một lần thực thi được bảo vệ và được cấp quyền. |
| `onNext` | Một phần tử được phát ra. | Chỉ là dữ liệu trong lần thực thi hiện tại, không phải một call riêng. |
| `onComplete` | Publisher kết thúc bình thường. | Kết quả thực thi được ghi nhận thành công. |
| `onError` | Publisher kết thúc bằng lỗi. | Kết quả thực thi được ghi nhận là lỗi nếu exception được cấu hình để ghi nhận. |
| `cancel` | Subscriber hủy việc nhận dữ liệu. | Không tương đương với hoàn tất hoặc lỗi; cách giải phóng quyền và thống kê phụ thuộc operator/phiên bản. |

Ví dụ, một subscription đến `Flux` phát 500 bản ghi và hoàn tất bình thường vẫn là một lần thực thi thành công của circuit breaker. Nếu publisher phát 200 bản ghi rồi phát `onError`, lần thực thi đó kết thúc bằng lỗi dù một phần dữ liệu đã được gửi đến subscriber.

## 2. Circuit breaker bao quanh toàn bộ Flux

Resilience4j cung cấp Reactor operator để bọc một `Mono` hoặc `Flux`. Với `Flux`, có thể dùng `CircuitBreakerOperator`:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.reactor.circuitbreaker.operator.CircuitBreakerOperator;
import reactor.core.publisher.Flux;

public class InventoryStreamService {
    private final CircuitBreaker inventoryStreamCircuitBreaker;
    private final InventoryClient inventoryClient;

    public InventoryStreamService(
            CircuitBreaker inventoryStreamCircuitBreaker,
            InventoryClient inventoryClient) {
        this.inventoryStreamCircuitBreaker = inventoryStreamCircuitBreaker;
        this.inventoryClient = inventoryClient;
    }

    public Flux<StockUpdate> streamUpdates(String sku) {
        return inventoryClient.streamUpdates(sku)
            .transform(CircuitBreakerOperator.of(inventoryStreamCircuitBreaker));
    }
}
```

Trong ví dụ, `inventoryClient.streamUpdates(sku)` có thể phát nhiều `StockUpdate`. Circuit breaker bảo vệ lần subscribe vào luồng đó. Nếu một subscriber nhận 100 phần tử và luồng hoàn tất, circuit breaker ghi nhận một kết quả thành công. Nếu subscriber khác subscribe lại vào một nguồn cold, lần subscribe thứ hai là một lần thực thi mới và có thể được ghi nhận thêm một kết quả.

Để sử dụng `CircuitBreakerOperator`, ứng dụng cần module tích hợp Reactor của Resilience4j, thường là `resilience4j-reactor`, cùng các module circuit breaker và Reactor tương ứng. Phiên bản module cần đồng bộ với Resilience4j được Spring Cloud starter quản lý.

## 3. Số phần tử Flux không phải số call của circuit breaker

Giả sử một subscription đến dịch vụ tồn kho phát 1.000 bản cập nhật rồi hoàn tất. Nếu circuit breaker bao quanh toàn bộ `Flux`, thống kê của circuit breaker phản ánh một lần thực thi, không phải 1.000 lần gọi thành công.

| Hành vi của một subscription | Số `onNext` | Kết quả kết thúc | Số kết quả thực thi được ghi nhận |
|---|---:|---|---:|
| Luồng phát 10 phần tử rồi hoàn tất | 10 | Success | 1 |
| Luồng phát 1.000 phần tử rồi hoàn tất | 1.000 | Success | 1 |
| Luồng phát 200 phần tử rồi phát lỗi được ghi nhận | 200 | Failure | 1 |
| Luồng hoàn tất mà không phát phần tử | 0 | Success | 1 |

Một `Flux` rỗng hoàn tất bình thường vẫn là một subscription kết thúc thành công. Số phần tử bằng 0 không đồng nghĩa với lời gọi thất bại. Nếu nghiệp vụ yêu cầu phải có ít nhất một phần tử, hãy kiểm tra điều kiện đó trong logic ứng dụng và chuyển thành lỗi nghiệp vụ phù hợp khi cần; circuit breaker không tự suy luận rằng luồng rỗng là lỗi.

Tương tự, một phần tử dữ liệu mang trạng thái “không tìm thấy” hoặc “không khả dụng” vẫn có thể được phát ra qua `onNext`. Nếu publisher hoàn tất bình thường, circuit breaker thường xem đó là thành công về mặt kỹ thuật. Muốn xem kết quả nghiệp vụ đó là lỗi, ứng dụng phải chuyển nó thành tín hiệu lỗi hoặc dùng cơ chế phân loại kết quả phù hợp.

## 4. Khi mỗi phần tử đại diện cho một lời gọi độc lập

Có trường hợp mỗi phần tử đầu vào kích hoạt một request riêng đến dịch vụ phụ thuộc. Khi đó, circuit breaker nên được đặt quanh từng request con thay vì chỉ bao quanh toàn bộ `Flux` đầu vào.

Ví dụ, mỗi SKU trong luồng đầu vào cần tra cứu tồn kho bằng một lời gọi `Mono<Stock>`:

```java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class InventoryLookupService {
    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryLookupService(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public Flux<Stock> lookupAll(Flux<String> skuStream) {
        return skuStream.flatMap(sku ->
            circuitBreakerFactory.create("inventory-item").run(
                inventoryClient.getStock(sku),
                error -> Mono.just(Stock.unavailable(sku))
            ),
            16
        );
    }
}
```

Ở đây, mỗi SKU tạo một lời gọi `Mono` riêng qua circuit breaker `inventory-item`. Mỗi inner publisher được subscribe khi `flatMap` xử lý phần tử đầu vào, vì vậy từng request có thể đóng góp một kết quả riêng vào thống kê circuit breaker. Tham số `16` giới hạn số inner publisher được xử lý đồng thời trong một lần áp dụng `flatMap`; nó không phải cấu hình bulkhead toàn cục và nhiều subscription đến `lookupAll` vẫn có thể làm tổng số request đồng thời tăng lên.

Nếu muốn xử lý tuần tự, có thể dùng `concatMap` thay cho `flatMap`. Nếu cần giới hạn đồng thời trên nhiều request và nhiều subscriber, hãy xem xét Bulkhead hoặc giới hạn tải ở tầng phù hợp. Circuit breaker và giới hạn đồng thời giải quyết hai vấn đề khác nhau.

## 5. Chuyển Flux thành một kết quả Mono

API reactive của Spring Cloud CircuitBreaker thường làm việc với `Mono<T>` cho một lời gọi reactive. Nếu một thao tác phụ thuộc trả về `Flux<T>` hữu hạn và nghiệp vụ cần toàn bộ kết quả như một đơn vị, có thể gom luồng thành `Mono<List<T>>` bằng `collectList()` rồi bọc `Mono` đó:

```java
import java.util.Collections;
import java.util.List;

import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class InventoryBatchService {
    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryBatchService(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public Mono<List<StockUpdate>> loadBatch(String warehouseId) {
        Mono<List<StockUpdate>> batch = inventoryClient.streamUpdates(warehouseId)
            .collectList();

        return circuitBreakerFactory.create("inventory-batch").run(
            batch,
            error -> Mono.just(Collections.emptyList())
        );
    }
}
```

Với cách này, toàn bộ luồng hữu hạn được gom thành một danh sách và circuit breaker bảo vệ một thao tác lấy batch. Nếu nguồn phát lỗi sau một số phần tử, `collectList()` phát lỗi thay vì trả danh sách từng phần; fallback được gọi cho lần thực thi đó. Cách gom này phù hợp khi số phần tử có giới hạn và nghiệp vụ cần kết quả tổng thể.

Không nên dùng `collectList()` cho một luồng không giới hạn hoặc rất lớn. Publisher chỉ tạo danh sách khi hoàn tất và danh sách phải giữ các phần tử trong bộ nhớ. Với luồng liên tục, hãy chọn ranh giới bảo vệ khác, chẳng hạn từng request lấy batch hữu hạn hoặc từng thao tác độc lập.

## 6. Cold Flux, nhiều subscription và số lần thực thi

Nhiều publisher trong Reactor là cold: dữ liệu và thao tác nguồn chỉ được thực hiện khi có subscriber. Mỗi lần subscribe vào cold publisher thường tạo một lần thực thi nguồn mới.

```java
Flux<StockUpdate> coldUpdates = Flux.defer(() ->
    inventoryClient.fetchCurrentUpdates()
);

Flux<StockUpdate> protectedUpdates = coldUpdates
    .transform(CircuitBreakerOperator.of(inventoryStreamCircuitBreaker));
```

Nếu hai thành phần độc lập subscribe vào `protectedUpdates`, nguồn cold có thể được gọi hai lần và circuit breaker có thể ghi nhận hai lần thực thi. Chỉ tạo biến `Flux` chưa đồng nghĩa request đã được gửi đi; request bắt đầu khi có subscription.

Điều này cũng có nghĩa một retry ở tầng reactive có thể tạo subscription mới. Nếu retry operator nằm ngoài circuit breaker, mỗi lần thử có thể đi qua circuit breaker và được thống kê như một lần thực thi. Cần tính đến hành vi đó khi thiết kế retry, cửa sổ trượt và ngưỡng lỗi.

## 7. Hot, share và cache làm thay đổi ranh giới thực thi

Với publisher hot hoặc publisher được chia sẻ, số subscriber ở phía downstream không nhất thiết bằng số lần nguồn upstream được thực thi. Các toán tử như `share()`, `publish().refCount()` và `cache()` có thể chia sẻ hoặc lưu kết quả nguồn.

Vị trí đặt circuit breaker so với các toán tử này quyết định nó đang đo nguồn upstream hay các lần đăng ký downstream:

```java
// Circuit breaker nằm trước share: bảo vệ lần thực thi nguồn được chia sẻ.
Flux<StockUpdate> sharedProtectedSource = inventoryClient.streamUpdates("SKU-1")
    .transform(CircuitBreakerOperator.of(inventoryStreamCircuitBreaker))
    .share();

// Circuit breaker nằm sau share: mỗi downstream subscription đi qua operator.
Flux<StockUpdate> protectedSharedView = inventoryClient.streamUpdates("SKU-1")
    .share()
    .transform(CircuitBreakerOperator.of(inventoryStreamCircuitBreaker));
```

Trong ví dụ thứ nhất, `share()` chia sẻ publisher đã được bảo vệ. Nguồn được chia sẻ thường có một upstream subscription trong vòng đời chia sẻ, vì vậy circuit breaker quan sát lần thực thi upstream đó. Trong ví dụ thứ hai, operator nằm sau `share()`: mỗi downstream subscriber có thể tạo một subscription riêng qua circuit breaker dù nguồn đã được chia sẻ. Khi đó số lần circuit breaker ghi nhận có thể lớn hơn số lần nguồn thực sự gọi dịch vụ.

`cache()` còn có thể phát lại dữ liệu đã lưu mà không gọi lại dịch vụ phụ thuộc. Nếu circuit breaker đặt sau cache, các subscriber đọc dữ liệu cache vẫn có thể được thống kê như các subscription qua circuit breaker, dù không có request mới đến dịch vụ. Nếu mục tiêu là đo lỗi và độ trễ của lời gọi mạng, hãy đặt ranh giới circuit breaker quanh thao tác mạng thực sự và cân nhắc vị trí cache.

Không có một vị trí duy nhất đúng cho mọi ứng dụng. Hãy xác định muốn bảo vệ và đo lường nguồn dữ liệu, luồng đã chia sẻ hay từng subscriber trước khi chọn thứ tự các toán tử.

## 8. Lỗi giữa luồng và vị trí của fallback

Một `Flux` có thể phát một số phần tử rồi mới phát lỗi. Circuit breaker bao quanh toàn bộ publisher nhận biết lỗi ở tín hiệu kết thúc và có thể ghi nhận một lần thực thi thất bại. Các phần tử đã được phát trước đó không bị thu hồi.

Với Resilience4j Reactor operator, có thể đặt xử lý fallback ở phía downstream của circuit breaker:

```java
Flux<StockUpdate> result = inventoryClient.streamUpdates("SKU-1")
    .transform(CircuitBreakerOperator.of(inventoryStreamCircuitBreaker))
    .onErrorResume(error -> fallbackUpdates("SKU-1", error));
```

Trong thứ tự này, circuit breaker nhìn thấy `onError` trước khi `onErrorResume` chuyển lỗi thành luồng fallback. Nó có thể ghi nhận failure, còn subscriber nhận dữ liệu fallback theo chính sách ứng dụng.

Nếu xử lý lỗi trước khi đưa publisher vào circuit breaker:

```java
Flux<StockUpdate> result = inventoryClient.streamUpdates("SKU-1")
    .onErrorResume(error -> fallbackUpdates("SKU-1", error))
    .transform(CircuitBreakerOperator.of(inventoryStreamCircuitBreaker));
```

thì circuit breaker có thể chỉ nhìn thấy luồng fallback kết thúc bình thường và ghi nhận success. Điều này làm sai lệch failure rate nếu mục tiêu là thống kê lỗi gốc của dịch vụ phụ thuộc. Hãy đặt fallback sau circuit breaker khi muốn circuit breaker ghi nhận lỗi nguồn trước khi ứng dụng phục hồi luồng.

Fallback cho `Flux` cần trả về `Publisher` tương thích và phải cân nhắc các phần tử đã phát trước khi lỗi. Ví dụ, nối thêm dữ liệu dự phòng sau một phần luồng có thể tạo ra tập kết quả trộn giữa dữ liệu thật và dữ liệu fallback. Với nghiệp vụ cần tính nhất quán toàn bộ batch, có thể gom thành `Mono<List<T>>` để chỉ phát kết quả sau khi hoàn tất thành công.

## 9. Luồng dài hạn và cancellation

Circuit breaker truyền thống phù hợp nhất với thao tác có thời điểm bắt đầu và kết thúc rõ ràng. Một `Flux` hữu hạn thường có tín hiệu `onComplete` hoặc `onError`, vì vậy operator có thể ghi nhận kết quả cuối cùng.

Một `Flux` dài hạn hoặc không bao giờ hoàn tất, chẳng hạn luồng sự kiện WebSocket, Kafka hoặc cập nhật liên tục, không tạo ra kết quả thành công/thất bại theo từng phần tử khi circuit breaker bao quanh toàn bộ stream. Nếu luồng tồn tại hàng giờ, circuit breaker có thể giữ lần thực thi ở trạng thái đang diễn ra trong phần lớn thời gian đó; failure rate không phản ánh từng sự kiện riêng lẻ.

Khi subscriber hủy subscription, đó là tín hiệu `cancel`, không phải `onComplete` hay `onError`. Cách operator giải phóng permission và ghi nhận cancellation có thể khác theo phiên bản thư viện. Không nên giả định cancellation là success hoặc failure. Hãy kiểm thử hành vi hủy với đúng phiên bản Resilience4j Reactor đang sử dụng.

Với stream dài hạn, cân nhắc:

- Bảo vệ thao tác thiết lập kết nối hoặc mở stream như một thao tác riêng.
- Dùng timeout, heartbeat và reconnect policy phù hợp với giao thức streaming.
- Bảo vệ từng request hoặc batch hữu hạn được gửi qua stream nếu đó mới là đơn vị nghiệp vụ cần đo.
- Theo dõi số lần kết nối lỗi, số lần reconnect, độ trễ xử lý và số sự kiện lỗi bằng metrics riêng.

Không nên dùng circuit breaker quanh một stream vô hạn rồi diễn giải số lần mở mạch như tỷ lệ lỗi của từng message.

## 10. Kiểm thử số subscription và số kết quả

Có thể dùng `Flux.defer` để đếm số lần nguồn được subscribe và `StepVerifier` để xác minh số phần tử phát ra. Ví dụ với Resilience4j Reactor operator:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.reactor.circuitbreaker.operator.CircuitBreakerOperator;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class FluxCircuitBreakerTest {

    @Test
    void countsOneExecutionForEachSubscriptionNotEachElement() {
        CircuitBreaker circuitBreaker = CircuitBreaker.ofDefaults("updates");
        AtomicInteger subscriptions = new AtomicInteger();

        Flux<Integer> source = Flux.defer(() -> {
            subscriptions.incrementAndGet();
            return Flux.just(10, 20, 30, 40);
        });

        Flux<Integer> protectedFlux = source
            .transform(CircuitBreakerOperator.of(circuitBreaker));

        StepVerifier.create(protectedFlux)
            .expectNext(10, 20, 30, 40)
            .verifyComplete();

        StepVerifier.create(protectedFlux)
            .expectNext(10, 20, 30, 40)
            .verifyComplete();

        assertEquals(2, subscriptions.get());
        assertEquals(2, circuitBreaker.getMetrics().getNumberOfSuccessfulCalls());
    }
}
```

Nguồn phát bốn phần tử trong mỗi subscription, nhưng sau hai lần subscribe, circuit breaker ghi nhận hai lần thực thi thành công. Kết quả này chứng minh số `onNext` không phải số call được ghi nhận khi operator bao quanh toàn bộ `Flux`.

Có thể bổ sung các ca kiểm thử sau:

1. Một subscription phát nhiều phần tử rồi hoàn tất: xác nhận một success.
2. Một subscription phát vài phần tử rồi `onError`: xác nhận một failure nếu exception được ghi nhận.
3. Hai subscription vào cold publisher: xác nhận hai lần thực thi nguồn.
4. Nhiều subscriber vào publisher đã `share()` hoặc `cache()`: xác nhận vị trí circuit breaker quyết định số subscription được thống kê và số lần gọi nguồn.
5. Hủy subscription trước khi publisher kết thúc: xác nhận hành vi permission và metrics theo phiên bản đang dùng.
6. Một `Flux` đầu vào gọi nhiều inner `Mono`: xác nhận mỗi lời gọi con có kết quả circuit breaker riêng.

## 11. Chọn ranh giới circuit breaker theo đơn vị nghiệp vụ

Trước khi đặt operator, hãy trả lời câu hỏi: một lần thất bại mà hệ thống cần thống kê là gì? Có thể là một lần mở kết nối stream, một lần lấy batch, một lần tra cứu SKU hoặc một lần gửi command. Đơn vị đó nên tương ứng với một thao tác phụ thuộc có thể thành công hoặc thất bại độc lập.

| Mục tiêu bảo vệ | Cách tổ chức phù hợp |
|---|---|
| Một request lấy toàn bộ danh sách cập nhật hữu hạn | Bọc toàn bộ `Flux` hoặc gom thành `Mono<List<T>>` nếu cần kết quả batch nguyên vẹn. |
| Mỗi SKU tạo một request tra cứu riêng | Đặt circuit breaker trong `flatMap`/`concatMap` quanh từng inner `Mono`. |
| Nhiều subscriber cùng đọc một nguồn đã chia sẻ | Xác định muốn đo upstream một lần hay từng downstream subscriber rồi đặt operator trước/sau `share` phù hợp. |
| Stream vô hạn hoặc kết nối lâu dài | Bảo vệ thao tác kết nối và reconnect; dùng metrics riêng cho từng sự kiện hoặc request. |
| Publisher phát một phần dữ liệu rồi lỗi | Đặt circuit breaker trước fallback nếu cần ghi nhận lỗi nguồn; quyết định rõ có chấp nhận dữ liệu một phần không. |

Khi triển khai Spring Cloud CircuitBreaker, reactive factory thường bảo vệ một `Mono` đại diện cho một lời gọi. Với luồng `Flux`, có thể dùng Reactor operator trực tiếp của Resilience4j hoặc chuyển một luồng hữu hạn thành một kết quả `Mono` nếu toàn bộ luồng là một đơn vị nghiệp vụ. Khi mỗi phần tử đại diện cho một request độc lập, hãy bảo vệ từng request con. Việc xác định đúng ranh giới subscription giúp failure rate, số lần thăm dò và metrics phản ánh đúng những lời gọi mà hệ thống thực sự muốn bảo vệ.
