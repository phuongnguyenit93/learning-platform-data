# group.instance.id và thành viên tĩnh

Kafka consumer group cần biết instance nào đang tham gia để phân phối partition. Mặc định, consumer tham gia với danh tính thành viên do giao thức group quản lý; khi process khởi động lại, thành viên mới có thể làm group rebalance và phân phối lại partition.

Static membership cho phép ứng dụng gán một định danh ổn định bằng `group.instance.id`. Khi cùng một logical instance khởi động lại và quay lại group với định danh đó, coordinator có thể nhận diện thành viên cũ và giữ assignment ổn định trong khoảng thời gian chờ đã cấu hình. Cơ chế này hữu ích với service có số replica tương đối ổn định, đặc biệt khi rolling restart thường xuyên và chi phí rebalance cao.

Static membership cần định danh duy nhất, ổn định và được quản lý theo vòng đời instance. Nếu nhiều consumer đang chạy đồng thời dùng chung một `group.instance.id`, chúng có thể fence lẫn nhau và làm group mất ổn định.

## 1. Dynamic membership và static membership

Với dynamic membership, mỗi lần consumer tham gia group, coordinator quản lý một member identity cho phiên tham gia đó. Khi consumer rời group hoặc bị xem là mất kết nối, group có thể rebalance để phân phối partition cho các member còn lại.

Với static membership, ứng dụng cung cấp `group.instance.id` ổn định. Coordinator dùng giá trị này để nhận diện logical instance qua những lần khởi động lại.

| Tiêu chí | Dynamic membership | Static membership |
|---|---|---|
| Định danh thành viên | Do group protocol quản lý cho phiên tham gia | Ứng dụng cung cấp qua `group.instance.id` |
| Khởi động lại ngắn | Có thể tạo member mới và kích hoạt rebalance | Có thể tiếp tục identity/assignment cũ nếu quay lại trước khi hết session timeout |
| Consumer mất kết nối đột ngột | Coordinator phát hiện qua heartbeat/session timeout | Coordinator giữ trạng thái thành viên trong thời gian session timeout trước khi loại bỏ |
| Trùng định danh | Không áp dụng theo cách static identity | Hai instance trong cùng group không được dùng cùng ID |
| Phù hợp | Replica co giãn, danh tính instance thay đổi thường xuyên | Instance có identity ổn định và restart có kiểm soát |
| Đánh đổi | Rebalance có thể xảy ra thường xuyên hơn | Phát hiện instance chết có thể chậm hơn nếu session timeout dài |

Static membership không loại bỏ mọi rebalance. Group vẫn có thể rebalance khi thêm/bớt thành viên, thay đổi subscription, số partition, assignor hoặc các điều kiện giao thức khác.

## 2. group.instance.id là gì?

`group.instance.id` là định danh do ứng dụng cung cấp cho một consumer instance. Khi thuộc tính này được cấu hình, Kafka xem consumer là static member của group.

Ví dụ:

~~~properties
group.id=orders-projection
group.instance.id=orders-projection-0
~~~

Trong đó:

- `group.id` xác định nhóm consumer cùng chia sẻ việc đọc partition.
- `group.instance.id` xác định một instance cụ thể trong nhóm đó.
- `client.id` chỉ là nhãn nhận diện client trong log và metric; nó không thay thế static member identity.

Một group có thể có nhiều static member:

| group.id | group.instance.id | Vai trò |
|---|---|---|
| orders-projection | orders-projection-0 | Consumer replica 0 |
| orders-projection | orders-projection-1 | Consumer replica 1 |
| orders-projection | orders-projection-2 | Consumer replica 2 |

Các giá trị `group.instance.id` phải duy nhất trong cùng một group tại một thời điểm. Không đặt cùng một giá trị cho mọi replica chỉ vì chúng chạy cùng một service.

Một giá trị có thể được dùng lại ở group khác vì namespace thành viên gắn với group. Tuy vậy, nên đặt tên có cấu trúc để dễ vận hành và tránh nhầm lẫn.

## 3. Static membership giữ assignment qua restart như thế nào?

