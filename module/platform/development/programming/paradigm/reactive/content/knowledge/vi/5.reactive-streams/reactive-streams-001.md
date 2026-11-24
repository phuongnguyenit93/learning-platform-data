# Mục tiêu và phạm vi của đặc tả Reactive Streams

Trong module **REACTIVE_PROGRAMMING**, ta học cách xử lý các luồng sự kiện bất đồng bộ bằng hợp đồng `Publisher–Subscriber`, backpressure và những công cụ như `Mono` và `Flux`. Nền tảng chung của nhiều thư viện reactive trên JVM là **Reactive Streams**: một đặc tả xác định cách Publisher phát dữ liệu, cách Subscriber nhận dữ liệu và cách Subscriber báo trước nhu cầu của mình.

Reactive Streams ra đời để các thư viện xử lý luồng bất đồng bộ có thể phối hợp theo một hợp đồng chung, đặc biệt khi tốc độ phát dữ liệu của nguồn lớn hơn khả năng xử lý của consumer. Để sử dụng đúng, cần hiểu đặc tả giải quyết vấn đề gì, quy định những thành phần nào và những quyết định nào vẫn thuộc về thư viện hoặc ứng dụng.

## 1. Vấn đề mà Reactive Streams giải quyết

Giả sử một dịch vụ đọc sự kiện từ message broker với tốc độ 50.000 sự kiện mỗi giây, trong khi bước ghi dữ liệu xuống cơ sở dữ liệu chỉ xử lý được 5.000 sự kiện mỗi giây. Nếu nguồn cứ đẩy dữ liệu sang consumer mà không có cơ chế điều tiết, phần tử chưa xử lý sẽ tích tụ trong bộ nhớ. Hàng đợi có thể tăng liên tục, độ trễ tăng và cuối cùng làm cạn tài nguyên.

Một cách xử lý đơn giản là để producer chờ consumer sau mỗi phần tử. Tuy nhiên, nếu việc chờ sử dụng các thao tác blocking trên nhiều luồng, hệ thống có thể lãng phí thread, tăng chi phí chuyển ngữ cảnh và làm giảm khả năng mở rộng. Các thư viện khác nhau còn có thể định nghĩa API nhận dữ liệu và điều tiết theo cách không tương thích.

Reactive Streams đặt ra một hợp đồng chung cho việc trao đổi dữ liệu bất đồng bộ theo hướng **non-blocking backpressure**. Subscriber thông báo số phần tử mình sẵn sàng nhận; Publisher phải tôn trọng nhu cầu đó. Nhờ vậy, consumer có thể điều tiết lượng dữ liệu đi vào pipeline thay vì để nguồn phát không giới hạn.

Reactive Streams không làm cho một bước xử lý vốn chậm trở nên nhanh hơn. Nó cung cấp giao thức để các thành phần phối hợp tốc độ, giới hạn lượng dữ liệu được phép chuyển tiếp và quản lý vòng đời đăng ký.

## 2. Mục tiêu cốt lõi

Đặc tả hướng đến các mục tiêu sau:

1. **Chuẩn hóa giao tiếp:** định nghĩa những giao diện và tín hiệu tối thiểu để Publisher, Subscriber và các thư viện khác nhau có thể kết nối với nhau.
2. **Hỗ trợ luồng bất đồng bộ:** dữ liệu được truyền qua các tín hiệu, không yêu cầu consumer phải gọi một API đọc blocking cho từng phần tử.
3. **Điều tiết bằng nhu cầu:** Subscriber yêu cầu số phần tử muốn nhận thông qua `request(n)`, giúp hạn chế việc producer phát vượt quá khả năng tiếp nhận.
4. **Quản lý vòng đời:** Subscriber có thể hủy đăng ký bằng `cancel()`, còn Publisher thông báo kết thúc bình thường hoặc lỗi bằng tín hiệu đầu cuối.
5. **Tạo khả năng tương tác:** một Publisher tuân thủ đặc tả có thể kết nối với Subscriber tuân thủ cùng hợp đồng, dù hai bên đến từ các thư viện khác nhau.

Mục tiêu của đặc tả là chuẩn hóa **giao thức truyền tín hiệu và điều tiết nhu cầu**. Nó không định nghĩa toàn bộ kiến trúc của một ứng dụng reactive.

## 3. Bốn thành phần trong hợp đồng

Reactive Streams định nghĩa bốn giao diện cốt lõi trong package `org.reactivestreams`.

