# Viết quyết định kiến trúc bằng thử nghiệm, chi phí và các giả định

Trong hệ thống dùng **Apache Cassandra**, một quyết định như “chia partition theo ngày”, “đọc bằng LOCAL_QUORUM” hay “dùng TimeWindowCompactionStrategy” không nên chỉ dựa vào kinh nghiệm hoặc lời khuyên chung. Hiệu quả của mỗi lựa chọn phụ thuộc vào hình dạng truy vấn, phân bố khóa phân vùng, tốc độ ghi, mức nhất quán, thời gian lưu trữ và khả năng vận hành của **chính ứng dụng**.

Một quyết định kiến trúc tốt cần trả lời được bốn câu hỏi:

1. **Vấn đề cần giải quyết là gì?** Nêu ràng buộc nghiệp vụ và chỉ tiêu kỹ thuật có thể đo.
2. **Ta đang giả định điều gì?** Ghi rõ điều chưa biết, mức độ rủi ro và cách xác minh.
3. **Bằng chứng nào phân biệt các phương án?** Thiết kế thử nghiệm có khả năng bác bỏ giả thuyết.
4. **Chi phí và điều kiện thay đổi quyết định là gì?** Tính cả tài nguyên, vận hành, độ phức tạp và khả năng phục hồi.

Kết quả thường được ghi vào **Architecture Decision Record (ADR)**: bản ghi ngắn, có phiên bản, giải thích bối cảnh, các phương án đã xem xét, bằng chứng, quyết định và thời điểm cần đánh giá lại. Đây là một phần của thiết kế kiến trúc ứng dụng Cassandra, không phải thủ tục viết tài liệu sau khi đã triển khai.

## 1. Bắt đầu từ truy vấn, SLO và ràng buộc

Giả sử hệ thống thu thập telemetry của **20.000 thiết bị**, trung bình mỗi thiết bị gửi **một sự kiện/phút**. Ứng dụng cần:

| Nhu cầu | Ràng buộc minh họa phải xác minh với sản phẩm |
|---|---|
| Ghi sự kiện | Trung bình khoảng 333 lần ghi/giây, đỉnh dự kiến 3.000 lần ghi/giây |
| Xem lịch sử thiết bị | Đọc 100 sự kiện mới nhất hoặc một khoảng thời gian của một thiết bị |
| Độ trễ ghi | p99 phía ứng dụng không vượt 80 ms ở tải mục tiêu |
| Độ trễ đọc | p99 phía ứng dụng không vượt 150 ms ở tải mục tiêu |
| Giữ dữ liệu | 30 ngày kể từ khi ghi; làm rõ cách xử lý sự kiện đến muộn |
| Khả dụng | Chịu được một node hỏng trong một datacenter với RF = 3, trong giới hạn tải đã thử |
| Tính nhất quán | Định nghĩa độ mới dữ liệu mà màn hình đọc cần; không mặc định mọi đường đọc có yêu cầu như nhau |

**SLO** (Service Level Objective) là mục tiêu của ứng dụng, ví dụ “99% yêu cầu đọc hoàn tất dưới 150 ms trong cửa sổ đo được chỉ định”. SLO phải nói rõ vị trí đo (client, API hay Cassandra coordinator), tải đo, tỷ lệ lỗi được chấp nhận và điều kiện lỗi node. Nếu chỉ nói “truy vấn nhanh”, không thể biết một phương án đã tốt hay chưa.

Với một workload dự kiến, tính nhẩm bước đầu:

~~~text
events_per_day = 20.000 * 1 * 1.440 = 28.800.000
average_writes_per_second = 28.800.000 / 86.400 ≈ 333
~~~

Những số này là **đầu vào giả định của bài tập**, không phải kết quả benchmark. Đặc biệt, trung bình 333 ghi/giây không cho biết mức đỉnh, dữ liệu đến dồn, mức lệch giữa các thiết bị hoặc tỷ lệ đọc/ghi thực tế.

