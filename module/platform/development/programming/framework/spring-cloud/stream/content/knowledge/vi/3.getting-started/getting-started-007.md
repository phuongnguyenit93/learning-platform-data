# Quan sát tài nguyên được tạo trên broker và đối chiếu kết quả

Khi một ứng dụng Spring Cloud Stream khởi động, các binding của ứng dụng được binder kết nối với tài nguyên tương ứng trên broker. Tùy công nghệ truyền tin, tài nguyên đó có thể là topic, consumer group, exchange, queue, binding hoặc subscription. Việc kiểm tra trực tiếp broker giúp xác nhận cấu hình ứng dụng đã được ánh xạ đúng, publisher và subscriber đang dùng cùng destination, đồng thời phát hiện sớm những sai lệch về group, partition và quyền tạo tài nguyên.

Bài học này hướng dẫn quan sát tài nguyên trước và sau khi chạy ứng dụng, phát một thông điệp thử, theo dõi trạng thái tiêu thụ và đối chiếu kết quả trên Kafka, RabbitMQ hoặc Pulsar. Các lệnh minh họa dùng CLI phổ biến của từng broker; tên tài nguyên thực tế có thể thay đổi theo phiên bản binder, cấu hình đặt tên và môi trường triển khai.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Xác định tài nguyên broker mà một input binding hoặc output binding cần sử dụng.
- Dự đoán tài nguyên được tạo từ destination và consumer group.
- Dùng công cụ quản trị của Kafka, RabbitMQ và Pulsar để liệt kê, mô tả và kiểm tra tài nguyên.
- Đối chiếu cấu hình Spring Cloud Stream với topic, exchange, queue, partition hoặc subscription quan sát được.
- Phân biệt trạng thái tài nguyên, trạng thái kết nối consumer và trạng thái thông điệp đã được xử lý.
- Khoanh vùng nguyên nhân khi tài nguyên không xuất hiện hoặc có trạng thái khác dự kiến.

## 1. Từ binding đến tài nguyên trên broker

Spring Cloud Stream cung cấp mô hình binding thống nhất ở phía ứng dụng. Binder chuyển binding thành các cấu trúc mà broker cụ thể hiểu được. Vì thế, cùng một cấu hình destination và group có thể tạo ra những loại tài nguyên khác nhau.

Một binding tiêu thụ thường có hai thuộc tính quan trọng:

- `destination` xác định luồng thông điệp mà ứng dụng đăng ký nhận.
- `group` xác định nhóm consumer có tiến độ tiêu thụ riêng.

Ví dụ, ứng dụng có consumer function tên `inventory`:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InventoryConfiguration {

    @Bean
    Consumer<OrderCreated> inventory() {
        return event -> {
            System.out.println("Nhận đơn hàng: " + event.orderId());
        };
    }
}
~~~

Tên bean `inventory` tạo input binding mặc định `inventory-in-0`. Cấu hình sau gắn binding đó với destination `orders` và group `inventory`:

~~~yaml
spring:
  cloud:
    function:
      definition: inventory
    stream:
      bindings:
        inventory-in-0:
          destination: orders
          group: inventory
~~~

Nếu ứng dụng phát hành sự kiện qua `StreamBridge`, output binding có thể được cấu hình như sau:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders
~~~

Publisher gửi bằng tên binding đã cấu hình:

~~~java
streamBridge.send("orders-out-0", event);
~~~

Trong ví dụ này, publisher và consumer cùng dùng destination `orders`. Consumer group `inventory` xác định subscription của phía nhận. Output binding không cần khai báo group.

### Tài nguyên được kỳ vọng theo từng broker

| Broker | Destination thường ánh xạ tới | Group thường ánh xạ tới | Điều cần quan sát |
|---|---|---|---|
| Kafka | Topic | Consumer group và offset của group | Tên topic, số partition, replication factor, consumer group, offset và lag |
| RabbitMQ | Exchange | Queue được liên kết với exchange | Exchange, queue, binding, routing key, consumer và số message |
| Pulsar | Topic | Subscription | Tên topic đầy đủ, subscription, consumer, backlog và loại subscription |

