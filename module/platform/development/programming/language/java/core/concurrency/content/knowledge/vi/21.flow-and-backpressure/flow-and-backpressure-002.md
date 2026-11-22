# Publisher, Subscriber, Subscription và Processor trong Java Flow

## 1. Flow giải quyết vấn đề gì?

Khi một bên tạo dữ liệu nhanh hơn bên tiêu thụ, việc **đẩy dữ liệu không giới hạn** có thể làm hàng đợi ngày càng lớn, tăng RAM, độ trễ và cuối cùng gây quá tải. Trong lập trình đồng thời, ta cần một giao thức để bên nhận thông báo mình sẵn sàng xử lý bao nhiêu phần tử. Cơ chế đó gọi là **backpressure**.

Từ Java 9, package `java.util.concurrent` cung cấp lớp `Flow` với bốn interface lồng nhau:

- `Flow.Publisher<T>` — nơi phát các phần tử kiểu `T`.
- `Flow.Subscriber<T>` — nơi nhận và xử lý các phần tử kiểu `T`.
- `Flow.Subscription` — kết nối riêng giữa một publisher và một subscriber, mang tín hiệu **demand** (nhu cầu nhận thêm) và hủy.
- `Flow.Processor<T,R>` — vừa là subscriber nhận `T`, vừa là publisher phát `R`, thường dùng để biến đổi/lọc dữ liệu trong một pipeline.

`Flow` định nghĩa **giao thức và trách nhiệm giữa các thành phần**, không tự cung cấp hệ thống xử lý data stream hoàn chỉnh. Một triển khai sẵn có của JDK là `SubmissionPublisher<T>`. Các interface của Flow tương ứng với mô hình Reactive Streams; bài này chỉ sử dụng Java SE, không cần Spring hoặc thư viện reactive bổ sung.

Hình dung pipeline:

```text
       dữ liệu vào                          dữ liệu đầu ra
   ┌────────────────┐   onNext(T)   ┌───────────────────┐   onNext(R)  ┌────────────────┐
   │ Publisher<T>   │ ────────────► │ Processor<T,R>    │ ───────────►│ Subscriber<R>  │
   └────────────────┘               └───────────────────┘             └────────────────┘
            ▲                               ▲                                  │
            │ request(n)                    │ request(n)                       │
            └── Subscription đầu nguồn ────┘   Subscription đầu ra ◄──────────┘
```

Ở đường bên trái, processor là **subscriber** của publisher nguồn; ở đường bên phải, nó là **publisher** cho subscriber cuối. Hai bên có **subscription riêng**. Processor phải quyết định cách cân đối demand ở hai phía; interface không tự làm công việc đó.

## 2. Bốn vai trò và API quan trọng

| Vai trò | Phương thức | Trách nhiệm chính |
| --- | --- | --- |
| `Publisher<T>` | `subscribe(Subscriber<? super T>)` | Nhận đăng ký và thiết lập một subscription; phát tín hiệu phù hợp giao thức |
| `Subscriber<T>` | `onSubscribe(Subscription)` | Nhận subscription trước mọi callback khác của subscription đó; thường gọi `request(n)` |
| `Subscriber<T>` | `onNext(T)` | Nhận một phần tử đã được yêu cầu |
| `Subscriber<T>` | `onError(Throwable)` | Nhận tín hiệu lỗi kết thúc, không còn callback tiếp theo của subscription |
| `Subscriber<T>` | `onComplete()` | Nhận tín hiệu kết thúc bình thường, không còn callback tiếp theo của subscription |
| `Subscription` | `request(long n)` | Tăng demand còn thiếu thêm `n`; `n` phải dương |
| `Subscription` | `cancel()` | Yêu cầu dừng nhận; mang tính best-effort |
| `Processor<T,R>` | Kế thừa hai nhóm API | Nhận `T` từ upstream, xử lý và phát `R` xuống downstream |

**Chú ý đến kiểu generic:** `Publisher<? extends T>` tạo dữ liệu; `Subscriber<? super T>` có thể nhận `T`. `Processor<Integer,String>` nhận `Integer` từ upstream rồi phát `String` cho downstream. `Subscription` không mang kiểu dữ liệu vì chỉ điều khiển số phần tử được nhận.

