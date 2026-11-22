# receiveTimeout và nguy cơ chặn luồng vô thời hạn khi nhận JMS

## 1. Vì sao receiveTimeout quan trọng?

Trong JMS, nhận message theo cách đồng bộ có nghĩa là thread gọi phương thức receive phải chờ cho đến khi có message hoặc thao tác nhận kết thúc. Nếu queue đang rỗng và không có giới hạn thời gian, lời gọi có thể chờ vô thời hạn.

Spring cung cấp JmsTemplate để đơn giản hóa thao tác gửi và nhận đồng bộ. Thuộc tính receiveTimeout quyết định thời gian JmsTemplate chờ khi gọi các phương thức receive. Đây là cấu hình quan trọng vì một lời gọi receive không giới hạn có thể giữ thread của ứng dụng cùng tài nguyên JMS trong thời gian rất dài.

Ví dụ, một HTTP request gọi receiveAndConvert("orders.queue") để đợi đơn hàng tiếp theo. Nếu không có đơn hàng mới, thread xử lý HTTP vẫn bị giữ lại. Khi nhiều request cùng chờ, thread pool có thể cạn và các request khác không còn thread để xử lý.

Cần phân biệt hai mô hình:

- **Nhận đồng bộ:** code ứng dụng gọi JmsTemplate.receive hoặc receiveAndConvert; chính thread gọi phải chờ.
- **Nhận bất đồng bộ:** một listener như @JmsListener được JMS listener container gọi khi message đến; ứng dụng xử lý message trong callback do container quản lý.

receiveTimeout chủ yếu điều khiển thao tác nhận đồng bộ và vòng polling của một số listener container. Nó không phải thời gian timeout của toàn bộ xử lý nghiệp vụ hoặc thời gian chờ chung cho mọi kiểu listener.

## 2. receiveTimeout của JmsTemplate

JmsTemplate có phương thức cấu hình:

~~~java
void setReceiveTimeout(long receiveTimeout)
~~~

Giá trị được tính bằng mili giây. Trong Spring Framework 7.0.10, JmsTemplate mặc định dùng JmsDestinationAccessor.RECEIVE_TIMEOUT_INDEFINITE_WAIT, có giá trị 0. Điều đó có nghĩa receive chặn cho đến khi có message hoặc consumer bị đóng.

Hai hằng số thường dùng:

| Giá trị | Hằng số Spring | Hành vi |
| --- | --- | --- |
| 0 | RECEIVE_TIMEOUT_INDEFINITE_WAIT | Chờ vô thời hạn |
| -1 | RECEIVE_TIMEOUT_NO_WAIT | Kiểm tra message có sẵn ngay lập tức; không chờ |
| Số dương, ví dụ 2000 | Giá trị timeout tùy chỉnh | Chờ tối đa số mili giây được chỉ định |

Theo hợp đồng JmsTemplate, mọi giá trị âm đều có nghĩa không chờ. Nên dùng hằng số RECEIVE_TIMEOUT_NO_WAIT để code thể hiện ý định rõ ràng.

Khi dùng số dương, JmsTemplate chờ đến khi xảy ra một trong các điều kiện: có message, hết timeout hoặc consumer bị đóng. Nếu hết timeout mà không có message, phương thức receive trả về null.

### 2.1. Quan hệ với API Jakarta Messaging

Spring ánh xạ receiveTimeout xuống các phương thức của Jakarta Messaging MessageConsumer:

| Spring receiveTimeout | JMS API tương ứng | Ý nghĩa |
| --- | --- | --- |
| 0 | receive() hoặc receive(0) | Block vô thời hạn |
| Số dương | receive(timeout) | Block tối đa timeout mili giây |
| Số âm | receiveNoWait() | Trả về ngay nếu chưa có message |

Trong Jakarta Messaging, receive(long timeout) với timeout bằng 0 cũng có nghĩa chờ vô thời hạn. receiveNoWait() trả về null ngay khi không có message sẵn sàng. Khi consumer bị đóng trong lúc đang receive, lời gọi đang chờ có thể kết thúc và trả về null.

