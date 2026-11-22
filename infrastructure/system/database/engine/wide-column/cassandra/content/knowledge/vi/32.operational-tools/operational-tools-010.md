# sstableloader và yêu cầu tương thích dữ liệu nhập

> **Chương:** Công cụ vận hành  
> **Phạm vi:** Apache Cassandra — cơ sở dữ liệu phân tán dạng *wide-column*, với kiến trúc LSM/SSTable, khóa phân vùng, replication và consistency level. Bài hướng dẫn cách dùng **`sstableloader` để nạp dữ liệu từ SSTable có sẵn vào cluster**, nhấn mạnh yêu cầu tương thích dữ liệu nguồn–đích, quy trình kiểm chứng, tình huống lỗi và cách đối chiếu bằng CQL/Java Driver 4.x.
>
> **Mục tiêu:** Hiểu `sstableloader` làm gì và không làm gì; biết kiểm tra **SSTable format, phiên bản Cassandra, partitioner, schema, dữ liệu TTL/tombstone, token placement và network/authentication**; thiết kế quy trình nhập hàng loạt có kiểm soát, không phá tính đúng đắn của dữ liệu đang phục vụ.

## 1. Tình huống: có thư mục SSTable, làm sao nạp vào cluster mới?

Một nhóm vận hành có snapshot của bảng `orders_by_customer_day` từ cluster Cassandra cũ. Họ cần đưa dữ liệu sang cluster mới đang chạy ở một datacenter khác. Trong thư mục snapshot có những tệp giống như:

```text
.../lab/orders_by_customer_day-<table-id>/snapshots/export-01/
  na-1-big-Data.db
  na-1-big-Index.db
  na-1-big-Statistics.db
  na-1-big-TOC.txt
  ...
```

Tên prefix, mã SSTable và những thành phần có mặt trong ví dụ **chỉ để minh họa**; chúng thay đổi theo phiên bản và format. Một SSTable thực tế là **tập các thành phần đi cùng nhau**, không phải mỗi tệp `Data.db` đứng riêng lẻ.

Kế hoạch ban đầu của nhóm là copy các tệp vào thư mục data của một node đích rồi restart. Cách đó rất rủi ro:

- Token placement có thể khác giữa cluster nguồn và cluster đích.
- Một node không sở hữu mọi partition trong snapshot.
- Bảng ở đích có thể khác định nghĩa cột, clustering key hoặc codec.
- Cassandra đang chạy quản lý SSTable, index và trạng thái đọc/compaction theo cơ chế riêng.
- Copy file không tự phân phối đủ replica theo replication factor (RF).

**`sstableloader` giải quyết phần chuyển dữ liệu:** nó đọc các SSTable ở một thư mục nguồn được tổ chức đúng và **stream dữ liệu tới các replica đích phù hợp theo token ranges của cluster nhận**. Tuy nhiên, công cụ này **không tự sửa schema, convert mọi SSTable cũ hay chứng minh dữ liệu nhập không xung đột**.

> Quy tắc: **Dữ liệu nguồn phải đọc được và có ngữ nghĩa tương thích với schema đích trước khi dùng `sstableloader`.**

## 2. `sstableloader` là công cụ nào?

`sstableloader` thường được gọi là công cụ **bulk load** SSTable. Nó được đóng gói cùng bộ công cụ Cassandra phù hợp với release. Mục đích của nó là lấy dữ liệu dạng SSTable đã được tạo trước đó và phân phối qua cơ chế streaming vào cluster đang hoạt động.

Luồng khái niệm:

```text
Nguồn SSTable đã chuẩn bị, bất biến
        |
        | Đọc định dạng SSTable và metadata
        v
Máy chạy sstableloader
        |
        | 1. Kết nối/khám phá cluster nhận và schema
        | 2. Xác định token ranges/replica đích
        | 3. Stream dữ liệu SSTable tới các node thích hợp
        v
Cassandra cluster đích
        |
        +--> Replica R1: nhận phần token range đang sở hữu
        +--> Replica R2: nhận bản sao theo RF
        +--> Replica R3: nhận bản sao theo RF
        |
        v
SSTable được tích hợp và phục vụ đọc
(sau khi streaming/validation/kiểm tra đúng trạng thái)
```

Đây là sơ đồ logic, không phải biểu đồ giao thức chính xác. Cách kết nối, lựa chọn endpoints, streaming nguyên SSTable hay từng phần, thông báo tiến độ và khả năng cấu hình thay đổi theo bản Cassandra.

### Điều nó **có** thể làm

- Đưa dữ liệu từ các SSTable ngoại tuyến vào cluster đang chạy mà không phải viết từng dòng `INSERT` qua ứng dụng.
- Phân phối dữ liệu theo **token ownership và replication strategy của đích**, thay vì giả định một thư mục chỉ thuộc một node.
- Hỗ trợ khôi phục/tái sử dụng dữ liệu đã được xuất thành SSTable trong một quy trình migration hoặc recovery có kiểm soát.
- Truyền khối dữ liệu lớn bằng cơ chế streaming nội bộ, tùy khả năng phiên bản/format.

### Điều nó **không** tự làm

- Không tự tạo keyspace/table, thay partition key, chuyển tên cột hoặc đổi kiểu dữ liệu CQL.
- Không tự dịch SSTable giữa **mọi** cặp phiên bản/format Cassandra khác nhau.
- Không khôi phục dữ liệu đã thiếu trong mọi replica của nguồn.
- Không giải quyết logic nghiệp vụ về duplicate event, idempotency hay xung đột dữ liệu ghi đồng thời.
- Không tạo một giao dịch nguyên tử trên toàn bộ bảng: đã stream được một phần nhưng job lỗi thì phải quản lý trạng thái nạp dở.
- Không thay thế repair định kỳ, backup strategy và kiểm tra replica sau topology change.
- Không biến một snapshot node đơn lẻ thành bản sao đầy đủ của cả cluster nếu node đó không giữ tất cả token ranges.

## 3. Phân biệt `sstableloader` với những lựa chọn khác

| Công cụ/cơ chế | Nguồn dữ liệu | Khi thường dùng | Điểm không thể đánh đồng |
| --- | --- | --- | --- |
| **`sstableloader`** | SSTable đã tạo, tổ chức theo layout nguồn hợp lệ | Bulk load vào cluster còn hoạt động, định tuyến theo token đích | Không tự tạo schema/convert mọi format |
| **`nodetool refresh`** | SSTable đặt tại vị trí nhập phù hợp **trên một node cụ thể** | Đưa SSTable vào quản lý cục bộ trong những tình huống được hỗ trợ | Không tự phân phối dữ liệu tới toàn bộ replica như bulk streaming |
| **`nodetool repair`** | Replica đang giữ những ranges trong cluster | Đối soát replica lệch, xử lý sự kiện bỏ lỡ mutation | Không phải công cụ import một thư mục backup bên ngoài theo nghĩa thông thường |
| **`nodetool rebuild`** | Replica nguồn đang sống, thường thuộc DC khác | Dựng dữ liệu cho node ở topology mới | Không trực tiếp lấy thư mục SSTable ngoại tuyến bất kỳ từ laptop |
| **Backup/restore SSTable** | Snapshot, incremental backup, commit log khi có | Khôi phục theo runbook backup và RPO/RTO | Khôi phục đòi hỏi lựa chọn thời điểm, version và consistency |
| **CQL import / bulk ETL** | CSV/JSON hoặc dữ liệu nghiệp vụ dạng logic | Chuyển schema, đổi partition key, làm sạch dữ liệu | Chi phí parse/ghi CQL khác và phải thiết kế idempotency |

