# Ghép luồng

## Nguồn rỗng, nguồn lỗi và nguồn không kết thúc khi ghép

Khi ghép nhiều Publisher, kết quả không chỉ phụ thuộc vào các phần tử dữ liệu. Trạng thái kết thúc của từng nguồn cũng quyết định pipeline có phát được kết quả, có hoàn tất hay phải báo lỗi. Ba trường hợp cần phân biệt là nguồn rỗng (empty), nguồn lỗi (error) và nguồn không phát tín hiệu, cũng không kết thúc (never).

Trong Project Reactor, **Mono.empty()** và **Flux.empty()** hoàn tất bình thường mà không phát phần tử. **Mono.error(...)** và **Flux.error(...)** kết thúc bằng **onError**. **Mono.never()** và **Flux.never()** không phát **onNext**, **onComplete** hay **onError**. Khi các nguồn này được kết hợp bằng **merge**, **concat**, **zip**, **combineLatest** hoặc **when**, mỗi toán tử phản ứng theo một cách khác nhau.

Hiểu đúng ba trạng thái giúp tránh những lỗi khó phát hiện như **zip** không tạo được tuple, **concat** không bao giờ đi đến nguồn tiếp theo, hoặc **mergeDelayError** giữ một lỗi mãi vì một nguồn không kết thúc.

### 1. Phân biệt empty, error và never

Ba kiểu Publisher có vòng đời khác nhau:

| Loại nguồn | Tín hiệu phát ra | Ý nghĩa |
| --- | --- | --- |
| Empty | **onComplete** ngay, không có **onNext** | Không có dữ liệu nhưng thao tác hoàn tất bình thường |
| Error | **onError(error)** | Thao tác thất bại và kết thúc |
| Never | Không phát tín hiệu nào | Chưa có dữ liệu và cũng chưa có thông tin kết thúc |

Ví dụ:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Mono<Customer> noCustomer = Mono.empty();
Flux<Order> noOrders = Flux.empty();

Mono<Customer> failed =
    Mono.error(new IllegalStateException("customer service unavailable"));

Flux<Order> failedOrders =
    Flux.error(new IllegalArgumentException("invalid query"));

Mono<Long> pendingForever = Mono.never();
Flux<Event> liveButSilent = Flux.never();
~~~

**empty** không đồng nghĩa với **null**. Reactive Streams không cho phép Publisher phát **null** qua **onNext**. Khi một truy vấn có thể không tìm thấy bản ghi, **Mono.empty()** biểu diễn kết quả không có giá trị. **Mono.justOrEmpty(nullableValue)** cũng hữu ích khi chuyển một giá trị Java có thể là **null** thành Mono.

**error** là một kết quả thất bại rõ ràng. Subscriber nhận terminal signal **onError**; cùng subscription đó không tiếp tục phát phần tử sau lỗi.

**never** thường dùng trong kiểm thử hoặc biểu diễn một nguồn có thể chờ vô thời hạn. Nó không phải cách biểu diễn một truy vấn không có kết quả: truy vấn không có kết quả nên dùng empty để subscriber biết thao tác đã hoàn tất.

### 2. Ảnh hưởng của ba trạng thái lên các toán tử ghép

Các toán tử ghép có mục tiêu khác nhau, nên cách chúng xử lý empty, error và never cũng khác nhau:

| Toán tử | Gặp empty | Gặp error | Gặp never |
| --- | --- | --- | --- |
| **merge** | Không thêm phần tử; các nguồn khác vẫn chạy | Lỗi được truyền ngay; hủy các nguồn còn lại | Luồng hợp nhất không hoàn tất khi nguồn never còn hoạt động |
| **concat** | Bỏ qua nguồn rỗng rồi đăng ký nguồn kế tiếp | Dừng chuỗi và truyền lỗi | Không đăng ký nguồn kế tiếp nếu nguồn never đứng trước |
| **zip** | Không thể tạo tuple; hoàn tất rỗng khi một nguồn kết thúc mà chưa có giá trị | Truyền lỗi | Chờ giá trị từ nguồn never nên không tạo tuple |
| **combineLatest** | Không thể tạo tổ hợp nếu một nguồn hoàn tất mà chưa phát giá trị | Truyền lỗi | Không thể tạo tổ hợp nếu nguồn never chưa phát giá trị |
| **when** | Xem empty là hoàn tất thành công | Lỗi làm phép phối hợp thất bại | Không hoàn tất khi nguồn never chưa kết thúc |

