# Ghép luồng

## flatMap: phối hợp các luồng con và cho phép xen kẽ kết quả

Trong một pipeline reactive, mỗi phần tử của luồng nguồn có thể cần kích hoạt một thao tác bất đồng bộ và tạo ra một luồng kết quả riêng. Ví dụ, một danh sách mã đơn hàng cần được dùng để gọi nhiều dịch vụ tra cứu; mỗi đơn hàng có thể trả về một hoặc nhiều bản ghi chi tiết, và các yêu cầu hoàn tất ở những thời điểm khác nhau.

Project Reactor cung cấp toán tử **flatMap** để biến mỗi phần tử nguồn thành một Publisher con rồi hợp nhất các tín hiệu từ những Publisher con đó vào một luồng đầu ra. Các luồng con có thể được đăng ký đồng thời và kết quả được phát khi chúng sẵn sàng. Vì vậy, thứ tự đầu ra có thể khác thứ tự phần tử nguồn, và các phần tử từ nhiều luồng con có thể xen kẽ nhau.

### 1. Từ map đến flatMap

**map** áp dụng một hàm đồng bộ lên từng phần tử và tạo đúng một giá trị đầu ra cho mỗi lần gọi hàm. Nếu hàm trả về một Publisher, kết quả của **map** sẽ là Publisher nằm bên trong Publisher:

~~~java
Flux<Mono<Order>> nested =
    orderIds.map(id -> orderClient.findOrder(id));
~~~

Kiểu dữ liệu là **Flux<Mono<Order>>**: luồng ngoài phát các đối tượng Mono, nhưng chưa tự hợp nhất kết quả bên trong từng Mono. Muốn nhận trực tiếp các đối tượng Order, ta cần một toán tử biết cách đăng ký các Publisher con và ghép tín hiệu của chúng.

**flatMap** thực hiện cả hai việc: ánh xạ mỗi phần tử thành một Publisher con, sau đó hợp nhất các phần tử mà Publisher con phát ra:

~~~java
Flux<Order> orders =
    orderIds.flatMap(id -> orderClient.findOrder(id));
~~~

Kiểu kết quả trở thành **Flux<Order>**. Nếu một Publisher con hoàn tất rỗng, nó không đóng góp phần tử nào. Nếu một Publisher con phát nhiều phần tử, tất cả các phần tử đó đều có thể xuất hiện trong luồng kết quả.

Có thể hình dung:

~~~text
Nguồn:       id-1       id-2       id-3
               |          |          |
               v          v          v
Luồng con:  Publisher1 Publisher2 Publisher3
               |          |          |
               +-----+----+----+-----+
                     |
                     v
              Luồng kết quả hợp nhất
~~~

### 2. Kết quả được phát khi luồng con sẵn sàng

Giả sử ba yêu cầu tra cứu được gửi gần như cùng lúc. Yêu cầu thứ hai hoàn tất trước, yêu cầu thứ ba hoàn tất tiếp theo, cuối cùng yêu cầu thứ nhất mới hoàn tất. Với **flatMap**, kết quả thường được phát theo thời điểm các Publisher con phát tín hiệu:

~~~text
Thứ tự nguồn:       A -------- B -------- C

Thời gian xử lý:    A ------------------------> A'
                    B -------> B'
                    C -------------> C'

Đầu ra flatMap:              B' ------ C' -------- A'
~~~

Sơ đồ chỉ minh họa khả năng hoàn tất khác thời điểm. Trong thực tế, thời điểm phát phụ thuộc nguồn, scheduler và thời gian xử lý của từng nhánh. **flatMap** không cam kết giữ thứ tự của nguồn; nó chuyển tiếp tín hiệu khi các Publisher con phát ra.

Ví dụ với các Mono hoàn tất sau khoảng thời gian khác nhau:

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<Integer> results =
    Flux.just(1, 2, 3)
        .flatMap(value ->
            Mono.delay(Duration.ofMillis(40L - value * 10L))
                .map(tick -> value)
        );
~~~

Trong ví dụ, giá trị 1 có độ trễ 30 ms, giá trị 2 có độ trễ 20 ms và giá trị 3 có độ trễ 10 ms. Khi các Publisher con chạy đồng thời, kết quả có thể đến theo thứ tự 3, 2, 1. Không nên viết kiểm thử hoặc logic nghiệp vụ giả định rằng kết quả sẽ luôn là 1, 2, 3.

### 3. Xen kẽ phần tử từ các luồng con

Khả năng xen kẽ thể hiện rõ hơn khi mỗi phần tử nguồn ánh xạ thành một **Flux** phát nhiều phần tử. Ví dụ, mỗi đơn hàng có thể tạo một luồng các dòng sản phẩm:

