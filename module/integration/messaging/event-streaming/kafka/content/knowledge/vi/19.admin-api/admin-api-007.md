# Điều chỉnh offset bằng Admin API với điều kiện vận hành an toàn

Kafka Admin API cho phép ứng dụng quản trị đọc và thay đổi committed offset của consumer group mà không cần khởi chạy một consumer để đọc dữ liệu. Trong Java, `AdminClient` cung cấp các thao tác như `listConsumerGroupOffsets()`, `describeConsumerGroups()` và `alterConsumerGroupOffsets()`.

Thay đổi offset là thao tác quản trị có ảnh hưởng trực tiếp đến vị trí consumer sẽ đọc tiếp. Đặt offset lùi có thể khiến ứng dụng xử lý lại sự kiện; đặt offset tiến có thể khiến ứng dụng bỏ qua sự kiện chưa xử lý. Vì vậy, trước khi gọi API thay đổi, cần dừng consumer, xác nhận group không còn thành viên hoạt động, kiểm tra offset đích và lưu lại trạng thái ban đầu để đối chiếu hoặc khôi phục.

Bài này trình bày cách đọc, lập kế hoạch, áp dụng và xác minh thay đổi offset bằng Java Admin API; đồng thời giải thích các điều kiện vận hành, lỗi thường gặp và cách tích hợp vào quy trình quản trị.

## 1. Offset của consumer group là gì?

Kafka lưu committed offset theo từng cặp topic-partition và consumer group. Offset đã commit là vị trí kế tiếp mà group sẽ đọc khi tiếp tục từ checkpoint đó.

Ví dụ, group `orders-service` đã commit offset 120 cho partition 0 của topic `orders`. Consumer tiếp theo của group sẽ tiếp tục từ vị trí 120. Offset 120 không có nghĩa bản ghi cuối cùng đã xử lý là 120; với cách đọc tuần tự, bản ghi đã xử lý trước đó thường mang offset 119.

Một group có thể có offset khác nhau ở từng partition:

| Topic | Partition | Committed offset |
|---|---:|---:|
| orders | 0 | 120 |
| orders | 1 | 98 |
| orders | 2 | 205 |

Điều chỉnh offset là thay đổi checkpoint mà Kafka lưu cho group. Nó không sửa, xóa hay di chuyển record trong partition log.

## 2. Khi nào cần điều chỉnh offset?

Các trường hợp quản trị thường gặp:

- **Đọc lại một khoảng dữ liệu:** consumer đã xử lý sai do lỗi ứng dụng và cần phát lại sự kiện từ một offset trước đó.
- **Bỏ qua dữ liệu đã được xử lý theo quy trình khác:** một khoảng record đã được xử lý hoặc đối soát bên ngoài, và người vận hành muốn chuyển checkpoint đến vị trí mới.
- **Phục hồi sau sự cố:** group cần bắt đầu từ checkpoint đã được xác định sau khi điều tra dữ liệu.
- **Kiểm thử hoặc diễn tập:** tạo group thử nghiệm, thay đổi offset để quan sát hành vi đọc lại.
- **Đồng bộ checkpoint với một hệ thống khác:** chỉ khi có quy trình xác định rõ quan hệ giữa trạng thái bên ngoài và offset Kafka.

Không nên thay offset chỉ để làm consumer lag về 0. Lag là tín hiệu cần điều tra; nhảy offset về cuối log có thể che giấu dữ liệu chưa xử lý và gây mất tác động nghiệp vụ.

## 3. Điều kiện an toàn trước khi gọi Admin API

### 3.1. Dừng consumer thuộc group

Trước khi thay đổi offset, dừng mọi consumer đang tham gia group đích. Điều này bao gồm:

- Các instance ứng dụng chạy trong Kubernetes, VM, container hoặc máy chủ.
- Consumer chạy thủ công hoặc trong môi trường kiểm thử.
- Tiến trình tự động khởi động lại bởi Deployment, systemd, supervisor hoặc job scheduler.
- Consumer tạm thời có cùng group ID do một nhóm vận hành khác khởi chạy.

Nếu chỉ dừng một instance nhưng orchestrator tự khởi động lại hoặc còn instance khác, group có thể tiếp tục hoạt động và thay đổi offset sẽ không an toàn.

### 3.2. Group phải ở trạng thái rỗng

`alterConsumerGroupOffsets()` yêu cầu consumer group không có thành viên đang hoạt động. Nếu group còn thành viên, broker có thể từ chối request bằng lỗi `GroupNotEmptyException`.

