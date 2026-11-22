# shutdownTimeout

Trong Spring Kafka, `shutdownTimeout` là khoảng thời gian listener container dành để chờ consumer dừng khi container được shutdown. Thuộc tính này ảnh hưởng trực tiếp đến quá trình dừng ứng dụng một cách có trật tự: consumer cần thoát khỏi vòng poll, hoàn tất phần xử lý đang chạy theo khả năng của ứng dụng và đóng tài nguyên Kafka.

Giá trị mặc định của `ContainerProperties.shutdownTimeout` là 10 giây. Có thể thay đổi bằng `setShutdownTimeout(long)`; đơn vị là millisecond. Giá trị cần đủ để consumer kết thúc trong điều kiện vận hành bình thường, nhưng phải được đặt cùng với thời gian xử lý listener, timeout của các dependency và giới hạn shutdown của nền tảng triển khai.

`shutdownTimeout` là thời gian chờ khi dừng container. Nó không phải timeout cho từng record, không giới hạn thời gian xử lý nghiệp vụ và không thay thế `max.poll.interval.ms`, `session.timeout.ms` hay transaction timeout.

## 1. Vì sao listener container cần thời gian shutdown?

Một listener container quản lý consumer thread, vòng poll, lời gọi listener và việc đóng Kafka consumer. Khi ứng dụng dừng, container cần đưa consumer ra khỏi vòng xử lý theo cách có kiểm soát. Nếu dừng process ngay khi listener đang thực hiện nghiệp vụ, ứng dụng có thể bỏ dở công việc hoặc chưa kịp hoàn tất các thao tác cần thiết.

Ví dụ, listener nhận một yêu cầu thanh toán và gọi service nội bộ. Khi ứng dụng nhận tín hiệu shutdown, listener có thể đang ở giữa lời gọi đó:

```text
Ứng dụng nhận tín hiệu shutdown
          |
          v
Listener container yêu cầu consumer dừng
          |
          v
Consumer ngừng nhận công việc mới
          |
          v
Listener đang chạy hoàn tất nếu có thể
          |
          v
Consumer đóng và container kết thúc
```

Container cần một khoảng thời gian để thực hiện quá trình này. `shutdownTimeout` cấu hình thời gian chờ cho bước dừng consumer. Nếu công việc đang chạy hoàn tất trong khoảng thời gian đó, việc đóng container có thể diễn ra gọn gàng. Nếu thời gian chờ hết trước khi consumer dừng, ứng dụng cần dự liệu rằng quá trình shutdown không hoàn tất theo thời gian mong muốn.

## 2. Giá trị mặc định và đơn vị

`ContainerProperties` có thuộc tính `shutdownTimeout`. Giá trị mặc định thông dụng là 10.000 millisecond, tương đương 10 giây. API setter nhận một số `long` tính bằng millisecond:

```java
factory.getContainerProperties().setShutdownTimeout(30_000L);
```

Đoạn code trên đặt thời gian chờ shutdown là 30 giây cho các listener container được tạo từ factory đó. Hãy ghi rõ đơn vị khi cấu hình để tránh nhầm giữa millisecond và second.

Không nên chọn một giá trị rất lớn chỉ để che giấu listener bị treo. `shutdownTimeout` cần phản ánh thời gian dừng hợp lý của hệ thống. Nếu listener thường xuyên cần vài phút để hoàn tất, hãy xem lại thời gian xử lý, cách gọi dependency và cách chia nhỏ công việc thay vì chỉ kéo dài thời gian chờ.

## 3. Cấu hình bằng listener container factory

Với ứng dụng dùng `ConcurrentKafkaListenerContainerFactory`, có thể đặt `shutdownTimeout` trên `ContainerProperties` của factory:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, Order> orderListenerFactory(
            ConsumerFactory<String, Order> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, Order>();
        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setShutdownTimeout(30_000L);
        return factory;
    }
}
```

Các listener sử dụng factory này sẽ nhận cấu hình container tương ứng:

```java
@KafkaListener(
        topics = "${app.topics.orders-in}",
        containerFactory = "orderListenerFactory")
