# ConsumerSeekAware.onIdleContainer

Trong Spring Kafka, **ConsumerSeekAware.onIdleContainer** là một callback cho phép listener nhận biết thời điểm **listener container ở trạng thái idle** và thực hiện thao tác **seek** trên những Kafka partitions mà consumer đang được giao. Callback này hữu ích khi ứng dụng có yêu cầu **đọc lại dữ liệu từ một checkpoint, thực hiện replay có kiểm soát hoặc đổi vị trí đọc khi không còn records mới được giao**.

Một điểm rất dễ nhầm: **idle không có nghĩa consumer bị treo**. Listener container có thể vẫn poll Kafka bình thường nhưng chưa nhận record nào trong khoảng thời gian được cấu hình. Ngược lại, một consumer bị kẹt trong xử lý hoặc không gọi poll có thể cần được phát hiện bởi cơ chế **NonResponsiveConsumerEvent**, không phải dựa vào onIdleContainer.

Callback onIdleContainer cũng không phải một yêu cầu tự động seek về đầu topic. **Spring Kafka không tự rewind offset chỉ vì consumer idle.** Ứng dụng chỉ thay đổi vị trí đọc khi chủ động gọi một phương thức trên **ConsumerSeekCallback**. Quyết định seek phải xem xét committed offset, retention, retry, idempotency, partition ownership và tác động đến consumer group đang chạy production.

## 1. ConsumerSeekAware giải quyết nhu cầu gì?

KafkaConsumer đọc records theo vị trí hiện tại của từng TopicPartition. Trong một số ứng dụng, listener cần điều khiển vị trí đọc một cách chủ động thay vì luôn tiếp tục từ vị trí kế tiếp:

- Tái xử lý một khoảng dữ liệu lịch sử sau khi sửa business logic.
- Chạy lại một event đã xử lý trước đó để xây dựng lại projection.
- Tiếp tục đọc từ checkpoint do ứng dụng lưu bên ngoài Kafka.
- Nhảy tới vị trí chỉ định của một partition khi có thao tác vận hành được phê duyệt.
- Thực hiện điều chỉnh vị trí đọc khi listener đang idle để giảm khả năng làm gián đoạn một callback xử lý record đồng bộ.

Spring Kafka cung cấp interface **ConsumerSeekAware** để listener có thể nhận các lifecycle callbacks và một **ConsumerSeekCallback** an toàn trong ngữ cảnh mà framework quản lý.

~~~text
Kafka topic orders.events
          |
          v
Listener container
          |
          +-- poll records
          +-- dispatch @KafkaListener
          |
          +-- không có record được giao đủ lâu
          |
          v
Idle condition
          |
          v
ConsumerSeekAware.onIdleContainer(assignments, callback)
          |
          +-- ứng dụng không muốn seek -> return
          |
          +-- có yêu cầu replay hợp lệ -> callback.seek(...)
          |
          v
Những lần poll tiếp theo đọc theo vị trí mới
~~~

**ConsumerSeekAware** phù hợp cho thao tác seek do ứng dụng quản lý. Với nhu cầu chỉ quan sát tình trạng không có dữ liệu, một listener cho **ListenerContainerIdleEvent** thường là đủ; không nhất thiết phải triển khai ConsumerSeekAware.

## 2. onIdleContainer có chữ ký gì?

Một callback thường được Spring Kafka cung cấp dưới dạng:

~~~java
@Override
public void onIdleContainer(
        Map<TopicPartition, Long> assignments,
        ConsumerSeekCallback callback) {
    // Kiểm tra assignments và quyết định có seek hay không.
}
~~~

Trong đó:

| Tham số | Ý nghĩa |
|---|---|
| **assignments** | Map các TopicPartition được giao cho consumer với thông tin vị trí/offset hiện tại do container cung cấp |
| **callback** | Đối tượng ConsumerSeekCallback để yêu cầu seek trên các partitions trong đúng lifecycle callback này |
| **TopicPartition** | Cặp topic và partition, ví dụ orders.events / partition 2 |
| **Long** | Thông tin offset/position ứng với partition; không được mặc định xem đó là committed offset của consumer group |

Ví dụ map:

~~~text
assignments:
  (orders.events, partition 0) -> 108
  (orders.events, partition 1) -> 55
  (orders.events, partition 2) -> 203
~~~

Nghĩa khái quát là listener container đang cung cấp các partition được gán và vị trí mà nó biết tại thời điểm callback. **Không dùng các giá trị này như dấu xác nhận tất cả business side effects trước đó đã commit**. Vị trí của KafkaConsumer và committed offsets của group là hai khái niệm khác nhau.

Trong code minh họa, ConsumerSeekCallback là kiểu lồng trong ConsumerSeekAware. Nếu khai báo ngoài class implements interface, có thể viết đầy đủ **ConsumerSeekAware.ConsumerSeekCallback** để tránh mơ hồ.

## 3. ConsumerSeekAware có những callback liên quan nào?

Interface ConsumerSeekAware có các callback phục vụ những thời điểm khác nhau của listener container:

| Callback | Khi nào hữu ích? |
|---|---|
| **registerSeekCallback** | Framework đăng ký một callback để ứng dụng có thể chuẩn bị cơ chế seek chủ động |
| **onPartitionsAssigned** | Có assignment mới; ứng dụng có thể chọn vị trí đọc ban đầu hoặc khôi phục checkpoint |
| **onPartitionsRevoked** | Partitions chuẩn bị bị thu hồi; ứng dụng dọn state gắn với ownership |
| **onIdleContainer** | Container nhận diện idle; ứng dụng có thể seek trên assigned partitions |

Sơ đồ lifecycle đơn giản:

~~~text
Consumer khởi động
       |
       v
registerSeekCallback(...)
       |
       v
Consumer được assign partitions
       |
       v
onPartitionsAssigned(...)
       |
       v
Poll / process records
       |
       +-- tiếp tục có dữ liệu --> process
       |
       +-- idle đủ thời gian
                |
                v
         onIdleContainer(...)
                |
                +-- có thể seek
                |
                v
          poll / process tiếp
       |
       v
Rebalance hoặc shutdown
       |
       v
onPartitionsRevoked(...)
~~~

Đây là sơ đồ minh họa, **không phải lời hứa mọi callback đều xảy ra đúng một lần và theo đúng thứ tự trong mọi tình huống**. Consumer có thể mất group membership, rebalance theo cooperative protocol hoặc bị kill trước khi có một callback thu hồi partition bình thường.

onIdleContainer không thay thế onPartitionsAssigned: nếu cần seek ngay khi một partition được giao, onPartitionsAssigned thường đúng thời điểm hơn; không nhất thiết phải chờ topic idle.

## 4. Idle là gì trong Spring Kafka?

Một listener container được xem là idle khi **không có record được giao tới listener trong khoảng thời gian đủ dài theo cấu hình idle event**.

Ví dụ:

~~~text
10:00:00  Listener xử lý record cuối cùng
10:00:05  Consumer vẫn poll, chưa có record mới
10:00:10  Consumer vẫn poll, chưa có record mới
10:00:15  Đạt idle interval
          -> container phát hiện idle
          -> callback/event liên quan được kích hoạt
~~~

Điều này **không có nghĩa**:

- Broker Kafka đã ngừng hoạt động.
- Consumer group đã rebalance.
- Consumer thread bị deadlock.
- Consumer đã pause.
- Topic hoàn toàn không có dữ liệu ở mọi partition.
- Tất cả records đã được xử lý thành công và committed.

