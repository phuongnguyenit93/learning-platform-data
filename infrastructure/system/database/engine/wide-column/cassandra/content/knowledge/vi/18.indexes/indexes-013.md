# Kiểm chứng bằng số liệu thực thi thay vì giả định có chỉ mục là đủ

> **Chương:** Chỉ mục  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — tìm hiểu kiến trúc phân tán và mô hình wide-column của Apache Cassandra, thiết kế bảng theo truy vấn, khóa phân vùng, mức nhất quán đọc/ghi và các thao tác vận hành như compaction, repair, xử lý lỗi, kết nối Java.

Tạo được index và chạy thành công câu `SELECT` là hai điều kiện cần, **chưa đủ** để chứng minh truy vấn sẽ nhanh và ổn định khi đưa vào production. Với Cassandra, một truy vấn có index vẫn có thể chạm tới nhiều node, đọc nhiều partition hoặc SSTable, tạo tải lớn cho coordinator và chậm ở đuôi phân phối độ trễ. Ngược lại, trong một số workload, đọc có điều kiện trong một partition nhỏ lại đủ nhanh mà không cần index.

Bài này hướng dẫn cách **đặt giả thuyết, đo, phân tích và quyết định** dựa trên workload thực tế, thay vì suy luận đơn giản rằng “có chỉ mục thì truy vấn nhanh”. Ví dụ sử dụng **Storage-Attached Indexing (SAI) của Apache Cassandra 5.0**; với Cassandra 4.x hoặc phiên bản/phân phối chưa hỗ trợ SAI, cần kiểm tra khả năng hỗ trợ và cú pháp trước khi thực hành. Không đồng nhất SAI với secondary index truyền thống (2i): chúng có cơ chế lưu trữ và giới hạn khác nhau.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **truy vấn hợp lệ**, **truy vấn dùng index** và **truy vấn đạt mục tiêu hiệu năng**.
2. Thiết kế phép đo đối chứng giữa truy vấn lọc không index, truy vấn qua SAI và bảng được thiết kế theo mẫu truy vấn.
3. Đo độ trễ `p50/p95/p99`, thông lượng, lỗi, áp lực I/O, chi phí ghi, kích thước dữ liệu và độ ổn định khi hệ thống chịu tải.
4. Dùng `TRACING ON`, `nodetool tablehistograms`, `tablestats`, `proxyhistograms` và metric/telemetry của ứng dụng để tìm nguồn chi phí.
5. Ra quyết định dựa trên **độ chọn lọc, số partition, phân phối dữ liệu, yêu cầu sắp xếp, SLO và tác động vận hành**.

## 2. Ba câu hỏi khác nhau: có index, có dùng index, có đáng dùng index?

| Câu hỏi | Cách kiểm tra | Điều chưa được chứng minh |
|---|---|---|
| **Index đã được khai báo chưa?** | Xem schema bằng `DESCRIBE TABLE` và trạng thái index build | Index đã sẵn sàng trên mọi replica; truy vấn đi đúng đường |
| **Truy vấn có thực sự sử dụng index không?** | Kiểm tra khả năng đáp ứng predicate, tracing và số liệu phục vụ truy vấn | Độ trễ hoặc tài nguyên thấp hơn đối chứng |
| **Index có phù hợp workload không?** | Benchmark với dữ liệu/phân phối thật, đủ mức tải, đo đọc **và ghi** | Chạy tốt lâu dài nếu dữ liệu hoặc topology thay đổi |

Đừng nhầm hai loại “số lượng”:

- **Độ chọn lọc (selectivity):** tỷ lệ hàng thỏa bộ lọc. Ví dụ `OPEN` chiếm 90% thì lọc theo status thường trả rất nhiều dữ liệu; `OPEN` chiếm 1% thì trả ít hơn. Độ chọn lọc chỉ là một biến, không tự dự báo độ trễ.
- **Cardinality:** số giá trị phân biệt của cột. Cột `status` có ít giá trị, `email` có rất nhiều giá trị. Với SAI, cả phân bố giá trị **giữa node và giữa partition** đều ảnh hưởng hiệu năng; “cardinality càng cao luôn càng tốt” là kết luận sai.

Ở Cassandra, **partition key** quyết định cách nhóm và đặt dữ liệu, replication strategy quyết định replica của partition, còn **consistency level (CL)** quyết định bao nhiêu replica phải phản hồi. Index không xóa đi các chi phí mạng, disk, coordinator, CL hoặc phân trang của một truy vấn.

### 2.1. Vì sao SAI cũng có thể tốn chi phí?

SAI lưu cấu trúc tra cứu gắn với SSTable. Khi lọc theo cột được lập chỉ mục, hệ thống thu hẹp tập hàng/partition ứng viên rồi truy xuất dữ liệu nền. Kết quả thực tế phụ thuộc số kết quả trúng, cách chúng phân tán và mức độ phải đọc dữ liệu:

- Nếu có **partition key đầy đủ**, truy vấn đã được định tuyến đến một tập replica của partition cụ thể; scan một partition nhỏ có thể cạnh tranh tốt với thao tác index.
- Nếu **thiếu partition key**, truy vấn theo index có thể phải phối hợp nhiều token range/node để tìm kết quả. Ngay cả một kết quả rất ít hàng cũng chưa chắc chỉ liên quan một node trong toàn bộ quá trình tìm kiếm.
- Nếu điều kiện phổ biến (ví dụ đa số bản ghi ở trạng thái `OPEN`), index có thể tìm ra tập ứng viên lớn, tiếp tục tốn đọc dữ liệu nền, truyền kết quả và phân trang.
- Nếu dữ liệu hoặc index còn đang được build, flush, compact hay repair, số liệu đo có thể khác trạng thái ổn định.
- Thêm index tăng chi phí quản lý trong đường ghi, dung lượng trên đĩa và thời gian xây dựng/khôi phục index; cần đo cả hiệu ứng gián tiếp lên write latency.

SAI có khả năng kết hợp nhiều điều kiện trên các cột có SAI index, nhưng mức cải thiện không tuyến tính theo số index. Khả năng truy vấn, giới hạn kiểu dữ liệu và cú pháp cụ thể phải đối chiếu đúng phiên bản Cassandra.

## 3. Một bài toán có thể kiểm chứng: tìm ticket OPEN trong một tenant/tháng

Giả sử ứng dụng hỗ trợ khách hàng lưu ticket của nhiều tenant. Màn hình cần lấy ticket có `status = 'OPEN'` trong tháng hiện tại của một tenant. Ta sẽ so sánh **ba phương án lưu trữ/truy vấn** trên cùng dữ liệu logic:

| Phương án | Mô hình | Câu hỏi thực nghiệm |
|---|---|---|
| A — Bảng gốc, không index | `tickets_plain` phân vùng theo tenant và tháng; lọc `status` | Scan trong partition có thực sự quá đắt? |
| B — Bảng gốc có SAI | `tickets_sai` cùng khóa chính; index vào `status` | SAI giảm chi phí bao nhiêu, ở phân bố nào? |
| C — Bảng theo truy vấn | `tickets_by_status` đưa `status` vào partition key | Truy xuất theo khóa có đáng giá hơn chi phí duy trì thêm bảng? |

Đây là một thí nghiệm **so sánh phương án**. Khi đo, phải nạp cùng dữ liệu vào A, B, C, giữ cùng RF/CL và cùng ngữ nghĩa bộ lọc. Phương án C có thêm khả năng sắp xếp theo thời gian bằng clustering key, nhưng đó là **một lợi ích chức năng riêng**; không nên gộp truy vấn “50 ticket mới nhất” với truy vấn “50 ticket bất kỳ” vào cùng cột so sánh độ trễ.

### 3.1. Tạo keyspace cho lab

Ví dụ dưới đây cần **Cassandra 5.0 có hỗ trợ SAI**, cqlsh và quyền tạo schema. Dùng cluster thử nghiệm cô lập. Tên datacenter `dc1` và RF = 3 chỉ đúng nếu thực tế có datacenter tên `dc1` và đủ ba node; chỉnh theo kết quả `nodetool status` trước khi chạy.

~~~sql
CREATE KEYSPACE IF NOT EXISTS index_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;
~~~

Trước benchmark, kiểm tra keyspace đã tồn tại có thật sự mang cấu hình mong muốn: `IF NOT EXISTS` **không cập nhật** schema cũ. RF nên phản ánh topology lab và phải được giữ giống nhau giữa các phương án.

### 3.2. A — Bảng không có index

~~~sql
CREATE TABLE IF NOT EXISTS index_lab.tickets_plain (
    tenant_id uuid,
    month_bucket int,
    ticket_id uuid,
    status text,
    updated_at timestamp,
    subject text,
    PRIMARY KEY ((tenant_id, month_bucket), ticket_id)
);
~~~

Khóa phân vùng gồm `tenant_id + month_bucket` để tránh dồn toàn bộ lịch sử của một tenant vào một partition. Tuy nhiên, một tenant cực lớn vẫn có thể tạo partition theo tháng quá rộng; cần đo phân phối kích thước và xem xét bucket nhỏ hơn nếu thực tế đòi hỏi.

Khi chưa có index trên `status`, muốn lọc theo cột thường cần chỉ thị `ALLOW FILTERING`:

~~~sql
SELECT ticket_id, status, updated_at, subject
FROM index_lab.tickets_plain
WHERE tenant_id = 5bd928ad-a5aa-4eb9-8c12-bfda73571a70
  AND month_bucket = 202611
  AND status = 'OPEN'
ALLOW FILTERING;
~~~

