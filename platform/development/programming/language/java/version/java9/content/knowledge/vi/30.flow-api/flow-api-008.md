# Tuần tự hóa tín hiệu cho từng Subscriber trong Java Flow

## 1. Tuần tự hóa tín hiệu là gì?

Java Flow là API reactive streams được đưa vào JDK từ Java 9. Publisher phát dữ liệu, Subscriber nhận dữ liệu và Subscription điều phối nhu cầu nhận. Một Publisher có thể phát tín hiệu từ nhiều luồng hoặc sử dụng executor để gọi Subscriber bất đồng bộ.

Dù callback có thể được thực thi trên nhiều thread, Publisher phải bảo đảm các lời gọi tín hiệu dành cho cùng một đăng ký Subscriber được tuần tự hóa. Các phương thức onSubscribe, onNext, onError và onComplete không được chồng lấn nhau; tín hiệu trước phải có quan hệ happens-before với tín hiệu sau.

Điều này có nghĩa:

- onNext của cùng Subscriber không chạy đồng thời ở hai thread.
- onError hoặc onComplete chỉ đến sau những onNext đã được phát trước đó.
- Không có onNext mới sau tín hiệu kết thúc onError hoặc onComplete.
- onSubscribe phải được gọi trước các tín hiệu còn lại của đăng ký đó.
- Publisher có thể dùng các thread khác nhau cho các callback kế tiếp, miễn là chúng được gọi tuần tự.

Tuần tự hóa là bảo đảm về thứ tự và việc không gọi chồng lấn. Nó không yêu cầu mọi callback phải chạy trên cùng một thread.

## 2. Phạm vi bảo đảm: từng Subscriber, không phải toàn bộ Publisher

Một Publisher có thể phục vụ nhiều Subscriber. Mỗi Subscriber có Subscription và nhu cầu nhận dữ liệu riêng. Publisher có thể xử lý hai Subscriber đồng thời để tận dụng nhiều thread.

Ví dụ, trong cùng một thời điểm:

- Subscriber A đang xử lý onNext trên thread thứ nhất.
- Subscriber B đang xử lý onNext trên thread thứ hai.
- Subscriber A không được nhận thêm một callback khác trước khi callback hiện tại của A kết thúc.

Vì vậy, tuần tự hóa áp dụng riêng cho luồng tín hiệu của từng đăng ký Subscriber. Nó không tạo ra một hàng đợi callback toàn cục cho tất cả Subscriber.

Nếu cùng một đối tượng Subscriber được đăng ký độc lập với nhiều Publisher, mỗi Publisher quản lý luồng tín hiệu của đăng ký riêng. Không nên giả định rằng các đăng ký độc lập đó có một thứ tự toàn cục chung. Nếu chúng cùng sửa một trạng thái dùng chung, Subscriber phải tự đồng bộ trạng thái đó.

Cũng cần phân biệt tuần tự hóa callback với thứ tự dữ liệu đầu vào. Khi nhiều producer gọi submit đồng thời, thứ tự giữa các lần gửi cạnh tranh có thể không xác định. Publisher phải tuần tự hóa các tín hiệu đã chọn để gửi cho từng Subscriber, nhưng ứng dụng cần một điểm sắp thứ tự riêng nếu nghiệp vụ yêu cầu thứ tự toàn cục xác định.

## 3. Vòng đời tín hiệu của một đăng ký

Một đăng ký Flow thông thường có trình tự:

1. Publisher gọi onSubscribe(subscription).
2. Subscriber gọi request(n) để yêu cầu số phần tử muốn nhận.
3. Publisher gọi onNext(item) theo nhu cầu đã được cấp.
4. Publisher kết thúc bằng đúng một tín hiệu terminal: onComplete() hoặc onError(error).

onSubscribe phải đến trước onNext, onError hoặc onComplete. Subscriber có thể gọi request ngay bên trong onSubscribe; Publisher phải xử lý yêu cầu đó mà vẫn giữ thứ tự tín hiệu.

onComplete và onError là tín hiệu kết thúc. Sau khi một tín hiệu terminal được gửi, Publisher không được tiếp tục phát onNext cho đăng ký đó. Một đăng ký không được kết thúc bằng cả onComplete lẫn onError.

Các callback phải được tuần tự hóa ngay cả khi Publisher nhận yêu cầu từ nhiều thread. Ví dụ, một thread gọi request trong khi thread khác phát dữ liệu; Publisher phải phối hợp để không gọi onNext chồng lên onSubscribe hoặc một onNext đang chạy.

