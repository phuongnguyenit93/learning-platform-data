# Sao chép, read replica và định tuyến đọc ghi

Khi ứng dụng cloud tăng lượng người dùng, cơ sở dữ liệu thường phải phục vụ đồng thời hai nhóm tải rất khác nhau: giao dịch thay đổi dữ liệu và truy vấn đọc. Nếu một máy chủ database xử lý tất cả, các truy vấn báo cáo hoặc màn hình đọc nhiều có thể cạnh tranh CPU, RAM, I/O và connection với giao dịch quan trọng. **Database replication**, **read replica** và **read/write routing** là các kỹ thuật giúp mở rộng khả năng phục vụ, tăng tính sẵn sàng và phân bổ tải phù hợp.

Replication tạo các bản sao dữ liệu trên những node khác nhau. Read replica thường nhận bản sao thay đổi từ node ghi để phục vụ truy vấn đọc. Read/write routing quyết định truy vấn nào được gửi tới primary, truy vấn nào có thể gửi tới replica và khi nào cần bảo đảm đọc được dữ liệu vừa ghi. Các kỹ thuật này không tự động tạo ra tính nhất quán mạnh hoặc khả năng failover an toàn. Kiến trúc cần hiểu rõ replication mode, độ trễ sao chép, giới hạn nhất quán, thứ tự ghi, fencing và cách phục hồi khi một node mất kết nối.

Bài học thuộc chương **Kiến trúc cơ sở dữ liệu** của lộ trình **Cloud Architecture**. Trọng tâm là đánh đổi giữa hiệu năng, độ tin cậy, bảo mật, chi phí và khả năng vận hành khi triển khai database có bản sao trên cloud.

Sau bài học, bạn có thể:

- Phân biệt replication, backup, read replica, standby và multi-primary.
- Giải thích replication đồng bộ, bất đồng bộ và bán đồng bộ.
- Đo và xử lý replica lag, stale reads và read-after-write consistency.
- Thiết kế định tuyến đọc/ghi ở ứng dụng, proxy hoặc database cluster.
- Chọn truy vấn có thể gửi tới replica và truy vấn phải đọc primary.
- Thiết kế failover, promotion, fencing và tránh split brain.
- Quản lý connection, transaction, session affinity, retry và lỗi khi chuyển node.
- Đánh giá topology, RPO/RTO, chi phí và khả năng kiểm thử phục hồi.

## 1. Replication là gì?

**Replication** là quá trình duy trì một hoặc nhiều bản sao của dữ liệu trên các node database khác nhau. Một node nhận thay đổi, sau đó truyền các thay đổi đó tới node còn lại theo cơ chế mà hệ quản trị hỗ trợ.

Trong topology phổ biến một primary và nhiều replica:

- **Primary/leader/writer:** nhận các thao tác ghi được phép và thường là nguồn có thẩm quyền cho dữ liệu mới nhất.
- **Replica/follower/reader:** nhận các thay đổi từ primary và có thể phục vụ truy vấn đọc.
- **Replication channel:** truyền log hoặc thay đổi từ writer tới replica.
- **Replication position/offset/LSN:** đánh dấu tiến độ thay đổi đã được gửi, nhận hoặc áp dụng.
- **Promotion:** chuyển replica thành primary khi có quyết định failover.
- **Failover:** chuyển hoạt động sang node khác khi primary lỗi hoặc không còn phù hợp để tiếp tục phục vụ.

Tên thuật ngữ khác nhau theo database. Một số hệ dùng WAL, binlog, transaction log, oplog hoặc cơ chế log riêng. Cần hiểu semantics của sản phẩm đang chọn thay vì giả định mọi engine sao chép giống nhau.

### 1.1. Sơ đồ primary và read replica

~~~mermaid
flowchart TB
    APP["Application / API"] --> ROUTER["Read-write router"]
    ROUTER -->|Write| P[("Primary database")]
    ROUTER -->|Read| R1[("Read replica A")]
    ROUTER -->|Read| R2[("Read replica B")]
    P -->|Replication stream| R1
    P -->|Replication stream| R2
~~~

Primary tiếp nhận write; các replica nhận thay đổi và có thể xử lý truy vấn đọc. Sơ đồ này không nói rằng mọi lần ghi đã có mặt ngay trên replica. Khoảng thời gian từ khi thay đổi được commit tại primary đến khi replica áp dụng xong là một phần quan trọng của thiết kế.

## 2. Replication khác backup như thế nào?

Replication và backup đều tạo thêm bản dữ liệu nhưng phục vụ mục tiêu khác nhau.

| Khả năng | Replication | Backup |
| --- | --- | --- |
| Mục tiêu chính | Phục vụ tải, tăng khả năng sẵn sàng hoặc phân phối dữ liệu | Khôi phục dữ liệu sau xóa nhầm, corruption hoặc sự cố |
| Độ mới | Có thể gần realtime nhưng chịu replication lag | Theo thời điểm backup và log được lưu |
| Khi primary bị lỗi | Replica có thể được promote nếu đủ điều kiện | Thường cần restore và phục hồi log |
| Xóa nhầm dữ liệu | Lệnh xóa có thể được replicate sang replica | Có thể khôi phục từ bản backup trước sự cố |
| Corruption logic | Có thể lan sang replica | Bản backup sạch trước thời điểm lỗi có thể hữu ích |
| Khả năng thay thế lẫn nhau | Không bảo vệ đầy đủ mọi trường hợp mất dữ liệu | Không giúp chia tải đọc realtime |