Các ánh xạ trên là mô hình khái niệm. Tên queue RabbitMQ, namespace Pulsar, tiền tố tài nguyên và cách tạo subscription có thể chịu ảnh hưởng của cấu hình binder. Khi kiểm tra, hãy dùng tên thực tế trong cấu hình ứng dụng và log khởi động, sau đó xác nhận bằng công cụ quản trị của broker.

**Không đồng nhất destination với group.** Hai ứng dụng có thể cùng đọc destination `orders` nhưng dùng group khác nhau. Trong Kafka, chúng có consumer group và offset riêng; trong RabbitMQ, chúng thường có queue riêng cùng được liên kết tới exchange; trong Pulsar, chúng có subscription riêng trên cùng topic. Nếu hai instance của cùng một dịch vụ dùng chung group, chúng tham gia chia tải trong cùng subscription.

## 2. Chuẩn bị một lần chạy có thể đối chiếu

Trước khi khởi động ứng dụng, hãy ghi lại cấu hình có hiệu lực và trạng thái ban đầu của broker. Việc chụp trạng thái ban đầu giúp phân biệt tài nguyên đã tồn tại từ lần chạy trước với tài nguyên được provision trong lần chạy hiện tại.

Dùng một ví dụ thống nhất:

| Thuộc tính | Giá trị |
|---|---|
| Function consumer | `inventory` |
| Input binding | `inventory-in-0` |
| Destination | `orders` |
| Consumer group | `inventory` |
| Sự kiện thử | `OrderCreated` |
| Mục tiêu | Xác nhận consumer kết nối đúng destination và broker giữ đúng trạng thái tiêu thụ |

Kiểm tra những điểm sau trong cấu hình đã nạp:

1. Function bean tồn tại và được kích hoạt bằng `spring.cloud.function.definition`.
2. Tên input binding được suy ra đúng từ tên function.
3. Destination của producer và consumer giống nhau nếu chúng phải trao đổi cùng luồng.
4. Group có tên ổn định nếu consumer cần giữ tiến độ qua các lần khởi động.
5. Ứng dụng đang dùng đúng binder và đúng địa chỉ broker của môi trường đang kiểm tra.
6. Profile, biến môi trường hoặc cấu hình triển khai không ghi đè destination và group bằng giá trị khác.

Đừng chỉ đọc file YAML trong mã nguồn. Hãy đối chiếu cấu hình thực tế của tiến trình đang chạy, vì profile và biến môi trường có thể thay đổi giá trị cuối cùng.

## 3. Quan sát Kafka

Với Kafka binder, destination `orders` thường là topic `orders`. Consumer group `inventory` lưu tiến độ đọc bằng offset theo từng partition. Một topic có thể tồn tại trước khi consumer group xuất hiện; group thường chỉ được broker ghi nhận sau khi consumer tham gia, và offset chỉ xuất hiện sau khi có tiến độ được commit.

### Liệt kê và mô tả topic

Với Kafka CLI, chạy:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --list
~~~

Sau khi ứng dụng được khởi động, mô tả topic:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders
~~~

Đọc kết quả và đối chiếu:

- `Topic`: phải khớp destination mong đợi.
- `PartitionCount`: số partition thực tế phải phù hợp với thiết kế song song.
- `ReplicationFactor`: số bản sao của mỗi partition.
- `Leader`, `Replicas`, `Isr`: cho biết trạng thái phân phối bản sao và đồng bộ.
- Nếu topic không tồn tại, kiểm tra binder có được phép tạo topic hay tài nguyên cần được quản trị viên tạo trước.

Ví dụ, nếu topic có ba partition, một consumer group có thể phân phối ba partition đó cho tối đa ba consumer đang hoạt động cùng group tại một thời điểm. Thêm consumer vượt quá số partition không tự làm tăng số partition.

