# Khôi phục connector và phát hiện khoảng trống dữ liệu nguồn

## Mục tiêu bài học

CDC (Change Data Capture) đọc thay đổi từ transaction log của database rồi chuyển chúng thành record Kafka. Outbox pattern ghi event nghiệp vụ vào database cùng transaction với dữ liệu gốc, sau đó connector phát event sang Kafka. Khi worker, task, database hoặc Kafka gặp sự cố, việc khởi động lại connector chỉ an toàn nếu trạng thái offset và transaction log nguồn vẫn còn hợp lệ. Ngoài khôi phục, hệ thống cần phát hiện được event bị thiếu, bị lặp hoặc bị trễ để không nhầm một connector đang `RUNNING` với một luồng dữ liệu đầy đủ.

Sau bài học, bạn có thể:

- Phân biệt worker restart, task restart, connector restart và khôi phục source offset.
- Giải thích quan hệ giữa source database log, Connect offset topic và Kafka output topic.
- Chẩn đoán connector dừng do worker, task, database log retention, schema hoặc quyền truy cập.
- Khôi phục connector từ offset đã lưu mà không xóa trạng thái một cách tùy tiện.
- Chọn giữa resume, snapshot, backfill hoặc tạo pipeline mới khi source log không còn vị trí cần đọc.
- Thiết kế outbox event ID và aggregate sequence để phát hiện duplicate và gap.
- Theo dõi heartbeat, source position, lag, replication slot/binlog retention và task status.
- Đối soát dữ liệu nguồn với Kafka bằng event ID, sequence, count và checksum.
- Xây dựng runbook recovery, replay và kiểm thử failure scenario.

## 1. Luồng CDC và các loại trạng thái cần khôi phục

Một source connector đọc thay đổi từ database và ghi chúng vào Kafka. Với CDC dựa trên transaction log, luồng tổng quát như sau:

```text
Database transaction
        |
        v
Transaction log (WAL / binlog / redo log / ...)
        |
        v
Source connector task
        |
        +----> Connect source offset
        |          (vị trí đã đọc trong nguồn)
        v
Kafka producer
        |
        v
Kafka topic
        |
        v
Downstream consumer / projection / warehouse
```

Connector không đơn giản đọc lại bảng từ đầu mỗi khi restart. Nó cần biết vị trí đã xử lý trong nguồn để tiếp tục. Với distributed Kafka Connect, source offset thường được lưu trong internal offset topic. Connector cụ thể có thể lưu vị trí như binlog file/position, GTID, PostgreSQL LSN, SCN hoặc một cấu trúc riêng.

### 1.1. Phân biệt ba loại offset

| Trạng thái | Nơi lưu | Ý nghĩa |
|---|---|---|
| Source connector offset | Connect offset storage (distributed mode thường là internal offset topic) | Vị trí connector đã đọc/ghi nhận trong hệ thống nguồn |
| Kafka topic offset | Metadata của từng partition Kafka | Vị trí record đã được append trong topic đích |
| Consumer group offset | Kafka `__consumer_offsets` | Vị trí consumer group đã commit khi đọc topic |

Ba loại offset phục vụ ba nhiệm vụ khác nhau. Reset consumer group offset không làm source connector đọc lại transaction log database. Xóa source connector offset cũng không xóa record đã ghi trong Kafka. Xóa Kafka topic không tự đưa source connector về đầu log nguồn.

### 1.2. Các trạng thái liên quan đến recovery

Khi điều tra, cần xem đồng thời:

- **Database log:** WAL/binlog/redo log còn chứa vị trí mà connector cần đọc không?
- **Source offset:** Connect đang lưu vị trí nguồn nào cho connector?
- **Connector/task state:** task đang `RUNNING`, `FAILED`, `PAUSED` hay chưa được phân công?
- **Kafka output:** record cuối cùng được ghi đến partition nào, offset nào, event ID/sequence nào?
- **Consumer state:** consumer downstream có lag hoặc đã commit đến đâu?
- **Schema/metadata:** connector còn giải mã được schema và transaction metadata không?

Một connector `RUNNING` chỉ cho biết task đang chạy theo trạng thái framework. Điều đó không chứng minh mọi thay đổi nguồn đều đã được capture, topic đích chưa mất dữ liệu hoặc consumer downstream đã xử lý hết.

## 2. Connector, task và worker khác nhau như thế nào khi restart?

### 2.1. Worker restart

Worker là process Kafka Connect. Khi worker dừng, distributed Connect có thể phân phối task sang worker còn hoạt động. Connector config và source offset được lưu trong Kafka internal topics nên worker mới có thể tiếp tục theo trạng thái đã lưu.

Điều kiện để failover hoạt động:

- Các worker còn lại cùng Connect cluster và dùng cùng `group.id`.
- Internal config/offset/status topics còn khả dụng.
- Plugin và dependency của connector có trên worker nhận task.
- Worker mới truy cập được database, Kafka và secret cần thiết.
- Source log vẫn giữ vị trí mà connector cần tiếp tục.

Worker restart thường không đòi hỏi reset source offset. Tuy nhiên, task có thể được khởi chạy lại và phát lại một số record quanh ranh giới offset cuối cùng đã lưu; downstream nên xử lý duplicate an toàn.

### 2.2. Task restart

Task là đơn vị thực thi công việc của connector. Một task có thể fail do lỗi tạm thời, kết nối database, lỗi dữ liệu, schema hoặc bug plugin. Restart task thường giữ connector config và source offset đã lưu.

Nếu lỗi là tạm thời, restart task có thể đủ. Nếu lỗi do source log đã bị purge, credential hết hạn hoặc schema không tương thích, restart lặp lại sẽ không giải quyết nguyên nhân.

### 2.3. Connector restart

Restart connector làm các task của connector được dừng và khởi động lại theo vòng đời Connect. Có thể dùng khi connector cần nạp lại cấu hình hoặc phục hồi sau lỗi ở cấp connector.

Restart không đồng nghĩa reset offset. Nếu source offset còn hợp lệ, connector thường tiếp tục từ vị trí đã lưu. Nếu offset không còn hợp lệ trong source log, connector có thể fail khi khởi động lại.

### 2.4. Pause và resume

Pause tạm dừng connector theo API Connect nhưng giữ cấu hình và offset. Resume cho phép connector chạy lại. Pause có thể hữu ích trước khi thay đổi nguồn/đích hoặc diễn tập maintenance, nhưng không nên dùng như cơ chế backup offset.

