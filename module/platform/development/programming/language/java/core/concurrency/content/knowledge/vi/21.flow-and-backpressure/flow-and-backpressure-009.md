# Thread safety trong callback và xử lý lỗi với Java Flow API

> Phạm vi: Java SE (Java 17+), đặc biệt `java.util.concurrent.Flow` và `SubmissionPublisher`. Bài này không bàn về Spring hay các thư viện reactive của Spring.

## 1. Bài toán cần giải quyết

Trong mô hình Publisher–Subscriber, dữ liệu được chuyển qua các callback `onSubscribe`, `onNext`, `onError`, `onComplete`. Với `SubmissionPublisher`, callback thường được gọi bất đồng bộ trên các luồng do `Executor` quản lý. Vì vậy, một bộ tiêu thụ phải giải quyết đồng thời ba vấn đề:

1. **Trạng thái có an toàn giữa các luồng không?** Callback có thể cập nhật bộ đếm, danh sách, cache hoặc kết quả mà luồng khác đang đọc.
2. **Có tuân thủ giao thức tín hiệu không?** Mỗi subscription phải quản lý `request(n)`, `cancel()` và tín hiệu kết thúc đúng cách.
3. **Lỗi xảy ra ở đâu, ai chịu trách nhiệm?** Lỗi dữ liệu của một phần tử, lỗi phát sinh từ upstream và ngoại lệ ném ra khỏi callback có hệ quả khác nhau.

`Flow` giải quyết việc đặt hàng tín hiệu và điều khiển nhu cầu (demand); việc bảo vệ **trạng thái ứng dụng** và xác định **chính sách khôi phục lỗi** vẫn thuộc trách nhiệm lập trình viên.

## 2. Giao thức callback và ý nghĩa lỗi

| Phương thức | Ý nghĩa | Điều cần giữ |
| --- | --- | --- |
| `onSubscribe(Subscription s)` | Nhận quyền điều khiển subscription; gọi `s.request(n)` để yêu cầu phần tử | `n > 0`; lưu subscription theo đúng vòng đời |
| `onNext(T item)` | Xử lý một phần tử đã được yêu cầu | Không chia sẻ mutable state thiếu bảo vệ; xác định cách xử lý lỗi của phần tử |
| `onError(Throwable error)` | Nhận tín hiệu lỗi **kết thúc** từ publisher | Ghi nhận nguyên nhân, giải phóng tài nguyên, thông báo kết quả thất bại |
| `onComplete()` | Nhận tín hiệu **kết thúc thành công** | Hoàn tất kết quả, giải phóng tài nguyên, đánh thức luồng đang đợi |
| `Subscription.cancel()` | Yêu cầu ngừng phát cho subscriber | Việc hủy có thể không tức thì và **không bảo đảm** có thêm `onComplete/onError` |

Một subscription hợp lệ có chuỗi tín hiệu dạng:

```text
onSubscribe
    |
    +-- request(n > 0) --> onNext --> onNext --> ... --> onComplete
    |                                      \
    |                                       +-----> onError (nếu upstream thất bại)
    +-- cancel() --------> ngừng phát (best effort; có thể không có terminal signal)
```

`onError` và `onComplete` là hai kết thúc loại trừ nhau. Sau tín hiệu kết thúc, publisher không gửi thêm tín hiệu đến subscription đó. `request(0)` hoặc `request(n < 0)` vi phạm giao thức: `Subscription` phải dẫn đến `onError` với `IllegalArgumentException`. `cancel()` không phải lệnh đồng nghĩa với `onComplete()`.

## 3. Flow bảo đảm điều gì về thread safety?

### 3.1. Tín hiệu được tuần tự hóa **theo từng subscription**

Giao thức `Flow.Publisher` yêu cầu callback đến **cùng một subscription** được phát theo thứ tự có quan hệ *happens-before*. Bởi vậy, nếu cùng một subscriber chỉ có một subscription hợp lệ, không đưa trạng thái ấy ra luồng khác và không tạo tác vụ phụ cùng sửa trạng thái, các callback của nó có thể dùng biến nội bộ thông thường mà không cần khóa riêng chỉ để chống hai `onNext` đồng thời.

Tuy nhiên, **tuần tự không đồng nghĩa với cố định một thread**. Các callback kế tiếp có thể chạy trên các thread khác nhau; không dựa vào `ThreadLocal`, tên thread hay giả định “callback luôn nằm trên main thread”. Với `SubmissionPublisher`, việc chuyển giao phần tử thường được thực thi bất đồng bộ bởi `Executor`.

