# Mô hình phát hành và đăng ký luồng dữ liệu với Java Flow

## Mục tiêu

Java 9 bổ sung **Flow API** trong package `java.util.concurrent` để mô hình hóa việc phát hành và đăng ký nhận dữ liệu bất đồng bộ. API này dựa trên mô hình Reactive Streams: một bên phát dữ liệu, một hoặc nhiều bên đăng ký nhận, và bên nhận điều khiển lượng dữ liệu mà mình sẵn sàng xử lý thông qua cơ chế **backpressure**.

Flow API định nghĩa bốn thành phần chính:

- **Publisher<T>** phát các phần tử kiểu T.
- **Subscriber<T>** đăng ký nhận và xử lý các phần tử.
- **Subscription** kết nối Publisher với Subscriber, đồng thời mang các thao tác yêu cầu dữ liệu và hủy đăng ký.
- **Processor<T,R>** vừa là Subscriber<T> vừa là Publisher<R>, dùng để xử lý dữ liệu trung gian.

Java cũng cung cấp **SubmissionPublisher<T>**, một triển khai Publisher có sẵn, hỗ trợ buffer cho từng subscriber và phân phối dữ liệu thông qua Executor.

## 1. Vì sao cần mô hình Publisher–Subscriber?

Trong một luồng xử lý dữ liệu, bên tạo dữ liệu và bên tiêu thụ dữ liệu thường có tốc độ khác nhau. Nếu bên phát gửi nhanh hơn khả năng xử lý của bên nhận, dữ liệu có thể tích tụ trong bộ nhớ hoặc làm quá tải hệ thống.

Mô hình Publisher–Subscriber tách hai vai trò:

- Publisher chịu trách nhiệm phát dữ liệu khi có dữ liệu mới.
- Subscriber chịu trách nhiệm đăng ký và xử lý dữ liệu.
- Subscription cho phép Subscriber báo lượng dữ liệu mà nó sẵn sàng nhận.

Subscriber không phải nhận mọi dữ liệu ngay lập tức. Nó có thể yêu cầu từng phần tử hoặc một nhóm phần tử khi đã sẵn sàng. Cơ chế điều tiết này được gọi là **backpressure**.

Flow API cũng tách việc phát dữ liệu khỏi cách xử lý cụ thể. Publisher không cần biết Subscriber sẽ lưu dữ liệu, ghi log, cập nhật giao diện hay chuyển tiếp sang một pipeline khác.

## 2. Bốn thành phần cốt lõi

Các kiểu được khai báo bên trong lớp **Flow**:

```java
Flow.Publisher<T>
Flow.Subscriber<T>
Flow.Subscription
Flow.Processor<T, R>
```

### Publisher<T>

Publisher là nguồn phát dữ liệu. Interface có phương thức:

```java
void subscribe(Flow.Subscriber<? super T> subscriber);
```

Khi Subscriber gọi `subscribe()`, Publisher bắt đầu thiết lập một quan hệ đăng ký. Publisher không tự ý gửi phần tử trước khi thông báo Subscription cho Subscriber.

Một Publisher có thể có nhiều Subscriber. Mỗi Subscriber có Subscription riêng, vì vậy lượng dữ liệu mà từng Subscriber yêu cầu có thể khác nhau.

### Subscriber<T>

Subscriber nhận các tín hiệu từ Publisher thông qua bốn callback:

```java
public interface Subscriber<T> {
    void onSubscribe(Flow.Subscription subscription);
    void onNext(T item);
    void onError(Throwable throwable);
    void onComplete();
}
```

Ý nghĩa:

- **onSubscribe(subscription)** được gọi khi đăng ký được thiết lập. Subscriber giữ Subscription và gọi `request()` để yêu cầu dữ liệu.
- **onNext(item)** nhận một phần tử. Publisher chỉ được phát số phần tử không vượt quá lượng Subscriber đã yêu cầu.
- **onError(error)** thông báo luồng kết thúc do lỗi.
- **onComplete()** thông báo luồng kết thúc bình thường.

`onError()` và `onComplete()` là tín hiệu kết thúc. Một khi một trong hai đã được gửi, Publisher không được gửi thêm `onNext()` hoặc một tín hiệu kết thúc khác cho Subscriber đó.

### Subscription

Subscription đại diện cho quan hệ giữa một Publisher và một Subscriber cụ thể. Nó có hai phương thức:

```java
public interface Subscription {
    void request(long n);
    void cancel();
}
```

