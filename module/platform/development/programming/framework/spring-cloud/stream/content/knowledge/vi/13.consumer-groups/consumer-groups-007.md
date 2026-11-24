# requiredGroups và điều kiện áp dụng theo binder

Trong một hệ thống xử lý sự kiện, producer có thể bắt đầu gửi thông điệp trước khi một consumer được triển khai. Nếu broker chưa có tài nguyên nhận dành cho nhóm đó, thông điệp phát ra trong khoảng thời gian chờ có thể không được lưu cho nhóm mới. Spring Cloud Stream cung cấp thuộc tính producer **requiredGroups** để khai báo trước những nhóm cần nhận dữ liệu. Tuy nhiên, tác dụng thực tế phụ thuộc vào mô hình lưu trữ và cách binder provision tài nguyên trên broker.

Thuộc tính này đặc biệt hữu ích với RabbitMQ, nơi mỗi consumer group thường có một queue riêng được bind vào exchange. Kafka và Pulsar dùng topic cùng offset hoặc subscription cursor, nên cách bảo đảm thông điệp cho nhóm khởi động muộn khác với việc tạo queue riêng. Không nên xem **requiredGroups** là một lệnh tạo consumer group giống nhau cho mọi binder.

## 1. Phân biệt group của consumer và requiredGroups của producer

Spring Cloud Stream có hai cấu hình liên quan đến nhóm tiêu thụ nhưng nằm ở hai phía khác nhau:

| Thuộc tính | Nằm ở đâu | Ý nghĩa |
|---|---|---|
| **group** | Input binding của consumer | Đặt danh tính nhóm tiêu thụ. Các instance cùng group phối hợp chia tải; nhóm khác nhận bản sao luồng sự kiện độc lập theo ngữ nghĩa broker. |
| **requiredGroups** | Producer properties của output binding | Khai báo các nhóm mà producer cần được chuẩn bị tài nguyên nhận trước khi bắt đầu phát thông điệp. |

Ví dụ một ứng dụng tiêu thụ sự kiện:

~~~yaml
spring:
  cloud:
    function:
      definition: billingConsumer
    stream:
      bindings:
        billingConsumer-in-0:
          destination: orders
          group: billing
~~~

Ở đây **billing** là group của input binding. Khi chạy nhiều bản sao ứng dụng với cùng tên group, chúng tham gia cùng một nhóm tiêu thụ. Một ứng dụng analytics có thể dùng group khác để nhận luồng độc lập.

Producer có thể khai báo các nhóm cần chuẩn bị:

~~~yaml
spring:
  cloud:
    function:
      definition: orderPublisher
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
          producer:
            required-groups: billing,analytics
~~~

**required-groups** là dạng kebab-case của thuộc tính **requiredGroups**. Giá trị là danh sách tên group phân tách bằng dấu phẩy. Các tên này phải khớp chính xác với group mà các consumer tương ứng sử dụng.

Thuộc tính nằm dưới **producer** của output binding. Đặt nó ở input binding hoặc dưới **consumer** không tạo ra hành vi mong muốn. Nếu dùng nhiều output binding, mỗi binding có thể khai báo danh sách required groups riêng vì mỗi destination có tập consumer khác nhau.

## 2. Vấn đề khi consumer khởi động sau producer

Hãy xem một luồng đơn hàng có hai nhóm nhận:

~~~mermaid
flowchart TD
    P[Order producer] --> D[Destination orders]
    D --> B[Group billing]
    D --> A[Group analytics]
    B --> B1[Billing consumers]
    A --> A1[Analytics consumers]
~~~

Giả sử producer bắt đầu lúc 09:00, nhóm billing chỉ được triển khai lúc 09:10. Hệ thống cần bảo đảm sự kiện phát trong 10 phút đầu vẫn có thể được billing xử lý.

Kết quả phụ thuộc vào broker:

- Với RabbitMQ, nếu queue của group chưa tồn tại lúc producer gửi, exchange không có queue tương ứng để định tuyến thông điệp. **requiredGroups** cho phép binder tạo queue và binding trước khi producer bắt đầu gửi.
- Với Kafka, thông điệp được lưu trong log của topic. Một consumer group mới có thể đọc dữ liệu còn trong retention dựa trên offset khởi tạo, không cần queue riêng cho group.
- Với Pulsar, subscription là nơi lưu cursor và backlog. Nếu subscription chưa tồn tại khi producer phát, topic mặc định không giữ thông điệp ngoài backlog; subscription mới cũng thường bắt đầu ở vị trí mới nhất. Cần xử lý subscription và retention theo chính sách Pulsar.

Do đó, mục tiêu của required groups là bảo đảm tài nguyên nhận phù hợp với mô hình broker. Nó không thay thế retention, offset, subscription cursor, acknowledgement hoặc chính sách hết hạn.

## 3. Cấu hình requiredGroups cho RabbitMQ

RabbitMQ binder ánh xạ destination thành exchange. Với mỗi consumer group, binder tạo một queue riêng và bind queue đó vào exchange. Tên queue mặc định có dạng:

~~~text
<prefix><destination>.<group>
~~~

Nếu output binding khai báo **requiredGroups**, Rabbit binder provision một queue và binding cho từng group khi producer binding được tạo. Nhờ vậy, queue đã tồn tại trước khi producer gửi thông điệp đầu tiên, kể cả khi ứng dụng consumer chưa chạy.

Ví dụ producer:

~~~yaml
spring:
  cloud:
    function:
      definition: orderPublisher
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
          producer:
            required-groups: billing,analytics
~~~

Rabbit binder có thể tạo các queue tương ứng với destination **orders** và các group **billing**, **analytics**. Consumer billing dùng:

~~~yaml
spring:
  cloud:
    function:
      definition: billingConsumer
    stream:
      bindings:
        billingConsumer-in-0:
          destination: orders
          group: billing
~~~

Consumer analytics dùng cùng destination nhưng group riêng:

~~~yaml
spring:
  cloud:
    function:
      definition: analyticsConsumer
    stream:
      bindings:
        analyticsConsumer-in-0:
          destination: orders
          group: analytics
~~~

Mỗi queue giữ bản sao thông điệp của group tương ứng. Nhiều instance cùng group cạnh tranh nhận từ cùng queue; hai group khác nhau nhận bản sao độc lập.

### Các điều kiện để queue giữ được thông điệp

Việc queue được tạo trước chỉ giải quyết điều kiện định tuyến. Để dữ liệu có thể sống qua thời gian consumer ngừng hoạt động, cần kiểm tra thêm:

1. Queue được khai báo bền vững và broker có cấu hình lưu trữ phù hợp.
2. Producer gửi thông điệp persistent. Rabbit binder mặc định dùng delivery mode **PERSISTENT**, nhưng cần kiểm tra nếu ứng dụng đã tùy chỉnh thuộc tính này.
3. Queue chưa bị xóa bởi chính sách auto-delete hoặc expires.
4. Thông điệp chưa hết TTL và queue chưa vượt giới hạn dung lượng hoặc số lượng.
5. Exchange, queue và binding có quyền truy cập phù hợp; producer được phép publish, binder được phép khai báo tài nguyên nếu tự provision.
6. Consumer chỉ ACK sau khi xử lý thành công theo thiết kế giao nhận của ứng dụng.

Durable queue và persistent message là hai thuộc tính riêng. Durable queue giữ định nghĩa queue qua lần restart broker; persistent message yêu cầu broker lưu thông điệp bền vững. Cả hai cần được xem xét cùng với loại queue, replication, publisher confirms và chính sách vận hành của RabbitMQ.

### Cấu hình queue và DLQ cho required groups

Rabbit binder cung cấp các thuộc tính mở rộng cho queue được tạo theo required groups. Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
          producer:
            required-groups: billing,analytics
      rabbit:
        bindings:
          orderPublisher-out-0:
            producer:
              auto-bind-dlq: true
              ttl: 3600000
              max-length: 100000