Một consumer có thể idle vì đang ở cuối log, topic ít traffic, subscription không phù hợp, records bị lọc, đang được pause hoặc do các điều kiện cụ thể của container. Cần điều tra trạng thái assignment, lag và pause trước khi kết luận nguyên nhân.

## 5. Cấu hình idleEventInterval

Để framework nhận biết idle theo khoảng thời gian mong muốn, cấu hình **idleEventInterval** trên listener container.

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        idleAwareKafkaFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    // Yêu cầu phát hiện container idle sau khoảng 15 giây.
    factory.getContainerProperties()
            .setIdleEventInterval(15_000L);

    return factory;
}
~~~

Đây là cách cấu hình Java dùng API ContainerProperties. Các bean ConsumerFactory và serializer/deserializer cần được cấu hình riêng theo ứng dụng.

Nếu không bật cơ chế phát hiện idle, **không được giả định onIdleContainer tự được gọi theo chu kỳ**. Phải cấu hình idleEventInterval trên container đang thực sự chạy listener.

Một cấu hình production có thể dùng khoảng thời gian lớn hơn, tùy throughput và yêu cầu replay. Khoảng 15 giây chỉ minh họa. Đặt quá thấp có thể phát sinh nhiều idle callbacks không cần thiết ở topic ít traffic; đặt quá cao sẽ làm yêu cầu seek-on-idle đến chậm.

Nếu listener container factory được dùng bởi nhiều listeners, idle interval có thể áp dụng cho nhiều containers. Khi cần chính sách khác nhau cho từng nhóm, nên tạo các factories hoặc cấu hình containers tường minh.

## 6. Ví dụ listener implements ConsumerSeekAware

Ví dụ minh họa một listener tiêu thụ orders.events và chỉ seek khi đã có **yêu cầu replay được đặt trước**:

~~~java
@Component
public class OrderEventListener implements ConsumerSeekAware {

    private static final Logger log =
            LoggerFactory.getLogger(OrderEventListener.class);

    private final OrderProjectionService projectionService;

    // Yêu cầu seek do một controller hoặc dịch vụ vận hành gửi tới.
    private final ConcurrentMap<TopicPartition, Long> pendingSeeks =
            new ConcurrentHashMap<>();

    public OrderEventListener(OrderProjectionService projectionService) {
        this.projectionService = projectionService;
    }

    @KafkaListener(
            id = "orders-idle-seek-listener",
            topics = "orders.events",
            groupId = "orders-projection",
            containerFactory = "idleAwareKafkaFactory")
    public void consume(ConsumerRecord<String, OrderEvent> record) {
        projectionService.apply(record.value());
    }

    public void requestReplay(
            String topic, int partition, long targetOffset) {
        if (targetOffset < 0) {
            throw new IllegalArgumentException(
                    "targetOffset must not be negative");
        }

        pendingSeeks.put(
                new TopicPartition(topic, partition),
                targetOffset);
    }

    @Override
    public void onIdleContainer(
            Map<TopicPartition, Long> assignments,
            ConsumerSeekCallback callback) {

        for (TopicPartition partition : assignments.keySet()) {
            Long targetOffset = pendingSeeks.get(partition);
            if (targetOffset == null) {
                continue;
            }

            log.info(
                    "Seek on idle: partition={}, targetOffset={}",
                    partition,
                    targetOffset);

            callback.seek(
                    partition.topic(),
                    partition.partition(),
                    targetOffset);

            pendingSeeks.remove(partition, targetOffset);
        }
    }
}
~~~

Trong ví dụ:

1. Listener xử lý records theo đường bình thường.
2. Một bên điều khiển gọi requestReplay(...) với topic, partition, offset đã được phê duyệt.
3. Yêu cầu được giữ trong ConcurrentHashMap.
4. Khi container idle, Spring Kafka gọi onIdleContainer(...).
5. Callback chỉ seek partitions có trong assignments hiện tại và có yêu cầu tương ứng.
6. Yêu cầu được bỏ khỏi map sau khi đã chuyển cho callback.

**Đây là ví dụ kỹ thuật về cơ chế seek, không phải công cụ replay production hoàn chỉnh.** Một hệ thống thật cần xác thực quyền requestReplay, kiểm tra topic/partition, log start/end offsets, trạng thái transaction, distributed ownership, audit, kết quả seek và khôi phục yêu cầu khi process restart.

## 7. Vì sao phải giới hạn seek bằng một yêu cầu tường minh?

Một implementation nguy hiểm:

~~~java
@Override
public void onIdleContainer(
        Map<TopicPartition, Long> assignments,
        ConsumerSeekCallback callback) {

    assignments.forEach((partition, position) ->
            callback.seek(
                    partition.topic(),
                    partition.partition(),
                    0L));
}
~~~

Mỗi lần container idle, code trên lại đưa consumer về offset 0. Nếu topic ít traffic, nó có thể đọc lại cùng các records **vô hạn lần**.

~~~text
Consumer đọc offsets 0..99
       |
       v
Đến cuối log -> idle
       |
       v
Seek về offset 0
       |
       v
Đọc lại offsets 0..99
       |
       v
Idle -> seek về offset 0 -> lặp
~~~

Hậu quả có thể là:

- Lặp gọi API thanh toán, gửi email hoặc cập nhật database.
- Tạo output Kafka trùng.
- Tăng consumer lag biểu kiến và làm gián đoạn tiến độ đọc records mới.
- Tạo chu kỳ CPU/network không cần thiết.
- Làm tăng kích thước audit/log và che khuất sự cố gốc.

Vì thế nên có **one-shot flag, replay request ID, giới hạn phạm vi và trạng thái đã áp dụng**. Callback không nên tự động rewind mỗi lần idle nếu không có chính sách replay được thiết kế rõ.

## 8. Callback.seek làm gì?

ConsumerSeekCallback cung cấp các phương thức seek do Spring Kafka thực hiện trong ngữ cảnh container phù hợp.

Ví dụ:

~~~java
callback.seek(
        "orders.events",
        2,
        105L);
~~~

Yêu cầu này di chuyển vị trí đọc của **partition 2 trên topic orders.events** đến offset 105, khi partition đó còn thuộc assignment và offset hợp lệ.

Điều cần phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| **Consumer position** | Vị trí mà consumer dự kiến đọc tiếp trong partition |
| **Committed offset** | Vị trí tiếp theo consumer group đã lưu bền vững để phục hồi/restart |
| **Seek target** | Vị trí ứng dụng muốn consumer đọc tiếp sau thao tác seek |
| **Record offset** | Offset riêng của một record đã được đọc |

Seek chủ yếu ảnh hưởng **position**, không phải một lệnh commit offset. Seek không viết lại Kafka log, không xóa các record cũ và không hủy side effects của những records trước đó.

Khi consumer restart hoặc group rebalance, committed offsets và container lifecycle tiếp tục quyết định vị trí đọc. Không giả định một seek tạm thời sẽ tồn tại mãi qua restart.

## 9. assignments không phải committed offsets

Giả sử:

~~~text
orders.events / P2

Consumer position: 120
Consumer group committed offset: 115
Last business record processed: 119
~~~

Map assignments trong callback có thể cung cấp thông tin vị trí hiện tại, nhưng **không phải lời chứng rằng group đã commit đến vị trí đó**.

Ngay cả khi listener đã xử lý record offset 119, commit có thể bị trì hoãn theo AckMode, transaction chưa commit hoặc ứng dụng vừa trải qua lỗi publish.

