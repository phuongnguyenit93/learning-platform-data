# Xử lý partition bị mất và tránh ghi kết quả từ chủ sở hữu cũ

Trong một consumer group, Kafka có thể chuyển partition từ consumer này sang consumer khác khi member tham gia, rời group, mất kết nối hoặc không gọi `poll()` đúng hạn. Đôi khi consumer cũ không còn sở hữu partition trước khi ứng dụng kịp hoàn tất xử lý. Worker chạy nền của consumer cũ vẫn có thể tiếp tục ghi database hoặc gọi API sau khi consumer mới đã nhận cùng partition.

Đây là tình huống **stale owner**: một tiến trình đã mất quyền sở hữu nhưng vẫn cố ghi kết quả. Chỉ hủy thread hoặc kiểm tra `isRunning` ở phía ứng dụng không đủ để ngăn mọi ghi muộn. Cần phân biệt callback thu hồi partition và callback báo partition đã mất, dừng công việc cũ, quản lý offset an toàn và dùng cơ chế fencing ở hệ thống nhận side effect.

## 1. Vì sao partition có thể bị mất?

Kafka gán partition cho consumer member trong một consumer group. Việc phân công có thể thay đổi khi:

- Một consumer mới tham gia group hoặc consumer hiện tại rời group.
- Consumer dừng đột ngột, mất kết nối hoặc không gửi heartbeat trong thời hạn.
- Ứng dụng không gọi `poll()` trong thời gian vượt `max.poll.interval.ms`.
- Topic được thêm partition hoặc metadata/assignment thay đổi.
- Group chuyển sang một giao thức phân công hoặc trạng thái rebalance mới.

Với xử lý đồng bộ trên consumer thread, callback rebalance thường có thể điều phối việc dừng xử lý trước khi consumer tiếp tục. Với mô hình poll thread kết hợp worker pool, worker có thể chạy độc lập lâu hơn vòng đời assignment. Khi partition đã được giao cho consumer khác, worker cũ vẫn có thể hoàn tất tác vụ đang chạy nếu ứng dụng không dừng hoặc fencing nó.

Ví dụ tình huống:

1. Consumer A nhận record offset 120 của partition 2 và chuyển record cho worker A1.
2. Worker A1 gọi dịch vụ thanh toán và mất 40 giây để hoàn tất.
3. Consumer A bị rebalance và partition 2 được giao cho consumer B.
4. Consumer B đọc lại offset 120 vì tiến độ của A chưa được commit.
5. B xử lý và ghi kết quả mới vào database.
6. Worker A1 hoàn tất muộn và ghi kết quả cũ đè lên kết quả của B.

Ngay cả khi event được xử lý idempotent theo `eventId`, một lần ghi cũ vẫn có thể ghi đè trạng thái mới hơn nếu hệ thống chỉ chống duplicate mà không kiểm tra thứ tự hoặc quyền sở hữu.

## 2. Phân biệt `onPartitionsRevoked` và `onPartitionsLost`

`ConsumerRebalanceListener` có các callback quan trọng để xử lý vòng đời partition:

| Callback | Ý nghĩa | Việc nên làm |
|---|---|---|
| `onPartitionsRevoked` | Partition sắp bị thu hồi trong quá trình rebalance; consumer đang có cơ hội xử lý việc bàn giao | Ngừng nhận thêm việc cho partition sắp rời, chờ công việc an toàn trong thời hạn, commit offset liên tục đã xử lý nếu vẫn hợp lệ và giải phóng tài nguyên/lease |
| `onPartitionsLost` | Partition đã mất quyền sở hữu; member khác có thể đã tiếp quản | Dừng phát sinh side effect mới, hủy hoặc đánh dấu worker cũ, vô hiệu token sở hữu và không cố commit offset cho partition đã mất |
| `onPartitionsAssigned` | Consumer được giao partition | Tạo trạng thái xử lý mới, lấy fencing token/lease nếu hệ thống dùng cơ chế ownership và bắt đầu nhận việc khi đã sẵn sàng |

`onPartitionsLost` có trong các phiên bản Kafka Java Consumer hiện đại; nếu client cũ không có callback này, cần dựa vào phiên bản API đang dùng và thiết kế cleanup an toàn cho các đường thoát khác. Không được coi `onPartitionsRevoked` và `onPartitionsLost` là cùng một sự kiện.

