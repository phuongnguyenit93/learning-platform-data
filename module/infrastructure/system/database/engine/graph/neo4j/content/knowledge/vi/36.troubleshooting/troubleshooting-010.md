# Thu thập bằng chứng, khoanh vùng nguyên nhân và xác minh sau khắc phục trong Neo4j

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Xử lý sự cố Neo4j theo quy trình **phát hiện → bảo toàn bằng chứng → đặt giả thuyết → kiểm chứng → giảm thiểu → sửa nguyên nhân → xác minh → rút kinh nghiệm**.
- Phân biệt sự cố **ứng dụng Java/Spring**, **mạng/Bolt/TLS**, **Neo4j DBMS**, **database/index/Cypher**, **cluster/routing**, **hệ điều hành/storage** và **nguồn dữ liệu ngoài**.
- Thu thập timeline, log, metrics, transaction đang chạy, trạng thái database, query plan và những thay đổi cấu hình với **phạm vi/độ nhạy được kiểm soát**.
- Đọc `SHOW TRANSACTIONS`, `SHOW DATABASES`, `SHOW INDEXES`, `EXPLAIN` và `PROFILE` để tạo bằng chứng thay vì suy đoán nguyên nhân từ một thông báo lỗi.
- Xây dựng và bác bỏ giả thuyết bằng cách đối chiếu **triệu chứng, dấu hiệu phân biệt, phép kiểm tra ít rủi ro và điều kiện kết luận**.
- Chọn biện pháp giảm tác động mà không làm mất transaction log, phá cluster quorum hoặc xóa nhầm graph.
- Xác minh sau sửa chữa ở **bốn lớp: tính sẵn sàng, tính đúng dữ liệu, hiệu năng và độ bền ổn định**, đồng thời tạo báo cáo sự cố có thể tái kiểm tra.

Bài thuộc chương **Xử lý sự cố** của module **DATABASE_ENGINE_GRAPH_NEO4J**. Neo4j tổ chức dữ liệu theo **property graph** (node, relationship, property) và xử lý truy vấn quan hệ/đường đi qua **Cypher**. Ứng dụng dùng Neo4j Java Driver hoặc Spring Data Neo4j có thể gặp lỗi tại nhiều lớp dù thông báo cuối cùng chỉ là “query timeout”, “database unavailable” hay “không tìm thấy đơn hàng”. Phương pháp điều tra đúng là dựa trên **bằng chứng có thời điểm và phạm vi**, không phải thay đổi cấu hình hàng loạt rồi hy vọng hết lỗi.

> **Phạm vi phiên bản:** Ví dụ áp dụng cho Neo4j 5.x và các dòng hiện đại 2025.x–2026.x khi lệnh tương ứng được hỗ trợ. Khả năng log, metrics, RBAC, cluster và truy cập file khác nhau theo **Community/Enterprise/Aura**. Đối chiếu `--help` và tài liệu đúng version/edition, đặc biệt trước khi bật logging chi tiết, tạo support report hoặc chạy lệnh quản trị.

## 1. Mô hình xử lý sự cố dựa trên bằng chứng

Một lần debug có trách nhiệm phải trả lời tuần tự:

1. **Điều gì bị ảnh hưởng?** Đọc hay ghi, database nào, endpoint nào, bao nhiêu người dùng, lỗi toàn phần hay chậm một nhóm truy vấn?
2. **Từ lúc nào?** Mốc bắt đầu, thay đổi vừa xảy ra, một lần tăng tải, backup/import/index population hay failover?
3. **Bằng chứng nào có thể kiểm chứng?** Log, metric, query ID/transaction ID, trace, status/index, plan, so sánh dữ liệu?
4. **Có những giả thuyết nào?** Đặt từ dễ kiểm tra/ít rủi ro tới phức tạp.
5. **Thử nghiệm nào phân biệt được?** Ví dụ chỉ một pod lỗi thì không nên bắt đầu bằng restart toàn cluster.
6. **Giảm tác động ra sao?** Cô lập query nặng, tạm giảm import, sửa routing/TLS, rollback release khi có bằng chứng.
7. **Sau khắc phục có thật sự hết lỗi?** API đúng dữ liệu, ghi commit được, p95/p99 đạt SLO, trạng thái ổn định qua đủ thời gian.

~~~mermaid
flowchart TD
    A["Tín hiệu lỗi: API, alert, người dùng"] --> B["Triage: phạm vi, mức độ, timeline"]
    B --> C["Bảo toàn log, metrics, IDs, thay đổi"]
    C --> D["Giả thuyết có thể kiểm chứng"]
    D --> E["Phép thử ít rủi ro"]
    E --> F{"Bằng chứng hỗ trợ?"}
    F -->|Không| D
    F -->|Có| G["Giảm tác động / sửa nguyên nhân"]
    G --> H["Xác minh chức năng, dữ liệu, SLO"]
    H --> I{"Đạt tiêu chí đóng?"}
    I -->|Không| C
    I -->|Có| J["Postmortem + hành động phòng ngừa"]
~~~

**Phân biệt quan trọng:**

- **Triệu chứng:** `executeWrite` timeout.
- **Giả thuyết:** Writer cluster không sẵn sàng hoặc transaction đợi khóa.
- **Bằng chứng:** `SHOW DATABASES` cho thấy writer có/quorum đủ; `SHOW TRANSACTIONS` cho thấy `waitTime` cao ở những transaction cùng ghi một node.
- **Nguyên nhân xác nhận:** Hai job cập nhật một `Account` nóng và giữ transaction quá lâu.
- **Khắc phục:** Đổi cách batch và thứ tự khóa/giới hạn độ dài transaction.
- **Xác minh:** Write commit trở lại, wait time giảm, không ghi lặp và trạng thái Account vẫn đúng.

Không gọi một tương quan (“sau deploy thì CPU tăng”) là **nguyên nhân đã chứng minh** nếu chưa có phép kiểm tra loại trừ những giả thuyết khác.

## 2. Triage trong những phút đầu: tác động, ưu tiên và người chịu trách nhiệm

Trước khi sửa:

| Câu hỏi | Ví dụ dữ liệu nên ghi |
| --- | --- |
| **Phạm vi người dùng** | 15% request `GET /customers/{id}/orders` timeout; `POST /orders` vẫn hoạt động |
| **Loại operation** | READ, WRITE, admin, backup, import, GDS job |
| **Database/cluster** | `orders_graph`, Neo4j Enterprise cluster vùng A; hoặc Aura instance ID nội bộ |
| **Mức độ** | SEV1 nếu mất khả năng ghi giao dịch quan trọng; SEV2 nếu một tính năng đọc bị suy giảm đáng kể |
| **Mốc thời gian** | Bắt đầu lúc 09:12 UTC, release lúc 09:05 UTC, index population 09:10 UTC |
| **Tình trạng dữ liệu** | Có nguy cơ ghi nửa chừng? Giao dịch đã commit nhưng HTTP timeout? |
| **Biện pháp tạm thời** | Tạm dừng batch import, chuyển truy vấn đọc sang endpoint nguồn tin cậy, rollback ứng dụng khi có cơ sở |

Đây là **mức độ minh họa**, không phải khung SEV bắt buộc của Neo4j. Tổ chức cần tiêu chí escalation riêng: mất tính đúng dữ liệu hoặc giao dịch tài chính thường ưu tiên hơn một dashboard thống kê bị trễ.

### 2.1. Phân công trong incident

- **Incident commander:** quyết định ưu tiên và điều phối biện pháp giảm thiểu.
- **DBA/Neo4j operator:** kiểm tra database, cluster, logs, metrics, locks, store/index.
- **Application owner:** kiểm tra Java Driver, SDN, API error/trace, câu Cypher thực tế và bản deploy.
- **SRE/platform:** kiểm tra CPU/RAM/disk, container, DNS, TLS, network và storage.
- **Data/domain owner:** xác nhận invariant nghiệp vụ, đối soát và kế hoạch sửa dữ liệu.

Ở nhóm nhỏ một người có thể đảm nhiệm nhiều vai trò, nhưng vẫn cần tách **người ra quyết định khắc phục** và **người xác nhận dữ liệu đúng** nếu sự cố nghiêm trọng.

### 2.2. Khi nào phải ưu tiên bảo toàn bằng chứng?