### Một subscription gắn với một mối quan hệ phát–nhận

Một publisher có thể có nhiều subscriber. Mỗi subscriber thường có một `Subscription` và lượng demand riêng. Nếu subscriber A đã yêu cầu 10 phần tử, điều đó **không cấp thêm quyền nhận** cho subscriber B. Publisher cần tuân thủ nhu cầu riêng của từng subscriber.

`Publisher.subscribe(...)` có thể thiết lập kết nối bất đồng bộ; không thể mặc định rằng sau khi method trả về thì subscriber đã xử lý `onSubscribe` hoặc sẵn sàng nhận `onNext`. Với `SubmissionPublisher`, quá trình thông báo subscriber được lên lịch bất đồng bộ qua `Executor`.

## 3. Vòng đời và thứ tự tín hiệu

Một subscription điển hình diễn ra như sau:

```text
Publisher                      Subscriber
    │                               │
    │  onSubscribe(subscription)     │
    ├──────────────────────────────►│
    │             request(2)         │
    │◄──────────────────────────────┤
    │                               │
    │  onNext(itemA)                │
    ├──────────────────────────────►│   demand còn 1
    │  onNext(itemB)                │
    ├──────────────────────────────►│   demand còn 0
    │             request(1)         │
    │◄──────────────────────────────┤
    │  onNext(itemC)                │
    ├──────────────────────────────►│
    │  onComplete()                  │
    ├──────────────────────────────►│
    │                               │   kết thúc
```

Những bảo đảm thiết yếu:

1. `onSubscribe` được gửi trước bất kỳ `onNext`, `onError` hoặc `onComplete` nào của subscription tương ứng.
2. `onNext` chỉ được phát khi có demand được yêu cầu trước đó, và mỗi phần tử tiêu thụ **một** đơn vị demand.
3. Với một subscription, callback tới subscriber được gọi **tuần tự, đúng thứ tự**. Chúng có quan hệ *happens-before* theo bảo đảm giao thức; một subscriber nhận **nhiều** subscription hoặc đồng thời có truy cập từ bên ngoài vẫn cần xem lại đồng bộ.
4. Một subscription kết thúc qua `onError` **hoặc** `onComplete`, và sau tín hiệu kết thúc không có callback nào khác từ subscription đó.
5. `cancel()` yêu cầu ngừng nhận nhưng không đồng nghĩa một lời hứa sẽ nhận `onComplete()`; có thể vẫn có ít callback đang trên đường đến sau `cancel`.
6. `onNext` không được truyền `null` như một item hợp lệ trong Flow; `SubmissionPublisher.submit(null)` ném `NullPointerException`.

Với `request(n)`, `n > 0` bổ sung số lượng phần tử được phép gửi; các lần gọi cộng dồn demand. `request(0)` hoặc `request(-1)` là lỗi giao thức và subscriber được gửi `onError(IllegalArgumentException)`. `request(Long.MAX_VALUE)` thường được xem là nhu cầu gần như vô hạn; nó **bỏ ý nghĩa điều tiết qua demand** nên chỉ dùng khi consumer thực sự có thể theo kịp hoặc đã có kiểm soát tải khác.

### Demand là tín hiệu điều khiển, không phải bộ đệm

Nếu consumer gọi `request(3)`, producer **được phép phát tối đa ba phần tử tiếp theo** trước khi có demand mới, nhưng không buộc phải phát đủ ba phần tử. Producer có thể chưa có dữ liệu, phát ít hơn rồi hoàn tất hoặc phát tín hiệu lỗi. Demand không có nghĩa ba phần tử đã được lưu sẵn ở đâu đó.

Backpressure điều tiết **số callback `onNext` được phép phát**, nhưng một publisher vẫn có thể giữ dữ liệu trong buffer nội bộ hoặc nhận dữ liệu từ nguồn ngoài trước khi downstream xử lý. Cần kiểm soát thêm sức chứa buffer, chính sách quá tải và tốc độ đầu nguồn.

## 4. Ví dụ Java 21 chạy được: đủ bốn vai trò trong một pipeline

