# RecordFilterStrategy

Trong một consumer Kafka, không phải record nào được đọc từ topic cũng cần đi vào logic nghiệp vụ. Ví dụ hệ thống Fulfillment chỉ xử lý đơn hàng đã xác nhận, còn sự kiện nháp, sự kiện kiểm thử hoặc trạng thái đã bị hủy có thể được bỏ qua. Spring Kafka cung cấp **RecordFilterStrategy** để lọc record trước khi gọi listener.

RecordFilterStrategy nhận một Kafka ConsumerRecord và quyết định record có bị loại khỏi luồng listener hay không. Nếu phương thức `filter(record)` trả về `true`, record bị discard và listener không nhận record đó. Nếu trả về `false`, record tiếp tục tới listener.

Filtering diễn ra ở phía consumer sau khi Kafka đã giao record cho client. Vì vậy, nó giúp tránh gọi logic listener cho record không cần thiết, nhưng không phải cơ chế lọc ở broker và không tự giảm lượng byte consumer phải fetch. Khi dùng filter, cần hiểu thêm cách offset của record bị discard được xác nhận, đặc biệt khi listener sử dụng manual acknowledgment.

Bài học thuộc chương **Filtering và interceptors** của module **SPRING_KAFKA_MESSAGING**, tập trung vào cách cấu hình RecordFilterStrategy trong Spring Kafka, thiết kế điều kiện lọc an toàn và kiểm soát offset, retry cùng khả năng quan sát.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích vai trò của RecordFilterStrategy trong listener container.
- Phân biệt giá trị trả về `true` và `false` của `filter(record)`.
- Cấu hình filter trên ConcurrentKafkaListenerContainerFactory.
- Lọc theo payload, key, header và metadata record.
- Xử lý an toàn record có value null và tombstone.
- Hiểu ảnh hưởng của filter tới AckMode, offset và `ackDiscarded`.
- Phân biệt filtering với RecordInterceptor, validation và broker-side filtering.
- Áp dụng filter cho record listener và batch listener.
- Hiểu tương tác giữa filter, retry, error handler và DLT.
- Kiểm thử record được giữ lại, record bị loại và offset được commit đúng.

## 1. RecordFilterStrategy giải quyết vấn đề gì?

Giả sử topic `orders.created` nhận nhiều loại đơn hàng. Fulfillment chỉ cần xử lý đơn có trạng thái `CONFIRMED`. Nếu mọi record đều đi vào listener rồi mới kiểm tra điều kiện, listener phải thực hiện thêm nhánh điều kiện và có thể gọi nhầm các service nghiệp vụ.

RecordFilterStrategy đặt quyết định loại record ở lớp listener adapter:

~~~text
Kafka topic
    |
    v
Consumer poll
    |
    v
RecordFilterStrategy
    |
    +---- filter(record) = true ----> Discard
    |
    +---- filter(record) = false ---> @KafkaListener
~~~

Ví dụ:

- Giữ record có trạng thái CONFIRMED.
- Bỏ qua record có trạng thái DRAFT.
- Bỏ qua event có header `event_type` không thuộc tập loại mà listener xử lý.
- Bỏ qua record của tenant không thuộc phạm vi consumer.
- Bỏ qua tombstone nếu luồng nghiệp vụ không dùng tombstone để xóa dữ liệu.

Filter nên phản ánh quy tắc chọn record của consumer. Những kiểm tra nghiệp vụ có thể thay đổi trạng thái hệ thống, cần gọi database hoặc cần trả lỗi cho producer thường nên đặt trong service nghiệp vụ thay vì filter.

## 2. Hợp đồng của RecordFilterStrategy

Interface `RecordFilterStrategy<K, V>` làm việc với `ConsumerRecord<K, V>`. Phương thức `filter` trả về boolean:

| Kết quả | Ý nghĩa | Hành vi |
|---|---|---|
| `true` | Record bị lọc | Listener không nhận record này. |
| `false` | Record được giữ | Record tiếp tục tới listener. |

Ví dụ đơn giản:

~~~java
RecordFilterStrategy<String, OrderCreatedEvent> strategy =
        record -> record.value() != null
                && record.value().status() == OrderStatus.CANCELLED;
~~~

Trong ví dụ, record có trạng thái CANCELLED bị discard; record còn lại được chuyển tiếp. Điều kiện null cần được thiết kế theo hợp đồng dữ liệu: value null có thể là tombstone hợp lệ, không nhất thiết là payload hỏng.

Không đảo ngược ý nghĩa boolean. Một lỗi thường gặp là đọc `true` như “accept”; thực tế `true` nghĩa là filter/discard.

## 3. Cấu hình RecordFilterStrategy trong listener container factory

Spring Kafka cho phép gắn strategy vào `ConcurrentKafkaListenerContainerFactory` bằng `setRecordFilterStrategy`.

Ví dụ factory lọc đơn hàng đã hủy:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
filteredOrderFactory(
        ConsumerFactory<String, OrderCreatedEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);

    factory.setRecordFilterStrategy(record -> {
        OrderCreatedEvent event = record.value();

        return event != null
                && event.status() == OrderStatus.CANCELLED;
    });

    return factory;
}
~~~

Gắn factory vào listener:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-fulfillment",
        containerFactory = "filteredOrderFactory"
)
public void consume(OrderCreatedEvent event) {
    fulfillmentService.handle(event);
}
~~~

Với cấu hình này, listener chỉ nhận record không bị strategy loại bỏ. Nếu ứng dụng có nhiều nhóm listener với quy tắc khác nhau, nên tạo factory riêng hoặc cấu hình factory theo từng endpoint để tránh một filter ngoài ý muốn áp dụng cho listener khác.

Filter thuộc listener container, không phải thuộc topic. Cùng một topic có thể được đọc bởi nhiều consumer group với chiến lược lọc khác nhau.

## 4. Lọc theo payload

Khi value đã deserialize thành event object, filter có thể kiểm tra field nghiệp vụ đơn giản và ổn định.

~~~java
factory.setRecordFilterStrategy(record -> {
    OrderCreatedEvent event = record.value();

    if (event == null) {
        return true;
    }

    return event.status() != OrderStatus.CONFIRMED;
});
~~~

Trong ví dụ, chỉ event CONFIRMED được giữ lại. Cần bảo đảm field dùng để lọc có ý nghĩa ổn định và không phụ thuộc vào một trạng thái bên ngoài có thể thay đổi trong lúc consumer chạy.

Không đặt truy vấn database hoặc HTTP call trong filter để quyết định có nhận record hay không. Filter chạy trên đường xử lý của consumer; một lời gọi chậm sẽ kéo dài thời gian xử lý poll, làm tăng lag và có thể ảnh hưởng membership của group.

Nếu điều kiện lọc cần dữ liệu ngoài, cân nhắc đưa quyết định vào listener/service để có retry, timeout, logging và xử lý lỗi rõ ràng.

## 5. Lọc theo key

Kafka key thường thể hiện định danh entity hoặc partition key. Filter có thể dùng key để bỏ qua một nhóm record.

~~~java
Set<String> ignoredTenants = Set.of("tenant-test", "tenant-demo");

factory.setRecordFilterStrategy(record -> {
    String key = record.key();

    return key != null && ignoredTenants.contains(key);
});
~~~

Ví dụ trên giả định key chính là tenant ID. Nếu key là orderId hoặc composite key, không được coi trực tiếp key là tenant. Hãy dùng đúng cấu trúc key đã được công bố trong event contract.

Lọc theo key không thay đổi partition assignment. Consumer vẫn fetch record từ partition chứa key đó; filter chỉ quyết định record có được gọi vào listener hay không.

## 6. Lọc theo Kafka header

Một số luồng có thể phân loại record bằng header như `event_type`, `event_version` hoặc `source_service`.

~~~java
private String headerText(Headers headers, String name) {
    Header header = headers.lastHeader(name);

    if (header == null || header.value() == null) {
        return null;
    }

    return new String(header.value(), StandardCharsets.UTF_8);
}

