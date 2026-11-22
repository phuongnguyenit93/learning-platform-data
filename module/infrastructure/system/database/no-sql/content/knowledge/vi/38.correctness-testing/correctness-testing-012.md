# Kiểm thử tích hợp trên engine thật và ghi rõ giới hạn của mock/emulator

## 1. Tình huống mở đầu: tất cả mock đều xanh, production vẫn mất dữ liệu

Một hệ thống Java bán vé dùng một NoSQL database. Đội phát triển viết lớp `TicketRepository`, sau đó mock repository để kiểm thử:

~~~java
when(repository.getAvailable("concert-7"))
    .thenReturn(1L);

when(repository.reserve("concert-7", 1))
    .thenReturn(true);

assertTrue(service.buyTicket("concert-7"));
~~~

Test thành công. Nhưng khi hai Java instances cùng mua vé cuối, production xảy ra lịch:

~~~text
Client A reads available = 1
Client B reads available = 1
Client A writes available = 0, creates reservation A
Client B writes available = 0, creates reservation B
Both return SUCCESS
~~~

Mock đã trả những giá trị mà người viết test yêu cầu; nó **không thực thi atomicity, index, transaction, write concern hoặc failover semantics của NoSQL database**. Một in-memory fake có `synchronized` thậm chí có thể vô tình an toàn hơn implementation đang chạy phân tán.

Đội chuyển sang emulator. Test vẫn xanh, nhưng trên dịch vụ managed thật xuất hiện throttling, eventual index propagation, permission errors và timeout sau commit. Emulator giúp thử API, nhưng không nhất thiết tái hiện cơ sở hạ tầng, replication, IAM và tất cả giới hạn của dịch vụ.

Cuối cùng đội chạy một database container thật. Một conditional update được kiểm đúng trên một node, nhưng thử nghiệm chưa chạy failover, không có network partition và không có replica lag. Kết quả này rất có giá trị, song vẫn chưa chứng minh tính đúng của **cụm phân tán**.

**Bài học này thuộc module Database No SQL, chương Kiểm thử tính đúng, chủ đề “Kiểm thử tích hợp trên engine thật và ghi rõ giới hạn của mock/emulator”.**

Mục tiêu là chọn mức độ chân thực của test theo từng yêu cầu, xây tích hợp Java với engine thực, ghi các giả định và khoảng trống còn lại, và không biến một tín hiệu `PASS` hữu hạn thành lời hứa vượt quá phạm vi kiểm chứng.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt mock, stub, fake, emulator, simulator, engine thật đơn nút, cụm thật và môi trường managed.
2. Giải thích vì sao unit test/mock không xác nhận được atomicity, consistency, replication, durability, index và driver behaviors.
3. Xác định những hợp đồng phải được kiểm với database engine thực.
4. Dùng Testcontainers/JUnit 5 cho Java integration tests với MongoDB và Redis.
5. Thiết kế contract tests có thể chạy trên cả source/target adapters.
6. Tạo concurrency tests có barrier, lịch sử thao tác và oracle độc lập.
7. Đánh giá giới hạn của DynamoDB Local, LocalStack và các môi trường mô phỏng managed service.
8. Lập kế hoạch thử nghiệm Cassandra, MongoDB replica sets/sharding, Redis Cluster/Sentinel, Elasticsearch/OpenSearch và Couchbase theo topology cần kiểm.
9. Phân biệt `PASS`, `FAIL`, `UNKNOWN`, `NOT_COVERED` và `NOT_REPRESENTATIVE`.
10. Tổ chức CI thành nhiều tầng, kết hợp test nhanh với test failover/recovery được chạy ở môi trường phù hợp.
11. Ghi version, config, seed, dữ liệu, fault schedule và bằng chứng để tái lập lỗi.
12. Tạo báo cáo minh bạch về **điều đã chứng minh** và **điều chưa chứng minh**.

---

## 2. Chính xác thì “kiểm thử tích hợp” là gì?

Unit test tập trung vào một đơn vị logic tương đối độc lập; integration test kiểm sự tương tác giữa những thành phần thật theo phạm vi đã xác định.

Trong NoSQL, một integration test thường bao gồm:

~~~mermaid
flowchart LR
    T["JUnit test harness"] --> A["Java service/repository adapter"]
    A --> D["Real NoSQL driver"]
    D --> E["Real database process"]
    E --> P["Persistent/temporary storage"]
    T --> O["Independent oracle"]
    O --> E
~~~

Những yếu tố quan trọng:

- Test gọi **code Java thực tế** mà ứng dụng sử dụng, không thay repository bằng `when(...).thenReturn(...)`.
- Driver thật serialize request, quản lý connection và xử lý response của engine.
- Database engine thật thực thi query, index, conditional update hoặc transaction.
- Oracle xác minh kết quả từ nguồn phù hợp, thay vì chỉ khẳng định method không ném exception.
- Môi trường test có topology/config/versions được ghi rõ.

Một kiểm thử có database process thật nhưng truy vấn trên fake driver vẫn chưa kiểm đường kết nối production. Ngược lại, dùng driver thật với server giả chỉ kiểm được giao thức/serialization đến mức server giả mô phỏng.

### 2.1. Integration test không có nghĩa toàn bộ production

Một MongoDB container đơn nút dùng để kiểm `$inc` và unique index rất hữu ích, nhưng không cho biết replica election dưới network partition. Một Redis server thật không tự kiểm Redis Cluster hash slots hoặc failover.

### 2.2. Điều cần khẳng định

Thay vì “đã test database”, nên viết:

> “Đã kiểm atomic conditional update trên MongoDB engine phiên bản X chạy trong một replica-set test container, hai mươi Java clients đồng thời, một document, không có fault injection. Chưa kiểm network partition, sharded cluster hoặc region failover.”

Đây là bằng chứng có phạm vi, không phải thiếu tự tin.

---

## 3. Thang độ chân thực của test

| Tầng | Môi trường | Điều có thể tin cậy tương đối | Điều chưa thể suy ra |
|---|---|---|---|
| L0 | Pure model/unit test | Logic nghiệp vụ, chuyển trạng thái, boundary | Database behavior |
| L1 | Mock/stub repository | Service orchestration, mapping lỗi đã lập trình | Query/index/atomicity thật |
| L2 | In-memory fake | Hành vi fake và một số contract | Durability, concurrency đa node, optimizer |
| L3 | Emulator/local service | Một phần API/wire behavior được mô phỏng | Full managed behavior và production topology |
| L4 | Real engine, one node | Query, index, atomic write, protocol trên bản đang chạy | Replication/failover/quorum |
| L5 | Real engine, multi-node | Membership, replication, election/consistency trong topology test | Mọi cloud/provider failure mode |
| L6 | Managed staging service thật | Managed API, IAM, một số quotas/limits và config thật | Không tự chứng minh mọi tình huống production/scale |
| L7 | Staged disaster/chaos drills | Các failure paths được kích hoạt và đo thực tế | Những lỗi chưa từng kích hoạt hoặc chưa được quan sát |

### 3.1. Tầng cao không thay hết tầng thấp

Test L6 thường đắt/chậm, khó debug. Pure model L0 lại rất tốt để sinh hàng nghìn command sequences và thu nhỏ counterexample.

### 3.2. Không đánh giá test chỉ bằng số lượng

Một nghìn unit tests với mocked `reserve()` không thay được một integration test chứng minh conditional write thật ngăn hai successful reservations cho vé cuối.

### 3.3. Độ chân thực có nhiều chiều

Cùng là “engine thật”, các chiều vẫn khác:

- Engine version.
- Driver version.
- Network topology.
- Storage type.
- Replication/sharding.
- Authentication/TLS.
- Write/read concern và consistency level.
- Indexes, TTL, schema.
- Load, data size, skew.
- Clock, region và failure domains.
- Managed control plane.

Do đó không có một nhãn `REAL=true` đủ mô tả fidelity.

---

## 4. Mock, stub, spy, fake, emulator và simulator

### 4.1. Stub

Trả dữ liệu định trước để kiểm nhánh code:

~~~java
when(profileGateway.find("user-1"))
    .thenReturn(Optional.of(profile));
~~~

Không thực thi hành vi NoSQL.

### 4.2. Mock

Ngoài trả dữ liệu còn xác minh tương tác như `verify(repository).save(...)`. Có ích để xem service đã gọi dependency đúng số lần theo một đường code.

**Không chứng minh** database đã commit, transaction atomic hoặc write được replicate.

### 4.3. Spy

Theo dõi một object thật hay một phần thật, nhưng dependency phía sau có thể vẫn giả. Cần ghi scope.

### 4.4. In-memory fake

Một implementation đơn giản của repository trong `HashMap`, có thể hỗ trợ tests domain. Nó có thể vô tình:

- Luôn serializable vì tất cả methods synchronized.
- Không bao giờ timeout.
- Không giới hạn item size.
- Không có index hoặc query planner.
- Không có partial failures.
- Trả reads mới nhất ngay lập tức.
- Không có TTL/GC hoặc chỉ xóa theo clock fake.

### 4.5. Emulator

Một dịch vụ/local binary mô phỏng API và một tập hành vi của target system; ví dụ DynamoDB Local hoặc những thành phần AWS được mô phỏng bởi LocalStack.

Emulator có thể giúp kiểm SDK requests, serialization, ConditionExpressions trong phạm vi hỗ trợ. **Không tự giống managed service thật** về IAM, stream delivery, global replication, throttle/quota, latency và vận hành.

### 4.6. Simulator

Một môi trường dựng mô hình time/network/replication để thử đặc tả. Giá trị của nó phụ thuộc giả định và độ đầy đủ mô hình, không phải tên gọi “simulator”.

### 4.7. Real engine

Binary/server chứa logic thực của sản phẩm hoặc bản phân phối được hỗ trợ. Nó kiểm được nhiều semantics thật hơn, nhưng chỉ trong cấu hình và topology được thiết lập.

---

## 5. Câu hỏi quyết định dùng tầng nào

Trước mỗi test, hãy hỏi:

1. Bất biến hoặc hợp đồng nào đang được bảo vệ?
2. Hành vi đó nằm trong Java logic hay do NoSQL engine quyết định?
3. Có phụ thuộc network, process crash, election hoặc replication không?
4. Có cần kiểm managed APIs như IAM, PITR, global tables không?
5. Có cần dữ liệu và tải đủ đại diện không?
6. Nếu test xanh ở tầng thấp, **lỗi nào vẫn có thể lọt**?
7. Mất bao lâu/chi phí bao nhiêu để chạy tầng cao?
8. Có thể đưa phần logic nhanh lên model tests và phần nguy hiểm xuống integration tests không?

Ví dụ:

| Yêu cầu | Tầng tối thiểu có giá trị | Tầng bổ sung |
|---|---|---|
| Mapping DTO thiếu field | Unit/contract | Engine real cho BSON/SDK representation |
| MongoDB unique compound index | MongoDB real | Concurrent creates/failover |
| Cassandra `IF` conditional update | Cassandra real | Multi-node LWT fault tests |
| DynamoDB conditional write | DynamoDB Local để smoke | AWS staging cho service fidelity |
| Redis Lua atomicity | Redis server real | Redis Cluster/failover cho durable outcomes |
| MongoDB replica election | Replica set thật nhiều member | Fault injection |
| Global table conflict | Managed multi-region test | Chaos/reconciliation |
| Tenant access policy | API + real DB data | IAM/role integration |
| CDC resume after failover | Real engine + stream integration | Restart/network faults |
| RPO/RTO của restore | Restore drill | Data scale/DR environment |

Không coi “tầng tối thiểu” là mức bảo đảm toàn diện; nó là điểm bắt đầu cho một contract cụ thể.

---

## 6. Điều mock rất giỏi

Mock hữu ích khi muốn kiểm:

- Service không gọi database nếu input invalid.
- Khi gateway trả `NotFound`, API ánh xạ thành 404.
- Khi dependency trả conflict, service không gửi email xác nhận.
- Deadline, retry budget và backoff orchestration trong logic Java.
- Authorization gate ở application layer trước repository.
- Một saga gọi các bước bù trừ đúng thứ tự trong model.
- Validation `quantity > 0` hoặc currency scale.
- Logging/redaction và metric emission.
- Pure state-machine transitions.

### 6.1. Mock phải có ranh giới

Mock một external payment provider để test business workflow là hợp lý; nhưng nếu test đang khẳng định MongoDB `updateOne` atomic thì **không mock MongoDB engine**.

### 6.2. Không đo performance từ mock

Một mock trả sau 1 ms không phản ánh network, query planner, I/O, compaction, pooling, throttling hoặc replication.

### 6.3. Mocks thường thực thi giả định người viết

Nếu một writer tưởng transaction luôn success, mock sẽ luôn success. Test chỉ xác minh logic đã được viết theo đúng giả định ấy, không phát hiện giả định sai.

### 6.4. Không có lỗi từ mock không chứng minh lỗi bất khả thi

Trong production có thể nhận timeout, failover, partial write, duplicate events, stale replica hoặc unknown commit result mà mock không bao giờ phát.

---

## 7. False confidence: những test xanh giả điển hình

| Test dùng mock/fake | Kết luận sai thường gặp | Điều thực tế cần kiểm |
|---|---|---|
| `save()` trả success | Write durable | Write concern/ACK/storage |
| `find()` trả latest | Mọi read mới nhất | Read preference/consistency |
| Hai method gọi liên tiếp | Transaction atomic | Engine transaction boundary |
| `HashMap.putIfAbsent` | Distributed uniqueness | Unique index/conditional create |
| In-memory counter atomic | No oversell | Multi-instance conditional update |
| Fake query tự sort | Sort/filter đúng | Index/collation/query semantics |
| Fake xóa TTL đúng giờ | Physical TTL đúng giờ | Engine TTL cleanup và app expiry check |
| Fake xử lý event đúng 1 lần | Exactly-once effect | At-least-once delivery + dedup |
| `sleep()` làm lag giả | Replica consistency | Real replication/CDC watermark |
| Fake cluster luôn healthy | Failover đúng | Multi-node election/partition |
| Mock IAM allow | Production IAM đúng | Real managed permissions |
| Test trên một tài liệu nhỏ | Item size tốt | Max item/partition, large values |
| Fake key-value đơn giản | MongoDB aggregation tương thích | Real query operators |
| Stub exception cố định | Driver retry đúng | Real error classes, timeouts và unknown outcome |

**Nguyên tắc:** nếu kết quả phụ thuộc behavior mà mock tự tạo, hãy nói rõ nó kiểm behavior của mock/service, không phải của database.

---

## 8. Test trên engine thật nên kiểm những gì trước tiên?

### 8.1. Kiểu dữ liệu và serialization

Document types, null/missing, decimal precision, UUID/BSON ObjectId, binary, timestamp/timezone, nested arrays/maps.

### 8.2. Query semantics

Predicates, sort/collation, projections, pagination, aggregation, secondary index, scan restrictions.

### 8.3. Writes và atomicity

Create, update, upsert, partial update, conditional writes, optimistic locking, uniqueness, transaction commit/abort.

### 8.4. Driver behavior

Connection string, TLS, authentication, timeouts, retry errors, server discovery, pool reuse và max connections.

### 8.5. Storage lifecycle

TTL, deletion/tombstones, index maintenance, background cleanup, schema migrations, backup/restore API.

### 8.6. Consistency và concurrency

Read-your-writes, stale read contract, race trên last resource, conflict detection, duplicate request handling.

### 8.7. Replication/failover

Thử trên **cụm thật**, không suy từ one-node integration test.

---

## 9. Trước khi chạy test: viết contract và oracle

Một test integration đáng giá có:

~~~yaml
testId: IT-RESERVE-001
contract: "At most one successful reservation for the last ticket"
authority: "inventory + reservation ledger"
precondition:
  capacity: 1
  activeReservations: 0
concurrency:
  clients: 20
  sameEvent: true
expected:
  successfulReservations: 1
  available: 0
  held: 1
  duplicateSeatAssignments: 0
evidence:
  - request IDs and results
  - authoritative state after logical commit
  - reservation ledger
environment:
  engine: MongoDB
  topology: replica-set test container
limitations:
  - "No leader failover injected"
  - "No sharding"
  - "No cross-region replication"
~~~

### 9.1. Oracle độc lập

Không chỉ assert `repository.reserve()` trả true. Cần kiểm trạng thái từ nguồn có thẩm quyền, outcome history và invariants.

### 9.2. Phân biệt thành công với không có exception

Một write bị condition reject có thể không ném exception tùy driver/method; cần kiểm `matchedCount`, affected rows, applied flag hoặc transaction response.

### 9.3. Phân biệt `UNKNOWN`

Một timeout sau commit có thể để lại dữ liệu. Test phải đọc status bằng idempotency key/ledger, không mặc định rollback.

### 9.4. Khi nào có thể kết luận `PASS`?

Khi predicate, dữ liệu kiểm và môi trường thực tế phù hợp với những giả định được ghi. Nếu thiếu checkpoint hoặc test không chạy topology cần thiết, ghi `NOT_COVERED` hoặc `UNKNOWN`.

---

## 10. Tính đúng phụ thuộc trạng thái đã commit

Ví dụ invariant:

\[
available + held + sold = capacity.
\]

Để kiểm trên engine thật, phải biết các giá trị đọc thuộc **cùng logical snapshot**.

### 10.1. False failure vì snapshot lệch

Nếu `available` đọc trước một transaction và `held` đọc sau transaction, tổng có thể sai tạm thời chỉ vì phép đo chéo thời điểm.

### 10.2. False pass vì counter thiếu ledger

Một code lỗi có thể tạo hai reservations thành công nhưng `available` vẫn không âm do lost update. Kiểm cả active reservation IDs/sold seats.

### 10.3. History property

Không có hai successful receipts cho cùng resource. Chỉ kiểm snapshot cuối sau compensation có thể bỏ sót một vi phạm đã xảy ra.

### 10.4. Ranh giới theo engine

Một document atomic update trong MongoDB khác transaction nhiều documents; một conditional write trong DynamoDB khác cross-item transaction; Redis Lua single-primary atomicity khác durable global commit; Cassandra LWT khác CQL batch.

---

## 11. Kiểu dữ liệu: nơi fake thường khác engine thật

Ví dụ một document cũ:

~~~json
{
  "orderId": "o-7",
  "amount": "100.00",
  "createdAt": "2026-11-14T02:03:04Z",
  "discount": null
}
~~~

Một record mới:

~~~json
{
  "orderId": "o-8",
  "amountMinor": 10000,
  "createdAt": 1794621784000
}
~~~

Cần kiểm:

- Mapping String ↔ decimal chính xác.
- Timezone/epoch seconds/milliseconds.
- Null khác missing.
- Empty array khác field absent.
- UTF-8/Unicode normalization.
- UUID/BSON type.
- Binary serialization.
- Enum unknown values.
- Field name escaping/reserved words.
- Numeric overflow, rounding và unsigned assumptions.

### 11.1. Ví dụ bug được fake bỏ qua

Fake dùng Java `Map<String,Object>` với `BigDecimal`, còn driver thực serialize thành `Double` hoặc String theo converter. Kết quả tiền bị thay đổi mà unit test vẫn xanh.

### 11.2. Dùng round-trip thật

Ghi một record bằng mapper Java thực, đọc bằng driver/codec thực, rồi so canonical domain representation. Không so raw JSON bytes nếu field order/type encoding không thuộc hợp đồng.

### 11.3. Kiểm legacy cohorts

Test chỉ dùng fixtures tạo từ DTO hiện tại không phát hiện dữ liệu 3 năm trước có kiểu sai hoặc thiếu field.

---

## 12. Query/index semantics: cùng kết quả nhỏ chưa chứng minh đúng

### 12.1. Query planner thật

Một fake có thể filter toàn bộ `List<Order>` trong memory. Engine thật có thể cần index, cấm scan/filter hoặc dùng đường truy cập tốn capacity.

### 12.2. Sort/collation

- `createdAt DESC` nhưng nhiều records cùng timestamp.
- Lowercase/case insensitive matching.
- Locale/Unicode collation.
- Missing/null sort positions.
- Numeric vs lexical ordering.
- Nested array semantics.

### 12.3. Pagination

Offset, keyset và opaque continuation tokens có semantics khác nhau. Test nhiều trang, insert/delete trong lúc paging và duplicate/tie-breaker.

### 12.4. Query results không là mọi thứ

Thêm test `EXPLAIN`/index usage khi engine hỗ trợ và mục tiêu là tránh full scan; đo p99 với dataset đủ đại diện. Một query đúng kết quả nhưng scan 100 triệu items vẫn không đạt contract vận hành.

### 12.5. Index uniqueness

Một fake dùng `HashMap` có thể áp uniqueness trên `_id` thôi, còn target cần unique `(tenantId, normalizedEmail)` hoặc partial uniqueness chỉ active accounts.

---

## 13. Atomic update: test bắt đầu bằng một thao tác, rồi tăng cạnh tranh

Tình huống số vé còn 1:

~~~text
Initial state:
  available=1
  held=0

20 clients:
  reserve(eventId, quantity=1)

Expected:
  exactly 1 logical success
  19 rejected by condition
  available=0
  held=1
~~~

### 13.1. Vòng 1: single-thread

Test boundary `q=0`, `q=1`, `q=2` và result mapping.

### 13.2. Vòng 2: concurrent

Cho hai mươi clients cùng start bằng barrier; kiểm successful effects/receipts và state.

### 13.3. Vòng 3: failover

Dùng cluster thật và inject fault sau commit trước ACK. Kiểm unknown outcome + idempotent retry.

### 13.4. Vòng 4: restore

Khôi phục checkpoint và kiểm không double-allocate resource hoặc mất ledger gây replay effect.

### 13.5. Lưu ý phạm vi

Một test concurrent pass trên một primary không chứng minh behavior sau asynchronous replica promotion hoặc cross-region conflict.

---

## 14. Giao dịch đa document/item: mock không cho bạn isolation

Một service:

~~~text
read inventory
create reservation
decrement available
write outbox event
~~~

Nếu source engine chỉ bảo đảm atomic mỗi document, những bước trên không tự thành một transaction.

### 14.1. Câu hỏi cần trả lời

- Có transaction API thật không?
- Mọi writes có nằm trong transaction được hỗ trợ không?
- Điều kiện commit/abort?
- Có transaction retries hay unknown commit result không?
- Concurrent reads có isolation level nào?
- Transaction có giới hạn số items/partitions/size không?
- External provider có nằm ngoài transaction không?

### 14.2. Đường lỗi cần test

Inject exception sau bước 2, timeout lúc commit, process kill và retry transaction callback. Kiểm không xuất hiện orphan reservations hoặc outbox intent thiếu.

### 14.3. Không dùng database khác làm “in-memory replacement”

H2/SQLite hay một key-value fake không thay được MongoDB transactions, Cassandra LWT hay DynamoDB conditional write semantics. Có thể dùng cho domain-level tests, nhưng không gọi chúng là engine-fidelity integration tests.

---

## 15. Durability và ACK: kết nối thành công không chứng minh dữ liệu bền

Một write có thể được xác nhận ở các mốc khác nhau:

~~~text
Client sends
  -> server receives
  -> memory write
  -> local WAL/journal durability
  -> replication/consensus condition
  -> ACK to client
~~~

Tùy engine và cấu hình, ACK không luôn đồng nghĩa dữ liệu sẽ sống sau mọi failure domain.

### 15.1. Mock không có durability

`when(save).thenReturn(success)` không ghi WAL, disk hoặc replicas.

### 15.2. Engine thật một node cũng chưa đủ

Kiểm kill/restart một node giúp hiểu local recovery, nhưng không chứng minh synchronous replication hoặc region RPO.

