# Xóa topic, xóa group và điều kiện xác minh trước thao tác

Xóa topic và xóa consumer group là hai thao tác quản trị khác nhau, nhưng đều có thể làm mất khả năng đọc lại dữ liệu hoặc tiếp tục từ vị trí cũ. Xóa topic loại bỏ log dữ liệu cùng metadata của topic. Xóa group loại bỏ metadata group và committed offsets của group đó. Trước khi chạy lệnh, cần xác minh đúng cluster, đúng resource, không còn workload phụ thuộc và đã có phương án khôi phục phù hợp.

Không nhầm xóa topic với retention/compaction, và không nhầm xóa group với reset offset. Retention xóa segment cũ theo policy; compaction giữ trạng thái mới nhất theo key; reset offset thay đổi vị trí đọc; delete group loại bỏ tiến độ đã commit của group. Chọn sai thao tác có thể làm mất dữ liệu hoặc khiến consumer đọc lại/nhảy qua dữ liệu ngoài dự kiến.

## 1. Phân biệt topic, consumer group và offset

Kafka lưu record trong topic, chia thành partition. Consumer group lưu tiến độ đọc bằng committed offsets theo topic-partition. Các tài nguyên có liên quan nhưng có vòng đời độc lập.

| Tài nguyên | Lưu gì? | Xóa tác động thế nào? |
|---|---|---|
| Topic | Partition log, record, topic configuration và metadata | Dữ liệu topic không còn được phục vụ; không thể đọc lại từ topic đã xóa |
| Consumer group | Group metadata, membership state và committed offsets | Consumer mất tiến độ đã commit; group có thể được tạo lại khi client cùng group ID kết nối |
| Committed offset | Vị trí consumer đã xác nhận xử lý | Reset hoặc xóa offset làm thay đổi vị trí consumer tiếp tục đọc |
| Topic retention | Quy tắc giữ/xóa segment theo thời gian hoặc dung lượng | Xóa dữ liệu cũ theo policy, topic vẫn tồn tại |
| Log compaction | Giữ bản ghi mới nhất theo key và tombstone theo policy | Topic vẫn tồn tại; lịch sử theo key được rút gọn |

Topic chứa dữ liệu; group chứa tiến độ tiêu thụ. Xóa một group không xóa record trong topic. Xóa một topic cũng không phải cách chủ động xóa toàn bộ group đang tồn tại.

## 2. Xóa topic khác retention và compaction

Kafka có nhiều cơ chế làm dữ liệu biến mất:

| Cơ chế | Phạm vi | Topic còn tồn tại? | Có thể đọc lại dữ liệu đã bị loại? |
|---|---|---|---|
| Delete topic | Toàn bộ topic | Không, sau khi deletion hoàn tất | Không từ topic đó |
| Retention theo thời gian | Segment cũ | Có | Không sau khi segment đã bị xóa |
| Retention theo dung lượng | Segment cũ khi vượt giới hạn dung lượng | Có | Không sau khi segment đã bị xóa |
| Compaction | Các phiên bản cũ của key | Có | Không bảo đảm giữ toàn bộ lịch sử |
| Tombstone | Xóa trạng thái key trong compacted topic sau thời gian giữ | Có | Không bảo đảm khôi phục trạng thái trước đó |

Ví dụ:

~~~properties
cleanup.policy=delete
retention.ms=604800000
retention.bytes=-1
~~~

Cấu hình này giữ segment theo retention policy; nó không xóa topic sau bảy ngày. Tương tự, cleanup.policy=compact không xóa topic mà rút gọn log theo key.

Chọn retention/compaction khi mục tiêu là quản lý vòng đời record. Chỉ dùng delete topic khi resource/topic đó không còn cần thiết và toàn bộ dữ liệu đã được xử lý theo chính sách lưu trữ.

## 3. Xóa consumer group khác reset offset

Xóa group loại bỏ group metadata và committed offsets của group. Reset offset chỉ thay đổi vị trí đọc của group cho một hoặc nhiều topic-partition.

