# Quản lý transaction log, checkpoint và chính sách giữ nhật ký

## 1. Vì sao transaction log là tài nguyên sống còn của Neo4j?

Trong một hệ thống sử dụng **DATABASE_ENGINE_GRAPH_NEO4J**, ứng dụng Java Driver hoặc Spring Data Neo4j có thể liên tục tạo node **Order**, cập nhật property của **Customer** và ghi relationship giữa các thực thể. Mỗi giao dịch ghi thành công cần được bảo đảm **durability**: nếu tiến trình Neo4j dừng đột ngột, dữ liệu đã commit vẫn phải có khả năng được phục hồi.

Neo4j dùng **transaction log** theo nguyên tắc *write-ahead logging* để ghi lại các thay đổi của giao dịch trước khi chúng được phản ánh đầy đủ vào các tệp lưu trữ graph (*store files*). Khi có sự cố, Neo4j có thể sử dụng log để khôi phục trạng thái nhất quán. Tuy nhiên, giữ log vô hạn sẽ tiêu tốn đĩa, còn giữ quá ít có thể ảnh hưởng đến **backup vi sai**, **cluster catch-up** và **Change Data Capture (CDC)**.

Trong chương **Cấu hình tài nguyên**, bài học này giải quyết năm câu hỏi:

1. **Transaction log** lưu gì, khác **query log**, **debug log** và **Raft log** như thế nào?
2. **Checkpoint** tác động tới phục hồi và khả năng xóa log cũ ra sao?
3. Các thiết lập **rotation size**, **retention policy**, **checkpoint policy** có ý nghĩa gì?
4. Làm thế nào cân đối **dung lượng đĩa**, **RPO/RTO**, **backup**, **CDC** và khả năng đồng bộ cụm?
5. Khi thư mục transaction log tăng nhanh, cần chẩn đoán và xử lý **an toàn** theo những bước nào?

> **Cảnh báo vận hành:** Không tự xóa, di chuyển, nén hoặc thay thế những tệp transaction log đang do Neo4j quản lý để “giải phóng đĩa”. Neo4j cần biết checkpoint nào đã hoàn tất và những log nào còn cần thiết cho recovery. Xóa thủ công không phải cách pruning được hỗ trợ và có thể khiến database không thể phục hồi.

## 2. Transaction log trong vòng đời của một giao dịch

Giả sử dịch vụ tạo một đơn hàng:

~~~cypher
MERGE (o:DemoResourceOrder {orderId: $orderId})
ON CREATE SET o.status = 'CREATED', o.createdAt = datetime()
RETURN o.orderId;
~~~

Trên một database đã cấu hình đúng, một giao dịch ghi thành công có luồng khái niệm:

~~~mermaid
flowchart TD
  A["Ứng dụng gửi giao dịch Cypher"] --> B["Neo4j xử lý thay đổi graph"]
  B --> C["Ghi bản ghi giao dịch vào transaction log"]
  C --> D["Commit thành công / xác nhận cho ứng dụng"]
  D --> E["Các trang store còn có thể cần flush từ page cache"]
  E --> F["Checkpoint hoàn tất: mốc recovery an toàn"]
  F --> G["Pruning các tệp log cũ đủ điều kiện"]
~~~

Sơ đồ là cách nhìn logic, không biểu diễn mọi bước ghi đĩa hay thứ tự xử lý nội bộ của từng phiên bản. Điểm quan trọng:

- **Transaction log** lưu các thay đổi đã được ghi nhận cho database, gồm thông tin cần thiết về thay đổi dữ liệu, index và constraint.
- **Commit thành công** không có nghĩa từng trang store đã được checkpoint ngay lúc trả lời ứng dụng.
- **Checkpoint** buộc những trang dữ liệu còn chờ ghi được đồng bộ ra store và tạo một mốc để recovery không phải bắt đầu từ đầu lịch sử giao dịch.
- **Pruning** là dọn những tệp log **đã xoay vòng** và **không còn cần giữ** theo checkpoint lẫn retention policy.

### 2.1. Khi database gặp sự cố

~~~mermaid
sequenceDiagram
  participant App as Java Driver
  participant DB as Neo4j
  participant Log as Transaction log
  participant Store as Store files
  App->>DB: T1: tạo Order
  DB->>Log: Ghi thay đổi giao dịch
  DB-->>App: T1 commit
  Note over DB,Store: Trang store có thể chưa được flush hết
  DB->>Store: Checkpoint: flush các trang
  Note over DB,Store: Có sự cố sau checkpoint
  DB->>Log: Đọc các bản ghi cần phục hồi
  DB->>Store: Khôi phục tới trạng thái nhất quán
~~~

Nếu sự cố xảy ra **sau commit nhưng trước checkpoint tiếp theo**, transaction log là thành phần cần thiết để đưa store trở về trạng thái có các giao dịch đã commit. **Checkpoint càng cách xa**, công việc phải replay log khi khởi động lại **có thể càng nhiều**. Ngược lại, checkpoint quá dày hoặc quá mạnh có thể tăng áp lực I/O.

**Checkpoint không phải backup.** Nó không tạo ra một bản sao độc lập để khôi phục khi mất toàn bộ ổ đĩa hoặc xóa database. Một backup đã được kiểm thử restore vẫn là thành phần bắt buộc của chiến lược phục hồi sự cố.

## 3. Phân biệt bốn loại log rất dễ nhầm

| Thành phần | Chức năng | Có dùng làm backup độc lập không? | Có nên xóa bằng tay không? |
|---|---|---|---|
| **Transaction log** | Ghi lại thay đổi giao dịch; phục hồi, hỗ trợ backup và cụm | **Không**; cần store/backup và chuỗi phù hợp | **Không** |
| **Query log** | Theo dõi truy vấn, latency, kế hoạch/thông tin phục vụ chẩn đoán | **Không** | Quản lý theo cơ chế log rotation riêng |
| **Debug / server log** | Ghi sự kiện, lỗi, checkpoint, cảnh báo vận hành | **Không** | Dùng chính sách log retention riêng |
| **Raft log** (cluster) | Dữ liệu/trạng thái đồng thuận giữa các thành viên primary | **Không** | **Không** can thiệp thủ công |

