# Snapshot so với streaming trong Debezium

## 1. Vì sao CDC cần cả snapshot lẫn streaming?

Trong module **SPRING_INTEGRATION_ADAPTERS**, ứng dụng sử dụng inbound/outbound adapter, gateway, poller và `MessageChannel` để trao đổi dữ liệu với hệ thống ngoài như Kafka, JMS, HTTP hoặc cơ sở dữ liệu. Khi nguồn dữ liệu là database nghiệp vụ, **Debezium** có thể thu nhận thay đổi bằng *Change Data Capture* (CDC), rồi chuyển sự kiện cho luồng Spring Integration xử lý.

Nhưng khi lần đầu kết nối tới bảng `sales.orders` đang có 2 triệu đơn hàng, transaction log thường chỉ cung cấp những thay đổi còn nằm trong khoảng log được lưu giữ. Muốn tạo một bản sao dữ liệu đầy đủ và tiếp tục cập nhật liên tục, ta cần giải quyết hai câu hỏi:

1. **Dữ liệu đã tồn tại trước khi chạy connector được lấy bằng cách nào?** Đó là nhiệm vụ thường gặp của *snapshot*.
2. **Những thay đổi được commit trong lúc hệ thống hoạt động được lấy bằng cách nào?** Đó là nhiệm vụ của *streaming* từ transaction log.

Snapshot và streaming là **hai giai đoạn bổ trợ** trong một luồng CDC; ứng dụng có thể bắt đầu chỉ với streaming trong những tình huống cụ thể, hoặc chủ động chụp bổ sung một phần dữ liệu bằng incremental snapshot.

Sau bài học, bạn sẽ:

- Phân biệt mục tiêu, nguồn dữ liệu, sự kiện, tính nhất quán, độ trễ và chi phí của snapshot/streaming.
- Hiểu chuyển tiếp từ initial snapshot sang streaming và vai trò của source offset.
- Nhận biết *blocking snapshot*, *incremental snapshot*, snapshot mode và signal theo phạm vi connector hỗ trợ.
- Xây dựng nguyên tắc xử lý CDC trong Spring Integration: upsert, delete, idempotency, thứ tự message và lỗi khôi phục.
- Chọn chiến lược snapshot phù hợp cho đồng bộ lần đầu, thêm bảng mới, sửa projection hoặc vận hành lại connector.

## 2. Bức tranh tổng thể

~~~mermaid
flowchart TD
    A[(Database nghiệp vụ)] --> B{Đã có source offset<br/>hợp lệ?}
    B -- Không, snapshot.mode=initial --> C[Initial snapshot<br/>đọc trạng thái hiện có]
    C --> D[Checkpoint ranh giới log<br/>và tiến độ snapshot]
    D --> E[Streaming<br/>đọc binlog / WAL]
    B -- Có --> E
    B -- Chọn chế độ không chụp dữ liệu --> E
    E --> F[Debezium change events]
    F --> G[(Kafka topic hoặc sink)]
    G --> H[Spring Integration inbound adapter]
    H --> I[MessageChannel]
    I --> J[Handler cập nhật projection]
    E -. Có thể nhận signal .-> K[Incremental snapshot<br/>một số bảng / chunk]
    K --> F
~~~

Sơ đồ cho thấy một kịch bản thường gặp với Debezium chạy trên Kafka Connect. **Nhánh vận hành thực tế tùy theo snapshot mode, connector, offset còn lưu và phiên bản Debezium**. Debezium Engine hoặc Debezium Server dùng cơ chế offset/sink khác nhưng vẫn có bài toán khởi tạo và đọc tiếp tương tự.

Trong quá trình này có ba loại tiến độ độc lập:

| Tiến độ | Thuộc về | Ý nghĩa |
|---|---|---|
| Vị trí nguồn | MySQL binlog, PostgreSQL WAL/LSN, v.v. | Sự thay đổi nằm ở đâu trong transaction log |
| Debezium source offset | Connector/offset store | Trạng thái để connector tiếp tục snapshot hoặc streaming sau restart |
| Kafka consumer offset | Consumer group của Spring Integration | Ứng dụng đã xác nhận tiêu thụ tới đâu trong partition của Kafka |

Không thể suy ra một loại offset từ một loại khác. Khi Debezium hoàn tất snapshot, điều đó **không chứng minh** toàn bộ snapshot đã được áp dụng thành công ở database đích.