| Nhu cầu | Thao tác phù hợp |
|---|---|
| Xóa hẳn group không còn được sử dụng | Delete consumer group |
| Cho consumer đọc lại topic từ đầu | Reset offsets về earliest |
| Bỏ qua backlog và đọc dữ liệu mới | Reset offsets về latest |
| Đưa một số partition về vị trí cụ thể | Reset offsets tới offset được chỉ định |
| Xóa toàn bộ dữ liệu topic | Delete topic, sau khi xác minh phụ thuộc và backup |
| Chỉ xóa record cũ theo policy | Điều chỉnh retention hoặc compaction phù hợp |

Nếu chỉ cần replay một topic, không xóa cả group một cách không cần thiết. Group có thể đang giữ offsets cho nhiều topic; delete group sẽ làm mất toàn bộ tiến độ của group, không chỉ topic đang điều tra.

## 4. Xóa topic là thao tác destructive

Khi topic được xóa, Kafka loại bỏ topic metadata và các partition log liên quan. Sau khi deletion hoàn tất, consumer không thể tiếp tục đọc dữ liệu cũ từ topic đó. Nếu topic được tạo lại cùng tên, đó là một topic mới về mặt vòng đời và không khôi phục log cũ.

Trước khi xóa, cần trả lời:

- Topic có chứa dữ liệu cần giữ theo yêu cầu nghiệp vụ, audit hoặc pháp lý không?
- Producer nào đang ghi vào topic?
- Consumer group nào đang đọc topic?
- Kafka Connect source/sink, Kafka Streams, MirrorMaker hoặc pipeline khác có tham chiếu topic không?
- Topic có phải internal topic hoặc changelog/repartition topic không?
- Có bản sao, archive, object storage hoặc nguồn dữ liệu có thể replay không?
- Topic có ACL, schema contract hoặc dashboard/alert phụ thuộc không?
- Việc xóa có nằm trong ticket/change window và được owner chấp thuận không?

Không xóa topic nội bộ của Kafka hoặc ứng dụng nền tảng chỉ vì thấy tên bắt đầu bằng dấu gạch dưới. Các topic như __consumer_offsets, __transaction_state, Connect config/offset/status topics và Kafka Streams changelog/repartition topics có vai trò vận hành và phục hồi riêng.

## 5. Xác minh đúng cluster trước khi chạy lệnh

Một lệnh delete chạy nhầm bootstrap server có thể xóa resource ở staging hoặc production ngoài dự kiến. Không dựa vào tên biến shell hoặc terminal hiện tại để kết luận cluster.

Checklist xác minh:

1. Đối chiếu bootstrap server với inventory/environment được phê duyệt.
2. Kiểm tra security protocol và file command-config đang dùng.
3. Xác minh broker trả lời thuộc cluster mong muốn bằng thông tin cluster trong quy trình vận hành.
4. Kiểm tra principal đang xác thực và quyền ACL của principal đó.
5. Đọc lại resource name từ ticket/manifest và đối chiếu chính xác từng ký tự.
6. Không dùng wildcard, regex hoặc danh sách được sinh tự động khi chưa review.
7. Chạy các lệnh describe/list trước, lưu output làm bằng chứng preflight.

Ví dụ kiểm tra broker endpoint:

~~~bash
kafka-broker-api-versions.sh \
  --bootstrap-server kafka-prod-1:9092 \
  --command-config admin.properties
~~~

Lệnh này kiểm tra khả năng kết nối và API của broker; bản thân nó không chứng minh endpoint là production hay staging. Phải đối chiếu endpoint/cluster identity với nguồn cấu hình đáng tin cậy của tổ chức.

### Không có dry-run cho delete topic/group

Các lệnh kafka-topics --delete và kafka-consumer-groups --delete không có chế độ dry-run phổ quát tương đương reset-offsets --dry-run. Lệnh describe/list chỉ là bước xác minh, không phải mô phỏng kết quả xóa. Chỉ chạy delete sau khi preflight và approval hoàn tất.

## 6. Preflight cho topic

Trước khi xóa topic, thu thập trạng thái:

~~~bash
# Xem topic có tồn tại và partition/leader/replica/ISR
kafka-topics.sh \
  --bootstrap-server kafka-prod-1:9092 \
  --command-config admin.properties \
  --describe \
  --topic orders.events

# Xem topic configuration và override
kafka-configs.sh \
  --bootstrap-server kafka-prod-1:9092 \
  --command-config admin.properties \
  --entity-type topics \
  --entity-name orders.events \
  --describe \
  --all

# Liệt kê topic để đối chiếu tên
kafka-topics.sh \
  --bootstrap-server kafka-prod-1:9092 \
  --command-config admin.properties \
  --list
~~~

Ghi lại topic name chính xác, partition count, replication factor, leader/replica/ISR của từng partition, cleanup.policy, retention.ms, retention.bytes, min.insync.replicas và các override quan trọng. Ghi thêm throughput gần đây, thời điểm ghi cuối, ACL và producer/consumer/connector/Streams phụ thuộc.

Topic không có record mới trong vài giờ chưa chắc là topic bỏ hoang. Có thể đó là topic lưu trữ dài hạn, topic chỉ hoạt động theo mùa hoặc topic chờ replay.

## 7. Tìm consumer group đang sử dụng topic

Liệt kê group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-prod-1:9092 \
  --command-config admin.properties \
  --list
~~~

Mô tả một group cụ thể:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-prod-1:9092 \
  --command-config admin.properties \
  --describe \
  --group payments-service
~~~

Output cho biết topic-partition, committed offset, log end offset, lag và consumer ID/host tùy trạng thái group. Để kiểm tra membership:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-prod-1:9092 \
  --command-config admin.properties \
  --describe \
  --group payments-service \
  --members \
  --verbose
~~~

Một group có thể subscribe nhiều topic. Nếu xóa topic, cần xác định ảnh hưởng tới toàn bộ ứng dụng và subscription; nếu xóa group, cần hiểu mọi topic mà group đang đọc sẽ bị mất committed offsets.

Không có một lệnh list group duy nhất chứng minh topic không còn consumer ở mọi pipeline. Cần đối chiếu consumer group, Kafka Connect, Kafka Streams, MirrorMaker, service configuration và telemetry của tổ chức.

## 8. Xác minh consumer group đã dừng

Consumer group đang hoạt động thường có state Stable và active members. Muốn xóa group an toàn, trước hết dừng mọi consumer instance dùng group ID đó và xác nhận group không còn member hoạt động.

Kiểm tra state:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-prod-1:9092 \
  --command-config admin.properties \
  --describe \
  --group payments-service \
  --state
~~~

Kiểm tra member:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-prod-1:9092 \
  --command-config admin.properties \
  --describe \
  --group payments-service \
  --members \
  --verbose
~~~

Chỉ tiếp tục khi group đã Empty và không còn active member theo trạng thái broker. Dead hoặc group không tồn tại là trạng thái khác với group Empty; kiểm tra lại output và xác minh group ID trước khi quyết định.

### Vì sao phải dừng consumer trước?

Nếu group còn member, broker có thể từ chối xóa group. Nếu dừng consumer chưa đầy đủ hoặc một deployment tự khởi động lại, group có thể chuyển về Stable ngay sau khi preflight. Cần phối hợp với owner workload, scale deployment về 0 hoặc dừng service theo runbook rồi xác nhận lại sát thời điểm delete.

Với Kafka Streams, application ID liên quan tới consumer group và internal topics. Không xóa group hoặc internal topic khi Streams application còn chạy hay còn cần khôi phục state.

## 9. Xác minh quyền và broker configuration

Xóa topic và xóa group cần quyền phù hợp. Với ACL Kafka, kiểm tra principal có operation DELETE trên resource tương ứng và các quyền quản trị cần thiết theo authorizer/version.

Ví dụ liệt kê ACL topic:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-prod-1:9092 \
  --command-config admin.properties \
  --list \
  --topic orders.events
~~~

Kiểm tra ACL của GROUP resource:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-prod-1:9092 \
  --command-config admin.properties \
  --list \
  --group payments-service
~~~