Đường dẫn mặc định của transaction log trên Neo4j tự quản lý thường là:

~~~text
<NEO4J_HOME>/data/transactions/<database-name>
~~~

Thư mục gốc có thể thay bằng thiết lập **server.directories.transaction.logs.root**. Trong khi đó, **query/debug/server log** thường nằm dưới thư mục log do **server.directories.logs** kiểm soát. Trên cluster, các thành viên có dữ liệu và log riêng; không giả định tất cả log nằm trong một volume chia sẻ.

**Không giải quyết việc transaction log đầy đĩa bằng cách chỉnh rotation của query log.** Hai loại log có mục đích và cơ chế xóa khác nhau.

## 4. Rotation, checkpoint và pruning: ba cơ chế độc lập nhưng liên quan

### 4.1. Rotation: chuyển sang tệp log mới

Neo4j ghi transaction log thành các tệp nối tiếp. Khi tệp hiện hành đạt ngưỡng kích thước, hệ thống **rotate** và tiếp tục ghi vào tệp mới. Cấu hình:

~~~properties
# neo4j.conf – ví dụ giá trị mặc định trong tài liệu Neo4j hiện hành
db.tx_log.rotation.size=256MiB
~~~

**256 MiB** là ngưỡng xoay vòng mặc định hiện hành, **không phải bảo đảm mọi file luôn đúng tối đa 256 MiB**. Một transaction lớn có thể khiến file vượt ngưỡng trước khi việc rotate diễn ra; hệ thống không chẻ một transaction thành các phần tùy ý chỉ để vừa đúng giới hạn.

Giảm kích thước rotation thường giúp có nhiều tệp nhỏ hơn, nhờ đó chính sách pruning có thể giải phóng không gian theo đơn vị nhỏ hơn. Nhưng nó cũng tạo nhiều file hơn và tăng tần suất rotation. Tăng kích thước tệp có thể giảm số file nhưng khiến **một file lớn không thể được dọn** cho tới khi điều kiện checkpoint và rotation được đáp ứng.

### 4.2. Checkpoint: đặt mốc dữ liệu đã được flush

Checkpoint là quá trình Neo4j flush những thay đổi còn chờ trong page cache sang **store files** và ghi mốc phục hồi. Nó có thể được kích hoạt theo lịch, số transaction, dung lượng log hoặc bởi một số sự kiện vận hành.

Chính sách mặc định hiện hành:

~~~properties
db.checkpoint=PERIODIC
db.checkpoint.interval.time=15m
db.checkpoint.interval.tx=100000
~~~

Trong chính sách **PERIODIC**, Neo4j đánh giá những điều kiện checkpoint theo thời gian và số transaction; khi một ngưỡng thích hợp đạt tới và có dữ liệu cần flush, checkpoint có thể được tiến hành. **15 phút không phải cam kết checkpoint hoàn tất chính xác mỗi 15 phút**: thời gian thực còn phụ thuộc I/O, khối lượng trang bẩn và trạng thái hệ thống.

### 4.3. Pruning: chỉ xóa file đã đủ điều kiện

**Pruning** là cơ chế tự động loại bỏ transaction log cũ. Một tệp log chỉ có thể được dọn an toàn khi các điều kiện nền tảng đã đáp ứng:

1. Tệp đó **đã rotate** và không còn là tệp đang ghi.
2. Có **checkpoint hoàn tất ở tệp log mới hơn**, để recovery không phải phụ thuộc vào tệp cũ.
3. Tệp nằm **ngoài phạm vi cần giữ** theo chính sách retention; các yêu cầu phục vụ backup/cluster cũng phải được xem xét khi thiết kế chính sách.

Neo4j kích hoạt việc đánh giá pruning **sau checkpoint**. Vì vậy, giảm retention từ 7 ngày xuống 2 ngày **không nhất thiết làm dung lượng giảm ngay lập tức**. Nếu checkpoint chưa xảy ra hoặc vẫn nằm trong cùng file lớn, những file nhìn có vẻ “đủ cũ” có thể chưa được thu hồi.

~~~mermaid
flowchart LR
  L0["Log 0: đã rotate"] --> L1["Log 1: đã rotate"]
  L1 --> L2["Log 2: đang ghi"]
  C["Checkpoint mới hoàn tất trong log mới hơn"] --> P{"Log cũ ngoài retention?"}
  P -->|"Có và an toàn"| D["Neo4j tự pruning"]
  P -->|"Chưa"| K["Tiếp tục giữ"]
~~~

**Rotation** chỉ chuyển tệp, **checkpoint** đặt mốc phục hồi, còn **retention** quyết định mức lịch sử muốn giữ. Chỉnh một tham số không thay thế hai cơ chế còn lại.

## 5. Retention policy: giữ bao nhiêu transaction log?

Cấu hình chính là **db.tx_log.rotation.retention_policy**. Giá trị mặc định theo tài liệu Neo4j hiện hành là **2 days 2G**; ở các phiên bản trước có thể khác. Vì vậy, hãy **đọc cấu hình đang có**, không giả định phiên bản đang chạy dùng đúng mặc định của tài liệu mới nhất.

### 5.1. Các dạng chính sách thường gặp

| Giá trị trong neo4j.conf | Ý nghĩa | Lưu ý |
|---|---|---|
| **2 days 2G** | Giữ log theo khoảng thời gian **tối đa khoảng 2 ngày** và giới hạn không gian log khoảng **2 GiB** theo cơ chế pruning | Không bảo đảm đủ 48 giờ khi tải ghi cao |
| **7 days** | Giữ những log chứa transaction nằm trong phạm vi 7 ngày theo chính sách thời gian | Dung lượng có thể rất lớn nếu ghi dày |
| **10 files** | Giữ số lượng tệp log gần nhất theo cơ chế pruning | Cửa sổ thời gian thay đổi theo tốc độ ghi |
| **500M size** | Giữ một lượng file log theo ngưỡng dung lượng 500 MiB | Không suy trực tiếp ra được số giờ lịch sử |
| **500k txs** | Giữ lịch sử xấp xỉ 500 nghìn transaction gần nhất theo các file log | Số byte có thể biến thiên mạnh |
| **keep_all** hoặc **true** | Không tự pruning theo thời gian/số lượng thông thường | Dễ tăng không giới hạn, không phù hợp mặc định production |
| **keep_none** hoặc **false** | Chỉ giữ mức tối thiểu, gồm log không rỗng mới nhất cần thiết | Có thể làm mất khả năng backup vi sai/catch-up hiệu quả |

