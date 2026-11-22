# Đóng SubmissionPublisher, tín hiệu kết thúc và vòng đời executor của publisher

## 1. Ba vòng đời khác nhau dễ bị nhầm

`SubmissionPublisher<T>` trong `java.util.concurrent` là một implementation của `Flow.Publisher<T>`. Nó phát các phần tử không `null` theo cách **bất đồng bộ** tới những subscriber hiện tại, sử dụng `Executor` để thực hiện các callback. Khi nguồn không còn dữ liệu hoặc thất bại, publisher cần kết thúc subscription đúng cách.

Cần phân biệt **ba sự kiện**:

1. **Publisher ngừng nhận dữ liệu:** `publisher.close()` hoặc `publisher.closeExceptionally(error)` chuyển publisher sang trạng thái đóng, không nhận những lần `submit`/`offer` mới.
2. **Subscriber nhận tín hiệu kết thúc:** callback `onComplete()` hoặc `onError(Throwable)` có thể được gửi qua executor **sau khi lệnh đóng trả về**. Trạng thái “publisher đã đóng” chưa chứng minh “mọi subscriber đã chạy xong”.
3. **Executor ngừng hoạt động:** executor được đưa vào constructor có vòng đời riêng. Đóng `SubmissionPublisher` **không đồng nghĩa gọi `ExecutorService.shutdown()`**. Chủ sở hữu executor phải tự quyết định khi nào được shutdown.

Nhầm ba sự kiện này có thể làm chương trình kết thúc trước khi các callback chạy, shutdown executor quá sớm dẫn tới tác vụ bị từ chối, hoặc để thread pool riêng chạy mãi dù publisher đã đóng.

Bài học tập trung vào **Java concurrency nói chung**: `Flow`, `SubmissionPublisher`, `ExecutorService` và cách dọn tài nguyên. Đây là kiến thức JDK độc lập với Spring.

## 2. Nhắc lại hợp đồng Flow trước khi nói về kết thúc

Bốn interface cốt lõi:

| Interface | Vai trò |
| --- | --- |
| `Flow.Publisher<T>` | Nguồn cho phép đăng ký `Subscriber` và phát tín hiệu dữ liệu. |
| `Flow.Subscriber<T>` | Nhận `onSubscribe`, `onNext`, `onError` và `onComplete`. |
| `Flow.Subscription` | Liên kết riêng của từng subscriber; `request(n)` cấp demand, `cancel()` yêu cầu hủy. |
| `Flow.Processor<T,R>` | Vừa là subscriber upstream vừa là publisher downstream. |

Vòng đời logic của **một subscription**:

```text
publisher.subscribe(subscriber)
        |
        v
  onSubscribe(subscription)
        |
        +-- subscriber.request(n)  -> mở hạn mức nhận item
        |
        +-- onNext(item)           -> 0..n lần theo demand
        |
        +-- ... có thể request tiếp ...
        |
        +-- onComplete()           -> kết thúc bình thường
             HOẶC
            onError(error)         -> kết thúc bất thường
```

`onComplete` và `onError` là **terminal signals**: một subscription không được nhận thêm `onNext` sau khi đã kết thúc. Hai tín hiệu terminal là những kết quả thay thế nhau cho cùng một subscription, không phải hai bước liên tiếp.

`cancel()` là yêu cầu ngừng subscription theo kiểu *best effort*, **không phải tín hiệu `onComplete`**. Một subscriber chủ động hủy không được đảm bảo sẽ nhận thêm `onComplete`/`onError`. Vì vậy, chương trình muốn chờ sự kiện kết thúc phải hiểu có thể có nhánh hủy không có terminal callback.

## 3. close(): kết thúc bình thường

`publisher.close()` được dùng khi publisher **đã sản xuất xong toàn bộ dữ liệu hợp lệ**.

Theo hợp đồng `SubmissionPublisher`:

- Nếu chưa đóng, nó bắt đầu gửi `onComplete` tới các subscriber hiện tại.
- Không nhận các lần publish mới; `isClosed()` trả `true`.
- Lệnh gọi lặp lại được xử lý theo semantics “nếu chưa đóng” (idempotent về trạng thái đóng).
- **Khi `close()` trả về, không có bảo đảm rằng tất cả subscriber đã xử lý xong hoặc đã nhận callback `onComplete`.**
- Các item đã submit được xử lý theo thứ tự cho từng subscriber hiện tại, nếu không có drop, cancellation hoặc exception. Subscriber vẫn cần cấp demand đủ để tiêu thụ item còn trong buffer.

