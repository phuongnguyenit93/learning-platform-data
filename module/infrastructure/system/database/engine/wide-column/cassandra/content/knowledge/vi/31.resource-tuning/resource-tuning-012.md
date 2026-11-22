# Kích thước mutation, batch, collection và phân vùng

> **Chương:** Tối ưu tài nguyên  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Ngữ cảnh:** Apache Cassandra là cơ sở dữ liệu wide-column phân tán. Hiệu năng ghi và đọc phụ thuộc vào khóa phân vùng, cách tổ chức bảng theo truy vấn, replication, consistency level, memtable, commitlog, SSTable, compaction, repair và cách ứng dụng Java gửi CQL.

## 1. Mục tiêu: nhận diện bốn loại “lớn” khác nhau

Một lỗi thiết kế thường gặp là cho rằng “Cassandra chịu ghi rất tốt nên có thể gửi một batch khổng lồ, nhét hàng nghìn phần tử vào collection và giữ dữ liệu của một khách hàng trong một partition mãi mãi”. Cassandra tối ưu tốt cho việc ghi phân tán theo khóa, nhưng từng yêu cầu và từng phân vùng vẫn phải dùng hữu hạn RAM, CPU, network, commitlog, ổ đĩa và tài nguyên compaction/repair.

Bài học phân biệt **bốn kích thước độc lập**:

| Đối tượng | Đo cái gì? | Vấn đề khi quá lớn |
|---|---|---|
| **Mutation** | Đơn vị thay đổi dữ liệu được gửi và áp dụng cho một phân vùng; kích thước phụ thuộc dữ liệu/cell/tombstone được mã hóa | Tốn buffer, CPU, mạng, commitlog, có thể vượt giới hạn mutation hoặc gây timeout |
| **Batch** | Nhóm câu lệnh ghi CQL gửi chung trong một request; có thể ảnh hưởng một hoặc nhiều phân vùng | Coordinator phải xử lý nhiều thao tác; batchlog và fan-out tốn tài nguyên; có ngưỡng cảnh báo/từ chối |
| **Collection** | Giá trị **list/set/map** của một cột trên một hàng, gồm nhiều phần tử | Cập nhật/đọc quá nhiều phần tử, tombstone và chi phí compaction; khó phân trang riêng từng phần tử |
| **Partition** | Toàn bộ các hàng có **cùng partition key** trong một bảng | Hotspot, đọc/repair/streaming tốn tài nguyên, SSTable và compaction nặng; độ trễ biến động |

**Một batch nhỏ không bảo đảm mutation nhỏ; mutation nhỏ không bảo đảm partition nhỏ; và collection nhỏ chưa chắc ngăn hotspot.** Mỗi lớp cần ràng buộc và chỉ số theo dõi riêng.

Sau bài này, bạn cần:

1. Phân biệt mutation, batch, collection, partition và tác động tài nguyên của chúng.
2. Chọn đúng khi nào dùng **LOGGED**, **UNLOGGED** hoặc không dùng CQL batch.
3. Thiết kế collection hữu hạn và chuyển dữ liệu không giới hạn thành các hàng được phân cụm.
4. Tính thử kích thước partition, chọn bucket/shard theo truy vấn và tải ghi.
5. Thực hành CQL, Java driver, kiểm tra cảnh báo kích thước và chẩn đoán sự cố.

## 2. Nhìn vào đường ghi Cassandra

Khi ứng dụng Java thực thi một **INSERT** hoặc **UPDATE**, request đến coordinator. Coordinator xác định các replica theo partition key, replication strategy và topology, rồi gửi yêu cầu ghi đến replica. Mỗi replica ghi commitlog và cập nhật memtable; sau đó memtable được flush thành SSTable. Compaction hợp nhất dữ liệu trên đĩa theo chiến lược đã cấu hình.

~~~mermaid
flowchart LR
    A["Ứng dụng Java / CQL write"] --> C["Coordinator"]
    C --> P["Xác định partition và replica"]
    P --> R["Replica"]
    R --> L["Commitlog"]
    R --> M["Memtable"]
    M --> F["Flush thành SSTable"]
    F --> K["Compaction, đọc và repair về sau"]
~~~

Độ lớn của request tạo áp lực ở **nhiều đoạn của đường đi**:

- **Client/driver:** tạo và mã hóa giá trị bind; hàng nghìn statement hoặc payload lớn có thể tiêu tốn heap của ứng dụng Java.
- **Network/coordinator:** chuyển byte, lập lịch, xử lý batch và phân phối sang replica.
- **Replica/commitlog:** ghi dữ liệu, phân bổ buffer và kiểm tra giới hạn mutation.
- **Memtable và flush:** thay đổi lớn chiếm bộ nhớ, có thể dẫn tới flush/backpressure.
- **SSTable/compaction/repair:** dữ liệu và tombstone vẫn tạo chi phí sau khi request được xác nhận.

**Consistency level** như **ONE** hoặc **LOCAL_QUORUM** quy định số replica cần đáp ứng trước khi trả kết quả. Nó không làm mutation nhỏ đi và không biến batch trải nhiều partition thành một giao dịch ACID.

## 3. Mutation: đơn vị ghi, không phải số dòng CQL

### 3.1. Mutation là gì?

Ở cấp triển khai, Cassandra biểu diễn các thay đổi cho một partition dưới dạng một **mutation**, chứa thông tin cần cập nhật một hay nhiều hàng/cell hoặc tombstone trong partition đó. Một câu CQL ghi có thể tạo mutation; nhiều thao tác trong batch cùng partition có thể được gom vào một mutation lớn hơn. Không nên đồng nhất **“một INSERT” = “một mutation có kích thước cố định”**.