**Chỉ dùng câu trên như đối chứng trong lab**, với dữ liệu được giới hạn và theo dõi. `ALLOW FILTERING` cho phép thực hiện phép lọc có thể đòi đọc nhiều hàng hơn số hàng trả về; bản thân nó không phải cách sửa thiết kế dữ liệu cho production.

### 3.3. B — Cùng khóa chính, thêm SAI

~~~sql
CREATE TABLE IF NOT EXISTS index_lab.tickets_sai (
    tenant_id uuid,
    month_bucket int,
    ticket_id uuid,
    status text,
    updated_at timestamp,
    subject text,
    PRIMARY KEY ((tenant_id, month_bucket), ticket_id)
);

CREATE INDEX IF NOT EXISTS tickets_status_sai_idx
ON index_lab.tickets_sai (status)
USING 'sai';
~~~

Đây là cú pháp SAI trong Apache Cassandra 5.0. Chỉ chạy benchmark sau khi mọi replica liên quan **hoàn tất xây dựng index** và trạng thái index được xác nhận theo công cụ/metric của phiên bản đang dùng. Cassandra có thể xây dựng index bất đồng bộ cho dữ liệu đã tồn tại; chỉ nhìn thấy lệnh `CREATE INDEX` thành công không đủ chứng minh đã sẵn sàng.

~~~sql
SELECT ticket_id, status, updated_at, subject
FROM index_lab.tickets_sai
WHERE tenant_id = 5bd928ad-a5aa-4eb9-8c12-bfda73571a70
  AND month_bucket = 202611
  AND status = 'OPEN';
~~~

Ở đây ứng dụng đã cung cấp partition key đầy đủ và một predicate có SAI index. Cần đo xem SAI có mang lại lợi ích thực sự so với scan trong cùng partition, đặc biệt khi tỷ lệ `OPEN` thay đổi.

### 3.4. C — Bảng thiết kế theo truy vấn

~~~sql
CREATE TABLE IF NOT EXISTS index_lab.tickets_by_status (
    tenant_id uuid,
    status text,
    month_bucket int,
    updated_at timestamp,
    ticket_id uuid,
    subject text,
    PRIMARY KEY ((tenant_id, status, month_bucket), updated_at, ticket_id)
) WITH CLUSTERING ORDER BY (updated_at DESC, ticket_id ASC);
~~~

Lúc này truy vấn lấy tất cả ticket `OPEN` của tenant trong tháng được giải bằng **partition key**, không cần secondary index:

~~~sql
SELECT ticket_id, status, updated_at, subject
FROM index_lab.tickets_by_status
WHERE tenant_id = 5bd928ad-a5aa-4eb9-8c12-bfda73571a70
  AND status = 'OPEN'
  AND month_bucket = 202611;
~~~

Nếu yêu cầu chức năng là **50 ticket được cập nhật mới nhất**, bảng C có clustering key phù hợp:

~~~sql
SELECT ticket_id, status, updated_at, subject
FROM index_lab.tickets_by_status
WHERE tenant_id = 5bd928ad-a5aa-4eb9-8c12-bfda73571a70
  AND status = 'OPEN'
  AND month_bucket = 202611
LIMIT 50;
~~~

Hai phương án A/B **không** có cùng bảo đảm sắp xếp theo `updated_at DESC`. Vì vậy muốn so sánh đúng một tính năng có thứ tự, phải thiết kế lại baseline có khả năng đáp ứng cùng ngữ nghĩa, hoặc ghi rõ A/B không đáp ứng được tính năng. Không lấy một tập 50 hàng tùy ý từ SAI rồi gọi đó là “50 hàng mới nhất”.

**Đổi lại:** để duy trì C khi ticket chuyển `OPEN → CLOSED` hoặc khi `updated_at` đổi, ứng dụng cần xóa hàng ở khóa cũ và chèn hàng ở khóa mới. Với A/B, cập nhật `status` không buộc ứng dụng tự chuyển hàng giữa các partition theo trạng thái, dù vẫn có chi phí duy trì SAI ở B. Mô hình C vì thế cần chiến lược cập nhật nhất quán, retry/idempotency và xử lý bản ghi stale; các bảng do ứng dụng dual-write không mặc nhiên có giao dịch đa bảng tuyến tính.

### 3.5. Ghi dữ liệu nhất quán vào ba phương án

Ví dụ một ticket để kiểm tra schema và kết quả truy vấn. Các khóa và giá trị ở ba câu `INSERT` phải đại diện cho **cùng một ticket logic**:

~~~sql
INSERT INTO index_lab.tickets_plain
    (tenant_id, month_bucket, ticket_id, status, updated_at, subject)
VALUES (
    5bd928ad-a5aa-4eb9-8c12-bfda73571a70,
    202611,
    f8ba776b-eb1a-4b94-8d2d-6d5460dbad1d,
    'OPEN',
    '2026-11-21T08:15:00Z',
    'Kiểm tra giới hạn truy cập'
);

