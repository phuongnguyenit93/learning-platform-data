# Tên exchange, tên queue và các tiền tố tài nguyên

Trong RabbitMQ Binder của Spring Cloud Stream, tên `destination` và `group` ảnh hưởng trực tiếp đến tên tài nguyên được tạo trên broker. Thông thường, `destination` xác định exchange; khi consumer khai báo `group`, binder tạo queue gắn với exchange đó. Thuộc tính `queueNameGroupOnly` thay đổi cách đặt tên queue, còn `spring.cloud.stream.rabbit.binder.prefix` cho phép thêm một tiền tố chung vào tên các exchange và queue do binder quản lý.

Hiểu quy tắc đặt tên giúp tránh tạo nhầm tài nguyên, tránh xung đột giữa môi trường và bảo đảm các producer/consumer cùng kết nối vào đúng topology. Tên exchange, queue và routing key là ba khái niệm khác nhau: exchange nhận message, queue lưu message để consumer nhận, còn routing key giúp exchange quyết định message được đưa đến queue nào.

Bài thuộc chương **RabbitMQ Binder** của module `SPRING_CLOUD_STREAM`, tập trung vào tên exchange, queue và tiền tố tài nguyên trong mô hình hàm `Supplier`/`Function`/`Consumer`. Nội dung cũng giải thích quan hệ giữa destination, consumer group, routing key, virtual host, provisioning và quy trình thay đổi tên an toàn.

## 1. Các tài nguyên RabbitMQ cần phân biệt

RabbitMQ sử dụng một số loại tài nguyên AMQP để định tuyến và lưu message:

| Tài nguyên | Vai trò | Ví dụ |
|---|---|---|
| Exchange | Nhận message từ producer và định tuyến theo loại exchange/routing key | `orders.events` |
| Queue | Lưu message đang chờ consumer nhận | `orders.events.inventory-projection` |
| Binding | Liên kết exchange với queue, có thể kèm binding key | Exchange `orders.events` liên kết queue inventory bằng `orders.*` |
| Routing key | Giá trị producer gửi kèm message để exchange định tuyến | `orders.created` |
| Virtual host (vhost) | Không gian tài nguyên và quyền truy cập độc lập trong broker | `/production` |

```text
Producer
   |
   | publish(exchange, routingKey, message)
   v
Exchange: orders.events
   |
   | binding key: orders.created
   v
Queue: orders.events.inventory-projection
   |
   v
Consumer group: inventory-projection
```

Exchange không phải nơi consumer lấy message trực tiếp. Queue mới là nơi giữ message cho consumer. Một exchange có thể được bind với nhiều queue; một queue cũng có thể được bind với nhiều exchange. Tên exchange và queue có thể có quan hệ theo quy ước binder, nhưng chúng vẫn là hai tài nguyên riêng biệt.

## 2. `destination` thường xác định tên exchange

Trong RabbitMQ Binder, `destination` của binding thường được dùng làm tên exchange mà binder kết nối hoặc khai báo. Ví dụ:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          content-type: application/json
```

Với cấu hình này, output binding `publishOrder-out-0` gửi message đến exchange `orders.events` trong phạm vi vhost và cấu hình binder đang dùng. Producer không nhất thiết tạo queue; queue thường được khai báo bởi consumer binding hoặc bởi quy trình quản trị topology riêng.

Nếu producer và consumer cùng dùng `destination: orders.events`, chúng đang tham chiếu cùng exchange logic. Consumer còn cần queue để nhận message. Tên queue phụ thuộc group và cấu hình Rabbit binder.

Không nhầm tên function hoặc binding với tên exchange. `publishOrder-out-0` là tên binding trong ứng dụng; `orders.events` là destination và thường là exchange trên RabbitMQ.

## 3. `group` tham gia tạo tên queue

Với consumer binding có group, RabbitMQ Binder mặc định đặt tên queue theo destination và group. Quy ước thường gặp:

```text
<destination>.<group>
```

Ví dụ:

```yaml
spring:
  cloud:
    function:
      definition: projectInventory
    stream:
      bindings:
        projectInventory-in-0:
          destination: orders.events
          group: inventory-projection
