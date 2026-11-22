# Mono, Flux và thời điểm thực thi sau khi có đăng ký

Trong Spring WebFlux, hai kiểu thường thấy nhất là `Mono<T>` và `Flux<T>` của Project Reactor. Một nhầm lẫn phổ biến là nghĩ rằng khi chương trình chạy đến dòng `Mono.just(...)`, `map(...)` hoặc trả về `Flux` thì toàn bộ công việc bên trong pipeline đã được thực hiện. Thực tế cần phân biệt **lúc tạo mô tả luồng (assembly)**, **lúc có người đăng ký nhận dữ liệu (subscription)**, **lúc downstream yêu cầu dữ liệu (request/demand)** và **lúc tín hiệu được phát ra (onNext/onError/onComplete)**.

Hiểu ranh giới này là nền tảng để đọc code WebFlux, tránh gọi tác vụ hai lần, tránh tự `subscribe()` trong controller, kiểm soát lỗi và sử dụng backpressure đúng cách. Bài dùng Java 17+ và Reactor trên Spring Boot 3.3.x; ví dụ minh họa hoạt động trong project có dependency phù hợp.

## 1. Mono và Flux là gì?

Project Reactor triển khai mô hình Reactive Streams và cung cấp hai loại publisher chính:

| Kiểu | Số phần tử tối đa | Kết thúc hợp lệ | Trường hợp sử dụng |
|---|---:|---|---|
| `Mono<T>` | 0 hoặc 1 | Hoàn thành rỗng, phát một giá trị rồi hoàn thành, hoặc lỗi | Tìm một bản ghi, phản hồi một HTTP request, ghi một thay đổi |
| `Flux<T>` | 0 đến N | Phát nhiều giá trị rồi hoàn thành, hoặc lỗi; có thể kéo dài vô hạn | Danh sách dữ liệu, stream sự kiện, thay đổi theo thời gian |

Ví dụ tạo publisher:

~~~java
Mono<String> one = Mono.just("hello");
Mono<String> none = Mono.empty();
Mono<String> failed = Mono.error(new IllegalStateException("unavailable"));

Flux<Integer> many = Flux.just(10, 20, 30);
Flux<Integer> range = Flux.range(1, 5);
Flux<Integer> noItems = Flux.empty();
~~~

`Mono.just("hello")` giữ một giá trị sẵn có; `Flux.range(1, 5)` mô tả các số từ 1 đến 5 (tham số thứ hai là **số lượng**, không phải cận trên). `Mono.empty()` không phát giá trị và hoàn thành thành công. `Mono.error(...)` phát tín hiệu lỗi khi luồng được đăng ký, không biến lỗi thành một giá trị dữ liệu.

Điểm cốt lõi: **Mono và Flux là Publisher, không phải bản thân giá trị hay collection đã tính xong**. Một `Mono<User>` khác với `User`; một `Flux<User>` khác với `List<User>`. Publisher mô tả cách các tín hiệu được cung cấp cho subscriber.

`Mono` không cho phép giá trị `null` như một phần tử `onNext`. Nếu nguồn có thể không có dữ liệu, dùng `Mono.empty()`, `Mono.justOrEmpty(value)`, hoặc thiết kế kiểu kết quả phù hợp.

## 2. Reactive Streams: Publisher, Subscriber và Subscription

Bốn vai trò chính của Reactive Streams:

- **Publisher<T>**: nguồn có khả năng cung cấp tối đa những phần tử mà giao thức của nó cho phép.
- **Subscriber<T>**: bên nhận dữ liệu và các tín hiệu kết thúc/lỗi.
- **Subscription**: quan hệ giữa Publisher và Subscriber; cho phép `request(n)` và `cancel()`.
- **Processor<T,R>**: vừa nhận vừa phát dữ liệu, một thành phần xử lý kết hợp.

Một subscription có thứ tự tín hiệu khái niệm:

~~~text
Publisher                    Subscriber
   |                              |
   | --- onSubscribe(sub) ------> |
   | <----- request(n) ---------- |  (n > 0)
   | --- onNext(value) ---------> |  (0..n giá trị theo demand)
   | --- onNext(value) ---------> |
   | --- onComplete() ----------> |  (thành công)
            hoặc
   | --- onError(cause) --------> |  (thất bại)

Subscriber có thể gọi cancel() để dừng nhận thêm dữ liệu.
~~~

Hai tín hiệu kết thúc `onComplete` và `onError` loại trừ nhau trong **một subscription**. Sau tín hiệu kết thúc, publisher không được gửi thêm `onNext` cho subscriber đó.

Không phải `Mono` nào cũng phát `onNext`: `Mono.empty()` chỉ hoàn thành. Không phải `Flux` nào cũng hoàn thành hữu hạn: stream thời gian thực có thể phát liên tục tới khi bị hủy. Tín hiệu `cancel` là hướng ngược từ subscriber để yêu cầu ngừng luồng, **không phải một `onComplete` thành công**.

## 3. Assembly và subscription là hai thời điểm khác nhau

Hãy xem:

~~~java
Mono<Integer> pipeline = Mono.fromSupplier(() -> {
    System.out.println("loading");
    return 7;
}).map(value -> value * 2);

System.out.println("assembled");
~~~

Khi chạy tới đây, Java đã tạo ra một đối tượng Publisher và gắn operator `map`. Callback của `fromSupplier` **chưa chạy** nếu chưa có subscription. Vì vậy, dòng được in lúc này chỉ là:

~~~text
assembled
~~~

Sau đó:

