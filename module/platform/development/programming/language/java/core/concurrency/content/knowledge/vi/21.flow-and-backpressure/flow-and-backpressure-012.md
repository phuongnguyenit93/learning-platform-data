# SubmissionPublisher.submit() so với offer(): xử lý subscriber chậm và buffer đầy

> Chủ đề: **Flow & Backpressure** trong Java, tập trung vào `java.util.concurrent.Flow` và `SubmissionPublisher<T>` (có từ Java 9). Các ví dụ dùng **JDK 17+** và chỉ phụ thuộc Java SE; không đi vào framework cụ thể.

## 1. Vấn đề: producer nhanh hơn subscriber

`Flow.Publisher<T>` phát phần tử cho các `Flow.Subscriber<T>`. Subscriber nhận `Flow.Subscription` từ `onSubscribe`, sau đó dùng `subscription.request(n)` để thông báo nhu cầu (*demand*). Publisher chỉ được phát `onNext` theo số lượng được yêu cầu; mỗi phần tử đã được chuyển tới `onNext` tiêu thụ một đơn vị demand.

`SubmissionPublisher<T>` là triển khai Publisher có sẵn của JDK. Nó nhận item từ producer và **giao bất đồng bộ** cho các subscriber bằng một `Executor`. Mỗi subscriber có **buffer riêng**, vì vậy nếu một subscriber xử lý chậm hoặc không yêu cầu thêm dữ liệu, buffer của subscriber đó có thể đầy.

```text
producer -- submit/offer(item) --> SubmissionPublisher
                                  |              |
                                  v              v
                             buffer S1      buffer S2
                             [đang đầy]      [còn chỗ]
                                  |              |
                                  v              v
                           subscriber S1  subscriber S2
                           chậm/không xin nhanh/đang xin
```

Bài toán cần quyết định: khi **ít nhất một subscriber không nhận kịp**, producer nên **chờ để giữ dữ liệu** hay **chấp nhận bỏ một item tại subscriber bị quá tải**? Hai API chính hỗ trợ hai lựa chọn đó:

- `submit(item)`: chờ khi thiếu tài nguyên buffer để phát item cho các subscriber hiện tại.
- `offer(item, ...)`: thử phát, có thể drop cho subscriber bị đầy; bản timed offer có thể chờ một khoảng trước khi drop.

**Backpressure ở đây không chỉ là buffer size.** `request(n)` cho biết số lượng callback `onNext` được phép giao theo nhu cầu subscriber. Buffer xử lý chênh lệch tốc độ producer/consumer tạm thời; khi backlog vượt khả năng buffer, producer phải chọn chính sách chờ, bỏ, giới hạn tải hoặc lưu bền vững ở nơi khác.

## 2. So sánh chính xác các overload

| API | Khi buffer của subscriber đầy | Khả năng drop | Khi nào dùng |
|---|---|---|---|
| `int submit(T item)` | **Chờ không ngắt được** (*blocks uninterruptibly*) đến khi có tài nguyên để nhận item | Không drop item chỉ do đầy buffer | Cần giữ dữ liệu trong luồng xử lý, producer được phép chịu backpressure |
| `int offer(T item, BiPredicate onDrop)` | Thử phát ngay, không chờ đầy buffer; chạy drop handler nếu cần | Có; handler có thể thử lại đúng **một lần** khi trả `true` | Không muốn producer bị treo vì subscriber chậm, chấp nhận xử lý mất item |
| `int offer(T item, long timeout, TimeUnit unit, BiPredicate onDrop)` | Chờ buffer rảnh **tối đa theo timeout hoặc tới khi bị interrupt**, sau đó có thể drop | Có; handler có thể thử lại một lần | Muốn một khoảng chờ hữu hạn trước khi áp dụng drop policy |

**Không đồng nghĩa:** gọi `offer` không có nghĩa *chắc chắn* drop, và gọi `submit` không có nghĩa *chắc chắn* block. Khi buffer còn chỗ, cả hai có thể phát thành công và quay lại rất nhanh.

