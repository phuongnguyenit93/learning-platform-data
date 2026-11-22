# Tách batch thành công việc nhỏ

Một batch lớn thường giúp giảm chi phí gọi hàm, truy vấn cơ sở dữ liệu hoặc gửi dữ liệu qua mạng. Nhưng nếu xử lý toàn bộ batch như một đơn vị duy nhất, một bản ghi chậm có thể giữ lại cả lô, lỗi ở cuối lô có thể khiến phần đã làm phải chạy lại, và bộ nhớ tăng theo kích thước đầu vào.

Trong ứng dụng Spring Kafka, ta có thể chia batch thành các phần nhỏ (*chunk*) có kích thước giới hạn. Mỗi chunk trở thành một đơn vị xử lý vừa đủ để kiểm soát thời gian, bộ nhớ và khả năng thử lại. Muốn chia đúng, trước hết cần xác định batch đang tồn tại ở tầng nào.

## 1. Phân biệt các loại batch

Từ “batch” trong Kafka thường chỉ nhiều cơ chế khác nhau. Chúng có liên quan nhưng không thay thế cho nhau.

| Tầng | Batch có nghĩa là gì? | Tham số hoặc cơ chế liên quan |
|---|---|---|
| Producer Kafka | Các record được gom thành một lô gửi đến broker theo partition | `batch.size`, `linger.ms` |
| Consumer poll | Các record được trả về trong một lần gọi `poll()` | `max.poll.records`, các giới hạn fetch theo byte |
| Spring Kafka listener | Listener nhận từng record hoặc nhận cả danh sách record của một poll | `setBatchListener(true)`, `@KafkaListener` |
| Xử lý nghiệp vụ | Ứng dụng gom nhiều record thành một đơn vị công việc nhỏ hơn | Kích thước chunk do ứng dụng quy định |
| Batch logic của hệ thống nguồn | Một yêu cầu nghiệp vụ lớn được chia thành nhiều thông điệp Kafka | `batchId`, `chunkIndex`, `chunkCount` nếu cần theo dõi |

Ví dụ, producer có thể gửi 1.000 event. Kafka gom các record thành các lô truyền tải theo partition. Consumer có thể nhận tối đa 500 record trong một poll. Listener lại chia 500 record đó thành 5 chunk, mỗi chunk 100 record để ghi vào cơ sở dữ liệu.

Các con số trên chỉ minh họa cách phối hợp giữa các tầng. `batch.size` không phải kích thước chunk nghiệp vụ; `max.poll.records` cũng không tự chia danh sách mà listener nhận được thành các phần nhỏ.

## 2. Khi nào nên tách batch?

Tách batch có ích khi kích thước công việc hiện tại vượt quá giới hạn thực tế của một thành phần xử lý:

- Một lần ghi cơ sở dữ liệu quá nhiều dòng làm transaction kéo dài hoặc giữ nhiều lock.
- Một batch chiếm nhiều heap do mỗi record cần được deserialize, ánh xạ và giữ thêm dữ liệu trung gian.
- Dịch vụ phía sau có giới hạn số phần tử trong một request hoặc giới hạn tốc độ nhận dữ liệu.
- Thời gian xử lý một poll batch tiến gần đến `max.poll.interval.ms`, làm consumer có nguy cơ bị xem là không còn hoạt động.
- Khi một phần tử lỗi, hệ thống cần xác định rõ phần công việc nào phải thử lại.

Không nên chia quá nhỏ chỉ vì có thể chia. Mỗi chunk đều có chi phí điều phối, gọi service, mở transaction hoặc gửi request. Chunk quá nhỏ có thể làm giảm hiệu suất tổng thể. Hãy chọn kích thước dựa trên thời gian xử lý, giới hạn của downstream và số liệu đo được.

Một điểm quan trọng: chia một danh sách sau khi consumer đã nhận và deserialize nó chỉ giới hạn đơn vị xử lý trong ứng dụng. Cách này không làm một Kafka record quá lớn trở nên nhỏ hơn khi truyền qua broker. Nếu một record đang chứa cả một mảng dữ liệu khổng lồ, cần chia dữ liệu ở producer thành nhiều record trước khi gửi.