~~~java
Flux<OrderLine> allLines =
    orderIds.flatMap(id -> orderClient.streamLines(id));
~~~

Nếu luồng của đơn hàng A phát A1, A2, A3, còn luồng của đơn hàng B phát B1, B2, B3, đầu ra có thể có dạng:

~~~text
Nguồn con A:  A1 -------- A2 -------- A3
Nguồn con B:  B1 ---- B2 -------- B3

Đầu ra có thể: B1 ---- A1 -- B2 ---- A2 -- B3 ---- A3
~~~

Đầu ra là một chuỗi tín hiệu được hợp nhất. Các phần tử từ một luồng con thường giữ thứ tự tương đối của chính luồng con đó, trong khi phần tử giữa các luồng con có thể xen kẽ. Đây là điểm quan trọng khi xử lý nhiều nguồn dữ liệu đồng thời.

### 4. Ví dụ nghiệp vụ: tra cứu nhiều đơn hàng

Một trang quản trị cần lấy chi tiết cho nhiều mã đơn hàng. Mỗi lời gọi dịch vụ trả về một Mono, và các yêu cầu có thể hoàn tất ở những thời điểm khác nhau:

~~~java
import reactor.core.publisher.Flux;

Flux<OrderDetails> details =
    Flux.fromIterable(orderIds)
        .flatMap(orderClient::findDetails, 8);
~~~

Tham số 8 giới hạn tối đa số Publisher con đang được đăng ký đồng thời theo overload này. Nếu có hàng trăm mã đơn hàng, Reactor không cần khởi chạy tất cả yêu cầu cùng một lúc; các yêu cầu mới được đăng ký khi có chỗ trống trong giới hạn concurrency.

Giới hạn concurrency hữu ích khi dịch vụ phía sau có hạn mức kết nối, giới hạn request hoặc tài nguyên xử lý hữu hạn. Một giá trị concurrency quá lớn có thể gây quá tải dịch vụ, còn giá trị quá nhỏ có thể làm giảm thông lượng khi các yêu cầu chủ yếu chờ I/O.

### 5. flatMap không tự tạo thread mới

**flatMap** cho phép nhiều Publisher con cùng hoạt động, nhưng không tự động chuyển công việc sang thread khác. Nếu mapper thực hiện tính toán đồng bộ nặng hoặc gọi API blocking trước khi trả về Publisher, lời gọi đó vẫn có thể chặn thread đang xử lý tín hiệu nguồn.

Ví dụ dưới đây tạo một Mono từ thao tác blocking:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Flux<CustomerProfile> profiles =
    customerIds.flatMap(id ->
        Mono.fromCallable(() -> legacyClient.loadProfile(id))
            .subscribeOn(Schedulers.boundedElastic()),
        16
    );
~~~

**fromCallable** trì hoãn lời gọi đến khi có subscription và chuyển ngoại lệ thành tín hiệu lỗi. **subscribeOn(Schedulers.boundedElastic())** điều phối thao tác blocking trên scheduler phù hợp. Tham số concurrency 16 giới hạn số Publisher con hoạt động đồng thời qua nhánh này.

Nếu API client đã non-blocking và trả về Mono/Flux, không cần bọc nó bằng **fromCallable** hoặc chuyển scheduler chỉ để có concurrency. Hãy để client reactive thực hiện I/O theo cơ chế của nó, rồi dùng **flatMap** để điều phối các Publisher con.

### 6. Điều khiển concurrency và prefetch

Reactor có các overload cho phép điều khiển số Publisher con hoạt động đồng thời và lượng phần tử được yêu cầu trước từ mỗi Publisher con:

~~~java
Flux<Event> events =
    source.flatMap(
        event -> eventClient.fetchRelatedEvents(event),
        12,
        4
    );
~~~

Trong ví dụ:

- 12 là **concurrency**: số Publisher con tối đa được đăng ký đồng thời.
- 4 là **prefetch**: số phần tử được yêu cầu trước từ mỗi Publisher con trong cơ chế điều phối của toán tử.

Concurrency kiểm soát số nhánh con đang hoạt động. Prefetch kiểm soát lượng tín hiệu mà toán tử yêu cầu trước từ mỗi nhánh để duy trì hoạt động. Tăng các giá trị này có thể cải thiện thông lượng khi nguồn thường xuyên chờ I/O, nhưng cũng có thể tăng lượng phần tử đang chờ và bộ nhớ sử dụng.