| Thành phần | Vai trò | Các phương thức chính |
|---|---|---|
| `Publisher<T>` | Nguồn có khả năng phát các phần tử kiểu `T` | `subscribe(Subscriber<? super T>)` |
| `Subscriber<T>` | Consumer nhận dữ liệu và tín hiệu kết thúc | `onSubscribe`, `onNext`, `onError`, `onComplete` |
| `Subscription` | Kênh điều khiển nhu cầu và hủy đăng ký | `request(long n)`, `cancel()` |
| `Processor<T, R>` | Vừa nhận dữ liệu như Subscriber, vừa phát dữ liệu như Publisher | Kết hợp hai nhóm phương thức tương ứng |

`Publisher` không cần biết chi tiết nghiệp vụ của Subscriber. Nó chỉ cần tuân thủ hợp đồng khi gửi tín hiệu. `Subscriber` cũng không điều khiển trực tiếp cách Publisher lấy dữ liệu; nó gửi yêu cầu thông qua `Subscription` được cung cấp khi đăng ký.

`Processor<T, R>` hữu ích khi một thành phần nằm giữa hai đoạn pipeline: nó nhận các phần tử kiểu `T`, biến đổi hoặc xử lý chúng, rồi phát các phần tử kiểu `R`. Các thư viện cấp cao thường cung cấp nhiều toán tử để thực hiện công việc này mà không cần người dùng tự viết Processor.

## 4. Giao thức tín hiệu và thứ tự cơ bản

Khi Subscriber gọi `publisher.subscribe(subscriber)`, Publisher phải cung cấp một `Subscription` qua `onSubscribe`. Sau đó, Publisher có thể gửi không hoặc nhiều phần tử qua `onNext`, rồi kết thúc bằng `onComplete` hoặc `onError`.

```text
Subscriber                         Publisher
    |                                  |
    |------ subscribe(subscriber) ---->|
    |<--------- onSubscribe -----------|
    |                                  |
    |---------- request(2) ----------->|
    |<----------- onNext(A) -----------|
    |<----------- onNext(B) -----------|
    |                                  |
    |------ request(2) --------------->|
    |<----------- onNext(C) -----------|
    |<----------- onNext(D) -----------|
    |<----------- onComplete ----------|
```

Sơ đồ minh họa một Publisher phát bốn phần tử theo hai đợt nhu cầu. Publisher có thể phát ít hơn số phần tử đã được yêu cầu, chẳng hạn khi nguồn chỉ còn một phần tử rồi hoàn tất.

Các quy tắc quan trọng của giao thức gồm:

- `onSubscribe` phải được gửi trước mọi tín hiệu `onNext`, `onError` hoặc `onComplete` của subscription đó.
- `onNext` chỉ được phát trong giới hạn nhu cầu mà Subscriber đã yêu cầu.
- Các tín hiệu của một subscription phải được gửi tuần tự, không chồng lấn nhau; thứ tự phần tử được phát phải được giữ nguyên.
- Một subscription kết thúc bằng `onComplete` hoặc `onError`. Sau tín hiệu đầu cuối, Publisher không được gửi thêm tín hiệu tiếp theo cho subscription đó.
- `request(n)` yêu cầu thêm `n` phần tử. Giá trị `n` phải lớn hơn 0; yêu cầu không hợp lệ phải được xử lý theo hợp đồng, trong đó Publisher báo lỗi bằng `onError` với `IllegalArgumentException`.
- `cancel()` yêu cầu Publisher dừng việc phát dữ liệu cho subscription. Hủy đăng ký là tín hiệu điều khiển, không phải một tín hiệu hoàn tất được gửi đến Subscriber.

`onComplete` và `onError` không tiêu thụ phần nhu cầu dành cho phần tử. Chúng là tín hiệu đầu cuối để Subscriber biết luồng đã kết thúc. Một Publisher cũng có thể hoàn tất ngay mà không phát `onNext` nào.

## 5. Backpressure: Subscriber chủ động báo nhu cầu

Backpressure là phần đặc trưng nhất của Reactive Streams. Thay vì để Publisher đẩy số lượng phần tử tùy ý, Subscriber thông báo số phần tử có thể tiếp nhận bằng `Subscription.request(n)`.

Ví dụ, khi Subscriber gọi `request(10)`, Publisher được phép gửi tối đa mười tín hiệu `onNext` theo nhu cầu hiện tại. Khi Subscriber xử lý xong và sẵn sàng nhận thêm, nó có thể yêu cầu một lô tiếp theo. Nếu Subscriber chưa yêu cầu thêm, Publisher không được phát vượt quá số lượng còn được phép.

