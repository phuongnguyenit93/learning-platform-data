# Lỗi và phục hồi

## Xử lý ngay hoặc trì hoãn lỗi khi phối hợp nhiều nguồn

Một pipeline reactive thường phối hợp dữ liệu từ nhiều nguồn: gọi nhiều dịch vụ, đọc nhiều phân vùng, xử lý một danh sách sự kiện hoặc thực hiện nhiều tác vụ độc lập cùng lúc. Khi một nguồn phát lỗi, ứng dụng cần quyết định điều gì xảy ra với những nguồn còn lại. Pipeline nên dừng ngay để báo lỗi, hay tiếp tục thu thập các kết quả có thể nhận được rồi mới báo lỗi?

Project Reactor hỗ trợ cả hai cách. Các toán tử như **merge** và **flatMap** thường xử lý lỗi ngay (fail-fast): một lỗi được truyền xuống downstream và các nhánh còn hoạt động bị hủy. Những biến thể như **mergeDelayError** và **flatMapDelayError** trì hoãn việc truyền lỗi đến khi các nguồn hoặc nhánh liên quan kết thúc. Với các tác vụ chỉ quan tâm tín hiệu hoàn tất, **Mono.when** và **Mono.whenDelayError** cung cấp lựa chọn tương ứng.

Trì hoãn lỗi không có nghĩa là phục hồi thành công. Nó thay đổi thời điểm lỗi được chuyển đến subscriber để các nhánh khác có cơ hội hoàn tất. Subscriber cuối cùng vẫn nhận lỗi nếu có nguồn thất bại và không có bước phục hồi phía sau.

### 1. Bài toán khi phối hợp nhiều nguồn

Giả sử một màn hình tổng hợp trạng thái đơn hàng từ ba dịch vụ độc lập:

- Dịch vụ thanh toán trả về trạng thái giao dịch.
- Dịch vụ vận chuyển trả về trạng thái giao hàng.
- Dịch vụ kho trả về tình trạng chuẩn bị hàng.

Nếu dịch vụ thanh toán gặp lỗi ngay lập tức, có hai chính sách có thể chọn:

1. **Fail-fast:** dừng pipeline, hủy các yêu cầu còn lại và báo lỗi ngay khi nhận được lỗi đầu tiên.
2. **Delay error:** tiếp tục nhận kết quả từ các nguồn còn lại; khi tất cả nguồn đã kết thúc, mới chuyển lỗi xuống downstream.

Fail-fast phù hợp khi kết quả tổng hợp không còn hữu ích nếu thiếu một nguồn, hoặc cần giải phóng tài nguyên nhanh. Delay error phù hợp khi các kết quả thành phần vẫn có giá trị chẩn đoán hoặc cần thu thập đầy đủ trước khi quyết định bước tiếp theo.

Hai chính sách không thay thế yêu cầu thiết kế nghiệp vụ. Nếu màn hình có thể hiển thị trạng thái một phần, có thể chuyển lỗi riêng của từng nguồn thành một kết quả trạng thái lỗi thay vì để cả pipeline thất bại. Nếu kết quả phải đầy đủ và nhất quán, trì hoãn lỗi có thể giúp thu thập đủ phản hồi trước khi báo thất bại.

### 2. Xử lý lỗi ngay với merge

**Flux.merge** hợp nhất tín hiệu từ nhiều Publisher và mặc định truyền lỗi ngay khi một nguồn phát **onError**. Các nguồn còn hoạt động bị hủy khi lỗi được truyền xuống downstream.

~~~java
import reactor.core.publisher.Flux;

Flux<DashboardEvent> dashboard =
    Flux.merge(
        paymentClient.events(),
        shippingClient.events(),
        inventoryClient.events()
    );
~~~

Nếu **paymentClient.events()** phát lỗi, **dashboard** kết thúc bằng lỗi. Reactor hủy các subscription của các nguồn còn lại theo ngữ nghĩa fail-fast. Điều này giúp pipeline không tiếp tục tiêu thụ dữ liệu mà downstream đã không còn nhận.

Hủy subscription không phải là rollback. Nếu một dịch vụ khác đã hoàn tất thao tác ghi dữ liệu hoặc gửi thông báo trước khi lỗi được truyền đến, side effect đó vẫn có thể đã xảy ra. Cancellation chỉ yêu cầu các nguồn còn hoạt động ngừng tiếp tục phát; nó không thể tự đảo ngược công việc đã hoàn thành ở hệ thống bên ngoài.

### 3. Trì hoãn lỗi với mergeDelayError

