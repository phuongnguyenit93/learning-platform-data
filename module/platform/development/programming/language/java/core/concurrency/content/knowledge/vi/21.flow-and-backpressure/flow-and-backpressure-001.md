# Flow API trong java.util.concurrent

## 1. Flow giải quyết vấn đề gì?

Khi một thành phần tạo dữ liệu nhanh hơn thành phần xử lý, việc đẩy dữ liệu vô điều kiện có thể làm hàng đợi phình to, tăng bộ nhớ, làm hệ thống chậm hoặc hết heap. **Backpressure** là cơ chế để bên nhận thông báo khả năng tiếp nhận, giúp bên phát điều chỉnh số lượng phần tử gửi.

Từ **Java 9**, Java cung cấp `java.util.concurrent.Flow`: tập các interface nền tảng cho mô hình **Publisher–Subscriber có điều khiển nhu cầu (demand)**. Flow mô tả hợp đồng truyền các tín hiệu dữ liệu, hoàn tất, lỗi và cơ chế đăng ký/yêu cầu số lượng; nó không tự biến mọi đoạn xử lý thành một hệ thống không chặn, không tự cung cấp hàng trăm toán tử biến đổi và cũng không quyết định cách lưu trữ dữ liệu thay cho ứng dụng.

Flow hữu ích khi xây dựng pipeline bất đồng bộ giữa producer và consumer, xử lý stream sự kiện, kết nối các tầng xử lý nhiều tốc độ và học các nguyên lý Reactive Streams. Nội dung này tập trung vào **Java concurrency nói chung** và các class của JDK, không phụ thuộc framework khác.

### Tư duy cốt lõi

Thay vì producer cứ gọi `consumer.accept(item)` không kiểm soát tốc độ, subscriber có thể nói: **“Tôi sẵn sàng nhận thêm n item.”** Publisher chỉ được phát `onNext` trong hạn mức yêu cầu chưa được sử dụng của subscription đó.

```text
                  subscribe(subscriber)
  Publisher --------------------------------> Subscriber
             onSubscribe(subscription)
            <--------------------------------
                 request(2)
            <--------------------------------
                   onNext(A)
            -------------------------------->
                   onNext(B)
            -------------------------------->
                 request(1)
            <--------------------------------
                   onNext(C)
            -------------------------------->
          onComplete() hoặc onError(error)
            -------------------------------->
```

Các mũi tên thể hiện **luồng tín hiệu logic**, không yêu cầu mọi callback phải chạy trên thread riêng hoặc cùng thread; điều đó tùy triển khai.

## 2. Bốn interface trọng tâm

| Interface | Vai trò | Phương thức quan trọng |
| --- | --- | --- |
| `Flow.Publisher<T>` | Nguồn phát dữ liệu kiểu `T` cho các subscriber | `subscribe(Subscriber<? super T>)` |
| `Flow.Subscriber<T>` | Bên nhận dữ liệu, quyết định nhu cầu và xử lý các sự kiện | `onSubscribe`, `onNext`, `onError`, `onComplete` |
| `Flow.Subscription` | Liên kết giữa một publisher và một subscriber; mang tín hiệu demand/cancel | `request(long n)`, `cancel()` |
| `Flow.Processor<T,R>` | Vừa là subscriber nhận `T`, vừa là publisher phát `R`, có thể biến đổi/lọc dữ liệu | Kế thừa `Subscriber<T>` và `Publisher<R>` |

### Publisher

`Publisher.subscribe(...)` đăng ký một subscriber. Sau khi đăng ký hợp lệ, subscriber được cung cấp một đối tượng `Subscription` qua `onSubscribe`. Publisher có thể có một hoặc nhiều subscriber; chính sách replay, multicast, buffer và bắt đầu phát do implementation quyết định, **không suy ra rằng mọi publisher đều ghi lại lịch sử để người đăng ký muộn đọc lại**.

### Subscriber và bốn tín hiệu

Một subscriber có vòng đời điển hình:

1. **`onSubscribe(subscription)`**: nhận liên kết; thường lưu subscription rồi gọi `request(n)`. Không yêu cầu thì không có quyền nhận item mới.
2. **`onNext(item)`**: xử lý một item đã được yêu cầu; có thể yêu cầu thêm số lượng sau khi hoàn tất xử lý.
3. **`onError(throwable)`**: kết thúc do lỗi; không có thêm tín hiệu thông thường sau terminal signal.
4. **`onComplete()`**: kết thúc bình thường khi nguồn không còn item; không có thêm `onNext` sau đó.

