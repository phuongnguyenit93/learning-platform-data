# Topic naming

Trong Spring Kafka, **non-blocking retry** đưa record bị lỗi sang một hoặc nhiều retry topic, trì hoãn việc xử lý rồi thử lại ở các listener tương ứng. Khi đã hết số lần thử, record thường được chuyển sang **dead-letter topic (DLT)**. Vì mỗi bước có thể tương ứng với một Kafka topic vật lý, cách đặt tên topic là một phần của thiết kế vận hành: tên phải thể hiện được luồng dữ liệu, không xung đột với ứng dụng khác, dễ quan sát và có thể quản lý bằng hạ tầng tự động.

Spring Kafka cung cấp quy ước tên mặc định và các tùy chọn để thay đổi suffix, chiến lược thêm độ trễ hoặc chỉ số vào tên, cũng như tùy biến sâu hơn khi cần. Chủ đề này tập trung vào **topic naming** trong non-blocking retry, từ cách hình thành tên đến các quyết định khi triển khai production.

## 1. Tên topic nằm ở đâu trong luồng non-blocking retry?

Giả sử hệ thống đọc sự kiện đơn hàng từ topic `orders.created`. Khi xử lý thất bại vì một dịch vụ phụ thuộc chưa sẵn sàng, Spring Kafka có thể chuyển record sang retry topic có khoảng trì hoãn. Nếu sau các lần thử vẫn thất bại, record được chuyển tới DLT:

```text
orders.created
     |
     | listener thất bại
     v
orders.created-retry-1000
     |
     | thử lại sau khoảng 1 giây, vẫn lỗi
     v
orders.created-retry-2000
     |
     | thử lại sau khoảng 2 giây, vẫn lỗi
     v
orders.created-retry-4000
     |
     | thử lại sau khoảng 4 giây, vẫn lỗi
     v
orders.created-dlt
```

Các tên và khoảng chờ ở sơ đồ là **ví dụ minh họa** cho một cấu hình có nhiều độ trễ. Danh sách topic vật lý thực tế phụ thuộc vào `attempts`, chính sách backoff, chiến lược đặt suffix, khả năng tái sử dụng topic cùng delay và phiên bản Spring Kafka.

Các thành phần cần phân biệt:

| Thành phần | Vai trò | Ví dụ tên |
|---|---|---|
| Main topic | Nguồn nhận sự kiện ban đầu | `orders.created` |
| Retry topic | Giữ record để xử lý lại theo một khoảng delay | `orders.created-retry-1000` |
| Retry topic khác | Một mức chờ hoặc một lần thử khác | `orders.created-retry-2000` |
| DLT | Cách ly record không được phục hồi sau khi hết retry | `orders.created-dlt` |

Retry topic và DLT là những topic Kafka thực sự. Chúng có partition, replication factor, retention, ACL, metric và chi phí lưu trữ riêng. Đổi cách đặt tên có thể tạo ra topic mới, ảnh hưởng đến topology đang hoạt động và cách ứng dụng quan sát hoặc replay record.

## 2. Quy ước tên mặc định của Spring Kafka

Khi cấu hình `@RetryableTopic`, Spring Kafka thường lấy **tên main topic** làm gốc và nối thêm suffix cho các topic phụ trợ:

- Retry topic dùng suffix mặc định `-retry`.
- Dead-letter topic dùng suffix mặc định `-dlt`.
- Retry topic có thể được bổ sung giá trị delay hoặc index để phân biệt những đích retry khác nhau.

Với main topic `payments.requested`, một nhóm tên có thể là:

```text
payments.requested
payments.requested-retry-1000
payments.requested-retry-2000
payments.requested-retry-4000
payments.requested-dlt
```

Tên gốc giúp người vận hành nhanh chóng nhận ra các topic thuộc cùng một luồng. Phần `-retry` cho biết record chưa được xử lý thành công và đang được thử lại; phần `-dlt` thể hiện record đã đi vào tuyến xử lý lỗi cuối cùng.