Ví dụ này tạo chuỗi:

```text
SubmissionPublisher<Integer>          DoublerProcessor<Integer,String>        PrintSubscriber<String>
           1, 2, 3           ───────►        "value=2", "value=4", ...  ───────► output
                ^                                  ^                                |
                | upstream request(1)              | downstream request(1)          |
                └──────────────────────────────────┘◄───────────────────────────────┘
```

`SubmissionPublisher` là `Publisher` thực tế có trong JDK; `DoublerProcessor` tự triển khai `Processor` bằng cách nhận từng `Integer`, chuyển thành `String` và ủy quyền quản lý subscription đầu ra cho một `SubmissionPublisher<String>` khác. `PrintSubscriber` yêu cầu **một** phần tử mỗi lần nhận xong phần tử trước.

Lưu nguyên chương trình vào `FlowFourRolesDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class FlowFourRolesDemo {

    static final class DoublerProcessor
            implements Flow.Processor<Integer, String>, AutoCloseable {

        private final SubmissionPublisher<String> output;
        private Flow.Subscription upstream;

        DoublerProcessor(ExecutorService executor) {
            // Bản thân output sẽ cung cấp Subscription cho downstream.
            this.output = new SubmissionPublisher<>(executor, 4);
        }

        @Override
        public void subscribe(Flow.Subscriber<? super String> subscriber) {
            output.subscribe(subscriber);
        }

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            if (upstream != null) {
                subscription.cancel(); // Ví dụ chỉ hỗ trợ một upstream.
                return;
            }
            upstream = subscription;
            subscription.request(1);
        }

        @Override
        public void onNext(Integer item) {
            try {
                output.submit("value=" + (item * 2));
                upstream.request(1);
            } catch (RuntimeException ex) {
                upstream.cancel();
                output.closeExceptionally(ex);
            }
        }

        @Override
        public void onError(Throwable throwable) {
            output.closeExceptionally(throwable);
        }

        @Override
        public void onComplete() {
            output.close();
        }

        @Override
        public void close() {
            output.close();
        }
    }

    static final class PrintSubscriber implements Flow.Subscriber<String> {
        private final CountDownLatch terminal = new CountDownLatch(1);
        private Flow.Subscription subscription;
        private volatile Throwable failure;

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            subscription.request(1);
        }

        @Override
        public void onNext(String item) {
            System.out.println(item);
            subscription.request(1);
        }

        @Override
        public void onError(Throwable throwable) {
            failure = throwable;
            terminal.countDown();
        }

        @Override
        public void onComplete() {
            System.out.println("complete");
            terminal.countDown();
        }

        void awaitResult() throws InterruptedException {
            if (!terminal.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Flow pipeline timed out");
            }
            if (failure != null) {
                throw new IllegalStateException("Flow pipeline failed", failure);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try (ExecutorService executor = Executors.newFixedThreadPool(2);
             SubmissionPublisher<Integer> publisher =
                     new SubmissionPublisher<>(executor, 4);
             DoublerProcessor processor = new DoublerProcessor(executor)) {

            PrintSubscriber subscriber = new PrintSubscriber();

            // Đăng ký downstream trước, rồi mới nối nguồn vào processor.
            processor.subscribe(subscriber);
            publisher.subscribe(processor);

            for (int item = 1; item <= 3; item++) {
                publisher.submit(item);
            }

            // Không phát thêm dữ liệu; tín hiệu hoàn tất lan qua processor.
            publisher.close();

            // close() của publisher không bảo đảm subscriber đã xử lý xong.
            subscriber.awaitResult();
        }
    }
}
```

Chạy trên **JDK 21 trở lên** (không cần thư viện ngoài):

```bash
javac FlowFourRolesDemo.java
java FlowFourRolesDemo
```

Output khi không xảy ra lỗi/timeout:

```text
value=2
value=4
value=6
complete
```

Đầu ra này có thứ tự xác định nhờ tín hiệu `onNext` của từng subscription được gửi tuần tự. `CountDownLatch` đợi tín hiệu cuối thay vì đoán thời gian bằng `Thread.sleep(...)`. `try-with-resources` đảm bảo publisher, processor và executor được đóng khi kết thúc.

