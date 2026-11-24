# Bất đồng bộ

## Cơ chế đẩy, kéo và phối hợp đẩy–kéo trong trao đổi dữ liệu

Khi hai thành phần trao đổi dữ liệu, một câu hỏi quan trọng là: bên nào quyết định thời điểm chuyển phần tử tiếp theo? Với cơ chế kéo (pull), bên nhận chủ động yêu cầu dữ liệu khi sẵn sàng. Với cơ chế đẩy (push), bên phát thông báo cho bên nhận ngay khi có dữ liệu mới. Mỗi cách có ưu điểm riêng về quyền kiểm soát, độ trễ và cách sử dụng tài nguyên.

Trong ứng dụng Java, vòng lặp đọc **Iterator** hoặc thao tác trên **Stream** thường thể hiện cách kéo. Callback và listener thường thể hiện cách đẩy. Reactive Streams kết hợp hai ý tưởng: Subscriber gửi nhu cầu bằng **request(n)**, còn Publisher truyền các phần tử bằng tín hiệu **onNext** khi có thể đáp ứng nhu cầu đó. Đây là nền tảng của backpressure trong Project Reactor và các thư viện tương thích.

### 1. Cơ chế kéo: bên nhận chủ động lấy dữ liệu

Với pull, consumer điều khiển nhịp đọc. Nó yêu cầu hoặc lấy phần tử kế tiếp khi đã xử lý xong phần tử trước đó. Nguồn dữ liệu không cần gửi liên tục đến một consumer chưa sẵn sàng.

Ví dụ đơn giản với **Iterator**:

~~~java
import java.util.Iterator;

Iterator<OrderEvent> iterator = eventRepository.findEvents().iterator();

while (iterator.hasNext()) {
    OrderEvent event = iterator.next();
    process(event);
}
~~~

Vòng lặp gọi **hasNext()** và **next()** để lấy dữ liệu theo nhu cầu. Nếu **process** xử lý tuần tự, phần tử kế tiếp chỉ được lấy sau khi phần tử hiện tại đã xử lý xong. Consumer có quyền kiểm soát nhịp đọc và có thể dừng vòng lặp khi không cần thêm dữ liệu.

Java Stream cũng thường được tiêu thụ theo cách kéo:

~~~java
import java.util.stream.Stream;

try (Stream<OrderEvent> events = eventRepository.streamEvents()) {
    events
        .filter(OrderEvent::isRelevant)
        .map(this::toNotification)
        .forEach(this::sendNotification);
}
~~~

Các phép toán trung gian của Stream thường được thực thi lười; thao tác kết thúc như **forEach** bắt đầu quá trình duyệt nguồn. Khi consumer yêu cầu phần tử tiếp theo, pipeline lấy dữ liệu từ nguồn và áp dụng các phép biến đổi. **Stream** là API xử lý dữ liệu đồng bộ theo mô hình pull; nó không tự cung cấp giao thức truyền tín hiệu bất đồng bộ hoặc backpressure giữa các thành phần độc lập.

Pull phù hợp khi consumer cần kiểm soát tốc độ đọc, xử lý theo lô hoặc truy vấn nguồn theo từng trang. Nó cũng thuận tiện khi nguồn hỗ trợ cursor, iterator hoặc API poll. Tuy nhiên, nếu dữ liệu chỉ xuất hiện rải rác theo thời gian, consumer có thể phải chờ hoặc liên tục kiểm tra nguồn. Khi nhiều nguồn cập nhật độc lập, việc tự quản lý vòng lặp chờ và ghép dữ liệu có thể phức tạp.

### 2. Cơ chế đẩy: bên phát thông báo khi có dữ liệu

Với push, producer quyết định khi nào phát tín hiệu. Consumer đăng ký một callback hoặc listener; khi có sự kiện, producer gọi callback tương ứng. Consumer không cần liên tục hỏi nguồn xem đã có dữ liệu mới chưa.

Ví dụ một nguồn sự kiện đơn hàng:

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

interface OrderEventListener {
    void onEvent(OrderEvent event);
}

final class OrderEventBus {
    private final List<OrderEventListener> listeners =
        new CopyOnWriteArrayList<>();

    AutoCloseable register(OrderEventListener listener) {
        listeners.add(listener);
        return () -> listeners.remove(listener);
    }

    void publish(OrderEvent event) {
        for (OrderEventListener listener : listeners) {
            listener.onEvent(event);
        }
    }
}
~~~

Khi trạng thái đơn hàng thay đổi, producer gọi **publish**; mỗi listener đã đăng ký nhận sự kiện qua **onEvent**. Cách làm này phù hợp với giao diện cần cập nhật ngay, callback từ thư viện I/O, hoặc hệ thống thông báo sự kiện.

