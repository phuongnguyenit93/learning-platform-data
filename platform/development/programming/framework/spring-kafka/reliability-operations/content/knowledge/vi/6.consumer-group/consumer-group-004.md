# Group id ổn định theo nghiệp vụ

Trong Kafka, consumer group là một đơn vị xử lý có tiến độ đọc riêng. Giá trị group.id xác định consumer nào cùng chia sẻ việc đọc một luồng dữ liệu và cùng sử dụng offset đã commit. Vì vậy, group.id cần đại diện cho **một trách nhiệm xử lý nghiệp vụ ổn định**.

Một consumer group thường tồn tại lâu hơn một pod, một JVM hay một lần triển khai. Khi ứng dụng khởi động lại hoặc được scale thêm replica, các consumer mới cần tham gia đúng group để tiếp tục tiến độ đã lưu. Nếu group.id thay đổi theo tên pod, timestamp hoặc mã build, Kafka sẽ xem đó là một group khác và ứng dụng có thể bắt đầu một lịch sử offset mới.

Bài này giải thích cách đặt group.id theo mục đích nghiệp vụ, cách chọn giữa dùng chung và tách group, cách cấu hình trong Spring Kafka và những ảnh hưởng khi đổi định danh.

## 1. group.id xác định điều gì?

Kafka lưu offset theo từng consumer group, topic và partition. Khi consumer đọc record, group có thể commit offset để ghi nhận vị trí tiếp theo cần xử lý. Những consumer có cùng group.id tham gia cùng một nhóm điều phối và chia sẻ tiến độ đọc đó.

Ví dụ, topic orders có bốn partition. Ba instance của dịch vụ tạo projection đơn hàng cùng tham gia group orders-projection. Kafka phân phối các partition cho ba consumer. Mỗi partition tại một thời điểm được gán cho tối đa một consumer trong group, nhưng một consumer có thể nhận nhiều partition.

    Topic orders
      partition 0 ----+
      partition 1 ----+----> group: orders-projection
      partition 2 ----+          |
      partition 3 ----+          +--> consumer instance A
                                  +--> consumer instance B
                                  +--> consumer instance C

Khi một instance dừng, group thực hiện rebalance để phân phối lại partition cho các thành viên còn hoạt động. Các instance mới tham gia với cùng group.id có thể tiếp tục từ offset đã commit của group, nếu offset đó còn hợp lệ.

Nếu một dịch vụ khác cần nhận toàn bộ sự kiện orders để phát hành hóa đơn, dịch vụ đó phải dùng group riêng. Hai group độc lập có hai tiến độ đọc riêng:

    Topic orders
       |
       +----> group: orders-projection
       |          +--> nhiều consumer chia tải
       |
       +----> group: invoice-issuer
                  +--> nhiều consumer chia tải

Mỗi group nhận luồng record theo tiến độ riêng. Việc tạo thêm một group mới không làm tăng số consumer chia tải trong group hiện có; nó tạo một subscriber độc lập đọc lại topic.

### 1.1. Phân biệt group.id với các định danh khác

| Định danh | Mục đích | Có nên thay đổi theo lần deploy? |
|---|---|---|
| group.id | Xác định logical consumer group và namespace offset | Không, nếu trách nhiệm xử lý vẫn như cũ |
| client.id | Nhận diện một Kafka client cho log và metric | Có thể thêm thông tin instance nếu cần |
| member.id | Nhận diện thành viên trong group do Kafka quản lý | Kafka quản lý trong quá trình tham gia group |
| group.instance.id | Định danh thành viên tĩnh khi dùng static membership | Ổn định theo từng member, có chủ đích |
| @KafkaListener id | Định danh listener container trong Spring | Ổn định và duy nhất trong application context |
| application name | Tên dịch vụ hoặc ứng dụng triển khai | Có thể rộng hơn một trách nhiệm consumer |

group.id không phải tên của một pod hay một Kafka client riêng lẻ. Nó đại diện cho tập consumer hợp tác xử lý cùng một luồng nghiệp vụ.

