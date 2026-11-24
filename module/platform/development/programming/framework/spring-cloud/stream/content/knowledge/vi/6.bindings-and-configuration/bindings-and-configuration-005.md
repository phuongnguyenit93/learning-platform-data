# Thuộc tính chung, thuộc tính producer và thuộc tính consumer

Trong Spring Cloud Stream, binding là điểm nối giữa hàm xử lý của ứng dụng và destination trên broker. Một binding có thể là input để nhận message hoặc output để gửi message. Mỗi binding có các thuộc tính chung như destination, consumer group, content type và binder; ngoài ra còn có các thuộc tính riêng cho phía producer hoặc consumer. Hiểu đúng phạm vi của từng thuộc tính giúp cấu hình luồng sự kiện rõ ràng, tránh đặt nhầm một tùy chọn của producer vào input binding hoặc dùng thuộc tính riêng của Kafka cho RabbitMQ.

Spring Cloud Stream cung cấp mô hình hàm `Supplier`, `Function`, `Consumer`, binding và binder. Binder chuyển các thuộc tính chung thành cấu hình tương ứng cho Kafka, RabbitMQ hoặc Pulsar. Các thuộc tính lõi được dùng chung ở mức abstraction; những tùy chọn chuyên biệt của broker được đặt trong namespace mở rộng của binder tương ứng. Tên thuộc tính và khả năng hỗ trợ có thể thay đổi theo phiên bản Spring Cloud Stream và binder, vì vậy cần đối chiếu tài liệu của đúng phiên bản đang dùng.

## 1. Mô hình cấu hình của một binding

Với function có tên `processOrder`, Spring Cloud Stream tạo hai binding mặc định:

- `processOrder-in-0`: input binding, nhận message từ destination đầu vào.
- `processOrder-out-0`: output binding, gửi message đến destination đầu ra.

Các thuộc tính lõi được khai báo dưới `spring.cloud.stream.bindings.<bindingName>`:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          content-type: application/json
          consumer:
            concurrency: 3
            max-attempts: 4
        processOrder-out-0:
          destination: orders.accepted
          content-type: application/json
          producer:
            partition-key-expression: payload.orderId
            partition-count: 6
