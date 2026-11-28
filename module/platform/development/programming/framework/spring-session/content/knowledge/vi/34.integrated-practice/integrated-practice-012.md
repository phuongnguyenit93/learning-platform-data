# Tạo sự cố kho, thu bằng chứng và thực hiện quy trình phục hồi

Spring Session lưu trạng thái phiên trong một kho dùng chung như Redis hoặc JDBC để nhiều instance Spring có thể xử lý request của cùng một người dùng. Khi kho session gặp sự cố, ảnh hưởng không chỉ là lỗi cache: ứng dụng có thể không tải được SecurityContext, không lưu được lần đăng nhập mới, không cập nhật được lastAccessedTime hoặc không thu hồi được phiên khi logout.

Bài thực hành này mô phỏng một sự cố kho session trong môi trường nhiều instance. Mục tiêu là nhận diện phạm vi ảnh hưởng, thu thập bằng chứng trước khi thay đổi hệ thống, phân loại lỗi ứng dụng/mạng/backend, chọn hành động giảm thiểu phù hợp, khôi phục dịch vụ và xác minh an toàn sau phục hồi. Quy trình áp dụng cho Redis và JDBC, nhưng lệnh chẩn đoán cụ thể khác nhau theo backend và nền tảng triển khai.

## 1. Kịch bản sự cố

Một ứng dụng thương mại điện tử chạy ba instance Spring Session phía sau load balancer. Tất cả instance sử dụng chung Redis để lưu session. Trong giờ cao điểm, người dùng báo:

- Một số request trả 5xx hoặc timeout.
- Một số người dùng bị yêu cầu đăng nhập lại dù cookie vẫn còn.
- Đăng nhập mới đôi khi thành công ở bước xác thực nhưng response kết thúc bằng lỗi.
- Logout hoặc cập nhật giỏ hàng không ổn định.
- Dashboard Redis cho thấy độ trễ tăng, số kết nối cao và bộ nhớ gần giới hạn.

Giả thuyết ban đầu có thể là Redis quá tải, mạng giữa ứng dụng và Redis có vấn đề, connection pool cạn, Redis failover, maxmemory/noeviction gây lỗi ghi hoặc session key bị eviction. Không kết luận nguyên nhân chỉ từ biểu hiện người dùng bị logout: session miss cũng có thể do cookie sai, namespace lệch, serializer không tương thích hoặc session hết hạn thật.

### Mục tiêu phục hồi

1. Bảo vệ chức năng xác thực và dữ liệu phiên còn hợp lệ.
2. Xác định ứng dụng nào, instance nào và nhóm request nào bị ảnh hưởng.
3. Thu bằng chứng đủ để xác định nguyên nhân gốc.
4. Khôi phục khả năng đọc/ghi session có kiểm soát.
5. Xác minh login, request đã xác thực, cập nhật session, logout và expiration.
6. Ghi nhận dữ liệu nào có thể đã mất và quyết định có cần yêu cầu đăng nhập lại.

## 2. Hiểu đường đi của session trước khi điều tra

Một request đi qua SessionRepositoryFilter. Filter đọc session ID qua cookie hoặc header, tải session từ repository khi cần, cho ứng dụng truy cập HttpSession và lưu thay đổi theo lifecycle của request.

~~~mermaid
flowchart TD
    C["Browser / API client"] --> LB["Load balancer"]
    LB --> A["Spring instance A"]
    LB --> B["Spring instance B"]
    LB --> D["Spring instance C"]
    A --> F["SessionRepositoryFilter"]
    B --> G["SessionRepositoryFilter"]
    D --> H["SessionRepositoryFilter"]
    F --> R[("Shared Redis / JDBC")]
    G --> R
    H --> R
    R --> F
    R --> G
    R --> H
~~~

Các điểm cần kiểm tra:

- Tất cả instance có dùng cùng backend, endpoint, namespace/schema và serializer không?
- Có bao nhiêu ứng dụng dùng chung Redis hoặc database?
- Cookie name, Domain, Path, Secure, SameSite hoặc header resolver có đồng nhất không?
- Spring Session có được auto-configure đúng và SessionRepositoryFilter có mặt trên mọi node không?
- Spring Security có lưu SecurityContext trong session không?
- Redis/JDBC có HA, replication, backup và monitoring như thế nào?
- Ứng dụng có local fallback hoặc cache session riêng không?