**Flux.mergeDelayError** vẫn hợp nhất các nguồn, nhưng hoãn việc phát lỗi cho downstream cho đến khi các nguồn liên quan đã kết thúc. Trong thời gian đó, phần tử từ những nguồn còn hoạt động vẫn có thể được phát:

~~~java
import reactor.core.publisher.Flux;

Flux<DashboardEvent> dashboard =
    Flux.mergeDelayError(
        32,
        paymentClient.events(),
        shippingClient.events(),
        inventoryClient.events()
    );
~~~

Tham số **32** là prefetch được dùng trong cơ chế hợp nhất. Khi một nguồn lỗi, Reactor ghi nhận lỗi và tiếp tục xử lý những nguồn còn lại. Sau khi tất cả nguồn kết thúc, downstream nhận lỗi. Nếu chỉ có một nguồn lỗi, lỗi đó được chuyển xuống; nếu nhiều nguồn lỗi, Reactor có thể tổng hợp các lỗi thành một lỗi tổng hợp.

Điều này có nghĩa subscriber có thể nhận một số phần tử từ các nguồn khác sau khi lỗi đầu tiên đã xảy ra upstream. Tuy nhiên, pipeline vẫn kết thúc bằng lỗi sau khi các nguồn hoàn tất. Nếu downstream chỉ cần kết quả thành công, nó sẽ không nhận được tín hiệu **onComplete** trong trường hợp có lỗi chưa được phục hồi.

### 4. Khi nào delay error có ích?

Delay error hữu ích khi cần cho các nguồn độc lập có cơ hội hoàn thành:

- Thu thập nhiều kết quả kiểm tra trước khi tạo báo cáo lỗi.
- Gửi nhiều lệnh ghi độc lập và chờ tất cả hoàn tất để biết tác vụ nào thất bại.
- Hợp nhất các luồng sự kiện mà một nguồn lỗi không nên làm mất ngay những dữ liệu cuối cùng từ nguồn khác.
- Thực hiện nhiều bước dọn dẹp hoặc tác vụ kết thúc mà cần ghi nhận lỗi từ nhiều nhánh.

Không nên trì hoãn lỗi nếu các nhánh còn lại tiêu thụ tài nguyên lớn, kết quả của chúng không còn giá trị hoặc hệ thống cần dừng càng sớm càng tốt. Cũng cần tránh delay error trên một nguồn không có giới hạn thời gian và có thể không bao giờ kết thúc; khi đó lỗi đã ghi nhận có thể không bao giờ được chuyển đến downstream.

### 5. flatMap và flatMapDelayError

Khi mỗi phần tử nguồn tạo ra một Publisher con, **flatMap** mặc định áp dụng chính sách fail-fast. Nếu một Publisher con lỗi, pipeline có thể hủy các nhánh con còn lại và truyền lỗi xuống:

~~~java
import reactor.core.publisher.Flux;

Flux<OrderDetails> details =
    orderIds.flatMap(id ->
        orderClient.findDetails(id)
    );
~~~

Nếu muốn các Publisher con đang hoạt động tiếp tục trước khi báo lỗi, dùng **flatMapDelayError**:

~~~java
import reactor.core.publisher.Flux;

Flux<OrderDetails> details =
    orderIds.flatMapDelayError(
        id -> orderClient.findDetails(id),
        8,
        16
    );
~~~

Trong ví dụ:

- **8** là concurrency tối đa của các Publisher con được đăng ký đồng thời.
- **16** là prefetch được dùng cho mỗi Publisher con.

Nếu một yêu cầu tra cứu lỗi, toán tử ghi nhận lỗi và vẫn cho các nhánh đang hoạt động khác phát kết quả. Lỗi được chuyển xuống sau khi các nhánh liên quan hoàn tất. Concurrency và prefetch vẫn cần được giới hạn theo khả năng của dịch vụ ngoài và ngân sách bộ nhớ.

Delay error không bảo đảm mọi phần tử nguồn sẽ được xử lý trong mọi tình huống. Nếu nguồn ngoài cũng lỗi, nó không thể phát thêm phần tử để tạo nhánh mới. Toán tử trì hoãn lỗi của các nhánh con không biến một nguồn đầu vào đã kết thúc do lỗi thành nguồn tiếp tục phát dữ liệu.

### 6. Xử lý lỗi ở từng nhánh trước khi hợp nhất

Fail-fast hoặc delay error là chính sách ở cấp phối hợp. Một lựa chọn khác là xử lý lỗi ngay trong Publisher con để lỗi của một nguồn được chuyển thành kết quả nghiệp vụ, rồi các nhánh còn lại tiếp tục như bình thường.

