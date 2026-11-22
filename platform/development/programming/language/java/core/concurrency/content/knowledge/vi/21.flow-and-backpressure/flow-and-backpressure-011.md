# Khi phù hợp để xây pipeline theo sự kiện trong Java: Flow & Backpressure

Một **pipeline theo sự kiện** (event-driven pipeline) tổ chức công việc thành các giai đoạn nhận, biến đổi, lọc, tổng hợp hoặc ghi kết quả khi sự kiện xuất hiện. Thay vì một hàm gọi tuần tự mọi bước rồi đợi trả về, các giai đoạn có thể chạy độc lập, truyền thông điệp qua ranh giới bất đồng bộ và phối hợp tốc độ xử lý. Trong Java, `java.util.concurrent.Flow` (từ Java 9) đưa ra giao thức **Publisher–Subscriber** có cơ chế *backpressure* (điều tiết theo nhu cầu), giúp downstream nói rõ nó còn có thể tiếp nhận bao nhiêu phần tử.

Điểm cần quyết định không phải “có event thì dùng Flow”, mà là **pipeline có đủ lý do để chịu thêm độ phức tạp của xử lý bất đồng bộ, bộ đệm, yêu cầu dữ liệu, lỗi và hủy tác vụ hay không**.

Bài học tập trung vào Java concurrency thuần, đặc biệt là `Flow`, `SubmissionPublisher` và công cụ chuẩn `java.util.concurrent`. Không cần framework để hiểu và áp dụng các nguyên tắc bên dưới.

## 1. “Pipeline theo sự kiện” thực sự giải quyết vấn đề gì?

Giả sử ứng dụng nhận liên tục các bản ghi đo đạc:

```text
Nguồn sự kiện
    │
    ▼
Kiểm tra dữ liệu ──► Lọc sự kiện không hợp lệ
    │
    ▼
Chuẩn hóa/biến đổi
    │
    ▼
Tổng hợp theo điều kiện
    │
    ▼
Gửi kết quả đến nơi tiêu thụ
```

Nếu xử lý mọi thứ trên một thread tuần tự, đường đi dễ hiểu nhưng có thể không tận dụng tốt thời gian chờ I/O. Nếu nguồn sinh nhanh hơn nơi ghi kết quả, một hàng đợi không giới hạn có thể làm cạn bộ nhớ. Nếu nhiều giai đoạn chạy độc lập, hệ thống cần biết:

1. **Sự kiện đến từ đâu?** Nguồn kéo dữ liệu khi được hỏi (*pull*) hay phát liên tục dù chưa có người nhận (*push/hot source*)?
2. **Ai quyết định lượng công việc đang chờ?** Có hàng đợi/buffer hữu hạn và quy tắc khi đầy không?
3. **Người tiêu thụ chậm thì sao?** Chờ, giảm nhịp nguồn, bỏ sự kiện, ghi bền vững hay báo lỗi?
4. **Thứ tự và tính đúng đắn cần gì?** Cần giữ thứ tự từng nguồn, thứ tự toàn cục, xử lý đúng một lần hay chỉ cần kết quả cuối?
5. **Lỗi/hủy/trả tài nguyên lan qua các giai đoạn thế nào?** Có đóng subscription, executor, socket và resource đúng vòng đời không?

Pipeline theo sự kiện phù hợp khi những câu hỏi này có câu trả lời rõ ràng và ranh giới bất đồng bộ đem lại lợi ích thực tế.

### Event, command và batch không giống nhau

- **Event** là thông báo “điều đã xảy ra”, chẳng hạn `ReadingReceived` hoặc `FileChanged`. Nó có thể kích hoạt nhiều bộ xử lý.
- **Command** là yêu cầu làm một hành động, có thể cần kết quả hoặc xác nhận, chẳng hạn `RecalculateInvoice`.
- **Batch** là tập dữ liệu có giới hạn được xử lý theo đợt, ví dụ đọc một tệp rồi tính tổng.

Ba kiểu có thể kết hợp, nhưng không nên đổi một phép tính batch ngắn thành nhiều event và callback chỉ vì thư viện cung cấp API bất đồng bộ.

## 2. Những dấu hiệu NÊN cân nhắc event pipeline

