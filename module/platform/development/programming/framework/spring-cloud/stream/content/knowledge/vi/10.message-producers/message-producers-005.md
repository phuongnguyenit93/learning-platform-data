# Sử dụng @PollableBean cho nguồn trả luồng hữu hạn

Một ứng dụng xử lý sự kiện đôi khi cần đọc một tập dữ liệu hữu hạn từ cơ sở dữ liệu hoặc một nguồn bên ngoài rồi phát từng phần tử thành message. Ví dụ, dịch vụ đơn hàng định kỳ lấy các bản ghi outbox đang chờ gửi và đưa chúng lên destination để các dịch vụ khác xử lý. Với Spring Cloud Stream, có thể biểu diễn nguồn dữ liệu này bằng một reactive Supplier trả về Flux<T>.

Điểm cần chú ý là Spring Cloud Stream thường xem Supplier<Flux<T>> như một nguồn reactive liên tục: framework gọi Supplier để lấy Flux rồi kết nối với luồng xử lý. Nếu Flux thực tế chỉ chứa một tập hữu hạn, Supplier cần được gọi lại theo chu kỳ để lấy tập dữ liệu tiếp theo. Annotation @PollableBean đánh dấu đúng trường hợp này và cho phép Spring Cloud Stream áp dụng cơ chế polling cho Supplier reactive.

Bài học tập trung vào cách chọn đúng mô hình nguồn, cấu hình poller, tách phần tử thành message, quản lý dữ liệu đã phát và kiểm thử. Các ví dụ dùng Java, Spring Cloud Stream và Project Reactor; dependency, cấu hình binder và một số chi tiết vận hành cần được đối chiếu với phiên bản Spring Cloud đang sử dụng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao Supplier<Flux<T>> thông thường thường được khởi tạo một lần.
- Phân biệt nguồn reactive liên tục với nguồn reactive trả về tập dữ liệu hữu hạn.
- Dùng @PollableBean để đánh dấu Supplier<Flux<T>> cần được gọi lại theo chu kỳ.
- Hiểu thuộc tính splittable và tác động của nó đến số message được phát ra.
- Cấu hình output binding và poller cho nguồn hữu hạn.
- Thiết kế truy vấn theo lô, cursor hoặc outbox để mỗi lần polling lấy được dữ liệu phù hợp.
- Xử lý lỗi, message trùng, kiểm thử bất đồng bộ và theo dõi hoạt động của nguồn.

## 1. Bài toán: một Supplier reactive nhưng dữ liệu có điểm kết thúc

Spring Cloud Stream hỗ trợ ba dạng hàm chính:

| Dạng hàm | Đầu vào | Đầu ra | Cách kích hoạt thường gặp |
|---|---|---|---|
| Supplier<T> | Không có | Một giá trị T | Poller gọi định kỳ |
| Function<T, R> | Một message T | Một kết quả R | Message đầu vào kích hoạt |
| Consumer<T> | Một message T | Không có | Message đầu vào kích hoạt |

Supplier không có input binding để nhận sự kiện kích hoạt. Framework cần một cơ chế khác để gọi phương thức get(). Với Supplier<T> mang tính imperative, mỗi lần gọi thường tạo một giá trị và cơ chế poller mặc định gọi nó định kỳ.

Supplier<Flux<T>> mang ý nghĩa khác. Phương thức get() trả về một Publisher, tức là một mô tả luồng dữ liệu. Trong mô hình reactive thông thường, framework gọi Supplier một lần để lấy Flux rồi đăng ký tiêu thụ luồng đó. Cách này phù hợp với một nguồn sống lâu dài như Flux phát sự kiện liên tục.

Tuy nhiên, có những nguồn trả về Flux hữu hạn. Ví dụ:

- Truy vấn JDBC hoặc R2DBC trả về một tập bản ghi hiện có.
- Một lần đọc file trả về danh sách các dòng.
- Một API bên ngoài trả về một trang kết quả.
- Một bảng outbox chứa các sự kiện đang chờ phát.
- Một tác vụ định kỳ tạo một lô sự kiện cần gửi đi.

Sau khi Flux hoàn tất, không còn phần tử nào được phát từ lần gọi đó. Nếu Supplier chỉ được gọi một lần, lần truy vấn kế tiếp sẽ không tự diễn ra. Đây là lúc cần đánh dấu Supplier là pollable.

## 2. @PollableBean là gì?

@PollableBean là marker annotation trong Spring Cloud Function, có tên đầy đủ là:

~~~java
org.springframework.cloud.function.context.PollableBean
~~~

