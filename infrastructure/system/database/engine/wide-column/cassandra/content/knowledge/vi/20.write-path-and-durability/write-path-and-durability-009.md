# Ghi quá tải, hàng đợi và cơ chế điều tiết theo phiên bản

> **Chương:** Đường ghi và độ bền  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — kiến trúc phân tán và mô hình wide-column của Apache Cassandra, từ khóa phân vùng, thiết kế bảng theo truy vấn, nhất quán đọc/ghi đến CQL, replication, compaction, repair, xử lý lỗi và kết nối ứng dụng Java.

Apache Cassandra được tối ưu cho lưu lượng ghi lớn, nhưng **ghi nhanh không đồng nghĩa với khả năng tiếp nhận vô hạn**. Khi ứng dụng tạo mutation nhanh hơn tốc độ coordinator, replica, commit log, memtable flush hoặc ổ đĩa có thể xử lý, các hàng đợi tăng dần. Hệ quả có thể là độ trễ p99 tăng vọt, request hết hạn, lỗi quá tải và hiệu ứng dây chuyền do client retry. Kết quả từ một lần `INSERT` thành công ở mức tải thấp không dự báo được hành vi của cụm ở đỉnh tải.

Bài này tập trung vào **cơ chế ghi quá tải, vị trí các hàng đợi, cách quan sát và điều tiết tải**, đồng thời chỉ ra **khác biệt quan trọng giữa các thế hệ Cassandra 3.11, 4.0, 4.1 và 5.x**. Các tên cấu hình không phải API bất biến: khi vận hành phải đối chiếu chính xác phiên bản và bản phân phối đang chạy. Các thử nghiệm gây quá tải dưới đây chỉ dành cho cluster lab cô lập, có giới hạn dừng.

## 1. Mục tiêu học tập

Học xong, bạn có thể:

1. Vẽ và giải thích luồng ghi từ Java client đến coordinator, replica, commit log, memtable, SSTable; xác định khâu có thể tắc nghẽn.
2. Phân biệt **backlog**, **backpressure**, **rate limiting**, **load shedding**, **timeout** và **retry**.
3. Đọc số liệu của `nodetool tpstats`, `compactionstats`, JMX/metrics và Java driver để khoanh vùng nút thắt.
4. Giải thích vì sao tài liệu cấu hình backpressure của Cassandra 3.11 **không** được chép trực tiếp sang 4.x/5.x; biết phạm vi của native transport rate limiting trong 4.1/5.x.
5. Thiết kế thử tải có giới hạn; đề xuất điều tiết từ ứng dụng và biện pháp vận hành nhằm bảo vệ tính sẵn sàng, độ trễ và độ bền dữ liệu.
6. Xử lý kết quả ghi **không rõ đã áp dụng hay chưa** khi timeout mà không tạo lỗi nghiệp vụ do retry mù quáng.

## 2. Đường ghi và vị trí phát sinh hàng đợi

### 2.1. Luồng xử lý của một mutation thông thường

~~~mermaid
flowchart TD
    A["Ứng dụng Java: producer và hàng đợi nội bộ"] --> B["Driver: pool, giới hạn in-flight, timeout"]
    B --> C["Coordinator: native transport và xử lý yêu cầu"]
    C --> D["Chọn replica theo token, RF và topology"]
    D --> E["Internode messaging: gửi mutation"]
    E --> F1["Replica 1"]
    E --> F2["Replica 2"]
    E --> F3["Replica 3"]
    F1 --> G1["Commit log + memtable"]
    F2 --> G2["Commit log + memtable"]
    F3 --> G3["Commit log + memtable"]
    G1 --> H["Coordinator thu đủ xác nhận theo CL"]
    G2 --> H
    G3 --> H
    H --> I["Phản hồi cho Java client"]
    G1 -. "Flush nền" .-> J["SSTable trên disk"]
    G2 -. "Flush nền" .-> J
    G3 -. "Flush nền" .-> J
    J -. "Compaction nền" .-> K["SSTable được hợp nhất"]
~~~

**Các bước khái quát:**

1. Ứng dụng gửi CQL `INSERT`/`UPDATE`/`DELETE` qua native protocol. Node nhận yêu cầu đóng vai trò **coordinator**; nó có thể không phải replica lưu partition.
2. Coordinator tính vị trí partition theo **partition key**, xác định replica theo replication strategy và gửi mutation qua mạng internode.
3. Replica nhận mutation, ghi vào **commit log** và cập nhật **memtable**; chi tiết đồng bộ commit log trước khi xác nhận phụ thuộc `commitlog_sync`.
4. Coordinator chờ số replica phản hồi theo **consistency level (CL)** của request. Phần việc không cần nằm trên đường phản hồi vẫn có thể tiếp diễn.
5. Memtable được flush thành **SSTable** và sau đó compaction chạy nền. **Không phải mỗi lần ghi đều chờ flush SSTable** trước khi phản hồi cho client.

Một hàng đợi ở bất kỳ điểm nào trong sơ đồ cũng có thể làm tăng thời gian đầu-cuối. Ví dụ commit log còn khả dụng nhưng flush không theo kịp: memtable và commit log segment tích tụ, gây chặn ghi; mở rộng thread tiếp nhận request có thể làm hàng đợi **dài hơn**, không giải quyết giới hạn I/O. <a id="writepath"></a>

### 2.2. Độ bền ghi và xác nhận của replica là hai trục khác nhau

Với `durable_writes: true` ở keyspace, Cassandra sử dụng commit log theo chính sách durability đang cấu hình. Phân biệt:

| Trục | Ví dụ cấu hình | Điều nó kiểm soát |
|---|---|---|
| **Số replica phải xác nhận** | `ONE`, `LOCAL_QUORUM`, `QUORUM`, `ALL` | Khi nào coordinator có thể trả **success** theo yêu cầu nhất quán |
| **Đồng bộ commit log** | `commitlog_sync: periodic` hoặc `batch` | Khi log ở mỗi replica được fsync tương ứng với lịch/đường xác nhận |
| **Flush memtable** | Tự động khi đạt ngưỡng bộ nhớ/commit log | Khi mutation được chuyển sang SSTable |
| **Replication/repair** | RF, strategy, hinted handoff, repair | Các node nào giữ bản sao và đồng bộ chúng ra sao |

