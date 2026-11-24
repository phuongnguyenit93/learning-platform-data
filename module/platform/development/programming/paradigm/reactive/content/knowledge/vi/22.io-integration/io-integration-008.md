# Chuyển đổi CompletableFuture mà không chặn để lấy kết quả

Java có nhiều API bất đồng bộ dựa trên `CompletableFuture`. Một thư viện cũ có thể trả về future cho thao tác HTTP, truy vấn dữ liệu hoặc tính toán nền, trong khi phần còn lại của ứng dụng đang dùng Project Reactor với `Mono` và `Flux`. Khi kết hợp hai mô hình, ta cần chuyển đổi kết quả mà không gọi `get()` hoặc `join()` để chờ thread hiện tại.

Reactor cung cấp `Mono.fromFuture` để đưa `CompletableFuture` vào pipeline reactive và `Mono.toFuture` để chuyển một `Mono` thành future khi phải giao tiếp với API imperative. Việc chuyển đổi cần làm rõ thời điểm thao tác bắt đầu, cách chia sẻ kết quả, xử lý giá trị rỗng, lỗi, cancellation và thread thực thi.

Các kiểu `User`, `Order`, `Dashboard` và client trong ví dụ là kiểu miền minh họa do ứng dụng định nghĩa.

## 1. Vì sao không dùng get() hoặc join() trong pipeline?

`CompletableFuture.get()` và `join()` chờ kết quả. Nếu gọi chúng trên event loop hoặc thread đang xử lý một pipeline reactive, thread đó bị giữ lại cho đến khi future hoàn tất. Khi nhiều request cùng chờ, số thread bị chiếm có thể tăng và làm giảm khả năng phục vụ của ứng dụng.

Ví dụ sau chặn thread gọi:

~~~java
CompletableFuture<User> future = legacyClient.findUserAsync(userId);
User user = future.join();

return Mono.just(user);
~~~

Mặc dù nguồn dữ liệu là bất đồng bộ, lời gọi `join()` đã biến đoạn mã thành thao tác chờ đồng bộ. Cách làm này có thể gây nghẽn event loop trong Spring WebFlux hoặc chiếm worker thread không cần thiết.

Hãy chuyển future thành Mono để pipeline đăng ký nhận kết quả khi future hoàn tất:

~~~java
Mono<User> user = Mono.fromFuture(
    legacyClient.findUserAsync(userId)
);
~~~

`Mono.fromFuture` không chờ future bằng cách giữ thread gọi. Nó đăng ký callback để nhận kết quả khi future hoàn tất và phát giá trị hoặc lỗi qua giao thức Reactive Streams.

## 2. Chuyển CompletableFuture thành Mono bằng fromFuture

Một `CompletableFuture<T>` đại diện cho tối đa một kết quả trong tương lai. Vì vậy, kiểu tương ứng trong Reactor thường là `Mono<T>`.

~~~java
import java.util.concurrent.CompletableFuture;
import reactor.core.publisher.Mono;

CompletableFuture<User> future =
    legacyClient.findUserAsync(userId);

Mono<User> user = Mono.fromFuture(future);
~~~

Khi future hoàn tất thành công với một giá trị, Mono phát giá trị đó rồi hoàn tất. Khi future hoàn tất ngoại lệ, Mono phát `onError`. Nếu future hoàn tất thành công với `null`, Mono không phát `onNext(null)`; nó hoàn tất rỗng vì Reactive Streams không cho phép phát null.

Cần phân biệt việc bọc future đã tồn tại với việc tạo future khi có subscription:

- `Mono.fromFuture(future)` nhận một future đã được tạo. Nếu lời gọi tạo future khởi động I/O ngay lập tức, công việc có thể đã bắt đầu trước khi Mono được subscribe.
- `Mono.fromFuture(() -> createFuture())` nhận một supplier. Supplier được gọi khi có subscription, giúp trì hoãn việc tạo future đến đúng thời điểm tiêu thụ.

Ví dụ dùng supplier:

~~~java
Mono<User> user = Mono.fromFuture(
    () -> legacyClient.findUserAsync(userId)
);
~~~

Cách này phù hợp khi muốn giữ tính lazy của pipeline. Mỗi subscription có thể tạo một future riêng và thực hiện một lần gọi độc lập, tùy theo hành vi của client.

