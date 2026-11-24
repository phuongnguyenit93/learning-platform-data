# Hợp đồng bộ nhớ, thứ tự tín hiệu và lời gọi lồng nhau

Trong Reactive Streams, một luồng dữ liệu đúng không chỉ cần phát đúng giá trị và tôn trọng nhu cầu (`request`). Nó còn phải bảo đảm các tín hiệu được quan sát theo thứ tự xác định và dữ liệu đã phát có thể được thread nhận nhìn thấy an toàn. Nếu nhiều thread cùng phát tín hiệu, hoặc một lời gọi `request` kích hoạt ngay một callback khác, Publisher vẫn phải giữ đúng hợp đồng.

Bài học này thuộc chương **Reactive Streams** của module `REACTIVE_PROGRAMMING`. Module giúp người học nắm tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; đồng thời thực hành `Mono`, `Flux`, kết hợp toán tử, điều khiển scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Ở đây, trọng tâm là mối liên hệ giữa Java Memory Model, thứ tự tín hiệu và các lời gọi lồng nhau trong một subscription.

Sau bài học, bạn có thể:

- Giải thích vì sao thứ tự tín hiệu phải đi kèm quan hệ *happens-before*.
- Phân biệt tuần tự tín hiệu với việc mọi callback chạy trên cùng một thread.
- Nhận diện các tình huống `request` hoặc `cancel` gây lời gọi đồng bộ, lồng nhau.
- Chọn cơ chế đồng bộ phù hợp khi xây dựng Publisher hoặc Subscriber có trạng thái dùng chung.
- Kiểm thử thứ tự, backpressure và tính an toàn khi nhiều nguồn cùng phát dữ liệu.

## 1. Hợp đồng reactive còn bao gồm khả năng quan sát bộ nhớ

Reactive Streams định nghĩa giao thức giữa `Publisher`, `Subscriber` và `Subscription`. Một subscription thông thường có vòng đời như sau:

```text
Publisher.subscribe(subscriber)
          |
          v
Subscriber.onSubscribe(subscription)
          |
          | request(n)
          v
       onNext(item)  ...  onNext(item)
          |
          v
   onComplete() hoặc onError(error)
```

`request(n)` biểu thị nhu cầu của Subscriber; nó không phải một tín hiệu dữ liệu. Publisher chỉ được phát số lượng `onNext` nằm trong nhu cầu đã nhận, và subscription kết thúc bằng tối đa một tín hiệu đầu cuối (`onComplete` hoặc `onError`). Sau tín hiệu đầu cuối, Publisher không được phát thêm tín hiệu nào cho subscription đó.

Ngoài vòng đời và backpressure, Reactive Streams còn yêu cầu các phương thức tín hiệu `onSubscribe`, `onNext`, `onError` và `onComplete` được phát tuần tự. Quy tắc 1.3 của đặc tả yêu cầu thiết lập quan hệ *happens-before* giữa các tín hiệu. Điều này có hai ý nghĩa gắn với nhau:

1. Subscriber phải quan sát các tín hiệu theo thứ tự giao thức, không bị hai luồng callback cạnh tranh làm đảo lộn trạng thái.
2. Những thay đổi bộ nhớ được thực hiện trước khi phát tín hiệu phải được công bố an toàn để thread xử lý tín hiệu có thể nhìn thấy chúng.

Vì vậy, “đã gọi `onNext` trước” chưa đủ nếu việc truyền dữ liệu giữa các thread không có cơ chế đồng bộ thích hợp. Một pipeline có thể phát đúng số lượng phần tử nhưng vẫn gặp data race nếu Publisher chia sẻ trạng thái bằng các biến thường không được bảo vệ.

## 2. Hiểu quan hệ happens-before trong Java

Trong Java Memory Model, *happens-before* là quan hệ thứ tự bộ nhớ. Nếu hành động A happens-before hành động B, các ghi bộ nhớ trước A được công bố để B có thể quan sát theo quy tắc của mô hình bộ nhớ. Đây là nền tảng để chuyển dữ liệu và trạng thái giữa các thread một cách an toàn.

Ví dụ, một thread tạo sự kiện và đưa nó vào hàng đợi đồng thời; thread khác lấy sự kiện ra để xử lý:

```java
record OrderCreated(String orderId, long total) {}

BlockingQueue<OrderCreated> queue = new LinkedBlockingQueue<>();

// Thread phát sự kiện
void publishOrder() throws InterruptedException {
    OrderCreated event = new OrderCreated("ORD-42", 250_000L);
    queue.put(event);
}

// Thread xử lý sự kiện
void consumeOrder() throws InterruptedException {
    OrderCreated event = queue.take();
    System.out.println(event.orderId() + ": " + event.total());
}
```