## 2. Đặt group.id theo trách nhiệm nghiệp vụ

Tên group nên giúp người vận hành trả lời được câu hỏi: **Nhóm consumer này đọc dữ liệu để thực hiện trách nhiệm nào?**

Một mẫu tên dễ hiểu có thể là:

    <environment>.<business-domain>.<processing-purpose>[.<version>]

Ví dụ:

- prod.orders.projection.v1: xây dựng projection đọc đơn hàng cho hệ thống production.
- prod.billing.invoice-issuer.v1: phát hành hóa đơn từ các sự kiện nghiệp vụ.
- prod.risk.fraud-detection.v1: phân tích sự kiện để phát hiện gian lận.
- prod.fulfillment.shipment-planner.v1: lập kế hoạch giao hàng.
- staging.orders.projection.v1: projection đơn hàng ở môi trường staging.

Có thể dùng dấu chấm, dấu gạch ngang hoặc quy ước tên khác. Điều quan trọng là tên có ý nghĩa, ổn định và được áp dụng nhất quán trong tổ chức.

Một group có thể đọc nhiều topic nếu các record phục vụ cùng một trách nhiệm xử lý. Ngược lại, một topic có thể có nhiều group độc lập nếu nhiều hệ thống cần tiêu thụ cùng sự kiện với tiến độ riêng. Vì vậy, không nên mặc định group.id chỉ là tên topic hoặc tên ứng dụng.

### 2.1. Một group cho một logical workload

Nếu nhiều replica cùng chạy một dịch vụ và cùng tạo một loại kết quả nghiệp vụ, chúng thường dùng chung group.id.

Ví dụ: bốn pod của orders-projection đều đọc topic orders và cập nhật cùng loại read model. Chúng phải tham gia cùng group để Kafka phân phối partition và chia tải.

~~~yaml
spring:
  kafka:
    consumer:
      group-id: prod.orders.projection.v1
~~~

Khi rolling deployment thay pod cũ bằng pod mới, group.id vẫn giữ nguyên. Thành viên mới tham gia group hiện tại và tiếp tục tiến độ đã commit.

### 2.2. Tách group cho các trách nhiệm độc lập

Nếu hai dịch vụ cần nhận cùng sự kiện nhưng thực hiện tác vụ khác nhau, chúng phải có group.id riêng.

~~~java
@KafkaListener(
    id = "ordersProjectionListener",
    groupId = "prod.orders.projection.v1",
    topics = "orders"
)
public void updateProjection(OrderEvent event) {
    projectionService.apply(event);
}

@KafkaListener(
    id = "invoiceIssuerListener",
    groupId = "prod.billing.invoice-issuer.v1",
    topics = "orders"
)
public void issueInvoice(OrderEvent event) {
    invoiceService.issue(event);
}
~~~

Hai listener trên cùng nhận các record từ topic orders nhưng mỗi listener có tiến độ riêng. Nếu dùng chung group.id, chúng sẽ tham gia cùng một nhóm và cạnh tranh phân vùng theo cơ chế group assignment. Một record được giao cho một member trong group ở một thời điểm, nên không thể dựa vào cách này để bảo đảm cả projection và invoice đều nhận được mọi record.

Đây là quy tắc quan trọng khi thiết kế hệ thống event-driven:

- Cùng một trách nhiệm xử lý, cần chia tải: dùng cùng group.id.
- Trách nhiệm xử lý độc lập, cần đọc đầy đủ luồng riêng: dùng group.id khác nhau.

## 3. Vì sao group.id cần ổn định?

Kafka lưu offset theo group.id. Khi consumer restart với cùng group.id, nó có thể tiếp tục từ offset đã commit. Nếu group.id thay đổi, Kafka coi đó là một group khác và không tự chuyển offset từ group cũ sang group mới.

Giả sử group prod.orders.projection.v1 đã xử lý tới offset 850 của partition 0. Một lần deploy đổi group.id thành orders-projection-20261115. Group mới không có offset 850. Kafka phải áp dụng chính sách auto.offset.reset nếu chưa có offset hợp lệ cho group mới.

    group cũ: prod.orders.projection.v1
       partition 0 -> committed offset 850

    deploy đổi group.id

    group mới: orders-projection-20261115
       partition 0 -> chưa có committed offset
       |
       +--> auto.offset.reset quyết định vị trí bắt đầu