Đây là hành vi ở cấp toán tử. Khi thêm **switchIfEmpty**, **onErrorResume**, **timeout**, **take** hoặc một toán tử phục hồi khác, hành vi downstream có thể thay đổi theo chính sách được khai báo.

### 3. merge: nguồn rỗng không cản các nguồn khác

**Flux.merge** phát phần tử từ nhiều nguồn theo thời điểm chúng đến. Một nguồn empty chỉ hoàn tất mà không đóng góp phần tử; những nguồn khác vẫn tiếp tục:

~~~java
import reactor.core.publisher.Flux;

Flux<Integer> merged =
    Flux.merge(
        Flux.just(1, 2),
        Flux.<Integer>empty(),
        Flux.just(3, 4)
    );
~~~

Kết quả chứa **1**, **2**, **3**, **4** (thứ tự xen kẽ có thể phụ thuộc thời điểm phát của các nguồn bất đồng bộ). Nguồn rỗng không tạo phần tử giả và không làm mất dữ liệu của các nguồn còn lại.

Nếu một nguồn trong **merge** phát lỗi, lỗi được truyền xuống ngay theo chính sách fail-fast mặc định. Các subscription còn hoạt động nhận yêu cầu cancellation:

~~~java
Flux<Integer> merged =
    Flux.merge(
        Flux.just(1, 2),
        Flux.error(new IllegalStateException("source failed")),
        Flux.just(3, 4)
    );
~~~

Không nên giả định các phần tử **3** và **4** chắc chắn được phát trước lỗi. Các nguồn đồng bộ có thể phát theo thứ tự đăng ký, còn nguồn bất đồng bộ phụ thuộc lịch thực thi. Khi lỗi đến downstream, các nhánh còn lại có thể bị hủy trước khi phát hết dữ liệu.

Nếu một nguồn là **Flux.never()**, **merge** vẫn có thể phát dữ liệu từ các nguồn hữu hạn khác, nhưng toàn bộ luồng không thể hoàn tất khi nguồn never còn tham gia:

~~~java
Flux<Integer> merged =
    Flux.merge(
        Flux.just(10, 20),
        Flux.<Integer>never()
    );
~~~

Subscriber nhận **10** và **20**, nhưng không nhận **onComplete**. Nếu nghiệp vụ cần một kết quả hữu hạn, hãy giới hạn nguồn dài hạn bằng timeout, take hoặc cancellation có chủ đích.

### 4. mergeDelayError: lỗi bị trì hoãn nhưng never vẫn có thể giữ luồng

**mergeDelayError** cho các nguồn còn lại tiếp tục phát sau khi một nguồn lỗi. Lỗi chỉ được chuyển xuống khi các nguồn liên quan kết thúc:

~~~java
import reactor.core.publisher.Flux;

Flux<Integer> delayed =
    Flux.mergeDelayError(
        16,
        Flux.<Integer>error(new IllegalStateException("source A failed")),
        Flux.just(10, 20),
        Flux.just(30)
    );
~~~

Các nguồn thành công vẫn có cơ hội phát **10**, **20** và **30**; sau đó downstream nhận lỗi. Nếu có nhiều nguồn lỗi, Reactor có thể chuyển một lỗi tổng hợp chứa các lỗi thành phần.

Tuy nhiên, nếu thêm một nguồn không kết thúc:

~~~java
Flux<Integer> delayedForever =
    Flux.mergeDelayError(
        16,
        Flux.<Integer>error(new IllegalStateException("source A failed")),
        Flux.just(10, 20),
        Flux.<Integer>never()
    );
~~~

Lỗi đã được ghi nhận nhưng nguồn never không phát terminal signal. Vì vậy, điều kiện để chuyển lỗi xuống không bao giờ được đáp ứng. Các phần tử từ nguồn hữu hạn vẫn có thể đến downstream, nhưng lỗi có thể bị giữ lại vô thời hạn.

Delay error phù hợp khi mọi nguồn đều có vòng đời hữu hạn hoặc đã có giới hạn thời gian. Với nguồn sống lâu như WebSocket hoặc event bus, cần xác định rõ khi nào kết thúc, hoặc dùng một cấu trúc khác để báo lỗi riêng từng nguồn.

### 5. concat: nguồn never chặn các nguồn đứng sau

**Flux.concat** đăng ký và tiêu thụ từng nguồn theo thứ tự. Nguồn kế tiếp chỉ được đăng ký sau khi nguồn hiện tại hoàn tất:

~~~java
import reactor.core.publisher.Flux;

Flux<String> sequence =
    Flux.concat(
        Flux.just("A", "B"),
        Flux.<String>empty(),
        Flux.just("C", "D")
    );
~~~

Nguồn thứ hai rỗng nên được bỏ qua; sau đó nguồn thứ ba được đăng ký. Kết quả là **A**, **B**, **C**, **D**, rồi hoàn tất.

Nếu một nguồn lỗi, **concat** dừng chuỗi tại nguồn đó và không đăng ký các nguồn phía sau:

~~~java
Flux<String> sequence =
    Flux.concat(
        Flux.just("A"),
        Flux.error(new IllegalStateException("step failed")),
        Flux.just("B")
    );
~~~

Subscriber nhận **A**, sau đó nhận lỗi. Nguồn phát **B** không được đăng ký trong lần tiêu thụ này.

Nếu nguồn đầu tiên là never, **concat** không bao giờ chuyển sang nguồn tiếp theo:

~~~java
Flux<String> sequence =
    Flux.concat(
        Flux.<String>never(),
        Flux.just("will not be reached")
    );
~~~

Đây là hệ quả trực tiếp của ngữ nghĩa tuần tự: toán tử cần **onComplete** từ nguồn hiện tại trước khi đăng ký nguồn kế tiếp. Nếu nguồn có thể im lặng vô thời hạn, hãy đặt timeout hoặc xác định một điều kiện dừng.

### 6. zip: mọi nguồn phải có phần tử để tạo tuple

**zip** kết hợp các phần tử theo vị trí. Để tạo một tuple, mỗi nguồn phải cung cấp một phần tử tương ứng. Với các Mono, nếu một nguồn hoàn tất rỗng trước khi phát giá trị, không thể tạo tuple nên kết quả zip hoàn tất rỗng:

~~~java
import reactor.core.publisher.Mono;
import reactor.util.function.Tuple2;

Mono<Tuple2<Customer, Address>> profile =
    Mono.zip(
        customerClient.findCustomer(customerId),
        addressClient.findPrimaryAddress(customerId)
    );
~~~

Nếu **findCustomer** trả **Mono.empty()**, không có tuple Customer–Address. Đây không phải lỗi; đó là kết quả rỗng của phép kết hợp. Nếu một nguồn phát lỗi, zip kết thúc bằng lỗi. Nếu một nguồn never, zip phải chờ giá trị từ nguồn đó nên không thể phát tuple.

Ví dụ zip với một nguồn rỗng:

~~~java
Mono<Tuple2<String, Integer>> combined =
    Mono.zip(
        Mono.just("order-42"),
        Mono.<Integer>empty()
    );
~~~

**combined** hoàn tất rỗng. Khi thiết kế nghiệp vụ, cần quyết định liệu thiếu một thành phần có nghĩa là không có kết quả tổng hợp, hay cần một giá trị mặc định để vẫn tạo tuple.

### 7. Chuyển empty thành giá trị trước khi zip

Nếu nghiệp vụ muốn giữ kết quả từ những nguồn có dữ liệu và biểu diễn rõ nguồn không có dữ liệu, có thể dùng **singleOptional()** trước khi zip:

~~~java
import java.util.Optional;

import reactor.core.publisher.Mono;
import reactor.util.function.Tuple2;

Mono<Tuple2<Optional<Customer>, Optional<Address>>> profile =
    Mono.zip(
        customerClient.findCustomer(customerId).singleOptional(),
        addressClient.findPrimaryAddress(customerId).singleOptional()
    );
~~~

Mỗi Mono sau **singleOptional()** luôn phát một **Optional**: **Optional.of(value)** nếu có dữ liệu hoặc **Optional.empty()** nếu nguồn hoàn tất rỗng. Nhờ đó zip có thể tạo tuple ngay cả khi một nguồn không có giá trị.

Cách này cũng hữu ích khi cần bảo đảm mỗi Publisher con được đăng ký để hoàn tất phần việc của nó. Zip có thể kết thúc sớm khi biết chắc không thể tạo tuple; nếu cần chạy mọi tác vụ độc lập, hãy chuyển empty thành một giá trị đại diện trước khi phối hợp hoặc dùng **Mono.when** nếu chỉ cần chờ hoàn tất.

Không nên thay empty bằng một đối tượng giả nếu đối tượng đó có thể bị hiểu nhầm là dữ liệu thật. **Optional** làm rõ trạng thái thiếu dữ liệu ở kiểu kết quả.

