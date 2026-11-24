# Luồng thực thi

## subscribeOn: thay đổi nơi thực hiện việc đăng ký nguồn

Một pipeline reactive mô tả cách dữ liệu đi từ nguồn qua các toán tử đến subscriber. Tuy nhiên, việc đăng ký với nguồn cũng là một công việc có thể cần điều phối: một nguồn lạnh có thể mở cursor, gọi thư viện đồng bộ, đọc tệp hoặc đăng ký listener. Nếu những thao tác này chạy trên thread xử lý sự kiện của ứng dụng, chúng có thể chặn thread và làm chậm các yêu cầu khác.

Project Reactor cung cấp **subscribeOn** để điều khiển scheduler được dùng khi thực hiện quá trình đăng ký vào nguồn. Với nguồn đồng bộ, các tín hiệu được phát ngay trong quá trình đăng ký thường cũng được tạo trên thread mà scheduler đó sử dụng. Điều này đặc biệt hữu ích khi bọc một API blocking thành **Mono** hoặc **Flux**.

**subscribeOn** có vai trò khác với **publishOn**. subscribeOn điều phối việc subscribe và request ở phía upstream; publishOn chuyển việc xử lý các tín hiệu downstream sau vị trí đặt toán tử sang scheduler được chọn. Hiểu ranh giới này giúp đặt scheduler đúng chỗ và tránh kỳ vọng rằng mọi phần của pipeline tự động chạy trên cùng một thread.

### 1. Quá trình đăng ký đi từ subscriber về nguồn

Khi gọi **subscribe**, quá trình đăng ký đi ngược từ subscriber về phía publisher nguồn. Publisher thiết lập các subscription dọc theo chuỗi toán tử, sau đó nguồn bắt đầu phát dữ liệu theo nhu cầu:

~~~text
Assembly:
Source -> map -> filter -> Subscriber

Subscription:
Subscriber <- filter <- map <- Source

Data signals:
Source -> map -> filter -> Subscriber
~~~

Đăng ký đi theo hướng upstream, còn các tín hiệu dữ liệu đi theo hướng downstream. Vì vậy, thay đổi scheduler ở giai đoạn đăng ký có thể ảnh hưởng nơi nguồn được gọi và nơi các toán tử đồng bộ phía upstream xử lý tín hiệu do nguồn phát.

Ví dụ, **Flux.range** là nguồn đồng bộ. Khi subscriber đăng ký, nguồn phát các phần tử trong quá trình xử lý subscription:

~~~java
import reactor.core.publisher.Flux;

Flux.range(1, 3)
    .map(value -> value * 10)
    .subscribe(System.out::println);
~~~

Nếu không có toán tử điều phối, nguồn đồng bộ và phép biến đổi có thể chạy trên thread gọi **subscribe**. Trong một ứng dụng web reactive, thread đó có thể là event-loop thread; thực hiện công việc blocking trên thread này có thể làm giảm khả năng phục vụ nhiều request.

### 2. subscribeOn điều phối việc đăng ký nguồn

**subscribeOn(scheduler)** yêu cầu Reactor thực hiện quá trình đăng ký upstream trên scheduler được chọn:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

Flux.range(1, 3)
    .map(value -> value * 10)
    .subscribeOn(Schedulers.single())
    .subscribe(value ->
        System.out.println(
            Thread.currentThread().getName() + ": " + value
        )
    );
~~~

Với nguồn đồng bộ như **Flux.range**, subscription được thực hiện trên worker của **Schedulers.single()**. Nguồn phát phần tử trong quá trình đó, nên phép **map** phía upstream và callback nhận dữ liệu trong ví dụ cũng có thể chạy trên thread này nếu không có ranh giới scheduler khác.

**subscribeOn** không tạo một thread mới cho từng phần tử. Scheduler thường quản lý và tái sử dụng worker/thread. Việc chọn scheduler quyết định nơi thực hiện công việc được điều phối, còn số thread và cách tái sử dụng phụ thuộc loại scheduler.

### 3. Bọc lời gọi blocking đúng cách

Một lỗi thường gặp là gọi API blocking trước khi tạo Mono:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

// Lời gọi repository xảy ra ngay khi biểu thức này được đánh giá.
Mono<Customer> wrong =
    Mono.just(legacyRepository.findCustomer(customerId))
        .subscribeOn(Schedulers.boundedElastic());
~~~

**subscribeOn** không thể chuyển một lời gọi đã xảy ra ở assembly time sang scheduler khác. Trong ví dụ, **findCustomer** chạy trước khi **Mono.just** được tạo. Nếu lời gọi mất nhiều thời gian, thread gọi biểu thức vẫn bị chặn.

