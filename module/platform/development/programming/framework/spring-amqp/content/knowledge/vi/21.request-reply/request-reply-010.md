# AsyncRabbitTemplate với CompletableFuture

## 1. Bài toán: gọi một dịch vụ qua RabbitMQ mà không chặn luồng

Trong **Spring AMQP**, luồng xử lý bất đồng bộ thường dùng **RabbitTemplate** để gửi message đến exchange, **@RabbitListener** để nhận từ queue, và **binding** để định tuyến. Với tác vụ dạng sự kiện như “đơn hàng đã tạo”, producer thường không cần nhận kết quả ngay. Nhưng đôi khi một ứng dụng cần **gửi yêu cầu và lấy phản hồi tương ứng**: hỏi số lượng tồn kho, tính phí vận chuyển hoặc tra trạng thái đơn hàng.

Mẫu này gọi là **request–reply**, hay RPC qua messaging. Nếu dùng **RabbitTemplate.convertSendAndReceive(...)**, luồng gọi phải đợi kết quả hoặc timeout. **AsyncRabbitTemplate** cung cấp API trả về **CompletableFuture** để ứng dụng tiếp tục xử lý trong lúc phản hồi đang được chờ.

Ví dụ: API nhận yêu cầu hỏi tồn kho mã **SKU-42**. Service A publish request tới RabbitMQ; service B xử lý và gửi reply; CompletableFuture tại service A hoàn tất khi nhận reply hoặc khi có lỗi/timeout. Service A có thể gắn callback hoặc trả future cho tầng HTTP phù hợp mà không cần gọi **get()** hay **join()** để chờ.

**Mục tiêu sau bài học:** thiết lập luồng request–reply bằng AsyncRabbitTemplate; khai báo exchange/queue/binding; trả lời tự động từ @RabbitListener; xử lý CompletableFuture, timeout, correlation ID, idempotency và lỗi; biết lúc nào nên dùng RPC và lúc nào nên dùng message bất đồng bộ một chiều.

> **Phạm vi phiên bản:** Các ví dụ về **CompletableFuture** phù hợp với dòng **Spring AMQP 3.x trở lên**, nơi API bất đồng bộ sử dụng CompletableFuture. Nếu dự án dùng Spring AMQP 2.x, một số API từng trả về kiểu Future/ListenableFuture cũ; cần đối chiếu phiên bản thư viện trong dự án trước khi áp dụng nguyên mã ví dụ.

## 2. Luồng request–reply diễn ra như thế nào?

~~~text
Service A (client)               RabbitMQ                Service B (worker)
------------------               --------                ------------------
AsyncRabbitTemplate
    |
    | 1. publish request
    |    exchange: stock.rpc.x
    |    routing key: stock.lookup
    |    replyTo: địa chỉ phản hồi
    |    correlationId: mã ghép cặp
    |-----------------------------> exchange
    |                                  |
    |                              binding
    |                                  |
    |                               stock.rpc.q ---------> @RabbitListener
    |                                                         |
    |                                                2. xử lý tồn kho
    |                                                         |
    |  4. nhận reply và                                         |
    |     hoàn tất future <----- reply destination <------------|
    |
    | 5. whenComplete / thenApply / xử lý lỗi
    v
Kết quả bất đồng bộ
~~~

Thông điệp request chứa **replyTo** để server biết nơi gửi phản hồi và **correlationId** để client ghép đúng reply với lời gọi đang chờ. AsyncRabbitTemplate quản lý cơ chế tương quan cho các lời gọi được gửi bằng API request–reply của nó; không cần tự tạo một queue reply riêng cho mỗi request.

Một request–reply có ít nhất bốn mốc khác nhau:

| Mốc | Ý nghĩa |
| --- | --- |
| Client publish request | Client đã yêu cầu RabbitMQ chuyển thông điệp tới service B. |
| Broker chấp nhận request | Có thể được xác nhận bằng publisher confirm nếu được cấu hình; chưa chứng minh service B xử lý. |
| Worker xử lý và publish reply | Nghiệp vụ phía worker đã thực thi đến bước gửi kết quả; reply vẫn cần tới đúng client. |
| CompletableFuture hoàn tất | Client nhận và chuyển đổi reply, hoặc future kết thúc vì timeout/lỗi. |