### 15.3. Unknown outcome

Nếu server commit nhưng response mất, client thấy timeout. Test cần oracle bằng operation ID để không gửi action có side effect lần nữa.

### 15.4. Test phải ghi config

Write concern, read concern, consistency level, fsync/AOF, replication settings và isolation policies ảnh hưởng kết luận.

---

## 16. TTL và dữ liệu hết hạn: emulator rất dễ đơn giản hóa sai

Yêu cầu:

> Session không được sử dụng sau `expiresAt`.

Một fake có thể tự xóa session đúng thời gian fake clock chạy đến mốc. Engine thật có thể cleanup bất đồng bộ.

### 16.1. Safety đúng

\[
now\ge expiresAt\Rightarrow authorizationDenied.
\]

### 16.2. Physical deletion là việc khác

Cần test policy về cleanup trong thời gian dự kiến nếu đó là yêu cầu lưu trữ/retention. Không dùng thời điểm cleanup vật lý như oracle duy nhất cho auth.

### 16.3. TTL trong các engine

MongoDB TTL index monitor, DynamoDB TTL removal, Redis key expiration và Cassandra TTL/tombstone behavior khác nhau. Mỗi cái cần test/version-specific docs và quy tắc chờ phù hợp.

### 16.4. Tránh flaky timing

Dùng injected application `Clock`, kiểm mốc logic gần `expiresAt`, và chỉ chạy test physical TTL cleanup với bounded polling + timeout hợp lý. Không bắt engine phải dọn vật lý trong vài millisecond nếu nó không cam kết vậy.

---

## 17. CDC và streams: mock message listener không đủ

Một system:

~~~text
NoSQL write
   -> CDC/change stream
   -> event broker
   -> Java consumer
   -> search/read model
~~~

### 17.1. Contract cần test

- Insert/update/delete event shapes.
- Ordering scope.
- Resume/checkpoint.
- Retry và duplicate delivery.
- Schema version.
- Before/after image semantics.
- Log retention.
- Backfill + CDC race.
- Consumer idempotency.
- Recovery sau restart/failover.

### 17.2. Fake stream dễ bỏ sót lỗi

Nếu fake luôn đưa event theo thứ tự một lần, nó không kiểm production behavior khi event đến trùng, chậm, hoặc source log hết retention.

### 17.3. Chạy real stream

Tạo update trên engine thật, đọc bằng driver/connector thật, lưu source version/opaque token và kiểm downstream projection. Test failover/resume cần topology hỗ trợ.

### 17.4. Không giả định ordering toàn cục

Một stream partitioned có thứ tự trong partition nhưng không nhất thiết trong mọi partitions. Biến requirement thành per-key/per-entity version predicate.

---

## 18. Security cũng cần integration tests thật

### 18.1. TLS

Kiểm trust chain và SAN hostname/IP. Một mocked repository không chứng minh driver từ chối server certificate sai.

### 18.2. Authentication

Test credentials/role hợp lệ và không hợp lệ bằng engine thật hoặc managed staging. Không chỉ mock `authorize=true`.

### 18.3. Authorization

Test tenant A không đọc/ghi được record B; kiểm API, direct DB account, search index và cache paths.

### 18.4. IAM của managed service

DynamoDB Local không thay AWS IAM evaluation; test IAM resource/action policies cần môi trường AWS staging phù hợp.

### 18.5. Secrets và permissions

Không dùng production keys/PII trong local integration tests. Tạo test identities, scope hẹp và rotate/cleanup theo quy trình.

---

## 19. Một database process thật vẫn có thể khác production

Các nguồn khác biệt:

| Trục | Local test | Production | Rủi ro |
|---|---|---|---|
| Version | `mongo:7` | Engine version khác | Semantics/feature changes |
| Topology | One node | Replica set/sharded | Failover/quorum thiếu |
| Network | localhost | Multi-AZ/region | Timeout/partition khác |
| Disk | Docker ephemeral | Persistent SSD/network volume | Durability/latency khác |
| Auth | Disabled | TLS + RBAC/IAM | Permission bugs |
| Data | 100 records | 100 million records | Index/partition hot |
| Workload | Sequential | Concurrent peaks | Races/throttling |
| Clock | One host | Multi-host skew | Lease/expiry |
| Config | Defaults | Tuned flags | Query/TTL/replication khác |
| Managed | None | Service quotas/control plane | Throttle/restore khác |
| Drivers | Dev version | Older deployment version | Retry/codec differences |

**Đưa engine thật vào CI là bước rất mạnh, nhưng không phải giấy chứng nhận production parity.**

---

## 20. Test environment as code: pin versions và config

Một test có thể “tình cờ pass” khi máy developer dùng image tag `latest`, nhưng CI hoặc production đã chạy một release khác.

### 20.1. Pin image version

Dùng Docker image tags/digests được dự án phê duyệt. Nếu cần kiểm upgrade, chạy ma trận version rõ ràng thay vì thả nổi.

### 20.2. Pin Java driver versions

MongoDB Java Driver, DataStax/Apache Cassandra Java Driver, AWS SDK, Lettuce/Jedis và Elasticsearch/OpenSearch clients có version/default options khác.

### 20.3. Pin schema/config

Tạo indexes/tables/roles bằng migrations thật của ứng dụng. Không tạo schema test bằng hand-written shortcut thiếu validators, TTL, read concern hoặc index options.

### 20.4. Ghi topology

- Number of nodes/voters.
- Replica/shard assignments.
- Failure domains.
- Read/write settings.
- TLS/auth.
- Storage backends.
- Endpoint discovery.

### 20.5. Đừng để local default làm sai kết luận

Một test với database authentication disabled không xác minh production RBAC. Một test với replica count 1 không xác minh quorum write availability.

---

## 21. Testcontainers giúp được gì?

**Testcontainers** là cách khởi chạy các container phụ thuộc bằng code kiểm thử, thường kết hợp JUnit 5, giúp integration tests dùng database process thật mà không cần database cố định do developer tạo thủ công.

### 21.1. Ưu điểm

- Mỗi test suite có môi trường rõ.
- Lấy host/mapped port động.
- Dễ chạy trong CI có Docker-compatible runtime.
- Hạn chế phụ thuộc một database shared giữa nhiều developers.
- Dễ chạy engine version matrix.
- Tích hợp setup/teardown.
- Có thể kết hợp network/proxy containers để test lỗi.

### 21.2. Giới hạn

- Phụ thuộc container runtime và khả năng tải image.
- Startup có chi phí thời gian/CPU.
- Một container không tự là multi-node cluster.
- Không tự mô phỏng region outage, managed IAM, throttling hoặc backend storage.
- Cần tự triển khai readiness, data fixtures, schema và failure oracle đúng.

### 21.3. Đặt tên đúng

`MongoDBContainer` là **MongoDB process thật trong container**, không phải mock MongoDB. `DynamoDB Local` chạy trong container vẫn là **local implementation/emulator**, không biến thành AWS DynamoDB managed production chỉ vì Testcontainers khởi động nó.

---

## 22. Dependencies Java và JUnit 5

Một dự án Gradle Java 17 có thể cấu hình phụ thuộc kiểm thử theo phiên bản **được duyệt trong dự án**:

~~~kotlin
dependencies {
    testImplementation(platform(
        "org.junit:junit-bom:<approved-junit-version>"
    ))
    testImplementation("org.junit.jupiter:junit-jupiter")

    testImplementation(platform(
        "org.testcontainers:testcontainers-bom:<approved-tc-version>"
    ))
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:mongodb")
    testImplementation("org.testcontainers:testcontainers")

    testImplementation(
        "org.mongodb:mongodb-driver-sync:<approved-driver-version>"
    )
    testImplementation(
        "redis.clients:jedis:<approved-jedis-version>"
    )
}

tasks.test {
    useJUnitPlatform()
}
~~~

**Cú pháp các tọa độ/module và khả năng BOM phụ thuộc phiên bản Testcontainers đang dùng.** Đoạn này là cấu trúc minh họa để bạn thay bằng version và artifact names tương thích đã xác minh; không phải một `build.gradle.kts` có thể chạy nguyên xi với placeholders.

### 22.1. Vì sao không dùng `latest`?

“Cùng test” nhưng thư viện khác version có thể thay API, retry defaults, serializer và behavior. Pin giúp tái lập.

### 22.2. Chỉ dùng test-scoped credentials

MongoDB/Redis test containers dùng dữ liệu giả. Managed service integration tests phải cấp secret riêng có TTL/permissions tối thiểu.

### 22.3. Không chạy Gradle như một phần đọc bài

Mã là ví dụ để người học tích hợp vào dự án; cần điều chỉnh import/module versions theo stack thực tế.

---

## 23. Ví dụ 1 — Redis thật: kiểm tính nguyên tử của `SETNX`

Yêu cầu: trong một namespace test, hai mươi requests cùng giành một key chỉ được có **một request** tạo key thành công.

Dùng Redis process thật do Testcontainers khởi chạy.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import redis.clients.jedis.JedisPooled;

@Testcontainers
class RedisSetNxIntegrationTest {

    @Container
    static final GenericContainer<?> redis =
        new GenericContainer<>(
            DockerImageName.parse("redis:7.4")
        ).withExposedPorts(6379);

    @Test
    void onlyOneConcurrentCreateWins() throws Exception {
        String key = "it:lock:" + UUID.randomUUID();

        try (JedisPooled client = new JedisPooled(
                redis.getHost(),
                redis.getMappedPort(6379))) {

            int contenders = 20;
            ExecutorService pool =
                Executors.newFixedThreadPool(contenders);

            CountDownLatch start = new CountDownLatch(1);
            List<Future<Long>> outcomes = new ArrayList<>();

            try {
                for (int i = 0; i < contenders; i++) {
                    String requestId = "r-" + i;

                    outcomes.add(pool.submit(() -> {
                        if (!start.await(
                                10, TimeUnit.SECONDS)) {
                            throw new IllegalStateException(
                                "Start barrier timed out"
                            );
                        }

                        return client.setnx(key, requestId);
                    }));
                }

                start.countDown();

                long wins = 0;
                for (Future<Long> outcome : outcomes) {
                    if (outcome.get(
                            30, TimeUnit.SECONDS) == 1L) {
                        wins++;
                    }
                }

                assertEquals(1L, wins);
                assertNotNull(client.get(key));
            } finally {
                start.countDown();
                pool.shutdownNow();
            }
        }
    }
}
~~~

### 23.1. Điều bài test chứng minh

Trên Redis instance được khởi chạy, với cùng key và client API `SETNX`, đúng một concurrent command tạo key thành công trong lần chạy được quan sát, nếu test hoàn tất.

### 23.2. Điều bài test không chứng minh

- Key sống sau crash/power loss.
- Key đã replicate trước khi primary fail.
- Không có duplicate effects nếu lock giữ một external resource.
- Distributed lease/fencing an toàn.
- Các hash-slot/multi-key semantics của Redis Cluster.
- Kết quả tương tự dưới mọi topology/failure schedule.

### 23.3. Phiên bản và image

Tag `redis:7.4` là ví dụ cho một phiên bản được chọn. Trong pipeline thực, pin release/digest được phê duyệt, kiểm module Testcontainers/Jedis tương thích rồi ghi version vào kết quả.

### 23.4. Bước mở rộng

Test TTL, clock/expiry, failover, duplicate request IDs, stale owner epoch. Không dùng `SETNX` một mình để bảo đảm lock an toàn khi tác vụ kéo dài quá lease.

---

## 24. Ví dụ 2 — MongoDB thật: conditional update khi tranh vé cuối

Đặc tả:

> Khi chỉ còn một vé, nhiều writes có điều kiện trên cùng document chỉ cho một lần giảm `available` từ 1 xuống 0.

Ví dụ Java 17 + JUnit 5 + MongoDB synchronous driver + Testcontainers:

~~~java
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.inc;
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.*;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class MongoConditionalReservationIT {

    @Container
    static final MongoDBContainer mongo =
        new MongoDBContainer(
            DockerImageName.parse("mongo:7.0")
        );

    @Test
    void onlyOneReservationWins() throws Exception {
        try (MongoClient client =
                MongoClients.create(mongo.getReplicaSetUrl())) {

            MongoCollection<Document> inventory =
                client.getDatabase("tickets_integration")
                      .getCollection("inventory");

            String eventId = "e-" + UUID.randomUUID();

            inventory.insertOne(
                new Document("_id", eventId)
                    .append("available", 1)
                    .append("held", 0)
            );

            int contenders = 20;
            ExecutorService pool =
                Executors.newFixedThreadPool(contenders);
            CountDownLatch start = new CountDownLatch(1);

            List<Future<Long>> effects = new ArrayList<>();

            try {
                for (int i = 0; i < contenders; i++) {
                    effects.add(pool.submit(() -> {
                        if (!start.await(
                                10, TimeUnit.SECONDS)) {
                            throw new IllegalStateException(
                                "Start barrier timed out"
                            );
                        }

                        return inventory.updateOne(
                            and(
                                eq("_id", eventId),
                                gte("available", 1)
                            ),
                            combine(
                                inc("available", -1),
                                inc("held", 1)
                            )
                        ).getModifiedCount();
                    }));
                }

                start.countDown();

                long successes = 0;
                for (Future<Long> effect : effects) {
                    successes += effect.get(
                        30, TimeUnit.SECONDS);
                }

                assertEquals(1L, successes);

                Document state = inventory.find(
                    eq("_id", eventId)
                ).first();

                assertNotNull(state);
                assertEquals(
                    0, state.getInteger("available")
                );
                assertEquals(
                    1, state.getInteger("held")
                );
            } finally {
                start.countDown();
                pool.shutdownNow();
            }
        }
    }
}
~~~

### 24.1. Vì sao khác mock?

Engine thực sự thực thi filter `available >= 1` và `$inc` trên một document dưới concurrent writes. Mock đơn giản có thể trả `modifiedCount=1` cho tất cả requests, che lỗi hoặc tạo hành vi không giống engine.

### 24.2. Giới hạn quan trọng

Test này **chỉ cập nhật một inventory document**. Nó không tạo reservation ledger, không có request ID/idempotency, chưa kiểm transaction nhiều documents và chưa chứng minh hai successful API receipts không xảy ra nếu service bị lỗi.

### 24.3. Replica set trong container

`MongoDBContainer` với `getReplicaSetUrl()` cung cấp kết nối phù hợp cho các tính năng cần replica set trong cấu hình được module hỗ trợ. Điều đó không biến nó thành mô hình production nhiều voting members. Phải ghi chính xác topology mà module đã tạo.

### 24.4. Tiếp tục đến contract đầy đủ

Bổ sung transaction hoặc data model chứa receipt độc nhất; test retry sau timeout, crash ở điểm commit, client sessions, read concern và write concern.

### 24.5. Cleanup/test isolation

Tạo event ID duy nhất cho mỗi test; tùy pipeline có thể dùng database/collection riêng và xóa có kiểm soát khi suite kết thúc. Không chạy các thao tác xóa trên cluster production.

---

## 25. Contract tests: dùng chung một bộ test cho nhiều adapters

Nếu ứng dụng chuyển từ MongoDB sang DynamoDB, cần bảo vệ hợp đồng repository trước và sau khi chuyển.

~~~java
import java.math.BigDecimal;
import java.util.Optional;

public interface OrderRepository {
    Optional<Order> find(
        String tenantId,
        String orderId
    );

    boolean updateAmountIfVersion(
        String tenantId,
        String orderId,
        long expectedVersion,
        BigDecimal newAmount
    );

    record Order(
        String tenantId,
        String orderId,
        BigDecimal amount,
        long version
    ) {}
}
~~~

### 25.1. Bộ contract phải nói về behavior

- Wrong tenant không đọc được đơn.
- Unknown order trả `Optional.empty`.
- Stale version update bị từ chối.
- Successful conditional update tăng version đúng.
- Monetary precision không thay.
- Retry với cùng operation ID không nhân effect.
- Read path đáp ứng freshness contract.

### 25.2. Mỗi adapter phải chạy trên backend thích hợp

- Source adapter → MongoDB engine thật.
- Target adapter → DynamoDB Local cho API-level tests.
- Target adapter → AWS DynamoDB staging cho managed-service behaviors chưa thể xác nhận bằng local.

### 25.3. Contract test không thay design review

Nếu target GSI eventual còn source path trước đây read-your-writes, việc cả hai adapters pass basic CRUD tests không có nghĩa read-freshness contract được giữ.

---

## 26. DynamoDB Local: mạnh ở API-level, có giới hạn managed fidelity

DynamoDB Local là lựa chọn hữu ích khi muốn thử:

- AWS SDK request/response và attribute serialization.
- Table creation.
- Primary key access.
- ConditionExpressions.
- UpdateExpressions.
- Một số query, scan và transaction APIs trong phạm vi được hỗ trợ.
- Repository mapping và error handling cho các case local triển khai.
- Data fixtures không cần kết nối account AWS.

### 26.1. Không được mặc định mô phỏng

- AWS IAM authorization.
- AWS VPC endpoint/network policies.
- Real global table multi-region replication.
- Production capacity allocation/throttling.
- CloudWatch metrics/control plane behavior.
- Managed PITR/backup/restore lifecycle.
- Streams delivery semantics như môi trường managed.
- Service quotas và scale.
- Region or AZ failure.

Một số tính năng có thể được hỗ trợ một phần hoặc khác theo release; luôn đối chiếu **feature coverage của bản Local thực sự dùng**.

### 26.2. Local endpoint thường dùng HTTP

Trong môi trường test cách ly, SDK được trỏ tới local endpoint. Không áp cấu hình local endpoint hoặc dummy credentials sang production.

### 26.3. SDK setup minh họa

~~~java
import java.net.URI;

import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

public final class LocalDynamoClient {

    public static DynamoDbClient forLocal(String endpoint) {
        return DynamoDbClient.builder()
            .endpointOverride(URI.create(endpoint))
            .region(Region.US_EAST_1)
            .credentialsProvider(
                StaticCredentialsProvider.create(
                    AwsBasicCredentials.create(
                        "local-test",
                        "local-test"
                    )
                )
            )
            .build();
    }
}
~~~

Ví dụ chỉ dùng cho DynamoDB Local endpoint cách ly như `http://127.0.0.1:<mapped-port>`; credentials là dummy, không dùng cho AWS thật. Phải đóng client theo lifecycle và quản lý table cleanup của suite.

### 26.4. Managed staging test cần thực sự là managed staging

Muốn kiểm IAM deny, throttling, PITR, global tables, region failover hay service quotas, phải có những test được phép trên AWS account/region thử nghiệm với resource và budget controls.

---

## 27. LocalStack: service simulation không đồng nghĩa AWS semantics đầy đủ

LocalStack có thể hữu ích khi một integration flow đi qua nhiều AWS-style APIs như SQS, SNS, DynamoDB và S3 trong cùng local environment.

### 27.1. Giá trị

- SDK endpoint wiring.
- Event-driven flow smoke tests.
- Request format và service orchestration trong phần được triển khai.
- Test không phụ thuộc tài khoản cloud cho những trường hợp cơ bản.

### 27.2. Cần ghi version/edition/config

Feature support và fidelity phụ thuộc phiên bản, edition, resource configuration và cụ thể API đang gọi.

### 27.3. Không suy được từ test xanh

Một SQS→Lambda→DynamoDB flow chạy trên mô phỏng không chứng minh IAM policies, throughput, retries, ordering, DLQ và failure domains sẽ giống AWS managed thật.

### 27.4. Test matrix

Mỗi feature phải được ghi:

~~~text
Feature: conditional DynamoDB update
Local emulator: PASS in version X
Managed staging: PASS in region Y
Production assumption: same API contract, monitored

Feature: IAM Deny on target table
Local emulator: NOT REPRESENTATIVE
Managed staging: REQUIRED
~~~

### 27.5. Không dùng emulator để xác nhận compliance

Chính sách network/data residency, encryption keys, audit và authorization phải được kiểm trên hạ tầng thực hoặc được review bằng chứng từ provider phù hợp.

---

## 28. Cassandra: một node thật không đại diện consistency toàn cụm

Cassandra rất phụ thuộc partition keys, replication factor, consistency level và trạng thái peers.

### 28.1. Tests phù hợp trên một node

- CQL schema migrations.
- Serialization/codec mapping.
- Partition/clustering key ordering.
- Basic reads/writes.
- Conditional/LWT behavior trong phạm vi môi trường.
- TTL/tombstone behavior theo cấu hình.
- Driver prepared statements/connection basics.

### 28.2. Tests cần nhiều nodes/DC

- `ONE`, `QUORUM`, `LOCAL_QUORUM` với replica placement phù hợp.
- Unavailable replicas.
- Coordinator failure.
- Hints, repair, streaming.
- Consistency under partitions.
- Node rejoin sau offline.
- Tombstone/repair horizon.
- Schema agreement.
- Multi-DC failure modes.

### 28.3. Tránh hiểu nhầm `R+W>N`

Quorum overlap có giá trị với nhiều mô hình, nhưng không tự chứng minh linearizability của mọi thao tác CQL, đặc biệt conditional writes và multi-partition workflow có semantics riêng.

### 28.4. Container đơn nút chưa giải quyết cluster test

Một `CassandraContainer` hoặc `GenericContainer` đủ để test CRUD/CQL, nhưng muốn thử RF=3 hay DC failover phải tổ chức topology thật phù hợp. Driver/contact points/datacenter routing cũng cần được kiểm.

### 28.5. LWT và race

Test hai clients tranh cùng điều kiện tại phân vùng thực với `IF`, kiểm kết quả applied và business invariant, rồi mở rộng vào failover/network faults khi contract yêu cầu.

---

## 29. MongoDB: phân biệt standalone, replica set và sharded cluster

### 29.1. Standalone process

Tốt cho nhiều CRUD/query/index/serialization tests, nhưng không phù hợp để kiểm replica election, rollback và những feature đòi replica set.

### 29.2. Replica set

Cho phép thử read preference, sessions, majority write concerns, change streams và transactions trong phạm vi cấu hình được hỗ trợ.

### 29.3. Multi-member replica set

Cần thiết khi muốn kiểm election, secondary lag, stepdown, majority availability và unknown commit outcomes.

### 29.4. Sharded cluster

Cần thiết khi bất biến phụ thuộc shard key, routing, distributed transactions, chunk movement hoặc metadata.

### 29.5. Chú ý index và collation

Unit fake thường không mô phỏng unique partial indexes, collation hoặc aggregation pipelines. Đây là lý do mạnh để dùng engine thật sớm.

### 29.6. Change Streams

Chỉ có thể tin kết quả resume/failover sau khi test trên topology hỗ trợ và thực sự inject fault thích hợp. Mock listener luôn đúng thứ tự không cung cấp bằng chứng tương đương.

---

## 30. Redis: server thật, Sentinel và Cluster là ba phạm vi

### 30.1. Server standalone

Có thể kiểm RESP protocol, atomic commands, Lua scripts, data structures, TTL và persistence configuration ở một server.

### 30.2. Replication và failover

Để kiểm promotion làm mất/giữ writes thế nào, cần primary/replica topology và failure injection.

### 30.3. Redis Sentinel

Kiểm primary discovery, failover/quorum của Sentinel, client reconnect behavior.

### 30.4. Redis Cluster

Kiểm hash slots, `MOVED`/`ASK`, multi-key restrictions, resharding và per-slot availability.

### 30.5. `SETNX` không phải fencing

Một lock có TTL không đảm bảo stale holder không tiếp tục tác động external resource. Nếu yêu cầu là mutual exclusion của side effect, cần epoch/fencing tại nơi nhận write.

### 30.6. RDB/AOF/ACK