### Kiểm tra consumer group và offset

Liệt kê group:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list
~~~

Mô tả group:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group inventory
~~~

Các cột thường cần xem:

| Trường | Ý nghĩa |
|---|---|
| `GROUP` | Tên consumer group |
| `TOPIC` | Topic mà group đang đọc |
| `PARTITION` | Partition được theo dõi |
| `CURRENT-OFFSET` | Offset đã commit |
| `LOG-END-OFFSET` | Offset cuối hiện có trên partition |
| `LAG` | Số bản ghi group còn chậm so với cuối log |
| `CONSUMER-ID` / `HOST` | Consumer và máy đang tham gia group |

Nếu group chưa xuất hiện, kiểm tra consumer đã được kích hoạt và kết nối thành công chưa. Nếu group đã có nhưng chưa có offset, có thể consumer chưa xử lý và commit bản ghi nào. Nếu lag tăng liên tục, tốc độ phát hành đang vượt tốc độ tiêu thụ hoặc consumer gặp lỗi.

### Đối chiếu partition

Partition count không chỉ là một con số hiển thị. Hãy đối chiếu nó với:

- Số consumer instance dự kiến chạy đồng thời trong một group.
- Cấu hình partition của binding hoặc binder.
- Khả năng mở rộng của ứng dụng.
- Khóa phân vùng được dùng để giữ thứ tự cho các sự kiện cùng thực thể.

Nếu cấu hình yêu cầu thêm partition nhưng broker vẫn giữ số cũ, kiểm tra quyền quản trị và tùy chọn tự tăng partition của Kafka binder. Không tự tăng partition trên môi trường dùng chung khi chưa đánh giá ảnh hưởng tới thứ tự và phân phối khóa.

## 4. Quan sát RabbitMQ

Với RabbitMQ binder, destination thường được ánh xạ thành exchange. Khi có consumer group, binder thường provision một queue cho group rồi liên kết queue đó với exchange. Nhiều group độc lập có thể có các queue riêng để mỗi nhóm nhận bản sao thông điệp. Tên queue thực tế thường được tạo từ destination và group, nhưng có thể thay đổi theo prefix hoặc cấu hình binder.

### Liệt kê exchange

Chạy trên máy chủ RabbitMQ hoặc trong container broker:

~~~bash
rabbitmqctl list_exchanges name type durable auto_delete
~~~

Tìm exchange tương ứng với destination `orders`. Kiểm tra loại exchange, trạng thái durable và auto-delete theo thiết kế của ứng dụng.

### Liệt kê queue và trạng thái message

~~~bash
rabbitmqctl list_queues name durable auto_delete consumers messages_ready messages_unacknowledged
~~~

Đối chiếu các trường:

- `name`: queue được tạo cho group.
- `durable`: queue có tồn tại qua lần restart broker theo cấu hình hay không.
- `auto_delete`: queue có thể bị xóa khi điều kiện consumer cuối cùng ngừng hoạt động hay không.
- `consumers`: số consumer hiện đang đăng ký.
- `messages_ready`: số message đang chờ được giao cho consumer.
- `messages_unacknowledged`: số message đã giao nhưng chưa được xác nhận.

Một queue có `messages_ready=0` không nhất thiết có nghĩa publisher chưa gửi message. Consumer có thể đã nhận và xử lý nhanh. Hãy xem thêm `messages_unacknowledged`, bộ đếm publish/deliver/ack trên Management UI và log xử lý của ứng dụng.

### Kiểm tra binding giữa exchange và queue

~~~bash
rabbitmqctl list_bindings source_name source_kind destination_name destination_kind routing_key
~~~

Với group `inventory`, cần xác minh queue của group được liên kết tới exchange tương ứng. Nếu exchange tồn tại nhưng không có queue được liên kết, thông điệp có thể không đến được subscriber. Hãy kiểm tra routing key và binding arguments khi ứng dụng dùng định tuyến theo khóa hoặc partition.