Push giúp giảm việc thăm dò liên tục và có thể giảm độ trễ giữa lúc sự kiện phát sinh với lúc consumer biết đến sự kiện. Nhưng nếu producer phát nhanh hơn consumer xử lý, callback có thể làm chậm chính luồng phát hoặc dữ liệu có thể tích tụ trong hàng đợi trung gian. Ví dụ trên gọi listener đồng bộ, nên một listener chậm có thể làm chậm lời gọi **publish**. Nếu chuyển callback sang executor hoặc hàng đợi, hệ thống phải xác định giới hạn hàng đợi, chính sách khi đầy và cách xử lý lỗi.

Một listener đơn giản thường không có cách chuẩn để nói rằng nó chỉ muốn nhận thêm 10 sự kiện. Producer có thể tiếp tục phát dù consumer đang quá tải. Vì vậy, push thuần túy cần một chính sách điều tiết riêng nếu tốc độ phát và tốc độ xử lý khác nhau đáng kể.

### 3. So sánh pull và push

| Khía cạnh | Pull | Push |
| --- | --- | --- |
| Ai quyết định nhịp trao đổi? | Consumer yêu cầu phần tử khi sẵn sàng | Producer phát khi có dữ liệu |
| Cách tiêu thụ phổ biến | Iterator, cursor, truy vấn theo trang | Callback, listener, notification |
| Khi nguồn không có dữ liệu | Consumer có thể chờ hoặc hỏi lại | Consumer thường chờ tín hiệu |
| Khi consumer chậm | Có thể giảm hoặc dừng yêu cầu tiếp theo | Cần hàng đợi, bộ đệm hoặc cơ chế điều tiết |
| Điểm cần quản lý | Vòng lặp đọc, thời gian chờ, phân trang | Đăng ký, hủy đăng ký, tốc độ phát và hàng đợi |

Không có cơ chế nào luôn tốt hơn. Pull tạo quyền kiểm soát rõ cho bên tiêu thụ; push phù hợp với sự kiện xuất hiện bất chợt. Hệ thống thực tế thường kết hợp hai cách tùy theo khả năng của nguồn dữ liệu và yêu cầu nghiệp vụ.

### 4. Reactive Streams: yêu cầu theo kiểu kéo, truyền theo kiểu đẩy

Reactive Streams định nghĩa một giao thức bất đồng bộ gồm **Publisher**, **Subscriber** và **Subscription**. Subscriber đăng ký với Publisher. Publisher gọi **onSubscribe(subscription)** để cấp Subscription; sau đó Subscriber gọi **request(n)** để yêu cầu số phần tử muốn nhận. Khi có dữ liệu và còn nhu cầu đã được yêu cầu, Publisher truyền phần tử qua **onNext(value)**.

Trình tự rút gọn:

~~~text
Subscriber                    Publisher
    |                             |
    |--------- subscribe() ------>|
    |<----- onSubscribe(sub) -----|
    |                             |
    |--------- request(2) ------->|
    |<--------- onNext(A) --------|
    |<--------- onNext(B) --------|
    |                             |
    |--------- request(1) ------->|
    |<--------- onNext(C) --------|
    |                             |
    |<------- onComplete() -------|
~~~

Trong ví dụ, Subscriber yêu cầu hai phần tử đầu tiên rồi yêu cầu thêm một phần tử. Publisher truyền dữ liệu bằng các tín hiệu đẩy, nhưng chỉ trong giới hạn nhu cầu mà Subscriber đã công bố. Khi hoàn tất bình thường, Publisher gửi **onComplete**; nếu xảy ra lỗi, Publisher gửi **onError**. Subscriber có thể gọi **cancel()** để hủy đăng ký và ngừng yêu cầu thêm dữ liệu.

**request(n)** là một thông báo nhu cầu, không phải lời gọi đồng bộ kiểu **next()** để lấy đúng một phần tử ngay tại thời điểm gọi. Publisher có thể phát các phần tử bất đồng bộ sau đó, miễn tuân thủ tổng nhu cầu đã được yêu cầu. Các yêu cầu dương được cộng dồn; **Long.MAX_VALUE** biểu thị nhu cầu không giới hạn. Yêu cầu không hợp lệ, chẳng hạn số âm hoặc bằng không, dẫn đến tín hiệu lỗi theo hợp đồng.

Do đó, Reactive Streams không đơn thuần là pull hay push. Subscriber dùng ý tưởng pull để cho biết khả năng tiếp nhận; Publisher dùng ý tưởng push để chuyển dữ liệu khi sẵn sàng. Cách phối hợp này thường được gọi là mô hình đẩy–kéo (push–pull) hoặc push có kiểm soát nhu cầu.

### 5. Backpressure điều hòa tốc độ giữa hai phía

