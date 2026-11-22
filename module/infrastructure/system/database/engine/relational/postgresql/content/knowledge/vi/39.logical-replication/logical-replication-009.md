# Khả năng tương thích giữa các phiên bản và lược đồ trong PostgreSQL Logical Replication

## 1. Vì sao compatibility là điều kiện sống còn?

PostgreSQL logical replication chuyển các thay đổi dữ liệu được công bố từ publisher sang subscriber. Hai bên không cần dùng cùng một bố cục vật lý, nhưng phải hiểu cùng một hợp đồng dữ liệu: quan hệ nào được đồng bộ, cột nào được ánh xạ, giá trị có chuyển đổi được không và các ràng buộc trên subscriber có chấp nhận dữ liệu hay không.

Có hai chiều tương thích cần quản lý:

- **Tương thích phiên bản:** major version của publisher, subscriber, output plugin và replication protocol có hỗ trợ tổ hợp đang triển khai hay không.
- **Tương thích lược đồ:** table, column, data type, replica identity, partitioning, constraint và các object phụ thuộc có phù hợp để apply dữ liệu hay không.

Logical replication chủ yếu đồng bộ row changes. Nó không tự sao chép toàn bộ DDL, schema objects, roles, grants, sequence state, extension binaries hoặc cấu hình database. Vì vậy hai database có thể cùng nhận được WAL logical stream nhưng subscriber vẫn lỗi khi apply nếu schema drift.

Bài này giải thích cách thiết kế compatibility trước khi tạo subscription, cách triển khai thay đổi schema an toàn, cách kiểm tra drift và cách tổ chức nâng cấp major version.

### 1.1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích giới hạn tương thích publisher/subscriber giữa các PostgreSQL major versions.
2. Phân biệt logical data replication với schema/DDL migration.
3. Hiểu cách ánh xạ table và column giữa publisher và subscriber.
4. Đánh giá data type conversion, defaults, generated/identity columns và constraints.
5. Quản lý primary key/replica identity cho UPDATE và DELETE.
6. Thiết kế schema evolution theo expand-and-contract.
7. Xử lý partitioning, row filters, column lists, enums, collations và extensions.
8. Lập kế hoạch nâng cấp major version bằng logical replication.
9. Phát hiện schema drift và subscription apply errors.
10. Thực hiện preflight checks, lab và cutover có kiểm soát.

### 1.2. Nguyên tắc nền tảng

- Logical replication chuyển changes theo publication/subscription; nó không tự đồng bộ DDL.
- Publisher và subscriber phải có table mapping tương thích tại thời điểm apply.
- Tên column là cơ sở ánh xạ; không giả định hai bảng được ghép theo vị trí cột.
- Data type khác nhau chỉ an toàn khi giá trị thực tế có thể được chuyển đổi đúng ở subscriber.
- Thêm cột vào publisher không tự tạo cột tương ứng ở subscriber.
- Replica identity quyết định cách subscriber tìm row cũ cho UPDATE/DELETE.
- Sequence values, large objects và nhiều loại database objects không nằm trong luồng row replication thông thường.
- Một schema migration phải được triển khai theo thứ tự tương thích với cả hai phía.
- Subscriber không nên được xem là writable multi-master peer của publisher.
- Luôn test trên đúng PostgreSQL versions, extensions và dữ liệu đại diện trước cutover.

---

## 2. Publisher, subscriber và ranh giới của logical replication

### 2.1. Publisher

Publisher là PostgreSQL server/database tạo publication và phát logical changes. Publication xác định các tables hoặc operations được công bố.

Ví dụ:

~~~sql
CREATE PUBLICATION app_pub
FOR TABLE app.customers, app.orders;
~~~

Publication có thể giới hạn operations như INSERT, UPDATE, DELETE và TRUNCATE theo khả năng/version. Row filters và column lists cũng có thể được hỗ trợ ở các phiên bản tương ứng.

### 2.2. Subscriber

Subscriber là database tạo subscription để kết nối tới publisher và apply changes vào các tables tương ứng.

~~~sql
CREATE SUBSCRIPTION app_sub
CONNECTION 'host=publisher.example.net port=5432 dbname=appdb user=replicator'
PUBLICATION app_pub;
~~~

Subscriber cần có schema và tables tương ứng được chuẩn bị trước. Logical replication không tự tạo table definitions từ publisher.

### 2.3. Publication không phải schema migration

Publication mô tả dữ liệu nào được phát và operation nào được phát. Nó không phải một migration script và không đồng bộ tự động:
- CREATE/ALTER/DROP TABLE.
- CREATE/ALTER TYPE.
- Indexes, constraints và triggers.
- Roles, grants, policies và ownership.
- Extensions và extension binaries.
- Sequence definitions/current values.
- Views, materialized views và functions.

Các object này cần được triển khai bằng migration tooling hoặc quy trình quản trị riêng.

### 2.4. Subscriber table phải tồn tại

Khi subscription copy dữ liệu ban đầu, apply worker cần target relation để ghi rows. Nếu table chưa tồn tại hoặc schema không tương thích, initial table synchronization hoặc apply phase sẽ thất bại.

Có thể tạo schema trước bằng migration tool, schema dump hoặc deployment scripts. Tránh để hai bên tự phát triển schema không có version control.

### 2.5. Logical replication không phải bidirectional replication

Một subscription thông thường truyền changes từ publisher sang subscriber. Nếu ứng dụng ghi độc lập vào cả hai phía, có thể phát sinh:
- Row conflicts.
- Duplicate primary keys.
- Divergent values.
- Sequence collisions.
- Không có cơ chế conflict resolution tổng quát như một distributed multi-master database.

Thiết kế mặc định nên có một write authority cho replicated tables trong mỗi thời điểm.

### 2.6. Phân biệt logical replication với logical decoding

Logical decoding là cơ chế đọc WAL và chuyển changes thành logical representation thông qua output plugin. Logical replication là một cách dùng logical decoding để chuyển changes tới subscriber và apply vào tables.

Output plugin/protocol là một phần của compatibility surface. Custom consumers có thể có yêu cầu version riêng ngoài built-in pgoutput.

---

## 3. Tương thích major version giữa publisher và subscriber

### 3.1. Quy tắc triển khai cơ bản

PostgreSQL built-in logical replication thường được dùng để replicate từ publisher phiên bản cũ sang subscriber phiên bản mới trong quá trình major upgrade. Subscriber nên chạy cùng major version hoặc mới hơn publisher theo compatibility policy của PostgreSQL.

Không giả định publisher mới hơn có thể replicate an toàn sang subscriber cũ hơn. Logical replication protocol, message fields, type behavior và publication features có thể thay đổi qua major releases.

Trước triển khai, tra tài liệu của cả hai major versions và kiểm tra đúng hướng replication. Không suy ra compatibility chỉ từ việc TCP connection hoặc replication slot được tạo thành công.

### 3.2. Vì sao hướng cũ sang mới hữu ích?

Một quy trình major upgrade có thể:
1. Dựng subscriber trên major version mới.
2. Cài extensions và tạo schema tương thích.
3. Copy dữ liệu ban đầu.
4. Stream changes từ publisher cũ.
5. Chờ subscriber bắt kịp.
6. Dừng writes trong cutover window.
7. Xác nhận final LSN/data parity.
8. Chuyển ứng dụng sang subscriber mới.

Cách này có thể giảm downtime so với dump/restore offline cho database lớn, nhưng đòi hỏi schema compatibility và cutover runbook rõ ràng.

### 3.3. Không chỉ kiểm tra major version

Preflight phải xem:
- Publisher và subscriber exact server versions.
- Replication protocol/output plugin.
- Publication options đang dùng.
- Row filter/column list support.
- Partition replication behavior.
- Type definitions và extension versions.
- Encoding/collation.
- Replication slot/plugin compatibility.
- Client tools và migration tooling.

### 3.4. Feature gates theo phiên bản

Logical replication được mở rộng qua các major versions. Các tính năng như row filters, column lists, partition-root publication behavior, parallel apply, streaming in-progress transactions, two-phase replication và failover slots có thể được thêm hoặc thay đổi ở các phiên bản khác nhau.

Không copy cấu hình từ PostgreSQL mới sang server cũ mà không kiểm tra. Dùng documentation đúng release cho:
- CREATE PUBLICATION options.
- CREATE SUBSCRIPTION options.
- ALTER SUBSCRIPTION syntax.
- Monitoring view columns.
- Replication protocol capabilities.

### 3.5. pgoutput và custom output plugins

Built-in logical replication thường dùng output plugin pgoutput. Nếu dùng plugin khác, phải kiểm tra:
- Plugin có được cài trên publisher không.
- Plugin binary tương thích server major version.
- Consumer hiểu message format/version.
- Schema/type mapping của consumer.
- Upgrade/rollback path khi plugin thay đổi.

Một consumer tự viết có thể phụ thuộc protocol details mà built-in subscriber đã xử lý.

### 3.6. PostgreSQL upgrade không tự nâng cấp extensions

Logical replication chuyển row changes, không cài shared libraries hoặc nâng extension binaries. Khi subscriber chạy major version mới:
- Cài extension package tương thích với major version mới.
- Tạo extension trong subscriber database.
- Kiểm tra extension SQL objects và version.
- Xác nhận types/operators/functions được dùng trong schema.
- Test apply rows có extension types trước cutover.

### 3.7. System catalogs khác nhau

Không replicate trực tiếp system catalogs để nâng version. PostgreSQL major versions có thể thay đổi catalog layout và internal representation. Dùng logical replication ở tầng table changes, migration scripts và tools được hỗ trợ.

### 3.8. Version compatibility matrix

Nên duy trì bảng nội bộ cho mỗi pipeline:

| Publisher | Subscriber | Mục đích | Kết quả kiểm chứng |
|---|---|---|---|
| PG 14 | PG 15 | Major upgrade | Đã test trên staging |
| PG 15 | PG 16 | Major upgrade | Chưa test |
| PG 16 | PG 15 | Reverse direction | Không giả định hỗ trợ |
| PG 16 | PG 16 | Same-major replication | Đã test |

Các version chỉ là ví dụ minh họa. Thay bằng version thực tế và trạng thái support đã xác minh.

---

## 4. Table mapping và schema matching

### 4.1. Tên relation

Subscriber cần có target table tương ứng với table được publication gửi. Mapping relation sử dụng schema/table identity theo logical replication configuration; subscriber table không được tự suy ra từ tên tương tự hoặc thứ tự tạo.

Nếu table được rename ở publisher, subscriber không tự rename theo. Cần phối hợp migration hai phía và publication/subscription refresh nếu table membership thay đổi.

### 4.2. Column mapping theo tên

Logical replication ánh xạ các columns theo tên, không dựa vào vị trí ordinal trong table. Vì vậy thứ tự column có thể khác nhau, nhưng tên cột và khả năng chuyển giá trị phải phù hợp.

Không nên dựa vào việc subscriber có cột tên giống nhưng semantics khác. Ví dụ publisher dùng amount theo cents nhưng subscriber dùng amount theo dollars; kiểu dữ liệu có thể tương thích nhưng business meaning đã sai.

### 4.3. Publisher có thêm cột

Nếu publisher gửi một column mà subscriber không có, column đó không được tự tạo ở subscriber. Trong các trường hợp mapping được hỗ trợ, publisher-side columns không có target counterpart có thể bị bỏ qua theo rules của logical replication; tuy nhiên thay đổi này vẫn phải được kiểm tra theo publication column list, table mapping và version.

An toàn hơn là triển khai cột mới trên subscriber trước khi publisher bắt đầu ghi giá trị vào cột đó.

### 4.4. Subscriber có thêm cột

Subscriber có thể có các cột bổ sung ngoài replicated columns, nhưng chúng phải có thể được gán giá trị hợp lệ khi apply row:
- Nullable columns thường dễ tương thích hơn.
- Column có default có thể được xử lý khi không có giá trị replicated tương ứng theo insert semantics.
- NOT NULL column không có default có thể khiến INSERT apply thất bại.
- Generated columns có quy tắc riêng và subscriber tự tính theo expression của nó.

Không dựa vào default của subscriber như một cách thay thế cho dữ liệu publisher nếu business semantics yêu cầu cùng giá trị.

