# Kiểm thử tính nguyên tử theo đúng khóa/tài liệu/phân vùng/giao dịch

Ứng dụng đặt chỗ lưu số phòng còn lại và số phòng đã giữ. Khi nhận một yêu cầu thành công, ứng dụng phải giảm `available` và tăng `reserved` đúng một lần. Nếu hai trường này cùng nằm trong **một document** và được sửa bởi **một lệnh atomic**, chúng có thể cùng thay đổi trong một phạm vi bảo đảm. Nhưng nếu một trường nằm trong document tồn kho, trường kia nằm trong booking document, một lệnh atomic trên document thứ nhất **không** tự động làm document thứ hai atomic.

Đây là điểm thường gây lỗi khi dùng NoSQL: nhiều hệ hỗ trợ atomic operations nhưng **đơn vị nguyên tử** có thể là một key, một document, một nhóm thao tác có cùng partition key, hoặc một transaction nhiều bản ghi theo API cụ thể. Một batch gửi nhiều writes không mặc nhiên có all-or-nothing. Một thao tác atomic cũng không mặc nhiên có isolation mạnh, durability vượt mọi lỗi, hay tự ngăn client retry tạo hiệu ứng kép.

Bài học thuộc chương **Kiểm thử tính đúng** trong module **Database No SQL**. Chúng ta sẽ chuyển khái niệm tính nguyên tử thành **bài kiểm có giả thuyết, workload cạnh tranh, điểm tiêm lỗi và oracle** đúng phạm vi, kết hợp ví dụ MongoDB, DynamoDB, Cassandra, Redis, Cosmos DB và các dạng NoSQL khác. Bài cũng có chương trình Java 17 tự chứa mô phỏng khác biệt giữa hai writes độc lập và một cập nhật atomic có điều kiện.

> **Nguyên tắc:** Đừng chỉ hỏi “database có atomic không?”. Phải hỏi **“thao tác nào, trên khóa/tài liệu/phân vùng/giao dịch nào, với điều kiện và kiểu đọc nào?”**

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Định nghĩa rõ tập hiệu ứng phải all-or-nothing.
2. Nhận diện ranh giới atomicity ở từng NoSQL API và data model.
3. Phân biệt atomicity, isolation, linearizability, durability, consistency và idempotency.
4. Viết invariant cùng test oracle cho single-key/document update.
5. Kiểm atomic conditional writes khi nhiều clients tranh chấp.
6. Kiểm transaction abort/commit khi có lỗi giữa các writes.
7. Phân loại kết quả SUCCESS, REJECTED, ABORTED, UNKNOWN.
8. Tiêm lỗi khi gửi, trước commit, sau commit nhưng mất ACK, khi failover.
9. Đánh giá đúng các giới hạn của batch, TTL, replica reads, external side effects.
10. Thiết kế test plan, log history, báo cáo bằng chứng và quy trình xử lý lỗi.

## 2. Khái niệm atomicity

Một operation `T` gồm các hiệu ứng:

~~~text
Transfer 100 units from A to B
  Effect 1: A.balance -= 100
  Effect 2: B.balance += 100
~~~

Nếu có **transaction thật sự bao trùm A và B**, trạng thái sau transaction được xác nhận:

- **Commit:** cả Effect 1 và Effect 2 có hiệu lực.
- **Abort:** cả hai không có hiệu lực.
- **Không chấp nhận:** Effect 1 đã được commit nhưng Effect 2 chưa được commit như một kết quả cuối của chính transaction.

\[
CommittedEffects(T)\in\{\varnothing,AllEffects(T)\}
\]

Mô hình này không tự nói mọi read trên mọi replica đều đồng thời nhìn thấy state mới, và không bao gồm payment APIs hoặc email bên ngoài database.

## 3. Ranh giới phải được xác định trước

| Phạm vi | Ví dụ | Điều cần hỏi |
| --- | --- | --- |
| Một key | `INCR counter` | Lệnh có atomic với key không? |
| Một document | Đổi `status` và `version` | Một update hay hai updates? |
| Một item | Conditional decrement inventory | Predicate và write có chung atomic operation? |
| Một partition | Mutations nhiều rows cùng partition | Engine cam kết atomicity/isolation tới đâu? |
| Nhiều documents | Booking + inventory + outbox | Có transaction bao trùm cả ba không? |
| Batch nhiều keys | Bulk puts/deletes | Batch có phải transaction không? |
| Nhiều services | DB booking + external payment | Cơ chế compensation/idempotency là gì? |

**Một NoSQL partition không tự đồng nghĩa transaction partition**. “Partition” ở Cassandra, partition key của DynamoDB, logical partition của Cosmos DB và shard của MongoDB có giới hạn khác nhau.

## 4. Phân biệt với các tính chất khác

| Thuật ngữ | Câu hỏi kiểm thử |
| --- | --- |
| Atomicity | Một operation có commit dở tập hiệu ứng được bảo vệ không? |
| Isolation | Các transaction đồng thời được phép quan sát/ảnh hưởng nhau ra sao? |
| Consistency (ACID) | Invariant nghiệp vụ nào được bảo vệ? |
| Durability | Sau ACK, state tồn tại qua sự cố theo cam kết không? |
| Linearizability | Operation có thể coi xảy ra tại một thời điểm giữa invoke và response không? |
| Serializability | Lịch transaction tương đương lịch tuần tự hợp lệ không? |
| Idempotency | Retry cùng business intent có tạo thêm effect không? |
| Freshness | Một replica/search projection chậm nguồn bao lâu? |

Một hệ có atomic `SET` nhưng code `GET` + `SET` gây lost update vẫn **không chứng minh `SET` non-atomic**. Lỗi có thể nằm ở giao thức cạnh tranh.

## 5. Atomic update khác hai writes tuần tự

### Một document, một atomic update

~~~text
Before:
  available=1, reserved=0, version=7

After:
  available=0, reserved=1, version=8
~~~

Một observer đọc **full document image** theo contract phù hợp không được thấy nửa hiệu ứng do lệnh cập nhật nguyên tử ấy, chẳng hạn `available=0,reserved=0,version=8`.

### Hai document writes

~~~text
update inventory.available = 0
       |
    CRASH
       |
insert booking B101 never runs
~~~

Nếu hai writes không nằm trong một transaction, trạng thái dở dang là **điều có thể xảy ra**. Không nên viết test đòi all-or-nothing rồi quy lỗi cho database.

## 6. Atomicity không tự chống oversell

Lịch sử:

~~~text
Client A reads stock=1
Client B reads stock=1
Client A writes stock=0 (atomic)
Client B writes stock=0 (atomic)
Both report successful booking
~~~

Hai `SET` đều atomic nhưng application đã xác nhận hai bookings. Cần conditional update kiểu “giảm nếu stock còn dương”, version/CAS hoặc transaction tương ứng.

**Hai test khác nhau:**

- Test lệnh ghi có xuất hiện **half-written state** không?
- Test nhiều clients có cùng **thắng một điều kiện cạnh tranh** khi chỉ còn một slot không?

## 7. Invariant đặt chỗ