**request(n)** báo rằng Subscriber sẵn sàng nhận thêm tối đa n phần tử. Giá trị n phải dương. Nếu n không dương, Publisher phải báo lỗi `IllegalArgumentException` qua `onError()` theo hợp đồng Flow.

**cancel()** báo rằng Subscriber không còn muốn nhận dữ liệu từ Subscription đó. Sau khi hủy, Publisher không nên tiếp tục gửi dữ liệu cho Subscriber. Tuy nhiên, một tín hiệu đã được lên lịch hoặc đang diễn ra có thể tạo ra tình huống cạnh tranh tại thời điểm hủy; không nên dựa vào việc cancel có thể thu hồi một callback đã bắt đầu.

Có thể gọi `request(Long.MAX_VALUE)` để biểu thị nhu cầu không giới hạn thực tế. Nếu muốn kiểm soát tải, Subscriber nên yêu cầu số lượng vừa với khả năng xử lý thay vì luôn yêu cầu không giới hạn.

### Processor<T,R>

Processor kết hợp hai vai trò:

```java
public interface Processor<T, R>
        extends Flow.Subscriber<T>, Flow.Publisher<R> {
}
```

Nó nhận dữ liệu kiểu T từ Publisher upstream, xử lý hoặc biến đổi dữ liệu, rồi phát dữ liệu kiểu R cho Subscriber downstream.

Ví dụ về một pipeline:

```text
Publisher<Integer>
       |
       v
Processor<Integer, String>
       |
       v
Subscriber<String>
```

Processor hữu ích khi cần lọc, chuyển đổi, gom nhóm hoặc áp dụng một bước nghiệp vụ ở giữa luồng. Khi triển khai Processor, cần phối hợp nhu cầu dữ liệu từ downstream với Subscription upstream. Nếu chỉ yêu cầu upstream liên tục mà không kiểm soát khả năng tiêu thụ phía dưới, Processor có thể tạo backlog và làm mất ý nghĩa của backpressure.

## 3. Vòng đời đăng ký và phát dữ liệu

Một luồng Flow thông thường diễn ra theo thứ tự:

1. Subscriber gọi `publisher.subscribe(subscriber)`.
2. Publisher gọi `subscriber.onSubscribe(subscription)` để trao Subscription.
3. Subscriber gọi `subscription.request(n)` để yêu cầu dữ liệu.
4. Publisher phát tối đa n phần tử bằng các lần gọi `onNext(item)`.
5. Subscriber có thể yêu cầu thêm dữ liệu trong hoặc sau khi xử lý mỗi phần tử.
6. Khi kết thúc bình thường, Publisher gọi `onComplete()`; khi lỗi, Publisher gọi `onError(error)`.
7. Subscriber có thể gọi `cancel()` trước khi luồng kết thúc để dừng nhận thêm dữ liệu.

Publisher phải gọi `onSubscribe()` trước các callback dữ liệu hoặc tín hiệu kết thúc. Các tín hiệu của một Subscription phải tuân theo thứ tự và quy tắc của Flow; Subscriber không nên giả định các callback được chạy trên thread gọi `subscribe()` hoặc `submit()`, vì điều đó phụ thuộc Publisher và Executor.

### Quy tắc tín hiệu cần nhớ

- Mỗi Subscriber nhận một Subscription thông qua `onSubscribe()`.
- Không gửi `onNext()` vượt quá số phần tử Subscriber đã yêu cầu.
- Không gửi `onNext()` trước `onSubscribe()`.
- `onError()` hoặc `onComplete()` kết thúc luồng; không phát tín hiệu tiếp theo sau terminal signal.
- Subscriber phải xử lý cả trường hợp lỗi và hoàn tất bình thường.
- Subscriber nên gọi `request()` với số dương; yêu cầu không dương là lỗi theo hợp đồng Flow.

## 4. Backpressure: Subscriber kiểm soát lượng dữ liệu

Backpressure là cơ chế cho phép bên nhận điều khiển tốc độ phát dữ liệu. Thay vì để Publisher đẩy dữ liệu không giới hạn, Subscriber chủ động gửi nhu cầu thông qua `request(n)`.

Ví dụ:

```java
@Override
public void onSubscribe(Flow.Subscription subscription) {
    this.subscription = subscription;
    subscription.request(1);
}

@Override
public void onNext(Integer item) {
    process(item);
    subscription.request(1);
}
```

Subscriber chỉ yêu cầu một phần tử ban đầu. Sau khi xử lý xong phần tử hiện tại, nó yêu cầu thêm một phần tử. Cách này tạo nhịp xử lý tuần tự theo khả năng của Subscriber.

