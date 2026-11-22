# Hủy subscription và giải phóng tài nguyên trong Java Flow

## 1. Vì sao hủy subscription là một phần của backpressure?

Trong Java, `java.util.concurrent.Flow` định nghĩa mô hình Publisher–Subscriber để trao đổi dữ liệu bất đồng bộ có điều tiết lưu lượng (*backpressure*). Một `Flow.Subscriber<T>` nhận đối tượng `Flow.Subscription` trong `onSubscribe`, rồi gọi `request(n)` để xin nhận tối đa `n` phần tử tiếp theo. Khi không còn nhu cầu tiêu thụ, subscriber có thể gọi `cancel()` để ngừng đăng ký.

Hủy subscription giải quyết **quyền tiếp tục nhận dữ liệu của một subscriber**. Giải phóng tài nguyên giải quyết **vòng đời của các đối tượng và công việc phục vụ luồng dữ liệu**: tác vụ đang chạy, bộ đệm, luồng I/O, socket, timer, executor, tệp mở, kết nối và các đối tượng giữ tham chiếu. Hai việc có liên quan nhưng không tự động thay thế cho nhau.

Ví dụ: màn hình theo dõi tiến trình đã đóng thì subscriber không cần nhận thông báo mới. Gọi `subscription.cancel()` là cần thiết; nếu chương trình còn có tác vụ đọc file theo chu kỳ và executor riêng thì thành phần sở hữu chúng vẫn phải dừng và đóng chúng.

**Mục tiêu học tập**

- Biết khi nào và ở đâu gọi `cancel()`, kể cả hủy do người dùng rời màn hình, timeout, đạt đủ số bản ghi, hoặc hệ thống dừng.
- Hiểu tính *best effort* của `cancel()`, sự khác nhau giữa hủy và tín hiệu kết thúc `onComplete`/`onError`.
- Xác định ai sở hữu tài nguyên để đóng đúng nơi, đúng thời điểm và chỉ một lần.
- Viết subscriber Java 17+ có kiểm soát demand, hủy chủ động và không treo khi chờ sự kiện hoàn tất.

## 2. Vai trò và vòng đời trong `Flow`

| Thành phần | Trách nhiệm liên quan đến hủy và tài nguyên |
| --- | --- |
| `Flow.Publisher<T>` | Phát dữ liệu theo demand; quản lý nguồn dữ liệu, hàng đợi hoặc tác vụ do chính publisher tạo; phải phản ứng phù hợp khi subscriber hủy. |
| `Flow.Subscriber<T>` | Nhận `onSubscribe`, giữ `Subscription`, gọi `request`/`cancel` và xử lý `onNext`, `onError`, `onComplete`. |
| `Flow.Subscription` | Liên kết **một** subscriber với publisher; quản lý demand và hủy liên kết đó. |
| `Flow.Processor<T,R>` | Vừa là subscriber phía upstream vừa là publisher phía downstream; phải thiết kế cách truyền tín hiệu hủy và dọn tài nguyên ở cả hai phía. |

Một vòng đời điển hình:

```text
subscribe(subscriber)
    |
    v
onSubscribe(subscription)
    |
    +-- request(n > 0) --> onNext(item) ... --> request(thêm)
    |                                           |
    |                                           +--> onComplete()
    |                                           +--> onError(error)
    |
    +-- cancel() ------> hủy đăng ký; không cần có tín hiệu terminal
```

Điểm cần phân biệt:

1. `request(n)` làm tăng lượng cầu chưa được đáp ứng; `n > 0`. Theo hợp đồng Flow, `request(n <= 0)` dẫn đến `onError(IllegalArgumentException)`.
2. `cancel()` yêu cầu publisher **cuối cùng** dừng gửi thông điệp cho subscriber đó. Nó là hành động *best effort*: khi có cạnh tranh giữa các luồng, vẫn có thể nhận thêm thông điệp sau lời gọi.
3. Sau `cancel()`, **không được chờ `onComplete()` hay `onError()` như một bảo đảm**. Hủy không phải là một tín hiệu kết thúc bình thường.
4. `onComplete()` là nguồn dữ liệu kết thúc bình thường; `onError(Throwable)` là kết thúc do lỗi. Cả hai kết thúc dòng tín hiệu cho subscription; chúng không đồng nghĩa với việc mọi tài nguyên phụ trợ đã được đóng.
5. Một publisher có thể phục vụ nhiều subscriber. Hủy **một** subscription không mặc nhiên đóng publisher hoặc hủy subscription của các consumer khác.