Nếu cần lựa chọn replay target dựa trên một checkpoint nghiệp vụ, nên lấy checkpoint đó từ hệ thống được thiết kế để lưu nó, không tự lấy assignments position trừ một số lượng bất kỳ rồi coi đó là an toàn.

Với consumer transactional, việc seek tùy tiện giữa các transaction boundaries có thể phá vỡ kỳ vọng về output và input offset đi cùng nhau. Hãy giới hạn seek ở callback/lifecycle điểm hợp lệ và xác định rõ semantics replay.

## 10. Offset trước log start và sau log end

Kafka topics có retention và cleanup policy. Một target offset từng hợp lệ có thể không còn tồn tại:

~~~text
orders.events/P2

Log start offset: 200
Log end offset:   340

Replay request target: 105
~~~

Offset 105 nằm trước log start; broker đã xóa đoạn log chứa record đó. Khi consumer seek đến vị trí không còn hợp lệ, có thể phát sinh lỗi offset out of range hoặc cơ chế auto.offset.reset được áp dụng tùy cấu hình và đường xử lý.

Nếu target nằm ở log end, consumer có thể không nhận thêm record ngay; đây là hành vi bình thường. Nếu target vượt quá end, không nên giả định Kafka sẽ tự tìm lại một record lịch sử.

Trước khi chấp nhận replay production:

1. Xác minh topic và partition tồn tại.
2. Kiểm tra target không âm.
3. Xác minh target còn nằm trong phạm vi retention hiện tại.
4. Xác nhận topic không bị truncate/recreate theo cách làm mất ý nghĩa offset cũ.
5. Xác định có nên đưa target tới beginning/end hợp lệ hay từ chối yêu cầu.
6. Tránh tự động fallback về earliest mà không có quyết định nghiệp vụ, vì có thể dẫn tới xử lý lại một lượng dữ liệu rất lớn.

Những kiểm tra này có thể được thực hiện bởi một thành phần quản trị riêng, hoặc qua API Kafka trong ngữ cảnh thread phù hợp. Đừng gọi KafkaConsumer từ thread của HTTP controller để query offset hoặc seek một consumer đang được Spring container quản lý.

## 11. Một listener idle không đồng nghĩa topic hết dữ liệu

Các tình huống có thể dẫn tới idle:

- Consumer đang ở cuối log đối với các partition nó sở hữu.
- Topic ít traffic hoặc chỉ có record ở các partition do consumers khác sở hữu.
- Listener container đang paused.
- Consumer được cấu hình filter và không có record nào cuối cùng được giao đến business listener theo semantics container.
- Topic subscription hoặc group offset khiến container không nhận thêm record.
- Consumer đang chờ các transactional records commit khi sử dụng read_committed.

Vì vậy, nếu định dùng onIdleContainer để replay, cần xác định lý do idle có phù hợp với kế hoạch hay không.

Không xem idle là điều kiện chắc chắn rằng **toàn bộ hệ thống đã xử lý xong tất cả dữ liệu**. Có thể vẫn còn dữ liệu ở partition khác, consumer khác hoặc trong worker queue bên ngoài listener.

## 12. Idle khác NonResponsiveConsumerEvent như thế nào?

Trong chủ đề **Idle và non-responsive**, đây là sự phân biệt quan trọng nhất:

| Khía cạnh | Listener idle | Consumer non-responsive |
|---|---|---|
| Dấu hiệu chính | Không có record được giao trong khoảng cấu hình | Consumer không thực hiện poll đúng nhịp theo cơ chế giám sát |
| Poll loop | Có thể vẫn hoạt động bình thường | Có thể bị block hoặc xử lý quá lâu |
| Cơ chế liên quan | idleEventInterval, ListenerContainerIdleEvent, ConsumerSeekAware.onIdleContainer | NonResponsiveConsumerEvent, monitorInterval, noPollThreshold |
| Có chắc topic hết records? | Không | Không |
| Có thích hợp để seek? | Có thể, nếu có yêu cầu replay hợp lệ | Không; ưu tiên chẩn đoán consumer thread bị chậm/kẹt |
| Hành động điển hình | Quan sát idle hoặc apply một seek có kiểm soát | Alert, thread dump, kiểm tra poll/DB/API/locks |

Một listener bị block trong lời gọi database kéo dài có thể **không quay lại poll loop**. Nếu callback onIdleContainer được kích hoạt từ vòng xử lý của container, nó không nên được dùng làm cơ chế phát hiện consumer đang bị treo ở một lời gọi dài.

Ngược lại, khi Kafka topic yên ắng nhưng consumer vẫn poll khỏe, một NonResponsiveConsumerEvent không nên được suy ra chỉ vì không có messages.

## 13. Cấu hình giám sát non-responsive riêng

Spring Kafka có cơ chế theo dõi consumer có poll thường xuyên hay không, với các cấu hình như **monitorInterval** và **noPollThreshold** trong các phiên bản hỗ trợ.

Ví dụ cấu hình riêng:

~~~java
factory.getContainerProperties()
        .setIdleEventInterval(15_000L);

factory.getContainerProperties()
        .setPollTimeout(1_000L);

factory.getContainerProperties()
        .setNoPollThreshold(3.0f);

factory.getContainerProperties()
        .setMonitorInterval(10);
~~~

Ví dụ trên minh họa hai nhóm cấu hình khác nhau. Giá trị thực tế và đơn vị của monitorInterval, pollTimeout cùng thuật toán phát hiện phụ thuộc phiên bản Spring Kafka; cần chọn theo thời gian xử lý của ứng dụng.

**Không biến onIdleContainer thành nơi giám sát thread deadlock.** Một logic tự động seek khi consumer không responsive có thể làm mất dấu sự cố hoặc tạo thêm duplicates sau khi thread phục hồi.

Khi quan sát non-responsive, nên kiểm tra listener processing duration, max.poll.interval.ms, database waits, thread pool saturation và số lần consumer rebalance.

## 14. ListenerContainerIdleEvent và onIdleContainer khác nhau

Hai cơ chế đều liên quan idle, nhưng vai trò khác:

### ListenerContainerIdleEvent

Đây là **Spring application event**. Ứng dụng có thể lắng nghe:

~~~java
@Component
public class IdleObserver {

    private static final Logger log =
            LoggerFactory.getLogger(IdleObserver.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info(
                "Listener container idle, listenerId={}, partitions={}",
                event.getListenerId(),
                event.getTopicPartitions());
    }
}
~~~

API event getter có thể khác theo phiên bản Spring Kafka; ví dụ minh họa pattern lắng nghe idle bằng @EventListener và đọc context của event. Đối với các API có tên getter không đồng nhất giữa versions, sử dụng trường/metadata mà dependency hiện tại thực sự cung cấp.

### ConsumerSeekAware.onIdleContainer

Đây là **callback của listener implements ConsumerSeekAware**:

~~~java
@Override
public void onIdleContainer(
        Map<TopicPartition, Long> assignments,
        ConsumerSeekCallback callback) {
    // Có thể gọi callback.seek(...) trong ngữ cảnh thích hợp.
}
~~~

**Event listener** phù hợp cho metrics, alert, dashboard hoặc notification. **ConsumerSeekAware callback** phù hợp để thao tác seek do framework cung cấp, không cần tự lấy KafkaConsumer và gọi seek ngoài consumer thread.

Không nên dùng ListenerContainerIdleEvent listener để lấy consumer object rồi truyền sang một background thread nhằm seek; KafkaConsumer không được truy cập đồng thời tùy ý.

## 15. Thread nào chạy onIdleContainer?

