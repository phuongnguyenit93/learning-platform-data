# Replay có kiểm soát

Trong vận hành Spring Kafka, replay là việc đọc và xử lý lại các bản ghi Kafka đã được consumer xử lý trước đó hoặc đã bị bỏ qua do sự cố. Replay hữu ích khi cần sửa dữ liệu sau một lỗi nghiệp vụ, chạy lại bằng phiên bản code đã sửa, phục hồi consumer sau khi xác định sai offset hoặc xử lý lại một khoảng message nằm trong Dead Letter Topic (DLT).

Replay tác động trực tiếp đến dữ liệu và side effect. Một lần replay có thể tạo lại đơn hàng, ghi nợ, gửi email hoặc phát sinh sự kiện downstream. Vì vậy, replay phải có phạm vi rõ ràng, điểm bắt đầu và kết thúc xác định, cách chống tác động trùng, giới hạn tốc độ, người chịu trách nhiệm và điều kiện dừng. Trong quy trình incident response, replay là một thao tác phục hồi có kiểm soát, không phải cách thử lại message một cách tùy ý.

## 1. Replay là gì và khi nào cần dùng?

Kafka lưu các record theo partition. Consumer group lưu offset đã commit để ghi nhận vị trí đọc tiếp theo của từng partition. Replay đưa một consumer trở lại các offset cũ hoặc tạo một consumer group khác để đọc lại dữ liệu từ một vị trí đã chọn.

Một số tình huống thường cần replay:

- Một phiên bản consumer có bug đã ghi sai dữ liệu; code đã được sửa và cần chạy lại các event bị ảnh hưởng.
- Consumer bị cấu hình sai, commit offset vượt quá dữ liệu đã xử lý hoặc bỏ qua một khoảng record.
- Một downstream service tạm thời không hoạt động và hệ thống cần xử lý lại các event đã được lưu giữ.
- Cần tái tạo read model, search index, cache hoặc projection từ event log.
- Cần xử lý lại message đã được chuyển vào DLT sau khi nguyên nhân lỗi được khắc phục.

Replay không phải lựa chọn phù hợp cho mọi lỗi. Nếu một message chỉ thất bại tạm thời và retry policy đang hoạt động đúng, retry có thể đủ. Nếu dữ liệu gốc đã hết retention hoặc bị loại bỏ do log compaction, replay từ Kafka có thể không khôi phục được đầy đủ trạng thái. Nếu side effect đã xảy ra nhưng response bị timeout, cần đối soát trạng thái trước khi replay để tránh thực hiện tác động lần hai.

### Phân biệt retry, DLT và replay

| Cơ chế | Mục đích | Phạm vi |
|---|---|---|
| Retry | Thử lại một lần xử lý thất bại | Thường áp dụng ngay trong luồng xử lý hoặc retry topic |
| Dead Letter Topic | Cách ly record không thể xử lý theo chính sách retry | Giữ record lỗi để điều tra hoặc xử lý sau |
| Replay | Đọc lại một tập record đã tồn tại | Có thể là một partition, một khoảng offset, một khoảng thời gian hoặc toàn bộ dữ liệu còn lưu |

DLT không tự sửa side effect đã xảy ra trước khi exception được ném ra. Tương tự, replay không tự bảo đảm chỉ tạo một side effect. Consumer chạy replay vẫn phải áp dụng idempotency và kiểm tra trạng thái nghiệp vụ.

## 2. Xác định chính xác phạm vi replay

Trước khi chạy replay, hãy mô tả phạm vi bằng các thành phần có thể kiểm tra được:

- **Topic:** nguồn dữ liệu cần đọc lại.
- **Partition:** các partition bị ảnh hưởng. Không mặc định mọi partition đều cần replay.
- **Start offset:** offset đầu tiên cần xử lý ở từng partition.
- **End offset exclusive:** offset giới hạn, không được xử lý. Chụp giá trị này trước khi bắt đầu để replay không chạy theo các record mới phát sinh liên tục.
- **Consumer group hoặc replay job ID:** định danh luồng replay và checkpoint của nó.
- **Business filter:** loại event, tenant, aggregate hoặc operation nằm trong phạm vi sự cố.
- **Target:** database, service hoặc read model sẽ nhận tác động từ lần replay.

