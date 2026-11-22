# Đặt group.id cho từng use case

Trong Kafka, **group.id** xác định consumer group mà một consumer tham gia. Group ID quyết định consumer chia sẻ partition với những consumer nào và Kafka lưu tiến độ đọc (offset) cho nhóm nào. Vì vậy, lựa chọn group.id là quyết định về cách một use case tiêu thụ sự kiện, không đơn thuần là đặt tên cho một instance ứng dụng.

Nếu nhiều replica của cùng một chức năng cần chia nhau xử lý tải, chúng thường dùng chung group.id. Nếu nhiều hệ thống cần nhận độc lập toàn bộ sự kiện từ một topic, mỗi hệ thống cần group.id riêng để có offset và tiến độ đọc độc lập. Đặt nhầm group.id có thể khiến các consumer vô tình chia nhau record, hoặc cùng xử lý lại toàn bộ luồng sự kiện và tạo tác động nghiệp vụ trùng.

Bài học thuộc chương **Consumer group** của module **SPRING_KAFKA_MESSAGING**, tập trung vào cách đặt group.id theo use case, cách Spring Kafka cấu hình group cho listener, và cách quản lý tiến độ đọc khi triển khai nhiều replica, nhiều ứng dụng hoặc cần replay dữ liệu.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích group.id liên kết consumer với membership và offset như thế nào.
- Phân biệt nhiều replica cùng use case với nhiều use case tiêu thụ độc lập.
- Chọn group.id phù hợp cho xử lý đơn hàng, analytics, audit và các consumer khác.
- Cấu hình group mặc định trong Spring Boot và ghi đè group cho từng @KafkaListener.
- Hiểu ảnh hưởng của thay đổi group.id tới offset, replay và tác động nghiệp vụ.
- Tách group theo môi trường khi nhiều môi trường dùng chung Kafka cluster.
- Thiết kế group ID ổn định, dễ quan sát và tránh xung đột.
- Lập kế hoạch blue-green, shadow consumer và migration group an toàn.

## 1. group.id là định danh của một consumer group

Kafka dùng group.id để xác định tập consumer phối hợp đọc dữ liệu. Các consumer có cùng group.id tham gia cùng một nhóm logic. Kafka group coordinator quản lý membership, phân phối partition và phối hợp việc lưu offset cho nhóm.

Offset được lưu theo group, topic và partition. Có thể hình dung tiến độ đọc là một tập hợp các vị trí, mỗi vị trí gắn với một partition trong một group cụ thể. Khi consumer commit offset, tiến độ đó thuộc group.id đang sử dụng.

Ví dụ một topic orders.created có ba partition:

~~~mermaid
flowchart LR
    T[Topic: orders.created] --> P0[Partition 0]
    T --> P1[Partition 1]
    T --> P2[Partition 2]
    subgraph G1["Group: orders-fulfillment"]
        C1[Consumer A]
        C2[Consumer B]
    end
    P0 --> C1
    P1 --> C1
    P2 --> C2
    subgraph G2["Group: orders-analytics"]
        A1[Analytics consumer]
    end
    P0 --> A1
    P1 --> A1
    P2 --> A1
~~~

Trong ví dụ:

- orders-fulfillment là một group, các consumer member chia nhau ba partition.
- orders-analytics là group khác, có tiến độ đọc riêng và có thể đọc toàn bộ record của topic.
- Hai group không chia sẻ offset với nhau. Việc group fulfillment commit offset không làm analytics bị bỏ qua record.

Việc một group mới có đọc lại toàn bộ lịch sử đang được giữ hay chỉ đọc record mới phụ thuộc offset đã có và auto.offset.reset. Group độc lập có tiến độ riêng, nhưng điểm bắt đầu của từng group vẫn phải được cấu hình có chủ đích.

Đây là điểm cốt lõi khi thiết kế group.id: cùng group để chia tải của một luồng xử lý; group khác nhau để tiêu thụ độc lập.

## 2. Dùng chung group.id cho các replica của cùng use case

Giả sử dịch vụ fulfillment có ba replica chạy cùng một chức năng xử lý OrderCreatedEvent. Cả ba replica nên dùng cùng group.id, ví dụ orders-fulfillment.

Kafka sẽ phân phối các partition của topic cho các consumer member trong group. Mỗi record được giao cho một member theo assignment hiện tại, giúp các replica chia nhau tải xử lý.