Không nhầm giá trị 0 của receiveTimeout với ý nghĩa “không chờ”. Trong Spring JMS, 0 là chờ vô thời hạn; giá trị âm mới là không chờ.

## 3. Các phương thức chịu ảnh hưởng

receiveTimeout được cấu hình trên instance JmsTemplate và áp dụng cho các thao tác nhận đồng bộ của instance đó, ví dụ:

- receive()
- receive(Destination)
- receive(String destinationName)
- receiveSelected(...)
- receiveAndConvert(...)
- receiveSelectedAndConvert(...)
- sendAndReceive(...) khi chờ message trả lời

Điểm cuối cùng rất dễ bỏ sót. sendAndReceive vừa gửi request vừa đợi reply; thời gian chờ reply cũng sử dụng receiveTimeout của template. Nếu timeout quá ngắn, ứng dụng có thể nhận null dù hệ thống xử lý request vẫn đang chạy. Nếu timeout vô hạn, thread gửi request cũng có thể bị giữ vô thời hạn.

Nếu receive hoặc receiveAndConvert hết thời gian mà không có message, kết quả là null. Đây là một kết quả hợp lệ, không phải lỗi JMS. Lỗi từ provider thường được Spring chuyển thành JmsException.

## 4. Cấu hình timeout hữu hạn

Trong ứng dụng web hoặc service cần giới hạn thời gian chờ, nên cấu hình timeout hữu hạn phù hợp với ngân sách thời gian của thao tác.

Ví dụ cấu hình JmsTemplate chờ tối đa hai giây:

~~~java
@Configuration
public class JmsConfiguration {

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setReceiveTimeout(2_000);
        return template;
    }
}
~~~

Sau khi cấu hình, có thể nhận message như sau:

~~~java
@Service
public class OrderReceiver {

    private final JmsTemplate jmsTemplate;