Ví dụ, một incident chỉ ảnh hưởng các event ở partition `0` và `2` trong topic `orders`, với khoảng offset `[1200, 1450)` và `[800, 920)`. Khoảng này có nghĩa offset bắt đầu được xử lý, còn offset kết thúc không được xử lý. Mỗi partition có một dải offset riêng; không thể dùng một offset toàn cục để đại diện cho toàn topic.

Nếu xác định phạm vi theo thời gian, hãy chuyển mốc thời gian thành offset riêng cho từng partition. Kafka không bảo đảm một timestamp tương ứng với cùng một offset ở các partition. Timestamp của record cũng có thể là thời điểm tạo ở producer hoặc thời điểm broker nhận, tùy cấu hình timestamp.

### Offset là vị trí đọc tiếp theo

Offset được commit là vị trí consumer sẽ đọc tiếp theo, không phải số thứ tự của record cuối cùng đã xử lý. Ví dụ, commit offset `1201` thường có nghĩa record ở offset `1200` đã được xử lý và lần đọc tiếp theo bắt đầu từ `1201`.

Khi chỉ định replay range, nên dùng quy ước rõ ràng `[startOffset, endOffsetExclusive)`. Điều này giúp tránh xử lý thừa record cuối hoặc bỏ sót record đầu. Cũng cần nhớ log có thể có khoảng trống offset do compaction, transaction marker hoặc record đã bị loại bỏ; không phải mọi số nguyên trong khoảng đều tương ứng với một record còn đọc được.

## 3. Chọn chiến lược replay phù hợp

Có ba cách tổ chức thường gặp. Cách phù hợp phụ thuộc vào việc cần sửa consumer group đang chạy, xử lý lại dữ liệu trong môi trường cô lập hay phát lại event qua một luồng riêng.

### Cách A: Dùng consumer group riêng cho replay

Đây thường là lựa chọn dễ kiểm soát khi cần xử lý lại dữ liệu mà không làm thay đổi offset của consumer production. Tạo một group ID dành riêng cho incident hoặc replay job, ví dụ `orders-replay-incident-2026-11-16`.

Ưu điểm:

- Offset production được giữ nguyên.
- Có thể chạy code mới trong một consumer riêng.
- Có thể giới hạn tốc độ và dừng replay mà không dừng luồng production.
- Có thể đối chiếu kết quả trước khi quyết định cập nhật dữ liệu chính thức.

Rủi ro cần kiểm soát:

- Nếu consumer replay ghi vào cùng database hoặc gọi cùng dịch vụ ngoài, side effect vẫn có thể bị lặp.
- Nếu group mới không có committed offset, `auto.offset.reset=earliest` có thể khiến nó đọc toàn bộ dữ liệu còn retention.
- Nếu tạo group ID mới mỗi lần retry một job đã dở dang, checkpoint của lần trước không được tiếp tục sử dụng.

Với replay có phạm vi offset xác định, nên cấu hình `auto.offset.reset=none` để consumer thất bại rõ ràng nếu không có offset được chỉ định hoặc offset không còn hợp lệ. Hãy seek đến start offset đã được duyệt. Dùng group ID ổn định cho cùng một replay job để có thể tiếp tục từ checkpoint; tạo ID mới khi thực sự bắt đầu một job độc lập.

### Cách B: Reset offset của consumer group hiện tại

Reset offset phù hợp khi chủ đích là cho consumer production đọc lại dữ liệu từ một vị trí cũ, ví dụ cần phục hồi một group đã commit vượt quá phần xử lý bền vững. Cách này ảnh hưởng trực tiếp đến tiến độ của group đang phục vụ hệ thống.