### 3.2. Những gì Flow *không* tự bảo vệ

- Hai subscriber/subscription khác nhau có thể chạy callback song song. Nếu cùng ghi vào một `ArrayList`, `HashMap` hoặc bộ đếm chung thì phải phối hợp truy cập.
- Luồng gọi `submit`, luồng giám sát metrics và callback có thể hoạt động đồng thời. Quy tắc tuần tự hóa callback không làm mọi thao tác trên trạng thái bên ngoài trở nên an toàn.
- Nếu `onNext` tạo thêm `CompletableFuture`, task trong pool hay thread mới, tác vụ phụ ấy có thể chạy song song với callback kế tiếp. Khi đó trạng thái chung cần cơ chế đồng bộ độc lập.
- Một thao tác gồm nhiều bước, chẳng hạn “kiểm tra còn quota rồi tăng số lượng”, không trở nên nguyên tử chỉ vì từng biến là `volatile`.

### 3.3. Chọn cơ chế bảo vệ theo loại dữ liệu

| Tình huống | Cách làm phù hợp | Lý do |
| --- | --- | --- |
| Trạng thái chỉ được đọc/ghi bên trong callback của một subscription | Biến thường, không chia sẻ ra ngoài | Tín hiệu đã tuần tự theo giao thức |
| Cờ trạng thái được một thread ghi và thread khác đọc | `volatile` hoặc `AtomicBoolean` | Bảo đảm nhìn thấy cập nhật; atomic cho thao tác như CAS |
| Bộ đếm đồng thời | `AtomicLong`, `LongAdder` tùy yêu cầu | Tránh mất cập nhật kiểu `count++` |
| Hai trường phải thỏa bất biến chung | `synchronized`/lock hoặc một immutable snapshot thay thế nguyên tử | Hai atomic riêng lẻ không tạo transaction |
| Danh sách/tập hợp cùng được sửa bởi nhiều callback | Bộ sưu tập concurrent phù hợp hoặc khóa | Tránh data race và hỏng cấu trúc |
| Luồng ngoài cần đợi kết thúc rồi đọc kết quả | `CountDownLatch`, `CompletableFuture` hoặc cơ chế chờ đồng bộ | Vừa chờ tín hiệu cuối, vừa có bảo đảm visibility |

Ví dụ `volatile long count` vẫn **không** làm `count++` trở thành phép tăng nguyên tử. `AtomicLong.incrementAndGet()` phù hợp cho một bộ đếm; nếu cần nhất quán giữa `accepted` và `rejected` ở thời điểm chụp báo cáo, cần cùng một khóa/snapshot.

## 4. Backpressure và callback phải đi cùng nhau

Subscriber nhận phần tử theo **demand** đã cấp bằng `request(n)`. Một cách dễ hiểu và dễ kiểm chứng là chỉ giữ tối đa một yêu cầu chưa hoàn thành:

1. Trong `onSubscribe`, gọi `request(1)`.
2. Trong `onNext`, xử lý xong phần tử.
3. Nếu tiếp tục thì gọi `request(1)` để xin phần tử kế tiếp.

Cách này đơn giản nhưng có overhead cho mỗi phần tử; pipeline throughput cao thường cấp theo batch và bổ sung demand theo ngưỡng. **Demand không có nghĩa publisher không bao giờ buffer**: `SubmissionPublisher` có bộ đệm riêng cho từng subscriber. `submit(item)` có thể chặn khi không còn dung lượng; `offer(...)` có thể rơi phần tử theo chính sách được cấu hình. Không dùng số liệu ước lượng lag/demand như primitive đồng bộ hóa.

Tránh khóa quá rộng hoặc thực hiện I/O chậm trong `onNext`: điều này làm downstream trả demand chậm và có thể khiến upstream bị backpressure. Đặc biệt, không giữ khóa của trạng thái ứng dụng trong khi gọi hàm bên ngoài có thể gọi ngược/reentrant như `request`, `cancel`, logger tùy biến hoặc callback do người khác cung cấp.

## 5. Phân biệt ba lớp lỗi

