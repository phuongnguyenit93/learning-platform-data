# Change Data Capture, GoldenGate và phân biệt với Data Guard

Một hệ thống nghiệp vụ thường cần biết dữ liệu nào đã thay đổi để cập nhật kho dữ liệu, đồng bộ sang ứng dụng khác, xây dựng báo cáo gần thời gian thực hoặc phát sự kiện cho các dịch vụ downstream. Đọc lại toàn bộ bảng theo lịch có thể đơn giản lúc đầu nhưng trở nên tốn kém khi dữ liệu lớn, tần suất thay đổi cao hoặc yêu cầu độ trễ thấp. **Change Data Capture (CDC)** giải quyết bài toán này bằng cách ghi nhận các thay đổi phát sinh ở nguồn và chuyển chúng đến nơi tiêu thụ.

Trong hệ sinh thái Oracle, Oracle GoldenGate là một nền tảng phổ biến để capture, truyền và apply các thay đổi dữ liệu giữa các database hoặc hệ thống khác nhau. GoldenGate có thể đọc redo của Oracle Database, chuyển thay đổi thành các bản ghi logic trong trail file, truyền trail qua mạng và áp dụng chúng ở target. Nhờ đó, hệ thống đích nhận được insert, update, delete và một số thay đổi cấu trúc theo cấu hình.

Oracle Data Guard cũng truyền thông tin thay đổi từ primary sang standby, nhưng mục tiêu và cách vận hành khác GoldenGate. Data Guard chủ yếu bảo vệ một database bằng standby database để đáp ứng high availability và disaster recovery. GoldenGate chủ yếu phục vụ logical replication và phân phối thay đổi đến các hệ thống tiêu thụ. Hai công nghệ có thể bổ sung cho nhau trong cùng kiến trúc.

## 1. Change Data Capture là gì?

Change Data Capture là kỹ thuật nhận biết và chuyển tiếp những thay đổi xảy ra trong dữ liệu nguồn. Thay đổi thường gồm:

- `INSERT`: một dòng mới được thêm.
- `UPDATE`: giá trị của một hoặc nhiều cột thay đổi.
- `DELETE`: một dòng bị xóa.
- DDL: một số thay đổi cấu trúc như tạo, sửa hoặc xóa object nếu công cụ và cấu hình hỗ trợ.

CDC khác với việc sao chép toàn bộ bảng theo lịch. Với full refresh, hệ thống đọc lại cả tập dữ liệu để tạo trạng thái mới. Với CDC, hệ thống đọc phần thay đổi kể từ một vị trí đã biết, nhờ đó giảm lượng dữ liệu phải chuyển khi tỷ lệ thay đổi nhỏ so với tổng dữ liệu.

Ví dụ, bảng `ORDERS` có 200 triệu dòng nhưng mỗi phút chỉ có vài nghìn giao dịch mới hoặc cập nhật. Một job full refresh mỗi phút sẽ phải đọc và truyền lượng dữ liệu rất lớn. CDC có thể chuyển các thay đổi tương ứng với những giao dịch vừa commit.

### 1.1. CDC thường được dùng ở đâu?

| Nhu cầu | Cách CDC hỗ trợ |
|---|---|
| Đồng bộ database | Chuyển thay đổi từ database nguồn sang database đích |
| Data warehouse | Đưa các bản ghi mới/cập nhật/xóa vào kho dữ liệu để xử lý tiếp |
| Data lake | Phát thay đổi sang nền tảng lưu trữ hoặc xử lý dữ liệu khác |
| Search index | Cập nhật tài liệu tìm kiếm khi dữ liệu nghiệp vụ thay đổi |
| Event-driven architecture | Phát sự kiện thay đổi để các service downstream xử lý |
| Reporting gần thời gian thực | Cập nhật bảng báo cáo hoặc read model theo thay đổi nguồn |
| Audit và phân tích | Lưu lịch sử thay đổi theo chính sách và định dạng riêng |

CDC không tự quyết định ý nghĩa nghiệp vụ của một thay đổi. Ví dụ, một `UPDATE` đổi `ORDER_STATUS` từ `NEW` sang `CANCELLED` là thay đổi dữ liệu; việc downstream phải hoàn tiền, gửi thông báo hay giải phóng tồn kho là quy tắc nghiệp vụ của ứng dụng tiêu thụ.

### 1.2. CDC không đồng nghĩa với event sourcing

CDC ghi nhận thay đổi trên dữ liệu đã được lưu trong database. Event sourcing lưu các sự kiện nghiệp vụ làm nguồn dữ liệu chính và dựng trạng thái hiện tại bằng cách áp dụng các sự kiện. Hai cách có thể cùng xuất hiện trong một hệ thống, nhưng không thể coi mọi bản ghi redo hoặc mọi row change là một business event hoàn chỉnh.

Ví dụ, một transaction có thể cập nhật nhiều bảng để hoàn tất một nghiệp vụ đặt hàng. CDC có thể capture các thay đổi từng bảng. Nếu downstream cần một sự kiện nghiệp vụ duy nhất `OrderPlaced`, cần một lớp xử lý gom các thay đổi và xác định transaction boundary hoặc ứng dụng nên phát business event riêng.

## 2. Các cách triển khai CDC

CDC có thể được thực hiện theo nhiều cách. Việc chọn phương pháp ảnh hưởng đến độ trễ, tính đầy đủ, overhead trên nguồn và độ phức tạp vận hành.

### 2.1. Snapshot hoặc polling theo cột thời gian

Ứng dụng định kỳ truy vấn các dòng có `UPDATED_AT` lớn hơn watermark lần trước:

```sql
SELECT order_id,
       customer_id,
       order_status,
       updated_at
FROM orders
WHERE updated_at > :last_watermark
ORDER BY updated_at, order_id;
```

Ưu điểm là dễ hiểu và dễ triển khai. Tuy nhiên, cách này có một số giới hạn:

- Không phát hiện được dòng đã bị xóa nếu không có tombstone hoặc cơ chế soft delete.
- Có thể bỏ sót thay đổi nếu timestamp không được cập nhật chính xác.
- Hai dòng có cùng timestamp ở ranh giới watermark có thể bị đọc trùng hoặc bị bỏ sót nếu logic không chặt.
- Clock, precision và transaction commit order có thể làm timestamp ứng dụng không phản ánh chính xác thứ tự commit.
- Polling thường phải quét index/range lặp lại và có thể tạo tải trên bảng nguồn.

Nếu dùng polling, nên có khóa thứ tự phụ để tạo watermark ổn định, ví dụ `(UPDATED_AT, ORDER_ID)`, có overlap window và xử lý idempotent. Dù vậy, polling không phải log-based CDC đầy đủ.

### 2.2. Trigger-based CDC

Trigger trên bảng ghi lại thay đổi vào bảng audit hoặc change table:

```sql
CREATE OR REPLACE TRIGGER orders_audit_trg
AFTER INSERT OR UPDATE OR DELETE ON orders
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        INSERT INTO orders_change_log (
            order_id, operation_type, changed_at
        ) VALUES (
            :NEW.order_id, 'I', SYSTIMESTAMP
        );
    ELSIF UPDATING THEN
        INSERT INTO orders_change_log (
            order_id, operation_type, changed_at
        ) VALUES (
            :NEW.order_id, 'U', SYSTIMESTAMP
        );
    ELSIF DELETING THEN
        INSERT INTO orders_change_log (
            order_id, operation_type, changed_at
        ) VALUES (
            :OLD.order_id, 'D', SYSTIMESTAMP
        );
    END IF;
END;
/
```

