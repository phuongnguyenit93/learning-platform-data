# Runbook khi topic mất dữ liệu

Runbook này hướng dẫn xử lý sự cố khi một Kafka topic được cho là đã mất record, mất một phần lịch sử hoặc không còn cung cấp dữ liệu mà consumer cần. Mục tiêu đầu tiên là bảo vệ dữ liệu còn lại và xác định chính xác điều gì đã xảy ra. Sau đó mới chọn cách khôi phục từ nguồn dữ liệu có thể tin cậy.

Một topic trống hoặc consumer không đọc thấy record chưa đủ để kết luận Kafka đã làm mất dữ liệu. Record có thể đã hết retention, bị compaction loại bỏ, được consumer group commit vượt qua, bị lọc ở tầng ứng dụng hoặc đang nằm trên cluster/topic khác. Những trường hợp này có cách xử lý khác nhau. Đặc biệt, reset consumer offset không khôi phục record đã bị xóa khỏi log.

## 1. Nguyên tắc xử lý sự cố

Trong suốt incident, giữ các nguyên tắc sau:

1. **Bảo toàn bằng chứng trước khi thay đổi cấu hình.** Ghi lại topic metadata, topic config, partition offsets, consumer group offsets, broker health, log và mốc thời gian.
2. **Xác định phạm vi trước khi khôi phục.** Tìm topic, partition, khoảng thời gian, key hoặc nhóm record bị ảnh hưởng; xác định producer, consumer và hệ thống downstream liên quan.
3. **Phân biệt log data với consumer position.** Kafka lưu record trong partition log; consumer group lưu offset đã commit. Hai loại trạng thái này độc lập.
4. **Không coi replica là backup.** Replica giúp chịu lỗi broker. Các thao tác xóa record, retention và compaction được phản ánh trên các replica theo cơ chế replication.
5. **Không reset offset hoặc publish lại dữ liệu khi chưa có kế hoạch chống duplicate.** Replay có thể chạy lại side effect như trừ tiền, gửi thông báo hoặc tạo đơn hàng.
6. **Không xóa rồi tạo lại topic để thử khắc phục.** Việc này có thể làm mất thêm dữ liệu, thay đổi topic identity và phá vỡ liên kết với consumer group hoặc hệ thống quản lý schema.
7. **Chỉ kết thúc incident sau khi xác minh dữ liệu và luồng nghiệp vụ.** Topic có leader và ISR khỏe mạnh chưa chứng minh dữ liệu nghiệp vụ đã đầy đủ.

Nếu có thể, chỉ định một incident commander điều phối, một Kafka operator thu thập trạng thái cluster và owner của producer/consumer xác minh dữ liệu nghiệp vụ. Ghi lại thời điểm bắt đầu, thay đổi gần nhất và mọi hành động đã thực hiện.

## 2. Nhận diện đúng loại sự cố

Trước tiên, mô tả điều người dùng hoặc hệ thống quan sát được:

- Topic không tồn tại hoặc không truy cập được.
- Một hay nhiều partition có ít record hơn dự kiến.
- Record trong một khoảng thời gian không xuất hiện.
- Consumer group đã đọc đến offset mới nhưng nghiệp vụ chưa xử lý đủ.
- Consumer lag tăng, đứng yên hoặc đột ngột giảm về 0.
- Một key không còn giá trị hoặc không còn lịch sử như mong đợi.
- Producer báo gửi thành công nhưng consumer không tìm thấy record.

Phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa | Cách kiểm tra ban đầu |
|---|---|---|
| Log start offset | Offset sớm nhất còn được giữ trong partition | So sánh với thời điểm và offset cần điều tra |
| Log end offset | Ranh giới offset cuối hiện có của partition | Đối chiếu với tốc độ ghi và producer metadata |
| Consumer committed offset | Vị trí group đã commit để tiếp tục đọc | Kiểm tra group, partition và commit history |

Offset là số thứ tự trong partition, không phải số lượng record nghiệp vụ liên tục. Compaction, transaction và một số thao tác nội bộ có thể tạo khoảng trống offset. Vì vậy, chỉ thấy offset nhảy không chứng minh record bị mất.