INSERT INTO index_lab.tickets_sai
    (tenant_id, month_bucket, ticket_id, status, updated_at, subject)
VALUES (
    5bd928ad-a5aa-4eb9-8c12-bfda73571a70,
    202611,
    f8ba776b-eb1a-4b94-8d2d-6d5460dbad1d,
    'OPEN',
    '2026-11-21T08:15:00Z',
    'Kiểm tra giới hạn truy cập'
);

INSERT INTO index_lab.tickets_by_status
    (tenant_id, status, month_bucket, updated_at, ticket_id, subject)
VALUES (
    5bd928ad-a5aa-4eb9-8c12-bfda73571a70,
    'OPEN',
    202611,
    '2026-11-21T08:15:00Z',
    f8ba776b-eb1a-4b94-8d2d-6d5460dbad1d,
    'Kiểm tra giới hạn truy cập'
);
~~~

Một hàng chỉ xác minh cú pháp, **không tạo benchmark có ý nghĩa**. Cần sinh/nạp dữ liệu khối lượng đại diện cho thực tế: hàng chục đến hàng trăm nghìn partition, đủ nhiều hàng ở tenant/tháng lớn, nhiều tenant nhỏ, phân phối trạng thái lệch, bản ghi được cập nhật/xóa và dữ liệu đã đi qua các chu kỳ flush/compaction tự nhiên. Ghi rõ công cụ nạp, seed, kích thước tổng dữ liệu, trạng thái index build, phiên bản Cassandra và topology trong nhật ký thực nghiệm.

## 4. Thiết kế benchmark để trả lời đúng câu hỏi

### 4.1. Giả thuyết và tiêu chí thành công

Ví dụ giả thuyết ban đầu:

> Với tenant/tháng có nhiều ticket nhưng tỷ lệ `OPEN` thấp, phương án B sẽ giảm p95/p99 so với lọc không index; khi tỷ lệ `OPEN` cao, lợi ích có thể nhỏ hoặc âm. Phương án C thường có lợi với truy vấn theo tenant/status/tháng, đặc biệt khi cần sắp xếp theo thời gian, nhưng phải tính chi phí duy trì bảng và các cập nhật trạng thái.

Đây là **giả thuyết cần đo**, không phải kết quả đã được xác minh. Trước khi chạy, xác định SLO của sản phẩm, chẳng hạn p99 truy vấn đọc không vượt **100 ms** tại **300 yêu cầu/giây** trong một profile tải cụ thể, cùng ngưỡng lỗi và mức tăng write latency cho phép. Những con số SLO này chỉ là **ví dụ thiết kế thử nghiệm**, không phải số liệu thực nghiệm Cassandra.

Để kết luận, cần so sánh cả số liệu **đáp ứng trải nghiệm người dùng** và chi phí hệ thống. Một phương án nhanh hơn 10 ms ở p50 nhưng gây timeout hoặc làm tăng p99 đọc/ghi khi nhiều client cùng truy vấn có thể không đạt SLO.

### 4.2. Ma trận dữ liệu và tải

Không đo một query lặp lại trên một khóa duy nhất. Gợi ý ma trận tối thiểu:

| Trục khảo sát | Mức thử | Mục đích |
|---|---|---|
| Số hàng trong một tenant/tháng | 100; 10.000; 100.000 | Kiểm tra chi phí khi partition lớn |
| Tỷ lệ `OPEN` | 1%; 25%; 90% | Phân biệt index lọc ít và lọc nhiều |
| Phân phối tenant | Nhiều tenant nhỏ và một số tenant rất lớn | Kiểm tra skew/hot partition |
| Số client đồng thời | 1; 10; 50 (điều chỉnh theo môi trường) | Quan sát tail latency và fan-out |
| Loại tải | Chỉ đọc; đọc xen ghi; cập nhật `status`; xóa | Đo chi phí duy trì index và bảng C |
| Trạng thái cache | Cold/warm được **ghi rõ**, không trộn tùy tiện | Tránh giải thích sai kết quả nhờ cache |
| Kích cỡ kết quả | 20; 100; toàn bộ kết quả qua paging | Đo ảnh hưởng `LIMIT` và network |

**Giữ cố định** khi so sánh: số node, rack/DC, replication factor, CL, driver, prepared statement, page size, dữ liệu logic, tốc độ tải, phần cứng, codec/compaction strategy, trạng thái sửa chữa node, và profile truy vấn. Đo nhiều lượt độc lập, sau warm-up và ở trạng thái nền ổn định; đảo thứ tự chạy A/B/C giữa các lượt để giảm sai lệch do cache hoặc compaction.

Không cố ý chạy repair, major compaction hoặc thêm/bớt node ngay giữa một cặp benchmark trừ khi đó là biến đang nghiên cứu. Nếu background compaction hoặc GC mạnh xuất hiện, phải đánh dấu cửa sổ đo đó để phân tích riêng.

### 4.3. Kiểm tra đúng dữ liệu và đúng ngữ nghĩa trước khi đo nhanh