Hãy trì hoãn lời gọi bằng **Mono.fromCallable** rồi điều phối subscription:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<Customer> customer =
    Mono.fromCallable(() ->
        legacyRepository.findCustomer(customerId)
    )
    .subscribeOn(Schedulers.boundedElastic());
~~~

**fromCallable** chỉ gọi hàm khi có subscription và chuyển exception được ném ra thành tín hiệu **onError**. **subscribeOn** đưa subscription đến callable lên scheduler phù hợp cho công việc blocking. Nếu callable trả về null, Mono hoàn tất rỗng thay vì phát một phần tử null.

Với một API trả về danh sách đồng bộ, có thể trì hoãn cả việc gọi API và tạo Flux:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

Flux<Customer> customers =
    Flux.defer(() ->
        Flux.fromIterable(legacyRepository.loadCustomers())
    )
    .subscribeOn(Schedulers.boundedElastic());
~~~

Factory trong **defer** chạy khi có subscription. Do subscription được điều phối qua **boundedElastic**, lời gọi **loadCustomers** và quá trình phát đồng bộ từ Iterable có thể chạy trên worker đó. Mỗi subscription cold sẽ gọi factory lại và có thể đọc dữ liệu mới.

### 4. Vì sao boundedElastic phù hợp với blocking?

Reactor cung cấp các scheduler dùng chung cho những loại công việc phổ biến:

| Scheduler | Mục đích | Cách dùng điển hình |
| --- | --- | --- |
| **Schedulers.parallel()** | Công việc tính toán ngắn, không blocking | Biến đổi CPU-bound, xử lý dữ liệu thuần |
| **Schedulers.boundedElastic()** | Công việc blocking hoặc có thời gian chờ dài | JDBC đồng bộ, API HTTP blocking, đọc tệp đồng bộ |
| **Schedulers.single()** | Công việc tuần tự trên một thread dùng chung | Tác vụ cần tuần tự hóa trong phạm vi phù hợp |
| **Schedulers.immediate()** | Thực thi ngay trên thread hiện tại | Trường hợp đặc biệt cần không điều phối |

**boundedElastic** giới hạn tài nguyên thread và hỗ trợ các tác vụ blocking có thời gian chờ. Nó thường là lựa chọn phù hợp khi tích hợp thư viện cũ chưa có API reactive. Không nên dùng **parallel** cho lời gọi blocking vì các worker của scheduler này được thiết kế cho công việc tính toán không blocking.

Nếu toàn bộ thư viện đã hỗ trợ I/O non-blocking và trả về Publisher, không cần bọc nó vào **fromCallable** chỉ để dùng **subscribeOn**. Hãy giữ nguyên API reactive và chỉ điều phối khi có lý do cụ thể.

### 5. subscribeOn và publishOn giải quyết hai việc khác nhau

Để hiểu rõ vị trí ảnh hưởng, hãy so sánh hai toán tử:

| Toán tử | Điều phối | Phạm vi tác động chính |
| --- | --- | --- |
| **subscribeOn(scheduler)** | Quá trình subscribe và request đi về upstream | Nơi nguồn được đăng ký; với nguồn đồng bộ, nơi nguồn phát và các bước upstream được thực thi |
| **publishOn(scheduler)** | Chuyển tiếp tín hiệu downstream qua scheduler | Các toán tử nằm phía downstream sau vị trí đặt publishOn |

Ví dụ kết hợp:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

Flux.range(1, 3)
    .map(this::readOrPrepareValue)
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .map(this::calculateResult)
    .subscribe(this::storeResult);
~~~

Với nguồn đồng bộ, **readOrPrepareValue** nằm phía upstream của **publishOn** và được thực thi trong luồng xử lý được khởi động bởi **subscribeOn**. Tại **publishOn**, tín hiệu được chuyển sang **parallel**; phép **calculateResult** và callback downstream tiếp tục trên scheduler đó, trừ khi một ranh giới điều phối khác được đặt phía sau.

Nếu mục tiêu là chuyển việc xử lý từng phần tử sau một bước cụ thể, hãy dùng **publishOn** tại ranh giới đó. Nếu mục tiêu là đăng ký một nguồn blocking trên scheduler khác, hãy dùng **subscribeOn** với nguồn được tạo lười.

### 6. Vị trí đặt subscribeOn trong pipeline

**subscribeOn** ảnh hưởng đến quá trình đăng ký upstream dù được đặt ở vị trí nào trong chuỗi. Tuy nhiên, để người đọc dễ thấy nguồn nào được điều phối, thông thường nên đặt nó gần nguồn:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<Customer> customer =
    Mono.fromCallable(() -> legacyRepository.findCustomer(customerId))
        .subscribeOn(Schedulers.boundedElastic())
        .map(this::toCustomerView);
~~~

