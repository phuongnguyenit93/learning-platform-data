# Đồng bộ dữ liệu, đối soát và chuyển nguồn ghi

Di chuyển một ứng dụng sang serverless thường kéo theo thay đổi cách lưu trữ và xử lý dữ liệu. Một hệ thống cũ có thể đang ghi vào database của monolith, trong khi các Java function mới chạy trên nền tảng serverless cần đọc và ghi vào database hoặc datastore mới. Trong giai đoạn chuyển tiếp, hai môi trường phải cùng tồn tại: ứng dụng cũ vẫn phục vụ người dùng, function mới được triển khai dần, và dữ liệu tiếp tục thay đổi mỗi giây.

Thách thức lớn nhất không chỉ là sao chép dữ liệu ban đầu. Hệ thống phải bắt kịp mọi thay đổi phát sinh trong lúc sao chép, xử lý message trùng hoặc đến sai thứ tự, chứng minh dữ liệu đích tương đương dữ liệu nguồn, rồi chuyển quyền ghi mà không tạo hai nguồn sự thật. Nếu chỉ đổi connection string sang database mới, có thể mất các cập nhật cuối, ghi trùng, hoặc rollback về hệ thống cũ trong khi dữ liệu mới đã phát sinh ở đích.

Bài học này tập trung vào quy trình **baseline snapshot → change data capture (CDC) → reconciliation → cutover** cho ứng dụng serverless. Bạn sẽ học cách giữ checkpoint, áp dụng thay đổi idempotent, đối soát ở cùng một mốc dữ liệu, quản lý write ownership, chuyển nguồn ghi theo từng bước và xây kế hoạch rollback dựa trên trạng thái dữ liệu thực tế.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Lập kế hoạch di chuyển dữ liệu khi monolith và serverless cùng hoạt động.
- Phân biệt baseline snapshot, CDC, replication và application-level dual-write.
- Chọn một điểm bắt đầu CDC không tạo khoảng trống giữa snapshot và change stream.
- Thiết kế consumer áp dụng change event có checkpoint, ordering và idempotency.
- Xử lý insert, update, delete, schema change và dữ liệu đến trễ.
- Đối soát row count, checksum theo partition và các invariant nghiệp vụ.
- Chuyển quyền ghi bằng write fence và một mốc cutover có thể kiểm chứng.
- Xây phương án rollback khi target đã nhận write mới.
- Kiểm soát tải đồng bộ, database connection, retry và backpressure trong serverless.
- Dùng Java để mô hình hóa change event, apply ledger và reconciliation result.

## 1. Bài toán di chuyển dữ liệu khi hệ thống vẫn phục vụ

Giả sử một ứng dụng thương mại điện tử hiện chạy trong monolith. Orders, customers và inventory nằm trong database cũ. Đội phát triển muốn chuyển dần API tạo đơn và xử lý event sang các Java function. Database mới có thể là managed relational database, document store hoặc datastore được chọn cho workload serverless.

Trong quá trình migration có ba luồng hoạt động:

1. **Ứng dụng cũ** tiếp tục nhận request và ghi vào nguồn hiện tại.
2. **Đồng bộ dữ liệu** sao chép baseline và chuyển tiếp các thay đổi từ nguồn sang đích.
3. **Ứng dụng mới** được triển khai, kiểm thử và dần nhận traffic; ban đầu thường chỉ đọc shadow hoặc đọc thử từ target.

~~~mermaid
flowchart LR
    U["Users / upstream systems"] --> OLD["Legacy application"]
    OLD --> SRC[("Source database")]
    SRC --> SNAP["Consistent snapshot"]
    SRC --> CDC["CDC change stream"]
    SNAP --> LOAD["Baseline loader"]
    LOAD --> DST[("Target database")]
    CDC --> APPLY["Idempotent CDC applier"]
    APPLY --> DST
    DST --> NEW["Serverless Java functions"]
    NEW --> U
~~~

Mục tiêu migration không đơn giản là “copy đủ bảng”. Cần giữ được các thuộc tính sau:

- Không bỏ sót thay đổi đã commit ở nguồn.
- Không áp dụng một thay đổi nhiều lần thành nhiều side effect.
- Bảo toàn thứ tự cần thiết của thay đổi trên cùng một entity.
- Dữ liệu đích phản ánh đúng trạng thái nguồn tại một mốc xác định.
- Chỉ có một nơi được quyền nhận write nghiệp vụ tại một thời điểm, trừ khi đã thiết kế một giao thức multi-writer có kiểm soát.
- Có thể dừng, tiếp tục, đối soát và khôi phục tiến trình migration.

### Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa |
|---|---|
| Baseline snapshot | Ảnh chụp nhất quán của dữ liệu tại một thời điểm hoặc transaction snapshot |
| CDC | Luồng thay đổi insert/update/delete sau một vị trí log xác định |
| Checkpoint/watermark | Vị trí đã đọc hoặc áp dụng thành công trong change stream |
| Reconciliation | So sánh dữ liệu và invariant giữa nguồn với đích |
| Write ownership | Hệ thống đang có quyền chấp nhận write nghiệp vụ |
| Cutover | Chuyển traffic và quyền ghi sang target theo một mốc được kiểm chứng |
| Rollback | Khôi phục hoạt động về hệ thống trước đó với dữ liệu không bị mất hoặc ghi phân nhánh |

## 2. Chọn chiến lược đồng bộ

Có nhiều cách đưa dữ liệu từ nguồn sang đích. Chọn chiến lược theo downtime cho phép, kích thước dữ liệu, khả năng CDC, yêu cầu consistency và khả năng chuyển đổi ngược.

| Chiến lược | Cách hoạt động | Phù hợp | Rủi ro/chú ý |
|---|---|---|---|
| Offline migration | Dừng write, export/import, xác minh rồi mở hệ thống mới | Dataset nhỏ hoặc chấp nhận downtime | Downtime phụ thuộc thời gian copy và kiểm thử |
| Snapshot + CDC | Copy baseline, sau đó áp dụng thay đổi liên tục | Hệ thống cần downtime thấp | Cần quản lý log position, ordering và lag |
| Application dual-write | Ứng dụng ghi cả source và target | Một số giai đoạn chuyển đổi có kiểm soát | Hai write không nguyên tử; dễ lệch dữ liệu |
| Outbox + replication consumer | Ghi business state và outbox cùng transaction, worker cập nhật target | Có thể sửa ứng dụng nguồn | Cần schema/event contract và replay |
| Change log/CDC từ database | Đọc transaction log của nguồn rồi áp dụng ở đích | Muốn giảm sửa đổi code legacy | Cần kiểm soát schema, log retention và quyền đọc |

