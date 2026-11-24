# Vận hành khi mất kết nối và đồng bộ trạng thái trở lại

Hệ thống hybrid và edge thường phải tiếp tục phục vụ tại chi nhánh, nhà máy, cửa hàng, phương tiện hoặc địa điểm xa ngay cả khi đường truyền về cloud bị gián đoạn. Nếu ứng dụng chỉ hoạt động khi gọi được dịch vụ trung tâm, một sự cố WAN có thể làm dừng toàn bộ nghiệp vụ tại edge. Ngược lại, nếu cho phép ghi dữ liệu offline mà không có quy tắc đồng bộ, khi kết nối trở lại hệ thống có thể tạo bản ghi trùng, ghi đè dữ liệu mới hơn hoặc làm sai trạng thái nghiệp vụ.

Thiết kế cần trả lời hai câu hỏi: **edge được phép tiếp tục làm gì khi mất kết nối**, và **làm thế nào hợp nhất những thay đổi cục bộ với trạng thái trung tâm khi kết nối trở lại**. Không phải dữ liệu nào cũng cần đồng bộ ngay, và không phải mọi thao tác đều an toàn khi chạy độc lập. Cần phân loại nghiệp vụ, xác định nguồn dữ liệu có thẩm quyền, lưu thay đổi bền vững, truyền dữ liệu có kiểm soát và giải quyết xung đột theo ý nghĩa nghiệp vụ.

Bài học này trình bày các chế độ hoạt động khi offline, mô hình lưu và chuyển tiếp dữ liệu, giao thức đồng bộ, xử lý duplicate và out-of-order event, chiến lược conflict resolution, bảo mật, quan sát vận hành và quy trình phục hồi sau mất kết nối.

## 1. Mục tiêu và phạm vi của disconnected operation

Disconnected operation là khả năng hệ thống tiếp tục thực hiện một tập chức năng đã xác định khi không thể liên lạc với một hoặc nhiều dịch vụ bên ngoài. Nguyên nhân có thể là:
- Mất kết nối Internet hoặc WAN.
- VPN/private link bị lỗi.
- Cloud region hoặc control plane không truy cập được.
- DNS, routing, firewall hoặc gateway gặp sự cố.
- Đường truyền chập chờn, độ trễ cao hoặc packet loss.
- Edge node bị cô lập theo thiết kế để bảo vệ mạng.
- Thiết bị di động hoặc phương tiện di chuyển qua vùng không phủ sóng.

Mục tiêu không phải duy trì mọi tính năng như khi online. Mục tiêu là duy trì các nghiệp vụ đã được phê duyệt, bảo vệ dữ liệu và phục hồi nhất quán khi kết nối trở lại.

### Các câu hỏi thiết kế

1. Những chức năng nào bắt buộc hoạt động offline?
2. Những thao tác nào chỉ được phép khi có xác nhận từ cloud?
3. Dữ liệu nào được lưu cục bộ và trong bao lâu?
4. Edge có quyền tạo hoặc thay đổi loại dữ liệu nào?
5. Khi hai nơi cùng sửa một đối tượng, ai có quyền quyết định?
6. Mất kết nối tối đa bao lâu mà edge vẫn đủ dung lượng?
7. Khi reconnect, dữ liệu nào cần đồng bộ trước?
8. Làm sao biết đồng bộ đã hoàn tất và có thể tin trạng thái mới?
9. Điều gì xảy ra nếu edge mất điện hoặc hỏng ổ đĩa trong lúc offline?
10. Làm thế nào thu hồi quyền truy cập của thiết bị bị mất kết nối lâu ngày?

### Phân biệt offline với degraded mode

- **Offline:** không có đường giao tiếp khả dụng tới một dependency hoặc hệ thống trung tâm.
- **Degraded mode:** vẫn có một phần kết nối hoặc dịch vụ, nhưng khả năng bị giới hạn, ví dụ chỉ đọc được cache hoặc chỉ gửi dữ liệu ưu tiên cao.
- **Partitioned mode:** một phần các node vẫn liên lạc nội bộ nhưng bị tách khỏi phần còn lại của hệ thống.
- **Recovery/synchronizing:** kết nối đã trở lại nhưng backlog chưa được đồng bộ hết.

Đừng chuyển trạng thái từ offline sang healthy ngay khi một ping thành công. Hệ thống có thể đã truy cập được endpoint nhưng chưa xác thực được, chưa gửi được dữ liệu hoặc chưa xử lý xong backlog.

## 2. Xác định mức độ tự chủ của edge

Mỗi workload cần một mức tự chủ được xác định trước.

| Mức | Khả năng khi mất kết nối | Ví dụ |
|---|---|---|
| Read-only cache | Đọc dữ liệu đã cache, không nhận thay đổi | Tra cứu danh mục hoặc hướng dẫn |
| Local write queue | Ghi yêu cầu vào hàng đợi bền vững, xử lý sau | Gửi telemetry, đơn hàng chờ xác nhận |
| Local processing | Xử lý nghiệp vụ cục bộ trong phạm vi được phép | Tính toán, phân loại, điều khiển cục bộ |
| Autonomous operation | Tiếp tục một quy trình có state và policy riêng | Dây chuyền sản xuất cần điều khiển tại chỗ |
| Fail-closed | Từ chối thao tác khi không xác minh được điều kiện | Giao dịch vượt hạn mức hoặc thao tác nhạy cảm |

Không nên chọn một mức duy nhất cho toàn bộ ứng dụng. Một edge site có thể tiếp tục hiển thị dashboard, nhận lệnh nội bộ và thu thập telemetry, nhưng tạm dừng thay đổi quyền, thanh toán rủi ro cao hoặc cập nhật policy bảo mật khi không liên lạc được với control plane.

### Phân loại theo mức rủi ro

- **Có thể chạy offline:** thao tác cục bộ, có thể kiểm tra bằng dữ liệu đã đồng bộ và có quy tắc hợp nhất.
- **Chạy có điều kiện:** thao tác chỉ được thực hiện trong hạn mức, thời gian hoặc quyền đã cấp trước.
- **Phải chờ online:** thao tác cần xác nhận duy nhất từ hệ thống trung tâm.
- **Phải fail-safe:** nếu không thể xác minh trạng thái thì hệ thống chuyển về trạng thái an toàn đã thiết kế.

Với hệ thống điều khiển vật lý, fail-safe phải được xác định bởi kỹ sư nghiệp vụ/an toàn của thiết bị. Không tự suy diễn rằng "tiếp tục chạy" luôn an toàn hơn "dừng".

## 3. Mô hình dữ liệu local-first và nguồn dữ liệu có thẩm quyền