Một test Lua script thành công trước crash không chứng minh durability. Kiểm persistence/replication/failover settings theo RPO contract và lưu trace.

---

## 31. Elasticsearch/OpenSearch: query, refresh và cluster health

### 31.1. Engine thật cần cho

- Analyzer và mapping.
- Tokenization, normalization.
- Numeric/date/text/keyword fields.
- Nested queries.
- Sort/facets/aggregations.
- Index aliases.
- Refresh visibility.
- Optimistic concurrency/version handling.
- Index templates/pipelines.

### 31.2. Một node không đại diện shard movement

Single-node container có thể trả đúng search results nhưng không kiểm replica allocation, node failure, shard relocation và cluster-manager election.

### 31.3. Read model freshness

Một successful indexing response không đồng nghĩa search nhìn thấy document ngay. Test theo refresh policy/watermark, không buộc “search instant” nếu contract không yêu cầu.

### 31.4. Đừng dùng embedded Lucene như toàn bộ Elasticsearch

Lucene API không thay Elasticsearch/OpenSearch REST layer, distributed query, analyzers config, mappings, aliases và shard coordination của deployment thật.

### 31.5. Dữ liệu lớn

Một index 500 documents không phát hiện hiệu quả truy vấn kém với hàng chục triệu documents, merges, disk watermarks và ingestion bursts.

---

## 32. Couchbase: transaction/CAS, indexes và services

Couchbase có KV/document operations, CAS, SQL++/query, indexing, multiple services và cluster features.

### 32.1. Điều cần real-engine integration

- CAS update/replace.
- KV operations/codec.
- Query indexes.
- Durability settings.
- TTL/expiration.
- Document sizes.
- Transactions trong phạm vi hỗ trợ.
- SDK node discovery và routing.

### 32.2. Điều cần multi-node

- Rebalance.
- Failover.
- Replica placement.
- vBucket ownership.
- Warm-up.
- Service availability khi một member mất.

### 32.3. Không gọi một HTTP mock là Couchbase test

Nếu mock trả JSON giống Query API, nó không xác minh index freshness, KV consistency hay CAS conflicts.

### 32.4. Version-specific behavior

Ghi Couchbase Server/SDK versions, enabled services và capabilities thay vì suy một tên sản phẩm bảo đảm mọi feature.

---

## 33. Dữ liệu kiểm thử phải đủ thực tế để làm lộ lỗi

Một bộ fixtures nên gồm:

- Record bình thường.
- Legacy schema versions.
- Missing vs null.
- Number/decimal overflow và precision.
- Unicode/UTF-8/collation variants.
- Nested arrays/empty collections.
- Max-size gần giới hạn.
- Large partitions/hot keys.
- Same timestamp khác IDs.
- Multi-tenant cùng logical IDs.
- Soft-deleted, TTL-near-expiry.
- Data đang thay đổi trong lúc paginate.
- Duplicate idempotency keys.
- Out-of-order event versions.
- Records bị update/cancel cùng lúc.
- Invalid/expired credentials trong security tests.

### 33.1. Synthetic data không phải random thuần

Nên có phân phối skew, peak values và ngoại lệ đã quan sát ở production qua metadata đã được phê duyệt. Uniform random data có thể không tạo hot partitions.

### 33.2. Không lấy raw PII làm fixture

Dùng synthetic/masked data. Nếu dùng data subset thật theo policy, cần tách account, KMS, retention, permissions, logging.

### 33.3. Fixture phải tương thích migration

Nếu schema production có partial indexes, validators, TTL và ACL, fixture setup phải tạo chúng qua migration script thực.

---

## 34. Seed, trạng thái ban đầu và cleanup

### 34.1. Determinism

Tạo ID theo test namespace + random seed được ghi lại, dùng controllable clocks cho business TTL.

### 34.2. Không phụ thuộc test order

Test A không được dựa vào dữ liệu còn sót từ Test B. Nếu dùng shared container, mỗi test có database/table/keyspace/prefix riêng hoặc fixture reset.

### 34.3. Cleanup có thể thất bại

Khi assertion fail, vẫn cần finally/teardown; nhưng không xóa chứng cứ quan trọng trước khi trace được lưu.

### 34.4. Không chạy destructive cleanup nhầm môi trường

Sử dụng sentinel guard, endpoint allowlist, test credentials và resource naming. Một `dropDatabase` trong integration suite phải **không thể trỏ nhầm production**.

### 34.5. Container reuse

Reuse có thể giảm thời gian startup nhưng tăng nguy cơ state leakage nếu không reset. Các test critical nên ưu tiên isolation và ghi rõ reuse policy.

---

## 35. Testcontainers trong CI: điều kiện tiên quyết

- Docker-compatible runtime thực sự khả dụng.
- Images có thể tải từ approved registry/mirror.
- Resource limits đủ CPU/RAM/disk/network.
- Testcontainers/JUnit/driver versions tương thích.
- Test runner được cấp quyền container nhưng không quá rộng.
- Không gắn production credentials vào môi trường CI không cần thiết.
- Startup probes/timeout phù hợp engine.
- Log/artifacts được thu khi fail.
- Cleanup sau test và sau job bị hủy.

### 35.1. Nếu CI không hỗ trợ containers

Không đổi test thành mock và tiếp tục báo “integration passed”. Đánh dấu `SKIPPED_INFRA`/`NOT_RUN`, báo thiếu bằng chứng và dùng môi trường integration chuyên biệt.

### 35.2. Quota

Cassandra/Elasticsearch nhiều nodes tốn tài nguyên; có thể chạy trong nightly lane thay vì mọi PR.

### 35.3. Image security

Pin versions, hạn chế privileged Docker features và kiểm container image supply chain theo chính sách công ty.

### 35.4. Thời gian chờ không là bất biến cố định

Startup time tăng trong CI chậm; sử dụng readiness phù hợp, không `Thread.sleep(30000)` rồi hy vọng.

---

## 36. Mô hình CI nhiều tầng

~~~mermaid
flowchart TD
    PR["Pull request"] --> U["Unit/model/mock tests"]
    U --> I["Real single-node Testcontainers"]
    I --> C["Real engine contract tests"]
    C --> R["Release candidate"]
    R --> N["Nightly multi-node/fault tests"]
    R --> M["Managed staging integration"]
    N --> G["Go/no-go evidence"]
    M --> G
    G --> D["Controlled deployment"]
    D --> P["Runtime reconciliation/monitoring"]
~~~

### 36.1. PR fast lane

Pure business rules, converters, repository mock tests, one-node engine tests có thời gian vừa phải.

### 36.2. Nightly lane

Multi-node, partition, leader failover, repair, long-running CDC, stress/soak.

### 36.3. Release lane

Managed staging permissions, TTL/Streams/PITR, capacity, realistic load, backup/restore và security checks.

### 36.4. Production canary

Không cố ý gây mất quorum hoặc xóa dữ liệu production để “kiểm thử”. Canary có phạm vi nhỏ, quyền hạn và rollback rõ.

### 36.5. Báo cáo lane thiếu

Một PR có thể pass mock nhưng multi-node nightly đang fail; release gate phải phản ánh chính sách cho invariant critical.

---

## 37. Test oracle: tránh tự khẳng định bằng cùng bug

Một service Java dùng mapper lỗi `BigDecimal -> double`. Nếu integration test đọc target bằng đúng mapper ấy rồi so với object trước khi serialize, hai phía có thể cùng lỗi/rounding.

### 37.1. Canonical domain representation

Dùng rules đã duyệt:

~~~text
orderId: canonical string
amountMinor: exact integer
currency: ISO code
createdAt: UTC instant with required precision
tenant: authenticated scope
version: monotonic counter
deleted: explicit lifecycle status
~~~

### 37.2. Nguồn độc lập

- Provider receipts cho payment.
- Reservation ledger cho inventory.
- Database-native query với consistency thích hợp.
- Immutable event history khi cần chứng minh transitions.
- A second implementation của invariant checker nếu rủi ro cao.

### 37.3. Snapshot consistency

Không cộng counters đọc ở nhiều shards ở những thời điểm khác nhau rồi tuyên bố conservation bị phá. Cần consistent cut/transaction snapshot/committed event replay.

### 37.4. Unknown không phải pass

Nếu source lag cao hoặc history bị mất, không có cơ sở chứng minh invariant. Kết luận test phải ghi `UNKNOWN` và nguyên nhân.

---

## 38. Concurrency tests: không chỉ gọi nhiều threads

### 38.1. Start barrier

Cho nhiều clients thực sự tranh cùng key. Nếu calls bắt đầu tuần tự, bug read-modify-write có thể không xuất hiện.

### 38.2. Multiple Java clients

Một test dùng chung singleton process có thể vẫn được bảo vệ bởi JVM lock. Cần test nhiều instances/clients để loại bỏ giả định local serialization.

### 38.3. Targeted interleavings

Chèn delay giữa read và write, sau commit trước ACK, hoặc giữa transaction commit và event publish qua fault proxy/harness.

### 38.4. Stateful model

Kiểm cả kết quả, state cuối, sequence transitions, idempotency ledger.

### 38.5. Repetition và seed

Lặp nhiều lịch khác nhau; lưu seed, trace, image digest và network schedule để tái lập.

### 38.6. Không gắn một lần test xanh thành chứng minh

Concurrency bug có thể hiếm. Dùng property-based/model testing, formal reasoning và production safeguards ở những invariant critical.

---

## 39. Fault injection: những mốc nào cần tạo lỗi?

Một write:

~~~text
A client sends request
B server receives
C server commits local state
D replicas acknowledge per policy
E server sends ACK
F client receives ACK
G CDC event is consumed
H external side effect completes
~~~

Các tình huống:

| Mốc | Fault | Bất biến cần kiểm |
|---|---|---|
| Trước B | Packet drop | Không phát effect nếu request không tới |
| Giữa B và C | Process crash | Transaction rollback/recovery đúng |
| Sau C trước F | Lost response | Unknown outcome + idempotent retry |
| Trước D | Replica unavailable | ACK/durability theo consistency |
| Sau D | Leader crash | Acknowledged writes survive theo contract |
| Giữa F và G | CDC lag/restart | Replay không mất events |
| Sau G trước H | Consumer crash | Không bỏ qua intent |
| Sau H trước consumer ACK | Duplicate redelivery | Không nhân side effect |
| Sau backup trước restore | Delete request | Không hồi sinh dữ liệu trái policy |

### 39.1. Proxy giúp gì?

Có thể dùng network proxy hỗ trợ thêm latency, drop/reset connections. Nhưng proxy chỉ tác động đúng các connections đi qua nó; không tự tạo filesystem corruption hoặc engine election.

### 39.2. Clock skew

Cần thận trọng: chỉnh clock có thể ảnh hưởng certificates, TTL và hệ điều phối. Chỉ thử trong isolated test nodes được phê duyệt.

### 39.3. Unknown write result là trạng thái thật

Timeout không cho phép client suy “chắc chắn rollback”. Test oracle phải tra authoritative ledger.

### 39.4. Fault test cần safety bounds

Không chạy destructive fault trên production ngoài chương trình đã được cấp phép; giới hạn scope, cleanup, resource budget và incident escalation.

---

## 40. Khác biệt giữa lỗi network và lỗi DB

Một client có thể thấy:

~~~text
ConnectTimeout
TLS handshake failure
ReadTimeout
ServerSelectionTimeout
ConditionalCheckFailed
NotPrimary / leader moved
UnprocessedItems
Throttling
TransactionConflict
~~~

Không phải tất cả lỗi có cùng semantics.

### 40.1. Connection failure trước khi gửi

Có thể xác định request chưa rời client nếu có bằng chứng; nhưng nếu chưa biết byte nào đã gửi, cần thận trọng.

### 40.2. Timeout sau gửi

Write có thể đã commit; `UNKNOWN` là outcome phù hợp nếu không có receipt chắc chắn.

### 40.3. Conditional conflict