Một subscriber chậm là đủ khiến `submit` của producer bị chờ, dù các subscriber khác vẫn theo kịp. Ngược lại, `offer` có thể phát item cho subscriber nhanh và drop riêng ở subscriber quá tải. Tùy hợp đồng ứng dụng, việc các subscriber thấy tập item khác nhau có thể được chấp nhận hoặc là lỗi nghiêm trọng.

Các phương thức này **đưa item vào đường giao bất đồng bộ**, không có nghĩa `onNext` của mọi subscriber đã thực thi xong khi phương thức trả về.

## 3. Buffer riêng và demand: vì sao subscriber bị đầy?

### 3.1. `request(n)` ảnh hưởng đến luồng giao item

Ví dụ một subscriber:

```java
@Override
public void onSubscribe(Flow.Subscription subscription) {
    this.subscription = subscription;
    subscription.request(1);
}

@Override
public void onNext(String item) {
    process(item);
    subscription.request(1);
}
```

Đây chỉ là **fragment**: giả định class đã có trường `subscription` và phương thức `process`. Nó yêu cầu **từng item**, rồi yêu cầu tiếp khi xử lý xong. Nếu `process` chậm, subscriber cấp lại demand chậm và backlog có thể tăng. Nếu không gọi `request`, `onNext` không được giao, và những item đã được chấp nhận có thể nằm trong buffer cho tới khi đầy.

Nếu subscriber gọi `request(Long.MAX_VALUE)`, đó là demand rất lớn, **không phải** buffer vô hạn. Nếu `onNext` mất 200 ms nhưng producer gửi 1.000 item mỗi giây thì hàng đợi vẫn có thể bị lấp kín.

Không dùng `request(0)` hoặc `request` với số âm: đây là yêu cầu sai giao thức và dẫn tới tín hiệu lỗi theo hợp đồng Flow. Sau khi `cancel()`, subscriber không còn nhận các item mới của subscription đó.

### 3.2. `maxBufferCapacity` là cho **từng subscriber**

```java
ExecutorService delivery = Executors.newFixedThreadPool(4);
SubmissionPublisher<String> publisher =
        new SubmissionPublisher<>(delivery, 16);
```

*Đoạn minh họa trong một chương trình có import `java.util.concurrent.*`; thực tế phải đóng publisher và shutdown executor đúng vòng đời.*

Con số `16` ở constructor là **dung lượng yêu cầu cho mỗi subscriber**, không phải tổng số item trên toàn publisher. Dung lượng thực thi có thể được làm tròn lên lũy thừa 2 hoặc bị chặn bởi giới hạn implementation; gọi `publisher.getMaxBufferCapacity()` để biết dung lượng thực tế.

Nếu có 100 subscriber, có thể có nhiều buffer đang hoạt động đồng thời; cần cân nhắc bộ nhớ, số subscriber và kích thước mỗi item. Buffer giúp hấp thụ burst ngắn, **không chữa được** chênh lệch tốc độ lâu dài. Đặt buffer cực lớn có thể chỉ che một subscriber chậm bằng tăng RAM và latency.

### 3.3. Một mục đang được xử lý và một mục còn trong buffer

Subscriber có thể đang thực hiện `onNext(item1)` khá lâu, trong khi `item2` nằm đợi ở buffer. Cả khi demand chưa hết, tốc độ của executor và thời gian chạy callback vẫn giới hạn khả năng xả buffer. Đừng chỉ đo demand mà bỏ qua **tốc độ hoàn tất `onNext`**.

## 4. `submit(item)`: chờ để giữ item, đánh đổi latency producer

Cú pháp:

```java
int lag = publisher.submit(item);
```

- Item phải **khác `null`**; gửi khi publisher đã đóng gây `IllegalStateException`.
- Khi chưa đủ chỗ trong buffer của bất kỳ subscriber hiện tại nào, `submit` có thể **block uninterruptibly**. `Thread.interrupt()` **không phải** bảo đảm làm lời gọi này kết thúc ngay.
- Giá trị trả về là **ước lượng maximum lag**: số item đã gửi nhưng chưa được consume ở subscriber chậm nhất; có subscriber thì ít nhất 1, không có subscriber thì 0. Không phải số item đã xử lý thành công và không phải số millisecond bị chờ.
- Nếu executor từ chối tác vụ (ví dụ `RejectedExecutionException`), lời gọi có thể ném exception; khi phát sinh lỗi từ executor, không bảo đảm tất cả subscriber đã nhận được item.

