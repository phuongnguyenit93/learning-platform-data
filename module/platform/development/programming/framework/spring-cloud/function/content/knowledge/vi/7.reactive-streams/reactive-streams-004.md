# @PollableBean, splittable và trách nhiệm của cơ chế polling bên ngoài

## 1. Vì sao Supplier<Flux<T>> hữu hạn cần @PollableBean?

Trong Spring Cloud Function, `Supplier<T>` là một hàm không có đầu vào, trả kết quả mỗi khi được gọi bằng `get()`. Nếu kết quả là `Flux<T>` của Reactor, ta có **một publisher** có thể phát nhiều phần tử. Đây là cách thuận tiện để tạo nguồn sự kiện, nhưng có một câu hỏi vận hành quan trọng: **ai quyết định khi nào gọi lại `get()` sau khi luồng đã kết thúc?**

Hãy xem hai nguồn:

~~~java
Supplier<Flux<String>> liveTicks =
    () -> Flux.interval(Duration.ofSeconds(1))
              .map(String::valueOf);

Supplier<Flux<String>> pendingIds =
    () -> Flux.just("ORD-101", "ORD-102");
~~~

- `liveTicks.get()` tạo một publisher có khả năng phát liên tục. Trong adapter nguồn reactive, chỉ cần kích hoạt supplier và subscribe vào publisher; từng tick sẽ phát theo thời gian.
- `pendingIds.get()` tạo một publisher hữu hạn, phát hai giá trị rồi `onComplete`. Nếu chỉ gọi `get()` một lần thì không có lô thứ hai; muốn đọc lại, **cần cơ chế chủ động gọi lại supplier**.

Khi tích hợp với Spring Cloud Stream, framework thường xử lý reactive supplier như một nguồn luồng dài hạn: gọi `get()` để lấy `Flux` rồi đăng ký tiêu thụ. Vì vậy, một nguồn trả `Flux.just(...)` hữu hạn **không tự động được gọi lại liên tục** chỉ nhờ kiểu `Supplier<Flux<T>>`.

`@PollableBean` giải quyết vấn đề diễn đạt *ý định*: **đây là bean supplier phản ứng có kết quả hữu hạn và cần được poll lại**. Nhưng bản thân annotation này **không cung cấp scheduler hoặc thuật toán polling**. Spring Cloud Function định nghĩa annotation, còn framework sử dụng function, chẳng hạn Spring Cloud Stream, phải nhận biết annotation và thực hiện việc gọi theo lịch.

Bài này tập trung vào ba trách nhiệm dễ nhầm lẫn:

1. **`@PollableBean`**: đánh dấu cách một reactive supplier nên được tiêu thụ.
2. **`splittable`**: đánh dấu có tách từng phần tử của kết quả thành message riêng hay không.
3. **Poller bên ngoài**: quyết định lịch kích hoạt, số lần gọi, vòng đời, lỗi và cách gửi kết quả.

Nhờ phân tách các trách nhiệm, logic nghiệp vụ vẫn có thể đóng gói bằng `Supplier`, `Function`, `Consumer` và tra cứu qua `FunctionCatalog`. Cùng function có thể được adapter HTTP, sự kiện hoặc serverless sử dụng, nhưng cơ chế kích hoạt không nhất thiết giống nhau.

## 2. Phân biệt get(), subscribe() và onNext()

Một lần poll không đồng nghĩa với một phần tử. Với một supplier trả `Flux` hữu hạn, có ba mốc:

| Mốc | Chủ thể thực hiện | Ý nghĩa |
| --- | --- | --- |
| `get()` | Caller hoặc adapter/poller | Yêu cầu supplier tạo một publisher cho lần gọi hiện tại |
| `subscribe()` | Caller, framework hoặc adapter | Đăng ký nhận dữ liệu từ publisher |
| `onNext(T)` | Publisher khi có dữ liệu | Phát một phần tử; downstream có thể chuyển thành một message |
| `onComplete()` | Publisher hữu hạn | Báo rằng subscription hiện tại đã kết thúc bình thường |
| `cancel()` | Subscriber/adapter | Ngừng tiêu thụ publisher; cần thiết để giải phóng tài nguyên của nguồn dài hạn |

Ví dụ:

~~~java
AtomicInteger getCalls = new AtomicInteger();
AtomicInteger subscriptions = new AtomicInteger();
AtomicInteger items = new AtomicInteger();

Supplier<Flux<String>> source = () -> {
    getCalls.incrementAndGet();
    return Flux.just("A", "B", "C")
        .doOnSubscribe(s -> subscriptions.incrementAndGet())
        .doOnNext(value -> items.incrementAndGet());
};

Flux<String> result = source.get();
// getCalls=1; subscriptions=0; items=0

result.subscribe();
// getCalls=1; subscriptions=1; items=3
~~~

Đây là ví dụ Reactor thuần với một subscriber chủ động. Trong ứng dụng Spring Cloud Stream, adapter thường là bên quản lý subscription; mã trong supplier chỉ cần trả `Flux`. Nếu một poller gọi `get()` lại để lấy lô mới, `getCalls` tăng thêm một. Ngược lại, subscribe lại *cùng* publisher cold có thể phát lại ba phần tử mà **không gọi lại** `get()`.

Cần lưu ý rằng không phải mọi publisher đều cold. Nguồn hot có thể bỏ lỡ phần tử khi subscriber đến muộn; nguồn I/O bên ngoài có quy tắc retry/acknowledgment riêng.

