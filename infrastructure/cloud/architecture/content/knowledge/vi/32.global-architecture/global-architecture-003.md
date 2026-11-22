# Phân bố quyền ghi và quyền sở hữu dữ liệu theo khu vực

## 1. Vì sao kiến trúc toàn cầu cần xác định rõ quyền ghi?

Ứng dụng phục vụ nhiều quốc gia thường triển khai compute và database ở nhiều region để giảm latency, tăng khả năng chịu lỗi và đáp ứng yêu cầu vị trí dữ liệu. Tuy nhiên, khi nhiều region cùng có thể nhận lệnh ghi, câu hỏi quan trọng không chỉ là dữ liệu được replicate tới đâu mà là **region nào có quyền quyết định giá trị đúng của dữ liệu**.

Nếu hai region cùng cập nhật một bản ghi khách hàng, số dư, tồn kho hoặc trạng thái đơn hàng mà không có quy tắc ownership, hệ thống có thể tạo ra lost update, ghi đè lẫn nhau, trạng thái không hợp lệ hoặc số dư sai. Một thiết kế active-active chỉ nhân đôi endpoint và bật replication không tự giải quyết được các vấn đề này.

Trong module **CLOUD_ARCHITECTURE**, phân bố quyền ghi là quyết định kiến trúc liên quan tới consistency, latency, availability, data residency, failure recovery và vận hành. Mục tiêu là xác định ai được ghi vào dữ liệu nào, trong điều kiện nào, và hệ thống xử lý ra sao khi owner mất kết nối hoặc hai phía đồng thời thay đổi dữ liệu.

Sau bài học, bạn có thể:

- Phân biệt data location, data ownership, write authority và read routing.
- Chọn single-writer, regional ownership hoặc multi-writer theo semantics nghiệp vụ.
- Thiết kế phân vùng dữ liệu theo tenant, entity, geography hoặc aggregate boundary.
- Xây dựng write routing, fencing và failover có kiểm soát.
- Lựa chọn consistency guarantee và conflict resolution phù hợp.
- Xử lý replication lag, duplicate, retry, out-of-order event và stale read.
- Đánh giá active-active, active-passive và regional cell theo RTO/RPO, latency và cost.
- Đặt governance, observability và quy trình thay đổi ownership trong production.

## 2. Những khái niệm cần tách biệt

Các hệ thống thường dùng từ “owner” với nhiều ý nghĩa. Cần định nghĩa rõ trong architecture decision record và data contract.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Data location | Nơi bản dữ liệu được lưu | Primary database ở region A, replica ở B |
| Data residency | Ranh giới địa lý nơi dữ liệu được phép lưu/xử lý | Dataset bị giới hạn trong jurisdiction đã duyệt |
| Data owner | Vai trò nghiệp vụ chịu trách nhiệm về meaning, quality và allowed use | Team Customer chịu trách nhiệm hồ sơ khách hàng |
| Write authority | Thành phần/region được phép chấp nhận và quyết định write | Region A là writer của customer record |
| Entity ownership | Quy tắc xác định region hoặc partition sở hữu một entity | Customer ID được gán về home region |
| Read routing | Quy tắc chọn nguồn phục vụ read | Đọc local replica hoặc home region |
| Replication | Cơ chế truyền thay đổi sang nơi khác | WAL replication, change stream hoặc event |
| Conflict resolution | Quy tắc xử lý nhiều thay đổi không tương thích | Version check, merge hoặc domain-specific decision |

Một region có thể chứa replica nhưng không có write authority. Ngược lại, data owner nghiệp vụ có thể ở một quốc gia trong khi workload kỹ thuật phục vụ entity chạy tại region khác đã được phê duyệt. Không suy quyền ghi từ việc một database endpoint đang reachable.

### 2.1. Ownership cần xác định theo aggregate

Trong domain-driven design, aggregate là ranh giới nhất quán mà business rule cần được thực thi nguyên tử. Một entity hoặc aggregate nên có một nơi chịu trách nhiệm quyết định các invariant quan trọng, trừ khi domain có protocol phân tán rõ ràng.

Ví dụ:

- Customer profile có thể được gán home region theo customer ID.
- Inventory của một kho có thể thuộc region nơi kho vận hành.
- Order có thể thuộc region tiếp nhận checkout hoặc region của merchant.
- Global catalog có thể được quản trị bởi một writer toàn cục.
- Analytics projection có thể được rebuild từ event và không có write authority nghiệp vụ.

Nếu một nghiệp vụ cần update đồng thời nhiều aggregate thuộc nhiều region, phải xác định saga/process manager, transaction boundary và trạng thái trung gian thay vì giả định một database transaction xuyên region.

## 3. Ba mô hình phân bố quyền ghi

Ba mô hình cơ bản khác nhau ở nơi chấp nhận write và cách phân chia ownership.

| Mô hình | Quyền ghi | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| Single-writer toàn cục | Một region/leader nhận write cho dataset | Quy tắc đơn giản, ít conflict, strong consistency dễ hơn | Write latency liên vùng, phụ thuộc writer region |
| Regional ownership / partitioned writers | Mỗi region sở hữu một tập entity/partition riêng | Local write nhanh, giảm conflict nếu ownership không chồng lấn | Cần định tuyến entity, chuyển ownership và xử lý giao dịch liên vùng |
| Multi-writer / active-active | Nhiều region có thể ghi cùng dataset/entity | Availability và local write tốt trong một số workload | Conflict, consistency, ordering và reconciliation phức tạp |

Không có mô hình nào luôn tốt nhất. Lựa chọn phụ thuộc vào việc cùng một entity có thể được ghi đồng thời ở nhiều nơi hay không, business invariant nào phải giữ và thời gian chờ khi owner không khả dụng.

### 3.1. Single-writer toàn cục