Trước khi restart/roll back, nên lấy các snapshot **nhẹ và an toàn** nếu không làm sự cố trầm trọng:

- Biểu đồ metrics trong khoảng **trước–trong–sau** lỗi.
- Log có timestamp chính xác và thông báo lỗi nguyên bản.
- Danh sách transaction đang chạy và blocked, khi còn quan sát được.
- Trạng thái database, index, topology, config/release đang dùng.
- Request ID/trace ID, database name, query hash hoặc query ID.

Những thứ như **running transaction**, routing state và lock wait có thể biến mất sau restart. Tuy nhiên, không trì hoãn vô hạn biện pháp cứu dịch vụ chỉ để thu đủ mọi loại bằng chứng; cân đối theo mức độ tác động.

## 3. Timeline: chuẩn hóa thời gian trước khi đối chiếu

Một sự cố Neo4j thường có nhiều đồng hồ:

~~~text
09:04:32.100Z  Application deploy hoàn tất
09:07:12.550Z  Query p95 tăng từ 80ms lên 900ms
09:07:14.015Z  Neo4j query.log: queryId ..., elapsed=910ms
09:07:15.640Z  SHOW TRANSACTIONS: 18 transaction blocked
09:08:01.420Z  Import job #42 bắt đầu batch ghi lớn
09:12:00.000Z  Operator tạm dừng import
09:14:20.000Z  p95 xuống 100ms, tỷ lệ timeout về nền
~~~

Các mốc là ví dụ giả định. **Không chứng minh import là nguyên nhân chỉ vì xuất hiện gần thời gian tăng p95**: cần so lock wait, số transaction, query ID và thử nghiệm giảm tải có đối chứng.

Hướng dẫn timeline:

1. Ghi thời gian ở **UTC hoặc ISO 8601 có offset**, không trộn giờ local và giờ UTC.
2. Ghi rõ **time zone của log**. Với container, log collector có thể gắn thời gian khác timestamp trong ứng dụng.
3. Kiểm tra **NTP/clock skew** giữa server, ứng dụng và broker; không sử dụng “occurredAt” từ client làm bằng chứng tuyệt đối nếu đồng hồ chưa tin cậy.
4. Ghi **deploy/change events**: version application, query, index, plugin, database setting, DNS/TLS, backup/GDS job.
5. Giữ **timestamp gốc** và lưu một phiên bản chuẩn hóa để so sánh.
6. Nếu sự cố lặp, tạo timeline cho **mỗi lần tái xuất hiện** và tìm điều kiện chung.

Một “incident worksheet” nên gồm:

| Trường | Ví dụ | Bảo mật |
| --- | --- | --- |
| `incidentId` | `INC-2026-114` | Không chứa PII |
| `firstSeenAt` | `2026-11-25T09:07:12Z` | Dùng UTC |
| `environment` | `prod-asia` | Không công khai nếu nhạy cảm |
| `database` | `orders_graph` | Ghi đúng database, không phải alias mơ hồ |
| `operation` | `createOrder` | Không log payload thanh toán |
| `appTraceId` | `trace-...` | Truy vết được giữa các lớp |
| `queryId / transactionId` | Giá trị quan sát tại thời điểm lỗi | ID có vòng đời; không xem là business key |
| `changeId` | Release, index job hoặc network change | Link ticket/phê duyệt |
| `evidenceRefs` | Link log/dashboard snapshot | Giới hạn quyền xem |

## 4. Ma trận nguồn bằng chứng: mỗi tầng cung cấp điều gì?

| Tầng | Nguồn bằng chứng | Phân biệt được | Không chứng minh được |
| --- | --- | --- | --- |
| **HTTP/API** | APM/trace, request metrics, retry, timeout | Endpoint nào bị lỗi và người dùng đợi bao lâu | Nguyên nhân chắc chắn nằm ở Neo4j |
| **Java Driver/SDN** | Error code/classification, connection/pool, database name, session routing | Auth/TLS/timeout/query error phía client | Store/index đã nhất quán |
| **Cypher/database** | `SHOW TRANSACTIONS`, `SHOW INDEXES`, `SHOW DATABASES` | Query đang chạy, khóa, index state, database online | Network giữa mọi node đều tốt |
| **Neo4j logs** | `neo4j.log`, `debug.log`, `query.log`, `security.log` tùy edition | Startup/recovery/errors/slow query/auth events | Tất cả các request lỗi đều được log với đầy đủ payload |
| **Neo4j metrics** | JVM, page cache, Bolt, transactions, disk I/O | Saturation và xu hướng qua thời gian | Truy vấn nào gây lỗi nếu không ghép log/trace |
| **OS/container** | Host/kernel, disk, OOMKill, restart, network | Tài nguyên, container lifecycle, storage/network | Business invariant có còn đúng |
| **Cluster** | Topology/role, writer/quorum, routing, replication lag | Một lỗi có phải chỉ ảnh hưởng READ hoặc WRITE | Dữ liệu đã đồng bộ với hệ thống bên ngoài |
| **Data/integration** | Kiểm tra theo business ID, source of truth, CDC/outbox checkpoint | Missing/stale/duplicate node/relationship | Dữ liệu phục hồi hoàn toàn nếu chưa đối soát đầy đủ |

**Quy tắc vàng:** Thu ít nhất **hai nguồn độc lập** hỗ trợ kết luận quan trọng. Ví dụ “database chậm vì thiếu index” cần `PROFILE`/DB Hits và `SHOW INDEXES`; chỉ một biểu đồ CPU tăng là chưa đủ.

## 5. Neo4j log: đọc đúng file, đúng phiên bản, đúng độ nhạy

Các file log thường gặp trên Neo4j tự quản:

| Log | Chứa thông tin gì? | Cảnh giác |
| --- | --- | --- |
| **`neo4j.log`** | Sự kiện vận hành thông thường, startup/shutdown | Tùy package có thể xem qua `journalctl` |
| **`debug.log`** | Chi tiết hữu ích cho chẩn đoán/Neo4j Support | Có thể rất dài; từ 2025.01 định dạng mặc định là JSON |
| **`query.log`** | Query chậm/đã thực thi, thời gian và thông tin liên quan | Là tính năng Enterprise; có nguy cơ chứa query parameters |
| **`security.log`** | Sự kiện bảo mật/xác thực khi được hỗ trợ | Không phát tán thông tin người dùng/địa chỉ nội bộ |
| **`gc.log`** | Thời gian và hoạt động Garbage Collection nếu bật | Ghép với JVM heap, p99 và OOM |
| **Container/system logs** | OOM, restart, disk/network events | Timestamps có thể lệch với log Neo4j |

Vị trí log do `server.directories.logs` hoặc deployment quản lý. Ở Docker/Kubernetes có thể cần container stdout/log collector; ở Aura sử dụng **các log/dashboard mà dịch vụ thực sự cung cấp**, không giả định truy cập filesystem Neo4j.

### 5.1. Query logging khi cần chẩn đoán

Trong Neo4j Enterprise self-managed, một cấu hình thận trọng cho query chậm là:

~~~properties
# neo4j.conf - ví dụ điều tra; đối chiếu version và chính sách dữ liệu.
db.logs.query.enabled=INFO
db.logs.query.threshold=200ms
db.logs.query.parameter_logging_enabled=false
db.logs.query.obfuscate_literals=true
~~~

Ý nghĩa:

- `INFO`: log sau khi query hoàn tất và vượt threshold.
- `threshold`: giúp tìm query bất thường; con số 200 ms chỉ là ví dụ.
- Tắt ghi **parameter values** nếu không cần chúng để điều tra.
- Obfuscate literals giúp hạn chế lộ dữ liệu trong query text, nhưng không bảo đảm mọi biến thể thông tin nhạy cảm được che hoàn toàn.

**Tùy bản Neo4j**, một số setting động có thể cập nhật runtime và một số thay đổi cần restart/rollout. Không sửa cấu hình production thiếu phê duyệt. Theo tài liệu hiện hành, mặc định query logging ở các bản mới có thể là `VERBOSE`; đừng giả định mọi server luôn có log giống nhau.

### 5.2. Cái giá của log chi tiết

Không bật vô hạn:

~~~properties
# KHÔNG mặc định dùng cho production chỉ vì muốn debug.
db.logs.query.enabled=VERBOSE
db.logs.query.plan_description_enabled=true
db.logs.query.parameter_logging_enabled=true
~~~