~~~mermaid
flowchart LR
    TIMER["Poller / external trigger"] -->|kích hoạt| GET["Supplier.get()"]
    GET --> FLUX["Flux<T> hữu hạn"]
    FLUX -->|subscribe| SUB["Adapter"]
    SUB -->|onNext A| M1["Message A"]
    SUB -->|onNext B| M2["Message B"]
    FLUX -->|onComplete| DONE["Lần poll kết thúc"]
    DONE -.->|lịch sau: get() mới| TIMER
~~~

Đường mũi tên cuối là **trách nhiệm của poller**, không phải chức năng tự có của Reactor hoặc `@PollableBean`.

## 3. @PollableBean thực sự là gì?

Spring Cloud Function cung cấp annotation:

~~~java
import org.springframework.cloud.function.context.PollableBean;
~~~

Nó có thể dùng ở vị trí khai báo bean tương tự `@Bean`:

~~~java
@PollableBean
public Supplier<Flux<String>> recentOrders() {
    return () -> Flux.just("ORD-101", "ORD-102");
}
~~~

Với trường hợp này, `@PollableBean` đánh dấu phương thức tạo bean supplier; không cần gắn thêm `@Bean` ở cùng phương thức chỉ để khai báo bean lần thứ hai.

**Ranh giới cốt lõi:** `@PollableBean` là *marker annotation*. Spring Cloud Function **không tự đặt timer, tạo thread, lên lịch gọi `get()` hay gửi message** chỉ vì thấy annotation. Những chức năng đó phải được triển khai bởi framework sử dụng nó.

Trong Spring Cloud Stream, annotation này báo rằng supplier reactive — vốn thường được xem là nguồn liên tục — cần được gọi lại theo cơ chế polling. Lần gọi tạo một publisher hữu hạn; khi subscriber tiêu thụ xong, lần gọi tiếp theo sẽ do trigger/poller thực hiện.

### 3.1. Tại sao @Bean và @PollableBean có hành vi khác?

~~~java
@Bean
Supplier<Flux<String>> continuousSource() {
    return () -> Flux.interval(Duration.ofSeconds(1))
        .map(String::valueOf);
}

@PollableBean
Supplier<Flux<String>> finiteSource() {
    return () -> Flux.just("A", "B");
}
~~~

| Khía cạnh | `@Bean Supplier<Flux<T>>` | `@PollableBean Supplier<Flux<T>>` |
| --- | --- | --- |
| Vai trò khai báo | Tạo functional bean thường | Tạo functional bean và đánh dấu cần polling |
| Hợp đồng Java | `Supplier.get()` trả `Flux<T>` | Giống hoàn toàn |
| Giả định thường gặp ở Spring Cloud Stream | Lấy một publisher để tiêu thụ như nguồn reactive liên tục | Poll lại reactive supplier để thu các lô hữu hạn |
| Có lịch chạy độc lập chỉ nhờ annotation? | Không | Không |
| Có tự bảo đảm exactly-once? | Không | Không |
| Có luôn phát message riêng cho mỗi phần tử? | Phụ thuộc adapter và kiểu dữ liệu | Tùy `splittable` và adapter |

Một supplier trả `Flux.never()` sẽ không phát phần tử hoặc hoàn tất; dù gắn `@PollableBean`, nó không trở thành nguồn dữ liệu hữu hạn có kết quả. Ngược lại, `@Bean Supplier<Flux<T>>` có thể trả publisher hữu hạn — nhưng nếu adapter chỉ kích hoạt một lần, nguồn đó sẽ kết thúc mà không được poll lại.

### 3.2. Cái gì không nằm trong hợp đồng annotation?

`@PollableBean` không tự quy định:

- Chu kỳ poll là 1 giây, 5 giây hay theo cron.
- Số phần tử tối đa của mỗi `Flux`.
- Có poll chồng lên nhau hay không khi một lần chạy chậm.
- Có tự retry khi truy vấn lỗi hoặc binder gửi thất bại hay không.
- Điểm nào được coi là “đã gửi”, “đã xác nhận” hoặc “đã commit”.
- Tác vụ nào sẽ tiếp tục khi ứng dụng restart.

Các quyết định đó phải được cấu hình và kiểm chứng ở poller/adapter cùng hệ thống lưu trữ và nhận message.

## 4. Ví dụ Spring Cloud Function: phát lô hữu hạn qua @PollableBean

Giả sử mỗi lần poll cần phát hai bản ghi thay đổi tồn kho. Ví dụ này độc lập database và tạo dữ liệu có mã lô tăng dần để người học dễ nhận ra **mỗi lần `get()` là một lô mới**.

~~~java
package demo.function;

import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Supplier;

import org.springframework.cloud.function.context.PollableBean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;

@Configuration
public class InventorySuppliers {

    private final AtomicLong batchCounter = new AtomicLong();

    public record StockChange(
        long batchId,
        String sku,
        int quantityDelta
    ) {}

    @PollableBean(splittable = true)
    public Supplier<Flux<StockChange>> stockChanges() {
        return () -> {
            long batchId = batchCounter.incrementAndGet();
            return Flux.just(
                new StockChange(batchId, "SKU-A", 5),
                new StockChange(batchId, "SKU-B", -2)
            );
        };
    }
}
~~~

Nếu poller gọi supplier ba lần, xét từng publisher được subscribe và hoàn tất:

| Lần gọi `get()` | Publisher phát | Số phần tử |
| ---: | --- | ---: |
| 1 | `StockChange(1, "SKU-A", 5)`, `StockChange(1, "SKU-B", -2)` | 2 |
| 2 | `StockChange(2, "SKU-A", 5)`, `StockChange(2, "SKU-B", -2)` | 2 |
| 3 | `StockChange(3, "SKU-A", 5)`, `StockChange(3, "SKU-B", -2)` | 2 |