## 3. Phản ứng ban đầu: bảo toàn trạng thái

### 3.1. Ghi nhận thông tin incident

Ghi lại tối thiểu:

- Tên cluster, môi trường, topic và consumer group.
- Thời điểm cuối cùng dữ liệu được xác nhận đầy đủ và thời điểm đầu tiên phát hiện bất thường.
- Danh sách partition bị ảnh hưởng hoặc phạm vi chưa xác định.
- Tên ứng dụng producer/consumer và phiên bản vừa triển khai.
- Thay đổi gần đây: tạo/xóa topic, đổi partition, retention, cleanup policy, ACL, broker, storage hoặc cấu hình consumer.
- Mã correlation/event ID, key mẫu và nguồn dữ liệu có thể đối chiếu.

Chuẩn hóa múi giờ khi so sánh log của broker, producer, consumer và hệ thống nghiệp vụ. Lưu lại command, output, timestamp và người thực hiện cho mỗi hành động trong incident.

### 3.2. Kiểm tra topic và partition

Dùng Kafka CLI với bootstrap server và thông tin xác thực của đúng cluster:

~~~bash
kafka-topics.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --topic orders
~~~

Đọc kết quả theo từng partition:

- Partition có leader hay đang offline?
- Danh sách replica có đúng như dự kiến?
- ISR có thiếu replica không?
- Có partition nào không có leader hoặc under-replicated kéo dài không?
- Số partition có đúng với cấu hình trước incident không?

Nếu topic không được tìm thấy, xác nhận bootstrap server, cluster, tên topic, quyền truy cập và metadata trước khi kết luận topic đã bị xóa. Một client trỏ nhầm cluster có thể cho kết quả giống như topic mất tích.

### 3.3. Lưu cấu hình topic

~~~bash
kafka-configs.sh \
  --bootstrap-server broker1:9092 \
  --entity-type topics \
  --entity-name orders \
  --describe
~~~

Ghi lại các cấu hình liên quan đến lưu giữ và độ bền dữ liệu:

- **cleanup.policy:** delete, compact hoặc kết hợp compact,delete.
- **retention.ms** và **retention.bytes:** giới hạn giữ dữ liệu theo thời gian hoặc dung lượng.
- **delete.retention.ms:** khoảng giữ tombstone trong topic compact.
- **segment.ms** và **segment.bytes:** điều kiện roll log segment.
- **min.insync.replicas:** số replica tối thiểu trong ISR khi producer dùng acks=all.

Kiểm tra cả cấu hình cấp broker nếu topic không có override. Giá trị hiệu lực có thể khác giá trị mặc định mà đội vận hành nhớ từ trước incident.

### 3.4. Ghi nhận offset của từng partition

~~~bash
kafka-get-offsets.sh \
  --bootstrap-server broker1:9092 \
  --topic orders \
  --time -2

kafka-get-offsets.sh \
  --bootstrap-server broker1:9092 \
  --topic orders \
  --time -1
~~~

Với Kafka CLI có hỗ trợ kafka-get-offsets.sh, --time -2 lấy earliest offset và --time -1 lấy latest offset. Lưu output cho tất cả partition. Nếu phiên bản Kafka đang dùng có cú pháp khác, dùng công cụ tương ứng của phiên bản đó và ghi rõ phương pháp lấy offset.

Hai mốc này cho biết phạm vi log còn có thể đọc tại thời điểm kiểm tra. Chúng không cho biết record nghiệp vụ nào đã bị thiếu. Cần so sánh với offset hoặc timestamp đã ghi nhận từ trước, producer metadata, consumer log và nguồn dữ liệu gốc.

### 3.5. Ghi nhận consumer group

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --group orders-service
~~~

Ghi lại current/committed offset, log end offset, lag và partition assignment. Nếu cần xem toàn bộ group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --list
~~~

Consumer group offset cho biết vị trí group sẽ tiếp tục đọc. Nó không phải bằng chứng record trước offset đó đã được xử lý thành công. Nếu ứng dụng commit trước khi hoàn tất side effect, hoặc commit khi xử lý bất đồng bộ chưa xong, group có thể bỏ qua record dù nghiệp vụ chưa hoàn tất.