Trong ứng dụng thực tế, nên mô hình hóa tối thiểu các trạng thái: **đang hoạt động → đang hủy/đã hủy** hoặc **đã kết thúc**. Một cờ trạng thái nguyên tử giúp việc dọn dẹp lặp lại và các cuộc đua đồng thời an toàn hơn.

## 3. Khi nào hủy và điều gì không được giả định?

Hãy hủy khi không còn lý do để nhận thêm phần tử: người dùng đóng phiên theo dõi, đạt đủ mẫu, đạt deadline, lỗi trong khâu xử lý khiến tiếp tục nhận dữ liệu không có ý nghĩa, hoặc thành phần sở hữu subscriber chuẩn bị đóng.

Đừng sử dụng `cancel()` như một cơ chế ngắt tức thời tuyệt đối. Publisher có thể đã phát một item; callback `onNext` có thể đang xử lý hoặc đã được xếp lịch. Với luồng concurrent, thứ tự quan sát giữa thao tác hủy và callback đang chạy phụ thuộc vào triển khai và đồng bộ hóa của ứng dụng. Vì vậy:

- Đánh dấu trạng thái hủy trước hoặc khi gọi `cancel()`; callback đến trễ nên kiểm tra trạng thái trước khi tạo tác dụng phụ mới.
- Không gọi `request(1)` tiếp nếu đã quyết định hủy.
- Nếu callback còn sử dụng một file/socket/resource, **đừng đóng resource giữa chừng** mà không có cơ chế phối hợp. Dùng lock, bộ đếm tác vụ đang xử lý, hoặc giao thức chờ xử lý xong rồi mới đóng.
- Nếu thời điểm đóng phải có giới hạn, dùng timeout khi chờ tác vụ thoát và xác định chính sách xử lý phần việc còn dở.
- Cần phân biệt “đã yêu cầu hủy” với “mọi công việc thực sự đã dừng”. Nếu cần chờ điều kiện thứ hai, ứng dụng phải có tín hiệu phối hợp riêng như `CountDownLatch`, `Future` hoặc một completion stage.

Không có API chung của `Flow.Subscription` để “await cancelled”. `cancel()` cũng không có `boolean` trả về cho biết đã giải phóng xong tài nguyên.

## 4. Ví dụ chạy được: subscriber tự hủy sau ba phần tử

Ví dụ sử dụng `SubmissionPublisher<Integer>` có sẵn trong Java, thay vì tự viết một publisher đầy đủ. Subscriber yêu cầu từng phần tử một; sau phần tử thứ ba, nó hủy. `CountDownLatch` là tín hiệu **do ứng dụng chủ động phát ra lúc hủy**, chứ không phải do Flow tự gửi `onComplete`.

Tạo file `CancelAfterThree.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class CancelAfterThree {
    static final class FirstThreeSubscriber implements Flow.Subscriber<Integer> {
        private final CountDownLatch stopped;
        private Flow.Subscription subscription;
        private int received;
        private boolean cancelled;

        FirstThreeSubscriber(CountDownLatch stopped) {
            this.stopped = stopped;
        }

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            subscription.request(1);
        }

        @Override
        public void onNext(Integer value) {
            if (cancelled) {
                return; // Bỏ qua tín hiệu đến trễ sau khi đã hủy.
            }

            System.out.println("Nhận: " + value);
            received++;

            if (received == 3) {
                cancelled = true;
                subscription.cancel();
                System.out.println("Đã hủy subscription");
                stopped.countDown();
            } else {
                subscription.request(1);
            }
        }

        @Override
        public void onError(Throwable error) {
            System.err.println("Lỗi: " + error);
            stopped.countDown();
        }

        @Override
        public void onComplete() {
            System.out.println("Publisher hoàn tất");
            stopped.countDown();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch stopped = new CountDownLatch(1);

        try (SubmissionPublisher<Integer> publisher = new SubmissionPublisher<>()) {
            publisher.subscribe(new FirstThreeSubscriber(stopped));

            for (int i = 1; i <= 5; i++) {
                publisher.submit(i);
            }

            if (!stopped.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Chờ subscriber quá lâu");
            }
        } // Đóng publisher tại nơi sở hữu publisher.
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac CancelAfterThree.java
java CancelAfterThree
```

Khi chương trình chạy bình thường, output:

```text
Nhận: 1
Nhận: 2
Nhận: 3
Đã hủy subscription
```

**Giải thích từng điểm quan trọng:**