## 3. Chọn ranh giới và kích thước chunk

Một chunk tốt có ranh giới rõ ràng và có thể xử lý lại an toàn. Khi thiết kế, hãy xem xét các yếu tố sau.

**Giới hạn của hệ thống nhận dữ liệu.** Nếu cơ sở dữ liệu hoặc API chỉ xử lý ổn định một số lượng phần tử nhất định trong một request, kích thước chunk phải nằm trong giới hạn đó. Với thao tác ghi hàng loạt, cần cân bằng số dòng mỗi lần ghi với thời gian transaction và lượng lock được giữ.

**Thời gian xử lý.** Listener phải hoàn tất công việc của poll hiện tại và quay lại poll trong giới hạn `max.poll.interval.ms`. Nếu xử lý tuần tự nhiều chunk, thời gian cần tính là tổng thời gian của tất cả chunk trong poll, cộng thêm thời gian chuyển đổi dữ liệu và các chi phí khác. Chia thành chunk không tự động làm tổng thời gian này ngắn đi.

**Bộ nhớ.** Ước lượng bộ nhớ theo kích thước record sau deserialize và dữ liệu trung gian, không chỉ theo số byte truyền trên mạng. Một trăm object Java có thể chiếm nhiều bộ nhớ hơn đáng kể so với payload JSON tương ứng.

**Thứ tự.** Kafka bảo đảm thứ tự trong một partition. Nếu các event của cùng một thực thể phải được xử lý theo thứ tự, hãy dùng key ổn định để chúng đi vào cùng partition và xử lý tuần tự theo partition đó. Không giả định rằng nhiều partition có một thứ tự toàn cục.

**Khả năng nhận diện và xử lý trùng.** Một chunk có thể được chạy lại sau lỗi hoặc khi consumer khởi động lại. Mỗi event nên có định danh ổn định, chẳng hạn `eventId` hoặc mã nghiệp vụ duy nhất. Tác vụ ghi dữ liệu nên có tính idempotent: nhận cùng event nhiều lần vẫn cho ra cùng trạng thái cuối cùng.

Có thể bắt đầu với một kích thước nhỏ vừa phải, đo p95/p99 thời gian xử lý và mức sử dụng bộ nhớ, rồi tăng hoặc giảm dần. Không có một giá trị chunk phù hợp cho mọi topic và mọi dịch vụ.

## 4. Chia batch nhận được trong Spring Kafka listener

Spring Kafka hỗ trợ batch listener để một phương thức `@KafkaListener` nhận danh sách record từ một lần poll. Factory cần bật batch listener:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> batchListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.BATCH);

    return factory;
}
```

Sau đó, listener chia danh sách nhận được thành các phần có tối đa `CHUNK_SIZE` record:

```java
@Component
public class OrderBatchListener {

    private static final int CHUNK_SIZE = 200;

    private final OrderService orderService;