Đây là ví dụ tạo dữ liệu *minh họa*. Trong ứng dụng thực tế, lô mới thường đến từ repository hoặc API và **không nên** tạo dữ liệu nghiệp vụ bằng bộ đếm trong bộ nhớ để mô phỏng độ bền sau restart.

Cách viết trên cũng cho thấy `@PollableBean(splittable = true)` không đổi kiểu trả về: `stockChanges().get()` vẫn là `Flux<StockChange>`. Việc chuyển hai phần tử thành hai message là việc của postprocessor/adapter hiểu annotation.

### 4.1. Lấy lô từ một repository reactive

Một ứng dụng có thể thay nguồn tạo tay bằng:

~~~java
@PollableBean
public Supplier<Flux<OrderEvent>> pendingOrders() {
    return () -> orderRepository.findPending();
}
~~~

Đây là phác thảo: `orderRepository` cần được inject, `OrderEvent` là kiểu nghiệp vụ và `findPending()` phải có hợp đồng trả `Flux<OrderEvent>`. Khi `get()` trả publisher mới, truy vấn reactive thường thực hiện lúc có subscription.

Rủi ro lớn nhất: nếu `findPending()` luôn đọc lại các đơn chưa thay đổi trạng thái, **cùng đơn hàng có thể được phát ở nhiều lần poll**. Cần một chiến lược như outbox, đánh dấu đã xử lý, checkpoint, claim bản ghi hoặc idempotency tại consumer; chỉ thêm `@PollableBean` không ngăn trùng.

Nếu repository là blocking (JDBC API đồng bộ), sử dụng Reactor wrapper không tự biến nó thành non-blocking. Ưu tiên nguồn reactive, hoặc cô lập blocking bằng scheduler phù hợp và giới hạn mức song song.

## 5. splittable: tách các phần tử hay giữ publisher nguyên dạng?

`@PollableBean` có thuộc tính `splittable`, mặc định **`true`** theo tài liệu Spring Cloud Stream. Thuộc tính này gửi tín hiệu cho các postprocessor của framework về cách xử lý publisher do supplier tạo ra.

### 5.1. splittable = true: tách thành các message riêng

~~~java
@PollableBean(splittable = true)
Supplier<Flux<String>> codes() {
    return () -> Flux.just("A", "B", "C");
}
~~~

Với adapter Spring Cloud Stream hỗ trợ xử lý split, một lần poll trả `Flux<String>` có ba phần tử; adapter có thể gửi thành **ba message** có payload riêng lần lượt là `"A"`, `"B"`, `"C"`.

~~~mermaid
flowchart LR
    P["Một lần poll"] --> F["Flux: A, B, C"]
    F --> SPLIT["splittable = true"]
    SPLIT --> A["Message(A)"]
    SPLIT --> B["Message(B)"]
    SPLIT --> C["Message(C)"]
~~~

Giá trị `splittable = true` **không** có nghĩa poller sẽ gọi `get()` ba lần. Nó mô tả cách **một kết quả Flux** được chuyển tiếp sau khi có dữ liệu.

### 5.2. splittable = false: không yêu cầu chia nhỏ

~~~java
@PollableBean(splittable = false)
Supplier<Flux<String>> originalFlux() {
    return () -> Flux.just("A", "B", "C");
}
~~~

Ở đây annotation báo cho postprocessor **không thực hiện bước split Flux thành từng message theo mặc định**. Kết quả reactive được giữ nguyên ở ranh giới xử lý đó.

**Không suy diễn rằng mọi binder sẽ tự serialize một đối tượng `Flux` thành một JSON array hoặc tự gửi một message chứa danh sách `["A","B","C"]`.** Với `splittable = false`, việc đưa publisher vào pipeline, định dạng payload và nơi subscribe tiếp phụ thuộc adapter và downstream. Nếu không có thành phần hiểu publisher, có thể không đạt hành vi mong muốn.

### 5.3. Nếu nghiệp vụ yêu cầu một message chứa cả lô?

Hãy tạo **kiểu batch rõ ràng** và làm việc với hợp đồng message cụ thể, ví dụ:

~~~java
public record StockBatch(
    String batchId,
    java.util.List<String> skus
) {}

@Bean
public Supplier<StockBatch> batchAsOnePayload() {
    return () -> new StockBatch(
        java.util.UUID.randomUUID().toString(),
        java.util.List.of("SKU-A", "SKU-B")
    );
}
~~~

Đây là một **supplier imperative** trả một đối tượng `StockBatch` trong mỗi lần `get()`. Khi dùng Spring Cloud Stream poller, adapter có thể chuyển một `StockBatch` thành một payload message theo cấu hình serializer. Kiểu rõ ràng giúp downstream biết đây là một lô; việc poll theo lịch và gửi message vẫn thuộc framework tích hợp.

Nếu muốn API reactive cho một batch, `Supplier<Mono<StockBatch>>` cũng là một lựa chọn về hợp đồng dữ liệu. Cần kiểm tra khả năng xử lý publisher và lập lịch của adapter cụ thể.

### 5.4. Bảng chọn splittable

| Ý định | Thiết kế nên cân nhắc | Điều cần kiểm chứng |
| --- | --- | --- |
| Mỗi `T` là một sự kiện độc lập | `@PollableBean(splittable = true) Supplier<Flux<T>>` | Số message đầu ra, header, thứ tự, lỗi |
| Downstream nhận và xử lý nguyên publisher | `@PollableBean(splittable = false)` trong adapter hỗ trợ | Ai subscribe, publisher truyền qua đâu, serialization |
| Một message chứa danh sách item | Payload kiểu batch/DTO rõ ràng | Một invocation tương ứng bao nhiêu message, content type |
| Nguồn stream liên tục, mỗi phần tử phát theo thời gian | Thường dùng `@Bean Supplier<Flux<T>>` | Vòng đời subscription và backpressure |

