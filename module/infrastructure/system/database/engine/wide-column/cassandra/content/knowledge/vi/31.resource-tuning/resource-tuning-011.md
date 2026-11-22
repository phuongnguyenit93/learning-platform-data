# Guardrail, timeout và tác động khi tăng giới hạn để né lỗi

## 1. Tình huống: tăng timeout từ 2 giây lên 20 giây có thực sự chữa được lỗi?

Một hệ thống **Apache Cassandra** lưu dữ liệu sự kiện theo thiết bị và thời gian. Bình thường, truy vấn lấy 100 sự kiện gần đây mất khoảng 30–80 ms. Sau một đợt tăng lưu lượng, p99 lên 2 giây, ứng dụng nhận timeout và một số truy vấn phát sinh cảnh báo về tombstone. Nhóm vận hành đề xuất:

- Nâng timeout đọc của Cassandra và Java Driver lên 20 giây.
- Nới ngưỡng cảnh báo/từ chối khi quét nhiều tombstone.
- Tăng page size và kích thước batch để “giảm số request”.
- Nới giới hạn kích thước partition vì dữ liệu vẫn phải giữ lâu hơn.

Những thay đổi này có thể khiến **một số lỗi không còn xuất hiện ngay**, nhưng cũng có thể làm hệ thống **giữ request chậm lâu hơn, tăng queue, tiêu thụ thêm heap, gây GC pause, tăng read/write amplification và kéo p99 của những request khác đi xuống**. Thay vì khắc phục nguyên nhân, ta có thể vô tình mở rộng vùng ảnh hưởng.

Trong chương **Tối ưu tài nguyên**, bài này làm rõ:

1. **Guardrail** là gì và khác timeout, hard limit, cảnh báo dung lượng thế nào?
2. Những timeout nào tồn tại ở client, driver, coordinator và replica? Việc tăng từng lớp có tác dụng gì?
3. Vì sao “cho phép quét nhiều hơn, đợi lâu hơn, gửi batch lớn hơn” thường làm tình hình xấu đi?
4. Cách dùng **CQL, tracing, nodetool, metrics và Java Driver 4.x** để tìm nguyên nhân trước khi chỉnh ngưỡng?
5. Khi nào điều chỉnh giới hạn có thể là hợp lý và cần kiểm chứng/rollback ra sao?

**Mục tiêu:** phân loại lỗi chính xác, giải thích được chi phí của việc nới giới hạn, đánh giá sự đánh đổi availability/latency/tài nguyên, và thiết kế một quy trình thay đổi cấu hình an toàn.

**Phạm vi phiên bản:** Apache Cassandra có nhiều loại giới hạn; hệ thống **Guardrails** được bổ sung/mở rộng qua các thế hệ Cassandra hiện đại. Danh sách guardrail, tên thuộc tính, mặc định, chính sách với superuser và cách cấu hình thay đổi theo phiên bản. Các ví dụ cấu hình trong bài là **minh họa**, không phải cấu hình production có thể sao chép nguyên xi. Luôn kiểm tra bản Cassandra/JDK/Java Driver đang chạy.

## 2. Bốn kiểu cơ chế thường bị gọi chung là “giới hạn”

| Cơ chế | Câu hỏi nó trả lời | Hành vi điển hình | Ví dụ |
| --- | --- | --- | --- |
| **Guardrail cảnh báo (warn)** | Thao tác có vượt ngưỡng rủi ro được nhận diện không? | Request có thể vẫn được chấp nhận nhưng server/driver ghi warning. | Quá nhiều tombstone trong một lần đọc, batch lớn, cấu trúc bảng vượt ngưỡng. |
| **Guardrail từ chối (fail)** | Thao tác đã vượt ngưỡng không cho phép chưa? | Server từ chối, ngắt hoặc thất bại theo điều kiện cụ thể. | Đọc vượt ngưỡng tombstone failure; dùng một tính năng bị hạn chế. |
| **Timeout/deadline** | Hệ thống còn chờ bao lâu trước khi báo request không hoàn tất đúng hạn? | Client/coordinator ngừng chờ hoặc trả lỗi timeout. | Read, write, range read, driver request timeout. |
| **Giới hạn tài nguyên/hard limit** | Nền tảng/protocol/thiết bị có thể xử lý tối đa đến đâu? | Có thể từ chối, lỗi cấp phát hoặc mất tính sẵn sàng. | Dung lượng đĩa, giới hạn message/mutation, heap, số kết nối. |

**Guardrail không phải quota tài nguyên độc lập**: nới ngưỡng fail không làm node tự có thêm RAM, IOPS hay băng thông. **Timeout không phải bộ tối ưu truy vấn**: tăng deadline cho phép chờ lâu hơn, không làm Cassandra đọc SSTable nhanh hơn. **Warning không nhất thiết đồng nghĩa request đã thất bại**.

### 2.1. Guardrail được áp dụng ở đâu?

Tùy loại và phiên bản, guardrail có thể kiểm tra **schema**, **hành động CQL**, **kích thước dữ liệu**, **đặc tính truy vấn** hoặc **khối lượng dữ liệu phải xử lý**. Một số cảnh báo chỉ xuất hiện khi flush/compaction hoặc khi read thực sự quét dữ liệu; không phải mọi guardrail đều kiểm tra ngay lúc `INSERT`.

Ví dụ về **nhóm** giới hạn/cảnh báo thường gặp:

| Nhóm | Tín hiệu cần hiểu | Nếu chỉ tăng ngưỡng |
| --- | --- | --- |
| **Tombstones scanned on read** | Query phải duyệt rất nhiều marker xóa/TTL để tìm hàng còn sống. | Mỗi request có thể quét lâu hơn, giữ CPU/I/O/memory lâu hơn và tăng tail latency. |
| **Batch size / mutation size** | Một batch/mutation quá lớn với tài nguyên hoặc semantics phù hợp. | Có thể tạo spike network/heap/commit log và ảnh hưởng replica. |
| **Partition / collection / value size** | Dữ liệu tổ chức quá lớn, nguy cơ hot partition và hoạt động bảo trì tốn kém. | Repair, streaming, compaction và read theo khoảng có thể khó hoàn tất. |
| **Schema complexity / feature restrictions** | Quá nhiều bảng/cột/index hoặc sử dụng tính năng bị hạn chế. | Tăng metadata, chi phí schema agreement hoặc query không dự đoán được. |
| **Query fan-out / paging / filtering** | Một request có thể đọc quá nhiều partition hoặc quá nhiều dữ liệu. | Tăng số task nội bộ, traffic giữa replica và memory client/server. |

**Quan trọng:** bảng trên mô tả **những loại rủi ro cần kiểm soát**, không cam kết mỗi hàng đều có cặp cấu hình `warn/fail` với đúng tên như nhau ở mọi phiên bản. Ví dụ ngưỡng tombstone có thể nằm trong phần cấu hình đọc, còn các guardrail schema khác được tổ chức riêng. Hãy dùng tài liệu/cấu hình phiên bản thật để xác định cơ chế cụ thể.

### 2.2. Quyền người dùng có thể làm kết quả kiểm tra khác nhau

Trong một số phiên bản/cấu hình, **superuser hoặc thao tác quản trị** được xử lý khác với ứng dụng thường đối với những guardrail nhất định. Vì vậy, “thử bằng tài khoản admin thấy vẫn chạy” **không chứng minh** request production sẽ được chấp nhận với role ứng dụng.