~~~

Đây là ví dụ minh họa các tùy chọn binder; cần kiểm tra đúng namespace và khả năng hỗ trợ của phiên bản Rabbit binder đang dùng. Các thuộc tính như TTL, max length, DLX và DLQ chỉ có ý nghĩa cho queue được provision theo required groups. Chúng không phải cấu hình retention chung của exchange.

Khi dùng hạ tầng RabbitMQ đã được tạo sẵn, có thể cần tắt khai báo queue hoặc exchange tự động bằng các thuộc tính tương ứng, chẳng hạn **bindQueue: false**. Trong trường hợp đó, đội vận hành phải bảo đảm exchange, queue và binding đã tồn tại với tên và routing key chính xác. **requiredGroups** không thể tạo tài nguyên nếu binder bị cấu hình không khai báo chúng.

## 4. Điều kiện theo Kafka binder

Kafka tổ chức dữ liệu theo topic log và partition. Các consumer group độc lập đọc cùng topic bằng offset riêng; broker không tạo một queue vật lý cho mỗi group. Vì vậy, Kafka không cần cơ chế provision queue theo từng group như RabbitMQ.

Khi producer gửi sự kiện vào topic **orders**, bản ghi được lưu theo retention của topic. Một consumer group mới có thể đọc các bản ghi còn tồn tại nếu offset khởi tạo của nó trỏ về vị trí phù hợp. Với Kafka binder, thuộc tính **startOffset** điều khiển vị trí bắt đầu cho group chưa có offset đã commit:

- **earliest**: bắt đầu từ bản ghi sớm nhất còn có trong partition.
- **latest**: bắt đầu từ cuối log và chỉ nhận bản ghi mới được ghi sau vị trí đó.

Trong Kafka binder, input binding có group tường minh mặc định dùng **earliest** cho group mới; binding anonymous mặc định dùng **latest**. Có thể đặt tường minh:

~~~yaml
spring:
  cloud:
    function:
      definition: billingConsumer
    stream:
      bindings:
        billingConsumer-in-0:
          destination: orders
          group: billing
      kafka:
        bindings:
          billingConsumer-in-0:
            consumer:
              start-offset: earliest
~~~

Với cấu hình này, group **billing** mới bắt đầu từ các bản ghi sớm nhất còn trong topic. Nó không đọc được dữ liệu đã bị xóa bởi retention. Nếu group đã có offset commit, vị trí tiếp tục thông thường dựa trên offset đó; **startOffset** không tự động tua lại group đang hoạt động.

### requiredGroups có tạo Kafka group trước không?

Không nên diễn giải **requiredGroups** như một yêu cầu tạo consumer group metadata hoặc queue riêng trên Kafka. Kafka group được broker nhận diện thông qua hoạt động của consumer và offset commit. Producer ghi vào topic; các group tự theo dõi tiến độ đọc của mình.

Với Kafka, hãy bảo đảm:

- Topic được tạo và có đủ partition.
- Retention đủ dài để bao phủ khoảng thời gian consumer có thể khởi động muộn hoặc ngừng hoạt động.
- Group mới dùng **startOffset** hoặc cấu hình offset phù hợp.
- Quyền ACL cho phép consumer đọc topic và sử dụng group.
- Chính sách offset retention của broker không làm mất tiến độ trong khoảng thời gian cần thiết.

Do topic retention áp dụng cho log, mọi group chỉ có thể đọc những bản ghi còn tồn tại. **requiredGroups** không kéo dài retention và không tạo một bản sao log riêng cho từng group. Hãy xác minh hành vi của phiên bản Kafka binder cụ thể nếu ứng dụng dùng thuộc tính common này; không dựa vào nó để thay thế topic retention hoặc cấu hình offset.

## 5. Điều kiện theo Pulsar binder

Apache Pulsar sử dụng topic và subscription. Subscription có tên và cursor lưu vị trí tiêu thụ; nhiều consumer cùng subscription chia sẻ công việc theo loại subscription. Một subscription bền vững có thể tiếp tục sau khi consumer ngắt kết nối và broker restart.

