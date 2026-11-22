# Bảo vệ cập nhật cạnh tranh bằng điều kiện hoặc giao dịch phù hợp

Một ứng dụng Java quản lý phòng lưu kho còn **một suất** cho chuyến xe. Hai khách cùng bấm “Đặt chỗ”. Cả hai API instances đọc được `remaining = 1`, rồi cùng thực hiện `remaining = 0` và trả thành công. Dữ liệu cuối cùng vẫn bằng 0, nhưng hệ thống đã bán **hai vé cho một ghế**. Trong một tình huống khác, hai request cùng đọc số dư 500.000 đồng; một lệnh trừ 100.000 và lệnh khác cộng 200.000. Nếu cả hai tính kết quả từ giá trị cũ rồi ghi đè nhau, một giao dịch hợp lệ bị mất.

Đây là lỗi **cập nhật cạnh tranh** (*concurrent update*). Trong NoSQL, document/key thường là đơn vị có bảo đảm nguyên tử mạnh nhất, nhưng tính nhất quán của các thao tác nhiều bản ghi phụ thuộc rất nhiều vào engine, partitioning và API cụ thể. Chỉ có replicas, WAL hoặc độ bền ghi không tự ngăn lost update, double booking hay write skew.

Bài học thuộc chương **Thực hành tổng hợp** của module **Database No SQL**. Ta sẽ thiết kế một bài lab bảo vệ tồn kho và đặt chỗ bằng **điều kiện ghi nguyên tử (conditional write), compare-and-set (CAS), optimistic concurrency/version và transaction khi cần**; triển khai mô hình Java 17; xây test nhiều luồng và tiêm lỗi; sau đó đối chiếu primitives trên MongoDB, DynamoDB, Cosmos DB, Cassandra/ScyllaDB, Redis, Firestore và một số hệ document khác.

> **Mục tiêu không phải “không còn conflict”.** Các request cạnh tranh có thể bị từ chối hợp lệ. Mục tiêu là **không bao giờ commit trạng thái trái bất biến nghiệp vụ**, không làm mất ghi đã xác nhận, không nhân đôi tác động khi retry và có phản hồi đủ rõ để client xử lý.

## 1. Kết quả mong đợi của bài thực hành

Sau bài này, bạn có thể:

1. Xác định bất biến của một thao tác trước khi viết query.
2. Phân biệt một-document atomic update với transaction nhiều bản ghi.
3. Viết conditional update kiểm tra `available >= quantity` ngay tại storage.
4. Dùng `version`/ETag/CAS để chống ghi đè trên dữ liệu đọc cũ.
5. Tách **concurrency control** khỏi **idempotency** của các lần retry.
6. Xác định khi nào transaction vẫn chưa đủ do isolation/write skew.
7. Thiết kế test có rào bắt đầu đồng thời, fault injection và oracle dữ liệu.
8. Lựa chọn primitive phù hợp với engine/partition scope và đánh giá chi phí.

### 1.1. Bài toán xuyên suốt

Ta quản lý `InventoryItem` theo cặp `(tenantId, sku)` và `Reservation` theo một `commandId` ổn định. Khi đặt `q` suất:

~~~text
Precondition:
    item exists
    q > 0
    available >= q

Commit:
    available := available - q
    version := version + 1
    create a unique reservation for commandId
    record an idempotency receipt
    record an outbox event if required

Invariant:
    available >= 0
    one business reservation per commandId
    no successful response without durable reservation
    committed operations do not disappear under supported failure model
~~~

### 1.2. Nhiều đơn vị tồn kho

Khi `available = 10`, có 20 người đồng thời đặt mỗi người một suất. Kết quả đúng là **tối đa 10 reservations thành công**, `available = 0`, không có reservation trùng. Không cần tất cả 20 requests đều thành công.

### 1.3. Đa tenant

Tenant A và tenant B có thể có cùng `sku`. Mọi điều kiện, uniqueness và authority phải chứa tenant scope đáng tin cậy; không dùng tenantId do client tự bịa để truy cập tenant khác.

## 2. Bất biến nghiệp vụ khác yêu cầu hiệu năng

Một hệ có thể đạt 50.000 writes/s nhưng sai nếu một giao dịch bán quá số suất. Hãy xác định:

| Bất biến | Ý nghĩa | Phạm vi |
|---|---|---|
| `available >= 0` | Không đặt quá tồn kho | Một InventoryItem |
| `version` tăng khi state đổi | Không ghi lùi state | Một InventoryItem |
| Mỗi `commandId` chỉ có một reservation | Retry không nhân effect | Key namespace |
| Một ghế không có hai booking active | No double booking | Một seat/time slot |
| Tổng debit = tổng credit | Conservation of money | Nhiều ledger entries |
| Không có hai leader có quyền ghi | Single authority | Shard/epoch |
| Không đọc/ghi chéo tenant | Authorization isolation | Tenant, API, storage |

### 2.1. Bất biến nào có thể bảo vệ trên một key?

`available >= 0` của một InventoryItem có thể được chặn bằng conditional update trên item đó nếu **mọi writer** đi qua cùng authority.

### 2.2. Bất biến nào trải qua nhiều keys?

Trừ tồn kho, tạo reservation và ghi outbox ở các documents khác nhau có thể cần **transaction** trong phạm vi engine hỗ trợ hoặc giao thức có thể phục hồi.

### 2.3. Thế nào là một commit đúng?

Không chỉ database trả `success`, mà các trường/phần tử liên quan phải được xác nhận theo hợp đồng: cập nhật tồn, ghi reservation, bảo đảm unique idempotency và durability.

### 2.4. Một transaction không thay authorization

Ngay cả thao tác nguyên tử vẫn có thể ghi nhầm tenant nếu filter thiếu `tenantId`. Security predicate là một phần của correctness.

## 3. Lost update: đọc–sửa–ghi không bảo vệ

Giả sử item ban đầu:

~~~json
{
  "tenantId": "T1",
  "sku": "SEAT-17",
  "available": 1,
  "version": 4
}
~~~

Hai handlers:

~~~text
Time    Request A                         Request B
--------------------------------------------------------
T0      read available=1
T1                                        read available=1
T2      calculate next=0
T3                                        calculate next=0
T4      write available=0
T5                                        write available=0
T6      return RESERVED                   return RESERVED
~~~

### 3.1. Vì sao final state đánh lừa?

`available=0` trông hợp lệ nhưng hai reservations đã được chấp nhận. Test chỉ assert `available >= 0` chưa đủ; phải đối chiếu reservations và số hiệu ứng thực tế.

### 3.2. Counter lost update

Một luồng cập nhật `balance = 500 - 100`, luồng khác cập nhật `balance = 500 + 200`; last-write-wins có thể cho 400 hoặc 700 thay vì 600. Đây là sự mất một thay đổi hợp lệ.

### 3.3. Chỉ dùng `synchronized` trong Java không đủ

Lock của một JVM không bảo vệ hai pods, batch worker hoặc service khác cùng ghi database. Lock cũng không tự xử lý process crash và leader failover.

### 3.4. Đọc mạnh rồi ghi vô điều kiện vẫn sai

Strongly consistent read không làm cặp **read + later write** trở thành nguyên tử. Một writer khác có thể chen vào sau lúc đọc.

## 4. Mẫu sai phổ biến: check-then-act

~~~java
// KHÔNG AN TOÀN nếu có nhiều writers.
Inventory item = repository.findByTenantAndSku(tenant, sku);
if (item.available() >= quantity) {
    repository.save(item.withAvailable(
        item.available() - quantity));
    return "RESERVED";
}
return "INSUFFICIENT";
~~~

### 4.1. Race window

Khoảng từ `find` đến `save` có thể chứa nhiều writers. Transaction read committed đơn giản cũng chưa chắc loại race nếu write không có điều kiện tương thích.

### 4.2. Chỉ check trong ứng dụng không bảo vệ

Phải chuyển điều kiện liên quan bất biến xuống cùng operation nguyên tử tại nơi có thẩm quyền ghi.

### 4.3. Read–modify–write vẫn hữu ích nếu có CAS

Đọc current state, tính candidate, rồi ghi với `version = expected` là optimistic concurrency đúng khi mọi writer tuân thủ và xử lý CAS failure.

## 5. Giải pháp một item: conditional atomic update

Một thao tác có thể viết ý tưởng:

~~~text
UPDATE inventory
SET available = available - :quantity,
    version = version + 1
WHERE tenantId = :tenant
  AND sku = :sku
  AND available >= :quantity
  AND item exists;
~~~

Đây là **pseudo-query**, không phải cú pháp chung cho mọi NoSQL. Điều kiện và phép trừ phải được thực thi **nguyên tử trên cùng authoritative item**.

### 5.1. Một writer thắng khi còn một suất

Hai requests `q=1`, `available=1`: DB serialize/linearize conditional update phù hợp; một update thành công, update kia thấy điều kiện không còn đúng và từ chối.

### 5.2. Điều kiện dùng state hiện tại tại commit

Không chỉ lấy `available` trong request JSON hoặc cache. Điều kiện phải dựa trên dữ liệu đang được lưu ở authority theo semantics của engine.

### 5.3. Không tự suy từ “atomic increment”

Một atomic decrement không kèm điều kiện có thể đưa available xuống âm. Atomicity của một arithmetic operation không đồng nghĩa bảo vệ domain constraint.

### 5.4. Kết quả conditional failure

Một `condition failed` có thể do thiếu item, version cũ, không đủ tồn kho hoặc conflict khác. Thiết kế error taxonomy và đọc lại có điều kiện để phân biệt khi cần.