## 4. Xác định nguyên nhân

Dùng các dấu hiệu sau để khoanh vùng. Một incident có thể có nhiều nguyên nhân cùng lúc; ví dụ broker outage xảy ra sau khi retention đã xóa một phần lịch sử.

### 4.1. Retention đã xóa dữ liệu cũ

**Dấu hiệu:** log start offset của partition đã tiến vượt qua khoảng offset cần tìm; cấu hình retention.ms hoặc retention.bytes có giới hạn; thời gian record bị thiếu nằm ngoài cửa sổ dữ liệu còn giữ.

Kafka có thể xóa log segment cũ khi chúng không còn nằm trong thời hạn hoặc giới hạn dung lượng. Việc xóa segment không nhất thiết diễn ra đúng vào thời điểm từng record hết hạn; segment được quản lý theo đơn vị log segment.

**Xác minh:**

- So sánh timestamp sự kiện cần tìm với retention hiệu lực.
- Kiểm tra retention.ms, retention.bytes, cấu hình broker và thời điểm segment bị xóa trong broker log.
- Đối chiếu log start offset hiện tại với offset đã ghi lại trước incident.
- Xem tốc độ tăng dữ liệu và dung lượng disk trong khoảng thời gian liên quan.

**Xử lý:** tăng retention có thể bảo vệ dữ liệu còn lại trong các segment chưa bị xóa, nhưng không phục hồi segment đã bị xóa. Muốn khôi phục phần đã mất cần replay từ nguồn dữ liệu gốc, backup hoặc bản sao độc lập còn giữ đủ khoảng thời gian.

### 4.2. Log compaction đã loại bỏ phiên bản cũ

**Dấu hiệu:** topic có cleanup.policy=compact hoặc compact,delete; consumer tìm một event cũ nhưng key hiện chỉ còn giá trị mới nhất.

Compaction giữ lại giá trị mới nhất theo key trong log đã compact. Đây là hành vi phù hợp với topic lưu trạng thái hiện tại theo key, nhưng không bảo đảm giữ toàn bộ lịch sử event. Với compact,delete, dữ liệu còn chịu thêm giới hạn retention.

Tombstone là record có key và value null, biểu thị xóa key trong topic compact. Sau khoảng delete.retention.ms, compaction có thể loại bỏ tombstone và các giá trị cũ liên quan theo quy tắc compact.

**Xác minh:**

- Kiểm tra cleanup.policy, delete.retention.ms và lịch sử thay đổi cấu hình.
- Xác định yêu cầu nghiệp vụ là trạng thái mới nhất hay toàn bộ event history.
- Đối chiếu key bị thiếu với event tạo, cập nhật và tombstone từ nguồn gốc.

**Xử lý:** nếu compaction đã loại bỏ phiên bản cũ, tăng retention hoặc đổi cleanup policy không thể làm phiên bản đó xuất hiện trở lại. Khôi phục từ event store, backup hoặc nguồn phát lại. Nếu cần lưu toàn bộ lịch sử, thiết kế topic event history với chính sách lưu giữ phù hợp thay vì phụ thuộc vào compacted topic.

### 4.3. Consumer group đã commit vượt qua record

**Dấu hiệu:** record vẫn còn trong log nhưng committed offset của group đã vượt qua vị trí cần xử lý; log ứng dụng có commit thành công trước khi xử lý nghiệp vụ hoàn tất.

Các tình huống thường gặp:

- Consumer commit offset trước khi ghi database hoặc gọi dịch vụ phụ trợ.
- Xử lý bất đồng bộ nhưng acknowledgment được gửi khi tác vụ chưa hoàn thành.
- Có một deployment lỗi ghi nhận offset sau khi bỏ qua record.
- Một operator reset offset tiến lên hoặc ứng dụng dùng group ID khác với dự kiến.

**Xác minh:** so sánh log start/end offset, committed offset, timestamp xử lý và transaction/DB log. Xác định record có còn trong log hay không. Kiểm tra group ID, auto.offset.reset, acknowledgment mode, manual commit và logic xử lý bất đồng bộ.

