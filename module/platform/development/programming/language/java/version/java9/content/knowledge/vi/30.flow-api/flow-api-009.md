# Quan hệ giữa việc đăng ký và bộ máy thực thi

Trong Flow API của Java, việc một subscriber đăng ký nhận dữ liệu và việc các callback của subscriber được chạy là hai phần liên quan nhưng có trách nhiệm khác nhau. `Publisher.subscribe(Subscriber)` thiết lập quan hệ nhận dữ liệu và khởi động giao thức `onSubscribe`/`Subscription.request(n)`. Bộ máy thực thi (executor), nếu implementation sử dụng, quyết định các tác vụ callback chạy ở đâu và theo chính sách lập lịch nào.

Phân biệt hai việc này giúp tránh giả định sai rằng gọi `subscribe` luôn tạo một thread mới, rằng `request(n)` tự chạy callback ngay lập tức, hoặc rằng mọi implementation của Flow đều phải dùng executor. Flow định nghĩa giao thức trao đổi tín hiệu và backpressure; cách triển khai việc phân phối tín hiệu thuộc về publisher cụ thể.

## 1. Các thành phần của Flow API

Flow API được giới thiệu trong Java 9, nằm trong `java.util.concurrent`. Bốn thành phần cốt lõi là:

| Thành phần | Vai trò |
|---|---|
| `Flow.Publisher<T>` | Nguồn phát các phần tử kiểu T và cho phép subscriber đăng ký |
| `Flow.Subscriber<T>` | Thành phần nhận các tín hiệu `onSubscribe`, `onNext`, `onError`, `onComplete` |
| `Flow.Subscription` | Quan hệ điều khiển giữa publisher và một subscriber; cung cấp `request(n)` và `cancel()` |
| `Flow.Processor<T,R>` | Vừa là subscriber nhận T, vừa là publisher phát R; thường dùng làm một bước trung gian |

Một subscriber không trực tiếp gọi `onNext` để lấy dữ liệu. Nó đăng ký với publisher, nhận một subscription và yêu cầu số lượng phần tử muốn nhận. Publisher chịu trách nhiệm phát tín hiệu theo giao thức.

Ví dụ cấu trúc:

```java
publisher.subscribe(subscriber);
```

Lời gọi này nhận một `Subscriber` để đăng ký. Phương thức `subscribe` có kiểu trả về `void`; subscription được chuyển cho subscriber thông qua callback `onSubscribe(Subscription)`, không được trả trực tiếp từ `subscribe`.

## 2. Đăng ký tạo quan hệ nhận dữ liệu như thế nào?

Giao thức thông thường bắt đầu theo trình tự:

1. Ứng dụng gọi `publisher.subscribe(subscriber)`.
2. Publisher tạo hoặc thiết lập một subscription dành cho subscriber đó.
3. Publisher gọi `subscriber.onSubscribe(subscription)`.
4. Subscriber lưu subscription và gọi `request(n)` để thể hiện nhu cầu.
5. Publisher phát tối đa số phần tử đang được yêu cầu qua `onNext(item)`.
6. Khi nguồn hoàn tất hoặc gặp lỗi kết thúc, publisher gửi `onComplete()` hoặc `onError(error)`.

`onSubscribe` phải đến trước các tín hiệu khác của subscription đó. Publisher không được gửi `onNext` trước khi subscriber nhận subscription. Subscriber có thể yêu cầu dữ liệu ngay trong `onSubscribe` hoặc yêu cầu sau đó khi ứng dụng sẵn sàng.

`subscribe` chỉ thiết lập quan hệ và bắt đầu giao thức. Nó không có nghĩa dữ liệu đã được xử lý xong, không tự động yêu cầu vô hạn phần tử và cũng không bảo đảm callback chạy trên thread gọi `subscribe`.

Một subscriber thường chỉ nhận những phần tử được publisher phát sau khi đăng ký theo hành vi của publisher. Không nên giả định publisher lưu lịch sử để phát lại cho subscriber đăng ký muộn; nếu cần replay, phải chọn implementation có khả năng đó hoặc tự quản lý lịch sử.

## 3. Subscription và backpressure không phải executor

`Flow.Subscription` điều khiển nhu cầu dữ liệu. Hai phương thức chính:

```java
public interface Subscription {
    void request(long n);
    void cancel();
}
```