Đặt gần nguồn thể hiện rõ rằng lời gọi blocking được chạy trên bounded elastic. Các toán tử phía sau không tự chuyển sang scheduler khác; chúng tiếp tục xử lý tín hiệu theo thread phát tín hiệu cho đến khi gặp một ranh giới như **publishOn**.

Nếu có nhiều **subscribeOn** trong cùng pipeline, không nên dùng chúng như cách chia pipeline thành nhiều vùng xử lý dữ liệu. Chúng điều phối quá trình đăng ký và request ở các điểm upstream, còn việc chuyển thread cho các bước xử lý dữ liệu nên được biểu diễn bằng **publishOn**. Trong hầu hết trường hợp, một **subscribeOn** gần nguồn là đủ và dễ hiểu nhất.

### 7. subscribeOn với nguồn nóng

Với nguồn cold, mỗi subscription thường khởi động việc tạo hoặc đọc dữ liệu. **subscribeOn** có thể điều phối nơi thực hiện thao tác khởi động đó.

Với nguồn hot, producer có thể đã chạy độc lập với subscriber. Khi subscriber đăng ký, **subscribeOn** chỉ điều phối lời gọi đăng ký vào nguồn hoặc listener; nó không tự di chuyển thread mà producer dùng để phát các sự kiện sau đó.

Ví dụ, một event bus bên ngoài gọi callback trên thread riêng:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

Flux<ExternalEvent> events =
    externalEventBus.events()
        .subscribeOn(Schedulers.boundedElastic())
        .publishOn(Schedulers.parallel())
        .map(this::normalize);
~~~

Ở đây, đăng ký listener có thể được thực hiện trên bounded elastic. Khi event bus phát callback trên thread của nó, **publishOn** chuyển việc xử lý phía sau sang parallel. Nếu bỏ **publishOn**, các toán tử xử lý sự kiện có thể chạy trên thread mà event bus dùng để gọi callback.

Hãy đọc tài liệu của API nguồn để biết nó phát tín hiệu trên thread nào và có hỗ trợ cancellation hay không. **subscribeOn** không thể kiểm soát một producer bên ngoài nếu producer tự quản lý vòng đời và thread phát dữ liệu.

### 8. Mỗi subscriber có thể kích hoạt một lần đăng ký riêng

Với nguồn cold được tạo bằng factory, mỗi subscription sẽ thực hiện quá trình đăng ký riêng. Vì vậy, mỗi lần đăng ký có thể chạy trên scheduler được chọn:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

AtomicInteger loads = new AtomicInteger();

Mono<Integer> value =
    Mono.fromCallable(() -> loads.incrementAndGet())
        .subscribeOn(Schedulers.boundedElastic());

value.subscribe(System.out::println);
value.subscribe(System.out::println);
~~~

Hai subscriber tạo hai subscription và callable được gọi hai lần. Scheduler có thể tái sử dụng worker/thread; điều đó không làm hai subscription trở thành một lần thực thi chung. Nếu cần chia sẻ một kết quả cho nhiều subscriber, phải chọn cơ chế chia sẻ hoặc cache phù hợp, không dựa vào việc dùng cùng một scheduler.

### 9. Demand và cancellation vẫn đi qua subscription

**subscribeOn** điều phối việc đăng ký và các yêu cầu demand đi về upstream theo scheduler. Nó không thay đổi quy tắc backpressure: Publisher vẫn chỉ được phát số phần tử đã được yêu cầu. Khi downstream hủy subscription, yêu cầu cancellation vẫn được truyền ngược qua chuỗi toán tử đến nguồn.

Nếu nguồn là một API blocking không hỗ trợ ngắt giữa chừng, việc hủy subscription không nhất thiết dừng ngay lời gọi đang chạy. Cancellation có thể ngăn công việc tiếp tục phát tín hiệu hoặc ngăn các lần yêu cầu tiếp theo, nhưng một lời gọi JDBC hay thư viện cũ đang blocking có thể chỉ kết thúc khi API đó trả về hoặc tự hỗ trợ hủy.

Khi tích hợp nguồn blocking, hãy đặt timeout ở mức API hoặc tầng kết nối nếu thư viện hỗ trợ. Không nên dựa vào cancellation của Reactor như một cơ chế đảm bảo ngắt mọi lời gọi blocking ở hệ điều hành.

### 10. Xử lý lỗi từ nguồn được subscribeOn

Lỗi phát sinh trong một nguồn lazy vẫn đi theo kênh tín hiệu reactive. Ví dụ:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<Customer> customer =
    Mono.fromCallable(() -> legacyRepository.findCustomer(customerId))
        .subscribeOn(Schedulers.boundedElastic())
        .onErrorResume(DataAccessException.class, error ->
            Mono.empty()
        );
~~~