Các thao tác trên hàng đợi đồng thời cung cấp cơ chế công bố dữ liệu giữa thread đưa phần tử vào và thread lấy phần tử ra. Thread nhận có thể đọc các trường đã được thiết lập trước khi phần tử được đưa vào hàng đợi.

Một số cơ chế Java thường dùng để thiết lập quan hệ bộ nhớ phù hợp:

| Cơ chế | Cách sử dụng trong pipeline |
|---|---|
| `synchronized` | Bảo vệ vùng trạng thái dùng chung; thao tác mở khóa được công bố cho lần khóa tiếp theo trên cùng monitor. |
| `volatile` | Công bố thay đổi của một biến giữa các lần ghi và đọc volatile; phù hợp với cờ hoặc tham chiếu trạng thái đơn giản. |
| `Atomic*` | Cập nhật nguyên tử và công bố trạng thái qua các phép toán atomic như `get`, `set`, `compareAndSet`. |
| Hàng đợi đồng thời | Chuyển phần tử giữa thread phát và thread nhận, đồng thời cung cấp bảo đảm bộ nhớ của cấu trúc đó. |
| Executor hoặc scheduler | Đưa công việc qua cơ chế chuyển giao tác vụ có đồng bộ, thay vì tự chia sẻ dữ liệu bằng biến thường. |

Không nên dùng `Thread.sleep`, `yield` hoặc giả định về tốc độ thread để thay thế đồng bộ. Việc một thread thường chạy sau thread khác trong thử nghiệm không tạo ra bảo đảm happens-before.

### Một ví dụ về data race

Đoạn mã sau dùng hai biến thường để chia sẻ một sự kiện:

```java
final class UnsafeSlot {
    private OrderCreated latest;
    private boolean ready;

    void publish(OrderCreated event) {
        latest = event;
        ready = true;
    }

    OrderCreated read() {
        return ready ? latest : null;
    }
}
```

Nếu `publish` và `read` chạy trên các thread khác nhau, không có quan hệ đồng bộ nào bảo đảm thread đọc nhìn thấy cập nhật mới nhất. Thread đọc có thể chưa thấy `ready = true`, hoặc không quan sát trạng thái theo cách mà người viết mã mong đợi. Đây là data race.

Nếu chỉ cần một ô lưu giá trị mới nhất, có thể dùng một tham chiếu `volatile`:

```java
final class LatestOrderSlot {
    private volatile OrderCreated latest;

    void publish(OrderCreated event) {
        latest = event;
    }

    OrderCreated read() {
        return latest;
    }
}
```

Phép ghi volatile công bố đối tượng đã được khởi tạo trước phép ghi; phép đọc volatile tiếp theo có thể quan sát tham chiếu được công bố. Cách này chỉ biểu diễn một giá trị mới nhất, không phải hàng đợi sự kiện và không thay thế backpressure. Với nhiều sự kiện, hãy dùng cấu trúc truyền dữ liệu đồng thời phù hợp và xác định rõ chính sách lưu, bỏ hoặc chặn phần tử.

## 3. Tuần tự tín hiệu không đồng nghĩa với cố định thread

Một Publisher có thể chuyển việc phát tín hiệu giữa các thread, miễn là vẫn giữ thứ tự và quan hệ happens-before theo hợp đồng. Subscriber không nên mặc định mọi callback luôn chạy trên thread gọi `subscribe` hoặc thread gọi `request`.

Ví dụ, trong Reactor:

```java
Flux.range(1, 3)
    .publishOn(Schedulers.single())
    .doOnNext(value -> System.out.println(
        Thread.currentThread().getName() + " -> " + value
    ))
    .subscribe();
```

`publishOn` tạo ranh giới scheduler cho các tín hiệu downstream. Reactor chuyển phần tử qua cơ chế hàng đợi nội bộ và xử lý chúng trên scheduler được chọn. Việc chuyển thread không cho phép các callback downstream chạy chồng lấn hoặc làm mất thứ tự tín hiệu của subscription.

Hãy phân biệt ba khái niệm:

- **Tuần tự tín hiệu:** các tín hiệu của một subscription được quan sát theo thứ tự giao thức và có quan hệ happens-before.
- **Thread thực thi:** thread xử lý một callback cụ thể; thread có thể thay đổi qua ranh giới scheduler.
- **Thứ tự nghiệp vụ:** thứ tự mà ứng dụng mong muốn giữa các sự kiện, chẳng hạn thứ tự tạo đơn hàng hoặc cập nhật tài khoản. Thứ tự này còn phụ thuộc vào cách nguồn phát và toán tử kết hợp các luồng.