Thử nghiệm phải ghi rõ **role, keyspace, CL, phiên bản, query, loại guardrail và hành vi cảnh báo/từ chối**. Không dùng tài khoản superuser của ứng dụng như cách né guardrail.

## 3. Timeout ở nhiều tầng: ai dừng chờ trước?

Một request Cassandra đi qua ứng dụng, driver, mạng, coordinator và các replica. Mỗi tầng có thể đặt deadline/timeout khác nhau.

~~~mermaid
flowchart LR
    A["HTTP/API gateway: deadline"] --> B["Java service: thời gian còn lại"]
    B --> C["Java Driver: request timeout"]
    C --> D["Cassandra coordinator: read/write/range timeout"]
    D --> E["Replica: queue, JVM, SSTable, network"]
    E --> D
    D --> C
    C --> B
    B --> A
~~~

| Lớp | Ví dụ giới hạn | Khi hết hạn, điều gì chắc chắn? | Điều **không** chắc chắn |
| --- | --- | --- | --- |
| **API gateway** | Deadline 1 giây. | Gateway có thể đóng request và báo timeout phía HTTP. | Cassandra đã ngừng làm việc. |
| **Service/Java application** | Deadline nghiệp vụ 1,5 giây. | Ứng dụng không còn muốn chờ kết quả. | Mutation phía replica chưa được áp dụng. |
| **Java Driver 4.x** | `basic.request.timeout`, ví dụ 3 giây. | Driver báo request không hoàn tất trong deadline theo semantics driver. | Coordinator/replica đã hủy mọi công việc. |
| **Cassandra coordinator** | `read_request_timeout_in_ms`, `write_request_timeout_in_ms`, v.v. | Coordinator không nhận đủ phản hồi/kết quả trước ngưỡng phù hợp. | Mọi replica đều thất bại hoặc write đã được rollback. |
| **Replica/OS** | Thread queue, socket/network, disk I/O, JVM pause. | Có thể làm việc chậm hoặc thất bại. | Tăng timeout đủ để khắc phục thiếu tài nguyên. |

Tên tùy chọn server thường thấy gồm `read_request_timeout_in_ms`, `write_request_timeout_in_ms`, `range_request_timeout_in_ms` và các timeout riêng cho loại thao tác khác. **Không chỉnh một timeout đọc rồi giả định nó cũng điều khiển LWT, counter, range scan hoặc request phía driver**; phải kiểm tra từng loại theo phiên bản.

### 3.1. Ba cấu hình giả định cho cùng một truy vấn chậm 6 giây

| Kịch bản | Client deadline | Server read timeout | Quan sát có thể xảy ra |
| --- | ---: | ---: | --- |
| A | 2 giây | 5 giây | Client bỏ chờ trước; server có thể vẫn bận thêm và trả timeout sau. |
| B | 10 giây | 5 giây | Client chờ lâu hơn nhưng coordinator vẫn có thể báo read timeout khoảng ngưỡng server. |
| C | 10 giây | 15 giây | Request có thể hoàn tất sau 6 giây **nếu đủ replica và tài nguyên**, nhưng giữ slot/tài nguyên lâu hơn. |

Đây là ví dụ ý nghĩa deadline, **không phải timeline chính xác cho mọi request**: thời điểm bắt đầu đo, retry/speculative execution, queue và network khác nhau. Nếu gateway có deadline 1 giây, cả ba kịch bản đều có thể vô ích với người gọi API.

### 3.2. Timeout khác hủy bỏ giao dịch

**Write timeout không chứng minh write chưa được áp dụng.** Với RF = 3, write `LOCAL_QUORUM` cần hai ACK ở local DC. Nếu một replica áp dụng mutation nhưng ACK thứ hai chậm, client có thể nhận `WriteTimeout` dù một phần dữ liệu đã được ghi.

Vì Cassandra thường hòa giải mutation theo timestamp, retry thiếu kiểm soát có thể gây **ghi đè**, đặc biệt với read-modify-write, counter hoặc LWT. Cần dùng key/event ID ổn định, hiểu semantics idempotency và reconciliation trước khi tự động retry.

**Read timeout** cũng không có nghĩa “không có hàng”; nó là **không hoàn tất request đúng hạn**. Không thay lỗi bằng kết quả rỗng trong tầng ứng dụng.

## 4. Phân loại lỗi trước khi sửa một tham số nào

Các exception và cảnh báo trông giống “Cassandra không trả lời” nhưng nguyên nhân và hướng xử lý khác nhau.

| Dấu hiệu | Ý nghĩa khái quát | Không nên làm | Nên kiểm tra |
| --- | --- | --- | --- |
| **`Unavailable`** | Không đủ replica được xem là khả dụng cho CL tại thời điểm coordinator đánh giá. | Chỉ tăng timeout. | RF/CL, DC, trạng thái node, gossip/network, replica placement. |
| **`ReadTimeout`** | Không có đủ phản hồi/dữ liệu đọc phù hợp trước timeout server. | Tăng vô hạn thời gian chờ. | Replica chậm, tombstone scan, SSTable/disk, GC, queue, CL. |
| **`WriteTimeout`** | Không có đủ xác nhận write trong thời gian chờ server. | Giả định write đã rollback và retry bằng ID mới. | ACK count, replica health, commit log/flush, network, retry idempotency. |
| **`ReadFailure` / `WriteFailure`** | Replica báo lỗi khi xử lý request. | Coi là timeout đơn thuần. | Disk errors, memory, tombstone failure và logs của replica. |
| **Driver request timeout** | Driver chưa nhận kết quả kịp deadline của mình. | Chỉ tăng server timeout. | Gateway deadline, driver time budget, coordinator, retry, network. |
| **Guardrail warning** | Vượt ngưỡng cảnh báo; request có thể thành công. | Tắt mọi warning để dashboard xanh. | Query/schema/row size/batch/tombstone và xu hướng. |
| **Guardrail reject hoặc query validation error** | Vi phạm một hạn chế hoặc ngưỡng fail. | Chỉ tăng ngưỡng mà không phân tích độ lớn request. | Loại guardrail/giới hạn, version, nguồn request, chi phí. |
| **Overloaded / busy / dropped messages** | Không tiếp nhận/xử lý đủ công việc trong áp lực tài nguyên. | Tăng concurrency cùng lúc tăng timeout. | Thread pools, backpressure, p99, I/O, GC, traffic. |

Tên exception và mã lỗi cụ thể có thể khác theo phiên bản protocol/driver và đường lỗi. **Lấy thông điệp đầy đủ, consistency level, keyspace/table, query template, coordinator, thời gian và trace ID nếu có**, nhưng tránh log dữ liệu nhạy cảm hoặc toàn bộ partition key người dùng.

### Một ví dụ tính CL

Với `NetworkTopologyStrategy`, RF = 3 ở `dc1`, `LOCAL_QUORUM` cần **2/3 replica tại dc1**. Khi chỉ có một replica của partition khả dụng, có thể nhận `Unavailable`; tăng read timeout từ 5 lên 30 giây không tạo thêm replica.

Nếu cả ba replica có mặt nhưng một số trả lời chậm do GC/disk/tombstone, tăng timeout **có thể** giúp một vài read hoàn tất, nhưng khả năng chịu tải phải được tính lại. Đây là hai tình huống khác nhau, cần hai quyết định khác nhau.