public void onOrder(Order order) {
    orderService.process(order);
}
```

Nếu ứng dụng có nhiều factory, hãy đặt thời gian chờ phù hợp với loại công việc của từng nhóm listener. Một listener xử lý sự kiện nhẹ có thể dừng nhanh; một listener gọi hệ thống phụ thuộc chậm có thể cần ngân sách shutdown lớn hơn. Tránh tăng timeout cho mọi container nếu chỉ một nhóm listener có thời gian xử lý dài.

Có thể cấu hình container trực tiếp sau khi tạo thay vì đặt trên factory. Cách này hữu ích khi một listener cần chính sách riêng:

```java
MessageListenerContainer container =
        kafkaListenerEndpointRegistry.getListenerContainer("orders-listener");

if (container != null) {
    container.getContainerProperties().setShutdownTimeout(45_000L);
}
```

Trong ứng dụng thực tế, hãy thực hiện cấu hình trước khi container bắt đầu chạy. Không thay đổi thuộc tính giữa lúc shutdown đang diễn ra và mong lần dừng hiện tại sẽ tự nhận ngân sách mới.

## 4. shutdownTimeout tham gia vào quá trình dừng như thế nào?

Khi container được yêu cầu dừng, Spring Kafka yêu cầu consumer thoát khỏi hoạt động bình thường. Consumer có thể đang chờ trong `poll()` hoặc đang thực thi listener. Tùy trạng thái, container cần đánh thức vòng poll, chờ phần xử lý hiện tại kết thúc và đóng consumer.

Một chuỗi sự kiện điển hình:

1. Spring context hoặc ứng dụng yêu cầu listener container stop.
2. Container yêu cầu consumer thread dừng và đánh thức consumer nếu đang chờ poll.
3. Consumer không tiếp tục nhận công việc mới sau khi tiến trình dừng được xử lý.
4. Listener đang chạy có cơ hội kết thúc; container chờ consumer hoàn tất việc dừng trong giới hạn shutdown timeout.
5. Consumer được đóng và container hoàn tất quá trình stop.

`shutdownTimeout` là ngân sách chờ ở giai đoạn dừng consumer. Nó không tự ngắt một lời gọi HTTP đang treo, không hủy thread đang chạy nghiệp vụ và không thể buộc một database transaction hoàn tất. Nếu listener bị chặn vô thời hạn trong dependency, tăng `shutdownTimeout` chỉ khiến ứng dụng chờ lâu hơn; bản thân dependency vẫn cần timeout riêng.

## 5. Phân biệt với các timeout Kafka khác

Các timeout trong Kafka consumer và Spring Kafka giải quyết những vấn đề khác nhau. Đặt chúng lẫn lộn có thể khiến hệ thống shutdown không như dự kiến.

| Thuộc tính | Phạm vi | Câu hỏi nó trả lời |
|---|---|---|
| `shutdownTimeout` | Spring Kafka listener container khi stop | Container chờ consumer dừng trong bao lâu? |
| `max.poll.interval.ms` | Kafka consumer | Consumer được phép mất bao lâu giữa các lần gọi `poll()` trước khi bị xem là không còn tiến triển? |
| `session.timeout.ms` | Kafka consumer group membership | Broker chờ bao lâu khi không nhận heartbeat hợp lệ trước khi xem consumer đã mất? |
| `request.timeout.ms` | Kafka client request | Client chờ phản hồi cho một request broker trong bao lâu? |
| `transaction.timeout.ms` | Kafka transaction | Một transaction được phép mở trong bao lâu trước khi coordinator có thể timeout nó? |
| HTTP/database timeout | Client hoặc driver của dependency | Một lời gọi bên ngoài được phép chờ bao lâu? |

Ví dụ, tăng `shutdownTimeout` không làm tăng `max.poll.interval.ms`. Nếu listener xử lý một record quá lâu, consumer vẫn có thể vượt quá poll interval và bị group coordinator loại khỏi group trước khi ứng dụng bắt đầu shutdown.

Tương tự, `shutdownTimeout` không kéo dài transaction timeout. Nếu listener đang ở trong Kafka transaction và transaction vượt quá giới hạn broker, transaction có thể thất bại dù container vẫn còn thời gian chờ shutdown.

## 6. Chọn timeout theo thời gian xử lý thực tế

Hãy dựa vào thời gian xử lý quan sát được thay vì chọn một con số tùy ý. Xem xét:

- Thời gian listener cần để hoàn tất một record hoặc batch trong điều kiện tải bình thường.
- Thời gian tối đa mà các HTTP client, database driver và service phụ thuộc có thể chờ.
- Thời gian cần để producer flush hoặc hoàn tất Kafka transaction nếu listener có gửi output.
- Số lượng consumer thread và số listener đang hoạt động trong cùng ứng dụng.
- Ngân sách shutdown mà Spring Boot, process supervisor, container runtime hoặc orchestrator cấp.

Một cách ước lượng thực tế là đo thời gian từ lúc ứng dụng yêu cầu stop đến lúc listener container thực sự dừng trong các tình huống tải đại diện. Sau đó đặt `shutdownTimeout` đủ lớn cho phân vị thời gian dừng mà hệ thống cần hỗ trợ, đồng thời giữ giới hạn tổng shutdown trong ngân sách của nền tảng.

Ví dụ, nếu listener thông thường hoàn tất trong vài giây nhưng một số lần gọi dependency có thể mất tới 20 giây, timeout 30 giây có thể là điểm bắt đầu để kiểm thử. Con số cuối cùng cần dựa trên dữ liệu production và thời gian graceful shutdown mà môi trường triển khai cho phép.

Không cộng cơ học mọi timeout thành một giá trị duy nhất. Các thao tác có thể chạy tuần tự hoặc song song, và shutdown còn bao gồm lifecycle của những bean khác. Đo toàn bộ thời gian dừng ứng dụng giúp xác định ngân sách chính xác hơn.

## 7. Kết hợp với graceful shutdown của Spring Boot

Trong ứng dụng Spring Boot, listener container thường được quản lý bởi Spring context và `KafkaListenerEndpointRegistry`. Khi context đóng, lifecycle của container được gọi để dừng listener. `shutdownTimeout` tham gia vào quá trình dừng consumer của container.

Một số điều cần phối hợp:

- Spring Boot graceful shutdown cần được bật nếu ứng dụng muốn ngừng nhận request mới trong khi hoàn tất request HTTP đang chạy.
- Listener container Kafka có lifecycle riêng; graceful shutdown HTTP không tự thay thế việc dừng consumer.
- Các bean phụ thuộc mà listener cần phải còn hoạt động trong lúc listener hoàn tất. Nếu đóng database connection pool hoặc HTTP client quá sớm, listener có thể thất bại trong quá trình shutdown.
- Thời gian chờ của process supervisor hoặc container runtime phải đủ để Spring context hoàn tất shutdown.

Với một ứng dụng Spring Boot, có thể cấu hình graceful shutdown cho web server như sau:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s
```

