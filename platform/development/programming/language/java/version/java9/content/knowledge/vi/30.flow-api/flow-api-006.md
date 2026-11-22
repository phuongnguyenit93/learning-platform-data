# Quy tắc request dương và cộng dồn nhu cầu trong Java Flow

Java Flow API mô hình hóa luồng dữ liệu bất đồng bộ theo kiểu Reactive Streams. Một Subscriber không nhận dữ liệu tùy ý theo tốc độ Publisher; nó điều khiển lượng phần tử mà mình sẵn sàng nhận thông qua `Flow.Subscription.request(long n)`. Quy tắc cốt lõi là **mỗi request phải có số lượng dương và các lần request được cộng dồn vào nhu cầu còn chưa được đáp ứng**.

Hiểu đúng demand giúp tránh hai lỗi phổ biến: yêu cầu quá ít khiến pipeline ngừng tiến triển, hoặc yêu cầu quá nhiều khiến publisher phải tạo/buffer dữ liệu vượt khả năng xử lý của subscriber. Bài viết tập trung vào hợp đồng hiện hành của `java.util.concurrent.Flow` trong Java 9+, cách quản lý demand và cách kiểm thử bằng `SubmissionPublisher`.

## 1. Ba thành phần liên quan đến demand

Flow API nằm trong package `java.util.concurrent` và có bốn interface chính:

- `Flow.Publisher<T>`: phát các phần tử tới subscriber đã đăng ký.
- `Flow.Subscriber<T>`: nhận subscription, phần tử, lỗi hoặc tín hiệu hoàn tất.
- `Flow.Subscription`: kết nối một subscriber với publisher; cung cấp `request(n)` và `cancel()`.
- `Flow.Processor<T,R>`: vừa là subscriber của một publisher upstream, vừa là publisher cho downstream.

Mỗi lần một subscriber đăng ký, publisher gọi `onSubscribe(subscription)` để cấp một subscription riêng. Subscriber dùng chính subscription đó để điều khiển demand của mình. Nếu có ba subscriber, mỗi subscriber có demand độc lập; request của subscriber A không cộng vào demand của subscriber B.

Một subscription có hai thao tác điều khiển:

~~~java
subscription.request(n);
subscription.cancel();
~~~

`request(n)` thông báo subscriber muốn nhận thêm tối đa n phần tử. `cancel()` yêu cầu chấm dứt subscription. Không có phương thức “thu hồi n phần tử đã request”; nếu đã phát tín hiệu request, subscriber không thể giảm demand đó bằng cách gửi số âm hoặc request 0.

## 2. Request phải là số dương

Theo hợp đồng Flow/Reactive Streams, `request(long n)` chỉ hợp lệ khi `n > 0`.

~~~java
subscription.request(1);   // hợp lệ
subscription.request(32);  // hợp lệ
subscription.request(0);   // không hợp lệ
subscription.request(-1);  // không hợp lệ
~~~

Nếu subscriber gọi request với n không dương, publisher phải báo lỗi bằng `onError(new IllegalArgumentException(...))` và kết thúc subscription theo quy tắc Reactive Streams. Không sử dụng request(0) như lệnh “tạm dừng”, và không dùng số âm để giảm lượng demand.

Muốn tạm thời ngừng yêu cầu thêm dữ liệu, subscriber chỉ cần không gọi request tiếp. Demand đã gửi trước đó vẫn còn hiệu lực và publisher vẫn có thể phát những phần tử nằm trong demand còn lại. Muốn chấm dứt nhận dữ liệu, gọi `cancel()`.

### Vì sao request(0) không phải pause?

Giả sử subscriber đã gọi `request(10)` nhưng mới nhận 4 phần tử. Còn 6 đơn vị demand chưa được đáp ứng. Gọi `request(0)` không xóa 6 đơn vị này; đó là request không hợp lệ và phải được báo lỗi. Nếu muốn chỉ nhận từng nhóm nhỏ, hãy chọn số lượng phù hợp ngay từ đầu và chỉ cấp thêm demand khi xử lý xong một nhóm.

## 3. Nhiều lần request được cộng dồn

Demand là số phần tử còn được phép phát tại thời điểm hiện tại. Mỗi lần request dương làm tăng demand chưa được đáp ứng; request mới không ghi đè request cũ.

Ví dụ subscriber gọi:

~~~java
subscription.request(2);
subscription.request(3);
~~~