Callback onIdleContainer được Spring Kafka gọi trong quá trình listener container xử lý trạng thái idle của **consumer thread**. Điều này quan trọng vì thao tác seek trên KafkaConsumer phải tuân thủ thread confinement.

~~~text
Consumer thread C
     |
     +-- poll
     +-- phát hiện idle
     +-- onIdleContainer(assignments, callback)
     |      |
     |      +-- callback.seek(...)
     |
     +-- tiếp tục poll theo vị trí mới
~~~

Trong callback:

- Chỉ thao tác trên partitions có trong assignments.
- Quyết định seek nên ngắn gọn và không block lâu.
- Không chờ một REST request hoặc database query nhiều giây.
- Không sleep để đợi data.
- Không giữ lock toàn cục làm các listeners khác bị chặn.
- Không gọi listener container.stop() đồng bộ trên consumer thread.

Nếu cần truy xuất policy từ database hoặc một hệ thống phê duyệt, hãy chuẩn bị **yêu cầu replay/checkpoint trước**, trong một service khác. onIdleContainer chỉ áp dụng quyết định đã sẵn sàng, tránh đặt network I/O trong vòng poll.

## 16. Callback nhận ở onIdleContainer có thể lưu dùng sau không?

Spring Kafka cung cấp callback cho nhiều ngữ cảnh. Đặc biệt, callback truyền vào **onPartitionsAssigned** hoặc **onIdleContainer** được thiết kế để sử dụng trong lifecycle method tương ứng, khác về ngữ nghĩa với callback mà **registerSeekCallback** cung cấp.

Nguyên tắc an toàn:

1. **Dùng callback tham số của onIdleContainer ngay trong method này.**
2. Không giữ tham chiếu callback của onIdleContainer trong một field rồi gọi từ một HTTP thread về sau.
3. Nếu cần yêu cầu seek chủ động từ một thread khác, nghiên cứu cơ chế **registerSeekCallback** và cách Spring Kafka schedule seeks phù hợp với phiên bản.
4. Với concurrent listener, quản lý callbacks theo consumer thread/assignment; đừng ghi đè một callback global rồi gọi seek trên partition thuộc consumer khác.

Một cấu trúc dễ sai:

~~~java
private ConsumerSeekCallback latestCallback;

@Override
public void onIdleContainer(
        Map<TopicPartition, Long> assignments,
        ConsumerSeekCallback callback) {

    latestCallback = callback; // Không lưu callback lifecycle tùy tiện.
}

public void seekFromHttpThread(...) {
    latestCallback.seek(...);  // Không an toàn khi dùng sai ngữ cảnh.
}
~~~

Thay vào đó, một cách đơn giản là đưa **seek request** vào ConcurrentMap hoặc durable request queue và áp dụng trong onIdleContainer, khi framework đang gọi callback trên consumer thread.

## 17. registerSeekCallback dùng khi nào?

**registerSeekCallback** được thiết kế cho nhu cầu ứng dụng phải thực hiện seek không nhất thiết trùng với một callback idle hoặc assignment. Spring Kafka hỗ trợ lưu callback phù hợp và thực hiện các thao tác seek được yêu cầu qua API callback.

Ví dụ biểu diễn giao diện:

~~~java
@Override
public void registerSeekCallback(
        ConsumerSeekCallback callback) {

    // Có thể lưu callback theo consumer context,
    // nhưng phải tuân thủ quy tắc threading và assignment
    // của Spring Kafka version đang sử dụng.
}
~~~

Không nhầm callback đăng ký này với callback tham số của onIdleContainer. Trong ứng dụng concurrency lớn, một listener bean có thể được nhiều consumer threads dùng chung. Vì vậy, thường cần ánh xạ callback theo thread hoặc container instance, đồng thời cập nhật khi assignment/revocation thay đổi.

Nếu yêu cầu rất đơn giản là "chỉ replay khi idle", một **pending seek map** áp dụng trong onIdleContainer dễ hiểu và ít rủi ro hơn việc expose trực tiếp callback ra ngoài. Nếu yêu cầu replay ngay, không thể chờ idle, nên thiết kế một dịch vụ điều khiển seek riêng với callback từ registerSeekCallback theo API được phiên bản hỗ trợ.

## 18. Rebalance ảnh hưởng đến pending seek như thế nào?

Các partitions mà listener đang sở hữu có thể đổi owner khi scale, deploy hoặc group rebalance.

~~~text
Trước:
  Consumer A sở hữu orders.events/P2

Operator request replay:
  orders.events/P2 -> offset 105

Rebalance:
  P2 chuyển sang Consumer B

Sau:
  Consumer A không còn quyền seek P2
  Consumer B là owner mới
~~~

Nếu pending seek nằm trong bộ nhớ của listener bean trên Consumer A, request đó **không tự chuyển sang Consumer B**. Callback onIdleContainer của A không nên cố seek partition không còn thuộc assignments.

Có hai mô hình:

- **Best-effort local request:** chỉ thực hiện khi consumer hiện tại còn ownership; nếu mất assignment, request có thể hết hạn hoặc phải gửi lại.
- **Durable replay request:** lưu yêu cầu trong database/command topic, có owner coordination, version và audit; consumer owner hiện tại đọc và áp dụng một lần.

Với hệ thống nhiều replicas, nên có một nguồn sự thật cho replay requests. Không xây API admin mà gửi lệnh tới một pod ngẫu nhiên rồi giả định pod ấy đang sở hữu partition.

## 19. onPartitionsAssigned bổ sung gì cho replay?

Khi partition được assign, listener có thể dùng **onPartitionsAssigned** để thiết lập vị trí đọc ban đầu theo checkpoint hoặc policy:

~~~java
@Override
public void onPartitionsAssigned(
        Map<TopicPartition, Long> assignments,
        ConsumerSeekCallback callback) {

    assignments.forEach((partition, currentPosition) -> {
        Long checkpoint = checkpointService.findReplayCheckpoint(partition);

        if (checkpoint != null) {
            callback.seek(
                    partition.topic(),
                    partition.partition(),
                    checkpoint);
        }
    });
}
~~~

CheckpointService ở đây là một service ứng dụng. Mẫu code minh họa logic; để bảo đảm Kafka consumer thread không bị block, checkpoint nên được cache hoặc có đường lookup bounded/đã chuẩn bị trước khi callback chạy.

**onPartitionsAssigned** phù hợp khi muốn khởi tạo vị trí đọc ngay lúc assignment. **onIdleContainer** phù hợp khi việc seek chỉ được kích hoạt ở trạng thái idle. Không nên tự ý seek lại checkpoint ở cả hai callback mà không có request/version guard, vì sẽ tạo replay trùng hoặc khiến consumer không tiến.

## 20. onPartitionsRevoked phải xử lý state ra sao?

Nếu consumer mất assignment của partition, state và callback context gắn với partition cũ cần được cập nhật:

~~~java
@Override
public void onPartitionsRevoked(
        Collection<TopicPartition> partitions) {

    for (TopicPartition partition : partitions) {
        log.info("Partition revoked: {}", partition);
        // Cập nhật ownership/metrics của partition.
        // Không cố seek partition đã rời assignment.
    }
}
~~~

Không tự xóa **mọi** state của mọi partition khi cooperative rebalance chỉ revoke một phần assignments. Tham số partitions cho biết những partitions cần xử lý trong callback hiện tại.

Với pending durable requests, không nên xóa request vĩnh viễn chỉ vì owner cũ mất assignment. Hãy để owner mới lấy lại hoặc điều phối lại sau khi xác định request chưa được áp dụng thành công.