~~~java
pipeline.subscribe(value -> System.out.println("result=" + value));
~~~

Với nguồn `Mono.fromSupplier` và các operator đồng bộ trong ví dụ, kết quả bổ sung sẽ là:

~~~text
loading
result=14
~~~

Tổng thứ tự là `assembled`, rồi `loading`, rồi `result=14`.

Trong trường hợp tổng quát, **subscription không bảo đảm mọi callback hoàn tất trước khi `subscribe()` trả về**. Nếu luồng chứa timer, network I/O, scheduler hoặc nguồn bất đồng bộ, `subscribe()` có thể trả về ngay, còn dữ liệu xuất hiện sau.

Cũng không nên phát biểu tuyệt đối rằng “mọi thứ chỉ chạy sau subscribe”: lời gọi Java dùng để **xây dựng** publisher vẫn thực thi ở assembly, còn các nguồn hot có thể phát giá trị độc lập với subscriber. Ranh giới chính xác phụ thuộc cách tạo publisher.

## 4. Ví dụ chạy được: hai lần subscribe chạy lại nguồn cold

Để quan sát trực tiếp, tạo project Spring Boot dùng `spring-boot-starter-webflux`. Dependency WebFlux đã đưa Reactor Core vào classpath:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Trong file `src/main/java/com/example/demo/SubscriptionDemo.java`, đặt:

~~~java
package com.example.demo;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class SubscriptionDemo {

    public static void main(String[] args) {
        Mono<Integer> pipeline = Mono.fromSupplier(() -> {
            System.out.println("source invoked");
            return 2;
        }).map(number -> number * 10);

        System.out.println("assembled");

        pipeline.subscribe(value ->
            System.out.println("first: " + value));

        pipeline.subscribe(value ->
            System.out.println("second: " + value));

        Flux<Integer> items = Flux.range(1, 3)
            .doOnSubscribe(subscription ->
                System.out.println("flux subscribed"));

        items.subscribe(
            value -> System.out.println("item: " + value),
            error -> System.out.println("error: " + error.getMessage()),
            () -> System.out.println("flux complete")
        );
    }
}
~~~

Đây là class có `main` độc lập về logic nhưng **cần dependency Reactor**. Chạy trong IDE với runtime classpath của project, hoặc bằng task JavaExec do project cấu hình; chỉ dùng `javac SubscriptionDemo.java` đơn lẻ sẽ thiếu thư viện Reactor.

Với source và operator đồng bộ như trên, stdout chính xác là:

~~~text
assembled
source invoked
first: 20
source invoked
second: 20
flux subscribed
item: 1
item: 2
item: 3
flux complete
~~~

Tại sao `source invoked` in hai lần? `Mono.fromSupplier` là nguồn cold: mỗi subscription kích hoạt supplier một lần. Hai subscriber không mặc nhiên chia sẻ kết quả. `Flux.range` cũng cung cấp dãy phần tử mới cho subscription của nó.

Ví dụ này cố tình không dùng scheduler hay delay, nên thứ tự stdout mang tính xác định. Với code đa luồng hoặc I/O thật, chỉ dựa vào thứ tự dòng log để suy luận thời gian subscription là không đủ; cần quan sát signal và thread.

## 5. Mono.just, fromSupplier, fromCallable và defer

Từ “lazy” cần được hiểu theo **những biểu thức cụ thể**. So sánh:

~~~java
String value = loadValue();                  // chạy NGAY
Mono<String> a = Mono.just(value);           // giữ giá trị đã có
Mono<String> b = Mono.just(loadValue());     // loadValue chạy NGAY
Mono<String> c = Mono.fromSupplier(
    () -> loadValue());                       // loadValue chạy khi subscribe
Mono<String> d = Mono.fromCallable(
    () -> readFile());                        // đọc file khi subscribe
Mono<String> e = Mono.defer(
    () -> Mono.just(loadValue()));            // tạo Mono mới khi subscribe
~~~

Các dòng trên minh họa thời điểm đánh giá Java expression, không phải chương trình độc lập; `loadValue` và `readFile` là các hàm do ứng dụng tự định nghĩa.

| Factory | Điểm cần nhớ |
|---|---|
| `Mono.just(value)` | Nhận giá trị đã được tính tại assembly; mỗi subscribe nhận lại giá trị đó |
| `Mono.justOrEmpty(value)` | Tạo Mono từ một giá trị có thể null hoặc Optional; null dẫn tới empty |
| `Mono.fromSupplier(supplier)` | Gọi Supplier khi có subscription, cho phép chuẩn bị giá trị mới cho từng lần đăng ký |
| `Mono.fromCallable(callable)` | Tương tự Supplier nhưng phù hợp tác vụ có thể ném checked exception; exception được chuyển thành tín hiệu lỗi |
| `Mono.defer(factory)` | Chạy factory khi subscribe; mỗi lần đăng ký có thể tạo publisher khác |
| `Mono.error(exception)` | Phát lỗi dưới dạng tín hiệu reactive cho subscriber |
| `Mono.empty()` | Hoàn thành mà không phát giá trị |

**Sắc thái quan trọng:** `Mono.just` tự nó phát giá trị theo subscription, nhưng giá trị đã được chụp trước đó nên các phép tính để tạo giá trị có thể đã xảy ra tại assembly. Tài liệu Reactor gọi đây là một dạng nguồn hot theo khía cạnh capture; không được suy diễn rằng mọi công việc dùng `Mono.just` sẽ lặp lại ở mỗi subscriber.

