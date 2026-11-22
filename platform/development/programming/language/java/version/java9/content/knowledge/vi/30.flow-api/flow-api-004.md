# Nhu cầu tiêu thụ qua request trong Java Flow

Java 9 giới thiệu `java.util.concurrent.Flow`, bộ interface chuẩn hóa mô hình Reactive Streams trong JDK. Trong mô hình này, subscriber chủ động thông báo cho publisher biết mình sẵn sàng nhận bao nhiêu phần tử thông qua `Flow.Subscription.request(n)`.

Cơ chế đó gọi là *backpressure* (điều tiết ngược): tốc độ phát dữ liệu được điều phối theo nhu cầu tiêu thụ. Subscriber có thể yêu cầu từng phần tử, theo lô hoặc yêu cầu không giới hạn. Publisher phải tôn trọng lượng demand đã được cấp và không phát nhiều phần tử hơn subscriber đã yêu cầu.

Đề bài tập trung vào `request`: hiểu demand được cộng dồn ra sao, khi nào nên yêu cầu thêm, cách hủy subscription và cách `SubmissionPublisher` phối hợp buffer với nhu cầu của subscriber.

## 1. Flow gồm Publisher, Subscriber và Subscription

Ba interface cốt lõi tạo thành một luồng dữ liệu:

- `Flow.Publisher<T>`: nguồn phát các phần tử kiểu T; subscriber đăng ký qua `subscribe`.
- `Flow.Subscriber<T>`: bên nhận dữ liệu, xử lý phần tử và nhận tín hiệu kết thúc hoặc lỗi.
- `Flow.Subscription`: liên kết riêng giữa một publisher và một subscriber; subscriber dùng nó để yêu cầu dữ liệu hoặc hủy đăng ký.

Trình tự cơ bản:

1. Subscriber gọi `publisher.subscribe(subscriber)`.
2. Publisher gọi `subscriber.onSubscribe(subscription)` để cấp subscription.
3. Subscriber gọi `subscription.request(n)` để cấp demand.
4. Publisher phát tối đa số phần tử đã được yêu cầu qua `onNext(item)`.
5. Subscriber có thể yêu cầu thêm trong lúc xử lý phần tử.
6. Luồng kết thúc bằng `onComplete()`, hoặc kết thúc lỗi bằng `onError(error)`.

~~~text
Publisher                 Subscriber
    |                          |
    |<------ subscribe --------|
    |                          |
    |------ onSubscribe ------>|
    |                          |
    |<------- request(2) ------|
    |                          |
    |--------- onNext(1) ----->|
    |--------- onNext(2) ----->|
    |                          |
    |<------- request(2) ------|
    |                          |
    |--------- onNext(3) ----->|
    |--------- onNext(4) ----->|
    |                          |
    |------ onComplete ------->|
~~~

Một subscriber nhận đúng một subscription cho một lần đăng ký. Demand thuộc về subscription đó; hai subscriber khác nhau có thể có tốc độ tiêu thụ và lượng demand khác nhau dù cùng nhận dữ liệu từ một publisher.

## 2. request(n) biểu diễn lượng demand

Chữ ký:

~~~java
void request(long n)
~~~

`request(n)` báo cho publisher rằng subscriber có thể tiếp nhận thêm tối đa n phần tử. n phải là số dương.

Ví dụ:

~~~java
@Override
public void onSubscribe(Flow.Subscription subscription) {
    this.subscription = subscription;
    subscription.request(5);
}
~~~

Subscriber cấp quyền nhận tối đa 5 phần tử. Publisher có thể phát ít hơn nếu nguồn dữ liệu đã kết thúc hoặc chưa có phần tử; request không bắt buộc publisher phải tạo ra dữ liệu.

### Demand được cộng dồn

Các lần gọi request bổ sung demand còn lại:

~~~java
subscription.request(2);
subscription.request(3);
~~~

Nếu chưa phần tử nào được phát, publisher có thể phát tối đa tổng cộng 5 phần tử. Nếu đã phát một phần, request mới được cộng vào phần demand còn lại.

Có thể hình dung:

| Thao tác | Demand còn lại |
|---|---:|
| Ban đầu | 0 |
| `request(2)` | 2 |
| Phát 1 phần tử | 1 |
| `request(3)` | 4 |
| Phát 4 phần tử | 0 |

Đây là lượng phần tử tối đa được phép phát, không phải lời hứa rằng publisher sẽ phát đủ số lượng đó ngay lập tức.

### Yêu cầu không giới hạn

~~~java
subscription.request(Long.MAX_VALUE);
~~~