Một điều kiện không thỏa là reject xác định, không tự retry vô hạn cùng stale version.

### 40.4. Throttling

Có thể retry với bounded backoff/jitter trong deadline, nhưng tăng tải không giới hạn sẽ gây retry storm.

### 40.5. Mock error tests vẫn hữu ích

Dùng mock để kiểm Java policy cho từng error class. Sau đó bổ sung real integration tests để xác minh **driver/engine thật trả error nào** dưới tình huống đó.

---

## 41. Consistency tests cần một hợp đồng rõ

### 41.1. Read-your-writes

Sau successful write, cùng session có phải thấy giá trị mới trong read path đã định không?

### 41.2. Monotonic reads

Một client đã thấy version 8 có được đọc lại version 6 không?

### 41.3. Linearizability

Nếu cần một register/lock/atomic condition hoạt động như một thứ tự thao tác nguyên tử tôn trọng real-time order, cần kiểm operation history với checker/abstract model phù hợp.

### 41.4. Eventual convergence

Sau khi writes dừng và network/replay bình thường, các replicas/projections có hội tụ trong thời gian policy không?

### 41.5. Không đánh đồng consistency với freshness SLO

Một eventual projection có p99 lag dưới 5 giây không tự có linearizable reads. Ngược lại, một quorate write có thể an toàn nhưng tạm không available khi mất quorum.

### 41.6. Oracle theo version/watermark

Đo causal/session tokens, commit indexes hoặc source versions nếu engine có contract. Wall-clock timestamps một mình có thể không đủ.

---

## 42. Test linearizability trên engine thật

Một lịch sử tối thiểu:

~~~text
write(x=5) invoked at t1, returned success at t2
read(x) invoked at t3 > t2, returned 3 at t4
~~~

Nếu không có write hợp lệ khác xen vào và contract là linearizable, đó là counterexample.

### 42.1. Thu đủ history

Client ID, operation ID, invoke/response events, key, result, node endpoint và failure context.

### 42.2. Đồng hồ

`System.nanoTime()` dùng để đo thời gian trong một process, không thể so trực tiếp origin giữa machines khác. Dùng tracer với clock bounds/causal relationships hoặc collector phù hợp.

### 42.3. Histories có UNKNOWN

Nếu write timeout, checker có thể phải xét khả năng nó đã commit. Không tự gán unsuccessful.

### 42.4. Engine-level guarantee thay đổi theo operation

Không suy toàn bộ MongoDB/Cassandra/DynamoDB/Redis có một consistency semantics duy nhất cho mọi query/transaction.

### 42.5. Khi nào cần công cụ chuyên dụng?

Hệ có yêu cầu cao có thể dùng model/history checker theo phong cách Jepsen/Elle hoặc custom state-machine harness, nhưng phải hiểu checker assumptions và scope. Công cụ không thay đặc tả đúng.

---

## 43. Sử dụng emulator đúng cách: luôn có Limitations Ledger

Bên cạnh mỗi suite, lưu một file/bảng theo format minh bạch:

~~~yaml
suite: dynamodb-local-order-contracts
tested:
  sdk: aws-sdk-java-v2
  engine: DynamoDB Local
  mode: isolated-container
  operations:
    - GetItem
    - UpdateItem with condition
    - TransactWriteItems within tested limits
  observations:
    - "No stale-version write was accepted in tested runs"
notProven:
  - IAM enforcement in AWS
  - realistic provisioned/on-demand throttling
  - global tables conflicts
  - PITR and region recovery
  - actual service availability SLO
followUps:
  - aws-staging-iam-deny-tests
  - aws-staging-throttle-budget-tests
  - cross-region-drill
result: "API_CONTRACT_PARTIALLY_VERIFIED"
~~~

### 43.1. Có version và ngày

Emulator cập nhật liên tục; thay version có thể thay feature coverage. Đừng dùng một bảng kiểm kê từ nhiều năm trước rồi tuyên bố hiện hành.

### 43.2. Có owner

Ai chịu trách nhiệm chạy follow-up test? Khi nào? Có release blocker không?

### 43.3. Nêu giới hạn riêng từng feature

Một test DynamoDB Local có thể đáng tin cho `ConditionExpression` nhưng không có giá trị cho IAM resource policy. Không gộp “emulator đúng 90%” vì tỷ lệ này không có nghĩa kỹ thuật rõ.

---

## 44. Các trạng thái kiểm thử cần phân biệt

| Status | Nghĩa | Có được tính PASS? |
|---|---|---|
| `PASS` | Đã kiểm đúng oracle trong phạm vi test | Có, chỉ phạm vi đó |
| `FAIL` | Có counterexample/vi phạm quan sát | Không |
| `UNKNOWN` | Không đủ bằng chứng kết luận | Không |
| `NOT_RUN` | Test chưa chạy | Không |
| `SKIPPED_INFRA` | Thiếu Docker/cluster/account quyền | Không |
| `NOT_COVERED` | Test không chứa scenario cần thiết | Không |
| `NOT_REPRESENTATIVE` | Môi trường không mô phỏng behavior đang khẳng định | Không |
| `FLAKY_UNRESOLVED` | Lỗi không ổn định chưa root cause | Không coi như an toàn |
| `EXPECTED_REJECT` | Engine từ chối đúng một negative case | Có thể pass nếu oracle yêu cầu reject |

### 44.1. Tên status không thay evidence

Một row `PASS` phải có test ID, scope, version, oracle, seed/traces và thời điểm chạy.

### 44.2. Không “tạm PASS” vì deadline

Nếu chưa thử managed IAM/region behavior, hãy ghi `NOT_COVERED` với risk acceptance/owner, không tô xanh giả.

### 44.3. Phân loại flaky

Một concurrency test đôi khi fail có thể đã tìm được race. Giữ counterexample và trace; không tăng retries của test để che nó.

---

## 45. Báo cáo fidelity theo từng invariant

Ví dụ:

| Invariant | Mock | Real single-node | Real cluster | Managed staging |
|---|---|---|---|---|
| Negative quantity rejected | PASS | PASS | Không bắt buộc | Không bắt buộc |
| MongoDB atomic decrement | Không chứng minh | PASS | PASS cần bổ sung fault | N/A |
| No double charge after unknown timeout | Policy test | Partial | Fault test | Provider sandbox reconciliation |
| Cassandra quorum availability | Không chứng minh | NOT_REPRESENTATIVE | REQUIRED | Tùy deployment |
| DynamoDB IAM tenant policy | Mock path only | DynamoDB Local: NOT_REPRESENTATIVE | N/A | REQUIRED |
| Redis key TTL deletion behavior | Fake clock rule | PARTIAL | Cluster/failover riêng | Managed semantics riêng |
| MongoDB Change Streams failover | Listener mock | Partial | REQUIRED | Managed test nếu có |
| Search index freshness | Expected map only | Real index + refresh | Scale/replica tests | Managed integration tùy scope |
| Node recovery/RPO | Không | Crash recovery partial | REQUIRED | DR drill |

“PARTIAL”, “REQUIRED” là cách ghi coverage, không phải nhãn kết quả test được phép dùng thay PASS/FAIL. Có thể chuẩn hóa thành `NOT_COVERED` và kèm follow-up.

---

## 46. Chiến lược chạy test không làm CI quá chậm

### 46.1. Reuse container theo suite

Static `@Container` có thể chia chi phí startup cho nhiều tests trong một class. Tuy nhiên cần isolation từng test.

### 46.2. Tách tests theo nguy cơ

Fast PR lane cho engine CRUD/index/CAS quan trọng; nightly cho multi-node/faults; release candidate cho managed tests.

### 46.3. Parallelism có giới hạn

Nhiều container heavy chạy đồng thời có thể làm CI swap/OOM, gây false timeout. Đặt resource budget cho suite.

### 46.4. Test fixtures có thể pre-seed

Dùng schema migration và generated datasets được kiểm; tránh chia sẻ backup trạng thái đã bị làm bẩn từ suite khác.

### 46.5. Cache image có kiểm soát

Mirror/internal registry giúp ổn định pipeline; vẫn pin digest và kiểm security policy.

### 46.6. Không xóa test critical để giảm build time

Thay bằng lane phù hợp và gating rõ; giữ evidence về coverage.

---

## 47. Metrics của chính test harness

Một harness cần quan sát **độ tin cậy của bài test**:

- Container startup time và failure.
- Readiness retry count.
- Driver connect/server selection time.
- Successful/failed operations.
- Unknown outcomes.
- Oracle execution time.
- Test data size.
- Concurrency and fault schedule.
- Lost traces/events.
- Assertion failures.
- Cleanup failures.
- CPU/memory/disk pressure của test DB.
- Image/driver/config versions.
- Number of cases actually executed.

### 47.1. Một test bị skip không thành success

Nếu Docker unavailable và JUnit tự skip suite, dashboard phải hiển thị coverage gap.

### 47.2. Traces mất thì kết luận yếu đi

Một chaos test có thể chạy xong nhưng mất request history ở thời điểm crash. Nếu mục tiêu là chứng minh không double charge, thiếu history là `UNKNOWN`, không PASS.

### 47.3. Test infrastructure có thể là nguyên nhân

CI node bị OOM làm database chết không giống một fault đã lập kế hoạch. Vẫn là tín hiệu hữu ích, nhưng cần phân biệt infra error với correctness violation.

---

## 48. Error-handling tests: cách kết hợp mock và engine thật

Một pattern thực tế:

1. Dùng mock để kiểm service **sẽ làm gì** khi `WriteConflict`, throttling hoặc `UNKNOWN`.
2. Dùng real engine để kiểm **driver thật tạo ra trường hợp đó thế nào**.
3. Dùng fault injection để tạo timeout/connection reset quanh commit.
4. Dùng operation ledger/authoritative read để phân loại outcome.
5. Kiểm retry budget/idempotency.
6. Chạy lặp nhiều lần dưới concurrency.
7. Ghi lại trường hợp chưa mô phỏng được.

### 48.1. Không phải mọi lỗi đều dễ tạo

Một managed service có thể khó ép đúng internal leader failover mà không có provider hooks. Khi không tạo được, báo limitation và dùng hợp đồng/phân tích có bằng chứng bổ sung.

### 48.2. Chọn negative cases

- Wrong tenant.
- Stale version.
- Invalid index/key.
- Untrusted TLS certificate.
- Missing permission.
- Unsupported query shape.
- Oversized item.
- Throttle.
- Duplicate request ID.
- Expired token.
- Unexpected schema version.

### 48.3. Đo cả hiệu ứng không mong muốn

Một request bị từ chối phải không gây business state mutation ngoài phạm vi được cho phép, không chỉ nhận đúng error string.

---

## 49. Ma trận 40 kịch bản cho integration/fidelity

