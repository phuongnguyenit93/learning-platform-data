# FailoverLoadBalancingStrategy trong Spring Integration

## Mục tiêu

Trong Spring Integration, một channel kiểu point-to-point có thể có nhiều MessageHandler đăng ký nhận message. Dispatcher cần trả lời hai câu hỏi:

1. **Load balancing:** handler nào được thử trước cho message hiện tại?
2. **Failover:** nếu handler đó ném exception, dispatcher có được thử handler tiếp theo hay phải dừng?

Hai quyết định này phối hợp để tạo thành hành vi thường được gọi là *failover kết hợp load balancing*. Trong API Spring Integration, chúng là hai cấu hình riêng: LoadBalancingStrategy quyết định thứ tự thử handler; thuộc tính failover hoặc Predicate&lt;Exception&gt; failoverStrategy quyết định có tiếp tục sau lỗi hay không.

> **Lưu ý về tên:** không nên mặc định rằng Spring Integration Core cung cấp một class có sẵn tên FailoverLoadBalancingStrategy để khởi tạo trực tiếp. API chuẩn mô tả LoadBalancingStrategy và cơ chế failover riêng trên dispatcher. Nếu dự án có class cùng tên, hãy kiểm tra xem đó có phải implementation tùy biến của dự án hay không.

Sau bài này, bạn có thể chọn cấu hình round-robin hoặc primary/backup, phân loại exception để quyết định failover, và nhận biết những giới hạn liên quan đến transaction, executor và side effect.

## 1. Dispatcher giải quyết vấn đề gì?

DirectChannel là channel point-to-point: mỗi message được xử lý thành công bởi một subscriber. Tuy nhiên, channel có thể có nhiều subscriber cùng đăng ký. DirectChannel ủy quyền việc chọn subscriber cho UnicastingDispatcher.

UnicastingDispatcher thử các handler theo thứ tự do chiến lược load balancing xác định. Khi một handler xử lý message mà không ném exception, dispatcher xem việc dispatch đã thành công và dừng; các handler còn lại không nhận message đó. Nếu handler thất bại và failover được cho phép, dispatcher có thể thử handler tiếp theo. Vì vậy, một message có thể đi qua nhiều lần thử trong cùng một lần dispatch, nhưng chỉ cần một handler xử lý thành công là quá trình kết thúc.

Nếu không có handler nào đăng ký, dispatcher ném MessageDispatchingException. Nếu tất cả handler được thử đều ném exception, dispatcher ném AggregateMessageDeliveryException.

## 2. Tách bạch load balancing và failover

| Cơ chế | Câu hỏi nó trả lời | Cấu hình phổ biến |
|---|---|---|
| Load balancing | Bắt đầu thử handler nào và theo thứ tự nào? | round-robin, none, hoặc bean triển khai LoadBalancingStrategy |
| Failover | Khi handler hiện tại ném exception, có thử handler kế tiếp không? | failover=true/false hoặc failoverStrategy |
| Retry | Có thử lại một lần xử lý theo chính sách số lần, độ trễ và backoff không? | Retry advice / cơ chế retry riêng |
| Error flow | Khi xử lý thất bại, message lỗi được định tuyến và xử lý thế nào? | errorChannel, error handler, router |

Load balancing không tự tạo failover. Ngược lại, failover cũng không tự quyết định thứ tự ưu tiên. Hai cơ chế được áp dụng cùng nhau trên dispatcher dạng unicast.

Với DirectChannel mặc định:

- Load balancing dùng round-robin.
- Failover được bật.
- Cả hai chỉ có ý nghĩa khi channel có nhiều subscriber.

ExecutorChannel cũng hỗ trợ cấu hình dispatcher tương tự. Chi tiết về luồng thực thi và transaction của nó khác DirectChannel, được trình bày ở phần sau.

## 3. Luồng dispatch và failover