Với truy vấn lấy **tất cả** ticket trúng bộ lọc, kiểm tra:

1. Ba bảng chứa cùng tập ticket logic cho tenant và tháng được chọn, không thiếu và không nhân đôi; sử dụng khóa `ticket_id` để đối chiếu.
2. Thống nhất cột trả về, điều kiện lọc, CL và cách phân trang; đọc hết tất cả trang để tính số hàng thực được trả về.
3. Đọc kết quả theo lô tương đương. Không cho phương án A/B trả hàng tùy ý nhưng C chỉ trả 50 hàng mới nhất rồi so p99 như cùng workload.
4. Đối với phép đo chỉ truy vấn, hoàn tất công việc đồng bộ bảng C/index B trước khi đo. Đối với phép đo từ luồng ghi đến lúc đọc được dữ liệu, đưa chính **độ trễ cập nhật** vào phạm vi thí nghiệm và kiểm tra tính nhất quán theo CL.
5. Xác minh không có truy vấn lỗi, timeout hoặc trang cuối bị bỏ qua. Một kết quả “nhanh” nhưng thiếu hàng là thất bại chức năng.

Trong ứng dụng Java, prepared statement và paging của driver giúp đo sát thực tế. Nếu benchmark lấy mọi kết quả, chỉ đo sau khi **đã tiêu thụ toàn bộ ResultSet**, bởi `execute()` có thể chưa tải tất cả các trang tại thời điểm trả về.

## 5. Thu thập số liệu trực tiếp từ Cassandra

### 5.1. Tracing: hiểu đường thực thi của một truy vấn

Trong `cqlsh`:

~~~text
CONSISTENCY LOCAL_QUORUM
TRACING ON
~~~

Chạy **lần lượt từng câu SELECT** của ba phương án ở mục 3 rồi tắt:

~~~text
TRACING OFF
~~~

`LOCAL_QUORUM` trong ví dụ phù hợp khi RF và DC đã được thiết lập đúng; nếu lab chỉ có một replica, hãy chọn CL hợp lệ cho chính môi trường đó và giữ nhất quán giữa A/B/C.

Với mỗi trace, ghi lại:

| Tín hiệu trace | Câu hỏi cần trả lời |
|---|---|
| Tổng duration do Cassandra ghi | Truy vấn nào tốn nhiều thời gian phía cluster? |
| Hoạt động trên coordinator/replica | Bao nhiêu node tham gia phục vụ request? Có giao tiếp mạng phân tán không? |
| Các pha index lookup, partition/SSTable read, filtering (tùy phiên bản) | Tốn chi phí tra index hay đọc dữ liệu nền? |
| Chờ I/O, phát thông điệp, retry (nếu trace thể hiện) | Có dấu hiệu nghẽn disk, mạng hoặc coordinator không? |
| Số kết quả trả về và thời gian phân trang | Có tương xứng với lượng dữ liệu phải xử lý không? |

Tên hoạt động trong trace khác nhau theo phiên bản và loại truy vấn, vì vậy hãy đọc **chuỗi sự kiện thực tế**, không tìm một dòng chữ cố định để kết luận index đã được dùng.

**Giới hạn của tracing:** tracing thêm overhead, ghi dữ liệu trace và phù hợp với **mẫu truy vấn có chọn lọc**, không bật đại trà trong toàn bộ load test. Duration phía server không bằng latency đầu-cuối tại ứng dụng: ứng dụng còn chịu connection pool, serialization/deserialization, tải từng trang và đường mạng.

### 5.2. Histogram và trạng thái bảng

Các lệnh trên node Cassandra:

~~~bash
nodetool tablehistograms index_lab tickets_plain
nodetool tablehistograms index_lab tickets_sai
nodetool tablehistograms index_lab tickets_by_status
~~~

Tùy phiên bản, `tablehistograms` cho percentile của read/write latency cục bộ, số SSTable tham gia một lần đọc, kích thước partition và số cell. Đối chiếu với số đo phía client; các histogram này thường là số liệu **tích lũy theo bảng/node**, chịu ảnh hưởng bởi workload khác nếu lab không cô lập.

~~~bash
nodetool tablestats index_lab.tickets_plain
nodetool tablestats index_lab.tickets_sai
nodetool tablestats index_lab.tickets_by_status
nodetool proxyhistograms
~~~

`tablestats` giúp theo dõi dung lượng, số liệu đọc/ghi, SSTable và trạng thái lưu trữ theo bảng. `proxyhistograms` phản ánh phân phối độ trễ ở coordinator cho **nhiều request**, không phải riêng một câu SELECT, nên cần cô lập tải và diễn giải theo cửa sổ đo. Để đo chi phí SAI trên disk/JMX, đối chiếu bộ metric SAI được hỗ trợ trong **phiên bản chạy thực tế**; không suy ra chính xác dung lượng index chỉ từ một thống kê tổng kích thước bảng.