Nếu người vận hành chạy nhầm câu lệnh xóa toàn bộ bảng, replication có thể sao chép thao tác đó sang các replica. Vì vậy, read replica không thay thế backup, point-in-time recovery, kiểm thử restore hoặc quy trình bảo vệ trước thao tác phá hoại.

## 3. Primary, read replica và standby

Các thuật ngữ này đôi khi bị dùng lẫn nhau, nhưng vai trò có thể khác:

- **Read replica:** bản sao có thể nhận truy vấn đọc từ ứng dụng.
- **Standby replica:** bản sao chủ yếu phục vụ failover hoặc disaster recovery; có thể không mở read traffic hoặc bị hạn chế truy vấn.
- **Hot standby:** node đã nhận và áp dụng log đủ để có thể được kích hoạt nhanh theo cơ chế engine.
- **Warm/cold standby:** mức sẵn sàng thấp hơn, có thể cần thêm thời gian khởi động, phục hồi hoặc bắt kịp log.
- **Multi-primary/multi-writer:** nhiều node có thể nhận write, đòi hỏi cơ chế giải quyết xung đột và consistency phức tạp hơn.

Một dịch vụ cloud có thể cung cấp read replica và standby như hai tùy chọn riêng. Cần kiểm tra vai trò, khả năng kết nối đọc, khả năng promotion, vùng triển khai và RPO/RTO được cam kết.

### 3.1. Read replica không mặc nhiên là node failover tốt nhất

Một replica đang xử lý báo cáo nặng có thể tụt lag hoặc thiếu tài nguyên. Nếu promote nó thành primary mà không kiểm tra, hệ thống có thể chuyển sang node chưa bắt kịp dữ liệu hoặc không đủ năng lực ghi. Thiết kế failover nên dùng candidate replica được xác định và theo dõi riêng, với tiêu chí freshness, health và capacity.

## 4. Replication đồng bộ và bất đồng bộ

Khác biệt quan trọng nhất là thời điểm primary xác nhận commit so với việc replica nhận và áp dụng thay đổi.

### 4.1. Asynchronous replication

Trong replication bất đồng bộ, primary commit và trả kết quả cho client mà không cần đợi replica áp dụng thay đổi.

~~~mermaid
sequenceDiagram
    participant A as Application
    participant P as Primary
    participant R as Replica
    A->>P: INSERT / UPDATE
    P->>P: Commit transaction
    P-->>A: Commit success
    P-->>R: Send log/change
    R->>R: Apply change
~~~

Ưu điểm:

- Write latency thấp hơn vì primary không phải chờ replica.
- Replica có thể ở xa hơn và chịu độ trễ mạng lớn hơn.
- Primary tiếp tục ghi khi replica tạm thời không theo kịp, trong giới hạn log/storage.
- Phù hợp nhiều workload đọc nhiều, nơi một mức stale read có thể chấp nhận.

Đánh đổi:

- Client có thể ghi thành công rồi đọc từ replica và chưa thấy dữ liệu.
- Nếu primary mất trước khi log được chuyển hoặc áp dụng đủ, một số giao dịch đã xác nhận có thể chưa nằm trên replica được promote.
- Replication lag có thể tăng khi tải write cao hoặc replica yếu.

### 4.2. Synchronous replication

Trong replication đồng bộ, primary chờ xác nhận từ replica hoặc một quorum theo semantics của hệ thống trước khi xác nhận commit cho client.

~~~mermaid
sequenceDiagram
    participant A as Application
    participant P as Primary
    participant R as Replica
    A->>P: INSERT / UPDATE
    P->>P: Prepare/record transaction
    P-->>R: Send commit record
    R->>R: Persist required log
    R-->>P: Acknowledgement
    P-->>A: Commit success
~~~

Ưu điểm là giảm nguy cơ mất các giao dịch đã được xác nhận trong phạm vi các node/quorum được yêu cầu. Đổi lại, write latency và khả năng hoạt động phụ thuộc mạng, vị trí replica và số node cần acknowledgement. Nếu một replica bắt buộc không phản hồi, write có thể bị chậm hoặc dừng tùy cấu hình.

### 4.3. Semi-synchronous và quorum

Một số engine hỗ trợ bán đồng bộ: primary chờ ít nhất một replica nhận hoặc xác nhận một mức durability, nhưng không nhất thiết chờ mọi replica áp dụng xong transaction. Một số hệ phân tán dùng quorum để quyết định commit và leader.

Không được diễn giải chung rằng “semi-sync bảo đảm mọi replica đã có dữ liệu”. Cần đọc chính xác acknowledgement nói tới log đã nhận, đã flush hay đã apply. Các mức này ảnh hưởng trực tiếp tới RPO và read consistency.

### 4.4. So sánh nhanh

| Tiêu chí | Async | Sync | Semi-sync/quorum |
| --- | --- | --- | --- |
| Write latency | Thường thấp hơn | Có thể cao hơn | Nằm giữa tùy topology |
| Phụ thuộc mạng replica | Ít hơn khi commit | Cao hơn | Theo quorum/ack policy |
| Risk mất write đã xác nhận khi failover | Có thể lớn hơn | Thấp hơn trong phạm vi đảm bảo | Phụ thuộc mức ack và quorum |
| Read replica freshness | Có thể trễ | Không nhất thiết apply tức thì dù commit được xác nhận ở mức log | Phụ thuộc apply progress |
| Availability khi node/network lỗi | Primary có thể tiếp tục ghi | Có thể bị chặn nếu thiếu ack bắt buộc | Phụ thuộc khả năng đạt quorum |
| Use case | Read scaling, latency-sensitive | Dữ liệu cần durability cao và topology phù hợp | Cân bằng durability và latency |