Local-first cho phép edge ghi nhận thay đổi cục bộ trước, sau đó đồng bộ về trung tâm. Mô hình này tăng khả năng hoạt động offline nhưng yêu cầu xác định rõ quyền sở hữu dữ liệu.

### Các kiểu ownership

- **Central-authoritative:** cloud là nguồn dữ liệu có thẩm quyền. Edge có thể cache và gửi đề xuất thay đổi, nhưng cloud quyết định kết quả cuối.
- **Edge-authoritative:** edge sở hữu một miền dữ liệu cụ thể, ví dụ trạng thái thiết bị tại một site. Cloud nhận bản sao hoặc tổng hợp.
- **Partitioned ownership:** mỗi edge sở hữu một tập đối tượng hoặc key riêng, giảm khả năng hai nơi cùng sửa.
- **Shared ownership:** nhiều node có thể sửa cùng dữ liệu; cần versioning và conflict resolution rõ ràng.

### Phân loại dữ liệu

| Loại dữ liệu | Nơi có thẩm quyền gợi ý | Hành vi offline |
|---|---|---|
| Cấu hình nền tảng | Cloud/control plane | Dùng bản đã xác minh; không tự sửa policy gốc |
| Cache danh mục | Cloud phát hành, edge đọc | Cho phép đọc bản cache theo TTL |
| Telemetry | Edge tạo, cloud tổng hợp | Buffer cục bộ và gửi lại |
| Sự kiện giao dịch tại site | Edge hoặc domain service theo ownership | Ghi local bền vững, đồng bộ sau |
| Trạng thái tồn kho dùng chung | Domain inventory trung tâm hoặc phân vùng sở hữu | Giới hạn giao dịch theo quota/reservation |
| Lệnh điều khiển nhạy cảm | Authority được chỉ định | Fail-closed nếu không có quyền hợp lệ |
| Log vận hành | Edge tạo, central lưu trữ | Buffer, ưu tiên sự kiện quan trọng |

Không nên để cả cloud và edge cùng là master của cùng một trường dữ liệu nếu không có quy tắc phân xử. Cách đơn giản nhất để tránh conflict là phân chia quyền ghi theo domain, tenant, site hoặc key.

### Bản sao không đồng nghĩa nguồn sự thật

Một bản cache có thể cũ nhưng vẫn hữu ích để phục vụ đọc. UI và API cần biết dữ liệu đang ở chế độ stale, thời điểm cập nhật gần nhất và liệu thao tác ghi có được phép hay không.

## 4. Kiến trúc store-and-forward

Store-and-forward là mẫu phổ biến: edge ghi sự kiện hoặc command vào bộ lưu trữ bền vững, sau đó một tiến trình đồng bộ gửi chúng tới cloud khi kết nối sẵn sàng.

~~~mermaid
flowchart LR
    APP["Ứng dụng tại edge"] --> LOCAL["Local database / durable outbox"]
    LOCAL --> SENDER["Sync agent"]
    SENDER --> LINK["WAN / private connection"]
    LINK --> INGEST["Cloud ingestion API"]
    INGEST --> INBOX["Inbox / deduplication"]
    INBOX --> DOMAIN["Domain processing"]
    DOMAIN --> ACK["Commit result / acknowledgement"]
    ACK --> SENDER
    SENDER --> LOCALACK["Đánh dấu event đã đồng bộ"]
~~~

### Thành phần chính

- **Local database:** lưu state nghiệp vụ và metadata cần thiết khi offline.
- **Outbox/spool:** giữ các event chưa gửi, có sequence và trạng thái delivery.
- **Sync agent:** quản lý kết nối, batching, retry, compression và checkpoint.
- **Cloud ingestion endpoint:** xác thực edge identity, kiểm tra schema và nhận event.
- **Inbox/deduplication store:** phát hiện event đã được xử lý.
- **Domain processor:** áp dụng thay đổi vào hệ thống có thẩm quyền.
- **Acknowledgement:** xác nhận kết quả commit để edge có thể đánh dấu event hoàn tất.

### Ghi state và outbox cùng transaction

Nếu ứng dụng ghi một thay đổi vào local database rồi gửi event riêng, có thể xảy ra:
- Database commit nhưng process crash trước khi publish.
- Event được gửi nhưng database transaction rollback.
- Edge khởi động lại và không biết event nào cần gửi.

Outbox pattern giải quyết bằng cách ghi business state và outbox record trong cùng local transaction. Sync agent đọc outbox và gửi sau. Đây là cách giảm nguy cơ mất event giữa hai thao tác ghi.

### Outbox không tự bảo đảm exactly-once

Event có thể được gửi nhiều lần nếu edge không nhận được acknowledgement sau khi cloud đã commit. Cloud cần idempotency/deduplication để một event được áp dụng nghiệp vụ tối đa một lần. Thực tế thường là at-least-once delivery kết hợp idempotent processing.

## 5. Lưu dữ liệu offline bền vững

Một hàng đợi trong RAM không đủ cho outage kéo dài hoặc mất điện. Cần lưu trên storage bền vững và có cơ chế khôi phục.

### Những gì cần lưu

- Event ID và sequence.
- Job/task ID nếu sự kiện thuộc một job.
- Entity ID hoặc partition key.
- Schema version.
- Event type.
- Event time và local ingest time.
- Payload hoặc reference tới payload.
- Retry count và next retry time.
- Delivery state.
- Checksum/hash nếu cần kiểm tra integrity.
- Correlation ID.
- Data classification và retention metadata.

### Write-ahead log và transaction

Database có thể dùng write-ahead log (WAL) để bảo vệ thay đổi trước khi page data được flush. Cấu hình durability cần phù hợp với rủi ro mất điện và loại storage. Nếu workload cần xác nhận ghi trước khi trả kết quả, không nên chỉ giữ dữ liệu trong page cache hoặc buffer chưa fsync theo policy.

### Capacity planning cho offline buffer

Ước lượng dung lượng tối thiểu:

\[
BufferSize \approx EventRate \times AverageEventSize \times OfflineDuration
\]

Cần cộng:
- Metadata và index overhead.
- Retry copy hoặc payload tạm.
- Log và checkpoint.
- Growth margin.
- File system reserved space.
- Dung lượng cần để compaction/backup.

Ví dụ edge tạo 30 event/giây, mỗi event trung bình 2 KiB và cần chịu offline 12 giờ:

\[
30 \times 2KiB \times 43{,}200 \approx 2.47GiB
\]

Đây mới là payload thô. Storage thực tế cần lớn hơn để chứa index, WAL, replication hoặc overhead. Nếu event size có đuôi dài, dùng p95/p99 và giới hạn payload.

### Quản lý đầy đĩa

