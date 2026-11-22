# Chi phí giao dịch phân tán, khóa và thời gian giữ tài nguyên

Trong một cơ sở dữ liệu NoSQL, cập nhật một document hoặc một key có thể rất nhanh. Nhưng một nghiệp vụ **giữ hàng, chuyển tiền, tạo đơn hàng hoặc chuyển quyền sở hữu** thường cần nhiều bản ghi được thay đổi nhất quán. Khi dữ liệu trải trên nhiều shard, partition hay node, hệ phải phối hợp giữa những đơn vị sở hữu dữ liệu. Chi phí không chỉ là số câu lệnh ghi: còn có **truyền mạng, ghi log, kiểm tra xung đột, khóa hoặc lưu phiên bản, chờ commit, retry và phục hồi**.

Chủ đề *Chi phí giao dịch phân tán, khóa và thời gian giữ tài nguyên* thuộc chương **Giao dịch và nguyên tử** tập trung vào ba câu hỏi:

1. Bất biến nghiệp vụ nào bắt buộc phải nguyên tử và phạm vi dữ liệu nào thật sự tham gia?
2. Một giao dịch phân tán phải trả chi phí phối hợp, lock/conflict và durability ra sao?
3. Làm sao giữ giao dịch ngắn, tránh hot key, tránh retry storm, đồng thời vẫn khôi phục đúng khi lỗi?

Bài dùng mô hình MongoDB, DynamoDB, Cassandra/ScyllaDB, Redis và luồng điều phối nhiều dịch vụ để minh họa. Mỗi công nghệ có **phạm vi transaction, isolation, consistency và durability khác nhau theo phiên bản/topology**; sơ đồ 2PC bên dưới là nguyên lý để suy luận, không có nghĩa tất cả các hệ đều dùng đúng thuật toán ấy.

## 1. Phân biệt cập nhật nguyên tử và giao dịch phân tán

Một thao tác như “giảm tồn kho của Product A nếu còn đủ” có thể được bảo vệ bằng một conditional update nguyên tử trên đúng bản ghi. Nhưng nếu đơn hàng phải giữ **Product A và Product B**, rồi chuyển trạng thái Order, hệ có thêm bất biến xuyên nhiều bản ghi.

| Phạm vi | Ví dụ | Điều cần kiểm tra |
|---|---|---|
| Một key/document | Giảm số vé còn lại nếu `available >= q` | Điều kiện và phép giảm cùng atomic operation |
| Nhiều document cùng engine | Giảm Stock và tạo Reservation | Có transaction đa document hoặc recovery protocol không? |
| Nhiều shard/partition | Order chạm Stock-A, Stock-B, Order-C ở ba owner | Cần coordination, log, conflicts và commit |
| Nhiều dịch vụ/hệ thống | Order DB cùng payment provider | Không tự tồn tại một ACID transaction chung |

**ACID** thường được diễn giải:

- **Atomicity:** thay đổi thuộc phạm vi giao dịch được commit như một đơn vị hoặc không được commit.
- **Consistency:** bất biến được duy trì từ trạng thái hợp lệ sang trạng thái hợp lệ, nhưng database không tự biết mọi quy tắc nghiệp vụ.
- **Isolation:** các giao dịch đồng thời tương tác theo mức cô lập đã công bố.
- **Durability:** kết quả đã commit được bảo vệ trước các loại lỗi trong phạm vi write concern/durability contract.

Không được suy rằng “database có transaction” tức có serializable isolation xuyên nhiều region, hoặc mọi thao tác với hệ ngoài database được bao phủ.

## 2. Ví dụ xuyên suốt: một đơn hàng, ba đơn vị dữ liệu

~~~text
Order ord-1001:
  SKU-A, Warehouse HN, quantity=2
  SKU-B, Warehouse HCM, quantity=1

Partition 1: stock SKU-A = 10
Partition 2: stock SKU-B = 5
Partition 3: Order ord-1001 = PENDING_HOLD
~~~

Các bất biến:

1. Mọi pool luôn có `availableStock >= 0`.
2. Order chỉ được công bố `HELD` khi cả hai SKU đã được giữ theo chính sách.
3. Một `reservationId`/idempotency key không được trừ số lượng nhiều lần.
4. Release/expire không trả cùng một lượng hàng hai lần.
5. Không tuyên bố thanh toán thành công chỉ vì transaction database đã commit.

Nếu giảm Stock-A rồi lỗi trước Stock-B, một bước atomic đơn lẻ là chưa đủ. Cần transaction trong phạm vi database **hoặc** một workflow có trạng thái trung gian, compensation và đối soát.

## 3. Sơ đồ phối hợp nhiều participant

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as Transaction Coordinator
    participant A as Shard A
    participant B as Shard B
    participant R as Order Shard
    C->>O: Reserve order
    O->>A: Prepare/validate Stock A
    O->>B: Prepare/validate Stock B
    O->>R: Prepare Order state
    A-->>O: Ready
    B-->>O: Ready
    R-->>O: Ready
    O->>O: Durable commit decision
    O->>A: Commit
    O->>B: Commit
    O->>R: Commit
    O-->>C: Result
~~~

Đây là mô hình phối hợp **prepare/commit** ở mức khái niệm, không phải wire protocol của MongoDB, DynamoDB hoặc Cassandra. Một số engine dùng coordinator, snapshot timestamps, validation, replication quorum, transaction logs hoặc kết hợp nhiều cơ chế khác.

Một participant bị lỗi hoặc chậm có thể tác động toàn transaction, dù hai participant còn lại đã hoàn tất phần tính toán của chúng.

## 4. Phân rã chi phí giao dịch phân tán

| Thành phần | Nguyên nhân | Biểu hiện |
|---|---|---|
| Network RTT | Coordinator gọi nhiều node/shard | Latency tăng, nhạy với liên vùng |
| Routing/fan-out | Tìm và gửi tới nhiều data owner | Nhiều RPC và response |
| Read/validation | Kiểm tra version, stock, predicate | CPU, I/O, khả năng abort |
| Prepare/commit | Phối hợp để cùng quyết định | Nhiều round và trạng thái giao dịch |
| Recovery logging | Ghi quyết định/redo/undo theo engine | I/O, sync hoặc quorum wait |
| Locks/conflict tracking | Bảo vệ cập nhật cạnh tranh | Wait, abort, deadlock |
| Snapshot retention | Giữ phiên bản cho transaction đang hoạt động | RAM/disk/GC và dọn phiên bản trễ |
| Retry/backoff | Conflict, timeout hoặc failover | Tăng tổng tải và p99 |
| Index maintenance | Những field được sửa có index | Write amplification |
| Coordinator recovery | Xử lý trạng thái prepared/in-doubt | Tăng độ phức tạp vận hành |

Một mô hình thời gian đơn giản:

\[
T_{tx}\approx T_{routing}+T_{validation}+T_{coordination}+T_{commit}+T_{waiting}+T_{response}
\]

Các bước có thể chạy song song, nên đây **không phải công thức tính thời gian chính xác của một sản phẩm**. Nó giúp phân loại nguyên nhân trong trace. Khi `T_waiting` cao hơn hẳn các phần khác, tối ưu một lệnh serialize nhỏ có thể không cải thiện tail latency đáng kể.

