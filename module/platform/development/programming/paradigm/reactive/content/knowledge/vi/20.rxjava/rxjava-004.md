# Subject và Processor: phát dữ liệu và chuyển tiếp tín hiệu

Trong chương **RxJava** của module `REACTIVE_PROGRAMMING`, ta học cách tổ chức các luồng sự kiện bất đồng bộ theo hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams, đồng thời thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Khi tích hợp callback, event listener hoặc một nguồn dữ liệu được đẩy từ bên ngoài, đôi khi ứng dụng cần một đối tượng vừa nhận dữ liệu từ producer vừa công bố dữ liệu cho nhiều consumer. RxJava cung cấp hai nhóm kiểu thường dùng cho nhu cầu này: **Subject** và **Processor**.

Subject thuộc mô hình `Observable`/`Observer`: nó nhận tín hiệu như một Observer và phát tín hiệu như một Observable. Processor thuộc mô hình `Flowable`/Reactive Streams: nó nhận tín hiệu như một Subscriber và phát tín hiệu như một Publisher, do đó tham gia vào hợp đồng backpressure. Hai nhóm có cách sử dụng gần nhau nhưng khác nhau ở giao thức tiêu thụ. Chọn đúng loại giúp ứng dụng kiểm soát được demand, xử lý tín hiệu kết thúc và tránh lỗi khi nhiều thread cùng phát dữ liệu.

## 1. Subject là cầu nối giữa Observer và Observable

Trong RxJava, `Subject<T>` vừa là một `Observable<T>`, vừa là một `Observer<T>`. Producer có thể gọi `onNext`, `onError` hoặc `onComplete` trên Subject; consumer có thể subscribe để nhận các tín hiệu đó.

```java
import io.reactivex.rxjava3.subjects.PublishSubject;
import io.reactivex.rxjava3.subjects.Subject;

Subject<String> events = PublishSubject.<String>create();

events.subscribe(
    value -> System.out.println("Nhận: " + value),
    error -> System.err.println("Lỗi: " + error.getMessage()),
    () -> System.out.println("Nguồn đã hoàn tất")
);

events.onNext("ORDER_CREATED");
events.onNext("ORDER_PAID");
events.onComplete();
```

`PublishSubject` phát các phần tử mới đến những Observer đang đăng ký. Subscriber đăng ký sau khi một sự kiện đã phát sẽ không nhận lại sự kiện cũ. Subject là nguồn nóng: việc gọi `onNext` có thể phát ngay đến các Observer hiện tại, không cần chờ một subscription mới bắt đầu nguồn.

Một Subject cũng có thể nhận dữ liệu từ một Observable khác vì nó triển khai `Observer`:

```java
Observable<Event> upstream = eventSource.readEvents();
Subject<Event> bridge = PublishSubject.create();

upstream.subscribe(bridge);
bridge.subscribe(this::handleEvent);
```

Trong ví dụ, `bridge` nhận tín hiệu từ `upstream` và phát chúng cho Observer đăng ký vào bridge. Nếu cần nhận sự kiện ngay từ đầu, hãy thiết lập các Observer cần thiết trước khi nguồn nóng bắt đầu phát để tránh bỏ lỡ những tín hiệu đến sớm.

## 2. Các loại Subject và chính sách phát lại

RxJava có nhiều implementation Subject. Chúng khác nhau chủ yếu ở cách xử lý subscriber đến muộn:

| Loại | Dữ liệu subscriber mới nhận được | Trường hợp phù hợp |
|---|---|---|
| `PublishSubject` | Chỉ các phần tử phát sau khi subscribe | Event bus, thông báo trực tiếp |
| `BehaviorSubject` | Giá trị gần nhất, sau đó là các phần tử mới | Trạng thái hiện tại như lựa chọn giao diện hoặc trạng thái thiết bị |
| `ReplaySubject` | Lịch sử đã lưu theo chính sách replay | Cache sự kiện hoặc phát lại một phần lịch sử |
| `AsyncSubject` | Chỉ phần tử cuối cùng khi nguồn hoàn tất thành công | Chia sẻ kết quả cuối của một phép tính hữu hạn |

Ví dụ `BehaviorSubject` giữ giá trị mới nhất:

```java
BehaviorSubject<String> connectionState =
    BehaviorSubject.createDefault("DISCONNECTED");

connectionState.onNext("CONNECTING");
connectionState.onNext("CONNECTED");

connectionState.subscribe(state ->
    System.out.println("Trạng thái hiện tại: " + state)
);
```

Observer đăng ký sau sẽ nhận giá trị `CONNECTED` rồi tiếp tục nhận các cập nhật tiếp theo. Vì vậy, `BehaviorSubject` phù hợp khi consumer cần trạng thái mới nhất.

`ReplaySubject` có thể giới hạn số phần tử được giữ:

```java
ReplaySubject<Event> recentEvents = ReplaySubject.createWithSize(100);
```

Subscriber đến muộn nhận các phần tử còn nằm trong giới hạn replay. Không nên dùng replay không giới hạn cho luồng dài hạn nếu lịch sử có thể tăng liên tục, vì các phần tử được giữ lại sẽ chiếm bộ nhớ.

`AsyncSubject` chỉ phát giá trị cuối cùng khi nhận `onComplete`. Nếu nguồn kết thúc bằng `onError`, subscriber nhận lỗi thay vì giá trị cuối. Điều này phù hợp với kết quả cuối của một nguồn hữu hạn, không phù hợp với luồng sự kiện cần cập nhật liên tục.

## 3. Subject không có backpressure

Subject phát theo mô hình `Observable`, không có `Subscription.request(n)`. Observer không thể yêu cầu một lượng phần tử cụ thể hoặc báo cho Subject biết tốc độ tiêu thụ của mình. Nếu producer phát nhanh hơn consumer xử lý, Subject không tự điều tiết tốc độ phát theo demand.

Điều này có thể chấp nhận với các luồng sự kiện nhẹ, có tần suất được kiểm soát và consumer xử lý nhanh. Với luồng có thể phát burst lớn, cần cân nhắc:

- Đặt giới hạn hoặc hàng đợi ở tầng tiếp nhận trước khi gọi `onNext`.
- Chuyển dữ liệu sang một pipeline có chính sách buffer/drop rõ ràng.
- Dùng `Flowable` và Processor nếu cần tuân thủ backpressure.
- Theo dõi tốc độ phát, độ trễ xử lý và số sự kiện bị loại bỏ.

Không nên giả định rằng `observeOn` biến Subject thành nguồn có backpressure. `observeOn` chuyển callback sang scheduler khác và có thể dùng hàng đợi nội bộ, nhưng Observable vẫn không có giao thức request từ downstream để điều tiết producer.

## 4. Subject và an toàn khi nhiều thread phát tín hiệu

Các phương thức phát tín hiệu của Subject như `onNext`, `onError` và `onComplete` không nên được gọi đồng thời từ nhiều thread. ReactiveX yêu cầu tín hiệu được tuần tự hóa. Nếu nhiều callback hoặc thread có thể cùng phát vào một Subject, hãy dùng wrapper `toSerialized()`:

```java
Subject<Event> eventBus = PublishSubject.<Event>create()
    .toSerialized();

eventBus.onNext(new Event("A"));
```

Wrapper serialized tuần tự hóa các lời gọi phát tín hiệu, bao gồm cả tình huống phát lồng nhau (reentrant). Nó giúp bảo vệ hợp đồng tín hiệu khi producer cạnh tranh, nhưng không làm cho logic nghiệp vụ bên trong producer trở nên thread-safe và cũng không tự giới hạn tốc độ phát.

Hãy giữ một tham chiếu tới Subject đã được serialized và chỉ dùng tham chiếu đó để phát. Nếu một phần code vẫn gọi trực tiếp Subject gốc, đường phát đó có thể bỏ qua cơ chế tuần tự hóa.

## 5. Processor là cầu nối giữa Subscriber và Publisher

Trong RxJava 3, `FlowableProcessor<T>` là kiểu vừa là `Flowable<T>`, vừa triển khai vai trò `org.reactivestreams.Processor<T, T>`. Nó nhận tín hiệu từ một upstream Subscriber và công bố dữ liệu cho downstream Subscriber. Khác với Subject, phía downstream của Processor sử dụng `Subscription` và demand.

```java
import io.reactivex.rxjava3.processors.FlowableProcessor;
import io.reactivex.rxjava3.processors.PublishProcessor;

FlowableProcessor<Event> processor = PublishProcessor.create();

processor.subscribe(event -> handleEvent(event));

processor.onNext(new Event("ORDER_CREATED"));
processor.onComplete();
```