~~~mermaid
flowchart TB
    T[orders.created: 6 partitions]
    T --> P[Partition assignment]
    P --> C1[fulfillment instance 1]
    P --> C2[fulfillment instance 2]
    P --> C3[fulfillment instance 3]
    C1 -.-> G["Shared group.id: orders-fulfillment"]
    C2 -.-> G
    C3 -.-> G
~~~

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-fulfillment
      enable-auto-commit: false
~~~

Các replica của cùng deployment nhận cùng cấu hình. Khi một replica dừng, Kafka có thể rebalance và giao partition của replica đó cho member còn lại. Khi replica mới tham gia, group lại phân phối partition.

Việc một partition chỉ được gán cho một member tại một thời điểm không đồng nghĩa xử lý exactly-once. Nếu consumer đã xử lý record nhưng dừng trước khi offset được commit, record có thể được giao lại sau rebalance. Logic nghiệp vụ nên có khả năng xử lý lặp an toàn, chẳng hạn dùng eventId làm khóa idempotency.

Không đặt group.id chứa hostname, pod name, UUID hoặc instance ID nếu mục tiêu là các replica chia tải. Nếu mỗi replica có một group.id riêng, mỗi replica sẽ trở thành một group độc lập và có thể nhận toàn bộ record của topic, gây nhân bản xử lý.

## 3. Dùng group.id riêng cho từng use case độc lập

Một topic có thể cung cấp sự kiện cho nhiều chức năng nghiệp vụ. Ví dụ, OrderCreatedEvent được dùng bởi fulfillment để giữ hàng, analytics để tổng hợp số liệu và audit để lưu dấu hoạt động.

Nếu mỗi use case cần nhận toàn bộ record độc lập, mỗi use case cần một group.id riêng:

| Use case | Group ID gợi ý | Mục đích |
|---|---|---|
| Fulfillment | orders-fulfillment | Xử lý giữ hàng và điều phối đơn hàng. |
| Analytics | orders-analytics | Tổng hợp số liệu và tạo báo cáo. |
| Audit | orders-audit | Lưu dấu sự kiện phục vụ truy vết. |
| Notification | orders-notification | Gửi thông báo theo sự kiện đơn hàng. |

Các consumer trong cùng một group chia partition với nhau. Các group khác nhau có thể cùng đọc toàn bộ luồng topic, mỗi group có offset riêng.

Ví dụ hai listener thuộc hai use case độc lập:

~~~java
@Component
public class OrderAnalyticsListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-analytics"
    )
    public void onOrderCreated(OrderCreatedEvent event) {
        // Cập nhật dữ liệu phân tích.
    }
}
~~~

~~~java
@Component
public class OrderAuditListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-audit"
    )
    public void onOrderCreated(OrderCreatedEvent event) {
        // Lưu dấu vết kiểm toán.
    }
}
~~~

Hai listener trên có group ID khác nhau nên mỗi use case có tiến độ đọc riêng. Nếu audit tạm dừng, analytics vẫn tiếp tục đọc và commit offset của group analytics.

Đừng tạo group riêng cho từng phương thức hoặc từng request nếu các consumer thực chất là replica của cùng một use case. Hãy đặt group ở ranh giới tiến độ đọc và trách nhiệm xử lý mà bạn muốn quản lý độc lập.

## 4. Cùng topic nhưng khác group và cùng group có gì khác?

Hai cách tổ chức này có hành vi rất khác nhau:

| Cách tổ chức | Cách Kafka phân phối record | Khi nên dùng |
|---|---|---|
| Nhiều consumer cùng group.id | Các consumer chia nhau partition; một partition chỉ được gán cho một member tại một thời điểm | Nhiều replica cùng thực hiện một use case để chia tải. |
| Nhiều consumer khác group.id | Mỗi group duy trì offset riêng và tiêu thụ độc lập; điểm bắt đầu phụ thuộc offset và auto.offset.reset | Nhiều use case cần nhận cùng một sự kiện. |

Ví dụ, ba instance fulfillment cùng group orders-fulfillment giúp chia tải xử lý. Một analytics consumer dùng group orders-analytics vẫn đọc được các record đó theo tiến độ riêng. Việc nhận cả lịch sử đang được giữ hay chỉ record mới phụ thuộc cấu hình offset ban đầu của group analytics.

Một lỗi cấu hình phổ biến là dùng cùng group.id cho analytics và fulfillment chỉ vì hai listener cùng đọc orders.created. Khi đó hai chức năng có thể chia nhau partition và mỗi chức năng chỉ nhận một phần sự kiện. Kết quả là analytics có thể bỏ lỡ các đơn hàng mà fulfillment đã nhận, hoặc ngược lại.