**Khi phù hợp:** dữ liệu bắt buộc đi qua từng subscriber trong một pipeline ngắn, producer có thể chờ, đã có giới hạn upstream và cơ chế hủy/shutdown đúng. Việc `submit` bảo toàn giao hàng khi **buffer đầy** không đồng nghĩa bảo đảm bền vững khi JVM crash, subscriber hủy, callback lỗi hoặc publisher bị đóng bất thường.

**Rủi ro:** nếu subscriber không bao giờ gọi `request` tiếp, bị treo trong `onNext` hoặc executor không có thread rảnh, `submit` có thể chờ rất lâu hoặc vô thời hạn. Không gọi `submit` trên luồng phục vụ UI/đường xử lý yêu cầu có deadline nghiêm ngặt nếu không thể kiểm soát backpressure. Đặc biệt tránh gọi `submit` lặp lại từ chính một callback `onNext` khi nó đang chiếm worker mà publisher cần để xả buffer: có thể tạo vòng chờ/deadlock.

`submit` không cho đối số timeout. Nếu cần chính sách latency hữu hạn, xem `offer` có timeout; nếu cần xử lý hủy mạnh hơn, xây dựng cơ chế dừng/cancel trên toàn pipeline thay vì chỉ kỳ vọng interrupt giải phóng producer.

## 5. `offer(item, onDrop)`: không chờ, có khả năng mất item

Cú pháp:

```java
int status = publisher.offer(event, (subscriber, rejectedEvent) -> {
    // Ghi metric / thông báo sự kiện quá tải.
    return false;  // Không thử lại: drop item ở subscriber bị đầy.
});
```

*Đoạn code cần biến `publisher`, `event` và kiểu generic tương thích; không là chương trình độc lập.*

Khi không thể phát cho subscriber do giới hạn buffer, `onDrop` nhận **subscriber cụ thể** và item bị từ chối. Giá trị boolean:

- `false`: không thử lại, item bị drop cho subscriber này.
- `true`: yêu cầu thử offer lại **một lần duy nhất** ở subscriber này; **không** đảm bảo lần thử lại thành công. Nếu vẫn đầy, item có thể bị drop.

Nếu handler là `null`, lời gọi vẫn có thể drop và không gọi handler. Handler nên **rất ngắn, không block, không có thao tác gọi ngược phức tạp vào publisher**: tài liệu API nêu rằng các lời gọi khác vào publisher từ luồng khác sẽ bị chặn trong khi handler chạy. Handler chậm làm lan truyền sự chậm trễ tới cả các producer khác.

Một chiến lược đúng có thể là đếm drop, ghi log có giới hạn, chọn hủy subscriber lỗi hoặc gửi thông báo qua kênh phụ. Không nên giả định `onDrop` là nơi an toàn để retry vô hạn, ngủ dài hoặc chờ cùng buffer mà nó đang xử lý.

## 6. `offer(item, timeout, unit, onDrop)`: chờ có hạn

Ví dụ:

```java
int status = publisher.offer(
        event,
        100, TimeUnit.MILLISECONDS,
        (subscriber, dropped) -> {
            droppedCounter.increment();
            return false;
        }
);
```

*Fragment này cần các biến `publisher`, `event`, `droppedCounter` và import `java.util.concurrent.TimeUnit`.*

Phiên bản timed offer cho phép publisher đợi tài nguyên của subscriber trong khoảng timeout hoặc tới khi thread gọi bị interrupt. Nếu hết thời gian/được ngắt mà subscriber vẫn không nhận được, sẽ áp dụng drop handler; handler vẫn chỉ có quyền yêu cầu **một** lần retry. API nói rõ handler có thể phân biệt interrupt với timeout bằng cờ interrupt của thread hiện tại.

**Lưu ý:** timeout dùng để giới hạn việc đợi tài nguyên trong chính lời gọi offer, không bảo đảm callback `onNext` kết thúc trước deadline; logic nghiệp vụ cần timeout cho processing riêng. Tổng thời gian thực còn chịu scheduler và thời gian handler; không dùng timeout này thay thế deadline end-to-end.