## 5. Hiểu ba mốc: send, receive và apply

Một replication pipeline có thể có nhiều tiến độ:

1. Primary tạo log record khi transaction commit.
2. Log được gửi qua network.
3. Replica nhận và ghi log vào vùng bền vững.
4. Replica replay/apply log để thay đổi data page hoặc state có thể truy vấn.

Một hệ quản trị có thể công bố nhiều chỉ số khác nhau cho các mốc này. Nếu replica đã nhận log nhưng chưa apply, nó có thể đã giữ dữ liệu bền vững nhưng query vẫn chưa nhìn thấy thay đổi.

Khi đánh giá lag, cần phân biệt:

- **Transport/send lag:** thay đổi chưa được gửi hoặc truyền tới replica.
- **Receive/write lag:** replica chưa nhận/flush đủ log.
- **Apply/replay lag:** log đã nhận nhưng chưa áp dụng xong.
- **Query visibility:** dữ liệu đã được áp dụng và có thể được truy vấn theo isolation semantics của engine.

Đừng lấy một chỉ số “replica lag” không rõ định nghĩa làm bằng chứng duy nhất cho durability hoặc freshness.

## 6. Replica lag và stale reads

**Replica lag** là khoảng cách tiến độ hoặc thời gian giữa dữ liệu tại primary và replica. Một replica có lag có thể trả về trạng thái cũ.

Ví dụ:

1. Khách tạo booking tại primary.
2. Primary commit và trả thành công.
3. Client tiếp tục tải màn hình booking từ read replica.
4. Replica chưa áp dụng event ghi mới.
5. Client thấy “chưa có booking” dù giao dịch đã thành công.

Đây là lỗi read-after-write nếu ứng dụng kỳ vọng ngay lập tức đọc được dữ liệu vừa ghi.

### 6.1. Lag theo thời gian và theo log position

Lag có thể đo bằng thời gian ước tính hoặc khoảng cách log position. Hai con số không tương đương tuyệt đối. Nếu workload có thời gian rảnh, khoảng cách byte/LSN có thể lớn nhưng thời gian apply ngắn; nếu có transaction dài hoặc contention, byte lag nhỏ vẫn có thể khiến apply bị chậm.

Cần theo dõi cả:

- Commit timestamp gần nhất tại primary.
- Replay/apply timestamp hoặc log position tại replica.
- Bytes/transactions behind nếu engine công bố.
- Queue backlog của replication.
- Thời gian query và health của replica.
- Lag theo từng replica, không chỉ trung bình cluster.

### 6.2. Vì sao lag tăng?

- Tốc độ write vượt năng lực replay.
- Replica có CPU, RAM, disk IOPS hoặc network thấp hơn primary.
- Truy vấn báo cáo nặng làm replica tranh chấp CPU/I/O.
- Transaction dài hoặc DDL ảnh hưởng apply.
- Network cross-zone/cross-region chậm hoặc gián đoạn.
- Replica maintenance, restart hoặc backlog sau outage.
- Replication slot/log retention giữ lại quá nhiều WAL/binlog và gây áp lực storage.

## 7. Read-after-write consistency

Read-after-write yêu cầu caller đọc được thay đổi do chính mình vừa ghi. Nếu hệ thống dùng async replica, định tuyến mọi read tới replica có thể vi phạm yêu cầu này.

### 7.1. Sticky read/session affinity

Sau khi ghi, ứng dụng có thể tạm thời gửi các lần đọc liên quan của cùng session tới primary. Cách này thường được gọi là read-your-writes routing hoặc primary stickiness.

Có thể gắn vào request context:

~~~text
requestContext:
    principalId
    tenantId
    lastWriteDatabase = primary
    writeCommitToken = replication_position
~~~

Thời gian stickiness phải đủ để bảo vệ trải nghiệm nhưng không nên kéo dài vô hạn khiến toàn bộ traffic quay lại primary. Có thể xóa cờ sau khi xác nhận replica đã bắt kịp hoặc sau một TTL có giới hạn, tùy consistency contract.

### 7.2. Wait until replica catches up

Một số engine cung cấp token/position sau commit và cho phép ứng dụng chờ replica đạt tới position đó. Luồng khái niệm:

1. Ghi tại primary và commit.
2. Nhận write position/token.
3. Chọn replica và kiểm tra replay position.
4. Nếu replica chưa đạt token, chờ trong một deadline ngắn.
5. Nếu vẫn chưa đạt, fallback sang primary hoặc trả trạng thái phù hợp.

Tên API và semantics tùy database; không nên tự xây phép so sánh position nếu không hiểu cách engine định nghĩa chúng.

### 7.3. Primary read cho thao tác nhạy cảm

Các truy vấn sau thường cần dữ liệu mới nhất hoặc nguồn có thẩm quyền:

- Đọc trạng thái ngay sau khi tạo/cập nhật.
- Kiểm tra số dư hoặc hạn mức trước giao dịch mới.
- Kiểm tra tồn kho cuối cùng trước khi xác nhận giữ hàng.
- Đọc trạng thái payment/refund trước khi thực hiện command tiếp theo.
- Kiểm tra quyền hoặc trạng thái account khi quyết định truy cập nhạy cảm.
- Truy vấn phải tham gia transaction hoặc lock với thao tác ghi.