- Với chế độ **`batch` của commit log**, Cassandra đợi fsync commit log trước khi xác nhận mutation cục bộ, tăng bảo đảm độ bền trên node nhưng có thể tăng write latency.
- Với **`periodic`**, các ghi có thể được xác nhận trước khi fsync của chu kỳ tiếp theo hoàn tất; một sự cố đột ngột có thể làm mất dữ liệu mới chưa được fsync trên các replica liên quan. Khoảng có nguy cơ không nhất thiết đúng bằng thời gian cấu hình nếu fsync bị chậm.
- CL cao hơn tăng yêu cầu về số replica phản hồi; nó **không** tự biến chế độ `periodic` thành `batch`. Ngược lại, `batch` commit log cũng không tự tạo quorum.

**Ghi nhận:** từ “batch” trong `commitlog_sync: batch` **khác** câu lệnh CQL `BEGIN BATCH`. Dùng CQL batch để gom hàng loạt partition không làm Cassandra tự động ghi nhanh hơn; batch đa partition còn có thêm chi phí điều phối/batchlog.

## 3. Cơ chế quá tải: tốc độ đến, tốc độ xử lý và backlog

Ký hiệu:

- `λ`: lưu lượng yêu cầu ghi đến, ví dụ 2.000 request/giây.
- `μ`: thông lượng xử lý ổn định của hệ thống trong điều kiện hiện tại, ví dụ 1.500 request/giây.
- `Q(t)`: số yêu cầu đang chờ tại một khâu.

Nếu tải vào **liên tục vượt** tải xử lý, backlog tăng xấp xỉ `(λ − μ) × Δt` trong giai đoạn chưa bị chặn hoặc bỏ yêu cầu. Chẳng hạn:

~~~text
Tốc độ tới (λ)          2.000 ghi/s
Tốc độ xử lý (μ)        1.500 ghi/s
Chênh lệch                 500 ghi/s
Backlog thêm sau 30 s   15.000 request  (ước tính lý thuyết)
~~~

Đây là phép minh họa **cân bằng lưu lượng**, không phải dự báo chính xác cho cluster Cassandra: coordinator/replica, kích thước mutation, timeout, driver, network và giới hạn hàng đợi khiến `μ` thay đổi. Nhưng nó chỉ ra nguyên tắc: **không có hàng đợi hữu hạn nào hấp thụ được tải vượt khả năng xử lý mãi mãi**.

Khi tải ổn định, định luật Little `L = λ × W` liên hệ số yêu cầu trong hệ thống (L), thông lượng (λ) và thời gian ở trong hệ thống (W). Ví dụ giữ 1.000 request in-flight và đạt 2.000 request/s nghĩa là thời gian lưu hệ thống trung bình khoảng 0,5 giây; mở rộng số request in-flight không tự làm tài nguyên disk phục vụ nhanh hơn.

### 3.1. Phân biệt năm hiện tượng

| Thuật ngữ | Ý nghĩa | Biểu hiện điển hình |
|---|---|---|
| **Queue/backlog** | Công việc đã nhận nhưng chưa tới lượt thực thi | `Pending` tăng, latency đuôi dài |
| **Backpressure** | Làm nguồn gửi **chậm lại** vì nơi nhận không theo kịp | Client bị chặn/giảm tốc đọc từ socket hoặc producer tự ngừng nạp |
| **Rate limiting** | Giới hạn tốc độ tiếp nhận/gửi theo thời gian | QPS được khống chế; có thể delay hoặc reject tùy cơ chế |
| **Load shedding/reject** | Từ chối một phần việc mới để bảo vệ hệ thống | Lỗi quá tải rõ ràng, tỷ lệ request bị từ chối tăng |
| **Timeout** | Không nhận được kết quả đúng hạn | Có thể xảy ra dù mutation đã được áp dụng trên một số replica |

Chúng **không đồng nghĩa**. Backpressure có thể khiến latency tăng nhưng hạn chế lỗi tức thời; reject giúp hệ thống còn phục vụ được phần tải khác. Timeout là kết quả quan sát của một lời gọi bị trễ, không nhất thiết nói được nguyên nhân.

### 3.2. Vì sao retry không có điều tiết gây “retry storm”?

Giả sử trong một giây client gửi 1.000 mutation, 10% bị timeout, và mỗi timeout được retry ngay hai lần. Tải đến lại tăng thêm tối đa 200 request trong chính giai đoạn cluster đã chậm; nếu các lần retry lại timeout, tải có thể tiếp tục phình. Request cũ có thể vẫn đang xử lý ở replica trong khi request lặp lại đã tới.

**Quy tắc thực hành:** đặt ngân sách retry nhỏ, dùng exponential backoff với jitter, giới hạn cả số yêu cầu **đang bay** (*in-flight*) lẫn tốc độ gửi, và áp dụng circuit breaker/load shedding ở biên ứng dụng khi cần. Chỉ retry tự động khi **ngữ nghĩa nghiệp vụ và loại statement** cho phép; timeout của ghi có thể là kết quả **mơ hồ**.

## 4. Nút thắt nằm ở đâu? Quan sát trước khi chỉnh cấu hình

### 4.1. Hàng đợi ở client và coordinator

**Java client/driver:**

- Producer nhận sự kiện từ HTTP/Kafka có thể tạo backlog **trước driver**; số request mà Cassandra nhìn thấy nhỏ hơn số request ứng dụng đang chờ.
- Driver dùng connection pool và giới hạn số request đồng thời trên connection. Khi tầng gửi có quá nhiều lời gọi, pending acquisition và request timeout có thể tăng ngay cả trước khi Cassandra xử lý.
- Nếu mỗi yêu cầu lớn hoặc nhiều batch đồng thời, số **byte in-flight** quan trọng không kém số request; chỉ nhìn request/s dễ bỏ qua tải lớn bất thường.

**Coordinator:**