Các chính sách điển hình:

| Mức chịu mất dữ liệu | Chiến lược |
|---|---|
| Không thể bỏ item | Không dùng drop silently; cân nhắc `submit` có backpressure được kiểm soát, hoặc hệ thống lưu bền vững/ack ở tầng khác |
| Có thể bỏ cập nhật trung gian (ví dụ tiến độ UI) | `offer(..., onDrop -> false)`; ghi metric drop |
| Cho phép trễ nhỏ nhưng không vô hạn | Timed `offer` và xử lý drop rõ ràng |
| Chỉ cần trạng thái mới nhất | Thiết kế cơ chế coalescing/latest-state ở ứng dụng; `offer` tự nó **không thay thế item cũ bằng item mới** |

## 7. Đọc `int` trả về cho đúng

Cả `submit` và `offer` đều trả `int`, nhưng **ý nghĩa không giống nhau**.

### `submit`

- Trả **ước lượng lag lớn nhất** của các subscriber tại thời điểm đo.
- Không có subscriber: `0`.
- Có subscriber: giá trị ít nhất `1`, gồm item vừa gửi.
- Không phản ánh trực tiếp độ dài queue chính xác hay số item thật sự đã gọi xong `onNext`.

### `offer` (cả hai overload)

- `status >= 0`: không ghi nhận drop; giá trị là **ước lượng maximum lag** (không có subscriber thì `0`).
- `status < 0`: trị tuyệt đối biểu diễn **số lần không phát được item cho subscriber** (drop/failed attempts theo hợp đồng API), không phải thời gian chờ, không phải subscriber ID và không phải backlog âm.
- Khi handler trả `true` để retry, **vẫn phải xem status cuối**, không được kết luận retry luôn thành công.

```java
int status = publisher.offer(item, (subscriber, rejected) -> false);
if (status < 0) {
    int drops = -status;
    // Ghi nhận số lượt drop; xử lý theo yêu cầu nghiệp vụ.
} else {
    int estimatedMaxLag = status;
    // Chỉ dùng để theo dõi, không làm tín hiệu đồng bộ chính xác.
}
```

*Đây là fragment, không thể biên dịch độc lập nếu chưa khai báo `publisher` và `item`.*

Các API quan sát `estimateMaximumLag()` và `estimateMinimumDemand()` cũng trả **ước lượng**; chúng có thể lỗi thời khi nhiều producer/consumer chạy đồng thời. Dùng để **monitoring/tuning**, không dùng làm giao thức khóa kiểu “nếu lag nhỏ hơn X thì sẽ chắc chắn submit không block”.

## 8. Ví dụ Java 17+ chạy được: chủ động làm đầy buffer

Ví dụ sau làm subscriber chậm bằng `CountDownLatch` để bảo đảm item thứ nhất **đang kẹt trong `onNext`**. Buffer cấu hình 1 chỗ; item thứ hai nằm đợi. Vì thế item thứ ba qua `offer` bị drop, còn item thứ tư gửi bằng `submit` phải chờ tới khi subscriber được mở khóa. Code sử dụng hai executors riêng để tránh tự khóa chính worker giao hàng.