Ngược lại, nếu ba replica fulfillment vô tình dùng ba group ID khác nhau, mỗi replica có thể nhận toàn bộ đơn hàng và thực hiện giữ hàng ba lần. Đây là lỗi có thể gây tác động nghiệp vụ nghiêm trọng.

## 5. Cấu hình group mặc định trong Spring Boot

Spring Boot cho phép khai báo group ID mặc định qua spring.kafka.consumer.group-id:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-fulfillment
      auto-offset-reset: earliest
      enable-auto-commit: false
~~~

Các listener không khai báo group riêng có thể sử dụng group ID từ cấu hình consumer factory. Cách này phù hợp khi ứng dụng chủ yếu có một use case tiêu thụ sự kiện.

Khi ứng dụng có nhiều listener thuộc các use case khác nhau, nên cấu hình group rõ ràng tại từng listener bằng groupId. Điều này làm rõ ý định và tránh việc các listener vô tình dùng chung group mặc định.

Ví dụ cấu hình mặc định cho fulfillment nhưng listener analytics dùng group riêng:

~~~java
@Component
public class OrderListeners {

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-fulfillment"
    )
    public void fulfill(OrderCreatedEvent event) {
        // Xử lý đơn hàng.
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-analytics"
    )
    public void analyze(OrderCreatedEvent event) {
        // Phân tích sự kiện.
    }
}
~~~

Trong ví dụ này, groupId trên @KafkaListener chỉ định group cho listener tương ứng và ghi đè group mặc định từ consumer factory. Hãy kiểm tra cấu hình thực tế của từng listener khi ứng dụng có nhiều container.

## 6. Đặt tên group.id theo use case

Group ID nên ổn định, có ý nghĩa và phản ánh trách nhiệm xử lý. Một quy ước đơn giản:

~~~text
<domain>-<use-case>-<environment>
~~~

Ví dụ:

~~~text
orders-fulfillment-prod
orders-analytics-prod
orders-audit-prod
payments-reconciliation-staging
inventory-reservation-dev
~~~

Các thành phần có ý nghĩa:

- **domain:** miền nghiệp vụ hoặc loại dữ liệu, ví dụ orders, payments, inventory.
- **use-case:** chức năng tiêu thụ, ví dụ fulfillment, analytics, audit, reconciliation.
- **environment:** môi trường triển khai khi các môi trường có thể dùng chung cluster hoặc cần tách tiến độ.

Một số nguyên tắc:

- Dùng tên ổn định qua các lần restart và scale replica.
- Tránh gắn pod name, hostname hoặc UUID vào group ID của consumer chia tải.
- Đặt group ID khác nhau cho các use case có tiến độ và trách nhiệm độc lập.
- Chỉ thêm version suffix khi thực sự muốn tạo một tiến độ đọc mới hoặc chạy song song một consumer contract mới.
- Giữ quy ước nhất quán để dễ tra cứu group lag, offset và membership.
- Không đưa thông tin bí mật hoặc dữ liệu cá nhân vào group ID.

Không có một mẫu tên bắt buộc cho mọi hệ thống. Điều quan trọng là group ID phải thể hiện được ranh giới xử lý và được quản lý như một phần cấu hình vận hành.

## 7. Tách group.id theo môi trường

Nếu development, staging và production kết nối tới cùng một Kafka cluster, không nên để tất cả consumer dùng cùng group ID. Nếu dùng chung group, consumer ở môi trường này có thể nhận partition thay cho consumer ở môi trường khác và làm thay đổi tiến độ đọc chung.

Ví dụ:

| Môi trường | Group ID |
|---|---|
| Local | orders-fulfillment-local |
| Development | orders-fulfillment-dev |
| Staging | orders-fulfillment-staging |
| Production | orders-fulfillment-prod |

Nếu mỗi môi trường có Kafka cluster riêng, việc thêm tên môi trường vào group ID vẫn có thể hữu ích cho tính nhất quán và khả năng quan sát, dù group namespace đã được tách bởi cluster.

Ví dụ dùng Spring profile:

~~~yaml
# application-local.yml
spring:
  kafka:
    consumer:
      group-id: orders-fulfillment-local
~~~

~~~yaml
# application-prod.yml
spring:
  kafka:
    consumer:
      group-id: orders-fulfillment-prod
~~~