Ví dụ, nếu không tìm thấy chi tiết của một đơn hàng thì có thể bỏ qua đơn đó:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<OrderDetails> details =
    orderIds.flatMap(id ->
        orderClient.findDetails(id)
            .onErrorResume(
                OrderNotFoundException.class,
                error -> {
                    log.info("Bỏ qua đơn hàng không tồn tại: {}", id);
                    return Mono.empty();
                }
            ),
        8
    );
~~~

Lỗi **OrderNotFoundException** được xử lý bên trong nhánh của đơn hàng tương ứng. Nhánh đó hoàn tất rỗng; các nhánh khác tiếp tục. Nếu lỗi thuộc loại khác, nó vẫn truyền ra ngoài và có thể khiến **flatMap** kết thúc theo chính sách fail-fast mặc định.

Nếu muốn giữ thông tin thất bại thay vì bỏ qua, hãy chuyển mỗi nhánh thành một kiểu kết quả biểu diễn cả thành công và lỗi:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record LookupResult(
    String orderId,
    OrderDetails details,
    Throwable failure
) {}

Flux<LookupResult> results =
    orderIds.flatMap(id ->
        orderClient.findDetails(id)
            .map(details -> new LookupResult(id, details, null))
            .onErrorResume(error ->
                Mono.just(new LookupResult(id, null, error))
            ),
        8
    );
~~~

Ở đây, lỗi được chuyển thành dữ liệu. Luồng ngoài có thể hoàn tất bình thường sau khi mọi nhánh kết thúc, nhưng consumer vẫn biết đơn hàng nào thất bại. Cách này khác với delay error: lỗi không còn là terminal signal của toàn bộ pipeline, vì nó đã được chuyển thành một phần tử kết quả.

Chỉ chuyển lỗi thành dữ liệu khi kiểu kết quả thể hiện rõ trạng thái thất bại và consumer có chính sách xử lý. Nếu âm thầm dùng **onErrorResume** để trả về danh sách rỗng, lỗi nghiêm trọng có thể bị che khuất và ứng dụng báo thành công dù dữ liệu không đầy đủ.

### 7. Phối hợp các tác vụ chỉ cần hoàn tất với whenDelayError

Đôi khi các Publisher không phát giá trị cần hợp nhất; ứng dụng chỉ cần biết tất cả tác vụ đã hoàn tất hay có tác vụ nào thất bại. **Mono.when** kết hợp các Publisher theo kiểu này và mặc định truyền lỗi ngay. **Mono.whenDelayError** trì hoãn lỗi đến khi các Publisher đã kết thúc:

~~~java
import reactor.core.publisher.Mono;

Mono<Void> completion =
    Mono.whenDelayError(
        auditService.writeRecord(event),
        notificationService.send(event),
        metricsService.record(event)
    );
~~~

Các tác vụ được đăng ký để chạy cùng nhau. Nếu ghi audit thất bại, Reactor vẫn chờ các tác vụ gửi thông báo và ghi metric kết thúc. Sau đó, **completion** mới phát completion hoặc lỗi tổng hợp nếu có lỗi.

So sánh với **Mono.when**:

~~~java
import reactor.core.publisher.Mono;

Mono<Void> failFast =
    Mono.when(
        auditService.writeRecord(event),
        notificationService.send(event)
    );

Mono<Void> waitForAll =
    Mono.whenDelayError(
        auditService.writeRecord(event),
        notificationService.send(event)
    );
~~~

**when** phù hợp khi một lỗi khiến các tác vụ còn lại không cần tiếp tục. **whenDelayError** phù hợp khi muốn chờ các tác vụ độc lập kết thúc để thu thập kết quả lỗi đầy đủ hơn. Cả hai đều không tạo một giao dịch phân tán và không rollback side effect đã hoàn thành.

### 8. Nhiều lỗi được báo cáo như thế nào?

Nếu nhiều nguồn cùng lỗi trong một phép phối hợp delay error, Reactor có thể gói các lỗi thành một lỗi tổng hợp. Vì vậy, không nên giả định downstream luôn nhận đúng một exception gốc hoặc chỉ cần kiểm tra một message.

Ở tầng ứng dụng, nên ghi log lỗi tại nhánh có đủ ngữ cảnh như ID đơn hàng, tên dịch vụ hoặc correlation ID. Lỗi tổng hợp ở downstream cho biết phép phối hợp thất bại; log tại từng nhánh giúp xác định nguồn nào đã gây ra lỗi.

Ví dụ:

~~~java
import reactor.core.publisher.Flux;

Flux<Result> results =
    Flux.mergeDelayError(16, sourceA, sourceB)
        .doOnError(error ->
            log.error("Các nguồn phối hợp đã kết thúc với lỗi", error)
        );