Kiểm tra effective broker configuration delete.topic.enable. Với broker có ID 1, ví dụ:

~~~bash
kafka-configs.sh \
  --bootstrap-server kafka-prod-1:9092 \
  --command-config admin.properties \
  --entity-type brokers \
  --entity-name 1 \
  --describe \
  --all
~~~

Nếu broker không cho phép delete topic, yêu cầu xóa có thể bị từ chối hoặc topic không được xóa theo mong đợi. Hãy kiểm tra effective broker config trên các broker liên quan và theo đúng cơ chế cấu hình của cluster/version, không chỉ file cấu hình cũ trong repository.

Với group deletion, kiểm tra quyền DELETE trên GROUP resource và đảm bảo principal dùng trong CLI thực sự là principal được phê duyệt cho thao tác.

Không cấp ALL hoặc super.users chỉ để vượt qua authorization error. Nếu thiếu quyền, dừng thao tác và yêu cầu cấp đúng quyền theo quy trình.

## 10. Xóa topic bằng Kafka CLI

Sau khi preflight, approval và xác minh producer/consumer đã hoàn tất, lệnh xóa topic:

~~~bash
kafka-topics.sh \
  --bootstrap-server kafka-prod-1:9092 \
  --command-config admin.properties \
  --delete \
  --topic orders.events
~~~

Lệnh trên gửi yêu cầu xóa đúng topic orders.events. Không dùng lệnh này cho topic nội bộ hoặc topic chưa xác minh owner.

### Xóa nhiều topic

Nếu cần xóa nhiều topic, liệt kê từng tên rõ ràng trong change record và xác minh từng topic riêng. Không dùng wildcard như orders.* vào lệnh delete với kỳ vọng Kafka CLI tự mở rộng. Kafka CLI nhận tên topic cụ thể.

Không chạy vòng lặp xóa từ file đầu vào chưa review. Một lỗi tạo danh sách có thể xóa nhầm hàng loạt topic.

### Xóa topic có thể chưa hoàn tất ngay

Topic deletion là thao tác điều phối trong cluster và việc dọn log segment trên broker có thể diễn ra bất đồng bộ. Trong thời gian đó, topic có thể còn xuất hiện trong metadata hoặc CLI có thể báo đang xóa. Không tạo lại topic cùng tên ngay lập tức; chờ xác minh deletion hoàn tất và metadata đã ổn định.

Nếu topic không biến mất, kiểm tra delete.topic.enable, broker/controller health và metadata quorum, broker chứa replica có online không, authorization và broker log. Không xóa trực tiếp thư mục log trên filesystem để thay thế Kafka delete API; thao tác filesystem thủ công có thể làm metadata và replica state không nhất quán.

## 11. Xóa consumer group bằng Kafka CLI

Sau khi tất cả consumer member đã dừng và group được xác nhận Empty:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-prod-1:9092 \
  --command-config admin.properties \
  --delete \
  --group payments-service
~~~

Lệnh này xóa group metadata và committed offsets của payments-service. Nó không xóa record trong các topic mà group từng đọc.

Nếu group có active members, broker có thể từ chối yêu cầu. Không lặp lại lệnh delete trong khi deployment vẫn tự khởi động consumer. Dừng workload, xác nhận state Empty rồi mới chạy lại.

### Điều gì xảy ra nếu consumer chạy lại?

Nếu một consumer mới kết nối với cùng group ID, group có thể được tạo lại. Vì committed offsets đã bị xóa, consumer sẽ áp dụng auto.offset.reset khi không còn offset hợp lệ:

| auto.offset.reset | Hành vi khi không có committed offset hợp lệ |
|---|---|
| earliest | Bắt đầu từ offset sớm nhất còn được giữ |
| latest | Bắt đầu từ cuối log tại thời điểm xác định offset |
| none | Ném lỗi nếu không có offset hợp lệ |

auto.offset.reset không ghi đè committed offset hợp lệ đang tồn tại. Nhưng sau khi xóa group, consumer có thể bắt đầu lại theo cấu hình này. Vì vậy, xóa group có thể khiến consumer đọc lại backlog lớn hoặc bỏ qua dữ liệu cũ tùy policy.