Ví dụ một hàng nhỏ:

~~~sql
INSERT INTO app.events_by_tenant_hour
  (tenant_id, bucket_hour, happened_at, event_id, event_type, attributes)
VALUES
  (11111111-1111-4111-8111-111111111111,
   '2026-11-21T03:00:00Z',
   '2026-11-21T03:05:00Z',
   22222222-2222-4222-8222-222222222222,
   'login',
   {'device': 'web'});
~~~

Nếu **attributes** bị thay bằng một collection khổng lồ hoặc một blob nhiều MiB, câu lệnh vẫn chỉ có một hàng nhưng mutation có thể rất lớn. Ngược lại, 10.000 câu **INSERT** nhỏ trong batch trải nhiều partition có thể tạo nhiều mutation nhỏ, trong khi **batch request** lại quá lớn và tốn chi phí điều phối.

### 3.2. Vì sao Cassandra giới hạn mutation?

- Mutation được mã hóa và vận chuyển qua mạng; replica phải đủ khả năng tiếp nhận, phân tích và ghi nó.
- Commitlog được tổ chức theo segment; kích thước mutation có quan hệ với khả năng ghi/định dạng commitlog và các giới hạn phiên bản.
- Mutation lớn làm tăng đỉnh sử dụng bộ nhớ, độ trễ xử lý và tác động của một lần retry.
- Replica chậm hoặc bị timeout có thể khiến driver gửi lại thao tác. Nếu thao tác **không idempotent**, cần đặc biệt thận trọng để tránh cập nhật ngoài ý muốn.

Cassandra có các cấu hình/guardrail về độ lớn mutation, chẳng hạn tên **max_mutation_size_in_kb** trong một số phiên bản. Mặc định, tên tham số, đơn vị và cách giới hạn tương tác với **commitlog_segment_size_in_mb** có thể khác giữa phiên bản; hãy xem **cấu hình hiệu lực** và log lỗi của cluster đang chạy. Đừng lấy giá trị từ tài liệu phiên bản khác rồi giả định đó là giới hạn toàn hệ thống.

> **Không coi giới hạn cấu hình là “kích thước mục tiêu”.** Một mutation thấp hơn ngưỡng từ chối vẫn có thể quá tốn kém với latency, heap/native memory và network thực tế.

### 3.3. Giảm kích thước mutation từ mô hình dữ liệu

Thay vì lưu một tài liệu khổng lồ thành một cell:

- Chia dữ liệu có thể đọc độc lập thành **nhiều hàng nhỏ**.
- Nếu cần giữ object lớn nguyên vẹn, cân nhắc lưu object trong hệ thống lưu trữ thích hợp, còn Cassandra giữ metadata và khóa tham chiếu.
- Không tự cắt một object theo byte vào nhiều cột nếu thao tác truy vấn buộc phải đọc tất cả phần và tạo hotspot; phải thiết kế lifecycle, tính toàn vẹn và chiến lược đọc.
- Giới hạn payload đầu vào, số phần tử/độ dài của từng giá trị tại tầng API; kiểm thử bằng kích thước thực **sau mã hóa CQL**, không chỉ kích thước JSON trước khi gửi.

## 4. CQL batch: khi nào có ích, khi nào gây hại?

**BATCH** gom nhiều câu ghi thành một request CQL. Nó thường bị hiểu nhầm là một cách tăng tốc mọi loại bulk insert. Trong Cassandra, dùng batch trải nhiều partition để “tiết kiệm network round-trip” thường tạo tải lớn lên coordinator, batchlog và replica.

### 4.1. Các loại batch

| Cách dùng | Ngữ nghĩa đáng quan tâm | Khi nên cân nhắc |
|---|---|---|
| **BEGIN LOGGED BATCH** (mặc định cho batch thường) | Dùng **batchlog** để hỗ trợ áp dụng các mutation của nhóm trên nhiều partition khi xảy ra một số lỗi; không cung cấp isolation/rollback như giao dịch SQL đa partition | Có yêu cầu nghiệp vụ buộc nhóm ghi nhiều partition phải được hoàn tất theo ngữ nghĩa batch của Cassandra |
| **BEGIN UNLOGGED BATCH** | Không ghi batchlog cho nhóm; với thao tác **cùng partition** thường tránh chi phí batchlog không cần thiết; đa partition có thể ghi một phần nếu lỗi | Vài thao tác cùng partition cần gửi chung; phải hiểu giới hạn |
| **BEGIN COUNTER BATCH** | Chỉ dành cho cập nhật counter theo quy tắc counter | Workload counter; không trộn counter và non-counter |

**BATCH không phải thao tác bulk load phổ dụng.** Với các INSERT độc lập vào hàng trăm partition, dùng **prepared statements + các request bất đồng bộ có giới hạn concurrency/backpressure** thường phù hợp hơn một batch lớn.

Đối với **batch cùng partition**, các cập nhật có thể được xử lý như một mutation của partition và có tính atomicity/isolation ở phạm vi partition theo ngữ nghĩa Cassandra. Với **logged batch nhiều partition**, batchlog hỗ trợ phục hồi và hoàn tất các ghi sau một số lỗi, nhưng không cho phép ứng dụng mặc nhiên quan sát một ảnh chụp nhất quán tức thì của tất cả partition. Không có **rollback, unique constraint và giao dịch đa bảng kiểu SQL** chỉ vì viết **BEGIN BATCH**.

### 4.2. Sơ đồ chi phí batch đa partition