| Dấu hiệu trong bài toán | Lợi ích khả dĩ | Cần kiểm chứng |
|---|---|---|
| Nguồn dữ liệu đến liên tục theo thời gian | Xử lý tăng dần, không đợi toàn bộ dữ liệu kết thúc | Cơ chế dừng, ranh giới buffer |
| Nhiều giai đoạn độc lập về thời gian hoặc I/O | Tách trách nhiệm, overlap công việc | Scheduling overhead, quản lý lỗi |
| Tốc độ nguồn và đích biến động | Backpressure có thể hạn chế lượng đang chờ | Nguồn có thực sự giảm nhịp được không? |
| Dữ liệu lớn/không muốn load toàn bộ vào RAM | Xử lý từng phần tử hoặc theo cửa sổ | Tổng hợp/window có giữ state có giới hạn không? |
| Mỗi sự kiện có thể được lọc và biến đổi độc lập | Dễ bố trí các stage và test riêng | Side effects, ordering, idempotency |
| Có nhiều người tiêu thụ với tốc độ khác nhau | Publisher có thể phân phối tới các subscriptions | Buffer và độ trễ riêng từng subscriber |
| Cần hủy luồng xử lý khi người nhận bỏ cuộc | `Subscription.cancel()` tạo kênh thông báo hủy | Các stages có giải phóng tài nguyên thật không? |
| Một bước blocking cần tách khỏi nơi phát sinh event | Không giữ thread nguồn chờ thao tác nặng | Chọn executor/concurrency model phù hợp |

**Ví dụ hợp lý:** xử lý liên tục thay đổi từ cảm biến, đọc và phân loại dòng sự kiện nội bộ, luồng notifications, chuyển đổi bản ghi trong ứng dụng, hoặc streaming dữ liệu với tốc độ tiêu thụ khó dự báo.

“Có nhiều sự kiện” chỉ là dấu hiệu ban đầu. **Giá trị chính của Flow là mô hình hợp đồng nhu cầu** giữa producer và consumer, đặc biệt khi downstream có thể chậm.

## 3. Những trường hợp CHƯA nên xây event pipeline

Đừng ép một quy trình đơn giản thành hệ thống phát/nhận bất đồng bộ nếu:

- Chỉ có vài bước **ngắn, tuần tự, có kết quả ngay**, chẳng hạn kiểm tra input rồi trả giá trị.
- Toàn bộ dữ liệu đã ở trong bộ nhớ và chỉ cần một phép biến đổi batch; `Stream` hoặc vòng lặp thường đơn giản hơn.
- Công việc là CPU-bound thuần và cần tăng tốc chia dữ liệu; cân nhắc thuật toán, `ExecutorService` hoặc parallel stream có kiểm soát thay vì tạo pipeline nhiều buffer.
- Một yêu cầu bắt buộc một giao dịch nguyên tử bao trùm mọi thao tác; tách thành nhiều event bất đồng bộ làm thay đổi ranh giới transaction.
- Cần **lưu bền vững, replay sau restart, retry có đảm bảo, phối hợp nhiều máy hoặc xử lý chính xác một lần**. `Flow` tự nó là giao thức in-process, không tự cung cấp message broker, storage, transaction hay exactly-once.
- Nguồn external *không thể giảm tốc* và nghiệp vụ **không chấp nhận mất dữ liệu**, nhưng chưa có chiến lược buffer/bền vững. Chỉ thêm `request(n)` không làm lượng dữ liệu ngoài hệ thống biến mất.
- Các bên không thể xác định trách nhiệm quản lý lifecycle, cancellation, error và quan sát trạng thái. Độ phức tạp này có thể lớn hơn lợi ích.

Một `BlockingQueue` hữu hạn và một worker có thể đủ cho producer–consumer đơn giản; các lệnh gọi thông thường hoặc `ExecutorService` dễ bảo trì hơn nếu không cần giao thức Publisher–Subscriber. Chọn Flow khi **demand và nhiều stage** là vấn đề thực sự, không phải như một mặc định cho mọi bài toán concurrency.

## 4. Java Flow gồm những thành phần nào?

`Flow` định nghĩa các giao diện tương ứng tinh thần **Reactive Streams**:

| Thành phần | Hợp đồng cốt lõi |
|---|---|
| `Flow.Publisher<T>` | Cho phép một `Subscriber` đăng ký qua `subscribe(subscriber)` và phát phần tử/terminal signals |
| `Flow.Subscriber<T>` | Nhận `onSubscribe`, `onNext`, `onError`, `onComplete` |
| `Flow.Subscription` | Nối Publisher với **một Subscriber**, cho phép `request(long n)` và `cancel()` |
| `Flow.Processor<T,R>` | Vừa là Subscriber nhận `T`, vừa là Publisher phát `R`; thích hợp cho một stage biến đổi |