**Chú ý cú pháp:** mẫu **2 days 2G** có thành phần thời gian và giới hạn dung lượng. Không viết tùy ý **2 years 2G** rồi mong được hỗ trợ; các loại đơn vị và tổ hợp hợp lệ phụ thuộc phiên bản. Một số bản phát hành từ **2026.04** bổ sung dạng policy mới liên quan backup, vì vậy phải xem **validValues** của server trước khi áp dụng cú pháp không có trong bản đang chạy.

### 5.2. Vì sao “2 days 2G” không hứa giữ đủ hai ngày?

Giả sử ứng dụng ghi trung bình **1 GiB transaction log mỗi giờ**. Nếu đặt **2 days 2G**, dung lượng log cần để giữ 48 giờ ở tốc độ này sẽ khoảng **48 GiB** trước khi tính overhead; giới hạn 2 GiB khiến phần lịch sử cũ có thể bị pruning **sớm hơn 48 giờ**. Còn nếu database gần như không ghi, lượng log giữ có thể rất ít về byte.

Điều kiện thời gian và dung lượng phải được đọc như **giới hạn chính sách**, không phải SLA bảo đảm log luôn truy vấn được ngược đúng 48 giờ hoặc luôn chiếm đúng 2 GiB. Số byte thực còn bị ảnh hưởng bởi tệp đang ghi, kích thước rotation, checkpoint, những transaction lớn và thời điểm pruning.

### 5.3. Keep-all và keep-none đều có rủi ro

**keep_all** nghe có vẻ an toàn cho phục hồi, nhưng không phải giải pháp backup: ổ đĩa có thể đầy, database có thể dừng ghi, và mất volume vẫn làm mất cả store lẫn log. Những file log đã rotate cũng không được tự ý đem đi lưu trữ rồi xóa bằng công cụ bên ngoài; quá trình pruning cần hiểu mốc checkpoint.

**keep_none** có thể giảm không gian, nhưng các hệ thống dùng **differential backup**, **cluster catch-up** hoặc **CDC** có thể cần đọc lịch sử transaction lâu hơn mức tối thiểu để phục hồi hoặc đồng bộ. Trong môi trường Neo4j Enterprise production, không bật keep_none nếu chưa chứng minh được quy trình backup/phục hồi và phụ thuộc khác vẫn đạt yêu cầu.

## 6. Các thiết lập cần biết và ảnh hưởng tài nguyên

| Setting | Vai trò | Giá trị mặc định trong tài liệu hiện hành |
|---|---|---|
| **db.tx_log.rotation.size** | Ngưỡng xoay vòng tệp transaction log | **256 MiB** |
| **db.tx_log.rotation.retention_policy** | Lịch sử log cần giữ sau pruning | **2 days 2G** |
| **db.tx_log.preallocate** | Thử cấp phát trước dung lượng file log để hạn chế phân mảnh và thiếu chỗ | **true** |
| **server.directories.transaction.logs.root** | Thư mục gốc đặt transaction logs | Phụ thuộc vị trí data directory |
| **db.checkpoint** | Chiến lược kích hoạt checkpoint | **PERIODIC** |
| **db.checkpoint.interval.time** | Ngưỡng thời gian đối với PERIODIC | **15m** |
| **db.checkpoint.interval.tx** | Ngưỡng số transaction đối với PERIODIC | **100000** |
| **db.checkpoint.interval.volume** | Ngưỡng dung lượng log khi dùng VOLUME | **250 MiB** |
| **db.checkpoint.iops.limit** | Giới hạn I/O checkpoint theo mức cố gắng tối đa, áp dụng trong Enterprise | **600** |

Các giá trị trên nhằm cung cấp mốc tham khảo của tài liệu Neo4j hiện hành. **Kiểm tra chính server/edition đang vận hành** vì giá trị, tên setting hoặc chính sách có thể đổi theo version.

### 6.1. Những chế độ checkpoint

| Chế độ | Cơ chế | Phù hợp khi |
|---|---|---|
| **PERIODIC** | Dựa trên ngưỡng thời gian và số transaction | Lựa chọn mặc định, đủ cho nhiều hệ thống |
| **VOLUME** | Dựa trên lượng transaction log phát sinh | Muốn ràng buộc nhịp checkpoint theo lượng ghi |
| **CONTINUOUS** | Thực hiện checkpoint liên tục, **Enterprise Edition** | Workload đặc thù cần điều chỉnh I/O và thời gian recovery |
| **VOLUMETRIC** | Điều chỉnh checkpoint/pruning theo lượng log có thể dọn, **Enterprise Edition** | Workload có mục tiêu giữ dung lượng log sát chính sách |

**Không có chính sách tốt nhất cho mọi database.** Checkpoint thường xuyên hơn có thể giảm lượng log phải replay sau crash và kích hoạt pruning sớm hơn, nhưng tạo thêm flush I/O. Checkpoint thưa hơn có thể giảm áp lực I/O ngắn hạn nhưng làm tăng khối lượng recovery và lượng log tồn tại giữa hai checkpoint.

### 6.2. Giới hạn I/O checkpoint

Trong Neo4j Enterprise Edition, **db.checkpoint.iops.limit** giới hạn số thao tác I/O nền mà checkpoint cố gắng tiêu thụ mỗi giây. Giới hạn quá thấp có thể khiến checkpoint rất lâu, để log tích lũy nhiều hơn và tăng thời gian khôi phục. Giới hạn quá cao có thể khiến việc flush cạnh tranh I/O với truy vấn.

Từ **Neo4j 2025.07**, có thêm **db.checkpoint.throughput.limit**, giới hạn tốc độ flush theo byte/giây khi được hỗ trợ. Không sao chép tham số này vào bản Neo4j cũ hơn; với Neo4j Community, cơ chế điều tiết I/O checkpoint có thể không được áp dụng như Enterprise.