### Vì sao snapshot đơn lẻ thường không đủ?

Nếu copy bảng orders lúc 10:00 và tiếp tục nhận write đến 10:30, snapshot không chứa các đơn tạo sau 10:00. Nếu chỉ chạy CDC sau khi copy xong, thay đổi xảy ra trong khoảng copy có thể bị bỏ sót.

Cách phổ biến là xác định một CDC start position trước hoặc đồng bộ với snapshot boundary, lấy snapshot nhất quán tại boundary đó, rồi replay mọi thay đổi sau boundary. Cơ chế cụ thể phụ thuộc database và công cụ migration: có hệ thống cung cấp consistent snapshot kèm log position; có hệ thống cần khởi động capture trước, giữ log đủ lâu và dùng checkpoint do công cụ trả về.

Không tự ghép một timestamp từ ứng dụng với một log offset rồi coi chúng là cùng mốc. Dùng snapshot/CDC coordination mechanism được database hoặc replication tool hỗ trợ.

### CDC không phải event nghiệp vụ

CDC thường phản ánh thay đổi ở cấp database row/transaction. Event nghiệp vụ như `OrderPaid` thể hiện ý nghĩa của hành động. Một row update từ `PENDING` sang `PAID` không nhất thiết cung cấp đầy đủ lý do, actor, policy hoặc context nghiệp vụ.

Dùng CDC để di chuyển trạng thái dữ liệu khi phù hợp. Dùng domain event/outbox khi consumer cần hiểu ý nghĩa nghiệp vụ. Không phát domain event bằng cách suy đoán từ mọi row update nếu không có quy tắc mapping rõ ràng.

## 3. Lập kế hoạch baseline snapshot và CDC boundary

Quy trình snapshot + CDC cần bảo đảm không có khoảng trống:

~~~mermaid
sequenceDiagram
    participant S as Source database
    participant M as Migration tool
    participant T as Target database
    M->>S: Establish consistent snapshot and log position L0
    S-->>M: Snapshot at boundary L0
    M->>T: Load baseline rows
    M->>S: Read changes after L0
    S-->>M: CDC transactions L1, L2, L3...
    M->>T: Apply changes in order
    Note over M,T: Continue until target catches up
~~~

Các bước tổng quát:

1. Kiểm tra source database có bật log/CDC và retention đủ dài.
2. Xác định snapshot mode và vị trí log tương ứng do công cụ hỗ trợ.
3. Bắt đầu capture thay đổi theo đúng cơ chế của công cụ.
4. Lấy snapshot nhất quán và ghi nhận boundary `L0`.
5. Nạp snapshot vào target theo batch có thể resume.
6. Đọc CDC sau `L0`, áp dụng theo transaction/order semantics.
7. Lưu checkpoint sau khi batch/transaction đã được áp dụng bền vững.
8. Theo dõi replication lag cho đến khi gần zero.
9. Đối soát tại một mốc có thể xác định trước cutover.

Tên vị trí log khác nhau theo database, ví dụ LSN, SCN, binlog position hoặc stream sequence. Không so sánh trực tiếp offset giữa hai database khác nhau. Checkpoint của CDC là vị trí trong log nguồn; nó không phải primary key hoặc timestamp của row.

### Snapshot consistency

Snapshot phải đại diện cho một trạng thái dữ liệu nhất quán. Nếu export từng bảng ở những thời điểm khác nhau trong khi transaction đang cập nhật nhiều bảng, target có thể chứa một order đã được tạo nhưng thiếu order lines hoặc payment record tương ứng.

Dùng consistent snapshot, transaction isolation hoặc migration tool có khả năng phối hợp snapshot theo database. Với dataset rất lớn, snapshot có thể chia chunk/partition; cần bảo đảm mọi chunk cùng thuộc một snapshot boundary hoặc có cách áp dụng CDC để bù các thay đổi phát sinh trong lúc đọc.

### Log retention và tốc độ copy

Nguồn phải giữ transaction log lâu hơn thời gian snapshot, load và catch-up cần thiết. Nếu CDC consumer chậm đến mức log position đã bị purge, có thể phải khởi tạo lại snapshot hoặc dùng cơ chế recovery được công cụ hỗ trợ.

Ước lượng sơ bộ:

~~~text
required source log retention
  > snapshot duration
    + target load duration
    + expected catch-up duration
    + recovery margin
~~~

Đây là ước lượng vận hành. Cần đo tốc độ phát sinh log, tốc độ copy, throughput apply và khả năng lưu log thực tế của database.

## 4. Thiết kế change event và thứ tự áp dụng

CDC record thường cần metadata đủ để xác định nguồn, transaction và row:

- Source database/table hoặc stream.
- Primary key của row.
- Operation: INSERT, UPDATE hoặc DELETE.
- Before/after image theo cấu hình capture.
- Commit position hoặc transaction sequence.
- Schema/table version nếu có.
- Transaction boundary và thứ tự trong transaction.
- Snapshot marker nếu record thuộc baseline.

Một mô hình Java minh họa:

~~~java
import java.util.Map;

public enum ChangeOperation {
    INSERT,
    UPDATE,
    DELETE
}

public record SourcePosition(
        String stream,
        String transactionId,
        String commitPosition,
        int eventSequence) {
}

public record RowChange(
        String table,
        String primaryKey,
        ChangeOperation operation,
        Map<String, Object> afterImage,
        SourcePosition position,
        int schemaVersion) {
}
~~~

Đây là mô hình trung lập. Adapter CDC thực tế cần map metadata của database/tool vào object này. Không giả định mọi connector cung cấp before image, transaction ID hoặc cùng semantics của sequence.

### Thứ tự toàn cục và thứ tự theo entity

Một số database log có thứ tự transaction toàn cục; một số stream chia partition/shard và chỉ bảo đảm thứ tự trong một partition. Nếu các update cho cùng order có thể đi qua nhiều partition, target có thể áp dụng phiên bản cũ sau phiên bản mới.