factory.setRecordFilterStrategy(record -> {
    String eventType = headerText(
            record.headers(),
            "event_type"
    );

    return !"OrderCreated".equals(eventType);
});
~~~

Kafka header có value dạng byte[], vì vậy cần thống nhất encoding giữa producer và consumer. Nếu header trùng tên, `lastHeader` chỉ trả về giá trị cuối; khi hợp đồng cho phép nhiều giá trị, hãy đọc toàn bộ bằng `headers(name)`.

Header là dữ liệu do producer gửi. Không dùng custom header như bằng chứng phân quyền hoặc nguồn gốc đáng tin cậy nếu chưa xác thực theo cơ chế bảo mật của hệ thống.

## 7. Lọc theo metadata record

ConsumerRecord cung cấp metadata như topic, partition, offset, timestamp và key. Có thể dùng các giá trị này cho quy tắc kỹ thuật, ví dụ loại một partition thử nghiệm hoặc chỉ nhận record thuộc topic cụ thể trong một factory dùng chung.

~~~java
factory.setRecordFilterStrategy(record ->
        record.topic().equals("orders.created.replay")
                || record.partition() == 7
);
~~~

Ví dụ này chỉ minh họa cách truy cập metadata. Lọc theo partition cố định thường là dấu hiệu cần xem lại subscription hoặc topic design; không nên dùng như cách thay thế ACL, routing hay consumer group.

Offset có thể dùng để kiểm soát replay trong môi trường kiểm thử hoặc migration có kế hoạch. Với production, một quy tắc lọc theo offset có thể làm bỏ qua dữ liệu nghiệp vụ nếu không có tài liệu và phê duyệt rõ ràng.

## 8. Xử lý value null và tombstone

Kafka cho phép record có value null. Trong compacted topic, record có key và value null thường được dùng làm tombstone để biểu thị xóa key tương ứng theo semantics của log compaction.

Filter cần phân biệt:

- Tombstone hợp lệ theo hợp đồng topic.
- Record value null không mong đợi.
- Payload deserialize thất bại đã được ErrorHandlingDeserializer chuyển thành null kèm exception header.

Ví dụ nếu listener không xử lý tombstone:

~~~java
factory.setRecordFilterStrategy(record -> record.value() == null);
~~~

Nhưng nếu topic dùng tombstone để xóa dữ liệu trong projection, lọc tất cả value null sẽ làm listener không nhận lệnh xóa và dữ liệu downstream có thể tồn tại sai.

Nếu cần phân biệt null hợp lệ với lỗi deserialize, kiểm tra deserialization exception header thay vì chỉ nhìn `record.value() == null`. Lỗi deserialize thường phải đi qua ErrorHandlingDeserializer và error handler; filter không nên vô tình che giấu poison pill.

## 9. Filter và offset commit

Record bị filter không đi vào listener, nhưng consumer đã poll record đó từ Kafka. Vì thế, ứng dụng cần hiểu record bị discard sẽ được xác nhận tiến độ ra sao.

Với các AckMode container-managed như RECORD hoặc BATCH, container quản lý commit theo semantics của mode sau khi adapter xử lý record/batch. Với manual acknowledgment, listener bình thường phải acknowledge sau khi xử lý; record bị filter thì listener không được gọi để tự acknowledge.

Spring Kafka cung cấp thuộc tính `ackDiscarded` để adapter acknowledge record bị discard. Thuộc tính này mặc định là false và đặc biệt hữu ích khi dùng manual acknowledgment.

Ví dụ:

~~~java
factory.setRecordFilterStrategy(
        record -> record.value() == null
);
factory.setAckDiscarded(true);
factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.MANUAL_IMMEDIATE);
~~~

Khi adapter loại record, `ackDiscarded=true` cho phép xác nhận record bị discard theo cơ chế acknowledgment. Hãy kiểm tra đúng AckMode và phiên bản Spring Kafka đang dùng; kiểm thử committed offset để chắc chắn record không bị đọc lại ngoài ý muốn.