Nếu cần đổi `PRIMARY KEY` hoặc chuyển một cột `text` sang `timestamp` theo logic nghiệp vụ, giải pháp thường là **đọc dữ liệu ở mức logic → chuyển đổi → ghi vào bảng mới**, không ép `sstableloader` đọc SSTable cũ như thể đó là bảng mới.

## 4. Vì sao phải kiểm tra tính tương thích trước khi nạp?

SSTable chứa biểu diễn lưu trữ của dữ liệu Cassandra, đi kèm metadata về cách giải mã, timestamp, cell, tombstone và các thành phần index. Cluster đích dùng **schema CQL** và partitioner để hiểu/định tuyến dữ liệu đó.

Một bộ SSTable có thể tồn tại trên đĩa, có tên giống bảng đích, nhưng **không tương thích ngữ nghĩa** với bảng đích.

Ví dụ:

```text
Nguồn:
PRIMARY KEY ((customer_id, event_day), event_time, event_id)
payload text

Đích:
PRIMARY KEY ((customer_id), event_day, event_time, event_id)
payload text

Trùng một số cột nhưng khác partition key!
-> Không được bulk load trực tiếp như cùng một bảng.
```

Điều này không chỉ ảnh hưởng hiệu năng. Token của partition được tính từ **giá trị và cấu trúc partition key**. Thay khóa phân vùng có thể làm dữ liệu được diễn giải/định tuyến sai; cần migration logic.

### Bảng kiểm tra tương thích tối thiểu

| Thành phần | Cần tương thích/kiểm tra | Nếu khác thì làm gì? |
| --- | --- | --- |
| **Phiên bản Cassandra** | SSTable format nguồn được công cụ và hệ thống đích hỗ trợ đọc/stream hay không | Dùng quy trình nâng cấp/convert được hỗ trợ hoặc import logic; không đoán chỉ qua tên file |
| **SSTable format và component** | Dữ liệu có đủ thành phần cần đọc, không hỏng, đúng chuẩn format | Kiểm chứng trên bản copy; lấy lại snapshot sạch nếu thiếu/hỏng |
| **Partitioner** | Thuật toán token của nguồn/đích, chẳng hạn Murmur3Partitioner | Không giả định loader chuyển partitioner; xem migration logic nếu không tương thích |
| **Keyspace/table** | Đúng tên nguồn mong đợi và schema đích tồn tại | Tạo/chỉnh schema bằng CQL theo runbook trước khi load |
| **Partition key** | Cùng cột, thứ tự và kiểu dữ liệu | Migration logic sang bảng mới nếu khác |
| **Clustering columns/order** | Cùng các clustering columns và thứ tự/loại so sánh | Không nhập trực tiếp nếu khác cách biểu diễn row |
| **Column types** | Kiểu CQL, collection, tuple, UDT và metadata serialization | Chuyển đổi dữ liệu ở mức logic nếu không đọc tương thích |
| **Static/regular columns** | Vai trò cột, schema evolution/dropped columns | Kiểm tra định nghĩa bảng/metadata; không chỉ so tên |
| **Timestamp/TTL/tombstone** | Quy tắc reconciliation, expiry và xóa dữ liệu | Thiết kế chính sách ghi đè/retention, kiểm tra data sau nhập |
| **Replication/topology** | RF/DC, token ownership và trạng thái node đích | Sửa topology/replication và capacity trước khi stream |
| **Auth/TLS/network** | CQL metadata access và internode streaming connection | Kiểm tra quyền và kết nối giữa máy loader với các đích |

Không cần mọi cấu hình vật lý của nguồn và đích phải giống hệt. Nhưng những khác biệt có thể tác động đến **cách giải mã dữ liệu hoặc xác định danh tính hàng/cell** phải được xử lý trước khi import.

## 5. Yêu cầu về phiên bản Cassandra và SSTable format

### Không đủ khi chỉ so chuỗi version

Đội vận hành thường hỏi: “Nguồn Cassandra 3.x, đích 4.x; có chạy `sstableloader` được không?” Câu trả lời không thể dựa chỉ trên số major:

- Các release có thể dùng **format SSTable khác nhau**.
- Các công cụ của một release có thể đọc một số format cũ nhưng không phải mọi format.
- Một số thay đổi cần bước **upgrade SSTable** phù hợp trước khi di chuyển.
- Giao thức streaming/network/auth giữa loader và node đích cũng có yêu cầu tương thích.

**Không dùng một bản `sstableloader` bất kỳ trên `PATH`.** Chọn bộ công cụ có phiên bản và khả năng đọc format đã được xác minh theo cặp nguồn–đích, tốt nhất thử trước trên cluster lab cùng version.

### Metadata nào cần ghi lại?

Trước khi di chuyển, ghi vào checklist:

```text
Source Cassandra release:
Source partitioner:
Source SSTable format/generation:
Source keyspace/table and table schema:
Destination Cassandra release:
Destination partitioner:
Destination table schema:
Loader version:
Validation result on representative snapshot:
```

Ví dụ tên `na-...-Data.db` hay `nb-...-Data.db` **không phải hợp đồng tương thích đầy đủ**. Dùng các công cụ metadata SSTable theo release phù hợp; tên, cờ và output có thể khác theo phiên bản.

### Khi cần chuyển định dạng

Có những công cụ Cassandra như `sstableupgrade` phục vụ trường hợp nâng format SSTable được hỗ trợ. Nhưng không nên chạy chúng trên một snapshot duy nhất của dữ liệu quan trọng mà chưa có bản gốc/backup và runbook:

- Không giả định công cụ “upgrade” có thể hạ định dạng để load vào bản cũ.
- Không chạy công cụ biến đổi trực tiếp trên file dữ liệu live của node sản xuất.
- Không nghĩ format được nâng cấp là đủ: **schema, partitioner và timestamp semantics** vẫn phải tương thích.
- Đánh giá chi phí disk, thời gian chuyển đổi và khả năng rollback.

Nếu source/target quá khác nhau, **xuất nhập qua CQL/ETL** thường là lựa chọn minh bạch hơn, dù tốn công và tài nguyên hơn.

## 6. Yêu cầu về schema: những gì phải giữ nguyên?

### Ví dụ schema nguồn có thể dùng để thực hành

Giả sử keyspace `lab` đã tồn tại và hai môi trường được thiết kế với schema tương đương:

```cql
CREATE TABLE IF NOT EXISTS lab.orders_by_customer_day (
    customer_id uuid,
    order_day date,
    created_at timestamp,
    order_id uuid,
    status text,
    amount decimal,
    note text,
    PRIMARY KEY ((customer_id, order_day), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

Từ partition key `(customer_id, order_day)`, Cassandra tính token cho từng partition ngày của khách hàng. Các hàng trong partition được sắp xếp theo `created_at` và `order_id`.

Đích cần có **schema tương thích**, đặc biệt ở các điểm:

- `customer_id` và `order_day` đúng kiểu và đúng thứ tự làm partition key.
- `created_at` và `order_id` đúng thứ tự, kiểu và clustering semantics.
- `status`, `amount`, `note` được giải mã đúng kiểu.
- Các cột có thể từng bị drop/rename phải được đánh giá cùng metadata schema history.
- Nếu bảng có UDT hoặc collection phức tạp, định nghĩa các type lồng nhau phải tương thích.

Một bảng cùng tên nhưng viết:

```cql
PRIMARY KEY ((customer_id), order_day, created_at, order_id)
```

không còn cùng partition model. Dù cùng dữ liệu CQL nhìn bằng mắt, nó **không phải đích an toàn cho SSTable gốc**.

### Schema có nhiều cột hơn hoặc ít cột hơn?

Khi bảng đã trải qua `ALTER TABLE`, Cassandra có cơ chế schema evolution. Nhưng không được giả định cứ thêm/bớt cột là mọi SSTable cũ nhập được:

- Một cột mới có thể không tồn tại trong SSTable nguồn và được xử lý như giá trị thiếu; điều này cần kiểm tra với kiểu/cấu hình cụ thể.
- Cột đã bị **drop** có metadata thời điểm xóa, ảnh hưởng việc đọc dữ liệu cũ khi import.
- Kiểu dữ liệu đổi không tương thích có thể khiến SSTable giải mã sai hoặc thất bại.
- UDT/collection có quy tắc serialization và update riêng.

**Thực hành an toàn:** tạo bảng đích bằng schema đã xác nhận, nạp một **mẫu snapshot nhỏ nhưng đại diện**, rồi kiểm tra bằng CQL từng kiểu cột và cả dữ liệu đã xóa/TTL trước khi nạp hàng loạt.

### Table ID và layout vật lý

Thư mục dữ liệu Cassandra thường có tên bảng đi kèm định danh nội bộ, ví dụ `orders_by_customer_day-<table-id>`. Một số công cụ đọc tên **keyspace/table từ layout directory**, trong khi các phần tử metadata lại nằm ở các SSTable components.

Đừng chỉ đổi tên thư mục hay table ID theo cảm tính để công cụ “chấp nhận”. Kiểm tra yêu cầu layout của **bản `sstableloader` đang chạy**; không lấy table ID của cluster cũ làm bằng chứng rằng nó khớp bảng đích.

## 7. Partitioner và token ownership: điều kiện nền tảng

Cassandra phân phối partition dựa vào token do partitioner tính từ partition key. Hệ phổ biến sử dụng `Murmur3Partitioner`, nhưng không thể mặc định mọi cluster đều giống nhau.

Hai điều cần phân biệt:

1. **Schema partition key:** bộ cột và kiểu dữ liệu xác định những byte khóa được mã hóa.
2. **Partitioner/token placement:** hàm tính token và danh sách node sở hữu range trong cluster đích.

`sstableloader` cần đọc SSTable và gửi dữ liệu tới đúng replica theo token ownership đích. Nó không phải công cụ tùy ý chuyển một bảng có partition key A sang bảng có partition key B.

### Khi RF hoặc số node khác thì có sao?

RF và topology **không nhất thiết phải giống nguồn**. Một mục tiêu hợp lý của bulk load là đưa dữ liệu logic vào cluster mới có số node/RF khác nhưng **schema và partitioner phù hợp**, rồi để dữ liệu được phân phối theo ownership của đích.

Ví dụ:

```text
Cluster nguồn: dc-old, RF=3, 4 node
Cluster đích:  dc-new, RF=3, 8 node

Cùng partitioner + schema tương thích
          |
          v
sstableloader xác định replica của token ranges ở cluster đích
          |
          v
Dữ liệu được stream theo đích, không sao chép file node-1 sang node-1
```

Nếu đích có RF chưa được áp dụng đúng hoặc topology còn đang bootstrap/rebuild, nạp dữ liệu khi ownership chưa ổn định sẽ làm việc kiểm chứng khó hơn. Hoàn tất/ổn định topology trước và đo coverage sau.

## 8. Chuẩn bị SSTable nguồn: đừng lấy file live tùy tiện

SSTable là tệp bất biến sau flush, nhưng **tập SSTable sống của một node có thể được thay thế/xóa khi compaction diễn ra**. Copy một số file trong lúc node đang compaction có thể bỏ sót thành phần hoặc snapshot trạng thái không nhất quán ở cấp thư mục.

### Nên lấy nguồn từ đâu?

Nguồn phổ biến là **snapshot SSTable có quản lý**, hoặc bản export/staging đã được tạo từ quy trình được Cassandra hỗ trợ. Ví dụ trên node nguồn của **lab**:

```bash
nodetool flush lab orders_by_customer_day
nodetool snapshot -t export-01 lab
nodetool listsnapshots
```

`flush` đưa memtable của bảng ra SSTable, giúp snapshot bao gồm nhiều mutation gần thời điểm chụp hơn; `snapshot` tạo bản tham chiếu SSTable theo cơ chế snapshot cục bộ. Cú pháp flag/table-specific và nội dung snapshot cần kiểm tra qua `nodetool help snapshot` của phiên bản. Lệnh trên minh họa chụp **keyspace lab**; trong thực tế có thể cần giới hạn bảng theo khả năng lệnh.

**Snapshot trên một node không phải global transaction snapshot của toàn cluster.** Nếu node chỉ là một replica cho một phần token, snapshot đó chỉ chứa dữ liệu node có; để xuất toàn bộ keyspace cần **kế hoạch coverage theo token/replica** hoặc một quy trình backup đủ phạm vi.

### Vì sao cần staging và bản gốc?

Quy trình an toàn:

1. Chụp snapshot khi các mutation trước mốc yêu cầu đã được flush.
2. Xác định đúng thư mục snapshot của bảng.
3. Copy/stage **đầy đủ các SSTable components** bằng phương pháp bảo toàn byte và metadata cần thiết.
4. Giữ bản gốc bất biến, tránh chạy công cụ sửa SSTable trực tiếp trên snapshot duy nhất.
5. Tính hash/inventory số tệp/dung lượng; xác nhận không bị thiếu do lỗi copy.
6. Chỉ dùng bản staging để thử `sstableloader` hoặc chuyển đổi format khi cần.

Nếu cần point-in-time restore sau thời điểm snapshot, **commit log replay và backup timeline** là bài toán riêng. `sstableloader` không tự phát lại mọi mutation kể từ snapshot.

### Không trộn các file thuộc nhiều format/tables một cách tùy tiện

Không gom các thành phần SSTable của nhiều bảng vào một thư mục rồi mong loader tự phân biệt theo nội dung. Cần bảo toàn **tên, cặp thành phần theo SSTable, layout keyspace/table được loader hỗ trợ**.

Ví dụ bố cục *minh họa* trên máy staging:

```text
/srv/cassandra-import/
└── lab/
    └── orders_by_customer_day-<table-id>/
        ├── <descriptor-A>-Data.db
        ├── <descriptor-A>-Index.db
        ├── <descriptor-A>-Statistics.db
        ├── <descriptor-A>-TOC.txt
        ├── <descriptor-B>-Data.db
        ├── <descriptor-B>-Index.db
        ├── ...
        └── ...
```

Đây không phải một cấu trúc được đảm bảo chấp nhận trong mọi release. `sstableloader` có yêu cầu về tên keyspace/table của **thư mục đầu vào**; có phiên bản hỗ trợ sử dụng trực tiếp thư mục snapshot nếu layout đúng. Phải kiểm tra help và thử với bản staging. **Đừng tự sửa tên SSTable components** chỉ để trông giống mẫu.

## 9. Dữ liệu nguồn có thật sự bao phủ đủ token ranges?

Snapshot node đơn lẻ rất dễ gây hiểu nhầm trong cluster RF>1:

- Node nguồn chỉ lưu những partition mà nó chịu trách nhiệm, không phải mọi partition của keyspace.
- Nếu snapshot được lấy khi một replica offline hoặc đang stale, dữ liệu trong nó có thể thiếu những mutation mà replica khác đã nhận.
- Nếu nhiều node nguồn có vùng token trùng nhau, SSTable có thể chứa các phiên bản cùng cell; Cassandra dùng timestamp/tombstone reconciliation, không phải “lấy file mới nhất” theo tên.
- Nếu nguồn đã purge tombstone trước khi replica cũ hòa giải, dữ liệu cũ có nguy cơ sống lại sau nhập.

Hãy lập **bản đồ coverage**:

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Nguồn gồm những node/replica nào? | Snapshot inventory theo node |
| Mỗi nguồn giữ những ranges nào? | Token ownership và topology tại mốc snapshot |
| Có đủ mọi partition cần chuyển không? | Coverage toàn bộ ranges hoặc nguồn logic được xác minh |
| Các replica nguồn có đồng nhất không? | Repair history, tình trạng node offline, thời điểm chụp |
| Có mutation sau snapshot không? | Cutover plan, log/replay/dual write/reconciliation |
| Bản nhập có trùng một phần dữ liệu đang có ở đích không? | Chính sách merge/rewrite theo timestamp và mục tiêu restore |

**Nạp một file thành công chỉ chứng minh file ấy được stream theo quy trình**, không chứng minh tập file nguồn là toàn bộ dữ liệu nghiệp vụ.

## 10. TTL, tombstone, timestamp và xung đột dữ liệu

Đây là phần dễ sai nhất khi bulk load bảng vào cluster đã có dữ liệu.

### TTL không “bắt đầu đếm lại” chỉ vì được import

Mutation được ghi với `USING TTL` chứa metadata về tuổi thọ/expiration. Khi load SSTable cũ, **không được xem thao tác import là INSERT mới với TTL mới tính từ ngày import**.

Ví dụ:

```text
Ngày D:   ghi event với TTL 7 ngày
Ngày D+5: tạo snapshot
Ngày D+6: nạp SSTable vào cluster mới
Ngày D+7: event đã tới hạn hết TTL logic

