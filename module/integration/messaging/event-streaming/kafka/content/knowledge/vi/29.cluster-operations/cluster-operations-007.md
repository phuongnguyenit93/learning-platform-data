# Thay broker, thay đĩa và xử lý thư mục log lỗi

Broker Kafka lưu các partition replica trên đĩa. Khi thay máy chủ, thay ổ đĩa hoặc một thư mục trong `log.dirs` bị lỗi, mục tiêu vận hành là giữ đủ bản sao dữ liệu, khôi phục replica về trạng thái đồng bộ và đưa broker trở lại cluster mà không làm mất dữ liệu ngoài dự kiến.

Ba tình huống cần phân biệt:

- **Thay host nhưng giữ broker identity**: máy mới dùng lại `node.id` của broker cũ, cluster assignment không đổi; replica thiếu dữ liệu sẽ được đồng bộ lại từ leader còn khỏe.
- **Thay broker bằng node.id mới**: thêm broker mới, di chuyển replica bằng partition reassignment, xác minh ISR rồi mới loại broker cũ.
- **Thay một log directory/ổ đĩa**: broker có thể vẫn chạy với các thư mục khỏe; cần chuyển replica khỏi đĩa lỗi hoặc phục hồi chúng từ replica khác trước khi thay ổ.

Không xóa log directory, format lại storage hoặc khởi động hai máy cùng `node.id` khi chưa xác nhận bản sao dữ liệu và trạng thái cluster. Một thao tác dọn đĩa tưởng như đơn giản có thể xóa bản sao cuối cùng của partition.

## 1. Kafka lưu dữ liệu ở đâu?

Mỗi topic partition là một log riêng. Broker lưu các segment và index của partition trong một trong các thư mục được khai báo bởi `log.dirs`.

~~~properties
node.id=2
process.roles=broker
log.dirs=/data/kafka-1,/data/kafka-2
~~~

Với cấu hình trên, broker có thể lưu các replica trên cả hai mount point. Kafka phân bổ replica mới giữa các thư mục theo cơ chế log directory hiện hành; mỗi partition replica cụ thể nằm trong một thư mục tại một thời điểm.

Một số file thường thấy trong partition directory:

| File | Vai trò |
|---|---|
| `00000000000000000000.log` | Segment chứa record theo offset |
| `.index` | Offset index giúp tìm vị trí record |
| `.timeindex` | Timestamp index |
| `.txnindex` | Transaction index khi cần |
| `leader-epoch-checkpoint` | Thông tin leader epoch dùng khi phục hồi |
| `partition.metadata` | Metadata của partition replica trên các phiên bản hỗ trợ |

Không xóa riêng `.log`, `.index`, `.timeindex` hoặc checkpoint để “sửa” một partition. Các file liên quan nhau; xóa sai có thể gây mất dữ liệu hoặc làm quá trình recovery thất bại.

### Phân biệt log.dirs và metadata.log.dir trong KRaft

`log.dirs` chứa dữ liệu topic partition của broker. `metadata.log.dir` là nơi lưu metadata log của KRaft controller. Nếu không cấu hình riêng, vị trí metadata log phụ thuộc cấu hình storage và vai trò node theo phiên bản Kafka.

Không coi metadata log như một topic data thông thường. Với controller hoặc node kết hợp broker/controller, lỗi metadata storage có thể ảnh hưởng đến metadata quorum và khả năng quản lý toàn cluster. Quy trình thay controller cần xét quorum membership, không chỉ di chuyển partition replica như thay broker-only.

## 2. Quyết định thay broker bằng cùng hay khác node.id

Trước khi thao tác, chọn cách thay thế:

| Phương án | Identity | Partition assignment | Khi phù hợp |
|---|---|---|---|
| Thay host, giữ `node.id` | Giữ nguyên | Giữ nguyên | Máy cũ hỏng, máy mới thay đúng vị trí broker |
| Thay bằng broker mới | Dùng `node.id` mới | Reassign replica sang broker mới | Mở rộng cluster hoặc thay broker có thay đổi identity |
| Thay đĩa trên broker | `node.id` không đổi | Có thể giữ nguyên hoặc chuyển replica giữa log dirs | Chỉ một mount point bị lỗi |

Với broker-only node trong KRaft, `node.id` là identity của broker. Broker thay thế phải dùng đúng cluster ID của cluster hiện tại. Không tạo cluster mới bằng cách format với cluster ID khác.

Nếu node chạy `process.roles=broker,controller` hoặc `process.roles=controller`, việc thay node còn liên quan đến metadata quorum. Với static quorum phải cập nhật voter configuration theo quy trình phù hợp; với dynamic quorum phải thay đổi membership qua công cụ/API của phiên bản đang chạy. Không áp dụng nguyên xi runbook broker-only cho controller.

## 3. Preflight trước khi thay broker hoặc ổ đĩa

Ghi lại cấu hình và trạng thái trước khi dừng máy:

- `node.id`, `process.roles`, cluster ID, `broker.rack`.
- Listener, advertised listener, TLS/SASL và cấu hình replication.
- `log.dirs`, `metadata.log.dir`, filesystem và mount point.
- Topic/partition replica đang nằm trên broker.
- Leader, replica assignment và ISR của từng partition.
- Offline partition, under-replicated partition và reassignment đang chạy.
- Dung lượng trống, inode, IOPS, latency và tình trạng SMART của đĩa.
- Backup/snapshot hoặc bản sao dữ liệu độc lập nếu quy trình yêu cầu.

Kiểm tra partition của broker:

~~~bash
bin/kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --describe
~~~

Kiểm tra consumer group và lag nếu workload đang chạy:

~~~bash
bin/kafka-consumer-groups.sh --bootstrap-server kafka-1:9092 \
  --all-groups --describe
~~~

Kiểm tra log directory của các broker:

~~~bash
bin/kafka-log-dirs.sh --bootstrap-server kafka-1:9092 \
  --describe --broker-list "1,2,3"
~~~

Kiểm tra trạng thái metadata quorum trên KRaft:

~~~bash
bin/kafka-metadata-quorum.sh --bootstrap-server kafka-1:9092 \
  describe --status
~~~

Trước khi thay ổ hoặc xóa dữ liệu cũ, xác nhận mỗi partition có ít nhất một replica khỏe khác chứa dữ liệu cần giữ. Nếu partition chỉ còn bản sao trên broker/đĩa sắp thay, dừng quy trình và phục hồi hoặc sao lưu bản sao đó trước.

## 4. Thay host nhưng giữ nguyên node.id

Phương án này phù hợp khi host cũ hỏng và host mới sẽ tiếp quản đúng broker identity. Các bước dưới đây giả định node là broker-only; controller node cần quy trình quorum riêng.

### Bước 1: Fencing máy cũ

Đảm bảo tiến trình broker cũ đã dừng và không thể tự khởi động lại. Không để hai host cùng chạy với một `node.id`; broker mới có thể bị fencing hoặc đăng ký thất thường.

Nếu host cũ vẫn truy cập được, dừng Kafka một cách có kiểm soát. Nếu host mất nguồn, xác nhận hạ tầng đã fencing VM/instance hoặc network identity trước khi đưa host mới lên.

### Bước 2: Xác nhận dữ liệu còn bản sao khỏe

Kiểm tra ISR và offline partition. Nếu broker cũ là replica duy nhất còn dữ liệu mới nhất của một partition, không format hoặc bỏ ổ cũ. Ưu tiên khôi phục disk/host cũ hoặc tạo bản sao forensic trước khi thử recovery.

Với RF=3, hai replica còn lại trong ISR thường có thể phục vụ dữ liệu và đồng bộ replica mới. Tuy nhiên, phải kiểm tra từng partition; RF=3 không đảm bảo mọi partition đều còn hai replica khỏe tại thời điểm sự cố.

