# Phân vùng để gom thông điệp theo khóa nghiệp vụ

Trong hệ thống xử lý sự kiện, nhiều thông điệp có liên quan cần được xử lý bởi cùng một luồng hoặc cùng một instance để giữ trạng thái và thứ tự nghiệp vụ. Ví dụ, các sự kiện tạo đơn, thanh toán, cập nhật và hủy của cùng một đơn hàng nên đi theo cùng một partition. Nếu chúng bị phân tán tùy ý, hai consumer có thể cập nhật cùng một đơn hàng đồng thời hoặc hoàn tất các bước theo thứ tự không mong muốn.

Spring Cloud Stream cung cấp abstraction partitioning để producer chọn partition dựa trên khóa của từng message và consumer nhận các partition theo cách phù hợp với binder. Khóa thường là một định danh nghiệp vụ ổn định như orderId, accountId, customerId hoặc sensorId. Với Kafka, partition là cấu trúc native của topic. Với RabbitMQ, binder có thể mô phỏng partition bằng các queue riêng. Với Pulsar, topic phân vùng và key-based routing có cơ chế riêng của Pulsar. Cần hiểu cả abstraction chung lẫn cách binder triển khai để cấu hình đúng.

## 1. Vì sao cần phân vùng theo khóa?

Partitioning chia dữ liệu thành nhiều phần độc lập. Producer tính khóa cho message rồi chọn partition đích. Những message có cùng khóa được ánh xạ vào cùng partition theo thuật toán nhất quán. Consumer group chia các partition cho nhiều consumer instance để tăng khả năng xử lý song song.

Ví dụ với các sự kiện đơn hàng:

| Message | Khóa nghiệp vụ | Partition |
|---|---|---|
| OrderCreated ORD-1001 | ORD-1001 | 2 |
| PaymentReceived ORD-1001 | ORD-1001 | 2 |
| OrderShipped ORD-1001 | ORD-1001 | 2 |
| OrderCreated ORD-1002 | ORD-1002 | 4 |
| PaymentReceived ORD-1002 | ORD-1002 | 4 |

Các sự kiện của ORD-1001 cùng đi vào partition 2; các sự kiện của ORD-1002 cùng đi vào partition 4. Hai partition có thể được xử lý song song, nhưng các sự kiện của cùng một khóa được gom vào cùng một đơn vị phân vùng.

Partitioning hữu ích khi:

- Cần giữ thứ tự các sự kiện của cùng aggregate hoặc thực thể nghiệp vụ.
- Consumer duy trì trạng thái cục bộ theo khóa, chẳng hạn tổng số dư của một tài khoản hoặc trạng thái một đơn hàng.
- Cần mở rộng thông lượng bằng nhiều partition và consumer.
- Cần tránh nhiều instance cùng cập nhật một trạng thái theo khóa.

Partitioning không tự bảo đảm xử lý đúng một lần, không thay thế idempotency và không tạo thứ tự toàn cục giữa các partition. Nó chỉ xác định cách nhóm dữ liệu và phân phối công việc. Ứng dụng vẫn cần xử lý retry, redelivery, giao dịch và duplicate theo yêu cầu nghiệp vụ.

## 2. Phân biệt partition, consumer group và instance

Ba khái niệm này liên quan nhưng không đồng nghĩa:

| Khái niệm | Vai trò |
|---|---|
| Partition | Một phần của destination, giữ một luồng dữ liệu có thứ tự riêng theo khả năng của broker |
| Consumer group | Nhóm consumer cùng chia sẻ việc đọc dữ liệu; mỗi group có tiến độ tiêu thụ riêng |
| Consumer instance | Một tiến trình/replica ứng dụng đang chạy và nhận một hoặc nhiều partition |

Trong Kafka, mỗi partition trong một consumer group tại một thời điểm được gán cho tối đa một consumer trong group đó. Một consumer có thể nhận nhiều partition. Nếu số consumer đang hoạt động lớn hơn số partition, một số consumer sẽ không có partition để đọc. Nếu số partition lớn hơn số consumer, một consumer có thể nhận nhiều partition.

