# Điều tiết theo nhu cầu và kiểm soát áp lực ngược với `Flow`

Java 9 giới thiệu `java.util.concurrent.Flow`, bộ giao diện chuẩn để mô tả luồng dữ liệu bất đồng bộ theo mô hình Reactive Streams. Điểm cốt lõi là **subscriber chủ động báo lượng dữ liệu mình sẵn sàng nhận** thông qua `Subscription.request(n)`. Publisher phải tôn trọng lượng nhu cầu đó, nhờ vậy một consumer xử lý chậm có thể điều tiết tốc độ phát dữ liệu và hạn chế việc hàng đợi tăng vô hạn.

Cơ chế này được gọi là *backpressure* (áp lực ngược). Nó tạo một giao thức phối hợp giữa bên sản xuất và bên tiêu thụ: subscriber báo nhu cầu, publisher phát trong giới hạn nhu cầu, subscriber xử lý rồi yêu cầu thêm khi sẵn sàng.

## 1. Vì sao cần backpressure?

Giả sử một publisher đọc hàng triệu bản ghi từ nguồn dữ liệu và gửi chúng đến subscriber để ghi vào cơ sở dữ liệu. Nếu publisher phát nhanh hơn khả năng ghi của subscriber, dữ liệu chờ xử lý sẽ tích tụ. Một hàng đợi không giới hạn có thể tiêu thụ hết heap; hàng đợi có giới hạn nhưng không có chính sách đầy hàng đợi có thể làm mất dữ liệu hoặc khiến producer bị treo.

Backpressure cho phép consumer kiểm soát tốc độ phát. Thay vì publisher tự đẩy dữ liệu liên tục, subscriber chỉ yêu cầu số phần tử mà nó có thể xử lý:

```java
subscription.request(10);
```

Lời gọi trên báo rằng subscriber muốn nhận thêm tối đa 10 phần tử. Khi xử lý xong và có khả năng nhận tiếp, subscriber có thể gọi `request` lần nữa.

Backpressure không tự làm cho một tác vụ xử lý nhanh hơn. Nó điều phối tốc độ và lượng dữ liệu đang chờ, giúp hệ thống duy trì giới hạn tài nguyên khi producer và consumer có tốc độ khác nhau.

## 2. Bốn giao diện trong `java.util.concurrent.Flow`

`Flow` cung cấp bốn giao diện chính:

| Giao diện | Vai trò |
| --- | --- |
| `Flow.Publisher<T>` | Nguồn phát các phần tử kiểu `T` đến subscriber đã đăng ký. |
| `Flow.Subscriber<T>` | Consumer nhận tín hiệu đăng ký, dữ liệu, lỗi hoặc hoàn tất. |
| `Flow.Subscription` | Kênh điều khiển giữa publisher và subscriber: yêu cầu dữ liệu hoặc hủy đăng ký. |
| `Flow.Processor<T, R>` | Thành phần vừa là subscriber của `T`, vừa là publisher của `R`; thường dùng để biến đổi hoặc trung gian luồng dữ liệu. |

Quan hệ cơ bản:

```text
Publisher<T>
    | subscribe
    v
Subscriber<T>
    ^
    | onSubscribe(Subscription)
    |
Subscription
    | request(n) / cancel()
    v
Publisher<T>
```

Publisher tạo subscription riêng cho mỗi subscriber. Vì vậy mỗi subscriber có thể có lượng demand và tốc độ tiêu thụ riêng.

## 3. Vòng đời tín hiệu của một subscriber

Một subscription thông thường có trình tự:

1. Subscriber gọi `publisher.subscribe(subscriber)`.
2. Publisher gọi `subscriber.onSubscribe(subscription)` để cung cấp kênh điều khiển.
3. Subscriber lưu subscription và gọi `request(n)` với `n > 0` khi sẵn sàng nhận dữ liệu.
4. Publisher gọi `onNext(item)` tối đa theo lượng demand còn lại.
5. Subscriber xử lý dữ liệu rồi yêu cầu thêm, hoặc gọi `cancel()` nếu không còn cần dữ liệu.
6. Khi nguồn kết thúc bình thường, publisher gọi `onComplete()`; khi có lỗi, publisher gọi `onError(error)`.