Đây là cấu hình lifecycle tổng thể của Spring Boot. Nó không phải thuộc tính thay thế `ContainerProperties.shutdownTimeout`. Hãy phối hợp ngân sách lifecycle với timeout của listener container và các thành phần khác. Nếu timeout của phase ngắn hơn thời gian cần thiết để container dừng, Spring context có thể hết ngân sách trước khi listener hoàn tất.

## 8. Kubernetes và termination grace period

Trong Kubernetes, khi Pod bị xóa hoặc rollout, kubelet gửi tín hiệu `SIGTERM` tới container rồi chờ trong `terminationGracePeriodSeconds`. Nếu process chưa kết thúc khi grace period hết, kubelet có thể gửi `SIGKILL`.

Vì vậy, ngân sách shutdown của ứng dụng phải nằm trong thời gian Kubernetes cho phép. Nếu listener container cần 30 giây để dừng, nhưng Pod chỉ có 20 giây termination grace period, process có thể bị kết thúc trước khi listener hoàn tất. Khi đó `shutdownTimeout` không thể bảo vệ ứng dụng khỏi `SIGKILL`.

Ví dụ cấu hình minh họa:

```yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: order-worker
      image: example/order-worker:latest
```

Con số 60 giây chỉ là ví dụ. Cần đặt grace period đủ cho thời gian Spring context dừng, listener container chờ consumer, các tác vụ lifecycle khác và một khoảng dự phòng. Kiểm tra cả `preStop` hook nếu deployment dùng hook này vì thời gian chạy hook cũng tiêu thụ grace period.

Khi rollout, readiness và liveness probe có vai trò khác nhau. Readiness quyết định Pod còn nhận traffic hoặc được xem là sẵn sàng hay không; nó không thay thế tín hiệu dừng listener container. Với consumer Kafka, cần thiết kế rollout để consumer rời group có trật tự và instance còn lại có thể tiếp tục xử lý.