## 5. Vì sao tăng timeout có thể tạo vòng xoáy nghẽn?

Giả sử ứng dụng gửi **250 request/giây** ổn định, mỗi request giữ tài nguyên tới khi trả lời. Theo **định luật Little** ở trạng thái tương đối ổn định:

~~~text
L ≈ λ × W

L: số request đang nằm trong hệ thống
λ: thông lượng hoàn tất/giây
W: thời gian trung bình một request tồn tại trong hệ thống (giây)

Nếu W = 0,2 giây:  L ≈ 250 × 0,2 = 50 request đồng thời
Nếu W = 4 giây:    L ≈ 250 × 4   = 1.000 request đồng thời
~~~

Đây là **minh họa sizing**, không phải số liệu đo thực của cluster. Khi tải vượt capacity, hệ thống có thể không còn ở trạng thái ổn định, thông lượng hoàn tất giảm và backlog phình không giới hạn. Công thức giúp thấy: **request sống lâu hơn có thể làm số request tồn đọng tăng mạnh**.

~~~mermaid
flowchart TD
    A["Query/replica chậm vì disk, GC hoặc scan"] --> B["Tăng timeout để request sống lâu hơn"]
    B --> C["In-flight requests và queue có thể tăng"]
    C --> D["Heap, CPU, I/O, network và GC pressure tăng"]
    D --> E["p99 và số timeout có thể tăng tiếp"]
    E --> F["Client retry / traffic khuếch đại"]
    F --> C
~~~

**Các hệ quả cụ thể:**

1. **Nhiều request giữ tài nguyên lâu hơn.** Coordinator/replica có thể giữ dữ liệu, buffers, task và kết nối lâu hơn.
2. **Queueing delay lan sang request khỏe.** Một request ngắn đến sau cũng phải xếp hàng với workload đang chậm.
3. **Retry storm:** client timeout rồi retry trong khi request cũ có thể vẫn chạy, làm tải thực cao hơn traffic người dùng.
4. **Tail latency tăng:** một vài request rất chậm kéo p99/p99.9; không cần CPU trung bình đạt 100%.
5. **Áp lực ổ đĩa/bộ nhớ tăng:** tombstone scan, đọc SSTable hoặc compaction chồng tải khiến GC/disk latency xấu đi.
6. **Che khuất nguyên nhân:** tỷ lệ lỗi nhìn giảm trong ngắn hạn nhưng request latency vượt SLO nghiệp vụ.

### Timeout dài hơn đôi khi có ích, nhưng phải có điều kiện

Ví dụ một **batch job ít ưu tiên**, chạy ngoài giờ cao điểm, có deadline 120 giây và traffic được giới hạn có thể chấp nhận một timeout lớn hơn so với API tương tác cần phản hồi dưới 200 ms. Khi đó:

- Dùng **execution profile**/cấu hình riêng cho batch job, không tăng timeout toàn bộ ứng dụng.
- Giới hạn **concurrency, page size, rate** và tổng thời gian chạy.
- Đo throughput, request in-flight, p99 của API chính và chi phí trên replica.
- Chứng minh workload **có khả năng hoàn tất** thay vì chỉ chờ lâu hơn để thất bại.

Không có giá trị timeout “càng cao càng an toàn” dùng chung cho mọi nghiệp vụ.

## 6. Guardrail tombstone: tăng failure threshold không làm query rẻ hơn

### 6.1. Vì sao một SELECT ít hàng vẫn đọc nhiều tombstone?

Trong Cassandra, `DELETE` và TTL hết hạn tạo thông tin xóa (*tombstone*) để che phiên bản cũ trên các replica/SSTable. Một truy vấn có `LIMIT 10` cần tìm **10 hàng còn sống**, chứ không nhất thiết chỉ xử lý mười entry vật lý.

~~~text
Partition theo thời gian:
  9.900 hàng đã xóa/hết TTL  +  100 hàng còn sống

SELECT ... LIMIT 10
  → có thể phải duyệt hàng nghìn tombstone trước khi tìm đủ 10 hàng sống,
    tùy thứ tự clustering, SSTable và dữ liệu cụ thể.
~~~

Nếu truy vấn vượt một ngưỡng cảnh báo, server có thể phát warning. Nếu vượt **ngưỡng từ chối quét tombstone** phù hợp, truy vấn có thể thất bại để tránh tiếp tục tiêu tốn tài nguyên. Một số cấu hình có tên lịch sử như `tombstone_warn_threshold` và `tombstone_failure_threshold`; **kiểm tra tên, phạm vi và mặc định theo phiên bản**, thay vì mặc định đây là cặp guardrail giống nhau cho mọi bản.

### 6.2. Tăng ngưỡng từ chối có thể đổi lỗi nhanh thành chờ lâu

Giả sử trước đây một read bị dừng sau khi quét tới giới hạn. Nếu nâng giới hạn lên gấp 10:

- Read có thể phải xử lý **nhiều marker hơn**, tạo nhiều thao tác hợp nhất dữ liệu/SSTable.
- Một vài request có thể trả được kết quả, nhưng các request khác có thể **timeout hoặc gây áp lực heap/GC**.
- Query không có partition key đúng có thể làm ảnh hưởng **nhiều replica** thay vì một partition.
- Thời gian scan dài có thể làm read latency và concurrency tăng, đặc biệt nếu client còn retry.

**Giải pháp bền vững:** thiết kế partition theo truy vấn, **time bucketing**, giới hạn clustering range, tránh xóa từng hàng hàng loạt khi có phương án vòng đời dữ liệu tốt hơn, dùng TTL/TWCS khi phù hợp và duy trì lịch compaction/repair lành mạnh. Không hạ `gc_grace_seconds` tùy tiện để né tombstone: replica bỏ lỡ tombstone có thể gây **zombie data** nếu thông tin xóa bị purge quá sớm.

### 6.3. Phân biệt cảnh báo tombstone với tiến trình purge

| Việc | Tác động |
| --- | --- |
| Nâng tombstone warning threshold | Có thể làm **ít cảnh báo hơn**, không dọn tombstone. |
| Nâng tombstone failure threshold | Cho phép một số read tiếp tục quét hơn trước, **không giảm công việc đọc**. |
| Tăng read timeout | Cho phép chờ lâu hơn, không quyết định tombstone nào được purge. |
| Compaction đủ điều kiện | Có thể hợp nhất SSTable và purge tombstone an toàn theo các điều kiện. |
| Anti-entropy repair | Đồng bộ khác biệt giữa replica, đặc biệt quan trọng trước khi purge delete cũ. |
| Thiết kế lại partition/TTL | Giảm số tombstone một request phải quét và giảm read amplification lâu dài. |

## 7. Các “cách né lỗi” khác cũng có giá

### 7.1. Tăng batch size không biến batch thành bulk loader

Một **CQL batch** không giống cơ chế bulk ingest miễn phí. Batch nhiều partition có thể tăng coordination, lưu dữ liệu batch log khi dùng logged batch, gây burst tại các replica và tăng memory/network/commit log I/O.