Nếu publisher chưa phát phần tử nào giữa hai lời gọi, tổng demand là 5. Publisher có thể phát tối đa năm lần `onNext` theo demand này, trừ khi publisher kết thúc hoặc báo lỗi sớm hơn.

Có thể mô tả quy tắc bằng biến demand:

~~~text
outstandingDemand = outstandingDemand + n
outstandingDemand = outstandingDemand - 1  // sau mỗi onNext
~~~

Ví dụ diễn tiến:

| Sự kiện | Demand còn lại |
| --- | ---: |
| Ban đầu | 0 |
| request(2) | 2 |
| request(3) | 5 |
| Publisher phát onNext đầu tiên | 4 |
| Publisher phát onNext thứ hai | 3 |
| Publisher phát onNext thứ ba | 2 |
| Publisher phát onNext thứ tư | 1 |
| Publisher phát onNext thứ năm | 0 |

Nếu publisher phát 2 phần tử sau request(2), demand trở về 0. Khi subscriber gọi request(3), demand tăng lên 3 và có thể nhận thêm ba phần tử.

**Điểm quan trọng:** request(n) là số lượng *thêm vào* demand, không phải tổng số phần tử subscriber muốn nhận kể từ đầu subscription.

## 4. onNext tiêu thụ demand; tín hiệu kết thúc thì không

Mỗi lần publisher gọi `onNext(item)`, publisher tiêu thụ một đơn vị demand. Publisher không được phát nhiều phần tử hơn tổng demand hiện có.

Các tín hiệu `onComplete()` và `onError(error)` là tín hiệu kết thúc, không phải phần tử dữ liệu và không tiêu thụ demand. Vì vậy publisher có thể báo hoàn tất hoặc lỗi ngay cả khi subscriber chưa request phần tử nào.

Nếu publisher phát xong nguồn trước khi dùng hết demand, phần demand còn lại không tạo thêm phần tử. Ví dụ subscriber request(100), nhưng nguồn chỉ có 3 phần tử; publisher phát 3 lần onNext rồi onComplete.

Demand chỉ giới hạn số lần onNext được phát. Nó không bắt buộc publisher phải phát đủ n phần tử, cũng không bảo đảm phần tử sẽ được phát đồng bộ ngay trong lời gọi request.

## 5. Long.MAX_VALUE biểu thị demand không giới hạn

Flow dùng kiểu long cho tham số request. `Long.MAX_VALUE` có thể được dùng để biểu thị nhu cầu không giới hạn:

~~~java
subscription.request(Long.MAX_VALUE);
~~~

Khi demand đạt Long.MAX_VALUE, publisher có thể coi demand là unbounded và không cần giảm bộ đếm sau từng onNext. Subscriber vẫn có thể cancel để ngừng nhận dữ liệu.

Dùng unbounded demand chỉ phù hợp khi subscriber thực sự có khả năng xử lý tốc độ phát dữ liệu hoặc publisher có cơ chế giới hạn/buffer phù hợp. Nếu subscriber yêu cầu Long.MAX_VALUE nhưng publisher tiếp tục tạo dữ liệu nhanh hơn khả năng xử lý, backpressure ở ranh giới subscription gần như bị vô hiệu hóa.

Không dùng Long.MAX_VALUE chỉ vì “đỡ phải request nhiều lần”. Với nguồn lớn, vô hạn hoặc có tốc độ không ổn định, nên cấp demand theo batch và theo khả năng tiêu thụ thực tế.

## 6. Tránh overflow khi cộng dồn demand

Một publisher tự triển khai phải cộng dồn request an toàn. Phép cộng long thông thường có thể overflow:

~~~java
long demand = currentDemand + n;
~~~

Nếu tổng vượt Long.MAX_VALUE, phép cộng có thể quay vòng thành số âm. Demand âm sẽ phá vỡ quy tắc phát dữ liệu và có thể khiến publisher dừng hoặc phát sai.

Cách cộng an toàn là bão hòa ở Long.MAX_VALUE:

~~~java
static long addCap(long current, long n) {
    if (n >= Long.MAX_VALUE - current) {
        return Long.MAX_VALUE;
    }
    return current + n;
}
~~~

Hàm trên giả định current không âm và n dương. Nếu demand hiện tại là Long.MAX_VALUE, kết quả vẫn là Long.MAX_VALUE. Nếu tổng vừa đúng Long.MAX_VALUE, kết quả cũng là Long.MAX_VALUE.