Nên có sơ đồ kết nối, tên service, địa chỉ endpoint nội bộ, namespace/schema, owner backend và runbook sẵn trước sự cố. Không lưu password, token hoặc session ID trong sơ đồ hay ticket.

## 3. Nhận biết sự cố và xác định phạm vi ảnh hưởng

Khi cảnh báo hoặc ticket xuất hiện, ghi nhận:

- Thời điểm bắt đầu và thời điểm phát hiện.
- Endpoint, HTTP status và tỷ lệ lỗi.
- Instance/pod/zone xử lý request.
- Redis/JDBC latency, error rate, connection count và CPU/memory.
- Tỷ lệ login failure, session lookup miss và logout failure.
- Số người dùng/tenant bị ảnh hưởng, nếu có thể xác định mà không thu thập dữ liệu nhạy cảm.
- Thay đổi gần nhất: deploy, cấu hình, secret rotation, network policy, failover, migration hoặc tăng tải.

Phân biệt các nhóm biểu hiện:

| Biểu hiện | Hướng nghi ngờ | Bằng chứng cần lấy |
| --- | --- | --- |
| Tất cả instance lỗi cùng lúc | Backend hoặc mạng dùng chung | Redis/JDBC health, network metrics, backend logs |
| Chỉ một instance lỗi | Cấu hình, DNS, pool hoặc network của node | Pod events, app logs, connection metrics |
| Chỉ login mới lỗi | Lỗi create/save hoặc ghi SecurityContext | Save latency, OOM/SQL errors, auth logs |
| Session cũ đọc được nhưng cập nhật lỗi | Backend read OK, write path có vấn đề | Redis write error, JDBC transaction/constraint |
| Người dùng bị logout hàng loạt | Session miss, eviction, restore hoặc namespace mismatch | evicted_keys, TTL, failover, deploy/config history |
| Request chậm nhưng ít lỗi | Saturation hoặc queueing | p95/p99, pool wait, CPU, Redis command latency |
| Logout không có hiệu lực | Delete failure hoặc node dùng store khác | deleteById errors, namespace/schema, stale cache |

Đừng xem một session miss là bằng chứng backend đã xóa session. Trước hết phải phân biệt session không tồn tại/hết hạn với lỗi không truy cập được kho. Nếu repository hoặc wrapper biến lỗi backend thành null, đó là lỗi cần điều tra riêng.

## 4. Bảo toàn bằng chứng trước khi thay đổi

Trong giai đoạn đầu, ưu tiên thao tác chỉ đọc. Ghi lại thời điểm, múi giờ, nguồn lấy dữ liệu và người thực hiện. Giữ log/metrics theo retention phù hợp để có thể đối chiếu trước và sau khi phục hồi.

Thu thập:

- Application logs của tất cả instance bị ảnh hưởng.
- Load balancer/reverse proxy access logs đã redact cookie và session header.
- Metrics Redis/JDBC và dashboard trong khoảng thời gian xảy ra sự cố.
- Redis slow log hoặc database slow query log nếu đã bật.
- Pod/container restart, OOM kill, readiness/liveness failures và deployment events.
- Thay đổi cấu hình, secret, network policy và hạ tầng.
- Error stack trace đã loại bỏ session ID, cookie, token và dữ liệu người dùng.
- Snapshot/backup metadata: thời điểm tạo, trạng thái hoàn tất, key ID mã hóa và vị trí lưu.

Không ghi hoặc gửi nguyên giá trị Cookie, Set-Cookie, header session, SecurityContext hay toàn bộ session attributes vào ticket. Session ID là bearer credential. Nếu cần đối chiếu cùng một phiên trong log, dùng correlation ID ngẫu nhiên riêng không thể dùng để xác thực.