```

Tên queue mặc định tương ứng là:

```text
orders.events.inventory-projection
```

Các replica của cùng một consumer logic phải dùng chung group. Khi đó, chúng cùng tiêu thụ queue và RabbitMQ phân phối message giữa các consumer theo cơ chế competing consumers. Nếu một ứng dụng khác dùng group riêng, binder tạo queue khác và queue đó cũng được bind với exchange; mỗi group có thể nhận bản sao của message theo binding/routing topology.

Ví dụ hai consumer độc lập:

| Consumer | Destination | Group | Queue mặc định |
|---|---|---|---|
| Inventory projection | `orders.events` | `inventory-projection` | `orders.events.inventory-projection` |
| Analytics projection | `orders.events` | `analytics-projection` | `orders.events.analytics-projection` |

Hai queue phục vụ hai mục đích xử lý khác nhau. Không tạo group riêng cho từng pod của cùng một ứng dụng nếu mục tiêu là chia tải; làm như vậy có thể khiến mỗi pod có một queue riêng và nhận bản sao độc lập thay vì cùng cạnh tranh trên một queue.

## 4. Consumer không có group

Nếu không khai báo `group`, consumer thường được xem là anonymous subscription. RabbitMQ Binder có thể tạo queue tạm/ẩn danh với tên do binder hoặc broker sinh, thường có đặc tính auto-delete hoặc không bền vững tùy cấu hình.

Kiểu subscription này hữu ích cho thử nghiệm hoặc consumer chỉ cần nhận message trong thời gian tồn tại của ứng dụng. Nó không phù hợp khi cần một queue ổn định để giữ message trong lúc ứng dụng offline.

Với consumer production cần độ bền vững, hãy khai báo group có tên ổn định. Queue có tên ổn định giúp:

- Message tiếp tục được lưu khi consumer tạm thời dừng, nếu queue durable và message được publish persistent theo cấu hình.
- Nhiều replica cùng tham gia một queue.
- Quản trị viên theo dõi backlog, consumer và quyền truy cập.
- Topology có thể được provision và kiểm tra trước khi triển khai.

Chỉ khai báo group chưa đủ để mọi điều kiện durability được đáp ứng. Cần kiểm tra cấu hình queue durable, exchange durable, delivery mode, TTL và các policy của RabbitMQ.

## 5. `queueNameGroupOnly` thay đổi cách đặt tên queue

RabbitMQ Binder có thuộc tính `queueNameGroupOnly`. Khi giữ mặc định `false`, queue thường bao gồm cả destination và group. Khi bật `true`, tên queue chỉ dựa trên group.

Ví dụ:

```yaml
spring:
  cloud:
    function:
      definition: projectInventory
    stream:
      bindings:
        projectInventory-in-0:
          destination: orders.events
          group: inventory-projection
      rabbit:
        bindings:
          projectInventory-in-0:
            consumer:
              queue-name-group-only: true
```

Tên queue theo chế độ group-only là:

```text
inventory-projection
```

So sánh:

| `queue-name-group-only` | Queue name theo quy ước |
|---|---|
| `false` | `orders.events.inventory-projection` |
| `true` | `inventory-projection` |

Thuộc tính này chỉ thay đổi cách tạo tên queue. Nó không thay đổi tên exchange theo destination, không đổi routing key và không biến group thành exchange.

### Khi nào dùng group-only?

Chế độ group-only hữu ích khi hệ thống đã có quy ước tên queue độc lập với destination hoặc cần tương thích với topology RabbitMQ được quản lý bên ngoài. Tuy nhiên, group name lúc này phải đủ duy nhất trong phạm vi vhost và binder. Nếu hai destination khác nhau cùng dùng group `worker`, chúng có thể cùng hướng đến queue `worker`, gây xung đột hoặc ghép các luồng dữ liệu ngoài dự kiến.

Chỉ bật `queueNameGroupOnly` khi đã kiểm tra toàn bộ consumer dùng chung vhost và xác nhận group name không va chạm. Nếu không có yêu cầu tương thích topology, tên mặc định gồm destination và group thường dễ truy vết hơn.

## 6. Thêm tiền tố bằng Rabbit binder `prefix`

Rabbit binder có thuộc tính cấp binder `prefix` để thêm một chuỗi đứng trước tên exchange và queue mà binder khai báo. Thuộc tính thường được cấu hình tại:

```text
spring.cloud.stream.rabbit.binder.prefix
```

Ví dụ:

```yaml
spring:
  cloud:
    stream:
      rabbit:
        binder:
          prefix: "prod."