Luồng tín hiệu cơ bản:

```text
Publisher                          Subscriber
    |                                  |
    | ------- onSubscribe(s) --------> |
    | <------ s.request(2) ----------- |
    | ------- onNext(eventA) --------> |
    | ------- onNext(eventB) --------> |
    |    (không được đẩy thêm nếu       |
    |     chưa có demand mới)          |
    | <------ s.request(1) ----------- |
    | ------- onNext(eventC) --------> |
    | ------- onComplete() ----------> |
    |                                  |
          hoặc onError(error)
```

**`request(n)` nói “cho phép nhận thêm tối đa n sự kiện”**, không phải bắt Publisher phải tạo đủ n phần tử ngay. Demand là số lượng phần tử được phép phát cho subscription đó và được cộng dồn theo quy tắc bão hòa của API. Mỗi `onNext` tiêu thụ một đơn vị demand. `request(Long.MAX_VALUE)` biểu diễn nhu cầu không giới hạn, không có nghĩa hệ thống đã có vô hạn buffer hay vô hạn tốc độ xử lý.

Điều kiện quan trọng:

1. Sau `subscribe`, Subscriber được cấp `Subscription` qua `onSubscribe` trước khi nhận các tín hiệu dữ liệu thông thường.
2. Một subscription chỉ được phát `onNext` khi có demand dương; `request(0)` hoặc giá trị âm là yêu cầu không hợp lệ và phải được phản ánh bằng `onError` theo hợp đồng Flow.
3. Tín hiệu của **cùng một subscription** được gửi theo thứ tự, không gọi chồng nhau đồng thời theo quy tắc Publisher; điều này không đảm bảo nhiều subscribers thấy callback tại cùng thời điểm.
4. `onError` hoặc `onComplete` là tín hiệu kết thúc; sau đó không được gửi thêm `onNext` đến cùng subscription.
5. `cancel()` là yêu cầu ngừng subscription, không phải lời bảo đảm rằng subscriber sẽ nhận thêm `onComplete`. Code upstream cần thực sự giải phóng nguồn tài nguyên.
6. Event `null` không được phép trong các implementations tuân thủ Flow phổ biến; với `SubmissionPublisher`, `submit(null)` ném `NullPointerException`.

`Flow` mô tả hợp đồng trao đổi tín hiệu; **không tự tạo thread, không tự lưu sự kiện, không tự chuyển một phép tính thành non-blocking**. Cách chạy đồng bộ hay bất đồng bộ do implementation và executor quyết định.

## 5. Backpressure khác gì queue, rate limit và load shedding?

**Backpressure** là tín hiệu từ downstream về lượng dữ liệu nó có thể tiếp nhận, truyền ngược để upstream kiểm soát nhịp hoặc chính sách phát. Một buffer có thể hấp thụ burst trong một khoảng ngắn, nhưng buffer **không thể giải quyết chênh lệch tốc độ kéo dài vô hạn**.

Giả sử nguồn tạo 1.000 sự kiện/giây, bộ xử lý chỉ hoàn thành 100 sự kiện/giây:

- Nếu chỉ dùng queue không giới hạn, backlog tăng xấp xỉ 900 sự kiện/giây; cuối cùng có thể hết heap.
- Nếu dùng buffer hữu hạn và nguồn có thể chờ, producer tạm dừng/giảm nhịp, hệ thống ổn định hơn nhưng có thể tăng độ trễ producer.
- Nếu nguồn không thể chờ (ví dụ một thiết bị liên tục gửi), phải có chính sách drop, sampling, lưu bền vững hoặc kiểm soát từ phía nguồn.
- Nếu nghiệp vụ không cho phép mất một sự kiện nào và nguồn vẫn không dừng, **cần một nơi lưu trữ đủ bền vững và có giới hạn vận hành rõ ràng**, không thể giải quyết chỉ bằng RAM và `request(n)`.

**Phân biệt các cơ chế:**