Nếu consumer bị kill đột ngột, onPartitionsRevoked có thể không được gọi. Vì thế một replay workflow quan trọng không được dựa hoàn toàn vào cleanup callbacks trong bộ nhớ.

## 21. Concurrency: một bean, nhiều consumer threads

Khi @KafkaListener dùng concurrency lớn hơn 1, Spring Kafka tạo nhiều consumer threads/child containers. Một bean implements ConsumerSeekAware có thể được sử dụng bởi nhiều consumer contexts.

~~~text
OrderEventListener bean
         |
         +-- consumer thread A -> partitions P0,P1
         |
         +-- consumer thread B -> partitions P2,P3
         |
         +-- consumer thread C -> partitions P4,P5
~~~

Trong onIdleContainer, assignments của mỗi callback thuộc context consumer liên quan. Vì vậy:

- Chỉ seek các partitions xuất hiện trong assignments hiện tại.
- Dùng ConcurrentMap/transaction-safe registry cho requests được gửi từ thread khác.
- Không dùng một biến global "currentOffset" cho tất cả consumers.
- Không lưu một callback duy nhất rồi coi nó đại diện cho toàn listener.
- Phân biệt child listener IDs và current partition owners trong logs.
- Không giả định P2 luôn thuộc consumer B; rebalance có thể thay đổi assignment.

Nếu muốn replay một partition từ admin API, cần có cơ chế định tuyến yêu cầu đến consumer owner hoặc lưu yêu cầu trong shared store để owner hiện tại nhận.

## 22. Tại sao không nên tự seek toàn bộ partitions khi idle?

Một topic có thể gồm sáu partitions, trong đó một partition thật sự cần replay còn năm partitions đã xử lý đúng.

~~~text
orders.events
  P0 -> processed to 500
  P1 -> processed to 700
  P2 -> replay request to 105
  P3 -> processed to 920
  P4 -> processed to 160
  P5 -> processed to 430
~~~

Nếu onIdleContainer seek toàn bộ assignments về đầu log, hệ thống có thể tạo lượng dữ liệu xử lý lại rất lớn và vi phạm ordering/business state trên năm partitions không liên quan.

Một request tốt nên có:

~~~text
requestId: replay-2026-001
topic: orders.events
partition: 2
targetOffset: 105
reason: rebuild-order-projection
requestedBy: operator-identity
expiresAt: một thời điểm giới hạn
status: PENDING / APPLIED / FAILED
~~~

Các trường trên là thiết kế của ứng dụng, không phải Kafka record headers tự sinh. Mục tiêu là hạn chế phạm vi tác động và có khả năng kiểm toán, không thực hiện một câu lệnh seek toàn cluster thiếu kiểm soát.

## 23. Replay và thứ tự xử lý

Kafka giữ thứ tự **trong một partition** theo offset. Khi seek lùi, consumer đọc lại một dãy records đã từng được xử lý, có thể làm hệ thống nghiệp vụ nhìn thấy events cũ sau events mới.

Ví dụ:

~~~text
P2:
  offset 105 -> OrderCreated
  offset 106 -> OrderPaid
  offset 107 -> OrderShipped
  offset 108 -> OrderCancelled

Ứng dụng hiện tại đã xử lý tới 108.
Seek về 105:
  OrderCreated lại được giao sau OrderCancelled.
~~~

Nếu projection áp dụng events theo thứ tự và có khả năng rebuild từ đầu, replay có thể hợp lý. Nhưng nếu handler gửi lại email "đơn đã được tạo", trừ tồn kho hoặc hoàn tiền, replay không có biện pháp an toàn sẽ gây side effects không mong muốn.

Các chiến lược thường gặp:

- Idempotent handler theo event ID.
- Kiểm tra aggregate version hoặc state transition hợp lệ.
- Chạy replay trong một consumer group hoặc môi trường riêng.
- Chỉ phát output sang topic phục vụ rebuild, không gọi external APIs.
- Ghi rõ replay mode để handler biết cần bỏ qua các side effects không được phép lặp.

Không coi Kafka offset là định danh nghiệp vụ bất biến khi sự kiện có thể được republish sang topic hoặc cluster khác.

## 24. Tác động tới group committed offset

Seek thay đổi consumer position, nhưng group committed offset có thể còn ở vị trí cũ.

~~~text
Trước replay:
  consumer position = 500
  committed offset  = 500

onIdleContainer seek(200)
  consumer position = 200
  committed offset  = 500 (chưa thay đổi)

Consumer đọc và xử lý lại từ 200
~~~

Sau đó, container có thể commit offsets từ các lần xử lý mới theo AckMode/transaction policy. Điều này có thể làm committed offset của group tiến theo dữ liệu replay hoặc đi lùi theo mục tiêu seek, tùy trình tự xử lý và commit.

Không dựa vào một phép seek để giữ lâu dài một vị trí đọc qua restart, nếu không thiết kế cách commit/checkpoint tương ứng.

Nếu cần replay dữ liệu lịch sử **mà không thay đổi tiến độ của consumer group production**, cách an toàn hơn thường là **dùng một consumer group riêng**. Group mới có committed offsets độc lập, tránh ảnh hưởng quy trình live đang tiêu thụ topic.

## 25. AckMode và manual acknowledgment

Trong Spring Kafka, container có các AckMode như RECORD, BATCH, MANUAL và MANUAL_IMMEDIATE. Cách container commit offsets ảnh hưởng trực tiếp đến kết quả của seek.

Ví dụ listener manual ack:

~~~java
@KafkaListener(
        topics = "orders.events",
        containerFactory = "manualAckFactory")
public void consume(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment acknowledgement) {

    projectionService.apply(record.value());
    acknowledgement.acknowledge();
}
~~~

Code minh họa chỉ phù hợp nếu manualAckFactory có AckMode tương ứng. Acknowledgment được thực hiện **sau khi** nghiệp vụ hoàn tất. Nếu ack sớm rồi seek hoặc crash, record có thể bị đánh dấu xử lý dù side effect còn dang dở.

Khi listener xử lý bất đồng bộ, một record được enqueue không có nghĩa đã hoàn thành; seek-on-idle có thể xảy ra khi worker pool vẫn chạy tasks từ những records trước đó. Cần tracking in-flight tasks và idempotency.

Trong giao dịch Kafka-to-Kafka, consumed offsets có thể được đưa vào Kafka transaction. Không tự gọi commitSync trong callback onIdleContainer để "lưu seek" vì điều đó có thể phá vỡ transaction semantics của container.

## 26. Idle callback và tác vụ bất đồng bộ

Giả sử listener nhận record rồi đẩy công việc sang executor:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(OrderEvent event) {
    workerPool.execute(() -> projectionService.apply(event));
}
~~~

Nếu method trả về ngay, container có thể tiếp tục poll rồi sau đó idle dù worker pool vẫn còn các jobs chưa hoàn tất.

~~~text
12:00:00  Listener enqueue A, B, C
12:00:01  Callback listener đã trả về
12:00:15  Container idle
           -> onIdleContainer được gọi

Nhưng worker pool:
  A = DONE
  B = RUNNING
  C = QUEUED
~~~

Nếu callback seek về offset của A để replay khi B vẫn đang cập nhật database, hệ thống có thể chạy hai chuỗi xử lý cùng event song song hoặc đảo ngược thứ tự business effects.

Nếu muốn dùng seek-on-idle trong hệ thống async:

1. Theo dõi in-flight tasks theo partition.
2. Không coi idle là in-flight=0.
3. Chờ một điều kiện quiesce có giới hạn ở coordinator bên ngoài consumer thread.
4. Chỉ đưa replay request vào hàng đợi khi trạng thái nghiệp vụ an toàn.
5. Áp dụng seek trong callback ngắn gọn, không chờ worker pool ngay trong onIdleContainer.
6. Bảo vệ duplicate side effects bằng idempotency.

## 27. Consumer pause và idle callback

Pause và idle là hai khái niệm riêng:

| Trạng thái | Ý nghĩa |
|---|---|
| **RUNNING, ACTIVE** | Consumer tiếp tục giao records cho listener |
| **PAUSED** | Consumer vẫn có thể poll, nhưng tạm ngừng giao records của partitions paused |
| **IDLE** | Container không giao record trong khoảng idleEventInterval |
| **STOPPED** | Consumer/container đóng theo lifecycle |
| **NON_RESPONSIVE** | Consumer không poll theo nhịp theo giám sát |

Một consumer đang paused có thể không nhận records và vì vậy có biểu hiện giống idle tùy cơ chế phiên bản/container. **Không dùng onIdleContainer làm phương thức thay thế cho pause/resume**.

Nếu ứng dụng đang pause vì database overload, tự động seek ngay khi idle có thể khiến backlog replay phình to, và khi resume sẽ tạo đợt tải lớn hơn. Nên kiểm tra desired pause state và lý do pause trước khi áp dụng replay.

Khi đã stop container, callback idle sẽ không tiếp tục chạy như một scheduler độc lập. Nếu cần tự động replay theo lịch, không nên dùng onIdleContainer làm bộ lập lịch chính.

## 28. Idle và ConsumerStoppedEvent

Spring Kafka phát các lifecycle events khác nhau để vận hành:

~~~text
ListenerContainerIdleEvent
  -> container không có record được giao trong thời gian idle

ConsumerStoppedEvent
  -> consumer đã dừng

NonResponsiveConsumerEvent
  -> consumer không poll đúng nhịp

ConsumerPausedEvent / ConsumerResumedEvent
  -> consumer pause/resume có hiệu lực
~~~

Những events không thay thế nhau:

- Idle không có nghĩa stopped.
- Stopped không có nghĩa idle.
- Paused không có nghĩa consumer không còn group assignment.
- Non-responsive không phải một yêu cầu seek.

Đối với dashboard, nên tách các trạng thái: listener running, current assignment, pause requested/observed, idle duration, non-responsive count và consumer lag.

## 29. Khi nào seek-on-idle là một ý tưởng tốt?

Seek-on-idle có thể phù hợp khi:

- Consumer phục vụ một **projection rebuild** chứ không gọi side effects bên ngoài.
- Replay target đã được kiểm tra hợp lệ trước.
- Có yêu cầu một lần rõ ràng, có audit và quyền truy cập.
- Consumer group có thể chấp nhận đọc lại records và thay đổi tiến độ xử lý.
- Handler idempotent hoặc hoạt động ở chế độ rebuild.
- Listener thực sự idle và không còn in-flight work liên quan.

Seek-on-idle thường **không phù hợp** khi:

- Production listener xử lý thanh toán hoặc tác vụ không idempotent.
- Consumer đang bị kẹt/no poll và cần chẩn đoán non-responsive.
- Ứng dụng muốn replay ngay mà không chờ idle.
- Replay cần thao tác trên nhiều partitions/instances và ownership đang thay đổi.
- Dữ liệu nguồn có thể đã hết retention nhưng ứng dụng chưa kiểm tra.
- Hệ thống chỉ muốn biết vì sao topic không có records; lúc này chỉ cần monitoring.

Nếu cần quét lịch sử một lần để dựng lại dữ liệu, một job/consumer group chuyên dụng thường dễ kiểm soát hơn việc điều khiển group production bằng idle callback.

## 30. Replay target là offset hay timestamp?

Kafka định vị records theo partition + offset. Một số use cases muốn đọc từ thời điểm thay vì offset cụ thể:

~~~text
Replay request:
  topic = orders.events
  partition = 2
  fromTimestamp = 2026-11-15T10:00:00Z
~~~

Trong trường hợp đó, phải chuyển yêu cầu timestamp thành offset hợp lệ hoặc sử dụng các API seek theo timestamp mà phiên bản Spring Kafka hỗ trợ. Không tự giả định timestamp tương ứng chính xác một event duy nhất: nhiều records có thể cùng timestamp, và Kafka hỗ trợ CREATE_TIME hoặc LOG_APPEND_TIME theo cấu hình topic.

Nếu đã có một checkpoint offset đáng tin cậy, callback.seek(topic, partition, offset) là lựa chọn đơn giản và rõ nhất. Nếu muốn seek theo timestamp, cần kiểm tra semantics, retention và độ chính xác thời gian ở cả producer và Kafka topic.

Không dùng System.currentTimeMillis() trực tiếp làm offset; đó là hai đơn vị hoàn toàn khác nhau.

## 31. Quan sát và ghi log cho onIdleContainer

Một callback idle không nên spam log ERROR mỗi lần không có records. Topic không có traffic có thể là bình thường.

Logs hữu ích khi có replay request:

~~~text
event=seek_on_idle_requested
requestId=replay-001
listenerId=orders-idle-seek-listener
topic=orders.events
partition=2
targetOffset=105
requestedBy=operator

event=seek_on_idle_applied
requestId=replay-001
listenerId=orders-idle-seek-listener
topic=orders.events
partition=2
observedPositionBefore=340
targetOffset=105
~~~

Đây là định dạng structured log ứng dụng tự thiết kế, không phải log mặc định của Spring Kafka.

Metrics nên theo dõi:

- Idle callback count và idle duration.
- Seek request count, applied count, rejected count.
- Thời gian từ request tới callback seek.
- Replay records processed và replay failure count.
- Consumer lag và tốc độ commit offset.
- Rebalance count, assignment changes.
- In-flight business tasks nếu listener async.
- NonResponsiveConsumerEvent count riêng.
- DLT/retry rate nếu replay thất bại.

Không dùng từng offset hoặc request ID làm metric label vì cardinality cao. Đưa chúng vào log/trace có kiểm soát.

## 32. Tránh xử lý nặng trong callback

Một implementation không phù hợp:

~~~java
@Override
public void onIdleContainer(
        Map<TopicPartition, Long> assignments,
        ConsumerSeekCallback callback) {

    for (TopicPartition partition : assignments.keySet()) {
        // Tránh gọi REST/DB chậm ngay trên consumer thread.
        Long target = remoteReplayService.fetchNextOffset(partition);

        if (target != null) {
            callback.seek(
                    partition.topic(),
                    partition.partition(),
                    target);
        }
    }
}
~~~

Nếu remoteReplayService chậm, consumer thread không thể tiếp tục poll đúng hạn. Ứng dụng có thể gặp max.poll.interval.ms, rebalance hoặc NonResponsiveConsumerEvent — chính sự cố mà nhóm vận hành đang muốn tránh.

Mô hình tốt hơn:

~~~text
Admin API / Scheduler / Database worker
       |
       +-- kiểm tra request + quyền truy cập
       +-- lấy checkpoint/target
       +-- kiểm tra offset range
       |
       v
Thread-safe pending replay store
       |
       v
onIdleContainer (consumer thread)
       |
       +-- đọc request đã chuẩn bị
       +-- callback.seek(...)
       +-- ghi nhận state ngắn gọn
       |
       v
Poll tiếp
~~~