~~~

Nếu cần phân tích từng lỗi thành phần, hãy dùng tiện ích xử lý exception của Reactor phù hợp với phiên bản thư viện đang dùng để tách các lỗi đã tổng hợp. Tránh phụ thuộc vào cách định dạng message của lỗi tổng hợp; cấu trúc exception và danh sách lỗi thành phần mới là dữ liệu cần kiểm tra.

### 9. Retry ở trong nhánh hay sau phép hợp nhất?

Vị trí đặt retry thay đổi phạm vi thực thi lại:

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.util.retry.Retry;

Flux<OrderDetails> retryEachOrder =
    orderIds.flatMap(id ->
        orderClient.findDetails(id)
            .retryWhen(Retry.backoff(2, Duration.ofMillis(100))),
        8
    );
~~~

Trong ví dụ này, mỗi Publisher con tự thử lại tối đa hai lần theo chính sách backoff. Lỗi chỉ thoát khỏi nhánh nếu các lần thử đều thất bại. Các nhánh khác vẫn được xử lý theo chính sách của **flatMap**.

Nếu đặt retry sau phép hợp nhất:

~~~java
Flux<OrderDetails> retryWholePipeline =
    orderIds.flatMap(id -> orderClient.findDetails(id), 8)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100)));
~~~

Khi lỗi thoát khỏi **flatMap**, retry downstream có thể đăng ký lại toàn bộ pipeline upstream. Những yêu cầu đã thành công trước đó có thể được thực hiện lại. Điều này có thể lặp truy vấn, ghi dữ liệu hoặc side effect của các nhánh đã hoàn tất.

Hãy đặt retry ở phạm vi nhỏ nhất có thể phục hồi độc lập. Với thao tác ghi hoặc gửi yêu cầu có tác dụng phụ, cần bảo đảm tính idempotent hoặc dùng khóa idempotency ổn định. Retry không phải là cơ chế rollback và cũng không thay thế việc xử lý lỗi cuối cùng.

### 10. Delay error và nguồn không bao giờ kết thúc

Một rủi ro của chính sách trì hoãn lỗi là lỗi chỉ được chuyển xuống khi các nguồn liên quan kết thúc. Nếu một nguồn là **Flux.never()**, hoặc một kết nối sự kiện có thể mở vô thời hạn, lỗi từ nguồn khác có thể bị giữ lại mãi.

Ví dụ:

~~~java
import reactor.core.publisher.Flux;

Flux<Integer> combined =
    Flux.mergeDelayError(
        8,
        Flux.error(new IllegalStateException("source failed")),
        Flux.never()
    );
~~~

Nguồn thứ nhất lỗi ngay, nhưng nguồn thứ hai không phát tín hiệu kết thúc. Vì vậy, downstream không nhận được lỗi tổng hợp trong thời gian hữu hạn. Trong ứng dụng thực tế, hãy đặt timeout hoặc chính sách đóng nguồn cho các nhánh có thời gian sống không xác định.

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;

Flux<Event> boundedSource =
    eventClient.events()
        .timeout(Duration.ofSeconds(30));
~~~

Timeout biến việc không có tín hiệu trong thời gian quy định thành lỗi. Khi dùng cùng delay error, timeout giúp nguồn cuối cùng cũng kết thúc, để lỗi được chuyển xuống. Cần chọn timeout phù hợp với đặc tính nguồn; một luồng sự kiện bình thường có thể im lặng lâu mà không phải là lỗi.

### 11. Backpressure và cancellation vẫn có hiệu lực

Delay error không vô hiệu hóa backpressure. Downstream vẫn điều khiển demand; các toán tử phối hợp vẫn quản lý prefetch và hàng đợi theo cấu hình. Nếu downstream chậm, dữ liệu từ các nhánh còn hoạt động có thể phải chờ trong các vùng đệm. Vì vậy, giới hạn concurrency và prefetch vẫn quan trọng.

Cancellation từ downstream cũng vẫn có ý nghĩa. Nếu subscriber không còn cần kết quả và hủy subscription, các nguồn còn hoạt động sẽ nhận yêu cầu hủy theo cấu trúc pipeline. Delay error không buộc Reactor phải tiếp tục tiêu thụ tất cả dữ liệu sau khi subscriber đã hủy.

Với nguồn ngoài không hỗ trợ cancellation đúng cách, adapter cần có chính sách dừng, đóng listener hoặc giải phóng kết nối. Hãy gắn cleanup với vòng đời subscription để tránh giữ tài nguyên sau khi pipeline kết thúc hoặc bị hủy.

