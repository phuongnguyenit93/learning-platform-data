# Subscriber: tiếp nhận subscription, dữ liệu và tín hiệu kết thúc

Trong Reactive Streams, Subscriber là thành phần tiêu thụ dữ liệu từ Publisher. Subscriber nhận một Subscription, chủ động yêu cầu số phần tử muốn xử lý, tiếp nhận từng phần tử qua callback và kết thúc bằng một trong hai tín hiệu: hoàn tất hoặc lỗi. Hiểu đúng vòng đời này là nền tảng để sử dụng backpressure, hủy luồng và xử lý lỗi trong Project Reactor.

Bài học thuộc chương **Reactive Streams** của module **REACTIVE_PROGRAMMING**. Module tập trung vào các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure; người học sẽ vận dụng các khái niệm đó khi làm việc với Mono, Flux, toán tử, scheduler, xử lý lỗi và kiểm thử pipeline Java.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả thứ tự các callback mà Publisher gửi đến Subscriber.
- Giải thích vai trò của Subscription và cách Subscriber điều khiển nhu cầu bằng request.
- Phân biệt tín hiệu dữ liệu với hai tín hiệu kết thúc onComplete và onError.
- Viết Subscriber tuân thủ hợp đồng Reactive Streams và xử lý được luồng rỗng, luồng có dữ liệu, luồng lỗi.
- Dùng BaseSubscriber của Reactor để kiểm soát demand và hủy subscription.
- Nhận diện các lỗi phổ biến như không request dữ liệu, request không hợp lệ, xử lý chặn trong callback hoặc tiếp tục xử lý sau tín hiệu kết thúc.

## 1. Subscriber nằm ở đâu trong hợp đồng Reactive Streams?

Reactive Streams định nghĩa cách các thành phần trao đổi dữ liệu bất đồng bộ với khả năng điều tiết nhu cầu. Hợp đồng có bốn vai trò:

- **Publisher** là nguồn phát dữ liệu. Publisher cung cấp phương thức subscribe để một Subscriber đăng ký nhận dữ liệu.
- **Subscriber** là bên tiêu thụ. Nó nhận Subscription, yêu cầu dữ liệu và triển khai cách xử lý từng tín hiệu.
- **Subscription** là liên kết điều khiển giữa Publisher và Subscriber. Nó cung cấp hai thao tác chính: request(n) để yêu cầu dữ liệu và cancel() để hủy.
- **Processor** vừa là Subscriber vừa là Publisher, có thể nhận dữ liệu, biến đổi rồi phát tiếp.

Publisher không tự ý gửi vô hạn dữ liệu ngay khi Subscriber đăng ký. Sau khi nhận Subscription, Subscriber quyết định lượng dữ liệu sẵn sàng tiếp nhận bằng cách gọi request(n). Cơ chế này giúp hai phía phối hợp theo tốc độ tiêu thụ, thay vì mặc định bên phát luôn nhanh hơn bên nhận.

Trong Java, Reactive Streams định nghĩa các interface trong package org.reactivestreams. Java cũng có bộ interface Flow trong java.util.concurrent từ Java 9 với cùng mô hình giao tiếp. Hai bộ interface có thiết kế tương ứng nhưng là các kiểu Java riêng biệt; khi tích hợp thư viện, cần dùng đúng kiểu mà Publisher và Subscriber của thư viện đó hỗ trợ.

## 2. Vòng đời tín hiệu mà Subscriber nhận được

Một subscription thông thường có chuỗi tín hiệu như sau:

~~~text
Subscriber                 Publisher
    |                          |
    |-------- subscribe() ---->|
    |<------- onSubscribe -----|
    |                          |
    |-------- request(n) ----->|
    |<--------- onNext --------|  (0..n lần, tùy dữ liệu và demand)
    |<--------- onNext --------|
    |                          |
    |<------ onComplete -------|  hoặc onError(error)
~~~

Thứ tự quan trọng:

1. Subscriber gọi subscribe trên Publisher.
2. Publisher gọi onSubscribe và truyền vào một Subscription.
3. Subscriber lưu Subscription và gọi request(n) khi sẵn sàng nhận dữ liệu.
4. Publisher phát không quá lượng dữ liệu đã được yêu cầu, thông qua các lần gọi onNext.
5. Khi không còn dữ liệu, Publisher gọi onComplete; nếu xảy ra lỗi kết thúc luồng, Publisher gọi onError.

Một luồng có thể không phát phần tử nào. Ví dụ, một Publisher biểu diễn kết quả tìm kiếm rỗng có thể gọi onSubscribe rồi onComplete mà không gọi onNext. Nếu luồng lỗi ngay từ đầu, Subscriber có thể nhận onSubscribe rồi onError mà chưa nhận phần tử nào.

Hai tín hiệu kết thúc loại trừ lẫn nhau. Một subscription kết thúc bằng onComplete hoặc onError, không phải cả hai. Sau tín hiệu kết thúc, Publisher không được gửi thêm onNext cho subscription đó. Subscriber cần xem đây là ranh giới cuối cùng của vòng đời luồng.

## 3. onSubscribe: nhận quyền điều khiển subscription

onSubscribe là callback đầu tiên mà Subscriber nhận từ Publisher. Tham số Subscription cho phép Subscriber điều khiển việc nhận dữ liệu:

~~~java
@Override
public void onSubscribe(Subscription subscription) {
    this.subscription = subscription;
    subscription.request(1);
}
~~~

Trong ví dụ này, Subscriber yêu cầu một phần tử ngay khi đăng ký. Khi phần tử đó được xử lý xong, Subscriber có thể yêu cầu phần tiếp theo. Nếu không gọi request, Subscriber không tạo demand nên Publisher tuân thủ giao thức sẽ không gửi onNext cho phần đăng ký đó.

Thông thường, Subscriber cần giữ Subscription để có thể request thêm hoặc cancel ở thời điểm phù hợp. Không nên giữ nhiều Subscription cho cùng một Subscriber nếu không có thiết kế rõ ràng về việc hợp nhất các nguồn. Publisher tuân thủ hợp đồng sẽ gửi một Subscription cho lần đăng ký đó; nếu nhận được Subscription không mong đợi trong một triển khai phòng vệ, Subscriber có thể hủy Subscription dư thừa.

Có thể request ngay trong onSubscribe hoặc request sau khi một phần tử đã được xử lý. Quyết định phụ thuộc vào dung lượng xử lý và cách ứng dụng muốn điều tiết dữ liệu.

## 4. request(n): Subscriber chủ động điều tiết dữ liệu

request(n) biểu thị số phần tử mà Subscriber sẵn sàng nhận thêm. Demand được cộng dồn trên Subscription:

- request(1) yêu cầu thêm một phần tử.
- request(10) yêu cầu thêm mười phần tử.
- Nhiều lần request được cộng lại thành tổng nhu cầu còn lại.
- request(Long.MAX_VALUE) thường được dùng để biểu thị nhu cầu không giới hạn.

Giả sử Subscriber đã request(5), Publisher phát hai phần tử. Demand còn lại là ba. Nếu Subscriber gọi request(4), demand mới là bảy. Publisher chỉ được gửi onNext trong giới hạn demand còn lại.

request(0) hoặc request một số âm là yêu cầu không hợp lệ. Theo hợp đồng Reactive Streams, Publisher phải báo lỗi bằng IllegalArgumentException qua onError, trừ trường hợp subscription đã bị hủy hoặc đã kết thúc theo các quy tắc tương ứng. Vì vậy, Subscriber luôn phải truyền một số dương khi muốn nhận dữ liệu.

Demand không đồng nghĩa với số phần tử chắc chắn sẽ đến. Publisher có thể có ít dữ liệu hơn số đã yêu cầu, có thể hoàn tất sớm hoặc phát lỗi. Tín hiệu onComplete và onError không cần chờ demand còn lại; chúng thông báo trạng thái kết thúc của luồng.

### Ví dụ: xử lý từng phần tử rồi yêu cầu phần tiếp theo

Đoạn mã sau minh họa một Subscriber tối giản sử dụng Reactive Streams API:

~~~java
import org.reactivestreams.Subscriber;
import org.reactivestreams.Subscription;

public final class LoggingSubscriber implements Subscriber<Integer> {
    private Subscription subscription;

    @Override
    public void onSubscribe(Subscription subscription) {
        this.subscription = subscription;
        subscription.request(1);
    }

    @Override
    public void onNext(Integer value) {
        System.out.println("Nhận được: " + value);
        subscription.request(1);
    }

    @Override
    public void onError(Throwable error) {
        System.err.println("Luồng thất bại: " + error.getMessage());
    }

    @Override
    public void onComplete() {
        System.out.println("Luồng đã hoàn tất");
    }
}
~~~

Có thể đăng ký Subscriber này với Publisher tương thích, chẳng hạn một Flux của Reactor:

~~~java
import reactor.core.publisher.Flux;

Flux.range(1, 5)
    .subscribe(new LoggingSubscriber());
~~~

Subscriber bắt đầu bằng request(1). Sau mỗi lần nhận onNext, nó xử lý giá trị rồi yêu cầu thêm một phần tử. Publisher phát tối đa một phần tử cho mỗi đơn vị demand mới, cho đến khi phát hết dãy và gọi onComplete.

Ví dụ tập trung vào giao thức nên lược bỏ một số kiểm tra phòng vệ. Trong mã ứng dụng, cần bảo đảm Subscription đã được lưu trước khi dùng, xử lý an toàn nếu có đường đi đồng thời và không để callback ném lỗi ngoài dự kiến. Cũng cần nhớ rằng gọi request trong onNext có thể khiến Publisher tiếp tục phát đồng bộ tùy triển khai; xử lý callback quá nặng hoặc tạo chuỗi gọi lồng nhau sâu có thể ảnh hưởng hiệu năng.

## 5. onNext: tiếp nhận và xử lý một phần tử

Mỗi lần Publisher phát một phần tử, Subscriber nhận phần tử đó qua onNext(T item). Callback này chỉ được gọi khi có demand tương ứng và luồng chưa kết thúc.

Công việc trong onNext thường gồm:

- Kiểm tra hoặc chuyển đổi dữ liệu đầu vào.
- Cập nhật trạng thái tiêu thụ.
- Chuyển dữ liệu đến bước xử lý tiếp theo.
- Yêu cầu thêm dữ liệu nếu Subscriber muốn tiếp tục.

Subscriber nên giữ callback ngắn và tránh thực hiện I/O chặn kéo dài trong onNext. Trong ứng dụng reactive, callback có thể chạy trên event loop hoặc scheduler được lựa chọn bởi pipeline. Một thao tác chặn kéo dài có thể chiếm luồng xử lý và làm chậm các sự kiện khác. Nếu cần thực hiện công việc nặng hoặc gọi API chặn, hãy thiết kế ranh giới scheduler phù hợp thay vì tùy tiện chặn callback.

Subscriber cũng không nên sửa trực tiếp một đối tượng dữ liệu dùng chung nếu chưa có quy tắc đồng bộ. Dữ liệu có thể được chia sẻ với thành phần khác, và việc cập nhật trạng thái không an toàn có thể tạo ra lỗi tranh chấp.

Theo hợp đồng Reactive Streams, các tín hiệu mà một Subscriber nhận từ một subscription phải được tuần tự hóa: Publisher không được gọi chồng lấn các callback onNext, onError hoặc onComplete trên Subscriber đó. Điều này giúp Subscriber xử lý trạng thái theo trình tự. Tuy nhiên, nếu ứng dụng tự chia sẻ trạng thái Subscriber với các luồng khác, ứng dụng vẫn phải tự bảo vệ trạng thái chia sẻ đó.

## 6. onComplete và onError: hai cách kết thúc luồng

### onComplete

onComplete thông báo Publisher đã phát xong dữ liệu một cách bình thường. Callback này không có tham số:

~~~java
@Override
public void onComplete() {
    System.out.println("Đã nhận đủ dữ liệu");
    releaseResources();
}
~~~