| Cơ chế | Câu hỏi nó giải quyết |
|---|---|
| `request(n)` | Subscriber còn cho phép upstream gửi bao nhiêu phần tử? |
| Bounded queue/buffer | Bao nhiêu phần tử có thể đang đợi trong bộ nhớ? |
| Rate limiting | Được phát bao nhiêu yêu cầu trong một khoảng thời gian? |
| Semaphore/concurrency limit | Có tối đa bao nhiêu thao tác cùng sử dụng tài nguyên? |
| Load shedding/drop | Khi quá tải, phần tử nào được bỏ và có chấp nhận mất không? |
| Durable log/queue | Nếu process restart thì các event đã nhận có thể được phục hồi không? |

Các cơ chế này bổ trợ nhau, không thay thế hoàn toàn nhau. Ví dụ subscriber có thể yêu cầu 20 phần tử nhưng hệ thống chỉ có 5 kết nối ra ngoài; vẫn phải giới hạn số kết nối thực tế.

## 6. Ví dụ runnable: nhu cầu từng phần tử với `SubmissionPublisher`

`SubmissionPublisher<T>` là Publisher chuẩn của JDK: dùng executor để gửi bất đồng bộ đến subscribers hiện có, có **buffer riêng cho mỗi subscriber** và các lựa chọn phát khi buffer đầy. Demo sau tính tổng 5 sự kiện; subscriber chỉ yêu cầu thêm **một phần tử** mỗi khi xử lý xong một phần tử.