- Native transport nhận và điều phối request; nếu tốc độ nhập quá lớn, request phải chờ hoặc bị giới hạn tùy phiên bản và cấu hình.
- Coordinator có thể chờ ACK từ nhiều replica; `LOCAL_QUORUM` với RF = 3 ở DC cục bộ thường cần hai replica, trong khi `ONE` cần một. Tăng CL có thể làm phần “đợi replica” của request dài hơn khi một replica chậm.
- Không phải mọi coordinator sẽ bận như nhau. Token-aware routing và phân bố khóa phân vùng ảnh hưởng vị trí xử lý, còn hot partition khiến một nhóm replica nóng bất thường.

**Dấu hiệu cần đối chiếu:** client pending/latency, số request in-flight, coordinator write latency, thời gian chờ trong các thread pool và phân bố write load giữa node.

### 4.2. Hàng đợi ở internode messaging, replica và storage engine

| Nút thắt | Dấu hiệu thực tế | Nguyên nhân có thể |
|---|---|---|
| Gửi mutation giữa các node | Tăng latency mạng, thông điệp hết hạn/dropped | Mạng, quá nhiều request, replica chậm |
| Worker xử lý mutation | `MutationStage`/pool tương ứng có `Pending` và `Blocked` tăng theo thời gian | CPU/GC, tải ghi, lock/resource contention |
| Commit log | `CommitLog.PendingTasks`, `WaitingOnCommit`, `WaitingOnSegmentAllocation` tăng | Fsync chậm, disk I/O hoặc chờ segment |
| Memtable/flush | `PendingFlushes`, số byte memtable và thời gian flush tăng | Disk chậm, flush writer không theo kịp |
| Compaction | `Compaction.PendingTasks` và SSTable backlog tăng | Write amplification, disk/CPU, compaction bị hạn tốc |
| Dung lượng disk | Disk gần đầy, lỗi I/O, commit log/flush/compaction không còn chỗ | Thiếu capacity hoặc dữ liệu/tombstone/SSTable tăng |
| Hints sau sự cố replica | Hints tích tụ, delivery chậm hoặc hết thời hạn lưu | Node Down, network, lượng mutation lớn |

Với nhiều trường hợp, **điểm nghẽn thật nằm ở disk**, nhưng dấu hiệu đầu tiên lại là `Pending` ở thread pool. Cần nối các metric theo **cùng một cửa sổ thời gian**: “thấy 1.000 mutation pending” không tự chứng minh phải tăng số thread. Việc tăng concurrency thường làm disk/GC quá tải nặng hơn nếu I/O mới là giới hạn.

Một vài metric Cassandra phản ánh **tổng tích lũy từ khi node khởi động** thay vì số đang chờ; với counter phải tính độ tăng theo phút (rate/delta) và so từng node. Tên stage, metric và ý nghĩa chi tiết có thể đổi giữa phiên bản.

## 5. Khác biệt theo phiên bản: đừng sao chép công thức cấu hình

### 5.1. Bảng định hướng phiên bản

| Nhánh Apache Cassandra | Cơ chế/điểm cần biết | Điều phải tránh suy diễn |
|---|---|---|
| **3.11** | Tài liệu chính thức có `back_pressure_enabled` và `back_pressure_strategy` (*RateBasedBackPressure*) để coordinator điều tiết mutation gửi tới replica | Không mặc định tính năng đã bật; mặc định tài liệu là `false`. Không áp tên tham số cũ cho các nhánh mới |
| **4.0** | Kiến trúc internode messaging và tổ chức thực thi đã được thay đổi đáng kể so với 3.11; tiếp tục dùng metric và giới hạn phù hợp bản 4.0 | Không suy ra có native transport request-per-second limiter cùng khóa với 4.1 nếu tài liệu 4.0 không liệt kê |
| **4.1** | Tài liệu `cassandra.yaml` ghi nhận `native_transport_rate_limiting_enabled` và `native_transport_max_requests_per_second`; hành vi phụ thuộc lựa chọn `THROW_ON_OVERLOAD` ở kết nối client | Đây là kiểm soát **đầu vào native transport** của node, không phải bảo đảm RF/CL hay giới hạn write IOPS trên mọi replica |
| **5.0 / 5.x** | Tiếp tục có cơ chế native transport rate limiting và metadata native protocol liên quan quá tải; số metric/giới hạn bộ nhớ và tên cấu hình có thể khác | Không xem tên trường, giá trị mặc định hoặc cú pháp bản 5.x là hợp lệ trên tất cả cụm 3.x/4.x hoặc bản phân phối tùy biến |