Các lựa chọn:
- Partition theo primary key/aggregate ID nếu connector và broker hỗ trợ.
- Dùng version/commit sequence để từ chối stale update.
- Giữ transaction ordering khi nhiều row phải thay đổi cùng nhau.
- Chạy một applier tuần tự cho phạm vi cần strict ordering.
- Chỉ song song hóa các partition độc lập.

Không cần strict global ordering nếu nghiệp vụ không phụ thuộc thứ tự giữa các entity. Nhưng phải ghi rõ consistency boundary: theo row, aggregate, partition hay transaction.

### Delete phải được biểu diễn rõ

Nếu CDC chỉ gửi row sau update mà không có delete tombstone, target có thể giữ lại row đã xóa ở source. Với delete event, cần primary key và commit position để target xóa đúng record. Nếu dùng soft delete, phải quyết định `deleted_at` hoặc trạng thái archived có phải semantics chuẩn hay không.

Với stream compacted hoặc datastore dùng tombstone, không loại bỏ tombstone quá sớm nếu consumer chậm hoặc cần replay.

## 5. Áp dụng CDC idempotent ở target

CDC delivery thường có thể lặp khi consumer retry sau lỗi hoặc checkpoint chưa được commit. Applier cần xử lý lại cùng một change event mà không tạo ra kết quả sai.

Một cách là lưu apply ledger theo source position/event identity:

~~~sql
CREATE TABLE migration_apply_ledger (
    source_stream       VARCHAR(200) NOT NULL,
    source_position     VARCHAR(300) NOT NULL,
    event_sequence      INTEGER NOT NULL,
    applied_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_stream, source_position, event_sequence)
);
~~~

Applier thực hiện trong cùng transaction:

1. Thử insert ledger key.
2. Nếu key đã tồn tại, change đã được apply; bỏ qua.
3. Nếu insert thành công, apply row change vào target.
4. Commit cả ledger và target mutation cùng transaction.

Nếu ledger được commit trước target mutation hoặc ngược lại, crash có thể tạo trạng thái sai: đánh dấu đã xử lý nhưng chưa ghi row, hoặc ghi row rồi retry gây lặp side effect. Hai thay đổi cần cùng transaction nếu cùng database.

### Upsert theo version

Một cách bổ sung là lưu source version/commit position trên target row và chỉ áp dụng update mới hơn:

~~~sql
INSERT INTO target_order (
    order_id, status, source_version, updated_at
)
VALUES (
    :order_id, :status, :source_version, :updated_at
)
ON CONFLICT (order_id) DO UPDATE
SET status = EXCLUDED.status,
    source_version = EXCLUDED.source_version,
    updated_at = EXCLUDED.updated_at
WHERE target_order.source_version < EXCLUDED.source_version;
~~~

Ví dụ trên chỉ dùng được nếu `source_version` có thứ tự so sánh hợp lệ cho cùng entity. LSN/SCN dạng chuỗi không nhất thiết so sánh lexicographic đúng; cần parser/typed representation hoặc sequence numeric theo connector. Nếu event đến từ nhiều nguồn, không so sánh version độc lập mà không có quy tắc ordering chung.

### Delete cũng cần version/tombstone

Nếu row bị delete ở version 12 rồi event update cũ version 11 đến muộn, target không được tái tạo row đã xóa. Lưu tombstone hoặc deletion marker kèm source version trong khoảng cần thiết:

~~~sql
CREATE TABLE target_order_tombstone (
    order_id        VARCHAR(100) PRIMARY KEY,
    source_version  BIGINT NOT NULL,
    deleted_at      TIMESTAMPTZ NOT NULL
);
~~~

Khi nhận delete, ghi tombstone theo version. Khi nhận upsert, so sánh version với tombstone; chỉ cho phép tạo lại nếu change thực sự mới hơn và contract cho phép. Thời hạn giữ tombstone phải bao phủ cửa sổ replay và event trễ.

## 6. Checkpoint: chỉ tiến sau khi dữ liệu đã bền vững

Checkpoint thể hiện vị trí CDC consumer đã áp dụng an toàn. Một nguyên tắc quan trọng:

**Không advance checkpoint trước khi target mutation được commit.**

Nếu checkpoint tiến trước, consumer crash có thể bỏ qua change chưa được ghi vào target. Nếu target commit trước nhưng checkpoint chưa tiến, consumer có thể replay change; vì vậy apply phải idempotent.

Khi xử lý batch:
- Xác định batch/transaction boundary.
- Apply tất cả change cần thiết.
- Commit target mutation và ledger.
- Sau đó commit checkpoint tương ứng theo semantics connector.
- Nếu crash trước checkpoint, replay batch an toàn.
- Nếu checkpoint đã commit, mọi change trước vị trí đó phải durable.

Một số connector quản lý offset/checkpoint nội bộ hoặc dùng distributed transaction/offset storage riêng. Hãy tuân thủ protocol của connector; không tự ghi một offset tùy ý rồi giả định nó tương đương commit của broker.

### Transaction có nhiều row

Nếu một source transaction cập nhật order, order lines và inventory, áp dụng từng row riêng lẻ có thể khiến target tạm thời không nhất quán. Nếu consumer cần nhìn thấy transaction nguyên tử, phải giữ transaction boundary và apply các row trong cùng target transaction, hoặc dùng staging/version marker để chỉ công bố batch khi hoàn tất.

Nếu migration chỉ cần eventual consistency ở từng bảng và chưa mở target cho traffic đọc nghiệp vụ, có thể chấp nhận trạng thái trung gian trong giai đoạn load. Nhưng không mở target cho người dùng khi các invariant liên bảng chưa đạt.

## 7. Transform dữ liệu và schema mapping

Source và target có thể khác kiểu dữ liệu, naming, normalization hoặc model. Migration phải có mapping được version hóa và kiểm thử.

Ví dụ:

| Source | Target | Rủi ro |
|---|---|---|
| Integer amount theo đồng | Decimal/amountMinor | Sai đơn vị hoặc mất precision |
| Timestamp không timezone | Instant UTC | Diễn giải sai múi giờ |
| CHAR padded | VARCHAR | Khoảng trắng cuối làm lệch key |
| Case-insensitive collation | Case-sensitive key | Hai giá trị trước đây tương đương nay thành khác |
| Nullable field | Required field | Row cũ thiếu dữ liệu |
| Numeric enum | String enum | Mapping giá trị chưa biết |
| Soft delete flag | Physical delete | Mất khả năng audit/restore |