### 8. combineLatest: chờ giá trị đầu tiên từ mọi nguồn

**combineLatest** tạo kết quả khi mỗi nguồn đã phát ít nhất một giá trị. Sau đó, mỗi lần một nguồn phát giá trị mới, toán tử kết hợp giá trị mới đó với giá trị gần nhất của các nguồn còn lại:

~~~java
import reactor.core.publisher.Flux;

Flux<String> summary =
    Flux.combineLatest(
        Flux.just("PAID"),
        Flux.just("PACKING", "SHIPPED"),
        (payment, shipping) -> payment + ":" + shipping
    );
~~~

Nguồn thanh toán phát **PAID**; nguồn vận chuyển phát các trạng thái. Khi cả hai nguồn đã có giá trị, kết quả được tạo từ các giá trị mới nhất. Nguồn hoàn tất sau khi đã phát giá trị vẫn để lại giá trị cuối cùng để kết hợp với những cập nhật tiếp theo từ nguồn khác.

Nếu một nguồn hoàn tất mà chưa từng phát giá trị, không thể hình thành tổ hợp đầu tiên; luồng kết hợp có thể hoàn tất mà không phát kết quả. Nếu một nguồn là never và chưa phát giá trị, các nguồn khác có thể phát nhưng không có tổ hợp nào được tạo. Nếu nguồn never cũng không kết thúc, subscriber không nhận được terminal signal từ phép kết hợp.

Vì vậy, khi dùng **combineLatest**, hãy xác định nguồn nào bắt buộc phải có giá trị ban đầu. Với nguồn có thể rỗng, có thể dùng **defaultIfEmpty** để cung cấp giá trị mặc định hoặc chuyển sang **Optional** để giữ ý nghĩa thiếu dữ liệu.

### 9. when: chỉ phối hợp tín hiệu hoàn tất

**Mono.when** phù hợp khi cần chờ nhiều tác vụ hoàn tất mà không cần hợp nhất giá trị dữ liệu:

~~~java
import reactor.core.publisher.Mono;

Mono<Void> completed =
    Mono.when(
        auditService.write(event),
        notificationService.send(event),
        metricsService.record(event)
    );
~~~

Publisher hoàn tất rỗng được xem là hoàn tất thành công. Nếu một tác vụ phát lỗi, **when** mặc định truyền lỗi ngay và hủy các tác vụ còn lại đang hoạt động. Nếu một tác vụ là never, **when** không thể hoàn tất cho đến khi tác vụ đó kết thúc.

**Mono.whenDelayError** trì hoãn việc truyền lỗi cho đến khi các Publisher hoàn tất. Giống **mergeDelayError**, một nguồn never có thể giữ lỗi lại vô thời hạn. Chỉ dùng delay error khi các tác vụ có vòng đời hữu hạn hoặc có timeout thích hợp.

### 10. Chọn hành vi cho nguồn empty

Nếu nguồn rỗng là một trường hợp nghiệp vụ bình thường, hãy quyết định cách biểu diễn trước khi ghép:

~~~java
import reactor.core.publisher.Mono;

Mono<Customer> customer =
    customerClient.findCustomer(customerId)
        .switchIfEmpty(Mono.defer(() ->
            customerRepository.findArchivedCustomer(customerId)
        ));
~~~

**switchIfEmpty** chuyển sang nguồn dự phòng chỉ khi nguồn đầu tiên hoàn tất mà không phát giá trị. Dùng **defer** cho nguồn dự phòng nếu việc gọi repository cần được trì hoãn đến thời điểm thực sự cần.

Nếu cần giá trị mặc định:

~~~java
import reactor.core.publisher.Mono;

Mono<ShippingStatus> status =
    shippingClient.findStatus(orderId)
        .defaultIfEmpty(ShippingStatus.UNKNOWN);
~~~

Giờ đây một nguồn rỗng trở thành một giá trị **UNKNOWN**, giúp các phép zip hoặc combine có thể tiếp tục. Hãy bảo đảm giá trị mặc định có ý nghĩa nghiệp vụ rõ ràng; không nên biến thiếu dữ liệu thành một trạng thái thành công giả.

### 11. Chọn hành vi cho nguồn error

Lỗi cần được phân loại theo khả năng phục hồi. Nếu có nguồn thay thế:

~~~java
import reactor.core.publisher.Mono;

Mono<Customer> customer =
    customerClient.findCustomer(customerId)
        .onErrorResume(ServiceUnavailableException.class, error ->
            backupCustomerClient.findCustomer(customerId)
        );
