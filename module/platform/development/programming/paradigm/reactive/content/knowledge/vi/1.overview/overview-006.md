# Tổng quan

## Mối liên hệ với lập trình hàm, hướng đối tượng và hướng sự kiện

Lập trình phản ứng (reactive programming) thường được dùng cùng lập trình hàm, lập trình hướng đối tượng và lập trình hướng sự kiện. Những cách tiếp cận này giải quyết các khía cạnh khác nhau của một chương trình. Hướng đối tượng giúp tổ chức trách nhiệm và trạng thái; lập trình hàm giúp mô tả phép biến đổi dữ liệu; hướng sự kiện xác định cách chương trình phản ứng khi một sự việc xảy ra; còn reactive tập trung vào việc biểu diễn và truyền các giá trị thay đổi theo thời gian, thường qua những luồng bất đồng bộ có cơ chế điều tiết nhu cầu.

Trong module **REACTIVE_PROGRAMMING**, ta dùng các khái niệm đó để hiểu Publisher–Subscriber, backpressure và cách xây dựng pipeline bằng **Mono** và **Flux** trong Project Reactor. Reactive không yêu cầu loại bỏ các phong cách lập trình quen thuộc. Một ứng dụng Java có thể dùng lớp và interface để đóng gói nghiệp vụ, dùng hàm thuần để biến đổi dữ liệu, nhận sự kiện từ hệ thống bên ngoài và kết hợp tất cả bằng một pipeline reactive.

### 1. Bốn góc nhìn bổ trợ cho nhau

| Cách tiếp cận | Câu hỏi chính | Trọng tâm |
| --- | --- | --- |
| Hướng đối tượng (OOP) | Trách nhiệm và trạng thái thuộc về đối tượng nào? | Đóng gói dữ liệu, hành vi và cộng tác giữa các đối tượng |
| Lập trình hàm (FP) | Biến đầu vào thành kết quả như thế nào? | Hàm, tính bất biến, kết hợp phép biến đổi và kiểm soát tác dụng phụ |
| Hướng sự kiện (event-driven) | Điều gì kích hoạt công việc? | Sự kiện, bộ phát, bộ xử lý và phản ứng khi sự kiện đến |
| Lập trình phản ứng (reactive) | Dữ liệu thay đổi theo thời gian được truyền và tiêu thụ ra sao? | Luồng dữ liệu, tín hiệu bất đồng bộ, subscription, demand và backpressure |

Các cách tiếp cận này có thể xuất hiện trong cùng một đoạn mã. Ví dụ, một dịch vụ hướng đối tượng giữ tham chiếu đến nguồn sự kiện; nguồn phát các sự kiện thanh toán; pipeline reactive lọc những khoản thanh toán cần xử lý; các hàm theo phong cách functional chuyển sự kiện thành dữ liệu hóa đơn; cuối cùng một cổng tích hợp gửi hóa đơn đến hệ thống khác.

### 2. Reactive và lập trình hàm

Lập trình hàm xem phép tính như việc áp dụng hàm lên đầu vào để tạo đầu ra. Hàm thuần (pure function) luôn cho cùng kết quả với cùng đầu vào và không tạo tác dụng phụ quan sát được. Dữ liệu bất biến (immutable data) giúp một bước xử lý không âm thầm thay đổi đối tượng mà bước khác đang sử dụng.

Đây là cách tư duy phù hợp với pipeline reactive. Ta có thể mô tả từng bước bằng các phép biến đổi:

- **map** chuyển mỗi phần tử thành một giá trị khác.
- **filter** chỉ giữ phần tử thỏa điều kiện.
- **flatMap** chuyển mỗi phần tử thành một publisher rồi hợp nhất kết quả bất đồng bộ.
- **reduce** tổng hợp các phần tử thành một kết quả.

Ví dụ, việc chuyển một sự kiện thanh toán thành dữ liệu hóa đơn có thể được viết thành hàm thuần:

~~~java
import java.math.BigDecimal;

record PaymentReceived(String orderId, BigDecimal amount) {}

record InvoiceDraft(String orderId, BigDecimal total) {}

final class InvoiceMapping {
    static InvoiceDraft toInvoiceDraft(PaymentReceived payment) {
        return new InvoiceDraft(payment.orderId(), payment.amount());
    }
}
~~~

