# Điều tiết tốc độ theo nhu cầu nhận dữ liệu

## 1. Vì sao cần điều tiết tốc độ trong luồng phản ứng?

Hãy hình dung hệ thống nhận **10.000 sự kiện đơn hàng mỗi giây** nhưng dịch vụ kiểm tra rủi ro chỉ xử lý ổn định khoảng **500 sự kiện mỗi giây**. Nếu cứ đọc và gửi tất cả sự kiện vào tác vụ kiểm tra, số yêu cầu đang chờ, bộ nhớ và độ trễ sẽ tăng nhanh. Cuối cùng ứng dụng có thể hết kết nối, hết bộ nhớ hoặc timeout hàng loạt.

Trong mô hình **Reactive Streams**, cơ chế **backpressure** cho phép phía nhận biểu đạt nhu cầu: *“Tôi hiện sẵn sàng nhận thêm bao nhiêu phần tử?”* Phía gửi có khả năng tuân thủ cơ chế này sẽ phát dữ liệu theo yêu cầu thay vì đẩy không giới hạn.

Chương **Luồng phản ứng** của **Spring Cloud Function** thường sử dụng `Mono` và `Flux` của Project Reactor. Các bean Java như `Supplier`, `Function` và `Consumer` có thể được tra cứu qua `FunctionCatalog`, composition và đưa ra HTTP, message broker hoặc môi trường serverless. Tuy nhiên, **chữ ký có `Flux` không tự bảo đảm backpressure xuyên suốt đến nguồn dữ liệu bên ngoài**. Cơ chế điều tiết chỉ phát huy tác dụng ở những đoạn pipeline và connector có hỗ trợ.

Ví dụ, một hàm xử lý luồng đơn hàng:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> evaluate =
    orders -> orders.flatMap(
        riskClient::check, // Mono<Decision>
        8                  // Tối đa 8 tác vụ con đang hoạt động
    );
~~~

`flatMap(..., 8)` giới hạn **số publisher con đang được xử lý đồng thời trong một subscription**. Nó giúp tránh gọi quá nhiều request cùng lúc nhưng không mặc nhiên giới hạn số message broker gửi vào ứng dụng, không quy định chính sách lưu trữ khi quá tải và cũng không giới hạn số lời gọi đang chạy từ các instance khác.

Bài này đi từ **`request(n)`** của Reactive Streams đến các chiến lược điều tiết thực tế trong Spring Cloud Function.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích `Publisher`, `Subscriber`, `Subscription` và cách demand truyền từ downstream lên upstream.
2. Phân biệt **backpressure**, **giới hạn concurrency**, **buffer**, **giảm nhịp nguồn** và **rate limiting**.
3. Quan sát tác dụng của `request(n)` bằng `BaseSubscriber` hoặc `StepVerifier`.
4. Chọn `flatMap`, `concatMap`, `limitRate` và các toán tử `onBackpressure...` theo yêu cầu mất dữ liệu hoặc giữ dữ liệu.
5. Nhận diện giới hạn của nguồn hot, nguồn phát theo thời gian và nguồn bên ngoài không tuân theo backpressure.
6. Thiết kế, kiểm thử và giám sát function reactive trên HTTP, binder sự kiện và serverless.

## 2. Reactive Streams: demand đến từ phía nhận

Reactive Streams mô tả tương tác giữa những thành phần sau:

| Thành phần | Vai trò |
| --- | --- |
| `Publisher<T>` | Nguồn có khả năng phát các phần tử `T` và tín hiệu kết thúc |
| `Subscriber<T>` | Bên đăng ký nhận dữ liệu và phản hồi theo các tín hiệu |
| `Subscription` | Giao diện nối hai bên, cho phép `request(n)` và `cancel()` |
| `onNext(T)` | Tín hiệu một phần tử được phát |
| `onComplete()` | Kết thúc bình thường |
| `onError(Throwable)` | Kết thúc do lỗi |

Khi subscriber đăng ký, publisher cung cấp `Subscription` thông qua `onSubscribe`. Subscriber có thể gọi `request(n)` với `n > 0` để yêu cầu thêm `n` phần tử.

~~~mermaid
sequenceDiagram
    participant D as Subscriber (downstream)
    participant S as Subscription
    participant P as Publisher (upstream)

    D->>P: subscribe(...)
    P-->>D: onSubscribe(subscription)
    D->>S: request(2)
    S->>P: chuyển nhu cầu
    P-->>D: onNext(A)
    P-->>D: onNext(B)
    Note over D,P: Hết nhu cầu còn lại
    D->>S: request(1)
    S->>P: thêm nhu cầu
    P-->>D: onNext(C)
    P-->>D: onComplete
~~~

Đây là luồng minh họa với publisher hữu hạn có thể tuân thủ demand. `onComplete` và `onError` là tín hiệu kết thúc; chúng không phải phần tử dữ liệu và không được tính vào số lượng `request(n)`.

### 2.1. Outstanding demand là gì?

Nếu subscriber yêu cầu `request(5)` rồi nhận ba `onNext` thì, ở đoạn quan hệ subscription đó, còn nhu cầu cho hai phần tử. Nếu tiếp tục yêu cầu `request(4)`, tổng nhu cầu chưa được đáp ứng tăng tương ứng.

- Yêu cầu dương có thể được cộng dồn.
- `request(0)` hoặc `request(n)` với `n < 0` vi phạm hợp đồng Reactive Streams và dẫn đến lỗi theo quy tắc subscription.
- `Long.MAX_VALUE` biểu diễn yêu cầu **không giới hạn**. Nó tương đương cho phép upstream phát nhanh theo khả năng thay vì đợi từng lệnh yêu cầu nhỏ.
- `cancel()` thông báo rằng subscriber không còn muốn nhận dữ liệu, nhưng khả năng hủy ngay một tác vụ I/O ngoài ứng dụng phụ thuộc thư viện tích hợp.

**Demand đo số phần tử, không đo thời gian.** `request(10)` không có nghĩa “10 phần tử mỗi giây”; nó có nghĩa “có thể nhận thêm tối đa 10 phần tử theo hợp đồng của publisher”. Muốn giới hạn theo giây cần cơ chế điều tiết theo thời gian riêng.

### 2.2. Thông thường Reactor subscribe có demand lớn

Các overload tiện dụng như:

~~~java
flux.subscribe(System.out::println);
~~~

thường yêu cầu demand không giới hạn. Điều đó thuận tiện cho ứng dụng nhỏ nhưng không thể hiện cách downstream chủ động phát nhu cầu theo từng đợt.

Nếu muốn điều khiển demand, dùng `BaseSubscriber`, subscriber tùy chỉnh hoặc test với `StepVerifier`. Không cần tự điều khiển request trong mọi function: các toán tử Reactor có cơ chế điều tiết demand của riêng chúng.