Các lệnh ở trên là **lệnh kiểm tra**, không thay đổi nội dung dữ liệu. Với môi trường sản xuất, ưu tiên số liệu sẵn có từ observability stack thay vì tạo load mới.

### 5.3. Metric cần ghi cùng một mốc thời gian

| Nhóm | Metric hữu ích | Vì sao cần |
|---|---|---|
| Trải nghiệm ứng dụng | p50, p95, p99 và max của **end-to-end latency**; tỷ lệ timeout/error | Xác định có đạt SLO hay không |
| Lưu lượng | QPS thành công/lỗi; số client; requests in flight; số trang/hàng trả về | Đảm bảo so sánh cùng công việc |
| Coordinator | Độ trễ coordinator, pending/blocked tasks, tải mạng giữa node | Phát hiện fan-out và nghẽn dịch vụ |
| Replica/table | Local read latency, SSTables per read, partition size, disk read, heap/GC | Tìm nguyên nhân khác biệt |
| Chi phí ghi | p95/p99 write latency, throughput ghi, compaction backlog, index build | Tránh tối ưu đọc làm chậm ghi |
| Tài nguyên | CPU, memory/GC, disk IOPS/bandwidth, network, disk footprint | Đánh giá khả năng mở rộng và chi phí vận hành |

Gắn nhãn variant (A/B/C), tập dữ liệu, phân bố `OPEN`, concurrency, CL và phiên bản. Chỉ một ảnh chụp metrics “trước/sau” không đủ tách tác động của index khỏi thay đổi tải, cache và compaction.

## 6. Đo từ Java: quan sát đúng thời gian người dùng chờ

Ví dụ với **DataStax/Apache Cassandra Java Driver 4.x** trên một `CqlSession` đã kết nối. Đặt prepared statement cho phương án B:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

PreparedStatement prepared = session.prepare(
    "SELECT ticket_id, status, updated_at, subject " +
    "FROM index_lab.tickets_sai " +
    "WHERE tenant_id = ? AND month_bucket = ? AND status = ?");

UUID tenant = UUID.fromString("5bd928ad-a5aa-4eb9-8c12-bfda73571a70");
BoundStatement statement = prepared.bind(tenant, 202611, "OPEN")
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(500);

long started = System.nanoTime();
ResultSet rows = session.execute(statement);
int returnedRows = 0;
for (Row row : rows) {
    returnedRows++;
    // Đọc nội dung cột cần thiết như workload thật, không in từng dòng.
    row.getUuid("ticket_id");
}
long elapsedNs = System.nanoTime() - started;
double latencyMs = elapsedNs / 1_000_000.0;
~~~

Đo trên **nhiều lần chạy và nhiều khóa**, tái sử dụng prepared statement và session; ghi lại `latencyMs`, `returnedRows`, lỗi/timeout và nhãn dataset để tính phân phối. Không dùng một lần gọi `System.nanoTime()` làm kết luận hiệu năng. Trong benchmark nghiêm túc, ghi số liệu vào histogram hỗ trợ concurrency và cả thao tác đọc xen ghi theo tỷ lệ thật.

Nếu workload của sản phẩm chỉ lấy trang đầu tiên, phải đo **trang đầu tiên** với paging semantics thực tế; nếu người dùng cuộn đến cuối, đo cả chuỗi trang. Hai loại thời gian đó không thể thay thế nhau.

## 7. Mẫu bảng kết quả thực nghiệm

Ghi số thật từ hệ thống của bạn; **không điền các con số ví dụ như thể đó là kết quả benchmark**.

| Variant | Tenant/tháng | % OPEN | QPS | p50 (ms) | p95 (ms) | p99 (ms) | Timeout % | Hàng trả về | Ghi chú |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A — lọc, không index | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _trace, SSTable, CPU_ |
| B — SAI | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _index build, fan-out_ |
| C — bảng theo truy vấn | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _chi phí dual-write_ |

Thêm bảng **write workload** riêng theo cùng mức tải (đọc:ghi, kiểu cập nhật trạng thái, p95/p99 ghi, số lỗi, dung lượng) và lưu trace mẫu. Nếu phương án C dùng thêm bảng, tổng chi phí phải gồm **toàn bộ bảng/ghi** cần duy trì cho một ticket, không chỉ kích thước của bảng tra cứu C.

Để một reviewer có thể kiểm chứng kết quả, báo cáo cần nêu:

- **Thông số:** Cassandra/Java driver version, số node/CPU/RAM/disk, RF, CL, compaction strategy, schema/index options.
- **Dữ liệu:** tổng rows/partition, phân phối hàng giữa tenant, tỷ lệ `OPEN`, tuổi dữ liệu, TTL/tombstone nếu có, data seed.
- **Tải:** QPS, concurrency, client pool, read/write mix, kích thước trang, thứ tự chạy, warm-up, thời lượng mẫu.
- **Bằng chứng:** bảng percentile/error, metric node/table, trace đại diện và kết quả đối soát row counts/keys.
- **Quyết định:** phương án đạt SLO nào, chi phí write/storage ra sao và khi nào cần benchmark lại.