Một region giữ vai trò writer; các region còn lại phục vụ read hoặc giữ standby/replica. Request ghi được chuyển tới writer hoặc đi qua service sở hữu dữ liệu.

~~~mermaid
flowchart TB
    R1["Users / Region A"] --> API1["Regional API A"]
    R2["Users / Region B"] --> API2["Regional API B"]
    R3["Users / Region C"] --> API3["Regional API C"]
    API1 --> W["Global write authority"]
    API2 --> W
    API3 --> W
    W --> P[("Primary database")]
    P -->|Replication| RDB[("Read replicas A/B")]
    API1 --> RDB
    API2 --> RDB
    API3 --> RDB
~~~

Mô hình phù hợp với dữ liệu có invariant toàn cục khó hòa giải, ví dụ ledger hoặc một số trạng thái thanh toán. Read replica có thể phục vụ read local nếu ứng dụng chấp nhận freshness guarantee tương ứng.

Nhược điểm là write phải vượt network tới region writer. Khi writer region mất, failover cần fencing và chọn recovery point trước khi promote region mới.

### 3.2. Regional ownership theo partition

Mỗi entity hoặc partition có một owner region tại một thời điểm. Request được route tới owner; region khác có thể giữ replica để đọc hoặc DR nhưng không được tự ghi entity đó nếu chưa có quyền.

~~~mermaid
flowchart TB
    Router["Global ownership router"]
    Router --> A["Region A API"]
    Router --> B["Region B API"]
    Router --> C["Region C API"]
    A --> DA[("Partition set A")]
    B --> DB[("Partition set B")]
    C --> DC[("Partition set C")]
    DA -. "Replicas / events" .-> DB
    DB -. "Replicas / events" .-> DC
~~~

Mô hình phù hợp khi có thể chia domain theo tenant, customer, merchant, warehouse hoặc geography sao cho các write quan trọng chủ yếu nằm trong một ownership boundary.

### 3.3. Multi-writer active-active

Nhiều region có thể nhận ghi, có thể cùng một entity. Hệ thống cần xác định conflict detection, merge semantics, ordering và quyền ưu tiên. Multi-writer phù hợp khi domain chấp nhận merge hoặc dữ liệu có thể phân chia đủ độc lập; nó nguy hiểm khi dùng cho dữ liệu tài chính, tồn kho hoặc trạng thái cần invariant nghiêm ngặt mà chưa có protocol.

Không gọi mô hình là active-active chỉ vì mỗi region có database instance. Cần nêu rõ write path, consistency model, conflict rate, behavior khi partition và cách chứng minh không có hai writer trái phép.

## 4. Chọn ownership boundary và partition key

Regional ownership chỉ hiệu quả khi partition key phản ánh domain và hạn chế được các thao tác cần phối hợp liên vùng.

### 4.1. Các chiến lược phân vùng

| Chiến lược | Ví dụ key | Phù hợp | Rủi ro |
| --- | --- | --- | --- |
| Tenant-based | tenant_id | SaaS nhiều khách hàng có dữ liệu tách biệt | Tenant lớn tạo hotspot; tenant migration phức tạp |
| Customer/entity-based | customer_id, account_id | Hồ sơ và hoạt động gắn với một chủ thể | Một giao dịch liên quan nhiều customer có thể cross-region |
| Geography-based | country, market, jurisdiction | Locality và data residency | Người dùng/đơn hàng di chuyển; biên địa lý không trùng business ownership |
| Resource-location-based | warehouse_id, store_id | Inventory, logistics, branch operations | Chuyển kho hoặc order liên vùng cần workflow |
| Hash/shard-based | hash(entity_id) | Phân bố tải đồng đều | Ownership khó giải thích và không tự phản ánh residency |
| Domain-based | ledger_id, merchant_id | Tách bounded context | Domain transaction vẫn có thể cần phối hợp |

### 4.2. Tiêu chí chọn partition key

- **Invariant locality:** những thao tác cần atomic consistency có cùng owner hay không?
- **Traffic distribution:** key có thể tạo hotspot hoặc skew không?
- **Data residency:** partition có thể đặt tại nơi được phép không?
- **Routing simplicity:** request có thể xác định owner trước khi gọi write service không?
- **Mobility:** entity có thường xuyên đổi market, tenant hoặc warehouse không?
- **Scale:** số partition và khả năng rebalance có đáp ứng tăng trưởng không?
- **Recovery:** partition có thể được promote ở region khác trong thời gian mục tiêu không?

Không chọn partition key chỉ vì dễ hash. Ví dụ, order theo customer có thể thuộc home region của customer, nhưng inventory thuộc warehouse region. Checkout cần reservation từ cả hai domain; giải pháp nên dùng saga/command giữa owner thay vì nhân bản quyền ghi của inventory.

### 4.3. Home region và ownership registry

Một ownership registry có thể ánh xạ entity/partition tới owner:

| Entity/partition | Owner region | Replica regions | Ownership epoch | Status |
| --- | --- | --- | ---: | --- |
| customer-shard-01 | region-a | region-b | 12 | Active |
| customer-shard-02 | region-b | region-a | 7 | Active |
| warehouse-17 | region-c | region-a | 4 | Active |
| global-catalog | region-a | region-b, region-c | 21 | Active |

Registry cần authoritative source, version, audit và cache policy. Router có thể cache mapping để giảm latency nhưng phải xử lý stale ownership khi entity được chuyển. Không để mọi application tự giữ mapping tĩnh trong config.

### 4.4. Ownership epoch và fencing token

Mỗi lần chuyển owner, tăng epoch/generation. Write request phải mang epoch hiện hành; data service chỉ chấp nhận request nếu token đúng với ownership đã được commit.

Ví dụ logic:

~~~text
write(entity, expected_epoch, command):
    current = ownership_registry.lookup(entity)
    if expected_epoch != current.epoch:
        reject(STALE_OWNER)
    if current.region != local_region:
        reject(NOT_OWNER)
    persist(command, fencing_epoch=current.epoch)