Với cùng một subscription, các lời gọi tín hiệu tới subscriber được tổ chức theo thứ tự và bảo đảm quan hệ *happens-before*, dù triển khai có thể sử dụng nhiều thread khác nhau. Không suy ra thứ tự tổng thể giữa **các subscription khác nhau**.

### Subscription

`request(n)` **cộng thêm** n vào nhu cầu chưa đáp ứng; nó không đặt lại demand bằng n. Với n dương, publisher có thể gọi tối đa thêm n lần `onNext` theo lượng demand đã có; mỗi `onNext` tiêu thụ một đơn vị. Nếu `n <= 0`, subscriber phải nhận tín hiệu `onError` với `IllegalArgumentException`. Giá trị `Long.MAX_VALUE` thường được coi là nhu cầu gần như vô hạn.

`cancel()` yêu cầu dừng nhận dữ liệu theo cách **best effort**: vẫn có thể có tín hiệu đã lên lịch đến sau khi cancel, và subscriber đã cancel không được bảo đảm nhận `onComplete`/`onError`. Vì thế, cancel không đồng nghĩa hủy mọi công việc trong hệ thống ngay lập tức.

### Processor

`Processor<T,R>` vừa nhận tín hiệu đầu vào, vừa phát đầu ra. Một pipeline:

```text
Publisher<Integer>
    |
    v
Processor<Integer, String>  (đổi số thành chuỗi)
    |
    v
Subscriber<String>
```

Một processor đúng phải quản lý **demand ở cả hai phía**: không nhận dữ liệu upstream vô hạn nếu downstream không xử lý kịp, trừ khi chính nó có chiến lược buffer/drop được kiểm soát. `Flow.Processor` là interface, **không tự thực hiện phép map/filter hoặc lan truyền backpressure**.

## 3. Backpressure hoạt động như thế nào?

Giả sử một subscriber bắt đầu với `request(2)`:

| Thời điểm | Hành động | Demand còn lại |
| --- | --- | --- |
| Ban đầu | `onSubscribe`, chưa gọi request | 0 |
| T1 | `request(2)` | 2 |
| T2 | Nhận `onNext(A)` | 1 |
| T3 | Nhận `onNext(B)` | 0 |
| T4 | Producer có item C | C chưa được phát qua `onNext` nếu không có demand mới |
| T5 | `request(3)` | 3 |
| T6 | Nhận `onNext(C)` | 2 |

Ở T4, publisher có thể giữ item trong buffer, trì hoãn nguồn sinh dữ liệu, chặn publisher, áp dụng drop policy hoặc làm gì khác theo hợp đồng triển khai. **Flow quy định giới hạn phát `onNext`, không bảo đảm toàn bộ pipeline dùng bộ nhớ hữu hạn trong mọi implementation.**

Có hai cách yêu cầu phổ biến:

- **Theo từng phần tử:** `request(1)` trong `onSubscribe`, rồi gọi tiếp `request(1)` sau khi xử lý mỗi `onNext`. Dễ hiểu và kiểm soát số phần tử đang được cho phép.
- **Theo lô (batch/prefetch):** yêu cầu ban đầu, chẳng hạn 32 hoặc 64 item, rồi bổ sung khi đã xử lý một phần lô. Thường giảm chi phí điều phối so với yêu cầu từng item, nhưng cho phép nhiều item in-flight hơn.

Kích thước batch phù hợp phụ thuộc độ trễ nguồn, chi phí xử lý, kích thước item và bộ nhớ chấp nhận được. `request(Long.MAX_VALUE)` có thể hợp lý khi dữ liệu nhỏ và bên nhận thật sự xử lý kịp, nhưng làm mất khả năng dùng demand để hạn chế luồng item.

## 4. Ví dụ Java 17+: subscriber tự yêu cầu từng item

JDK cung cấp `SubmissionPublisher<T>`, một publisher có buffer riêng cho từng subscriber và gửi tín hiệu bất đồng bộ qua `Executor`. Ta dùng nó để quan sát chu trình request–onNext–complete.