~~~mermaid
flowchart TD
    B["Một BATCH với N câu INSERT"] --> C["Coordinator"]
    C --> S{"Bao nhiêu partition?"}
    S -->|Một partition| M["Có thể gom thành mutation trong một partition"]
    S -->|Nhiều partition| L["Logged batch có thể cần batchlog"]
    L --> P["Phân phối mutation cho nhiều nhóm replica"]
    M --> R["Replica ghi commitlog / memtable"]
    P --> R
    R --> X["Flush, compaction và repair về sau"]
~~~

Số statement không nói hết chi phí: **2 câu có blob 20 MiB** có thể nguy hiểm hơn **20 câu nhỏ**; trong khi **20 câu nhỏ trải 20 partition** lại có chi phí fan-out khác **20 câu cùng partition**.

### 4.3. Cảnh báo và giới hạn batch

Nhiều phiên bản Cassandra có ngưỡng cảnh báo/từ chối kích thước batch qua các tham số như **batch_size_warn_threshold** / **batch_size_fail_threshold** (hoặc tên có hậu tố **_in_kb** ở phiên bản cũ). Kích thước mà server kiểm tra liên quan đến dữ liệu/statement của batch; quy tắc áp dụng và mặc định phải đối chiếu phiên bản.

Khi thấy cảnh báo kiểu **batch too large**:

1. Ghi lại **số câu**, số **partition key phân biệt**, payload và loại batch.
2. Nếu các statement độc lập trải nhiều partition, **tách thành request riêng có điều tiết**.
3. Nếu cùng partition nhưng quá nhiều statement, **chia nhỏ công việc**, giới hạn kích thước mutation và độ lớn partition; đừng mặc định dùng batch để tải hàng triệu hàng.
4. Chỉ tăng ngưỡng sau khi có bằng chứng phần cứng, mô hình dữ liệu và hành vi latency phù hợp; **nâng ngưỡng không giảm áp lực tài nguyên**.

### 4.4. Hai ví dụ đối chiếu

**Trường hợp phù hợp:** ghi hai sự kiện cùng khách hàng và cùng bucket giờ, với vài giá trị nhỏ. Cả hai row thuộc **một partition key**.

~~~sql
BEGIN UNLOGGED BATCH
  INSERT INTO app.events_by_tenant_hour
    (tenant_id, bucket_hour, happened_at, event_id, event_type, attributes)
  VALUES
    (11111111-1111-4111-8111-111111111111,
     '2026-11-21T03:00:00Z', '2026-11-21T03:05:00Z',
     22222222-2222-4222-8222-222222222222,
     'login', {'device': 'web'});

  INSERT INTO app.events_by_tenant_hour
    (tenant_id, bucket_hour, happened_at, event_id, event_type, attributes)
  VALUES
    (11111111-1111-4111-8111-111111111111,
     '2026-11-21T03:00:00Z', '2026-11-21T03:06:00Z',
     33333333-3333-4333-8333-333333333333,
     'logout', {'device': 'web'});
APPLY BATCH;
~~~

**Trường hợp cần tránh:** tạo một LOGGED BATCH gồm 5.000 sự kiện của 5.000 khách hàng khác nhau để hy vọng nhanh hơn. Các sự kiện trải trên nhiều partition và có thể nhiều replica; coordinator phải điều phối fan-out, batchlog và xử lý kết quả. Nếu các ghi độc lập, hãy chia request, giới hạn inflight và theo dõi timeout/retry.

**Lưu ý về retry:** Một batch đã timeout không có nghĩa mọi replica đều không nhận được ghi. Với các thao tác idempotent như **INSERT** cùng primary key và cùng giá trị/timestamp nghiệp vụ đã xác định, retry có thể dễ kiểm soát hơn so với **counter increment** hoặc logic sinh mã mới cho mỗi lần thử. Cần xử lý idempotency ở tầng ứng dụng và kiểm tra ngữ nghĩa consistency thực tế.

## 5. Collection: list, set, map nên nhỏ và có giới hạn

Cassandra hỗ trợ các cột collection:

| Loại | Ví dụ | Đặc điểm |
|---|---|---|
| **set<text>** | Nhãn cố định của sản phẩm | Phần tử không trùng; không bảo đảm thứ tự theo nghiệp vụ |
| **list<text>** | Danh sách các bước ngắn có thứ tự | Có thứ tự; cập nhật index/prepend và đồng thời có thể tốn chi phí |
| **map<text, text>** | Một số thuộc tính nhỏ của sự kiện | Tra cứu/cập nhật theo key; tránh tăng số key vô hạn |
| **frozen<collection>** | Giá trị nhỏ được đọc/ghi nguyên khối | Được lưu và cập nhật như một giá trị đơn; sửa một phần thường phải thay toàn bộ |

Collection phù hợp với **một tập nhỏ và hữu hạn phần tử của một hàng**. Nó không thay thế bảng gồm nhiều row nếu dữ liệu cứ lớn lên theo thời gian.

### 5.1. Collection lớn gây chi phí gì?

- **Đọc:** lấy cột collection thường trả cả giá trị, khó phân trang từng phần tử như với clustering rows.
- **Ghi:** thay cả collection hoặc cập nhật một loạt phần tử có thể tạo mutation lớn.
- **Tombstone:** xóa phần tử, thay toàn bộ non-frozen collection hoặc giá trị hết TTL có thể để lại dữ liệu đánh dấu xóa cần được đọc và dọn theo cơ chế compaction.
- **Compaction/repair:** nhiều cell và tombstone khiến CPU, disk I/O, streaming và chi phí đọc tăng.
- **Giới hạn:** số lượng phần tử và kích thước sau mã hóa có thể chạm guardrail/giới hạn của phiên bản hoặc ứng dụng.