### Phân biệt sự thật, giả định và quyết định

| Loại | Ví dụ | Cách xử lý |
|---|---|---|
| Sự thật đã kiểm chứng | API hiện tại truy vấn lịch sử theo thiết bị và khoảng thời gian | Dẫn đến trace, đặc tả API hoặc log |
| Giả định | Không thiết bị nào vượt 10 sự kiện/giây trong thời gian dài | Kiểm tra phân bố tải, đặc biệt p99 và cực đại theo thiết bị |
| Ràng buộc | Dữ liệu chỉ được lưu 30 ngày | Xác nhận yêu cầu nghiệp vụ và cách tính mốc 30 ngày |
| Giả thuyết | Bucket theo ngày sẽ giữ kích thước partition trong ngân sách | Đo kích thước partition sau khi nạp dữ liệu có lệch tải |
| Quyết định | Dùng bucket ngày nếu đạt ngưỡng trong thí nghiệm | Ghi trong ADR cùng bằng chứng, hệ quả và điều kiện thay đổi |

Không biến một giả định chưa đo thành “sự thật” chỉ vì nó xuất hiện trong sơ đồ kiến trúc.

## 2. Đề xuất phương án dữ liệu theo truy vấn

Cassandra là cơ sở dữ liệu **wide-column phân tán**. Dữ liệu được phân bổ theo **partition key**; các hàng trong một partition được sắp xếp theo **clustering columns**. Thiết kế bảng phải bắt đầu từ truy vấn cần phục vụ. Một truy vấn không được hỗ trợ bởi khóa phân vùng thường đòi hỏi bảng chuyên biệt, thay vì quét phân tán hoặc phụ thuộc vào ALLOW FILTERING.

Xét ba phương án lưu lịch sử sự kiện theo thiết bị:

| Phương án | Partition key | Lợi ích có thể có | Rủi ro phải thử |
|---|---|---|---|
| A — không bucket | (tenant_id, device_id) | Một lần truy vấn có thể đọc lịch sử dài | Partition tăng rất lớn; đọc và compaction khó dự đoán |
| B — bucket ngày | (tenant_id, device_id, event_day) | Giới hạn thời gian trong một partition; truy vấn theo ngày rõ ràng | Đọc nhiều ngày phải fan-out có giới hạn |
| C — bucket giờ | (tenant_id, device_id, event_hour) | Thu nhỏ partition khi thiết bị sinh sự kiện dày đặc | Nhiều partition hơn, nhiều truy vấn hơn, phải hợp nhất kết quả |

Đừng chọn C chỉ vì “partition càng nhỏ càng tốt”: mỗi partition bổ sung cũng có metadata, thao tác truy vấn và chi phí điều phối. Đừng chọn A chỉ vì số partition ít: một partition không có giới hạn thực tế là rủi ro khi lưu lâu hoặc gặp thiết bị phát dữ liệu bất thường.

Một schema minh họa cho phương án B:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry.events_by_device_day (
    tenant_id uuid,
    device_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id timeuuid,
    payload text,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC)
  AND default_time_to_live = 2592000;
~~~

**Giải thích:**

- Bộ ba **(tenant_id, device_id, event_day)** tạo một partition; cả ba giá trị phải được cung cấp khi truy vấn partition này.
- **occurred_at** và **event_id** là clustering columns. **event_id** phân biệt các sự kiện có cùng timestamp; ứng dụng phải giữ nguyên ID khi gửi lại cùng sự kiện.
- TTL 2.592.000 giây bằng 30 ngày và được tính từ thời điểm ghi, **không tự động tính từ occurred_at**. Nếu nghiệp vụ yêu cầu hết hạn đúng theo thời gian phát sinh sự kiện, cần có chính sách riêng cho sự kiện đến muộn.
- Giá trị **dc1** chỉ là tên datacenter ví dụ. Phải thay bằng tên datacenter thực tế; khai báo RF = 3 ở một DC không đồng nghĩa hệ thống đã có khả năng chịu mất toàn bộ DC.