Nếu auto.offset.reset=earliest, group mới có thể đọc lại các record còn được giữ trên topic từ đầu phần dữ liệu còn lưu. Nếu dùng latest, group mới bắt đầu ở cuối log và chỉ nhận record mới sau thời điểm bắt đầu. Hai lựa chọn có thể tạo ra kết quả nghiệp vụ rất khác nhau.

### 3.1. Ảnh hưởng của auto.offset.reset

auto.offset.reset được áp dụng khi group không có offset hợp lệ, chẳng hạn group mới chưa commit offset hoặc offset đã nằm ngoài phạm vi log còn lưu.

| Giá trị | Hành vi | Trường hợp cần cân nhắc |
|---|---|---|
| earliest | Bắt đầu từ record sớm nhất còn được giữ | Muốn dựng lại projection hoặc replay dữ liệu còn lưu |
| latest | Bắt đầu từ cuối log | Chỉ muốn xử lý dữ liệu mới khi tạo group mới |
| none | Báo lỗi nếu không tìm thấy offset hợp lệ | Muốn buộc cấu hình offset rõ ràng và tránh tự chọn vị trí |

Ví dụ cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: prod.orders.projection.v1
      auto-offset-reset: earliest
~~~

earliest không khôi phục được record đã hết retention hoặc đã bị loại bỏ bởi compaction. latest cũng không phải cách khắc phục dữ liệu cũ bị mất; nó chủ động bỏ qua phần backlog trước vị trí bắt đầu mới của group.

Với một group đã có offset hợp lệ, thay đổi auto.offset.reset thường không làm consumer quay lại đầu topic. Chính sách này không phải lệnh reset offset cho group đang hoạt động.

### 3.2. Offset cũ không được bảo đảm tồn tại vô thời hạn

Dùng group.id ổn định giúp giữ continuity, nhưng không có nghĩa offset tồn tại mãi mãi. Kafka có chính sách retention cho offset của consumer group không còn hoạt động. Topic cũng có retention hoặc compaction riêng. Nếu group ngừng quá lâu, offset hết hạn hoặc record nguồn không còn, việc restart có thể không khôi phục được toàn bộ lịch sử.

Hãy xác định thời gian gián đoạn tối đa mà hệ thống cần chịu được, cấu hình retention phù hợp và theo dõi thời điểm commit cuối cùng. Với projection có thể dựng lại, cần có kế hoạch replay từ nguồn dữ liệu còn lưu hoặc snapshot.

## 4. Tránh tạo group.id theo instance hoặc deployment

Một số cách đặt tên làm mất tính ổn định của group:

| Cách đặt tên | Ví dụ | Hệ quả |
|---|---|---|
| Theo pod | orders-projection-pod-7c9d | Mỗi pod có thể tạo một group riêng, đọc lại toàn bộ stream |
| Theo hostname | orders-projection-node-03 | Scale hoặc đổi node làm thay đổi group |
| Theo timestamp | orders-projection-20261115 | Mỗi lần deploy có thể tạo group mới |
| Theo build number | orders-projection-build-482 | Lịch sử offset bị phân tách theo build |
| Theo UUID ngẫu nhiên | orders-projection-7f3a... | Restart có thể tạo group hoàn toàn mới |
| Theo request hoặc user | orders-projection-user-1042 | Số lượng group tăng không kiểm soát và offset bị phân mảnh |

Ví dụ cấu hình sai nếu mục đích là một workload chia tải:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-projection-pod-7c9d
~~~

Mỗi pod có thể tham gia một group khác nhau. Khi đó, mỗi group nhận toàn bộ topic thay vì chia partition với các pod còn lại. Điều này làm tăng lượng đọc, tăng số offset và có thể khiến side effect nghiệp vụ bị nhân đôi.