Không chuyển tiền qua floating point. Dùng integer minor units hoặc decimal có precision/scale được quy định. Khi đổi timezone, phân biệt local date-time với instant UTC; không gắn UTC cho timestamp cũ nếu dữ liệu nguồn vốn là local time không rõ timezone.

### Version hóa transformation

Một transformation nên có:
- Version/commit của mapping.
- Input schema version.
- Output schema version.
- Quy tắc xử lý null, default và unknown value.
- Quy tắc rounding, timezone, collation và enum.
- Cách xử lý record không hợp lệ.
- Bộ fixture đại diện và kết quả mong đợi.

Nếu mapping thay đổi trong lúc CDC chạy, phải biết record nào đã được transform bằng version nào. Có thể rebuild target từ source bằng transformation mới, hoặc tạo migration version mới với backfill có kiểm soát. Không thay logic mapping âm thầm giữa một lần load mà không có audit.

### Poison row và quarantine

Một row có dữ liệu không hợp lệ có thể làm CDC batch liên tục thất bại. Không bỏ qua im lặng vì checkpoint sẽ tiến qua dữ liệu chưa được migrate.

Thiết kế quarantine:
- Ghi source key, source position, schema version và error category.
- Bảo vệ payload theo chính sách dữ liệu nhạy cảm.
- Giữ checkpoint hoặc đánh dấu partition có lỗi theo khả năng connector.
- Sửa mapping hoặc dữ liệu bằng quy trình có audit.
- Replay row sau khi khắc phục.
- Không mở cutover nếu lỗi ảnh hưởng dữ liệu bắt buộc hoặc invariant quan trọng.

Nếu có thể chấp nhận bỏ qua một số field không thiết yếu, cần quyết định từ owner nghiệp vụ và ghi lại ngoại lệ.

## 8. Đối soát dữ liệu: chứng minh target tương đương

Copy hoàn tất và CDC lag bằng zero chưa đủ để chứng minh dữ liệu đúng. Có thể có bug mapping, bỏ sót delete, sai timezone hoặc event bị apply sai thứ tự. **Reconciliation** so sánh source và target tại cùng một logical point và kiểm tra cả dữ liệu lẫn invariant nghiệp vụ.

Các lớp đối soát:

1. **Completeness:** row count, partition count, key coverage.
2. **Integrity:** checksum/hash theo partition hoặc record.
3. **Business invariants:** tổng tiền, số order theo trạng thái, quan hệ parent-child.
4. **Freshness:** CDC lag và source position đã áp dụng.
5. **Exception review:** row quarantine, mapping exception và duplicate.

### Vì sao phải so sánh cùng một mốc?

Nếu source tiếp tục nhận write trong khi reconciliation quét nhiều phút, source và target có thể thay đổi giữa lúc đọc. Một row mismatch chưa chắc là lỗi migration; có thể source được cập nhật sau khi target đã được đọc.

Cách làm:
- Chọn source snapshot/consistent read tại một boundary.
- So target ở trạng thái đã apply đến cùng CDC position.
- Hoặc tạm ngừng write trong giai đoạn final reconciliation.
- Nếu không thể dừng write, dùng snapshot isolation hoặc watermark/vector position để xác định phạm vi so sánh.

Không so source “hiện tại” với target “hiện tại” bằng hai query không có snapshot coordination rồi kết luận mismatch chính xác.

### Row count theo partition

Thay vì chỉ so tổng row count, chia theo key range, tenant, ngày hoặc hash bucket:

| Partition | Source rows | Target rows | Difference |
|---|---:|---:|---:|
| tenant 00–19 | 125.000 | 125.000 | 0 |
| tenant 20–39 | 118.400 | 118.399 | -1 |
| tenant 40–59 | 132.050 | 132.050 | 0 |
| tenant 60–79 | 121.900 | 121.900 | 0 |
| tenant 80–99 | 119.700 | 119.700 | 0 |

Ví dụ này cho thấy tổng count có thể gần đúng nhưng vẫn có một partition thiếu row. Partitioning giúp khoanh vùng điều tra và chạy lại phần lỗi.

### Checksum theo partition

Có thể tạo checksum trên tập field chuẩn hóa và sắp xếp theo primary key. Ví dụ khái niệm:

~~~text
partition_checksum =
  HASH(
    CONCAT(
      canonical(row_1),
      canonical(row_2),
      ...
      canonical(row_n)
    )
  )
~~~

Checksum chỉ hữu ích nếu canonicalization ổn định:
- Cùng thứ tự row.
- Cùng cách biểu diễn null.
- Cùng precision số.
- Cùng timezone.
- Cùng encoding và collation.
- Không đưa field volatile như migration timestamp vào hash nếu không có cùng semantics.

Một checksum partition khác nhau chỉ nói rằng dữ liệu khác; nó không cho biết row nào khác. Chia nhỏ partition rồi so key/field để tìm nguyên nhân. Với dữ liệu cực lớn, có thể dùng Merkle tree hoặc hierarchical checksum để khoanh vùng khác biệt mà không truyền toàn bộ dataset.

### Đối soát invariant nghiệp vụ

Row count và checksum có thể bỏ sót lỗi semantics nếu cùng số row nhưng field mapping sai. Kiểm tra thêm:

- Tổng số đơn theo trạng thái.
- Tổng amount theo currency và ngày.
- Số order lines trên mỗi order.
- Tổng inventory không âm và cân bằng theo kho.
- Số payment thành công khớp số payment reference.
- Foreign key/reference không bị orphan.
- Soft-deleted rows được giữ hoặc xóa theo policy.
- Unique business key không bị trùng.

Không cộng tiền của nhiều currency vào một tổng chung. Nhóm theo currency và scale; kiểm tra rounding theo đúng contract.

## 9. Java: biểu diễn kết quả reconciliation

Có thể chuẩn hóa kết quả đối soát thành object để ghi log, dashboard hoặc migration report:

~~~java
import java.time.Instant;