## 5. Two-phase commit: hai giai đoạn không miễn phí

**Two-phase commit (2PC)** cổ điển phối hợp các participants qua:

- **Prepare:** coordinator hỏi participant có thể commit không; mỗi participant kiểm tra, ghi trạng thái chuẩn bị và bảo đảm có thể tuân theo quyết định về sau theo giao thức.
- **Commit/Abort:** coordinator quyết định và thông báo; participant hoàn tất hoặc hủy.

~~~mermaid
flowchart TD
    A["BEGIN"] --> B["PREPARE participants"]
    B --> C{"Tất cả READY?"}
    C -->|Không| D["ABORT decision"]
    C -->|Có| E["COMMIT decision"]
    D --> F["Notify abort and release"]
    E --> G["Notify commit and release"]
~~~

**Chi phí 2PC:** thêm trao đổi mạng, ghi log trạng thái, chờ prepare, giữ tài nguyên tới khi có quyết định và phục hồi transaction in-doubt. Trong 2PC cổ điển, coordinator chết tại thời điểm xấu có thể khiến prepared participants **bị chặn khi chờ quyết định** cho tới khi coordinator/recovery protocol giải quyết.

### 5.1. 2PC khác consensus và replication

2PC xử lý **quyết định chung giữa participants**. Consensus, chẳng hạn họ Raft/Paxos, giải bài toán đồng thuận giữa các replica trong một mô hình lỗi/quorum cụ thể. Một hệ có thể dùng consensus để lưu durable transaction decisions hoặc replicate các bản ghi, nhưng 2PC và consensus **không đồng nghĩa**.

Có quorum ở mỗi shard không tự biến nhiều cập nhật shard thành một transaction atomic. Ngược lại, 2PC không tự bảo vệ mọi trường hợp mất coordinator mà không có cơ chế durable decisions và recovery.

## 6. Chi phí của participant chậm nhất

Khi coordinator gửi prepare song song tới ba shard, phase thường phải đợi tất cả participant cần thiết:

\[
T_{\text{phase}}\gtrsim\max(T_A,T_B,T_C)
\]

Đây là mô hình để hiểu **tail latency**, không phải đồng nhất transaction time với một phép max duy nhất. Một shard bị network jitter, compaction, cache miss hoặc GC có thể kéo cả transaction chậm. Giao dịch chạm nhiều owner hơn cũng có nhiều cơ hội gặp một participant chậm.

Nếu dữ liệu nằm ở nhiều region, RTT liên vùng có thể lớn hơn nhiều RTT nội cụm. Không thể suy p99 end-to-end bằng cách cộng p99 của mỗi shard mà không xét thứ tự, sự phụ thuộc và tương quan giữa các độ trễ. Cần trace theo transaction thực.

## 7. Các loại lock và cơ chế đồng thời

Từ “lock” không chỉ có nghĩa một mutex trong mã ứng dụng:

| Cơ chế | Mục đích | Đánh đổi |
|---|---|---|
| Exclusive write lock | Chặn ghi xung đột trong phạm vi nào đó | Writer khác chờ/abort |
| Shared/read lock | Cho phép một số lượt đọc đồng thời | Có thể chặn writer theo engine |
| Intent lock | Biểu diễn ý định khóa ở cấp cao | Cần hiểu hierarchy/engine |
| Document/key lock | Phạm vi bản ghi hẹp | Hot record tạo contention |
| Range/predicate lock | Bảo vệ tập/đoạn key theo isolation | Tăng phạm vi tranh chấp |
| Metadata/schema lock | Phối hợp DDL/index và dữ liệu | Migration có thể đụng workload |
| MVCC snapshot | Reader thấy version nhất quán theo mức cô lập | Giữ old versions/metadata |
| Optimistic CAS/OCC | Ghi nếu version/predicate không đổi | Abort/retry khi tranh |
| Distributed lease | Quyền sở hữu có hạn ở một service ngoài | Hết lease cần fencing để tránh ghi stale |

**Không phải mọi database giữ khóa độc quyền từ khi BEGIN tới COMMIT.** Có engine dùng MVCC, optimistic concurrency và conflict detection. Cần hiểu **transaction lifetime** khác **thời gian giữ một khóa cụ thể**.

## 8. Transaction lifetime khác lock hold time

- **Transaction lifetime:** từ khi bắt đầu transaction cho tới commit/abort và giải phóng transaction state.
- **Lock hold time:** khoảng một lock cụ thể được giữ.
- **Resource retention time:** khoảng mà snapshot, connection, transaction metadata, undo/write set hoặc prepared state còn chiếm tài nguyên.

Ví dụ một transaction bắt đầu, đọc snapshot 2 giây rồi mới sửa một document trong 10 ms. Không được khẳng định document write lock đã bị giữ 2 giây nếu engine chỉ lấy lock lúc ghi. Nhưng snapshot/transaction state có thể đã tồn tại trong 2 giây và gây áp lực nhất định.

Một transaction dài có thể ảnh hưởng:

- Thời gian giữ old versions, ngăn garbage collection/cleanup sớm.
- Số phiên/connection/transaction slots đang chiếm.
- Memory cho read/write sets và recovery metadata.
- Thời gian các writers khác gặp conflict hoặc lock wait.
- Prepared participant chờ quyết định và recovery khi client biến mất.

Điểm cần tối ưu là **giảm thời gian giữ các tài nguyên có thể tranh chấp**, không chỉ tối ưu một câu lệnh cuối cùng.

## 9. Hot key: một bất biến có thể làm nghẽn cả cụm

Giả sử hàng trăm nghìn người tranh một pool:

~~~text
capacityPool:event-42:standard
  available = 100
~~~

Tất cả request đều cần cập nhật cùng một counter nếu thiết kế tập trung. Dù cụm có nhiều máy, khả năng phối hợp trên **một nguồn quota có thẩm quyền** là điểm nóng.

Với mô hình lý tưởng chỉ một thao tác được dùng tài nguyên độc quyền tại một thời điểm, nếu mỗi lượt chiếm `H` giây:

\[
\mu_{\text{serial}}\lesssim 1/H
\]

| Đoạn tuần tự chiếm giữ | Công suất lý tưởng minh họa |
|---|---:|
| 2 ms | khoảng 500 lượt/s |
| 10 ms | khoảng 100 lượt/s |
| 50 ms | khoảng 20 lượt/s |

Đây là **mô hình giới hạn một tài nguyên tuần tự**, không phải benchmark hay giới hạn công bố của MongoDB, Redis, DynamoDB. Engine thực tế còn có batching, conflict retries, sharding/escrow, CPU, network và các yếu tố khác.

Khi tốc độ đến cao hơn mức xử lý ổn định, queue tăng; client timeout rồi retry, retry lại làm tăng tải. Một lỗi thời gian phản hồi có thể trở thành **retry storm** nếu không có backoff và admission control.

## 10. Little's Law và chi phí giao dịch quá dài

Trong điều kiện hệ ổn định, Little's Law:

\[
L=\lambda W
\]

Trong đó `L` là số công việc trung bình đang ở trong hệ, `λ` là throughput hoàn thành trung bình và `W` là thời gian trung bình của công việc.