## 3. Lazy và eager: thời điểm thao tác bắt đầu

Trong Reactor, việc xây dựng pipeline thường chưa bắt đầu I/O cho đến khi có subscription. Nhưng nhiều API CompletableFuture khởi động công việc ngay khi gọi phương thức trả về future.

Ví dụ:

~~~java
CompletableFuture<User> future =
    legacyClient.findUserAsync(userId); // Công việc có thể bắt đầu tại đây.

Mono<User> user = Mono.fromFuture(future); // Chỉ bọc future đã chạy.
~~~

Nếu muốn thao tác chỉ bắt đầu khi có subscriber:

~~~java
Mono<User> user = Mono.fromFuture(
    () -> legacyClient.findUserAsync(userId)
);
~~~

Điều này có ý nghĩa khi pipeline được tạo trước, lưu vào biến hoặc chỉ chạy khi một request thực sự được xử lý.

Supplier cũng ảnh hưởng đến số lần gọi:

~~~java
Mono<User> lazyUser = Mono.fromFuture(
    () -> legacyClient.findUserAsync(userId)
);
~~~

Nếu hai Subscriber đăng ký độc lập vào `lazyUser`, supplier có thể được gọi hai lần và tạo hai future. Nếu muốn nhiều Subscriber dùng chung một kết quả, có thể chia sẻ Mono:

~~~java
Mono<User> sharedUser = Mono.fromFuture(
        () -> legacyClient.findUserAsync(userId)
    )
    .cache();
~~~

`cache()` chia sẻ kết quả và giữ tín hiệu để phát lại theo semantics của cache. Hãy dùng khi việc dùng chung kết quả là chủ ý và có chính sách vòng đời phù hợp. Với dữ liệu cần cập nhật theo request hoặc theo thời gian, không nên cache vô hạn chỉ để tránh gọi API nhiều lần.

Ngược lại, nếu dùng `Mono.fromFuture(future)` với cùng một future rồi subscribe nhiều lần, các subscriber cùng quan sát một công việc future đã được tạo. Cần cân nhắc cancellation: một subscriber hủy có thể làm future dùng chung bị cancel theo mặc định, ảnh hưởng subscriber khác.

Nếu chủ ý chia sẻ một future giữa nhiều subscriber và không muốn cancellation từ một subscriber hủy future chung, Reactor có overload nhận cờ `suppressCancel`:

~~~java
Mono<User> shared = Mono.fromFuture(sharedFuture, true);
~~~

Khi đó, việc hủy một subscription không truyền lệnh cancel xuống future. Ứng dụng vẫn cần một thành phần sở hữu vòng đời và quyết định khi nào công việc dùng chung được kết thúc.

## 4. Kết hợp nhiều CompletableFuture độc lập

Nếu nhiều API trả về future độc lập, có thể chuyển từng future thành Mono rồi dùng `Mono.zip`. Cách này giữ pipeline ở dạng reactive và không cần gọi `join()` để lấy từng kết quả.

~~~java
import java.util.List;
import reactor.core.publisher.Mono;

record Dashboard(User user, List<Order> orders) {}

Mono<Dashboard> dashboard = Mono.zip(
    Mono.fromFuture(() -> userClient.findUserAsync(userId)),
    Mono.fromFuture(() -> orderClient.findOrdersAsync(userId)),
    Dashboard::new
);
~~~

Hai supplier được gọi khi có subscription. Các future có thể chạy đồng thời tùy theo client và executor mà chúng sử dụng. Khi cả hai Mono đều có giá trị, hàm kết hợp tạo Dashboard.

Nếu muốn giữ toàn bộ logic trong CompletableFuture trước khi chuyển sang Reactor, có thể dùng `thenCombine`:

~~~java
CompletableFuture<Dashboard> dashboardFuture =
    userClient.findUserAsync(userId)
        .thenCombine(
            orderClient.findOrdersAsync(userId),
            Dashboard::new
        );

Mono<Dashboard> dashboard = Mono.fromFuture(dashboardFuture);
~~~

`thenCombine` kết hợp kết quả của hai future khi cả hai hoàn tất thành công. Cả hai cách đều không cần chặn thread. Chọn cách đầu nếu phần tiếp theo của ứng dụng dùng Reactor; chọn cách sau nếu đang tích hợp một API vốn đã điều phối bằng CompletableFuture.

