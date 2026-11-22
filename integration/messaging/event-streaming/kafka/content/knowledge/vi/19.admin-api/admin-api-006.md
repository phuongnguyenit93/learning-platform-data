# Liệt kê consumer group, đọc offset và tính lag

Kafka Admin API cho phép một ứng dụng quản trị liệt kê consumer group, xem trạng thái thành viên, đọc committed offset và lấy offset đầu/cuối của từng partition. Từ các dữ liệu này, ứng dụng có thể tính consumer lag, phát hiện group không còn hoạt động, partition chưa có committed offset và tình huống consumer đã tụt sau log start do retention.

Bài này xây dựng một công cụ Java dùng Kafka AdminClient để liệt kê group, mô tả member/assignment, đọc offset đã commit, lấy log start offset, log end offset và Last Stable Offset (LSO), sau đó tính lag theo từng topic-partition. Công cụ cũng giải thích giới hạn của phép đo: Admin API đọc committed offset chứ không đọc được vị trí hiện tại trong bộ nhớ của consumer, và lag theo offset không phải lúc nào cũng bằng số record thực tế còn chờ xử lý.

## 1. Consumer group và Admin API

Consumer group là tập consumer cùng dùng một group ID để chia sẻ việc đọc topic. Kafka phân phối partition cho các member trong group. Mỗi partition có committed offset riêng cho group; offset này là vị trí tiếp theo mà group sẽ đọc khi khôi phục.

Admin API cung cấp các thao tác chính:

| API | Dữ liệu trả về | Mục đích |
|---|---|---|
| listConsumerGroups() | Danh sách group và một số metadata cơ bản | Liệt kê group trong cluster |
| describeConsumerGroups(groupIds) | State, coordinator, assignor và members | Xem group đang stable, rebalance hay empty |
| listConsumerGroupOffsets(groupId) | Map topic-partition sang OffsetAndMetadata | Đọc committed offset |
| listOffsets(partitions, options) | Offset theo OffsetSpec | Lấy earliest, latest hoặc timestamp offset |
| describeTopics(topicNames) | Partition, leader và replica metadata | Đối chiếu topology của topic |

AdminClient là client quản trị độc lập với KafkaConsumer. Nó không tham gia group, không nhận partition và không làm thay đổi committed offset khi chỉ gọi các API đọc.

## 2. Phân biệt committed offset, consumer position và log end offset

Ba loại offset thường bị nhầm lẫn:

| Khái niệm | Ý nghĩa | Ai biết/đọc được? |
|---|---|---|
| Committed offset | Vị trí kế tiếp group đã xác nhận để khôi phục sau restart | Admin API đọc được từ group coordinator |
| Consumer position | Vị trí kế tiếp consumer instance sẽ đọc trong phiên hiện tại; có thể đã poll nhưng chưa commit | KafkaConsumer.position() đọc được trong chính consumer instance |
| Log end offset (LEO) | Vị trí kế tiếp được append vào partition log | Admin API listOffsets(latest) đọc được |

Admin API không thể đọc consumer position trong bộ nhớ của một instance khác. Vì vậy phép tính bằng committed offset phản ánh khoảng cách từ offset đã xác nhận đến cuối log, không nhất thiết là số record consumer chưa hề poll hoặc chưa xử lý.

Ví dụ:

| Thành phần | Offset |
|---|---:|
| Consumer đã poll và xử lý đến | 120 |
| Consumer position | 121 |
| Committed offset | 110 |
| Log end offset | 150 |

Committed-offset lag là 150 - 110 = 40. Tuy nhiên, consumer đã xử lý đến offset 120; 10 offset chênh lệch là công việc đã làm nhưng chưa commit. Nếu ứng dụng commit theo batch, lag nhìn từ Admin API có thể cao hơn backlog thực tế đang chờ xử lý.

## 3. Công thức tính consumer lag

Với một topic-partition:

~~~text
committedOffset = offset đã commit của consumer group
logEndOffset    = OffsetSpec.latest() với READ_UNCOMMITTED
consumerLag     = logEndOffset - committedOffset
~~~

Ví dụ committed offset là 120 và log end offset là 175:

~~~text
consumerLag = 175 - 120 = 55 offsets
~~~