Một số chiến lược yêu cầu thường gặp:

| Chiến lược | Cách hoạt động | Khi phù hợp |
|---|---|---|
| Yêu cầu từng phần tử | Gọi `request(1)` sau mỗi lần xử lý | Xử lý tuần tự, mỗi phần tử tốn nhiều tài nguyên |
| Yêu cầu theo lô | Gọi `request(batchSize)` | Xử lý theo batch hoặc ghi dữ liệu theo nhóm |
| Yêu cầu không giới hạn | Gọi `request(Long.MAX_VALUE)` | Luồng nhỏ hoặc Subscriber chắc chắn đủ khả năng xử lý |
| Hủy đăng ký | Gọi `cancel()` | Không còn nhu cầu nhận dữ liệu |

Không phải Publisher nào cũng có cùng chính sách buffer hoặc cách xử lý khi Subscriber chậm. Flow định nghĩa hợp đồng trao đổi tín hiệu và demand; chiến lược lưu đệm, thread và cách xử lý quá tải phụ thuộc implementation.

## 5. SubmissionPublisher: Publisher có sẵn trong JDK

**SubmissionPublisher<T>** là một triển khai Publisher có trong Java 9+. Nó hỗ trợ:

- Đăng ký nhiều Subscriber.
- Phân phối phần tử tới các Subscriber thông qua một **Executor**.
- Buffer riêng cho từng Subscriber.
- Điều tiết việc phân phối theo demand của Subscriber.
- Đóng Publisher bình thường hoặc kết thúc bằng lỗi.

Khởi tạo cơ bản:

```java
SubmissionPublisher<String> publisher =
        new SubmissionPublisher<>();
```

Constructor mặc định sử dụng common ForkJoinPool và dung lượng buffer mặc định. Có thể truyền Executor và dung lượng buffer tối đa:

```java
SubmissionPublisher<String> publisher =
        new SubmissionPublisher<>(executor, 256);
```

Một số phương thức thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| `subscribe(subscriber)` | Đăng ký Subscriber |
| `submit(item)` | Phát phần tử tới các Subscriber hiện tại; có thể chờ khi Subscriber bị chậm và buffer đầy |
| `offer(item, ...)` | Thử phát phần tử với chính sách xử lý khi buffer không đủ |
| `close()` | Đóng Publisher và hoàn tất luồng bình thường |
| `closeExceptionally(error)` | Kết thúc luồng bằng lỗi |
| `getNumberOfSubscribers()` | Lấy số Subscriber hiện tại |
| `estimateMaximumLag()` | Ước lượng độ trễ lớn nhất giữa dữ liệu đã phát và đã được Subscriber xử lý |
| `estimateMinimumDemand()` | Ước lượng nhu cầu còn lại nhỏ nhất trong các Subscriber |

`submit()` phù hợp khi ứng dụng muốn gửi dữ liệu và chấp nhận chờ tài nguyên buffer. Với luồng tải cao, cần cân nhắc ảnh hưởng của việc chờ lên thread phát dữ liệu.

`offer()` có các overload cho phép xử lý tình trạng Subscriber chậm, ví dụ timeout và hàm quyết định khi một phần tử không thể được nhận. Hãy đọc giá trị trả về và chọn chính sách drop/retry phù hợp với nghiệp vụ; không được âm thầm coi mọi lần offer đều đã giao thành công.

`close()` báo Publisher không phát thêm phần tử mới và hoàn tất sau khi xử lý các phần tử đã được gửi theo cơ chế của Publisher. Dùng `closeExceptionally(error)` nếu luồng cần kết thúc bằng lỗi.

## 6. Viết Subscriber có backpressure

Subscriber thường lưu Subscription nhận được trong `onSubscribe()` rồi yêu cầu dữ liệu theo nhu cầu.

Ví dụ khung:

```java
import java.util.concurrent.Flow;

public class OneAtATimeSubscriber
        implements Flow.Subscriber<Integer> {

    private Flow.Subscription subscription;

    @Override
    public void onSubscribe(Flow.Subscription subscription) {
        this.subscription = subscription;
        subscription.request(1);
    }

    @Override
    public void onNext(Integer item) {
        process(item);
        subscription.request(1);
    }

    @Override
    public void onError(Throwable error) {
        handleError(error);
    }

    @Override
    public void onComplete() {
        finish();
    }

    private void process(Integer item) {
        // Xử lý một phần tử.
    }

    private void handleError(Throwable error) {
        // Ghi nhận hoặc chuyển tiếp lỗi.
    }

    private void finish() {
        // Giải phóng tài nguyên sau khi luồng kết thúc.
    }
}
```