~~~sql
-- Minh họa ANTI-PATTERN: gom thao tác trên nhiều partition không liên quan
-- chỉ vì muốn tiết kiệm một lượt gọi mạng.
BEGIN BATCH
  INSERT INTO telemetry_limits.events_by_device_day
    (device_id, event_day, event_time, event_id, payload)
  VALUES ('device-A', '2026-11-21', '2026-11-21T10:00:00Z',
          123e4567-e89b-42d3-a456-426614174001, 'A');
  INSERT INTO telemetry_limits.events_by_device_day
    (device_id, event_day, event_time, event_id, payload)
  VALUES ('device-B', '2026-11-21', '2026-11-21T10:00:00Z',
          123e4567-e89b-42d3-a456-426614174002, 'B');
APPLY BATCH;
~~~

**Không chạy batch mẫu này như tối ưu hóa production.** Trong nhiều trường hợp, nhiều prepared statements **bất đồng bộ với concurrency hữu hạn**, hoặc batch nhỏ gắn chặt cùng partition khi thật sự cần semantics của batch, là lựa chọn tốt hơn. Logged batch mang tính **atomicity theo semantics của Cassandra**, không biến nhiều partition thành giao dịch có isolation đầy đủ.

Thấy cảnh báo `batch_size_warn_threshold_in_kb` hoặc giới hạn kích thước tương ứng không có nghĩa giải pháp là tăng ngưỡng. Hãy đo **số partition/batch, batch bytes, tốc độ gửi và chi phí coordinator**. Đừng tăng batch size để che poor data modeling.

### 7.2. Tăng page size có thể làm chậm và tốn memory hơn

`LIMIT` trong CQL giới hạn số hàng trả về của statement; **page size** của driver điều khiển kích thước page khi fetch. Page size 10.000 không khiến đọc 10.000 hàng trở nên miễn phí; nó làm **một response chứa nhiều dữ liệu hơn**, có thể tăng allocation, decode time, network và GC.

Khi một page bị timeout, giảm page size có thể giúp chia công việc thành các phần nhỏ hơn; nhưng nhiều page hơn cũng tăng số lượt request. Phải benchmark dựa trên kích thước **byte** mỗi hàng, không chỉ đếm rows.

### 7.3. Tăng giới hạn partition/value/collection che thiết kế dữ liệu

**Partition lớn** là rủi ro đặc biệt với wide-column Cassandra: cùng một partition key tạo một nhóm replica và một số thao tác đọc/repair/streaming phải xử lý nhiều dữ liệu. Nếu nới ngưỡng kích thước để cho phép một partition tăng từ vài trăm MB lên nhiều GB mà không thay mô hình:

- Hot partition có thể làm một nhóm replica bị dồn tải dù cluster có nhiều node.
- Read theo khoảng và scan tombstone khó dự đoán chi phí.
- Compaction/repair/streaming trên vùng dữ liệu có thể mất nhiều thời gian hơn.
- Mất cân bằng dữ liệu không được sửa chỉ bằng tăng RF hoặc node count.

Các biện pháp thay thế gồm **bucket theo giờ/ngày**, bổ sung shard có kiểm soát khi write quá nóng, tách payload lớn khỏi bảng phục vụ danh sách và tạo projection theo truy vấn. Mỗi phương án cần đánh giá fan-out, vì bucket quá nhỏ cũng có thể tạo nhiều partition/request.

### 7.4. Cho phép filtering rộng không phải tối ưu hóa

`ALLOW FILTERING` có thể cho phép một số truy vấn mà Cassandra thường từ chối vì không có đường truy cập phù hợp. Nó **không tạo index** và có thể khiến truy vấn phải quét phần lớn dữ liệu để lọc vài hàng. Nếu giới hạn/tối ưu bị bỏ qua, lỗi nhanh có thể chuyển thành **range scan chậm** trên nhiều replica.

Trước khi dùng filtering, xác định **pattern truy vấn thực tế**, partition key bắt buộc, clustering range và nhu cầu projection/index thích hợp theo phiên bản.

## 8. Thời gian chờ, quorum và tác động lên replica

### 8.1. RF và CL không đổi khi tăng timeout

Với keyspace `NetworkTopologyStrategy` có `dc1: 3`, request `LOCAL_QUORUM` cần **hai phản hồi trong dc1**. Tăng timeout từ 5 lên 30 giây **không** biến quorum thành một replica; nó chỉ thay thời gian coordinator/driver có thể chờ đủ điều kiện.

~~~mermaid
sequenceDiagram
    participant A as Java client
    participant C as Coordinator
    participant R1 as Replica N1
    participant R2 as Replica N2
    participant R3 as Replica N3
    A->>C: SELECT LOCAL_QUORUM
    C->>R1: Read
    C->>R2: Read
    C->>R3: Có thể liên hệ theo read plan
    R1-->>C: Phản hồi nhanh
    Note over R2: GC/disk làm chậm
    Note over R3: Có thể không nằm trong số đủ điều kiện đúng hạn
    C-->>A: Timeout nếu chưa đủ phản hồi khi hết hạn
    Note over A,C: Tăng timeout chỉ giúp chờ lâu hơn
~~~

Sơ đồ là minh họa: Cassandra có thể chọn replica/digest, gửi speculative reads hoặc thực hiện read repair tùy phiên bản/trạng thái. Không mặc định mọi read gửi dữ liệu tới cả ba replica, cũng không khẳng định một replica chậm luôn làm `LOCAL_QUORUM` timeout.

### 8.2. Khi một DC đang mất kết nối

Với `dc1:3`, `dc2:3`, write `LOCAL_QUORUM` từ `dc1` không cần chờ quorum `dc2`, trong khi `EACH_QUORUM` write yêu cầu quorum **mỗi DC**. Nếu mất liên kết liên DC:

- Tăng `EACH_QUORUM` write timeout **không thể tạo ra ACK từ DC đang mất hoàn toàn**.
- Hạ CL có thể tăng availability nhưng thay đổi **cam kết nhất quán/độ bền liên DC**; không phải sửa lỗi miễn phí.
- Replica remote có thể bỏ lỡ mutation/tombstone; cần giám sát hints/repair và quy trình khôi phục.

Không điều chỉnh CL/timeout như một tổ hợp mù khi chưa xác định **mục tiêu RPO/RTO, tính sẵn sàng và mức nhất quán** của nghiệp vụ.

## 9. Hướng sửa gốc: bớt việc mỗi request thay vì cho phép request làm nhiều hơn

| Triệu chứng | Thay đổi “né lỗi” hấp dẫn | Thay đổi nên khảo sát trước |
| --- | --- | --- |
| Tombstone read warning/failure | Nâng ngưỡng quét tombstone. | Thu hẹp partition/range, time bucket, TTL/TWCS hợp lý, kiểm soát delete và repair. |
| Read timeout một partition rất lớn | Tăng read timeout và `LIMIT`. | Sửa primary key/bucket, tránh hot partition, chỉ lấy cột cần thiết, kiểm soát paging. |
| Range scan timeout | Nâng `range_request_timeout_in_ms`. | Truy vấn bằng partition key, bảng projection/rollup, chia workload offline. |
| Batch warnings | Tăng batch warn/fail threshold. | Prepared async writes có giới hạn concurrency; tối giản batch nhiều partition. |
| Driver timeout tăng đồng loạt | Tăng `basic.request.timeout` mọi request. | Kiểm tra coordinator/replica, disk, GC, queue, network, retry storm và request deadline. |
| Hết disk/compaction backlog | Tăng timeout để chờ compaction xong. | Tăng capacity/headroom, xử lý snapshot/compaction theo runbook, giảm write burst. |
| Quorum unavailable | Tăng timeout. | Khôi phục replica/DC/network, kiểm tra RF/CL/placement. |
| Truy vấn dữ liệu lịch sử quá rộng | Tăng page size + timeout. | Rollup theo ngày/tuần, time window, API cursor và batch analytics riêng. |