Plan logging có overhead và nhiều tham số có thể chứa **PII, token, query payload**. Chỉ bật khi có mục đích, khoảng thời gian, chủ sở hữu log, giới hạn dung lượng và phương án tắt. Trước khi chia sẻ support package, phải rà soát redaction và quyền truy cập.

### 5.3. Phân tích một mục query log

Giả sử thấy:

~~~text
2026-11-25T09:07:14Z  queryId=Q-17  database=orders_graph
elapsed=910ms planning=8ms waiting=650ms pageHits=900
query="MATCH ... MERGE ..."
~~~

**Đây là dòng log giả lập**, không phải format bắt buộc. Nếu `waiting=650ms` và `planning=8ms`, nên tìm **lock/transaction contention** trước khi kết luận thiếu index. Nếu `pageFaults` và I/O tăng, cân nhắc working set/page cache/disk. Nếu `planning` tăng mạnh sau upgrade, kiểm tra cache/replanning/index state.

Một số query ID có thể reset sau restart; không dùng ID log để nhận diện một query vĩnh viễn giữa nhiều lần chạy. Kết hợp **timestamp, database, server, query text/hash, app trace ID**.

Nguồn: [Neo4j Operations Manual — Logging](https://neo4j.com/docs/operations-manual/current/monitoring/logging/).

## 6. Tình trạng database, edition và schema: thu bằng chứng read-only

### 6.1. Xác định DBMS và database đích

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

~~~cypher
SHOW DATABASES
YIELD name, requestedStatus, currentStatus, statusMessage
RETURN name, requestedStatus, currentStatus, statusMessage
ORDER BY name;
~~~

Lệnh cần quyền phù hợp và cột hỗ trợ theo phiên bản. **`requestedStatus`** là trạng thái mong muốn; **`currentStatus`** là trạng thái quan sát được. Nếu database đích offline, đừng vội debug query `MATCH` như một vấn đề index.

Ở cluster Enterprise, nếu phiên bản hỗ trợ:

~~~cypher
SHOW SERVERS;
~~~

~~~cypher
SHOW DATABASES
YIELD name, address, role, writer, currentStatus
RETURN name, address, role, writer, currentStatus
ORDER BY name, address;
~~~

Một database có thể vẫn **READ được** nhưng không có **WRITE route/quorum** thích hợp. Trạng thái một endpoint đơn lẻ không đại diện cho toàn bộ các allocation; cần kiểm tra các thành viên theo runbook cluster.

### 6.2. Kiểm tra index và constraint

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes,
      properties, state, populationPercent
RETURN name, type, entityType, labelsOrTypes,
       properties, state, populationPercent
ORDER BY state, name;
~~~

~~~cypher
SHOW CONSTRAINTS;
~~~

Phân biệt:

- **Index không tồn tại:** query không có access path như mong đợi.
- **Index `POPULATING`:** schema đã định nghĩa nhưng chưa sẵn sàng cho workload.
- **Index `FAILED`:** xem lý do failure và nguồn lực; không xóa/tạo lại mù quáng.
- **Constraint violation:** dữ liệu hoặc concurrency không đáp ứng invariant; không “chữa” bằng cách tắt constraint trước khi đánh giá nghiệp vụ.

Một query chậm **không đồng nghĩa index thiếu**; planner có thể scan hợp lý trên tập dữ liệu nhỏ hoặc dùng plan khác tốt hơn. Phải dùng `EXPLAIN`/`PROFILE` để xác minh.

## 7. Transaction, khóa và các truy vấn đang chạy

Neo4j hỗ trợ `SHOW TRANSACTIONS` để xem transaction hiện tại theo quyền:

~~~cypher
SHOW TRANSACTIONS
YIELD transactionId, database, username, status,
      elapsedTime, waitTime, currentQuery
RETURN transactionId, database, username, status,
       elapsedTime, waitTime, currentQuery
ORDER BY elapsedTime DESC
LIMIT 25;
~~~

Để tránh in query/PII trong bản báo cáo rộng, chỉ xem metadata khi đủ thông tin:

~~~cypher
SHOW TRANSACTIONS
YIELD transactionId, database, status,
      elapsedTime, waitTime, activeLockCount
RETURN transactionId, database, status,
       elapsedTime, waitTime, activeLockCount
ORDER BY elapsedTime DESC
LIMIT 25;
~~~

Một số cột là **cột mở rộng** và quyền xem transaction của user khác phụ thuộc RBAC. Theo tài liệu, `SHOW TRANSACTIONS` quan sát transaction **trên instance đang kết nối**; trong cluster cần xem phạm vi thích hợp, không lấy một kết quả trống để kết luận mọi server không có transaction chậm.

### 7.1. Đọc các con số đúng cách

| Dấu hiệu | Có thể gợi ý | Cần xác minh tiếp |
| --- | --- | --- |
| `elapsedTime` cao, `waitTime` cao | Tranh chấp khóa, transaction blocked | `status`, `resourceInformation`, transaction liên quan |
| `elapsedTime` cao nhưng `waitTime` thấp | Query đang tính toán hoặc đợi I/O/network | CPU, DB Hits, page faults, client consumption |
| `activeLockCount` nhiều | Transaction giữ nhiều khóa | Có thực sự blocked hay workload ghi lớn hợp lệ? |
| Query đã xong nhưng transaction vẫn mở | App không commit/consume kịp, chờ việc ngoài DB | Code callback, session lifecycle, transaction log |
| Một `Order`/`Account` nóng được ghi liên tục | Hotspot theo business key | Batch size, thứ tự update, lock contention |

**Cẩn trọng với duration:** `elapsedTime` đo tuổi transaction; không mặc định bằng thời gian Cypher đang chạy. Một transaction có thể mở rồi nằm idle trong khi ứng dụng xử lý HTTP bên ngoài — một thiết kế cần xem lại.

### 7.2. Terminate transaction là biện pháp giảm thiểu có rủi ro

Sau khi ghi lại bằng chứng, xác định transaction đích và được phê duyệt, Neo4j có:

~~~cypher
// MINH HỌA CHO MÔI TRƯỜNG LAB / QUY TRÌNH SỰ CỐ ĐƯỢC DUYỆT.
// Thay ID bằng transactionId thực đã xác minh.
TERMINATE TRANSACTIONS 'neo4j-transaction-123';
~~~

Không chọn bừa “transaction lâu nhất”. Terminate có thể rollback công việc đang chạy, khiến application retry và tăng tải; ở ranh giới commit lỗi mạng, **client có thể không biết transaction đã commit hay chưa**. Phải có **business ID/idempotency** và quy trình xác minh dữ liệu trước khi gửi lại yêu cầu.

Không tự động terminate mọi transaction có `elapsedTime > 30s` mà không hiểu batch/import/GDS/traversal hợp lệ. Nhận diện **request owner** và hiệu ứng rollback trước khi can thiệp.

Nguồn: [Neo4j — Show and terminate transactions](https://neo4j.com/docs/operations-manual/current/database-internals/show-and-terminate-transactions/).

## 8. Hiệu năng Cypher: EXPLAIN/PROFILE để phân biệt nguyên nhân

Giả sử ứng dụng báo endpoint danh sách đơn tăng từ 60 ms lên 1.200 ms:

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId, o.status AS status
ORDER BY o.orderId
LIMIT 20;
~~~

Trước hết **xem plan mà không chạy dữ liệu**:

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId, o.status AS status
ORDER BY o.orderId
LIMIT 20;
~~~

Nếu an toàn, đo thực thi trên snapshot/lab hoặc production với kiểm soát:

~~~cypher
PROFILE
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId, o.status AS status
ORDER BY o.orderId
LIMIT 20;
~~~

**`PROFILE` thực thi query thật.** Với truy vấn `CREATE`, `SET`, `DELETE` hoặc procedure có side effect, chạy PROFILE có thể **ghi dữ liệu**; không dùng trên production chỉ để “xem plan”.

### 8.1. Bằng chứng trong query plan

| Toán tử/chỉ số | Điều cần kiểm tra |
| --- | --- |
| `NodeUniqueIndexSeek` / `NodeIndexSeek` | Có bắt đầu từ index trên `Customer.customerId` không? |
| `NodeByLabelScan` / `AllNodesScan` | Vì sao planner quét nhiều node? |
| `Expand(All)` | Một customer sinh 100 hay 100.000 hàng qua `PLACED`? |
| `Filter` | Lọc quá muộn sau khi duyệt quan hệ? |
| `Sort` / `Top` | Bao nhiêu hàng phải sắp xếp trước `LIMIT 20`? |
| `Rows` | Số hàng thực tế ở từng bước; có nổ fan-out? |
| `DB Hits` | Chi phí truy cập dữ liệu tăng bao nhiêu so baseline? |
| Page hits/faults | Cache hoặc I/O có đang bị áp lực? |
| Plan/runtime | Có thay đổi do index, statistics, version Cypher hoặc runtime? |

**`LIMIT 20` không bảo đảm chỉ đọc 20 relationship**. Nếu một customer có 80.000 order, Neo4j có thể phải duyệt/sort rất nhiều hàng để xác định top-20. Thay Java DTO không tự giảm việc này nếu Cypher vẫn kéo toàn graph.

### 8.2. Đối chiếu trước/sau

Đối với cùng query ID:

- Giữ **dataset, index, parameter và mức concurrency** tương đương.
- So sánh khách hàng bậc thấp và khách hàng bậc cao; trung bình có thể che hotspot.
- Phân biệt **cold cache** sau restart với **warm cache** trong vận hành bình thường.
- Ghép DB Hits/Rows với **Java Driver pool wait**, HTTP latency và mạng.
- Nếu vừa nâng phiên bản Neo4j/Cypher, so **cùng cú pháp và phiên bản ngôn ngữ** trước khi thay nhiều biến đồng thời.

Không buộc query plan phải có **cùng chuỗi tên operator** sau nâng cấp. Mục tiêu là kết quả nghiệp vụ đúng và chi phí nằm trong SLO.

Nguồn: [Neo4j — Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/).

## 9. Metrics hệ thống: chứng minh nghẽn CPU, bộ nhớ, disk hay mạng

Một incident Neo4j thường cần ghép ít nhất **ba nguồn**: metrics Neo4j, metrics host/container và metrics phía ứng dụng.

| Nhóm | Chỉ số nên quan sát | Triệu chứng gợi ý |
| --- | --- | --- |
| **CPU** | CPU process, host, load, throttling container | Query scan/expand lớn, bão hòa hoặc container bị throttled |
| **JVM heap** | Used/max, allocation, GC pause/time | Query tạo object nhiều, transaction lớn, OOM pressure |
| **Page cache** | Hit/miss, faults, configured size | Working set vượt cache; I/O chậm |
| **Disk** | Free bytes, IOPS, read/write latency, filesystem errors | Store/log không ghi được, checkpoint chậm, backup/import tranh tài nguyên |
| **Bolt/network** | Connection failures, handshake/TLS, RTT, packet drops | Driver timeout, routing địa chỉ unreachable |
| **Transactions** | Active, commit/rollback, retry, lock wait | Hotspot ghi hoặc transaction lâu |
| **Application** | HTTP p50/p95/p99, error rate, pool pending, retries | Người dùng chờ nhiều hơn thời gian query server |
| **Cluster** | Writer/quorum, member availability, replication lag | WRITE unavailable hoặc READ trễ |

### 9.1. CPU cao chưa chắc là lỗi

CPU tăng cùng throughput tăng và p99 giữ ổn có thể là hệ thống **đang làm nhiều công việc hợp lệ**. CPU cao nhưng throughput giảm và DB Hits tăng mạnh có thể là query regression. CPU thấp nhưng pool pending cao có thể là nghẽn **phía client** hoặc network.

### 9.2. JVM heap chưa đầy không chứng minh RAM đủ

Tổng RAM Neo4j còn gồm **page cache, native/off-heap memory, OS và các process khác**. Container bị OOMKilled có thể do memory limit dù Java heap chưa đạt max. Nếu có GDS/plugin, các graph projection hoặc cấu trúc thuật toán trong bộ nhớ cần được tính riêng theo khả năng triển khai.

### 9.3. Disk đầy là tình huống nguy hiểm

Nếu filesystem store/transaction log gần đầy:

1. Xác định **mount/partition nào** đầy và tốc độ tăng.
2. Kiểm tra backup/import, retention, transaction logs, store growth.
3. Giảm workload không thiết yếu, mở rộng dung lượng theo runbook.
4. **Không xóa thủ công transaction log hoặc store files khi server đang chạy** chỉ để giải phóng dung lượng.
5. Sau khôi phục, kiểm tra consistency/backup readiness và WRITE commit.

### 9.4. Prometheus, NOM, Aura

Neo4j Enterprise self-managed có các cơ chế metrics như Prometheus/JMX/CSV hoặc Neo4j Ops Manager theo bản hỗ trợ. Trên **Aura**, dùng dashboard/metrics do gói managed service cung cấp và giám sát phía ứng dụng; không mặc định có quyền vào server log filesystem hay tự bật exporter.

Giữ label metrics có cardinality nhỏ (`database`, `instance`, `operation`), không đưa `customerId`, `orderId` hoặc query parameters nhạy cảm vào nhãn dashboard.

Nguồn: [Neo4j Operations Manual — Metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/).

## 10. Java Driver và Spring Data Neo4j: lỗi có thể ở trước database

Một exception từ Java Driver là **dấu vết của tầng client**, không tự chứng minh Neo4j Server đã crash.

| Loại lỗi/triệu chứng | Giả thuyết ban đầu | Bằng chứng phân biệt |
| --- | --- | --- |
| `ServiceUnavailableException` hoặc không mở được kết nối | Network, DNS, TLS, Bolt, server unavailable | TCP/TLS test, URI, driver logs, server health |
| `SessionExpiredException` | Server/route hiện tại không đáp ứng tiêu chí session (ví dụ writer thay đổi) | Cluster writer/routing, failover timeline, retry |
| `AuthenticationException` / authorization error | Credential sai, role thiếu quyền, secret rotation | Security log, user/role, lỗi code cụ thể |
| `ClientException` do Cypher/constraint | Query sai hoặc dữ liệu vi phạm invariant | Neo4j error code/GQLSTATUS, query/params đã redacted |
| `TransientException` | Lỗi tạm thời, lock/timeout/unavailability | Transaction state, retry policy, resource metrics |
| “HTTP timeout nhưng query server nhanh” | App pool, serialization, network, external service | APM span, connection acquisition, CPU app, response bytes |
| “Kết quả thiếu relationship” | SDN projection/mapping, query giới hạn, cache stale | Raw Cypher result, DTO mapping, entity load scope |

Neo4j error code có nhóm như **`Neo.ClientError`**, **`Neo.TransientError`** và **`Neo.DatabaseError`**, cùng các mã trạng thái GQL trong phiên bản mới. Đọc **mã và loại exception thực tế**; không retry vô hạn mọi lỗi. Lỗi constraint hoặc Cypher syntax không được “chữa” bằng retry như một lỗi routing nhất thời.

### 10.1. Connectivity probe có giới hạn

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class Neo4jDiagnosticProbe {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String user = System.getenv("NEO4J_USERNAME");
        String password = System.getenv("NEO4J_PASSWORD");

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(user, password))) {
            driver.verifyConnectivity(); // Bolt/TLS/auth/routing

            try (Session session = driver.session(
                    SessionConfig.forDatabase("orders_graph"))) {
                long result = session.executeRead(tx ->
                        tx.run("RETURN 1 AS ok")
                          .single()
                          .get("ok")
                          .asLong());
                System.out.println("Read probe: " + result);
            }
        }
    }
}
~~~