## 3. Snapshot: đọc trạng thái đang có

### 3.1. Initial snapshot hoạt động thế nào?

*Initial snapshot* giúp connector chụp những hàng đang có tại một thời điểm hoặc một ảnh nhìn nhất quán được xác định bởi database/connector. Debezium thường thực hiện các công việc logic:

1. Khám phá schema và danh sách bảng được capture theo cấu hình.
2. Xác định ranh giới hoặc tọa độ log dùng để nối snapshot với streaming.
3. Đọc bản ghi hiện có của các bảng đã chọn, phát ra những sự kiện dạng **read**.
4. Lưu trạng thái/tiến độ snapshot theo cơ chế offset của connector.
5. Chuyển sang streaming, đọc các thay đổi đã commit từ ranh giới log phù hợp.

**Lưu ý về tính nhất quán:** cơ chế khóa, mức cô lập, số lần chụp và cách xác định ranh giới thay đổi tùy hệ quản trị CSDL, loại bảng và chế độ snapshot. PostgreSQL thường khai thác MVCC/replication slot; MySQL có yêu cầu về binlog và consistent read. Không nên mặc định snapshot luôn “khóa toàn bộ database” hoặc “không sử dụng khóa”.

Giả sử tại thời điểm snapshot, bảng `orders` có:

| id | status | total |
|---:|---|---:|
| 101 | NEW | 150000 |
| 102 | PAID | 250000 |

Debezium có thể phát hai event **`op = "r"`** (read) tương ứng với trạng thái của hai hàng. Snapshot không tự dựng lại được lịch sử “đơn 102 trước đó từng ở trạng thái NEW” nếu lịch sử ấy không còn trong các bản ghi đang đọc hoặc log được giữ lại.

Ví dụ envelope được **rút gọn để dễ nhìn**:

~~~json
{
  "before": null,
  "after": {
    "id": 102,
    "status": "PAID",
    "total": 250000
  },
  "source": {
    "connector": "mysql",
    "db": "sales",
    "table": "orders",
    "snapshot": "true"
  },
  "op": "r"
}
~~~

Một số connector đánh dấu bản ghi cuối của snapshot bằng giá trị như `"last"`; dạng dữ liệu của `source.snapshot` phụ thuộc converter/schema. Với incremental snapshot, `op = "r"` vẫn có thể xuất hiện **sau khi streaming đã hoạt động**.

### 3.2. Snapshot giải quyết được gì, và giới hạn ở đâu?

Snapshot cung cấp **trạng thái ban đầu** để khởi tạo search index, cache, data warehouse hoặc bảng projection. Đổi lại, nó có thể tiêu tốn I/O, CPU, kết nối database, dung lượng message broker và thời gian vận chuyển khối lượng dữ liệu lớn. Snapshot dài cũng làm tăng yêu cầu giữ transaction log đủ lâu để nối tiếp streaming.

Snapshot không tự đảm bảo đồng bộ hai chiều, không thể tái hiện mọi lịch sử trước ranh giới chụp, và không có nghĩa sink đã xử lý xong chỉ vì connector phát hết các bản ghi `r`.

## 4. Streaming: đọc thay đổi đã commit từ log

Sau khi có ranh giới log hợp lệ, Debezium đọc dữ liệu thay đổi qua cơ chế log của nguồn:

- **MySQL:** binary log (*binlog*), thường ở row-based format; vị trí liên quan tới binlog file, position và có thể GTID.
- **PostgreSQL:** WAL qua logical decoding và replication slot; vị trí thường là LSN.
- **Nguồn khác:** SQL Server, Oracle, MongoDB có cơ chế ghi và định vị riêng.

Streaming phản ánh **những thay đổi được commit**, thường là insert/update/delete. Các giá trị `op` điển hình trong envelope:

| `op` | Tên | Ý nghĩa đối với dữ liệu đích |
|---|---|---|
| `r` | Read | Hàng được đọc trong snapshot; thường có thể xử lý như khởi tạo/upsert |
| `c` | Create | Một hàng mới được insert; thường upsert/insert theo khóa |
| `u` | Update | Hàng được cập nhật; áp dụng trạng thái mới hoặc xử lý khác biệt |
| `d` | Delete | Hàng bị xóa; xóa hoặc đánh dấu xóa ở projection |

Ví dụ event streaming sau khi đơn 101 chuyển từ `NEW` sang `PAID`:

~~~json
{
  "before": { "id": 101, "status": "NEW", "total": 150000 },
  "after":  { "id": 101, "status": "PAID", "total": 150000 },
  "source": {
    "connector": "mysql",
    "db": "sales",
    "table": "orders",
    "file": "mysql-bin.000021",
    "pos": 23456,
    "snapshot": "false"
  },
  "op": "u"
}
~~~

Các ví dụ JSON biểu diễn cấu trúc logic, **không cam kết** mọi trường đều có mặt trong tất cả phiên bản Debezium, mọi connector hoặc sau khi dùng SMT/converter. Giá trị `before` cũng tùy khả năng log và cấu hình nguồn.

### Streaming khác database polling ở đâu?

Polling thông thường chạy câu SQL định kỳ, ví dụ “lấy các hàng có `updated_at` mới hơn lần trước”. Cách này cần cột theo dõi tin cậy, có thể bỏ qua các thay đổi xảy ra nhanh giữa hai lần polling, và khó nhận diện DELETE nếu hàng đã biến mất. Debezium streaming theo transaction log cung cấp luồng thay đổi theo khả năng nguồn và cơ chế capture, không cần liên tục quét cả bảng để tìm hàng mới.

Tuy vậy, streaming **không bảo đảm** độ trễ bằng 0: có thời gian commit, giải mã, buffer, truyền qua broker, xử lý downstream và có thể bị lag. Nó cũng phụ thuộc retention log, quyền replication và sức khỏe connector.

### Delete event và tombstone

Khi một hàng bị xóa, Debezium thường phát event `op = "d"`. Với connector/cấu hình có tạo tombstone, Kafka còn có thể nhận bản ghi **cùng key nhưng value null** để phục vụ log compaction. Tombstone không phải một sự kiện update thứ hai. Khi dùng Spring Integration Kafka adapter, ứng dụng cần hiểu converter/deserializer đang biểu diễn null value ra sao, tránh tự giải mã null như một JSON envelope.

## 5. Snapshot so với streaming: bảng đối chiếu

| Tiêu chí | Snapshot | Streaming |
|---|---|---|
| Mục tiêu | Lấy trạng thái các bản ghi đang tồn tại | Theo dõi thay đổi liên tục sau ranh giới log |
| Nguồn dữ liệu chính | Đọc bảng/schema bằng cơ chế snapshot của connector | Đọc transaction log hoặc change stream |
| Sự kiện phổ biến | `op = r` | `op = c/u/d`, đôi khi có metadata bổ sung |
| Khi thường xảy ra | Khởi tạo connector hoặc yêu cầu snapshot bổ sung | Sau khi chụp ban đầu hoặc theo cấu hình chỉ streaming |
| Chi phí nổi bật | Quét dữ liệu, tải I/O, thời gian chụp, backlog lớn | Giải mã log, duy trì replication và dòng sự kiện liên tục |
| Hàng chưa từng thay đổi | Có thể xuất hiện nếu hàng nằm trong phạm vi snapshot | Không xuất hiện chỉ vì hàng đang tồn tại |
| Thay đổi trước ranh giới capture | Chỉ cho biết trạng thái còn tồn tại, không tái hiện đầy đủ lịch sử | Không thể đọc thay đổi từ log đã bị loại bỏ |
| Tính nhất quán | Phụ thuộc cơ chế snapshot, transaction isolation và connector | Bám theo log commit; thứ tự toàn cục ở sink còn phụ thuộc partition/routing |
| Restart | Có thể resume hoặc chạy lại một phần/toàn phần tùy mode, offset, connector | Tiếp tục từ checkpoint hợp lệ nếu log cần đọc vẫn còn |
| Ảnh hưởng tới sink | Có thể tạo số lượng lớn `r`, cần upsert/bulk load | Áp dụng chuỗi c/u/d, cần retry và idempotency |

Không thể chọn một chế độ chỉ dựa trên tốc độ: nếu cần **đồng bộ đầy đủ dữ liệu hiện có**, streaming từ thời điểm hiện tại không đủ; nếu cần **duy trì bản sao gần thời gian thực**, snapshot một lần cũng không đủ.

## 6. Chuyển tiếp từ initial snapshot sang streaming mà không bỏ sót thay đổi