Nếu repository ném **DataAccessException**, **fromCallable** chuyển ngoại lệ thành **onError**. Toán tử **onErrorResume** xử lý lỗi đó ở downstream và thay bằng Mono rỗng. Việc chuyển scheduler không làm thay đổi loại lỗi hay chính sách phục hồi; nó chỉ quyết định nơi lời gọi nguồn được thực hiện.

Nếu lỗi xảy ra ngay khi gọi một phương thức trước khi Publisher được tạo, **subscribeOn** không thể biến ngoại lệ đó thành tín hiệu. Vì vậy, cần đặt lời gọi có khả năng lỗi bên trong **fromCallable** hoặc factory của **defer**.

### 11. Kiểm thử scheduler của việc đăng ký nguồn

Có thể kiểm tra thread thực hiện factory bằng cách ghi lại tên thread khi nguồn được tạo:

~~~java
import java.util.concurrent.atomic.AtomicReference;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

Scheduler scheduler = Schedulers.newSingle("source-subscription-test");
AtomicReference<String> sourceThread = new AtomicReference<>();

Mono<Integer> source =
    Mono.defer(() -> {
        sourceThread.set(Thread.currentThread().getName());
        return Mono.just(42);
    })
    .subscribeOn(scheduler);

try {
    StepVerifier.create(source)
        .expectNext(42)
        .verifyComplete();

    assertTrue(sourceThread.get().startsWith("source-subscription-test"));
} finally {
    scheduler.dispose();
}
~~~

Factory trong **defer** chạy khi subscription đến nguồn. Kiểm thử xác nhận tên thread có tiền tố của scheduler được tạo. Scheduler tùy chỉnh cần được giải phóng sau kiểm thử để không giữ thread nền.

Trong kiểm thử ứng dụng, nên ưu tiên xác minh hành vi cần thiết thay vì phụ thuộc quá sâu vào tên thread nội bộ. Nếu chỉ cần chứng minh lời gọi được trì hoãn, có thể dùng bộ đếm; nếu cần chứng minh scheduler cụ thể được dùng, inject scheduler hoặc dùng một scheduler có tên rõ ràng như ví dụ.

### 12. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Gọi API blocking trước **Mono.just** | API chạy ngay trên thread gọi biểu thức | Dùng **fromCallable** hoặc **defer** |
| Nghĩ **subscribeOn** chuyển mọi đoạn xử lý downstream | Các bước sau vẫn có thể chạy trên thread phát tín hiệu | Dùng **publishOn** tại ranh giới cần chuyển |
| Dùng **parallel** cho JDBC hoặc API blocking | Worker dành cho tính toán bị chặn | Dùng **boundedElastic** hoặc API non-blocking |
| Nghĩ **subscribeOn** tạo thread mới cho mỗi phần tử | Hiểu sai vòng đời scheduler | Scheduler quản lý và tái sử dụng worker |
| Dùng **subscribeOn** để điều khiển thread của hot producer | Producer có thể vẫn phát trên thread riêng | Điều phối callback downstream bằng **publishOn** |
| Tạo scheduler riêng nhưng không dispose | Thread nền và tài nguyên có thể bị giữ | Quản lý vòng đời scheduler rõ ràng |
| Dùng nhiều **subscribeOn** để chia pipeline | Khó đọc và không thể hiện rõ ranh giới xử lý dữ liệu | Đặt một **subscribeOn** gần nguồn và dùng **publishOn** khi cần |

### 13. Quy trình lựa chọn subscribeOn

Khi quyết định có cần **subscribeOn** hay không, hãy tự hỏi:

1. Nguồn có thực hiện công việc đồng bộ hoặc blocking khi được subscribe không?
2. Lời gọi nguồn đã được trì hoãn hay đã xảy ra ở assembly time?
3. Scheduler nào phù hợp với đặc tính công việc: blocking, CPU-bound hay tuần tự?
4. Có cần chuyển các bước downstream sang scheduler khác không? Nếu có, đặt **publishOn** ở đâu?
5. Nguồn là cold hay hot; subscribeOn điều khiển việc tạo nguồn hay chỉ đăng ký listener?
6. Cancellation có thể dừng lời gọi nguồn hay chỉ ngăn các tín hiệu tiếp theo?
7. Scheduler tùy chỉnh được quản lý và giải phóng ở đâu?

Trong module REACTIVE_PROGRAMMING, **subscribeOn** là công cụ điều phối quá trình đăng ký nguồn và request upstream. Kết hợp nó với nguồn lazy như **fromCallable** hoặc **defer** giúp chuyển API blocking ra khỏi event loop. Dùng **publishOn** cho những ranh giới xử lý downstream cần đổi scheduler. Phân biệt đúng hai toán tử này giúp pipeline **Mono**/**Flux** dễ dự đoán, tránh chặn thread quan trọng và quản lý tài nguyên thực thi có chủ đích.
