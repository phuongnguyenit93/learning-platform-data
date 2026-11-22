# Strangler Fig và chuyển dần lưu lượng sang phần mới

## 1. Mục tiêu

Một hệ thống lâu năm thường chứa nghiệp vụ quan trọng, dữ liệu tích lũy nhiều năm, các tích hợp khó thay thế và quy trình vận hành đã quen thuộc. Khi muốn hiện đại hóa, việc viết lại toàn bộ hệ thống rồi chuyển traffic trong một lần có rủi ro rất lớn: phạm vi thay đổi rộng, khó kiểm thử mọi trường hợp, dữ liệu có thể không đồng bộ, rollback phức tạp và tổ chức phải duy trì hai hệ thống gần như hoàn chỉnh trong thời gian dài.

**Strangler Fig Pattern** là chiến lược chuyển đổi kiến trúc theo từng phần. Một lớp điều phối hoặc routing đứng trước hệ thống hiện tại, rồi từng năng lực nghiệp vụ được chuyển dần sang implementation mới. Phần cũ tiếp tục phục vụ những luồng chưa chuyển; phần mới tiếp nhận các luồng đã đủ điều kiện. Khi một năng lực đã được thay thế, đường đi cũ của năng lực đó được thu hẹp rồi loại bỏ.

Tên gọi lấy cảm hứng từ cây strangler fig: cây mới phát triển bao quanh cây chủ, dần thay thế vai trò của nó. Trong kiến trúc phần mềm, ý tưởng là **thay thế có kiểm soát qua nhiều bước nhỏ, mỗi bước có thể quan sát và khôi phục**, thay vì đặt toàn bộ hệ thống vào một lần chuyển đổi lớn.

Bài học thuộc nhóm Chuyển đổi kiến trúc, tập trung vào Strangler Fig và việc chuyển dần lưu lượng sang phần mới. Sau khi học, người đọc có thể:

- Nhận diện khi nào Strangler Fig phù hợp và khi nào nên chọn modular monolith, replatform hoặc thay thế theo cách khác.
- Xác định seam, bounded context và năng lực nghiệp vụ có thể tách khỏi legacy.
- Thiết kế facade/routing layer để đưa từng request tới hệ thống cũ hoặc mới.
- Phân biệt chuyển traffic theo route, tenant, cohort, feature flag, percentage và shadow traffic.
- Kiểm soát dữ liệu, transaction, event, cache và consistency khi hai implementation cùng tồn tại.
- Thiết kế rollout, canary, rollback, reconciliation và các tiêu chí chuyển giai đoạn.
- Theo dõi cả technical metrics và business correctness để biết phần mới đã đủ an toàn.
- Quản lý phụ thuộc legacy, tránh tạo thêm một lớp kiến trúc tồn tại vĩnh viễn.
- Lập kế hoạch loại bỏ code, hạ tầng, dữ liệu và chi phí của phần cũ sau cutover.

## 2. Vì sao không viết lại toàn bộ rồi chuyển một lần?

Một big-bang rewrite thường gặp các vấn đề:

- Không thể liệt kê đầy đủ mọi hành vi legacy, đặc biệt các edge cases chỉ xuất hiện trong production.
- Hệ thống mới được phát triển trong thời gian dài nhưng không nhận được feedback từ traffic thật.
- Trong lúc viết lại, legacy vẫn tiếp tục thay đổi nghiệp vụ và dữ liệu, khiến khoảng cách giữa hai hệ thống tăng.
- Cả hai implementation phải được duy trì, nhưng chỉ một bên đang nhận traffic.
- Khi cutover, lỗi có thể ảnh hưởng nhiều domain cùng lúc.
- Rollback không đơn giản nếu schema, event hoặc dữ liệu đã thay đổi theo cách không tương thích.
- Khó xác định phần nào của rewrite tạo ra regression.
- Team có thể trì hoãn cutover vì không thể chứng minh parity cho toàn bộ hệ thống.

Strangler Fig giảm kích thước của mỗi lần thay đổi. Ví dụ một ứng dụng thương mại điện tử có thể chuyển dần:

~~~text
Bước 0: Toàn bộ request -> Legacy application

Bước 1: Product catalog -> New Catalog Service
        Orders, payments, inventory -> Legacy

Bước 2: Inventory -> New Inventory Service
        Orders, payments -> Legacy

Bước 3: Order query/read model -> New Order Query Service
        Order commands, payments -> Legacy

Bước 4: Payment orchestration -> New Payment Service
        Legacy chỉ còn một số năng lực chưa chuyển

Bước 5: Loại bỏ các module legacy đã hết trách nhiệm
~~~

Các bước này chỉ là ví dụ. Thứ tự phải dựa trên coupling, rủi ro, khả năng tách dữ liệu, giá trị kinh doanh và năng lực vận hành. Không phải cứ module ít code nhất là nên chuyển trước.

**Mỗi lát cắt phải tạo ra một trạng thái hoạt động có thể kiểm chứng**, không phải một nửa tính năng chưa thể phục vụ người dùng.

## 3. Các thành phần cốt lõi của Strangler Fig

Một kiến trúc phổ biến có:

1. **Legacy system:** hệ thống hiện tại tiếp tục phục vụ các năng lực chưa chuyển.
2. **Strangler facade / routing layer:** điểm vào ổn định, quyết định request đi legacy hay implementation mới.
3. **New services/modules:** phần năng lực được xây lại theo ranh giới phù hợp.
4. **Data migration/replication path:** đồng bộ, chuyển đổi hoặc sở hữu dữ liệu giữa các hệ thống.
5. **Observability:** metrics, traces, logs, business SLI và rollout markers.
6. **Feature flags / routing policy:** điều khiển phạm vi traffic được chuyển.
7. **Rollback/mitigation path:** cách quay lại đường cũ hoặc giảm tác động khi phần mới gặp lỗi.
8. **Decommission plan:** kế hoạch thu hồi code, DB, queue, credentials, jobs và hạ tầng legacy.

Sơ đồ khái niệm:

~~~text
                  Clients
                     |
                     v
            +-------------------+
            | Gateway / Facade  |
            | Routing decisions |
            +---------+---------+
                      |
             +--------+--------+
             |                 |
             v                 v
       Legacy System       New Service
       old capability      migrated capability
             |                 |
             +--------+--------+
                      |
             Data / Event / Integration
                      |
                      v
             Observability & Control
~~~

Không phải mọi request cần đi qua một gateway mới. Nếu hệ thống đã có API Gateway, reverse proxy, BFF hoặc modular monolith boundary phù hợp, có thể bổ sung routing ở đó. Thêm một proxy riêng chỉ đáng làm khi nó tạo được ranh giới kiểm soát thực sự.

## 4. Chọn đúng seam để tách

**Seam** là ranh giới nơi có thể thay đổi implementation mà không phải thay toàn bộ caller. Một seam tốt thường có:

- Hợp đồng input/output rõ.
- Trách nhiệm nghiệp vụ tương đối tập trung.
- Ít phụ thuộc trực tiếp vào internal state của module khác.
- Có thể định nghĩa ownership của dữ liệu.
- Có khả năng đo thành công/thất bại.
- Có thể chuyển traffic theo phạm vi nhỏ.
- Có thể rollback hoặc xử lý dữ liệu đã ghi.
- Có giá trị đủ lớn để biện minh chi phí vận hành.

Ví dụ:

- Catalog read API có thể tách tương đối dễ nếu data ownership và search contract đã rõ.
- Payment authorization có side effects tài chính, idempotency và reconciliation phức tạp; thường cần thiết kế cẩn thận hơn.
- Một màn hình dashboard lấy dữ liệu từ 12 bảng của nhiều module không phải seam tốt nếu nó truy cập trực tiếp database nội bộ của tất cả module.
- Một lớp tính giá dùng chung bởi nhiều use cases có thể cần được trích thành domain capability trước khi chuyển service.

### 4.1. Không chọn seam chỉ dựa trên folder hoặc table

Legacy code thường phân lớp theo kỹ thuật: controller, service, DAO, utils. Chuyển cả folder DAO sang service mới không tự tạo bounded context. Cần tìm **năng lực nghiệp vụ và quyền sở hữu**: ai quyết định trạng thái, ai bảo vệ invariant, ai được phép ghi dữ liệu.

### 4.2. Bounded context và modular monolith

Strangler Fig có thể dẫn tới microservices, nhưng không bắt buộc. Phần mới có thể là module độc lập trong cùng deployment hoặc một service riêng.

Nếu một capability cần transaction chặt với phần legacy và chưa có cách tách dữ liệu an toàn, có thể trước tiên tạo module boundary trong cùng codebase. Modular monolith là bước chuyển tiếp hợp lý trong nhiều trường hợp.

### 4.3. Đánh giá độ sẵn sàng của seam

Một bảng quyết định:

| Tiêu chí | Câu hỏi |
|---|---|
| Domain cohesion | Nghiệp vụ có một trách nhiệm rõ? |
| Data ownership | Ai là nguồn sự thật và ai được ghi? |
| Contract | API/event có thể định nghĩa và version? |
| Dependency | Có gọi trực tiếp internal tables hoặc code của module khác? |
| Transaction | Có invariant cần transaction xuyên ranh giới? |
| Traffic control | Có thể định tuyến một nhóm request? |
| Observability | Có thể đo riêng phần mới và phần cũ? |
| Rollback | Có thể đưa traffic về cũ mà không làm sai dữ liệu? |
| Operational readiness | Team có thể trực và xử lý service mới? |
| Business value | Tách ra giải quyết vấn đề cụ thể nào? |

Nếu nhiều câu hỏi chưa có lời giải, hãy làm rõ boundary trước khi viết service mới.

## 5. Vai trò của facade và routing layer

Facade là điểm điều phối giúp client không cần biết implementation nào đang xử lý một capability. Nó có thể nằm tại:

- API Gateway/reverse proxy.
- Backend for Frontend.
- Một application facade trong legacy.
- Service mesh/ingress routing.
- Một adapter chuyên biệt cho capability.

Nhiệm vụ thường gặp:

- Nhận diện route/capability.
- Xác định tenant, cohort hoặc feature flag.
- Chọn legacy hay new implementation.
- Giữ contract bên ngoài ổn định.
- Gắn version/route decision vào logs và traces.
- Áp dụng timeout, rate limit và retry policy phù hợp.
- Có cơ chế kill switch hoặc chuyển traffic về đường cũ.
- Không vô tình gửi cùng một side-effecting request đến cả hai bên.

### 5.1. Giữ contract bên ngoài ổn định

Ví dụ client vẫn gọi:

~~~http
GET /api/catalog/items/sku-123
~~~

Trong giai đoạn chuyển đổi:

~~~text
Request
   |
   v
Facade
   |
   +-- flag OFF / chưa migrate ---> Legacy Catalog Module
   |
   +-- flag ON / cohort đủ điều kiện -> New Catalog Service
~~~

Client không cần thay đổi URL chỉ vì backend được chuyển. Điều này giảm số nhóm phải phối hợp và cho phép chuyển implementation độc lập.

### 5.2. Facade không nên chứa toàn bộ domain logic

Facade nên quyết định routing, kiểm tra những điều kiện cross-cutting phù hợp và giữ contract. Nếu nó bắt đầu tính giá, cập nhật order state, quản lý inventory và chứa mọi quy tắc legacy, facade trở thành một monolith mới.

Business invariants nên nằm trong service/module sở hữu nghiệp vụ. Facade không được biến thành một lớp bypass mọi ranh giới dữ liệu.

## 6. Các chiến lược routing

### 6.1. Routing theo route hoặc endpoint

Chuyển toàn bộ một nhóm API sang implementation mới:

~~~text
GET /catalog/**       -> New Catalog
POST /orders/**       -> Legacy Orders
GET /reports/**       -> Legacy Reports
~~~

Ưu điểm: dễ hiểu, dễ quan sát, ít phải tính toán cohort. Hạn chế: route có thể không tương ứng một capability hoàn chỉnh; API read và command có thể đi khác nơi nếu không thiết kế cẩn thận.

### 6.2. Routing theo tenant/customer cohort

Một tập tenant được chuyển sang phần mới:

~~~text
tenant A, B, C -> New
tenant D, E    -> Legacy
~~~

Phù hợp khi cần giới hạn blast radius và đo theo nhóm khách hàng. Cần bảo đảm tất cả request trong một business workflow được định tuyến nhất quán. Nếu một order command vào legacy nhưng order read ngay sau đó vào new projection chưa đồng bộ, người dùng có thể thấy trạng thái cũ.

### 6.3. Routing theo feature flag

Flag có thể bật capability mới cho một nhóm:

~~~text
catalog.new-read-path = true for internal users
catalog.new-read-path = false for everyone else
~~~

Cần quản lý flag lifecycle: owner, purpose, default, allowed values, audit, expiry và rollback. Flag migration không nên tồn tại vĩnh viễn sau khi cutover hoàn tất.

### 6.4. Percentage-based routing

Traffic được chia theo tỷ lệ:

~~~text
0% new   -> 100% legacy
1% new   -> 99% legacy
5% new   -> 95% legacy
25% new  -> 75% legacy
50% new  -> 50% legacy
100% new -> 0% legacy
~~~

Phù hợp để đánh giá capacity và behavior dưới tải thật, nhưng **percentage không tự bảo đảm sample đại diện**. Traffic thấp, tenant skew, route mix khác nhau hoặc một vài khách hàng lớn có thể làm kết quả sai lệch.

### 6.5. Routing theo version/capability

Có thể route theo API version, client capability hoặc loại operation. Cần giữ backward compatibility và tránh làm client phải biết quá nhiều chi tiết migration nội bộ.

### 6.6. Deterministic routing

Với tenant/customer, dùng hash ổn định theo key để một tenant nhất quán đi một backend trong giai đoạn rollout:

~~~text
bucket = hash(tenant_id) mod 100

if bucket < new_traffic_percent:
    route to new
else:
    route to legacy
~~~

Không dùng random routing riêng cho từng request nếu workflow yêu cầu consistency. Hash key cần ổn định, có salt/version policy rõ, và không đưa raw PII vào log/metrics.

## 7. Percentage rollout và canary không hoàn toàn giống nhau

Canary thường là kỹ thuật phát hành phiên bản mới với một lượng traffic nhỏ để quan sát lỗi, latency, capacity và correctness. Strangler Fig là chiến lược chuyển dần **trách nhiệm của một capability từ hệ thống cũ sang hệ thống mới**.

Có thể dùng canary để thực hiện từng bước Strangler Fig, nhưng hai khái niệm không đồng nghĩa:

- Canary một phiên bản của cùng service không nhất thiết thay đổi ownership kiến trúc.
- Strangler có thể chuyển từng route/tenant/command/query qua nhiều release.
- Strangler cần kế hoạch data ownership và loại bỏ legacy, không chỉ quan sát một đợt deploy.

Một migration có thể có canary release cho New Catalog, sau đó giữ new path làm implementation chính và tiếp tục strangling capability kế tiếp.

## 8. Shadow traffic: quan sát mà không nhân đôi side effects

Shadow traffic (dark launch) gửi bản sao request tới implementation mới để so sánh kết quả nhưng **chỉ một implementation được phép tạo side effect chính thức**.

~~~text
Client Request
      |
      v
  Facade / Proxy
      |
      +----> Legacy (authoritative response) ---> Client
      |
      +----> New (shadow, no external side effects)
                         |
                         v
                  Compare / Observe
~~~

Shadow hữu ích để:

- Đánh giá latency và resource usage.
- So response shape và dữ liệu trả về.
- Phát hiện business rules bị bỏ sót.
- Kiểm tra behavior trên traffic distribution thật.
- Tìm các edge cases mà test fixture chưa có.

### 8.1. Những điều cần bảo vệ

Không được nhân đôi payment, email, order creation, inventory reservation, webhook hoặc bất kỳ side effect nào chỉ vì shadow request được gửi tới new service.

Các biện pháp:

- Chế độ read-only hoặc sandbox mode.
- Adapter giả lập external side effects.
- Bỏ qua commit/write path một cách có kiểm soát.
- Dùng dữ liệu đã mask/anonymize khi cần.
- Hạn chế payload và rate.
- Gắn shadow marker để trace/log tách biệt.
- Không để shadow traffic ảnh hưởng metrics user-facing hoặc tính billing.
- Không cho phép shadow response trở thành response chính khi chưa bật route chính thức.

Nếu new implementation phải ghi DB để đánh giá transaction behavior, dùng một môi trường shadow riêng với dữ liệu phù hợp; không tự tạo side effect trong production.

### 8.2. So sánh response

Response comparison cần normalize các field không ổn định như timestamp, generated IDs, ordering không được đảm bảo hoặc metadata nội bộ. So sánh semantics của kết quả, không chỉ byte-for-byte JSON.

Ví dụ:

~~~text
Legacy:
  price = 100000
  available = true
  displayName = "Book A"

New:
  price = 100000
  available = true
  displayName = "Book A"

Normalized comparison: MATCH
~~~

Khi mismatch, phân loại:

- Lỗi logic ở new.
- Lỗi/behavior cũ đã được xác định cần sửa.
- Dữ liệu không đồng bộ.
- Khác biệt hợp lệ do contract mới.
- Non-deterministic field.
- Lỗi trong normalization/comparison.

Không tự động coi legacy là đúng tuyệt đối; có thể chính migration là cơ hội sửa lỗi nghiệp vụ đã tồn tại, nhưng phải có quyết định domain owner và contract rõ.

## 9. Data ownership là vấn đề khó nhất

Khi legacy và new cùng hoạt động, câu hỏi quan trọng nhất thường không phải routing HTTP mà là **ai có quyền ghi trạng thái thật**.

Ví dụ Order Service mới được xây nhưng legacy vẫn có thể sửa orders table. Nếu cả hai cùng ghi trực tiếp cùng một bảng, các vấn đề có thể xuất hiện:

- Quy tắc validation khác nhau.
- Transaction boundaries khác nhau.
- Một hệ thống không biết version/state do hệ thống kia tạo.
- Lost update hoặc ghi đè trạng thái mới.
- Audit trail không đầy đủ.
- Một bug ở new làm legacy không thể phục hồi dữ liệu.

Cần xác định từng entity/capability:

| Dữ liệu | Owner trong giai đoạn hiện tại | Hướng đích |
|---|---|---|
| Catalog product state | Legacy Catalog | New Catalog |
| Order lifecycle | Legacy Orders | New Order Service |
| Payment state | Payment module cũ | New Payment Service |
| Inventory reservation | Legacy Inventory | New Inventory |
| Analytics projection | Analytics platform | Read-only derived data |

Trong migration, owner có thể thay đổi theo từng bước nhưng phải có **một nguồn sự thật có quyền quyết định** cho mỗi state transition. Hai bên cùng giữ một bản authoritative cho cùng một field thường là dấu hiệu boundary chưa rõ.

## 10. Các mô hình chuyển dữ liệu

### 10.1. Legacy là owner, new đọc projection

Legacy tiếp tục ghi nguồn dữ liệu. CDC/event/ETL đưa bản sao sang new service để phục vụ read hoặc shadow.

~~~text
Legacy DB (source of truth)
       |
       +---- CDC/event ----> New read model
       |
       +-------------------> Legacy writes
~~~

Ưu điểm: rủi ro thấp khi bắt đầu, không thay command path. Hạn chế: new vẫn phụ thuộc freshness và schema/contract từ legacy; không thể tự sở hữu lifecycle.

Phù hợp với việc chuyển query trước, khi read model mới có thể được xây độc lập.

### 10.2. New là owner, legacy đọc projection

Sau cutover của một capability, new service nhận command và phát changes sang legacy nếu các phần cũ còn cần đọc:

~~~text
Client -> Facade -> New Service -> New DB (source of truth)
                                |
                                +---- events/CDC ----> Legacy projection
~~~

Legacy không được tiếp tục ghi authoritative state cho capability đã chuyển. Các module cũ phải gọi API/command của owner mới hoặc dùng projection read-only có freshness contract.

### 10.3. Dual-read

Cả hai hệ thống có thể được truy vấn để so sánh hoặc fallback. Nhưng cần định nghĩa rõ response nào được trả và khi nào. Nếu mỗi request đọc legacy rồi new một cách đồng bộ, latency và failure surface tăng; không biến dual-read thành mặc định lâu dài.

### 10.4. Dual-write

Cùng một nghiệp vụ ghi cả hai database trực tiếp là cách dễ gây lỗi nhất nếu không có transaction coordination. Có thể xảy ra một bên commit, bên kia fail; retry tạo duplicate; hai bên áp rule khác nhau.

Không dùng dual-write chỉ để "giữ dữ liệu giống nhau". Ưu tiên một authoritative write path rồi publish event/outbox/CDC sang read projection. Nếu có giai đoạn cần dual-write thật sự, phải có thiết kế consistency, idempotency, reconciliation, retry, ownership và rollback được kiểm chứng.

## 11. Transactional outbox và event propagation

Khi new service sở hữu command, nó có thể ghi state và outbox event trong cùng transaction:

~~~text
New Order Service transaction
   |
   +-- update orders
   +-- insert outbox event
   |
  COMMIT
   |
   v
CDC / Outbox Relay
   |
   v
Broker
   |
   +--> Legacy compatibility projection
   +--> Search/read model
   +--> Analytics
~~~

Outbox giúp tránh tình huống DB commit thành công nhưng publish event thất bại. Tuy nhiên relay có thể gửi trùng sau crash; consumer phải idempotent.

Event nên có:

- eventId ổn định.
- eventType và schemaVersion.
- aggregateId và aggregateVersion.
- occurredAt/source position có semantics rõ.
- trace/correlation context.
- payload tối thiểu cần thiết.
- data classification và retention rules.

Không đưa toàn bộ entity hoặc PII vào event chỉ để consumers khỏi gọi thêm API. Event contract là một phần public của domain boundary và cần quản trị compatibility.

### 11.1. Consumer idempotency

Consumer có thể lưu processed event IDs, upsert theo aggregate version hoặc dùng cơ chế sink transaction phù hợp. Không giả định broker exactly-once sẽ bao phủ external database và side effects.

### 11.2. Ordering

Nếu OrderCreated, OrderPaid và OrderCancelled có thứ tự quan trọng, partition theo aggregate ID hoặc dùng version sequence để phát hiện event đến sai thứ tự. Ordering toàn cục giữa nhiều partitions/services thường không có sẵn.

## 12. Migration theo read path trước, write path sau?

Một cách triển khai phổ biến là tách query/read path trước vì nó thường ít side effect hơn, nhưng không phải quy tắc tuyệt đối.

Ví dụ:

1. Xây New Catalog read model từ dữ liệu legacy.
2. Shadow GET requests, so kết quả và latency.
3. Chuyển một cohort GET sang new.
4. Theo dõi freshness, correctness, errors và fallback.
5. Khi read path ổn định, chuyển command/write path bằng một kế hoạch ownership riêng.
6. Cập nhật consumers và các luồng nghiệp vụ phụ thuộc.
7. Loại bỏ legacy code cho capability đó.

### 12.1. Tại sao read path có thể chưa đơn giản?

- Read model chưa đủ freshness cho màn hình cần trạng thái tức thời.
- Legacy API có implicit authorization hoặc tenant scoping.
- Một query cũ kết hợp nhiều module mà new service chưa sở hữu.
- Client dựa vào field/ordering undocumented.
- Cùng endpoint vừa đọc vừa sửa state.
- Read-after-write yêu cầu consistency mạnh.

Nếu query mới đọc projection trễ, phải quyết định behavior: chờ projection, trả trạng thái pending, đọc từ owner, hoặc dùng read-your-writes token. Không giấu eventual consistency bằng cách giả vờ dữ liệu mới là realtime.

### 12.2. Command path cần kế hoạch riêng

Command có side effects phải xác định:

- Thời điểm chuyển authoritative writer.
- Idempotency key và duplicate handling.
- In-flight requests/transactions khi đổi routing.
- State version và conflict resolution.
- Outbox/event propagation.
- Compensation nếu một bước workflow thất bại.
- Reconciliation cho dữ liệu đã ghi.
- Rollback khi new đã nhận command và thay đổi state.

## 13. Routing theo percentage: không chỉ chỉnh một con số

Ví dụ policy:

~~~text
Migration: catalog-read-v2
Owner: catalog-team
Default route: legacy
Cohort key: tenant_id
Allowed new percentage: 0, 1, 5, 10, 25, 50, 100
Min sample per stage: policy-specific
Guardrails:
  business success >= agreed threshold
  p95 latency within SLO
  error rate below threshold
  data freshness within contract
Rollback:
  route to legacy, preserve new data for investigation
~~~

Đây là cấu trúc policy minh họa. Từng ngưỡng phải dựa trên baseline, traffic volume, risk tier và business outcome.

### 13.1. Tại sao không tăng 1% -> 100% ngay?

Một phần traffic nhỏ có thể chưa chạm tới:

- Tenant có lượng dữ liệu lớn.
- Các request ít gặp như refund, cancellation, bulk import.
- Peak traffic và burst.
- Region có network/dependency khác.
- Các trạng thái cũ/historical edge cases.
- Một tỷ lệ hiếm của permissions và feature combinations.

Rollout phải có thời gian/sample đủ để kiểm tra các cohort có rủi ro, không chỉ đợi vài phút rồi tự động tăng.

### 13.2. Stable cohort và fairness

Nếu dùng tenant hash, một số tenant lớn có thể vô tình nằm trong 1% đầu tiên. Cần xem phân bố theo request volume, size, plan, region và business criticality. Có thể bắt đầu với internal tenants, test tenants hoặc nhóm có đặc điểm đại diện, sau đó mở rộng.

Không dùng PII trực tiếp làm routing key hoặc log value. Dùng identifier phù hợp với privacy policy và deterministic hash có quản lý.

## 14. Canary guardrails và điều kiện dừng

Mỗi stage cần tiêu chí **go / hold / rollback**.

| Tín hiệu | Ví dụ guardrail | Cách diễn giải |
|---|---|---|
| Request success | Không thấp hơn baseline quá mức đã thống nhất | Tách lỗi do client/dependency |
| Business success | Order/catalog action hoàn tất đúng | Không chỉ nhìn HTTP 2xx |
| Latency | p95/p99 nằm trong budget | So cùng traffic cohort |
| Dependency | DB/provider errors và saturation | Phát hiện overload downstream |
| Data correctness | Mismatch trong tolerance | Cần cutoff/semantics rõ |
| Freshness | Projection lag trong SLO | Quan trọng với read path |
| Capacity | CPU/memory/pool/queue có headroom | Tránh tăng traffic vào hệ thống thiếu capacity |
| Security | Authorization failures không tăng bất thường | Phát hiện routing bỏ qua policy |
| Cost | Chi phí/transaction không tăng bất hợp lý | Tránh chuyển traffic nhưng tạo overhead quá lớn |

Một policy nên có:

- Stage duration hoặc minimum sample count.
- Tín hiệu nào đủ tin cậy để đánh giá.
- Ngưỡng hold để điều tra thêm.
- Ngưỡng rollback tự động hoặc thủ công.
- Người được quyền quyết định.
- Hành động khi metrics mất dữ liệu.
- Runbook và kill switch.
- Quy trình sau khi rollback.

Không dùng một tỷ lệ lỗi cố định cho mọi service. Một payment correctness mismatch có thể cần dừng ngay dù chỉ một mẫu; một chênh lệch latency nhỏ trong internal read API có thể cần thêm mẫu để xác định.

## 15. Shadow comparison và data parity

Khi shadowing, response có thể khác vì:

- Legacy có bug đã tồn tại.
- New áp business rule mới.
- Data replication lag.
- Rounding, timezone hoặc currency conversion.
- Null/default semantics.
- Ordering không được bảo đảm.
- Permissions hoặc tenant scope khác.
- Timestamps/generated IDs khác nhau.
- Một bên trả cache cũ.

Cần xây **normalization và classification** thay vì đếm mọi khác biệt thành lỗi. Với dữ liệu tài chính, số tiền phải so theo currency, scale và business definition; không so float hoặc string display.

### 15.1. Parity test

Có thể kiểm tra theo các lớp:

1. Schema/contract parity: fields, status codes, pagination, error semantics.
2. Functional parity: kết quả use case với cùng input/state.
3. Data parity: các key/versions/aggregates tại cùng cutoff.
4. Authorization parity: cùng principal được phép/không được phép như nhau.
5. Operational parity: timeout, retry, idempotency, failure behavior.
6. Performance parity: latency/throughput/cost dưới cùng tải.

Không nhất thiết mọi behavior legacy phải được giữ nguyên. Khác biệt mong muốn cần được phê duyệt và ghi trong migration decision.

## 16. Rollback không đơn giản là route về legacy

Với read-only operation, quay routing về legacy có thể tương đối đơn giản nếu dữ liệu legacy vẫn còn đủ mới.

Với command đã chuyển sang new và đã ghi state, rollback phức tạp hơn:

~~~text
Traffic -> New Service
New DB commits command
Event -> Legacy projection delayed
New Service later fails
Operator routes traffic back to Legacy
Legacy may not yet contain latest state
~~~

Nếu legacy không biết những thay đổi đã commit ở new, route back có thể làm người dùng thấy trạng thái cũ hoặc ghi đè dữ liệu.

### 16.1. Phân loại rollback

- **Traffic rollback:** đưa request về implementation cũ.
- **Code rollback:** quay artifact/feature flag.
- **Data rollback:** hoàn tác hoặc bù trừ dữ liệu, không phải lúc nào cũng có thể.
- **Schema rollback:** thường cần expand/contract và compatibility.
- **Business compensation:** thực hiện nghiệp vụ bù, ví dụ refund/reversal theo contract.
- **Operational fallback:** chuyển sang degraded mode, queue command hoặc read-only.

Mỗi migration phải chỉ ra rollback nào khả thi, rollback nào không, và cần điều kiện gì.

### 16.2. Giữ legacy synchronized trong cửa sổ rollback

Nếu muốn route command về legacy sau khi new đã nhận traffic, có thể cần một projection/event stream từ new sang legacy. Nhưng projection có thể trễ và không nhất thiết đủ để legacy tiếp tục xử lý command an toàn.

Một số lựa chọn:

- Giữ legacy làm owner cho đến khi hoàn tất giai đoạn cutover.
- Chỉ chuyển read path trước.
- Giới hạn command scope của new cho một cohort có thể tách.
- Đồng bộ state và xác minh consistency trước khi cho phép rollback command.
- Khi không thể rollback, dùng forward-fix hoặc compensation với quy trình được thiết kế trước.

Không tuyên bố "có kill switch" là đã có rollback nếu dữ liệu mới không tương thích với phần cũ.

## 17. Database/schema migration trong giai đoạn coexistence

Legacy và new thường chạy nhiều version cùng lúc. Schema phải chịu được:

- Legacy v1 đang chạy.
- New v2 đang triển khai.
- Batch/CDC đang đọc.
- Background jobs chưa chuyển.
- Rollback quay về code cũ.

Chiến lược **expand-and-contract**:

1. Expand: thêm column/table/index nullable hoặc compatible.
2. Deploy code có thể đọc schema cũ và mới.
3. Dual-read hoặc backfill có kiểm soát nếu cần.
4. Chuyển traffic và data ownership.
5. Theo dõi không còn consumer phụ thuộc cấu trúc cũ.
6. Contract: loại cột/bảng/logic cũ trong release riêng.

Ví dụ:

~~~text
Release A: thêm new_status, vẫn duy trì old_status
Release B: legacy/new đọc được cả hai
Backfill: copy old_status -> new_status
Release C: new service dùng new_status làm owner
Observe: không còn consumer đọc old_status
Release D: xóa old_status sau khi hết rollback window
~~~

Không drop column ngay khi new code deploy thành công. Có thể còn report, batch, admin tool hoặc một phiên bản service cũ vẫn đang đọc.

### 17.1. Schema ownership

Khi một service mới sở hữu domain, nên dần chuyển quyền quản lý schema sang service đó. Các service khác không tự truy cập bảng private của owner mới; dùng API/event hoặc projection được công bố.

Trong giai đoạn chuyển tiếp, nếu cả legacy và new cùng ghi cùng bảng, phải có quy tắc write ownership rõ theo entity/partition/time window và test race conditions. Tránh hai bên cùng ghi một row theo kiểu "ai tới trước".

## 18. Data migration và backfill

Trước khi new service nhận traffic, dữ liệu cần đủ để xử lý request:

- Initial snapshot từ legacy.
- Backfill lịch sử cần thiết.
- Incremental changes trong lúc backfill.
- Mapping IDs và reference keys.
- Defaults/null semantics.
- Timezone/currency/enum conversion.
- Deletes, tombstones và corrections.
- Data quality checks và reconciliation.

### 18.1. Quy trình snapshot + CDC

~~~text
T0: xác định snapshot cutoff/log position
T1: bắt đầu copy lịch sử theo batch
T2: capture các thay đổi mới trong transaction log
T3: nạp snapshot vào new data store
T4: áp CDC theo position/version
T5: đối soát counts, totals và invariants
T6: xác nhận lag trong SLO
T7: cho phép shadow hoặc traffic stage đầu
~~~

Cần dùng semantics của CDC tool/database cụ thể. Không tự ghép snapshot và log stream chỉ theo timestamp nếu có nguy cơ bỏ sót hoặc áp event cũ sau mới.

### 18.2. Reconciliation

Kiểm tra:

- Row counts theo partition/status/time window.
- Unique business keys.
- Totals theo currency và trạng thái.
- Relationship order/payment/refund.
- State transitions hợp lệ.
- Sample records từ cả happy path và edge cases.
- Deleted/archived records.
- Event lag và duplicate count.
- Các dữ liệu có thể chênh hợp lệ do eventual consistency.

Chọn cùng cutoff/watermark và định nghĩa business metric. So tổng hiện tại của hai hệ thống khi CDC còn lag sẽ tạo mismatch giả.

### 18.3. Backfill an toàn

Backfill nên có:

- Job ID và source/target version.
- Phạm vi dữ liệu, batch size, checkpoint.
- Rate limit để bảo vệ OLTP và sink.
- Retry/idempotency.
- Error quarantine.
- Pause/resume.
- Progress và estimated completion.
- Data quality gates.
- Dataset staging/atomic swap nếu cần.
- Audit và quyền chạy.

Không chạy full-table scan không giới hạn trên primary chỉ vì migration cần nhanh. Nếu nguồn có read replica hoặc export snapshot được hỗ trợ, đánh giá tải và lag trước.

## 19. Cache và search index trong migration

Legacy có thể có cache key, invalidation rule và search index riêng. New service không thể mặc định dùng lại cache cũ nếu semantics khác.

Cần xem:

- Cache key namespace/version.
- TTL và stale data tolerance.
- Invalidation source/owner.
- Warm-up và cold-start behavior.
- Cache stampede.
- Search index mapping/analyzer.
- Eventual consistency của projection.
- Cutover và rollback của cache/index.
- Tenant/security boundaries.
- Xử lý dữ liệu bị xóa hoặc thay đổi quyền.

Một lỗi thường gặp là new service dùng cùng Redis key nhưng hiểu value theo schema mới, gây deserialize error hoặc trả dữ liệu sai. Dùng versioned key namespace khi cần và có kế hoạch dọn key cũ.

Với search, có thể xây index mới song song, chạy shadow queries và so relevance/filters, sau đó đổi alias/routing khi đủ điều kiện. Không ghi đè index cũ trước khi có cách rebuild/rollback.

## 20. Legacy strangler facade có thể trở thành bottleneck

Facade giúp điều phối nhưng nếu mọi request phải qua một service proxy trung tâm, nó có thể trở thành:

- Single point of failure.
- Bottleneck latency/throughput.
- Nơi chứa quá nhiều domain logic.
- Nơi giữ feature flags khó quản lý.
- Một lớp coupling mới mà mọi team phải chờ.
- Nơi làm sai auth/tenant routing.

Cần:

- Chạy nhiều replicas và có capacity phù hợp.
- Stateless routing policy hoặc state store có HA.
- Timeout/connection pooling hợp lý.
- Fail-safe default route đã được xác định.
- Metrics route decision và routing error.
- Versioned policy/config.
- Tránh lookup remote flag service cho mỗi request nếu nó tạo critical dependency; dùng cache/snapshot phù hợp.
- Không cho phép client tự chọn target backend qua header không tin cậy.
- Có kế hoạch giảm/loại facade khi migration hoàn tất.

Nếu Gateway hiện tại đã có routing/flag capability, dùng lại có thể giảm thêm một hop và operational component. Nhưng phải kiểm tra nó có hỗ trợ quyết định theo domain/tenant, audit và rollback cần thiết hay không.

## 21. Authentication, authorization và identity trong hai hệ thống

Khi traffic chuyển từ legacy sang new, security behavior phải giữ hoặc cải thiện:

- Cùng issuer/audience/scope contract phù hợp.
- Không tin header do client tự gán.
- Forward end-user identity theo cách có kiểm chứng.
- Service-to-service identity tách biệt user identity.
- Authorization theo resource/tenant tại owner.
- Audit trail và trace context.
- Secret rotation và certificate trust.
- CORS, CSRF và rate limiting nếu có frontend/browser.
- Error behavior không tiết lộ sự tồn tại của dữ liệu nhạy cảm.

Một gateway có thể authenticate token nhưng new service vẫn cần kiểm tra quyền trên resource. Shadow traffic phải tránh tạo side effects và không gửi payload nhạy cảm tới môi trường không được phép.

### 21.1. Parity về quyền truy cập

Trong shadow comparison, không chỉ so response của user được phép. Cần test cả:

- User không thuộc tenant.
- User chỉ có quyền read.
- User có quyền admin theo scope.
- Resource đã bị xóa hoặc chuyển owner.
- Token hết hạn/audience sai.
- Service identity thiếu quyền.

Một migration thành công không được biến 403 của legacy thành 200 của new.

## 22. Observability theo migration stage

Không đủ nếu dashboard chỉ hiển thị tổng latency của cả legacy và new. Cần phân tách:

- service/implementation version.
- route decision (legacy/new/shadow).
- rollout stage và cohort.
- region/zone.
- request type/business outcome.
- data freshness/version.
- dependency latency.
- error class/retry attempts.
- rollback/flag events.

Ví dụ metric dimensions có cardinality được kiểm soát:

~~~text
migration_requests_total{
  capability="catalog-read",
  target="new",
  stage="5",
  outcome="success"
}

migration_route_decisions_total{
  capability="catalog-read",
  target="legacy",
  reason="flag_off"
}
~~~

Không gắn tenant_id, user_id, order_id hoặc raw path động làm metric label. Những thông tin cần điều tra cụ thể có thể nằm trong logs/traces có access control phù hợp.

### 22.1. Dashboard theo từng stage

Một dashboard migration nên trả lời:

1. Bao nhiêu traffic đang vào legacy/new/shadow?
2. Có cohort nào bị lệch traffic ngoài dự kiến?
3. Success rate theo business outcome thế nào?
4. p95/p99 theo cùng route và cohort?
5. Có data parity mismatch, projection lag hoặc duplicate?
6. Dependency nào đang saturation?
7. Có authorization/error pattern khác legacy?
8. Rollback/kill switch đã được test chưa?
9. New service có đủ capacity nếu tăng stage tiếp theo?
10. Legacy traffic thực sự giảm hay có hidden consumers còn gọi trực tiếp?

### 22.2. Trace route decision

Một span/event có thể ghi:

~~~text
migration.capability = catalog-read
migration.target = new
migration.stage = 25
migration.reason = tenant-cohort
service.version = 2.0.0
~~~

Đây là thuộc tính minh họa. Tránh đưa giá trị tenant/user nhạy cảm vào span. Route decision giúp nối lỗi với stage và xác định traffic đã thực sự đi đâu.

## 23. Business metrics quan trọng hơn việc chỉ nhìn HTTP 200

Một hệ thống có thể trả 200 nhưng không thực hiện đúng nghiệp vụ:

- Order được tạo hai lần.
- Inventory bị giữ hai lần.
- Payment authorization không gắn với order.
- Refund bị mất.
- Catalog trả giá cũ.
- User nhìn thấy dữ liệu tenant khác.
- Search index chưa cập nhật.
- Command mới đã commit nhưng event projection không phát.

Các SLI có thể gồm:

| Capability | Business SLI |
|---|---|
| Catalog | Tỷ lệ truy vấn trả đúng item/permission/price |
| Inventory | Tỷ lệ reservation thành công và không oversell |
| Orders | Tỷ lệ order state transition hợp lệ, không duplicate |
| Payment | Tỷ lệ payment/order reconciliation khớp |
| Search | Tỷ lệ kết quả đúng filter/relevance theo contract |
| Reporting | Freshness và completeness theo cutoff |
| Notification | Tỷ lệ gửi đúng recipient, không gửi lặp |
| Workflow | Tỷ lệ hoàn tất trong deadline |

Đặc biệt với payment, inventory và order, cần có reconciliation trước và sau mỗi stage. Không tăng traffic chỉ vì p95 của new thấp hơn nếu business correctness chưa được chứng minh.

## 24. Error handling và fallback

Một facade có thể fallback từ new sang legacy khi new trả lỗi, nhưng điều này không phải lúc nào cũng an toàn.

Ví dụ GET catalog có thể đọc legacy khi new lỗi nếu dữ liệu tương thích. Nhưng POST create payment nếu new timeout sau khi commit thì gửi lại legacy có thể tạo payment thứ hai.

Trước khi cho phép fallback, xác định:

- Operation read hay command?
- Request có idempotency key không?
- New đã có thể commit side effect chưa?
- Có cách tra trạng thái operation không?
- Legacy có đủ dữ liệu/version mới nhất không?
- Retry/fallback có làm khuếch đại traffic không?
- Response semantics có tương thích?
- Client có thể nhận kết quả không chắc chắn hay cần polling?

### 24.1. Fallback theo operation

| Operation | Fallback khả thi? | Điều kiện |
|---|---|---|
| GET read-only | Thường dễ hơn | Legacy data đủ mới, cùng authorization |
| Search | Có thể | Index/schema và query semantics tương thích |
| Create order | Rủi ro cao | Idempotency, authoritative writer rõ |
| Payment authorize | Rất thận trọng | Idempotency, status lookup, reconciliation |
| Inventory reserve | Rủi ro cao | Reservation owner/consistency |
| Export async | Có thể | Job identity và trạng thái không trùng |
| Update profile | Tùy | Một writer và đồng bộ state |

Không tạo retry/fallback tự động chỉ từ HTTP 500. Phải biết operation có thể đã commit hay chưa.

## 25. Quản lý feature flags và routing policy

Một flag migration nên có metadata:

- Name và capability.
- Owner/team.
- Mục đích và phạm vi.
- Default per environment.
- Cohort/routing rules.
- Rollout stages.
- Guardrails.
- Kill switch behavior.
- Audit/change history.
- Expiry/removal date.
- Người được quyền thay đổi.

### 25.1. Tránh flag debt

Một flag được bật 100% trong sáu tháng nhưng không xóa sẽ tạo đường đi kép, test matrix lớn và khiến team không biết code legacy còn được dùng không.

Khi 100% traffic đã chuyển và criteria ổn định:

1. Xác minh không có hidden caller.
2. Xóa legacy routing branch.
3. Xóa flag và config không còn dùng.
4. Cập nhật tests/docs/catalog.
5. Theo dõi sau khi loại bỏ.
6. Thu hồi quyền/secret/route của phần cũ nếu phù hợp.

Flag migration có lifecycle riêng; không để trở thành cấu hình vĩnh viễn.

## 26. Kế hoạch cutover theo từng giai đoạn

Một mẫu quy trình:

### Giai đoạn 0 — Khảo sát và baseline

- Xác định capability và domain owner.
- Liệt kê callers, routes, jobs, tables, events và reports.
- Đo traffic mix, latency, errors, business outcomes.
- Xác định legacy behaviors và undocumented contracts.
- Chốt source of truth, seam và rollback constraints.
- Chọn một lát cắt có blast radius kiểm soát được.

### Giai đoạn 1 — Xây implementation mới

- Tạo API/event contracts.
- Xây service/module và data model.
- Đưa auth, observability, SLO và runbook vào từ đầu.
- Tạo tests parity, edge cases và contract compatibility.
- Xác định capacity và deployment strategy.

### Giai đoạn 2 — Chuẩn bị dữ liệu

- Initial snapshot/backfill.
- CDC/event synchronization nếu cần.
- Idempotency và ordering.
- Reconciliation tại cùng cutoff.
- Kiểm tra freshness và deletion semantics.
- Xác định khi nào new có thể phục vụ read/command.

### Giai đoạn 3 — Shadow

- Gửi request bản sao có kiểm soát.
- Ngăn side effects.
- So normalized responses.
- Theo dõi latency, capacity, security và mismatch.
- Sửa lỗi trước khi new trở thành authoritative.

### Giai đoạn 4 — Canary nhỏ

- Bật một cohort/route/tenant phù hợp.
- Duy trì legacy cho phần còn lại.
- Theo dõi business SLI và technical guardrails.
- Có người trực và stop criteria.
- Không tăng stage nếu sample chưa đủ hoặc data parity chưa đạt.

### Giai đoạn 5 — Mở rộng dần

- Tăng stage theo policy.
- Kiểm tra các cohort/regions/edge cases.
- Reconcile state và event lag.
- Cập nhật dependency owners.
- Xem xét capacity và cost khi new nhận thêm tải.

### Giai đoạn 6 — Cutover

- Chuyển 100% traffic thuộc capability.
- Chỉ định new là authoritative owner.
- Chặn đường write cũ.
- Giữ thời gian quan sát và rollback plan đã xác định.
- Xác minh mọi caller/job/report đã chuyển.

### Giai đoạn 7 — Decommission

- Xóa route/flag/adapter cũ.
- Xóa legacy module/table/queue khi an toàn.
- Thu hồi credentials và quyền.
- Dừng jobs, alerts và dashboards không còn cần.
- Giải phóng compute/storage.
- Cập nhật sơ đồ kiến trúc, catalog và runbook.
- Đo chi phí và operational burden sau migration.

Các giai đoạn có thể lặp cho nhiều capabilities; không cần chờ toàn bộ ứng dụng hoàn tất mới loại bỏ từng module đã được thay thế an toàn.

## 27. Kiểm thử migration

### 27.1. Contract tests

Kiểm tra API/event của new tương thích với callers và consumers đang tồn tại. Test success, validation, authorization, error codes, pagination, ordering, null/defaults và version compatibility.

### 27.2. Characterization tests

Đối với legacy behavior khó hiểu, ghi lại hành vi quan sát được từ các inputs representative để làm baseline. Không phải behavior cũ nào cũng đúng; đánh dấu những hành vi cần giữ và những bug được phép sửa có chủ đích.

### 27.3. Golden dataset / differential tests

Dùng bộ dữ liệu đã kiểm soát, chạy cả legacy và new rồi so kết quả theo business rules. Dataset cần có edge cases: trạng thái cũ, nulls, duplicate, timezone boundary, currency, deleted records, tenant isolation và lịch sử dài.

### 27.4. Shadow tests

Đảm bảo shadow mode không phát side effects, không làm tăng tải vượt mức, không gửi dữ liệu nhạy cảm ra môi trường không được phép và có thể tắt ngay.

### 27.5. Failure tests

Mô phỏng:

- New service timeout hoặc 5xx.
- Legacy timeout.
- Data projection lag.
- Broker unavailable.
- Duplicate/out-of-order events.
- Database pool exhaustion.
- Feature flag service mất kết nối.
- Gateway routing config sai.
- Pod restart trong lúc có request.
- Một vùng bị network partition.

Xác nhận fallback, timeout, retry, alert và recovery có hành vi đúng.

### 27.6. Load and soak tests

Traffic 1% ở canary có thể ít nhưng khi 100% traffic vào new, pool/DB/provider có thể quá tải. Test ở mức peak đại diện, burst, long-running soak, cold cache và autoscaling. Không suy capacity 100% bằng phép nhân tuyến tính nếu dependency hoặc contention dùng chung.

## 28. Các lỗi migration thường gặp

### 28.1. Không phát hiện hidden callers

Một cronjob, admin tool hoặc integration cũ vẫn gọi trực tiếp legacy endpoint/database sau cutover. Kết quả: legacy không thể shutdown hoặc state diverge.

Cách giảm: inventory access logs, DB clients, job schedules, network flows, API consumers và service catalog; dùng deprecation signals có thời hạn.

### 28.2. Facade chỉ route HTTP nhưng batch vẫn đọc DB cũ

Một capability tưởng đã chuyển nhưng báo cáo/ETL vẫn truy vấn legacy tables. Cần map toàn bộ consumers, không chỉ API.

### 28.3. Hai hệ thống cùng ghi authoritative state

Tạo race, lost updates và reconciliation phức tạp. Xác định một owner theo state/partition/time và chuyển quyền có kiểm soát.

### 28.4. Percentage traffic không đại diện

Cohort nhỏ có ít dữ liệu hoặc chỉ gồm internal users. Tăng traffic theo sample count, segment coverage và risk, không chỉ theo đồng hồ.

### 28.5. Shadow gây side effects

Gửi duplicate payment hoặc email. Shadow phải read-only/sandbox/side-effect disabled và được test.

### 28.6. Rollback chỉ có routing flag

New đã ghi dữ liệu mà legacy không biết. Cần data compatibility, projection lag, idempotency và compensation plan.

### 28.7. Eventual consistency không được công bố

Người dùng thấy stale order status sau khi write. Cần read-your-writes strategy, consistency token hoặc route read về owner.

### 28.8. Legacy không bao giờ được xóa

Team giữ facade, adapter, table, job và feature flags mãi mãi. Cần decommission owner, deadline, acceptance criteria và ngân sách cleanup.

### 28.9. Tách service trước khi hiểu domain

New service chỉ là remote wrapper quanh legacy DB; network call tăng nhưng coupling vẫn nguyên. Phải thiết lập domain ownership và data boundary thực sự.

### 28.10. Không theo dõi correctness

Dashboard chỉ thấy latency/error rate, trong khi duplicate orders hoặc missing refunds xuất hiện. Business reconciliation phải là guardrail.

## 29. Ví dụ: chuyển Catalog từ legacy monolith sang service mới

### 29.1. Hiện trạng

~~~text
Legacy Monolith
  - ProductController
  - ProductService
  - ProductRepository
  - product tables
  - category tables
  - image metadata
  - price rules (một phần)
~~~

Một số chức năng khác của monolith vẫn cần product data. Client đang gọi /api/products. Team muốn chuyển catalog query và quản lý sản phẩm sang Catalog Service.

### 29.2. Chọn boundary

Catalog Service sở hữu product metadata, category và lifecycle publish/unpublish. Pricing và Inventory vẫn do service/module khác sở hữu. Catalog không tự ghi giá tồn kho vào DB của Inventory.

Contract:

~~~text
GET  /catalog/items/{sku}
GET  /catalog/items?category=...
POST /catalog/items
PATCH /catalog/items/{sku}
POST /catalog/items/{sku}/publish
~~~

Các command có authorization và audit. Search query có thể dùng projection/index riêng.

### 29.3. Data preparation

- Backfill product/category từ legacy.
- Tạo mapping ID/sku.
- CDC hoặc outbox cho thay đổi trong giai đoạn sync.
- Chọn thời điểm cutover writer.
- Reconcile counts, SKU uniqueness, published status, category relationships.
- Xác minh image metadata và references.

### 29.4. Shadow reads

Gateway vẫn trả response từ legacy nhưng gửi shadow GET tới new. Normalization bỏ các field generated timestamp khác nhau. So status, product attributes, permissions, category membership và latency.

### 29.5. Canary

Bật 1% cohort phù hợp cho GET. Theo dõi p95, error, mismatch, cache hit, data freshness và authorization. Sau khi đạt sample/guardrails, tăng 5%, 25%, 50%, 100%.

### 29.6. Chuyển write ownership

Trước khi nhận POST/PATCH từ new:

- Dừng legacy writer hoặc route command về owner mới.
- Xử lý in-flight writes và sequence/version.
- Đồng bộ legacy consumers bằng event/projection nếu còn cần.
- Kiểm tra idempotency, optimistic concurrency và audit.
- Xác minh mọi admin tool/cronjob đã chuyển.

### 29.7. Decommission

- Chặn direct legacy product write.
- Chuyển các batch jobs và reports.
- Xóa legacy product controller/repository/table sau thời gian an toàn.
- Thu hồi DB credentials và permissions cũ.
- Xóa route/flag và dashboard không còn cần.
- Cập nhật service catalog và sơ đồ phụ thuộc.

Không chuyển Pricing hoặc Inventory chỉ vì chúng xuất hiện trong cùng màn hình Product. Mỗi capability cần seam, owner và migration plan riêng.

## 30. Ví dụ routing facade bằng Spring Boot

Một facade tối giản có thể dùng một interface chọn implementation. Đây là minh họa logic, không phải production-ready feature flag framework.

~~~java
public interface CatalogReader {
    CatalogItem getBySku(String sku);
}
~~~

Legacy adapter:

~~~java
@Component("legacyCatalogReader")
public class LegacyCatalogReader implements CatalogReader {
    private final LegacyProductRepository repository;

    public LegacyCatalogReader(LegacyProductRepository repository) {
        this.repository = repository;
    }

    @Override
    public CatalogItem getBySku(String sku) {
        return repository.findBySku(sku)
                .map(CatalogItem::fromLegacy)
                .orElseThrow(ProductNotFoundException::new);
    }
}
~~~

New adapter:

~~~java
@Component("newCatalogReader")
public class NewCatalogReader implements CatalogReader {
    private final CatalogClient client;

    public NewCatalogReader(CatalogClient client) {
        this.client = client;
    }

    @Override
    public CatalogItem getBySku(String sku) {
        return client.getBySku(sku);
    }
}
~~~

Facade chọn target:

~~~java
@Service
public class CatalogFacade {
    private final CatalogReader legacy;
    private final CatalogReader modern;
    private final MigrationPolicy policy;

    public CatalogFacade(
            @Qualifier("legacyCatalogReader") CatalogReader legacy,
            @Qualifier("newCatalogReader") CatalogReader modern,
            MigrationPolicy policy) {
        this.legacy = legacy;
        this.modern = modern;
        this.policy = policy;
    }

    public CatalogItem getBySku(String sku, String tenantKey) {
        if (policy.useNewCatalog(tenantKey)) {
            return modern.getBySku(sku);
        }
        return legacy.getBySku(sku);
    }
}
~~~

MigrationPolicy cần được định nghĩa với config/flag provider, deterministic cohort assignment, audit và safe default. tenantKey phải đến từ identity đã xác thực, không nhận tùy tiện từ query/header client. Code mẫu bỏ qua metrics, timeout, exception mapping và tracing; triển khai thực cần bổ sung các cross-cutting concerns đó.

### 30.1. Không fallback mù

Không nên viết:

~~~text
try new
catch any error -> legacy
~~~

Cách đó có thể che lỗi new, làm tải legacy tăng bất ngờ và tạo double side effect nếu request đã commit. Fallback phải được quyết định theo operation, error class, commit uncertainty và data consistency.

## 31. Chiến lược routing ở Gateway/Ingress

Một gateway có thể route theo path:

~~~yaml
# Pseudocode-like example: exact syntax depends on gateway/controller.
routes:
  - match: /api/catalog/**
    destination: catalog-service
  - match: /api/orders/**
    destination: legacy-monolith
~~~

Với canary percentage hoặc tenant cohort, dùng capability thực tế của gateway/controller/service mesh hoặc một routing service được kiểm soát. Không giả định YAML trên là resource chuẩn của Kubernetes.

Cần kiểm tra:

- Sticky/deterministic cohort.
- Header trust boundary.
- Path rewrite và forwarded headers.
- Authentication/authorization propagation.
- Timeout/retry policy ở gateway và downstream.
- Connection pooling và HTTP protocol.
- Routing config rollout/rollback.
- Metrics per destination.
- Gateway availability/capacity.
- Behavior khi flag provider unavailable.

Một header như X-Route-To: new do client tự gửi không được phép quyết định đi thẳng vào backend nội bộ. Routing policy phải được xác thực và audit.

## 32. Kiểm soát blast radius và capacity

Một service mới có thể đúng chức năng nhưng chưa chịu được traffic production:

- CPU/memory requests chưa phù hợp.
- DB pool quá nhỏ hoặc quá lớn.
- Cache cold và stampede.
- Provider quota thấp.
- Autoscaling phản ứng chậm.
- Node capacity chưa đủ.
- Trace/log sampling gây overhead.
- Downstream services chưa được capacity test.

Khi tăng stage, đánh giá **tải tổng thể**: legacy load giảm bao nhiêu, new load tăng bao nhiêu, shared dependencies có thay đổi ra sao. Nếu new và legacy cùng dùng một DB/provider, giảm load tại một process không đồng nghĩa giảm tổng load dependency.

Giữ max traffic stage dưới capacity đã thử nghiệm, có headroom cho burst và rollout. Không dùng 100% production traffic làm load test lần đầu.

## 33. Thời điểm legacy được coi là đã thay thế

Không phải chỉ khi 100% API traffic đi new. Một capability chỉ có thể decommission khi:

- Không còn caller chính thức gọi đường cũ.
- Không còn job/cron/batch/admin tool phụ thuộc.
- New là owner rõ ràng của state transitions.
- Dữ liệu đã chuyển và reconciliation đạt tiêu chí.
- Events/consumers/downstream dependencies đã chuyển.
- Reporting/analytics và audit đã có nguồn mới.
- Không còn rollback requirement chưa được xử lý.
- Runbook, alerts, dashboards và catalog đã cập nhật.
- Security/DB credentials cũ có thể thu hồi.
- Hạ tầng và chi phí cũ đã được tính.
- Domain owner và platform/operations xác nhận readiness.

Có thể dùng access logs/DB audit/network telemetry để chứng minh legacy path không còn được dùng trong một cửa sổ phù hợp. Không dựa vào việc "team nghĩ không còn ai gọi".

### 33.1. Legacy decommission checklist

- [ ] Tắt routing/flag cũ.
- [ ] Chặn API/endpoint cũ theo giai đoạn và có cảnh báo caller còn lại.
- [ ] Dừng scheduled jobs và batch consumers cũ.
- [ ] Chuyển database ownership/migrations.
- [ ] Backup/archive dữ liệu theo retention.
- [ ] Thu hồi service accounts, DB users, secrets và certificates.
- [ ] Xóa queues/topics cũ khi retention/replay policy cho phép.
- [ ] Xóa code, tests, configs, dashboards và alerts không còn dùng.
- [ ] Giải phóng compute/storage/load balancer.
- [ ] Cập nhật architecture diagram và service catalog.
- [ ] Xác nhận cost reduction và operational ownership.
- [ ] Theo dõi sau shutdown và có kế hoạch xử lý hidden dependency.

## 34. Đo thành công của chương trình migration

Không chỉ đo số microservices mới hoặc tỷ lệ traffic đã chuyển. Các chỉ số có ý nghĩa:

| Nhóm | Chỉ số |
|---|---|
| Delivery | Lead time cho một capability, số lần rollout bị dừng |
| Reliability | Error rate, SLO attainment, incident rate |
| Performance | p95/p99, throughput, resource cost per transaction |
| Correctness | Parity mismatch, duplicate/missing records, reconciliation |
| Data | CDC lag, projection freshness, backfill completion |
| Operations | MTTR/mitigation time, on-call load, runbook usage |
| Architecture | Legacy dependencies còn lại, direct DB access |
| Decommission | Legacy compute/storage/credentials đã thu hồi |
| Developer experience | Độ khó deploy, test và vận hành |
| Business value | Năng lực mới, thời gian thay đổi, rủi ro giảm |

Một migration tăng số service nhưng tăng lỗi, chi phí và on-call burden có thể chưa thành công. Cần so với mục tiêu ban đầu: scale độc lập, thay đổi nhanh hơn, giảm rủi ro legacy, cải thiện reliability hoặc cho phép phát triển capability mới.

## 35. Runbook cho một stage chuyển traffic

Trước stage:

1. Xác nhận change ticket, owner và người trực.
2. Xác nhận version, config, routing policy và stage hiện tại.
3. Kiểm tra baseline metrics, data freshness, parity và capacity.
4. Kiểm tra rollback route và kill switch.
5. Kiểm tra các dependency có incident đang diễn ra không.
6. Thống nhất go/hold/rollback criteria.
7. Xác nhận business test/synthetic transaction.

Trong stage:

1. Tăng cohort theo policy.
2. Xác minh actual traffic distribution, không chỉ desired percentage.
3. Theo dõi errors, latency, business outcomes, data lag và dependency.
4. Chọn trace đại diện từ new và legacy.
5. Không thay thêm config không liên quan trong cùng thời điểm.
6. Ghi stage marker và quyết định.
7. Dừng tăng nếu sample chưa đủ hoặc guardrail không đạt.

Khi có vấn đề:

1. Xác nhận tác động và phạm vi.
2. Hold rollout hoặc kill switch.
3. Chọn mitigation theo loại operation.
4. Kiểm tra commit uncertainty, in-flight work và data projection.
5. Route về legacy chỉ khi đường cũ còn authoritative/đủ dữ liệu và rollback an toàn.
6. Nếu không thể route back, dùng forward-fix hoặc business compensation đã thiết kế.
7. Xác nhận business SLI phục hồi.
8. Ghi timeline, preserve traces/logs và mở incident review.

Sau stage:

1. Lưu kết quả, sample size và cohort.
2. Reconcile dữ liệu theo cutoff.
3. Cập nhật migration dashboard và risk register.
4. Quyết định tiếp tục, giữ stage hoặc rollback.
5. Xử lý các mismatch trước khi tăng tỷ lệ.

## 36. Bài tập thực hành

### Bài 1 — Chọn seam

Một monolith có Catalog, Pricing, Orders và Payments. Catalog có API riêng, dữ liệu product không được module khác ghi trực tiếp; Pricing đọc product data và có logic độc lập.

**Câu hỏi:** Có nên chuyển toàn bộ Product/Pricing/Orders/Payments cùng lúc?

**Đáp án:** Không có lý do để chuyển cùng lúc. Có thể chọn Catalog read path làm lát cắt đầu nếu contract và freshness rõ, rồi đánh giá Pricing riêng. Orders/Payments có side effects và invariant cần migration plan khác.

### Bài 2 — Percentage routing

Một gateway đặt 5% request vào new service, nhưng 5% request đó toàn bộ đến từ một tenant lớn. Có thể kết luận new service đã được test trên traffic đại diện không?

**Đáp án:** Không. Cần xem tenant distribution, route mix, payload và cohort. Có thể chọn deterministic cohort và mở rộng theo các phân đoạn có đặc tính khác nhau.

### Bài 3 — Shadow side effects

Một endpoint POST /payments/authorize được shadow sang new implementation. Cả legacy và new đều gọi provider.

**Câu hỏi:** Rủi ro?

**Đáp án:** Có thể tạo hai payment authorizations. Shadow phải không thực hiện side effects hoặc dùng provider sandbox/mock và dữ liệu tách biệt; chỉ một bên là authoritative.

### Bài 4 — Rollback sau khi new đã ghi

New Order Service đã tạo 500 đơn, nhưng event sang legacy projection đang trễ 10 phút. New gặp lỗi và team route toàn bộ traffic về legacy.

**Câu hỏi:** Có an toàn không?

**Đáp án:** Chưa thể kết luận. Legacy có thể không nhìn thấy 500 đơn vừa tạo; route back có thể cho phép duplicate hoặc ghi đè state. Cần chờ/khôi phục projection, tra cứu owner mới, hoặc dùng forward-fix/compensation. Rollback policy phải được thiết kế trước.

### Bài 5 — Dual-write

Legacy và new cùng cập nhật product stock trong hai DB. Một lần ghi thành công ở new nhưng timeout ở legacy.

**Câu hỏi:** Vì sao retry cả hai không đủ?

**Đáp án:** Không biết lần ghi nào đã commit; retry có thể ghi lặp hoặc tạo state diverge. Cần một authoritative writer, idempotency/version và event projection/reconciliation. Tránh dual-write trực tiếp không có coordination.

### Bài 6 — Read-your-writes

User cập nhật catalog item qua new service rồi lập tức GET qua route vẫn đang vào legacy projection.

**Câu hỏi:** User có thể thấy gì?

**Đáp án:** Giá trị cũ do projection lag. Cần routing nhất quán theo owner, read-your-writes token/version hoặc đọc trực tiếp new owner trong thời gian phù hợp.

### Bài 7 — Canary guardrail

New service có p95 thấp hơn legacy nhưng business success giảm 0,5% do một số SKU không tìm thấy.

**Câu hỏi:** Có nên tăng từ 25% lên 50%?

**Đáp án:** Không. Correctness guardrail không đạt; giữ/rollback và điều tra dữ liệu, mapping, contract. Latency không bù được nghiệp vụ sai.

### Bài 8 — Decommission

Sau cutover, access log API cũ không có request trong 7 ngày. Có thể xóa DB/table legacy ngay không?

**Đáp án:** Chưa chắc. Cần xem batch jobs, direct DB clients, reporting, scheduled jobs, retention, backups và các chu kỳ nghiệp vụ ít xảy ra hơn 7 ngày. Dùng nhiều nguồn bằng chứng và kế hoạch decommission.

### Bài 9 — Facade failure

Facade flag provider bị outage. Hệ thống có nên route toàn bộ request về new?

**Đáp án:** Phải theo safe default đã thiết kế cho capability và consistency. Không mặc định new là an toàn; có thể dùng cached policy snapshot, route legacy, reject/hold hoặc degraded mode tùy data ownership và operation. Quyết định phải được test trước.

### Bài 10 — Phân biệt Strangler và canary

Team deploy v2 của cùng Catalog Service bằng canary 10%, nhưng vẫn giữ cùng database/schema và ownership.

**Câu hỏi:** Đây đã là Strangler Fig chưa?

**Đáp án:** Đó là canary release của một version. Chỉ trở thành một bước trong Strangler nếu đang chuyển dần capability/ownership khỏi implementation legacy theo một migration plan. Hai kỹ thuật có thể kết hợp nhưng không đồng nghĩa.

## 37. Checklist trước khi chuyển một capability

### Boundary và contract

- [ ] Capability có domain owner và seam rõ.
- [ ] Đã liệt kê callers, jobs, reports và hidden dependencies.
- [ ] API/event contract, error semantics và version compatibility đã định nghĩa.
- [ ] Authn/authz và tenant isolation parity đã được kiểm tra.
- [ ] Invariants và transaction boundaries được hiểu.
- [ ] Không tách service chỉ dựa trên folder hoặc table.

### Data và consistency

- [ ] Source of truth và writer owner rõ ở từng giai đoạn.
- [ ] Snapshot/backfill/CDC/outbox strategy được kiểm chứng.
- [ ] Idempotency, ordering, duplicate và late events có policy.
- [ ] Read-your-writes/eventual consistency được xử lý.
- [ ] Reconciliation dùng cutoff và business definitions thống nhất.
- [ ] Schema migration tương thích legacy/new trong rollout.
- [ ] Deletes, corrections và retention được xử lý.

### Traffic và operations

- [ ] Facade/routing policy có owner, audit, kill switch.
- [ ] Cohort/percentage deterministic khi workflow cần.
- [ ] Shadow mode không tạo side effects.
- [ ] Canary có sample criteria, duration, guardrails và stop conditions.
- [ ] Dashboard phân biệt legacy/new/shadow và rollout stage.
- [ ] SLI business correctness cùng technical latency/error được theo dõi.
- [ ] Capacity test đủ cho traffic stage tiếp theo.
- [ ] Fallback/rollback theo operation đã được test.
- [ ] Có người trực, runbook và incident escalation.

### Cutover và retirement

- [ ] New đã nhận đúng ownership của capability.
- [ ] Legacy writer/caller đã được ngăn hoặc chuyển.
- [ ] Hidden consumers được xác minh bằng nhiều nguồn.
- [ ] Rollback window và data constraints được chốt.
- [ ] Decommission owner, criteria và timeline có.
- [ ] Credentials, tables, jobs, routes và infrastructure cũ được thu hồi an toàn.
- [ ] Catalog, diagrams, docs và alerts được cập nhật.
- [ ] Kết quả migration được đo theo reliability, cost và business value.

## 38. Ghi nhớ

Strangler Fig là một chiến lược chuyển đổi kiến trúc theo từng capability. Facade hoặc routing layer giữ contract bên ngoài ổn định, trong khi từng route/tenant/cohort được chuyển dần từ legacy sang implementation mới. Shadow traffic, canary và feature flags hỗ trợ quan sát và điều khiển, nhưng không thay thế việc xác định domain boundary và data ownership.

**Dữ liệu quyết định độ an toàn của migration.** Cần một nguồn sự thật rõ cho từng state, một writer authoritative tại từng giai đoạn, event/CDC/outbox có semantics, idempotency, ordering, backfill và reconciliation. Dual-write không kiểm soát và fallback mù có thể tạo lỗi nghiêm trọng dù routing trông đơn giản.

Chuyển traffic theo stage phải có guardrails technical và business, đủ sample, observability theo version/cohort và rollback plan phản ánh cả code lẫn dữ liệu. Khi new đã nhận command và commit state, route về legacy có thể không an toàn; có thể cần forward-fix hoặc compensation.

Migration chỉ hoàn tất khi các callers, jobs, data consumers và ownership đã chuyển, legacy không còn trách nhiệm cần thiết, rồi code/hạ tầng/quyền cũ được decommission có bằng chứng.

**Nguyên tắc cốt lõi: chia quá trình hiện đại hóa thành những lát cắt nghiệp vụ nhỏ, có một chủ sở hữu dữ liệu rõ ràng, chuyển traffic theo điều kiện có thể đo, bảo vệ tính đúng đắn ở mọi giai đoạn và chỉ loại bỏ legacy khi đã chứng minh không còn phụ thuộc.**