~~~

Đây là pseudo-code. Kiểm tra phải được thực thi ở nơi có authority ghi dữ liệu, không chỉ ở router/API. Nếu một client cũ vẫn kết nối tới database primary sau failover, fencing tại data plane ngăn nó ghi bằng epoch cũ.

## 5. Write routing và read routing

Global routing chọn region theo latency hoặc health; ownership routing chọn nơi có quyền ghi. Hai quyết định có thể khác nhau. Request đọc có thể đi tới region gần nhất, nhưng command cập nhật entity phải tới owner.

### 5.1. Write path theo ownership

~~~mermaid
sequenceDiagram
    participant Client
    participant Edge as Global/API Router
    participant Registry as Ownership Registry
    participant Owner as Owner Region Service
    participant DB as Owner Database
    Client->>Edge: Update entity E
    Edge->>Registry: Resolve owner(E), epoch
    Registry-->>Edge: region B, epoch 18
    Edge->>Owner: Command + expected epoch 18
    Owner->>DB: Validate owner/epoch and commit
    DB-->>Owner: Commit result + version
    Owner-->>Edge: Result
    Edge-->>Client: Response
~~~

Router lookup có thể nằm trong service hoặc SDK và được cache; tuy nhiên write service vẫn phải xác minh authority. Response nên trả entity version/commit token để client có thể yêu cầu read-your-writes ở lần đọc tiếp theo.

### 5.2. Read routing

Có thể chọn:

- **Home-region read:** đọc từ owner, phù hợp khi cần latest state.
- **Local replica read:** giảm latency nhưng có thể stale.
- **Read-your-writes:** sau write, route client/operation tới owner hoặc replica đã bắt kịp commit version.
- **Bounded-staleness read:** chỉ đọc replica khi lag nằm trong giới hạn nghiệp vụ.
- **Fallback read:** khi owner lỗi, trả bản sao kèm freshness marker hoặc trả lỗi/degraded response.

Không route mọi read tới replica gần nhất một cách mù quáng. Trạng thái payment, reservation hoặc quyền truy cập có thể cần strong consistency; product listing hoặc recommendation có thể chấp nhận eventual consistency.

### 5.3. Cache ownership và invalidation

Ownership registry, route table và entity cache thường có TTL. Khi ownership thay đổi, cần invalidation hoặc version check. TTL dài làm giảm lookup load nhưng tăng nguy cơ gửi write tới owner cũ. TTL ngắn tăng traffic registry và phụ thuộc control plane.

Có thể kết hợp push invalidation, short TTL, epoch validation và retry có giới hạn khi nhận STALE_OWNER. Không retry vô hạn vì mapping cũ hoặc registry outage có thể tạo storm.

### 5.4. Idempotency và request retry

Client có thể mất response sau khi owner commit thành công rồi retry sang region khác. Command cần idempotency key/operation ID để phát hiện operation đã thực hiện. Idempotency scope phải gắn với business operation, tenant và retention phù hợp; không chỉ dựa vào request ID do proxy tự tạo lại.

## 6. Consistency model theo ownership

Ownership giúp quyết định ai được ghi, nhưng không tự đảm bảo mọi read ở mọi region thấy dữ liệu mới ngay.

| Guarantee | Hành vi | Khi nào dùng |
| --- | --- | --- |
| Strong/linearizable write | Mọi write được sắp thứ tự như một điểm commit duy nhất | Ledger, balance, critical reservation |
| Read-your-writes | Client nhìn thấy write trước của chính mình | Profile update, settings |
| Monotonic reads | Một client không thấy version lùi | Session/account views |
| Bounded staleness | Độ trễ replica nằm trong giới hạn xác định | Dashboard vận hành, catalog |
| Eventual consistency | Replica hội tụ khi không có write mới hoặc conflict được giải quyết | Feed, recommendation, analytics |

### 6.1. Strong consistency và latency

Nếu cần synchronous/quorum replication giữa hai region trước khi ACK, write latency sẽ chịu RTT liên vùng và hệ thống phụ thuộc đường kết nối. Có thể chọn primary region gần owner để local commit nhanh, rồi replicate async; đổi lại RPO khác 0 trong disaster.

Không quảng cáo “strong consistency toàn cầu” nếu chỉ có local database transaction và asynchronous replication. Cam kết consistency phải nói rõ phạm vi entity, commit point, read path và behavior khi region/network partition.

### 6.2. Read-your-writes token

Sau khi write commit, service có thể trả entity version hoặc commit position. Client gửi token này cho read tiếp theo; router chỉ chọn replica đã đạt ít nhất version đó hoặc route về owner. Nếu chưa có replica đáp ứng, hệ thống có thể chờ có giới hạn, đọc từ owner hoặc trả trạng thái chưa sẵn sàng.

### 6.3. Cross-region transaction

Tránh thiết kế transaction đồng bộ xuyên nhiều database region nếu domain có thể tách thành local transaction và event-driven workflow. Saga điều phối chuỗi bước, mỗi bước commit cục bộ và có compensating action khi bước sau thất bại.

Compensation không phải rollback vật lý của transaction đã commit; ví dụ refund là một giao dịch mới bù trừ charge. Business state cần mô hình hóa trạng thái pending/confirmed/compensated và timeout rõ ràng.

## 7. Multi-writer và conflict resolution

Multi-writer chỉ an toàn khi hệ thống xác định được hai write có xung đột hay không, cách phân xử và các invariant vẫn đúng sau merge.

### 7.1. Các loại conflict