Dùng `describeConsumerGroups()` để kiểm tra trạng thái. Chỉ tiếp tục khi trạng thái group là `EMPTY`. Nếu group đang rebalance, stable hoặc còn thành viên, hãy dừng consumer và chờ group chuyển về `EMPTY`, sau đó kiểm tra lại.

Với static membership, consumer có thể còn được giữ trong group trong một khoảng thời gian sau khi tiến trình mất kết nối. Không dựa vào việc process đã dừng để kết luận group đã rỗng; hãy xác nhận trạng thái qua broker.

### 3.3. Xác định đúng topic, partition và offset đích

Trước khi áp dụng, cần biết:

- Group ID chính xác.
- Topic và partition cần thay đổi.
- Committed offset hiện tại.
- Offset sớm nhất còn được lưu (log start/beginning offset).
- Offset cuối hiện có (log end offset).
- Offset đích và lý do nghiệp vụ cho giá trị đó.

Offset đích phải nằm trong phạm vi hợp lệ của partition tại thời điểm áp dụng. Về nguyên tắc, vị trí đọc có thể nằm từ offset sớm nhất còn lưu đến log end offset. Offset đích bằng log end offset nghĩa là consumer bắt đầu ở cuối log tại thời điểm kiểm tra. Offset cũ hơn log start có thể không còn đọc được do retention; offset vượt log end không phải vị trí hợp lệ cho dữ liệu hiện có.

Log có thể thay đổi trong khoảng thời gian giữa lúc kiểm tra và lúc áp dụng, đặc biệt khi retention tiếp tục xóa segment. Vì vậy, kiểm tra phạm vi offset sát thời điểm thực hiện và xác minh lại sau khi thay đổi.

### 3.4. Lưu checkpoint cũ và chuẩn bị kế hoạch khôi phục

Trước khi sửa, xuất hoặc lưu lại committed offset ban đầu theo từng partition. Ghi rõ:

- Thời điểm thực hiện và người thực hiện.
- Cluster/bootstrap endpoint và môi trường.
- Group ID, topic, partition.
- Offset trước thay đổi và offset đích.
- Lý do, ticket hoặc phê duyệt nghiệp vụ liên quan.
- Cách khôi phục nếu kết quả không đúng dự kiến.

Việc lưu checkpoint cũ giúp đặt lại offset về vị trí trước đó nếu cần. Tuy nhiên, nếu consumer đã chạy và tạo side effect sau khi thay đổi, khôi phục offset cũ có thể khiến sự kiện được xử lý lại. Hệ thống đích vẫn cần idempotency.

## 4. Các API cần biết trong AdminClient

| API | Mục đích |
|---|---|
| `describeConsumerGroups(groupIds)` | Kiểm tra trạng thái và thông tin thành viên group |
| `listConsumerGroupOffsets(groupId)` | Đọc committed offset theo partition |
| `alterConsumerGroupOffsets(groupId, offsets)` | Đặt committed offset mới cho các partition chỉ định |
| `listOffsets(offsetSpecs)` | Lấy beginning/end offset để kiểm tra phạm vi |
| `deleteConsumerGroupOffsets(groupId, partitions)` | Xóa committed offset của các partition chỉ định |

`alterConsumerGroupOffsets()` đặt một vị trí đọc cụ thể. `deleteConsumerGroupOffsets()` xóa checkpoint đã lưu; khi consumer chạy lại, hành vi tiếp theo phụ thuộc `auto.offset.reset` nếu không còn offset hợp lệ. Hai thao tác này khác nhau và không nên dùng thay thế tùy tiện.

Admin API không có cờ `--dry-run` tương đương lệnh reset offset của CLI. Ứng dụng cần tự tạo bước preview: đọc trạng thái hiện tại, kiểm tra group, tính offset đích, hiển thị kế hoạch và yêu cầu người vận hành xác nhận trước khi gọi API thay đổi.

## 5. Chuẩn bị AdminClient trong Java

Ví dụ dưới đây sử dụng Kafka Java client. Thư viện client nên tương thích với broker đang chạy.

```java
import java.util.Properties;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;

public class KafkaAdminFactory {
    public static AdminClient create() {
        Properties props = new Properties();
        props.put(
            AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        props.put(
            AdminClientConfig.REQUEST_TIMEOUT_MS_CONFIG,
            "30000"
        );

        return AdminClient.create(props);
    }
}
```