Không chạy lệnh xóa, flush, restore, failover thủ công hoặc thay maxmemory policy trong khi chưa hiểu phạm vi ảnh hưởng. Không khởi động lại tất cả instance cùng lúc: việc đó có thể làm mất thêm bằng chứng và tạo thêm tải reconnect lên backend.

## 5. Thu bằng chứng từ ứng dụng Spring

Từ mỗi instance, thu thập:

- Timestamp, instance ID, pod/host và zone.
- Tỷ lệ request thành công/thất bại theo endpoint.
- Exception class và nguyên nhân gốc khi repository truy cập backend.
- Redis/JDBC connection pool active, idle, pending và timeout.
- Repository find/save/delete latency và error count nếu đã instrument.
- JVM heap, GC pause, thread pool và request queue.
- Phiên bản ứng dụng, Spring Boot, Spring Session và Spring Data client.
- Runtime configuration không nhạy cảm: backend type, namespace/schema, timeout, cookie/header resolver và flush/save mode.

Ví dụ log lỗi cần phân loại:

~~~text
Session repository read failed
instance=app-2
operation=findById
backend=redis
exception=RedisConnectionFailureException
correlationId=req-7f3a
~~~

Ví dụ trên không ghi session ID hoặc cookie. Giữ cause chain để phân biệt timeout, DNS failure, authentication failure, TLS error, OOM và lỗi serialization.

### Kiểm tra khác biệt giữa các instance

So sánh các giá trị:

- Redis host/cluster endpoint và TLS mode.
- Namespace.
- JDBC URL/schema/table name.
- Serializer và classpath.
- Session timeout.
- Cookie name hoặc header resolver.
- Spring Session repository implementation.

Nếu chỉ một node có namespace hoặc serializer khác, request được load balancer chuyển đến node đó có thể nhận session miss hoặc deserialize error. Không giải quyết bằng sticky session; sửa cấu hình lệch và xác minh rollout.

## 6. Chẩn đoán Redis theo hướng chỉ đọc

Với Redis, thu thập tình trạng server bằng công cụ được cấp quyền:

~~~text
PING
INFO server
INFO clients
INFO memory
INFO stats
INFO persistence
INFO replication
ROLE
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
~~~

Managed Redis có thể giới hạn CONFIG GET hoặc ROLE. Dùng dashboard/API chính thức của nhà cung cấp nếu command bị chặn. Không thử bypass quyền quản trị.

Các thông tin cần xem:

- Server có trả lời PING ổn định không?
- used_memory, used_memory_peak, maxmemory và used_memory_rss.
- maxmemory-policy hiện tại.
- evicted_keys và expired_keys có tăng đột biến không?
- connected_clients, blocked_clients và client buffer.
- rejected connections hoặc error count.
- master/replica role, replication link và lag.
- RDB/AOF trạng thái gần nhất và lỗi persistence.
- Command latency, slow log và network throughput.

Nếu Redis báo OOM khi maxmemory-policy là noeviction, thao tác ghi có thể bị từ chối. Nếu evicted_keys tăng, key session có thể bị loại bỏ trước idle timeout. Nếu replication lag tăng, failover có thể làm mất các write gần đây. Đây là ba tình huống khác nhau và cần phương án phục hồi riêng.

### Các lệnh quan sát bổ sung

Trong môi trường kiểm soát, có thể dùng:

~~~text
SLOWLOG GET 20
LATENCY LATEST
CLIENT LIST
~~~

CLIENT LIST có thể chứa địa chỉ client và metadata kết nối; hạn chế quyền xem và redact trước khi chia sẻ. Tránh dùng MONITOR liên tục trong production vì overhead lớn và có thể làm lộ command/data. Tránh KEYS * trên kho lớn vì có thể chặn Redis; dùng SCAN có giới hạn khi cần khảo sát key theo namespace.

Không đọc payload session thật chỉ để xác nhận sự cố. Nếu bắt buộc phải kiểm tra cấu trúc, dùng bản sao đã được bảo vệ trong môi trường cô lập và dữ liệu đã được phê duyệt.

## 7. Chẩn đoán JDBC theo hướng chỉ đọc

Với Spring Session JDBC, kiểm tra:

- Database endpoint, DNS, TLS và authentication.
- Connection pool active/idle/pending và acquisition timeout.
- Số connection đang mở, transaction duration và lock waits.
- Query latency, deadlock, rollback và constraint errors.
- CPU, memory, IOPS, storage latency và replication lag.
- Số lượng hàng trong bảng session và bảng attributes.
- Index/query plan của truy vấn find/update/cleanup.
- Trạng thái schema migration giữa các instance.

Ví dụ truy vấn tổng quan, điều chỉnh tên schema/bảng theo phiên bản:

~~~sql
SELECT COUNT(*) AS session_rows
FROM SPRING_SESSION;

SELECT COUNT(*) AS attribute_rows
FROM SPRING_SESSION_ATTRIBUTES;
~~~

Chỉ chạy truy vấn trên khi có quyền đọc và biết đúng schema. COUNT trên bảng rất lớn có thể tốn tài nguyên; dùng thống kê hệ quản trị hoặc bảng monitoring nếu phù hợp. Không SELECT toàn bộ serialized attributes để đưa vào ticket.

Kiểm tra lỗi connection pool trước khi tăng pool size. Tăng số connection quá mức có thể làm database quá tải hơn. Nếu database đang lock hoặc cạn I/O, ưu tiên giảm tải và tìm query/transaction gây nghẽn.

## 8. Phân loại nguyên nhân gốc

Một cây quyết định giúp thu hẹp phạm vi:

~~~mermaid
flowchart TD
    A["Session request lỗi"] --> B{"Instance có kết nối backend?"}
    B -->|Không| C["Kiểm tra DNS, network, TLS, credentials"]
    B -->|Có| D{"Backend có trả lời ổn định?"}
    D -->|Không| E["Kiểm tra saturation, failover, DB/Redis health"]
    D -->|Có| F{"Lỗi chủ yếu ở read hay write?"}
    F -->|Read| G["Kiểm tra namespace, ID resolver, expiry, serializer"]
    F -->|Write| H["Kiểm tra OOM, transaction, pool, flush/save mode"]
    G --> I["Đối chiếu session miss với TTL, eviction và deploy"]
    H --> J["Giảm tải, sửa capacity hoặc schema/config"]
    I --> K["Chọn phục hồi có kiểm soát"]
    J --> K
    C --> K
    E --> K
~~~

Các nhóm nguyên nhân:

1. **Network/DNS/TLS:** instance không thể kết nối hoặc xác minh chứng chỉ backend.
2. **Authentication/ACL:** Redis ACL hoặc database credential bị thay đổi, hết hạn hay thiếu quyền.
3. **Capacity:** Redis maxmemory, database connection pool, CPU, IOPS hoặc storage đã bão hòa.
4. **Eviction/expiration:** key session bị loại bỏ hoặc hết hạn.
5. **Failover/replication:** node mới không có đầy đủ write gần nhất.
6. **Configuration drift:** namespace, schema, timeout, serializer hoặc resolver khác nhau.
7. **Application defect:** serialize lỗi, request ghi session quá lớn, custom repository bug hoặc filter order sai.
8. **Schema/version mismatch:** code mới chạy với schema cũ hoặc các node dùng phiên bản không tương thích.

Không thay đổi đồng thời nhiều biến. Thay một nguyên nhân có giả thuyết rõ, quan sát kết quả và ghi lại thời điểm để tránh làm mất khả năng xác định root cause.

## 9. Đánh giá mức độ ảnh hưởng và quyết định containment

Phân loại theo chức năng:

- Request công khai không dùng session.
- Request cần đọc session để xác thực.
- Login mới cần tạo và ghi session.
- Request cập nhật session attributes.
- Logout/thu hồi session.
- Tác vụ nền hoặc WebSocket phụ thuộc session.

Nếu repository không truy cập được, request cần xác minh session phải fail closed. Không bỏ qua lỗi rồi cho phép request được bảo vệ tiếp tục như người dùng đã xác thực. Không fallback sang local in-memory session trên từng node: điều này tạo nhiều bản session không đồng nhất và có thể khiến logout ở node A không có hiệu lực ở node B.