Trước khi chỉnh các ngưỡng, hãy đo **thời lượng checkpoint**, **số trang/byte đã flush**, **log append rate**, **I/O disk**, **p95 truy vấn** và **khả năng phục hồi**. Đừng tăng IOPS chỉ vì muốn xóa file nhanh, khi nguyên nhân thực là writer liên tục tạo log với tốc độ vượt dung lượng dự trữ.

## 7. Thiết kế retention dựa trên yêu cầu phục hồi và đồng bộ

Để chọn policy, không chỉ hỏi “ổ đĩa còn bao nhiêu?”. Cần xác định các hệ thống sử dụng lịch sử transaction:

| Phụ thuộc | Cần giữ log để làm gì? | Rủi ro nếu pruning quá sớm |
|---|---|---|
| **Crash recovery** | Replay các giao dịch đã commit nhưng chưa được phản ánh hoàn toàn trong store | Thiếu log cần thiết để mở database nhất quán |
| **Backup vi sai** | Lấy thay đổi kể từ lần backup trước, thay vì sao chép lại toàn bộ store | Chuỗi thay đổi không còn sẵn có; có thể phải backup full lại hoặc thao tác thất bại |
| **Cluster catch-up** | Thành viên bị tụt hậu nhận các transaction chưa áp dụng | Thành viên có thể cần quy trình copy/store seeding nặng hơn |
| **CDC consumer** | Đọc các thay đổi chưa kịp tiêu thụ từ transaction log đã được enrich | Cursor/change ID trỏ vào lịch sử đã bị pruning |
| **Phân tích sự cố** | Có thời gian điều tra và xác định khoảng giao dịch liên quan | Thiếu lịch sử để đối soát hoặc phục hồi theo khả năng của hệ thống |

**Retention không tự tạo khả năng point-in-time recovery (PITR).** Khôi phục tới một thời điểm/transaction cụ thể cần một **backup hợp lệ**, chuỗi backup và những log có thể replay, cùng công cụ restore được phiên bản/edition hỗ trợ. Chỉ giữ transaction log trên cùng ổ với database không bảo vệ khỏi mất volume hoặc hư hỏng vật lý.

### 7.1. RPO, RTO và transaction log

- **RPO (*Recovery Point Objective*)**: mức dữ liệu tối đa nghiệp vụ chấp nhận mất khi xảy ra thảm họa.
- **RTO (*Recovery Time Objective*)**: thời gian tối đa để dịch vụ được khôi phục hoạt động.
- **Checkpoint** thường tác động đến lượng thao tác replay khi crash, từ đó ảnh hưởng RTO.
- **Backup cadence, khả năng truy cập bản backup và log chain** tác động tới điểm có thể phục hồi sau thảm họa, từ đó ảnh hưởng RPO.
- **Transaction log retention** phải đủ cho các backup/consumer dựa vào log, nhưng **không thay thế backup**.

Ví dụ: đặt **db.tx_log.rotation.retention_policy=7 days** không có nghĩa hệ thống tự có backup 7 ngày hoặc khôi phục được mọi giây trong 7 ngày. Nếu không từng tạo một bản backup dùng được, retention dài cũng không giải quyết mất toàn bộ store.

### 7.2. Ước lượng ngân sách dung lượng

Một cách tính **sơ bộ để lập kế hoạch**, không phải quy tắc sizing chính thức:

\[
\text{Log budget} \approx
\text{Peak log rate} \times
\text{Required retention window}
\times \text{Headroom factor}
\]

Ví dụ, nếu hệ thống phát sinh **1,5 GiB log/giờ** vào giai đoạn cao điểm, phụ thuộc xa nhất cần **24 giờ** lịch sử, và nhóm vận hành chọn hệ số dự phòng **1,5**:

\[
1{,}5 \times 24 \times 1{,}5 = 54\;\text{GiB}
\]

**54 GiB là ví dụ tính toán**, không phải kích thước bắt buộc của Neo4j. Cần điều chỉnh theo thực tế: log rate có thể đột biến, kích thước transaction không đồng đều, CDC log enrichment làm log lớn hơn, còn checkpoint và rotation khiến dung lượng sử dụng dao động. Cũng phải dành riêng ngân sách cho **store files, index, backup staging, hệ điều hành và log khác**.

### 7.3. Hai tình huống lựa chọn chính sách

**Tình huống A — Hệ thống độc lập, backup hằng ngày:** nếu backup có thể bị trễ một ngày và lưu lượng ghi lớn, chính sách chỉ **2 days 2G** có thể không giữ được dữ liệu đủ dài cho backup vi sai tiếp theo. Hãy đo lượng log phát sinh giữa **hai lần backup thành công**, bổ sung ngân sách chờ khi backup lỗi, rồi chọn retention phù hợp với SLA và dung lượng.

**Tình huống B — Cluster + CDC:** nếu CDC downstream có thể dừng **36 giờ**, còn một thành viên cluster có thể cần catch-up sau **48 giờ**, policy chỉ giữ khoảng **1 ngày** là quá ngắn cho các phụ thuộc này. Nhu cầu giữ log phải xét **khoảng chờ lớn nhất** kết hợp lưu lượng đỉnh và giới hạn disk; nếu không thể tăng storage, cần thay đổi phương án backup/consumer/catch-up, không chỉ rút ngắn retention.

Với CDC, lưu ý **CDC cần được bật/enrich** trên database có hỗ trợ. Khi được bật, CDC thường tăng số byte ghi vào transaction log, khiến log rotate/prune nhanh hơn ở policy có giới hạn dung lượng. Nếu change ID của consumer đã nằm ngoài phạm vi log còn giữ, không thể tự giải quyết bằng cách chạy lại query cũ mà không có kế hoạch **resnapshot/reseed** thích hợp.

## 8. Kiểm tra cấu hình thực tế bằng Cypher

### 8.1. SHOW SETTINGS là bước quan sát an toàn

Trên Neo4j tự quản lý, với quyền xem cấu hình:

~~~cypher
SHOW SETTINGS
YIELD name, value, defaultValue, isDynamic
WHERE name STARTS WITH 'db.tx_log.'
   OR name STARTS WITH 'db.checkpoint'
   OR name = 'server.directories.transaction.logs.root'
RETURN name, value, defaultValue, isDynamic
ORDER BY name;
~~~