**Xử lý:** nếu record còn trong log, có thể replay bằng một consumer group phục hồi riêng để xác minh và xử lý lại. Nếu cần thay đổi offset group hiện tại, phải tính đến consumer đang chạy, duplicate và side effect; xem quy trình ở phần khôi phục offset.

### 4.4. Producer chưa ghi hoặc ghi sang nơi khác

**Dấu hiệu:** producer không có metadata xác nhận, send error hoặc timeout; record xuất hiện ở topic/cluster khác; traffic theo partition thấp hơn số liệu upstream.

Kiểm tra:

- Producer log, callback error, retry, delivery timeout và buffer exhaustion.
- acks, idempotence, retry và transaction commit.
- Bootstrap server, topic name, serializer, partitioner, key và schema.
- ACL có cho phép producer ghi đúng topic không.
- Producer có ghi vào cluster khác do cấu hình môi trường hoặc secret không.

Nếu producer dùng acks=0, client không nhận xác nhận từ broker về việc record đã được ghi. Với acks=1, leader có thể xác nhận trước khi replica khác sao chép. acks=all chờ ISR theo cơ chế Kafka và kết hợp với min.insync.replicas để đặt yêu cầu durability. Cấu hình producer hiện tại không chứng minh cấu hình tại thời điểm incident; hãy xem deployment history và metric tương ứng.

### 4.5. Replica hoặc leader election làm mất phần dữ liệu chưa replicate

**Dấu hiệu:** broker outage, ISR shrink, under-replicated partitions, leader election bất thường hoặc log có thông tin về unclean leader election trong thời gian mất record.

Nếu leader cũ xác nhận record trước khi replica theo kịp, một replica không có record đó có thể được bầu làm leader trong một số tình huống cấu hình cho phép unclean election. Khi đó, record đã được xác nhận bởi leader cũ có thể không còn trên log leader mới.

**Xác minh:**

- Kiểm tra broker log, controller log, ISR changes, leader changes và thời điểm broker mất kết nối.
- Đối chiếu producer acknowledgment, min.insync.replicas và trạng thái ISR tại thời điểm gửi.
- Kiểm tra metric under-replicated partitions, replica fetch lag và storage error.
- Xác định có broker hoặc replica cũ còn giữ segment chưa bị ghi đè hay không; bảo toàn disk và log để đội Kafka chuyên trách điều tra.

**Xử lý:** khôi phục broker/replica chỉ giúp nếu dữ liệu cần thiết vẫn còn trên bản sao có thể sử dụng. Không ép replica cũ làm leader hoặc thay đổi election policy tùy tiện. Nếu mọi replica hợp lệ đều không còn record, cần nguồn phục hồi độc lập.

### 4.6. Topic bị xóa rồi tạo lại

**Dấu hiệu:** topic biến mất rồi xuất hiện lại; partition offset bắt đầu lại; topic ID hoặc metadata khác với trước; có audit log hoặc lệnh quản trị xóa topic.

Tạo lại topic cùng tên không khôi phục log cũ. Topic mới có thể có cùng số partition nhưng dữ liệu và topic identity khác. Kiểm tra audit trail, broker/controller log, automation và deployment script để tìm thao tác delete/create.

**Xử lý:** dừng automation có thể tiếp tục xóa/tạo topic. Bảo toàn cluster log và storage còn liên quan. Khôi phục từ backup hoặc nguồn upstream vào một topic phục hồi riêng, xác minh xong mới chuyển consumer sang luồng phục hồi theo kế hoạch.

### 4.7. Record tồn tại nhưng ứng dụng không nhìn thấy

**Dấu hiệu:** offset và broker metric cho thấy record đã ghi, nhưng consumer không phát sinh xử lý hoặc dashboard nghiệp vụ không có dữ liệu.

Kiểm tra:

- Consumer có subscribe đúng topic và pattern không?
- Group ID, partition assignment và ACL có đúng không?
- Consumer dùng read_committed có đang bỏ qua transactional record chưa commit hoặc đã abort không?
- Có filter, deserializer error, schema incompatibility, exception handler hoặc error handler gửi record sang DLT không?
- Record có bị loại bởi logic nghiệp vụ hoặc truy vấn downstream không?
- Dashboard có lọc theo timestamp, tenant, key hoặc trạng thái sai không?