Containment có thể gồm:

- Giảm hoặc tạm dừng endpoint không thiết yếu đang tạo nhiều session.
- Giới hạn retry và request concurrency.
- Tách workload cache không quan trọng khỏi Redis session nếu đang dùng chung.
- Tăng capacity theo quy trình hạ tầng đã được phê duyệt.
- Chuyển traffic khỏi node ứng dụng có cấu hình sai.
- Nếu backend đang failover, chờ endpoint ổn định và kiểm tra replication trước khi mở lại traffic.

Không xóa cookie hàng loạt khi chưa xác định session còn nguyên vẹn. Không khôi phục snapshot cũ ngay khi backend vừa lên: snapshot có thể làm mất session mới hoặc hồi sinh session đã logout/thu hồi.

## 10. Quy trình phục hồi Redis

### Trường hợp A: Redis tạm mất kết nối

1. Xác nhận DNS, route, TLS certificate và ACL.
2. Kiểm tra Redis endpoint và trạng thái HA.
3. Xác nhận ứng dụng reconnect được bằng health check.
4. Kiểm tra read/write test bằng namespace kiểm thử riêng và dữ liệu giả.
5. Mở traffic từng phần, theo dõi lỗi repository và latency.

Không dùng lệnh ghi trực tiếp vào key session production để thử kết nối.

### Trường hợp B: Redis đầy với noeviction

1. Xác nhận OOM/rejected write và mức memory.
2. Xác định workload nào chiếm bộ nhớ; không giả định toàn bộ là session.
3. Nếu dùng chung cache, giảm tải hoặc tách workload cache theo runbook.
4. Mở rộng memory hoặc chuyển sang node/cluster có capacity đã chuẩn bị.
5. Xác nhận headroom trước khi cho phép tạo session mới.
6. Thực hiện login/update test với account giả.

Không chuyển sang allkeys-lru chỉ để hết OOM nếu session cần tồn tại đến timeout. Chính sách eviction có thể làm mất phiên đang hoạt động. Thay đổi maxmemory-policy là quyết định kiến trúc và bảo mật, không phải thao tác chữa cháy mặc định.

### Trường hợp C: Eviction làm mất session

1. Ghi nhận evicted_keys và thời gian bắt đầu tăng.
2. Xác định session miss có tương quan với eviction không.
3. Dừng áp lực từ workload cache hoặc mở rộng capacity.
4. Đánh giá session nào có thể đã mất; không thể khôi phục attributes chỉ từ cookie.
5. Yêu cầu người dùng xác thực lại theo chính sách nếu session record không còn.
6. Xác minh logout/revocation và không tạo session thay thế từ ID cũ.

Không tự tái tạo SecurityContext hoặc quyền từ dữ liệu trong cookie. Cookie chỉ là định danh, không phải bản sao session có thể tin cậy.

### Trường hợp D: Redis failover hoặc restore

1. Xác nhận role, replication link, lag và persistence status.
2. Xác định write nào có thể mất trong cửa sổ failover.
3. Xác nhận endpoint ứng dụng kết nối là endpoint chính thức sau failover.
4. Kiểm tra namespace, TTL và session lookup.
5. Nếu restore snapshot cũ, đánh giá nguy cơ hồi sinh session đã bị thu hồi.
6. Khi không thể bảo đảm trạng thái thu hồi, đổi namespace/purge session đã restore hoặc yêu cầu xác thực lại.
7. Chỉ mở traffic khi kiểm thử read/write/logout đã đạt.

## 11. Quy trình phục hồi JDBC

### Trường hợp A: Database không kết nối được

1. Kiểm tra endpoint, DNS, route, TLS và credential.
2. Xác nhận database có nhận connection và còn capacity.
3. Kiểm tra connection pool có đang giữ connection lỗi hoặc cạn không.
4. Xác nhận application instances dùng cùng database/schema.
5. Kiểm tra bằng một truy vấn health nhẹ và thao tác session giả trong môi trường test.
6. Mở traffic từng phần và theo dõi connection acquisition, query latency và rollback.

Không tăng pool size một cách mù quáng khi database đã quá tải.