### 12. Kiểm thử fail-fast và delay error bằng StepVerifier

Kiểm thử nên xác nhận cả phần tử được phát và thời điểm lỗi được chuyển đến downstream. Ví dụ fail-fast:

~~~java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

IllegalStateException failure =
    new IllegalStateException("source A failed");

Flux<Integer> failFast =
    Flux.merge(
        Flux.<Integer>error(failure),
        Flux.<Integer>never()
    );

StepVerifier.create(failFast)
    .expectErrorMessage("source A failed")
    .verify();
~~~

Với **merge**, lỗi được chuyển xuống ngay; Publisher không bao giờ kết thúc còn lại không giữ pipeline chờ vô hạn.

Kiểm thử delay error:

~~~java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

Flux<Integer> delayedError =
    Flux.mergeDelayError(
        8,
        Flux.<Integer>error(
            new IllegalStateException("source A failed")
        ),
        Flux.just(10, 20)
    );

StepVerifier.create(delayedError)
    .expectNext(10, 20)
    .expectErrorMessage("source A failed")
    .verify();
~~~

Nguồn thứ nhất lỗi, nhưng nguồn thứ hai vẫn phát 10 và 20. Sau khi cả hai nguồn kết thúc, StepVerifier nhận lỗi đã được trì hoãn. Kiểm thử này làm rõ rằng delay error vẫn kết thúc bằng lỗi dù các phần tử từ nhánh khác đã được chuyển xuống.

Có thể kiểm tra **flatMapDelayError** tương tự:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

Flux<Integer> delayedInnerError =
    Flux.just(1, 2, 3)
        .flatMapDelayError(
            value -> value == 2
                ? Mono.error(new IllegalArgumentException("bad item"))
                : Mono.just(value * 10),
            3,
            1
        );

StepVerifier.create(delayedInnerError)
    .expectNextCount(2)
    .expectErrorMessage("bad item")
    .verify();
~~~

Hai nhánh thành công phát kết quả, nhánh thứ hai lỗi, và lỗi chỉ được truyền sau khi các nhánh liên quan hoàn tất. Không nên kiểm tra thứ tự hai phần tử nếu pipeline có xử lý đồng thời và thứ tự không phải một phần hợp đồng.

### 13. Chọn chính sách lỗi theo yêu cầu nghiệp vụ

| Yêu cầu | Cách tiếp cận phù hợp |
| --- | --- |
| Dừng ngay khi một nguồn thất bại | **merge**, **flatMap**, **Mono.when** |
| Chờ các nguồn kết thúc rồi mới báo lỗi | **mergeDelayError**, **flatMapDelayError**, **Mono.whenDelayError** |
| Một nhánh lỗi nhưng các nhánh khác vẫn hoàn tất bình thường | Phục hồi trong Publisher con bằng **onErrorResume** hoặc chuyển lỗi thành kiểu kết quả |
| Thử lại riêng nguồn có thể phục hồi | Đặt **retryWhen** bên trong nhánh |
| Chờ nguồn có thể im lặng vô thời hạn | Dùng **timeout** hoặc chính sách đóng nguồn trước khi trì hoãn lỗi |
| Thu thập nhiều lỗi thành phần | Dùng delay error và ghi log ngữ cảnh tại từng nhánh |

Trước khi chọn toán tử, hãy xác định:

- Kết quả của một nguồn lỗi có làm toàn bộ kết quả mất ý nghĩa không?
- Các nguồn còn lại có tạo ra dữ liệu hữu ích sau khi một nguồn thất bại không?
- Có cần ghi nhận tất cả lỗi thành phần hay chỉ cần lỗi đầu tiên?
- Các nguồn có giới hạn thời gian và hỗ trợ cancellation không?
- Retry có thể lặp side effect hoặc toàn bộ pipeline không?
- Có thể chuyển lỗi riêng thành một kết quả nghiệp vụ thay vì làm thất bại toàn bộ luồng không?

Trong module REACTIVE_PROGRAMMING, phối hợp nhiều Publisher không chỉ là chọn cách hợp nhất dữ liệu. Chính sách lỗi quyết định nguồn nào tiếp tục chạy, subscriber nhận những phần tử nào trước terminal signal và tài nguyên được giải phóng khi nào. Dùng fail-fast khi cần dừng nhanh; dùng delay error khi cần chờ các nguồn độc lập hoàn tất; và phục hồi tại từng nhánh khi nghiệp vụ có thể biểu diễn thất bại như một kết quả riêng. Những lựa chọn rõ ràng này giúp pipeline **Mono**/**Flux** có hành vi dự đoán được khi nhiều nguồn hoạt động bất đồng bộ.