Giả sử một nguồn phát 15.000 sự kiện mỗi giây, trong khi consumer chỉ xử lý được 3.000 sự kiện mỗi giây. Nếu producer liên tục đẩy sự kiện vào một hàng đợi không giới hạn, hàng đợi sẽ tăng dần, tiêu thụ bộ nhớ và có thể làm ứng dụng dừng hoạt động.

Backpressure cho phép consumer giới hạn lượng dữ liệu mà nó sẵn sàng nhận. Trong Reactive Streams, cơ chế cơ bản là **Subscription.request(n)**. Publisher tuân theo nhu cầu đã được yêu cầu thay vì phát vô hạn phần tử cho subscriber. Khi consumer xử lý xong và có khả năng nhận thêm, nó yêu cầu thêm dữ liệu.

Backpressure chỉ có thể điều tiết những nguồn và thành phần tham gia hoặc có thể được chuyển đổi sang giao thức nhu cầu. Một thiết bị, callback thư viện hoặc hệ thống bên ngoài có thể tiếp tục phát dù consumer đã yêu cầu dừng. Khi đó, adapter cần chọn chính sách cụ thể:

- **Buffer:** lưu tạm một lượng phần tử có giới hạn để hấp thụ chênh lệch ngắn hạn.
- **Drop:** bỏ phần tử mới hoặc phần tử theo quy tắc đã chọn khi quá tải, nếu nghiệp vụ cho phép mất dữ liệu.
- **Latest:** chỉ giữ giá trị mới nhất khi các giá trị trung gian không còn quan trọng.
- **Error:** báo lỗi khi vượt giới hạn để hệ thống có thể xử lý tình trạng quá tải một cách tường minh.

Chính sách phải phù hợp với ý nghĩa dữ liệu. Với sự kiện thanh toán hoặc chuyển trạng thái đơn hàng, bỏ sự kiện có thể làm sai nghiệp vụ. Với dữ liệu nhiệt độ cập nhật liên tục, giữ giá trị mới nhất có thể hữu ích hơn việc xử lý mọi mẫu cũ. Buffer cũng cần giới hạn và quy tắc khi đầy; một hàng đợi không giới hạn chỉ trì hoãn thời điểm cạn bộ nhớ.

### 6. Kết hợp pull và push trong Project Reactor

Project Reactor biểu diễn luồng bằng **Flux<T>** và kết quả có không hoặc một phần tử bằng **Mono<T>**. Cả hai triển khai **Publisher**, vì vậy có thể tham gia giao thức Reactive Streams.

Một nguồn đồng bộ có thể được chuyển thành **Flux**:

~~~java
import reactor.core.publisher.Flux;

Flux<OrderEvent> events =
    Flux.fromIterable(eventRepository.findEvents());

events
    .filter(OrderEvent::isRelevant)
    .map(this::toNotification)
    .subscribe(this::sendNotification);
~~~

**Flux.fromIterable** chuyển một Iterable thành Publisher. Khi có subscriber và nhu cầu, publisher duyệt nguồn để phát các phần tử. Nguồn ban đầu được đọc theo kiểu pull, còn dữ liệu sau đó được truyền qua các tín hiệu reactive. Đây là cách đưa một nguồn dữ liệu quen thuộc vào pipeline có thể kết hợp với các publisher khác.

Với consumer cần kiểm soát lượng yêu cầu, Reactor cung cấp **BaseSubscriber**:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

Flux<OrderEvent> events = orderEventSource.events();

events.subscribe(new BaseSubscriber<OrderEvent>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(1);
    }

    @Override
    protected void hookOnNext(OrderEvent event) {
        process(event);
        request(1);
    }
});
~~~

Subscriber trong ví dụ chỉ yêu cầu một phần tử ban đầu. Sau khi **process** xử lý xong phần tử hiện tại, nó yêu cầu thêm một phần tử. Đây là cách minh họa demand theo từng phần tử. Trong ứng dụng thực tế, **process** cần hoàn tất công việc đồng bộ trước khi yêu cầu tiếp; nếu xử lý là I/O bất đồng bộ, nên biểu diễn thao tác đó thành Mono hoặc Flux và dùng các toán tử kết hợp có giới hạn concurrency thay vì chặn callback.

Nếu muốn yêu cầu theo lô, có thể dùng **limitRate** để điều chỉnh cách Reactor chuyển nhu cầu từ downstream lên upstream:

~~~java
import reactor.core.scheduler.Schedulers;

events
    .limitRate(64)
    .publishOn(Schedulers.parallel())
    .map(this::toNotification)
    .subscribe(this::sendNotification);
~~~

**limitRate(64)** chia nhu cầu upstream thành các đợt có kích thước giới hạn, giúp kiểm soát lượng phần tử được yêu cầu trước. **publishOn** chuyển các bước phía sau sang scheduler được chọn. Việc đổi scheduler không thay thế backpressure: nếu downstream chậm, nhu cầu vẫn cần được quản lý và mọi vùng đệm cần có giới hạn phù hợp.