Không nên chọn giá trị chỉ dựa trên số lượng CPU. Hãy cân nhắc độ trễ I/O, giới hạn dịch vụ ngoài, kích thước phần tử, tốc độ downstream và ngân sách bộ nhớ. Đo đạc trong điều kiện tải đại diện sẽ giúp chọn cấu hình phù hợp hơn.

### 7. So sánh flatMap, flatMapSequential và concatMap

Ba toán tử đều ánh xạ mỗi phần tử nguồn thành một Publisher con, nhưng khác nhau về cách đăng ký và phát kết quả:

| Toán tử | Đăng ký Publisher con | Thứ tự đầu ra | Khi phù hợp |
| --- | --- | --- | --- |
| **flatMap** | Có thể đăng ký nhiều nhánh đồng thời | Theo thời điểm nhánh phát; các nhánh có thể xen kẽ | Ưu tiên thông lượng và không yêu cầu thứ tự toàn cục |
| **flatMapSequential** | Có thể đăng ký trước nhiều nhánh đồng thời | Giữ thứ tự theo phần tử nguồn; kết quả nhánh sau có thể phải chờ | Muốn tận dụng I/O đồng thời nhưng cần thứ tự đầu ra |
| **concatMap** | Đăng ký và xử lý từng Publisher con tuần tự | Theo đúng thứ tự nguồn | Cần tuần tự hóa thao tác hoặc phụ thuộc kết quả trước |

Ví dụ, cùng một mapper có thể được dùng với các toán tử khác nhau:

~~~java
Flux<Result> unordered =
    ids.flatMap(id -> client.fetch(id), 8);

Flux<Result> orderedConcurrent =
    ids.flatMapSequential(id -> client.fetch(id), 8);

Flux<Result> sequential =
    ids.concatMap(id -> client.fetch(id));
~~~

Với **flatMapSequential**, nhánh sau có thể hoàn tất trước nhưng kết quả của nó được giữ lại cho đến khi các nhánh trước phát xong để đầu ra giữ thứ tự nguồn. Điều này có thể cần thêm bộ nhớ nếu nhánh đầu chậm trong khi nhiều nhánh sau đã hoàn tất.

Với **concatMap**, Publisher con tiếp theo chỉ được đăng ký sau khi Publisher con hiện tại hoàn tất. Cách này giảm số nhánh hoạt động đồng thời và phù hợp khi thao tác có phụ thuộc thứ tự, chẳng hạn cập nhật trạng thái tuần tự cho cùng một thực thể.

### 8. Xử lý lỗi từ một Publisher con

Mặc định, nếu một Publisher con phát lỗi, **flatMap** truyền lỗi đó xuống downstream và hủy các nhánh đang hoạt động còn lại theo chính sách lỗi tức thời. Các phần tử đã phát trước lỗi vẫn đã được downstream nhận; các phần tử chưa phát có thể không còn được xử lý.

Ví dụ:

~~~java
Flux<CustomerProfile> profiles =
    customerIds.flatMap(id -> customerClient.findProfile(id));
~~~

Nếu một lời gọi tra cứu thất bại, toàn bộ pipeline có thể kết thúc bằng **onError**. Nếu nghiệp vụ cho phép bỏ qua một khách hàng lỗi và tiếp tục các khách hàng khác, có thể xử lý lỗi bên trong từng Publisher con:

~~~java
Flux<CustomerProfile> profiles =
    customerIds.flatMap(id ->
        customerClient.findProfile(id)
            .onErrorResume(error -> {
                log.warn("Không tải được hồ sơ {}", id, error);
                return Mono.empty();
            })
    );
~~~

Ở đây, lỗi của một nhánh được chuyển thành Mono rỗng, nên nhánh đó không phát hồ sơ nhưng các nhánh khác vẫn có thể tiếp tục. Chỉ dùng cách này nếu việc thiếu kết quả được nghiệp vụ chấp nhận; không nên âm thầm bỏ lỗi quan trọng.

Nếu muốn trì hoãn việc truyền lỗi cho đến khi các Publisher con đang hoạt động hoàn tất, Reactor cung cấp **flatMapDelayError**:

~~~java
Flux<Result> results =
    ids.flatMapDelayError(
        id -> client.fetch(id),
        8,
        16
    );
~~~

Toán tử vẫn ghi nhận lỗi, nhưng cho các nhánh đang hoạt động tiếp tục phát trước khi chuyển lỗi xuống downstream. Nó không biến lỗi thành thành công và cũng không đảm bảo mọi nhánh chưa được đăng ký sẽ luôn được xử lý; cần đọc đúng ngữ nghĩa lỗi của pipeline và xác định hành vi mong muốn khi một phần tử thất bại.

### 9. Backpressure trong quá trình hợp nhất

