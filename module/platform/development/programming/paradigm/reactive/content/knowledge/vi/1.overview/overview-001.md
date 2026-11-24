# Tổng quan

## Lập trình phản ứng là gì và bài toán thay đổi theo thời gian

Trong module **REACTIVE_PROGRAMMING**, chúng ta học cách mô hình hóa dữ liệu và sự kiện bất đồng bộ thành các luồng có thể kết hợp, biến đổi và kiểm soát. Lập trình phản ứng (reactive programming) là cách tổ chức chương trình xoay quanh những giá trị hoặc sự kiện xuất hiện theo thời gian: khi dữ liệu mới đến, các bước xử lý đã khai báo sẽ tiếp tục chạy và chuyển kết quả đến nơi tiêu thụ.

Ý tưởng này hữu ích khi ứng dụng không chỉ đọc một giá trị tại một thời điểm. Giá cổ phiếu thay đổi liên tục, trạng thái đơn hàng được cập nhật qua nhiều bước, cảm biến gửi dữ liệu định kỳ, hay nhiều dịch vụ trả kết quả vào những thời điểm khác nhau. Thay vì liên tục hỏi “đã có dữ liệu mới chưa?” và tự quản lý nhiều callback, ta có thể mô tả một pipeline phản ứng với từng tín hiệu đến.

### 1. Bài toán của dữ liệu thay đổi theo thời gian

Hãy hình dung một ứng dụng theo dõi đơn hàng. Trạng thái ban đầu có thể là **CREATED**, sau đó lần lượt chuyển thành **PAID**, **PACKING**, **SHIPPED** và **DELIVERED**. Nếu chương trình chỉ lấy một bản ghi đơn hàng tại thời điểm người dùng mở trang, nó chỉ nhìn thấy một ảnh chụp (snapshot) của trạng thái. Khi trạng thái thay đổi, giao diện hoặc dịch vụ liên quan cần nhận được thông tin mới.

Có một số cách xử lý quen thuộc:

| Cách tiếp cận | Khó khăn khi dữ liệu liên tục thay đổi |
| --- | --- |
| Polling: hỏi nguồn dữ liệu theo chu kỳ | Có thể hỏi quá thường xuyên, tạo tải không cần thiết; hoặc hỏi quá thưa khiến thông tin cập nhật chậm |
| Callback lồng nhau | Luồng xử lý khó đọc khi nhiều tác vụ bất đồng bộ phụ thuộc lẫn nhau; xử lý lỗi và hủy tác vụ dễ bị phân tán |
| Tạo một luồng cho mỗi tác vụ | Có thể tiêu tốn nhiều tài nguyên khi số lượng kết nối hoặc tác vụ đồng thời tăng |
| Hàng đợi tự quản lý | Phải tự quyết định giới hạn bộ nhớ, thứ tự xử lý, cách phản ứng khi bên nhận chậm và cách truyền lỗi |

Lập trình phản ứng cung cấp một mô hình thống nhất để biểu diễn chuỗi dữ liệu, mô tả các bước xử lý và xác định cách bên tiêu thụ nhận tín hiệu. Mô hình này không tự động giải quyết mọi vấn đề về tải hay đồng thời; nó cung cấp các hợp đồng và công cụ để ta xử lý những vấn đề đó một cách rõ ràng.

### 2. Tư duy theo luồng dữ liệu

Một luồng (stream) là chuỗi các phần tử có thể xuất hiện theo thời gian. Luồng có thể hữu hạn, chẳng hạn danh sách kết quả của một truy vấn, hoặc kéo dài liên tục, chẳng hạn các sự kiện cảm biến. Mỗi phần tử có thể được biến đổi, lọc, kết hợp với luồng khác hoặc chuyển đến một thành phần tiêu thụ.

Một pipeline thường có ba phần:

1. **Nguồn dữ liệu** tạo ra các phần tử hoặc sự kiện.
2. **Các toán tử** biến đổi, lọc, kết hợp hoặc điều phối luồng.
3. **Subscriber** nhận kết quả và thực hiện hành động ở điểm cuối.

Ví dụ, một pipeline theo dõi giá có thể đọc các cập nhật, bỏ qua giá không vượt ngưỡng, chuyển phần tử sang định dạng phù hợp rồi gửi thông báo. Các bước mô tả việc cần làm; thư viện reactive điều phối việc truyền tín hiệu khi có dữ liệu.