Replica có thể phục vụ lịch sử, danh sách và báo cáo có stale tolerance nếu nghiệp vụ cho phép.

## 8. Định tuyến đọc ghi ở đâu?

Có ba cách triển khai chính; hệ thống có thể kết hợp.

### 8.1. Routing trong ứng dụng

Application có hai database connection/pool rõ ràng:

- Writer connection tới primary.
- Reader connection tới một hoặc nhiều replica.

Repository/data access layer quyết định query nào dùng writer/reader. Ưu điểm là ứng dụng có thể hiểu use case và consistency requirement. Nhược điểm là phải triển khai logic, health detection, failover và routing nhất quán ở mọi service.

### 8.2. Database proxy hoặc connection router

Proxy đứng giữa ứng dụng và database cluster, nhận kết nối và route theo endpoint, session hoặc policy. Nó có thể cung cấp connection pooling, endpoint ổn định, health check và hỗ trợ failover tùy sản phẩm.

Ưu điểm là giảm code routing lặp lại và tập trung quản trị. Đánh đổi là thêm một thành phần trong đường kết nối, cần HA, capacity, monitoring và hiểu rõ khả năng phân tích SQL/session của proxy. Một proxy không phải lúc nào cũng biết query nào an toàn để gửi replica.

### 8.3. Endpoint riêng của managed database

Nhiều dịch vụ cloud cung cấp writer endpoint, reader endpoint hoặc cluster endpoint. Ứng dụng kết nối theo vai trò thay vì từng node. Đây là lựa chọn thuận tiện, nhưng cần biết:

- Reader endpoint phân phối kết nối hay phân phối từng query?
- Connection hiện tại có tự chuyển khi failover không?
- DNS TTL và connection pool có làm client giữ IP/node cũ không?
- Reader endpoint có bao gồm replica đang lag hoặc đang maintenance không?
- Có hỗ trợ read-after-write/session affinity không?

Không giả định endpoint reader tự bảo đảm consistency hoặc load balancing theo từng statement.

### 8.4. So sánh

| Nơi định tuyến | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| Application | Hiểu nghiệp vụ và consistency của từng query | Logic phân tán trong code, nhiều client phải nhất quán |
| Proxy/router | Chính sách tập trung, pooling và health routing | Thêm hop và điểm cần HA; SQL semantics có thể phức tạp |
| Managed reader/writer endpoint | Đơn giản hóa cấu hình client | Tính năng và semantics phụ thuộc nhà cung cấp |

## 9. Quy tắc phân loại query

Không nên dùng một quy tắc đơn giản kiểu “SELECT luôn tới replica, INSERT/UPDATE tới primary”. Một câu SELECT có thể là bước quyết định cho giao dịch; một stored procedure có thể thay đổi dữ liệu; transaction có thể đọc rồi ghi và cần snapshot nhất quán.

| Loại thao tác | Điểm đọc khuyến nghị | Lý do |
| --- | --- | --- |
| INSERT/UPDATE/DELETE | Primary/writer | Nguồn có thẩm quyền ghi |
| SELECT ngay sau write của cùng request | Primary hoặc replica đã xác nhận bắt kịp | Bảo đảm read-your-writes |
| Đọc tồn kho trước commit giữ chỗ | Primary hoặc transaction coordinator thích hợp | Tránh dùng trạng thái stale để quyết định |
| Dashboard tổng hợp có tolerance | Read replica/projection | Tách tải đọc khỏi writer |
| Lịch sử giao dịch với độ trễ vài giây chấp nhận được | Replica nếu có contract | Workload đọc nhiều và có thể stale |
| Query trong transaction ghi | Thường cùng transaction/primary | Bảo đảm isolation và consistency |
| Read-only analytics nặng | Replica chuyên dụng hoặc warehouse | Tránh ảnh hưởng giao dịch |
| Quyết định authorization quan trọng | Nguồn authoritative theo consistency requirement | Replica lag có thể gây quyết định sai |

Một truy vấn SELECT có thể dùng khóa, temporary table, session state hoặc gọi stored procedure có side effect. Routing phải dựa trên semantic và workload, không chỉ keyword SQL.

## 10. Transaction và connection pooling

Routing đọc ghi phải giữ tính nhất quán của transaction. Khi transaction bắt đầu trên primary, mọi query thuộc transaction đó thường phải ở cùng connection/node cho đến commit/rollback.

Các quy tắc:

- Không chuyển một câu SELECT giữa transaction sang replica khác.
- Không thay connection của transaction đang mở khi proxy failover mà không xử lý transaction state.
- Xác định pool writer và reader, giới hạn connection theo capacity database.
- Xử lý connection stale sau failover; client cần reconnect theo policy.
- Giải phóng connection khi timeout/hủy request.
- Tránh một pool reader quá lớn làm cạn connection dù CPU database còn thấp.

### 10.1. Read transaction và isolation

Một transaction đọc nhiều bảng có thể cần snapshot nhất quán tại cùng thời điểm. Nếu ứng dụng thực hiện từng query qua nhiều replica hoặc node khác nhau, kết quả có thể phản ánh những mốc dữ liệu không đồng nhất.

Để giữ consistency, dùng transaction ở node hỗ trợ isolation cần thiết, hoặc đọc từ một snapshot/projection có semantics rõ. Không chia một logical transaction tùy tiện qua nhiều read replica.