Kết quả cho biết **giá trị hiện hành** trên **server đang thực thi lệnh**, khác với việc chỉ đọc file **neo4j.conf**. Cột **isDynamic** giúp xác định setting có thể đổi trong runtime trên môi trường được hỗ trợ hay không.

**Lưu ý phân quyền và môi trường:**

- **SHOW SETTINGS** cần quyền phù hợp; một user ứng dụng bình thường có thể không xem được mọi setting.
- Lệnh này **không khả dụng trên Aura** theo tài liệu quản trị hiện hành; Aura quản lý tài nguyên và nhiều tham số vận hành bên dưới dịch vụ.
- Trong **cluster**, lệnh hiển thị cấu hình của **server thực thi**. Nếu cần so sánh từng thành viên, quản trị viên nên kết nối trực tiếp đúng server theo cách được hỗ trợ để kiểm tra không lệch cấu hình.

### 8.2. Ví dụ neo4j.conf cho môi trường thử nghiệm

~~~properties
# Ví dụ tùy chỉnh. KHÔNG mặc định sao chép vào production.
db.tx_log.rotation.size=256MiB
db.tx_log.rotation.retention_policy=7 days

db.checkpoint=PERIODIC
db.checkpoint.interval.time=15m
db.checkpoint.interval.tx=100000
~~~

Đây là **một cấu hình minh họa**; chọn 7 ngày chỉ sau khi tính được log rate và phụ thuộc backup/catch-up/CDC. Tùy chính sách tổ chức, có thể dùng retention kết hợp thời gian–dung lượng, nhưng giới hạn dung lượng phải đủ lớn để không cắt ngắn cửa sổ thời gian cần thiết.

Không đặt **server.directories.transaction.logs.root** sang ổ khác chỉ vì nghe “nhanh hơn”. Nếu đặt log trên storage riêng, cần bảo đảm độ tin cậy, latency, băng thông, khả năng đồng bộ backup và phục hồi toàn bộ bộ dữ liệu. Mất một trong hai volume **store/log** có thể phá vỡ khả năng mở database.

### 8.3. Thay đổi động (Enterprise Edition)

Một số tham số như **db.tx_log.rotation.retention_policy** và **db.tx_log.rotation.size** được đánh dấu **Dynamic**. Trong **Neo4j Enterprise Edition**, quản trị viên có thể thay đổi một setting dynamic khi server đang chạy:

~~~cypher
// Ví dụ dành riêng môi trường thử nghiệm và tài khoản quản trị.
CALL dbms.setConfigValue(
  'db.tx_log.rotation.retention_policy',
  '7 days'
);
~~~

Tuy nhiên:

1. Lệnh dynamic này ảnh hưởng **server được gọi**, **không tự lan truyền** tới mọi thành viên cluster.
2. Thay đổi runtime **không tự được ghi bền vững** vào **neo4j.conf**. Phải cập nhật cấu hình triển khai tương ứng, nếu không giá trị có thể trở lại như cũ sau restart.
3. Thay đổi sang thời gian giữ **ngắn hơn** có thể khiến các log cũ được pruning ở checkpoint tiếp theo; quyết định này có thể **không đảo ngược được**.
4. Với setting không được phép đổi động, phải dùng quy trình cấu hình/restart được hỗ trợ thay vì cố gọi thủ tục.

**Thực hành an toàn:** bắt đầu bằng **SHOW SETTINGS** và đánh giá nhu cầu, thực hiện thay đổi trên staging, sau đó triển khai qua hệ thống quản lý cấu hình với phê duyệt và kiểm chứng từng server.

## 9. Kích hoạt checkpoint thủ công: chỉ khi có lý do

Neo4j cung cấp thủ tục:

~~~cypher
CALL db.checkpoint();
~~~

Thủ tục này yêu cầu quyền thực thi thích hợp và có thể gây **I/O flush đáng kể** nếu hệ thống có nhiều trang bẩn. Nó có thể giúp quan sát việc checkpoint hoàn tất và sau đó kích hoạt điều kiện pruning, nhưng **không bảo đảm dung lượng lập tức giảm** khi những file đang giữ vẫn chưa đủ điều kiện xóa.

Đừng chạy liên tục **CALL db.checkpoint()** trong production để chữa log đầy đĩa mà chưa kiểm tra:

- Log có đang được ghi cực nhanh do import hoặc batch không?
- Retention policy có cần giữ vì backup/CDC/cluster không?
- Tệp log đã rotate hay chưa?
- Checkpoint trước đó có đang chậm hoặc thất bại vì I/O không?
- Disk còn đủ khoảng trống an toàn để tiếp tục commit, rotate và flush không?

Nếu database có sự cố thiếu log hoặc không thể phục hồi, thủ tục checkpoint **không phải** cách tạo lại những transaction đã mất.

## 10. Giám sát transaction log, checkpoint và dung lượng

Theo dõi đồng thời các phép đo từ **filesystem**, **Neo4j metrics** và **backup/CDC jobs**.

| Tín hiệu | Điều cần biết | Tình huống cảnh báo |
|---|---|---|
| **Disk free / used** ở volume log | Còn đủ dung lượng cho peak writes và rotation? | Free space giảm nhanh, nguy cơ đầy disk |
| **Transaction log bytes appended** | Tốc độ sinh log theo giờ/ngày | Lưu lượng log tăng bất thường so với baseline |
| **Log rotation events / duration** | Số lần rotate và thời gian thao tác | Rotate liên tục, latency tăng |
| **Checkpoint events / duration** | Checkpoint có chạy và hoàn tất đều? | Khoảng cách checkpoint lớn, duration tăng |
| **Checkpoint bytes flushed / I/O limiter** | Áp lực flush đối với disk | Checkpoint thường xuyên bị throttling hoặc đĩa bão hòa |
| **Last committed tx ID** | Thành viên đang tiến tới đâu trên chuỗi transaction | Một thành viên cluster tụt hậu lâu |
| **Lowest available committed tx ID** | Cửa sổ transaction còn sẵn có trong log, trên bản hỗ trợ metric | Khoảng còn lại không đủ cho backup/catch-up |
| **Backup age + result** | Lần backup thành công gần nhất và chuỗi backup còn dùng được | Backup lỗi nhiều kỳ liên tiếp |
| **CDC lag / cursor** | Consumer chậm bao xa so với các thay đổi đã commit | Cursor có nguy cơ rơi khỏi cửa sổ log |