### 2.5. Reset source offset

Reset/alter source offset thay đổi vị trí connector sẽ đọc trong nguồn. Đây là thao tác có ảnh hưởng trực tiếp đến dữ liệu:

- Đặt offset cũ hơn có thể phát lại dữ liệu và tạo duplicate.
- Đặt offset mới hơn có thể bỏ qua thay đổi nguồn và tạo gap.
- Xóa offset có thể khiến connector khởi tạo lại hoặc chạy snapshot tùy connector/configuration.

Chỉ reset sau khi đã xác định vị trí nguồn, phạm vi dữ liệu cần phục hồi và cách xử lý duplicate. Không dùng reset offset như thao tác restart thông thường.

## 3. Source offset trong distributed Kafka Connect

### 3.1. Offset topic

Distributed Connect lưu source offsets trong topic được cấu hình bởi `offset.storage.topic`, thường có cleanup policy compact. Offset được lưu theo key/partition source do connector định nghĩa.

Worker sử dụng offset này khi task khởi động lại để tiếp tục đọc từ vị trí đã ghi nhận. Không đọc, chỉnh sửa hoặc xóa record trong internal offset topic bằng consumer/producer ứng dụng thông thường.

### 3.2. Connector identity và offset key

Offset được gắn với danh tính connector và cấu trúc source partition do connector cung cấp. Đổi tên connector, thay source identity, đổi cấu hình định danh hoặc chuyển offset storage có thể làm Connect không tìm thấy offset cũ như mong đợi.

Với Debezium, một số cấu hình định danh như `topic.prefix`, logical server identity, replication slot hoặc server ID có thể ảnh hưởng đến topic, vị trí và cách connector đọc nguồn. Ý nghĩa chính xác phụ thuộc database connector và phiên bản Debezium.

Không đổi connector name, topic prefix, database identity, slot hoặc offset storage trong cùng một lần release nếu chưa hiểu cách connector ánh xạ source partition/offset. Hãy kiểm tra tài liệu connector và thử trên môi trường staging.

### 3.3. Source offset không phải bằng chứng duy nhất rằng record đã đến đích

Offset thường được ghi nhận theo cơ chế source task và Connect framework. Tùy connector, batch, flush interval và thời điểm crash, một số record có thể được phát lại. Đối với connector có bảo đảm khác nhau, hãy đọc tài liệu cụ thể; không giả định mọi source connector đều exactly-once end-to-end.

Thiết kế downstream theo hướng chịu được duplicate bằng event ID hoặc khóa nghiệp vụ ổn định. Nếu cần kiểm chứng đầy đủ, đối chiếu source event với record Kafka thay vì chỉ nhìn offset topic.

## 4. Điều kiện để resume từ transaction log nguồn

### 4.1. Log retention phải còn đủ

Source connector dựa trên transaction log chỉ có thể tiếp tục nếu database còn giữ vị trí log cần đọc. Ví dụ:

- MySQL/MariaDB: binlog file/position hoặc GTID cần còn trong binary log.
- PostgreSQL: WAL cần còn khả dụng cho replication slot/connector.
- SQL Server, Oracle và database khác: cơ chế log/CDC retention tương ứng phải còn dữ liệu cần capture.

Nếu database đã xóa log cũ hơn source offset của connector, task không thể đơn giản resume tại vị trí đã mất. Connector có thể báo lỗi về log position không tồn tại, WAL/slot invalid hoặc binlog purged.

### 4.2. Theo dõi replication slot và WAL trên PostgreSQL

Với PostgreSQL logical decoding, replication slot giữ vị trí WAL cần thiết cho consumer. Nếu slot còn hợp lệ và database giữ WAL, connector có thể tiếp tục từ LSN đã xác nhận. Tuy nhiên, slot inactive lâu có thể làm WAL tích tụ và chiếm dung lượng đĩa.

Kiểm tra slot bằng truy vấn phù hợp với phiên bản PostgreSQL:

```sql
SELECT
    slot_name,
    plugin,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots;
```

Các cột như `wal_status` và `safe_wal_size` phụ thuộc phiên bản PostgreSQL. Nếu phiên bản không có cột đó, bỏ chúng khỏi truy vấn và dùng view/documentation đúng version.

Các điểm cần theo dõi:

- Slot có tồn tại và đúng tên connector cấu hình không?
- Slot có đang active khi connector chạy không?
- `confirmed_flush_lsn` có tiến lên theo thời gian không?
- WAL giữ lại có tăng quá mức và gây áp lực disk không?
- Slot có bị invalidated do giới hạn WAL retention hoặc thao tác quản trị không?

Không tự ý drop/recreate replication slot đang được connector sử dụng. Việc đó có thể làm mất vị trí CDC và buộc phải snapshot/backfill lại.

### 4.3. Theo dõi MySQL binlog

Với MySQL, connector cần đọc binlog từ file/position hoặc GTID. Nếu binlog đã bị purge trước khi connector tiếp tục, vị trí nguồn không còn hợp lệ.

Kiểm tra trạng thái log bằng câu lệnh phù hợp với version:

```sql
SHOW BINARY LOGS;
SHOW MASTER STATUS;
```

Ở các phiên bản MySQL mới, tên lệnh/metadata có thể thay đổi, ví dụ dùng `SHOW BINARY LOG STATUS`; hãy dùng cú pháp của phiên bản đang chạy.

Kiểm tra:

- Binlog hiện tại và danh sách file còn giữ.
- GTID set của database và vị trí connector đã lưu.
- Binary log expiration/purge policy.
- Dung lượng disk và tốc độ phát sinh log.
- Connector có quyền đọc binlog và metadata cần thiết không.

Đặt binlog retention dài hơn thời gian sự cố tối đa dự kiến cộng thời gian phát hiện, xử lý và phục hồi. Retention quá ngắn có thể khiến connector không thể bắt kịp sau một outage dài.

### 4.4. Tính retention headroom

Ví dụ nếu hệ thống tạo 20 GB binlog/WAL mỗi ngày và muốn chịu được outage 3 ngày, lượng log tối thiểu cần giữ đã vượt 60 GB, chưa tính burst, transaction lớn và khoảng dự phòng. Hãy dùng tốc độ log thực tế ở tải đỉnh, không chỉ trung bình ngày.

Một ước lượng vận hành:

```text
required_log_capacity
  >= peak_log_rate_per_hour
     * (maximum_outage_hours + detection_and_recovery_hours)
     * safety_factor
```