`PublishProcessor` phát các phần tử mới đến các Subscriber đang đăng ký. Vì đây là `Flowable`, Subscriber phải yêu cầu dữ liệu bằng `request(n)`. Processor có thể nhận dữ liệu từ một Publisher khác:

```java
Flowable<Event> upstream = eventSource.readFlowable();
FlowableProcessor<Event> processor = PublishProcessor.create();

upstream.subscribe(processor);
processor.subscribe(this::handleEvent);
```

Ở đây, Processor đứng giữa upstream và downstream. Nó nhận `onSubscribe`, `onNext`, `onError` và `onComplete` từ upstream; đồng thời cung cấp Publisher cho các Subscriber đăng ký vào nó.

## 6. Các loại Processor

Các Processor phổ biến có chính sách phát lại tương ứng với những Subject quen thuộc:

| Processor | Chính sách phát lại | Lưu ý |
|---|---|---|
| `PublishProcessor` | Chỉ phát phần tử mới cho Subscriber hiện tại | Không giữ lịch sử cho Subscriber đến muộn |
| `BehaviorProcessor` | Phát giá trị gần nhất và các phần tử mới | Phù hợp với trạng thái hiện tại; cần giá trị ban đầu nếu muốn có trạng thái ngay |
| `ReplayProcessor` | Phát lại phần lịch sử theo cấu hình | Cần giới hạn replay để kiểm soát bộ nhớ |
| `AsyncProcessor` | Phát phần tử cuối khi upstream hoàn tất | Dành cho kết quả cuối của nguồn hữu hạn |

Ví dụ một Processor giữ trạng thái kết nối gần nhất:

```java
BehaviorProcessor<String> state =
    BehaviorProcessor.createDefault("DISCONNECTED");

state.onNext("CONNECTED");

state.subscribe(value -> System.out.println("State: " + value));
```

Subscriber mới nhận giá trị trạng thái gần nhất theo chính sách của `BehaviorProcessor`, đồng thời vẫn chịu quy tắc demand của Flowable. Không nên nhầm việc phát lại trạng thái gần nhất với việc phát lại toàn bộ lịch sử; đó là hai chính sách khác nhau.

## 7. Backpressure và hành vi khi downstream không yêu cầu dữ liệu

Processor thuộc mô hình `Flowable`, vì vậy downstream có thể điều khiển lượng phần tử được phát qua `request(n)`. Tuy nhiên, từng implementation có chính sách riêng khi producer phát dữ liệu trong lúc một Subscriber chưa có demand.

Ví dụ, `PublishProcessor` không lưu hàng đợi riêng cho từng Subscriber. Nếu một Subscriber không yêu cầu dữ liệu mà Processor phát một phần tử mới, Subscriber đó có thể nhận `MissingBackpressureException` và bị kết thúc. Các Subscriber khác có demand vẫn có thể tiếp tục theo trạng thái subscription của chúng.

Có thể minh họa demand tường minh bằng `TestSubscriber`:

```java
FlowableProcessor<Integer> processor = PublishProcessor.create();
TestSubscriber<Integer> subscriber = new TestSubscriber<>(0L);

processor.subscribe(subscriber);

subscriber.request(1);
processor.onNext(10);

subscriber.assertValue(10);

processor.onComplete();
subscriber.assertComplete();
```

Subscriber bắt đầu với demand bằng không. Sau khi yêu cầu một phần tử, nó nhận `10`. Sau đó Processor phát tín hiệu hoàn tất. Nếu producer phát khi chưa có demand, hành vi phụ thuộc implementation và chính sách overflow của Processor; cần kiểm thử đúng loại Processor đang dùng.

Nếu một Subscriber downstream xử lý chậm, có thể đặt buffer ở nhánh tiêu thụ sau Processor:

```java
processor
    .onBackpressureBuffer(256)
    .subscribe(slowSubscriber);
```

Buffer nằm ở nhánh downstream này nhận demand từ Subscriber chậm và có thể yêu cầu dữ liệu từ Processor trong khi giữ tối đa 256 phần tử chờ cho Subscriber đó. Khi vượt giới hạn, nhánh này kết thúc bằng lỗi overflow. Có thể chọn chiến lược drop nếu nghiệp vụ cho phép mất phần tử. Nếu nhiều Subscriber có tốc độ khác nhau, mỗi nhánh cần chính sách phù hợp; buffer của một nhánh không tự bảo vệ các nhánh khác. Buffer không giới hạn có nguy cơ làm bộ nhớ tăng liên tục và không nên được dùng như cách xử lý quá tải mặc định.