    public OrderReceiver(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public Optional<String> receiveNextOrder() {
        Object payload = jmsTemplate.receiveAndConvert("orders.queue");
        return Optional.ofNullable((String) payload);
    }
}
~~~

Với cấu hình trên, nếu trong hai giây không có message, receiveAndConvert trả về null và phương thức trả về Optional.empty(). Nếu có TextMessage, SimpleMessageConverter mặc định của JmsTemplate chuyển body thành String.

Ví dụ này là các thành phần tích hợp trong một ứng dụng Spring; để chạy cần có ConnectionFactory do JMS provider cung cấp và broker đang hoạt động. Không có stdout cố định vì kết quả phụ thuộc message có đến trong khoảng timeout hay không.

### 4.1. Chọn timeout theo deadline của ứng dụng

Timeout nhận JMS cần nằm trong ngân sách thời gian còn lại của thao tác gọi:

- Nếu request HTTP có deadline ba giây, không nên để receiveTimeout mặc định chờ vô hạn.
- Cần chừa thời gian cho kết nối broker, xử lý nghiệp vụ, chuyển đổi message và trả response.
- Nếu service gọi nhiều hệ thống nối tiếp, mỗi lần chờ cần có ngân sách riêng để tổng thời gian không vượt deadline.
- Nếu không có yêu cầu phản hồi ngay, nên đưa việc nhận message sang listener bất đồng bộ hoặc worker chuyên dụng.

Timeout không đảm bảo toàn bộ lời gọi kết thúc đúng mili giây tuyệt đối. Scheduling của JVM, network, broker và cách provider triển khai có thể làm thời gian thực tế lệch khỏi giá trị cấu hình.

## 5. Dùng no-wait khi cần kiểm tra message có sẵn

Khi muốn kiểm tra queue mà không chặn thread, có thể cấu hình:

~~~java
template.setReceiveTimeout(
    JmsDestinationAccessor.RECEIVE_TIMEOUT_NO_WAIT
);
~~~

Hoặc:

~~~java
template.setReceiveTimeout(-1);
~~~

Lúc này, receive trả về ngay:

- Có message sẵn sàng: trả về message.
- Không có message: trả về null.

No-wait phù hợp với một lần kiểm tra nhanh hoặc vòng polling có lịch chạy riêng. Không nên gọi no-wait liên tục trong vòng lặp sát nhau vì có thể tạo busy loop, tiêu tốn CPU và gửi nhiều request không cần thiết đến broker.

Nếu cần polling, hãy kết hợp với lịch chạy có khoảng nghỉ, backoff hoặc scheduler:

~~~java
@Scheduled(fixedDelayString = "PT1S")
public void pollOrders() {
    Object payload = jmsTemplate.receiveAndConvert("orders.queue");

    if (payload != null) {
        processOrder((String) payload);
    }
}
~~~

Đoạn code trên minh họa polling định kỳ. Cần cấu hình JmsTemplate không chờ hoặc dùng timeout rất ngắn để mỗi lượt polling không giữ scheduler thread quá lâu. Nếu xử lý message có thể mất thời gian, hãy chuyển công việc sang executor phù hợp và bảo đảm thứ tự/acknowledgement theo yêu cầu nghiệp vụ.

## 6. Nguy cơ khi chờ vô thời hạn

### 6.1. Cạn thread pool

Mỗi lời gọi receive đồng bộ chiếm một thread trong suốt thời gian chờ. Giả sử web server có 100 request threads và 100 request đều gọi receive với timeout 0. Khi đó, cả 100 thread có thể bị giữ lại. Request mới phải xếp hàng hoặc bị từ chối dù CPU vẫn còn khả năng xử lý.

Tình huống này thường biểu hiện qua:

- Request latency tăng đột ngột.
- Thread pool đạt mức active tối đa.
- Queue chờ của server tăng.
- Health check hoặc endpoint quản trị phản hồi chậm.
- Các tác vụ cần cùng executor không thể bắt đầu.

### 6.2. Starvation hoặc deadlock ở tầng ứng dụng

Một lỗi thiết kế nghiêm trọng xảy ra khi thread đang chờ message cũng là thread cần thực hiện công việc tạo ra message đó.

Ví dụ, một executor chỉ có hai thread. Cả hai thread chạy tác vụ chờ kết quả JMS vô thời hạn. Hai tác vụ producer được submit vào cùng executor để tạo reply. Producer không có thread để chạy, còn consumer không có reply để kết thúc. Hệ thống rơi vào trạng thái starvation giống deadlock.

Cách khắc phục là tách công việc chờ khỏi executor xử lý producer, dùng listener bất đồng bộ hoặc giới hạn số tác vụ chờ đồng thời.

### 6.3. Giữ tài nguyên lâu hơn dự kiến

Trong một lần nhận đồng bộ, JmsTemplate cần tạo và sử dụng JMS consumer cùng session/connection resource tương ứng. Khi receive bị chặn, consumer và tài nguyên liên quan phải được giữ cho đến khi thao tác kết thúc. Pool connection hoặc session có giới hạn có thể bị chiếm hết nếu nhiều lời gọi cùng chờ.

### 6.4. Shutdown và triển khai lại khó khăn

Một worker chờ vô hạn có thể làm quá trình dừng ứng dụng kéo dài nếu vòng đời của tác vụ không có cách kết thúc rõ ràng. Các thread đang chờ có thể chưa trả lại tài nguyên, khiến shutdown hook hoặc executor phải chờ.

Nếu buộc phải dùng receive vô hạn cho một worker chuyên dụng, hãy thiết kế tín hiệu dừng, vòng đời consumer và cơ chế đóng tài nguyên. Với luồng polling, timeout hữu hạn giúp worker có cơ hội quay lại kiểm tra trạng thái dừng.

## 7. receiveTimeout của listener container là cấu hình khác

Spring JMS còn có receiveTimeout trên các listener container dựa trên polling, chẳng hạn DefaultMessageListenerContainer. Thuộc tính này có cùng tên nhưng có mục đích và mặc định riêng.

| Thành phần | Mặc định | Ý nghĩa của 0 | Ý nghĩa số âm |
| --- | --- | --- | --- |
| JmsTemplate | 0 | Chờ vô thời hạn | Không chờ |
| AbstractPollingMessageListenerContainer và DefaultMessageListenerContainer | 1000 ms | Chờ vô thời hạn; thường không nên dùng vì có thể cản trở shutdown sạch | Không chờ |

Với DefaultMessageListenerContainer, timeout là thời gian một lần polling chờ message trước khi vòng lặp tiếp tục. Mặc định một giây giúp container kiểm tra trạng thái, điều phối consumer và shutdown theo vòng polling.

Ví dụ cấu hình container trực tiếp:

~~~java
@Bean
public DefaultMessageListenerContainer ordersContainer(
        ConnectionFactory connectionFactory,
        Destination ordersQueue,
        MessageListener orderListener) {

    DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();

    container.setConnectionFactory(connectionFactory);
    container.setDestination(ordersQueue);
    container.setMessageListener(orderListener);
    container.setConcurrentConsumers(2);
    container.setReceiveTimeout(1_000);
    return container;
}
~~~

Ở đây receiveTimeout 1000 ms thuộc vòng polling của listener container. Container quản lý consumer và gọi listener khi message đến. Nó không phải timeout của một lời gọi JmsTemplate.receiveAndConvert trong service.

Không cấu hình receiveTimeout bằng 0 cho polling listener container một cách tùy tiện. Tài liệu Spring cảnh báo kiểu chờ vô hạn này có thể khiến container không shutdown sạch được, đặc biệt khi đang dùng transaction manager.

## 8. Khi nào nên dùng @JmsListener?

Nếu mục tiêu là xử lý message ngay khi broker giao đến, @JmsListener thường phù hợp hơn việc một service liên tục gọi receive.

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void handle(String orderId) {
        processOrder(orderId);
    }