- **Concurrent update:** hai region cập nhật cùng một field/entity trước khi thấy thay đổi của nhau.
- **Delete/update race:** một region xóa entity, region khác cập nhật bản cũ.
- **Unique constraint conflict:** hai region tạo cùng business key hoặc username.
- **Ordering conflict:** event tới sai thứ tự hoặc timestamp khác nhau.
- **Invariant conflict:** từng write hợp lệ cục bộ nhưng kết hợp lại vi phạm tổng thể, ví dụ oversell inventory.
- **Ownership conflict:** hai region cùng tin mình là owner sau network partition hoặc failover.

### 7.2. Các chiến lược giải quyết

| Chiến lược | Cách làm | Phù hợp | Rủi ro |
| --- | --- | --- | --- |
| Last-write-wins | Chọn theo timestamp/version/priority | Một số preference có thể ghi đè | Đồng hồ lệch; mất update có ý nghĩa |
| Version/optimistic concurrency | Compare-and-set theo version; reject stale write | Entity cần phát hiện lost update | Client phải retry/merge |
| Field-level merge | Kết hợp field không xung đột | Profile có field độc lập | Quan hệ giữa field có thể bị phá |
| Domain-specific resolver | Áp quy tắc nghiệp vụ | Inventory, booking, financial state | Cần thiết kế/test kỹ |
| CRDT | Dùng cấu trúc dữ liệu có phép merge hội tụ | Counter/set/collection phù hợp | Không áp dụng cho mọi invariant hoặc transaction |
| Single-owner arbitration | Đưa conflict về owner duy nhất | Critical aggregate | Tăng routing/availability dependency |

Không chọn last-write-wins làm mặc định cho tất cả bảng. Timestamp do client cung cấp hoặc clock của hai region lệch có thể khiến write cũ thắng write mới.

### 7.3. Domain example: profile

Một người dùng có thể sửa display name ở thiết bị A và đổi ngôn ngữ ở thiết bị B cùng lúc. Nếu hai field độc lập, field-level merge có thể giữ cả hai thay đổi. Nhưng nếu cùng thay đổi địa chỉ giao hàng hoặc trạng thái account, cần version check hoặc nghiệp vụ arbitration.

### 7.4. Domain example: inventory

Hai region không nên cùng giảm stock từ một bản sao stale khi lượng tồn kho hữu hạn. Cách tiếp cận có thể là:

- Mỗi warehouse giữ quyền sở hữu stock của chính warehouse đó.
- Reservation được gửi tới warehouse owner và trả reservation ID.
- Nếu cần pool tồn toàn cầu, dùng quota allocation/escrow để mỗi region chỉ bán trong phần quota được cấp.
- Khi chuyển quota, dùng protocol để tránh cùng lúc hai region có quyền tiêu cùng đơn vị tồn kho.

### 7.5. CRDT và giới hạn

CRDT có thể giúp các replica hội tụ mà không cần coordinator trong một số cấu trúc như grow-only counter hoặc set. Tuy nhiên, một counter có thể merge đúng mà vẫn vi phạm business limit; ví dụ hai region cùng tăng reservation làm tổng vượt stock. Cần kiểm tra invariant ngoài khả năng merge dữ liệu.

### 7.6. Conflict queue và manual resolution

Một số conflict không thể tự động giải quyết. Đưa chúng vào conflict queue có trạng thái, owner, source versions, reason, deadline và audit. Cho phép human review với quyền hạn hẹp; không âm thầm chọn một giá trị rồi bỏ mất evidence.

## 8. Command/event ownership và event-driven architecture

Trong kiến trúc event-driven, command nên gửi tới owner có authority; event thông báo thay đổi đã commit và có thể được replicate tới các region khác.

### 8.1. Command ownership và event distribution

~~~mermaid
flowchart LR
    Client["Client / regional API"] --> Router["Ownership router"]
    Router --> Owner["Domain owner service"]
    Owner --> DB[("Owner database")]
    DB --> Outbox["Transactional outbox"]
    Outbox --> Broker["Event broker"]
    Broker --> R1["Regional consumer A"]
    Broker --> R2["Regional consumer B"]
    R1 --> ReadA[("Local read model A")]
    R2 --> ReadB[("Local read model B")]
~~~

Command yêu cầu thay đổi state; event biểu diễn sự kiện đã xảy ra. Không phát event “OrderPaid” trước khi transaction thanh toán được xác nhận. Transactional outbox giúp lưu state change và event intent cùng transaction cục bộ; publisher có thể retry, nên consumer vẫn cần idempotency.

### 8.2. Event schema và ordering

- Có event ID duy nhất, aggregate/entity ID và version/sequence.
- Dùng partition key nhất quán để giữ ordering trong phạm vi cần thiết.
- Consumer lưu checkpoint và chống xử lý trùng.
- Event schema có version và compatibility rules.
- Xử lý late/out-of-order event bằng version check hoặc reorder window có giới hạn.
- DLQ có owner và replay procedure.

Timestamp không thay thế sequence nếu cần ordering chính xác. Hai region có clock lệch có thể phát event timestamp không phản ánh thứ tự commit.

### 8.3. Local read model

Region nhận event có thể tạo projection để phục vụ read local. Projection cần có freshness marker, last processed sequence và trạng thái lag. Khi user vừa thực hiện write ở owner, read model local có thể chưa bắt kịp; áp dụng read-your-writes token hoặc route read về owner.

### 8.4. Replay và rebuild

Consumer hoặc region mới có thể rebuild projection từ event log nếu retention đủ. Rebuild cần giới hạn throughput để không ảnh hưởng traffic live; kiểm tra schema version, tombstone, compaction và event ordering. Event log có thể chứa PII nên retention/location phải theo policy dữ liệu.

## 9. Failover ownership và chống split-brain

Khi owner region mất, tổ chức có thể chuyển ownership sang region khác. Đây là thay đổi quyền ghi, cần coordination chặt hơn việc route user sang endpoint mới.

### 9.1. Các bước failover