`onSubscribe` phải đến trước các tín hiệu dữ liệu hoặc tín hiệu kết thúc. `onError` và `onComplete` là tín hiệu kết thúc: một subscription không tiếp tục phát `onNext` sau khi đã gửi tín hiệu kết thúc.

`onNext` là tín hiệu dữ liệu. Các lời gọi tín hiệu của một subscription phải được tuần tự hóa theo hợp đồng Flow; subscriber không nên phải xử lý nhiều `onNext` đồng thời cho cùng một subscription.

## 4. `request(n)` điều tiết nhu cầu như thế nào?

`Flow.Subscription` có hai phương thức:

```java
public interface Subscription {
    void request(long n);
    void cancel();
}
```

`request(n)` yêu cầu publisher phát thêm tối đa `n` phần tử theo nhu cầu tích lũy của subscription.

- `n` phải là số dương.
- Các lần gọi `request` cộng dồn nhu cầu còn lại.
- Publisher không được phát `onNext` vượt quá nhu cầu đã được yêu cầu.
- `Long.MAX_VALUE` có thể được dùng để biểu thị nhu cầu không giới hạn.
- Yêu cầu `0` hoặc số âm vi phạm giao thức; publisher tuân thủ Flow báo lỗi bằng `IllegalArgumentException` qua `onError`.

Ví dụ subscriber yêu cầu một phần tử mỗi lần:

```java
public void onSubscribe(Flow.Subscription subscription) {
    this.subscription = subscription;
    subscription.request(1);
}

public void onNext(Item item) {
    process(item);
    subscription.request(1);
}
```

Subscriber chỉ yêu cầu phần tử tiếp theo sau khi xử lý phần tử hiện tại. Cách này dễ kiểm soát lượng công việc đang được giao, nhưng tạo nhiều lần gọi `request` nếu throughput cao.

### Yêu cầu theo lô

Với dữ liệu cần throughput cao, subscriber có thể yêu cầu theo batch:

```java
private static final int BATCH_SIZE = 64;
private int processed;

public void onSubscribe(Flow.Subscription subscription) {
    this.subscription = subscription;
    subscription.request(BATCH_SIZE);
}

public void onNext(Item item) {
    process(item);
    if (++processed == BATCH_SIZE) {
        processed = 0;
        subscription.request(BATCH_SIZE);
    }
}
```

Subscriber yêu cầu trước 64 phần tử và bổ sung thêm 64 sau khi xử lý hết batch. Cách này giảm số lần gọi `request`, nhưng cho phép publisher có tối đa một batch demand đang chờ.

Chọn batch theo khả năng xử lý và giới hạn bộ nhớ. Batch quá lớn có thể làm tăng lượng dữ liệu đang chờ; batch quá nhỏ có thể tăng chi phí điều phối.

## 5. Demand không đồng nghĩa với số byte

Flow đếm nhu cầu theo **số phần tử** được phát, không phải số byte hay dung lượng bộ nhớ. Một phần tử có thể nhỏ hoặc rất lớn.

Ví dụ, `request(100)` cho phép nhận tối đa 100 object; nếu mỗi object giữ một ảnh 20 MB, lượng dữ liệu được yêu cầu vẫn có thể rất lớn. Với phần tử có kích thước biến đổi, ứng dụng cần thêm giới hạn về kích thước, buffer hoặc số byte đang xử lý.

Để bảo vệ bộ nhớ, có thể kết hợp:

- Giới hạn số phần tử đang được yêu cầu.
- Giới hạn kích thước mỗi phần tử.
- Giới hạn số byte trong buffer hoặc hàng đợi nội bộ.
- Không giữ tham chiếu đến các phần tử đã xử lý.
- Giải phóng tài nguyên gắn với phần tử sau khi xử lý xong.

Backpressure ở cấp phần tử là một phần của kiểm soát tải; nó không thay thế việc thiết kế giới hạn bộ nhớ.

## 6. `cancel()` và kết thúc subscription

`cancel()` báo cho publisher rằng subscriber không muốn nhận thêm dữ liệu:

```java
subscription.cancel();
```

Publisher nên ngừng phát dữ liệu cho subscription đã bị hủy và giải phóng tài nguyên liên quan khi có thể. Subscriber thường hủy khi:

- Người dùng rời khỏi màn hình hoặc đóng phiên.
- Đã nhận đủ số phần tử cần thiết.
- Không thể tiếp tục xử lý.
- Một bước xử lý nội bộ thất bại và luồng không thể phục hồi.

`cancel()` không phải cơ chế hoàn tác các tác dụng phụ đã xảy ra. Dữ liệu đã được xử lý hoặc ghi xuống hệ thống trước khi hủy vẫn tồn tại. Trong môi trường bất đồng bộ, một tín hiệu đang được xử lý tại thời điểm hủy cũng cần được tính đến trong thiết kế.

`onComplete()` biểu thị publisher đã phát xong bình thường; `onError()` biểu thị luồng kết thúc do lỗi. Subscriber nên giải phóng tài nguyên ở cả hai nhánh.

## 7. Publisher phải tôn trọng demand

Publisher có trách nhiệm theo dõi lượng demand và chỉ phát `onNext` khi có demand còn lại. Nếu publisher phát nhiều hơn số phần tử subscriber yêu cầu, publisher vi phạm giao thức.

Trong publisher tự cài đặt, cần xử lý cẩn thận:

1. Demand có thể được yêu cầu nhiều lần và phải cộng dồn.
2. Phép cộng demand phải tránh tràn `long`; khi vượt giới hạn, có thể bão hòa ở `Long.MAX_VALUE`.
3. Nhiều lời gọi `request` có thể đến từ các thread khác nhau.
4. Không phát `onNext` đồng thời cho cùng một subscriber.
5. `cancel` phải ngăn các lần phát tiếp theo khi có thể.
6. `onError` hoặc `onComplete` chỉ được gửi một lần và kết thúc subscription.
7. Không gọi callback subscriber trong vùng khóa có thể gây deadlock hoặc chặn các thao tác điều khiển.

Publisher đơn giản có thể dùng một bộ đếm demand nguyên tử, hàng đợi có giới hạn và một vòng lặp drain được tuần tự hóa. Publisher production cần đặc biệt chú ý race giữa `request`, `cancel`, phát dữ liệu và tín hiệu kết thúc.

## 8. `SubmissionPublisher` — publisher có sẵn trong JDK

Java 9 cung cấp `SubmissionPublisher<T>`, một implementation của `Flow.Publisher<T>`. Nó phát dữ liệu bất đồng bộ thông qua một `Executor` và duy trì buffer riêng cho từng subscriber.

Ví dụ tạo publisher với executor riêng và buffer capacity được yêu cầu là 16:

```java
ExecutorService executor = Executors.newFixedThreadPool(2);
SubmissionPublisher<String> publisher =
    new SubmissionPublisher<>(executor, 16);
```

Subscriber vẫn kiểm soát lượng dữ liệu nhận bằng `request(n)`. Buffer cho phép publisher tạm thời giữ các phần tử đã submit trong khi subscriber chưa yêu cầu hoặc chưa xử lý kịp.

### `submit` và `offer`

`submit(item)` phát một phần tử đến các subscriber hiện tại. Nếu buffer của subscriber bị đầy, `submit` có thể chờ cho đến khi có chỗ trống. Vì vậy, producer có thể bị chặn khi consumer xử lý chậm.

`offer(...)` cung cấp cách phát không chờ theo cùng kiểu đó và cho phép xác định cách xử lý khi subscriber không nhận được phần tử, chẳng hạn bỏ phần tử qua drop handler. Khi dùng chính sách bỏ dữ liệu, ứng dụng phải ghi nhận và chấp nhận rõ ràng khả năng mất dữ liệu.

Chọn cách phát theo yêu cầu của hệ thống:

| Cách phát | Hành vi khi subscriber chậm | Phù hợp khi |
| --- | --- | --- |
| `submit` | Có thể chặn producer khi buffer đầy | Cần giữ dữ liệu và producer có thể chờ |
| `offer` với drop handler | Có thể bỏ phần tử khi không có chỗ, theo chính sách handler | Dữ liệu có thể mất có kiểm soát, như telemetry hoặc cập nhật trạng thái mới nhất |