| Lỗi | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **Lỗi phần tử, có thể phục hồi** | Một giá trị âm không được phép | `onNext` bắt ngoại lệ dự kiến, ghi nhận/bỏ qua hoặc chuyển sang luồng xử lý lỗi, rồi cấp demand tiếp theo theo chính sách |
| **Lỗi upstream không thể tiếp tục** | Nguồn dữ liệu hỏng, không còn phát đúng được | Publisher phát `onError`; với `SubmissionPublisher`, gọi `closeExceptionally(cause)` |
| **Ngoại lệ thoát khỏi callback** | `onNext` ném `RuntimeException` không bắt | **Không** mặc định coi đây là `onError` của upstream; kiểm tra hợp đồng của publisher cụ thể. `SubmissionPublisher` hủy subscription nếu một phương thức subscriber ném ngoại lệ; handler tùy chọn của publisher có thể nhận ngoại lệ `onNext` trước khi hủy |

`SubmissionPublisher.close()` báo kết thúc bình thường qua `onComplete()`; `closeExceptionally(error)` báo kết thúc lỗi qua `onError(error)`. Nếu đã đóng, lời gọi đóng lại không tạo thêm một kết thúc mới.

Đối với lỗi nghiêm trọng ngay trong việc xử lý item, chọn chính sách rõ ràng: hủy subscription, báo thất bại qua một `CompletableFuture`/kênh trạng thái riêng và dọn tài nguyên. Vì hủy **không bắt buộc** phát terminal signal, không nên chỉ chờ `onError()` sau `cancel()` để kết thúc tác vụ ứng dụng. Với lỗi có thể bỏ qua, bắt **đúng loại ngoại lệ dự kiến**; không `catch(Throwable)` bừa bãi vì có thể nuốt các lỗi nghiêm trọng của JVM.

Trong `onError` và `onComplete`, làm thao tác dọn dẹp/hoàn tất đơn giản, có kiểm soát và tránh ném ngoại lệ. Nếu dọn dẹp có thể thất bại, ghi nhận lỗi riêng nhưng đừng biến đường kết thúc thành điểm phát sinh lỗi không được xử lý.

## 6. Ví dụ Java 17+: subscriber an toàn, backpressure và hai đường kết thúc

Lưu toàn bộ chương trình vào tệp **`SafeFlowCallbacks.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

public class SafeFlowCallbacks {
    static final class RecordingSubscriber implements Flow.Subscriber<Integer> {
        private final AtomicLong total = new AtomicLong();
        private final AtomicInteger skipped = new AtomicInteger();
        private final AtomicReference<Throwable> terminalError = new AtomicReference<>();
        private final CountDownLatch finished = new CountDownLatch(1);
        private Flow.Subscription subscription;

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            subscription.request(1);
        }

        @Override
        public void onNext(Integer item) {
            try {
                if (item < 0) {
                    throw new IllegalArgumentException("negative input: " + item);
                }
                total.addAndGet(item);
            } catch (IllegalArgumentException expected) {
                skipped.incrementAndGet();
            } finally {
                subscription.request(1);
            }
        }

        @Override
        public void onError(Throwable error) {
            terminalError.set(error);
            finished.countDown();
        }

        @Override
        public void onComplete() {
            finished.countDown();
        }

        void awaitTermination() throws InterruptedException {
            if (!finished.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out waiting for terminal signal");
            }
        }

        String report() {
            Throwable error = terminalError.get();
            String terminal = error == null ? "complete" : error.getClass().getSimpleName();
            return "total=" + total.get() + ", skipped=" + skipped.get()
                    + ", terminal=" + terminal;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        RecordingSubscriber success = new RecordingSubscriber();
        try (SubmissionPublisher<Integer> publisher = new SubmissionPublisher<>()) {
            publisher.subscribe(success);
            publisher.submit(10);
            publisher.submit(-7);
            publisher.submit(20);
        }
        success.awaitTermination();
        System.out.println("success: " + success.report());

        RecordingSubscriber failure = new RecordingSubscriber();
        try (SubmissionPublisher<Integer> publisher = new SubmissionPublisher<>()) {
            publisher.subscribe(failure);
            publisher.closeExceptionally(new IllegalStateException("source unavailable"));
        }
        failure.awaitTermination();
        System.out.println("failure: " + failure.report());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac SafeFlowCallbacks.java
java SafeFlowCallbacks
```

Kết quả stdout (đã kiểm tra trên JDK 21, code dùng API có trong Java 17):

```text
success: total=30, skipped=1, terminal=complete
failure: total=0, skipped=0, terminal=IllegalStateException
```

**Giải thích chi tiết:**

