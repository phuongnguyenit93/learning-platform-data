# Vai trò Publisher, Subscriber, Subscription và Processor

Java 9 đưa Flow API vào `java.util.concurrent.Flow` để xây dựng các pipeline truyền dữ liệu bất đồng bộ theo mô hình publish–subscribe. Bốn vai trò cốt lõi là `Publisher`, `Subscriber`, `Subscription` và `Processor`. Chúng phối hợp để phát dữ liệu, nhận dữ liệu, điều khiển lượng dữ liệu được yêu cầu và biến đổi dữ liệu giữa các bước.

Điểm quan trọng của Flow là **backpressure (điều tiết ngược)**: Subscriber báo trước số phần tử mà nó sẵn sàng nhận thông qua `Subscription.request(n)`. Publisher phải tôn trọng nhu cầu đó thay vì đẩy dữ liệu vô hạn vào một Subscriber chậm.

## Mục tiêu

- Hiểu trách nhiệm của bốn interface trong `Flow`.
- Nắm trình tự đăng ký và vòng đời tín hiệu của một Subscriber.
- Dùng `Subscription.request()` và `cancel()` để điều khiển luồng dữ liệu.
- Giải thích demand và backpressure.
- Hiểu Processor là một Subscriber ở đầu vào và Publisher ở đầu ra.
- Sử dụng `SubmissionPublisher` để tạo Publisher bất đồng bộ trong Java 9.
- Nhận biết cách xử lý lỗi, hoàn tất, hủy đăng ký và tài nguyên của pipeline.

## 1. Flow API là gì?

`Flow` là lớp chứa các interface lồng nhau trong package `java.util.concurrent`. API được thiết kế cho mô hình truyền dữ liệu bất đồng bộ giữa Publisher và Subscriber, có cơ chế Subscriber yêu cầu dữ liệu để kiểm soát tốc độ nhận.

| Interface | Vai trò |
| --- | --- |
| `Flow.Publisher<T>` | Nguồn phát các phần tử kiểu `T` tới Subscriber đã đăng ký |
| `Flow.Subscriber<T>` | Nhận đăng ký, phần tử, lỗi và tín hiệu hoàn tất |
| `Flow.Subscription` | Kết nối một Publisher với một Subscriber; điều khiển demand và cancellation |
| `Flow.Processor<T,R>` | Vừa là Subscriber nhận `T`, vừa là Publisher phát `R` |

Flow API được thiết kế theo cùng mô hình điều tiết dữ liệu của Reactive Streams. Các interface trong JDK thuộc package `java.util.concurrent.Flow`; nếu tích hợp với thư viện sử dụng kiểu `org.reactivestreams`, cần adapter tương thích thay vì truyền trực tiếp các interface khác package.

## 2. Publisher: nơi phát dữ liệu

`Flow.Publisher<T>` đại diện cho nguồn dữ liệu có thể đăng ký Subscriber. Interface có phương thức chính:

~~~java
void subscribe(Flow.Subscriber<? super T> subscriber);
~~~

Publisher nhận Subscriber và thiết lập một subscription riêng cho mối quan hệ đó. Một Publisher có thể hỗ trợ nhiều Subscriber; mỗi Subscriber có Subscription và demand riêng.

Ví dụ một nguồn phát chuỗi:

~~~java
SubmissionPublisher<String> publisher = new SubmissionPublisher<>();
publisher.subscribe(subscriber);
publisher.submit("hello");
publisher.close();
~~~

Đoạn mã dùng `SubmissionPublisher`, một implementation có sẵn trong JDK 9. `submit()` phát phần tử tới các Subscriber đã đăng ký; `close()` báo rằng nguồn đã hoàn tất và các phần tử đã gửi cần được xử lý trước tín hiệu hoàn tất.

### 2.1. Publisher phải tôn trọng demand

Publisher không được gửi nhiều phần tử `onNext()` hơn số lượng Subscriber đã yêu cầu. Nếu Subscriber đã yêu cầu một phần tử, Publisher có thể gửi tối đa một phần tử cho Subscription đó cho đến khi có thêm demand.

Một Publisher có thể phát cùng một phần tử logic tới nhiều Subscriber, nhưng việc mỗi Subscriber nhận được bao nhiêu phần tử phụ thuộc Subscription và chính sách của Publisher.

### 2.2. Publisher cần tuần tự hóa tín hiệu