Đây là **diagnostic CLI example**, không phải readiness endpoint hoàn chỉnh. Cấu hình biến môi trường và database thật trước khi chạy. `verifyConnectivity()` có thể thành công trong khi một database cụ thể offline hoặc WRITE không khả dụng. `RETURN 1` cũng không chứng minh một traversal nặng sẽ đáp ứng SLO.

### 10.2. Thêm metadata theo request một cách an toàn

Với Java Driver bản hỗ trợ `TransactionConfig`:

~~~java
import java.time.Duration;
import java.util.Map;
import org.neo4j.driver.TransactionConfig;

var cfg = TransactionConfig.builder()
        .withTimeout(Duration.ofSeconds(5))
        .withMetadata(Map.of(
                "operation", "lookupCustomerOrders",
                "traceRef", "trace-opaque-123"))
        .build();

var result = session.executeRead(tx ->
        tx.run("""
            MATCH (c:Customer {customerId: $id})
            RETURN c.customerId AS id
            """, Map.of("id", customerId))
          .single()
          .get("id")
          .asString(), cfg);
~~~

Đoạn này giả định `session` và `customerId` đã được khai báo, dùng metadata **không chứa PII**. Metadata giúp ghép transaction/query log với trace ứng dụng, nhưng tùy bản, logging của những trường này khác nhau; không coi nó thay thế tracing chuẩn.