Giả sử group `orders-projection` có ba static member:

- `orders-projection-0` đọc partition 0 và 1.
- `orders-projection-1` đọc partition 2 và 3.
- `orders-projection-2` đọc partition 4 và 5.

Khi instance 1 khởi động lại trong thời gian ngắn:

1. Process cũ ngừng heartbeat hoặc rời group.
2. Coordinator giữ trạng thái static member trong thời gian session timeout.
3. Process mới khởi động với cùng `group.instance.id=orders-projection-1`.
4. Coordinator nhận diện đây là cùng logical member.
5. Nếu member quay lại đúng hạn và các điều kiện group không thay đổi, group có thể tiếp tục với assignment cũ mà không cần rebalance toàn group.

Sơ đồ minh họa:

~~~mermaid
sequenceDiagram
    participant Old as Consumer instance 1 (cũ)
    participant Coord as Group coordinator
    participant New as Consumer instance 1 (mới)

    Old->>Coord: Join group với instance ID orders-projection-1
    Coord-->>Old: Assignment partition 2, 3
    Note over Old: Process restart ngắn
    Old--xCoord: Heartbeat tạm ngừng
    Note over Coord: Giữ static member đến session timeout
    New->>Coord: Rejoin với cùng instance ID
    Coord-->>New: Tiếp tục membership/assignment
~~~

Điều kiện quan trọng là instance quay lại trước khi coordinator hết thời gian chờ và loại member. Nếu thời gian ngừng vượt quá `session.timeout.ms`, coordinator có thể loại member và phân phối lại partition. Khi instance cũ quay lại sau đó, group có thể phải rebalance lần nữa.

Static membership giúp tránh rebalance do gián đoạn ngắn. Nó không giữ partition vô thời hạn cho một process đã chết.

## 4. Chọn group.instance.id ổn định và duy nhất

Giá trị `group.instance.id` cần có hai thuộc tính:

- **Ổn định qua restart:** cùng một logical instance phải dùng lại cùng giá trị.
- **Duy nhất trong group:** hai consumer đang hoạt động không được dùng cùng giá trị.

Các mẫu định danh phù hợp:

| Nền tảng triển khai | Cách tạo ID gợi ý | Lưu ý |
|---|---|---|
| Kubernetes StatefulSet | Tên workload cộng ordinal, ví dụ `orders-projection-0` | Ordinal được giữ khi pod được tạo lại |
| VM cố định | Tên node hoặc instance ID ổn định | Không lấy hostname tạm thời nếu hostname thay đổi sau restart |
| Service chạy trên máy cố định | ID cấu hình riêng cho từng process | Lưu trong cấu hình triển khai |
| Container có identity ổn định | Logical slot hoặc task identity do orchestrator cấp | Phải bảo đảm task cũ đã dừng trước khi slot được dùng lại |

Không nên dùng:

- UUID tạo mới mỗi lần process khởi động, vì mỗi lần restart sẽ trở thành một static member khác.
- Một hằng số giống nhau cho tất cả replica.
- `client.id` dùng chung làm `group.instance.id` mà không kiểm tra uniqueness.
- PID của hệ điều hành, vì PID có thể thay đổi sau restart hoặc bị tái sử dụng.
- Tên pod ngẫu nhiên của Deployment nếu mục tiêu là giữ identity qua lần thay thế pod.

Ví dụ với ba replica StatefulSet:

~~~text
orders-projection-0
orders-projection-1
orders-projection-2
~~~

Khi pod `orders-projection-1` được tạo lại, nó tiếp tục dùng `orders-projection-1`. Pod khác không được nhận ID đó trong khi instance cũ vẫn có thể hoạt động.

## 5. Cấu hình KafkaConsumer bằng Java

Khai báo `group.instance.id` qua `ConsumerConfig.GROUP_INSTANCE_ID_CONFIG`.

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Properties;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;

public class StaticOrderConsumer {