### 9.1. Rate limiting và backpressure

Nếu Cassandra chỉ chịu được tốc độ xử lý ổn định `μ` mà ứng dụng tiếp tục gửi ở tốc độ `λ > μ`, **queue sẽ tăng**. Tăng timeout chỉ cho hàng đợi thêm thời gian phình to.

Giải pháp thường là:

1. **Rate limit** phía producer/gateway theo tenant hoặc query type.
2. **Bounded concurrency** ở Java service thay vì tạo hàng nghìn futures không giới hạn.
3. **Queue size hữu hạn** và cơ chế trả lỗi/backpressure có chủ đích khi quá tải.
4. **Retry có exponential backoff và jitter**, retry budget và idempotency; không retry đồng loạt mọi timeout.
5. Tách **traffic tương tác** với **backfill/batch analytics** bằng execution profile, thời gian chạy hoặc hệ thống xử lý riêng.

Tăng số thread/connection không nhất thiết tăng throughput nếu nút nghẽn là disk IOPS, SSTable scan hoặc replica placement.

### 9.2. Tránh chữa symptom bằng thao tác bảo trì nguy hiểm

- `nodetool compact` hoặc ép major compaction không phải nút “xóa tombstone ngay”: có thể cần disk tạm lớn và tranh I/O với read/write.
- `gc_grace_seconds` không phải ngưỡng timeout; giảm quá mức mà repair chưa đủ có nguy cơ **zombie data**.
- Xóa thủ công commit log, hints, SSTable hoặc snapshot để giảm disk không phải cách giải quyết read timeout; có thể làm mất dữ liệu hoặc điểm phục hồi.
- Tăng RF cũng tăng write/repair/storage cost và **không tự sửa** partition key kém.

## 10. CQL lab: truy vấn tốt, truy vấn nguy cơ và quan sát cảnh báo

### 10.1. Chuẩn bị schema theo bucket

Ví dụ lab có ít nhất ba full replica trong DC tên `dc1`. Nếu môi trường không có topology này, hãy điều chỉnh RF/CL phù hợp trước khi chạy.

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_limits
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_limits.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  payload text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

**Phân tích:** `(device_id, event_day)` là partition key kép; `event_time`, `event_id` xác định clustering order. Thiết kế này cho phép query theo thiết bị/ngày/đoạn thời gian thay vì gom nhiều năm vào một partition.

### 10.2. Ghi hai hàng và tạo một tombstone

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_limits.events_by_device_day
  (device_id, event_day, event_time, event_id, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:00:00Z',
   123e4567-e89b-42d3-a456-426614174001, 'temperature:20.5');

INSERT INTO telemetry_limits.events_by_device_day
  (device_id, event_day, event_time, event_id, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:01:00Z',
   123e4567-e89b-42d3-a456-426614174002, 'temperature:20.6');

DELETE FROM telemetry_limits.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time = '2026-11-21T09:00:00Z'
  AND event_id = 123e4567-e89b-42d3-a456-426614174001;
~~~

Sau `DELETE`, ứng dụng thường không còn thấy hàng 09:00, nhưng thông tin xóa vẫn có thể tồn tại trên đĩa. Hai hàng và một tombstone **không đủ** để kích hoạt guardrail tombstone trên phần lớn cấu hình; bài lab này minh họa semantics, **không cố tạo hàng triệu tombstone để vượt ngưỡng**.

### 10.3. Truy vấn tốt với đủ partition key

~~~sql
TRACING ON;

SELECT event_time, event_id, payload
FROM telemetry_limits.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time < '2026-11-21T10:00:00Z'
LIMIT 100;

TRACING OFF;
~~~

Mục đích tracing: xem coordinator/replica và hoạt động xử lý của **một truy vấn cụ thể**. Nếu xuất hiện warning, cần lưu **thông điệp nguyên văn, thời gian, query shape và node liên quan**. Một trace thành công chưa chứng minh hệ thống không có tombstone debt ở các partition khác.

### 10.4. Ví dụ phản mẫu: đọc không có partition key

~~~sql
-- PHẢN MẪU: không chạy trên cluster dữ liệu lớn.
-- Thiếu device_id và event_day; đây không phải partition lookup.
SELECT event_time, payload
FROM telemetry_limits.events_by_device_day
WHERE event_time >= '2026-11-21T09:00:00Z'
ALLOW FILTERING;
~~~

Tùy phiên bản và execution plan, truy vấn có thể bị từ chối hoặc dẫn tới scan tốn kém. Nếu nhận lỗi “cannot execute this query ... ALLOW FILTERING”, việc thêm `ALLOW FILTERING` không biến nó thành đường đọc hiệu quả. Sửa bằng **mô hình bảng theo truy vấn** hoặc hệ thống analytics phù hợp.

### 10.5. Quan sát qua nodetool

~~~bash
nodetool status
nodetool tpstats
nodetool tablestats telemetry_limits.events_by_device_day
nodetool tablehistograms telemetry_limits events_by_device_day
nodetool proxyhistograms
nodetool compactionstats
nodetool gcstats
nodetool netstats
~~~

| Lệnh | Dữ liệu cần xem | Câu hỏi |
| --- | --- | --- |
| `status` | Node/DC/rack Up/Down/Joining. | Timeout có do replica không sẵn sàng? |
| `tpstats` | Pending/blocked/dropped tasks theo pool. | Có backlog và overload không? |
| `tablestats` | Dung lượng, SSTable count, tombstone/partition thống kê theo phiên bản. | Partition/read amplification có bất thường? |
| `tablehistograms` | Phân phối kích thước/độ trễ cấp bảng. | Có hot/large partition hoặc tail latency? |
| `proxyhistograms` | Latency ở phía coordinator theo semantics công cụ. | Client p99 khác server latency thế nào? |
| `compactionstats` | Compaction đang chạy và pending. | Disk có bận với SSTable maintenance? |
| `gcstats` | GC activity theo node. | GC pause có trùng spike không? |
| `netstats` | Streaming/handoff tình huống phù hợp. | Replica đang truyền dữ liệu nhiều? |

Số liệu `nodetool` có thể là counter tích lũy, histogram, cửa sổ thời gian hoặc snapshot thời điểm lấy. **Không so hai con số khác đơn vị/cửa sổ rồi kết luận**. Kiểm tra `nodetool help` khi cú pháp/đầu ra khác phiên bản.

## 11. Java Driver 4.x: deadline rõ ràng, page size hữu hạn, không retry mù

Ví dụ cấu hình **request timeout ở tầng driver**, chọn `LOCAL_QUORUM` và giới hạn page size. Đo thời gian từ client bằng đồng hồ monotonic; ghi lỗi loại nào thay vì bắt mọi exception rồi trả dữ liệu rỗng.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.util.concurrent.TimeUnit;