Điểm khó nhất của initial snapshot là database **vẫn có giao dịch mới trong lúc đang đọc hàng triệu bản ghi**. Debezium phải phối hợp thời điểm đọc nhất quán với ranh giới log. Ví dụ logic:

~~~mermaid
sequenceDiagram
    participant DB as Database
    participant DZ as Debezium connector
    participant OUT as Kafka / Sink
    DZ->>DB: Thiết lập snapshot nhất quán + ranh giới log P
    DZ->>DB: Đọc các hàng hiện có
    DB-->>DB: Giao dịch T1 cập nhật đơn 101, commit sau P
    DZ->>OUT: Phát các event r từ ảnh chụp
    DZ->>DZ: Hoàn tất snapshot; lưu state/offset
    DZ->>DB: Bắt đầu streaming từ vị trí phù hợp
    DB-->>DZ: Log sự kiện T1
    DZ->>OUT: Phát event u của đơn 101
~~~

Ví dụ nếu ảnh chụp nhìn thấy đơn 101 là `NEW`, giao dịch `T1` cập nhật nó thành `PAID` sau ranh giới snapshot, người nhận có thể thấy:

1. `r`: đơn 101 = `NEW`;
2. `u`: đơn 101 = `PAID`.

Trình tự logic giúp projection đạt trạng thái cuối là `PAID`. Cách thiết lập ảnh chụp nhất quán, thứ tự giữa các bảng và phạm vi transaction cụ thể phụ thuộc connector và database. **Không tự xây chuyển tiếp bằng cách vừa chạy `SELECT *` vừa đọc log mà thiếu thuật toán đồng bộ ranh giới**: có thể vừa mất vừa đếm trùng thay đổi.

### Khi nào lần khởi động sau chụp lại từ đầu?

Với `snapshot.mode = initial`, connector thường thực hiện initial snapshot **khi chưa có offset nguồn hợp lệ**. Nếu offset còn và trạng thái snapshot đã hoàn tất, restart tiếp tục từ trạng thái đã lưu thay vì tự động quét lại toàn bảng. Nếu xóa offset store, thay định danh connector nguồn hoặc có sự cố cần recovery, ứng dụng có thể bắt đầu lại theo quy tắc mode và connector.

Source offset có thể bao gồm **trạng thái snapshot** bên cạnh log position. Một con số LSN hay binlog position lấy từ event **không đủ** để tự khôi phục mọi trạng thái snapshot. Khi source offset được lưu định kỳ, crash cũng có thể làm connector phát lại một phần event; đây là lý do sink cần idempotency.

## 7. Incremental snapshot: chụp từng phần khi streaming đang chạy

Không phải lúc nào cũng nên quét hàng triệu bản ghi theo một đợt initial snapshot. Nhiều connector Debezium hỗ trợ **incremental snapshot**: chia dữ liệu của một hoặc nhiều bảng thành các *chunk* theo khóa phù hợp, đọc lần lượt và tiếp tục xử lý luồng thay đổi trong suốt thời gian chụp.

Ví dụ bảng `orders` có khóa chính `id`:

~~~text
Chunk 1: id 1..1000    -> phát event r
Chunk 2: id 1001..2000 -> phát event r
Chunk 3: id 2001..3000 -> phát event r
...
Streaming c/u/d vẫn tiếp tục xen kẽ với các chunk.
~~~

### Vấn đề bản ghi thay đổi trong lúc đọc chunk

Giả sử khi incremental snapshot đọc chunk chứa `orders.id = 101`, ứng dụng đồng thời cập nhật đơn đó. Nếu connector cứ phát bản chụp cũ sau event update, sink có thể **ghi đè trạng thái mới bằng trạng thái cũ**.

Để giảm xung đột này, Debezium dùng cơ chế cửa sổ (*snapshot window*) và nhận diện va chạm giữa những khóa đang snapshot với sự kiện streaming; chi tiết điều phối bằng watermark/signal khác nhau theo connector và phiên bản. Bản ghi snapshot xung đột có thể bị loại khỏi cửa sổ để thay đổi log chiếm ưu tiên. Đây là một phần cơ chế **chống trùng/đè sai trong chính quá trình incremental snapshot**, không loại bỏ nhu cầu idempotency ở downstream sau retry hoặc restart.