Điều quan trọng là **không dự đoán topology chỉ từ suffix**. Khi cấu hình thay đổi, có thể có ít retry topic hơn số lần thử, nhất là khi nhiều lần thử dùng cùng khoảng delay và được gộp vào một topic. Muốn biết tên chính xác, hãy kiểm tra cấu hình Spring Kafka và các topic thực sự có trong cluster.

## 3. Đặt suffix qua @RetryableTopic

`@RetryableTopic` cho phép thay đổi suffix của retry topic và DLT bằng `retryTopicSuffix` và `dltTopicSuffix`.

Ví dụ:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;

@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
                delay = 1_000,
                multiplier = 2.0,
                maxDelay = 4_000),
        retryTopicSuffix = "-processing-retry",
        dltTopicSuffix = "-processing-dlt")
@KafkaListener(
        topics = "orders.created",
        groupId = "order-processor")
public void handle(OrderCreated event) {
    orderService.process(event);
}
```

Trong ví dụ, phần tên gốc vẫn là `orders.created`, nhưng retry topic sử dụng suffix `-processing-retry`, còn DLT là `orders.created-processing-dlt`. Nếu cấu hình dùng suffix theo delay, một retry topic có thể có tên như `orders.created-processing-retry-1000`.

`attempts = "4"` có nghĩa là **tối đa bốn lần xử lý, bao gồm lần đầu**; khi toàn bộ các lần xử lý thất bại, record sẽ được chuyển sang DLT theo chiến lược được cấu hình. Độ trễ tăng dần có thể tạo các mức khoảng chờ khác nhau cho ba lần retry.

Các kiểu `OrderCreated` và `orderService` là thành phần nghiệp vụ minh họa. Ứng dụng thực tế cần cấu hình deserializer, serializer, Kafka listener container và hạ tầng topic phù hợp.

### Khi nào nên đổi suffix?

Nên cân nhắc suffix riêng khi nhiều pipeline độc lập cùng tiêu thụ một main topic, khi tổ chức có quy chuẩn tên topic, hoặc khi cần tránh trùng với những topic vận hành sẵn có.

Ví dụ, hai consumer group cùng đọc `orders.created` nhưng chạy hai nghiệp vụ khác nhau:

```text
orders.created
    |
    +-- inventory-service
    |     orders.created-inventory-retry-1000
    |     orders.created-inventory-dlt
    |
    +-- billing-service
          orders.created-billing-retry-1000
          orders.created-billing-dlt