Nếu nhiều thread có thể gọi request đồng thời, phép cập nhật phải atomic hoặc được bảo vệ bằng cơ chế đồng bộ phù hợp. Chỉ tính đúng trong một thread là chưa đủ cho publisher đa luồng.

Một mẫu cập nhật với AtomicLong:

~~~java
private final AtomicLong requested = new AtomicLong();

void addDemand(long n) {
    if (n <= 0) {
        throw new IllegalArgumentException("n must be positive");
    }

    requested.getAndUpdate(current ->
            current >= Long.MAX_VALUE - n
                    ? Long.MAX_VALUE
                    : current + n);
}
~~~

Đoạn này minh họa phép cộng demand nguyên tử. Một publisher hoàn chỉnh còn phải phối hợp cập nhật demand với hàng đợi dữ liệu, cancellation, terminal signal và việc tuần tự hóa các callback. Không nên dùng riêng đoạn code trên như một implementation Publisher hoàn chỉnh.

## 7. Request theo batch và replenishment

Subscriber có thể chọn một trong các chiến lược sau:

### Request từng phần tử

~~~java
@Override
public void onSubscribe(Flow.Subscription subscription) {
    this.subscription = subscription;
    subscription.request(1);
}

@Override
public void onNext(Item item) {
    process(item);
    subscription.request(1);
}
~~~

Cách này giới hạn số phần tử outstanding rất chặt. Tuy nhiên, mỗi phần tử lại tạo một lần request; với pipeline có overhead điều phối cao, việc request từng item có thể giảm throughput.

### Request một batch

~~~java
subscription.request(32);
~~~

Subscriber cho phép tối đa 32 phần tử outstanding. Sau khi xử lý xong nhóm, subscriber request thêm một batch. Cách này giảm số lần gọi request nhưng có thể tăng lượng dữ liệu đang chờ xử lý.

### Replenish theo ngưỡng

Một subscriber có thể request batch mới khi demand còn lại xuống dưới ngưỡng. Ví dụ, buffer có sức chứa 100 phần tử, subscriber ban đầu request 100; khi đã xử lý 75 phần tử, nó request thêm 75 để giữ một lượng dữ liệu đang chờ ổn định.

Khi chọn batch size, cân nhắc:

- Dung lượng bộ nhớ có thể dành cho phần tử đang chờ.
- Thời gian xử lý trung bình và độ biến động của mỗi phần tử.
- Độ trễ mà ứng dụng chấp nhận.
- Chi phí gọi request và chuyển tiếp tín hiệu.
- Publisher có buffer hay nguồn dữ liệu có thể tạm dừng hay không.

Không request một batch lớn hơn mức subscriber có thể lưu giữ hoặc xử lý an toàn.

## 8. Backpressure và giới hạn bộ đệm

Backpressure là cơ chế để consumer truyền ngược khả năng tiếp nhận dữ liệu về phía producer. Trong Flow, request là tín hiệu demand của subscriber.

Tuy nhiên, request không tự động bảo đảm toàn hệ thống không dùng nhiều bộ nhớ. Publisher có thể nhận dữ liệu từ một nguồn bên ngoài và phải buffer trước khi subscriber request. Nếu nguồn upstream không thể tạm dừng, publisher cần một chính sách khi buffer đầy: chặn producer, từ chối, bỏ phần tử theo chính sách, hoặc báo lỗi tùy hợp đồng API.

`SubmissionPublisher` là một implementation hiện hành của `Flow.Publisher` có buffer cho subscriber và hỗ trợ xử lý bất đồng bộ. Nó cho phép đặt executor và giới hạn buffer capacity:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(2);
SubmissionPublisher<String> publisher =
        new SubmissionPublisher<>(executor, 64);
~~~

Buffer capacity không phải demand. Capacity giới hạn lượng phần tử được buffer; request điều khiển lượng phần tử subscriber được phép nhận. Hai khái niệm liên quan nhưng không thay thế nhau.

Với `SubmissionPublisher.submit(item)`, producer có thể bị block khi subscriber chậm và buffer đầy. `offer(...)` cung cấp cách thử gửi với chính sách xử lý khi không thể buffer ngay, tùy overload và handler được chọn. Hãy đọc hợp đồng của API cụ thể thay vì giả định mọi Publisher đều có cùng chính sách buffer.