Trong Reactor, nhiều pipeline chỉ được mô tả khi ta gọi các toán tử. Việc đăng ký (subscribe) mới kích hoạt quá trình tiêu thụ đối với các nguồn lạnh (cold publisher) như **Flux.fromIterable** hoặc **Mono.fromCallable**. Nguồn nóng (hot publisher) có thể phát sự kiện độc lập với từng subscriber; một subscriber đăng ký muộn có thể không nhận được những sự kiện đã phát trước đó. Vì vậy, cần hiểu vòng đời của nguồn dữ liệu trước khi chọn cách chia sẻ hoặc đăng ký.

### 3. Ví dụ: phản ứng với cập nhật giá

Thư viện Project Reactor cung cấp **Flux** để biểu diễn một luồng có từ không đến nhiều phần tử. Ví dụ dưới đây mô phỏng năm lần cập nhật giá, mỗi giây một lần, rồi chỉ giữ những cập nhật vượt ngưỡng:

~~~java
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;

import reactor.core.publisher.Flux;

record PriceUpdate(String symbol, BigDecimal price, Instant observedAt) {}

Flux<PriceUpdate> priceChanges =
    Flux.interval(Duration.ofSeconds(1))
        .map(index -> new PriceUpdate(
            "ACME",
            new BigDecimal("100.00").add(
                new BigDecimal("0.25").multiply(BigDecimal.valueOf(index))
            ),
            Instant.now()
        ))
        .take(5)
        .filter(update ->
            update.price().compareTo(new BigDecimal("100.50")) > 0
        );

priceChanges.subscribe(
    update -> System.out.println(
        update.symbol() + ": " + update.price() + " at " + update.observedAt()
    ),
    error -> System.err.println("Nguồn dữ liệu gặp lỗi: " + error.getMessage()),
    () -> System.out.println("Đã nhận hết dữ liệu mô phỏng")
);
~~~

Trong ví dụ này, **Flux.interval** phát một số thứ tự theo chu kỳ. **map** chuyển mỗi số thành một đối tượng cập nhật giá, **take(5)** giới hạn nguồn còn năm phần tử và **filter** chỉ giữ giá lớn hơn **100.50**. Cuối cùng, **subscribe** cung cấp cách xử lý phần tử, lỗi và tín hiệu hoàn tất.

Ví dụ dùng Java **record** (Java 16 trở lên) để giữ phần khai báo dữ liệu ngắn gọn. Trong ứng dụng thực tế, nguồn giá thường đến từ message broker, WebSocket hoặc một dịch vụ bên ngoài thay vì **Flux.interval**. Ta cũng thường trả **Flux<PriceUpdate>** từ tầng dịch vụ để tầng gọi quyết định đăng ký và xử lý kết quả, thay vì gọi **subscribe** tùy tiện bên trong mọi phương thức.

### 4. Publisher, Subscriber và hợp đồng Reactive Streams

Reactive Streams là một đặc tả về truyền dữ liệu bất đồng bộ có kiểm soát nhu cầu (demand). Đặc tả này định nghĩa các vai trò và tín hiệu để publisher và subscriber phối hợp với nhau:

| Thành phần | Trách nhiệm |
| --- | --- |
| **Publisher<T>** | Cung cấp một chuỗi tín hiệu chứa các phần tử kiểu **T** |
| **Subscriber<T>** | Đăng ký nhận tín hiệu và xử lý phần tử, lỗi hoặc hoàn tất |
| **Subscription** | Đại diện cho quan hệ đăng ký; cho phép yêu cầu số phần tử và hủy đăng ký |

Trình tự cơ bản diễn ra như sau:

1. Subscriber gọi **subscribe** trên publisher.
2. Publisher gọi **onSubscribe(subscription)** để cung cấp đối tượng đăng ký.
3. Subscriber gọi **subscription.request(n)** để yêu cầu tối đa **n** phần tử.
4. Publisher gửi các phần tử bằng **onNext(value)** theo nhu cầu đã được yêu cầu.
5. Khi kết thúc, publisher gửi một tín hiệu cuối: **onComplete()** hoặc **onError(error)**.