Tạo tệp **`SubmissionPublisherPressureDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.Future;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class SubmissionPublisherPressureDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService delivery = Executors.newSingleThreadExecutor();
        ExecutorService producer = Executors.newSingleThreadExecutor();
        CountDownLatch subscribed = new CountDownLatch(1);
        CountDownLatch inFirstOnNext = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        SubmissionPublisher<Integer> publisher =
                new SubmissionPublisher<>(delivery, 1);

        Flow.Subscriber<Integer> slow = new Flow.Subscriber<>() {
            private Flow.Subscription subscription;

            @Override
            public void onSubscribe(Flow.Subscription s) {
                subscription = s;
                s.request(Long.MAX_VALUE);
                subscribed.countDown();
            }

            @Override
            public void onNext(Integer value) {
                if (value == 1) {
                    inFirstOnNext.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                }
            }

            @Override
            public void onError(Throwable error) {
                System.err.println("Subscriber failed: " + error);
            }

            @Override
            public void onComplete() {
                // Kết thúc bình thường.
            }
        };

        try {
            publisher.subscribe(slow);
            subscribed.await();

            publisher.submit(1);
            inFirstOnNext.await();  // Đảm bảo onNext(1) đang đợi release.

            publisher.submit(2);    // Một slot buffer đang được dùng.
            int offered = publisher.offer(3, (s, item) -> false);
            System.out.println("offerDropped=" + (offered < 0));

            Future<Integer> pending =
                    producer.submit(() -> publisher.submit(4));
            // Dù tác vụ producer đã bắt đầu hay đang đợi đến lượt,
            // nó không thể hoàn tất submit(4) khi slot còn đầy.
            System.out.println("submitFinishedWhileFull=" + pending.isDone());

            release.countDown();    // Giải phóng callback để xả buffer.
            pending.get(5, TimeUnit.SECONDS);
            System.out.println("submitFinishedAfterRelease=true");
        } finally {
            release.countDown();
            publisher.close();
            producer.shutdown();
            delivery.shutdown();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac SubmissionPublisherPressureDemo.java
java SubmissionPublisherPressureDemo
```

Với cấu hình `maxBufferCapacity=1` và các mốc `CountDownLatch` như chương trình, stdout dự kiến khi chạy bình thường:

```text
offerDropped=true
submitFinishedWhileFull=false
submitFinishedAfterRelease=true
```

Giải thích:

1. Subscriber gọi `request(Long.MAX_VALUE)`, nhưng `onNext(1)` cố tình chờ. Cấp demand vô hạn **không** làm consumer xử lý nhanh.
2. Sau khi đã biết item 1 đang ở trong callback, item 2 có thể chờ ở buffer duy nhất; `offer(3, handler -> false)` phát hiện không còn chỗ và drop.
3. `submit(4)` chạy ở producer thread khác. Khi subscriber còn bị giữ bởi latch, việc phát item 4 không thể hoàn tất, nên producer bị backpressure. Sau khi `release.countDown()`, worker hoàn thành `onNext(1)`, tiếp tục xả buffer, và `submit(4)` có thể trở về.
4. `Future.get(5, SECONDS)` là **giới hạn đợi của chương trình demo**, không biến lời gọi `submit` bên trong thành interruptible hay timed submit. Nếu môi trường bị nghẽn bất thường, `get` có thể ném `TimeoutException` thay vì in dòng cuối.
5. `finally` giải phóng latch và đóng publisher/executors; tránh để một thread demo bị giữ vì callback chờ vô hạn.

Trong thực tế, số worker, lịch chạy và giới hạn tài nguyên làm performance khác nhau. Đừng dùng microdemo này như benchmark thông lượng. Nếu sửa mã (ví dụ bỏ latch), **không** còn bảo đảm mã trả về hoặc trình tự kết quả tương tự.

## 9. Khi có nhiều subscriber: một bên chậm kéo theo điều gì?

Giả sử có hai subscriber `fast` và `slow`, mỗi subscriber có buffer riêng:

```text
       item X
         |
  SubmissionPublisher
       /       \
   fast          slow
   buffer 0/8    buffer 8/8
   nhận X        không còn chỗ
```

- Với `submit(X)`, producer có thể bị chặn vì `slow`. `fast` có thể đã được giao item nhưng lời gọi producer vẫn đang chờ đường còn lại.
- Với `offer(X, handler -> false)`, `fast` có thể nhận X còn `slow` bị drop X. `onDrop` cho biết subscriber cụ thể bị drop để ghi metric/điều chỉnh chính sách.
- Nếu drop là không chấp nhận được, ứng dụng cần định nghĩa việc một subscriber chậm có được quyền làm chậm tất cả subscriber hay phải được tách khỏi pipeline. Một số hệ thống chọn cô lập một subscriber bằng queue/publisher riêng hoặc hủy subscription chậm, nhưng cần quyết định rõ semantics dữ liệu.
- Nếu subscriber mới subscribe sau khi X đã được publish, `SubmissionPublisher` không tự phát lại lịch sử X; nó không phải message broker có replay/durable log.