Annotation này đánh dấu một Supplier reactive tạo ra luồng hữu hạn và cần được gọi lại theo cơ chế polling của framework tích hợp. Khi dùng với Spring Cloud Stream, phần tích hợp nhận biết marker này và đăng ký Supplier với poller để mỗi chu kỳ có thể lấy một Flux mới.

Một điểm quan trọng: Spring Cloud Function chỉ cung cấp ý nghĩa đánh dấu của annotation, bản thân Spring Cloud Function không tự tạo scheduler hay thực hiện polling. Hành vi polling được framework tích hợp, trong trường hợp này là Spring Cloud Stream, cung cấp.

Ví dụ tối giản:

~~~java
import java.util.function.Supplier;

import org.springframework.cloud.function.context.PollableBean;
import reactor.core.publisher.Flux;

public class GreetingSource {

    @PollableBean
    public Supplier<Flux<String>> greetings() {
        return () -> Flux.just("xin chao", "hen gap lai");
    }
}
~~~

Mỗi lần Supplier được gọi, nó trả về một Flux hữu hạn có hai phần tử. PollableBean cho biết nguồn này cần được gọi lại, thay vì coi Flux đầu tiên là một luồng liên tục tồn tại mãi.

Vì @PollableBean đã đóng vai trò khai báo bean, phương thức ví dụ dùng annotation này trực tiếp. Không cần đặt thêm @Bean trên cùng phương thức. Hãy dùng đúng package và dependency do phiên bản Spring Cloud Function/Spring Cloud Stream tương thích cung cấp.

## 3. Phân biệt ba kiểu Supplier

### 3.1. Supplier imperative tạo một giá trị mỗi lần

Khi Supplier trả về một đối tượng đơn, mỗi lần poll tạo một message:

~~~java
@Bean
public Supplier<Heartbeat> heartbeat() {
    return () -> new Heartbeat(Instant.now());
}

record Heartbeat(Instant createdAt) {}
~~~

Đây là lựa chọn phù hợp khi một lần gọi chỉ tạo một giá trị. Không cần @PollableBean để biến một Supplier imperative thành nguồn định kỳ; cơ chế poller mặc định đã hỗ trợ kiểu nguồn này.

### 3.2. Supplier reactive liên tục

Một Supplier trả về Flux dài hạn thường được gọi một lần:

~~~java
@Bean
public Supplier<Flux<Heartbeat>> heartbeatStream() {
    return () -> Flux.interval(Duration.ofSeconds(1))
            .map(tick -> new Heartbeat(Instant.now()));
}
~~~

Flux.interval tạo ra các phần tử theo thời gian và không tự hoàn tất. Đây là nguồn reactive liên tục. Không đánh dấu nguồn này bằng @PollableBean, vì việc gọi lại Supplier theo chu kỳ có thể tạo nhiều luồng liên tục và nhiều subscription không mong muốn.

### 3.3. Supplier reactive hữu hạn

Một Supplier trả về Flux hữu hạn cần được gọi lại để đọc tập dữ liệu mới:

~~~java
@PollableBean
public Supplier<Flux<Heartbeat>> finiteHeartbeatBatch() {
    return () -> Flux.just(
            new Heartbeat(Instant.now()),
            new Heartbeat(Instant.now()));
}
~~~

Đây là trường hợp dành cho @PollableBean. Mỗi lần polling tạo một Flux hữu hạn, các phần tử được tiêu thụ, Flux hoàn tất và chu kỳ tiếp theo có thể gọi Supplier để lấy dữ liệu mới.

| Tiêu chí | Supplier<T> | Supplier<Flux<T>> liên tục | Supplier<Flux<T>> hữu hạn |
|---|---|---|---|
| Giá trị trả về | Một giá trị | Một Publisher dài hạn | Một Publisher có điểm kết thúc |
| Hành vi thường dùng | Poll từng giá trị | Đăng ký một lần | Poll để lấy nhiều lô |
| Annotation | @Bean | @Bean | @PollableBean |
| Ví dụ | Heartbeat mỗi lần gọi | Flux.interval | Truy vấn một trang dữ liệu |

Không nên chọn annotation chỉ dựa trên việc kiểu trả về có chữ Flux. Hãy xem xét vòng đời thực tế của Publisher: nó hoàn tất sau mỗi lô hay tiếp tục phát dữ liệu trong thời gian dài?

## 4. Thuộc tính splittable

@PollableBean có thuộc tính splittable. Giá trị mặc định là true. Khi true, kết quả Flux được tách thành các phần tử riêng và mỗi phần tử được phát như một message riêng.

Ví dụ:

~~~java
@PollableBean(splittable = true)
public Supplier<Flux<String>> names() {
    return () -> Flux.just("An", "Binh", "Chi");
}
~~~

Trong một chu kỳ polling, Supplier tạo ba phần tử. Với chế độ tách mặc định, output binding nhận ba message:

~~~text
Message 1: An
Message 2: Binh
Message 3: Chi
~~~

Đây là lựa chọn thường phù hợp với event streaming: mỗi bản ghi là một đơn vị dữ liệu độc lập, có thể được định tuyến, phân vùng, xác nhận và xử lý riêng.

Nếu đặt splittable = false, framework giữ Flux như một kết quả không tách ở bước xử lý này. Cách sử dụng đó chỉ phù hợp khi phần xử lý tiếp theo và message converter/binder hỗ trợ biểu diễn kết quả theo dạng mong muốn. Không nên mặc định rằng mọi broker đều có thể serialize một đối tượng Flux thành một payload batch. Hãy kiểm tra định dạng message thực tế bằng integration test.

| Cấu hình | Ý nghĩa | Trường hợp phù hợp |
|---|---|---|
| splittable = true | Tách từng phần tử Flux thành message riêng | Mỗi bản ghi là một sự kiện độc lập |
| splittable = false | Không tách Flux ở bước splitter | Luồng tiếp theo có chủ đích xử lý kết quả như một đơn vị |

Ví dụ dùng mặc định:

~~~java
@PollableBean
public Supplier<Flux<OrderCreated>> orderEvents() {
    return () -> repository.findPendingEvents();
}
~~~

Ví dụ tường minh:

~~~java
@PollableBean(splittable = false)
public Supplier<Flux<OrderBatch>> orderBatches() {
    return () -> repository.findPendingBatches();
}
~~~

Ví dụ thứ hai chỉ có ý nghĩa nếu kiểu payload thực tế và converter của ứng dụng hỗ trợ việc gửi kết quả như một đơn vị. Nếu yêu cầu nghiệp vụ là gửi một JSON array, hãy cân nhắc tạo kiểu batch rõ ràng như List<OrderCreated> hoặc OrderBatch và kiểm thử serialization, thay vì cho rằng Flux tự động trở thành JSON array.

## 5. Xây dựng nguồn đọc dữ liệu theo lô

Một nguồn hữu hạn hữu ích cần trả về dữ liệu mới trong mỗi lần gọi. Ví dụ sau mô phỏng dịch vụ đọc sự kiện từ outbox:

~~~java
import java.util.function.Supplier;

import org.springframework.cloud.function.context.PollableBean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;

@Configuration
class OrderEventSource {

    private final OrderOutboxRepository repository;

    OrderEventSource(OrderOutboxRepository repository) {
        this.repository = repository;
    }

    @PollableBean(splittable = true)
    Supplier<Flux<OrderCreated>> pendingOrders() {
        return () -> Flux.defer(() ->
                repository.claimNextBatch(100)
                        .map(OutboxRecord::toOrderCreated));
    }
}

interface OrderOutboxRepository {
    Flux<OutboxRecord> claimNextBatch(int limit);
}

record OutboxRecord(String eventId, String orderId, String customerId) {
    OrderCreated toOrderCreated() {
        return new OrderCreated(eventId, orderId, customerId);
    }
}

record OrderCreated(String eventId, String orderId, String customerId) {}
~~~

Đây là ví dụ mô tả ranh giới của repository; claimNextBatch cần được triển khai bằng truy vấn và cơ chế cập nhật trạng thái phù hợp với cơ sở dữ liệu. Tên phương thức không tự bảo đảm rằng dữ liệu đã được khóa hoặc đánh dấu. Phần triển khai phải bảo đảm hai instance không cùng lấy một lô ngoài ý muốn.

Flux.defer trì hoãn việc tạo publisher nguồn đến lúc có subscription. Điều này hữu ích khi cần mỗi lần subscription thực hiện truy vấn mới. Cũng cần hiểu rõ cách repository được triển khai: một số API trả về cold Flux và chỉ thực thi khi subscribe, trong khi một API khác có thể đã khởi chạy thao tác ngay khi gọi phương thức.

### 5.1. Không đọc lại cùng một bản ghi vô hạn

Giả sử mỗi lần polling đều chạy:

~~~sql
SELECT *
FROM order_outbox
WHERE status = 'PENDING'
ORDER BY created_at
LIMIT 100;
~~~

Nếu trạng thái bản ghi không thay đổi sau khi gửi, lần polling tiếp theo sẽ đọc lại cùng 100 bản ghi. Kết quả là producer phát message trùng lặp liên tục.