`safety_factor` cần được chọn theo biến động workload, dung lượng disk và SLA. Đây là ước lượng lập kế hoạch, không thay thế kiểm tra retention policy thực tế của database.

## 5. Chẩn đoán connector sau sự cố

Trước khi restart hoặc reset, thu thập trạng thái để biết connector đang dừng ở lớp nào.

### 5.1. Kiểm tra connector và task status

```bash
curl http://connect-1.internal:8083/connectors
curl http://connect-1.internal:8083/connectors/orders-cdc/status
```

Xem:

- Connector state.
- Task ID, state và worker đang chạy.
- Error trace nếu task ở `FAILED`.
- Worker nào đang nhận task.
- Thời điểm task restart gần nhất.

Không chỉ kiểm tra connector state. Connector có thể được đăng ký nhưng task fail; cũng có thể connector ở trạng thái pause theo chủ đích.

### 5.2. Đọc connector config và source offset

```bash
curl http://connect-1.internal:8083/connectors/orders-cdc/config
curl http://connect-1.internal:8083/connectors/orders-cdc/offsets
```

Endpoint đọc source offsets có trong các phiên bản Kafka Connect hỗ trợ offset management REST API. Kiểm tra REST API của version thực tế. Offset response thường mang cấu trúc riêng do connector định nghĩa; không tự diễn giải một trường thành LSN/binlog position nếu chưa biết format.

Lưu bản config đã che secret, source offset response và status trước khi thực hiện thao tác thay đổi. Đây là dữ liệu cần để so sánh sau recovery.

### 5.3. Kiểm tra worker log

Tìm các lỗi:

- Không kết nối được database hoặc Kafka.
- Authentication/authorization failure.
- Source log position không tồn tại hoặc đã bị purge.
- Replication slot không tồn tại, inactive hoặc invalid.
- Binlog/GTID không hợp lệ.
- Schema change hoặc converter/deserializer failure.
- Plugin class/dependency không nạp được.
- Task bị timeout, rebalance hoặc worker bị OOM.
- Offset commit/flush failure.

Ghi nhận timestamp và connector/task ID để đối chiếu với database log và Kafka output.

### 5.4. Xác định connector có thực sự tiến triển không

So sánh theo thời gian:

- Source position/LSN/GTID/binlog offset có tiến lên không?
- Heartbeat hoặc watermark record có được phát không?
- Kafka output topic có record mới không?
- Task record poll/write rate có lớn hơn zero khi nguồn có thay đổi không?
- Consumer lag downstream có giảm hoặc tăng bất thường không?

Nếu task `RUNNING` nhưng source position đứng yên, cần phân biệt nguồn không có thay đổi, connector bị chặn, replication slot không tiến triển hay metric không phản ánh đúng connector.

## 6. Quy trình resume an toàn

Khi worker/task lỗi tạm thời và source log vẫn còn, thường có thể khôi phục bằng cách sửa nguyên nhân rồi restart task hoặc connector.

### 6.1. Trước khi restart

1. Ghi lại connector config, status, source offsets và thời điểm lỗi.
2. Kiểm tra database log retention còn chứa vị trí offset.
3. Kiểm tra Kafka internal topics và worker cluster khỏe.
4. Kiểm tra plugin, credential, network và ACL.
5. Xác định nguyên nhân đã được sửa, ví dụ database đã phục hồi hoặc secret đã rotate.
6. Xác nhận downstream có khả năng xử lý duplicate.

### 6.2. Restart connector

```bash
curl -X POST http://connect-1.internal:8083/connectors/orders-cdc/restart
```

Endpoint restart có thể có tùy chọn xử lý task riêng tùy phiên bản Kafka Connect. Với task `FAILED`, một số version hỗ trợ restart task cụ thể qua REST API. Kiểm tra API version và response trước khi tự động hóa.

Sau restart:

- Đọc lại connector/task status.
- Xác minh task chạy trên worker hợp lệ.
- Quan sát source offset có tiếp tục tiến lên.
- Kiểm tra Kafka output có record mới.
- Theo dõi duplicate và gap bằng event ID/sequence.
- Kiểm tra lag có giảm về mức bình thường.

Restart chỉ là thao tác lifecycle. Nếu nguyên nhân gốc chưa được xử lý, task có thể fail lại ngay lập tức.

### 6.3. Resume connector đã pause

```bash
curl -X PUT http://connect-1.internal:8083/connectors/orders-cdc/resume
```

Resume không reset offset. Dùng khi connector được pause có chủ đích và điều kiện nguồn/đích đã sẵn sàng.

## 7. Khi source log đã bị purge hoặc offset không còn hợp lệ

Đây là tình huống khác hoàn toàn với worker crash. Nếu transaction log nguồn không còn vị trí connector cần đọc, restart không thể tái tạo các log record đã bị xóa.

### 7.1. Không xóa offset để thử vận may

Xóa source offset có thể khiến connector khởi động theo default/snapshot behavior. Tùy connector, kết quả có thể là:

- Snapshot lại toàn bộ bảng được capture.
- Bắt đầu ở vị trí log hiện tại và bỏ qua khoảng thay đổi cũ.
- Dừng với lỗi vì connector không hỗ trợ khởi tạo theo cách đó.
- Tạo dữ liệu trùng với những record đã có trong Kafka.

Không xóa offset topic hoặc record internal bằng tay. Trước khi dùng offset reset API, cần biết rõ connector hỗ trợ thao tác nào và hành vi khi offset không tồn tại.

### 7.2. Lựa chọn phục hồi

| Tình huống | Hướng xử lý thường dùng | Rủi ro cần kiểm soát |
|---|---|---|
| Source log còn đủ, offset hợp lệ | Resume từ offset đã lưu | Duplicate nhỏ quanh ranh giới restart |
| Offset bị thiếu nhưng source log còn đủ | Khôi phục offset từ backup hoặc dùng API connector hỗ trợ | Chọn sai vị trí có thể tạo gap/duplicate |
| Source log đã purge, bảng hiện tại còn đầy đủ | Snapshot/rebootstrap hoặc backfill có kiểm soát | Snapshot không tái tạo mọi lịch sử event đã mất |
| Cần lịch sử đầy đủ nhưng log nguồn mất | Restore backup/PITR hoặc nguồn audit khác, sau đó backfill | Chi phí và độ phức tạp cao; có thể không khôi phục được mọi event |
| Kafka output bị xóa/retention hết nhưng source còn dữ liệu | Backfill từ nguồn hoặc replay bằng pipeline riêng | Phải tránh trộn dữ liệu backfill với luồng live không có watermark |
| Schema/plugin mới không đọc được state cũ | Rollback plugin hoặc migration theo hướng dẫn connector | Offset/schema history có thể không tương thích |