Các message cùng key được gom vào cùng partition; consumer instance đang sở hữu partition đó có thể thay đổi sau rebalance hoặc khi triển khai lại. Vì vậy, partitioning giúp giữ nhóm dữ liệu cùng luồng đọc, nhưng không bảo đảm một process cụ thể sẽ sở hữu key đó suốt vòng đời ứng dụng.

Các consumer group khác nhau đọc độc lập. Ví dụ group order-projection và group audit-service đều có thể nhận cùng một sự kiện, mỗi group duy trì tiến độ riêng. Trong cùng một group, các consumer chia dữ liệu để mở rộng xử lý; chúng không nhận bản sao độc lập của mọi message.

Với RabbitMQ và các binder mô phỏng partition bằng queue, cách gán queue cho instance khác với cơ chế Kafka. Với Pulsar, subscription type và partitioned topic quyết định cách phân phối. Không áp dụng một sơ đồ gán consumer cho mọi broker chỉ vì cùng dùng Spring Cloud Stream.

## 3. Hai phía đều phải cấu hình partitioning

Một kịch bản partitioned processing cần cấu hình cả producer lẫn consumer:

1. Producer trích partition key từ message và xác định partition đích.
2. Broker/binder lưu hoặc định tuyến message vào partition tương ứng.
3. Consumer group nhận các partition và phân công chúng cho các instance.
4. Consumer xử lý dữ liệu trong partition được giao, duy trì thứ tự và trạng thái theo thiết kế.

Nếu producer chỉ gửi khóa nhưng không bật partitioning hoặc consumer không đọc đúng partition, việc gom nhóm theo nghiệp vụ sẽ không đạt mục tiêu. Nếu các producer không thống nhất partition count hoặc thuật toán chọn partition, cùng một khóa có thể đi đến các partition khác nhau. Consumer cũng cần được cấu hình đúng số instance và cơ chế gán partition để không bỏ sót partition.

## 4. Chọn partition key từ dữ liệu nghiệp vụ

Trong Spring Cloud Stream, producer có thể dùng thuộc tính partitionKeyExpression để trích khóa bằng SpEL. Biểu thức được đánh giá trên outbound message. Ví dụ:

    spring:
      cloud:
        stream:
          bindings:
            publishOrder-out-0:
              destination: orders.events
              producer:
                partition-key-expression: payload.orderId
                partition-count: 6
          instance-count: 3

Nếu message có payload:

    public record OrderCreated(
        String eventId,
        String orderId,
        long total
    ) {}

thì biểu thức payload.orderId lấy orderId làm partition key. Một sự kiện thanh toán hoặc giao hàng cũng cần dùng cùng khóa orderId nếu chúng phải được gom với các sự kiện khác của đơn hàng.

Nếu một output binding nhận nhiều DTO có cấu trúc khác nhau, không giả định mọi payload đều có thuộc tính orderId. Có thể chuẩn hóa khóa trong một envelope chung, chẳng hạn aggregateId, hoặc đặt một header chuẩn trên mọi message:

    partition-key-expression: headers['aggregateId']

Producer của OrderCreated, PaymentReceived và OrderShipped đều phải gắn cùng aggregateId cho cùng đơn hàng. Cách này giữ một quy ước khóa nhất quán dù payload của từng event khác nhau.

Khi ứng dụng producer được triển khai thành nhiều replica, đặt spring.cloud.stream.instanceCount bằng tổng số replica theo yêu cầu của Spring Cloud Stream. Ví dụ cấu hình ở trên đặt instance-count là 3 cho ba producer instance. Nếu chạy độc lập, mỗi instance phải nhận đúng thông tin triển khai; môi trường như Spring Cloud Data Flow có thể cấp các giá trị này tự động.

Có thể trích khóa từ header:

    partition-key-expression: headers['accountId']

Chỉ dùng header nếu producer luôn gắn header đó, kiểu dữ liệu ổn định và consumer/binder giữ đúng metadata cần thiết. Nếu khóa là một phần của hợp đồng nghiệp vụ, đặt nó trong payload hoặc có quy ước header được tài liệu hóa rõ ràng.

Khóa tốt cần có các đặc điểm:

- Ổn định trong suốt vòng đời của aggregate.
- Có mặt trên mọi loại sự kiện cần được gom chung.
- Phân bố đủ đều giữa các partition.
- Không chứa dữ liệu nhạy cảm không cần thiết.
- Không phụ thuộc vào object identity hoặc giá trị ngẫu nhiên được tạo lại ở mỗi lần gửi.

Ví dụ, orderId phù hợp cho luồng sự kiện đơn hàng; accountId phù hợp cho luồng cập nhật số dư; sensorId phù hợp cho chuỗi số đo của cùng cảm biến. Dùng timestamp hoặc UUID mới cho từng message thường làm các message liên quan bị phân tán, vì mỗi message có khóa khác nhau.

### Kiểm tra khóa bị thiếu

Nếu partition key rỗng hoặc null, message có thể rơi vào cùng một partition mặc định, lỗi khi tính partition hoặc tạo phân bố tải không mong muốn tùy binder. Hãy xác thực khóa trước khi publish:

    public boolean publish(OrderCreated event) {
        if (event.orderId() == null || event.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required for partitioning");
        }
        return streamBridge.send("publishOrder-out-0", event);
    }

Không dùng một giá trị mặc định chung cho mọi message lỗi, vì điều đó có thể tạo partition nóng. Nếu không có khóa nghiệp vụ hợp lệ, hãy từ chối message hoặc chuyển sang luồng lỗi theo chính sách.

## 5. Cách Spring Cloud Stream chọn partition

Producer partitioned cần cấu hình đúng một trong hai thuộc tính:

- partitionKeyExpression: biểu thức SpEL lấy khóa từ outbound message.
- partitionKeyExtractorName: tên bean triển khai PartitionKeyExtractorStrategy để trích khóa bằng Java.

Đồng thời, partitionCount phải lớn hơn 1. Hai cách trích khóa loại trừ lẫn nhau; không cấu hình cả hai cho cùng binding.

Sau khi lấy được key, Spring Cloud Stream chọn partition trong khoảng từ 0 đến partitionCount - 1. Mặc định, thuật toán dựa trên hashCode của key chia cho partitionCount. Có thể tùy biến bằng partitionSelectorExpression hoặc bean PartitionSelectorStrategy.

Ví dụ dùng partition selector expression:

    spring:
      cloud:
        stream:
          bindings:
            publishOrder-out-0:
              destination: orders.events
              producer:
                partition-key-expression: payload.orderId
                partition-selector-expression: key.hashCode() % 6
                partition-count: 6

Trong đa số trường hợp, selector mặc định đã đủ. Chỉ tùy biến khi có yêu cầu rõ về thuật toán phân bố hoặc cần tương thích với hệ thống khác. Producer và consumer không tự trao đổi thuật toán; chúng phải cùng hiểu cách phân vùng đã được triển khai.

Thuật toán mặc định dựa trên hàm hash của đối tượng key trong Java. Với chuỗi Java, hashCode có kết quả ổn định theo nội dung chuỗi; với object tự tạo, không dùng implementation mặc định dựa trên identity nếu message được tạo lại ở tiến trình khác. Nếu có producer viết bằng nhiều ngôn ngữ hoặc cần tính partition độc lập với JVM, hãy công bố thuật toán hash/selector dùng chung và kiểm thử cùng một bộ khóa trên mọi producer. Không giả định các ngôn ngữ khác nhau tạo cùng partition chỉ vì chuỗi key giống nhau.

### Dùng PartitionKeyExtractorStrategy

Nếu khóa cần kết hợp nhiều trường hoặc cần quy tắc phức tạp hơn SpEL, có thể đăng ký bean triển khai PartitionKeyExtractorStrategy:

    @Bean
    PartitionKeyExtractorStrategy orderKeyExtractor() {
        return message -> {
            OrderCreated event = (OrderCreated) message.getPayload();
            return event.orderId();
        };
    }

Sau đó chọn bean trong cấu hình:

    spring:
      cloud:
        stream:
          bindings:
            publishOrder-out-0:
              destination: orders.events
              producer:
                partition-key-extractor-name: orderKeyExtractor
                partition-count: 6

Nếu có nhiều bean cùng kiểu, chỉ định rõ tên extractor. Không khai báo đồng thời partition-key-expression và partition-key-extractor-name trên cùng binding.

