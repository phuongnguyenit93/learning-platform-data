# Gửi yêu cầu trùng, đảo thứ tự và sự kiện đến muộn

## 1. Vì sao kiểm thử thành công khi xử lý một lần vẫn chưa đủ?

Một ứng dụng Java ghi trạng thái đơn hàng vào NoSQL và phát sự kiện đến consumer cập nhật read model. Trong môi trường lý tưởng:

~~~text
OrderCreated(v1) -> OrderPaid(v2) -> OrderShipped(v3)
~~~

Nhưng thực tế có thể như sau:

~~~text
09:00:01  API gửi CreateOrder(op-101).
09:00:02  Database commit, nhưng ACK bị mất.
09:00:03  Client timeout rồi retry CreateOrder(op-101).
09:00:04  Event OrderPaid(v2) đến trước OrderCreated(v1).
09:00:05  OrderCreated(v1) được giao lại hai lần.
09:15:00  OrderCancelled(v3) đến sau OrderReopened(v5).
~~~

Nếu hệ chỉ chạy đúng trên happy path, nó có thể tạo hai đơn hàng, thu tiền hai lần, ghi đè trạng thái mới bằng trạng thái cũ, phát email sai hoặc hồi sinh bản ghi đã xóa.

**Kiểm thử lỗi và tải** cần chủ động tạo những tình huống này, không chờ chúng xảy ra ngẫu nhiên trên production.

Bài này thuộc module **Database No SQL**, chương **Kiểm thử lỗi và tải**, tập trung vào ba nhóm nhiễu:

1. **Yêu cầu hoặc sự kiện trùng** (*duplicate request/delivery*).
2. **Yêu cầu hoặc sự kiện đảo thứ tự** (*reordering/out-of-order processing*).
3. **Sự kiện đến muộn** (*late arrival*), nhất là sau window, TTL, xóa, chuyển trạng thái hoặc failover.

Ví dụ dùng Java và MongoDB, DynamoDB, Cassandra/ScyllaDB, Redis, Elasticsearch/OpenSearch; khả năng cụ thể phụ thuộc engine, phiên bản và deployment.

### Mục tiêu học tập

Sau bài, bạn có thể:

- Phân biệt request trùng, retry sau timeout, delivery trùng, replay và event mới hợp lệ.
- Giải thích vì sao at-least-once delivery đòi consumer idempotent và phạm vi của các bảo đảm exactly-once.
- Thiết kế idempotency key, scope, payload binding, retention và atomic persistence.
- Dùng unique constraints, conditional writes, optimistic versions và inbox/outbox để chống hiệu ứng trùng.
- Phân biệt arrival order, source order, entity version, event time và processing time.
- Xử lý stale/late event mà không làm giảm phiên bản hoặc hồi sinh dữ liệu bị xóa.
- Viết JUnit/integration/property tests, fake clock, failure injection và load experiments.
- Đo duplicate suppression, stale rejection, pending gaps, lateness, dedup TTL và queue lag.
- Phân biệt eventual consistency hợp lệ với invariant violation thực sự.

## 2. Những định nghĩa phải tách rõ

| Thuật ngữ | Ý nghĩa | Có nhất thiết là lỗi? |
|---|---|---|
| Duplicate request | Một logical operation được gửi lại | Không, client retry có thể hợp lệ |
| Duplicate delivery | Một eventId đến consumer nhiều lần | Không, broker có thể redeliver |
| Distinct event cùng entity | Hai events mới cho một entity | Không, có thể là hai thay đổi hợp lệ |
| Out-of-order arrival | Event mới hơn đến trước event cũ | Cần chính sách |
| Late event | Event đến sau thời điểm/window dự kiến | Tùy hợp đồng lateness |
| Stale update | Mutation version cũ hơn state đã áp dụng | Cần reject/merge |
| Retry after unknown outcome | Client không biết commit hay chưa | Không suy là chưa commit |
| Replay | Xử lý lại lịch sử có chủ đích | Hợp lệ nếu consumer an toàn |
| Redelivery | Broker giao lại do chưa ACK | Bình thường ở nhiều hệ |

### 2.1. Duplicate request không bằng duplicate business operation

Hai POST có payload giống nhau có thể là hai đơn hàng người dùng cố ý tạo. Hai POST cùng **idempotency key** và cùng scope thường đại diện một logical operation. Không dùng raw JSON equality làm cơ sở duy nhất.

### 2.2. MessageId khác operationId

EventId giúp dedup message delivery; operationId nhận diện business command. Một command có thể phát nhiều events và envelope mới có thể có message ID khác. Chọn stable identifier theo tầng nghiệp vụ.

### 2.3. Late không luôn đồng nghĩa stale

Event xảy ra hôm qua nhưng hôm nay mới đến vẫn có thể hợp lệ để tính lại báo cáo theo event time. State update v3 đến sau v8 lại là stale. Đây là hai quyết định khác nhau.

### 2.4. Same version không luôn là same payload

Hai events entityVersion=8 nhưng payload khác nhau có thể là corruption hoặc producer bug. Không silently bỏ bản thứ hai chỉ vì version trùng.

## 3. Vì sao hệ phân tán sinh duplicate và đảo thứ tự?

~~~mermaid
sequenceDiagram
    participant C as Java Client
    participant DB as NoSQL
    participant B as Broker
    participant W as Consumer
    C->>DB: Write(operationId=op-101)
    DB-->>DB: Commit
    DB--xC: ACK lost / timeout
    C->>DB: Retry(operationId=op-101)
    DB-->>C: Existing result / deduplicated
    DB->>B: Event e1
    B->>W: Deliver e1
    W--xB: ACK lost
    B->>W: Redeliver e1
~~~

Nguồn nhiễu phổ biến:

- Network timeout, connection reset, mất response sau commit.
- Consumer crash sau xử lý nhưng trước ACK.
- Retry/backoff của client, job scheduler hoặc queue framework.
- Partition rebalance, failover và leader election.
- Nhiều partitions/threads xử lý song song với độ trễ khác nhau.
- CDC snapshot + streaming overlap, replay checkpoint hoặc restore.
- Backfill muộn ghi đè update mới.
- Truyền đa Region, clock skew, offline/mobile clients.

**Đặt thứ tự event arrival làm thứ tự sự thật là giả định nguy hiểm** nếu kiến trúc không có guarantee tương ứng.

## 4. Đảm bảo delivery không thay nghĩa idempotency

### 4.1. At-most-once

Hệ có thể không xử lý lại khi ACK lỗi, ít duplicate hơn nhưng có nguy cơ mất event. Không hợp khi mất OrderPaid không được chấp nhận.

### 4.2. At-least-once

Hệ retry cho tới khi có ACK/điều kiện dừng; cùng event có thể được giao nhiều lần. Consumer phải idempotent để không nhân đôi business effects.

### 4.3. Exactly-once trong một phạm vi

Broker/stream processor có thể cung cấp transactional/exactly-once trong boundary được hỗ trợ. Không có nghĩa tự bảo đảm exactly-once cho email, payment, Redis, MongoDB hoặc nhiều databases bên ngoài.

### 4.4. End-to-end correctness

Hệ có thể giao event hai lần mà vẫn tạo **một kết quả nghiệp vụ** khi dùng stable key, transaction/conditional guard, outbox/inbox và downstream idempotency.

### 4.5. Exactly-once effect

Một logical command tạo tác dụng nghiệp vụ tối đa một lần theo operationId trong scope và thời hạn được xác định, dù request/ACK/delivery lặp bao nhiêu lần. Đây là invariant có thể kiểm thử.

## 5. Ba loại thứ tự

~~~text
Source commit:
  v1 OrderCreated
  v2 OrderPaid
  v3 OrderShipped

Broker arrival:
  v2 OrderPaid
  v1 OrderCreated
  v3 OrderShipped

Consumer completion:
  v2 finishes at t4
  v3 finishes at t5
  v1 finishes at t6
~~~

### 5.1. Source order

Thứ tự mutations được source-of-truth chấp nhận, thường theo entity/aggregate hoặc partition chứ không nhất thiết toàn hệ.

### 5.2. Delivery order

Thứ tự consumer thấy events có thể khác source khi đi qua nhiều partitions, network hops hoặc retry.

### 5.3. Completion order

Ngay cả khi nhận v1, v2, v3 theo thứ tự, xử lý async nhiều threads có thể hoàn tất v2, v3, v1. Broker ordering chưa đủ nếu consumer tự song song thiếu key-level serialization.

### 5.4. Scope của version

orderVersion của O101 không tự so được với orderVersion của O102. Một total order toàn hệ đắt và có thể không cần.

### 5.5. Đừng dùng timestamp client làm global sequence

Clock skew khiến sự kiện đến sau mang timestamp nhỏ hơn. Dùng monotonic source version/sequence hoặc causal model phù hợp với nguồn thực sự.

## 6. Viết invariants trước khi tạo lịch giao nhiễu

Ví dụ Order aggregate:

1. Cùng tenantId+operationId và cùng payload, CreateOrder tạo tối đa một order.
2. OperationId đã dùng với payload khác phải trả conflict, không tái sử dụng kết quả cũ im lặng.
3. Payment capture được thực hiện tối đa một lần theo payment intent ID, dù event delivery lặp.
4. Applied sourceVersion của projection không được giảm bởi event cũ.
5. Replay event không làm gửi trùng một email nghiệp vụ theo eventId+purpose.
6. Sau tombstone/delete v8, upsert v6 đến muộn không hồi sinh record.
7. Nếu delta v3 cần v2 trước đó, consumer buffer/rebuild chứ không giả áp delta lên state thiếu.
8. Late event trong allowed lateness đi vào window được định nghĩa; quá hạn có xử lý explicit.
9. Khi các dependencies phục hồi, kết quả cuối hội tụ theo oracle bất kể permutation arrival được phép.
10. Thử overload không gây retry storm, backlog và business effects tăng không giới hạn.

### 6.1. Safety và liveness khác nhau

Safety: “không bao giờ double charge” hoặc “không bao giờ version regression”. Liveness: “consumer cuối cùng xử lý đến checkpoint v9” khi dependencies khỏe. Test eventual system không nên đòi projection bắt kịp ngay lập tức nhưng vẫn phải kiểm safety ở mọi điểm.

### 6.2. State transitions không nhất thiết giao hoán

OrderPaid rồi OrderCancelled có thể có nghĩa khác OrderCancelled rồi OrderPaid. Dedup eventId chỉ xử lý delivery trùng, không tự đảm bảo transition hợp lệ.

### 6.3. Giao hoán khác idempotent

Phép cộng số nguyên có tính giao hoán: cộng 3 rồi cộng 2 bằng cộng 2 rồi cộng 3. Nhưng cộng 3 hai lần vẫn khác cộng một lần. Với duplicated increments phải dedup hoặc dùng một data type/protocol phù hợp.

## 7. Idempotency key: định danh logical operation

~~~text
POST /orders
Idempotency-Key: op-101
Body: {tenantId:"T17", cartId:"C55", ...}
~~~

### 7.1. Scope

Key nên được phân vùng theo tenantId, operationType, operationId hoặc scope tương đương. Hai tenants trùng key không được nhận nhầm result.

### 7.2. Payload binding

Lưu canonical request digest hoặc normalized business parameters theo policy. Retry cùng key nhưng payload khác phải bị từ chối. Chú ý digest thấp entropy có thể bị dò nếu lộ, không coi nó là bảo mật cho PII.