Một aggregate:

~~~json
{
  "id": "T1/R1/2026-11-20",
  "capacity": 10,
  "available": 7,
  "reserved": 3,
  "version": 12
}
~~~

Invariant:

\[
available+reserved=capacity
\]

\[
0\le available\le capacity,\quad
0\le reserved\le capacity
\]

Reserve một đơn vị:

~~~text
Before: available=7 reserved=3 version=12
After:  available=6 reserved=4 version=13
~~~

Test phải xác định thêm những operations khác có thể tác động state: cancel, expire, restock, admin adjustment. Không viết oracle chỉ biết reserve nhưng lại bật cả cancellation worker.

## 8. Test atomic counter đúng cách

Khởi tạo `counter=0` rồi gửi 100 lần **atomic increment** có đủ chứng cứ success.

\[
ExpectedFinalCounter=100
\]

Điều kiện:

- Thực sự gọi primitive atomic increment, không phải read-modify-write tự tạo.
- Không có writer khác.
- Các operations được xác nhận là committed.
- Readback theo mức consistency phù hợp.
- Không có overflow/expiry.

Nếu 10 requests timeout và không biết server đã commit, không thể suy chỉ có 90 increments. Trạng thái **UNKNOWN** phải được phân giải theo request IDs/evidence.

## 9. Test conditional decrement dưới cạnh tranh

Tồn kho còn một đơn vị, hai clients cùng yêu cầu:

~~~text
Initial: available=1
Client A: conditional reserve
Client B: conditional reserve
~~~

Hợp lệ:

~~~text
A SUCCESS, B CONDITION_FAILED, available=0
~~~

hoặc A/B đổi vai.

Không hợp lệ với business contract:

~~~text
A SUCCESS, B SUCCESS, 2 bookings for one slot
~~~

Khi test, đếm **business intents thành công đã xác minh**, không chỉ HTTP 200: một retry hoặc fallback có thể trả response khác với commit state.

## 10. Test nhiều trường trong cùng một document

Booking chuyển:

~~~json
{"id":"B101","status":"PENDING","confirmedAt":null,"version":6}
~~~

sang:

~~~json
{"id":"B101","status":"CONFIRMED","confirmedAt":"2026-11-14T09:00:00Z","version":7}
~~~

Writer dùng một operation sửa ba trường, reader đọc nhiều lần. Oracle cấm trạng thái “`CONFIRMED` nhưng `confirmedAt=null`” khi giả thuyết nói một update atomic bảo vệ invariant ấy.

Nếu thấy state hỗn hợp, kiểm trước:

1. App có thực sự gửi **một update** không?
2. Reader có ghép fields từ hai API reads?
3. Đang đọc authority hay projection bất đồng bộ?
4. Có writer khác không theo cùng version protocol?
5. Có lỗi type/default mapping trong client?

Chỉ sau khi loại trừ những nguyên nhân đó mới kết luận về server.

## 11. Transaction nhiều bản ghi

Tài khoản A=500, B=200. Một transfer 100 cần cả hai writes.

~~~text
BEGIN TRANSACTION
  A.balance = 400
  B.balance = 300
COMMIT
~~~

Sau commit:

\[
A.balance+B.balance=700
\]

Sau abort:

~~~text
A=500, B=200
~~~

Một operation được kỳ vọng transaction atomic **không được để A=400,B=200 làm trạng thái committed cuối**, nếu không có writer hợp lệ khác. Test cần xác minh transaction đã abort/commit rõ ràng và dùng read/snapshot semantics tương thích.

## 12. Khả năng quan sát không đồng nghĩa commit-state

Một reader trên replica lag có thể thấy **toàn bộ state cũ**. Điều đó là freshness/read-consistency issue, không nhất thiết là partial write.

Mặt khác, nếu reader lấy A từ replica 1 lúc 10:00:01 và B từ replica 2 lúc 10:00:03, tổng hai reads không phải một snapshot thống nhất. Không dùng phép cộng chúng làm bằng chứng vi phạm atomic commit nếu API đọc không cam kết snapshot isolation.

**Hai lớp test nên tách:**

- Sau khi dữ liệu settle: có partial committed effects trong phạm vi transaction không?
- Trong lúc transaction diễn ra: reader có được guarantee nào về visibility/isolation?

## 13. Atomicity khác isolation và linearizability

Một transaction có thể commit all-or-nothing nhưng một read khác vẫn thấy trạng thái cũ do consistency mode.

**Linearizability** yêu cầu có thể xếp các operations như diễn ra tại các điểm tức thời phù hợp thứ tự real-time. Một bộ history-checker sẽ xét invocation/completion và sequential spec. Đó là phép thử mạnh hơn khác mục đích.

Nếu DB công bố eventual reads, một history không linearizable khi đọc replica **không đủ chứng minh single-document write atomicity sai**.

## 14. Hợp đồng test cần ghi gì?

~~~yaml
testId: "ATOMIC-BOOKING-01"
engine: "specific product/version"
deployment: "specific cluster/tier/topology"
operation: "conditional-reserve"
scope:
  atomicBoundary: "one document"
  fullKey: "tenant=T1,room=R1,date=2026-11-20"
initial:
  available: 1
  reserved: 0
  version: 7
writers: 2
readPolicy: "authoritative read compatible with contract"
expected:
  acceptedReservationsMax: 1
  availableNeverNegative: true
  noPartialDocumentImages: true
faultModes: ["concurrency", "lost-response"]
~~~

Đây chỉ là cấu trúc mô tả, không phải file cấu hình một test runner có sẵn. **Phiên bản, topology và API operation** cần được ghi rõ vì có tác động tới guarantee.

## 15. Bảng phạm vi trên các họ NoSQL

| API/engine | Phạm vi phù hợp | Không được suy rộng |
| --- | --- | --- |
| MongoDB `updateOne` | Một document | Hai documents tự atomic |
| MongoDB transactions | Những operations trong transaction hợp lệ | HTTP/payment ngoài DB cùng commit |
| DynamoDB `UpdateItem` có condition | Một item | `BatchWriteItem` all-or-nothing |
| DynamoDB `TransactWriteItems` | Tập transaction actions theo giới hạn API | Không có quotas/constraints |
| Cassandra CQL mutation/LWT | Theo operation, partition và CQL semantics | Batch đa partition có isolation SQL |
| Cassandra logged batch | Eventual batch recovery semantics | Instantaneous cross-partition visibility |
| Redis `INCR`/single command | Command execution trên instance | Hai lệnh riêng tạo một transaction |
| Redis `MULTI/EXEC` | Thứ tự thực thi không interleave | Rollback mọi runtime errors |
| Redis Lua | Script không interleave với clients khác | Error tự undo writes trước đó |
| Cosmos DB transactional batch | Cùng logical partition key | Cross-partition atomicity tổng quát |
| Firestore transaction/batch | Trong phạm vi API documented | External service tự rollback |
| Search bulk | Kết quả theo từng item | Cả bulk là một transaction |

Đây là định hướng thiết kế test, không thay **tài liệu chính thức của phiên bản/tier**. Một hệ có thể có constraints cho transaction size, keys và deployment.