Ví dụ truy vấn phù hợp khóa:

~~~sql
CONSISTENCY LOCAL_QUORUM;

SELECT occurred_at, event_id, payload
FROM telemetry.events_by_device_day
WHERE tenant_id = 11111111-1111-1111-1111-111111111111
  AND device_id = 22222222-2222-2222-2222-222222222222
  AND event_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T08:00:00Z'
  AND occurred_at < '2026-11-22T00:00:00Z'
LIMIT 100;
~~~

Truy vấn qua nhiều ngày cần xác định trước những bucket ngày liên quan, đọc có phân trang và hợp nhất kết quả theo thời gian ở ứng dụng. Không tự giả định rằng một bảng đáp ứng được mọi loại truy vấn. Ví dụ “liệt kê cảnh báo theo tenant và độ nghiêm trọng” có thể cần bảng **alerts_by_tenant_severity_day** khác, cùng quy tắc cập nhật dữ liệu và khả năng chấp nhận độ trễ đồng bộ.

### Khi giả định về partition bị phá vỡ

Với tải trung bình một sự kiện/phút và payload 1 KiB, một thiết bị tạo khoảng **1,4 MiB payload/ngày**. Nhưng một thiết bị bị lỗi gửi **200 sự kiện/giây** sẽ tạo khoảng **16,5 GiB payload/ngày**. Đây là khác biệt rất lớn dù số thiết bị trung bình không đổi.

Vì vậy cần đo **phân phối sự kiện theo thiết bị**, không chỉ tính trung bình. Nếu có thiết bị “nóng”, thử bucket giờ, bucket ngắn hơn hoặc shard có kiểm soát. Việc thêm shard làm tăng số partition cần đọc; nó phải được đánh giá bằng thí nghiệm, không coi là phương án miễn phí.

## 3. Chọn mức nhất quán bằng hợp đồng nghiệp vụ

Trong Cassandra, **replication factor (RF)** cho biết số bản sao và **consistency level (CL)** cho biết số replica phải phản hồi thành công theo quy tắc của từng thao tác. Hai quyết định này tác động đến độ trễ, khả dụng và độ mới quan sát được.

Với RF = 3 trong **một datacenter**:

| CL | Yêu cầu phản hồi trong ví dụ | Phù hợp khi | Đổi lại |
|---|---|---|---|
| LOCAL_ONE | Một replica tại DC địa phương | Đọc dashboard chấp nhận dữ liệu có thể hơi cũ | Có thể gặp giá trị cũ hơn |
| LOCAL_QUORUM | Hai trong ba replica tại DC địa phương | Cần mức đảm bảo cao hơn cho ghi/đọc trong cùng DC | Latency và xác suất timeout có thể tăng |
| ALL | Cả ba replica | Trường hợp rất đặc biệt cần tất cả bản sao xác nhận | Một replica không đáp ứng có thể làm thao tác thất bại |

Nếu cùng DC có N = 3 replica, ghi với W = 2 và đọc với R = 2 thì **R + W > N**: các tập replica được xác nhận có ít nhất một phần tử giao nhau trong điều kiện thông thường. Đây là trực giác quan trọng khi chọn LOCAL_QUORUM cho cả đọc và ghi. Tuy nhiên nó **không biến mọi tương tác thành giao dịch tuyến tính hóa (linearizable)**: ghi đồng thời, xung đột timestamp, truyền replica và thao tác nhiều hàng vẫn cần xem xét. Với so sánh và cập nhật điều kiện, Cassandra có **lightweight transactions (LWT)** dùng cơ chế đồng thuận và chi phí khác; cần thử riêng.