Lưu tệp **`FlowBasicsDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class FlowBasicsDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch done = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Flow.Subscriber<Integer> subscriber = new Flow.Subscriber<>() {
            private Flow.Subscription subscription;

            @Override
            public void onSubscribe(Flow.Subscription subscription) {
                this.subscription = subscription;
                subscription.request(1);
            }

            @Override
            public void onNext(Integer item) {
                System.out.println("received=" + item);
                subscription.request(1);
            }

            @Override
            public void onError(Throwable error) {
                failure.set(error);
                done.countDown();
            }

            @Override
            public void onComplete() {
                System.out.println("completed");
                done.countDown();
            }
        };

        try (SubmissionPublisher<Integer> publisher =
                     new SubmissionPublisher<>()) {
            publisher.subscribe(subscriber);
            publisher.submit(10);
            publisher.submit(20);
            publisher.submit(30);
        }

        if (!done.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timed out");
        }
        if (failure.get() != null) {
            throw new IllegalStateException("Subscriber failed", failure.get());
        }
    }
}
```

Biên dịch và chạy (JDK 17 trở lên):

```bash
javac -encoding UTF-8 FlowBasicsDemo.java
java FlowBasicsDemo
```

Stdout khi chạy thành công:

```text
received=10
received=20
received=30
completed
```

**Giải thích:**

- `SubmissionPublisher` cung cấp thực thi sẵn cho `Flow.Publisher`; subscriber không phải tự quản lý queue hoặc đồng bộ callback.
- `onSubscribe` mở demand là 1. Sau mỗi item, `onNext` yêu cầu thêm một item. Do đó subscriber chủ động điều tiết quá trình nhận.
- `submit(...)` có thể trả về trước khi subscriber đã xử lý xong, vì delivery là bất đồng bộ. Không dùng `Thread.sleep(...)` tùy ý để “đợi đủ”; demo dùng `CountDownLatch` và timeout.
- `try-with-resources` đóng publisher và phát `onComplete` sau khi dữ liệu đã được xử lý theo thứ tự cho subscriber đó. `done.await(...)` giữ main thread sống đến khi nhận terminal signal.
- `AtomicReference<Throwable>` giúp truyền lỗi từ callback sang main để không báo thành công giả.

Lưu ý về output: ba dòng `received` có thứ tự xác định với **cùng một subscription**; executor có thể chọn thread nào chạy callback mà không ảnh hưởng thứ tự logic đó.

## 5. Ví dụ Java 17+: chứng minh không có demand thì chưa nhận onNext

Để thấy subscriber là bên cấp quyền nhận item, ví dụ sau **chủ động trì hoãn `request`**. `SubmissionPublisher` có thể giữ các item đã submit trong buffer ngay cả khi subscriber chưa yêu cầu.

Lưu tệp **`FlowDemandDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class FlowDemandDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch subscribed = new CountDownLatch(1);
        CountDownLatch firstReceived = new CountDownLatch(1);
        CountDownLatch completed = new CountDownLatch(1);
        AtomicReference<Flow.Subscription> control = new AtomicReference<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Flow.Subscriber<String> subscriber = new Flow.Subscriber<>() {
            @Override
            public void onSubscribe(Flow.Subscription subscription) {
                control.set(subscription);
                subscribed.countDown();
            }

            @Override
            public void onNext(String item) {
                System.out.println("onNext: " + item);
                if ("A".equals(item)) firstReceived.countDown();
            }

            @Override
            public void onError(Throwable throwable) {
                failure.set(throwable);
                completed.countDown();
            }

            @Override
            public void onComplete() {
                System.out.println("onComplete");
                completed.countDown();
            }
        };

        try (SubmissionPublisher<String> publisher =
                     new SubmissionPublisher<>()) {
            publisher.subscribe(subscriber);
            if (!subscribed.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("No onSubscribe");
            }

            publisher.submit("A");
            publisher.submit("B");

            System.out.println("request(1)");
            control.get().request(1);
            if (!firstReceived.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("First item not delivered");
            }

            System.out.println("request(1) again");
            control.get().request(1);
            publisher.close();

            if (!completed.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("No completion");
            }
        }

        if (failure.get() != null) {
            throw new IllegalStateException("Flow failed", failure.get());
        }
    }
}
```