Trong production, cấu hình thêm bảo mật TLS/SASL, truststore hoặc cơ chế xác thực được tổ chức sử dụng. Không ghi password hoặc secret trực tiếp vào source code. Tài khoản quản trị cần quyền đọc thông tin group/topic và quyền thay đổi offset của group theo ACL/authorizer trong cluster.

Đóng AdminClient sau khi sử dụng để giải phóng kết nối và tài nguyên:

```java
try (AdminClient admin = KafkaAdminFactory.create()) {
    // Thực hiện các thao tác quản trị tại đây.
}
```

## 6. Đọc trạng thái group và committed offset

Đầu tiên, xác nhận group đã rỗng:

```java
import java.util.List;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.ConsumerGroupDescription;
import org.apache.kafka.common.GroupState;

public static ConsumerGroupDescription requireEmptyGroup(
        AdminClient admin,
        String groupId
) throws Exception {
    ConsumerGroupDescription description = admin
        .describeConsumerGroups(List.of(groupId))
        .describedGroups()
        .get(groupId)
        .get(30, TimeUnit.SECONDS);

    if (description.state() != GroupState.EMPTY) {
        throw new IllegalStateException(
            "Consumer group must be EMPTY before altering offsets. State: "
                + description.state()
        );
    }

    return description;
}
```

Trạng thái `EMPTY` cho biết group không có consumer member đang hoạt động tại thời điểm broker trả kết quả. Nếu group chuyển trạng thái hoặc có consumer mới tham gia sau bước kiểm tra, cần dừng tiến trình đó và kiểm tra lại ngay trước khi thay đổi.

Đọc committed offset:

```java
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

public static Map<TopicPartition, OffsetAndMetadata> readGroupOffsets(
        AdminClient admin,
        String groupId
) throws Exception {
    return admin
        .listConsumerGroupOffsets(groupId)
        .partitionsToOffsetAndMetadata()
        .get(30, TimeUnit.SECONDS);
}
```

Kết quả là map theo topic-partition. Nếu một partition chưa có committed offset, partition đó có thể không xuất hiện trong map. Hãy phân biệt trường hợp này với offset bằng 0.

Ví dụ hiển thị checkpoint hiện tại:

```java
Map<TopicPartition, OffsetAndMetadata> current =
    readGroupOffsets(admin, "orders-service");

current.forEach((partition, metadata) ->
    System.out.printf(
        "%s-%d -> offset %d%n",
        partition.topic(),
        partition.partition(),
        metadata.offset()
    )
);
```

Không lấy offset của một partition rồi áp dụng cho tất cả partition. Mỗi partition có log và checkpoint độc lập.

## 7. Kiểm tra beginning offset và end offset

Có thể dùng `AdminClient.listOffsets()` với `OffsetSpec.earliest()` và `OffsetSpec.latest()` để kiểm tra giới hạn của partition.

```java
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.OffsetSpec;
import org.apache.kafka.common.TopicPartition;

public static long readEarliestOffset(
        AdminClient admin,
        TopicPartition partition
) throws Exception {
    return admin.listOffsets(
        Map.of(partition, OffsetSpec.earliest())
    ).partitionResult(partition)
     .get(30, TimeUnit.SECONDS)
     .offset();
}

public static long readLatestOffset(
        AdminClient admin,
        TopicPartition partition
) throws Exception {
    return admin.listOffsets(
        Map.of(partition, OffsetSpec.latest())
    ).partitionResult(partition)
     .get(30, TimeUnit.SECONDS)
     .offset();
}
```

Ví dụ kiểm tra offset đích:

```java
long earliest = readEarliestOffset(admin, partition);
long latest = readLatestOffset(admin, partition);
long target = 120L;

if (target < earliest || target > latest) {
    throw new IllegalArgumentException(
        "Target offset is outside the current log range: "
            + earliest + " .. " + latest
    );
}
```

`latest` là vị trí cuối log, tức vị trí kế tiếp sau các offset hiện có theo cách diễn giải của API. Nếu consumer bắt đầu tại vị trí này, nó không đọc lại các record hiện có trước vị trí đó. Với topic có giao dịch và consumer dùng `isolation.level=read_committed`, cần hiểu khác biệt giữa log end offset và last stable offset; kiểm tra phạm vi theo đúng isolation semantics của ứng dụng.

Với log compaction, không phải mọi số offset trong phạm vi đều còn một record. Một offset hợp lệ có thể trỏ đến khoảng trống do compaction; consumer sẽ đọc các record còn tồn tại tiếp theo.

## 8. Thay đổi offset bằng alterConsumerGroupOffsets