Hai dạng lỗi cũng phải được phân biệt: **UNAVAILABLE** khi không đủ replica đáp ứng điều kiện CL, và **READ_TIMEOUT/WRITE_TIMEOUT** khi các replica không trả lời kịp. Số replica cần thiết, tình trạng mạng và tải quyết định xác suất gặp từng lỗi; không thể suy từ RF đơn thuần.

Một giả thuyết kiểm chứng được:

> “Ghi LOCAL_QUORUM và đọc LOCAL_QUORUM đáp ứng p99 ghi dưới 80 ms, p99 đọc dưới 150 ms ở mức đỉnh 3.000 ghi/giây; khi một node chết, tỷ lệ lỗi dưới ngưỡng SLO đã thống nhất.”

Giả thuyết phải có **ngưỡng lỗi cụ thể** được sản phẩm chấp nhận. Nếu benchmark không đạt, thay đổi CL hoặc topology cần dựa trên yêu cầu độ mới của từng đường đọc, không âm thầm hạ CL để làm biểu đồ độ trễ đẹp hơn.

## 4. Thiết kế thử nghiệm có thể bác bỏ phương án

### 4.1. Chốt giả thuyết và tiêu chí trước khi chạy

Một bảng thí nghiệm tối thiểu:

| Mã | Giả thuyết | Cách đo | Tiêu chí minh họa |
|---|---|---|---|
| H1 | Bucket ngày phù hợp truy vấn lịch sử 24 giờ | Replay các dạng truy vấn thực với phân bố thời gian | p99 đọc ≤ 150 ms ở tải mục tiêu |
| H2 | LOCAL_QUORUM đáp ứng tải ghi đỉnh | 3.000 ghi/giây và workload đọc đồng thời | p99 ghi ≤ 80 ms; tỷ lệ lỗi theo SLO đã chốt |
| H3 | Partition không phình khi tải bị lệch | Nạp cả thiết bị bình thường và thiết bị nóng | Max và p99 kích thước partition nằm trong ngân sách đo được |
| H4 | Hệ thống hồi phục sau mất một node | Dừng có kiểm soát một node ở môi trường thử | Độ trễ, lỗi, backlog và thời gian phục hồi đạt ngưỡng |
| H5 | Chính sách lưu 30 ngày vận hành được | Quan sát TTL, tombstone, compaction và repair | Dung lượng ổn định, không xuất hiện backlog kéo dài |

Ngưỡng 80/150 ms chỉ là **đề bài giả lập**. Ngưỡng kích thước partition và tỷ lệ lỗi phải lấy từ phân tích nghiệp vụ, năng lực phần cứng và phép đo ban đầu. Không có một kích thước partition “đúng” cho mọi triển khai Cassandra.

### 4.2. Cố định điều kiện để so sánh công bằng

Với từng phương án A/B/C, lưu lại:

1. Phiên bản Cassandra, Java driver, cấu hình heap/GC, số node, CPU, RAM, loại ổ đĩa, mạng, topology và RF.
2. Schema/CQL, CL đọc và ghi, chính sách retry, timeout, page size, TTL và compaction strategy.
3. Bộ dữ liệu có phân bố tenant, thiết bị nóng, payload, thời gian phát sinh và sự kiện đến muộn gần với sản phẩm.
4. Workload ghi/đọc đồng thời: tỷ lệ các loại query, mức tăng tải, thời gian chạy, số kết nối và concurrency phía Java client.
5. Thời điểm chạy, trạng thái warm-up, snapshot kết quả, cấu hình môi trường và commit của trình tạo tải.

Không so sánh A chạy trên ổ đĩa trống với B chạy khi compaction backlog lớn. Cũng không so sánh hai phương án khi một bên dùng LOCAL_ONE và bên kia dùng LOCAL_QUORUM mà không ghi rõ sự khác biệt; lúc đó đang thử **hai biến cùng lúc**.