Giả sử hệ hoàn thành ổn định 500 transaction/s:

| Thời gian trung bình | Transaction in-flight trung bình |
|---|---:|
| 20 ms | 10 |
| 50 ms | 25 |
| 200 ms | 100 |
| 500 ms | 250 |

Thời gian sống tăng từ 50 lên 200 ms, nếu throughput vẫn giữ được 500/s, lượng giao dịch đang hoạt động tăng từ 25 lên 100. Các transaction này có thể tiêu thụ connection, snapshot metadata, memory và những tài nguyên riêng của engine.

**Không được lấy `L` làm số lock đang giữ** nếu `W` được đo từ HTTP request đầu tới response cuối. Khi hệ đã bão hòa, throughput có thể giảm nên những số liệu minh họa không thể dùng để dự đoán chính xác queue length mới.

## 11. Deadlock, lock wait và write conflict

Một deadlock cổ điển:

~~~text
Transaction T1                 Transaction T2
--------------                 --------------
Giữ lock Stock-A               Giữ lock Stock-B
Muốn lock Stock-B              Muốn lock Stock-A
Chờ T2                         Chờ T1
~~~

Các giao dịch đang giữ tài nguyên mà bên kia cần, tạo chu trình chờ. Cơ chế xử lý tùy engine: **deadlock detection**, chọn một victim để abort, lock timeout, ưu tiên dựa vào timestamp hoặc optimistic conflict handling.

| Hiện tượng | Ý nghĩa | Hướng xử lý |
|---|---|---|
| Lock wait | Chưa nhận được tài nguyên | Đo wait duration, giảm contention |
| Deadlock | Có chu trình chờ không tự tiến triển | Abort một transaction, retry an toàn |
| Write conflict | Hai transaction ghi không tương thích | Kiểm tra trạng thái, retry theo contract |
| Client timeout | Client không biết kết quả đúng hạn | Không tự suy rằng commit chưa xảy ra |
| Transaction abort | Thay đổi thuộc transaction không được commit | Trả lỗi nghiệp vụ hoặc retry đúng loại |

**Timeout không chứng minh transaction chưa commit.** Client có thể mất response sau khi database đã ghi bền kết quả. Retry với ID mới có thể trừ tồn kho hoặc tạo đơn hai lần.

### 11.1. Thứ tự tài nguyên nhất quán

Nếu nhiều transaction cùng cần Stock-A và Stock-B, quy tắc truy cập một thứ tự cố định như `Stock-A → Stock-B` giúp giảm một lớp deadlock do đảo thứ tự khóa. Tuy nhiên, query planner hoặc engine có thể tự chọn thứ tự thực thi, và các loại conflict khác vẫn xảy ra. Phải đo trên tải thật, không xem quy tắc thứ tự là bảo đảm tuyệt đối.

## 12. MVCC và snapshot isolation: không khóa đọc không có nghĩa mọi bất biến an toàn

**MVCC (Multi-Version Concurrency Control)** cho reader thấy version dữ liệu phù hợp theo snapshot/visibility rules, tránh việc mọi reader phải chờ writer như một số mô hình locking. Đánh đổi: duy trì old versions, transaction metadata, conflict checking và cleanup.

Một anomaly cần biết là **write skew**:

~~~text
Invariant: phải có ít nhất một bác sĩ trực.

Ban đầu:
  Doctor A = ON_CALL
  Doctor B = ON_CALL

T1 đọc cả hai, thấy B trực -> đặt A = OFF_CALL
T2 đọc cả hai, thấy A trực -> đặt B = OFF_CALL

Nếu hai giao dịch ghi hai record khác nhau và cùng commit
dưới isolation không ngăn tình huống này:
  Không còn bác sĩ nào ON_CALL.
~~~

Snapshot isolation ở những hệ thống nhất định có thể cho phép dạng anomaly này dù từng ghi không mất dữ liệu. Cần **serializable isolation**, một record có thẩm quyền bảo vệ quota trực, conditional updates hoặc giao thức bảo vệ invariant khác theo engine thực tế.

Không đồng nhất “reader thấy snapshot nhất quán” với “mọi transaction tương đương chạy tuần tự”. Bảo đảm đúng còn phụ thuộc isolation level và các predicate/record được đọc–ghi.

## 13. Lock scope và thời gian chiếm giữ quyết định contention

Một lock quá rộng có thể làm hai cập nhật không liên quan phải chờ nhau:

~~~text
Update Product p100
Update Product p101
~~~

Nếu application tạo một global mutex cho toàn bộ catalog, hai thao tác trên bị tuần tự hóa không cần thiết. Ngược lại, nếu một bất biến trải trên hai ghế cạnh nhau, chỉ khóa từng ghế không có giao thức nhóm có thể khiến khách bị cấp một nửa.

Các câu hỏi thiết kế:

1. Bất biến nằm ở một document, một partition hay nhiều bản ghi?
2. Cần khóa key, document, range/predicate, hay chỉ CAS trên version?
3. Mỗi transaction giữ tài nguyên từ lúc nào tới lúc nào?
4. Có thể chuyển phép kiểm tra điều kiện vào một atomic update không?
5. Một request chậm có làm những request khác chờ cùng resource không?

Mục tiêu là **phạm vi bảo vệ nhỏ nhất vẫn đủ giữ đúng nghiệp vụ**, không phải khóa nhỏ nhất bằng mọi giá.

## 14. Đừng gọi API chậm trong lúc giữ transaction database

Anti-pattern:

~~~text
BEGIN TRANSACTION
  Update Stock
  Call external payment provider over HTTPS
  Call delivery API
  Insert Order
COMMIT
~~~

Payment có thể mất nhiều giây, chậm hoặc không trả response. Trong lúc đó transaction có thể giữ snapshot, connection, trạng thái commit hoặc locks theo engine. Callback transaction có thể được retry và gọi payment trùng; payment đã thu tiền nhưng DB abort cũng không tự động rollback bên provider.

Workflow tốt hơn:

~~~text
1. Transaction DB ngắn:
   giữ Stock + tạo Reservation/Order PENDING
2. COMMIT, giải phóng DB resources
3. Authorize payment với paymentAttemptId ổn định
4. Transaction DB ngắn:
   confirm theo điều kiện và ghi outbox
5. Gửi fulfillment/email từ outbox consumer
6. Void/refund/reconcile nếu kết quả hai bên không khớp
~~~

**Không có một ACID transaction tự nhiên xuyên DB và payment provider.** Thời gian chờ mạng phải nằm ngoài transaction database trừ khi có lý do và giao thức đặc biệt đã được kiểm chứng.

### 14.1. Deadline ở nhiều tầng

Nếu HTTP timeout 3 giây, DB transaction timeout 30 giây và payment provider timeout 60 giây, client có thể bỏ request trong khi công việc tiếp tục chiếm tài nguyên. Cần **deadline propagation, cancellation và cleanup**, song không được giả định hủy HTTP request chắc chắn hủy một commit đã diễn ra.

Trạng thái commit không rõ phải được đối soát bằng business ID hoặc đưa vào trạng thái `PENDING_RECONCILIATION`.