### 7.3. Atomic claim

Kiểm tra key tồn tại rồi tạo order là **check-then-act race**: hai workers có thể cùng thấy chưa tồn tại. Dùng unique/conditional claim, transaction hoặc workflow có claim/fencing để một winner duy nhất.

### 7.4. Persist result

Lần đầu tạo orderId=O101; retry cùng key phải nhận cùng orderId/status hoặc trạng thái PROCESSING/UNKNOWN có thể tra, chứ không tạo O102.

### 7.5. Dedup TTL

Nếu record idempotency chỉ giữ 24 giờ, retry sau 25 giờ có thể được coi là operation mới. Chọn retention theo retry/replay horizon và hậu quả kinh doanh, không tuyên bố exactly once vĩnh viễn bằng TTL ngắn.

### 7.6. Restore có thể làm mất idempotency ledger

Khi khôi phục database về thời điểm trước commit ledger nhưng payment bên ngoài đã capture, retry có nguy cơ double charge. Cần reconcile với authoritative payment provider theo stable operation ID.

## 8. State machine khi retry sau timeout

~~~text
UNSEEN -> CLAIMED -> PROCESSING -> SUCCEEDED
                        |
                        +-----> FAILED_FINAL
                        |
                        +-----> UNKNOWN_NEEDS_RECONCILIATION
~~~

### 8.1. Vì sao UNKNOWN là trạng thái thật?

Database hoặc payment provider có thể commit trước khi ACK mất. “Không nhận response” không chứng minh “chưa thực hiện”.

### 8.2. Không retry side effect mù quáng

Với payment, tra status theo provider idempotency key hoặc đối soát trước khi tạo capture mới. Provider idempotency có giới hạn scope/window riêng, cần hiểu contract.

### 8.3. CLAIMED rồi crash

Cần lease/fencing hoặc sweeper để claim có thể được tiếp quản an toàn, không cho hai owners đồng thời hoàn tất cùng side effect.

### 8.4. Kết quả retry có thể là đang xử lý

Nếu operation IN_PROGRESS, API có thể trả 202 + status endpoint thay vì đợi. Không coi request chưa hoàn tất là thất bại vĩnh viễn.

### 8.5. Fault injection ở đúng điểm

Inject lỗi **sau commit nhưng trước response/ACK**. Chỉ giả lập lỗi trước database call sẽ bỏ sót bài toán khó nhất.

## 9. Consumer inbox và processed-event ledger

Một consumer có thể giữ:

~~~text
consumerName
eventId
entityId
sourceVersion
payloadDigest
status
processedAt
~~~

### 9.1. Ghi processed sau effect không phải lúc nào an toàn

Effect hoàn tất rồi process crash trước ghi inbox: redelivery có thể chạy effect lại. Ghi processed trước effect rồi crash: event bị đánh dấu xử lý nhưng effect chưa xảy ra.

### 9.2. Atomic boundary

Nếu inbox claim + business update + outbox event nằm trong cùng transaction được engine hỗ trợ, ta có atomic boundary. Nếu qua nhiều stores/third-party APIs, cần idempotency riêng, compensation và reconciliation.

### 9.3. Outbox

Commit business mutation và outbox record cùng transaction; publisher có thể gửi nhiều lần nhưng consumer dedup. Outbox chống mất event giữa DB commit và broker publish; không tự bảo đảm exactly-once external effects.

### 9.4. Per-consumer identity

Search consumer và billing consumer có quyền xử lý cùng event, nên inbox key gồm consumerName+eventId. Không dùng một global consumed flag ngăn consumer thứ hai.

### 9.5. Retention

Dedup ledger hết hạn sớm hơn broker replay horizon có thể cho phép effect cũ lặp. Retention, backfill và disaster recovery phải xem xét cùng nhau.

## 10. Các lựa chọn khử trùng lặp

| Cách | Đặc điểm | Giới hạn |
|---|---|---|
| Unique constraint | Một record theo unique business key | Không giúp nếu retry tự sinh ID mới |
| Idempotency ledger | Key → status/result được lưu bền | Cần atomic claim và retention |
| Consumer inbox | Một eventId/consumer được áp một lần | Effect và claim cần transaction hoặc reconciliation |
| Version compare-and-set | Chặn stale overwrite | Không chặn một event mới sai payload cùng version nếu không kiểm |
| Upsert theo stable key | Idempotent với full state deterministic | Side effects khác vẫn có thể lặp |
| External provider idempotency | Chặn duplicate effect theo provider scope | Window và guarantees theo provider |
| Dedup cache TTL | Chi phí thấp trong thời hạn ngắn | TTL/eviction/restore có thể cho duplicate lọt |

### 10.1. Idempotent record không đồng nghĩa workflow

SET order.status=PAID hai lần có thể cho cùng state, nhưng sendPaidEmail() chạy hai lần vẫn là duplicate effect.

### 10.2. Payload không phải định danh operation

User đặt hai đơn giống hệt vẫn là hai operations khác nhau. OperationId phải sinh/được tái sử dụng đúng theo business command.

## 11. Out-of-order update cần version gate

Current projection:

~~~json
{"orderId":"O101","status":"SHIPPED","appliedVersion":3}
~~~

Event đến sau:

~~~json
{"eventId":"e-paid","orderId":"O101","status":"PAID","entityVersion":2}
~~~

### 11.1. Last arrival wins không tương đương latest source version

Nếu consumer ghi PAID lên SHIPPED, dữ liệu regress. Với full-state events, có thể chỉ áp eventVersion lớn hơn appliedVersion; với delta events cần ràng buộc kế tiếp.

### 11.2. Snapshot event và delta event

Full state v3 có thể thay v1/v2 khi đủ thông tin; delta “increaseQty by 2” ở v3 có thể phụ thuộc v2. Không dùng một policy skip gaps cho cả hai.

### 11.3. Active-active không luôn có single integer version

Hai Regions có thể cùng tạo v8 nếu thiếu sequencer. Cần owner/fencing, conflict resolution, vector/causal metadata hoặc CRDT tùy thiết kế.

### 11.4. Thử hai thứ tự

~~~text
Case A: v1, v2, v3
Case B: v3, v1, v2
~~~

Kết quả cuối phải theo contract; với delta cần buffer rồi apply đúng thứ tự thay vì chấp nhận v3 ngay.

## 12. Khi nào dùng version >, khi nào dùng version == current+1?

### 12.1. Full snapshot replacement

Nếu event mang toàn bộ canonical state của entity tại version v, có thể dùng rule “chỉ áp nếu v lớn hơn current” và bỏ các bản cũ. Điều này giả định event tự đủ và version tăng đơn điệu.

### 12.2. Delta/event phụ thuộc

Nếu event mô tả chuyển trạng thái hoặc số tăng dựa trên state trước đó, thường yêu cầu expectedVersion=current và apply version kế tiếp; gặp gap thì buffer, rebuild từ nguồn hoặc re-fetch snapshot.

### 12.3. Cùng version, eventId khác

Nếu có hai updates cùng version, không được tự coi là duplicate. Có thể xảy ra split-brain/producer bug; báo VERSION_CONFLICT và dừng áp cho tới khi xác định authority.

### 12.4. Sequence reset

Khi rebuild/restore hay đổi ownership, version counter có thể reset nếu thiết kế sai. Dùng generation/epoch+sequence hoặc stable source version để tránh coi events cũ là mới sau cutover.

### 12.5. Không dùng MAX(timestamp) thay bằng version

Timestamp từ các client khác nhau có thể lệch và event time không phải commit order. Chọn metadata theo mục tiêu: ordering, audit, windowing hay retention.

## 13. Tombstone: chống hồi sinh dữ liệu đã xóa

Một timeline:

~~~text
v5: product P1 exists
v6: product P1 deleted, tombstone retained
v4: delayed ProductUpdated arrives
~~~

Nếu xử lý delete bằng cách xóa hẳn record/version khỏi B, consumer thấy v4 và tạo lại P1 vì tưởng chưa có. **Tombstone ghi nhớ việc đã xóa cùng sourceVersion** giúp reject stale upsert.

### 13.1. Tombstone là dữ liệu nghiệp vụ của projection

Ví dụ:

~~~json
{"productId":"P1","deleted":true,"appliedVersion":6}
~~~

Nó không nhất thiết là tombstone vật lý mà engine sử dụng nội bộ (ví dụ Cassandra). Phân biệt application-level tombstone và storage-engine tombstone.

### 13.2. Tombstone retention

Nếu tombstone bị TTL trước khi mọi delayed events hết khả năng xuất hiện, stale update có thể hồi sinh record. TTL phải xét message retention, max offline delay, replay/backfill và recovery horizon.

### 13.3. Recreate hợp lệ

Nếu productId được tái sử dụng sau xóa, cần incarnation/generation mới và explicit creation event; không phân biệt bằng version cũ. Nhiều hệ an toàn hơn khi không tái sử dụng ID.

### 13.4. Thử duplicate delete

Delete v6 gửi hai lần phải không xóa entity mới của generation khác; conditional delete/versions giúp giữ an toàn.

## 14. “Đến muộn” có hai nghĩa vận hành quan trọng

**State late:** Một event v6 đến khi projection đã v9, cần reject theo source order.

**Event-time late:** Sự kiện xảy ra lúc 09:00 nhưng consumer nhận lúc 09:20; có thể vẫn phải cập nhật cửa sổ thống kê 09:00–09:05 tùy allowed lateness.

### 14.1. Event time

Thời điểm nghiệp vụ phát sinh, ví dụ lúc đơn thực sự được tạo theo nguồn được chọn. Không nhất thiết là thời điểm broker nhận.

### 14.2. Processing time

Thời điểm worker xử lý event, phụ thuộc network, retry, backlog, downtime.

### 14.3. Ingestion time

Thời điểm event vào pipeline/broker; hữu ích đo transport delay nhưng không thay event time.

### 14.4. Watermark

Một số stream processors dùng watermark để biểu diễn tiến trình event time và khi nào có thể đóng một window theo chính sách. Watermark không chứng minh tuyệt đối không có event muộn hơn trừ khi nguồn/contract thực sự có guarantee.

### 14.5. Allowed lateness

Window 09:00–09:05 có thể tiếp nhận updates bổ sung tới 09:10 theo policy 5 phút, sau đó chuyển sự kiện quá hạn vào late stream, correction hoặc audit; không tự bỏ lặng.

## 15. Ví dụ windowing có sự kiện đến muộn

Một báo cáo tính tổng giá trị đơn trong cửa sổ 10 phút theo **event time**:

~~~text
Event                     eventTime   arrivalTime   amount
Order O1 confirmed         09:01       09:01        100
Order O2 confirmed         09:04       09:05        200
Order O3 confirmed         09:03       09:12        300
~~~

Cửa sổ [09:00,09:10) có tổng cuối cùng 600, nhưng ở 09:10 hệ mới biết 300. Nếu allowed lateness chỉ 1 phút, O3 tới 09:12 có thể vượt chính sách.

### 15.1. Bốn cách xử lý late data

1. **Drop có audit:** chỉ khi business contract cho phép.
2. **Side output/DLQ:** chuyển sang luồng kiểm tra và xử lý có kiểm soát.
3. **Correct/retract aggregate:** cập nhật kết quả đã publish và phát correction event/version.
4. **Recompute window:** tính lại từ authoritative source với checkpoint và publish bản mới.