### 4.5. Column rename

Rename column trên publisher không tự đổi tên column ở subscriber. Trong giai đoạn hai bên lệch tên, mapping có thể không tìm thấy target column tương ứng và apply có thể lỗi hoặc không replicate column theo mong đợi.

Dùng expand-and-contract:
1. Thêm cột mới ở cả hai phía.
2. Backfill/dual-write hoặc migration data có kiểm soát.
3. Đổi publication/column mapping theo version hỗ trợ.
4. Chuyển ứng dụng sang cột mới.
5. Chỉ drop cột cũ khi mọi consumers đã chuyển.

### 4.6. Drop column

Drop cột ở publisher trước khi subscriber/application đã ngừng phụ thuộc có thể làm dữ liệu bị thiếu hoặc apply mismatch. Drop column là bước contract cuối cùng sau thời gian quan sát và xác nhận tất cả consumers đã nâng cấp.

### 4.7. Table rename/schema rename

DDL rename không tự propagate. Cần có migration phối hợp, cập nhật publication membership nếu cần và xác minh subscription relation mapping. Với table rename, có thể phải drop/add table trong publication và refresh publication trên subscriber theo version/operation đang dùng.

### 4.8. Schema khác nhau có chủ đích

Publisher và subscriber có thể có một số khác biệt được quản lý, ví dụ subscriber thêm index để phục vụ reads hoặc có tablespace khác. Nhưng những khác biệt đó phải được ghi rõ trong schema contract. Không để drift ngẫu nhiên vì một thay đổi cục bộ có thể làm apply fail.

---

## 5. Data type compatibility và chuyển đổi giá trị

### 5.1. Type names giống nhau chưa đủ

Hai columns cùng tên và cùng type có thể vẫn khác semantics do:
- Precision/scale khác nhau.
- Length constraints khác nhau.
- Collation khác nhau.
- Domain constraints khác nhau.
- Enum labels khác nhau.
- Extension type version khác nhau.
- Time zone interpretation khác nhau.

Compatibility phải kiểm tra cả metadata lẫn dữ liệu thực tế.

### 5.2. Type khác nhau

Logical replication có thể chuyển dữ liệu qua output/input representation của type theo protocol và server behavior. Một số source/target type khác nhau có thể tương thích nếu target nhận được representation; các trường hợp khác sẽ lỗi ở apply.

Ví dụ:
- integer sang bigint thường là hướng mở rộng an toàn nếu giá trị trong range.
- bigint sang integer có thể overflow.
- text sang uuid chỉ thành công nếu mọi value có format UUID hợp lệ.
- numeric precision nhỏ hơn có thể round hoặc reject tùy value/constraints.
- timestamp và timestamptz không thể coi là tương đương nếu semantics timezone khác.

Luôn thử trên dữ liệu đại diện và kiểm tra các giá trị biên.

### 5.3. Numeric precision/scale

Publisher có thể dùng numeric(18,2), subscriber numeric(12,2). Các values vượt precision target sẽ gây lỗi hoặc bị xử lý theo conversion semantics; không giả định subscriber có thể chứa toàn bộ publisher range.

Để mở rộng capacity, thường an toàn hơn khi target type rộng hơn hoặc tương đương, rồi mới thay publisher sau khi subscriber sẵn sàng.

### 5.4. Integer ranges

- smallint: phạm vi hẹp.
- integer: phạm vi rộng hơn smallint.
- bigint: phạm vi rộng hơn integer.

Khi subscriber dùng type nhỏ hơn, một row mới có thể làm apply worker fail. Kiểm tra max/min values trước khi thu hẹp type.

### 5.5. Character data

varchar(n)/char(n)/text có thể khác nhau về length semantics và padding. Nếu subscriber giới hạn ngắn hơn publisher, values dài có thể gây lỗi. Cần kiểm tra Unicode characters, byte length và character length; chúng không giống nhau.

### 5.6. Timestamp và timezone

timestamp without time zone lưu giá trị ngày giờ không gắn timezone. timestamptz biểu diễn instant và hiển thị theo session timezone. Chuyển đổi giữa hai loại có thể thay đổi ý nghĩa thời gian.

Đối với events, payment timestamps và audit records, thống nhất semantics trước migration. Kiểm tra TimeZone settings, client input formats và values quanh daylight-saving transitions nếu hệ thống có timezone rules.

### 5.7. Boolean, UUID và binary

Các type đơn giản thường dễ replicate khi hai bên cùng hiểu representation. Tuy nhiên, kiểm tra custom casts, domains và client encoding. bytea data có thể lớn; test throughput, memory và WAL/replication lag với payload thực tế.

### 5.8. Arrays, composites và ranges

Các type phức hợp phụ thuộc type definitions tương thích. Subscriber cần có type và nested element types phù hợp. Nếu composite type thay đổi field names/order/types, hãy triển khai migration đồng bộ và test values cũ/mới.

### 5.9. Domains

Domain type gồm base type và constraints. Cùng tên domain không đảm bảo definitions giống nhau. Nếu subscriber domain chặt hơn, row từ publisher có thể bị reject. So sánh pg_type, pg_constraint và domain base type/check constraints.

### 5.10. Enums

Enum labels phải có mặt trên subscriber trước khi publisher phát row chứa label mới. Thêm enum value trên publisher không tự tạo label ở subscriber. Thêm label trước trên subscriber là cách triển khai thường dùng khi nâng cấp schema.

Thứ tự enum labels cũng có semantics ordering. Hai bên có cùng labels nhưng khác thứ tự có thể cho kết quả so sánh/sort khác nhau. Không xem enum definitions tương đương chỉ vì danh sách labels giống nhau.

### 5.11. Collations

Collation ảnh hưởng sort order, comparison và uniqueness behavior. Khác locale, libc/ICU version hoặc collation provider có thể làm subscriber có behavior khác publisher, thậm chí ảnh hưởng unique indexes. Kiểm tra collation definitions/version và reindex requirements theo PostgreSQL docs.

### 5.12. Extension types

Các types như geography/geometry hoặc extension-defined types yêu cầu extension tương thích trên subscriber. Không chỉ tạo cột bằng type name; cài extension version đúng, kiểm tra casts/operators/functions và test apply payload thực tế.

### 5.13. Type conversion checklist

Trước khi cho phép type mismatch:
- Kiểm tra source/target type và typmod.
- Kiểm tra min/max và null distribution.
- Kiểm tra text/binary representation behavior theo version.
- Test values biên và malformed values.
- Kiểm tra domain/enum/collation dependencies.
- Test initial copy và streaming updates.
- Xác nhận lỗi conversion được phát hiện trước cutover.

---

## 6. Replica identity, primary keys và row matching

### 6.1. Vì sao UPDATE/DELETE cần nhận diện row?

Khi publisher phát INSERT, subscriber có thể thêm row mới bằng dữ liệu được gửi. Với UPDATE hoặc DELETE, subscriber cần biết row cũ nào phải thay đổi/xóa. PostgreSQL dùng replica identity để xác định row đó.

Thông thường replica identity là primary key. Một bảng không có primary key vẫn có thể được publish, nhưng cần chọn chiến lược phù hợp nếu publication có UPDATE/DELETE.

### 6.2. Các chế độ replica identity

- DEFAULT: dùng primary key nếu có.
- USING INDEX: dùng một unique index phù hợp được chỉ định.
- FULL: gửi old row values để nhận diện row.
- NOTHING: không gửi replica identity; phù hợp với các workload chỉ INSERT khi không cần old row identity.

Ví dụ:

~~~sql
ALTER TABLE app.events REPLICA IDENTITY DEFAULT;

ALTER TABLE app.audit_log REPLICA IDENTITY FULL;
~~~

Cú pháp USING INDEX yêu cầu index phù hợp với các điều kiện PostgreSQL quy định, ví dụ unique, không partial và có các thuộc tính cần thiết.

### 6.3. Publisher và subscriber phải cùng hiểu row identity

Publisher quyết định old-row identity được gửi trong logical change. Subscriber phải có cách tìm đúng row đích. Với bảng quan trọng, nên giữ primary key/unique key tương thích ở cả hai phía và kiểm tra key values không bị biến đổi trong quá trình type conversion.

Nếu subscriber không thể tìm đúng row, apply UPDATE/DELETE có thể lỗi với thông báo không tìm thấy tuple hoặc không tìm được replica identity. Một số thao tác có thể không phát hiện sai lệch ngay nếu dữ liệu đã drift; do đó cần kiểm tra row counts và keys trước subscription/cutover.

### 6.4. REPLICA IDENTITY FULL

FULL gửi nhiều old-row data hơn và có thể làm tăng WAL/logical stream size, đặc biệt với row rộng. Nó cũng làm việc nhận diện row tốn kém hơn nếu subscriber không có index phù hợp.

Dùng FULL khi thực sự cần và đo overhead. Một primary key ổn định thường là lựa chọn hiệu quả hơn.

### 6.5. Thay đổi primary key

Thay primary key trong lúc logical replication chạy là migration nhiều bước:
1. Tạo candidate unique key trên publisher và subscriber.
2. Backfill/validate uniqueness và NOT NULL.
3. Triển khai ứng dụng tương thích.
4. Chuyển replica identity theo kế hoạch.
5. Xác nhận apply worker tiếp tục bình thường.
6. Chỉ drop key cũ khi mọi consumers đã chuyển.

Không drop primary key trên publisher trong khi publication cần UPDATE/DELETE mà chưa có replica identity thay thế.

### 6.6. Subscriber có primary key khác

Nếu publisher và subscriber dùng các key khác nhau, cần chứng minh subscriber có thể định vị cùng row từ identity data được gửi. Không đổi key tùy tiện chỉ để schema trông gần giống; thử UPDATE/DELETE với dữ liệu thực tế trên đúng versions.

---

## 7. Defaults, generated columns, identity và sequences

### 7.1. Default values

Default là logic chạy khi INSERT không cung cấp giá trị cho column. Trong logical replication, subscriber nhận row values từ publisher cho các replicated columns; không giả định default subscriber sẽ được dùng để thay thế một giá trị publisher đã gửi.

Một subscriber có thêm column với default có thể dùng default khi column đó không được cung cấp trong target INSERT, nhưng hành vi cần được test với publication column lists và version cụ thể.

### 7.2. Defaults phải tương thích về semantics

Hai bên có thể cùng định nghĩa DEFAULT now() nhưng timestamp có thể được tạo ở hai thời điểm khác nhau nếu column không được replicate và default được tính cục bộ. Nếu giá trị phải nhất quán, hãy replicate giá trị từ publisher hoặc dùng một nguồn thời gian/ID có semantics rõ.

Các defaults dùng nextval() cũng có vấn đề riêng: sequence state không tự replicate như row data.

### 7.3. Generated columns

Generated columns được tính từ các cột khác theo expression trên mỗi database. Logical replication không truyền generated-column value như một cột bình thường trong các trường hợp được tài liệu hóa; subscriber có thể tự tính generated value theo definition của nó.

Vì vậy generated expression phải tương thích về semantics. Nếu expression khác nhau giữa publisher và subscriber, cùng row input có thể tạo ra kết quả khác. Kiểm tra version support và generated expression trước cutover.

### 7.4. Identity columns

Identity column có thể dùng sequence để tạo giá trị khi INSERT cục bộ. Trong logical replication, giá trị row được phát từ publisher; subscriber cần được cấu hình để chấp nhận giá trị replicated theo semantics của identity và PostgreSQL version.

Không giả định GENERATED ALWAYS và GENERATED BY DEFAULT có thể thay thế nhau mà không test. Kiểm tra apply với explicit identity values trên staging trước khi bật subscription.

### 7.5. Sequence state không được đồng bộ như row changes

Logical replication không tự đồng bộ trạng thái sequence. Sau initial copy hoặc trong khi subscriber nhận các giá trị identity/serial từ publisher, sequence ở subscriber có thể ở vị trí khác với giá trị row lớn nhất.

Nếu subscriber sẽ được promote và nhận writes:
- Dừng writes/cutover theo runbook.
- Xác định giá trị hiện tại/lớn nhất đã dùng.
- Đồng bộ sequence bằng setval() hoặc công cụ migration phù hợp.
- Xác nhận sequence increment/min/max/cache/cycle.
- Test cấp ID mới trước khi mở traffic.