    private void processOrder(String orderId) {
        System.out.println("Processing order: " + orderId);
    }
}
~~~

Spring tạo và quản lý listener container. Container nhận message bất đồng bộ rồi gọi phương thức handle. Thread ứng dụng không cần gọi receive và chờ message đến.

Cần lưu ý:

- Listener method vẫn chạy trên thread do container quản lý và chiếm thread trong lúc xử lý nghiệp vụ.
- Nếu listener chậm, số consumer/concurrency và khả năng xử lý phải được cấu hình phù hợp.
- Đảm bảo listener thread-safe khi có nhiều consumer.
- Cấu hình transaction, acknowledgement, retry và error handler theo yêu cầu.
- Không dùng receiveTimeout của JmsTemplate để điều khiển thời gian xử lý của @JmsListener.

## 9. Dùng timeout riêng cho từng loại công việc

JmsTemplate là thread-safe sau khi đã cấu hình xong. Vì vậy, hãy cấu hình receiveTimeout một lần khi tạo bean và dùng nhất quán. Không nên thay đổi setReceiveTimeout liên tục theo từng request trên một template được nhiều thread dùng chung, vì request khác có thể bị ảnh hưởng bởi giá trị mới.

Nếu ứng dụng có nhiều chính sách nhận, có thể:

- Tạo các JmsTemplate bean riêng, mỗi bean có receiveTimeout cố định.
- Dùng JmsClient của Spring Framework 7.0 nếu muốn API fluent với tùy chỉnh theo từng thao tác.
- Dùng một listener container cho luồng nhận bất đồng bộ và JmsTemplate cho các thao tác nhận đồng bộ có giới hạn.

Ví dụ hai template có chính sách khác nhau:

~~~java
@Bean
public JmsTemplate shortWaitTemplate(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setReceiveTimeout(500);
    return template;
}

@Bean
public JmsTemplate longWaitTemplate(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setReceiveTimeout(5_000);
    return template;
}
~~~

Cả hai template dùng chung ConnectionFactory nhưng mỗi template giữ timeout riêng. Đặt qualifier khi inject để tránh chọn nhầm bean.

## 10. Kiểm thử và quan sát receiveTimeout

Một số trường hợp cần kiểm thử:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Message có sẵn trước khi receive | Trả về message gần như ngay lập tức |
| Message đến trong thời gian timeout | Trả về message đó |
| Không có message đến trước timeout dương | Trả về null sau khi hết thời gian chờ |
| Timeout bằng 0 | Tiếp tục chờ cho đến khi có message hoặc consumer bị đóng |
| Timeout âm | Trả về ngay; null nếu không có message sẵn |
| Broker gặp lỗi | Spring ném JmsException phù hợp |
| Request/reply không có phản hồi | sendAndReceive trả về null khi timeout kết thúc |