- `request(n)` thông báo subscriber muốn nhận thêm tối đa n phần tử.
- `cancel()` báo rằng subscriber không còn muốn nhận tín hiệu tiếp theo.

`n` phải là số dương. Yêu cầu không hợp lệ (0 hoặc số âm) vi phạm hợp đồng Flow; publisher phải kết thúc subscription bằng tín hiệu lỗi theo quy tắc của Flow. Nếu muốn biểu thị nhu cầu không giới hạn, có thể dùng `Long.MAX_VALUE`.

Backpressure giải quyết câu hỏi **publisher được phép gửi bao nhiêu phần tử**. Executor giải quyết câu hỏi **tác vụ được chạy bằng cơ chế và thread nào**. Hai cơ chế độc lập:

| Câu hỏi | Thành phần chịu trách nhiệm |
|---|---|
| Subscriber đã đăng ký chưa? | `Publisher.subscribe` và trạng thái subscription |
| Subscriber đang yêu cầu bao nhiêu phần tử? | `Subscription.request(n)` |
| Subscriber hủy đăng ký nhận tiếp? | `Subscription.cancel()` |
| Callback được lập lịch trên thread nào? | Implementation của publisher và executor mà nó sử dụng |
| Có bao nhiêu callback có thể chạy đồng thời? | Executor cùng quy tắc tuần tự tín hiệu của publisher |

Ví dụ, subscriber yêu cầu `request(1)` thì publisher chỉ được phát một phần tử cho đến khi có thêm nhu cầu. Dùng pool 20 thread không biến yêu cầu đó thành 20 phần tử; ngược lại, `request(Long.MAX_VALUE)` cũng không bắt buộc publisher phải tạo 20 thread.

Không dùng executor để thay thế backpressure. Tăng số thread có thể tăng khả năng xử lý song song, nhưng không tự giới hạn lượng dữ liệu được gửi đến subscriber.

## 4. Flow API có bắt buộc phải dùng Executor không?

Không. Các interface `Flow.Publisher`, `Flow.Subscriber`, `Flow.Subscription` và `Flow.Processor` mô tả giao thức. Chúng không nhận `Executor` trong chữ ký phương thức và không quy định mọi publisher phải tạo thread hoặc dùng thread pool.

Một publisher tự cài đặt có thể phát callback đồng bộ trên thread gọi phương thức của nó, hoặc có thể dùng executor, event loop hay cơ chế lập lịch khác. Vì vậy, khi đọc một implementation, cần kiểm tra chính sách thực thi của implementation đó.

Điều này cũng có nghĩa:

- Gọi `subscribe` trên thread `main` không chứng minh `onSubscribe` hoặc `onNext` sẽ chạy trên `main`.
- Việc callback chạy trên thread khác không tự chứng minh subscriber đã được đăng ký đúng hoặc có demand.
- Không nên dựa vào thread name hay thứ tự thời gian của các lời gọi nếu API implementation không cam kết điều đó.
- Một publisher đồng bộ có thể chạy callback ngay trong luồng gọi; một publisher bất đồng bộ có thể lên lịch callback sau khi phương thức đăng ký đã trả về.

Quy tắc của Flow yêu cầu các tín hiệu của một subscription được tuần tự hóa: `onSubscribe`, `onNext`, `onError` và `onComplete` không được chồng lấn trái hợp đồng. Tuy nhiên, những subscriber khác nhau có thể được xử lý song song nếu implementation và executor cho phép.

## 5. SubmissionPublisher kết nối Flow với Executor

`java.util.concurrent.SubmissionPublisher<T>` là implementation publisher có sẵn từ Java 9. Nó phân phối các phần tử đến subscriber theo cơ chế bất đồng bộ và sử dụng một `Executor` để thực thi các tác vụ phân phối.

Có thể truyền executor khi tạo publisher:

```java
ExecutorService executor = Executors.newSingleThreadExecutor();

SubmissionPublisher<String> publisher =
        new SubmissionPublisher<>(executor, 16);
```

Trong ví dụ này:

- `publisher.subscribe(subscriber)` đăng ký subscriber.
- `SubmissionPublisher` tạo subscription và lên lịch các callback thông qua executor.
- `onSubscribe`, `onNext` và terminal signal được thực thi bởi bộ máy đã cấu hình.
- `request(n)` vẫn quyết định số phần tử subscriber sẵn sàng nhận.
- Executor một thread giúp callback được chạy lần lượt trên thread do executor quản lý; nó không thay đổi số lượng demand.