### 15.2. Retraction phải idempotent

Nếu correction đến trùng, aggregate không được trừ hai lần. Gắn windowKey, revision/eventId và apply theo version hoặc atomic dedup.

### 15.3. Không dùng processing-time window nếu báo cáo theo event time

Event O3 đến 09:12 thuộc window 09:00 theo nghiệp vụ, không tự thuộc 09:10–09:20 chỉ vì consumer chạy lúc đó.

### 15.4. Late threshold theo nguồn

Mobile offline, IoT edge hoặc cross-region replication có distribution delay khác nhau. Đặt allowed lateness theo business obligation và latency evidence, không chỉ cho đơn giản.

### 15.5. Kiểm thử boundary

Tạo event ở 09:09:59.999, 09:10:00.000, watermark ngay trước/sau mốc đóng, và sự kiện đúng ngưỡng lateness để tránh off-by-one.

## 16. Không mặc định broker bảo toàn order toàn hệ

Một số brokers bảo toàn thứ tự **trong một partition hoặc key** với điều kiện nhất định. Không suy ra total order giữa các partitions hay consumer groups.

### 16.1. Partition key theo aggregate

Nếu Order O101 events route cùng partition, khả năng xử lý theo source order tốt hơn. Nhưng rebalance, retries, parallel workers và producer paths vẫn cần test.

### 16.2. Multiple producers

Hai services phát events cùng order mà không có version authority có thể tạo race. Broker offsets ở hai partitions không là một business sequence chung.

### 16.3. Key-level serial executor

Consumer dispatch theo entity key để một entity được xử lý tuần tự; vẫn cần dedup vì redelivery, version gate vì producer/restore.

### 16.4. Retry partition

Đẩy event lỗi sang retry topic có thể làm event kế tiếp vượt trước. Test điều này thay vì giả sử retry giữ nguyên order.

### 16.5. Backfill có thể đi ngoài broker

Backfill chạy trực tiếp có thể ghi v3 sau CDC v9. DB conditional gate là lớp bảo vệ cuối.

## 17. Gap detection và pending buffer

Delta consumer ở appliedVersion=4 nhận v6, chưa có v5:

~~~text
State at v4
Incoming v6
Expected v5
~~~

### 17.1. Không apply delta v6 ngay

Nếu v6 là “trừ số lượng reserved 2”, nó có thể cần thay đổi v5. Đợi v5, fetch authoritative snapshot hoặc replay từ checkpoint.

### 17.2. Pending buffer có giới hạn

Giữ v6 trong bounded store, deadline, max pending per entity và max global bytes. Không để missing event tạo buffer tăng vô hạn.

### 17.3. Nếu v5 không bao giờ tới

Sau gap timeout, chuyển GAPPED/NEEDS_REBUILD, kích hoạt recovery workflow đọc snapshot đủ mới. Không silently bỏ qua rồi báo checkpoint đã xử lý đủ.

### 17.4. Duplicate trong pending

Nếu v6 đến ba lần, pending store chỉ cần một bản cùng eventId+digest. Cùng version nhưng digest khác báo VERSION_CONFLICT.

### 17.5. Xử lý v5 rồi drain

Khi v5 commit, áp v6 pending theo expectedVersion. Việc cập nhật checkpoint và xóa pending phải crash/retry safe.

## 18. Negative tests: cố tình vi phạm các giả định

Không chỉ thử lịch hợp lệ. Hãy gửi:

- Duplicate eventId nhưng payloadDigest khác.
- Same entityVersion nhưng hai eventIds khác.
- Event v3 trước v1 trong consumer chỉ có delta.
- Delete v7 rồi update v6 đến muộn.
- Recreate generation=2 rồi delete generation=1.
- Event time vượt allowed lateness.
- Event tenantId khác với partition key.
- Retry same idempotency key nhưng thay payload hoặc principal.
- Lease hết hạn khi worker cũ vẫn chạy.
- Event signature/schema invalid.

### 18.1. Kết quả mong đợi không luôn là HTTP 400

Consumer có thể quarantine/DLQ hoặc phân loại pending, còn offset/progress được quản trị theo policy. Không được mất dữ liệu chỉ để giữ broker offset tăng.

### 18.2. Poison event không được tạo retry storm

Payload permanently invalid cần DLQ/quarantine và cảnh báo, không retry vô hạn ở tốc độ cao.

### 18.3. Log metadata an toàn

Ghi error category, event reference, schema version và restricted evidence; không xuất auth tokens/PII vào logs.

## 19. Test harness điều khiển lịch giao

Kiểm thử cần ba phần:

1. **Events:** eventId, entityId, sourceVersion, eventTime, payload.
2. **Schedule:** thứ tự delivery, duplicates, delays, crashes.
3. **Oracle:** state, side-effect counts, tombstones, gaps, metrics, checkpoint.

~~~text
Given: events e1(v1), e2(v2), e3(v3)
Schedule: [e2, e1, e2, e3, e1]
Expected after convergence:
  appliedVersion = 3
  no duplicate payment capture
  no version regression
  duplicate deliveries classified
~~~

### 19.1. Đừng phụ thuộc Thread.sleep

Sleep tùy ý làm tests flaky. Dùng deterministic scheduler, fake clock và queue để điều khiển delivery/processing.

### 19.2. Assert cả side effects

Handler có thể gửi email trùng rồi vẫn kết thúc state đúng. Kiểm external call counts, outbox events và charge IDs.

### 19.3. Crash points

Crash sau inbox claim, sau business write, trước outbox insert, sau publish trước ACK, sau external capture; mỗi điểm có outcome khác.

### 19.4. Nhiều keys xen kẽ

Per-key executor vẫn phải xử lý các entities khác nhau song song, không starvation/lẫn versions.

## 20. Java: biểu diễn event và immutable state

~~~java
import java.time.Instant;

public record OrderEvent(
        String eventId,
        String tenantId,
        String orderId,
        long generation,
        long version,
        Instant eventTime,
        String status,
        String payloadDigest
) {}

public record OrderState(
        String tenantId,
        String orderId,
        long generation,
        long appliedVersion,
        String status,
        boolean deleted
) {}
~~~

### 20.1. Generation

Phân biệt lifecycle của một entity khi ID được tái tạo sau delete/restore. v1 generation=2 không phải v1 generation=1.

### 20.2. Version

Sequence tăng theo aggregate trong generation. Nó được authority cấp; consumer không được tự sinh version theo arrival order.

### 20.3. EventId

Nhận diện delivery/replay. Cùng eventId với payloadDigest khác phải báo conflict.

### 20.4. EventTime

Dùng cho windowing/audit, không mặc định là thứ tự commit.

### 20.5. Record không tự deep-copy nested collections

Nếu payload chứa List/Map mutable, dùng defensive copy trước khi so sánh hoặc lưu test event.

## 21. Java: pure reducer chống stale overwrite

Ví dụ xử lý **full-state events** có version đơn điệu và generation ổn định; không dùng nguyên xi cho delta events.

~~~java
public enum ApplyKind {
    APPLIED,
    DUPLICATE_OR_STALE,
    REQUIRES_NEW_GENERATION,
    REJECTED_INVALID
}

public record Reduction(ApplyKind kind, OrderState state) {}

public final class OrderReducer {
    public Reduction reduce(OrderState current, OrderEvent event) {
        if (event.version() <= 0 || event.generation() <= 0) {
            return new Reduction(ApplyKind.REJECTED_INVALID, current);
        }

        if (current == null) {
            if (event.version() != 1) {
                return new Reduction(ApplyKind.REJECTED_INVALID, null);
            }
            return new Reduction(ApplyKind.APPLIED, stateOf(event));
        }

        if (!current.tenantId().equals(event.tenantId())
                || !current.orderId().equals(event.orderId())) {
            return new Reduction(ApplyKind.REJECTED_INVALID, current);
        }

        if (event.generation() < current.generation()) {
            return new Reduction(ApplyKind.DUPLICATE_OR_STALE, current);
        }
        if (event.generation() > current.generation()) {
            return new Reduction(
                    ApplyKind.REQUIRES_NEW_GENERATION, current
            );
        }
        if (event.version() <= current.appliedVersion()) {
            return new Reduction(ApplyKind.DUPLICATE_OR_STALE, current);
        }
        return new Reduction(ApplyKind.APPLIED, stateOf(event));
    }

    private OrderState stateOf(OrderEvent event) {
        boolean deleted = "DELETED".equals(event.status());
        return new OrderState(
                event.tenantId(), event.orderId(),
                event.generation(), event.version(),
                event.status(), deleted
        );
    }
}
~~~

### 21.1. Giới hạn của ví dụ

Code minh họa version gate, không validate toàn bộ business state machine. Nếu transition phải theo CREATED→PAID→SHIPPED, cần rules riêng.

### 21.2. Gap

Reducer cho phép v4 thay v2 nếu event chứa full state hợp lệ. Delta v4 yêu cầu v3; không áp reducer full-state vào phép cộng/trừ delta.

### 21.3. Equal version không chứng minh duplicate

Reducer không lưu eventId/digest của appliedVersion. Projection/inbox ở production cần dữ liệu đó để phát hiện eventId khác với cùng version.

### 21.4. Race hai workers

Hai workers cùng đọc v2 có thể ghi v3 và v4 sai thứ tự dù reducer riêng lẻ đúng. Persist bằng atomic conditional update/transaction có predicate currentVersion.

## 22. Java JUnit: cùng event lặp phải không đổi state cuối

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class OrderReducerTest {
    private final OrderReducer reducer = new OrderReducer();

    private OrderEvent event(String id, long v, String status) {
        return new OrderEvent(
                id, "T17", "O101", 1L, v,
                Instant.parse("2026-11-14T08:00:00Z"),
                status, "digest-" + id
        );
    }

    @Test
    void repeatedFullStateEventDoesNotRegress() {
        OrderEvent created = event("e1", 1L, "CREATED");
        OrderEvent paid = event("e2", 2L, "PAID");

        OrderState s1 = reducer.reduce(null, created).state();
        OrderState s2 = reducer.reduce(s1, paid).state();
        Reduction duplicate = reducer.reduce(s2, paid);
        Reduction older = reducer.reduce(s2, created);

        assertEquals(ApplyKind.DUPLICATE_OR_STALE, duplicate.kind());
        assertEquals(ApplyKind.DUPLICATE_OR_STALE, older.kind());
        assertEquals(2L, duplicate.state().appliedVersion());
        assertEquals("PAID", older.state().status());
    }
}
~~~

### 22.1. Test trên pure function chỉ là lớp đầu

Reducer test không chứng minh atomic persistence, broker ACK, external effects và durability của dedup ledger. Cần integration tests và fault injection.

### 22.2. Thêm trường hợp same-version-conflicting-payload

Pure reducer ở trên gộp vào DUPLICATE_OR_STALE. Một consumer hoàn chỉnh cần xem metadata để báo VERSION_CONFLICT nếu eventId/payload khác dù version bằng nhau.

### 22.3. Không dùng wall clock trong assertion

Event time cố định trong fixture giúp test tái lập. Clock-dependent logic cần fake clock.