Lựa chọn `splittable` là lựa chọn về **đơn vị xử lý output**, không phải về lịch poll hoặc số lần gọi supplier.

## 6. Phần việc của Spring Cloud Function và Spring Cloud Stream

Phân định trách nhiệm giúp tránh kỳ vọng sai khi chạy mã Java thuần:

| Thành phần | Trách nhiệm chính |
| --- | --- |
| **Spring Cloud Function Core** | Định nghĩa/đăng ký function bean, `FunctionCatalog`, wrapper chuyển đổi kiểu, composition, cung cấp `@PollableBean` như marker |
| **Spring Cloud Stream** | Phát hiện/bind supplier, tổ chức trigger/polling, tiếp nhận output, đưa message tới binder và đích cấu hình |
| **Spring Integration poller** | Cung cấp cơ chế trigger và cấu hình chu kỳ, số lượt nhận/nhịp theo hợp đồng |
| **Binder (Kafka/RabbitMQ/...)** | Kết nối transport, gửi message, serialization và các tùy chọn delivery phụ thuộc binder |
| **Hệ thống dữ liệu** | Lưu trạng thái, xác định bản ghi mới, xác nhận đã đọc/đã phát, xử lý lỗi và trùng |
| **Ứng dụng** | Chính sách idempotency, phân lô, transaction, retry, giám sát và mục tiêu vận hành |

Khi ứng dụng chỉ có Spring Cloud Function Core, các câu lệnh sau **không tạo poller**:

~~~java
@PollableBean
Supplier<Flux<String>> changes() {
    return () -> Flux.just("A", "B");
}
~~~

Để poll, bên gọi vẫn phải dùng `FunctionCatalog` hoặc bean và tự lập lịch `get()`/subscription. Trong môi trường có Spring Cloud Stream, framework có cơ chế poller riêng để dùng marker đó. Đây là khác biệt quan trọng nhất của bài.

## 7. Cấu hình một pollable supplier qua Spring Cloud Stream

Giả sử ứng dụng đã thêm Spring Cloud Stream và binder phù hợp (chẳng hạn Kafka hoặc RabbitMQ), có bean `stockChanges` như mục 4. Cấu hình chọn chức năng và đích output:

~~~properties
spring.cloud.function.definition=stockChanges
spring.cloud.stream.bindings.stockChanges-out-0.destination=stock-updates
~~~

`stockChanges-out-0` là tên output binding theo quy ước chức năng cho bean `stockChanges`. `stock-updates` là tên đích logic; cần cấu hình binder, broker và serializer riêng theo môi trường.

### 7.1. Cấu hình polling mặc định ở Spring Cloud Stream

Trong tài liệu Spring Cloud Stream 5.1, các thuộc tính poller được công bố với prefix `spring.integration.poller.`. Ví dụ:

~~~properties
# Khoảng nghỉ cố định giữa các lần kích hoạt, tính bằng mili giây
spring.integration.poller.fixed-delay=5000

# Số lượt nhận tối đa cho một polling event
spring.integration.poller.maxMessagesPerPoll=1
~~~

Ở phiên bản tài liệu này, giá trị mặc định được nêu là `fixedDelay = 1000` mili giây và `maxMessagesPerPoll = 1`. Có thể cấu hình `cron`, `initialDelay` và `timeUnit` khi cần.

**Chú ý sự khác biệt của phiên bản:** tài liệu Spring Cloud Stream đời cũ có thể dùng prefix `spring.cloud.stream.poller.`. Hãy căn cứ chính xác BOM/phiên bản dependency đang triển khai, tránh chép thuộc tính cũ rồi tưởng đã thay đổi lịch. Phần trên bám theo cách mô tả của tài liệu 5.1.

`maxMessagesPerPoll` không nên hiểu đơn giản là “một `Flux` chỉ được phát đúng một phần tử”. Trong kiểu reactive pollable, một lời gọi `get()` có thể tạo một publisher hữu hạn phát nhiều `T`; việc split và gửi các phần tử thuộc pipeline xử lý output.

### 7.2. Poller riêng cho một output binding

Khi nhiều supplier cần nhịp khác nhau, có thể dùng cấu hình poller theo binding, ví dụ:

~~~properties
spring.cloud.stream.bindings.stockChanges-out-0.producer.poller.fixed-delay=2000
~~~

Đây là cách tài liệu Spring Cloud Stream mô tả cấu hình riêng cho output binding thay vì sửa poller mặc định toàn ứng dụng. Trong dự án cụ thể cần xác minh property có hiệu lực theo phiên bản/binder đang dùng.

### 7.3. Fixed delay, cron và vấn đề tác vụ chậm

Một cấu hình `fixed-delay` diễn đạt ý định kích hoạt định kỳ, **không** là bằng chứng rằng mọi subscription đã hoàn tất hoặc broker đã xác nhận trước khi đợt kế tiếp bắt đầu.

Nếu truy vấn mất 15 giây nhưng nhịp poll là 5 giây, cần xác định framework có chờ tác vụ hay chỉ chờ bước khởi tạo publisher. Với API bất đồng bộ, hai lượt có thể cùng tồn tại tùy scheduler/adapter. Muốn đảm bảo không poll chồng hoặc không phát trùng, hãy thiết kế một trong các cơ chế sau và kiểm chứng:

- Lock/lease trên nguồn dữ liệu hoặc giới hạn concurrency.
- Claim bản ghi có thời hạn và trạng thái xử lý.
- Phân trang theo checkpoint và đánh dấu đã công bố.
- Một luồng polling tự quản lý thứ tự bằng `concatMap` nếu chọn kiến trúc không dùng `@PollableBean`.

Đừng xem chu kỳ poll là một transaction hoặc một đơn vị acknowledgment.

## 8. Nguồn phát liên tục không cần @PollableBean như thế nào?

Nếu bản thân publisher đã có khả năng phát lâu dài, thường có thể dùng supplier reactive thông thường:

~~~java
@Bean
Supplier<Flux<Long>> ticker() {
    return () -> Flux.interval(Duration.ofSeconds(1));
}
~~~

Trong tích hợp Spring Cloud Stream theo mô hình reactive supplier, một lần lấy `Flux` đủ để bắt đầu subscription dài hạn. Các `onNext` xuất hiện theo nhịp của nguồn. Không cần poller gọi lại `get()` mỗi giây để tạo tick.

Ngược lại, nguồn hữu hạn:

~~~java
@PollableBean
Supplier<Flux<String>> snapshot() {
    return () -> Flux.just("A", "B");
}
~~~

cần poller bên ngoài để gọi lại nếu ứng dụng muốn có các snapshot tiếp theo.

### 8.1. Hai cách thiết kế polling định kỳ, đừng kích hoạt cả hai vô tình

**Cách A: framework gọi lại supplier hữu hạn**

~~~java
@PollableBean
Supplier<Flux<String>> finiteChanges() {
    return () -> readNextFiniteBatch();
}
~~~

`readNextFiniteBatch()` là hàm giả định trả `Flux<String>` hữu hạn; nhịp poll thuộc Spring Cloud Stream hoặc caller.

**Cách B: supplier tự tạo lịch trong Flux liên tục**

~~~java
@Bean
Supplier<Flux<String>> scheduledChanges() {
    return () -> Flux.interval(
            Duration.ZERO,
            Duration.ofSeconds(5)
        )
        .concatMap(tick -> readNextFiniteBatch());
}
~~~

Ở cách B, `Flux.interval` là trigger; `concatMap` đăng ký các lô tuần tự trong một pipeline. Đây là ví dụ thiết kế nguồn reactive liên tục. Nếu đồng thời gắn `@PollableBean` và để external poller gọi lại nguồn `Flux.interval`, có thể tạo **nhiều lịch phát song song**, dẫn đến tải tăng và dữ liệu trùng. Chọn một cơ chế chủ đạo và quy định rõ quyền sở hữu scheduler.

### 8.2. Luồng hữu hạn không có nghĩa dữ liệu luôn thay đổi

~~~java
@PollableBean
Supplier<Flux<String>> repetitive() {
    return () -> Flux.just("A", "B");
}
~~~

Cứ mỗi lần `get()` được gọi, `A` và `B` lại xuất hiện. Marker không biết đây là dữ liệu cũ. Do đó, truy vấn nghiệp vụ cần có trạng thái/checkpoint và người nhận cần idempotency.

## 9. Lỗi trong một đợt poll và vòng đời subscription

Nếu lần poll tạo `Flux.error(...)`, subscription đó phát `onError` và kết thúc. Không thể mặc định Spring Cloud Stream sẽ âm thầm retry, hay poller tiếp tục theo đúng lịch và giữ nguyên dữ liệu đã gửi; hành vi phụ thuộc binder, adapter và cấu hình.

Ví dụ minh họa một nguồn có thể gặp lỗi:

~~~java
@PollableBean
Supplier<Flux<OrderEvent>> changedOrders() {
    return () -> orderRepository.findChangedSinceLastCheckpoint();
}
~~~

Khi nguồn lỗi sau khi đã phát một số bản ghi:

1. Subscriber có thể đã nhận một số `onNext` trước `onError`.
2. Việc binder đã gửi/xác nhận các message đó hay chưa là một vấn đề riêng.
3. Nếu lần poll khác đọc lại từ checkpoint cũ, các message vừa phát có thể bị lặp.
4. Nếu checkpoint được đẩy lên quá sớm, message chưa gửi thành công có thể bị bỏ sót.

### 9.1. Retry phải đi cùng idempotency

~~~java
return () -> orderRepository.findPending()
    .retryWhen(
        reactor.util.retry.Retry.backoff(
            3, Duration.ofMillis(200)
        )
    );
~~~

Đây là phác thảo một chiến lược retry cho lỗi tạm thời; nó chưa xử lý trọn vẹn việc gửi broker, checkpoint hoặc transaction. Khi upstream được subscribe lại, những phần tử đã phát trước lỗi **có thể phát lại**, nên retry có thể làm xuất hiện message trùng.

Với thao tác có side effect, cần phân biệt lỗi của **truy vấn** và lỗi của **gửi message**. Retry đọc dữ liệu không đồng nghĩa retry được một lần gửi đã thất bại sau khi message được nhận bởi broker.

### 9.2. Đừng dùng Flux.empty() để che giấu lỗi quan trọng

Nếu nguồn trả `Flux.empty()`, subscription hoàn tất mà không có phần tử. Đây là một kết quả hợp lệ khi không có dữ liệu mới. Nhưng nếu một lỗi kết nối bị chuyển vô điều kiện thành `Flux.empty()`, hệ thống giám sát có thể hiểu sai rằng đợt poll thành công nhưng không có công việc.