Hàm **toInvoiceDraft** không truy cập cơ sở dữ liệu, không gửi email và không sửa sự kiện đầu vào. Vì vậy, ta có thể kiểm thử nó độc lập và dùng nó trong nhiều pipeline.

Với Reactor, các phép biến đổi có thể được kết hợp trên một luồng:

Giả sử **paymentEventSource** đã được inject và cung cấp **Flux<PaymentReceived>**:

~~~java
import java.math.BigDecimal;

import reactor.core.publisher.Flux;

Flux<PaymentReceived> paymentEvents = paymentEventSource.paymentEvents();

Flux<InvoiceDraft> drafts =
    paymentEvents
        .filter(payment ->
            payment.amount().compareTo(new BigDecimal("100.00")) >= 0
        )
        .map(InvoiceMapping::toInvoiceDraft);
~~~

Pipeline trên giữ các sự kiện có số tiền từ 100 trở lên rồi chuyển chúng thành bản nháp hóa đơn. **filter** và **map** mô tả quan hệ đầu vào/đầu ra của từng bước; Reactor điều phối tín hiệu đi qua pipeline khi có phần tử được phát.

Không phải mọi toán tử đều là hàm thuần. Một callback có thể ghi log, cập nhật cơ sở dữ liệu hoặc gọi dịch vụ ngoài. Tác dụng phụ cần được đặt ở vị trí có chủ đích, thường tại ranh giới tích hợp hoặc trong toán tử kết hợp với publisher của thao tác I/O. Giữ phần biến đổi dữ liệu càng thuần càng giúp pipeline dễ đọc, kiểm thử và dự đoán.

### 3. Reactive và lập trình hướng đối tượng

Hướng đối tượng tổ chức chương trình thành các đối tượng có trách nhiệm rõ ràng. Một đối tượng có thể đóng gói trạng thái, cung cấp hành vi và cộng tác với những đối tượng khác thông qua interface. Cách tổ chức này vẫn hữu ích trong ứng dụng reactive: nguồn sự kiện, dịch vụ nghiệp vụ và cổng truy cập dữ liệu có thể là các thành phần độc lập.

Điểm cần chú ý là một trường Java thông thường không tự trở thành luồng reactive. Nếu chương trình gán một giá trị mới vào **order.status**, các subscriber không tự động nhận được thông báo. Muốn quan sát thay đổi, đối tượng cần phát sự kiện qua một publisher hoặc sử dụng một cơ chế trạng thái có khả năng thông báo thay đổi.

Ví dụ, interface có thể biểu diễn một nguồn sự kiện thanh toán:

~~~java
import reactor.core.publisher.Flux;

interface PaymentEventSource {
    Flux<PaymentReceived> paymentEvents();
}
~~~

Dịch vụ nghiệp vụ sử dụng interface đó để cung cấp một luồng bản nháp hóa đơn:

~~~java
import java.math.BigDecimal;

import reactor.core.publisher.Flux;

final class InvoiceService {
    private final PaymentEventSource eventSource;

    InvoiceService(PaymentEventSource eventSource) {
        this.eventSource = eventSource;
    }

    Flux<InvoiceDraft> invoiceDrafts() {
        return eventSource.paymentEvents()
            .filter(payment ->
                payment.amount().compareTo(new BigDecimal("100.00")) >= 0
            )
            .map(InvoiceMapping::toInvoiceDraft);
    }
}
~~~

Trong ví dụ, **InvoiceService** đóng gói quy tắc nghiệp vụ và phụ thuộc vào một interface. Cách tổ chức này giúp thay nguồn sự kiện mà không phải viết lại phép lọc và chuyển đổi. Các đối tượng **PaymentReceived** và **InvoiceDraft** có thể là record bất biến, còn pipeline mô tả cách dữ liệu đi qua dịch vụ.

Vì thế, OOP và reactive bổ trợ nhau: OOP tổ chức cấu trúc và quyền sở hữu trách nhiệm; reactive mô tả cách các giá trị được phát và truyền giữa các thành phần theo thời gian. Cần tránh giấu quá nhiều trạng thái có thể thay đổi bên trong callback, vì điều đó làm khó xác định thời điểm và nơi dữ liệu được cập nhật.