## 3. Thử request(n) bằng BaseSubscriber

Ví dụ sau thực hiện một subscription yêu cầu ban đầu hai phần tử, sau đó yêu cầu tiếp ba phần tử để tiêu thụ hết nguồn hữu hạn:

~~~java
import org.reactivestreams.Subscription;

import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class DemandDemo {

    public static void main(String[] args) {
        Flux<Integer> source = Flux.range(1, 5)
            .doOnRequest(n ->
                System.out.println("Upstream requested: " + n)
            );

        source.subscribe(new BaseSubscriber<>() {
            private int received;

            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                request(2);
            }

            @Override
            protected void hookOnNext(Integer value) {
                received++;
                System.out.println("Received: " + value);

                if (received == 2) {
                    request(3);
                }
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("Completed");
            }

            @Override
            protected void hookOnError(Throwable error) {
                System.err.println("Failed: " + error);
            }
        });
    }
}
~~~

Với `Flux.range(1, 5)`, subscriber yêu cầu 2 rồi thêm 3; nguồn có thể phát các giá trị `1, 2, 3, 4, 5` và kết thúc. `doOnRequest` giúp quan sát tín hiệu yêu cầu tại điểm được đặt trong pipeline.

Các điểm cần hiểu:

1. `Flux.range` là publisher hữu hạn, cold và có khả năng phát theo demand.
2. Trong `hookOnSubscribe`, subscriber bắt đầu với `request(2)`.
3. Sau khi nhận đủ hai phần tử, subscriber gọi `request(3)` để xử lý nốt.
4. Nếu không yêu cầu thêm sau khi hết demand, nguồn có thể dừng ở hai phần tử dù chưa phát `onComplete`.
5. `BaseSubscriber` không phải framework tiêu thụ HTTP hoặc broker; ví dụ chỉ giúp thấy cơ chế Reactive Streams.

**Tránh dùng `BaseSubscriber` để “đợi” I/O bất đồng bộ bằng cách gọi `request(1)` ngay trong `hookOnNext`.** Lúc callback bắt đầu, thao tác I/O mới có thể chưa hoàn tất. Muốn giới hạn số tác vụ I/O đang chạy, hãy ghép publisher của các tác vụ bằng `concatMap` hoặc `flatMap` với mức đồng thời phù hợp.

### 3.1. Hủy khi không còn muốn nhận

~~~java
Flux.range(1, 100)
    .subscribe(new BaseSubscriber<Integer>() {
        @Override
        protected void hookOnSubscribe(Subscription subscription) {
            request(1);
        }

        @Override
        protected void hookOnNext(Integer value) {
            System.out.println(value);
            cancel();
        }
    });
~~~

Subscriber nhận phần tử đầu rồi yêu cầu hủy. Với nguồn hỗ trợ cancellation, upstream ngừng cung cấp các phần tử còn lại. **Hủy subscription không tương đương hoàn tất thành công một giao dịch hoặc rollback hoạt động bên ngoài.**

## 4. Backpressure thay đổi qua các toán tử

Nhìn vào một luồng Reactor:

~~~java
Flux<Integer> result = Flux.range(1, 100)
    .filter(n -> n % 2 == 0)
    .map(n -> n * 10);
~~~

Nếu downstream muốn nhận 5 số chẵn, upstream có thể cần phát nhiều hơn 5 số ban đầu vì `filter` loại các số lẻ. Do đó:

> **Không mặc định rằng một `request(1)` ở cuối pipeline luôn trở thành đúng một `request(1)` tại nguồn.**

Một số toán tử chuyển đổi nhu cầu:

| Toán tử | Cách nó ảnh hưởng nhu cầu upstream |
| --- | --- |
| `map` | Thường ánh xạ một phần tử vào một phần tử; gần với quan hệ 1–1 |
| `filter` | Có thể yêu cầu thêm phần tử để bù những giá trị đã bị loại |
| `buffer(10)` | Một batch đầu ra cần tối đa 10 phần tử đầu vào trong nhóm đủ kích thước |
| `flatMap` | Có thể subscribe nhiều inner publishers và prefetch dữ liệu |
| `concatMap` | Tuần tự hóa inner publishers; có các yêu cầu/buffer nội bộ theo phiên bản Reactor |
| `publishOn` | Chuyển việc phát downstream sang scheduler khác và sử dụng queue/prefetch |
| `limitRate` | Chia yêu cầu lớn thành các yêu cầu upstream nhỏ hơn |
| `collectList` | Tích lũy dữ liệu để tạo một kết quả khi upstream hoàn tất |

### 4.1. Ví dụ buffer: một yêu cầu batch khác một yêu cầu phần tử

~~~java
Flux<java.util.List<Integer>> batches =
    Flux.range(1, 6).buffer(3);
~~~

Một subscriber yêu cầu **một batch** từ `batches`. `buffer(3)` cần tiêu thụ ba số từ upstream để tạo một `List<Integer>` đủ ba phần tử. Như vậy, demand ở output là **đơn vị batch**, còn demand ở input là **đơn vị số nguyên**.

Đối với luồng lớn, batch size cần giới hạn; `collectList()` trên luồng không kết thúc sẽ đợi mãi và có nguy cơ giữ dữ liệu không giới hạn.

### 4.2. Prefetch và queue nội bộ

Toán tử bất đồng bộ như `flatMap` hoặc `publishOn` thường có cơ chế **prefetch**: chủ động yêu cầu một lượng phần tử để giảm chi phí chờ và tăng throughput. Điều này có thể khiến lượng dữ liệu đang nằm trong queue/đang xử lý lớn hơn số phần tử downstream vừa yêu cầu trực tiếp.

Vì vậy, khi giám sát backpressure, cần xem cả:

- Demand mà downstream phát ra.
- Demand đã được các toán tử trung gian chuyển đổi.
- Số phần tử nằm trong các queue/buffer.
- Số inner publishers đang hoạt động.
- Tốc độ và khả năng chịu tải của đích I/O.

Không nên lấy riêng số `request(n)` tại một điểm để suy ra toàn bộ lượng dữ liệu đang ở trong hệ thống.

## 5. limitRate: chia nhỏ yêu cầu upstream

`limitRate` thay đổi cách một pipeline yêu cầu dữ liệu từ nguồn:

~~~java
Flux<Integer> limited = Flux.range(1, 100)
    .doOnRequest(n ->
        System.out.println("Requested upstream: " + n)
    )
    .limitRate(10);
~~~

Nếu downstream yêu cầu rất nhiều phần tử, `limitRate(10)` có thể chia nhu cầu upstream thành những đợt nhỏ với ngưỡng cao tối đa được cấu hình, thay vì truyền nguyên một yêu cầu không giới hạn lên nguồn. Reactor có chiến lược bổ sung nhu cầu khi phần dữ liệu đã được tiêu thụ để duy trì luồng.