    public OrderBatchListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "${app.kafka.topics.orders}",
            containerFactory = "batchListenerFactory")
    public void consume(
            List<ConsumerRecord<String, OrderEvent>> records) {

        for (int start = 0; start < records.size(); start += CHUNK_SIZE) {
            int end = Math.min(start + CHUNK_SIZE, records.size());

            List<ConsumerRecord<String, OrderEvent>> chunk =
                    records.subList(start, end);

            List<OrderEvent> events = chunk.stream()
                    .map(ConsumerRecord::value)
                    .collect(Collectors.toList());

            orderService.processChunk(events);
        }
    }
}
```

Ở ví dụ này, `max.poll.records` giới hạn số record consumer có thể nhận trong một poll, còn `CHUNK_SIZE` giới hạn số event mà `processChunk` xử lý trong một lần gọi. Nếu một poll trả về 450 record và chunk size là 200, listener sẽ xử lý lần lượt các chunk có 200, 200 và 50 record.

`subList` tạo một view trên danh sách ban đầu. Ví dụ trên dùng view ngay trong vòng lặp và xử lý đồng bộ. Nếu cần đưa chunk sang luồng khác hoặc lưu lại sau khi listener kết thúc, hãy tạo bản sao bằng `new ArrayList<>(records.subList(start, end))`; không giữ view của danh sách listener để dùng bất đồng bộ.

`processChunk` có thể ánh xạ event thành entity rồi gọi thao tác ghi hàng loạt. Nếu mỗi chunk cần một transaction cơ sở dữ liệu riêng, hãy đặt ranh giới transaction trong service tương ứng. Transaction Kafka không tự làm cho thao tác ghi vào cơ sở dữ liệu trở thành một phần của cùng transaction.

## 5. Xử lý lỗi và offset khi một chunk thất bại

Đây là điểm cần thiết kế trước khi đưa chunking vào production.

Với batch listener dùng `AckMode.BATCH`, container commit offset sau khi listener xử lý thành công các record của poll theo cơ chế ack đang cấu hình. Giả sử listener đã xử lý xong chunk đầu tiên, nhưng chunk thứ hai ném exception. Các thay đổi nghiệp vụ của chunk đầu tiên có thể đã được ghi vào cơ sở dữ liệu, trong khi poll batch vẫn chưa hoàn tất. Khi batch được gửi lại, chunk đầu tiên có thể chạy lại.

Vì vậy, chia batch trong listener không đồng nghĩa mỗi chunk tự có một offset commit độc lập. Hãy chọn chiến lược lỗi phù hợp:

- **Thử lại toàn bộ poll batch:** đơn giản, nhưng mọi chunk đã chạy trước lỗi có thể được xử lý lại. Các thao tác nghiệp vụ phải idempotent.
- **Đánh dấu record lỗi:** với batch listener, có thể kết hợp `DefaultErrorHandler` và `BatchListenerFailedException` để chỉ ra record thất bại. Error handler cần được cấu hình đúng cho chính sách retry và phục hồi mong muốn.
- **Đưa phần không thể xử lý vào dead-letter topic (DLT):** cấu hình recoverer để lưu record lỗi cùng thông tin cần thiết cho việc điều tra và phát lại. Việc gửi DLT không tự xảy ra chỉ vì listener đã chia chunk.

Nếu xử lý chunk bằng một thao tác ghi hàng loạt mà chỉ biết cả chunk thất bại, ứng dụng có thể không xác định được record gây lỗi. Khi đó, hãy quyết định rõ sẽ thử lại cả chunk, tách tiếp chunk bị lỗi, hay chuyển chunk sang quy trình phục hồi riêng. Không được bỏ qua lỗi rồi để listener trả về bình thường: container có thể xem poll đã thành công và commit offset, khiến event chưa được xử lý bị mất khỏi luồng retry.

Một cách giảm tác động của việc chạy lại là ghi nhận `eventId` đã xử lý bằng ràng buộc duy nhất hoặc cơ chế upsert phù hợp. Nếu một event đã được áp dụng, lần nhận lại không được tạo thêm tác động nghiệp vụ. Với luồng Kafka-to-Kafka, có thể cân nhắc Kafka transaction và chế độ đọc phù hợp; điều đó vẫn không bao phủ tự động các tác dụng phụ ở hệ thống bên ngoài Kafka.

## 6. Tách một batch nghiệp vụ lớn ngay từ producer

Nếu hệ thống nguồn có một danh sách lớn và mỗi phần tử có thể xử lý độc lập, thường nên phát từng phần tử thành record riêng. Kafka khi đó có thể gom các record theo partition ở tầng truyền tải:

```java
for (OrderEvent event : events) {
    kafkaTemplate.send(
            "order-events",
            event.orderId().toString(),
            event);
}
```

Key ở đây là mã đơn hàng. Các event của cùng một đơn hàng sẽ được định tuyến theo cùng key, giúp giữ thứ tự trong partition tương ứng. Producer vẫn có thể gom nhiều record thành một lô gửi mạng; việc gửi từng record qua `KafkaTemplate` không có nghĩa mỗi record tạo ra một request mạng riêng.

Nếu downstream cần nhận một nhóm phần tử như một thông điệp độc lập, có thể đóng gói từng chunk thành một event có metadata:

```java
public record OrderChunk(
        String batchId,
        int chunkIndex,
        int chunkCount,
        List<OrderEvent> items) {
}
```

Producer tạo nhiều `OrderChunk` từ batch nguồn rồi gửi từng chunk:

```java
List<List<OrderEvent>> chunks = partition(events, CHUNK_SIZE);