~~~

**onErrorResume** chỉ chuyển sang nguồn dự phòng cho loại lỗi đã chọn. Những lỗi khác vẫn được truyền xuống. Khi đặt phục hồi bên trong từng nhánh trước khi ghép, lỗi riêng của nhánh có thể được xử lý mà không làm thất bại toàn bộ phép hợp nhất.

Nếu muốn giữ thông tin lỗi như dữ liệu, có thể dùng một kiểu kết quả có trường trạng thái hoặc **materialize()** để biểu diễn tín hiệu. Cách này cần được thiết kế cẩn thận vì **materialize** chuyển terminal signal thành dữ liệu tín hiệu; nó không làm cho nguồn never tự phát ra kết quả.

### 12. Giới hạn nguồn never hoặc nguồn im lặng

Một Publisher không phát tín hiệu có thể làm pipeline chờ mãi. Tùy mục đích, có thể giới hạn bằng timeout hoặc take:

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;

Flux<Event> boundedEvents =
    eventClient.events()
        .timeout(Duration.ofSeconds(15));

Flux<Event> firstHundred =
    eventClient.events()
        .take(100);

Flux<Event> forThirtySeconds =
    eventClient.events()
        .take(Duration.ofSeconds(30));
~~~

**timeout(Duration)** phát lỗi nếu không có tín hiệu phù hợp trong khoảng thời gian quy định. Với Flux, timeout mặc định giám sát khoảng chờ giữa các tín hiệu; nguồn vẫn có thể chạy lâu nếu đều đặn phát dữ liệu. **take(100)** hoàn tất sau 100 phần tử, nhưng nếu nguồn never không phát phần tử nào thì nó vẫn chờ. **take(Duration)** kết thúc sau khoảng thời gian, kể cả khi nguồn không phát dữ liệu.

Nếu muốn chuyển timeout thành nguồn dự phòng, dùng overload timeout có fallback:

~~~java
import java.time.Duration;

import reactor.core.publisher.Mono;

Mono<Config> config =
    configClient.fetch()
        .timeout(
            Duration.ofSeconds(2),
            Mono.just(Config.defaults())
        );
~~~

Khi nguồn không phát tín hiệu trong thời hạn, subscriber nhận cấu hình mặc định. Cần phân biệt fallback do timeout với fallback do empty: **switchIfEmpty** không chạy chỉ vì nguồn im lặng; nó chỉ chạy khi nguồn phát **onComplete** mà không có phần tử.

### 13. Cancellation là cách dừng một nguồn không cần chờ

Nếu subscriber không còn cần dữ liệu, nó có thể hủy subscription. Trong Reactor, các dạng **subscribe** thường trả về **Disposable**:

~~~java
import reactor.core.Disposable;
import reactor.core.publisher.Flux;

Disposable subscription =
    Flux.<Event>never()
        .subscribe(this::handleEvent);

// Khi thành phần sở hữu không còn cần luồng:
subscription.dispose();
~~~

Cancellation yêu cầu nguồn dừng việc phát dữ liệu cho subscription đó. Nó không phải **onComplete** và không biến nguồn never thành nguồn hoàn tất bình thường. Với API ngoài không hỗ trợ hủy, adapter vẫn cần cơ chế đóng listener hoặc tài nguyên tương ứng.

Không nên dùng **block()** hoặc **verifyComplete()** trên một Publisher never trong luồng kiểm thử thông thường vì thao tác sẽ chờ vô hạn. Hãy kiểm thử cancellation hoặc đặt timeout cho bài kiểm thử.

### 14. Kiểm thử empty, error và never bằng StepVerifier

Kiểm thử từng loại nguồn giúp xác nhận đúng terminal signal:

~~~java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.create(Mono.<String>empty())
    .verifyComplete();

StepVerifier.create(
        Mono.<String>error(new IllegalStateException("unavailable"))
    )
    .expectErrorMessage("unavailable")
    .verify();

StepVerifier.create(Mono.<String>never())
    .thenCancel()
    .verify();
~~~

Với nguồn empty, xác minh completion mà không có phần tử. Với nguồn error, xác minh lỗi. Với nguồn never, chủ động hủy subscription; không chờ completion.

Kiểm thử **zip** với nguồn rỗng:

~~~java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

Mono<?> zipped =
    Mono.zip(
        Mono.just("order-42"),
        Mono.<Integer>empty()
    );

StepVerifier.create(zipped)
    .verifyComplete();