Đặt ngưỡng:
- Warning khi buffer đạt mức sử dụng nhất định.
- Critical khi không còn headroom.
- Admission control để từ chối loại event ít ưu tiên.
- Retention/compaction cho dữ liệu đã được xác nhận.
- Alert khi oldest pending event vượt SLA.

Không xóa event chưa được cloud xác nhận chỉ để giải phóng dung lượng. Nếu buộc phải loại bỏ telemetry ít quan trọng, policy phải nêu rõ loại dữ liệu, số lượng bị drop và audit record.

## 6. Phân loại dữ liệu theo ưu tiên đồng bộ

Khi kết nối trở lại, gửi toàn bộ dữ liệu cùng lúc có thể làm nghẽn WAN và cloud ingestion. Cần xếp thứ tự theo giá trị và yêu cầu nghiệp vụ.

Ví dụ các lớp:
1. Security/audit event và command result quan trọng.
2. Giao dịch nghiệp vụ cần hoàn tất.
3. Trạng thái thiết bị và inventory.
4. Telemetry vận hành.
5. Log debug hoặc dữ liệu có thể tái tạo.
6. Artifact lớn có thể truyền ngoài luồng.

### Chính sách ưu tiên

Mỗi loại event nên có:
- Priority class.
- Maximum queue age.
- Retention khi không gửi được.
- Retry policy.
- Data size limit.
- Ordering requirement.
- Whether lossy delivery is allowed.
- Deadline hoặc expiration.

Không để debug log chiếm hết buffer và ngăn giao dịch quan trọng được đồng bộ. Dùng quota hoặc queue riêng cho từng class.

### Backpressure

Khi tốc độ tạo dữ liệu lớn hơn tốc độ gửi:
- Tăng backlog.
- Tăng queue age.
- Storage cục bộ có thể đầy.
- Event quan trọng có thể bị trì hoãn.

Backpressure có thể gồm giảm tốc độ producer, sampling telemetry, batch event, giới hạn concurrency và tạm dừng workload có thể trì hoãn. Không áp dụng drop policy cho business transaction nếu chưa có quy tắc nghiệp vụ rõ.

## 7. Phát hiện kết nối đã mất và đã phục hồi

Không nên dựa vào một lần ping tới Internet để xác định hệ thống đã online. Đường Internet có thể hoạt động trong khi API ingestion, DNS nội bộ hoặc identity endpoint vẫn không truy cập được.

### Health checks theo dependency

Kiểm tra riêng:
- DNS resolution.
- TCP/TLS connectivity.
- Authentication/token validity.
- API readiness.
- Permission để publish.
- Khả năng nhận acknowledgement.
- Latency và packet loss.
- Clock synchronization nếu giao thức phụ thuộc timestamp.

Dùng health probe nhẹ, có timeout và tần suất hợp lý. Không gửi probe quá dày gây tải thêm trong lúc mạng yếu.

### State machine kết nối

~~~mermaid
stateDiagram-v2
    [*] --> ONLINE
    ONLINE --> DEGRADED: latency cao hoặc lỗi từng phần
    ONLINE --> OFFLINE: dependency không truy cập được
    DEGRADED --> OFFLINE: lỗi kéo dài
    OFFLINE --> RECONNECTING: endpoint phục hồi
    RECONNECTING --> SYNCHRONIZING: xác thực và handshake thành công
    SYNCHRONIZING --> ONLINE: backlog và consistency đạt điều kiện
    SYNCHRONIZING --> DEGRADED: backlog còn lớn hoặc lỗi một phần
    RECONNECTING --> OFFLINE: handshake thất bại
    SYNCHRONIZING --> OFFLINE: kết nối lại bị mất
~~~

Ứng dụng cần hiển thị trạng thái phù hợp:
- Online.
- Degraded.
- Offline; local operations only.
- Reconnecting.
- Synchronizing; pending changes.
- Sync blocked; action required.

### Hysteresis

Để tránh trạng thái chập chờn:
- Cần một số lần probe thất bại trước khi chuyển offline.
- Cần nhiều lần probe thành công hoặc một handshake hoàn chỉnh trước khi chuyển reconnecting.
- Dùng cooldown giữa các lần thử.
- Phân biệt network failure với authentication failure.

Nếu TLS certificate hết hạn, retry mạng liên tục không giải quyết được; cần trạng thái "sync blocked" và hướng dẫn khắc phục credential.

## 8. Giao thức đồng bộ khi reconnect

Một giao thức sync nên có các bước rõ ràng:

1. **Authenticate:** edge xác minh danh tính bằng certificate, workload identity hoặc credential phù hợp.
2. **Negotiate:** trao đổi protocol version, schema support, capabilities và data scope.
3. **Identify state:** gửi edge ID, epoch/generation, last acknowledged sequence và local checkpoint.
4. **Reconcile metadata:** cloud trả cursor, snapshot version hoặc trạng thái đã nhận.
5. **Upload pending changes:** gửi event theo batch và thứ tự yêu cầu.
6. **Apply inbound changes:** nhận delta hoặc snapshot từ cloud.
7. **Resolve conflicts:** xử lý theo ownership và policy.
8. **Commit checkpoint:** lưu watermark/cursor chỉ sau khi dữ liệu được áp dụng bền vững.
9. **Verify:** đối chiếu số event, hash hoặc aggregate.
10. **Resume:** cho phép workload chuyển dần về chế độ online bình thường.

### Handshake

Handshake giúp hai phía xác nhận:
- Edge identity và site.
- Protocol/schema version.
- Last cloud cursor.
- Last local sequence committed.
- Pending event count/bytes.
- Snapshot generation.
- Supported conflict policy.
- Device certificate status.
- Clock offset nếu cần.

Không gửi toàn bộ dữ liệu trước khi xác định hai phía đang đồng bộ từ checkpoint nào.

### Acknowledgement

Cloud chỉ nên acknowledge một event hoặc batch sau khi đã commit theo semantics được định nghĩa. Nếu ack trước commit, edge có thể xóa event rồi cloud crash, dẫn tới mất dữ liệu.

Acknowledgement nên chứa:
- Event ID hoặc sequence range.
- Commit status.
- Cloud cursor/watermark.
- Rejection/conflict code.
- Retryability.
- Result reference.

Edge chỉ xóa hoặc compact outbox record khi nhận ack hợp lệ và checkpoint đã được lưu an toàn.

## 9. Đồng bộ tăng dần và full resynchronization

### Delta sync

Delta sync chỉ truyền thay đổi kể từ cursor/checkpoint đã xác nhận:
- Ít băng thông.
- Thời gian phục hồi ngắn.
- Giảm tải cloud.
- Dễ ưu tiên event quan trọng.