Ví dụ trên chỉ minh họa ý tưởng. Một giải pháp production cần xử lý khóa, old/new values, transaction identity, bulk DML, error handling, retention và tải ghi bổ sung.

Trigger-based CDC có thể ghi thay đổi trong cùng transaction, nhưng làm tăng công việc trên đường DML của ứng dụng. Trigger row-level có thể gây overhead lớn với bulk load, dễ tạo phụ thuộc vào cấu trúc bảng và cần thiết kế cẩn thận để tránh recursion hoặc side effects.

### 2.3. Log-based CDC

Log-based CDC đọc thông tin thay đổi từ transaction log của database thay vì yêu cầu ứng dụng ghi thêm một bản sao thay đổi bằng trigger. Với Oracle, redo log chứa thông tin cần thiết để phục hồi database và có thể được các công cụ như GoldenGate sử dụng để tái tạo logical changes.

Ưu điểm của log-based capture:

- Có thể nhận thay đổi từ nhiều ứng dụng mà không yêu cầu từng ứng dụng tự ghi change table.
- Có thể capture transaction theo thứ tự commit và giữ ranh giới transaction.
- Không cần chạy một truy vấn polling trên toàn bộ bảng để tìm dòng mới.
- Có thể giảm overhead trực tiếp trên đường DML so với trigger-based approach.

Nhưng log-based CDC cần cấu hình redo/supplemental logging, quyền truy cập log, retention và cơ chế recovery/checkpoint phù hợp. Nó cũng phụ thuộc khả năng capture của phiên bản và loại object/operation.

### 2.4. So sánh các phương pháp

| Tiêu chí | Polling | Trigger-based | Log-based |
|---|---|---|---|
| Nguồn thay đổi | Query trên bảng | Trigger ghi change table | Transaction log/redo |
| Phát hiện delete | Cần thiết kế bổ sung | Có thể ghi rõ trong trigger | Có thể capture từ log |
| Overhead trên DML | Thường thấp ở mỗi DML nhưng có polling query | Thêm công việc trong transaction nguồn | Đọc log và xử lý capture ngoài đường DML chính |
| Độ trễ | Theo chu kỳ polling | Gần thời gian thực sau commit/trigger processing | Có thể gần thời gian thực tùy capture và transport |
| Transaction ordering | Phải tự thiết kế watermark | Có thể ghi cùng transaction | Có thể giữ transaction/order từ log |
| Độ phức tạp | Thấp đến trung bình | Trung bình | Trung bình đến cao |
| Trường hợp phù hợp | Bảng nhỏ, thay đổi đơn giản, độ trễ thấp không bắt buộc | Audit/change log cục bộ có phạm vi rõ | Đồng bộ lớn, nhiều bảng, yêu cầu latency/transaction semantics |

## 3. Redo, archive log và supplemental logging trong Oracle CDC

Oracle Database tạo redo để hỗ trợ instance recovery và media recovery. Redo ghi lại thông tin cần thiết để tái tạo thay đổi trên database block. Redo có thể nằm trong online redo log và sau đó được archive thành archived redo log.

GoldenGate sử dụng redo để nhận biết các thay đổi logic. Để xác định đầy đủ dòng và cột liên quan, đặc biệt với update/delete, cần thông tin định danh đủ trong redo. Supplemental logging bổ sung các giá trị khóa hoặc cột cần thiết vào redo.

### 3.1. Online redo và archived redo

Khi transaction thực hiện DML, Oracle tạo redo trong redo log buffer và ghi xuống online redo log theo cơ chế LGWR. Khi log switch xảy ra và điều kiện archiving được đáp ứng, ARCn hoặc cơ chế tương ứng tạo archived redo log.

Một log-based capture process có thể đọc online redo để giảm độ trễ và dùng archived redo để tiếp tục đọc khi cần. Nếu log cần thiết bị xóa trước khi capture process đọc tới, tiến trình có thể bị gián đoạn hoặc cần khôi phục từ backup/log khác theo khả năng cấu hình.

Vì vậy, chính sách archive log retention và backup phải được thiết kế cùng GoldenGate. Không nên xóa archive log chỉ vì database đã backup nếu GoldenGate Extract vẫn cần đọc log đó.

### 3.2. Supplemental logging là gì?

Redo thông thường được tối ưu cho recovery. Một số thay đổi không ghi đủ giá trị cũ để một công cụ CDC xác định chính xác dòng cần cập nhật ở target. Supplemental logging yêu cầu Oracle ghi thêm thông tin định danh vào redo.

Có thể bật database-level minimal supplemental logging:

```sql
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA;
```

Tùy mô hình capture và bảng, cần bật thêm logging cho primary key, unique key hoặc all columns. Ví dụ ở cấp database:

```sql
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA (PRIMARY KEY) COLUMNS;
```

Hoặc ở cấp table:

```sql
ALTER TABLE app.orders
ADD SUPPLEMENTAL LOG DATA (PRIMARY KEY) COLUMNS;
```

Các câu lệnh trên cần được đối chiếu với phiên bản Oracle, cấu hình GoldenGate và loại key thực tế. Không nên bật all-column logging cho mọi bảng mà không cân nhắc kích thước redo và chi phí. Bật supplemental logging làm tăng lượng redo được tạo, đổi lại capture có đủ dữ liệu để định danh thay đổi.

### 3.3. Key logging và định danh dòng

GoldenGate cần biết target row nào tương ứng với source row. Primary key thường là lựa chọn tốt nhất. Nếu bảng không có primary key, có thể dùng unique key hoặc cơ chế định danh khác theo cấu hình. Với bảng không có khóa duy nhất, việc xác định dòng có thể khó và có thể phải log nhiều cột hơn.

Ví dụ bảng `ORDERS` có primary key `ORDER_ID`. Khi update `ORDER_STATUS`, target có thể tìm dòng bằng `ORDER_ID` và áp dụng giá trị mới. Nếu bảng không có khóa duy nhất, hai dòng có cùng giá trị ở nhiều cột có thể khiến apply không xác định được một dòng duy nhất hoặc tạo xung đột.

Thiết kế primary key/unique key tốt giúp CDC đơn giản, giảm lượng supplemental data và tăng độ tin cậy khi apply.

### 3.4. Kiểm tra supplemental logging

Một số view hữu ích:

```sql
SELECT supplemental_log_data_min,
       supplemental_log_data_pk,
       supplemental_log_data_ui,
       supplemental_log_data_fk,
       supplemental_log_data_all
FROM v$database;
```

Kiểm tra log group ở cấp bảng:

```sql
SELECT owner,
       table_name,
       log_group_name,
       log_group_type,
       always
FROM dba_log_groups
WHERE owner = 'APP'
  AND table_name = 'ORDERS';
```

Các view và cột có thể khác theo phiên bản. Cần xác nhận chính sách logging thực tế trước khi start capture.

## 4. Oracle GoldenGate là gì?

Oracle GoldenGate là nền tảng capture, transport và delivery các thay đổi dữ liệu giữa hệ thống nguồn và hệ thống đích. GoldenGate hỗ trợ nhiều mô hình topology và nhiều loại database/platform theo phiên bản, license và cấu hình được triển khai.

GoldenGate có thể được dùng để:

- Replicate dữ liệu từ Oracle sang Oracle.
- Replicate từ Oracle sang một database hoặc nền tảng dữ liệu khác được hỗ trợ.
- Duy trì read-only/reporting copy.
- Cấp dữ liệu thay đổi cho data warehouse hoặc data lake.
- Phân phối dữ liệu cho nhiều consumer.
- Hỗ trợ migration với thời gian downtime thấp bằng initial load kết hợp CDC.

GoldenGate là công nghệ logical replication. Nó hiểu các thao tác dữ liệu ở mức bảng/record và có thể map, filter, transform theo cấu hình. Điều này khác với việc gửi nguyên block/redo để tạo một physical standby giống primary.

## 5. Kiến trúc GoldenGate cổ điển: Extract, Trail, Pump và Replicat

Trong kiến trúc Classic, các thành phần cốt lõi thường gồm:

- **Manager:** quản lý các process GoldenGate trong deployment Classic, hỗ trợ start/stop và một số tác vụ quản trị.
- **Extract:** đọc thay đổi từ redo/log source hoặc nguồn được hỗ trợ và tạo trail record.
- **Local trail:** file tuần tự chứa các logical change records trên máy nguồn.
- **Data Pump:** Extract phụ trên source, đọc local trail và gửi dữ liệu đến target qua mạng; đây là GoldenGate Data Pump process, không phải Oracle Data Pump utility `expdp`/`impdp`.
- **Remote trail:** trail được ghi tại phía target hoặc deployment trung gian.
- **Replicat:** đọc trail và áp dụng thay đổi vào target database.
- **Checkpoint:** lưu vị trí tiến trình đã xử lý để có thể tiếp tục sau restart.

```text
       Source Oracle Database
       +----------------------+
       | Tables / Transactions|
       | Online & Archive Redo|
       +----------+-----------+
                  |
                  v
              EXTRACT
                  |
                  v
            Local Trail
                  |
                  v
           Data Pump (optional)
                  |
              Network
                  |
                  v
            Remote Trail
                  |
                  v
              REPLICAT
                  |
                  v
       Target Database / Consumer
```

Data Pump process thường được dùng để tách việc đọc redo khỏi việc truyền qua mạng. Nếu mạng hoặc target tạm thời không sẵn sàng, Extract chính vẫn có thể ghi local trail, miễn trail storage đủ chỗ và process được cấu hình phù hợp.

### 5.1. Extract

Extract capture thay đổi từ nguồn. Với Oracle, các chế độ phổ biến là Integrated Extract và Classic Extract, tùy phiên bản, topology và khả năng hỗ trợ.

Integrated Extract phối hợp với database log mining server để đọc redo và tái tạo logical changes. Cơ chế integrated capture được Oracle khuyến nghị cho nhiều triển khai Oracle hiện đại, nhưng vẫn cần kiểm tra compatibility matrix, database version và các loại object/operation được hỗ trợ.

Classic Extract tự xử lý capture từ redo theo cơ chế classic. Nó vẫn xuất hiện trong các môi trường legacy hoặc một số topology được hỗ trợ. Không nên chọn mode chỉ theo thói quen; hãy dựa vào phiên bản, tính năng cần dùng và hướng dẫn triển khai GoldenGate tương ứng.

Extract có thể filter bảng/schema và chọn cột hoặc thao tác cần capture theo parameter file. Ví dụ khái niệm:

```text
EXTRACT ext_orders
USERIDALIAS gg_src
EXTTRAIL ./dirdat/ea
TABLE app.orders;
```

Đây là mẫu cấu hình minh họa cho Classic architecture; cú pháp xác thực, credential store, trail path và parameter phải điều chỉnh theo phiên bản/deployment. Không copy trực tiếp vào production mà chưa kiểm tra cấu hình bảo mật và source requirements.

### 5.2. Trail file

Trail là định dạng file nội bộ của GoldenGate chứa logical change records. Trail giúp tách capture khỏi transport và apply, đồng thời hỗ trợ restart/recovery theo checkpoint.

Trail có thể chứa:

- Metadata về source table và record format.
- Operation type như insert, update, delete.
- Giá trị cột cần thiết theo logging/configuration.
- Transaction boundaries và thông tin thứ tự.
- Timestamp/SCN hoặc thông tin định vị liên quan.

Trail không phải CSV hoặc SQL script. Không chỉnh sửa nội dung trail bằng text editor. Dùng công cụ GoldenGate như `logdump` để inspect trail theo quy trình được hỗ trợ.

Trail file cần được quản lý retention. Xóa trail còn cần cho Extract/Data Pump/Replicat có thể làm mất khả năng tiếp tục. Dọn trail phải dựa trên checkpoint và purge policy của GoldenGate.

### 5.3. Data Pump process

Trong Classic architecture, Data Pump là một Extract process đọc local trail và truyền record đến remote trail. Nó giúp tránh để Extract capture phụ thuộc trực tiếp vào tình trạng mạng/target.

Ví dụ parameter khái niệm:

```text
EXTRACT pump_orders
PASSTHRU
RMTHOST target-host, MGRPORT 7809
RMTTRAIL ./dirdat/rt
TABLE app.orders;
```

`PASSTHRU` có thể dùng trong một số cấu hình để truyền record mà không cần map/transform ở pump. Các tham số thực tế phụ thuộc trail format, credential và version.

### 5.4. Replicat

Replicat đọc trail ở target và apply thay đổi. Các mode thường gặp gồm Classic Replicat, Coordinated Replicat và Integrated Replicat. Integrated Replicat sử dụng apply server của Oracle Database để áp dụng transaction và có thể tận dụng parallelism/commit dependency theo khả năng hỗ trợ.

Ví dụ parameter khái niệm:

```text
REPLICAT rep_orders
USERIDALIAS gg_tgt
MAP app.orders, TARGET dw.orders;
```

Trong môi trường thực tế cần cấu hình mapping, column conversion, error handling, checkpoint table và các tùy chọn apply phù hợp. Integrated Replicat thường được cân nhắc cho Oracle target hiện đại; lựa chọn cụ thể phụ thuộc version và yêu cầu transaction/DDL.

## 6. GoldenGate Microservices Architecture

GoldenGate hiện có kiến trúc Microservices bên cạnh Classic architecture. Tên service và giao diện có thể khác theo release, nhưng các vai trò chính gồm:

| Thành phần | Vai trò khái quát |
|---|---|
| Service Manager | Quản lý deployment và các service trong môi trường Microservices |
| Administration Server | Tạo, cấu hình và quản lý Extract/Replicat cùng process liên quan |
| Distribution Server | Phân phối trail/data từ deployment này sang deployment khác |
| Receiver Server | Nhận trail/data từ Distribution Server |
| Performance Metrics Server | Cung cấp thông tin metrics và giám sát theo deployment |

Trong Microservices, quản trị thường thực hiện qua REST API và browser UI, còn các process capture/apply vẫn thực hiện vai trò logic tương ứng. Cần phân biệt kiến trúc deployment với luồng dữ liệu: Extract capture, trail lưu trữ, Distribution/Receiver chuyển tiếp, Replicat apply.

Không nên trộn các lệnh và parameter của Classic architecture với thao tác Microservices một cách tùy tiện. Hãy dùng tài liệu đúng release và deployment mode.

## 7. Luồng dữ liệu từ source tới target

Một pipeline GoldenGate cơ bản gồm các bước:

1. Transaction thực hiện DML trên source.
2. Oracle ghi redo cần thiết vào online redo log.
3. Extract đọc redo và xác định thay đổi của các bảng được cấu hình.
4. Extract tạo logical change records và ghi vào local trail.
5. Data Pump/Distribution Server truyền trail qua mạng nếu có cấu hình trung gian.
6. Receiver/remote trail nhận record ở target.
7. Replicat đọc trail, map source object sang target object và apply thay đổi.
8. Checkpoint cập nhật vị trí đã xử lý để restart an toàn.

Thứ tự transaction và commit cần được bảo toàn theo cấu hình replication. Replicat không đơn giản chạy một câu SQL độc lập cho mỗi row mà không quan tâm transaction. GoldenGate có các cơ chế xử lý transaction, checkpoint và apply dependency để duy trì consistency trong phạm vi topology được hỗ trợ.

### 7.1. Capture theo transaction

Một transaction nguồn có thể sửa nhiều dòng ở nhiều bảng. CDC cần giữ mối quan hệ giữa những thay đổi thuộc cùng transaction và chỉ apply theo cách bảo đảm tính nhất quán đã thiết kế.

Ví dụ transaction tạo đơn hàng:

```sql
INSERT INTO orders(order_id, customer_id, order_status)
VALUES (1001, 501, 'NEW');

INSERT INTO order_items(order_id, product_id, quantity)
VALUES (1001, 9001, 2);

COMMIT;
```

Nếu downstream cần tính nhất quán giữa `ORDERS` và `ORDER_ITEMS`, việc capture/apply cần giữ transaction boundary và mapping đúng. Nếu downstream chỉ nhận từng row event qua broker, consumer cần biết cách gom transaction hoặc chấp nhận eventual consistency theo hợp đồng dữ liệu.

### 7.2. Checkpoint và restart

Checkpoint ghi nhận vị trí process đã xử lý trong log/trail hoặc target apply. Khi process restart, GoldenGate dùng checkpoint để tiếp tục từ vị trí phù hợp thay vì bắt đầu từ đầu.

Checkpoint không thay thế backup trail hoặc archive log. Nếu file cần thiết bị xóa, checkpoint có thể chỉ ra vị trí mà process muốn đọc nhưng dữ liệu tại vị trí đó không còn. Do đó, retention phải giữ đủ log/trail cho lag, downtime, recovery và thời gian xử lý sự cố dự kiến.

### 7.3. Transaction ordering và parallel apply

Replicat có thể áp dụng song song để tăng throughput. Parallel apply cần tôn trọng dependency giữa các transaction để không phá vỡ consistency. Các transaction độc lập có thể được áp dụng đồng thời; các transaction xung đột hoặc có dependency cần được sắp xếp phù hợp.

Tăng parallelism không phải lúc nào cũng tăng throughput. Target có thể bị giới hạn bởi index contention, foreign key, trigger, redo generation, CPU, I/O hoặc một số transaction dài tạo dependency chain.

## 8. Cấu hình source và target cho GoldenGate

Một triển khai GoldenGate cần chuẩn bị database, quyền, logging và kết nối ở cả source lẫn target.

### 8.1. Chuẩn bị source

Các bước thường gồm:

- Xác nhận database version và GoldenGate release compatibility.
- Bật `ARCHIVELOG` nếu capture mode/topology yêu cầu archived redo.
- Cấu hình supplemental logging phù hợp.
- Bảo đảm redo/archive log được giữ đủ lâu.
- Cấp quyền capture cho GoldenGate user theo script/quyền được Oracle cung cấp cho release.
- Xác định schema/table được capture và các operation cần hỗ trợ.
- Kiểm tra Data Guard, RAC, CDB/PDB hoặc TDE nếu có trong kiến trúc.

Không nên tự tạo một danh sách privilege cố định cho mọi version. Oracle GoldenGate cung cấp các script/procedure cấp quyền theo release và mode. Hãy chạy bằng tài khoản quản trị được phê duyệt và chỉ cấp quyền cần thiết.

### 8.2. Chuẩn bị target

Target cần:

- Schema và bảng đích có cấu trúc tương thích hoặc mapping rõ ràng.
- GoldenGate user có quyền apply trên object đích.
- Checkpoint table nếu mode/deployment yêu cầu.
- Quy tắc xử lý duplicate, constraint và trigger.
- Dung lượng cho trail, report và discard file.
- Chính sách transaction và error handling.

Nếu target đã có dữ liệu trước khi CDC bắt đầu, cần đồng bộ initial load và CDC bằng một SCN hoặc cơ chế instantiation nhất quán.

### 8.3. Ví dụ quản lý process trong Classic architecture

Trong Classic deployment, GGSCI thường được dùng để quản lý process:

```text
GGSCI> INFO ALL
GGSCI> INFO EXTRACT ext_orders, DETAIL
GGSCI> INFO REPLICAT rep_orders, DETAIL
GGSCI> LAG EXTRACT ext_orders
GGSCI> LAG REPLICAT rep_orders
```

Tên lệnh và khả năng có thể khác theo release/deployment. Với Microservices, quản trị thường qua Administration Server/REST API. Không dùng lệnh Classic trên deployment không hỗ trợ.

## 9. Initial load và đồng bộ thay đổi liên tục

Khi target chưa có dữ liệu, CDC không thể chỉ apply các thay đổi mới mà bỏ qua trạng thái hiện có. Cần initial load để tạo baseline, sau đó áp dụng thay đổi phát sinh trong thời gian load.

### 9.1. Vấn đề nhất quán giữa initial load và CDC

Giả sử bắt đầu copy bảng lúc 10:00 và hoàn tất lúc 10:30. Trong khoảng thời gian đó, source vẫn nhận giao dịch. Nếu chỉ copy bảng rồi bắt đầu capture từ 10:30, các thay đổi từ 10:00 đến 10:30 sẽ bị mất. Nếu capture từ trước 10:00 mà không kiểm soát, một số thay đổi có thể được apply trùng với dữ liệu snapshot.

Giải pháp là xác định một vị trí đồng bộ, thường là SCN hoặc cơ chế instantiation được hỗ trợ:

1. Xác định điểm nhất quán `S` trên source.
2. Initial load đọc snapshot dữ liệu tại `S`.
3. Extract capture thay đổi bắt đầu từ `S` hoặc vị trí tương ứng.
4. Load baseline vào target.
5. Replicat apply các thay đổi sau `S` theo thứ tự.

Khi triển khai thật, cần theo đúng quy trình instantiation của GoldenGate version, database version và topology. Không tự chọn một SCN bằng cách lấy `CURRENT_SCN` tùy tiện nếu không bảo đảm snapshot và capture start point tương ứng.

### 9.2. Phương pháp initial load

Một số phương pháp có thể dùng tùy quy mô và yêu cầu downtime:

- SQL-based load bằng `INSERT ... SELECT` hoặc database link.
- Data Pump export/import để chuyển baseline.
- GoldenGate initial load process.
- Backup/restore hoặc storage-level copy trong một số migration architecture.

Initial load cần đối soát số dòng, key, aggregate/checksum và các bảng liên quan. Sau khi baseline hoàn tất, Replicat mới tiếp tục apply trail theo điểm bắt đầu đã xác định.

### 9.3. Đồng bộ lại sau khi mất dữ liệu hoặc lệch target

Nếu target bị lệch hoặc thiếu dữ liệu, cần xác định phạm vi và điểm divergence. Có thể reload một bảng/partition hoặc thực hiện instantiation lại. Không nên xóa trail và reset checkpoint tùy tiện vì có thể làm mất thay đổi chưa apply hoặc apply trùng.

## 10. Mapping, filtering và transformation