1. `onSubscribe` nhận subscription rồi xin `request(1)`, cho phép publisher gửi một phần tử. Sau mỗi phần tử được giữ lại, subscriber xin thêm đúng một phần tử; đây là backpressure ở mức đơn giản.
2. Khi `received == 3`, subscriber đặt `cancelled = true` rồi gọi `subscription.cancel()`; nó không xin thêm phần tử. Các item `4` và `5` đã được gửi vào publisher không đồng nghĩa sẽ tiếp tục được giao cho subscription đã hủy.
3. `SubmissionPublisher` giao callback bất đồng bộ và giữ đúng thứ tự phần tử trong ví dụ này. `CountDownLatch` giúp main đợi đến lúc subscriber đã thực hiện yêu cầu hủy, thay vì thoát ngay khi gọi `submit`.
4. Vì callback của **một subscription** được gửi theo thứ tự, cờ `cancelled` trong ví dụ nhỏ này chỉ được truy cập từ chuỗi callback đó. Trong ứng dụng hủy từ một luồng khác, cần `AtomicBoolean` hoặc đồng bộ hóa tương đương.
5. `try-with-resources` đóng `SubmissionPublisher` khi rời khối. Nó là bước dọn dẹp **publisher**, khác với việc subscriber vừa hủy đăng ký. Publisher mặc định dùng `ForkJoinPool.commonPool()`; không được gọi shutdown trên common pool chỉ vì đóng publisher.
6. Sau khi hủy, ví dụ **không** chờ `onComplete`. Nếu bỏ `stopped.countDown()` trong nhánh hủy, chương trình có thể chờ mãi hoặc hết timeout dù `cancel()` đã hoạt động đúng.

Ví dụ trên giả định không có lỗi hệ thống và executor còn nhận nhiệm vụ. `await(5, ...)` bảo vệ việc chờ; thời gian 5 giây là timeout trình diễn, không phải cam kết hiệu năng của `Flow`.

## 5. Phân biệt `cancel()`, đóng publisher và đóng tài nguyên ứng dụng

| Thao tác | Phạm vi và ý nghĩa | Có tự động dọn mọi tài nguyên không? |
| --- | --- | --- |
| `subscription.cancel()` | Yêu cầu dừng gửi dữ liệu cho **subscription cụ thể**. | Không. Không buộc đóng publisher, executor, kết nối hay resource mà caller sở hữu. |
| `publisher.close()` với `SubmissionPublisher` | Ngừng nhận item mới; gửi `onComplete` bất đồng bộ đến subscriber còn hoạt động. | Chỉ theo quy ước của publisher đó. Không bảo đảm callback đã hoàn tất khi `close()` trả về. |
| `publisher.closeExceptionally(error)` | Đóng publisher, phát `onError(error)` đến các subscriber còn hoạt động. | Không thay thế việc đóng resource ngoài publisher. |
| `executor.shutdown()` hoặc `shutdownNow()` | Bắt đầu dừng executor do ứng dụng sở hữu; `shutdownNow` chỉ cố gắng ngắt nhiệm vụ. | Phải phối hợp với task và giới hạn thời gian; không bảo đảm task dừng tức thì. |
| `resource.close()` | Giải phóng tài nguyên `AutoCloseable` như stream/kết nối theo giao ước của resource. | Chỉ dọn chính resource đó; không tự quyết định trạng thái subscription. |

Ví dụ một subscriber có reader và một publisher dùng executor riêng:

```text
Tài nguyên được tạo ở đâu?       Người chịu trách nhiệm đóng
-----------------------------    ----------------------------------------
Subscription nhận trong onSubscribe  Subscriber gọi cancel khi hết nhu cầu
SubmissionPublisher tạo tại main      main/service owner gọi close
ExecutorService tạo tại main          main/service owner shutdown và await
InputStream mở trong source adapter   source adapter đóng sau khi callback/tác vụ an toàn
Timer do component tự tạo             component hủy timer và đóng scheduler
```

**Quy tắc sở hữu:** thành phần tạo resource hoặc nhận trách nhiệm sở hữu rõ ràng mới quyết định khi nào đóng. Nếu một executor được chia sẻ cho nhiều publisher/subscriber, hủy một consumer tuyệt đối không được đóng executor chung.

Nếu một `Flow.Processor` trung gian bị hủy ở phía downstream, việc có hủy upstream ngay hay không tùy thiết kế pipeline: có thể còn downstream khác hoặc xử lý công việc chung. Không suy ra tự động rằng hủy ở một đầu sẽ dọn toàn bộ chuỗi.

## 6. Dọn dẹp một lần, kể cả khi lỗi hoặc hủy đồng thời