Trình tự vận hành an toàn:

1. Xác định chính xác group, topic và partition cần reset.
2. Ghi lại offset hiện tại, lag và trạng thái consumer để có thể đối chiếu hoặc khôi phục.
3. Dừng toàn bộ consumer thuộc group, xác nhận group không còn thành viên hoạt động.
4. Chạy lệnh reset ở chế độ `--dry-run` và kiểm tra kết quả cho từng partition.
5. Chỉ thực thi khi start offset mới đã được duyệt và tác động đến production đã được tính đến.
6. Khởi động lại consumer, theo dõi lag, throughput, lỗi và side effect.

Ví dụ kiểm tra offset hiện tại:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server <broker:9092> \
  --describe \
  --group <production-group>
```

Ví dụ xem trước việc đưa các partition của một topic về offset đầu tiên còn lưu:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server <broker:9092> \
  --group <production-group> \
  --topic <topic-name> \
  --reset-offsets \
  --to-earliest \
  --dry-run
```

Sau khi xác minh kết quả và group đã dừng hoàn toàn, mới chạy lại với `--execute`:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server <broker:9092> \
  --group <production-group> \
  --topic <topic-name> \
  --reset-offsets \
  --to-earliest \
  --execute
```

Tên script có thể là `.sh` hoặc `.bat` tùy bản phân phối và hệ điều hành. Các tùy chọn reset khác gồm `--to-offset`, `--to-datetime`, `--to-latest` và `--shift-by`; cú pháp chi tiết cần khớp phiên bản Kafka CLI đang sử dụng.

Không chạy reset offset trên group còn consumer hoạt động. Consumer có thể tiếp tục commit offset mới, rebalance hoặc tạo kết quả khó dự đoán. `--to-earliest` cũng có thể khiến production xử lý lại toàn bộ record còn retention của topic được chỉ định. Nếu không có idempotency ở sink, việc reset có thể nhân đôi tác động nghiệp vụ.

### Cách C: Phát lại sang replay topic

Một job có thể đọc record từ topic nguồn rồi publish bản sao sang topic riêng, ví dụ `orders-replay`. Consumer replay xử lý topic này bằng group và cấu hình tách biệt.

Cách này hữu ích khi muốn:

- Thử nghiệm phiên bản handler mới trong môi trường cô lập.
- Giữ nguyên topic production và tiến độ consumer hiện tại.
- Áp dụng bộ lọc, bổ sung metadata incident hoặc chia replay thành nhiều đợt.
- Tạo luồng đầu vào riêng cho quy trình sửa read model hoặc đối soát.

Khi copy record, cần giữ business event ID, key, schema version và các header cần thiết. Có thể thêm metadata như `original-topic`, `original-partition`, `original-offset`, `replay-job-id` và `replay-reason`. Nếu cần giữ thứ tự theo aggregate, phải duy trì cùng key và bảo đảm các event của aggregate đi vào cùng partition ở topic đích. Không có thứ tự toàn cục giữa các partition.

Replay topic có thể chứa event được phát lại, nhưng nó không tự tạo ra transaction nguyên tử giữa thao tác đọc nguồn và publish bản sao. Nếu publisher dừng sau khi publish nhưng trước khi ghi nhận tiến độ, record có thể được publish lại. Hãy dùng outbox hoặc checkpoint phù hợp và để consumer đích xử lý idempotent. Tránh publish ngược vào chính topic nguồn nếu không có cơ chế ngăn vòng lặp.

### So sánh các lựa chọn

| Chiến lược | Ảnh hưởng đến production group | Phù hợp khi | Điểm cần kiểm soát |
|---|---|---|---|
| Group replay riêng | Không đổi offset production | Replay độc lập, thử code mới, xử lý lại có kiểm soát | Group ID, offset range, side effect ở sink |
| Reset group hiện tại | Thay đổi offset production | Phục hồi chính group đang chạy | Dừng consumer, dry-run, duplicate, lag tăng |
| Replay topic | Không đổi offset nguồn nếu publisher dùng group riêng | Cần pipeline replay tách biệt hoặc thêm metadata | Publish lặp, key, thứ tự và schema |

## 4. Thực hiện replay có giới hạn trong ứng dụng Spring Kafka

Với `@KafkaListener`, một replay listener nên có `groupId` riêng và cấu hình riêng. Không dùng chung group ID production nếu mục tiêu là replay độc lập.

Ví dụ listener chuyên xử lý event replay:

```java
@Component
public class OrderReplayListener {