## 15. MongoDB: transaction nhiều document

MongoDB hỗ trợ multi-document transactions trên các topology được hỗ trợ. Mục tiêu: giảm hai pool stock và tạo Reservation cùng commit hoặc abort.

Ví dụ Node.js MongoDB driver (mô hình minh họa; không phải service production hoàn chỉnh):

~~~javascript
async function holdOrder(client, db, command) {
  const { reservationId, orderId, lines } = command;

  if (!reservationId || !orderId || !Array.isArray(lines) ||
      lines.length === 0) {
    throw new Error("INVALID_COMMAND");
  }

  // Thực tế cần normalize các dòng trùng SKU và xác thực tenant.
  const ordered = [...lines].sort(
    (a, b) => a.poolId.localeCompare(b.poolId)
  );

  const session = client.startSession();
  try {
    return await session.withTransaction(async () => {
      const existing = await db.collection("reservations").findOne(
        { _id: reservationId }, { session }
      );
      if (existing) {
        // Phải so cả payload/tenant, không chỉ orderId.
        if (existing.orderId !== orderId) {
          throw new Error("IDEMPOTENCY_CONFLICT");
        }
        return existing;
      }

      for (const line of ordered) {
        if (!Number.isSafeInteger(line.quantity) ||
            line.quantity <= 0) {
          throw new Error("INVALID_QUANTITY");
        }

        const r = await db.collection("stockPools").updateOne(
          {
            _id: line.poolId,
            available: { $gte: line.quantity }
          },
          {
            $inc: {
              available: -line.quantity,
              held: line.quantity
            }
          },
          { session }
        );
        if (r.matchedCount !== 1) {
          throw new Error("INSUFFICIENT_STOCK");
        }
      }

      const r = await db.collection("orders").updateOne(
        { _id: orderId, status: "PENDING_HOLD" },
        { $set: { status: "HELD" } },
        { session }
      );
      if (r.matchedCount !== 1) {
        throw new Error("INVALID_ORDER_STATE");
      }

      const reservation = {
        _id: reservationId,
        orderId,
        lines: ordered,
        status: "HELD",
        createdAt: new Date()
      };
      await db.collection("reservations").insertOne(
        reservation, { session }
      );

      return reservation;
    }, {
      readConcern: { level: "snapshot" },
      writeConcern: { w: "majority" }
    });
  } finally {
    await session.endSession();
  }
}
~~~

**Giới hạn của ví dụ:** còn cần kiểm tra tenant ownership, payload đầy đủ của idempotency key, expiresAt, quy tắc unique, max transaction lifetime, timeout/retry, write conflict, topology và cách xử lý `UnknownTransactionCommitResult` theo driver. Không gọi payment provider/email trong callback.

Trong MongoDB, cross-shard transaction có thể chịu coordination và network overhead đáng kể hơn các cập nhật một document; không suy rằng mọi transaction đụng ít document sẽ nhanh như một `updateOne`.

### 15.1. Callback transaction và side effect

Helper transaction có thể retry callback khi có transient error. Business ID phải ổn định ở ngoài callback. Không tạo PaymentAttempt ngẫu nhiên hoặc gửi email trong callback, vì callback chạy lại không có nghĩa side effect bên ngoài được rollback.

Nếu commit đã thành công nhưng client timeout, retry cùng business key cần đọc trạng thái hiện hữu và trả kết quả, thay vì tạo Reservation mới.

## 16. DynamoDB: conditional write và transaction items

Conditional update theo một item:

~~~text
UpdateItem(
  Key = { PK:"STOCK#SKU-A", SK:"WAREHOUSE#HN" },
  ConditionExpression = "available >= :q",
  UpdateExpression = "SET available = available - :q"
)
~~~

Đây là **pseudocode**, không phải payload SDK hoàn chỉnh. Điều kiện cùng lệnh ghi giúp ngăn trừ quá số lượng của item.

Để thay nhiều items trong phạm vi DynamoDB hỗ trợ, có thể dùng **TransactWriteItems**. Cần kiểm tra giới hạn về số item, kích thước, điều kiện, transaction conflicts, idempotency token, region/table scope và throughput theo tài liệu phiên bản dịch vụ hiện hành.

| Lựa chọn | Phạm vi | Đánh đổi |
|---|---|---|
| Conditional write một item | Một nguồn bất biến | Không tự ghi Order ở item khác |
| Transactional write nhiều items | Bất biến xuyên items trong phạm vi hỗ trợ | Coordination/conflict/latency |
| Saga nhiều hệ hoặc vùng | Từng bước có transaction nhỏ | Trạng thái trung gian và compensation |

Một GSI/read eventual consistency không nên làm nguồn quyết định cuối cùng để cấp quota; điều kiện phải được kiểm tra ở nguồn có thẩm quyền.

## 17. Cassandra/ScyllaDB: LWT có chi phí và phạm vi riêng

Một conditional CQL update:

~~~sql
UPDATE quota_by_event
SET available = 9
WHERE event_id = 'E42'
IF available = 10;
~~~

Nó minh họa compare-and-set trên một giá trị kỳ vọng. Kết quả có trạng thái applied/not-applied theo CQL; khi không khớp, ứng dụng có thể phải đọc lại và quyết định retry. Đây không phải phép trừ chung áp được cho mọi collection/row.

Trong các hệ hỗ trợ, **Lightweight Transactions (LWT)** thường có thêm chi phí serial coordination/consensus theo triển khai. Không nên đánh đồng LWT với transaction tùy ý trên nhiều partition/table. CQL batch cũng có semantics/giới hạn riêng, không phải lối tắt tạo ACID workflow như relational transaction.

Nếu mọi request cùng sửa một partition quota nóng, contention có thể lớn dù dữ liệu tổng được trải trên nhiều node. Hãy đo error rate, p95/p99, LWT latency và load trước khi chọn thiết kế.

## 18. Redis: nguyên tử trong server khác bền vững toàn hệ

Redis có các lệnh atomic và khả năng script để làm check-and-update trong một thao tác server:

~~~lua
local q = tonumber(ARGV[1])
if not q or q <= 0 or q % 1 ~= 0 then
  return redis.error_reply("INVALID_QUANTITY")
end

local available = tonumber(redis.call("HGET", KEYS[1], "available"))
if not available then
  return redis.error_reply("POOL_NOT_FOUND")
end
if available < q then
  return 0
end

redis.call("HINCRBY", KEYS[1], "available", -q)
redis.call("HINCRBY", KEYS[1], "held", q)
return 1
~~~

Script bảo vệ counter trên một key trong phạm vi thực thi server, nhưng chưa tạo Reservation bền vững hoặc đảm bảo không bị trừ hai lần khi client retry. Redis Cluster có giới hạn hash slot cho các thao tác nhiều key.

`MULTI/EXEC` và `WATCH` có thể hỗ trợ nhóm lệnh và optimistic checks, nhưng không mặc nhiên mang cùng rollback, isolation, multi-node scope và durability như database relational. Cần kiểm tra AOF/RDB, fsync policy, replication và failover nếu Redis là nguồn transaction quan trọng.

## 19. Timeout sau commit: kết quả không rõ

