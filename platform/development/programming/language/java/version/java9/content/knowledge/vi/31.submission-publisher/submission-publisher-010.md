# Đóng publisher và executor theo quyền sở hữu trong Flow

## Mục tiêu

Flow API của Java 9 cho phép một `Publisher` phát dữ liệu bất đồng bộ đến các `Subscriber`. Khi dùng `SubmissionPublisher`, ứng dụng thường truyền vào một `Executor` để thực thi các callback như `onNext`, `onError` và `onComplete`.

Hai đối tượng này có vòng đời khác nhau:

- **Publisher** quản lý luồng dữ liệu và các Subscription đang đăng ký.
- **Executor** quản lý thread và các tác vụ được gửi để phân phối dữ liệu.

Đóng publisher không đồng nghĩa với tắt executor. Ngược lại, tắt executor quá sớm có thể khiến callback của subscriber chưa được thực thi. Cần đóng từng tài nguyên theo đúng quyền sở hữu và đúng thứ tự.

## 1. Phân biệt publisher, subscription và executor

| Thành phần | Trách nhiệm | Cách kết thúc |
|---|---|---|
| `SubmissionPublisher<T>` | Phát dữ liệu, đệm phần tử và gửi tín hiệu đến subscriber | `close()` hoặc `closeExceptionally(error)` |
| `Flow.Subscription` | Quản lý nhu cầu và việc nhận dữ liệu của một subscriber | `cancel()` |
| `ExecutorService` | Chạy các tác vụ phân phối và callback bất đồng bộ | `shutdown()`, chờ `awaitTermination()`, khi cần thì `shutdownNow()` |

`Flow.Publisher` chỉ định nghĩa giao thức đăng ký và phát dữ liệu; interface này không có phương thức `close()`. `SubmissionPublisher` là một implementation cụ thể có hỗ trợ đóng publisher và triển khai `AutoCloseable`.

Một Subscription thuộc về một subscriber cụ thể. Gọi `cancel()` dừng việc nhận dữ liệu của subscription đó; thao tác này không đóng toàn bộ publisher và cũng không tắt executor.

## 2. Quyền sở hữu quyết định ai được đóng executor

Nguyên tắc quan trọng là thành phần tạo và sở hữu một tài nguyên chịu trách nhiệm kết thúc tài nguyên đó.

| Trường hợp | Thành phần có quyền đóng | Hành động |
|---|---|---|
| Ứng dụng tự tạo ExecutorService và truyền cho SubmissionPublisher | Ứng dụng tạo executor | Đóng publisher, sau đó shutdown executor |
| SubmissionPublisher dùng executor được inject từ service dùng chung | Service sở hữu executor | Publisher chỉ đóng publisher; service quản lý executor |
| Nhiều publisher cùng dùng một executor | Thành phần quản lý executor chung | Mỗi publisher đóng phần publisher của mình; không publisher nào tự tắt executor chung |
| Dùng executor dùng chung của runtime, chẳng hạn common pool | Runtime | Không tự shutdown hoặc shutdownNow executor dùng chung |

Ví dụ một publisher nhận executor được quản lý ở cấp ứng dụng:

~~~java
ExecutorService sharedExecutor =
        Executors.newFixedThreadPool(4);

SubmissionPublisher<Integer> publisher =
        new SubmissionPublisher<>(sharedExecutor, 64);
~~~

Khi publisher không còn phát dữ liệu, có thể gọi `publisher.close()`. Không gọi `sharedExecutor.shutdown()` nếu các thành phần khác vẫn cần executor đó.

`SubmissionPublisher` sử dụng executor được truyền vào để phân phối dữ liệu, nhưng không nhận quyền sở hữu vòng đời của executor. Vì vậy, đóng publisher không tự động tắt executor do ứng dụng cung cấp.

## 3. Đóng publisher bình thường bằng close()

Khi producer đã gửi xong dữ liệu và không còn phần tử nào cần submit, gọi:

~~~java
publisher.close();
~~~

`close()` đánh dấu publisher đã đóng bình thường. Các subscriber hiện tại sẽ nhận các phần tử đã được submit theo demand, sau đó nhận tín hiệu `onComplete()`.

Một số điểm cần nhớ:

- Gọi close khi producer đã hoàn tất việc submit dữ liệu.
- Sau khi publisher đóng, không submit thêm phần tử mới; thao tác submit tiếp theo sẽ thất bại.
- close không có nghĩa mọi callback đã chạy xong ngay khi phương thức trả về.
- Nếu subscriber chưa yêu cầu đủ phần tử đang được đệm, việc chuyển đến tín hiệu kết thúc có thể còn phải chờ subscriber tiêu thụ dữ liệu.
- `isClosed()` kiểm tra trạng thái đóng của publisher, không chứng minh rằng mọi callback đã hoàn tất.

Nếu ứng dụng cần biết subscriber đã xử lý xong tín hiệu kết thúc, hãy phối hợp bằng latch, future hoặc cơ chế xác nhận riêng trong `onComplete()`.

## 4. Kết thúc bất thường bằng closeExceptionally()

Nếu producer không thể tiếp tục vì lỗi, có thể đóng publisher bất thường:

~~~java
try {
    publishData();
} catch (RuntimeException error) {
    publisher.closeExceptionally(error);
}
~~~

Publisher sẽ kết thúc bất thường và thông báo lỗi cho các subscriber qua `onError(error)` theo giao thức của implementation.

Phân biệt:

| Phương thức | Ý nghĩa | Tín hiệu kết thúc |
|---|---|---|
| `close()` | Kết thúc luồng bình thường | `onComplete()` |
| `closeExceptionally(error)` | Kết thúc luồng do lỗi | `onError(error)` |
| `Subscription.cancel()` | Một subscriber không muốn nhận thêm dữ liệu | Không yêu cầu publisher phát `onComplete()` cho subscriber đó |

Không dùng `cancel()` để báo rằng producer đã phát xong dữ liệu cho tất cả subscriber. Cũng không dùng `closeExceptionally()` cho một lần kết thúc bình thường.

## 5. Đóng ExecutorService theo thứ tự an toàn

Với executor do ứng dụng sở hữu, trình tự thường dùng là:

1. Dừng producer để không còn công việc mới gửi vào publisher.
2. Gọi `publisher.close()` hoặc `closeExceptionally(error)`.
3. Nếu cần xác nhận subscriber đã nhận tín hiệu cuối, chờ `onComplete()` hoặc `onError()`.
4. Gọi `executor.shutdown()` để từ chối tác vụ mới nhưng cho các tác vụ đã nhận tiếp tục chạy.
5. Gọi `awaitTermination(timeout, unit)` để chờ executor kết thúc.
6. Nếu hết thời gian, gọi `shutdownNow()` để yêu cầu dừng khẩn cấp và interrupt các tác vụ đang chạy trong khả năng của executor.

Ví dụ helper:

~~~java
static void shutdownAndAwait(ExecutorService executor) {
    executor.shutdown();

    try {
        if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
            executor.shutdownNow();

            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Executor did not terminate");
            }
        }
    } catch (InterruptedException error) {
        executor.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

Các phương thức có ý nghĩa khác nhau:

- `shutdown()` bắt đầu orderly shutdown; tác vụ đã gửi được phép hoàn tất.
- `awaitTermination()` chờ executor kết thúc sau khi shutdown.
- `shutdownNow()` cố gắng dừng tác vụ đang chạy bằng interrupt và trả về các tác vụ đang chờ chưa bắt đầu.

`shutdownNow()` chỉ là yêu cầu dừng best-effort. Tác vụ không phản hồi interrupt vẫn có thể tiếp tục chạy. Vì vậy, code xử lý I/O hoặc vòng lặp dài nên có cơ chế hủy hợp tác và kiểm tra trạng thái interrupt.

Nếu thread bị interrupt trong lúc chờ, hãy dọn dẹp executor và khôi phục cờ interrupt bằng `Thread.currentThread().interrupt()`; không âm thầm nuốt InterruptedException.

## 6. Vì sao phải đóng publisher trước khi shutdown executor?

SubmissionPublisher dùng executor để gửi callback đến subscriber. Nếu executor bị shutdown trước khi publisher hoàn thành việc phân phối, các tác vụ callback có thể bị từ chối hoặc không được thực thi theo kế hoạch.

Trình tự an toàn khi ứng dụng sở hữu cả hai tài nguyên:

~~~text
Producer hoàn tất submit
        |
        v
publisher.close()
        |
        v
Subscriber xử lý dữ liệu còn lại
        |
        v
Subscriber nhận onComplete / onError
        |
        v
executor.shutdown()
        |
        v
executor.awaitTermination(timeout)
        |
        +----> Hoàn tất: tài nguyên đã dừng
        |
        +----> Hết hạn: executor.shutdownNow()
~~~

Không nhất thiết phải chờ callback terminal trong mọi kiến trúc, nhưng nếu ứng dụng cần bảo đảm subscriber đã xử lý xong trước khi kết thúc service, hãy chờ một tín hiệu hoàn tất rõ ràng.

Một executor đã shutdown vẫn có thể hoàn tất các tác vụ đã được chấp nhận trước đó. Tuy nhiên, chờ terminal callback trước khi shutdown làm cho thứ tự vòng đời dễ kiểm soát và dễ kiểm thử hơn.

## 7. Theo dõi tín hiệu kết thúc của Subscriber

Subscriber có thể dùng `CountDownLatch` để thông báo rằng callback terminal đã chạy:

~~~java
CountDownLatch terminal = new CountDownLatch(1);

Flow.Subscriber<Integer> subscriber = new Flow.Subscriber<>() {
    @Override
    public void onSubscribe(Flow.Subscription subscription) {
        subscription.request(Long.MAX_VALUE);
    }

    @Override
    public void onNext(Integer item) {
        process(item);
    }

    @Override
    public void onError(Throwable error) {
        try {
            logFailure(error);
        } finally {
            terminal.countDown();
        }
    }

    @Override
    public void onComplete() {
        try {
            logCompletion();
        } finally {
            terminal.countDown();
        }
    }
};
~~~

Sau khi gọi `publisher.close()`, thread quản lý có thể chờ:

~~~java
if (!terminal.await(5, TimeUnit.SECONDS)) {
    throw new IllegalStateException("Subscriber did not terminate");
}
~~~

Trong ví dụ này Subscriber yêu cầu `Long.MAX_VALUE` nên có demand để nhận các phần tử đang được đệm. Nếu Subscriber chỉ request một phần tử rồi dừng, publisher có thể chưa thể gửi `onComplete()` cho đến khi phần tử còn lại được tiêu thụ hoặc subscription bị hủy.

Không chờ terminal callback nếu Subscriber đã bị cancel và giao thức của luồng không còn gửi callback đó. Với nhiều subscriber, cần theo dõi tín hiệu kết thúc của từng subscriber nếu ứng dụng yêu cầu tất cả đều xử lý xong.

## 8. Ví dụ hoàn chỉnh: đóng publisher rồi đóng executor do ứng dụng sở hữu

Tệp `FlowResourceLifecycleDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class FlowResourceLifecycleDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        SubmissionPublisher<Integer> publisher =
                new SubmissionPublisher<>(executor, 8);
        CountDownLatch terminal = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        try {
            publisher.subscribe(new Flow.Subscriber<Integer>() {
                @Override
                public void onSubscribe(Flow.Subscription subscription) {
                    subscription.request(Long.MAX_VALUE);
                }

                @Override
                public void onNext(Integer item) {
                    System.out.println("item: " + item);
                }

                @Override
                public void onError(Throwable error) {
                    failure.set(error);
                    terminal.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("publisher complete");
                    terminal.countDown();
                }
            });

            publisher.submit(10);
            publisher.submit(20);

            // Producer đã gửi xong dữ liệu.
            publisher.close();

            if (!terminal.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Subscriber did not finish");
            }

            if (failure.get() != null) {
                throw new IllegalStateException(
                        "Subscriber failed", failure.get());
            }

            System.out.println("publisher closed: " + publisher.isClosed());
            System.out.println(
                    "executor shut down by publisher: " + executor.isShutdown());
        } catch (RuntimeException | Error error) {
            if (!publisher.isClosed()) {
                publisher.closeExceptionally(error);
            }
            throw error;
        } finally {
            if (!publisher.isClosed()) {
                publisher.close();
            }

            // Executor được main tạo nên main chịu trách nhiệm shutdown.
            shutdownAndAwait(executor);
        }

        System.out.println("executor terminated: " + executor.isTerminated());
    }

    private static void shutdownAndAwait(ExecutorService executor) {
        executor.shutdown();

        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();

                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    System.err.println("Executor did not terminate");
                }
            }
        } catch (InterruptedException error) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 9 trở lên:

~~~bash
javac --release 9 -Xlint:all FlowResourceLifecycleDemo.java
java FlowResourceLifecycleDemo
~~~

Kết quả chuẩn:

~~~text
item: 10
item: 20
publisher complete
publisher closed: true
executor shut down by publisher: false
executor terminated: true
~~~

Kết quả cho thấy publisher đã đóng và subscriber nhận `onComplete()`, nhưng executor vẫn chưa shutdown ngay sau khi publisher đóng. Sau đó main gọi helper để shutdown executor do chính main sở hữu và chờ executor kết thúc.

## 9. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nghĩ `publisher.close()` tự shutdown executor | Publisher và executor có vòng đời độc lập | Chủ sở hữu executor tự shutdown |
| Shutdown executor trước khi publisher đóng | Callback phân phối có thể chưa được gửi hoặc thực thi xong | Đóng publisher trước, rồi mới kết thúc executor |
| Gọi `shutdown()` rồi giả định thread đã dừng | shutdown chỉ bắt đầu quá trình kết thúc | Chờ bằng awaitTermination |
| Chỉ gọi awaitTermination mà chưa shutdown | Executor vẫn nhận công việc mới | Gọi shutdown trước khi chờ |
| Gọi shutdownNow ngay trong đường chạy bình thường | Có thể ngắt callback hoặc tác vụ đang xử lý | Ưu tiên orderly shutdown và chỉ force khi timeout |
| Đóng executor dùng chung từ một publisher | Các publisher hoặc service khác mất executor | Chỉ chủ sở hữu executor chung được shutdown |
| Chỉ gọi `Subscription.cancel()` và nghĩ publisher đã đóng | Cancel chỉ áp dụng cho một đăng ký | Chủ sở hữu publisher gọi close hoặc closeExceptionally |
| Chờ onComplete sau khi subscription đã cancel | Cancel không yêu cầu gửi terminal callback như close bình thường | Quản lý trạng thái cancel riêng |
| Nghĩ isClosed() nghĩa là callback đã hoàn tất | isClosed chỉ phản ánh trạng thái publisher | Chờ latch/future từ callback terminal |
| Bỏ qua InterruptedException khi chờ executor | Mất tín hiệu yêu cầu dừng thread | Shutdown khẩn cấp và khôi phục interrupt flag |
| Để producer tiếp tục submit sau close | Publisher đã ngừng nhận phần tử mới | Dừng producer và phối hợp trước khi close |

## 10. Checklist quản lý vòng đời

- Xác định ai tạo và sở hữu publisher.
- Xác định executor là riêng hay dùng chung/inject từ service.
- Chỉ chủ sở hữu mới shutdown executor.
- Dừng producer trước khi đóng publisher.
- Dùng `close()` cho kết thúc bình thường và `closeExceptionally()` khi có lỗi.
- Theo dõi `onComplete()` hoặc `onError()` nếu cần xác nhận subscriber đã kết thúc.
- Đóng publisher trước khi shutdown executor dùng riêng.
- Gọi shutdown rồi awaitTermination; chỉ dùng shutdownNow khi hết thời hạn hoặc cần dừng khẩn cấp.
- Khôi phục interrupt flag khi xử lý InterruptedException.
- Không shutdown common pool hoặc executor do thành phần khác quản lý.
- Dùng cancel cho một Subscription; dùng close cho vòng đời publisher.
- Không coi isClosed() là bằng chứng mọi callback đã hoàn tất.

Flow yêu cầu quản lý riêng vòng đời của publisher, subscription và executor. Khi đóng publisher trước, chờ các subscriber hoàn tất nếu cần, rồi shutdown executor đúng chủ sở hữu, ứng dụng có thể kết thúc luồng dữ liệu mà không làm mất callback hoặc tắt nhầm tài nguyên dùng chung.