## 12. Xóa group không xóa topic data

Committed offsets được lưu trong internal topic __consumer_offsets. Kafka quản lý metadata group và offset record theo cơ chế nội bộ. Khi xóa một group, broker loại bỏ group và tiến độ đã commit tương ứng; record trong topic nghiệp vụ vẫn còn theo retention/compaction policy.

Ví dụ:

~~~text
Topic: orders.events
  Partition 0: records 0..5000
  Partition 1: records 0..4200

Group: orders-analytics
  orders.events-0 committed offset = 4900
  orders.events-1 committed offset = 4100

Delete group orders-analytics
  -> committed offsets của group bị xóa
  -> orders.events vẫn giữ record theo retention
  -> group có thể được tạo lại khi consumer kết nối
~~~

Không xóa __consumer_offsets để xóa một group. Đây là internal topic dùng chung cho nhiều group; xóa nó có thể ảnh hưởng tiến độ tiêu thụ của toàn cluster.

## 13. Khi chỉ muốn reset offset

Nếu mục tiêu là replay dữ liệu mà vẫn giữ group, dùng reset-offsets. Bắt đầu bằng dry-run:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-prod-1:9092 \
  --command-config admin.properties \
  --group payments-service \
  --topic orders.events \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

Đọc kỹ output theo từng partition. Khi đã xác minh phạm vi và được phê duyệt, chạy lại với execute:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-prod-1:9092 \
  --command-config admin.properties \
  --group payments-service \
  --topic orders.events \
  --reset-offsets \
  --to-earliest \
  --execute
~~~

Reset offset yêu cầu group không có active consumer theo các điều kiện của CLI/broker. Dừng consumer trước, kiểm tra trạng thái, dry-run, review kết quả rồi mới execute.

Các lựa chọn khác gồm to-latest, to-offset, to-datetime hoặc shift-by; kiểm tra help của đúng Kafka release và xem kỹ từng partition. shift-by có thể tạo offset ngoài range nếu không kiểm tra.

## 14. Xóa topic và group bằng AdminClient

Kafka Admin API cho phép ứng dụng quản trị thực hiện delete topic/group. Nên dùng service account quản trị riêng, timeout hữu hạn và log lại request/result.

### Delete topic

~~~java
Properties props = new Properties();
props.put(
    AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
    "kafka-prod-1:9092,kafka-prod-2:9092"
);
props.put(
    "security.protocol",
    "SASL_SSL"
);
// Thêm SASL/TLS credential qua secret manager hoặc config provider.

String topicName = "orders.events";

try (AdminClient admin = AdminClient.create(props)) {
    DeleteTopicsOptions options =
        new DeleteTopicsOptions().timeoutMs(30_000);

    DeleteTopicsResult result =
        admin.deleteTopics(List.of(topicName), options);

    result.topicNameValues()
        .get(topicName)
        .get(35, TimeUnit.SECONDS);
}
~~~

Đây là ví dụ API; cần import AdminClient, AdminClientConfig, DeleteTopicsOptions, DeleteTopicsResult, List, Properties và TimeUnit. Không hard-code credential vào source code. Future hoàn tất cho biết kết quả request theo API; vẫn cần kiểm tra metadata/topic list và trạng thái dọn log trên cluster.

### Delete consumer group

~~~java
try (AdminClient admin = AdminClient.create(props)) {
    DeleteConsumerGroupsResult result =
        admin.deleteConsumerGroups(
            List.of("payments-service")
        );

    result.deletedGroups()
        .get("payments-service")
        .get(30, TimeUnit.SECONDS);
}
~~~

Group phải đáp ứng điều kiện xóa của broker, đặc biệt không còn active member. Bắt và phân loại exception như group đang hoạt động, authorization failure, timeout hoặc coordinator unavailable. Không retry vô hạn nếu điều kiện preflight chưa được đáp ứng.

### Vì sao cần kiểm tra sau Admin API?