Đối chiếu raw record bằng consumer kiểm tra trong group riêng, không dùng group production để thử. Nếu đọc bằng group mới thấy record, vấn đề có thể nằm ở offset hoặc logic consumer. Nếu raw record cũng không còn, tiếp tục điều tra retention, compaction, producer hoặc replication.

## 5. Cây quyết định điều tra nhanh

~~~text
Record nghiệp vụ bị thiếu
        |
        v
Đúng cluster, topic và partition?
   | Không                  | Có
   v                        v
Sửa endpoint/tên       Record còn trong log?
                            | Có                 | Không
                            v                    v
                    Kiểm tra group offset,   Kiểm tra retention,
                    ACL, filter, schema,     compaction, delete,
                    transaction, DLT        producer và replication
                            |                    |
                            v                    v
                    Replay có kiểm soát    Tìm backup hoặc nguồn
                    nếu cần                dữ liệu độc lập để replay
~~~

Sơ đồ này giúp chọn nhánh điều tra đầu tiên. Không dùng một nhánh đơn lẻ làm kết luận trước khi đối chiếu log và dữ liệu nghiệp vụ.

## 6. Quy trình khôi phục dữ liệu

### 6.1. Chọn nguồn phục hồi

Ưu tiên nguồn có thể chứng minh tính đầy đủ và thứ tự của dữ liệu:

1. **Nguồn dữ liệu gốc:** database, transactional outbox, event store hoặc hệ thống đã tạo event.
2. **Backup hoặc bản sao độc lập:** backup cluster, object storage chứa event, MirrorMaker/Cluster Linking hoặc hệ thống DR còn giữ đúng khoảng thời gian.
3. **Nguồn nghiệp vụ có thể tái dựng:** dữ liệu lịch sử đủ để tạo lại event với ID, key, timestamp và payload tương ứng.
4. **DLT hoặc retry topic:** chỉ dùng nếu đã xác nhận nó chứa đúng các record cần khôi phục; DLT thường chỉ chứa record lỗi, không phải bản sao đầy đủ của topic.

Replica trong cùng cluster không phải nguồn backup cho record đã bị retention, compaction hoặc delete. Nếu thao tác xóa đã replicate, tất cả replica có thể cùng không còn record đó.

### 6.2. Tạo vùng phục hồi riêng

Ưu tiên khôi phục vào topic riêng, ví dụ orders-recovery-incident-2026, hoặc cluster phục hồi. Điều này giúp:

- Kiểm tra số lượng, partition, key, timestamp và payload trước khi ảnh hưởng consumer thật.
- Chạy thử consumer phục hồi và đo duplicate.
- Giữ được dữ liệu gốc và dữ liệu replay tách biệt để audit.
- Chỉ chuyển traffic khi owner nghiệp vụ xác nhận kết quả.

Chọn số partition, replication factor, cleanup policy, retention và ACL theo yêu cầu phục hồi. Nếu thứ tự theo key là bắt buộc, dùng cùng quy tắc partitioning và bảo đảm record cùng key đi đúng partition theo thiết kế. Không giả định rằng publish lại với partition count khác sẽ giữ thứ tự tương đương topic cũ.

### 6.3. Xác định khoảng dữ liệu cần replay

Lập danh sách theo partition hoặc theo khóa nghiệp vụ:

- Khoảng thời gian bắt đầu và kết thúc theo UTC.
- Offset đầu/cuối nếu có checkpoint đáng tin cậy.
- Key hoặc event ID cần khôi phục.
- Số record và số byte dự kiến.
- Trạng thái xử lý của downstream.

Không suy ra số record bị mất bằng phép trừ offset một cách máy móc. Compaction, transaction và offset gap có thể làm số offset khác số record nghiệp vụ. Dùng event ID hoặc nguồn dữ liệu gốc để xác định tập record chính xác khi có thể.

### 6.4. Replay an toàn

Trước khi replay:

- Xác nhận owner nghiệp vụ chấp nhận chạy lại side effect.
- Dùng idempotency key hoặc deduplication theo event ID.
- Chọn replay group hoặc consumer phục hồi riêng.
- Kiểm soát tốc độ replay để không làm quá tải database/API.
- Ghi lại source, incident ID, replay window và kết quả.
- Xác định cách xử lý event đến muộn và event đã được xử lý một phần.

Nếu producer phát lại dữ liệu, giữ key, schema, header và timestamp nghiệp vụ gốc khi hệ thống cần các trường đó. Có thể bổ sung header cho biết record là replay và incident ID, nhưng không ghi đè thông tin nguồn cần cho audit.

Nếu downstream không idempotent, đưa record vào vùng kiểm tra và xây dựng quy trình đối soát trước khi cho phép xử lý thật. Không phát lại trực tiếp vào topic đang được consumer production sử dụng khi chưa kiểm soát duplicate và thứ tự.

## 7. Khôi phục consumer offset khi record vẫn còn

Chỉ dùng phần này khi đã xác nhận record cần đọc lại vẫn tồn tại trong log. Reset offset thay đổi vị trí đọc của group; nó không tạo lại dữ liệu đã bị xóa.

### 7.1. Ưu tiên group phục hồi riêng

Tạo một consumer group riêng cho việc kiểm tra/replay thường an toàn hơn sửa offset của group production. Group riêng có thể đọc lại dữ liệu mà không làm gián đoạn vị trí commit của ứng dụng hiện tại. Tuy nhiên, side effect của consumer vẫn phải được kiểm soát.

### 7.2. Preview trước khi reset

Ví dụ dưới đây chỉ mô phỏng đưa group về earliest offset của topic. Tùy phiên bản Kafka, cú pháp CLI có thể khác:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --group orders-service \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

Đọc kỹ output theo từng partition. --to-earliest chỉ đưa group về log start offset hiện còn; nó không thể đọc lại segment đã hết retention hoặc record đã bị compaction loại bỏ.

Nếu chỉ một partition hoặc một khoảng offset bị ảnh hưởng, giới hạn phạm vi reset tương ứng. Với --to-offset, xác định offset đích chính xác và kiểm tra ý nghĩa của offset đó theo partition. Với --to-datetime, xác nhận timestamp và timezone; offset được tìm theo timestamp record, không bảo đảm khớp chính xác ranh giới nghiệp vụ.

Chỉ sau khi preview được owner xác nhận, consumer của group đã dừng hoặc được điều phối theo quy trình, mới thực hiện reset. Ví dụ lệnh thực thi có thể bỏ --dry-run:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --group orders-service \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --execute
~~~

Đây là thao tác thay đổi trạng thái group. Không chạy ví dụ này theo kiểu copy/paste trong incident; thay topic, group, partition và offset theo kết quả điều tra, sau đó ghi nhận phê duyệt và output.

### 7.3. Theo dõi sau reset

Khởi động consumer theo kế hoạch, theo dõi:

- Lag giảm theo tốc độ dự kiến.
- Record được xử lý theo đúng thứ tự yêu cầu.
- Duplicate và lỗi side effect.
- Retry, DLT và commit error.
- Database/API latency khi replay tạo tải lớn.

Nếu group bắt đầu xử lý lại dữ liệu đã hoàn tất trước đó, đối chiếu bằng event ID và idempotency key. Đừng kết luận thành công chỉ vì lag về 0; cần xác minh số record nghiệp vụ và kết quả downstream.

## 8. Các lệnh kiểm tra hữu ích

Các lệnh dưới đây là ví dụ chẩn đoán. Thay bootstrap server, topic, group và thông tin xác thực bằng giá trị của môi trường incident.

**Mô tả topic và trạng thái replica**

~~~bash
kafka-topics.sh --bootstrap-server broker1:9092 --describe --topic orders
~~~

**Xem cấu hình topic**

~~~bash
kafka-configs.sh --bootstrap-server broker1:9092 --entity-type topics --entity-name orders --describe
~~~

**Xem consumer group theo partition**