Điểm quan trọng: **API của client không chặn** không có nghĩa worker tự động xử lý nhanh hơn. RPC qua RabbitMQ vẫn phụ thuộc thời gian định tuyến, tải queue, tài nguyên worker và việc reply được gửi đến nơi nhận.

## 3. Chuẩn bị Spring Boot và topology

Ví dụ tối thiểu dùng **spring-boot-starter-amqp**. Ứng dụng cần kết nối đến một RabbitMQ broker đang hoạt động; thông tin host, cổng, tài khoản và TLS được cấu hình theo môi trường.

~~~xml
<!-- pom.xml: bên trong <dependencies> -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Topology cho ví dụ:

- **Direct exchange**: stock.rpc.x
- **Request queue**: stock.rpc.q, durable
- **Routing key**: stock.lookup
- **Reply destination**: được AsyncRabbitTemplate quản lý (thường là cơ chế **RabbitMQ Direct Reply-to** nếu broker và cấu hình hỗ trợ).

Khai báo ba thành phần request như các bài Spring AMQP thông thường:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.AsyncRabbitTemplate;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class StockRpcConfig {
    public static final String EXCHANGE = "stock.rpc.x";
    public static final String REQUEST_QUEUE = "stock.rpc.q";
    public static final String ROUTING_KEY = "stock.lookup";

    @Bean
    DirectExchange stockExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue stockRequestQueue() {
        return QueueBuilder.durable(REQUEST_QUEUE).build();
    }

    @Bean
    Binding stockRequestBinding(Queue stockRequestQueue,
                                DirectExchange stockExchange) {
        return BindingBuilder.bind(stockRequestQueue)
                .to(stockExchange)
                .with(ROUTING_KEY);
    }

    @Bean
    AsyncRabbitTemplate asyncRabbitTemplate(RabbitTemplate rabbitTemplate) {
        AsyncRabbitTemplate asyncTemplate =
                new AsyncRabbitTemplate(rabbitTemplate);
        asyncTemplate.setReceiveTimeout(5_000L);
        return asyncTemplate;
    }
}
~~~

Trong ví dụ trên, **RabbitTemplate** và kết nối đến RabbitMQ được Spring Boot tự cấu hình từ starter/cấu hình ứng dụng. **AsyncRabbitTemplate** sử dụng RabbitTemplate đó để gửi request, nhưng tự quản lý việc chờ và khớp reply. **setReceiveTimeout(5_000L)** đặt giới hạn chờ phản hồi ở mức 5.000 ms. Nên xác định timeout theo SLA thực tế, không đặt tùy tiện hoặc vô hạn.

Đặt bean AsyncRabbitTemplate trong Spring context để vòng đời listener trả lời được quản lý cùng ứng dụng. Trong kiến trúc hai service, service A có producer/AsyncRabbitTemplate, service B có listener; topology request phải được khai báo thống nhất, thường bởi một bên sở hữu hạ tầng hoặc một module cấu hình dùng chung.

## 4. Worker trả kết quả bằng @RabbitListener

Với lời gọi request–reply thông thường, client gửi sẵn địa chỉ **replyTo**. Phương thức **@RabbitListener** có kiểu trả về khác void sẽ được Spring AMQP dùng để phát reply đến địa chỉ này.

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class StockRpcListener {

    @RabbitListener(queues = StockRpcConfig.REQUEST_QUEUE)
    public String checkStock(String sku) {
        // Demo để có thể chạy độc lập; thực tế hãy truy vấn
        // một service hoặc repository quản lý số lượng tồn kho.
        return "SKU-42".equals(sku) ? "AVAILABLE" : "UNAVAILABLE";
    }
}
~~~

Không cần tự publish reply bằng RabbitTemplate trong ví dụ này và **không cần @SendTo** khi request đã cung cấp replyTo: Spring AMQP dùng replyTo của request để gửi kết quả. **@SendTo** hữu ích trong các trường hợp khác, chẳng hạn quy định sẵn reply destination hoặc khi message không có replyTo.

Nếu listener trả về **null**, không nên mặc định client sẽ nhận một kết quả có giá trị null. Tùy cách xử lý reply, worker có thể không phát message reply và client sẽ chờ đến timeout. Với RPC, hãy định nghĩa **hợp đồng trả lời rõ ràng**, gồm trạng thái thành công, không tìm thấy, lỗi nghiệp vụ và dữ liệu phản hồi.