Khi kết hợp nhiều nguồn, chẳng hạn bằng `merge`, các phần tử từ từng nguồn có thể xen kẽ theo thời điểm chúng đến. Điều đó không tự tạo ra một thứ tự nghiệp vụ toàn cục giữa các nguồn. Nếu nghiệp vụ yêu cầu thứ tự cụ thể, hãy mã hóa thứ tự bằng sequence number, khóa phân vùng, timestamp có quy tắc xử lý rõ ràng hoặc một toán tử sắp xếp phù hợp với giới hạn bộ nhớ và độ trễ.

## 4. Lời gọi lồng nhau khi request phát tín hiệu đồng bộ

Reactive Streams không bắt buộc Publisher phải bất đồng bộ. Một Publisher đồng bộ có thể gọi `onSubscribe` ngay trong `subscribe`, và một lời gọi `request(n)` có thể kích hoạt `onNext` trước khi `request` trả về.

Ví dụ Subscriber yêu cầu từng phần tử:

```java
final class OneByOneSubscriber<T> implements Subscriber<T> {
    private Subscription subscription;

    @Override
    public void onSubscribe(Subscription subscription) {
        this.subscription = subscription;
        subscription.request(1);
    }

    @Override
    public void onNext(T item) {
        process(item);
        subscription.request(1);
    }

    @Override
    public void onError(Throwable error) {
        error.printStackTrace();
    }

    @Override
    public void onComplete() {
        System.out.println("Completed");
    }

    private void process(T item) {
        System.out.println("Received: " + item);
    }
}
```

Khi Subscriber gọi `request(1)` trong `onSubscribe`, Publisher đồng bộ có thể phát `onNext` ngay trong quá trình xử lý yêu cầu đó. Tương tự, `request(1)` bên trong `onNext` có thể làm Publisher phát thêm phần tử trước khi lời gọi `request` hiện tại trả về. Đây là tình huống lời gọi lồng nhau (*reentrant call*).

Từ đó rút ra các nguyên tắc thực hành:

- Không giả định `request` luôn trả về trước khi callback kế tiếp bắt đầu.
- Không giữ khóa ứng dụng trong lúc gọi `request` nếu callback được kích hoạt có thể cần chính khóa đó.
- Không dựa vào một độ sâu stack cố định để xử lý luồng dài.
- Giữ thao tác trong callback ngắn gọn; đưa công việc tốn thời gian sang scheduler phù hợp.
- Publisher phải giới hạn số lần đệ quy đồng bộ của `request` theo quy tắc 3.3 của Reactive Streams.

Lời gọi lồng nhau và phát tín hiệu đồng thời là hai vấn đề khác nhau. Lời gọi lồng nhau có thể xảy ra trên cùng một call stack do `request` phát tín hiệu đồng bộ. Phát tín hiệu đồng thời xảy ra khi nhiều thread cùng cố gọi phương thức tín hiệu. Publisher phải giữ hợp đồng tuần tự trong cả hai tình huống và không để hai nguồn cạnh tranh làm hỏng trạng thái subscription.

## 5. Cách Publisher tuần tự hóa tín hiệu

Một Publisher có nhiều nguồn phát thường cần một điểm điều phối duy nhất trước khi gọi callback downstream. Một mẫu triển khai phổ biến là kết hợp hàng đợi với bộ đếm `work-in-progress` (WIP):

```java
// Phác thảo thuật toán, không phải một Publisher hoàn chỉnh.
final Queue<T> queue = new ConcurrentLinkedQueue<>();
final AtomicInteger wip = new AtomicInteger();

void offer(T value) {
    queue.offer(value);
    drain();
}

void request(long n) {
    addDemandSaturating(n);
    drain();
}

void drain() {
    if (wip.getAndIncrement() != 0) {
        return; // Một vòng drain khác đang sở hữu quyền phát tín hiệu.
    }

    int missed = 1;
    do {
        emitQueuedItemsWhileDemandIsPositive();
        missed = wip.addAndGet(-missed);
    } while (missed != 0);
}
```

Đây là phác thảo để giải thích cơ chế, không đủ để dùng trực tiếp trong production. Một Publisher hoàn chỉnh còn phải xử lý nhu cầu bão hòa, `request(n <= 0)`, hủy subscription, lỗi, tín hiệu đầu cuối, race giữa `cancel` và `onNext`, cũng như việc chỉ phát khi còn demand.

Ý tưởng của vòng `drain` là:

1. Mọi nguồn đưa sự kiện vào hàng đợi an toàn.
2. `wip` dùng phép toán atomic để chỉ cho một vòng drain phát callback tại một thời điểm.
3. Nếu `request` hoặc nguồn khác gọi `drain` khi vòng hiện tại đang chạy, bộ đếm ghi nhận công việc mới thay vì tạo thêm một vòng callback lồng nhau.
4. Vòng hiện tại tiếp tục lấy phần tử khi còn demand, rồi kiểm tra xem có công việc mới đến trong lúc drain hay không.

Nhờ vậy, lời gọi đến `request` trong callback có thể cập nhật demand mà không cần mở một vòng phát tín hiệu lồng sâu trên cùng stack. Cơ chế WIP cũng giúp gom nhiều yêu cầu drain đồng thời thành một vòng điều phối tuần tự.

Khi gọi code của Subscriber, Publisher cần cẩn thận với khóa nội bộ. Giữ monitor trong lúc gọi `onNext` có thể khiến callback gọi ngược `request` hoặc `cancel`, dẫn đến deadlock hoặc kéo dài thời gian giữ khóa. Một thiết kế thường an toàn hơn là cập nhật trạng thái và lấy phần tử dưới cơ chế đồng bộ, sau đó gọi callback ngoài vùng khóa; vòng drain vẫn chịu trách nhiệm bảo đảm chỉ có một luồng phát tín hiệu.

## 6. Subscriber cần quản lý trạng thái thế nào?

Subscriber nên quyết định rõ trạng thái nào chỉ được truy cập trong callback tuần tự và trạng thái nào có thể bị truy cập từ nhiều thread. Nếu một trạng thái chỉ được đọc, ghi trong các callback đã được tuần tự hóa, có thể quản lý nó theo luồng callback. Nếu một thread bên ngoài cũng đọc hoặc thay đổi trạng thái đó, cần thêm cơ chế đồng bộ.

Một số nguyên tắc hữu ích:

- **Công bố an toàn:** hoàn tất khởi tạo đối tượng trước khi phát nó qua `onNext`; dùng cơ chế chuyển giao thread có bảo đảm bộ nhớ.
- **Quyền sở hữu dữ liệu:** sau khi phát một đối tượng mutable, tránh tiếp tục sửa nó trong khi Subscriber có thể đang đọc. Ưu tiên object bất biến hoặc chuyển giao quyền sở hữu rõ ràng.
- **Trạng thái subscription:** chỉ thiết lập subscription trong `onSubscribe`; không giả định callback sẽ chạy bất đồng bộ sau đó.
- **Demand:** chỉ yêu cầu số lượng dương. Theo quy tắc 3.9, `request` với giá trị không dương phải dẫn đến `onError` với `IllegalArgumentException` theo hợp đồng, trừ trường hợp subscription đã kết thúc hoặc bị hủy theo các quy tắc liên quan.
- **Hủy:** `cancel` có thể cạnh tranh với một tín hiệu đang được xử lý. Theo quy tắc 1.8, Publisher phải dừng phát tín hiệu sau khi việc hủy có hiệu lực; Subscriber không nên dựa vào giả định rằng mọi công việc đang chạy biến mất tức thời tại đúng thời điểm gọi `cancel`.
- **Kết thúc:** sau `onError` hoặc `onComplete`, không xử lý thêm tín hiệu của subscription đó.

Nếu ứng dụng cần cập nhật một cấu trúc dùng chung từ nhiều callback hoặc thread, hãy chọn `ConcurrentHashMap`, atomic, khóa hoặc một actor/event loop tùy theo mô hình truy cập. Không thêm `volatile` một cách máy móc: `volatile` công bố giá trị của biến, nhưng không làm cho một chuỗi thao tác đọc-sửa-ghi trở thành nguyên tử.

## 7. Kiểm thử thứ tự, backpressure và ranh giới scheduler

Kiểm thử reactive nên xác minh hành vi giao thức thay vì dựa vào thời gian chạy thực tế. Với Reactor Test, `StepVerifier` có thể kiểm tra thứ tự phần tử và demand:

```java
StepVerifier.create(
        Flux.range(1, 3).publishOn(Schedulers.single()),
        0
    )
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .verifyComplete();
```

Ví dụ bắt đầu với demand downstream bằng `0`, sau đó yêu cầu một phần tử rồi hai phần tử. Bài kiểm thử xác nhận downstream không nhận phần tử trước khi có demand và nhận các giá trị theo đúng thứ tự. `publishOn` vẫn có thể prefetch từ upstream vào hàng đợi theo cấu hình của operator, vì vậy demand trong ví dụ kiểm soát tín hiệu downstream chứ không có nghĩa upstream hoàn toàn chưa làm việc. Riêng kết quả `StepVerifier` cũng không chứng minh mọi trường hợp truy cập bộ nhớ dùng chung đều an toàn.