public final class BoundedCassandraRead {
    public static void main(String[] args) {
        DriverConfigLoader loader = DriverConfigLoader.programmaticBuilder()
            .withDuration(DefaultDriverOption.REQUEST_TIMEOUT,
                          Duration.ofSeconds(3))
            .build();

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .withConfigLoader(loader)
                .build()) {

            PreparedStatement prepared = session.prepare(
                "SELECT event_time, event_id, payload " +
                "FROM telemetry_limits.events_by_device_day " +
                "WHERE device_id = ? AND event_day = ? " +
                "AND event_time >= ? AND event_time < ? LIMIT 100");

            BoundStatement read = prepared.bind(
                    "device-7",
                    LocalDate.of(2026, 11, 21),
                    Instant.parse("2026-11-21T09:00:00Z"),
                    Instant.parse("2026-11-21T10:00:00Z"))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setPageSize(100);

            long started = System.nanoTime();
            try {
                ResultSet result = session.execute(read);
                ExecutionInfo info = result.getExecutionInfo();

                // Server warnings có thể xuất hiện trong metadata của
                // execution, tùy đường request/phiên bản.
                for (String warning : info.getWarnings()) {
                    System.err.println("Cassandra warning: " + warning);
                }

                int count = 0;
                for (Row row : result) {
                    count++;
                }
                long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started);
                System.out.println("query=read_recent_events"
                    + " cl=LOCAL_QUORUM"
                    + " ok=true rows=" + count
                    + " elapsed_ms=" + elapsedMs);
            } catch (RuntimeException error) {
                long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started);
                System.err.println("query=read_recent_events"
                    + " cl=LOCAL_QUORUM ok=false"
                    + " elapsed_ms=" + elapsedMs
                    + " exception=" + error.getClass().getSimpleName());
                throw error;
            }
        }
    }
}
~~~

**Điểm chính:**

1. `DefaultDriverOption.REQUEST_TIMEOUT` đặt timeout **tầng driver**; không sửa `read_request_timeout_in_ms` của Cassandra. Cấu hình HOCON tương ứng thường nằm dưới `datastax-java-driver.basic.request.timeout`; kiểm tra version driver.
2. `setPageSize(100)` giới hạn page ở tầng driver, khác `LIMIT 100` của CQL. Bảng này đã `LIMIT 100` nên số hàng logic tối đa 100, nhưng đọc tombstone có thể tốn nhiều công việc hơn.
3. `LOCAL_QUORUM` xác định số phản hồi replica, không điều khiển deadline. Với RF = 3 ở `dc1` cần hai replica trả lời.
4. `ExecutionInfo.getWarnings()` hỗ trợ quan sát warning khi server gửi metadata phù hợp; không thể dựa duy nhất vào nó để biết **mọi guardrail trên cluster**.
5. `System.nanoTime()` đo duration; không phải timestamp UTC. Trong production, thêm UTC wall-clock, query name, DC/coordinator nếu có, và correlation ID với cardinality/PII được kiểm soát.
6. Việc lặp toàn bộ `ResultSet` có thể tải nhiều page ở query lớn. **Một driver request timeout không phải deadline tổng của toàn bộ API gồm nhiều statement/page**; API cần deadline/budget độc lập.
7. Code cố ý **không tự retry mọi lỗi**. Với write hoặc multi-step workflow, timeout có thể là trạng thái chưa biết; retry budget và idempotency phải được thiết kế trước.

### 11.1. Chọn timeout theo loại workload

| Loại traffic | Nguyên tắc |
| --- | --- |
| Read API tương tác | Deadline nhỏ hơn SLO có tính network/serialization; query cần partition key và kích thước dự đoán được. |
| Ghi sự kiện thời gian thực | Deadline và retry budget thống nhất với ACK/CL/idempotency; tránh tạo duplicate khi timeout. |
| Backfill/batch analytics | Có thể cho phép thời gian dài hơn nhưng **concurrency/rate/budget riêng**. |
| Repair/streaming/maintenance | Dùng công cụ và quy trình quản trị phù hợp, không lấy timeout một CQL request làm giới hạn toàn tác vụ. |

Không chọn giá trị tuyệt đối chỉ dựa trên ví dụ `3 seconds`; phải đo **p95/p99, queue time, throughput, rủi ro retry và SLO người dùng**.

## 12. Dashboard: cần chứng minh “đợi lâu hơn” có lợi hay không

### 12.1. Tối thiểu phải đặt những đồ thị này cùng timeline

| Nhóm | Chỉ số nên có | Câu hỏi |
| --- | --- | --- |
| **Client** | p50/p95/p99, request rate, timeout/error rate, retries, in-flight. | Người dùng có thực sự nhanh và ít lỗi hơn? |
| **Coordinator** | Read/write/range latency, read/write timeout, unavailable, speculative retries. | Lỗi phát sinh trước hay sau khi coordinator nhận đủ replica? |
| **Replica** | Pending/blocked/dropped tasks, per-node read latency, SSTable/tombstone stats. | Có node nào bị hot hoặc backlog lớn không? |
| **JVM** | Heap after GC, allocation rate, STW pause duration, CPU/thread pressure. | Timeout dài khiến memory/GC xấu đi? |
| **Disk** | Await/IOPS, free space, compaction/flush backlog, active SSTables. | Query chậm vì storage hay tài nguyên đang bị compaction chiếm? |
| **Network/topology** | Node up/down, DC/rack, retransmits, streaming/hints/repair status. | Có replica thiếu phản hồi vì lỗi kết nối? |
| **Guardrail** | Warning/reject count theo loại/query nếu metric/log hỗ trợ. | Loại workload nào vượt ngưỡng và xu hướng ra sao? |

**Quan sát p99 theo query shape**, không chỉ trung bình cả dịch vụ. Một vài query scan toàn lịch sử có thể làm phần còn lại bị ảnh hưởng; nếu chỉ nhìn tỉ lệ error tổng, ta sẽ không nhận ra.

### 12.2. Một bảng đánh giá thay đổi giả định

Giả sử nhóm thử tăng timeout cho **riêng một loại batch read** trên staging, không đổi RF/CL:

| Metric | Trước | Sau | Diễn giải |
| --- | ---: | ---: | --- |
| Request success rate | 97% | 99% | Có cải thiện tỷ lệ hoàn tất. |
| p99 latency batch read | 2,0 s | 12,0 s | Batch chờ lâu hơn; cần kiểm tra SLA của batch. |
| In-flight requests | 180 | 950 | Tăng concurrency tồn đọng. |
| p99 của API tương tác | 90 ms | 450 ms | **Hồi quy nghiêm trọng** nếu dùng chung replica/tài nguyên. |
| GC pause p99 | 45 ms | 250 ms | Có dấu hiệu áp lực JVM tăng; cần điều tra. |
| Pending compactions | 12 | 45 | Có thể backlog tăng; phải kiểm tra traffic/đĩa trước khi kết luận nguyên nhân. |

Đây là **dữ liệu giả lập**. Dù success rate batch có vẻ tăng, thay đổi có thể **không đạt điều kiện chấp nhận** vì làm API chính chậm đi. Nhiều lỗi cần được giải quyết bằng giảm chi phí read/giới hạn rate, không chỉ bằng timeout.

### 12.3. Quy tắc diễn giải cảnh báo

- **Không có warning** sau khi nới ngưỡng không nghĩa hệ thống khỏe hơn.
- Warning tăng có thể do **nhiều request hơn** chứ không nhất thiết từng request xấu hơn; cần chuẩn hóa **per 1.000 requests** và theo query type.
- Tỷ lệ timeout giảm cần xem cùng p99, throughput và **retry rate** để tránh đếm nhầm các request đã chậm nhưng không còn bị cắt sớm.
- Metrics theo node/DC giúp thấy thay đổi làm nghẽn một replica thay vì toàn cluster.
- Tương quan thời gian chưa đủ để khẳng định một tham số là nguyên nhân; ghi lại deploy/repair/compaction/traffic và dùng benchmark có kiểm soát.