## 11. Tách workload đọc: replica, cache hay read model?

Read replica là một cách mở rộng đọc ở mức database. Không phải mọi query đều nên chuyển sang replica.

| Giải pháp | Phù hợp khi | Đánh đổi |
| --- | --- | --- |
| Read replica | Query gần giống nguồn dữ liệu và chấp nhận lag theo policy | Có chi phí node, replication và lag |
| Cache | Kết quả lặp lại, freshness có thể kiểm soát | Invalidation, cache stampede và isolation |
| CQRS/read projection | Query shape khác write model, cần tổng hợp hoặc index riêng | Pipeline cập nhật và eventual consistency |
| Data warehouse | Analytics/reporting lớn, scan và aggregate phức tạp | Không phù hợp transactional low-latency read |
| Vertical scaling | Tải vừa và cần giải pháp đơn giản | Có giới hạn phần cứng và chi phí nâng cấp |
| Sharding/partitioning | Dữ liệu hoặc throughput vượt một node | Tăng độ phức tạp phân phối dữ liệu và truy vấn |

Một query báo cáo đọc hàng tỷ dòng không nhất thiết phù hợp trên read replica production; nó có thể làm lag tăng và chiếm I/O. Warehouse hoặc projection riêng có thể phù hợp hơn.

## 12. Replication topology: một vùng hay nhiều vùng?

### 12.1. Same-region replicas

Replica cùng region, có thể ở availability zone khác, thường có network latency thấp hơn và phù hợp read scaling/HA trong vùng. Cần kiểm tra dịch vụ có đảm bảo replica placement khác zone hay không và việc promotion diễn ra ra sao.

### 12.2. Cross-region replicas

Replica ở region khác hỗ trợ disaster recovery, đọc gần người dùng ở vùng xa hoặc tuân thủ một số mục tiêu địa lý. Đánh đổi gồm network latency, replication lag lớn hơn, data transfer cost, khả năng mất kết nối và quy trình promotion phức tạp.

### 12.3. Topology ví dụ

~~~mermaid
flowchart TB
    subgraph R1["Region A - primary region"]
        APP["Application"] --> W[("Primary writer")]
        W --> RA1[("Reader AZ A")]
        W --> RA2[("Reader AZ B")]
    end
    W -->|Cross-region replication| RB[("DR replica - Region B")]
    DRAPP["DR application"] -. "Kích hoạt khi failover" .-> RB
~~~

Cross-region replica có thể được dùng làm DR candidate. Nếu ứng dụng đang đọc trực tiếp từ replica ở region xa, cần đánh giá lag và latency; nếu chỉ dành cho recovery, có thể không cần mở read traffic thường xuyên.

## 13. Read scaling và giới hạn thực tế

Có thể ước tính tải đọc và tải ghi để xác định số replica cần thiết, nhưng tăng replica không tự động tăng throughput tuyến tính.

Nếu mỗi replica chịu được \(Q\) truy vấn/giây trong workload đo được và có \(N\) replica cân bằng tương đối đều:

\[
Q_{\text{aggregate}} \approx N \times Q
\]

Đây là ước lượng lý tưởng. Thực tế còn giới hạn bởi primary phải gửi log, network, storage, connection router, query skew, cache locality và replication overhead. Nếu query có hotspot hoặc một khách hàng chiếm phần lớn tải, phân phối đều theo số kết nối chưa chắc đều về CPU/I/O.

Cần benchmark theo query mix thật, không chỉ chạy một SELECT đơn giản. Theo dõi p95/p99, CPU, IOPS, buffer/cache hit, connection count, replication lag và chi phí.

### 13.1. Replica có thể làm primary chậm hơn

Replication tiêu thụ tài nguyên để tạo log, truyền log và duy trì các bản sao. Nhiều replica hoặc replica liên vùng có thể làm tăng network, storage và CPU. Tùy engine, primary có thể phải giữ log lâu hơn khi replica lag hoặc replication slot chưa tiến triển, làm tăng áp lực đĩa.

## 14. Failover, promotion và fencing

Failover chuyển writer role sang node khác khi primary không thể tiếp tục. Đây là quy trình trạng thái, không chỉ thay hostname.

Một chuỗi failover thường gồm:

1. Phát hiện primary lỗi hoặc bị cô lập.
2. Xác minh trạng thái và chọn candidate replica.
3. Đánh giá replica freshness và transaction loss có thể xảy ra.
4. Ngăn primary cũ tiếp tục nhận write.
5. Promote candidate theo cơ chế engine/control plane.
6. Cập nhật writer endpoint/route.
7. Ứng dụng hủy connection cũ và reconnect.
8. Kiểm tra consistency, read/write health và replication topology mới.
9. Khôi phục node cũ như replica mới sau khi đồng bộ an toàn.

### 14.1. Split brain

**Split brain** xảy ra khi hai node cùng tin rằng mình là primary và cùng nhận write. Hậu quả có thể là dữ liệu phân nhánh, xung đột và mất khả năng hợp nhất tự động.

Cần cơ chế **fencing** để bảo đảm primary cũ không còn quyền ghi trước khi promote node mới. Cơ chế có thể dựa trên quorum/lease, control plane, network isolation, revoke writer credential hoặc fencing token tùy hệ thống. Chỉ đổi DNS mà primary cũ vẫn nhận write không phải fencing an toàn.

### 14.2. RPO và RTO

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất theo thời gian/điểm khôi phục được chấp nhận.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ.