Khi chạy ứng dụng, hãy xác nhận profile đang hoạt động và group ID hiệu lực. Một cấu hình local trỏ nhầm cluster production có thể tạo consumer group ngoài ý muốn và ảnh hưởng dữ liệu thật.

## 8. Đổi group.id có thể làm thay đổi vị trí bắt đầu đọc

Offset được lưu riêng theo group. Khi đổi group.id, consumer tham gia một group khác và không sử dụng offset đã commit của group cũ.

Nếu group mới chưa có offset hợp lệ, thuộc tính auto.offset.reset quyết định vị trí bắt đầu:

- **earliest:** bắt đầu từ offset sớm nhất còn được giữ trong log.
- **latest:** bắt đầu từ các record mới khi consumer bắt đầu đọc.
- **none:** ném lỗi nếu không tìm thấy offset hợp lệ theo cấu hình client.

auto.offset.reset chỉ có hiệu lực khi group không có offset hợp lệ. Nó không ghi đè offset đã commit của group hiện tại và không phải công cụ để tua lại dữ liệu mỗi lần restart.

Ví dụ group cũ:

~~~text
orders-fulfillment
partition 0 committed offset = 120
partition 1 committed offset = 95
~~~

Nếu đổi group ID thành orders-fulfillment-v2, group mới chưa có offset riêng. Với auto.offset.reset=earliest, nó có thể bắt đầu từ offset sớm nhất còn được giữ. Các record đã xử lý trước đây có thể được đọc lại, dẫn tới tác động nghiệp vụ trùng nếu consumer không idempotent.

Đổi group ID không xóa offset của group cũ. Offset cũ vẫn tồn tại theo chính sách lưu trữ offset của Kafka cho tới khi hết hạn hoặc bị xóa theo quy trình quản trị.

Trước khi đổi group ID, cần xác định rõ mục tiêu là tạo tiến độ mới, replay dữ liệu hay chỉ đổi tên. Nếu chỉ đổi tên mà muốn tiếp tục từ offset cũ, cần có kế hoạch chuyển offset phù hợp và kiểm tra cẩn thận trước khi triển khai.

## 9. Dùng group riêng để replay hoặc chạy shadow consumer

Một group ID riêng có thể hữu ích khi cần đọc lại dữ liệu hoặc thử nghiệm logic consumer mới mà không làm thay đổi tiến độ của group production hiện tại.

Ví dụ group replay:

~~~text
orders-fulfillment-replay-2026-11
~~~

Với group mới và auto.offset.reset=earliest, consumer có thể đọc lại các record còn được giữ trong topic. Đây là cách hữu ích để tái tạo dữ liệu phân tích hoặc xác minh một phiên bản xử lý mới.

Tuy nhiên, replay có thể gọi lại các tác động bên ngoài như giữ hàng, trừ tiền hoặc gửi thông báo. Trước khi replay, cần:

1. Xác định khoảng dữ liệu và topic cần đọc.
2. Dùng group ID riêng để không ảnh hưởng offset production.
3. Xác định auto.offset.reset và chính sách seek/offset cụ thể.
4. Kiểm soát các tác động nghiệp vụ; ưu tiên môi trường hoặc output riêng nếu chỉ kiểm chứng.
5. Bảo đảm consumer có idempotency nếu có khả năng xử lý lại event.
6. Theo dõi lag và tốc độ replay để không gây tải đột biến lên downstream.
7. Ghi nhận kết quả và dừng group replay khi hoàn thành.

Với shadow consumer, group mới đọc cùng luồng nhưng chỉ quan sát hoặc ghi kết quả sang nơi thử nghiệm. Không để shadow consumer gọi tác động nghiệp vụ production nếu chưa có thiết kế chống trùng và phê duyệt triển khai.

## 10. Blue-green deployment và migration group

Khi triển khai phiên bản mới, cần quyết định consumer mới sẽ tham gia group cũ hay group mới.

**Dùng cùng group ID:** phiên bản cũ và mới cùng chia partition. Đây là lựa chọn thường gặp khi muốn rolling deployment và tiếp tục một tiến độ đọc chung. Tuy nhiên, hai phiên bản phải tương thích về schema, xử lý sự kiện và cách commit offset. Khi cả hai phiên bản cùng chạy, partition có thể được phân phối giữa chúng.

**Dùng group ID mới:** phiên bản mới tạo tiến độ đọc độc lập và có thể đọc lại dữ liệu theo auto.offset.reset. Cách này hữu ích cho shadow testing hoặc migration cần đối chiếu, nhưng có nguy cơ xử lý lại toàn bộ dữ liệu và tạo side effect.