## 8. Tuần tự hóa tín hiệu của Processor

Giống Subject, các phương thức nhận tín hiệu của Processor không nên bị gọi đồng thời nếu implementation yêu cầu tín hiệu tuần tự. RxJava cung cấp `toSerialized()` để tạo wrapper tuần tự hóa:

```java
FlowableProcessor<Event> eventProcessor =
    PublishProcessor.<Event>create().toSerialized();
```

Producer có thể phát qua `eventProcessor.onNext(...)` từ nhiều thread mà các tín hiệu được tuần tự hóa qua wrapper. Điều này bảo vệ thứ tự tín hiệu ở ranh giới Processor; thứ tự thực tế giữa các producer cạnh tranh vẫn phụ thuộc thời điểm chúng gọi vào wrapper. Nếu thứ tự nghiệp vụ phải theo sequence number hoặc event time, cần sắp xếp hoặc điều phối riêng thay vì dựa vào thứ tự thread giành được khóa.

Serialization cũng không thay thế backpressure. Nó bảo đảm tín hiệu không chồng lấn theo cách vi phạm hợp đồng, nhưng không tạo demand cho Subscriber và không giải quyết việc downstream tiêu thụ chậm.

## 9. Tín hiệu kết thúc và vòng đời

Subject và Processor đều tuân theo vòng đời tín hiệu kết thúc:

- `onComplete()` kết thúc nguồn thành công.
- `onError(Throwable)` kết thúc nguồn do lỗi.
- Sau một tín hiệu kết thúc, không được phát thêm `onNext` hoặc một tín hiệu kết thúc khác cho cùng nguồn.
- Không được phát `null` bằng `onNext`; Reactive Streams và RxJava không chấp nhận `null` làm phần tử.

Với Subject, Observer nhận `Disposable` khi subscribe và có thể dispose để ngừng nhận tín hiệu. Với Processor, Subscriber nhận `Subscription` và có thể `cancel()`; Processor phải áp dụng chính sách thích hợp cho upstream. Nếu Processor có nhiều Subscriber, một Subscriber hủy không nhất thiết đồng nghĩa toàn bộ Processor kết thúc.

Subject/Processor là đối tượng có trạng thái và có thể được nhiều thành phần giữ tham chiếu. Hãy xác định rõ ai sở hữu quyền gọi `onComplete` hoặc `onError`, khi nào nguồn được đóng và thành phần nào chịu trách nhiệm giải phóng subscription upstream. Tránh để nhiều thành phần cùng tự ý kết thúc một event bus dùng chung.

## 10. Subject, Processor và các toán tử thông thường

Không phải mọi phép biến đổi dữ liệu đều cần Subject hoặc Processor. Với một pipeline biến đổi một nguồn thành nguồn khác, hãy ưu tiên các toán tử thuần:

```java
Flowable<OrderView> views = orders
    .filter(Order::isPaid)
    .map(OrderView::from);
```

`map`, `filter`, `flatMap` và các toán tử khác giữ pipeline theo mô hình Publisher–Subscriber mà không cần tạo một điểm phát dữ liệu có trạng thái riêng. Subject hoặc Processor phù hợp khi cần một cổng phát dữ liệu được điều khiển thủ công, kết nối callback bên ngoài hoặc chia sẻ một nguồn nóng cho nhiều consumer.

| Nhu cầu | Lựa chọn thường phù hợp |
|---|---|
| Nguồn Observable được đẩy từ callback, không cần backpressure | Subject |
| Nguồn Flowable được đẩy từ callback và cần demand | FlowableProcessor |
| Chỉ biến đổi dữ liệu từ một Publisher hiện có | Toán tử `map`, `filter`, `flatMap`... |
| Chia sẻ trạng thái gần nhất cho nhiều consumer | `BehaviorSubject` hoặc `BehaviorProcessor` tùy giao thức |
| Cần phát lại lịch sử có giới hạn | `ReplaySubject` hoặc `ReplayProcessor` |

## 11. Kiểm thử Subject và Processor