| ID | Test | Môi trường tối thiểu phù hợp | Oracle / giới hạn |
|---|---|---|---|
| I01 | MongoDB null vs missing field | MongoDB real | Filter/mapping đúng |
| I02 | BSON Decimal128 round-trip | MongoDB real | Exact amount |
| I03 | MongoDB compound index sort | MongoDB real | Order/tie-break/index |
| I04 | MongoDB unique partial index | MongoDB real | Duplicate rejection |
| I05 | MongoDB `$inc` last ticket | MongoDB real | One successful update |
| I06 | MongoDB multi-document rollback | Replica-set test | No partial commit |
| I07 | MongoDB stepdown during commit | Multi-member replica set | Unknown outcome/retry |
| I08 | MongoDB Change Streams resume | Replica set + fault | No missing/duplicate effect |
| I09 | Cassandra CQL mapping | Cassandra real | Partition/clustering representation |
| I10 | Cassandra LWT concurrent conflict | Cassandra real | Applied result/CAS |
| I11 | Cassandra `LOCAL_QUORUM` loss | Multi-node/DC topology | Read/write contract |
| I12 | Cassandra offline stale replica | Real cluster/controlled rejoin | No zombie data |
| I13 | DynamoDB condition expression | DynamoDB Local + AWS staging | API semantics; managed tests separate |
| I14 | DynamoDB item size boundary | AWS staging or verified local API support | Correct rejection |
| I15 | DynamoDB GSI read after write | AWS staging | Eventual visibility contract |
| I16 | DynamoDB IAM deny | AWS staging | Access denied |
| I17 | DynamoDB throttle/retry | AWS staging/bounded scenario | Retry budget |
| I18 | DynamoDB PITR restore | AWS staging/DR | Restore table/data/config |
| I19 | DynamoDB global-table conflict | Multi-region managed staging | Conflict policy |
| I20 | Redis SETNX race | Redis real single node | Exactly one create |
| I21 | Redis Lua atomic update | Redis real | State invariant |
| I22 | Redis TTL/expiry behavior | Redis real | Logical expiry vs physical cleanup |
| I23 | Redis async failover | Primary/replica topology | Acked-write risks |
| I24 | Redis Cluster MOVED/ASK | Redis Cluster | Client routing |
| I25 | Redis multi-key cross-slot | Redis Cluster | Correct restriction/error |
| I26 | Elasticsearch text mapping | Elasticsearch real | Analyzer results |
| I27 | Elasticsearch refresh visibility | Elasticsearch real | Search freshness |
| I28 | Elasticsearch shard relocation | Multi-node search cluster | Availability/consistency |
| I29 | Couchbase CAS conflict | Couchbase real | Stale version rejected |
| I30 | Couchbase rebalance | Multi-node Couchbase | Service/placement eligibility |
| I31 | Concurrent same request ID | Real authority + ledger | At-most-once effect |
| I32 | Commit succeeds, response lost | Real DB + fault proxy | UNKNOWN/reconciliation |
| I33 | Tenant A reads B document | Real API/DB role context | Zero exposure |
| I34 | Expired session still present | Real DB + app clock | Denied despite cleanup lag |
| I35 | CDC old event after new event | Real stream + projection | Monotonic version |
| I36 | Delete followed by old backfill | Real target + ledger | No resurrection |
| I37 | Source/target count equal, IDs differ | Real stores + checker | Detect mismatch |
| I38 | Replica reads lag | Multi-node real cluster | Freshness contract |
| I39 | Restore from snapshot | DR/staging restore | Data invariants and RPO/RTO |
| I40 | Emulator test pass but managed gap | Local + managed comparison | Explicit limitation report |

Không yêu cầu một suite chạy đủ 40 kịch bản mỗi pull request. Phân bổ theo tầng, severity và khả năng môi trường; critical uncovered cases phải xuất hiện trong release report.

---

## 50. Một hồ sơ test đầy đủ

Mẫu lưu kết quả:

~~~yaml
id: IT-ORDER-CAS-007
businessInvariant: no-lost-update
owner: order-platform
codeRevision: <git-sha>
testSuiteRevision: <git-sha>
environment:
  engine: MongoDB
  image: "mongo:<approved-version>"
  driver: "<approved-driver-version>"
  topology: single-member-replica-set
  storage: ephemeral-container-volume
  tls: test-configuration
  writeConcern: "explicitly-recorded"
  readConcern: "explicitly-recorded"
data:
  entities: 10000
  tenantCohorts: 20
  hotKeyDistribution: skewed
workload:
  clients: 20
  durationSeconds: 60
  randomSeed: 847201
faults:
  - none
oracle:
  source: authoritative-state-plus-request-history
  predicate: "no stale CAS accepted"
outcome: PASS
limitations:
  - "No multi-member failover"
  - "No region fault"
artifacts:
  - redacted-operation-history
  - container-logs
  - invariant-report
~~~

### 50.1. Không tạo SHA/version giả

Những placeholders cần được công cụ thực thi ghi bằng giá trị quan sát. Không điền tên môi trường production khi test chạy local.

### 50.2. Lưu error types

Nếu test fail, artifact phải chứa nguyên nhân, failure context và steps để reproduce, không chỉ `AssertionError`.

### 50.3. Redaction

Không lưu credentials, PII, TLS private key hoặc access tokens trong artifacts.

---

## 51. Từ `PASS` sang release decision

Một release checklist nên hỏi:

- Các business-critical invariants có test tương ứng không?
- Test nào chỉ chạy mock/fake?
- Test nào chạy engine thật?
- Test nào cần topology multiple members?
- Test managed behavior nào chưa chạy?
- Môi trường có đúng version/config chưa?
- Có tests về concurrency, retries, unknown outcomes không?
- Có đủ data distributions và hot keys không?
- Data correctness checker có độc lập không?
- Có test xóa/quyền/tenant isolation không?
- Backup/restore/failover đã được thử theo release risk chưa?
- Có flaky/unresolved failures không?
- Có owner/risk acceptance cho gaps không?
- Test artifacts có thể tái lập không?

### 51.1. Không phải mọi gap đều ngăn release

Một test multi-region DR chưa chạy có thể được một tổ chức chấp nhận rủi ro cho tính năng không critical, nhưng gap liên quan duplicate payment hoặc cross-tenant leakage thường phải block. Quyết định thuộc risk owner, không do framework tự suy.

### 51.2. Không thay scope bằng tỷ lệ

“98% tests pass” có thể che 2% còn lại là các safety-critical tests. Báo cáo cần trọng số theo invariant severity và coverage.

---

## 52. Runbook: đưa một repository từ mock sang integration thực

### Pha A — Xác định hợp đồng

1. Liệt kê repository methods.
2. Gắn business invariant cho từng method critical.
3. Phân loại query/atomicity/consistency/transaction behavior.
4. Ghi input/output/error contract.
5. Chọn authoritative oracle.

### Pha B — Chọn môi trường

6. Nếu là pure mapping logic, dùng unit/mock test.
7. Nếu phụ thuộc query/index/CAS, dùng real engine.
8. Nếu phụ thuộc replica/quorum, dùng multi-node.
9. Nếu phụ thuộc managed IAM/PITR/global tables, dùng managed staging.
10. Ghi những behavior emulator không đại diện.

### Pha C — Dựng test harness

11. Pin engine/driver versions và schema migrations.
12. Dùng Testcontainers/isolated resources nếu phù hợp.
13. Cấu hình endpoints, TLS, auth và connectivity.
14. Seed synthetic data và legacy cohorts.
15. Bảo đảm teardown không thể xóa production.
16. Thu logs/trace/seed/version.

### Pha D — Viết tests

17. Basic CRUD/query/serialization.
18. Unique/index/TTL.
19. Atomic/CAS/transaction.
20. Concurrent races và retry after timeout.
21. Failover/replication ở môi trường topology cao hơn.
22. Security negative cases.
23. CDC/restore/reconciliation khi contract có yêu cầu.

### Pha E — Đánh giá bằng chứng

24. Kiểm oracle độc lập.
25. Phân loại PASS/FAIL/UNKNOWN/NOT_COVERED.
26. Ghi mốc/version/fidelity.
27. Gắn owner và follow-up cho limitations.
28. Đưa vào CI lanes thích hợp.
29. Chỉ tuyên bố những bảo đảm nằm trong phạm vi đã thử.

---

## 53. Khi một integration test fail: chẩn đoán có hệ thống

| Triệu chứng | Nhóm nguyên nhân | Bằng chứng cần tìm |
|---|---|---|
| Container không start | Docker/image/resource | Startup logs, exit code |
| DB ready chậm | Recovery/initialization | Health logs và timeouts |
| Driver không kết nối | Host/mapped port/DNS | Runtime endpoint |
| TLS fail | Truststore/SAN/certificate | Handshake errors |
| Auth fail | User/role/secret | DB security logs |
| Migration DDL fail | Version/schema incompatibility | Applied schema/version |
| Query trả khác | Null/collation/index semantics | Actual query + fixture |
| Concurrent CAS fail | Race/incorrect condition | Request history/version |
| Timeout rải rác | Pool/CPU/IO/network | Client/DB metrics |
| CDC không ra event | Topology/feature/consumer | Source stream config |
| Count mismatch | Snapshot lag/write race | Watermarks/IDs |
| Emulator pass, managed fail | Missing managed behavior | Feature coverage ledger |
| Chỉ CI fail | Resource/scheduler/config | CI vs local environment |
| Failover test bị skip | One-node topology | Test definition/gap |
| Oracle mất trace | Instrumentation error | Capture pipeline logs |
| Cleanup fail | Leaked namespace/permissions | Resource inventory |

### 53.1. Không sửa bằng tắt verification

Ví dụ TLS certificate mismatch cần sửa SAN/trust, không đặt `trustAll=true`. Một test security fail là thông tin cần giữ.

### 53.2. Không tăng timeout mù quáng

Nếu test fail vì query scan chậm, tăng timeout có thể chỉ che vấn đề. Điều tra query/index, load và environment resources.

### 53.3. Không chuyển test về fake để “ổn định”

Nếu engine test tìm lỗi thật, thay nó bằng mock khiến coverage yếu đi. Có thể tách flaky infrastructure issue và correctness issue, nhưng phải giữ mục tiêu kiểm.

---

## 54. Bài tập 1 — Lập Fidelity Matrix cho một ứng dụng

Ứng dụng dùng:

~~~text
Java Order API -> MongoDB
Redis -> idempotency cache
Kafka -> events
Elasticsearch -> search
Payment provider -> capture/refund
~~~

Yêu cầu:

1. Liệt kê 10 business invariants.
2. Với mỗi invariant, chọn mock, real one-node, real cluster hoặc managed staging.
3. Giải thích vì sao một tầng thấp không đủ.
4. Ghi oracle và dữ liệu cần thu.
5. Ghi ít nhất ba `NOT_COVERED` sau vòng PR.
6. Đề xuất nightly/release lanes.
7. Xác định critical go/no-go blockers.

---

## 55. Bài tập 2 — Phát hiện fake quá tốt

Một fake repository:

~~~java
public synchronized boolean reserve(
        String eventId, int quantity) {

    long current = available.get(eventId);
    if (current < quantity) return false;

    available.put(eventId, current - quantity);
    return true;
}
~~~

Trong production, service gọi `GET` rồi `PUT` qua hai operations riêng.

Hãy:

1. Nêu vì sao fake an toàn hơn production.
2. Viết một interleaving gây oversell.
3. Định nghĩa business invariant và oracle.
4. Chọn một conditional write trên engine thật.
5. Thiết kế concurrency test 20 clients.
6. Mở rộng kiểm requestId/idempotency.
7. Xác định một lỗi chỉ xuất hiện khi failover.

---

## 56. Bài tập 3 — DynamoDB Local vs AWS staging

Một bộ test Local đã pass:

~~~text
GetItem
PutItem
UpdateItem ConditionExpression
Query GSI
~~~

Product yêu cầu:

~~~text
IAM ngăn tenant ngoài scope.
GSI có freshness SLO được đo.
RPO region loss <= 5 phút.
Retry không tạo duplicate order.
~~~

Hãy:

1. Chỉ ra yêu cầu nào Local có thể giúp test phần API.
2. Yêu cầu nào cần AWS staging/DR test.
3. Thiết kế permissions với test IAM deny.
4. Thiết kế read freshness test.
5. Định nghĩa idempotency contract.
6. Ghi limitation ledger.
7. Nêu cách tránh dùng dummy credentials ở production.

---

## 57. Bài tập 4 — Kiểm MongoDB transactions

Có hai collections:

~~~text
inventory
reservations
~~~

Business yêu cầu tạo reservation và giảm stock phải all-or-nothing.

1. Viết pre/postcondition.
2. Tạo MongoDB replica-set test environment.
3. Test transaction success.
4. Inject exception trước commit.
5. Kiểm abort không để orphan.
6. Inject timeout tại commit/ACK.
7. Kiểm unknown outcome/retry.
8. Chạy concurrent reservations tranh vé cuối.
9. Nêu giới hạn của single-member test topology.

---

## 58. Bài tập 5 — Kiểm Cassandra theo consistency