### Thu hồi có trật tự

Trong `onPartitionsRevoked`, partition đang được thu hồi nhưng consumer được thông báo để hoàn tất bàn giao. Đây là thời điểm phù hợp để:

- Ngừng phân phối record mới của các partition bị thu hồi.
- Chờ worker đang xử lý hoàn tất trong một deadline có giới hạn.
- Tính offset liên tục đã xử lý thành công cho từng partition.
- Commit những offset an toàn nếu consumer còn quyền sở hữu.
- Giải phóng lease/tài nguyên bằng thao tác có điều kiện theo token hiện tại.

Với eager rebalance, assignment cũ có thể bị thu hồi rộng hơn. Với cooperative rebalance, chỉ những partition thực sự cần chuyển mới bị revoke; các partition được giữ lại tiếp tục thuộc consumer. Chỉ dừng và xóa trạng thái cho các partition được liệt kê trong callback, không xóa toàn bộ assignment một cách máy móc.

### Partition đã mất

Trong `onPartitionsLost`, consumer đã mất quyền sở hữu partition. Không commit offset tại callback này vì consumer mới có thể đã bắt đầu xử lý. Callback chủ yếu dùng để ngăn worker cũ tiếp tục tạo side effect, hủy task nếu có thể và vô hiệu hóa thông tin ownership cũ.

Hủy một `Future` hoặc gửi interrupt không bảo đảm tác vụ bên ngoài dừng ngay. Một HTTP request đã được gửi, một câu lệnh database đang chạy hoặc một thư viện không hỗ trợ interrupt vẫn có thể hoàn tất. Vì vậy, callback cleanup là bước giảm công việc còn chạy; fencing ở nơi ghi dữ liệu mới là lớp bảo vệ cuối cùng.

## 3. Vì sao kiểm tra cờ hoặc hủy worker là chưa đủ?

Một cách triển khai thường thấy là đặt cờ `cancelled=true` khi partition bị revoke. Cách này hữu ích nhưng có khoảng đua:

1. Worker kiểm tra cờ và thấy `false`.
2. Partition bị mất, poll thread đặt cờ thành `true`.
3. Worker tiếp tục câu lệnh ghi database đã bắt đầu trước đó.
4. Ghi cũ hoàn tất sau khi consumer mới đã xử lý record.

Tương tự, `Future.cancel(true)` chỉ yêu cầu hủy và ngắt thread. Nó không tự rollback một side effect đã được hệ thống bên ngoài chấp nhận. `Thread.interrupt()` cũng chỉ có tác dụng nếu code đang chạy kiểm tra hoặc phản ứng với interrupt.

Các biện pháp ở phía consumer vẫn cần thiết:

- Dùng queue có giới hạn và theo dõi task theo `TopicPartition`.
- Không dispatch thêm record cho partition đang revoke/lost.
- Hủy hoặc drain task theo deadline, không chờ vô hạn trong callback.
- Gắn token ownership vào task tại thời điểm dispatch.
- Không để worker gọi API `KafkaConsumer`; consumer chỉ được điều khiển bởi poll thread.

Nhưng để ngăn ghi muộn thực sự, hệ thống nhận kết quả phải kiểm tra quyền sở hữu hoặc phiên bản trước khi áp dụng thay đổi.

## 4. Fencing token: ngăn chủ sở hữu cũ ghi dữ liệu

**Fencing token** là một giá trị tăng đơn điệu theo mỗi lần cấp quyền sở hữu. Khi consumer mới nhận partition, hệ thống ownership cấp token mới. Mọi tác vụ của consumer phải mang token đã nhận; hệ thống lưu dữ liệu chỉ chấp nhận thao tác có token hiện hành.

Ví dụ:

```text
Partition 2
  Consumer A được cấp epoch 41
  Consumer A mất partition
  Consumer B được cấp epoch 42

  Worker cũ của A gửi write(epoch=41) -> bị từ chối
  Worker của B gửi write(epoch=42)     -> được chấp nhận
```

Token phải được cấp và kiểm tra tại một nơi có thể tuần tự hóa việc đổi chủ sở hữu, ví dụ database chứa dữ liệu nghiệp vụ hoặc một dịch vụ lease có fencing semantics. Một biến `AtomicLong` trong từng JVM không đủ vì consumer A và B có bộ nhớ riêng, có thể khởi động lại và không chia sẻ thứ tự token.