Không chạy mọi subscriber và producer trên cùng một executor có quá ít thread khi callback có thể block và producer cũng cần chờ, vì rất dễ tạo **thread starvation**. Chọn executor dựa trên workload, số subscriber và hành vi callback; Java API có tùy chọn mặc định dựa trên `ForkJoinPool.commonPool()`, nhưng không có nghĩa mọi workload đều phù hợp với pool mặc định.

## 10. Chọn backpressure policy theo yêu cầu nghiệp vụ

| Workload | Gợi ý | Lưu ý |
|---|---|---|
| Sự kiện phải đủ, không được mất | `submit` trong pipeline có giới hạn upstream hoặc cơ chế lưu/ack bền vững | Nếu subscriber ngừng request, producer có thể chờ vô hạn |
| Telemetry/giá trị có thể lấy lại | `offer` và đếm drop | Chấp nhận mất điểm dữ liệu, không giả vờ delivery guaranteed |
| Cập nhật giá/làm mới UI, chỉ quan tâm bản mới | Thiết kế coalescing/latest-value có chủ đích | `offer` không tự bỏ bản cũ để ưu tiên bản mới |
| Producer có deadline chặt | Timed `offer`, timeout và chính sách fallback | Timeout không khống chế thời gian `onNext` |
| Nhiều subscriber với tốc độ lệch lớn | Tách nhóm/cô lập subscriber, đo per-subscriber lag/drop | Một slow subscriber có thể kìm `submit` của tất cả |
| Mọi item đều cần retry đến khi có ack | Thiết kế queue/durable log + ack/retry ở cấp ứng dụng | `onDrop -> true` chỉ retry một lần, không đảm bảo delivery |

Mục tiêu là **kiểm soát tải**. Dù chọn `submit` hay `offer`, hãy đo tốc độ sản sinh, tốc độ tiêu thụ, tần suất drop, độ trễ `submit`, lag của subscriber, memory và trạng thái thread pool. Không tăng buffer vô hạn để né việc thiết kế flow control.

## 11. Tình huống lỗi phổ biến

### Lỗi A: quên `request(n)`

Subscriber đăng ký thành công nhưng không request, không nhận `onNext`. Producer vẫn gửi nhanh, buffer dần đầy; `submit` có thể treo. **Sửa:** luôn lưu `Subscription` và gọi `request` phù hợp, cấp lại demand theo mức độ xử lý xong. Nếu subscriber cố ý ngừng nhận, cần có cơ chế cancel/timeout/close pipeline ở tầng hệ thống.

### Lỗi B: `request(Long.MAX_VALUE)` rồi tin rằng hết backpressure

Demand lớn chỉ mở quyền giao, không giúp `onNext` chạy nhanh hơn. Nếu callback chậm, buffer vẫn đầy. **Sửa:** giảm tải, mở rộng/đổi cách xử lý callback phù hợp, hoặc chọn drop/backpressure policy rõ ràng.

### Lỗi C: dùng `submit` trong callback phụ thuộc chính publisher

Nếu callback giữ delivery worker mà producer chờ buffer của chính callback, có thể deadlock/starvation. **Sửa:** tránh vòng gọi đồng bộ, tách executor và đường chờ, hoặc đẩy tác vụ sang pipeline không phụ thuộc callback hiện tại.

### Lỗi D: tưởng `onDrop -> true` bảo đảm retry tới thành công

Handler chỉ yêu cầu **một** lần thử lại, vẫn có thể bị drop. **Sửa:** kiểm tra mã trả về, ghi metric, xây cơ chế retry/ack riêng nếu nghiệp vụ yêu cầu.

### Lỗi E: log/block lâu trong `onDrop`

Các producer khác có thể bị chặn trong lúc handler chạy. **Sửa:** chỉ ghi metric/counter nhẹ, tránh network I/O hoặc đợi futures trong handler; ghi log có giới hạn, không spam theo từng item với tốc độ rất cao.

### Lỗi F: dùng `status < 0` như số milliseconds

Đây là chỉ dấu drop; `status >= 0` là estimated max lag. **Sửa:** đo latency bằng clock/metrics riêng, không suy ra từ status.