Không chạy setval trên production trong lúc writes còn tiếp diễn mà không có quy trình khóa/coordination.

### 7.6. Serial và identity khác nhau

serial là shorthand tạo integer column, sequence và default nextval. Identity là tính năng SQL chuẩn hơn với metadata riêng. Cả hai đều có sequence state không tự được logical replication đồng bộ.

### 7.7. Large objects

Large objects được quản lý qua cơ chế riêng và không nằm trong row changes thông thường của logical replication. Nếu schema/application dùng large objects, phải có một quy trình copy/validation riêng hoặc chọn giải pháp migration phù hợp.

---

## 8. Constraints, indexes, triggers và object dependencies

### 8.1. Constraints không được tạo tự động

Subscriber cần có các constraints mong muốn được triển khai riêng. Nếu subscriber thiếu constraint, nó có thể chấp nhận data mà publisher sẽ reject. Nếu subscriber có constraint chặt hơn, apply có thể fail dù publisher đã commit thành công.

Compatibility không chỉ là “có table và columns”; nó còn là behavior của constraints.

### 8.2. NOT NULL

Nếu publisher gửi NULL nhưng subscriber column NOT NULL, apply sẽ thất bại. Trước khi thêm NOT NULL ở subscriber:
1. Backfill dữ liệu hiện tại.
2. Kiểm tra không còn NULL.
3. Triển khai publisher/app để luôn gửi giá trị hợp lệ.
4. Áp constraint theo migration plan.
5. Theo dõi apply errors.

### 8.3. CHECK constraints

CHECK constraint trên subscriber có thể reject row nếu điều kiện khác publisher. Ví dụ publisher cho phép status pending, paid, subscriber chỉ cho paid, cancelled. Cần đồng bộ constraint semantics trước khi publish giá trị mới.

### 8.4. Foreign keys

Foreign key trên subscriber có thể gây apply failure nếu referenced row chưa được apply, không nằm trong publication hoặc thứ tự changes không phù hợp. Nếu replicate nhiều bảng có quan hệ, kiểm tra publication membership, transaction ordering và FK actions.

Không tắt constraints để che apply errors mà không có kế hoạch validate/re-enable. Subscriber data có thể trở nên không nhất quán.

### 8.5. Unique indexes

Unique constraints/indexes có thể phát sinh conflict nếu subscriber đã có local rows hoặc data khác publisher. Một subscription không tự giải quyết duplicate key conflicts. Trước initial copy:
- Xác định subscriber table có dữ liệu sẵn hay không.
- Dùng empty target hoặc quy trình seed được thiết kế.
- Kiểm tra duplicate keys.
- Kiểm soát mọi local writes vào replicated tables.

### 8.6. Indexes

Indexes không được tạo từ publication. Subscriber có thể có indexes khác nhau, nhưng indexes tăng write/apply cost. Một unique index khác publisher có thể reject row mà publisher chấp nhận. Cần cân bằng query performance và apply throughput.

### 8.7. Triggers

Subscriber triggers có thể chạy khi apply rows tùy trigger type/replication role semantics. Trigger có thể:
- Tạo side effects lặp.
- Ghi audit/outbox lần thứ hai.
- Gọi external systems.
- Reject row.
- Thay đổi dữ liệu subscriber khác publisher.

Thiết kế trigger để hiểu replication context, dùng trigger enable/replica semantics phù hợp và test kỹ. Không để trigger subscriber phát lại email/payment/webhook do row được replicate.

### 8.8. Rules, policies và row-level security

Views/rules/RLS policies không được tự replicate. Kiểm tra quyền apply worker và behavior của subscriber tables theo role/replication context của đúng version. Không suy ra RLS sẽ tự lọc changes giống SELECT của ứng dụng.

### 8.9. Views và materialized views

Logical replication không tự đồng bộ view definitions hoặc refresh materialized views. Triển khai definitions trên subscriber và xác định ai refresh materialized views, tần suất và chi phí.

### 8.10. Functions và procedures

Function definitions, procedures, event triggers và scheduled jobs cần được deploy riêng. Nếu trigger hoặc default gọi function, function phải tồn tại trên subscriber với semantics tương thích.

---

## 9. Partitioning, row filters và column lists

### 9.1. Partitioned tables

Publication có thể publish partitioned table theo cấu hình/version. Partitioning ở publisher và subscriber không nhất thiết phải có cùng physical layout trong mọi topology được hỗ trợ, nhưng cần hiểu mapping relation và hành vi khi partition được thêm/xóa.

### 9.2. publish_via_partition_root

Các PostgreSQL versions hỗ trợ option này cho phép publish changes của partitioned table dưới identity của partition root thay vì leaf partition. Điều đó ảnh hưởng relation mapping ở subscriber và cách subscriber table/partition layout được tổ chức.

Kiểm tra version, publication definition và subscriber partitioning trước khi dùng. Không mặc định mọi version có cùng behavior.

### 9.3. Partition layout khác nhau

Subscriber có thể cần partitioning riêng để phục vụ workload read hoặc retention. Khi layout khác publisher, hãy xác định:
- Root table mapping.
- Leaf partition mapping.
- Partition key/type.
- Routing rules trên subscriber.
- Behavior khi partition mới được tạo.
- DDL deployment order.
- Initial table synchronization.

### 9.4. Row filters

Row filter giới hạn rows được publish theo điều kiện. Filter phải dùng các columns/type/functions được hỗ trợ và có semantics phù hợp. Nếu filter dựa vào column bị rename/drop hoặc expression thay đổi, publication có thể cần được cập nhật.

Row filter không phải cơ chế security boundary duy nhất. Subscriber vẫn cần access control và network isolation.

### 9.5. Column lists

Column list cho phép publication chỉ gửi một tập columns. Subscriber mapping phải có các columns cần thiết và ứng dụng cần hiểu columns nào không được replicate. Column list không tự tạo default/data mapping cho các columns còn lại.

### 9.6. TRUNCATE và filters

TRUNCATE là operation ở mức table, không phải row-by-row DELETE. Đừng giả định row filter có thể biến TRUNCATE thành thao tác chỉ xóa subset rows. Kiểm tra semantics của phiên bản và publication options; nếu subscriber có dữ liệu ngoài publication filter, TRUNCATE có thể có tác động rộng hơn dự kiến.

### 9.7. Thêm partition mới

Một partition mới có thể cần được attach trên publisher và có thể thay đổi publication membership/mapping theo cách version-dependent. Kiểm tra subscription table sync state và xác nhận rows mới đi đúng target. DDL partition phải được triển khai theo runbook, không coi việc tạo partition là một DML event được tự động replicate.

---

## 10. Schema evolution: expand-and-contract

### 10.1. Vì sao cần rollout nhiều bước?

Khi publisher và subscriber chạy đồng thời, có một khoảng thời gian hai schema versions cùng tồn tại. Migration phải giữ cho mọi DML trong khoảng đó apply được. Expand-and-contract thêm cấu trúc mới trước, chuyển ứng dụng, rồi mới loại bỏ cấu trúc cũ.

### 10.2. Thêm column mới

Giả sử cần thêm customer_tier:

**Bước 1 — Expand subscriber trước**

~~~sql
ALTER TABLE app.customers
ADD COLUMN customer_tier text;
~~~

**Bước 2 — Expand publisher**

~~~sql
ALTER TABLE app.customers
ADD COLUMN customer_tier text;
~~~

**Bước 3 — Deploy application tương thích**

Ứng dụng cũ vẫn hoạt động khi column còn NULL; ứng dụng mới có thể bắt đầu ghi giá trị sau khi cả hai schema đã sẵn sàng.

**Bước 4 — Backfill và validate**

Kiểm tra null count, value domain và publisher/subscriber parity.

**Bước 5 — Contract khi an toàn**

Chỉ thêm NOT NULL/drop old columns sau khi toàn bộ application versions và subscribers đã chuyển.

Thứ tự chính xác có thể thay đổi theo migration architecture, nhưng subscriber phải sẵn sàng trước khi apply worker nhận row cần column mới.

### 10.3. Rename column

Không rename trực tiếp ở một phía rồi kỳ vọng logical replication tự ánh xạ. Dùng hai columns tạm thời:
1. Add new column trên cả hai.
2. Dual-write hoặc backfill.
3. Chuyển publication column list/mapping nếu có.
4. Chuyển consumers.
5. Stop writing old column.
6. Drop old column ở giai đoạn contract.

### 10.4. Type widening

Ví dụ integer sang bigint:
1. Mở rộng subscriber column trước.
2. Xác minh target accepts mọi publisher values.
3. Mở rộng publisher column.
4. Deploy application hỗ trợ bigint.
5. Kiểm tra indexes/foreign keys/functions/casts.
6. Đo apply throughput và query plan.

Type narrowing cần kiểm tra range trước và thường nên tránh trong khi replication đang hoạt động.

### 10.5. Enum evolution

Khi thêm enum label:
1. Thêm label vào subscriber trước.
2. Kiểm tra label order/semantics.
3. Thêm label vào publisher.
4. Chỉ sau đó ứng dụng mới ghi label mới.
5. Theo dõi apply errors và query behavior.

Không dùng label mới trên publisher trước khi subscriber hiểu label đó.

### 10.6. Constraint tightening

Nếu muốn thêm NOT NULL/unique/check:
1. Backfill.
2. Kiểm tra dữ liệu hiện tại.
3. Tạo/validate constraint theo cách phù hợp.
4. Triển khai application.
5. Đồng bộ constraint trên cả hai phía.
6. Theo dõi apply errors.

### 10.7. Drop table/column

Drop là bước cuối sau khi:
- Không còn application version dùng object.
- Publication/subscription membership được cập nhật.
- Initial sync/refresh đã hoàn tất.
- Backup/rollback path sẵn sàng.
- Monitoring không còn references.
- Consumer downstream đã chuyển.

### 10.8. Migration version table

Có thể duy trì bảng migration version ở mỗi database, nhưng logical replication không tự đồng bộ migration history trừ khi table đó nằm trong publication. Nên quản lý migration state độc lập và ghi lại phiên bản schema của publisher/subscriber trong deployment inventory.

### 10.9. DDL coordination runbook

Mỗi migration cần có:
- Compatibility window.
- Thứ tự apply trên publisher/subscriber.
- Backward/forward compatibility assumptions.
- Initial sync/refresh requirements.
- Rollback plan.
- Data backfill strategy.
- Expected replication lag impact.
- Validation queries.
- Owner và cutover condition.

---

## 11. Publication changes và subscription refresh

### 11.1. Thêm table vào publication

Khi thêm table vào publication sau khi subscription đã tồn tại, subscriber cần refresh publication để biết table mới. Ví dụ trên publisher:

~~~sql
ALTER PUBLICATION app_pub
ADD TABLE app.invoices;
~~~

Sau đó trên subscriber:

~~~sql
ALTER SUBSCRIPTION app_sub
REFRESH PUBLICATION;
~~~

Tùy version và option, refresh có thể khởi tạo table synchronization/copy dữ liệu ban đầu. Kiểm tra đúng syntax và copy_data behavior của release đang chạy.

### 11.2. Refresh không tạo schema

REFRESH PUBLICATION cập nhật danh sách published relations mà subscription theo dõi. Nó không tự chạy CREATE TABLE hoặc ALTER TABLE trên subscriber. Tạo target schema trước khi refresh.

### 11.3. Xóa table khỏi publication

Khi bỏ table khỏi publication, changes tương lai của table đó không còn được gửi theo membership mới. Rows đã tồn tại trên subscriber thường vẫn còn; không mặc định rằng remove table đồng nghĩa DELETE target table/data.

Nếu cần drop hoặc giữ dữ liệu subscriber, thực hiện migration riêng sau khi xác định downstream consumers.

### 11.4. Column list thay đổi

Nếu publication dùng column list, thay đổi list phải được triển khai cùng schema subscriber. Khi thêm column vào list, target cần sẵn sàng trước khi publisher phát values. Khi bỏ column, ứng dụng và subscriber schema vẫn có thể giữ column đó trong một compatibility window.

### 11.5. Row filter thay đổi