```

Trong ví dụ này, input binding nhận sự kiện từ destination `orders.created` thuộc group `order-processor`. Output binding gửi kết quả đến destination `orders.accepted` và dùng `orderId` làm khóa phân vùng theo cơ chế partitioning của Spring Cloud Stream. Phần `consumer` chỉ áp dụng cho input; phần `producer` chỉ áp dụng cho output.

## 2. Các thuộc tính chung của binding

Các thuộc tính chung mô tả binding kết nối đến đâu, dùng nhóm nào và diễn giải payload ra sao.

| Thuộc tính | Ý nghĩa | Lưu ý |
|---|---|---|
| `destination` | Tên destination trên broker, thường là topic hoặc exchange/queue tùy binder | Tên vật lý và cách provision phụ thuộc binder |
| `group` | Tên consumer group hoặc nhóm nhận logic | Chủ yếu có ý nghĩa với input binding; ảnh hưởng cách nhiều instance chia sẻ message |
| `content-type` | Định dạng nội dung message, ví dụ `application/json` | Liên quan đến message conversion; không phải tên serializer của broker |
| `binder` | Chỉ định binder sẽ phục vụ binding | Hữu ích khi ứng dụng có nhiều binder cùng classpath |
| `consumer` | Nhóm thuộc tính dành cho phía nhận | Chỉ cấu hình trên input binding |
| `producer` | Nhóm thuộc tính dành cho phía gửi | Chỉ cấu hình trên output binding |

### destination

`destination` ánh xạ binding đến tài nguyên trên broker. Với Kafka, destination thường là topic. Với RabbitMQ, binder ánh xạ destination qua exchange và các queue liên quan theo cấu hình. Với Pulsar, destination thường là topic. Cùng một tên thuộc tính nhưng tài nguyên vật lý và quy tắc tạo tài nguyên có thể khác nhau giữa các binder.

Nếu bỏ `destination`, một số cấu hình có thể suy ra tên mặc định từ binding; tuy nhiên, trong ứng dụng thực tế nên khai báo tường minh để dễ đọc, vận hành và phân quyền broker. Tên destination cũng cần thống nhất với quy ước đặt tên của hệ thống.

### group

`group` xác định nhóm consumer logic cho input binding. Nhiều instance dùng cùng group thường cùng chia sẻ việc tiêu thụ dữ liệu theo cơ chế của broker. Với Kafka, các instance trong cùng consumer group phân chia partition. Với RabbitMQ, queue gắn với group thường được nhiều consumer cạnh tranh nhận message. Với Pulsar, group được ánh xạ vào subscription theo cách của binder.

Nếu không khai báo group, binder có thể tạo nhóm consumer ẩn danh hoặc subscription riêng cho instance. Hành vi lưu giữ và chia sẻ message khi đó khác với nhóm có tên ổn định. Đối với dịch vụ cần tiếp tục đọc sau khi khởi động lại và chia tải giữa nhiều instance, hãy khai báo group rõ ràng và kiểm tra cách binder provision tài nguyên.

### content-type

`content-type` cho biết định dạng payload để Spring Cloud Stream chọn message converter, chẳng hạn `application/json` hoặc `text/plain`. Nó mô tả định dạng nội dung ở tầng message abstraction. Khi bật native encoding/decoding, serializer hoặc deserializer của binder/client có thể đảm nhiệm việc chuyển đổi ở tầng broker; khi đó cần cấu hình đồng bộ với kiểu dữ liệu mà hàm mong đợi.

### binder

Khi classpath có nhiều binder, thuộc tính `binder` giúp chọn binder cho một binding cụ thể. Ví dụ một ứng dụng có thể dùng Kafka để phát sự kiện nghiệp vụ và RabbitMQ để gửi lệnh nội bộ. Việc thêm nhiều binder chỉ hợp lý khi ứng dụng thật sự cần kết nối nhiều broker; cần cấu hình từng binder và tránh để một binding vô tình chọn nhầm broker.

## 3. Cấu hình mặc định và cấu hình theo từng binding

Spring Cloud Stream hỗ trợ cấu hình mặc định cho nhiều binding dưới `spring.cloud.stream.default`. Khi một binding cần hành vi khác, khai báo thuộc tính riêng tại `spring.cloud.stream.bindings.<bindingName>`. Ví dụ:

```yaml
spring:
  cloud:
    stream:
      default:
        content-type: application/json
        consumer:
          max-attempts: 3
          back-off-initial-interval: 1000
          back-off-max-interval: 10000
        producer:
          error-channel-enabled: true
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            max-attempts: 5
        processOrder-out-0:
          destination: orders.accepted
```

Trong ví dụ, các binding dùng JSON theo mặc định. Consumer `processOrder-in-0` ghi đè số lần thử thành 5; những thuộc tính consumer khác vẫn lấy theo cấu hình mặc định nếu không bị ghi đè. Cấu hình mặc định giúp giảm lặp lại, còn cấu hình theo binding thể hiện ngoại lệ ở đúng nơi sử dụng.

Hãy phân biệt cấu hình mặc định của Spring Cloud Stream với cấu hình mặc định của Spring Boot. Spring Boot còn có quy tắc hợp nhất các nguồn cấu hình như file YAML, file theo profile, biến môi trường, system property và tham số dòng lệnh. Khi có giá trị khác nhau, nguồn cấu hình có độ ưu tiên cao hơn có thể ghi đè giá trị trong file. Khi điều tra cấu hình thực tế, cần kiểm tra cả tên binding, profile đang chạy và nguồn cấu hình được triển khai.

## 4. Thuộc tính producer

Producer là phía gửi message vào output binding. Nhóm thuộc tính `producer` điều khiển cách tạo và định tuyến message ở phía gửi. Những thuộc tính thường gặp gồm partition key, số partition, nhóm consumer cần provision, native encoding và kênh lỗi.

### partition-key-expression và partition-count

`partition-key-expression` là biểu thức SpEL dùng để lấy khóa phân vùng từ payload hoặc message. `partition-count` cho biết số partition dự kiến mà cơ chế partitioning của Spring Cloud Stream sử dụng. Ví dụ:

```yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.created
          producer:
            partition-key-expression: payload.orderId
            partition-count: 8