Một keyspace có RF=3, Java API dùng `LOCAL_QUORUM`.

Hãy:

1. Đề xuất topology test tối thiểu có ý nghĩa.
2. Vì sao CassandraContainer một node không đủ?
3. Seed partition keys và data distribution.
4. Test fail một replica.
5. Test fail nhiều replicas trong local DC.
6. Phân biệt unavailable và timeout.
7. Xem contract của read-after-write.
8. Nêu vì sao `R+W>N` không tự chứng minh transaction multi-table.
9. Ghi fault trace và recovery criteria.

---

## 59. Bài tập 6 — Redis TTL và failover

Một service dùng Redis giữ:

~~~text
idempotency:<chargeId>
lease:<resourceId>
session:<userId>
~~~

Hãy:

1. Phân loại các business invariants.
2. Dùng Redis server thật kiểm TTL logic.
3. Giải thích physical cleanup không phải auth expiry.
4. Chạy `SETNX` concurrency test.
5. Tạo primary/replica failure test.
6. Xác định mức dữ liệu có thể mất do async replication.
7. Thiết kế fencing cho stale lease holder.
8. Nêu test nào không được chứng minh từ mock/fake.

---

## 60. Bài tập 7 — Tạo Test Report có giới hạn rõ

Một nhóm có kết quả:

~~~text
Mock tests: 500 PASS
DynamoDB Local: 120 PASS
Real MongoDB single node: 40 PASS
Redis Cluster tests: NOT_RUN
Managed IAM tests: NOT_RUN
Payment idempotency fault test: FAIL once
~~~

Hãy:

1. Viết báo cáo không che các gaps.
2. Phân biệt regression với infrastructure failure.
3. Chọn blocker release.
4. Đề xuất owner và deadline follow-up.
5. Định nghĩa artifacts cần lưu để reproduce payment failure.
6. Nêu vì sao “660 tests pass” không đủ.
7. Viết bản trình bày technical risk cho product owner.

---

## 61. Bài tập 8 — Thiết kế lộ trình kiểm thử tổng thể

Một hệ NoSQL cần:

- Fast PR feedback.
- Tích hợp với database driver.
- Kiểm concurrency/CAS/transactions.
- Kiểm multi-region failover.
- Kiểm backup/restore.
- Kiểm source/target migration.
- Kiểm security/TLS/IAM.
- Chịu peak load.
- Giảm chi phí CI.
- Có lịch sử test đủ truy vết.

Hãy xây kế hoạch gồm:

1. Unit/mock suite.
2. Testcontainers real-engine suite.
3. Multi-node fault suite.
4. Managed staging suite.
5. Chaos/DR drills.
6. Representative test fixtures.
7. Oracle và invariant catalog.
8. Fidelity/limitations ledger.
9. Owners và release gates.
10. PASS/FAIL/UNKNOWN/NOT_COVERED reporting.

Không biến kế hoạch thành lời hứa rằng mọi tình huống phân tán đều được chứng minh tuyệt đối bằng test hữu hạn.

---

## 62. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “Mock pass nghĩa DB sẽ làm đúng.” | Mock kiểm logic đã mô phỏng, không engine semantics |
| “Một fake `HashMap` giống NoSQL.” | Không có index, consistency, durability, errors thật |
| “Fake synchronized chứng minh concurrent safety.” | Có thể an toàn hơn multi-instance production |
| “Emulator là managed service thật trên localhost.” | API fidelity có giới hạn |
| “LocalStack pass nghĩa AWS IAM pass.” | IAM phải kiểm managed staging/policy thực |
| “DynamoDB Local mô phỏng mọi regional failure.” | Không thể suy điều đó |
| “Container có engine thật nên kiểm luôn quorum.” | Một node không có distributed topology |
| “MongoDB `getReplicaSetUrl` nghĩa có nhiều voters.” | Module có thể tạo replica set một thành viên |
| “Cassandra một node đủ kiểm LOCAL_QUORUM outage.” | Cần topology RF/replicas thật |
| “Redis Lua atomic nghĩa durable sau failover.” | Atomic execution khác replication durability |
| “Redis SETNX là distributed fencing lock.” | Cần epoch/fencing tại destination |
| “Elasticsearch local search pass nghĩa shard recovery pass.” | Multi-node shard behavior chưa được thử |
| “Database ping thành công chứng minh transaction.” | Ping chỉ kiểm một path kết nối |
| “Equal count nghĩa content đúng.” | IDs/types/deletes/invariants có thể sai |
| “Query trả đúng 10 records nghĩa scale tốt.” | Planner/index/partition skew có thể khác |
| “Mock timeout nghĩa đã test unknown commit.” | Cần tạo/đối soát scenario thực |
| “One successful concurrency run chứng minh race không thể.” | Interleavings hữu hạn |
| “`Thread.sleep` là cách ổn định eventual tests.” | Cần bounded polling và watermark |
| “TTL xóa vật lý đúng thời điểm expiresAt.” | Cleanup có thể bất đồng bộ |
| “Mock event listener chứng minh CDC recovery.” | Replay/resume/failover cần real stream |
| “Driver mới tự giữ response/error semantics.” | Có thể khác timeouts, retries, codecs |
| “Test database không cần giống production config.” | Config có thể đổi semantics |
| “Docker image `latest` tái lập được.” | Tag có thể di chuyển/version đổi |
| “CI skip test vì thiếu Docker cũng tính xanh.” | Phải báo NOT_RUN/SKIPPED_INFRA |
| “Flaky correctness test nên retry tới khi pass.” | Có thể che race thật |
| “One node crash test giống region loss.” | Failure domain khác |
| “Nhiều PASS bù được một critical FAIL.” | Safety/tenant/payment gates theo severity |
| “Index presence không cần integration test.” | Query shape/index behavior phải kiểm |
| “Emulator test có thể xác minh compliance.” | Security/data residency cần bằng chứng phù hợp |
| “Có engine real là khỏi cần mocks.” | Unit/mocks vẫn rất hiệu quả cho pure policy |
| “Càng nhiều integration tests càng tốt không giới hạn.” | Phân tầng theo rủi ro/chi phí |
| “Dùng production secrets để staging giống thật.” | Tăng exposure, trái least privilege |
| “Test report chỉ cần PASS/FAIL.” | Cần UNKNOWN/NOT_COVERED/NOT_REPRESENTATIVE |
| “Không có error là correctness được chứng minh.” | Phải có independent oracle |
| “Test pass ở version X áp cho mọi version.” | Cần version/config compatibility review |
| “Read từ replica eventual là oracle của current state.” | Có thể stale |
| “RPO/RTO có thể chứng minh bằng mock.” | Cần restore/drill thực tế |
| “Chạy load test pass nghĩa no data corruption.” | Cần thu history và invariant checker |
| “Khi source emulation thiếu feature cứ bỏ test.” | Ghi giới hạn và follow-up |
| “Container test là test toàn hệ phân tán.” | Phải ghi topology/operation scope |

---

## 63. Checklist để gọi một bộ integration test là có giá trị

- [ ] Có yêu cầu nghiệp vụ/invariant cụ thể.
- [ ] Phạm vi test và điều **không chứng minh** được ghi rõ.
- [ ] Chọn đúng tầng mock/fake/emulator/real engine/real cluster.
- [ ] Driver và server versions được pin.
- [ ] Schema/index/migration thật được áp dụng trong môi trường test.
- [ ] Connection/endpoint/TLS/auth phù hợp điều cần kiểm.
- [ ] Real engine test thực sự gọi đúng repository adapter production.
- [ ] Test data có boundary, legacy, null/missing, large value và hot keys.
- [ ] Có tenant isolation/authorization negative tests.
- [ ] Có atomic/CAS/transaction tests cho writes quan trọng.
- [ ] Có concurrency tests với barrier và multi-client behavior.
- [ ] Có test retry sau timeout/unknown commit.
- [ ] Có independent oracle và authoritative source evidence.
- [ ] Có cách lấy consistent snapshot/watermark khi cần.
- [ ] Không dựa vào eventual replica read để kết luận strong correctness.
- [ ] Có kiểm TTL logic khác physical cleanup.
- [ ] Có event/CDC duplicate/order/resume tests nếu hệ dùng stream.
- [ ] Có multi-node/failover tests cho distributed contracts.
- [ ] Có managed staging tests cho IAM/PITR/global tables khi cần.
- [ ] Có dữ liệu và load tương xứng với scale assumption.
- [ ] Test không vô tình dùng production credentials/data.
- [ ] Cleanup có boundary, không thể xóa nhầm production.
- [ ] Có measured resource limits và readiness startup.
- [ ] Có random seed và operation IDs khi chạy concurrency.
- [ ] Traces/logs được lưu khi fail và redacted đúng.
- [ ] Kết quả phân biệt PASS/FAIL/UNKNOWN/NOT_RUN.
- [ ] SKIPPED/NOT_REPRESENTATIVE không được gộp PASS.
- [ ] Có limitations ledger theo feature/emulator/version.
- [ ] Có version/config/topology trong test report.
- [ ] Có CI lane nhanh và lane fault/managed chậm.
- [ ] Có owner cho critical gaps và release gates.
- [ ] Không hạ TLS/consistency/durability chỉ để test xanh.
- [ ] Không che flaky tests bằng retries vô hạn.
- [ ] Có test security, deletions/restore và idempotency nếu thuộc scope.
- [ ] Mọi test critical có thời điểm chạy và freshness của evidence.
- [ ] Test report không tuyên bố bảo đảm rộng hơn phạm vi đã thử.
- [ ] Có lịch cập nhật tests khi engine/driver/schema/topology thay đổi.

---

## 64. Tổng kết

**Kiểm thử NoSQL đáng tin không phải chọn giữa mock và database thật; đó là đặt mỗi câu hỏi tính đúng vào đúng môi trường có khả năng trả lời.** Mock rất hiệu quả để kiểm business orchestration. Emulator hữu ích để kiểm một phần API. Engine thật giúp xác minh query, index, serialization và atomic operation semantics. Cụm thật cần thiết cho replication, quorum và failover. Dịch vụ managed staging và restore drills cần thiết cho những hành vi mà local container không thể đại diện.

Mười nguyên tắc quan trọng:

1. **Gắn test với invariant/contract trước khi chọn công cụ.** Mục tiêu là bảo vệ hành vi nghiệp vụ, không phải tăng test count.
2. **Mock không kiểm được database semantics.** Những gì mock không thực thi phải được test ở tầng khác hoặc ghi limitation.
3. **Emulator không tự tương đương managed service.** Ghi feature coverage, version và những API/behavior chưa được kiểm.
4. **Engine thật một node không chứng minh cụm phân tán.** Multi-member election, replication, partition và DR phải có topology/fault tests riêng.
5. **Test trên actual Java driver và production adapter.** Serialization, errors, retries, pool và protocol behavior là phần quan trọng của integration.
6. **Dùng oracle độc lập, consistent evidence và history khi cần.** Một API trả success chưa chắc dữ liệu, receipts và business effects đúng.
7. **Bổ sung concurrency/unknown-outcome scenarios.** Các lỗi khó thường xuất hiện giữa commit, ACK, failover và retry.
8. **Dữ liệu/version/config phải đại diện và tái lập được.** Không suy production parity từ default container config.
9. **CI có nhiều tầng với phạm vi rõ ràng.** Fast unit tests và nightly/managed suites bổ sung nhau, không thay nhau.
10. **Báo cáo trung thực PASS, FAIL, UNKNOWN và NOT_COVERED.** Điều chưa chạy hoặc môi trường không đại diện không phải bằng chứng an toàn.

**Câu cần nhớ: “Mock giúp kiểm code có phản ứng như mình đã giả định hay không. Engine thật giúp kiểm database có hành xử như mình kỳ vọng hay không. Cụm thật và môi trường managed giúp kiểm những giả định phân tán và vận hành. Phải ghi rõ mỗi lớp đã chứng minh gì, và chưa chứng minh gì.”**