Trong RabbitMQ Management UI, các khu vực thường dùng là:

- **Exchanges**: xem exchange, loại exchange, durable và số binding.
- **Queues and Streams**: xem queue, consumer, message ready và unacknowledged.
- **Bindings**: xem nguồn, đích và routing key của từng liên kết.

Queue có group thường tồn tại lâu hơn queue ẩn danh. Khi không cấu hình group, binder có thể dùng queue tạm thời hoặc tên ngẫu nhiên; queue đó có thể biến mất khi consumer ngừng hoạt động. Vì vậy, hãy xác định group trước khi kết luận queue bị thiếu.

## 5. Quan sát Apache Pulsar

Với Pulsar binder, destination ánh xạ tới topic. Consumer group được biểu diễn bằng subscription name. Tên topic đầy đủ có dạng:

~~~text
persistent://<tenant>/<namespace>/<topic>
~~~

Trong môi trường local phổ biến, topic có thể nằm trong namespace `public/default`, ví dụ `persistent://public/default/orders`. Môi trường khác có thể dùng tenant hoặc namespace riêng; luôn lấy giá trị từ cấu hình thực tế.

### Liệt kê topic

~~~bash
pulsar-admin topics list public/default
~~~

Tìm topic `orders`. Nếu không thấy, kiểm tra namespace, loại topic (persistent hoặc non-persistent), quyền truy cập và chính sách tạo topic tự động của broker.

### Xem subscription và thống kê topic

~~~bash
pulsar-admin topics subscriptions persistent://public/default/orders
~~~

Lấy thống kê:

~~~bash
pulsar-admin topics stats persistent://public/default/orders
~~~

Nếu topic được phân vùng, dùng lệnh thống kê dành cho partitioned topic:

~~~bash
pulsar-admin topics partitioned-stats persistent://public/default/orders
~~~

Trong thống kê, tập trung vào:

- Danh sách subscription và tên subscription tương ứng với group.
- Consumer đang kết nối và subscription type.
- Backlog của subscription.
- Tốc độ message vào/ra và số message được lưu.
- Trạng thái từng partition nếu topic có phân vùng.

Một subscription có thể chỉ được tạo khi consumer kết nối lần đầu. Vì vậy, topic tồn tại nhưng subscription chưa xuất hiện có thể là dấu hiệu consumer chưa khởi động thành công, group chưa được áp dụng hoặc ứng dụng đang kết nối tới namespace khác.

Pulsar hỗ trợ các subscription type như Exclusive, Shared, Failover và Key_Shared. Loại subscription quyết định cách nhiều consumer trong cùng subscription nhận message. Khi đối chiếu với thiết kế chia tải, hãy kiểm tra subscription type thực tế thay vì chỉ dựa vào tên group.

## 6. Phát một sự kiện và xác nhận đường đi

Việc tài nguyên xuất hiện mới xác nhận bước provisioning. Để chứng minh luồng hoạt động, hãy phát một sự kiện có định danh dễ tìm, ví dụ:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "order-1001",
  "occurredAt": "2026-11-24T09:00:00Z",
  "schemaVersion": 1
}
~~~

Thực hiện theo trình tự:

1. Khởi động broker và chờ broker báo trạng thái sẵn sàng.
2. Khởi động consumer Spring Cloud Stream, chờ log cho biết binding đã kết nối.
3. Kiểm tra tài nguyên broker và ghi lại topic/exchange/queue/subscription đã xuất hiện.
4. Gửi sự kiện qua publisher, chẳng hạn bằng `StreamBridge` với output binding trỏ tới `orders`.
5. Tìm `eventId=evt-1001` trong log consumer hoặc công cụ quan sát message phù hợp.
6. Kiểm tra lại offset, queue counters hoặc subscription backlog.
7. Đối chiếu kết quả trên ứng dụng với số liệu broker.