### 7.3. Snapshot không đồng nghĩa phục hồi đầy đủ lịch sử event

Snapshot thường đọc trạng thái hiện tại của các row được capture. Nó có thể khôi phục trạng thái bảng hiện tại nhưng không tái tạo tất cả thay đổi trung gian đã xảy ra rồi bị ghi đè hoặc xóa.

Ví dụ một đơn hàng đã chuyển trạng thái `NEW -> PAID -> SHIPPED`. Nếu snapshot chỉ đọc trạng thái hiện tại `SHIPPED`, downstream không thể suy ra chính xác hai event `PAID` và `SHIPPED` đã xảy ra vào thời điểm nào, trừ khi database còn audit/outbox/history table lưu chúng.

Nếu nghiệp vụ cần lịch sử event đầy đủ, phải có outbox/audit log hoặc backup/log nguồn đủ dài. Snapshot bảng hiện tại không thay thế event history.

### 7.4. Snapshot rồi tiếp tục streaming

Với connector hỗ trợ snapshot, quy trình thường cần xác định một ranh giới nhất quán giữa snapshot và transaction log streaming. Connector phải phối hợp snapshot với source position để tránh bỏ qua thay đổi phát sinh trong lúc snapshot.

Chi tiết phụ thuộc connector và database. Không tự triển khai “đọc bảng rồi mới bắt đầu binlog/WAL” nếu không có cơ chế consistent snapshot, vì thay đổi phát sinh giữa hai bước có thể bị mất hoặc xuất hiện hai lần.

Debezium cung cấp các chế độ snapshot và cơ chế incremental snapshot khác nhau theo connector/version. Kiểm tra tài liệu đúng phiên bản trước khi đổi `snapshot.mode` hoặc kích hoạt signal.

## 8. Offset management REST API và thao tác có kiểm soát

Một số phiên bản Kafka Connect cung cấp REST API để đọc, thay đổi hoặc xóa source connector offsets. API và điều kiện trạng thái connector thay đổi theo version; chỉ dùng sau khi kiểm tra documentation của runtime.

Các endpoint thường gặp ở version có hỗ trợ:

```text
GET    /connectors/{name}/offsets   Đọc source offsets
PATCH  /connectors/{name}/offsets   Thay đổi source offsets
DELETE /connectors/{name}/offsets   Xóa source offsets
```

Không phải mọi phiên bản Connect đều hỗ trợ đầy đủ các endpoint này. Một số thao tác yêu cầu connector ở trạng thái `STOPPED`; endpoint và request body phải tuân theo schema của API version đang dùng.

### 8.1. Trình tự trước khi alter/delete offset

1. Đọc và lưu offset hiện tại.
2. Pause/stop connector theo trạng thái mà API yêu cầu.
3. Xác định source partition và offset chính xác cần dùng.
4. Đánh giá phạm vi record sẽ bị phát lại hoặc bỏ qua.
5. Kiểm tra downstream idempotency và khả năng tiếp nhận lượng replay.
6. Thực hiện `PATCH` hoặc `DELETE` theo API version.
7. Khởi động connector và kiểm tra source position/output.
8. Đối soát event ID/sequence để xác nhận không còn gap.

### 8.2. Không chỉnh sửa internal offset topic bằng tay

Offset topic là internal state do Connect quản lý. Dùng REST API được hỗ trợ hoặc quy trình migration chính thức của connector. Sửa record trực tiếp có thể phá cấu trúc source partition/offset, compaction key hoặc trạng thái recovery.

### 8.3. Khi cần lùi offset

Lùi offset để replay chỉ an toàn nếu:

- Source log vẫn còn từ vị trí đích.
- Đã biết phạm vi thời gian/event sẽ phát lại.
- Downstream có deduplication/idempotency.
- Có cách xác định điểm dừng replay và chuyển về live stream.
- Có metric để phân biệt replay với event mới.

Nếu cần phát lại vào cùng topic, record mới có Kafka offset mới dù phản ánh cùng event nghiệp vụ. Event ID phải giữ nguyên để downstream nhận diện duplicate.

## 9. Thiết kế outbox để có thể đối soát và phục hồi

Outbox pattern lưu event trong database cùng transaction với business update. Connector CDC đọc các row outbox và phát chúng vào Kafka.

### 9.1. Vì sao outbox giúp recovery tốt hơn?

Transaction log có thể chỉ được giữ trong một khoảng thời gian. Một bảng outbox có retention dài hơn hoặc được archive có thể cung cấp nguồn audit để đối chiếu event nghiệp vụ, đặc biệt khi connector bị gián đoạn.

Outbox không tự làm connector không bao giờ mất dữ liệu. Nó tạo ra bản ghi event bền vững trong database, giúp connector đọc lại hoặc một quy trình backfill có thể khôi phục những event còn lưu.

### 9.2. Schema outbox gợi ý

```sql
CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(150) NOT NULL,
    aggregate_sequence BIGINT NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (aggregate_type, aggregate_id, aggregate_sequence)
);

CREATE INDEX idx_outbox_created_at
    ON outbox_events (created_at);
```

Đây là schema tham khảo cho PostgreSQL. Kiểu UUID/JSONB/TIMESTAMPTZ cần điều chỉnh theo database. Unique constraint theo aggregate sequence giúp phát hiện producer nghiệp vụ ghi trùng sequence cho cùng entity.

### 9.3. Business update và outbox insert cùng transaction

```sql
BEGIN;

UPDATE orders
SET status = 'PAID', version = version + 1
WHERE order_id = 'ORD-101';

INSERT INTO outbox_events (
    event_id,
    aggregate_type,
    aggregate_id,
    aggregate_sequence,
    event_type,
    payload,
    occurred_at
)
VALUES (
    '8c3e7b8e-5d6f-4b4c-8a7e-0c4e5a1b2c3d',
    'Order',
    'ORD-101',
    7,
    'OrderPaid',
    '{"orderId":"ORD-101","status":"PAID"}',
    CURRENT_TIMESTAMP
);

COMMIT;
```

Nếu transaction commit, cả business state và outbox event cùng tồn tại. Nếu rollback, cả hai đều không được ghi nhận. Điều này tránh dual-write trực tiếp giữa database và Kafka trong request path.