Nên dùng một trong các chính sách rõ ràng: báo lỗi và alert, retry có giới hạn, chuyển lỗi thành trạng thái nghiệp vụ hoặc bỏ qua chu kỳ khi nghiệp vụ thực sự cho phép. Lỗi phải được ghi nhận và có số liệu theo dõi.

## 10. splittable tác động thế nào tới headers và chuyển đổi thông điệp?

Khi `splittable = true`, mỗi phần tử `T` có thể là một message với payload riêng. Nếu cần metadata từng phần tử, có thể phát `Message<T>`:

~~~java
import java.util.function.Supplier;

import org.springframework.cloud.function.context.PollableBean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import reactor.core.publisher.Flux;

@PollableBean(splittable = true)
public Supplier<Flux<Message<String>>> stockUpdates() {
    return () -> Flux.just("SKU-A", "SKU-B")
        .map(sku -> MessageBuilder.withPayload(sku)
            .setHeader("eventType", "STOCK_UPDATE")
            .setHeader("source", "warehouse-service")
            .build());
}
~~~

Mỗi phần tử là một Spring Messaging `Message<String>` có payload và header. Adapter/binder có thể ánh xạ các header sang transport hoặc chỉ giữ những header được cấu hình cho phép.

Nếu `splittable = false`, không thể giả định metadata của **nhiều** phần tử sẽ tự được tổng hợp thành metadata của **một** message. Khi yêu cầu chuyển cả lô thành một message, hãy định nghĩa batch payload và bộ header tương ứng.

### 10.1. Dùng FunctionCatalog và composition

Logic biến đổi nên tách khỏi logic đọc nguồn:

~~~java
@Bean
Function<Flux<StockChange>, Flux<StockChange>> positiveChanges() {
    return source -> source.filter(change ->
        change.quantityDelta() > 0
    );
}
~~~

Spring Cloud Function cho phép composition như `stockChanges|positiveChanges` khi chữ ký tương thích. Nhưng việc **gắn marker @PollableBean với supplier gốc** và **cách adapter nhận ra metadata sau composition** cần được integration test ở phiên bản đang dùng. Đừng chỉ dựa vào unit test gọi hai hàm Java để kết luận scheduler và binder đã giữ hành vi polling/splitting mong muốn.

Với mô hình xử lý theo message, đôi khi một `Function<StockChange, Result>` được gọi cho từng message thuận tiện hơn một `Function<Flux<StockChange>, Flux<Result>>`. Hãy xác định rõ ranh giới đơn vị công việc của pipeline, nhất là khi dùng split.

## 11. HTTP, sự kiện và serverless: cùng một bean, khác quyền sở hữu trigger

`@PollableBean` không tạo một “lịch chạy toàn cục” dùng chung cho mọi giao thức. Trong Spring Cloud Function, adapter chịu trách nhiệm giải thích cách kích hoạt:

| Môi trường | Đơn vị kích hoạt thông thường | Tác động lên @PollableBean |
| --- | --- | --- |
| Gọi Java trực tiếp / `FunctionCatalog` | Caller chủ động gọi `get()` | Marker không tự gọi; caller phải chủ động lập lịch nếu muốn |
| Spring Cloud Stream | Output binding và poller | Có thể đọc marker để poll lại reactive supplier hữu hạn |
| HTTP adapter | Một HTTP request/invocation | HTTP request thường là trigger; không nên giả định annotation kích hoạt HTTP server theo lịch |
| Serverless adapter | Một invocation do nền tảng kích hoạt | Scheduler/trigger ngoài như EventBridge, cron hoặc event source quyết định nhịp |
| External scheduler + service | Lịch của scheduler hoặc lệnh chạy | Hệ thống ngoài có trách nhiệm kích hoạt/đợi kết quả/điều khiển retry |

Ví dụ, một job serverless mỗi phút gọi hàm có thể lấy một batch hữu hạn rồi kết thúc invocation. Khi đưa cùng logic sang Spring Cloud Stream, poller của Stream có thể đảm nhiệm lịch gọi. Không nên chạy đồng thời cron ngoài **và** poller trong ứng dụng nếu không có quy định rõ ràng về phân vùng hoặc khóa xử lý.

Khi triển khai qua HTTP, một `Flux` có được trả thành JSON array sau khi hoàn tất hay stream từng phần tử còn phụ thuộc web adapter và content negotiation; `splittable` không mặc nhiên cấu hình media type.

## 12. Threading, backpressure và quản lý tài nguyên

Poller có thể chạy trên thread không phải event loop của Reactor. Vì supplier không nhận input, thread kích hoạt do scheduler hoặc framework quyết định; thông tin `ThreadLocal` (ví dụ tracing context) có thể không tự theo qua các biên bất đồng bộ.

Với nguồn blocking, đoạn sau là **cách gọi sai trong pipeline reactive** nếu đang chạy trên thread nhạy cảm:

~~~java
@PollableBean
Supplier<Flux<OrderEvent>> blockingRead() {
    return () -> Flux.fromIterable(
        blockingJdbcRepository.findAllPending()
    );
}
~~~

`blockingJdbcRepository.findAllPending()` chạy ngay khi `get()` được gọi, có thể chặn thread poller. Nếu phải dùng API cũ, có thể cô lập:

~~~java
@PollableBean
Supplier<Flux<OrderEvent>> boundedBlockingRead() {
    return () -> Mono.fromCallable(
            () -> blockingJdbcRepository.findAllPending()
        )
        .subscribeOn(Schedulers.boundedElastic())
        .flatMapMany(Flux::fromIterable);
}
~~~