Cấu hình đúng hơn là dùng một group.id cố định theo trách nhiệm:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: prod.orders.projection.v1
~~~

Tên instance vẫn có thể xuất hiện trong client.id hoặc log để phân biệt member. Không cần đưa tên instance vào group.id chỉ để biết consumer nào đang chạy.

## 5. Cấu hình group.id trong Spring Kafka

Spring Kafka cho phép đặt group.id ở cấu hình consumer dùng chung hoặc chỉ định trực tiếp trên từng @KafkaListener.

### 5.1. Cấu hình mặc định trong application.yml

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092
    consumer:
      group-id: prod.orders.projection.v1
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.events
~~~

group-id trong spring.kafka.consumer là giá trị mặc định mà Spring Boot dùng khi tạo consumer. Nó phù hợp khi các listener trong ứng dụng thực sự thuộc cùng một logical workload.

Nếu một ứng dụng chứa nhiều listener có trách nhiệm khác nhau, nên chỉ định groupId riêng trên từng @KafkaListener thay vì để mọi listener vô tình dùng chung group mặc định.

### 5.2. Chỉ định groupId trên @KafkaListener

~~~java
@KafkaListener(
    id = "ordersProjectionListener",
    groupId = "prod.orders.projection.v1",
    topics = "orders"
)
public void consume(OrderEvent event) {
    projectionService.apply(event);
}
~~~

Thuộc tính groupId trên annotation ghi đè group.id lấy từ consumer factory cho listener đó. Cách khai báo tường minh giúp người đọc thấy ngay trách nhiệm và tiến độ đọc của listener.

Thuộc tính id định danh listener container trong Spring. Theo hành vi mặc định của Spring Kafka, nếu id được đặt và groupId không được khai báo, id có thể được dùng làm group.id khi idIsGroup=true. Thuộc tính groupId tường minh sẽ ghi đè hành vi này. Có thể đặt idIsGroup=false nếu muốn id chỉ là container identifier.

Để tránh vô tình dùng một container id làm định danh offset, nên khai báo groupId rõ ràng trong các listener quan trọng:

~~~java
@KafkaListener(
    id = "invoiceIssuerContainer",
    idIsGroup = false,
    groupId = "prod.billing.invoice-issuer.v1",
    topics = "orders"
)
public void issueInvoice(OrderEvent event) {
    invoiceService.issue(event);
}
~~~

id phải duy nhất trong application context của ứng dụng. Còn groupId cần được thống nhất giữa các instance triển khai cùng workload. Hai thuộc tính có phạm vi và mục đích khác nhau.

### 5.3. Một ứng dụng có nhiều listener

Một ứng dụng Spring Boot có thể chạy nhiều listener container. Nếu chúng phục vụ các trách nhiệm độc lập, hãy cấu hình groupId riêng cho từng listener:

~~~java
@KafkaListener(
    id = "paymentProjectionContainer",
    groupId = "prod.payments.projection.v1",
    topics = "payments"
)
public void updatePaymentProjection(PaymentEvent event) {
    paymentProjection.apply(event);
}

@KafkaListener(
    id = "riskScoringContainer",
    groupId = "prod.risk.scoring.v1",
    topics = "payments"
)
public void scorePayment(PaymentEvent event) {
    riskScoring.score(event);
}
~~~

Hai listener có thể nằm trong cùng một codebase nhưng tiến độ đọc độc lập. Việc chúng được deploy cùng một ứng dụng không có nghĩa chúng có cùng trách nhiệm nghiệp vụ.

Ngược lại, nếu một listener được chạy trên nhiều pod để cùng xử lý một workload, tất cả pod phải dùng cùng groupId. Không thêm hostname hoặc mã replica vào giá trị đó.

## 6. Scale consumer mà không đổi group.id

Khi tăng số instance hoặc concurrency, các consumer mới tham gia cùng group. Kafka rebalance và phân phối partition cho các member. group.id không cần thay đổi khi số replica thay đổi.

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: prod.orders.projection.v1
    listener:
      concurrency: 3
~~~