Nếu dùng manual ack mà không acknowledge record bị discard, offset có thể không tiến theo kỳ vọng và record có thể được giao lại sau restart/rebalance. Ngược lại, bật ackDiscarded có nghĩa ứng dụng chấp nhận bỏ qua record đó và tiến offset qua nó. Chỉ bật khi quy tắc filter thực sự cho phép loại record.

## 10. RecordFilterStrategy với các AckMode

| AckMode | Cách container xác nhận | Lưu ý khi filter |
|---|---|---|
| RECORD | Commit sau khi record được xử lý thành công | Record bị discard được xử lý qua adapter; xác minh offset trong integration test. |
| BATCH | Commit sau khi xử lý thành công các record của poll | Cần hiểu hành vi khi một phần hoặc toàn bộ batch bị lọc. |
| MANUAL | Listener gọi acknowledge; commit theo semantics manual | Bật ackDiscarded nếu cần xác nhận record bị loại. |
| MANUAL_IMMEDIATE | Acknowledge trên consumer thread có thể commit ngay | ackDiscarded giúp adapter xác nhận record bị loại. |

Không bật `enable.auto.commit=true` nếu muốn listener container quản lý offset theo AckMode. Auto commit có thể xác nhận offset theo lịch độc lập với kết quả xử lý.

Với MANUAL và MANUAL_IMMEDIATE, đọc kỹ cách ứng dụng gọi acknowledgment và cấu hình ackDiscarded. Đừng giả định filter tự động có cùng semantics với listener đã chạy thành công.

## 11. Filtering với batch listener

Một batch listener nhận nhiều ConsumerRecord trong một lần gọi. Spring Kafka có thể áp dụng RecordFilterStrategy cho các record trong batch để loại record không phù hợp trước khi chuyển danh sách còn lại tới listener.

Ví dụ listener batch:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-batch",
        containerFactory = "filteredBatchFactory"
)
public void consume(List<ConsumerRecord<String, OrderCreatedEvent>> records) {
    for (ConsumerRecord<String, OrderCreatedEvent> record : records) {
        batchOrderService.handle(record.value());
    }
}
~~~

Nếu filter loại một phần batch, listener chỉ nên nhận các record còn lại theo semantics của adapter. Nếu tất cả record trong batch bị loại, listener có thể không được gọi. Hành vi batch cụ thể và việc xác nhận offset cần được kiểm thử với phiên bản Spring Kafka đang sử dụng.

Với batch listener, không giả định index trong danh sách sau filter còn tương ứng với index của batch gốc. Nếu cần audit hoặc xác định record bị loại, hãy ghi metadata trước khi danh sách được lọc hoặc dùng một cơ chế quan sát riêng.

## 12. Phân biệt RecordFilterStrategy và RecordInterceptor

Hai extension point đều chạy trước hoặc quanh listener nhưng có mục đích khác nhau.

| Tiêu chí | RecordFilterStrategy | RecordInterceptor |
|---|---|---|
| Mục tiêu | Quyết định discard hay chuyển record tới listener | Quan sát hoặc can thiệp record trước/sau listener |
| Kết quả chính | `true` loại, `false` giữ | Có thể trả record đã chỉnh sửa hoặc null theo contract interceptor |
| Use case | Loại event không thuộc phạm vi xử lý | Gắn context, log, kiểm tra, enrich nhẹ hoặc theo dõi |
| Offset discard | Có thuộc tính ackDiscarded cho record bị filter | Cần hiểu semantics khi interceptor bỏ record |
| Tính phù hợp | Quy tắc chọn record rõ ràng | Cross-cutting behavior quanh listener |

Nếu mục tiêu là quyết định record có thuộc tập dữ liệu listener cần nhận hay không, dùng RecordFilterStrategy. Nếu cần quan sát, bổ sung context hoặc can thiệp vào record trong vòng đời listener, cân nhắc RecordInterceptor.

Không đặt cùng một quy tắc loại record ở cả filter và interceptor nếu không có lý do rõ ràng; điều đó làm khó truy vết vì sao listener không nhận được record.