    public static void main(String[] args) {
        Properties props = new Properties();

        props.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        props.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "orders-projection"
        );
        props.put(
            ConsumerConfig.GROUP_INSTANCE_ID_CONFIG,
            "orders-projection-0"
        );
        props.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class.getName()
        );
        props.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class.getName()
        );
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        props.put(ConsumerConfig.SESSION_TIMEOUT_MS_CONFIG, 45000);
        props.put(ConsumerConfig.HEARTBEAT_INTERVAL_MS_CONFIG, 15000);
        props.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 300000);

        try (KafkaConsumer<String, String> consumer =
                 new KafkaConsumer<>(props)) {

            consumer.subscribe(List.of("orders"));

            while (true) {
                var records = consumer.poll(Duration.ofMillis(500));

                for (var record : records) {
                    processOrder(record.key(), record.value());
                }

                if (!records.isEmpty()) {
                    consumer.commitSync();
                }
            }
        }
    }

    private static void processOrder(String key, String value) {
        // Xử lý nghiệp vụ.
    }
}
~~~

Các giá trị timeout trong ví dụ chỉ để minh họa. Cần điều chỉnh theo thời gian xử lý, mục tiêu phát hiện lỗi, cấu hình broker và phiên bản consumer group protocol đang dùng.

Trong môi trường triển khai nhiều replica, giá trị `orders-projection-0` phải được truyền từ cấu hình riêng của từng instance. Không copy nguyên cấu hình này cho tất cả replica.

## 6. Session timeout và max.poll.interval.ms

Static membership phụ thuộc vào cách coordinator phát hiện thành viên không còn hoạt động. Hai timeout thường bị nhầm là một:

| Thuộc tính | Ý nghĩa |
|---|---|
| `session.timeout.ms` | Thời gian coordinator chờ heartbeat trước khi xem member mất kết nối |
| `heartbeat.interval.ms` | Chu kỳ heartbeat trong classic group protocol |
| `max.poll.interval.ms` | Giới hạn thời gian giữa hai lần poll để phát hiện consumer không tiến triển xử lý |

### 6.1. Session timeout

Khi static member tạm thời mất heartbeat, coordinator giữ membership trong khoảng session timeout để instance có cơ hội quay lại với cùng identity.

Tăng session timeout có thể giúp một instance chịu được thời gian restart dài hơn mà ít gây rebalance. Tuy nhiên, nếu instance thực sự chết, group cũng phải chờ lâu hơn trước khi giải phóng partition và giao cho member khác.

Chọn timeout theo hai đại lượng:

- Thời gian restart hoặc gián đoạn dự kiến trong vận hành.
- Thời gian tối đa nghiệp vụ có thể chấp nhận partition không được xử lý khi member chết.

Không đặt timeout quá dài chỉ để tránh rebalance. Việc đó có thể làm consumer group thiếu năng lực xử lý trong thời gian dài khi một replica đã mất thật sự.

### 6.2. Heartbeat interval

Trong classic group protocol, `heartbeat.interval.ms` thường được đặt thấp hơn đáng kể so với `session.timeout.ms`; một quy tắc cấu hình phổ biến là khoảng một phần ba session timeout. Cần tuân thủ giới hạn và khuyến nghị của broker/client đang dùng.

Với consumer group protocol mới, một số tham số heartbeat/session được broker quản lý thay vì dùng cấu hình client truyền thống. Hãy kiểm tra `group.protocol` và tài liệu của đúng phiên bản trước khi áp dụng các con số trong ví dụ.

### 6.3. Max poll interval

`max.poll.interval.ms` giới hạn khoảng thời gian giữa các lần `poll()`. Nếu ứng dụng xử lý một batch quá lâu, consumer có thể bị xem là không còn tiến triển.

Với static member, khi vượt quá max poll interval, consumer ngừng heartbeat; việc phân phối lại partition có thể chờ đến khi session timeout hết thay vì xảy ra ngay lập tức như một số trường hợp dynamic membership. Điều này giảm rebalance đột ngột nhưng có thể kéo dài thời gian partition bị giữ bởi một consumer không xử lý được.

Để tránh tình trạng này:

- Đặt `max.poll.records` phù hợp với thời gian xử lý mỗi batch.
- Đặt timeout cho database/API được gọi trong handler.
- Đo thời gian xử lý batch p95/p99.
- Không dùng static membership để che giấu consumer bị treo hoặc xử lý quá chậm.