```java
final class BatchSubscriber implements Subscriber<String> {
    private static final int BATCH_SIZE = 10;
    private Subscription subscription;

    @Override
    public void onSubscribe(Subscription subscription) {
        this.subscription = subscription;
        subscription.request(BATCH_SIZE);
    }

    @Override
    public void onNext(String item) {
        process(item);
    }

    // Ứng dụng gọi khi đã xử lý xong lô hiện tại và sẵn sàng nhận thêm.
    void requestNextBatch() {
        subscription.request(BATCH_SIZE);
    }

    @Override
    public void onError(Throwable error) {
        System.err.println("Stream failed: " + error.getMessage());
    }

    @Override
    public void onComplete() {
        System.out.println("Stream completed");
    }

    private void process(String item) {
        System.out.println(item);
    }
}
```

Subscriber trên yêu cầu mười phần tử khi đăng ký. Sau khi ứng dụng xử lý xong lô hiện tại, ứng dụng có thể gọi `requestNextBatch()` để yêu cầu thêm mười phần tử. Trong mã thực tế, cần quản lý thời điểm gọi phương thức này và vòng đời của subscription phù hợp với luồng xử lý của ứng dụng.

`request(Long.MAX_VALUE)` biểu thị nhu cầu không giới hạn. Cách dùng này hợp lệ trong giao thức nhưng làm giảm tác dụng điều tiết của backpressure ở subscription đó. Ngoài ra, `request(n)` đếm **số phần tử**, không phải số byte hay dung lượng bộ nhớ. Nếu mỗi phần tử có kích thước rất khác nhau, ứng dụng vẫn cần cân nhắc kích thước dữ liệu và chiến lược bộ nhớ.

Backpressure cũng không đồng nghĩa với việc mọi thành phần đều có bộ đệm nhỏ hoặc bộ nhớ toàn hệ thống luôn được giới hạn. Một implementation có thể cần bộ đệm để kết nối các nguồn khác tốc độ; kích thước bộ đệm, chiến lược prefetch và cách xử lý nguồn không thể điều tiết là quyết định của implementation. Hợp đồng yêu cầu không phát vượt nhu cầu, nhưng không tự chọn chính sách lưu trữ cho mọi tình huống.

## 6. Phạm vi mà đặc tả bao phủ

Reactive Streams tập trung vào ranh giới giữa Publisher và Subscriber trong một luồng dữ liệu bất đồng bộ. Có thể chia phạm vi thành các nhóm sau:

| Trong phạm vi | Ý nghĩa |
|---|---|
| Giao diện trao đổi | Cách Publisher đăng ký Subscriber và cung cấp Subscription |
| Vòng đời tín hiệu | Thứ tự `onSubscribe`, `onNext` và tín hiệu đầu cuối |
| Demand và backpressure | Cách Subscriber yêu cầu số phần tử và Publisher tôn trọng nhu cầu |
| Hủy đăng ký | Cách Subscriber yêu cầu dừng việc phát dữ liệu |
| Tính tương thích | Quy tắc để các implementation có thể giao tiếp qua cùng hợp đồng |

Đặc tả cũng đặt ra các yêu cầu về tính tuần tự và tính hợp lệ của tín hiệu, nhờ đó hai phía có thể dự đoán cách giao thức hoạt động ngay cả khi xử lý bất đồng bộ.

## 7. Những điều Reactive Streams không quy định

Hiểu ranh giới của đặc tả quan trọng không kém hiểu các giao diện. Reactive Streams không quyết định thay ứng dụng hoặc framework những vấn đề sau:

- **Lập lịch và thread:** đặc tả không bắt buộc Publisher phải chạy trên thread riêng, cũng không quy định thread pool hay scheduler nào được sử dụng. Tín hiệu có thể được phát đồng bộ hoặc bất đồng bộ, miễn là tuân thủ hợp đồng.
- **Chiến lược buffer và prefetch:** đặc tả không chọn kích thước hàng đợi, số phần tử đọc trước hoặc chính sách lưu trữ cụ thể cho từng implementation.
- **Giao thức truyền tải:** đặc tả không định nghĩa HTTP, TCP, message broker hay cách tuần tự hóa dữ liệu trên mạng.
- **Lưu trữ và độ bền dữ liệu:** nó không bảo đảm dữ liệu được ghi xuống cơ sở dữ liệu, lưu lại để phát lại hoặc tồn tại sau khi tiến trình dừng.
- **Ngữ nghĩa giao nhận:** nó không tự cung cấp bảo đảm at-most-once, at-least-once hay exactly-once cho nghiệp vụ hoặc hệ thống phân tán.
- **Xử lý nghiệp vụ và phục hồi lỗi:** nó quy định tín hiệu lỗi của giao thức, nhưng không quyết định retry bao nhiêu lần, fallback ra sao hoặc lỗi nào được xem là có thể phục hồi.
- **Tính không blocking của mã ứng dụng:** giao thức hỗ trợ backpressure không blocking, nhưng callback do ứng dụng viết vẫn có thể thực hiện thao tác blocking nếu người viết không kiểm soát.