Khi xây dựng Publisher tùy chỉnh, nên bổ sung các nhóm kiểm thử sau:

| Tình huống | Điều cần xác minh |
|---|---|
| Nhiều thread cùng đưa phần tử vào | Không có callback downstream bị phát đồng thời; các phần tử không bị mất ngoài chính sách đã định. |
| `request` được gọi trong `onSubscribe` | Publisher xử lý được yêu cầu đồng bộ ngay khi subscription được thiết lập. |
| `request` được gọi trong `onNext` | Không tạo đệ quy đồng bộ không giới hạn; demand được cập nhật chính xác. |
| `cancel` cạnh tranh với nguồn phát | Publisher dừng phát theo hợp đồng và không tiếp tục xử lý vô hạn công việc đã hủy. |
| `onError` hoặc `onComplete` | Chỉ có một tín hiệu đầu cuối và không có tín hiệu tiếp theo. |
| Chuyển thread qua scheduler | Dữ liệu đã công bố được nhìn thấy đầy đủ và thứ tự tín hiệu vẫn được giữ. |

Với Publisher tự triển khai, hãy dùng Reactive Streams TCK để kiểm tra các quy tắc giao thức. Với code ứng dụng, dùng `StepVerifier`, latch hoặc barrier để điều khiển đồng bộ trong kiểm thử cạnh tranh. Tránh dùng `sleep` để hy vọng một race condition xuất hiện; cách đó vừa không ổn định vừa không chứng minh được quan hệ bộ nhớ.

## 8. Những lỗi thường gặp

| Cách làm sai | Hậu quả | Cách xử lý |
|---|---|---|
| Cho nhiều thread gọi trực tiếp `onNext` | Callback có thể chạy đồng thời, gây race trong Subscriber. | Đưa phần tử qua hàng đợi và một vòng drain tuần tự. |
| Chia sẻ biến thường giữa thread phát và thread nhận | Thread nhận có thể không thấy cập nhật mới nhất. | Dùng queue đồng thời, atomic, volatile hoặc khóa đúng phạm vi. |
| Nghĩ rằng `request` luôn bất đồng bộ | Callback có thể chạy ngay trong lời gọi `request`, gây reentrancy. | Thiết kế callback an toàn với phát đồng bộ; giới hạn đệ quy ở Publisher. |
| Giữ khóa khi gọi `onNext` | Callback gọi ngược Publisher có thể gây deadlock hoặc tranh chấp khóa. | Tránh gọi code bên ngoài khi đang giữ khóa nội bộ. |
| Cho rằng đổi scheduler sẽ tự sửa mọi data race | Trạng thái mutable ngoài pipeline vẫn có thể bị nhiều thread truy cập sai cách. | Đồng bộ rõ ràng mọi trạng thái chia sẻ ngoài cơ chế truyền tín hiệu. |
| Dùng `volatile` thay cho mọi phép cập nhật nguyên tử | Chuỗi đọc-sửa-ghi vẫn có thể mất cập nhật. | Dùng atomic operation hoặc khóa khi cần tính nguyên tử. |

## 9. Checklist khi thiết kế pipeline

Trước khi hoàn thiện một Publisher, Subscriber hoặc operator tùy chỉnh, hãy tự kiểm tra:

- `onSubscribe` được phát đúng một lần và trước các tín hiệu còn lại.
- `onNext` tôn trọng demand; tín hiệu đầu cuối chỉ phát tối đa một lần.
- Các tín hiệu được tuần tự hóa và có quan hệ happens-before.
- Mọi dữ liệu đi qua ranh giới thread được công bố bằng cơ chế an toàn.
- `request` có thể kích hoạt callback đồng bộ mà không làm hỏng trạng thái hoặc tạo đệ quy không giới hạn.
- `cancel` và tín hiệu đầu cuối được phối hợp an toàn với nguồn phát đang chạy.
- Callback không giữ khóa nội bộ trong lúc gọi code của Subscriber.
- Kiểm thử bao gồm demand, thứ tự, kết thúc, hủy và các tình huống nhiều thread.

Khi nắm được các nguyên tắc này, bạn có thể đọc và xây dựng pipeline `Mono`/`Flux` với hiểu biết rõ hơn về điều gì được bảo đảm tại ranh giới thread, cách backpressure tương tác với lời gọi đồng bộ, và vì sao một luồng tín hiệu đúng phải đồng thời giữ thứ tự giao thức lẫn tính an toàn của bộ nhớ.
