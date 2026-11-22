# stopImmediate

Trong Spring Kafka, listener container quản lý vòng đời consumer: poll record, gọi listener, xử lý acknowledgment và commit offset. Khi ứng dụng yêu cầu dừng container, hệ thống cần quyết định có xử lý hết các record đã lấy về trong poll hiện tại hay dừng ngay sau record đang được xử lý. Thuộc tính **stopImmediate** điều khiển ranh giới dừng này.

Mặc định, container thường hoàn tất các record còn lại trong kết quả poll hiện tại trước khi dừng. Khi bật stopImmediate, container dừng sau khi xử lý xong record hiện tại. Điều này giúp rút ngắn thời gian dừng khi triển khai phiên bản mới, bảo trì hoặc thu hồi consumer. Đổi lại, những record còn lại trong poll chưa được listener xử lý có thể được giao lại khi consumer group tiếp tục hoạt động.

stopImmediate không hủy ngang một lời gọi listener đang chạy, không rollback side effect đã thực hiện và không thay thế chính sách commit offset. Muốn dừng an toàn, cần hiểu rõ điểm dừng, AckMode, cách listener xử lý record và thời gian shutdown của ứng dụng.

## 1. stopImmediate giải quyết điều gì?

Kafka consumer lấy record bằng poll(). Một lần poll có thể trả về nhiều record từ một hoặc nhiều partition. Với record listener, Spring Kafka gọi listener lần lượt cho từng record trong kết quả poll. Khi có yêu cầu stop, container cần quyết định xử lý bao nhiêu record nữa trước khi kết thúc vòng lặp.

- **stopImmediate=false:** container xử lý các record còn lại trong kết quả poll hiện tại rồi mới dừng theo hành vi mặc định.
- **stopImmediate=true:** container dừng sau khi record đang được xử lý hoàn tất; những record tiếp theo trong kết quả poll hiện tại không được gọi tới listener trong vòng đời container đó.

Ví dụ một poll trả về năm record:

    Poll trả về:  A  B  C  D  E
    Listener đang xử lý: C
    Có yêu cầu stop()

    stopImmediate=false:
        Hoàn tất C -> xử lý D -> xử lý E -> dừng

    stopImmediate=true:
        Hoàn tất C -> dừng
        D và E chưa được listener xử lý trong lượt chạy này

Giá trị này kiểm soát thời điểm container ngừng dispatch record cho listener. Nó không phải một lệnh hủy thread và không làm cho một record đang chạy biến mất. Nếu listener đang gọi database hoặc HTTP service, container phải chờ lời gọi đó trả về hoặc ném exception trước khi có thể hoàn tất record hiện tại.

## 2. Ranh giới dừng và vòng đời record

Một record thường đi qua các bước:

1. Consumer poll record từ broker.
2. Container chuyển record cho listener.
3. Listener thực hiện xử lý nghiệp vụ.
4. Listener hoàn tất bình thường hoặc ném exception.
5. Container áp dụng chính sách error handler và acknowledgment/commit tương ứng.
6. Container kiểm tra trạng thái chạy và tiếp tục record kế tiếp hoặc dừng.

Khi stopImmediate được bật, ranh giới dừng nằm sau record hiện tại. Điều này có nghĩa container không chủ động ngắt giữa các câu lệnh trong listener. Nếu listener đã bắt đầu xử lý record C, listener phải tự hoàn tất hoặc thất bại theo logic của nó.

Ví dụ:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders",
    groupId = "order-service"
)
public void consume(OrderEvent event) {
    orderService.process(event);
    auditService.recordProcessed(event.eventId());
}
~~~

Nếu container nhận lệnh dừng trong lúc consume() đang chạy, stopImmediate không xóa lời gọi auditService hoặc dừng thread giữa hai dòng. Container đợi listener kết thúc, sau đó dừng trước khi gọi listener cho record tiếp theo.

Nếu process() đã commit database nhưng auditService thất bại, record có thể bị xem là thất bại tùy exception và error handler. Khi record được giao lại, process() có thể chạy lần nữa. Listener nên có idempotency cho side effect để tránh cập nhật nghiệp vụ hai lần.

## 3. Cấu hình stopImmediate trên listener container

Cách trực tiếp là cấu hình ContainerProperties của factory trước khi tạo container:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);

    ContainerProperties properties = factory.getContainerProperties();
    properties.setStopImmediate(true);
    properties.setAckMode(ContainerProperties.AckMode.RECORD);

    return factory;
}
~~~