~~~mermaid
flowchart TD
    A[Ứng dụng gửi Message vào channel] --> B[UnicastingDispatcher]
    B --> C[LoadBalancingStrategy xác định thứ tự thử]
    C --> D[Dispatcher gọi MessageHandler]
    D -->|Handler xử lý thành công| E[Dừng dispatch]
    D -->|Handler ném Exception| F{Failover có được phép?}
    F -->|Có| G[Thử handler kế tiếp]
    G --> D
    F -->|Không| H[Trả lỗi cho phía gọi]
    G -->|Đã hết handler| I[AggregateMessageDeliveryException]
~~~

Có thể đọc luồng này theo từng bước:

1. Một endpoint gửi Message vào channel.
2. Dispatcher lấy danh sách subscriber hiện có và xác định thứ tự thử.
3. Dispatcher gọi handler đầu tiên trong thứ tự đó.
4. Nếu handler hoàn tất bình thường, dispatcher kết thúc lần dispatch.
5. Nếu handler ném exception, dispatcher đánh giá chính sách failover.
6. Nếu được phép, dispatcher thử handler kế tiếp. Nếu không, lỗi được truyền ra theo ngữ cảnh thực thi.
7. Nếu tất cả handler đều thất bại, dispatcher báo lỗi tổng hợp.

Handler được xem là thành công khi lời gọi xử lý kết thúc bình thường. Nếu handler tự bắt exception rồi trả về bình thường, dispatcher không biết rằng nghiệp vụ bên trong đã thất bại và sẽ không chuyển sang handler khác.

## 4. Các kiểu lựa chọn handler

### 4.1. Round-robin

Round-robin xoay vòng điểm bắt đầu giữa các subscriber. Cách này hữu ích khi nhiều worker có năng lực tương đương và đều có thể xử lý cùng loại message.

Cấu hình DirectChannel mặc định đã dùng round-robin và bật failover:

~~~java
@Bean
public DirectChannel workChannel() {
    return new DirectChannel();
}
~~~

Có thể khai báo rõ trong XML:

~~~xml
<int:channel id="workChannel">
    <int:dispatcher load-balancer="round-robin" failover="true"/>
</int:channel>
~~~

Khi một handler ném exception, failover có thể khiến dispatcher thử các handler tiếp theo theo thứ tự dispatch. Không nên dựa vào một chuỗi handler cố định khi đang dùng round-robin; nếu cần primary, secondary và tertiary rõ ràng, hãy cấu hình thứ tự cố định.

### 4.2. Thứ tự cố định: primary rồi backup

Khi một handler là chính và các handler khác là dự phòng, tắt load balancing bằng none để dispatcher luôn bắt đầu từ handler đầu tiên theo thứ tự subscriber. Failover vẫn có thể được bật.

~~~xml
<int:channel id="orderWorkChannel">
    <int:dispatcher load-balancer="none" failover="true"/>
</int:channel>

<int:service-activator
        input-channel="orderWorkChannel"
        ref="primaryOrderHandler"
        method="handle"
        order="1"/>

<int:service-activator
        input-channel="orderWorkChannel"
        ref="backupOrderHandler"
        method="handle"
        order="2"/>
~~~

Hai endpoint cùng tham chiếu orderWorkChannel, vì vậy chúng cùng đăng ký subscriber trên một channel. Với load-balancer="none", dispatcher bắt đầu ở handler có thứ tự trước. Nếu handler chính ném exception và failover được chấp nhận, handler backup được thử tiếp.

Trong XML namespace, thuộc tính order của endpoint xác định thứ tự. Nếu không khai báo thứ tự tường minh, thứ tự đăng ký subscriber có thể quyết định thứ tự xử lý; không nên phụ thuộc vào thứ tự ngầm này trong một cấu hình primary/backup quan trọng.

Java configuration có thể tạo channel không áp dụng load balancing bằng constructor nhận null:

~~~java
@Bean
public DirectChannel orderWorkChannel() {
    DirectChannel channel = new DirectChannel(null);
    channel.setFailover(true);
    return channel;
}
~~~