Không dùng `allOf(...).join()` trong một pipeline reactive để chờ nhiều future. Nếu đã ở Reactor, `Mono.zip` thường thể hiện trực tiếp ý định kết hợp các kết quả đơn.

## 5. Kết hợp các thao tác phụ thuộc

Nếu future thứ hai cần dữ liệu do future thứ nhất trả về, hãy dùng `flatMap` sau khi chuyển future đầu tiên thành Mono:

~~~java
Mono<OrderDetails> details =
    Mono.fromFuture(() -> orderClient.findOrderAsync(orderId))
        .flatMap(order ->
            Mono.fromFuture(
                () -> customerClient.findCustomerAsync(order.customerId())
            ).map(customer ->
                new OrderDetails(order, customer)
            )
        );
~~~

Thao tác tải khách hàng chỉ được tạo sau khi đã nhận được đơn hàng và biết `customerId`. `flatMap` giữ quan hệ phụ thuộc trong pipeline mà không cần chờ bằng `get()`.

Nếu vẫn ở trong API CompletableFuture, toán tử tương ứng thường là `thenCompose`:

~~~java
CompletableFuture<OrderDetails> detailsFuture =
    orderClient.findOrderAsync(orderId)
        .thenCompose(order ->
            customerClient.findCustomerAsync(order.customerId())
                .thenApply(customer ->
                    new OrderDetails(order, customer)
                )
        );

Mono<OrderDetails> details = Mono.fromFuture(detailsFuture);
~~~

`thenApply` biến đổi một kết quả đồng bộ; `thenCompose` nối một thao tác trả về future khác. Trong Reactor, `map` và `flatMap` biểu đạt hai ý định tương ứng.

## 6. Chuyển Mono thành CompletableFuture bằng toFuture

Khi một thư viện hoặc tầng tích hợp chỉ chấp nhận CompletableFuture, có thể chuyển Mono bằng `toFuture()`:

~~~java
Mono<User> user = userRepository.findById(userId);

CompletableFuture<User> userFuture = user.toFuture();
~~~

Lời gọi `toFuture()` đăng ký vào Mono và trả về một future đại diện cho kết quả. Vì vậy, đây là ranh giới kích hoạt pipeline: khi gọi `toFuture()`, quá trình tiêu thụ bắt đầu.

Các trường hợp kết thúc được ánh xạ như sau:

| Kết quả Mono | Kết quả CompletableFuture |
|---|---|
| Phát một giá trị rồi hoàn tất | Future hoàn tất thành công với giá trị đó. |
| Hoàn tất rỗng | Future hoàn tất thành công với `null`. |
| Phát lỗi | Future hoàn tất ngoại lệ với lỗi tương ứng. |
| Future bị cancel | Subscription Reactor được yêu cầu hủy. |

CompletableFuture không có biểu diễn riêng cho trạng thái “hoàn tất nhưng không có giá trị”. Nếu cần giữ khác biệt giữa có và không có dữ liệu, hãy chuyển sang Optional:

~~~java
CompletableFuture<Optional<User>> userFuture =
    userRepository.findById(userId)
        .map(Optional::of)
        .defaultIfEmpty(Optional.empty())
        .toFuture();
~~~

Cách này giúp caller phân biệt `Optional.empty()` với một lỗi. Tránh dùng null như một quy ước nghiệp vụ nếu có thể biểu diễn trạng thái rõ ràng hơn.

## 7. Cancellation và quyền sở hữu công việc

Cancellation cần được xem xét ở cả hai chiều chuyển đổi.

Khi dùng `Mono.fromFuture`, nếu subscriber hủy, Reactor mặc định truyền yêu cầu cancel đến CompletableFuture. Tuy nhiên, `CompletableFuture.cancel(true)` không bảo đảm thread đang chạy bị interrupt hoặc thao tác I/O bên dưới dừng ngay lập tức. Khả năng dừng thực tế phụ thuộc vào cách client triển khai future và liệu nó có hỗ trợ hủy request hay không.

Khi dùng `Mono.toFuture()`, nếu caller hủy future được trả về, Reactor yêu cầu hủy subscription tương ứng. Điều này giúp truyền cancellation ngược vào pipeline, nhưng cũng cần nguồn hỗ trợ cancellation để dừng công việc thực tế.