Nếu việc ghi audit bền vững có thể chặn thread, hãy đưa thông tin chuyển trạng thái vào một queue/event phù hợp và để worker riêng lưu audit. Nếu audit là điều kiện bắt buộc trước replay, chuẩn bị audit/approval **trước** khi callback seek thay vì cố tạo một DB transaction dài ngay trong callback.

## 33. Xử lý lỗi seek

Không phải mọi yêu cầu seek đều thành công:

- Target offset không hợp lệ hoặc đã hết retention.
- Partition không còn thuộc assignment do rebalance.
- Consumer/container đang stop.
- Request dành cho topic không được listener subscribe.
- Callback không còn hợp lệ theo lifecycle.
- Recovery workflow chưa cho phép replay một event cụ thể.

Trong ví dụ pendingSeeks, có thể xem xét phân loại:

~~~text
PENDING
   |
   +-- target không hợp lệ -> REJECTED
   |
   +-- không còn ownership -> WAITING_FOR_OWNER
   |
   +-- callback được áp dụng -> APPLIED
   |
   +-- exception -> FAILED_RETRYABLE hoặc FAILED_FINAL
~~~

Không ghi "REPLAY_COMPLETED" ngay sau callback.seek. **Seek applied chỉ có nghĩa vị trí đọc đã được yêu cầu thay đổi**; quá trình xử lý lại records và commit kết quả là giai đoạn khác.

Nếu cần exactly-once effect ở nghiệp vụ, nên có transaction/idempotency tại nơi ghi kết quả. Callback seek tự thân không cung cấp exactly-once delivery.

## 34. Kafka transaction và seek-on-idle

Trong consumer-initiated Kafka transaction, container phối hợp output Kafka với consumed offsets bằng transactional producer. Seek thay đổi vị trí đọc nhưng không nên bị dùng như cách bỏ qua hoặc hoàn tất một transaction đang dang dở.

~~~text
Consumer nhận P2@100
      |
      v
Kafka transaction T1
      |
      +-- produce output
      +-- process result
      |
      v
Commit hoặc abort T1 theo container
      |
      v
Sau đó, ở lifecycle idle phù hợp,
onIdleContainer có thể áp dụng một seek request.
~~~

Khi replay cùng record, listener có thể chạy lại và tạo output lần nữa trong transaction mới. Kafka transaction bảo vệ tính nguyên tử của records/offsets **trong mỗi transaction**, nhưng không tự ngăn replay có chủ đích tạo một lần xử lý Kafka mới.

Nếu output Kafka từ lần xử lý đầu đã committed và event được replay thành công lần nữa, business downstream có thể thấy event tương đương ở offset Kafka mới. Cần event ID ổn định và quy tắc deduplication hoặc một consumer group chuyên dụng cho rebuild.

Không dùng consumer.commitSync() trong onIdleContainer để đặt offset theo ý muốn khi container đang quản lý Kafka transactions; điều đó có thể phá vỡ sự phối hợp output và offset.

## 35. Listener idle khi topic có transaction đang mở

Consumer sử dụng isolation.level=read_committed chỉ được nhìn thấy những transactional records đã commit. Nếu có một transaction đang mở trước Last Stable Offset, consumer có thể chưa nhận records mới dù broker đã ghi một số batches phía sau.

~~~text
Topic log:
  committed record A
  open transaction T1
  committed record B phía sau

Consumer read_committed:
  có thể phải chờ tại Last Stable Offset
~~~

Vì vậy, một ListenerContainerIdleEvent hoặc onIdleContainer callback không chứng minh topic trống. Consumer có thể đang đợi transaction giải quyết.

Nếu tình huống này gây lag, cần kiểm tra Kafka transaction duration, producer commit/abort errors và Last Stable Offset thay vì tự động seek backward để "kích hoạt" consumer.

Seek không sửa được một transaction đang mở hoặc bị broker coordinator chờ xử lý.

## 36. Mẫu kiểm thử tích hợp dùng Kafka broker

Một unit test gọi trực tiếp onIdleContainer với map giả và callback giả có thể kiểm tra logic routing seek. Nhưng để chứng minh cơ chế **container idle → callback → consumer position đổi**, cần dùng Kafka thật trong test, ví dụ Testcontainers Kafka hoặc EmbeddedKafka.

### Test 1: callback được gọi khi idle

1. Tạo topic orders.events.
2. Khởi động listener implements ConsumerSeekAware với idleEventInterval ngắn trong test.
3. Đảm bảo listener đã có assignment.
4. Không gửi records trong khoảng interval.
5. Dùng CountDownLatch trong test observer để xác nhận onIdleContainer được gọi.
6. Kiểm tra assignments chứa những TopicPartitions đúng phạm vi.

Không chỉ sleep một khoảng cố định rồi suy luận callback chắc chắn đã chạy; nên đợi điều kiện có timeout.

### Test 2: không tự seek khi không có request

1. Gửi một record và chờ listener xử lý.
2. Để container idle.
3. Không gửi replay request.
4. Kiểm tra listener không xử lý lại record chỉ vì idle.
5. Kiểm tra offset/processed count vẫn phù hợp.

### Test 3: one-shot replay

1. Produce một record và ghi nhận topic/partition/offset thực tế.
2. Đợi listener xử lý lần đầu.
3. Gọi requestReplay với chính offset đó.
4. Đợi callback idle.
5. Xác nhận listener nhận lại record một lần theo phạm vi test.
6. Đợi idle lần nữa và xác nhận không seek lặp vô hạn khi pending request đã được xóa.

Nếu test có nhiều records, cần thiết kế điều kiện chờ để phân biệt record replay với record mới, chẳng hạn event ID cố định và bộ đếm riêng.

### Test 4: target đã hết retention

1. Tạo topic/retention setup phù hợp.
2. Chọn target offset trước log start.
3. Gửi yêu cầu replay.
4. Xác nhận chính sách ứng dụng từ chối hoặc xử lý invalid offset có kiểm soát.
5. Kiểm tra không có vòng retry/seek vô hạn.

### Test 5: rebalance trước idle

1. Tạo topic có nhiều partitions và hai consumer instances cùng group.
2. Đặt pending request cho partition P2 ở instance A.
3. Gây rebalance để P2 chuyển owner.
4. Xác nhận A không seek P2 khi P2 không còn trong assignments.
5. Với durable request, xác nhận owner mới B có thể nhận và áp dụng request.

### Test 6: non-responsive khác idle

1. Để consumer poll bình thường nhưng topic trống.
2. Xác nhận idle callback/event có thể phát sinh.
3. Tạo tình huống listener xử lý lâu gây no-poll monitoring.
4. Xác nhận NonResponsiveConsumerEvent được theo dõi theo chính sách riêng.
5. Không tự động seek trong một tình huống chỉ có non-responsive alert.

### Test 7: callback không được block

1. Cho một thread chuẩn bị pending replay target.
2. Khi callback idle chạy, chỉ đọc dữ liệu sẵn có và gọi seek.
3. Đo callback duration.
4. Xác nhận poll thread không chờ remote network operations.
5. Kiểm tra consumer không bị rebalance do callback tự block.

### Test 8: duplicate business effect

1. Gửi một event có event ID cố định.
2. Listener ghi side effect vào test database có idempotency.
3. Seek replay record đó.
4. Xác nhận listener có thể được gọi lại nhưng side effect không bị lặp.
5. Nếu có Kafka output, kiểm tra event ID và downstream deduplication strategy.

Các test nên đặt timeouts và isolation rõ ràng. Không dùng group production hoặc dữ liệu Kafka production để thử seek backward.

## 37. Các lỗi thiết kế thường gặp