Ví dụ String chỉ nhằm minh họa luồng. Khi sử dụng DTO/record, hai phía phải dùng **message converter** tương thích (thường là JSON), quy ước schema và tương thích phiên bản; không thể tùy ý gửi Object rồi giả định nó luôn trở thành cùng kiểu Java ở phía nhận.

## 5. Client gửi request, nhận CompletableFuture

Điểm khác biệt quan trọng nhất là lời gọi **convertSendAndReceive(...)** trả về một future cho reply được chuyển đổi, thay vì chờ reply ngay trên luồng gọi.

~~~java
import java.util.concurrent.CompletableFuture;

import org.springframework.amqp.rabbit.AsyncRabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class StockRpcClient {
    private final AsyncRabbitTemplate asyncRabbitTemplate;

    public StockRpcClient(AsyncRabbitTemplate asyncRabbitTemplate) {
        this.asyncRabbitTemplate = asyncRabbitTemplate;
    }

    public CompletableFuture<String> checkStockAsync(String sku) {
        if (sku == null || sku.isBlank()) {
            return CompletableFuture.failedFuture(
                    new IllegalArgumentException("SKU must not be blank"));
        }

        return asyncRabbitTemplate.<String>convertSendAndReceive(
                StockRpcConfig.EXCHANGE,
                StockRpcConfig.ROUTING_KEY,
                sku
        );
    }
}
~~~

Việc trả về **CompletableFuture<String>** giúp tầng gọi tiếp tục ghép công việc hoặc trả một kết quả bất đồng bộ cho framework HTTP hỗ trợ kiểu trả về này. Đoạn mã dùng **SimpleMessageConverter** mặc định với payload String; producer và listener nhất quán về dữ liệu.

Phân biệt hai nhóm API:

| API AsyncRabbitTemplate | Giá trị trả về | Dùng khi |
| --- | --- | --- |
| **sendAndReceive(...)** | Future chứa **Message** thô | Cần đọc properties/header hoặc tự giải mã body. |
| **convertSendAndReceive(...)** | Future chứa object đã được **MessageConverter** chuyển đổi | Muốn lấy dữ liệu nghiệp vụ như String/DTO. |
| **RabbitTemplate.convertSendAndReceive(...)** | Object kết quả theo kiểu gọi đồng bộ | Chấp nhận chặn luồng đến khi có reply/timeout. |

Trong Spring AMQP 3.x+, các future đặc thù của AsyncRabbitTemplate thuộc họ **CompletableFuture**, do đó có thể sử dụng các toán tử CompletableFuture thông thường. Không giả định mọi đời Spring AMQP đều có cùng kiểu trả về.

## 6. Xử lý kết quả mà không dùng get() hoặc join()

**CompletableFuture** đặc biệt hữu ích khi cần tiếp tục công việc sau khi reply đến. Các phương thức sau không cần chặn luồng hiện tại:

~~~java
CompletableFuture<String> future =
        stockRpcClient.checkStockAsync("SKU-42");

future.thenApply(status -> {
    // Biến đổi dữ liệu khi có reply.
    return "AVAILABLE".equals(status);
}).whenComplete((available, error) -> {
    if (error != null) {
        // Log/metrics/ghi nhận lỗi; không log dữ liệu nhạy cảm.
        System.err.println("Stock RPC failed: " + error.getMessage());
    } else {
        System.out.println("Available: " + available);
    }
});

// Luồng hiện tại đi tiếp, không cần chờ tương ứng.
~~~

Các thao tác thường dùng:

| Phương thức | Công dụng | Lưu ý |
| --- | --- | --- |
| **thenApply(fn)** | Biến đổi reply thành kiểu dữ liệu khác. | Nếu fn ném exception, future tiếp theo thất bại. |
| **thenCompose(fn)** | Gọi tiếp một thao tác khác cũng trả future, tránh future lồng nhau. | Phù hợp chuỗi yêu cầu phụ thuộc. |
| **thenCombine(other, fn)** | Kết hợp kết quả của hai future độc lập. | Một trong hai lỗi sẽ ảnh hưởng kết quả kết hợp. |
| **whenComplete(fn)** | Quan sát thành công/lỗi, thường dùng log và metrics. | Không dùng thay cho cơ chế xử lý lỗi thực sự. |
| **exceptionally(fn)** | Chuyển thất bại thành giá trị dự phòng. | Giá trị dự phòng phải có ý nghĩa nghiệp vụ. |
| **handle(fn)** | Tính ra kết quả mới cho cả hai trường hợp thành công/lỗi. | Cần tránh che giấu lỗi. |
| **get() / join()** | Chờ future hoàn thành. | **Chặn luồng**; làm mất lợi ích của mô hình bất đồng bộ. |