```

Với destination `orders.events` và group `inventory-projection`, tên tài nguyên được thêm tiền tố theo quy ước:

| Tài nguyên | Không có prefix | Với prefix `prod.` |
|---|---|---|
| Exchange | `orders.events` | `prod.orders.events` |
| Queue mặc định | `orders.events.inventory-projection` | `prod.orders.events.inventory-projection` |
| Queue khi group-only | `inventory-projection` | `prod.inventory-projection` |

Prefix là một phần của tên tài nguyên vật lý. Ứng dụng vẫn có thể dùng destination logic `orders.events` trong cấu hình binding; binder thêm prefix khi khai báo/resolve tài nguyên RabbitMQ theo cấu hình.

Prefix giúp phân biệt tài nguyên giữa các môi trường hoặc nhóm ứng dụng trên cùng vhost, ví dụ `dev.`, `staging.` và `prod.`. Tuy nhiên, prefix không phải ranh giới bảo mật và không thay thế virtual host hoặc ACL.

## 7. Prefix áp dụng cho resource name, không phải routing key

Prefix của Rabbit binder nhằm thêm tiền tố vào tên exchange và queue do binder quản lý. Routing key và binding key là các giá trị định tuyến message; chúng có quy tắc cấu hình riêng.

Ví dụ:

```text
prefix = prod.
destination = orders.events
group = inventory-projection
binding key = orders.created

Exchange:    prod.orders.events
Queue:       prod.orders.events.inventory-projection
Binding key: orders.created
```

Không tự thêm `prod.` vào routing key chỉ vì đã cấu hình binder prefix. Nếu routing key cần phân biệt môi trường hoặc tenant, hãy thiết kế nó như một phần của hợp đồng routing riêng và cấu hình producer/consumer nhất quán.

## 8. Cấu hình hoàn chỉnh cho producer và consumer

Ví dụ một producer phát sự kiện đơn hàng và consumer inventory nhận sự kiện:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder;projectInventory
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          content-type: application/json
        projectInventory-in-0:
          destination: orders.events
          group: inventory-projection
          content-type: application/json
      rabbit:
        binder:
          prefix: "prod."
        bindings:
          publishOrder-out-0:
            producer:
              exchange-type: topic
          projectInventory-in-0:
            consumer:
              queue-name-group-only: false
              binding-routing-key: "orders.*"
```

Topology logic được mong đợi:

```text
Producer binding: publishOrder-out-0
Destination: orders.events
          |
          v
Exchange: prod.orders.events (topic)
          |
          | binding key: orders.*
          v
Queue: prod.orders.events.inventory-projection
          |
          v
Consumer binding: projectInventory-in-0
```

Producer và consumer cùng dùng destination logic `orders.events`; binder prefix làm tên exchange vật lý thành `prod.orders.events`. Consumer group tạo queue logic theo destination và group, rồi prefix được thêm vào tên queue. Binding key `orders.*` quyết định message nào được định tuyến vào queue khi dùng topic exchange.

Nếu exchange đã tồn tại với loại `direct` nhưng binding mới cố khai báo cùng tên với loại `topic`, RabbitMQ có thể từ chối thao tác redeclare vì thuộc tính exchange không tương thích. Tất cả producer và consumer cùng chia sẻ một exchange phải thống nhất exchange type và các thuộc tính topology.

## 9. Exchange type không phải tên exchange

`exchange-type` xác định cách exchange định tuyến, không thay đổi quy tắc tên destination. Các loại thường gặp:

| Exchange type | Cách định tuyến | Ví dụ |
|---|---|---|
| `direct` | Routing key phải khớp chính xác binding key | `orders.created` |
| `topic` | Routing key khớp pattern có `*` và `#` | `orders.*`, `orders.#` |
| `fanout` | Gửi đến mọi queue được bind, không dựa trên routing key | Phát thông báo đến nhiều consumer |
| `headers` | Định tuyến dựa trên message headers và binding arguments | Message có header `region=apac` |

Ví dụ `destination: orders.events` vẫn là tên exchange logic dù `exchange-type` là `direct` hay `topic`. Khi nhiều binding cùng khai báo exchange, chúng phải nhất quán về loại exchange và các thuộc tính declaration.

## 10. Virtual host khác với prefix

RabbitMQ virtual host tạo không gian tài nguyên riêng. Hai vhost có thể có exchange và queue trùng tên nhưng chúng là các tài nguyên độc lập. Prefix chỉ thay đổi chuỗi tên trong cùng không gian tài nguyên.

| Tiêu chí | Prefix | Virtual host |
|---|---|---|
| Mục đích | Phân biệt tên tài nguyên | Phân vùng tài nguyên và quyền truy cập |
| Phạm vi | Trong một vhost | Tách biệt tài nguyên trong broker |
| ACL | Không tự tạo ranh giới quyền | Có quyền configure/write/read theo vhost |
| Tên trùng | Vẫn có thể xung đột nếu prefix giống nhau | Có thể dùng cùng tên trong vhost khác |
| Ví dụ | `prod.orders.events` | Vhost `/production` chứa `orders.events` |