Một kịch bản đề xuất: khởi động tải và ổn định 20 phút, chạy 60 phút ở tải mục tiêu, tăng tải đỉnh 30 phút, thử một node không sẵn sàng, sau đó theo dõi giai đoạn phục hồi. Chạy lặp nhiều lần để phân biệt hiệu ứng cấu hình với dao động ngẫu nhiên. Thời lượng thực tế phải đủ dài để nhìn thấy flush, compaction và đặc điểm của dataset; thí nghiệm một giờ **không đủ chứng minh** hành vi TTL 30 ngày.

### 4.3. Đo từ góc nhìn người dùng và từ Cassandra

| Nhóm đo | Số đo cần lưu | Vì sao cần |
|---|---|---|
| Client Java/API | Throughput, p50/p95/p99, timeout, lỗi, số lần retry | Cho biết SLO thực tế của ứng dụng |
| Truy vấn | p99 theo query shape, fan-out, số trang kết quả | Phát hiện truy vấn xấu bị che bởi trung bình |
| Phân phối khóa | Partition size p95/p99/max, top thiết bị nóng, request/key | Phát hiện hotspot |
| Node | CPU, disk I/O, dung lượng, mạng, heap, GC pause | Xác định nút nghẽn tài nguyên |
| Đường ghi/đọc | Pending tasks, dropped messages, read/write latency | Phát hiện nghẽn mà API có thể chưa bộc lộ |
| Vòng đời dữ liệu | SSTable count, tombstone, pending compactions, thời gian repair | Đánh giá tác động dài hạn của TTL và compaction |
| Lỗi node | Lỗi trong sự cố, thời gian khôi phục, backlog sau khôi phục | Kiểm tra giả thuyết chịu lỗi |

Các lệnh quan sát cơ bản trên **môi trường thử nghiệm**:

~~~bash
nodetool status
nodetool tablestats telemetry.events_by_device_day
nodetool tpstats
nodetool compactionstats
nodetool netstats
~~~

Những lệnh này không thay thế metric time series và tracing phía client. Công cụ tải cần phát đúng truy vấn thực tế qua driver (chẳng hạn chương trình Java dùng prepared statements); benchmark mặc định không có query shape của ứng dụng có thể trả lời sai câu hỏi. Lưu cả **kết quả thất bại**: mức tải khiến p99 tăng vọt thường có giá trị hơn một lần chạy thành công ở tải nhẹ.

Đối với compaction, thử riêng các ứng viên như SizeTieredCompactionStrategy, LeveledCompactionStrategy hay TimeWindowCompactionStrategy tùy đặc điểm đọc/ghi. **TWCS** thường được xem xét cho dữ liệu chuỗi thời gian chủ yếu ghi mới, TTL tương đồng và ít sửa lại; các ghi đến muộn hoặc cập nhật trộn nhiều độ tuổi trong SSTable có thể làm hiệu quả hết hạn dữ liệu kém đi. Đặt TTL và **gc_grace_seconds** cần xét repair, tombstone và nguy cơ dữ liệu đã xóa xuất hiện lại nếu replica bỏ lỡ xóa. Không rút ngắn gc_grace_seconds chỉ để giải quyết dung lượng mà chưa chứng minh quy trình repair an toàn.

## 5. Đưa chi phí vào cùng bảng với hiệu năng

Chi phí Cassandra không chỉ là tiền thuê máy. Cần xem xét **replication**, mức sử dụng đĩa an toàn, compaction, mạng giữa các node/DC, backup, monitoring, on-call, repair và công sức phát triển khi một yêu cầu nghiệp vụ phải ghi vào nhiều bảng.

### 5.1. Ước lượng dung lượng bằng đơn vị rõ ràng

Giả sử mỗi sự kiện có trung bình **1 KiB dữ liệu logic** và giữ 30 ngày:

~~~text
28.800.000 events/day * 1 KiB ≈ 27,5 GiB/day
27,5 GiB/day * 30 days ≈ 824 GiB dữ liệu logic
824 GiB * RF 3 ≈ 2,41 TiB dữ liệu đã nhân bản
~~~