Ví dụ ghép hai tra cứu độc lập để chỉ cho phép giao hàng khi cả hai kho đều còn hàng:

~~~java
CompletableFuture<String> north =
        stockRpcClient.checkStockAsync("SKU-42");
CompletableFuture<String> south =
        stockRpcClient.checkStockAsync("SKU-42");

CompletableFuture<Boolean> inBothWarehouses =
        north.thenCombine(south,
                (a, b) -> "AVAILABLE".equals(a)
                        && "AVAILABLE".equals(b));
~~~

Đoạn trên chỉ minh họa **thenCombine**; để tra cứu hai kho thực, cần routing key/payload xác định kho tương ứng. Cả hai request trong ví dụ hiện tại vẫn đi tới cùng request queue.

**Chú ý về thread:** callback không có hậu tố **Async** có thể chạy trên luồng hoàn thành future, chẳng hạn luồng tiếp nhận reply. Không thực hiện xử lý nặng hoặc I/O chậm ngay trong **thenApply/whenComplete**. Nếu cần chuyển sang pool riêng, dùng **thenApplyAsync(..., executor)** hoặc **thenComposeAsync(..., executor)** với executor do ứng dụng quản lý; tránh tạo pool mới cho từng request.

## 7. Timeout, reply muộn và giới hạn trách nhiệm

Giả sử receiveTimeout được đặt là 5 giây:

~~~text
t = 0s    Client gửi request, future đang pending.
t = 1s    Request nằm trong queue, worker chưa rảnh.
t = 5s    Client hết thời gian chờ; future thất bại vì timeout.
t = 7s    Worker xử lý xong và gửi reply.
          Reply đã quá muộn đối với lời gọi này.
~~~

Thông thường, khi quá thời gian chờ, future **hoàn tất ngoại lệ** (có thể gặp **AmqpReplyTimeoutException**, tùy phiên bản/cấu hình). **Không được hiểu timeout là worker chưa xử lý hoặc đã bị hủy**. Worker vẫn có thể cập nhật dữ liệu sau khi client ngừng chờ. Nếu reply đến sau khi correlation của lời gọi đã được giải phóng, nó không thể làm future đã timeout hoàn tất thành công lần nữa.

Khi xử lý lỗi:

~~~java
stockRpcClient.checkStockAsync("SKU-42")
        .whenComplete((reply, error) -> {
            if (error != null) {
                // Timeout, lỗi publish, lỗi giải mã... cần được
                // phân loại theo loại exception và ngữ cảnh thực tế.
                System.err.println("RPC unavailable: " + error);
                return;
            }
            System.out.println("Reply: " + reply);
        });
~~~

Để không giữ request chờ quá lâu, đặt **AsyncRabbitTemplate.setReceiveTimeout(...)**. Có thể thêm deadline ở tầng API/gateway nhưng phải hiểu rõ tương tác: **CompletableFuture.orTimeout(...)** hoàn tất future tại phía Java; nó **không hủy message đang nằm trong RabbitMQ**, cũng không buộc worker ngừng xử lý. Nên có một deadline rõ ràng và chính sách xử lý khi kết quả muộn đến.

Không retry tự động vô hạn chỉ vì timeout. Đối với thao tác có tác dụng phụ như đặt hàng, trừ tiền hoặc gửi email, request ban đầu có thể đã thực hiện thành công. Retry mà không có **idempotency key** có thể gây hành động trùng.

## 8. Correlation ID, replyTo và Direct Reply-to

Một ứng dụng có thể gửi hàng trăm request đồng thời. Giả sử:

~~~text
Request A -- correlationId: c-101 --\
                                     +--> cùng một worker pool
Request B -- correlationId: c-102 --/

Reply B (c-102) đến trước -> hoàn tất future B.
Reply A (c-101) đến sau   -> hoàn tất future A.
~~~