## 23. Java JUnit: đảo thứ tự full-state events

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class ReorderTest {
    @Test
    void applyingV3ThenV2MustNotRevert() {
        OrderReducer r = new OrderReducer();
        Instant t = Instant.parse("2026-11-14T08:00:00Z");
        OrderEvent v1 = new OrderEvent(
                "e1", "T17", "O101", 1, 1, t, "CREATED", "d1"
        );
        OrderEvent v3 = new OrderEvent(
                "e3", "T17", "O101", 1, 3, t, "SHIPPED", "d3"
        );
        OrderEvent v2 = new OrderEvent(
                "e2", "T17", "O101", 1, 2, t, "PAID", "d2"
        );

        OrderState s = r.reduce(null, v1).state();
        s = r.reduce(s, v3).state();
        Reduction stale = r.reduce(s, v2);

        assertEquals("SHIPPED", stale.state().status());
        assertEquals(3L, stale.state().appliedVersion());
        assertEquals(ApplyKind.DUPLICATE_OR_STALE, stale.kind());
    }
}
~~~

### 23.1. Không chứng minh đúng transition từ mọi lịch giao

Ví dụ hợp lệ **chỉ nếu v3 là full-state event** và domain cho phép projection bỏ qua v2. Nếu mỗi event là transition/delta, v3 không được áp trước v2.

### 23.2. Dùng parameterized permutations

Sinh mọi permutation của e1/e2/e3 và duplicates có giới hạn. Với full-state snapshot events và initialization policy phù hợp, final state phải đúng; với delta, kiểm tra buffer+drain behavior.

### 23.3. Đo violation ở mọi intermediate step

Assert appliedVersion không giảm giữa các lần, không chỉ final state. Một regression thoáng qua có thể làm API đọc sai dù cuối test lại đúng.

## 24. Java: fake clock cho late-event tests

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;

public final class FixedTestClock extends Clock {
    private final Instant time;
    private final ZoneId zone;

    public FixedTestClock(Instant time, ZoneId zone) {
        this.time = time;
        this.zone = zone;
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId newZone) {
        return new FixedTestClock(time, newZone);
    }

    @Override
    public Instant instant() {
        return time;
    }
}
~~~

### 24.1. Có thể dùng Clock.fixed

JDK đã có Clock.fixed(instant, zone) cho test. Class ở trên chỉ để thấy dependency injection; không cần triển khai lại trong mọi dự án.

### 24.2. Clock không thay event time

Fake processing clock giúp test receipt deadline, nhưng event-time timestamp lấy từ event. Watermark cần được truyền/điều khiển riêng.

### 24.3. Test đúng ngưỡng

Nếu cutoff là 10:10:00, thử arrival 10:09:59.999, 10:10:00.000 và 10:10:00.001 theo inclusive/exclusive policy.

### 24.4. Không dùng sleep hàng phút để “đợi late”

Đẩy virtual clock hoặc watermark test harness thay vì khiến bộ test chậm/flaky.

## 25. Java: trình điều khiển giả lập lịch delivery

Một harness khái niệm:

~~~java
import java.util.List;

public final class ScheduledDelivery {
    public static OrderState replayFullStates(
            List<OrderEvent> schedule, OrderReducer reducer
    ) {
        OrderState state = null;
        for (OrderEvent event : schedule) {
            Reduction result = reducer.reduce(state, event);
            state = result.state();
        }
        return state;
    }
}
~~~

### 25.1. Không đồng nhất in-memory replay với distributed commit

Harness trên deterministic và hữu ích cho reducer, nhưng không kiểm race trên database, connection reset, ACK loss, transaction atomicity hay inbox survival.

### 25.2. Event v3 tới trước event khởi tạo

Với reducer minh họa, v3 khi state null bị REJECTED_INVALID chứ không buffer. Một production consumer cần chính sách pending/re-fetch; harness phải kiểm tra decision đúng thay vì kỳ vọng mọi permutation tự hội tụ.

### 25.3. Chèn duplicates có kiểm soát

Schedule [e1,e2,e2,e3,e1] kiểm idempotency; [e1,e3,e2] kiểm reorder; [e2,e1,e3] kiểm gap và policy.

## 26. MongoDB: unique index chống create trùng

Ví dụ idempotency collection:

~~~javascript
db.idempotency.createIndex(
  {tenantId: 1, operationType: 1, operationId: 1},
  {unique: true}
)
~~~

Một command CreateOrder phải gắn key với result, không tạo random order mới sau retry.

### 26.1. Atomic duplicate-key rejection

Hai request cùng key đồng thời cố insert claim; unique index khiến chỉ một insert thành công. Request còn lại nhận duplicate-key và đọc claim/result phù hợp. Cần phân biệt duplicate-key với lỗi DB khác.

### 26.2. Nếu claim và order ở hai collections

Nếu insert claim thành công nhưng insert order thất bại, hệ có claim dang dở. Khi yêu cầu atomicity, dùng MongoDB transaction hỗ trợ theo deployment hoặc workflow claim state/recovery; không xem unique index tự bao phủ cả hai writes.

### 26.3. FindOneAndUpdate và expected version

Một projection có thể update khi appliedVersion nhỏ hơn incoming version, hoặc dùng compare-and-set với phiên bản hiện tại. Conditional predicate phải nằm trong **một atomic write**, không phải đọc ở app rồi write vô điều kiện.

### 26.4. MongoDB retryable writes

Driver có cơ chế retryable writes trong phạm vi được hỗ trợ, nhưng không thay business idempotency của multi-step workflow hoặc external payment/email. Test timeout sau commit ở application boundary.

### 26.5. Change streams

Change streams/resume tokens giúp CDC consumer tiếp tục, nhưng consumer có thể gặp replay/snapshot overlap và cần dedup theo stable entity/event metadata. Đừng suy resume token tương ứng một business operation ID.

### 26.6. Test TTL ledger

MongoDB TTL indexes dọn theo lịch, không tức thời đúng millisecond. Test semantics theo thời hạn dedup contract, không dựa trên việc document vật lý biến mất đúng tại cutoff.

## 27. MongoDB: thử hai concurrent updates trái thứ tự

Current:

~~~json
{"_id":"O101","status":"PAID","appliedVersion":2}
~~~

Hai workers nhận v4 rồi v3.

### 27.1. Lịch kiểm thử

~~~text
W1 reads current v2; holds event v4.
W2 reads current v2; holds event v3.
W1 attempts atomic conditional update v4.
W2 attempts atomic conditional update v3.
Final should be v4 for full-state updates.
~~~

### 27.2. Filter/update cùng statement

Một update với predicate appliedVersion thấp hơn v4 không được làm mất phiên bản đã cao hơn vì race. Hãy quan sát matchedCount/modifiedCount và result state.

### 27.3. Equal-version payload conflict

Nếu event v4' có status khác, cần kiểm tra stored digest/eventId và báo conflict. Không coi matchedCount=0 là đủ chứng minh duplicate.

### 27.4. Hậu quả nếu dùng read-then-save

W1 đọc v2, W2 đọc v2, W1 ghi v4, W2 ghi v3 bằng replaceOne theo _id vô điều kiện: final v3 sai. Thử lịch này để chứng minh CAS cần thiết.

### 27.5. Write concern

Kiểm thử replication/failover còn phải xem acknowledged durability theo write concern được chọn. Một update được ACK theo mức yếu có thể bị rollback theo engine semantics; đừng khẳng định nó đã bền toàn cụm chỉ vì một thread success.

## 28. DynamoDB: conditional PutItem tạo idempotency claim

Một item:

~~~text
PK=TENANT#T17#OP#op-101
requestDigest=...
status=PROCESSING
resultOrderId=O101
ttlEpochSeconds=...
~~~

Ví dụ biểu thức điều kiện:

~~~text
ConditionExpression: attribute_not_exists(PK)
~~~

### 28.1. Một winner

Hai PutItem cùng PK và condition trên item chưa tồn tại: chỉ một request có thể tạo item, request còn lại nhận ConditionalCheckFailedException khi condition không còn đúng.

### 28.2. Failure không phải luôn retryable

ConditionalCheckFailed có thể là kết quả bình thường của duplicate/stale request; không nên retry vô hạn mà cần đọc existing claim và xác minh payload/owner.

### 28.3. TTL là cleanup, không phải exact expiry

DynamoDB TTL deletion có thể bất đồng bộ; code phải kiểm logical expiration và policy key reuse, không trông đợi TTL làm item biến mất đúng mốc.

### 28.4. TransactWriteItems

Khi claim và order nằm trong các items có thể giao dịch phù hợp, transaction có thể gắn chúng theo ACID boundary của DynamoDB. Hiểu limits và conflict behavior; client request token của transaction có phạm vi/idempotency window riêng, không thay permanent operation ledger.

### 28.5. Update projection theo version

ConditionExpression trên appliedVersion đảm bảo stale v3 không ghi đè current v4; cùng version/payload khác cần detect conflict bằng metadata. Có thể kết hợp return values/extra read theo protocol.

### 28.6. GSI/eventual reads

Một consumer xác minh idempotency qua GSI eventual có thể không thấy claim vừa ghi. Hãy lựa chọn key lookup/consistency phù hợp; condition trên base item vẫn là cơ chế đảm bảo uniqueness.

## 29. DynamoDB: test crash sau transaction và trước response

~~~text
1. Client TransactWriteItems(op-101) được commit.
2. Network drop response.
3. Client retry cùng business operation ID.
4. App nhận duplicate claim, đọc result.
5. Exactly one order and one payment intent exists.
~~~

### 29.1. Retry của SDK

SDK tự retry một số lỗi transient theo chính sách, nhưng app phải kiểm soát số attempts, timeout và cách phân loại unknown outcome. Đừng đồng nhất HTTP timeout với transaction cancellation.

### 29.2. Conditional conflicts không phải dữ liệu hỏng

Một duplicate có thể làm conditional write thất bại như thiết kế. Alert dựa trên bất thường/burst và phân loại; không báo tất cả conditional failures là hệ thống down.

### 29.3. Transaction token window

Nếu dựa vào token có retention window hữu hạn, kiểm tra retry xảy ra sau window và sau restore; business key cần chính sách độc lập.

### 29.4. Giao thoa với TTL

Test cùng operationId trước TTL, ngay thời điểm logical expiry, và sau cleanup; ghi rõ khi nào key có thể được tái sử dụng.

## 30. Cassandra/ScyllaDB: LWT và conditional state transitions

Trong Cassandra, một câu:

~~~sql
INSERT INTO processed_events (
    consumer_name, event_id, processed_at
) VALUES (?, ?, ?) IF NOT EXISTS;
~~~

có thể sử dụng lightweight transaction (LWT) trong phạm vi hỗ trợ để một event claim không bị tạo trùng. Dùng cẩn trọng vì LWT có latency/cost/availability trade-off.

### 30.1. LWT không tự giao dịch với mọi bảng bên ngoài

Ghi inbox claim bằng LWT và cập nhật một table khác bằng write riêng vẫn có crash gap. Cần kiến trúc xử lý effects/chia boundary và recovery.

### 30.2. Last-write-wins theo timestamp khác business version

Các writes Cassandra có timestamps và conflict resolution riêng. Một event cũ đến sau có thể ghi đè nếu timestamp của lần xử lý muộn hơn, dù business version nhỏ hơn. Không dựa vào physical LWW để đảm bảo source order.

### 30.3. Tombstones

Delete trong Cassandra tạo tombstone theo storage semantics. Tombstone compaction/repair, gc_grace_seconds và replica outage có quan hệ phức tạp với dữ liệu hồi sinh; application-level version/tombstone policy vẫn cần cho business event replay.