Với Kafka, có thể dùng console consumer để đọc thử bằng một group kiểm tra riêng:

~~~bash
kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic orders --from-beginning --max-messages 5 --group inspect-orders-unique
~~~

Dùng tên group kiểm tra duy nhất, không dùng group `inventory` của ứng dụng. Nếu dùng group của ứng dụng để đọc bằng công cụ dòng lệnh, tiến độ tiêu thụ có thể bị thay đổi và làm sai kết quả kiểm chứng.

Với RabbitMQ, quan sát bộ đếm message trên queue group trong Management UI hoặc dùng công cụ quản trị phù hợp với phiên bản đang chạy. Không xác nhận hoặc lấy message theo cách làm thay đổi trạng thái queue trước khi ghi lại số liệu cần đối chiếu.

Với Pulsar, quan sát subscription và backlog bằng `pulsar-admin topics stats`. Nếu dùng `pulsar-client consume` để đọc thử, hãy tạo subscription kiểm tra riêng và ghi nhớ rằng thao tác này có thể tạo subscription mới trên broker.

**Kết quả cần có:** publisher gửi đến đúng destination; broker nhận message; consumer group/subscription tương ứng xuất hiện; subscriber nhận đúng payload; và trạng thái offset, queue hoặc backlog thay đổi phù hợp với việc xử lý.

## 7. Quan sát khi consumer dừng và khởi động lại

Một phép kiểm chứng hữu ích là quan sát message trong lúc consumer tạm ngừng:

1. Ghi lại số liệu ban đầu của topic, queue hoặc subscription.
2. Dừng ứng dụng consumer một cách có kiểm soát.
3. Phát một vài sự kiện mới từ publisher.
4. Quan sát message được giữ lại hoặc backlog tăng theo chính sách của broker.
5. Khởi động lại consumer với cùng destination và group.
6. Xác minh consumer tiếp tục xử lý và trạng thái tồn đọng giảm.

Hành vi mong đợi có khác biệt:

| Broker | Khi consumer dừng | Khi consumer chạy lại |
|---|---|---|
| Kafka | Bản ghi tiếp tục được lưu theo retention; lag của group có thể tăng khi group đã có offset | Consumer tiếp tục từ offset đã commit theo cấu hình reset và trạng thái group |
| RabbitMQ | Message có thể tích lũy trong queue bền vững; queue tạm thời có thể bị xóa tùy cấu hình | Consumer kết nối lại queue còn tồn tại và xử lý message đang chờ |
| Pulsar | Backlog của subscription có thể tăng theo chính sách lưu giữ và subscription | Consumer tiếp tục đọc theo cursor của subscription |

Không nên dùng việc dừng consumer để kết luận message chắc chắn được giữ vô thời hạn. Kafka retention, RabbitMQ queue durability/TTL/overflow policy và Pulsar retention/expiry policy đều có thể làm message bị xóa hoặc hết hạn.

Khi ứng dụng khởi động lại, kiểm tra xem tài nguyên có giữ đúng tên và trạng thái không. Nếu mỗi lần khởi động lại tạo ra queue hoặc subscription mới, hãy kiểm tra group có ổn định không, profile có ghi đè cấu hình không và binder có đang tạo subscription ẩn danh hay không.

## 8. Đối chiếu kết quả và tìm sai lệch

Nên ghi lại kết quả theo cùng một mẫu để có thể so sánh giữa cấu hình và broker:

| Hạng mục | Cấu hình dự kiến | Kết quả quan sát | Đánh giá |
|---|---|---|---|
| Binder | Kafka / RabbitMQ / Pulsar | Binder thực tế | Khớp / lệch |
| Destination | `orders` | Topic / exchange / topic đầy đủ | Khớp / lệch |
| Group | `inventory` | Consumer group / queue / subscription | Khớp / lệch |
| Partition | Số lượng mong đợi | Số lượng thực tế | Khớp / lệch |
| Kết nối consumer | Một hoặc nhiều instance | Consumer đang hoạt động | Khớp / lệch |
| Message | Có event thử | Offset / ready / backlog / log | Đã nhận / đang chờ / chưa thấy |