Nếu môi trường production và staging cần cách ly dữ liệu và quyền truy cập, nên dùng vhost riêng hoặc cluster riêng theo yêu cầu bảo mật. Prefix hữu ích để nhận diện tài nguyên và tránh va chạm tên khi nhiều ứng dụng dùng chung vhost, nhưng không nên xem nó là cơ chế bảo vệ dữ liệu.

## 11. Đặt prefix theo môi trường

Có thể truyền prefix qua cấu hình môi trường để dùng cùng một artifact cho nhiều môi trường:

```yaml
spring:
  cloud:
    stream:
      rabbit:
        binder:
          prefix: "${RABBIT_RESOURCE_PREFIX:dev.}"
```

Ví dụ giá trị:

```text
Local:       RABBIT_RESOURCE_PREFIX=local.
Development: RABBIT_RESOURCE_PREFIX=dev.
Staging:     RABBIT_RESOURCE_PREFIX=staging.
Production:  RABBIT_RESOURCE_PREFIX=prod.
```

Đặt prefix trong cấu hình môi trường hoặc secret/config management của nền tảng. Tránh hardcode tên môi trường vào từng destination vì sẽ làm binding configuration bị lặp và khó thay đổi.

Prefix nên ổn định trong suốt vòng đời triển khai. Nếu đổi từ `prod.` sang `production.`, binder có thể bắt đầu khai báo exchange/queue mới trong khi tài nguyên cũ vẫn còn. Message đang chờ trong queue cũ không tự chuyển sang queue mới.

## 12. Quy tắc đặt tên tài nguyên

Tên resource nên dễ đọc, ổn định và có thể quản trị. Một quy ước thường dùng:

```text
<environment>.<domain>.<event>
<environment>.<domain>.<event>.<consumer-group>
```

Ví dụ:

```text
Exchange: prod.orders.events
Queue:    prod.orders.events.inventory-projection
Queue:    prod.orders.events.analytics-projection
```

Khuyến nghị:

- Dùng chữ thường và dấu chấm hoặc dấu gạch ngang nhất quán.
- Tên phản ánh domain/event hoặc vai trò consumer, không chứa thông tin cá nhân.
- Giữ tên ổn định qua các lần deploy và restart.
- Tránh dùng dữ liệu request tùy ý để tạo tên exchange/queue.
- Giới hạn độ dài; RabbitMQ giới hạn tên queue/exchange theo giới hạn giao thức/broker, nên ưu tiên tên ngắn, có cấu trúc.
- Đặt group đủ cụ thể để tránh va chạm khi dùng `queueNameGroupOnly`.
- Không nhúng số phiên bản build hoặc pod ID vào tên queue bền vững.

Không dùng một prefix chung cho hai ứng dụng nếu chúng cần topology hoặc quyền khác nhau nhưng không có quy ước namespace tiếp theo. Tên resource phải phản ánh chủ sở hữu và vòng đời vận hành.

## 13. Prefix và quyền provisioning

RabbitMQ Binder có thể khai báo exchange, queue và binding dựa trên binding configuration. Để binder tự tạo tài nguyên, tài khoản kết nối cần quyền configure phù hợp trong vhost; producer cần quyền write lên exchange và consumer cần quyền read trên queue.

Khi hạ tầng được provision trước bằng Terraform, Ansible hoặc quy trình quản trị broker, cần thống nhất tên vật lý với binder. Nếu binder vẫn cố khai báo một resource đã tồn tại nhưng khác loại, durability hoặc arguments, RabbitMQ có thể từ chối declaration. Nếu tổ chức yêu cầu binder không tự khai báo một số tài nguyên, hãy cấu hình các tùy chọn declaration/binding tương ứng của đúng phiên bản Rabbit binder và kiểm thử với topology đã provision.

Ví dụ quyền cần xem xét:

| Thành phần | Quyền cần thiết theo vai trò |
|---|---|
| Producer | Write vào exchange mà producer publish |
| Consumer binder | Read queue; configure/bind nếu binder tự khai báo topology |
| Quản trị hạ tầng | Configure exchange/queue/binding và policy |
| Công cụ giám sát | Read/inspect metadata theo quyền được cấp |