Đối với một Subscriber, các tín hiệu `onSubscribe`, `onNext`, `onError` và `onComplete` phải tuân theo thứ tự của hợp đồng Flow. Không phát đồng thời các callback tới cùng một Subscriber theo cách khiến Subscriber phải xử lý hai tín hiệu cạnh tranh.

## 3. Subscriber: nơi nhận dữ liệu

`Flow.Subscriber<T>` định nghĩa bốn callback:

~~~java
public interface Subscriber<T> {
    void onSubscribe(Subscription subscription);
    void onNext(T item);
    void onError(Throwable throwable);
    void onComplete();
}
~~~

### 3.1. onSubscribe

Publisher gọi `onSubscribe()` để chuyển Subscription cho Subscriber. Đây là tín hiệu đầu tiên của một lần đăng ký. Subscriber thường lưu Subscription và gọi `request(n)` để bắt đầu nhận dữ liệu:

~~~java
public void onSubscribe(Flow.Subscription subscription) {
    this.subscription = subscription;
    subscription.request(1);
}
~~~

Subscriber có thể gọi `cancel()` ngay trong `onSubscribe()` nếu không muốn tiếp tục nhận dữ liệu.

### 3.2. onNext

Publisher gọi `onNext(item)` để chuyển một phần tử. Số lần gọi phải nằm trong giới hạn demand đã được yêu cầu.

~~~java
public void onNext(String item) {
    process(item);
    subscription.request(1);
}
~~~

Ví dụ trên yêu cầu thêm một phần tử sau khi xử lý xong phần tử hiện tại. Đây là cách đơn giản để biểu diễn Subscriber chỉ muốn xử lý từng phần tử một.

### 3.3. onError

`onError(throwable)` báo rằng Publisher hoặc pipeline đã kết thúc do lỗi. Đây là tín hiệu kết thúc: sau `onError()`, Subscriber không được nhận thêm `onNext()` hoặc một tín hiệu kết thúc khác cho cùng Subscription.

Subscriber nên ghi nhận lỗi, giải phóng tài nguyên thuộc quyền sở hữu của mình và hoàn tất trạng thái xử lý.

### 3.4. onComplete

`onComplete()` báo rằng Publisher đã phát xong dữ liệu bình thường. Đây cũng là tín hiệu kết thúc. Sau `onComplete()`, không có phần tử mới nào được gửi cho Subscriber đó.

`onError()` và `onComplete()` là hai kết quả kết thúc thay thế nhau; một Subscription chỉ có một tín hiệu kết thúc.

## 4. Subscription: điều khiển demand và cancellation

`Flow.Subscription` liên kết một Subscriber với Publisher. Nó có hai phương thức:

~~~java
void request(long n);
void cancel();
~~~

### 4.1. request(n)

`request(n)` thông báo Subscriber muốn nhận thêm tối đa `n` phần tử. Publisher dùng demand để điều chỉnh lượng dữ liệu phát ra.

| Cách gọi | Ý nghĩa |
| --- | --- |
| `request(1)` | Yêu cầu thêm một phần tử |
| `request(10)` | Yêu cầu thêm tối đa mười phần tử |
| `request(Long.MAX_VALUE)` | Yêu cầu một lượng demand rất lớn, thường được dùng như chế độ không giới hạn thực tế |

Giá trị `n` phải lớn hơn `0`. Nếu Subscriber gọi `request(n)` với `n <= 0`, Subscription phải báo lỗi theo hợp đồng Flow, thường bằng cách phát `onError(new IllegalArgumentException(...))`.

Demand được cộng dồn qua nhiều lần gọi `request()`. Publisher phải tránh tràn số khi cộng demand; `Long.MAX_VALUE` được dùng để biểu diễn demand không giới hạn thực tế.

### 4.2. cancel()

`cancel()` thông báo Subscriber không còn quan tâm tới dữ liệu của Subscription này. Sau khi hủy, Publisher nên dừng phát dữ liệu cho Subscriber đó và giải phóng tài nguyên liên quan khi có thể.

Cancellation là yêu cầu điều khiển luồng dữ liệu; nó không nhất thiết dừng ngay lập tức mọi công việc nội bộ đang diễn ra. Subscriber không nên dựa vào việc một callback đang chạy sẽ bị ngắt giữa chừng.

### 4.3. Subscription là riêng cho từng Subscriber

