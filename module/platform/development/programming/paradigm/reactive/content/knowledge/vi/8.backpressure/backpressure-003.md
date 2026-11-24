# Áp lực ngược khác gì giới hạn tốc độ và kiểm soát lưu lượng

Khi một hệ thống reactive nhận dữ liệu nhanh hơn khả năng xử lý, hàng đợi có thể tăng mãi, độ trễ phình lên hoặc bộ nhớ cạn. Có nhiều cách xử lý tình huống này, nhưng **backpressure**, **rate limiting** và **flow control** giải quyết những khía cạnh khác nhau của vấn đề. Chọn nhầm cơ chế dễ tạo ra một pipeline vẫn quá tải, dù nhìn bề ngoài đã có giới hạn.

Bài học thuộc chương **Áp lực ngược** của module `REACTIVE_PROGRAMMING`. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; người học thực hành `Mono`, `Flux`, kết hợp toán tử, điều khiển scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Bài này tập trung phân biệt cơ chế điều tiết nhu cầu với chính sách giới hạn tốc độ và các cơ chế kiểm soát lưu lượng rộng hơn.

Sau bài học, bạn có thể:

- Giải thích backpressure dựa trên nhu cầu của Subscriber và hợp đồng `request(n)`.
- Phân biệt giới hạn số phần tử đang được yêu cầu với giới hạn số phần tử trong một đơn vị thời gian.
- Nhận diện flow control ở cấp ứng dụng, giao thức và hệ thống.
- Chọn cách xử lý khi nguồn có thể tạm dừng hoặc khi nguồn nóng không thể chờ.
- Đọc đúng ý nghĩa của `limitRate`, `onBackpressureBuffer`, `delayElements` và giới hạn concurrency trong Reactor.

## 1. Ba câu hỏi khác nhau

Hãy bắt đầu bằng ba câu hỏi mà mỗi cơ chế trả lời:

| Cơ chế | Câu hỏi chính | Đại lượng được điều tiết |
|---|---|---|
| **Backpressure** | Consumer hiện có thể nhận thêm bao nhiêu phần tử? | Nhu cầu hoặc số phần tử được phép phát theo subscription. |
| **Rate limiting** | Trong một khoảng thời gian, hệ thống được phép xử lý hoặc chấp nhận bao nhiêu yêu cầu? | Tốc độ theo thời gian, ví dụ 100 yêu cầu/giây. |
| **Flow control** | Bên gửi cần điều chỉnh việc truyền như thế nào để phù hợp với năng lực hoặc dung lượng hiện có của bên nhận? | Tín dụng, cửa sổ, hàng đợi, mức độ bận hoặc dung lượng khả dụng. |

Flow control là khái niệm rộng. Backpressure là một kiểu điều khiển dựa trên phản hồi nhu cầu, thường được xem là cơ chế flow control ở cấp luồng dữ liệu. Rate limiting là chính sách giới hạn tốc độ; nó có thể tham gia một hệ thống flow control lớn hơn nhưng không tự động thay thế backpressure.

## 2. Backpressure: phát theo nhu cầu của consumer

Trong Reactive Streams, `Subscriber` thông báo nhu cầu qua `Subscription.request(n)`. `n` là số phần tử mà Subscriber sẵn sàng nhận thêm từ subscription đó. Publisher phải tôn trọng nhu cầu đã tích lũy và không được phát `onNext` vượt quá số lượng được yêu cầu.

Ví dụ, Subscriber yêu cầu từng lô:

```java
final class BatchSubscriber<T> implements Subscriber<T> {
    private Subscription subscription;
    private int remainingInBatch = 20;

    @Override
    public void onSubscribe(Subscription subscription) {
        this.subscription = subscription;
        subscription.request(20);
    }

    @Override
    public void onNext(T item) {
        process(item);

        if (--remainingInBatch == 0) {
            remainingInBatch = 20;
            subscription.request(20);
        }
    }

    @Override
    public void onError(Throwable error) {
        log.error("Stream failed", error);
    }

    @Override
    public void onComplete() {
        log.info("Stream completed");
    }

    private void process(T item) {
        // Xử lý một phần tử.
    }

}
```

Ví dụ khởi tạo số phần tử còn lại trước khi gọi `request(20)`, rồi yêu cầu lô tiếp theo sau khi xử lý đủ 20 phần tử. Nhờ đó, ví dụ cũng xử lý được trường hợp Publisher phát tín hiệu đồng bộ ngay trong lời gọi `request`. Trong ứng dụng thực tế, cần bổ sung đồng bộ nếu trạng thái lô còn được truy cập từ thread khác. Subscriber không cần yêu cầu trước toàn bộ dữ liệu; nó có thể chỉ yêu cầu khi đã xử lý xong phần đang có.