## 16. MongoDB: một document được cập nhật nguyên tử

Ví dụ:

~~~javascript
db.inventory.updateOne(
  { _id: "T1/R1/2026-11-20", available: { $gt: 0 } },
  { $inc: { available: -1, reserved: 1, version: 1 } }
)
~~~

Điều kiện `available>0` và các `$inc` trong cùng update operation bảo vệ state của **một document**.

### Test

1. Khởi tạo stock=1.
2. Cho hai writers đồng thời gọi operation với cùng `_id`.
3. Kiểm tối đa một update match predicate và tạo booking hợp lệ.
4. Đọc lại full document theo contract phù hợp.
5. Kiểm không có state nửa cập nhật.
6. Tiêm lỗi mất response và xác minh unknown outcome bằng stable business ID.

**Không coi hai lệnh `updateOne` riêng trên hai collections là cùng transaction.**

## 17. MongoDB Java: conditional document update

Ví dụ MongoDB synchronous Java driver, giả định collection, dependency và quyền đã được cấu hình:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gt;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.inc;

final class MongoAtomicReserve {
    static boolean reserveOne(
            MongoCollection<Document> inventory,
            String key) {
        UpdateResult result = inventory.updateOne(
            and(eq("_id", key), gt("available", 0)),
            combine(
                inc("available", -1),
                inc("reserved", 1),
                inc("version", 1))
        );
        return result.getModifiedCount() == 1;
    }
}
~~~

### Giới hạn

- Phạm vi là một document, không phải transaction xuyên booking/outbox.
- Timeout có thể xảy ra sau khi commit; không gộp mọi exception thành condition-failed.
- Không có idempotency key: retry y hệt sau commit có thể trừ thêm một đơn vị nếu vẫn còn stock.
- Cần xem read/write concerns, replica reads và retryable-write semantics theo deployment.
- Nếu writer khác bỏ qua condition/version protocol, business invariant vẫn có thể bị phá.

## 18. MongoDB multi-document transaction

Một booking workflow:

~~~text
Transaction T101:
  update inventory
  insert booking B101
  insert outbox E101
~~~

Nếu cả ba effects cần all-or-nothing, sử dụng transaction API thực sự trên deployment hỗ trợ.

### Fault test

- Lỗi sau update inventory nhưng trước insert booking.
- Lỗi sau insert booking nhưng trước insert outbox.
- Condition/unique-key failure khiến transaction abort.
- Transaction write conflict dưới cạnh tranh.
- Mất ACK sau commit.

Sau **abort đã xác nhận**, không được có committed partial set. Sau commit đã xác nhận, cả ba effects phải tồn tại theo contract và quan sát phù hợp.

MongoDB driver có cơ chế retry/transient transaction errors và unknown commit results; không đặt một payment call không idempotent bên trong callback có khả năng được chạy lại.

## 19. DynamoDB: một item và condition

Một item có khóa `(pk,sk)`:

~~~text
pk=ROOM#R1
sk=DATE#2026-11-20
available=1
reserved=0
version=7
~~~

`UpdateItem` với condition `available>0`, cập nhật `available`, `reserved` và `version`, là một thao tác nguyên tử trên **item**.

### Test oracle

- Hai writers tranh stock=1: tối đa một conditional success.
- `ConditionalCheckFailed` nghĩa là predicate không được thỏa theo API, không tính là booking success.
- Timeout không chứng minh thất bại; recheck theo business intent.
- Read eventually consistent có thể thấy item cũ; không nhầm với trạng thái nửa áp.

**`BatchWriteItem` có thể trả `UnprocessedItems` và không là transaction all-or-nothing của cả batch.**

## 20. DynamoDB: transaction nhiều items

`TransactWriteItems` có thể gom actions như Put, Update, Delete, ConditionCheck trong transaction hợp lệ theo limits của dịch vụ.

~~~text
Transaction:
  Update inventory if available > 0
  Put booking if bookingId absent
  Put outbox event if eventId absent
~~~

Lưu ý một transaction request **không được tự đặt nhiều actions lên cùng một item** nếu API hạn chế; predicate tồn kho nên nằm ngay condition của Update trên item đó, thay vì thêm ConditionCheck độc lập cho cùng item.

### Test

1. Một condition fail: không có partial transaction effects.
2. Concurrent transactions conflict: check aborted effects.
3. Transaction vượt limits: không tự tách thành nhiều batch mà vẫn đòi atomicity.
4. Client timeout: outcome có thể unknown.
5. Token idempotency của API có phạm vi/thời hạn riêng; nghiệp vụ còn cần durable business idempotency.

## 21. DynamoDB Java SDK v2: cập nhật có điều kiện

~~~java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.UpdateItemRequest;
import software.amazon.awssdk.services.dynamodb.model
        .ConditionalCheckFailedException;

final class DynamoAtomicReserve {
    static boolean reserve(
            DynamoDbClient db, String table,
            String pk, String sk) {
        UpdateItemRequest request =
            UpdateItemRequest.builder()
                .tableName(table)
                .key(Map.of(
                    "pk", AttributeValue.builder().s(pk).build(),
                    "sk", AttributeValue.builder().s(sk).build()))
                .conditionExpression("available > :zero")
                .updateExpression(
                    "SET available = available - :one, "
                    + "reserved = reserved + :one, "
                    + "version = version + :one")
                .expressionAttributeValues(Map.of(
                    ":zero", AttributeValue.builder().n("0").build(),
                    ":one", AttributeValue.builder().n("1").build()))
                .build();
        try {
            db.updateItem(request);
            return true;
        } catch (ConditionalCheckFailedException rejected) {
            return false;
        }
    }
}
~~~

Mẫu giả định các numeric fields đã tồn tại, item có đúng key schema và IAM cho phép UpdateItem. Không bắt mọi exception thành “false”: throttling, timeout và network errors có semantics khác. Ví dụ chưa có idempotency, chỉ minh họa atomic predicate+mutation **trên một item**.

## 22. Cassandra: thao tác, partition và LWT

Cassandra không nên được giải thích bằng một câu chung “một partition là một SQL transaction”. Cần phân biệt:

- CQL mutations theo operation/partition.
- Conditional updates qua **lightweight transactions (LWT)** trong phạm vi hỗ trợ.
- Logged batch với batch log hỗ trợ eventual atomicity/recovery của mutations, **không mặc nhiên isolation tức thời xuyên partitions**.
- Unlogged batch không nên xem là transaction cross-partition.
- Replication consistency và timestamp/tombstone semantics.

### Ví dụ LWT

~~~sql
UPDATE inventory
SET available = 0, reserved = 1, version = 8
WHERE room_id = 'R1'
  AND stay_date = '2026-11-20'
IF version = 7;
~~~

Khi hai writers tranh cùng version, test kiểm không có hai transitions khác nhau cùng thành công theo `[applied]` trong phạm vi LWT phù hợp. Không coi timeout là `[applied]=false`.

## 23. Cassandra logged batch: eventual atomicity khác isolation