## 7. Điều gì xảy ra nếu hai consumer dùng cùng group.instance.id?

`group.instance.id` đại diện cho một logical member duy nhất trong một group. Nếu hai process cùng hoạt động và cùng khai báo một ID, coordinator không thể xem chúng là hai static member độc lập.

Tình huống có thể xuất hiện khi:

- Deployment scale nhiều replica nhưng mọi pod dùng chung một environment variable.
- Pod mới khởi động trước khi pod cũ cùng identity dừng hoàn toàn.
- Hai VM vô tình copy cùng file cấu hình.
- Một process cũ bị mất kết nối mạng nhưng vẫn tiếp tục chạy, trong khi process thay thế khởi động với cùng ID.

Kafka có thể fence một member và trả lỗi như `FencedInstanceIdException`. Member bị fence không thể tiếp tục hoạt động như static member hợp lệ. Việc hai process liên tục thay thế hoặc fence nhau có thể làm group chập chờn.

Cách phòng tránh:

1. Cấp ID duy nhất cho từng replica trong cùng group.
2. Dùng identity ổn định qua restart, không dùng một ID chung cho cả deployment.
3. Bảo đảm orchestrator không chạy đồng thời hai process cho cùng logical slot ngoài kế hoạch.
4. Theo dõi log và metric liên quan đến fencing.
5. Khi gặp `FencedInstanceIdException`, kiểm tra duplicate ID và trạng thái process cũ trước khi restart hàng loạt.

Không xử lý fencing bằng cách tự động sinh ID ngẫu nhiên mỗi lần lỗi. Làm như vậy có thể che mất lỗi cấu hình và biến static member thành dynamic member ngoài ý muốn.

## 8. Static membership và graceful shutdown

Static membership hữu ích nhất khi process gián đoạn ngắn rồi quay lại. Cách xử lý khi dừng có chủ đích khác với khi process chết đột ngột.

Khi consumer đóng sạch, Kafka client có thể gửi yêu cầu rời group để coordinator giải phóng membership và rebalance sớm. Khi process chết, máy bị mất điện hoặc mạng bị phân vùng, coordinator không nhận được yêu cầu rời group và phải dựa vào session timeout để phát hiện member mất tích.

Điều này dẫn đến hai trường hợp:

| Trường hợp | Hành vi mong đợi |
|---|---|
| Rolling restart có kiểm soát | Consumer đóng sạch; group có thể rebalance theo yêu cầu rời group và instance mới tham gia |
| Restart ngắn do lỗi process/network | Coordinator giữ static member trong thời gian chờ; instance cùng ID quay lại có thể tiếp tục assignment |
| Process chết hẳn | Sau session timeout, coordinator loại member và phân phối partition |
| Hai instance cùng ID cùng chạy | Một instance có thể bị fence; cần sửa identity/lifecycle |

Hành vi cụ thể của LeaveGroup và group protocol phụ thuộc phiên bản client/broker. Hãy kiểm tra log trong môi trường thực tế để xác nhận cách phiên bản đang dùng xử lý static member khi close.

Nếu mục tiêu là giữ assignment qua rolling restart, hãy phối hợp thời gian dừng, khởi động và session timeout. Nếu mục tiêu là chuyển partition ngay cho replica còn lại khi một instance chủ động dừng, hãy kiểm tra rằng quá trình close rời group đúng cách và không kéo dài shutdown bằng việc chờ timeout không cần thiết.

## 9. Static membership khác gì cooperative rebalancing?

Hai cơ chế này thường được dùng cùng nhau nhưng giải quyết hai vấn đề khác nhau.

- **Static membership** giữ identity của consumer qua restart để tránh rebalance do thay đổi thành viên tạm thời.
- **Cooperative rebalancing** thay đổi assignment theo từng phần, giúp giảm việc thu hồi toàn bộ partition trong một lần rebalance.

Ví dụ `CooperativeStickyAssignor` cố gắng giữ assignment ổn định và chỉ chuyển những partition cần thay đổi. Static membership giúp coordinator nhận diện lại cùng member sau restart.