## 6. Chọn số lượng partition

partitionCount xác định số partition mà producer abstraction dùng để chọn đích. Giá trị phải lớn hơn 1 khi bật partitioning. Với Kafka, partitionCount được xem là một gợi ý; số partition thực tế của topic nếu lớn hơn giá trị cấu hình sẽ được dùng theo quy tắc của binder. Hãy kiểm tra topic đã tồn tại và số partition thật thay vì chỉ dựa vào YAML.

Chọn partition count cần cân nhắc:

- Thông lượng dự kiến và kích thước message.
- Số consumer instance có thể chạy đồng thời.
- Số lượng khóa nghiệp vụ và phân bố của chúng.
- Chi phí file, metadata, replication và quản trị của broker.
- Nhu cầu tăng tải trong tương lai.
- Yêu cầu giữ thứ tự theo key.

Ví dụ có 6 partition và 3 consumer instance. Nếu mỗi instance có thể nhận 2 partition, cả 6 partition đều có consumer xử lý. Nếu chỉ có 2 partition, tối đa 2 consumer trong một group có thể hoạt động đồng thời trên các partition đó; instance còn lại sẽ không có partition.

Không nên tạo số partition quá lớn khi chưa có nhu cầu. Mỗi partition tăng chi phí quản lý và có thể ảnh hưởng thời gian rebalance, phục hồi và lưu trữ. Ngược lại, quá ít partition giới hạn mức song song ngay cả khi ứng dụng có nhiều instance.

### Thay đổi partition count có thể đổi nơi nhận của một key

Với thuật toán hash modulo, partition của một key phụ thuộc partition count. Khi tăng số partition, nhiều key có thể được ánh xạ sang partition mới. Các message cũ vẫn nằm ở partition cũ, trong khi message mới của cùng key có thể sang partition khác. Khi đó, không còn một thứ tự đọc duy nhất cho toàn bộ lịch sử của key.

Vì vậy, thay đổi partition count là thay đổi vận hành có ảnh hưởng đến thứ tự. Trước khi tăng, hãy đánh giá:

- Consumer có cần thứ tự xuyên suốt toàn bộ lịch sử của aggregate không?
- Có thể dừng producer, drain dữ liệu cũ rồi chuyển đổi không?
- Có cần tạo destination versioned và chuyển dữ liệu theo một quy trình có kiểm soát không?
- Các state store hoặc projection có cần rebuild không?

Không tăng partition count tùy tiện chỉ để xử lý lag nếu luồng nghiệp vụ phụ thuộc thứ tự theo key.

## 7. Cấu hình consumer theo binder

Spring Cloud Stream có thuộc tính consumer.partitioned để báo input binding nhận dữ liệu được phân vùng. Các thuộc tính instanceCount và instanceIndex xác định tổng số instance và chỉ số của instance hiện tại trong những binder cần ứng dụng tự ánh xạ partition. Ví dụ tiếp theo minh họa chế độ consumer partition-aware cần chỉ số instance, thường gặp với binder không có partition native như RabbitMQ; không áp dụng nguyên xi cho Kafka với auto rebalance mặc định.

Ví dụ cấu hình cho một consumer partition-aware với ba instance:

    spring:
      cloud:
        function:
          definition: updateOrder
        stream:
          instance-count: 3
          instance-index: 0
          bindings:
            updateOrder-in-0:
              destination: orders.events
              group: order-projection
              consumer:
                partitioned: true

Mỗi replica phải có cùng instance-count và instance-index duy nhất trong khoảng từ 0 đến instance-count - 1. Với ba replica, các chỉ số lần lượt là 0, 1 và 2. Không để hai replica dùng cùng index nếu binder dùng chỉ số đó để phân công queue/partition.

### Kafka

Kafka có partition native trên topic. Mặc định, Kafka consumer group tự rebalance và phân phối các partition cho các consumer đang hoạt động. Với autoRebalanceEnabled=true (mặc định), instanceCount và instanceIndex không cần thiết chỉ để Kafka phân phối partition.

Ví dụ consumer group:

    spring:
      cloud:
        function:
          definition: updateOrder
        stream:
          bindings:
            updateOrder-in-0:
              destination: orders.events
              group: order-projection
              consumer:
                concurrency: 2
          kafka:
            bindings:
              updateOrder-in-0:
                consumer:
                  auto-rebalance-enabled: true

