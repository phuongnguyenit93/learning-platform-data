# Nguồn nóng: dữ liệu tồn tại độc lập với thời điểm đăng ký

Trong lập trình reactive, một nguồn dữ liệu có thể bắt đầu phát sự kiện theo vòng đời riêng của nó. Sự kiện có thể xuất hiện dù hiện tại chưa có Subscriber nào đăng ký. Khi một Subscriber tham gia sau đó, nó thường chỉ quan sát được những sự kiện phát từ thời điểm tham gia trở đi. Đây là đặc điểm cốt lõi của **hot publisher** (Publisher nóng).

Bài học thuộc chương **Nguồn nóng và lạnh** của module **REACTIVE_PROGRAMMING**. Module giúp người học tư duy theo các luồng sự kiện bất đồng bộ, hiểu hợp đồng Publisher–Subscriber và backpressure của Reactive Streams, đồng thời thực hành Mono, Flux, toán tử và kiểm thử pipeline trong Java. Với nguồn nóng, điều quan trọng là hiểu vòng đời phát dữ liệu, thời điểm đăng ký và chính sách giữ lại sự kiện.

## Nguồn nóng hoạt động như thế nào?

Với một Publisher nóng, quá trình tạo dữ liệu không phụ thuộc vào từng lần subscribe. Nguồn có thể nhận dữ liệu từ hệ thống bên ngoài hoặc từ một tiến trình đang chạy, rồi phát dữ liệu tới các Subscriber hiện có. Việc đăng ký chỉ kết nối Subscriber với luồng sự kiện đang diễn ra.

Hãy hình dung một dịch vụ theo dõi trạng thái đơn hàng. Dịch vụ nhận sự kiện từ hệ thống xử lý đơn và phát lần lượt các thay đổi:

1. Đơn hàng được tạo.
2. Đơn hàng được thanh toán.
3. Đơn hàng được bàn giao cho đơn vị vận chuyển.

Nếu màn hình theo dõi đăng ký sau khi sự kiện tạo đơn đã phát, màn hình có thể chỉ nhận được sự kiện thanh toán và bàn giao. Việc đăng ký không làm cho nguồn phát lại sự kiện tạo đơn, trừ khi nguồn có chính sách lưu và phát lại lịch sử.

Một Publisher nóng thường có các đặc điểm sau:

- Nguồn dữ liệu có vòng đời riêng và có thể phát khi không có Subscriber.
- Nhiều Subscriber có thể quan sát cùng một luồng sự kiện đang diễn ra.
- Subscriber đăng ký muộn có thể bỏ lỡ những phần tử đã phát.
- Mỗi Subscriber không nhất thiết nhận cùng một lịch sử; kết quả phụ thuộc thời điểm đăng ký và chính sách replay.
- Việc đăng ký không tự tạo một lần thực thi độc lập của nguồn.

Điểm cuối giúp phân biệt nguồn nóng với nguồn lạnh. Với Publisher lạnh, mỗi lần subscribe thường khởi động một lần thực thi mới và Subscriber nhận luồng từ đầu. Với Publisher nóng, nguồn đã có thể hoạt động trước khi Subscriber đăng ký.

## Thời điểm đăng ký quyết định những gì Subscriber quan sát

Giả sử một nguồn nóng phát các sự kiện A, B, C theo thứ tự thời gian. Subscriber thứ nhất đăng ký trước A; Subscriber thứ hai đăng ký sau B nhưng trước C.

~~~mermaid
sequenceDiagram
    participant P as Nguồn nóng
    participant S1 as Subscriber 1
    participant S2 as Subscriber 2
    S1->>P: subscribe
    P-->>S1: A
    P-->>S1: B
    S2->>P: subscribe
    P-->>S1: C
    P-->>S2: C
~~~

Subscriber 1 quan sát A, B, C. Subscriber 2 chỉ quan sát C. Không có lỗi giao thức khi Subscriber 2 không nhận A và B: các phần tử đó đã được phát trước khi Subscriber này tham gia.

Tuy nhiên, không nên kết luận rằng mọi Publisher nóng đều bỏ lịch sử. “Nóng” mô tả sự độc lập giữa quá trình phát dữ liệu và thời điểm subscribe. Việc giữ lại lịch sử là một chính sách riêng. Một nguồn nóng có thể:

- Chỉ phát cho Subscriber đang kết nối, không lưu lịch sử.
- Lưu một số phần tử gần nhất để Subscriber mới nhận lại.
- Lưu toàn bộ lịch sử trong giới hạn được cấu hình.
- Lưu dữ liệu ở một hệ thống bên ngoài và cho phép đọc lại theo offset hoặc thời điểm.