Đây là khung minh họa, các phương thức nghiệp vụ cần được cung cấp trong lớp thực tế. Trong ứng dụng thật, Subscriber cũng cần cân nhắc:

- Nếu xử lý một phần tử thất bại, không bỏ qua lỗi một cách im lặng.
- Không gọi `request()` với số 0 hoặc số âm.
- Không giữ tài nguyên lâu hơn vòng đời Subscription.
- Không làm callback chặn quá lâu nếu Publisher dùng một Executor có ít thread.
- Hủy Subscription khi ứng dụng không còn cần dữ liệu.

## 7. Ví dụ Java hoàn chỉnh

Ví dụ sau dùng `SubmissionPublisher` và một Subscriber yêu cầu từng phần tử. Executor trực tiếp `Runnable::run` được chọn để thứ tự stdout dễ kiểm tra; trong ứng dụng bất đồng bộ thực tế, có thể truyền Executor phù hợp với mô hình thread của hệ thống.

Tạo tệp **FlowPublisherSubscriberDemo.java**:

```java
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;

public class FlowPublisherSubscriberDemo {
    private static final class OneAtATimeSubscriber
            implements Flow.Subscriber<Integer> {
        private Flow.Subscription subscription;

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            System.out.println("subscribed");
            subscription.request(1);
        }

        @Override
        public void onNext(Integer item) {
            System.out.println("item: " + item);
            subscription.request(1);
        }

        @Override
        public void onError(Throwable error) {
            System.out.println("error: "
                    + error.getClass().getSimpleName());
        }

        @Override
        public void onComplete() {
            System.out.println("complete");
        }
    }

    public static void main(String[] args) {
        SubmissionPublisher<Integer> publisher =
                new SubmissionPublisher<>(Runnable::run, 8);
        try {
            publisher.subscribe(new OneAtATimeSubscriber());
            System.out.println("subscribers: "
                    + publisher.getNumberOfSubscribers());

            publisher.submit(10);
            publisher.submit(20);
            publisher.submit(30);
        } finally {
            publisher.close();
        }
    }
}
```

Biên dịch và chạy trên Java 17+:

```bash
javac --release 17 FlowPublisherSubscriberDemo.java
java FlowPublisherSubscriberDemo
```

Stdout chính xác:

```text
subscribed
subscribers: 1
item: 10
item: 20
item: 30
complete
```

Diễn giải:

1. Subscriber đăng ký với Publisher.
2. Publisher gọi `onSubscribe()` và Subscriber yêu cầu một phần tử.
3. Mỗi lần `onNext()` nhận một phần tử, Subscriber yêu cầu thêm một phần tử.
4. Publisher phát lần lượt 10, 20 và 30.
5. Khi Publisher đóng, Subscriber nhận `onComplete()`.

Ví dụ sử dụng Executor trực tiếp để đơn giản hóa kiểm tra. Khi dùng Executor bất đồng bộ, callback có thể chạy trên thread khác; nếu chương trình cần chờ kết quả, hãy phối hợp bằng latch, future hoặc cơ chế đồng bộ thích hợp thay vì giả định `submit()` đã làm mọi callback hoàn tất.

## 8. Kết hợp nhiều Subscriber

Một Publisher có thể phát cùng dữ liệu cho nhiều Subscriber. Mỗi Subscriber có Subscription và demand riêng:

```text
                 +--> Subscriber A (request 1)
Publisher -------+
                 +--> Subscriber B (request 10)
```

Subscriber A và B có thể xử lý cùng một phần tử theo tốc độ khác nhau. Publisher phải tuân thủ demand của từng Subscription. Với SubmissionPublisher, buffer và độ trễ được quản lý riêng cho từng Subscriber; một Subscriber chậm có thể ảnh hưởng đến việc submit hoặc offer theo chính sách buffer của Publisher.

Khi thiết kế nhiều Subscriber:

- Xác định Subscriber nào cần nhận mọi phần tử và Subscriber nào có thể bỏ dữ liệu.
- Chọn dung lượng buffer phù hợp với tốc độ phát và khả năng tiêu thụ.
- Theo dõi độ trễ bằng các phương thức ước lượng của SubmissionPublisher.
- Tránh để một callback chậm giữ thread phát dữ liệu quá lâu.
- Xác định chính sách khi Subscriber lỗi hoặc hủy đăng ký.

