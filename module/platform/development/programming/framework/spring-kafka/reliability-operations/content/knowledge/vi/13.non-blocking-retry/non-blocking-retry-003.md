# Cách retry topic hoạt động

Trong Spring Kafka, **non-blocking retry** là cơ chế chuyển một record xử lý thất bại sang các Kafka topic dành riêng cho việc thử lại. Thay vì giữ consumer của topic gốc chờ hết khoảng backoff, framework gửi record lỗi sang retry topic, để consumer của topic gốc tiếp tục xử lý những record khác. Consumer trên retry topic sẽ giao lại record cho listener khi đến thời điểm retry được cấu hình. Nếu vẫn thất bại sau các lần thử được phép, record được chuyển sang dead-letter topic (DLT) hoặc đi qua cơ chế kết thúc phù hợp.

Trong chủ đề Spring Kafka Reliability Operations, hiểu cơ chế này đặc biệt quan trọng vì nó thay đổi luồng xử lý, độ trễ, thứ tự record, cách theo dõi lỗi và mức độ chịu tải của consumer group. Retry topic giải quyết vấn đề **không chặn luồng chính bởi một record cần chờ lâu**, nhưng không tự tạo exactly-once, không sửa lỗi dữ liệu và không giữ nguyên thứ tự xử lý giữa các record.

## 1. Vì sao cần retry topic?

Giả sử listener xử lý sự kiện OrderCreated và cần gọi một service thanh toán. Service trả HTTP 503, còn thời gian phục hồi dự kiến là vài phút. Nếu dùng blocking retry với backoff dài, consumer thread có thể phải chờ record đó; các partition khác do cùng consumer sở hữu cũng có thể bị trì hoãn.

Với retry topic, Spring Kafka chuyển sự kiện thất bại sang topic riêng và để consumer chính tiếp tục đọc:

~~~text
Topic gốc: orders

offset 100: OrderCreated A -> thất bại tạm thời
                            |
                            v
                       orders-retry

offset 101: OrderCreated B -> xử lý tiếp ở topic gốc
offset 102: OrderCreated C -> xử lý tiếp ở topic gốc

Retry consumer:
  Chờ đến hạn -> xử lý lại A
~~~

Như vậy, sự kiện A vẫn có cơ hội được xử lý sau khi dependency phục hồi, trong khi B và C không phải chờ toàn bộ thời gian retry của A. Đây là lợi ích chính, nhưng cũng tạo ra thay đổi về thứ tự: B và C có thể hoàn tất trước A.

Retry topic phù hợp với những lỗi có thể phục hồi sau thời gian chờ tương đối dài, chẳng hạn API tạm thời unavailable, giới hạn tốc độ của downstream hoặc service cần thời gian ổn định lại. Nếu lỗi là schema không hợp lệ hoặc dữ liệu không thể chuyển đổi, gửi qua nhiều retry topic thường chỉ kéo dài thời gian phát hiện sự cố.

## 2. Luồng main topic → retry topic → DLT

Spring Kafka có thể xây dựng một **retry topology** gồm listener cho topic gốc, các topic retry với khoảng chờ khác nhau và một DLT.

Ví dụ một record được phép xử lý tối đa bốn lần, tính cả lần đầu:

~~~text
                     Lần xử lý 1
                  +----------------+
                  | orders (main)  |
                  +----------------+
                          |
                     Listener lỗi
                          |
                          v
                    +-------------+
                    | Retry #1    | chờ khoảng 1 giây
                    +-------------+
                          |
                     Listener lỗi
                          |
                          v
                    +-------------+
                    | Retry #2    | chờ khoảng 2 giây
                    +-------------+
                          |
                     Listener lỗi
                          |
                          v
                    +-------------+
                    | Retry #3    | chờ khoảng 4 giây
                    +-------------+
                          |
                     Vẫn thất bại
                          |
                          v
                    +-------------+
                    | orders-dlt  |
                    +-------------+
~~~

Tên Retry #1, Retry #2 và Retry #3 trong sơ đồ là tên vai trò. Spring Kafka có thể sinh tên topic mang hậu tố retry và thông tin delay; tên cụ thể phụ thuộc version, suffix, chiến lược tái sử dụng topic và cấu hình của ứng dụng.

Mỗi chặng có một consumer xử lý record trên topic tương ứng:

1. Consumer của topic gốc nhận record và gọi business listener.
2. Listener ném exception.
3. Infrastructure retry của Spring Kafka kiểm tra exception, số lần thử và backoff.
4. Nếu còn retry, recoverer publish một bản ghi tương ứng sang retry topic đã chọn, kèm metadata cần thiết.
5. Consumer của retry topic nhận record, nhưng chỉ thực thi listener khi thời điểm backoff đến hạn.
6. Nếu listener ở retry topic thành công, hành trình retry của record kết thúc.
7. Nếu vẫn thất bại và còn lần retry, record được publish đến retry topic tiếp theo.
8. Nếu đã hết lần thử hoặc exception không được phép retry, record được định tuyến đến DLT theo chính sách.