Thứ tự ý tưởng:

```text
Producer thread                  Delivery executor / subscriber
    |                                          |
    | submit(A)                                |
    | submit(B)                                |
    | close() --------------------------------> | onNext(A)
    | close() trả về                           | onNext(B)
    |                                          | onComplete()
    |  (phải chờ terminal riêng nếu cần)       |
    +------------------------------------------+
```

Đường thời gian minh họa **không khẳng định** callback luôn bắt đầu sau `close`: chúng có thể chạy trước, trong hoặc sau lời gọi đóng. Điều chắc chắn là chỉ chờ `close` trả về thì chưa chứng minh subscriber hoàn tất.

Khi gọi `submit(item)` sau khi publisher đóng, `IllegalStateException` được ném. Dù vậy, không dùng `isClosed()` rồi `submit()` như một phép kiểm tra và cập nhật nguyên tử giữa các producer: thread khác có thể đóng publisher sau bước kiểm tra. Cần thiết kế điều phối producer hoặc xử lý race một cách có chủ đích.

## 4. closeExceptionally(error): kết thúc do lỗi

`publisher.closeExceptionally(error)` dùng khi nguồn **không thể tiếp tục hoàn tất bình thường**. Nếu publisher chưa đóng, phương thức gửi `onError(error)` tới các subscriber hiện tại và ngừng nhận item mới. Các subscriber đăng ký **sau khi publisher đã đóng lỗi** cũng nhận `onSubscribe` rồi tín hiệu lỗi tương ứng.

Điểm cần nhớ:

- `error` phải không `null`; truyền `null` ném `NullPointerException`.
- `getClosedException()` trả lỗi đã dùng để đóng bất thường; trả `null` nếu chưa đóng hoặc đóng bình thường.
- Lệnh `closeExceptionally` trả về **không chờ** mọi `onError` callback hoàn tất.
- Không dùng `closeExceptionally` chỉ để diễn tả việc người dùng hết quan tâm dữ liệu; đó thường là nhánh `Subscription.cancel()`.
- Nếu publisher đã được đóng trước đó, một lần đóng khác không biến đổi lại kết quả terminal của những subscription đã kết thúc. Hãy quyết định kết quả kết thúc tại một nơi rõ ràng.

Một số lỗi phát sinh riêng trong **callback subscriber** không đồng nghĩa publisher phải tự động phát `onError` tới toàn bộ subscriber còn lại. Ví dụ, theo `SubmissionPublisher`, khi phương thức của một subscriber ném exception, subscription đó có thể bị hủy. Constructor có callback xử lý exception của `onNext`; nó không tự biến sự cố một subscriber thành lỗi toàn cục cho tất cả subscribers. Chính sách dừng toàn pipeline cần được thiết kế riêng.

## 5. Ví dụ Java 17+: đóng bình thường và chờ subscriber thực sự hoàn tất

`SubmissionPublisher.consume(Consumer)` tạo một subscriber tự yêu cầu và xử lý dữ liệu qua `Consumer`, đồng thời trả về `CompletableFuture<Void>` để quan sát khi subscription kết thúc hoặc thất bại. Đây là cách ngắn gọn để phân biệt `close` với **đợi terminal**.

Lưu tệp `PublisherNormalCloseDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class PublisherNormalCloseDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService delivery = Executors.newSingleThreadExecutor();
        SubmissionPublisher<String> publisher =
                new SubmissionPublisher<>(delivery, 8);

        try {
            CompletableFuture<Void> completed =
                    publisher.consume(item -> System.out.println("onNext: " + item));

            publisher.submit("A");
            publisher.submit("B");
            publisher.close();

            // close() chỉ đánh dấu kết thúc và phát tín hiệu bất đồng bộ.
            // get() chờ cho consumer nhận terminal signal.
            completed.get(5, TimeUnit.SECONDS);

            System.out.println("subscriber completed");
            System.out.println("publisher closed: " + publisher.isClosed());
            System.out.println("executor closed by publisher: " + delivery.isShutdown());
        } finally {
            publisher.close();      // Có thể gọi lại an toàn nếu đã đóng.
            delivery.shutdown();    // Executor thuộc quyền sở hữu của main.
            if (!delivery.awaitTermination(5, TimeUnit.SECONDS)) {
                delivery.shutdownNow();
            }
        }

        System.out.println("executor shutdown: " + delivery.isShutdown());
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 PublisherNormalCloseDemo.java
java PublisherNormalCloseDemo
```