Ví dụ với một request có thể bị hủy khi client ngắt kết nối:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;

Mono<Response> response = Mono.fromFuture(
    () -> legacyClient.callAsync(request)
);

return response
    .timeout(Duration.ofSeconds(3))
    .onErrorMap(TimeoutException.class,
        error -> new UpstreamTimeoutException(error));
~~~

Khi timeout, Reactor kết thúc nhánh bằng lỗi timeout và yêu cầu hủy upstream. Nếu future/client hỗ trợ cancellation, request ngoài có thể được dừng. Nếu client chỉ đánh dấu future là cancelled mà vẫn tiếp tục I/O, tài nguyên bên dưới có thể vẫn được sử dụng cho đến khi thao tác tự kết thúc.

Đừng xem cancellation của future là bằng chứng chắc chắn rằng server đích đã dừng xử lý. Với thao tác có side effect, hãy thiết kế idempotency key hoặc cơ chế kiểm tra trạng thái nếu cần xử lý trường hợp caller timeout nhưng hệ thống đích vẫn hoàn tất.

## 8. Lỗi từ CompletableFuture trong pipeline Reactor

Một future có thể hoàn tất bằng exception. Khi chuyển sang Mono, lỗi trở thành `onError`, vì vậy có thể dùng các toán tử Reactor quen thuộc:

~~~java
Mono<User> user = Mono.fromFuture(
        () -> userClient.findUserAsync(userId)
    )
    .onErrorMap(error ->
        new UserLookupException("Không thể tải người dùng", error)
    );
~~~

Nếu có giá trị dự phòng hợp lệ, dùng `onErrorResume`:

~~~java
Mono<User> user = Mono.fromFuture(
        () -> userClient.findUserAsync(userId)
    )
    .onErrorResume(error -> {
        log.warn("Không tải được người dùng {}", userId, error);
        return Mono.just(User.anonymous());
    });
~~~

Chỉ dùng giá trị dự phòng khi nghiệp vụ cho phép. Nếu lỗi là lỗi xác thực hoặc dữ liệu bắt buộc, chuyển thành người dùng mặc định có thể che giấu vấn đề.

Một số API future bọc nguyên nhân trong `CompletionException` hoặc `ExecutionException`. Hãy xem cause chain khi ghi log và chuẩn hóa lỗi ở một nơi nếu ứng dụng cần phân loại thống nhất. Không nên giả định mọi thư viện đều bọc lỗi theo cùng một cách.

Nếu thao tác có timeout ở tầng future, có thể chuyển lỗi đó thành lỗi miền ở Reactor. Tránh đặt timeout ở nhiều tầng mà không có chính sách rõ ràng, vì mỗi tầng có thể hủy hoặc kết thúc ở thời điểm khác nhau.

## 9. Giá trị null và Mono rỗng

Reactive Streams không cho phép `onNext(null)`. Vì vậy, nếu CompletableFuture hoàn tất thành công với `null`, `Mono.fromFuture` biểu diễn kết quả đó bằng `Mono.empty()`.

~~~java
CompletableFuture<User> future =
    CompletableFuture.completedFuture(null);

Mono<User> user = Mono.fromFuture(future);
~~~

Có thể xử lý kết quả rỗng bằng `switchIfEmpty`:

~~~java
Mono<User> user = Mono.fromFuture(
        () -> userClient.findUserAsync(userId)
    )
    .switchIfEmpty(Mono.error(
        new UserNotFoundException(userId)
    ));
~~~

Hãy xác định ý nghĩa của null trong API cũ. Nó có thể có nghĩa không tìm thấy dữ liệu, không có nội dung hoặc là lỗi thiết kế của API. Chuyển nó thành `Mono.empty()` là hành vi kỹ thuật; quyết định nghiệp vụ nên được thể hiện rõ ở tầng gọi.

Ở chiều ngược lại, `Mono.empty().toFuture()` hoàn tất future thành công với null. Nếu caller cần biết trạng thái rỗng, dùng Optional như phần trước.

## 10. Thread và Executor khi chuyển đổi