Không được giả định nó còn 7 ngày kể từ D+6.
```

Nếu snapshot đã quá cũ, nhiều cell TTL có thể đã hết hạn trước khi nạp. Khi đó việc nhập tệp thành công không bảo đảm những cell đó xuất hiện trong truy vấn đích.

### Timestamp gốc quyết định hòa giải phiên bản

Cassandra dùng timestamp của cell/mutation và quy tắc reconciliation để quyết định giá trị nào thắng. Giả sử:

```text
SSTable nhập: status='PENDING' @ timestamp 100
Cluster đích: status='PAID'    @ timestamp 200

Sau import:
- Không được kỳ vọng 'PENDING' ghi đè 'PAID' chỉ vì import chạy sau.
- Mutation timestamp 200 mới hơn vẫn có thể thắng khi đọc.
```

Timestamp ở đây là số minh họa cho quan hệ mới/cũ, không phải giá trị thời gian thực tế hợp lệ để khai báo trong CQL. Cassandra còn có tie-break và tombstone semantics khi timestamp bằng nhau; không xây quy trình nhập dựa trên “file nào copy sau”.

### Tombstone có thể giữ vai trò chặn dữ liệu cũ

Nếu snapshot có dấu xóa, nó có thể được stream cùng dữ liệu tùy SSTable và thời điểm compaction. Các dấu xóa phải đủ tuổi và đủ điều kiện an toàn trước khi GC. Ngược lại, nếu snapshot thiếu tombstone quan trọng, nạp các phiên bản cũ có thể làm dữ liệu đã xóa xuất hiện trở lại trong tình huống xấu.

**Không đặt `gc_grace_seconds=0` và không xóa tombstone bằng tay để đẩy nhanh import.** Với dữ liệu có replica từng offline, điều đó có thể làm tăng nguy cơ zombie data.

### Thời gian và clock skew

Timestamp ghi trong Cassandra có thể đến từ client hoặc server theo chính sách mutation. Hai cluster có lịch sử đồng hồ khác nhau tạo nguy cơ thứ tự ghi không phù hợp với nghiệp vụ.

Trước khi gộp SSTable nguồn vào bảng đích đang được ghi:

- So sánh timestamp dữ liệu nguồn–đích và chính sách client-generated timestamp.
- Xác nhận độ chính xác đồng hồ của ứng dụng/node.
- Quyết định mục tiêu **merge**, **replace toàn bộ theo backup**, hay **migration sang bảng trống**.
- Thiết kế cách xử lý các ghi đồng thời trong lúc streaming.

**Bulk load không phải upsert nghiệp vụ có kiểm chứng thứ tự sự kiện.**

## 11. Những kiểu dữ liệu và tính năng cần kiểm tra riêng

### Collections và UDT

SSTable có thể chứa collection `list`/`set`/`map`, UDT hoặc tuple. Khả năng giải mã phụ thuộc schema và format.

- `frozen` và non-frozen collection có biểu diễn/cách update khác nhau.
- UDT ở đích cần định nghĩa tương thích, kể cả tên/kiểu trường.
- Với collection bị cập nhật hoặc xóa, tombstone của phần tử/collection cần được xử lý đúng.
- Không nạp collection cũ vào schema mới chỉ vì output JSON nhìn gần giống.

### Counter

Counter có cơ chế cập nhật và trạng thái phân tán đặc thù; không được xem snapshot SSTable counter như dữ liệu scalar thông thường mà có thể gộp vào bảng đích đang chạy tùy ý.

Đối với bảng counter, yêu cầu **quy trình migration được Cassandra version hỗ trợ và kiểm chứng trên môi trường riêng**. Nếu không có cách bảo đảm chính xác, cân nhắc xuất giá trị logic và thiết kế lại mô hình hoặc dùng phương án phục hồi được tài liệu release xác nhận. Không thử `sstableloader` lên counter production chỉ vì định dạng công cụ chấp nhận.

### LWT, Paxos và thao tác có điều kiện

SSTable bulk load không đi qua logic business của từng `INSERT ... IF NOT EXISTS` hay `UPDATE ... IF ...` như ứng dụng bình thường. Nếu ứng dụng dựa vào LWT/`LOCAL_SERIAL` hoặc trạng thái đồng thuận để bảo vệ bất biến, phải thiết kế quy trình ngừng/giới hạn ghi và xác nhận trạng thái tương thích. **Không coi bulk load là một chuỗi thao tác CAS được tuần tự hóa.**

### Indexes, SAI, materialized views và CDC

Khi bảng dùng secondary index, Storage-Attached Index (SAI), materialized view hoặc CDC:

- Kiểm tra phiên bản Cassandra/feature của cả nguồn và đích.
- Xác định index/view/CDC có được tạo hoặc tái đồng bộ chính xác sau khi SSTable được stream không.
- Thực hiện bước rebuild/index validation hoặc backfill nếu runbook tương ứng yêu cầu.
- Đừng chỉ SELECT theo primary key rồi tuyên bố mọi đường truy vấn qua index/view đã đúng.
- Đừng kỳ vọng bulk SSTable import tự phát sinh **mọi event CDC** giống như ghi CQL qua commit log.

Hành vi cụ thể phụ thuộc từng loại tính năng và release; cần kiểm thử query theo index/view và pipeline CDC thực tế.

## 12. Yêu cầu network, authentication và quyền truy cập

`sstableloader` không chỉ cần biết một IP đích. Công cụ thường cần:

1. **Liên lạc ban đầu** để khám phá cluster, schema và token ownership.
2. **Kết nối streaming** tới những endpoint sở hữu ranges.
3. **Tài khoản và quyền** phù hợp nếu authentication được bật.
4. **TLS/encryption** theo chính sách CQL/internode mà cluster yêu cầu.
5. DNS/routing/firewall/port phù hợp **từ máy chạy loader tới từng node có thể là stream target**.

Ví dụ điểm quan trọng:

```text
Máy loader kết nối được contact point C1 qua native transport.
Nhưng R2 và R3 có IP private không route từ máy loader.
-> Khám phá schema có thể thành công.
-> Streaming tới các replica đích có thể thất bại.
```

Không nhầm “kết nối CQL 9042 được” với “mọi stream target reachable”. Port và phương thức truyền thay đổi theo phiên bản và cấu hình; kiểm tra chính sách mạng thực tế, không mở rộng firewall bừa bãi.

### Không để mật khẩu xuất hiện trong command history

Một số bản công cụ hỗ trợ tham số username/password hoặc file cấu hình. Để hạn chế lộ thông tin:

- Xem `sstableloader --help` của release đang dùng.
- Ưu tiên cơ chế credentials được hỗ trợ mà không để lộ secret trên command line/process list nếu có.
- Bảo vệ quyền truy cập file cấu hình/chứng chỉ, không commit secret vào mã nguồn.
- Không in chi tiết credentials trong runbook/log và không dùng tài khoản quyền quá rộng.

Ví dụ trong bài **không ghi password trực tiếp**.

## 13. Chọn chiến lược nhập: cluster trống, cluster đã có dữ liệu hay bảng mới?

| Trạng thái đích | Rủi ro chính | Chiến lược khuyến nghị |
| --- | --- | --- |
| **Cluster/bảng mới, chưa có dữ liệu** | Tương thích SSTable/schema, thiếu token ranges, TTL đã hết | Tạo schema tương thích, kiểm tra nguồn/coverage, bulk load và xác thực |
| **Cluster có bảng đang phục vụ** | Giá trị cũ/mới xung đột timestamp, tombstone, ghi đồng thời | Có kế hoạch merge, đóng băng/điều phối write hoặc nạp vào bảng staging mới |
| **Đích cần thay thế hoàn toàn dữ liệu** | Bulk load không tự xóa những hàng vốn có mà nguồn không chứa | Dùng runbook restore/swap/replace phù hợp; không coi import là truncate+restore |
| **Đích khác partition key/kiểu dữ liệu** | Không có ánh xạ SSTable an toàn | ETL/CQL migration với kiểm tra logic |
| **Đích thêm datacenter** | RF/ownership thay đổi, dữ liệu lịch sử chưa đủ | So sánh `nodetool rebuild` với bulk load ngoại tuyến, theo runbook topology |
| **Khôi phục sau node mất disk** | Identity/token và replica nguồn không đúng | Ưu tiên replace/rebuild/restore được hỗ trợ thay vì import file tùy ý |

**Nạp vào bảng trống mới** thường dễ kiểm chứng hơn nạp chồng lên bảng đang nhận update. Nhưng còn phải giải quyết read routing, đổi ứng dụng sang bảng mới và quyền truy cập.

## 14. Quy trình thực hành từng bước trong lab

Giả sử muốn nạp SSTable của `lab.orders_by_customer_day` vào một **cluster đích thử nghiệm** cùng schema tương thích.

### Bước A — Kiểm tra cluster đích

```bash
nodetool status
nodetool describecluster
```

Trên `cqlsh` kết nối tới cluster đích:

```cql
DESCRIBE KEYSPACE lab;
DESCRIBE TABLE lab.orders_by_customer_day;
```

Xác nhận keyspace/table đã tồn tại, các key columns/type khớp với nguồn và RF/DC đã được cấu hình đúng. Nếu keyspace `lab` chưa có trong lab, tạo nó theo replication strategy đã thiết kế; **không copy RF nguồn** khi topology đích khác.

Ví dụ cho **một** DC tên `dc1` có ít nhất ba node phù hợp:

```cql
CREATE KEYSPACE IF NOT EXISTS lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
```

Lệnh này là ví dụ chuẩn bị schema; không dùng tên `dc1` hoặc RF=3 nếu cluster lab thực tế không đáp ứng. Không dùng `SimpleStrategy` như mặc định cho triển khai nhiều DC.

### Bước B — Xác nhận định nghĩa bảng

```cql
CREATE TABLE IF NOT EXISTS lab.orders_by_customer_day (
    customer_id uuid,
    order_day date,
    created_at timestamp,
    order_id uuid,
    status text,
    amount decimal,
    note text,
    PRIMARY KEY ((customer_id, order_day), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

**`IF NOT EXISTS` không kiểm chứng schema khớp!** Nếu bảng đã tồn tại với một định nghĩa khác, lệnh sẽ không tự chỉnh nó về schema mong muốn. Bắt buộc dùng `DESCRIBE TABLE` và so sánh với nguồn.

### Bước C — Chuẩn bị dữ liệu nguồn

Trong môi trường nguồn lab có bảng tương ứng, có thể tạo mutation ví dụ:

```cql
INSERT INTO lab.orders_by_customer_day
    (customer_id, order_day, created_at, order_id, status, amount, note)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-21',
    '2026-11-21T03:00:00Z',
    11111111-1111-4111-8111-111111111111,
    'PAID',
    250.00,
    'source-row'
);

INSERT INTO lab.orders_by_customer_day
    (customer_id, order_day, created_at, order_id, status, amount, note)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-21',
    '2026-11-21T03:01:00Z',
    22222222-2222-4222-8222-222222222222,
    'PENDING',
    125.00,
    'ttl-row'
) USING TTL 86400;
```

Sau đó flush và snapshot trên node nguồn lab với công cụ hỗ trợ:

```bash
nodetool flush lab orders_by_customer_day
nodetool snapshot -t export-01 lab
nodetool listsnapshots
```

Nhắc lại: nếu nguồn là cluster nhiều node, **snapshot chỉ trên một node không bao phủ tất cả ranges**. Quy trình xuất toàn bảng thực sự cần kế hoạch nguồn đầy đủ và bảo vệ dữ liệu đồng thời.

### Bước D — Xác minh file ở máy staging

Trên máy chứa bản copy SSTable, kiểm tra:

```text
[ ] Thư mục keyspace/table theo layout loader yêu cầu.
[ ] Đầy đủ các thành phần của từng SSTable.
[ ] Không trộn file từ table khác.
[ ] Có backup gốc riêng và hash/inventory.
[ ] Loader version có khả năng đọc SSTable format.
[ ] Partitioner và schema nguồn–đích tương thích.
[ ] Đích có headroom, RF/DC và token ownership ổn định.
[ ] Network/auth/TLS cho mọi streaming endpoint đã thử.
```

Dùng công cụ metadata SSTable của đúng release nếu có; không sửa file chỉ để metadata “đẹp hơn”. Đọc lệnh help:

```bash
sstableloader --help
```

Nếu công cụ dùng `-h` thay vì `--help`, hãy đọc help của bản thực tế trước.

### Bước E — Chạy nạp từ máy staging

Mẫu lệnh minh họa **không có credentials**:

```bash
sstableloader -d 192.0.2.10,192.0.2.11 \
  /srv/cassandra-import/lab/orders_by_customer_day-<table-id>
```

Trong đó:

- `192.0.2.10` và `192.0.2.11` là địa chỉ dùng cho tài liệu, phải thay bằng contact points thật của cluster đích.
- `-d` thường là danh sách initial hosts để loader khám phá cluster, **không phải danh sách đầy đủ mọi replica sẽ được ghi**.
- Thư mục cuối chứa SSTable components và có tên/layout mà **phiên bản loader chấp nhận**.
- Đường dẫn `<table-id>` là placeholder, không phải ký tự cần gõ nguyên văn.
- Trên hệ có authentication/TLS, phải sử dụng cách cấu hình được bản công cụ hỗ trợ.

Ví dụ này không thay thế kiểm thử tương thích. **Không nạp từ snapshot production vào production khác chỉ dựa trên một dòng lệnh.**

### Bước F — Theo dõi quá trình import

Trên các node đích:

```bash
nodetool netstats
nodetool compactionstats
nodetool tpstats
nodetool tablestats lab.orders_by_customer_day
```

Kết hợp telemetry:

- Streaming session active/success/error, lượng bytes sent/received.
- Disk read/write latency và headroom của source/destination.
- CPU, GC, network saturation và write/read p95/p99 của ứng dụng.
- Số SSTable, compaction backlog và trạng thái node.
- Dữ liệu nạp thành công theo phạm vi; lưu stderr/stdout của loader và mốc thời gian.

Một công cụ báo kết thúc nhưng có lỗi một phần hoặc nguồn chưa bao phủ đủ tokens **không được coi là migration thành công**.

## 15. Kiểm chứng dữ liệu bằng CQL

Với partition thử nghiệm:

```cql
SELECT created_at, order_id, status, amount, note,
       TTL(note), WRITETIME(note)
FROM lab.orders_by_customer_day
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_day = '2026-11-21';
```

Mục tiêu kiểm tra:

1. Hai event có khóa/giá trị mong đợi khi vẫn còn sống.
2. Các cột kiểu `decimal`, `uuid`, `date` và `timestamp` được giải mã chính xác.
3. `WRITETIME(note)` phản ánh timestamp ghi của giá trị đang sống; không mặc nhiên đổi thành thời điểm bulk load.
4. `TTL(note)` của row TTL phản ánh **thời gian sống còn lại**, không reset theo thời điểm nhập.
5. Nếu TTL đã hết tại thời điểm kiểm tra, row/cell có thể không còn xuất hiện như dữ liệu sống — **không tự kết luận loader đã bỏ qua tệp**.

### Đối chiếu dữ liệu nguồn–đích thế nào cho tốt?

| Phép kiểm tra | Giá trị | Hạn chế |
| --- | --- | --- |
| So sánh các **partition mẫu** theo token range | Phát hiện cột/kiểu/TTL/giá trị sai | Không chứng minh mọi range đầy đủ |
| Kiểm tra **coverage** của nguồn và đích | Phát hiện các vùng dữ liệu không được xuất/nạp | Cần inventory topology và dữ liệu nguồn đầy đủ |
| Đối chiếu row counts trên tập partition đã chọn | Phát hiện thiếu/nhân bản logic trong mẫu | Không nên chạy toàn bảng bằng `COUNT(*)` |
| So sánh các giá trị, timestamps, TTL còn lại | Phát hiện lỗi merge/expiry/schema | Timestamps có thể khác nếu ETL thay mutation |
| Kiểm tra đường đọc qua index/SAI/view (nếu có) | Xác minh tính năng phụ trợ sau load | Phụ thuộc khả năng rebuild/index version |
| Kiểm tra p95/p99 và timeout dưới tải đọc thật | Bảo đảm dữ liệu có thể phục vụ | Không chứng minh toàn vẹn dữ liệu đơn độc |

**`SELECT COUNT(*)` toàn bộ bảng** không phải xác minh lý tưởng: có thể cực kỳ tốn tài nguyên, không chứng minh từng partition/range đúng, và có nguy cơ ảnh hưởng production.

### Kiểm tra cả dữ liệu đã xóa

Nếu business logic phụ thuộc delete, hãy có mẫu kiểm tra row đã xóa/TTL-expire. Sau import, việc giá trị cũ xuất hiện lại có thể do:

- Snapshot không mang tombstone cần thiết.
- Replica nguồn không nhất quán hoặc stale.
- Import merge với giá trị/timestamp cũ ở đích.
- Repair/GC grace không bảo đảm an toàn trong lịch sử dữ liệu.

Không xử lý bằng cách chạy `DELETE` đại trà nếu chưa hiểu nguyên nhân và phạm vi ảnh hưởng.

## 16. Java Driver 4.x: kiểm tra sau nhập qua truy vấn nghiệp vụ

Ứng dụng Java cần chứng minh dữ liệu bulk-loaded phục vụ đúng **truy vấn theo partition key** và consistency level mục tiêu.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.metadata.Node;

public final class ImportedOrdersCheck {
    private final CqlSession session;
    private final PreparedStatement byDay;

    public ImportedOrdersCheck(CqlSession session) {
        this.session = session;
        this.byDay = session.prepare(
            "SELECT created_at, order_id, status, amount, note " +
            "FROM lab.orders_by_customer_day " +
            "WHERE customer_id = ? AND order_day = ? LIMIT ?"
        );
    }

    public List<UUID> fetchOrderIds(UUID customerId, LocalDate day) {
        BoundStatement statement = byDay.bind(customerId, day, 100)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true)
            .setPageSize(100);

        ResultSet result = session.execute(statement);
        Node coordinator = result.getExecutionInfo().getCoordinator();

        List<UUID> ids = new ArrayList<>();
        for (Row row : result) {
            Instant createdAt = row.getInstant("created_at");
            UUID orderId = row.getUuid("order_id");
            String status = row.getString("status");
            BigDecimal amount = row.getBigDecimal("amount");
            String note = row.getString("note");

            if (orderId == null || createdAt == null) {
                throw new IllegalStateException("Hàng nhập thiếu khóa dự kiến");
            }
            ids.add(orderId);
            System.out.printf(
                "%s %s %s %s %s%n",
                createdAt, orderId, status, amount, note
            );
        }

        System.out.println("Rows=" + ids.size()
            + " coordinator_dc="
            + (coordinator == null
                ? "unknown" : coordinator.getDatacenter()));
        return ids;
    }
}
```

Giả định `CqlSession` đã được cấu hình local datacenter, contact points, authentication/TLS và keyspace đúng; RF ở DC coordinator đủ để sử dụng `LOCAL_QUORUM`. Đoạn mã minh họa kiểm tra một partition, **không chứng minh toàn bộ nhập liệu đã đầy đủ**. Không in dữ liệu cá nhân/đơn hàng thật vào log production; sử dụng test data, masking và sampling phù hợp.

Một request thành công chỉ chứng minh đủ replica đã đáp ứng CL đó. Nếu muốn xác nhận mọi replica sau bulk load, cần theo dõi streaming/repair và so sánh phạm vi theo runbook thay vì chỉ SELECT `LOCAL_ONE`.

## 17. Tác động tài nguyên và điều tiết tốc độ import

`sstableloader` chạy bằng streaming nên có thể cạnh tranh với công việc bình thường:

- **Disk đọc ở máy nguồn:** đọc SSTable, metadata, checksum/format.
- **Network:** nhiều luồng truyền tới các replica đích.
- **Disk ghi ở replica:** nhận dữ liệu SSTable và công việc tích hợp/compaction.
- **CPU:** nén/giải nén, xác thực, serialization, xử lý metadata.
- **Bộ nhớ:** buffers và hoạt động JVM trên loader/node đích.

Một phép nhập khối lượng lớn còn có thể khiến số SSTable tăng và compaction backlog kéo dài sau khi lệnh kết thúc.

### Không chỉ tối đa hóa MiB/s

Mục tiêu tốt:

```text
Import throughput hữu dụng cao
           VÀ
Business p95/p99, error rate trong SLO
           VÀ
Không làm đầy disk / nghẽn compaction
           VÀ
Dữ liệu được xác minh đúng và đủ
```

Một số bản `sstableloader` hỗ trợ tham số throttle streaming; tên cờ và **đơn vị** phải kiểm tra qua `--help`. Không lấy giá trị `200` từ lệnh của release khác rồi mặc nhiên hiểu là 200 MiB/s.

Lịch an toàn thường:

1. Thử một tập SSTable nhỏ đại diện.
2. Đo p95/p99, throughput, disk/network và compaction backlog.
3. Tăng giới hạn hoặc số công việc có kiểm soát, tránh dồn quá nhiều loader vào cùng replica.
4. Giảm tải hoặc dời cửa sổ nếu API vượt SLO.
5. Khi load xong, tiếp tục theo dõi compaction và disk; không đóng ticket chỉ vì progress bar đạt 100%.

## 18. Import dở, retry và tính idempotent

### Khi loader thất bại giữa chừng

Một phần SSTable có thể đã được stream và tích hợp trước khi lỗi xảy ra. Quy trình xử lý cần:

- Lưu log, danh sách file, phiên bản, node đích và phạm vi lỗi.
- Xác định node/range nào đã nhận dữ liệu theo bằng chứng streaming.
- Khắc phục nguyên nhân mạng/auth/disk/format trước khi retry.
- Kiểm tra hành vi retry của công cụ/phiên bản trên **bản thử nghiệm**, nhất là khi bảng đích đã có dữ liệu.
- Sau retry, xác minh dữ liệu logic/timestamp/TTL và replica coverage.

**Không giả định load dở được tự rollback atomically**. Cũng không giả định retry cùng SSTable chắc chắn tạo một row nghiệp vụ mới: Cassandra định danh row theo primary key và hòa giải cell theo timestamp, nhưng side effect/index/CDC và trạng thái nạp dở vẫn cần kiểm tra.

### Vì sao retry không đơn giản là “chạy thêm lần nữa”?

Nếu dữ liệu nhập chứa timestamp cũ và bảng đích đang nhận ghi mới:

- Cùng khóa có thể có nhiều phiên bản; timestamp quyết định giá trị được đọc.
- Tombstone có thể che một phiên bản cũ.
- TTL có thể đã hết trước khi retry.
- CDC/index/view hoặc pipeline nghiệp vụ có thể không có đúng đặc tính “exactly once” như kỳ vọng.

Khi cần **replace chính xác một snapshot** thay vì merge, hãy chuẩn bị runbook riêng với staging table/swap/routing và sự đồng thuận về điểm dừng ghi. Loader không có nút tổng quát “đảm bảo bảng đích giống 100% ảnh chụp”.

## 19. Các lỗi thường gặp và cách chẩn đoán

### Lỗi A — Công cụ báo format SSTable không được hỗ trợ

**Khả năng:** source/loader/target version không hỗ trợ nhau hoặc một thành phần SSTable bị hỏng.

**Kiểm tra:** release của Cassandra nguồn, format SSTable, version công cụ, thành phần file. Thử load trên lab, dùng đường chuyển format/ETL được hỗ trợ; không tự rename prefix `na` thành `nb`.

### Lỗi B — Không tìm thấy keyspace hoặc table

**Khả năng:** schema đích chưa được tạo, tên/layout thư mục nhập sai hoặc phiên bản loader suy tên bảng khác dự kiến.

**Kiểm tra:** `DESCRIBE KEYSPACE/TABLE` ở đích, đường dẫn staging, yêu cầu layout của loader. Không sửa table ID hoặc chuyển file sang tên bảng khác mà chưa xác minh schema compatibility.

### Lỗi C — Invalid schema/column/type mismatch

**Khả năng:** partition/clustering key không khớp, cột có kiểu khác hoặc schema evolution không tương thích.

**Kiểm tra:** toàn bộ `CREATE TABLE` của hai phía, dropped columns, UDT/collections. Nếu khóa hoặc kiểu thực sự thay đổi, chuyển qua ETL logic thay vì ép SSTable cũ vào bảng mới.

### Lỗi D — Kết nối contact point được nhưng streaming thất bại

**Khả năng:** máy loader không kết nối được tất cả streaming endpoints, firewall/TLS/internode protocol khác mong đợi.

**Kiểm tra:** địa chỉ các node đích do topology công bố, cổng/giao thức phiên bản, network route và log node. Không chỉ test `cqlsh` đến một host rồi kết luận mạng đủ.

### Lỗi E — Không đủ quyền hoặc TLS sai

**Khả năng:** auth yêu cầu credentials khác, chứng chỉ không tin cậy hoặc chính sách encryption không tương thích.

**Kiểm tra:** phương thức credential/certificate được loader hỗ trợ, phân quyền và log lỗi cụ thể. Không tắt TLS trên production chỉ để import nhanh.

### Lỗi F — Không đủ disk ở replica nhận

**Khả năng:** estimate SSTable bytes/replication sai, compaction tạo tệp tạm hoặc snapshot giữ dung lượng.

**Kiểm tra:** per-node SSTable size, RF, headroom, active/total disk space và snapshot. Tăng capacity hoặc thay lịch; không xóa SSTable/commit log thủ công.

### Lỗi G — Loader thành công nhưng query không thấy data

**Khả năng:** query không đúng partition key, TTL đã hết, schema/table đích khác, dữ liệu chỉ được nhập một phần hoặc timestamp cũ bị dữ liệu đích mới che.

**Kiểm tra:** query theo khóa mẫu, `TTL`/`WRITETIME`, stream logs/coverage và metadata bảng. Không suy ra file nhập đã được bỏ chỉ từ một câu SELECT.

### Lỗi H — Đọc primary key đúng nhưng index/view thiếu

**Khả năng:** tính năng secondary index/SAI/materialized view chưa được cập nhật/rebuild theo quy trình của version.

**Kiểm tra:** query index/view, metrics và hướng dẫn build/rebuild của release; không chỉ kiểm tra bảng gốc.

### Lỗi I — Dữ liệu đã xóa xuất hiện lại

**Khả năng:** nguồn stale, thiếu tombstone, snapshot/repair history không an toàn, timestamp xung đột hoặc dữ liệu khác có tuổi cũ.

**Kiểm tra:** lịch `DELETE`, `gc_grace_seconds`, trạng thái replica nguồn, file snapshot và timestamp. Đây là lỗi tính đúng đắn, cần tạm dừng cutover và điều tra trước khi mở rộng import.

### Lỗi J — Import làm API đọc/ghi chậm

**Khả năng:** network, disk, compaction, streaming concurrency gây cạnh tranh với request thật.

**Kiểm tra:** `netstats`, `compactionstats`, `tpstats`, disk await, CPU/GC và p99 theo node. Giảm concurrency/throttle hoặc chuyển cửa sổ, nhưng vẫn đảm bảo deadline migration.

## 20. Quy trình kiểm tra và bàn giao sau import

Một runbook thực tế nên có ba cửa kiểm soát.

### Cửa 1 — **Tương thích đã được chứng minh**

- [ ] Đã ghi source version, loader version, target version và SSTable format.
- [ ] Partitioner, partition key, clustering key, column/UDT types tương thích.
- [ ] Keyspace/table đích tồn tại, RF/DC và token ownership đúng.
- [ ] Snapshot nguồn bất biến, đầy đủ components và ranges cần thiết.
- [ ] Đã kiểm tra dữ liệu TTL, tombstone, timestamp và các features đặc thù.
- [ ] Có kế hoạch auth/TLS/network và không lộ secret.

### Cửa 2 — **Streaming hoàn tất có kiểm soát**

- [ ] Đã chạy thử tập SSTable nhỏ và đo tác động p95/p99.
- [ ] Tài nguyên node nguồn/đích còn headroom.
- [ ] Log ghi nhận kết quả từng lượt và lỗi/retry rõ ràng.
- [ ] Không còn session lỗi chưa xử lý.
- [ ] Không tự thay đổi/tắt compaction hoặc xóa file data để “giải phóng chỗ”.
- [ ] Có rollback hoặc kế hoạch quay lại nguồn cũ khi dữ liệu chưa đạt.

### Cửa 3 — **Dữ liệu và ứng dụng được xác minh**

- [ ] Các partition mẫu thuộc nhiều token ranges có khóa/giá trị đúng.
- [ ] Kiểu dữ liệu, collection/UDT, TTL và timestamp được đọc đúng.
- [ ] Các row đã xóa/hết hạn không xuất hiện lại ngoài ý muốn.
- [ ] Index/SAI/view và CDC pipeline (nếu có) được kiểm tra theo release.
- [ ] Đã xem xét repair/replica coverage và streaming consistency.
- [ ] Java Driver đặt local DC/CL phù hợp; API p95/p99, timeout và lỗi đạt SLO.
- [ ] Đã thống nhất cutover, rollback và mốc kết thúc ghi nguồn nếu migrate.

**Một file `Data.db` được truyền xong chưa phải tiêu chí hoàn tất.** Thành công nghĩa là dữ liệu đúng về ngữ nghĩa, đã vào đúng replica, đọc được qua các query nghiệp vụ và không phá SLO.

## 21. Những ngộ nhận cần tránh

**“`sstableloader` là `COPY` cho dữ liệu CQL.”** Sai. Nó xử lý dữ liệu dưới dạng SSTable và streaming, cần tương thích lưu trữ/schema.

**“Cứ cùng tên bảng là nạp được.”** Sai. Partition/clustering key, kiểu cột, partitioner và schema history đều quan trọng.

**“Chỉ cần copy `Data.db` là đủ.”** Sai. SSTable gồm các thành phần tương ứng; thiếu/hỏng metadata có thể khiến không đọc được.

**“Lấy snapshot từ một replica là snapshot toàn cluster.”** Sai. Nó chỉ chứa những partition và phiên bản node đó đang giữ.

**“Nạp vào node đầu tiên là đủ cho RF=3.”** Sai. `sstableloader` dùng token placement/streaming để đưa dữ liệu tới replica đích; copy tay trên một node không thay thế phân phối.

**“Đích có RF khác nên chắc chắn không thể bulk load.”** Không hẳn. RF/topology có thể khác, miễn schema/partitioner/format phù hợp và loader định tuyến đúng.

**“TTL tính lại từ lúc import.”** Sai. Metadata expiration trong SSTable gốc có ý nghĩa; có thể hết hạn ngay sau/ trước lúc nhập.

**“SSTable import chạy sau sẽ ghi đè mọi dữ liệu đích.”** Sai. Cassandra dùng timestamps và quy tắc reconciliation, không đơn thuần theo giờ chạy loader.

**“Nạp snapshot là thay thế toàn bộ bảng hiện tại.”** Sai. Nhập dữ liệu không tự xóa những row ở đích mà snapshot không có.

**“Không cần xem tombstone vì SELECT không thấy row đã xóa.”** Sai. Dấu xóa quyết định tính đúng đắn và rủi ro zombie data.

**“Có `UN` ở mọi node nghĩa là loader chắc chắn stream tới đủ replica.”** Sai. Node khỏe theo gossip chưa bảo đảm source coverage và stream session thành công.

**“Đọc bằng `LOCAL_ONE` ra đúng vài row nghĩa là restore hoàn chỉnh.”** Sai. Cần kiểm chứng token range, nhiều replica và các query nghiệp vụ.

**“Có thể bỏ qua index/CDC vì CQL primary-key query chạy được.”** Sai. Những tính năng phụ trợ có thể cần quy trình riêng sau SSTable streaming.

**“Tăng streaming throttle luôn làm migration an toàn hơn.”** Sai. Import có thể cạnh tranh CPU/disk/network và làm p99 của ứng dụng tăng.

## 22. Bài tập và tình huống phỏng vấn

1. Giải thích sự khác nhau giữa `sstableloader` và `nodetool refresh` khi nạp SSTable từ một máy staging vào cluster nhiều node.
2. Vì sao cùng tên `orders_by_customer_day` nhưng khác partition key thì không được bulk load trực tiếp?
3. Một SSTable từ bản Cassandra cũ có format mà loader không hỗ trợ. Nêu hai hướng xử lý an toàn, giải thích vì sao đổi tên file không phải giải pháp.
4. Trong cluster RF=3 có 6 node, snapshot trên node N1 bao phủ toàn bộ keyspace không? Cần làm gì để kiểm tra?
5. Vì sao source/target có thể khác RF nhưng vẫn bulk load hợp lệ trong điều kiện tương thích?
6. Một bản ghi TTL 7 ngày đã được ghi 6 ngày trước. Import hôm nay có được thêm 7 ngày sống không? Vì sao?
7. Bảng đích có `status='PAID'` tại timestamp mới hơn nguồn `status='PENDING'`. Giá trị nào có khả năng được đọc sau merge và vì sao?
8. Khi nguồn chứa tombstone nhưng một replica cũ đã vắng mặt lâu, nhập dữ liệu phải lưu ý nguy cơ nào?
9. Vì sao bulk load có thể không phát event CDC như một lệnh CQL bình thường? Cần làm gì nếu nghiệp vụ bắt buộc replay event?
10. Những trường hợp nào cần chú ý đặc biệt nếu bảng sử dụng `counter`, LWT hoặc materialized view?
11. Một loader kết nối được contact point nhưng timeout khi streaming. Bạn sẽ kiểm tra các tầng mạng/auth nào?
12. Đích có dữ liệu đã tồn tại nhưng business muốn “giống hệt snapshot ngày D”. Vì sao bulk load không tự đáp ứng yêu cầu này?
13. Tại sao `SELECT COUNT(*)` toàn bảng không phải phép kiểm chứng bulk import tối ưu?
14. Một nguồn snapshot có nhiều cell TTL đã hết hạn. Vì sao loader thành công nhưng số row đọc được ít hơn số row tưởng là có trong file?
15. Làm sao dùng `nodetool netstats`, `compactionstats`, `tpstats` và Java Driver để phát hiện import đang làm xấu SLO?
16. Đề xuất chiến lược xử lý khi job loader lỗi nửa chừng mà không giả định rollback atomically.
17. Tạo bảng kiểm tra compatibility cho source version, loader version, partitioner, schema, SSTable format, TTL/tombstone và UDT.
18. Vì sao không nên nạp SSTable trực tiếp vào bảng có partition key đã được thiết kế lại? Hãy đề xuất một luồng ETL thay thế.
19. Trên cluster nhiều DC, vì sao phải kiểm tra RF/DC, network streaming và kết quả CQL theo local DC của Java Driver trước cutover?
20. Một file mới được nạp khiến query primary key đúng nhưng query index sai. Bạn sẽ kiểm tra tính năng gì và quy trình nào?

## 23. Sơ đồ quyết định cuối bài

```text
          CÓ SSTABLE CẦN ĐƯA VÀO CLUSTER ĐÍCH
                           |
                           v
            Nguồn có đủ dữ liệu/token ranges?
                 |                    |
                Không                Có
                 |                    |
      Bổ sung nguồn/repair             v
      hoặc khôi phục backup      Version/format đọc được?
                                     |         |
                                    Không     Có
                                     |         |
                             Upgrade/ETL        v
                             được hỗ trợ     Schema + partitioner tương thích?
                                                   |         |
                                                  Không     Có
                                                   |         |
                                          Migration CQL     v
                                          logic         TTL/tombstone/conflict
                                                       đã có chính sách?
                                                        |       |
                                                       Chưa     Có
                                                        |       |
                                               Thiết kế merge  v
                                               hoặc staging  Kiểm tra network/
                                                            auth/RF/capacity
                                                                   |
                                                                   v
                                                       Chạy thử trên bản copy
                                                                   |
                                                                   v
                                                    Bulk load có kiểm soát
                                                                   |
                                                                   v
                                               Xác minh ranges, dữ liệu, API
                                               indexes/CDC và rollback
```

**Ghi nhớ:** `sstableloader` là công cụ **stream dữ liệu từ SSTable đã tồn tại vào cluster Cassandra theo token ownership ở đích**. Nó hữu ích cho bulk import nhưng **không biến SSTable nguồn thành dữ liệu CQL tương thích một cách tự động**. Chỉ nạp khi đã xác minh **format/phiên bản, schema/partitioner, đầy đủ nguồn, RF/topology, TTL/tombstone/timestamps, auth/network và khả năng phục vụ sau nhập**. Một migration thành công là **dữ liệu đúng, đủ, an toàn cho replica và không làm truy vấn nghiệp vụ vượt SLO**, chứ không đơn thuần là thông báo “stream completed”.