Điểm khác biệt quan trọng là một subscription mới thường bắt đầu ở vị trí **latest**. Nếu producer đã gửi thông điệp trước khi subscription được tạo, consumer mới có thể bắt đầu sau các thông điệp đó. Ngoài ra, theo mặc định Pulsar chỉ giữ thông điệp đang thuộc backlog của ít nhất một subscription. Topic chưa có subscription thường không giữ thông điệp để một subscription tương lai đọc lại, trừ khi namespace có retention policy phù hợp.

Vì vậy, với Pulsar:

1. Tạo subscription bền vững trước khi producer bắt đầu phát, nếu nhóm cần nhận mọi sự kiện từ thời điểm khởi chạy producer.
2. Nếu subscription chỉ được tạo sau, cân nhắc cấu hình initial position là **Earliest** và bật retention cho namespace/topic để các bản ghi trước đó còn tồn tại.
3. Kiểm tra backlog quota, TTL, retention size/time và chính sách xóa topic.
4. Giữ tên subscription ổn định giữa các lần triển khai để cursor tiếp tục đúng tiến độ.
5. Chọn subscription type phù hợp với concurrency và yêu cầu thứ tự.

Trong Spring Boot for Apache Pulsar, thuộc tính subscription initial position có thể được cấu hình qua consumer properties. Ví dụ:

~~~yaml
spring:
  pulsar:
    consumer:
      subscription:
        initial-position: earliest
        mode: durable
~~~

Tên và vị trí cấu hình cụ thể có thể khác khi cấu hình qua extended binding properties của Pulsar binder. Hãy xác nhận tài liệu của phiên bản Spring Cloud Stream và Spring for Apache Pulsar đang dùng. Ví dụ trên minh họa ý nghĩa cấu hình ở cấp Spring Boot Pulsar; nó không phải cấu hình **requiredGroups**.

Tài liệu Pulsar binder hiện mô tả topic provisioner, subscription và các thuộc tính client/binder, nhưng không mô tả **requiredGroups** như cơ chế tạo sẵn subscription cho từng group tương đương Rabbit binder. Vì vậy, không nên dựa vào thuộc tính này để bảo đảm nhóm Pulsar khởi động muộn nhận được dữ liệu. Hãy provision subscription bằng công cụ quản trị hoặc triển khai consumer trước producer, đồng thời cấu hình retention và initial position theo yêu cầu phát lại.

## 6. So sánh requiredGroups và cơ chế tương đương

| Nội dung | RabbitMQ binder | Kafka binder | Pulsar binder |
|---|---|---|---|
| Mô hình lưu dữ liệu | Exchange định tuyến thông điệp tới queue. | Topic log lưu bản ghi theo partition. | Topic lưu thông điệp; subscription giữ cursor và backlog. |
| Tài nguyên nhận của group | Queue riêng cho từng group. | Offset của consumer group trên topic. | Subscription riêng theo tên. |
| Vai trò rõ ràng của requiredGroups | Provision queue/binding trước khi producer gửi. | Không tạo queue riêng hay offset group; topic retention và offset quyết định khả năng đọc muộn. | Không có cơ chế được tài liệu binder mô tả tương đương để provision subscription bằng requiredGroups. |
| Điều kiện để group bắt đầu muộn đọc được dữ liệu | Queue đã tồn tại trước lúc publish. | Bản ghi còn trong retention và group bắt đầu từ offset phù hợp. | Subscription đã tồn tại, hoặc retention giữ dữ liệu và subscription mới bắt đầu từ earliest. |
| Nơi quản lý vòng đời | Queue, exchange, binding, TTL, DLQ và policy. | Topic, partition, retention, group offset và ACL. | Topic, subscription, cursor, retention, TTL và backlog quota. |

Một khác biệt dễ gây hiểu nhầm là từ **durable**. Queue RabbitMQ bền vững, Kafka log retention và Pulsar durable subscription đều giúp phục hồi dữ liệu theo cách riêng. Chúng không phải cùng một cơ chế và không thể thay thế cho nhau bằng một thuộc tính cấu hình duy nhất.