`Long.MAX_VALUE` được dùng để biểu diễn demand không giới hạn (unbounded demand). Sau khi yêu cầu như vậy, subscriber không còn điều tiết số lượng phần tử bằng request theo từng lô.

Chỉ dùng unbounded demand khi subscriber có khả năng xử lý luồng dữ liệu liên tục và publisher có cơ chế tài nguyên phù hợp. Yêu cầu không giới hạn không có nghĩa hệ thống có bộ nhớ vô hạn hoặc mọi nguồn phát đều không thể bị quá tải.

## 3. Backpressure kiểm soát tốc độ tiêu thụ như thế nào?

Giả sử publisher nhận dữ liệu nhanh hơn subscriber có thể xử lý. Nếu publisher cứ phát dữ liệu mà không quan tâm khả năng tiếp nhận, subscriber có thể bị quá tải hoặc phải lưu quá nhiều phần tử trong bộ nhớ.

Backpressure tạo ra một hợp đồng:

- Subscriber quyết định lượng dữ liệu mình sẵn sàng nhận.
- Publisher không được phát vượt quá demand hiện có.
- Subscriber yêu cầu thêm sau khi xử lý xong một phần dữ liệu.
- Publisher có thể giữ dữ liệu trong buffer, giảm tốc độ phát hoặc áp dụng chính sách riêng khi không còn chỗ chứa.

Ví dụ subscriber chỉ xử lý theo lô 10 phần tử:

~~~java
@Override
public void onSubscribe(Flow.Subscription subscription) {
    this.subscription = subscription;
    subscription.request(10);
}

@Override
public void onNext(Event event) {
    process(event);

    if (batchCompleted()) {
        subscription.request(10);
    }
}
~~~

Đoạn mã trên là minh họa cho chiến lược yêu cầu theo lô; `process` và `batchCompleted` là logic của ứng dụng, không phải API Flow.

Không nên yêu cầu thêm ngay sau mỗi `onNext` nếu subscriber vẫn đang bận xử lý một lô lớn. Hãy chọn kích thước lô dựa trên thời gian xử lý, dung lượng bộ nhớ, độ trễ mong muốn và khả năng phát của nguồn.

## 4. Vòng đời Subscription và các quy tắc quan trọng

### request chỉ được gọi sau onSubscribe

Subscriber nhận subscription trong callback `onSubscribe`. Đây là nơi thông thường để lưu subscription và gửi request đầu tiên:

~~~java
@Override
public void onSubscribe(Flow.Subscription subscription) {
    this.subscription = subscription;
    subscription.request(1);
}
~~~

Không có subscription thì subscriber không có đối tượng để điều khiển demand hoặc hủy đăng ký.

### request phải là số dương

Nếu subscriber gọi `request(0)` hoặc `request(-1)`, đó là yêu cầu không hợp lệ. Theo hợp đồng Flow, publisher phải báo lỗi qua `onError` với `IllegalArgumentException`.

Không dùng số 0 để tạm dừng. Muốn tạm ngừng nhận dữ liệu, subscriber chỉ cần không yêu cầu thêm khi demand hiện tại đã dùng hết. Khi sẵn sàng, subscriber gọi request với số dương.

### Publisher không được phát vượt demand

Nếu subscriber đã yêu cầu 2 phần tử, publisher không được gửi phần tử thứ ba cho subscription đó cho tới khi có thêm request.

Publisher có thể phát ít hơn demand nếu không có dữ liệu. Demand là giới hạn trên cho số lần `onNext`, không phải số lượng bắt buộc.

### Tín hiệu của một subscriber được tuần tự hóa

Các lời gọi `onSubscribe`, `onNext`, `onError` và `onComplete` cho một subscription phải tuân theo thứ tự tín hiệu của Flow. Publisher không được gọi chồng lấn các tín hiệu tới cùng subscriber. Việc phát có thể diễn ra trên thread khác nhau ở các thời điểm khác nhau; subscriber không nên giả định callback luôn chạy trên thread đã gọi `subscribe` hoặc `request`.

Tránh thực hiện công việc blocking lâu trong callback. Nếu xử lý nặng, có thể chuyển công việc sang executor riêng và chỉ request thêm khi có đủ năng lực tiếp nhận dữ liệu tiếp theo.

## 5. request và cancel

`Flow.Subscription` có hai phương thức:

~~~java
void request(long n);
void cancel();
~~~

`cancel()` yêu cầu publisher ngừng phát dữ liệu cho subscription đó:

~~~java
@Override
public void onNext(Event event) {
    if (shouldStop(event)) {
        subscription.cancel();
        return;
    }

    process(event);
    subscription.request(1);
}
~~~