**Đọc code theo vai trò:**

- **Publisher:** `publisher` phát ba số nguyên, cấp phát subscription khi `processor` đăng ký; không gọi trực tiếp `subscriber.onNext(...)`.
- **Subscriber đầu vào:** `processor.onSubscribe` nhận subscription upstream và xin một phần tử. Sau `onNext`, processor chuyển đổi item rồi xin phần tử tiếp theo.
- **Processor:** biến đổi `Integer → String`; `output` giữ những phần tử đã biến đổi trong giới hạn buffer và quản lý demand downstream.
- **Subscriber cuối:** `PrintSubscriber` nhận subscription downstream, yêu cầu một item, xử lý rồi mới yêu cầu tiếp.
- **Terminal:** `publisher.close()` gửi kết thúc theo thứ tự, `processor.onComplete()` đóng output, và `PrintSubscriber.onComplete()` giải phóng latch.

**Giới hạn có chủ ý của ví dụ:** processor minh họa **một upstream**, một đường biến đổi đơn giản và delegate buffering cho `SubmissionPublisher`. Đây không phải processor tổng quát đã hoàn thiện các tình huống hủy downstream, hỗ trợ nhiều upstream, ghi nhận trạng thái lỗi phức tạp hoặc điều phối demand theo nhiều consumer. `output.submit(...)` vẫn có thể chặn nếu downstream chậm và buffer đầy. Khi xây dựng processor dùng thật, cần xác định rõ chính sách cancel, khả năng đóng tài nguyên, retry/drop và cách chuyển demand giữa hai phía.

## 5. Publisher: sản xuất và phát dữ liệu đúng giao thức

`Flow.Publisher<T>` chỉ có phương thức `subscribe(...)`. Việc thực sự đọc dữ liệu từ file/socket, lấy bản ghi DB, gọi API hoặc tạo event là trách nhiệm implementation.

Một publisher phù hợp cần:

- Cấp một `Subscription` cho mỗi subscriber được chấp nhận.
- Không phát `onNext` quá demand mà subscription đó đã nhận.
- Giữ thứ tự callback đối với mỗi subscription và kết thúc đúng một lần.
- Quản lý nguồn dữ liệu, bộ đệm, lỗi và hủy; không đợi mọi consumer vô hạn mà không có kế hoạch tài nguyên.
- Xác định rõ subscriber mới có nhận dữ liệu trước khi subscribe hay chỉ nhận dữ liệu tương lai. `SubmissionPublisher` gửi các item **được submit sau khi** subscriber đăng ký, không mặc định replay lịch sử.

### SubmissionPublisher đã cung cấp gì?

`java.util.concurrent.SubmissionPublisher<T>` là publisher bất đồng bộ sẵn có, phát các item **khác `null`** đến các subscriber hiện tại, dùng `Executor` để gửi callback. Mỗi subscriber có **buffer riêng**. Constructor có thể chỉ định `Executor` và buffer capacity; capacity thực thi có thể được làm tròn theo implementation.

```java
// Snippet: executor là Executor đã được ứng dụng tạo và quản lý.
SubmissionPublisher<String> publisher =
        new SubmissionPublisher<>(executor, 32);

publisher.subscribe(subscriber); // subscriber: Flow.Subscriber<String>
publisher.submit("event-1");
publisher.close();
```

Đoạn trên là **snippet**, vì cần khai báo/import `executor` và `subscriber` phù hợp. Một publisher chỉ có interface `Flow.Publisher` không nhất thiết có `submit()` hoặc `close()`; đó là API của `SubmissionPublisher` cụ thể.

**Sự khác nhau giữa `submit` và `offer`:**