GoldenGate có thể map source table sang target table và áp dụng một số phép biến đổi. Ví dụ:

```text
MAP app.orders, TARGET dw.fact_orders;
MAP app.customers, TARGET dw.dim_customers;
```

Mapping cho phép source và target có tên schema/table khác nhau. Có thể cấu hình column mapping khi tên hoặc kiểu cột khác:

```text
MAP app.orders, TARGET dw.fact_orders,
    COLMAP (
        order_key = order_id,
        customer_key = customer_id,
        status_code = order_status
    );
```

Đây là ví dụ parameter file ở dạng khái niệm. Cú pháp cụ thể cần kiểm tra theo GoldenGate release, target type và các quy tắc mapping.

### 10.1. Filtering

Có thể chỉ capture một số bảng hoặc chỉ replicate những dòng thỏa điều kiện. Ví dụ chỉ chuyển đơn hàng của một khu vực hoặc một trạng thái nhất định. Filtering giảm lượng dữ liệu truyền và lưu trữ, nhưng cần xem xét thay đổi điều kiện theo thời gian.

Nếu filter loại bỏ một dòng ở thời điểm insert nhưng sau đó dòng được update để thỏa điều kiện, pipeline cần có logic để nhận biết dòng cần được insert vào target. Ngược lại, nếu dòng đang có ở target sau đó update để không còn thỏa filter, cần xử lý delete/ignore theo semantics đã chọn.

### 10.2. Transformation

GoldenGate hỗ trợ các khả năng mapping/conversion theo release, nhưng không nên đưa toàn bộ logic nghiệp vụ phức tạp vào capture/apply process. Transformation nặng có thể làm tăng lag và khó kiểm thử. Với quy tắc phức tạp, có thể đưa thay đổi thô tới staging/stream processor rồi xử lý ở tầng downstream.

### 10.3. DDL replication

GoldenGate có thể hỗ trợ capture/replication một số DDL tùy database, version, object và cấu hình. DDL replication cần kiểm soát cẩn thận vì schema source và target có thể có khác biệt chủ ý. Không nên bật mọi DDL cho mọi schema nếu target là reporting model đã biến đổi.

## 11. Bảo đảm consistency và xử lý xung đột

GoldenGate thường được dùng cho asynchronous logical replication. Source transaction có thể commit trước khi thay đổi được apply ở target. Vì vậy, target có thể trễ so với source trong một khoảng thời gian.

### 11.1. Eventual consistency

Trong mô hình asynchronous, khi pipeline hoạt động bình thường và không còn lỗi/lag, target sẽ hội tụ về trạng thái tương ứng với các thay đổi đã capture và apply. Nhưng ngay tại một thời điểm, target có thể chưa thấy transaction vừa commit ở source.

Ứng dụng đọc target cần hiểu độ trễ này. Nếu người dùng vừa tạo đơn hàng ở source rồi lập tức truy vấn reporting replica, có thể chưa thấy đơn hàng. Các lựa chọn gồm:

- Đọc lại từ source cho luồng cần read-your-writes.
- Chờ target đạt checkpoint/lag yêu cầu.
- Truyền transaction token/commit position để consumer biết khi nào dữ liệu đã đến.
- Chấp nhận eventual consistency nếu nghiệp vụ cho phép.

### 11.2. Transactional consistency

GoldenGate có thể giữ transaction grouping và commit order trong pipeline theo cấu hình. Nhưng nếu downstream chuyển từng row thành event riêng và xử lý song song, consumer có thể quan sát trạng thái từng phần nếu không gom theo transaction.

Hãy xác định rõ hợp đồng consistency:

- Có cần apply tất cả thay đổi của một source transaction cùng nhau không?
- Có cần giữ thứ tự commit toàn cục hay chỉ theo key/table?
- Có cho phép parallel apply các transaction độc lập không?
- Consumer có cần biết transaction ID/commit timestamp/SCN không?

### 11.3. Conflict trong nhiều nguồn ghi

Mô hình một chiều source-to-target đơn giản hơn active-active replication. Khi nhiều source cùng có thể ghi vào cùng logical row, xung đột có thể xảy ra:

- Hai site cùng update một row.
- Một site delete trong khi site khác update.
- Unique key được sinh trùng.
- Transaction đến target theo thứ tự khác với thứ tự mà nghiệp vụ mong đợi.

GoldenGate có các cơ chế conflict detection/resolution cho những topology và cấu hình hỗ trợ, nhưng không thể tự suy ra quy tắc nghiệp vụ đúng. Cần thiết kế ownership theo key, timestamp/version, site priority hoặc quy tắc merge cụ thể. Tránh multi-master nếu ứng dụng không có quy tắc giải quyết xung đột rõ ràng.

## 12. Monitoring lag và vận hành GoldenGate

CDC chỉ hữu ích nếu có thể biết pipeline đang bắt kịp hay bị trễ. Cần giám sát cả capture, transport và apply.

### 12.1. Các loại lag

| Thành phần | Câu hỏi |
|---|---|
| Extract lag | Capture process chậm bao lâu so với thời điểm thay đổi ở source? |
| Pump/Distribution lag | Trail đang chờ truyền bao lâu? |
| Replicat lag | Target apply chậm bao lâu so với commit ở source? |
| End-to-end latency | Từ source commit đến khi target có thể đọc dữ liệu mất bao lâu? |

Lag không chỉ là một con số. Cần xem throughput, backlog/trail size, transaction lớn, process status và thời điểm gần nhất apply thành công.

### 12.2. Lệnh và giao diện theo dõi

Trong Classic architecture, GGSCI có các lệnh như:

```text
GGSCI> INFO ALL
GGSCI> INFO EXTRACT ext_orders, DETAIL
GGSCI> INFO REPLICAT rep_orders, DETAIL
GGSCI> LAG EXTRACT ext_orders
GGSCI> LAG REPLICAT rep_orders
GGSCI> STATS EXTRACT ext_orders, TOTAL
GGSCI> STATS REPLICAT rep_orders, TOTAL
```

Trong Microservices, có thể xem process status, lag, throughput và report qua Administration Server/Performance Metrics Server hoặc REST API theo release. Không nên phụ thuộc vào một câu lệnh duy nhất; cần alert khi process abended, trail storage tăng nhanh hoặc lag vượt ngưỡng SLA.

### 12.3. Checkpoint và heartbeat

Checkpoint giúp biết process đã capture hoặc apply đến vị trí nào. Một số cấu hình Replicat dùng checkpoint table trong target database. Heartbeat table có thể ghi nhận timestamp hoặc vị trí của các batch thay đổi để đo end-to-end latency và phát hiện pipeline không còn cập nhật.

Heartbeat cần được cấu hình và bảo trì đúng. Nếu clock giữa source và target không đồng bộ, phép đo dựa trên timestamp có thể sai. Có thể dùng SCN/commit position hoặc các metric mà GoldenGate cung cấp khi phù hợp.

### 12.4. Dung lượng trail và archive log

Khi target dừng hoặc mạng bị lỗi, trail backlog tăng. Nếu không có đủ dung lượng, Extract hoặc pump có thể dừng. Source archive logs cũng phải được giữ đủ lâu để Extract tiếp tục sau downtime.

Capacity planning cần xét:

- Peak redo generation rate.
- Tỷ lệ redo thuộc các bảng được capture.
- Thời gian target có thể ngừng.
- Thời gian cần để catch up sau khi phục hồi.
- Số trail copy/route và retention.
- Dung lượng archive log và chính sách backup/purge.