~~~bash
kafka-consumer-groups.sh --bootstrap-server broker1:9092 --describe --group orders-service
~~~

**Lấy earliest offset**

~~~bash
kafka-get-offsets.sh --bootstrap-server broker1:9092 --topic orders --time -2
~~~

**Lấy latest offset**

~~~bash
kafka-get-offsets.sh --bootstrap-server broker1:9092 --topic orders --time -1
~~~

**Đọc record trong group kiểm tra riêng**

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server broker1:9092 \
  --topic orders \
  --group orders-incident-inspection \
  --from-beginning \
  --property print.key=true \
  --property print.timestamp=true
~~~

Consumer kiểm tra có thể đọc lượng lớn dữ liệu và tạo tải broker. Giới hạn thời gian, partition hoặc số record theo tùy chọn CLI mà phiên bản đang dùng hỗ trợ. Không dùng group ID của production để điều tra bằng console consumer.

## 9. Điều kiện xác nhận đã khôi phục

Chỉ đánh dấu recovery hoàn tất khi có bằng chứng ở cả Kafka và nghiệp vụ:

1. Tập record cần thiết đã được xác định theo event ID, key, thời gian hoặc nguồn dữ liệu gốc.
2. Dữ liệu phục hồi có số lượng, schema, key, timestamp và payload phù hợp với nguồn đối chiếu.
3. Partition và replication khỏe mạnh; không còn offline partition hoặc under-replicated kéo dài ngoài ngưỡng vận hành.
4. Consumer group đọc đúng topic, đúng partition và xử lý hết backlog theo kế hoạch.
5. Duplicate, event đến muộn và thứ tự theo key đã được kiểm tra.
6. Database và dịch vụ phụ trợ phản ánh đúng trạng thái nghiệp vụ sau replay.
7. Producer tiếp tục ghi vào đúng cluster/topic và metric không còn dấu hiệu mất record mới.
8. Owner nghiệp vụ xác nhận dữ liệu đầy đủ hoặc chấp nhận rõ phần không thể phục hồi.

Nếu không thể khôi phục toàn bộ dữ liệu, ghi rõ khoảng thời gian, partition, key hoặc event ID còn thiếu, nguồn đã thử, lý do không thể phục hồi và quyết định nghiệp vụ. Không báo “đã khôi phục” chỉ dựa trên việc topic hoạt động trở lại.

## 10. Theo dõi sau incident

Trong giai đoạn theo dõi, quan sát:

- Producer send success/error, retry, timeout và throughput theo topic/partition.
- Broker leader, ISR, under-replicated partitions, disk capacity, network và request latency.
- Consumer lag, processing latency, commit error, rebalance và DLT rate.
- Tốc độ tăng log, retention window thực tế và dung lượng disk còn lại.
- Số lượng event ở nguồn gốc so với số event đã xử lý ở downstream.

Giữ dashboard theo dõi đủ lâu để bao phủ chu kỳ traffic liên quan. Nếu incident xảy ra vào giờ cao điểm, xác minh lại trong một khoảng tải tương đương.

## 11. Phòng ngừa tái diễn

### Thiết kế lưu giữ theo nhu cầu dữ liệu

- Chọn cleanup.policy theo mục đích: event history cần giữ lịch sử; compacted topic phù hợp với trạng thái mới nhất theo key.
- Đặt retention theo thời gian cần replay, điều tra và đáp ứng DR.
- Dự báo dung lượng theo bytes/sec, replication factor, số broker và headroom disk.
- Cảnh báo trước khi log start offset tiến gần cửa sổ dữ liệu tối thiểu cần giữ.

### Tăng độ bền khi ghi

- Chọn acks=all khi yêu cầu durability cần xác nhận từ ISR.
- Đặt min.insync.replicas phù hợp với replication factor và mức chịu lỗi mong muốn.
- Bật idempotence khi phù hợp với producer và phiên bản Kafka.
- Theo dõi ISR shrink, under-replicated partitions và replica fetch lag.
- Kiểm soát thay đổi liên quan đến unclean leader election theo chính sách vận hành.

### Bảo vệ quy trình consumer