~~~text
Client                          DB
POST /reservations -----------> BEGIN, WRITE, COMMIT
                       X <---- response mất
Client timeout
~~~

Có thể transaction **đã commit** hoặc **chưa commit**. Cần:

1. Sinh ID ý định nghiệp vụ ổn định trước khi gọi.
2. Lưu trạng thái/kết quả gắn với ID trong ranh giới nhất quán thích hợp.
3. Retry cùng ID, cùng payload.
4. Khi gặp duplicate, kiểm tra payload và trả kết quả hiện hữu.
5. Khi vẫn không xác định được kết quả, để trạng thái `UNKNOWN/PENDING` và đối soát.
6. Không tạo ý định mới chỉ vì response lần đầu bị mất.

Idempotency không đồng nghĩa “retry mọi lệnh bao nhiêu lần cũng được”. Một decrement trực tiếp trên counter có thể vẫn giảm nhiều lần nếu không lưu dấu vết ý định.

## 20. Retry budget, jitter và phân loại lỗi

~~~text
for attempt in 1..maxAttempts:
    try:
        executeTransactionWithStableBusinessId()
        return result
    catch transientConflict:
        backoffWithJitter()
    catch unknownCommitResult:
        checkResultByBusinessIdOrDriverCommitProtocol()
    catch businessRejection:
        return failure
return RETRY_BUDGET_EXCEEDED
~~~

Đây là pseudocode chính sách, không thay thế retry protocol của driver cụ thể. Cần phân biệt:

- Transient conflict/abort: có thể retry theo contract nếu code không sinh side effect trùng.
- Unknown commit: cần xác định outcome, không mặc nhiên replay một payment.
- Business rejection (hết hàng, status không hợp lệ): retry vô hạn không giúp.
- Authentication/validation failure: không nên retry khi input chưa thay.
- Network outage: retry cần deadline và circuit breaker/admission control phù hợp.

**Exponential backoff với jitter**, retry budget và giới hạn song song giúp tránh retry storm. Đặt deadline cho cả request, không cấp cho mỗi lần retry một thời gian vô hạn.

## 21. Distributed lock, lease và fencing token

Nếu ứng dụng tự tạo một lock phân tán có TTL:

~~~text
Worker A lấy lock "reconcile:order42" với lease 10 giây.
A bị treo 15 giây.
Lease hết hạn, Worker B lấy lock và xử lý.
A tỉnh lại và tiếp tục ghi nguồn dữ liệu.
~~~

Một lease hết hạn không tự ngăn Worker A ghi sau đó. **Distributed lock không đủ bảo vệ bất biến** nếu nguồn nhận ghi không nhận biết quyền sở hữu đã lỗi thời.

Một giao thức có thể dùng **fencing token** tăng đơn điệu:

~~~text
A lấy token 101
B lấy token 102

Nguồn từ chối các write có token thấp hơn token
đã được chấp nhận theo giao thức có thẩm quyền.
~~~

Token cần được cấp và so sánh bằng cơ chế bền/atomic thích hợp. Không tự dùng clock timestamp làm token rồi cho rằng nó tăng đơn điệu giữa các node.

Nếu bài toán chỉ là giảm counter không âm trong một DB, conditional update tại nguồn thường rõ và ít rủi ro hơn một distributed lock bên ngoài cộng thao tác read–set.

## 22. Saga: giao dịch ngắn đổi lấy trạng thái trung gian

Khi Order và Payment thuộc những hệ không thể có transaction ACID chung, **Saga** điều phối nhiều bước nhỏ với compensation:

~~~mermaid
flowchart TD
    A["Order PENDING_HOLD"] --> B["Hold SKU-A"]
    B --> C{"A held?"}
    C -->|Không| X["HOLD_FAILED"]
    C -->|Có| D["Hold SKU-B"]
    D --> E{"B held?"}
    E -->|Không| F["Release SKU-A"]
    F --> X
    E -->|Có| G["Order HELD"]
~~~

Saga không phải atomic all-or-nothing tức thời: giữa Hold-A và Hold-B, một phần stock có thể đang giữ. Mỗi bước và compensation cần idempotency, trạng thái đủ bền và khả năng retry/đối soát.

Lợi ích: không giữ database transaction trong lúc chờ payment provider/remote service; mỗi transaction cục bộ có thể ngắn. Giá phải trả: nhiều trạng thái, sự kiện trùng/sai thứ tự, timeout, compensation failures và yêu cầu reconciliation.

## 23. Outbox, inbox và reconciliation không làm transaction dài thêm vô ích

Một lệnh Order commit thành công, rồi service crash trước khi gửi event cho Inventory/Search/Email. Nếu không có cơ chế phục hồi, hệ có thể ở trạng thái DB đúng nhưng projection/consumer không biết thay đổi.

**Transactional outbox** ghi event cùng transaction DB:

~~~text
BEGIN LOCAL TRANSACTION
  Update Order -> CONFIRMED
  Insert OutboxEvent(evt-1001, OrderConfirmed, PENDING)
COMMIT

Outbox publisher đọc event và gửi qua broker.
Consumer xử lý idempotent theo eventId.
~~~

Với các engine hỗ trợ giao dịch nhiều document, Order và Outbox cần nằm trong phạm vi atomic thích hợp. Nếu không có multi-document atomicity, cần mô hình sự kiện nhúng/transaction log hoặc thiết kế khác có recovery cụ thể.

Outbox không bảo đảm message chỉ được gửi một lần. Publisher có thể gửi thành công rồi crash trước khi đánh dấu `SENT`; lúc restart, nó phát lại. **Inbox/deduplication** ở consumer giúp một `eventId` không gây side effect lần hai.

Reconciliation định kỳ phát hiện:

- Reservation `HELD` quá hạn nhưng quota chưa được release.
- Order `CONFIRMED` chưa có event tương ứng ở projection.
- Payment đã authorized/captured nhưng Order còn `PENDING_PAYMENT`.
- Một compensation được yêu cầu nhưng chưa hoàn thành.
- Transaction/intent mắc kẹt quá deadline.

Một công việc reconciliation có thể được thực hiện ngoài đường request chính, tránh giữ transaction database lâu chỉ để chờ tất cả projection đồng bộ.

## 24. Escrow quota và giảm contention trên hot key

Nếu mọi request tranh `available=1000` trên một document duy nhất, throughput có thể bị giới hạn bởi contention. Một hướng mở rộng là **phân bổ trước quyền cấp phát (escrow quota)**.

Ví dụ:

~~~text
Global capacity = 1000

Owner VN: 600 quyền giữ
Owner SG: 300 quyền giữ
Unallocated: 100 quyền

Tổng quyền được cấp + chưa cấp luôn = 1000
~~~

Mỗi owner chỉ giữ trong lượng quyền đã được cấp, giảm phối hợp cho từng request. Nhưng cần một giao thức chuyển quota an toàn:

1. Owner A không được tiếp tục cấp phần quota đã chuyển.
2. Owner B không được cấp quota trước khi transfer được xác nhận theo một nguồn có thẩm quyền.
3. Một transferId chỉ được áp dụng một lần dù retry.
4. Nếu transfer timeout, phải tra lại kết quả thay vì chuyển thêm lần nữa.
5. Tổng quyền bán trên mọi owner không được vượt global capacity.