Admin API trả kết quả cho từng resource. Sau thao tác, ứng dụng quản trị vẫn nên list topic/group để xác nhận resource không còn; describe resource nếu còn xuất hiện; kiểm tra broker/controller logs nếu deletion pending; ghi lại timestamp, principal, cluster và kết quả vào audit/change record.

Không chỉ dựa vào việc method trả về mà bỏ qua xác minh hậu kiểm.

## 15. Race condition khi xóa

Delete là thao tác quản trị diễn ra đồng thời với producer, consumer và controller. Một vài race phổ biến:

| Race | Hậu quả | Phòng tránh |
|---|---|---|
| Producer tiếp tục ghi trong lúc topic bị xóa | Produce errors, topic có thể được tạo lại nếu auto-create bật | Dừng producer và tắt/kiểm soát auto topic creation theo policy |
| Consumer tự reconnect trong lúc delete group | Group được tạo lại hoặc delete bị từ chối | Dừng mọi instance và autoscaling trước |
| Topic được tạo lại ngay khi deletion chưa hoàn tất | Metadata conflict hoặc nhầm topic cũ/mới | Chờ deletion hoàn tất trước khi recreate |
| Deployment rollback khởi động group cũ | Group metadata xuất hiện lại | Cập nhật deployment/config và xác nhận không còn workload |
| Script dùng nhầm bootstrap server | Xóa resource trên cluster sai | Đối chiếu cluster identity và review lệnh |
| Hai operator chạy delete cùng lúc | Kết quả không rõ ràng, audit khó | Dùng change lock/ownership và một operator thực hiện |

Nếu broker cho phép auto topic creation, producer có thể vô tình tạo lại topic cùng tên sau khi xóa. Quản lý auto.create.topics.enable và quy trình provisioning để tránh topic ngoài ý muốn.

## 16. Internal topics và tài nguyên không được xóa tùy tiện

Một số topic không phải dữ liệu nghiệp vụ thông thường:

| Internal topic/resource | Vai trò | Rủi ro khi xóa |
|---|---|---|
| __consumer_offsets | Lưu consumer group offsets/metadata | Ảnh hưởng rộng tới nhiều group trong cluster |
| __transaction_state | Lưu trạng thái transaction coordinator | Có thể làm transaction processing/recovery bị ảnh hưởng nghiêm trọng |
| Kafka Connect config topic | Lưu connector configuration | Mất cấu hình connector cluster |
| Kafka Connect offset topic | Lưu source connector offsets | Connector có thể snapshot/re-read hoặc tiếp tục sai vị trí |
| Kafka Connect status topic | Lưu trạng thái connector/task | Mất trạng thái vận hành |
| Kafka Streams changelog topic | Phục hồi state store | State recovery có thể thất bại hoặc phải rebuild |
| Kafka Streams repartition topic | Phân phối lại record theo key | Topology có thể không xử lý đúng hoặc không phục hồi được |

Không xóa internal topic để dọn rác hoặc giải quyết một consumer group bị lỗi. Dùng Admin API/CLI và runbook riêng của Kafka Connect/Streams/Kafka platform khi cần reset ứng dụng.

## 17. Recovery và khả năng rollback

Xóa topic không có thao tác undo trực tiếp. Nếu topic đã bị xóa hoàn tất, tạo lại cùng tên chỉ tạo resource mới rỗng. Khả năng phục hồi phụ thuộc bản sao hoặc nguồn dữ liệu khác:

- Mirror cluster hoặc topic replica ở hệ thống khác.
- Archive/object storage đã export.
- Database/outbox/source of truth có thể replay.
- Snapshot hoặc backup được kiểm thử restore.
- Downstream event store có bản sao độc lập.

Trước khi delete topic quan trọng, phải chứng minh restore/replay khả thi và ước lượng thời gian phục hồi. Không coi replication factor là backup; replica bảo vệ availability trong cluster nhưng không bảo vệ khỏi thao tác xóa hợp lệ được controller áp dụng cho toàn bộ replica.