Nếu `loadValue()` gọi database hoặc HTTP service, đặt nó ngay trong `Mono.just(loadValue())` sẽ thực hiện lời gọi trước khi pipeline được subscribe. Dùng `Mono.defer`, `Mono.fromCallable` hoặc API reactive đúng nghĩa để kiểm soát thời điểm làm việc.

`fromCallable` không tự biến I/O blocking thành non-blocking. Với tác vụ blocking buộc phải giữ lại, cần cân nhắc `Schedulers.boundedElastic()` (xem mục về thread).

## 6. Operator map, filter, flatMap không tự kích hoạt subscription

Khi nối operator:

~~~java
Mono<String> result = Mono.just("  spring  ")
    .map(String::trim)
    .filter(text -> !text.isBlank())
    .map(String::toUpperCase);
~~~

Ta đang mô tả một chuỗi xử lý. Callback trong `map` và `filter` được gọi khi có tín hiệu từ upstream trong một subscription, thay vì tự chạy chỉ bởi việc nối operator.

Trong ví dụ trên, sau khi đăng ký:

~~~java
result.subscribe(System.out::println);
~~~

Stdout:

~~~text
SPRING
~~~

`flatMap` khác `map` ở chỗ callback trả một Publisher, và Reactor kết hợp/subcribe publisher bên trong theo semantics của operator:

~~~java
Mono<User> user = userRepository.findById(id); // giả sử repository reactive
Mono<Order> order = user.flatMap(foundUser ->
    orderRepository.findLatestByUserId(foundUser.id())
);
~~~

Đây là mã minh họa, các repository là interface của ứng dụng. `flatMap` hữu ích khi bước kế tiếp cũng bất đồng bộ. Nếu viết `map(foundUser -> orderRepository.find...)`, kết quả có thể thành `Mono<Mono<Order>>`, khiến caller không có `Mono<Order>` như mong muốn.

Với nhiều giá trị:
- `flatMap` có thể chạy các publisher bên trong đồng thời, thứ tự hoàn thành không nhất thiết bằng thứ tự nguồn.
- `concatMap` giữ thứ tự bằng cách xử lý tuần tự theo logic operator.
- `flatMapSequential` kết hợp khả năng xử lý nhiều nguồn với thứ tự phát lại.
- `then` bỏ qua các giá trị dữ liệu trước đó và chờ completion; `thenReturn` cung cấp giá trị sau completion.

Không đặt logic có side effect quan trọng vào một callback rồi giả định nó “đã được thực hiện” khi method trả Publisher. Nếu không có subscription, callback có thể chưa chạy.

## 7. Khi nào publisher thực sự được subscribe?

Các hành động thường tạo subscription:

1. Gọi `mono.subscribe(...)` hoặc `flux.subscribe(...)` ở cuối pipeline trong ứng dụng console/service ở ranh giới hệ thống.
2. Gọi terminal operation kiểu `block()`, `blockFirst()`, `blockLast()` (cũng subscribe, nhưng chặn thread gọi).
3. Framework như Spring WebFlux nhận một Publisher để xử lý HTTP response/request và quản lý subscription.
4. Các công cụ kiểm thử như `StepVerifier` subscribe khi bước `verify()` được thực hiện.
5. Một số adapter/bridge chuyển Publisher thành công cụ khác cũng tự tạo subscription.

Ngược lại, `map`, `filter`, `doOnNext`, `flatMap` hoặc việc tạo biến `Mono<T>` không phải hành động đăng ký độc lập.

Cần phân biệt **“có subscribe”** và **“đã có giá trị”**. Subscriber có thể đăng ký nhưng chưa có demand đủ lớn, nguồn đang đợi timer/network I/O, publisher không phát phần tử hoặc đã bị hủy. Subscription là điều kiện cơ bản cho luồng cold, không đồng nghĩa với hoàn thành ngay.

## 8. Tín hiệu doOnSubscribe, doOnNext, doOnSuccess, doOnComplete

Reactor cung cấp các operator để quan sát lifecycle mà không tự kết thúc pipeline:

~~~java
Mono<String> observed = Mono.fromSupplier(() -> "ok")
    .doOnSubscribe(subscription ->
        System.out.println("subscribed"))
    .doOnNext(value ->
        System.out.println("next: " + value))
    .doOnSuccess(value ->
        System.out.println("success: " + value))
    .doOnError(error ->
        System.out.println("error: " + error.getMessage()))
    .doFinally(signalType ->
        System.out.println("finally: " + signalType));

observed.subscribe();
~~~

Lưu ý:
- `doOnSubscribe` quan sát khi một Subscription đã được thiết lập.
- `doOnNext` chỉ chạy khi có giá trị `onNext`.
- `Mono.doOnSuccess` chạy khi Mono hoàn thành thành công, **kể cả Mono empty** (giá trị callback là null đối với empty).
- `Flux.doOnComplete` quan sát luồng Flux hoàn thành thành công; nó không chạy khi luồng kết thúc bằng lỗi.
- `doOnError` quan sát lỗi nhưng **không tự phục hồi lỗi**.
- `doFinally` nhận loại tín hiệu kết thúc cuối cùng: complete, error hoặc cancel, hữu ích để ghi metric và giải phóng tài nguyên theo scope.
- `doFirst` là hook chạy rất sớm khi có subscription; có thể dùng để quan sát trước `doOnSubscribe`.

Các operator `doOn...` dành cho logging, metrics và side effect có kiểm soát. Đừng biến chúng thành nơi thực hiện bước nghiệp vụ phải được chờ hoàn thành; trong trường hợp đó hãy đưa công việc vào `flatMap`, `then` hoặc operator phù hợp để nó trở thành một phần của pipeline.