Async replication có thể có RPO lớn hơn 0 khi primary hỏng trước khi log được replicate; sync/quorum có thể giảm RPO trong phạm vi semantics được bảo đảm nhưng tăng latency hoặc phụ thuộc quorum. RTO còn phụ thuộc phát hiện lỗi, promotion, endpoint change, reconnect, kiểm tra ứng dụng và xử lý giao dịch chưa rõ kết quả.

Không lấy thời gian promotion của database làm toàn bộ RTO ứng dụng.

## 15. Giao dịch đang chạy khi failover

Nếu primary mất kết nối giữa lúc application gửi COMMIT và nhận response, client có thể không biết transaction đã commit hay chưa. Retry toàn bộ thao tác có thể tạo bản ghi trùng hoặc thu tiền hai lần.

Thiết kế cần:

- Idempotency key cho command/giao dịch quan trọng.
- Unique constraint hoặc business key để chống duplicate.
- Retry có phân loại lỗi và giới hạn.
- Reconciliation khi trạng thái transaction chưa xác định.
- Xử lý connection invalid và transaction rollback/reconnect rõ ràng.
- Không giả định transaction có thể tiếp tục trên primary mới.

Một lỗi network khi commit không đồng nghĩa transaction chắc chắn rollback. Application nên tra cứu trạng thái theo business identifier hoặc idempotency key trước khi thử lại tác động.

## 16. Read routing khi replica lag cao

Router không nên chỉ phân phối round-robin tới mọi replica bất kể health và lag.

Một policy có thể gồm:

- Health check connection và query cơ bản.
- Lag threshold theo use case.
- Loại replica đang resync, maintenance hoặc quá tải.
- Ưu tiên replica cùng region/zone khi có thể.
- Fallback về primary chỉ khi primary còn capacity và query được phép.
- Trả degraded/temporarily unavailable khi không thể đáp ứng consistency contract.
- Theo dõi số request bị route primary do lag.

### 16.1. Tránh overload primary khi fallback

Nếu mọi replica cùng lag và router chuyển tất cả query về primary, writer có thể bị quá tải đúng lúc đang chịu áp lực replication. Cần giới hạn fallback, ưu tiên query quan trọng, rate-limit request đọc không thiết yếu và có load shedding/cache phù hợp.

Không nên cho router “thử replica, timeout rồi retry primary” với thời gian chờ dài cho mọi query; cách này có thể làm tổng latency và số query tăng mạnh.

## 17. Security cho replication và read endpoint

Replica chứa dữ liệu giống primary nên phải được bảo vệ theo sensitivity của dữ liệu nguồn.

- Mã hóa kết nối replication và xác thực node bằng danh tính/certificate phù hợp.
- Mã hóa storage/snapshot theo policy.
- Giới hạn network path giữa primary, replica và ứng dụng.
- Tài khoản read-only phải thật sự không có quyền ghi/DDL hoặc quyền quản trị ngoài yêu cầu.
- Phân tách credential writer và reader.
- Không cho người dùng cuối kết nối trực tiếp database chỉ vì node mang tên read replica.
- Áp authorization/tenant filter ở application hoặc data layer; quyền read-only không đồng nghĩa quyền đọc mọi tenant.
- Audit quyền promotion, thay đổi topology, replication configuration và truy vấn dữ liệu nhạy cảm.
- Quản lý snapshot/backup và dữ liệu replica theo cùng chính sách retention/privacy.

Nếu primary dùng row-level security hoặc view giới hạn dữ liệu, phải xác minh policy có hiệu lực tương tự trên replica và trong đường truy cập thực tế. Không được giả định đọc từ replica tự động tuân thủ tenant isolation.

## 18. Quản lý schema change và DDL

Schema migration có thể ảnh hưởng replication và các phiên bản ứng dụng cùng đang hoạt động.

Một quy trình an toàn thường dùng expand–migrate–contract:

1. **Expand:** thêm schema mới theo cách tương thích với ứng dụng cũ, tránh rename/drop ngay.
2. **Deploy application:** ứng dụng mới có thể đọc/ghi theo schema tương thích.
3. **Migrate/backfill:** cập nhật dữ liệu theo batch, có rate limit để không gây lag.
4. **Verify:** kiểm tra cả primary và replica, query plan và replication health.
5. **Contract:** chỉ bỏ cột/schema cũ sau khi không còn consumer cần dùng.

DDL replication semantics khác nhau theo engine. Một số thao tác có thể gây lock lâu, làm replica apply lag hoặc cần chạy riêng. Cần kiểm thử trên phiên bản engine và topology production-like.

## 19. Read replica và báo cáo

Đưa query báo cáo sang replica có thể bảo vệ primary khỏi scan nặng, nhưng replica vẫn dùng cùng loại tài nguyên và có thể bị quá tải.

Cần:

- Tách workload báo cáo nặng sang replica riêng hoặc warehouse.
- Dùng query timeout, resource group/workload management nếu có.
- Tránh chạy full table scan cùng thời điểm với replication catch-up.
- Theo dõi lag theo thời gian chạy báo cáo.
- Xác định freshness cho dashboard và export.
- Giới hạn concurrency và kết quả tải xuống.
- Không chạy tác vụ write hoặc stored procedure side effect từ tài khoản read-only.

Với báo cáo cần dữ liệu tại một thời điểm nhất quán, có thể dùng snapshot/reporting projection thay vì chạy nhiều truy vấn dài trên replica đang tiếp nhận dữ liệu liên tục.