Nguồn cần một chiến lược tiến độ rõ ràng:

- Claim bản ghi bằng một transaction và chuyển trạng thái sang PROCESSING.
- Gán lease hoặc thời điểm hết hạn để bản ghi có thể được lấy lại khi worker gặp sự cố.
- Chỉ đánh dấu SENT sau khi xác nhận kết quả gửi theo mức bảo đảm mà ứng dụng yêu cầu.
- Lưu event ID ổn định để consumer có thể nhận biết message trùng.
- Giới hạn số bản ghi trong một lô để kiểm soát bộ nhớ và thời gian xử lý.

Với nhiều instance producer, việc claim phải có tính nguyên tử. Có thể dùng khóa hàng, câu lệnh cập nhật có điều kiện, SKIP LOCKED nếu hệ quản trị cơ sở dữ liệu hỗ trợ, hoặc một cơ chế lease tương đương. Cú pháp SQL và mức cô lập transaction phụ thuộc hệ quản trị được sử dụng.

### 5.2. Phân trang và cursor

Nếu dữ liệu có thể tăng nhanh, tránh đọc toàn bộ tập dữ liệu vào bộ nhớ. Chọn một chiến lược theo lô:

| Chiến lược | Cách hoạt động | Lưu ý |
|---|---|---|
| Limit/offset | Đọc một đoạn theo vị trí | Offset lớn có thể chậm; dữ liệu thay đổi có thể làm lệch trang |
| Cursor theo khóa | Đọc các bản ghi có khóa lớn hơn khóa đã xử lý | Cần khóa sắp xếp ổn định và xử lý bản ghi đến muộn |
| Claim theo trạng thái | Chuyển bản ghi sang trạng thái đang xử lý trong lúc lấy | Phải có lease và quy trình thu hồi khi worker chết |
| Outbox relay | Đọc bản ghi outbox chưa phát và chuyển tiếp | Cần thiết kế transaction, retry và idempotency |

Đối với nguồn sự kiện nghiệp vụ, outbox relay thường dễ kiểm soát hơn một truy vấn tùy ý trên bảng nghiệp vụ vì outbox lưu rõ event ID, payload, loại sự kiện và trạng thái phát.

### 5.3. Giữ lô hữu hạn và có giới hạn

Một lần polling nên có thời gian hoàn tất hữu hạn và lượng dữ liệu có thể dự đoán. Hãy đặt giới hạn số bản ghi, timeout cho truy vấn, giới hạn thời gian xử lý và chính sách khi nguồn dữ liệu không phản hồi.

Không nên trả về Flux.interval, Flux.never hoặc một publisher không bao giờ hoàn tất từ Supplier được đánh dấu @PollableBean. Một lần polling cần có điểm kết thúc để chu kỳ tiếp theo có thể hoạt động đúng theo ý định.

## 6. Cấu hình output binding và poller

Giả sử bean có tên pendingOrders và kiểu Supplier<Flux<OrderCreated>>. Binding đầu ra theo quy ước functional binding là pendingOrders-out-0.

~~~yaml
spring:
  cloud:
    function:
      definition: pendingOrders
    stream:
      bindings:
        pendingOrders-out-0:
          destination: orders.created
          content-type: application/json
  integration:
    poller:
      fixed-delay: 5000
      initial-delay: 1000
~~~

Ý nghĩa:

- spring.cloud.function.definition chọn bean hàm cần bind.
- pendingOrders-out-0 là output binding của Supplier.
- destination xác định topic, queue hoặc tài nguyên tương ứng do binder ánh xạ.
- content-type khai báo định dạng payload để quá trình chuyển đổi message diễn ra nhất quán.
- fixed-delay đặt khoảng thời gian giữa các lần kích hoạt của default poller theo mili giây.
- initial-delay trì hoãn lần kích hoạt đầu tiên.

Theo cấu hình trên, poller bắt đầu sau một giây và sau đó kích hoạt theo khoảng trễ năm giây. Mỗi lần gọi Supplier cần tạo một Flux hữu hạn mới. Với splittable mặc định, từng phần tử của Flux được phát thành message riêng.

Nếu ứng dụng có nhiều output binding cần nhịp polling khác nhau, có thể cấu hình poller riêng cho binding thay vì dùng một cấu hình toàn cục. Cú pháp và thuộc tính chi tiết cần đối chiếu tài liệu của phiên bản Spring Cloud Stream đang chạy.

### 6.1. Default poller và giới hạn message

Spring Cloud Stream sử dụng cơ chế poller mặc định cho Supplier. Tài liệu hiện hành mô tả các thuộc tính như fixedDelay, maxMessagesPerPoll, cron, initialDelay và timeUnit dưới tiền tố spring.integration.poller.