~~~

Nếu nghiệp vụ cần giữ trạng thái thiếu dữ liệu, kiểm thử phiên bản dùng **singleOptional()**:

~~~java
import java.util.Optional;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.function.Tuple2;

import static org.junit.jupiter.api.Assertions.assertEquals;

Mono<Tuple2<Optional<String>, Optional<Integer>>> zipped =
    Mono.zip(
        Mono.just("order-42").singleOptional(),
        Mono.<Integer>empty().singleOptional()
    );

StepVerifier.create(zipped)
    .assertNext(tuple -> {
        assertEquals(Optional.of("order-42"), tuple.getT1());
        assertEquals(Optional.empty(), tuple.getT2());
    })
    .verifyComplete();
~~~

Kiểm thử này xác nhận zip tạo tuple chứa một giá trị có mặt và một giá trị vắng mặt được biểu diễn bằng **Optional.empty()**.

### 15. Kiểm thử merge và concat khi có never

Với **merge**, nguồn hữu hạn vẫn phát dữ liệu dù nguồn khác never, nhưng luồng không hoàn tất. Kiểm thử bằng cách nhận phần tử rồi hủy:

~~~java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

Flux<Integer> merged =
    Flux.merge(
        Flux.just(1, 2),
        Flux.<Integer>never()
    );

StepVerifier.create(merged)
    .expectNext(1, 2)
    .thenCancel()
    .verify();
~~~

Với **concat**, nguồn never đứng trước ngăn nguồn tiếp theo được đăng ký:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertFalse;

AtomicBoolean secondSubscribed = new AtomicBoolean();

Flux<Integer> sequence =
    Flux.concat(
        Flux.<Integer>never(),
        Flux.defer(() -> {
            secondSubscribed.set(true);
            return Flux.just(3);
        })
    );

StepVerifier.create(sequence)
    .thenCancel()
    .verify();

assertFalse(secondSubscribed.get());
~~~

Sau khi hủy subscription, cờ vẫn là **false**: nguồn thứ hai chưa được đăng ký vì nguồn đầu tiên chưa hoàn tất. Kiểm thử này xác nhận đặc tính tuần tự của **concat**.

### 16. Bảng quyết định khi thiết kế

| Tình huống | Câu hỏi cần trả lời | Hướng xử lý |
| --- | --- | --- |
| Một nguồn có thể empty | Thiếu dữ liệu là bình thường hay là lỗi nghiệp vụ? | Giữ empty, dùng **defaultIfEmpty**, **switchIfEmpty** hoặc **singleOptional** |
| Một nguồn có thể error | Có nguồn dự phòng hoặc kết quả lỗi riêng không? | **onErrorResume**, chuyển lỗi thành dữ liệu hoặc để lỗi kết thúc pipeline |
| Một nguồn có thể never | Khi nào nguồn phải phát hoặc kết thúc? | **timeout**, **take(Duration)**, cancellation hoặc giao thức đóng nguồn |
| Ghép bằng merge | Một nguồn lỗi có nên hủy các nguồn khác? | Chọn **merge** hoặc **mergeDelayError** |
| Ghép bằng concat | Có chấp nhận nguồn trước giữ các nguồn sau chờ không? | Giới hạn thời gian nguồn và thứ tự chuỗi |
| Ghép bằng zip | Mọi nguồn có bắt buộc phải có giá trị không? | Dùng **singleOptional** hoặc giá trị mặc định nếu cần tuple |
| Chờ nhiều tác vụ | Chỉ cần tất cả hoàn tất hay cần hợp nhất dữ liệu? | **Mono.when** hoặc **Mono.whenDelayError** |

Khi phối hợp Publisher trong Project Reactor, hãy xem empty là hoàn tất không có dữ liệu, error là terminal failure và never là không có tín hiệu để quyết định bước tiếp theo. **merge** ưu tiên phát dữ liệu từ các nguồn đang hoạt động; **concat** chờ từng nguồn theo thứ tự; **zip** cần giá trị từ mọi nguồn; **combineLatest** cần giá trị ban đầu từ tất cả nguồn; còn **when** chỉ quan tâm việc hoàn tất. Chọn đúng toán tử, bổ sung fallback hoặc giới hạn thời gian ở đúng nơi sẽ giúp pipeline **Mono**/**Flux** không bị chờ vô hạn, không bỏ mất ý nghĩa của dữ liệu thiếu và xử lý lỗi theo yêu cầu nghiệp vụ.