### 4. Reactive và lập trình hướng sự kiện

Trong lập trình hướng sự kiện, chương trình thực hiện công việc để phản ứng với một sự kiện. Ví dụ, khi nhận được sự kiện **PaymentReceived**, hệ thống có thể xác nhận đơn hàng, tạo hóa đơn hoặc gửi thông báo. Bộ phát sự kiện và bộ xử lý thường được tách rời, giúp thành phần phát không cần biết chi tiết mọi nơi nhận sự kiện.

Reactive Streams dùng mô hình Publisher–Subscriber để truyền chuỗi tín hiệu bất đồng bộ. Giao thức này bổ sung những quy tắc quan trọng cho việc tiêu thụ luồng:

1. Subscriber đăng ký với Publisher.
2. Publisher gửi Subscription cho Subscriber.
3. Subscriber yêu cầu số phần tử muốn nhận bằng **request(n)**.
4. Publisher gửi phần tử qua **onNext** theo nhu cầu đã yêu cầu.
5. Luồng kết thúc bằng **onComplete** hoặc **onError**; Subscriber cũng có thể hủy đăng ký bằng **cancel**.

Một hệ thống hướng sự kiện dùng callback đơn giản có thể gọi handler mỗi khi sự kiện đến, nhưng callback đó thường không có giao thức demand chuẩn để bên nhận kiểm soát lượng dữ liệu. Reactive Streams đưa ra hợp đồng truyền tín hiệu và backpressure, nhờ vậy subscriber có thể điều tiết tốc độ tiêu thụ khi publisher hỗ trợ giao thức.

Không phải mọi sự kiện đều cần được lưu hoặc phát lại, và không phải mọi publisher đều có cùng vòng đời. Nguồn lạnh (cold publisher) thường bắt đầu tạo dữ liệu theo từng subscription; nguồn nóng (hot publisher) có thể phát độc lập với subscriber và một subscriber đăng ký muộn có thể bỏ lỡ sự kiện đã phát. Khi tích hợp message broker, WebSocket hoặc luồng sự kiện dùng chung, cần xác định rõ chính sách lưu giữ, phát lại, chia sẻ và xác nhận xử lý của nguồn đó.

### 5. Kết hợp cả bốn cách tiếp cận trong một luồng nghiệp vụ

Giả sử hệ thống nhận sự kiện thanh toán và gửi bản nháp hóa đơn đến một dịch vụ khác. Ta có thể chia trách nhiệm như sau:

- Nguồn sự kiện phát các đối tượng **PaymentReceived**.
- Dịch vụ hướng đối tượng giữ các phụ thuộc và quy tắc lọc thanh toán.
- Các hàm theo phong cách functional chuyển sự kiện thành **InvoiceDraft**.
- Pipeline reactive truyền các kết quả theo thời gian và kết hợp publisher của thao tác gửi hóa đơn.
- Bộ tích hợp thực hiện tác dụng phụ gửi dữ liệu ra hệ thống bên ngoài.

Một interface cho bộ tích hợp có thể trả về **Mono<Void>** để biểu diễn thao tác gửi bất đồng bộ:

~~~java
import reactor.core.publisher.Mono;

interface InvoiceGateway {
    Mono<Void> send(InvoiceDraft draft);
}
~~~

Ở composition root, giả sử **invoiceService**, **invoiceGateway** và **logger** đã được khởi tạo bằng cơ chế dependency injection của ứng dụng. Phần điều phối có thể kết hợp luồng bản nháp với thao tác gửi:

~~~java
import reactor.core.Disposable;

Disposable subscription =
    invoiceService.invoiceDrafts()
        .concatMap(invoiceGateway::send)
        .subscribe(
            ignored -> {},
            error -> logger.error("Không thể xử lý luồng hóa đơn", error)
        );
~~~

**concatMap** đăng ký xử lý từng bản nháp theo thứ tự, chờ publisher gửi hóa đơn hiện tại hoàn tất trước khi xử lý bản tiếp theo. Vì **Mono<Void>** không phát giá trị dữ liệu, callback nhận phần tử ở ví dụ này không được gọi; callback lỗi vẫn nhận lỗi từ pipeline. Với nguồn chạy liên tục, ứng dụng cần quản lý **Disposable** theo vòng đời của thành phần để có thể hủy đăng ký khi dừng dịch vụ.