Ví dụ đặt partition 0 của topic `orders` về offset 120:

```java
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

public static void setGroupOffset(
        AdminClient admin,
        String groupId,
        TopicPartition partition,
        long targetOffset
) throws Exception {
    Map<TopicPartition, OffsetAndMetadata> offsets = Map.of(
        partition,
        new OffsetAndMetadata(targetOffset)
    );

    admin.alterConsumerGroupOffsets(groupId, offsets)
         .all()
         .get(30, TimeUnit.SECONDS);
}
```

Cách gọi:

```java
TopicPartition partition = new TopicPartition("orders", 0);

try (AdminClient admin = KafkaAdminFactory.create()) {
    requireEmptyGroup(admin, "orders-service");

    long earliest = readEarliestOffset(admin, partition);
    long latest = readLatestOffset(admin, partition);
    long target = 120L;

    if (target < earliest || target > latest) {
        throw new IllegalArgumentException("Offset đích ngoài phạm vi log");
    }

    setGroupOffset(admin, "orders-service", partition, target);
}
```

Đoạn mã là ví dụ minh họa. Trong quy trình thực tế, hãy đọc và lưu offset cũ, hiển thị kế hoạch cho người vận hành, kiểm tra group rỗng ngay trước thao tác và xác minh kết quả sau khi API hoàn tất. Không gọi thay đổi offset từ luồng xử lý record của consumer; đây là tác vụ quản trị riêng.

Nếu cần thay đổi nhiều partition, tạo map chứa chính xác các topic-partition và offset đích đã được duyệt. Không dùng một giá trị offset chung cho mọi partition trừ khi có căn cứ nghiệp vụ rõ ràng.

## 9. Xác minh sau khi thay đổi

Sau khi API trả về thành công, đọc committed offset một lần nữa:

```java
Map<TopicPartition, OffsetAndMetadata> after =
    readGroupOffsets(admin, "orders-service");

OffsetAndMetadata actual = after.get(partition);

if (actual == null || actual.offset() != target) {
    throw new IllegalStateException(
        "Offset verification failed for " + partition
    );
}
```

Việc xác minh cần thực hiện cho từng partition đã thay đổi. Nếu thao tác nhiều partition và một kết quả lỗi, không giả định toàn bộ yêu cầu đã rollback. Hãy đọc lại tất cả partition trong phạm vi để xác định partition nào đã thay đổi, partition nào chưa thay đổi và xử lý tiếp theo dựa trên trạng thái thực tế.

Sau khi xác minh:

1. Lưu kết quả offset mới cùng thời điểm thực hiện.
2. Xác nhận group vẫn rỗng trong lúc chuẩn bị hoàn tất thao tác.
3. Khởi động lại consumer theo quy trình triển khai đã kiểm soát.
4. Theo dõi record đầu tiên được đọc, consumer lag, lỗi offset và side effect ở hệ thống đích.
5. Đối chiếu kết quả với mục tiêu vận hành đã duyệt.

Offset mới chỉ thay đổi vị trí đọc của group. Nó không chứng minh các record trước đó đã được xử lý hoặc các record bị bỏ qua không còn giá trị nghiệp vụ.

## 10. Ví dụ quy trình quản trị có preview

Vì Admin API không cung cấp chế độ dry-run, có thể thiết kế một quy trình hai pha:

**Pha 1 — Preview**

- Nhận group ID, danh sách partition và offset đích.
- Kiểm tra group state.
- Đọc committed offset hiện tại.
- Đọc beginning/end offset của từng partition.
- Kiểm tra offset đích trong phạm vi hợp lệ.
- Hiển thị bảng trước/sau dự kiến và lý do thay đổi.
- Ghi lại checkpoint cũ.
- Chờ người vận hành xác nhận đúng cluster, group và partition.

Ví dụ preview:

| Partition | Offset hiện tại | Offset đích | Thay đổi |
|---|---:|---:|---|
| orders-0 | 150 | 120 | Đọc lại từ vị trí sớm hơn |
| orders-1 | 98 | 98 | Giữ nguyên |
| orders-2 | 205 | 220 | Bỏ qua đến vị trí mới |

**Pha 2 — Apply**

- Dừng hoặc giữ dừng toàn bộ consumer thuộc group.
- Kiểm tra group vẫn `EMPTY`.
- Kiểm tra lại offset range.
- Gọi `alterConsumerGroupOffsets()` cho các partition đã được duyệt.
- Đọc lại offset và so sánh với giá trị đích.
- Lưu audit record.
- Cho phép triển khai consumer chạy lại theo quy trình vận hành.