**`limitRate(10)` không có nghĩa tối đa 10 phần tử mỗi giây.** Nó điều chỉnh *kích thước request* tại một ranh giới của pipeline. Nếu nguồn và downstream đều xử lý rất nhanh, 100 phần tử vẫn có thể được xử lý trong thời gian ngắn.

Bên cạnh đó, `limitRate`:

- Không đặt giới hạn chung cho tổng số message đã nằm ở broker.
- Không thay thế giới hạn concurrency của nhiều HTTP request đang chạy.
- Không thay thế queue dung lượng hữu hạn nếu nguồn có thể đẩy bất chấp demand.
- Không tự đảm bảo giữ được thứ tự hoặc exactly-once ở hệ thống ngoài.

### 5.1. Khi nào hữu ích?

`limitRate` phù hợp khi cần quan sát/điều chỉnh yêu cầu upstream theo lô, ví dụ khi một publisher đọc từng trang hoặc có chi phí lớn cho mỗi lượt yêu cầu. Kết quả chính xác của `doOnRequest` còn phụ thuộc các toán tử và phiên bản Reactor, nên dùng test hoặc metrics để xác định tác động thực tế.

## 6. Điều tiết số tác vụ I/O đang chạy bằng flatMap và concatMap

Với xử lý bất đồng bộ, vấn đề lớn nhất thường là **số thao tác đang mở**: HTTP requests, JDBC connections, khóa giao dịch hoặc lệnh ghi broker. Ta có thể sử dụng `flatMap` với mức đồng thời giới hạn.

### 6.1. Bean Spring Cloud Function xử lý luồng sự kiện

Ví dụ dưới đây dùng Java 17+, Spring Cloud Function, Project Reactor. `RiskClient` là interface của ứng dụng, có thể được triển khai bằng WebClient hoặc một SDK bất đồng bộ trả `Mono`.

~~~java
package demo.flowcontrol;

import java.time.Duration;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration
public class RiskFunctions {

    public record OrderEvent(String orderId, long amountCents) {}

    public enum RiskStatus {
        APPROVED, REJECTED, UNAVAILABLE
    }

    public record Decision(String orderId, RiskStatus status) {}

    public interface RiskClient {
        Mono<Decision> check(OrderEvent event);
    }

    @Bean
    public Function<Flux<OrderEvent>, Flux<Decision>> assessRisk(
            RiskClient client) {

        return incoming -> incoming.flatMap(
            order -> client.check(order)
                .timeout(Duration.ofSeconds(2)),
            8
        );
    }
}
~~~

Nhận xét:

1. `assessRisk.apply(flux)` tạo pipeline cho **một publisher đầu vào**; nó không gọi toàn bộ dịch vụ rủi ro ngay lập tức.
2. `flatMap` subscribe các `Mono<Decision>` khi upstream phát `OrderEvent`.
3. Tham số `8` giới hạn số inner publishers đồng thời tại toán tử.
4. `timeout` đặt trong từng inner publisher nên áp dụng cho từng lượt kiểm tra.
5. `flatMap` có thể phát kết quả **khác thứ tự** đơn hàng ban đầu.
6. Nếu một inner publisher phát lỗi không được xử lý, luồng kết quả có thể kết thúc bằng `onError`.

Nếu hệ thống cần **dừng toàn bộ luồng khi dịch vụ rủi ro lỗi**, để lỗi truyền ra ngoài là chính sách hợp lý. Nếu cần đánh dấu sự kiện thất bại rồi tiếp tục, phải tạo một kết quả nghiệp vụ rõ ràng theo từng phần tử.

### 6.2. Xử lý lỗi trong từng tác vụ con

~~~java
@Bean
public Function<Flux<OrderEvent>, Flux<Decision>> assessRiskResilient(
        RiskClient client) {

    return incoming -> incoming.flatMap(
        order -> client.check(order)
            .timeout(Duration.ofSeconds(2))
            .onErrorResume(error ->
                Mono.just(new Decision(
                    order.orderId(),
                    RiskStatus.UNAVAILABLE
                ))
            ),
        8
    );
}
~~~

`UNAVAILABLE` biểu diễn **không kiểm tra được**, khác với `REJECTED` do quy tắc nghiệp vụ kết luận. Bằng cách xử lý lỗi ở **inner publisher**, một lỗi mạng tạm thời không nhất thiết kết thúc toàn bộ nguồn `Flux`.

Chỉ dùng chiến lược này khi hệ thống downstream chấp nhận trạng thái chưa xác định. Với thanh toán hoặc quyết định an toàn, có thể phải dừng luồng, gửi dead-letter hoặc retry có kiểm soát; không âm thầm coi mọi lỗi là thành công.

### 6.3. Cần giữ thứ tự tác động bên ngoài?

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> sequential =
    events -> events.concatMap(client::check);
~~~

`concatMap` subscribe lần lượt từng inner publisher, đợi tác vụ trước hoàn tất rồi mới xử lý tác vụ sau. Thường phù hợp với việc cập nhật trạng thái có thứ tự. Đổi lại throughput thấp hơn khi I/O chậm.

`flatMapSequential` cho phép subscribe các tác vụ đồng thời nhưng phát **kết quả** theo thứ tự nguồn. Nó **không bảo đảm side effect tại dịch vụ ngoài đã hoàn tất đúng thứ tự**. Nếu muốn đảm bảo lệnh ghi A hoàn thành trước khi bắt đầu ghi B, hãy cân nhắc `concatMap`.

### 6.4. Một giới hạn 8 không phải giới hạn toàn hệ thống

Giả sử mỗi instance có 5 subscription cùng xử lý, mỗi pipeline `flatMap(..., 8)`. Tối đa số inner tasks đang hoạt động có thể nhiều hơn 8 trên toàn instance. Nếu scale thêm instance, tổng tải còn cao hơn nữa.

Cần kiểm soát ở nhiều lớp: số subscription, số consumer, concurrency, connection pool, rate limit theo API và khả năng xử lý của dịch vụ đích. Khi yêu cầu giới hạn toàn cụm, phải có cơ chế phân phối hoặc giới hạn tập trung; một tham số `flatMap` trong mỗi pipeline là chưa đủ.

## 7. Khi nguồn không tuân thủ demand: buffer, drop, latest và error

Không phải nguồn nào cũng có thể tạm dừng theo `request(n)`. Cảm biến vật lý, callback từ SDK, hệ thống push qua WebSocket hoặc bộ đếm thời gian có thể phát dữ liệu trong khi subscriber chưa sẵn sàng. Đây là nơi cần một **chính sách quá tải**.

Reactor cung cấp các toán tử `onBackpressure...` để xử lý trường hợp bên gửi không đáp ứng tốc độ yêu cầu.