Escrow **đổi phối hợp theo từng đơn hàng thành phối hợp theo từng đợt tái phân bổ**, không xóa hoàn toàn bài toán consistency. Một region có thể tạm hết quota dù region khác còn; phải chấp nhận trade-off về hiệu suất và độ linh hoạt.

## 25. Giới hạn số tài nguyên tham gia một giao dịch

Một transaction chạm ít document nhưng ở nhiều shard/region có thể đắt hơn một transaction chạm nhiều document cục bộ; ngược lại, quá nhiều document cùng một shard vẫn có thể tạo write set lớn. Không có chỉ số đơn giản “dưới N document luôn rẻ”.

Những biến số cần tính:

| Biến số | Tại sao quan trọng |
|---|---|
| Số participants/shards | Tăng coordination và xác suất gặp participant chậm |
| Số đọc/ghi mỗi participant | Tăng validation, index update, log |
| Số hot keys | Tăng wait, conflict và retry |
| Phạm vi địa lý | Cross-region RTT và failure modes |
| Transaction lifetime | Giữ state/snapshot/locks lâu hơn |
| Kích thước document/item | Network, memory, log và serialization |
| Isolation/write concern | Mức đồng bộ cần đạt và chi phí |
| Index count | Tăng write amplification |
| Retry rate | Tăng lưu lượng thực so với traffic nghiệp vụ |
| Background operations | Compaction, index builds, failover, resharding |

Một số cách giảm phạm vi:

- Xác định aggregate root phù hợp để bất biến quan trọng được bảo vệ trong một đơn vị nhỏ.
- Dùng conditional update khi chỉ cần một counter/record.
- Colocate dữ liệu **khi access pattern thực sự yêu cầu** và shard key cho phép, không tạo partition nóng khổng lồ.
- Tách side effects sau commit qua outbox.
- Tránh đưa batch migration/reporting vào transaction phục vụ người dùng.
- Chia một workflow dài thành state transitions ngắn khi nghiệp vụ cho phép trạng thái trung gian.
- Giới hạn số dòng Order trong transaction và xử lý trường hợp quá giới hạn theo chính sách rõ ràng.

**Không xé nhỏ một invariant cần atomicity chỉ để có nhiều transaction ngắn.** Nếu bước A và B bắt buộc đồng thời, phải có giao thức khác bảo vệ đúng hợp đồng thay vì đơn giản tách API rồi hy vọng không lỗi.

## 26. Chọn transaction deadline và timeout hợp lý

Một giao dịch nên có **time budget** được quyết định theo SLO nghiệp vụ và khả năng của engine. Không nên đặt một giá trị cực lớn để “chắc chắn không timeout”; điều này có thể giữ resource quá lâu trong các sự cố mạng/node.

Ví dụ một request có deadline 2 giây:

~~~text
Request deadline              2000 ms
  Authentication + routing     100 ms
  DB transaction budget        600 ms
  Application processing       150 ms
  Network/response             150 ms
  Buffer/uncertainty          1000 ms
~~~

Đây là **phân bổ minh họa**, không phải giá trị khuyến nghị dùng được cho mọi hệ. Nếu một transaction thường cần 1,5 giây ở p99, cần phân tích nguyên nhân (conflict, network, data model) thay vì chỉ nâng timeout lên 60 giây.

### 26.1. Cancellation và cleanup

Khi client ngắt kết nối:

- Session/transaction chưa commit cần được abort/cleanup theo contract driver.
- Không để connection/transaction state nằm treo vô hạn.
- Nếu commit outcome chưa rõ, phải dùng business ID xác minh, không mặc định abort.
- Worker background phải có lease/ownership hoặc checkpoint thích hợp.
- Các resource được giữ bởi coordinator/participants cần có cơ chế phục hồi khi process chết.

Thời gian **HTTP request duration** và **database transaction lifetime** nên được đo riêng. Cần theo dõi max/oldest transaction age và số transaction đang chờ conflict/lock.

## 27. Chống quá tải: admission control, bounded concurrency và backpressure

Khi traffic tăng đột biến, cho tất cả request chạy transaction đồng thời không phải lúc nào cũng tăng throughput. Nó có thể làm queue, lock wait và conflicts tăng nhanh hơn công suất xử lý.

Một thiết kế bảo vệ tải:

~~~mermaid
flowchart TD
    A["Incoming requests"] --> B["Rate limit / admission"]
    B --> C{"Còn capacity?"}
    C -->|Không| D["Reject / retry-after"]
    C -->|Có| E["Bounded concurrency queue"]
    E --> F["Short DB transaction"]
    F --> G{"Success?"}
    G -->|Có| H["Return result"]
    G -->|Conflict| I["Bounded backoff + retry"]
    I --> E
    G -->|Business fail| J["Return business rejection"]
~~~

Các kỹ thuật:

- **Admission control/waiting room:** giới hạn số request tranh cùng pool.
- **Bounded queue:** không nhận vô hạn request vào RAM.
- **Per-key concurrency control:** tránh cùng lúc tạo quá nhiều transaction xung đột trên một hot key.
- **Circuit breaker/backpressure:** giảm tải tới dependency đang lỗi.
- **Timeout budget:** không giữ request nằm chờ vô hạn.
- **Backoff và jitter:** tránh toàn bộ client retry theo cùng nhịp.
- **Load shedding:** từ chối có kiểm soát tốt hơn để timeout tất cả.

Khi từ chối request, API cần hợp đồng rõ: retry có an toàn không, có giữ business key không, thời gian nào được retry và kết quả chưa rõ có cần đối soát không. Không lấy `429`/`503` làm bằng chứng transaction trước đó chắc chắn chưa commit.

## 28. Đo chi phí giao dịch bằng những metric nào?

Một dashboard chỉ có transaction throughput và average latency thường không đủ. Cần ít nhất:

| Nhóm | Chỉ số |
|---|---|
| Độ trễ | p50, p95, p99 transaction end-to-end và riêng DB |
| Lifecycle | In-flight transactions, active/oldest age, timeout/abort |
| Coordination | Participants per transaction, cross-shard calls, network RTT |
| Contention | Lock wait duration, conflicts, deadlocks, abort rate |
| Retry | Attempts per business intent, backoff, retry success/exhaustion |
| Durability | Commit latency, log sync/quorum wait, replica lag |
| Tài nguyên | Connections, session state, memory, write set size, disk I/O |
| Hot keys | Key/partition contention, queue wait, throughput per pool |
| Workflow | Saga PENDING age, compensation lag, stuck reservations |
| Side effects | Payment reconciliation, outbox/inbox duplicate and lag |

**Transaction abort rate** cần chia loại: business rule bị từ chối (hết hàng) khác technical abort do write conflict hoặc timeout. Không gom mọi request thất bại thành “database failure”.

Với tracing:

~~~text
Trace reservationId = res-1001
  API auth              8 ms
  DB transaction begin  2 ms
  Read/validate        10 ms
  Wait/conflict         0 ms
  Write participants   25 ms
  Commit/quorum        18 ms
  API response          5 ms
~~~