Kafka binder có thể đặt concurrency cho mỗi instance; tổng số consumer trong group còn phụ thuộc số replica. Với 3 replica và concurrency 2, có thể có tối đa 6 consumer trong group. Nếu topic chỉ có 4 partition, tối đa 4 consumer có partition được gán; các consumer còn lại sẽ nhàn rỗi.

Khi autoRebalanceEnabled=false, binder dùng instanceCount và instanceIndex để quyết định instance nhận partition nào. Khi đó phải bảo đảm số partition đủ cho số instance và các chỉ số được cấu hình chính xác. Chỉ tắt auto rebalance khi có lý do vận hành cụ thể và đã kiểm thử việc phân công, phục hồi instance.

### RabbitMQ

RabbitMQ không có partition native giống Kafka. Rabbit binder có thể mô phỏng partition bằng nhiều queue, mỗi queue đại diện cho một partition. Khi dùng cơ chế này, consumer cần bật partitioned và cấu hình instanceCount/instanceIndex để mỗi instance nhận đúng queue hoặc tập queue được phân công.

Ví dụ:

    spring:
      cloud:
        stream:
          instance-count: 3
          instance-index: 0
          bindings:
            updateOrder-in-0:
              destination: orders.events
              group: order-projection
              consumer:
                partitioned: true

Binder provision các queue phân vùng theo cấu hình và quy tắc đặt tên của phiên bản Rabbit binder. Hãy xác minh queue thực tế trong RabbitMQ Management UI, routing key và binding của exchange. Cấu hình partitionCount ở producer phải tương thích với số partition/queue đã provision.

### Pulsar

Pulsar hỗ trợ partitioned topic và định tuyến theo key ở tầng client/broker. Subscription type, key-based batching và cơ chế phân phối ảnh hưởng đến việc các message cùng key được xử lý. Khi dùng Pulsar binder, hãy kiểm tra phiên bản binder hỗ trợ những thuộc tính partitioning nào và cách ánh xạ partitionKeyExpression sang key/partition native.

Không giả định consumer.partitioned, instanceIndex và instanceCount có cùng vai trò trên mọi Pulsar binder. Ưu tiên cấu hình topic phân vùng và key-based routing theo hướng dẫn của binder/client đang dùng; kiểm thử nhiều consumer trong cùng subscription để xác nhận các message cùng key được giao theo yêu cầu.

## 8. Khóa phân vùng không đồng nghĩa với broker record key

Partition key trong abstraction Spring Cloud Stream là giá trị được dùng để chọn partition. Việc giá trị này có đồng thời được ghi thành native message key của broker hay không phụ thuộc binder và cấu hình riêng.

Với Kafka, record key có thể được dùng bởi partitioner native của Kafka và được consumer đọc lại. Nếu ứng dụng downstream hoặc công cụ vận hành phụ thuộc vào record key, hãy cấu hình message key theo Kafka binder, ví dụ:

    spring:
      cloud:
        stream:
          kafka:
            bindings:
              orders-out-0:
                producer:
                  message-key-expression: headers['orderId']

Producer cần gắn header orderId tương ứng vào message trước khi gửi. Trong các phiên bản Kafka binder có thuộc tính messageKeyExpression, biểu thức này được dùng để đặt key của Kafka record. Kiểm tra tài liệu binder đang dùng vì cách đánh giá biểu thức và kiểu dữ liệu có thể phụ thuộc phiên bản. Đừng mặc định rằng partitionKeyExpression luôn đồng nghĩa với record key trong mọi binder/cấu hình.

Với RabbitMQ, routing key điều khiển định tuyến qua exchange; nó không hoàn toàn tương đương partition key của Spring Cloud Stream. Với Pulsar, message key có semantics và cấu hình riêng. Khi tích hợp nhiều broker hoặc nhiều ngôn ngữ, hãy tài liệu hóa rõ key nào dùng cho phân vùng, key nào dùng cho nghiệp vụ và key nào được lưu trong wire message.

## 9. Tránh partition nóng và phân bố lệch