Nếu một Publisher có ba Subscriber, thông thường mỗi Subscriber nhận một Subscription riêng. Một Subscriber có thể yêu cầu một phần tử, Subscriber khác yêu cầu một trăm phần tử, và Subscriber thứ ba hủy đăng ký. Publisher cần quản lý demand và trạng thái của từng mối quan hệ độc lập.

## 5. Processor: vừa nhận vừa phát dữ liệu

`Flow.Processor<T,R>` kế thừa cả `Flow.Subscriber<T>` và `Flow.Publisher<R>`. Processor đứng giữa hai giai đoạn của pipeline:

~~~text
Publisher<T> -> Processor<T,R> -> Subscriber<R>
~~~

Processor nhận dữ liệu đầu vào kiểu `T`, xử lý hoặc biến đổi nó, rồi phát dữ liệu đầu ra kiểu `R`.

Các trường hợp sử dụng phổ biến:

- Chuyển đổi kiểu dữ liệu.
- Chuẩn hóa hoặc làm sạch dữ liệu.
- Lọc phần tử theo điều kiện.
- Chia hoặc kết hợp dữ liệu.
- Đệm dữ liệu hoặc tạo một ranh giới xử lý giữa hai giai đoạn.

Ví dụ, một Processor có thể nhận chuỗi thường và phát chuỗi viết hoa. Ở đầu vào, nó nhận `Subscription` từ Publisher upstream. Ở đầu ra, nó cung cấp Subscription cho các Subscriber downstream.

### 5.1. Processor phải quản lý cả hai phía

Vì Processor tham gia vào hai mối quan hệ, nó cần xử lý:

- `onSubscribe()` từ upstream và quyết định khi nào yêu cầu dữ liệu đầu vào.
- `onNext()` để biến đổi hoặc xử lý phần tử.
- Demand từ downstream để tránh tạo dữ liệu nhanh hơn khả năng tiêu thụ.
- `cancel()` và lỗi để tránh tiếp tục làm công việc không còn người nhận.
- `onError()` và `onComplete()` để truyền tín hiệu kết thúc tới downstream.

Chỉ triển khai `Processor` và gọi `submit()` không tự động tạo ra một chiến lược backpressure hoàn chỉnh. Processor sản xuất thực tế cần quản lý demand, buffer, cancellation và lỗi ở cả hai đầu.

## 6. Backpressure: Subscriber điều tiết tốc độ Publisher

Backpressure là cơ chế để bên tiêu thụ báo cho bên phát biết khả năng nhận dữ liệu hiện tại. Thay vì Publisher phát vô hạn và buộc Subscriber phải giữ mọi phần tử trong bộ nhớ, Subscriber chủ động yêu cầu lượng dữ liệu nó có thể xử lý.

Ví dụ Subscriber yêu cầu từng phần tử:

~~~java
public void onSubscribe(Flow.Subscription subscription) {
    this.subscription = subscription;
    subscription.request(1);
}

public void onNext(String item) {
    process(item);
    subscription.request(1);
}
~~~

Quy trình:

1. Subscriber nhận Subscription.
2. Subscriber yêu cầu một phần tử.
3. Publisher phát một `onNext()`.
4. Subscriber xử lý phần tử.
5. Subscriber yêu cầu thêm một phần tử.
6. Quy trình tiếp tục cho tới khi Publisher phát tín hiệu kết thúc hoặc Subscriber hủy.

### 6.1. Yêu cầu theo lô

Subscriber có thể yêu cầu một lô thay vì từng phần tử:

~~~java
subscription.request(100);
~~~

Yêu cầu theo lô có thể giảm chi phí điều phối callback, nhưng Subscriber phải có khả năng xử lý và lưu trữ lượng dữ liệu tương ứng.

### 6.2. Demand không phải là buffer

`request(n)` biểu thị số phần tử Subscriber sẵn sàng nhận; nó không trực tiếp cấp phát bộ nhớ cho Publisher. Publisher hoặc Processor có thể cần buffer để giữ dữ liệu đang chờ demand. Kích thước buffer và hành vi khi đầy là trách nhiệm của implementation.

Không nên gọi `request(Long.MAX_VALUE)` một cách máy móc cho mọi pipeline. Nếu nguồn dữ liệu rất lớn hoặc vô hạn, Subscriber chậm có thể khiến buffer tăng hoặc làm nghẽn hệ thống tùy implementation.

