# Can thiệp vào luồng sự kiện và nguy cơ phá vỡ áp lực ngược trong AOP

## 1. Bài toán và mục tiêu

Aspect-Oriented Programming (AOP) cho phép tách những mối quan tâm cắt ngang như đo thời gian, ghi log, tracing, kiểm soát truy cập và thống kê ra khỏi luồng xử lý nghiệp vụ. Với lời gọi đồng bộ, một advice dạng `around` thường chạy trước/sau một phương thức và quan sát được điểm trả về hoặc ngoại lệ ngay tại đó. Với luồng sự kiện bất đồng bộ, **phương thức trả về không đồng nghĩa với công việc đã kết thúc**: kết quả có thể xuất hiện trên một luồng khác, nhiều lần, hoặc không bao giờ được phát ra nếu có hủy.

Rủi ro quan trọng nhất xuất hiện khi aspect vô tình biến một kênh có kiểm soát nhu cầu thành kênh đẩy dữ liệu quá nhanh, gây tràn hàng đợi, tăng độ trễ, cạn bộ nhớ hoặc làm sai hợp đồng của producer và consumer. Sau bài này, người học cần phân biệt thời điểm lời gọi với vòng đời sự kiện, nhận ra các can thiệp phá vỡ backpressure, và thiết kế một advice theo dõi tín hiệu mà vẫn bảo toàn hành vi của luồng.

## 2. Mô hình tín hiệu và ranh giới bất đồng bộ

Một luồng kiểu Reactive Streams, được Java 9+ phản ánh bằng các interface trong `java.util.concurrent.Flow`, có các vai trò sau:

- **Publisher:** nguồn phát dữ liệu; đăng ký một `Subscriber` qua `subscribe`.
- **Subscriber:** bên nhận dữ liệu; được gọi `onSubscribe`, `onNext`, và cuối cùng là `onError` hoặc `onComplete`.
- **Subscription:** kênh điều khiển giữa subscriber và publisher; `request(n)` thông báo nhu cầu, `cancel()` dừng việc nhận.
- **Demand (nhu cầu):** số phần tử subscriber còn cho phép gửi. Lời gọi `request(n)` có thể cộng dồn; `n` phải dương.

Dòng dữ liệu đi xuôi, còn nhu cầu đi ngược:

~~~mermaid
flowchart LR
    P[Publisher] -->|onNext / onError / onComplete| A[Aspect quan sát tín hiệu]
    A -->|chuyển tiếp tín hiệu| S[Subscriber]
    S -->|request n / cancel| A
    A -->|chuyển tiếp demand / cancel| P
~~~

Hợp đồng cần bảo toàn: trong một `Subscription`, số `onNext` đã phát không được vượt quá tổng nhu cầu hợp lệ đã được yêu cầu, sau khi tính phần tử đã gửi; `cancel` phải được chuyển tiếp; tín hiệu kết thúc chỉ xảy ra một lần và không được phát dữ liệu sau khi kết thúc. `request(n)` là **giới hạn cấp phép**, không phải yêu cầu publisher nhất thiết phải phát đủ `n` phần tử.

Một số hệ thống truyền sự kiện kiểu callback, event bus hoặc listener chỉ hỗ trợ `emit` / `onEvent` mà **không có cơ chế demand**. Khi đó không thể tự tuyên bố là đã bảo toàn backpressure; phải xác định riêng chiến lược hàng đợi, từ chối, làm chậm nguồn, gộp hoặc bỏ sự kiện theo hợp đồng nghiệp vụ.

### Advice thực thi ở thời điểm nào?

Giả sử một phương thức trả về `CompletionStage<T>` hoặc `Flow.Publisher<T>`:

1. `before` hoặc `around` tại **lời gọi phương thức** chỉ chứng kiến thao tác tạo/trả về đối tượng bất đồng bộ; nó chưa biết kết quả cuối.
2. Callback trên `CompletionStage` có thể chạy lúc stage hoàn tất, đôi khi ngay trên thread hoàn tất stage; callback nặng sẽ làm chậm chính luồng xử lý đó.
3. Với `Publisher`, việc nhận đối tượng publisher, gọi `subscribe`, nhận `onSubscribe`, từng `onNext` và tín hiệu cuối là các điểm khác nhau. Có publisher chỉ bắt đầu làm việc sau khi đăng ký; có publisher tạo luồng riêng hoặc phát liên tục.
4. Advice có thể chạy trên thread gọi, thread xử lý sự kiện hoặc thread khác do scheduler/executor quyết định. Không được giả định thread-local context tự đi qua ranh giới này.

Vì thế, đo thời gian từ lúc gọi đến lúc trả về chỉ đo **chi phí tạo tác vụ**. Muốn đo toàn bộ luồng, phải nói rõ đo từ lúc `subscribe` đến tín hiệu cuối, từ lúc `request` đến lúc giao `onNext`, hay từ khi một sự kiện được tạo đến khi xử lý xong.

## 3. Backpressure là gì và vì sao aspect có thể phá vỡ nó?

Đối với một subscriber, có thể hình dung:

`demand_còn_lại = tổng_request_hợp_lệ − số_onNext_đã_giao`

Đây là mô hình tư duy cho một subscription, không phải biến toàn cục dùng chung. Với bộ đệm, phải phân biệt số phần tử đang nằm trong queue với nhu cầu đã được cấp để **giao cho downstream**; buffered event không tự trở thành demand mới.

Một advice dù không sửa dữ liệu vẫn có thể làm sai luồng:

| Can thiệp | Nguy cơ | Cách phù hợp |
| --- | --- | --- |
| Advice chủ động gọi `request(Long.MAX_VALUE)` để “nhìn hết” dữ liệu | Biến nhu cầu hữu hạn thành gần như không giới hạn; upstream có thể tạo quá nhanh | Chỉ chuyển tiếp `request(n)` do downstream đưa ra |
| Advice tự `subscribe` thêm một lần để log | Có thể khởi động tác vụ nguồn lần hai, tạo side effect, tốn tài nguyên, hoặc nhận một bản sao khác | Quan sát subscription thật qua decorator; không tạo subscriber phụ |
| `onNext` ghi log mạng hoặc lưu DB đồng bộ | Chặn thread phát tín hiệu, kéo dài độ trễ, tạo nghẽn trên event loop | Ghi số đếm/timestamp nhẹ; xuất telemetry sang hàng đợi có giới hạn |
| Đưa mọi sự kiện vào queue không giới hạn trong advice | Bộ nhớ tăng dù downstream đang chậm; che khuất backpressure thật | Tránh queue khi không cần; nếu cần, giới hạn sức chứa và xác định chiến lược khi đầy |
| Gọi `request(n + k)` hoặc gọi thêm `request` vì mục đích metrics | Upstream nhận demand lớn hơn mức consumer cho phép | Giữ nguyên giá trị và số lần gọi của downstream |
| Chặn/bỏ một số `onNext` nhưng không điều chỉnh phép đếm demand | Mất cân bằng giữa upstream và downstream, có thể làm upstream chạy mãi để lấp nhu cầu hoặc downstream thiếu dữ liệu | Nếu lọc/biến đổi có trạng thái, dùng toán tử backpressure-aware và chứng minh quy tắc bù demand |
| `onNext` tự gọi lại downstream cùng lúc từ nhiều thread | Phá vỡ tính tuần tự của tín hiệu; race trong subscriber | Giữ callback theo thứ tự, tránh phát thêm tín hiệu ngoài giao thức |
| Nuốt `onError`, quên `cancel` hoặc phát `onComplete` sớm | Hỏng semantics terminal, rò rỉ subscription/tài nguyên | Chuyển tiếp đúng một terminal và hủy khi được yêu cầu |

Ví dụ: consumer xử lý được 100 sự kiện/giây nhưng producer tạo 10.000 sự kiện/giây. Nếu advice tạo hàng đợi vô hạn, số tồn có thể tăng gần 9.900 sự kiện mỗi giây. Sau 60 giây sẽ là khoảng 594.000 sự kiện chưa xử lý (giả sử tốc độ ổn định và chưa có cơ chế điều tiết). Đây là ví dụ về **tích lũy tồn kho**, không phải số liệu benchmark. Giới hạn demand và kích thước buffer giúp hệ thống phản ứng có kiểm soát thay vì giữ tất cả sự kiện.