### 9.4. Debezium Outbox Event Router

Debezium có Outbox Event Router SMT để ánh xạ row outbox thành Kafka record. Cấu hình chính xác phụ thuộc Debezium version và connector database. Một ví dụ khái quát:

```properties
transforms=outbox
transforms.outbox.type=io.debezium.transforms.outbox.EventRouter
transforms.outbox.table.field.event.id=event_id
transforms.outbox.table.field.event.key=aggregate_id
transforms.outbox.table.field.event.type=event_type
transforms.outbox.table.field.event.payload=payload
```

Tên field và các tùy chọn routing cần khớp schema outbox cùng phiên bản Event Router. Nếu SMT route topic theo `aggregate_type` hoặc event type, hãy ghi rõ quy tắc topic và key để giữ ordering theo aggregate.

### 9.5. Không xóa outbox quá sớm

Nếu xóa row ngay sau khi connector phát event, việc backfill sau outage dài có thể không còn nguồn dữ liệu. Thiết kế cleanup cần tính đến:

- Source connector đã đọc và commit offset qua row chưa.
- Khoảng outage tối đa cần chịu đựng.
- Thời gian điều tra và phục hồi.
- Retention/replay window của downstream.
- Yêu cầu audit và pháp lý.
- Archive/backup có thể truy xuất event cũ hay không.

Có thể giữ outbox trong database một khoảng thời gian rồi archive/partition drop theo lịch. Việc cleanup nên có watermark/checkpoint đáng tin cậy, không chỉ dựa vào tuổi row.

## 10. Phát hiện khoảng trống bằng event ID và sequence

### 10.1. Event ID phát hiện duplicate, sequence phát hiện gap

Event ID duy nhất giúp nhận biết cùng một event logic đã xuất hiện nhiều lần. Sequence tăng dần theo aggregate giúp phát hiện một event trong chuỗi bị thiếu hoặc đến sai thứ tự.

Ví dụ event cho một đơn hàng:

```json
{
  "eventId": "evt-ord-101-7",
  "aggregateType": "Order",
  "aggregateId": "ORD-101",
  "aggregateSequence": 7,
  "eventType": "OrderPaid",
  "occurredAt": "2026-11-20T09:30:00Z",
  "data": {
    "status": "PAID"
  }
}
```

Nếu consumer đã xử lý sequence 5 rồi nhận 7, sequence 6 có thể bị thiếu hoặc đang đến trễ. Không nên lập tức kết luận mất dữ liệu; cần kiểm tra ordering, partition, retry và event filter trước.

### 10.2. Sequence phải có phạm vi rõ ràng

Sequence toàn cục cho mọi row trong database thường khó duy trì và không cần thiết. Một mô hình phổ biến là sequence theo aggregate/entity:

- `aggregate_id` xác định entity.
- `aggregate_sequence` tăng một cách nguyên tử trong transaction cập nhật entity.
- Outbox row được ghi cùng transaction với sequence mới.
- Kafka key dùng `aggregate_id` để event của cùng entity đi cùng partition theo partitioner ổn định.

Sequence theo aggregate giúp kiểm tra thứ tự event của một đơn hàng hoặc tài khoản. Nó không thể chứng minh thứ tự toàn cục giữa hai aggregate khác nhau.

### 10.3. Không phải mọi khoảng nhảy đều là mất event

Sequence có thể nhảy do:

- Connector chỉ capture một số bảng hoặc loại operation.
- SMT filter loại bỏ event theo điều kiện.
- Một số sequence được dùng cho update nội bộ không tạo event.
- Event bị route sang topic khác.
- Consumer chỉ subscribe một tập topic/partition.
- Event đến trễ hoặc retry sau event mới hơn.

Để sequence gap có ý nghĩa, contract phải quy định mọi sequence trong phạm vi đó đều tạo event mà consumer này phải nhận. Nếu có filtering, cần sequence riêng cho stream đã filter hoặc một cách xác định các sequence được phép bỏ qua.

### 10.4. Lưu trạng thái sequence phía consumer

Ví dụ bảng lưu tiến độ theo aggregate:

```sql
CREATE TABLE aggregate_projection_checkpoint (
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(150) NOT NULL,
    last_sequence BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (aggregate_type, aggregate_id)
);

CREATE TABLE consumed_event_ids (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(150) NOT NULL,
    aggregate_sequence BIGINT NOT NULL,
    consumed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (aggregate_type, aggregate_id, aggregate_sequence)
);
```

Trong một database transaction, consumer kiểm tra event ID/sequence, áp dụng projection và cập nhật checkpoint. Unique constraint giúp ngăn hai worker cùng áp dụng một event do race condition hoặc redelivery.

Nếu projection được khởi tạo từ snapshot, checkpoint phải được seed bằng sequence/watermark tương ứng với snapshot đó. Nếu không, event đầu tiên sau snapshot có sequence lớn hơn 1 có thể bị hiểu nhầm là gap dù các event trước đó đã được phản ánh trong trạng thái snapshot.

## 11. Ví dụ logic consumer phát hiện duplicate và gap

Pseudocode Java minh họa quy tắc:

```java
void handle(OutboxEvent event) {
    Gap detectedGap = database.inTransaction(tx -> {
        long last = tx.loadLastSequence(
            event.aggregateType(), event.aggregateId()
        );

        if (tx.eventAlreadyConsumed(event.eventId())) {
            return null; // Duplicate do replay/redelivery.
        }

        if (event.aggregateSequence() <= last) {
            tx.recordLateOrDuplicate(event);
            return null;
        }

        if (event.aggregateSequence() > last + 1) {
            return new Gap(
                event.aggregateType(), event.aggregateId(),
                last + 1, event.aggregateSequence() - 1
            );
        }

        tx.applyProjection(event);
        tx.insertConsumedEvent(event);
        tx.updateLastSequence(event, event.aggregateSequence());
        return null;
    });

    if (detectedGap != null) {
        // Ghi audit gap bằng transaction riêng để không bị rollback cùng handler.
        gapRepository.recordInIndependentTransaction(detectedGap);
        throw new SequenceGapException(event.aggregateId());
    }
}
```

Đây là pseudocode, không phải API database cụ thể. `Gap` và `gapRepository` là kiểu/adapter minh họa. Gap được ghi bằng transaction độc lập để thông tin điều tra không bị rollback khi handler ném exception. Trong triển khai thật, cần khóa row checkpoint hoặc dùng optimistic concurrency/version để tránh hai thread xử lý cùng aggregate đồng thời. Nếu sequence gap xuất hiện, có thể retry/backoff trong thời gian chờ event thiếu; nếu quá thời hạn, đưa vào hàng chờ điều tra/backfill thay vì bỏ qua im lặng.