### Token nên gắn với điều gì?

Thông thường, ownership được quản lý theo `groupId + topic + partition`. Nếu nhiều consumer group cùng xử lý một topic, mỗi group có quyền sở hữu độc lập. Token phải bao gồm phạm vi group để một group không vô tình fencing group khác.

Định danh chủ sở hữu nên nhận diện một lần chạy cụ thể của process, chẳng hạn `instanceId` kèm UUID khởi động. Không chỉ dùng hostname hoặc một tên pod có thể được tái sử dụng, vì tiến trình cũ và mới có thể cùng mang một tên trong thời gian chuyển tiếp.

## 5. Lưu fencing epoch trong database

Một cách triển khai là duy trì bảng ownership cho từng partition:

```sql
CREATE TABLE kafka_partition_lease (
    group_id      VARCHAR(200) NOT NULL,
    topic_name    VARCHAR(200) NOT NULL,
    partition_id  INTEGER NOT NULL,
    owner_id      VARCHAR(200) NOT NULL,
    epoch         BIGINT NOT NULL,
    updated_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (group_id, topic_name, partition_id)
);
```

Khi consumer được giao partition, ownership service cập nhật chủ sở hữu và tăng epoch một cách nguyên tử. Ví dụ về ý tưởng SQL (cú pháp cụ thể tùy database):

```sql
UPDATE kafka_partition_lease
SET owner_id = :new_owner_id,
    epoch = epoch + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE group_id = :group_id
  AND topic_name = :topic
  AND partition_id = :partition
RETURNING epoch;
```

Nếu chưa có row, ứng dụng cần tạo row theo cách xử lý xung đột insert đồng thời. Trong thực tế, nên đóng gói việc acquire thành một stored procedure hoặc transaction có khóa để hai consumer không cùng nhận một epoch hiện hành.

Consumer giữ epoch trả về và gắn nó vào từng task:

```java
public record OwnershipToken(
        String groupId,
        TopicPartition partition,
        String ownerId,
        long epoch
) {}

public record WorkItem(
        ConsumerRecord<String, String> record,
        OwnershipToken ownership
) {}
```

Worker không tự lấy token hiện tại từ một biến toàn cục khi bắt đầu ghi. Nó phải dùng token đã được gắn vào `WorkItem` lúc dispatch. Nếu worker cũ lấy token mới sau khi partition được chuyển giao, fencing sẽ mất tác dụng.

### Kiểm tra token cùng transaction với side effect

Việc kiểm tra token và cập nhật dữ liệu nghiệp vụ phải được thực hiện nguyên tử trong cùng transaction hoặc bằng một câu lệnh có điều kiện. Ví dụ quy trình:

```sql
BEGIN;

SELECT epoch, owner_id
FROM kafka_partition_lease
WHERE group_id = :group_id
  AND topic_name = :topic
  AND partition_id = :partition
FOR UPDATE;

-- Ứng dụng kiểm tra epoch = :task_epoch và owner_id = :task_owner.
-- Nếu không khớp: ROLLBACK và từ chối stale write.

UPDATE order_projection
SET status = :new_status,
    updated_at = CURRENT_TIMESTAMP
WHERE order_id = :order_id;

COMMIT;
```

Khóa row ownership trong cùng transaction giúp việc cấp epoch mới và side effect được tuần tự hóa. Nếu transaction cũ đã khóa row trước, thao tác cấp ownership mới phải chờ transaction đó hoàn tất; sau khi epoch mới được cấp, mọi transaction bắt đầu với token cũ sẽ bị từ chối. Nếu chỉ đọc epoch rồi đóng transaction, sau đó mới ghi business table, vẫn có race giữa kiểm tra và ghi.

Trong hệ thống có nhiều bảng hoặc nhiều side effect, mọi thay đổi cần được bảo vệ bởi cùng quy tắc fencing. Một thao tác ghi không kiểm tra token vẫn có thể bị worker cũ thực hiện muộn.

## 6. Kết hợp fencing với event ID và entity version

Fencing token, event ID và entity version giải quyết các vấn đề khác nhau:

| Cơ chế | Ngăn vấn đề nào? | Phạm vi |
|---|---|---|
| Fencing epoch | Chủ sở hữu partition cũ ghi sau khi quyền đã chuyển giao | Quyền ghi của một owner đối với partition/group |
| `eventId` duy nhất | Cùng một event bị áp dụng nhiều lần | Deduplication của từng sự kiện |
| Entity version/sequence | Cập nhật cũ ghi đè trạng thái mới hơn | Thứ tự thay đổi của một entity nghiệp vụ |
| Idempotent operation | Lặp cùng thao tác không tạo thêm tác động | Một nghiệp vụ hoặc API cụ thể |

Ví dụ cập nhật projection theo version:

```sql
UPDATE order_projection
SET status = :status,
    version = :event_version
WHERE order_id = :order_id
  AND version < :event_version;
```

Điều kiện version ngăn event cũ ghi đè version mới hơn của cùng đơn hàng. Tuy nhiên, nó không thay thế fencing khi cần ngăn owner cũ ghi vào nhiều entity khác nhau. Ngược lại, fencing không thay thế event ID vì cùng một owner vẫn có thể nhận lại cùng event sau khi offset chưa được commit.

Một thiết kế chắc chắn thường kết hợp cả ba: ownership epoch để xác thực writer, event ID để deduplicate và entity version để từ chối cập nhật nghiệp vụ đến sai thứ tự.

## 7. Xử lý task khi partition revoke hoặc lost

Poll thread nên quản lý một trạng thái cho mỗi partition, chẳng hạn `ACTIVE`, `REVOKING`, `LOST` hoặc `PAUSED`. Worker chỉ nhận task khi partition đang `ACTIVE` và token hợp lệ.

Luồng xử lý gợi ý:

1. Khi `onPartitionsAssigned`, tạo ownership epoch mới và chỉ dispatch sau khi acquire thành công.
2. Khi `onPartitionsRevoked`, chuyển partition sang `REVOKING`, ngừng dispatch và chờ task hoàn tất trong deadline.
3. Commit offset sau dãy record liên tục đã xử lý thành công, nếu còn quyền sở hữu.
4. Giải phóng lease có điều kiện theo đúng `ownerId` và `epoch`; không xóa lease của owner mới.
5. Khi `onPartitionsLost`, chuyển ngay sang `LOST`, vô hiệu token trong poll thread, hủy task có thể hủy và không commit offset.
6. Khi task cũ hoàn tất muộn, hệ thống ghi dữ liệu phải từ chối token cũ.

Ví dụ callback rút gọn:

```java
consumer.subscribe(List.of("orders.events"), new ConsumerRebalanceListener() {
    @Override
    public void onPartitionsRevoked(Collection<TopicPartition> partitions) {
        for (TopicPartition tp : partitions) {
            partitionWorkers.stopDispatch(tp);
        }

        // Chờ có giới hạn và lấy offset liên tục đã xử lý an toàn.
        Map<TopicPartition, OffsetAndMetadata> safeOffsets =
                partitionWorkers.drainAndGetSafeOffsets(partitions, revokeDeadline);

        if (!safeOffsets.isEmpty()) {
            consumer.commitSync(safeOffsets);
        }

        for (TopicPartition tp : partitions) {
            ownership.releaseIfCurrent(activeTokens.remove(tp));
        }
    }

    @Override
    public void onPartitionsLost(Collection<TopicPartition> partitions) {
        for (TopicPartition tp : partitions) {
            OwnershipToken oldToken = activeTokens.remove(tp);
            partitionWorkers.markLostAndCancel(tp);
            ownership.invalidateLocal(oldToken);
        }
        // Không commit ở đây: partition đã mất quyền sở hữu.
    }

    @Override
    public void onPartitionsAssigned(Collection<TopicPartition> partitions) {
        for (TopicPartition tp : partitions) {
            // Acquire epoch mới trước khi cho phép worker ghi dữ liệu.
            activeTokens.put(tp, ownership.acquire(tp, processIncarnationId));
            partitionWorkers.activate(tp);
        }
    }
});
```

Đây là khung minh họa; `partitionWorkers`, `ownership`, `activeTokens`, `revokeDeadline` và `processIncarnationId` là thành phần ứng dụng tự triển khai. Không gọi các thao tác `KafkaConsumer` từ worker thread. Trong production, việc acquire/release lease trong callback phải có timeout ngắn; nếu thao tác ownership có thể chậm, hãy pause partition, tiếp tục poll và hoàn tất acquire qua completion queue trước khi dispatch.