Một luồng demand cơ bản:

```text
Subscriber                         Publisher
    |                                  |
    | -------- request(20) ----------> |
    |                                  |
    | <--------- onNext(1) ----------- |
    | <--------- onNext(2) ----------- |
    |              ...                 |
    | <-------- onNext(20) ----------- |
    |                                  |
    |       xử lý xong batch            |
    | -------- request(20) ----------> |
    |                                  |
```

Backpressure điều chỉnh lượng dữ liệu đang được phép chuyển qua subscription. Con số `20` không có nghĩa là 20 phần tử mỗi giây. Nếu consumer xử lý 20 phần tử trong 10 mili giây, nó có thể yêu cầu lô tiếp theo rất nhanh. Nếu mỗi phần tử mất một giây, nhịp yêu cầu sẽ chậm lại tương ứng.

Đó là điểm cốt lõi: **backpressure phản ánh khả năng tiếp nhận hiện tại của consumer, không áp đặt một tốc độ cố định theo đồng hồ**.

### Khi nguồn có thể tôn trọng demand

Nếu Publisher kiểm soát được nguồn phát, nó có thể giảm hoặc tạm dừng việc lấy dữ liệu khi không còn demand. Chẳng hạn, một publisher đọc từ nguồn phân trang có thể chỉ truy vấn trang tiếp theo sau khi downstream yêu cầu thêm phần tử. Cách này giúp tránh tạo ra hàng đợi lớn ở giữa.

Với một nguồn không thể tạm dừng, chẳng hạn cảm biến, callback từ thư viện bên ngoài hoặc một luồng sự kiện nóng, hệ thống phải quyết định điều gì xảy ra khi dữ liệu đến trong lúc downstream chưa sẵn sàng: lưu vào bộ đệm, bỏ phần tử, giữ giá trị mới nhất, hoặc báo lỗi khi vượt giới hạn. Các chính sách này xử lý sự chênh lệch giữa nguồn và consumer; chúng không làm cho nguồn nóng tự nhiên tuân theo demand.

## 3. Rate limiting: giới hạn tốc độ theo thời gian

Rate limiter đặt ra ngân sách theo thời gian. Ví dụ:

- Một API key được gọi tối đa 100 lần trong mỗi giây.
- Một dịch vụ gửi tối đa 5 email mỗi giây tới nhà cung cấp.
- Một worker chỉ bắt đầu tối đa 30 tác vụ trong một phút.

Rate limiter thường cần một khái niệm thời gian và một chính sách khi ngân sách đã hết. Nó có thể từ chối, trì hoãn hoặc xếp hàng yêu cầu cho đến khi có ngân sách mới.

Một thuật toán phổ biến là **token bucket**. Bucket có dung lượng tối đa `B`; token được bổ sung với tốc độ `r` token mỗi giây. Mỗi yêu cầu tiêu thụ một hoặc nhiều token. Nếu bucket không đủ token, yêu cầu bị từ chối hoặc phải chờ theo chính sách của ứng dụng.

```text
             bổ sung r token/giây
                      |
                      v
              +---------------+
              |   TOKEN       |
              |   BUCKET      |  dung lượng tối đa B
              +---------------+
                      |
                yêu cầu token
                      |
             +--------+--------+
             |                 |
         đủ token          thiếu token
             |                 |
             v                 v
         cho phép       từ chối hoặc chờ
```

Token bucket cho phép một lượng burst ngắn nếu bucket đã tích lũy token, trong khi vẫn giới hạn tốc độ trung bình theo tốc độ bổ sung. Một số thuật toán khác như fixed window, sliding window và leaky bucket có cách xử lý burst và ranh giới cửa sổ khác nhau.

Rate limiting không nhất thiết biết consumer đang có bao nhiêu demand. Ví dụ, API gateway có thể giới hạn một khách hàng ở 100 request/giây dù backend hiện đang rất rảnh. Ngược lại, một Subscriber có thể yêu cầu 100 phần tử trong một lần, rồi xử lý hết chúng trong vài mili giây; bản thân `request(100)` không giới hạn tốc độ theo giây.

## 4. Flow control: điều chỉnh truyền dữ liệu theo năng lực nhận

Flow control mô tả cách bên gửi và bên nhận phối hợp để tránh bên nhận bị áp đảo. Cơ chế có thể nằm ở nhiều tầng:

| Tầng | Ví dụ | Cách phối hợp |
|---|---|---|
| Reactive Streams | `Subscription.request(n)` | Subscriber cấp thêm nhu cầu cho Publisher. |
| Message broker | Consumer prefetch hoặc credit | Broker chỉ gửi số message nằm trong giới hạn chưa xác nhận. |
| Network transport | TCP receive window | Receiver quảng bá dung lượng nhận; sender điều chỉnh lượng dữ liệu đang truyền. |
| HTTP/2 | Stream hoặc connection flow-control window | Sender tiêu thụ credit và chỉ tiếp tục khi nhận thêm window update. |
| Ứng dụng | Semaphore hoặc giới hạn hàng đợi | Producer chỉ nhận thêm công việc khi còn slot hoặc capacity. |

Các cơ chế này có thể cùng tồn tại. Một ứng dụng dùng Reactive Streams vẫn chạy trên TCP; TCP flow control bảo vệ khả năng nhận dữ liệu của socket, trong khi backpressure của ứng dụng điều tiết việc phát các phần tử trong pipeline. TCP không biết một phần tử `Flux<Order>` đã được xử lý nghiệp vụ hay chưa. Tương tự, `request(n)` của Reactive Streams không trực tiếp điều khiển cửa sổ TCP.

Flow control thường dựa trên credit hoặc window. Ví dụ, consumer của một message broker có thể cho phép tối đa 50 message chưa xác nhận. Khi xác nhận một message, consumer giải phóng một credit để broker gửi message tiếp theo. Cơ chế này tương tự demand theo số lượng, nhưng giao thức và thời điểm giải phóng credit thuộc broker.

## 5. So sánh bằng một tình huống quá tải

Giả sử một nguồn tạo 1.000 sự kiện mỗi giây, còn consumer chỉ xử lý được 200 sự kiện mỗi giây.

**Dùng backpressure:** nếu nguồn hỗ trợ tạm dừng hoặc đọc theo nhu cầu, consumer chỉ yêu cầu phần tử khi còn khả năng xử lý. Tốc độ phát thực tế sẽ giảm theo nhịp tiêu thụ. Nếu nguồn bắt buộc phát liên tục, cần thêm chính sách cho phần dữ liệu không thể chờ.

**Dùng rate limiting:** hệ thống giới hạn việc chấp nhận hoặc xử lý ở 200 sự kiện mỗi giây. 800 sự kiện còn lại mỗi giây cần được từ chối, trì hoãn, lưu ở một hàng đợi có giới hạn hoặc xử lý theo chính sách khác. Nếu cứ xếp hàng vô hạn, rate limiter chỉ chuyển điểm quá tải sang bộ nhớ.

**Dùng flow control:** producer và consumer trao đổi capacity, ví dụ consumer cấp 200 credit và cấp lại credit sau khi xử lý. Producer chỉ truyền dữ liệu khi còn credit. Cách triển khai cụ thể có thể dựa trên demand, cửa sổ hoặc giới hạn số message đang chờ xác nhận.

Ba cơ chế có thể kết hợp. Một dịch vụ có thể dùng flow control để giới hạn số tác vụ đang bay, backpressure để bảo vệ từng pipeline reactive, và rate limiter để tuân thủ quota của API bên ngoài.

## 6. Nhìn đúng ý nghĩa các toán tử Reactor

Các toán tử Reactor có tên gần nhau nhưng điều khiển những đại lượng khác nhau.

### `limitRate`: chia nhỏ yêu cầu upstream

```java
Flux<Order> orders = orderSource
    .limitRate(64);
```

`limitRate(64)` điều tiết cách Reactor yêu cầu dữ liệu từ upstream bằng các lô có giới hạn. Nó hữu ích khi muốn tránh một yêu cầu upstream quá lớn và điều phối việc lấy phần tử theo demand downstream.

`limitRate` **không** có nghĩa là tối đa 64 phần tử mỗi giây. Nếu downstream xử lý nhanh và tiếp tục yêu cầu, các lô tiếp theo có thể được yêu cầu liên tục. Tham số này liên quan đến batching/prefetch của demand, không phải một quota theo thời gian.

### `onBackpressureBuffer`: lưu phần tử khi downstream chưa nhận

```java
Flux<Event> buffered = hotEvents
    .onBackpressureBuffer(500);
```

Toán tử này dùng buffer có giới hạn để giữ các phần tử đến khi downstream có thể nhận. Khi vượt giới hạn, pipeline sẽ báo lỗi overflow theo chính sách của overload được chọn. Buffer hữu ích khi có thể hấp thụ một burst ngắn, nhưng nó không tăng năng lực xử lý của consumer.