### 4.3. Tắt failover để dừng ngay khi lỗi

Khi không muốn một handler khác tiếp tục xử lý sau lỗi, đặt failover=false:

~~~java
@Bean
public DirectChannel failFastChannel() {
    DirectChannel channel = new DirectChannel();
    channel.setFailover(false);
    return channel;
}
~~~

Với cấu hình này, dispatcher chỉ thử handler được chọn đầu tiên trong lần dispatch đó. Exception được truyền ra theo ngữ cảnh thực thi của channel. Có thể dùng khi các subscriber không phải bản thay thế tương đương, hoặc khi lỗi phải được xử lý ở tầng gọi, retry hay error flow.

## 5. Failover có điều kiện theo exception

Từ Spring Integration 6.3, các channel dựa trên UnicastingDispatcher hỗ trợ Predicate&lt;Exception&gt; thông qua setFailoverStrategy. Predicate quyết định có chuyển sang handler tiếp theo dựa trên exception vừa phát sinh.

Ví dụ: chỉ failover khi gặp lỗi truy cập dữ liệu tạm thời:

~~~java
import org.springframework.dao.TransientDataAccessException;
import org.springframework.integration.channel.DirectChannel;

@Bean
public DirectChannel conditionalFailoverChannel() {
    DirectChannel channel = new DirectChannel();

    channel.setFailoverStrategy(exception ->
            exception instanceof TransientDataAccessException);

    return channel;
}
~~~

Ý nghĩa của predicate:

- Trả về true: cho phép dispatcher thử handler tiếp theo.
- Trả về false: dừng failover tại exception hiện tại.

Cách phân loại này giúp tránh chuyển một lỗi dữ liệu hoặc lỗi nghiệp vụ không thể khắc phục sang một handler dự phòng không liên quan. Ví dụ, lỗi kết nối tạm thời có thể phù hợp với failover; lỗi payload sai định dạng thường cần dừng và báo lỗi.

setFailoverStrategy thay thế tùy chọn boolean setFailover; hãy chọn một cơ chế phù hợp với phiên bản Spring Integration đang dùng. Với phiên bản trước 6.3, dùng failover=true/false. Nếu cần phân tích lỗi phức tạp, tài liệu Spring Integration khuyến nghị xem xét ErrorMessageExceptionTypeRouter thay vì nhồi toàn bộ logic định tuyến vào predicate.

## 6. Tùy biến LoadBalancingStrategy

Ngoài các giá trị dựng sẵn round-robin và none, ứng dụng có thể cung cấp bean triển khai LoadBalancingStrategy rồi tham chiếu bằng load-balancer-ref.

~~~xml
<int:channel id="customBalancedChannel">
    <int:dispatcher load-balancer-ref="customLoadBalancer"
                    failover="true"/>
</int:channel>

<bean id="customLoadBalancer"
      class="com.example.integration.PriorityLoadBalancingStrategy"/>
~~~

load-balancer và load-balancer-ref loại trừ lẫn nhau; không khai báo đồng thời cả hai. Implementation tùy biến chịu trách nhiệm xác định thứ tự handler phù hợp với hợp đồng của LoadBalancingStrategy. Nếu chiến lược giữ trạng thái dùng chung, chẳng hạn bộ đếm hoặc chỉ số vòng quay, hãy bảo đảm nó an toàn khi nhiều thread gửi message đồng thời.

Load balancer chỉ làm việc với các subscriber mà dispatcher của channel nhìn thấy. Nó không tự thực hiện service discovery giữa các instance, không kiểm tra sức khỏe của node ở xa và không thay thế cơ chế cân bằng tải ở broker hoặc hạ tầng.

## 7. Những giới hạn cần hiểu trước khi bật failover

### 7.1. Failover không phải retry