### Bước 3: Chuẩn bị host mới

Triển khai đúng:

- Kafka version và cấu hình tương thích với cluster.
- Cùng `node.id` của broker bị thay.
- Cùng `process.roles=broker` nếu đây là broker-only.
- Listener, advertised listener, rack và security config phù hợp.
- Mount point và `log.dirs` có quyền ghi, dung lượng đủ.
- Cluster ID của cluster hiện tại.

Không sao chép mù toàn bộ `meta.properties` từ ổ cũ nếu chưa hiểu directory ID và trạng thái storage. Với đĩa mới, chuẩn bị storage theo hướng dẫn KRaft của đúng phiên bản, dùng cluster ID hiện tại và không khởi tạo một quorum/cluster mới.

Ví dụ định dạng storage cho thư mục log mới, chỉ thực hiện trên các thư mục trống và sau khi đã xác nhận replica có thể được tái tạo từ broker khác:

~~~bash
bin/kafka-storage.sh format \
  --cluster-id <EXISTING_CLUSTER_ID> \
  --config config/server.properties \
  --no-initial-controllers
~~~

Ví dụ trên minh họa broker-only node gia nhập một KRaft cluster hiện hữu trong các release hỗ trợ tùy chọn `--no-initial-controllers`. Tùy release Kafka, cú pháp và lựa chọn bootstrap metadata quorum khi format có thể khác. Dùng đúng hướng dẫn KRaft của phiên bản triển khai; không dùng tùy chọn tạo standalone/initial quorum khi node đang gia nhập cluster hiện hữu. Không chạy format trên thư mục còn dữ liệu cần phục hồi.

### Bước 4: Khởi động broker mới

Khởi động broker và theo dõi log. Broker phải đăng ký được với cluster, kết nối controller, nhận partition assignment và bắt đầu fetch dữ liệu cho các replica bị thiếu.

~~~bash
bin/kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --describe --topic orders.events

bin/kafka-log-dirs.sh --bootstrap-server kafka-1:9092 \
  --describe --broker-list "2"
~~~

Đợi replica đồng bộ, ISR trở lại mức mong muốn và không còn offline partition ngoài dự kiến. Không đánh giá thành công chỉ dựa trên việc process Kafka đã chạy hoặc port đã mở.

### Bước 5: Xác minh sau thay thế

- Broker mới xuất hiện với đúng node ID.
- Replica trên broker mới có `error: null` trong log-dir description.
- Partition leader/replica assignment đúng như dự kiến.
- Under-replicated partition trở về 0 sau khi recovery hoàn tất.
- Producer/consumer hoạt động, lag giảm về mức bình thường.
- Không có lỗi storage, authentication hoặc registration lặp lại.

## 5. Thay broker bằng node.id mới

Nếu broker mới dùng identity khác, phải chuyển replica khỏi broker cũ. Không chỉ thêm máy mới rồi tắt máy cũ; cluster vẫn có thể giữ assignment trỏ đến broker cũ.

### Bước 1: Thêm broker mới

Provision broker mới với `node.id` chưa được sử dụng, cùng cluster ID, listener, rack và storage capacity phù hợp. Khởi động và xác nhận broker đã đăng ký với cluster.

### Bước 2: Tạo danh sách topic cần di chuyển

Tạo file `topics-to-move.json`:

~~~json
{
  "topics": [
    { "topic": "orders.events" },
    { "topic": "payments.events" }
  ],
  "version": 1
}
~~~

Sinh kế hoạch reassignment để phân phối các replica lên danh sách broker đích. Ví dụ broker cũ là 2; các broker đích được chọn là 1, 3 và 4:

~~~bash
bin/kafka-reassign-partitions.sh \
  --bootstrap-server kafka-1:9092 \
  --topics-to-move-json-file topics-to-move.json \
  --broker-list "1,3,4" \
  --generate