Đoạn này giả định repository trả `Iterable<OrderEvent>`; các import `Mono`, `Flux` và `Schedulers` phải có trong class. Nó chuyển công việc blocking sang scheduler phù hợp, nhưng **không biến JDBC blocking thành non-blocking**. Vẫn cần timeout, connection pool phù hợp và hạn mức song song.

### 12.1. Backpressure khác với lịch polling

- **Polling** quyết định khi nào gọi `get()` để tạo một batch.
- **Backpressure** điều tiết nhu cầu phần tử của một publisher trong subscription.
- **Binder flow control** quyết định khả năng đẩy message vào broker và cách xử lý khi transport quá tải.

Một luồng phát 100.000 bản ghi trong một lần poll có thể làm hệ thống nặng ngay cả khi poller chỉ chạy mỗi phút. `maxMessagesPerPoll=1` không phải giới hạn mặc định 1 phần tử trong mọi `Flux`. Cần thêm phân trang/batch size, concurrency limit, backpressure và đo lượng dữ liệu thực.

Nếu các phần tử là đơn hàng hoặc thanh toán, không tùy tiện dùng `onBackpressureDrop()` để tránh quá tải. Khi cần không mất dữ liệu, giải pháp thường phải bao gồm nguồn dữ liệu bền vững và cơ chế phân phối/nhận xác nhận.

## 13. Kiểm thử logic supplier và hành vi của poller

Với ví dụ `InventorySuppliers` ở mục 4, đơn vị test logic có thể gọi bean supplier trực tiếp. `StepVerifier` xác nhận mỗi publisher hữu hạn phát hai phần tử và hoàn tất:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.function.Supplier;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class InventorySuppliersTest {

    @Test
    void newGetCreatesNextFiniteBatch() {
        InventorySuppliers config = new InventorySuppliers();
        Supplier<Flux<InventorySuppliers.StockChange>> source =
            config.stockChanges();

        StepVerifier.create(source.get())
            .expectNext(
                new InventorySuppliers.StockChange(1, "SKU-A", 5),
                new InventorySuppliers.StockChange(1, "SKU-B", -2)
            )
            .verifyComplete();

        StepVerifier.create(source.get())
            .expectNext(
                new InventorySuppliers.StockChange(2, "SKU-A", 5),
                new InventorySuppliers.StockChange(2, "SKU-B", -2)
            )
            .verifyComplete();
    }
}
~~~

Test trên chứng minh logic `Supplier.get()` và `Flux`: hai lời gọi tạo hai lô; mỗi lô phát hai phần tử rồi `onComplete`. **Nó không chứng minh poller của Spring Cloud Stream có hoạt động, cũng không chứng minh split thành message broker**.

### 13.1. Integration test cần xác nhận điều gì?

Với một binder thử nghiệm hoặc broker thật, kiểm tra ít nhất những điều sau:

1. `spring.cloud.function.definition` chọn đúng pollable supplier và output binding.
2. Sau hai lần poll, nguồn tạo đúng hai batch với ID khác nhau.
3. Với `splittable = true`, hai phần tử trong mỗi batch tạo đúng số message đầu ra kỳ vọng.
4. Với `splittable = false`, adapter và downstream thực sự xử lý publisher theo hợp đồng dự kiến.
5. Cấu hình `fixed-delay`/poller theo binding có hiệu lực; đếm số lần `get()` trong khoảng đo thích hợp.
6. Khi truy vấn thất bại, không có dữ liệu bị xác nhận/đánh dấu hoàn thành sai.
7. Khi broker chậm, restart hoặc có hai instance, không gửi trùng ngoài mức hệ thống chấp nhận.
8. Khi shutdown, tất cả subscription/tài nguyên được giải phóng.

Không nên viết test ngủ chính xác 1.000 ms rồi kỳ vọng luôn có đúng một poll: scheduler và thời điểm khởi động binder có thể dao động. Có thể dùng điều kiện chờ với timeout hữu hạn và quan sát kết quả thực tế.

### 13.2. Khi nào test bằng Reactor StepVerifier.withVirtualTime?

`StepVerifier.withVirtualTime` phù hợp khi **chính Flux** tạo lịch, chẳng hạn `Flux.interval(...)`. Nó không tự điều khiển scheduler của Spring Integration poller. Nếu muốn kiểm thử lịch poll bên ngoài, cần integration test với cơ chế poller thật hoặc cơ chế test có thể điều khiển trigger cụ thể.

## 14. Các lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Supplier hữu hạn chỉ phát một lô rồi im lặng | `@Bean Supplier<Flux<T>>` được subscribe một lần | Dùng `@PollableBean` với adapter poller hỗ trợ, hoặc tự tổ chức trigger |
| Gắn `@PollableBean` nhưng không thấy poll | Ứng dụng chỉ có Spring Cloud Function Core, không có scheduler/adapter nhận marker | Cấu hình Spring Cloud Stream hoặc scheduler bên ngoài |
| Muốn gửi 1 batch nhưng nhận N message | `splittable` mặc định là `true` | Chọn hợp đồng batch payload rõ ràng; cân nhắc `false` và xác minh adapter |
| Đặt `splittable = false` nhưng consumer không hiểu payload | Publisher được giữ nguyên, không có chuyển đổi thích hợp | Thiết kế payload DTO và converter/downstream phù hợp |
| Một poll có 50 phần tử dù `maxMessagesPerPoll=1` | Nhầm số lượt polling với số `onNext` | Giới hạn batch size tại nguồn; hiểu cấu hình từng phiên bản |
| Poll nhanh gây trùng dữ liệu | Nguồn luôn đọc lại cùng bản ghi | Dùng checkpoint/claim/idempotency |
| Một nguồn interval tạo nhiều timer | Vừa tự lập lịch trong Flux vừa được external poller gọi lại | Chỉ dùng một cơ chế trigger |
| Sự cố broker làm message không nhất quán | Retry, transaction/ack và checkpoint không đồng bộ | Thiết kế lại ranh giới giao nhận và kiểm thử lỗi |
| Gọi JDBC blocking làm poller chậm | Truy vấn chạy ngay trong `get()` hoặc subscribe thread | Dùng repository reactive hoặc boundedElastic với giới hạn |
| Không thấy hiệu quả từ property poller | Sai prefix theo phiên bản, sai binding name hoặc thiếu Stream binder | Đối chiếu tài liệu phiên bản, log binding và integration test |
| Kiểm thử trực tiếp bean PASS nhưng broker không nhận dữ liệu | Unit test chưa kiểm chứng trigger/split/binder | Thêm integration test với adapter thật |