1. Phát hiện sự cố và xác định failure domain.
2. Xác minh primary cũ không còn khả năng nhận/commit write hoặc chủ động fence.
3. Kiểm tra replica lag, log position và recovery point.
4. Chọn region mới theo policy và kiểm tra capacity/key/network.
5. Tăng ownership epoch hoặc leader term.
6. Promote writer và cập nhật ownership registry.
7. Mở write path tới owner mới; từ chối token/epoch cũ.
8. Chuyển traffic, kiểm tra business invariant và giám sát replication.

Không thực hiện bước 7 trước khi bước 5–6 được commit và có bằng chứng writer cũ bị fence.

### 9.2. Fencing

Fencing có thể dựa trên:

- Lease/quorum/consensus protocol của datastore.
- Monotonic fencing token/epoch được kiểm tra ở write path.
- Revocation credential hoặc disable endpoint cũ kết hợp network isolation.
- Provider-supported database promotion có leader generation.

Chỉ đổi DNS không đủ vì client có thể giữ connection và route cache. Thu hồi credential cũng có thể không đóng các session đã xác thực nếu database không kill/revoke session.

### 9.3. Split-brain

Split-brain xảy ra khi hai region cùng tin mình là primary. Hệ quả có thể là divergence, unique key conflict, giao dịch không thể merge và mất dữ liệu. Trong hệ thống không có quorum để xác định leader, cần chọn availability hay consistency theo domain; không tự cho cả hai phía tiếp tục ghi critical data.

### 9.4. Quorum và witness

Một witness/consensus service có thể giúp xác định leader khi thiết kế quorum đúng. Nhưng witness phải ở failure domain độc lập và không biến thành một dependency duy nhất dễ mất. Cần tính majority, network partition, stale lease, clock assumptions và behavior khi quorum unavailable.

### 9.5. Fallback khi ownership registry lỗi

Không cho router tự suy owner từ region gần nhất. Với critical writes, fail closed hoặc dùng signed/leased ownership record còn hiệu lực theo policy. Read có thể dùng replica với freshness marker nếu nghiệp vụ cho phép.

## 10. Rebalance và chuyển ownership có kiểm soát

Ownership có thể thay đổi do tenant di chuyển, region mất cân bằng, thay đổi residency hoặc tối ưu latency. Rebalance không phải chỉ copy dữ liệu rồi đổi routing.

### 10.1. Quy trình migrate partition

1. Chọn partition và owner hiện tại; ghi baseline/version.
2. Tạo destination schema, index, key và capacity.
3. Copy snapshot ban đầu có checksum/count validation.
4. Stream change log/delta trong lúc source vẫn nhận write.
5. Đạt replication lag thấp và kiểm tra invariant.
6. Đặt partition vào trạng thái chuyển tiếp; dừng hoặc serialize write mới.
7. Fence source và chốt final log position.
8. Apply delta cuối, verify destination và tăng ownership epoch.
9. Cập nhật registry/router; chỉ destination nhận write.
10. Duy trì source ở read-only/rollback window theo policy rồi cleanup.

### 10.2. Cutover có thời gian freeze

Với hệ thống không có dual-write an toàn, có thể cần ngừng ghi ngắn trong cutover. Thông báo rõ degraded mode, queue command tạm thời hoặc trả retryable response. Không để hai database cùng nhận write trong cửa sổ migration chỉ để giảm downtime nếu chưa có conflict protocol.

### 10.3. Dual-write và CDC

Dual-write từ ứng dụng tới cả source và destination có thể tạo partial success: một nơi commit, nơi kia timeout. Nếu phải dual-write, cần outbox/CDC, idempotency, reconciliation và state machine; không xem hai lời gọi độc lập là distributed transaction.

### 10.4. Rollback migration

Sau khi destination đã nhận write, quay về source cần reverse replication hoặc một quy trình data reconciliation. Chỉ đổi router về source sẽ làm mất các write mới ở destination. Xác định rollback window và điều kiện kết thúc trước khi bắt đầu migration.

## 11. Ownership registry và governance

Ownership registry là control plane ghi nhận region/partition nào có quyền ghi. Nó cần độ tin cậy, quyền truy cập, versioning và audit phù hợp vì lỗi registry có thể làm sai toàn bộ write routing.

### 11.1. Metadata tối thiểu

| Field | Mục đích |
| --- | --- |
| entity/partition key | Xác định phạm vi ownership |
| owner region | Region có write authority |
| epoch/generation | Chống stale writer và mapping cũ |
| state | Active, migrating, fenced, recovering hoặc disabled |
| replica locations | Nơi có bản sao và vai trò read/standby |
| consistency policy | Read/write guarantee áp dụng |
| residency tag | Boundary được phép lưu/xử lý |
| version/update time | Phát hiện stale mapping |
| approval/change reference | Truy vết người và lý do thay đổi |

### 11.2. State transition

Không chuyển ownership trực tiếp từ A sang B bằng một field update không có protocol. Các trạng thái có thể gồm:

~~~mermaid
stateDiagram-v2
    [*] --> ActiveA
    ActiveA --> PreparingB: Prepare destination
    PreparingB --> CatchingUp: Initial copy complete
    CatchingUp --> FreezingA: Cutover window
    FreezingA --> FencedA: Old writer fenced
    FencedA --> PromotingB: Final delta verified
    PromotingB --> ActiveB: New epoch committed
    ActiveB --> PreparingA: Reverse migration
    PreparingA --> ActiveA: Failback complete
~~~

Mỗi transition cần precondition, timeout, operator/automation identity, evidence và cách xử lý khi trạng thái không rõ. Nếu workflow bị restart, cần đọc state đã commit để tiếp tục an toàn.

### 11.3. Ai được đổi ownership?

- Business/data owner xác nhận entity có thể chuyển region mà không vi phạm business rule.
- Platform/data operations thực hiện migration và cutover.
- Security/privacy xác nhận residency, key, identity và access boundary.
- Incident commander/DR lead có quyền kích hoạt failover theo runbook.
- Auditor có thể đọc change history nhưng không mặc nhiên có quyền sửa registry.