Nhưng delta phụ thuộc event history còn đầy đủ và hai phía có checkpoint hợp lệ.

### Full snapshot

Full resync truyền lại snapshot hoặc trạng thái hiện tại:
- Phù hợp khi edge mất checkpoint.
- Phù hợp khi schema/state migration làm delta không tương thích.
- Có thể phục hồi sau khi event history hết retention.
- Tốn thời gian, storage và bandwidth.

### Chọn delta hay snapshot

Dùng delta khi:
- Cursor còn hợp lệ.
- Event history liên tục.
- Schema tương thích.
- Không có corruption.
- Khoảng offline nằm trong retention window.

Dùng snapshot khi:
- Edge cài mới hoặc mất local state.
- Sequence gap không thể khôi phục.
- Checkpoint bị hỏng.
- Delta history đã hết hạn.
- Hai phía không còn cùng schema generation.
- Integrity verification thất bại.

### Snapshot an toàn

Snapshot nên có:
- Snapshot ID và generation.
- Schema version.
- Created-at.
- Data scope.
- Content hash/manifest.
- Pagination/chunk manifest.
- Consistent watermark.
- Signature hoặc authentication metadata.

Không ghi đè database đang hoạt động từng phần trong lúc snapshot tải về. Tải vào staging area, xác minh checksum, kiểm tra schema rồi thực hiện atomic switch hoặc migration có rollback.

## 10. Ordering, sequence và versioning

Trong hệ thống phân tán, event có thể đến trễ, lặp hoặc sai thứ tự. Timestamp không phải lúc nào cũng đủ để xác định thứ tự.

### Sequence theo aggregate

Có thể cấp sequence tăng dần cho mỗi entity hoặc aggregate:
- Device 17: 101, 102, 103.
- Order 42: 8, 9, 10.
- Site inventory partition: offset riêng.

Sequence giúp phát hiện:
- Duplicate.
- Missing event.
- Out-of-order delivery.
- Replay.
- Stale update.

Không nhất thiết cần một global sequence cho toàn hệ thống. Global sequence có thể tạo bottleneck và không cần thiết nếu ordering chỉ quan trọng trong một aggregate.

### Event time và ingest time

- **Event time:** thời điểm nghiệp vụ xảy ra tại edge.
- **Ingest time:** thời điểm cloud nhận event.
- **Commit time:** thời điểm cloud áp dụng thay đổi.
- **Observed time:** thời điểm telemetry ghi nhận.

Đồng hồ edge có thể sai hoặc không đồng bộ khi offline. Dùng sequence và causal metadata cho ordering; dùng timestamp để phân tích thời gian với sai số được ghi nhận.

### Version và optimistic concurrency

Một record có thể có version tăng sau mỗi thay đổi. Khi cloud nhận update dựa trên version cũ, có thể:
- Chấp nhận nếu không có thay đổi cạnh tranh.
- Từ chối conflict để xử lý.
- Merge theo field/domain rule.
- Ghi thành proposal để người có quyền quyết định.

Ví dụ API cập nhật record với expected_version = 12. Nếu server hiện là 13, update dựa trên version 12 không nên ghi đè mù.

### Epoch và fencing token

Khi edge reconnect sau thời gian dài, cloud có thể đã cấp ownership hoặc lease mới cho node khác. Epoch/generation và fencing token giúp từ chối lệnh ghi từ worker cũ. Không dùng timestamp đơn thuần để bảo vệ quyền ghi khi có split-brain.

## 11. Xử lý duplicate và idempotency

Mất kết nối có thể xảy ra sau khi cloud đã commit nhưng trước khi edge nhận ack. Edge sẽ gửi lại event. Vì vậy duplicate là tình huống bình thường cần thiết kế trước.

### Event ID ổn định

Mỗi event cần ID duy nhất được tạo trước lần gửi đầu và giữ nguyên qua mọi retry. Không tạo event ID mới khi gửi lại cùng một thay đổi.

Cloud có thể lưu inbox/deduplication key:
- Edge ID.
- Event ID.
- Event type hoặc operation scope.
- Commit result.
- Received/committed timestamp.

### Idempotent apply

Một thao tác idempotent có thể được áp dụng lại mà không tạo thêm hiệu ứng nghiệp vụ. Ví dụ:
- Đặt trạng thái thiết bị thành giá trị xác định theo version.
- Ghi một record có unique business key.
- Upsert theo event ID.
- Tăng counter bằng event ledger có dedupe.

Thao tác "cộng thêm 5 vào tồn kho" không tự idempotent. Nếu gửi lại, giá trị tăng hai lần. Cần ghi nhận operation ID hoặc dùng transaction với inbox.

### Transactional inbox

Một pattern:
1. Nhận event.
2. Bắt đầu transaction.
3. Kiểm tra event ID đã có chưa.
4. Nếu đã commit, trả lại ack cũ.
5. Nếu chưa, ghi inbox record và cập nhật domain state.
6. Commit.
7. Trả acknowledgement.

Nếu domain update và inbox record cùng transaction, duplicate có thể được nhận diện an toàn.

### Không hứa exactly-once end-to-end

Network, queue và process có thể retry. Thực tế thường kết hợp at-least-once transport với idempotent consumer, deduplication và transactional state. Chỉ tuyên bố exactly-once trong phạm vi transaction cụ thể đã được chứng minh, không áp dụng chung cho toàn bộ chuỗi hệ thống.

## 12. Chiến lược giải quyết conflict

Conflict xảy ra khi hai phía cùng thay đổi một dữ liệu trước khi đồng bộ. Không có một policy đúng cho mọi loại dữ liệu.

### Last-write-wins

Chọn thay đổi có timestamp hoặc version mới hơn. Cách này đơn giản nhưng có thể mất update nếu clock sai hoặc hai thay đổi độc lập. Chỉ dùng khi dữ liệu có semantics cho phép thay thế hoàn toàn.

### Field-level merge

Nếu hai phía sửa các field khác nhau, có thể hợp nhất từng field. Cần định nghĩa field nào độc lập và field nào có invariant liên quan.

Ví dụ edge sửa ghi chú thiết bị, cloud sửa nhãn quản trị; hai field có thể merge. Nhưng edge sửa số lượng tồn kho và cloud sửa reservation có thể không merge độc lập vì liên quan invariant tổng.

### Domain-specific merge

Dùng logic nghiệp vụ:
- Inventory: áp dụng movement ledger thay vì ghi đè tổng số.
- Đơn hàng: transition hợp lệ theo state machine.
- Telemetry: append event, không overwrite.
- Cấu hình: cloud policy có thể là authority, edge chỉ gửi desired-state proposal.
- Counter: dùng operation ID hoặc CRDT counter nếu semantics phù hợp.