Số liệu hoàn toàn minh họa. Mỗi span nên có correlation ID/transaction ID ở mức an toàn, không log secrets hoặc thông tin cá nhân không cần thiết. Cần tách wall-clock time và thời gian server thực xử lý; các span có thể chồng lấp.

### 28.1. Nhìn p99 chứ không chỉ trung bình

Giả sử:

~~~text
99% transactions: 30 ms
 1% transactions: 2,000 ms
~~~

Average có thể vẫn trông khá nhỏ, trong khi 1% người dùng chịu timeout hoặc rất chậm. Tail latency có thể bị chi phối bởi hot partition, lock wait, abort/retry hoặc straggler shard. Đo p95/p99 dưới tải và khi có failover/compaction mới cho thông tin hữu ích.

## 29. Thực nghiệm 1: local atomic update so với cross-shard transaction

**Giả định:** một môi trường thử có database hỗ trợ multi-document transactions; dữ liệu trải trên một hoặc nhiều partition/shard tùy bài thử.

Thiết kế ba phương án:

| Phương án | Thao tác | Bất biến kiểm tra |
|---|---|---|
| A | Conditional update một Stock document | Stock không âm |
| B | Transaction cập nhật 2 Stock + 1 Order | Hoặc đủ hai SKU hoặc Order không HELD |
| C | Saga hai hold nhỏ + compensation | Không báo HELD khi mới giữ một phần; release đúng một lần |

Các bước:

1. Chuẩn bị dữ liệu và keys/partitions sao cho biết chính xác dữ liệu nằm ở đâu.
2. Chạy sequential baseline rồi tăng concurrency theo các bậc.
3. Đo offered load, achieved throughput, p50/p95/p99, conflict/abort.
4. Chạy cùng tải với participant cục bộ và participant ở nhiều shard/region nếu topology cho phép.
5. Bật tình huống một shard chậm, đo ảnh hưởng tới transaction tail latency.
6. Đo DB transaction lifetime và lock wait riêng; đừng suy lock hold time từ HTTP latency.
7. Đảm bảo các kết quả **đã commit** giữ bất biến; không chỉ đếm HTTP 200.
8. Ghi lại version, topology, replication/write concern, index, concurrency, dữ liệu, seed.

Không kết luận “2PC luôn chậm X lần” từ một phép thử, vì đặc tính engine và workload có thể thay đổi kết quả.

## 30. Thực nghiệm 2: hot key và thời gian giữ resource

Tạo một pool sức chứa 10, gửi đồng thời 100 request giữ 1 suất. Mỗi request có business ID riêng.

~~~text
For i in 1..100 concurrently:
    Reserve(pool="event-42", quantity=1, intentId="req-" + i)

After all settled:
    Read authoritative state
    Assert available >= 0
    Assert held + confirmed <= 10
    Assert each intent applied at most once
~~~

Tiếp tục thử:

- Chạy một transaction chỉ có thao tác database cần thiết.
- Chạy phiên bản cố ý sleep 100 ms trong transaction (chỉ trong lab).
- Chạy cùng phiên bản với 500 ms; đo conflict/lock wait/p99.
- Giới hạn in-flight transactions từ 100 xuống 10 rồi xuống 5.
- So throughput và latency, đồng thời đếm request bị từ chối/timeout.

Nếu một engine không giữ write lock suốt thời gian sleep, tác động có thể xuất hiện ở snapshot retention, transaction age, write conflict hoặc resource khác; **không được gán mọi chậm trễ cho lock** khi chưa có metric chứng minh.

Một hệ có thể từ chối nhiều request vì hết stock; điều này là business rejection đúng, khác với technical failure. Không ép đúng 10 HTTP responses thành công khi hệ có timeout/admission policy, nhưng **không được quá 10**.

## 31. Thực nghiệm 3: fault injection khi commit và retry

Các tình huống quan trọng:

| Tình huống | Kiểm tra |
|---|---|
| Client timeout trước khi server bắt đầu | Không tạo side effect |
| Client timeout khi DB đang chạy | Có thể abort hoặc commit; xác minh bằng ID |
| Commit thành công, response mất | Retry cùng ID không nhân đôi |
| Coordinator/crash giữa prepare/commit | Recovery đưa participants về trạng thái hợp lệ theo protocol |
| Một participant chậm bất thường | Giới hạn wait, p99 và cleanup |
| Hai transaction tranh Stock-A/Stock-B đảo thứ tự | Deadlock/conflict được xử lý có giới hạn |
| Worker hold SKU-A rồi chết trước SKU-B trong Saga | Compensation/recovery được retry |
| Outbox publish thành công nhưng ACK publisher mất | Event gửi trùng không tạo side effect trùng |
| Payment authorized nhưng Order chưa confirm | Đối soát, void/refund theo quy tắc |
| Lease worker cũ hết hạn nhưng worker còn chạy | Fencing ngăn stale write |

Không thực hiện crash/failover trên production để “thử may mắn”. Hãy dựng môi trường thử, có khả năng quan sát transaction outcome và dữ liệu cuối cùng, rồi kiểm tra bất biến từ nguồn có thẩm quyền.

## 32. Bảng lựa chọn: giao dịch hay workflow?

| Nhu cầu | Lựa chọn để bắt đầu đánh giá | Lý do |
|---|---|---|
| Giảm một counter không âm | Atomic conditional update | Một nguồn bất biến, ít coordination |
| Cập nhật nhiều field trong một document | Atomic document update | Giữ ranh giới hẹp |
| Order + Reservation trong cùng engine | Transaction đa document nếu phù hợp | Bảo vệ bất biến commit cùng nhau |
| Nhiều shard cùng engine | Distributed transaction theo contract | Đảm bảo atomicity, trả chi phí coordination |
| DB và payment provider | State machine + provider idempotency + reconciliation | Không có chung ACID transaction |
| Nhiều kho/region không hỗ trợ transaction chung | Saga/escrow theo nghiệp vụ | Phân bổ quyền, xử lý trạng thái trung gian |
| Một background job độc quyền | Lease + fencing hoặc CAS | Ngăn worker stale tiếp tục ghi |
| Search/cache sau Order commit | Outbox/CDC + idempotent projection | Không kéo dài DB transaction |
| Batch migration hàng triệu record | Chunk + checkpoint/retry + đối soát | Tránh transaction quá lớn/lâu |

Lựa chọn phụ thuộc **mức bất biến**, không phụ thuộc sở thích “NoSQL phải eventual consistency” hoặc “mọi thứ bắt buộc transaction ACID”. Transaction rộng có thể đúng nhưng đắt; Saga có thể rẻ hơn đường ghi chính nhưng đòi hỏi thiết kế recovery tốt.