## 13. Filter không thay thế validation nghiệp vụ

Filtering thường dùng cho record không thuộc phạm vi consumer. Validation kiểm tra record có hợp lệ để thực hiện nghiệp vụ hay không.

Ví dụ:

- Consumer Notification chỉ nhận event OrderCreated, bỏ qua event InventoryReserved: có thể dùng filter theo event type.
- OrderCreated thiếu orderId bắt buộc: đây là dữ liệu không hợp lệ, nên đi qua validation/error handling và có thể DLT.
- Đơn hàng đã bị hủy nhưng event vẫn tới: cần xác minh trạng thái nghiệp vụ; không phải lúc nào cũng nên âm thầm filter.

Nếu filter loại dữ liệu lỗi, hệ thống có thể mất khả năng điều tra và producer không biết dữ liệu sai. Với poison pill hoặc schema không tương thích, dùng ErrorHandlingDeserializer và error handler phù hợp thay vì cố filter sau deserialize.

## 14. Filter không phải broker-side filtering

RecordFilterStrategy chạy ở phía consumer sau khi record được poll và deserialize. Kafka broker không chạy predicate Java của ứng dụng để chỉ gửi các record phù hợp.

Điều đó có nghĩa:

- Record bị loại vẫn tiêu thụ network và fetch capacity.
- Consumer vẫn phải deserialize key/value trước khi filter chạy.
- Filter giảm số lần listener và business service được gọi, không tự giảm lượng dữ liệu lưu trong topic.
- Nếu nhiều consumer group cần tập record khác nhau, mỗi group có thể fetch cùng luồng và áp dụng filter riêng.
- Nếu cần giảm lưu lượng hoặc tách quyền sở hữu dữ liệu, hãy cân nhắc topic riêng, routing ở producer hoặc stream processing.

Không dùng RecordFilterStrategy như cơ chế bảo mật để ngăn consumer đọc dữ liệu không được phép. Dùng ACL, topic separation và quyền truy cập phù hợp.

## 15. Filter tương tác với retry và DLT

Record bị filter không đi vào listener nên listener không ném exception cho record đó. Vì vậy retry của listener và error handler không phải cơ chế để xử lý một record bị discard theo filter.

Nếu filter strategy tự ném exception, đó là lỗi trong quá trình xử lý filter, không phải kết quả discard bình thường. Hãy giữ filter đơn giản, deterministic và không gọi dependency bên ngoài. Nếu filter thất bại do lỗi hệ thống, cần để lỗi được quan sát và xử lý theo error path phù hợp thay vì trả true để âm thầm loại record.

Retry/DLT phù hợp với record đã được chuyển vào listener nhưng xử lý thất bại, hoặc lỗi deserialize được error handler nhận diện. Filter phù hợp với record hợp lệ nhưng không thuộc phạm vi listener.

Một quy tắc filter quá rộng có thể loại record quan trọng mà không tạo DLT. Do đó nên có metric đếm record bị loại và log metadata đủ để audit.

## 16. Thiết kế filter deterministic và an toàn

Filter tốt nên là hàm quyết định đơn giản, lặp lại cùng kết quả với cùng record.

Nguyên tắc:

- Không gọi database, HTTP hoặc service bên ngoài trong filter.
- Không sửa trạng thái nghiệp vụ hoặc tạo side effect.
- Không dựa vào thời gian hiện tại nếu không có yêu cầu rõ ràng.
- Xử lý null key/value và header thiếu.
- Dùng enum/constant thay vì chuỗi rải rác.
- Ghi rõ quy tắc filter và lý do loại record.
- Có metric theo loại lý do, tránh label có cardinality quá lớn.
- Version hóa hợp đồng header/payload mà filter dựa vào.

Nếu filter phụ thuộc cấu hình runtime, hãy đảm bảo mọi replica nhận cùng cấu hình và có cách quan sát phiên bản rule đang hoạt động. Thay đổi filter có thể làm thay đổi record nào được xử lý và offset group tiến qua dữ liệu ra sao.