Vì vậy, khi thiết kế hợp đồng của một luồng nóng, cần xác định rõ Subscriber mới sẽ nhận dữ liệu trực tiếp từ hiện tại hay nhận thêm dữ liệu lịch sử.

## Tạo một nguồn nóng bằng Sinks trong Project Reactor

Trong Project Reactor, **Sinks** cung cấp API để mã ứng dụng chủ động phát tín hiệu. Một Sink có thể cung cấp Publisher thông qua **asFlux()** hoặc **asMono()**. Với luồng sự kiện nhiều phần tử, có thể dùng **Sinks.Many**.

Ví dụ dưới đây tạo một nguồn multicast. Subscriber đang kết nối cùng quan sát các sự kiện được phát; Subscriber đăng ký sau không tự nhận lại những sự kiện đã phát trước thời điểm đăng ký:

~~~java
import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

Sinks.Many<String> orderEvents =
    Sinks.many().multicast().onBackpressureBuffer();

Flux<String> liveOrders = orderEvents.asFlux();

Disposable first = liveOrders.subscribe(
    event -> System.out.println("Màn hình A: " + event)
);

orderEvents.tryEmitNext("ORDER_CREATED").orThrow();

Disposable second = liveOrders.subscribe(
    event -> System.out.println("Màn hình B: " + event)
);

orderEvents.tryEmitNext("ORDER_PAID").orThrow();

first.dispose();
second.dispose();
~~~

Diễn biến của ví dụ:

| Thời điểm | Sự kiện | Màn hình A | Màn hình B |
|---|---|---|---|
| A đăng ký | Chưa có | Đã kết nối | Chưa kết nối |
| Nguồn phát | ORDER_CREATED | Nhận sự kiện | Chưa nhận |
| B đăng ký | Chưa có | Đã kết nối | Đã kết nối |
| Nguồn phát | ORDER_PAID | Nhận sự kiện | Nhận sự kiện |

Lệnh **asFlux()** tạo góc nhìn Publisher để các thành phần khác đăng ký. Việc gọi **tryEmitNext** mới là hành động phát sự kiện. Hai thao tác này tách vai trò của bên phát dữ liệu khỏi bên tiêu thụ dữ liệu: thành phần phát giữ Sink, còn thành phần nhận chỉ cần Flux.

Trong ứng dụng thực tế, nguồn phát có thể nằm trong một adapter nhận callback từ WebSocket, message broker, cảm biến hoặc một API sự kiện. Adapter chuyển mỗi sự kiện nhận được thành một lần phát qua Sink. Các tầng nghiệp vụ phía sau chỉ cần subscribe vào Flux đã được cung cấp.

## Chính sách replay: Subscriber muộn có nhận được lịch sử không?

Một nguồn nóng có thể cần giữ lại dữ liệu để Subscriber mới không bỏ lỡ thông tin quan trọng. Reactor cung cấp các loại replay sink cho mục đích này.

Ví dụ sau giữ lại tối đa hai sự kiện gần nhất:

~~~java
Sinks.Many<Integer> replaySink = Sinks.many().replay().limit(2);
Flux<Integer> replayingEvents = replaySink.asFlux();

replaySink.tryEmitNext(10).orThrow();
replaySink.tryEmitNext(20).orThrow();
replaySink.tryEmitNext(30).orThrow();

StepVerifier.create(replayingEvents)
    .expectNext(20, 30)
    .then(() -> replaySink.tryEmitNext(40).orThrow())
    .expectNext(40)
    .thenCancel()
    .verify();
~~~

Khi Subscriber bắt đầu đăng ký, Sink phát lại hai phần tử gần nhất là 20 và 30, sau đó tiếp tục phát sự kiện mới là 40. Nguồn vẫn là nguồn nóng vì việc phát 10, 20 và 30 đã diễn ra trước khi Subscriber đăng ký. Replay chỉ bổ sung chính sách lưu và phát lại một phần lịch sử.

Một số lựa chọn thường gặp:

| Loại nguồn | Hành vi với Subscriber đăng ký muộn | Khi phù hợp |
|---|---|---|
| Multicast không replay | Chỉ nhận sự kiện mới trong thời gian kết nối | Trạng thái trực tiếp, thông báo tức thời |
| Replay giới hạn số phần tử | Nhận lại một số sự kiện gần nhất | Bảng điều khiển cần trạng thái gần đây |
| Replay theo thời gian | Nhận lại sự kiện trong một khoảng thời gian | Luồng cập nhật có cửa sổ lịch sử ngắn |
| Lưu trữ ngoài nguồn phát | Có thể đọc lại theo offset hoặc mốc thời gian nếu hệ thống hỗ trợ | Event log, message broker, lịch sử giao dịch |