| Phương thức | Hành vi khi buffer bị bão hòa | Cần lưu ý |
| --- | --- | --- |
| `submit(item)` | Có thể chặn **không ngắt được bằng InterruptedException** khi đợi tài nguyên buffer | Đơn giản, nhưng producer cũng có thể bị kẹt vì consumer chậm |
| `offer(item, onDrop)` | Có thể bỏ item cho một hay nhiều subscriber khi không còn khả năng cấp phát buffer | Giá trị trả về âm cho biết số lần drop, không phải “đã xử lý” |
| `offer(item, timeout, unit, onDrop)` | Chờ có hạn rồi xử lý trường hợp không còn chỗ | Handler có thể yêu cầu thử lại một lần; cần policy drop/retry/error rõ |
| `close()` | Không nhận thêm submit và gửi `onComplete` cho subscriber hiện tại | **Không** bảo đảm callback `onComplete` đã chạy xong ngay khi `close` trả về |
| `closeExceptionally(error)` | Kết thúc với tín hiệu `onError` | Dùng khi nguồn không thể tiếp tục bình thường |

`submit` trả về ước lượng **maximum lag**, không phải số item được consumer xử lý. Các phép đo như `estimateMaximumLag()` và `estimateMinimumDemand()` chủ yếu dành cho quan sát; chúng có thể phản ánh tình trạng cũ, không dùng để quyết định một thao tác check-then-act an toàn.

Điểm dễ bỏ sót: giới hạn 32 buffer là **mỗi subscriber**. Một publisher với 200 subscriber chậm không có nghĩa tổng bộ nhớ luôn bằng 32 item. Các đối tượng item có kích thước khác nhau; nhiều subscriber và nguồn phát có thể tiêu thụ nhiều bộ nhớ hơn dự kiến.

## 6. Subscriber: điều tiết nhu cầu và xử lý tín hiệu

`Flow.Subscriber<T>` gồm bốn callback. Cần thiết kế chính sách **request thêm lúc nào**:

- **`request(1)` trong `onSubscribe`, `request(1)` sau mỗi `onNext`**: dễ hiểu, số item chưa xử lý nhỏ; phù hợp với consumer đơn giản, throughput có thể bị giảm do giao tiếp demand thường xuyên.
- **Yêu cầu theo lô, ví dụ `request(32)`**: giảm số lần gửi demand, phù hợp consumer throughput cao; nhưng số item in-flight và chi phí lưu/đệm tăng, cần đo.
- **`request(Long.MAX_VALUE)`**: không tạo lực cản theo demand; chỉ phù hợp nếu hệ thống khác đã giới hạn tài nguyên và quá trình xử lý luôn theo kịp.

Khi xử lý, nên phân biệt **đã nhận item**, **đã hoàn thành xử lý item** và **đã xử lý thành công**. Nếu `onNext` chỉ đẩy item sang một asynchronous worker khác rồi xin thêm ngay, demand chỉ giới hạn số lần nhận callback, **không** giới hạn số worker đang chạy. Khi đó cần một hạn mức công việc đang xử lý và chỉ yêu cầu thêm sau khi tác vụ thực sự hoàn tất, hoặc áp dụng backpressure qua một queue có sức chứa cố định.

Không tự gọi trực tiếp `onNext`, `onError`, `onComplete` trên subscriber của người khác để “đẩy nhanh” pipeline; giao thức yêu cầu publisher/subscription điều phối callbacks. Đối với subscriber nhận **một** subscription, callbacks từ đúng subscription được bảo đảm tuần tự; nhưng thread thực thi không nhất thiết cố định, và mọi state được chia sẻ với thread khác vẫn cần bảo vệ phù hợp.

**Quản lý lỗi ở consumer:** nếu `onNext` ném exception, giao thức không đảm bảo mọi implementation tự chuyển nó thành `onError` theo cách ứng dụng mong muốn; `SubmissionPublisher` sẽ hủy subscription tương ứng và có cơ chế handler cho một số lỗi. Hãy xử lý lỗi nghiệp vụ một cách chủ động, quyết định fail stream hay giữ/retry item, và đảm bảo tài nguyên được đóng. Đừng ném exception trong `onError`/`onComplete`.

## 7. Subscription: demand và hủy theo từng subscriber

`Flow.Subscription` là **kênh điều khiển** để một subscriber nói với upstream “tôi còn có thể nhận bao nhiêu item”.