Đây chỉ là **ước lượng bậc độ lớn**, chưa gồm toàn bộ overhead của hàng/cột, index, Bloom filter, memtable/SSTable, tombstone, dữ liệu chưa được compact, snapshot và backup. Nếu giả định hệ số tăng dung lượng 1,25 lần và mục tiêu chỉ dùng 60% dung lượng đĩa, tổng dung lượng đĩa phải cấp phát xấp xỉ:

~~~text
provisioned_capacity
  ≈ 2,41 TiB * 1,25 / 0,60
  ≈ 5,02 TiB
~~~

Hai hệ số **1,25 và 60% chỉ minh họa**; phải thay bằng quan sát thật và quy tắc vận hành của hệ thống. Nếu dữ liệu được nén tốt, kích thước thực có thể nhỏ hơn; nếu có nhiều tombstone/compaction hoặc lưu thêm bảng truy vấn, chi phí có thể lớn hơn.

### 5.2. Mô hình tổng chi phí sở hữu

~~~text
monthly_cost =
    node_count * node_hourly_price * hours_per_month
  + separately_billed_storage_GiB * storage_price_per_GiB_month
  + billable_network_egress_GiB * network_price_per_GiB
  + backup_and_observability_cost
  + operations_and_incident_cost
  + migration_or_development_cost_amortized
~~~

Nếu gói node đã bao gồm ổ đĩa, không tính trùng dung lượng vào dòng storage. Bổ sung chi phí theo từng DC, môi trường staging và khả năng cần thêm node để phục hồi sau sự cố. Khi so sánh A/B/C, dùng **cùng chân trời thời gian**, cùng giả định tăng trưởng và mức rủi ro; đừng chỉ so “node count hôm nay”.

Phần phải làm rõ trong ADR:

- **Chi phí trực tiếp:** số node, CPU/RAM/SSD, băng thông, backup, monitoring.
- **Chi phí theo hình dạng truy vấn:** fan-out qua nhiều bucket, số bảng nhân bản cho các cách đọc khác nhau và chi phí ghi bổ sung.
- **Chi phí vận hành:** thời gian repair, compaction backlog, thêm node, xử lý hotspot và phục hồi node.
- **Chi phí thay đổi:** backfill dữ liệu, dual-write, đối soát và rollback nếu đổi partition key sau khi chạy thật.

Một phương án chậm hơn vài mili giây nhưng rẻ và dễ vận hành hơn có thể phù hợp nếu vẫn đáp ứng SLO. Một phương án rẻ hơn nhưng không đạt tiêu chí khi một node hỏng thì không thể được coi là đạt yêu cầu chịu lỗi.

## 6. Chuyển kết quả đo thành quyết định

Sau khi thí nghiệm, đặt tất cả lựa chọn trên **cùng một bảng bằng chứng**. Ví dụ dưới đây là **số liệu giả lập chỉ để minh họa cách lập ADR, không phải benchmark Cassandra**:

| Chỉ số ở cùng workload | A — không bucket | B — bucket ngày | C — bucket giờ |
|---|---:|---:|---:|
| p99 đọc lịch sử | 220 ms | 110 ms | 98 ms |
| p99 ghi | 74 ms | 70 ms | 73 ms |
| Partition lớn nhất | 8 GiB | 72 MiB | 16 MiB |
| Dung lượng cấp phát ước tính | 4,9 TiB | 5,0 TiB | 5,4 TiB |
| Đọc lịch sử 7 ngày | 1 partition | Tối đa 7 bucket | Tối đa 168 bucket |
| Đạt SLO đọc 150 ms | Không | Có | Có |

Trong ví dụ này, B có thể là lựa chọn ban đầu hợp lý hơn A và C **nếu** thử nghiệm chịu lỗi, consistency và vận hành cũng đạt. C giảm kích thước partition thêm nhưng tăng fan-out khi đọc dài ngày. Nếu thiết bị nóng khiến partition của B vượt ngưỡng an toàn, phải thử một chính sách bucket thích ứng hoặc phương án C trước khi chấp nhận B.