Điều kiện vận hành cần xem xét gồm: bảng có khóa thích hợp để chia chunk, kích thước chunk, độ tải DB, tín hiệu điều khiển snapshot, tiến độ đã lưu, schema thay đổi trong lúc chạy, dữ liệu mới phát sinh trong cùng khoảng khóa và thứ tự áp dụng message tại sink.

### Ví dụ yêu cầu incremental snapshot bằng signal

Ở một triển khai Debezium MySQL hỗ trợ signaling qua bảng, giả sử đã cấu hình signal data collection là `sales.debezium_signal` và tạo bảng theo schema mà phiên bản connector yêu cầu. Một lệnh **minh họa**:

~~~sql
INSERT INTO sales.debezium_signal (id, type, data)
VALUES (
    'snap-orders-20261123',
    'execute-snapshot',
    '{"data-collections": ["sales.orders"], "type": "incremental"}'
);
~~~

Debezium quan sát signal được commit và thực hiện snapshot cho data collection được yêu cầu theo khả năng connector. Cần cấu hình đúng signal channel/table, quyền đọc ghi, bộ lọc capture, khóa bảng và chế độ hỗ trợ. Cú pháp signal, tên thuộc tính và tính năng có thể thay đổi theo phiên bản; **chạy thử ở staging trước khi áp dụng cho production**.

Incremental snapshot phù hợp khi **thêm bảng vào phạm vi capture**, đồng bộ lại một tập dữ liệu hoặc giảm ảnh hưởng của lần đọc toàn bảng. Nó không tự sửa một offset streaming bị trỏ tới vị trí log đã mất, và không đảm bảo mọi giao dịch đích tương thích với số lượng lớn event `r` nếu handler chỉ chấp nhận `c/u/d`.

## 8. Chọn snapshot mode theo bài toán

Không phải mọi snapshot mode tồn tại hoặc có cùng tên/ý nghĩa trên mọi phiên bản Debezium và connector. Những lựa chọn thường gặp:

| Nhu cầu | Hướng cấu hình/thao tác | Cần kiểm tra |
|---|---|---|
| Lần đầu dựng projection đầy đủ | `snapshot.mode=initial` và streaming sau snapshot | Bảng được capture, tính nhất quán, retention log, tải DB |
| Chỉ muốn thay đổi mới từ thời điểm bắt đầu | Chế độ không chụp dữ liệu, ví dụ `no_data` ở connector/phiên bản hỗ trợ | Sink đã có baseline đầy đủ chưa; mất dữ liệu cũ là hệ quả có chủ ý |
| Đồng bộ bổ sung một số bảng đang hoạt động | Incremental snapshot theo signal nếu được hỗ trợ | Khóa bảng, chunk, bộ lọc và sự kiện r tại sink |
| Chỉ chụp dữ liệu để xuất một lần | Snapshot-only mode nếu connector/phiên bản hỗ trợ | Connector có tiếp tục streaming hay dừng sau snapshot |
| Chủ động chụp lại toàn bộ khi restart | Chế độ chụp lại có chủ đích, nếu được hỗ trợ | Tải hệ thống, sự kiện lặp, idempotency |
| Không đọc được vị trí log đã lưu | Quy trình phục hồi hoặc snapshot lại đã được đánh giá | Khả năng mất khoảng thay đổi, cần đối soát dữ liệu đích |

### Ví dụ cấu hình initial snapshot với PostgreSQL

Đoạn JSON sau mô tả **cấu hình connector trên Kafka Connect**, không phải bean cấu hình Spring Integration:

~~~json
{
  "name": "sales-orders-cdc",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "tasks.max": "1",
    "topic.prefix": "sales-cdc",
    "database.hostname": "postgres.example.internal",
    "database.port": "5432",
    "database.user": "cdc_reader",
    "database.password": "<set-using-secret-management>",
    "database.dbname": "sales",
    "plugin.name": "pgoutput",
    "slot.name": "sales_orders_slot",
    "publication.name": "sales_orders_pub",
    "table.include.list": "public.orders",
    "snapshot.mode": "initial"
  }
}
~~~

Đây là **ví dụ tham khảo**. Để chạy thực tế, cần cấu hình WAL/logical replication, publication, slot, quyền của user, bảo mật credential, Kafka Connect worker và các yêu cầu riêng của phiên bản Debezium đang dùng. `snapshot.mode=initial` chỉ kiểm soát điều kiện chụp dữ liệu ban đầu; nó không thay thế cấu hình giữ WAL hay giám sát replication slot.