Listener có thể chọn factory bằng thuộc tính containerFactory:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders",
    groupId = "order-service",
    containerFactory = "ordersKafkaListenerContainerFactory"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Đặt stopImmediate trên ContainerProperties giúp các container được tạo từ factory sử dụng cùng chính sách. Nếu chỉ muốn áp dụng cho một listener, hãy cấu hình factory riêng hoặc tùy chỉnh container tương ứng theo cách mà phiên bản Spring Kafka của dự án hỗ trợ.

Không nên đặt cấu hình sau khi container đã chạy rồi giả định nó thay đổi ngay ranh giới dừng của một lần poll đang diễn ra. Hãy cấu hình trước khi start và kiểm tra hành vi trong môi trường tích hợp.

### 3.1. Cấu hình shutdown timeout

stopImmediate điều khiển số record tiếp tục được dispatch sau khi có yêu cầu dừng. shutdownTimeout điều khiển thời gian container chờ quá trình dừng hoàn tất trong lúc shutdown. Hai thuộc tính giải quyết hai vấn đề khác nhau.

~~~java
ContainerProperties properties = factory.getContainerProperties();

properties.setStopImmediate(true);
properties.setShutdownTimeout(15_000L);
~~~

Giá trị shutdown timeout được tính theo milliseconds trong API này. Chọn timeout dựa trên thời gian tối đa mà listener cần để hoàn tất một record, cộng thêm thời gian commit offset và đóng consumer. Timeout quá ngắn có thể khiến tiến trình bị kết thúc khi listener vẫn đang xử lý; timeout quá dài có thể làm rollout hoặc shutdown kéo dài.

Hãy phối hợp timeout của container với thời gian graceful shutdown của Spring Boot, thời gian termination grace period của nền tảng triển khai và timeout của các dịch vụ phụ thuộc. Nếu orchestrator buộc kết thúc process trước khi container hoàn tất, listener có thể bị ngắt dù stopImmediate đã bật.

## 4. Dừng container bằng KafkaListenerEndpointRegistry

Với listener khai báo bằng @KafkaListener, Spring Kafka đăng ký container vào KafkaListenerEndpointRegistry. Ứng dụng có thể tìm container theo id rồi yêu cầu dừng.

~~~java
@Component
public class ListenerControlService {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerControlService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void stopOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container != null && container.isRunning()) {
            container.stop();
        }
    }
}
~~~

id truyền vào getListenerContainer() phải khớp với id của @KafkaListener. Nếu không đặt id rõ ràng, Spring Kafka có thể tạo id mặc định; dùng id tường minh giúp thao tác vận hành dễ kiểm soát hơn.

stop() yêu cầu container dừng. Khi stopImmediate=true, container áp dụng ranh giới dừng sau record hiện tại. Không nên gọi stop() từ chính listener thread nếu thao tác đó làm luồng điều khiển tự chờ chính nó hoàn tất. Với yêu cầu điều khiển từ endpoint quản trị hoặc một service khác, hãy thực hiện trên thread phù hợp và bảo vệ endpoint bằng cơ chế xác thực, phân quyền của ứng dụng.

Có thể dùng callback của lifecycle khi cần biết container đã dừng:

~~~java
container.stop(() -> {
    log.info("Orders listener has stopped");
});
~~~

Callback cho biết quá trình dừng của container đã hoàn tất theo lifecycle contract. Nó không chứng minh toàn bộ nghiệp vụ ngoài Kafka đã hoàn thành nếu listener tự khởi chạy công việc bất đồng bộ rồi trả về sớm.

## 5. Ảnh hưởng tới offset và acknowledgment

stopImmediate không tự quyết định offset nào được commit. Offset commit phụ thuộc AckMode, transaction, listener đã hoàn tất record nào và thời điểm container xử lý acknowledgment.

Ví dụ với AckMode.RECORD:

~~~java
ContainerProperties properties = factory.getContainerProperties();
properties.setAckMode(ContainerProperties.AckMode.RECORD);
properties.setStopImmediate(true);
~~~

Khi listener hoàn tất record C thành công, container có thể commit offset của record đó theo chế độ commit đang cấu hình. Các record D và E chưa được xử lý sẽ không được xác nhận như các record thành công chỉ vì chúng đã được poll. Khi consumer group khởi động lại, những record chưa được commit có thể được giao lại.