Không commit Kafka offset qua record có gap nếu chính sách nghiệp vụ yêu cầu xử lý đúng thứ tự. Ngược lại, nếu handler ném exception mãi mà không có retry/DLT policy, partition có thể bị kẹt. Hãy xác định rõ cách giữ event sau và cách replay event thiếu.

## 12. Heartbeat, watermark và source position

### 12.1. Heartbeat

Heartbeat record cho biết connector còn phát tín hiệu tiến triển ngay cả khi bảng nghiệp vụ ít thay đổi. Với Debezium, heartbeat có thể được cấu hình để phát record định kỳ và mang metadata nguồn tùy connector/version.

Heartbeat giúp phân biệt:

- Nguồn thực sự không có thay đổi nghiệp vụ.
- Connector đang chạy nhưng không đọc/ghi tiến triển.
- Đường Kafka output hoặc task bị gián đoạn.

Heartbeat không chứng minh mọi row đã được capture. Nó chỉ là tín hiệu liveness/progress theo semantics connector.

### 12.2. Source position và transaction metadata

Nhiều CDC connector cung cấp metadata về vị trí nguồn như LSN, binlog file/position, GTID, SCN, transaction ID hoặc timestamp. Lưu metadata này trong record hoặc headers để hỗ trợ:

- Truy vết record về transaction nguồn.
- So sánh vị trí connector đã đọc với vị trí database hiện tại.
- Phát hiện offset đứng yên.
- Điều tra thứ tự record và transaction boundary.

Không so sánh số LSN/position giữa hai database hoặc hai connector identity khác nhau như cùng một thước đo. Source position là định dạng riêng của database/connector.

### 12.3. Lag khác gap

**Lag** là độ trễ giữa thay đổi đã xảy ra ở nguồn và vị trí connector/consumer đã xử lý. **Gap** là một event hoặc sequence được kỳ vọng nhưng không thấy trong luồng.

Một connector có lag lớn nhưng không mất event vẫn có thể phục hồi khi bắt kịp. Ngược lại, connector có lag bằng zero nhưng đã bỏ qua một khoảng source log do offset sai thì vẫn có gap.

Đừng dùng một metric lag duy nhất để tuyên bố dữ liệu đầy đủ.

## 13. Đối soát nguồn với Kafka

### 13.1. Đối soát theo event ID

Với outbox, event ID là khóa đối chiếu tốt nhất giữa database và Kafka. Một audit job có thể lấy tập event ID trong outbox theo khoảng thời gian và so sánh với event ID đã xuất hiện trong topic/warehouse.

Các chỉ số hữu ích:

- Tổng số outbox row theo time window.
- Số event ID duy nhất đã xuất hiện trong Kafka.
- Số event ID thiếu ở Kafka.
- Số event ID trùng trong Kafka.
- Số event đã đến Kafka nhưng chưa được downstream xử lý.
- Số event đang nằm trong trạng thái pending/backfill.

Nếu topic có compaction hoặc retention ngắn, không thể dùng việc scan topic hiện tại để chứng minh lịch sử chưa từng có event bị thiếu. Cần audit store/warehouse hoặc consumer checkpoint độc lập.

### 13.2. Đối soát theo sequence

Với mỗi aggregate, so sánh:

```text
Database/outbox:  1, 2, 3, 4, 5, 6, 7
Kafka observed:   1, 2, 3,    5, 6, 7
                              ^
                         thiếu sequence 4
```

Nếu sequence 4 xuất hiện ở partition khác hoặc topic khác theo routing rule, đây không phải gap trong toàn bộ hệ thống. Audit cần biết routing contract và consumer scope.

### 13.3. Đối soát bằng count/checksum

Khi không có event ID/sequence, có thể so sánh count, aggregate sum hoặc checksum theo partition/time window. Cách này giúp phát hiện sai lệch tổng thể nhưng không chỉ ra chính xác event nào bị thiếu.

Ví dụ:

- Count row theo ngày và loại event.
- Tổng số tiền theo currency và ngày.
- Min/max timestamp.
- Checksum theo bucket của primary key.
- Số row insert/update/delete theo operation.

Count có thể lệch hợp lệ do filter, tombstone, snapshot, retention hoặc thời điểm chụp dữ liệu khác nhau. Cần đồng bộ snapshot/watermark và quy tắc transform trước khi kết luận.

### 13.4. Watermark cho cửa sổ đối soát

Đặt watermark cho biết mọi event trước một mốc nguồn đã được connector xử lý. Watermark có thể dựa trên source position, transaction metadata, heartbeat hoặc sequence đã xác nhận.

Chỉ đóng cửa sổ đối soát khi:

- Connector source position đã vượt watermark.
- Kafka output đã có các record cần thiết.
- Consumer/audit pipeline đã xử lý đến mốc tương ứng.
- Độ trễ tối đa và late arrival window đã qua.

Không dùng `created_at` đơn thuần làm watermark nếu transaction có thể commit trễ hoặc timestamp giữa các node không đồng bộ.

## 14. Xử lý duplicate và thứ tự khi recovery

### 14.1. Duplicate quanh ranh giới offset

Sau crash, connector có thể phát lại record cuối cùng chưa được xác nhận offset. Downstream cần xử lý duplicate:

- Dùng event ID ổn định.
- Dùng upsert theo khóa nghiệp vụ khi semantics cho phép.
- Dùng inbox table có unique constraint.
- Không tạo event ID mới khi replay cùng một event logic.

### 14.2. Ordering

Kafka chỉ bảo đảm thứ tự trong một partition. Nếu event cùng aggregate dùng key ổn định, chúng có thể cùng partition và giữ thứ tự append của partition. Nhưng:

- Replay/backfill vào topic có thể tạo record mới ở offset mới.
- Hai producer/connector ghi song song có thể thay đổi thứ tự tương đối.
- Dual-publish sang hai topic không tạo global ordering.
- Thay key/partition count có thể làm entity chuyển partition.

Nếu cần bảo toàn thứ tự nghiệp vụ, dùng aggregate sequence và consumer checkpoint thay vì chỉ dựa vào timestamp.

### 14.3. Backfill song song với live CDC

Backfill từ database hiện tại trong khi live CDC vẫn chạy có thể làm record mới và cũ xen kẽ. Cần một ranh giới watermark rõ ràng:

1. Xác định source snapshot/LSN hoặc timestamp nhất quán.
2. Chạy backfill đến mốc đó.
3. Phát live CDC từ vị trí sau mốc theo cơ chế connector hỗ trợ.
4. Hoặc ghi backfill vào topic riêng rồi merge theo event ID/sequence.
5. Đối soát không thiếu/duplicate trước khi cutover.

Không chỉ dùng timestamp của row nếu database không bảo đảm snapshot nhất quán theo thời điểm đó.

## 15. Quy trình recovery theo tình huống

### 15.1. Worker bị crash, source log còn đủ

1. Khôi phục worker hoặc để worker khác nhận task.
2. Xác nhận internal topics và plugin sẵn sàng.
3. Kiểm tra connector/task status.
4. Nếu task không tự chạy lại, restart task/connector theo REST API version.
5. Xác minh source offset tiếp tục tiến lên.
6. Theo dõi duplicate và downstream lag.

### 15.2. Task fail do database/network

1. Kiểm tra database health, connection limit, DNS, TLS và credential.
2. Sửa nguyên nhân kết nối.
3. Xác minh source log retention còn đủ.
4. Restart task hoặc connector.
5. Kiểm tra source position, heartbeat và output topic.

### 15.3. Replication slot hoặc binlog position bị mất

1. Dừng restart loop để tránh log nhiễu và tải không cần thiết.
2. Ghi lại source offset cuối cùng và error trace.
3. Kiểm tra database có backup/PITR/audit/outbox đủ để backfill không.
4. Chọn snapshot/rebootstrap hoặc phục hồi từ nguồn audit.
5. Dùng connector identity/topic mới nếu cần cô lập dữ liệu rebootstrap.
6. Xác định watermark để ghép backfill với live stream.
7. Đối soát event ID/sequence trước cutover.

### 15.4. Kafka output topic bị xóa hoặc retention làm mất dữ liệu

1. Xác định source log/outbox còn đủ dữ liệu cần phát lại không.
2. Xác định consumer group và downstream đã xử lý đến đâu.
3. Chọn backfill topic riêng hoặc replay vào topic hiện tại theo quy trình rõ ràng.
4. Giữ event ID gốc và đánh dấu replay metadata nếu cần.
5. Chặn hoặc phối hợp live stream để không trộn dữ liệu sai thứ tự.
6. Đối soát output và consumer state.

### 15.5. Connector chạy nhưng audit phát hiện gap

1. Xác định sequence/event ID thiếu và phạm vi aggregate/time window.
2. Kiểm tra SMT filter, table include/exclude, routing và topic subscription.
3. Kiểm tra source log retention và offset có nhảy qua vùng nghi vấn không.
4. Kiểm tra task error, DLT, converter và schema failure.
5. Tìm event trong outbox/audit/backup hoặc nguồn khác.
6. Backfill đúng event thiếu, giữ event ID và sequence gốc.
7. Chạy lại đối soát và xác nhận checkpoint downstream.

## 16. Monitoring và cảnh báo

Theo dõi các nhóm tín hiệu sau:

| Nhóm | Metric/tín hiệu | Điều cần phát hiện |
|---|---|---|
| Connect runtime | Worker membership, connector/task state, restart count | Worker/task fail hoặc rebalance lặp |
| Source progress | Last source position, offset commit time, heartbeat age | Connector không tiến triển |
| Database retention | WAL retained bytes, slot lag, binlog age/available files | Source log sắp bị purge hoặc disk đầy |
| Kafka output | Record write rate, partition end offset, error rate | Không có output dù nguồn có thay đổi |
| Data quality | Duplicate event ID, sequence gap, invalid payload | Event lặp, thiếu hoặc sai contract |
| Downstream | Consumer lag, processing rate, checkpoint | Event đã vào Kafka nhưng chưa xử lý |
| Outbox | Pending row count, oldest unpublished age, cleanup watermark | Event tồn đọng hoặc bị cleanup quá sớm |

### 16.1. Alert gợi ý

- Source offset không tiến triển trong khi database có thay đổi.
- Heartbeat quá hạn theo SLA.
- WAL/binlog retention headroom thấp hơn thời gian outage mục tiêu.
- Replication slot inactive hoặc WAL retention tăng bất thường.
- Connector/task `FAILED` hoặc restart liên tục.
- Sink/source error rate tăng.
- Sequence gap tồn tại quá late-arrival window.
- Duplicate event ID vượt ngưỡng.
- Outbox oldest row age tăng liên tục.
- Kafka output rate bằng zero trong khi source change rate lớn hơn zero.

Alert phải tính đến giờ ít giao dịch và filter hợp lệ. Ví dụ không có record nghiệp vụ trong vài phút không nhất thiết là lỗi nếu nguồn thực sự idle; heartbeat giúp phân biệt trường hợp đó.

## 17. Kiểm thử recovery và gap detection

Một pipeline CDC cần được diễn tập trước khi production incident xảy ra.

| Kịch bản kiểm thử | Kết quả cần xác minh |
|---|---|
| Kill worker khi connector đang capture | Task được phân phối lại và tiếp tục từ source offset đã lưu |
| Kill task giữa batch | Có thể redeliver; downstream không tạo business effect trùng |
| Mất kết nối database trong thời gian ngắn | Connector retry/recover, source position không bị nhảy |
| Source log gần hết retention | Alert xuất hiện trước khi offset trở nên không hợp lệ |
| Purge source log trong môi trường test | Connector báo lỗi rõ; runbook chọn snapshot/backfill đúng |
| Restart connector sau khi pause | Tiếp tục đúng source position, không reset ngoài ý muốn |
| Replay một event hai lần | Event ID/inbox phát hiện duplicate |
| Bỏ một sequence trong fixture | Gap detector phát hiện đúng aggregate và sequence |
| Event đến trễ sau sequence mới hơn | Late-arrival policy xử lý được, không đánh dấu mất vĩnh viễn quá sớm |
| Thay đổi schema nguồn | Connector xử lý theo policy; không âm thầm bỏ record |
| Kafka output topic bị retention/xóa trong test | Quy trình backfill tạo lại dữ liệu và đối soát được |

Test nên xác minh cả database, source offset, Kafka output và downstream projection. Chỉ kiểm tra REST status là chưa đủ.