Đối với **non-frozen map**, có thể sửa phần tử cụ thể:

~~~sql
UPDATE app.events_by_tenant_hour
SET attributes['device'] = 'mobile'
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND bucket_hour = '2026-11-21T03:00:00Z'
  AND happened_at = '2026-11-21T03:05:00Z'
  AND event_id = 22222222-2222-4222-8222-222222222222;
~~~

Câu lệnh chỉ sửa một map entry, nhưng **một map có hàng chục nghìn key vẫn là mô hình dữ liệu cần xem lại**. Khi một khóa trong map bị xóa liên tục, tombstone vẫn là yếu tố cần giám sát.

### 5.2. Khi nào chuyển collection thành bảng?

Giả sử một tài khoản có thể tạo vô hạn notification. Không nên lưu tất cả trong:

~~~sql
-- Phản ví dụ về mô hình: danh sách tăng không giới hạn.
CREATE TABLE app.bad_notifications (
    tenant_id uuid PRIMARY KEY,
    messages list<text>
);
~~~

Với danh sách tăng theo ngày, mô hình tốt hơn là **một notification = một row**, chia partition theo tenant và bucket thời gian:

~~~sql
CREATE TABLE app.notifications_by_tenant_day (
    tenant_id uuid,
    bucket_day date,
    created_at timestamp,
    notification_id uuid,
    message text,
    PRIMARY KEY ((tenant_id, bucket_day), created_at, notification_id)
) WITH CLUSTERING ORDER BY (created_at DESC, notification_id ASC);
~~~

Lúc này ứng dụng có thể truy vấn **theo khóa phân vùng**, giới hạn số row và phân trang theo nhu cầu. Vẫn phải đặt ngân sách kích thước partition cho từng **bucket_day**; chuyển sang row không tự động làm partition hữu hạn nếu partition key vẫn chỉ là tenant_id.

**Quy tắc:** collection mô tả **các thuộc tính nhỏ của một thực thể**; tập dữ liệu có lifecycle riêng, truy vấn riêng hoặc tăng không giới hạn nên là row/table được thiết kế theo access pattern.

## 6. Partition: đơn vị phân bố dữ liệu và nguyên nhân hotspot

Trong mô hình wide-column, **partition key** quyết định token và nhóm replica sở hữu một phân vùng logic. Các **clustering columns** sắp xếp nhiều row trong partition.

Ví dụ:

~~~sql
CREATE KEYSPACE IF NOT EXISTS app
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS app.events_by_tenant_hour (
    tenant_id uuid,
    bucket_hour timestamp,
    happened_at timestamp,
    event_id uuid,
    event_type text,
    attributes map<text, text>,
    PRIMARY KEY ((tenant_id, bucket_hour), happened_at, event_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, event_id ASC);
~~~

Ở đây **(tenant_id, bucket_hour)** là **composite partition key**; mọi sự kiện cùng tenant trong một giờ UTC nằm chung partition (nếu ứng dụng tính bucket nhất quán).

~~~mermaid
flowchart TB
    A["tenant_id + bucket_hour"] --> T["Partition key → token"]
    T --> R["Replica được chọn theo replication"]
    R --> P["Partition chứa nhiều row"]
    P --> C1["happened_at DESC, event_id"]
    P --> C2["happened_at DESC, event_id"]
    P --> C3["... tối đa trong ngân sách kích thước"]
~~~

**Replication factor (RF)** quyết định số bản sao logic, không chia nhỏ một partition thành nhiều phần theo RF. Ví dụ RF = 3 nghĩa là **mỗi replica liên quan giữ bản sao của partition**, không phải mỗi replica chỉ giữ một phần ba dữ liệu của partition đó.

### 6.1. Vì sao partition lớn gây vấn đề?

- **Read amplification:** quét nhiều row, tombstone, nhiều SSTable hoặc tìm theo khoảng quá rộng có thể làm tăng công đọc.
- **Hot partition:** một partition nhận tỷ lệ lớn write/read thì nhóm replica của nó dễ thành nút thắt; thêm node không tự động phân tán một partition hot thành nhiều phần.
- **Compaction:** partition lớn và nhiều cập nhật/xóa gây tải nền đáng kể; tombstone làm đường đọc khó dự đoán.
- **Repair/streaming:** chuyển hoặc đối chiếu dữ liệu phân vùng quá lớn có thể kéo dài và tốn I/O/network.
- **Memory/GC:** query, iterator, buffer và các cấu trúc đọc/ghi cũng chịu áp lực; **LIMIT 20** không biến partition 10 GiB thành partition nhỏ.
- **Availability:** sự cố của một nhóm replica có thể ảnh hưởng đáng kể đến các partition quá nóng.

Không có **một giới hạn kích thước partition tối ưu cho mọi hệ Cassandra**. Các mốc như “vài chục MiB” hoặc “100 MiB” thường được nhắc tới như **kinh nghiệm vận hành**, không phải giới hạn phổ quát và càng không phải mục tiêu phải lấp đầy. Chọn ngân sách dựa trên kiểu truy vấn, số row, độ rộng row, tombstone, ổ đĩa, replication, mức nhất quán và dữ liệu đo thực tế.

### 6.2. Ước lượng để thiết kế bucket

Giả sử một tenant ghi trung bình **10 sự kiện/giây**, mỗi sự kiện có **payload hữu ích 512 byte**, phân bố đều.

~~~text
Sự kiện trong ngày = 10 × 86.400 = 864.000
Payload/ngày = 864.000 × 512 B = 442.368.000 B ≈ 421,9 MiB

Sự kiện trong giờ = 10 × 3.600 = 36.000
Payload/giờ = 36.000 × 512 B = 18.432.000 B ≈ 17,6 MiB
~~~

Nếu dùng partition **(tenant_id, ngày)**, chỉ riêng payload đã khoảng **422 MiB/partition/ngày**. Chuyển sang **(tenant_id, giờ)** giảm payload xuống khoảng **17,6 MiB/partition/giờ**.

Đây là **ước lượng ban đầu**, không phải dự báo chính xác kích thước SSTable. Cần cộng/trừ ảnh hưởng của primary key, timestamp, metadata/cell, tombstone, định dạng lưu trữ, nén, TTL và phân phối lưu lượng. Một tenant có đỉnh tải gấp 20 lần mức trung bình vẫn có thể làm **partition theo giờ** quá lớn.

Công thức hữu ích:

~~~text
payload_dự_kiến_trên_partition
  ≈ events_per_second × seconds_per_bucket × average_payload_bytes

số_bucket_tối_thiểu_theo_dung_lượng
  ≈ ceil(payload_trong_khoảng / ngân_sách_payload_mỗi_bucket)
~~~

**Không tính số bucket chỉ dựa trên byte**: còn phải kiểm soát **request/giây trên partition**, số row, mô hình truy vấn và khả năng merge kết quả giữa nhiều bucket.

### 6.3. Chọn bucket theo access pattern

| Hướng thiết kế | Ưu điểm | Đánh đổi |
|---|---|---|
| **tenant_id** làm partition key duy nhất | Truy vấn toàn bộ lịch sử một tenant đơn giản | Dễ trở thành partition không giới hạn/hotspot |
| **(tenant_id, day)** | Dễ truy vấn theo ngày, giảm kích thước partition | Tenant rất hoạt động vẫn có partition lớn |
| **(tenant_id, hour)** | Partition nhỏ hơn, phù hợp dữ liệu tuần tự thời gian | Truy vấn dài ngày phải chạm nhiều partition và tổng hợp |
| **(tenant_id, day, shard)** với shard có quy tắc | Phân bố tải ghi của tenant rất nóng | Đọc phải fan-out nhiều shard, merge theo thời gian; tăng độ phức tạp |

Chọn **bucket_hour** từ timestamp theo một múi giờ chuẩn, ví dụ **UTC**, rồi dùng cùng quy tắc lúc ghi và đọc. Khi truy vấn từ 02:30 đến 04:15 UTC, ứng dụng phải truy vấn các bucket 02:00, 03:00, 04:00 và gộp kết quả theo timestamp nếu cần thứ tự toàn cục.

Không dùng **bucket ngẫu nhiên** nếu ứng dụng không biết tìm dữ liệu ở shard nào. Nếu bắt buộc shard để phân tán hot tenant, hãy đưa vào design một quy tắc xác định hoặc danh sách shard cần đọc, đồng thời giới hạn fan-out.

## 7. CQL theo partition key: nhỏ theo phạm vi đọc và ghi

Với bảng **events_by_tenant_hour**, truy vấn điển hình:

~~~sql
SELECT happened_at, event_id, event_type, attributes
FROM app.events_by_tenant_hour
WHERE tenant_id = ?
  AND bucket_hour = ?
LIMIT ?;
~~~

Cả hai thành phần partition key đều được bind, nên driver có thể tính routing key/token trong trường hợp đủ metadata và định tuyến thuận lợi cho replica. Clustering columns cho phép lấy các sự kiện mới nhất trong bucket.

Đọc một khoảng trong **một partition**:

~~~sql
SELECT happened_at, event_id, event_type
FROM app.events_by_tenant_hour
WHERE tenant_id = ?
  AND bucket_hour = ?
  AND happened_at >= ?
  AND happened_at < ?
LIMIT ?;
~~~

Điều kiện khoảng nằm trên **happened_at**, một clustering column. Truy vấn này khác về chi phí với việc đọc mọi sự kiện của tenant trên tất cả giờ hoặc quét theo một cột không nằm trong key. **Prepared statement và bind** tối ưu việc tái sử dụng CQL, an toàn kiểu dữ liệu và có thể giúp token-aware routing; chúng **không chữa được partition quá lớn hoặc batch quá nhiều partition**.

## 8. Java driver 4.x: chuẩn bị một lần, ghi nhóm nhỏ

Ví dụ sau tạo hai sự kiện cùng tenant/bucket trong một **UNLOGGED BATCH** nhỏ, với **prepared statement** và kiểu dữ liệu tương ứng. Môi trường phải có Cassandra và dependency **java-driver-core** của driver 4.x tương thích.

~~~java
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Map;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public class SmallPartitionBatchDemo {
    public static void main(String[] args) {
        UUID tenantId =
            UUID.fromString("11111111-1111-4111-8111-111111111111");
        Instant t1 = Instant.parse("2026-11-21T03:05:00Z");
        Instant t2 = Instant.parse("2026-11-21T03:06:00Z");
        Instant bucketHour = t1.truncatedTo(ChronoUnit.HOURS);

        // Thay địa chỉ và dc1 theo cluster thực tế.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement insert = session.prepare(
                "INSERT INTO app.events_by_tenant_hour " +
                "(tenant_id, bucket_hour, happened_at, event_id, " +
                "event_type, attributes) VALUES (?, ?, ?, ?, ?, ?)");

            // Cả hai statement có cùng composite partition key.
            BoundStatement first = insert.bind(
                tenantId, bucketHour, t1, UUID.randomUUID(),
                "login", Map.of("device", "web"));

            BoundStatement second = insert.bind(
                tenantId, bucketHour, t2, UUID.randomUUID(),
                "logout", Map.of("device", "web"));

            BatchStatement batch =
                BatchStatement.builder(DefaultBatchType.UNLOGGED)
                    .addStatement(first)
                    .addStatement(second)
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM)
                    .build();

            session.execute(batch);
        }
    }
}
~~~