CompletableFuture thường dùng executor do thư viện tạo future chỉ định. Các phương thức `thenApply` không có hậu tố Async có thể chạy trên thread hoàn tất future hoặc thread đăng ký continuation, tùy trạng thái và cách hoàn tất. `thenApplyAsync` cho phép chọn executor cho continuation.

Khi chuyển future thành Mono, callback nhận kết quả có thể chạy trên thread hoàn tất future. Các toán tử đồng bộ phía sau có thể chạy trên thread đó cho đến khi có ranh giới scheduler.

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<String> result = Mono.fromFuture(
        () -> legacyClient.fetchAsync(id)
    )
    .publishOn(Schedulers.parallel())
    .map(this::cpuIntensiveTransform);
~~~

`publishOn` chuyển các toán tử phía sau sang scheduler được chỉ định. Đây là cách tách bước xử lý CPU khỏi thread hoàn tất future.

Nếu supplier tạo một future từ API chặn, có thể chuyển thời điểm gọi supplier sang `boundedElastic`:

~~~java
import java.util.concurrent.CompletableFuture;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<User> user = Mono.fromFuture(
        () -> CompletableFuture.completedFuture(
            legacyBlockingClient.findUser(userId)
        )
    )
    .subscribeOn(Schedulers.boundedElastic());
~~~

Ví dụ trên minh họa vị trí thực thi supplier, nhưng nếu API chặn thì cách rõ ràng hơn thường là dùng `Mono.fromCallable` với `subscribeOn(boundedElastic())`, vì không cần tạo CompletableFuture chỉ để bọc một lời gọi đồng bộ:

~~~java
Mono<User> user = Mono.fromCallable(
        () -> legacyBlockingClient.findUser(userId)
    )
    .subscribeOn(Schedulers.boundedElastic());
~~~

`subscribeOn` có thể ảnh hưởng nơi supplier của `fromFuture` được gọi; nó không thay đổi executor mà thư viện future dùng cho công việc đã khởi chạy. `publishOn` điều khiển nơi các toán tử phía sau xử lý tín hiệu. Hãy chọn đúng ranh giới thay vì thêm scheduler tùy tiện.

## 11. Không tạo subscription phụ bằng subscribe

Khi đã có Mono từ future, hãy tiếp tục kết hợp pipeline và để ranh giới ứng dụng quyết định cách tiêu thụ:

~~~java
Mono<OrderView> view = Mono.fromFuture(
        () -> orderClient.findOrderAsync(orderId)
    )
    .flatMap(order ->
        Mono.fromFuture(
            () -> inventoryClient.checkAsync(order.productId())
        ).map(stock -> new OrderView(order, stock))
    );
~~~

Không nên gọi `subscribe()` bên trong một phương thức nghiệp vụ chỉ để lấy kết quả rồi trả về `void` hoặc một biến đã thay đổi:

~~~java
void loadOrder(String orderId) {
    Mono.fromFuture(() -> orderClient.findOrderAsync(orderId))
        .subscribe(order -> this.currentOrder = order);
}
~~~

Cách này tạo subscription tách rời, caller không thể kết hợp lỗi, cancellation hoặc vòng đời của nó. Hãy trả `Mono<Order>` hoặc `CompletableFuture<Order>` theo hợp đồng của tầng gọi. Chỉ chuyển sang future ở ranh giới thực sự cần API đó.

## 12. Kiểm thử chuyển đổi bằng StepVerifier

`StepVerifier` kiểm tra hành vi của Mono tạo từ future mà không cần chờ bằng `get()` hoặc `join()`.

Các phương thức kiểm thử dưới đây thuộc cùng một test class và dùng chung các import sau:

~~~java
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.Exceptions;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
~~~

Kiểm thử future hoàn tất thành công:

~~~java
@Test
void fromFuturePhatGiaTriKhiFutureHoanTat() {
    CompletableFuture<String> future =
        CompletableFuture.completedFuture("ready");

    StepVerifier.create(Mono.fromFuture(future))
        .expectNext("ready")
        .verifyComplete();
}
~~~

Kiểm thử supplier được gọi khi subscribe:

~~~java
@Test
void fromFutureSupplierChiChayKhiSubscribe() {
    AtomicInteger calls = new AtomicInteger();

    Mono<String> result = Mono.fromFuture(() -> {
        calls.incrementAndGet();
        return CompletableFuture.completedFuture("ok");
    });

    assertEquals(0, calls.get());

    StepVerifier.create(result)
        .expectNext("ok")
        .verifyComplete();

    assertEquals(1, calls.get());
}
~~~