Giá trị này là khoảng cách offset, không đảm bảo có đúng 55 record còn tồn tại. Topic compacted hoặc topic có record bị xóa theo retention có thể có khoảng trống offset. Nếu cần đếm record thực sự còn đọc được, phải scan dữ liệu hoặc dùng metric/telemetry phù hợp; không thể suy ra số record chính xác chỉ từ phép trừ offset.

### 3.1. Log start, LEO và LSO

Ngoài committed offset, nên đọc thêm ba mốc:

| Mốc | Cách lấy | Ý nghĩa |
|---|---|---|
| Log start offset | OffsetSpec.earliest() | Offset sớm nhất còn giữ trong partition |
| Log end offset (LEO) | OffsetSpec.latest() với READ_UNCOMMITTED | Ranh giới cuối log, bao gồm dữ liệu transactional chưa hoàn tất |
| Last Stable Offset (LSO) | OffsetSpec.latest() với READ_COMMITTED | Ranh giới an toàn cho consumer read_committed; không đi qua transaction đang mở |

Từ đó có hai cách quan sát:

~~~text
logEndLag    = LEO - committedOffset
readCommittedLag = LSO - committedOffset
~~~

LEO lag cho thấy khoảng cách tới cuối log. LSO lag gần hơn với lượng dữ liệu mà consumer read_committed có thể đọc tại thời điểm đo. Nếu có transaction đang mở, LSO có thể thấp hơn LEO; phần chênh lệch là vùng chưa ổn định mà read_committed chưa thể đi qua.

Nếu committed offset nhỏ hơn log start offset, consumer đã tụt sau dữ liệu bị retention xóa. Nếu committed offset lớn hơn LEO, cần điều tra log truncation, offset reset thủ công hoặc trạng thái bất thường; không tự động ép lag về 0 để che vấn đề.

## 4. Chuẩn bị Java và Maven

Yêu cầu:

| Thành phần | Phiên bản gợi ý |
|---|---|
| JDK | 17 trở lên |
| Maven | 3.8 trở lên |
| Kafka client | 3.9.1 trong ví dụ |
| Kafka cluster | Broker có listener truy cập được từ máy chạy công cụ |

Tạo project Maven và thêm dependency:

~~~xml
<dependency>
    <groupId>org.apache.kafka</groupId>
    <artifactId>kafka-clients</artifactId>
    <version>3.9.1</version>
</dependency>
~~~

Chọn Kafka client tương thích với cluster và dependency management của dự án. Các ví dụ sử dụng API Kafka client hiện đại; nếu dự án đang dùng client cũ, kiểm tra chữ ký API theo đúng phiên bản trước khi áp dụng.

## 5. Cấu hình AdminClient

AdminClient cần bootstrap server và cấu hình bảo mật tương tự producer/consumer. Đưa endpoint và thông tin xác thực ra ngoài source code.

~~~java
Properties properties = new Properties();
properties.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
        System.getenv().getOrDefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"));
properties.put(AdminClientConfig.CLIENT_ID_CONFIG, "consumer-group-lag-reporter");
properties.put("security.protocol",
        System.getenv().getOrDefault("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"));
properties.put(AdminClientConfig.REQUEST_TIMEOUT_MS_CONFIG, "30000");
properties.put(AdminClientConfig.DEFAULT_API_TIMEOUT_MS_CONFIG, "30000");
~~~

Với cluster bảo mật, cấu hình thêm SASL/SSL, truststore hoặc credential từ secret manager. Không commit password, JAAS config hay private key vào Git và không ghi toàn bộ Properties ra log.

## 6. Liệt kê tất cả consumer group

API listConsumerGroups() trả về danh sách ConsumerGroupListing. Kết quả có thể chứa group đang hoạt động và group không có member nhưng vẫn còn committed offset.

~~~java
try (Admin admin = Admin.create(properties)) {
    Collection<ConsumerGroupListing> groups =
            admin.listConsumerGroups()
                    .all()
                    .get(30, TimeUnit.SECONDS);

    for (ConsumerGroupListing group : groups) {
        System.out.printf("groupId=%s%n", group.groupId());
    }
}
~~~

Phương thức all() trả KafkaFuture; get(timeout) chờ kết quả với giới hạn thời gian. Trong ứng dụng quản trị, nên đặt timeout rõ ràng và xử lý TimeoutException, ExecutionException, InterruptedException.

Không đồng nhất “không có member đang chạy” với “group không tồn tại”. Một group state EMPTY vẫn có thể còn committed offset và consumer lag cần theo dõi.

## 7. Xem state và member assignment