    private final OrderReplayService replayService;

    public OrderReplayListener(OrderReplayService replayService) {
        this.replayService = replayService;
    }

    @KafkaListener(
        id = "orders-replay-listener",
        topics = "${replay.orders.topic}",
        groupId = "${replay.orders.group-id}",
        autoStartup = "false"
    )
    public void onMessage(ConsumerRecord<String, OrderEvent> record) {
        replayService.process(
            record.key(),
            record.value(),
            record.topic(),
            record.partition(),
            record.offset()
        );
    }
}
```

`autoStartup = "false"` cho phép ứng dụng khởi tạo listener nhưng chỉ bắt đầu khi replay job đã được chuẩn bị. Một coordinator có thể điều khiển listener qua `KafkaListenerEndpointRegistry`, sau khi kiểm tra cấu hình, group ID, phạm vi và checkpoint. Để seek đến offset cụ thể, Spring Kafka hỗ trợ `ConsumerSeekAware` hoặc thao tác trên listener container; việc seek phải được thực hiện đúng thời điểm consumer đã được assign partition. Chỉ seek start offset là chưa đủ để giới hạn end offset, nên coordinator vẫn phải theo dõi ranh giới kết thúc của từng partition và dừng job khi đạt ranh giới đó.

Với replay yêu cầu phạm vi `[start, end)` nghiêm ngặt, có thể triển khai một worker dùng trực tiếp Kafka `Consumer` trong ứng dụng Spring. Ví dụ sau minh họa cách gán partition, seek đến offset đã duyệt, chụp end offset và chỉ chuyển record trong phạm vi cho handler. Các phần tạo consumer, giải mã event và lưu trạng thái job được cung cấp bởi ứng dụng:

```java
public final class BoundedReplayWorker {

    private final Consumer<String, OrderEvent> consumer;
    private final OrderReplayService replayService;

    public BoundedReplayWorker(
            Consumer<String, OrderEvent> consumer,
            OrderReplayService replayService) {
        this.consumer = consumer;
        this.replayService = replayService;
    }