### 30.4. Client retries có thể không an toàn cho counter operations

Một counter increment có thể bị thực thi hai lần nếu client timeout rồi retry không có idempotency guard. Thiết kế counters dựa trên unique events hoặc ledger/aggregation nếu cần exactly-once business effect.

### 30.5. Test consistency levels

Thử với CL được triển khai (ví dụ LOCAL_QUORUM), node outage và write timeout; không suy mọi CL trả một hình ảnh state giống nhau ngay tức thì.

### 30.6. ScyllaDB version semantics

ScyllaDB có tính năng LWT/conditional và tooling tùy version/managed service. Cần validate chính xác feature support trước khi dùng lệnh cụ thể trong môi trường thực.

## 31. Redis: SET NX và atomic scripts

Ví dụ dedup ngắn hạn:

~~~text
SET processed:consumer-A:e1 1 NX EX 3600
~~~

NX chỉ tạo key nếu chưa có, EX đặt TTL. Đây có thể là claim idempotency trong một giờ **nếu dữ liệu Redis và failure semantics phù hợp**, không tự bảo đảm permanent exactly-once business processing.

### 31.1. Lỗ hổng claim trước effect

Redis SET NX thành công rồi worker crash trước khi gửi effect: các lần retry thấy key và bỏ qua effect. Cần trạng thái PROCESSING/SUCCEEDED, lease/recovery và effect idempotent.

### 31.2. Redis persistence và failover

Một claim đã trả success có thể không bền theo persistence/replication configuration. Sau failover, claim mất khiến duplicate lọt qua.

### 31.3. Lua/script atomics

Redis Lua hoặc Redis Functions có thể kiểm tra version và cập nhật state atomically trong scope command/script, nhưng script không thể tạo transaction với một payment provider khác. Với Redis Cluster, truy cập keys của script bị ràng buộc slot/cluster semantics.

### 31.4. TTL quá ngắn

Broker replay sau 48 giờ trong khi dedup key TTL 1 giờ sẽ được coi là mới. Nếu effect không thể lặp, dùng persistent ledger có retention phù hợp.

### 31.5. Redis Stream consumer groups

Pending entries, reclaims, ACKs và redelivery có thể tạo duplicates; xử lý idempotently trước/đồng thời với ACK theo crash-safe contract, test worker chết ở nhiều điểm.

### 31.6. Đếm INCR không idempotent

INCR counter một lần khác INCR hai lần. Đừng retry INCR sau timeout nếu không có protocol tránh duplicate increments theo operationId.

## 32. Elasticsearch/OpenSearch: events đảo thứ tự làm regression index

Một search projection nhận:

~~~text
ProductUpdated(P1, price=200, version=9)
ProductUpdated(P1, price=100, version=8)  // late arrival
~~~

Nếu indexer chỉ dùng last arrival wins, search có thể trả giá 100 thay vì 200.

### 32.1. External versioning

Một số search engines/APIs hỗ trợ versioning/concurrency control trong phạm vi được định nghĩa. Thiết kế index write theo source version/seq_no/primary_term hoặc update protocol tương ứng; không đồng nhất search internal version với domain version.

### 32.2. Eventual index refresh

Ghi index thành công chưa chắc query thấy ngay. Test với refresh semantics, không kết luận event bị mất chỉ từ một search ngay sau write.

### 32.3. Delete và late update

Delete v10 rồi update v8 tới sau có thể hồi sinh document nếu không có tombstone/version gate đủ bền. Test cả sau index rollover/rebuild.

### 32.4. Reindex replay

Tạo index mới từ snapshot rồi replay CDC chồng lấn cần idempotent versioned writes. Test repeated backfill rows và concurrent updates.

### 32.5. Semantic correctness

So source-of-truth vs search index sau convergence watermark. Search ranking/analyzer có thể thay đổi hợp lệ, nhưng indexed business field/version không được regress.

## 33. CDC, outbox và partition migration

~~~text
Source NoSQL --> Outbox/CDC --> Broker --> Projection B
      |                             |
      +---------- Backfill ---------+
~~~

### 33.1. Snapshot overlap

Backfill đọc Order O101 v5, CDC đã áp v7 ở B, rồi backfill v5 ghi đến muộn. Nếu không có version guard, B regress.

### 33.2. Thời điểm bắt đầu CDC

Nếu backfill snapshot t0 nhưng CDC chỉ bắt đầu t1>t0, các writes giữa t0 và t1 có thể biến mất. Test checkpoint capture/replay từ snapshot boundary.

### 33.3. CDC duplicate

Resume token hoặc offset có thể khiến một nhóm events được đọc lại. Consumer inbox/version guard phải chống duplicate, không tạo side effects mới khi reprocess.

### 33.4. Shard/partition rebalance

Đổi routing có thể khiến một entity được xử lý từ hai owners trong migration window. Generation/fencing và stable event version giúp bảo vệ; test double-owner race.

### 33.5. End-to-end reconciliation

Đừng chỉ kiểm số lượng events consumed; so source counts/hashes/business invariants với projection theo partition và committed checkpoint.

## 34. Restore và replay: sự kiện cũ quay lại sau nhiều tuần

Một hệ restore projection từ backup tuần trước, sau đó replay event archive tới mốc hiện tại.

### 34.1. Restore có thể làm mất inbox

Nếu inbox ledger không cùng mốc với business state, một effect đã thực hiện trước đó có thể bị replay như mới.

### 34.2. External effects không rollback theo database

Payment đã capture và email đã gửi vẫn là facts ngoài database. Consumer replay phải có side-effect suppression hoặc provider reconciliation; không chạy lại webhook live chỉ vì event xuất hiện.

### 34.3. Version epoch sau restore

Nếu sequence reset, old events có thể trông mới hơn; giữ generation/epoch/fencing và source authority.

### 34.4. Late event vượt TTL

Restore/replay có thể lâu hơn dedup TTL bình thường. Xác định replay mode đặc biệt hoặc persistent dedup registry, không dựa vào cache keys ngắn hạn.

### 34.5. Replay có checkpoint

Ghi source offset/checkpoint, last applied version và event corruption/gap metrics. Cho phép resume idempotently sau restart.

## 35. Multi-region active-active và xung đột không giải được bằng thứ tự arrival

Region A ghi status=APPROVED, Region B ghi status=CANCELLED gần như đồng thời.

### 35.1. Version collision

Nếu mỗi Region tăng integer local lên 8, cả hai có v8 nhưng payload khác. Không thể dùng “event đến cuối thắng” như business truth mà không xác định conflict policy.

### 35.2. Ownership/fencing

Một thiết kế có primary owner/epoch cho entity giúp reject writes từ owner cũ sau failover. Test old owner tiếp tục gửi late writes sau khi mất lease.

### 35.3. Causal metadata

Lamport/vector clocks có thể nhận diện causal order hoặc concurrent updates; không tự quyết định business winner. Cần resolver theo domain.

### 35.4. CRDT khi phù hợp

Set union hoặc counters được thiết kế là CRDT có thể hội tụ qua reorder/duplicates theo semantics riêng; không áp CRDT tùy tiện cho thanh toán, chuyển quyền hoặc trạng thái đơn hàng có ràng buộc.

### 35.5. Test split brain

Cắt network giữa Regions, cho hai nơi nhận writes rồi nối lại. Assert safety/conflict outcomes theo policy, chứ không mặc định chỉ cần eventually equal là đúng.

## 36. Test matrix: duplicate, reorder, late và lỗi xác nhận

| Case | Inject | Oracle cần kiểm |
|---|---|---|
| D1 | Cùng HTTP command 2 lần tuần tự | Cùng result/operation ID |
| D2 | Cùng command 100 lần đồng thời | Tối đa một business effect |
| D3 | ACK mất sau DB commit | Retry không tạo bản ghi khác |
| D4 | Cùng eventId 10 lần | Tối đa một semantic effect |
| D5 | EventId giống, payload khác | VERSION/DEDUP CONFLICT |
| R1 | v3 đến trước v2 | Không regress/gap policy đúng |
| R2 | v2 hoàn tất sau v3 | Conditional write chặn stale overwrite |
| R3 | Hai producers cùng version | Conflict được phát hiện |
| R4 | Backfill v5 sau CDC v9 | B vẫn v9 |
| L1 | Event tại window boundary | Window [start,end) đúng |
| L2 | Event muộn trong grace | Correction/retraction đúng |
| L3 | Event muộn vượt grace | DLQ/late stream/explicit policy |
| L4 | Upsert cũ sau delete | Tombstone không hồi sinh |
| F1 | Crash sau inbox claim | Không mất effect vĩnh viễn |
| F2 | Crash sau side effect trước ACK | Không lặp effect |
| F3 | Redis dedup key expire/restart | Contract retention được kiểm |
| F4 | Failover/owner epoch thay đổi | Old worker không ghi stale |
| P1 | Retry storm + overload | Bounded concurrency/queue |
| P2 | Consumer lag nhiều giờ | Recovery, TTL, backlog an toàn |

### 36.1. Thử lỗi theo thời điểm

Đặt fault at-before-commit, after-commit-before-ACK, after-effect-before-inbox-complete, before-broker-ACK và during-rebalance. Chỉ một network timeout test chung không thể bao phủ hết.

### 36.2. Thử mất message vĩnh viễn

Trong at-least-once không có giả định rằng event chắc chắn đến trước deadline nếu source/broker hỏng hoặc retention bị vượt. Tạo gap không thể tự điền để xác minh DLQ/rebuild runbook.

### 36.3. Thử dữ liệu corrupt

Same eventId khác payload hoặc invalid schema phải không được âm thầm bỏ để “đạt throughput”; cần quarantine và alert.

## 37. Kiểm thử deterministic trước chaos ngẫu nhiên

~~~text
Schedule A: e1, e1, e2, e3
Schedule B: e1, e3, e2, e2
Schedule C: e2, e1, e3
Schedule D: e3, e2, e1
Schedule E: e1, delete(v4), stale update(v2)
~~~

### 37.1. Lịch cố định

Mỗi lịch gắn expected behavior theo full-state/delta semantics. Dùng cùng seed, fake clock và controlled executor để test tái hiện.

### 37.2. Exhaustive permutations khi n nhỏ

Với ba events và duplicate counts giới hạn, kiểm được nhiều schedules. Với n lớn, số permutations tăng nhanh; dùng property-based generator/model checking chọn lọc.

### 37.3. Random test có seed

Lưu random seed, generated schedule IDs, injected fault positions và engine/test version. Nếu failed case không tái hiện, khó sửa race.

### 37.4. Shrinking

Khi property test tìm lịch 200 events gây fail, shrink về lịch nhỏ nhất có cùng lỗi, ví dụ [v2,v3,duplicate v2], giúp phân tích.

### 37.5. Oracle độc lập

Test oracle nên dùng mô hình đơn giản và invariants, không copy nguyên production reducer rồi so hai kết quả giống nhau do cùng bug.

## 38. Property-based test cho tính chất cần giữ

~~~text
P1: insert duplicate delivery -> no extra business effect.
P2: shuffle independent full-state events -> max version wins.
P3: append any stale version -> state must not regress.
P4: tombstone vN then event v<N -> no resurrect.
P5: crash at any supported point -> no double external effect.
P6: gap resolved and retries stop -> projection converges.
~~~

### 38.1. Tiền đề

P2 đúng với full-state events tự đủ và cùng generation. Với deltas, đảo tùy ý phải buffer hoặc rebuild, không apply ngay.