```

Nếu các message có cùng `orderId`, chúng có thể được định tuyến về cùng partition theo thuật toán partition selector. Điều này hữu ích khi cần giữ thứ tự các sự kiện của cùng một đơn hàng. Khóa nên ổn định, có phân bố hợp lý và không rỗng. Nếu mọi message dùng cùng một khóa, một partition có thể trở thành điểm nóng.

Partitioning ở tầng Spring Cloud Stream cần được phân biệt với cấu hình partition trực tiếp của broker. Kafka binder cũng có thể dùng partitioner hoặc serializer/key của Kafka; RabbitMQ và Pulsar có cơ chế định tuyến riêng. Không giả định rằng cùng một biểu thức partition có hiệu lực giống hệt nhau ở mọi binder. Kiểm tra tài liệu binder và cấu hình destination thực tế.

### partition-selector-expression

Khi cần kiểm soát cách chọn partition từ khóa đã trích xuất, có thể dùng `partition-selector-expression`. Thông thường không cần tùy biến selector nếu thuật toán mặc định đáp ứng yêu cầu. Chỉ thay đổi khi có lý do về phân bố tải hoặc tương thích với quy ước định tuyến hiện tại; thay đổi selector có thể khiến cùng một khóa được gửi sang partition khác sau khi triển khai.

### required-groups

`required-groups` liệt kê các consumer group cần được binder chuẩn bị tài nguyên trước hoặc ngay khi producer binding được tạo, tùy binder. Ví dụ:

```yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.created
          producer:
            required-groups:
              - order-projection
              - audit-service
```

Thuộc tính này hữu ích khi producer bắt đầu phát message trước khi consumer group khởi động. Với broker/binder hỗ trợ cơ chế provision tương ứng, tài nguyên nhận có thể được tạo sẵn để message không bị mất chỉ vì consumer chưa chạy. Hành vi cụ thể phụ thuộc binder, loại destination và chính sách retention; không nên coi `required-groups` là bảo đảm giao nhận độc lập với cấu hình broker.

### use-native-encoding

`use-native-encoding` yêu cầu binder/client dùng cơ chế serialize native của broker thay vì message converter của Spring Cloud Stream cho output. Thuộc tính này thường chỉ nên bật khi đã cấu hình serializer tương ứng và consumer có cách deserialize tương thích. Nếu bật nhưng serializer không khớp kiểu payload, message có thể được gửi ở định dạng mà consumer không đọc được.

Ví dụ dưới đây chỉ minh họa vị trí thuộc tính:

```yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.created
          producer:
            use-native-encoding: true
```

Với native encoding, cấu hình serializer thường nằm trong phần mở rộng của binder, chẳng hạn cấu hình Kafka producer. Không bật tùy chọn này chỉ để né một lỗi message conversion; hãy xác định định dạng byte thực tế và cấu hình cả hai phía.

### error-channel-enabled

`error-channel-enabled` điều khiển việc phát sinh kênh lỗi cho lỗi liên quan đến binding theo khả năng của framework và binder. Kênh lỗi giúp ứng dụng hoặc thành phần tích hợp quan sát lỗi gửi bất đồng bộ và xử lý theo chính sách. Nó không tự động bảo đảm message được gửi lại hoặc được lưu vào DLQ. Retry, error handling và DLQ cần được thiết kế riêng.

## 5. Thuộc tính consumer

Consumer là phía nhận message từ input binding. Các thuộc tính consumer thường điều khiển mức song song, retry, phân vùng, native decoding và cách xử lý lỗi.

### concurrency

`concurrency` xác định số consumer hoặc luồng xử lý đồng thời mà binder/container tạo cho một binding, trong giới hạn hỗ trợ của binder. Ví dụ:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            concurrency: 3
```