maxMessagesPerPoll là giới hạn số message cho mỗi polling event của default poller. Khi nguồn reactive được tách thành nhiều message, cần kiểm thử hành vi thực tế của phiên bản và binder đang dùng; không nên nhầm giới hạn của poller với kích thước lô mà truy vấn cơ sở dữ liệu trả về. Giới hạn batch ở tầng nguồn nên được thiết kế riêng trong repository.

Không nên giảm fixed-delay xuống quá thấp để bù cho một truy vấn chậm. Hãy đo thời gian mỗi chu kỳ, throughput và độ trễ của nguồn trước khi chọn lịch polling.

## 7. Đường đi của dữ liệu từ nguồn đến broker

~~~mermaid
flowchart TD
    A[Default poller đến lịch] --> B[Gọi Supplier.get]
    B --> C[Tạo Flux hữu hạn mới]
    C --> D[Đọc hoặc claim một lô dữ liệu]
    D --> E{Flux có phần tử?}
    E -->|Có| F{splittable?}
    F -->|true| G[Tách mỗi phần tử thành message]
    F -->|false| H[Giữ kết quả Flux không tách]
    G --> I[Output binding]
    H --> I
    I --> J[Binder]
    J --> K[(Kafka / RabbitMQ / Pulsar)]
    E -->|Không| L[Không phát message trong chu kỳ]
    K --> M[Consumer nhận và xử lý]
~~~

Các thành phần có trách nhiệm khác nhau:

1. Poller quyết định khi nào gọi Supplier.
2. Supplier tạo Publisher cho lần đọc hiện tại.
3. Repository hoặc adapter đọc dữ liệu từ nguồn.
4. PollableBean đánh dấu rằng Supplier reactive này cần được gọi lại theo polling.
5. Splitter xử lý thuộc tính splittable.
6. Output binding và binder chuyển message đến destination.
7. Consumer phía sau chịu trách nhiệm xử lý sự kiện và chống trùng khi cần.

Nếu Flux rỗng, chu kỳ đó không tạo message. Điều này có thể là trạng thái bình thường khi không có dữ liệu chờ xử lý.

## 8. Xử lý lỗi trong một lần polling

Nguồn hữu hạn có thể gặp lỗi khi truy vấn cơ sở dữ liệu, gọi API, đọc file hoặc chuyển đổi payload. Cần phân loại lỗi để chọn hành vi phù hợp:

- Lỗi tạm thời như timeout hoặc mất kết nối có thể được thử lại với backoff.
- Lỗi dữ liệu như bản ghi không hợp lệ cần được ghi nhận, cách ly hoặc đưa vào quy trình xử lý lỗi.
- Lỗi cấu hình như credentials sai hoặc destination không tồn tại cần cảnh báo và sửa cấu hình.
- Lỗi lập trình cần log đủ ngữ cảnh và không được retry vô hạn một cách mù quáng.

Với nguồn reactive, có thể đặt xử lý lỗi trong pipeline:

~~~java
@PollableBean
Supplier<Flux<OrderCreated>> pendingOrders() {
    return () -> Flux.defer(() -> repository.claimNextBatch(100))
            .map(OutboxRecord::toOrderCreated)
            .doOnError(error ->
                    log.error("Cannot read pending order events", error));
}
~~~

Đoạn code minh họa việc ghi nhận lỗi; nó không tự tạo một chính sách retry hoàn chỉnh. Nếu dùng retryWhen, hãy giới hạn số lần thử, dùng backoff có giới hạn và xác định cách hoàn trả lease cho bản ghi đã claim nhưng chưa phát thành công.

Không nên giả định retry của consumer binding sẽ tự động giải quyết mọi lỗi phát sinh trong reactive Supplier. Reactive pipeline có vòng đời và cách xử lý lỗi riêng; cần kiểm thử cả lỗi xảy ra trước khi có phần tử, lỗi giữa luồng và lỗi khi binder gửi message.

### 8.1. Không đánh dấu đã gửi trước khi có kết quả

Giả sử producer cập nhật bản ghi thành SENT ngay sau khi truy vấn nhưng trước khi binder gửi message. Nếu broker mất kết nối ở thời điểm đó, bản ghi đã bị đánh dấu hoàn tất nhưng message chưa đến nơi. Đây là nguy cơ mất sự kiện.

Ngược lại, nếu broker đã nhận message nhưng producer không nhận được phản hồi do timeout rồi gửi lại, message có thể bị trùng. Đây là tình huống phổ biến trong hệ thống phân tán.