- `publisher.subscribe(success)` đăng ký subscriber; `onSubscribe` nhận `Subscription` và yêu cầu đúng một phần tử. Các `submit` có thể xảy ra trước khi callback thực thi nhưng publisher quản lý delivery/demand.
- Với `10` và `20`, `total.addAndGet` cập nhật tổng. `-7` gây `IllegalArgumentException` **do quy tắc nghiệp vụ của ví dụ**, được bắt trong `onNext`; callback không ném lỗi ra publisher, nên stream tiếp tục.
- `finally { subscription.request(1); }` ở đây thể hiện chính sách *tiếp tục sau lỗi dữ liệu đã kiểm soát*. Với lỗi không thể phục hồi, **không** dùng `finally` yêu cầu tiếp vô điều kiện; thay bằng nhánh hủy và tự đánh dấu kết thúc thất bại.
- `try-with-resources` gọi `SubmissionPublisher.close()` ở đường thành công; subscriber được gửi `onComplete` sau các phần tử đã phát hợp lệ.
- Đường thất bại không gửi item: `closeExceptionally` chuyển `IllegalStateException` qua `onError`. `total=0` và `skipped=0`.
- `AtomicLong`, `AtomicInteger`, `AtomicReference` cho phép đọc snapshot an toàn nếu cần quan sát từ thread khác khi stream đang chạy. Ví dụ cũng dùng `CountDownLatch` để chờ terminal signal trước khi in; các ghi xảy ra trước `countDown` được nhìn thấy sau `await` thành công.
- `subscription` là biến thường vì **chỉ callback của một subscription** truy cập nó trong ví dụ. Nếu thread bên ngoài được phép hủy trực tiếp, thiết kế thêm cơ chế công bố subscription an toàn, ví dụ `AtomicReference<Flow.Subscription>`, và phối hợp trạng thái cancel/termination.

Lưu ý giới hạn minh họa: bộ đếm atomic bảo vệ từng phép cập nhật, nhưng không đảm bảo một ảnh chụp nhiều chỉ số lấy cùng một thời điểm nếu đọc **trong lúc** dữ liệu còn đến. Ở ví dụ, đọc báo cáo **sau** terminal signal nên không gặp vấn đề snapshot đang biến đổi.

## 7. Khi trạng thái nhiều trường phải nhất quán

Nếu mỗi callback của nhiều subscription cùng cập nhật metrics tổng hợp, hãy dùng một khóa chung cho cả cập nhật lẫn đọc snapshot. Ví dụ dưới đây là **đoạn lớp hỗ trợ**, có thể đặt vào chương trình khác; không phải chương trình độc lập có `main`:

```java
final class Metrics {
    record Snapshot(long accepted, long rejected) {}

    private long accepted;
    private long rejected;

    synchronized void record(boolean valid) {
        if (valid) {
            accepted++;
        } else {
            rejected++;
        }
    }

    synchronized Snapshot snapshot() {
        return new Snapshot(accepted, rejected);
    }
}
```

Khóa bao quanh cả `record` và `snapshot` giúp người đọc không thấy một trạng thái bị quan sát dở chừng. Nếu cần lưu danh sách sự kiện, `Collections.synchronizedList` chỉ đồng bộ **từng thao tác**; duyệt hoặc kiểm tra–rồi–sửa gồm nhiều thao tác vẫn cần đồng bộ theo tài liệu API. Đừng biến khóa thành chỗ gọi I/O hoặc callback bên ngoài.

## 8. Những race và lỗi vòng đời dễ gặp

### Đọc kết quả quá sớm

`publisher.submit(x)` không có nghĩa `onNext(x)` đã hoàn thành vì việc phát là bất đồng bộ. `Thread.sleep(100)` không phải cơ chế chứng minh hoàn thành. Dùng `CountDownLatch`, `CompletableFuture`, hoặc synchronization đúng vòng đời. Nếu chờ bị timeout, xem đó là lỗi/giới hạn thời gian cần được xử lý, đừng in kết quả như thể đã hoàn tất.

### Hủy subscription rồi chờ mãi

Một `cancel()` có thể còn vài tín hiệu đang trên đường giao và không buộc publisher phải phát `onError` hay `onComplete`. Nếu ứng dụng chủ động hủy, hãy tự hoàn tất promise/latch quản lý vòng đời và dọn tài nguyên idempotent. Không mặc định rằng hủy là thất bại upstream.

### Giữ chung một subscriber cho nhiều subscription