Tăng concurrency có thể tăng thông lượng khi còn partition hoặc message để xử lý và tài nguyên ứng dụng đủ đáp ứng. Với Kafka, số consumer trong cùng group vượt số partition sẽ có consumer nhàn rỗi. Với RabbitMQ và Pulsar, giới hạn thực tế phụ thuộc queue/subscription, số consumer, prefetch, partition và cách binder triển khai. Tăng concurrency quá cao có thể làm tăng tải cơ sở dữ liệu, tranh chấp tài nguyên hoặc đảo thứ tự xử lý ở tầng nghiệp vụ.

### max-attempts và backoff

Các thuộc tính retry lõi gồm:

| Thuộc tính | Ý nghĩa |
|---|---|
| `max-attempts` | Tổng số lần gọi xử lý bao gồm lần đầu và các lần retry |
| `back-off-initial-interval` | Khoảng chờ ban đầu trước lần retry |
| `back-off-max-interval` | Giới hạn tối đa của khoảng chờ |
| `back-off-multiplier` | Hệ số nhân khoảng chờ giữa các lần retry |
| `default-retryable` | Quy định mặc định một exception có được retry hay không khi không có quy tắc riêng |
| `retryable-exceptions` | Bản đồ exception class và giá trị boolean cho phép hoặc từ chối retry |

Ví dụ:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            max-attempts: 4
            back-off-initial-interval: 1000
            back-off-max-interval: 8000
            back-off-multiplier: 2.0
            default-retryable: true
            retryable-exceptions:
              com.example.TemporaryGatewayException: true
              com.example.InvalidOrderException: false
```

Với cấu hình này, lỗi tạm thời có thể được thử lại theo backoff tăng dần; lỗi dữ liệu không hợp lệ được đánh dấu không retry. `max-attempts: 1` có nghĩa là chỉ gọi lần đầu, không có lần retry tiếp theo. Retry chỉ phù hợp với lỗi có khả năng tự hết; retry lỗi dữ liệu cố định thường chỉ kéo dài thời gian xử lý và làm tăng tải.

Retry của abstraction có thể diễn ra trong tiến trình consumer. Nếu tiến trình dừng đột ngột, broker có thể giao lại message theo cơ chế riêng. Vì vậy, retry trong ứng dụng và redelivery của broker là hai cơ chế khác nhau. Hãy dùng idempotency để bảo vệ nghiệp vụ khỏi xử lý trùng.

### partitioned, instance-count và instance-index

Với các mô hình triển khai partition-aware, `partitioned` cho biết consumer binding tham gia cơ chế phân vùng của Spring Cloud Stream. `instance-count` và `instance-index` xác định tổng số instance và chỉ số của instance hiện tại trong các cấu hình cần phân công partition. Một số phiên bản/cấu hình đặt hai thuộc tính instance ở cấp `spring.cloud.stream`; cần kiểm tra tài liệu đúng phiên bản và binder.

Ví dụ minh họa cho hai instance:

```yaml
spring:
  cloud:
    stream:
      instance-count: 2
      instance-index: 0
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            partitioned: true
```

Instance còn lại dùng cùng `instance-count` nhưng `instance-index: 1`. Không cấu hình hai replica cùng một instance index khi cơ chế partitioning yêu cầu chỉ số duy nhất. Với Kafka, consumer group và partition assignment của Kafka cũng tham gia quyết định phân phối thực tế; không nhầm `instance-index` của Spring Cloud Stream với partition assignment nội bộ của Kafka.

### use-native-decoding

`use-native-decoding` yêu cầu binder/client dùng deserializer native của broker thay vì message converter của Spring Cloud Stream cho input. Tùy chọn này thường cần đi cùng cấu hình deserializer tương ứng. Producer và consumer phải thống nhất serializer/deserializer và schema. Nếu chỉ bật native decoding ở consumer nhưng producer vẫn gửi JSON theo một cơ chế khác, dữ liệu có thể không giải mã được.

## 6. Phân biệt thuộc tính lõi và thuộc tính mở rộng của binder

Thuộc tính lõi nằm dưới `spring.cloud.stream.bindings`. Thuộc tính mở rộng của binder nằm dưới namespace binder cụ thể, ví dụ `spring.cloud.stream.kafka.bindings` hoặc `spring.cloud.stream.rabbit.bindings`. Phần mở rộng cung cấp quyền truy cập vào tính năng riêng của broker.

Ví dụ Kafka binder có thể có cấu hình consumer để bật DLQ:

```yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.created.dlq
```

Tên và khả năng của thuộc tính mở rộng như DLQ, offset, acknowledgement hoặc transaction phụ thuộc phiên bản Kafka binder. Không đặt `enable-dlq` vào phần `consumer` lõi rồi kỳ vọng mọi binder hiểu cùng cách.

Rabbit binder có các tùy chọn riêng để tạo dead-letter exchange/queue, điều khiển requeue hoặc prefetch. Ví dụ minh họa vị trí namespace:

```yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              republish-to-dlq: true
```

Hãy kiểm tra đúng tên thuộc tính và điều kiện hỗ trợ trong tài liệu phiên bản Rabbit binder đang dùng. Pulsar binder cũng có phần mở rộng riêng cho subscription, dead-letter policy và acknowledgement. Không thể sao chép cấu hình Kafka sang RabbitMQ hoặc Pulsar chỉ bằng cách thay tên destination.

## 7. Ví dụ cấu hình tổng hợp

Giả sử function `processOrder` nhận `OrderCreated`, kiểm tra đơn hàng rồi trả về `OrderAccepted`. Cấu hình lõi có thể được tổ chức như sau:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      default:
        content-type: application/json
        consumer:
          max-attempts: 3
          back-off-initial-interval: 1000
          back-off-max-interval: 10000
          back-off-multiplier: 2.0
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            concurrency: 2
            max-attempts: 4
            retryable-exceptions:
              com.example.InvalidOrderException: false
        processOrder-out-0:
          destination: orders.accepted
          producer:
            partition-key-expression: payload.orderId
            partition-count: 6
            required-groups:
              - order-projection
              - audit-service
```