**Không đánh tráo tương quan thành nguyên nhân:** nếu B tốt hơn A, cần kiểm tra xem sự khác biệt đến từ partition key hay từ cấu hình compaction, cache, dataset và trạng thái ổ đĩa đã thay đổi.

### Mẫu ADR hoàn chỉnh về cấu trúc

~~~markdown
# ADR-012: Bucket theo ngày cho lịch sử thiết bị

- Trạng thái: Proposed (chưa chấp nhận khi thiếu bằng chứng thật)
- Ngày: YYYY-MM-DD
- Chủ sở hữu: Nhóm phụ trách ingestion và query
- Bối cảnh: 20.000 thiết bị, đọc lịch sử theo thiết bị và thời gian,
  giữ 30 ngày; SLO đọc p99 <= 150 ms, ghi p99 <= 80 ms.

## Phương án
- A: Partition theo tenant + device, không bucket.
- B: Partition theo tenant + device + ngày.
- C: Partition theo tenant + device + giờ.

## Giả định cần xác minh
- Phân bố sự kiện theo thiết bị và tenant đủ ổn định.
- Tải đỉnh 3.000 ghi/giây phản ánh ít nhất mục tiêu sản phẩm.
- Truy vấn dài hơn 7 ngày hiếm hoặc có API riêng.
- TTL 30 ngày từ thời điểm ghi phù hợp với sự kiện đến muộn.

## Thử nghiệm và bằng chứng
- Link báo cáo chạy tải, cấu hình cụm và phiên bản driver.
- Bảng p95/p99/timeout, partition size, compaction và chi phí.
- Kết quả thử mất một node và giai đoạn hồi phục.
- Ghi riêng các trường hợp chưa được thử.

## Quyết định đề xuất
- Chọn B nếu tất cả tiêu chí chấp nhận đã chốt đều đạt.
- Dùng prepared statements và truy vấn theo partition key.
- Định nghĩa CL theo nghiệp vụ cho từng đường đọc/ghi.

## Hệ quả và đánh đổi
- Đọc xuyên ngày cần fan-out có giới hạn, paging và hợp nhất.
- Sự kiện đến muộn và thiết bị nóng cần chính sách riêng.
- Đổi bucket cần backfill và kế hoạch chuyển dữ liệu.

## Trigger xem xét lại
- p99 vượt SLO trong nhiều cửa sổ đo liên tiếp.
- Kích thước partition hoặc lệch tải vượt ngân sách.
- Tăng trưởng khác đáng kể giả định, thay đổi retention hay query.
- Chi phí vận hành vượt ngân sách đã ký duyệt.
~~~

Để chuyển **Proposed** thành **Accepted**, thay các dòng “link báo cáo” bằng dữ liệu có thể truy lại và ghi người phê duyệt, ngày quyết định, phiên bản cấu hình được đo. Khi quyết định bị thay thế, giữ bản ADR cũ với trạng thái **Superseded** và liên kết ADR mới; không xóa lịch sử giải thích vì sao hệ thống từng được thiết kế như vậy.

## 7. Nối quyết định kiến trúc với mã Java

Một ADR nói “truy vấn theo partition, ghi LOCAL_QUORUM và retry idempotent” phải có cách kiểm tra trong mã. Ví dụ với **DataStax/Apache Cassandra Java Driver 4.x**, chuẩn bị statement một lần và tái sử dụng:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class EventWriter {
    private final CqlSession session;
    private final PreparedStatement insert;

    public EventWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO telemetry.events_by_device_day " +
            "(tenant_id, device_id, event_day, occurred_at, event_id, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?)"
        );
    }

    public void save(
            UUID tenantId,
            UUID deviceId,
            LocalDate eventDayUtc,
            Instant occurredAt,
            UUID eventId,
            String payload) {
        // eventId, timestamp và các giá trị phải được giữ nguyên khi retry.
        BoundStatement statement = insert.bind(
            tenantId, deviceId, eventDayUtc, occurredAt, eventId, payload
        ).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
         .setIdempotent(true);

        session.execute(statement);
    }
}
~~~