Kết quả khi thực thi thành công:

```text
onNext: A
onNext: B
subscriber completed
publisher closed: true
executor closed by publisher: false
executor shutdown: true
```

Vì `completed.get(...)` chờ xong trước khi main in trạng thái, thứ tự output này không phụ thuộc việc executor khởi động callback nhanh hay chậm. Hai `onNext` có thứ tự A rồi B trong cùng subscription; `CompletableFuture` được hoàn tất khi subscriber nhận `onComplete`.

Lệnh `delivery.isShutdown()` vẫn trả `false` trước khi main tự `shutdown()`, chứng minh việc đóng publisher **không sở hữu và không đóng executor do caller cung cấp**. `shutdown()` cấm nhận task mới và cho phép những task đã gửi tiếp tục; `awaitTermination` đợi executor hoàn tất, còn `shutdownNow()` chỉ là nỗ lực dừng khẩn khi quá thời hạn.

### Vì sao không chỉ viết try-with-resources rồi kết thúc main?

`SubmissionPublisher` triển khai `AutoCloseable` nên có thể viết:

```java
try (SubmissionPublisher<String> publisher =
             new SubmissionPublisher<>()) {
    publisher.submit("item");
}
```

Đây là **mã minh họa**, không phải chương trình độc lập. `try-with-resources` tự gọi `close`, nhưng **không chờ subscriber nhận xong `onComplete`** và không cho phép suy ra rằng mọi callback đã chạy xong khi ra khỏi block. Nếu kết quả subscriber quan trọng, cần một completion signal/future hoặc latch rõ ràng.

## 6. Ví dụ Java 17+: closeExceptionally và onError

Ví dụ sau dùng `CountDownLatch` để chờ callback lỗi, tránh dựa vào `Thread.sleep()`. Không submit item trước khi đóng lỗi, vì thứ tự giữa dữ liệu pending và quyết định đóng bất thường là một vấn đề riêng của quy tắc hủy/terminal; ở đây ta cần quan sát thuần túy nhánh `onError`.

Lưu tệp `PublisherExceptionalCloseDemo.java`:

```java
import java.io.IOException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class PublisherExceptionalCloseDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService delivery = Executors.newSingleThreadExecutor();
        SubmissionPublisher<String> publisher =
                new SubmissionPublisher<>(delivery, 8);

        CountDownLatch terminal = new CountDownLatch(1);
        AtomicReference<String> outcome = new AtomicReference<>();

        try {
            publisher.subscribe(new Flow.Subscriber<>() {
                @Override
                public void onSubscribe(Flow.Subscription subscription) {
                    subscription.request(Long.MAX_VALUE);
                }

                @Override
                public void onNext(String item) {
                    System.out.println("unexpected item: " + item);
                }

                @Override
                public void onError(Throwable error) {
                    outcome.set("onError: " + error.getClass().getSimpleName()
                            + ": " + error.getMessage());
                    terminal.countDown();
                }

                @Override
                public void onComplete() {
                    outcome.set("onComplete");
                    terminal.countDown();
                }
            });

            publisher.closeExceptionally(new IOException("source failed"));

            if (!terminal.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Terminal signal timed out");
            }

            System.out.println(outcome.get());
            System.out.println("publisher closed: " + publisher.isClosed());
            System.out.println("closed cause: "
                    + publisher.getClosedException().getMessage());
        } finally {
            publisher.close();
            delivery.shutdown();
            if (!delivery.awaitTermination(5, TimeUnit.SECONDS)) {
                delivery.shutdownNow();
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 PublisherExceptionalCloseDemo.java
java PublisherExceptionalCloseDemo
```

Kết quả:

```text
onError: IOException: source failed
publisher closed: true
closed cause: source failed
```

`onSubscribe` đến trước terminal callback, dù cả hai được thực thi bất đồng bộ. Trong ví dụ chỉ có lỗi nguồn, nên subscriber đi vào `onError` thay vì `onComplete`. `CountDownLatch` truyền điểm hoàn tất sang main thread; `AtomicReference` truyền kết quả giữa threads một cách an toàn.

Trong ứng dụng thực tế, `onError` nên ghi nhận và phát tín hiệu failure ra nơi gọi phù hợp, đồng thời giải phóng tài nguyên do subscriber sở hữu. Chỉ in thông báo lỗi không đảm bảo caller xử lý lỗi đúng.

## 7. Đăng ký subscriber sau khi publisher đã đóng

Một subscriber có thể `subscribe(...)` **sau** khi publisher đã đóng. `SubmissionPublisher` xử lý theo trạng thái kết thúc:

- **Đóng bình thường:** subscriber mới vẫn được gọi `onSubscribe` rồi `onComplete`.
- **Đóng bất thường:** subscriber mới được gọi `onSubscribe` rồi `onError` với exception đã ghi.
- Không có cơ chế phát lại toàn bộ item đã được submit trước khi đóng. `SubmissionPublisher` là cơ chế phát cho subscriber hiện tại, không phải event log lịch sử.
- Các callback vẫn đi qua executor của publisher; vì vậy việc muốn có subscriber “late” cần tính đến **executor còn khả năng thực thi task**.

Điều này giải thích vì sao không nên shutdown executor ngay khi publisher đóng nếu còn chủ động cho phép đăng ký/quan sát tín hiệu kết thúc sau đó. Nếu vòng đời chương trình cho phép late subscribers, phải xác định chính sách và thời hạn cho việc này. Một mô hình quản lý hữu ích là **ngừng tạo subscription mới trước**, cho tất cả subscriber hiện hữu đi tới terminal, rồi mới shutdown executor của pipeline.

Không sử dụng `hasSubscribers()` hay `getNumberOfSubscribers()` để tự xác nhận tất cả callback hoàn tất. Các phương thức này phục vụ quan sát trạng thái, không phải cơ chế join tất cả tín hiệu terminal.

## 8. Ai chịu trách nhiệm đóng executor?

`SubmissionPublisher` dùng một `Executor` để gọi các phương thức của subscriber. Có hai cấu hình chính:

### 8.1. Publisher mặc định

```java
SubmissionPublisher<String> publisher = new SubmissionPublisher<>();
```

Thông thường JDK dùng `ForkJoinPool.commonPool()`, hoặc tạo thread cho tác vụ trong cấu hình không hỗ trợ mức song song tối thiểu. **Không được shutdown `ForkJoinPool.commonPool()` của toàn JVM như thể nó là pool riêng của publisher.** Không thể giả định executor mặc định là một thread pool độc quyền chỉ dành cho publisher đó.

### 8.2. Executor do ứng dụng cung cấp

```java
ExecutorService delivery = Executors.newFixedThreadPool(2);
SubmissionPublisher<String> publisher =
        new SubmissionPublisher<>(delivery, 64);
```

Hai dòng này **chỉ minh họa khởi tạo**, chưa có logic cleanup hoàn chỉnh.

`delivery` thuộc nơi tạo/quản lý executor. Nếu ứng dụng tạo pool riêng cho publisher, ứng dụng phải gọi `shutdown()` và có thể `awaitTermination(...)` khi không còn nhiệm vụ cần nhận. Nếu executor dùng chung cho nhiều publisher hoặc thành phần khác, **không một publisher riêng lẻ nào được tự shutdown executor chung**; chủ sở hữu dùng chung quyết định thời điểm đóng sau khi các thành phần đã kết thúc.

### Thứ tự shutdown an toàn

Một chuỗi quản lý vòng đời điển hình:

1. **Ngừng producer:** dừng timer, loop hoặc nguồn gọi `submit`/`offer`; đồng bộ hóa với những producer đang hoạt động để tránh race submit với close.
2. **Quyết định kết quả cuối:** gọi `close()` khi hết dữ liệu bình thường; gọi `closeExceptionally(error)` khi publisher bị lỗi không thể hoàn tất.
3. **Chờ tiêu thụ dữ liệu và terminal callback:** dùng `CompletableFuture` từ `consume`, latch/future tự quản lý ở subscriber hoặc cơ chế đồng bộ tương đương. Với nhiều subscriber, chờ từng subscriber cần thiết.
4. **Shutdown executor do mình sở hữu:** gọi `shutdown()`, sau đó `awaitTermination` với timeout; xử lý timeout và interruption theo chính sách ứng dụng.
5. **Dọn các tài nguyên khác:** đóng nguồn, buffer hoặc connection theo ownership của chúng.

Không áp dụng công thức một cách máy móc trong mọi hệ thống: có trường hợp shutdown khẩn buộc bỏ dữ liệu và không thể đợi hoàn tất. Cần phân biệt **graceful shutdown** (ưu tiên xử lý hết dữ liệu) và **forced shutdown** (ưu tiên kết thúc nhanh, chấp nhận mất việc đang chờ).

### Vì sao shutdown sớm gây lỗi?

Nếu `executor.shutdown()` xảy ra **trước** khi publisher kịp xếp các callback cuối, executor có thể ném `RejectedExecutionException` khi publisher cố gửi task. JavaDoc `SubmissionPublisher` cho phép exception executor bị ném ngược ra từ những đường publish. Khi đó dữ liệu có thể chưa đến mọi subscriber. Không nên suy ra chỉ cần bắt exception rồi coi như mọi subscriber đã nhận `onError`.

Đặc biệt, `shutdownNow()` trả về những tác vụ chưa chạy và nỗ lực ngắt các tác vụ đang chạy, **không có bảo đảm toàn bộ callback đã xong**. Sử dụng nó như biện pháp timeout/forced shutdown có điều kiện, và phải chấp nhận rằng delivery có thể không hoàn chỉnh.

## 9. Cách chờ đúng: future, latch và tránh deadlock

### CompletableFuture của consume

`publisher.consume(consumer)` trả `CompletableFuture<Void>`:

- Hoàn tất bình thường khi subscriber được phát `onComplete`.
- Hoàn tất thất bại nếu publisher phát `onError`, consumer ném exception hoặc future bị hủy.
- `get(timeout, unit)` chờ có giới hạn và cho caller xử lý `TimeoutException` hoặc `ExecutionException`.

Mẫu này phù hợp khi chỉ cần subscriber tiêu thụ mọi item qua một `Consumer`.

### Subscriber tự triển khai

Với nhiều trạng thái kết thúc hoặc xử lý phức tạp, subscriber có thể hoàn tất một `CompletableFuture<Result>` trong `onComplete` hoặc hoàn tất exceptional trong `onError`. `CountDownLatch` đơn giản khi chỉ cần một sự kiện kết thúc. Cần suy nghĩ riêng nhánh `cancel()`, vì cancel thường không mang đến terminal callback.

### Đừng đợi trên chính thread cần chạy callback

Ví dụ: dùng **single-thread executor** vừa để gửi item, vừa để đợi một latch mà chỉ `onComplete` trên chính executor đó mới đếm xuống. Executor đang bị chiếm bởi tác vụ đợi, callback cuối không thể chạy → deadlock. Hãy đợi ở thread điều phối khác hoặc thiết kế bất đồng bộ không chặn executor xử lý tín hiệu.

Không dùng `Thread.sleep(1000)` thay cho completion signal. Trên máy nhanh có thể thừa; trên máy chậm vẫn chưa đủ. Cơ chế latch/future có timeout cho kết quả có thể kiểm chứng.

## 10. Khi có nhiều subscriber hoặc nhiều producer

Mỗi subscriber của `SubmissionPublisher` có buffer/demand riêng. Đóng publisher phát kết thúc tới các **subscriber hiện tại**, nhưng họ có thể kết thúc tại các thời điểm khác nhau.

Nếu có ba subscriber và chương trình cần cả ba hoàn tất, **một latch của subscriber thứ nhất không đủ**. Có thể dùng ba future hoặc một `CountDownLatch(3)`, mỗi subscriber đếm xuống đúng một lần khi nhận terminal. Nếu một subscriber chủ động cancel và không nhận terminal, phải có cơ chế báo hủy riêng để tránh chờ vô hạn.