## 9. Một publisher và nhiều subscriber: cold, hot, cache, share

**Cold publisher** tạo tiến trình phát dữ liệu riêng cho mỗi lần đăng ký. `Mono.fromSupplier`, `Flux.range` và nhiều lời gọi reactive HTTP/DB là các ví dụ thường gặp. Với cold publisher, đăng ký hai lần có thể dẫn đến **hai lần gọi I/O thật**.

~~~java
Mono<String> cold = Mono.fromSupplier(() -> {
    System.out.println("loading");
    return "value";
});

cold.subscribe();
cold.subscribe();
~~~

Stdout:

~~~text
loading
loading
~~~

**Hot publisher** có thể phát dữ liệu độc lập với một subscriber cụ thể. Người đến sau có thể bỏ lỡ phần tử trước đó nếu nguồn không replay. Ví dụ có thể tạo nguồn bằng `Sinks.Many` hoặc chia sẻ bằng `share()`; cách replay phụ thuộc cấu hình.

Các operator chia sẻ có ý nghĩa khác nhau:

| Cách tiếp cận | Hành vi cần lưu ý |
|---|---|
| Giữ một `Mono.just(value)` | Chia sẻ giá trị được capture tại assembly; không chạy lại phép tính tạo giá trị |
| `Mono.cache()` | Cache tín hiệu từ một lần subscription upstream sau khi nó xảy ra; các subscriber sau nhận tín hiệu cache theo semantics của operator |
| `Flux.share()` | Chia sẻ một nguồn đang chạy cho subscriber đồng thời theo dạng publish/refCount; người đăng ký muộn có thể bỏ lỡ phần tử |
| `Flux.replay(...)` / `cache(...)` | Có cơ chế lưu và phát lại dữ liệu theo cấu hình; cần chú ý bộ nhớ và vòng đời cache |
| `Sinks.Many` | Cho phép mã ứng dụng chủ động phát tín hiệu; lựa chọn multicast/unicast/replay quyết định fan-out |

Ví dụ `Mono.cache()`:

~~~java
Mono<String> once = Mono.fromSupplier(() -> {
    System.out.println("fetch");
    return "data";
}).cache();

once.subscribe(System.out::println);
once.subscribe(System.out::println);
~~~

Với nguồn đồng bộ và hai subscription tuần tự này, stdout:

~~~text
fetch
data
data
~~~

Chỉ đăng ký hai lần không đảm bảo cùng một kết quả nếu publisher nguồn chứa side effect; muốn dùng chung dữ liệu cần chọn rõ semantics cache/share.

**Cảnh báo:** Không dùng cache vô hạn cho dữ liệu cần luôn mới hoặc cho Flux không giới hạn nếu không hiểu bộ nhớ và lifecycle. Với API cần reload theo request, cold publisher riêng theo request thường là lựa chọn rõ ràng hơn.

## 10. Backpressure: request(n) điều khiển lượng dữ liệu

Reactive Streams cho phép downstream yêu cầu số lượng phần tử có thể nhận qua `Subscription.request(n)`. Đó là **demand**.

Ví dụ dùng `BaseSubscriber` để yêu cầu từng phần tử:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

Flux.range(1, 3).subscribe(new BaseSubscriber<Integer>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        System.out.println("subscribed");
        request(1);
    }

    @Override
    protected void hookOnNext(Integer value) {
        System.out.println("next: " + value);
        request(1);
    }

    @Override
    protected void hookOnComplete() {
        System.out.println("complete");
    }
});
~~~

Với nguồn `Flux.range` đồng bộ, stdout:

~~~text
subscribed
next: 1
next: 2
next: 3
complete
~~~

Nếu không gọi `request(n)` với `n > 0` trong subscriber này, nguồn có thể chờ mãi vì downstream chưa yêu cầu dữ liệu. Cần nhớ:
- `request(1)` yêu cầu một phần tử; nhiều lần gọi cộng dồn demand.
- `Long.MAX_VALUE` đại diện yêu cầu không giới hạn theo quy ước Reactor.
- Các overload `subscribe(value -> ...)` thông dụng tự yêu cầu demand không giới hạn; chúng **không chứng minh** rằng toàn pipeline đang tự động giới hạn từng phần tử.
- Một số operator thay đổi demand ở upstream thông qua prefetch, buffering hoặc concurrency. Không suy đoán mỗi lần `request(1)` của subscriber luôn tương ứng một lần gọi request(1) tới nguồn ban đầu.

Backpressure là cơ chế phối hợp sản xuất/tiêu thụ ở tầng Reactive Streams. Nó không thay thế giới hạn memory, kích thước request hoặc chính sách bảo vệ các nguồn nóng có thể phát nhanh hơn consumer.

## 11. subscribeOn và publishOn: subscription không đồng nghĩa thread mới

Trong Reactor, `subscribe()` tự nó không có nghĩa là “chạy trên thread khác”. Với `Mono.just`, `Flux.range` và operator đồng bộ, nhiều callback có thể chạy ngay trên thread gọi `subscribe()`.

Để thay đổi môi trường thực thi, Reactor có hai operator chính:

| Operator | Tác động chủ yếu |
|---|---|
| `subscribeOn(scheduler)` | Chỉ định scheduler cho việc subscribe/request upstream và các tín hiệu nguồn trong phạm vi phù hợp |
| `publishOn(scheduler)` | Chuyển nơi xử lý các tín hiệu ở **phần downstream** phía sau operator đó |

Ví dụ khi bắt buộc gọi API blocking cũ:

~~~java
Mono<String> legacyCall = Mono.fromCallable(() ->
        legacyClient.loadValue())
    .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là đoạn minh họa, `legacyClient` là dependency của ứng dụng. `fromCallable` hoãn lời gọi đến subscription; `boundedElastic` cung cấp scheduler phù hợp để cô lập những tác vụ blocking mà chưa thể thay thế. **Cả hai không biến thao tác blocking thành I/O không blocking thực sự.**

Nếu đã dùng repository/client reactive thì ưu tiên giữ nguyên chuỗi không blocking:

~~~java
Mono<Order> order = reactiveRepository.findById(id)
    .flatMap(found -> reactiveService.enrich(found));
~~~

Đừng thêm `subscribeOn(boundedElastic())` cho mọi endpoint theo thói quen; scheduler switching có chi phí và có thể che giấu chỗ I/O blocking cần sửa.

Với WebFlux + Reactor Netty, event loop phục vụ I/O. Gọi `Thread.sleep`, `Future.get` hoặc `Mono.block()` trên event loop có thể làm nghẽn request của nhiều client. Trong một số thread không blocking do Reactor quản lý, `block()` còn có thể bị từ chối bằng exception.

## 12. Spring WebFlux subscribe ở đâu?

Trong WebFlux, controller thường **trả Publisher** cho framework:

~~~java
@GetMapping("/api/orders/{id}")
public Mono<OrderDto> find(@PathVariable long id) {
    return orderService.findById(id);
}
~~~

Giả sử `orderService.findById` trả `Mono<OrderDto>` từ reactive data access. Controller không cần gọi `subscribe()`; Spring WebFlux xử lý giá trị trả về, kết hợp với pipeline HTTP và đăng ký vào Publisher khi thực hiện response.

Luồng khái niệm:

~~~text
HTTP request đến
   |
WebFlux dispatcher tìm handler
   |
Controller method được gọi
   |
Trả Mono<OrderDto> hoặc Flux<OrderDto>
   |
WebFlux xử lý return value và chuẩn bị response writer
   |
Framework subscribe / demand / consume các tín hiệu
   |
Source thực hiện công việc lúc subscription (nếu là cold)
   |
HttpMessageWriter mã hóa body và gửi xuống transport
   |
Hoàn thành / lỗi / hủy kết nối
~~~

**Một điểm thời gian dễ nhầm:** Code Java **bên ngoài** Publisher nằm trong body method controller có thể chạy ngay khi framework gọi method đó. Chỉ phần công việc được đưa vào nguồn cold/operator mới chờ subscription.

Ví dụ:

~~~java
@GetMapping("/api/demo")
public Mono<String> demo() {
    System.out.println("handler method invoked"); // chạy khi gọi handler
    return Mono.fromSupplier(() -> {
        System.out.println("publisher evaluated"); // khi subscribe
        return "OK";
    });
}
~~~

Log `handler method invoked` và `publisher evaluated` ở hai mốc logic khác nhau. Không dựa vào thứ tự log giữa các request đồng thời để chứng minh chính xác từng thread hoặc số lần subscribe.

### 12.1. Tại sao không gọi subscribe() trong controller?

**Không nên:**

~~~java
@PostMapping("/api/orders")
public Mono<Void> create(@RequestBody Mono<CreateOrder> request) {
    request.flatMap(orderService::save).subscribe();
    return Mono.empty();
}
~~~

Trong đoạn minh họa này, `subscribe()` khởi động một công việc phụ tách khỏi phản hồi HTTP. WebFlux có thể trả thành công trong khi thao tác lưu chưa xong hoặc đã thất bại. Exception, cancellation và lifecycle của request không còn được framework phối hợp theo cùng pipeline. Cũng dễ tạo đăng ký trùng khi đồng thời trả/đăng ký publisher.

**Nên:**

~~~java
@PostMapping("/api/orders")
public Mono<Void> create(@RequestBody Mono<CreateOrder> request) {
    return request.flatMap(orderService::save).then();
}
~~~

Giờ response phụ thuộc completion/error của công việc lưu. `then()` bỏ giá trị và chỉ giữ tín hiệu hoàn thành/lỗi; `Mono<Void>` nghĩa là thành công không phát body. Đây là mã minh họa khi `orderService.save` trả một Publisher; không phải class chạy độc lập.

**Không gọi `subscribe()` trong controller chỉ để “kích hoạt” Mono/Flux**. Chính framework là subscriber thích hợp ở ranh giới HTTP. Những background job tự quản lý có thể cần subscriber riêng, nhưng phải có lifecycle, xử lý lỗi, cancellation và ownership rõ ràng.

## 13. Ví dụ Spring Boot WebFlux đầy đủ

Trong project Java 17+ có `spring-boot-starter-webflux`, tạo file `src/main/java/com/example/demo/ReactiveWebApplication.java`:

~~~java
package com.example.demo;

import java.time.Duration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveWebApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveWebApplication.class, args);
    }
}

record Greeting(String message) {}

@RestController
class ReactiveController {

    @GetMapping("/api/hello/{name}")
    public Mono<Greeting> hello(@PathVariable String name) {
        System.out.println("handler invoked: " + name);
        return Mono.fromSupplier(() -> {
            System.out.println("source subscribed: " + name);
            return new Greeting("Hello, " + name);
        });
    }