~~~sql
BEGIN BATCH
  INSERT INTO booking_events (tenant_id, event_id, payload)
  VALUES ('T1', 'E101', 'created');
  INSERT INTO audit_events (tenant_id, event_id, payload)
  VALUES ('T1', 'E101', 'recorded');
APPLY BATCH;
~~~

Đây là ví dụ cú pháp; schema/partition placement thực tế phải xác minh.

Một logged batch qua nhiều partitions có thể dùng cơ chế batchlog để bảo đảm các mutations cuối cùng được áp theo contract, nhưng một reader có thể thấy mutations ở các thời điểm khác nhau. **Đừng dùng yêu cầu snapshot isolation của RDBMS để kết luận batchlog atomicity sai**.

### Cần kiểm riêng

1. Điều gì xảy ra khi coordinator hỏng trước/sau ghi batch log?
2. Sau recovery, batch mutations có được hoàn thiện theo semantics không?
3. Readers có isolation guarantee nào cho batch cùng partition/cross partition?
4. Consistency level/repair có ảnh hưởng kết quả quan sát?
5. Có TTL/tombstones tạo phiên bản chồng chéo?

## 24. Redis: một command atomic không bằng nhiều commands atomic

`INCR counter` là một command atomic trên Redis instance thực thi. Nhưng:

~~~text
Client A: GET counter → 0
Client B: GET counter → 0
Client A: SET counter 1
Client B: SET counter 1
~~~

Kết quả 1 là lost update của read-modify-write được tách thành hai commands, không phải `SET` bị ghi một nửa.

Muốn nhiều thao tác được áp không interleave, có thể dùng `MULTI/EXEC` hoặc Lua script với semantics/limits riêng; không mặc định nó cho rollback SQL.

## 25. Redis MULTI/EXEC và WATCH

~~~text
MULTI
DECR inventory
INCR reserved
EXEC
~~~

Commands trong EXEC được chạy tuần tự không interleave với commands khác trên instance, nhưng **runtime error của một command không rollback những commands đã thực thi trước đó**. Cần test kết quả từng command.

`WATCH` có thể dùng optimistic check: nếu watched key thay đổi trước EXEC, transaction có thể bị abort theo contract.

### Bẫy

- Không dùng “EXEC trả response” làm bằng chứng mọi command thành công.
- Không đòi rollback tổng quát khi runtime error nếu Redis không cam kết.
- Không đánh đồng EXEC với distributed commit qua nhiều nodes.
- Phân biệt command atomicity và durability khi replica failover.

## 26. Redis Lua scripts

Ví dụ Lua:

~~~lua
local stock = tonumber(redis.call("GET", KEYS[1]) or "0")
if stock <= 0 then
    return 0
end
redis.call("DECR", KEYS[1])
redis.call("INCR", KEYS[2])
return 1
~~~

Script được thực thi không interleave với commands khác, nhưng **script có thể gặp error sau khi đã thực hiện một số writes**; Redis không tự undo mọi write trước error.

Test:

1. Hai clients cùng tranh chỗ cuối.
2. Trường hợp một key có wrong type.
3. Script lỗi sau mutation đầu tiên.
4. Cluster keys có cùng hash slot theo yêu cầu multi-key.
5. Replica failover và durability **kiểm riêng**.

Nếu cần all-or-nothing khi dữ liệu có thể sai type, validate preconditions trước mutation hoặc chọn model/transaction hỗ trợ semantics cần thiết.

## 27. Cosmos DB: logical partition là boundary của transactional batch

Với Azure Cosmos DB for NoSQL, transactional batch hỗ trợ tập operations atomic **cùng logical partition key** theo API documented.

~~~text
Partition key: tenant=T1, booking=B101
  update booking
  update allocation
  create outbox event
~~~

Nếu một item ở logical partition key khác, không được giả định cùng batch vẫn là transaction. Test cần kiểm:

- Chính xác partition key value, không chỉ physical partition placement.
- ETag/conditional constraints.
- Batch size/actions limits.
- Aborted transaction không có committed partial effects.
- Read consistency/region semantics.

**Logical partition boundary là một ràng buộc data modeling**, không phải chi tiết dễ bỏ qua.

## 28. Firestore và những database transaction khác

Firestore có transaction và batched-write APIs với atomic guarantees riêng. Cần kiểm:

- Documents nào nằm trong transaction/batch.
- Các preconditions được đánh giá thế nào.
- Retry khi conflict và callback có bị chạy lại không.
- Transaction limitations và read semantics.
- External payment/email vẫn nằm ngoài transaction.

Không copy cùng test expectation từ MongoDB sang Firestore mà không kiểm product contract.

## 29. Search bulk indexing không phải một multi-document transaction

Bulk API của search có thể trả:

~~~text
Item A: successful
Item B: failed
Item C: successful
~~~

Phải kiểm **per-item results** thay vì coi cả request là all-or-nothing. Search visibility còn chịu ảnh hưởng của refresh/indexing lag. Nếu search là projection, đối chiếu lại từ authority/source+CDC, không biến search bulk thành transaction cho booking.

## 30. Thiết kế test harness gồm bốn phần

~~~text
Initial data + model
        |
        v
Concurrent workload generator
        |
        v
Fault injector
        |
        v
Operation history + authoritative readback
        |
        v
Oracle / checker
        |
        v
Verdict: PASS / FAIL / INDETERMINATE
~~~

### Không thể thiếu

- Initial state có version rõ.
- Seed/dataset tái hiện được.
- Full business key, idempotency ID.
- Invocation/completion times và error category.
- Cơ chế đọc cuối tương thích với contract.
- Kiểm các transitions và invariants, không chỉ error rates.

## 31. Kết quả phải chia ít nhất bốn nhóm

| Kết quả | Ý nghĩa |
| --- | --- |
| SUCCESS | API phản hồi thành công theo contract |
| REJECTED | Condition/constraint bị từ chối rõ ràng |
| ABORTED | Có bằng chứng transaction không commit |
| UNKNOWN | Không xác định server đã commit hay chưa |

Các lỗi timeout/network có thể thuộc UNKNOWN. **Không tự chuyển UNKNOWN thành ABORTED**. Đặc biệt khi response mất sau commit, client có thể nghĩ thất bại dù state đã đổi.

## 32. Test history cần có invoke và completion

~~~json
{
  "runId": "atomic-lab-543",
  "operationId": "op-101",
  "clientId": "writer-A",
  "businessIntent": "reserve-R101",
  "fullKey": "T1/R1/2026-11-20",
  "startedMonoNs": 1000000,
  "completedMonoNs": 2400000,
  "result": "SUCCESS",
  "reportedVersion": 8,
  "faultPhase": null
}
~~~

Một timeout:

~~~json
{
  "operationId": "op-102",
  "businessIntent": "reserve-R102",
  "result": "UNKNOWN",
  "errorCategory": "RESPONSE_TIMEOUT"
}
~~~

Không log credentials, raw payment info hoặc token trong history.

## 33. Fault injection theo giai đoạn

~~~text
Client                Database
  |
  | (A) before-send
  |-------------------->
  | (B) in-flight
  |     execute
  | (C) before-commit
  |     COMMIT
  | (D) after-commit
  |<------ ACK
      (E) response may be lost