```

Nếu cả hai pipeline dùng tên retry/DLT giống nhau, chúng có nguy cơ chia sẻ topic vật lý không chủ đích. Các consumer group khác nhau có offset riêng nhưng vẫn đọc dữ liệu từ cùng topic; vì vậy một pipeline có thể nhìn thấy record retry của pipeline kia. Suffix riêng làm rõ quyền sở hữu dữ liệu và giảm nguy cơ xử lý nhầm.

## 4. TopicSuffixingStrategy: suffix theo delay hay theo index?

Khi nhiều retry destination được tạo, cần một phần tên bổ sung để phân biệt chúng. Spring Kafka có `TopicSuffixingStrategy` để lựa chọn cách thêm suffix theo **giá trị delay** hoặc **index**.

| Chiến lược | Ý nghĩa | Tên minh họa |
|---|---|---|
| `SUFFIX_WITH_DELAY_VALUE` | Dùng thời gian delay để phân biệt retry destination | `orders-retry-1000`, `orders-retry-2000` |
| `SUFFIX_WITH_INDEX_VALUE` | Dùng chỉ số cho những retry destination | `orders-retry-0`, `orders-retry-1` |

Số index và tập topic thực tế còn phụ thuộc cách Spring Kafka xây dựng retry topology cho phiên bản và chính sách topic reuse đang dùng; các tên trong bảng chỉ minh họa hình dạng.

### 4.1. Suffix theo giá trị delay

Tên dạng `orders-retry-1000` giúp người vận hành nhìn thấy ngay delay được cấu hình tính bằng millisecond. Đây là lựa chọn thuận tiện khi mỗi tầng retry có khoảng chờ khác nhau.

Ưu điểm:

- Tên topic phản ánh khoảng thời gian retry.
- Dễ liên hệ giữa cấu hình backoff và topic trong dashboard.
- Phù hợp với exponential backoff có các mức chờ khác nhau.

Hạn chế:

- Đổi delay có thể đổi tên topic vật lý.
- Nhiều lần retry có cùng delay cần quy tắc reuse hoặc phân biệt tên thích hợp.
- Tên topic phản ánh cấu hình delay, không bảo đảm record sẽ được xử lý chính xác đúng từng millisecond; thời điểm thực tế còn phụ thuộc consumer scheduling, poll và tải hệ thống.

### 4.2. Suffix theo index

Tên dạng `orders-retry-0` hoặc `orders-retry-1` thể hiện thứ tự của destination thay vì phơi bày giá trị delay.

Ưu điểm:

- Tên gọn hơn khi delay dài hoặc cấu hình có nhiều mức chờ.
- Tách ý nghĩa định danh topic khỏi con số delay trong tên.
- Thuận tiện khi chính sách vận hành chỉ cần phân biệt từng tầng retry.

Hạn chế:

- Cần xem cấu hình để biết một index tương ứng delay nào.
- Đổi số tầng retry hoặc chiến lược reuse có thể làm thay đổi ý nghĩa các index.
- Không thể giả định rằng index là số lần listener đã được gọi nếu nhiều attempt được gộp vào cùng một retry topic.

Tùy phiên bản Spring Kafka, chiến lược này được cấu hình qua thuộc tính annotation hoặc builder của retry topic configuration. Khi vận hành hệ thống dùng phiên bản cụ thể, kiểm tra API `TopicSuffixingStrategy` được hỗ trợ trước khi thay đổi topology.

## 5. Quan hệ giữa backoff và số retry topic

Tên retry topic không chỉ phụ thuộc `retryTopicSuffix`. Nó còn phụ thuộc số lần thử, delay và chiến lược dùng lại topic.

Ví dụ, với một retry ban đầu sau 1 giây, lần tiếp theo sau 2 giây, lần tiếp theo sau 4 giây, Spring Kafka có thể tạo ba retry destination riêng. Với **fixed backoff** mà mọi lần retry đều chờ 1 giây, một số cấu hình/phiên bản cho phép **reuse cùng một retry topic** cho các attempt có cùng delay.

So sánh về mặt ý tưởng:

```text
Exponential backoff:
main -> retry-1000 -> retry-2000 -> retry-4000 -> dlt

Fixed backoff, các retry destination tách riêng:
main -> retry-0 -> retry-1 -> retry-2 -> dlt

Fixed backoff, reuse topic cùng delay:
main -> retry-1000 -> retry-1000 -> retry-1000 -> dlt
                    (cùng một topic vật lý)