Chính sách replay cần được chọn theo yêu cầu nghiệp vụ và chi phí bộ nhớ. Giữ toàn bộ lịch sử trong bộ nhớ có thể làm bộ nhớ tăng liên tục nếu nguồn phát lâu dài. Với lịch sử lớn hoặc cần khôi phục sau khi ứng dụng khởi động lại, nên cân nhắc hệ thống lưu trữ hoặc message broker chuyên dụng.

## Kết hợp nguồn nóng với Flux và ConnectableFlux

Một Publisher lạnh có thể được chuyển thành luồng chia sẻ bằng các toán tử của Reactor. Ví dụ, **publish()** tạo một **ConnectableFlux**: nguồn chưa bắt đầu phát chỉ vì có Subscriber; lời gọi **connect()** mới khởi động việc phát dữ liệu tới các Subscriber đang kết nối.

~~~java
ConnectableFlux<Long> sharedClock =
    Flux.interval(Duration.ofMillis(500)).publish();

sharedClock.subscribe(value ->
    System.out.println("Đồng hồ A: " + value)
);

sharedClock.subscribe(value ->
    System.out.println("Đồng hồ B: " + value)
);

sharedClock.connect();
~~~

Hai Subscriber cùng nhận các nhịp từ một lần chạy của nguồn. Nếu một Subscriber khác đăng ký sau khi kết nối đã hoạt động, Subscriber đó tham gia vào luồng đang chạy và không mặc nhiên nhận lại các nhịp trước đó.

Có thể dùng **autoConnect(n)** để tự kết nối khi đủ số Subscriber:

~~~java
Flux<Long> sharedAfterFirstSubscriber =
    Flux.interval(Duration.ofMillis(500))
        .publish()
        .autoConnect(1);
~~~

Với ngưỡng 1, lần subscribe đầu tiên kích hoạt kết nối. Các Subscriber tiếp theo chia sẻ nguồn đã chạy. Đây là cách hữu ích khi muốn chuyển một nguồn vốn được tạo theo kiểu lạnh thành nguồn chia sẻ có hành vi nóng sau khi bắt đầu.

**share()** là một lựa chọn ngắn gọn cho trường hợp chia sẻ nguồn qua cơ chế ref-count:

~~~java
Flux<Long> shared = Flux.interval(Duration.ofMillis(500)).share();
~~~

Khác với một kết nối được giữ cố định bằng **autoConnect**, ref-count có thể ngắt kết nối khi số Subscriber giảm về không và kết nối lại khi có Subscriber mới. Vì vậy, Subscriber đến sau có thể tham gia một lần chạy mới nếu nguồn đã bị ngắt. Hãy chọn toán tử dựa trên vòng đời mong muốn, đặc biệt khi nguồn có side effect hoặc chi phí khởi tạo cao.

## Backpressure và Subscriber xử lý chậm

Nguồn nóng có thể phát sự kiện theo nhịp riêng, trong khi Subscriber xử lý chậm hơn tốc độ phát. Đây là tình huống cần thiết kế backpressure và chính sách quá tải. Hợp đồng Reactive Streams cho phép Subscriber yêu cầu số phần tử thông qua **Subscription.request(n)**; nguồn và toán tử cần phối hợp để không buộc Subscriber nhận nhiều phần tử hơn nhu cầu đã yêu cầu.

Với Sink multicast có buffer, các phần tử có thể được giữ lại để chờ Subscriber yêu cầu. Tuy nhiên, buffer có giới hạn thực tế. Nếu tốc độ phát liên tục cao hơn tốc độ tiêu thụ, hàng đợi có thể đầy và lần phát tiếp theo thất bại. Ứng dụng phải quan sát kết quả phát, chọn dung lượng phù hợp và quyết định cách xử lý khi quá tải.

Một số chính sách multicast trong Reactor có ý nghĩa khác nhau:

| Chính sách | Hành vi khi Subscriber không có nhu cầu tức thời | Cân nhắc |
|---|---|---|
| **onBackpressureBuffer()** | Đệm phần tử để Subscriber tiêu thụ theo nhu cầu | Cần giới hạn và theo dõi nguy cơ đầy buffer |
| **directAllOrNothing()** | Không chuyển sự kiện nếu một Subscriber không sẵn sàng nhận | Giữ tính đồng bộ giữa các Subscriber, nhưng một Subscriber chậm ảnh hưởng cả nhóm |
| **directBestEffort()** | Chuyển tới Subscriber đang có nhu cầu, bỏ qua Subscriber chưa sẵn sàng | Phù hợp khi chấp nhận mất sự kiện ở từng Subscriber chậm |