public record PartitionReconciliation(
        String partitionId,
        long sourceCount,
        long targetCount,
        String sourceChecksum,
        String targetChecksum,
        long sourcePosition,
        long targetAppliedPosition,
        Instant checkedAt) {

    public boolean countsMatch() {
        return sourceCount == targetCount;
    }

    public boolean checksumsMatch() {
        return sourceChecksum.equals(targetChecksum);
    }

    public boolean caughtUp() {
        return targetAppliedPosition >= sourcePosition;
    }

    public boolean passed() {
        return countsMatch() && checksumsMatch() && caughtUp();
    }
}
~~~

Đây là mô hình minh họa. `sourcePosition` và `targetAppliedPosition` phải cùng một hệ thứ tự có thể so sánh; nếu target chỉ lưu checkpoint riêng, hãy map về source log position đã apply. Không so hai offset từ hai stream độc lập như thể chúng có cùng thứ tự.

Ví dụ tạo report:

~~~java
import java.util.List;

public final class ReconciliationReport {
    private final List<PartitionReconciliation> partitions;

    public ReconciliationReport(List<PartitionReconciliation> partitions) {
        this.partitions = List.copyOf(partitions);
    }

    public boolean passed() {
        return !partitions.isEmpty()
                && partitions.stream().allMatch(
                        PartitionReconciliation::passed);
    }

    public List<PartitionReconciliation> failedPartitions() {
        return partitions.stream()
                .filter(result -> !result.passed())
                .toList();
    }
}
~~~

Trong production, report cần thêm mapping version, snapshot boundary, CDC stream identity, schema version, count of quarantined rows và operator/run ID. Chỉ ghi PASS nếu mọi kiểm tra bắt buộc đều đạt; không tính trung bình các partition rồi bỏ qua partition lỗi.

## 10. Shadow reads và so sánh trước khi chuyển traffic

Sau khi baseline và CDC bắt kịp, có thể chạy shadow reads: request thật vẫn trả kết quả từ source, đồng thời một bản sao request được gửi đến target để so sánh.

Shadow read cần:
- Không tạo side effect ở target.
- Dùng cùng input và cùng quyền truy cập tương đương.
- So sánh các field có semantics giống nhau.
- Chuẩn hóa field không ổn định như timestamp, generated ID hoặc ordering không được bảo đảm.
- Giới hạn sampling/rate để không quá tải target.
- Không để lỗi target làm thất bại request đang phục vụ từ source.

Kết quả shadow mismatch nên được phân loại:
- Target thiếu record.
- Field mapping khác.
- Stale CDC.
- Khác biệt do business rule hoặc data freshness.
- Khác biệt hợp lệ theo thiết kế target.
- Lỗi authorization/tenant filter.

Không so response byte-for-byte nếu hai hệ thống có thể sắp xếp array khác nhau hoặc tạo metadata khác nhau. So sánh semantic fields theo contract.

### Shadow writes có rủi ro cao hơn

Không gửi một request ghi nghiệp vụ thật đến cả hai hệ thống rồi hy vọng hai write luôn thành công cùng nhau. Nếu source commit còn target fail, hoặc ngược lại, hệ thống có hai trạng thái khác nhau. Nếu dùng shadow write, nó phải được thiết kế như một migration protocol: idempotency key, outbox/CDC, error ledger, replay và reconciliation. Không dùng nó như một dòng code gọi hai repository.

## 11. Dual-write và write ownership

Trong thời gian migration, một quyết định then chốt là hệ thống nào được quyền ghi dữ liệu chuẩn.

### Vì sao application dual-write đơn giản không an toàn?

Ví dụ code:

~~~java
sourceRepository.save(order);
targetRepository.save(order);
~~~

Nếu lệnh đầu thành công và lệnh thứ hai thất bại, source và target lệch nhau. Đảo thứ tự chỉ đảo tình huống. Không có transaction phân tán được thiết kế rõ, hai database không commit nguyên tử.

Các lựa chọn an toàn hơn:
- Source là single writer; CDC/outbox chuyển thay đổi sang target.
- Target là single writer; reverse replication chuyển thay đổi về source trong giai đoạn rollback được hỗ trợ.
- Một write service duy nhất điều phối và ghi qua transactional outbox.
- Chấp nhận dual-write có reconciliation/compensation rõ ràng khi không thể dùng một nguồn ghi.

### Write ownership

Một service hoặc control plane nên ghi nhận nguồn ghi đang hoạt động:

~~~text
write_owner = LEGACY
migration_phase = CDC_CATCH_UP
migration_epoch = 12
~~~

Sau cutover:

~~~text
write_owner = SERVERLESS
migration_phase = TARGET_ACTIVE
migration_epoch = 13
~~~

Đây là metadata điều khiển, không phải biến local trong từng function. Mọi writer cần kiểm tra ownership hoặc nhận cấu hình có version/fencing phù hợp. Nếu chỉ thay environment variable trên một số instance, instance cũ có thể tiếp tục ghi vào source sau khi traffic đã chuyển.

### Fencing old writers

Để ngăn writer cũ tiếp tục ghi:
- Tạm dừng hoặc disable route/consumer cũ.
- Thu hồi quyền write của legacy identity sau khi đã drain.
- Dùng database role/permission hoặc write gate có thể kiểm tra tập trung.
- Dùng migration epoch/fencing token nếu kiến trúc hỗ trợ.
- Xác minh không còn connection hoặc job cũ ghi sau mốc cutover.

Chỉ đổi DNS hoặc load balancer không ngăn cron job, queue consumer hoặc batch process cũ tiếp tục ghi. Liệt kê toàn bộ writer: API, worker, scheduler, admin tool, ETL, trigger và integration bên ngoài.

## 12. Quy trình cutover theo từng giai đoạn

Một cutover ít downtime nên có các giai đoạn có điều kiện đi tiếp rõ ràng.

~~~mermaid
flowchart TD
    A["1. Inventory writers and readers"] --> B["2. Baseline snapshot + CDC"]
    B --> C["3. Load and catch up"]
    C --> D["4. Reconcile and shadow read"]
    D --> E["5. Freeze / fence source writes"]
    E --> F["6. Drain in-flight work and final CDC"]
    F --> G["7. Final reconciliation at watermark"]
    G --> H{"All gates pass?"}
    H -->|No| I["Abort cutover; keep legacy owner"]
    H -->|Yes| J["8. Switch write owner to target"]
    J --> K["9. Route traffic and monitor"]
    K --> L["10. Retire old writer after rollback window"]
~~~

### Giai đoạn 1: inventory