| Chiến lược | Ý nghĩa | Mất dữ liệu? | Tình huống phù hợp |
| --- | --- | --- | --- |
| `onBackpressureBuffer(...)` | Giữ tạm phần tử dư trong queue | Có thể lỗi khi đầy nếu cấu hình giới hạn | Burst ngắn với bộ nhớ được tính toán |
| `onBackpressureDrop(...)` | Bỏ phần tử khi downstream không theo kịp | Có | Telemetry có thể chấp nhận bỏ mẫu |
| `onBackpressureLatest()` | Giữ giá trị mới nhất, thay thế giá trị cũ đang chờ | Có | Trạng thái màn hình, vị trí hiện thời |
| `onBackpressureError()` | Phát lỗi nếu không thể đáp ứng nhu cầu | Dừng luồng | Yêu cầu fail-fast và báo quá tải rõ ràng |
| Điều khiển nguồn/producer | Giảm nhịp tạo dữ liệu hoặc ngừng đọc upstream | Không nhất thiết | Dữ liệu quan trọng cần giữ đầy đủ |
| Hàng đợi bền vững | Lưu dữ liệu ngoài bộ nhớ để xử lý sau | Phụ thuộc cấu hình/độ bền | Đơn hàng, thanh toán, tác vụ nghiệp vụ |

### 7.1. Buffer hữu hạn

~~~java
Flux<SensorReading> buffered = pushSource
    .onBackpressureBuffer(100);
~~~

Với phiên bản Reactor hỗ trợ overload này, buffer có sức chứa hữu hạn. Nếu dữ liệu đến quá nhanh và buffer không còn chỗ, pipeline có thể lỗi overflow. **Buffer không làm nguồn tự giảm tốc**; nó hấp thụ chênh lệch tốc độ trong một khoảng thời gian.

Các câu hỏi cần trả lời trước khi cấu hình buffer: một phần tử tốn bao nhiêu byte? Có bao nhiêu subscription đồng thời? Điều gì xảy ra khi queue đầy? Có cần lưu vào disk/broker không? Sau restart có khôi phục được dữ liệu không?

Không dùng buffer không giới hạn như giải pháp mặc định cho stream vô hạn. Nếu upstream liên tục nhanh hơn downstream, queue sớm hay muộn cũng sẽ tăng tới mức nguy hiểm.

### 7.2. Bỏ mẫu với drop/latest

~~~java
Flux<SensorReading> sampled = pushSource
    .onBackpressureLatest();
~~~

Nếu một subscriber chỉ cần **trạng thái mới nhất**, việc bỏ các trạng thái trung gian có thể hợp lý. Ví dụ màn hình nhiệt độ không nhất thiết cần hiển thị mọi giá trị đo trong lúc giao diện bị lag.

Tương tự:

~~~java
Flux<SensorReading> dropWhenBusy = pushSource
    .onBackpressureDrop(reading ->
        metrics.recordDroppedReading()
    );
~~~

Giả định `metrics.recordDroppedReading()` là phương thức đo đạc nhỏ, không chặn. Chính sách này **không phù hợp** với sự kiện thanh toán hoặc một lệnh ghi có nghĩa vụ xử lý mỗi phần tử, trừ khi đã có đường lưu trữ/khôi phục độc lập.

### 7.3. Phát lỗi khi quá tải

~~~java
Flux<SensorReading> failWhenBusy = pushSource
    .onBackpressureError();
~~~

Chọn `onBackpressureError` khi ứng dụng muốn nhận lỗi rõ ràng thay vì âm thầm làm mất phần tử. Sau `onError`, subscription kết thúc; muốn khôi phục phải thiết kế cách tạo nguồn mới, replay hoặc resume. Đừng hiểu `onErrorResume` ngoài cùng là “tiếp tục luồng cũ từ phần tử sau”.

### 7.4. Lưu ý: toán tử không cứu được một nguồn đã mất dữ liệu

Nếu một driver đã bỏ event **trước khi** đưa vào `Flux`, việc thêm `onBackpressureBuffer` ở downstream không thể khôi phục event đó. Nếu broker gửi mà consumer xác nhận trước khi lưu bền vững, một lần ngắt kết nối cũng có thể làm mất dữ liệu. Chính sách backpressure phải được thiết kế từ **nguồn dữ liệu tới nơi lưu kết quả**, không chỉ ở đoạn Reactor nằm trong application.

## 8. Flux.interval và nguồn hot: khi request không đủ

### 8.1. Flux.interval phát theo thời gian

~~~java
Flux<Long> ticks =
    Flux.interval(Duration.ofMillis(100));
~~~

`Flux.interval` được lập lịch để phát tick định kỳ. Nếu downstream không có demand cho tick cần phát, Reactor có thể kết thúc subscription bằng lỗi thiếu backpressure thay vì tự dừng thời gian ở bên ngoài. Đây là ví dụ của nguồn có yếu tố thời gian không thể “chờ vô hạn” mà vẫn giữ đúng nhịp phát.

Để quan sát các tick mà không khiến test chạy vô hạn, dùng `take(n)`:

~~~java
Flux<Long> firstFive = ticks.take(5);
~~~

`take(5)` làm publisher kết quả phát tối đa năm tick rồi hoàn tất/hủy nguồn. Nó **không** làm `Flux.interval` trở thành kho sự kiện bền vững.

### 8.2. Nguồn hot với Sinks

Một API callback có thể gửi event vào `Sinks.Many<T>`:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

Sinks.Many<String> sink =
    Sinks.many().multicast().onBackpressureBuffer(64);

Flux<String> stream = sink.asFlux();

// Callback bên ngoài muốn đẩy một sự kiện:
Sinks.EmitResult outcome = sink.tryEmitNext("ORDER-101");

if (outcome.isFailure()) {
    // Chọn chính sách: báo lỗi, retry, lưu vào queue hoặc từ chối.
}
~~~

`Sinks` cho phép phát dữ liệu từ bên ngoài vào Reactor mà không buộc callback phải được chuyển thành publisher cold. Nhưng nó không tự biến một hàng đợi trong bộ nhớ thành message broker bền vững. Hành vi khi không có subscriber, nhiều subscriber, queue đầy hoặc sink đã kết thúc tùy loại sink và cấu hình.

Không nên gọi `emitNext` trong một vòng retry vô hạn khi sink báo overflow, vì như vậy có thể làm CPU tăng cao và giữ thread nguồn. Với dữ liệu bắt buộc xử lý, cần một cơ chế lưu tạm/bền vững và backoff rõ ràng.

## 9. Phân biệt backpressure với rate limiting và batching

Các kỹ thuật dưới đây bổ sung cho nhau nhưng không có cùng ý nghĩa:

| Cơ chế | Câu hỏi được giải quyết | Công cụ minh họa |
| --- | --- | --- |
| **Backpressure** | Downstream còn muốn nhận bao nhiêu phần tử? | `request(n)`, `Subscription` |
| **Concurrency limit** | Có tối đa bao nhiêu tác vụ bất đồng bộ đang chạy? | `flatMap(mapper, 8)`, `concatMap` |
| **Rate limiting** | Có tối đa bao nhiêu yêu cầu được bắt đầu mỗi giây? | Bộ giới hạn token/rate tại client, gateway hoặc nguồn |
| **Buffering** | Chênh lệch tốc độ ngắn hạn được giữ ở đâu? | `onBackpressureBuffer`, queue có giới hạn |
| **Batching** | Có thể xử lý N phần tử trong một đợt không? | `buffer(100)`, `bufferTimeout` |
| **Sampling/drop** | Có thể bỏ dữ liệu khi quá tải không? | `onBackpressureDrop`, `onBackpressureLatest` |
| **Broker flow control** | Transport có thể giảm nhận/phát message không? | Tùy binder, consumer prefetch, poll, ack, pause |

### 9.1. Giới hạn số lần gọi theo thời gian

Giả sử một API chỉ cho phép **100 request/giây**. `flatMap(..., 8)` chỉ đảm bảo tối đa tám request đang chạy **trong một subscription**, không đảm bảo không vượt 100 request/giây khi mỗi request kết thúc rất nhanh.

Cần bộ giới hạn tốc độ dựa trên token bucket, semaphore kết hợp scheduler, hoặc chức năng rate limit của client/gateway. Một publisher `Flux.interval` có thể tạo trigger theo thời gian, nhưng không nên biến mọi API vào thành “mỗi phần tử đợi một tick” mà không xem xét buffering, hủy và độ chính xác đồng hồ.

### 9.2. Batching hiệu quả nhưng phải kiểm soát kích thước

~~~java
Function<Flux<OrderEvent>, Flux<java.util.List<OrderEvent>>> batch100 =
    orders -> orders.buffer(100);
~~~

`buffer(100)` phát list khi đủ 100 phần tử; một batch chưa đủ 100 chỉ phát khi nguồn kết thúc bình thường. Nếu stream vô hạn nhưng mật độ sự kiện thấp, batch có thể chờ rất lâu.

Muốn có giới hạn thời gian, có thể dùng:

~~~java
Function<Flux<OrderEvent>, Flux<java.util.List<OrderEvent>>> batches =
    orders -> orders.bufferTimeout(
        100,
        Duration.ofSeconds(5)
    );
~~~

Đây là ví dụ chia theo tối đa số lượng hoặc thời gian. Cần kiểm tra tác động của timer, bộ nhớ, các batch rỗng hoặc batch cuối với phiên bản Reactor đang dùng. Batching có ích khi downstream hỗ trợ ghi nhiều bản ghi một lần, nhưng một batch quá lớn có thể làm tăng độ trễ, thời gian commit và chi phí retry.

## 10. Vai trò của Spring Cloud Function trong pipeline backpressure

Một function reactive thường có chữ ký:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>>
~~~

Lời gọi `apply(input)` có thể chỉ **tạo pipeline**, còn các phần tử được xử lý khi có subscription. Vì vậy cần phân biệt:

- **Lần gọi function:** adapter truyền một `Flux<OrderEvent>` vào `Function.apply`.
- **Subscription:** subscriber ở đầu ra kích hoạt chuỗi Reactor.
- **Demand:** nhu cầu từ downstream đi ngược qua các toán tử, nếu chúng hỗ trợ.
- **Tác vụ nghiệp vụ:** `flatMap`/`concatMap` kích hoạt các publisher I/O theo từng phần tử.
- **Vòng đời:** `onComplete`, `onError` hoặc `cancel` xác định điểm kết thúc.

### 10.1. Tách bước lọc và bước gọi API

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderEvent>> positiveOrders() {
    return orders -> orders
        .filter(order -> order.amountCents() > 0);
}
~~~

Với bean `assessRisk` ở mục 6, Spring Cloud Function có thể tạo composition:

~~~properties
spring.cloud.function.definition=positiveOrders|assessRisk
~~~

Hai chữ ký tương thích về kiểu luồng: `positiveOrders` phát `Flux<OrderEvent>`, `assessRisk` nhận `Flux<OrderEvent>` và trả `Flux<Decision>`. `FunctionCatalog` hỗ trợ tìm function theo tên và composition; **nó không tạo bảo đảm end-to-end backpressure chỉ nhờ việc có composition**.

### 10.2. Supplier: nguồn có tạo dữ liệu theo demand không?

~~~java
@Bean
Supplier<Flux<Integer>> orderIds() {
    return () -> Flux.range(1, 1000);
}
~~~

`Flux.range` phát theo demand và hữu hạn. Ngược lại:

~~~java
@Bean
Supplier<Flux<Long>> sensorTicks() {
    return () -> Flux.interval(Duration.ofMillis(100));
}
~~~

`Flux.interval` phát theo thời gian. Khi sử dụng Spring Cloud Stream, adapter có thể lấy publisher để duy trì subscription dài hạn; tuy nhiên tần suất gọi supplier, cách đẩy message và mức điều tiết đến broker phụ thuộc adapter.

Nếu nguồn phải được đọc theo lịch từng lô hữu hạn, cơ chế `@PollableBean` có thể dùng với Spring Cloud Stream có poller hỗ trợ. Khi đó **polling cadence** quyết định bao giờ tạo lô mới; còn `request(n)` quyết định nhu cầu bên trong subscription khi các thành phần Reactor tương thích. Hai cơ chế không phải một.

### 10.3. Consumer: ai subscribe và ai phát demand?

~~~java
Consumer<Flux<OrderEvent>> loggingConsumer = source ->
    source.subscribe(
        event -> logger.info("{}", event),
        error -> logger.error("stream failed", error)
    );
~~~

Với reactive `Consumer<Flux<T>>` tường minh, vì `accept` trả `void`, caller/framework không có publisher kết quả để subscribe. Consumer thường phải tự subscribe, đồng thời quản lý `Disposable`, lỗi và lifecycle. Các overload `subscribe(...)` tiện dụng thường yêu cầu không giới hạn; muốn điều tiết, ưu tiên xây pipeline có giới hạn concurrency hoặc subscriber chủ động.

Nếu cần trả tín hiệu hoàn tất/lỗi cho caller, cân nhắc:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> persistOrders = source ->
    source.concatMap(repository::save).then();
~~~

`repository.save` ở đây là API giả định trả publisher. `Mono<Void>` trả về cho caller có thể được subscribe và quan sát completion. Với nguồn không bao giờ hoàn tất, `Mono<Void>` toàn pipeline cũng có thể không hoàn tất trong suốt vòng đời; nó không tự biểu diễn acknowledgment **từng** message.

## 11. HTTP, broker và serverless: backpressure kết thúc ở đâu?