Không gọi `submit` trên chính thread executor duy nhất đang cần chạy subscriber để giải phóng buffer. Nếu producer chặn thread đó trong khi subscriber không thể được lập lịch, ứng dụng có thể deadlock. Tách thread producer và executor xử lý subscriber khi dùng publisher có buffer giới hạn.

### Nhiều subscriber

Mỗi subscriber có buffer và demand riêng. Một subscriber nhanh có thể nhận dữ liệu đều trong khi subscriber khác yêu cầu chậm. Tuy nhiên, khi dùng `submit`, subscriber chậm có thể làm producer phải chờ vì publisher cần có chỗ cho các subscriber hiện tại.

`estimateMaximumLag()` và `estimateMinimumDemand()` cung cấp số liệu ước lượng hữu ích để quan sát tải. Đây là số liệu ước lượng, không nên dùng như một phép đồng bộ chính xác hoặc điều kiện bảo đảm không có race.

## 9. Các chiến lược xử lý áp lực ngược

Flow định nghĩa giao thức demand, nhưng không áp đặt một chính sách buffer duy nhất. Ứng dụng cần chọn chiến lược phù hợp với ý nghĩa dữ liệu:

### Làm chậm producer

Subscriber yêu cầu theo lô nhỏ hoặc publisher chỉ đọc nguồn tiếp theo khi còn demand. Phù hợp với nguồn có thể tạm dừng như đọc tệp, truy vấn phân trang hoặc tạo công việc theo yêu cầu.

### Buffer có giới hạn

Publisher giữ một lượng dữ liệu tối đa. Khi buffer đầy, producer chờ, tạm dừng đọc hoặc báo lỗi. Đây là lựa chọn phù hợp khi cần giữ dữ liệu và có thể điều tiết nguồn.

### Bỏ dữ liệu có chính sách

Với telemetry hoặc trạng thái cập nhật liên tục, có thể bỏ dữ liệu cũ, bỏ dữ liệu mới hoặc chỉ giữ giá trị gần nhất. Chính sách phải phù hợp nghiệp vụ; không áp dụng cho giao dịch hoặc sự kiện không được phép mất.

### Gộp hoặc lấy mẫu

Nhiều sự kiện có thể được gộp thành một bản cập nhật tổng hợp, hoặc chỉ lấy mẫu theo chu kỳ. Cách này giảm tải nhưng thay đổi độ chi tiết của dữ liệu.

### Lưu trữ tạm

Nếu producer không thể dừng và dữ liệu không được phép mất, có thể ghi vào log hoặc hàng đợi bền vững rồi tiêu thụ dần. Cần tính đến dung lượng lưu trữ, retry, thứ tự và cơ chế xác nhận.

Không có một chiến lược đúng cho mọi luồng. Hãy quyết định rõ hệ thống ưu tiên giữ đủ dữ liệu, độ trễ thấp, tính mới của trạng thái hay khả năng tiếp tục khi consumer chậm.

## 10. `Processor` và backpressure qua nhiều bước

`Flow.Processor<T, R>` vừa nhận dữ liệu kiểu `T`, vừa phát dữ liệu kiểu `R`. Ví dụ một processor có thể lọc, chuyển đổi, xác thực hoặc gom nhóm dữ liệu.

```text
Source Publisher
      |
      v
Transform Processor
      |
      v
Final Subscriber
```

Backpressure cần được truyền qua cả chuỗi. Khi subscriber cuối yêu cầu ít dữ liệu, processor không nên tiếp tục lấy vô hạn dữ liệu từ publisher đầu vào. Processor phải cân đối demand của downstream với lượng công việc đang chờ và khả năng xử lý của chính nó.

Một processor có buffer nội bộ phải giới hạn buffer đó. Nếu chỉ chuyển demand không giới hạn lên upstream, áp lực ngược có thể bị mất ngay tại processor và hàng đợi vẫn tăng vô hạn.