    @GetMapping(value = "/api/numbers",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<Integer> numbers() {
        return Flux.range(1, 3);
    }

    @GetMapping(value = "/api/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<Long>> events() {
        return Flux.interval(Duration.ofSeconds(1))
            .take(3)
            .map(index -> ServerSentEvent.<Long>builder()
                .data(index)
                .build());
    }
}
~~~

Khởi động bằng Gradle wrapper trong project Spring Boot đã cấu hình:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Kiểm tra Mono:

~~~bash
curl -i http://localhost:8080/api/hello/Ada
~~~

Body JSON điển hình:

~~~json
{"message":"Hello, Ada"}
~~~

Trong log server, handler được gọi để tạo Mono; supplier được gọi khi pipeline được subscribe. Vì đây là request thật, WebFlux đảm nhiệm việc subscribe và tạo HTTP response.

Kiểm tra Flux hữu hạn:

~~~bash
curl -i http://localhost:8080/api/numbers
~~~

Body JSON điển hình:

~~~json
[1,2,3]
~~~

**Quan trọng:** `Flux<Integer>` không tự đồng nghĩa với “mỗi phần tử gửi ra mạng ngay khi tạo”. Với `application/json`, mã hóa thành một mảng JSON có thể đi kèm buffering. Nếu muốn luồng dữ liệu tăng dần, cần media type và writer phù hợp như Server-Sent Events hoặc NDJSON.

Kiểm tra SSE:

~~~bash
curl -N http://localhost:8080/api/events
~~~

Ví dụ nội dung sự kiện (xuống dòng/chi tiết tùy encoder):

~~~text
data:0

data:1

data:2
~~~

`Flux.interval` bắt đầu tính thời gian theo subscription; ở ví dụ này có ba phần tử 0, 1 và 2 với khoảng cách xấp xỉ một giây. Thời gian response thực tế có thể lệch do scheduling, mạng và client.

Nếu client ngắt kết nối giữa chừng, WebFlux có thể truyền tín hiệu hủy tới pipeline. Việc tác vụ upstream thực sự dừng và tài nguyên được giải phóng còn phụ thuộc publisher/operator đang dùng.

## 14. Flux và streaming HTTP: không phải hai khái niệm đồng nhất

Một `Flux<T>` chỉ mô tả khả năng phát nhiều phần tử; cách biểu diễn HTTP do content negotiation và codec quyết định.

| Dạng trả về | Điều thường thấy | Cần lưu ý |
|---|---|---|
| `Mono<T>` với `application/json` | Một JSON value hoặc body rỗng | Empty không tự đồng nghĩa 404 |
| `Flux<T>` hữu hạn với `application/json` | Một JSON array | Có thể được ghi/buffer theo chiến lược codec |
| `Flux<T>` với `application/x-ndjson` | Nhiều dòng JSON | Phù hợp streaming nhiều object |
| `Flux<ServerSentEvent<T>>` với `text/event-stream` | Sự kiện SSE theo thời gian | Client cần xử lý luồng và kết nối lâu |
| `Mono<Void>` | Chỉ completion/error | HTTP status cần được đặt đúng theo API contract |

Không ép mọi API trả Flux dù nghiệp vụ chỉ có một kết quả. Chọn Mono/Flux theo cardinality và tính chất nguồn; chọn media type theo hợp đồng truyền tải.

## 15. WebClient và repository reactive cũng tạo Publisher

Ví dụ sử dụng WebClient:

~~~java
Mono<Product> product = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .bodyToMono(Product.class);
~~~

Đây là đoạn minh họa với `webClient` và `Product` của ứng dụng. Việc **xây** pipeline chưa đồng nghĩa có HTTP network request ngay. Với cách dùng WebClient reactive thông thường, network I/O gắn với subscription của publisher kết quả.

Nếu đăng ký hai lần vào một pipeline cold, có thể tạo **hai HTTP request outbound**. Điều này có ý nghĩa khi controller logic gọi service nhiều lần hoặc khi retry. Nếu cần dùng chung kết quả trong cùng một request, phải chọn cấu trúc compose/cache phù hợp và cân nhắc độ mới dữ liệu.

Ví dụ kết hợp:

~~~java
Mono<ProductView> result = productRepository.findById(id)
    .flatMap(product ->
        stockClient.getStock(product.id())
            .map(stock -> new ProductView(product, stock))
    );
~~~

Đây là một chain gồm nhiều Publisher, không yêu cầu gọi subscribe ở từng bước. Subscriber ở cuối (chẳng hạn WebFlux) điều khiển toàn bộ công việc.

**Đừng nhầm:** Lời gọi method tạo Publisher có thể tự thực thi code Java đồng bộ trước khi trả về publisher. Điều được hoãn là I/O/side effect nằm **bên trong** quá trình subscription của nguồn reactive được thiết kế đúng; không phải mọi câu lệnh trong hàm đều được Reactor trì hoãn.

## 16. Lỗi, empty, completion và cancellation

Bốn tình huống cần xử lý riêng:

| Tình huống | Tín hiệu của Mono/Flux | Hướng xử lý |
|---|---|---|
| Có dữ liệu | `onNext`, sau đó `onComplete` nếu hữu hạn | `map`, `flatMap` hoặc response writer |
| Thành công nhưng rỗng | `onComplete` không có `onNext` | `switchIfEmpty`, `defaultIfEmpty` hoặc API contract |
| Lỗi | `onError` | `onErrorResume`, `onErrorMap` hoặc error handler của framework |
| Client hủy / subscriber cancel | `cancel()` gửi upstream | `doOnCancel`, `doFinally`, cleanup tài nguyên |

Ví dụ xử lý không tìm thấy bản ghi:

~~~java
@GetMapping("/api/products/{id}")
public Mono<Product> find(@PathVariable long id) {
    return productRepository.findById(id)
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Product not found")));
}
~~~

Các dependency `Product`, `productRepository`, `ResponseStatusException` và `HttpStatus` cần được import/định nghĩa tương ứng. Ví dụ nêu cách chuyển empty thành lỗi 404; **Mono.empty() tự nó không buộc WebFlux trả 404**.

Nếu muốn xử lý ngoại lệ theo loại:

~~~java
Mono<Product> recovered = productRepository.findById(id)
    .onErrorResume(TemporaryBackendException.class,
        error -> fallbackRepository.findById(id));
~~~

`onErrorResume` tạo luồng fallback khi nhận error. `doOnError` chỉ quan sát error, không thay nó bằng giá trị.

Với `retry(1)`, Reactor thường **đăng ký lại** vào upstream khi gặp lỗi, do đó một tác vụ side effect có thể được thực thi thêm lần nữa. Chỉ retry những thao tác an toàn/idempotent hoặc có cơ chế chống lặp. Cancellation cũng có thể xảy ra sau khi bên ngoài đã thực hiện một phần side effect; không thể mặc định cancel sẽ rollback transaction hay request HTTP đã gửi.

## 17. Sai lầm block() và subscribe() ở WebFlux

### 17.1. block() cũng subscribe nhưng giữ thread chờ

~~~java
String value = Mono.just("ok").block();
~~~

`block()` vừa tạo subscription vừa chặn thread gọi cho đến khi có tín hiệu. Nó hữu ích ở **ranh giới ứng dụng đồng bộ** như một số tác vụ CLI hoặc test nhỏ, nhưng thường không phù hợp trong handler WebFlux vì có thể chặn event loop, làm giảm khả năng xử lý đồng thời.

Đặc biệt, mỗi lần gọi `block()` riêng là một subscription mới; dùng `block()` hai lần trên nguồn cold có thể lặp I/O. Không dùng `block()` chỉ để “lấy dữ liệu” rồi bọc lại trong `Mono.just` ở controller.

### 17.2. subscribe() bỏ qua lifecycle nếu không quản lý

~~~java
Disposable subscription = flux.subscribe(
    value -> consume(value),
    error -> report(error)
);

// Khi không còn cần:
subscription.dispose();
~~~

Đây là minh họa cho chương trình **tự sở hữu** subscriber. `subscribe` có thể trả về `Disposable` để hủy subscription. Tuy nhiên `dispose()` là yêu cầu dừng theo quy tắc reactive; với một số nguồn đã hoàn tất hoặc side effect bên ngoài, không đảm bảo hoàn tác những việc đã diễn ra.

Trong controller WebFlux, ưu tiên **return Publisher**. Nếu bạn tự subscribe rồi trả Mono rỗng, response của framework không còn gắn đầy đủ với kết quả công việc bên trong.

### 17.3. Không “fire-and-forget” tùy ý

Đối với gửi email, ghi database, đẩy event hoặc thay đổi trạng thái, hãy xác định chính sách: HTTP response phải chờ công việc hoàn tất hay chỉ xác nhận đã nhận job? Nếu cần chạy background job, dùng cơ chế queue/scheduler/lifecycle phù hợp, có error handling và quản lý shutdown. Chỉ thêm `.subscribe()` vào controller không tạo ra một hàng đợi công việc bền vững.

## 18. Quan sát và kiểm tra chính xác thời điểm subscription

### 18.1. Hook log trong pipeline

~~~java
Flux<Integer> pipeline = Flux.range(1, 3)
    .doOnSubscribe(s -> log.info("subscribed"))
    .doOnRequest(n -> log.info("requested {}", n))
    .doOnNext(value -> log.info("next {}", value))
    .doOnComplete(() -> log.info("completed"))
    .doOnCancel(() -> log.info("cancelled"))
    .doFinally(signal -> log.info("finally {}", signal));
~~~

Đây là snippet minh họa, yêu cầu biến logger `log`. Nó cho biết mức subscription/demand/emission/cancel theo luồng mà code đang theo dõi.

`checkpoint("product pipeline")` hoặc `log()` của Reactor cũng hữu ích khi debug stack trace và signal. Tránh bật logging toàn bộ payload/body trên hệ thống thật nếu có dữ liệu nhạy cảm. Với luồng bất đồng bộ, thread name và request correlation id giúp ghép sự kiện chính xác hơn stdout thuần.

### 18.2. StepVerifier: không cần sleep để đoán thời điểm

Thêm dependency kiểm thử vào project:

~~~groovy
dependencies {
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Ví dụ kiểm tra rằng supplier chỉ chạy sau khi `verifyComplete()` tạo subscription:

~~~java
package com.example.demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SubscriptionBehaviorTest {

    @Test
    void supplierRunsWhenSubscribed() {
        AtomicInteger calls = new AtomicInteger();

        Mono<Integer> source = Mono.fromSupplier(calls::incrementAndGet);

        assertEquals(0, calls.get()); // mới assembly, chưa subscribe

        StepVerifier.create(source)
            .expectNext(1)
            .verifyComplete();

        assertEquals(1, calls.get());
    }
}
~~~

`StepVerifier.create(source)` chuẩn bị kịch bản kiểm chứng; lời gọi `verifyComplete()` là điểm bắt đầu thực hiện test và subscribe vào nguồn. Test này xác nhận không có supplier invocation ở assembly và có một lần invocation khi verification.

Nếu muốn kiểm tra dữ liệu theo timer, `StepVerifier.withVirtualTime(...)` có thể mô phỏng tiến trình thời gian mà không cần đợi đồng hồ thật; cần tạo publisher trong Supplier của virtual-time verifier để scheduler ảo được gắn đúng.

### 18.3. Kiểm tra WebFlux bằng WebTestClient

Với Spring Boot test và WebFlux, có thể dùng `WebTestClient` để gửi request, kiểm tra JSON/status và đảm bảo framework xử lý Publisher được trả về. Ví dụ skeleton:

~~~java
webTestClient.get()
    .uri("/api/hello/Ada")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.message").isEqualTo("Hello, Ada");
~~~

`webTestClient` là bean/instance do test setup cung cấp; ví dụ chỉ mô tả phần assertion, không phải toàn bộ class độc lập. Trong test, nên kiểm tra cả trường hợp lỗi và empty thay vì chỉ HTTP 200.

## 19. Các câu hỏi dễ gây nhầm lẫn

**Nếu đã tạo Mono bằng `Mono.just("A")` thì có chạy chưa?** Biểu thức tạo dữ liệu được tính tại assembly; Mono giữ giá trị và sẽ phát nó khi subscription nhận demand. Với `Mono.just(callService())`, `callService()` đã được gọi trước subscription vì quy tắc đánh giá đối số của Java.

**Có thể truyền Mono xuyên nhiều tầng mà chưa chạy không?** Có, với publisher cold và các operator thông thường, bạn có thể compose rồi trả qua service/controller. Tuy nhiên những câu lệnh Java ở ngoài Publisher vẫn chạy khi method được gọi.

**Subscribe một lần có đồng nghĩa kết quả xuất hiện tức thì?** Không. Một subscription có thể chờ demand, thời gian I/O, timer hoặc bị hủy trước khi có giá trị. Đừng dựa vào thứ tự các dòng log giữa những thread khác nhau.

**Mono là bất đồng bộ, Flux là đồng bộ?** Không. Cả hai có thể đồng bộ hoặc bất đồng bộ; khác biệt chính là số phần tử 0..1 và 0..N.

**Flux luôn gửi response HTTP theo từng phần tử?** Không. Publisher có thể phát từng phần tử, nhưng codec và media type quyết định cách ghi body HTTP. JSON array có thể buffer, SSE/NDJSON phù hợp cho streaming.

**Gọi `subscribe()` ở controller có nhanh hơn không?** Không phải mặc định. Nó tách công việc khỏi response và có thể làm mất quản lý lỗi/hủy; cải thiện throughput cần dựa trên non-blocking I/O và backpressure đúng cách.

**Tại sao một lệnh gọi WebClient xảy ra hai lần?** Có thể do publisher cold được subscribe hai lần, do retry/resubscription hoặc do tạo Publisher ở hai nơi. Dùng `doOnSubscribe`, test và trace để phân biệt.

**Có phải “chưa có subscriber” thì mọi Publisher không làm gì?** Không. Nguồn hot có thể phát dữ liệu trước khi ai đó đăng ký; biểu thức dùng tạo `Mono.just` hoặc code bên ngoài pipeline có thể chạy ngay.

## 20. Checklist khi viết code Spring WebFlux

1. Chọn `Mono` cho 0..1 kết quả, `Flux` cho 0..N; xác định rõ empty, error và completion.
2. Ghi rõ nguồn là cold hay hot, và side effect thực hiện ở assembly hay subscription.
3. Dùng `defer`/`fromCallable` khi cần trì hoãn việc tạo giá trị hoặc gọi legacy API.
4. Dùng `flatMap`/`then` để nối công việc bất đồng bộ, đảm bảo kết quả được chờ trong pipeline.
5. Trả Publisher cho WebFlux ở ranh giới HTTP; tránh tự `subscribe()` trong controller.
6. Không dùng `block()` trên event loop hoặc các thread cần non-blocking.
7. Nếu có blocking I/O bắt buộc, cô lập bằng scheduler phù hợp và lên kế hoạch thay bằng client reactive.
8. Khi làm việc với Flux, xác định nhu cầu demand/backpressure và buffering.
9. Cẩn trọng với `retry` vì nó có thể tạo thêm subscription và lặp side effect.
10. Với streaming HTTP, chọn codec/media type phù hợp và xử lý cancellation.
11. Quan sát `doOnSubscribe`, `doOnRequest`, `doOnNext`, `doOnError`, `doFinally` khi debug.
12. Viết StepVerifier test để chứng minh thời điểm thực thi, thay vì thêm `Thread.sleep` rồi phỏng đoán.

## 21. Tài liệu tham khảo

- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/): publishers, signals, backpressure, threading và testing.
- [Project Reactor — Hot Versus Cold](https://projectreactor.io/docs/core/3.7.0/reference/advancedFeatures/reactor-hotCold.html): khác biệt giữa publisher cold/hot, `just`, `defer`, sharing.
- [Project Reactor — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): phương thức factory, subscribe, block và lifecycle signals.
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): request/response processing, Reactive Streams và annotated controllers.
- [Spring Boot — WebFlux](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): ứng dụng WebFlux với Boot và embedded web server.

**Ghi nhớ:** `Mono` và `Flux` mô tả các tín hiệu có thể được phát; **assembly** xây pipeline, **subscription** kích hoạt nguồn cold, **request(n)** truyền demand và **onNext/onComplete/onError** thể hiện kết quả. Trong Spring WebFlux, hãy để framework quản lý subscription tại HTTP boundary và compose toàn bộ công việc thành một pipeline quan sát, kiểm thử và hủy được.