## 18. Các lỗi và anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách làm phù hợp |
|---|---|---|
| Reset consumer group offset để sửa source connector | Không thay đổi source offset của Connect | Kiểm tra source offset riêng của connector |
| Xóa internal offset topic | Mất tiến độ của nhiều connector | Dùng REST offset API hoặc recovery procedure được hỗ trợ |
| Restart liên tục khi source log đã purge | Task fail lặp lại, không khôi phục được dữ liệu | Dừng retry và chọn snapshot/backfill |
| Drop replication slot để giải phóng WAL | Mất vị trí CDC | Đánh giá slot lag và retention trước; chỉ drop trong migration có kế hoạch |
| Rút ngắn binlog/WAL retention dưới outage SLA | Connector không thể resume sau outage dài | Tính retention headroom theo peak log rate |
| Nghĩ snapshot tái tạo toàn bộ event history | Mất các chuyển trạng thái trung gian | Dùng outbox/audit log hoặc backup log để phục hồi lịch sử |
| Chỉ nhìn connector `RUNNING` | Có thể vẫn có gap hoặc output không tiến triển | Đối chiếu source position, heartbeat và event sequence |
| Dùng timestamp làm bằng chứng ordering | Clock skew và commit delay làm sai thứ tự | Dùng aggregate sequence/source transaction metadata |
| Dùng sequence toàn cục trong stream đã filter | Báo gap giả | Định nghĩa sequence scope phù hợp với stream |
| Cleanup outbox ngay sau khi publish | Mất nguồn backfill khi connector outage | Giữ/archive theo replay và audit window |
| Backfill song song với live stream không watermark | Event cũ/mới xen kẽ, duplicate hoặc gap | Dùng consistent snapshot và cutover watermark |
| Tạo event ID mới khi replay | Downstream không nhận ra duplicate | Giữ event ID gốc |
| Cho rằng Kafka transaction bao trùm database | DB và Kafka có thể lệch trạng thái | Inbox/outbox và idempotency |

## 19. Runbook recovery mẫu

Khi nhận cảnh báo CDC connector bị dừng hoặc nghi ngờ mất event, thực hiện theo trình tự:

1. **Khoanh vùng:** xác định connector, task, worker, database, topic và thời điểm bắt đầu sự cố.
2. **Bảo toàn bằng chứng:** lưu config đã che secret, task status, source offset, worker log và metric.
3. **Xác định loại lỗi:** worker/task/network, authentication, source log purged, schema/plugin hay output topic.
4. **Kiểm tra nguồn:** xác nhận WAL/binlog/slot/LSN/GTID còn chứa vị trí connector cần đọc.
5. **Kiểm tra đích:** xác nhận Kafka topic, partition, replication, ACL và retention.
6. **Chọn hành động:** restart/resume nếu offset hợp lệ; snapshot/backfill nếu source log mất; offset alter chỉ khi đã tính được gap/duplicate.
7. **Thực hiện có kiểm soát:** dừng task khi API yêu cầu, không xóa internal topic, ghi lại mọi offset trước/sau.
8. **Xác minh tiến triển:** source position, heartbeat, Kafka output và task status phải tiếp tục.
9. **Đối soát:** event ID, aggregate sequence, count/checksum và downstream checkpoint.
10. **Đóng sự cố:** cập nhật retention, alert, runbook và cleanup policy để tránh lặp lại.

## 20. Checklist thiết kế và vận hành

- Đã xác định source offset khác Kafka topic offset và consumer group offset.
- Distributed Connect internal topics được bảo vệ, backup/monitor và không chỉnh sửa bằng tay.
- Connector identity/source partition ổn định qua restart và upgrade.
- Source database log retention dài hơn outage + detection + recovery window.
- PostgreSQL replication slot hoặc MySQL binlog được theo dõi về lag/retention.
- Có metric source position, heartbeat age và Kafka output progress.
- Có event ID ổn định và sequence theo aggregate nếu cần phát hiện gap.
- Sequence scope phù hợp với table/topic filter và routing.
- Outbox insert nằm cùng transaction với business update.
- Outbox cleanup có watermark, retention và archive phù hợp.
- Downstream có inbox/deduplication và idempotent side effect.
- Có quy trình resume, snapshot, backfill và offset alter theo từng loại sự cố.
- Không reset offset hoặc xóa replication slot trước khi xác định tác động.
- Backfill và live CDC có watermark/cutover plan.
- Có audit đối chiếu event ID/sequence và count/checksum.
- Có diễn tập worker crash, task failure, source log purge và replay.

## 21. Câu hỏi tự kiểm tra

1. Source connector offset khác consumer group offset ở điểm nào?
2. Worker restart, task restart và source offset reset có tác động khác nhau ra sao?
3. Vì sao worker có thể chạy lại task nhưng không thể đọc một binlog/WAL đã bị purge?
4. PostgreSQL replication slot giúp giữ WAL như thế nào và rủi ro khi slot inactive là gì?
5. Cần kiểm tra những thông tin nào trước khi restart một source connector?
6. Vì sao snapshot bảng hiện tại không thể tái tạo mọi event history?
7. Khi nào nên resume, snapshot, backfill hoặc tạo connector/topic mới?
8. Offset management REST API có thể dùng để làm gì và vì sao phải kiểm tra version?
9. Event ID và aggregate sequence phát hiện duplicate/gap khác nhau như thế nào?
10. Vì sao sequence nhảy không luôn có nghĩa event bị mất?
11. Heartbeat giúp phân biệt source idle và connector không tiến triển ra sao?
12. Lag khác gap như thế nào?
13. Outbox event cần những field nào để hỗ trợ recovery và audit?
14. Vì sao outbox row không nên bị cleanup quá sớm?
15. Làm thế nào để backfill song song với live CDC mà không làm sai ordering?
16. Vì sao chỉ nhìn connector status `RUNNING` chưa đủ để xác nhận dữ liệu đầy đủ?

## Kết luận

Khôi phục CDC bắt đầu bằng việc phân biệt trạng thái worker/task, source offset, transaction log nguồn và Kafka output. Nếu log nguồn còn đủ, connector thường có thể resume từ offset đã lưu; nếu WAL/binlog đã bị purge, cần snapshot hoặc backfill có watermark và đối soát, vì restart không thể khôi phục log đã mất. Outbox cung cấp event history bền vững hơn để audit và replay; event ID giúp nhận diện duplicate, aggregate sequence giúp phát hiện gap trong đúng phạm vi. Kết hợp retention headroom, heartbeat, source position, audit và runbook giúp hệ thống phát hiện khoảng trống sớm và phục hồi có kiểm soát.