~~~

Lệnh `--generate` in ra kế hoạch đề xuất và assignment hiện tại. Lưu JSON kế hoạch mới vào file riêng, review từng partition để bảo đảm không bỏ replica ngoài ý muốn và không vượt capacity của broker đích.

### Bước 3: Thực thi reassignment

Ví dụ file `reassignment.json` đã được review:

~~~json
{
  "version": 1,
  "partitions": [
    {
      "topic": "orders.events",
      "partition": 0,
      "replicas": [1, 3, 4]
    }
  ]
}
~~~

Thực thi:

~~~bash
bin/kafka-reassign-partitions.sh \
  --bootstrap-server kafka-1:9092 \
  --reassignment-json-file reassignment.json \
  --execute
~~~

Kafka tạo replica mới và đồng bộ dữ liệu trước khi hoàn tất thay đổi assignment. Reassignment tiêu thụ network, disk I/O và có thể ảnh hưởng latency của workload. Với cluster lớn, dùng throttle và chia thành từng đợt theo hướng dẫn CLI của phiên bản hiện tại; không di chuyển toàn bộ replica cùng lúc nếu broker đang sát ngưỡng.

### Bước 4: Theo dõi và xác minh

~~~bash
bin/kafka-reassign-partitions.sh \
  --bootstrap-server kafka-1:9092 \
  --reassignment-json-file reassignment.json \
  --verify
~~~

Đồng thời kiểm tra `kafka-topics --describe`, ISR, offline partition và dung lượng broker. Chỉ dừng broker cũ khi mọi partition cần giữ đã có assignment mới, replica đích đồng bộ và không còn replica assignment nào trỏ đến broker cũ.

### Bước 5: Gỡ broker cũ

Sau khi xác minh:

1. Kiểm tra toàn bộ topic assignment và internal topics liên quan.
2. Xác nhận broker cũ không còn replica được gán.
3. Dừng broker cũ.
4. Thu hồi DNS, certificate, secret và quyền truy cập host cũ theo quy trình hạ tầng.
5. Theo dõi cluster sau khi broker rời đi.

Không xóa dữ liệu cũ cho đến khi thời gian quan sát và yêu cầu lưu trữ/rollback cho phép.

## 6. Thay một ổ đĩa trong broker có nhiều log.dirs

Với JBOD, một broker có thể dùng nhiều thư mục log trên nhiều volume. Nếu một đĩa bắt đầu có dấu hiệu lỗi nhưng vẫn đọc được, di chuyển replica khỏi volume đó trước khi thay ổ thường an toàn hơn chờ đến khi disk chết hoàn toàn.

Giả sử:

~~~properties
log.dirs=/data/kafka-a,/data/kafka-b,/data/kafka-c
~~~

Ổ `/data/kafka-b` có SMART warning hoặc latency tăng bất thường. Quy trình:

1. Kiểm tra partition replica đang nằm trên `/data/kafka-b`.
2. Xác nhận các log directory đích còn đủ dung lượng.
3. Chuyển replica khỏi `/data/kafka-b` sang log directory khỏe trên cùng broker hoặc sang broker khác.
4. Theo dõi tiến trình copy/recovery và ISR.
5. Xác nhận không còn replica cần giữ trên volume cũ.
6. Dừng broker theo kế hoạch, tháo/thay volume và mount volume mới đúng path.
7. Kiểm tra filesystem, ownership, permission và dung lượng.
8. Khởi động broker, kiểm tra log directories và partition health.

### Kiểm tra replica nằm trên thư mục nào

~~~bash
bin/kafka-log-dirs.sh --bootstrap-server kafka-1:9092 \
  --describe --broker-list "2" \
  --topic-list orders.events
~~~

Kết quả trả về theo broker và log directory, kèm partition, size, offset lag, trạng thái future replica và error nếu có. Đối chiếu path thực tế với `log.dirs` trước khi tháo volume.