**Điều kiện và giới hạn:**

- Keyspace/bảng đã được tạo như mục 6 và datacenter thực sự có tên **dc1**, hoặc đã thay bằng tên phù hợp.
- Ví dụ keyspace RF = 3 và **LOCAL_QUORUM** yêu cầu đủ replica trong local DC để đạt quorum; không dùng mô hình một nút làm bằng chứng rằng cấu hình production này sẵn sàng.
- **bucketHour** lấy từ t1 đã chuẩn hóa theo UTC; t2 phải được xác minh thuộc cùng giờ. Với batch có nhiều mốc thời gian, ứng dụng phải **kiểm tra mỗi mốc** trước khi gộp.
- **Map.of** yêu cầu Java 9+; map thuộc tính nên bị giới hạn kích thước bằng kiểm tra input.
- Ví dụ tạo UUID ngẫu nhiên khi chạy **main**. Ứng dụng có retry thực tế nên **giữ nguyên event_id** cho cùng sự kiện để tránh ghi hai row mới khi retry.
- Dùng **CqlSession** và **PreparedStatement** lâu dài trong ứng dụng. Đừng tạo session/prepare mới cho từng yêu cầu.
- **Batch size = 2** chỉ minh họa cách dùng. Nó không phải ngưỡng tối ưu chung; trong một số trường hợp gửi hai request độc lập vẫn đủ và đơn giản hơn.

### 8.1. Nếu các sự kiện nằm ở nhiều partition thì sao?

Với các sự kiện độc lập thuộc nhiều tenant hoặc bucket, hãy gửi **các BoundStatement riêng** bằng driver, sử dụng API bất đồng bộ khi phù hợp, và đặt **giới hạn số request inflight**. Theo dõi timeout, queue, retry, backpressure và tải replica. Không gộp hàng nghìn statement vào một LOGGED BATCH để thay cho cơ chế giới hạn concurrency.

Pseudocode triển khai:

~~~text
prepare INSERT một lần
for each event:
    validate payload/collection size
    calculate tenant_id + bucket_hour
    build bound statement với event_id ổn định
    submit theo giới hạn số request đang thực thi
    khi request hoàn tất: cập nhật kết quả / xử lý retry an toàn
~~~

Pseudocode không quy định một con số concurrency cố định. Giới hạn thích hợp phụ thuộc topology, connection pool, payload, consistency, tốc độ replica và latency mục tiêu.

## 9. Chẩn đoán: nhìn đúng chỉ số cho đúng vấn đề

| Triệu chứng | Giả thuyết cần kiểm tra | Biện pháp ưu tiên |
|---|---|---|
| Server log báo **mutation too large** | Một row/blob/collection hoặc mutation gộp cùng partition quá lớn | Giảm đơn vị ghi; tách dữ liệu theo hàng/thiết kế, kiểm tra giới hạn phiên bản |
| Server cảnh báo **batch too large** | Nhiều statement/payload hoặc batch trải nhiều partition | Đếm partition trong batch, chia request, giới hạn số statement và byte |
| Ghi timeout khi batch nhiều tenant | Coordinator fan-out, batchlog, replica chậm/đang quá tải | Dùng request độc lập có bounded concurrency; kiểm tra retry, compaction, node |
| Read p99 tăng khi dữ liệu một tenant lớn dần | Partition lớn, nhiều SSTable/tombstone/hotspot | Bucket/shard theo access pattern, kiểm tra histogram partition |
| Xóa hoặc cập nhật collection nhiều gây read chậm | Nhiều cell/tombstone, compaction chưa xử lý | Thay collection tăng vô hạn bằng row, hạn chế update/delete không cần thiết |
| Compaction/repair kéo dài | SSTable, tombstone, partition lớn, I/O hoặc dữ liệu lệch replica | Kiểm tra metrics compaction/repair, thiết kế partition và lịch bảo trì |
| JVM heap/native pressure khi tải ghi tăng | Payload/requests concurrent quá lớn, coordinator/buffer quá tải | Giảm payload và inflight, đo GC/RSS/queue; không chỉ tăng heap |
| Ứng dụng Java bị OOM khi bulk import | Gom dữ liệu và batch/BoundStatement quá nhiều trong RAM | Streaming theo nhóm nhỏ, điều tiết request, không giữ toàn bộ input |

### 9.1. Công cụ thao tác

Trên phiên bản Cassandra hỗ trợ, các lệnh có thể dùng để quan sát:

~~~bash
# Thống kê bảng và partition: kích thước lớn nhất, trung bình,
# số lượng partition ước lượng, SSTable và một số chỉ số tombstone.
nodetool tablestats app.events_by_tenant_hour

# Histogram về kích thước/row count partition theo phiên bản.
nodetool tablehistograms app events_by_tenant_hour

# Hàng đợi hoặc tác vụ đang chạy.
nodetool tpstats

# Áp lực nền do compaction.
nodetool compactionstats

# Tổng quan một node.
nodetool info
~~~

Các tên trường, cú pháp tùy chọn và đơn vị có thể thay đổi theo phiên bản. Cần đối chiếu metrics của bảng, JMX/Prometheus, log server và metrics của **Java driver** cùng thời điểm. Ví dụ **mean partition size** nhỏ vẫn có thể che khuất một số **partition cực lớn**; hãy xem distribution/max và tìm hot partition theo workload.