## 8. Đọc kết quả và chọn thiết kế

### 8.1. Những kết luận có thể xảy ra (phải xác nhận bằng số)

**Trường hợp 1 — partition nhỏ, đa số hàng trúng lọc.** A có thể nhanh tương đương hoặc nhanh hơn B vì đọc trong partition đã rẻ, còn index không loại bỏ nhiều hàng. Khi đó giữ một index có thể chỉ tăng chi phí ghi/disk. Không suy rộng kết quả sang partition lớn hay workload khác.

**Trường hợp 2 — partition lớn, chỉ ít hàng trúng lọc.** B có thể giúp giảm lượng công việc so với A. Nếu p95/p99 đạt SLO và chi phí duy trì index chấp nhận được, B có thể phù hợp, nhất là khi ứng dụng cần tìm theo nhiều điều kiện khác nhau.

**Trường hợp 3 — truy vấn thường xuyên yêu cầu “ticket mới nhất theo tenant và status”.** C cung cấp quyền truy cập trực tiếp theo partition key và thứ tự clustering key. Nếu tốc độ đọc quan trọng và ứng dụng chấp nhận đồng bộ nhiều bảng, C thường là ứng viên cần benchmark nghiêm túc.

**Trường hợp 4 — truy vấn không có partition key và kết quả phân bố khắp cluster.** Dù có index, network fan-out/coordinator load và tail latency có thể chi phối. Khi đó xem xét chỉnh yêu cầu truy vấn, thêm partition key có ý nghĩa nghiệp vụ hoặc thiết kế bảng chuyên dụng, thay vì chỉ thêm index.

Không chọn theo p50 duy nhất. Quan sát **p99 dưới tải mục tiêu, lỗi/timeout và độ bền sau tăng dữ liệu**. Một benchmark với vài trăm hàng hoặc một node không đại diện cho cluster sản xuất nhiều replica, mạng và compaction.

### 8.2. Sai lầm phổ biến và cách khắc phục

| Sai lầm | Vì sao dễ cho kết luận sai | Cách sửa |
|---|---|---|
| “CREATE INDEX thành công nghĩa là đã tối ưu” | Không chứng minh index build xong, query dùng nó hay SLO đạt | Xác minh trạng thái build, tracing và benchmark |
| So A trên dữ liệu lớn với B trên dữ liệu ít | Khối lượng xử lý khác nhau | Nạp và đối soát cùng bộ dữ liệu |
| Chỉ đo `LIMIT 10` | Có thể che giấu chi phí truy vấn nhiều trang hoặc tạo ấn tượng sai về độ sắp xếp | Đo các kích cỡ kết quả và semantics thật |
| Chỉ so thời gian trong `cqlsh` | Trộn chi phí rendering, network, coordinator và client | Đo driver end-to-end; dùng tracing để giải thích |
| Chạy khi index đang build hoặc cluster đang repair | Số liệu dao động và hệ thống chịu tải nền khác nhau | Chọn cửa sổ ổn định, ghi log tác vụ nền |
| Đo một khóa nóng lặp lại | Cache/partition skew làm kết quả đẹp giả | Dùng nhiều tenant, nhiều kích cỡ partition |
| Dùng `ALLOW FILTERING` làm giải pháp dài hạn | Có thể phải đọc nhiều dữ liệu để trả ít kết quả | Chỉ dùng đối chứng có kiểm soát; xét SAI hoặc bảng theo truy vấn |
| Chỉ đo đọc mà bỏ qua ghi | Index và bảng bổ sung cũng cần cập nhật, chiếm disk | Đo mixed workload và trạng thái thay đổi status |
| So `ONE` với `QUORUM` | Mức phản hồi replica khác nhau tạo lệch lớn | Giữ CL cố định, ghi rõ mức nhất quán |
| Nhìn p50 và bỏ qua p99 | Người dùng vẫn gặp tail latency hoặc timeout | Đặt SLO theo percentile, lỗi và tải mục tiêu |

## 9. Quy trình quyết định trước khi chấp nhận một index

~~~mermaid
flowchart TD
    A["Xác định truy vấn thật và SLO"] --> B["Kiểm tra partition key, CL, số hàng và phân bố"]
    B --> C{"Truy vấn đã đi theo partition key phù hợp?"}
    C -->|Có| D["Benchmark đường đọc PK không index"]
    C -->|Chưa| E["Xét SAI và bảng theo truy vấn"]
    D --> F["Tạo biến thể SAI trong lab"]
    E --> F
    F --> G["Đối soát kết quả, đợi index build, warm-up"]
    G --> H["Đo read/write, p95/p99, lỗi, node metrics"]
    H --> I{"Đạt SLO và chi phí chấp nhận được?"}
    I -->|Có| J["Lưu số liệu, chọn phương án và đặt ngưỡng giám sát"]
    I -->|Không| K["Sửa khóa/bảng, index, phân trang hoặc yêu cầu truy vấn"]
    K --> G