### Manual resolution

Với conflict ảnh hưởng tài chính, quyền truy cập, safety hoặc dữ liệu không thể khôi phục, đưa vào hàng đợi xử lý thủ công. UI cần cho biết:
- Hai phiên bản.
- Nguồn và thời điểm thay đổi.
- Ai tạo thay đổi.
- Lý do conflict.
- Hành động được phép.
- Audit record sau khi giải quyết.

### Bảng lựa chọn

| Loại dữ liệu | Policy thường phù hợp | Lý do |
|---|---|---|
| Telemetry append-only | Append + dedupe | Không ghi đè mẫu đo |
| Cấu hình trung tâm | Cloud-authoritative | Tránh edge ghi ngược policy |
| Ghi chú cục bộ | Field merge hoặc LWW | Rủi ro thấp nếu field độc lập |
| Inventory | Movement ledger / domain merge | Cần giữ invariant |
| Command state | Sequence + state machine | Thứ tự và quyền thực thi quan trọng |
| Giao dịch tài chính | Idempotency + central reconciliation | Không thể merge tùy tiện |
| Counter phân tán | CRDT hoặc operation ledger | Có thể cộng thay đổi độc lập nếu đúng semantics |

### Conflict không đồng nghĩa lỗi transport

Event đã tới cloud nhưng bị từ chối do version conflict là kết quả nghiệp vụ cần xử lý, không nên retry cùng payload vô hạn. Phân biệt transport retry, transient server error và semantic conflict.

## 13. Tránh split-brain và ghi đồng thời nguy hiểm

Split-brain xảy ra khi hai node cùng tin rằng mình có quyền authoritative và cùng cập nhật một state. Mất kết nối làm tăng rủi ro này.

### Cách hạn chế

- Chia ownership theo site/partition.
- Dùng lease có expiry và fencing token.
- Dùng epoch/generation tăng dần.
- Chỉ một writer cho aggregate khi invariant yêu cầu.
- Dùng quorum hoặc consensus cho dữ liệu cần consistency mạnh.
- Tạm dừng thao tác không thể phân xử offline.
- Reconcile trước khi cho phép writer mới tiếp tục.

### Lease không đủ nếu thiếu fencing

Một node có thể bị pause lâu, lease hết hạn và node khác được cấp lease mới. Node cũ thức dậy vẫn có thể gửi lệnh ghi. Fencing token tăng dần giúp storage/service từ chối token cũ.

### Khi nào phải từ chối offline write?

- Hai edge có thể cùng sửa một số dư hoặc inventory dùng chung.
- Thao tác cần unique global sequence.
- Lệnh cần xác nhận quyền mới nhất từ cloud.
- Policy hoặc credential đã bị thu hồi nhưng edge chưa biết.
- Tác động vật lý không thể đảo ngược.
- Không có đủ dữ liệu để xác minh điều kiện an toàn.

Thiết kế offline cần ghi rõ những thao tác bị hạn chế, không chỉ liệt kê các thao tác được hỗ trợ.

## 14. Đồng bộ dữ liệu lớn và bandwidth management

Edge có thể tạo file video, ảnh, model artifact, log hoặc dataset lớn. Truyền tất cả cùng lúc khi reconnect có thể chiếm đường truyền và làm chậm transaction.

### Metadata trước, payload sau

Một cách:
1. Đồng bộ event metadata và business state.
2. Gửi manifest của artifact.
3. Truyền file theo chunk.
4. Xác minh checksum.
5. Commit reference khi đủ chunk.
6. Xóa bản local theo retention sau khi xác nhận.

### Chunking và resume

Mỗi chunk nên có:
- Artifact ID.
- Chunk index.
- Byte range.
- Hash.
- Upload session ID.
- Expiry.
- Retry state.

Nếu kết nối mất giữa chừng, tiếp tục từ chunk chưa xác nhận. Không tải lại toàn bộ file nếu đã có multipart/resumable upload phù hợp.

### Điều tiết băng thông

Có thể áp dụng:
- Priority queue.
- Token bucket/rate limit.
- Compression.
- Delta encoding.
- Deduplication content hash.
- Schedule truyền ngoài giờ cao điểm.
- Giới hạn concurrency.
- Local cache.
- Separate channel cho control và bulk data.

Đừng nén dữ liệu đã nén hoặc mã hóa nếu chi phí CPU lớn hơn lợi ích băng thông. Benchmark theo CPU tại edge và chất lượng link.

## 15. Security khi edge offline lâu ngày

Offline làm chậm khả năng nhận policy update, certificate revocation và security patch. Vì vậy cần giới hạn thời gian tự chủ và dữ liệu được giữ cục bộ.

### Device identity

Mỗi edge node cần identity riêng:
- Certificate hoặc workload identity.
- Key được lưu trong TPM/secure element nếu có.
- Rotation policy.
- Device enrollment và decommission.
- Revocation khi mất thiết bị.
- Audit cho lần sync và thao tác nhạy cảm.

Không dùng một credential chung cho nhiều site. Nếu một thiết bị bị compromise, phạm vi thu hồi phải giới hạn được.

### Credential expiry và offline grace

Credential ngắn hạn tăng bảo mật nhưng có thể hết hạn khi site offline. Có thể thiết kế offline grace có giới hạn:
- Credential cache chỉ dùng trong thời gian tối đa.
- Quyền offline bị giới hạn theo operation.
- Không cho phép mở rộng privilege.
- Ghi lại thời điểm credential được cấp và expiry.
- Khi reconnect, xác minh revocation và refresh trước khi mở lại thao tác nhạy cảm.

Không kéo dài credential vô hạn chỉ để đảm bảo availability.

### Local data protection

- Encrypt-at-rest cho database, spool và disk.
- Encrypt-in-transit khi đồng bộ.
- Secure boot và image signing.
- Least privilege cho sync agent.
- Không lưu secret trong log.
- Chống rollback hoặc tamper nếu threat model yêu cầu.
- Secure deletion theo policy khi thiết bị decommission.

### Schema và payload validation

Cloud không nên tin payload chỉ vì nó đến từ edge đã đăng ký. Xác thực schema, size, sequence, signature khi cần và quyền của event type. Cô lập event malformed vào quarantine để tránh làm hỏng pipeline.

## 16. Schema evolution và tương thích khi offline dài ngày

Edge có thể offline trong lúc cloud được nâng cấp. Khi reconnect, edge có thể gửi event theo schema cũ.

Cần:
- Version envelope và payload.
- Backward-compatible field additions khi có thể.
- Consumer hỗ trợ nhiều schema trong thời gian migration.
- Explicit rejection cho version không còn hỗ trợ.
- Migration hoặc translation adapter.
- Retention window phù hợp với thời gian offline tối đa.
- Test event được tạo từ phiên bản edge cũ.