### Di chuyển replica giữa các log directory

Kafka Admin API có thao tác `alterReplicaLogDirs` để yêu cầu chuyển một replica sang log directory khác trên cùng broker. Ví dụ Java minh họa:

~~~java
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.common.TopicPartitionReplica;

Properties props = new Properties();
props.put("bootstrap.servers", "kafka-1:9092");

try (Admin admin = Admin.create(props)) {
    TopicPartitionReplica replica =
        new TopicPartitionReplica("orders.events", 0, 2);

    admin.alterReplicaLogDirs(
        Map.of(replica, "/data/kafka-c")
    ).all().get(30, TimeUnit.SECONDS);
}
~~~

Lệnh trên gửi yêu cầu di chuyển; nó không chứng minh dữ liệu đã chuyển xong. Tiếp tục polling `describeReplicaLogDirs` hoặc `kafka-log-dirs.sh --describe` để xác nhận replica đã nằm ở path mới và không còn future replica đang copy. API yêu cầu quyền quản trị tương ứng và log directory đích phải nằm trong `log.dirs` của broker.

Nếu đĩa đã hỏng và replica ở đó không thể đọc, thao tác chuyển local replica có thể không thực hiện được. Khi đó cần tái tạo replica từ một broker khỏe thông qua partition reassignment hoặc recovery procedure phù hợp. Không giả định Kafka có thể copy dữ liệu từ volume đã chết.

## 7. Xử lý log directory bị lỗi khi broker vẫn chạy

Trong cấu hình nhiều `log.dirs`, Kafka có thể đánh dấu một log directory là offline khi gặp lỗi I/O. Các partition replica nằm trên thư mục đó có thể chuyển sang trạng thái offline, trong khi broker tiếp tục phục vụ replica trên thư mục khỏe khác. Hành vi cụ thể phụ thuộc loại lỗi, vai trò node và phiên bản Kafka.

Dấu hiệu thường gặp:

- Broker log có `KafkaStorageException`, `StorageException` hoặc lỗi I/O.
- `kafka-log-dirs.sh --describe` trả về error cho một path.
- Một số partition replica có offline log directory.
- `OfflineLogDirectoryCount` tăng.
- `UnderReplicatedPartitions` tăng hoặc consumer/producer báo lỗi với partition liên quan.
- Broker shutdown nếu không còn log directory khả dụng hoặc lỗi ảnh hưởng metadata storage.

### Quy trình xử lý

1. Xác định chính xác path bị lỗi và partition replica nằm trên path đó.
2. Kiểm tra filesystem, kernel log, SMART, mount status, inode và permission.
3. Xác định broker có còn log directory khỏe không.
4. Kiểm tra mỗi partition có replica khỏe ở broker khác hay không.
5. Nếu đĩa vẫn đọc được, ưu tiên di chuyển replica khỏi path lỗi.
6. Nếu đĩa không đọc được, phục hồi replica từ broker khỏe bằng reassignment.
7. Sau khi mọi replica cần giữ đã được phục hồi, dừng broker và thay volume.
8. Khởi động lại, kiểm tra log directory status, ISR và broker metrics.

Nếu lỗi xảy ra trên controller/combined node và path là `metadata.log.dir`, dừng quy trình broker-only. Bảo toàn metadata quorum và thực hiện recovery theo quy trình controller KRaft của phiên bản triển khai.

## 8. Khi broker mất toàn bộ log directory

Nếu tất cả `log.dirs` trên broker đều offline, broker có thể không tiếp tục phục vụ. Không khởi động lặp lại bằng cách xóa thư mục hoặc format storage để “làm sạch”.

Thứ tự xử lý:

1. Fencing broker nếu tiến trình restart liên tục hoặc filesystem lỗi.
2. Bảo toàn các ổ còn có thể đọc; tạo snapshot/clone nếu có khả năng cần forensic recovery.
3. Kiểm tra offline partition và ISR của cluster.
4. Xác định partition nào còn replica khỏe ở broker khác.
5. Khôi phục filesystem/volume hoặc thay broker với cùng identity khi phù hợp.
6. Nếu cần, reassignment để tạo replica mới từ nguồn dữ liệu khỏe.
7. Chỉ mở lại traffic khi partition có leader hợp lệ và ISR đáp ứng durability policy.

Nếu một partition không còn replica nào chứa dữ liệu cần thiết, Kafka không thể tái tạo các record đã mất chỉ từ metadata. Cần khôi phục từ backup/nguồn upstream hoặc chấp nhận mất dữ liệu theo quyết định nghiệp vụ. Unclean leader election có thể chọn replica không đồng bộ và làm mất record đã được xác nhận trước đó; không bật nó như một thao tác chữa lỗi mặc định.

## 9. Phân biệt offline replica, under-replicated và offline partition

| Trạng thái | Ý nghĩa | Mức độ |
|---|---|---|
| Offline log directory | Broker không dùng được một path lưu trữ | Có thể ảnh hưởng một phần partition trên broker |
| Offline replica | Replica không khả dụng trên broker/path | Partition có thể còn leader và replica khác |
| Under-replicated partition | Số replica trong ISR thấp hơn replica assignment | Dữ liệu vẫn có thể phục vụ nhưng mức dự phòng giảm |
| Offline partition | Không có leader khả dụng | Client không thể đọc/ghi partition bình thường |
| Under-min-ISR | ISR thấp hơn `min.insync.replicas` | Producer `acks=all` có thể bị từ chối ghi |

Một partition có thể under-replicated nhưng vẫn có leader phục vụ traffic. Offline partition nghiêm trọng hơn vì không có leader để phục vụ client.

## 10. Kiểm tra sau thay broker hoặc disk

Checklist xác minh:

- Broker đăng ký đúng cluster ID và node.id.
- Listener/advertised listener và security handshake hoạt động.
- Tất cả `log.dirs` mong muốn hiển thị khỏe.
- `kafka-log-dirs.sh` không báo error trên path mới.
- Không còn replica cần giữ nằm trên ổ cũ.
- Partition leader và replica assignment đúng.
- ISR trở lại mức yêu cầu.
- Offline partition bằng 0.
- Under-replicated partition trở về 0 sau khi catch-up.
- Producer `acks=all` ghi thành công.
- Consumer đọc tiếp từ offset đúng và lag ổn định.
- Kafka Streams state store/changelog restore hoàn tất nếu có task chuyển host.
- Kafka Connect source/sink tasks hoạt động và không lặp lỗi.
- Disk utilization, IOPS, network và request latency ở mức bình thường.

Các lệnh kiểm tra tổng hợp:

~~~bash
bin/kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --describe --under-replicated-partitions

bin/kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --describe --unavailable-partitions

bin/kafka-log-dirs.sh --bootstrap-server kafka-1:9092 \
  --describe --broker-list "1,2,3"
~~~

Tên option và khả năng lọc có thể khác theo phiên bản Kafka; kiểm tra `--help` của distribution đang chạy nếu CLI không nhận option.

## 11. Những thao tác cần tránh

| Thao tác | Rủi ro |
|---|---|
| Format lại disk khi chưa xác minh replica khác | Xóa bản sao dữ liệu cuối cùng |
| Chạy hai broker với cùng node.id | Broker fencing, registration conflict hoặc trạng thái không ổn định |
| Thay cluster ID khi thay host | Node không còn thuộc cluster hiện tại |
| Xóa partition directory thủ công khi broker đang chạy | Metadata/log inconsistency và mất dữ liệu |
| Xóa toàn bộ `log.dirs` để xử lý lỗi một disk | Mất tất cả replica cục bộ |
| Tắt broker cũ trước khi reassignment hoàn tất | Replica assignment vẫn trỏ đến broker không còn hoạt động |
| Bật unclean leader election để đưa partition online | Có thể mất các record chưa có trên replica được chọn |
| Tháo volume khi broker còn ghi | Hỏng segment/index và lỗi filesystem |
| Mount sai path rồi khởi động Kafka | Kafka có thể ghi vào filesystem gốc tại mount point |