```

Sơ đồ cuối thể hiện luồng logic quay lại cùng retry topic; Kafka không tạo ba bản sao của topic chỉ vì topic được xuất hiện ba lần trong sơ đồ.

Chính sách tái sử dụng retry topic với cùng delay có thể khác nhau theo phiên bản Spring Kafka. Vì vậy, không nên cam kết số topic chỉ dựa trên số attempts. Khi lập tài liệu hạ tầng, hãy dùng **tên topic đã được tạo hoặc cấu hình topic definition thực tế** để làm nguồn xác nhận.

## 6. Đặt tên DLT và định tuyến theo loại exception

DLT thường có suffix `-dlt`. Nó giữ record mà ứng dụng không xử lý thành công qua đường retry thông thường. Tên DLT cần làm rõ main topic và luồng nghiệp vụ sở hữu nó.

Ví dụ:

```text
invoices.issued                  # main
invoices.issued-retry-1000       # retry
invoices.issued-retry-5000       # retry
invoices.issued-dlt              # dead letter
```

Trong một số thiết kế, cần phân tuyến DLT theo loại lỗi:

```text
invoices.issued-dlt-validation
invoices.issued-dlt-downstream
invoices.issued-dlt
```

Các tên trên là quy ước thiết kế, **không tự động được Spring Kafka tạo ra chỉ vì exception thuộc loại tương ứng**. Muốn phân tuyến nhiều DLT, cần cấu hình routing rules hoặc destination resolver phù hợp với phiên bản Spring Kafka. Khi không có cấu hình đó, nên coi `-dlt` là đích mặc định.

Khi thiết kế nhiều DLT, cần quyết định rõ mỗi loại lỗi được lưu ở đâu, retention bao lâu, ai sở hữu quy trình sửa lỗi và replay ra sao. Phân nhỏ DLT có thể giúp phân quyền và xử lý, nhưng cũng tăng số topic, ACL, dashboard và runbook phải quản lý.

## 7. Naming và consumer group ID là hai lớp khác nhau

Tên topic là tài nguyên vật lý của Kafka cluster. Consumer group ID xác định offset và phân chia partition giữa những consumer cùng group.

Ví dụ:

```text
Topic: orders.created-processing-retry-1000
  group A: có offset riêng
  group B: có offset riêng
```

Nếu hai listener dùng hai consumer group khác nhau nhưng subscribe cùng retry topic, **cả hai group đều có thể nhận record đó**. Đổi group ID không làm retry topic trở thành topic riêng tư của một pipeline.

Spring Kafka thường tạo container cho retry topic và DLT từ listener gốc, đồng thời áp dụng quy tắc group ID cho các container liên quan. Tuy nhiên, đây là cơ chế group membership; nó không thay thế việc cấp tên topic duy nhất giữa các pipeline.

Trong kiến trúc nhiều service hoặc nhiều consumer group trên cùng một main topic, hãy đặt retry/DLT suffix có nhận diện service hoặc nghiệp vụ. Tránh để hai pipeline độc lập vô tình dùng chung một đường retry vật lý.

## 8. Tên topic và giới hạn của Kafka

Kafka topic name có giới hạn độ dài và ký tự hợp lệ. Các ký tự an toàn, phổ biến gồm chữ cái Latin, chữ số, dấu chấm (`.`), gạch nối (`-`) và gạch dưới (`_`). Kafka thường giới hạn tên topic tối đa 249 ký tự.

Do Spring Kafka **nối thêm suffix** vào main topic, một tên main topic gần sát giới hạn có thể trở nên không hợp lệ khi được thêm `-retry-<delay>` hoặc `-dlt`.

Ví dụ:

```text
Tên gốc:
  commerce.orders.fulfillment.events.v2

Tên retry:
  commerce.orders.fulfillment.events.v2-retry-16000

Tên DLT:
  commerce.orders.fulfillment.events.v2-dlt
```

Giữ phần nhận diện cần thiết trong tên, nhưng không dùng tên quá dài chỉ để đưa mọi metadata vào tên topic. Các thông tin thay đổi thường xuyên như timestamp deploy, build number hay pod ID nên nằm trong cấu hình, labels, metrics hoặc headers thay vì nằm trong tên retry topic.

Vì dấu chấm và gạch dưới có thể dẫn tới cách chuẩn hóa tên metric tương tự nhau ở Kafka, nên dùng một quy ước nhất quán cho toàn bộ cluster để tránh nhầm lẫn trong monitoring.

## 9. Đặt tên theo môi trường và ownership

Trong cluster dùng chung, topic có thể cần tiền tố môi trường hoặc domain để tránh va chạm:

```text
dev.orders.created
dev.orders.created-retry-1000
dev.orders.created-dlt

staging.orders.created
staging.orders.created-retry-1000
staging.orders.created-dlt