Subscriber có thể gọi **cancel()** để hủy đăng ký. Sau tín hiệu kết thúc, publisher không gửi thêm tín hiệu dữ liệu cho đăng ký đó. Một subscription hợp lệ phải nhận số lượng yêu cầu dương; yêu cầu **Long.MAX_VALUE** biểu thị nhu cầu không giới hạn.

Hợp đồng này tách việc tạo dữ liệu khỏi tốc độ mà bên nhận sẵn sàng xử lý. Đây là nền tảng để xây dựng backpressure.

### 5. Backpressure: khi bên nhận chậm hơn bên phát

Giả sử một dịch vụ phát 20.000 sự kiện mỗi giây, trong khi subscriber chỉ xử lý được 2.000 sự kiện mỗi giây. Nếu cứ đưa mọi sự kiện vào một hàng đợi không giới hạn, bộ nhớ có thể tăng liên tục và cuối cùng làm ứng dụng mất ổn định.

Backpressure (điều tiết áp lực ngược) là cơ chế để subscriber báo cho publisher biết mình muốn nhận bao nhiêu phần tử thông qua **request(n)**. Publisher tuân theo nhu cầu đó thay vì gửi tùy ý. Khi subscriber xử lý xong một phần, nó có thể yêu cầu thêm.

Backpressure không có nghĩa mọi nguồn dữ liệu đều có thể bị dừng lại. Một thiết bị hoặc hệ thống bên ngoài có thể không hỗ trợ giảm tốc độ phát. Trong trường hợp đó, pipeline cần một chính sách phù hợp, chẳng hạn:

- **Buffer** một lượng phần tử có giới hạn để hấp thụ chênh lệch ngắn hạn.
- **Drop** phần tử khi không thể tiếp nhận thêm và việc bỏ dữ liệu được nghiệp vụ cho phép.
- **Latest** chỉ giữ giá trị mới nhất khi các giá trị trung gian không còn quan trọng.
- **Error** kết thúc pipeline khi vượt giới hạn thay vì âm thầm tiêu thụ thêm tài nguyên.

Chọn chính sách nào phụ thuộc vào ý nghĩa dữ liệu. Bỏ một mẫu cảm biến cũ có thể chấp nhận được; bỏ một sự kiện thanh toán hoặc chuyển trạng thái đơn hàng thường không thể chấp nhận. Vì vậy, cần xác định rõ yêu cầu về tính đầy đủ, thứ tự và độ trễ trước khi cấu hình backpressure.

### 6. Mono và Flux trong Project Reactor

Project Reactor là thư viện reactive phổ biến trong hệ sinh thái Java. Hai kiểu dữ liệu chính của thư viện là:

| Kiểu | Số phần tử | Ví dụ sử dụng |
| --- | --- | --- |
| **Mono<T>** | Không hoặc một phần tử | Tìm một đơn hàng, lưu một bản ghi, nhận một kết quả đơn |
| **Flux<T>** | Không, một hoặc nhiều phần tử | Theo dõi sự kiện đơn hàng, đọc nhiều bản ghi, nhận luồng cập nhật |

Cả **Mono<T>** và **Flux<T>** đều triển khai hợp đồng **Publisher**, nên có thể dùng các khái niệm subscriber, subscription và backpressure. Ví dụ về chữ ký phương thức:

~~~java
Mono<Order> findOrder(OrderId id);

Flux<OrderEvent> watchOrder(OrderId id);
~~~

**Mono.empty()** biểu diễn việc hoàn tất mà không phát giá trị; **Mono<Void>** thường dùng khi chỉ quan tâm một tác vụ hoàn tất hay thất bại. **Flux.empty()** là luồng hoàn tất ngay mà không có phần tử. Việc chọn **Mono** hay **Flux** giúp chữ ký phương thức thể hiện rõ số lượng kết quả mà người gọi có thể nhận.

Không nên nhầm **Flux** với **java.util.stream.Stream**. Java Stream chủ yếu mô tả phép xử lý trên một nguồn dữ liệu theo mô hình pull, thường hữu hạn và chạy trong luồng gọi. **Flux** và **Mono** tuân theo Reactive Streams, hỗ trợ tín hiệu bất đồng bộ và điều tiết nhu cầu. Hai mô hình có thể cùng dùng toán tử như **map** hoặc **filter**, nhưng hợp đồng thực thi và vòng đời của chúng khác nhau.

### 7. Bất đồng bộ, scheduler và xử lý lỗi