Preview chỉ là bản kế hoạch dựa trên trạng thái được đọc tại thời điểm đó. Nếu retention, assignment hoặc trạng thái group thay đổi trước lúc apply, cần tạo preview mới hoặc dừng thao tác để đánh giá lại.

## 11. Thay đổi offset lùi và tiến có hệ quả gì?

| Hướng thay đổi | Ví dụ | Hệ quả |
|---|---|---|
| Lùi offset | 150 xuống 120 | Consumer có thể đọc lại record từ offset 120 trở đi |
| Tiến offset | 150 lên 180 | Consumer bỏ qua các record từ 150 đến trước 180 |
| Đặt tại end offset | 150 lên 220 khi latest là 220 | Consumer chờ dữ liệu mới sau vị trí cuối log hiện tại |
| Đặt tại earliest | Chuyển về beginning offset hiện tại | Consumer đọc lại từ dữ liệu sớm nhất còn được lưu |

### 11.1. Lùi offset: xử lý lại sự kiện

Lùi offset thường được dùng khi cần replay. Tuy nhiên, một sự kiện có thể đã tạo side effect trước đó, ví dụ đã trừ tiền, gửi email hoặc cập nhật trạng thái đơn hàng. Nếu consumer đọc lại và thực hiện side effect lần nữa, hệ thống có thể bị trùng tác động.

Cần có event ID ổn định, idempotency key, unique constraint hoặc inbox table để nhận diện sự kiện đã xử lý. Nếu cần replay để sửa lỗi dữ liệu, nên xác định phạm vi record và chiến lược xử lý trùng trước khi thay đổi offset.

### 11.2. Tiến offset: bỏ qua sự kiện

Tiến offset có thể bỏ qua record mà ứng dụng chưa từng xử lý. Chỉ thực hiện khi đã đối soát dữ liệu hoặc có quyết định nghiệp vụ chấp nhận bỏ qua khoảng record đó.

Ghi lại khoảng offset bị bỏ qua, partition liên quan, lý do và người phê duyệt. Đối với dữ liệu quan trọng, nên lưu bản xuất hoặc cách truy xuất lại record để phục vụ kiểm toán.

## 12. Xử lý lỗi và tình huống cạnh tranh

| Lỗi/tình huống | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `GroupNotEmptyException` | Group còn consumer member hoặc đang tham gia group | Dừng tất cả consumer, chờ group về EMPTY rồi thử lại |
| `GroupIdNotFoundException` hoặc group không được mô tả như dự kiến | Group ID sai, group chưa có metadata hoặc cluster không đúng | Kiểm tra bootstrap server và group ID; xác minh chính sách của phiên bản |
| `TopicAuthorizationException` | Thiếu quyền đọc metadata/offset của topic | Kiểm tra ACL và quyền của principal |
| `GroupAuthorizationException` | Thiếu quyền mô tả hoặc thay đổi group | Cấp đúng quyền quản trị group theo chính sách |
| `TimeoutException` | Broker/coordinator chậm, mất kết nối hoặc request chưa hoàn tất trong thời hạn | Kiểm tra trạng thái cluster; đọc lại offset trước khi quyết định retry |
| Offset đích ngoài phạm vi | Offset nhỏ hơn log start hoặc lớn hơn log end | Đọc lại beginning/end offset và xác định vị trí hợp lệ |
| Kết quả nhiều partition không đồng nhất | Một số partition thành công, số khác lỗi hoặc trạng thái thay đổi | Đọc lại toàn bộ partition và lập kế hoạch sửa phần còn thiếu |
| Consumer chạy lại trước khi apply | Deployment hoặc operator khởi động group trở lại | Dừng consumer và xác nhận group EMPTY ngay trước khi thay đổi |

Một timeout không chứng minh request chắc chắn thất bại. Broker có thể đã áp dụng thay đổi nhưng phản hồi không đến được client. Khi gặp timeout, đọc lại committed offset trước khi gửi lại request. Nếu offset đã bằng giá trị đích, thao tác có thể đã thành công; nếu chưa, kiểm tra group state và điều kiện rồi mới quyết định thử lại.

Admin API trả kết quả bất đồng bộ. Với nhiều partition, cần theo dõi kết quả từng partition hoặc dùng kết quả tổng hợp và sau đó đọc lại trạng thái thực tế. Không giả định một request nhiều partition có tính nguyên tử như một transaction bao trùm mọi partition.