Dùng cùng một bean Spring Cloud Function qua giao thức khác nhau là lợi ích lớn của kiến trúc này, nhưng cơ chế điều tiết của Reactor chỉ có ích khi các thành phần trên đường truyền tương thích.

~~~mermaid
flowchart LR
    E["Nguồn sự kiện / HTTP / broker"] --> A["Adapter"]
    A --> P["Flux đầu vào"]
    P --> F["FunctionCatalog + Function<Flux<T>,Flux<R>>"]
    F --> O["Flux kết quả"]
    O --> D["Adapter / downstream"]
    D --> DEST["HTTP client / broker / dịch vụ đích"]
    D -.->|"request(n) nếu tương thích"| O
    O -.->|"demand truyền ngược"| F
    F -.->|"demand truyền ngược"| P
    P -.->|"cần connector hỗ trợ"| A
~~~

### 11.1. HTTP

Một HTTP stack reactive có thể biểu diễn body như publisher và hỗ trợ stream response, nhưng hành vi thực tế phụ thuộc HTTP adapter, media type, client và tầng mạng. Ví dụ server có thể trả dữ liệu dạng streaming hoặc gom kết quả trước khi trả. Backpressure ở Reactor chưa chắc tương đương với việc TCP/network tự dừng nguồn nghiệp vụ ngay lập tức.

Khi client ngắt kết nối, cancellation có thể được truyền đến subscription. Tuy nhiên, một thao tác ghi bên ngoài đang chạy không nhất thiết rollback hoặc hủy tức thì; cần thiết kế timeout và cleanup.

### 11.2. Spring Cloud Stream và binder

Tài liệu Spring Cloud Stream nêu rõ: dùng API reactive **không tự mang lại end-to-end backpressure** nếu nguồn/đích không tương thích Reactive Streams. Với một Kafka/Rabbit binder xử lý message theo mô hình không reactive, ranh giới message channel có thể cắt đứt khả năng truyền `request(n)` trực tiếp đến broker.

Một số lớp cơ sở hạ tầng có cơ chế điều tiết riêng như consumer prefetch, số record mỗi lần poll, pause/resume, ack hoặc credit; tên và semantics tùy binder. Các cấu hình đó **không tự được điều khiển bởi `limitRate(10)` trong Java**.

Ngoài ra, tài liệu Spring Cloud Stream cho biết **reactive Kafka binder đã được đánh dấu deprecated từ phiên bản 4.3.0**. Vì vậy cần đối chiếu phiên bản Spring Cloud Stream và hướng bảo trì của connector trước khi chọn binder để chỉ nhằm có end-to-end reactive behavior; không nên xem binder này là lời giải mặc định cho dự án mới.

### 11.3. Reactive function và retry

Ở mô hình reactive, một function có thể được áp dụng một lần để thiết lập pipeline dài hạn. Sau đó từng message đi qua các toán tử; framework không nhất thiết có cùng điểm chặn và bao lỗi **mỗi message** như với `Function<T,R>` imperative.

Do đó, chính sách `onErrorResume`, `retryWhen`, timeout và phân loại lỗi **bên trong pipeline** là rất quan trọng. Mặt khác, lỗi transport, redelivery và acknowledgment vẫn phải xử lý theo binder thực tế.

### 11.4. Serverless

Môi trường serverless thường có timeout invocation và hạn mức concurrency. Một `Flux` vô hạn không mặc nhiên phù hợp nếu runtime cần đợi completion. Hãy chọn ranh giới đầu vào hữu hạn, giới hạn số request đồng thời và kết thúc trong hạn mức cho phép.

Backpressure không thay thế giới hạn concurrency của nền tảng serverless, quota API bên ngoài hoặc kiểm soát số invocation đồng thời. Nếu cần xử lý sự kiện lớn, có thể dùng queue/broker kết hợp cơ chế nhận theo lô và idempotency.

## 12. Message<T>, phân vùng và thứ tự

Một `Flux<T>` chỉ chứa payload có thể thiếu thông tin cần thiết để quyết định cách điều tiết. Khi cần ID sự kiện, key phân vùng hoặc correlation ID, có thể dùng `Flux<Message<T>>`:

~~~java
Function<
    Flux<org.springframework.messaging.Message<OrderEvent>>,
    Flux<Decision>
> processMessages = messages -> messages
    .flatMap(message ->
        riskClient.check(message.getPayload()),
        8
    );
~~~

Ví dụ này minh họa xử lý payload; output `Decision` không tự mang header từ input. Nếu downstream cần correlation ID, function nên trả `Message<Decision>` và sao chép/chọn lọc header nghiệp vụ tương ứng.

Khi một luồng trộn nhiều khóa phân vùng, chạy song song có thể tăng throughput nhưng cũng làm thay đổi thứ tự hoàn tất. Nếu các sự kiện cùng `orderId` phải xử lý tuần tự, cần chiến lược chia luồng theo key, giới hạn song song và bảo đảm mỗi key không bị xử lý đồng thời ở nhiều instance. **`flatMap(..., 8)` không tự bảo đảm thứ tự trong một partition.**

## 13. Quan sát nhu cầu, queue, lỗi và việc hủy

Có thể dùng các hook Reactor để quan sát pipeline:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> observed =
    source -> source
        .doOnRequest(n ->
            logger.debug("Downstream requested {}", n)
        )
        .flatMap(riskClient::check, 8)
        .doOnError(error ->
            logger.error("Risk stream failed", error)
        )
        .doFinally(signal ->
            logger.info("Risk stream finished by {}", signal)
        );
~~~

Lưu ý: `doOnRequest` quan sát demand **tại vị trí nó được đặt**. Nếu một toán tử downstream viết lại nhu cầu, những lần request mà upstream thấy có thể khác nhu cầu ban đầu của subscriber cuối cùng.

Các số liệu nên theo dõi trong môi trường thực tế:

| Nhóm | Ví dụ metric | Ý nghĩa |
| --- | --- | --- |
| Thông lượng | Events nhận/giây, events xử lý thành công/giây | Xác định chênh lệch tốc độ |
| Độ trễ | p50/p95/p99 thời gian xử lý | Phát hiện downstream chậm |
| Đồng thời | Số request I/O đang chạy | Kiểm tra mức `flatMap` và pool |
| Queue | Kích thước và thời gian nằm trong buffer | Phát hiện backlog |
| Quá tải | Số event bị drop, buffer overflow | Đánh giá chính sách mất dữ liệu |
| Lỗi | Timeout, retry, dead-letter, redelivery | Đánh giá khả năng phục hồi |
| Vòng đời | Subscription, completion, cancellation | Kiểm tra đóng/hủy nguồn |
| Broker | Lag, offset, ack, consumer pause/prefetch | Quan sát chênh lệch ở phía transport |