## 17. Quan sát record bị filter

Vì listener không được gọi với record bị discard, log trong listener không thể đếm đầy đủ các record bị loại. Nên bổ sung metric hoặc logging tại filter strategy hoặc một wrapper có kiểm soát.

Thông tin hữu ích:

- Topic, partition và offset.
- Loại event hoặc giá trị enum dùng để quyết định.
- Lý do filter.
- Consumer group hoặc listener ID.
- Số record bị loại theo thời gian.
- Số record được giữ lại.
- Tỷ lệ discard so với tổng record poll.

Ví dụ:

~~~java
factory.setRecordFilterStrategy(record -> {
    OrderCreatedEvent event = record.value();

    boolean discard = event == null
            || event.status() == OrderStatus.CANCELLED;

    if (discard) {
        filteredCounter.increment();
        log.debug(
                "Discarding record topic={}, partition={}, offset={}",
                record.topic(),
                record.partition(),
                record.offset()
        );
    }

    return discard;
});
~~~

Trong production, tránh log toàn bộ payload hoặc key có thông tin nhạy cảm. Dùng metric có nhãn giới hạn; không đưa orderId hoặc customerId riêng lẻ làm metric label.

Nếu số record bị loại tăng đột biến, có thể producer đổi event contract, filter config sai hoặc một loại sự kiện mới đang bị loại. Cần cảnh báo theo tỷ lệ discard bất thường chứ không chỉ theo số tuyệt đối.

## 18. Kiểm thử RecordFilterStrategy

Kiểm thử cần xác minh cả hành vi listener và offset group sau khi filter.

| Kịch bản | Điều cần xác minh |
|---|---|
| Record được giữ | Listener nhận record đúng một lần theo delivery semantics. |
| Record bị loại | Listener không được gọi cho record đó. |
| Null value/tombstone | Được giữ hoặc loại theo hợp đồng topic. |
| Header thiếu | Filter áp dụng fallback đã định nghĩa, không ném lỗi ngoài ý muốn. |
| Key null | Không gây NullPointerException. |
| Header trùng tên | Chọn đúng lastHeader hoặc xử lý toàn bộ danh sách. |
| Manual ack + ackDiscarded | Offset của record bị loại tiến theo chính sách đã chọn. |
| Record listener | Filter và commit hoạt động đúng với AckMode.RECORD. |
| Batch listener | Kiểm tra batch còn record, batch rỗng và offset. |
| Retry/DLT | Record được giữ nhưng listener lỗi đi vào error handler; record bị filter không bị hiểu nhầm là retry. |
| Nhiều consumer group | Mỗi group áp dụng filter riêng mà không ảnh hưởng group khác. |

Ví dụ integration test có thể gửi hai record, một record CONFIRMED và một record CANCELLED. Xác minh listener chỉ nhận CONFIRMED; sau đó dùng AdminClient đọc committed offset để kiểm tra consumer group đã tiến qua record bị loại theo AckMode và ackDiscarded đã cấu hình.

Dùng EmbeddedKafka hoặc Testcontainers để kiểm tra listener container thật. Dùng Awaitility/latch có timeout thay vì Thread.sleep cố định. Nếu test manual acknowledgment, cần kiểm tra riêng trường hợp ackDiscarded bật và tắt.

## 19. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Đảo ngược boolean của filter | Loại record cần xử lý hoặc giữ record không mong muốn | Nhớ true = discard, false = keep. |
| Không xử lý null value | NullPointerException hoặc loại nhầm tombstone | Xác định rõ null theo contract. |
| Dùng filter để kiểm tra database | Poll bị chậm và lỗi dependency làm filter không ổn định | Đưa kiểm tra vào listener/service. |
| Nghĩ filter giảm broker/network traffic | Consumer vẫn fetch record | Dùng topic/routing/stream processing nếu cần giảm traffic. |
| Dùng filter để loại payload sai | Mất dấu poison pill và không có DLT | Dùng ErrorHandlingDeserializer và error handler. |
| Manual ack nhưng quên ackDiscarded | Offset record bị loại có thể không tiến như kỳ vọng | Cấu hình và test ackDiscarded. |
| Filter theo header không kiểm tra encoding | Lỗi parse hoặc quyết định sai | Thống nhất UTF-8 và xử lý header thiếu/trùng. |
| Cấu hình filter ở factory dùng chung ngoài ý muốn | Listener khác bị loại record | Dùng factory riêng cho từng nhóm chính sách. |
| Không đo số record bị loại | Khó phát hiện filter sai hoặc contract thay đổi | Thêm counter và cảnh báo discard rate. |
| Dùng filter thay validation nghiệp vụ | Bỏ qua lỗi dữ liệu cần điều tra | Phân biệt out-of-scope event với invalid event. |