Với pipeline nhiều bước, hãy xác định rõ:

- Bước nào phát demand ngược về upstream.
- Bước nào có buffer và dung lượng tối đa bao nhiêu.
- Bước nào có thể tạm dừng producer.
- Khi buffer đầy thì chờ, bỏ, gộp hay báo lỗi.
- Khi subscriber cuối cancel hoặc lỗi, các subscription upstream được hủy như thế nào.

## 11. Ví dụ hoàn chỉnh: subscriber yêu cầu từng phần tử

Chương trình sau dùng `SubmissionPublisher<Integer>` với buffer capacity 1 và một executor riêng. Subscriber chỉ yêu cầu một phần tử trong `onSubscribe`, xử lý phần tử đó trong `onNext`, rồi mới yêu cầu phần tử tiếp theo.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class Main {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor(
            task -> new Thread(task, "flow-worker"));
        CountDownLatch completed = new CountDownLatch(1);
        AtomicInteger received = new AtomicInteger();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        try {
            try (SubmissionPublisher<Integer> publisher =
                     new SubmissionPublisher<>(executor, 1)) {
                publisher.subscribe(new Flow.Subscriber<Integer>() {
                    private Flow.Subscription subscription;

                    @Override
                    public void onSubscribe(Flow.Subscription subscription) {
                        this.subscription = subscription;
                        subscription.request(1);
                    }

                    @Override
                    public void onNext(Integer item) {
                        System.out.println("received: " + item);
                        received.incrementAndGet();
                        subscription.request(1);
                    }

                    @Override
                    public void onError(Throwable error) {
                        failure.set(error);
                        completed.countDown();
                    }

                    @Override
                    public void onComplete() {
                        System.out.println("completed: " + received.get());
                        completed.countDown();
                    }
                });

                for (int item = 1; item <= 5; item++) {
                    publisher.submit(item);
                }
            }

            if (!completed.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("subscriber did not complete");
            }
            if (failure.get() != null) {
                throw new AssertionError("publisher failed", failure.get());
            }
            if (received.get() != 5) {
                throw new AssertionError("expected 5 items, got " + received.get());
            }
        } finally {
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new AssertionError("executor did not terminate");
            }
        }
    }
}
```

Lưu thành `Main.java`, biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all Main.java
java Main
```

Stdout chính xác:

```text
received: 1
received: 2
received: 3
received: 4
received: 5
completed: 5
```

Subscriber chỉ yêu cầu một phần tử tại một thời điểm. Publisher phát bất đồng bộ trên `flow-worker`; khi buffer đầy, lời gọi `submit` từ thread `main` có thể phải chờ cho đến khi subscriber xử lý và tạo thêm chỗ trống. Khi publisher được đóng, subscriber nhận `onComplete` sau khi các phần tử đã submit được xử lý.

Ví dụ minh họa cách phối hợp demand và buffer của `SubmissionPublisher`. Trong ứng dụng thực tế, callback `onNext` nên xử lý nhanh hoặc chuyển công việc sang một cơ chế có giới hạn; không đưa tác vụ blocking dài vào executor dispatch nếu điều đó làm chậm mọi subscriber dùng chung executor.

## 12. Kiểm thử và quan sát backpressure

Để kiểm thử publisher/subscriber, nên quan sát cả số phần tử được phát, demand và lượng dữ liệu đang chờ:

1. Subscriber không request: xác nhận publisher không phát `onNext`.
2. Subscriber request `1`: xác nhận chỉ có tối đa một phần tử được phát trước khi có request tiếp theo.
3. Subscriber request theo batch: xác nhận tổng số phần tử không vượt tổng demand.
4. Subscriber request `Long.MAX_VALUE`: xác nhận luồng có thể tiêu thụ liên tục cho đến khi hoàn tất.
5. Subscriber gọi `cancel`: xác nhận publisher dừng phát các phần tử tiếp theo.
6. Subscriber request `0` hoặc số âm: xác nhận lỗi giao thức được báo qua `onError`.
7. Subscriber xử lý chậm: xác nhận buffer không vượt giới hạn và producer áp dụng đúng chính sách chờ/bỏ/lỗi.
8. Nhiều subscriber có tốc độ khác nhau: xác nhận demand và buffer của từng subscriber được xử lý độc lập.
9. Publisher hoàn tất hoặc lỗi: xác nhận chỉ một tín hiệu terminal được gửi và tài nguyên được giải phóng.