Vì thứ tự hoàn tất không nhất thiết trùng thứ tự gửi, không được ghép reply chỉ bằng “message nào đến trước”. **AsyncRabbitTemplate** dùng thông tin tương quan để ánh xạ message trả về vào đúng future đang đợi.

RabbitMQ cung cấp **Direct Reply-to** với địa chỉ đặc biệt **amq.rabbitmq.reply-to**. Khi cơ chế này được hỗ trợ và sử dụng, client không phải tạo một reply queue durable riêng cho mỗi request. Đây là cách thuận tiện cho RPC ngắn có client còn đang kết nối, nhưng reply qua Direct Reply-to mang tính tạm thời, **best-effort/at-most-once**: khi client mất kết nối hoặc không còn chờ reply, không thể kỳ vọng broker giữ bền vững reply để giao lại sau.

Một số hệ thống dùng **reply queue cố định** thay cho Direct Reply-to. Khi đó phải cấu hình AsyncRabbitTemplate và consumer reply tương thích, đồng thời tính đến các replica của client: nếu nhiều instance cùng tiêu thụ chung một reply queue mà mỗi instance chỉ giữ future của mình, reply có thể bị instance không sở hữu correlation đó nhận mất.

**Correlation ID phục vụ ghép cặp giao thức, còn business request ID phục vụ idempotency.** Hai giá trị có thể liên quan nhưng không nên xem là một: một thao tác nghiệp vụ được retry có thể tạo request AMQP mới và correlation ID mới, trong khi **business request ID** vẫn phải ổn định để worker nhận ra thao tác đã thực hiện.

## 9. Cách ứng phó với lỗi phổ biến

| Tình huống | Điều có thể xảy ra | Cách xử lý |
| --- | --- | --- |
| Sai exchange hoặc routing key; không có binding | Request không tới được worker; future có thể timeout. | Kiểm tra topology, log broker; cấu hình publisher returns/confirm khi cần. |
| Worker ném exception | Worker không gửi được reply bình thường; request có thể bị retry/requeue theo cấu hình listener, client chờ rồi timeout. | Định nghĩa hợp đồng lỗi nghiệp vụ; retry có giới hạn, DLQ; quan sát lỗi listener. |
| Reply đến sau timeout | Worker có thể đã hoàn tất nhưng client xem lời gọi thất bại. | Idempotency, query trạng thái cuối, thiết kế xử lý kết quả muộn. |
| Client mất kết nối trong lúc chờ | Future thất bại hoặc timeout; Direct Reply-to không lưu reply bền vững để chờ client hồi phục. | Xử lý reconnect; chọn chiến lược giao tiếp phù hợp SLA. |
| MessageConverter không nhất quán | Sai kiểu payload, lỗi deserialization hoặc không nhận đúng nội dung. | Cấu hình converter và version schema thống nhất hai phía. |
| Đột biến số request đồng thời | Nhiều future pending, queue backlog và timeout dây chuyền. | Hạn chế số request in-flight, giới hạn tải, scale worker và quan sát độ trễ. |
| Retry request không có idempotency | Ghi dữ liệu hoặc tạo tác dụng phụ nhiều lần. | Thêm business request ID duy nhất và kiểm tra xử lý trùng ở worker. |

**@RabbitListener trả về exception** không mặc nhiên biến exception thành một reply nghiệp vụ mà client hiểu được. Nếu nghiệp vụ cần thông báo “SKU không tồn tại” hoặc “yêu cầu không hợp lệ”, thường nên trả một envelope rõ ràng, ví dụ **{success, data, errorCode}**, với JSON converter tương thích. Các lỗi hệ thống thực sự nên được giám sát riêng và không tự động chuyển mọi lỗi thành “hết hàng”.

Về xác nhận giao nhận, cần phân biệt:

- **Publisher confirm**: broker xác nhận đã xử lý publish theo cơ chế confirm, không chứng minh worker trả reply thành công.
- **Publisher return**: nếu bật mandatory và returns, có thể phát hiện một số tình huống message không được định tuyến; không thay thế xác nhận nghiệp vụ.
- **Consumer ACK**: liên quan message worker đã nhận và xử lý theo chế độ ACK của listener, không phải bằng chứng chắc chắn client đã nhận reply.
- **Future completed normally**: client thực sự nhận được reply và chuyển đổi thành kết quả; vẫn cần kiểm tra nội dung nghiệp vụ của reply.