Đối với sự kiện nghiệp vụ như thanh toán hoặc thay đổi trạng thái đơn hàng, bỏ sự kiện có thể không chấp nhận được. Khi đó, cần buffer có giới hạn, cơ chế retry hoặc lưu trữ bền vững ở upstream. Với dữ liệu đo lường hoặc cập nhật giao diện tần suất cao, có thể chấp nhận bỏ bớt sự kiện cũ hoặc chỉ giữ giá trị mới nhất, nếu nghiệp vụ cho phép.

Khi phát bằng Sink, hãy kiểm tra kết quả của **tryEmitNext**:

~~~java
Sinks.EmitResult result = orderEvents.tryEmitNext("ORDER_SHIPPED");

if (result.isFailure()) {
    // Ghi nhận lỗi phát và áp dụng chính sách phù hợp.
    System.err.println("Không thể phát sự kiện: " + result);
}
~~~

Kết quả có thể cho biết Sink đã kết thúc, đã bị hủy, buffer đầy, không có Subscriber theo chính sách đang dùng hoặc có lần phát đồng thời không được tuần tự hóa. Không nên bỏ qua kết quả này trong hệ thống cần độ tin cậy cao. Nếu nhiều thread cùng phát vào một Sink, cần tuần tự hóa nguồn phát hoặc xử lý tình huống phát đồng thời theo API của Reactor.

## Kiểm thử thời điểm đăng ký và replay

Kiểm thử nguồn nóng nên điều khiển rõ thứ tự subscribe và emit. **StepVerifier** có thể thực hiện hành động phát dữ liệu sau khi Subscriber đã đăng ký:

~~~java
Sinks.Many<Integer> liveSink =
    Sinks.many().multicast().onBackpressureBuffer();

StepVerifier.create(liveSink.asFlux())
    .then(() -> liveSink.tryEmitNext(1).orThrow())
    .expectNext(1)
    .then(() -> liveSink.tryEmitNext(2).orThrow())
    .expectNext(2)
    .thenCancel()
    .verify();
~~~

Kiểm thử này xác nhận Subscriber nhận các phần tử được phát trong thời gian đăng ký. Để kiểm tra chính sách replay, có thể phát dữ liệu trước khi tạo StepVerifier:

~~~java
Sinks.Many<Integer> history =
    Sinks.many().replay().limit(2);

history.tryEmitNext(1).orThrow();
history.tryEmitNext(2).orThrow();
history.tryEmitNext(3).orThrow();

StepVerifier.create(history.asFlux())
    .expectNext(2, 3)
    .thenCancel()
    .verify();
~~~

Kết quả mong đợi chứng minh Subscriber muộn nhận hai phần tử gần nhất theo chính sách replay. Hai kiểm thử mô tả hai hợp đồng khác nhau: multicast trực tiếp quan sát sự kiện đang diễn ra, còn replay sink cung cấp thêm một phần lịch sử.

## Những câu hỏi cần trả lời khi thiết kế nguồn nóng

Trước khi đưa một Publisher nóng vào ứng dụng, hãy xác định:

1. Ai sở hữu vòng đời của nguồn và điều gì khiến nguồn bắt đầu hoặc kết thúc?
2. Sự kiện có thể phát khi không có Subscriber không?
3. Subscriber đăng ký muộn cần nhận dữ liệu từ thời điểm hiện tại hay cần lịch sử?
4. Nếu cần lịch sử, giữ bao nhiêu phần tử hoặc trong bao lâu? Lịch sử có cần tồn tại sau khi ứng dụng khởi động lại không?
5. Khi Subscriber xử lý chậm, hệ thống đệm, từ chối, bỏ sự kiện hay lưu trữ để xử lý lại?
6. Khi phát lỗi hoặc nguồn kết thúc, các Subscriber và thành phần phát dữ liệu xử lý trạng thái đó như thế nào?

Nguồn nóng hữu ích khi nhiều thành phần cần quan sát cùng một dòng sự kiện đang diễn ra, chẳng hạn trạng thái đơn hàng, thông báo thời gian thực, dữ liệu cảm biến hoặc cập nhật giao diện. Hiểu rõ thời điểm đăng ký và chính sách replay giúp tránh giả định rằng Subscriber nào cũng nhận được toàn bộ lịch sử. Kết hợp lựa chọn đó với backpressure, giới hạn buffer và kiểm thử thứ tự phát sẽ giúp pipeline reactive hoạt động ổn định hơn.