Liệt kê:
- Tất cả service/function có thể ghi source.
- Reader phụ thuộc vào source.
- Queue, scheduled job, batch và integration bên ngoài.
- Table, sequence, trigger, stored procedure và constraint.
- Data owner, retention và compliance.
- SLO downtime, RTO, RPO và rollback requirement.

### Giai đoạn 2: baseline + CDC

Lấy snapshot nhất quán, nạp target và bắt đầu apply CDC theo boundary. Theo dõi:
- Snapshot progress.
- Source log retention.
- CDC lag/oldest unapplied position.
- Apply throughput và error rate.
- Quarantine count.
- Target database load.

### Giai đoạn 3: catch-up và reconciliation

Để CDC chạy đến gần zero lag. Chạy count/checksum/business invariants theo snapshot hoặc watermark có thể so sánh. Xử lý mọi mismatch bắt buộc. Chạy shadow reads để kiểm tra query semantics và authorization.

### Giai đoạn 4: chuẩn bị cutover

- Deploy serverless functions và cấu hình runtime identity.
- Kiểm tra connection pool/max instances để không làm target quá tải.
- Chuẩn bị write gate/fencing.
- Dừng các deployment/schema changes trong cutover window.
- Xác định operator, dashboard, rollback decision owner và communication channel.
- Chạy diễn tập trên staging với dataset/traffic đại diện.

### Giai đoạn 5: freeze và drain

- Chặn write mới ở source theo cách có thể kiểm chứng.
- Cho request đang chạy hoàn tất hoặc kết thúc an toàn.
- Dừng/disable legacy consumers, scheduled jobs và batch writers.
- Ghi source high-water mark cuối cùng.
- Đợi CDC apply đến đúng mốc đó.
- Chạy final reconciliation tại mốc dữ liệu đã freeze.

Nếu không thể freeze toàn bộ writer, phải có một giao thức ownership/epoch bảo đảm không có hai nguồn ghi đồng thời. Không chuyển traffic chỉ vì queue lag “gần zero”; cần biết chính xác watermark cuối.

### Giai đoạn 6: switch

- Atomically cập nhật write ownership/epoch.
- Bật target writer và kiểm tra quyền ghi.
- Route request/trigger sang serverless functions.
- Kiểm tra một giao dịch canary có thể trace từ request đến database/event.
- Xác minh source writer đã bị fence và không còn write mới.
- Theo dõi error rate, latency, queue age và business metrics.

### Giai đoạn 7: giữ rollback window

Không xóa source ngay sau khi target nhận traffic. Giữ source ở trạng thái read-only hoặc standby trong thời gian đã thống nhất, giữ schema/backup và tiếp tục theo dõi mismatch. Retire source chỉ sau khi rollback window đóng và owner chấp thuận.

## 13. Rollback khi target đã nhận write

Rollback dữ liệu khó hơn rollback code. Trước cutover, source chứa trạng thái chuẩn. Sau khi target nhận write mới, source không tự biết các thay đổi đó.

Có ba chiến lược chính:

| Chiến lược | Cách rollback | Điều kiện |
|---|---|---|
| Reversible replication | CDC/reverse sync từ target về source | Có reverse mapping và target changes tương thích source |
| Freeze and reconcile | Dừng target writes, chuyển các thay đổi cần thiết về source, đối soát rồi switch | Có downtime/maintenance window |
| Forward recovery | Giữ target làm source of truth, rollback code nhưng vẫn ghi target | Code cũ có thể tương thích target hoặc có adapter |

Không bao giờ chỉ đổi connection string về source nếu target đã nhận write chưa được sao chép ngược. Điều đó có thể làm mất order/payment mới hoặc tạo hai lịch sử dữ liệu.

### Rollback gate

Trước cutover phải trả lời:
- Target đã nhận write nghiệp vụ chưa?
- Có reverse CDC/replication được kiểm thử không?
- Target schema có field mà source không biểu diễn được không?
- Có side effect ngoài database như payment/email đã xảy ra không?
- Có thể replay event từ outbox để khôi phục không?
- RPO cho rollback là bao nhiêu?
- Ai có quyền quyết định rollback và thời gian tối đa là bao lâu?

Nếu không có reverse replication, có thể chọn **forward recovery**: giữ target làm nguồn ghi và triển khai lại phiên bản ứng dụng ổn định tương thích target. Đây thường an toàn hơn việc chuyển về source đã stale.

## 14. Serverless-specific concerns trong data migration

Serverless giúp scale worker nhanh nhưng migration cần kiểm soát tốc độ. Nếu CDC backlog tăng, autoscaler có thể tạo nhiều function instances cùng lúc và đẩy target database đến giới hạn.

### Backpressure và concurrency

Đặt giới hạn:
- Max concurrency/instance hoặc max function concurrency.
- Batch size và parallelism của CDC consumer.
- Connection pool per instance.
- Tổng connection budget của target.
- Rate limit cho write amplification/index maintenance.
- Retry/backoff có jitter.

Một ước lượng cần kiểm tra:

~~~text
maximum database connections
  ≈ max active instances × pool size per instance
     + other application/admin connections
~~~

Đây là upper bound xấp xỉ. Pool có thể mở kết nối lazy; một số driver/proxy multiplex connection. Nhưng phải load test để biết giới hạn thực tế.

### Serverless worker nên stateless

Mỗi invocation cần có khả năng tiếp tục từ checkpoint bền vững. Không giữ CDC offset duy nhất trong static field hoặc local file của container. Khi instance bị thu hồi, worker khác phải có thể đọc checkpoint và tiếp tục an toàn.

### Batch và retry

- Batch nhỏ giúp giảm thời gian transaction và phạm vi retry.
- Batch lớn tăng throughput nhưng có thể tăng lock duration, memory và blast radius.
- Nếu một row poison làm cả batch rollback, cần cơ chế xác định row lỗi và quarantine.
- Không advance checkpoint qua row chưa apply thành công.
- Retry transient errors theo backoff; lỗi schema/permanent cần dừng hoặc quarantine có kiểm soát.

### Database connection

Function scale-out có thể tạo connection storm. Dùng connection pool có giới hạn, database proxy/pooling service nếu phù hợp, và giới hạn max instances. Không tạo một connection mới cho mỗi row trong batch. Tái sử dụng client/connection trong invocation environment theo thread-safety và lifecycle của driver.

