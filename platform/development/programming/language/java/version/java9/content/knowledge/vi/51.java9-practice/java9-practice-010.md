# Xây luồng phát dữ liệu có điều tiết cùng hoàn tất bất đồng bộ (Java 9+)

## 1. Bài toán thực tế và mục tiêu

Một dịch vụ nhận nhiều bản ghi từ bộ tạo sự kiện, đọc tuần tự từ tệp hoặc API rồi xử lý chúng bất đồng bộ. Nếu phía phát nhanh hơn phía xử lý, các hàng đợi có thể tăng vô hạn và gây áp lực bộ nhớ. Nếu phía nhận buộc phía phát dừng sau từng bước theo cách đồng bộ, hệ thống có thể lãng phí tài nguyên.

Từ **Java 9**, JDK cung cấp API `java.util.concurrent.Flow`, tuân theo mô hình Reactive Streams, để phía nhận thông báo **khả năng nhận thêm dữ liệu (demand)**. `SubmissionPublisher` là một publisher mẫu có bộ đệm và executor; `CompletableFuture` dùng để biểu diễn **kết quả cuối cùng hoặc lỗi của cả quá trình bất đồng bộ**.

Một thiết kế hữu ích phải giải được đồng thời:

- Phát nhiều phần tử và giữ đúng thứ tự trên từng subscription.
- Không cho downstream nhận thêm phần tử khi chưa có năng lực xử lý.
- Xử lý mỗi phần tử trên executor, không chặn callback phát dữ liệu.
- Không báo hoàn tất cho caller khi worker cuối cùng vẫn còn chạy.
- Truyền lỗi và hủy theo hợp đồng rõ ràng, không đợi mãi một sự kiện sẽ không đến.
- Giải phóng publisher, subscription và executor theo vòng đời ứng dụng.

Sơ đồ kiến trúc:

```text
                             request(1)
                                 ▲
                                 │
Dữ liệu → SubmissionPublisher ───┼──► Flow.Subscriber
             submit()             │       │
             (có bộ đệm)          │       │ onNext(item)
                                 │       ▼
                                 └── CompletableFuture.runAsync(...)
                                           │
                                      Worker Executor
                                           │
                                    xử lý hoàn tất
                                           │
                                     xin item tiếp
                                           │
Publisher.close() → Subscriber.onComplete() │
                        │                   │
                        └── đợi worker cuối ┘
                                    ▼
                         CompletableFuture<List<T>>
                                    │
                            thenApply / handle
                                    ▼
                           Kết quả hoặc lỗi
```

**Phân biệt cốt lõi:** `Flow` xử lý **nhiều tín hiệu và backpressure**; `CompletableFuture` mô tả **một kết quả cuối của chuỗi xử lý**. Hai cơ chế không tự kết nối: chính subscriber phải hoàn tất future vào đúng thời điểm.

## 2. Bốn kiểu trong Flow và hợp đồng callback

Các thành phần chuẩn của `java.util.concurrent.Flow`:

| Thành phần | Trách nhiệm |
|---|---|
| `Flow.Publisher<T>` | Cho phép đăng ký bằng `subscribe(Subscriber)` và phát phần tử/sự kiện kết thúc |
| `Flow.Subscriber<T>` | Nhận `onSubscribe`, `onNext`, `onError`, `onComplete` |
| `Flow.Subscription` | Liên kết giữa publisher và một subscriber; có `request(long n)` và `cancel()` |
| `Flow.Processor<T,R>` | Đồng thời là subscriber và publisher, phù hợp để tạo các bước biến đổi |

Vòng đời điển hình trên một subscription:

```text
publisher.subscribe(subscriber)
             |
             v
subscriber.onSubscribe(subscription)
             |
       subscription.request(1)
             |
             v
         onNext(item1)
             |
       xử lý xong item1
             |
       subscription.request(1)
             |
             v
         onNext(item2)
             |
             ...
             |
       +-----+------+
       |            |
  onComplete()   onError(error)
    bình thường     lỗi
```

Từng subscriber được gọi **tuần tự theo thứ tự callback trên cùng subscription**, nhưng không bảo đảm tất cả callback luôn chạy trên một thread. `onSubscribe` đến trước các tín hiệu khác; `onError` và `onComplete` là **hai đường kết thúc thay thế nhau**, không phải hai bước liên tiếp.

### Demand: request(n) thực sự có nghĩa gì?

`subscription.request(n)` cộng thêm quyền nhận **tối đa n phần tử `onNext`**, không phải ra lệnh publisher phải tạo ngay n phần tử:

- `request(1)`: cho phép thêm một phần tử.
- `request(5)`: cho phép thêm tối đa năm phần tử trong phạm vi subscription.
- `request(Long.MAX_VALUE)`: nhu cầu rất lớn, trên nhiều triển khai tương đương không giới hạn; không nên mặc định nếu năng lực xử lý hữu hạn.
- `request(0)` hay số âm: **sai hợp đồng** và subscriber sẽ nhận `onError(IllegalArgumentException)`.

`cancel()` chỉ yêu cầu ngừng phát đến subscription theo kiểu *best effort*. Có thể vẫn còn tác vụ đã phát đang xử lý; một subscription đã hủy **không được bảo đảm** sẽ nhận `onComplete` hoặc `onError`. Vì vậy, nếu ứng dụng tự hủy, hãy chủ động quyết định trạng thái của future tổng, không cứ chờ `onComplete`.

**Backpressure không tự giới hạn mọi hàng đợi.** Nó điều tiết số phần tử được chuyển vào `onNext`, trong khi publisher có thể còn đệm phần tử và chính ứng dụng có thể lập lịch nhiều tác vụ worker. Nếu `onNext` gọi `request(1)` ngay sau khi `runAsync` vừa được lập lịch nhưng chưa xong, downstream vẫn có thể tạo hàng đợi công việc không kiểm soát được. Thiết kế trong bài yêu cầu tiếp **sau khi việc xử lý thật sự hoàn tất**.

## 3. SubmissionPublisher: bộ phát có executor và bộ đệm

`SubmissionPublisher<T>` là triển khai `Flow.Publisher<T>` có từ Java 9, thuận tiện cho bài toán minh họa cũng như pipeline đơn giản.

Tạo publisher với executor rõ ràng:

```java
ExecutorService signals = Executors.newSingleThreadExecutor();
SubmissionPublisher<Integer> publisher =
        new SubmissionPublisher<>(signals, 2);
```

Đây là **mảnh mã**, cần import các lớp trong `java.util.concurrent` và đóng/thu hồi cả publisher lẫn executor. Đối số `2` yêu cầu dung lượng bộ đệm 2 cho mỗi subscription; khả năng đệm thực tế của triển khai có thể được làm tròn trong một số trường hợp. Có thể hỏi `getMaxBufferCapacity()` để biết giá trị mà publisher báo.

### submit và offer không giống nhau

| Phương thức | Khi không còn chỗ đệm | Ý nghĩa giá trị trả về |
|---|---|---|
| `submit(item)` | Có thể **chặn caller** để chờ tài nguyên; API mô tả chờ không ngắt được theo cơ chế này | Ước lượng lag tối đa giữa subscriber, **không phải ack xử lý xong** |
| `offer(item, onDrop)` | Không chờ để thêm chỗ; có thể gọi callback xử lý drop và thử lại một lần | Giá trị âm cho biết có lượt phát không thành công đến subscriber |
| `offer(item, timeout, unit, onDrop)` | Có thể chờ tối đa khoảng đã chỉ định rồi xử lý tình huống không phát được | Tình trạng phát, **không phải kết quả nghiệp vụ** |

`submit` và `offer` yêu cầu phần tử không phải `null`. Khi đã `close()` thì không thể `submit` tiếp. Khi bộ đệm đầy, publisher chịu áp lực từ **subscriber chậm**; có thể phát chậm hơn dù thread phát không trực tiếp chạy logic xử lý.

Ví dụ:

```java
int lagEstimate = publisher.submit(42);
```

Đây là **mảnh mã**. Không viết assert `lagEstimate == 0` hay `== 1` để suy ra worker đã xử lý phần tử; giá trị phụ thuộc lịch chạy bất đồng bộ và chỉ dùng để giám sát. Nếu không có subscriber tại thời điểm phát, publisher không giữ phần tử để tự động giao cho một subscriber mới trong tương lai.

Với `offer`, nếu dữ liệu có tính bắt buộc thì **không được bỏ qua** chính sách drop. Một callback `onDrop` trả `true` chỉ yêu cầu thử lại một lần, không bảo đảm sẽ phát thành công. Để bảo đảm phục hồi/sao chép dữ liệu sau sự cố, ứng dụng còn cần cơ chế lưu bền và retry ở tầng phù hợp.

### close và closeExceptionally

- `publisher.close()`: không chấp nhận item mới, phát thông báo `onComplete` bất đồng bộ cho các subscriber hiện tại.
- `publisher.closeExceptionally(error)`: kết thúc với lỗi, phát `onError(error)`.
- **`close()` trả về không có nghĩa tất cả `onComplete` đã chạy xong**. Muốn đợi kết quả downstream, hãy dùng một future hoàn tất do subscriber sở hữu.

## 4. CompletableFuture: cầu nối từ nhiều item sang một kết quả