Với AckMode.BATCH, container commit theo batch poll sau khi batch được xử lý thành công. Nếu muốn dừng giữa kết quả poll mà vẫn cần tiến độ offset chính xác, hãy xác định cách phiên bản Spring Kafka và listener type xử lý commit cho các record đã được xử lý. Không giả định rằng bật stopImmediate tự biến mọi chế độ BATCH thành RECORD.

Một số điểm cần nhớ:

- Record đã xử lý thành công nhưng chưa commit có thể được giao lại.
- Record chưa được listener xử lý không được xem là đã hoàn tất chỉ vì consumer đã poll nó.
- Commit offset trước khi side effect bền vững có thể làm mất tác vụ.
- Side effect hoàn tất nhưng offset chưa commit có thể tạo duplicate khi record được giao lại.
- Manual acknowledgment phải được gọi sau khi xử lý nghiệp vụ thành công.

Với listener ghi database, một mẫu thường dùng là ghi thay đổi nghiệp vụ và dấu mốc eventId trong cùng transaction database, sau đó để container commit offset. Nếu process dừng giữa database commit và offset commit, lần giao lại sẽ gặp eventId đã xử lý và có thể bỏ qua side effect trùng.

## 6. stopImmediate với record listener và batch listener

### 6.1. Record listener

Record listener nhận từng ConsumerRecord hoặc payload tương ứng. Container điều khiển việc gọi listener cho từng record trong kết quả poll. Đây là trường hợp dễ hình dung nhất: khi stopImmediate=true, container hoàn tất record hiện tại rồi dừng trước khi gọi listener cho record tiếp theo.

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void consume(ConsumerRecord<String, OrderEvent> record) {
    orderService.process(record.value());
}
~~~

Nếu poll trả về nhiều record, container có thể chỉ xử lý một phần kết quả poll khi có yêu cầu stop. Các record chưa xử lý sẽ được đọc lại theo committed offset sau khi consumer group tiếp tục.

### 6.2. Batch listener

Batch listener nhận một danh sách record trong một lần gọi:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-service",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void consume(List<ConsumerRecord<String, OrderEvent>> records) {
    orderService.processBatch(records);
}
~~~

Với batch listener, ứng dụng nhận cả batch trong một invocation. Không nên giả định container có thể dừng giữa các câu lệnh của processBatch() hoặc hủy một phần công việc trong method. stopImmediate là chính sách dừng của container; nó không phải API hủy batch callback đang chạy.

Nếu cần dừng sau từng record, cân nhắc dùng record listener. Nếu phải dùng batch listener, hãy thiết kế xử lý batch có thể kiểm soát tiến độ, transaction và lỗi từng record theo API batch listener đang sử dụng. Xác nhận hành vi thực tế với phiên bản Spring Kafka của ứng dụng.

### 6.3. Listener chuyển công việc sang executor

Một lỗi thiết kế thường gặp là listener khởi chạy công việc nền rồi trả về ngay:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void consume(OrderEvent event) {
    executor.submit(() -> orderService.process(event));
}
~~~

Container có thể xem listener đã hoàn tất ngay sau khi submit task. Nếu offset được commit sau đó, record có thể được xác nhận trong khi công việc nền chưa hoàn tất. stopImmediate chỉ chờ listener method kết thúc; nó không tự chờ task do ứng dụng submit sang executor.

Nếu xử lý bất đồng bộ, cần phối hợp acknowledgment với completion của task. Có thể dùng async acknowledgment được hỗ trợ ở phiên bản Spring Kafka tương ứng, hoặc giữ listener invocation chưa hoàn tất cho tới khi future hoàn thành. Không commit offset chỉ vì task đã được đưa vào hàng đợi.

## 7. stopImmediate không phải pauseImmediate

Spring Kafka có các cơ chế pause và stop phục vụ mục đích khác nhau.

| Cơ chế | Mục đích | Hành vi |
|---|---|---|
| stopImmediate | Dừng container sớm | Dừng sau khi record hiện tại hoàn tất |
| stopImmediate=false | Dừng theo ranh giới poll mặc định | Xử lý các record còn lại trong poll trước khi dừng |
| pause | Tạm ngừng lấy thêm record | Container vẫn tồn tại và có thể tiếp tục sau resume |
| pauseImmediate | Điều khiển thời điểm pause | Có thể pause sau record hiện tại thay vì chờ hết poll |
| shutdown | Kết thúc ứng dụng/container | Thực hiện lifecycle stop và đóng tài nguyên |

Pause phù hợp khi cần giảm tải tạm thời hoặc chờ một dịch vụ phụ thuộc phục hồi mà không rời consumer group theo cách stop container. Stop phù hợp khi cần loại consumer khỏi hoạt động, triển khai phiên bản mới hoặc đóng ứng dụng.