Khi có nhiều producer cùng dùng publisher, hãy quyết định ai có quyền phát tín hiệu cuối. Một producer gọi `close` trong lúc producer khác còn `submit` có thể khiến bên kia nhận `IllegalStateException`. Điều phối đóng ở một lifecycle owner sau khi đã chặn nguồn phát mới và đợi các producer hoàn thành phần phát cần thiết.

Cũng cần tách biệt lỗi của từng subscriber với lỗi toàn nguồn. Một subscriber xử lý chậm hoặc ném exception không nhất thiết đồng nghĩa nguồn không còn giá trị đối với subscriber khác. Chính sách tiếp tục, hủy riêng, phát lỗi toàn pipeline hoặc retry phải được định nghĩa dựa trên nghiệp vụ.

## 11. Những điểm tinh tế về submit, buffer và backpressure khi đóng

`SubmissionPublisher` sử dụng buffer độc lập theo subscription để điều hòa khác biệt tốc độ giữa bên phát và bên nhận. Các phương thức có hành vi khác nhau:

| API | Hành vi chính |
| --- | --- |
| `submit(item)` | Thường chờ không ngắt được khi buffer của một subscriber không còn chỗ; phát item qua callback bất đồng bộ. |
| `offer(item, onDrop)` | Cho phép drop item khi thiếu chỗ và gọi handler nếu được cung cấp; có thể thử lại một lần theo kết quả handler. |
| `Subscription.request(n)` | Subscriber cấp demand dương, tăng hạn mức `onNext` được phép nhận. |
| `Subscription.cancel()` | Yêu cầu hủy subscription, thường không có terminal callback sau đó. |
| `close()` | Ngừng nhận item mới; phát tín hiệu hoàn tất bình thường. |
| `closeExceptionally(error)` | Ngừng nhận item mới; phát tín hiệu lỗi. |

Một subscriber chưa `request` đủ để nhận những item đã đệm có thể khiến việc chờ `onComplete` kéo dài. Vì thế thiết kế graceful shutdown phải dựa trên việc subscriber tiến triển và phối hợp demand, không chỉ gọi `close` rồi chờ vô hạn.

Nếu ứng dụng cho phép drop trong `offer`, không được tuyên bố rằng subscriber đã nhận “đầy đủ toàn bộ item” chỉ vì nhận `onComplete`. `onComplete` nghĩa là **không còn item mới cho subscription**, không phải một cam kết không mất dữ liệu bất kể chính sách overflow trước đó.

Giá trị `estimateMaximumLag()` và `estimateMinimumDemand()` dùng để theo dõi, không phải hàng rào đồng bộ để quyết định “mọi callback đã xử lý xong”. Khi cần chắc chắn, sử dụng protocol hoàn tất thực sự.

## 12. Xử lý lỗi, interruption và timeout có trách nhiệm

Một quy trình shutdown chất lượng cần xử lý cả nhánh không thành công:

- **Timeout chờ subscriber:** ghi nhận thành phần chưa kết thúc; quyết định có `cancel`, đóng lỗi, hay bỏ chờ tùy ứng dụng. Không báo hoàn tất nếu chưa thấy terminal callback.
- **Interruption:** nếu thread điều phối bị interrupt khi `await` hoặc `get`, trả lại cờ interrupt bằng `Thread.currentThread().interrupt()` khi bắt `InterruptedException` và kết thúc/ủy quyền cleanup theo chính sách. Mã ví dụ `main throws Exception` để đơn giản nhưng logic production cần chủ động.
- **Subscriber ném exception:** `SubmissionPublisher` có thể hủy subscription; handler đặc biệt ở constructor áp dụng khi `onNext` ném exception. Không mặc định caller nhận được exception của subscriber qua `submit`.
- **Executor bị từ chối:** một số đường có thể ném `RejectedExecutionException`; không giả định mọi subscriber đều đã nhận item hoặc terminal signal.
- **Nhiều lần đóng:** dùng kết quả đóng đầu tiên làm kết quả lifecycle; gọi `close` lần nữa không phải kỹ thuật gửi lại terminal để “chắc ăn”.