Reactive và bất đồng bộ có liên quan nhưng không đồng nghĩa. Một pipeline reactive có thể chạy đồng bộ nếu nguồn và các toán tử thực thi trên luồng hiện tại. Scheduler quyết định nơi một phần công việc được thực thi; chuyển scheduler không tự làm cho một thao tác blocking trở thành non-blocking.

Trong Reactor, một số scheduler thường gặp là:

- **Schedulers.parallel()** phù hợp với các tác vụ tính toán ngắn, thiên về CPU.
- **Schedulers.boundedElastic()** phù hợp khi cần cô lập lời gọi blocking hoặc API cũ chưa có phiên bản bất đồng bộ.
- **Schedulers.single()** chạy công việc trên một luồng tuần tự dùng chung.

**subscribeOn** ảnh hưởng đến nơi subscription và nguồn upstream bắt đầu thực thi. **publishOn** chuyển việc xử lý các toán tử downstream kể từ vị trí được đặt nó. Chỉ nên chuyển scheduler khi có lý do rõ ràng; việc chuyển luồng quá nhiều làm pipeline khó theo dõi và có thể tạo thêm chi phí điều phối.

Trong pipeline reactive, lỗi được truyền thành tín hiệu **onError** và thường kết thúc chuỗi hiện tại. Ta có thể dùng **onErrorReturn** để thay bằng một giá trị dự phòng, **onErrorResume** để chuyển sang publisher khác, hoặc **retry**/**retryWhen** cho thao tác có thể thử lại. Retry cần giới hạn và cân nhắc tính idempotent của thao tác; thử lại vô hạn một yêu cầu ghi dữ liệu có thể tạo tác dụng phụ lặp lại.

Các bài kiểm thử cũng nên xác minh tín hiệu, thứ tự và thời điểm hoàn tất thay vì chỉ kiểm tra một giá trị trả về. Reactor cung cấp **StepVerifier** trong module **reactor-test**:

~~~java
StepVerifier.create(
        Flux.just(10, 20, 30)
            .map(value -> value / 10)
            .filter(value -> value > 1)
    )
    .expectNext(2, 3)
    .verifyComplete();
~~~

Đoạn kiểm thử xác nhận pipeline phát lần lượt **2** và **3**, sau đó hoàn tất. Với nguồn phụ thuộc thời gian hoặc scheduler, có thể dùng các công cụ kiểm thử thời gian ảo của Reactor để tránh phải chờ thật trong mỗi bài kiểm thử.

### 8. Khi nào nên dùng lập trình phản ứng?

Reactive programming thường phù hợp khi ứng dụng xử lý nhiều I/O đồng thời, tiêu thụ luồng sự kiện, kết hợp nhiều nguồn bất đồng bộ hoặc cần điều tiết tốc độ giữa producer và consumer. Pipeline cũng giúp diễn đạt các bước biến đổi dữ liệu liên tiếp theo một cấu trúc thống nhất.

Mô hình này đi kèm chi phí học và vận hành: cần hiểu vòng đời subscription, cách lỗi lan truyền, scheduler, context và backpressure. Một tác vụ đồng bộ đơn giản với ít I/O có thể dễ đọc hơn khi viết theo phong cách imperative. Vì vậy, hãy chọn reactive khi đặc tính của luồng dữ liệu và mức đồng thời tạo ra lợi ích rõ ràng, không chỉ vì muốn dùng một API mới.

Khi đọc hoặc thiết kế một pipeline, hãy tự hỏi:

- Nguồn phát ra một kết quả, nhiều kết quả hay một luồng liên tục?
- Nguồn là cold hay hot, và subscriber đăng ký vào thời điểm nào?
- Bên nhận yêu cầu dữ liệu theo nhu cầu ra sao?
- Điều gì xảy ra nếu bên nhận chậm, nguồn lỗi hoặc subscriber hủy đăng ký?
- Phần nào cần chạy trên scheduler khác, và phần nào có thể blocking?
- Có thể kiểm thử thứ tự tín hiệu, lỗi và hoàn tất một cách xác định không?

Đây là nền tảng cho các phần tiếp theo của module: hiểu sâu hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; thực hành **Mono**, **Flux** và các toán tử kết hợp; điều khiển scheduler; xử lý lỗi; và kiểm thử pipeline trong hệ sinh thái Java.