## 4. Thiết kế aspect an toàn tại ranh giới sự kiện

### 4.1 Quan sát mà không chiếm quyền điều khiển

Khi cần ghi log/tracing ở mức tín hiệu, có thể bọc `Subscriber` và `Subscription`:

- `onSubscribe(original)`: đưa xuống downstream một `Subscription` ủy quyền. `request(n)` phải chuyển **đúng `n`, đúng một lần**, theo thứ tự hợp lệ tới `original.request(n)`. `cancel()` phải chuyển tiếp `original.cancel()`.
- `onNext(item)`: ghi nhận một phép đo ngắn, rồi chuyển **chính item đó** xuống downstream một lần; không bí mật đệm, sao chép thành nhiều lần gửi, tạo subscriber thứ hai hoặc yêu cầu thêm dữ liệu.
- `onError(error)` và `onComplete()`: ghi trạng thái rồi chuyển nguyên tín hiệu tới downstream; không tự thay đổi loại lỗi hay phát tín hiệu tiếp theo.
- Telemetry phải hạn chế ném lỗi. Nếu công cụ metrics/logging thất bại, cơ chế quan sát không nên tự biến thành lỗi của stream; ranh giới bắt lỗi cần được thiết kế rõ ràng.
- Bảo toàn sự tuần tự của callbacks theo giao thức. Không tự đẩy `onNext` lên một executor khác nếu chưa có cơ chế tuần tự hóa, quản lý queue và demand.

Điều này tương ứng với một **decorator/interceptor tại biên subscription**, có thể được cài bằng proxy, weaving bytecode hoặc bọc đối tượng một cách tường minh. Một pointcut ở phương thức tạo publisher thường chưa đủ để thấy từng sự kiện: muốn đo luồng thì advice phải bọc hành vi đăng ký hoặc callback, chứ không chỉ đo thời gian thực thi phương thức.

### 4.2 Ví dụ Java 17+ chạy độc lập: trace tín hiệu mà vẫn tôn trọng request(1)

Mã sau dùng `Flow` và `SubmissionPublisher` của JDK, không phụ thuộc thư viện ngoài. Subscriber chỉ yêu cầu **một phần tử tại một thời điểm**. Lớp `TracingSubscriber` đóng vai trò thành phần quan sát AOP: mọi `request` và `cancel` đều được ủy quyền, không tạo thêm nhu cầu. Ví dụ sử dụng nguồn chỉ có ba phần tử để minh họa hợp đồng tín hiệu; `SubmissionPublisher` **có bộ đệm riêng**, vì vậy `request(1)` giới hạn giao tới subscriber nhưng không đồng nghĩa cấm producer nộp trước nhiều phần tử vào buffer.