```bash
javac -encoding UTF-8 FlowDemandDemo.java
java FlowDemandDemo
```

Stdout khi chạy thành công:

```text
request(1)
onNext: A
request(1) again
onNext: B
onComplete
```

`firstReceived.await` buộc main đợi A được in trước khi gửi demand thứ hai. Nhờ vậy thứ tự output không phụ thuộc lịch chạy của executor. `publisher.close()` báo không còn item mới và gửi tín hiệu kết thúc sau các item đã được xếp hàng cho subscription. Đây là một demo với buffer không bão hòa: **không có demand chỉ ngăn callback `onNext`, không nhất thiết ngăn producer gọi `submit` ngay lập tức**.

## 6. SubmissionPublisher: buffer, executor và chính sách khi consumer chậm

`SubmissionPublisher<T>` là implementation có sẵn của `Flow.Publisher<T>` từ Java 9; lớp này thực hiện phát item **bất đồng bộ** cho các subscriber đang đăng ký.

### Khởi tạo

```java
// Đoạn minh họa, không phải chương trình độc lập:
SubmissionPublisher<String> publisher = new SubmissionPublisher<>();

// Hoặc chỉ định Executor và dung lượng buffer mục tiêu cho mỗi subscriber:
SubmissionPublisher<String> custom =
        new SubmissionPublisher<>(executor, 64);
```

Biến `executor` ở ví dụ thứ hai là một `Executor` do ứng dụng cung cấp và phải được quản lý vòng đời riêng khi cần; không có khai báo nên đoạn trên chỉ minh họa API. Constructor mặc định thường sử dụng `ForkJoinPool.commonPool()` và dung lượng mặc định `Flow.defaultBufferSize()`. Không hard-code giá trị mặc định vì có thể phụ thuộc phiên bản/triển khai.

Mỗi subscriber có **buffer độc lập**. Khi publisher phát nhiều hơn tốc độ subscriber yêu cầu và xử lý, buffer của subscriber đó có thể đầy; dung lượng được thực thi có thể làm tròn so với con số truyền vào constructor. `getMaxBufferCapacity()` trả về dung lượng thực tế của publisher.

### `submit`, `offer` và `close`

| API | Hành vi và lựa chọn |
| --- | --- |
| `submit(item)` | Phát item không-null tới các subscriber hiện tại; có thể **block không ngắt được** khi tài nguyên/buffer chưa sẵn cho subscriber chậm. Kết quả trả về là ước lượng lag tối đa, không phải số item đã xử lý. |
| `offer(item, onDrop)` | Thử phát mà không chờ không giới hạn; khi thiếu chỗ, có thể drop cho một hoặc nhiều subscriber, gọi handler và thử lại một lần nếu handler trả `true`. |
| `offer(item, timeout, unit, onDrop)` | Cho phép đợi có giới hạn; sau đó áp dụng hành vi drop/retry phù hợp. |
| `close()` | Ngăn submit mới và phát `onComplete` cho subscribers hiện tại. |
| `closeExceptionally(error)` | Kết thúc bằng tín hiệu `onError`. |
| `estimateMaximumLag()` | Thông tin **ước lượng để quan sát**, không được dùng như khóa đồng bộ chính xác. |

Với `offer`, kết quả **âm** chỉ báo các lần drop không phát được; kết quả không âm là ước lượng lag, không nên diễn giải như một cam kết không mất dữ liệu tuyệt đối. `onDrop` có thể được gọi trong lúc publisher giữ khóa nội bộ; tránh xử lý phức tạp hoặc block trong handler.

**Trade-off quan trọng:**

- `submit` thường giữ được item theo semantics của publisher nhưng có thể khiến thread sản xuất bị chặn bởi một subscriber chậm.
- `offer` giúp producer phản hồi nhanh hơn khi thiếu chỗ, đổi lại **có thể mất item**. Chỉ dùng drop policy khi sản phẩm hoặc nghiệp vụ cho phép.
- Tăng buffer có thể làm giảm block/drop trong burst ngắn, nhưng làm tăng bộ nhớ; buffer lớn **không xử lý được consumer chậm liên tục**.
- Nhiều subscriber có demand khác nhau, buffer riêng và lịch callback riêng. Một subscriber chậm có thể tác động khả năng gọi `submit` do publisher phải xét tình trạng tài nguyên của từng subscription.