Có thể đo thời gian thực tế bằng System.nanoTime trong test, nhưng không nên kiểm tra bằng điều kiện bằng tuyệt đối vì scheduler và môi trường chạy có sai số. Dùng khoảng dung sai hợp lý và broker test độc lập.

Các chỉ số nên theo dõi:

- Số lời gọi receive đang hoạt động và thời gian chờ trung bình.
- Số lần receive trả về null.
- Số thread đang bị block trong JMS receive.
- Số connection/session/consumer đang được mượn từ pool.
- Queue depth và tốc độ message đến.
- Thời gian xử lý listener, số lần retry và lỗi provider.

Nếu receiveTimeout hữu hạn nhưng receive vẫn chậm hơn dự kiến, kiểm tra cả độ trễ broker, network, connection pool và thread scheduling. Timeout của API là giới hạn chờ theo hợp đồng JMS; nó không loại bỏ thời gian thiết lập kết nối hoặc mọi độ trễ ở tầng ứng dụng.

## 11. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Ứng dụng treo khi queue rỗng | JmsTemplate mặc định chờ vô thời hạn | Đặt timeout dương hoặc chuyển sang @JmsListener |
| Nghĩ rằng timeout 0 là không chờ | Nhầm quy ước với API khác | Nhớ 0 là vô hạn; số âm mới là no-wait |
| Không nhận được message và kết quả là null | Hết timeout hoặc không có message sẵn | Xử lý null như kết quả hợp lệ |
| Request HTTP bị timeout nhưng thread vẫn bận | JMS receive đồng bộ vẫn đang chờ | Đặt timeout nằm trong request deadline hoặc dùng xử lý bất đồng bộ |
| Thread pool không chạy producer | Tất cả thread bị chiếm bởi consumer đang chờ | Tách executor hoặc dùng listener container |
| Polling tiêu tốn CPU | Vòng lặp receiveNoWait chạy liên tục | Thêm delay/backoff hoặc dùng scheduler |
| Listener container shutdown lâu | Polling receive chờ vô hạn | Giữ timeout hữu hạn; tránh 0 nếu không có lý do đặc biệt |
| Thay đổi timeout ảnh hưởng request khác | Mutate JmsTemplate dùng chung trong lúc chạy | Cấu hình bean riêng theo chính sách hoặc dùng API theo thao tác |
| Request/reply chờ lâu | sendAndReceive dùng cùng receiveTimeout của template | Cấu hình timeout phù hợp cho request/reply hoặc template riêng |

## 12. Checklist chọn receiveTimeout

- [ ] Xác định đang dùng JmsTemplate đồng bộ hay listener container polling.
- [ ] Ghi nhớ mặc định JmsTemplate là chờ vô thời hạn.
- [ ] Chọn số dương nếu cần giới hạn thời gian chờ.
- [ ] Dùng giá trị âm hoặc RECEIVE_TIMEOUT_NO_WAIT khi muốn kiểm tra ngay.
- [ ] Không dùng 0 cho polling listener container nếu chưa đánh giá ảnh hưởng shutdown.
- [ ] Xử lý null khi không có message trong thời hạn chờ.
- [ ] Đặt timeout trong ngân sách deadline của request hoặc job.
- [ ] Tránh chờ vô hạn trên servlet thread hoặc executor dùng chung với producer.
- [ ] Dùng @JmsListener cho xử lý message bất đồng bộ khi phù hợp.
- [ ] Cấu hình JmsTemplate một lần; không thay đổi timeout trên bean dùng chung theo từng request.
- [ ] Kiểm thử tình huống queue rỗng, message đến muộn, broker lỗi và shutdown.

## 13. Tài liệu tham khảo

- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework API — JmsTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Framework API — JmsDestinationAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/destination/JmsDestinationAccessor.html)
- [Spring Framework API — AbstractPollingMessageListenerContainer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/AbstractPollingMessageListenerContainer.html)
- [Spring Framework API — DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Jakarta Messaging API — MessageConsumer](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/MessageConsumer.html)