Trong MySQL, cấu hình sẽ dùng connector MySQL, binlog và các thuộc tính chuyên biệt như server ID/schema history. **Không sao chép cấu hình PostgreSQL để chạy MySQL**.

## 9. Xử lý snapshot và streaming trong Spring Integration

Kiến trúc thường gặp với Kafka:

~~~mermaid
flowchart LR
    DB[(MySQL / PostgreSQL)] --> DZ[Debezium<br/>snapshot + streaming]
    DZ --> K[(Kafka CDC topic)]
    K --> IN[Spring Integration<br/>Kafka inbound adapter]
    IN --> CH[MessageChannel]
    CH --> TRANS[Transformer<br/>chuẩn hóa envelope]
    TRANS --> H[Service activator<br/>upsert / delete]
    H --> PROJ[(Projection / cache)]
    H -. Thất bại .-> ERR[Retry / error channel / DLQ]
~~~

Spring Integration có thể nhận message từ Kafka qua inbound adapter hoặc gateway phù hợp, chuyển đến `MessageChannel`, áp dụng transformer/filter/router rồi cập nhật hệ thống đích. Luồng nghiệp vụ cần phân biệt **loại thay đổi của Debezium** và **metadata của Kafka consumer**. Đừng biến `op=r` thành “tạo đơn mới và gửi email khách hàng”: đó có thể chỉ là việc đọc lại một hàng đã tồn tại nhiều năm.

### 9.1. Ví dụ handler xử lý trạng thái, không chạy lại side effect

Giả mã cho một projection `reporting.orders`:

~~~text
handleCdcEvent(message):
    event = decodeDebeziumEnvelope(message)
    if event is a Kafka tombstone:
        processAccordingToTombstonePolicy(message.key)
        return

    key = extractPrimaryKey(message.key, event)

    if event.op in ["r", "c", "u"]:
        desiredState = event.after
        transaction:
            applyIdempotentUpsert(key, desiredState, sourceVersion(event))
            recordProcessingCheckpointIfNeeded(event)

    else if event.op == "d":
        transaction:
            applyIdempotentDelete(key, sourceVersion(event))
            recordProcessingCheckpointIfNeeded(event)

    else:
        routeToUnsupportedEventPolicy(event)

    acknowledgeBrokerConsumptionAfterSuccessfulProcessing()
~~~

Đây là **giả mã**, không phải Java API của một adapter cụ thể. `sourceVersion(event)` phải được thiết kế dựa trên connector và hợp đồng nguồn thực tế; không mặc định một `ts_ms`, `lsn` hay `binlog.pos` riêng lẻ có thể so sánh toàn cục giữa mọi bảng, partition hoặc transaction.

Với hệ thống chỉ cần trạng thái cuối, **idempotent upsert theo khóa nghiệp vụ** thường thích hợp cho `r/c/u`. Với hệ thống phát lệnh thanh toán, gửi email hoặc cộng dồn số lượng, xử lý lặp cần một khóa dedupe bền vững hoặc outbox/giao dịch phù hợp. Nếu event `r` được diễn giải như một sự kiện “mới phát sinh”, side effect rất dễ bị chạy lại khi snapshot hoặc resnapshot.

### 9.2. Những điều dễ gây sai lệch

1. **Thứ tự:** trong Kafka, thứ tự được bảo đảm theo từng partition; dùng key thích hợp cho các thay đổi của cùng bản ghi, và kiểm soát xử lý đồng thời trong Spring Integration. Thứ tự giữa các partition không được suy ra từ thời điểm message đến.
2. **Commit/ack:** chỉ xác nhận offset tiêu thụ sau khi ghi đích an toàn theo chính sách của ứng dụng. Việc đưa message vào queue nội bộ có thể chưa đồng nghĩa projection đã commit; kiểm tra chế độ ACK, async handoff và error flow.
3. **Phát lại:** source offset chưa flush, consumer offset chưa commit hoặc retry đều có thể khiến một sự kiện xuất hiện lần nữa. Snapshot hoàn tất không tạo ra exactly-once end-to-end.
4. **Thay đổi schema:** event trước và sau DDL có thể có cấu trúc khác nhau; transformer/validator phải xem xét schema evolution, converter và SMT đang dùng.
5. **Delete:** cần quy ước rõ xóa vật lý, xóa mềm và tombstone; nhiều hệ thống compacted topic sử dụng tombstone để dọn khóa nhưng hệ thống nghiệp vụ vẫn phải xử lý `op=d`.
6. **Tốc độ:** initial snapshot có thể phát nhanh lượng lớn dữ liệu, tạo Kafka lag hoặc quá tải downstream. Có thể cần backpressure/rate limit, batch hoặc tăng tài nguyên ở điểm nghẽn phù hợp.