## 13. Xóa committed offset khác với đặt offset

`deleteConsumerGroupOffsets(groupId, partitions)` xóa committed offset của các partition chỉ định. Group cũng phải ở trạng thái rỗng trước thao tác này. Khi consumer chạy lại, nếu không có offset hợp lệ, nó áp dụng `auto.offset.reset` như `earliest` hoặc `latest`.

Ví dụ:

```java
admin.deleteConsumerGroupOffsets(
    "orders-service",
    java.util.Set.of(new TopicPartition("orders", 0))
).all().get(30, TimeUnit.SECONDS);
```

Thao tác này không có nghĩa là đặt offset về 0. Nếu log start hiện tại là 500, `auto.offset.reset=earliest` sẽ bắt đầu từ offset sớm nhất còn tồn tại, không phải offset 0. Nếu cấu hình là `latest`, consumer sẽ bắt đầu ở cuối log theo semantics của client.

Chỉ xóa offset khi chủ đích là bỏ checkpoint đã lưu và để client áp dụng chính sách reset. Nếu biết chính xác vị trí cần đọc, `alterConsumerGroupOffsets()` thể hiện rõ ràng hơn.

## 14. Tích hợp vào ứng dụng Spring

Trong ứng dụng Spring Boot, có thể tạo một bean quản trị dựa trên `AdminClient` hoặc dùng cơ chế quản lý Kafka Admin phù hợp với phiên bản Spring Kafka. Một tác vụ quản trị offset nên chạy trong service/job riêng, có xác thực người thực hiện, audit log và kiểm tra điều kiện trước khi apply.

Ví dụ cấu hình client trong Spring Boot:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    admin:
      fail-fast: true
```

Cấu hình này minh họa việc khai báo broker cho thành phần Kafka Admin của Spring; không tự động tạo quy trình reset offset an toàn. Service quản trị vẫn phải kiểm tra group, offset hiện tại, offset range và xác minh sau khi thay đổi.

Không gọi thay đổi offset mỗi khi ứng dụng khởi động. Một tác vụ tự động lặp lại có thể liên tục ghi đè checkpoint do consumer đã tạo. Chỉ kích hoạt khi có yêu cầu quản trị cụ thể và được kiểm soát.

## 15. Checklist trước và sau khi apply

**Trước khi thay đổi**

- [ ] Đúng cluster và bootstrap endpoint.
- [ ] Đúng group ID.
- [ ] Đã dừng mọi consumer thuộc group.
- [ ] Group state là `EMPTY`.
- [ ] Đã lưu committed offset hiện tại theo từng partition.
- [ ] Đã xác định beginning/end offset và offset đích.
- [ ] Đã đánh giá tác động replay hoặc bỏ qua dữ liệu.
- [ ] Đã có lý do và xác nhận vận hành.

**Sau khi thay đổi**

- [ ] API hoàn tất hoặc đã xác định trạng thái sau timeout.
- [ ] Đã đọc lại committed offset của từng partition.
- [ ] Offset thực tế khớp với kế hoạch.
- [ ] Đã lưu audit record và checkpoint mới.
- [ ] Consumer được khởi động lại có kiểm soát.
- [ ] Đã theo dõi lag, lỗi xử lý và side effect sau khi chạy lại.

## 16. Những điểm cần nhớ

- `alterConsumerGroupOffsets()` thay đổi committed offset theo từng topic-partition của consumer group.
- Group cần ở trạng thái `EMPTY`; dừng process chưa đủ, phải xác nhận broker không còn member hoạt động.
- Admin API không có dry-run tích hợp. Hãy tự tạo preview, lưu offset cũ và xác nhận trước khi apply.
- Kiểm tra offset đích trong phạm vi log hiện tại; retention có thể làm beginning offset thay đổi.
- Lùi offset có thể gây replay và side effect trùng; tiến offset có thể bỏ qua sự kiện chưa xử lý.
- Timeout hoặc lỗi một phần cần được xác minh bằng cách đọc lại committed offset trước khi retry.
- `deleteConsumerGroupOffsets()` xóa checkpoint để client áp dụng `auto.offset.reset`; nó không giống việc đặt offset về một giá trị cụ thể.

Điều chỉnh offset bằng Admin API là thao tác quản trị checkpoint của consumer group. Quy trình an toàn cần dừng consumer, xác nhận group rỗng, lưu trạng thái cũ, preview phạm vi thay đổi và xác minh từng partition sau khi áp dụng.