Một quy trình outbox relay thường cần:

1. Claim một nhóm bản ghi với lease có thời hạn.
2. Phát message kèm event ID ổn định.
3. Ghi nhận kết quả gửi theo cơ chế xác nhận của binder/broker.
4. Đánh dấu hoàn tất sau khi có kết quả phù hợp.
5. Thu hồi hoặc cho phép claim lại các lease hết hạn.
6. Dùng idempotency ở consumer để xử lý an toàn khi phát lại.

Việc gửi message và cập nhật trạng thái database thường không nằm trong cùng một transaction nguyên tử. Vì vậy, thiết kế nên chấp nhận khả năng giao ít nhất một lần và chống tác động lặp ở phía nhận, trừ khi hệ thống có cơ chế giao dịch cụ thể chứng minh được mức bảo đảm khác.

## 9. Bảo đảm giao nhận và tính idempotent

@PollableBean quyết định Supplier reactive được polling như thế nào; nó không tự bảo đảm message được giao đúng một lần. Mức bảo đảm cuối cùng còn phụ thuộc binder, broker, acknowledgement, producer confirm, transaction và logic cập nhật trạng thái của ứng dụng.

Để xử lý an toàn:

- Gán event ID duy nhất và không đổi cho mỗi sự kiện.
- Consumer lưu dấu event ID đã xử lý hoặc áp dụng unique constraint.
- Tác vụ cập nhật trạng thái nên có tính idempotent.
- Dùng outbox để tách việc ghi sự kiện nghiệp vụ khỏi quá trình gửi qua broker.
- Có lease hoặc cơ chế phục hồi cho bản ghi bị claim nhưng worker dừng.
- Theo dõi số bản ghi pending, processing, sent và số bản ghi quá hạn.

Ví dụ consumer có thể ghi nhận event ID trước khi áp dụng thay đổi nghiệp vụ trong cùng transaction database. Nếu event ID đã tồn tại, consumer bỏ qua tác động lặp và trả về trạng thái xử lý phù hợp.

Không nên dùng thời điểm polling hoặc số lần thử làm event ID. Những giá trị đó thay đổi qua mỗi lần chạy và không nhận diện ổn định một sự kiện nghiệp vụ.

## 10. Kiểm thử Supplier hữu hạn

Nên kiểm thử ở nhiều lớp vì unit test cho Flux không xác minh được lịch poller, binding hoặc semantics của broker.

### 10.1. Unit test bằng StepVerifier

Với nguồn reactive, StepVerifier giúp xác nhận các phần tử và tín hiệu hoàn tất:

~~~java
class PendingOrderSourceTest {

    @Test
    void returnsFiniteBatch() {
        OrderOutboxRepository repository = limit ->
                Flux.just(
                        new OutboxRecord("e-1", "o-1", "c-1"),
                        new OutboxRecord("e-2", "o-2", "c-2"));

        OrderEventSource source = new OrderEventSource(repository);
        Flux<OrderCreated> events = source.pendingOrders().get();

        StepVerifier.create(events)
                .expectNextMatches(event -> event.eventId().equals("e-1"))
                .expectNextMatches(event -> event.eventId().equals("e-2"))
                .verifyComplete();
    }
}
~~~

Đây là kiểm thử ý tưởng về dữ liệu và tín hiệu hoàn tất. Trong mã thực tế, phương thức Supplier có thể được expose theo bean factory method và test nên lấy bean từ Spring context nếu cần kiểm tra wiring hoặc proxy.

### 10.2. Kiểm tra mỗi lần gọi lấy dữ liệu mới

Một kiểm thử quan trọng là xác minh Supplier có thể được gọi nhiều lần và mỗi lần nhận kết quả mới:

~~~java
AtomicInteger pollCount = new AtomicInteger();

@PollableBean
Supplier<Flux<Integer>> counterBatch() {
    return () -> Flux.just(pollCount.incrementAndGet());
}
~~~

Khi gọi get() hai lần, nguồn trả về hai lô khác nhau. Có thể dùng bộ đếm hoặc fake repository để xác minh số lần truy vấn. Kiểm thử này phát hiện trường hợp vô tình tạo một Flux duy nhất ở ngoài lambda rồi tái sử dụng cùng một kết quả cho mọi chu kỳ.

### 10.3. Kiểm thử binding bằng test binder

Spring Cloud Stream test binder cho phép gửi và nhận message trong bộ nhớ. Với Supplier được polling, test nên chờ message bất đồng bộ trong một khoảng timeout có giới hạn:

~~~java
@SpringBootTest(properties = {
        "spring.cloud.function.definition=pendingOrders",
        "spring.integration.poller.fixed-delay=100"
})
class PendingOrderBindingTest {

    @Autowired
    OutputDestination output;

    @Test
    void publishesEachElementAsMessage() {
        Message<byte[]> first =
                output.receive(3000, "pendingOrders-out-0");

        assertNotNull(first);
    }
}
~~~

Ví dụ này chỉ phác họa cách chờ message; test cần cấu hình test binder, repository test double và destination theo đúng phiên bản dependency. Nếu splittable là true, nên nhận đủ số message dự kiến và xác minh payload từng message, thay vì chỉ kiểm tra message đầu tiên.

### 10.4. Integration test với broker thật

Test binder không mô phỏng đầy đủ việc broker lưu message, xác nhận gửi, phân phối partition, phục hồi kết nối hay redelivery. Với luồng quan trọng, bổ sung integration test với đúng broker:

- Kafka: kiểm tra topic, partition, key, producer acknowledgement và consumer group.
- RabbitMQ: kiểm tra exchange, queue, routing, publisher confirm và dead-letter.
- Pulsar: kiểm tra topic, subscription, acknowledgement và redelivery.
- Outbox: kiểm tra claim cạnh tranh, lease hết hạn, broker ngắt kết nối và gửi lại.

Nên kiểm tra cả trường hợp Flux rỗng, batch đầy, batch lớn hơn giới hạn dự kiến, repository timeout, lỗi giữa lúc phát và ứng dụng dừng đột ngột.

## 11. Vận hành và quan sát nguồn polling

Một nguồn polling có thể chạy đúng trong môi trường phát triển nhưng gây tải cao hoặc phát lặp khi triển khai nhiều instance. Cần quan sát các chỉ số sau:

| Chỉ số | Ý nghĩa |
|---|---|
| Số lần polling | Xác nhận poller vẫn hoạt động theo lịch |
| Thời gian một lần polling | Phát hiện truy vấn hoặc xử lý kéo dài |
| Số phần tử trong mỗi Flux | Theo dõi kích thước batch |
| Số message phát thành công/thất bại | Đo kết quả xuất bản |
| Số bản ghi pending/processing/sent | Theo dõi tiến độ outbox |
| Tuổi bản ghi pending lâu nhất | Phát hiện backlog bị kẹt |
| Số lease hết hạn | Phát hiện worker dừng hoặc xử lý quá lâu |
| Số event ID trùng ở consumer | Phát hiện redelivery hoặc producer phát lặp |

Đặt giới hạn batch và thời gian truy vấn để tránh một chu kỳ chiếm quá nhiều tài nguyên. Nếu nhiều instance cùng chạy Supplier, phải xác định rõ mỗi instance đọc cùng một tập dữ liệu hay chia nhau công việc. Với nguồn outbox dùng chung, cơ chế claim là phần bắt buộc để tránh tất cả instance cùng phát một lô.

Poller có thể chạy trên thread do framework quản lý. Không nên dựa vào thread cụ thể hoặc ThreadLocal để lưu trạng thái nghiệp vụ. Nếu cần kiểm soát thread phát message từ một nguồn event-driven bên ngoài, hãy cân nhắc StreamBridge hoặc adapter phù hợp thay vì ép một nguồn liên tục vào mô hình polling.

Khi shutdown, cần cho phép tác vụ đang chạy hoàn tất trong giới hạn thời gian hoặc để lease hết hạn và được instance khác thu hồi. Không đánh dấu bản ghi hoàn tất chỉ vì ứng dụng sắp dừng.

## 12. Khi nào dùng @PollableBean và khi nào chọn cách khác?

| Tình huống | Lựa chọn phù hợp |
|---|---|
| Mỗi lần gọi tạo một giá trị đơn | Supplier<T> |
| Nguồn reactive phát liên tục và tồn tại lâu | Supplier<Flux<T>> thông thường |
| Nguồn reactive truy vấn một tập hữu hạn rồi hoàn tất | @PollableBean Supplier<Flux<T>> |
| Dữ liệu đến từ HTTP, callback hoặc hệ thống event-driven khác | StreamBridge hoặc adapter tích hợp |
| Ứng dụng cần tự quyết định thời điểm đọc từng message đầu vào | PollableMessageSource |
| Cần xử lý trạng thái theo key, cửa sổ hoặc aggregate trên Kafka | Kafka Streams |

Đừng nhầm @PollableBean với PollableMessageSource. @PollableBean đánh dấu một nguồn phát reactive Supplier để framework gọi lại định kỳ. PollableMessageSource là mô hình consumer cho phép ứng dụng chủ động gọi poll() để lấy message đầu vào. Hai cơ chế có hướng dữ liệu và cách điều khiển khác nhau.