### 38.2. Idempotency theo payload

Giữ operationId cố định, thay payload để assert reject; không coi mọi request cùng key là duplicate hợp lệ.

### 38.3. Tombstone retention

Advance fake clock trước TTL, đúng TTL, sau TTL rồi phát stale event. Nếu policy không còn bảo vệ sau TTL, ghi limitation và monitor replay window.

### 38.4. Liveness

Khi gap được lấp và worker/source khỏe, pending phải drain trong deadline định nghĩa. Không chỉ chứng minh không cập nhật sai mà bỏ quên consumer kẹt.

## 39. Concurrency test: hai workers cùng một key

~~~text
Worker A read version=5
Worker B read version=5
Barrier releases both
A tries to apply version=6
B tries to apply version=7
~~~

Nếu writes là replace vô điều kiện, final có thể v6. Với database conditional gate, final không regress theo policy.

### 39.1. Dùng barrier có chủ đích

Đồng bộ hai workers ngay trước conditional write bằng CountDownLatch/Phaser thay vì Thread.sleep. Lặp nhiều lần và đo actual applied versions.

### 39.2. DB thật cần tham gia

Mock repository không phản ánh transaction isolation/network timeout/failover. Unit reducer cộng integration test engine thật cho guarantees quan trọng.

### 39.3. Intermediate states

Sau mỗi committed write, đọc với consistency phù hợp để xác minh version không lùi. Eventual replica read có thể thấy stale vì replication lag, phải phân biệt.

### 39.4. Fencing token

Worker cũ sau lease expiration không được ghi. Lưu epoch/owner trong conditional predicate. Test old worker resumes after new owner commits.

## 40. Fault injection phải có phạm vi và điểm dừng

Một test plan ghi:

- Môi trường cô lập/staging hoặc controlled experiment được duyệt.
- Thành phần gây lỗi: client, DB, network proxy, broker, worker.
- Điểm inject trước/sau commit/ACK.
- Thời lượng, max QPS, max outstanding tasks.
- Expected invariant và monitoring.
- Kill switch, stop condition, recovery owner.
- Cleanup test data và bảo vệ PII.

### 40.1. Không thử bằng thanh toán thật

Double-charge test dùng sandbox provider/fixtures; không capture payments của khách hàng để kiểm lỗi.

### 40.2. Test cả recovery

Sau khi lỗi mạng/broker được gỡ, xác minh pending/lag giảm, không retry storm, state cuối hội tụ và không duplicate effects.

### 40.3. Crash khác exception

Catch block khi exception không mô phỏng process kill tại thời điểm commit. Dùng process termination/container restart, network proxy và real DB boundary ở integration/chaos test.

### 40.4. Evidence độc lập

Ghi checkpoint/audit từ nguồn bền để kiểm sau crash; nếu metrics recorder cùng process chết, còn authoritative DB/provider evidence.

## 41. Load test: duplicates và retry amplification

Giả sử có 10.000 logical operations/giây, trong đó 20% timeout và retry đúng một lần:

\[
\mathrm{AttemptRate}=10{,}000 + 0.2\times10{,}000 = 12{,}000/s.
\]

Amplification 1,2× chỉ đúng khi mỗi operation trong nhóm timeout retry thêm **một** lần. Retry nhiều tầng hoặc nhiều lần có thể làm hệ quá tải nhanh hơn.

### 41.1. Không chỉ đo accepted QPS

Đo logical operations, physical attempts, duplicate claims, conditional conflicts, broker redeliveries và external effects. 12.000 attempts không được tạo 12.000 orders nếu chỉ có 10.000 commands.

### 41.2. Retry storm

Thất bại transient làm client retry đồng bộ có thể khiến DB càng quá tải. Dùng exponential backoff+jitter, max attempts, deadlines, rate limits và retry budget.

### 41.3. Retry nhiều tầng

Gateway, HTTP client, SDK và worker framework có thể đều retry. Với 3 tầng mỗi tầng có tối đa 3 attempts, một operation có thể bị nhân nhiều lần trong trường hợp xấu; cần inventory tổng số calls.

### 41.4. Conditional failure không luôn retryable

ConditionalCheckFailed vì duplicate/stale là kết quả logic cần xử lý, không nên retry vô hạn như throttling/network errors.

### 41.5. Dedup store dưới tải

Unique constraints, conditional claims và LWT có thể thành hot partition/lock bottleneck. Đo p99 và contention khi nhiều retries cùng operationId.

## 42. Hot key khác nhiều key phân tán

100.000 events/s trên 100.000 orderIds khác 100.000 events/s cùng O101.

### 42.1. Hot entity

Key-level serial processing có thể gây hàng đợi dài cho O101. Cần per-entity backpressure, fair scheduling và gap timeout.

### 42.2. Duplicate storm

1.000 clients retry op-101: chỉ một winner và stable result, không tạo 1.000 orders hoặc 1.000 transactions nặng mỗi giây vô hạn.

### 42.3. Many-key fairness

Giữ throughput cho O102/O103 khi O101 gặp poison event/gap. Không để một key chiếm tất cả worker slots.

### 42.4. Broker lag và retention

Consumer lag tăng gần event-log retention expiry có thể khiến gap không điền được. Monitor time-to-expiry và kích hoạt recovery sớm.

### 42.5. Pending buffer size

Giới hạn pending events per key/global, bytes và age; khi vượt, chuyển recovery path thay vì OOM.

## 43. Batch delivery và partial success

Một batch e1,e2,e3 được gửi, e1/e2 commit rồi client timeout. Retry toàn batch có thể thực thi e1/e2 lại.

### 43.1. Batch không mặc nhiên atomic

Các NoSQL batch APIs có thể tối ưu truyền tải nhưng không bảo đảm atomicity cho mọi items/partitions. Xem contract của từng engine và response per item.

### 43.2. Per-event dedup

Đừng chỉ dedup batchId nếu partial success có thể xảy ra. Lưu stable eventId/item operationId để reprocess phần chưa xác định.

### 43.3. Batch split đảo thứ tự

Một batch bị chia thành nhiều partitions/requests có thể hoàn tất khác source order. Key-level version gate vẫn cần.

### 43.4. Retry khi outcome không rõ

Reconcile committed items theo stable IDs trước khi replay những phần side-effecting; không tính số HTTP calls là kết quả nghiệp vụ.

## 44. Mức consistency quyết định oracle của test

### 44.1. Eventual read chưa thấy write không chứng minh write mất

Một replica có thể đang ở v7 khi source đã commit v8. Test phải dùng consistency contract và convergence deadline thay vì báo lỗi ngay.

### 44.2. Safety tại write authority

Unique/conditional write/LWT cần được kiểm bằng commit operation semantics và authoritative outcome. Read stale không chứng minh condition thất bại.

### 44.3. Không mặc định linearizability

Nếu engine hỗ trợ eventual/quorum theo setting, test không được tự yêu cầu total order mạnh hơn guarantee thực tế.

### 44.4. Temporal properties

Safety: không bao giờ charge trùng. Liveness: trong 30s sau network phục hồi, projection bắt kịp checkpoint N. Hai loại assertions có lifetime khác.

### 44.5. Quorum không sửa business events

Quorum ACK cải thiện một số durability/consistency guarantees, không tự làm operation idempotent hoặc event v3 xử lý đúng khi v2 thiếu.

## 45. Side effects ngoài NoSQL

~~~text
OrderPaid event
  -> update MongoDB order
  -> send email
  -> call loyalty provider
  -> emit analytics event
~~~

### 45.1. Một event duplicate có nhiều effects

MongoDB update có thể idempotent, nhưng loyalty points cộng trùng và email gửi hai lần. Test từng external boundary.

### 45.2. Outbox cho outbound messages

Ghi event cần publish cùng business mutation rồi dispatch retryable. Downstream vẫn cần stable eventId/dedup.

### 45.3. External provider idempotency

Truyền stable business operation ID nếu provider hỗ trợ, không sinh key mới mỗi retry; kiểm scope/window và reconcile UNKNOWN.

### 45.4. Notification intent

Một durable notification intent có status/retry/dedup key giúp tránh gửi trùng trong giới hạn contract; provider response timeout vẫn có unknown outcome cần giải quyết.

### 45.5. Test count

Dùng sandbox provider/spy theo stable key; assert tối đa một effect sau lịch duplicate/reorder/crash.

## 46. Metrics để chẩn đoán nhiễu

| Nhóm | Metric gợi ý | Ý nghĩa |
|---|---|---|
| Logical calls | logical_operations_total | Số operations không tính retries |
| Attempts | request_attempts_total | Số physical attempts |
| Retry | retry_attempts_total{reason} | Nguyên nhân/lượng retry |
| Dedup | duplicate_claims_total | Bao nhiêu claims bị nhận diện trùng |
| Conflicts | idempotency_payload_conflicts_total | Cùng key khác payload |
| Consumer | duplicate_events_total{consumer} | Event delivery lặp |
| Reorder | stale_events_rejected_total | Events cũ bị chặn |
| Gap | sequence_gap_detected_total | Version thiếu |
| Pending | pending_gap_events | Hàng đợi gap |
| Late | event_lateness_seconds | Độ trễ eventTime đến processing |
| Windows | late_events_total{policy} | Event quá hạn/được sửa |
| Tombstone | resurrection_blocked_total | Stale update sau delete |
| Outcomes | unknown_outcome_total | Commit không rõ kết quả |
| External | business_effects_total{type} | Hiệu ứng thực theo stable key |
| DLQ | poison_events_total | Event invalid không retry vô hạn |

Những tên metric là ví dụ do ứng dụng instrument; không phải mặc định của một sản phẩm.

### 46.1. Không gắn eventId/orderId làm label

High-cardinality labels gây tốn bộ nhớ và có thể lộ PII. Dùng query class, consumer, error category, deployment version và scope bucket; raw IDs chỉ trong evidence store có kiểm soát.

### 46.2. Có mẫu số rõ

DuplicateRate = duplicate deliveries / total delivery attempts khác duplicate business effect rate. Không gộp hai mẫu số.

### 46.3. Track age, không chỉ depth

Pending queue 10 items tồn tại 2 ngày nguy hiểm hơn 10.000 items vừa đến trong 1 giây. Đo oldest pending age và max gap age.

### 46.4. Histogram lateness

Đo p50/p95/p99 event lateness, late-after-grace share và DLQ trend theo source, tránh đặt allowed lateness dựa vào average.

### 46.5. Đo sự thật kinh doanh

Chỉ thấy dedup cache hit tăng chưa chứng minh “không double charge”. Cần audit effect IDs và reconciliation với external authoritative service.

## 47. Alert thresholds và cutover gates

Một experiment chỉ đạt khi:

- Không xuất hiện business invariant violation trong test workload.
- Atomic claim/conditional guards vẫn đúng dưới concurrency.
- Duplicate suppression đúng trên toàn retry/replay horizon đã cam kết.
- AppliedVersion không regress, tombstones không resurrect.
- Gap/late-event classifications hoạt động; DLQ có owner/runbook.
- Liveness được đo sau fault recovery.
- Retry amplification và backlog không vượt budget.
- p95/p99 latency/error rate của nghiệp vụ không vi phạm SLO.
- External side-effect counts khớp operation IDs.
- Replay từ backup/checkpoint vẫn cho state được chấp nhận.