Một kế hoạch migration nên xác định:

- Phiên bản mới có tương thích event schema với producer hiện tại không.
- Có chạy song song hai group trong thời gian chuyển đổi không.
- Offset của group mới bắt đầu từ đâu.
- Consumer mới có được phép tạo side effect production không.
- Khi nào dừng group cũ và cách quay lui nếu phát hiện lỗi.
- Cách giám sát lag, lỗi và chênh lệch kết quả giữa hai phiên bản.

Không thêm hậu tố v2 vào group ID chỉ vì tên ứng dụng hoặc phiên bản phần mềm thay đổi. Hãy dùng group ID mới khi thật sự cần một tiến độ đọc độc lập.

## 11. group.id khác client.id và listener id như thế nào?

Các ID trong Kafka/Spring Kafka có vai trò khác nhau:

| ID | Vai trò |
|---|---|
| group.id | Xác định consumer group và không gian offset của group. |
| client.id | Nhận diện client để hỗ trợ log, metric và quota ở phía Kafka. |
| member.id | Định danh một member trong consumer group do Kafka quản lý. |
| @KafkaListener id | Định danh listener container trong ứng dụng Spring Kafka. |

Không dùng client.id thay cho group.id. Nhiều consumer có thể có client.id khác nhau nhưng vẫn thuộc cùng một group nếu cùng group.id. Ngược lại, hai consumer có cùng client.id nhưng group.id khác nhau vẫn thuộc hai group độc lập.

Spring Kafka còn có cấu hình để tạo client ID cho từng consumer thread/container. Client ID giúp quan sát từng instance; group ID quyết định chia tải và tiến độ đọc. Hãy giữ hai khái niệm tách biệt khi thiết kế cấu hình và dashboard.

## 12. Những lỗi thường gặp khi chọn group.id

| Lỗi cấu hình | Hệ quả | Cách khắc phục |
|---|---|---|
| Mỗi replica dùng một group ID khác nhau | Mỗi replica đọc toàn bộ luồng, có thể xử lý trùng | Dùng chung group ID cho các replica cùng use case. |
| Nhiều use case độc lập dùng chung group | Các use case chia nhau record và mỗi use case chỉ nhận một phần | Tách group ID theo từng use case cần đọc độc lập. |
| Dev và production dùng chung group trên một cluster | Consumer hai môi trường tranh partition và dùng chung offset | Tách group ID theo môi trường. |
| Đổi group ID mà không đánh giá offset | Consumer mới có thể replay dữ liệu hoặc bỏ qua dữ liệu cũ tùy auto.offset.reset | Lập kế hoạch offset và kiểm thử trước khi đổi. |
| Tạo group ID ngẫu nhiên mỗi lần chạy | Mỗi lần restart có thể tạo tiến độ mới và đọc lại dữ liệu | Dùng group ID ổn định. |
| Dùng group mới cho shadow consumer nhưng vẫn bật side effect | Sự kiện có thể tác động nghiệp vụ hai lần | Dùng chế độ quan sát hoặc output riêng, kiểm soát idempotency. |
| Dùng client.id làm group ID | Nhầm lẫn giữa định danh client và tiến độ consumer | Cấu hình riêng group.id và client.id. |

Một dấu hiệu quan trọng cần quan sát là số consumer group tăng bất thường hoặc nhiều group có cùng mục đích. Đây có thể là dấu hiệu ứng dụng tạo group ID động ngoài ý muốn.

## 13. Kiểm thử cấu hình group.id

Kiểm thử group ID cần xác minh hành vi của group chứ không chỉ đọc giá trị trong application.yml.

Các kịch bản nên có:

- Nhiều replica cùng group ID chia nhau partition.
- Hai group ID khác nhau cùng đọc toàn bộ record của topic.
- Hai listener cùng group ID có chủ đích chia tải.
- Listener thuộc hai use case khác nhau dùng group ID riêng.
- Group mới bắt đầu đọc theo auto.offset.reset khi chưa có offset.
- Group cũ tiếp tục từ offset đã commit sau khi restart.
- Thay đổi group ID không làm thay đổi offset của group cũ.
- Môi trường local và production không vô tình dùng chung group trên cùng cluster.