### Lỗi G: dùng `getMaxBufferCapacity()` như giới hạn tổng RAM

Dung lượng theo subscriber; item có thể lớn và số subscriber biến động. **Sửa:** tính tổng footprint, memory pressure và backlogs. Theo dõi đối tượng được giữ trong buffer cho tới khi tiêu thụ/hủy.

### Lỗi H: dùng `offer` để truyền sự kiện không được phép mất

Offer có thể bỏ item ở subscriber bị đầy; không bảo đảm giao đều cho tất cả. **Sửa:** dùng chính sách không mất kèm downstream limits hoặc lưu bền vững/ack/replay ở cấp phù hợp.

### Lỗi I: quên đóng publisher và executor

`close()` đánh dấu hoàn tất, gửi tín hiệu `onComplete` cho các subscriber hiện tại khi các điều kiện giao tín hiệu được đáp ứng; gửi item mới sau đó bị từ chối. Nếu subscriber hoặc executor bị kẹt, việc giao tín hiệu hoàn tất cũng có thể chậm. **Sửa:** quản lý vòng đời executor, `Subscription.cancel()` và chính sách shutdown rõ ràng. Không gọi `closeExceptionally` nếu thực ra kết thúc bình thường; khi pipeline lỗi nghiêm trọng có thể phát `onError` bằng `closeExceptionally(Throwable)`.

### Lỗi J: dùng metric ước lượng làm điều kiện đồng bộ

`estimateMaximumLag()` và `estimateMinimumDemand()` là thông tin quan sát, có thể lệch khi nhiều thread thao tác. **Sửa:** dùng `Semaphore`/queue có giới hạn hoặc cơ chế điều phối khác nếu cần admission control chính xác.

## 12. Checklist trước khi đưa SubmissionPublisher vào ứng dụng

1. **Xác định yêu cầu dữ liệu**: mỗi item có bắt buộc tới mọi subscriber không, có thể drop hay cần ack/replay?
2. **Định nghĩa demand**: subscriber gọi `request` khi nào, xử lý xong/đang chờ/đã cancel thế nào?
3. **Chọn policy**: `submit` (chờ) hay `offer` (có thể drop), hoặc timed `offer` (chờ hạn chế). Ghi rõ timeout và hành vi `onDrop`.
4. **Đặt giới hạn tài nguyên**: dung lượng buffer theo subscriber, số subscriber, mức gọi đồng thời, executor capacity và tổng memory footprint.
5. **Kiểm tra tương tác khi quá tải**: subscriber không request, `onNext` block, executor bão hòa, interrupt và publisher close giữa lúc producer gửi.
6. **Theo dõi dữ liệu**: đo drops, lag estimates, latency của producer và `onNext`, subscriber count và executor saturation.
7. **Test có kiểm soát**: dùng latches/điều kiện rõ ràng để tái hiện buffer đầy; tránh kết luận từ `Thread.sleep` ngẫu nhiên trong test.
8. **Bảo vệ đúng nghĩa**: nếu cần giao hàng bền vững hoặc retry đến thành công, bổ sung queue/durable log/ack; `SubmissionPublisher` tự thân không làm thay việc đó.

## Tài liệu chính thức

- [Oracle Java 21 — SubmissionPublisher API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html): mô tả chính xác `submit`, hai overload `offer`, `onDrop` và mã trả về.
- [Oracle Java 21 — Flow API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html): quan hệ Publisher–Subscriber–Subscription, demand và tín hiệu.
- [Oracle Java 21 — Flow.Subscription](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html): `request` và `cancel`.
- [Oracle Java 21 — Flow.Subscriber](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html): thứ tự gọi `onSubscribe`, `onNext`, `onError` và `onComplete`.

**Điểm cốt lõi:** `submit()` chuyển sức ép từ buffer đầy sang **thời gian chờ của producer**; `offer()` chuyển nó thành **khả năng drop theo subscriber**. `offer(timeout, ...)` cho phép chờ có hạn trước khi áp dụng drop policy. Không phương thức nào tự giải quyết subscriber lỗi, executor thiếu tài nguyên hoặc yêu cầu bảo đảm giao hàng bền vững.