Trong Neo4j Enterprise, **metrics** có thể xuất qua hệ thống giám sát được hỗ trợ. Tên metric tham khảo gồm **log.appended_bytes**, **log.rotation_events**, **check_point.duration**, **check_point.events**, **transaction.last_committed_tx_id**; prefix và khả năng cung cấp tùy bản/edition. **transaction.lowest_available_committed_tx_id** được giới thiệu ở các phiên bản hiện đại, không giả định tồn tại trên mọi server.

### 10.1. Chẩn đoán qua log checkpoint

Neo4j ghi các sự kiện **checkpoint started/completed** và số liệu như thời lượng, lượng trang đã flush, I/O được giới hạn vào các log vận hành thích hợp. Dùng chúng để phân biệt:

- **Không có checkpoint mới:** cần xem policy, tình trạng dịch vụ, quyền I/O hoặc log.
- **Checkpoint chạy rất lâu:** có thể do tốc độ ghi cao, ổ đĩa chậm hoặc giới hạn IOPS quá thấp.
- **Checkpoint hoàn tất nhưng log vẫn nhiều:** retention vẫn yêu cầu giữ, một file lớn chưa đủ điều kiện pruning, hoặc lượng ghi mới bù phần được dọn.
- **Log tăng cùng lúc bật CDC:** enrichment có thể làm lượng dữ liệu ghi vào log tăng; cần cập nhật sizing.

Nếu log checkpoint thất bại, hoặc storage trả lỗi, ưu tiên bảo vệ dữ liệu và điều tra hạ tầng thay vì thử xóa file.

## 11. Runbook: thư mục transaction log tăng bất thường

Khi nhận cảnh báo log volume sắp đầy, sử dụng quy trình có điều kiện:

~~~mermaid
flowchart TD
  A["Cảnh báo transaction log tăng / disk free thấp"] --> B["Xác nhận đúng volume và database"]
  B --> C["Đo tốc độ ghi log, rotation, checkpoint"]
  C --> D{"Checkpoint có hoàn tất?"}
  D -->|"Không"| E["Điều tra lỗi I/O, thời gian flush, giới hạn tài nguyên"]
  D -->|"Có"| F{"Retention có giữ log cho backup/CDC/cluster?"}
  F -->|"Có"| G["Kiểm tra backup/consumer lag và mở rộng tài nguyên khi cần"]
  F -->|"Không hoặc cấu hình sai"| H["Đánh giá policy mới trên staging và triển khai có kiểm soát"]
  E --> I["Khôi phục năng lực vận hành theo runbook đã duyệt"]
  G --> I
  H --> I
  I --> J["Đối soát backup, recovery và cảnh báo sau thay đổi"]
~~~

### Bước 1 — Xác nhận sự cố

Xác định **database**, server/cluster member, đường dẫn transaction log, volume và tỷ lệ tăng dung lượng. Phân biệt log của database nào với **query/debug log**, backup staging hoặc dữ liệu Raft. Nếu có nhiều database, mỗi database có lượng log riêng, nên không lấy tổng dung lượng toàn server làm bằng chứng một database gặp lỗi.

### Bước 2 — Đọc cấu hình và tình trạng backup

Chạy **SHOW SETTINGS** với nhóm **db.tx_log**, **db.checkpoint**. Xem chính sách có bị thay sau đợt deploy không; xác nhận **backup thành công gần nhất**, lịch backup tiếp theo, yêu cầu **CDC** và trạng thái thành viên cụm. Không hạ retention trước khi trả lời được “ai còn cần những log sắp bị dọn?”.

### Bước 3 — Kiểm tra rotation và checkpoint

Đối chiếu **log appended rate**, kích thước rotation, log checkpoint gần nhất, thời gian checkpoint và lượng bytes flush. Nếu checkpoint chưa hoàn tất, giảm retention không tự giải phóng log ngay.

### Bước 4 — Chọn hành động ít rủi ro

- **Nếu log tăng do workload vừa bùng phát:** điều tiết batch/import, cân nhắc giảm concurrency ghi hoặc tăng storage có kiểm soát.
- **Nếu checkpoint bị nghẽn I/O:** điều tra disk latency, giới hạn throughput/IOPS, page cache và tải truy vấn; không ép checkpoint liên tục.
- **Nếu retention dài hơn nhu cầu thực:** sau khi kiểm tra backup/CDC/cluster, thay đổi policy có phê duyệt, lên lịch và theo dõi pruning.
- **Nếu backup/CDC đã vượt cửa sổ log:** xử lý **backup full lại** hoặc **resnapshot/reseed** theo quy trình được hỗ trợ; kéo dài retention **sau khi log đã bị pruning** không phục hồi các transaction cũ.
- **Nếu ổ đĩa sắp đầy nghiêm trọng:** kích hoạt runbook sự cố storage và backup, có thể tạm ngừng workload ghi theo quyền vận hành; **không xóa file transaction log thủ công**.

### Bước 5 — Kiểm tra sau xử lý

Xác nhận database vẫn đọc/ghi được, transaction commit không lỗi, checkpoint hoàn tất, dung lượng log ổn định hơn, backup tiếp theo thành công và các consumer/cluster member không mất khả năng bắt kịp. Lưu lại thay đổi cấu hình và số liệu trước–sau để đưa vào bài kiểm thử hồi quy vận hành.

## 12. Thử nghiệm thay đổi policy trước production

Một môi trường thử nghiệm có lưu lượng gần thực tế giúp đánh giá không chỉ tổng byte log mà cả ảnh hưởng tới recovery và backup.

### 12.1. Tạo workload ghi có kiểm soát

Trên database thử nghiệm, tạo constraint:

~~~cypher
CREATE CONSTRAINT demo_resource_order_unique IF NOT EXISTS
FOR (o:DemoResourceOrder)
REQUIRE o.orderId IS UNIQUE;
~~~

Chạy một tập tham số định danh được kiểm soát bằng Java Driver hoặc công cụ tải, ví dụ:

~~~cypher
UNWIND $orderIds AS orderId
MERGE (o:DemoResourceOrder {orderId: orderId})
ON CREATE SET
  o.status = 'CREATED',
  o.createdAt = datetime()