Với concurrency bằng 3, listener container có thể tạo ba consumer trong cùng group theo cấu hình. Nếu ứng dụng chạy ba pod và mỗi pod có concurrency bằng 3, group có thể có tổng cộng chín consumer member.

Tuy nhiên, số consumer hoạt động song song bị giới hạn bởi số partition được gán. Nếu topic có bốn partition và group có chín consumer, một số consumer sẽ không được gán partition. Tăng concurrency vượt số partition không tự tăng throughput.

| Số partition | Số consumer trong group | Kết quả có thể xảy ra |
|---:|---:|---|
| 4 | 1 | Một consumer xử lý cả bốn partition |
| 4 | 2 | Hai consumer chia nhau partition |
| 4 | 4 | Mỗi consumer có thể nhận một partition |
| 4 | 8 | Tối đa bốn consumer nhận partition; các consumer còn lại idle |

Tạo group.id khác cho mỗi replica không phải cách scale. Điều đó tạo nhiều subscriber độc lập, mỗi subscriber đọc toàn bộ stream và có offset riêng. Để chia tải, hãy tăng member trong cùng group.

## 7. Khi nào nên tạo group.id mới?

Đổi group.id là một quyết định về lịch sử xử lý và tiến độ đọc. Chỉ nên đổi khi thực sự muốn tạo một logical consumer group mới.

Những trường hợp hợp lý có thể gồm:

- Một nghiệp vụ mới cần đọc cùng topic nhưng tạo kết quả khác.
- Một projection mới cần replay lịch sử để xây dựng read model riêng.
- Một phiên bản xử lý mới có semantics không tương thích và cần chạy song song để migration.
- Một workload cần tiến độ độc lập, retention offset và quyền vận hành riêng.

Những trường hợp thường không cần đổi group.id:

- Deploy phiên bản code mới nhưng trách nhiệm nghiệp vụ không đổi.
- Restart pod hoặc JVM.
- Scale số replica hoặc thay đổi concurrency.
- Thay hostname, node, container image tag hoặc build number.
- Thay đổi cấu hình logging, metric hoặc timeout mà không thay đổi logic đọc.

### 7.1. Version suffix phải có ý nghĩa

Có thể thêm version vào tên group khi thay đổi semantics yêu cầu lịch sử offset độc lập:

    prod.orders.projection.v1
    prod.orders.projection.v2

Ví dụ, v2 thay đổi cách tính trạng thái đơn hàng và cần dựng lại projection từ đầu. Group v2 có thể dùng earliest để đọc lại dữ liệu còn lưu, trong khi v1 vẫn chạy để so sánh kết quả.

Đây là một migration có chủ đích. Trước khi triển khai, cần xác định:

1. v2 sẽ bắt đầu từ earliest, latest hay một offset được đặt rõ ràng.
2. Topic còn giữ đủ lịch sử để dựng lại projection hay không.
3. v1 và v2 có thể cùng ghi vào một bảng hoặc cùng phát side effect không.
4. Cách so sánh kết quả và thời điểm chuyển traffic.
5. Cách dừng v1 và giữ lại khả năng rollback.

Không thêm version vào group.id cho mọi release. Nếu mỗi bản build tạo group mới, consumer có thể đọc lại dữ liệu, tạo duplicate và để lại nhiều group cũ khó quản lý.

### 7.2. Thay group.id không tự chuyển offset

Nếu cần đổi tên group nhưng muốn tiếp tục từ vị trí đã đọc, phải lập kế hoạch chuyển offset riêng. Kafka không tự sao chép committed offset từ group cũ sang group mới chỉ vì hai tên giống nhau.

Có thể sử dụng công cụ quản trị consumer group để mô tả hoặc chuyển offset theo quy trình đã kiểm soát. Cần bảo đảm consumer mới chưa chạy khi đặt offset, xác định đúng topic-partition và kiểm tra kết quả trước khi mở workload. Không nên vừa cho group mới tự chạy với auto.offset.reset vừa kỳ vọng nó tự tìm offset của group cũ.

## 8. Môi trường, tenant và phạm vi định danh