Trong hệ thống có callback, timeout và yêu cầu dừng từ người dùng, nhiều đường thực thi có thể cùng cố dọn resource: `cancel()`, `onError()`, `onComplete()`, `close()` của service. Mẫu cần áp dụng là **idempotent cleanup**: dù gọi nhiều lần, một resource chỉ được thực hiện quy trình đóng một lần.

Đoạn sau chỉ **minh họa phương thức dọn dẹp bên trong một component** đã khai báo các trường `subscription`, `task`, `ownedExecutor` và `closed`; đây không phải chương trình độc lập:

```java
private final java.util.concurrent.atomic.AtomicBoolean closed =
        new java.util.concurrent.atomic.AtomicBoolean();

private volatile Flow.Subscription subscription;
private java.util.concurrent.Future<?> task;
private java.util.concurrent.ExecutorService ownedExecutor;

@Override
public void close() {
    if (!closed.compareAndSet(false, true)) {
        return; // Thành phần khác đã bắt đầu dọn dẹp.
    }

    Flow.Subscription current = subscription;
    if (current != null) {
        current.cancel();
    }

    if (task != null) {
        task.cancel(true); // Chỉ yêu cầu ngắt; tác vụ phải hợp tác.
    }

    if (ownedExecutor != null) {
        ownedExecutor.shutdown(); // Chỉ khi component sở hữu executor.
    }
}
```

Trong component thật, phải bổ sung cách chờ các tác vụ đang sử dụng resource, chính sách timeout và cách xử lý lỗi khi gọi `close()`. `AtomicBoolean` ngăn dọn lặp nhưng **không tự giải quyết** mọi cuộc đua: chẳng hạn `close()` có thể đến trước `onSubscribe`, khi `subscription` vẫn `null`. Khi đó `onSubscribe` phải kiểm tra trạng thái đã đóng, hủy ngay subscription mới nhận và tuyệt đối không cấp thêm demand. Nếu khởi tạo resource xảy ra sau lúc bắt đầu dọn, cần phối hợp đồng bộ quá trình khởi tạo với đóng.

Đặc biệt, đừng dùng `cancel()` đơn độc để bảo đảm một thread đang thực thi `onNext` đã dừng trước khi socket hay file bị đóng. Thứ tự an toàn thường là: đánh dấu ngừng nhận việc mới → hủy subscription → ngăn task mới → đợi task đang sử dụng resource kết thúc (có giới hạn) → đóng resource → ghi nhận kết quả.

## 7. Thiết kế đường kết thúc cho mọi tình huống

Tùy thuộc ứng dụng, mỗi đường kết thúc cần một cách hoàn thành khác nhau:

| Tình huống | Xử lý subscription | Xử lý hoàn thành/dọn dẹp |
| --- | --- | --- |
| Nguồn phát hết dữ liệu | Subscriber nhận `onComplete`; không cần hủy thêm để dừng dữ liệu. | Dọn resource do subscriber sở hữu và báo hoàn tất cho service nếu cần. |
| Publisher phát lỗi | Subscriber nhận `onError`; kết thúc luồng đó. | Ghi nhận lỗi, dọn resource; quyết định retry là việc ở tầng điều phối. |
| Consumer tự dừng sớm | Subscriber chủ động gọi `cancel()`. | Phát tín hiệu hoàn tất **của ứng dụng**; không chờ `onComplete` từ Flow. |
| Deadline / người dùng đóng màn hình | Thành phần quản lý vòng đời yêu cầu hủy, dừng tác vụ liên quan. | Hợp nhất các đường cleanup bằng trạng thái nguyên tử, quản lý timeout. |
| Publisher/service shutdown | Chủ sở hữu đóng publisher và các resource do mình cấp phát. | Nếu cần chờ callback đã chạy xong, sử dụng công cụ phối hợp riêng. |
| `onNext` thất bại | Chính sách lỗi phụ thuộc publisher và cách xử lý callback. | Tránh ném lỗi vô kiểm soát; ghi nhận nguyên nhân, yêu cầu hủy và dọn resource thích hợp. |

Với `SubmissionPublisher`, nếu callback `onNext` ném ngoại lệ, subscription của subscriber đó bị hủy; nếu muốn ghi nhận lỗi và dọn resource riêng, phải xây dựng đường xử lý của chính ứng dụng. Không thể giả định `onError` của subscriber sẽ được gọi sau mọi ngoại lệ phát sinh trong chính `onNext`.