Failover chuyển sang handler khác trong cùng lần dispatch sau khi handler hiện tại ném exception. Nó không mặc định gọi lại handler vừa lỗi, không tạo backoff, không giữ message để xử lý sau và không cung cấp bảo đảm giao nhận bền vững.

Nếu cần thử lại cùng một bước xử lý theo số lần và khoảng nghỉ, hãy dùng cơ chế retry phù hợp. Nếu cần giữ message qua thời điểm ứng dụng dừng hoặc khởi động lại, hãy dùng channel/store hoặc broker có khả năng lưu trữ bền vững và cấu hình giao nhận tương ứng.

### 7.2. Side effect có thể bị lặp

Giả sử handler chính gọi dịch vụ thanh toán. Dịch vụ đã nhận yêu cầu và thực hiện thanh toán, nhưng kết nối bị timeout trước khi handler nhận được phản hồi. Handler ném exception; dispatcher chuyển message sang handler backup. Handler backup có thể gửi lại yêu cầu thanh toán và tạo giao dịch thứ hai.

Vì vậy, failover không đảm bảo exactly-once. Các handler dự phòng cần tương đương về ý nghĩa nghiệp vụ và nên dùng khóa idempotency hoặc mã giao dịch ổn định để chống xử lý trùng. Chỉ bật failover khi việc chuyển cùng message sang handler khác là an toàn.

### 7.3. Handler phải để lỗi đi tới dispatcher

Dispatcher chỉ đánh giá exception mà lời gọi handler đưa ra ngoài. Nếu handler nuốt exception:

~~~java
public void handle(Order order) {
    try {
        process(order);
    }
    catch (RuntimeException exception) {
        log.error("Order processing failed", exception);
        // Không ném lại exception
    }
}
~~~

thì dispatcher coi lời gọi đã kết thúc bình thường và không kích hoạt failover. Nếu muốn dispatcher quyết định, hãy để exception phù hợp được ném ra ngoài hoặc chuyển lỗi sang một error flow được thiết kế riêng.

### 7.4. Failover chỉ có tác dụng khi có nhiều subscriber

Nếu chỉ có một endpoint đăng ký trên channel, không có handler kế tiếp để thử. Kiểm tra các endpoint có thực sự dùng chung cùng một input-channel hay không. Hai endpoint dùng hai channel khác nhau không tạo thành một nhóm failover.

### 7.5. DirectChannel và ExecutorChannel có ngữ nghĩa thread khác nhau

| Đặc điểm | DirectChannel | ExecutorChannel |
|---|---|---|
| Thực thi handler | Trong thread gọi send() | Thường được giao cho TaskExecutor |
| Thời điểm send() trả về | Sau khi handler xử lý xong | Thường sau khi công việc được submit |
| Transaction giữa sender và handler | Có thể dùng chung cùng thread và transaction context | Không hỗ trợ transaction trải qua sender và handler |
| Quan sát exception | Có thể truyền về caller đồng bộ | Lỗi có thể xảy ra sau khi caller đã nhận kết quả gửi |

ExecutorChannel hỗ trợ cùng kiểu cấu hình load balancing và failover của dispatcher, nhưng việc xử lý bất đồng bộ làm thay đổi cách quan sát lỗi. Không giả định rằng sender sẽ nhận được exception từ handler. Hãy kiểm tra cấu hình executor, error handling và log của luồng xử lý.

Ngay cả với DirectChannel, failover thành công không tự chứng minh transaction đã commit. Transaction interceptor có thể đánh dấu transaction rollback-only sau exception; side effect ngoài transaction cũng không tự được hoàn tác. Cần thiết kế transaction propagation và tính idempotent của handler theo đúng nghiệp vụ.

## 8. Chẩn đoán khi failover không diễn ra như mong đợi

Khi một message không đến handler dự phòng, kiểm tra lần lượt:

1. **Số subscriber:** channel có ít nhất hai handler đang đăng ký không?
2. **Channel dùng chung:** các endpoint có cùng tham chiếu một DirectChannel hoặc ExecutorChannel không?
3. **Thứ tự bắt đầu:** đang dùng round-robin hay none? Có khai báo order nếu cần primary/backup không?
4. **Chính sách failover:** failover có bị đặt thành false không? Predicate có trả về true cho exception thực tế không?
5. **Exception có thoát khỏi handler:** handler có bắt rồi bỏ qua exception không?
6. **Mô hình thread:** channel có executor khiến lỗi xảy ra sau khi send() đã trả về không?
7. **Side effect:** handler đầu tiên có thể đã thực hiện một phần nghiệp vụ trước khi ném exception không?

Từ Spring Integration 5.2, khi failover được bật, lỗi của handler hiện tại cùng message thất bại được ghi log ở mức DEBUG hoặc INFO tùy cấu hình logging. Khi điều tra production, nên liên kết log bằng message ID hoặc correlation ID, mã nghiệp vụ, channel, handler được thử và loại exception. Có thể bổ sung metric riêng cho số lần failover, handler thành công, lỗi cuối cùng và độ trễ xử lý.

## 9. Kiểm thử hành vi failover

Một bộ kiểm thử nên xác nhận hành vi quan sát được, không chỉ kiểm tra giá trị cấu hình:

- **Primary thành công:** handler chính được gọi; handler backup không được gọi.
- **Primary lỗi, backup thành công:** cả hai handler được gọi theo thứ tự dự kiến; lần dispatch hoàn tất thành công.
- **Predicate từ chối exception:** handler backup không được gọi; lỗi hiện tại được truyền ra.
- **Tất cả handler lỗi:** dispatch kết thúc bằng lỗi tổng hợp.
- **Thứ tự cố định:** với load-balancer="none", mỗi message đều bắt đầu từ subscriber có thứ tự cao ưu tiên hơn.
- **Round-robin:** nhiều message phân phối điểm bắt đầu giữa các subscriber theo chiến lược đã chọn.
- **Tính idempotent:** nếu handler chính đã tạo side effect rồi mới ném exception, việc backup nhận cùng message không tạo tác động nghiệp vụ trùng.

Trong kiểm thử, dùng spy hoặc mock để đếm số lần gọi và ghi nhận thứ tự. Với ExecutorChannel, cần chờ kết quả xử lý bất đồng bộ hoặc quan sát error flow thay vì chỉ assert ngay sau send().

## 10. Quy tắc lựa chọn nhanh

| Nhu cầu | Cấu hình gợi ý |
|---|---|
| Nhiều worker tương đương, chia tải theo vòng | round-robin, failover bật nếu worker thay thế được cho nhau |
| Primary/secondary theo thứ tự rõ ràng | none, failover bật, khai báo order |
| Lỗi phải dừng ngay | failover=false |
| Chỉ chuyển handler với một số loại exception | failoverStrategy từ Spring Integration 6.3 |
| Cần retry cùng handler với backoff | Retry advice / cơ chế retry riêng |
| Cần broadcast cho mọi subscriber | PublishSubscribeChannel |
| Cần lưu message và poll sau | QueueChannel hoặc broker phù hợp |

## Kết luận

Failover và load balancing là hai quyết định độc lập của dispatcher unicast. Hãy chọn load balancing theo cách phân phối công việc, chọn failover theo loại lỗi có thể phục hồi bằng handler khác, rồi kiểm tra tính idempotent, transaction và mô hình thread. Một cấu hình fallback chỉ đáng tin cậy khi các handler thực sự thay thế được cho nhau và việc xử lý lặp không làm sai lệch nghiệp vụ.

## Tài liệu tham khảo

- [Spring Integration — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration — Message Channel Implementations](https://www.springframework.org/spring-integration/reference/channel/implementations.html)
- [Spring Integration 6.5 — UnicastingDispatcher API](https://www.springframework.org/spring-integration/docs/6.5.0/api/org/springframework/integration/dispatcher/UnicastingDispatcher.html)