**Lưu ý:** “Publisher hỗ trợ backpressure” không đảm bảo toàn bộ hệ thống không bao giờ bị đầy bộ nhớ. Phải xem producer tạo item trước khi submit thế nào, có queue nào ở phía trước hay không, tốc độ downstream, dung lượng buffer và chính sách overflow.

## 7. Processor: kết nối các giai đoạn xử lý

Một pipeline thường gồm nguồn → xử lý → đích. `Flow.Processor<T,R>` là hợp đồng để một thành phần nhận item kiểu `T` rồi phát item kiểu `R`. Nó có thể chuyển đổi dữ liệu, lọc hoặc tổng hợp, nhưng **phải tự quản lý subscription, trạng thái, demand, lỗi và tín hiệu kết thúc**.

### Khung processor minh họa

```java
// Khung ý tưởng đặt bên trong một lớp; không phải chương trình hoàn chỉnh:
final class DoublingProcessor
        extends SubmissionPublisher<Integer>
        implements Flow.Processor<Integer, Integer> {

    private Flow.Subscription upstream;

    @Override
    public void onSubscribe(Flow.Subscription subscription) {
        upstream = subscription;
        upstream.request(1);
    }

    @Override
    public void onNext(Integer item) {
        submit(item * 2);
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
```

Đây là minh họa một phép biến đổi **một đầu vào → một đầu ra** dùng buffering của `SubmissionPublisher`. Nếu downstream chậm và buffer đầy, `submit` có thể chặn trước khi yêu cầu upstream tiếp. Đó là một cách nối backpressure đơn giản, nhưng việc gọi `request(1)` theo từng item **không thay thế** phân tích buffer, cancellation, vòng đời và xử lý exception.

Để triển khai processor thực tế, còn phải xử lý các trường hợp như nhiều downstream, cancel ở downstream làm ảnh hưởng upstream thế nào, overflow, rejected executor, race khi terminal signal đến và cleanup. Flow chỉ cung cấp interface; không cung cấp sẵn cơ chế truyền toàn bộ nhu cầu ngược qua mọi processor tùy ý.

## 8. Các nguyên tắc an toàn khi tự implement Publisher/Subscriber

**Không gửi onNext vượt demand.** Subscriber `request(3)` không có nghĩa publisher được phát bốn item rồi hứa xử lý sau. Publisher tùy chỉnh phải phối hợp thread và bộ đếm demand; khi cộng demand lớn cần tránh tràn `long`, thường dùng phép cộng bão hòa ở `Long.MAX_VALUE`.

**Đảm bảo callback theo thứ tự cho từng subscription.** Không gọi `onNext` đồng thời hoặc lộn thứ tự vào cùng một subscriber. JavaDoc `Flow.Publisher` yêu cầu thứ tự chặt chẽ và quan hệ *happens-before* giữa các tín hiệu của một subscription.

**Kết thúc đúng một lần.** Sau `onComplete` hoặc `onError` không được gửi thêm `onNext`. Sai `request(0)` hoặc `request(-1)` phải dẫn tới `onError(IllegalArgumentException)`.

**Tôn trọng cancel.** Khi bị hủy, dừng phát trong khả năng cho phép, giải phóng tham chiếu và ngừng công việc thừa. Do cancel là best effort, bên nhận cũng cần chuẩn bị cho những callback đã được lên lịch trước đó.

**Không block tùy tiện trong callback.** `onNext` xử lý quá lâu sẽ làm nghẽn executor, tăng lag và buffer. Nếu cần chuyển xử lý sang queue khác, queue đó cũng cần capacity/giới hạn; không thể né backpressure bằng cách tạo một queue vô hạn nằm bên trong `onNext`.

**Tính tới việc callback ném exception.** Một subscriber phải xử lý lỗi ứng dụng có chủ đích. Không giả định publisher tự khôi phục sau exception trong `onNext` hoặc sẽ tiếp tục các item như bình thường. Chính sách hủy, error handler và đóng tài nguyên phải được xác định.

**Không suy diễn toàn hệ thống từ một subscription.** Thứ tự của item của một subscriber được đảm bảo theo hợp đồng; thời điểm subscriber khác xử lý item có thể khác. Thiết kế dữ liệu chia sẻ phải đảm bảo thread safety độc lập.