Đặc tả cũng không bắt buộc mọi nguồn dữ liệu bên ngoài đều có khả năng điều tiết. Khi kết nối một nguồn không hỗ trợ backpressure, adapter hoặc framework phải chọn cách tích hợp phù hợp; nếu chọn buffer không giới hạn, rủi ro tăng bộ nhớ vẫn còn.

## 8. Reactive Streams trong hệ sinh thái Java

Reactive Streams cung cấp hợp đồng ở mức giao diện. Các thư viện xây dựng API và toán tử ở mức cao hơn để lập trình viên tạo pipeline dễ dàng hơn.

Trong Project Reactor:

- `Flux<T>` biểu diễn một Publisher có thể phát từ không đến nhiều phần tử.
- `Mono<T>` biểu diễn một Publisher có thể phát tối đa một phần tử.
- Cả `Flux` và `Mono` đều có thể được sử dụng ở nơi cần một `org.reactivestreams.Publisher`.
- Các toán tử như `map`, `filter`, `flatMap`, `take` và `onErrorResume` mô tả các bước biến đổi hoặc điều khiển luồng ở mức thư viện.

Ví dụ, có thể tiếp nhận một Publisher theo hợp đồng chung rồi chuyển thành pipeline Reactor:

```java
Publisher<Order> orderPublisher = orderSource();

Flux<Order> orders = Flux.from(orderPublisher);

Flux<String> orderIds = orders
    .filter(Order::isValid)
    .map(Order::getId);
```

`Flux.from` cho phép Reactor làm việc với một Publisher tương thích. Sau đó ta sử dụng toán tử của Reactor để mô tả xử lý nghiệp vụ. Các toán tử cụ thể, scheduler và chính sách prefetch thuộc API và implementation của Reactor, không phải các thành phần mới của đặc tả Reactive Streams.

Ví dụ, `subscribeOn` và `publishOn` điều khiển nơi thực thi trong Reactor. `limitRate` điều chỉnh cách Reactor chia nhỏ nhu cầu upstream. Đây là công cụ hữu ích khi xây dựng pipeline, nhưng không nên nhầm chúng với các phương thức được định nghĩa bởi bốn giao diện cốt lõi của Reactive Streams.

Các implementation có thể cung cấp bộ kiểm thử tương thích (Technology Compatibility Kit, TCK) để kiểm tra việc tuân thủ hợp đồng. TCK hỗ trợ kiểm tra giao thức của implementation; nó không thay thế kiểm thử nghiệp vụ, hiệu năng hoặc hành vi của toàn ứng dụng.

## 9. Khi nào cần quan tâm đến đặc tả?

Bạn nên hiểu Reactive Streams khi:

- Kết nối Publisher từ một thư viện với Subscriber hoặc pipeline của thư viện khác.
- Xử lý nguồn dữ liệu nhanh hơn consumer và cần kiểm soát lượng phần tử được phép đi tiếp.
- Tự xây dựng adapter, Publisher, Subscriber hoặc Processor.
- Điều tra lỗi liên quan đến request, cancel, tín hiệu đầu cuối hoặc việc nguồn phát vượt nhu cầu.
- Phân biệt quy tắc của giao thức với các tiện ích riêng của Reactor hay framework đang sử dụng.

Nếu chỉ sử dụng `Flux` và `Mono` ở mức nghiệp vụ, bạn không cần tự cài đặt bốn giao diện. Tuy vậy, hiểu hợp đồng bên dưới giúp dự đoán vì sao một pipeline chưa phát dữ liệu khi chưa có demand, vì sao `take` có thể hủy nguồn và vì sao một nguồn không hoàn tất có thể giữ subscription mở.

## 10. Checklist đọc một pipeline Reactive Streams

Khi xem xét một pipeline, hãy lần lượt trả lời:

1. Publisher nào tạo ra dữ liệu và Subscriber nào tiêu thụ dữ liệu?
2. Subscription được tạo ở đâu và demand ban đầu là bao nhiêu?
3. Toán tử hoặc thành phần nào yêu cầu thêm dữ liệu, có prefetch hay buffer không?
4. Điều kiện nào khiến subscription bị hủy?
5. Luồng kết thúc bằng `onComplete` hay `onError`, và lỗi được xử lý ở đâu?
6. Scheduler và các thao tác blocking được kiểm soát như thế nào trong implementation đang dùng?

Khi trả lời được những câu hỏi này, bạn có thể phân biệt phần bảo đảm bởi Reactive Streams với phần hành vi do Reactor và ứng dụng quyết định. Đó là nền tảng để thiết kế pipeline bất đồng bộ có kiểm soát nhu cầu, quản lý vòng đời subscription và phối hợp an toàn giữa các thành phần trong hệ sinh thái Java.