for (int index = 0; index < chunks.size(); index++) {
    OrderChunk chunk = new OrderChunk(
            batchId,
            index,
            chunks.size(),
            chunks.get(index));

    kafkaTemplate.send("order-chunks", batchId, chunk);
}
```

Hàm chia danh sách có thể viết như sau:

```java
static <T> List<List<T>> partition(List<T> items, int size) {
    if (size <= 0) {
        throw new IllegalArgumentException("size must be positive");
    }

    List<List<T>> result = new ArrayList<>();

    for (int start = 0; start < items.size(); start += size) {
        int end = Math.min(start + size, items.size());
        result.add(new ArrayList<>(items.subList(start, end)));
    }

    return result;
}
```

Trong ví dụ, dùng `batchId` làm key khiến các chunk của cùng batch đi vào cùng partition với cách partition mặc định theo key. Điều này hữu ích nếu cần giữ thứ tự chunk, nhưng một batch rất lớn có thể tập trung tải vào một partition. Nếu ưu tiên phân tán tải, hãy chọn key theo thực thể nghiệp vụ và thiết kế cách theo dõi thứ tự hoặc hoàn tất batch tương ứng.

Các trường `batchId`, `chunkIndex` và `chunkCount` giúp consumer biết chunk thuộc batch nào, vị trí của nó và tổng số chunk dự kiến. Chúng không tự bảo đảm batch đã hoàn tất. Nếu cần phát tín hiệu hoàn tất, hãy định nghĩa rõ điều kiện: tất cả chunk đã được xử lý thành công, hoặc tất cả kết quả đã được ghi nhận. Cũng cần xử lý trường hợp chunk đến trễ, được gửi lại hoặc xuất hiện trùng.

Với producer gửi số lượng lớn record, hãy theo dõi kết quả gửi bất đồng bộ và giới hạn số lần gửi đang chờ xác nhận. Tạo hàng triệu future cùng lúc có thể chuyển vấn đề bộ nhớ từ consumer sang producer. API future cụ thể phụ thuộc phiên bản Spring Kafka mà dự án sử dụng.

## 7. Kết hợp chunking với concurrency

Chunking và concurrency giải quyết hai vấn đề khác nhau:

- Chunking giới hạn kích thước một đơn vị công việc.
- Concurrency cho phép nhiều consumer hoặc luồng xử lý làm việc đồng thời.

Trong Spring Kafka, thuộc tính `concurrency` của listener container có thể tạo nhiều consumer chạy song song. Số consumer thực sự có thể nhận partition phụ thuộc số partition được gán cho group. Tăng concurrency vượt quá số partition không làm một partition được xử lý song song an toàn bởi nhiều consumer trong cùng group.

Không nên đưa mọi record của một chunk vào `parallelStream()` hoặc executor không giới hạn mà không xét thứ tự và offset. Nếu listener trả về khi các tác vụ nền chưa hoàn thành, container có thể commit offset trước khi công việc nghiệp vụ hoàn tất. Nếu nhiều event cùng một key cần đúng thứ tự, xử lý song song chúng có thể làm đảo thứ tự dù Kafka đã sắp xếp record trong partition.

Một cách an toàn hơn là tăng concurrency ở cấp partition, giữ xử lý tuần tự trong mỗi partition, và chỉ song song hóa các công việc độc lập sau khi đã xác định rõ thời điểm hoàn tất trước khi ack. Nếu buộc phải xử lý bất đồng bộ trong listener, listener phải chờ tất cả tác vụ liên quan hoàn thành và truyền lỗi trở lại container trước khi kết thúc.

## 8. Điều chỉnh và quan sát throughput

Khi thử nghiệm, hãy điều chỉnh từng giới hạn và quan sát tác động:

| Tín hiệu | Điều cần kiểm tra |
|---|---|
| Consumer lag tăng liên tục | Tốc độ xử lý có thấp hơn tốc độ phát sinh record không; downstream có đang nghẽn không |
| Thời gian xử lý poll batch cao | Tổng thời gian của các chunk có tiến gần `max.poll.interval.ms` không |
| Heap tăng mạnh | Chunk có giữ nhiều object trung gian hoặc có quá nhiều tác vụ đang chờ không |
| Database chậm hoặc lock lâu | Chunk có quá lớn, transaction có quá dài hoặc có quá nhiều consumer ghi đồng thời không |
| Retry và DLT tăng | Lỗi tập trung ở một loại record, một chunk lớn hay một dependency không ổn định |
| Throughput giảm khi chunk nhỏ | Chi phí gọi service, transaction hoặc request có đang lấn át công việc thực tế không |

`max.poll.records` là giới hạn số record trong một poll. Giảm giá trị này có thể giảm lượng việc dồn vào một lần poll, nhưng cũng làm tăng số lần poll cần thiết. `max.poll.interval.ms` đặt giới hạn thời gian giữa các lần poll. Nếu tổng thời gian xử lý vẫn vượt giới hạn, cần giảm tải mỗi poll, tối ưu thao tác downstream hoặc thay đổi cách xử lý; chỉ chia một poll thành nhiều vòng lặp không giải quyết được nguyên nhân.

Ở phía producer, `batch.size` và `linger.ms` ảnh hưởng cách gom record để gửi. Tăng `linger.ms` có thể giúp gom được nhiều record hơn nhưng thêm độ trễ chờ. Hãy điều chỉnh dựa trên mục tiêu latency và throughput, đồng thời phân biệt chúng với kích thước chunk nghiệp vụ.

Nên ghi nhận ít nhất số record mỗi poll, số chunk mỗi poll, kích thước chunk thực tế, thời gian xử lý từng chunk, số lần retry, số event đưa vào DLT và consumer lag. Những số liệu này giúp trả lời liệu bottleneck nằm ở consumer, cơ sở dữ liệu, API phía sau hay cách phân phối partition.

## 9. Checklist trước khi đưa vào vận hành

- [ ] Đã xác định batch thuộc tầng producer, poll, listener hay nghiệp vụ.
- [ ] Chunk có kích thước giới hạn và phù hợp với khả năng của downstream.
- [ ] Tổng thời gian xử lý một poll nằm trong giới hạn poll interval với biên an toàn.
- [ ] Event có định danh ổn định và thao tác nghiệp vụ chịu được việc xử lý lặp.
- [ ] Chính sách retry, xác định record lỗi và DLT đã được cấu hình rõ.
- [ ] Thứ tự theo key/partition được giữ ở những luồng cần thứ tự.
- [ ] Tác vụ bất đồng bộ không hoàn tất sau khi listener đã ack.
- [ ] Producer và consumer đều có giới hạn cho lượng công việc đang chờ.
- [ ] Có metric để theo dõi latency, throughput, lag, retry và kích thước chunk.

Tách batch thành công việc nhỏ giúp ứng dụng kiểm soát tài nguyên và giới hạn phạm vi xử lý lại. Hiệu quả chỉ đạt được khi ranh giới chunk khớp với ranh giới nghiệp vụ, offset được commit đúng thời điểm, và mỗi phần việc có thể được nhận diện khi chạy lại. Trong Spring Kafka, hãy xem kích thước poll, kích thước chunk, partition và chính sách lỗi như các quyết định liên quan với nhau khi thiết kế một luồng messaging tin cậy.