Không bao giờ giữ khóa ứng dụng trong lúc chờ callback nếu callback cần chính khóa đó để tiến triển. Việc đợi terminal nên xảy ra sau khi đã nhả những synchronization lock có thể gây deadlock.

## 13. Bảng lựa chọn API theo tình huống

| Tình huống | Hành động phù hợp |
| --- | --- |
| Đã phát hết item và mọi producer kết thúc | `close()`, chờ những subscriber quan trọng nhận terminal. |
| Nguồn bị hỏng, không thể tiếp tục | `closeExceptionally(cause)`, ghi nhận lỗi và chờ callback khi cần. |
| Chỉ một subscriber không còn muốn nhận | `Subscription.cancel()`, tự quản lý điểm hoàn tất của tác vụ bị hủy. |
| Muốn xử lý item qua hàm đơn giản | `consume(consumer)` và chờ `CompletableFuture`. |
| Cần biết tất cả subscriber hoàn tất | Latch/future theo từng subscriber và phối hợp ở owner. |
| Có pool riêng cho delivery | Sau khi hoàn tất, owner gọi `shutdown` rồi `awaitTermination`. |
| Executor dùng chung nhiều publisher | Chỉ owner chung shutdown sau khi các thành phần hoàn tất. |
| Hệ thống buộc dừng ngay | Có thể `shutdownNow` hoặc cancel có kiểm soát; chấp nhận và báo cáo công việc có thể chưa hoàn tất. |

## 14. Bài tập tự kiểm tra

**Câu 1:** Gọi `publisher.close()` xong, `publisher.isClosed()` trả `true`. Có thể khẳng định subscriber đã chạy `onComplete()` không?  
**Đáp:** Không. Callback được phát bất đồng bộ, cần completion signal riêng nếu phải đợi.

**Câu 2:** `closeExceptionally(new IOException("failed"))` khác `close()` thế nào?  
**Đáp:** Nó phát `onError` với exception cho subscriber, còn `close()` phát `onComplete` khi hết dữ liệu bình thường.

**Câu 3:** Ứng dụng tạo `ExecutorService` rồi đưa vào constructor `SubmissionPublisher`. Đóng publisher có shutdown executor đó không?  
**Đáp:** Không. Owner executor quản lý shutdown riêng.

**Câu 4:** Chờ `CountDownLatch` trong chính single-thread delivery executor có nguy cơ gì?  
**Đáp:** Deadlock nếu callback cần đếm latch cũng chỉ có thể chạy trên executor đang bị chiếm.

**Câu 5:** Publisher gọi `close` trong lúc một producer khác `submit`. Điều gì có thể xảy ra?  
**Đáp:** Producer kia có thể nhận `IllegalStateException` khi publisher đã đóng; cần điều phối lifecycle giữa producer threads.

**Câu 6:** Subscriber gọi `cancel()` thì có chắc nhận `onComplete` không?  
**Đáp:** Không. Cancel là yêu cầu hủy best effort, không phải terminal signal.

**Câu 7:** `onComplete` có đồng nghĩa không item nào bị drop trước đó không?  
**Đáp:** Không. Chính sách `offer` có thể đã drop item; completion chỉ báo không còn item mới cho subscription đó.

**Câu 8:** Nếu publisher dùng `ForkJoinPool.commonPool()` mặc định, sau khi `close` có nên gọi `commonPool().shutdownNow()` không?  
**Đáp:** Không. Common pool là tài nguyên chia sẻ của JVM, không phải executor riêng của publisher.

**Ghi nhớ:** **Đóng publisher → chờ tín hiệu kết thúc → shutdown executor thuộc quyền sở hữu** là ba trách nhiệm riêng. `close()` và `closeExceptionally()` quyết định cách kết thúc luồng; `onComplete`/`onError` xác nhận kết quả ở subscriber; owner executor bảo đảm tài nguyên delivery được giải phóng đúng thời điểm.

## Tài liệu tham khảo chính thức

- [Oracle Java 21 API — SubmissionPublisher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html)
- [Oracle Java 21 API — Flow.Subscriber](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html)
- [Oracle Java 21 API — Flow.Subscription](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html)
- [Oracle Java 21 API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Oracle Java 21 API — CompletableFuture](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