SET o.lastMeasuredAt = datetime();
~~~

Ở đây **$orderIds** là danh sách ID từ bộ phát tải, không phải giá trị tùy ý nhập từ người dùng. **MERGE** tránh tạo trùng node theo ID khi chạy lại, nhưng **SET o.lastMeasuredAt** vẫn sinh thay đổi khi lệnh chạy và thuộc tính đổi. Để so sánh chính xác log rate, kiểm soát số batch, số transaction, tổng thời gian và kích thước dữ liệu tương đương giữa các lần thử.

Không chạy bài tạo tải trong production hoặc trên một Neo4j Aura không có quyền vận hành tài nguyên tương ứng.

### 12.2. Ma trận thử nghiệm

| Thử nghiệm | Quan sát | Tiêu chí đánh giá |
|---|---|---|
| **Retention cũ vs mới** | Lượng log sau các checkpoint | Không mất cửa sổ cần thiết cho backup/CDC/catch-up |
| **Rotation 256MiB vs khác** | Số file, tần suất rotate, pruning | Không tăng overhead không cần thiết |
| **Checkpoint PERIODIC vs VOLUME** | Duration, log growth, p95 truy vấn | Cân đối recovery và áp lực I/O |
| **Backup vi sai sau chậm trễ** | Backup có tiếp tục được không? | Chuỗi backup hợp lệ, không bắt buộc full bất ngờ |
| **Restart sau crash được mô phỏng an toàn** | Thời gian recovery và dữ liệu đã commit | Không mất dữ liệu đã được xác nhận commit |
| **CDC consumer tạm dừng** | Có đọc tiếp được từ cursor cũ? | Không vượt retention theo SLA |
| **Cluster member offline có kiểm soát** | Catch-up khi quay lại | Không phải store copy ngoài dự tính |

Các bài thử **crash**, **failover** hoặc **ngắt thành viên** chỉ được thực hiện trong môi trường cô lập có phương án khôi phục và sự cho phép của người vận hành. Không cố tình giết tiến trình Neo4j production để đo checkpoint.

### 12.3. Đối soát dữ liệu sau restart

~~~cypher
MATCH (o:DemoResourceOrder)
RETURN count(o) AS totalOrders;
~~~

~~~cypher
MATCH (o:DemoResourceOrder)
WHERE o.orderId IS NULL
RETURN count(o) AS missingIds;
~~~

Hai câu trên chỉ cung cấp **một phần bằng chứng**. Kiểm tra thêm các **orderIds đã được ứng dụng xác nhận commit**, property và relationship mong đợi, số giao dịch lỗi, thông báo recovery và tính đầy đủ của backup. Count đúng chưa đủ nếu node bị đổi thông tin hoặc thiếu liên kết.

## 13. Tương thích phiên bản, cluster và dịch vụ quản lý

### 13.1. Neo4j 4.x, 5.x và bản năm–tháng

Các ví dụ setting trong bài hướng tới **Neo4j 5 và các phiên bản hiện hành**. Một số phiên bản cũ (đặc biệt Neo4j 4.x) có **tên setting khác** như nhóm **dbms.tx_log...**. Khi nâng cấp, không copy nguyên file **neo4j.conf** cũ rồi giả định tất cả tên vẫn hợp lệ.

Trình tự phù hợp:

1. Xem **version source/target** và migration guide.
2. Tra bảng **changed/removed settings** và cú pháp retention hợp lệ.
3. Dùng **SHOW SETTINGS** hoặc tài liệu cấu hình của server đích để xác nhận.
4. Chạy staging với dữ liệu/khối lượng ghi tương tự.
5. Chỉ áp dụng cấu hình trên production sau khi đã đối soát backup/restore, checkpoint và log retention.

### 13.2. Cluster cần kiểm soát từng thành viên

Giá trị thay đổi runtime có thể chỉ tác động **một server**. Nếu các thành viên có retention khác nhau, khả năng phục vụ **catch-up**, backup và CDC có thể không đồng nhất. Mỗi thành viên cần cấu hình theo quy định của cluster và bộ kiểm tra drift.

**Transaction log và Raft log không phải một.** Tăng retention của transaction log không tự thay cấu hình prune Raft, và xóa Raft log bằng tay không phải cách giải quyết sự cố transaction log.

### 13.3. Docker và Aura

Trong Docker Neo4j, cấu hình có thể được cung cấp bằng **neo4j.conf**, image được quản lý hoặc biến môi trường. Khi chuyển tên setting sang biến môi trường, dấu gạch dưới trong **tên gốc** cần escaping theo quy tắc của image Neo4j; không đoán tên biến bằng cách thay mọi dấu chấm bằng một gạch dưới nếu tên setting có dấu gạch dưới.

Với **Aura**, nhiều cấu hình transaction log và checkpoint do nền tảng quản lý; người dùng không có cùng quyền can thiệp **neo4j.conf**, filesystem hoặc checkpoint như server tự quản lý. Hãy dựa trên SLA, khả năng backup/restore và tài liệu Aura tương ứng, không cố áp dụng runbook xóa file hoặc thay setting ở cấp OS.

## 14. Các ngộ nhận phổ biến

1. **“Commit thành công thì store file đã checkpoint.”** Sai; durability và flush store có các mốc vận hành khác nhau.
2. **“Checkpoint là backup.”** Sai; checkpoint không tạo bản sao độc lập khỏi ổ đĩa hiện tại.
3. **“Rotation sẽ xóa file cũ.”** Sai; rotation chuyển tệp, còn pruning cần checkpoint và chính sách retention.
4. **“2 days 2G bảo đảm đúng 48 giờ.”** Sai; giới hạn dung lượng có thể cắt ngắn cửa sổ lịch sử.
5. **“Hạ retention xong là giải phóng disk ngay.”** Chưa chắc; log chỉ được dọn ở thời điểm và điều kiện an toàn.
6. **“Log cũ thì xóa bằng rm/Explorer được.”** Sai; không được Neo4j hỗ trợ và có thể phá hỏng khả năng recovery.
7. **“Giữ tất cả log là đã có backup.”** Sai; mất volume sẽ mất cả database và log.
8. **“keep_none luôn là cấu hình tối ưu.”** Sai; có thể phá vỡ kế hoạch backup vi sai, CDC hoặc catch-up.
9. **“Tăng checkpoint vô hạn sẽ luôn tăng tốc.”** Sai; checkpoint cũng dùng tài nguyên I/O và có thể gây tranh chấp với truy vấn.
10. **“SHOW SETTINGS của một server đại diện cho cả cluster.”** Sai; phải xét từng server và cấu hình triển khai.
11. **“Query log và transaction log là cùng một thứ.”** Sai; mục tiêu và chính sách xoay vòng khác nhau.
12. **“Tăng retention sau khi CDC mất cursor sẽ lấy lại dữ liệu cũ.”** Sai; log đã bị pruning không được tạo lại bởi việc thay cấu hình.
13. **“Tắt db.recovery.fail_on_missing_files là sửa được database.”** Sai; bỏ kiểm tra log thiếu có thể gây rủi ro toàn vẹn dữ liệu, không phải phương pháp recovery chuẩn.