## 20. Ví dụ định tuyến trong ứng dụng

Một lớp data access có thể phân loại query theo consistency requirement.

~~~java
enum ReadConsistency {
    STRONG,
    EVENTUAL
}

public final class DatabaseRouter {
    private final DataSource writer;
    private final DataSource reader;

    public DatabaseRouter(DataSource writer, DataSource reader) {
        this.writer = writer;
        this.reader = reader;
    }

    public Connection getConnection(ReadConsistency consistency)
            throws SQLException {
        return consistency == ReadConsistency.STRONG
                ? writer.getConnection()
                : reader.getConnection();
    }

    public Connection getWriteConnection() throws SQLException {
        return writer.getConnection();
    }
}
~~~

Đây là ví dụ khái niệm. Trong hệ thống thực, routing phải hiểu transaction context, session stickiness, failover, health/lag và connection lifecycle. Không nên để caller tự chọn STRONG/EVENTUAL một cách tùy tiện; API/repository cần định nghĩa chính sách theo use case.

### 20.1. Ví dụ chính sách repository

~~~text
createBooking(command):
    write transaction on primary
    return bookingId and commit position

getBookingImmediately(bookingId):
    read primary
    or wait for a replica to reach commit position

listPastBookings(customerId):
    read eligible replica
    stale tolerance = product-defined

checkInventoryBeforeReservation(assetId):
    read authoritative state on primary
    then execute reservation transaction
~~~

Điểm quan trọng là consistency requirement thuộc use case. Không nên để việc chọn node bị ẩn trong một router không hiểu ý nghĩa nghiệp vụ.

## 21. Kiểm thử replication và failover

Chỉ kiểm tra replica có kết nối được chưa đủ. Cần kiểm thử dữ liệu, lag, routing và hành vi của ứng dụng.

- **Replication correctness:** ghi dữ liệu, xác nhận replica nhận/apply đúng và không thiếu thứ tự cần thiết.
- **Lag test:** tăng write load, chạy query nặng trên replica và quan sát độ trễ.
- **Read-after-write test:** ghi rồi đọc qua từng route, xác minh semantics.
- **Failover test:** ngắt primary có kiểm soát, đo detection, promotion, endpoint update và reconnect.
- **Split-brain test:** xác minh primary cũ bị fencing trước khi writer mới hoạt động.
- **Unknown commit test:** ngắt mạng giữa commit và response, kiểm tra idempotency/reconciliation.
- **Replica outage test:** một replica lỗi không làm reader router gửi traffic tiếp tục vào node đó.
- **Restore test:** khôi phục từ backup độc lập với replication.
- **DDL/migration test:** thay schema dưới tải và đo lock/replication lag.
- **Security test:** tài khoản reader không ghi được, tenant isolation và quyền promotion đúng.

### 21.1. Diễn tập theo runbook

Mỗi kịch bản cần có owner, điều kiện bắt đầu, tiêu chí abort, cách đánh giá dữ liệu mất, thao tác promotion, cách đổi endpoint, kiểm tra sau failover và quy trình tái gia nhập node cũ. Diễn tập trong môi trường staging tương đương trước khi áp dụng production.

## 22. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Coi read replica là backup | Lệnh xóa/corruption lan sang bản sao | Backup và PITR riêng, diễn tập restore |
| Route mọi SELECT tới replica | Read-after-write và giao dịch nghiệp vụ dùng dữ liệu stale | Phân loại query theo consistency |
| Giả định replication async không lag | UI hoặc quyết định nghiệp vụ sai | Đo lag và quy định stale tolerance |
| Chọn replica chỉ theo round-robin | Query tới node đang quá tải hoặc lag | Health, lag-aware routing và load metrics |
| Promote replica chưa bắt kịp | Mất dữ liệu đã commit ở primary cũ | Kiểm tra log position/RPO và fencing |
| Đổi DNS mà không fence primary cũ | Split brain, hai writer | Fencing/quorum và xác nhận writer role |
| Fallback toàn bộ traffic về primary | Quá tải writer khi replica sự cố | Giới hạn fallback, ưu tiên và load shedding |
| Transaction đi qua nhiều node | Isolation và snapshot không nhất quán | Giữ transaction trên một connection/node |
| Retry commit mù quáng | Giao dịch hoặc side effect trùng | Idempotency key và reconciliation |
| Tăng số replica không đo workload | Chi phí/log pressure tăng nhưng throughput không tăng tương ứng | Benchmark query mix và replication overhead |
| Dùng replica cho báo cáo quá nặng | Lag tăng, reader và primary chịu ảnh hưởng | Replica chuyên dụng hoặc warehouse |
| Chỉ đo lag trung bình | Một replica/partition bị kẹt không phát hiện | Theo dõi từng node và queue/apply progress |
| DDL/backfill không kiểm soát | Replica tụt lag và ứng dụng bị lock | Expand–migrate–contract, batch và rate limit |
| Dùng chung credential writer/reader | Tài khoản read có thể ghi hoặc leo quyền | Tách identity và least privilege |

## 23. Quy trình thiết kế và triển khai