Tệp: `BackpressureAspectDemo.java`

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class BackpressureAspectDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch done = new CountDownLatch(1);

        try (SubmissionPublisher<Integer> publisher = new SubmissionPublisher<>()) {
            publisher.subscribe(
                new TracingSubscriber<>(new OneByOneSubscriber(done))
            );

            for (int value = 1; value <= 3; value++) {
                publisher.submit(value);
            }
        }

        if (!done.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Subscriber did not finish");
        }
    }

    static final class TracingSubscriber<T> implements Flow.Subscriber<T> {
        private final Flow.Subscriber<? super T> downstream;

        TracingSubscriber(Flow.Subscriber<? super T> downstream) {
            this.downstream = downstream;
        }

        @Override
        public void onSubscribe(Flow.Subscription upstream) {
            downstream.onSubscribe(new Flow.Subscription() {
                @Override
                public void request(long n) {
                    System.out.println("trace request(" + n + ")");
                    upstream.request(n);
                }

                @Override
                public void cancel() {
                    System.out.println("trace cancel");
                    upstream.cancel();
                }
            });
        }

        @Override
        public void onNext(T item) {
            System.out.println("trace onNext(" + item + ")");
            downstream.onNext(item);
        }

        @Override
        public void onError(Throwable error) {
            System.out.println("trace error: " + error);
            downstream.onError(error);
        }

        @Override
        public void onComplete() {
            System.out.println("trace complete");
            downstream.onComplete();
        }
    }

    static final class OneByOneSubscriber implements Flow.Subscriber<Integer> {
        private final CountDownLatch done;
        private Flow.Subscription subscription;

        OneByOneSubscriber(CountDownLatch done) {
            this.done = done;
        }

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            subscription.request(1);
        }

        @Override
        public void onNext(Integer value) {
            System.out.println("consume " + value);
            subscription.request(1);
        }

        @Override
        public void onError(Throwable error) {
            System.err.println("failed: " + error);
            done.countDown();
        }

        @Override
        public void onComplete() {
            done.countDown();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BackpressureAspectDemo.java
java BackpressureAspectDemo
~~~

Với luồng hoàn tất bình thường, stdout là:

~~~text
trace request(1)
trace onNext(1)
consume 1
trace request(1)
trace onNext(2)
consume 2
trace request(1)
trace onNext(3)
consume 3
trace request(1)
trace complete
~~~

Ở đây người tiêu thụ tự gọi `request(1)` sau mỗi lần xử lý, kể cả sau phần tử cuối vì nó chưa biết publisher sẽ hoàn tất. Trace thấy đúng những lời gọi ấy; không có `request(Long.MAX_VALUE)` do aspect thêm vào. Các tín hiệu của cùng subscription được xử lý tuần tự, nhưng không được suy ra mọi publisher đều dùng chung một thread hoặc có bộ đệm giống `SubmissionPublisher`.

**Giới hạn của mẫu:** Đây là decorator để giải thích nơi đặt advice; chưa phải một runtime weaving hoàn chỉnh. Trong hệ thống thực, phần instrumentation còn cần chính sách xử lý lỗi telemetry, phân bổ tài nguyên và đo tải. Nếu mục đích là đo chính xác tốc độ tạo sự kiện hay kích thước hàng đợi, phải đo thêm ở phía nguồn/buffer; trace `onNext` downstream một mình không cung cấp hai số đó.

### 4.3 Advice trên CompletionStage khác với advice trên Publisher

`CompletionStage<T>` có một kết quả hoàn tất (thành công hoặc thất bại), không có chuỗi `request(n)`/`onNext`. Advice ghi nhận việc trả stage sẽ không thấy thời điểm stage hoàn tất. Có thể gắn callback `whenComplete` để đo terminal, nhưng cần chú ý:

- Callback có thể chạy trên thread hoàn tất stage, hoặc ngay khi đăng ký nếu stage đã xong; tránh I/O chặn hoặc xử lý nặng.
- Telemetry phải tự bắt lỗi và không thay thế kết quả/ngoại lệ của nghiệp vụ. Nếu cần trả về stage cho caller, phải xác định rõ có trả nguyên stage hay stage phụ thuộc mới.
- Hủy `CompletableFuture` không tự bảo đảm hủy mọi tác vụ hoặc I/O gốc; không giả định có backpressure như `Flow.Subscription`.

Khi kết nối stage với stream, cần một toán tử hoặc bridge có hợp đồng cụ thể về cancellation, demand và error. Không thể áp dụng quy tắc của hai cơ chế như thể chúng giống nhau.

## 5. Các can thiệp nâng cao và bất biến cần giữ

### Đưa telemetry sang worker khác

Nếu aspect gửi dữ liệu đo đạc vào queue riêng, queue cũng là một tài nguyên hữu hạn. Cần đặt `capacity`, giới hạn thời gian chờ và chính sách khi đầy: bỏ **bản ghi telemetry** có đếm số bản ghi bị bỏ, lấy mẫu, hoặc chuyển sang bộ đếm tổng hợp. Không được âm thầm bỏ **sự kiện nghiệp vụ** chỉ vì kênh metrics quá tải. Nếu yêu cầu bảo đảm mọi log phải lưu được, chi phí lưu log phải được đưa vào thiết kế throughput và backpressure một cách công khai.

### Thay đổi thứ tự, lập lịch và tốc độ

Một advice tự đổi thread hoặc xếp sự kiện vào executor có thể thay đổi thứ tự, tạo callback chồng lấn, trì hoãn cancellation và làm tăng số event đang bay (`in-flight`). Nếu bắt buộc chèn ranh giới bất đồng bộ, phải thiết kế bộ điều phối có giới hạn, truyền demand ngược, ngừng nhận khi hủy, xử lý lỗi executor và bảo toàn thứ tự theo cam kết của API. Đây là **biến đổi giao thức**, cần kiểm thử như một thành phần xử lý stream thực thụ.

### Filter, retry, fan-out, batching

- **Filter:** bỏ một phần tử vẫn có thể đã tiêu thụ một slot nhu cầu upstream. Muốn đáp ứng nhu cầu downstream đúng nghĩa, toán tử có thể phải yêu cầu bù theo cách an toàn; advice ghi log không nên tự cài logic này.
- **Retry:** đăng ký lại hoặc chạy lại nguồn có thể tạo side effect lần hai. Không retry trong advice nếu chưa xác định tính idempotent, giới hạn số lần, xử lý hủy và demand.
- **Fan-out:** nhiều consumer có tốc độ khác nhau cần chính sách chia sẻ, hàng đợi và xử lý consumer chậm; không thể sao chép một `Subscription` đơn lẻ cho mọi consumer rồi cộng demand tùy tiện.
- **Batching:** gộp `k` phần tử thành một batch làm thay đổi đơn vị demand; phải công bố hợp đồng mới và tính toán lại chuyển đổi nhu cầu giữa hai phía.

### Context, security và lifecycle

Trace ID hoặc thông tin phân quyền thường nằm trong context của lời gọi ban đầu. Qua ranh giới async, `ThreadLocal` có thể mất hoặc lẫn giữa các tác vụ dùng chung thread. Dùng cơ chế truyền context tường minh hoặc scope được quản lý đúng cách; luôn đóng/khôi phục scope tại đúng callback để tránh rò rỉ. Không nên giả định advice đặt trên một phương thức sẽ tự chạy lại trên mọi callback nội bộ.

Đối với lỗi và hủy, ghi nhận riêng ít nhất: `completed`, `failed`, `cancelled`. Nguồn có thể kết thúc sớm khi thiếu dữ liệu, một callback có thể đến gần thời điểm cancellation do cuộc đua đã diễn ra, và không phải mọi callback sau lệnh hủy đều có thể thu hồi tức thời. Đo đạc nên tôn trọng trạng thái thực tế và không giả lập terminal thứ hai.

## 6. Cách áp dụng: quy trình thiết kế một aspect trên event stream

1. **Xác định điểm nối:** advice gắn vào lời gọi tạo publisher, `subscribe`, `Subscription`, từng callback, hay một toán tử xử lý? Vẽ rõ producer, consumer và bất kỳ queue nào.
2. **Ghi hợp đồng tín hiệu:** có `request(n)` hay không, ai nắm quyền `cancel`, có buffer hay không, quy tắc thứ tự và terminal, một hay nhiều subscriber, nóng (`hot`) hay chỉ phát khi đăng ký (`cold`).
3. **Định nghĩa điều gì được quan sát:** số đăng ký, nhu cầu, phần tử đã giao, thời gian xử lý callback, lỗi, hủy hoặc độ sâu queue. Đừng suy diễn số phần tử được sản xuất từ số callback đã thấy.
4. **Giữ một đường điều khiển duy nhất:** truyền `request(n)`/`cancel` nguyên vẹn; không tự `subscribe` để thăm dò hay tăng nhu cầu chỉ để ghi log.
5. **Giữ advice nhẹ và có giới hạn:** thu thập phép đo ngắn, xử lý ngoại lệ telemetry, có chính sách tràn tải cho mọi buffer phụ.
6. **Kiểm thử cả giao thức lẫn áp lực:** nguồn nhanh, consumer chậm, hủy giữa chừng, request không hợp lệ, lỗi ở cả hai phía, hoàn tất ngay, đua giữa các thread và việc đăng ký lại.

### Checklist kiểm thử thực tế

| Tình huống | Kết quả cần quan sát |
| --- | --- |
| Chưa gọi `request` | Không có `onNext` được giao đối với publisher tuân theo demand |
| `request(1)`, nguồn còn dữ liệu | Tối đa một `onNext` trước khi có demand mới |
| `request(2)` rồi `request(3)` | Tổng cấp phép là năm phần tử, không bị nhân đôi do advice |
| Gọi `cancel` | Lệnh hủy tới đúng upstream; không có yêu cầu thêm ngoài ý muốn |
| Nguồn phát `onError` | Downstream nhận đúng tín hiệu lỗi terminal một lần |
| Nguồn phát `onComplete` | Downstream nhận hoàn tất một lần, không thêm `onNext` |
| Log/metrics chậm hoặc hỏng | Có chính sách giới hạn, đường nghiệp vụ giữ hợp đồng đã chọn |
| Subscriber chậm hơn nguồn trong nhiều phút | Buffer và bộ nhớ không tăng vô hạn vì instrumentation |
| Subscribe nhiều lần | Số lần thực thi nguồn phù hợp semantics nguồn; aspect không tự đăng ký thêm |
| Phát hiện race / đổi scheduler | Không phát callback đồng thời trái hợp đồng hoặc tráo thứ tự bất ngờ |

Trong kiểm thử tự động, subscriber điều khiển thủ công demand có ích hơn chỉ đo thời gian chạy. Đối với hệ thống tải cao, hãy theo dõi tốc độ producer/consumer, độ sâu và mức sử dụng buffer, thời gian từ `request` tới `onNext`, độ trễ xử lý, số `cancel` và số telemetry bị bỏ; kết hợp các thước đo mới phân biệt được nút nghẽn ở nguồn, consumer hay chính advice.

## 7. Những nhầm lẫn phổ biến cần tránh

**“Dùng async nghĩa là tự có backpressure.”** Sai: nhiều API bất đồng bộ chỉ trả kết quả về sau; không cung cấp demand. Ngay cả khi downstream yêu cầu từng phần tử, một publisher có buffer vẫn có thể nhận trước nhiều phần tử từ producer.

**“Advice chỉ ghi log thì không ảnh hưởng nghiệp vụ.”** Sai: log đồng bộ có thể chặn thread, bản ghi không giới hạn có thể chiếm bộ nhớ, và một exception phát sinh trong instrumentation có thể thay đổi đường lỗi. Tính xuyên suốt của advice phụ thuộc cả tài nguyên lẫn semantics.

**“Đo thời gian trả về từ phương thức là đo thời gian xử lý stream.”** Sai: lời gọi có thể trả đối tượng publisher rất nhanh trước khi có subscriber. Phải ghi rõ thời điểm bắt đầu/kết thúc phép đo.

**“Cứ gọi request(Long.MAX_VALUE) để không bỏ lỡ sự kiện.”** Sai: thao tác đó xóa bỏ giới hạn demand của consumer và có thể làm producer vượt khả năng xử lý phía sau.

**“Bọc subscriber là luôn an toàn.”** Chỉ an toàn khi wrapper chuyển tiếp đúng các tín hiệu, nhu cầu, hủy, lỗi, thứ tự và ranh giới tài nguyên. Khi wrapper lọc, cache, retry, fan-out hoặc chuyển thread, nó đã trở thành một thành phần xử lý stream cần hợp đồng và kiểm thử riêng.

## 8. Kết luận

Trong AOP, ranh giới bất đồng bộ làm tách biệt **thời điểm gọi phương thức** và **vòng đời phát tín hiệu**. Với stream có backpressure, aspect quan sát cần đứng cạnh giao thức: theo dõi `subscribe`/`onNext`/terminal, ủy quyền `request(n)` và `cancel()` nguyên vẹn, không sinh demand hay queue vô hạn. Mọi biến đổi event, scheduler, buffering hoặc retry phải được thiết kế như một toán tử có kiểm soát nhu cầu. Như vậy mối quan tâm cắt ngang vẫn quan sát được hệ thống mà không phá vỡ khả năng tự điều tiết của luồng.