## 7. SubmissionPublisher trong JDK 9

`SubmissionPublisher<T>` là implementation của `Flow.Publisher<T>` được bổ sung trong Java 9. Nó phát dữ liệu bất đồng bộ tới các Subscriber bằng một `Executor` và quản lý buffer cho từng Subscriber.

Các thao tác quan trọng:

| API | Công dụng |
| --- | --- |
| `subscribe(subscriber)` | Đăng ký Subscriber |
| `submit(item)` | Gửi phần tử tới các Subscriber; có thể chặn khi buffer của Subscriber bị đầy |
| `offer(item, onDrop)` | Thử gửi mà không chờ buffer; cho phép xử lý trường hợp phần tử bị loại bỏ |
| `close()` | Đóng Publisher và báo hoàn tất bình thường sau các phần tử đã gửi |
| `closeExceptionally(error)` | Đóng Publisher với lỗi |
| `getNumberOfSubscribers()` | Lấy số Subscriber hiện tại |
| `estimateMaximumLag()` | Ước lượng độ trễ lớn nhất của các Subscriber |

`SubmissionPublisher` hữu ích khi cần một Publisher bất đồng bộ có buffer mà không phải tự viết toàn bộ cơ chế lập lịch và phát tín hiệu.

### 7.1. submit() và offer()

`submit()` phù hợp khi không được phép bỏ phần tử. Nếu một Subscriber chậm và buffer của nó đạt giới hạn, lời gọi có thể phải chờ cho đến khi có chỗ.

`offer()` cho phép Publisher thử gửi mà không chặn lâu theo cùng cách; nếu không thể đưa phần tử vào buffer, chính sách drop handler được dùng để quyết định cách xử lý. Dùng `offer()` đồng nghĩa ứng dụng phải định nghĩa rõ việc mất phần tử có được chấp nhận hay không.

Không dùng `offer()` nếu dữ liệu là sự kiện bắt buộc phải xử lý đầy đủ mà không có cơ chế lưu bền vững hoặc retry.

### 7.2. Executor và tính bất đồng bộ

Subscriber của `SubmissionPublisher` được gọi thông qua executor. Có thể truyền executor riêng khi tạo publisher để kiểm soát tài nguyên và mức độ song song:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(4);
SubmissionPublisher<String> publisher = new SubmissionPublisher<>(
    executor, Flow.defaultBufferSize()
);
~~~

Đóng Publisher không thay thế việc shutdown executor do ứng dụng tạo và sở hữu. Hãy đóng publisher, chờ các tác vụ cần thiết hoàn tất, rồi shutdown executor theo vòng đời của ứng dụng.

## 8. Ví dụ hoàn chỉnh: Publisher → Processor → Subscriber

Ví dụ tạo một pipeline ba tầng:

- `SubmissionPublisher<String>` là Publisher nguồn.
- `UpperCaseProcessor` nhận chuỗi, chuyển thành chữ hoa và phát tiếp.
- `PrintSubscriber` nhận từng phần tử và yêu cầu thêm một phần tử sau mỗi lần xử lý.

**Tệp:** `FlowRolesDemo.java`