- Chỉ commit sau khi xử lý đạt điều kiện acknowledgment đã định.
- Với side effect ngoài Kafka, cân nhắc transaction/outbox, idempotency hoặc cơ chế deduplication.
- Theo dõi commit error, retry, DLT và event processing lag.
- Kiểm thử restart, rebalance và xử lý lại record.

### Có khả năng phục hồi độc lập

- Xác định nguồn dữ liệu gốc có thể phát lại và thời gian lưu giữ của nguồn đó.
- Thiết lập backup/DR độc lập nếu yêu cầu nghiệp vụ cần phục hồi sau xóa hoặc corruption.
- Thử restore định kỳ, bao gồm kiểm tra dữ liệu, offset, schema và quyền truy cập.
- Viết rõ RPO/RTO và người có quyền quyết định chuyển sang cluster phục hồi.

### Kiểm soát thay đổi và thao tác quản trị

- Ghi audit cho create/delete topic, thay đổi partition, retention, cleanup policy và ACL.
- Yêu cầu review cho automation có thể xóa hoặc tạo lại topic.
- Lưu cấu hình topic mong muốn dưới dạng có version và so sánh với cấu hình thực tế.
- Kiểm thử runbook với topic test, gồm replay, reset offset và restore từ backup.

## 12. Checklist thao tác trong incident

### Khi phát hiện

- [ ] Xác nhận đúng cluster, topic, group và môi trường.
- [ ] Ghi thời điểm cuối cùng dữ liệu được xác nhận đầy đủ.
- [ ] Xác định partition, khoảng thời gian, key hoặc event ID bị ảnh hưởng.
- [ ] Dừng thay đổi quản trị không cần thiết và bảo toàn log/bằng chứng.
- [ ] Ghi topic metadata, topic config, earliest/latest offsets và group offsets.

### Khi điều tra

- [ ] Kiểm tra retention và cleanup policy hiệu lực.
- [ ] Kiểm tra producer send result, acks, retry, transaction và endpoint.
- [ ] Kiểm tra broker log, leader election, ISR và storage.
- [ ] Kiểm tra consumer commit, acknowledgment, filter, schema, DLT và group ID.
- [ ] Xác định record còn trong log hay cần nguồn phục hồi độc lập.

### Khi khôi phục

- [ ] Chọn nguồn dữ liệu có thể chứng minh tính đầy đủ.
- [ ] Xác định replay window theo partition/key/event ID.
- [ ] Dùng topic hoặc group phục hồi riêng khi phù hợp.
- [ ] Xác nhận idempotency, duplicate, ordering và tải downstream.
- [ ] Preview mọi thay đổi consumer offset trước khi execute.
- [ ] Ghi lại người phê duyệt, lệnh và kết quả thực thi.

### Khi đóng incident

- [ ] Đối chiếu dữ liệu Kafka với nguồn nghiệp vụ.
- [ ] Xác nhận consumer và downstream đã xử lý đúng.
- [ ] Xác nhận producer tiếp tục ghi đúng đích.
- [ ] Ghi phần dữ liệu không thể phục hồi và quyết định liên quan.
- [ ] Tạo hành động khắc phục có owner, deadline và tiêu chí hoàn tất.

## 13. Mẫu báo cáo incident

~~~text
Incident ID:
Cluster / Environment:
Topic:
Consumer group:
First observed (UTC):
Last known good (UTC):
Affected partitions:
Affected time window:
Affected event IDs / keys:

Observed symptoms:
Evidence collected:
Root cause:
Data still available in Kafka:
Recovery source:
Recovery method:
Replay window and volume:
Duplicate / ordering controls:
Validation result:
Unrecoverable data:
Business owner decision:

Follow-up actions:
Owner:
Due date:
~~~

Runbook này giúp chuẩn hóa việc điều tra và khôi phục. Mỗi incident vẫn cần căn cứ vào phiên bản Kafka, cấu hình thực tế, bằng chứng broker và yêu cầu nghiệp vụ để quyết định hành động. Khi chưa xác định được record còn tồn tại ở đâu, hãy tiếp tục bảo toàn trạng thái và tìm nguồn dữ liệu độc lập trước khi thay đổi offset hoặc topic.