Row filter thay đổi phạm vi rows trong stream. Nó không tự xóa rows đã được copy trước đó mà nay không còn thỏa filter. Nếu cần reconcile dữ liệu, lập kế hoạch cleanup/backfill riêng; không giả định refresh tự đồng bộ lại toàn bộ table state.

### 11.6. pg_publication_tables

Có thể xem table membership và row filter/column list theo khả năng version:

~~~sql
SELECT *
FROM pg_publication_tables
WHERE pubname = 'app_pub'
ORDER BY schemaname, tablename;
~~~

Đây là view hữu ích để xác nhận publisher đang publish relation nào. Output fields có thể khác theo version.

### 11.7. pg_publication

~~~sql
SELECT *
FROM pg_publication
WHERE pubname = 'app_pub';
~~~

Kiểm tra flags về publish operations và các options hiện tại. Không chỉ dựa vào migration source code; xem catalog state đang có hiệu lực.

### 11.8. Table synchronization state

Trên subscriber, pg_subscription_rel lưu trạng thái sync của các relations trong subscription. Có thể quan sát:

~~~sql
SELECT
    srrelid::regclass AS relation_name,
    srsubstate,
    srsublsn
FROM pg_subscription_rel
ORDER BY relation_name;
~~~

Các state codes có ý nghĩa riêng theo version; tra tài liệu tương ứng. Chỉ coi table sẵn sàng sau khi initial copy/sync đã hoàn tất và apply đang theo kịp.

---

## 12. Initial table synchronization và schema readiness

### 12.1. Hai giai đoạn dữ liệu

Khi subscription khởi động với copy_data bật, PostgreSQL có thể:
1. Copy snapshot ban đầu của table.
2. Đồng thời theo dõi changes phát sinh trong thời gian copy.
3. Đồng bộ phần changes còn lại.
4. Chuyển table sang trạng thái replication bình thường.

Chi tiết worker/process và state names thay đổi theo version. Schema phải sẵn sàng trước khi copy bắt đầu.

### 12.2. Tránh subscriber có dữ liệu xung đột

Nếu target table đã có data, initial copy có thể gặp duplicate key hoặc unique conflicts. Cần chọn một phương án:
- Subscriber table rỗng trước initial copy.
- Seed dữ liệu theo quy trình được hỗ trợ và tắt copy_data khi phù hợp.
- Dùng migration tool có khả năng validate/coordinate snapshot.
- Restore/seed theo một protocol rõ ràng trước khi bật subscription.

Không tạo một subscriber “gần giống” bằng cách copy thủ công rồi kỳ vọng logical replication tự reconcile mọi rows.

### 12.3. copy_data=false

Tùy version, subscription có option copy_data để không copy initial table contents. Khi chọn false, operator chịu trách nhiệm bảo đảm target đã có dataset baseline tương ứng với publisher và không có gap dữ liệu trước khi streaming bắt đầu.

Đây là một lựa chọn có rủi ro cao nếu không có snapshot/LSN coordination. Không bật chỉ để tránh duplicate key errors.

### 12.4. Initial copy và schema drift

Nếu initial copy thất bại do missing column, type conversion, NOT NULL, unique constraint hoặc extension, sửa schema/target rồi dùng đúng procedure để resume/reinitialize table sync. Đừng drop subscription/slot tùy tiện khi chưa ghi nhận slot ownership và restart position.

### 12.5. Subscription state

Có thể quan sát:

~~~sql
SELECT
    subname,
    pid,
    relid,
    received_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription
ORDER BY subname, relid;
~~~

Các columns có thể khác theo PostgreSQL release. Kết hợp pg_subscription_rel, subscriber logs và pg_stat_activity để hiểu table sync/apply worker.

### 12.6. Table sync không đồng nghĩa application ready

Một table có thể hoàn tất initial sync nhưng application vẫn chưa sẵn sàng nếu:
- Các bảng liên quan chưa sync.
- Constraints/indexes chưa được tạo.
- Sequence state chưa đồng bộ.
- Views/functions/extensions thiếu.
- Business invariants chưa đạt.
- Apply lag vẫn còn.

Cần một readiness gate ở cấp hệ thống.

---

## 13. Phát hiện schema drift giữa publisher và subscriber

### 13.1. Schema drift là gì?

Schema drift là khác biệt ngoài dự kiến giữa hai phía. Có thể là:
- Column thiếu/thừa/đổi tên.
- Data type/typmod khác.
- Nullability/default khác.
- Replica identity/primary key khác.
- Constraints/indexes khác.
- Enum/domain definitions khác.
- Extension/collation version khác.
- Publication membership/filters khác.

Một số khác biệt là có chủ đích, ví dụ subscriber thêm read index. Hãy lưu allowlist để phân biệt intentional drift và lỗi.

### 13.2. So sánh columns

Chạy trên cả publisher và subscriber, lưu kết quả rồi diff:

~~~sql
SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type,
    udt_schema,
    udt_name,
    character_maximum_length,
    numeric_precision,
    numeric_scale,
    is_nullable,
    column_default,
    is_identity,
    identity_generation,
    is_generated,
    generation_expression
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, ordinal_position;
~~~

information_schema có thể lọc theo privileges và một số fields có thể phụ thuộc version. Dùng cùng query và role đủ quyền trên cả hai sides.

### 13.3. So sánh replica identity và primary keys

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relreplident AS replica_identity,
    i.indisprimary,
    i.indisunique,
    pg_get_indexdef(i.indexrelid) AS index_definition
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_index i ON i.indrelid = c.oid
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname, i.indisprimary DESC;
~~~

Catalog query cần xem xét partitioned/inherited tables và index validity. Không dùng một dòng output làm bằng chứng duy nhất cho toàn bộ replica identity behavior.

### 13.4. So sánh constraints

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    con.conname,
    con.contype,
    con.convalidated,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname, con.conname;
~~~

Định nghĩa constraint có thể chứa tên/format khác dù semantics giống nhau. Review diff có hiểu biết thay vì so text một cách máy móc.

### 13.5. So sánh indexes

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename, indexname;
~~~

Subscriber có thể có indexes bổ sung phục vụ read workload; so sánh theo allowlist thay vì yêu cầu mọi index giống hệt.

### 13.6. So sánh publication và subscription

Trên publisher:

~~~sql
SELECT *
FROM pg_publication_tables
ORDER BY pubname, schemaname, tablename;
~~~

Trên subscriber:

~~~sql
SELECT
    subname,
    subenabled,
    subslotname,
    subpublications
FROM pg_subscription;
~~~

Catalog fields thay đổi theo version và có thể chứa connection metadata nhạy cảm. Không xuất connection strings/secrets vào logs hoặc ticket.

### 13.7. Schema fingerprints

Có thể tạo schema fingerprint bằng cách chuẩn hóa metadata cần thiết (table, column, type, constraints, replica identity, publication membership) rồi hash kết quả. Fingerprint cần:
- Chỉ lấy fields có ý nghĩa với compatibility.
- Loại trừ OIDs và metadata thay đổi theo môi trường.
- Chuẩn hóa ordering.
- Có allowlist cho subscriber-only indexes/tables.
- Lưu schema version cùng hash.
- Chạy sau mỗi migration.

Fingerprint phát hiện drift; nó không thay thế semantic review và test data conversion.

### 13.8. Schema contract

Một schema contract nên mô tả:
- Tables/columns được replicate.
- Data type và business meaning.
- Nullable/default rules.
- Primary key/replica identity.
- Publication filters/column lists.
- Partitioning behavior.
- Required extensions/collations/enums.
- Subscriber-only objects.
- Migration order và compatibility window.

---

## 14. Monitoring apply errors và replication health

### 14.1. Subscriber logs

Apply worker errors thường được ghi ở subscriber. Theo dõi:
- Missing target relation/column.
- Type input/conversion failure.
- NOT NULL/CHECK/foreign key violations.
- Duplicate key conflicts.
- Replica identity lookup failures.
- Missing enum labels/extensions/functions.
- Permission errors.
- Worker exit/restart loops.

Một apply error có thể khiến subscription dừng apply; replication lag sau đó tiếp tục tăng.

### 14.2. pg_stat_subscription

View này giúp theo dõi subscription workers, received LSN và thời gian nhận message cuối. Dùng cùng logs để phân biệt:
- Không có connection.
- Có connection nhưng không nhận data.
- Receive tiến nhưng table sync chưa xong.
- Apply worker lỗi và restart.
- Subscriber đã nhận nhưng apply/commit còn chậm.

### 14.3. pg_stat_subscription_stats

Một số PostgreSQL versions có view thống kê lỗi subscription, ví dụ apply errors và sync errors. Kiểm tra availability/columns theo release. Stats reset phải được theo dõi để tính delta.

### 14.4. Publisher-side monitoring

Kết hợp:
- pg_stat_replication cho walsender connections nếu view áp dụng.
- pg_replication_slots để xem logical slot active/restart_lsn.
- pg_stat_wal để hiểu WAL generation.
- Logs của publisher để tìm slot/output plugin errors.
- Disk usage của pg_wal để phát hiện slot giữ WAL.

### 14.5. Slot retention

Logical replication slot giữ WAL cần cho subscriber decode. Nếu subscriber dừng hoặc lag lâu, slot có thể làm pg_wal tăng. Không drop slot nếu chưa xác định subscription/consumer và hậu quả reinitialization.

### 14.6. Lag metrics

Có thể dùng LSN distance giữa current WAL và received/replayed positions, nhưng không quy đổi thành thời gian nếu WAL generation thay đổi mạnh. LSN distance là byte distance; time lag cần timestamps/heartbeat và workload context.

### 14.7. Heartbeat table

Một heartbeat table được publish có thể giúp quan sát end-to-end apply latency:
- Publisher cập nhật heartbeat theo interval.
- Subscriber quan sát timestamp/sequence cuối.
- Dashboard đo thời gian từ source marker tới apply.
- Heartbeat row phải nằm trong publication và schema contract.
- Không dùng heartbeat làm thay thế WAL LSN/slot monitoring.

### 14.8. Alerting

Alert hữu ích:
- Subscription disabled/disconnected.
- Apply worker error mới.
- Last received/apply heartbeat quá cũ khi publisher có writes.
- Replication slot inactive giữ WAL vượt budget.
- pg_wal disk pressure.
- Table sync state không hoàn tất trong SLA.
- Schema fingerprint thay đổi ngoài migration.
- Version pair ngoài compatibility matrix.

Alert phải có cluster, subscription, table, error context và runbook owner.

---

## 15. Troubleshooting schema compatibility

### 15.1. Column does not exist

Nguyên nhân:
- DDL chưa chạy trên subscriber.
- Publisher column list vừa thay đổi.
- Rename không được phối hợp.
- Table sync đang dùng schema cũ.

Xử lý: đọc subscriber log, xác định relation/column, kiểm tra publication column list, triển khai schema subscriber tương thích rồi resume/retry theo procedure.

### 15.2. Type conversion failure

Nguyên nhân:
- Value không parse được.
- Target range/precision nhỏ hơn.
- Enum label thiếu.
- Domain/check constraint reject.
- Extension type/input function không tương thích.

Xử lý: lấy sample row/key an toàn từ logs, kiểm tra source/target definitions, test conversion trên staging và backfill/normalize dữ liệu trước khi resume.

### 15.3. Duplicate key

Nguyên nhân:
- Subscriber đã có seed/local rows.
- Application ghi vào subscriber.
- Initial copy bị chạy lại trên table không rỗng.
- Key mapping/sequence strategy sai.

Xử lý: xác định row conflict, so sánh nguồn authoritative, dừng local writes, chọn reseed hoặc reconcile có kiểm soát. Không xóa row chỉ để worker chạy tiếp khi chưa hiểu ownership.

### 15.4. UPDATE/DELETE không tìm thấy row

Nguyên nhân:
- Subscriber đã drift data.
- Replica identity không tương thích.
- Row bị local process xóa.
- Type conversion làm key khác.
- Initial copy/slot start position không khớp.

Xử lý: kiểm tra key/replica identity ở hai phía, row presence và subscription state; chọn resync/reseed nếu cần.

### 15.5. Foreign key violation

Nguyên nhân:
- Referenced table không nằm trong publication.
- Target rows chưa được seed.
- Apply order/transaction behavior không phù hợp.
- Schema constraints khác nhau.