Sau khi có group ID, gọi describeConsumerGroups:

~~~java
Map<String, ConsumerGroupDescription> descriptions =
        admin.describeConsumerGroups(List.of(groupId))
                .all()
                .get(30, TimeUnit.SECONDS);

ConsumerGroupDescription description = descriptions.get(groupId);
System.out.printf("group=%s state=%s coordinator=%s assignor=%s%n",
        description.groupId(),
        description.state(),
        description.coordinator(),
        description.partitionAssignor());

for (MemberDescription member : description.members()) {
    System.out.printf("member=%s clientId=%s host=%s assignment=%s%n",
            member.consumerId(),
            member.clientId(),
            member.host(),
            member.assignment().topicPartitions());
}
~~~

Thông tin member cho biết consumer nào đang tham gia và partition nào được giao. Nó không cung cấp consumer position hay số record đang nằm trong worker queue của ứng dụng.

Một số trạng thái thường gặp:

| State | Ý nghĩa tổng quát |
|---|---|
| STABLE | Group đã hoàn tất phân phối partition |
| PREPARING_REBALANCE | Group đang chuẩn bị rebalance |
| COMPLETING_REBALANCE | Group đang hoàn tất assignment |
| EMPTY | Không có member hoạt động; committed offset vẫn có thể còn |
| DEAD | Group đã bị xóa hoặc không còn tồn tại trong coordinator |
| UNKNOWN | Client không xác định được state |

Tên state và tập trạng thái có thể mở rộng theo phiên bản Kafka và group protocol. Khi group đang rebalance, assignment và offset có thể thay đổi trong lúc công cụ đang đọc; nên đo lại sau khi group ổn định.

## 8. Đọc committed offset bằng Admin API

API listConsumerGroupOffsets(groupId) trả về map topic-partition và OffsetAndMetadata:

~~~java
Map<TopicPartition, OffsetAndMetadata> committed =
        admin.listConsumerGroupOffsets(groupId)
                .partitionsToOffsetAndMetadata()
                .get(30, TimeUnit.SECONDS);

for (Map.Entry<TopicPartition, OffsetAndMetadata> entry : committed.entrySet()) {
    TopicPartition partition = entry.getKey();
    OffsetAndMetadata metadata = entry.getValue();
    System.out.printf("topic=%s partition=%d committedOffset=%d metadata=%s%n",
            partition.topic(),
            partition.partition(),
            metadata.offset(),
            metadata.metadata());
}
~~~

OffsetAndMetadata.offset() là vị trí kế tiếp cần đọc. Ví dụ consumer đã xử lý record offset 99 và commit thành công thì committed offset thường là 100.

Map có thể rỗng nếu group chưa commit offset cho partition nào. Không được mặc định offset 0 trong trường hợp này; consumer có thể áp dụng auto.offset.reset là earliest, latest hoặc none. Admin API không thể suy ra chính sách reset của consumer chỉ từ committed offset.

## 9. Lấy log end offset bằng listOffsets

Để tính lag, cần lấy latest offset của các partition. Kafka Admin API hỗ trợ gửi nhiều partition trong một request:

~~~java
Set<TopicPartition> partitions = committed.keySet();

Map<TopicPartition, OffsetSpec> request = new HashMap<>();
for (TopicPartition partition : partitions) {
    request.put(partition, OffsetSpec.latest());
}

Map<TopicPartition, ListOffsetsResult.ListOffsetsResultInfo> latest =
        admin.listOffsets(request).all().get(30, TimeUnit.SECONDS);

for (Map.Entry<TopicPartition, ListOffsetsResult.ListOffsetsResultInfo> entry
        : latest.entrySet()) {
    System.out.printf("%s latestOffset=%d%n",
            entry.getKey(), entry.getValue().offset());
}
~~~

Mặc định listOffsets dùng READ_UNCOMMITTED. Để tính rõ LEO và LSO, truyền ListOffsetsOptions với isolation level tương ứng. Với Kafka client hiện đại:

~~~java
ListOffsetsOptions uncommittedOptions = new ListOffsetsOptions()
        .isolationLevel(IsolationLevel.READ_UNCOMMITTED);

ListOffsetsOptions committedOptions = new ListOffsetsOptions()
        .isolationLevel(IsolationLevel.READ_COMMITTED);
~~~

READ_UNCOMMITTED lấy latest theo cuối log; READ_COMMITTED lấy latest theo Last Stable Offset. Hai mốc có thể bằng nhau khi không có transaction đang mở.