### 7. Chuyển nguồn push bên ngoài thành Publisher

Một nguồn callback thường phát dữ liệu theo kiểu push. Để đưa nó vào Reactor, ta cần một adapter đăng ký listener, chuyển mỗi callback thành phần tử và hủy listener khi subscription kết thúc. **Flux.create** có thể dùng để kết nối callback với **FluxSink**:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.FluxSink;

Flux<OrderEvent> eventFlux =
    Flux.create(sink -> {
        AutoCloseable registration =
            externalOrderBus.register(sink::next);

        sink.onDispose(() -> {
            try {
                registration.close();
            } catch (Exception error) {
                // Ghi log hoặc xử lý lỗi đóng đăng ký theo chính sách ứng dụng.
            }
        });
    }, FluxSink.OverflowStrategy.LATEST);
~~~

Đây là ví dụ khung: **externalOrderBus.register** đại diện cho API đăng ký callback của hệ thống bên ngoài. Khi callback phát sự kiện, **sink.next** chuyển sự kiện thành phần tử của Flux. Khi subscription bị hủy hoặc kết thúc, **onDispose** đóng đăng ký để giải phóng tài nguyên.

Nguồn callback không nhất thiết tuân theo demand. Vì vậy, adapter phải xác định cách xử lý khi sự kiện đến nhanh hơn downstream. **OverflowStrategy.LATEST** phù hợp khi chỉ cần giữ giá trị mới nhất; nếu mọi sự kiện đều quan trọng, cần một chiến lược buffer có giới hạn hoặc cơ chế xác nhận/đọc lại từ nguồn. Với nhiều luồng producer đồng thời, cần chọn API tạo Flux phù hợp và bảo đảm nguồn callback an toàn luồng.

### 8. Kết hợp snapshot kiểu pull với cập nhật kiểu push

Một mẫu thường gặp trong ứng dụng là lấy trạng thái hiện tại từ API rồi tiếp tục nhận sự kiện thay đổi. Ví dụ, màn hình đơn hàng gọi REST để lấy snapshot hiện tại, sau đó mở WebSocket để nhận cập nhật. Snapshot là thao tác pull; sự kiện trực tiếp là push.

Mẫu này có một vấn đề về thứ tự. Nếu trạng thái thay đổi sau khi snapshot được tạo nhưng trước khi WebSocket đăng ký thành công, ứng dụng có thể bỏ lỡ thay đổi đó. Nếu sự kiện đến trước snapshot nhưng được áp dụng sau, trạng thái cũ từ snapshot có thể ghi đè dữ liệu mới.

Để phối hợp an toàn, nguồn dữ liệu nên cung cấp sequence number, version hoặc offset. Một quy trình thường dùng là:

1. Đọc snapshot kèm version tại thời điểm chụp.
2. Đăng ký hoặc đọc lại luồng sự kiện từ version/offset đó.
3. Bỏ qua sự kiện có version đã được áp dụng và xử lý sự kiện mới theo thứ tự.
4. Nếu phát hiện khoảng trống version, yêu cầu đọc bù hoặc lấy snapshot mới.

Nếu hệ thống hỗ trợ đăng ký trước rồi lấy snapshot, cần xác định cách giữ các sự kiện đến trong lúc snapshot đang tải và cách ghép chúng để không áp dụng sai thứ tự. Chỉ ghép một **Mono<Snapshot>** với một **Flux<Event>** không tự bảo đảm tính nhất quán; giao thức giữa hai nguồn phải định nghĩa điểm đồng bộ.

### 9. Chọn mô hình trao đổi theo yêu cầu

Khi thiết kế một luồng dữ liệu, hãy xác định ai có thể điều khiển tốc độ, nguồn có hỗ trợ demand hay không, và dữ liệu có được phép mất hay không. Pull thường hợp lý cho truy vấn theo trang, cursor và xử lý theo lô. Push thường hợp lý cho thông báo tức thời và sự kiện phát sinh không đều. Reactive Streams hữu ích khi cần truyền bất đồng bộ nhưng vẫn muốn consumer công bố nhu cầu để giới hạn lượng dữ liệu đang được gửi.

Trong hệ sinh thái Java, có thể kết hợp các mô hình: đọc dữ liệu bằng API pull, chuyển thành **Flux**, nhận callback từ nguồn push qua adapter, rồi dùng các toán tử Reactor để ghép và biến đổi. Cần quản lý rõ buffer, demand, thứ tự, lỗi và vòng đời subscription. Những quyết định đó giúp pipeline vừa phản ứng kịp thời với dữ liệu mới vừa giữ được giới hạn tài nguyên khi tốc độ giữa producer và consumer không cân bằng.