## 9. Listener xử lý lâu và tác động tới shutdown

Nếu listener thực hiện công việc dài, `shutdownTimeout` cần được xem cùng timeout của chính công việc đó. Ví dụ listener gọi một HTTP service không có timeout, nên khi service không phản hồi, consumer thread có thể bị giữ lại rất lâu.

Hãy đặt timeout hữu hạn cho các dependency:

```java
@Bean
RestClient paymentRestClient(RestClient.Builder builder) {
    var requestFactory = new SimpleClientHttpRequestFactory();
    requestFactory.setConnectTimeout(Duration.ofSeconds(3));
    requestFactory.setReadTimeout(Duration.ofSeconds(10));

    return builder
            .requestFactory(requestFactory)
            .build();
}
```

API cụ thể để cấu hình HTTP timeout tùy thuộc client và phiên bản Spring Framework đang dùng; ví dụ trên minh họa ý tưởng đặt connect/read timeout hữu hạn. Database query, lock wait và producer send cũng cần timeout phù hợp.

Với batch listener, thời gian xử lý có thể dài hơn record listener vì một lần gọi chứa nhiều record. Hãy đo thời gian cả batch và xác định cách xử lý khi shutdown đến giữa batch. Không acknowledge toàn batch trước khi các bước bắt buộc hoàn tất.

Nếu xử lý dài và không thể hoàn tất trong ngân sách shutdown, cân nhắc chia công việc thành các bước nhỏ, lưu tiến độ bền vững hoặc chuyển phần xử lý nặng sang một cơ chế worker riêng có idempotency. Không dựa vào việc kéo dài shutdown vô hạn.

## 10. Shutdown khi dùng manual acknowledgment

Với `AckMode.MANUAL` hoặc `MANUAL_IMMEDIATE`, listener quyết định thời điểm gọi `Acknowledgment.acknowledge()`. Nếu shutdown xảy ra trước khi listener acknowledge và offset chưa được commit, record có thể được giao lại sau restart hoặc rebalance.

Đây thường là hành vi an toàn theo hướng at-least-once: record có thể được xử lý lặp nhưng không bị bỏ qua chỉ vì listener chưa xác nhận. Để chịu được redelivery, nghiệp vụ cần idempotent hoặc có cơ chế deduplication.

Không gọi acknowledge chỉ để làm shutdown kết thúc nhanh nếu nghiệp vụ chưa thành công. Làm vậy có thể commit offset cho một record chưa được xử lý đầy đủ. `shutdownTimeout` không phải lý do để bỏ qua bước xác nhận đúng đắn.

Nếu listener chạy trong Kafka transaction, output và offset có thể được commit cùng nhau. Khi transaction chưa hoàn tất lúc shutdown, kết quả phụ thuộc vào trạng thái transaction và cách container dừng; transaction timeout vẫn có hiệu lực độc lập. Hãy kiểm thử shutdown khi transaction đang mở để xác nhận output và offset có semantics như mong đợi.

## 11. Quan sát và chẩn đoán shutdown chậm

Khi container dừng lâu hoặc không dừng trong timeout dự kiến, cần thu thập bằng chứng về consumer thread và listener đang thực hiện gì.

Theo dõi các tín hiệu sau:

- Thời gian từ lúc nhận SIGTERM hoặc lệnh stop đến khi container dừng hoàn toàn.
- Listener nào đang xử lý và thời gian xử lý của record/batch hiện tại.
- Timeout hoặc lỗi từ HTTP client, database, producer và transaction manager.
- Log của Spring Kafka về stop, consumer close, commit và rebalance.
- Thời gian shutdown của toàn Spring context so với `timeout-per-shutdown-phase`.
- Số lần Pod bị kết thúc bằng SIGKILL hoặc rollout vượt quá grace period.

Log nghiệp vụ nên có topic, partition, offset hoặc event ID để liên kết record đang xử lý với log shutdown. Tránh ghi payload nhạy cảm. Nếu cần điều tra thread bị treo, thread dump trong thời điểm shutdown có thể cho biết consumer thread đang chờ ở HTTP client, JDBC driver, lock hay đoạn code ứng dụng.