Nếu nguồn tiếp tục nhanh hơn consumer trong thời gian dài, buffer sẽ đầy. Vì vậy, hãy chọn dung lượng dựa trên burst có thể chấp nhận, bộ nhớ sẵn có và cách hệ thống xử lý overflow. Buffer không giới hạn thường chỉ trì hoãn thời điểm hết bộ nhớ.

### `onBackpressureDrop` và `onBackpressureLatest`: chấp nhận mất dữ liệu có chủ đích

```java
Flux<Metric> sampledState = hotMetrics
    .onBackpressureLatest();

Flux<AuditEvent> bestEffort = hotAuditEvents
    .onBackpressureDrop(event -> recordDropped(event));
```

`onBackpressureDrop` bỏ các phần tử đến khi downstream chưa có demand; có thể cung cấp callback để ghi nhận phần tử bị bỏ. `onBackpressureLatest` giữ lại giá trị mới nhất trong lúc downstream chưa sẵn sàng, thay thế giá trị chờ cũ bằng giá trị mới.

Hai chiến lược này chỉ phù hợp khi nghiệp vụ chấp nhận mất dữ liệu. Ví dụ, màn hình giám sát thường chỉ cần trạng thái mới nhất, trong khi sự kiện thanh toán hoặc audit thường cần được bảo toàn. Cần kiểm tra semantics của nguồn và toán tử trong pipeline cụ thể: các toán tử `onBackpressure...` xử lý tình trạng thiếu demand bằng buffer/drop/latest theo chính sách của chúng; chúng không khiến một nguồn nóng có thể tạm dừng phát.

### `delayElements`: tạo khoảng cách thời gian giữa các phần tử

```java
Flux<Event> paced = events
    .delayElements(Duration.ofMillis(100));
```

Ví dụ này thêm độ trễ giữa các phần tử trong một subscription, tạo nhịp phát chậm hơn xấp xỉ một phần tử mỗi 100 mili giây khi không có yếu tố khác chi phối. Nó có thể hữu ích để làm chậm một luồng, nhưng không phải một rate limiter dùng chung cho nhiều subscription hoặc nhiều instance. Nó cũng không tự thực thi quota toàn cục của một API.

### Giới hạn concurrency không phải giới hạn request mỗi giây

```java
Flux<Result> results = requests
    .flatMap(this::callRemoteService, 8);
```

Tham số `8` giới hạn số inner publisher được subscribe đồng thời theo cấu hình của `flatMap`. Đây là cách kiểm soát số tác vụ đang chạy cùng lúc và có thể giúp bảo vệ tài nguyên. Nếu mỗi tác vụ hoàn tất rất nhanh, hệ thống vẫn có thể bắt đầu nhiều hơn 8 tác vụ trong một giây. Muốn giới hạn tốc độ theo thời gian, cần một rate limiter riêng.

## 7. Chọn cơ chế theo mục tiêu

| Mục tiêu | Cơ chế nên xem xét | Câu hỏi cần trả lời |
|---|---|---|
| Consumer chỉ muốn nhận khi đã có capacity | Backpressure qua `request(n)` | Nguồn có thể tạm dừng hoặc chỉ đọc theo nhu cầu không? |
| API bên ngoài có quota 100 request/giây | Rate limiter | Quota áp dụng theo user, API key, instance hay toàn hệ thống? |
| Không muốn có quá 20 tác vụ đồng thời | Giới hạn concurrency hoặc semaphore | Slot được giải phóng khi nào, kể cả khi có lỗi hoặc timeout? |
| Broker không nên gửi quá nhiều message chưa ack | Flow control bằng prefetch/credit | Ack có giải phóng credit và broker có giữ message bền vững không? |
| Chỉ cần trạng thái mới nhất | Latest/conflation | Có thể bỏ qua các trạng thái trung gian không? |
| Cần giữ mọi sự kiện trong burst ngắn | Buffer có giới hạn | Overflow sẽ retry, ghi bền vững, từ chối hay báo lỗi? |

Trước khi chọn, hãy xác định rõ phần tử nào được phép mất, thời gian chờ tối đa, giới hạn bộ nhớ, phạm vi quota và cách phục hồi khi downstream chậm. Những quyết định này thuộc yêu cầu nghiệp vụ và vận hành, không thể suy ra chỉ từ tên toán tử.