Hệ thống cần **dead-letter queue** cho request lỗi không xử lý được, retry có backoff hợp lý và metric phân biệt số request gửi, reply thành công, reply lỗi, timeout, message bị dead-letter.

## 10. Thông số vận hành và kiểm soát tải

Một hệ thống RPC qua RabbitMQ nên theo dõi:

| Chỉ số/cấu hình | Tại sao quan trọng |
| --- | --- |
| **receiveTimeout** | Giới hạn thời gian future chờ reply; cần ngắn hơn hoặc phù hợp deadline của caller. |
| **Request queue depth và consumer lag** | Backlog có thể làm reply đến sau khi client timeout. |
| **In-flight RPC requests** | Số request đang chờ reply ảnh hưởng bộ nhớ, connection và độ ổn định. |
| **Latency p50/p95/p99** | Phân biệt đường đi bình thường với đuôi trễ và chọn timeout phù hợp. |
| **Timeout, publish failure và reply conversion failure** | Các loại lỗi cần hướng xử lý khác nhau. |
| **Consumer concurrency và thời gian xử lý** | Quyết định tốc độ đáp ứng request. |
| **Duplicate request/business ID** | Cho biết retry có đang gây xử lý lặp. |

Không để số request in-flight tăng không giới hạn. Ngay cả khi mỗi lời gọi nhanh chóng trả một CompletableFuture, template vẫn phải lưu thông tin tương quan của những lời gọi chưa hoàn tất. Có thể dùng rate limit, bulkhead hoặc semaphore giới hạn đồng thời tại client, đồng thời tăng worker concurrency có kiểm soát.

Nếu API HTTP trả về CompletableFuture, cần phối hợp **HTTP timeout**, **RPC receiveTimeout** và **thời gian xử lý worker**. HTTP gateway có thể ngắt kết nối trước khi RabbitMQ trả reply; future phía ứng dụng và request phía worker không tự động được hủy bởi việc client HTTP ngắt kết nối.

Nên ghi **requestId nghiệp vụ** và trace ID xuyên suốt request, worker, reply; tránh ghi payload nhạy cảm trong log. Correlation AMQP giúp map reply, còn tracing ứng dụng giúp tìm nguyên nhân trễ trên nhiều dịch vụ.

## 11. Kiểm thử hành vi

Thực hành trên hai ứng dụng hoặc hai thành phần trong cùng ứng dụng:

1. Khởi động RabbitMQ và service B; xác minh exchange **stock.rpc.x**, queue **stock.rpc.q** và binding **stock.lookup** tồn tại.
2. Từ service A gọi **checkStockAsync("SKU-42")**. Xác nhận caller nhận CompletableFuture ngay và callback cuối cùng in **AVAILABLE**.
3. Gọi đồng thời nhiều mã SKU. Cố tình cho worker xử lý khác thời gian để kiểm chứng reply vẫn ghép đúng request, không phụ thuộc thứ tự đến.
4. Thêm độ trễ lớn hơn **receiveTimeout** bên worker. Quan sát future thất bại; sau đó kiểm tra worker có thể vẫn thực hiện công việc dù client đã timeout.
5. Tạm dừng consumer và quan sát request queue tăng, nhiều future timeout. Khởi động lại consumer và quan sát request cũ còn trong queue có thể vẫn được xử lý.
6. Gỡ binding ở môi trường test để mô phỏng request không được route. Xác minh metric, publisher return/confirm (nếu cấu hình) và phản ứng khi timeout.
7. Với thao tác có tác dụng phụ, gửi hai request cùng **business request ID**; worker phải ghi nhận để chỉ thực hiện hiệu ứng một lần.

**Gợi ý unit test cho caller:** mock AsyncRabbitTemplate trả một future chưa hoàn tất; gọi client và xác nhận lời gọi trả về ngay; hoàn tất future bằng **complete("AVAILABLE")** hoặc **completeExceptionally(...)** để kiểm tra chuỗi xử lý. **Gợi ý integration test:** dùng RabbitMQ thật hoặc Testcontainers để kiểm chứng replyTo, correlation, timeout và lifecycle của reply listener. Mock đơn thuần không thay thế được việc kiểm tra định tuyến ở broker.

## 12. Khi nào nên và không nên dùng request–reply bất đồng bộ?