### 5.5. Một operation không bảo vệ external side effects

Nếu email được gửi trước conditional update, cả hai requests có thể đã gửi mail dù chỉ một reservation thành công. Side effects cần outbox/idempotency.

## 6. Optimistic concurrency bằng version hoặc ETag

Một update có điều kiện:

~~~text
Read:
    Order version = 12, status = NEW

Attempt:
    IF version == 12 AND status == NEW
    THEN set status=CONFIRMED, version=13
~~~

### 6.1. Compare-and-set (CAS)

CAS cho phép thay đổi chỉ khi giá trị/version vẫn như kỳ vọng, để cập nhật từ snapshot cũ không ghi đè trạng thái mới.

### 6.2. Version nên tăng như thế nào?

Với update thành công, increment version trong **cùng atomic operation**. Nếu đọc version rồi update version bằng lệnh riêng, vẫn có race.

### 6.3. ETag

Một số document stores cung cấp ETag hoặc CAS token từ server. Đưa token vào conditional write `If-Match` theo API; không tự tạo ETag bằng timestamp client.

### 6.4. Conflict là kết quả hợp lệ

Một CAS failure cho biết một writer đã thay state, không phải database bị lỗi. Client có thể reload, merge hoặc trả `409 Conflict` theo nghiệp vụ.

### 6.5. Không retry CAS bằng cách bỏ điều kiện

Nếu thấy `version conflict` và chạy update vô điều kiện để “đảm bảo thành công”, ta đã phá chính cơ chế chống lost update.

## 7. Khi nào dùng điều kiện theo version, khi nào theo giá trị?

### 7.1. Chặn số lượng âm

`available >= qty` trực tiếp diễn tả invariant. Nếu update chỉ dùng version mà không recheck `available`, code đọc cũ có thể tính sai khi có logic khác.

### 7.2. Chặn ghi đè chỉnh sửa profile

`version = expected` phù hợp khi client muốn update trên bản đã xem: một người sửa địa chỉ, người khác sửa số điện thoại. Conflict cho cơ hội merge dữ liệu.

### 7.3. Kết hợp hai điều kiện

`available >= qty AND version = expected` có thể cần nếu caller đòi làm việc đúng trên snapshot/version đã biết. Nhưng tăng contention; nếu chỉ cần stock không âm, version precondition có thể không cần.

### 7.4. Kiểm domain transition

`status = PENDING AND version = expected` giúp cấm chuyển trực tiếp từ `CANCELLED` sang `PAID`. Version không thay validation state machine.

### 7.5. Kiểm theo nhiều fields

Có thể dùng predicate trên nhiều fields cùng document, nhưng phải xác nhận engine thực thi atomic predicate + update và mọi writers cùng dựa authority đó.

## 8. Concurrency control khác idempotency

Xét ba requests:

~~~text
A: reserve seat S, commandId=K1
B: reserve seat S, commandId=K2
C: retry exactly A, commandId=K1
~~~

### 8.1. A và B là hai ý định cạnh tranh

Chỉ một được giành seat nếu còn một ghế. Cần conditional update/unique constraint/transaction.

### 8.2. A và C là cùng một ý định

Nếu A thành công rồi response mất, C không được trừ thêm một ghế. Cần **idempotency receipt**, stable reservation ID hoặc uniqueness theo command.

### 8.3. Conditional decrement chưa đủ chống retry

Khi còn 10 ghế, A trừ từ 10 xuống 9; C retry cùng ý định có thể trừ 9 xuống 8 nếu không dedupe, dù cả hai decrements đều thỏa `available >= 1`.

### 8.4. Receipt lưu ở đâu?

Lưu `(authenticatedTenantId, operation, commandId)` với fingerprint và outcome trong durable store. Cần cùng atomic boundary với business mutation hoặc recoverable protocol.

### 8.5. Same key, different payload

Nếu K1 trước dùng `quantity=1` nhưng retry dùng `quantity=3`, đây là key reuse conflict. Không tự chọn payload mới hoặc trả thành công cũ mà không kiểm fingerprint.

## 9. Sơ đồ xử lý một reservation

~~~mermaid
flowchart TD
    REQ["Reserve(tenant, sku, q, commandId)"] --> AUTH["Authorize tenant + validate payload"]
    AUTH --> REC{"Receipt exists?"}
    REC -->|Yes, same fingerprint| REPLAY["Replay stored result"]
    REC -->|Yes, different fingerprint| CONFLICT["Key conflict"]
    REC -->|No| ATOMIC["Atomic reserve + receipt + outbox"]
    ATOMIC -->|Committed| OK["Reservation result"]
    ATOMIC -->|Insufficient| NO["Terminal rejection per policy"]
    ATOMIC -->|Unknown outcome| RESOLVE["Resolve authoritative receipt"]
    RESOLVE --> REC
~~~

### 9.1. Receipt lookup không tự bảo đảm safety

Hai requests có thể cùng đọc receipt absent. Trường hợp thắng/thua phải được phân định bằng uniqueness/conditional transaction tại storage.

### 9.2. Terminal business failure có lưu không?

Nếu request thiếu stock, có thể persist failure outcome cho commandId hoặc cho phép retry sau replenish. Contract phải nêu rõ; ví dụ trong lab sẽ **lưu terminal `INSUFFICIENT`**.

### 9.3. Unknown commit không bằng failure

Timeout sau commit có thể khiến client chưa biết outcome. Retry giữ nguyên commandId và truy vấn authoritative receipt; không tạo một lệnh mới.

## 10. Nhiều bản ghi: điều kiện trên một item chưa đủ

Đặt chỗ có thể gồm:

~~~text
Inventory: available := available - 1
Reservation: create unique reservationId
Order: status := RESERVED
Outbox: append ReservationCreated
Receipt: commandId -> result
~~~

Nếu mỗi thao tác là một write độc lập, crash sau decrement nhưng trước reservation có thể làm mất một suất vĩnh viễn; crash sau reservation nhưng trước receipt có thể khiến retry tạo thêm reservation.

### 10.1. Transaction đúng phạm vi

Nếu engine hỗ trợ atomic transaction trên tập documents liên quan, đặt điều kiện/changes/receipt/outbox vào **cùng transaction** trong giới hạn kích thước, thời gian và partition.

### 10.2. Dùng aggregate/document phù hợp

Nếu các fields cần cập nhật cùng nhau có thể đặt trong một item bounded, single-item CAS/transaction có thể đơn giản và hiệu quả hơn distributed multi-document transaction.

### 10.3. Không nhúng danh sách reservations vô hạn

Để có single-document atomicity, không nên lưu tất cả reservations vào mảng không giới hạn. Cần cân bằng atomic boundary, document size và retention.

### 10.4. Nếu transaction không hỗ trợ

Dùng một authority record/ledger, reservation state machine và outbox/CDC/saga có khả năng phục hồi, với idempotency và invariant được thiết kế rõ. Không chỉ “ghi hai bên rồi retry”.

## 11. Atomicity, isolation và durability là ba câu hỏi khác

| Khả năng | Nó trả lời điều gì? | Không tự bảo đảm |
|---|---|---|
| Atomicity | Tập writes commit cùng hoặc không | Business uniqueness ngoài tập |
| Isolation | Concurrent transactions nhìn nhau thế nào | Durability sau failover |
| Durability | ACKed commits còn sau lỗi nào | Không double-booking do logic |
| Conditional write | Một predicate được bảo vệ tại update | Multiple independent items |
| Idempotency | Cùng command gửi lại không thêm effect | Khác commands tranh nguồn |
| Ordering/fencing | Ai có quyền ghi và theo thứ tự nào | Domain constraints khác |

### 11.1. “Có transaction” không đồng nghĩa serializable

Một engine có thể hỗ trợ snapshot isolation mà vẫn cho phép write skew giữa hai transactions ghi các documents khác nhau.

### 11.2. Chọn isolation theo bất biến

Nếu cần một predicate toàn tập (`at least one on-call doctor`), phải có transaction serializable hoặc thiết kế authority chung/constraint cụ thể; snapshot isolation có thể không đủ.

### 11.3. Đảm bảo đúng ở ranh giới nào?

Kiểm local partition, collection, table, database, region hoặc global? Không suy transaction scope từ cụm từ “NoSQL transaction”.

### 11.4. Durability phải cùng mục tiêu

Một atomic write được ACK với replication policy yếu vẫn có thể mất khi failover theo failure model. Chọn write concern/quorum/durability phù hợp, test nó.

## 12. Write skew: hai writers cập nhật khác documents

Hai bác sĩ A và B đều đang trực. Quy tắc nghiệp vụ: **phải luôn có ít nhất một người trực**.

~~~text
Transaction T1:
    read A=ON, B=ON
    set A=OFF

Transaction T2:
    read A=ON, B=ON
    set B=OFF

Both commit under an isolation model allowing write skew.
Final state: A=OFF, B=OFF  (violates invariant)
~~~

### 12.1. Vì sao CAS trên mỗi bác sĩ chưa đủ?

T1 ghi A, T2 ghi B; hai writes không tranh cùng version key nên cả hai có thể thành công dù cùng dựa một snapshot cũ.

### 12.2. Snapshot isolation có thể cho write skew

Đây là hiện tượng khác lost update. Một transaction snapshot-consistent không tự bảo vệ một predicate bất biến trên nhiều rows/documents.

### 12.3. Các cách bảo vệ

Sử dụng serializable transaction/predicate protection khi được hỗ trợ, hoặc đưa invariant vào một `OnCallGuard` document có CAS version bị cả hai transactions cập nhật, hoặc tổ chức command qua một authoritative scheduler.