**Giới hạn của ví dụ:** lớp nhận sẵn CqlSession được quản lý vòng đời ở nơi khởi tạo ứng dụng. eventId phải là UUID phù hợp cột **timeuuid**, được tạo **một lần cho mỗi sự kiện** trước khi gọi save; không tạo ID mới sau timeout. Cờ **setIdempotent(true)** chỉ đúng khi cùng sự kiện được ghi lại với **cùng primary key và cùng dữ liệu**, không có counter hoặc thao tác có tác dụng phụ không lặp an toàn. Nếu hệ thống có ghi cạnh tranh cùng khóa, timestamp, TTL hoặc quy tắc hòa giải dữ liệu phức tạp, phải phân tích lại khả năng lặp an toàn và retry policy.

Một timeout không chứng minh thao tác ghi đã thất bại ở tất cả replica: có thể replica đã ghi nhưng client chưa nhận đủ phản hồi. Vì thế, **idempotency key, xử lý duplicate và quan sát retry** là một phần của quyết định kiến trúc, không chỉ là tùy chọn cấu hình Java driver. Trong hệ thống có điều kiện “chỉ tạo một lần”, nghiên cứu LWT riêng thay vì mặc định một INSERT thông thường bảo đảm duy nhất theo nghiệp vụ.

Ngoài ra, **date bucket phải được tính thống nhất theo UTC** từ thời điểm sự kiện hoặc chính sách đã chốt; nếu một service tính theo múi giờ thiết bị và service khác tính theo UTC, cùng sự kiện có thể bị ghi và đọc ở hai partition khác nhau.

## 8. Checklist phản biện và bài tập

Trước khi chấp nhận một ADR Cassandra, tự trả lời:

- **Truy vấn:** Có liệt kê các query shape và ràng buộc partition key, clustering columns, paging, fan-out chưa?
- **Giả định:** Có ghi trung bình, p99, extreme-case và cách giả định bị vô hiệu chưa?
- **Nhất quán:** CL có khớp yêu cầu độ mới dữ liệu, lỗi node, retry và tình huống ghi đồng thời chưa?
- **Thử nghiệm:** Có dataset gần thực tế, bằng chứng nhiều lần đo, tải đỉnh, compaction, TTL và failure test chưa?
- **Chi phí:** Có RF, headroom, backup, mạng, vận hành và việc ghi vào nhiều bảng chưa?
- **Khả năng đổi quyết định:** Có trigger, người phụ trách, kế hoạch migration và rollback chưa?

**Bài tập thực hành:** Với cùng hệ thống, giả sử 1% thiết bị đột nhiên tạo 50 sự kiện/giây và màn hình phải đọc 72 giờ gần nhất. Hãy: (1) tính lại kích thước payload lớn nhất theo bucket ngày và giờ; (2) thiết kế thí nghiệm so B với C hoặc bucket có shard; (3) xác định SLO và ngân sách fan-out; (4) lập bảng chi phí cho ba mức dung lượng; (5) viết ADR **Proposed** với ít nhất ba giả định có phép đo kiểm chứng. Nếu thiếu kết quả đo, ghi rõ **“chưa có bằng chứng”** thay vì chọn phương án bằng cảm tính.

**Điểm cần nhớ:** Một thiết kế Cassandra chỉ trở thành **quyết định kiến trúc có thể bảo vệ** khi chỉ ra được truy vấn nó phục vụ, giả định nó phụ thuộc, kết quả thí nghiệm có thể lặp lại, chi phí phải trả và điều kiện khiến nhóm sẵn sàng đổi quyết định.
