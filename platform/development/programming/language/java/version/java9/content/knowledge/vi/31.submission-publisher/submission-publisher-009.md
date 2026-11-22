# Tránh giữ khóa trong khi phát dữ liệu có thể chặn

Khi dùng `SubmissionPublisher` để phát sự kiện từ một vùng trạng thái được bảo vệ bằng lock, hãy hoàn tất việc cập nhật và tạo snapshot dữ liệu bên trong vùng khóa, sau đó nhả lock rồi mới gọi `submit` hoặc `offer`. Việc phát dữ liệu có thể chờ subscriber tiêu thụ buffer; callback của subscriber cũng có thể cần chính lock mà producer đang giữ. Nếu hai phía chờ nhau, hệ thống có thể deadlock.

Đây là quy tắc quan trọng khi kết hợp `SubmissionPublisher`, `synchronized` hoặc `ReentrantLock` và callback của Flow. Flow API không bắt buộc mọi publisher phải bất đồng bộ hoặc không chặn. Riêng `SubmissionPublisher.submit(item)` phát bất đồng bộ nhưng có thể chặn không ngắt được khi buffer của bất kỳ subscriber nào chưa có chỗ trống.

## 1. Vì sao publish có thể chặn?

`SubmissionPublisher` duy trì buffer riêng cho từng subscriber. Buffer giúp producer và consumer hoạt động ở tốc độ khác nhau trong một khoảng thời gian. Khi subscriber xử lý chậm hoặc chưa yêu cầu đủ dữ liệu, buffer của subscriber đó có thể đầy.

Các phương thức phát dữ liệu có chính sách khác nhau:

| Phương thức | Hành vi khi thiếu chỗ trong buffer |
|---|---|
| `submit(item)` | Chờ không ngắt được cho đến khi có tài nguyên để phát đến các subscriber hiện tại |
| `offer(item, onDrop)` | Thử phát; subscriber không nhận được item có thể bị drop; handler có thể được gọi và yêu cầu thử lại một lần |
| `offer(item, timeout, unit, onDrop)` | Chờ tối đa timeout hoặc đến khi thread bị interrupt; sau đó gọi handler nếu được cấu hình, handler có thể yêu cầu thử lại một lần |

`submit` đơn giản vì publisher tự chờ buffer có chỗ, nhưng producer có thể bị giữ lại lâu. `offer` cho phép ứng dụng chọn chính sách khi quá tải, nhưng đổi lại có thể mất sự kiện nếu không có cơ chế retry hoặc lưu trữ bền vững.

Giá trị trả về của `submit` và `offer` không phải là số subscriber đã xử lý xong. Chúng cung cấp ước lượng độ trễ tối đa (lag) của subscriber; với các overload `offer`, kết quả âm biểu thị số lần phát thất bại do drop. Các ước lượng này dành cho giám sát, không dùng làm cơ chế đồng bộ hoặc căn cứ duy nhất để quyết định tính đúng đắn của nghiệp vụ.

## 2. Deadlock khi giữ lock trong lúc submit

Giả sử producer cập nhật trạng thái tài khoản dưới `stateLock` rồi phát sự kiện. Subscriber nhận sự kiện và cần cùng lock để đọc trạng thái hoặc cập nhật một cấu trúc liên quan.

Một tình huống có thể xảy ra:

1. Producer lấy `stateLock`.
2. Producer gọi `publisher.submit(event)` khi buffer của subscriber đã đầy.
3. `submit` chờ subscriber tiêu thụ phần tử để giải phóng chỗ trong buffer.
4. Callback `onNext` của subscriber cần lấy `stateLock` trước khi xử lý và trả về.
5. Subscriber không lấy được lock vì producer vẫn đang giữ nó; producer không thể hoàn tất `submit` vì subscriber chưa tiêu thụ được phần tử.