prod.orders.created
prod.orders.created-retry-1000
prod.orders.created-dlt
```

Nếu mỗi môi trường đã dùng cluster riêng, có thể không cần đưa tên môi trường vào topic. Điều quan trọng là một quy tắc nhất quán với kiến trúc triển khai, cách cấp ACL, IaC và dashboard.

Topic naming nên trả lời được:

- Topic thuộc domain/service nào?
- Topic là main, retry hay DLT?
- Retry topic thuộc pipeline/consumer group nào nếu nhiều pipeline dùng chung main topic?
- Suffix có cần phản ánh delay hoặc index không?
- Ai có quyền tạo topic, publish, consume và replay?

Không đặt version của ứng dụng vào suffix ở mỗi lần deploy. Nếu mỗi release tạo bộ retry topic mới, record còn tồn trong bộ topic cũ có nguy cơ không được consumer mới theo dõi. Khi cần version topology, cần có kế hoạch chuyển đổi và drain rõ ràng.

## 10. Cấu hình tạo topic tự động và topic có sẵn

Trong môi trường local hoặc thử nghiệm, Spring Kafka có thể hỗ trợ tạo retry/DLT topic theo cấu hình. Trong production, nhiều hệ thống yêu cầu topic được tạo qua Terraform, GitOps, Kafka operator hoặc quy trình quản trị cluster.

Ví dụ tắt việc tự tạo topic từ annotation:

```java
@RetryableTopic(
        attempts = "4",
        retryTopicSuffix = "-retry",
        dltTopicSuffix = "-dlt",
        autoCreateTopics = "false")