`releaseIfCurrent` phải có điều kiện `ownerId` và `epoch` khớp. Nếu consumer cũ gọi release muộn sau khi consumer mới đã acquire epoch mới, thao tác release phải không ảnh hưởng lease mới.

## 8. Không commit offset khi partition đã lost

Offset commit là tiến độ của consumer group, không phải bằng chứng rằng side effect đã được thực hiện đúng một lần. Khi partition đã lost, consumer cũ không được commit offset của partition đó. Consumer mới sẽ bắt đầu từ offset đã commit trước đó và có thể đọc lại record.

Trong `onPartitionsRevoked`, chỉ commit offset kế tiếp sau các record đã xử lý liên tục. Nếu record 101 và 103 đã hoàn tất nhưng 102 chưa hoàn tất, không được commit 104. Với xử lý song song, cần theo dõi completion theo từng partition và chỉ tiến offset qua phần đầu liên tục đã hoàn tất.

Trong `onPartitionsLost`, không cố gọi `commitSync()` để “giữ” tiến độ. Việc commit có thể bị coordinator từ chối do generation/member đã thay đổi; quan trọng hơn, partition đã thuộc về owner mới và việc xử lý tiếp phải dựa trên tiến độ đã commit trước đó. Nếu side effect cũ đã hoàn tất, deduplication/fencing phải giúp lần đọc lại an toàn.

## 9. Kafka transaction bảo vệ luồng Kafka-to-Kafka

Nếu consumer đọc record rồi ghi kết quả sang topic Kafka khác, Kafka transaction có thể kết hợp output records và input offsets trong một transaction nguyên tử:

1. Consumer đọc input record.
2. Producer transactional gửi output record.
3. Producer gọi `sendOffsetsToTransaction(offsets, consumer.groupMetadata())`.
4. Producer commit transaction.

Khi group generation thay đổi, coordinator có thể từ chối việc commit offset của consumer cũ. Transaction sẽ không commit thành công như một kết quả hoàn chỉnh; consumer downstream cấu hình `isolation.level=read_committed` chỉ nhìn thấy output đã commit.

Transaction Kafka phù hợp cho pipeline Kafka-to-Kafka. Nó không tự bao gồm ghi database, gửi email hoặc gọi API ngoài Kafka. Những side effect đó vẫn cần fencing/idempotency ở hệ thống đích. Không gọi `consumer.commitSync()` riêng cho input offsets nếu đang dùng `sendOffsetsToTransaction` để bảo đảm tính nguyên tử.

## 10. Static membership và cooperative rebalance có thay thế fencing không?

`group.instance.id` bật static membership và giúp một instance giữ danh tính ổn định qua một số lần restart. Cooperative assignor chuyển partition theo từng phần thay vì thu hồi toàn bộ assignment, giúp giảm gián đoạn và công việc lặp lại.

Hai cơ chế này cải thiện độ ổn định của group nhưng **không bảo vệ hệ thống ngoài Kafka khỏi worker cũ đang chạy**:

- Static membership không dừng một thread cũ đã gửi request tới database.
- Cooperative rebalance không bảo đảm task cũ kết thúc trước khi partition được giao lại trong mọi tình huống mất quyền sở hữu.
- Một instance ID ổn định không phải fencing token cho database/API.
- Heartbeat và poll timeout quản lý membership; chúng không rollback side effect đã xảy ra.