onComplete có thể đến sau nhiều lần onNext hoặc đến ngay sau onSubscribe nếu Publisher rỗng. Subscriber nên dùng callback này để hoàn tất công việc, ghi nhận trạng thái thành công và giải phóng tài nguyên thuộc quyền sở hữu của mình.

### onError

onError(Throwable error) thông báo luồng kết thúc do lỗi:

~~~java
@Override
public void onError(Throwable error) {
    logger.error("Không thể xử lý luồng dữ liệu", error);
    releaseResources();
}
~~~

onError là tín hiệu kết thúc, không phải thông báo tạm thời để Subscriber tiếp tục chờ dữ liệu mới từ cùng subscription. Sau onError, Publisher không được tiếp tục phát onNext hoặc onComplete cho subscription đó.

Nếu nghiệp vụ cần thử lại, chuyển sang nguồn dự phòng hoặc thay thế lỗi bằng dữ liệu mặc định, hãy quyết định cách xử lý ở pipeline trước khi Subscriber cuối cùng nhận tín hiệu. Trong Reactor, các toán tử như retry, onErrorResume và onErrorReturn có thể thay đổi cách lỗi được truyền xuống subscriber.

Ví dụ, pipeline có thể chuyển lỗi thành một giá trị dự phòng:

~~~java
Flux<String> names =
    Flux.just("An", "Bình")
        .concatWith(Flux.error(
            new IllegalStateException("Nguồn dữ liệu bị lỗi")
        ))
        .onErrorResume(error -> Flux.just("Dữ liệu dự phòng"));
~~~

Với pipeline trên, lỗi được xử lý bởi onErrorResume. Subscriber ở cuối pipeline sẽ nhận các giá trị từ luồng thay thế và tín hiệu hoàn tất của luồng thay thế nếu nó thành công. Subscriber cuối không nhất thiết nhìn thấy onError ban đầu vì toán tử đã chuyển lỗi thành một luồng khác.

### Không nhầm lỗi nghiệp vụ với tín hiệu kết thúc

Một giá trị biểu diễn kết quả nghiệp vụ không thành công chưa chắc là tín hiệu onError. Ví dụ, một phần tử kiểu Result có thể chứa trạng thái từ chối thanh toán nhưng Publisher vẫn tiếp tục phát các kết quả khác. Chỉ lỗi làm kết thúc luồng mới được biểu diễn bằng onError. Hãy chọn mô hình dữ liệu phù hợp để không biến mọi tình huống nghiệp vụ thành lỗi hạ tầng.

## 7. cancel(): dừng việc nhận thêm dữ liệu

Subscriber gọi cancel() trên Subscription khi không còn muốn nhận dữ liệu. Các tình huống thường gặp:

- Người dùng rời khỏi màn hình đang theo dõi dữ liệu.
- Kết quả hiện tại đã đủ để hoàn thành nghiệp vụ.
- Yêu cầu phía trên đã hết thời gian chờ hoặc bị hủy.
- Subscriber phát hiện trạng thái khiến việc tiếp tục tiêu thụ không còn ý nghĩa.

Ví dụ:

~~~java
@Override
public void onNext(Integer value) {
    if (value >= 3) {
        subscription.cancel();
        return;
    }

    process(value);
    subscription.request(1);
}
~~~

Khi nhận giá trị đạt ngưỡng, Subscriber hủy Subscription và không yêu cầu thêm phần tử. cancel() là tín hiệu điều khiển, không phải tín hiệu kết thúc thành công. Subscriber không nên giả định rằng sau cancel chắc chắn sẽ nhận onComplete; Publisher cũng không có nghĩa vụ gửi một callback kết thúc để xác nhận việc hủy.

Việc hủy có thể không ngăn được một tín hiệu đã ở trên đường truyền hoặc một thao tác đã bắt đầu. Do đó, mã xử lý cần an toàn khi có công việc đang hoàn tất đồng thời với lúc hủy. Nếu công việc có tác dụng phụ như ghi dữ liệu hoặc trừ tiền, cần có cơ chế kiểm soát nghiệp vụ riêng; cancel không thể tự đảo ngược tác dụng phụ đã xảy ra.

## 8. Kiểm soát demand bằng BaseSubscriber của Reactor