### Expand-and-contract

Một quy trình an toàn:
1. Cloud thêm khả năng đọc schema mới nhưng vẫn hỗ trợ schema cũ.
2. Edge được nâng cấp dần.
3. Theo dõi tỷ lệ event theo version.
4. Chờ hết offline grace và backlog cũ.
5. Chỉ sau đó mới loại bỏ schema cũ.

Không thay đổi semantics của field cũ mà không version. Một event được tạo offline có thể tới sau khi nhiều phiên bản cloud đã triển khai.

### Không migrate queue mù quáng

Nếu local queue có event cũ, migration cần:
- Backup/checkpoint.
- Xác minh schema.
- Chuyển đổi có thể lặp.
- Giữ original payload hoặc audit reference.
- Có rollback.
- Không đánh dấu ack trước khi dữ liệu mới được commit.

## 17. Đồng bộ thời gian và dữ liệu có thứ tự

Edge có thể mất NTP hoặc nguồn thời gian chuẩn trong thời gian dài. Đồng hồ có thể drift.

### Timestamp không phải sequence

Dùng monotonic clock để đo duration cục bộ; dùng wall clock để ghi thời gian thực; dùng sequence/version để xác định thứ tự thay đổi. Không so sánh timestamp từ hai edge khác nhau như một thứ tự tuyệt đối nếu chưa biết clock offset.

### Time metadata

Có thể lưu:
- event_time.
- observed_time.
- local_sequence.
- edge_epoch.
- cloud_received_at.
- cloud_committed_at.
- estimated_clock_offset.
- time_quality/status.

Nếu cần xử lý event theo event-time, dùng watermark và late-event policy. Nếu cần bảo vệ transaction ordering, ưu tiên sequence/transaction version.

### Clock correction

Khi reconnect:
- Đo clock offset.
- Không sửa ngược timestamp lịch sử.
- Ghi nhận time quality.
- Điều chỉnh lịch/lease tương lai.
- Kiểm tra certificate validity và token expiry.
- Tránh dùng clock local chưa tin cậy làm căn cứ duy nhất cho authorization.

## 18. Kiểm soát vòng đời dữ liệu pending

Một event offline có thể tồn tại lâu trong spool. Cần policy rõ:
- Maximum offline age.
- Retention.
- Expiry.
- Retry count.
- Dead-letter/quarantine.
- Manual replay.
- Data deletion.
- Legal hold.
- Priority downgrade.

### Expired event

Không phải mọi event cũ đều vô dụng. Telemetry cũ có thể vẫn cần cho audit; command điều khiển cũ có thể phải hết hạn vì không còn an toàn khi thực thi muộn.

Mỗi event type nên có semantics:
- Có được thực thi muộn không?
- Có thể bỏ qua không?
- Có cần báo người dùng không?
- Có phải chuyển sang manual review không?
- Có thể tổng hợp thành snapshot thay vì replay từng event không?

### Tombstone và deletion

Nếu cloud yêu cầu xóa dữ liệu, edge offline có thể chưa nhận lệnh. Khi reconnect, cần đồng bộ tombstone hoặc deletion marker theo version. Không để một snapshot cũ tự phục hồi dữ liệu đã bị xóa theo policy.

## 19. Ví dụ: cửa hàng bán lẻ mất WAN

Một cửa hàng có POS, inventory cache, máy in hóa đơn và kết nối về cloud. Khi WAN mất:
- POS tiếp tục ghi giao dịch local.
- Mỗi giao dịch có transaction ID duy nhất.
- Giá và danh mục dùng snapshot có version/TTL.
- Hạn mức offline payment được áp dụng.
- Inventory local được ghi như movement ledger.
- Giao dịch được lưu trong local database và outbox.
- UI hiển thị offline mode và giới hạn chức năng.

Khi kết nối trở lại:
1. Edge xác thực thiết bị.
2. Gửi handshake với last sequence.
3. Cloud trả cursor và policy hiện tại.
4. Edge gửi giao dịch theo thứ tự yêu cầu.
5. Cloud deduplicate theo transaction ID.
6. Inventory service áp dụng movement ledger và kiểm tra invariant.
7. Cloud trả ack và kết quả conflict.
8. Edge cập nhật trạng thái giao dịch đã sync.
9. Artifact/log dung lượng lớn được upload sau.
10. Dashboard báo backlog bằng 0 và reconciliation hoàn tất.

### Trường hợp xung đột inventory

Hai cửa hàng cùng offline và cùng bán một mặt hàng trong khi inventory trung tâm không được cập nhật. Không thể đảm bảo tổng tồn kho toàn hệ thống nếu cả hai được phép bán vô hạn từ cùng một số lượng.

Giải pháp có thể gồm:
- Phân bổ quota/reservation tồn kho trước cho từng cửa hàng.
- Giới hạn số lượng bán offline.
- Cho phép oversell trong ngưỡng được nghiệp vụ chấp nhận và có quy trình xử lý.
- Chặn mặt hàng rủi ro cao khi offline.

Policy phụ thuộc business risk; đồng bộ sau đó không thể làm một mặt hàng vật lý đã bán trở lại tồn kho.

## 20. Ví dụ: edge gateway tại nhà máy

Một gateway tại nhà máy thu telemetry và điều khiển một phần thiết bị trong mạng OT. Cloud dùng để tổng hợp, phân tích và cập nhật cấu hình.

Khi mất kết nối:
- Điều khiển cục bộ tiếp tục theo policy đã xác minh.
- Telemetry được buffer trên disk.
- Cảnh báo an toàn quan trọng được lưu với priority cao.
- Command từ cloud cũ hoặc hết hạn không được thực thi muộn.
- Operator tại chỗ vẫn có khả năng quan sát trạng thái.
- Sync agent không can thiệp vào control loop thời gian thực.

Khi reconnect:
- Xác thực gateway và kiểm tra certificate.
- So sánh configuration generation.
- Đồng bộ audit và alarm trước telemetry dung lượng lớn.
- Gửi dữ liệu theo chunk với checksum.
- Nhận cấu hình mới vào staging.
- Kiểm tra chữ ký, version và policy.
- Chỉ activate cấu hình theo quy trình được phê duyệt.
- Đối chiếu event sequence và dữ liệu bị thiếu.

Không để tiến trình đồng bộ cloud làm nghẽn CPU, network hoặc storage của control function. Tách resource budget và network path cho control plane cục bộ với bulk synchronization.

## 21. Ví dụ giao thức event envelope

Một event có thể mang metadata chuẩn:

~~~json
{
  "event_id": "evt-01J9EDGEA7",
  "edge_id": "site-042-gateway-01",
  "edge_epoch": 18,
  "sequence": 10452,
  "aggregate_type": "device-state",
  "aggregate_id": "device-17",
  "event_type": "DeviceReadingRecorded",
  "schema_version": 3,
  "event_time": "2026-11-22T10:15:30Z",
  "local_recorded_at": "2026-11-22T10:15:31Z",
  "correlation_id": "job-2026-11-22-0042",
  "payload_ref": "local-object://telemetry/part-10452",
  "payload_sha256": "example-checksum",
  "priority": "normal"
}
~~~

Ví dụ chỉ minh họa cấu trúc. Production cần quy định:
- Event ID duy nhất và ổn định.
- Sequence scope rõ ràng.
- Payload reference có thể truy cập theo quyền.
- Hash được tính từ nội dung thực.
- Timestamp có timezone.
- Schema version được hỗ trợ.
- Không đưa secret hoặc dữ liệu nhạy cảm vào metadata.

### Batch acknowledgement

Cloud có thể trả kết quả theo event:
- committed.
- duplicate_already_committed.
- rejected_schema.
- conflict_requires_resolution.
- expired.
- retryable_failure.

Không chỉ trả một HTTP 200 cho cả batch nếu một số event bị từ chối. Edge cần biết chính xác event nào đã commit để cập nhật checkpoint đúng.

## 22. Quan sát và cảnh báo đồng bộ

Dashboard cần hiển thị trạng thái kết nối và trạng thái dữ liệu riêng biệt.

### Connectivity metrics

- connection_state.
- last_successful_handshake.
- probe_failure_count.
- reconnect_attempts.
- TLS/authentication failure.
- round-trip latency.
- packet loss.
- clock offset.

### Sync metrics

- pending_event_count.
- pending_bytes.
- oldest_pending_event_age.
- upload/download throughput.
- last_acked_sequence.
- sequence_gap_count.
- duplicate_event_count.
- conflict_count.
- rejected_event_count.
- snapshot_generation.
- sync_lag_seconds.
- full_resync_duration.
- checksum_failure_count.

### Local resource metrics

- spool disk used/free.
- database size.
- WAL growth.
- compaction backlog.
- CPU/memory usage of sync agent.
- dropped telemetry count.
- oldest unacknowledged event.
- local storage health.

### Alert quan trọng

- Edge offline lâu hơn offline grace.
- Pending bytes gần đầy disk.
- Oldest business event vượt deadline.
- Sequence gap không thể tự phục hồi.
- Authentication/certificate failure.
- Conflict rate tăng đột biến.
- Sync throughput thấp hơn incoming event rate.
- Checksum hoặc signature verification thất bại.
- Snapshot quá cũ hoặc schema không còn hỗ trợ.
- Cloud ack không tiến triển.

Không chỉ alert "edge offline". Cần biết site có đang tiếp tục hoạt động, buffer còn bao nhiêu dung lượng và có nguy cơ mất dữ liệu hay không.

## 23. Quy trình phục hồi sau khi kết nối trở lại

Một runbook reconnect có thể gồm:

1. **Xác nhận đường truyền:** DNS, TLS, API và authentication đều hoạt động.
2. **Kiểm tra edge identity:** certificate, device status, revocation và epoch.
3. **Đọc local health:** disk, database, WAL, outbox và checksum.
4. **Handshake:** trao đổi schema, cursor, sequence và snapshot generation.
5. **Phân loại backlog:** business event, audit, telemetry, artifact.
6. **Đồng bộ ưu tiên cao:** giao dịch và security event trước.
7. **Xử lý duplicate:** cloud trả lại kết quả đã commit.
8. **Xử lý gap/conflict:** replay, snapshot hoặc manual resolution.
9. **Đồng bộ inbound delta:** cập nhật state từ cloud theo ownership policy.
10. **Upload artifact lớn:** resumable chunk và checksum.
11. **Commit checkpoint:** chỉ sau khi dữ liệu đã được áp dụng bền vững.
12. **Verify:** so sequence range, count và hash/manifest.
13. **Giảm backlog:** tăng throughput từ từ, theo dõi downstream.
14. **Reconcile nghiệp vụ:** kiểm tra số giao dịch, inventory hoặc state quan trọng.
15. **Trở lại online:** chỉ khi sync lag và consistency đạt điều kiện.
16. **Lưu audit:** thời gian outage, dữ liệu replay, conflict và hành động operator.

### Không chuyển online chỉ vì queue rỗng

Queue có thể rỗng vì event đã bị drop hoặc bị chuyển DLQ. Điều kiện hoàn tất cần bao gồm:
- Không còn event pending thuộc priority cần thiết.
- Không có sequence gap chưa giải quyết.
- Snapshot/delta đã được xác minh.
- Conflict quan trọng đã được xử lý.
- Cloud và edge có checkpoint tương thích.
- Business reconciliation đạt tiêu chí.

### Phục hồi từng phần

Một edge có thể đồng bộ xong transaction nhưng vẫn còn log hoặc video. Có thể cho phép business online trong khi bulk data tiếp tục truyền, nếu policy và workload cho phép. Trạng thái cần thể hiện rõ "business sync complete, bulk upload pending".

## 24. Kiểm thử disconnected operation

Không chỉ rút cáp mạng một lần. Cần kiểm thử nhiều kiểu lỗi:

- Mất WAN hoàn toàn.
- DNS lỗi nhưng IP route còn.
- TLS certificate hết hạn.
- Token hết hạn trong lúc offline.
- Packet loss và latency cao.
- Kết nối chập chờn liên tục.
- Cloud nhận event nhưng ack bị mất.
- Edge crash sau local commit.
- Edge crash sau cloud commit trước ack.
- Disk gần đầy hoặc WAL tăng nhanh.
- Sequence gap hoặc event bị hỏng.
- Snapshot download bị gián đoạn.
- Hai edge cùng cập nhật dữ liệu.
- Schema cloud mới, edge cũ.
- Clock drift.
- Device bị revoke khi đang offline.

### Tiêu chí kiểm thử

- Không mất event đã xác nhận ghi local theo durability policy.
- Duplicate không tạo side effect trùng.
- Event ordering được giữ trong scope yêu cầu.
- Conflict được giải quyết hoặc đưa manual queue.
- Storage không vượt ngưỡng không kiểm soát.
- Control loop cục bộ vẫn đáp ứng yêu cầu.
- Reconnect không làm cloud/database quá tải.
- Checkpoint chỉ tiến sau commit.
- Có thể phục hồi sau crash ở mọi điểm quan trọng.
- Audit cho biết event nào đã nhận, commit, reject hoặc replay.