| Nhu cầu | Phù hợp hơn | Lý do |
| --- | --- | --- |
| Phải trả lời một câu hỏi nghiệp vụ trong thời gian ngắn, không muốn chặn thread caller | **AsyncRabbitTemplate + CompletableFuture** | Có thể ghép callback và kiểm soát timeout, dùng RabbitMQ làm đường truyền. |
| Hệ thống cũ có API đồng bộ, tải thấp và cần thao tác đơn giản | **RabbitTemplate.convertSendAndReceive(...)** | Dễ theo dõi nhưng chặn luồng trong lúc chờ. |
| Phát sự kiện để nhiều dịch vụ xử lý độc lập | **Publish event, @RabbitListener** | Không cần một reply tương ứng; giảm phụ thuộc thời gian giữa dịch vụ. |
| Công việc kéo dài nhiều phút hoặc phải tiếp tục khi client rời đi | **Job bất đồng bộ + lưu trạng thái + query/event kết quả** | Tránh giữ hàng loạt future đang chờ và phụ thuộc reply tạm thời. |
| Giao dịch có tính nhất quán chặt, phải có kết quả bền vững và chống trùng | **Workflow/outbox/idempotent consumer kết hợp lưu trạng thái** | RPC một lần không tự cung cấp bảo đảm exactly-once hoặc transaction phân tán. |

AsyncRabbitTemplate giải quyết vấn đề **chờ reply mà không chiếm luồng gọi**, nhưng **không biến RPC thành xử lý độc lập hoàn toàn**: thời gian xử lý của worker vẫn ảnh hưởng câu trả lời cho client. Nếu mục tiêu là xử lý nền và có thể lấy kết quả rất lâu sau, mô hình lưu trạng thái tác vụ thường phù hợp hơn.

## 13. Bài thực hành vận dụng

**Bối cảnh:** Service Đơn hàng cần hỏi service Kho xem sản phẩm còn đủ tồn để đặt hàng. Service Kho có thể mất 100 ms đến vài giây tùy tải. API Đơn hàng phải tránh giữ luồng chờ RabbitMQ và phải báo kết quả khi nhận được reply.

**Yêu cầu:**

1. Tạo request exchange, request queue, binding và bean AsyncRabbitTemplate có receiveTimeout 3–5 giây.
2. Viết phương thức **checkStockAsync(sku)** trả **CompletableFuture<String>**, không gọi get() hoặc join().
3. Viết **@RabbitListener** nhận SKU và trả một kết quả theo hợp đồng đã định.
4. Gắn callback ghi kết quả hoặc lỗi, sau đó viết một phép biến đổi bằng **thenApply**; thử **thenCombine** cho hai lời gọi độc lập.
5. Mô phỏng worker trả lời muộn, listener ném exception và binding sai. Ghi nhận mỗi kiểu lỗi và hành vi tương ứng.
6. Bổ sung **requestId nghiệp vụ**, thử retry cùng requestId và giải thích cách chống tác dụng phụ trùng lặp.
7. Giải thích vì sao **correlationId**, **publisher confirm**, **consumer ACK** và **CompletableFuture thành công** là bốn khái niệm khác nhau.

**Câu hỏi tự kiểm tra:** Client gửi request lúc 10:00:00, timeout lúc 10:00:05. Worker xử lý xong lúc 10:00:07 và đã cập nhật tồn kho. Client có nên gửi lại ngay một request “trừ 1 sản phẩm” với ID mới không?

**Đáp án:** Không nên gửi lại một cách mù quáng. Timeout chỉ cho biết client không nhận reply đúng hạn, không chứng minh worker chưa cập nhật. Cần **idempotency key ổn định**, hoặc tra cứu trạng thái thao tác trước khi quyết định retry, tránh trừ tồn kho hai lần.

## 14. Ghi nhớ

**AsyncRabbitTemplate** là API request–reply của Spring AMQP cho phía gọi bất đồng bộ. Sau khi khai báo exchange, queue, binding và listener, client gọi **convertSendAndReceive(...)** để nhận **CompletableFuture**, còn worker có thể trả reply trực tiếp từ phương thức **@RabbitListener**. Template xử lý việc tương quan reply; ứng dụng phải tự chịu trách nhiệm về **timeout**, **ngữ nghĩa lỗi**, **idempotency**, **kiểm soát tải**, **quan sát** và lựa chọn mô hình phù hợp với tác vụ nghiệp vụ.