Không xóa trail hoặc archive log thủ công chỉ để giải phóng disk. Dùng purge/checkpoint mechanism và xác định process nào còn cần file.

## 13. Error handling và phục hồi pipeline

Replicat có thể gặp lỗi khi target constraint từ chối dòng, mapping sai kiểu, target object không tồn tại hoặc dữ liệu đã được apply trước đó. Extract có thể lỗi do thiếu log, quyền hoặc unsupported operation. Mỗi loại lỗi cần cách xử lý khác nhau.

### 13.1. Discard file và error handling

Discard file có thể ghi các record không được apply theo cấu hình. Report file và process log cung cấp thông tin về lỗi. Không nên cấu hình bỏ qua mọi lỗi chỉ để process tiếp tục chạy; làm vậy có thể tạo target thiếu dữ liệu mà không ai nhận ra.

Nếu cần skip một transaction, phải ghi lại transaction identity, lý do, phạm vi dữ liệu và kế hoạch reconcile. Skip là một quyết định vận hành có tác động đến consistency.

### 13.2. Restart process

Khi process dừng, kiểm tra report, error code, checkpoint, trail file và tình trạng database trước khi restart. Nếu chỉ là lỗi tạm thời, restart từ checkpoint có thể tiếp tục. Nếu trail thiếu hoặc target đã bị chỉnh sửa thủ công, cần đánh giá khả năng duplicate hoặc gap trước khi chạy lại.

### 13.3. Idempotency và duplicate handling

CDC pipeline có thể phải retry khi network hoặc process lỗi. Consumer nên thiết kế idempotent nếu có thể: cùng một change event được xử lý lại không tạo thêm tác dụng phụ ngoài ý muốn.

Với database target, primary key/unique constraint và cơ chế checkpoint giúp kiểm soát apply. Với event consumer, có thể lưu event ID/transaction key đã xử lý hoặc dùng upsert theo khóa nghiệp vụ. Không nên dựa vào giả định “mỗi event chỉ đến đúng một lần” nếu transport/consumer có thể retry.

## 14. Oracle Data Guard là gì?

Oracle Data Guard duy trì một hoặc nhiều standby database để bảo vệ primary database. Primary gửi redo tới standby; standby nhận redo và apply để duy trì trạng thái gần với primary.

Mục tiêu chính của Data Guard là high availability, data protection và disaster recovery. Khi primary gặp sự cố, standby có thể được chuyển thành primary bằng failover. Khi cần bảo trì có kế hoạch, switchover cho phép đổi vai trò primary/standby theo quy trình.

### 14.1. Primary và standby

```text
           Primary Database
                  |
              Redo Transport
                  |
                  v
           Standby Database
                  |
              Redo Apply
                  |
                  v
        Database gần với Primary
```

Standby có thể là physical standby hoặc logical standby, tùy cấu hình và mục tiêu. Active Data Guard là tùy chọn/khả năng bổ sung cho một số workload read-only trên physical standby và chịu điều kiện license tương ứng.

### 14.2. Physical standby

Physical standby duy trì bản sao vật lý của primary ở mức block. Redo được apply bằng Redo Apply để standby phản ánh thay đổi của primary. Physical standby thường phù hợp cho DR vì cấu trúc database được duy trì tương ứng với primary.

### 14.3. Logical standby

Logical standby sử dụng SQL Apply để chuyển redo thành các thay đổi SQL logic. Nó có thể mở database cho một số hoạt động đọc/ghi được hỗ trợ và có một số giới hạn object/data type. Logical standby không tương đương GoldenGate; nó là một loại standby database trong Data Guard.

### 14.4. Redo transport và apply

Primary truyền redo tới standby bằng các transport service. Standby nhận redo vào standby redo log hoặc archive log và apply theo chế độ cấu hình. Có thể chọn synchronous/asynchronous transport và protection mode phù hợp với mục tiêu RPO, latency và khoảng cách.

## 15. GoldenGate và Data Guard khác nhau thế nào?

Hai công nghệ đều có thể sử dụng redo và truyền thay đổi, nhưng chúng giải quyết mục tiêu khác nhau.

| Tiêu chí | Oracle GoldenGate | Oracle Data Guard |
|---|---|---|
| Mục tiêu chính | Logical replication, CDC và phân phối dữ liệu | High availability, data protection và disaster recovery |
| Đơn vị đồng bộ | Logical changes như insert/update/delete theo object | Redo và trạng thái database standby |
| Target | Có thể là database khác, schema khác hoặc nền tảng được hỗ trợ | Standby database của primary |
| Schema mapping | Có thể map tên schema/table/cột và transform | Physical standby giữ cấu trúc vật lý tương ứng; logical standby có quy tắc SQL Apply riêng |
| Filtering | Có thể chọn bảng, operation và dòng theo cấu hình | Không phải công cụ phân phối subset dữ liệu theo mô hình CDC thông thường |
| Heterogeneous replication | Có thể hỗ trợ nhiều nền tảng khác nhau theo release | Chủ yếu bảo vệ database Oracle trong Data Guard configuration |
| Độ trễ | Thường asynchronous, phụ thuộc capture/transport/apply | Có synchronous/asynchronous redo transport và apply lag |
| Failover database role | Không thay thế Data Guard role transition | Hỗ trợ switchover/failover giữa primary và standby |
| Conflict handling | Cần thiết kế cho multi-source/active-active topology | Không phải mô hình multi-master conflict resolution |
| Use case | DWH, integration, migration, reporting copy, CDC feed | DR site, HA database, data protection |

### 15.1. Ví dụ chọn công nghệ

**Tình huống A: Cần có standby database để chuyển đổi khi primary site mất.** Data Guard thường là lựa chọn phù hợp vì mục tiêu là duy trì database standby có thể đảm nhận vai trò primary.

**Tình huống B: Cần chuyển một số bảng từ Oracle sang một nền tảng dữ liệu khác để phân tích.** GoldenGate phù hợp hơn vì có thể capture thay đổi theo object và chuyển logical records tới target được hỗ trợ.

**Tình huống C: Cần migration sang database mới với downtime thấp.** GoldenGate có thể đồng bộ thay đổi liên tục sau initial load, giúp target bắt kịp source trước cutover. Cần có kế hoạch kiểm tra dữ liệu và dừng ghi ở thời điểm chuyển đổi.

**Tình huống D: Cần vừa có HA/DR cho database giao dịch, vừa có data warehouse cập nhật gần thời gian thực.** Có thể dùng Data Guard cho standby/DR và GoldenGate để cấp thay đổi cho warehouse. Hai luồng cần được thiết kế về tài nguyên, logging, network và điểm nguồn phù hợp.

## 16. Có thể kết hợp GoldenGate với Data Guard không?

Có. Một kiến trúc thường gặp là primary database có RAC ở site chính, Data Guard standby ở site dự phòng, và GoldenGate capture/replicate thay đổi đến reporting hoặc warehouse platform.

```text
                    Ứng dụng OLTP
                          |
                          v
                 Primary Oracle RAC
                          |
               +----------+----------+
               |                     |
               v                     v
         Data Guard redo       GoldenGate Extract
               |                     |
               v                     v
        Standby Database          Trail / Pump
                                     |
                                     v
                              GoldenGate Replicat
                                     |
                                     v
                             Data Warehouse
```