## 9. Cancellation và demand còn lại

`cancel()` yêu cầu publisher ngừng gửi dữ liệu cho subscription đó:

~~~java
subscription.cancel();
~~~

Cancellation là thao tác kết thúc, không phải giảm demand về một giá trị nhỏ hơn. Một khi đã cancel, subscriber không thể tiếp tục bằng cách gọi request thêm; nếu cần tiếp tục xử lý, phải thiết lập subscription mới theo hợp đồng publisher.

Cancellation phải idempotent: gọi nhiều lần không được tạo ra nhiều lần hủy có hại. Vì tín hiệu có thể đang được xử lý đồng thời, subscriber cần chấp nhận khả năng một callback đã bắt đầu trước khi cancellation được quan sát. Publisher phải tiến tới trạng thái ngừng phát tín hiệu cho subscription đã cancel.

Không dùng cancel để biểu diễn “tôi xử lý xong batch này nhưng vẫn muốn nhận tiếp”. Trường hợp đó, giữ subscription và chỉ request batch tiếp theo khi sẵn sàng.

## 10. Tuần tự hóa tín hiệu và request đồng thời

Một publisher có thể nhận request từ nhiều thread. Cập nhật demand cần an toàn với cạnh tranh, và publisher phải tuân thủ thứ tự tín hiệu cho từng subscriber.

Các callback `onSubscribe`, `onNext`, `onError` và `onComplete` phải được gọi theo hợp đồng tuần tự của Flow. Publisher không được gọi chồng lấn onNext đồng thời cho cùng subscriber. Điều này cho phép subscriber xử lý trạng thái nội bộ tuần tự trong callback, nhưng không có nghĩa toàn bộ ứng dụng hoặc các subscriber khác chạy trên một thread.

Subscriber có thể gọi request ngay trong `onSubscribe` hoặc trong `onNext`. Đây là cách phổ biến để cấp demand ban đầu và replenishment. Publisher cần xử lý được request reentrant mà không phát callback lồng nhau theo cách vi phạm tuần tự hóa tín hiệu.

Nếu tự triển khai publisher, cần thiết kế drain loop hoặc cơ chế điều phối tương đương để hợp nhất request đồng thời, phát dữ liệu theo demand, xử lý cancellation và chỉ gửi terminal signal một lần. Tránh gọi subscriber callback từ nhiều thread mà không có serialization.

## 11. Ví dụ hoàn chỉnh: hai request được cộng dồn thành năm

Ví dụ dưới đây dùng `SubmissionPublisher` và một subscriber tự request 2 phần tử, sau đó request thêm 3 phần tử trước khi publisher gửi dữ liệu. Subscriber nhận tổng cộng 5 phần tử. Chương trình dùng latch để bảo đảm cả hai request đã được gửi trước khi producer submit các item.

Tạo tệp `PositiveDemandDemo.java`:

~~~java
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.Flow;

public class PositiveDemandDemo {
    private static final class RecordingSubscriber
            implements Flow.Subscriber<Integer> {
        private final CountDownLatch subscribed = new CountDownLatch(1);
        private final CountDownLatch completed = new CountDownLatch(1);
        private final List<Integer> received = new CopyOnWriteArrayList<>();
        private final AtomicReference<Throwable> failure = new AtomicReference<>();

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            System.out.println("request(2)");
            subscription.request(2);

            System.out.println("request(3)");
            subscription.request(3);

            subscribed.countDown();
        }

        @Override
        public void onNext(Integer item) {
            received.add(item);
            System.out.println("onNext: " + item);
        }

        @Override
        public void onError(Throwable throwable) {
            failure.set(throwable);
            completed.countDown();
        }

        @Override
        public void onComplete() {
            System.out.println("onComplete");
            completed.countDown();
        }

        void awaitSubscription() throws InterruptedException {
            if (!subscribed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("onSubscribe timed out");
            }
        }