### 9.2. Những phép đo cần thu thập

1. **Từng request ghi:** payload sau serialize, số statement, số partition key duy nhất, loại batch, latency p50/p95/p99, timeout.
2. **Từng bảng:** phân phối kích thước partition, số row mỗi partition, số tombstone, số SSTable, read/write latency.
3. **Từng node:** heap/GC, native memory, network, disk I/O, pending tasks, compaction/flush/repair.
4. **Từng client:** số request đang thực thi, retry, timeout, request queue và tỷ lệ lỗi.
5. **Theo thời gian:** sự thay đổi khi ingest, TTL expiry, compaction và đợt repair; tránh kết luận chỉ từ một mẫu đo.

**Query tracing** trong cqlsh có thể giúp hiểu một truy vấn, nhưng tracing có overhead. Chỉ bật có chọn lọc trong môi trường phù hợp, không kích hoạt cho mọi request production.

## 10. Liên hệ replication, consistency, compaction và repair

### Replication và consistency level

Một partition được sao chép sang các replica theo replication strategy. Thêm replica giúp availability và yêu cầu nhất quán, nhưng cũng tăng số bản sao lưu trữ/duy trì. Với **LOCAL_QUORUM** và RF = 3 trong một datacenter, coordinator thông thường cần phản hồi từ ít nhất **2 replica** tại datacenter đó; nếu replica quá tải vì hot partition hoặc mutation lớn, request vẫn có thể timeout.

**Token-aware routing** có thể giúp chọn coordinator thuận lợi khi CQL đã bind đủ partition key. Nó không chia nhỏ một hot partition, không bỏ qua kích thước mutation và không tự động nâng mức nhất quán.

### Compaction và tombstone

Cassandra lưu dữ liệu theo cấu trúc LSM. Xóa dữ liệu hoặc hết TTL tạo **tombstone** theo ngữ nghĩa Cassandra; SSTable phải được compaction/đối chiếu an toàn trước khi một số tombstone có thể được bỏ. Collection cập nhật/xóa liên tục hoặc partition lớn có thể làm read amplification, I/O và compaction backlog tăng.

**TTL ngắn** không có nghĩa dữ liệu biến mất ngay khỏi mọi SSTable lúc hết hạn. Quy trình compaction và các điều kiện an toàn xóa vẫn ảnh hưởng disk usage và hiệu năng đọc.

### Repair và streaming

Repair đối chiếu dữ liệu giữa replica, còn streaming truyền các vùng dữ liệu cần thiết. Partition rất lớn, nhiều tombstone hoặc dữ liệu tập trung ở một số replica có thể tăng thời gian và tài nguyên bảo trì. Thiết kế bucket phải được kiểm tra với **cả workload truy vấn lẫn hoạt động repair/streaming**, không chỉ đo tốc độ INSERT.

## 11. Quy trình thiết kế hạn mức thực tế

Không có một ngưỡng chung dùng cho mọi tổ hợp Cassandra/JDK/hardware. Quy trình nên bắt đầu bằng **ngân sách ứng dụng và đo kiểm**, sau đó so với guardrail cấu hình:

1. **Đặt giới hạn đầu vào:** số byte tối đa của một sự kiện, số key trong map, độ dài chuỗi và tỷ lệ ghi theo tenant.
2. **Định nghĩa access pattern:** đọc theo tenant/giờ, trang kết quả, thời gian giữ dữ liệu; mô hình partition phải hỗ trợ truy vấn.
3. **Ước lượng partition:** dựa trên peak events/s, payload sau mã hóa và số giây trong bucket; dự trù row overhead, tombstone, nén và skew.
4. **Giới hạn batch:** chỉ gộp khi có ngữ nghĩa rõ; đặt ngân sách cả **số statement, số partition và số byte**, không dựa mỗi số câu.
5. **Đo trên dữ liệu đại diện:** đo p95/p99, throughput, timeout, GC, disk I/O, partition histogram, compaction và repair ở đỉnh tải.
6. **Thử kịch bản lỗi:** replica chậm, coordinator restart, retry, request timeout, replay/repair. Xem có ghi trùng, tăng tải hay thiếu availability không.
7. **Chọn ngưỡng vận hành và alert:** điều chỉnh ngưỡng input, bucket, concurrency và cấu hình theo số liệu; có đường rollback nếu thay đổi khiến latency/xử lý lỗi xấu đi.

Ví dụ một nhóm có thể tự đặt **ngân sách mục tiêu 16–32 MiB/partition** cho một workload nhiều truy vấn ngắn, đồng thời đặt giới hạn kích thước sự kiện tại API. Đây chỉ là **ngân sách minh họa do ứng dụng quyết định**; có hệ thống cần nhỏ hơn hoặc có thể chấp nhận lớn hơn sau khi đo kiểm. Đừng suy ra guardrail Cassandra có đúng giá trị đó.

## 12. Bài tập tình huống

### Bài 1 — Nhận diện mutation và batch

Ứng dụng muốn gửi 2.000 sự kiện, mỗi sự kiện 1 KiB, vào 2.000 tenant khác nhau. Một lập trình viên đề xuất tạo **một LOGGED BATCH** để “chỉ có một round-trip”.

**Câu hỏi:**

1. Có bao nhiêu partition độc lập ít nhất bị tác động trong tình huống này?
2. Vì sao một batch với tổng payload khoảng 2 MiB có thể gây vấn đề dù mỗi sự kiện rất nhỏ?
3. Phương án nào phù hợp hơn nếu các ghi không phải cùng một nhóm dữ liệu cần hoàn tất theo ngữ nghĩa batch?