### Trường hợp B: Lock, deadlock hoặc storage saturation

1. Thu deadlock/lock wait reports và query latency.
2. Xác định transaction nào giữ lock lâu.
3. Kiểm tra cleanup job có đang quét quá nhiều bản ghi không.
4. Giảm concurrency hoặc tạm điều chỉnh lịch cleanup theo runbook.
5. Xử lý index/query plan hoặc tăng capacity sau khi xác định nguyên nhân.
6. Xác nhận session read/write/delete hoạt động và transaction commit.

Không xóa hàng session hoặc attributes thủ công để giải phóng database nếu chưa có quy trình được kiểm chứng. Có thể làm mất quan hệ metadata/attributes hoặc để lại dữ liệu mồ côi.

### Trường hợp C: Schema mismatch sau deploy

1. Xác định phiên bản ứng dụng và schema migration hiện tại.
2. So sánh với migration history được quản lý.
3. Xác nhận tất cả node đang chạy phiên bản tương thích.
4. Áp dụng migration theo thứ tự đã kiểm thử.
5. Không chạy lại migration không idempotent hoặc sửa schema bằng tay khi chưa có kế hoạch.
6. Kiểm tra create/find/save/delete và cleanup sau migration.

## 12. Phân biệt khôi phục dịch vụ và khôi phục session

Backend có thể khỏe trở lại nhưng dữ liệu session đã mất hoặc không nhất quán. Hai mục tiêu phải được kiểm tra riêng:

- **Khôi phục dịch vụ:** ứng dụng kết nối Redis/JDBC, request không còn timeout, create/read/update/delete hoạt động.
- **Khôi phục trạng thái session:** các session trước sự cố có còn record hợp lệ, principal index đúng, TTL đúng và trạng thái logout/revocation được giữ không?

Nếu dữ liệu session không thể khôi phục đầy đủ, không cố làm cho người dùng tiếp tục phiên bằng cách đoán hoặc dựng lại attributes. Yêu cầu đăng nhập lại là hành vi có thể chấp nhận khi được thực hiện an toàn và truyền thông rõ ràng.

Với session chứa dữ liệu tạm như giỏ hàng, wizard hoặc lựa chọn người dùng, đánh giá xem dữ liệu đó có nguồn nghiệp vụ độc lập hay chỉ tồn tại trong session. Dữ liệu quan trọng cần nằm trong database nghiệp vụ có backup/transaction riêng, không phụ thuộc vào backup session để phục hồi.

## 13. Kiểm tra an toàn sau phục hồi

Trước khi mở traffic hoàn toàn, thực hiện một ma trận kiểm thử:

| Kiểm tra | Thực hiện | Kết quả mong đợi |
| --- | --- | --- |
| Backend health | Ping/health query từ từng instance | Kết nối ổn định |
| Session create | Login account kiểm thử | Session được lưu và cookie/header được phát |
| Session read | Request tiếp theo đến node khác | Principal/attribute được tải đúng |
| Session update | Cập nhật một attribute | Giá trị được đọc lại ở node khác |
| Logout | Invalidate ở node A | Node B không chấp nhận ID cũ |
| Expiration | Chờ quá idle timeout | Session hết hạn theo chính sách |
| Principal index | Tra cứu session test theo principal | Index đúng và không có dữ liệu chéo |
| Error handling | Ngắt kết nối có kiểm soát trong test | Request được bảo vệ fail closed, lỗi được quan sát |
| Multi-node | Luân phiên request qua tất cả node | Không phụ thuộc local session |
| Monitoring | Theo dõi latency, errors, pool và memory | Các chỉ số trở về vùng vận hành |

Không dùng tài khoản người dùng thật hoặc session production để test. Dùng principal và dữ liệu giả, namespace riêng và dọn đúng phạm vi.

## 14. Theo dõi sau khi mở traffic

Trong giai đoạn ổn định sau phục hồi, theo dõi sát:

- Tỷ lệ 5xx, timeout và repository exception.
- Redis used_memory, evicted_keys, OOM, latency và replication lag.
- JDBC active/pending connections, query latency, lock waits và rollback.
- Session lookup miss và login failure.
- Tỷ lệ tạo session mới bất thường.
- Logout và session invalidation failures.
- p95/p99 của endpoint có session.
- Sự khác biệt giữa các instance.

So sánh với baseline trước sự cố. Nếu login rate tăng đột biến, có thể nhiều người dùng phải đăng nhập lại; điều này có thể làm IdP hoặc auth service quá tải. Giới hạn tải và mở rộng capacity theo kế hoạch nếu cần.

## 15. Thu thập timeline và bằng chứng cho RCA

Sau khi hệ thống ổn định, lập timeline:

| Thời điểm | Sự kiện | Nguồn bằng chứng | Tác động |
| --- | --- | --- | --- |
| T0 | Metric đầu tiên vượt ngưỡng | Monitoring alert | Bắt đầu suy giảm |
| T1 | Repository timeout/OOM tăng | Application/backend logs | Request đọc/ghi lỗi |
| T2 | Incident được xác nhận | Incident channel | Kích hoạt response |
| T3 | Containment được áp dụng | Change log | Tải giảm hoặc traffic chuyển |
| T4 | Backend phục hồi | Health/metrics | Read/write khả dụng |
| T5 | Kiểm thử session hoàn tất | Test report | Xác nhận an toàn |
| T6 | Mở traffic hoàn toàn | Deployment/traffic log | Dịch vụ ổn định |

RCA cần nêu:

- Trigger và nguyên nhân gốc.
- Vì sao cảnh báo không phát hiện sớm hơn.
- Session nào bị mất hoặc có nguy cơ mất.
- Có nguy cơ session bị hồi sinh sau restore không.
- Các thay đổi cấu hình/hạ tầng đã thực hiện.
- Cách xác minh kết quả.
- Việc cần làm để tránh lặp lại.

Không đưa credential, cookie, session ID hoặc payload session vào RCA.

## 16. Lỗi ứng phó thường gặp

| Hành động sai | Rủi ro | Cách làm phù hợp |
| --- | --- | --- |
| Flush toàn bộ Redis để giải phóng RAM | Xóa mọi session và key của workload khác | Phân tích memory, tách workload và mở rộng capacity |
| Chuyển eviction policy sang LRU để giảm OOM | Session đang hoạt động có thể bị loại bỏ | Đánh giá noeviction/capacity và tác động write failure |
| Retry vô hạn khi Redis/JDBC down | Tăng tải và làm cạn thread/connection pool | Retry giới hạn, backoff và circuit breaker |
| Fallback local session ở từng node | Split-brain, logout không nhất quán | Fail closed và phục hồi shared repository |
| Restore backup cũ ngay | Mất session mới hoặc hồi sinh session đã revoke | Kiểm tra backup, revocation state và restore plan |
| Restart tất cả app instance cùng lúc | Tăng reconnect storm và mất bằng chứng | Drain/roll từng node và quan sát |
| Ghi cookie/session ID vào ticket | Lộ bearer credential | Redact và dùng correlation ID |
| Xóa hàng JDBC thủ công | Hỏng quan hệ metadata/attributes | Dùng repository API hoặc migration đã kiểm thử |
| Tăng pool không giới hạn | Làm backend quá tải hơn | Đo saturation và đặt pool theo capacity |

## 17. Runbook rút gọn cho on-call

### Trong 5 phút đầu

- Xác nhận incident và phạm vi instance/endpoint.
- Kiểm tra Redis/JDBC health, latency, memory/connection pool.
- Thu application logs và backend metrics đã redact.
- Kiểm tra deploy/config/secret/network changes gần nhất.
- Không flush, restore hoặc đổi eviction policy vội.

### Sau khi xác định nhóm lỗi

- Network/TLS/ACL: sửa đường kết nối hoặc credential theo quy trình.
- Redis OOM: xác định workload, capacity và policy; không retry vô hạn.
- Redis eviction: xác định session loss, ngừng nguồn memory pressure và đánh giá login lại.
- JDBC saturation: giảm concurrency, kiểm tra locks, pool và query.
- Schema/serializer mismatch: đồng bộ version và migration đã kiểm thử.
- Failover/restore: xác minh replication, TTL và revocation state.