Đọc cấu hình từ trên xuống:

1. `processOrder` là function được kích hoạt.
2. Các binding dùng JSON theo mặc định.
3. Input đọc từ `orders.created` với consumer group `order-processor`.
4. Consumer có concurrency 2 và tối đa 4 lần thử; `InvalidOrderException` không được retry.
5. Output gửi đến `orders.accepted`, dùng `orderId` làm khóa phân vùng và khai báo hai nhóm nhận cần provision nếu binder hỗ trợ.

Ví dụ minh họa các thuộc tính lõi, chưa bao gồm thông tin kết nối broker, credential, serializer native hoặc DLQ riêng của binder. Những phần đó cần được cấu hình theo môi trường và loại broker.

## 8. Cách chọn thuộc tính và tránh lỗi cấu hình

| Nhu cầu | Thuộc tính nên xem xét | Binding áp dụng |
|---|---|---|
| Đổi topic/queue đích | `destination` | Input hoặc output |
| Chia tải nhiều consumer instance | `group` | Input |
| Chọn định dạng payload | `content-type` | Input hoặc output |
| Chọn broker khi có nhiều binder | `binder` | Input hoặc output |
| Tăng số consumer đồng thời | `consumer.concurrency` | Input |
| Retry lỗi tạm thời | `consumer.max-attempts`, `back-off-*`, `retryable-exceptions` | Input |
| Phân vùng theo khóa nghiệp vụ | `producer.partition-key-expression`, `partition-count` | Output |
| Chuẩn bị tài nguyên cho nhóm nhận | `producer.required-groups` | Output |
| Dùng serializer/deserializer native | `producer.use-native-encoding`, `consumer.use-native-decoding` | Output/input tương ứng |
| Bật tính năng riêng của broker | Namespace mở rộng của binder | Theo binder và chiều gửi/nhận |

Một số lỗi cấu hình phổ biến:

- Đặt thuộc tính producer trên input binding hoặc consumer trên output binding. Thuộc tính có thể bị bỏ qua hoặc không có tác dụng như mong đợi.
- Nhầm binding name với destination. Binding name là khóa cấu hình trong ứng dụng; destination là tên tài nguyên broker.
- Dùng `content-type` như thể đó là Kafka serializer class. Hai lớp cấu hình có vai trò khác nhau.
- Bật native encoding/decoding mà không cấu hình serializer/deserializer tương thích ở hai phía.
- Tăng concurrency mà không xét số partition, giới hạn broker hoặc năng lực xử lý của downstream.
- Dùng cùng một group cho hai ứng dụng có mục tiêu nhận độc lập, khiến chúng cạnh tranh message thay vì mỗi ứng dụng nhận bản sao riêng.
- Sao chép thuộc tính mở rộng giữa các binder mà không kiểm tra tài liệu của binder tương ứng.

Khi một thuộc tính không có hiệu lực, hãy kiểm tra chính tả tên binding, vị trí namespace, profile đang hoạt động, nguồn cấu hình có độ ưu tiên cao hơn và log khởi tạo binding. Với ứng dụng có nhiều binder, kiểm tra binding đã chọn đúng binder chưa.

## 9. Kiểm thử và vận hành cấu hình

Kiểm thử cấu hình nên xác minh hành vi quan sát được thay vì chỉ kiểm tra YAML có thể parse:

- Khởi tạo context và xác nhận đúng function cùng input/output binding được tạo.
- Gửi message JSON hợp lệ, xác nhận payload được chuyển đổi đúng kiểu và output đến đúng destination.
- Gửi message gây lỗi tạm thời và xác nhận số lần retry/backoff theo cấu hình.
- Gửi message lỗi không retry và xác nhận đường xử lý lỗi/DLQ tương ứng với binder.
- Chạy nhiều instance cùng group để quan sát phân phối message và kiểm tra concurrency/partition.
- Kiểm tra partition key với nhiều giá trị khóa, xác nhận các sự kiện cùng aggregate được định tuyến theo yêu cầu.
- Kiểm tra native encoding/decoding bằng đúng serializer và deserializer thực tế.

Test binder hữu ích để kiểm tra logic function và binding trong phạm vi ứng dụng. Nó không thay thế integration test với Kafka, RabbitMQ hoặc Pulsar khi cần xác minh partition assignment, publisher confirmation, offset/acknowledgement, dead-letter routing, durability hoặc hành vi redelivery.

Trong production, theo dõi số lượng message nhận/gửi, consumer lag, thời gian xử lý, retry count, DLQ depth, lỗi conversion, số consumer hoạt động và tình trạng kết nối broker. Ghi log binding name, destination, group và event ID để có thể liên hệ lỗi cấu hình với message cụ thể. Tránh ghi payload nhạy cảm vào log.

## 10. Checklist trước khi triển khai

- [ ] Mỗi binding có tên rõ ràng và trỏ đến đúng destination.
- [ ] Input binding có group ổn định khi cần chia tải và tiếp tục tiêu thụ sau restart.
- [ ] Content type phù hợp với kiểu payload và message converter.
- [ ] Thuộc tính consumer chỉ đặt trên input binding; thuộc tính producer chỉ đặt trên output binding.
- [ ] Concurrency phù hợp với partition, broker và năng lực downstream.
- [ ] Retry có giới hạn và phân loại lỗi; DLQ được cấu hình theo đúng binder nếu cần.
- [ ] Partition key ổn định và phân bố tải hợp lý.
- [ ] Native encoding/decoding chỉ bật khi serializer/deserializer đã được cấu hình đồng bộ.
- [ ] Các thuộc tính mở rộng đã được kiểm tra theo đúng binder và phiên bản.
- [ ] Kiểm thử với broker thật đã xác nhận hành vi quan trọng trước khi phát hành.

Khi phân tách rõ thuộc tính chung, producer và consumer, cấu hình Spring Cloud Stream sẽ thể hiện đúng trách nhiệm của từng binding. Kết hợp cấu hình lõi với phần mở rộng đúng binder giúp ứng dụng giữ được tính di động ở mức abstraction và vẫn khai thác được khả năng cần thiết của Kafka, RabbitMQ hoặc Pulsar.