`SubmissionPublisher` phân phối callback bất đồng bộ, nhưng điều đó không loại bỏ deadlock. Callback có thể chạy trên thread khác và vẫn cần lock mà producer đang giữ.

Sơ đồ chờ:

```text
Producer thread                         Subscriber thread
---------------                         -----------------
acquire stateLock
submit(event)
wait for buffer space  <--------------  onNext(event)
                                        wait for stateLock
                                        cannot finish callback
                                        cannot free buffer
```

Đây là một dạng vòng chờ giữa lock và backpressure. Tăng kích thước buffer có thể làm lỗi khó xuất hiện hơn, nhưng không loại bỏ nguyên nhân. Khi tải tăng hoặc subscriber chậm, buffer vẫn có thể đầy.

Ngay cả khi dùng publisher khác, giữ lock trong lúc gọi một API bên ngoài vẫn có rủi ro: implementation có thể gọi callback đồng bộ, gọi code tùy biến, chờ I/O hoặc lấy một lock khác. Không nên gọi publisher, subscriber, listener hoặc callback không thuộc quyền kiểm soát của mình trong critical section.

## 3. Mẫu an toàn: cập nhật và tạo snapshot, rồi publish sau khi nhả lock

Giữ lock chỉ đủ lâu để bảo vệ trạng thái nội bộ:

1. Lấy lock.
2. Cập nhật trạng thái.
3. Tạo một event snapshot độc lập, bất biến hoặc không còn bị thay đổi sau khi rời vùng khóa.
4. Nhả lock.
5. Gọi `publisher.submit(event)` hoặc chính sách phát phù hợp ở bên ngoài lock.

Ví dụ:

```java
private final Object stateLock = new Object();

private int balance;
private long version;

public void deposit(int amount) {
    AccountEvent event;

    synchronized (stateLock) {
        balance += amount;
        version++;

        // Snapshot được tạo khi trạng thái đang được bảo vệ.
        event = new AccountEvent(version, balance);
    }

    // Không giữ stateLock trong lúc phát dữ liệu.
    publisher.submit(event);
}

record AccountEvent(long version, int balance) {}
```

`AccountEvent` chứa các giá trị cần thiết tại thời điểm thay đổi. Subscriber không cần lấy lock của producer để đọc lại một object mutable có thể tiếp tục bị sửa. Với payload phức tạp, hãy sao chép các collection hoặc chuyển chúng thành cấu trúc bất biến; chỉ sao chép tham chiếu đến object mutable là chưa đủ.

Cách này giữ critical section ngắn và tránh việc producer giữ lock trong lúc chờ buffer. Subscriber vẫn có thể lấy lock nếu cần truy cập trạng thái khác, nhưng nó không bị chặn bởi một producer đang giữ lock để gọi `submit`.

## 4. Ví dụ đầy đủ chạy được