### 47.1. 99,99% success không che một double-charge

Severity theo domain quan trọng hơn tỷ lệ errors trung bình. Một double payment có thể là stop-the-line dù load throughput đẹp.

### 47.2. Không lấy “không thấy bug” làm bảo đảm tuyệt đối

Nêu test coverage, fault matrix, seed, scale, engine versions và giới hạn. Property test có n samples không chứng minh mọi lịch đã được cover.

### 47.3. Có rollback/kill switch

Nếu test trên production canary gây tăng latency hoặc effects bất thường, cần cách dừng lỗi nhanh và reconcile những operations đã xảy ra.

## 48. Runbook: retry storm sau timeout

### Bước 1 — Chẩn đoán mẫu hình

Đo logical QPS, attempts, retry reasons, DB throttling, conditional conflicts, p99 và số idempotency claims.

### Bước 2 — Giảm áp lực

Giảm concurrency/retry budgets, thêm jitter, dừng retries cho non-retryable conflicts; bảo vệ authoritative store khỏi overload.

### Bước 3 — Xác minh outcomes

Phân biệt failed-before-send, failed-before-commit, committed-but-ACK-lost và unknown. Không replay external effects khi chưa reconcile.

### Bước 4 — Kiểm tra claim ledger

Xem stale PROCESSING, duplicate payload conflicts, TTL expiry, hot key và version collision.

### Bước 5 — Recovery

Đưa unknown operations qua reconciliation worker có idempotency/fencing, không reset toàn bộ ledger.

### Bước 6 — Điều tra nguyên nhân

Client timeout quá thấp, SDK retries, latency spikes, network fault hay overloaded DB? Ghi evidence để cập nhật retry policy/test matrix.

## 49. Runbook: projection bị ghi lùi sau reorder

### Bước 1 — Xác định scope

Những entity nào appliedVersion giảm, keyspace/table nào và bắt đầu từ deployment/version nào?

### Bước 2 — Chặn writer lỗi

Tạm dừng consumer hoặc chặn stale writes bằng conditional gate; không tiếp tục replay bừa làm sai thêm.

### Bước 3 — Xem timeline

Đối chiếu source version sequence, eventId, broker offset, completion order, backfill checkpoint và actual DB mutation.

### Bước 4 — Phân loại

Lỗi last-arrival-wins, read-then-write race, same-version conflict, missing tombstone, generation reset hay CDC/backfill overlap?

### Bước 5 — Repair có kiểm soát

Rebuild projection từ authoritative source theo checkpoint hoặc apply version-aware repair; không để comparator tự mutate trong production read path.

### Bước 6 — Kiểm chứng

Đối soát counts, hashes, business states, version monotonicity và no duplicate external effect; chạy regression schedule đã gây lỗi.

## 50. Runbook: sự kiện đến muộn vượt allowed lateness

### Bước 1 — Không drop im lặng

Ghi category, source/partition, eventTime, arrival delay và event reference có bảo vệ; chuyển late stream/DLQ nếu policy yêu cầu.

### Bước 2 — Xác định business impact

Đây là telemetry không critical hay doanh thu/ledger bắt buộc đúng? Quyết định correction/recompute/compensation theo owner.

### Bước 3 — Kiểm tra upstream

Clock skew, offline client, queue backlog, cross-region network, stuck consumer hay watermark config sai?

### Bước 4 — Sửa với version/revision

Nếu recompute window, publish corrected aggregate version và tránh áp duplicate correction. Nếu không được nhận nữa, để lại audit trail.

### Bước 5 — Điều chỉnh ngưỡng

Dùng lateness distribution và business deadline để xác định allowed lateness, không nới vô hạn để che pipeline lag.

## 51. Bài tập 1 — retry sau khi commit nhưng mất ACK

Một user POST /orders với operationId=op-101. MongoDB đã commit order O101 nhưng network drop response; Java HTTP client retry request.

1. Tại sao không thể suy lần đầu chưa commit?
2. Nếu code mỗi lần tạo UUID làm orderId, có thể xảy ra gì?
3. Thiết kế unique idempotency claim theo tenantId+operationType+operationId.
4. Nên trả gì nếu retry xảy ra khi lần đầu vẫn PROCESSING?
5. Cần gì để đảm bảo claim và order creation không bị crash gap?
6. Nếu retry payload khác nhưng key giống, response nên thế nào?
7. Fault injection cần đặt trước hay sau DB commit để bắt lỗi nguy hiểm nhất?

## 52. Bài tập 2 — cùng một request được gửi 100 lần đồng thời

Một load generator phát 100 HTTP POST với cùng idempotency key, cả 100 requests bắt đầu tại barrier.

1. Viết các invariants về số orders và resultOrderId.
2. Một check-then-insert hai bước có race như thế nào?
3. Unique index/conditional PutItem giúp chọn winner ra sao?
4. Nếu 99 requests nhận duplicate-key, nên retry create hay đọc existing result?
5. Làm sao đo physical attempts khác logical operations?
6. Nếu first winner crash sau claim nhưng trước create, hệ phục hồi thế nào?
7. Một test chỉ chạy tuần tự 100 requests có phát hiện race đầy đủ không?

## 53. Bài tập 3 — idempotency key dùng lại với payload khác

~~~text
Request 1:
  operationId=op-101
  tenantId=T17
  amountMinor=50000

Request 2:
  operationId=op-101
  tenantId=T17
  amountMinor=90000
~~~

1. Hai requests có phải duplicates hợp lệ không?
2. Chọn normalized fields nào để bind vào operation key?
3. Lưu payloadDigest mà không log raw payment data ra sao?
4. Nếu user đổi tenantId=T18 nhưng giữ key, làm sao tránh trả nhầm result T17?
5. Nếu idempotency record hết TTL sau 24 giờ, retry ở giờ 25 sẽ như thế nào?
6. Đề xuất retention cho một charge operation có hậu quả dài hạn.

## 54. Bài tập 4 — duplicate event trong consumer

Broker giao eventId=e-paid đến billing consumer ba lần do ACK lần đầu bị mất:

~~~text
Delivery e-paid #1 -> effect success -> ACK lost
Delivery e-paid #2 -> consumer restart
Delivery e-paid #3 -> retry topic
~~~

1. Inbox key nên gồm những trường nào?
2. Vì sao ghi inbox processed **sau** payment capture vẫn có crash gap?
3. Vì sao ghi processed **trước** payment capture cũng có gap?
4. Provider idempotency key cần được tạo từ business identifier nào?
5. Một search consumer khác có được xử lý e-paid không?
6. Chứng minh business effect count tối đa một lần bằng dữ liệu nào?

## 55. Bài tập 5 — event đảo thứ tự full-state

Source commit:

~~~text
e1(v1) status=CREATED
e2(v2) status=PAID
e3(v3) status=SHIPPED
~~~

Consumer nhận: [e1,e3,e2,e2,e1].

1. Nếu events chứa toàn state, version gate sẽ xử lý ra sao?
2. Final state/version phải là gì?
3. Những attempts nào bị phân loại stale/duplicate?
4. Nếu e3 là delta “increment shipmentCount”, có thể áp ngay sau e1 không?
5. Vì sao dùng processing timestamp làm version không đáng tin?
6. Viết JUnit test kiểm intermediate appliedVersion không lùi.

## 56. Bài tập 6 — hai workers race rồi ghi sai thứ tự

Hai workers cùng đọc projection v5:

~~~text
W1 handles e6(version=6).
W2 handles e7(version=7).
W2 writes v7 first.
W1 writes v6 later.
~~~

1. Nếu write là replaceOne/update unconditional, final có thể sai thế nào?
2. Thiết kế MongoDB conditional filter hoặc DynamoDB ConditionExpression ngăn v6 ghi đè v7.
3. Vì sao pure reducer đúng vẫn chưa đủ?
4. Dùng CountDownLatch/Phaser thế nào để tạo race deterministic?
5. Thử consistency level/read preference phù hợp để assert commit state.
6. Nếu v7 đã commit, W1 nên log outcome gì?

## 57. Bài tập 7 — một sequence bị mất

Consumer dùng delta events cần apply v1→v2→v3. Nó đang ở v1, nhận v3 trước và v2 bị giữ trong retry topic.

1. V3 có được apply ngay không?
2. Thiết kế pending buffer theo entity/version với max size và TTL.
3. Nếu v2 đến, consumer nên drain pending theo thứ tự nào?
4. Nếu v2 không bao giờ đến, recovery action là gì?
5. Khi v3 bị giao lại ba lần, pending store cần dedup thế nào?
6. Vì sao một global queue bị một entity gap chiếm hết là nguy hiểm?
7. Đề xuất metrics cho oldest_gap_age và pending_count.

## 58. Bài tập 8 — tombstone và sự kiện cũ

~~~text
v5 ProductUpdated(P1)
v6 ProductDeleted(P1)
v4 ProductUpdated(P1) arrives late
~~~

1. Nếu projection chỉ xóa document khi v6, v4 có thể gây lỗi gì?
2. Application-level tombstone nên giữ những metadata nào?
3. Tombstone TTL phải xét broker retention và replay horizon thế nào?
4. Nếu P1 được recreate hợp lệ, generation/epoch mới dùng ra sao?
5. Khác biệt giữa tombstone Cassandra storage và tombstone business projection?
6. Thiết kế test phát late v4 sau delete và sau fake-clock advance.

## 59. Bài tập 9 — sự kiện đến muộn trong window

Window [09:00,09:10), allowed lateness 5 phút:

~~~text
e1 eventTime=09:01, arrival=09:02, amount=100
e2 eventTime=09:04, arrival=09:05, amount=200
e3 eventTime=09:03, arrival=09:12, amount=300
~~~

1. e3 thuộc window nào theo event time?
2. Nếu watermark tiến theo engine policy và e3 vẫn trong allowed lateness, aggregate sau correction là bao nhiêu?
3. Nếu e3 đến sau grace, có những policy nào thay vì drop im lặng?
4. Nếu correction e3 redeliver, làm sao không cộng 300 lần nữa?
5. Vì sao dùng processing-time window sẽ làm sai báo cáo?
6. Thiết kế test đúng boundary 09:09:59.999 và 09:10:00.

## 60. Bài tập 10 — source event time khác processing time

Một thiết bị offline ghi eventTime=10:00 nhưng chỉ gửi tới server lúc 15:00. Đồng hồ thiết bị có thể sai 20 phút.

1. Event time có đáng tin tuyệt đối không?
2. Thiết kế ingestTime, sourceClockQuality hoặc timestamp authority metadata.
3. Đặt allowed lateness theo device/offline cohort ra sao?
4. Nếu cần fraud detection realtime, late event có thể được xử lý bù khác báo cáo lịch sử thế nào?
5. Vì sao arrival order không định nghĩa causal order?
6. Metrics lateness histogram nên phân nhóm gì mà không tiết lộ device ID?

## 61. Bài tập 11 — MongoDB unique index và transaction boundary

Một ứng dụng có collections idempotency và orders. Hai concurrent POST cùng operationId.

1. Tạo unique index trên tenantId+operationType+operationId.
2. Nếu claim insert trước rồi process crash trước create order, trạng thái nào còn lại?
3. Nếu create order trước rồi claim insert thất bại, tình huống gì xảy ra?
4. Thiết kế MongoDB transaction hoặc state machine+reconciler phù hợp.
5. Inject ACK loss sau commit và xác minh stable result.
6. Nếu mongodump/restore quay về trước một số claims, bạn phải đối soát gì?
7. Vì sao retryable writes của driver chưa thay thế business operationId?