## 9. Flow khác Stream và BlockingQueue thế nào?

| Công cụ | Dạng dữ liệu/tương tác | Điểm khác cần nhớ |
| --- | --- | --- |
| `java.util.stream.Stream` | Pipeline thao tác trên nguồn dữ liệu, thường được xử lý khi terminal operation chạy | Không có hợp đồng subscription/demand kiểu `Flow`; không phải một async event stream chỉ vì tên có “stream”. |
| `BlockingQueue` | Producer/consumer trao đổi qua hàng đợi hữu hạn hoặc không hữu hạn | Bên nhận có thể `take`, producer có thể `put`; backpressure qua capacity chứ không phải `request(n)`. |
| `Flow` | Giao diện phát/nhận bất đồng bộ theo subscription và demand | Định nghĩa hợp đồng tín hiệu, không chọn buffer/executor/overflow cho bạn. |
| `SubmissionPublisher` | Implementation publisher có thể dùng ngay | Hỗ trợ buffer, executor, `submit`/`offer`, multicast cho subscriber hiện tại. |
| `CompletableFuture<T>` | Biểu diễn một kết quả hoặc lỗi trong tương lai | Không cung cấp dòng nhiều item cùng hợp đồng demand. |

Nếu chỉ cần một queue công việc nhiều producer/consumer, `ArrayBlockingQueue` hoặc `LinkedBlockingQueue` có thể dễ quản lý hơn. Nếu chỉ cần tính toán trên một danh sách sẵn có, `Stream` thường phù hợp hơn. Flow hữu ích khi cần **đầu ra nhiều item, bên nhận có thể yêu cầu số lượng, và các stage được kết nối bằng subscription**.

## 10. Thiết kế và giám sát pipeline thực tế

Trước khi chọn cấu hình, xác định:

1. **Nguồn:** dữ liệu đến từ đâu, có tạm dừng được không, có cần thứ tự và delivery guarantee nào?
2. **Subscriber:** công việc mỗi item mất bao lâu; có thể xử lý song song không; có cần giữ nguyên thứ tự không?
3. **Demand:** yêu cầu từng item hay theo lô; nên tăng demand ở thời điểm bắt đầu hay hoàn tất xử lý?
4. **Capacity:** publisher và từng stage có những buffer nào; tổng bộ nhớ tệ nhất theo số subscribers là bao nhiêu?
5. **Quá tải:** chặn, đợi có timeout, drop, retry, hay báo lỗi; tác động nghiệp vụ của mất item là gì?
6. **Lifecycle:** ai đóng publisher, ai hủy subscription, ai sở hữu `Executor`, làm gì khi một subscriber lỗi?
7. **Quan sát:** throughput, lag, allocation, thời gian callback, phần trăm drop, thời gian block của producer, `onError`/`cancel`.

Có thể dùng các phương thức ước lượng lag của `SubmissionPublisher` để quan sát và đo bổ sung ở application level, nhưng không dùng chúng làm cơ chế đồng bộ. Với pipeline dài, phải đo từng stage để tìm nơi dữ liệu tích tụ; chỉ nâng buffer ở stage nghẽn có thể chuyển áp lực sang stage tiếp theo.

### Virtual threads có thay thế backpressure không?

Không. Virtual threads giúp triển khai tác vụ blocking với nhiều luồng sống đồng thời ở chi phí thread thấp hơn platform threads, nhưng **không làm tài nguyên downstream vô hạn**. Một triệu tác vụ chờ DB, API hoặc queue vẫn chiếm bộ nhớ và có thể đẩy quá tải vào dịch vụ phía sau. Flow kiểm soát tốc độ phát thông qua demand; khi dùng virtual threads vẫn cần giới hạn kết nối, buffer và những tài nguyên hữu hạn khác.

## 11. Lỗi phổ biến và cách sửa

**Lỗi: gọi `subscribe` nhưng quên `request`.** Subscriber thường sẽ không nhận `onNext`. Sửa bằng cách phát yêu cầu hợp lý trong `onSubscribe` hoặc khi có khả năng tiếp tục nhận.

**Lỗi: coi `request(n)` là đặt lại số lượng.** Request là cộng demand còn thiếu, không xóa demand cũ. Theo dõi tổng yêu cầu, số item đã giao và demand chưa sử dụng.