Không cấp quyền quản trị toàn vhost cho ứng dụng chỉ để nó có thể publish. Cấp quyền tối thiểu theo resource và trách nhiệm của từng service.

## 14. Thay đổi destination, group hoặc prefix là thay đổi topology

Đổi tên exchange hoặc queue không đơn thuần là đổi một chuỗi trong file YAML. RabbitMQ không tự di chuyển message từ resource cũ sang resource mới.

Ví dụ đổi prefix:

```text
Trước: prod.orders.events
Sau:   production.orders.events
```

Sau khi deploy cấu hình mới, binder có thể khai báo exchange mới. Queue mới cũng có thể được tạo và bind vào exchange mới. Queue cũ vẫn có thể chứa message chưa xử lý và consumer cũ có thể vẫn đang hoạt động.

Quy trình migration nên:

1. Liệt kê exchange, queue, binding và backlog hiện tại.
2. Tạo resource mới với tên và thuộc tính đã thống nhất.
3. Cấu hình producer publish đến exchange mới hoặc dual-publish có kiểm soát nếu cần.
4. Khởi động consumer mới và xác nhận queue/binding đúng.
5. Drain hoặc replay message còn tồn tại ở queue cũ theo chính sách.
6. Chuyển toàn bộ producer/consumer sang topology mới.
7. Xác nhận queue cũ không còn message/consumer rồi mới xóa.
8. Lưu lại mapping tên cũ và tên mới để audit.

Không xóa queue cũ ngay sau khi đổi group hoặc prefix nếu chưa kiểm tra backlog. Việc xóa có thể làm mất message chưa được xử lý.

## 15. Tránh xung đột khi dùng nhiều binder hoặc nhiều service

Một ứng dụng Spring Cloud Stream có thể dùng nhiều binder, nhưng mỗi binder có namespace cấu hình và kết nối broker riêng. Rabbit resource prefix thuộc Rabbit binder; không áp dụng cho Kafka topic hoặc Pulsar topic.

Nếu nhiều service dùng chung RabbitMQ vhost, hãy xác định:

- Service nào sở hữu exchange và queue.
- Các service nào được phép bind queue vào exchange.
- Prefix có phân biệt môi trường hoặc domain không.
- Group name có duy nhất nếu dùng group-only queue naming không.
- Các exchange cùng tên có cùng type và declaration arguments không.
- Ai chịu trách nhiệm cleanup resource khi service ngừng hoạt động.

Không tạo queue riêng cho mỗi replica của cùng một consumer group nếu muốn competing consumers. Cũng không dùng cùng queue cho hai service độc lập nếu chúng phải nhận đầy đủ bản sao message; hai service cần hai queue và hai binding riêng.

## 16. Kiểm tra tên tài nguyên khi chạy

Không chỉ dựa vào tên logic trong YAML. Sau khi ứng dụng khởi động, kiểm tra tên vật lý trong RabbitMQ Management UI hoặc RabbitMQ CLI:

- Exchange có đúng prefix và destination không?
- Queue có đúng destination/group hoặc group-only không?
- Queue có durable/auto-delete đúng yêu cầu không?
- Binding key có đúng pattern không?
- Exchange type có khớp giữa producer và consumer không?
- Queue có consumer đang kết nối không?
- Message có đi vào queue mong đợi không?

Có thể dùng lệnh RabbitMQ CLI để liệt kê tài nguyên trong vhost tương ứng:

```bash
rabbitmqctl list_exchanges -p /production name type durable
rabbitmqctl list_queues -p /production name durable auto_delete messages consumers
rabbitmqctl list_bindings -p /production source_name destination_name routing_key
```

Các lệnh cần quyền quản trị phù hợp và phải chạy trên node/cluster có công cụ RabbitMQ CLI. Với môi trường production, thao tác đọc thông tin topology nên theo quyền vận hành được cấp.

## 17. Kiểm thử quy tắc đặt tên

Một bộ integration test nên xác minh tên exchange/queue thực tế sau khi binder khai báo topology:

| Kịch bản | Cấu hình | Kết quả cần xác minh |
|---|---|---|
| Tên mặc định | destination và group, không prefix | Exchange bằng destination; queue theo destination/group |
| Prefix | Prefix `dev.` | Tên exchange/queue có tiền tố đúng |
| Group-only | `queue-name-group-only: true` | Queue name chỉ dựa trên group, có prefix nếu cấu hình |
| Hai group | Cùng destination, group khác nhau | Hai queue độc lập cùng bind vào exchange |
| Cùng group, nhiều replica | Các replica dùng chung destination/group | Cùng tiêu thụ một queue |
| Anonymous consumer | Không khai báo group | Kiểm tra queue ẩn danh và lifecycle thực tế |
| Routing key | Topic/direct exchange và binding key cụ thể | Message đến đúng queue |
| Prefix khác môi trường | `dev.` và `prod.` | Resource name không va chạm theo thiết kế |
| Exchange declaration conflict | Cùng tên nhưng exchange type khác | Broker từ chối declaration; phát hiện trước khi deploy |
| Migration prefix | Chuyển từ prefix cũ sang mới | Queue cũ được drain/replay trước cleanup |

Test binder có thể kiểm tra message flow ở tầng Spring, nhưng không xác nhận đầy đủ tên exchange/queue và binding trên RabbitMQ thật. Cần integration test với broker tương thích hoặc kiểm tra topology qua RabbitMQ management API/CLI.

## 18. Quan sát và vận hành

Theo dõi các chỉ số:

- Số exchange và queue được tạo theo prefix.
- Queue backlog, tuổi message cũ nhất và tốc độ tăng message.
- Số consumer trên từng queue.
- Tỷ lệ publish không định tuyến được hoặc message bị trả về nếu publisher returns được bật.
- Lỗi declaration do resource cùng tên nhưng khác thuộc tính.
- Lỗi permission khi configure, write, read hoặc bind.
- Số queue không còn consumer hoặc resource cũ sau migration.

Log nên ghi binding name, destination logic, group và vhost; khi có thể, ghi thêm tên exchange/queue vật lý đã resolve. Không đưa payload nhạy cảm hoặc credential vào log. Metric label cần giới hạn để tránh cardinality cao nếu có nhiều destination động.

Đặt cảnh báo khi queue không có consumer, backlog tăng kéo dài, exchange/queue declaration thất bại hoặc resource tăng bất thường sau một lần deploy.

## 19. Quy trình thiết kế tên exchange, queue và prefix

Khi cấu hình RabbitMQ Binder:

1. Chọn destination ổn định cho exchange theo domain/event.
2. Chọn group ổn định cho từng consumer logic.
3. Quyết định queue name mặc định gồm destination/group hay group-only.
4. Nếu dùng group-only, bảo đảm group name duy nhất trong vhost/binder namespace.
5. Chọn prefix theo môi trường hoặc namespace ứng dụng nếu nhiều topology dùng chung vhost.
6. Phân biệt prefix với vhost; dùng vhost/ACL khi cần cách ly bảo mật.
7. Thống nhất exchange type, durability và binding arguments giữa các service.
8. Provision resource và cấp configure/write/read permissions phù hợp.
9. Kiểm tra tên vật lý bằng RabbitMQ Management UI hoặc CLI.
10. Lập kế hoạch migration khi đổi destination, group hoặc prefix; drain queue cũ trước cleanup.

## 20. Tự kiểm tra

- [ ] Phân biệt được exchange, queue, binding và routing key.
- [ ] Giải thích được vì sao destination thường xác định exchange name.
- [ ] Giải thích được cách group tham gia tạo queue name mặc định.
- [ ] Phân biệt consumer group có tên với anonymous subscription.
- [ ] Biết `queueNameGroupOnly` thay đổi tên queue như thế nào.
- [ ] Cấu hình được `spring.cloud.stream.rabbit.binder.prefix`.
- [ ] Hiểu prefix áp dụng cho tên resource, không tự thay đổi routing key.
- [ ] Phân biệt prefix với RabbitMQ virtual host.
- [ ] Biết exchange type và declaration arguments phải nhất quán giữa các binding.
- [ ] Thiết kế được migration an toàn khi đổi destination, group hoặc prefix.
- [ ] Kiểm tra được topology thực tế bằng RabbitMQ Management UI/CLI.

## Kết luận

Trong RabbitMQ Binder, `destination` thường xác định exchange; `group` tham gia tạo queue theo quy ước destination cộng group. `queueNameGroupOnly` có thể rút gọn queue name chỉ còn group, còn `spring.cloud.stream.rabbit.binder.prefix` thêm tiền tố vào tên exchange và queue do binder quản lý. Prefix giúp phân biệt resource giữa môi trường nhưng không thay thế virtual host hoặc ACL. Hãy giữ tên ổn định, bảo đảm group không va chạm, thống nhất exchange declaration và kiểm tra topology thực tế. Khi đổi tên hoặc prefix, cần migration và drain queue cũ để tránh bỏ sót message.