## 13. Quy trình quyết định trước khi nới guardrail hoặc timeout

~~~mermaid
flowchart TD
    A["Có warning/reject/timeout"] --> B["Phân loại chính xác lỗi và phạm vi"]
    B --> C{"Unavailable hoặc node/DC lỗi?"}
    C -->|Có| D["Khôi phục replica/network; kiểm tra RF và CL"]
    C -->|Không| E["Lấy metrics + logs + tracing mẫu"]
    E --> F{"Query/model dữ liệu gây scan/batch/partition lớn?"}
    F -->|Có| G["Tối ưu schema/query, bucket, pagination, rate limit"]
    F -->|Không| H["Đo GC, disk, compaction, pool, network"]
    G --> I["Benchmark trên staging với workload gần thật"]
    H --> I
    I --> J{"Đã chứng minh workload hợp lệ cần thêm budget?"}
    J -->|Không| K["Giữ guardrail; sửa gốc / scale hợp lý"]
    J -->|Có| L["Nới hẹp phạm vi, giới hạn concurrency và thời gian"]
    L --> M["Canary; theo dõi p99, throughput, in-flight, GC, disk"]
    M --> N{"SLO và resource budgets đều đạt?"}
    N -->|Không| O["Rollback theo kế hoạch"]
    N -->|Có| P["Ghi runbook, version, lý do và mốc review"]
~~~

### Checklist thay đổi an toàn

1. **Ghi rõ loại lỗi:** warning, guardrail fail, driver timeout, read/write timeout, unavailable, overload, validation.
2. **Đo quy mô và xu hướng:** query name, CL, RF, DC, partition size, tombstones scanned, batch bytes, p99 và request rate.
3. **Xác định tại sao cần nới:** có phải một workload hợp lệ, có hạn và có SLA cho phép chờ lâu không?
4. **Chứng minh phương án sửa gốc đã được đánh giá:** partition design, time bucket, bounded pagination, async writes/rate, capacity, repair.
5. **Kiểm tra phiên bản:** tên cấu hình, phạm vi, role exemptions, cần restart/reload hay có thể thay đổi động; tránh áp hướng dẫn phiên bản khác.
6. **Phân biệt client và server:** nếu nới chỉ một lớp, deadline còn lại có cho phép tác dụng không? Gateway có chờ đủ lâu không?
7. **Đặt giới hạn kèm theo:** concurrency, queue length, rate limit, byte budget, retry budget, per-query execution profile.
8. **Thử staging/canary:** dữ liệu có tombstone/hot partitions thật, traffic peak và CL tương tự production.
9. **Theo dõi regression:** p95/p99 của API chính, error rate, JVM, disk, maintenance và replica health; có điều kiện rollback rõ.
10. **Lưu hồ sơ:** lý do thay đổi, owner, thời gian, phiên bản, tên key/giá trị trước–sau, kết quả đo, ngày đánh giá lại.

### Khi nào *có thể* nới giới hạn?

Một thay đổi có cơ sở khi **workload có giới hạn và được chứng minh**:

- Batch analytics riêng cần 10 giây thay vì 3 giây; đã có rate limit và staging cho thấy API tương tác không bị ảnh hưởng.
- Guardrail warning quá nhạy với một kích thước hợp lệ có baseline rõ, **không** làm tăng fail/OOM/compaction debt, có kế hoạch giám sát.
- Một thay đổi version nâng khả năng xử lý, và benchmark chỉ ra ngưỡng cũ không còn phù hợp **trong phạm vi hẹp**.

Ngay cả khi hợp lý, nên ưu tiên **nới theo workload/role/profile hoặc khoảng bảo trì** nếu nền tảng hỗ trợ. Không tăng toàn cluster và vô thời hạn chỉ để “hết thông báo”.

## 14. Runbook khi production đang báo read timeout và tombstone warning

**Bước 1 — Bảo vệ hệ thống trước khi sửa cấu hình.** Xác định liệu write/read SLO đã bị vi phạm, có ổ đĩa gần đầy hoặc node down không. Giới hạn traffic/đợt retry ở tầng ứng dụng nếu cần theo quy trình, tránh làm thêm backlog.

**Bước 2 — Chụp hiện trạng.** Lưu query template, giờ UTC, CL, RF, keyspace/table, coordinator, node/DC, loại timeout, warning text và số request. Tránh sao chép nguyên dữ liệu người dùng vào ticket.

**Bước 3 — Phân loại lỗi.** `Unavailable` cần điều tra replicas; guardrail fail cần kiểm tra ngưỡng và query; read timeout cần tìm chỗ chậm; write timeout cần xác định mutation có thể đã áp dụng một phần.

**Bước 4 — Đo tài nguyên cùng cửa sổ.** So p99 và request rate với `nodetool tpstats`, `compactionstats`, `tablestats`, `gcstats`, disk I/O và network, theo từng node. Lấy tracing **có chọn lọc**, không bật cho tất cả request.

**Bước 5 — Tìm chỗ phải làm ít việc hơn.** Với time-series, thường là thêm bucket vào partition key, đọc clustering range nửa kín, giới hạn lịch sử hoặc dùng rollup. Với batch, chia nhỏ và dùng async có concurrency hữu hạn.

**Bước 6 — Nếu vẫn cần nới**, sửa **đúng tham số** và scope sau khi benchmark; cân đối deadline gateway/client/server và nguồn lực. Tạo rollback sẵn và hạn chế rollout một nhóm workload trước.

**Bước 7 — Kiểm chứng.** Sau thay đổi phải quan sát p99, throughput, error/timeout, retry amplification, in-flight/queue, GC, disk và tombstone metrics trong cả thời gian tải đỉnh; xác nhận không làm workload khác hồi quy.

**Bước 8 — Ghi nhận học được.** Cập nhật alert về guardrail, xử lý write timeout/idempotency, schema governance và quy trình kiểm tra capacity. Nếu đã rollback, lưu bằng chứng nguyên nhân và hẹn sửa thiết kế thay vì giữ cấu hình nới vô hạn.

## 15. Sai lầm thường gặp

| Nhận định | Đúng/sai | Lý do |
| --- | --- | --- |
| “Nâng read timeout làm Cassandra đọc SSTable nhanh hơn.” | **Sai** | Nó chỉ thay thời gian chờ. |
| “Nâng tombstone failure threshold tự giảm tombstone scan.” | **Sai** | Nó có thể cho phép scan nhiều hơn, không làm dữ liệu chết biến mất. |
| “`ReadTimeout` có nghĩa partition không tồn tại.” | **Sai** | Request chưa hoàn tất trước timeout, không phải kết quả rỗng. |
| “`WriteTimeout` có nghĩa không replica nào đã ghi.” | **Sai** | Một số replica có thể đã áp dụng mutation. |
| “`Unavailable` có thể sửa bằng cách chờ lâu hơn.” | **Sai trong bản chất lỗi** | Cần đủ replica khả dụng và đúng topology/CL. |
| “`LIMIT 10` bảo đảm server chỉ xử lý mười tombstone/hàng.” | **Sai** | Giới hạn hàng trả về khác lượng dữ liệu vật lý phải duyệt. |
| “Tăng batch size luôn giảm chi phí ghi.” | **Sai** | Multi-partition batch lớn có thể gây spike và coordinator overhead. |
| “Page size càng lớn càng nhanh.” | **Sai** | Phải xét byte/page, memory, network và latency. |
| “RF = 3, `LOCAL_QUORUM` cần ba ACK.” | **Sai** | Cần hai phản hồi ở local DC có RF 3. |
| “Đổi timeout driver là đã đổi server timeout.” | **Sai** | Hai lớp được cấu hình độc lập. |
| “Tăng timeout giảm lỗi nhưng p99 xấu đi vẫn là thành công.” | **Sai** | Phải thỏa SLO và capacity budgets, không chỉ error rate. |
| “Có thể nới hẹp scope nếu benchmark cho thấy workload hợp lệ và có rollback.” | **Đúng** | Cần đo tác động và quản trị thay đổi. |