Ví dụ subscriber đã gọi `request(5)`. Publisher phát hai `onNext` thì demand chưa đáp ứng còn 3. Nếu subscriber gọi thêm `request(4)`, tổng outstanding demand là 7. Khi nhu cầu rất lớn, implementation thường dùng phép cộng bão hòa để không tràn `long`. `Long.MAX_VALUE` biểu diễn hiệu quả không giới hạn cho nhiều cách triển khai.

- `request(n <= 0)` là lỗi và sẽ dẫn tới `onError(IllegalArgumentException)` cho subscriber tương ứng.
- `cancel()` là yêu cầu ngừng nhận **best-effort**; có thể còn thông báo đang trên đường đến. Một subscription bị cancel **không bắt buộc** phát `onComplete` hay `onError`.
- Chỉ subscriber của subscription tương ứng được thiết kế để gọi `request/cancel`. Gọi chúng từ đối tượng không phải chủ sở hữu là ngoài hợp đồng sử dụng thông thường.
- Subscriber phải lưu subscription sau `onSubscribe` nếu muốn request thêm hoặc cancel sau này.
- Không đồng nhất `request(n)` với “tạo n thread”, “ghi n item vào queue” hay “consumer chắc chắn nhận đủ n item”.

**Ví dụ subscriber dừng sau ba phần tử** (snippet minh họa, không phải lớp chạy độc lập):

```java
private Flow.Subscription subscription;
private int received;

@Override
public void onSubscribe(Flow.Subscription s) {
    subscription = s;
    s.request(1);
}

@Override
public void onNext(String item) {
    use(item); // Hàm do ứng dụng định nghĩa.
    if (++received == 3) {
        subscription.cancel();
        return; // Không chờ onComplete sau cancel.
    }
    subscription.request(1);
}
```

Với ứng dụng thực, cần cân nhắc nếu lời gọi `use(item)` thất bại: có hoàn tác không, hủy hay báo lỗi, và khi nào giải phóng tài nguyên.

## 8. Processor: hai chiều demand, chuyển đổi và lỗi

`Processor<T,R>` kế thừa **`Subscriber<T>` và `Publisher<R>`**. Nó có thể map, filter, batch, aggregate, validate hoặc mã hóa dữ liệu. Điều khó nhất là **không chỉ biến đổi kiểu**, mà còn giữ đúng giao thức ở cả hai mặt:

```text
Source Publisher<T>
      │
      │ onNext(T), onComplete(), onError(...)
      ▼
Processor<T,R> [Subscriber<T>]
      │ transform/filter/buffer
      │ [Publisher<R>]
      ▼
Final Subscriber<R>
```

**Upstream subscription** điều khiển số `T` mà processor được nhận; **downstream subscription** điều khiển số `R` được phát xuống consumer. Nếu một `T` tạo ra ba `R`, không thể truyền thẳng downstream demand theo tỷ lệ 1:1. Nếu processor lọc bỏ nhiều `T`, có thể cần xin nhiều upstream item để đáp ứng một downstream item. Nếu processor gom 100 bản ghi thành một batch, giới hạn bộ nhớ và thời gian chờ của batch phải được thiết kế riêng.

Các trách nhiệm cần thiết trong processor:

1. Bảo đảm mỗi downstream subscription có demand riêng; không phát quá nhu cầu.
2. Truyền lỗi upstream xuống downstream một cách nhất quán khi pipeline không thể tiếp tục; sau lỗi không phát thêm dữ liệu.
3. Khi nguồn kết thúc, xử lý các item/buffer còn hợp lệ rồi phát `onComplete` cuối cùng.
4. Khi downstream cancel hoặc không còn người nhận, quyết định có cancel upstream, tiếp tục cho subscriber khác hay đóng nguồn tài nguyên.
5. Đặt sức chứa buffer và chiến lược quá tải: block producer, drop có chủ đích, reject hay ngừng nguồn; không để queue lớn vô hạn.
6. Xác định cách đồng bộ nếu có nhiều upstream hoặc nhiều downstream, và thứ tự các item phải được bảo tồn.

Ví dụ `DoublerProcessor` ở trên dùng `SubmissionPublisher<String>` để quản lý mặt phát. Phần nhận `Integer` chỉ request tiếp sau khi đã `submit` phần tử biến đổi. Đây là một mẫu học tập phù hợp cho mapping 1:1, nhưng không thay thế thiết kế demand theo đa số đường xử lý phức tạp.