### Chaos test và diễn tập

Thực hiện diễn tập định kỳ theo thời gian outage giả định: 15 phút, vài giờ và nhiều ngày nếu yêu cầu. Kiểm tra cả capacity buffer, credential grace, schema compatibility và tốc độ drain backlog.

## 25. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ buffer trong RAM | Mất dữ liệu khi crash/mất điện | Durable local database hoặc spool |
| Gửi event rồi xóa local ngay | Mất event nếu ack không tới hoặc cloud chưa commit | Chờ acknowledgement sau commit |
| Retry tạo event ID mới | Deduplication không nhận ra duplicate | Giữ event ID ổn định qua retry |
| Dùng timestamp để sắp thứ tự tuyệt đối | Clock drift làm event bị đảo | Sequence/version theo aggregate |
| Cả cloud và edge cùng ghi không policy | Lost update và split-brain | Ownership, version, lease và conflict rule |
| Gửi toàn bộ backlog cùng lúc | Nghẽn WAN và downstream | Priority, rate limit và backpressure |
| Xem ping thành công là online | API/auth vẫn có thể lỗi | Handshake và end-to-end probe |
| Không quản lý schema cũ | Edge offline lâu không sync được | Versioning và expand-and-contract |
| Xóa queue khi disk đầy | Mất transaction/audit | Quota, admission control và retention policy |
| Sync agent chiếm resource control | Ảnh hưởng workload tại chỗ | Resource isolation và bandwidth budget |
| Tin last-write-wins cho mọi dữ liệu | Mất cập nhật có ý nghĩa | Domain-specific conflict resolution |
| Không xác minh snapshot | State hỏng lan vào hệ thống | Manifest, checksum, signature và atomic switch |
| Không theo dõi clock drift | Lease/certificate/order sai | Time quality metric và sequence |
| Cho phép lệnh cũ chạy muộn | Hành động không còn an toàn | Expiry, generation và command state machine |

## 26. Quy trình thiết kế disconnected operation

1. **Inventory dependency:** liệt kê cloud API, identity, DNS, database, queue, storage và control service.
2. **Phân loại nghiệp vụ:** online-only, offline-capable, degraded hoặc fail-safe.
3. **Xác định ownership:** cloud, edge, partitioned hay shared.
4. **Thiết kế local state:** database, outbox, checkpoint và retention.
5. **Tính offline capacity:** event rate, payload, outage duration và growth margin.
6. **Định nghĩa event contract:** ID, sequence, schema, timestamp và priority.
7. **Thiết kế sync protocol:** handshake, delta, snapshot, ack và checkpoint.
8. **Thiết kế idempotency:** inbox, dedupe và transactional apply.
9. **Định nghĩa conflict policy:** theo từng domain/entity.
10. **Chống split-brain:** epoch, lease, fencing và write ownership.
11. **Thiết kế security:** identity, key rotation, offline grace và local encryption.
12. **Đặt backpressure:** rate, queue class, retry và storage threshold.
13. **Thiết kế observability:** connectivity, backlog, sync lag, conflict và disk.
14. **Xây recovery runbook:** ưu tiên, reconcile, verify và online criteria.
15. **Kiểm thử outage:** network, crash, duplicate, schema, clock và capacity.
16. **Diễn tập định kỳ:** đo RPO, RTO, backlog drain time và data integrity.

## 27. Checklist production

### Offline capability
- [ ] Đã phân loại chức năng offline, degraded, online-only và fail-safe.
- [ ] Có owner và policy cho từng loại dữ liệu.
- [ ] Edge chỉ thực hiện thao tác được phép trong offline grace.
- [ ] Có UI/API thể hiện trạng thái offline và dữ liệu stale.
- [ ] Có giới hạn chức năng khi cache hoặc credential quá cũ.

### Local durability
- [ ] Event được ghi bền vững trước khi xác nhận thành công.
- [ ] Có outbox/store-and-forward.
- [ ] Business state và outbox được commit nhất quán.
- [ ] Buffer capacity đủ cho outage mục tiêu và growth margin.
- [ ] Có disk threshold, backpressure và retention.
- [ ] Không xóa event chưa ack theo policy.

### Synchronization
- [ ] Có handshake và edge identity.
- [ ] Có cursor/sequence và checkpoint.
- [ ] Delta và full snapshot có tiêu chí lựa chọn.
- [ ] Ack chỉ trả sau commit.
- [ ] Event ID ổn định và consumer idempotent.
- [ ] Có xử lý duplicate, out-of-order và sequence gap.
- [ ] Có checksum/manifest và atomic snapshot activation.
- [ ] Có rate limit, priority và resumable upload.

### Consistency và security
- [ ] Ownership cloud/edge được định nghĩa.
- [ ] Conflict policy theo domain.
- [ ] Có epoch/fencing khi cần chống split-brain.
- [ ] Credential offline grace có giới hạn.
- [ ] Local data được mã hóa và access control.
- [ ] Schema tương thích với edge offline lâu ngày.
- [ ] Clock drift được đo và không dùng timestamp làm thứ tự duy nhất.
- [ ] Event expired/revoked được xử lý theo policy.

### Operations
- [ ] Dashboard có connectivity, pending bytes, oldest event age và sync lag.
- [ ] Alert cho disk, auth, sequence gap, conflict và backlog.
- [ ] Có runbook reconnect và manual conflict resolution.
- [ ] Có kiểm thử crash ở các điểm commit/ack.
- [ ] Có diễn tập outage và đo thời gian drain backlog.
- [ ] Có reconciliation nghiệp vụ trước khi đánh dấu online hoàn toàn.
- [ ] Có audit trail cho replay, reject, conflict và operator action.

## Kết luận

Vận hành khi mất kết nối cần xác định trước những nghiệp vụ edge được phép tiếp tục, dữ liệu nào có thể ghi cục bộ và nơi nào là nguồn có thẩm quyền. Store-and-forward với local durable outbox giúp giữ thay đổi qua outage; handshake, delta/snapshot, sequence, acknowledgement và checkpoint giúp đồng bộ có thể tiếp tục sau gián đoạn. Duplicate và event đến sai thứ tự phải được xử lý bằng ID ổn định, idempotency, versioning và transaction; conflict cần policy theo domain, còn split-brain cần ownership, lease hoặc fencing phù hợp. Khi reconnect, ưu tiên dữ liệu quan trọng, điều tiết backlog, xác minh integrity và đối soát nghiệp vụ trước khi chuyển về online hoàn toàn. Thiết kế tốt giữ được khả năng hoạt động tại edge mà vẫn bảo vệ tính nhất quán, an toàn và khả năng truy vết của toàn hệ thống.