Không nên log mỗi `onNext` ở tốc độ rất cao; bản thân logging có thể làm chậm pipeline. Nên dùng metric tổng hợp, sampling hoặc log có giới hạn.

### 13.1. Một lỗi phổ biến khi đo demand

~~~java
Flux<Integer> source = Flux.range(1, 10)
    .doOnRequest(n -> logger.info("request={}", n))
    .buffer(5);
~~~

Nếu subscriber yêu cầu một **List**, `buffer(5)` có thể yêu cầu số lượng **Integer** lớn hơn một từ upstream. Vì vậy, số `request(n)` tại `Flux.range` cần được diễn giải theo đơn vị của nguồn; không thể so trực tiếp với request đếm batch ở đầu ra.

## 14. Kiểm thử backpressure bằng StepVerifier

`reactor-test` cho phép chủ động đặt demand ban đầu bằng `StepVerifier.create(publisher, initialRequest)`. Đây là cách xác nhận publisher không phát vượt nhu cầu trong những trường hợp có thể kiểm thử xác định.

### 14.1. Yêu cầu 2 rồi yêu cầu thêm 3 phần tử

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicLong;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class DemandTest {

    @Test
    void sourceRespectsDemandInTwoRounds() {
        AtomicLong requested = new AtomicLong();

        Flux<Integer> source = Flux.range(1, 5)
            .doOnRequest(requested::addAndGet);

        StepVerifier.create(source, 0L)
            .expectSubscription()
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(3)
            .expectNext(3, 4, 5)
            .verifyComplete();

        assertEquals(5L, requested.get());
    }
}
~~~

Test bắt đầu với demand `0`, rồi chủ động yêu cầu `2` và `3`. Với nguồn trực tiếp `Flux.range` không qua toán tử viết lại request, tổng nhu cầu upstream là năm phần tử.

### 14.2. Yêu cầu một batch, nguồn cần ba phần tử

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class BufferDemandTest {

    @Test
    void batchesChangeDemandUnit() {
        Flux<List<Integer>> batches = Flux.range(1, 6).buffer(3);

        StepVerifier.create(batches, 0L)
            .expectSubscription()
            .thenRequest(1)
            .expectNext(List.of(1, 2, 3))
            .thenRequest(1)
            .expectNext(List.of(4, 5, 6))
            .verifyComplete();
    }
}
~~~

Test này làm rõ `request(1)` ở output của `buffer(3)` có nghĩa là muốn nhận **một list**, chứ không phải một số nguyên.

### 14.3. Kiểm tra giới hạn concurrency

Với I/O bất đồng bộ, có thể dùng bộ đếm số tác vụ đang hoạt động và một publisher có delay để kiểm thử mức đồng thời:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ConcurrencyTest {

    @Test
    void flatMapDoesNotExceedConfiguredConcurrency() {
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maxSeen = new AtomicInteger();

        Flux<Integer> pipeline = Flux.range(1, 10)
            .flatMap(number -> Mono.defer(() -> {
                int now = active.incrementAndGet();
                maxSeen.accumulateAndGet(now, Math::max);

                return Mono.delay(Duration.ofMillis(10))
                    .map(ignored -> number)
                    .doOnTerminate(() -> active.decrementAndGet());
            }), 2);

        StepVerifier.create(pipeline.collectList())
            .assertNext(results -> assertEquals(10, results.size()))
            .verifyComplete();

        assertTrue(maxSeen.get() <= 2);
    }
}
~~~

Test này xác minh mức đồng thời của inner publishers trong một subscription, **không phải giới hạn của toàn bộ cluster**. Để kiểm thử việc broker tạm dừng, queue đầy, retry hay mất kết nối, cần integration test với adapter/binder.