Khi dùng Project Reactor, có thể kế thừa BaseSubscriber để tùy chỉnh thời điểm request và cancel mà không phải tự triển khai toàn bộ interface Subscriber:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class ControlledSubscriber extends BaseSubscriber<Integer> {

    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        System.out.println("Đã đăng ký");
        request(2);
    }

    @Override
    protected void hookOnNext(Integer value) {
        System.out.println("Xử lý: " + value);

        if (value == 5) {
            cancel();
            return;
        }

        request(1);
    }

    @Override
    protected void hookOnComplete() {
        System.out.println("Nguồn đã hoàn tất");
    }

    @Override
    protected void hookOnError(Throwable error) {
        System.err.println("Nguồn phát lỗi: " + error.getMessage());
    }
}
~~~

Đăng ký:

~~~java
Flux.range(1, 10)
    .subscribe(new ControlledSubscriber());
~~~

Subscriber bắt đầu với demand bằng hai phần tử. Mỗi lần xử lý một phần tử khác năm, nó yêu cầu thêm một phần tử. Khi nhận giá trị năm, nó hủy subscription. Vì vậy, các giá trị sau đó không còn được yêu cầu. Do hủy là thao tác điều khiển bất đồng bộ, không nên dựa vào việc Publisher luôn dừng tức thì tại đúng ranh giới của callback đang chạy.

BaseSubscriber giúp viết logic tiêu thụ theo nhu cầu, nhưng không thay thế việc hiểu giao thức. Nếu chỉ cần xử lý tất cả phần tử với demand không giới hạn, các overload subscribe đơn giản của Reactor thường phù hợp hơn. Chỉ dùng subscriber tùy chỉnh khi có yêu cầu thực sự về tốc độ tiêu thụ, giới hạn batch hoặc điều kiện hủy.

## 9. Demand trong pipeline có nhiều toán tử

Trong Reactor, Subscriber cuối không nhất thiết yêu cầu trực tiếp từng phần tử từ nguồn gốc. Giữa Subscriber và Publisher có thể có nhiều toán tử như map, filter, buffer, flatMap hoặc publishOn. Các toán tử này có thể biến đổi cách demand được truyền lên, lưu đệm một số phần tử hoặc yêu cầu trước một lượng dữ liệu để xử lý hiệu quả.

Ví dụ:

~~~java
Flux.range(1, 100)
    .filter(number -> number % 2 == 0)
    .map(number -> number * 10)
    .buffer(5)
    .subscribe(
        batch -> System.out.println("Batch: " + batch),
        error -> System.err.println("Lỗi: " + error),
        () -> System.out.println("Hoàn tất")
    );
~~~

Subscriber cuối nhận từng batch gồm tối đa năm giá trị đã qua filter và map. Demand của subscriber được phối hợp qua các toán tử; nó không có nghĩa nguồn ban đầu chỉ phát đúng năm số nguyên cho mỗi request(1) ở cuối pipeline. Filter có thể cần đọc nhiều phần tử nguồn để tạo một phần tử đầu ra, còn buffer gom nhiều phần tử thành một phần tử đầu ra.

Vì vậy, khi phân tích backpressure, cần xem toàn bộ pipeline và chính sách prefetch/buffering của các toán tử, thay vì chỉ nhìn vào số request ở Subscriber cuối. Một toán tử có thể có hàng đợi nội bộ; nếu dữ liệu được đẩy vào nhanh hơn tốc độ xử lý và hàng đợi không được kiểm soát, bộ nhớ vẫn có thể tăng cao.

## 10. Các quy tắc và lỗi thường gặp