## 10. Chương trình Java hoàn chỉnh tính lag

Ví dụ sau thực hiện các bước:

1. Liệt kê group.
2. Describe từng group để lấy state và partition assignment.
3. Đọc committed offset.
4. Hợp nhất partition đang được assign với partition đã có committed offset.
5. Lấy log start, LEO và LSO.
6. Tính lag theo từng partition và in trạng thái bất thường.

~~~java
package com.example.kafkaadmin;

import org.apache.kafka.clients.admin.*;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.IsolationLevel;
import org.apache.kafka.common.TopicPartition;

import java.util.*;
import java.util.concurrent.TimeUnit;

public final class ConsumerGroupLagReporter {
    private static final long TIMEOUT_SECONDS = 30;

    public static void main(String[] args) throws Exception {
        Properties properties = new Properties();
        properties.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                System.getenv().getOrDefault(
                        "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"));
        properties.put(AdminClientConfig.CLIENT_ID_CONFIG,
                "consumer-group-lag-reporter");
        properties.put(AdminClientConfig.REQUEST_TIMEOUT_MS_CONFIG, "30000");
        properties.put(AdminClientConfig.DEFAULT_API_TIMEOUT_MS_CONFIG, "30000");
        properties.put("security.protocol",
                System.getenv().getOrDefault(
                        "KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"));

        try (Admin admin = Admin.create(properties)) {
            List<ConsumerGroupListing> groups = new ArrayList<>(
                    admin.listConsumerGroups().all()
                            .get(TIMEOUT_SECONDS, TimeUnit.SECONDS));
            groups.sort(Comparator.comparing(ConsumerGroupListing::groupId));

            if (groups.isEmpty()) {
                System.out.println("No consumer groups found.");
                return;
            }

            for (ConsumerGroupListing group : groups) {
                reportGroup(admin, group.groupId());
            }
        }
    }

    private static void reportGroup(Admin admin, String groupId) {
        System.out.printf("%n=== GROUP %s ===%n", groupId);

        try {
            ConsumerGroupDescription description =
                    admin.describeConsumerGroups(List.of(groupId))
                            .all()
                            .get(TIMEOUT_SECONDS, TimeUnit.SECONDS)
                            .get(groupId);

            System.out.printf("state=%s coordinator=%s assignor=%s%n",
                    description.state(),
                    description.coordinator(),
                    description.partitionAssignor());

            Map<TopicPartition, OffsetAndMetadata> committed =
                    admin.listConsumerGroupOffsets(groupId)
                            .partitionsToOffsetAndMetadata()
                            .get(TIMEOUT_SECONDS, TimeUnit.SECONDS);

            Set<TopicPartition> partitions = new TreeSet<>(
                    Comparator.comparing(TopicPartition::topic)
                            .thenComparingInt(TopicPartition::partition));
            partitions.addAll(committed.keySet());

            for (MemberDescription member : description.members()) {
                Set<TopicPartition> assignment =
                        member.assignment().topicPartitions();
                partitions.addAll(assignment);
                System.out.printf("member=%s clientId=%s host=%s assignment=%s%n",
                        member.consumerId(), member.clientId(),
                        member.host(), assignment);
            }

            if (partitions.isEmpty()) {
                System.out.println(
                        "No assigned partitions and no committed offsets.");
                return;
            }

            Map<TopicPartition, Long> logStart = readOffsets(
                    admin, partitions, OffsetSpec.earliest(),
                    IsolationLevel.READ_UNCOMMITTED);
            Map<TopicPartition, Long> logEnd = readOffsets(
                    admin, partitions, OffsetSpec.latest(),
                    IsolationLevel.READ_UNCOMMITTED);
            Map<TopicPartition, Long> lastStable = readOffsets(
                    admin, partitions, OffsetSpec.latest(),
                    IsolationLevel.READ_COMMITTED);

            for (TopicPartition partition : partitions) {
                OffsetAndMetadata metadata = committed.get(partition);
                long start = logStart.get(partition);
                long leo = logEnd.get(partition);
                long lso = lastStable.get(partition);

                if (metadata == null) {
                    System.out.printf(
                            "topic=%s partition=%d status=NO_COMMITTED_OFFSET "
                                    + "logStart=%d LSO=%d LEO=%d "
                                    + "earliestBacklogOffsetDistance=%d%n",
                            partition.topic(), partition.partition(),
                            start, lso, leo, leo - start);
                    continue;
                }

                long committedOffset = metadata.offset();
                long leoLag = leo - committedOffset;
                long lsoLag = lso - committedOffset;
                String status = classify(committedOffset, start, leo);

                System.out.printf(
                        "topic=%s partition=%d committed=%d "
                                + "logStart=%d LSO=%d LEO=%d "
                                + "LEO_lag=%d LSO_lag=%d status=%s%n",
                        partition.topic(), partition.partition(),
                        committedOffset, start, lso, leo,
                        leoLag, lsoLag, status);
            }
        } catch (Exception exception) {
            System.err.printf("group=%s report_failed=%s%n",
                    groupId, rootMessage(exception));
        }
    }

    private static Map<TopicPartition, Long> readOffsets(
            Admin admin,
            Set<TopicPartition> partitions,
            OffsetSpec spec,
            IsolationLevel isolationLevel) throws Exception {

        Map<TopicPartition, OffsetSpec> request = new HashMap<>();
        for (TopicPartition partition : partitions) {
            request.put(partition, spec);
        }

        ListOffsetsOptions options = new ListOffsetsOptions()
                .isolationLevel(isolationLevel);
        Map<TopicPartition, ListOffsetsResult.ListOffsetsResultInfo> response =
                admin.listOffsets(request, options)
                        .all()
                        .get(TIMEOUT_SECONDS, TimeUnit.SECONDS);

        Map<TopicPartition, Long> offsets = new HashMap<>();
        response.forEach((partition, info) ->
                offsets.put(partition, info.offset()));
        return offsets;
    }

    private static String classify(long committed, long logStart, long logEnd) {
        if (committed < logStart) {
            return "COMMITTED_BEHIND_LOG_START";
        }
        if (committed > logEnd) {
            return "COMMITTED_AHEAD_OF_LOG_END";
        }
        return "OK";
    }

    private static String rootMessage(Throwable throwable) {
        Throwable current = throwable;
        while (current.getCause() != null) {
            current = current.getCause();
        }
        return current.getClass().getSimpleName() + ": " + current.getMessage();
    }
}
~~~