| Sai lầm | Vì sao nguy hiểm | Thay thế |
|---|---|---|
| Seek về offset 0 mỗi lần idle | Tạo replay loop không giới hạn | One-shot replay request với trạng thái |
| Coi assignments position là committed offset | Có thể lệch commit hoặc transaction | Kiểm tra group committed offset/checkpoint riêng |
| Coi idle là consumer non-responsive | Chẩn đoán sai root cause | Theo dõi NonResponsiveConsumerEvent riêng |
| Gọi KafkaConsumer.seek từ HTTP thread | Vi phạm thread confinement | Dùng ConsumerSeekCallback đúng lifecycle |
| Lưu callback onIdleContainer để gọi về sau | Sai ngữ cảnh lifecycle | Sử dụng callback trong method; thiết kế registerSeekCallback cho external requests |
| Query database chậm trong onIdleContainer | Block poll thread và có thể rebalance | Chuẩn bị request trước bằng worker khác |
| Seek partition không thuộc assignments | Mất ownership hoặc logic race | Chỉ seek partitions hiện được giao |
| Dùng pending request local cho nhiều pods | Request không theo owner khi rebalance | Durable request + owner coordination |
| Coi seek applied là replay completed | Chưa có bằng chứng processing/commit | Theo dõi replay completion riêng |
| Không kiểm tra retention | Offset có thể đã bị xóa | Validate log start/end trước replay |
| Rewind consumer group production để rebuild | Ảnh hưởng live processing và group offsets | Ưu tiên consumer group riêng |
| Không có idempotency khi replay | Lặp side effects, output trùng | Event ID, unique constraint, replay mode |

## 38. Quan hệ với ứng dụng Spring Kafka production

Một hệ thống vận hành an toàn nên tách rõ ba lớp:

~~~text
Control plane
  - Ai được phép replay?
  - Replay topic/partition/offset nào?
  - Vì sao? Trong thời gian nào?
  - Kiểm tra retention và approvals
          |
          v
Durable replay request store
          |
          v
Kafka listener owner
  - ConsumerSeekAware.onIdleContainer
  - Chỉ apply request hợp lệ khi assigned và idle
  - Không block poll thread
          |
          v
Processing/data plane
  - Consumer đọc lại record
  - Idempotent business handling
  - Track Kafka/database output
  - Record replay outcome
~~~

Control plane không cần thao tác trực tiếp trên KafkaConsumer của data plane. Nó chỉ gửi một yêu cầu đã xác minh. Listener owner là nơi thực hiện seek đúng lifecycle, còn processing layer quyết định record có được áp dụng lại hay không.

Nếu mục tiêu là tự động retry lỗi record, **DefaultErrorHandler, backoff và DLT** thường phù hợp hơn. onIdleContainer không phải một error-handler thay thế và cũng không phải scheduler cho retry delay.

## 39. Các hiểu nhầm phổ biến

**onIdleContainer được gọi sau mỗi consumer.poll() trả về rỗng.** Không đúng. Nó gắn với điều kiện container idle theo idleEventInterval và lifecycle cấu hình, không phải hook bắt buộc ở mỗi poll trống.

**Idle có nghĩa topic Kafka không còn dữ liệu.** Không đúng. Có thể còn records ở partitions khác, open transactions hoặc consumer đang paused.

**Idle có nghĩa consumer thread đang treo.** Không đúng. Consumer có thể poll khỏe nhưng không có messages.

**ConsumerSeekAware.onIdleContainer và ListenerContainerIdleEvent là cùng một API.** Không đúng. Một bên là callback trên listener, một bên là Spring application event.

**Map assignments chứa committed offsets chắc chắn.** Không đúng. Nó chứa thông tin vị trí/offset do container cung cấp ở thời điểm callback; cần phân biệt consumer position và group committed offset.

**Gọi callback.seek là Kafka đã commit offset mới.** Không đúng. Seek thay đổi vị trí đọc, commit group offset là việc khác.

**Seek được Kafka giữ vĩnh viễn qua restart.** Không đúng. Khi restart/rebalance, committed offset và assignment quyết định vị trí mặc định nếu không có cơ chế seek/checkpoint mới.

**Seek lùi chỉ đọc lại một record rồi dừng.** Không đúng. Consumer có thể đọc lại cả dãy records từ target tới cuối log.

**onIdleContainer tự bảo đảm không có in-flight business task.** Không đúng nếu listener dùng worker pool hoặc công việc bất đồng bộ.

**Có thể gọi callback của onIdleContainer từ một thread khác bất cứ lúc nào.** Không nên. Dùng callback trong lifecycle method và cơ chế external seek được Spring Kafka hỗ trợ riêng.

**Khi cooperative rebalance, mọi partitions đều bị revoke.** Không đúng. Chỉ một tập partitions có thể thay owner.

**Một replay request gửi đến pod nào cũng được.** Không đúng. Pod đó phải sở hữu partition hoặc có coordination để owner hiện tại xử lý yêu cầu.

**Seek-on-idle tự xử lý deserialization, retry và DLT.** Không đúng. Đó là các cơ chế error handling khác.

**Kafka transaction loại bỏ mọi side effect trùng khi replay.** Không đúng. Replay là lần thực thi mới, database/API cần idempotency.

## 40. Quy trình triển khai khuyến nghị

Để sử dụng ConsumerSeekAware.onIdleContainer trong Spring Kafka Reliability Operations:

1. Chỉ bật cơ chế seek-on-idle khi có **nhu cầu nghiệp vụ rõ ràng**, không coi idle là một lỗi.
2. Cấu hình idleEventInterval trên đúng listener container factory.
3. Để bean listener implements ConsumerSeekAware và định nghĩa onIdleContainer với Map<TopicPartition, Long> và ConsumerSeekCallback.
4. Mặc định **không seek** khi chưa có yêu cầu replay được phê duyệt.
5. Lưu request có topic, partition, target offset, request ID, lý do và trạng thái.
6. Kiểm tra target không âm, partition hợp lệ và offset còn trong retention.
7. Chỉ apply seek với partitions trong assignments của callback hiện tại.
8. Không query REST/DB hoặc sleep lâu trên consumer thread.
9. Dùng callback.seek ngay trong onIdleContainer; không cất giữ callback lifecycle để gọi tùy tiện từ thread khác.
10. Xử lý rebalance, partition revoke và nhiều replicas bằng ownership-aware request management.
11. Phân biệt seek applied với replay completed, theo dõi tiến độ và kết quả.
12. Dùng event ID và idempotency để tránh duplicate side effects khi record được đọc lại.
13. Ưu tiên consumer group riêng nếu chỉ cần rebuild lịch sử mà không ảnh hưởng tiến độ production.
14. Tách metrics **idle** khỏi **non-responsive**, pause, stop và rebalance.
15. Kiểm thử one-shot replay, expired offset, concurrent consumers, async in-flight tasks và transaction boundaries bằng Kafka broker test.

**ConsumerSeekAware.onIdleContainer** là một điểm mở rộng hữu ích để ứng dụng **quyết định seek tại thời điểm listener container idle**, với thông tin assignment và ConsumerSeekCallback do Spring Kafka cung cấp. Nó không tự làm consumer khỏe hơn khi non-responsive, không tự commit offsets và không loại bỏ rủi ro xử lý trùng. Khi được kết hợp với một replay request có kiểm soát, ownership chính xác, thao tác callback ngắn gọn và idempotent processing, seek-on-idle trở thành công cụ vận hành có giá trị mà vẫn giữ được các nguyên tắc reliability của Kafka.