### 8.1. Phân biệt môi trường

Nếu dev, staging và production dùng chung một Kafka cluster, nên đưa môi trường vào group.id:

    dev.orders.projection.v1
    staging.orders.projection.v1
    prod.orders.projection.v1

Điều này giúp tách offset và dễ tìm group trong dashboard. Nếu các môi trường dùng cluster độc lập, Kafka đã phân tách namespace group ở cấp cluster, nhưng vẫn có thể giữ quy ước tên có môi trường để vận hành nhất quán.

Không dùng chung group.id giữa các môi trường nếu chúng vô tình kết nối vào cùng cluster và cần tiến độ đọc độc lập.

### 8.2. Group riêng theo tenant

Một số hệ thống cần tách tiến độ theo tenant vì mỗi tenant có lịch xử lý, quyền truy cập hoặc yêu cầu phục hồi riêng. Khi đó có thể cân nhắc group riêng cho tenant.

Tuy nhiên, không nên tạo group cho từng user hoặc từng request. Nếu có hàng chục nghìn tenant thay đổi liên tục, số lượng group và offset sẽ tăng, làm phức tạp việc giám sát và quản trị.

Trước khi chọn mô hình group theo tenant, hãy xác định:

- Tenant có thực sự cần tiến độ đọc độc lập hay không?
- Có yêu cầu replay, retention hoặc ACL riêng cho từng tenant không?
- Số lượng tenant tối đa và tốc độ tạo/xóa tenant là bao nhiêu?
- Topic có partition key theo tenant để giữ thứ tự cần thiết không?
- Hệ thống có đủ năng lực vận hành và giám sát số group dự kiến không?

Nếu các tenant chỉ cần dùng chung một luồng xử lý, có thể dùng một group ổn định và mang tenantId trong key hoặc payload. Ứng dụng phân luồng nghiệp vụ theo tenant ở bên trong handler. Chỉ tách group khi nhu cầu tiến độ và vận hành thực sự yêu cầu.

### 8.3. Không đưa dữ liệu nhạy cảm vào group.id

group.id có thể xuất hiện trong metric, log, công cụ quản trị và cấu hình ACL. Không nên đưa email, số điện thoại, mã khách hàng nhạy cảm, token hoặc secret vào tên group. Hãy dùng tên capability hoặc mã định danh kỹ thuật không nhạy cảm.

## 9. Static membership không thay thế group.id

Kafka hỗ trợ static membership thông qua group.instance.id. Thuộc tính này giúp nhận diện một member ổn định trong group và có thể giảm một số lần rebalance khi member tạm thời rời đi rồi quay lại với cùng identity.

Cần phân biệt:

- group.id xác định logical group và offset dùng chung.
- group.instance.id xác định một member cụ thể trong group khi bật static membership.

Ví dụ, ba instance của một workload có thể dùng cùng group.id nhưng mỗi instance có group.instance.id riêng, ổn định theo instance:

    group.id = prod.orders.projection.v1
    group.instance.id = orders-projection-member-0

Không dùng một group.instance.id giống nhau cho nhiều member đang hoạt động đồng thời trong cùng group; điều đó có thể gây xung đột thành viên. Nếu nền tảng orchestration tạo lại pod với tên khác, cần cân nhắc cách cấp static member identity và thời gian session timeout.

Static membership là tối ưu hành vi tham gia group. Nó không phải lý do để đưa pod name vào group.id, cũng không thay thế quy ước group theo nghiệp vụ.

## 10. group.id và quyền truy cập Kafka

Trong cluster có bật authorization, quyền truy cập consumer group có thể được kiểm soát bằng ACL cho resource loại GROUP. Tên group vì vậy còn là một phần của ranh giới vận hành và bảo mật.

Khi đổi group.id, consumer có thể cần quyền cho group mới. Một ứng dụng có quyền đọc topic nhưng thiếu quyền sử dụng group tương ứng có thể gặp lỗi authorization khi tham gia hoặc commit offset.

Khi thiết kế tên group, hãy phối hợp với quy ước ACL:

- Cấp quyền theo workload hoặc domain cần thiết.
- Không cấp quyền rộng chỉ để khắc phục lỗi group name không nhất quán.
- Khi migration sang group mới, chuẩn bị ACL trước khi bật consumer.
- Thu hồi quyền group cũ sau khi migration và rollback window kết thúc.

Tên group ổn định giúp quyền truy cập dễ kiểm soát và audit hơn.

## 11. Quan sát và vận hành consumer group

Một group.id có ý nghĩa nghiệp vụ giúp người vận hành liên hệ metric Kafka với trách nhiệm của dịch vụ. Nên theo dõi:

- Consumer lag theo group, topic và partition.
- Số member đang hoạt động và trạng thái group.
- Số lần rebalance và thời gian hoàn tất rebalance.
- Offset đã commit và thời điểm commit cuối cùng.
- Tốc độ xử lý record và tỷ lệ lỗi theo group.
- Số group mới xuất hiện bất thường sau deployment.
- Group không còn member nhưng vẫn có offset hoặc lag cần xử lý.

Nếu mỗi lần deploy tạo group mới, dashboard có thể xuất hiện nhiều group cùng tên gần giống nhau. Điều đó gây khó khăn khi xác định group nào là workload chính, group nào đang giữ offset cũ và group nào vẫn tiêu thụ dữ liệu.

Tên group nên được đưa vào log và tracing cùng các trường topic, partition, offset, eventId và client.id. Không dùng group.id thay cho eventId; group nhận diện workload, còn eventId nhận diện một sự kiện nghiệp vụ.

### 11.1. Kiểm tra group bằng công cụ Kafka

Có thể xem trạng thái consumer group bằng Kafka CLI:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group prod.orders.projection.v1
~~~

Lệnh này giúp quan sát partition assignment, current offset, log end offset và lag theo group. Tên script hoặc cách gọi có thể khác tùy bản phân phối Kafka và hệ điều hành.

Để liệt kê group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --list
~~~

Trước khi xóa hoặc reset một group, cần xác nhận không còn workload cần tiến độ đó và có phương án khôi phục. Xóa group hoặc reset offset là thao tác quản trị có thể làm thay đổi hành vi replay và side effect nghiệp vụ.

## 12. Kiểm thử group.id trong Spring Kafka

Trong kiểm thử, cần tránh để test dùng chung group production hoặc dùng một group tĩnh đã có offset từ lần chạy trước nếu bài test cần đọc lại từ đầu.

Có thể tạo group riêng cho test:

~~~java
@KafkaListener(
    id = "ordersTestListener",
    groupId = "test.orders.projection",
    topics = "orders-test"
)
public void consume(OrderEvent event) {
    testRecorder.record(event);
}
~~~

Nếu test chạy song song, mỗi test có thể cần group riêng để không cạnh tranh offset và partition assignment với test khác. Trong môi trường test, group ID động có thể hữu ích vì vòng đời ngắn và mục tiêu là cô lập test. Không mang cách đặt tên động đó sang production.

Một test tích hợp nên kiểm tra các hành vi có ý nghĩa:

1. Hai consumer cùng group chia sẻ partition và không nhận hai bản sao đồng thời của cùng một lần giao record trong điều kiện bình thường.
2. Hai group khác nhau đều có thể nhận cùng record từ topic.
3. Restart consumer với cùng group.id tiếp tục từ offset đã commit khi offset còn hợp lệ.
4. Dùng group.id mới tạo lịch sử offset mới và tuân theo auto.offset.reset.
5. Scale số consumer mà không thay group.id vẫn duy trì một logical workload.
6. Cấu hình annotation groupId ghi đè group mặc định theo đúng mong đợi.

Test nên xác nhận kết quả nghiệp vụ và offset, không chỉ xác nhận ứng dụng khởi động thành công.

## 13. Các tình huống cấu hình sai thường gặp