Sau khi hủy, subscriber không nên tiếp tục yêu cầu dữ liệu. Publisher sẽ ngừng gửi các tín hiệu tiếp theo theo hợp đồng subscription, nhưng việc hủy có thể không thu hồi được công việc đã bắt đầu hoặc callback đang chạy.

Cancel khác với request(0):

- `cancel()` là yêu cầu kết thúc subscription.
- `request(0)` là request không hợp lệ và dẫn tới tín hiệu lỗi theo hợp đồng Flow.

Nếu một subscriber chỉ muốn tạm thời không nhận thêm dữ liệu, hãy dùng chiến lược demand hữu hạn: không gọi request thêm cho tới khi sẵn sàng.

## 6. SubmissionPublisher: publisher có buffer trong JDK

Java 9 cung cấp `SubmissionPublisher<T>`, một implementation của `Flow.Publisher<T>`. Nó hỗ trợ phát dữ liệu bất đồng bộ qua Executor và lưu tạm các phần tử cho subscriber trong buffer.

~~~java
SubmissionPublisher<Integer> publisher =
    new SubmissionPublisher<>();
~~~

Một số thao tác chính:

| API | Ý nghĩa |
|---|---|
| `subscribe(subscriber)` | Đăng ký subscriber |
| `submit(item)` | Gửi một phần tử tới các subscriber |
| `offer(item, ...)` | Thử gửi với chính sách xử lý khi buffer không tiếp nhận được |
| `close()` | Ngừng nhận phần tử mới và báo hoàn tất sau các phần tử đã gửi |
| `closeExceptionally(error)` | Kết thúc publisher bằng lỗi |
| `getNumberOfSubscribers()` | Số subscriber hiện tại |
| `estimateMinimumDemand()` | Ước lượng demand nhỏ nhất của các subscriber |
| `estimateMaximumLag()` | Ước lượng độ trễ lớn nhất trong buffer |

### Buffer không thay thế demand

Khi subscriber chưa request, SubmissionPublisher có thể lưu phần tử trong buffer. Khi subscriber cấp demand, publisher mới phát các phần tử đang chờ theo giới hạn đã yêu cầu.

Nếu buffer đầy, `submit` có thể phải chờ cho tới khi có chỗ. `offer` cho phép cấu hình thời gian chờ và hàm xử lý khi phần tử không được tiếp nhận. Vì vậy, backpressure vẫn cần đi cùng chính sách buffer và cách producer gửi dữ liệu.

### Demand độc lập theo từng subscriber

Nếu có nhiều subscriber, mỗi subscriber có subscription và demand riêng. Một subscriber chậm không có cùng lượng demand với subscriber nhanh. SubmissionPublisher duy trì trạng thái buffer/lag cho từng subscriber; producer cần cân nhắc tác động của subscriber chậm tới việc gửi dữ liệu.

Các phương thức `estimateMinimumDemand()` và `estimateMaximumLag()` là số liệu ước lượng để quan sát, không phải cơ chế đồng bộ hoặc cam kết rằng trạng thái sẽ không đổi ngay sau khi đọc.

## 7. Ví dụ Java chạy được: request theo từng lô

Ví dụ sử dụng SubmissionPublisher. Subscriber yêu cầu 2 phần tử ban đầu, sau mỗi 2 phần tử lại yêu cầu thêm 2. Publisher gửi 5 số rồi đóng. CountDownLatch giúp chương trình chính chờ callback `onComplete` trước khi kết thúc.

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class FlowRequestExample {
    public static void main(String[] args) throws InterruptedException {
        SubmissionPublisher<Integer> publisher =
            new SubmissionPublisher<>();
        CountDownLatch completed = new CountDownLatch(1);

        Flow.Subscriber<Integer> subscriber =
            new Flow.Subscriber<Integer>() {
                private Flow.Subscription subscription;
                private int received;

                @Override
                public void onSubscribe(Flow.Subscription subscription) {
                    this.subscription = subscription;
                    System.out.println("subscribed; request=2");
                    subscription.request(2);
                }

                @Override
                public void onNext(Integer item) {
                    received++;
                    System.out.println("onNext=" + item);

                    if (received % 2 == 0) {
                        System.out.println("request=2");
                        subscription.request(2);
                    }
                }

                @Override
                public void onError(Throwable error) {
                    System.out.println("onError="
                        + error.getClass().getSimpleName());
                    completed.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("onComplete");
                    completed.countDown();
                }
            };

        publisher.subscribe(subscriber);

        for (int item = 1; item <= 5; item++) {
            publisher.submit(item);
        }
        publisher.close();

        if (!completed.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Subscriber did not complete");
        }
    }
}
~~~

Lưu trong tệp `FlowRequestExample.java`, biên dịch và chạy với Java 9 trở lên:

~~~shell
javac --release 9 -Xlint:all FlowRequestExample.java
java FlowRequestExample
~~~

Kết quả stdout chính xác:

~~~text
subscribed; request=2
onNext=1
onNext=2
request=2
onNext=3
onNext=4
request=2
onNext=5
onComplete
~~~

Giải thích:

1. Subscriber nhận subscription và yêu cầu 2 phần tử.
2. Publisher gửi 1 và 2; demand ban đầu đã được sử dụng hết.
3. Sau phần tử thứ hai, subscriber yêu cầu thêm 2.
4. Publisher gửi 3 và 4; subscriber lại yêu cầu thêm 2.
5. Publisher gửi phần tử cuối cùng là 5. Vì producer đã gọi close và không còn phần tử chờ, subscriber nhận onComplete.
6. Subscriber chỉ nhận 5 phần tử, đúng với dữ liệu producer gửi; request cuối có thể lớn hơn số phần tử còn lại.

Ví dụ không phụ thuộc thứ tự thread cụ thể vì các callback của subscriber được tuần tự hóa và chương trình chính đợi tín hiệu hoàn tất. Trong hệ thống thực tế, không nên dựa vào tên thread hoặc thời gian callback chính xác.

## 8. Chọn chiến lược request phù hợp

| Chiến lược | Cách dùng | Khi phù hợp |
|---|---|---|
| Từng phần tử | `request(1)`, xử lý xong rồi request tiếp | Xử lý tuần tự, mỗi phần tử tốn tài nguyên |
| Theo lô | `request(batchSize)`, yêu cầu thêm khi lô được xử lý | Xử lý batch, ghi database hoặc gửi network theo nhóm |
| Demand lớn | Yêu cầu một số lượng lớn hữu hạn | Subscriber có năng lực xử lý cao và nguồn được kiểm soát |
| Unbounded | `request(Long.MAX_VALUE)` | Subscriber có thể nhận liên tục và không cần điều tiết bằng demand |

Không có batch size tối ưu cho mọi ứng dụng. Cần cân nhắc:

- Bộ nhớ dùng để giữ phần tử đang chờ.
- Thời gian xử lý trung bình và độ dao động.
- Độ trễ mà người dùng chấp nhận.
- Khả năng producer phát dữ liệu.
- Số lượng subscriber và subscriber chậm nhất.
- Hành vi khi buffer đầy: chờ, từ chối hoặc bỏ dữ liệu theo chính sách.

## 9. Lỗi thường gặp

- **Quên gọi request trong onSubscribe:** subscriber sẽ không nhận phần tử nào từ publisher tuân thủ Flow cho tới khi có demand.
- **Gọi request(0) để tạm dừng:** đây là request không hợp lệ; hãy ngừng yêu cầu thêm.
- **Yêu cầu Long.MAX_VALUE trong mọi trường hợp:** có thể bỏ qua khả năng điều tiết và làm tăng áp lực lên subscriber.
- **Nghĩ request(n) bảo đảm nhận đúng n phần tử:** n là giới hạn tối đa; publisher có thể phát ít hơn.
- **Nghĩ mỗi request thay thế demand cũ:** các request được cộng dồn với demand còn lại.
- **Nhầm demand với số phần tử đang nằm trong buffer:** demand là lượng được phép phát; buffer là nơi lưu dữ liệu chưa được tiêu thụ.
- **Gọi cancel rồi tiếp tục request:** subscription đã được yêu cầu hủy; không nên tiếp tục sử dụng.
- **Dùng cancel để dừng producer toàn cục:** cancel hủy một subscription; publisher có thể còn các subscriber khác.
- **Giả định callback chạy trên thread gọi request:** SubmissionPublisher có thể phát bất đồng bộ qua Executor.
- **Blocking lâu trong onNext:** có thể làm chậm việc tiêu thụ và ảnh hưởng buffer; chuyển xử lý nặng sang executor phù hợp và kiểm soát demand.
- **Coi SubmissionPublisher là giải pháp tự động chống mọi quá tải:** vẫn cần chọn buffer, chính sách submit/offer và chiến lược demand phù hợp.

## 10. Tài liệu tham khảo chính thức

- [Flow — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Flow.html): các interface Publisher, Subscriber, Subscription và hợp đồng tín hiệu.
- [SubmissionPublisher — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html): buffer, submit, offer, close và số liệu demand/lag.
- [JEP 266: More Concurrency Updates](https://openjdk.org/jeps/266): giới thiệu Flow API và SubmissionPublisher trong Java 9.
- [Reactive Streams Specification](https://github.com/reactive-streams/reactive-streams-jvm): các quy tắc về demand, tín hiệu và backpressure mà Flow dựa trên.