## 9. Flow API và Stream API khác nhau

Tên gọi có thể gây nhầm lẫn, nhưng **java.util.concurrent.Flow** và **java.util.stream.Stream** phục vụ hai mô hình khác nhau.

| Tiêu chí | **Stream API** | **Flow API** |
|---|---|---|
| Package | `java.util.stream` | `java.util.concurrent` |
| Mô hình | Pipeline xử lý dữ liệu | Publisher–Subscriber |
| Cách kích hoạt | Terminal operation kéo pipeline chạy | Subscriber đăng ký và request dữ liệu |
| Backpressure | Không có giao thức demand giữa các bước | Có qua `Subscription.request(n)` |
| Vòng đời | Thường là pipeline hữu hạn, dùng một lần | Có thể là luồng dài hạn và bất đồng bộ |
| Thành phần chính | Source, intermediate operation, terminal operation | Publisher, Subscriber, Subscription, Processor |

Dùng Stream API cho xử lý collection hoặc nguồn dữ liệu có thể duyệt theo pipeline. Dùng Flow khi cần giao tiếp giữa nguồn phát và bên nhận theo mô hình đăng ký, bất đồng bộ và có điều tiết demand.

Flow API tương thích về mô hình với Reactive Streams. Các thư viện reactive có thể cung cấp adapter hoặc implementation riêng để kết nối với Flow; không nên giả định mọi Stream hoặc mọi Publisher đều có thể thay thế trực tiếp cho nhau.

## 10. Lỗi thường gặp và cách tránh

1. **Quên gọi request() trong onSubscribe()**: Publisher không có demand để phát phần tử. Hãy yêu cầu số lượng phù hợp ngay khi Subscription được thiết lập.
2. **Yêu cầu dữ liệu không giới hạn mà không cần thiết**: dùng `Long.MAX_VALUE` có thể khiến Subscriber nhận dữ liệu nhanh hơn khả năng xử lý. Chọn batch hoặc request từng phần tử khi cần backpressure.
3. **Gọi request(0) hoặc request số âm**: đây là yêu cầu không hợp lệ và dẫn tới tín hiệu lỗi theo hợp đồng Flow.
4. **Không xử lý onError()**: lỗi bất đồng bộ có thể bị bỏ sót hoặc không được chuyển đến nơi quản lý lỗi. Luôn triển khai callback này.
5. **Không xử lý onComplete()**: tài nguyên hoặc trạng thái nghiệp vụ có thể không được kết thúc đúng lúc.
6. **Gửi dữ liệu sau khi Publisher đã đóng**: sau khi close hoặc closeExceptionally, Publisher không còn nhận phần tử mới theo vòng đời đã kết thúc.
7. **Nhầm cancel() với dừng chắc chắn công việc nền**: cancel chấm dứt nhu cầu của Subscription; nó không tự động dừng mọi công việc ngoài Publisher đang thực hiện.
8. **Cho rằng callback luôn chạy trên thread gọi submit()**: SubmissionPublisher dùng Executor; callback có thể chạy trên thread khác. Đồng bộ trạng thái chia sẻ đúng cách.
9. **Để callback chặn quá lâu**: một Subscriber xử lý chậm có thể làm tăng lag và tiêu thụ buffer. Cân nhắc chuyển công việc nặng sang executor riêng nhưng vẫn quản lý demand.
10. **Coi Flow.Publisher là một triển khai cụ thể**: Publisher chỉ là interface. Dùng SubmissionPublisher hoặc một implementation phù hợp để thực sự phát dữ liệu.
11. **Nhầm Flow với Stream API**: Flow có subscription và backpressure; Stream có pipeline và terminal operation. Chọn theo mô hình dữ liệu của bài toán.

## Kết luận

Flow API trong Java 9 mô hình hóa luồng dữ liệu bằng **Publisher**, **Subscriber**, **Subscription** và **Processor**. Subscriber đăng ký với Publisher, nhận Subscription và điều khiển lượng dữ liệu thông qua `request(n)`. Publisher gửi phần tử bằng `onNext()` và kết thúc bằng `onComplete()` hoặc `onError()`.

**SubmissionPublisher** cung cấp một Publisher có sẵn trong JDK, hỗ trợ nhiều Subscriber, Executor và buffer. Khi triển khai ứng dụng, hãy thiết kế demand/backpressure, xử lý đầy đủ tín hiệu kết thúc, chọn executor và chính sách buffer phù hợp, đồng thời phân biệt Flow API với Stream API.