## 9. Backpressure thực tế: xử lý chậm, buffer và executor

Giả sử publisher có tốc độ 1.000 item/giây, subscriber xử lý 100 item/giây. Hệ thống sẽ có chênh lệch trung bình khoảng 900 item/giây nếu nguồn tiếp tục tạo dữ liệu bằng tốc độ cũ. Nếu thiếu cơ chế khống chế, backlog có thể tăng liên tục.

**Flow giúp đặt nhu cầu ở ranh giới callback**, còn việc pipeline có thực sự giảm tải đầu nguồn hay không phụ thuộc cách publisher và processor được triển khai. Các chiến lược thường dùng:

| Tình huống | Hướng xử lý |
| --- | --- |
| Nguồn có thể tạm dừng (đọc từng chunk, iterator) | Chỉ đọc/tạo thêm khi có demand |
| Nguồn có tốc độ không điều khiển được (sự kiện ngoài) | Buffer hữu hạn, drop/reject có quan sát hoặc điều tiết ở cổng nhận |
| I/O chậm với SLA rõ ràng | Bounded in-flight, timeout, cancel khi cần và đo độ trễ |
| Một subscriber quá chậm trong luồng nhiều subscriber | Có policy riêng: buffer theo subscriber, drop, cô lập subscriber hoặc ngắt subscription |
| Processor có xử lý async | Yêu cầu thêm theo lượng việc thực sự hoàn thành, hoặc dùng bộ đếm in-flight/queue có chặn |

### Vai trò của Executor

`SubmissionPublisher` chuyển callbacks đến `Executor`. Hãy chọn executor phù hợp và tránh các trường hợp tự deadlock khi callback có thể chặn vì buffer đầy, trong khi mọi thread trong cùng executor đang chờ vào cùng pipeline. Với xử lý rất chậm, thiết kế cơ chế admission và tài nguyên downstream tách bạch.

Dùng virtual threads (Java 21+) có thể phù hợp cho tác vụ blocking I/O, nhưng **nhiều virtual threads không tự tạo backpressure hoặc giới hạn kết nối ngoài**. Nếu callback đưa việc sang virtual thread khác rồi lập tức request thêm, phải có hạn mức tác vụ và tài nguyên thật; nếu không backlog vẫn tăng dù mỗi virtual thread có chi phí thấp.

Không dùng `Thread.sleep` như một cơ chế backpressure. Sleep không thay đổi outstanding demand, không ràng buộc queue, cũng không bảo đảm nguồn sẽ dừng tạo dữ liệu.

## 10. Các lỗi thường gặp

**Quên gọi `request(n)` sau `onSubscribe`.** Subscriber đã đăng ký nhưng chưa cấp demand nên không nhận `onNext`; pipeline trông như “treo”. Hãy bắt đầu bằng request nhỏ và quan sát.

**Gọi `request(0)` hoặc `request(-n)` để tạm dừng.** Đây là lỗi giao thức, publisher gửi `onError`. Muốn tạm dừng, đơn giản **chưa request thêm** và quản lý outstanding demand đã cấp từ trước.

**Dùng `request(Long.MAX_VALUE)` mọi nơi.** Mất khả năng giới hạn callback theo nhu cầu downstream; dễ che giấu backlog ở các layer khác.

**Hiểu `submit` là consumer đã xử lý xong.** `SubmissionPublisher.submit` có thể chỉ mới đưa item vào buffer; `close` cũng không chờ subscriber hoàn tất. Dùng tín hiệu terminal, `CompletableFuture`, latch hoặc kết quả xử lý để chờ một cách đúng đắn.

**Giữ buffer vô hạn trong processor.** Flow interface không tự cấm một implementation lưu vô hạn item. Giới hạn capacity và xác định hành vi khi tràn.

**Không chuyển lỗi/hủy giữa hai đầu processor.** Downstream có thể chờ mãi khi upstream đã lỗi hoặc hủy; cần quy tắc terminal và cleanup rõ ràng.