Chương trình dưới đây cập nhật balance trong synchronized block, tạo một record snapshot, rồi phát snapshot sau khi ra khỏi block. Subscriber dùng cùng lock để xử lý sự kiện. Executor một thread giúp quan sát callback được phân phối bất đồng bộ.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class Main {
    record AccountEvent(long version, int balance) {}

    public static void main(String[] args) throws Exception {
        Object stateLock = new Object();

        ExecutorService deliveryExecutor =
                Executors.newSingleThreadExecutor(task ->
                        new Thread(task, "flow-delivery"));

        CountDownLatch subscribed = new CountDownLatch(1);
        CountDownLatch received = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        try {
            try (SubmissionPublisher<AccountEvent> publisher =
                         new SubmissionPublisher<>(deliveryExecutor, 8)) {

                publisher.subscribe(new Flow.Subscriber<>() {
                    @Override
                    public void onSubscribe(Flow.Subscription subscription) {
                        subscription.request(Long.MAX_VALUE);
                        subscribed.countDown();
                    }

                    @Override
                    public void onNext(AccountEvent event) {
                        synchronized (stateLock) {
                            System.out.println(
                                    "Subscriber read version=" + event.version()
                                            + ", balance=" + event.balance());
                        }
                        received.countDown();
                    }

                    @Override
                    public void onError(Throwable error) {
                        failure.set(error);
                        received.countDown();
                    }

                    @Override
                    public void onComplete() {
                        // Không cần xử lý thêm trong ví dụ này.
                    }
                });

                if (!subscribed.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Subscriber did not subscribe");
                }

                int balance = 100;
                long version = 0;
                AccountEvent event;

                synchronized (stateLock) {
                    balance += 25;
                    version++;
                    event = new AccountEvent(version, balance);
                }

                System.out.println(
                        "Producer holds lock before submit: "
                                + Thread.holdsLock(stateLock));

                publisher.submit(event);

                if (!received.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Event was not received");
                }
                if (failure.get() != null) {
                    throw new IllegalStateException("Subscriber failed", failure.get());
                }
            }
        } finally {
            deliveryExecutor.shutdown();
            if (!deliveryExecutor.awaitTermination(5, TimeUnit.SECONDS)) {
                deliveryExecutor.shutdownNow();
            }
        }
    }
}
```

Lưu thành `Main.java`, biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 Main.java
java Main
```

Kết quả stdout:

```text
Producer holds lock before submit: false
Subscriber read version=1, balance=125
```

Dòng đầu xác nhận producer đã nhả `stateLock` trước khi gọi `submit`. Callback `onNext` lấy cùng lock để xử lý snapshot mà không phải chờ producer nhả lock sau một thao tác publish có thể chặn.

Ví dụ dùng `record` để snapshot chỉ chứa các giá trị primitive. Trong ứng dụng thực tế, payload nên bất biến hoặc được sao chép đủ sâu để subscriber không nhìn thấy dữ liệu bị thay đổi sau khi phát.

## 5. Không thay deadlock bằng một race về thứ tự sự kiện

Đưa `submit` ra ngoài lock loại bỏ một kiểu deadlock, nhưng khi có nhiều producer đồng thời, thứ tự gọi `submit` có thể khác thứ tự cập nhật trạng thái.

Ví dụ:

- Thread A cập nhật version 1, tạo event 1 rồi nhả lock.
- Thread B cập nhật version 2, tạo event 2 rồi nhả lock.
- Thread B có thể gọi `submit(event2)` trước thread A.
- Subscriber có thể nhận event theo thứ tự publish, trong khi version của snapshot phản ánh thứ tự cập nhật khác.

Nếu nghiệp vụ yêu cầu thứ tự sự kiện phải khớp thứ tự thay đổi trạng thái, hãy thiết kế một đường phát tuần tự:

- Gán sequence/version khi đang giữ lock.
- Chuyển event bất biến sang một dispatcher duy nhất theo thứ tự đã xác định.
- Dispatcher gọi `submit` sau khi lock trạng thái đã được nhả.
- Xác định rõ cách xử lý khi hàng đợi dispatcher đầy hoặc executor từ chối tác vụ; không âm thầm bỏ event.
- Không dùng chính sách `CallerRunsPolicy` cho dispatcher nếu tác vụ có thể chạy inline trên thread đang giữ lock.

Với hệ thống cần bảo đảm sự kiện không mất khi tiến trình dừng, cân nhắc transactional outbox hoặc một log bền vững. `SubmissionPublisher` là cơ chế phân phối trong bộ nhớ; nó không thay thế transaction, durable queue hay cơ chế exactly-once.

## 6. Chọn submit hay offer khi có backpressure

Nhả lock trước khi phát là nguyên tắc độc lập với chính sách quá tải. Sau khi nhả lock, vẫn cần quyết định producer nên chờ, cho phép drop hay ghi nhận sự kiện vào một hàng đợi khác.

### Dùng submit khi chờ là chấp nhận được

`submit(item)` phù hợp khi:

- Producer có thể chờ nếu subscriber xử lý chậm.
- Producer chạy trên thread chuyên dụng, không phải thread giữ lock, UI thread hoặc thread phục vụ request có deadline ngắn.
- Hệ thống chấp nhận việc một subscriber chậm làm chậm producer.
- Không có chu trình chờ khác giữa producer, subscriber và executor.

Nhớ rằng `submit` chờ không ngắt được khi buffer của bất kỳ subscriber nào không có chỗ. Không nên gọi nó trong critical section hoặc trên thread cần phản hồi nhanh.

### Dùng offer khi cần giới hạn thời gian hoặc chính sách drop

`offer(item, timeout, unit, onDrop)` cho phép chờ tối đa một khoảng thời gian hoặc đến khi thread bị interrupt, sau đó gọi handler nếu có. Handler có thể trả `true` để yêu cầu thử lại một lần. Nếu vẫn không phát được, kết quả trả về là số âm biểu thị số lần phát bị drop.

`offer(item, onDrop)` thử phát mà không chờ theo timeout; item có thể bị drop nếu tài nguyên không đủ. Handler chạy trong luồng gọi và các lời gọi method khác của publisher từ thread khác có thể bị chặn trong lúc handler chạy. Vì vậy handler phải ngắn, không lấy lock có thể tạo vòng chờ và không thực hiện I/O chậm.

Ví dụ kiểm tra kết quả:

```java
int lagOrDrops = publisher.offer(
        event,
        100,
        TimeUnit.MILLISECONDS,
        (subscriber, droppedItem) -> {
            logDroppedEvent(droppedItem);
            return false;
        }
);

if (lagOrDrops < 0) {
    // Có subscriber không nhận được event.
    // Thực hiện chính sách retry hoặc lưu bền vững nếu nghiệp vụ yêu cầu.
}
```

Đoạn mã là minh họa cho overload có timeout. Không coi giá trị không âm là xác nhận subscriber đã xử lý xong; đó chỉ là ước lượng lag. Nếu event quan trọng, handler không nên chỉ ghi log rồi bỏ qua. Hãy chuyển sang durable queue, retry có giới hạn hoặc báo lỗi nghiệp vụ phù hợp.

`offer` cũng không phải giải pháp thay thế cho việc nhả lock. Overload có timeout vẫn có thể chờ; handler có thể chạy ngay trên thread đang gọi. Luôn phát bên ngoài critical section.

## 7. Những cách dễ tạo vòng chờ

**Giữ synchronized khi gọi submit**

```java
synchronized (stateLock) {
    updateState();
    publisher.submit(createEvent());
}
```

Nếu subscriber cần `stateLock` và buffer đầy, producer có thể chờ buffer trong khi subscriber chờ lock. Hãy tạo event bên trong block và submit sau block.

**Giữ ReentrantLock khi chờ subscriber hoàn tất**

```java
lock.lock();
try {
    updateState();
    publisher.submit(event);
    subscriberProcessed.await();
} finally {
    lock.unlock();
}
```

Cách này có hai điểm chờ trong critical section: `submit` và `await`. Subscriber cần lock để xử lý hoặc xác nhận sự kiện sẽ không thể tiến triển. Không đợi callback, Future, latch hay I/O bên trong lock nếu tác vụ được chờ có thể cần cùng lock.

**Gọi callback tùy biến dưới lock**

```java
synchronized (stateLock) {
    updateState();
    listener.onChanged(snapshot);
}
```

Listener có thể gọi ngược vào component, lấy lock khác hoặc thực hiện thao tác chậm. Quy tắc tương tự áp dụng cho event bus, hook, observer, logging appender tùy biến và các API gọi code bên ngoài.

## 8. Thiết kế lock và event payload

Một số nguyên tắc giúp giảm rủi ro:

- Lock chỉ bảo vệ invariant của trạng thái nội bộ; không dùng lock để bao trọn cả quá trình phân phối sự kiện.
- Tạo snapshot nhất quán khi đang giữ lock. Nếu nhiều field phải cùng phản ánh một version, hãy đọc/copy chúng trong cùng critical section.
- Dùng record hoặc immutable class cho event. Tránh phát trực tiếp một object mutable mà producer tiếp tục sửa.
- Không đưa lock hoặc tham chiếu đến cấu trúc nội bộ có thể thay đổi vào event.
- Nếu subscriber cần đọc trạng thái mới nhất thay vì trạng thái tại thời điểm event được tạo, xác định rõ semantics và cung cấp API đọc an toàn riêng.
- Nếu thứ tự sự kiện quan trọng, dùng sequence number và một cơ chế dispatch tuần tự.
- Đo thời gian giữ lock, thời gian publish, lag và số lần drop bằng metric; không dùng các giá trị lag ước lượng làm synchronization primitive.

`SubmissionPublisher` có các phương thức giám sát như `estimateMaximumLag()`, `estimateMinimumDemand()` và `getMaxBufferCapacity()`. Chúng hữu ích để quan sát tải, nhưng các giá trị ước lượng có thể cũ hoặc không chính xác tại thời điểm đọc. Không viết logic kiểu “nếu lag nhỏ thì giữ lock và submit” vì trạng thái có thể đổi ngay sau phép kiểm tra.

## 9. Kiểm tra và chẩn đoán deadlock

Khi hệ thống có dấu hiệu treo:

1. Lấy thread dump bằng công cụ runtime phù hợp, ví dụ `jcmd <pid> Thread.print`.
2. Tìm thread producer đang ở trong `SubmissionPublisher.submit` hoặc `offer`.
3. Tìm thread subscriber đang ở `onNext` và chờ monitor hoặc lock.
4. Đối chiếu lock producer đang giữ với lock subscriber cần lấy.
5. Kiểm tra executor có đủ worker để chạy callback và có worker nào bị chặn lâu không.
6. Kiểm tra subscriber có gọi `request(n)` và có xử lý/return khỏi `onNext` hay không.
7. Sau khi sửa, thử tải với buffer nhỏ, subscriber xử lý chậm và nhiều producer đồng thời.

Một thread dump có thể chỉ ra monitor owner và thread đang chờ. Nếu vòng chờ đi qua executor queue, Future, latch hoặc semaphore, cần lần theo cả chuỗi phụ thuộc chứ không chỉ tìm từ khóa synchronized.

## 10. Checklist trước khi publish

- Event đã được tạo thành snapshot nhất quán trong vùng khóa chưa?
- Lock đã được nhả hoàn toàn trước `submit` hoặc `offer` chưa?
- Subscriber có thể lấy lại cùng lock mà không chờ producer không?
- Callback có gọi ngược vào producer hoặc giữ lock trong lúc làm I/O không?
- Producer có chấp nhận việc `submit` chờ không ngắt được khi subscriber chậm không?
- Nếu dùng `offer`, đã xử lý kết quả âm và chính sách drop/retry chưa?
- Handler có tránh lock, I/O chậm và gọi lại publisher không?
- Nhiều producer có cần giữ thứ tự cập nhật và thứ tự phát không?
- Event có bất biến hoặc được sao chép đủ sâu không?
- Có giám sát lag, thời gian publish, queue và timeout không?
- Có kiểm thử với subscriber chậm, không demand, executor bận và nhiều producer không?

Nguyên tắc cốt lõi là giữ lock cho việc bảo vệ trạng thái và tạo snapshot; việc phát dữ liệu là một thao tác riêng có thể chờ subscriber hoặc gọi code khác. Với `SubmissionPublisher`, `submit` có thể chặn không ngắt được khi buffer đầy, nên hãy luôn nhả lock trước khi publish. Nếu cần thứ tự, retry hoặc độ bền dữ liệu, bổ sung dispatcher tuần tự hay outbox phù hợp thay vì mở rộng critical section.