~~~

**Tiêu chuẩn chấp nhận** nên bao gồm:

1. **Đúng dữ liệu:** kết quả khớp kỳ vọng qua nhiều partition, trang và cập nhật; không lấy độ trễ thấp làm lý do chấp nhận trả thiếu hàng.
2. **Đạt SLO:** p95/p99 và tỷ lệ lỗi ở lưu lượng dự kiến, có biên dự phòng cho tăng trưởng dữ liệu.
3. **Chi phí chấp nhận được:** CPU, I/O, mạng, write latency, compaction/index build và dung lượng.
4. **Khả năng vận hành:** quan sát được index health, xử lý build/rebuild/repair, triển khai và rollback schema theo quy trình của phiên bản.
5. **Khả năng mở rộng:** khi tenant lớn hoặc tỷ lệ status thay đổi, đo lại trên ma trận dữ liệu mới thay vì tin kết quả cũ mãi mãi.

Với index đã triển khai, nên có dashboard theo workload để quan sát p95/p99, timeout, read/write throughput, compaction backlog và dung lượng index. Khi thay đổi schema, RF, CL, driver hoặc pattern truy vấn, **chạy lại** benchmark liên quan.

## 10. Bài tập thực hành

**Bài 1 — Vì sao cùng một index nhưng chênh lệch lớn?** Hai tenant có cùng số ticket trong tháng. Tenant A có 1% `OPEN`, tenant B có 90% `OPEN`. Hãy dự đoán biến nào sẽ thay đổi giữa truy vấn A và B, lập ít nhất ba metric để kiểm chứng dự đoán và giải thích vì sao không thể kết luận chỉ từ một tỷ lệ.

**Bài 2 — Kiểm tra tính đúng của đối chứng.** Một benchmark báo SAI lấy 20 hàng trong 4 ms, còn bảng theo truy vấn lấy 50 ticket mới nhất trong 7 ms. Có thể kết luận index nhanh hơn không? Hãy chỉ ra ít nhất hai điểm chưa tương đương (semantics `LIMIT`/ordering, lượng dữ liệu trả về, CL, cache hoặc concurrency) và thiết kế lại phép đo.

**Bài 3 — Đọc trace.** Ghi trace cho cùng `tenant_id`/`month_bucket` tại các tỷ lệ status khác nhau, đối chiếu độ trễ client, local read latency, SSTables per read và số lượng replica tham gia. Nếu index có trace duration thấp nhưng p99 client cao, hãy đề xuất các nguyên nhân ở driver, network và phân trang.

**Bài 4 — Chốt phương án triển khai.** Với SLO p99 ≤ 100 ms tại 300 QPS (chỉ là mục tiêu giả định), hãy xây bảng kết quả A/B/C và quyết định chọn phương án nào, bao gồm read latency, write latency, disk footprint và chi phí cập nhật ticket khi đổi trạng thái. Nếu chưa có số đo, ghi rõ “chưa đủ bằng chứng” thay vì tự điền.

### Checklist nộp bài lab

- [ ] Có ba schema, cùng dữ liệu logic và đủ bản ghi để tạo chênh lệch có ý nghĩa.
- [ ] Ghi rõ Cassandra version; SAI chỉ được dùng khi môi trường hỗ trợ.
- [ ] Query A/B/C đúng cùng predicate và kết quả đã được đối soát.
- [ ] Có ma trận phân phối status, kích thước partition và concurrency.
- [ ] Có p50/p95/p99, lỗi, QPS, số hàng và mức CL; có mixed read/write workload.
- [ ] Có ít nhất một trace mẫu cho mỗi biến thể và metric `nodetool`/JMX đối chiếu.
- [ ] Có nhận xét về chi phí duy trì index/bảng và kết luận theo SLO có ghi bằng chứng.

## Tài liệu tham khảo

1. Apache Cassandra — [Working with Storage-Attached Indexing (SAI)](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-working-with.html): cú pháp `CREATE INDEX ... USING 'sai'` và cách truy vấn.
2. Apache Cassandra — [SAI FAQ](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-faq.html): ảnh hưởng của cardinality, partition và phạm vi truy vấn.
3. Apache Cassandra — [When to use a secondary index](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/2i/2i-when-to-use.html): trường hợp cần cân nhắc index hoặc thiết kế dữ liệu khác.
4. Apache Cassandra — [Use Nodetool](https://cassandra.apache.org/doc/stable/cassandra/troubleshooting/use_nodetool.html): `tablehistograms`, `proxyhistograms` và điều tra latency.
5. Apache Cassandra — [Monitoring](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html): chỉ số table, latency, histogram và JMX.