    public void run(Map<TopicPartition, Long> startOffsets) {
        Set<TopicPartition> partitions = startOffsets.keySet();
        consumer.assign(partitions);

        Map<TopicPartition, Long> beginning = consumer.beginningOffsets(partitions);
        Map<TopicPartition, Long> endExclusive = consumer.endOffsets(partitions);

        for (TopicPartition partition : partitions) {
            long start = startOffsets.get(partition);
            long earliest = beginning.get(partition);
            long end = endExclusive.get(partition);

            if (start < earliest || start > end) {
                throw new IllegalArgumentException(
                    "Replay offset is outside the retained range: " + partition
                );
            }

            consumer.seek(partition, start);
        }

        Map<TopicPartition, Long> nextOffsets = new HashMap<>(startOffsets);
        Set<TopicPartition> completed = new HashSet<>();

        while (completed.size() < partitions.size()) {
            ConsumerRecords<String, OrderEvent> records =
                consumer.poll(Duration.ofMillis(500));

            for (ConsumerRecord<String, OrderEvent> record : records) {
                TopicPartition partition = new TopicPartition(
                    record.topic(), record.partition()
                );
                long end = endExclusive.get(partition);

                if (record.offset() >= end) {
                    continue;
                }

                replayService.processIdempotently(record);
                nextOffsets.put(partition, record.offset() + 1);
            }

            for (TopicPartition partition : partitions) {
                if (consumer.position(partition) >= endExclusive.get(partition)) {
                    completed.add(partition);
                    nextOffsets.put(partition, endExclusive.get(partition));
                }
            }

            Map<TopicPartition, OffsetAndMetadata> commit = new HashMap<>();
            nextOffsets.forEach((partition, next) ->
                commit.put(partition, new OffsetAndMetadata(next))
            );
            if (!commit.isEmpty()) {
                consumer.commitSync(commit);
            }
        }
    }
}
```

Đây là khung minh họa cho worker đồng bộ, không phải một replay framework hoàn chỉnh. Trong ứng dụng thực tế, cần bổ sung việc đóng consumer, timeout, hủy job, checkpoint bền vững, giới hạn tốc độ, xử lý exception và báo cáo kết quả. `endExclusive` được chụp trước khi đọc nên record mới được ghi sau thời điểm đó không thuộc replay hiện tại. Khi poll trả về record nằm sau ranh giới, worker bỏ qua record đó và kết thúc partition khi consumer position đạt end offset.

Một cấu hình consumer dành cho worker có thể bắt đầu như sau:

```java
Map<String, Object> props = new HashMap<>();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
props.put(ConsumerConfig.GROUP_ID_CONFIG, replayGroupId);
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "none");
props.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 100);
```

`replayGroupId` cần dành riêng cho job. `enable.auto.commit=false` giúp ứng dụng chỉ commit sau khi handler hoàn tất. `auto.offset.reset=none` tránh vô tình đọc từ đầu hoặc cuối topic khi offset không hợp lệ. `isolation.level=read_committed` phù hợp khi topic có transactional producer và replay chỉ nên thấy record đã commit. Với topic không dùng transaction, thiết lập này vẫn có thể dùng được.

Trong ví dụ worker, `processIdempotently` phải hoàn tất transaction ở sink trước khi `commitSync` được gọi. Nếu handler thất bại giữa batch, offset chưa commit có thể được đọc lại ở lần chạy sau. Đây là lý do sink cần idempotency. Không nên commit Kafka offset trước khi dữ liệu đích đã được ghi bền vững.

Khi chạy nhiều worker, mỗi partition chỉ nên có một worker sở hữu trong cùng replay job. Nếu các worker cùng ghi checkpoint cho một partition, chúng có thể ghi đè tiến độ hoặc xử lý vượt thứ tự. Hãy chia partition rõ ràng và dùng cơ chế khóa/lease hoặc điều phối job để bảo đảm ownership.

## 5. Bảo vệ dữ liệu và side effect trong lúc replay

Replay đọc lại record cũ, nhưng hệ thống đích có thể đã thay đổi kể từ lần xử lý đầu tiên. Vì vậy, handler phải quyết định rõ replay là cập nhật trạng thái, tái tạo projection hay thực hiện lại một command nghiệp vụ.

### Dùng event ID và operation ID để chống trùng

Giữ nguyên `eventId` của event gốc khi replay. Không tạo event ID mới chỉ vì record được publish lại sang replay topic. Nếu event có `businessOperationId`, hãy dùng nó để nhận diện cùng một ý định nghiệp vụ ngay cả khi event được đóng gói lại hoặc có metadata replay mới.

Một inbox table với unique key như `(consumerName, eventId)` có thể ngăn consumer ghi cùng event nhiều lần. Nếu replay có thể tạo event ID mới cho cùng một nghiệp vụ, khóa nghiệp vụ phải được dùng bổ sung. Tác động ở dịch vụ ngoài cần idempotency key ổn định; ví dụ mọi lần retry của cùng một charge phải dùng lại cùng payment key.

Idempotency cũng phải xét phiên bản logic. Một event đã được xử lý trước đó có thể cần cập nhật lại projection bằng code mới. Nếu inbox hiện tại chặn mọi event đã thấy, replay sẽ không chạy logic mới. Trong trường hợp này, hãy dùng một consumer/version scope riêng cho projection mới, tạo read model mới hoặc thiết kế một quy trình rebuild có checkpoint. Không xóa inbox production hàng loạt chỉ để ép replay chạy lại.

### Giữ thứ tự cần thiết

Kafka bảo đảm thứ tự trong một partition. Replay nhiều partition song song có thể làm thay đổi thứ tự hoàn thành giữa các partition. Nếu nghiệp vụ phụ thuộc thứ tự theo aggregate, hãy giữ cùng key và xử lý tuần tự các event của aggregate đó. Không giả định rằng event ở partition `0` phải hoàn tất trước event ở partition `1`.

Nếu replay topic có số partition khác topic nguồn, key vẫn có thể được ánh xạ sang partition khác. Hãy kiểm tra partitioning strategy và yêu cầu ordering trước khi chuyển dữ liệu. Với một số nghiệp vụ, cần gom event theo aggregate rồi sắp thứ tự bằng sequence/version trong payload thay vì dựa vào timestamp.

### Kiểm tra retention và log compaction

Replay chỉ có thể đọc dữ liệu còn tồn tại. Nếu start offset nhỏ hơn `beginningOffsets` hiện tại, dữ liệu cần replay đã bị loại khỏi log do retention hoặc thao tác quản trị. Không tự động seek sang earliest trong tình huống này vì sẽ âm thầm thay đổi phạm vi replay. Hãy dừng job, ghi nhận khoảng dữ liệu bị thiếu và tìm nguồn phục hồi khác như archive, backup hoặc database audit.

Với compacted topic, Kafka có thể giữ giá trị mới nhất cho key và loại bỏ record cũ. Topic đó phù hợp cho một số kiểu khôi phục trạng thái hiện tại, nhưng không nhất thiết là event history đầy đủ để tái dựng mọi chuyển đổi. Tombstone cũng có ý nghĩa xóa dữ liệu và cần được xử lý đúng khi rebuild.

## 6. Điều tiết tốc độ và giới hạn tác động

Replay quá nhanh có thể làm tăng tải database, cạn connection pool, vượt rate limit của dịch vụ ngoài hoặc khiến consumer production bị tranh chấp tài nguyên. Hãy coi replay là một workload riêng có ngân sách tài nguyên.

Các biện pháp thường dùng:

- Giới hạn `max.poll.records` để kiểm soát kích thước batch.
- Điều chỉnh concurrency theo số partition và khả năng của sink.
- Dùng rate limiter hoặc giới hạn số record mỗi giây.
- Chạy thử trên một partition hoặc một khoảng offset nhỏ trước khi mở rộng.
- Tạm dừng replay khi latency, error rate hoặc database load vượt ngưỡng đã định.
- Dùng connection pool, thread pool và quota riêng nếu replay có thể ảnh hưởng production.
- Tránh chạy replay đồng thời với migration, backup hoặc batch job nặng nếu chúng cùng tranh chấp tài nguyên.

Không nên chỉ dựa vào `max.poll.records` để giới hạn tốc độ. Tham số này giới hạn số record trả về trong một poll, không đặt giới hạn records/second. Nếu handler xử lý rất nhanh, worker vẫn có thể tạo tải lớn. Cần rate limiter hoặc pacing thực sự khi downstream có giới hạn.

## 7. Quy trình incident response cho một lần replay

Một quy trình có thể áp dụng trong vận hành:

### Bước 1: Xác định nguyên nhân và tác động

Ghi nhận consumer group, topic, partition, offset hoặc thời gian bị ảnh hưởng, phiên bản ứng dụng, thời điểm bắt đầu/kết thúc incident và loại dữ liệu sai. Xác định side effect nào đã thành công trước khi lỗi xảy ra. Nếu có nguy cơ tiếp tục ghi sai, khắc phục hoặc tạm dừng nguồn lỗi trước khi replay.

### Bước 2: Lưu lại trạng thái trước replay

Thu thập offset đã commit, beginning/end offset của partition, consumer lag, số record trong DLT, số lượng bản ghi nghiệp vụ bị ảnh hưởng và checkpoint hiện tại. Lưu các giá trị này cùng incident ID để so sánh sau khi chạy.

### Bước 3: Chọn chiến lược và môi trường đích

Quyết định dùng replay group, reset group hiện tại hay replay topic. Xác định replay chạy ở staging, một read model mới hay production sink. Nếu replay sẽ gọi payment, email hoặc dịch vụ có side effect, cần xác minh idempotency key và trạng thái nghiệp vụ trước khi cho phép.

### Bước 4: Chốt replay window

Chọn start offset và end offset exclusive cho từng partition. Chụp end offset tại một thời điểm cố định. Kiểm tra start offset còn trong retention và schema của record tương thích với code replay. Ghi rõ business filter và những loại record bị loại trừ.

### Bước 5: Dry run và thử phạm vi nhỏ

Kiểm tra cấu hình group ID, topic, partition, offset, sink, tốc độ và quyền truy cập. Nếu dùng reset offset, bắt buộc xem kết quả `--dry-run`. Nếu dùng replay worker, chạy một partition hoặc một khoảng nhỏ và đối chiếu số record đọc, số record được áp dụng, số record bị bỏ qua và side effect.

### Bước 6: Chạy theo đợt và theo dõi

Chạy từng partition hoặc từng dải offset theo kế hoạch. Theo dõi lag, throughput, lỗi, retry, DLT, latency database, rate limit và trạng thái compensation. Dừng khi vượt ngưỡng, xuất hiện duplicate bất thường hoặc số lượng record không khớp dự kiến.

### Bước 7: Đối soát và đóng incident

Đối chiếu số record dự kiến với số record đã xử lý, checkpoint từng partition, trạng thái dữ liệu đích và side effect ở dịch vụ ngoài. Ghi nhận record không thể phục hồi, record cần xử lý thủ công và các thay đổi đã thực hiện. Chỉ đóng incident khi kết quả đã được xác nhận và replay job đã dừng.

## 8. Theo dõi tiến độ, lỗi và khả năng tiếp tục

Một replay job cần lưu trạng thái bền vững, không chỉ dựa vào log console. Có thể lưu các trường:

| Trường | Mục đích |
|---|---|
| `replayJobId` | Định danh lần replay |
| `incidentId` | Liên kết với incident gốc |
| `sourceTopic`, `partition` | Nguồn dữ liệu đang xử lý |
| `startOffset`, `endOffsetExclusive` | Ranh giới replay đã được duyệt |
| `lastProcessedOffset` | Tiến độ đã xử lý bền vững |
| `status` | `PLANNED`, `RUNNING`, `PAUSED`, `COMPLETED`, `FAILED` hoặc `CANCELLED` |
| `processedCount`, `skippedCount`, `failedCount` | Thống kê kết quả |
| `startedAt`, `updatedAt`, `completedAt` | Thời điểm vận hành |
| `lastError` | Lỗi gần nhất để điều tra |

Checkpoint phải được cập nhật sau khi side effect ở sink đã commit. Nếu ứng dụng dừng sau khi sink commit nhưng trước checkpoint, record có thể được xử lý lại; idempotency phải bảo vệ tình huống đó. Nếu checkpoint được ghi trước sink, ứng dụng có thể bỏ qua record khi khởi động lại dù tác động chưa hoàn tất.

Metric và log nên có `replayJobId`, `incidentId`, `topic`, `partition` và offset. Các metric hữu ích gồm record đọc/giây, record xử lý thành công, record bỏ qua, lỗi, retry, lag, thời gian xử lý mỗi record, checkpoint lag và tuổi job. Có cảnh báo khi job không tiến triển, một partition bị kẹt hoặc số lượng lỗi tăng bất thường.

Khi tạm dừng job, lưu checkpoint cho từng partition và lý do tạm dừng. Khi tiếp tục, dùng lại cùng replay job ID và xác minh checkpoint còn hợp lệ. Khi hủy job, ghi rõ các partition đã hoàn tất và các khoảng chưa chạy để tránh người vận hành nhầm rằng toàn bộ phạm vi đã được phục hồi.

## 9. Các lỗi vận hành thường gặp

| Sai sót | Hậu quả | Cách phòng tránh |
|---|---|---|
| Reset offset khi consumer group còn hoạt động | Consumer tiếp tục commit hoặc rebalance trong lúc reset | Dừng toàn bộ member và xác minh group inactive |
| Tạo replay group mới với `auto.offset.reset=earliest` mà không chỉ định range | Đọc lại toàn bộ dữ liệu còn retention | Dùng `none`, seek rõ ràng và chụp end offset |
| Replay vào cùng sink mà không có idempotency | Tạo side effect trùng | Dùng inbox, business key và idempotency key downstream |
| Chỉ giới hạn start offset, không giới hạn end offset | Job tiếp tục đọc record mới vô thời hạn | Chốt end offset exclusive cho từng partition |
| Chỉ dựa vào timestamp để xác định offset | Có thể lệch phạm vi do timestamp khác nhau giữa partition | Dùng offsetsForTimes theo từng partition và kiểm tra kết quả |
| Không kiểm tra retention | Seek đến dữ liệu không còn tồn tại | So sánh start offset với beginning offset trước khi chạy |
| Chạy replay quá nhanh | Quá tải sink hoặc ảnh hưởng production | Rate limit, chạy thử nhỏ và theo dõi ngưỡng |
| Commit offset trước khi sink commit | Mất tác động nghiệp vụ khi tiến trình dừng | Commit offset sau khi xử lý bền vững |
| Tạo group ID mới khi tiếp tục job cũ | Mất checkpoint và có thể replay lại từ đầu | Dùng ID ổn định theo replay job |

## 10. Checklist trước và sau replay

Trước khi chạy:

- [ ] Incident có nguyên nhân, phạm vi dữ liệu và người phụ trách rõ ràng.
- [ ] Topic, partition, start offset và end offset exclusive đã được xác định.
- [ ] Start offset còn trong retention và dữ liệu có thể đọc được.
- [ ] Chiến lược replay và group ID đã được chọn rõ ràng.
- [ ] Sink có idempotency hoặc đã có kế hoạch cô lập side effect.
- [ ] Code replay tương thích schema và đã được thử trên phạm vi nhỏ.
- [ ] Đã thiết lập rate limit, checkpoint, metric và điều kiện dừng.
- [ ] Nếu reset group, toàn bộ consumer đã dừng và kết quả dry-run đã được kiểm tra.

Sau khi chạy:

- [ ] Tất cả partition đã đạt end offset đã duyệt hoặc được ghi nhận rõ là chưa hoàn tất.
- [ ] Checkpoint được lưu sau khi sink commit.
- [ ] Số record đọc, xử lý, bỏ qua và lỗi đã được đối chiếu.
- [ ] Dữ liệu đích và side effect đã được xác minh.
- [ ] Record thất bại đã được chuyển sang retry, DLT hoặc xử lý thủ công theo chính sách.
- [ ] Replay worker/listener đã dừng và tài nguyên đã được giải phóng.
- [ ] Kết quả và giới hạn còn tồn tại đã được ghi vào incident record.

## Kết luận

Replay có kiểm soát trong Spring Kafka bắt đầu bằng việc xác định đúng topic, partition và replay window, sau đó chọn group riêng, reset offset hoặc replay topic theo mục tiêu phục hồi. Một lần replay an toàn cần end offset cố định, idempotency ở sink, checkpoint bền vững, giới hạn tốc độ và đối soát sau khi chạy. Khi tổ chức các bước này thành quy trình incident response, đội vận hành có thể xử lý lại dữ liệu bị ảnh hưởng mà vẫn theo dõi được phạm vi, tiến độ và tác động của từng lần chạy.