Kiểm thử lỗi:

~~~java
@Test
void fromFutureChuyenLoiThanhOnError() {
    CompletableFuture<String> future = new CompletableFuture<>();
    future.completeExceptionally(
        new IllegalStateException("remote failed")
    );

    StepVerifier.create(Mono.fromFuture(future))
        .expectErrorMatches(error ->
            Exceptions.unwrap(error) instanceof IllegalStateException
                && Exceptions.unwrap(error).getMessage().equals("remote failed")
        )
        .verify();
}
~~~

Kiểm thử Mono rỗng khi future trả null:

~~~java
@Test
void fromFutureNullHoanTatRong() {
    CompletableFuture<String> future =
        CompletableFuture.completedFuture(null);

    StepVerifier.create(Mono.fromFuture(future))
        .verifyComplete();
}
~~~

Với cancellation, có thể tạo một future kiểm thử có ghi nhận lời gọi `cancel` hoặc dùng client giả có thể quan sát request bị hủy. Không nên dùng thời gian chờ dài hoặc `Thread.sleep` để kiểm tra race condition; hãy điều khiển việc hoàn tất future từ test và xác minh hành vi bằng tín hiệu.

## 13. Kiểm thử chiều chuyển từ Mono sang CompletableFuture

`toFuture()` subscribe vào Mono, vì vậy có thể xác minh future được hoàn tất mà không chặn thread:

~~~java
@Test
void toFutureChuyenGiaTriMonoSangCompletableFuture() {
    CompletableFuture<String> future = Mono.just("done").toFuture();

    assertTrue(future.isDone());
    assertEquals("done", future.getNow(null));
}
~~~

Với Mono rỗng, future hoàn tất thành công với null. Nếu muốn biểu diễn empty rõ ràng:

~~~java
CompletableFuture<Optional<String>> future =
    Mono.<String>empty()
        .map(Optional::of)
        .defaultIfEmpty(Optional.empty())
        .toFuture();
~~~

Ở ranh giới imperative, caller có thể tiếp tục xử lý bằng các continuation không chặn:

~~~java
CompletableFuture<String> response =
    service.loadResult()
        .toFuture()
        .thenApply(this::formatResponse);
~~~

Không cần gọi `get()` để nối hai bước. `thenApply` đăng ký continuation và thực thi khi future hoàn tất.

## 14. Quy tắc chọn cách chuyển đổi

| Tình huống | Cách làm |
|---|---|
| API cũ trả về một CompletableFuture | `Mono.fromFuture(future)` |
| Muốn tạo future khi có subscription | `Mono.fromFuture(() -> createFuture())` |
| Nhiều future độc lập cần kết hợp trong Reactor | Chuyển từng future thành Mono rồi dùng `Mono.zip` |
| Kết quả future thứ hai phụ thuộc kết quả thứ nhất | `flatMap` với `Mono.fromFuture` |
| API imperative yêu cầu CompletableFuture | `mono.toFuture()` |
| Mono có thể rỗng nhưng future caller cần phân biệt empty | Chuyển thành `Optional` trước `toFuture()` |
| Cần chuyển thread xử lý downstream | `publishOn` sau điểm chuyển đổi |
| Future được tạo từ API chặn | Ưu tiên `fromCallable(...).subscribeOn(boundedElastic())` |
| Cần dừng công việc khi downstream hủy | Kiểm tra cancellation support của future và client |

Chuyển đổi giữa CompletableFuture và Reactor giúp tích hợp thư viện bất đồng bộ cũ với pipeline reactive mà không chiếm thread để chờ kết quả. Dùng `Mono.fromFuture` để đưa một kết quả tương lai vào pipeline; dùng supplier khi cần trì hoãn việc tạo future đến lúc subscribe; dùng `Mono.toFuture` tại ranh giới API imperative. Khi hiểu rõ empty/null, lỗi, cancellation và executor, ứng dụng có thể kết hợp hai mô hình bất đồng bộ mà vẫn giữ được khả năng điều phối, kiểm thử và quản lý vòng đời.