~~~

| Giai đoạn | Giả thuyết | Kỳ vọng |
| --- | --- | --- |
| A | Request chưa rời client | Không có effect do request đó |
| B | Network drop trong lúc gửi | UNKNOWN có thể xảy ra |
| C | Transaction abort trước commit | Không có committed partial set |
| D | Commit rồi lỗi kết nối | Không được tự retry tạo intent mới |
| E | ACK mất | Query/reconcile outcome theo idempotency key |

Một network proxy không nhất thiết chặn chính xác instruction trong server. Ghi rõ fault injection boundary thực tế; không tuyên bố “crash đúng trước commit” khi chỉ mô phỏng socket reset.

## 34. Concurrency test phải tạo tranh chấp cùng key

Test 100.000 requests trên 100.000 keys thường khó phát hiện race của conditional update.

Thay vào đó:

~~~text
1 key, 100 concurrent writers
10 keys, 1000 writers with Zipfian skew
~~~

Dùng barrier/latch để tăng khả năng operations overlap. Chạy nhiều rounds, ghi random seed, timing, transaction outcomes và state cuối. Muốn tái hiện interleaving hiếm có thể cần failpoint/test hooks riêng trong môi trường an toàn.

**Load test QPS không thay correctness test có oracle**.

## 35. Oracle cho một document

~~~text
Allowed:
  BEFORE: available=1, reserved=0, version=7
  AFTER:  available=0, reserved=1, version=8

Forbidden mixed:
  available=0, reserved=0, version=8
  available=1, reserved=1, version=8
~~~

Nếu có cancel/restock/expire workers, oracle phải bao gồm mọi transition hợp lệ. Nếu không, test có thể báo false positive vì nó không biết operation khác đã thay state.

Đọc từng field từ hai calls độc lập rồi ghép thành một “document image” cũng tạo false positive.

## 36. Oracle cho transaction nhiều documents

Một transfer A=500,B=200:

~~~text
Committed: A=400, B=300
Aborted:   A=500, B=200
~~~

Nếu có nhiều transfers đồng thời, checker phải xem **tập các operations và lịch sử** thay vì so với duy nhất hai states cố định.

Đối với concurrent snapshot reads, phải dùng read mode có snapshot guarantee nếu oracle đòi quan sát nhất quán xuyên documents. Nếu chỉ dùng independent eventual reads, một trạng thái quan sát A mới/B cũ chưa tự chứng minh transaction commit một nửa.

## 37. Unknown commit outcome

~~~text
Client sends transaction T101
Database COMMIT succeeds
Network loses response
Client receives timeout
~~~

Đúng cách:

1. Giữ stable business intent ID.
2. Query transaction/business outcome tại authority theo contract.
3. Retry có giới hạn nếu idempotent.
4. Không tự tạo booking/payment ID mới.
5. Theo dõi unresolved unknown outcomes để reconcile.

Một timeout sau commit không phải atomicity violation. Một **retry tạo hai bookings** là lỗi idempotency/business orchestration, dù mỗi transaction đều atomic.

## 38. Idempotency khác atomicity

Một lệnh atomic decrement được gửi hai lần có thể trừ hai đơn vị hoàn toàn hợp lệ.

\[
Atomic(Decrement)\not\Rightarrow Idempotent(Decrement)
\]

Để retry cùng intent an toàn:

- Stable idempotency key.
- Dedupe record/tracking cùng atomic boundary nếu có thể.
- Conditional uniqueness/version.
- Durable decision record hoặc query-by-intent.
- Phân biệt retry một request và yêu cầu business mới.

Window token của một API chưa chắc đủ dài cho toàn business lifecycle; đừng dựa hoàn toàn vào một token có expiry ngắn.

## 39. Failover và durability phải được kiểm riêng

Tình huống:

~~~text
Write ACKed by coordinator
Leader fails
Client reads through another replica
~~~

Nếu read trả phiên bản cũ, có thể là replication/freshness. Nếu dữ liệu đã ACK bị mất vĩnh viễn, xét durability guarantee. Nếu một update được áp dở fields trong **document image có cùng version**, mới cần điều tra atomicity.

Một test muốn đánh giá cả ba phải có:

- Write concern/durability settings.
- Read concern/consistency settings.
- Replica roles, election timing.
- Crash/recovery evidence.
- Assertions được tách theo guarantee.

## 40. TTL, tombstones và các writer nền

Hold có thể tự hết hạn:

~~~text
Client: CONFIRM hold
TTL worker: EXPIRE hold
~~~

Mỗi operation riêng có thể atomic nhưng cả hai cùng “thành công” sai policy nếu state machine thiếu conditional transition.

Tương tự:

- Cassandra tombstone/timestamp ảnh hưởng row visibility.
- Redis TTL xóa keys theo expiry.
- DynamoDB TTL deletion là hoạt động riêng theo contract.
- CDC/search áp events trễ.

Test oracle phải mô hình **operations nền có thể xảy ra**, không gán mọi thay đổi bất ngờ cho write đang kiểm.

## 41. Java 17: mô phỏng broken two-write và atomic aggregate

Bài lab này không kết nối DB. Nó minh họa một chuỗi hai writes có thể bị crash giữa chừng, còn một `compareAndSet` trên **một immutable aggregate** làm state transition nguyên tử trong một JVM. Tạo `AtomicityBoundaryLab.java`:

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicReference;

public final class AtomicityBoundaryLab {
    record State(int available, int reserved,
                 Set<String> processed) {}

    enum Result {
        APPLIED, ALREADY_APPLIED, OUT_OF_STOCK
    }

    static final class BrokenTwoWrites {
        int available = 10;
        int reserved = 0;

        void reserveThenCrash() {
            available--; // first independent write
            throw new IllegalStateException(
                    "crash before second write");
        }

        boolean invariant() {
            return available + reserved == 10;
        }
    }

    static final class AtomicAggregate {
        private final AtomicReference<State> ref =
            new AtomicReference<>(new State(10, 0, Set.of()));

        Result reserve(String id) {
            for (;;) {
                State old = ref.get();
                if (old.processed().contains(id)) {
                    return Result.ALREADY_APPLIED;
                }
                if (old.available() == 0) {
                    return Result.OUT_OF_STOCK;
                }

                Set<String> ids =
                        new HashSet<>(old.processed());
                ids.add(id);

                State next = new State(
                    old.available() - 1,
                    old.reserved() + 1,
                    Set.copyOf(ids));

                if (ref.compareAndSet(old, next)) {
                    return Result.APPLIED;
                }
                // Retry after another writer changed state.
            }
        }

        State read() {
            return ref.get();
        }
    }