Một số tình huống thường gặp:

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Không thấy tài nguyên nào | Function chưa được kích hoạt; binding name sai; ứng dụng chưa khởi động thành công; sai broker/namespace; binder không provision tự động hoặc thiếu quyền tạo tài nguyên |
| Kafka có topic nhưng chưa có group | Consumer chưa join group; function không chạy; group name khác cấu hình; consumer chưa commit offset |
| Kafka có group nhưng lag tăng | Consumer xử lý chậm, lỗi liên tục, thiếu instance hoặc partition chưa được phân phối như dự kiến |
| RabbitMQ có exchange nhưng không có queue | Consumer group chưa được tạo; queue tạm thời đã bị xóa; provisioning queue thất bại |
| RabbitMQ có queue nhưng không có binding | Queue chưa được liên kết với exchange hoặc routing key không khớp |
| Pulsar có topic nhưng không có subscription | Consumer chưa kết nối; group chưa được áp dụng; sai tenant/namespace hoặc subscription chỉ được tạo khi consumer bắt đầu |
| Tài nguyên xuất hiện với tên khác | Prefix, tên group, namespace, profile hoặc cấu hình binder làm thay đổi tên thực tế |
| Tài nguyên tồn tại nhưng không có message | Publisher chưa gửi; destination của producer và consumer khác nhau; message đã được xử lý nhanh; routing/partition/subscription không đúng |
| Queue hoặc subscription mới xuất hiện sau mỗi lần chạy | Consumer dùng group ẩn danh hoặc tên group thay đổi giữa các lần triển khai |

Khi phát hiện sai lệch, kiểm tra theo thứ tự sau:

1. **Cấu hình có hiệu lực:** destination, group, function definition, binder và profile.
2. **Log khởi động:** binding có được tạo không, kết nối broker có thành công không, lỗi provisioning có xuất hiện không.
3. **Tài nguyên broker:** tên, loại, partition, queue binding hoặc subscription.
4. **Quyền truy cập:** tài khoản ứng dụng có quyền kết nối, khai báo, ghi và đọc tài nguyên cần thiết không.
5. **Luồng message:** publisher có gửi đến đúng destination không, subscriber có nhận được không và trạng thái tiêu thụ thay đổi ra sao.

Đừng vội tạo thủ công một tài nguyên mới khi tên tài nguyên không khớp. Trước tiên xác định cấu hình thực tế và quy tắc đặt tên của binder; nếu tạo thêm topic, queue hoặc subscription sai tên, bạn có thể khiến hệ thống có nhiều luồng rời rạc khó theo dõi.

## 9. Quyền provision và trách nhiệm vận hành

Binder có thể tự khai báo hoặc yêu cầu broker tạo tài nguyên, nhưng khả năng này phụ thuộc binder, phiên bản, cấu hình và quyền của tài khoản kết nối. Trong môi trường production, tổ chức có thể chủ động tạo topic, exchange, queue, namespace hoặc subscription trước khi triển khai ứng dụng.

Các quyền cần xem xét gồm:

- **Kafka:** quyền mô tả topic, tạo topic khi được phép, ghi dữ liệu và tham gia/đọc consumer group.
- **RabbitMQ:** quyền configure để khai báo exchange/queue/binding, write để publish và read để consume.
- **Pulsar:** quyền truy cập namespace/topic và quyền producer/consumer phù hợp với chính sách bảo mật.

Nếu ứng dụng chỉ có quyền đọc và ghi nhưng không có quyền khai báo tài nguyên, broker có thể từ chối bước provisioning. Khi đó, log thường chứa lỗi authorization hoặc access denied. Hãy phối hợp với người quản trị broker để tạo tài nguyên và cấp quyền tối thiểu cần thiết.