### 9.3. Luồng lỗi và trách nhiệm

| Lỗi | Thuộc lớp nào? | Xử lý phù hợp |
|---|---|---|
| PostgreSQL slot/WAL không còn dùng được | Database + Debezium | Kiểm tra checkpoint, WAL retention và quy trình khôi phục nguồn |
| Event snapshot quá nhiều làm consumer lag | Debezium/Kafka/Spring Integration | Đo throughput, phân bổ tài nguyên, chunk/throttle nếu được hỗ trợ |
| Transformer không hiểu `op=r` | Spring Integration | Thêm nhánh xử lý read event, kiểm thử dữ liệu chụp |
| Projection ghi xong nhưng consumer chết trước commit | Consumer + sink | Idempotency để nhận lại bản ghi an toàn |
| Event `d` bị bỏ qua | Ứng dụng đích | Xác định chính sách delete và kiểm tra consistency |
| Snapshot đọc thiếu bảng do filter | Cấu hình connector | Xác nhận `table.include.list` / các bộ lọc liên quan trước chạy |

Các adapter khác như file, HTTP, JMS, AMQP hoặc database có thể tham gia **phần sau của flow** thông qua outbound handler/gateway. Bản chất snapshot/streaming vẫn do Debezium và database nguồn quyết định; đặt poller trong Spring Integration không biến query polling thành transaction-log CDC.

## 10. Các tình huống thiết kế thực tế

### Tình huống A — Khởi tạo kho báo cáo mới

Database `sales` đã có 500.000 đơn hàng; đội phân tích cần dữ liệu lịch sử còn tồn tại và thay đổi tương lai.

**Lựa chọn:** initial snapshot + streaming. Projection xử lý `r` bằng upsert, sau đó nhận `c/u/d`. Cần xác nhận đầy đủ tập bảng, tính nhất quán và đối soát số hàng/số tiền trước khi công bố báo cáo.

### Tình huống B — Nạp dữ liệu đích đã có baseline tin cậy

Kho báo cáo đã được đồng bộ bằng cơ chế khác và chỉ muốn nhận biến động từ một ranh giới rõ ràng.

**Lựa chọn:** streaming-only/no-data snapshot mode phù hợp connector nếu chấp nhận không đọc lại toàn bộ hàng có sẵn. Phải kiểm chứng ranh giới bàn giao, dữ liệu đích và retention log; nếu baseline không đầy đủ, các bản ghi không thay đổi sẽ không tự xuất hiện.

### Tình huống C — Thêm bảng sản phẩm sau ba tháng vận hành

Connector đang streaming bảng `orders`, giờ cần thêm `products` mà tránh dừng luồng đơn hàng.

**Lựa chọn:** cập nhật danh sách bảng capture/schema theo quy trình connector; nếu được hỗ trợ, phát incremental snapshot cho `products`. Kiểm tra quyền, khóa chính, schema history, cấu hình signal, tiến độ snapshot và downstream có xử lý `r`.

### Tình huống D — Lỗi sink khi snapshot vừa chạy xong

Debezium đã phát đủ 500.000 sự kiện `r` vào Kafka, nhưng ứng dụng báo cáo mới ghi được 420.000.

**Lựa chọn:** sửa lỗi ở consumer/sink, theo dõi consumer group offset, retry hoặc replay từ Kafka theo chính sách. Không vội xóa offset Debezium và chụp lại database: checkpoint của connector không đại diện cho tiến độ consumer.

### Tình huống E — Connector dừng dài ngày

Source offset lưu tại vị trí log cũ, nhưng MySQL đã purge binlog tương ứng hoặc PostgreSQL không còn WAL cần đọc.

**Lựa chọn:** đánh giá khả năng khôi phục và khoảng dữ liệu có thể thiếu. Có thể cần đối soát/resnapshot có kiểm soát, chứ không thể bảo đảm resume chỉ bằng việc restart. Theo dõi log retention và thời gian dừng tối đa phục hồi để phòng ngừa.