    public static void main(String[] args)
            throws Exception {
        BrokenTwoWrites broken = new BrokenTwoWrites();
        try {
            broken.reserveThenCrash();
        } catch (IllegalStateException ignored) {
            System.out.println(
                "Broken invariant=" + broken.invariant());
        }

        AtomicAggregate store = new AtomicAggregate();
        ExecutorService workers =
                Executors.newFixedThreadPool(12);
        CountDownLatch go = new CountDownLatch(1);
        List<Future<Result>> results = new ArrayList<>();

        try {
            for (int i = 0; i < 30; i++) {
                String requestId = "req-" + (i % 20);
                results.add(workers.submit(() -> {
                    go.await();
                    return store.reserve(requestId);
                }));
            }
            go.countDown();

            int applied = 0;
            for (Future<Result> future : results) {
                if (future.get() == Result.APPLIED) {
                    applied++;
                }
            }

            State finalState = store.read();
            boolean valid =
                finalState.available() >= 0
                && finalState.available()
                    + finalState.reserved() == 10
                && finalState.reserved() == applied
                && finalState.processed().size() == applied;

            System.out.println("Applied=" + applied);
            System.out.println(
                "Available=" + finalState.available());
            System.out.println(
                "Reserved=" + finalState.reserved());
            System.out.println("Invariant=" + valid);
        } finally {
            workers.shutdownNow();
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac AtomicityBoundaryLab.java
java AtomicityBoundaryLab
~~~

Kết quả mong đợi của ví dụ:

~~~text
Broken invariant=false
Applied=10
Available=0
Reserved=10
Invariant=true
~~~

### Vì sao phù hợp với bài học?

- `BrokenTwoWrites` ghi một state rồi crash trước state thứ hai, tạo partial state.
- `AtomicAggregate` dùng CAS chuyển toàn bộ fields và processed request IDs trong một immutable value.
- Dưới concurrent writers, nếu CAS thất bại worker **đọc lại điều kiện** thay vì ghi dựa trên state cũ.
- Stable request ID chống hai effects của cùng intent khi state đã ghi nhận nó.

**Giới hạn:** CAS này chỉ nguyên tử trong **một JVM** và không bền qua process crash. Nó không là bằng chứng về MongoDB, Cassandra, DynamoDB, Redis hay multi-service transaction. Với database thật cần primitive atomic/transaction trên đúng data boundary, read/write concerns, failure injection và history checker riêng.

## 42. Tại sao test trong một JVM chưa đủ?

Một process có thể giữ mọi state trong `AtomicReference` và pass stress tests, nhưng production có:

~~~text
Pod A → DB node 1
Pod B → DB node 2
Pod C → DB node 3
~~~

Ứng dụng phải dựa vào **database-side condition/transaction**, không dựa vào `synchronized` hoặc local lock ở một pod. Khi pod crash, memory state bị mất; khi replicas lag, readers có observation khác. Vì vậy lab là mô hình tư duy, không thay end-to-end test.

## 43. Test lỗi trước commit

Trong môi trường test hỗ trợ failpoint:

~~~text
BEGIN TRANSACTION
  write inventory
  FAILPOINT("after-inventory")
  write booking
COMMIT
~~~

Nếu failpoint làm transaction abort theo contract, sau khi xác minh trạng thái authority:

~~~text
inventory unchanged
booking absent
~~~

Nếu ứng dụng không mở transaction thật, inventory có thể đã đổi. **Test này phân biệt rõ lỗi boundary trong application code**, không nhất thiết là bug của engine.

## 44. Test lỗi sau commit trước ACK

~~~text
Client                   Database
  |    Submit T101         |
  |----------------------->|
  |                        | COMMIT
  |<----- response lost --- |
  | Timeout (UNKNOWN)      |
~~~

Yêu cầu:

- Không coi timeout là abort.
- Không tự tạo transaction ID/business ID khác.
- Truy vấn status qua stable idempotency key hoặc authority version.
- Retry theo contract có bounded budget.
- Kiểm không có double side effects.
- Ghi unresolved operations vào reconciliation.

Đây là một trong những fault cases quan trọng nhất của hệ phân tán.

## 45. Runtime lỗi trong một batch

Đừng kiểm tất cả batch APIs với cùng oracle:

| Batch/API | Phản ứng cần kiểm |
| --- | --- |
| Transaction thật | Abort/commit all-or-nothing trong phạm vi |
| BatchWriteItem | Per-item successes và unprocessed items |
| Cassandra logged batch | Eventual recovery semantics, không snapshot isolation xuyên partitions |
| Cassandra unlogged cross-partition batch | Partial application có thể xảy ra |
| Redis MULTI/EXEC | Commands nối tiếp, runtime errors không rollback phần trước |
| Redis Lua | Không interleave, nhưng script error sau writes không tự undo |
| Search bulk | Per-item result |

**Tên “batch” biểu diễn đóng gói thao tác, không đủ chứng minh transaction**.

## 46. Test outbox cùng booking transaction

~~~text
Transaction T:
  update inventory
  insert booking
  insert outbox event E101
COMMIT
~~~

Kỳ vọng nếu cả ba thực sự nằm trong cùng transaction boundary:

- Abort T: không committed inventory/booking/outbox effects của T.
- Commit T: cả ba effects được ghi trong DB theo contract.
- Consumer có thể publish/deliver event trễ hoặc nhiều lần.

Một email hoặc payment được gọi sau đó **không cùng transaction**. Consumer phải idempotent, events có stable IDs và ledger phải đối soát.

## 47. Nếu không có multi-record transactions

Ba hướng thiết kế:

1. **Gộp fields liên quan chặt vào một aggregate item/document**, dùng atomic conditional update. Cần xét hot key và item size limit.
2. **State machine + compensation:** mỗi bước atomic trong scope nhỏ, có trạng thái `PENDING/RESERVED/CONFIRMED/COMPENSATED` và reconciliation.
3. **Chọn một authority có transaction phù hợp** cho invariant sống còn, dùng CDC để xây search/cache/analytics projections.

Không dùng local Java `synchronized` để giả làm transaction xuyên pods/regions; nó không bao phủ nhiều processes và không tồn tại sau crash.

## 48. Version guard và optimistic concurrency

Một CAS:

~~~text
Read version 7
Try update WHERE version=7
If matched:
  write new state, version=8
Else:
  conflict; re-read and re-evaluate
~~~

Nếu application không re-evaluate business predicate sau conflict mà retry mù quáng, có thể oversell.

Để CAS bảo vệ được invariant:

- Mọi relevant writers phải tuân thủ version protocol.
- Version có semantics monotonic theo aggregate.
- Predicate và mutation cùng atomic operation.
- Condition fail không được chuyển thành unconditional upsert.
- Unknown outcome và retry được xử lý riêng.

## 49. History-based checking

Một checker có thể thử xếp operations thành một lịch hợp lệ theo sequential specification, giữ các quan hệ happens-before do invocation/completion xác định. Các công cụ kiểu Jepsen/Knossos hoặc model-based test hỗ trợ tiếp cận này, nhưng phải cấu hình **đúng consistency model và operation semantics**.

### Tránh báo lỗi sai

- Eventual read thấy version cũ không chứng minh partial write.
- Client timeout không chứng minh operation abort.
- Lịch không linearizable không tự chứng minh atomicity của một write sai.
- Một batch cross-partition không có isolation contract không thể bị đánh giá theo global snapshot isolation.

**Kết quả INDETERMINATE là hợp lệ** nếu không có đủ evidence để kết luận.

## 50. Metrics và bằng chứng cần lưu

| Metric/trường | Mục đích |
| --- | --- |
| `test_run_id`, random seed | Tái hiện |
| Operation ID, client ID | Phân biệt requests |
| Business intent ID | Kiểm retry/dedupe |
| Full key, partition key | Xác định atomic boundary |
| Invoke/completion timestamps | Phân tích lịch |
| Result category | SUCCESS/REJECTED/ABORTED/UNKNOWN |
| Before/after version | Kiểm transition |
| Transaction/session ID | Liên kết writes |
| Fault phase | Xác định nơi lỗi |
| Read/consistency policy | Tránh stale-read false positive |
| Replica/leader/CDC watermark | Ngữ cảnh failover |
| Invariant violation count | Chất lượng nghiệp vụ |
| Unresolved unknown outcomes | Công việc đối soát |

Metrics labels phải low-cardinality, không đưa từng user ID/secret vào telemetry. Raw operation histories cần storage có access control/retention phù hợp.

## 51. Runbook khi nghi ngờ partial commit

1. Chỉ ra **API operation và documented atomic boundary**.
2. Dừng fault test hoặc cô lập workload nếu có tác động.
3. Bảo vệ request histories, trace IDs và initial/final states.
4. Xác định dữ liệu từ authority hay replica/projection.
5. Kiểm application có thực sự dùng single atomic operation/transaction không.
6. Kiểm writers khác, TTL, retries và concurrency.
7. Phân loại unknown outcomes trước khi đếm failures.
8. Chọn read mode đủ kiểm proof, có checkpoint/watermark nếu cần.
9. Thu nhỏ reproducer, ghi engine version/config/consistency.
10. Nếu cần sửa dữ liệu, dùng conditional repair có approval, không blind overwrite.
11. Nếu vẫn nghi DB vi phạm hợp đồng, gửi evidence cho nhà cung cấp.
12. Thêm regression test trước khi đưa thay đổi trở lại production.

Một state không hợp lệ xuất hiện không đồng nghĩa lỗi database nếu application đã gửi hai independent writes trong hai atomic scopes khác nhau.

## 52. Ma trận fault injection đề xuất

| ID | Scenario | Boundary | Expected test conclusion |
| --- | --- | --- | --- |
| F1 | 100 concurrent atomic increments | Single key | No lost confirmed increments |
| F2 | Two conditional reserves stock=1 | Single item | At most one accepted |
| F3 | Reader giữa một document update | One document | No partial document image |
| F4 | Crash giữa hai independent writes | Two docs | Partial state possible |
| F5 | Abort trước commit | Transaction | No committed partial effect |
| F6 | Condition fails inside transaction | Transaction | All-or-nothing abort |
| F7 | Lose ACK after commit | Operation/txn | Unknown resolution, no double intent |
| F8 | Retry same booking request nhiều lần | Business intent | One business effect |
| F9 | Concurrent overlapping transactions | Transaction | Conflict/abort handled |
| F10 | Coordinator crash giữa logged batch | Cassandra | Check eventual batch semantics |
| F11 | Unlogged cross-partition batch fails | Cassandra | Do not expect global atomicity |
| F12 | Lua runtime error after write | Redis | Do not assume rollback |
| F13 | EXEC includes failing command | Redis | Inspect per-command effects |
| F14 | BatchWrite returns unprocessed | DynamoDB | Per-item follow-up |
| F15 | Cross-partition transactional batch attempted | Cosmos DB | Scope rejected/not assumed |
| F16 | Bulk one item fails | Search | Partial per-item results |
| F17 | Stale replica read after commit | Read consistency | Not a partial-write proof |
| F18 | TTL expiry competes with confirm | State machine | No double release/confirm |
| F19 | Leader failover after ACK | Durability/read | Separate from atomicity |
| F20 | Outbox publish retried | Cross-service | No duplicate business side effect |

Không tiêm destructive faults trực tiếp trên production nếu không có quyền, guardrails và runbook an toàn.

## 53. Bài tập thực hành

### Bài 1 — Boundary

Hai lệnh `updateOne` MongoDB trên hai documents có là một transaction không? Khi nào cần multi-document transaction?

### Bài 2 — Lost update

Hai clients cùng `GET x=0` rồi `SET x=1`. Vì sao kết quả 1 không tự chứng minh SET thiếu atomicity?

### Bài 3 — Invariant

Inventory có capacity 5, available 3, reserved 2. Viết transition khi reserve 1 và điều kiện không cho overbook.

### Bài 4 — Concurrency

Tồn kho còn 1, 30 clients cùng conditional decrement. Expected successful intents tối đa bao nhiêu?

**Gợi ý:** 1 nếu không có restock và tất cả kết quả được xác minh.

### Bài 5 — Stale read

Primary v9, replica v8. Khi cả hai document images đều hợp lệ, đó có nhất thiết là atomicity violation không?

### Bài 6 — Transfer

Ví A=500, B=200. Giao dịch chuyển 100 bị abort. State nào hợp lệ? Nếu A=400,B=200 thì có vấn đề gì?

### Bài 7 — Unknown outcome

Commit thành công nhưng ACK bị mất. Vì sao retry bằng booking ID mới là nguy hiểm?

### Bài 8 — Atomicity vs idempotency

Một atomic decrement bị gọi hai lần. Vì sao có thể giảm hai đơn vị dù cả hai calls đều atomic?

### Bài 9 — MongoDB

Viết một `updateOne` có `available>0` và `$inc` đồng thời `available`, `reserved`, `version`.

### Bài 10 — MongoDB transaction

Transaction cập nhật inventory, booking và outbox. Tiêm fault sau inventory write; sau abort phải kiểm gì?

### Bài 11 — Callback retries

Vì sao không gửi email/capture payment bên trong transaction callback có thể retry?

### Bài 12 — DynamoDB

Viết ConditionExpression cho stock dương. `ConditionalCheckFailed` có nghĩa hệ thống bị lỗi không?

### Bài 13 — DynamoDB batch

Một `BatchWriteItem` có unprocessed items. Vì sao không gọi toàn batch là atomic?

### Bài 14 — DynamoDB transaction

Một condition trong `TransactWriteItems` fail. Những writes còn lại được phép commit riêng lẻ không?

### Bài 15 — Cassandra LWT

Hai writers cùng `IF version=7`. Nếu cả hai nhận `[applied]=true` cho hai competing transitions, phải điều tra gì?

### Bài 16 — Cassandra logged batch

Reader nhìn thấy một partition update trước partition còn lại. Vì sao phải phân biệt eventual batch recovery và isolation?

### Bài 17 — Cassandra unlogged

Một batch không log qua nhiều partitions có lỗi. Vì sao không được suy cả batch all-or-nothing?

### Bài 18 — Redis INCR

So concurrent `INCR` với `GET` rồi `SET`. Phép nào chống lost update theo key?

### Bài 19 — Redis MULTI/EXEC

Một command gặp runtime error trong EXEC. Redis có rollback mọi command trước đó không?

### Bài 20 — Redis Lua

Một script viết key A rồi error ở key B. Atomic execution giúp điều gì, không giúp điều gì?

### Bài 21 — Cosmos DB

Ba items trong một logical partition key được đưa vào transactional batch. Item thứ tư khác key có thuộc transaction không?

### Bài 22 — Search bulk

Item A và C success, B failed. Cách kiểm kết quả bulk đúng là gì?

### Bài 23 — Payment

DB transaction commit booking rồi payment API lỗi. Vì sao ACID của DB không tự rollback payment?

### Bài 24 — Snapshot

Reader lấy A và B từ hai replicas khác nhau. Có đủ evidence kết luận transaction bị partial commit không?

### Bài 25 — Timeout

Request timeout, database có thể đã commit. Thiết kế cách xác minh theo intent ID và read policy.

### Bài 26 — Java lab

Chạy `AtomicityBoundaryLab.java`. Giải thích vì sao broken invariant false nhưng CAS aggregate vẫn giữ tổng capacity 10.

### Bài 27 — Mở rộng lab

Thêm `cancel` và `expire` có điều kiện. Oracle phải biết những transition hợp lệ nào?

### Bài 28 — Stress

So 100 clients tranh cùng 1 key với 100 clients trên 100 keys. Test nào kích hoạt contention mạnh hơn?

### Bài 29 — Fault phases

Phân biệt lỗi trước send, trong request, trước commit, sau commit và lost ACK. Outcome classes có giống nhau không?

### Bài 30 — History logs

Thiết kế JSON log chứa invoke/complete, request ID, version và fault phase. Vì sao chỉ log exception text không đủ?

### Bài 31 — Linearizability

Giải thích vì sao non-linearizable history với eventual reads không tự chứng minh writes bị half-applied.

### Bài 32 — TTL

Hold hết hạn cùng lúc client confirm. Thiết kế state transition tránh cùng expire và confirm.

### Bài 33 — Outbox

Nếu booking commit mà outbox vắng, cần xác nhận transaction scope và các quan sát nào?

### Bài 34 — Repair

Một test phát hiện partial state do hai independent writes. Vì sao repair bằng unconditional upsert có thể ghi đè state mới đúng?

### Bài 35 — Tổng hợp

Thiết kế kiểm thử correctness cho Booking API dùng MongoDB authority, DynamoDB inventory, Redis cache, Cassandra event history và search projection:

1. Xác định phạm vi atomicity ở từng API.
2. Chọn invariant về booking và inventory.
3. Viết test tranh tồn kho cuối và idempotent retry.
4. Kiểm multi-record transaction có thật hay chỉ batch.
5. Tiêm fault sau một write và trước commit.
6. Tiêm lost ACK sau commit.
7. Tách stale reads, durability và atomicity.
8. Kiểm outbox/CDC side effects không nhân đôi.
9. Chọn oracle, history format và stop conditions.
10. Đặt pass/fail theo **guarantee thực sự được document**.

**Gợi ý:** bắt đầu từ business invariant, vẽ atomic boundary thực, sau đó gắn fault phases và expected states vào đúng boundary.

## 54. Checklist kiểm thử đúng phạm vi

1. Đã ghi product, version, deployment, consistency mode chưa?
2. Đã xác định operation API cụ thể và atomic boundary chưa?
3. Có phân biệt key, document, logical partition, batch và transaction không?
4. Full business key và tenant scope đã đúng chưa?
5. Initial state, invariant và expected effects đã rõ chưa?
6. Có test concurrent writers tranh cùng key không?
7. Có conditional/version guard thay read-then-write không?
8. Có test fail trước commit và lost ACK sau commit không?
9. Có phân loại SUCCESS/REJECTED/ABORTED/UNKNOWN không?
10. Retry có stable intent ID/idempotency không?
11. Reader có quan sát một document image nhất quán không?
12. Read policy có phù hợp consistency guarantee không?
13. Có tránh gán stale replica read thành atomicity violation không?
14. Có kiểm transaction abort không để lại committed partial effects không?
15. Có hiểu giới hạn multi-document transaction về API/size không?
16. Có hiểu Cassandra LWT/logged/unlogged batches không?
17. Có hiểu Redis EXEC/Lua không rollback mọi runtime errors không?
18. Có hiểu DynamoDB BatchWrite không phải transaction không?
19. Có hiểu Cosmos logical partition batch scope không?
20. Có kiểm search bulk per-item results không?
21. Có kiểm TTL, cancel, expire và background writers trong model không?
22. Có kiểm external payment/email là ranh giới khác DB transaction không?
23. Có lưu history với invocation/completion, request IDs và versions không?
24. Có repeat/fault injection với seed và môi trường an toàn không?
25. Có tách verdict INDETERMINATE khỏi PASS/FAIL không?
26. Có runbook điều tra và conditional repair nếu state sai không?
27. Có bảo vệ dữ liệu/credential trong logs và test fixtures không?
28. Có regression tests khi thay schema, index, SDK hoặc transaction model không?

## 55. Tổng kết

1. **Atomicity luôn có phạm vi.** Một key/document update không tự bảo đảm nhiều documents hoặc services.
2. **All-or-nothing của operation khác isolation và linearizability.** Một replica stale có thể trả full state cũ mà không chứng minh partial write.
3. **Lost updates và oversell thường là lỗi giao thức cạnh tranh**, dù từng lệnh đọc/ghi riêng có tính nguyên tử.
4. **Batch không mặc nhiên transaction.** MongoDB, DynamoDB, Cassandra, Redis, Cosmos và search bulk có các semantics khác nhau.
5. **Conditional writes/CAS cần chạy trong cùng atomic operation**, đồng thời mọi writers phải tôn trọng protocol.
6. **Unknown commit outcome phải được xử lý đúng**, vì timeout có thể tới sau commit.
7. **Atomicity không tự tạo idempotency**: retry một decrement có thể thực hiện decrement thêm một lần.
8. **Fault injection và concurrent histories là phần quan trọng của test**, chứ không chỉ đếm requests thành công.
9. **Business invariant và scope của readback quyết định oracle**; không dùng read mode yếu để đòi guarantee mạnh.
10. **Transaction không bao phủ external side effects**. Payment, email và broker cần outbox/saga/idempotency.
11. **Bài lab Java minh họa một boundary trong JVM**, không thay kiểm thử trên database thật với failover/durability.
12. **Một báo cáo correctness có giá trị phải có contract, lịch sử, bằng chứng và khả năng tái hiện**.

**Nguyên tắc thực hành:** mỗi khi viết bài kiểm NoSQL, hãy trả lời **“những hiệu ứng nào phải cùng thành công?”, “chúng có thật nằm trong cùng khóa/tài liệu/phân vùng/giao dịch được cam kết?”, “lỗi xảy ra ở pha nào?”, “kết quả nào là success, abort hay unknown?”, và “đọc theo cách nào mới đủ bằng chứng?”**. Khi năm câu hỏi được trả lời chính xác, bạn mới thực sự **kiểm thử tính nguyên tử theo đúng phạm vi**.