Spring Kafka tổ chức các thành phần trên thông qua RetryTopicConfiguration hoặc annotation @RetryableTopic cùng các listener container được tạo cho retry và DLT. Không cần viết thủ công một vòng lặp sleep rồi gửi lại record trong business listener.

## 3. Retry topic lưu record như một Kafka topic bình thường

Retry topic là một Kafka topic thực tế trên cluster. Nó có partition, offset, retention, replication, ACL và consumer group giống các topic khác. Khi record được chuyển từ topic orders sang retry topic, Kafka lưu một **record mới với offset mới** trong topic đích.

Ví dụ:

~~~text
orders, partition 2, offset 410
    |
    | publish vào retry topic
    v
orders-retry-1000, partition 2, offset 87
    |
    | retry thất bại; publish tiếp
    v
orders-retry-2000, partition 2, offset 24
    |
    | retry thành công
    v
Kết thúc
~~~

Các offset 410, 87 và 24 thuộc ba log khác nhau. Không được dùng offset của retry topic thay cho offset ban đầu để xác định vị trí sự kiện trong topic gốc. Muốn truy vết một sự kiện xuyên suốt retry topology, cần mang theo event ID hoặc correlation ID ổn định.

Khi chuyển record, hệ thống có thể bổ sung header cho biết nguồn gốc, lần thử, exception và thời điểm backoff. Payload và key được gửi tiếp theo cấu hình producer, serializer và recoverer. Hãy coi việc publish sang retry topic là một hành động ghi Kafka mới, có thể thành công hoặc thất bại giống một lần produce thông thường.

Retry topic không phải bộ hẹn giờ có khả năng tự thực thi công việc. Kafka broker chỉ lưu record; **Spring Kafka retry consumer** chịu trách nhiệm chờ đến hạn và gọi lại listener.

## 4. Spring Kafka thực hiện thời gian chờ như thế nào?

Với non-blocking retry, khi forward record, framework tính thời điểm sớm nhất record được phép xử lý lại từ thời gian hiện tại và delay của lần retry. Thông tin backoff được lưu dưới dạng metadata/header phục vụ retry consumer.

Luồng thời gian có thể hình dung:

~~~text
12:00:00.000  Listener gốc thất bại
12:00:00.050  Record được publish vào retry topic
12:00:01.000  Thời điểm retry dự kiến
12:00:01.xxx  Retry listener bắt đầu xử lý nếu consumer sẵn sàng
~~~

Khi consumer đọc record retry trước thời điểm đến hạn, Spring Kafka có thể pause partition tương ứng và tiếp tục poll theo cơ chế container. Khi thời điểm backoff tới, partition được resume để record được giao lại cho listener. Cách này tránh bắt consumer thread ngủ xuyên suốt một khoảng delay dài chỉ để chờ record.

Một vài hệ quả vận hành cần hiểu:

- **Thời gian retry là thời gian sớm nhất, không phải cam kết chính xác từng mili giây.** Record có thể được xử lý muộn do poll timeout, rebalance, thiếu consumer, backlog hoặc broker chậm.
- **Không nên dùng retry topic làm hệ thống scheduling thời gian thực.** Nó phù hợp với retry có delay, không phải hẹn giờ chính xác đến mili giây.
- **Pause diễn ra với partition của retry consumer.** Nó không có nghĩa toàn bộ consumer của topic gốc phải chờ.
- **Một record chưa đến hạn có thể làm các record phía sau trong cùng retry partition chờ.** Topic retry vẫn tuân theo thứ tự offset trong partition.

Vì vậy, non-blocking retry giúp giải phóng luồng xử lý ở main topic, còn retry topic có thể chịu hiện tượng head-of-line waiting khi nhiều record cùng nằm trên một partition với các thời điểm đến hạn khác nhau.

## 5. Cách tính số lần thử và backoff

Thuộc tính attempts của @RetryableTopic bao gồm **lần xử lý đầu tiên trên topic gốc**. Ví dụ attempts bằng 4 nghĩa là có tối đa một lần xử lý gốc và ba lần xử lý lại, nếu các lỗi đều đủ điều kiện retry.

Giả sử cấu hình:

~~~java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
                delay = 1_000,
                multiplier = 2.0,
                maxDelay = 4_000))
~~~

Một lịch thử có thể được biểu diễn:

| Lần xử lý | Nơi xử lý | Delay trước lần đó | Kết quả nếu lại thất bại |
|---|---|---:|---|
| 1 | Topic gốc | Không | Chuyển đến retry đầu tiên |
| 2 | Retry topic thứ nhất | Khoảng 1 giây | Chuyển sang lần retry tiếp theo |
| 3 | Retry topic thứ hai | Khoảng 2 giây | Chuyển sang lần retry tiếp theo |
| 4 | Retry topic thứ ba | Khoảng 4 giây | Chuyển đến DLT |

Ví dụ mang tính minh họa cho exponential backoff với hệ số 2. Delay thực tế còn phụ thuộc thời điểm record được forward, cách đặt lịch retry và thời gian consumer sẵn sàng; nó không phải phép đo chính xác tổng thời gian xử lý.