## 7. Tình huống triển khai thực tế

Giả sử hệ thống bán hàng có producer **order-api** và hai consumer:

- **billing** tạo hóa đơn.
- **analytics** cập nhật báo cáo.

Yêu cầu là hai nhóm phải nhận mọi đơn hàng kể từ thời điểm hệ thống producer được triển khai, kể cả khi một consumer được triển khai sau.

### Nếu dùng RabbitMQ

Producer output binding khai báo:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
          producer:
            required-groups: billing,analytics
~~~

Rabbit binder tạo exchange và queue/binding cho hai group theo cấu hình. Consumer có thể được triển khai sau; thông điệp được xếp trong queue tương ứng trong giới hạn của TTL, queue policy và dung lượng.

### Nếu dùng Kafka

Producer gửi vào topic **orders**. Topic cần retention đủ dài. Consumer **billing** và **analytics** dùng group riêng. Nếu group bắt đầu lần đầu với **startOffset: earliest**, chúng đọc bản ghi còn trong topic. Không cần khai báo requiredGroups để tạo queue. Nếu retention đã xóa bản ghi cũ trước khi consumer khởi động, không thể khôi phục từ topic đó.

### Nếu dùng Pulsar

Tạo hai durable subscription **billing** và **analytics** trước khi producer gửi sự kiện, hoặc cấu hình retention phù hợp và initial position **Earliest** cho subscription được tạo sau. Nếu topic chưa có subscription và retention mặc định không giữ thông điệp ngoài backlog, dữ liệu phát trước khi subscription tồn tại có thể không còn để đọc.

Khi thay đổi broker, hãy viết lại phần thiết lập tài nguyên và kiểm thử thời điểm consumer được tạo. Không chỉ sao chép nguyên cấu hình **required-groups** từ môi trường RabbitMQ sang Kafka hoặc Pulsar.

## 8. Kiểm thử requiredGroups và consumer khởi động muộn

Kiểm thử cần mô phỏng đúng thứ tự khởi động, vì chạy producer và consumer cùng lúc có thể che giấu lỗi thiếu tài nguyên nhận.

### Kịch bản tổng quát

1. Khởi động broker và producer application.
2. Chờ output binding được tạo và xác nhận tài nguyên theo binder.
3. Gửi một loạt sự kiện có mã định danh riêng.
4. Giữ consumer group ở trạng thái chưa chạy.
5. Khởi động consumer sau một khoảng thời gian.
6. Xác nhận group nhận được những sự kiện nằm trong phạm vi bảo đảm của broker.
7. Khởi động lại consumer và xác nhận tiến độ được tiếp tục, không mất hoặc xử lý trùng ngoài chính sách dự kiến.

### Ma trận kiểm thử theo binder

| Binder | Trước khi gửi | Khi consumer chưa chạy | Khi consumer bắt đầu muộn |
|---|---|---|---|
| RabbitMQ | Xác nhận exchange, queue cho từng required group và binding đã được tạo. | Gửi thông điệp; kiểm tra queue có message ready. | Consumer đúng group nhận backlog và ACK sau xử lý. |
| Kafka | Xác nhận topic, partition và retention. | Gửi thông điệp vào topic; không cần group metadata tồn tại. | Tạo group mới với startOffset phù hợp; xác nhận đọc bản ghi còn trong retention. |
| Pulsar | Xác nhận durable subscription đã tạo, hoặc retention được bật nếu subscription tạo sau. | Gửi thông điệp và kiểm tra backlog/retention của topic. | Consumer nối vào subscription đã có cursor hoặc tạo subscription earliest khi dữ liệu còn được giữ. |

Với RabbitMQ, kiểm tra tên queue theo destination và group, queue durability, message persistence, TTL, expires, max length và DLQ. Thử restart broker trong môi trường kiểm thử để xác nhận tài nguyên và thông điệp được phục hồi theo cấu hình.