Đặc biệt kiểm tra mount point trước khi start broker. Nếu volume chưa mount, thư mục `/data/kafka-b` có thể vẫn tồn tại trên root filesystem; Kafka có thể ghi dữ liệu vào đó, sau đó dữ liệu bị che khuất khi volume thật được mount lại.

## 12. Runbook rút gọn

~~~mermaid
flowchart TD
    A["Phát hiện broker/disk lỗi"] --> B["Fencing và xác định phạm vi"]
    B --> C["Kiểm tra ISR, offline partitions, log dirs"]
    C --> D{"Còn bản sao dữ liệu khỏe?"}
    D -->|Không| E["Bảo toàn disk/backup, dừng thay thế"]
    D -->|Có| F{"Thay host hay chỉ thay disk?"}
    F -->|Host, giữ node.id| G["Chuẩn bị host mới và storage cùng cluster ID"]
    F -->|Broker node.id mới| H["Thêm broker mới, reassignment"]
    F -->|Một log dir| I["Di chuyển replica khỏi volume lỗi"]
    G --> J["Khởi động và catch-up replica"]
    H --> K["Verify reassignment và ISR"]
    I --> L["Thay volume, mount và kiểm tra"]
    J --> M["Health checks"]
    K --> M
    L --> M
    M --> N["Đóng sự cố và lưu audit"]
~~~

Khi sự cố xảy ra, ghi lại thời điểm, broker/node ID, path lỗi, partition bị ảnh hưởng, ISR trước/sau, thao tác đã chạy và kết quả xác minh. Nhật ký này giúp phân biệt lỗi phần cứng, cấu hình mount, lỗi storage và lỗi replication trong lần điều tra tiếp theo.

## 13. Bài tập tự kiểm tra

1. `log.dirs` khác `metadata.log.dir` như thế nào trong KRaft?
2. Khi nào nên thay host bằng cách giữ nguyên `node.id`?
3. Vì sao phải xác nhận ISR trước khi format storage của broker cũ?
4. Khi thay broker bằng `node.id` mới, tại sao phải reassignment replica?
5. Làm thế nào để biết partition replica đang nằm trên log directory nào?
6. `alterReplicaLogDirs` dùng để làm gì và vì sao phải xác minh sau khi gửi request?
7. Phân biệt offline log directory, under-replicated partition và offline partition.
8. Tại sao mount point phải được kiểm tra trước khi khởi động broker?
9. Vì sao không nên bật unclean leader election như cách sửa lỗi mặc định?
10. Khi broker đồng thời là controller trong KRaft, vì sao phải có quy trình quorum riêng?

## Kết luận

Thay broker, thay đĩa và xử lý log directory lỗi đều phải bắt đầu bằng việc xác định dữ liệu còn bản sao khỏe ở đâu. Thay host với cùng `node.id` giữ nguyên assignment nhưng cần bảo đảm host cũ đã được fencing và storage mới thuộc đúng cluster ID. Thay bằng broker ID mới cần reassignment và xác minh ISR trước khi gỡ broker cũ. Thay một disk trong JBOD cần di chuyển hoặc tái tạo replica khỏi volume lỗi trước khi tháo ổ.

Trong KRaft, cần phân biệt broker data log với metadata log của controller. Không format, xóa partition directory hoặc bật unclean leader election chỉ để làm cluster “xanh” trở lại. Hoàn tất sự cố khi broker, log directories, replica, ISR và client đều hoạt động đúng, dữ liệu được bảo toàn theo durability policy và mọi thay đổi đã được ghi nhận.