| Cơ chế | Giảm vấn đề nào? | Không giải quyết điều gì? |
|---|---|---|
| `group.instance.id` | Rebalance do member tạm thời biến mất rồi quay lại | Không loại bỏ rebalance khi topology hoặc subscription thay đổi |
| Cooperative assignor | Giảm phạm vi partition phải thu hồi trong rebalance | Không ngăn rebalance phát sinh |
| Kết hợp cả hai | Giảm tần suất và mức gián đoạn trong nhiều tình huống | Không bảo đảm tuyệt đối không rebalance hoặc exactly-once |

Cần chọn assignor tương thích với phiên bản Kafka và chiến lược triển khai. Không thay đổi assignor đồng loạt mà không kiểm tra tác động tới các consumer đang chạy.

## 10. Khi nào nên và không nên dùng static membership?

### Nên cân nhắc

- Consumer service có số replica ổn định.
- Các instance có identity bền vững, chẳng hạn StatefulSet ordinal.
- Rolling restart thường xuyên gây rebalance và làm gián đoạn xử lý.
- Việc khởi động lại một replica thường ngắn hơn thời gian session timeout.
- Hệ thống có thể bảo đảm mỗi static ID chỉ có một instance hoạt động.

### Không nên dùng hoặc cần cân nhắc kỹ

- Replica được scale up/down liên tục và identity thay đổi ngẫu nhiên.
- Các instance không thể bảo đảm ID duy nhất.
- Consumer thường xuyên bị treo hoặc mất kết nối lâu.
- Nghiệp vụ cần partition được giao lại ngay khi instance mất heartbeat.
- Orchestrator có thể chạy hai process cùng logical identity trong thời gian dài.
- Team chưa có giám sát session timeout, fencing và rebalance.

Static membership là tối ưu hóa cho vòng đời instance có identity ổn định. Nó không phải lựa chọn mặc định cho mọi consumer group.

## 11. Cấu hình trong Spring Kafka

Spring Kafka sử dụng Kafka consumer bên dưới, vì vậy có thể cấu hình thuộc tính client `group.instance.id` thông qua consumer properties.

Ví dụ cấu hình Spring Boot theo dạng properties:

~~~properties
spring.kafka.consumer.group-id=orders-projection
spring.kafka.consumer.properties[group.instance.id]=orders-projection-0
spring.kafka.consumer.properties[session.timeout.ms]=45000
spring.kafka.consumer.properties[heartbeat.interval.ms]=15000
~~~

Với nhiều replica, giá trị `group.instance.id` phải được cấp riêng cho từng instance từ môi trường triển khai. Không để mọi pod nhận cùng giá trị trong file cấu hình dùng chung.

Nếu listener container có `concurrency` lớn hơn 1, một container có thể tạo nhiều consumer instance. Mỗi consumer cần static identity riêng trong group. Một số phiên bản Spring Kafka có cơ chế thêm hậu tố cho các child container; hãy xác minh behavior của phiên bản đang dùng và kiểm tra log member identity để tránh trùng ID.

Không nên tự thêm hậu tố theo phỏng đoán nếu framework đã quản lý nó, và cũng không nên giả định framework tự xử lý trong mọi phiên bản. Kiểm tra cấu hình runtime là cách xác nhận đáng tin cậy.

## 12. Quan sát static member trong vận hành

Khi điều tra rebalance hoặc fencing, cần theo dõi cả identity và thời gian:

- Group ID.
- Group instance ID.
- Member ID do coordinator quản lý.
- Consumer client ID.
- Thời điểm heartbeat cuối cùng.
- Session timeout và max poll interval.
- Số lần rebalance.
- Số lần consumer bị fence.
- Partition assignment trước và sau restart.
- Consumer lag theo partition.

Có thể xem trạng thái group bằng CLI:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-projection
~~~

Tùy phiên bản CLI, output có thể hiển thị member ID, host, client ID và assignment; không phải phiên bản nào cũng hiển thị trực tiếp `group.instance.id` trong cùng bảng. Khi cần đối chiếu static identity, kết hợp log consumer, log coordinator và công cụ quản trị phù hợp phiên bản.