## 15. Java: applier với ledger và transaction

Một abstraction có thể giúp tách CDC adapter khỏi logic apply:

~~~java
public interface ChangeApplier {
    ApplyResult apply(RowChange change);
}

public enum ApplyResult {
    APPLIED,
    ALREADY_APPLIED,
    QUARANTINED
}
~~~

Một service xử lý change event cần transaction bao quanh ledger và target mutation:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransactionalChangeApplier implements ChangeApplier {
    private final ApplyLedgerRepository ledger;
    private final TargetRowRepository target;
    private final ChangeMapper mapper;

    public TransactionalChangeApplier(
            ApplyLedgerRepository ledger,
            TargetRowRepository target,
            ChangeMapper mapper) {
        this.ledger = ledger;
        this.target = target;
        this.mapper = mapper;
    }

    @Override
    @Transactional
    public ApplyResult apply(RowChange change) {
        boolean claimed = ledger.tryInsert(
                change.position().stream(),
                change.position().commitPosition(),
                change.position().eventSequence());

        if (!claimed) {
            return ApplyResult.ALREADY_APPLIED;
        }

        switch (change.operation()) {
            case INSERT, UPDATE -> target.upsert(mapper.toTarget(change));
            case DELETE -> target.delete(
                    change.table(), change.primaryKey(),
                    change.position());
        }

        return ApplyResult.APPLIED;
    }
}
~~~

Đây là ví dụ cấu trúc. `tryInsert` phải dùng unique constraint/atomic insert; `upsert` và ledger phải dùng cùng database transaction. Nếu mapper ném lỗi dữ liệu, transaction rollback; quarantine nên được ghi bằng một transaction/flow có chủ đích để không đánh dấu change đã apply khi target mutation chưa thành công.

Nếu target là datastore khác với ledger, không thể dùng transaction Spring thông thường để bao trùm cả hai. Khi đó cần conditional write, outbox, apply state machine hoặc cơ chế idempotency của target store.

### Không giả định commit checkpoint cùng database transaction

CDC connector có thể lưu offset trong broker hoặc external offset store. Transaction giữa target DB và offset store có thể không tồn tại. Mẫu phổ biến là commit target + ledger trước, rồi commit offset; nếu crash giữa hai bước, replay được hấp thụ bởi ledger. Không commit offset trước target mutation.

## 16. Migration ledger và operational state

Ngoài row-level apply ledger, nên lưu tiến trình migration ở mức job/run:

~~~sql
CREATE TABLE migration_run (
    migration_id       VARCHAR(100) PRIMARY KEY,
    source_name        VARCHAR(200) NOT NULL,
    target_name        VARCHAR(200) NOT NULL,
    snapshot_id        VARCHAR(300),
    start_position     VARCHAR(300),
    applied_position   VARCHAR(300),
    mapping_version   VARCHAR(100) NOT NULL,
    schema_version    VARCHAR(100) NOT NULL,
    status             VARCHAR(30) NOT NULL,
    started_at         TIMESTAMPTZ NOT NULL,
    updated_at         TIMESTAMPTZ NOT NULL,
    completed_at       TIMESTAMPTZ
);
~~~

Các trạng thái có thể gồm:
- PLANNED
- SNAPSHOT_RUNNING
- SNAPSHOT_COMPLETE
- CDC_CATCH_UP
- RECONCILING
- READY_FOR_CUTOVER
- CUTOVER_IN_PROGRESS
- TARGET_ACTIVE
- ROLLBACK_IN_PROGRESS
- COMPLETED
- BLOCKED

State machine giúp operator biết migration đang ở đâu và điều kiện nào được phép chuyển bước. Mỗi transition cần lưu actor, timestamp, migration epoch và evidence/report liên quan. Không chỉ dựa vào một biến environment hoặc một dòng log.

## 17. Bảo mật và quản trị dữ liệu trong migration

Migration worker thường có quyền đọc phần lớn source và ghi target. Đây là workload có blast radius lớn, nên cần identity riêng.

- Dùng service account/role riêng cho snapshot loader, CDC applier và reconciliation worker nếu quyền khác nhau.
- Source identity chỉ có quyền đọc snapshot/log cần thiết.
- Target identity chỉ có quyền ghi đúng schema/table.
- Không cấp quyền admin database nếu chỉ cần INSERT/UPDATE/DELETE.
- Dùng TLS và mã hóa at rest theo chính sách.
- Không log full row image nếu chứa PII hoặc secret.
- Bảo vệ file snapshot, staging bucket và quarantine store.
- Audit quyền truy cập và xóa dữ liệu tạm sau migration theo retention.
- Giữ mapping/transform version và operator actions có audit trail.

Không sao chép secret hoặc token trong row image sang target như dữ liệu thông thường. Nếu source chứa credential đã hash, không đổi cách hash hoặc salt trong migration mà không có kế hoạch riêng.

## 18. Theo dõi tiến độ và chất lượng migration

Dashboard migration nên có các metric:

| Metric | Câu hỏi cần trả lời |
|---|---|
| Snapshot rows/bytes copied | Baseline còn bao nhiêu? |
| Snapshot throughput | Tốc độ copy có đáp ứng window? |
| CDC source position | Nguồn đã phát sinh đến đâu? |
| CDC applied position | Target đã apply đến đâu? |
| Replication lag/oldest event age | Target đang trễ bao lâu? |
| Apply rate/error rate | Consumer có xử lý ổn định? |
| Duplicate apply count | Replay/idempotency đang xảy ra thế nào? |
| Quarantine count | Có row nào chưa migrate? |
| Reconciliation mismatch count | Partition/invariant nào chưa đạt? |
| Target DB CPU/connections/IO | Có nguy cơ quá tải? |
| Cutover write errors | Target writer có lỗi sau switch? |

Checkpoint position có thể không chuyển thành thời gian một cách chính xác nếu log rate biến động. Theo dõi cả lag theo thời gian và vị trí log. Không chỉ nhìn “CDC running” hoặc trạng thái job xanh.

### Alert nên có

- CDC lag vượt ngưỡng cutover.
- Source log retention sắp cạn.
- Apply error hoặc quarantine tăng.
- Target connection pool/database chạm giới hạn.
- Reconciliation mismatch còn tồn tại.
- Snapshot không tiến triển.
- Writer cũ tiếp tục ghi sau fencing.
- Target nhận write khi migration chưa ở phase cho phép.