Xóa group thường có thể khôi phục bằng cách tạo lại group và reset offset theo kế hoạch, nhưng committed offsets cũ không tự quay lại. Nếu cần giữ tiến độ, export/ghi lại offsets trước thao tác:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-prod-1:9092 \
  --command-config admin.properties \
  --describe \
  --group payments-service
~~~

Lưu output có topic, partition và current offset vào change record. Nếu phải khôi phục, tạo group lại và reset tới offset đã ghi sau khi kiểm tra log start offset còn tồn tại.

## 18. Runbook xóa topic an toàn

~~~mermaid
flowchart TD
    A[Nhận yêu cầu xóa topic] --> B[Xác minh cluster và tên topic]
    B --> C[Describe topic/config/ACL]
    C --> D[Tìm producer, consumer và connector phụ thuộc]
    D --> E{Có owner xác nhận và backup/replay?}
    E -->|Không| X[Dừng, làm rõ trước]
    E -->|Có| F[Dừng workload ghi/đọc]
    F --> G[Kiểm tra delete.topic.enable và ACL]
    G --> H[Review lệnh delete cụ thể]
    H --> I[Delete topic]
    I --> J[Verify topic đã biến mất]
    J --> K[Audit và thông báo owner]
~~~

Các bước:

1. Nhận ticket/change có topic name, cluster, owner, lý do và thời điểm.
2. Xác minh endpoint/cluster identity và principal quản trị.
3. Describe topic, config, partition, RF, ISR và ACL.
4. Xác định toàn bộ producer/consumer/Connect/Streams/MirrorMaker dependency.
5. Xác nhận retention/legal hold, backup và replay plan.
6. Dừng producer, consumer và pipeline liên quan theo runbook.
7. Kiểm tra delete.topic.enable và DELETE ACL.
8. Review command với topic name cụ thể; không dùng wildcard.
9. Thực hiện delete một lần.
10. List/describe lại cho tới khi topic biến mất và metadata ổn định.
11. Kiểm tra producer/consumer errors, connector/Streams status và alert.
12. Lưu output trước/sau, người thực hiện và timestamp vào change record.

## 19. Runbook xóa consumer group an toàn

~~~mermaid
flowchart TD
    A[Nhận yêu cầu xóa group] --> B[Xác minh cluster và group ID]
    B --> C[Describe offsets, topics và state]
    C --> D[Liệt kê active members]
    D --> E{Group Empty và owner xác nhận?}
    E -->|Không| X[Dừng hoặc dừng workload trước]
    E -->|Có| F[Lưu offsets nếu cần phục hồi]
    F --> G[Kiểm tra DELETE ACL]
    G --> H[Delete group]
    H --> I[Verify group không còn]
    I --> J[Kiểm tra consumer không tự tạo lại]
~~~

Các bước:

1. Xác minh cluster và group ID chính xác.
2. Describe group, committed offsets, topic subscriptions và state.
3. Liệt kê members/host/client ID.
4. Xác định service/deployment/autoscaler nào có thể tạo group lại.
5. Dừng toàn bộ consumer instance và xác nhận group Empty.
6. Export offsets nếu có khả năng cần khôi phục.
7. Kiểm tra DELETE ACL trên group.
8. Thực hiện delete group.
9. List/describe lại để xác nhận group đã bị xóa.
10. Theo dõi để phát hiện group được tạo lại ngoài ý muốn.
11. Nếu consumer được bật lại, xác minh auto.offset.reset và kế hoạch replay.

## 20. Bài thực hành trong lab

Tạo topic lab.orders, producer và consumer group lab.orders-reader trên cluster thử nghiệm:

1. Gửi một số record vào topic.
2. Consume một phần record bằng group lab.orders-reader.
3. Describe topic để ghi lại partition/replica/config.
4. Describe group để ghi lại committed offsets và lag.
5. Reset offset bằng dry-run; so sánh output trước khi execute.
6. Dừng consumer, xác minh group Empty và member list rỗng.
7. Delete group trong lab; xác minh topic và record vẫn còn.
8. Chạy lại consumer cùng group ID với auto.offset.reset=earliest, quan sát replay.
9. Tạo lại group với auto.offset.reset=latest, quan sát vị trí bắt đầu khác.
10. Dừng producer/consumer và delete topic trong lab.
11. List topic để xác nhận deletion hoàn tất.
12. Tạo lại cùng tên topic và xác minh đây là topic mới, không có record cũ.