stopImmediate không thay thế pauseImmediate. Một container đã stop cần được start lại theo lifecycle để tiêu thụ tiếp; một container được pause có thể resume mà không cần tạo lại toàn bộ vòng đời.

## 8. Tác động đến thứ tự và duplicate

Khi stopImmediate dừng sau record C trong một poll, record D và E có thể được giao lại khi consumer group khởi động tiếp. Điều này là hành vi bình thường của at-least-once nếu offset chưa được commit vượt qua chúng.

Ví dụ:

    Partition orders-0
    Offset:     20    21    22    23    24
    Record:      A     B     C     D     E

    Container xử lý A, B, C
    stopImmediate=true
    Container dừng sau C

Nếu offset 23 đã được commit, lần chạy tiếp theo bắt đầu từ D. Nếu offset chỉ mới commit tới 22, consumer có thể đọc lại C rồi D và E. Nếu offset đã bị commit sai tới 25, D và E có thể bị bỏ qua. Vì vậy, hãy kiểm tra AckMode và ranh giới commit khi thử nghiệm dừng giữa poll.

Duplicate thường xuất hiện khi listener hoàn tất side effect nhưng offset chưa được commit. Để xử lý an toàn:

- Dùng eventId ổn định trong payload hoặc header.
- Lưu dấu mốc đã xử lý trong cùng transaction với cập nhật nghiệp vụ.
- Dùng unique constraint hoặc upsert có điều kiện.
- Giữ thao tác gọi dịch vụ bên ngoài idempotent bằng idempotency key.
- Tránh tạo eventId mới khi record được retry hoặc re-drive.

Với thứ tự theo key, Kafka vẫn giữ thứ tự record trong một partition, nhưng việc giao lại có thể làm một record đã xử lý trước đó xuất hiện lần nữa. Idempotency và version của aggregate giúp tránh tác động lặp hoặc cập nhật trạng thái cũ.

## 9. Ảnh hưởng tới rebalance và triển khai rolling

Khi container dừng, consumer rời group hoặc đóng consumer, các partition có thể được phân công cho consumer khác. stopImmediate giảm số record mà instance cũ tiếp tục xử lý sau khi nhận lệnh stop. Điều này hữu ích trong rolling deployment vì instance mới có thể bắt đầu xử lý sớm hơn.

Tuy nhiên, không nên dừng tất cả instance cùng lúc nếu hệ thống cần duy trì năng lực xử lý. Trong triển khai rolling:

1. Chọn một instance để dừng.
2. Yêu cầu listener container dừng.
3. Chờ record hiện tại hoàn tất và container báo stopped.
4. Để group rebalance và instance còn lại tiếp nhận partition.
5. Khởi động phiên bản mới.
6. Theo dõi lag, lỗi và tỷ lệ duplicate sau khi rollout.

Nếu có nhiều concurrent child containers, dừng một ConcurrentMessageListenerContainer có thể điều khiển các child container theo lifecycle. Hãy kiểm tra trạng thái toàn bộ container và số consumer còn hoạt động trước khi tiếp tục rollout.

stopImmediate giảm thời gian drain poll hiện tại, nhưng không loại bỏ thời gian xử lý record đang chạy, commit offset, đóng network client hoặc rebalance. Hãy đo thời gian thực tế thay vì xem đây là bảo đảm shutdown tức thời.

## 10. Kết hợp stopImmediate với error handler

Nếu listener ném exception, error handler có thể retry record, recover hoặc chuyển record sang DLT. stopImmediate xử lý vòng đời dừng container, còn error handler xử lý lỗi của record. Hai cơ chế có thể tương tác tại thời điểm dừng.

Ví dụ record listener với error handler:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> template) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(template);

    return new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );
}
~~~

Nếu container đang dừng trong lúc error handler retry, thời điểm kết thúc phụ thuộc cách container xử lý record hiện tại và cấu hình retry/backoff. Không giả định stopImmediate sẽ bỏ qua error handler hoặc cắt ngắn một lần xử lý đang chạy.

Với retry có backoff dài, việc dừng có thể kéo dài theo chính sách xử lý record hiện tại. Hãy cân nhắc số lần retry, thời gian backoff, DLT và thời gian shutdown cho phép. Nếu record lỗi không thể phục hồi ngay, chuyển DLT có thể phù hợp hơn việc giữ container trong retry kéo dài, nhưng cần bảo đảm publish DLT thành công trước khi xem record gốc là đã được recover.