## 4. Tuần tự hóa và backpressure

Flow không chỉ quy định thứ tự callback mà còn quy định số lượng phần tử Subscriber đã yêu cầu.

Subscription.request(n) biểu thị nhu cầu nhận thêm n phần tử. Publisher không được gửi nhiều onNext hơn nhu cầu còn lại. Subscriber có thể yêu cầu thêm trong onNext khi đã xử lý xong hoặc có khả năng tiếp nhận thêm dữ liệu.

Ví dụ:

~~~java
@Override
public void onSubscribe(Flow.Subscription subscription) {
    this.subscription = subscription;
    subscription.request(10);
}

@Override
public void onNext(Item item) {
    process(item);
    subscription.request(1);
}
~~~

Đây là cách yêu cầu ban đầu 10 phần tử rồi bổ sung một đơn vị sau mỗi lần xử lý. Trong ứng dụng thực tế, nên gom yêu cầu theo lô để giảm số lần gọi request.

request(n) phải nhận n dương. Nếu Subscriber gọi request với giá trị không hợp lệ, Publisher phải xử lý theo hợp đồng Flow, thông thường kết thúc đăng ký bằng IllegalArgumentException qua onError.

Tuần tự hóa và backpressure giải quyết hai vấn đề khác nhau:

- Tuần tự hóa bảo đảm các callback không chồng lấn và giữ thứ tự.
- Backpressure giới hạn lượng dữ liệu Publisher được phép phát theo nhu cầu Subscriber.

Một Publisher có thể tuần tự hóa hoàn hảo nhưng vẫn tiêu thụ quá nhiều bộ nhớ nếu xếp hàng vô hạn các phần tử trong khi Subscriber xử lý chậm. Cần giới hạn hàng đợi và xác định chính sách khi vượt dung lượng.

## 5. Vì sao không được gọi onNext đồng thời?

Giả sử Subscriber cập nhật một bộ đếm và một danh sách:

~~~java
@Override
public void onNext(Event event) {
    count++;
    events.add(event);
}
~~~

Nếu hai onNext chạy đồng thời, count có thể bị mất cập nhật và danh sách có thể bị truy cập không an toàn. Publisher tuần tự hóa callback giúp Subscriber xử lý lần lượt từng sự kiện mà không cần khóa riêng cho trạng thái chỉ được truy cập từ một đăng ký.

Tuy nhiên, Subscriber vẫn có thể cần đồng bộ nếu:

- Cùng đối tượng Subscriber được nhiều đăng ký độc lập sử dụng.
- Callback khởi chạy công việc bất đồng bộ rồi công việc đó sửa cùng trạng thái.
- Trạng thái được đọc hoặc ghi từ thread bên ngoài Subscriber.
- Subscriber chia sẻ tài nguyên với thành phần khác.

Không nên hiểu tuần tự hóa callback là mọi dữ liệu bên trong ứng dụng đều tự động thread-safe.

## 6. Callback tuần tự có thể chạy trên các thread khác nhau

Publisher có thể dùng executor để lập lịch tín hiệu. Callback onNext đầu tiên có thể chạy trên worker-1, callback kế tiếp chạy trên worker-3. Điều cần giữ là callback trước phải hoàn tất trước callback tiếp theo của cùng đăng ký.

Do đó, không nên lưu trạng thái phụ thuộc thread trong ThreadLocal với giả định mọi callback của một Subscriber luôn quay lại cùng thread. Nếu trạng thái cần tồn tại xuyên suốt các tín hiệu, hãy đặt nó trong đối tượng Subscriber hoặc một context riêng.

Hãy tránh giữ khóa nội bộ của Publisher trong lúc gọi callback của Subscriber. Callback là mã do bên ngoài cung cấp và có thể gọi ngược request(), cancel() hoặc kích hoạt thao tác khác. Gọi callback khi đang giữ khóa có thể tạo deadlock hoặc làm chậm toàn bộ hệ thống.

## 7. Xử lý request reentrant và callback gọi ngược

Subscriber thường gọi request() ngay trong onSubscribe hoặc onNext. Đây là hành vi hợp lệ và Publisher phải xử lý được yêu cầu phát sinh ngay trong callback.

Một Publisher tự viết không nên triển khai request(n) bằng cách gọi onNext đệ quy ngay lập tức. Nếu onNext gọi request() lần nữa, Publisher có thể tạo chuỗi callback lồng nhau, làm tăng stack và phá vỡ tính tuần tự mà thiết kế mong muốn.

Một cách triển khai an toàn hơn là dùng hàng đợi và một vòng lặp drain cho mỗi Subscription:

- Producer thêm phần tử vào hàng đợi.
- request(n) cập nhật bộ đếm demand.
- Một cờ work-in-progress hoặc cơ chế tương đương bảo đảm chỉ có một drain loop hoạt động cho Subscription tại một thời điểm.
- Drain loop lấy phần tử khi demand còn, sau đó gọi onNext tuần tự.
- Yêu cầu mới trong callback chỉ cập nhật trạng thái; drain loop hiện tại sẽ xử lý tiếp sau khi callback trả về.
- Khi queue đã rỗng và có tín hiệu terminal đang chờ, drain loop phát onComplete hoặc onError đúng một lần.

Không giữ monitor hoặc khóa queue trong lúc gọi onNext. Hãy lấy trạng thái cần thiết dưới khóa, nhả khóa rồi mới gọi mã Subscriber. Sau callback, cập nhật trạng thái và tiếp tục vòng lặp.

## 8. Xử lý lỗi và tín hiệu kết thúc

Nếu Publisher gặp lỗi trong quá trình phát dữ liệu, nó gửi onError(error) cho Subscriber. Tín hiệu này phải được tuần tự hóa sau các onNext đã được phát trước đó và kết thúc luồng tín hiệu của đăng ký.

onComplete biểu thị Publisher đã phát xong dữ liệu bình thường. Sau onComplete, không gửi thêm onNext hoặc onError cho đăng ký đó.

Subscriber nên xử lý lỗi trong onError và giải phóng tài nguyên mà nó sở hữu. Không nên ném lỗi nghiệp vụ từ onNext rồi kỳ vọng Publisher tự chuyển lỗi đó thành onError theo một cách tùy ý. Hãy bắt lỗi có thể dự đoán và quyết định rõ việc tiếp tục, cancel hoặc báo lỗi.

Ví dụ:

~~~java
@Override
public void onError(Throwable error) {
    try {
        logFailure(error);
    } finally {
        releaseResources();
    }
}

@Override
public void onComplete() {
    releaseResources();
}
~~~

Trong ứng dụng thực tế, releaseResources nên an toàn khi chỉ được gọi một lần hoặc có cơ chế bảo vệ để tránh đóng cùng tài nguyên nhiều lần.

## 9. Hủy Subscription và các race condition

Subscriber gọi Subscription.cancel() để thông báo không muốn nhận thêm dữ liệu. Publisher nên dừng việc phát thêm tín hiệu cho đăng ký đó và giải phóng hàng đợi hoặc tài nguyên liên quan.

Cancellation có thể xảy ra trong khi Publisher đang chuẩn bị onNext. Một callback đã bắt đầu có thể vẫn cần hoàn tất. Vì vậy, đừng thiết kế logic dựa trên giả định cancel() sẽ làm callback đang chạy biến mất tức thì.

Các tình huống cần xử lý:

- cancel() được gọi trong onNext.
- cancel() xảy ra đồng thời với producer đang thêm phần tử.
- onError cạnh tranh với việc đóng Publisher bình thường.
- Subscriber yêu cầu thêm dữ liệu trong lúc tín hiệu terminal đang được chuẩn bị.
- Subscriber xử lý chậm khiến hàng đợi tăng.
- Executor từ chối tác vụ khi Publisher đang đóng.

Mỗi Subscription cần một trạng thái terminal/cancelled rõ ràng và chỉ cho phép một đường đi phát tín hiệu kết thúc. Việc chuyển trạng thái phải có tính nguyên tử hoặc được bảo vệ bằng cơ chế đồng bộ thích hợp.

## 10. Dùng SubmissionPublisher để có triển khai chuẩn của JDK

SubmissionPublisher là một triển khai Flow.Publisher có sẵn từ Java 9. Nó quản lý buffer riêng cho từng Subscriber và lập lịch các tín hiệu bất đồng bộ thông qua Executor.

Ví dụ khởi tạo:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(4);
SubmissionPublisher<String> publisher =
        new SubmissionPublisher<>(executor, 64);
~~~

Sau đó đăng ký Subscriber và gửi dữ liệu:

~~~java
publisher.subscribe(subscriber);
publisher.submit("first");
publisher.submit("second");
publisher.close();
~~~

SubmissionPublisher quản lý việc phân phối tín hiệu theo hợp đồng Flow. Mỗi Subscriber nhận các callback theo thứ tự và không bị gọi chồng lấn trong cùng đăng ký, dù executor có nhiều worker.

Một số thao tác chính:

| API | Ý nghĩa |
|---|---|
| subscribe(subscriber) | Đăng ký Subscriber |
| submit(item) | Gửi phần tử; có thể chờ khi buffer đầy |
| offer(item, handler) | Gửi phần tử với chính sách xử lý khi không thể xếp hàng ngay |
| close() | Đóng Publisher bình thường sau các phần tử đã gửi |
| closeExceptionally(error) | Đóng Publisher bằng lỗi |
| estimateMaximumLag() | Ước lượng độ trễ lớn nhất của Subscriber |
| estimateMinimumDemand() | Ước lượng nhu cầu nhỏ nhất của các Subscriber |

submit có thể chặn producer khi buffer của Subscriber chậm đã đầy. offer cho phép định nghĩa cách xử lý khi không thể xếp hàng ngay, ví dụ bỏ phần tử hoặc thử lại theo chính sách của ứng dụng. Cần cân nhắc kỹ vì bỏ phần tử có thể làm mất dữ liệu nghiệp vụ.

SubmissionPublisher phù hợp khi cần một Publisher bất đồng bộ có buffer và cơ chế phân phối được JDK cung cấp. Nếu cần quy tắc phát dữ liệu đặc thù, hãy kiểm tra kỹ hợp đồng Flow trước khi tự viết Publisher.

## 11. Ví dụ hoàn chỉnh: nhiều producer, từng Subscriber vẫn tuần tự

Ví dụ sau gửi 100 phần tử từ hai producer đồng thời đến hai Subscriber. Mỗi Subscriber đo số callback onNext đang chạy cùng lúc. Kết quả mong đợi là mỗi Subscriber nhận đủ 100 phần tử và số callback đồng thời lớn nhất luôn bằng 1.

**Tệp FlowSignalSerializationDemo.java:**

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.Flow;

public class FlowSignalSerializationDemo {
    private static final class TrackingSubscriber
            implements Flow.Subscriber<Integer> {
        private final String name;
        private final CountDownLatch terminal;
        private final AtomicInteger active = new AtomicInteger();
        private final AtomicInteger maximumActive = new AtomicInteger();
        private final AtomicInteger received = new AtomicInteger();
        private volatile Throwable failure;

        TrackingSubscriber(String name, CountDownLatch terminal) {
            this.name = name;
            this.terminal = terminal;
        }

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            subscription.request(Long.MAX_VALUE);
        }

        @Override
        public void onNext(Integer item) {
            int current = active.incrementAndGet();
            maximumActive.accumulateAndGet(current, Math::max);
            try {
                received.incrementAndGet();
                try {
                    Thread.sleep(1);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    failure = e;
                }
            } finally {
                active.decrementAndGet();
            }
        }

        @Override
        public void onError(Throwable error) {
            failure = error;
            terminal.countDown();
        }

        @Override
        public void onComplete() {
            terminal.countDown();
        }

        void verify() {
            if (failure != null) {
                throw new IllegalStateException(name + " failed", failure);
            }
        }

        int received() {
            return received.get();
        }