Data Guard bảo vệ database bằng standby. GoldenGate cung cấp logical changes tới warehouse. Nếu source là RAC hoặc có Data Guard role transition, cần xác định GoldenGate capture sẽ chạy ở đâu, cách xử lý role change và cách tránh capture trùng hoặc gap khi primary chuyển sang standby khác.

Không nên giả định GoldenGate tự động chuyển capture sang Data Guard standby trong mọi cấu hình. Cần dùng kiến trúc và thủ tục failover/switchover được Oracle hỗ trợ cho phiên bản đang triển khai.

## 17. GoldenGate trong môi trường RAC và Data Guard

GoldenGate có thể triển khai với Oracle RAC và Data Guard, nhưng cần hiểu redo thread, archive log và instance topology.

### 17.1. RAC source

RAC có nhiều redo thread, mỗi instance ghi redo vào thread của mình. Extract phải đọc đủ redo cần thiết từ các thread liên quan để capture thay đổi của database. Cấu hình access tới online/archive logs và shared storage cần đáp ứng kiến trúc RAC.

Nếu một instance lỗi, cần bảo đảm Extract có thể tiếp tục từ log còn lại và các archive log cần thiết. Monitoring phải theo dõi capture lag và trạng thái process trên toàn cluster.

### 17.2. Data Guard source

Nếu GoldenGate capture từ primary database có Data Guard standby, cần xác định capture mode và vị trí đọc redo. Một số cấu hình có thể capture từ standby để giảm tải primary, nhưng hỗ trợ phụ thuộc GoldenGate/database release, role, standby type và các điều kiện được Oracle công bố.

Không nên tự chuyển Extract sang standby chỉ vì standby có redo. Hãy kiểm tra yêu cầu supplemental logging, access to redo, database role, licensing và các giới hạn cụ thể của release.

### 17.3. Role transition

Khi Data Guard switchover/failover, database role thay đổi. GoldenGate cần được cấu hình để biết source mới, khôi phục capture position và duy trì không mất/không lặp thay đổi ngoài ý muốn. Runbook phải bao gồm:

- Xác định database nào là primary sau chuyển đổi.
- Xác định Extract đang capture ở đâu và trạng thái checkpoint.
- Kiểm tra archive/redo availability.
- Khởi động hoặc chuyển process theo kiến trúc được hỗ trợ.
- Kiểm tra trail continuity và Replicat lag.
- Đối soát dữ liệu sau khi pipeline hoạt động lại.

## 18. CDC và migration gần như không downtime

GoldenGate thường được dùng để giảm downtime khi chuyển database hoặc nâng cấp nền tảng.

Một luồng migration tổng quát:

1. Chuẩn bị target schema, quyền và GoldenGate.
2. Bật supplemental logging và bắt đầu capture ở source tại một điểm nhất quán.
3. Thực hiện initial load source sang target.
4. Replicat apply các thay đổi phát sinh trong lúc initial load.
5. Theo dõi lag đến khi target bắt kịp.
6. Kiểm tra số dòng, checksum, constraint và dữ liệu nghiệp vụ.
7. Chọn thời điểm cutover, tạm dừng ghi ở source hoặc dùng quy trình đồng bộ cuối.
8. Chờ Replicat apply hết backlog và xác nhận target nhất quán.
9. Chuyển ứng dụng sang target.
10. Giám sát sau cutover và giữ phương án rollback theo thời hạn đã thống nhất.

Downtime thấp không có nghĩa downtime bằng zero. Cần thời gian chặn ghi hoặc chuyển write ownership để bảo đảm không có hai nguồn cùng nhận giao dịch ngoài thiết kế.

### 18.1. Kiểm tra dữ liệu trước cutover

Không nên chỉ nhìn lag bằng zero rồi kết luận target hoàn toàn đúng. Cần kiểm tra:

- Row count theo bảng và partition.
- Aggregate theo key nghiệp vụ.
- Checksum/hash theo chunk hoặc key range.
- Missing/duplicate primary key.
- Foreign key và quan hệ dữ liệu.
- Các transaction cuối cùng ở source.
- Sequence, identity, database link, job, trigger và dependency liên quan.

### 18.2. Cutover và rollback

Cutover cần xác định rõ thời điểm source ngừng nhận write, target bắt đầu nhận write và cách xử lý kết nối cũ. Sau khi target đã nhận write mới, rollback về source không còn là thao tác đơn giản nếu thay đổi ở target chưa được đồng bộ ngược. Cần định nghĩa cửa sổ rollback và chiến lược reverse replication nếu yêu cầu.

## 19. Bảo mật và quản trị GoldenGate

GoldenGate có quyền đọc redo, truy cập object nguồn, ghi trail và apply dữ liệu đích. Vì vậy, credential và quyền của GoldenGate user cần được bảo vệ như quyền dịch vụ database quan trọng.

Các nguyên tắc:

- Dùng dedicated GoldenGate user, không dùng `SYS` hoặc schema ứng dụng làm tài khoản vận hành thường xuyên.
- Cấp quyền theo script/quy trình của đúng GoldenGate release và capture/apply mode.
- Lưu credential trong credential store/secret mechanism được hỗ trợ; tránh ghi password rõ trong parameter file.
- Bảo vệ trail file, report, log và discard file vì chúng có thể chứa dữ liệu nhạy cảm.
- Mã hóa kết nối/transport khi yêu cầu bảo mật mạng.
- Giới hạn quyền OS đối với thư mục GoldenGate và file trail.
- Phân quyền riêng cho operator, administrator và người xem metrics.
- Audit các thay đổi parameter, process start/stop, skip transaction và thao tác purge.

## 20. Các rủi ro và giới hạn cần hiểu

CDC và GoldenGate không tự động giải quyết mọi bài toán đồng bộ:

- **Unsupported object/operation:** một số datatype, object, DDL hoặc thao tác đặc biệt có giới hạn theo release.
- **Large transaction:** transaction rất lớn có thể làm tăng memory, trail backlog và apply latency.
- **LOB:** cần kiểm tra cấu hình và giới hạn capture/apply với loại LOB và thao tác cụ thể.
- **DDL drift:** schema source/target khác nhau có thể khiến apply lỗi.
- **Keyless table:** thiếu khóa duy nhất làm định danh row khó và tăng supplemental logging.
- **Target contention:** nhiều transaction apply song song có thể tranh chấp index/constraint.
- **Long-running transaction:** thay đổi chưa commit có thể chưa được phát ra target dù redo đã được tạo.
- **Trail/archive retention:** thiếu log có thể khiến capture không thể tiếp tục từ checkpoint.
- **Network outage:** backlog tăng và target có thể trễ lâu sau khi mạng phục hồi.
- **Duplicate/replay:** retry hoặc re-instantiation cần quy trình idempotent và checkpoint chính xác.

Trước khi triển khai, lập compatibility matrix theo database version, GoldenGate version, platform, character set, encryption, topology và datatype. Chạy proof-of-concept với workload thật thay vì dựa vào một ví dụ đơn giản.

## 21. Quy trình thiết kế một pipeline CDC

Một quy trình triển khai có thể đi theo các bước:

1. **Xác định mục tiêu:** target dùng cho DR, reporting, integration, migration hay event feed?
2. **Chọn semantics:** cần logical replication, physical standby hay chỉ snapshot/polling?
3. **Xác định nguồn và đích:** database version, schema, datatype, key, volume và network.
4. **Chọn capture mode:** log-based, trigger/polling hoặc GoldenGate integrated/classic theo hỗ trợ.
5. **Chuẩn bị logging:** ARCHIVELOG, supplemental logging, archive retention và quyền capture.
6. **Thiết kế initial load:** chọn SCN/instantiation point và phương pháp baseline.
7. **Thiết kế mapping:** table/column mapping, filter, transform và DDL policy.
8. **Thiết kế apply:** integrated/classic/coordinated Replicat, checkpoint và transaction semantics.
9. **Thiết kế lỗi và retry:** discard, error handling, skip policy, idempotency và reconcile.
10. **Thiết kế monitoring:** lag, throughput, process status, trail/archive capacity và alert.
11. **Kiểm thử failure:** source restart, network outage, target outage, process abend và role transition.
12. **Kiểm thử cutover/recovery:** xác nhận dữ liệu và quy trình quay lại.

## 22. Bài thực hành: đồng bộ bảng ORDERS sang reporting database

Giả sử `APP.ORDERS` ở source cần được replicate sang `REPORTING.ORDERS` ở target để phục vụ báo cáo. Source và target đều là Oracle Database; deployment dùng GoldenGate Classic để minh họa luồng process.

### Bước 1: Xác nhận bảng có khóa chính

```sql
SELECT constraint_name,
       constraint_type,
       status
FROM user_constraints
WHERE table_name = 'ORDERS';
```

Kiểm tra `ORDER_ID` có primary key hoặc unique key phù hợp. Nếu không có khóa, cần thiết kế key/supplemental logging trước khi capture.

### Bước 2: Bật supplemental logging theo yêu cầu

```sql
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA;
ALTER TABLE app.orders
ADD SUPPLEMENTAL LOG DATA (PRIMARY KEY) COLUMNS;
```

Các lệnh cần được thực hiện bởi tài khoản có quyền và xác nhận phù hợp với cấu hình capture.

### Bước 3: Tạo target table

Target cần có cấu trúc tương thích hoặc mapping đã được xác định. Có thể tạo baseline bằng Data Pump/SQL hoặc phương pháp initial load được chọn.

### Bước 4: Cấu hình Extract

Parameter minh họa:

```text
EXTRACT ext_orders
USERIDALIAS gg_src
EXTTRAIL ./dirdat/ea
TABLE app.orders;
```

### Bước 5: Cấu hình Data Pump

```text
EXTRACT pump_orders
PASSTHRU
RMTHOST target-host, MGRPORT 7809
RMTTRAIL ./dirdat/rt
TABLE app.orders;
```

### Bước 6: Cấu hình Replicat

```text
REPLICAT rep_orders
USERIDALIAS gg_tgt
MAP app.orders, TARGET reporting.orders;
```

Các file parameter trên chỉ là skeleton để hiểu mapping. Cần bổ sung credential, checkpoint, error handling, trail format, process group và các thiết lập bảo mật theo deployment thật.

### Bước 7: Initial load và bắt đầu CDC

Chọn điểm SCN/instantiation nhất quán. Nạp baseline vào `REPORTING.ORDERS`, sau đó khởi động Replicat từ trail position tương ứng. Không bắt đầu apply từ một vị trí tùy ý.

### Bước 8: Kiểm tra kết quả

So sánh số dòng và aggregate:

```sql
SELECT COUNT(*) AS row_count,
       SUM(total_amount) AS total_amount
FROM app.orders;
```

```sql
SELECT COUNT(*) AS row_count,
       SUM(total_amount) AS total_amount
FROM reporting.orders;
```

Hai truy vấn chỉ là đối soát đơn giản. Nếu source tiếp tục có giao dịch trong lúc đối chiếu, kết quả có thể khác do replication lag. Cần chọn một điểm snapshot hoặc tạm dừng write để so sánh chính xác.

### Bước 9: Theo dõi lag và process

```text
GGSCI> INFO ALL
GGSCI> LAG EXTRACT ext_orders
GGSCI> LAG REPLICAT rep_orders
GGSCI> STATS REPLICAT rep_orders, TOTAL
```

Đặt alert cho process abend, lag vượt SLA, trail disk gần đầy và archive log retention không đủ.

## 23. Checklist chọn giữa GoldenGate, Data Guard và CDC đơn giản

| Câu hỏi | Hướng lựa chọn thường gặp |
|---|---|
| Cần standby database để failover khi site chính lỗi? | Data Guard |
| Cần replicate một tập bảng sang hệ thống khác? | GoldenGate hoặc CDC platform phù hợp |
| Cần chuyển dữ liệu Oracle sang nền tảng khác? | GoldenGate nếu target được hỗ trợ |
| Cần migration với thời gian dừng ghi ngắn? | GoldenGate kết hợp initial load và cutover |
| Chỉ cần đồng bộ một bảng nhỏ mỗi giờ? | Polling có thể đủ đơn giản |
| Cần audit một số thay đổi cục bộ trong cùng transaction? | Trigger/change table có thể phù hợp |
| Cần bảo vệ database khỏi mất site và đồng thời cấp dữ liệu cho warehouse? | Data Guard kết hợp GoldenGate |
| Cần multi-master với nhiều site cùng ghi? | Chỉ chọn khi có thiết kế conflict/ownership rõ ràng và topology được hỗ trợ |

## 24. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| CDC chỉ là polling theo `UPDATED_AT` | CDC có thể dựa trên log, trigger hoặc polling; log-based capture có thể nhận cả delete và transaction metadata |
| GoldenGate là Data Guard | GoldenGate logical replication/CDC; Data Guard duy trì standby database cho HA/DR |
| Data Guard là công cụ chọn một vài bảng để replicate | Data Guard bảo vệ database ở cấp standby, không phải table-level distribution thông thường |
| GoldenGate chỉ copy toàn bộ bảng | GoldenGate có thể capture thay đổi liên tục và filter/map theo cấu hình |
| Trail file là CSV hoặc SQL script | Trail là định dạng nội bộ GoldenGate, cần dùng công cụ phù hợp để inspect |
| GoldenGate Data Pump là `expdp` | Data Pump process của GoldenGate chuyển trail; Oracle Data Pump là utility export/import riêng |
| Target luôn đồng bộ ngay sau source commit | Asynchronous pipeline có replication lag; cần định nghĩa consistency SLA |
| Bật supplemental logging không có chi phí | Redo tăng; cần chọn mức logging phù hợp |
| Replicat lỗi có thể skip mọi transaction | Skip có thể làm target lệch; phải ghi nhận và reconcile |
| Zero lag nghĩa target đã được kiểm chứng hoàn toàn | Lag là metric thời gian/vị trí, không thay thế đối soát dữ liệu |
| Multi-master tự giải quyết conflict | Cần quy tắc ownership và conflict resolution rõ ràng |
| GoldenGate thay thế backup | GoldenGate không thay thế backup/restore và chiến lược DR |

Change Data Capture giúp hệ thống chỉ chuyển những thay đổi cần thiết thay vì liên tục đọc lại toàn bộ dữ liệu. Oracle GoldenGate cung cấp pipeline logical replication với capture, trail, transport và apply; redo và supplemental logging là nền tảng quan trọng cho capture từ Oracle Database. Oracle Data Guard phục vụ mục tiêu khác: duy trì standby database để bảo vệ dữ liệu và chuyển đổi vai trò khi có sự cố. Chọn đúng công nghệ đòi hỏi xác định rõ mục tiêu, consistency, độ trễ, topology, khả năng tương thích và quy trình vận hành; nhiều kiến trúc cần kết hợp GoldenGate với Data Guard thay vì coi chúng là hai lựa chọn thay thế hoàn toàn.