~~~java
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class FlowRolesDemo {
    static final class UpperCaseProcessor extends SubmissionPublisher<String>
            implements Flow.Processor<String, String> {
        private Flow.Subscription upstream;

        UpperCaseProcessor(ExecutorService executor) {
            super(executor, Flow.defaultBufferSize());
        }

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            if (upstream != null) {
                subscription.cancel();
                return;
            }
            upstream = subscription;
            upstream.request(1);
        }

        @Override
        public void onNext(String item) {
            submit(item.toUpperCase(Locale.ROOT));
            upstream.request(1);
        }

        @Override
        public void onError(Throwable throwable) {
            closeExceptionally(throwable);
        }

        @Override
        public void onComplete() {
            close();
        }
    }

    static final class PrintSubscriber implements Flow.Subscriber<String> {
        private final CountDownLatch done;
        private Flow.Subscription subscription;

        PrintSubscriber(CountDownLatch done) {
            this.done = done;
        }

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            System.out.println("subscriber ready");
            subscription.request(1);
        }

        @Override
        public void onNext(String item) {
            System.out.println("received: " + item);
            subscription.request(1);
        }

        @Override
        public void onError(Throwable throwable) {
            System.out.println("error: " + throwable.getClass().getSimpleName());
            done.countDown();
        }

        @Override
        public void onComplete() {
            System.out.println("completed");
            done.countDown();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newFixedThreadPool(4);
        SubmissionPublisher<String> source = new SubmissionPublisher<>(
            executor, Flow.defaultBufferSize()
        );
        UpperCaseProcessor processor = new UpperCaseProcessor(executor);
        CountDownLatch done = new CountDownLatch(1);

        try {
            processor.subscribe(new PrintSubscriber(done));
            source.subscribe(processor);
            source.submit("alpha");
            source.submit("beta");
            source.submit("gamma");
            source.close();

            if (!done.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Flow pipeline timed out");
            }
        } finally {
            source.close();
            processor.close();
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 9 trở lên:

~~~text
javac --release 9 FlowRolesDemo.java
java FlowRolesDemo
~~~

Output:

~~~text
subscriber ready
received: ALPHA
received: BETA
received: GAMMA
completed
~~~

### 8.1. Giải thích luồng xử lý

1. `processor.subscribe(new PrintSubscriber(done))` đăng ký Subscriber ở đầu ra Processor.
2. `source.subscribe(processor)` đăng ký Processor làm Subscriber của Publisher nguồn.
3. Khi Processor nhận `onSubscribe()`, nó yêu cầu một phần tử từ upstream.
4. Khi Processor nhận `onNext()`, nó chuyển chuỗi thành chữ hoa rồi gửi qua `SubmissionPublisher.submit()`.
5. Processor yêu cầu thêm một phần tử upstream sau khi đã gửi phần tử hiện tại.
6. Subscriber nhận `onSubscribe()` và yêu cầu một phần tử. Sau mỗi `onNext()`, nó yêu cầu thêm một phần tử.
7. Khi nguồn đóng, Processor nhận `onComplete()` và đóng Publisher đầu ra. Subscriber nhận `onComplete()`.

Ví dụ dùng executor có bốn thread và `CountDownLatch` để chờ tín hiệu kết thúc. Trong hệ thống thực tế, cần chọn executor, buffer và chính sách lỗi theo tải thực tế.

### 8.2. Giới hạn của Processor minh họa

Processor trong ví dụ dùng `SubmissionPublisher` để quản lý buffer downstream và yêu cầu upstream từng phần tử. `submit()` có thể chặn khi buffer downstream đầy. Đây là ví dụ học tập về bốn vai trò và demand; một Processor production cần thiết kế rõ giới hạn buffer, cách truyền cancellation ngược upstream, cách xử lý exception khi transform và chính sách khi subscriber chậm hoặc biến mất.

## 9. Quy tắc tín hiệu và vòng đời

Một Subscriber cần tuân theo trình tự tín hiệu sau:

~~~text
onSubscribe(subscription)
        |
        v
   request(n) <------------------+
        |                        |
        v                        |
     onNext(item) ---------------+
        |
        +---- onNext(item) ...
        |
        +---- onComplete()
        |
        +---- onError(error)
~~~

Các quy tắc quan trọng:

- `onSubscribe()` phải được gọi trước các callback còn lại của lần đăng ký.
- Publisher chỉ gửi số phần tử trong giới hạn demand.
- `onError()` hoặc `onComplete()` kết thúc luồng tín hiệu của Subscription.
- Sau tín hiệu kết thúc, không gửi thêm `onNext()`.
- `request(n)` với `n <= 0` là yêu cầu không hợp lệ và phải dẫn tới xử lý lỗi theo hợp đồng Flow.
- `cancel()` báo rằng Subscriber không còn muốn nhận thêm phần tử.
- Tín hiệu tới cùng một Subscriber phải được tuần tự hóa; không yêu cầu Subscriber xử lý callback đồng thời.

## 10. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Publisher phát nhiều phần tử hơn demand | Không quản lý bộ đếm request | Theo dõi demand và chỉ phát trong giới hạn đã yêu cầu |
| Subscriber quên gọi request | Không có demand nên Publisher không có quyền phát phần tử tiếp | Gọi `request()` trong `onSubscribe()` hoặc sau khi xử lý phần tử |
| Gọi `request(0)` hoặc số âm | Demand không hợp lệ | Chỉ yêu cầu số dương; xử lý `onError()` |
| Gọi `request(Long.MAX_VALUE)` cho nguồn không giới hạn | Subscriber có thể nhận dữ liệu nhanh hơn khả năng xử lý | Yêu cầu theo lô vừa đủ hoặc theo từng phần tử |
| Processor không quản lý demand downstream | Có thể tạo dữ liệu nhanh hơn tốc độ tiêu thụ | Kết hợp demand, buffer có giới hạn và upstream request |
| Không truyền lỗi tới downstream | Pipeline có thể chờ mãi hoặc mất nguyên nhân lỗi | Chuyển `onError()` và đóng publisher đầu ra exceptional |
| Không truyền completion | Subscriber không biết pipeline đã kết thúc | Gọi `close()` hoặc phát `onComplete()` theo hợp đồng |
| Bỏ qua cancel | Tiếp tục làm việc dù không còn subscriber cần dữ liệu | Hủy upstream, ngừng sản xuất và giải phóng tài nguyên |
| Dùng submit() với subscriber quá chậm mà không hiểu buffer | submit có thể chặn khi buffer đầy | Chọn buffer, executor và chính sách backpressure phù hợp |
| Dùng offer() nhưng bỏ qua phần tử bị drop | Dữ liệu có thể mất âm thầm | Định nghĩa drop handler, retry hoặc lưu bền vững |
| Shutdown executor quá sớm | Callback bất đồng bộ chưa được thực thi | Đóng publisher và chờ hoàn tất trước khi shutdown executor |

## 11. Quy tắc thực hành

1. Dùng `Publisher` cho nguồn phát dữ liệu và `Subscriber` cho bên tiêu thụ.
2. Xem `Subscription` là hợp đồng điều khiển giữa đúng một Publisher và Subscriber.
3. Yêu cầu demand rõ ràng bằng `request(n)`; chỉ dùng demand không giới hạn khi thật sự phù hợp.
4. Luôn xử lý `onError()` và `onComplete()` như tín hiệu kết thúc.
5. Gọi `cancel()` khi Subscriber không còn cần dữ liệu.
6. Khi viết `Processor`, quản lý cả demand upstream lẫn downstream, buffer và cancellation.
7. Dùng `SubmissionPublisher` khi cần implementation Publisher bất đồng bộ có sẵn trong JDK.
8. Chọn `submit()` khi không muốn bỏ dữ liệu và chấp nhận backpressure; chọn `offer()` chỉ khi có chính sách drop rõ ràng.
9. Dùng executor có vòng đời được quản lý; đừng shutdown executor trước khi callback hoàn tất.
10. Kiểm thử cả luồng thành công, lỗi, hủy đăng ký và Subscriber xử lý chậm.

## 12. Tự kiểm tra

- `Publisher<T>` chịu trách nhiệm gì? Phát các phần tử tới Subscriber đã đăng ký.
- `Subscriber<T>` có những callback nào? `onSubscribe`, `onNext`, `onError` và `onComplete`.
- `Subscription` dùng để làm gì? Yêu cầu thêm dữ liệu bằng `request(n)` hoặc hủy bằng `cancel()`.
- Vì sao Subscriber cần gọi `request()`? Để báo demand và cho Publisher biết lượng dữ liệu nó sẵn sàng nhận.
- `request(0)` có hợp lệ không? Không; demand phải là số dương.
- `Processor<T,R>` khác Subscriber thông thường thế nào? Nó vừa nhận `T` như Subscriber vừa phát `R` như Publisher.
- Backpressure giải quyết vấn đề gì? Điều tiết tốc độ phát theo khả năng tiêu thụ, hạn chế việc bên nhận bị quá tải.
- `SubmissionPublisher.submit()` có thể chặn không? Có, khi buffer của Subscriber chậm đã đầy.
- `SubmissionPublisher.close()` báo điều gì? Nguồn đã hoàn tất và Subscriber sẽ nhận tín hiệu hoàn tất sau dữ liệu đã gửi.
- `cancel()` có đồng nghĩa với việc dừng ngay mọi callback đang chạy không? Không; đó là yêu cầu ngừng nhận thêm dữ liệu và giải phóng công việc liên quan theo khả năng.

Điểm cốt lõi: **Publisher phát dữ liệu, Subscriber nhận dữ liệu, Subscription điều khiển demand/cancellation, còn Processor nhận rồi phát tiếp dữ liệu đã xử lý.** Backpressure là trách nhiệm chung của pipeline; mỗi tầng cần tôn trọng demand và quản lý vòng đời tín hiệu.