Ví dụ này cho thấy bốn cách tiếp cận cùng tham gia một quy trình. Sự kiện xác định thời điểm bắt đầu công việc; đối tượng giữ trách nhiệm nghiệp vụ và phụ thuộc; phép biến đổi hàm tạo dữ liệu mới; publisher và các toán tử reactive điều phối việc xử lý bất đồng bộ.

### 6. Những điểm cần phân biệt khi thiết kế

Các khái niệm có thể kết hợp, nhưng không nên đồng nhất chúng:

| Khái niệm | Điều nó không tự bảo đảm |
| --- | --- |
| Lập trình hàm | Không tự cung cấp cơ chế truyền dữ liệu bất đồng bộ hoặc quản lý subscription |
| Hướng đối tượng | Không tự phát tín hiệu khi trường trạng thái thay đổi |
| Hướng sự kiện | Không nhất thiết có backpressure, demand hoặc giao thức hủy đăng ký thống nhất |
| Reactive | Không tự làm mọi thao tác trở thành non-blocking, không tự bảo đảm chạy song song và không tự biến mọi nguồn thành event stream |

Reactive cũng không đồng nghĩa với bất đồng bộ trong mọi trường hợp. Một publisher có thể phát tín hiệu đồng bộ trên luồng gọi hiện tại. Trong Reactor, scheduler và các toán tử như **subscribeOn** hoặc **publishOn** quyết định nơi một phần pipeline được thực thi. Nếu gọi API blocking trong một hàm **map**, pipeline vẫn có thể bị chặn; cần cô lập thao tác đó hoặc dùng API bất đồng bộ phù hợp.

Backpressure chỉ có tác dụng khi nguồn và các thành phần trung gian tuân theo giao thức hoặc có cơ chế thích nghi phù hợp. Nếu một nguồn bên ngoài không thể giảm tốc độ phát, hệ thống phải xác định chính sách buffer, drop, giữ giá trị mới nhất hoặc báo lỗi theo yêu cầu nghiệp vụ. Với sự kiện tài chính hay thay đổi trạng thái đơn hàng, việc bỏ sự kiện có thể làm sai dữ liệu; với dữ liệu đo liên tục, chỉ giữ mẫu mới nhất đôi khi là lựa chọn hợp lý.

### 7. Cách lựa chọn và phối hợp trong ứng dụng Java

Khi thiết kế một luồng xử lý, hãy bắt đầu từ trách nhiệm và yêu cầu của nghiệp vụ:

- Dùng interface và lớp để đóng gói nguồn dữ liệu, quy tắc nghiệp vụ và cổng tích hợp.
- Dùng record hoặc đối tượng bất biến để truyền dữ liệu rõ ràng giữa các bước.
- Viết phép lọc và biến đổi dưới dạng hàm thuần khi có thể.
- Biểu diễn các thay đổi theo thời gian bằng Publisher, rồi kết hợp chúng bằng toán tử phù hợp.
- Xác định demand, chính sách backpressure, cách xử lý lỗi và vòng đời subscription.
- Đặt thao tác có tác dụng phụ ở ranh giới tích hợp, nơi có thể kiểm soát retry, timeout và tính idempotent.

Khi kiểm thử, có thể kiểm tra hàm thuần bằng unit test thông thường; kiểm tra quy tắc của đối tượng bằng cách gọi hành vi của nó; và dùng **StepVerifier** để xác minh thứ tự phần tử, lỗi và tín hiệu hoàn tất của publisher. Việc tách trách nhiệm như vậy giúp mỗi phần có cách kiểm thử phù hợp với vai trò của nó.

Trong các hệ thống Java thực tế, một dịch vụ reactive thường không phải là một phong cách lập trình biệt lập. Nó kết hợp mô hình đối tượng để tổ chức ứng dụng, tư duy hàm để xử lý dữ liệu, mô hình sự kiện để phản ứng với thay đổi và Reactive Streams để truyền dữ liệu bất đồng bộ có kiểm soát. Hiểu mối liên hệ này giúp lựa chọn đúng công cụ cho từng phần và tạo ra pipeline dễ đọc, dễ kiểm thử, dễ vận hành.
