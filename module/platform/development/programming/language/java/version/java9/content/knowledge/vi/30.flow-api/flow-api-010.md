# Phân biệt hợp đồng Flow với thư viện xử lý phản ứng hoàn chỉnh

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của \`java.util.concurrent.Flow\` trong Java 9.
- Phân biệt giao thức Publisher/Subscriber với một framework reactive có nhiều toán tử và tiện ích vận hành.
- Hiểu trách nhiệm của \`Publisher\`, \`Subscriber\`, \`Subscription\` và \`Processor\`.
- Mô tả demand và backpressure, đồng thời phân biệt chúng với chiến lược buffering hoặc dropping.
- Xác định phần nào JDK cung cấp qua \`SubmissionPublisher\` và phần nào cần thư viện chuyên dụng.
- Chọn Flow hoặc một reactive library theo yêu cầu thực tế của ứng dụng.

## 1. Flow là hợp đồng giao tiếp, không phải một reactive framework đầy đủ

Java 9 đưa API \`java.util.concurrent.Flow\` vào JDK. API này định nghĩa các interface để một bên phát dữ liệu và một bên tiêu thụ dữ liệu có thể phối hợp theo mô hình publish-subscribe, có demand và backpressure.

Flow tập trung vào giao thức giữa các thành phần. Nó quy định cách đăng ký subscriber, gửi tín hiệu, yêu cầu số phần tử và hủy subscription. Nó không cung cấp sẵn một hệ thống toán tử phong phú để biến đổi, kết hợp, retry, chia sẻ hoặc điều phối mọi loại stream.

Cần phân biệt ba lớp:

1. **Giao thức Flow:** các interface và quy tắc tín hiệu để publisher và subscriber tương tác.
2. **Tiện ích có sẵn trong JDK:** ví dụ \`SubmissionPublisher\`, một publisher bất đồng bộ có buffer và hỗ trợ demand.
3. **Reactive library:** các thư viện như Project Reactor hoặc RxJava cung cấp thêm toán tử, scheduler, chiến lược lỗi, kiểm thử và tiện ích tích hợp.

Do đó, nói một ứng dụng dùng Flow không đồng nghĩa ứng dụng đã có đầy đủ mọi khả năng của một reactive framework. Flow cung cấp nền tảng giao tiếp để những thành phần khác có thể xây dựng trên đó.

## 2. Bốn thành phần của Flow

Các kiểu chính nằm trong \`java.util.concurrent.Flow\`:

| Thành phần | Vai trò |
|---|---|
| \`Flow.Publisher<T>\` | Cho phép subscriber đăng ký nhận phần tử kiểu T |
| \`Flow.Subscriber<T>\` | Nhận subscription, dữ liệu và tín hiệu kết thúc |
| \`Flow.Subscription\` | Biểu diễn mối quan hệ đăng ký; subscriber dùng nó để yêu cầu hoặc hủy |
| \`Flow.Processor<T, R>\` | Vừa là subscriber đầu vào kiểu T, vừa là publisher đầu ra kiểu R |

### 2.1. Publisher

Publisher công bố phương thức đăng ký:

~~~java
public interface Publisher<T> {
    void subscribe(Subscriber<? super T> subscriber);
}
~~~

Publisher chịu trách nhiệm tạo subscription và gửi tín hiệu theo giao thức. Một publisher có thể phục vụ nhiều subscriber; mỗi subscriber có subscription và demand riêng. Việc một subscriber yêu cầu thêm phần tử không tự động làm tăng demand của subscriber khác.

### 2.2. Subscriber

Subscriber nhận bốn callback:

~~~java
public interface Subscriber<T> {
    void onSubscribe(Subscription subscription);
    void onNext(T item);
    void onError(Throwable throwable);
    void onComplete();
}
~~~

Trình tự cơ bản là:

1. Publisher gọi \`onSubscribe\` để trao subscription.
2. Subscriber gọi \`request(n)\` trên subscription để yêu cầu dữ liệu.
3. Publisher gửi tối đa số phần tử đã được yêu cầu qua \`onNext\`.
4. Khi kết thúc bình thường, publisher gọi \`onComplete\`; khi có lỗi, gọi \`onError\`.

\`onError\` và \`onComplete\` là tín hiệu kết thúc. Sau một trong hai tín hiệu này, subscription không tiếp tục gửi \`onNext\` hoặc một tín hiệu kết thúc thứ hai.

### 2.3. Subscription

Subscription cung cấp hai thao tác:

~~~java
public interface Subscription {
    void request(long n);
    void cancel();
}
~~~

- \`request(n)\` báo rằng subscriber sẵn sàng nhận thêm tối đa n phần tử.
- \`cancel()\` yêu cầu publisher dừng việc phát dữ liệu cho subscription đó.

Giá trị \`n\` phải dương. Yêu cầu không hợp lệ phải được xử lý theo hợp đồng Flow bằng tín hiệu lỗi. Nhiều lần \`request\` cộng dồn demand; publisher không được gửi vượt quá tổng demand còn lại.

### 2.4. Processor

Processor kết hợp hai vai trò:

~~~java
public interface Processor<T, R>
        extends Subscriber<T>, Publisher<R> {
}
~~~

Một processor có thể nhận dữ liệu T, biến đổi hoặc lọc, rồi phát dữ liệu R. Nó phải phối hợp demand ở phía đầu vào và đầu ra. Chỉ triển khai hai interface không tự tạo ra cơ chế điều tiết đúng; người viết processor vẫn phải quản lý hàng đợi, tín hiệu, lỗi, hủy và concurrency.

## 3. Demand và backpressure là phần cốt lõi của hợp đồng

Trong mô hình push đơn giản, publisher có thể phát dữ liệu nhanh hơn subscriber xử lý. Điều đó dễ dẫn đến hàng đợi tăng không giới hạn, tăng độ trễ hoặc hết bộ nhớ.

Flow đưa demand vào giao thức. Subscriber yêu cầu số phần tử mà nó sẵn sàng nhận:

~~~java
subscription.request(1);
~~~

Sau khi xử lý một phần tử, subscriber có thể yêu cầu thêm:

~~~java
@Override
public void onNext(Integer item) {
    process(item);
    subscription.request(1);
}
~~~

Publisher chỉ được gửi số phần tử không vượt quá demand đã được yêu cầu. Đây là nền tảng của backpressure: tốc độ phát được ràng buộc bởi nhu cầu mà subscriber thể hiện.

Backpressure không tự quyết định ứng dụng phải làm gì khi nguồn dữ liệu không thể chậm lại. Ví dụ, một cảm biến hoặc callback từ hệ thống bên ngoài có thể tiếp tục tạo sự kiện. Ứng dụng vẫn cần chọn chính sách phù hợp:

- Giữ dữ liệu trong buffer có giới hạn.
- Làm chậm hoặc tạm dừng nguồn nếu nguồn hỗ trợ.
- Loại bỏ phần tử theo chính sách được định nghĩa rõ.
- Gộp nhiều sự kiện thành một giá trị tổng hợp.
- Từ chối dữ liệu hoặc báo lỗi khi vượt giới hạn.

Không nên coi backpressure là một buffer vô hạn. Demand kiểm soát số phần tử được phát theo giao thức; chiến lược lưu trữ và xử lý khi nguồn nhanh hơn subscriber vẫn là quyết định của publisher hoặc ứng dụng.

## 4. Quy tắc tín hiệu cần được tôn trọng

Khi tự triển khai Flow, hãy giữ các nguyên tắc sau:

- Publisher phải gọi \`onSubscribe\` trước các callback dữ liệu hoặc kết thúc của subscriber.
- Subscriber chỉ nhận \`onNext\` trong phạm vi demand còn lại.
- Các tín hiệu của cùng một subscription phải được tuần tự hóa; không gọi đồng thời nhiều \`onNext\` cho cùng subscriber.
- Sau \`onError\` hoặc \`onComplete\`, không phát thêm tín hiệu.
- Subscriber có thể gọi \`cancel()\` khi không còn quan tâm đến dữ liệu.
- Publisher phải xử lý subscriber hoặc subscription đã hủy.
- Exception trong quá trình xử lý cần được chuyển thành tín hiệu lỗi phù hợp; không tiếp tục phát dữ liệu sau tín hiệu kết thúc.

Các quy tắc này giúp nhiều implementation độc lập có thể giao tiếp mà không cần biết chi tiết nội bộ của nhau. Nếu tự viết publisher hoặc processor, cần kiểm thử các tình huống request nhiều lần, cancel, lỗi, hoàn tất và cạnh tranh giữa các thao tác.

## 5. JDK cung cấp gì qua SubmissionPublisher?

JDK có \`SubmissionPublisher<T>\`, một implementation của \`Flow.Publisher<T>\`. Nó hỗ trợ gửi dữ liệu bất đồng bộ đến subscriber bằng executor và buffer riêng cho từng subscriber.

Ví dụ tạo publisher:

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();
SubmissionPublisher<Integer> publisher =
        new SubmissionPublisher<>(executor, 8);
~~~

Một số thao tác đáng chú ý:

- \`subscribe(subscriber)\`: đăng ký subscriber.
- \`submit(item)\`: gửi item đến các subscriber; thao tác có thể block khi buffer của subscriber bị đầy cho đến khi có chỗ.
- \`offer(item, ...)\`: thử gửi theo hướng không chờ như \`submit\`; overload có thể dùng timeout và handler để quyết định xử lý khi không thể nhận ngay.
- \`close()\`: đóng publisher sau khi các item đã được submit, rồi phát tín hiệu hoàn tất theo thứ tự.
- \`closeExceptionally(error)\`: đóng publisher bằng lỗi.

\`SubmissionPublisher\` hữu ích cho các trường hợp cần một publisher bất đồng bộ cơ bản trong JDK. Nó không phải một bộ toán tử reactive tổng quát. Bạn vẫn phải tự viết subscriber, processor hoặc logic biến đổi nếu cần.

### 5.1. submit và offer không có cùng chính sách

\`submit\` phù hợp khi ứng dụng chấp nhận chờ để publisher có thể đưa item vào buffer. Nếu subscriber chậm, việc submit có thể làm thread gửi bị block.

\`offer\` phù hợp khi caller cần thử gửi mà không chờ như \`submit\`. Nếu không thể xếp item, handler được cấu hình có thể quyết định thử lại hoặc từ chối item; dữ liệu có thể bị bỏ tùy chính sách mà ứng dụng chọn.

Chọn chính sách theo yêu cầu dữ liệu:

- Với dữ liệu nghiệp vụ không được mất, cần cơ chế lưu bền vững hoặc chiến lược retry/điều tiết phù hợp; không âm thầm drop.
- Với số liệu telemetry có thể chấp nhận mất một phần, dropping có kiểm soát đôi khi hợp lý.
- Với dữ liệu trạng thái liên tục, có thể chỉ giữ giá trị mới nhất nếu nghiệp vụ cho phép.

## 6. Ví dụ chạy được: Flow và SubmissionPublisher

Ví dụ sau dùng một executor riêng để thứ tự callback dễ quan sát. Subscriber yêu cầu một phần tử mỗi lần, xử lý xong mới yêu cầu phần tử tiếp theo.

Tạo file **FlowContractDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class FlowContractDemo {

    private static final class PrintingSubscriber
            implements Flow.Subscriber<Integer> {

        private final CompletableFuture<Void> completed =
                new CompletableFuture<>();

        private Flow.Subscription subscription;

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            System.out.println("subscribed");
            subscription.request(1);
        }

        @Override
        public void onNext(Integer item) {
            System.out.println("received: " + item);
            subscription.request(1);
        }

        @Override
        public void onError(Throwable error) {
            completed.completeExceptionally(error);
        }

        @Override
        public void onComplete() {
            System.out.println("completed");
            completed.complete(null);
        }

        void awaitCompletion() throws Exception {
            completed.get(5, TimeUnit.SECONDS);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "flow-demo"));

        PrintingSubscriber subscriber = new PrintingSubscriber();

        try {
            try (SubmissionPublisher<Integer> publisher =
                         new SubmissionPublisher<>(executor, 8)) {

                publisher.subscribe(subscriber);

                publisher.submit(10);
                publisher.submit(20);
                publisher.submit(30);
            }

            // Publisher đã được close khi thoát try-with-resources.
            subscriber.awaitCompletion();
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17:

~~~bash
javac --release 17 -Xlint:all -d out FlowContractDemo.java
java -cp out FlowContractDemo
~~~

Output chính xác:

~~~text
subscribed
received: 10
received: 20
received: 30
completed
~~~

Subscriber chỉ yêu cầu một item trong \`onSubscribe\`. Sau mỗi \`onNext\`, nó mới yêu cầu item tiếp theo. Publisher được đóng sau khi gửi ba item; tín hiệu \`onComplete\` xuất hiện sau các item đã submit.

Ví dụ này minh họa giao thức và một tiện ích publisher có sẵn trong JDK. Nó chưa cung cấp các toán tử biến đổi như map/filter/flatMap, retry, ghép nhiều nguồn hoặc quản lý luồng dữ liệu phức tạp.

## 7. Reactive library cung cấp thêm lớp công cụ nào?

Một reactive library thường xây dựng trên một giao thức publisher/subscriber tương thích và cung cấp API cấp cao hơn. Ví dụ trong hệ sinh thái Java hiện nay có Project Reactor và RxJava.

Tùy thư viện, các khả năng thường gặp gồm:

| Khả năng | Flow trong JDK | Reactive library |
|---|---|---|
| Hợp đồng subscribe và tín hiệu | Có | Có hoặc tích hợp qua publisher tương thích |
| Demand/backpressure | Có trong giao thức | Thường có thêm chiến lược và operator hỗ trợ |
| Buffer publisher cơ bản | Có \`SubmissionPublisher\` | Có nhiều cấu hình và toán tử buffer |
| map/filter | Tự triển khai hoặc dùng thành phần khác | Có operator dựng sẵn |
| flatMap/merge/combine | Tự phối hợp các publisher | Có operator chuyên dụng |
| Retry và error recovery | Tự xây dựng | Thường có operator hỗ trợ |
| Scheduler và điều phối pipeline | Chọn Executor, tự nối logic | Có abstraction và operator riêng |
| Test publisher/pipeline | Tự tạo test subscriber | Thường có test utilities chuyên biệt |
| Context, replay, hot/cold source | Tự thiết kế | Tùy thư viện có abstraction và hỗ trợ |

Một thư viện đầy đủ giúp mô tả pipeline theo các bước khai báo: biến đổi, lọc, kết hợp, điều phối và xử lý lỗi. Nó cũng thường cung cấp công cụ kiểm thử và adapter cho hệ sinh thái khác.

Tuy nhiên, thư viện không loại bỏ nhu cầu hiểu backpressure. Operator có thể tạo buffer, chuyển đổi demand hoặc thay đổi concurrency; lựa chọn không phù hợp vẫn gây hàng đợi lớn, độ trễ cao hoặc mất dữ liệu.

## 8. Flow và Reactive Streams có liên quan thế nào?

Flow được thiết kế với các interface tương ứng với những thành phần trong Reactive Streams. Hai bộ kiểu có cùng mục tiêu giao thức và có thể được kết nối bằng adapter phù hợp.

Nhưng kiểu Java của chúng thuộc package khác nhau:

- JDK: \`java.util.concurrent.Flow.Publisher\`, \`Flow.Subscriber\`, \`Flow.Subscription\`.
- Reactive Streams: các interface trong package \`org.reactivestreams\`.

Một object triển khai \`Flow.Publisher\` không tự động là \`org.reactivestreams.Publisher\`; compiler xem chúng là hai kiểu khác nhau. Khi nối JDK Flow với thư viện dùng Reactive Streams, cần adapter hoặc bridge tương thích.

Không nên tự ép kiểu hoặc giả định hai interface tương đương ở mức type system. Dùng adapter chính thức do thư viện hoặc integration module cung cấp, và kiểm tra phiên bản tương thích.

## 9. Khi nào chọn Flow, khi nào chọn thư viện?

Chọn Flow và tiện ích JDK khi:

- Cần một giao thức chuẩn, gọn để các thành phần nội bộ trao đổi dữ liệu.
- Muốn tránh thêm dependency cho một publisher/subscriber đơn giản.
- Cần tự kiểm soát executor, buffer và quy tắc phát dữ liệu.
- Đang xây dựng adapter hoặc tích hợp giữa các thành phần có giao thức Flow.

Cân nhắc reactive library khi:

- Pipeline có nhiều bước map/filter/flatMap hoặc kết hợp nhiều nguồn.
- Cần retry, timeout, fallback, debounce, windowing hoặc điều khiển concurrency.
- Cần scheduler, context propagation, công cụ test và tích hợp hệ sinh thái.
- Đội ngũ muốn dùng abstraction reactive cấp cao thay vì tự viết operator và điều phối.

Đánh giá thêm chi phí dependency, khả năng tương thích Java, mức độ quen thuộc của đội ngũ, chính sách backpressure và công cụ vận hành. Không chọn thư viện chỉ vì tên gọi “reactive”; hãy xác định rõ những operator và hành vi mà ứng dụng thực sự cần.

## 10. Lỗi thường gặp

### Coi Flow là một framework reactive hoàn chỉnh

Flow định nghĩa giao thức cốt lõi. Các toán tử và tiện ích pipeline phong phú thường cần được tự triển khai hoặc lấy từ thư viện khác.

### Nghĩ SubmissionPublisher có sẵn mọi operator

\`SubmissionPublisher\` là một publisher bất đồng bộ có buffer. Nó không thay thế một thư viện có map/filter/flatMap, retry và công cụ test.

### Bỏ qua demand

Publisher không được phát vượt demand còn lại. Subscriber cần request thêm khi sẵn sàng nhận dữ liệu.

### Cho rằng backpressure tự giải quyết nguồn không thể chậm lại

Nguồn bên ngoài có thể tiếp tục tạo sự kiện. Ứng dụng vẫn cần buffer giới hạn, drop có kiểm soát, gộp dữ liệu hoặc cơ chế lưu bền vững.

### Dùng submit mà không tính đến blocking

\`SubmissionPublisher.submit\` có thể chờ khi buffer đầy. Nếu gọi từ thread nhạy cảm về độ trễ, cần xem xét executor và chính sách gửi.

### Dùng offer nhưng không định nghĩa hành vi khi không nhận được item

\`offer\` có thể không đưa item vào buffer. Handler phải thể hiện rõ retry hay drop; không được giả định mọi item đều đã được phát.

### Coi Flow và org.reactivestreams là cùng một kiểu

Chúng có hợp đồng tương ứng nhưng khác package và không assignment-compatible. Cần adapter khi kết nối hai hệ sinh thái.

### Tự viết Processor mà không quản lý demand hai phía

Processor phải điều phối yêu cầu đầu vào, hàng đợi, đầu ra, cancel và tín hiệu lỗi. Nếu chỉ chuyển tiếp callback mà không giữ hợp đồng, có thể phát vượt demand hoặc mất tín hiệu kết thúc.

## 11. Checklist

- [ ] Đã phân biệt Flow protocol, SubmissionPublisher và reactive library.
- [ ] Đã hiểu vai trò của Publisher, Subscriber, Subscription và Processor.
- [ ] Đã hiểu demand là giới hạn số phần tử publisher được phép phát.
- [ ] Đã xác định chính sách khi nguồn nhanh hơn subscriber.
- [ ] Đã hiểu SubmissionPublisher có buffer và có thể block ở submit.
- [ ] Đã định nghĩa hành vi khi offer không thể nhận item.
- [ ] Đã biết Flow không tự cung cấp bộ operator reactive đầy đủ.
- [ ] Đã chọn thư viện theo operator, scheduler, retry và công cụ thực sự cần.
- [ ] Đã dùng adapter khi nối Flow với org.reactivestreams.
- [ ] Đã biên dịch và chạy ví dụ bằng Java 9+.