### 12.4. Test phải đọc cả hai records

Sau hai transactions, oracle là `count(ON) >= 1`, không chỉ kiểm từng update có status 200.

## 13. Unique constraint và double booking

Ví dụ: ghế S17 chuyến F1 chỉ có tối đa một reservation ở trạng thái active.

### 13.1. Chỉ tìm “chưa ai đặt” rồi insert là sai

Hai writers có thể cùng thấy không có reservation, rồi mỗi người insert một document khác nhau.

### 13.2. Dùng key duy nhất theo slot

Một authority row keyed `(tenantId, flightId, seatId)` với conditional insert hoặc conditional state transition chặn hai claims cùng slot.

### 13.3. Uniqueness phải đúng scope

Unique theo `(tenant,seat)` không đủ khi ghế S17 có thể hợp lệ trên nhiều chuyến. Unique theo `(tenant,flightId,seatId)` mới phù hợp.

### 13.4. Phân vùng ảnh hưởng uniqueness

Nếu constraint chỉ bảo đảm uniqueness **trong một partition**, các claims của cùng slot phải cùng partition hoặc cần một unique registry authoritative khác.

### 13.5. Expiry/cancel khác delete mù

Hủy reservation nên dùng version/state guard để không xóa booking mới vừa giành slot do một delayed cancel cũ.

## 14. Chọn primitive theo phạm vi cập nhật

| Nhu cầu | Primitive ưu tiên | Kiểm tra thêm |
|---|---|---|
| Counter không âm trên một item | Atomic conditional decrement | Idempotency, consistency |
| Lost update trên một document | `version`/ETag CAS | Retry/reload conflict |
| Chuyển state có điều kiện | State + version predicate | Domain state machine |
| Tạo resource duy nhất | Conditional create/unique key | Namespace, tenant |
| Một command cập nhật nhiều items | Transaction có điều kiện | Isolation, size/partition limits |
| Predicate trải nhiều documents | Serializable hoặc guard key | Write skew/phantoms |
| Source không hỗ trợ transaction cần thiết | Single authority + saga/outbox | Recovery, reconciliation |
| Lock nhiều writers | Lock/lease với fencing | Crash, TTL, stale owner |
| Replicated multi-region writes | Conflict/authority protocol | RPO, merge semantics |

### 14.1. Primitive nhỏ nhất đáp ứng invariant

Nếu điều kiện một item đủ, không cần transaction nhiều documents vì thường tăng latency/cost và contention.

### 14.2. Nhưng không chọn nhỏ hơn invariant

Một conditional update trên Inventory không tự bảo đảm có Reservation record và receipt tương ứng. Nếu business success đòi cả hai, phải thiết kế atomic scope lớn hơn.

### 14.3. Tăng độ phức tạp có chủ đích

Chỉ thêm distributed locks, queues, sagas khi một CAS/transaction phù hợp không đáp ứng workload hoặc invariant.

## 15. Lab: dữ liệu, API và yêu cầu

API minh họa:

~~~text
POST /tenants/{tenantId}/inventory/{sku}/reservations
Idempotency-Key: command-123
If-Match: version=5  # optional per business contract

Body:
    { "quantity": 1 }

Success:
    { "reservationId": "...", "remaining": 0, "version": 6 }
~~~

### 15.1. Setup

Seed item `T1 / SEAT-17` có `available=10`, `version=0`. Tạo 100 requests gồm 80 lệnh distinct IDs và 20 retries dùng lại key của lệnh đã phát.

### 15.2. Endpoint chỉ minh họa

Đường dẫn chứa tenantId không làm tenantId đáng tin. Server phải lấy trusted tenant từ auth principal và so với path.

### 15.3. Hợp đồng phản hồi

`201/200` cho reservation committed hoặc replay theo API, `409` cho version/idempotency conflict, `422`/business status cho thiếu stock theo contract. Một outcome unknown cần cho client tra lại bằng commandId.

### 15.4. Oracle thành công

Với 10 suất và 80 unique intents quantity=1, **tối đa và trong điều kiện không có lỗi vĩnh viễn thì đúng 10** lệnh được chấp nhận. `available=0`, mỗi key có tối đa một reservation, số unique reservations committed bằng 10.

## 16. Thiết kế tài liệu NoSQL cho lab

~~~json
{
  "pk": "INV#T1#SEAT-17",
  "tenantId": "T1",
  "sku": "SEAT-17",
  "available": 10,
  "version": 0
}
~~~

~~~json
{
  "pk": "RECEIPT#T1#RESERVE#command-123",
  "tenantId": "T1",
  "commandId": "command-123",
  "fingerprint": "sha256:...",
  "status": "COMMITTED",
  "reservationId": "res-command-123",
  "remaining": 9
}
~~~

~~~json
{
  "pk": "RESERVATION#T1#command-123",
  "tenantId": "T1",
  "sku": "SEAT-17",
  "quantity": 1,
  "state": "ACTIVE"
}
~~~

### 16.1. Logical identity và partition key khác nhau

Ở một hệ, các records này có thể nằm cùng partition logic; ở hệ khác sẽ nằm các partitions khác nhau. Đây là **mô hình logic**, cần ánh xạ vào data model theo transaction scope thực của engine.

### 16.2. Receipt fingerprint

Tính từ các trường có ý nghĩa (`operation`, trusted tenant, SKU, quantity, expectedVersion nếu hợp đồng tính nó). Không hash raw JSON chưa canonicalize để tránh conflict giả.

### 16.3. Result lưu trong receipt

Retry cùng commandId/payload có thể trả lại reservationId và outcome đã ghi, không chạy lại decrement.

### 16.4. Không tự viết unique registry khi có primitive phù hợp

Nếu một conditional create trên key đã đại diện cho seat/slot là đủ, dùng nó. Tránh những tầng dữ liệu phụ dễ lệch trạng thái.

## 17. Java 17: domain command và kết quả

Các kiểu dưới đây không phụ thuộc driver; implementation NoSQL phải làm đúng atomic contract.

~~~java
import java.util.Objects;

public record ReserveCommand(
    String tenantId,
    String sku,
    String commandId,
    int quantity
) {
    public ReserveCommand {
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(sku);
        Objects.requireNonNull(commandId);
        if (tenantId.isBlank() || sku.isBlank()
                || commandId.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("invalid request");
        }
    }
}

public sealed interface ReserveOutcome
    permits Reserved, Insufficient, UnknownItem, KeyConflict {
}

public record Reserved(
    String reservationId,
    int remaining,
    long committedVersion
) implements ReserveOutcome {}

public record Insufficient(
    int remaining
) implements ReserveOutcome {}

public record UnknownItem() implements ReserveOutcome {}
public record KeyConflict() implements ReserveOutcome {}

public interface ReservationPort {
    // One logical command must have at most one business effect.
    ReserveOutcome reserveOrReplay(ReserveCommand command);
}
~~~

### 17.1. Port định nghĩa nghiệp vụ, không định nghĩa query SQL

Adapter MongoDB, DynamoDB hay Cosmos chịu trách nhiệm implementing transactions/conditions/receipts. Service layer không tự `find` rồi `save` thiếu CAS.

### 17.2. Unknown outcome trong interface thực

Ví dụ tối giản giả sử port trả một trong các outcomes ổn định. Adapter production cần type hoặc exception riêng cho **ambiguous commit** để caller resolve/retry cùng commandId, không gộp vào `Insufficient`.

### 17.3. Không coi `KeyConflict` là cạnh tranh stock

Nó chỉ xuất hiện khi cùng commandId dùng nghĩa khác. Hai distinct commandIds tranh hết stock có thể nhận `Insufficient`, không phải key conflict.

### 17.4. Bảo vệ quyền truy cập

Constructor nhận tenantId sau khi server đã xác thực/ủy quyền. Tránh cho mobile body chọn tenant khác.

## 18. Java: fake atomic authority để định nghĩa bài test

Fake sau dùng lock toàn JVM để **mô phỏng đúng một điểm commit trong bộ nhớ**. Nó chỉ phục vụ unit test/giải thích; **không phải implementation production**, vì không bền khi crash và không bảo vệ nhiều process.

~~~java
import java.util.HashMap;
import java.util.Map;

public final class InMemoryReservationFake
    implements ReservationPort {

    private record StockKey(String tenantId, String sku) {}
    private record ReceiptKey(
        String tenantId, String operation, String commandId) {}
    private record Stock(int available, long version) {}
    private record Receipt(
        ReserveCommand original, ReserveOutcome result) {}

    private final Map<StockKey, Stock> stock = new HashMap<>();
    private final Map<ReceiptKey, Receipt> receipts = new HashMap<>();
    private int committedReservations;

    public synchronized void seed(
            String tenantId, String sku, int available) {
        if (available < 0) throw new IllegalArgumentException();
        stock.put(new StockKey(tenantId, sku),
            new Stock(available, 0));
    }

    @Override
    public synchronized ReserveOutcome reserveOrReplay(
            ReserveCommand cmd) {
        ReceiptKey receiptKey = new ReceiptKey(
            cmd.tenantId(), "RESERVE", cmd.commandId());
        Receipt prior = receipts.get(receiptKey);
        if (prior != null) {
            return prior.original().equals(cmd)
                ? prior.result()
                : new KeyConflict();
        }

        StockKey key = new StockKey(cmd.tenantId(), cmd.sku());
        Stock current = stock.get(key);
        ReserveOutcome result;

        if (current == null) {
            result = new UnknownItem();
        } else if (current.available() < cmd.quantity()) {
            result = new Insufficient(current.available());
        } else {
            int next = current.available() - cmd.quantity();
            long newVersion = current.version() + 1;
            stock.put(key, new Stock(next, newVersion));
            committedReservations++;
            result = new Reserved(
                "RES#" + cmd.tenantId() + "#" + cmd.commandId(),
                next,
                newVersion);
        }
        // Fake critical section stands for an atomic business
        // state + receipt commit at the real storage authority.
        receipts.put(receiptKey, new Receipt(cmd, result));
        return result;
    }

    public synchronized int available(
            String tenantId, String sku) {
        return stock.get(new StockKey(tenantId, sku)).available();
    }

    public synchronized int commits() {
        return committedReservations;
    }

    public synchronized int receiptCount() {
        return receipts.size();
    }
}
~~~