Không nên bật chế độ debug dài hạn trên production. Khi cần chẩn đoán, có thể tăng log cho Spring Cloud Stream và package binder trong thời gian ngắn, thu thập thông tin cần thiết rồi đưa log level về mức vận hành bình thường. Log có thể chứa payload hoặc metadata nhạy cảm, vì vậy hãy tuân theo chính sách ghi log của hệ thống.

## 10. Bài thực hành: đối chiếu một destination trên ba broker

Dùng cùng một ứng dụng consumer với destination `orders` và group `inventory`. Thực hiện từng broker trong môi trường thử nghiệm riêng để tránh nhầm lẫn tài nguyên giữa các môi trường.

**Bước 1 — Dự đoán**

Trước khi chạy, viết ra tài nguyên bạn mong đợi:

- Kafka: topic `orders`; consumer group `inventory` sau khi consumer tham gia.
- RabbitMQ: exchange cho destination `orders`; queue của group `inventory`; binding nối queue với exchange.
- Pulsar: topic `orders` trong tenant/namespace đã cấu hình; subscription `inventory` sau khi consumer kết nối.

**Bước 2 — Chụp trạng thái trước khi chạy**

Dùng lệnh liệt kê tài nguyên tương ứng ở các phần trên. Ghi rõ tài nguyên nào đã tồn tại từ trước.

**Bước 3 — Khởi động ứng dụng**

Chạy consumer, chờ trạng thái sẵn sàng và lưu log binding. Chụp lại danh sách tài nguyên để nhận diện những tài nguyên mới được tạo.

**Bước 4 — Phát và xử lý sự kiện**

Gửi một sự kiện `OrderCreated` có `eventId` riêng. Xác minh log consumer và trạng thái message trên broker.

**Bước 5 — Kiểm tra vòng đời**

Dừng consumer, phát thêm sự kiện, quan sát backlog hoặc lag rồi khởi động lại cùng group. Ghi nhận tài nguyên có được tái sử dụng và consumer có tiếp tục từ trạng thái phù hợp hay không.

**Bước 6 — So sánh**

Hoàn thành bảng sau bằng kết quả thực tế:

| Nội dung | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| Tài nguyên destination | Topic | Exchange | Topic |
| Tài nguyên group | Consumer group/offset | Queue và binding | Subscription |
| Thông tin phân vùng | Partition | Không tương đương Kafka partition trong mọi cấu hình | Partitioned topic nếu được cấu hình |
| Chỉ số tồn đọng | Consumer lag | Ready / unacknowledged | Subscription backlog |
| Trạng thái sau restart | Offset/group | Queue và message | Subscription cursor |
| Sai lệch quan sát được | Ghi kết quả | Ghi kết quả | Ghi kết quả |

Khi hoàn thành, bạn cần giải thích được tài nguyên nào được tạo bởi binder, tài nguyên nào được broker tạo theo chính sách riêng, group được thể hiện như thế nào ở từng broker và số liệu nào chứng minh subscriber đã nhận hoặc còn tồn message.

## Kết luận

Quan sát broker là bước kiểm chứng quan trọng sau khi cấu hình binding trong Spring Cloud Stream. Destination cho biết luồng dữ liệu, group xác định phạm vi tiêu thụ độc lập, còn binder quyết định cách các khái niệm đó được ánh xạ thành tài nguyên cụ thể.

Kafka cần được kiểm tra qua topic, partition, consumer group và offset; RabbitMQ qua exchange, queue, binding và message counters; Pulsar qua topic, subscription, consumer và backlog. Khi đối chiếu cấu hình với trạng thái broker, hãy kiểm tra cả vòng đời message và hành vi sau restart để xác nhận ứng dụng đang sử dụng đúng tài nguyên và tiếp tục xử lý theo thiết kế.