## 13. Các lỗi thường gặp

1. **Dùng Supplier<Flux<T>> thông thường cho tập hữu hạn**: Supplier có thể chỉ được gọi một lần, khiến các lần đọc tiếp theo không diễn ra. Hãy đánh dấu nguồn hữu hạn bằng @PollableBean.
2. **Đánh dấu nguồn vô hạn bằng @PollableBean**: mỗi lần polling có thể tạo thêm một luồng liên tục. Hãy dùng Supplier reactive thông thường cho nguồn dài hạn.
3. **Tạo Flux một lần bên ngoài lambda**: các chu kỳ có thể tái sử dụng cùng một Publisher hoặc dữ liệu cũ. Hãy tạo truy vấn/publisher mới trong mỗi lần gọi Supplier.
4. **Không cập nhật trạng thái bản ghi đã phát**: poller đọc lại cùng bản ghi ở chu kỳ sau. Hãy dùng claim, cursor hoặc outbox state.
5. **Dùng splittable = false mà không kiểm tra converter**: Flux có thể không được biểu diễn theo định dạng message mà binder mong đợi. Hãy kiểm thử payload thực tế hoặc dùng kiểu batch rõ ràng.
6. **Nhầm fixed-delay với batch-size**: khoảng thời gian polling không giới hạn số bản ghi repository trả về. Hãy đặt giới hạn batch riêng.
7. **Không kiểm soát nhiều instance**: các instance có thể cùng lấy một tập bản ghi. Hãy dùng claim nguyên tử hoặc cơ chế phân chia công việc.
8. **Đánh dấu SENT trước khi gửi**: lỗi broker có thể làm mất sự kiện. Hãy cập nhật trạng thái theo kết quả gửi và có cơ chế thu hồi lease.
9. **Giả định retry bảo đảm không mất hoặc trùng message**: retry có thể tạo duplicate khi kết quả gửi không xác định. Hãy thiết kế event ID và idempotency.
10. **Không kiểm thử tín hiệu complete**: một nguồn tưởng là hữu hạn nhưng không kết thúc có thể làm chu kỳ polling bị treo. Hãy dùng StepVerifier để xác nhận verifyComplete.
11. **Không theo dõi backlog**: nguồn có thể vẫn polling nhưng không theo kịp tốc độ dữ liệu. Hãy đo tuổi bản ghi chờ, thời gian xử lý và số message phát.

## 14. Quy trình triển khai một nguồn hữu hạn

Khi xây dựng nguồn mới, thực hiện theo trình tự:

1. Xác định nguồn dữ liệu và điều kiện một bản ghi đủ tiêu chuẩn để phát.
2. Chọn Supplier imperative hay reactive dựa trên số lượng phần tử mỗi lần gọi.
3. Nếu dùng Supplier<Flux<T>>, xác định Publisher là hữu hạn hay liên tục.
4. Đánh dấu nguồn hữu hạn bằng @PollableBean.
5. Chọn splittable để quyết định phát từng phần tử hay giữ kết quả như một đơn vị.
6. Đặt giới hạn batch, cursor hoặc cơ chế claim cho mỗi chu kỳ.
7. Cấu hình function definition, output binding, destination và poller.
8. Thiết kế event ID, trạng thái outbox, lease, retry và idempotency.
9. Viết unit test cho dữ liệu và completion; test binder cho output binding; integration test cho broker.
10. Theo dõi thời gian polling, kích thước batch, backlog và lỗi xuất bản khi triển khai.

## Kết luận

@PollableBean giải quyết một trường hợp cụ thể trong mô hình hàm: Supplier reactive trả về một luồng hữu hạn nhưng cần được gọi lại theo chu kỳ để lấy lô dữ liệu mới. Annotation này đánh dấu ý định cho framework tích hợp; Spring Cloud Stream cung cấp cơ chế poller thực hiện việc gọi lại. Thuộc tính splittable mặc định tách từng phần tử thành message riêng.

Để nguồn hoạt động tin cậy, mỗi lần gọi phải tạo một Flux hữu hạn mới, dữ liệu cần có giới hạn và tiến độ đọc phải được quản lý rõ ràng. Với nguồn outbox hoặc cơ sở dữ liệu, cần kết hợp claim/lease, event ID và idempotency để xử lý an toàn khi gửi lại. Polling chỉ quyết định thời điểm đọc dữ liệu; nó không tự bảo đảm giao nhận đúng một lần.

## Tài liệu tham khảo

- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