**Fixed delay** dùng khoảng chờ cố định ở mọi lần retry. **Exponential backoff** tăng khoảng chờ để giảm tải lên dependency đang lỗi. **Randomized backoff/jitter** có thể giúp tránh nhiều consumer retry đồng loạt sau một sự cố chung nếu phiên bản và cấu hình hỗ trợ.

Nếu listener thành công ở một trong các retry topic, framework không chuyển record sang các chặng tiếp theo. Nếu lỗi được phân loại non-retryable, record có thể đi thẳng đến DLT mà không trải qua đủ số attempts.

## 6. Cấu hình @RetryableTopic và @KafkaListener

Trong ứng dụng Spring Kafka hiện đại, cách thuận tiện là đặt @RetryableTopic trên method dùng @KafkaListener.

~~~java
@Service
public class OrderEventListener {

    private final OrderService orderService;

    public OrderEventListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(
                    delay = 1_000,
                    multiplier = 2.0,
                    maxDelay = 4_000),
            autoCreateTopics = "false",
            retryTopicSuffix = "-retry",
            dltTopicSuffix = "-dlt")
    @KafkaListener(
            topics = "orders",
            groupId = "orders-service")
    public void onOrder(OrderCreatedEvent event) {
        orderService.process(event);
    }

    @DltHandler
    public void onDlt(OrderCreatedEvent event) {
        orderService.reportFailedEvent(event);
    }
}
~~~

Ví dụ minh họa:

- attempts bằng 4: một lần đầu và tối đa ba lần retry.
- backoff tăng từ 1 đến 4 giây theo hệ số 2.
- autoCreateTopics bằng false: các topic phải được chuẩn bị trước.
- retryTopicSuffix và dltTopicSuffix mô tả hậu tố để tạo tên topic đích.
- @DltHandler chỉ định method xử lý record khi được giao đến DLT.

Các kiểu OrderCreatedEvent và OrderService thuộc ứng dụng minh họa; cần có serializer/deserializer, consumer factory, producer factory và dependency phù hợp. Bản thân @DltHandler cũng có thể thất bại; ứng dụng phải có chính sách vận hành cho DLT thay vì xem handler này là nơi chắc chắn xử lý thành công.

Tùy phiên bản và cách cấu hình ứng dụng, có thể bật infrastructure retry topic bằng @EnableKafkaRetryTopic:

~~~java
@Configuration
@EnableKafkaRetryTopic
public class KafkaRetryConfiguration {
}
~~~

Không khai báo nhiều cơ chế bootstrap retry topic trùng nhau nếu framework đang tự cấu hình. Kiểm tra phiên bản Spring Kafka và cách ứng dụng tạo listener endpoint để chọn một phương án nhất quán.

Nếu không muốn sử dụng annotation, Spring Kafka cung cấp RetryTopicConfigurationBuilder hoặc cấu hình tương đương để thiết lập retry topology theo Java config. Cách này hữu ích khi nhiều listener cần chia sẻ policy hoặc muốn quản lý tên topic và chiến lược retry tập trung.

## 7. Spring Kafka tạo listener và topic như thế nào?

Khi ứng dụng khởi tạo listener với retry topic, Spring Kafka tạo thêm các endpoint/container để tiêu thụ retry topic và DLT. Mỗi endpoint có subscription tương ứng; consumer và group ID cụ thể được đặt theo cơ chế framework và cấu hình.

Ví dụ topology logic:

~~~text
Listener orders
   subscription: orders

Listener orders-retry-1000
   subscription: orders-retry-1000

Listener orders-retry-2000
   subscription: orders-retry-2000

Listener orders-retry-4000
   subscription: orders-retry-4000

Listener orders-dlt
   subscription: orders-dlt
~~~

Tên các topic ở trên là ví dụ. Tùy chiến lược và phiên bản, Spring Kafka có thể dùng tên khác hoặc tái sử dụng retry topic cho nhiều lần thử. Không nên hardcode giả định một retry topic luôn ứng với đúng một delay khi vận hành hoặc lập dashboard.

Retry topic và DLT cần tồn tại với số partition, replication, retention và quyền truy cập phù hợp. Nếu dùng autoCreateTopics, Spring Kafka có thể tự đăng ký bean topic để tạo khi khởi động trong điều kiện cluster và quyền cho phép. Trong production, nhiều nhóm vận hành chọn tạo topic chủ động để kiểm soát replication factor, min.insync.replicas, ACL và retention.

Listener của các retry topic cũng tiêu thụ tài nguyên: consumer member, connection, thread, fetch, partition assignment và monitoring. Số lượng topic retry càng nhiều thì topology càng phức tạp; cần tính tài nguyên ngoài topic gốc.

## 8. Record được định tuyến đến retry topic nào?

Quyết định routing thường dựa trên chính sách đã cấu hình:

1. Record đang ở chặng nào của retry topology?
2. Có bao nhiêu lần xử lý đã xảy ra?
3. Exception hiện tại có thuộc nhóm được phép retry không?
4. Backoff của bước tiếp theo là bao nhiêu?
5. Đã chạm giới hạn attempts hoặc timeout tổng thể chưa?
6. Nếu không retry, cần chuyển record đến DLT hay thực hiện kết thúc khác?

Ví dụ:

~~~text
orders
  |
  +-- IllegalArgumentException
  |       |
  |       v
  |   Không retry theo classifier -> orders-dlt
  |
  +-- TemporaryPaymentException
          |
          v
       retry topic 1
          |
          +-- thành công -> kết thúc
          |
          +-- vẫn lỗi -> retry topic 2
                              |
                              +-- hết attempts -> orders-dlt
~~~

Trong thực tế, cần cấu hình exception classifier theo tính chất nghiệp vụ. Lỗi mạng hoặc dependency tạm thời có thể retry; dữ liệu không hợp lệ hoặc vi phạm quy tắc nghiệp vụ thường nên xử lý trực tiếp bằng DLT hoặc recovery riêng.

Không retry mọi RuntimeException trong thời gian dài theo thói quen. Một exception không thể phục hồi có thể chiếm dung lượng retry topic, kéo dài thời gian giải quyết và che khuất nguyên nhân thật.

## 9. DLT là chặng kết thúc, không phải thành công nghiệp vụ

Dead-letter topic lưu những record không thể hoàn tất sau chính sách retry hoặc bị loại khỏi retry vì exception không phù hợp. Tên DLT có thể được cấu hình; ví dụ orders-dlt.

Một record trên DLT nên có đủ thông tin điều tra:

- Payload và key, nếu có thể lưu an toàn.
- Event ID hoặc correlation ID nghiệp vụ.
- Original topic, partition và offset.
- Thông tin exception, cause và lỗi ở chặng cuối.
- Số lần xử lý và retry đã thực hiện.
- Timestamp liên quan đến lần xử lý đầu và lần forward gần nhất.

Đưa record vào DLT chỉ có nghĩa record được chuyển sang luồng xử lý lỗi theo chính sách nếu thao tác publish thành công. Nó không có nghĩa OrderCreated đã được xử lý đúng hoặc side effect đã hoàn tất.

DLT cần quy trình vận hành: alert khi có record mới, dashboard theo exception class, công cụ xem lỗi, quy tắc replay có kiểm soát và cách tránh replay vô hạn. Nếu replay một event đã tạo side effect ở lần trước, consumer phải có cơ chế idempotency.

Nếu publish DLT thất bại do quyền, serializer hoặc broker unavailable, không nên âm thầm coi record đã được giải quyết. Cần cấu hình chính sách xử lý lỗi của recoverer/DLT và quan sát rõ kết quả cuối cùng.

## 10. Vì sao non-blocking retry làm thay đổi thứ tự xử lý?

Kafka giữ thứ tự đọc trong một partition, nhưng retry topic là topic khác với log và consumer riêng. Khi record lỗi được forward, topic gốc có thể tiếp tục xử lý record sau. Do đó, thứ tự hoàn tất nghiệp vụ có thể khác thứ tự append ban đầu.

Ví dụ cùng một orderId:

~~~text
orders / partition 0:
  offset 10: OrderCreated  -> lỗi -> chuyển retry
  offset 11: OrderPaid     -> thành công
  offset 12: OrderShipped  -> thành công

orders-retry:
  OrderCreated             -> chờ 30 giây -> thành công

Thứ tự hoàn tất quan sát được:
  OrderPaid -> OrderShipped -> OrderCreated
~~~

Với một nghiệp vụ yêu cầu OrderCreated phải xảy ra trước OrderPaid, thứ tự trên có thể gây sai dữ liệu. Gán cùng key cho các record giúp chúng đi vào cùng partition ở topic gốc, nhưng **không giữ được thứ tự xuyên qua các retry topic**.

Cách xử lý tùy nghiệp vụ:

- Nếu record độc lập, có thể chấp nhận xử lý lệch thứ tự.
- Nếu side effect phải tuần tự, cân nhắc blocking retry ngắn trước khi chuyển vào luồng lỗi.
- Thiết kế consumer kiểm tra version, trạng thái hoặc prerequisite trước khi áp dụng thay đổi.
- Dùng event ID, sequence number hoặc state machine để phát hiện event đến không đúng thứ tự.
- Với yêu cầu nghiêm ngặt hơn, cân nhắc mô hình xử lý riêng bảo đảm thứ tự theo entity.

Không nên bật non-blocking retry cho sự kiện thay đổi số dư, trạng thái đơn hàng hoặc workflow có phụ thuộc thứ tự mà chưa xác định cách giải quyết vấn đề này.

## 11. Offset, acknowledgement và khả năng xử lý trùng

Khi record lỗi được forward sang retry topic, consumer của topic gốc có thể tiến tiếp sau khi framework xử lý lỗi và offset theo cấu hình container. Điều này cho phép tránh giữ mãi record gốc trong luồng chính.