Với `SubmissionPublisher`, có thể dùng các phương thức ước lượng lag/demand để theo dõi tải, nhưng cần kết hợp metric của ứng dụng như thời gian xử lý `onNext`, số lần producer phải chờ, số phần tử bị drop và số lần subscriber cancel.

## 13. Lỗi thường gặp

1. **Không gọi `request`.** Subscriber đã đăng ký nhưng không yêu cầu dữ liệu, nên publisher không có demand để phát `onNext`.
2. **Gọi `request` với số 0 hoặc âm.** Đây là yêu cầu không hợp lệ và phải dẫn đến lỗi theo giao thức Flow.
3. **Yêu cầu `Long.MAX_VALUE` theo thói quen.** Điều này gần như loại bỏ giới hạn demand của subscriber; chỉ dùng khi consumer thực sự có thể tiếp nhận toàn bộ tốc độ nguồn.
4. **Cho rằng `request(10)` có nghĩa là nhận đúng 10 phần tử ngay lập tức.** Đây là nhu cầu tối đa được cấp thêm; publisher có thể phát bất đồng bộ và nguồn có thể kết thúc sớm.
5. **Nhầm demand với dung lượng byte.** Flow đếm phần tử; ứng dụng vẫn cần giới hạn kích thước phần tử và tổng bộ nhớ.
6. **Dùng hàng đợi không giới hạn phía sau subscriber.** Backpressure upstream không giúp ích nếu callback lại đẩy mọi phần tử vào một queue không giới hạn.
7. **Block lâu trong `onNext`.** Callback chậm có thể làm chậm executor dispatch và các subscriber khác dùng chung executor.
8. **Dùng `submit` trên thread duy nhất cần tiêu thụ buffer.** Producer có thể chặn chính thread cần chạy subscriber, gây deadlock.
9. **Bỏ dữ liệu mà không ghi nhận.** Chính sách drop phải được thể hiện bằng metric, log hoặc trạng thái phù hợp để ứng dụng biết dữ liệu đã mất.
10. **Quên cancel upstream trong processor.** Subscriber cuối dừng nhưng processor vẫn yêu cầu dữ liệu, khiến nguồn tiếp tục tạo công việc không cần thiết.
11. **Coi `onComplete` và `onError` là tín hiệu cần demand.** Tín hiệu kết thúc không phải phần tử `onNext` và có thể được gửi khi demand bằng 0.
12. **Dùng số liệu lag ước lượng như giá trị đồng bộ chính xác.** Các giá trị quan sát của `SubmissionPublisher` có thể thay đổi ngay sau khi đọc.

## 14. Ghi nhớ

1. `Flow` được giới thiệu trong Java 9 để chuẩn hóa giao tiếp publisher/subscriber có demand.
2. Subscriber nhận `Subscription` trong `onSubscribe` và gọi `request(n)` để yêu cầu phần tử.
3. Publisher không được phát nhiều `onNext` hơn lượng demand còn lại.
4. Demand được cộng dồn; `Long.MAX_VALUE` có thể biểu thị nhu cầu không giới hạn.
5. `cancel()` yêu cầu publisher dừng phát dữ liệu cho subscriber.
6. `onError` và `onComplete` là tín hiệu kết thúc, không tiêu thụ demand.
7. `SubmissionPublisher` cung cấp buffer theo subscriber; `submit` có thể chờ khi buffer đầy, còn `offer` cho phép áp dụng chính sách không chờ và drop.
8. Backpressure theo số phần tử không thay thế giới hạn byte hoặc bộ nhớ.
9. Với pipeline nhiều bước, processor phải truyền demand ngược và giới hạn buffer nội bộ.
10. Chọn rõ chính sách khi consumer chậm: giảm tốc producer, buffer giới hạn, bỏ/gộp dữ liệu hoặc lưu trữ bền vững.