**Nguồn đối chiếu trước khi sửa:** [Cassandra 3.11 `cassandra.yaml`](https://cassandra.apache.org/doc/3.11/cassandra/configuration/cass_yaml_file.html), [4.0](https://cassandra.apache.org/doc/4.0/cassandra/configuration/cass_yaml_file.html), [4.1](https://cassandra.apache.org/doc/4.1/cassandra/configuration/cass_yaml_file.html), [5.0](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html). Luôn xác nhận phiên bản đang chạy với `SELECT release_version FROM system.local;` và đối chiếu **file cấu hình thực tế của phân phối**.

### 5.2. Cơ chế cũ: RateBasedBackPressure ở Cassandra 3.11

Tài liệu 3.11 mô tả các mục:

~~~yaml
# Trích tên tùy chọn cho Apache Cassandra 3.11; KHÔNG dùng nguyên khối
# làm hướng dẫn cấu hình trên 4.x/5.x.
back_pressure_enabled: false
# back_pressure_strategy: ...
~~~

Khi được cấu hình, coordinator có thể điều chỉnh tốc độ đẩy mutation ra các replica dựa trên tỷ lệ request/response theo chiến lược. Nhưng cơ chế này chỉ là **một mắt xích**: nếu ứng dụng tiếp tục nạp vô hạn, backlog có thể chuyển từ replica về coordinator hoặc ứng dụng. Không coi đây là bảo đảm cluster tự “xử lý mọi burst”.

**Quan trọng:** tài liệu `cassandra.yaml` 4.0, 4.1 và 5.0 không liệt kê các khóa `back_pressure_enabled`/`back_pressure_strategy` như 3.11. Vì vậy, ở các nhánh mới **không dán** cấu hình 3.11 vào `cassandra.yaml` rồi cho rằng nó có tác dụng. Thay đổi internode messaging và cơ chế giới hạn phải dựa vào tài liệu đúng phiên bản, metric và thử tải.

### 5.3. Native transport rate limiting ở Cassandra 4.1 và 5.x

Đoạn sau là **minh họa cú pháp** trong tài liệu 4.1/5.x, không phải cấu hình nên bật nguyên trạng:

~~~yaml
# Tham khảo theo phiên bản; chỉ thiết lập trong lab sau khi kiểm tra
# cú pháp, tác động đến client, giá trị mặc định và cấu hình đang dùng.
native_transport_rate_limiting_enabled: true
native_transport_max_requests_per_second: 10000
~~~

Con số 10.000 request/s là **giả định của lab**, không phải đề xuất mặc định. Nó biểu diễn giới hạn **request được điều phối qua native transport trên một node**, không phải tổng ghi thành công của cluster hay tốc độ disk thực sự.

Tài liệu native protocol và `cassandra.yaml` mô tả hai đường phản ứng khi vượt ngưỡng:

1. Nếu kết nối client thương lượng bật `THROW_ON_OVERLOAD`, server có thể **trả lỗi OverloadedException** cho các request vượt giới hạn.
2. Nếu không bật lựa chọn này, server có thể **tạm ngừng tiêu thụ message từ socket** để tạo backpressure; phía ứng dụng có thể thấy hàng đợi/độ trễ tăng thay vì lỗi quá tải trực tiếp.

Driver hoặc native protocol version phải hỗ trợ hành vi thương lượng tương ứng. **Không giả định** ứng dụng Java đang bật `THROW_ON_OVERLOAD` chỉ vì cluster hỗ trợ. Cần kiểm tra bản driver, cấu hình thực tế, kết quả thử tải và log. Một phản hồi timeout trong cấu hình backpressure **không có nghĩa** mutation chưa được xử lý.

**Ranh giới bảo vệ:** limiter ở cổng native transport bảo vệ tốc độ nhận request tại node làm coordinator; nhưng một request có thể sinh nhiều thông điệp replica, nhiều mutation hoặc chi phí I/O rất khác nhau. Vì vậy rate limit theo request/s chỉ là một biện pháp, không thay thế kiểm soát in-flight, kích thước mutation, thiết kế partition, theo dõi disk và tính toán CL.

### 5.4. Các nút điều tiết khác cần phân biệt

| Vị trí | Cơ chế | Lưu ý |
|---|---|---|
| Producer/API/Kafka consumer | Giới hạn token-bucket QPS, bounded queue, pause/resume consumption | Đây thường là điểm điều tiết gần nguồn dữ liệu nhất và dễ kiểm soát |
| Java driver | Giới hạn async in-flight, pool, timeout hợp lý, retry budget | Số connection không tương đương số operation/s; tránh tạo thêm session cho mỗi ghi |
| Coordinator native transport | Giới hạn tiếp nhận, lỗi quá tải hoặc ngừng đọc socket tùy phiên bản | Quan sát cả server **và** latency/queue của client |
| Internode messaging | Giới hạn bộ nhớ/đường truyền, quản lý message, timeout/dropped | Cấu hình và tên metric thay đổi theo phiên bản |
| Commit log/memtable/flush | Throttle/chặn ghi khi tài nguyên bị căng | Disk/flush là giới hạn vật lý; không sửa bằng nâng thread vô điều kiện |
| Compaction | Điều tiết thông lượng, số compactor đồng thời | Quá thấp sẽ tích lũy SSTable; quá cao có thể chiếm I/O của foreground |
| Admission policy nghiệp vụ | Trả HTTP 429/503, yêu cầu thử lại sau, ưu tiên tác vụ thiết yếu | Bảo vệ user-facing request khi nhu cầu vượt năng lực thật |

Các mục `concurrent_compactors`, `compaction_throughput`, cấu hình memtable/flush và commit log cần được kiểm tra tên, đơn vị, mặc định theo đúng release. Tăng một giới hạn trước khi xác định bottleneck thường chỉ **đẩy hàng đợi xuống tầng thấp hơn**.

## 6. Thực hành: lập baseline và thử quá tải có giới hạn

### 6.1. Điều kiện lab

Chuẩn bị cluster Cassandra thử nghiệm, nhiều node nếu muốn thấy đường internode và CL, cùng công cụ `cqlsh`, `nodetool`, Java driver hoặc công cụ tạo tải kiểm soát QPS. Ghi lại:

- Phiên bản Cassandra thực tế, số node/DC/rack, CPU/RAM/disk, RF và CL.
- Kiểu commit log (`periodic`/`batch`), cấu hình native transport và giới hạn in-flight.
- Compaction strategy, tải nền, dung lượng đĩa và tình trạng node.
- Số kết nối client, kích thước mutation, loại request, tỷ lệ read/write.

Chỉ chạy trên cluster **không có dữ liệu sản xuất** và không dùng các lệnh gây hủy dữ liệu để “dọn nhanh”. Định nghĩa ngưỡng dừng thử: khi p99 vượt SLO giả định trong nhiều cửa sổ đo, lỗi tăng, disk sắp đầy hoặc `Pending` liên tục không hồi phục thì giảm/dừng producer và theo dõi cluster drain backlog.

### 6.2. Tạo bảng có partition key phù hợp

Trong `cqlsh`, xác minh tên DC bằng `nodetool status` và dùng RF phù hợp với số node thực tế. Ví dụ chỉ đúng cho DC tên `dc1` có ít nhất ba node:

~~~sql
CREATE KEYSPACE IF NOT EXISTS write_overload_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS write_overload_lab.events_by_tenant_day (
    tenant_id uuid,
    day_bucket date,
    event_id uuid,
    occurred_at timestamp,
    payload text,
    PRIMARY KEY ((tenant_id, day_bucket), event_id)
);
~~~

Giải thích: `tenant_id, day_bucket` là khóa phân vùng kép; `event_id` là clustering key, bảo đảm một sự kiện được xác định ổn định trong một tenant/ngày. Dùng nhiều tenant và nhiều ngày giúp khảo sát phân bố tải. Một tenant cực lớn vẫn có thể tạo **hot partition** theo ngày; nếu vậy cần chia bucket nhỏ hơn hoặc thêm shard có tính toán, thay vì tăng thread để che triệu chứng.

Một mutation mẫu:

~~~sql
INSERT INTO write_overload_lab.events_by_tenant_day
    (tenant_id, day_bucket, event_id, occurred_at, payload)
VALUES (
    5bd928ad-a5aa-4eb9-8c12-bfda73571a70,
    '2026-11-21',
    b399f6fb-1fa1-49e2-b56e-3455412a66dd,
    '2026-11-21T09:00:00Z',
    'sample-001'
);
~~~

Mỗi sự kiện benchmark nên có **ID ổn định** khi retry; ghi chép tỉ lệ phân phối partition và kích thước payload. Không dùng toàn bộ mutation của hàng triệu yêu cầu vào **một** `(tenant_id, day_bucket)` nếu mục đích là đo thông lượng tổng thể: điều đó đo hot partition hơn là sức chứa phân tán của cluster.

### 6.3. Kịch bản tải và số liệu cần ghi

Chạy theo từng nấc đã giới hạn, ví dụ các **mức thử nghiệm giả định** dưới đây; không ngầm xem chúng là công suất thật của máy:

| Pha | Đầu vào giả định | Mục tiêu | Điều quan sát |
|---|---|---|---|
| Baseline | 200 ghi/s, concurrency giới hạn | Xây đường chuẩn latency và tài nguyên | p50/p95/p99, disk, Pending, lỗi |
| Tăng có kiểm soát | 400 rồi 600 ghi/s | Tìm mức bắt đầu tăng hàng đợi | λ vào, throughput thành công, p99 |
| Burst ngắn | 2× mức baseline trong cửa sổ ngắn | Xem khả năng hấp thụ burst | Độ sâu queue, thời gian hồi phục |
| Recovery | Trả về 200 ghi/s | Xác nhận backlog tiêu tan | Pending trở về nền, latency/lỗi ổn định |
| Đối chứng điều tiết | Cùng workload nhưng giới hạn in-flight và QPS nguồn | Kiểm tra hiệu quả backpressure từ ứng dụng | Hàng đợi client/server và tỉ lệ thành công |

Thiết kế hai loại phép đo:

- **Open-loop:** bộ tạo tải cố gửi theo QPS mục tiêu; thích hợp để phát hiện overload. Phải ghi **offered load** kể cả khi server không nhận/xử lý được.
- **Closed-loop:** gửi tiếp sau khi request trước hoàn tất hoặc còn chỗ in-flight; thích hợp đánh giá latency theo concurrency cố định nhưng có thể tự giảm QPS khi hệ thống chậm.

Không so sánh kết quả hai kiểu load generator như cùng một thí nghiệm. Một hệ thống chậm dần có thể trông “ổn” trong phép đo closed-loop chỉ vì tốc độ gửi thực tế đã giảm.

Chạy đủ thời gian để thấy xu hướng queue (và recovery), nhưng có **ngưỡng dừng**; không cố đẩy quá tải cho tới khi node sập. Ghi riêng điều kiện warm-up, trạng thái compaction/GC và disk I/O.

### 6.4. Thu thập với nodetool

Trong các cửa sổ đo, trên **từng node**:

~~~bash
nodetool status
nodetool tpstats
nodetool compactionstats
nodetool tablestats write_overload_lab.events_by_tenant_day
nodetool netstats
~~~

Một số phiên bản có thể hỗ trợ tùy chọn bổ sung hoặc hiển thị tên pool khác nhau; `nodetool help` trên chính bản chạy là nguồn để kiểm tra cú pháp. Các lệnh trên lấy thông tin, không yêu cầu xóa dữ liệu.

**Đọc `tpstats` đúng cách:** so sánh các cột `Active`, `Pending`, `Completed`, `Blocked`, `All time blocked` theo thời gian, không chỉ một snapshot. Phần `Dropped Messages` thường là **bộ đếm tích lũy**; cần tính chênh lệch theo cửa sổ. `MUTATION` dropped tăng là dấu hiệu cần điều tra, **không** đồng nghĩa mỗi mutation ấy mất dữ liệu vĩnh viễn hoặc mọi ghi đã được xác nhận thành công.

**Đọc `compactionstats` đúng cách:** pending compaction tăng liên tục có thể liên quan write amplification và áp lực disk. Nhưng không kết luận cứ pending > 0 là lỗi; kiểm tra mức tăng bền vững, dữ liệu, đồng thời đo throughput và độ trễ foreground.

### 6.5. Bộ metric JMX cần đối chiếu

Theo tài liệu [Cassandra Monitoring](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html), các nhóm đáng theo dõi:

| Tên metric/nhóm | Ý nghĩa khi nghi ghi quá tải |
|---|---|
| `ClientRequest.Write.Latency`, `Timeouts`, `Failures`, `Unavailables` | Coordinator có đang tăng latency và lỗi ghi? |
| `ThreadPools.*.PendingTasks`, `ActiveTasks`, `CurrentlyBlockedTasks` (tên có thể khác) | Loại công việc nào bị ứ đọng? |
| `DroppedMessage.MUTATION.Dropped` và các loại message liên quan | Có thông điệp quá hạn/bị bỏ qua trong giai đoạn đo? |
| `CommitLog.PendingTasks`, `WaitingOnCommit`, `WaitingOnSegmentAllocation` | Commit log có chờ fsync/segment không? |
| `Table.PendingFlushes`, `MemtableLiveDataSize`, `WriteLatency` | Memtable flush có theo kịp tốc độ ghi? |
| `Compaction.PendingTasks`, `Table.PendingCompactions` | Công việc nền có tích tụ? |
| `Storage.TotalHints`, HintsService metrics | Có nhiều hints khi replica bất thường không? |
| OS CPU, GC, disk IOPS/latency, filesystem free, network | Xác định giới hạn tài nguyên vật lý |

Tên metric trong bảng là **nhóm/chỉ dấu tham chiếu**, không nhất thiết là đường JMX đầy đủ trong mọi bản phân phối; xác nhận từ exporter/JMX thực tế. Histogram server và latency ứng dụng đo các giai đoạn khác nhau, nên số đo có thể khác đáng kể.

## 7. Ví dụ Java: giới hạn số mutation in-flight

Java Driver 4.x hỗ trợ API bất đồng bộ; gọi `executeAsync` liên tục không kiểm soát có thể dồn việc sang connection pool và server. Mẫu sau dùng `Semaphore` để **chặn producer khi đã có 32 request đang chờ hoàn tất**.

Ví dụ Java 17+, giả định đã có `CqlSession session`, dữ liệu `events` và môi trường đúng CL. Đây là đoạn minh họa chính sách nạp, không phải một ứng dụng chạy độc lập:

~~~java
import com.datastax.oss.driver.api.core.ConsistencyLevel;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.Semaphore;

record WriteEvent(UUID tenantId, LocalDate dayBucket, UUID eventId,
                  Instant occurredAt, String payload) {}

static void writeBounded(CqlSession session, List<WriteEvent> events)
        throws InterruptedException {
    PreparedStatement ps = session.prepare(
        "INSERT INTO write_overload_lab.events_by_tenant_day " +
        "(tenant_id, day_bucket, event_id, occurred_at, payload) " +
        "VALUES (?, ?, ?, ?, ?)");

    int maxInFlight = 32; // Chỉ là mức thử nghiệm; đo để chọn mức thật.
    Semaphore permits = new Semaphore(maxInFlight);
    ConcurrentLinkedQueue<Throwable> errors = new ConcurrentLinkedQueue<>();

    for (WriteEvent e : events) {
        permits.acquire(); // Chờ chỗ trống thay vì nạp vô hạn vào driver.
        try {
            BoundStatement statement = ps.bind(
                    e.tenantId(), e.dayBucket(), e.eventId(),
                    e.occurredAt(), e.payload())
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(true);

            session.executeAsync(statement).whenComplete((result, error) -> {
                try {
                    if (error != null) errors.add(error);
                    // Ghi latency/error vào metrics của ứng dụng tại đây.
                } finally {
                    permits.release();
                }
            });
        } catch (RuntimeException submissionError) {
            permits.release();
            throw submissionError;
        }
    }

    // Chỉ đúng khi method này là producer duy nhất dùng permits ở trên.
    permits.acquire(maxInFlight);
    permits.release(maxInFlight);
    if (!errors.isEmpty()) {
        throw new IllegalStateException(
            "Có " + errors.size() + " mutation không được xác nhận");
    }
}
~~~

**Giải thích và giới hạn của ví dụ:**

- Một semaphore giữ **giới hạn in-flight**; muốn giữ QPS không quá một ngưỡng, cần thêm **rate limiter/token bucket** phía producer. Hai cơ chế này giải quyết hai đại lượng khác nhau.
- `setIdempotent(true)` trong ví dụ giả định ghi cùng **primary key và dữ liệu bất biến** bằng `INSERT` là phù hợp với ngữ nghĩa nghiệp vụ. Nó không tự biến mọi câu CQL thành idempotent: `UPDATE counter`, timestamp/TTL động, thao tác điều kiện và side effect ngoài Cassandra cần xem riêng.
- Code dùng CL `LOCAL_QUORUM`: giả định RF và tên DC hợp lệ, driver đã thiết lập local datacenter đúng. Không giảm CL để “chữa” overload trước khi hiểu yêu cầu dữ liệu của sản phẩm.
- Trong production, phải giám sát latency, phân loại lỗi và kết hợp deadline, retry budget có jitter, flow control từ HTTP/Kafka và khả năng hủy/quản lý nguồn. Không giữ vô hạn mọi yêu cầu trong RAM nếu downstream đã quá tải.
- Lưu một lỗi dưới tên “không được xác nhận” thay vì “không được ghi” vì mutation có thể đã áp dụng dù client thấy timeout.

Với dữ liệu lớn, thay vì đưa mọi sự kiện vào `List` khổng lồ, producer nên đọc theo streaming/polling có pause/resume; ưu tiên **backpressure ở đầu nguồn** để không biến hàng đợi bộ nhớ của ứng dụng thành điểm sập mới.

## 8. Timeout không đồng nghĩa rollback: retry và tính đúng đắn nghiệp vụ

Xét RF = 3, `LOCAL_QUORUM` cần hai replica phản hồi. Mutation có thể đã được một hoặc nhiều replica áp dụng nhưng coordinator không nhận đủ phản hồi kịp thời. Client nhìn thấy `WriteTimeoutException`; điều này **không chứng minh mutation chưa được ghi**. Gửi lại nguyên request có thể:

- Là điều có thể chấp nhận được với mutation **idempotent**, cùng khóa và giá trị, có chiến lược timestamp/TTL phù hợp.
- Gây tăng sai số với **counter increment**, thay đổi số dư hoặc sự kiện side-effect nếu nghiệp vụ không có idempotency key.
- Gây thứ tự cập nhật không mong muốn khi nhiều writer dùng timestamp khác nhau hoặc xảy ra ghi cạnh tranh.
- Tăng tải thêm lên cluster đang quá tải, kể cả khi mutation đầu tiên về sau hoàn thành.

### 8.1. Phân loại lỗi trước khi hành động

| Kết quả client | Cách diễn giải | Hướng xử lý |
|---|---|---|
| **Success** tại CL yêu cầu | Đã nhận đủ xác nhận theo CL; độ bền fsync còn phụ thuộc cấu hình | Ghi nhận thành công; tiếp tục quan sát chi phí |
| **Write timeout** | Không nhận đủ xác nhận **trước deadline**; kết quả ghi có thể mơ hồ | Kiểm tra idempotency, áp dụng retry budget nhỏ hoặc đối soát khóa |
| **Unavailable** | Không đủ replica được xem là khả dụng để đạt CL trước khi thực thi bình thường | Điều tra node/DC/RF/CL; không spam retry |
| **Write failure** | Replica trả lỗi hoặc hệ thống ghi thất bại trong quá trình xử lý | Điều tra nguyên nhân trước khi gửi lại |
| **Overloaded / quá giới hạn** | Hệ thống từ chối/điều tiết vì vượt ngưỡng ở một lớp xử lý | Giảm tốc nguồn, backoff có jitter, cảnh báo capacity |

Tên exception ở Java driver và cách retry có thể khác theo major version. Một chính sách retry bất cẩn có thể che tình trạng overload và làm tăng p99; theo dõi cả số lần thử, **số mutation logic thành công** và số request vật lý đã gửi.

### 8.2. Hinted handoff và repair không phải công cụ tăng throughput

Khi một replica bị mất kết nối và CL vẫn có thể thành công, **hinted handoff** có thể lưu lời nhắc để gửi lại mutation cho node đó theo cửa sổ/cấu hình hỗ trợ. Nhưng hints không phải hàng đợi vô hạn và không thay thế **anti-entropy repair**; khi quá hạn lưu hints hoặc node mất quá lâu, cần runbook sửa chữa/đồng bộ.

**Repair** chống chênh lệch dữ liệu replica; **compaction** hợp nhất SSTable cục bộ, xử lý nội bộ lưu trữ. Chạy repair diện rộng hoặc major compaction trong lúc đỉnh quá tải thường thêm I/O, có thể làm tình hình xấu hơn. Phải lập lịch theo tài nguyên và trạng thái cụ thể.

## 9. Chẩn đoán từng bước khi p99 ghi tăng

### 9.1. Quy trình điều tra nhanh

1. **Xác định triệu chứng và thời điểm:** QPS được đề nghị, QPS thành công, p50/p95/p99, timeout, error code, thời điểm bắt đầu. Tách lỗi của client, coordinator và replica.
2. **Kiểm tra topology:** `nodetool status` ở nhiều node nếu có góc nhìn khác; xem replica Down, thay đổi DC/rack, RF/CL và tình huống node nóng do partition key.
3. **Đo hàng đợi trên từng node:** `nodetool tpstats` theo nhiều mốc. Chú ý `MutationStage` hoặc tên stage tương ứng, `Pending` và `Blocked`. So sánh coordinator và replica để phân biệt nghẽn gửi mạng với nghẽn ghi cục bộ.
4. **Đi xuống commit log/memtable/compaction:** theo dõi `WaitingOnCommit`, `PendingFlushes`, compaction backlog, disk latency, free space và GC. Tìm nguyên nhân sát tài nguyên.
5. **Xác định phiên bản/cơ chế đang bật:** 3.11 có áp dụng legacy backpressure không, 4.1+/5.x có native transport limiter hay không, client có được thương lượng `THROW_ON_OVERLOAD` không.
6. **Điều tiết nguồn có kiểm soát:** hạ offered load, giới hạn số request in-flight, ngừng retry lan truyền; theo dõi backlog hồi phục và hiệu quả thực tế.
7. **Khắc phục theo nút thắt đã chứng minh:** ví dụ mở rộng tài nguyên disk, chia hot partition, điều chỉnh compaction theo metric hoặc phân phối coordinator; sau đó thử tải lại với cùng workload để xác nhận.

### 9.2. Bảng chẩn đoán

| Hiện tượng quan sát | Giả thuyết ưu tiên | Bằng chứng xác nhận | Động tác ban đầu |
|---|---|---|---|
| p99 tăng, driver pending tăng, Cassandra CPU thấp | Client/connection pool đã thành nút thắt hoặc bị backpressure | Driver metrics, socket/read, offered load | Giảm source QPS/in-flight; kiểm tra pool và deadline |
| `MutationStage.Pending` tăng trên vài replica | Một số replica quá tải, hot partition hoặc disk của node chậm | Per-node disk latency, partition distribution, GC | Giảm tải, kiểm tra partition key/hot key |
| `CommitLog.WaitingOnCommit` tăng, disk fsync chậm | Commit log I/O giới hạn | OS disk queue/fsync, commitlog metrics | Xác minh disk capacity, tránh ép thêm request |
| `PendingFlushes` tăng, memtable lớn | Flush không theo kịp ghi | Memtable/flush metrics, disk throughput | Giảm ingest, kiểm tra flush/disk |
| Compaction backlog tăng sau burst | Công việc nền không hồi phục đủ nhanh | `compactionstats`, SSD utilization, SSTable count | Đánh giá throughput compaction trong cửa sổ ổn định |
| `DroppedMessage.MUTATION` tăng cùng timeout | Message quá hạn/queue hoặc mạng quá tải | Delta dropped, coordinator latency, network | Giảm retry/QPS; tìm node chậm hoặc mạng lỗi |
| Một DC Down, `LOCAL_QUORUM` thất bại | Không đủ replica cục bộ | `nodetool status`, RF per DC | Khôi phục DC, kiểm tra khả năng đáp ứng CL |
| OverloadedException tăng sau bật limiter | Tốc độ vượt chính sách tiếp nhận | QPS mỗi coordinator, cấu hình và flag client | Giảm source rate, cân đối routing/limiter theo capacity |

**Không nên làm ngay:** nâng tất cả thread pool, tắt durability/commit log, vô hạn retry, tăng timeout để che bớt số lỗi, chạy `nodetool repair` hoặc `compact` đồng loạt, hay hạ CL mà chưa thống nhất yêu cầu nhất quán. Các động tác đó có thể chuyển rủi ro từ hiệu năng sang độ bền hoặc tính đúng đắn.

## 10. Chọn cách điều tiết phù hợp với mục tiêu vận hành

### 10.1. Ưu tiên theo lớp tác động

**Lớp 1 — ứng dụng:** giới hạn số in-flight, bớt burst khi consumer lấy từ queue, dùng bounded queue với chính sách rõ ràng khi đầy (chờ/429/503/dead-letter theo nghiệp vụ), dừng retry không cần thiết. Đây là nơi tốt nhất để xác định **ưu tiên nghiệp vụ** và chấp nhận/từ chối có kiểm soát.

**Lớp 2 — driver/coordinator:** kiểm tra connection pool, request timeout, lỗi quá tải và routing; bật native transport limiting đúng nhánh nếu đo được lợi ích. Mục tiêu là tránh đẩy khối lượng vượt năng lực vào executor/replica, đồng thời không chặn nhầm phần tải ưu tiên.

**Lớp 3 — storage/cluster:** nếu disk, flush hoặc compaction là giới hạn, cân đối phần cứng và compaction, xác minh số node/partition/RF và đường ghi commit log. Một cluster có thêm node không tự cải thiện partition key quá nóng, cũng như tăng RF có thể làm write amplification tăng.

### 10.2. Tiêu chí chấp nhận sau thay đổi

Không đánh giá thay đổi qua số `WRITE TIMEOUT` giảm đơn thuần; cần chứng minh:

- Thông lượng mutation logic thành công đáp ứng mục tiêu thực tế, ở CL và cấu hình durability đã chọn.
- p95/p99 ở client nằm trong SLO, gồm thời gian xếp hàng trước driver nếu thuộc trải nghiệm người dùng.
- Lỗi/overloaded rõ ràng và có **giới hạn**, không biến thành hàng đợi vô hạn.
- Pending/blocked tasks, disk/flush/compaction không tăng liên tục dưới tải mục tiêu; khi burst qua đi có thể hồi phục.
- Retry count, duplicate/ambiguous effects và tính nhất quán dữ liệu được kiểm chứng.
- Kết quả lặp lại được theo version/config/schema/seed/workload, cả khi một replica chậm hoặc có GC/compaction nền.

Ví dụ mục tiêu **giả định** cho bài lab: đạt 500 mutation logic/s với p99 ≤ 150 ms, lỗi dưới 0,1% và backlog hồi phục trong 60 giây sau burst. Những ngưỡng này chỉ để học cách đặt SLO; không phải khuyến nghị vận hành chung cho Cassandra.

## 11. Bài tập tình huống

**Tình huống A — hàng đợi càng tăng càng chậm.** Client đẩy 1.800 request/s nhưng cluster chỉ hoàn tất 1.200 request/s khi disk đã bão hòa. Sau 20 giây backlog lý thuyết tăng bao nhiêu nếu không có backpressure/reject/timeout? Tăng timeout gấp đôi có làm disk phục vụ nhanh hơn không?

<details>
<summary>Gợi ý đáp án</summary>

Chênh lệch 600 request/s × 20 giây = **12.000 request chờ** theo mô hình đơn giản. Tăng timeout không làm tăng năng lực disk, chỉ có thể cho request chờ lâu hơn và chiếm tài nguyên lâu hơn.
</details>

**Tình huống B — cấu hình khác phiên bản.** Một tài liệu 3.11 khuyên thử `back_pressure_enabled`; cluster đang dùng 5.0. Có nên dán tham số đó vào `cassandra.yaml`?

<details>
<summary>Gợi ý đáp án</summary>

**Không.** Kiểm tra tài liệu và cấu hình 5.0, vì các khóa legacy 3.11 không được liệt kê trong cấu hình 5.0. Nếu muốn giới hạn native transport, cần nghiên cứu `native_transport_rate_limiting_enabled` và tác động của `THROW_ON_OVERLOAD` đối với driver, thử trong lab và đo cả latency lẫn lỗi.
</details>

**Tình huống C — timeout nhưng dữ liệu vẫn xuất hiện.** Java client nhận write timeout, sau đó truy vấn theo khóa đã thấy giá trị mới. Có mâu thuẫn không? Nên xử lý retry thế nào?

<details>
<summary>Gợi ý đáp án</summary>

Không mâu thuẫn: timeout là thiếu xác nhận trong thời hạn, mutation vẫn có thể được áp dụng. Thiết kế mutation idempotent theo khóa cố định, phân loại lỗi, đối soát khi cần và hạn chế retry bằng backoff/jitter cùng ngân sách hữu hạn.
</details>

**Tình huống D — giảm latency bằng hạ CL.** Cụm RF = 3 đang ghi ở `LOCAL_QUORUM`; một replica chậm làm p99 tăng. Đổi sang `ONE` có phải giải pháp đủ?

<details>
<summary>Gợi ý đáp án</summary>

Đổi CL thay đổi **ngữ nghĩa xác nhận** và có thể giảm thời gian chờ một số thao tác, nhưng không giải quyết replica/disk chậm và có thể trái yêu cầu nhất quán. Cần xác định root cause, capacity và SLA dữ liệu rồi mới quyết định CL với chủ sản phẩm.
</details>

### Checklist hoàn thành lab

- [ ] Đã xác nhận Cassandra version, topology, RF/CL và cấu hình commit log.
- [ ] Nêu được từng điểm có thể tích tụ công việc từ Java client đến flush/compaction.
- [ ] So sánh `Pending`, `Dropped` và p99 trong các cửa sổ tải, tránh dùng một snapshot.
- [ ] Phân biệt native transport rate limit 4.1+/5.x với backpressure legacy 3.11.
- [ ] Chạy thử giới hạn in-flight và/hoặc QPS ở nguồn, đo được tốc độ hồi phục queue.
- [ ] Giải thích được write timeout là kết quả mơ hồ và áp dụng retry có idempotency.
- [ ] Đưa ra quyết định dựa trên SLO, throughput thành công, disk và mức độ bền dữ liệu.

## 12. Tài liệu tham khảo

1. Apache Cassandra — [Storage Engine: commit log, memtables, flush và durability](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html).
2. Apache Cassandra — [Monitoring: ClientRequest, ThreadPool, CommitLog, DroppedMessage, Compaction và Table metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html).
3. Apache Cassandra — [Use Nodetool: status, tpstats, compactionstats](https://cassandra.apache.org/doc/stable/cassandra/troubleshooting/use_nodetool.html).
4. Apache Cassandra — [Cassandra 3.11 cassandra.yaml](https://cassandra.apache.org/doc/3.11/cassandra/configuration/cass_yaml_file.html) và [4.0 cassandra.yaml](https://cassandra.apache.org/doc/4.0/cassandra/configuration/cass_yaml_file.html).
5. Apache Cassandra — [Cassandra 4.1 cassandra.yaml](https://cassandra.apache.org/doc/4.1/cassandra/configuration/cass_yaml_file.html), [5.0 cassandra.yaml](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html) và [Native protocol: THROW_ON_OVERLOAD](https://cassandra.apache.org/doc/stable/cassandra/reference/native-protocol.html).