### Trước khi kết thúc incident

- Test login, read, update, logout và expiration.
- Kiểm tra tất cả node dùng cùng repository và cấu hình.
- Theo dõi error rate, session miss, latency và pool/memory.
- Ghi timeline, tác động và quyết định phục hồi session.
- Chuyển các hành động phòng ngừa thành công việc có owner và thời hạn.

## 18. Bài tập thực hành trong môi trường thử nghiệm

Thực hiện trong môi trường local/staging có dữ liệu giả, không dùng production:

1. Khởi động hai hoặc ba instance Spring Session cùng kết nối một Redis hoặc JDBC test store.
2. Tạo session và xác nhận request có thể đi qua các node.
3. Ghi baseline: repository latency, Redis memory hoặc JDBC pool, session miss và request error.
4. Tạo sự cố có kiểm soát: dừng Redis test container, chặn kết nối test, làm đầy một Redis riêng hoặc giới hạn connection pool JDBC.
5. Thu log/metrics và ghi lại thời điểm phát sinh lỗi.
6. Xác nhận request được bảo vệ không fail open và không tạo local session thay thế.
7. Khôi phục backend theo đúng loại sự cố.
8. Chạy lại ma trận login/read/update/logout/expiration.
9. Kiểm tra session nào còn hợp lệ và session nào cần đăng nhập lại.
10. Viết timeline và RCA ngắn với nguyên nhân, tác động, bằng chứng và hành động phòng ngừa.

Không dùng lệnh phá hủy như FLUSHDB, xóa bảng hoặc restore snapshot trên kho có dữ liệu ngoài bài tập. Nếu cần mô phỏng mất dữ liệu, tạo instance riêng với volume và namespace chỉ dành cho test.

## 19. Checklist chuẩn bị trước sự cố

- [ ] Có sơ đồ từ load balancer đến mọi instance và shared session store.
- [ ] Có owner/on-call và quyền truy cập chẩn đoán Redis/JDBC.
- [ ] Có dashboard memory, eviction, OOM, connection pool, latency và replication.
- [ ] Có log repository errors với correlation ID và redaction.
- [ ] Có baseline session create/read/update/delete.
- [ ] Có backup/restore runbook và biết RPO/RTO.
- [ ] Có quy trình xử lý session bị mất hoặc bị thu hồi.
- [ ] Có quy tắc fail closed và không fallback local session.
- [ ] Có test môi trường cô lập cho Redis/JDBC outage, failover và capacity.
- [ ] Có checklist xác minh sau phục hồi trên tất cả instance.

## 20. Checklist đóng sự cố

- [ ] Nguyên nhân đã được xác định hoặc có giả thuyết còn mở được ghi rõ.
- [ ] Bằng chứng trước/sau phục hồi đã được lưu an toàn.
- [ ] Redis/JDBC health, capacity và latency trở lại ngưỡng.
- [ ] Mọi instance dùng cùng repository, namespace/schema, serializer và timeout.
- [ ] Login mới tạo được session bền vững.
- [ ] Session hiện có được đọc và cập nhật giữa các node.
- [ ] Logout và expiration hoạt động đúng.
- [ ] Không có fallback cục bộ hoặc fail-open.
- [ ] Đã đánh giá session bị mất, session bị revoke và rủi ro restore cũ.
- [ ] Người dùng bị ảnh hưởng được thông báo nếu phải đăng nhập lại.
- [ ] RCA và hành động phòng ngừa có owner/thời hạn.

Sự cố kho session cần được xử lý như sự cố của thành phần xác thực và trạng thái người dùng. Thu thập bằng chứng trước khi thay đổi, phân biệt lỗi backend với session miss, giữ fail-closed, khôi phục Redis/JDBC theo đúng nguyên nhân và xác minh login/read/update/logout trên nhiều node. Nếu session record đã mất hoặc trạng thái thu hồi không còn đáng tin cậy, yêu cầu xác thực lại an toàn thường tốt hơn việc dựng lại một phiên không có đủ bằng chứng.