Tách quyền đề xuất, phê duyệt và thực thi giúp giảm nguy cơ một thao tác sai chuyển toàn bộ tenant sang region không được phép.

### 11.4. Audit và reconciliation

Ghi lại ai thay đổi owner, epoch trước/sau, partition scope, approval, replication position, fencing evidence và verification result. Định kỳ đối chiếu registry với database leader, route configuration và replication topology để phát hiện drift.

## 12. Security và data residency trong ownership model

Ownership không chỉ là tối ưu latency. Nó còn xác định nơi dữ liệu được xử lý, ai có thể đọc/ghi và nơi bản sao được giữ.

### 12.1. Residency-aware placement

Nếu entity thuộc jurisdiction hạn chế, home region và mọi replica/backup phải tuân theo policy đã được xác nhận. Ownership registry cần chứa residency constraint hoặc tham chiếu tới policy có thẩm quyền; failover không được tự động chọn region ngoài allowlist.

Nếu không có region dự phòng hợp lệ trong boundary, cần phương án đã được phê duyệt như multi-AZ, backup restore tại region nội địa hoặc degraded mode. Không ưu tiên availability bằng cách âm thầm chuyển dữ liệu ra khỏi boundary.

### 12.2. Key và identity theo region

- Dùng workload identity theo account/region, không dùng credential dùng chung toàn cầu.
- Key policy giới hạn theo data class, jurisdiction và service identity.
- Replication role chỉ có quyền cần thiết trên dataset được phép.
- Fencing/ownership change phải cập nhật quyền writer theo cách audit được.
- Break-glass access có MFA, approval, expiry và session log.

### 12.3. Encrypt không đồng nghĩa được phép transfer

Encryption in transit/at rest giảm nguy cơ lộ dữ liệu nhưng không tự tạo quyền chuyển dữ liệu xuyên biên giới. Cần legal/privacy assessment và contract/transfer terms phù hợp với tình huống. Key đặt trong region gốc cũng không ngăn mọi hình thức remote access hoặc support disclosure.

### 12.4. Least privilege theo ownership

Service của region A chỉ nên ghi partition do A sở hữu; reader có quyền đọc replica theo scope; router có quyền tra registry; automation chuyển owner có quyền riêng và hạn chế thời gian. Không cấp quyền ghi toàn bộ database cho mọi regional service nếu domain có thể tách scope.

## 13. Observability cho quyền sở hữu và write path

Khi có lỗi ghi, người vận hành phải biết request đã được route tới đâu, owner/epoch nào được dùng, có bị reject vì stale mapping hay không và replication có theo kịp không.

### 13.1. Metrics cần có

- Write request rate theo owner region và partition class.
- Cross-region routing rate và routing latency.
- Stale owner rejection / fencing rejection.
- Conflict count và resolution outcome theo loại.
- Replication lag theo region/partition.
- Read replica freshness và read-your-writes fallback rate.
- Ownership registry latency, stale cache age và availability.
- Migration state, copied bytes, delta lag và cutover duration.
- Duplicate command/event, retry và reconciliation backlog.
- Split-brain/fencing alarm và writer identity observed.

Không gắn customer ID hoặc entity ID không giới hạn vào metric labels. Dùng partition group, region, service và conflict class; ID chi tiết để trong log/traces có quyền truy cập phù hợp.

### 13.2. Structured log/tracing

Write request nên có correlation ID, command ID, entity type, owner region, ownership epoch, selected route, expected version và outcome. Không log raw PII hoặc payload nhạy cảm chỉ để debug routing.

Trace span có thể ghi bước resolve owner, remote hop, fencing validation và database commit. Với async flow, propagate context qua event header và lưu event ID/version để nối producer với consumer.

### 13.3. Alert

Alert quan trọng gồm stale writer attempt, owner registry unavailable, replication lag vượt RPO/freshness SLO, conflict spike, migration stuck, ownership mismatch và cross-region route tăng bất thường. Alert cần runbook riêng, không chỉ “database CPU high”.

### 13.4. Business invariant monitoring

Một số lỗi chỉ phát hiện qua đối soát domain:

- Tổng reservation không vượt stock.
- Balance/ledger debit-credit khớp theo transaction semantics.
- Một idempotency key không tạo nhiều payment/order.
- Entity chỉ có một writer epoch active.
- Version không lùi và state transition hợp lệ.

Đặt reconciliation job và alert cho invariant quan trọng, vì kỹ thuật replication healthy không chứng minh nghiệp vụ đúng.

## 14. Availability, partition và degraded behavior

Network partition tạo lựa chọn khó: một region không biết owner ở nơi khác còn sống hay không. Nếu cả hai tiếp tục ghi critical entity, split-brain có thể xảy ra; nếu cả hai dừng, availability giảm.

### 14.1. Quy tắc theo domain

| Dữ liệu | Hành vi khi owner unreachable | Lý do |
| --- | --- | --- |
| Ledger/balance | Từ chối hoặc queue command để xử lý sau khi owner/quorum trở lại | Tránh double spend và mất ordering |
| Inventory có giới hạn | Chỉ dùng quota/escrow đã cấp; nếu hết thì reject/defer | Giữ invariant stock |
| User preference | Có thể ghi tạm local nếu merge policy rõ | Conflict thường có thể xử lý theo field/version |
| Catalog | Có thể cho phép local draft, publish qua owner | Tách draft khỏi authoritative state |
| Analytics projection | Có thể nhận event và lag, không nhận business write | Rebuild được từ source/event |

### 14.2. Queue commands khi owner mất