**Gợi ý:** Có thể có 2.000 partition phân biệt; coordinator và batchlog chịu fan-out lớn, request vượt ngưỡng/timeout. Dùng prepared statement và request riêng với giới hạn inflight, retry theo idempotency, thống kê lỗi từng request.

### Bài 2 — Collection hay nhiều hàng?

Bảng chứa một cột **list<text>** ghi lại toàn bộ lịch sử thao tác của user. Sau vài tháng, một số row có hàng trăm nghìn phần tử; ứng dụng chỉ cần xem 50 thao tác mới nhất.

**Câu hỏi:** Vì sao collection không phù hợp? Hãy đề xuất primary key mới.

**Gợi ý:** Collection không cung cấp mô hình phân trang từng hoạt động như clustering rows, giá trị phát triển vô hạn dễ phát sinh mutation và tombstone lớn. Chuyển sang **((user_id, bucket_day), happened_at, event_id)** và sắp xếp clustering giảm dần; chia bucket nhỏ hơn nếu dữ liệu/ngày vượt ngân sách.

### Bài 3 — Ước lượng kích thước partition

Một tenant tạo **50 sự kiện/giây**, payload trung bình **1 KiB**.

~~~text
Trong một ngày:
50 × 86.400 × 1.024 B = 4.423.680.000 B ≈ 4,12 GiB

Trong một giờ:
50 × 3.600 × 1.024 B = 184.320.000 B ≈ 175,8 MiB

Trong 5 phút:
50 × 300 × 1.024 B = 15.360.000 B ≈ 14,6 MiB
~~~

Nếu đội vận hành đặt **ngân sách mục tiêu 32 MiB payload mỗi partition**, bucket **ngày**, **giờ** hay **5 phút** có khả năng phù hợp hơn? Có cần tính peak load và row overhead không? Đọc một ngày sẽ phải thực hiện điều gì?

**Gợi ý:** 5 phút có vẻ phù hợp hơn ở mức trung bình, nhưng phải kiểm tra đỉnh tải và kích thước thực; truy vấn cả ngày sẽ phải đọc/ghép nhiều bucket, có thể tăng fan-out. Cần cân bằng độ lớn partition với yêu cầu đọc.

### Bài 4 — Timeout và lần ghi lại

Java client dùng **BEGIN BATCH** với nhiều câu cập nhật, timeout sau khi gửi request. Người phát triển mặc định “timeout = không có ghi nào được áp dụng” và tạo event_id mới khi retry.

**Câu hỏi:** Rủi ro là gì? Thay đổi nào giúp retry an toàn?

**Gợi ý:** Một phần hoặc toàn bộ ghi có thể đã được thực hiện; batchlog cũng có thể hoàn tất ghi sau sự cố đối với loại batch phù hợp. Giữ event_id ổn định, dùng thao tác idempotent khi có thể, kiểm tra kết quả và xây cơ chế deduplication/chống ghi trùng ở tầng ứng dụng.

## 13. Câu hỏi tự kiểm tra

1. **Nếu một INSERT có một blob 40 MiB thì batch size bằng một statement có đủ an toàn không?**  
   Không. Mutation/giá trị quá lớn vẫn có thể vượt giới hạn, gây áp lực tài nguyên hoặc timeout.

2. **Tại sao thêm replica không giải quyết hoàn toàn hot partition?**  
   Mọi bản sao của partition vẫn thuộc một nhóm replica hữu hạn; không chia partition thành các mảnh tự động khi tăng RF.

3. **LOGGED BATCH qua nhiều partition có giống transaction ACID của RDBMS không?**  
   Không. Cassandra có batchlog và ngữ nghĩa hỗ trợ hoàn tất nhóm ghi sau một số lỗi, nhưng không cung cấp isolation/rollback đa partition kiểu giao dịch SQL.

4. **Vì sao LIMIT 20 không cho phép xem nhẹ partition quá lớn?**  
   LIMIT hạn chế số hàng trả về, còn chi phí tìm/đọc dữ liệu trong nhiều SSTable, tombstone và hotspot vẫn phụ thuộc mô hình lưu trữ.

5. **Khi nào collection hợp lý?**  
   Khi số phần tử nhỏ, có giới hạn và thường được truy cập như thuộc tính của một hàng; dữ liệu tăng không giới hạn nên được biểu diễn thành nhiều row.

6. **Cách chọn bucket phải bắt đầu từ đâu?**  
   Từ access pattern, peak event rate, kích thước và phân phối dữ liệu, yêu cầu latency, rồi thử nghiệm thực tế.

## 14. Tổng kết

**Mutation, batch, collection và partition là bốn phạm vi kích thước khác nhau**. Mutation ảnh hưởng đường ghi của một partition; batch gom thao tác và có thể tạo fan-out/batchlog; collection diễn tả nhiều giá trị trong một cột của một hàng và phải hữu hạn; partition định tuyến dữ liệu tới replica và quyết định nơi tập trung khối lượng đọc/ghi.

Để tối ưu Cassandra bền vững, cần giới hạn dữ liệu đầu vào, dùng collection nhỏ, tránh batch đa partition tùy tiện, thiết kế partition key/bucket theo truy vấn và đo cả đỉnh tải. Prepared statement cùng bind đúng khóa giúp ứng dụng Java gửi yêu cầu ổn định, còn replication/consistency, compaction và repair quyết định tài nguyên thực tế cần để cluster vận hành. **Đừng đẩy giới hạn cấu hình lên chỉ để che một mô hình dữ liệu đang tăng không giới hạn.**