Hãy dùng static membership/cooperative assignor để giảm rebalance không cần thiết, đồng thời dùng fencing và idempotency để bảo vệ dữ liệu nghiệp vụ.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Worker cũ ghi sau khi consumer mới xử lý | Task chạy ngoài poll thread vẫn tiếp tục sau revoke/lost | Gắn ownership token vào task và kiểm tra fencing tại nơi ghi dữ liệu |
| `onPartitionsRevoked` không được gọi trước khi mất partition | Consumer đã mất quyền sở hữu trước khi nhận callback revoke | Dùng `onPartitionsLost` nếu client hỗ trợ; cleanup task và không commit |
| `Future.cancel(true)` nhưng side effect vẫn xảy ra | Tác vụ không phản ứng với interrupt hoặc request đã được gửi | Không dựa vào cancel làm bảo đảm; dùng fencing ở database/API |
| Consumer cũ release lease của consumer mới | Release không kiểm tra epoch/owner | Dùng conditional release theo đúng token đã cấp |
| Event cũ ghi đè trạng thái mới | Có dedup event nhưng không kiểm tra entity version hoặc owner epoch | Kết hợp fencing, event ID và version condition |
| Commit offset thất bại sau rebalance | Consumer không còn là owner hợp lệ | Không retry mù; để consumer mới đọc từ offset đã commit và xử lý idempotent |
| Callback rebalance bị block quá lâu | Drain worker hoặc gọi ownership service không có deadline | Đặt deadline, giới hạn số task và tiếp tục cleanup theo cơ chế ngoài callback nếu cần |
| Hai consumer cùng nhận cùng epoch | Acquire lease không nguyên tử hoặc storage ownership không có khóa | Dùng transaction/atomic update để tăng epoch và cấp owner duy nhất |
| Dùng generation ID làm token bền vững cho mọi hệ thống | Generation có phạm vi group lifecycle và phụ thuộc trạng thái coordinator | Dùng epoch do hệ thống ownership lưu bền vững; chỉ dùng group metadata như ngữ cảnh bổ sung |

## 12. Quy trình kiểm tra trong staging

Có thể tạo một bài thử nghiệm để xác minh fencing:

1. Chạy consumer A và gán một partition cho A.
2. A nhận token epoch 41 và bắt đầu task có thời gian xử lý dài.
3. Kích hoạt rebalance có kiểm soát để partition được giao cho consumer B.
4. B acquire epoch 42 và xử lý lại record chưa commit.
5. Cho worker A hoàn tất muộn sau khi B đã acquire epoch 42.
6. Xác minh database/API từ chối write mang epoch 41.
7. Xác minh write epoch 42 được chấp nhận và trạng thái không bị ghi đè bởi owner cũ.
8. Lặp lại với lỗi giữa xử lý và commit để xác minh event ID deduplication.

Ghi lại group ID, topic-partition, owner ID, epoch, event ID, offset, thời điểm revoke/lost và kết quả ghi. Không chỉ kiểm tra log của consumer; cần xác minh trạng thái cuối cùng trong hệ thống nhận side effect.

## 13. Checklist production

- Phân biệt rõ `onPartitionsRevoked` và `onPartitionsLost` theo Kafka client version.
- Theo dõi task đang chạy theo từng topic-partition.
- Ngừng dispatch ngay khi partition bắt đầu revoke/lost.
- Dùng deadline để drain worker; không block callback vô hạn.
- Chỉ commit offset liên tục đã xử lý thành công trong callback revoke khi còn quyền sở hữu.
- Không commit offset trong callback lost.
- Gắn token ownership vào task tại thời điểm dispatch.
- Cấp fencing epoch mới một cách nguyên tử khi partition được giao.
- Kiểm tra epoch/owner cùng transaction với side effect.
- Conditional release để owner cũ không xóa lease của owner mới.
- Kết hợp event ID deduplication và entity version để ngăn duplicate/ghi đè cũ.
- Với Kafka-to-Kafka, cân nhắc transaction để commit output và input offset nguyên tử.
- Kiểm thử stale worker hoàn tất sau khi partition đã được giao cho owner mới.
- Theo dõi rebalance rate, lost partition, worker task còn chạy, commit failure và stale-write rejection.

## 14. Ghi nhớ

`onPartitionsRevoked` là cơ hội bàn giao có trật tự: ngừng dispatch, drain trong deadline và commit offset an toàn nếu còn quyền sở hữu. `onPartitionsLost` báo rằng partition đã mất; không commit ở đây và phải ngăn worker cũ tạo side effect mới.

Hủy task và kiểm tra cờ giúp giảm công việc còn chạy nhưng không ngăn chắc chắn một request bên ngoài đã bắt đầu hoàn tất muộn. Để bảo vệ dữ liệu, cấp fencing epoch mới cho mỗi lần ownership và buộc hệ thống nhận side effect kiểm tra token một cách nguyên tử. Kết hợp fencing với event ID, entity version và Kafka transaction đúng phạm vi sẽ giúp consumer group chịu được rebalance mà không để chủ sở hữu cũ ghi đè kết quả mới.