Nếu shutdown timeout thường xuyên hết hạn, hãy tìm nguyên nhân thực tế trước khi tăng giá trị. Một timeout tăng lên có thể giảm cảnh báo trong ngắn hạn nhưng đồng thời kéo dài thời gian rollout và làm chậm việc thay thế instance lỗi.

## 12. Kiểm thử shutdownTimeout

Kiểm thử tích hợp giúp xác nhận container có dừng trong ngân sách đã đặt và record đang xử lý có hành vi mong đợi. Có thể dùng Embedded Kafka hoặc Kafka Testcontainers cùng listener container thật.

Các tình huống nên kiểm tra:

1. Listener xử lý nhanh; yêu cầu stop và xác nhận container dừng bình thường.
2. Listener đang xử lý một record trong thời gian có kiểm soát; yêu cầu stop và quan sát thời gian container kết thúc.
3. Listener bị chặn bởi dependency; xác nhận timeout của dependency giải phóng listener trước khi shutdown budget cạn.
4. Listener chưa acknowledge; dừng ứng dụng rồi khởi động lại và xác nhận record có thể được giao lại.
5. Listener đã acknowledge; xác nhận consumer group tiếp tục từ offset đã commit.
6. Với Kafka transaction, yêu cầu shutdown khi transaction đang mở và xác nhận output/offset theo trạng thái commit hoặc abort thực tế.
7. Chạy ứng dụng trong container với grace period tương đương môi trường triển khai và xác nhận process kết thúc trước khi hết thời gian.

Không dùng sleep cố định để kết luận container đã dừng. Hãy chờ callback stop, trạng thái container hoặc tín hiệu lifecycle cụ thể với timeout hữu hạn. Dọn topic, consumer group và executor sau test để tránh thread còn chạy ảnh hưởng các bài test khác.

## 13. Lỗi cấu hình thường gặp

- **Nhầm `shutdownTimeout` với timeout xử lý record:** thuộc tính này phục vụ shutdown container, không đặt giới hạn cho nghiệp vụ.
- **Chỉ tăng `shutdownTimeout` khi listener bị treo:** dependency vẫn có thể chờ vô hạn nếu không có timeout riêng.
- **Đặt timeout dài hơn termination grace period:** Kubernetes có thể gửi SIGKILL trước khi ứng dụng hoàn tất shutdown.
- **Đóng dependency quá sớm:** listener đang hoàn tất nhưng database hoặc HTTP client đã bị đóng.
- **Acknowledge trước khi xử lý xong để tránh redelivery:** offset có thể commit dù nghiệp vụ chưa thành công.
- **Bỏ qua transaction timeout:** Kafka transaction có thể timeout dù container vẫn đang chờ shutdown.
- **Không đo thời gian shutdown thực tế:** giá trị cấu hình không phản ánh thời gian dừng của toàn ứng dụng.
- **Dùng một timeout cho mọi loại listener:** các nhóm listener có thời gian xử lý và yêu cầu shutdown khác nhau.

## 14. Cách chọn shutdownTimeout cho production

Khi triển khai, hãy xác định thời gian xử lý dài nhất có thể chấp nhận, đặt timeout cho các dependency, đo thời gian dừng consumer và phối hợp ngân sách với Spring lifecycle cùng orchestrator. Bắt đầu từ giá trị mặc định 10 giây nếu workload dừng nhanh, sau đó điều chỉnh bằng số liệu quan sát được.

Một cấu hình nhất quán cần trả lời được:

- Container được yêu cầu dừng bằng cách nào và ai quản lý lifecycle của nó?
- Listener có thể đang xử lý record hoặc batch trong bao lâu?
- Các lời gọi HTTP, database và producer có timeout hữu hạn không?
- Nếu listener chưa acknowledge khi process dừng, record sẽ được giao lại và xử lý idempotent như thế nào?
- Spring lifecycle có đủ thời gian cho listener container dừng không?
- Container runtime hoặc Kubernetes có cho process đủ thời gian trước khi gửi SIGKILL không?

`shutdownTimeout` phát huy tác dụng khi nó là một phần của kế hoạch graceful shutdown hoàn chỉnh. Nó cung cấp thời gian để listener container dừng consumer có trật tự; chất lượng của quá trình dừng còn phụ thuộc vào listener có thể kết thúc hay không, dependency có timeout hay không, offset được xác nhận ở thời điểm nào và nền tảng có cấp đủ thời gian cho ứng dụng kết thúc hay không.