Chương trình gộp assignment hiện tại và committed offsets để không bỏ qua partition vừa được assign nhưng chưa có commit. Nếu group đang EMPTY, không có assignment nhưng vẫn có committed offsets, chương trình vẫn tính lag cho các partition đã lưu offset. Nếu group chưa từng commit và cũng không có member, Admin API không có đủ thông tin để biết topic-partition nào group dự định đọc.

## 11. Đọc kết quả và xử lý trường hợp đặc biệt

Ví dụ output:

~~~text
=== GROUP order-service ===
state=STABLE coordinator=broker-1 assignor=range
member=consumer-1 clientId=order-app-1 host=/10.0.0.11 assignment=[orders-0, orders-1]
topic=orders partition=0 committed=120 logStart=0 LSO=175 LEO=175 LEO_lag=55 LSO_lag=55 status=OK
topic=orders partition=1 committed=80 logStart=0 LSO=100 LEO=100 LEO_lag=20 LSO_lag=20 status=OK
~~~

Diễn giải:

- Group đang STABLE và có một member.
- Partition 0 có khoảng cách 55 offsets từ committed offset đến LEO.
- Partition 1 có khoảng cách 20 offsets.
- LSO bằng LEO nên tại thời điểm đo không có vùng transactional đang mở làm giảm ranh giới read_committed.

Nếu LSO nhỏ hơn LEO, hãy kiểm tra transaction đang mở hoặc transaction coordinator chậm. Consumer read_committed chỉ tiến đến LSO; consumer read_uncommitted có thể tiến gần LEO hơn.

Nếu LSO lag âm trong khi LEO lag vẫn dương, committed offset có thể đã vượt LSO. Điều này có thể xảy ra khi group dùng consumer read_uncommitted và đã commit qua vùng transaction chưa ổn định. Đây không tự động là lỗi offset; Admin API không cho biết isolation.level cấu hình trong từng consumer instance. Hãy đối chiếu cấu hình ứng dụng trước khi diễn giải LSO lag. Nếu group được xác nhận dùng read_committed, lấy mẫu lại sau khi transaction hoàn tất và kiểm tra committed offset.

### 11.1. Group không có committed offset