| Tình huống | Hành vi đúng theo hợp đồng | Cách Subscriber nên xử lý |
|---|---|---|
| Không gọi request | Không có demand nên không có onNext | Yêu cầu một lượng dữ liệu dương khi sẵn sàng |
| request(0) hoặc số âm | Yêu cầu không hợp lệ; Publisher phải báo IllegalArgumentException qua onError theo giao thức | Luôn xác thực số lượng request |
| Nguồn không có phần tử | Có thể nhận onComplete ngay sau onSubscribe | Hoàn tất bình thường, không chờ onNext |
| Nguồn phát lỗi | Nhận onError thay cho onComplete | Ghi nhận lỗi, giải phóng tài nguyên và kết thúc xử lý |
| Đã nhận tín hiệu kết thúc | Không còn onNext hoặc tín hiệu kết thúc thứ hai | Không tiếp tục request hay xử lý dữ liệu của subscription đã kết thúc |
| Gọi cancel | Ngừng yêu cầu thêm; không có cam kết nhận onComplete | Xử lý an toàn với công việc đang diễn ra |
| Callback chạy quá lâu | Có thể làm chậm luồng phát tín hiệu hoặc scheduler | Giữ callback ngắn, chuyển việc chặn sang scheduler phù hợp |
| Ném exception từ callback | Callback của Subscriber phải trả về bình thường theo hợp đồng | Bắt và xử lý lỗi trong logic callback; không dùng throw để báo lỗi ngược cho Publisher |

Một Subscriber đúng giao thức cần lưu ý thêm:

- Không truyền null làm phần tử dữ liệu hoặc tham số lỗi. Reactive Streams không cho phép tín hiệu dữ liệu null.
- Không giả định mọi request sẽ được đáp ứng đầy đủ; nguồn có thể hoàn tất hoặc lỗi trước đó.
- Không gọi request sau khi đã kết thúc hoặc hủy subscription.
- Không coi cancel là bảo đảm rằng mọi tác vụ phụ đã được dừng hoặc hoàn tác.
- Không dùng onError như một callback ghi log rồi tiếp tục chờ dữ liệu. Đây là tín hiệu kết thúc.
- Không thực hiện công việc chặn kéo dài trên event loop của ứng dụng reactive.

## 11. Bài tập vận dụng

Một dịch vụ nhận luồng giao dịch từ Publisher. Mỗi giao dịch cần được kiểm tra và ghi vào kho dữ liệu. Kho dữ liệu chỉ xử lý ổn định tối đa 20 giao dịch đồng thời. Khi có lỗi kết nối, luồng cần dừng và báo lỗi cho tầng gọi.

Hãy thiết kế Subscriber hoặc pipeline Reactor đáp ứng các yêu cầu:

1. Nhận Subscription và bắt đầu với một batch có kích thước phù hợp, ví dụ 10 phần tử.
2. Sau khi xử lý xong batch, mới yêu cầu thêm dữ liệu.
3. Nếu giao dịch không hợp lệ theo nghiệp vụ, ghi nhận kết quả từ chối mà không nhất thiết kết thúc toàn bộ luồng.
4. Nếu kết nối kho dữ liệu thất bại và không thể phục hồi, hủy hoặc kết thúc pipeline theo chính sách lỗi.
5. Khi tầng gọi hủy yêu cầu, Subscriber phải dừng tiêu thụ và giải phóng tài nguyên thuộc quyền sở hữu của nó.

Khi đánh giá lời giải, hãy xác định rõ phần nào là demand của Reactive Streams, phần nào là giới hạn đồng thời của kho dữ liệu và phần nào là quy tắc nghiệp vụ. request(10) giới hạn lượng demand mà Subscriber yêu cầu tại thời điểm đó; nó không tự bảo đảm chỉ có tối đa 10 giao dịch đang được ghi đồng thời nếu pipeline bên trong còn có cơ chế xử lý song song hoặc buffer khác. Giới hạn đồng thời cần được áp dụng đúng ở bước ghi dữ liệu.

## Kết luận

Subscriber là bên điều khiển nhu cầu tiêu thụ trong hợp đồng Reactive Streams. Nó nhận Subscription qua onSubscribe, yêu cầu dữ liệu bằng request(n), xử lý phần tử qua onNext và nhận đúng một tín hiệu kết thúc là onComplete hoặc onError. Khi không còn nhu cầu, Subscriber có thể gọi cancel để dừng việc nhận thêm. Nắm vững thứ tự tín hiệu và cách demand truyền qua pipeline giúp bạn xây dựng các luồng Mono và Flux có backpressure, xử lý lỗi và hủy tác vụ đúng cách trong ứng dụng Java.