## 62. Bài tập 12 — DynamoDB conditional claims và TTL

Một DynamoDB table Idempotency có PK=tenant#operationId, status và expiresAt.

1. Viết ConditionExpression cho claim chỉ tạo khi key chưa có.
2. Hai PutItem cạnh tranh sẽ trả kết quả như thế nào?
3. Phân biệt ConditionalCheckFailedException do duplicate với lỗi throttling.
4. Nếu item đã logical expiry nhưng TTL cleanup chưa xóa, ứng dụng phải xử lý ra sao?
5. Nếu TransactWriteItems gắn claim với order item, các giới hạn nghiệp vụ ngoài transaction còn là gì?
6. Test request ở 1 ms trước expiry, đúng expiry, và sau expiry.
7. Vì sao GSI eventual lookup không thay atomic condition trên base key?

## 63. Bài tập 13 — Cassandra/ScyllaDB LWT và counter

Một CQL consumer dùng INSERT IF NOT EXISTS để claim eventId, rồi cập nhật counter.

1. LWT giúp chặn loại trùng nào?
2. Nếu counter update xảy ra nhưng process crash trước ACK, retry có thể tạo kết quả gì?
3. Nếu LWT claim thành công nhưng counter update chưa xảy ra, làm sao phục hồi?
4. Vì sao tăng counter hai lần không idempotent dù phép cộng giao hoán?
5. Last-write-wins theo physical timestamp có chặn stale business version không?
6. Viết test với duplicate, retry và node outage theo CL thực.
7. Vì sao không suy batch nhiều partitions là một transaction toàn hệ?

## 64. Bài tập 14 — Redis SET NX và Stream redelivery

Redis worker dùng SET processed:e1 1 NX EX 3600 trước khi xử lý effect, sau đó ACK một Redis Stream entry.

1. Nếu crash sau SET NX nhưng trước effect, event có thể bị mất hiệu ứng không?
2. Nếu crash sau effect nhưng trước ACK, redelivery gây vấn đề gì?
3. Nếu Redis failover làm mất processed:e1, duplicate được xử lý ra sao?
4. Sau 2 giờ broker redeliver e1, TTL 1 giờ có còn bảo vệ không?
5. Thiết kế PROCESSING/SUCCEEDED lease và reconciliation.
6. Nếu dùng Lua để atomic claim+state update trên Redis, phần nào vẫn không atomic với external API?
7. Test reclaim pending entries và nhiều worker đồng thời.

## 65. Bài tập 15 — search projection bị hồi sinh document

Event đến indexer:

~~~text
ProductUpdated(P1, v8)
ProductDeleted(P1, v10)
ProductUpdated(P1, v9)  // late
~~~

1. Nếu indexer thực hiện last arrival wins, search sẽ sai như thế nào?
2. Cần giữ business sourceVersion và tombstone thế nào?
3. Một search internal _version có luôn bằng sourceVersion không?
4. Khi index rollover/reindex, cần copy/replay metadata nào?
5. Làm sao tách index refresh delay với lost update?
6. Viết test query sau convergence và test duplicate v9.

## 66. Bài tập 16 — CDC + backfill đụng nhau

Một projection B được backfill từ snapshot O101 v5. Trước khi backfill ghi, CDC đã cập nhật B lên v7.

1. Nếu backfill ghi vô điều kiện, final version nào có thể sai?
2. Version-aware conditional apply phải kiểm trường gì?
3. Nếu CDC stream có gap giữa snapshot checkpoint và start offset, rủi ro gì?
4. Consumer restart từ checkpoint cũ khiến events lặp, phải xử lý thế nào?
5. Test e5 từ backfill đến sau e7 từ CDC.
6. Bản đối soát source vs B phải dùng watermark/consistency nào?
7. Vì sao chỉ đếm số records bằng nhau không đủ?

## 67. Bài tập 17 — lease/fencing qua hai owners

Worker A giữ lease epoch=12 cho tenant T17. Mạng của A bị partition; worker B được cấp lease epoch=13 và xử lý v8. A hồi phục và cố ghi v7.

1. Nếu chỉ kiểm TTL lease trong memory của A, có chặn được old owner không?
2. Fencing token/epoch phải xuất hiện ở conditional write như thế nào?
3. Nếu A retry một old payment command, cần reconcile/provider idempotency ra sao?
4. Test inject network partition và resume đúng điểm.
5. Nếu B và A cùng có access token hợp lệ, IAM alone có đủ xác định owner không?
6. Những metrics nào phát hiện stale owner attempts?

## 68. Bài tập 18 — retry amplification và load budget

Hệ nhận 8.000 logical operations/s. 25% requests có timeout và mỗi request đó retry tối đa hai lần nữa.

1. Tính physical attempt rate nếu tất cả nhóm 25% đều thực hiện đủ hai retries.
2. Tính amplification factor.
3. Nếu HTTP gateway còn retry mỗi SDK call, số attempts có thể phình thế nào?
4. Viết backoff+jitter/deadline/retry budget policy.
5. Tạo load test gồm 1.000 retries cùng operationId và 7.000 distinct operations.
6. Assert số business effects, p99 và queue bounds.
7. Nếu conditional conflicts chiếm phần lớn errors, có nên tự retry chúng không?

## 69. Bài tập 19 — kiểm thử khôi phục từ backup và replay

Projection B được restore về checkpoint c100 rồi replay events c101..c200. Business đã gửi email và capture payments khi dữ liệu còn ở c190 trước sự cố.

1. Replay có được gửi email/capture lại không?
2. Inbox ledger ở checkpoint c100 có thể thiếu thông tin gì?
3. Làm sao reconcile external effects theo provider IDs?
4. Nếu tombstone của Product P1 bị TTL trước replay, rủi ro gì?
5. Nếu eventId thay đổi giữa archive/replay envelopes, key dedup nào cần giữ?
6. Test crash tại c150 rồi resume không duplicate effects.
7. Sau restore, nguồn authoritative hiện có version mới hơn thì merge/owner phải được chọn thế nào?

## 70. Bài tập 20 — thiết kế test plan end-to-end

Một dịch vụ Java vận hành Order API trên MongoDB, idempotency claims trên DynamoDB, Redis cache, outbox/Kafka cho events, một search projection và external payment provider.

Hãy thiết kế test plan có thể chạy trong môi trường cô lập:

1. Mô tả command/event IDs, source versions, generation và event time fields.
2. Viết 5 safety invariants về order creation, payment, tenant isolation, stale updates và delete.
3. Viết 3 liveness invariants về CDC convergence, pending gaps và replay.
4. Liệt kê test cases duplicate HTTP calls, ACK loss và same-key changed-payload.
5. Liệt kê schedules reorder [v1,v3,v2], [v2,v1,v3] và [delete(v8), update(v6)].
6. Thiết kế window-event late boundary tests và corrections.
7. Định nghĩa inbox/outbox/idempotency ledger retention vs broker replay window.
8. Dùng condition/transaction/LWT/Redis script ở những boundaries nào, và giới hạn của từng cái?
9. Inject process kill sau DB commit, sau external effect và trước broker ACK.
10. Thiết kế fake clock, deterministic scheduler, random seeds và shrinking failed schedules.
11. Test tải hot-key contention, physical attempts/logical ops và bounded buffers.
12. Ghi metrics/tags và đặt stop conditions, không leak raw PII.
13. Thiết kế reconciliation khi rollback/restore làm mất inbox history.
14. Nêu bằng chứng nào phải được lưu để chứng minh không double charge sau một chiến dịch chaos.
15. Khi có unexpected version conflict ở active-active Region, ai là business authority quyết định resolution?

## 71. Tổng kết

Một hệ NoSQL chịu lỗi tốt không thể chỉ đúng khi nhận một request hoặc một event đúng một lần và đúng thứ tự. Từ client timeout, lost ACK, broker redelivery, CDC replay, backfill, partition rebalance tới offline clients, hệ phải chấp nhận rằng **trùng lặp, đảo thứ tự và đến muộn là những đầu vào bình thường cần được xử lý an toàn**.

Các nguyên tắc quan trọng:

1. **Định nghĩa logical operation** bằng stable idempotency key với tenant/operation scope và payload binding; hai payload giống nhau không tự là cùng operation.
2. **Mất ACK không chứng minh chưa commit.** Test commit-before-response-loss và outcome UNKNOWN/reconciliation.
3. **Atomic claim/conditional guard** quan trọng hơn check-then-act trong application memory.
4. **Exactly-once chỉ có nghĩa trong boundary cụ thể.** Một broker transaction không tự bảo đảm email/payment đúng một lần.
5. **Inbox và outbox có vai trò khác nhau.** Outbox chống mất publish sau commit; inbox/dedup bảo vệ consumer trước redelivery, cả hai cần crash-safe design.
6. **Business state và side effects đều phải idempotent.** Order status đúng chưa chứng minh không có double charge.
7. **Arrival order không phải source order.** Key-level ordering giúp nhưng version/fencing vẫn cần.
8. **Full-state và delta events có gap policy khác nhau.** Full snapshot version mới có thể áp trực tiếp; delta cần dependencies.
9. **Không được ghi đè version mới bằng cũ.** Persist bằng conditional update/CAS/LWT hoặc protocol tương đương; reducer pure đúng chưa đủ.
10. **Tombstone/generation ngăn hồi sinh sai.** Delete không chỉ là bỏ document nếu stale events còn có thể đến.
11. **Late event theo event time khác stale state update.** Dùng watermark, allowed lateness, correction/retraction và audit.
12. **Dedup TTL phải dài đủ theo replay/recovery contract.** Restore, delayed delivery và offline clients có thể vượt một cache TTL ngắn.
13. **Deterministic schedules giúp tìm lỗi tái hiện được.** Fake clocks, barriers, injected ACK loss và property-based tests mạnh hơn Thread.sleep ngẫu nhiên.
14. **Test cả safety lẫn liveness.** Không double charge và cuối cùng hội tụ là hai phép kiểm khác nhau.
15. **Test concurrency và failover với database thật.** Mocks không thay được atomicity/durability/replication semantics.
16. **Tính retry amplification và hot-key contention.** Nhiều physical attempts không được biến thành nhiều business operations.
17. **Đo đúng các mẫu số.** Duplicate deliveries, duplicate effects, stale rejects, pending age và external outcomes không được trộn.
18. **Không bỏ poison/gap im lặng.** Quarantine/DLQ và recovery workflow cần owner, policy và alert.
19. **Phân biệt tính đúng đắn của từng engine.** MongoDB unique/transaction, DynamoDB conditional writes, Cassandra LWT/timestamps, Redis NX/TTL và search versioning có giới hạn khác nhau.
20. **Khôi phục cũng là một dạng replay có rủi ro.** Backup/CDC restoration không được làm phát lại các effects không thể đảo ngược.

Câu hỏi cuối cùng khi đánh giá một handler NoSQL:

> **“Nếu cùng một command hoặc event được gửi mười lần, đến theo mọi thứ tự hợp lệ, bị giữ lại nhiều giờ rồi xuất hiện sau failover hoặc restore, những điều kiện nào bảo đảm trạng thái không bị ghi lùi, dữ liệu đã xóa không hồi sinh, và các hiệu ứng nghiệp vụ không bị nhân đôi?”**