@KafkaListener(topics = "orders.created")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
```

Khi `autoCreateTopics = "false"`, ứng dụng **không được giả định** mọi retry/DLT topic đã tồn tại. Bộ topic phải được cấp phát trước với số partition, replication factor, retention và ACL phù hợp; nếu không, publish retry có thể thất bại hoặc consumer không được giao partition như dự kiến.

Các yếu tố cần khai báo khi tạo topic bằng hạ tầng:

| Thuộc tính | Vì sao cần chú ý |
|---|---|
| Tên topic | Phải khớp chính xác tên Spring Kafka xây dựng. |
| Partition count | Đủ cho routing/recovery và khả năng song song của listener retry. |
| Replication factor | Phù hợp mục tiêu durability và số broker. |
| Retention | Đủ giữ record trong thời gian chờ retry, điều tra và replay. |
| ACL | Producer được ghi retry/DLT; consumer được đọc topic tương ứng. |
| Quota/monitoring | Có thể nhìn thấy lượng ghi, lag và lỗi của retry/DLT. |

Trong các cấu hình recovery giữ nguyên partition từ record nguồn, retry/DLT topic cần có partition đích tương ứng. Nếu partition đích không tồn tại, thao tác publish có thể lỗi. Nên quy hoạch partition của retry/DLT tương thích với main topic và với cách `DeadLetterPublishingRecoverer` chọn partition.

## 11. Đổi topic naming khi hệ thống đang chạy

Đổi `retryTopicSuffix`, `dltTopicSuffix`, `TopicSuffixingStrategy`, hoặc số mức delay có thể làm **đổi tên topic vật lý**. Đây là thay đổi topology cần triển khai có kế hoạch.

Ví dụ ban đầu:

```text
orders.created-retry-1000
orders.created-retry-2000
orders.created-dlt
```

Sau khi chuyển sang suffix riêng cho service:

```text
orders.created-fulfillment-retry-1000
orders.created-fulfillment-retry-2000
orders.created-fulfillment-dlt
```

Record trong bộ retry topic cũ không tự chuyển sang bộ mới. Nếu ứng dụng mới chỉ subscribe tên mới, record đang chờ ở topic cũ có thể bị bỏ lại cho đến khi có consumer xử lý hoặc có quy trình replay.

Khi đổi tên, nên:

1. Kiểm kê main/retry/DLT topic hiện có và số record/lag còn lại.
2. Khai báo trước topic mới với partition, ACL, retention và monitoring phù hợp.
3. Xác định cách xử lý record đang nằm ở topic cũ: drain, tiếp tục chạy listener cũ trong giai đoạn chuyển tiếp hoặc replay có kiểm soát.
4. Triển khai listener cấu hình mới theo quy trình rollout có thể quan sát được.
5. Xác nhận luồng lỗi được publish vào đúng retry topic và DLT mới.
6. Chỉ xóa topic cũ sau khi đã xử lý record tồn và đáp ứng chính sách lưu trữ.

Nếu rollback release, ứng dụng cũ có thể không consume những retry topic vừa được phiên bản mới tạo. Hãy đưa khả năng rollback vào kế hoạch đổi tên ngay từ đầu.

## 12. Topic naming ảnh hưởng tới metrics và runbook

Tên nhất quán giúp nhận diện lỗi nhanh từ dashboard:

```text
Topic                                Records in    Lag
orders.created                       cao           thấp
orders.created-retry-1000            tăng          thấp
orders.created-retry-2000            tăng          tăng
orders.created-dlt                   tăng          tùy consumer DLT
```

Các con số trong sơ đồ chỉ thể hiện xu hướng. Khi retry topic có records-in tăng nhanh hoặc DLT liên tục nhận record mới, đó có thể là tín hiệu dependency đang lỗi, dữ liệu không hợp lệ hoặc một bản deploy gây lỗi logic.

Một dashboard vận hành nên nhóm:

- Main topic, các retry topic và DLT của cùng pipeline.
- Records/bytes vào từng retry topic theo thời gian.
- Consumer lag của listener retry và DLT theo partition.
- Tỷ lệ record quay lại xử lý thành công và record vào DLT.
- Lỗi publish retry/DLT, lỗi deserialize và lỗi authorization.
- Thời gian record ở trạng thái retry trước khi thành công hoặc được cách ly.

Không suy ra retry thực tế chỉ từ hậu tố `1000` hoặc `2000`. Suffix thể hiện **giá trị delay cấu hình**, còn thời gian hoàn tất thực tế có thể lâu hơn khi consumer đang bận, topic có lag hoặc broker gặp sự cố.

Runbook nên ghi chính xác tên retry/DLT mà hệ thống sở hữu, mô tả lý do tạo từng tầng, nơi tra cứu lỗi và quy trình replay. Khi nhiều ứng dụng chia sẻ Kafka cluster, naming convention còn giúp giới hạn quyền ACL và tránh thao tác nhầm topic.

## 13. Thử nghiệm để xác nhận tên topic

Có thể dùng Embedded Kafka hoặc Kafka Testcontainers để kiểm tra topology mà `@RetryableTopic` tạo ra. Các kiểm thử nên tập trung vào **record đi đúng topic** thay vì chỉ kiểm tra tên được dự đoán từ annotation.

Kịch bản tích hợp đề xuất:

1. Khởi động ứng dụng với `@RetryableTopic` và bộ topic dự kiến.
2. Liệt kê topic thực tế qua Kafka AdminClient hoặc công cụ quản trị cluster.
3. Gửi một record mà listener cố tình ném exception có thể retry.
4. Xác nhận record xuất hiện ở retry destination đúng theo cấu hình.
5. Cho các lần retry tiếp tục thất bại và xác nhận record đi tới DLT mong đợi.
6. Kiểm tra key, value, headers và metadata nguồn cần thiết được giữ lại.
7. Nếu nhiều pipeline dùng cùng main topic, xác nhận record lỗi của pipeline này không xuất hiện trong retry/DLT của pipeline khác.
8. Nếu tắt auto-create, chạy test khi thiếu retry topic để thấy hành vi lỗi và bảo đảm quy trình cấp topic hạ tầng phát hiện thiếu sót.

Với một cluster đã có Kafka command-line tools, có thể liệt kê topic:

```bash
kafka-topics.sh --bootstrap-server localhost:9092 --list
```

Không hard-code danh sách retry topic vào nhiều vị trí độc lập trong source code, test và IaC rồi để chúng lệch nhau. Hãy duy trì một quy ước naming có thể kiểm tra được, đồng bộ giữa cấu hình ứng dụng và hạ tầng.

## 14. Những sai lầm thường gặp

- **Hai pipeline dùng chung retry topic ngoài ý muốn:** khác consumer group không có nghĩa dữ liệu được tách ở mức topic vật lý.
- **Giả định luôn có một topic cho mỗi retry:** cách dùng lại topic cùng delay có thể làm số topic ít hơn số lần thử.
- **Nhìn suffix delay và cho rằng đó là thời điểm xử lý chính xác:** lịch retry thực tế còn phụ thuộc consumer scheduling, lag và tài nguyên.
- **Đổi suffix khi rollout mà không xử lý topic cũ:** record đang chờ retry có thể bị bỏ lại.
- **Chỉ tạo main topic trong IaC:** ứng dụng vẫn cần retry/DLT topic có tên và quyền truy cập chính xác.
- **Tạo retry topic có ít partition hơn routing cần dùng:** publish record vào partition không tồn tại có thể thất bại.
- **Dùng tên quá dài:** thêm delay/index và DLT suffix có thể vượt giới hạn Kafka.
- **Chèn pod ID hoặc build ID vào tên:** mỗi lần deploy tạo thêm topic và khiến luồng retry tồn đọng khó quản lý.
- **Dùng DLT chung cho mọi lỗi mà không có ownership:** khó xác định ai chịu trách nhiệm điều tra và replay.
- **Nhầm tên retry topic với group ID:** tên topic xác định nơi lưu record, còn group ID xác định offset và assignment của consumer.

## 15. Lựa chọn quy ước tên cho production

Một quy ước thực tế là lấy main topic làm gốc, gắn thêm nhận diện pipeline nếu có nhiều luồng độc lập, rồi dùng một suffix nhất quán cho retry và DLT:

```text
<main-topic>[-<pipeline>]-retry[-<delay-or-index>]
<main-topic>[-<pipeline>]-dlt
```

Đây là **quy ước thiết kế**, không phải một cú pháp bắt buộc của Kafka. Phần `<pipeline>` có thể bỏ qua nếu mỗi main topic chỉ có một pipeline retry và tổ chức đã xác định ownership rõ ràng.

| Bối cảnh | Hướng chọn naming |
|---|---|
Một service xử lý một main topic | Giữ mặc định `-retry` / `-dlt` để đơn giản. |
Nhiều service cùng subscribe một main topic | Bổ sung suffix nhận diện service hoặc nghiệp vụ cho retry/DLT. |
Exponential backoff có delay khác nhau | Suffix theo delay giúp nhìn rõ lịch chờ trên dashboard. |
Muốn tách tên topic khỏi giá trị delay | Cân nhắc chiến lược suffix theo index, xác minh tính tương thích theo phiên bản. |
Cluster quản lý topic bằng IaC | Tắt auto-create nếu chính sách yêu cầu; định nghĩa đầy đủ retry/DLT topic trước rollout. |
Đang đổi cấu hình retry của hệ thống có dữ liệu | Lập kế hoạch drain/migration và rollback cho những topic cũ. |

Khi thiết kế **topic naming** cho non-blocking retry, hãy xem tên topic như một phần của hợp đồng vận hành. Một tên tốt giúp nhận biết record đang ở bước nào, pipeline nào sở hữu nó và phải điều tra ở đâu. Khi phối hợp đúng suffix, delay/index strategy, topic provisioning và kế hoạch migration, hệ thống Spring Kafka có thể retry rõ ràng, giám sát dễ dàng và hạn chế thất lạc record trong những lần thay đổi cấu hình.