Xử lý: kiểm tra publication scope, FK graph và data baseline. Không tắt FK vĩnh viễn để che lỗi.

### 15.6. Table sync không hoàn tất

Kiểm tra pg_subscription_rel, sync worker logs, table size, lock contention, network throughput, disk space, conflicts và schema. Nếu restart table sync, cần hiểu copy_data, slot state và khả năng duplicate trước khi thao tác.

### 15.7. Subscriber version cũ hơn publisher

Kiểm tra compatibility direction và protocol support. Không workaround bằng cách hạ schema hoặc tự sửa replication protocol. Dùng subscriber version được hỗ trợ hoặc chọn migration strategy khác.

### 15.8. Publication refresh không thấy table mới

Kiểm tra:
- ALTER PUBLICATION có thành công không.
- Subscription đã REFRESH PUBLICATION chưa.
- Table có đủ quyền/owner và đúng schema không.
- Subscriber target table đã tồn tại chưa.
- Subscription enabled và workers hoạt động không.
- Version có hỗ trợ publication option đang dùng không.

---

## 11. Publication changes và subscription refresh

### 11.1. Thêm table vào publication

Khi thêm table vào publication sau khi subscription đã tồn tại, subscriber cần refresh publication để biết table mới. Ví dụ trên publisher:

~~~sql
ALTER PUBLICATION app_pub
ADD TABLE app.invoices;
~~~

Sau đó trên subscriber:

~~~sql
ALTER SUBSCRIPTION app_sub
REFRESH PUBLICATION;
~~~

Tùy version và option, refresh có thể khởi tạo table synchronization/copy dữ liệu ban đầu. Kiểm tra đúng syntax và copy_data behavior của release đang chạy.

### 11.2. Refresh không tạo schema

REFRESH PUBLICATION cập nhật danh sách published relations mà subscription theo dõi. Nó không tự chạy CREATE TABLE hoặc ALTER TABLE trên subscriber. Tạo target schema trước khi refresh.

### 11.3. Xóa table khỏi publication

Khi bỏ table khỏi publication, changes tương lai của table đó không còn được gửi theo membership mới. Rows đã tồn tại trên subscriber thường vẫn còn; không mặc định rằng remove table đồng nghĩa DELETE target table/data.

Nếu cần drop hoặc giữ dữ liệu subscriber, thực hiện migration riêng sau khi xác định downstream consumers.

### 11.4. Column list thay đổi

Nếu publication dùng column list, thay đổi list phải được triển khai cùng schema subscriber. Khi thêm column vào list, target cần sẵn sàng trước khi publisher phát values. Khi bỏ column, ứng dụng và subscriber schema vẫn có thể giữ column đó trong một compatibility window.

### 11.5. Row filter thay đổi

Row filter thay đổi phạm vi rows trong stream. Nó không tự xóa rows đã được copy trước đó mà nay không còn thỏa filter. Nếu cần reconcile dữ liệu, lập kế hoạch cleanup/backfill riêng; không giả định refresh tự đồng bộ lại toàn bộ table state.

### 11.6. pg_publication_tables

Có thể xem table membership và row filter/column list theo khả năng version:

~~~sql
SELECT *
FROM pg_publication_tables
WHERE pubname = 'app_pub'
ORDER BY schemaname, tablename;
~~~

Đây là view hữu ích để xác nhận publisher đang publish relation nào. Output fields có thể khác theo version.

### 11.7. pg_publication

~~~sql
SELECT *
FROM pg_publication
WHERE pubname = 'app_pub';
~~~

Kiểm tra flags về publish operations và các options hiện tại. Không chỉ dựa vào migration source code; xem catalog state đang có hiệu lực.

### 11.8. Table synchronization state

Trên subscriber, pg_subscription_rel lưu trạng thái sync của các relations trong subscription. Có thể quan sát:

~~~sql
SELECT
    srrelid::regclass AS relation_name,
    srsubstate,
    srsublsn
FROM pg_subscription_rel
ORDER BY relation_name;
~~~

Các state codes có ý nghĩa riêng theo version; tra tài liệu tương ứng. Chỉ coi table sẵn sàng sau khi initial copy/sync đã hoàn tất và apply đang theo kịp.

---

## 12. Initial table synchronization và schema readiness

### 12.1. Hai giai đoạn dữ liệu

Khi subscription khởi động với copy_data bật, PostgreSQL có thể:
1. Copy snapshot ban đầu của table.
2. Đồng thời theo dõi changes phát sinh trong thời gian copy.
3. Đồng bộ phần changes còn lại.
4. Chuyển table sang trạng thái replication bình thường.

Chi tiết worker/process và state names thay đổi theo version. Schema phải sẵn sàng trước khi copy bắt đầu.

### 12.2. Tránh subscriber có dữ liệu xung đột

Nếu target table đã có data, initial copy có thể gặp duplicate key hoặc unique conflicts. Cần chọn một phương án:
- Subscriber table rỗng trước initial copy.
- Seed dữ liệu theo quy trình được hỗ trợ và tắt copy_data khi phù hợp.
- Dùng migration tool có khả năng validate/coordinate snapshot.
- Restore/seed theo một protocol rõ ràng trước khi bật subscription.

Không tạo một subscriber “gần giống” bằng cách copy thủ công rồi kỳ vọng logical replication tự reconcile mọi rows.

### 12.3. copy_data=false

Tùy version, subscription có option copy_data để không copy initial table contents. Khi chọn false, operator chịu trách nhiệm bảo đảm target đã có dataset baseline tương ứng với publisher và không có gap dữ liệu trước khi streaming bắt đầu.

Đây là một lựa chọn có rủi ro cao nếu không có snapshot/LSN coordination. Không bật chỉ để tránh duplicate key errors.

### 12.4. Initial copy và schema drift

Nếu initial copy thất bại do missing column, type conversion, NOT NULL, unique constraint hoặc extension, sửa schema/target rồi dùng đúng procedure để resume/reinitialize table sync. Đừng drop subscription/slot tùy tiện khi chưa ghi nhận slot ownership và restart position.

### 12.5. Subscription state

Có thể quan sát:

~~~sql
SELECT
    subname,
    pid,
    relid,
    received_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription
ORDER BY subname, relid;
~~~

Các columns có thể khác theo PostgreSQL release. Kết hợp pg_subscription_rel, subscriber logs và pg_stat_activity để hiểu table sync/apply worker.

### 12.6. Table sync không đồng nghĩa application ready

Một table có thể hoàn tất initial sync nhưng application vẫn chưa sẵn sàng nếu:
- Các bảng liên quan chưa sync.
- Constraints/indexes chưa được tạo.
- Sequence state chưa đồng bộ.
- Views/functions/extensions thiếu.
- Business invariants chưa đạt.
- Apply lag vẫn còn.

Cần một readiness gate ở cấp hệ thống.

---

## 13. Phát hiện schema drift giữa publisher và subscriber

### 13.1. Schema drift là gì?

Schema drift là khác biệt ngoài dự kiến giữa hai phía. Có thể là:
- Column thiếu/thừa/đổi tên.
- Data type/typmod khác.
- Nullability/default khác.
- Replica identity/primary key khác.
- Constraints/indexes khác.
- Enum/domain definitions khác.
- Extension/collation version khác.
- Publication membership/filters khác.

Một số khác biệt là có chủ đích, ví dụ subscriber thêm read index. Hãy lưu allowlist để phân biệt intentional drift và lỗi.

### 13.2. So sánh columns

Chạy trên cả publisher và subscriber, lưu kết quả rồi diff:

~~~sql
SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type,
    udt_schema,
    udt_name,
    character_maximum_length,
    numeric_precision,
    numeric_scale,
    is_nullable,
    column_default,
    is_identity,
    identity_generation,
    is_generated,
    generation_expression
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, ordinal_position;
~~~

information_schema có thể lọc theo privileges và một số fields có thể phụ thuộc version. Dùng cùng query và role đủ quyền trên cả hai sides.

### 13.3. So sánh replica identity và primary keys

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relreplident AS replica_identity,
    i.indisprimary,
    i.indisunique,
    pg_get_indexdef(i.indexrelid) AS index_definition
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_index i ON i.indrelid = c.oid
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname, i.indisprimary DESC;
~~~

Catalog query cần xem xét partitioned/inherited tables và index validity. Không dùng một dòng output làm bằng chứng duy nhất cho toàn bộ replica identity behavior.

### 13.4. So sánh constraints

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    con.conname,
    con.contype,
    con.convalidated,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname, con.conname;
~~~

Định nghĩa constraint có thể chứa tên/format khác dù semantics giống nhau. Review diff có hiểu biết thay vì so text một cách máy móc.

### 13.5. So sánh indexes

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename, indexname;
~~~

Subscriber có thể có indexes bổ sung phục vụ read workload; so sánh theo allowlist thay vì yêu cầu mọi index giống hệt.

### 13.6. So sánh publication và subscription

Trên publisher:

~~~sql
SELECT *
FROM pg_publication_tables
ORDER BY pubname, schemaname, tablename;
~~~

Trên subscriber:

~~~sql
SELECT
    subname,
    subenabled,
    subslotname,
    subpublications
FROM pg_subscription;
~~~

Catalog fields thay đổi theo version và có thể chứa connection metadata nhạy cảm. Không xuất connection strings/secrets vào logs hoặc ticket.

### 13.7. Schema fingerprints

Có thể tạo schema fingerprint bằng cách chuẩn hóa metadata cần thiết (table, column, type, constraints, replica identity, publication membership) rồi hash kết quả. Fingerprint cần:
- Chỉ lấy fields có ý nghĩa với compatibility.
- Loại trừ OIDs và metadata thay đổi theo môi trường.
- Chuẩn hóa ordering.
- Có allowlist cho subscriber-only indexes/tables.
- Lưu schema version cùng hash.
- Chạy sau mỗi migration.

Fingerprint phát hiện drift; nó không thay thế semantic review và test data conversion.

### 13.8. Schema contract

Một schema contract nên mô tả:
- Tables/columns được replicate.
- Data type và business meaning.
- Nullable/default rules.
- Primary key/replica identity.
- Publication filters/column lists.
- Partitioning behavior.
- Required extensions/collations/enums.
- Subscriber-only objects.
- Migration order và compatibility window.

---

## 14. Monitoring apply errors và replication health

### 14.1. Subscriber logs

Apply worker errors thường được ghi ở subscriber. Theo dõi:
- Missing target relation/column.
- Type input/conversion failure.
- NOT NULL/CHECK/foreign key violations.
- Duplicate key conflicts.
- Replica identity lookup failures.
- Missing enum labels/extensions/functions.
- Permission errors.
- Worker exit/restart loops.

Một apply error có thể khiến subscription dừng apply; replication lag sau đó tiếp tục tăng.

### 14.2. pg_stat_subscription

View này giúp theo dõi subscription workers, received LSN và thời gian nhận message cuối. Dùng cùng logs để phân biệt:
- Không có connection.
- Có connection nhưng không nhận data.
- Receive tiến nhưng table sync chưa xong.
- Apply worker lỗi và restart.
- Subscriber đã nhận nhưng apply/commit còn chậm.

### 14.3. pg_stat_subscription_stats

Một số PostgreSQL versions có view thống kê lỗi subscription, ví dụ apply errors và sync errors. Kiểm tra availability/columns theo release. Stats reset phải được theo dõi để tính delta.

### 14.4. Publisher-side monitoring

Kết hợp:
- pg_stat_replication cho walsender connections nếu view áp dụng.
- pg_replication_slots để xem logical slot active/restart_lsn.
- pg_stat_wal để hiểu WAL generation.
- Logs của publisher để tìm slot/output plugin errors.
- Disk usage của pg_wal để phát hiện slot giữ WAL.

### 14.5. Slot retention

Logical replication slot giữ WAL cần cho subscriber decode. Nếu subscriber dừng hoặc lag lâu, slot có thể làm pg_wal tăng. Không drop slot nếu chưa xác định subscription/consumer và hậu quả reinitialization.

### 14.6. Lag metrics

Có thể dùng LSN distance giữa current WAL và received/replayed positions, nhưng không quy đổi thành thời gian nếu WAL generation thay đổi mạnh. LSN distance là byte distance; time lag cần timestamps/heartbeat và workload context.