**Dùng chung một state mutable cho nhiều subscription.** Callback được tuần tự **theo một subscription**, không bảo đảm đồng bộ giữa mọi subscriber và task khác. Mỗi subscription nên có state riêng hoặc phải bảo vệ shared state.

**Trả một item tới subscriber dù chưa có demand.** Custom publisher phải quản lý outstanding count; vi phạm giao thức có thể làm consumer quá tải hoặc gây lỗi khó đoán.

**Xem `cancel()` như `onComplete()`.** Cancel best-effort, không bắt buộc có terminal callback. Một consumer đợi `onComplete` sau cancel có thể chờ vô hạn.

**Tự tạo custom Publisher/Processor quá sớm.** Tự triển khai giao thức yêu cầu xử lý race giữa request/cancel/terminal, buffer và lỗi. Hãy ưu tiên thành phần JDK `SubmissionPublisher` hoặc thư viện đã kiểm chứng khi chức năng cần phức tạp hơn.

## 11. Kiểm chứng và quan sát một pipeline

Thử các tình huống có chủ đích:

1. Subscriber không request: không được nhận `onNext`.
2. Subscriber request(1): không được nhận quá một `onNext` trước khi request tiếp.
3. Gọi `request(0)`: đúng implementation phải báo lỗi giao thức, không âm thầm phát dữ liệu.
4. Publisher kết thúc bình thường: subscriber nhận `onComplete` đúng một lần, không còn `onNext` sau đó.
5. Publisher kết thúc lỗi: subscriber nhận `onError`; không đồng thời nhận `onComplete`.
6. Cancel giữa chừng: dừng phát theo best-effort, tránh chờ terminal bắt buộc.
7. Producer nhanh, consumer chậm: kiểm tra buffer giới hạn, thời gian `submit` bị chặn hoặc số item bị drop khi `offer`.
8. Processor filter/map/batch: kiểm tra đúng thứ tự, đúng số item, tính nhất quán khi upstream lỗi hoặc downstream cancel.
9. Subscriber ném exception: kiểm tra hành vi implementation, cleanup, và không rò subscription/resource.
10. Nhiều subscriber: demand, lỗi và cancel của từng subscription được quản lý độc lập.

Nên đo: tốc độ phát/nhận item, **outstanding demand** (nếu implementation có thể ghi nhận an toàn), độ trễ xử lý item, dung lượng queue/buffer, số item drop/retry, thời gian chờ `submit`, subscriptions active/cancelled và số lần lỗi terminal. Các API `estimate...` của `SubmissionPublisher` chỉ cho **ước lượng quan sát**, không phải một nguồn đồng bộ chính xác.

## 12. Ghi nhớ

- **Publisher** tạo và phát item; **Subscriber** xử lý và phát tín hiệu demand; **Subscription** là hợp đồng điều khiển cho từng cặp phát–nhận; **Processor** kết hợp hai vai trò để xây pipeline.
- `request(n)` là **quyền nhận tối đa n `onNext` thêm**, không phải cam kết sẽ nhận đủ n hoặc đã có n item trong buffer.
- `onSubscribe` đến trước các callback khác; `onError` và `onComplete` là terminal. `cancel` chỉ yêu cầu dừng, không hứa terminal callback.
- `SubmissionPublisher` cho sẵn cơ chế async delivery và buffering hữu hạn theo từng subscriber; vẫn phải lựa chọn chính sách block/drop/error và chờ kết thúc đúng cách.
- Backpressure có hiệu lực khi **toàn đường pipeline** tôn trọng demand và giới hạn nguồn/buffer/in-flight. Flow interface một mình không giải quyết tất cả bài toán quá tải.

## Tài liệu chính thức

- Oracle, [Flow API — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html): bốn interface, nguyên tắc demand và ví dụ subscriber.
- Oracle, [Publisher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Publisher.html) và [Subscriber](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html): callback, thứ tự và terminal.
- Oracle, [Subscription](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html): `request(long)`, `cancel()`, lỗi với demand không dương.
- Oracle, [Processor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Processor.html): kết hợp Subscriber và Publisher.
- Oracle, [SubmissionPublisher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html): buffer mỗi subscriber, `submit`, `offer` và vòng đời.