### 18.1. Điều bảo vệ trong fake

Chỉ một thread có thể kiểm stock và ghi receipt tại một thời điểm. Vì fake dùng một monitor, các yêu cầu cạnh tranh không oversell trong **cùng JVM**.

### 18.2. Hợp đồng failure

Ở đây cả `Insufficient` và `UnknownItem` đều được ghi như terminal receipts; production có thể chọn khác nhưng phải nhất quán và công bố rõ.

### 18.3. Fake chưa mô phỏng durable commit

Khi process mất, map mất. Mọi bài integration về retry sau crash phải thay fake bằng real datastore với receipt durable.

### 18.4. Cẩn trọng về ID

`"RES#"+tenant+"#"+commandId` chỉ minh họa; production nên dùng typed/binary-safe key framing để tránh delimiter collisions và kiểm length/charset.

### 18.5. Chưa có TTL và outbox

Với production, thêm receipt retention, unique reservation rows và outbox event được commit atomically hoặc bằng một giao thức recoverable.

## 19. JUnit: hai yêu cầu khác nhau giành một suất

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;

final class InventoryConcurrencyTest {
    @Test
    void onlyOneDistinctCommandWinsLastSeat() throws Exception {
        InMemoryReservationFake store =
            new InMemoryReservationFake();
        store.seed("T1", "SEAT-17", 1);

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        try {
            List<Future<ReserveOutcome>> jobs = new ArrayList<>();
            for (int i = 0; i < 2; i++) {
                final String id = "command-" + i;
                jobs.add(pool.submit(() -> {
                    ready.countDown();
                    if (!start.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("gate timeout");
                    }
                    return store.reserveOrReplay(
                        new ReserveCommand("T1", "SEAT-17", id, 1));
                }));
            }
            assertTrue(ready.await(5, TimeUnit.SECONDS));
            start.countDown();

            int successful = 0;
            for (Future<ReserveOutcome> job : jobs) {
                ReserveOutcome result = job.get(
                    10, TimeUnit.SECONDS);
                if (result instanceof Reserved) {
                    successful++;
                } else {
                    assertInstanceOf(Insufficient.class, result);
                }
            }
            assertEquals(1, successful);
            assertEquals(1, store.commits());
            assertEquals(0, store.available("T1", "SEAT-17"));
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

### 19.1. Tại sao dùng barrier?

`CountDownLatch` tạo cơ hội cho hai tasks bắt đầu gần đồng thời. Chỉ gọi A xong rồi B là test sequential, không bóc race.

### 19.2. Fake pass chưa phải NoSQL pass

Test lại cùng scenario trên service nhiều instances và database adapter thật. Network scheduling có thể khiến requests không overlap; nên dùng failpoints/barriers gần storage nếu cần tái tạo interleaving chắc chắn.

### 19.3. Oracle gồm nhiều trạng thái

Một success, tồn kho 0, đúng một reservation và version tăng một lần. Trong fake ta đo `commits`, production phải kiểm reservation/receipt/outbox records thực.

## 20. JUnit: 100 retries cùng commandId

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;

final class ReservationIdempotencyTest {
    @Test
    void sameCommandHasOneEffect() throws Exception {
        InMemoryReservationFake store =
            new InMemoryReservationFake();
        store.seed("T1", "SEAT-17", 10);
        ReserveCommand cmd =
            new ReserveCommand("T1", "SEAT-17", "K1", 1);

        int n = 100;
        ExecutorService pool = Executors.newFixedThreadPool(n);
        CountDownLatch ready = new CountDownLatch(n);
        CountDownLatch go = new CountDownLatch(1);
        try {
            List<Future<ReserveOutcome>> jobs = new ArrayList<>();
            for (int i = 0; i < n; i++) {
                jobs.add(pool.submit(() -> {
                    ready.countDown();
                    if (!go.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("gate timeout");
                    }
                    return store.reserveOrReplay(cmd);
                }));
            }
            assertTrue(ready.await(5, TimeUnit.SECONDS));
            go.countDown();
            String reservationId = null;
            for (Future<ReserveOutcome> job : jobs) {
                Reserved result = assertInstanceOf(
                    Reserved.class, job.get(10, TimeUnit.SECONDS));
                if (reservationId == null) {
                    reservationId = result.reservationId();
                }
                assertEquals(reservationId, result.reservationId());
            }
            assertEquals(9, store.available("T1", "SEAT-17"));
            assertEquals(1, store.commits());
            assertEquals(1, store.receiptCount());
        } finally {
            go.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

### 20.1. Kết quả khác test trước

Hai distinct keys tranh một suất chỉ một thắng; 100 attempts **cùng một key** phải cùng phản hồi một reservation đã commit, không trừ 100 lần.

### 20.2. Concurrent retries và timeout

Nếu adapter trả `IN_PROGRESS` khi winner chưa commit, test theo API contract có thể cho bounded wait/202 trước eventual replay. Fake này linearize toàn bộ call nên trả kết quả ngay.

### 20.3. Test khác payload cùng key

Gửi K1 quantity=1 rồi K1 quantity=2: phải trả `KeyConflict` và không thay stock. Fake so toàn bộ typed command; production so canonical semantic fingerprint.

## 21. MongoDB: atomic conditional update trên một document

Trong MongoDB, một update trên **một document** có thể kết hợp filter condition và `$inc` theo atomic operation. Ví dụ minh họa dùng Java MongoDB driver:

~~~java
import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;
import static com.mongodb.client.model.ReturnDocument.AFTER;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.FindOneAndUpdateOptions;
import org.bson.Document;

public Document tryDecrease(
        MongoCollection<Document> inventory,
        String trustedTenant,
        String sku,
        int quantity) {
    if (quantity <= 0) throw new IllegalArgumentException();

    return inventory.findOneAndUpdate(
        and(eq("tenantId", trustedTenant),
            eq("sku", sku),
            gte("available", quantity)),
        combine(inc("available", -quantity),
                inc("version", 1)),
        new FindOneAndUpdateOptions().returnDocument(AFTER));
}
~~~

### 21.1. Điều kiện phải là một phần của filter

Không tìm document trước rồi gọi `updateOne` chỉ theo `_id` mà không còn `available >= quantity`. Bảo vệ phải tồn tại tại update.

### 21.2. `null` không chỉ nghĩa thiếu stock

`findOneAndUpdate` không match có thể do item không tồn tại, tenant sai, qty không đủ hoặc filter khác. Phân biệt bằng read phù hợp và authorization, tránh tiết lộ dữ liệu tenant.

### 21.3. Cần unique key/index

Đảm bảo mỗi `(tenantId,sku)` đại diện đúng một inventory document bằng unique key/index nếu schema cho phép; nếu có duplicate documents, điều kiện trên một document không bảo vệ tổng inventory.

### 21.4. Idempotency là bài toán riêng

Lệnh trên có thể trừ hai lần khi cùng request bị retry và vẫn còn stock. Muốn receipt/reservation/outbox cần transaction phù hợp hoặc cùng aggregate bounded.

### 21.5. MongoDB transaction scope

MongoDB có transactions nhiều documents với giới hạn và yêu cầu cấu hình/version; trong transaction có thể ghi receipt unique, update Inventory và tạo Reservation/Outbox. Cần xử lý transaction conflicts và unknown commit results theo driver semantics, không gửi external side effects trong callback có thể retry.

## 22. DynamoDB: conditional `UpdateItem`

Trong DynamoDB, một item update có thể kết hợp điều kiện và arithmetic update:

~~~text
Key:
    PK = INV#T1#SEAT-17

UpdateExpression:
    SET #available = #available - :quantity,
        #version = #version + :one

ConditionExpression:
    attribute_exists(PK) AND #available >= :quantity

ExpressionValues:
    :quantity = 1
    :one = 1
~~~

Đây là **mẫu biểu thức**; khi code Java AWS SDK cần khai báo expression attribute names/values và key đúng bảng.

### 22.1. `ConditionCheckFailed` là kết quả cạnh tranh bình thường

Khi hết stock, một request có thể bị condition fail; đây không nhất thiết là lỗi hạ tầng cần retry. Tách `Insufficient` và `VersionConflict` theo hợp đồng.

### 22.2. Dùng version khi có read–modify–write

Thêm `#version = :expected` vào condition khi update phụ thuộc snapshot cũ. Nhưng đừng retry bằng cách bỏ version.

### 22.3. Transaction nhiều items

Với `TransactWriteItems`, có thể tạo receipt unique (conditional Put), cập nhật Inventory có điều kiện, tạo Reservation unique và Outbox trong **một transaction trong giới hạn API**. Nếu commandId đã được ghi, đọc receipt để replay result và kiểm fingerprint.

### 22.4. Client transaction token có giới hạn

Một SDK transaction idempotency token có cửa sổ và semantics do service định nghĩa; không dùng nó thay durable business receipt cho retry sau nhiều giờ/ngày.

### 22.5. Partitioning và chi phí

Ghi vào một hot inventory key có thể bị throttling dù table còn capacity; transaction/conditional write có cost và contention. Không tách cùng inventory thành nhiều independent keys nếu làm vỡ invariant.

## 23. Cosmos DB for NoSQL: ETag và transactional batch

### 23.1. Một document CAS

Đọc item cùng ETag; ghi replace/patch với `If-Match` khi API hỗ trợ. Nếu ETag đổi, thao tác bị từ chối để ngăn ghi đè trên snapshot cũ.

### 23.2. Điều kiện stock

Chỉ dùng ETag là chưa đủ nếu code không validate `available>=qty` từ version đã đọc. Tính next từ snapshot, rồi CAS theo ETag; khi conflict, đọc lại và **revalidate business condition**.

### 23.3. Transactional batch cùng logical partition

Khi Inventory, Receipt, Reservation và Outbox cùng logical partition key và nằm trong limits, transactional batch có thể đảm bảo chúng commit atomically. Nếu trải nhiều logical partitions, đừng suy atomicity toàn cục từ API batch.

### 23.4. 412/429 khác nhau

Precondition failed có thể là concurrency conflict; 429 là throughput throttling. Retry policy phải phân loại và giữ commandId/expected semantics.

### 23.5. Data model ảnh hưởng transaction

Chọn partition key theo aggregate nghiệp vụ có thể tạo giao dịch đơn giản, nhưng hot partition/fan-out lại tăng. Phải đo cả transaction scope, tải và chi phí RU.

## 24. Cassandra/ScyllaDB: LWT và CAS phiên bản

Cassandra/ScyllaDB thường thiết kế table theo partition key; LWT/conditional statements cho phép compare-and-set theo phạm vi và consistency được engine hỗ trợ.

~~~sql
-- Mẫu ý tưởng cho item có version:
UPDATE inventory
SET available = ?, version = ?
WHERE tenant_id = ? AND sku = ?
IF version = ?;
~~~

Ở service, trước khi gọi, đã đọc `(available,version)` đủ nhất quán theo protocol, kiểm `available >= qty`, tính `nextAvailable = available - qty`, `nextVersion = version + 1`, rồi thử conditional update. Nếu LWT báo không áp dụng, đọc lại và revalidate.

### 24.1. CAS chống update từ snapshot cũ

Hai writers cùng expected version v5: chỉ một được nâng lên v6; writer kia phải re-read, không ghi next value tính từ v5.

### 24.2. LWT không biến nhiều partitions thành transaction tùy ý

Receipt, Inventory, Reservation ở những partitions khác nhau có thể không được bảo vệ trong một atomic transaction chung. Cần authority design/recovery state machine.

### 24.3. Serial consistency và timeout

LWT có serial consistency/quorum semantics, latency và timeout behavior theo engine/config. Một timeout có thể ambiguous; cần resolve ở authority trước khi retry command.

### 24.4. Tránh blind batch

Logged batch của Cassandra không tự cung cấp transactional isolation giống một RDBMS transaction trên mọi partitions.

### 24.5. Contention

Một hot key nhận nhiều LWT có thể có độ trễ cao; bổ sung queue per aggregate, giảm writes hoặc thay domain decomposition nếu cần.

## 25. Redis: atomic Lua nhưng cần hiểu durability

Redis Lua script có thể kiểm state và decrement trong một atomic execution trên server/slot phù hợp:

~~~lua
-- KEYS[1] = inventory hash key
-- ARGV[1] = positive quantity
local q = tonumber(ARGV[1])
if not q or q <= 0 then
    return redis.error_reply("invalid quantity")
end
local available = tonumber(redis.call("HGET", KEYS[1], "available"))
if not available then
    return redis.error_reply("missing inventory")
end
if available < q then
    return {0, available}
end
local next = redis.call("HINCRBY", KEYS[1], "available", -q)
redis.call("HINCRBY", KEYS[1], "version", 1)
return {1, next}
~~~

### 25.1. Atomic không tự bảo đảm retry idempotent

Nếu script không kiểm receipt key, gửi lại cùng command khi stock còn có thể decrement thêm. Một bản đầy đủ phải kiểm/stamp receipt trong cùng atomic slot/scope, với TTL phù hợp.

### 25.2. Redis Cluster có slot constraints

Nhiều keys trong script cần cùng hash slot theo Redis Cluster rules. Hash tags có thể giúp locality nhưng có nguy cơ hot slot.

### 25.3. Durability/failover

Atomic execution không đồng nghĩa ACKed updates tồn tại sau mọi failover; AOF/RDB/replication settings ảnh hưởng guarantees. Test đúng failure model.

### 25.4. Redis làm cache không nên là authority cho stock

Nếu authoritative inventory ở database khác, Lua script trên cache không thể bảo vệ invariant của database đó. Single source of truth phải rõ ràng.

## 26. Firestore: transaction callback và versioned preconditions

### 26.1. Transaction trong phạm vi API

Firestore có transaction primitives, thực hiện reads rồi writes với concurrency/retry semantics được SDK hỗ trợ. Dùng nó để kiểm stock và ghi state/receipt nếu thỏa limits và model.

### 26.2. Callback có thể chạy lại

Không gửi email/charge payment trực tiếp trong transaction callback. Một HTTP command có thể khiến callback được thực thi nhiều lần, dù only one DB commit.

### 26.3. Server timestamps và preconditions

Không dùng timestamp local như một CAS token tự phát. Dùng transaction/update precondition được storage hỗ trợ và revalidate invariant trong callback.

### 26.4. Read cost và contention

Hot documents/transaction retries có thể tăng latency và billable operations; test p95/p99 cùng conflict ratio.

## 27. Couchbase và document CAS

Một số KV/document stores như Couchbase cung cấp CAS token; client đọc document kèm CAS rồi replace chỉ khi token còn phù hợp.

### 27.1. ETag/CAS là token, không là timestamp

Không tự so `updatedAt` rồi cho rằng không ai viết cùng thời điểm. Sử dụng server token và điều kiện tại write.

### 27.2. Một document vs nhiều documents

CAS tốt cho state một document. Nếu cần nhiều collections/keys atomically, kiểm khả năng transaction, isolation và failure recovery của version/deployment.

### 27.3. Retry

Sau CAS conflict, tải state mới, re-evaluate business transition; không ném lại payload cũ vô điều kiện.

## 28. Transaction retries phải bảo vệ side effects

~~~text
BEGIN
  conditional stock update
  create unique reservation
  create receipt
  create outbox event
COMMIT

After commit:
  outbox publisher sends external notification
~~~

### 28.1. Không gửi mail trong transaction callback

Database driver hoặc framework có thể retry transaction; SMTP có thể gửi hai lần dù cuối cùng một DB transaction commit.

### 28.2. Outbox nằm trong commit

Outbox event ghi cùng business state trong transactional boundary phù hợp. Publisher có thể redeliver, consumer phải dedupe theo stable `eventId`.

### 28.3. Idempotency ở payment provider

Nếu command gọi bên thứ ba, dùng provider-supported idempotency key và reconciliation. NoSQL transaction không thể thường xuyên commit đồng thời với remote charge.

### 28.4. Không chắc commit thì resolve

Một timeout sau commit là outcome unknown. Retry nên tra receipt/command status, không tự kết luận transaction rollback.

### 28.5. Nhiều cấp retry

HTTP client, gateway, service và SDK có thể cùng retry. Dùng deadline/backoff/jitter, giữ stable commandId và tính retry amplification.

## 29. Retry policy theo từng loại lỗi

| Kết quả | Ý nghĩa | Phản ứng |
|---|---|---|
| `INSUFFICIENT` | Business precondition không đạt | Trả lỗi nghiệp vụ/receipt |
| `VERSION_CONFLICT` | State thay đổi từ snapshot | Reload + re-evaluate hoặc trả 409 |
| `KEY_REUSE_CONFLICT` | Cùng key, payload khác | Không retry với key đó |
| `THROTTLED` | Resource/rate limit | Backoff/jitter, bounded retry |
| `TRANSIENT_UNAVAILABLE` | DB/service lỗi tạm | Bounded retry theo semantics |
| `UNKNOWN_COMMIT` | Có thể commit hoặc không | Resolve receipt; retry cùng ID |
| `AUTH_DENIED` | Không có quyền | Không retry tự động |
| `INVALID_INPUT` | Schema/business validation | Yêu cầu sửa request |
| `LOCK_TIMEOUT` | Không lấy được guard | Kiểm lease/fencing và retry có giới hạn |

### 29.1. Conflict không phải luôn transient infrastructure error

CAS conflict do users cùng chỉnh Order là tình huống nghiệp vụ bình thường. Retry vô hạn có thể tạo starvation và tăng contention.

### 29.2. Đọc lại và revalidate

Nếu client muốn “đặt một suất khi còn”, sau conflict có thể đọc available mới rồi thử lại có điều kiện. Nếu user muốn “chỉ update đúng version đã thấy”, nên trả conflict thay vì tự đổi yêu cầu.

### 29.3. Retry vẫn cần idempotency

Một request timeout có thể đã commit, vì vậy mọi attempt của cùng ý định dùng cùng commandId và replay receipt.

### 29.4. Retry budget phải hữu hạn

Nếu 1000 clients cùng tranh một item, retry tức thì làm contention tăng. Backoff/jitter/queue per aggregate có thể cải thiện ổn định.

## 30. Deadlock, livelock và starvation

### 30.1. Deadlock

Hai transactions giữ tài nguyên theo thứ tự ngược nhau và chờ nhau. Hệ engine có thể phát hiện/abort; application phải xử lý rollback/retry có giới hạn.

### 30.2. Livelock

Writers liên tục conflict/retry và không ai tiến triển đủ nhanh, đặc biệt khi optimistic retries không backoff dưới tải cao.

### 30.3. Starvation

Một request liên tục thua CAS trong khi requests khác thành công. Correctness vẫn có thể đúng nhưng latency/tính công bằng không đạt SLO.

### 30.4. Khóa theo thứ tự cố định

Nếu transaction/update nhiều entities, chọn deterministic lock/order khi engine/application cho phép để giảm deadlock.

### 30.5. Timeout và cancellation

Client cancel không chứng minh server chưa commit. Với API phi đồng bộ, cần trả `PENDING/UNKNOWN` và tra trạng thái để tránh double effect.

## 31. Distributed lock, lease và fencing token

### 31.1. Vì sao lock TTL có thể nguy hiểm?

Worker A giữ lease 10 giây rồi bị pause 15 giây. Lease hết; worker B lấy lease mới và ghi. Khi A tỉnh dậy, nếu A vẫn ghi được, có hai active writers.

### 31.2. Fencing token

Mỗi lease/owner epoch có token tăng đơn điệu. Nơi ghi phải từ chối stale token, không chỉ kiểm ở Java client.

### 31.3. Lock không thay conditional invariant

Ngay cả đã khóa, code cũng cần validate stock và status tại authority; stale lock hoặc bug vẫn có thể phá state.

### 31.4. Ưu tiên CAS khi đủ

Một CAS server-side thường đơn giản hơn tự xây distributed lock service. Chỉ dùng lock/lease khi workflow thực cần exclusive control vượt một conditional write.

## 32. Multi-region và conflict resolution

### 32.1. Hai regions cùng ghi

Nếu hai regions đều cho phép reserve cùng `seatId` độc lập rồi merge asynchronous, có thể xuất hiện double booking trước khi conflict được phát hiện.

### 32.2. Last-write-wins không cứu invariant

LWW có thể giữ một reservation và làm mất reservation còn lại đã ACK; người dùng vẫn có thể nhận hai confirmations.

### 32.3. Single authority hoặc protocol phân bổ

Cho một region/partition quyền xử lý seat reservation hoặc dùng escrow/quota allocation có chứng minh; lựa chọn phụ thuộc độ trễ, availability và business risk.

### 32.4. Network partition

Không thể tự vừa cho phép hai bên độc lập ghi mọi invariant, vừa bảo đảm không xung đột nếu không có coordination/protocol tương ứng. Cần chọn failure semantics rõ.

### 32.5. Test failover

Đo acknowledged writes có sống sau failover theo durability contract, fencing old owner, retry idempotent và eventual convergence của projections.

## 33. Test dữ liệu đúng, không chỉ response đúng

Một phép thử có 100 requests, 10 initial seats:

~~~text
Expected authoritative conditions:
    available >= 0
    available + sum(activeReservation.quantity) == initialSeats
    every reservationId is unique
    one receipt per scoped commandId
    no same commandId with two distinct committed payloads
    all acknowledged commits are present
    event/outbox count corresponds to business commits
~~~

### 33.1. Đọc nguồn có thẩm quyền

Đừng kiểm invariant bằng cache hoặc search projection có lag. Đọc source với consistency phù hợp sau khi tất cả writes/transactions/retries đã settle.

### 33.2. Đếm successful HTTP responses chưa đủ

Một request có thể commit nhưng response timeout. Khi đối soát, xem receipt và authoritative state của các outcomes unknown.

### 33.3. Số lượng stock đúng chưa đủ

`available=0` cùng 11 reservations vẫn sai. Sum invariant giúp phát hiện oversell dù stock tự giới hạn.

### 33.4. Negative assertion

Kiểm không có duplicate receipt, không có reservation cho tenant khác, không xuất hiện status transition bất hợp lệ và không có event side effect hai lần.

## 34. Ma trận test cạnh tranh và lỗi

| Case | Lịch biểu | Oracle |
|---|---|---|
| C01 | Một reservation, stock đủ | Commit đúng một lần |
| C02 | Hai distinct keys, một suất | Chỉ một success |
| C03 | 100 distinct keys, 10 suất | Tối đa 10 success; không âm |
| C04 | 100 attempts cùng commandId | Một effect, same result |
| C05 | Cùng key, khác qty | Key conflict |
| C06 | Two writers same version | Một CAS thắng |
| C07 | CAS fail rồi retry có revalidate | Không overwrite stale |
| C08 | Two transactions read shared predicate | Không write skew |
| C09 | Crash trước commit | Không partial business success |
| C10 | Crash sau commit trước response | Retry replay receipt |
| C11 | Failover khi commit | ACKed writes được bảo toàn theo policy |
| C12 | Receipt TTL expire | Hành vi theo dedupe horizon |
| C13 | Outbox event redelivered | Effect downstream không nhân |
| C14 | 429/timeout storm | Retry bounded, invariant giữ |
| C15 | Tenant collision | Không leak/chia sai namespace |
| C16 | Multi-region split | Không hai authorities ghi cùng seat |
| C17 | Cancellation sau dispatch | Resolve outcome, không double |
| C18 | Unique slot concurrent insert | Một active booking |

### 34.1. Test tuần tự không thay test concurrency

`reserve(); reserve();` chứng minh hành vi thứ tự nhưng không thể hiện race “cả hai cùng đọc old state”.

### 34.2. Test concurrency không thay test unknown outcome

Hai yêu cầu tranh một key và mất ACK sau commit là hai failure modes khác. Phải test cả hai.

### 34.3. Fault injection đúng thời điểm

Để mô phỏng “commit rồi mất ACK”, chặn response **sau** khi storage đã commit, không đơn giản ném exception trước DB call.

### 34.4. Test timeouts cần deadline

Không để stress test treo vô hạn. Bound worker joins/futures và ghi scheduler seed/fault markers để tái hiện.

## 35. Fault injection: bốn điểm cắt then chốt

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant D as NoSQL
    C->>A: Reserve(commandId=K)
    A->>D: Atomic conditional transaction
    Note over A,D: Fault F1 before DB request
    Note over D: Fault F2 during transaction
    D-->>A: COMMITTED
    Note over A,C: Fault F3 drop response after commit
    C->>A: Retry same K
    A->>D: Resolve K receipt
    D-->>A: Previous committed result
    A-->>C: Replay result
    Note over A,D: Fault F4 process restart/re-delivery
~~~

### 35.1. F1 — trước khi ghi

Không có effect; retry cùng key có thể là attempt đầu thật.

### 35.2. F2 — trong commit

Driver có thể trả conflict, transaction abort, timeout hoặc unknown result. Adapter phải phân biệt và resolve theo API.

### 35.3. F3 — commit xong nhưng response mất

Đây là case hay bị bỏ sót. Không có business effect thứ hai sau retry và phải trả đúng reservationId đã commit.

### 35.4. F4 — restart và delivery lặp

Receipts/outbox phải bền và hồi phục được; in-memory lock/cache không đủ.

## 36. Test nhiều writers trong thực tế

### 36.1. Nhiều JVM instances

Chạy ít nhất hai API replicas dùng chung DB authority; requests cùng key được gửi xen kẽ. Local `synchronized` không bảo vệ chúng.

### 36.2. Nhiều loại writers

API, scheduled job, admin batch, CDC processor và service cũ phải cùng tuân thủ CAS/transaction. Một writer bypass điều kiện có thể phá invariant.

### 36.3. Kết hợp distinct và duplicate intents

Không dùng toàn commands trùng key (chỉ test idempotency) hoặc toàn distinct keys (chỉ test competition). Mix để kiểm cả hai.

### 36.4. Hot key workload

Khi 10.000 clients tranh một SKU, test throughput, p95/p99, failed CAS ratio, retry storms và fairness. Có thể cần queue per aggregate nếu contention quá cao.

### 36.5. Multiple partitions

Với batch reservation nhiều SKUs, tạo cases item cùng partition và khác partitions để xác nhận transaction boundaries thực.

## 37. Isolation levels: xây phép thử phân biệt

### 37.1. Dirty read

Đọc state chưa commit rồi đưa ra quyết định có thể sai nếu transaction rollback. Xác minh read semantics của engine.

### 37.2. Non-repeatable read

Cùng transaction đọc một document hai lần và nhận giá trị khác; có thể ảnh hưởng logic cần snapshot.

### 37.3. Phantom

Hai lần query predicate (ví dụ count active reservations) cho kết quả khác vì concurrent inserts. Cần predicate-safe algorithm nếu invariant dựa vào “không có ai”.

### 37.4. Lost update

Hai transactions cùng ghi một document từ snapshot cũ; CAS/version hoặc transaction write conflict phải ngăn một update bị mất.

### 37.5. Write skew

Hai transactions ghi tài liệu khác nhau dựa trên cùng predicate; snapshot isolation có thể cho cả hai commit. Cần serializable/guard item.

### 37.6. Không dùng một tên isolation để suy mọi hành vi

Các engine có tài liệu về snapshot, read committed, serializable, eventual, quorum... nhưng API guarantees khác nhau. Viết test và trích contract của đúng backend/config.

## 38. Case study: hai lần thanh toán cùng giỏ hàng

Một Order `NEW` được client gửi hai request `PAY` vì response mất.

### 38.1. Không đủ nếu chỉ CAS `status=NEW`

Nếu charge external payment trước khi CAS Order, có thể đã charge hai lần rồi chỉ một DB update được commit.

### 38.2. Stable payment intent

Tạo payment intent ID/commandId durable, dùng provider idempotency key và ghi receipt để theo dõi `PENDING/PAID/FAILED` theo protocol.

### 38.3. Transaction boundary

Order status và internal outbox/receipt có thể commit cùng database transaction nếu engine hỗ trợ; provider charge bên ngoài phải reconciled.

### 38.4. Test

Drop provider ACK, retry API, concurrent callback, duplicate webhook, refund/cancel race; kiểm một charge và một ledger posting theo authoritative provider/ledger.

## 39. Case study: inventory + reservation khác partitions

Inventory keyed `(tenantId,sku)` nhưng Reservation keyed `(tenantId,bookingId)`. Engine chỉ atomic trong một logical partition.

### 39.1. Vấn đề

Trừ Inventory thành công, tạo Reservation thất bại; hai records không commit cùng nhau. Lặp request có thể trừ tiếp.

### 39.2. Giải pháp A: đổi key để đồng vị trí

Thiết kế keys để các records thuộc một aggregate nằm cùng transactional partition nếu phù hợp sizing/hotspot constraints.

### 39.3. Giải pháp B: một authority + projection

Inventory/Reservation claim có thể được biểu diễn trong một authority item/ledger; những read models khác được cập nhật bằng outbox/CDC idempotent.

### 39.4. Giải pháp C: saga có trạng thái

Reservation lifecycle `PENDING -> CONFIRMED/COMPENSATED`, durable command IDs, compensation idempotent và recovery. Cần nêu rõ lúc nào khách hàng được thông báo thành công.

### 39.5. Không coi eventual repair là no-oversell

Nếu hai users được ACK booking rồi background job hủy một booking, có thể vi phạm cam kết nghiệp vụ, dù “cuối cùng” data nhất quán.

## 40. Case study: write skew “ít nhất một người trực”

Hai bác sĩ cùng đọc A/B đang `ON`, rồi mỗi người tắt lịch trực của mình.

### 40.1. CAS trên từng bác sĩ

Mỗi document có version riêng; hai writes không tranh nhau. Cả hai có thể commit dưới snapshot isolation.

### 40.2. Guard document

Một `ScheduleGuard` có `onCallCount/version`; cả hai transactions cần cập nhật guard bằng CAS/serializable protection. Chỉ một được giảm từ 1 xuống 0 nếu điều kiện `onCallCount>1` đang đúng.

### 40.3. Guard phải được cập nhật cùng state

Nếu chỉ decrement guard rồi sau đó update doctor ngoài transaction, guard và thực tế có thể lệch. Transaction/authority boundary cần bao gồm cả hai hoặc có recoverable protocol.

### 40.4. Test invariant

Hai requests thử tắt cùng lúc; sau khi settle, `count(ON) >= 1`, guard tương ứng và không có confirmed response cho trạng thái không được commit.

## 41. Case study: hủy reservation đến trễ

Timeline:

~~~text
T1: Client A reserves seat S with reservationId=R1
T2: A cancels R1, seat becomes FREE
T3: Client B reserves same seat as R2
T4: Delayed retry of A's cancellation arrives
~~~

### 41.1. Delete theo seatId là nguy hiểm

Nếu cancel R1 chỉ `set seat FREE` theo seatId, delayed cancel có thể xóa claim R2.

### 41.2. Điều kiện theo current owner

Chỉ release khi `activeReservationId == R1` và version/epoch phù hợp. Nếu owner hiện là R2, cancel R1 là no-op/replay theo receipt.

### 41.3. Idempotent release

Release R1 hai lần không được cộng stock hai lần. Dùng reservation state transition có điều kiện và receipt.

### 41.4. Test

Chạy reserve A, cancel A, reserve B, retry cancel A; cuối cùng seat vẫn thuộc B và available đúng.

## 42. Observability cho cập nhật cạnh tranh

| Metric | Ý nghĩa |
|---|---|
| `inventory_attempts_total` | Tất cả attempts |
| `inventory_commits_total` | Business effects đã commit |
| `inventory_insufficient_total` | Business rejections |
| `inventory_cas_conflicts_total` | Stale version/conflicting writers |
| `idempotency_replays_total` | Retry được xử lý từ receipt |
| `idempotency_key_conflicts_total` | Key reuse khác payload |
| `transactions_aborted_total` | Transaction aborts theo loại |
| `transactions_unknown_total` | Commit outcome chưa rõ |
| `reservation_orphans_total` | Stock/reservation mismatch |
| `outbox_lag_seconds` | Side effect materialization delay |
| `negative_stock_violations_total` | Bất biến bị vi phạm |
| `retry_attempts_total` | Amplification/overload |

### 42.1. Conflict rate cao không nhất thiết sai

CAS conflicts có thể là cơ chế đang ngăn lost updates. Nhưng quá nhiều conflicts tạo latency/cost cao và có thể đòi thay data model.

### 42.2. Không log full idempotency keys vào metric label

Keys có cardinality cao và có thể chứa dữ liệu nhạy cảm. Dùng operation/result/tenant tier bounded; logs có phân quyền và redaction.

### 42.3. Trace retries cùng business command

HTTP attempts có trace IDs khác nhau nhưng commandId phải ổn định. Correlate chúng để phân biệt retry từ client, gateway và SDK.

### 42.4. Audit committed effects

Lưu commit version, reservationId và outbox event ID phù hợp. Một status HTTP “success” không phải receipt durable.

## 43. Performance cost và cách giảm contention

### 43.1. CAS không miễn phí

Mỗi failed CAS có thể tiêu tốn read/write units, network RTT và CPU. Ở hot key, optimistic retry có thể lãng phí nhiều tài nguyên.

### 43.2. Transaction rộng thường đắt hơn

Multi-item transactions có overhead, lock/validation/conflict handling và throughput limits. Chỉ đưa vào cùng transaction những records bất biến thực sự cần đồng bộ.

### 43.3. Chia aggregate tùy invariant

Nếu booking các ghế độc lập, partition theo seat có thể phân tán. Nếu quota toàn chuyến cần giữ nghiêm ngặt, không thể chia quota mù thành nhiều counters mà không có protocol phân quyền suất.

### 43.4. Queue per hot entity

Một sequencer/queue theo SKU giảm tranh CAS nhưng phải xử lý durable enqueue, worker crash, ordering và lag; không mặc định queue khôi phục correctness khi command đã được ACK sớm.

### 43.5. Escrow/quota allocation

Có thể phân bổ quota hữu hạn cho nhiều shards với bảo toàn tổng, nhưng cần chứng minh không phát hành quá quota và có reclaim protocol cho failed nodes.

### 43.6. Đo tail latency

Đo p95/p99, conflicts, retry attempts, successful commands/s, hot key distribution và side effects; throughput CRUD không đủ đánh giá thiết kế.

## 44. Quy trình thực hành end-to-end

### Bước 1 — Ghi invariant

`available>=0`, một reservation mỗi scoped commandId, một owner mỗi seat/slot, no acknowledged data loss và tenant isolation.

### Bước 2 — Viết bản cố tình sai

Đọc `available`, kiểm ở Java, rồi update bằng value tính sẵn không có điều kiện. Tạo concurrency test để thấy oversell/lost update, chỉ trong môi trường test.

### Bước 3 — Sửa một-item conditional update

Dùng atomic predicate/`$inc`/CAS/ETag/LWT/Lua phù hợp backend. Chạy lại test hai requests tranh một suất.

### Bước 4 — Thêm receipt idempotency

Chọn namespace, fingerprint, TTL và outcome; bảo vệ claim+business write trong một transaction hoặc recovery protocol. Test 100 retries cùng key.

### Bước 5 — Thêm reservation + outbox

Ghi business records trong transaction boundary được hỗ trợ; nếu không, dùng authoritative state machine và kiểm partial failure recovery.

### Bước 6 — Test error và timeout

Drop ACK sau commit, kill/restart API, failover DB trong sandbox, redeliver outbox event; kiểm authoritative receipts và states.

### Bước 7 — Test nhiều partitions

Đưa Inventory và Reservation vào hai partition keys, xác nhận không giả định transaction vượt scope. Viết phương án đồng vị trí hoặc saga.

### Bước 8 — Test write skew

Hai doctors cùng off-call; chứng minh CAS trên từng document chưa đủ, thêm guard/serializable solution.

### Bước 9 — Đo chi phí

So single-item CAS với transaction rộng về p99, conflict rate, retries, billable RU/IO và capacity.

### Bước 10 — Chốt contract

Mô tả khi nào API trả success, 409, insufficient, pending/unknown; hướng client giữ commandId và cách hệ phục hồi.

## 45. Checklist trước khi đưa cập nhật cạnh tranh vào production

1. Bất biến nghiệp vụ đã được mô tả bằng biểu thức kiểm được chưa?
2. Nguồn có thẩm quyền cho từng entity/aggregate có rõ chưa?
3. Có biết đúng **atomicity/transaction scope** của engine/version không?
4. Mọi writer đều đi qua cùng conditional/transaction protocol chưa?
5. Có ngăn `read-check-save` không điều kiện chưa?
6. Condition kiểm state đang commit, không chỉ cache chưa?
7. Có dùng CAS/version/ETag khi update dựa trên snapshot không?
8. Version increment trong cùng atomic operation chưa?
9. Có tách conflict nghiệp vụ khỏi timeout/throttling không?
10. Cạnh tranh hai distinct keys có ngăn oversell không?
11. Retry cùng commandId có không double effect không?
12. Same key, different payload có conflict không?
13. Receipt có scope tenant/operation và fingerprint không?
14. Receipt và mutation atomic hoặc recoverable chưa?
15. Receipt TTL có phù hợp delayed retry horizon không?
16. Có xử lý commit outcome unknown sau mất ACK không?
17. Reservation unique key phù hợp business scope không?
18. Có transaction/authority chung cho nhiều records cần nhất quán không?
19. Đã kiểm write skew và phantom predicates khi cần chưa?
20. Chọn isolation thật của engine có đáp ứng invariant không?
21. Có tránh gọi external effects trong transaction callbacks không?
22. Outbox/consumer có idempotency riêng chưa?
23. Có test cancel/release đến trễ và stale owner không?
24. Nếu dùng lease/lock, fencing có được enforce tại nơi ghi không?
25. Multi-region conflict/authority semantics đã rõ chưa?
26. Đã test multi-process, không chỉ multi-thread trong một JVM chưa?
27. Đã test failover/leader change với durability policy chưa?
28. Đã test timeout sau commit chứ không chỉ trước commit chưa?
29. Đã đối chiếu authoritative effects, versions và events chưa?
30. Retry budget/backoff tránh overload/starvation chưa?
31. Query/transaction cost ở hot key đã được đo chưa?
32. Có metrics conflicts/unknown/replays/invariant violations không?
33. Có runbook recovery, reconcile và incident owners không?
34. Đã kiểm tenant authorization trong mọi write filter chưa?
35. Các legacy jobs/admin scripts có bypass guard không?
36. Có kế hoạch test lại sau resharding/schema/SDK changes không?

## 46. Bài tập thực hành

### Bài 1 — Phân tích lost update

Hai requests cùng đọc balance=500, một trừ 100 và một cộng 200. Vẽ interleaving khiến final balance bằng 400 hoặc 700 thay vì 600.

### Bài 2 — Oversell một suất

Inventory còn một suất; hai clients dùng hai commandIds. Viết oracle đúng cho trạng thái, reservations và responses.

### Bài 3 — Conditional expression

Viết pseudocode atomic `available -= q` với điều kiện `available>=q`, `tenantId` và tồn tại item.

### Bài 4 — CAS version

Order v4 có status=NEW. Hai người chuyển sang CONFIRMED và CANCELLED. Thiết kế `expectedVersion` và cách trả conflict.

### Bài 5 — State transition

Một Order đã CANCELLED bị request cũ chuyển PAID. Ngoài version, cần predicate business nào?

### Bài 6 — Không dùng strong read làm lock

Tại sao đọc mạnh rồi ghi vô điều kiện vẫn có race? Thiết kế một test xen writer vào giữa read và write.

### Bài 7 — Hai types of concurrency

Phân biệt hai commandIds khác nhau tranh 1 SKU với 100 attempts cùng một commandId. Chọn primitive cho mỗi trường hợp.

### Bài 8 — Idempotency conflict

Gửi K quantity=1 rồi retry K quantity=2. Server cần lưu fingerprint nào và phải trả gì?

### Bài 9 — Receipt crash gap

Receipt ghi trước, inventory decrement sau; process crash giữa hai bước. Vì sao không được trả success cho retry?

### Bài 10 — Reverse crash gap

Inventory decrement trước, receipt ghi sau; crash giữa hai bước. Vì sao retry có thể double decrement?

### Bài 11 — Multi-record transaction

Thiết kế transaction gồm conditional stock update, unique reservation, receipt và outbox. Nêu backend scope cần đáp ứng.

### Bài 12 — Transaction limit

Nếu transaction engine chỉ hỗ trợ cùng logical partition nhưng records đang ở partitions khác, chọn redesign hay saga và lý giải.

### Bài 13 — Write skew

Hai bác sĩ cùng chuyển off-call từ trạng thái cả hai đang ON. Vẽ schedule dưới snapshot isolation và nêu hậu quả.

### Bài 14 — Guard document

Thiết kế guard CAS cho invariant `onCallCount>=1`; tại sao guard và doctor update phải có atomic/recoverable relationship?

### Bài 15 — Unique seat

Viết key/schema để một `(tenant,flightId,seatId)` có tối đa một active booking; xử lý cancel/rebook.

### Bài 16 — Delayed cancellation

Reserve R1, cancel R1, reserve R2, retry cancel R1. Điều kiện nào bảo vệ R2?

### Bài 17 — MongoDB

Viết `findOneAndUpdate` với tenant, SKU, `available>=quantity` và `$inc`, giải thích `null` result.

### Bài 18 — MongoDB transaction

Thiết kế receipt unique index, transaction stock + reservation + outbox, và test unknown commit.

### Bài 19 — DynamoDB

Viết `UpdateExpression` và `ConditionExpression` cho quantity=2; giải thích khác nhau giữa conditional failure và throttling.

### Bài 20 — DynamoDB TransactWrite

Gộp receipt Put, stock Update và reservation Put trong một transaction; test same-key retry sau timeout.

### Bài 21 — Cosmos DB

Đọc item kèm ETag, tính next available, ghi `If-Match`. Nếu 412, làm gì để không ghi lùi state?

### Bài 22 — Cosmos partition

Receipt và inventory ở hai logical partitions. Vì sao transactional batch không tự giải quyết?

### Bài 23 — Cassandra/ScyllaDB

Đọc `(available,version)`, tính candidate, `UPDATE ... IF version=?`; xử lý LWT failure và contention.

### Bài 24 — Redis

Hoàn thiện Lua script để kiểm receipt theo scoped commandId và decrement trong một slot. Nêu caveat về persistence.

### Bài 25 — Firestore

Ghi transaction callback làm read-check-update stock và receipt; vì sao không gửi email ngay trong callback?

### Bài 26 — Java concurrency

Chạy test hai distinct commandIds giành một suất bằng `CountDownLatch`. Chứng minh chỉ một success.

### Bài 27 — Java idempotency

Cho 100 threads cùng `commandId=K`; assert remaining chỉ giảm một, reservationId giống nhau.

### Bài 28 — Multi-process

Fake `synchronized` pass unit test. Thay bằng hai Spring pods cùng MongoDB; test nào cần thêm để chứng minh distributed correctness?

### Bài 29 — Lost ACK

Tiêm lỗi làm database commit nhưng HTTP response mất. Retry cùng K và kiểm receipt/stock/outbox như thế nào?

### Bài 30 — Transaction restart

Kill service sau commit trước response; test sau restart có replay đúng result mà không mutate thêm không.

### Bài 31 — Multi-region

Hai regions nhận reserve cùng một seat khi bị partition network. Vì sao LWW không thỏa no double booking? Đề xuất single authority.

### Bài 32 — Lock expiry

Worker A giữ lease 10 giây nhưng pause 15 giây, worker B lấy lease mới. Mô tả fencing token bảo vệ stale worker A.

### Bài 33 — Backoff

1.000 writers cạnh tranh cùng SKU. Đề xuất bounded retry/jitter hoặc queue và metrics đánh giá lợi ích.

### Bài 34 — Oracle reconciliation

Ban đầu 10 suất; sau test có 8 successful reservations và `available=3`. Bất biến nào bị sai? Thiết kế cách tìm missing/extra record.

### Bài 35 — Transaction isolation

Đưa ra ví dụ trong đó snapshot isolation đủ ngăn lost update một document nhưng chưa đủ bảo vệ predicate trên hai documents.

### Bài 36 — Batch reservation

Một command đặt đồng thời hai SKUs cần all-or-nothing nhưng engine không có transaction cross-partition. Thiết kế trạng thái `PENDING/CONFIRMED/COMPENSATED` và điều kiện client thấy success.

### Bài 37 — Retry logic

Viết bảng xử lý `VERSION_CONFLICT`, `INSUFFICIENT`, `THROTTLED`, `UNKNOWN_COMMIT` và `KEY_REUSE_CONFLICT`; lỗi nào phải dừng, reload, resolve hoặc retry?

### Bài 38 — Production checklist

Chuẩn bị runbook cho một service booking: invariant, schema, transaction scope, idempotency TTL, failover/durability, event outbox, metrics, fault injection và reconciliation.

### Bài 39 — Thiết kế hoàn chỉnh

Chọn một NoSQL engine, triển khai `reserveOrReplay` thực sự với Java, conditional writes/transaction được hỗ trợ, namespace tenant, receipt và outbox. Tạo integration tests gồm hai concurrent distinct requests, 100 duplicate requests, same-key payload mismatch, timeout sau commit, process restart, release đến trễ và failover test trong sandbox.

---

**Kết luận:** **Bảo vệ cập nhật cạnh tranh bằng điều kiện hoặc giao dịch phù hợp** không phải chỉ thêm `synchronized`, bật strong read hay bật transaction ở bất kỳ đâu. Hãy bắt đầu từ **bất biến nghiệp vụ và nguồn ghi có thẩm quyền**. Với một item, dùng atomic predicate/CAS/version/ETag để kiểm điều kiện ngay tại commit; với nhiều items, cần transaction đúng phạm vi/isolation hoặc một authority và giao thức recovery rõ ràng. **Idempotency** bảo vệ retry của cùng một ý định, còn **concurrency control** bảo vệ các ý định khác nhau tranh cùng tài nguyên; phải có cả hai khi API có timeout và cạnh tranh. Kiểm chứng kết quả bằng **authoritative stock, reservations, receipts, versions và outbox**, bao gồm lost ACK, failover, multi-process và write skew, thay vì chỉ nhìn HTTP status hay số lần chạy handler. Một thiết kế NoSQL đúng là thiết kế giữ invariant **trong mọi lịch biểu concurrent writes mà hệ cam kết hỗ trợ**, kể cả khi network, process hoặc database gặp lỗi.