**Lỗi: gọi `request(0)` để tạm dừng.** Không hợp lệ; hợp đồng yêu cầu `onError(IllegalArgumentException)`. Muốn tạm dừng, đơn giản không yêu cầu thêm sau khi tiêu thụ hết demand hiện tại.

**Lỗi: gọi `request(Long.MAX_VALUE)` rồi tưởng đã có backpressure hữu ích.** Đây gần như vô hạn; nếu consumer chậm, phải dựa vào buffering/overflow của triển khai thay vì demand giới hạn.

**Lỗi: dùng `submit` trong luồng nhạy độ trễ mà quên khả năng block.** Cân nhắc tác vụ phát riêng hoặc `offer` với timeout/drop policy chỉ khi phù hợp yêu cầu dữ liệu.

**Lỗi: nghĩ `close()` hoàn tất tức thì mọi callback.** `close` khởi phát kết thúc; trong xử lý bất đồng bộ, main cần cơ chế chờ terminal signal như `CountDownLatch` hoặc tương đương nếu kết quả còn quan trọng.

**Lỗi: biến một Processor thành queue vô hạn.** Nếu stage trung gian nhận upstream quá nhanh và đẩy xuống queue không giới hạn, backpressure thực chất bị phá vỡ ở stage đó.

**Lỗi: không hủy/đóng tài nguyên.** Chỉ giữ `Subscription` mà không gọi `cancel` khi tác vụ bị bỏ có thể khiến upstream tiếp tục tạo item. Khi producer kết thúc, cần `close` hoặc `closeExceptionally` phù hợp; quản lý vòng đời executor được truyền vào.

## 12. Câu hỏi tự kiểm tra

**Hỏi:** Bốn thành phần của Flow là gì?  
**Đáp:** `Publisher`, `Subscriber`, `Subscription` và `Processor`.

**Hỏi:** Subscriber gọi `request(5)`, sau đó `request(3)` và đã nhận hai item. Demand còn lại là bao nhiêu?  
**Đáp:** Sáu, nếu chưa có thay đổi nào khác: 5 + 3 − 2 = 6.

**Hỏi:** Có thể dùng `request(0)` để dừng tạm thời không?  
**Đáp:** Không; giá trị không dương dẫn tới `onError` với `IllegalArgumentException`. Để dừng cấp item mới, ngừng gọi `request` sau khi demand cũ đã được tiêu thụ.

**Hỏi:** Vì sao `submit` vẫn có thể block dù Flow là API bất đồng bộ?  
**Đáp:** Delivery tới subscriber là bất đồng bộ, nhưng `submit` có thể phải chờ tài nguyên khi buffer của subscriber đầy.

**Hỏi:** Hai subscriber nhận cùng item từ `SubmissionPublisher` có bắt buộc xử lý cùng lúc?  
**Đáp:** Không. Mỗi subscription có buffer/demand riêng và thời gian xử lý độc lập; thứ tự trong mỗi subscription được giữ theo hợp đồng nếu không drop hoặc lỗi.

**Hỏi:** `Flow.Processor` tự có toán tử map/filter và tự bảo đảm propagating demand chưa?  
**Đáp:** Chưa. Đây chỉ là interface; implementation quyết định xử lý và truyền backpressure.

**Hỏi:** Vì sao `CountDownLatch` hữu ích trong chương trình thử `SubmissionPublisher`?  
**Đáp:** Vì callback có thể đến sau khi `submit` trả về; latch cho main chờ tín hiệu hoàn tất hoặc lỗi với timeout rõ ràng.

**Ghi nhớ:** `Flow` cung cấp hợp đồng **Publisher → Subscription → Subscriber** với backpressure bằng `request(n)`; `SubmissionPublisher` là một implementation hữu ích để bắt đầu. Cần hiểu từng tín hiệu, demand, buffer, overflow, cancellation và lifecycle mới xây được pipeline không tích tụ dữ liệu ngoài kiểm soát.

## Tài liệu chính thức

- [Oracle Java 21 API — Flow](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html)
- [Oracle Java 21 API — Flow.Publisher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Publisher.html)
- [Oracle Java 21 API — Flow.Subscriber](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html)
- [Oracle Java 21 API — Flow.Subscription](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html)
- [Oracle Java 21 API — SubmissionPublisher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html)