`CompletableFuture<T>` kế thừa ý tưởng `Future` và triển khai `CompletionStage`. Nó có thể được hoàn tất bằng một giá trị hoặc một lỗi **một lần duy nhất**. Trong bài này, subscriber có:

```java
CompletableFuture<List<Integer>> finished =
        new CompletableFuture<>();
```

Đây là mảnh mã; khi thành công, future trả **danh sách kết quả của mọi phần tử**. Khi có lỗi không thể tiếp tục, future kết thúc exceptional.

| API | Vai trò |
|---|---|
| `complete(value)` | Hoàn tất thành công; chỉ thành công nếu future chưa hoàn tất |
| `completeExceptionally(error)` | Hoàn tất bằng lỗi |
| `thenApply(fn)` | Biến đổi giá trị sau khi stage trước thành công |
| `thenApplyAsync(fn, executor)` | Đưa hành động phụ thuộc lên executor chỉ định |
| `thenCompose(fn)` | Ghép với một stage khác, không tạo future lồng |
| `whenComplete((value,error) -> ...)` | Quan sát kết quả và lỗi, không chủ đích phục hồi lỗi |
| `handle((value,error) -> result)` | Chuyển thành công/lỗi thành kết quả stage mới |
| `exceptionally(error -> fallback)` | Phục hồi stage lỗi bằng fallback |
| `orTimeout(timeout, unit)` | Hoàn tất future exceptional khi hết thời hạn mà chưa xong |
| `CompletableFuture.allOf(f1, f2, ...)` | Đợi tất cả future con; lỗi của future con phản ánh vào kết quả tổng |
| `join()` và `get()` | Chờ đồng bộ ở caller; khác cách thể hiện ngoại lệ |

Với stage **không mang hậu tố Async**, callback phụ thuộc có thể chạy ngay ở thread hoàn tất stage hoặc thread gọi cơ chế hoàn tất. Không đặt tác vụ chặn dài vào callback đó chỉ vì nghĩ nó chạy tách luồng. Nếu cần chắc chắn nơi thực thi, dùng overload `...Async(..., executor)`.

Một future kết thúc chỉ khi **điều kiện do nghiệp vụ xác định** đã đáp ứng; nó không tự biết toàn bộ Flow đã xử lý xong. Trạng thái lỗi do `onError` hoặc worker phải được chuyển sang `completeExceptionally`. Khi future timeout, underlying worker hoặc publisher **không tự động bị hủy**.

## 5. Cách kết hợp an toàn: yêu cầu lại sau khi async task xong

Luồng thực thi trong ví dụ:

1. `onSubscribe` lưu `Flow.Subscription` và gọi `request(1)`.
2. `onNext(item)` khởi chạy `CompletableFuture.runAsync(...)` để chuyển đổi item bằng executor worker.
3. Callback `whenComplete` của stage xử lý chỉ gọi `request(1)` khi tác vụ hoàn tất **thành công**.
4. Nếu worker lỗi, callback hủy subscription và `finished.completeExceptionally(error)`.
5. Khi nhận `onComplete`, subscriber **đợi stage xử lý cuối cùng** (`inFlight`) trước khi `finished.complete(result)`.
6. Khi nhận `onError`, subscriber `finished.completeExceptionally(error)`.

Điểm thứ 5 đặc biệt quan trọng. `onNext` có thể trả về sau khi **lập lịch công việc** nhưng trước khi xử lý item xong; publisher có quyền gửi tín hiệu `onComplete` khi phần tử cuối đã được trao ở mức Flow. Nếu đánh dấu future thành công ngay trong `onComplete`, caller có thể nhận danh sách thiếu phần tử.

```text
Executor phát tín hiệu              Executor xử lý           Future
         |                                |                    |
         | onNext(5)                      |                    |
         |  -> runAsync(item=5) --------->| đang xử lý         |
         | return                         |                    |
         | onComplete()                   |                    |
         |  -> inFlight.whenComplete(...) |                    |
         |                                | hoàn thành item=5  |
         |                                +---- callback ------> complete(list)
         |                                                    |
         |                                             thenApply(sum)
```

Ở thiết kế **một item đang xử lý**, chỉ cần theo dõi một stage `inFlight`, vì subscriber chỉ yêu cầu thêm khi tác vụ trước thành công. Nếu tăng demand và xử lý **nhiều item song song**, chỉ chờ stage cuối **không đủ**: cần giữ tất cả stage chưa xong hoặc bộ đếm pending đồng bộ, đồng thời giải quyết thứ tự dữ liệu đầu ra.

## 6. Ví dụ Java 17+ hoàn chỉnh: có backpressure và kết quả bất đồng bộ

Chương trình sau:

- Phát lần lượt các số `1, 2, 3, 4, 5`.
- Mỗi `onNext` lập lịch nhân đôi số vào một executor worker.
- Mỗi lần chỉ yêu cầu thêm `1` phần tử sau khi xử lý xong item hiện tại.
- Sau khi publisher đóng bình thường, future tổng chờ công việc cuối cùng rồi trả danh sách và tổng.
- Không dùng `Thread.sleep`; stdout không phụ thuộc tốc độ thread.

**Tệp `ControlledFlowDemo.java`:**

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class ControlledFlowDemo {
    private static final class BatchSubscriber
            implements Flow.Subscriber<Integer> {
        private final Executor worker;
        private final List<Integer> values = new ArrayList<>();

        final CompletableFuture<List<Integer>> finished =
                new CompletableFuture<>();

        private Flow.Subscription subscription;
        private CompletableFuture<Void> inFlight =
                CompletableFuture.completedFuture(null);

        BatchSubscriber(Executor worker) {
            this.worker = worker;
        }

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            subscription.request(1);
        }

        @Override
        public void onNext(Integer item) {
            inFlight = CompletableFuture.runAsync(
                    () -> values.add(item * 2), worker
            ).whenComplete((ignored, error) -> {
                if (error != null) {
                    subscription.cancel();
                    finished.completeExceptionally(error);
                } else {
                    subscription.request(1);
                }
            });
        }

        @Override
        public void onError(Throwable error) {
            finished.completeExceptionally(error);
        }

        @Override
        public void onComplete() {
            inFlight.whenComplete((ignored, error) -> {
                if (error != null) {
                    finished.completeExceptionally(error);
                } else {
                    finished.complete(List.copyOf(values));
                }
            });
        }
    }

    public static void main(String[] args) {
        ExecutorService signals = Executors.newSingleThreadExecutor();
        ExecutorService worker = Executors.newSingleThreadExecutor();

        try {
            BatchSubscriber subscriber = new BatchSubscriber(worker);
            try (SubmissionPublisher<Integer> publisher =
                    new SubmissionPublisher<>(signals, 2)) {

                publisher.subscribe(subscriber);
                for (int i = 1; i <= 5; i++) {
                    publisher.submit(i);
                }
            }

            List<Integer> result =
                    subscriber.finished.orTimeout(5, TimeUnit.SECONDS).join();

            int sum = result.stream().mapToInt(Integer::intValue).sum();
            System.out.println("received=" + result);
            System.out.println("sum=" + sum);
        } finally {
            signals.shutdown();
            worker.shutdown();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 ControlledFlowDemo.java
java ControlledFlowDemo
```

**Stdout chính xác:**

```text
received=[2, 4, 6, 8, 10]
sum=30
```

Tệp trên đã được biên dịch với `javac --release 17` trên JDK hiện đại và chạy **bốn lần liên tiếp**, đều cho cùng hai dòng đầu ra. Nó chỉ phụ thuộc JDK, không dùng mạng, database hoặc thư viện ngoài.

### Đọc các đoạn mã cần chú ý

**Tạo executor:** `signals` được dùng để chuyển callback Flow, `worker` thực thi biến đổi. Tách hai executor tránh phải chạy công việc nặng trên thread callback và tránh một dạng deadlock do tự chờ công việc chưa được xử lý trên cùng executor.

**Điều tiết đúng chỗ:** `onNext` không lập tức gọi `request(1)`. Thay vào đó, callback `whenComplete` của task xử lý mới xin tiếp. Với một worker và cách cấp demand này, tác vụ xử lý phần tử không chồng lên nhau.

**Xử lý lỗi:** Khi `runAsync` lỗi, `whenComplete` nhận `error`, hủy subscription và hoàn tất future tổng ở trạng thái exceptional. Điều này không phụ thuộc việc publisher còn hay hết item.

**Đợi kết thúc đúng:** `publisher.close()` tự được gọi bởi `try-with-resources` nhưng không đồng nghĩa downstream xử lý xong. Chính `finished.orTimeout(...).join()` ở thread main nhận tín hiệu tổng kết. `onComplete` không bỏ qua `inFlight` cuối cùng.

**Snapshot:** `List.copyOf(values)` trả danh sách bất biến về mặt cấu trúc để caller không vô tình sửa bộ nhớ nội bộ subscriber. Ví dụ này chỉ có một worker thread ghi danh sách, và `finished` công bố kết quả sau stage cuối, nên không cần thêm khóa đồng bộ cho danh sách.

**Thời hạn:** 5 giây chỉ là giới hạn để demo không đợi vô hạn khi có vấn đề; đó **không phải cam kết về thời gian xử lý**. `orTimeout` thay đổi trạng thái future khi hết hạn, không tự đóng publisher/executor. Một ứng dụng cần hủy thực sự phải bổ sung chính sách cancellation.

**Lifecycle:** `signals.shutdown()` và `worker.shutdown()` giúp executor ngừng nhận task mới sau khi xử lý công việc đã nhận. Với service chạy lâu dài, hãy còn quản lý shutdown, `awaitTermination` và dọn dẹp khi lỗi/hủy.

## 7. Phân tích backpressure và sự khác biệt giữa demand, buffer, lag

Giả sử publisher có bộ đệm hữu hạn và worker mất nhiều thời gian cho từng item:

```text
Tình huống mô phỏng                 Trạng thái mong đợi
--------------------------------------------------------------------
Subscriber request(1)              Cho phép thêm tối đa 1 onNext
Producer submit nhiều item         Một số item có thể xếp trong buffer
Buffer hết dung lượng              submit có thể chờ
Worker xử lý xong item              Callback request(1)
Publisher đưa item tiếp             Buffer được giải phóng dần
Publisher close                      Lên lịch terminal onComplete
Subscriber future hoàn tất         Sau mọi worker cần thiết đã xong
```

Đây là **sơ đồ hành vi**, không phải trace bắt buộc với số mili giây hay vị trí chính xác từng item trong bộ đệm. Lịch thread, thời gian xử lý và chi tiết triển khai ảnh hưởng đến thời điểm `submit` chờ.

Ba đại lượng **khác nhau**:

- **Demand:** quyền gửi những `onNext` tiếp theo do subscriber cấp.
- **Buffer:** những item publisher đã chấp nhận nhưng chưa được chuyển tới subscriber.
- **Lag estimate:** ước lượng mà publisher có thể báo hoặc trả về sau `submit`, **không phải số item đã xử lý**.

Các phương thức `estimateMinimumDemand()` và `estimateMaximumLag()` được thiết kế để **giám sát**, không phải làm công cụ đồng bộ hóa. Giá trị ước lượng có thể lỗi thời ngay sau khi đọc. Nguồn kiểm soát luồng chính vẫn là `Subscription.request(n)` và chính sách phát của publisher.

### Tại sao không cứ request(Long.MAX_VALUE)?

Nếu downstream xử lý chậm nhưng request gần vô hạn, publisher có thể đẩy nhiều item qua `onNext` rất nhanh. Nếu mỗi callback tiếp tục giao task cho một executor có hàng chờ không giới hạn, số tác vụ chờ sẽ tăng theo nguồn phát, làm mất tác dụng của backpressure tổng thể. Chỉ sử dụng demand không giới hạn khi có giới hạn lưu lượng hoặc cơ chế kiểm soát tài nguyên khác rõ ràng.

Nếu muốn song song tối đa `k` tác vụ, cần giữ bộ đếm pending, cho phép `k` item đầu tiên, và bổ sung một demand **mỗi khi một task xong**, đồng thời chờ mọi tác vụ đã nhận trước khi đánh dấu future tổng thành công. Với xử lý song song, phải thêm cơ chế bảo vệ danh sách và thứ tự đầu ra; không thể chỉ sửa `request(1)` thành `request(k)` rồi giữ nguyên toàn bộ subscriber của mục 6.

## 8. Hoàn tất bình thường, lỗi và hủy

| Tình huống | Tín hiệu Flow | Tín hiệu CompletableFuture cần thiết |
|---|---|---|
| Nguồn phát hết item, các worker đã hoàn tất | `onComplete` | `finished.complete(result)` sau khi đợi task cuối |
| Publisher lỗi | `onError(error)` | `finished.completeExceptionally(error)` |
| Worker xử lý một item lỗi | Subscriber có thể `cancel()` | `finished.completeExceptionally(error)` |
| Người gọi chủ động hủy | `cancel()`, không bảo đảm terminal callback | Ứng dụng chủ động cancel hoặc hoàn tất lỗi future |
| Hết timeout | Không tự có Flow terminal callback | Future có thể exceptional với `TimeoutException`; tài nguyên bên dưới cần xử lý riêng |

### Nguồn báo lỗi

Phía phát có thể gọi:

```java
publisher.closeExceptionally(
        new IllegalStateException("Nguồn dữ liệu bị lỗi"));
```

Đây là **mảnh mã**, cần `publisher` còn tồn tại. Subscriber nhận `onError(error)` và nối lỗi sang `finished.completeExceptionally(error)`. Không giả định mọi item đã xếp trong buffer chắc chắn sẽ được xử lý trước khi hoàn tất lỗi.

### Worker báo lỗi

Trong ví dụ mục 6, một tác vụ `runAsync` thất bại khiến stage exceptional. Nhánh `whenComplete` thấy `error`, gọi `cancel()` và `completeExceptionally(error)`, thay vì request item tiếp theo.

Không nên ném ngoại lệ từ `onNext` để thay cho một chiến lược lỗi có kiểm soát: hợp đồng Flow của subscriber không bảo đảm một callback ném lỗi sẽ tự tạo ra phản hồi mà ứng dụng mong muốn. Khi một API tích hợp xử lý tác vụ bất đồng bộ, phải nối lỗi vào terminal future và quản lý hủy rõ ràng.

### Chỉ có một lần kết thúc hiệu lực

`CompletableFuture.complete(...)` và `completeExceptionally(...)` trả `boolean`, thể hiện lời gọi đó có thật sự thay đổi trạng thái future chưa. Nếu timeout, hủy và lỗi xảy ra gần nhau, **chỉ một lần hoàn tất thắng**; những lời gọi sau không thay thế được trạng thái đã có. Đừng giữ một danh sách kết quả đã công bố rồi tiếp tục đột biến nó.

### Cancellation không bảo đảm onComplete

Sau `subscription.cancel()`, Flow cho phép ngừng mà **không** cần gửi `onComplete` hay `onError`. Nếu một API của ứng dụng tự hủy, có thể gọi `finished.cancel(false)` hoặc `finished.completeExceptionally(new CancellationException(...))` theo thiết kế riêng. Chỉ gọi cancel trên subscription rồi `finished.join()` có nguy cơ chờ mãi.

## 9. Ghép tiếp công việc bằng CompletionStage

Khi đã có future terminal, xử lý kết quả bằng các stage thay vì tạo thêm thread chỉ để đợi.

Tính tổng sau khi đã nhận đủ:

```java
// MẢNH MÃ: subscriber thuộc chương trình mục 6.
CompletableFuture<Integer> total = subscriber.finished
        .thenApply(items -> items.stream()
                .mapToInt(Integer::intValue)
                .sum());
```

Đây là mảnh mã, không chạy riêng vì cần biến `subscriber`. Nếu `finished` hoàn tất lỗi, `thenApply` không thực thi hàm chuyển đổi; stage `total` cũng mang trạng thái lỗi.

Phân biệt ba API quan trọng:

```java
// MẢNH MÃ: total là CompletableFuture<Integer>.
// Chỉ quan sát, không chủ đích chuyển lỗi thành kết quả.
CompletableFuture<Integer> observed = total.whenComplete(
        (value, error) -> {
            if (error != null) {
                System.err.println("Tính tổng thất bại");
            }
        });

// Tạo một giá trị dự phòng khi nguồn lỗi.
CompletableFuture<Integer> recovered =
        total.exceptionally(error -> 0);

// Gộp cả hai trạng thái thành chuỗi báo cáo.
CompletableFuture<String> summary = total.handle(
        (value, error) -> error == null
                ? "Tổng = " + value
                : "Không thể tính tổng");
```

**Không vô tình nuốt lỗi:** `exceptionally` và `handle` có thể tạo stage hoàn tất **thành công** từ một stage bị lỗi. Với nghiệp vụ cần bảo toàn tính đúng đắn, phải xác định liệu fallback có hợp lệ hay không. `whenComplete` thích hợp cho logging/quan sát, nhưng callback này cũng nên tránh ném ngoại lệ vì có thể làm stage phụ thuộc đổi sang trạng thái lỗi.

Nếu một API xử lý tiếp trả `CompletionStage<U>`, dùng `thenCompose(...)` để ghép, thay vì `thenApply(...)` tạo ra stage lồng stage. Nếu có nhiều tác vụ độc lập, `CompletableFuture.allOf(a, b, c)` có thể đợi chúng, nhưng **không trực tiếp trả danh sách giá trị**; phải đọc kết quả từng future sau đó. Nếu bất cứ future thành phần nào lỗi, future tổng cũng hoàn tất lỗi.

## 10. Tránh deadlock, quá tải và race condition

### Không chặn callback trên executor tạo ra kết quả

Mẫu sai:

```java
// PHẢN VÍ DỤ, không nên sao chép vào ứng dụng.
void onNext(Integer item) {
    aFutureThatNeedsThisExecutor.join();
}
```

Đây chỉ là **giả mã Java**. Nếu executor có một thread đang chạy `onNext` mà `aFutureThatNeedsThisExecutor` chỉ hoàn tất khi một task khác trong **chính executor đó** được chạy, `join()` sẽ tạo deadlock.

Chương trình mục 6 không chặn trong `onNext`. Thread main mới đợi future terminal, trong khi hai executor khác vẫn tiến hành phát callback và xử lý.

### Thread.sleep không phải tín hiệu hoàn tất

Dùng `Thread.sleep(1000)` để “chắc subscriber đã xong” rất dễ tạo bài kiểm thử flaky: máy nhanh thì tình cờ qua, máy chậm thì bỏ sót. Future terminal hoặc latch/test synchronization có điều kiện mới là cách kiểm chứng trạng thái. Khi mô phỏng subscriber chậm, có thể thêm delay có chủ đích để quan sát buffer, nhưng **không dùng delay để xác định đúng/sai của kết quả cuối**.

### An toàn bộ nhớ và thứ tự khi xử lý song song

Trong ví dụ, chỉ một worker thread sửa `values` và mỗi lần chỉ có một task đang chạy. `onComplete` chờ `inFlight`, sau đó `List.copyOf(values)` tạo bản snapshot. Khi chuyển thành nhiều worker:

1. Các task có thể hoàn tất **khác thứ tự** nhận item.
2. `ArrayList` chia sẻ không thread-safe nếu nhiều task ghi cùng lúc.
3. `onComplete` có thể tới trước một hoặc nhiều task async hoàn tất.
4. Lỗi trong một task phải quyết định có hủy tất cả task khác hay tổng hợp lỗi.

Cần chọn rõ một trong hai mô hình: xử lý song song nhưng giữ thứ tự (lưu vị trí/index và hợp nhất sau) hoặc xử lý không yêu cầu thứ tự. Dùng hàng đợi/bộ sưu tập thích hợp và chờ **tất cả** task, không chỉ stage cuối.

### Quản lý executor và tài nguyên

- Executor phục vụ callback nên có khả năng tiến triển, không bị chặn bởi công việc cần chính nó hoàn tất.
- Worker executor nên có kích thước hợp lý với CPU và I/O; không đưa tất cả việc nặng vào một shared common pool không được giám sát.
- Đóng publisher, dừng nguồn phát và hủy subscription khi không còn cần dữ liệu.
- Khi timeout/hủy, thiết kế logic đóng kết nối, giải phóng buffer và dừng tác vụ đang chạy; `CompletableFuture.cancel(...)` không tự bảo đảm ngắt tác vụ được thực thi ở một executor.
- Với ứng dụng server dài hạn, có giai đoạn graceful shutdown và theo dõi thread còn hoạt động, không chỉ dựa vào quy trình thoát của một chương trình demo.

## 11. Khi nào nên dùng kiến trúc này?

**Phù hợp** khi có nguồn nhiều phần tử, downstream cần kiểm soát tốc độ và caller cần một kết quả cuối: đọc log/bản ghi, ETL nhỏ, xử lý sự kiện trong tiến trình, nhập lô hoặc tự tạo publisher cho một API cũ.

**Không tự động đáp ứng** các yêu cầu của hệ thống phân tán: `SubmissionPublisher` không phải message broker lưu bền, không cung cấp replay sau restart, không tự có exactly-once processing, không lưu offset và không bảo đảm dữ liệu sống sót nếu tiến trình dừng.

**Cân nhắc giải pháp đơn giản hơn** khi chỉ có một tác vụ: `CompletableFuture.supplyAsync(...)` là đủ, không cần cố tạo `Flow.Publisher`. Với pipeline Reactive Streams phức tạp (merge, window, retry, nhiều subscriber có tốc độ khác nhau), một framework reactive phù hợp có thể cung cấp toán tử phong phú, nhưng phải hiểu rõ chính sách demand và lỗi của nó.

Về tính hiện hành: `Flow` và `SubmissionPublisher` được thêm từ Java 9 và vẫn hiện diện trong API Java SE mới; `CompletableFuture` là API vẫn được phát triển. `orTimeout` và `completeOnTimeout` có từ Java 9, nên có thể dùng cùng Java 17+. Bài này dùng API chuẩn, không phụ thuộc thư viện hoặc phương thức JDK đã bị loại bỏ.

## 12. Lỗi thường gặp và hướng sửa

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Không gọi `request(n)` | Subscriber không nhận `onNext` vì chưa có demand | Xin số item phù hợp trong `onSubscribe` |
| Gọi `request(0)` để “tạm dừng” | Sai hợp đồng, gây `onError(IllegalArgumentException)` | Không xin thêm item; nếu không cần nữa thì hủy đúng cách |
| Gọi `request(1)` ngay sau `runAsync` | Tăng số task in-flight ngoài khả năng xử lý | Request sau khi task xong |
| Hoàn tất future ngay trong `onComplete` | Worker cuối có thể chưa xong | Chờ `inFlight` hoặc mọi stage đang hoạt động |
| Coi `publisher.close()` là subscriber đã xong | Close chỉ gửi tín hiệu bất đồng bộ | Chờ terminal future riêng |
| Coi số `submit` trả về là số item đã xử lý | Ước lượng lag không phải ack nghiệp vụ | Theo dõi kết quả riêng |
| Dùng `offer` rồi bỏ qua drop | Mất dữ liệu khi buffer đầy | Đặt chính sách drop/retry/đảm bảo lưu bền |
| Chặn `join()` trên callback executor một thread | Nguy cơ deadlock | Dùng stage async; đợi ở caller khác |
| Bỏ qua `onError` | Future có thể không bao giờ hoàn tất | Nối lỗi bằng `completeExceptionally` |
| Hủy subscription rồi chờ `onComplete` | Cancellation không bảo đảm terminal callback | Chủ động hoàn tất/hủy future |
| Timeout future nhưng không dừng công việc | Rò rỉ tài nguyên và xử lý thừa | Bổ sung cancellation/lifecycle |
| Tăng demand để chạy song song nhưng không đồng bộ danh sách | Race, sai thứ tự và kết quả | Quản lý in-flight, bộ nhớ thread-safe, đợi mọi task |
| `request(Long.MAX_VALUE)` trong mọi bài toán | Backpressure mất ý nghĩa với consumer giới hạn | Chọn demand hữu hạn |
| Không đóng publisher và executor | Thread giữ ứng dụng sống, tài nguyên không giải phóng | Đóng và shutdown theo vòng đời |

## 13. Bài tập mở rộng và câu hỏi tự kiểm tra

### Bài tập tự làm

1. Thay `item * 2` thành `item * item`, tính stdout mới và chạy lại. Vẫn phải bảo toàn quy tắc chỉ xin item sau khi worker xong.
2. Trong worker, nếu item âm thì ném `IllegalArgumentException`; xác minh terminal future chuyển trạng thái exceptional, không công bố danh sách thành công.
3. Thay dung lượng buffer và thêm một worker chậm có chủ đích để quan sát khả năng `submit` bị chặn; **không** dùng thời gian chờ đoán mò thay cho future xác nhận hoàn tất.
4. Thêm subscriber thứ hai, có demand thấp hơn. Tìm hiểu vì sao publisher có thể bị ảnh hưởng bởi subscriber chậm mặc dù các subscription có demand riêng.
5. Thiết kế biến thể xử lý tối đa 4 item đồng thời. Hãy giữ danh sách future in-flight, chỉ request thêm khi có task hoàn tất, và chỉ báo kết quả khi mọi task đã xử lý xong.

### Câu hỏi

1. **Flow khác CompletableFuture ở đâu?** Flow điều phối **nhiều item và demand**; CompletableFuture mang **một kết quả hoặc lỗi**.
2. **`request(1)` có đồng nghĩa “một worker task chạy” không?** Không tự động; cần đặt lần request tiếp theo sau khi task hiện tại hoàn tất.
3. **`submit` trả về số nào?** Ước lượng lag giữa subscriber, không phải số item đã xử lý.
4. **`close()` trả về có chắc `onComplete` đã chạy chưa?** Không.
5. **Vì sao trong `onComplete` phải đợi `inFlight`?** Vì `onNext` có thể trả về trước khi tác vụ async cuối hoàn tất.
6. **Nếu `onError` xảy ra thì tương lai terminal nên làm gì?** `completeExceptionally(error)`, không tạo kết quả giả là thành công.
7. **Sau `cancel()` có chắc nhận `onComplete` không?** Không.
8. **`orTimeout` có dừng được publisher/worker không?** Không tự động.
9. **Tại sao `join()` trong executor phục vụ kết quả dễ deadlock?** Vì nó có thể chặn chính thread cần chạy tác vụ làm future hoàn tất.
10. **Nếu cần 4 worker song song, có thể giữ nguyên cách đợi một `inFlight` không?** Không; phải đợi tất cả tác vụ còn hoạt động và bảo vệ dữ liệu dùng chung.
11. **Khi dùng `thenApply`, stage trước lỗi thì điều gì xảy ra?** Lambda không chạy; stage phụ thuộc mang lỗi.
12. **Tại sao không thay publisher bằng `CompletableFuture.supplyAsync` cho mọi trường hợp?** Future thể hiện một kết quả, không tự mô hình hóa chuỗi nhiều item với demand và terminal signals.

## Tài liệu API và tiêu chuẩn còn áp dụng

- [`Flow` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Flow.html)
- [`Flow.Publisher` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Flow.Publisher.html)
- [`Flow.Subscriber` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html)
- [`Flow.Subscription` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Flow.Subscription.html)
- [`SubmissionPublisher` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html)
- [`CompletableFuture` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [`CompletionStage` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [JEP 266 — More Concurrency Updates (Java 9)](https://openjdk.org/jeps/266)
- [Reactive Streams specification](https://www.reactive-streams.org/)