Command có thể được lưu vào durable queue với operation ID, timestamp và expected version, rồi gửi khi owner phục hồi. Queue phải có retention, ordering và expiry; các command đã hết hạn hoặc conflict cần trả trạng thái rõ cho caller. API phải phân biệt trạng thái accepted/pending với committed; không báo thành công cuối cùng khi mới chỉ nhận command vào queue.

### 14.3. Local write buffer

Local write buffer chỉ phù hợp với thao tác có thể xác nhận tạm thời và hòa giải an toàn. Phân biệt accepted với committed; UI/business process cần thể hiện trạng thái pending. Với payment capture, ledger hoặc inventory decrement quan trọng, buffer cục bộ không được giả làm commit.

### 14.4. CAP trong quyết định ownership

Trong network partition, hệ thống phân tán phải chọn trade-off giữa availability và consistency cho thao tác liên quan. Không nên dùng CAP như khẩu hiệu chung: xác định operation nào cần từ chối để giữ invariant và operation nào có thể tiếp tục local. Cùng một nền tảng có thể có policy khác nhau cho search, profile, balance và inventory.

## 15. Cost và hiệu năng của các mô hình ownership

| Yếu tố | Single-writer | Regional ownership | Multi-writer |
| --- | --- | --- | --- |
| Write latency | Có thể cao nếu writer xa | Thấp khi request tới đúng owner | Thấp cho local write |
| Coordination | Đơn giản hơn | Registry/routing và migration | Conflict resolution và replication phức tạp |
| Availability khi owner lỗi | Phụ thuộc failover | Phụ thuộc chuyển ownership theo partition | Có thể tiếp tục local nếu conflict policy cho phép |
| Data correctness | Dễ giữ invariant toàn cục hơn | Tốt khi partition boundary đúng | Phụ thuộc merge semantics |
| Operations | Ít moving parts hơn | Cần ownership lifecycle | Cần xử lý conflict/repair liên tục |
| Cost | Có thể tốn network/central capacity | Chi phí cell/replica/registry | Chi phí replication, compute và reconciliation |

### 15.1. Đánh giá write locality

Đo tỷ lệ write được xử lý tại home region so với phải route liên vùng, latency p50/p95/p99, registry lookup, retry và remote dependency. Nếu phần lớn request vẫn cross-region do entity ownership không trùng user locality, cần xem lại partitioning hoặc API/domain boundaries.

### 15.2. Rebalancing cost

Di chuyển partition tiêu tốn network, storage I/O, compute và có thể cần dual-run. Lập kế hoạch migration window, bandwidth cap và cutover duration; tránh di chuyển hàng loạt trong giờ peak. Đừng tối ưu phân bố shard quá thường xuyên nếu lợi ích latency/cost thấp hơn rủi ro ownership transfer.

### 15.3. Cost of conflict

Multi-writer có thể giảm write latency nhưng tăng conflict queue, duplicate processing, support và reconciliation. Đo conflict rate, manual resolution effort, data repair và business compensation cost; đưa những khoản này vào TCO.

## 16. Kiểm thử và diễn tập ownership

Không thể chỉ kiểm thử việc đọc mapping registry. Cần chứng minh write authority, fencing và recovery đúng dưới concurrency, network partition và thao tác operator.

### 16.1. Functional tests

- Hai request đồng thời cập nhật cùng entity phải được serialize/reject/merge đúng semantics.
- Stale epoch bị từ chối ở data plane.
- Retry sau timeout không tạo duplicate side effect.
- Read-your-writes token route tới version phù hợp.
- Out-of-order event không làm projection lùi version.
- Conflict resolver giữ các domain invariant.
- Registry cache invalidation không mở cửa cho stale writer.

### 16.2. Failure injection

1. Cắt kết nối giữa router và ownership registry.
2. Tạo network partition giữa hai region đang giữ replica.
3. Giả lập primary chậm nhưng vẫn có thể nhận write.
4. Kill writer ngay sau commit nhưng trước response.
5. Làm replica lag vượt RPO.
6. Gửi command cũ với epoch trước khi failover.
7. Restart ownership orchestrator giữa bước cutover.
8. Làm conflict queue tăng hoặc resolver lỗi.

### 16.3. Game day và exit criteria

Cuộc diễn tập đạt khi chỉ có một writer hợp lệ cho mỗi partition, không vi phạm business invariant, RPO/RTO nằm trong mục tiêu hoặc exception được phê duyệt, routing và read semantics đúng, audit đủ và operator có thể giải thích trạng thái. Mỗi lỗi cần owner, deadline và retest.

## 17. Well-Architected: phân bố quyền ghi theo khu vực

| Góc nhìn | Quyết định kiến trúc | Đánh đổi |
| --- | --- | --- |
| **Operational Excellence / Vận hành** | Ownership registry, epoch, audit, migration workflow và game day | Tự động hóa giúp nhất quán nhưng control plane cần vận hành tin cậy |
| **Security / Bảo mật** | Scoped writer identity, fencing, key boundary và residency guardrail | Phân quyền chặt tăng công sức provisioning và incident handling |
| **Reliability / Độ tin cậy** | Replica, quorum/failover, regional cells và degraded mode | RTO thấp hơn cần capacity/replication và quy trình phức tạp hơn |
| **Performance Efficiency / Hiệu quả hiệu năng** | Local writes, read replicas và partitioning theo domain | Write locality tốt nhưng giao dịch liên vùng cần orchestration |
| **Cost Optimization / Tối ưu chi phí** | Right-size replicas, registry, transfer và reconciliation | Multi-region tăng phí network, storage và vận hành |
| **Sustainability / Bền vững** | Giảm copy không cần, right-size replica và rebalance theo số liệu | Ít replica giảm footprint nhưng không được phá resilience |