Constructor nhận `Executor`, không yêu cầu kiểu cụ thể là `ExecutorService`. Một `ExecutorService` phù hợp khi ứng dụng cần quản lý vòng đời pool (shutdown, await termination). Có thể dùng executor khác nếu chính sách thực thi của nó phù hợp.

Constructor mặc định của `SubmissionPublisher` dùng executor mặc định của implementation, thường là `ForkJoinPool.commonPool()` trong cấu hình thông thường. Nếu cần kiểm soát thread, mức song song, đặt tên thread hoặc cô lập workload, truyền executor tường minh sẽ rõ ràng hơn.

## 6. Ví dụ đầy đủ: đăng ký trên main, callback chạy trên executor

Chương trình dưới đây dùng `SubmissionPublisher` với executor một thread có tên `flow-delivery`. Subscriber chỉ yêu cầu một phần tử ban đầu; sau mỗi `onNext`, nó yêu cầu thêm một phần tử. Ví dụ cho thấy đăng ký, demand và thread callback là ba việc có liên quan nhưng khác nhau.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class Main {
    public static void main(String[] args) throws Exception {
        ExecutorService deliveryExecutor =
                Executors.newSingleThreadExecutor(task ->
                        new Thread(task, "flow-delivery"));

        CountDownLatch subscribed = new CountDownLatch(1);
        CountDownLatch completed = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        try {
            try (SubmissionPublisher<String> publisher =
                         new SubmissionPublisher<>(deliveryExecutor, 8)) {

                publisher.subscribe(new Flow.Subscriber<>() {
                    private Flow.Subscription subscription;

                    @Override
                    public void onSubscribe(Flow.Subscription subscription) {
                        this.subscription = subscription;
                        System.out.println("onSubscribe thread: "
                                + Thread.currentThread().getName());

                        subscription.request(1);
                        subscribed.countDown();
                    }

                    @Override
                    public void onNext(String item) {
                        System.out.println("onNext " + item + " thread: "
                                + Thread.currentThread().getName());

                        subscription.request(1);
                    }

                    @Override
                    public void onError(Throwable throwable) {
                        failure.set(throwable);
                        System.out.println("onError: "
                                + throwable.getClass().getSimpleName());
                        completed.countDown();
                    }

                    @Override
                    public void onComplete() {
                        System.out.println("onComplete thread: "
                                + Thread.currentThread().getName());
                        completed.countDown();
                    }
                });

                if (!subscribed.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Subscriber was not registered in time");
                }

                System.out.println("submit thread: "
                        + Thread.currentThread().getName());

                publisher.submit("A");
                publisher.submit("B");
                publisher.close();

                if (!completed.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Subscriber did not complete in time");
                }

                if (failure.get() != null) {
                    throw new IllegalStateException(
                            "Publisher failed", failure.get());
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

Lưu mã vào `Main.java`, biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 Main.java
java Main
```

Kết quả stdout:

```text
onSubscribe thread: flow-delivery
submit thread: main
onNext A thread: flow-delivery
onNext B thread: flow-delivery
onComplete thread: flow-delivery
```

Phân tích:

1. Ứng dụng gọi `subscribe` từ thread `main`. `SubmissionPublisher` phân phối callback qua executor nên `onSubscribe` chạy trên `flow-delivery`.
2. Subscriber gọi `request(1)` trong `onSubscribe`. Đây là yêu cầu một phần tử đầu tiên, không phải yêu cầu executor tạo một thread.
3. Main chỉ gửi dữ liệu sau khi latch `subscribed` xác nhận callback `onSubscribe` đã chạy. Hai phần tử A và B được gửi từ thread main.
4. Sau khi xử lý A, subscriber yêu cầu thêm một phần tử. Tương tự, sau B nó yêu cầu tiếp; vì vậy cả hai phần tử được giao.
5. `close()` báo publisher không nhận thêm phần tử và sẽ hoàn tất sau các phần tử đã gửi. `onComplete` được gọi trên executor.
6. Latch hoàn tất giúp main chờ terminal signal trước khi shutdown executor. Không shutdown executor quá sớm khi publisher còn cần nó để chạy callback.

Latch trong ví dụ dùng để làm rõ thứ tự kiểm thử. Trong ứng dụng thực tế, nên chọn cơ chế phối hợp phù hợp với vòng đời và yêu cầu của hệ thống; không nên chặn thread giao diện hoặc thread xử lý sự kiện chỉ để chờ callback.

## 7. Executor ảnh hưởng đến việc phân phối ra sao?

Executor là chính sách thực thi tác vụ. Tùy loại executor, callback có thể chạy theo cách khác nhau:

| Executor | Đặc điểm | Tình huống phù hợp |
|---|---|---|
| `Executors.newSingleThreadExecutor()` | Một thread xử lý tác vụ lần lượt | Cần thứ tự thực thi dễ quan sát, workload nhẹ |
| `Executors.newFixedThreadPool(n)` | Tối đa n worker thread | Nhiều subscriber hoặc callback độc lập cần xử lý song song |
| `ForkJoinPool.commonPool()` | Pool dùng chung cho nhiều tác vụ trong JVM | Workload ngắn, có thể chia nhỏ và không cần cô lập pool |
| Executor trực tiếp (`Runnable::run`) | Chạy task ngay trên thread gọi `execute` | Kiểm thử đơn giản hoặc tác vụ rất nhỏ; cần hiểu nguy cơ callback chạy lồng trong caller |

`Executor` chỉ định phương thức `execute(Runnable)`; interface này không bắt buộc implementation phải tạo thread mới. Một executor trực tiếp có thể chạy task ngay trên thread gọi. Vì thế, chỉ nhìn kiểu `Executor` không thể kết luận callback luôn bất đồng bộ hoặc luôn chạy trên thread riêng.

Với `SubmissionPublisher`, executor được dùng để phân phối các tín hiệu. Một pool nhiều thread có thể giúp xử lý nhiều subscriber đồng thời, nhưng tín hiệu của cùng một subscriber vẫn phải tuân thủ thứ tự và không chồng lấn. Pool một thread có thể khiến subscriber chậm làm chậm các tác vụ phân phối khác dùng chung pool.

### Đừng chặn thread phân phối

Callback `onNext` nên xử lý nhanh và trả về. Nếu callback chặn lâu vì truy cập mạng, chờ khóa hoặc thao tác file lớn, thread executor có thể không phục vụ kịp subscriber khác. Với single-thread executor, một callback bị chặn có thể làm toàn bộ subscriber dùng executor đó chờ.

Nếu cần chuyển xử lý nặng sang executor khác, hãy xác định rõ cách lưu trữ phần tử, thứ tự hoàn tất, giới hạn queue và backpressure. Chỉ gọi `request(Long.MAX_VALUE)` rồi đẩy mọi phần tử vào một queue không giới hạn có thể làm bộ nhớ tăng liên tục nếu consumer xử lý chậm.

## 8. Nhiều subscriber và nhiều processor

Một publisher có thể có nhiều subscriber. Mỗi subscriber có subscription và demand riêng. Một subscriber yêu cầu một phần tử không có nghĩa mọi subscriber khác cũng yêu cầu một phần tử.

Với `SubmissionPublisher`, mỗi subscriber có bộ đệm và việc phân phối riêng. Executor có thể chạy tác vụ của các subscriber khác nhau trên các worker khác nhau. Dù vậy, các tín hiệu cho từng subscriber phải được tuần tự hóa theo giao thức.

`Flow.Processor<T,R>` có thể đứng giữa hai giai đoạn:

```text
Publisher nguồn
      |
      v
Processor (Subscriber + Publisher)
      |
      v
Subscriber cuối
```

Processor nhận subscription từ upstream, yêu cầu dữ liệu, xử lý phần tử rồi phát sang downstream theo subscription riêng. Do đó có hai luồng demand:

- Downstream yêu cầu processor phát bao nhiêu phần tử.
- Processor yêu cầu upstream cung cấp bao nhiêu phần tử.

Một processor đúng cần cân bằng hai phía để không nhận dữ liệu nhanh hơn khả năng xử lý hoặc phát dữ liệu vượt quá demand downstream. Executor của implementation processor (nếu có) quyết định callback chạy ở đâu; nó không thay thế việc điều phối demand giữa upstream và downstream.

## 9. Thời điểm đăng ký, phát dữ liệu và hoàn tất

Thời điểm gọi `subscribe` có ý nghĩa đối với publisher. Nếu dữ liệu được gửi trước khi subscriber đăng ký, `SubmissionPublisher` không phải kho lưu lịch sử để subscriber mới tự động nhận lại dữ liệu cũ. Hãy đăng ký trước khi phát nếu subscriber cần nhận toàn bộ các phần tử mới được gửi.

Trong ứng dụng nhiều thread, việc `subscribe` và `submit` đồng thời cần được điều phối theo yêu cầu nghiệp vụ. Nếu subscriber phải nhận một thông điệp cụ thể, hãy xác định rõ thứ tự đăng ký và gửi thay vì dựa vào race giữa hai thread.

`SubmissionPublisher.close()` đóng publisher một cách bình thường: publisher ngừng nhận thêm dữ liệu và hoàn tất việc phân phối các phần tử đã submit trước đó, sau đó gửi `onComplete` đến subscriber. `closeExceptionally(error)` kết thúc publisher bằng lỗi và dẫn đến `onError` cho subscriber.

`Subscription.cancel()` là thao tác riêng ở phía subscriber: nó hủy subscription đó. Nó không tương đương `publisher.close()`, vì publisher có thể vẫn đang phục vụ các subscriber khác.

## 10. Lỗi thường gặp

- **Cho rằng subscribe tạo thread:** Flow không quy định điều đó. Chỉ implementation và executor cụ thể mới quyết định cách callback được thực thi.
- **Cho rằng subscribe trả Subscription:** phương thức trả `void`; subscriber nhận subscription trong `onSubscribe`.
- **Nhầm request với lập lịch:** `request(n)` biểu thị demand, không chỉ định thread hay executor.
- **Nhầm executor với backpressure:** pool nhiều thread không giới hạn số phần tử publisher được phép phát.
- **Giả định callback luôn chạy trên thread khác:** executor trực tiếp có thể chạy task trên caller.
- **Không yêu cầu demand:** subscriber không yêu cầu dữ liệu có thể không nhận `onNext` dù đã đăng ký.
- **Yêu cầu số lượng không hợp lệ:** chỉ yêu cầu số dương; không dùng 0 hoặc số âm để tạm dừng.
- **Chặn callback quá lâu:** có thể làm nghẽn executor và khiến subscriber khác bị chậm.
- **Shutdown executor quá sớm:** callback đã lên lịch có thể không chạy nếu executor bị dừng trước khi publisher hoàn tất.
- **Chỉ kiểm tra một subscriber:** mỗi subscriber có demand, cancel và vòng đời riêng.
- **Cho rằng processor chỉ có một demand:** processor phải phối hợp demand upstream và downstream.
- **Quên đóng publisher:** subscriber có thể không nhận terminal signal nếu nguồn không được hoàn tất hoặc kết thúc lỗi theo đúng thiết kế.

## 11. Checklist thiết kế

- Đã chọn đúng publisher implementation và hiểu nó gọi callback đồng bộ hay bất đồng bộ chưa?
- Subscriber có xử lý `onSubscribe` và lưu subscription chưa?
- Demand được yêu cầu theo từng phần tử, theo batch hay không giới hạn?
- Executor có phù hợp với thời gian xử lý callback và số subscriber không?
- Có tránh block lâu trong callback không?
- Nếu dùng executor riêng, ai sở hữu và shutdown nó ở thời điểm nào?
- Có xử lý `onError`, `onComplete` và `cancel` không?
- Khi dùng processor, demand hai chiều có được điều phối không?
- Có kiểm soát bộ đệm và tốc độ producer/consumer không?
- Có kiểm thử trường hợp đăng ký muộn, consumer chậm, publisher đóng và executor dừng không?

Flow API tách giao thức đăng ký và điều khiển nhu cầu khỏi chính sách thực thi callback. `subscribe` thiết lập quan hệ, `Subscription.request(n)` điều khiển demand, còn executor chỉ tham gia khi publisher implementation dùng nó để lập lịch tác vụ. `SubmissionPublisher` là ví dụ cụ thể cho cách kết nối ba phần này; hiểu đúng vai trò của từng phần giúp thiết kế pipeline phản ứng có kiểm soát, tránh nghẽn thread và không nhầm lẫn giữa backpressure với concurrency.