Với Kafka, kiểm tra offset của group mới, startOffset, retention của topic và offset retention của broker. Một bài kiểm thử quan trọng là để consumer group vắng mặt, gửi dữ liệu, rồi tạo group với earliest; sau đó lặp lại với latest để xác nhận sự khác biệt.

Với Pulsar, thử hai trường hợp: subscription được tạo trước khi publish và subscription được tạo sau khi publish. Với trường hợp thứ hai, so sánh initial position latest và earliest khi retention đã bật. Nếu retention không được bật và không có subscription lúc producer gửi, không kỳ vọng dữ liệu cũ vẫn còn.

### Kiểm thử số lượng và ranh giới thời gian

Không chỉ xác nhận một thông điệp. Hãy gửi nhiều thông điệp với event ID tăng dần, tạo tải đủ để kiểm tra backlog, sau đó đối chiếu:

- Số thông điệp producer gửi thành công.
- Số thông điệp broker lưu hoặc định tuyến cho từng group.
- Số thông điệp consumer nhận và ACK/commit.
- Số thông điệp còn backlog sau khi consumer dừng.
- Số thông điệp hết hạn hoặc bị loại do giới hạn dung lượng.
- Số lần xử lý trùng sau restart hoặc redelivery.

Các chỉ số cần được đối chiếu với ngữ nghĩa broker. Queue depth của RabbitMQ, consumer lag của Kafka và subscription backlog của Pulsar không phải cùng một đơn vị đo.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| RabbitMQ mất thông điệp khi consumer khởi động muộn | Queue cho group chưa tồn tại lúc producer gửi. | Khai báo requiredGroups trên output binding hoặc provision queue trước. |
| RabbitMQ có queue nhưng dữ liệu không còn sau restart | Queue/message không bền vững hoặc policy lưu trữ không phù hợp. | Kiểm tra durable queue, persistent delivery mode và cấu hình broker. |
| RabbitMQ queue hết hạn khi consumer chưa triển khai | TTL, expires, auto-delete hoặc policy đã xóa queue/message. | Điều chỉnh vòng đời queue và message theo cửa sổ triển khai. |
| Consumer Kafka mới không đọc dữ liệu cũ | startOffset là latest, retention đã xóa bản ghi hoặc group có offset đã commit. | Kiểm tra startOffset, resetOffsets, committed offset và retention. |
| requiredGroups không tạo queue Kafka | Kafka không dùng queue riêng cho từng group. | Quản lý topic retention và offset của group. |
| Pulsar subscription mới không nhận thông điệp cũ | Subscription bắt đầu latest hoặc topic không giữ dữ liệu khi chưa có subscription. | Tạo subscription sớm hoặc dùng earliest cùng retention phù hợp. |
| Group mới đọc lại quá nhiều dữ liệu | Offset/cursor bắt đầu từ earliest hoặc group identity đã thay đổi. | Xác định rõ cửa sổ replay và vị trí bắt đầu mong muốn. |
| Producer và consumer dùng group khác nhau | Tên group không khớp hoặc cấu hình môi trường ghi đè. | Chuẩn hóa group name và kiểm tra cấu hình đã phân giải. |
| Backlog bị xóa trước khi xử lý | TTL, retention, backlog quota hoặc giới hạn queue. | Đặt giới hạn dựa trên thời gian gián đoạn và năng lực phục hồi. |

Khi điều tra, trước tiên xác nhận tên destination và group. Sau đó kiểm tra tài nguyên broker thực tế: queue và binding ở RabbitMQ, topic và offset ở Kafka, topic/subscription/cursor ở Pulsar. Cuối cùng mới xem cấu hình producer và consumer trong ứng dụng; một giá trị YAML đúng tên chưa chứng minh tài nguyên broker đã được tạo như dự kiến.

## 10. Quy trình lựa chọn và vận hành

Trước khi bật required groups, hãy trả lời:

1. Có những nhóm nghiệp vụ nào cần nhận cùng một sự kiện?
2. Các nhóm đó phải nhận dữ liệu từ thời điểm nào?
3. Consumer có thể khởi động muộn tối đa bao lâu?
4. Broker có tài nguyên nhận riêng cho group hay dùng log/subscription?
5. Dữ liệu có thể hết hạn hoặc bị xóa do giới hạn nào?
6. Ai chịu trách nhiệm provision, giám sát và xóa tài nguyên khi group ngừng hoạt động?

Áp dụng theo binder:

- **RabbitMQ:** dùng **requiredGroups** khi producer cần tạo trước queue/binding cho những group đã biết. Kiểm tra durability, persistent delivery, TTL, expires, queue limits và DLQ.
- **Kafka:** dựa vào topic log, retention và offset khởi tạo. Dùng group ổn định; đặt **startOffset** rõ ràng cho group mới nếu yêu cầu đọc dữ liệu lịch sử.
- **Pulsar:** quản lý durable subscription, initial position và namespace retention. Tạo subscription trước khi publish nếu cần backlog chắc chắn từ đầu; nếu tạo sau, phải bảo đảm dữ liệu còn trong retention và chọn earliest khi phù hợp.

Không đưa tất cả tên group vào requiredGroups theo thói quen. Chỉ khai báo những group có yêu cầu nhận dữ liệu trước khi consumer hoạt động và được đội vận hành quản lý. Danh sách group sai hoặc cũ có thể tạo tài nguyên không cần thiết, làm tăng dung lượng lưu trữ và chi phí dọn dẹp.

## 11. Checklist trước khi triển khai

- [ ] **requiredGroups** được khai báo trên đúng output binding nếu binder hỗ trợ hành vi cần thiết.
- [ ] Danh sách group phân tách bằng dấu phẩy và khớp chính xác với group ở input binding.
- [ ] Đã xác định consumer khởi động trước hay sau producer.
- [ ] RabbitMQ đã có queue/binding cho từng required group trước khi publish.
- [ ] RabbitMQ queue và message có độ bền phù hợp; TTL, expires, max length và DLQ đã được xem xét.
- [ ] Kafka topic retention đủ dài và startOffset của group mới phù hợp.
- [ ] Pulsar durable subscription đã được tạo hoặc retention/initial position được cấu hình cho consumer khởi động muộn.
- [ ] Không giả định requiredGroups tạo cùng một loại tài nguyên trên Kafka, RabbitMQ và Pulsar.
- [ ] Integration test đã chạy theo thứ tự producer trước, consumer sau.
- [ ] Có metric backlog/lag/queue depth và cảnh báo khi consumer ngừng xử lý.
- [ ] Có quy trình loại bỏ group và tài nguyên broker không còn sử dụng.

**requiredGroups** là một thuộc tính phía producer nhằm chuẩn bị khả năng nhận dữ liệu cho các nhóm đã biết, nhưng ý nghĩa vận hành của nó phải được đọc cùng binder. RabbitMQ dùng queue và binding nên có thể provision tài nguyên cho từng required group. Kafka dùng topic log và offset, còn Pulsar dùng subscription cursor cùng retention; hai binder này cần cấu hình tài nguyên và vị trí bắt đầu theo cơ chế riêng. Hiểu đúng sự khác biệt giúp hệ thống xử lý được trường hợp consumer khởi động muộn mà không dựa vào một giả định giao nhận chung cho mọi broker.

## Tài liệu tham khảo

- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Consumer Groups](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/consumer-groups.html)
- [RabbitMQ Binder — Producer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/prod-props.html)
- [RabbitMQ Binder — Existing Queues and Exchanges](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/existing-destinations.html)
- [Kafka Binder — Resetting Offsets](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/reset-offsets.html)
- [Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Apache Pulsar — Message Retention and Expiry](https://pulsar.apache.org/docs/next/cookbooks-retention-expiry/)
- [Apache Pulsar — Messaging and Subscriptions](https://pulsar.apache.org/docs/4.0.x/concepts-messaging/)