## 11. Kiểm soát thời gian listener đang chạy

stopImmediate chỉ có hiệu quả rõ ràng khi listener hoàn tất trong khoảng thời gian có giới hạn. Nếu listener gọi dịch vụ không có timeout, quá trình stop có thể chờ vô thời hạn hoặc tới khi shutdown timeout của container hết hạn.

Các biện pháp nên áp dụng:

- Đặt connect timeout và read timeout cho HTTP client.
- Đặt query timeout và transaction timeout cho database.
- Giới hạn thời gian retry trong listener.
- Không chờ future vô thời hạn bằng join() hoặc get() không timeout.
- Theo dõi thời gian xử lý p50, p95 và p99 của record.
- Đặt shutdown timeout đủ lớn để hoàn tất công việc hợp lệ.
- Phối hợp termination grace period của nền tảng triển khai với thời gian dừng container.

Ví dụ chờ future có timeout:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void consume(OrderEvent event) {
    try {
        orderService.processAsync(event)
                .get(20, TimeUnit.SECONDS);
    }
    catch (InterruptedException exception) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Interrupted while processing order", exception);
    }
    catch (ExecutionException | TimeoutException exception) {
        throw new IllegalStateException("Order processing failed", exception);
    }
}
~~~

Ví dụ này giữ listener invocation mở cho tới khi future hoàn tất hoặc timeout. Khi timeout, ứng dụng vẫn cần xử lý trường hợp task nền có thể tiếp tục chạy và tạo side effect sau khi listener đã báo lỗi. Dùng cancellation nếu dịch vụ hỗ trợ, đồng thời bảo đảm thao tác nghiệp vụ idempotent.

## 12. Các tình huống nên bật stopImmediate

| Tình huống | Lợi ích | Điều cần kiểm soát |
|---|---|---|
| Rolling deployment | Instance cũ dừng sớm sau record hiện tại | Instance mới và group cần tiếp nhận partition |
| Bảo trì một listener | Giảm lượng record xử lý thêm sau yêu cầu stop | Offset của record chưa xử lý phải còn an toàn |
| Shutdown ứng dụng | Giảm thời gian drain các record đã poll | Listener hiện tại phải có timeout hợp lý |
| Thay đổi cấu hình consumer | Dừng vòng lặp cũ nhanh hơn trước khi tạo lại container | Kiểm soát rebalance và duplicate |
| Dừng theo lệnh quản trị | Phản hồi nhanh hơn khi cần ngừng một consumer | Bảo vệ endpoint điều khiển và theo dõi lifecycle |

Không nhất thiết bật stopImmediate cho mọi listener. Nếu poll batch nhỏ và xử lý nhanh, hành vi mặc định có thể đơn giản hơn. Nếu listener xử lý batch cần hoàn tất cả nhóm record cùng nhau, hãy cân nhắc thiết kế batch và transaction trước khi bật chế độ dừng sớm.

## 13. Quan sát hoạt động dừng

Để xác nhận stopImmediate đang tạo hành vi mong muốn, nên ghi nhận các sự kiện lifecycle và tiến độ record:

- Thời điểm nhận yêu cầu stop.
- Container id, listener id và consumer group.
- Record đang xử lý khi nhận yêu cầu stop.
- Thời điểm listener hiện tại hoàn tất.
- Offset cuối cùng đã commit theo từng partition.
- Số record được poll nhưng chưa được listener xử lý.
- Thời điểm container báo stopped.
- Thời gian shutdown thực tế.
- Số record được giao lại sau khi instance mới nhận partition.

Log nên chứa topic, partition, offset, key hoặc eventId. Tránh ghi payload nhạy cảm. Kết hợp log producer, consumer và kết quả nghiệp vụ để phân biệt record được giao lại với một event mới.

Các metric hữu ích gồm consumer lag, processing duration, rebalance count, commit latency, listener error rate và thời gian stop container. Nếu stop nhanh nhưng consumer lag tăng mạnh hoặc record bị xử lý lặp nhiều, cần xem lại batch size, AckMode và idempotency.

## 14. Kiểm thử stopImmediate

Một kiểm thử tích hợp nên tạo nhiều record trong cùng partition, bắt đầu tiêu thụ và yêu cầu stop khi listener đang xử lý một record đã biết.

Kịch bản:

1. Gửi các record A, B, C, D, E tới cùng partition.
2. Dùng record listener có một latch để giữ record C trong lúc xử lý.
3. Đợi listener bắt đầu xử lý C.
4. Gọi stop() trên container.
5. Giải phóng latch để C hoàn tất.
6. Chờ container báo stopped.
7. Kiểm tra log listener: với stopImmediate=true, D và E không được gọi trong vòng đời container cũ.
8. Khởi động lại container hoặc một consumer cùng group.
9. Xác nhận D và E được giao lại nếu offset chưa commit vượt qua chúng.
10. Xác nhận side effect của C không bị nhân đôi khi C được giao lại trong trường hợp commit chưa hoàn tất.

Chạy lại kịch bản với stopImmediate=false để so sánh: container xử lý các record còn lại trong poll trước khi dừng theo hành vi mặc định.

Nên bổ sung các trường hợp:

- Listener hiện tại ném exception khi đang dừng.
- Error handler đang thực hiện retry/backoff.
- Listener dùng AckMode.RECORD và BATCH.
- Listener dùng manual acknowledgment.
- Batch listener nhận nhiều record trong một invocation.
- Listener offload task sang executor.
- Container có concurrency lớn hơn một.
- Ứng dụng shutdown trong lúc listener gọi dịch vụ chậm.
- Commit offset thất bại hoặc group rebalance xảy ra gần thời điểm stop.

Các kiểm thử này xác nhận ranh giới dừng và khả năng giao lại record theo cấu hình thực tế. Chỉ kiểm tra container đã dừng là chưa đủ; cần kiểm tra cả offset và kết quả nghiệp vụ.

## 15. Các lỗi vận hành thường gặp

| Cách hiểu hoặc cách làm | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ stopImmediate hủy listener hiện tại | Có thể để lại side effect dở dang | Thiết kế listener có timeout và hoàn tất record hiện tại |
| Bật stopImmediate rồi commit toàn bộ poll | Có thể bỏ qua record chưa xử lý | Chọn AckMode và commit offset theo record đã hoàn tất |
| Coi stopImmediate là pause | Container đã dừng, cần start lại | Dùng pause/resume khi chỉ muốn tạm ngừng |
| Gọi stop từ listener thread và chờ chính nó | Có nguy cơ chặn lifecycle hoặc deadlock | Điều khiển container từ thread quản trị phù hợp |
| Listener submit task rồi trả về | Container có thể commit trước khi task xong | Phối hợp acknowledgment với completion của task |
| Dùng batch listener nhưng kỳ vọng dừng giữa method | Batch callback không bị container hủy giữa câu lệnh | Dùng record listener hoặc thiết kế batch có checkpoint |
| Shutdown timeout quá ngắn | Process có thể kết thúc khi record chưa hoàn tất | Đồng bộ timeout container và nền tảng triển khai |
| Không kiểm tra offset sau rollout | Không phát hiện mất hoặc phát lại record | Theo dõi commit và kiểm thử restart/rebalance |
| Cho rằng stop nhanh đồng nghĩa không duplicate | Record đã xử lý nhưng chưa commit vẫn có thể được giao lại | Consumer idempotent theo eventId |

## 16. Nguyên tắc lựa chọn trong production

- Dùng stopImmediate khi cần dừng listener sau record đang chạy và giảm thời gian xử lý phần còn lại của poll.
- Giữ listener hiện tại có thời gian xử lý hữu hạn; stopImmediate không ngắt một lời gọi đang chạy.
- Cấu hình AckMode phù hợp với ranh giới side effect và offset commit.
- Với record listener, xác nhận record chưa xử lý không bị commit vượt qua.
- Với batch listener, không giả định container có thể hủy một phần invocation.
- Nếu listener chạy task bất đồng bộ, chỉ acknowledge sau khi task hoàn tất bền vững.
- Phân biệt stop, pause, pauseImmediate và shutdown.
- Phối hợp shutdownTimeout với timeout của listener và termination grace period.
- Theo dõi lifecycle, commit, lag, rebalance và record được giao lại.
- Kiểm thử stop giữa poll, lỗi listener và shutdown trước khi áp dụng rollout production.

stopImmediate cho phép Spring Kafka listener container kết thúc sau record hiện tại thay vì tiếp tục dispatch toàn bộ record còn lại của poll. Giá trị của nó nằm ở việc kiểm soát thời điểm dừng trong khi vẫn giữ ranh giới xử lý record rõ ràng. Khi phối hợp đúng với acknowledgment, offset commit, timeout và idempotency, ứng dụng có thể triển khai hoặc shutdown nhanh hơn mà vẫn phục hồi an toàn các record chưa được xử lý.