## 15. Quy trình lựa chọn cơ chế phù hợp

~~~mermaid
flowchart TD
    START["Nguồn cần phát dữ liệu"] --> Q{"Có tự phát liên tục\nsau subscription?"}
    Q -->|Có| LIVE["Supplier<Flux<T>>\nvới @Bean thông thường"]
    Q -->|Không, từng lô hữu hạn| BATCH{"Ai phụ trách lịch gọi?"}
    BATCH -->|Spring Cloud Stream| POLL["@PollableBean\n+ cấu hình poller"]
    BATCH -->|Cron, serverless, ứng dụng ngoài| EXT["Trigger ở bên ngoài\n+ gọi Supplier/Function"]
    POLL --> SPLIT{"Đơn vị output mong muốn?"}
    SPLIT -->|Từng phần tử| TRUE["splittable=true\n(giá trị mặc định)"]
    SPLIT -->|Một lô hoặc nguyên publisher| FALSE["splittable=false nếu adapter hỗ trợ;\nhoặc dùng batch DTO rõ ràng"]
    LIVE --> VERIFY["Xác minh vòng đời, lỗi,\nbackpressure và idempotency"]
    EXT --> VERIFY
    TRUE --> VERIFY
    FALSE --> VERIFY
~~~

Trước khi triển khai, trả lời bằng dữ liệu thực tế năm câu hỏi:

- **Nguồn:** một poll cần đọc tối đa bao nhiêu bản ghi và lấy từ đâu?
- **Trigger:** thành phần nào sở hữu lịch gọi, cấu hình theo phiên bản nào?
- **Output:** mỗi phần tử là một message hay cả batch là một message?
- **Độ tin cậy:** checkpoint, retry, idempotency và xác nhận gửi đặt ở đâu?
- **Vòng đời:** làm sao kiểm soát overlap, lỗi, shutdown và việc chạy nhiều instance?

Nếu có thể trả lời các câu hỏi này và kiểm thử cả logic lẫn adapter, `@PollableBean` trở thành một cơ chế thể hiện ý định rõ ràng mà không buộc logic nghiệp vụ phụ thuộc giao thức.

## 16. Câu hỏi tự đánh giá

1. Vì sao `Supplier<Flux<T>>` trả `Flux.just(...)` thường cần được gọi lại, trong khi `Supplier<Flux<T>>` trả `Flux.interval(...)` không nhất thiết cần poll theo từng tick?
2. Nếu một lần `get()` trả `Flux.just("A", "B", "C")` và `splittable=true`, số lần gọi `get()` và số message đầu ra có thể tương ứng là bao nhiêu?
3. Đặt `@PollableBean` trong ứng dụng chỉ dùng Spring Cloud Function Core có khiến một scheduler xuất hiện không? Thành phần nào cần đảm nhiệm điều đó?
4. Tại sao `splittable=false` không bảo đảm downstream nhận một JSON array gồm tất cả phần tử?
5. `maxMessagesPerPoll=1` có đồng nghĩa chỉ một `T` được phát từ mỗi `Flux<T>` không?
6. Nếu database trả cùng bản ghi trong hai lần poll, annotation có tự chống trùng không? Bạn cần bổ sung gì?
7. Dùng cả `@PollableBean` lẫn `Flux.interval(...)` trong cùng supplier có rủi ro gì?
8. Tại sao unit test `StepVerifier` thành công chưa đủ để khẳng định poller và broker đã gửi đúng số message?
9. Điều gì khác nhau khi chạy cùng supplier qua HTTP request, lịch serverless hoặc Spring Cloud Stream binding?

## 17. Tài liệu tham khảo

- [Spring Cloud Function — Programming model, Supplier và PollableBean](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Producing and Consuming Messages, Suppliers và Polling Configuration Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)

Các ví dụ thuộc nhóm Spring Cloud Function/Spring Cloud Stream hiện đại; chi tiết tên property và cách postprocessor/binder xử lý publisher cần đối chiếu với **phiên bản thư viện thực tế**. Tài liệu chính thức ở trên là điểm bắt đầu để xác nhận các khác biệt theo phiên bản.

**Ghi nhớ:** `@PollableBean` đánh dấu một reactive supplier có thể cần **được gọi lại để lấy các Flux hữu hạn**, nhưng **Spring Cloud Function Core không tự poll**. `splittable=true` yêu cầu tầng tích hợp có hỗ trợ tách từng phần tử thành message; `false` giữ publisher khỏi bước split đó và cần hợp đồng downstream phù hợp. **Poller bên ngoài** mới là nơi quyết định khi nào kích hoạt, còn ứng dụng phải tự thiết kế giới hạn batch, lỗi, dữ liệu trùng, checkpoint và độ tin cậy khi phát message.