RxJava cung cấp `TestObserver` cho Observable/Subject và `TestSubscriber` cho Flowable/Processor. Chúng giúp xác nhận giá trị, lỗi, hoàn tất và demand.

Kiểm thử `PublishSubject`:

```java
PublishSubject<Integer> subject = PublishSubject.create();
TestObserver<Integer> observer = subject.test();

subject.onNext(1);
subject.onNext(2);
subject.onComplete();

observer.assertValues(1, 2);
observer.assertComplete();
observer.assertNoErrors();
```

Kiểm thử Processor với demand ban đầu bằng không:

```java
PublishProcessor<Integer> processor = PublishProcessor.create();
TestSubscriber<Integer> subscriber = processor.test(0L);

subscriber.request(1);
processor.onNext(7);

subscriber.assertValue(7);

processor.onComplete();
subscriber.assertComplete();
subscriber.assertNoErrors();
```

Nên bổ sung kiểm thử cho các trường hợp subscriber đến muộn, nguồn kết thúc bằng lỗi, hủy subscription, phát đồng thời từ nhiều producer và downstream không có demand. Với loại Subject/Processor có replay, hãy xác nhận đúng số lượng phần tử được giữ và phát lại. Với Processor có backpressure, kiểm tra cả hành vi overflow theo implementation.

## 12. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng Subject khi downstream cần backpressure | Không có giao thức request để điều tiết consumer | Dùng Flowable/Processor hoặc thiết kế hàng đợi có giới hạn |
| Dùng `PublishSubject` rồi kỳ vọng subscriber đến muộn nhận lịch sử | Sự kiện đã phát trước khi subscribe bị bỏ lỡ | Chọn Behavior/Replay nếu cần phát lại |
| Dùng Replay không giới hạn cho nguồn dài hạn | Bộ nhớ tăng theo lịch sử | Giới hạn số phần tử hoặc thời gian replay |
| Gọi `onNext` đồng thời trên Subject/Processor | Tín hiệu có thể chồng lấn và vi phạm hợp đồng | Dùng `toSerialized()` hoặc tuần tự hóa producer |
| Nghĩ serialization tự xử lý backpressure | Consumer chậm vẫn có thể gây quá tải | Chọn Processor và chính sách buffer/drop phù hợp |
| Nhiều thành phần cùng gọi `onComplete` | Vòng đời nguồn khó dự đoán | Xác định một thành phần sở hữu việc kết thúc |
| Dùng Subject để thay mọi toán tử | Tạo thêm state và điểm điều phối không cần thiết | Ưu tiên pipeline toán tử khi không cần cổng phát thủ công |

## 13. Quy trình lựa chọn và sử dụng

Trước khi đưa Subject hoặc Processor vào ứng dụng, hãy xác định:

1. **Nguồn phát có cần điều khiển thủ công không?** Nếu không, giữ pipeline bằng các toán tử thông thường.
2. **Downstream có cần backpressure không?** Chọn Subject cho Observable không có demand; chọn FlowableProcessor khi cần giao thức request/cancel.
3. **Subscriber đến muộn cần nhận gì?** Chọn Publish, Behavior, Replay hoặc Async theo chính sách dữ liệu.
4. **Có nhiều thread phát tín hiệu không?** Dùng `toSerialized()` hoặc một cơ chế tuần tự hóa rõ ràng.
5. **Điều gì xảy ra khi downstream chậm?** Xác định demand, buffer, overflow hoặc drop; không mặc định rằng Processor tự lưu mọi phần tử.
6. **Ai sở hữu vòng đời?** Chỉ định nơi phát `onComplete`/`onError`, quản lý subscription upstream và dispose/cancel đúng lúc.
7. **Đã kiểm thử subscriber đến muộn, lỗi và cancellation chưa?** Dùng `TestObserver` và `TestSubscriber` để xác nhận hợp đồng.

Subject và Processor tạo ra một ranh giới phát dữ liệu có trạng thái trong ứng dụng RxJava. Subject phù hợp với mô hình Observable/Observer khi không có backpressure; Processor phù hợp với Flowable/Subscriber/Publisher khi cần demand. Khi chọn đúng chính sách replay, tuần tự hóa tín hiệu và vòng đời, chúng giúp nối callback bên ngoài vào pipeline reactive mà vẫn giữ hành vi có thể dự đoán và kiểm thử.