Tuy nhiên, **forward record** và **commit offset của nguồn** là hai hành động cần được điều phối. Nếu ứng dụng crash đúng lúc chuyển tiếp, record có thể được gửi sang retry topic nhưng offset của topic gốc chưa được commit. Sau restart, record gốc có thể được đọc lại và forward thêm lần nữa. Ngược lại, nếu ứng dụng commit quá sớm mà publish chưa thực sự thành công, có nguy cơ mất cơ hội xử lý.

Vì vậy, không được tự suy luận exactly-once end-to-end chỉ vì framework đã chuyển record qua retry topic.

Một kịch bản xử lý trùng:

~~~text
1. Listener gốc xử lý eventId=E123 -> lỗi
2. Recoverer publish E123 sang retry topic
3. Ứng dụng crash trước khi offset nguồn được commit
4. Consumer mới đọc lại event gốc E123
5. E123 được forward lần nữa

Retry topic có thể có hai record cùng eventId=E123.
~~~

Thiết kế bảo vệ nghiệp vụ nên dùng một event ID ổn định qua mọi chặng. Nếu listener cập nhật database, có thể lưu event ID đã xử lý trong cùng database transaction với side effect, rồi bỏ qua lần xử lý lặp. Nếu gọi một API bên ngoài, sử dụng idempotency key nếu dịch vụ đó hỗ trợ.

Thao tác retry cũng có thể thất bại sau khi side effect đã xảy ra nhưng trước khi listener báo thành công. Vì vậy, idempotency cần áp dụng ở bước thực hiện nghiệp vụ, không chỉ tại logic forward record.

## 12. Blocking retry và retry topic khác nhau ở đâu?

| Tiêu chí | Blocking retry | Non-blocking retry topic |
|---|---|---|
| Nơi thử lại | Luồng tiêu thụ của listener/container gốc | Các retry topic được tiêu thụ bằng listener riêng |
| Chờ backoff | Handler giữ tiến trình xử lý record trong container gốc | Retry consumer chờ thời điểm đến hạn trên retry topic |
| Ảnh hưởng topic gốc | Có thể chặn consumer thread và các partition cùng consumer | Topic gốc thường có thể xử lý tiếp |
| Thứ tự nghiệp vụ | Phù hợp hơn khi cần xử lý tuần tự trong partition | Record sau có thể hoàn tất trước record lỗi |
| Chi phí topic | Không cần retry topic riêng | Cần provision, retention, ACL, monitoring cho retry topic |
| Lỗi phù hợp | Lỗi tạm thời có delay ngắn | Lỗi cần delay dài và có thể chấp nhận xử lý không theo thứ tự |
| Quan sát | Retry attempt/backoff trong một consumer flow | Cần truy vết event qua nhiều topic và offset |

Blocking retry đôi khi vẫn hữu ích trước non-blocking retry để thử một số lỗi rất ngắn, nhưng khi kết hợp hai lớp phải tính rõ số lần thử tối đa và thời gian chờ tổng thể. Không cấu hình các lớp retry chồng nhau mà không biết chính xác record sẽ được thử bao nhiêu lần.

Một cách lựa chọn:

- Kết nối database chập chờn vài trăm mili giây: blocking retry ngắn có thể đủ.
- Dịch vụ downstream cần vài phút để phục hồi và các event độc lập: retry topic phù hợp hơn.
- Event yêu cầu thứ tự nghiêm ngặt theo key: cần ưu tiên giải pháp duy trì ordering hoặc thiết kế lại nghiệp vụ.

## 13. Retry topic và cấu hình topic trên cluster

Mỗi topic retry nên được vận hành như một topic quan trọng trong chuỗi reliability. Các tham số cần cân nhắc gồm:

| Nhóm cấu hình | Vì sao quan trọng |
|---|---|
| Partition count | Quyết định khả năng xử lý song song và giới hạn consumer của retry topic |
| Replication factor | Quyết định số bản sao và khả năng chịu lỗi broker |
| min.insync.replicas | Phối hợp với acks=all để kiểm soát mức replication tối thiểu |
| Retention | Phải đủ dài so với thời gian chờ, backlog, outage và yêu cầu điều tra |
| ACL / authentication | Consumer phải đọc được retry/DLT; producer phải ghi được topic đích |
| Serializer / deserializer | Payload phải được chuyển tiếp và đọc lại đúng kiểu |
| Cleanup policy | Cần tránh xóa hoặc compact record không phù hợp trước khi retry |
| Monitoring | Cần phát hiện topic retry tồn đọng và DLT tăng bất thường |

Ví dụ, nếu hệ thống có backoff kéo dài nhiều giờ nhưng retention của retry topic chỉ vài phút, record có thể hết hạn trước khi được xử lý lại. Retention phải tính theo thời gian chờ tối đa cộng khả năng topic bị backlog hoặc consumer downtime.

Đừng mặc định các topic retry có đúng số partition như topic gốc. Hãy kiểm tra topology được tạo và số partition thực tế, nhất là khi forward record cần giữ partition tương ứng. Nếu một recoverer chỉ định partition không tồn tại ở topic đích, publish có thể thất bại. Cấu hình partition, key routing và số consumer phải thống nhất.