Nếu một khóa chiếm phần lớn traffic, partition tương ứng sẽ nhận tải lớn hơn các partition khác. Ví dụ dùng tenantId làm khóa có thể gây nóng nếu một tenant tạo nhiều message hơn tất cả tenant còn lại. Một số nguyên nhân thường gặp:

- Khóa có cardinality thấp, nhiều message dùng cùng một giá trị.
- Dùng giá trị mặc định cho mọi message thiếu khóa.
- Một khách hàng hoặc tài khoản có lưu lượng vượt trội.
- Hash/selector tùy chỉnh tạo phân bố không đều.
- Một số partition có consumer chậm hoặc downstream bị nghẽn.

Theo dõi message rate, byte rate, consumer lag và thời gian xử lý theo partition. Nếu một partition nóng do đặc thù nghiệp vụ, tăng tổng partition count có thể không giải quyết được vì cùng một key vẫn phải đi cùng partition để giữ thứ tự. Có thể cần chia nhỏ aggregate, dùng khóa con khi semantics cho phép, hoặc xử lý riêng nhóm tải lớn.

Không thêm random suffix vào key chỉ để cân bằng tải nếu các sự kiện của cùng aggregate cần thứ tự. Cách đó phá vỡ mục tiêu gom nhóm và có thể làm state bị cập nhật đồng thời.

## 10. Thứ tự, concurrency và trạng thái nghiệp vụ

Partitioning giữ các message cùng key trong cùng partition theo thuật toán đã chọn. Broker có thể giữ thứ tự trong partition, nhưng consumer xử lý song song vẫn có thể làm thứ tự hoàn tất nghiệp vụ thay đổi.

Ví dụ, consumer nhận hai sự kiện theo thứ tự:

1. OrderCreated ORD-1001
2. PaymentReceived ORD-1001

Nếu xử lý đồng thời, PaymentReceived có thể hoàn tất trước khi OrderCreated commit. Nếu nghiệp vụ yêu cầu tuần tự, hãy xử lý tuần tự theo partition hoặc theo aggregate key, dùng transaction/idempotency và chỉ ack/commit sau khi công việc cần thiết hoàn tất.

Trong Kafka, một partition tại một thời điểm được gán cho tối đa một consumer trong cùng group, nhưng ứng dụng vẫn có thể đưa record vào executor riêng và làm mất thứ tự hoàn tất. Trong RabbitMQ, nhiều consumer cạnh tranh trên queue hoặc prefetch lớn cũng có thể khiến thứ tự xử lý khác thứ tự gửi. Với Pulsar, subscription type và key-based routing cần được chọn phù hợp.

## 11. Ví dụ hoàn chỉnh cho sự kiện đơn hàng

Producer gửi các event cùng orderId vào một output binding:

    @Service
    public class OrderPublisher {
        private final StreamBridge streamBridge;

        public OrderPublisher(StreamBridge streamBridge) {
            this.streamBridge = streamBridge;
        }

        public boolean publish(OrderEvent event) {
            if (event.orderId() == null || event.orderId().isBlank()) {
                throw new IllegalArgumentException("orderId is required");
            }
            return streamBridge.send("orders-out-0", event);
        }
    }

Cấu hình producer:

    spring:
      cloud:
        stream:
          instance-count: 3
          bindings:
            orders-out-0:
              destination: orders.events
              producer:
                partition-key-expression: payload.orderId
                partition-count: 6

Consumer Kafka:

    spring:
      cloud:
        function:
          definition: updateOrder
        stream:
          bindings:
            updateOrder-in-0:
              destination: orders.events
              group: order-projection
              consumer:
                concurrency: 2

Trong ví dụ, producer dùng orderId để chọn một trong sáu partition. Consumer group order-projection đọc topic và Kafka phân phối partition cho các consumer theo cơ chế rebalance mặc định. Nếu triển khai ba replica, mỗi replica có thể dùng concurrency 2; số consumer có partition thực tế không vượt quá số partition có thể gán.

Nếu chuyển sang RabbitMQ, giữ ý tưởng cùng khóa nghiệp vụ nhưng kiểm tra cách binder tạo queue phân vùng và cấu hình consumer.partitioned cùng instanceCount/instanceIndex. Nếu chuyển sang Pulsar, kiểm tra partitioned topic, key-based routing và subscription type. Không sao chép nguyên cấu hình Kafka sang binder khác.