Khi status là NO_COMMITTED_OFFSET, không tính lag bằng cách tự gán committed=0. Consumer có thể bắt đầu từ earliest hoặc latest theo auto.offset.reset; nếu là none, consumer có thể báo lỗi khi không tìm thấy offset hợp lệ.

Chương trình in earliestBacklogOffsetDistance = LEO - logStart để biểu thị khoảng cách offset có thể đọc từ đầu log. Đây không phải consumer lag của group vì chưa biết offset khởi đầu thực tế.

### 11.2. Committed offset nằm trước log start

Nếu committed offset nhỏ hơn log start, dữ liệu trước đó đã bị retention xóa hoặc log đã bị thay đổi. Consumer khi khởi động lại có thể gặp OffsetOutOfRangeException; cách xử lý phụ thuộc auto.offset.reset.

Không tự động reset offset về earliest/latest trong công cụ báo cáo. Hãy cảnh báo, xác định yêu cầu nghiệp vụ và để quy trình vận hành quyết định có reset hay không.

### 11.3. Committed offset lớn hơn log end

Đây là trạng thái cần điều tra. Nguyên nhân có thể là log truncation, thay đổi dữ liệu topic, reset offset hoặc snapshot được lấy trong lúc metadata thay đổi. Không ép giá trị lag âm về 0; giữ lại committed, LEO và status để điều tra.

### 11.4. Group EMPTY nhưng còn offset

Khi toàn bộ consumer dừng, group có thể ở trạng thái EMPTY nhưng committed offsets vẫn được giữ trong Kafka. Lag vẫn tính được bằng LEO trừ committed offset. Đây là cách phát hiện backlog của một service hiện không có instance chạy.

## 12. Offset lag khác số record chưa xử lý

Phép tính LEO - committed offset là offset distance. Nó có thể khác số record mà consumer thực sự sẽ nhận vì:

- Topic compacted có thể xóa các phiên bản key cũ nhưng giữ khoảng trống offset.
- Retention có thể xóa segment cũ.
- Control record của transaction cũng chiếm offset trong log.
- Consumer có thể đã poll/xử lý record nhưng chưa commit.
- Consumer read_committed bị giới hạn bởi LSO, không phải LEO.

Do đó, dashboard nên ghi rõ metric là committed offset lag hoặc offset distance. Nếu muốn hiển thị số record có thể đọc, cần xác định isolation level, log start và chính sách topic; với topic compacted, scan thực tế vẫn là cách đo chính xác hơn.

## 13. Lọc group theo topic hoặc trạng thái

Sau khi đọc danh sách group, có thể lọc theo state hoặc assignment:

~~~java
import org.apache.kafka.common.ConsumerGroupState;

for (ConsumerGroupListing listing : groups) {
    String groupId = listing.groupId();
    ConsumerGroupDescription description =
            admin.describeConsumerGroups(List.of(groupId))
                    .all()
                    .get(30, TimeUnit.SECONDS)
                    .get(groupId);

    boolean hasMembers = !description.members().isEmpty();
    boolean isStable = description.state() == ConsumerGroupState.STABLE;

    if (!hasMembers || !isStable) {
        System.out.printf("attention group=%s state=%s members=%d%n",
                groupId, description.state(), description.members().size());
    }
}
~~~

Để lọc group đang đọc một topic cụ thể, kiểm tra assignment của từng member:

~~~java
boolean consumesOrders = description.members().stream()
        .flatMap(member -> member.assignment().topicPartitions().stream())
        .anyMatch(partition -> partition.topic().equals("orders"));
~~~

Group EMPTY không có assignment hiện tại, vì vậy nếu cần tìm group lịch sử từng đọc topic nào, phải dựa vào committed offset map chứ không thể chỉ xem member assignment.

## 14. Đối chiếu bằng Kafka CLI

Admin API nên được kiểm tra chéo với Kafka command-line tools trong lab:

Liệt kê group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list
~~~

Xem chi tiết một group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-service
~~~

Kết quả CLI thường hiển thị topic, partition, current offset, log end offset và lag. Đối chiếu các cột này với committed, LEO và LEO_lag mà chương trình Java tính được.

CLI cũng không biến committed offset thành consumer position thực tế. Khi ứng dụng commit theo batch hoặc xử lý bất đồng bộ, lag CLI vẫn có thể bao gồm record đã được poll nhưng chưa commit.

## 15. Bảo mật và quyền ACL