## 33. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách làm đúng |
|---|---|---|
| Transaction nhiều document nhanh như update một key | Có thể thêm coordination, locks và log | Đo theo participant và topology |
| Có transaction là serializable mọi nơi | Isolation khác nhau | Xác định isolation contract và invariant |
| MVCC không dùng locks nên không giữ tài nguyên | Snapshot/version retention vẫn tốn | Đo transaction age và cleanup |
| Client timeout nghĩa rollback | Commit có thể thành công nhưng ACK mất | Idempotency ID + xác minh outcome |
| Retry vô hạn làm tăng thành công | Tạo retry storm/queue | Backoff, jitter, retry budget |
| Distributed lock TTL đủ ngăn race | Worker cũ có thể ghi sau hết lease | Fencing hoặc atomic condition tại nguồn |
| 2PC tự giải quyết mọi lỗi coordinator | Prepared participants có thể chờ recovery | Durable decision/recovery protocol |
| Consensus giống 2PC | Khác bài toán và phạm vi | Phân biệt replication/quorum và atomic commit |
| Cùng shard là không tranh chấp | Hot record/partition vẫn gây contention | Đo hot keys và conflict |
| Cross-region transaction chỉ thêm một RPC | RTT, commit, quorum và tail latency | Đo end-to-end trong topology |
| Cứ kéo dài transaction timeout để hết lỗi | Giữ tài nguyên lâu, p99 xấu hơn | Tìm nguyên nhân, giới hạn lifetime |
| Gọi payment trong transaction thì an toàn | Payment không rollback cùng DB | State machine, idempotent provider calls |
| Saga có all-or-nothing tức thì | Có trạng thái trung gian | Compensation/reconciliation |
| Outbox bảo đảm publish đúng một lần | Publisher có thể phát lại | Consumer idempotent/inbox |
| Lock càng rộng càng dễ đúng mà không có giá | Giảm concurrency | Bảo vệ ranh giới nhỏ nhất đủ đúng |
| Benchmark chỉ đo TPS thành công | Che khuất timeout, abort và tail | Đo offered load, reject, p99 và invariant |

## 34. Bài tập thiết kế

**Bối cảnh:** nền tảng bán 1.000 vé cho một sự kiện. Khách có thể mua 1–4 vé; giữ 5 phút rồi thanh toán. Giao diện chạy ở hai region. Một số vé có mã ghế riêng; payment provider là hệ ngoài.

### Phần A — Bất biến và boundary

1. Viết công thức bảo toàn capacity, available, held và confirmed.
2. Phân biệt quota tổng với uniqueness từng ghế đánh số.
3. Xác định giao dịch nào chỉ cần một document/key và giao dịch nào cần nhiều đơn vị.
4. Một Order mua cả vé thường lẫn VIP thì bất biến all-or-nothing nằm ở đâu?
5. Có thể dùng escrow quota cho hai region không? Nêu điều kiện chuyển quota an toàn.

### Phần B — Transaction cost

1. Vẽ prepare/commit cho hai kho hoặc hai shard.
2. Tách network, validation, log, lock wait và commit trong latency budget.
3. Với throughput 200/s và lifetime 50 ms, áp dụng Little's Law tính in-flight trung bình.
4. Nếu lifetime tăng lên 250 ms, in-flight thay đổi như thế nào dưới giả định throughput không đổi?
5. Nêu khi nào Little's Law **không thể** được diễn giải là số khóa đang giữ.

### Phần C — Failure và isolation

1. Tạo ví dụ deadlock A→B, B→A và đề xuất cách giảm nguy cơ.
2. Tạo ví dụ write skew mà hai transaction sửa hai document khác nhau.
3. Khi client timeout sau commit, hệ xác minh kết quả bằng business ID ra sao?
4. Vì sao lease có TTL không đủ ngăn worker stale? Thiết kế fencing token.
5. Gọi payment API trong callback transaction MongoDB có rủi ro gì?

### Phần D — Vận hành

1. So sánh p95/p99 của conditional update và multi-document transaction.
2. Thử contention trên một hot key và giới hạn concurrency.
3. Đo abort, lock wait, retries và số transaction giữ snapshot lâu.
4. Giả lập một participant chậm hoặc commit outcome không rõ.
5. Viết runbook cho Reservation HELD quá hạn, payment đã capture nhưng Order chưa confirm.

## 35. Câu hỏi tự kiểm tra

1. Một atomic update trên key có giải quyết all-or-nothing của Order hai SKU không?
2. 2PC thêm những chi phí và loại trạng thái chờ nào?
3. Vì sao 2PC khác consensus/quorum replication?
4. Transaction chạm nhiều shard có thể bị participant chậm nhất chi phối như thế nào?
5. Transaction lifetime và lock hold time có phải luôn bằng nhau không?
6. MVCC có thể khiến old versions được giữ lâu vì sao?
7. Snapshot isolation có bảo vệ mọi bất biến xuyên nhiều document không?
8. Hot key gây contention dù đã shard dữ liệu toàn hệ thế nào?
9. Điều kiện áp dụng Little's Law trong một phép đo transaction là gì?
10. Timeout, deadlock và write conflict khác nhau thế nào?
11. Vì sao không nên gọi provider ngoài trong DB transaction?
12. Retryable transaction callback có thể làm trùng những side effects nào?
13. Conditional update và business idempotency giải quyết hai vấn đề khác nhau ra sao?
14. DynamoDB transactional writes có cùng giới hạn với MongoDB transactions không?
15. LWT Cassandra có thay thế được mọi giao dịch cross-partition không?
16. Redis script atomic đã đủ bảo đảm durable commit toàn hệ chưa?
17. Tại sao distributed lock với lease cần fencing?
18. Saga giảm tài nguyên giữ lâu nhưng tăng chi phí gì?
19. Outbox có cần consumer deduplication không?
20. Nếu giao dịch chậm, nên quan sát lock wait, network, commit hay retry theo thứ tự nào?
21. Khi nào escrow quota giảm hot-key contention?
22. Vì sao chỉ nâng transaction timeout có thể làm p99 tệ hơn?
23. Làm sao xác nhận kết quả transaction đã commit khi response bị mất?
24. Tại sao benchmark phải đo business rejections và technical aborts riêng?
25. Một quyết định chọn transaction rộng hay Saga nên bắt đầu từ yếu tố nào?

## 36. Tổng kết

**Giao dịch phân tán có chi phí vì nhiều đơn vị dữ liệu phải cùng thống nhất một kết quả**, trong khi mỗi bên có network latency, durability, state và khả năng lỗi riêng. Chi phí chính gồm coordination round trips, validation, transaction logging, contention/locks, snapshot retention, abort/retry và recovery. Số participant lớn và một hot key có thể đẩy p95/p99 lên nhanh dù các câu lệnh đơn lẻ đều ngắn.

Để giữ hệ thống đúng mà vẫn chịu tải, hãy bắt đầu bằng **bất biến và phạm vi nguyên tử nhỏ nhất đủ bảo vệ nó**. Dùng conditional update khi một nguồn dữ liệu là đủ; dùng transaction đa document/shard khi thật sự cần commit cùng nhau; dùng Saga, escrow quota, outbox, idempotency và reconciliation cho những workflow không có transaction chung. Luôn phân biệt transaction lifetime với lock hold time, tránh chờ payment hoặc RPC dài trong transaction, đặt deadline/retry budget và quan sát hot keys, lock wait, abort rate, transaction age, p99.

Một thiết kế tốt không phải thiết kế “không có khóa”, mà là thiết kế **biết khóa hoặc conflict xuất hiện ở đâu, giữ tài nguyên bao lâu, ai có thẩm quyền quyết định commit và hệ sẽ phục hồi thế nào khi kết quả không rõ ràng**.