Lưu tệp **`FlowDemandDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class FlowDemandDemo {
    static final class CountingSubscriber implements Flow.Subscriber<Integer> {
        private final CountDownLatch done;
        private Flow.Subscription subscription;
        private int sum;

        CountingSubscriber(CountDownLatch done) {
            this.done = done;
        }

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            subscription.request(1);
        }

        @Override
        public void onNext(Integer item) {
            sum += item;
            subscription.request(1); // Xử lý xong mới xin thêm một phần tử.
        }

        @Override
        public void onError(Throwable error) {
            System.out.println("error=" + error.getClass().getSimpleName());
            done.countDown();
        }

        @Override
        public void onComplete() {
            System.out.println("sum=" + sum);
            done.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        var executor = Executors.newSingleThreadExecutor();
        var done = new CountDownLatch(1);

        try (var publisher = new SubmissionPublisher<Integer>(executor, 2)) {
            publisher.subscribe(new CountingSubscriber(done));

            for (int i = 1; i <= 5; i++) {
                publisher.submit(i);
            }
            publisher.close();

            if (!done.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out");
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

Biên dịch/chạy với **JDK 21**:

```bash
javac FlowDemandDemo.java
java FlowDemandDemo
```

Kết quả khi mọi phần tử xử lý thành công:

```text
sum=15
```

**Giải thích:**

- `publisher.subscribe(...)` đăng ký subscriber, callback `onSubscribe` cấp một `Subscription`.
- `request(1)` cho phép gửi một phần tử. Khi xử lý xong trong `onNext`, subscriber xin thêm một phần tử. Trong ví dụ, `onNext` tuần tự theo từng subscription.
- `SubmissionPublisher<>(executor, 2)` cấu hình buffer tối đa dự kiến cho **mỗi subscriber**; kích thước hiệu lực có thể được làm tròn theo implementation, hãy kiểm tra `getMaxBufferCapacity()` khi cần.
- `submit` có thể chặn thread producer khi buffer của bất kỳ subscriber nào đầy, chờ chỗ trống để phát. Vì vậy đây là **áp lực ngược lên nơi gọi submit**, không phải API luôn non-blocking.
- `close()` kết thúc việc publish và gửi `onComplete` đến subscribers một cách bất đồng bộ sau các phần tử đã phát; `CountDownLatch` giúp main chờ sự kiện kết thúc. Chỉ gọi `close()` rồi thoát ngay không đủ để bảo đảm mọi callback đã hoàn tất.
- Executor là tài nguyên riêng của demo, được `shutdown()` trong `finally`. Với nhiều subscribers chậm, một executor một worker có thể là nút thắt; đây là lựa chọn để ví dụ dễ kiểm chứng, không phải cấu hình hiệu năng được khuyến nghị chung.

Ví dụ không tạo network I/O và không chứng minh mức tăng thông lượng. Nó minh họa **demand và vòng đời tín hiệu**. Trong production, xử lý `onError` phải ghi nhận/đẩy lỗi theo chính sách nghiệp vụ; một callback chỉ in tên lỗi là chưa đủ.

## 7. Ví dụ runnable: dữ liệu có thể chờ trong buffer nhưng chưa được phép giao

Ví dụ tiếp theo tách rõ **đã `submit` vào Publisher** với **đã được giao qua `onNext`**. Subscriber yêu cầu 2 phần tử đầu. Producer phát 3 phần tử; phần tử thứ ba sẽ ở trạng thái đợi cho đến khi Subscriber yêu cầu tiếp.

Lưu thành **`DemandWindowDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class DemandWindowDemo {
    static final class Consumer implements Flow.Subscriber<Integer> {
        private final CountDownLatch firstTwo;
        private final CountDownLatch terminal;
        volatile Flow.Subscription subscription;
        int received;

        Consumer(CountDownLatch firstTwo, CountDownLatch terminal) {
            this.firstTwo = firstTwo;
            this.terminal = terminal;
        }

        @Override
        public void onSubscribe(Flow.Subscription s) {
            subscription = s;
            s.request(2);
        }

        @Override
        public void onNext(Integer item) {
            System.out.println("item=" + item);
            if (++received == 2) {
                firstTwo.countDown();
            }
        }

        @Override
        public void onError(Throwable failure) {
            System.out.println("error");
            terminal.countDown();
        }

        @Override
        public void onComplete() {
            System.out.println("complete");
            terminal.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        var executor = Executors.newSingleThreadExecutor();
        var firstTwo = new CountDownLatch(1);
        var terminal = new CountDownLatch(1);
        var consumer = new Consumer(firstTwo, terminal);

        try (var publisher = new SubmissionPublisher<Integer>(executor, 4)) {
            publisher.subscribe(consumer);

            for (int i = 1; i <= 3; i++) {
                publisher.submit(i);
            }

            if (!firstTwo.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Missing first batch");
            }

            System.out.println("request-more");
            consumer.subscription.request(1);
            publisher.close();

            if (!terminal.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Not completed");
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac DemandWindowDemo.java
java DemandWindowDemo
```

Đầu ra:

```text
item=1
item=2
request-more
item=3
complete
```

Ở đây phần tử 3 **đã được `submit`**, nhưng không được gửi qua `onNext` khi demand hai phần tử đã hết. Khi main gọi `request(1)`, publisher mới có quyền giao nốt phần tử đó. `CountDownLatch` bảo đảm phần “request-more” chỉ in sau khi subscriber đã xử lý hai phần tử đầu; không dùng `Thread.sleep` để đoán lịch chạy. `volatile` trên tham chiếu `subscription` thể hiện truy cập giữa callback thread và main thread; đồng thời tín hiệu latch bảo đảm thứ tự ở thời điểm main dùng tham chiếu.

**Điều không được suy diễn:** demand bằng 0 không chứng minh producer đã ngừng tạo dữ liệu, vì `SubmissionPublisher` có thể **đệm** sự kiện đã nộp đến giới hạn. Khi buffer đầy, tùy API gọi và policy, producer mới bị chặn hoặc có khả năng drop. Muốn áp lực ngược đi đến tận nguồn, nguồn đó phải được thiết kế tôn trọng tín hiệu này.

## 8. `SubmissionPublisher` phù hợp và giới hạn đến đâu?

`SubmissionPublisher` rất hữu ích để học hoặc ghép các thành phần nhỏ **trong một JVM**, không phải hạ tầng event-broker sản xuất đầy đủ.

### Hai chính sách khi buffer đầy

- **`submit(item)`:** có thể block **uninterruptibly** đến khi có chỗ trong buffer của mọi subscriber cần nhận; dễ hiểu nhưng nguy cơ giữ thread producer lâu hoặc vô hạn nếu subscriber không tiếp tục request.
- **`offer(item, onDrop)`** hoặc overload có timeout: có thể không gửi được cho một số subscribers khi quá tải. Handler có thể xử lý drop và yêu cầu retry một lần theo hợp đồng API; giá trị trả âm thể hiện các lần drop. Dữ liệu quan trọng không được âm thầm bỏ đi chỉ vì `offer` trả nhanh.

Một publisher có nhiều subscribers có **buffer độc lập** cho từng subscriber. Một consumer chậm có thể khiến `submit` của producer phải chờ, ảnh hưởng tất cả dù các consumer khác nhanh hơn. Việc tạo 100 subscribers với buffer 256 **không** tương đương một buffer toàn cục 256 phần tử; phải lập ngân sách bộ nhớ theo số subscriptions và trạng thái các stages.

`SubmissionPublisher` không replay những phần tử đã phát trước khi subscriber đăng ký như một durable event log; không dùng nó để thay thế lưu trữ lịch sử. Nếu cần khôi phục sau crash, thiết kế storage/broker riêng và adapter điều tiết đầu vào. Nếu event cực quan trọng, cần cơ chế ack/idempotency/retry ở tầng nghiệp vụ và trạng thái bền vững; `onNext` không mặc định là “đã ghi thành công vĩnh viễn”.

### Dấu hiệu thiếu backpressure khi tự viết Processor

Một `Flow.Processor<T,R>` là cầu nối nhận `T` từ upstream và phát `R` downstream. Nó có thể biểu diễn pipeline `Publisher -> Processor -> Subscriber`, nhưng **không có cơ chế chuyển demand tự động nếu bạn tự viết implementation**. Ví dụ processor gọi `upstream.request(Long.MAX_VALUE)`, rồi tự lưu mọi input vào danh sách không giới hạn, sẽ phá vỡ mục tiêu điều tiết dù downstream chỉ gọi `request(1)`.

Processor đúng cần phối hợp **demand downstream, số input đang xử lý, buffer hữu hạn, overflow policy, cancellation, completion và errors**. Với phép lọc bỏ nhiều phần tử, request đầu vào có thể phải cao hơn số output downstream yêu cầu, nhưng vẫn phải có giới hạn và quy tắc rõ ràng. Không suy ra rằng request đầu vào 10 phần tử chắc chắn cho ra 10 phần tử sau filter.

### Vòng đời lỗi và hủy

- `onError(Throwable)` là tín hiệu kết thúc cho subscriber; phải dọn resources và thông báo lỗi đúng phạm vi.
- `onComplete()` chỉ nói Publisher đã phát hết và hoàn tất cho subscription; không có ý nghĩa “mọi tác động ngoài hệ thống đã durable” trừ khi chương trình tự xác định.
- `Subscription.cancel()` yêu cầu ngừng nhận thêm và giải phóng các công việc liên quan; upstream/processor cần hỗ trợ, không mặc định luồng khác tự dừng.
- `SubmissionPublisher.closeExceptionally(error)` dùng để báo kết thúc lỗi đến subscribers hiện có; khác với `close()` thành công.
- Trong production, cần kiểm soát exception phát sinh từ code của `onNext`, tránh callback đốt hết worker, giữ tài nguyên hoặc che lỗi nghiệp vụ. Nếu stage biến đổi lỗi, đưa lỗi theo hợp đồng pipeline hoặc cơ chế giám sát rõ ràng.

## 9. Thiết kế một event pipeline có giới hạn

Ví dụ bài toán: sự kiện cập nhật trạng thái tài liệu phát sinh liên tục, được kiểm tra, làm giàu, gom số lượng và chuyển sang hệ thống ghi kết quả.

```text
Nguồn input
  ├─ giới hạn tốc độ nhận / nguồn có thể chờ?
  ▼
Buffer hữu hạn
  ▼
Validate/Filter
  ▼
Transform/Enrich  ───> Giới hạn số tác vụ I/O đồng thời
  ▼
Aggregate/window  ───> Giới hạn state và thời gian giữ
  ▼
Output
  └─ xác nhận kết quả / xử lý lỗi / hủy
```

Cần trả lời một số câu hỏi **trước khi tạo Publisher/Processor**:

1. **Đặc tính nguồn:** phát có giới hạn, burst, không thể chặn hay hỗ trợ pull? Nếu là hot source, điều gì xảy ra nếu subscriber tụt lại?
2. **Đơn vị sự kiện:** immutable data hay tham chiếu object mutable? Có cần copy để tránh dữ liệu bị thay khi xử lý sau?
3. **Ranh giới xử lý:** stage nào là CPU-bound, stage nào blocking I/O? Số executor/threads và memory budget được cấp riêng ra sao?
4. **Giới hạn bộ đệm:** sức chứa tối đa ở từng ranh giới, không chỉ một buffer tại đầu nguồn. Đầy thì chờ, trả lỗi, drop hay spill ra storage?
5. **Thứ tự:** có cần thứ tự theo key (ví dụ một thiết bị) hay toàn cục? Tăng concurrency có làm sai thứ tự update không?
6. **Tính đúng đắn:** duplicate, retry, timeout hoặc cancel xảy ra thì có xử lý trùng/thiếu sự kiện không? Có idempotent key hay transaction boundary?
7. **Phát tới nhiều subscribers:** một subscriber chậm có được chặn producer và các subscriber khác không? Có cần tách luồng hoặc ưu tiên không?
8. **Kết thúc:** điều kiện onComplete, onError, cancellation và shutdown; ai sở hữu executor và tài nguyên ngoài?
9. **Khả năng quan sát:** đo queue depth/lag, số demand chưa sử dụng (chỉ xem như tín hiệu giám sát), tỉ lệ drop, tốc độ phát/xử lý, latency, errors và GC.

**Một điều kiện quan trọng:** backpressure phải đi qua các stage hoặc chuyển thành một chính sách overflow có chủ đích. Nếu một stage tự sinh vô hạn tasks sang executor khác rồi báo hoàn thành nhận input, toàn bộ luồng có thể lại phình ra trong queue của executor đó.

## 10. Phân biệt việc “phù hợp với event pipeline” và việc “dùng Flow”

Event pipeline là **kiến trúc**; `Flow` là **một tập giao diện Java** để liên kết producer và consumer có demand. Bạn có thể có event pipeline với bounded `BlockingQueue`, actor/message loop hoặc giao diện tự định nghĩa; ngược lại, dùng `Flow` cho một đoạn rất nhỏ không tự làm cả hệ thống trở thành một kiến trúc event-driven.

| Nhu cầu | Lựa chọn khởi đầu nên cân nhắc |
|---|---|
| Một lệnh gọi cần kết quả ngay, logic ngắn | Hàm đồng bộ/`CompletableFuture` khi thực sự cần async |
| Xử lý batch hữu hạn trong bộ nhớ | Vòng lặp hoặc Java `Stream` |
| Producer–consumer một kênh, yêu cầu giới hạn queue rõ | `ArrayBlockingQueue` hoặc `BlockingQueue` hữu hạn |
| Nhiều stage dòng sự kiện, bên nhận cần điều tiết demand | `Flow.Publisher/Subscriber/Processor` |
| Nhiều công việc độc lập với số worker hữu hạn | `ExecutorService` với backlog và timeout kiểm soát |
| Rất nhiều tác vụ blocking I/O độc lập trên Java 21 | Virtual threads với giới hạn kết nối/tài nguyên thực |
| Cần replay, durable delivery, multi-process/multi-host | Storage/broker được thiết kế riêng; có thể adapter sang Flow ở bên trong JVM |

Các cơ chế có thể kết hợp, nhưng càng nhiều tầng concurrency càng khó hiểu thời điểm kết thúc và lỗi. Chọn cấu trúc tối thiểu giải quyết đúng điểm nghẽn đã đo.

## 11. Sai lầm phổ biến

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
|---|---|---|
| Cho rằng dùng `Flow` thì event source tự giảm tốc | Source không biết demand nếu adapter không chuyển tín hiệu | Thiết kế source pull hoặc overflow policy |
| Subscriber gọi `request(Long.MAX_VALUE)` bất kể tải | Mất tín hiệu giới hạn nhu cầu | Request theo batch/công suất xử lý |
| Dùng buffer không giới hạn ở một stage | Có thể OOM khi downstream chậm | Đặt quota rõ từng queue/window |
| Cho rằng `submit` luôn không chặn | Có thể chờ buffer rảnh | Chọn `submit`/`offer` theo yêu cầu mất dữ liệu và timeout |
| Bỏ qua exceptions trong `onNext` | Lỗi khó được quan sát hoặc làm mất subscription | Terminal handling và cleanup rõ ràng |
| Không gửi `onComplete` hoặc `close()` | Subscriber chờ mãi nếu nguồn đã hết | Hoàn tất và chờ terminal signal đúng vòng đời |
| Không xử lý `cancel` | Nguồn/stage vẫn chiếm tài nguyên | Lan cancellation ngược các stages và đóng tài nguyên |
| Gửi vô hạn việc tới pool bên trong `onNext` | Queue executor phình to dù Flow có demand | Limit số tác vụ in-flight và điều tiết upstream |
| Cần replay mà chỉ dùng `SubmissionPublisher` | Dữ liệu có thể mất khi JVM dừng | Durable storage/ack/retry rõ ràng |
| Giả định mọi subscribers xử lý cùng nhịp | Một consumer chậm có thể gây backpressure cho producer | Đo lag từng subscription, chia kênh khi cần |
| Dùng parallelism để sửa nghẽn I/O phía sau | Database/API vẫn có quota cố định | Giới hạn theo resource và tối ưu bottleneck thực |
| Cho rằng backpressure = exactly-once | Demand không bảo đảm durability/idempotency | Thiết kế business acknowledgment và xử lý trùng |

## 12. Phương pháp ra quyết định trong thực tế

Bắt đầu từ **bài toán và tốc độ dữ liệu**, không từ tên thư viện:

1. **Xác định mức độ liên tục:** có dữ liệu streaming hay chỉ là collection hữu hạn?
2. **Đo chênh lệch tốc độ:** producer/consumer events per second, burst peak, average processing latency; nếu tốc độ gần nhau và dữ liệu ít, mô hình đơn giản có thể đủ.
3. **Phân tích backpressure:** có thể chặn upstream không? Nếu không, mất dữ liệu có được phép không, cần buffer lâu bao nhiêu?
4. **Xác định semantic:** ordering, idempotency, retry, cancellation, delivery và persistence.
5. **Chọn mức abstraction:** stream tuần tự, queue hữu hạn, `ExecutorService`, `Flow` hay giao thức external. Chỉ thêm nhiều stage khi có lợi ích về logic hoặc hiệu năng.
6. **Đặt budgets:** buffer capacity, max in-flight tasks, CPU threads/connections, timeout và dung lượng state tổng hợp.
7. **Kiểm thử quá tải trước production:** subscriber nhận chậm, producer burst, lỗi giữa pipeline, cancellation, executor shutdown, một subscriber đứng hẳn, re-subscribe và lỗi logic downstream.
8. **Quan sát:** throughput, end-to-end latency, lag/buffer occupancy, drops, retries, allocation, memory và mức sử dụng executor. Số sự kiện đang chờ phải hữu hạn theo policy.

Một pipeline nên có **hợp đồng xác định khi nhanh và khi quá tải**. Nếu throughput cao trong benchmark bình thường nhưng burst lớn làm backlog tăng không giới hạn, pipeline chưa hoàn chỉnh.

### Tự kiểm tra kiến thức

1. Một dịch vụ chỉ nhận vài lệnh đồng bộ mỗi giây, xử lý 3 phép tính trong RAM: vì sao event pipeline chưa chắc cần thiết?
2. `Subscriber.request(5)` có buộc Publisher phải gửi đủ 5 phần tử ngay không?
3. Subscriber đã `request(2)`, producer `submit` 3 phần tử vào `SubmissionPublisher`. Phần tử 3 có thể tồn tại ở đâu trước khi được request thêm?
4. Nếu upstream tạo 500 events/giây, downstream xử lý 100 events/giây và upstream không thể dừng, tại sao chỉ tăng RAM buffer không giải quyết lâu dài?
5. `Flow` có tự lưu sự kiện để replay sau khi JVM restart không?
6. Vì sao `request(Long.MAX_VALUE)` không nên mặc định dùng cho một consumer có quota I/O hữu hạn?
7. Nếu stage A nhận có demand nhưng nộp toàn bộ input vào một executor có queue vô hạn, liệu backpressure đã được bảo toàn đến stage B?
8. Hai subscribers dùng cùng `SubmissionPublisher` nhưng một bên rất chậm, hành vi `submit` nào cần được tính đến?

**Đáp án định hướng:** (1) overhead và phức tạp vượt lợi ích; (2) không, đó là mức cho phép; (3) buffer của subscription; (4) backlog vẫn tăng, cần slow source/drop/durable queue/công suất xử lý; (5) không; (6) mất giới hạn nhu cầu trong khi tài nguyên vẫn hữu hạn; (7) không; (8) submit có thể bị chặn bởi buffer đầy của subscriber chậm.

### Tài liệu tham khảo chính thức

- [Java SE 21 — `Flow`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html): Publisher–Subscriber interfaces, demand và hướng dẫn cơ bản.
- [Java SE 21 — `Flow.Publisher`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Publisher.html): hợp đồng phát, thứ tự tín hiệu, terminal signals.
- [Java SE 21 — `Flow.Subscription`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html): `request`, `cancel`, demand.
- [Java SE 21 — `SubmissionPublisher`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html): executor, buffer từng subscription, `submit`, `offer`, `close`.
- [Java SE 21 — `BlockingQueue`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html): lựa chọn nhẹ hơn cho producer–consumer có queue hữu hạn.