AdminClient phải được cấp quyền đọc metadata group và topic. Tùy cấu hình authorization và phiên bản Kafka, principal thường cần:

- DESCRIBE trên resource CLUSTER để liệt kê consumer group.
- DESCRIBE trên resource GROUP để mô tả group và đọc group offsets.
- DESCRIBE trên resource TOPIC cho các topic-partition cần lấy offset.
- Quyền phù hợp để truy cập cluster metadata và broker listener.

Nếu nhận GroupAuthorizationException hoặc TopicAuthorizationException, kiểm tra principal, ACL và resource pattern. Không cấp quyền ALTER hoặc DELETE nếu ứng dụng chỉ cần báo cáo.

Ví dụ SASL_SSL cần cấu hình security.protocol, sasl.mechanism, sasl.jaas.config và truststore theo cluster. Secret phải được inject từ secret manager hoặc môi trường triển khai, không đặt trong source code.

## 16. Snapshot không nguyên tử và cách lấy số liệu ổn định

Việc liệt kê group, describe group, đọc committed offsets và listOffsets là các Admin API request riêng. Cluster có thể thay đổi giữa các request:

- Member mới tham gia hoặc rời group.
- Rebalance thay đổi assignment.
- Consumer commit offset mới.
- Producer append thêm record.
- Retention hoặc topic metadata thay đổi.

Vì vậy, một lượt báo cáo không phải snapshot nguyên tử của toàn cluster. Khi cần số liệu ổn định:

1. Đọc group state và chỉ đánh dấu snapshot ổn định khi group là STABLE.
2. Đọc committed offsets và LEO/LSO.
3. Đọc lại group state hoặc offset để phát hiện thay đổi trong lúc đo.
4. Nếu group đang rebalance hoặc số liệu thay đổi mạnh, lấy mẫu lại sau một khoảng ngắn.
5. Gắn timestamp của lần lấy mẫu vào metric và log.

Không khóa consumer group chỉ để lấy số liệu. Công cụ monitoring nên đọc không gây gián đoạn hoạt động của ứng dụng.

## 17. Tối ưu khi cluster có nhiều group

Khi số lượng group và partition lớn:

- Liệt kê group một lần rồi xử lý theo batch hợp lý.
- Gọi listConsumerGroupOffsets một lần cho mỗi group, không gọi lặp cho từng partition.
- Gộp nhiều partition trong một listOffsets request.
- Giới hạn số group xử lý đồng thời để tránh tạo quá nhiều request.
- Đặt timeout cho mỗi API và ghi rõ group nào thất bại.
- Cache metadata ngắn hạn nếu dashboard refresh liên tục, nhưng phải ghi timestamp để người xem biết độ mới.
- Không gọi describeConfigs hoặc scan toàn bộ record nếu chỉ cần committed lag.

Nếu cần báo cáo liên tục, có thể chạy định kỳ và xuất metric theo group/topic/partition. Chọn label có kiểm soát; group ID và topic có cardinality cao có thể làm tăng chi phí hệ thống metrics.

## 18. Metrics nên xuất ra dashboard

| Metric | Ý nghĩa |
|---|---|
| consumer_group_state | Trạng thái group như STABLE, EMPTY hoặc đang rebalance |
| consumer_group_members | Số member hiện tại |
| consumer_group_partition_count | Số partition được assign |
| committed_offset | Offset đã commit theo group/topic/partition |
| log_start_offset | Offset sớm nhất còn giữ |
| log_end_offset | LEO theo READ_UNCOMMITTED |
| last_stable_offset | LSO theo READ_COMMITTED |
| consumer_group_lag_offsets | LEO trừ committed offset |
| consumer_group_stable_lag_offsets | LSO trừ committed offset |
| offset_out_of_range | Committed offset nằm trước log start hoặc sau log end |
| admin_api_request_latency | Thời gian các Admin API request hoàn tất |
| admin_api_error_count | Timeout, authorization và lỗi broker |

Đặt cảnh báo theo cả giá trị lag và thời gian lag kéo dài. Ví dụ một group có lag 10.000 offsets nhưng đang giảm nhanh có thể ít nghiêm trọng hơn group có lag 500 offsets nhưng tăng liên tục trong nhiều giờ. Kết hợp lag với throughput, processing latency và thời điểm commit cuối cùng để xác định tình trạng thực.