Mỗi alert cần owner, runbook và điều kiện dừng migration. Nếu dữ liệu bắt buộc bị mismatch, không chuyển cutover chỉ để giữ lịch release.

## 19. Ví dụ kế hoạch cutover cho orders service

Giả sử hệ thống có 20 triệu orders và legacy application vẫn phục vụ traffic.

| Giai đoạn | Nguồn ghi | Hoạt động | Điều kiện đi tiếp |
|---|---|---|---|
| Prepare | Legacy | Tạo target schema, quyền và CDC | Snapshot/CDC test thành công |
| Baseline | Legacy | Copy 20 triệu orders theo consistent snapshot | Row count/chunk load hoàn tất |
| Catch-up | Legacy | Apply CDC liên tục | Lag nằm trong ngưỡng |
| Shadow | Legacy | So sánh read từ target với source | Mismatch được phân loại và giải quyết |
| Freeze | Không nhận write mới ở source | Drain requests/consumers, lấy final watermark | Không còn legacy writer |
| Final sync | Source đã fence | Apply đến watermark cuối và reconciliation | Count/checksum/invariants PASS |
| Cutover | Serverless target | Switch write owner và route traffic | Canary write/read PASS |
| Observe | Serverless target | Theo dõi lỗi, lag, business metrics | Hết rollback window |
| Retire | Serverless target | Read-only/archive source rồi retire theo policy | Owner chấp thuận |

Các con số và điều kiện trong bảng là ví dụ. Ngưỡng CDC lag, thời gian freeze, sample rate và rollback window phải dựa trên SLA/RTO/RPO và năng lực thật của hệ thống.

## 20. Những lỗi migration thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Chỉ copy snapshot, không capture thay đổi trong lúc copy | Mất write phát sinh giữa quá trình migration | Coordinated snapshot + CDC boundary |
| Bắt đầu CDC sau khi snapshot hoàn tất mà không có log position phù hợp | Khoảng trống dữ liệu | Capture/coordinate từ boundary được hỗ trợ |
| Advance checkpoint trước target commit | Bỏ sót change sau crash | Commit target + ledger trước offset |
| Apply duplicate không idempotent | Side effect hoặc row mutation lặp | Unique ledger và conditional/upsert |
| Không xử lý delete/tombstone | Target giữ dữ liệu đã xóa | Capture delete và giữ tombstone đủ lâu |
| So source và target ở hai thời điểm khác nhau | False mismatch hoặc bỏ sót lỗi | Consistent snapshot/watermark |
| Chỉ so tổng row count | Không phát hiện partition thiếu hoặc field sai | Count + checksum + business invariants |
| Dual-write trực tiếp hai database | Hai nguồn lệch khi một write fail | Single writer + CDC/outbox hoặc protocol rõ |
| Chuyển traffic nhưng quên cron/consumer cũ | Legacy tiếp tục ghi sau cutover | Inventory và fence mọi writer |
| Rollback code bằng cách trỏ lại source stale | Mất dữ liệu target mới | Reverse sync hoặc forward recovery |
| Scale CDC consumer không giới hạn | Connection storm, target quá tải | Backpressure, concurrency và pool budget |
| Xóa source ngay sau cutover | Không còn đường rollback/đối soát | Giữ read-only standby và rollback window |

## 21. Checklist trước khi chuyển nguồn ghi

- [ ] Có inventory đầy đủ mọi reader, writer, job, trigger và integration.
- [ ] Source/target schema và transformation được version hóa.
- [ ] Baseline snapshot có consistency boundary rõ.
- [ ] CDC start position được phối hợp với snapshot, không có gap.
- [ ] Source log retention đủ dài cho load, catch-up và recovery.
- [ ] CDC apply có idempotency ledger/conditional write.
- [ ] Ordering và transaction boundary được bảo toàn theo yêu cầu.
- [ ] Delete/tombstone và late event được xử lý.
- [ ] Checkpoint chỉ tiến sau target mutation durable.
- [ ] Quarantine có owner, replay và audit.
- [ ] Reconciliation chạy tại cùng snapshot/watermark.
- [ ] Row count, checksum và business invariants đạt.
- [ ] Shadow reads không tạo side effect và mismatch đã được xử lý.
- [ ] Chỉ một write owner được active tại một thời điểm.
- [ ] Legacy writer, scheduler, queue consumer và admin path đã được fence.
- [ ] Target capacity, concurrency, connection pool và backpressure đã load test.
- [ ] Final watermark và cutover gate được ghi lại.
- [ ] Rollback xét dữ liệu target đã phát sinh, không chỉ rollback code.
- [ ] Reverse replication hoặc forward recovery đã được diễn tập.
- [ ] Source được giữ theo rollback/retention policy trước khi retire.

## Tự kiểm tra

1. Vì sao baseline snapshot đơn lẻ không đủ khi source vẫn nhận write?
2. CDC start position cần liên hệ với snapshot boundary như thế nào?
3. Vì sao database CDC record khác domain event?
4. Checkpoint nên được commit trước hay sau target mutation, và vì sao?
5. Làm thế nào ngăn update cũ đến muộn ghi đè trạng thái mới?
6. Delete/tombstone cần được giữ bao lâu khi có replay?
7. Vì sao reconciliation phải so source và target tại cùng logical point?
8. Row count và checksum có thể bỏ sót loại lỗi nghiệp vụ nào?
9. Vì sao application dual-write trực tiếp hai database có thể tạo split state?
10. Write ownership và fencing bảo vệ cutover ra sao?
11. Nếu target đã nhận write mới, điều gì cần có trước khi rollback về source?
12. Vì sao serverless CDC consumer cần giới hạn concurrency và connection pool?

Di chuyển dữ liệu an toàn cần một chuỗi bằng chứng: snapshot nhất quán, CDC không có gap, apply idempotent, checkpoint durable, reconciliation tại cùng watermark và write ownership được chuyển có kiểm soát. Khi target đã trở thành nguồn ghi, rollback phải tính đến mọi write mới và side effect đã xảy ra. Với Java function serverless, stateless worker, backpressure, identity riêng và migration state machine giúp quá trình đồng bộ có thể tiếp tục, kiểm tra và khôi phục mà không dựa vào trạng thái trong một instance.