        int maximumActive() {
            return maximumActive.get();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService signalExecutor = Executors.newFixedThreadPool(4);
        ExecutorService producers = Executors.newFixedThreadPool(2);
        CountDownLatch terminal = new CountDownLatch(2);
        TrackingSubscriber first = new TrackingSubscriber("A", terminal);
        TrackingSubscriber second = new TrackingSubscriber("B", terminal);
        SubmissionPublisher<Integer> publisher =
                new SubmissionPublisher<>(signalExecutor, 32);

        try {
            publisher.subscribe(first);
            publisher.subscribe(second);

            Future<?> producerA = producers.submit(() -> {
                for (int i = 0; i < 50; i++) {
                    publisher.submit(i);
                }
            });
            Future<?> producerB = producers.submit(() -> {
                for (int i = 50; i < 100; i++) {
                    publisher.submit(i);
                }
            });

            producerA.get();
            producerB.get();
            publisher.close();

            if (!terminal.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Subscribers did not terminate");
            }

            first.verify();
            second.verify();
            System.out.println("subscriber A received: " + first.received());
            System.out.println("subscriber A max concurrent callbacks: "
                    + first.maximumActive());
            System.out.println("subscriber B received: " + second.received());
            System.out.println("subscriber B max concurrent callbacks: "
                    + second.maximumActive());
        } finally {
            if (!publisher.isClosed()) {
                publisher.close();
            }
            producers.shutdownNow();
            signalExecutor.shutdown();
            if (!signalExecutor.awaitTermination(10, TimeUnit.SECONDS)) {
                signalExecutor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch với API Java 9 và chạy trên JDK 17 trở lên:

~~~bash
javac --release 9 -Xlint:all FlowSignalSerializationDemo.java
java FlowSignalSerializationDemo
~~~

Output:

~~~text
subscriber A received: 100
subscriber A max concurrent callbacks: 1
subscriber B received: 100
subscriber B max concurrent callbacks: 1
~~~

Hai producer gửi dữ liệu đồng thời nên không nên dựa vào thứ tự xen kẽ giữa các giá trị của chúng. Điều ví dụ kiểm tra là mỗi Subscriber nhận đủ số phần tử và không có hai callback onNext chồng lấn trong cùng Subscriber.

Executor có bốn worker để Publisher có khả năng xử lý các Subscriber độc lập trên những thread khác nhau. Bộ đếm active và maximumActive được đặt riêng trong từng Subscriber, vì thế kết quả bằng 1 chứng minh không có callback đồng thời trong mỗi đăng ký.

## 12. Lỗi thường gặp

- **Cho rằng tuần tự hóa yêu cầu cùng một thread:** hợp đồng yêu cầu tín hiệu không chồng lấn và có thứ tự; thread thực thi có thể thay đổi.
- **Dùng một khóa toàn cục cho tất cả Subscriber:** làm mất khả năng xử lý song song giữa các đăng ký độc lập và có thể gây nghẽn.
- **Gọi onNext trực tiếp từ nhiều producer:** có thể tạo callback đồng thời. Hãy dùng queue và một drain loop cho mỗi Subscription.
- **Gọi callback khi đang giữ khóa nội bộ:** callback có thể gọi ngược request hoặc cancel, dẫn đến deadlock.
- **Gọi onNext đệ quy từ request:** dễ tạo callback lồng nhau và làm phức tạp thứ tự tín hiệu. Đưa yêu cầu vào drain loop.
- **Bỏ qua demand:** Publisher không được phát vượt số phần tử Subscriber đã yêu cầu.
- **Không giới hạn queue:** Subscriber chậm có thể khiến bộ nhớ tăng không giới hạn. Dùng buffer có giới hạn và chính sách backpressure.
- **Cho rằng các producer đồng thời có thứ tự cố định:** thứ tự giữa các lần gửi cạnh tranh không được bảo đảm nếu ứng dụng không sắp thứ tự trước.
- **Phát onNext sau onComplete hoặc onError:** terminal signal kết thúc đăng ký; không phát thêm tín hiệu dữ liệu.
- **Giả định cancel dừng callback đang chạy ngay lập tức:** callback đã bắt đầu có thể vẫn hoàn tất; thiết kế trạng thái và cleanup an toàn với race.
- **Dùng chung một Subscriber cho nhiều đăng ký mà không đồng bộ:** tuần tự hóa của từng đăng ký không tạo ra một thứ tự chung giữa các Publisher độc lập.

## 13. Chọn cách triển khai

| Nhu cầu | Cách làm |
|---|---|
| Phát dữ liệu bất đồng bộ đến nhiều Subscriber | SubmissionPublisher |
| Tuần tự hóa callback trong Publisher tự viết | Queue và drain loop riêng cho từng Subscription |
| Phát theo nhu cầu Subscriber | Theo dõi demand từ request(n) |
| Ngăn queue tăng không giới hạn | Buffer hữu hạn và backpressure |
| Xử lý nhiều Subscriber song song | Executor nhiều worker, trạng thái độc lập từng Subscriber |
| Giữ thứ tự khi nhiều producer cạnh tranh | Sắp thứ tự tại một điểm phát duy nhất hoặc gắn sequence number |
| Kết thúc luồng bình thường | onComplete |
| Kết thúc luồng do lỗi | onError |
| Ngừng nhận dữ liệu | Subscription.cancel |

## 14. Ghi nhớ

Flow yêu cầu Publisher tuần tự hóa onSubscribe, onNext, onError và onComplete cho từng đăng ký Subscriber. Các callback của cùng đăng ký không được chồng lấn và phải giữ quan hệ thứ tự, nhưng có thể chạy trên các thread khác nhau. Những Subscriber độc lập vẫn có thể được xử lý song song. Khi tự viết Publisher, hãy dùng queue và drain loop riêng cho từng Subscription, tôn trọng demand, không gọi callback khi giữ khóa và xử lý terminal/cancel an toàn. SubmissionPublisher là lựa chọn có sẵn trong JDK khi cần phân phối bất đồng bộ theo hợp đồng Flow.