### 10.3. Những sai lầm ở tầng ứng dụng

- Tạo **Driver mới cho mọi request**, làm mất lợi ích connection pool và tăng handshake.
- Dùng chung **Session giữa các thread** dù Session không được thiết kế để sử dụng đồng thời giữa nhiều luồng.
- Kết nối `bolt://` trực tiếp tới một thành viên không nhận WRITE trong cluster, thay vì dùng routing URI phù hợp.
- Không chỉ định database, dẫn tới truy vấn chạy nhầm database mặc định.
- Callback `executeWrite` gửi email/thanh toán khi driver **có thể retry toàn callback**, tạo side effect trùng.
- Chỉ tính thời gian `tx.run`, không tính **đọc hết Result/commit/retry** vào latency end-to-end.
- Dùng entity graph SDN cho API chỉ cần hai thuộc tính, tạo over-fetching/fan-out.

**Tính đúng sau lỗi:** nếu connection mất gần lúc commit, client có thể không biết WRITE đã commit hay chưa. Kiểm tra theo **business ID và idempotency key** ở database/source of truth trước khi gọi lại để tránh tạo lặp.

Nguồn: [Neo4j Java Driver Manual — Connect](https://neo4j.com/docs/java-manual/current/connect/), [Transactions](https://neo4j.com/docs/java-manual/current/transactions/), [Server error classifications](https://neo4j.com/docs/status-codes/current/errors/).

## 11. Cluster, routing và replication: lỗi READ và WRITE có thể khác nhau

Trong Neo4j Enterprise cluster hiện đại, mỗi standard database có **primary allocations**, một **writer/leader** và có thể có **secondary** phục vụ READ; secondary cập nhật bất đồng bộ.

Ví dụ:

~~~mermaid
flowchart LR
    API["Java Driver routing"] --> R["Routing table"]
    R -->|WRITE| P1["Primary writer"]
    P1 <-->|Consensus| P2["Primary follower"]
    P1 <-->|Consensus| P3["Primary follower"]
    R -->|READ| S["Secondary reader"]
    P1 -.->|Async replication| S
~~~

### 11.1. Mô hình lỗi

| Triệu chứng | Giả thuyết | Bằng chứng |
| --- | --- | --- |
| WRITE fail, READ còn chạy | Không còn write route/quorum hoặc role sai | `SHOW DATABASES` writer/status, topology, driver exception |
| Một số READ thiếu dữ liệu mới | Secondary lag hoặc causal bookmark chưa được truyền | Replication lag, session/bookmark, source commit |
| Chỉ một app pod timeout | DNS/route/CA/connection pool của pod đó | So env/pod metrics, traceroute/TLS logs theo chính sách |
| Lỗi sau failover | Routing table cũ, SessionExpired, retry | Timeline election, driver logs, URI `neo4j://` |
| Thêm server không tăng throughput | Server chưa enabled/allocated hoặc client không route sang | `SHOW SERVERS`, `SHOW DATABASES`, client routing/traffic |

**Quorum** thuộc về nhóm primary của **database cụ thể**, không phải số lượng process Neo4j có thể ping. Ba primary chịu mất một primary nếu còn quorum 2/3 liên lạc; không restart đồng loạt primary để “sửa” lỗi transient.

### 11.2. Bookmark chỉ giải quyết nhân quả trong Neo4j

Neo4j Driver cung cấp **bookmark/causal consistency** để một READ phụ thuộc có thể chờ transaction trước đó được quan sát. Bookmark **không** làm một thay đổi vừa commit trong PostgreSQL xuất hiện ngay trên graph Neo4j nếu CDC/outbox chưa đồng bộ.

Khi source of truth là RDBMS và Neo4j là read model:

- Đo **source commit → consumer apply → read visible**.
- Kiểm tra eventId/version, backlog, DLQ và checkpoint.
- Với dữ liệu bị thiếu/stale, **reconcile** theo business key, không chỉ restart Neo4j.

## 12. Sai dữ liệu: bảo vệ bất biến, kiểm tra trước khi sửa

Một sự cố có thể không có lỗi kỹ thuật: query trả HTTP 200 nhưng **sai đồ thị**. Ví dụ `Order` tồn tại nhưng relationship `PLACED` thiếu; hoặc có hai node cùng một ID logic.

### 12.1. Bằng chứng phải thu

~~~cypher
// Kiểm tra số Order có cùng business ID.
MATCH (o:Order {orderId: $orderId})
RETURN count(o) AS matches;
~~~

~~~cypher
// Kiểm tra chủ sở hữu theo cạnh PLACED.
MATCH (o:Order {orderId: $orderId})
OPTIONAL MATCH (c:Customer)-[:PLACED]->(o)
RETURN o.orderId AS orderId,
       o.status AS status,
       collect(DISTINCT c.customerId) AS ownerIds;
~~~

~~~cypher
// Kiểm tra constraint thật, không chỉ suy từ Java annotations.
SHOW CONSTRAINTS;
~~~

Với graph lớn, chọn **tập ID đại diện/batch** thay vì scan toàn bộ vào giờ cao điểm. Nếu có nhiều node `Order` trùng ID mà không có constraint, không tự xóa “bản dư” trước khi biết relationship và nguồn dữ liệu có thẩm quyền.

### 12.2. Nguyên tắc sửa dữ liệu an toàn

1. **Đóng băng thao tác ghi liên quan** nếu dữ liệu tiếp tục lệch và cần bảo vệ invariant.
2. Lấy bản backup/snapshot hoặc một export có kiểm soát của **phạm vi ảnh hưởng** trước khi repair.
3. Xác định **system of record** và bản nào đúng theo business ID/version.
4. Viết script **dry-run**: thống kê số node/edge sẽ thay đổi, điều kiện WHERE và ví dụ kết quả.
5. Thực hiện theo batch/transaction có kiểm soát và idempotent khi phù hợp.
6. Đối chiếu **trước–sau** bằng cùng query, kiểm tra downstream CDC/cache/search.
7. Giữ lịch sử quyết định sửa và khả năng rollback nếu cần.

**Không dùng `DETACH DELETE` hàng loạt** trên production để xử lý node mồ côi mà chưa đánh giá hậu quả: nó xóa mọi relationship của node đích. Với lỗi domain, sự đúng đắn quan trọng hơn việc làm số đếm “khớp” thật nhanh.

### 12.3. Backup restore không tự giải quyết chênh lệch liên hệ thống

Nếu phục hồi Neo4j về bản backup lúc 10:00 nhưng PostgreSQL đã commit đơn tới 10:30, cần **replay/rebuild/reconciliation** phần phát sinh. Không gọi trạng thái phục hồi là “đã đồng bộ” khi read model còn thiếu 30 phút sự kiện.

## 13. Khoanh vùng nguyên nhân bằng cây quyết định

Thay vì thử ngẫu nhiên, đi từ **bước có chi phí thấp, khả năng phân biệt cao**:

~~~mermaid
flowchart TD
    A["Request Neo4j lỗi/chậm"] --> B{"Driver kết nối và auth OK?"}
    B -->|Không| N["DNS/TLS/Bolt/credential/route"]
    B -->|Có| C{"Database đích ONLINE?"}
    C -->|Không| O["Recovery/disk/cluster/database state"]
    C -->|Có| D{"READ nhỏ OK?"}
    D -->|Không| P["Role/read route/resource/server error"]
    D -->|Có| E{"WRITE cần thiết OK?"}
    E -->|Không| Q["Quorum/writer/constraint/lock/disk"]
    E -->|Có| F{"Query nghiệp vụ chậm?"}
    F -->|Có| G["PROFILE + index + rows + client pool"]
    F -->|Không| H["Đối soát dữ liệu, cache, CDC, DTO"]
~~~

Đây là **cây gợi ý**, không phải logic loại trừ tuyệt đối. Một sự cố có thể gồm **hai lỗi đồng thời**: thiếu index làm query chậm, đồng thời một app pod dùng secret hết hạn. Kết quả `RETURN 1` thành công không loại trừ lỗi riêng của một relationship query nặng.

### 13.1. Mỗi giả thuyết phải có “dấu hiệu phản chứng”

| Giả thuyết | Bằng chứng hỗ trợ | Bằng chứng phản bác |
| --- | --- | --- |
| Lỗi TLS/Bolt | Handshake fail, không qua `verifyConnectivity` | Client vẫn kết nối/query bình thường bằng cùng URI/chứng chỉ |
| DB offline | `currentStatus` khác `online`, log recovery | DB online, query nhẹ trên đúng database thành công |
| Thiếu index | Planner scan lớn, index absent/FAILED | Plan dùng seek phù hợp, DB Hits thấp |
| Lock contention | `waitTime` cao, transaction blocked | Wait time gần 0, CPU/DB Hits cao |
| Page cache/disk | Faults và disk latency cùng tăng | Cache/IO bình thường, app pool pending cao |
| Cluster mất writer | WRITE route unavailable/quorum lỗi | WRITE thành công qua routing, chỉ một role thiếu quyền |
| Lỗi application mapping | Raw Cypher đúng, JSON/DTO sai | Raw result cũng sai tương ứng |
| CDC backlog | Source version cao hơn graph, consumer lag | Version và checkpoint đã bắt kịp, chỉ cache UI stale |

Ghi **độ tin cậy** của mỗi giả thuyết (thấp/vừa/cao) và bằng chứng mới đã thay đổi đánh giá ra sao. Đừng khẳng định 100% khi chưa có phép kiểm chứng quyết định.

## 14. Thu thập support report có kiểm soát

Neo4j tự quản có công cụ:

~~~bash
# Lệnh tại máy chủ Neo4j hoặc môi trường có binary neo4j-admin.
# Chỉ chạy khi được cho phép, đảm bảo đủ dung lượng.
neo4j-admin server report --list
~~~

Để lấy **một gói nhỏ** phục vụ điều tra:

~~~bash
# Ví dụ: chỉ logs + thread dumps, không tự gom heap/tx logs.
neo4j-admin server report \
  --to-path=/srv/incident-reports \
  threads logs
~~~

Tùy version, report có thể gom log, config, metrics, thread dump, cluster state và các loại classifier khác. **Không chọn `all` mặc định**, đặc biệt không tùy tiện thêm `heap`, `tx` hoặc `raft`: chúng có thể chứa dữ liệu nhạy cảm, chiếm nhiều dung lượng và tạo I/O.

Lưu ý:

- Công cụ không tự gửi report cho Neo4j Support; phải chia sẻ **chủ động** theo quy trình bảo mật.
- Xem danh sách classifier và cờ hỗ trợ bằng `--list`/`--help` trên bản thực tế.
- Các classifier bổ sung **từ 2026.08** có thể cần xác thực; không copy cờ mới vào 5.x cũ.
- Trước khi chia sẻ, rà soát thông tin cá nhân, query parameters, hostname nội bộ, token, cấu hình và heap.
- Đặt quyền đọc chặt, retention ngắn, checksum và incident ID cho artifact.
- Không tạo heap dump từ hệ đang thiếu disk/memory nếu không có phương án bảo vệ tài nguyên.

**Support report là công cụ thu thập bằng chứng, không phải bước khắc phục.** Tạo report thành công không đồng nghĩa đã tìm được root cause.

Nguồn: [Neo4j Operations Manual — Generate system report](https://neo4j.com/docs/operations-manual/current/monitoring/neo4j-admin-report/).

## 15. Chọn biện pháp khắc phục ít rủi ro trước

### 15.1. Phân cấp can thiệp

| Mức | Ví dụ | Khi thích hợp |
| --- | --- | --- |
| **0 — Quan sát** | Log, metrics, `SHOW`, `EXPLAIN`, synthetic read | Mặc định, ít rủi ro |
| **1 — Giảm tải** | Giảm concurrency, tạm dừng import/GDS job, rate limit query nặng | Khi có bằng chứng saturation hoặc contention |
| **2 — Sửa application/query** | Rollback release, sửa WHERE/LIMIT, điều chỉnh timeout/pool có cơ sở | Khi lỗi nằm ở app/query |
| **3 — Sửa database config/schema** | Tạo/khôi phục index theo runbook, chỉnh cấu hình có bảo trì | Khi plan/index/resource đã được xác minh |
| **4 — Thay đổi vận hành lớn** | Restart server, failover, restore/seed, đổi cluster topology | Chỉ khi có phê duyệt, backup, kế hoạch ảnh hưởng |
| **5 — Repair data** | Thao tác sửa relationship/node, replay CDC, khôi phục backup | Khi có bằng chứng dữ liệu sai, domain owner xác nhận |

Mức cao hơn **không tự là tốt hơn**. Nếu nguyên nhân là truy vấn `MATCH` không có filter và tạo 10 triệu hàng, restart cluster chỉ làm biến mất bằng chứng và thường không sửa được query.

### 15.2. Cần điều kiện dừng và rollback cho từng thay đổi

Mỗi action record nên có:

~~~text
Action ID: ACT-17
Hypothesis: Batch import giữ khóa quá lâu trên :Inventory
Evidence: 24 transaction waitTime tăng; query log ghi wait cao
Action: Tạm dừng job import, giữ nguyên dịch vụ READ/WRITE
Expected: p95 write giảm; waitTime giảm trong 3 cửa sổ đo
Risks: Import backlog tăng; dữ liệu read model có thể trễ
Rollback: Tiếp tục job với batch nhỏ sau khi sửa logic
Owner/approval: ...
Observed result: ...
~~~

Không đánh dấu “khắc phục thành công” chỉ vì một biểu đồ có vẻ cải thiện ngay sau action; đo theo cửa sổ đủ mẫu và đối chiếu với traffic.

### 15.3. Các hành động không nên làm bừa

- Xóa `data/databases`, transaction log hoặc file index để “giải phóng” disk.
- Vô hiệu hóa uniqueness constraint trước lỗi ghi trùng mà chưa kiểm tra dữ liệu.
- Chạy `TERMINATE TRANSACTIONS` với ID chưa xác minh hoặc terminate theo wildcard không có phê duyệt.
- Restart đồng thời các primary làm mất quorum Neo4j.
- Tắt xác minh TLS, mở unrestricted procedures hoặc cấp admin cho ứng dụng để né lỗi permission.
- Chạy `PROFILE` query ghi ở production rồi coi đó chỉ là quan sát.
- Restore thẳng database đang phục vụ hoặc đổi binary ngược phiên bản mà chưa xem đường migration.

Những thao tác này có thể biến sự cố hiệu năng tạm thời thành **mất dữ liệu hoặc mất tính sẵn sàng**.

## 16. Xác minh sau khắc phục: bốn cổng độc lập

Một action chỉ được đóng khi có **bằng chứng sau** ở những lớp phù hợp.

### Cổng A — Connectivity/availability

- Java Driver `verifyConnectivity()` thành công khi network/TLS/auth đúng.
- `SHOW DATABASES` cho database đích `online` theo phạm vi hỗ trợ.
- Synthetic **READ** trên đúng database và role chạy thành công.
- Nếu nghiệp vụ có ghi: một synthetic **WRITE có kiểm soát** hoặc transaction nghiệp vụ thật commit thành công.
- Với cluster: writer/quorum và routing hợp lệ, các bản sao đang phục hồi như kỳ vọng.

**`RETURN 1` thành công chưa đủ** để kết luận WRITE được hoặc graph traversal đã phục hồi.

### Cổng B — Tính đúng dữ liệu

- Đối chiếu business ID, số lượng và thuộc tính đúng trên tập dữ liệu ảnh hưởng.
- Không có node/relationship trùng do retry; constraint tồn tại và ONLINE khi cần.
- Dữ liệu mất sau restore được replay/đối soát với source of truth.
- Nếu có CDC/outbox: kiểm tra version, checkpoint, backlog và DLQ.
- Nếu có thao tác xóa/repair: xác minh các relationship **không liên quan** không bị thay đổi.

Đừng chỉ so `count(n)`: graph có thể đủ node nhưng thiếu cạnh `PLACED` hoặc hướng relationship sai.

### Cổng C — Hiệu năng và sức khỏe tài nguyên

- p50/p95/p99 của operation bị ảnh hưởng quay về **SLO** dưới tải đại diện.
- Error rate, timeout và retry rate giảm về baseline.
- `Rows`/`DB Hits`, lock wait, page faults và pool pending phù hợp với giả thuyết đã sửa.
- Heap/GC, CPU, disk free, I/O và transaction throughput ổn định.
- Không tạo regression ở operation khác: READ tốt lên nhưng WRITE bị bão hòa không phải thành công trọn vẹn.

### Cổng D — Độ bền và khả năng quay lại sự cố

- Biện pháp được quan sát qua **nhiều cửa sổ** hoặc qua lần job định kỳ tiếp theo.
- Không còn tăng backlog, index không `FAILED`, cluster đủ khả năng chịu lỗi theo SLO.
- Alert và tracing cho dấu hiệu tái phát đã hoạt động.
- Có owner cho giải pháp lâu dài, tránh chỉ để một cấu hình tạm hoặc tắt một job mãi mãi.

### 16.1. Tiêu chí đóng incident mẫu

| Gate | Bằng chứng bắt buộc | Ví dụ PASS |
| --- | --- | --- |
| Availability | Synthetic READ và WRITE theo quyền app | ≥ 99,9% thành công trong cửa sổ được duyệt |
| Data | Không có duplicate/missing trên tập ID bị ảnh hưởng | `orderId` và `PLACED` chính xác theo nguồn |
| Performance | p95/p99 & throughput dưới tải | p95 lookup ≤ 200 ms, p99 ≤ 500 ms |
| Stability | Không tái phát, tài nguyên hợp lý | 30 phút ổn định + batch job chạy lại không lỗi |
| Observability | Alert/trace có thể phát hiện tái phát | Dashboard và runbook được cập nhật |

**Các ngưỡng là ví dụ**, phải định nghĩa theo workload/SLO của dự án. Đối với một sự cố mất dữ liệu, chỉ 30 phút ổn định không đủ; cần **reconciliation và xác nhận của domain owner**.

## 17. Tình huống thực tế A: API đọc chậm sau release

**Bối cảnh:** Endpoint `GET /customers/{id}/orders` tăng p95 từ 80 ms lên 1.100 ms ngay sau một release Spring Data Neo4j. Database vẫn online, không có lỗi xác thực.

### Quan sát

1. APM cho thấy thời gian tập trung ở repository call, không phải HTTP serialization.
2. Query log xuất hiện query mới trả **node `Customer` và toàn bộ `Order` entities** thay vì hai trường DTO.
3. `PROFILE` cho thấy `Expand(All)` từ một customer bậc cao qua **50.000** cạnh `PLACED`; `Rows` và `DB Hits` tăng.
4. `SHOW INDEXES` xác nhận index trên `Customer.customerId` vẫn `ONLINE`; việc thêm index này nữa không xử lý fan-out.

### Giả thuyết/khắc phục

Release đã đổi từ DTO query có `ORDER BY ... LIMIT 20` sang entity mapping tải graph rộng. Rollback endpoint hoặc thay bằng `Neo4jClient`/Cypher trả **chỉ 20 order cần thiết**, giới hạn payload theo use case.

### Xác minh

- So kết quả 20 đơn đúng ID/order và thứ tự ổn định.
- `Rows`/bytes trả về giảm; API p95/p99 về SLO dưới cùng lượng request.
- Kiểm tra customer có **0, 1 và 50.000 đơn**.
- Kiểm tra những endpoint khác dùng full entity không bị thay đổi ngoài ý muốn.

**Bài học:** “Index đã online” và “database healthy” không loại trừ **query shape regression**.

## 18. Tình huống thực tế B: WRITE timeout nhưng READ vẫn tốt

**Bối cảnh:** `POST /orders` thường xuyên timeout, nhưng màn hình danh sách vẫn đọc được.

### Hai khả năng dễ nhầm

**Khả năng 1 — Cluster mất writer/quorum:**

- Driver có thông báo routing/write unavailable.
- `SHOW DATABASES` trên cụm cho thấy writer không khả dụng hoặc primary chưa đủ quorum.
- `SHOW TRANSACTIONS` không cho thấy lock wait tăng bất thường vì request có thể **không tới bước chạy transaction**.

**Khả năng 2 — Hotspot khóa trong database:**

- Writer vẫn sẵn sàng; một số WRITE nhỏ có thể thành công.
- Transaction ghi cùng `Inventory` hoặc `Account` có `waitTime` tăng, nhiều giao dịch blocked.
- Query log/APM cho thấy request đợi lâu sau khi đã vào transaction.

### Phép kiểm tra phân biệt

1. Test **READ** và **WRITE canary** riêng với quyền hợp lệ.
2. Xem trạng thái writer/quorum và routing driver.
3. Xem `SHOW TRANSACTIONS` về status, waitTime, elapsedTime và query.
4. Đối chiếu disk, CPU, GC, pool pending và timeline của job ghi.

### Biện pháp

- Nếu **mất quorum**, phục hồi network/server theo runbook cluster; **không force leader** bằng cách phá state.
- Nếu **lock contention**, giảm batch/concurrency, tránh transaction dài, tối ưu thứ tự cập nhật/hotspot; terminate chỉ khi được duyệt.

### Xác minh

Synthetic WRITE commit thành công, error/retry rate về baseline, không đơn nào được tạo trùng bởi request timeout/retry, và các primary/secondary phục hồi trạng thái đáp ứng SLO.

**Bài học:** Hai sự cố có cùng biểu hiện “write timeout” nhưng cách sửa hoàn toàn khác nhau.

## 19. Bài thực hành: xây hồ sơ bằng chứng và báo cáo RCA

### Bối cảnh phòng lab

Ứng dụng Java có hai use case:

- `readCustomerOrders(customerId)` chạy `MATCH (c)-[:PLACED]->(o)` và trả danh sách đơn.
- `placeOrder(orderId, customerId)` chạy nhiều câu Cypher trong `executeWrite`.

Neo4j có constraint `Customer.customerId` và `Order.orderId`; database thử nghiệm là `graph_lab`. Hệ thống được giả lập có p95 READ tăng, một vài WRITE bị timeout, và bản deploy mới xuất hiện trước đó 10 phút.

### Bước 1 — Ghi báo cáo tác động

Điền:

~~~text
Incident ID:
Environment/database:
Start time (UTC):
Affected operations:
Users/traffic affected:
Error messages + driver codes:
Last known good:
Recent changes:
Immediate data risk:
Incident owner:
~~~

Không log mật khẩu, raw token, ID khách hàng thật hoặc payload chứa thông tin nhạy cảm vào bài thực hành.

### Bước 2 — Thu bằng chứng không ghi dữ liệu

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

~~~cypher
SHOW DATABASES
YIELD name, currentStatus, statusMessage
RETURN name, currentStatus, statusMessage;
~~~

~~~cypher
SHOW INDEXES
YIELD name, type, state, populationPercent
RETURN name, type, state, populationPercent;
~~~

~~~cypher
SHOW TRANSACTIONS
YIELD transactionId, database, status, elapsedTime, waitTime
RETURN transactionId, database, status, elapsedTime, waitTime
ORDER BY elapsedTime DESC
LIMIT 20;
~~~

**Ghi rõ cột nào được version/edition lab hỗ trợ**. Nếu quyền không cho xem transaction của user khác, đó là giới hạn điều tra cần báo, không được tự cấp quyền admin cho app.

### Bước 3 — Chụp plan một query chậm

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId
ORDER BY o.orderId
LIMIT 20;
~~~

Khi dataset nhỏ/lab và query chỉ đọc:

~~~cypher
PROFILE
MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId
ORDER BY o.orderId
LIMIT 20;
~~~

Ghi các toán tử chính, `Rows`, `DB Hits`, có index seek không, có sort/fan-out lớn không.

### Bước 4 — Lập ba giả thuyết

Ví dụ:

| Mã | Giả thuyết | Phép thử phân biệt |
| --- | --- | --- |
| H1 | Index `Customer.customerId` đã `FAILED` | `SHOW INDEXES` + `PROFILE` có scan |
| H2 | Release mới tạo entity graph quá rộng | So generated Cypher/DTO, `Rows` và response bytes |
| H3 | Batch WRITE giữ khóa làm READ/WRITE bị nghẽn | `SHOW TRANSACTIONS` waitTime và lịch import |

Nêu rõ **bằng chứng nào bác bỏ** từng giả thuyết. Không tìm cách “chứng minh bằng được” H1 chỉ vì nó dễ sửa.

### Bước 5 — Mô phỏng một biện pháp ít rủi ro

Trong môi trường lab, dùng dữ liệu giả và workload đo được. Có thể:

- Thay query trả full entity bằng DTO có `LIMIT` rõ ràng; hoặc
- Giảm batch size của job ghi trong khi giữ nguyên dữ liệu nghiệp vụ.

Chọn **một thay đổi mỗi lần** và đo lại. Không xóa index, không terminate ngẫu nhiên, không restart cụm để tạo “thành công giả”.

### Bước 6 — Xác minh bằng các cổng

Tạo bảng:

| Tiêu chí | Trước | Sau | PASS/FAIL |
| --- | --- | --- | --- |
| Read probe | ... | ... | ... |
| Write transaction commit | ... | ... | ... |
| Số Order/relationship trên tập ID kiểm tra | ... | ... | ... |
| p95/p99 dưới tải tương đương | ... | ... | ... |
| `Rows`/`DB Hits` | ... | ... | ... |
| Lock wait/pool pending | ... | ... | ... |
| Alerts ổn định sau chu kỳ job | ... | ... | ... |

### Bước 7 — Viết postmortem ngắn

~~~text
What happened:
User impact and duration:
Root cause (confirmed) and evidence:
Contributing conditions:
Why alerts/detection were delayed:
Mitigation (time, owner, risk):
Permanent fix:
Verification (data + performance + availability):
Preventive actions (owner, deadline):
Open risks and follow-up:
~~~

**Khi chưa xác định được root cause**, viết rõ “chưa xác định” cùng các giả thuyết còn mở. Một postmortem hữu ích không cần giả vờ chắc chắn.

### Câu hỏi tự kiểm tra

**1. `verifyConnectivity()` thành công có đủ kết luận database khỏe không?** Không. Nó không chứng minh một database đích online, quyền READ/WRITE đúng hoặc query traversal đáp ứng SLO.

**2. Vì sao nên thu `SHOW TRANSACTIONS` trước khi restart?** Vì trạng thái running/blocked, waitTime và transaction IDs thay đổi hoặc biến mất sau restart.

**3. `PROFILE` query ghi có an toàn như `EXPLAIN` không?** Không. PROFILE thực thi thật; query ghi có thể thay đổi dữ liệu.

**4. Khi `waitTime` tăng cao, có nên lập tức tạo index mới?** Không. Trước tiên phân biệt lock contention với scan/index bằng transaction state và plan, rồi kiểm tra chi phí/rủi ro của giải pháp.

**5. Nếu ứng dụng bị timeout gần lúc commit, retry cùng request có tạo trùng không?** Có thể, nếu thiếu business ID/idempotency/constraint. Cần kiểm tra trạng thái commit theo khóa nghiệp vụ trước khi thử lại.

**6. Cluster có 3 primary, READ được nhưng WRITE lỗi. Có thể suy luận database đã mất dữ liệu không?** Không. Kiểm tra writer/quorum, trạng thái từng bản sao và sự cố network; WRITE unavailable không đồng nghĩa store bị xóa.

**7. Sau khi sửa, p95 trở lại bình thường nhưng có 50 đơn thiếu relationship. Đóng incident được chưa?** Chưa. Cổng **data correctness** chưa đạt; cần đối soát và repair có kiểm soát.

**8. Vì sao không chọn `neo4j-admin server report all` cho mọi sự cố?** Vì có thể gom dữ liệu nhạy cảm/khối lượng lớn (heap, transaction logs, config), gây áp lực I/O/disk. Chọn classifier cần thiết, redaction và quyền phù hợp.

## 20. Checklist xử lý sự cố Neo4j

- [ ] Xác định **tác động, READ/WRITE, database, thời điểm UTC, mức độ và người điều phối**.
- [ ] Tách triệu chứng, giả thuyết, bằng chứng và nguyên nhân đã xác nhận.
- [ ] Ghi lại **thay đổi gần nhất**: release, index, config, plugin, backup, import, GDS, network/TLS.
- [ ] Thu logs/metrics ở khoảng **trước–trong–sau**, đồng bộ timestamp và bảo vệ dữ liệu nhạy cảm.
- [ ] Lấy `SHOW DATABASES`, `SHOW INDEXES`, `SHOW CONSTRAINTS`, `SHOW TRANSACTIONS` khi quyền/version hỗ trợ.
- [ ] Với cluster, kiểm tra writer/quorum, database allocations, lag và routing riêng cho READ/WRITE.
- [ ] Với query chậm, dùng `EXPLAIN` trước, `PROFILE` chỉ khi an toàn; so `Rows`, `DB Hits`, index state và fan-out.
- [ ] Đối chiếu p95/p99 API với pool pending, network, retries và metrics Neo4j, không quy lỗi ngay cho database.
- [ ] Kiểm tra heap/GC, page cache, disk free/I/O, container restart/OOM và transaction log.
- [ ] Với lỗi Java Driver, đọc exception class, Neo4j/GQL status, database name, URI/TLS/auth và causal bookmark.
- [ ] Với lỗi dữ liệu, đối soát theo **business ID và relationship**, không chỉ theo tổng số node.
- [ ] Tạo support report **có chọn lọc**, kiểm soát disk, quyền và redaction; không thu `all` mặc định.
- [ ] Ưu tiên biện pháp **ít rủi ro**, mỗi thay đổi có owner, expected result và rollback plan.
- [ ] Không xóa store/log, tắt constraint, terminate hàng loạt hoặc restart tất cả primary theo phản xạ.
- [ ] Sau sửa, xác minh **availability, data correctness, performance và stability** bằng bằng chứng.
- [ ] Kiểm tra không có **request retry tạo trùng**, CDC backlog hoặc dữ liệu cũ sau restore.
- [ ] Chỉ đóng incident khi đạt SLO và invariant nghiệp vụ, có người xác nhận và hành động phòng ngừa.
- [ ] Lưu timeline, nguyên nhân, bài học, runbook và alert cải tiến cho lần sau.

## Tài liệu tham khảo

- [Neo4j Operations Manual — Monitoring](https://neo4j.com/docs/operations-manual/current/monitoring/)
- [Neo4j Operations Manual — Logging](https://neo4j.com/docs/operations-manual/current/monitoring/logging/)
- [Neo4j Operations Manual — Metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/)
- [Neo4j Operations Manual — Show and terminate transactions](https://neo4j.com/docs/operations-manual/current/database-internals/show-and-terminate-transactions/)
- [Neo4j Operations Manual — Generate a server report](https://neo4j.com/docs/operations-manual/current/monitoring/neo4j-admin-report/)
- [Neo4j Cypher Manual — Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/)
- [Neo4j Cypher Manual — SHOW INDEXES](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/list-indexes/)
- [Neo4j Operations Manual — Clustering](https://neo4j.com/docs/operations-manual/current/clustering/)
- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual — Connect](https://neo4j.com/docs/java-manual/current/connect/)
- [Neo4j Status Codes — Server errors](https://neo4j.com/docs/status-codes/current/errors/)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)

**Kết luận:** Khắc phục sự cố Neo4j hiệu quả phải bắt đầu bằng **bằng chứng có thể đối chiếu**: phạm vi và timeline, log/metrics, transaction đang chạy, trạng thái database/index, query plan, lỗi Java Driver và đối soát property graph. Từ đó đặt giả thuyết có thể bác bỏ, chọn biện pháp ít rủi ro và kiểm chứng sau sửa ở **bốn cổng độc lập: sẵn sàng, đúng dữ liệu, hiệu năng, ổn định**. Chỉ khi các cổng đạt tiêu chí nghiệp vụ, có thể kết luận sự cố đã được xử lý thay vì chỉ tạm thời hết thông báo lỗi.