        void awaitCompletion() throws InterruptedException {
            if (!completed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("publisher completion timed out");
            }

            Throwable error = failure.get();
            if (error != null) {
                throw new IllegalStateException("subscriber failed", error);
            }

            if (!received.equals(List.of(1, 2, 3, 4, 5))) {
                throw new AssertionError("Unexpected items: " + received);
            }

            System.out.println("received=" + received.size());
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        SubmissionPublisher<Integer> publisher =
                new SubmissionPublisher<>(executor, 8);
        RecordingSubscriber subscriber = new RecordingSubscriber();

        try {
            publisher.subscribe(subscriber);
            subscriber.awaitSubscription();

            for (int item = 1; item <= 5; item++) {
                publisher.submit(item);
            }
            publisher.close();

            subscriber.awaitCompletion();
        } finally {
            publisher.close();
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -Xlint:all PositiveDemandDemo.java
java PositiveDemandDemo
~~~

Kết quả stdout chính xác:

~~~text
request(2)
request(3)
onNext: 1
onNext: 2
onNext: 3
onNext: 4
onNext: 5
onComplete
received=5
~~~

Hai lời gọi request được thực hiện trước khi producer submit phần tử. Demand ban đầu là 0, sau request(2) là 2, sau request(3) là 5. Publisher phát năm phần tử theo demand rồi báo hoàn tất. Nếu subscriber chỉ request(2), publisher chỉ được phép phát tối đa hai onNext cho đến khi có request tiếp theo.

Ví dụ dùng SubmissionPublisher để kiểm tra hợp đồng ở cấp API. Nó không phải implementation của một publisher tùy biến; việc cộng demand, drain queue, saturation và serialization được implementation thư viện đảm nhiệm.

## 12. Những lỗi thường gặp

- **Coi request mới là giá trị thay thế:** request được cộng vào demand chưa đáp ứng, không ghi đè.
- **Gọi request(0) để pause:** n phải dương; chỉ ngừng request thêm hoặc cancel nếu muốn kết thúc.
- **Gọi request(-1) để giảm demand:** số âm không hợp lệ và dẫn đến onError theo hợp đồng.
- **Quên demand bị tiêu thụ:** mỗi onNext giảm một đơn vị demand outstanding.
- **Cho rằng onComplete cần demand:** terminal signal không tiêu thụ demand.
- **Request Long.MAX_VALUE không cân nhắc:** điều này tương đương unbounded demand và có thể làm mất backpressure ở subscriber.
- **Cộng long trực tiếp:** overflow có thể làm demand âm; dùng saturating addition.
- **Dùng biến demand không atomic:** request từ nhiều thread có thể làm mất cập nhật.
- **Request từng item trong workload throughput cao:** có thể tăng overhead; cân nhắc batch hoặc replenishment theo ngưỡng.
- **Buffer capacity bị nhầm với demand:** buffer giới hạn dữ liệu chờ; request giới hạn số onNext được phát.
- **Dùng cancel để kết thúc một batch:** cancel kết thúc subscription; request thêm khi sẵn sàng nếu muốn tiếp tục.
- **Cho rằng request bảo đảm phát đồng bộ:** publisher có thể xử lý bất đồng bộ; không block chờ onNext bên trong request.
- **Publisher phát callback đồng thời:** phải serialize tín hiệu cho từng subscriber và xử lý request reentrant an toàn.

## 13. Checklist thiết kế và kiểm thử

1. Subscriber chỉ gọi request với n dương.
2. Demand được cộng dồn giữa các lần request.
3. Mỗi onNext tiêu thụ đúng một đơn vị demand.
4. onComplete/onError không bị tính là phần tử dữ liệu.
5. Long.MAX_VALUE được xử lý như unbounded demand.
6. Phép cộng demand không overflow; kết quả bão hòa tại Long.MAX_VALUE.
7. Request đồng thời không làm mất cập nhật.
8. Publisher không phát vượt demand và tuần tự hóa callback.
9. Cancellation idempotent và dừng phát dữ liệu theo hợp đồng.
10. Batch size phù hợp với bộ nhớ, latency và throughput của subscriber.
11. Buffer policy được xem xét riêng với demand.
12. Test xác nhận số phần tử thực nhận không vượt tổng demand đã cấp.

Quy tắc request dương và cộng dồn là nền tảng của backpressure trong Flow. Mỗi request hợp lệ bổ sung demand outstanding; mỗi onNext tiêu thụ một đơn vị; Long.MAX_VALUE biểu thị unbounded demand; request không dương là lỗi. Publisher tự triển khai cần cộng demand an toàn, xử lý cạnh tranh và tuần tự hóa tín hiệu. Subscriber nên chọn batch theo năng lực xử lý thực tế để giữ cân bằng giữa throughput, latency và bộ nhớ.