## 19. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| listConsumerGroups trả rỗng | Cluster không có group hoặc principal không đủ quyền | Kiểm tra bootstrap server, ACL và group thực tế |
| describe group thất bại sau khi list | Group vừa bị xóa hoặc coordinator thay đổi | Retry có backoff và ghi nhận group đã biến mất |
| Không có committed offset | Group chưa commit lần nào hoặc partition mới được assign | Hiển thị NO_COMMITTED_OFFSET, kiểm tra auto.offset.reset |
| Lag âm | Committed offset lớn hơn LEO hoặc snapshot không đồng nhất | Giữ nguyên số liệu, lấy mẫu lại và điều tra truncation/reset |
| Lag rất lớn sau retention | Committed offset nằm trước log start | Cảnh báo dữ liệu đã hết retention và kiểm tra reset policy |
| LEO lag cao nhưng LSO lag thấp | Có transaction đang mở | Kiểm tra transaction duration, producer và transaction coordinator |
| Lag không giảm dù member STABLE | Consumer xử lý chậm, lỗi liên tục hoặc commit quá thưa | Xem processing latency, retry/DLT và commit interval |
| CLI và Admin API lệch nhẹ | Hai công cụ lấy mẫu ở thời điểm khác nhau | Lấy snapshot gần nhau và so sánh cùng isolation level |
| Timeout khi đọc offsets nhiều partition | Request lớn, broker chậm hoặc network lỗi | Chia batch partition, tăng timeout có giới hạn và theo dõi broker |

## 20. Lab: xây dựng báo cáo consumer group lag

Thực hiện các bước:

1. Tạo topic orders với ba partition.
2. Khởi động consumer group order-service và đọc một số record.
3. Commit offset theo batch để quan sát committed offset khác consumer position.
4. Chạy ConsumerGroupLagReporter; ghi lại group state, member, assignment và lag từng partition.
5. Dừng toàn bộ consumer; xác nhận group chuyển sang EMPTY nhưng committed offsets vẫn tồn tại và lag tiếp tục được tính.
6. Gửi thêm record khi consumer đã dừng; quan sát LEO tăng trong khi committed offset giữ nguyên.
7. Bật một transaction producer và để transaction mở trong lab; so sánh LEO với LSO và hai loại lag.
8. Tạo group mới chưa có committed offset; xác nhận công cụ hiển thị NO_COMMITTED_OFFSET.
9. Dùng retention ngắn trong topic lab để tạo tình huống committed offset nằm trước log start; quan sát cảnh báo.
10. Đối chiếu kết quả Java với kafka-consumer-groups.sh --describe.

Không thử retention hoặc reset offset trên topic production. Các thao tác này chỉ dành cho topic lab có dữ liệu có thể tạo lại.

## 21. Tiêu chí hoàn thành

- Dùng AdminClient.listConsumerGroups để liệt kê group.
- Dùng describeConsumerGroups để đọc state, member và assignment.
- Dùng listConsumerGroupOffsets để lấy committed offset theo partition.
- Dùng listOffsets để lấy log start, LEO và LSO.
- Tính được LEO lag và phân biệt với LSO lag.
- Giải thích committed offset khác consumer position.
- Xử lý group EMPTY, partition chưa có committed offset và offset out-of-range.
- Hiểu offset distance không nhất thiết bằng số record còn tồn tại.
- Biết quyền ACL và giới hạn snapshot của Admin API.
- Đối chiếu được kết quả với Kafka CLI.

## 22. Ghi nhớ

| API/khái niệm | Vai trò |
|---|---|
| listConsumerGroups | Liệt kê group |
| describeConsumerGroups | Đọc state và member assignment |
| listConsumerGroupOffsets | Đọc committed offset |
| listOffsets(earliest) | Lấy log start offset |
| listOffsets(latest, READ_UNCOMMITTED) | Lấy LEO |
| listOffsets(latest, READ_COMMITTED) | Lấy LSO |
| LEO - committed | Committed-offset lag theo offset distance |
| LSO - committed | Khoảng cách đến ranh giới read_committed |
| Consumer position | Vị trí trong client, Admin API không đọc trực tiếp được |

Admin API giúp xây dựng công cụ quan sát consumer group mà không cần tham gia group hoặc thay đổi offset. Hãy đọc committed offset, log start, LEO và LSO theo từng partition; phân biệt offset distance với số record thực tế, và xem group state cùng thời điểm lấy mẫu trước khi kết luận service đang bị lag.