## 15. Bài tập vận dụng

### Bài 1 — Phân loại log

Một máy Neo4j có dung lượng **debug.log** tăng nhanh, còn một database khác có nhiều tệp trong **data/transactions**. Hãy giải thích vì sao hai vấn đề cần chính sách và công cụ chẩn đoán khác nhau, và chỉ ra loại log nào cần cho crash recovery.

### Bài 2 — Retention không đủ backup window

Hệ thống phát sinh trung bình **800 MiB transaction log/giờ**, backup vi sai mỗi **12 giờ** nhưng thỉnh thoảng gián đoạn **24 giờ**. Đánh giá rủi ro khi giữ policy **2 days 2G**. Đề xuất các phép đo, cửa sổ retention và headroom cần xem xét, không đưa ra cấu hình cố định khi chưa có kích thước đĩa và SLA.

### Bài 3 — Rotation, checkpoint và pruning

Giả sử Log 4 đã rotate, Log 5 đang ghi, checkpoint gần nhất nằm trong Log 4. Có thể xóa Log 4 ngay không? Phải chờ điều kiện nào để pruning an toàn? Sau khi tạo checkpoint trong Log 5 nhưng policy yêu cầu giữ thêm lịch sử, Log 4 có tự bị xóa ngay không?

### Bài 4 — Cấu hình động

Một quản trị viên trong cluster thay retention trên server A bằng **dbms.setConfigValue**, sau đó server A restart và hiện lại giá trị cũ. Giải thích hai nguyên nhân: tính **per-server** và việc **thay đổi runtime không tự ghi vào neo4j.conf**. Thiết kế bước kiểm tra drift.

### Bài 5 — CDC consumer tụt hậu

Consumer CDC dừng 30 giờ nhưng log chỉ còn đủ khoảng 12 giờ lịch sử do giới hạn dung lượng. Hãy xác định rủi ro với cursor cũ, quy trình resnapshot/reseed phù hợp và cách chọn retention mới.

### Bài 6 — Checkpoint gây chậm truy vấn

Sau khi giảm ngưỡng checkpoint, thời lượng recovery test giảm nhưng p95 truy vấn production tăng. Hãy nêu những số liệu cần thu thập để xem checkpoint có đang chiếm băng thông I/O hay không. Có nên tăng **db.checkpoint.iops.limit** vô hạn không?

### Bài 7 — Viết runbook an toàn

Dung lượng volume transaction log đạt 95%, backup gần nhất thất bại, database vẫn nhận ghi. Hãy lập một runbook theo thứ tự ưu tiên **bảo vệ dữ liệu → xác định nguyên nhân → giảm rủi ro đầy đĩa → khôi phục backup thành công → đối soát sau sửa**. Giải thích tại sao xóa thủ công log là lựa chọn không chấp nhận được.

## 16. Kết luận

**Transaction log**, **checkpoint** và **retention policy** là ba yếu tố khác nhau nhưng phối hợp để bảo đảm Neo4j có thể phục hồi sau sự cố, giữ được lịch sử thay đổi cần thiết và không sử dụng đĩa vô hạn.

- **Transaction log** ghi thay đổi để bảo vệ các giao dịch đã commit và phục vụ những chức năng như backup vi sai, cluster catch-up hoặc CDC.
- **Checkpoint** flush dữ liệu về store, đặt mốc recovery và kích hoạt khả năng pruning.
- **Rotation** chia log thành tệp; **retention** quyết định phần lịch sử mong muốn còn giữ; **pruning** chỉ dọn log đã đủ điều kiện an toàn.
- **Thiết kế chính sách** phải dựa vào log rate, backup/CDC/cluster lag, yêu cầu RPO/RTO và ngân sách lưu trữ, không chỉ sao chép một con số mặc định.
- **Vận hành an toàn** bắt đầu từ quan sát cấu hình và metrics, không từ việc xóa tệp bằng tay.

Trước mọi thay đổi trong production, hãy đo trên workload đại diện, kiểm tra khả năng khôi phục từ backup và xác minh rằng các hệ thống phụ thuộc vào transaction log vẫn hoạt động đúng sau khi pruning.

### Tài liệu Neo4j chính thức

- [Neo4j Operations Manual – Transaction logging](https://neo4j.com/docs/operations-manual/current/database-internals/transaction-logs/)
- [Neo4j Operations Manual – Checkpointing and log pruning](https://neo4j.com/docs/operations-manual/current/database-internals/checkpointing/)
- [Neo4j Operations Manual – Configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/configuration-settings/)
- [Neo4j Operations Manual – Show configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/show-settings/)
- [Neo4j Operations Manual – Update dynamic settings](https://neo4j.com/docs/operations-manual/current/configuration/dynamic-settings/)
- [Neo4j Operations Manual – Database backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/)
- [Neo4j Operations Manual – Online backup](https://neo4j.com/docs/operations-manual/current/backup-restore/online-backup/)
- [Neo4j Operations Manual – Metrics reference](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/reference/)
- [Neo4j Change Data Capture – CDC on Neo4j DBMS](https://neo4j.com/docs/cdc/current/get-started/self-managed/)
- [Neo4j Change Data Capture – Troubleshooting](https://neo4j.com/docs/cdc/current/troubleshooting/)