Có thể dùng EmbeddedKafka hoặc Testcontainers để dựng topic nhiều partition và kiểm tra record được phân phối cho các group. Với test group assignment, hãy chờ sự kiện assignment hoặc điều kiện cụ thể với timeout; không dùng Thread.sleep cố định để đoán group đã ổn định.

Khi test auto.offset.reset, hãy tạo group mới hoặc xóa offset test có kiểm soát. Nếu group đã có offset hợp lệ, earliest không làm consumer quay lại đầu topic. Đây là nguyên nhân thường khiến test replay không cho kết quả như mong đợi.

## 14. Bài tập tổng hợp: thiết kế group cho hệ thống đơn hàng

Giả sử topic orders.created được producer phát sự kiện. Hệ thống có ba chức năng: fulfillment, analytics và audit. Mỗi chức năng có thể chạy nhiều replica.

Yêu cầu:

1. Chọn group ID riêng cho fulfillment, analytics và audit.
2. Chạy hai replica fulfillment với cùng group ID và quan sát chúng chia partition.
3. Chạy analytics và audit với group ID riêng, xác minh mỗi group nhận được toàn bộ luồng.
4. Dừng một replica fulfillment và quan sát rebalance.
5. Tạo một group replay mới với auto.offset.reset=earliest để đọc lại dữ liệu còn giữ.
6. Xác minh group replay không thay đổi offset của fulfillment production.
7. Chạy local và staging trên cùng cluster với group ID khác nhau.
8. Thử cấu hình sai: ba replica fulfillment dùng ba group ID khác nhau; quan sát số record mỗi replica nhận được.
9. Thử cấu hình sai: analytics dùng chung group với fulfillment; quan sát hai use case chia partition.
10. Xây dựng shadow consumer dùng group riêng nhưng không tạo side effect production.
11. Ghi log group ID, client ID, topic, partition và offset để hỗ trợ truy vết.
12. Viết integration test xác minh các hành vi chia tải và đọc độc lập.

Kết quả cần có một bảng ownership:

| Group ID | Use case | Replica dự kiến | Topic subscription | Side effect |
|---|---|---:|---|---|
| orders-fulfillment-prod | Xử lý đơn hàng | 2+ | orders.created | Giữ hàng, cập nhật đơn hàng |
| orders-analytics-prod | Phân tích | 1+ | orders.created | Ghi dữ liệu phân tích |
| orders-audit-prod | Audit | 1+ | orders.created | Lưu dấu vết |
| orders-replay-test | Replay thử nghiệm | Theo nhu cầu | orders.created | Không tác động production |

Hãy ghi rõ owner, môi trường, mục đích và chính sách offset cho từng group. Việc này giúp đội vận hành biết group nào được phép replay, group nào tạo side effect và group nào chỉ dùng để quan sát.

## 15. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Group identity | group.id và consumer group | Giải thích được group ID gắn với membership và offset. |
| 2. Scale replicas | Nhiều instance cùng group | Các replica chia partition để xử lý một use case. |
| 3. Independent use cases | Nhiều group cùng topic | Mỗi use case nhận toàn bộ record với offset riêng. |
| 4. Spring Kafka | consumer.group-id và @KafkaListener groupId | Cấu hình đúng group mặc định và group riêng từng listener. |
| 5. Environment | Local, dev, staging, production | Không để môi trường dùng chung group ngoài ý muốn. |
| 6. Offset/replay | auto.offset.reset và group mới | Dự đoán được vị trí bắt đầu khi group chưa có offset. |
| 7. Migration | Blue-green và shadow consumer | Chọn được cách dùng group cũ hoặc group mới theo mục tiêu. |
| 8. Operations | Naming, ownership, metrics | Tra cứu được owner, mục đích và tiến độ của từng group. |
| 9. Testing | EmbeddedKafka/Testcontainers | Xác minh được chia tải và đọc độc lập. |

Bài học hoàn thành khi bạn có thể thiết kế group ID theo từng use case, cấu hình đúng trong Spring Kafka, giải thích tác động của group ID lên partition assignment và offset, đồng thời lập kế hoạch replay hoặc migration mà không gây xử lý trùng ngoài ý muốn.

Một quy tắc thiết kế hữu ích là: các replica cùng thực hiện một luồng xử lý dùng chung group ID; các use case cần đọc độc lập dùng group ID riêng. Khi coi group ID là một phần của hợp đồng vận hành, bạn sẽ kiểm soát tốt hơn việc chia tải, replay, triển khai nhiều môi trường và khả năng truy vết consumer trong hệ thống Spring Kafka.