Không thực hiện bài lab trên cluster production hoặc cluster dùng chung của đội khác.

## 21. Checklist trước và sau thao tác

### Trước khi xóa topic

- [ ] Đã xác minh cluster identity và bootstrap server.
- [ ] Topic name được đối chiếu chính xác với ticket/owner.
- [ ] Topic không phải internal topic.
- [ ] Đã kiểm tra partition, RF, ISR và topic config.
- [ ] Đã xác định producer, consumer, connector, Streams và MirrorMaker dependency.
- [ ] Đã xác minh retention/legal hold và backup/replay.
- [ ] Workload đã dừng hoặc có kế hoạch phối hợp phù hợp.
- [ ] delete.topic.enable và DELETE ACL đã được kiểm tra.
- [ ] Lệnh delete cụ thể đã được review.

### Trước khi xóa group

- [ ] Đã xác minh cluster và group ID.
- [ ] Đã đọc offsets và danh sách topic-partition.
- [ ] Đã xác định owner/deployment/autoscaler.
- [ ] Tất cả member đã dừng; group state là Empty.
- [ ] Đã lưu offsets nếu cần khôi phục.
- [ ] Đã hiểu auto.offset.reset của consumer sẽ chạy lại.
- [ ] DELETE ACL đã được kiểm tra.

### Sau khi xóa

- [ ] List/describe xác nhận resource đã biến mất.
- [ ] Không có producer/consumer tự tạo lại resource ngoài ý muốn.
- [ ] Downstream service/connector/Streams không phát sinh lỗi mới.
- [ ] Alert và dashboard được kiểm tra.
- [ ] Output trước/sau và người thực hiện được lưu vào change record.

## 22. Những nhầm lẫn thường gặp

- **Delete topic giống retention:** delete loại bỏ toàn bộ topic; retention chỉ loại segment cũ theo policy.
- **Compaction xóa topic:** compaction chỉ rút gọn log theo key, topic vẫn tồn tại.
- **Delete group xóa record:** group deletion xóa metadata/offsets, record trong topic vẫn còn.
- **Delete topic xóa mọi consumer group:** topic và group là resource độc lập; cần kiểm tra/xử lý group theo mục tiêu riêng.
- **Reset offset cần xóa group:** reset offset có thể thực hiện trên group đang tồn tại sau khi dừng consumer.
- **Group Empty nghĩa là không ai dùng nữa:** deployment có thể khởi động lại và tạo group lại; cần xác nhận owner và autoscaler.
- **Xóa group rồi consumer tự đọc từ đầu:** vị trí bắt đầu phụ thuộc auto.offset.reset và log start offset còn tồn tại.
- **CLI delete có dry-run:** lệnh delete topic/group không có dry-run phổ quát; describe/list là bước preflight.
- **Delete command trả về nghĩa là mọi file đã được dọn ngay:** deletion và physical cleanup có thể bất đồng bộ; cần hậu kiểm.
- **Replication là backup:** xóa topic có thể áp dụng trên toàn bộ replica trong cluster; cần archive/replica độc lập để phục hồi.
- **Có thể xóa __consumer_offsets để reset một group:** đây là internal topic dùng chung và không được xử lý như group riêng.
- **Tạo lại topic cùng tên khôi phục dữ liệu:** topic mới không chứa log đã bị xóa.

Xóa topic và xóa consumer group là hai thao tác khác nhau nhưng đều cần preflight, xác minh owner và hậu kiểm. Xóa topic tác động tới log dữ liệu; xóa group tác động tới membership metadata và committed offsets. Khi mục tiêu chỉ là replay, hãy cân nhắc reset offset; khi mục tiêu là quản lý vòng đời dữ liệu, hãy xem retention/compaction. Chỉ thực hiện delete sau khi đã xác minh đúng cluster/resource, dependency, backup/replay, trạng thái workload và quyền quản trị.