| Tình huống | Hệ quả | Cách xử lý |
|---|---|---|
| Mỗi pod có group.id riêng | Mỗi pod đọc toàn bộ topic | Dùng cùng group.id cho các replica cùng workload |
| Hai nghiệp vụ độc lập dùng chung group.id | Chúng chia partition và có thể không cùng nhận một record | Tách group theo trách nhiệm |
| Đổi group.id theo build number | Group mới không có offset cũ; có thể replay hoặc bỏ qua backlog | Giữ tên ổn định qua các lần deploy |
| Đổi group.id nhưng giữ auto.offset.reset=latest | Group mới bắt đầu ở cuối log và không đọc backlog cũ | Chọn reset policy theo mục tiêu migration |
| Tạo group mới với earliest nhưng topic đã hết retention | Không thể dựng lại dữ liệu đã bị xóa | Bổ sung snapshot hoặc nguồn lưu trữ khác |
| Dùng listener id làm group ngoài ý muốn | Thay đổi id container có thể làm đổi group | Khai báo groupId tường minh |
| Dùng group theo từng user | Số group và offset tăng nhanh | Dùng một workload group, phân loại user trong payload nếu phù hợp |
| Tăng concurrency bằng cách đổi group.id | Mỗi group đọc cả stream, không phải chia tải | Tăng member/concurrency trong cùng group |
| Đổi group nhưng quên ACL | Consumer không thể tham gia hoặc commit offset | Cấp quyền cho group mới trước khi deploy |
| Dùng static member id trùng nhau | Member có thể xung đột | Cấp group.instance.id riêng cho từng member |

## 14. Quy ước đặt tên có thể áp dụng trong dự án

Một quy ước thực tế nên có các thành phần vừa đủ để hiểu mục đích:

    <env>.<domain>.<capability>.<version>

Ví dụ:

| group.id | Trách nhiệm |
|---|---|
| prod.orders.projection.v1 | Dựng read model đơn hàng |
| prod.orders.search-indexer.v1 | Cập nhật chỉ mục tìm kiếm đơn hàng |
| prod.billing.invoice-issuer.v1 | Phát hành hóa đơn |
| prod.payments.reconciliation.v1 | Đối soát thanh toán |
| prod.risk.fraud-detection.v1 | Phân tích gian lận |
| staging.orders.projection.v1 | Projection đơn hàng ở staging |

Có thể bỏ version nếu tổ chức không quản lý version trong group name. Nếu có version, hãy chỉ tăng khi cần một lịch sử offset độc lập hoặc migration có chủ đích.

Nên ghi quy ước này trong tài liệu vận hành của domain, cùng owner của từng group, topic được đọc, mục đích xử lý, retention cần thiết và quy trình reset/replay. Khi một workload đổi tên hoặc ngừng hoạt động, cần có quy trình dọn group cũ sau khi xác nhận không còn nhu cầu rollback hoặc audit.

## 15. Nguyên tắc ra quyết định

Khi tạo một consumer mới hoặc sửa cấu hình Spring Kafka, hãy bắt đầu bằng việc xác định trách nhiệm xử lý:

- Nếu nhiều instance cùng thực hiện một trách nhiệm, dùng cùng một group.id ổn định.
- Nếu hai trách nhiệm cần nhận cùng event độc lập, dùng group.id khác nhau.
- Nếu chỉ restart, scale hoặc deploy code mới, giữ nguyên group.id.
- Nếu cần replay lịch sử hoặc migration có tiến độ riêng, tạo group mới với kế hoạch offset và side effect rõ ràng.
- Nếu tách theo môi trường hoặc tenant, chỉ làm khi cần tiến độ, quyền hoặc ranh giới vận hành độc lập.
- Nếu muốn nhận diện từng client hoặc member, dùng client.id hoặc group.instance.id đúng mục đích, không thay group.id.

Một group.id tốt cho người vận hành biết consumer đang phục vụ nghiệp vụ nào và giúp Kafka duy trì tiến độ đọc xuyên suốt vòng đời triển khai. Hãy coi group.id là định danh lâu dài của một logical consumer workload, rồi quản lý việc thay đổi nó như một thay đổi về lịch sử xử lý dữ liệu.