### 14.7. Heartbeat table

Một heartbeat table được publish có thể giúp quan sát end-to-end apply latency:
- Publisher cập nhật heartbeat theo interval.
- Subscriber quan sát timestamp/sequence cuối.
- Dashboard đo thời gian từ source marker tới apply.
- Heartbeat row phải nằm trong publication và schema contract.
- Không dùng heartbeat làm thay thế WAL LSN/slot monitoring.

### 14.8. Alerting

Alert hữu ích:
- Subscription disabled/disconnected.
- Apply worker error mới.
- Last received/apply heartbeat quá cũ khi publisher có writes.
- Replication slot inactive giữ WAL vượt budget.
- pg_wal disk pressure.
- Table sync state không hoàn tất trong SLA.
- Schema fingerprint thay đổi ngoài migration.
- Version pair ngoài compatibility matrix.

Alert phải có cluster, subscription, table, error context và runbook owner.

---

## 15. Troubleshooting schema compatibility

### 15.1. Column does not exist

Nguyên nhân:
- DDL chưa chạy trên subscriber.
- Publisher column list vừa thay đổi.
- Rename không được phối hợp.
- Table sync đang dùng schema cũ.

Xử lý: đọc subscriber log, xác định relation/column, kiểm tra publication column list, triển khai schema subscriber tương thích rồi resume/retry theo procedure.

### 15.2. Type conversion failure

Nguyên nhân:
- Value không parse được.
- Target range/precision nhỏ hơn.
- Enum label thiếu.
- Domain/check constraint reject.
- Extension type/input function không tương thích.

Xử lý: lấy sample row/key an toàn từ logs, kiểm tra source/target definitions, test conversion trên staging và backfill/normalize dữ liệu trước khi resume.

### 15.3. Duplicate key

Nguyên nhân:
- Subscriber đã có seed/local rows.
- Application ghi vào subscriber.
- Initial copy bị chạy lại trên table không rỗng.
- Key mapping/sequence strategy sai.

Xử lý: xác định row conflict, so sánh nguồn authoritative, dừng local writes, chọn reseed hoặc reconcile có kiểm soát. Không xóa row chỉ để worker chạy tiếp khi chưa hiểu ownership.

### 15.4. UPDATE/DELETE không tìm thấy row

Nguyên nhân:
- Subscriber đã drift data.
- Replica identity không tương thích.
- Row bị local process xóa.
- Type conversion làm key khác.
- Initial copy/slot start position không khớp.

Xử lý: kiểm tra key/replica identity ở hai phía, row presence và subscription state; chọn resync/reseed nếu cần.

### 15.5. Foreign key violation

Nguyên nhân:
- Referenced table không nằm trong publication.
- Target rows chưa được seed.
- Apply order/transaction behavior không phù hợp.
- Schema constraints khác nhau.

Xử lý: kiểm tra publication scope, FK graph và data baseline. Không tắt FK vĩnh viễn để che lỗi.

### 15.6. Table sync không hoàn tất

Kiểm tra pg_subscription_rel, sync worker logs, table size, lock contention, network throughput, disk space, conflicts và schema. Nếu restart table sync, cần hiểu copy_data, slot state và khả năng duplicate trước khi thao tác.

### 15.7. Subscriber version cũ hơn publisher

Kiểm tra compatibility direction và protocol support. Không workaround bằng cách hạ schema hoặc tự sửa replication protocol. Dùng subscriber version được hỗ trợ hoặc chọn migration strategy khác.

### 15.8. Publication refresh không thấy table mới

Kiểm tra:
- ALTER PUBLICATION có thành công không.
- Subscription đã REFRESH PUBLICATION chưa.
- Table có đủ quyền/owner và đúng schema không.
- Subscriber target table đã tồn tại chưa.
- Subscription enabled và workers hoạt động không.
- Version có hỗ trợ publication option đang dùng không.

---

## 16. Nâng cấp major version bằng logical replication

### 16.1. Khi nào chọn logical replication?

Logical replication có thể phù hợp khi:
- Database lớn và cần giảm downtime so với dump/restore.
- Có thể chạy publisher cũ và subscriber mới song song.
- Ứng dụng chịu được một cutover window ngắn.
- Schema có thể được chuẩn bị tương thích.
- Không phụ thuộc vào object/data không được logical replication chuyển tự động.
- Có đủ capacity để chạy hai clusters và initial copy.

### 16.2. Khi nào nên cân nhắc phương án khác?

Logical replication có thể không phù hợp nếu:
- Ứng dụng dùng nhiều large objects cần chuyển riêng.
- Có schema/type phức tạp khó giữ compatibility.
- Workload có DDL thường xuyên và không thể phối hợp migration.
- Subscriber cần dữ liệu chính xác từ sequence state ngay trong quá trình chạy.
- Có nhiều local writes trên subscriber.
- Downtime có thể chấp nhận và dump/restore hoặc pg_upgrade đơn giản hơn.

### 16.3. So sánh các phương pháp major upgrade

| Phương pháp | Đặc điểm | Điều cần cân nhắc |
|---|---|---|
| pg_upgrade | Nâng major version tại chỗ/side-by-side theo cơ chế supported | Downtime, compatibility extension, rollback window |
| Dump/restore | Export/import logic | Thời gian dump/restore, object coverage, sequence/global state |
| Logical replication | Copy baseline rồi stream changes | Schema coordination, unsupported objects, cutover correctness |
| Physical replica upgrade workflow | Theo quy trình hỗ trợ cụ thể của tool/vendor | WAL format/major version restrictions, tool-specific process |

Không có một phương pháp tốt nhất cho mọi hệ thống. Chọn theo downtime budget, database size, feature use và khả năng kiểm chứng.

### 16.4. Pre-upgrade inventory

Lập inventory:
- PostgreSQL major/minor versions.
- Database encoding/collation.
- Extensions và versions.
- Tables/partitioned tables.
- Primary keys/replica identities.
- Sequences/identity columns.
- Large objects.
- Unlogged/temp tables.
- Publications/subscriptions/slots.
- DDL migrations đang chờ.
- Custom types/domains/enums.
- Triggers/functions/rules.
- Foreign keys và unique constraints.
- Roles/grants/RLS.
- Jobs/schedulers/external integrations.

### 16.5. Dựng subscriber mới

1. Cài PostgreSQL major version đích.
2. Cài extensions/binaries đúng version.
3. Tạo roles, schemas, types và tables.
4. Tạo indexes/constraints phù hợp với initial copy/apply.
5. Tạo publication-compatible mapping.
6. Cấu hình WAL, replication privileges và network.
7. Tạo subscription.
8. Theo dõi initial table synchronization.
9. Validate counts/keys/business invariants.
10. Chờ streaming catch-up.

### 16.6. Publications trong upgrade

Có thể tạo publication tường minh:

~~~sql
CREATE PUBLICATION upgrade_pub
FOR TABLE app.customers, app.orders, app.order_items;
~~~

Hoặc dùng publication FOR ALL TABLES khi phù hợp với version, ownership và scope. Publication ALL TABLES có thể tự bao gồm tables mới theo semantics của nó; vẫn phải tạo target schema trên subscriber và hiểu object restrictions.

### 16.7. Tạo subscription

~~~sql
CREATE SUBSCRIPTION upgrade_sub
CONNECTION 'host=old-primary.example.net port=5432 dbname=appdb user=replicator'
PUBLICATION upgrade_pub
WITH (copy_data = true, create_slot = true, enabled = true);
~~~

Ví dụ dùng tên/credentials minh họa. Trong production:
- Lưu secret trong secret manager.
- Dùng TLS/verify-ca hoặc verify-full phù hợp.
- Cấu hình pg_hba.conf/roles least privilege.
- Kiểm tra slot được tạo đúng và có owner.
- Chú ý initial copy có thể tạo load lớn trên publisher.

### 16.8. Capacity trong thời gian dual-cluster

Initial copy và logical decoding tạo thêm load:
- Read I/O trên publisher.
- Network throughput.
- Disk/write I/O trên subscriber.
- WAL retention bởi logical slot.
- CPU cho decoding/apply/index maintenance.
- Storage tăng do hai copies tồn tại.
- Monitoring/backup của cả hai clusters.

Dự trù đủ disk headroom. Nếu subscriber lag, logical slot có thể giữ WAL trên publisher và gây đầy pg_wal.

### 16.9. Chuyển schema trong upgrade

Giữ application tương thích với cả hai schema trong giai đoạn migration. Nếu target major version có behavior/type changes, test queries, casts, collations, extensions và functions. Logical replication không tự sửa schema hoặc application SQL.

### 16.10. Cutover

Một cutover có kiểm soát:
1. Freeze DDL và deploy window.
2. Dừng writes mới trên publisher hoặc đưa ứng dụng vào maintenance/read-only mode.
3. Chờ transactions đang mở kết thúc.
4. Ghi final publisher LSN/marker.
5. Chờ subscriber apply hoàn tất tới final marker/LSN bằng origin progress phù hợp.
6. Xác nhận table sync state, row counts và business checks.
7. Dừng/disable subscription theo runbook.
8. Cập nhật application connection/routing sang subscriber.
9. Mở writes trên cluster mới.
10. Theo dõi errors, sequence values, latency và business metrics.

pg_stat_subscription.latest_end_lsn là thông tin progress được báo về, nhưng không nên dùng riêng nó làm bằng chứng rằng mọi transaction đã apply xong. Dùng replication-origin progress/apply state và một marker transaction được xác nhận.

### 16.11. Sequence handoff

Trước khi mở writes ở subscriber, đồng bộ sequence values để ID mới không đụng với những IDs đã replicate. Cần tính tới:
- Maximum key hiện tại.
- Increment/min/max.
- is_called.
- Cache/preallocated values.
- Sequences dùng chung giữa nhiều tables.
- Sequence cycling.

### 16.12. Rollback sau cutover

Sau khi subscriber bắt đầu nhận writes độc lập, không thể đơn giản chuyển traffic về publisher cũ vì publisher không nhận những writes mới. Cần:
- Giữ publisher cũ read-only.
- Lưu final cutover markers.
- Có rollback window và điều kiện rõ.
- Nếu đã phát sinh writes trên subscriber, phải có phương án reconcile/reverse replication hoặc restore/replay phù hợp.
- Không mở writes đồng thời trên cả hai phía nếu không có conflict strategy được thiết kế.

---

## 17. Security và operational boundaries

### 17.1. Replication role

Tạo role riêng với quyền tối thiểu cần thiết. Logical replication cần quyền replication/connection và quyền đọc tables cho initial copy theo version/config. Không dùng superuser làm replication account chỉ vì tiện.

### 17.2. pg_hba.conf và network

Cho phép đúng source IP/subscriber host, database và replication user. Dùng TLS khi qua network không tin cậy; xác minh certificate/hostname và rotate credentials theo policy.

### 17.3. Password/connection strings

Connection strings có thể chứa secrets và được lưu trong catalog metadata. Hạn chế quyền xem catalog, không log raw conninfo, dùng secret rotation procedure và kiểm tra backup/exports không làm lộ credentials.

### 17.4. Publication scope

Chỉ publish tables/columns cần thiết. Dữ liệu không cần thiết không nên được chuyển qua replication chỉ vì dùng FOR ALL TABLES. Row filters/column lists có thể giảm scope nhưng không thay security design.

### 17.5. Subscriber access

Subscriber thường được ứng dụng đọc. Hạn chế local writes vào replicated tables và tách schema/table local-only. Dùng role privileges để ngăn sửa nhầm replicated data.

---

## 18. Preflight checklist trước khi bật subscription

### 18.1. Version

- [ ] Publisher/subscriber major versions theo hướng được hỗ trợ.
- [ ] Replication protocol/output plugin tương thích.
- [ ] Publication options có trên publisher version.
- [ ] Monitoring views/columns có trên cả hai.
- [ ] Extensions cài đúng major version.

### 18.2. Schema

- [ ] Target tables tồn tại.
- [ ] Published columns có mapping hợp lệ.
- [ ] Data types/typmods tương thích.
- [ ] Nullability/default/generated/identity semantics đã test.
- [ ] Primary key/replica identity phù hợp cho UPDATE/DELETE.
- [ ] Enum/domain/collation definitions tương thích.
- [ ] Constraints không reject publisher rows.
- [ ] Subscriber-only columns có default/nullable/generated behavior đúng.
- [ ] Partition mapping và publication options đã xác nhận.