## 20. Bài tập tổng hợp: lọc OrderCreatedEvent

Hãy xây dựng consumer Fulfillment cho topic `orders.created`.

Yêu cầu:

1. Tạo `ConcurrentKafkaListenerContainerFactory` riêng cho Fulfillment.
2. Cấu hình RecordFilterStrategy chỉ giữ event có trạng thái CONFIRMED.
3. Bỏ qua event CANCELLED và DRAFT theo quy tắc được mô tả.
4. Xử lý null value và tombstone theo hợp đồng topic.
5. Thêm filter theo header `event_type` và kiểm tra trường hợp header thiếu.
6. Tạo listener dùng factory đã cấu hình.
7. Thử `AckMode.RECORD` và `AckMode.MANUAL_IMMEDIATE`.
8. Bật/tắt `ackDiscarded` và quan sát committed offset.
9. Gửi record có key null và header trùng tên.
10. Thử batch listener với một phần record bị loại và toàn bộ batch bị loại.
11. Gửi record được giữ nhưng listener ném exception để kiểm tra retry/DLT.
12. Đếm record bị filter bằng metric và log topic/partition/offset.
13. Chạy hai consumer group có filter khác nhau trên cùng topic.
14. Viết integration test xác minh listener invocation, filter count và committed offset.

Bài tập hoàn thành khi bạn chứng minh được record nào bị discard, record nào được chuyển vào listener, offset tiến đúng theo AckMode và lỗi nghiệp vụ vẫn đi qua retry/DLT thay vì bị filter che giấu.

## 21. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Filter contract | RecordFilterStrategy boolean | Giải thích đúng true = discard, false = keep. |
| 2. Factory | setRecordFilterStrategy | Gắn filter vào đúng listener container. |
| 3. Predicate | Payload, key, header, metadata | Viết điều kiện an toàn với null và encoding. |
| 4. Tombstone | Null value và compacted topic | Không loại nhầm lệnh xóa hợp lệ. |
| 5. Offset | AckMode và ackDiscarded | Xác minh offset record bị loại được xử lý đúng. |
| 6. Listener modes | Record và batch listener | Kiểm thử partial/empty batch. |
| 7. Extension points | Filter và interceptor | Chọn đúng cơ chế cho mục đích. |
| 8. Error handling | Retry, DLT và deserialize failure | Không che giấu poison pill hoặc lỗi nghiệp vụ. |
| 9. Operations | Metrics và filter audit | Theo dõi được discard rate và lý do. |
| 10. Testing | Integration test và committed offset | Chứng minh hành vi filter cùng offset. |

Bài học hoàn thành khi bạn có thể cấu hình RecordFilterStrategy, viết predicate an toàn, giải thích tác động của ackDiscarded tới manual acknowledgment và kiểm thử được offset sau khi record bị loại. Bạn cũng cần phân biệt rõ filter với interceptor, validation và cơ chế lọc ở broker.

RecordFilterStrategy giúp listener chỉ nhận record thuộc phạm vi cần xử lý. Vì filter chạy sau khi consumer fetch và deserialize record, nó chủ yếu giảm công việc ở listener. Hãy giữ predicate đơn giản, xác định rõ semantics của offset và quan sát số record bị loại để bảo đảm filter không âm thầm bỏ qua dữ liệu quan trọng.