Downstream có thể yêu cầu dữ liệu chậm hơn tốc độ tổng hợp của các Publisher con. **flatMap** phối hợp demand với các nhánh con thông qua cơ chế prefetch và hàng đợi nội bộ. Khi downstream chưa sẵn sàng nhận thêm, toán tử có thể giữ một lượng phần tử đang chờ trong các hàng đợi theo cấu hình.

Điều đó có nghĩa concurrency và prefetch ảnh hưởng đến áp lực bộ nhớ. Một cấu hình có nhiều nhánh đồng thời và prefetch lớn có thể giữ nhiều phần tử cùng lúc, đặc biệt khi mỗi phần tử có payload lớn. Cần giới hạn concurrency, chọn prefetch vừa phải và tránh để downstream xử lý quá chậm so với tổng tốc độ các nhánh.

Backpressure chỉ điều tiết các Publisher tuân theo giao thức Reactive Streams hoặc các adapter có chính sách xử lý overflow. Nếu Publisher con kết nối đến nguồn callback không hỗ trợ demand, adapter vẫn cần chính sách buffer, drop, latest hoặc error phù hợp với nghiệp vụ.

### 10. Kiểm thử thứ tự và sự xen kẽ

Khi kiểm thử **flatMap**, tránh giả định thứ tự đầu ra nếu các Publisher con có thời gian hoàn tất khác nhau. Với nguồn thời gian, có thể dùng virtual time của StepVerifier để kiểm thử thứ tự theo độ trễ:

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
        Flux.just(1, 2, 3)
            .flatMap(value ->
                Mono.delay(Duration.ofMillis(40L - value * 10L))
                    .map(tick -> value)
            )
    )
    .thenAwait(Duration.ofMillis(40))
    .expectNext(3, 2, 1)
    .verifyComplete();
~~~

Ba Publisher con được tạo với độ trễ lần lượt 30, 20 và 10 ms. Khi đồng hồ ảo tiến đủ thời gian, kết quả được mong đợi theo thứ tự hoàn tất là 3, 2, 1. Kiểm thử này minh họa rằng **flatMap** không giữ thứ tự nguồn.

Nếu yêu cầu đầu ra theo thứ tự nguồn, có thể kiểm thử **flatMapSequential**:

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
        Flux.just(1, 2, 3)
            .flatMapSequential(value ->
                Mono.delay(Duration.ofMillis(40L - value * 10L))
                    .map(tick -> value)
            )
    )
    .thenAwait(Duration.ofMillis(40))
    .expectNext(1, 2, 3)
    .verifyComplete();
~~~

Các nhánh vẫn có thể chạy đồng thời, nhưng StepVerifier nhận kết quả theo thứ tự phần tử nguồn. Khi kiểm thử pipeline thực tế, cũng nên xác minh giới hạn concurrency, xử lý lỗi từ một nhánh và hành vi cancellation khi downstream hủy.

### 11. Khi nào nên dùng flatMap?

**flatMap** phù hợp khi mỗi phần tử nguồn cần kích hoạt một thao tác bất đồng bộ độc lập, kết quả có thể đến không theo thứ tự nguồn và ứng dụng ưu tiên thông lượng. Các tình huống thường gặp:

- Gọi nhiều dịch vụ để tra cứu thông tin theo danh sách ID.
- Đọc nhiều tệp hoặc đối tượng lưu trữ từ các khóa khác nhau.
- Xử lý từng sự kiện bằng một tác vụ I/O độc lập.
- Chuyển một phần tử thành nhiều kết quả con rồi hợp nhất thành luồng đầu ra.

Trước khi chọn toán tử, hãy xác định:

- Có cần giữ thứ tự của nguồn không?
- Mỗi phần tử tạo ra một Mono hay một Flux có nhiều phần tử?
- Bao nhiêu Publisher con được phép hoạt động đồng thời?
- Mỗi nhánh cần prefetch bao nhiêu phần tử?
- Nếu một nhánh lỗi, các nhánh khác nên bị hủy, tiếp tục hay chuyển lỗi thành kết quả nghiệp vụ?
- Downstream có đủ khả năng tiêu thụ tốc độ hợp nhất không?

Nếu thứ tự không quan trọng, **flatMap** thường là lựa chọn linh hoạt. Nếu cần chạy đồng thời nhưng vẫn giữ thứ tự, cân nhắc **flatMapSequential**. Nếu cần xử lý từng nhánh theo trình tự nghiêm ngặt, dùng **concatMap**. Chọn đúng toán tử giúp pipeline vừa đạt thông lượng phù hợp vừa giữ đúng ngữ nghĩa nghiệp vụ.