### 18.3. Data baseline

- [ ] Subscriber table rỗng hoặc seed có kiểm soát.
- [ ] Initial copy/copy_data policy rõ.
- [ ] Duplicate key risk được kiểm tra.
- [ ] Foreign key dependencies có trong scope hoặc được xử lý.
- [ ] Sequence state có handoff plan.
- [ ] Large objects/unsupported objects có migration plan.

### 18.4. Operations

- [ ] Replication role, pg_hba và TLS hoạt động.
- [ ] Slot owner/restart position được ghi nhận.
- [ ] Disk/WAL headroom đủ.
- [ ] Initial copy bandwidth được ước lượng.
- [ ] Apply errors/lag có alert.
- [ ] DDL change process được freeze/coordinate.
- [ ] Rollback/cutover owner và criteria rõ.

---

## 19. Bài lab: schema compatibility và publication refresh

### 19.1. Chuẩn bị publisher

~~~sql
CREATE SCHEMA IF NOT EXISTS compat_lab;

CREATE TABLE compat_lab.accounts (
    account_id bigint PRIMARY KEY,
    display_name text NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE PUBLICATION compat_pub
FOR TABLE compat_lab.accounts;
~~~

### 19.2. Chuẩn bị subscriber

Tạo schema/table tương ứng trước khi tạo subscription:

~~~sql
CREATE SCHEMA IF NOT EXISTS compat_lab;

CREATE TABLE compat_lab.accounts (
    account_id bigint PRIMARY KEY,
    display_name text NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
~~~

### 19.3. Tạo subscription

~~~sql
CREATE SUBSCRIPTION compat_sub
CONNECTION 'host=publisher.lab port=5432 dbname=appdb user=replicator'
PUBLICATION compat_pub;
~~~

Theo dõi initial sync và kiểm tra rows sau khi table đã ready.

### 19.4. Thêm subscriber-only column

Trên subscriber:

~~~sql
ALTER TABLE compat_lab.accounts
ADD COLUMN local_note text;
~~~

Thử INSERT trên publisher. Quan sát subscriber nhận row và local_note có NULL/default theo schema của nó. Không dùng local_note làm dữ liệu nguồn authoritative nếu nó không được publish.

### 19.5. Thêm cột mới theo đúng thứ tự

Trên subscriber trước:

~~~sql
ALTER TABLE compat_lab.accounts
ADD COLUMN tier text;
~~~

Sau đó trên publisher:

~~~sql
ALTER TABLE compat_lab.accounts
ADD COLUMN tier text;
~~~

Ghi row mới với tier và xác nhận apply thành công.

### 19.6. Type widening

Trên subscriber, mở rộng display hoặc numeric test column trước; sau đó thay đổi publisher theo kế hoạch. Kiểm tra values lớn và xác nhận subscriber không reject conversion. Không dùng type narrowing trong lab này nếu chưa lưu dữ liệu test/rollback.

### 19.7. Publication refresh

Trên publisher:

~~~sql
CREATE TABLE compat_lab.regions (
    region_id integer PRIMARY KEY,
    region_name text NOT NULL
);

ALTER PUBLICATION compat_pub
ADD TABLE compat_lab.regions;
~~~

Tạo target table trên subscriber, sau đó chạy:

~~~sql
ALTER SUBSCRIPTION compat_sub
REFRESH PUBLICATION;
~~~

Theo dõi pg_subscription_rel để xác nhận table sync state hoàn tất.

### 19.8. So sánh schema metadata

Chạy query information_schema.columns trên cả hai databases, export kết quả và diff. Ghi lại intentional differences như local_note; không coi mọi difference là lỗi.

---

## 20. Bài lab: replica identity và apply behavior

### 20.1. Tạo bảng không có primary key

Trên publisher:

~~~sql
CREATE TABLE compat_lab.no_key (
    code text NOT NULL,
    payload text NOT NULL
);

ALTER PUBLICATION compat_pub
ADD TABLE compat_lab.no_key;
~~~

Tạo target tương ứng trên subscriber. Khi cần publish UPDATE/DELETE, chọn replica identity phù hợp trước khi chạy DML.

### 20.2. Thử REPLICA IDENTITY FULL

~~~sql
ALTER TABLE compat_lab.no_key
REPLICA IDENTITY FULL;
~~~

Thực hiện INSERT, UPDATE và DELETE trên publisher; quan sát apply ở subscriber. Ghi nhận lượng dữ liệu/logical WAL tăng và so sánh với bảng có primary key.

### 20.3. Thử unique index

Tạo unique index đủ điều kiện làm replica identity trên publisher và subscriber; chuyển REPLICA IDENTITY USING INDEX. Kiểm tra index validity, uniqueness, NOT NULL semantics và apply UPDATE/DELETE.

### 20.4. Thử mismatch có kiểm soát

Trong một lab riêng:
- Thêm CHECK constraint chặt hơn trên subscriber.
- Phát một row không thỏa điều kiện đó từ publisher.
- Quan sát apply error trong subscriber logs.
- Ghi lại subscription state/worker behavior.
- Sửa schema hoặc dữ liệu theo phương án đã định và resume bằng procedure đúng version.

Không làm test mismatch trên subscription dùng chung với dữ liệu cần giữ.

---

## 21. Bài tập thực hành

Các câu hỏi dùng PostgreSQL lab. Không thay đổi schema/replication trên production chỉ để kiểm tra một giả thuyết.

### Bài 1 — Logical replication

Logical replication đồng bộ những gì? Những loại object nào cần migration riêng?

### Bài 2 — Publisher và subscriber

Phân biệt publisher, publication, subscriber và subscription.

### Bài 3 — Version direction

Vì sao thường dùng publisher major version cũ và subscriber major version mới khi nâng cấp?

### Bài 4 — DDL

CREATE TABLE hoặc ALTER TABLE trên publisher có tự xuất hiện ở subscriber không? Cần làm gì?

### Bài 5 — Column mapping

Columns được ánh xạ theo tên hay ordinal position? Vì sao điều này quan trọng khi thêm column?

### Bài 6 — Extra subscriber column

Subscriber có thêm nullable column không nằm trong publication. Điều gì xảy ra khi publisher INSERT row?

### Bài 7 — Missing subscriber column

Publisher bắt đầu publish một column mới nhưng subscriber chưa có. Vì sao phải chuẩn bị schema trước?

### Bài 8 — Type widening

Vì sao integer sang bigint thường dễ triển khai hơn bigint sang integer?

### Bài 9 — Type conversion

text publisher sang uuid subscriber có luôn an toàn không? Nêu điều kiện.

### Bài 10 — Timestamp

Vì sao timestamp without time zone và timestamptz không nên coi là cùng semantics?

### Bài 11 — Enum

Publisher thêm enum label mới. Thứ tự triển khai an toàn trên subscriber và publisher là gì?

### Bài 12 — Domain

Subscriber domain có CHECK constraint chặt hơn publisher. Điều gì có thể xảy ra khi apply row?

### Bài 13 — Collation

Khác collation/ICU version có thể ảnh hưởng những hành vi nào?

### Bài 14 — Replica identity

Replica identity dùng để làm gì? DEFAULT, USING INDEX, FULL và NOTHING khác nhau ra sao?

### Bài 15 — Primary key

Vì sao UPDATE/DELETE cần replica identity phù hợp? Điều gì xảy ra nếu subscriber data đã drift?

### Bài 16 — Sequence

Logical replication có đồng bộ sequence current value không? Cần làm gì trước khi promote subscriber?

### Bài 17 — Generated columns

Vì sao generated expressions phải tương thích giữa hai phía?

### Bài 18 — Triggers

Trigger trên subscriber có thể gây side effects gì khi apply replicated rows?

### Bài 19 — Foreign keys

Subscriber có FK tham chiếu bảng không được publish. Có thể xảy ra lỗi gì?

### Bài 20 — Partitioning

publish_via_partition_root ảnh hưởng điều gì? Vì sao cần version-gate?

### Bài 21 — Row filters

Nếu row filter thay đổi, rows đã được copy nhưng nay không thỏa filter có tự bị xóa khỏi subscriber không?

### Bài 22 — TRUNCATE

Vì sao phải đặc biệt thận trọng với TRUNCATE trong publication có row filters?

### Bài 23 — Publication refresh

Sau khi ADD TABLE vào publication, subscriber cần thao tác gì? Thao tác đó có tạo target schema không?

### Bài 24 — Initial copy

copy_data=false yêu cầu operator bảo đảm điều gì?

### Bài 25 — Duplicate key

Initial copy gặp duplicate key. Nêu các nguyên nhân có thể và cách xử lý an toàn.

### Bài 26 — Schema drift

Liệt kê ít nhất sáu loại schema drift có thể làm apply lỗi hoặc dữ liệu khác semantics.

### Bài 27 — Schema fingerprint

Một fingerprint schema nên bao gồm fields nào và loại trừ những metadata nào?

### Bài 28 — Monitoring

Nêu vai trò của pg_stat_subscription, pg_subscription_rel và subscriber logs.

### Bài 29 — Slot retention

Vì sao logical replication slot có thể làm pg_wal tăng? Có nên drop slot inactive ngay không?

### Bài 30 — Major upgrade

Nêu các giai đoạn của một major upgrade bằng logical replication từ preflight tới cutover.

### Bài 31 — Final LSN

Vì sao không nên dùng riêng pg_stat_subscription.latest_end_lsn làm bằng chứng tất cả transactions đã apply?

### Bài 32 — Cutover writes

Vì sao cần dừng writes trên publisher trước khi chuyển ứng dụng sang subscriber?

### Bài 33 — Rollback

Sau khi subscriber đã nhận writes mới, vì sao không thể đơn giản quay về publisher cũ?

### Bài 34 — Extensions

Vì sao extension binaries phải được cài riêng trên subscriber major version mới?

### Bài 35 — Large objects

Logical replication có tự chuyển large objects không? Cần chuẩn bị gì?

### Bài 36 — Schema contract

Một schema contract cần ghi những nội dung nào để giảm drift?

### Bài 37 — Subscriber-only index

Subscriber thêm index phục vụ reads. Đây có nhất thiết là schema incompatibility không? Cần cân nhắc gì?

### Bài 38 — DDL deployment

Viết trình tự expand-and-contract khi thêm một NOT NULL column mới.

### Bài 39 — Apply error

Subscriber log báo invalid input syntax for type uuid. Nêu quy trình điều tra và sửa.

### Bài 40 — Tổng hợp

Một subscriber mới hơn publisher, initial copy thành công nhưng sau migration enum mới, apply worker lỗi. Hãy nêu nguyên nhân, cách xử lý và cách ngăn tái diễn.

---

## 22. Lời giải — bài 1 đến 20

### Bài 1 — Logical replication

Nó đồng bộ row changes của các tables trong publication theo operations được bật. DDL, roles/grants, indexes, constraints, functions, views, extension binaries, sequence state và large objects cần quy trình riêng.

### Bài 2 — Publisher và subscriber

Publisher tạo publication và phát changes; publication xác định tables/operations; subscriber tạo subscription kết nối và apply changes vào target tables.

### Bài 3 — Version direction

Subscriber mới hơn thường hỗ trợ replication protocol/features của publisher cũ và phù hợp major upgrade. Hướng publisher mới sang subscriber cũ không được mặc định hỗ trợ; cần kiểm tra compatibility docs đúng release.

### Bài 4 — DDL

Không. Logical replication không tự đồng bộ DDL. Dùng migration tool/deployment script để tạo/alter schema tương thích trên subscriber theo thứ tự an toàn.

### Bài 5 — Column mapping

Ánh xạ theo tên column, không theo ordinal position. Vì vậy reorder columns không phải mapping strategy; tên, type và semantics mới quan trọng.

### Bài 6 — Extra subscriber column

Nếu column nullable hoặc có cách cung cấp giá trị hợp lệ, subscriber có thể apply row và column bổ sung nhận NULL/default theo insert behavior. Test với exact publication column list và version; NOT NULL không default có thể làm apply fail.

### Bài 7 — Missing subscriber column

Subscriber không tự tạo column. Khi publisher bắt đầu gửi giá trị cho column mới, mapping/target schema có thể không tương thích. Thêm và xác nhận column ở subscriber trước khi publish writes mới.

### Bài 8 — Type widening

Bigint chứa toàn bộ integer range; integer không chứa toàn bộ bigint range. Mở rộng thường giữ mọi giá trị hiện có, còn thu hẹp có nguy cơ overflow.

### Bài 9 — Type conversion

Không. Mọi source value phải có representation parse được thành UUID và target constraints phải chấp nhận. Kiểm tra dữ liệu cũ/mới và malformed strings trước migration.

### Bài 10 — Timestamp

timestamp without time zone là local date/time không gắn instant; timestamptz biểu diễn instant được hiển thị theo session timezone. Conversion có thể đổi ý nghĩa thời điểm.

### Bài 11 — Enum

Thêm label trên subscriber trước, xác nhận definition/order, sau đó thêm trên publisher và chỉ sau đó ứng dụng mới phát giá trị label mới.

### Bài 12 — Domain

Apply row có thể bị subscriber reject do CHECK/domain constraint chặt hơn, khiến apply worker báo lỗi và lag tăng. Đồng bộ semantics hoặc chuẩn hóa dữ liệu trước khi publish.

### Bài 13 — Collation

Có thể thay đổi sort order, equality/comparison, unique index behavior và query results. Kiểm tra provider/locale/version và reindex requirements.

### Bài 14 — Replica identity

Nó cung cấp old-row identity cho UPDATE/DELETE. DEFAULT dùng primary key; USING INDEX dùng unique index phù hợp; FULL gửi old row values; NOTHING không gửi identity và chỉ phù hợp khi không cần UPDATE/DELETE identity.

### Bài 15 — Primary key

Apply cần xác định row target. Nếu subscriber data drift hoặc key khác, UPDATE/DELETE có thể không tìm thấy row hoặc thay đổi sai; cần validate key parity và resync nếu cần.

### Bài 16 — Sequence

Không. Trước promotion, đồng bộ sequence state/next values bằng setval hoặc công cụ phù hợp sau khi dừng writes và xác định IDs đã dùng; kiểm tra increment/cache/is_called.

### Bài 17 — Generated columns

Subscriber tự tính expression từ input columns; expression khác có thể tạo kết quả khác publisher. Đồng bộ definition và test values.

### Bài 18 — Triggers

Trigger có thể ghi audit/outbox lặp, gửi email/payment/webhook, reject row hoặc thay đổi bảng khác. Thiết kế trigger hiểu replication role và chặn side effects ngoài ý muốn.

### Bài 19 — Foreign keys

Apply row có thể fail FK vì referenced row không tồn tại/không được publish hoặc baseline không đồng bộ. Kiểm tra publication scope, order và data baseline.

### Bài 20 — Partitioning

Option quyết định changes được publish dưới identity partition root hay leaf relation, ảnh hưởng target mapping. Hành vi và option support thay đổi theo major version nên cần version-gate.

---

## 23. Lời giải — bài 21 đến 40

### Bài 21 — Row filters

Không. Thay đổi filter điều chỉnh changes được gửi trong tương lai; rows đã copy trước đó mà không còn thỏa filter thường vẫn ở subscriber. Cần cleanup/reconcile riêng nếu business yêu cầu.

### Bài 22 — TRUNCATE

TRUNCATE là operation table-level, không phải row-level delete. Row filter không biến TRUNCATE thành xóa subset; subscriber có thể truncate toàn table tương ứng. Kiểm tra semantics/version và tránh publish TRUNCATE nếu subscriber chứa rows ngoài filtered set cần giữ.

### Bài 23 — Publication refresh

Sau ADD TABLE trên publisher, chạy ALTER SUBSCRIPTION ... REFRESH PUBLICATION trên subscriber. Refresh cập nhật membership và có thể khởi tạo table sync; nó không tạo target schema.

### Bài 24 — Initial copy

Operator phải bảo đảm subscriber baseline đúng với publisher tại điểm bắt đầu streaming, không thiếu hoặc duplicate rows và có snapshot/LSN coordination rõ. Nếu không, sẽ có data gap hoặc divergence.

### Bài 25 — Duplicate key

Nguyên nhân gồm subscriber đã seed/local rows, application ghi vào subscriber, initial copy chạy lại hoặc key mapping sai. So sánh authoritative source, dừng local writes, chọn empty target/reseed/reconcile có kiểm soát và kiểm tra slot/sync state trước retry.

### Bài 26 — Schema drift

Ví dụ: column thiếu/đổi tên, type/typmod khác, nullability/default khác, replica identity/PK khác, enum/domain khác, collation/extension khác, constraints/indexes khác và publication filter/membership khác.

### Bài 27 — Schema fingerprint

Bao gồm relation/column names, type/typmod, nullability/default/generated, replica identity/PK, constraints, required indexes, enum/domain/collation, publication membership/filter/column lists. Loại OIDs, physical file locations và metadata thay đổi theo môi trường; dùng allowlist cho subscriber-only objects.

### Bài 28 — Monitoring

pg_stat_subscription cho worker/receive progress; pg_subscription_rel cho table sync state; subscriber logs cho apply errors cụ thể như type/constraint/identity failures. Kết hợp cả ba để biết data đã được nhận và apply tới đâu.

### Bài 29 — Slot retention

Logical slot giữ WAL cần cho decoding từ restart position. Subscriber lag/disconnect có thể làm slot giữ nhiều WAL. Không drop inactive slot ngay; xác định owner/consumer, khả năng reconnect và hậu quả reinitialize trước khi xử lý.

### Bài 30 — Major upgrade

Preflight inventory/version/schema/extensions; dựng subscriber mới; tạo schema/roles/publication/subscription; initial copy; monitor apply/lag; validate data; freeze DDL/writes; chờ final marker/LSN apply; đồng bộ sequences; cutover app; monitor; giữ rollback window có kiểm soát.

### Bài 31 — Final LSN

latest_end_lsn là progress/feedback từ publisher, không tự chứng minh transaction cuối cùng đã được apply/commit trên subscriber. Cần dùng apply/origin progress, table sync state và marker transaction.

### Bài 32 — Cutover writes

Nếu publisher tiếp tục nhận writes sau khi subscriber được chọn làm primary, subscriber sẽ thiếu các changes mới. Dừng writes và drain transactions tạo một final boundary để xác nhận toàn bộ changes trước cutover đã apply.

### Bài 33 — Rollback

Publisher cũ không nhận writes đã phát sinh trên subscriber sau cutover. Chuyển traffic về sẽ mất những writes đó hoặc tạo divergence. Cần reverse replication/reconciliation hoặc restore/replay theo kế hoạch.

### Bài 34 — Extensions

Logical replication chuyển row data, không cài shared libraries/binaries. Major version mới cần package extension tương thích, SQL extension objects và type/function/operator definitions trước khi apply data dùng chúng.

### Bài 35 — Large objects

Không tự chuyển large objects như row changes thông thường. Cần export/copy/restore riêng, kiểm tra OID/reference mapping và xác minh ứng dụng đọc được trên subscriber.

### Bài 36 — Schema contract

Ghi tables/columns, types/business meaning, nullability/default, primary key/replica identity, publication filters/column lists, partitioning, enums/domains/extensions/collations, subscriber-only objects, migration order, compatibility window và validation criteria.

### Bài 37 — Subscriber-only index

Không nhất thiết. Index bổ sung có thể là khác biệt có chủ đích để phục vụ reads. Cần bảo đảm không thêm unique constraint gây reject rows mà publisher chấp nhận, và đo write/apply overhead.

### Bài 38 — DDL deployment

1. Add column nullable trên subscriber.
2. Add column nullable trên publisher.
3. Deploy application tương thích.
4. Backfill dữ liệu và kiểm tra parity.
5. Bảo đảm mọi writes có giá trị hợp lệ.
6. Validate không còn NULL.
7. Thêm NOT NULL theo quy trình phù hợp trên subscriber/publisher.
8. Theo dõi apply và app.
9. Chỉ contract/drop old fields khi consumers đã chuyển.

### Bài 39 — Apply error

Xác định relation/column/key gây lỗi từ subscriber logs. Kiểm tra source values, target UUID type, malformed strings, nulls và casts. Chuẩn hóa dữ liệu publisher trước khi phát, hoặc dùng migration/canonical column có kiểm soát. Sau đó sửa target/schema nếu cần, resume worker theo version procedure và xác minh row parity.

### Bài 40 — Enum migration

Subscriber thiếu enum label mới vì DDL không được replicate. Apply worker nhận text label không tồn tại trong target enum và lỗi. Thêm label trên subscriber trước, xác minh order/semantics, rồi publisher/app mới phát label đó. Ngăn tái diễn bằng migration ordering, schema contract, preflight enum diff và test trên staging.

---

## 24. Bảng tra cứu compatibility

| Thành phần | Có tự replicate không? | Việc cần làm |
|---|---|---|
| INSERT/UPDATE/DELETE rows | Có nếu publication bật operation | Đảm bảo schema/identity tương thích |
| TRUNCATE | Có nếu publication bật operation | Kiểm tra tác động table-level và row filters |
| CREATE/ALTER/DROP TABLE | Không | Chạy DDL migration hai phía |
| Column definitions/types | Không | Schema contract và migration |
| Indexes/constraints | Không | Tạo/validate riêng |
| Triggers/functions | Không | Deploy riêng, tránh side effects |
| Sequence state | Không | Đồng bộ khi seed/cutover |
| Large objects | Không theo row replication thông thường | Copy/validate riêng |
| Roles/grants | Không | Provision riêng |
| Extensions/binaries | Không | Cài version tương thích |
| Views/materialized views | Không | Deploy/refresh riêng |
| Publication membership | Được cấu hình ở publisher | Refresh subscription khi cần |
| Row filter/column list | Publication config | Version-gate và schema coordination |
| Replica identity | Phải cấu hình phù hợp | Kiểm tra publisher và target row matching |

---

## 25. Tổng kết

Khả năng tương thích của logical replication không chỉ là hai server kết nối được. Nó là sự phù hợp giữa version/protocol, publication membership, relation/column mapping, type conversion, replica identity và các constraints/objects phụ thuộc.

Các điểm cần nhớ:

1. Subscriber thường phải cùng major version hoặc mới hơn publisher theo compatibility policy; kiểm tra đúng hướng/version pair.
2. Logical replication chuyển row changes; DDL, sequence state, large objects, extensions và schema objects cần quản lý riêng.
3. Columns được ánh xạ theo tên, không theo vị trí; mọi migration cần giữ mapping apply được.
4. Data type khác nhau chỉ an toàn sau khi test conversion, range, precision và semantics.
5. UPDATE/DELETE cần replica identity phù hợp; primary key ổn định thường là lựa chọn tốt.
6. Defaults, generated columns, identity và sequences có semantics khác nhau; sequence state không tự đồng bộ.
7. Constraints, indexes và triggers trên subscriber có thể reject hoặc tạo side effects khi apply.
8. Partitioning, row filters, column lists và TRUNCATE phải được kiểm tra theo PostgreSQL version.
9. Dùng expand-and-contract để schema cũ/mới cùng tồn tại an toàn trong migration window.
10. REFRESH PUBLICATION cập nhật membership, không tạo target schema.
11. Initial copy phải có baseline rõ và tránh duplicate/local writes.
12. Schema fingerprint và contract giúp phát hiện drift trước khi apply lỗi.
13. Theo dõi pg_stat_subscription, pg_subscription_rel, logs, replication slots và WAL retention.
14. Major upgrade cần preflight, initial sync, data validation, final marker, sequence handoff và cutover.
15. Sau cutover, rollback cần xử lý writes mới; không thể tự quay lại publisher cũ.
16. Test restore, cutover và schema migration trên đúng versions/extensions trước production.

Quy trình an toàn: **xác nhận version pair → inventory schema và objects → tạo contract → triển khai subscriber schema → cấu hình publication/subscription → initial copy → giám sát apply và drift → validate dữ liệu → freeze writes/DDL → chờ final apply marker → handoff sequences → cutover → theo dõi và giữ rollback plan**.