## 16. Bài tập tự kiểm tra có đáp án

**Bài 1.** Một API có gateway deadline 1 giây, driver timeout 3 giây, server read timeout 5 giây. Nâng server read timeout lên 30 giây có giúp gateway trả thành công truy vấn mất 6 giây không?

**Đáp án:** **Không**, vì gateway đã hết hạn sau khoảng 1 giây. Muốn đáp ứng SLO phải giảm thời gian thực thi hoặc thay đổi **yêu cầu nghiệp vụ/kiến trúc API**, không chỉ nâng timeout server.

**Bài 2.** RF = 3 tại `dc1`, write `LOCAL_QUORUM` nhận ACK từ một replica rồi client thấy `WriteTimeout`. Có thể retry ngay bằng `event_id` mới không?

**Đáp án:** **Không nên.** Một replica đã có thể ghi. Retry bằng ID mới có nguy cơ tạo event trùng; phải xác định idempotency semantics và dùng ID ổn định hoặc quy trình reconciliation phù hợp.

**Bài 3.** Query `LIMIT 10` bị fail do quét quá nhiều tombstone. Nâng `tombstone_failure_threshold` gấp mười có làm query dùng ít disk I/O hơn không?

**Đáp án:** **Không.** Query có thể được phép quét nhiều hơn, tăng read amplification, memory và latency. Sửa gốc là thu hẹp partition/range, cải thiện TTL/delete/compaction và kiểm tra repair.

**Bài 4.** Một dịch vụ có lưu lượng 200 request/giây; thời gian ở trong hệ thống tăng từ 0,1 lên 2 giây. Theo Little's Law ở trạng thái giả định ổn định, số request in-flight thay đổi thế nào?

**Đáp án:** Từ `200 × 0,1 = 20` lên `200 × 2 = 400` request. Thực tế overload làm hệ thống mất ổn định, nhưng phép tính cho thấy nguy cơ concurrency tăng gấp 20.

**Bài 5.** Cùng một CQL request bị `Unavailable` khi local DC chỉ còn một replica khả dụng trong RF = 3 và CL `LOCAL_QUORUM`. Tăng timeout sẽ giải quyết không?

**Đáp án:** **Không phải cách sửa gốc.** Cần khôi phục khả năng có đủ hai replica của partition, hoặc đánh giá CL/availability theo chính sách nghiệp vụ; timeout không tạo thêm replica.

**Bài 6.** Sau nâng timeout read từ 3 lên 15 giây, batch success rate tăng từ 95% lên 99%, nhưng p99 của API tương tác từ 80 ms lên 600 ms và GC pause tăng. Có nên triển khai cho toàn cluster?

**Đáp án:** **Không nên** nếu API tương tác vượt SLO. Hãy cô lập batch workload, giảm query cost, giới hạn concurrency và benchmark lại; success rate của một nhóm không đủ để đánh giá tác động toàn dịch vụ.

**Bài 7.** Vì sao test guardrail bằng tài khoản quản trị có thể khác test bằng role ứng dụng?

**Đáp án:** Một số guardrail có ngoại lệ hoặc đường xử lý khác theo phiên bản/quyền. Cần xác minh cùng role và cấu hình mà ứng dụng production sử dụng.

**Bài 8.** Một nhóm muốn nới batch limit để ghi 10.000 partition trong một `BEGIN BATCH`. Hãy đề xuất hướng xử lý trước khi tăng ngưỡng.

**Đáp án:** Kiểm tra nhu cầu atomicity thực sự, tách các statement theo partition, dùng prepared async writes với bounded concurrency/rate, đo throughput và replica I/O. Không coi batch nhiều partition là bulk loader.

**Bài 9.** Có một batch job hợp lệ chạy ban đêm, query mất 6 giây, SLA cho phép 30 giây. Khi nào có thể cân nhắc driver timeout dài hơn?

**Đáp án:** Khi đã xác định server timeout/CL cũng phù hợp, workload có giới hạn concurrency, benchmark cho thấy không làm chậm hệ thống khác, và có rollback/monitoring. Nên dùng profile riêng thay vì nới toàn ứng dụng.

## 17. Sơ đồ ghi nhớ và checklist cuối bài

~~~mermaid
flowchart LR
    A["Warning / guardrail failure / timeout"] --> B["Phân loại theo lớp và nguyên nhân"]
    B --> C["Đo p99, in-flight, queue, SSTable/tombstone, GC, disk"]
    C --> D["Giảm chi phí query + sửa data model + backpressure"]
    D --> E{"Workload hợp lệ vẫn cần nới budget?"}
    E -->|Không| F["Giữ giới hạn bảo vệ hệ thống"]
    E -->|Có| G["Thử nghiệm có phạm vi và giới hạn tài nguyên"]
    G --> H["Canary, đo SLO và có rollback"]
~~~

~~~text
[ ] Hiểu đây là warning, guardrail fail, timeout hay unavailable.
[ ] Xác định tầng: gateway, service, driver, coordinator, replica.
[ ] Ghi rõ RF/CL, data center, query shape và phiên bản Cassandra.
[ ] Đo request rate, p95/p99, in-flight, retry và node/resource metrics.
[ ] Không thay lỗi timeout bằng kết quả SELECT rỗng.
[ ] Không retry write mù với ID/timestamp mới.
[ ] Ưu tiên partition key đúng, bucket, TTL/compaction và bounded paging.
[ ] Không nới tombstone/batch/partition thresholds chỉ để tắt warning.
[ ] Chỉ nới theo workload hợp lệ, với resource budget và rollback.
[ ] Sau rollout: kiểm tra SLO của các workload khác và repair/backup safety.
~~~

**Kết luận:** guardrail và timeout không chỉ là những “rào cản gây phiền” — chúng giúp **phơi bày query shape nguy hiểm, giới hạn công việc quá lớn và ngăn lỗi cục bộ lan thành quá tải toàn cluster**. Nâng warning/fail threshold có thể giảm số lần request bị chặn, còn nâng timeout có thể tăng số request hoàn tất, nhưng **không tăng tốc SSTable, không tạo thêm replica, không xóa tombstone và không mở rộng capacity thực**. Với Cassandra, hướng tối ưu bền vững là **giảm lượng dữ liệu mỗi truy vấn phải xử lý, giữ partition có kích thước dự đoán được, phân trang và giới hạn concurrency, quan sát tài nguyên theo node/CL, rồi mới điều chỉnh ngưỡng có kiểm chứng và rollback**.