Gán `this.subscription` lần hai có thể làm callback của subscription trước gọi `request` trên subscription sau. Cách dễ hiểu nhất: **tạo một instance subscriber cho mỗi subscription**, hoặc thiết kế riêng một subscriber đa subscription với trạng thái/đồng bộ được chứng minh rõ ràng.

### Nuốt lỗi trong `onNext`

`catch(Exception ignored) {}` làm mất dấu lỗi, trong khi `request(1)` tiếp tục tiêu thụ vô hạn. Cần ghi nhận item lỗi, loại lỗi, policy retry/bỏ qua, giới hạn số lần thất bại và cách thông báo cho phía gọi. Không dùng retry vô hạn bên trong callback đang giữ thread phát.

### Ném ngoại lệ khỏi callback rồi mong `onError` luôn chạy

Đó là giả định sai về kênh lỗi. Với `SubmissionPublisher`, ngoại lệ do phương thức subscriber ném sẽ khiến subscription bị hủy; handler truyền cho constructor có thể quan sát lỗi phát ra từ `onNext`. Đường xử lý ngoại lệ trong một publisher tự viết có thể khác, nên phải đọc hợp đồng của implementation. Muốn báo lỗi nhiệm vụ cho caller, dùng một kênh kết quả riêng có trạng thái thất bại rõ ràng.

### Gọi `request(Long.MAX_VALUE)` ở mọi nơi

Điều này gần như bỏ giới hạn demand của subscriber và có thể làm tăng lượng việc chờ, phụ thuộc cơ chế buffer của publisher. Hãy chọn demand dựa trên tốc độ xử lý, bộ nhớ, độ trễ và chiến lược khi đầy hàng đợi. `request(1)` là phương án giảng dạy an toàn để hiểu vòng đời, không phải tối ưu throughput mặc định.

## 9. Chiến lược kiểm thử

Kiểm tra cả **trật tự tín hiệu** lẫn **trạng thái quan sát được**, tránh test dựa trên thời gian ngủ tùy ý:

1. **Kết thúc thành công:** nhiều item, có item bị loại hợp lệ, tổng và số loại đúng; `onComplete` xảy ra một lần; không có `onError`.
2. **Lỗi upstream:** publisher kết thúc bằng `closeExceptionally`; subscriber lưu đúng nguyên nhân và không coi đó là hoàn thành thành công.
3. **Backpressure:** subscriber chỉ `request(1)`; kiểm thử publisher tuân thủ demand và không gửi vượt số phần tử đã được yêu cầu.
4. **Đồng thời:** nhiều publisher/subscriber cập nhật metrics dùng chung; kết quả không bị mất cập nhật, snapshot tuân thủ bất biến.
5. **Hủy:** khởi phát `cancel()` lúc đang tải, xác nhận ứng dụng tự kết thúc vòng đời mà không chờ một terminal signal không được bảo đảm.
6. **Lỗi callback:** với `SubmissionPublisher`, kiểm tra subscription bị hủy khi callback ném ngoại lệ và đường quan sát lỗi đã cấu hình; không assert rằng publisher phải chuyển lỗi đó thành `onError` trên chính subscriber.
7. **Timeout và cleanup:** nếu nguồn không phát terminal signal, cơ chế đợi phải timeout/cancel hợp lý; executor và tài nguyên sở hữu bởi ứng dụng được đóng đúng lúc.

Một test race có giá trị phải lặp đủ để tìm vấn đề, nhưng kết quả chạy qua một lần không chứng minh không còn race. Nên thiết kế chia sẻ trạng thái qua các primitive đồng bộ có hợp đồng rõ ràng, rồi kiểm tra bất biến thay vì dựa hoàn toàn vào stress test.

## 10. Ghi nhớ khi áp dụng

- **Tuần tự callback theo subscription** là bảo đảm của `Flow`; **an toàn trạng thái chia sẻ** là quyết định thiết kế của ứng dụng.
- **Lỗi dữ liệu phục hồi được**, **lỗi upstream kết thúc stream** và **lỗi ném khỏi callback** cần ba chính sách khác nhau.
- **`onError` và `onComplete` là terminal signals**; **`cancel()` không hứa gửi terminal signal**.
- Dùng demand có chủ đích, tránh callback chặn lâu, và quan sát kết thúc qua cơ chế đồng bộ đáng tin cậy.

Tài liệu tham khảo chính thức:
- [Flow — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html)
- [Flow.Publisher — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Publisher.html)
- [Flow.Subscription — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html)
- [SubmissionPublisher — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html)