Producer dùng để forward record cũng cần cấu hình đủ tin cậy, chẳng hạn acks=all và idempotence khi phù hợp; đồng thời hệ thống phải quan sát lỗi publish. Reliability của retry topology phụ thuộc cả producer chuyển tiếp lẫn consumer xử lý lại.

## 14. Fixed delay, exponential delay và tái sử dụng retry topic

Cùng một số lần retry có thể được tổ chức bằng nhiều topology.

### Fixed delay

Mọi lần retry chờ cùng một khoảng, chẳng hạn 5 giây:

~~~text
Main -> retry 5s -> retry 5s -> retry 5s -> DLT
~~~

Tùy phiên bản và chiến lược cấu hình, Spring Kafka có thể dùng nhiều topic hoặc tái sử dụng một topic cho những lần retry có cùng delay. Tái sử dụng topic giúp giảm số resource, nhưng không loại bỏ nhu cầu quản lý số lần thử và metadata backoff.

### Exponential delay

Khoảng chờ tăng theo từng lần:

~~~text
Main -> retry 1s -> retry 2s -> retry 4s -> retry 8s -> DLT
~~~

Mô hình này giảm tần suất gọi service đang gặp sự cố, nhưng thời gian xử lý cuối cùng có thể lớn. Khi backoff đạt maxDelay, các lần tiếp theo có thể dùng cùng delay. Một số phiên bản Spring Kafka hỗ trợ chiến lược tái sử dụng topic ở khoảng delay tối đa để tránh tạo thêm nhiều topic giống nhau.

Không nên chọn chính sách chỉ dựa vào số lượng topic. Cần xem xét quota Kafka, số consumer, khối lượng event lỗi, delay tối đa, retention và khả năng truy vết.

## 15. Một record mới vào retry topic có thể bị chờ sau record khác

Non-blocking retry không bảo đảm mọi record trên retry topic luôn được xử lý ngay khi đến hạn. Consumer đọc record theo thứ tự offset của từng partition. Nếu record ở đầu partition chưa đến thời điểm retry, partition có thể bị pause. Record khác phía sau dù đã đủ điều kiện cũng phải đợi record đầu được giao theo đúng thứ tự đọc trên partition đó.

Ví dụ:

~~~text
Retry partition P1:

offset 50: event A, due 12:05
offset 51: event B, due 12:03

Tại 12:03:
  A chưa đến hạn.
  Consumer chưa thể tự nhảy qua A để xử lý B.

Khi A đến hạn:
  consumer có thể tiếp tục đọc theo thứ tự partition.
~~~

Điều này có thể xảy ra khi nhiều event được forward với delay khác nhau vào cùng retry partition. Vì vậy, retry topic giúp tránh chặn main topic nhưng vẫn có head-of-line waiting cục bộ bên trong retry topic.

Nếu cần độ trễ retry tương đối dự đoán được ở tải lớn, hãy theo dõi tuổi của record đang chờ, partition lag và số record đến hạn nhưng chưa được xử lý. Cân nhắc chiến lược tách topic theo delay hoặc phân phối partition phù hợp với workload.

## 16. Lỗi serializer và deserializer trong retry topology

Một record có thể thất bại trước khi business listener được gọi, ví dụ deserializer không thể chuyển bytes thành object. Với kiểu lỗi này, cần biết lỗi xảy ra ở tầng Kafka consumer hay bên trong listener.

Một số lưu ý:

- Khi lỗi deserialize xảy ra trước listener, cấu hình ErrorHandlingDeserializer hoặc cơ chế error handler tương ứng có thể cần thiết để framework nhận thông tin lỗi và recovery.
- Retry nhiều lần với cùng bytes không sửa được schema không hợp lệ.
- Producer chuyển tiếp phải hỗ trợ serialize payload phù hợp; trong một số luồng recovery, payload có thể còn ở dạng byte[].
- Nếu retry topic và DLT dùng serializer không tương thích, record có thể không được forward thành công dù business exception đã được xử lý đúng.
- Khi event schema tiến hóa, cả listener topic gốc, retry topic và DLT consumer cần hiểu phiên bản payload đang lưu.

Nên phân loại deserialization, conversion và schema errors thành lỗi cần điều tra hoặc DLT sớm, trừ khi có lý do rõ ràng để tin rằng retry sẽ giúp. Nếu schema registry tạm thời unavailable, cách phân loại có thể khác so với payload thực sự không hợp lệ.

## 17. Giới hạn tích hợp với batch listener và transaction

Non-blocking retry của Spring Kafka có những giới hạn quan trọng cần đối chiếu với phiên bản được sử dụng.

**Batch listener:** Cơ chế retry topic được thiết kế chủ yếu cho record listener. Các phiên bản Spring Kafka thông dụng không hỗ trợ kết hợp non-blocking retry với batch listener theo cách tương đương record listener. Nếu đang dùng batch listener, hãy kiểm tra giới hạn hỗ trợ và chọn batch error handling hoặc thay đổi mô hình xử lý trước khi dùng @RetryableTopic.