Nếu cần tự phát hiện timeout, deadline hoặc hết phiên, có thể dùng `ScheduledExecutorService` hay `Future` do service quản lý; hủy timer khi xử lý xong. Không nên tạo một luồng nền vô hạn mà không có đường tắt khi subscriber hủy.

## 8. Những lỗi thường gặp

1. **Nhầm hủy với hoàn tất:** gọi `cancel()` rồi chờ `onComplete` để giải phóng resource. Kết quả có thể bị treo. Hãy tự dọn sau khi yêu cầu hủy hoặc phát tín hiệu hoàn tất riêng.
2. **Nhầm phạm vi:** hủy một subscriber nhưng đóng publisher hoặc executor dùng chung, làm gián đoạn subscriber khác.
3. **Quên hủy tác vụ sinh dữ liệu:** subscription đã dừng nhưng vòng lặp đọc file, socket, timer hoặc job vẫn chạy và vẫn cấp phát dữ liệu. Publisher tùy biến cần nối yêu cầu hủy với cơ chế dừng nguồn đúng cách.
4. **Giải phóng quá sớm:** đóng resource khi `onNext` đang dùng nó. Cần đồng bộ hoặc giao thức đợi các callback/tác vụ đang chạy.
5. **Tin rằng hủy là tức thời:** vẫn có callback đến muộn; callback phải biết trạng thái dừng và tránh tạo tác dụng phụ ngoài ý muốn.
6. **Dọn dẹp không idempotent:** timeout và nhánh lỗi cùng đóng resource, gây race hoặc lỗi thứ cấp. Dùng một đường cleanup chung.
7. **Gọi `request(0)` để “tạm dừng”:** theo hợp đồng Flow, demand không dương là lỗi. Muốn tạm ngừng, đơn giản là chưa xin thêm demand; muốn dừng vĩnh viễn thì `cancel()`.
8. **Yêu cầu quá nhiều để né backpressure:** `request(Long.MAX_VALUE)` tương đương cầu gần như vô hạn; chỉ phù hợp khi consumer thực sự chịu được dữ liệu đến.
9. **Không quản lý trường hợp đóng trước khi đăng ký:** `onSubscribe` đến sau `close()` vẫn xin dữ liệu hoặc giữ subscription không bao giờ hủy.
10. **Đóng executor không thuộc quyền sở hữu:** shutdown một pool chia sẻ chỉ vì một luồng tiêu thụ kết thúc.

## 9. Checklist kiểm thử vòng đời

Để kiểm chứng một luồng Java Flow thực tế, nên có ít nhất các trường hợp sau:

- Subscriber nhận được `onSubscribe` rồi chủ động hủy trước khi xin item đầu tiên; không bắt buộc có `onComplete`/`onError`.
- Subscriber `request(1)`, nhận một item, hủy; kiểm tra không xử lý tác dụng phụ mới sau khi đã đánh dấu hủy, dù callback đến trễ.
- Hủy cùng lúc với `onNext` hoặc đồng thời với shutdown; tài nguyên không bị đóng khi còn callback đang sử dụng.
- Hủy/`close()` lặp nhiều lần; chỉ một lần giải phóng các resource được sở hữu.
- Lỗi xảy ra trong nguồn hoặc xử lý item; không bỏ sót logging, completion của service và cleanup.
- Publisher còn subscriber khác; hủy một subscriber không ảnh hưởng đến luồng còn lại.
- Timeout/đóng trước `onSubscribe`; subscription đến muộn được hủy ngay.
- Sau shutdown, không còn thread riêng, file descriptor, kết nối hoặc scheduled task bị giữ vô hạn.

Các bài test bất đồng bộ nên dùng `CountDownLatch`/`CompletableFuture` hoặc công cụ đồng bộ xác định; tránh kết luận bằng `Thread.sleep(...)` và các giả định timing mong manh.

## 10. Kết luận áp dụng

Trong Java Flow, `Subscription.cancel()` là lệnh **ngừng nhu cầu nhận dữ liệu của một subscriber**, không phải bảo đảm shutdown toàn bộ pipeline. Lệnh hủy có thể trễ, và subscription đã hủy không nhất thiết nhận tín hiệu terminal. Muốn quản lý vòng đời đúng, phải xác định resource owner, tạo đường cleanup một lần cho cả hủy/lỗi/hoàn tất, phối hợp với công việc đang chạy, và dùng tín hiệu riêng nếu service phải chờ dừng thực sự.

Tham khảo API chính thức:

- [`Flow.Subscription` (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html)
- [`Flow.Subscriber` (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html)
- [`SubmissionPublisher` (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html)