1. **Đo tải hiện tại:** read/write ratio, query mix, peak QPS, connection, CPU, IOPS và latency p95/p99.
2. **Xác định consistency requirement:** use case nào cần strong/read-your-writes; stale tolerance bao lâu.
3. **Đặt RPO/RTO:** xác định mức dữ liệu mất và thời gian ngừng dịch vụ được chấp nhận.
4. **Chọn replication mode:** async, sync hoặc semi-sync theo durability, latency và topology.
5. **Chọn topology:** primary + reader, standby, cross-zone/cross-region, hoặc multi-writer nếu thực sự cần.
6. **Thiết kế routing:** application, proxy hay endpoint managed; định nghĩa read/write policy.
7. **Định nghĩa lag policy:** threshold, fallback, query priority, stale response và cảnh báo.
8. **Thiết kế failover:** candidate selection, fencing, promotion, endpoint update và rejoin.
9. **Tối ưu query workload:** replica chuyên dụng, cache, projection hoặc warehouse khi cần.
10. **Thiết lập security:** encryption, credential riêng, network isolation, audit và tenant authorization.
11. **Kiểm thử:** lag, read-after-write, failover, unknown commit, backup restore và DDL.
12. **Vận hành liên tục:** capacity, storage/log retention, connection pools, cost và diễn tập.

## 24. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi thiết kế |
| --- | --- |
| **Độ tin cậy** | Replication mode phù hợp RPO? Candidate có bắt kịp? Failover có fencing và diễn tập? Backup độc lập có restore test? |
| **Bảo mật** | Replica có cùng mức bảo vệ dữ liệu? Credential reader/writer tách? Network, encryption, tenant isolation và promotion audit rõ? |
| **Hiệu quả hiệu năng** | Read load thực sự được phân bổ? Lag, p95/p99, connection và I/O đạt SLO? Báo cáo có làm ảnh hưởng replication? |
| **Tối ưu chi phí** | Chi phí replica, cross-region transfer, storage log, proxy và vận hành có tương xứng với tải/SLO? |
| **Khả năng vận hành** | Có lag dashboard, alert, routing policy, runbook failover/rejoin và reconciliation giao dịch? |

### Checklist nghiệm thu

- [ ] Primary, read replica và standby có vai trò, region/zone và owner rõ.
- [ ] Replication mode và acknowledgement semantics được hiểu và ghi trong thiết kế.
- [ ] RPO/RTO được gắn với topology và đã kiểm chứng.
- [ ] Replica lag được theo dõi theo từng node và có threshold.
- [ ] Query được phân loại theo consistency; không dùng quy tắc SELECT luôn tới replica.
- [ ] Read-after-write được bảo vệ bằng primary stickiness hoặc wait-for-position khi cần.
- [ ] Transaction giữ trên connection/node phù hợp.
- [ ] Reader/writer connection pool và fallback có giới hạn.
- [ ] Failover có candidate selection, fencing, promotion, reconnect và rejoin.
- [ ] Unknown commit và retry có idempotency/reconciliation.
- [ ] Replica không bị coi là backup; PITR/backup có restore test.
- [ ] Credential reader/writer tách, encryption, network và tenant authorization được kiểm tra.
- [ ] Load test bao gồm query mix, lag, cross-region và báo cáo nặng.
- [ ] Có dashboard, alert và runbook cho lag, failover, storage và connection.

## 25. Bài tập áp dụng

Một nền tảng đặt thuê thiết bị có database primary phục vụ giao dịch. Lưu lượng giờ cao điểm gồm 70% đọc và 30% ghi. Trang danh sách đơn có thể chấp nhận dữ liệu chậm tối đa 3 giây; nhưng sau khi khách tạo booking, màn hình xác nhận phải hiển thị đơn vừa tạo ngay. Hệ thống báo cáo cuối ngày chạy query tổng hợp nặng. Doanh nghiệp yêu cầu RPO tối đa 5 giây khi mất primary trong region và RTO 2 phút.

Hãy thiết kế:

1. Có nên thêm read replica cùng region? Có cần replica/standby khác region cho DR?
2. Chọn async, sync hay semi-sync ở từng đường replication; giải thích tác động latency và RPO.
3. Định tuyến query nào sang replica và query nào phải đọc primary.
4. Làm sao bảo vệ read-after-write trên màn hình xác nhận?
5. Thiết kế lag threshold, fallback và cảnh báo khi replica vượt 3 giây.
6. Đặt báo cáo nặng trên replica riêng hay warehouse; tiêu chí lựa chọn là gì?
7. Mô tả failover gồm fencing, promotion, DNS/endpoint, reconnect và rejoin node cũ.
8. Nếu client timeout đúng lúc commit, hệ thống tránh tạo booking trùng ra sao?
9. Kiểm thử bằng cách nào để chứng minh RPO/RTO và consistency thực tế?

Một phương án có cơ sở có thể route danh sách đơn sang read replica khi lag dưới ngưỡng, giữ read sau tạo booking ở primary hoặc chờ replica đạt commit position, tách báo cáo nặng sang warehouse/replica chuyên dụng và chọn topology DR theo RPO/RTO. Cần chứng minh RPO/RTO qua diễn tập, không chỉ dựa trên cấu hình dịch vụ.

**Điểm cốt lõi:** replication tạo bản sao để hỗ trợ đọc, tính sẵn sàng hoặc phục hồi; read replica có thể giúp tách tải nhưng thường chịu replica lag; read/write routing phải hiểu consistency của từng use case. Failover an toàn còn cần fencing, promotion có kiểm soát, xử lý transaction chưa rõ kết quả và backup độc lập. Thiết kế tốt cân bằng được freshness, latency, durability, chi phí và khả năng vận hành thay vì chỉ tăng số lượng replica.