## 8. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
|---|---|---|
| `request(100)` nghĩa là 100 phần tử/giây | `request` không mang đơn vị thời gian. | Nó cấp quyền phát thêm tối đa 100 phần tử cho subscription. |
| `limitRate(100)` giới hạn 100 phần tử/giây | `limitRate` điều tiết các lô demand upstream. | Dùng rate limiter khi cần quota theo thời gian. |
| Buffer giải quyết được mọi tình trạng quá tải | Tốc độ đến cao hơn tốc độ xử lý lâu dài sẽ làm buffer đầy. | Đặt giới hạn, đo overflow và có chính sách khi đầy. |
| Giới hạn concurrency đồng nghĩa với rate limit | Tác vụ hoàn tất nhanh có thể được thay thế liên tục. | Concurrency giới hạn công việc đang chạy; rate limit giới hạn lượt bắt đầu theo thời gian. |
| TCP flow control bảo đảm consumer nghiệp vụ không quá tải | TCP chỉ điều tiết truyền byte giữa các endpoint. | Cần điều tiết ở tầng message hoặc pipeline ứng dụng nữa. |
| Drop hoặc latest vẫn giữ đủ dữ liệu | Những chiến lược này chủ động loại bỏ phần tử. | Chỉ dùng khi semantics nghiệp vụ cho phép mất hoặc gộp dữ liệu. |

## 9. Bài tập tình huống

Một ứng dụng nhận số đo nhiệt độ liên tục từ cảm biến. Dashboard chỉ cần hiển thị nhiệt độ mới nhất mỗi 500 mili giây. Cùng lúc đó, một luồng khác ghi sự kiện cảnh báo vượt ngưỡng vào kho lưu trữ; mọi cảnh báo đều phải được giữ lại. Dịch vụ lưu trữ chỉ cho phép tối đa 40 lần ghi mỗi giây.

Hãy xác định chính sách cho từng luồng:

1. Với dashboard, có thể giữ giá trị mới nhất trong lúc UI bận và bỏ các giá trị trung gian, vì mục tiêu là trạng thái hiện tại.
2. Với cảnh báo, không được dùng drop/latest nếu yêu cầu là lưu đủ. Cần buffer có giới hạn hoặc hàng đợi bền vững, kèm xử lý khi đầy và cơ chế retry có kiểm soát.
3. Trước kho lưu trữ, cần rate limiter để tuân thủ 40 lần ghi mỗi giây. Backpressure hoặc giới hạn concurrency vẫn cần để kiểm soát lượng công việc đang chờ và đang chạy.
4. Nếu nguồn cảm biến hỗ trợ lấy mẫu theo yêu cầu, có thể phối hợp demand để giảm dữ liệu đầu vào. Nếu cảm biến phát liên tục, phải áp dụng chính sách cho nguồn nóng.

Điểm cần nhận ra là hai luồng có yêu cầu dữ liệu khác nhau dù cùng xuất phát từ cảm biến. Luồng hiển thị ưu tiên tính mới; luồng cảnh báo ưu tiên tính đầy đủ; kho lưu trữ có thêm quota tốc độ. Một cơ chế duy nhất không thể biểu đạt cả ba yêu cầu đó.

## 10. Checklist trước khi đưa vào production

- Đã xác định rõ cần giới hạn demand, tốc độ theo thời gian, concurrency hay capacity của hàng đợi.
- Đã xác định nguồn là cold/pullable hay hot/push-only và nó có thể tạm dừng hay không.
- Mọi buffer đều có giới hạn và có cách xử lý overflow.
- Drop/latest chỉ được dùng khi nghiệp vụ cho phép mất hoặc gộp dữ liệu.
- Rate limiter có phạm vi quota rõ ràng: mỗi subscription, user, process, instance hay toàn cụm.
- Đã phân biệt giới hạn số tác vụ đang chạy với giới hạn số tác vụ bắt đầu trong một khoảng thời gian.
- Có metric cho demand, độ dài hàng đợi, số phần tử bị bỏ, overflow, độ trễ và số lần bị rate limit.
- Kiểm thử cả burst ngắn lẫn tình trạng tải cao kéo dài; xác minh hệ thống phục hồi khi tải giảm.

Khi phân biệt được ba cơ chế, bạn sẽ thiết kế pipeline `Mono`/`Flux` sát với yêu cầu hơn: backpressure giúp consumer điều tiết nhu cầu, rate limiting thực thi quota theo thời gian, còn flow control phối hợp dung lượng truyền và nhận trên từng tầng của hệ thống. Kết hợp đúng tầng giúp kiểm soát quá tải mà vẫn giữ được semantics dữ liệu của ứng dụng.