### 12.1. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `FencedInstanceIdException` | Hai process dùng cùng static ID hoặc member cũ bị thay thế | Tìm tất cả process trong group và xác minh identity |
| Rebalance vẫn xảy ra sau restart | Instance quay lại sau session timeout hoặc có thay đổi group khác | Đối chiếu thời gian restart, timeout, subscription và partition count |
| Partition bị giữ lâu khi consumer chết | Session timeout quá dài | Điều chỉnh timeout theo mục tiêu phát hiện lỗi |
| Nhiều consumer liên tục bị fence | ID dùng chung hoặc orchestrator chạy overlap | Cấp identity duy nhất và kiểm soát rollout |
| Static member không xử lý dù process còn sống | Poll loop bị treo hoặc vượt max poll interval | Kiểm tra thời gian xử lý batch, heartbeat và downstream |
| Spring listener có lỗi duplicate identity | Nhiều child consumer dùng chung ID | Kiểm tra concurrency và cách phiên bản Spring Kafka tạo ID |

## 13. Quy trình triển khai static membership

Có thể triển khai theo trình tự sau:

1. Xác định group nào có lợi từ việc giữ assignment qua restart.
2. Xác định logical replica và nguồn tạo identity ổn định.
3. Đảm bảo mỗi replica có một `group.instance.id` riêng trong group.
4. Cấu hình `group.id`, static ID và timeout phù hợp với phiên bản Kafka.
5. Kiểm tra `max.poll.interval.ms` so với thời gian xử lý batch.
6. Triển khai thử một replica và xác minh member identity trong log.
7. Restart replica trong khoảng thời gian nhỏ hơn session timeout.
8. Quan sát rebalance count và partition assignment trước/sau restart.
9. Thử dừng process đột ngột và đo thời gian coordinator giải phóng partition.
10. Thử tình huống duplicate ID trong môi trường test để xác nhận cảnh báo/fencing.
11. Mở rộng rollout sang các replica còn lại sau khi đã xác minh identity.
12. Đưa metric về rebalance, lag, fencing và session timeout vào dashboard.

Không nên thay đổi identity của toàn bộ consumer group cùng lúc mà không có kế hoạch. Nếu tất cả static member đổi ID, coordinator có thể xem chúng là thành viên mới và group sẽ phải phân phối lại partition.

## 14. Checklist cấu hình group.instance.id

- [ ] Đã xác định group nào thực sự cần static membership.
- [ ] Mỗi instance có `group.instance.id` duy nhất trong cùng group.
- [ ] ID ổn định qua restart của cùng logical instance.
- [ ] Không dùng UUID mới cho mỗi lần khởi động nếu muốn giữ membership.
- [ ] Không dùng một ID chung cho tất cả replica.
- [ ] Session timeout cân bằng giữa thời gian restart và thời gian phát hiện lỗi.
- [ ] `max.poll.interval.ms` phù hợp với thời gian xử lý batch.
- [ ] Đã hiểu hành vi graceful close và mất kết nối đột ngột.
- [ ] Đã kiểm tra fencing khi có duplicate identity.
- [ ] Đã xem xét tương thích Kafka client, broker và group protocol.
- [ ] Với Spring concurrency, mỗi child consumer có identity phù hợp.
- [ ] Theo dõi rebalance, lag, fencing và member identity.
- [ ] Đã kiểm thử restart ngắn, crash và rollout thực tế.

`group.instance.id` cho Kafka biết một consumer đang quay lại có phải cùng logical instance hay không. Khi identity ổn định và duy nhất, static membership có thể giảm rebalance do restart ngắn và giữ assignment ổn định hơn. Đổi lại, coordinator có thể phải chờ session timeout trước khi thu hồi partition của một member mất tích. Hãy chọn static membership khi vòng đời replica có thể quản lý được, đặt timeout theo mục tiêu vận hành và theo dõi fencing để bảo đảm mỗi identity chỉ thuộc về một consumer đang hoạt động trong group.