**Container transaction:** Non-blocking retry không được kết hợp trực tiếp với Kafka container transactions theo hướng hỗ trợ phổ biến của Spring Kafka. Transactional listener dùng cơ chế rollback/AfterRollbackProcessor riêng. Không nên tự giả định rằng forward sang retry topic và commit offset nguồn đã trở thành một transaction Kafka chỉ vì producer có transaction-id-prefix.

**Đảm bảo với hệ thống ngoài Kafka:** Kafka transaction cũng không tự rollback database, email hoặc API thanh toán. Với side effect bên ngoài, cần idempotency, outbox hoặc cơ chế nhất quán phù hợp.

**Blocking + non-blocking retry:** Có thể cần chính sách kết hợp cho một số tình huống, nhưng phải xác nhận cách triển khai tương thích với phiên bản, tổng attempts, ordering và điểm recovery. Không gắn thêm DefaultErrorHandler có retry dài vào mọi retry listener mà không tính toàn bộ vòng đời record.

## 18. Theo dõi retry topic trong production

Một dashboard đáng tin cậy cần phân biệt hoạt động trên main topic, các retry topic và DLT. Chỉ theo dõi lag của topic gốc có thể tạo cảm giác hệ thống đã xử lý xong trong khi nhiều record vẫn chờ trên retry topic.

Các chỉ số hữu ích:

- Số record thất bại từ topic gốc và được forward sang retry topic.
- Publish success/error rate của retry publisher.
- Consumer lag theo từng retry topic và từng partition.
- Thời gian thực tế từ failure đầu đến retry.
- Tuổi của record lâu nhất đang chờ.
- Tỷ lệ thành công ở mỗi retry attempt.
- Số record đi vào DLT và nguyên nhân.
- Lỗi DLT handler hoặc DLT publisher.
- Rebalance count, consumer uptime và số partition bị pause.
- Retry topic bytes, retention pressure và dung lượng lưu trữ.

Với mỗi event, log nên có event ID, original topic/partition/offset, current topic/partition/offset, attempt, exception category và correlation ID. Không nên dùng event ID hoặc offset làm metric label vì cardinality có thể rất lớn.

Ví dụ khi cần điều tra:

~~~text
eventId=E123
original=orders-2@410
current=orders-retry-2000-2@24
attempt=3
error=TemporaryPaymentException
nextAction=retry
~~~

Định dạng log trên là minh họa do ứng dụng tạo; không phải định dạng mặc định của framework.

Khi DLT tăng đột ngột, cần kiểm tra exception distribution và trạng thái downstream trước khi replay hàng loạt. Replay tất cả record trong lúc dependency vẫn lỗi có thể tạo một vòng retry mới, tăng tải Kafka và gây áp lực lên chính service đang phục hồi.

## 19. Các tình huống lỗi cần dự liệu

### Retry topic chưa tồn tại hoặc không có quyền ghi

Framework có thể không forward được record. Kiểm tra topic provisioning, broker ACL, cấu hình producer, partition đích và kết quả publish. Nếu sử dụng autoCreateTopics=false, đảm bảo mọi topic trong topology đã được tạo trước khi listener chạy.

### Consumer retry bị dừng trong thời gian dài

Record tiếp tục nằm trong retry topic đến khi được consume hoặc hết retention. Sau khi consumer khởi động lại, các record chưa được xử lý có thể được tiếp tục xử lý nếu chúng vẫn còn trong log. Vì thế retention và lag alert rất quan trọng.

### Dependency đã phục hồi nhưng retry vẫn chậm

Kiểm tra thời điểm backoff, retry partition đang pause, record đầu partition chưa đến hạn, số consumer và backlog. Một record có thể đến hạn nhưng vẫn phải chờ các record trước cùng partition.

### Record bị xử lý hai lần

Kiểm tra original offset commit, publish sang retry topic, crash/rebalance và idempotency của side effect. Retry topic không tự loại bỏ hai lần forward độc lập cùng event ID.

### Record đi thẳng đến DLT

Kiểm tra exception classifier, số attempts còn lại và các chính sách giới hạn thời gian retry. Một exception non-retryable có thể được chuyển sang DLT ngay cả khi chưa sử dụng hết các retry topic.

### Không tìm thấy record trong main topic nhưng nghiệp vụ chưa hoàn tất

Kiểm tra retry topics, DLT và metadata liên kết bằng event ID. Record đã được forward khỏi luồng chính không đồng nghĩa nghiệp vụ đã thành công.

## 20. Kiểm thử toàn bộ hành trình retry

Nên có các bài kiểm thử tích hợp với Kafka test broker hoặc môi trường tương đương để quan sát hành vi qua nhiều topic. Các trường hợp quan trọng gồm:

1. Listener thành công ngay lần đầu: không sinh record trên retry/DLT.
2. Lần đầu lỗi retryable, lần hai thành công: record đi một chặng retry và kết thúc.
3. Lỗi retryable ở mọi lần: record đi đến DLT sau khi hết attempts.
4. Lỗi non-retryable: record không chạy hết chuỗi retry.
5. Delay exponential: thời gian thực tế không sớm hơn thời điểm dự kiến theo chính sách.
6. Consumer retry tạm dừng: record vẫn còn trong retry topic khi chưa hết retention.
7. Publish retry thất bại: hệ thống ghi nhận lỗi và không âm thầm bỏ record.
8. Crash giữa forward và commit nguồn: consumer chịu được việc record xuất hiện lặp.
9. Hai event cùng key: xác nhận thứ tự nghiệp vụ có thể thay đổi khi event trước được retry.
10. DLT handler lỗi: vận hành biết record chưa được xử lý xong.

Trong test, dùng event ID riêng cho từng record và quan sát các topic liên quan. Tránh dùng sleep cố định dài để đo backoff; có thể dùng khoảng delay ngắn cùng timeout và điều kiện chờ có giới hạn. Cần phân biệt sai lệch do scheduler/poll với lỗi chính sách retry.

## 21. Những hiểu nhầm thường gặp

**Retry topic giúp Kafka broker tự xử lý lại record.** Không đúng. Broker lưu record; Spring Kafka retry consumer kiểm tra thời điểm đến hạn rồi gọi lại listener.

**Non-blocking retry có nghĩa không nơi nào phải chờ.** Không đúng. Topic gốc có thể tiếp tục, nhưng consumer của retry topic vẫn phải chờ backoff và có thể pause partition.

**attempts=4 là bốn lần retry sau lần đầu.** Không đúng. attempts thường bao gồm lần xử lý ban đầu; giá trị 4 nghĩa là tối đa bốn lần xử lý.

**Record giữ nguyên offset khi chuyển sang retry topic.** Không đúng. Mỗi topic có log và offset riêng. Dùng original metadata hoặc event ID để truy vết.

**Cùng key bảo đảm giữ thứ tự sau khi chuyển retry topic.** Không đúng. Retry topic và topic gốc có consumer, offset và lịch xử lý riêng.

**Đã forward sang retry topic là dữ liệu chắc chắn được xử lý đúng một lần.** Không đúng. Publish và commit nguồn có điểm lỗi; retry có thể gây side effect lặp. Cần chính sách commit và idempotency.

**Record vào DLT nghĩa là quy trình nghiệp vụ hoàn tất.** Không đúng. Nó chỉ được đưa vào luồng lỗi để xử lý hoặc điều tra tiếp.

**Tăng số retry topic luôn giúp xử lý nhanh hơn.** Không đúng. Nó tăng resource và độ phức tạp; throughput vẫn phụ thuộc số partition, consumer và downstream capacity.

**Delay 1 giây bảo đảm retry chính xác sau 1 giây.** Không đúng. Đây là thời điểm sớm nhất theo chính sách; thời điểm thực tế còn phụ thuộc consumer và cluster.

**Có thể dùng non-blocking retry cho mọi batch hoặc transactional listener.** Không đúng. Phải kiểm tra các giới hạn hỗ trợ của Spring Kafka; cơ chế batch và transaction có semantics riêng.

## 22. Hướng dẫn thiết kế retry topic

Khi tạo non-blocking retry cho một listener mới, trước tiên xác định exception nào thực sự có thể phục hồi và liệu nghiệp vụ có chấp nhận xử lý không theo thứ tự hay không.

Một quy trình triển khai:

1. Xác định lỗi retryable và non-retryable dựa trên hành vi dependency, schema và nghiệp vụ.
2. Chọn attempts và backoff theo thời gian phục hồi dự kiến, tránh retry vô hạn.
3. Đánh giá tác động đến thứ tự record, đặc biệt với các event cùng entity key.
4. Dùng @RetryableTopic hoặc RetryTopicConfigurationBuilder để mô tả topology.
5. Provision các retry topic và DLT với partition, replication, retention, ACL và serializer phù hợp.
6. Kiểm soát cách forward record, quan sát lỗi publish và offset nguồn.
7. Dùng event ID ổn định và thiết kế side effect idempotent ở mọi retry attempt.
8. Theo dõi lag của retry topic và DLT, không chỉ lag của main topic.
9. Thiết lập alert, quy trình xem lỗi và replay từ DLT có kiểm soát.
10. Kiểm thử retry thành công, hết attempts, DLT failure, consumer downtime, crash và thay đổi thứ tự.

Retry topic là một cách tách thời gian chờ phục hồi khỏi luồng xử lý chính. Nó cho phép main consumer tiếp tục nhận record trong khi record lỗi được xử lý ở một chuỗi topic riêng theo backoff. Để vận hành tin cậy, cần hiểu đầy đủ cả topology, thời điểm retry, offset, thứ tự, publish failure và idempotency; chỉ thêm @RetryableTopic mà không quản lý các yếu tố này thì chưa đủ để bảo đảm kết quả nghiệp vụ.