## 18. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Coi replica là writer dự phòng tự động | Có thể tạo hai writer hoặc promote dữ liệu stale | Fencing, epoch và promotion protocol |
| Chọn region gần nhất làm owner | Ownership thay đổi theo latency, tạo routing không ổn định | Registry authoritative theo entity/partition |
| Multi-writer cho mọi bảng | Conflict và invariant violation khó kiểm soát | Chọn ownership theo aggregate/domain |
| Last-write-wins cho dữ liệu tài chính | Mất update hoặc sai số dư | Single authority và domain transaction |
| Chỉ fence ở router | Client cũ vẫn có thể ghi qua connection cũ | Enforce fencing ở data plane |
| TTL registry quá dài | Stale owner routing kéo dài | Epoch validation và invalidation |
| Không idempotent command | Retry tạo duplicate payment/order | Operation ID và deduplication |
| Rebalance bằng copy rồi đổi DNS | Mất write mới hoặc split-brain | Catch-up, freeze, fence, final sync, epoch cutover |
| Đọc local replica không freshness marker | User thấy state cũ mà tưởng là authoritative | Read consistency policy và version token |
| Replicate dữ liệu ra ngoài residency boundary | Vi phạm governance | Residency-aware placement và allowlist |
| Queue command rồi trả committed | Client hiểu sai trạng thái giao dịch | Phân biệt accepted/pending/committed |
| Không test partition và failover | Không phát hiện stale writer ở production | Failure injection và game day |

## 19. Bài thực hành: phân bố ownership cho nền tảng thương mại điện tử

Một nền tảng có người dùng tại ba khu vực. Customer profile, order, inventory, payment ledger, catalog và recommendation được triển khai ở ba region. Người dùng cần profile/catalog phản hồi nhanh; checkout phải tránh bán vượt tồn kho và ghi nhận thanh toán chính xác. Một số profile thuộc jurisdiction cần giới hạn nơi lưu dữ liệu. Hai region có thể mất kết nối trong một khoảng thời gian.

**Yêu cầu bài làm:**

1. Phân loại aggregate và business invariant của customer, order, inventory, payment ledger, catalog và recommendation.
2. Chọn single-writer, regional ownership hay multi-writer cho từng aggregate; giải thích lý do.
3. Đề xuất partition key và home-region assignment, bao gồm tenant/customer/warehouse.
4. Thiết kế ownership registry với epoch, state transition, cache TTL và audit.
5. Vẽ write/read routing cho checkout và profile; nêu read-your-writes/bounded staleness.
6. Xác định command/event ownership, outbox, event version và idempotency.
7. Đề xuất conflict resolution cho profile và inventory; giải thích vì sao ledger không dùng last-write-wins.
8. Viết failover protocol cho một partition khi owner region mất; chứng minh fencing ngăn stale writer.
9. Thiết kế degraded behavior trong network partition cho payment, inventory, catalog và recommendation.
10. Lập quy trình migrate một tenant sang region khác mà không mất write.
11. Chỉ ra replica/backup/key nào được phép theo residency constraint.
12. Xây dashboard, alert, game day và cost model cho write locality/conflict/reconciliation.

### Gợi ý đánh giá

Một thiết kế tốt thường giữ payment ledger và thao tác trừ tồn kho ở một authority rõ ràng hoặc dùng protocol reservation/quota đã chứng minh invariant. Profile có thể dùng regional ownership theo customer và merge có điều kiện cho field độc lập. Catalog có thể có global publisher với regional read model; recommendation là projection có thể rebuild.

Bài làm cần phân biệt region chứa replica với region có quyền ghi; mô tả epoch/fencing ở data plane; xác định hành vi khi owner không truy cập được thay vì tự chuyển sang region gần nhất. Migration phải có snapshot, delta catch-up, freeze, fence, final sync và owner epoch mới.

## 20. Checklist trước khi đưa ownership đa khu vực vào production

- [ ] Mỗi aggregate/dataset có data owner, business invariant và write authority rõ.
- [ ] Phân biệt data location, residency, owner, writer và read routing.
- [ ] Partition key phản ánh domain, locality, traffic distribution và recovery.
- [ ] Ownership registry có owner, epoch, state, replica, residency và audit.
- [ ] Router không phải enforcement point duy nhất; data plane kiểm tra authority/fencing.
- [ ] Có consistency/read policy cho strong, read-your-writes, bounded staleness hoặc eventual.
- [ ] Multi-writer chỉ dùng khi conflict semantics và invariant được định nghĩa/test.
- [ ] Conflict resolver không mặc định last-write-wins cho dữ liệu critical.
- [ ] Command/event có ID, version, ordering và idempotency.
- [ ] Read model local có freshness marker và lag monitoring.
- [ ] Failover fence writer cũ, chọn recovery point, tăng epoch và promote có kiểm soát.
- [ ] Network partition có degraded behavior theo từng domain.
- [ ] Rebalance có snapshot, delta catch-up, freeze, final sync và rollback plan.
- [ ] Residency/key/backup/replica destination được enforce theo policy.
- [ ] Observability có write locality, stale owner, conflict, replication lag và invariant metrics.
- [ ] Ownership changes có approval, audit, reconciliation và separation of duties.
- [ ] Có test concurrency, retry, stale epoch, split-brain, registry outage và failover.
- [ ] DR/game day chứng minh RTO/RPO và chỉ một writer hợp lệ.
- [ ] Cost gồm replication, network, registry, conflict repair và human operations.
- [ ] Có runbook, owner và review định kỳ khi topology/business rules thay đổi.

**Ghi nhớ:** Quyền ghi phải gắn với entity hoặc aggregate và được thực thi ở data plane. Single-writer giảm conflict nhưng có thể tăng latency; regional ownership cải thiện locality khi partition boundary đúng; multi-writer chỉ phù hợp khi domain có quy tắc merge và vẫn giữ invariant. Hãy dùng registry/epoch, routing có kiểm tra, idempotency và fencing để quản lý vòng đời ownership; kiểm thử failover, partition và migration trước production.