### 14.4. Test nguồn thời gian và cancellation

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1)).take(3)
    )
    .thenAwait(Duration.ofSeconds(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();
~~~

`withVirtualTime` hữu ích để không phải đợi thời gian thực khi kiểm thử scheduler Reactor. `take(3)` yêu cầu dừng sau ba tick; điều này không có nghĩa `Flux.interval` gốc tự hoàn tất.

Nếu kiểm thử nguồn liên tục không được giới hạn bằng `take`, nên dùng `thenCancel()` và `verify()` thay vì chờ `onComplete` mãi. Bên cạnh đó, cần xác định cleanup với `doFinally` hoặc kiểm thử đóng tài nguyên thực tế.

## 15. Tình huống thực tế: xử lý đơn hàng không được mất sự kiện

Một hệ thống thương mại điện tử có luồng sự kiện đơn hàng. Đầu vào có thể tăng đột biến trong giờ cao điểm; dịch vụ kiểm tra rủi ro chậm hơn nguồn. Mục tiêu **không làm mất một đơn hàng nào** và vẫn duy trì độ trễ chấp nhận được.

Một thiết kế thực tế phải giải quyết nhiều lớp:

1. **Nguồn bền vững:** đặt sự kiện vào broker/outbox hoặc hệ thống lưu trữ có thể đọc lại; không dựa vào `Flux.interval` hoặc buffer trong RAM như nguồn sự thật.
2. **Nhận và điều tiết:** cấu hình tiêu thụ message, prefetch/poll, partition và acknowledgment theo binder cụ thể; đánh giá khả năng giảm tốc ở ranh giới transport.
3. **Pipeline Reactor:** dùng `flatMap(..., concurrency)` cho I/O độc lập, hoặc `concatMap` khi cần tuần tự; không dùng drop/latest cho đơn hàng bắt buộc xử lý.
4. **Lỗi:** đặt timeout, retry có giới hạn, dead-letter và phân biệt lỗi tạm thời với lỗi nghiệp vụ.
5. **Idempotency:** dùng khóa `eventId` để xử lý lại an toàn khi broker redelivery hoặc upstream được subscribe lại.
6. **Giám sát:** theo dõi consumer lag, buffer, throughput, request đang chạy, lỗi và độ trễ.
7. **Kiểm thử:** kiểm tra trường hợp broker chậm, một instance bị dừng, lỗi giữa batch, hủy subscription và khởi động lại.

Một pipeline mẫu (giả sử `event` và `riskClient` phù hợp với các kiểu ở mục 6):

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<Decision>> controlledProcessing(
        RiskClient riskClient) {

    return incoming -> incoming
        .flatMap(order ->
            riskClient.check(order)
                .timeout(Duration.ofSeconds(2))
                .retryWhen(
                    reactor.util.retry.Retry.backoff(
                        2,
                        Duration.ofMillis(200)
                    )
                ),
            8
        );
}
~~~

Đây chỉ là **phần xử lý trong Reactor**. Muốn kết luận “không mất đơn”, vẫn cần thiết kế idempotency của lời gọi `riskClient.check`, chính sách retry/ack của broker, nguồn sự kiện bền vững và test lỗi cuối đường truyền. `retryWhen` có thể làm lặp side effect nếu lời gọi trước đã thành công ở dịch vụ đích nhưng phản hồi bị mất.

### 15.1. Khi nào được bỏ dữ liệu?

Đối với dữ liệu giám sát như nhiệt độ tức thời hoặc tốc độ khung hình giao diện, mất một số mẫu có thể chấp nhận được. Khi đó có thể dùng `onBackpressureLatest` hoặc `onBackpressureDrop`, nhưng nên ghi metrics số phần tử bị loại và có quy tắc cập nhật lại trạng thái.

Đối với giao dịch tài chính, đơn hàng, hóa đơn hoặc sự kiện pháp lý, mỗi phần tử có thể là một nghĩa vụ riêng. Vì vậy, một toán tử drop chỉ giải quyết áp lực tài nguyên trước mắt nhưng tạo rủi ro mất dữ liệu; nên ưu tiên nguồn bền vững, queue hữu hạn và kiểm soát tốc độ ngay tại producer/consumer.

## 16. Các lỗi hiểu nhầm thường gặp

| Nhận định sai | Giải thích đúng |
| --- | --- |
| “Dùng `Flux` là broker tự giảm tốc theo `request(n)`.” | Chỉ các thành phần hỗ trợ và kết nối tương thích mới truyền được demand xuyên suốt. |
| “`request(10)` tức 10 phần tử mỗi giây.” | Đó là số phần tử được phép phát thêm, không phải hạn mức theo thời gian. |
| “`subscribe(onNext)` mặc định chỉ yêu cầu một phần tử.” | Các overload tiện dụng thường yêu cầu không giới hạn. |
| “`limitRate(10)` giới hạn 10 request/giây.” | Nó chia nhỏ nhu cầu upstream, không giới hạn thời gian. |
| “`flatMap(..., 8)` giới hạn tám tác vụ toàn cluster.” | Đây là giới hạn inner publishers trong một subscription của toán tử. |
| “`flatMapSequential` khiến database ghi đúng thứ tự.” | Nó có thể giữ thứ tự giá trị đầu ra nhưng vẫn thực thi side effect đồng thời. |
| “Buffer không giới hạn xử lý được mọi lần burst.” | Nếu chênh lệch tốc độ kéo dài, bộ nhớ có thể cạn. |
| “`onBackpressureLatest` không mất dữ liệu.” | Nó thay thế những giá trị cũ đang chờ bằng giá trị mới hơn. |
| “Backpressure xử lý được event đã bị SDK bỏ trước khi vào Flux.” | Event đã mất ở upstream không được Reactor downstream khôi phục. |
| “`Mono<Void>` hoàn tất sau mỗi message trong luồng vô hạn.” | Completion cuối publisher xảy ra khi **toàn upstream** hoàn tất, không phải sau mỗi phần tử. |
| “`onErrorResume` ngoài cùng tiếp tục subscription cũ.” | Nó thay thế publisher bị lỗi; upstream lỗi đã kết thúc subscription. |
| “Unit test StepVerifier đủ xác nhận broker flow control.” | Cần integration test ở ranh giới binder/transport và cơ chế delivery. |

## 17. Câu hỏi tự đánh giá

1. `request(n)` là gì? Vì sao nó không phải giới hạn n phần tử mỗi giây?
2. Subscriber yêu cầu năm phần tử rồi nhận ba `onNext`. Nếu không có yêu cầu khác, còn demand bao nhiêu ở subscription đó?
3. Một subscriber gọi `request(0)` có hợp lệ không?
4. Vì sao `filter` hoặc `buffer` có thể khiến lượng request tại upstream khác lượng request ở downstream?
5. `limitRate(16)` và `flatMap(mapper, 16)` khác nhau về mục đích nào?
6. Khi nào chọn `concatMap` thay vì `flatMap`? Vì sao `flatMapSequential` không bảo đảm thứ tự commit?
7. Vì sao `onBackpressureDrop` phù hợp hơn cho một số dữ liệu telemetry so với các sự kiện thanh toán?
8. `Flux.interval` sẽ xảy ra chuyện gì nếu subscriber không có nhu cầu nhận tick ở thời điểm cần phát?
9. Tại sao `Sinks.Many` có buffer không thể thay thế một broker bền vững?
10. Sử dụng `Function<Flux<T>, Flux<R>>` trong Spring Cloud Function có tự bảo đảm backpressure với Kafka/Rabbit không?
11. Nếu function chạy trên năm instance, việc đặt `flatMap(..., 8)` có đủ để giới hạn toàn hệ thống ở tám HTTP request không?
12. Bạn sẽ dùng `StepVerifier.create(publisher, 0L)` như thế nào để chứng minh nguồn tuân thủ demand?
13. Những metric nào giúp phân biệt backlog ở broker, backlog trong pipeline Reactor và bottleneck tại API bên ngoài?
14. Khi có dữ liệu cần xử lý đầy đủ, bạn sẽ kết hợp backpressure, idempotency, retry và acknowledgment ra sao?

## 18. Tài liệu tham khảo

- [Reactive Streams — Specification](https://www.reactive-streams.org/) — quy tắc `Publisher`, `Subscriber`, `Subscription` và `request(n)`.
- [Project Reactor — Simple Ways to Create a Flux or Mono and Subscribe to It](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html) — `BaseSubscriber` và cách thay đổi request.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/) — các toán tử, prefetch, buffer, lỗi và cancellation.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/) — `StepVerifier` và kiểm thử theo demand.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — mô hình function reactive, giới hạn backpressure với binder không reactive.
- [Spring Cloud Stream — Reactive Kafka Binder Overview](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-reactive-binder/overview.html) — lưu ý trạng thái deprecated và lộ trình lựa chọn binder.

Các cấu hình và đặc tính adapter có thể thay đổi giữa các phiên bản thư viện. Khi đưa ứng dụng vào production, hãy kiểm tra BOM/phiên bản Spring Cloud Function, Spring Cloud Stream, Reactor, binder và giao thức thực tế.

**Ghi nhớ:** Backpressure trong Reactive Streams là **nhu cầu nhận dữ liệu** được biểu đạt bằng `request(n)`. Nó giúp các publisher và toán tử tương thích điều tiết số phần tử phát tới subscriber. `flatMap` giới hạn công việc bất đồng bộ, `limitRate` chia nhu cầu, còn buffer/drop/latest là những chính sách xử lý chênh lệch tốc độ với các đánh đổi khác nhau. Trong Spring Cloud Function, hãy kết hợp pipeline Reactor với cơ chế kiểm soát nguồn, broker, tài nguyên, retry và idempotency; chỉ khi các ranh giới liên quan cùng hỗ trợ thì mới có thể đạt điều tiết tốc độ đáng tin cậy từ đầu đến cuối.