## 12. Kiểm thử partitioning

Kiểm thử nên xác minh cả việc trích khóa lẫn phân phối thực tế:

- Tạo nhiều message cùng orderId và xác nhận chúng được chọn cùng partition.
- Tạo message với orderId khác nhau và kiểm tra phân bố trên nhiều partition.
- Gửi message thiếu khóa và xác nhận producer từ chối hoặc chuyển vào luồng lỗi theo chính sách.
- Thay đổi partition count trong môi trường thử nghiệm để quan sát việc ánh xạ key thay đổi.
- Chạy nhiều consumer instance và xác nhận mỗi partition được phân công đúng theo binder.
- Kiểm tra rebalance khi instance dừng hoặc khởi động lại.
- Đo thứ tự nhận và thứ tự commit nghiệp vụ khi consumer xử lý đồng thời.
- Kiểm tra partition nóng bằng dữ liệu có phân bố lệch giống production.

Test Binder hữu ích để kiểm tra logic function và cấu hình binding trong phạm vi ứng dụng. Nó không thay thế integration test với broker thật khi cần xác nhận partition vật lý, queue provisioning, key routing, rebalance, ordering và consumer assignment. Hãy có bài kiểm thử riêng cho Kafka, RabbitMQ hoặc Pulsar được triển khai.

## 13. Vận hành và giám sát

Trong production, theo dõi:

- Số partition và trạng thái provision của destination.
- Số consumer đang hoạt động trong từng group/subscription.
- Message rate, byte rate và consumer lag theo partition.
- Thời gian xử lý và tỷ lệ lỗi theo partition.
- Partition nóng hoặc mất cân bằng tải.
- Số lần rebalance, thời gian rebalance và consumer không được gán partition.
- Số message redelivery, retry và DLQ theo partition hoặc key khi có thể quan sát.

Khi thêm consumer, xác định liệu số partition có đủ để tận dụng instance mới. Khi thay đổi partition count hoặc selector, lên kế hoạch cho ảnh hưởng tới thứ tự, trạng thái cục bộ và replay. Ghi lại partition key và thuật toán chọn partition trong tài liệu hợp đồng của event để producer/consumer khác ngôn ngữ có thể tuân thủ.

## 14. Checklist thiết kế partition

- [ ] Đã chọn khóa nghiệp vụ ổn định cho các message cần gom chung.
- [ ] Producer trích đúng khóa bằng partitionKeyExpression hoặc PartitionKeyExtractorStrategy.
- [ ] Chỉ dùng một cơ chế trích khóa trên mỗi binding.
- [ ] partitionCount lớn hơn 1 và phù hợp với destination thực tế.
- [ ] Partition selector mặc định hoặc tùy chỉnh được tài liệu hóa.
- [ ] Consumer group và cơ chế gán partition phù hợp với binder.
- [ ] Với RabbitMQ, đã cấu hình partitioned và instanceCount/instanceIndex cho các instance cần thiết.
- [ ] Với Kafka, hiểu rõ auto rebalance mặc định và trường hợp binder-managed assignment.
- [ ] Với Pulsar, đã kiểm tra partitioned topic, key routing và subscription type.
- [ ] Đã kiểm tra khóa null, phân bố lệch và partition nóng.
- [ ] Đã đánh giá ảnh hưởng của việc tăng partition count đến thứ tự key.
- [ ] Đã kiểm thử với broker thật trước khi triển khai.

Phân vùng theo khóa nghiệp vụ giúp các sự kiện liên quan được gom vào cùng một đơn vị xử lý, trong khi những khóa khác vẫn có thể chạy song song. Khi chọn khóa ổn định, đồng bộ cấu hình producer/consumer, hiểu cách binder ánh xạ partition và giám sát tải theo partition, ứng dụng Spring Cloud Stream có thể mở rộng thông lượng mà vẫn giữ được tính nhất quán cần thiết cho từng aggregate.

## Tài liệu tham khảo

- [Spring Cloud Stream — Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html)
- [Spring Cloud Stream — Binding properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