## 11. Thực hành suy luận event và trạng thái cuối

Cho bảng `orders` tại thời điểm bắt đầu initial snapshot:

| id | status |
|---:|---|
| 11 | NEW |
| 12 | PAID |

Giả định snapshot thiết lập được ranh giới log nhất quán tại vị trí `P`. Trong khi chụp, có hai giao dịch commit sau `P`:

- `T1` cập nhật `orders.id = 11` từ `NEW` sang `PAID`.
- `T2` xóa `orders.id = 12`.

Sau khi snapshot kết thúc, streaming đọc tiếp các transaction.

**Câu hỏi:**

1. Loại event nào có thể xuất hiện cho hai đơn hàng ở giai đoạn snapshot và streaming?
2. Sau khi áp dụng đúng thứ tự logic, projection cuối cùng phải có những hàng nào?
3. Nếu ứng dụng nhận lại `r` của đơn 11 do retry, làm sao không gửi lại email “đơn mới”?
4. Nếu dùng incremental snapshot khi streaming đã hoạt động, một update xảy ra giữa lúc đọc chunk cần được chú ý điều gì?

<details>
<summary>Gợi ý lời giải</summary>

1. Snapshot có thể phát `r(11, NEW)` và `r(12, PAID)`. Streaming sau đó phát `u(11, PAID)` và `d(12)`. Kafka có thể có tombstone riêng cho đơn 12 nếu được bật.
2. Projection cuối có đơn 11 ở trạng thái `PAID`; đơn 12 bị xóa hoặc đánh dấu xóa theo chính sách sink.
3. Tách **đồng bộ trạng thái** khỏi **side effect nghiệp vụ**. `r` chỉ upsert dữ liệu, không phát email; với tác vụ cần hiệu ứng đúng một lần, dùng cơ chế dedupe/outbox phù hợp.
4. Cần cơ chế window/collision resolution của incremental snapshot và xử lý có thứ tự/idempotent tại sink để dữ liệu chụp cũ không ghi đè update mới.

</details>

**Mở rộng:** giữ offset Debezium tại `P` nhưng để consumer đã ghi xong đơn 11 trước khi crash. Khi restart, có thể tồn tại **hai tầng phát lại**: connector phát lại change event nếu offset nguồn chưa flush, và consumer đọc lại event Kafka nếu group offset chưa commit. Bảo đảm dữ liệu đích an toàn trước cả hai trường hợp.

## 12. Checklist trước khi vận hành

- [ ] Xác định cần đồng bộ **trạng thái đang có**, **thay đổi mới**, hay cả hai.
- [ ] Xác nhận snapshot mode thực sự được connector/phiên bản hỗ trợ; kiểm tra trạng thái offset hiện tại.
- [ ] Chọn cơ chế snapshot nhất quán phù hợp database, khối lượng dữ liệu và khả năng chịu tải.
- [ ] Kiểm tra retention MySQL binlog/PostgreSQL WAL/replication slot xuyên suốt snapshot dài và các lần dừng.
- [ ] Nếu dùng incremental snapshot, kiểm tra khóa phù hợp, chunk size, signal và xử lý sự kiện `r` xen kẽ streaming.
- [ ] Tạo handler Spring Integration phân biệt `r/c/u/d`, tombstone, schema evolution và lỗi deserialization.
- [ ] Đảm bảo projection upsert/delete idempotent; ack Kafka consumer theo kết quả xử lý thực tế.
- [ ] Theo dõi snapshot progress, source lag, Kafka consumer lag, số lượng record đích và độ trễ đầu cuối.
- [ ] Thử restart giữa snapshot, giữa streaming và ngay sau khi ghi dữ liệu đích nhưng trước khi commit consumer offset.
- [ ] Có quy trình đối soát/resnapshot có kiểm soát khi offset hoặc log nguồn không còn hợp lệ.

**Điểm cốt lõi:** snapshot cung cấp **ảnh trạng thái ban đầu** (hoặc một phần trạng thái cần đồng bộ lại), còn streaming cung cấp **dòng thay đổi đã commit** để giữ ảnh đó liên tục cập nhật. Debezium chịu trách nhiệm nối hai giai đoạn theo vị trí log và trạng thái connector; Spring Integration chịu trách nhiệm đưa từng message qua `MessageChannel` tới hệ thống đích, xử lý đúng nghiệp vụ và chịu được phát lại.
