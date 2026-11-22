# Thử nghiệm mất gói, ngắt kết nối và nút phản hồi chậm

Một hệ thống NoSQL phân tán có thể hoạt động ổn định khi tất cả node khỏe mạnh, nhưng bắt đầu bộc lộ lỗi khi một gói tin bị mất, kết nối đứt giữa chừng hoặc một replica phản hồi chậm hơn những replica còn lại. Ở thời điểm đó, ứng dụng thường chỉ quan sát được **timeout**, **connection reset**, **unavailable** hoặc **kết quả không rõ ràng**; những thông báo này không cho biết chắc thao tác đã được commit hay chưa.

Ví dụ, client gửi yêu cầu tạo đơn hàng. Database đã ghi thành công và trừ tồn kho, nhưng gói ACK bị mất. Client thấy timeout rồi retry. Nếu hệ không có idempotency, **một ý định mua hàng có thể bị xử lý hai lần**. Ngược lại, nếu client không retry trong lúc request thực sự bị mất trước khi tới server, nghiệp vụ có thể không hoàn tất dù chỉ là sự cố mạng tạm thời.

Vì vậy, **thử nghiệm lỗi phân tán** (*fault injection*, *chaos testing*) không đơn giản là ngắt Wi-Fi rồi quan sát ứng dụng có chạy không. Ta cần cố ý tạo những kiểu lỗi khác nhau, kiểm tra **safety**, **liveness**, **độ nhất quán**, **hành vi retry** và **khả năng phục hồi**, đồng thời biết chính xác lỗi được tiêm ở đâu và lúc nào.

Bài học thuộc chương **Lỗi phân tán và retry** trong module **Database No SQL**. Nội dung tập trung vào ba nhóm thí nghiệm:

1. **Mất gói (*packet loss*):** một số thông điệp không tới đích hoặc không có phản hồi.
2. **Ngắt kết nối (*disconnection/partition*):** luồng liên lạc bị đóng, reset hoặc trở nên không thể sử dụng.
3. **Nút phản hồi chậm (*slow node*):** node chưa hỏng nhưng trả lời lâu vì mạng, CPU, GC, disk hoặc hàng đợi.

Để làm rõ cách thử, bài viết dùng sơ đồ luồng, ma trận thí nghiệm, lệnh mô phỏng trên **môi trường lab**, mã Java chạy trong một JVM và các bài tập thiết kế. Mỗi ví dụ đều phân biệt điều có thể quan sát với điều **không thể suy ra** chỉ từ timeout.

> **An toàn vận hành:** không áp dụng lệnh chặn mạng, dừng node, tăng packet loss hoặc giới hạn băng thông trên cluster production nếu không có quy trình phê duyệt, giới hạn tác động, giám sát và đường khôi phục ngoài luồng. Các lệnh minh họa trong bài dành cho network namespace/interface/proxy của lab mà bạn kiểm soát.

## 1. Tại sao lỗi mạng khó hơn lỗi trả mã 500?

Trong một chương trình đơn tiến trình, ta có thể gọi hàm và nhận giá trị hoặc exception. Qua mạng, một yêu cầu có nhiều giai đoạn:

~~~text
Client                  Coordinator               Replica
   |                          |                       |
   |---- request ------------>|                       |
   |                          |--- mutation --------->|
   |                          |<-- replica ACK --------|
   |<--- response ------------|                       |
~~~

Nếu client không nhận response, có ít nhất bốn khả năng:

~~~text
A. Request chưa tới coordinator.
B. Coordinator nhận nhưng chưa thực hiện mutation.
C. Mutation đã commit, response chưa được gửi.
D. Mutation đã commit, response được gửi nhưng bị mất.
~~~

Client chỉ quan sát:

~~~text
Timeout / IOException
~~~

thì **không thể kết luận chắc nó thuộc A, B, C hay D**. Đây là vấn đề *ambiguous outcome* hoặc *unknown commit outcome*.

Phân biệt:

- **Failure:** thành phần không thực hiện đúng đặc tả.
- **Fault:** nguyên nhân/điều kiện gây thất bại, như packet drop hoặc disk stall.
- **Error:** trạng thái sai bên trong hệ.
- **Observation:** điều client/monitor thực sự nhìn thấy.

Một fault không nhất thiết gây lỗi nghiệp vụ; nhiều hệ che giấu packet loss bằng retransmission hoặc retry. Nhưng lỗi nghiệp vụ có thể xảy ra **dù network layer cuối cùng khôi phục thành công**, nếu retry bị xử lý hai lần.

## 2. Ba tiêu chí: safety, liveness và performance

Khi tiêm lỗi, cần đo cả ba loại mục tiêu:

| Thuộc tính | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Safety** | Điều bị cấm có bao giờ xảy ra không? | Một ghế không được bán cho hai người |
| **Liveness** | Khi điều kiện thuận lợi quay lại, hệ có tiếp tục tiến lên không? | Sau khi nối mạng, yêu cầu mới cuối cùng hoàn tất |
| **Performance** | SLO độ trễ/tải thay đổi thế nào? | p99 tăng từ 100 ms lên 2 s trong lúc lỗi |

Một hệ có thể **an toàn nhưng không sẵn sàng** khi mất quorum: nó từ chối write thay vì xác nhận sai. Ngược lại, một hệ luôn trả HTTP 200 có thể **không an toàn** nếu hai bên network partition cùng bán một item cuối cùng.

Không dùng tiêu chí:

~~~text
HTTP 200 count high → system passed chaos test
~~~

cho mọi tình huống. Thử nghiệm phải gắn với **invariant của dữ liệu** và **mức consistency đã công bố**.

## 3. Mạng là một đồ thị có hướng

Trong một hệ ba node, hãy coi các luồng liên lạc là cạnh:

~~~text
       Node A
       /    \
      /      \
   Node B --- Node C
~~~

Thực tế đường A→B và B→A có thể không đối xứng:

~~~text
A → B: request tới được
B → A: response bị drop
~~~

Do đó một cuộc thử nghiệm cần ghi rõ:

1. **Nguồn:** client, proxy, coordinator hay replica nào?
2. **Đích:** node/port/service nào?
3. **Chiều:** request, response hay cả hai?
4. **Tầng:** DNS, TCP, TLS, HTTP, RPC, driver/database protocol?
5. **Thời lượng:** vài giây, lâu hơn timeout hay kéo dài qua failover?
6. **Tỉ lệ:** 5% packet loss, 100% drop, delay cố định hay jitter?
7. **Giai đoạn:** trước khi request đến, đang ghi hoặc sau commit trước ACK?

**“Chặn Node B” là mô tả chưa đủ** nếu không nói nó bị chặn từ đâu và theo chiều nào.

## 4. Packet loss là gì?

**Packet loss** là hiện tượng gói dữ liệu không đến đúng nơi được kỳ vọng. Trong TCP, mất packet có thể được **retransmit**, nên ứng dụng đôi khi chỉ thấy request chậm hơn chứ không nhận exception.

~~~text
Client                  Server
   |---- packet 1 -------->|
   |---- packet 2 ----X    |  lost
   |---- packet 3 -------->|
   |                       |
   |---- retransmit 2 ---->|
~~~

Với giao thức/datagram không bảo đảm truyền như UDP, ứng dụng hoặc giao thức tầng trên có thể phải tự xử lý mất gói. HTTP/3 trên QUIC có cơ chế phục hồi riêng, không đồng nhất hoàn toàn với TCP.

### Packet loss không đồng nghĩa request loss

Nếu tiêm:

~~~text
loss = 5% per packet
~~~

thì không được kết luận:

~~~text
5% database requests thất bại
~~~

Một request có thể dùng nhiều packets, bị retransmit, gặp deadline hoặc bị ảnh hưởng congestion control. Tỉ lệ request thất bại phụ thuộc protocol, kích thước payload, thời hạn và pattern mạng.

### Mất gói theo cụm (*burst loss*)

Loss thực tế có thể không độc lập:

~~~text
10 giây gần như không lỗi
2 giây packet drop hàng loạt
10 giây bình thường
~~~

Burst loss gây hiện tượng timeout đồng thời và có thể kích hoạt retry storm. Vì vậy nên thử cả **loss xác suất phân tán** lẫn **loss tương quan kéo dài**.

## 5. Latency, jitter, reorder và duplication

Mạng không chỉ có “được/mất”:

- **Latency:** độ trễ khi packet hoặc request đi qua mạng.
- **Jitter:** độ trễ thay đổi giữa các packet/request.
- **Reordering:** packet tới không đúng thứ tự đã gửi.
- **Duplication:** thông điệp/packet được nhân bản.
- **Bandwidth limit:** đường truyền bị giới hạn tốc độ.
- **Corruption:** payload bị lỗi, tầng dưới hoặc giao thức có thể phát hiện và drop.

Thí nghiệm:

~~~text
Baseline RTT:   2 ms
Injected delay: 200 ms + jitter 100 ms
Client timeout: 150 ms
~~~

Ngay cả khi **không mất packet nào**, request có thể timeout vì deadline quá ngắn.

### Không đánh đồng delay một chiều với RTT

Nếu một proxy thêm 100 ms **chỉ ở chiều request**, RTT tăng khác trường hợp thêm 100 ms ở **cả request và response**. Khi đo, phải nói rõ fault áp dụng trên một chiều hay hai chiều.

## 6. Ngắt kết nối có nhiều hình thức

| Hiện tượng | Client có thể thấy | Lưu ý |
| --- | --- | --- |
| **Graceful close / FIN** | EOF, connection closed | Peer có thể đóng có chủ đích |
| **TCP reset / RST** | Connection reset | Dòng đang xử lý có thể bị cắt |
| **Connection refused** | Kết nối mới bị từ chối ngay | Không có listener/đích reject |
| **Blackhole/drop** | Kết nối treo rồi timeout | Không có phản hồi rõ ràng |
| **Half-open connection** | Một đầu tưởng socket còn sống | Cần heartbeat/keepalive/deadline |
| **DNS failure** | Không resolve được host | Chưa tới database |
| **TLS handshake failure** | Không thiết lập phiên bảo mật | Khác lỗi query |
| **Connection pool exhaustion** | Chờ kết nối rồi timeout | Có thể không phải node chết |

Ngắt một socket đang hoạt động không đồng nghĩa chặn **mọi kết nối mới**. Driver có thể tự reconnect, thử replica khác hoặc mở lại pool.

### Nên thử ít nhất hai lớp

1. **Drop không phát RST:** kiểm tra deadline và half-open.
2. **Reset/close tức thời:** kiểm tra reconnect và retry.

Hai lỗi có thể dẫn đến hành vi khác nhau rất lớn dù đều được báo là “mất kết nối”.

## 7. Node phản hồi chậm là loại lỗi đặc biệt

Một **slow node** có thể:

- Nhận request nhưng xếp hàng quá lâu.
- Chậm disk hoặc commit log.
- CPU bị cạn.
- Có pause GC.
- Bị scheduler starvation.
- Giới hạn network bandwidth.
- Chậm do compaction/repair/streaming.
- Đang bảo trì index hoặc snapshot.

~~~text
Node A: reply 10 ms
Node B: reply 12 ms
Node C: reply 5 seconds
~~~

Node C không crash, vẫn heartbeat, nhưng có thể gây:

- **Tail latency** tăng.
- Coordinator đợi phản hồi chậm nếu consistency yêu cầu.
- Pool threads/connections bị giữ lâu.
- Retry làm số request đè lên node C càng nhiều.
- Leader election hoặc circuit breaker bị kích hoạt liên tục.

### Slow không phải down

Thử nghiệm chỉ `kill -9` node không thay thế được thử **GC pause hoặc disk stall**. Node đã chết có thể bị phát hiện và route quanh; node **sống nhưng chậm** có thể giữ nhiều tài nguyên hơn và gây hiện tượng cascading failure.

## 8. Ba mức lỗi cần phân biệt

~~~text
Process failure:
  DBMS process crash, host vẫn có mạng.

Host failure:
  VM/node mất khả năng xử lý, có thể mất network.

Network failure:
  Process/host vẫn chạy nhưng một số link bị mất.
~~~

Trong test, ghi:

~~~yaml
faultType: "network-drop"
affectedPath: "client-A -> coordinator-B"
processBStatus: "running"
storageBStatus: "healthy"
duration: "30s"
~~~

Nếu ta giết process để mô phỏng packet loss, kết quả không đại diện cho lỗi mạng bất đối xứng. Một test suite tốt có những thí nghiệm **độc lập** cho process, host, link và slow processing.

## 9. Các điểm tiêm lỗi trên đường một write

Xét:

~~~text
Client → API → Coordinator → Replica quorum → Durable commit → ACK
~~~

Nên thử theo *fault boundary*:

| Điểm lỗi | Điều có thể xảy ra | Rủi ro thử nghiệm cần phát hiện |
| --- | --- | --- |
| Trước API nhận | Request không đến | Client có retry hợp lý không? |
| Sau API nhận, trước ghi | Request được nhận nhưng chưa commit | Có phân biệt unknown outcome? |
| Trong lúc gửi replica | Một số replica nhận mutation | Quorum/repair và timeout ra sao? |
| Sau commit, trước ACK | Dữ liệu đã đổi nhưng client không biết | Duplicate effects khi retry |
| Trong khi trả response | Partial response/reset | Client có hiểu sai dữ liệu không? |
| Sau ACK, trước asynchronous replication | Remote replica chưa bắt kịp | Read ở DC khác có stale không? |

**Thử mất ACK sau commit đặc biệt quan trọng** vì một hệ chỉ kiểm “request trước khi tới server bị mất” thường bỏ sót lỗi nghiệp vụ do retry.

## 10. Mất request và mất response cho cùng một quan sát

Hai lịch:

### Lịch A — request không tới DB

~~~text
Client                     DB
  |---- CREATE order --X   |
  |                        |
  | timeout                |
~~~

Không có đơn được tạo.

### Lịch B — DB đã commit, ACK mất

~~~text
Client                     DB
  |---- CREATE order ----->|
  |                        | COMMIT order O123
  |<----- ACK --------X    |
  | timeout                |
~~~

Đơn O123 **đã tồn tại**.

Từ phía client, cả hai đều có thể là:

~~~text
java.net.SocketTimeoutException
~~~

Do đó điều kiện:

~~~text
if (timeout) retryCreateOrderWithNewId();
~~~

có thể tạo đơn trùng.

## 11. Idempotency: nền tảng của retry an toàn

Một operation **idempotent** nếu thực hiện lặp cùng một ý định không thay đổi kết quả nghiệp vụ sau lần đầu theo contract.

Ví dụ:

~~~text
Set status = "PAID"
~~~

có thể idempotent **đối với đúng một trạng thái**, nhưng vẫn cần xét version/ordering và side effects đi kèm.

Ngược lại:

~~~text
Increment availableInventory by -1
~~~

không idempotent nếu lặp hai lần sẽ trừ hai sản phẩm.

### Idempotency key

Client tạo một khóa ổn định cho **một ý định**:

~~~http
POST /orders
Idempotency-Key: order-create-req-801
~~~

Nếu request timeout, retry vẫn giữ **cùng key và cùng payload**. Server lưu bền/tra cứu kết quả của request đã xử lý và không tạo side effect lặp.

### Bảo đảm server cần có

- Key duy nhất theo phạm vi tenant/operation.
- Mapping key → trạng thái/result được commit **nguyên tử** với hiệu ứng nghiệp vụ hoặc bằng workflow đúng.
- Nếu cùng key đi kèm payload khác, **không được im lặng dùng lại**.
- Xử lý hai retry đồng thời của cùng key.
- Quy định thời gian retention của idempotency record.
- Trạng thái `IN_PROGRESS` không được tự hiểu là committed.

**Chỉ gửi một HTTP header Idempotency-Key không tạo idempotency nếu server không thực thi hợp đồng này.**

## 12. At-most-once, at-least-once và exactly-once

Một phép gọi qua mạng có thể được xử lý theo các ngữ nghĩa:

| Ngữ nghĩa | Hành vi điển hình | Đánh đổi |
| --- | --- | --- |
| **At-most-once attempt** | Không retry thao tác không chắc chắn | Có thể mất ý định nếu request chưa tới |
| **At-least-once delivery** | Retry tới khi có xác nhận theo điều kiện | Có thể xử lý lặp |
| **Effectively-once business effect** | At-least-once + dedupe/idempotent commit | Cần trạng thái/transaction/retention |
| **Exactly-once semantics** | Bảo đảm trong một phạm vi được định nghĩa | Không phải thuộc tính miễn phí của mạng |

Ví dụ một message broker có exactly-once processing trong **một phạm vi transaction nội bộ** không chứng minh một **payment provider bên ngoài** cũng chỉ nhận đúng một lệnh. Bất kỳ lời hứa exactly-once nào cũng phải nói rõ **ranh giới tác động**.

## 13. Retry có thể làm sự cố nghiêm trọng hơn

Giả sử bình thường 1.000 requests/s tới database. Mỗi request được retry tối đa ba lần, và 50% request ban đầu timeout do node chậm.

Nếu nhiều client cùng retry ngay lập tức, lưu lượng tăng trong lúc DB đang quá tải:

~~~text
Node chậm
   ↓
Timeout tăng
   ↓
Retries tăng
   ↓
QPS vào node tăng
   ↓
Node càng chậm
~~~

Đây là **retry amplification** hoặc retry storm.

### Công thức đơn giản

Nếu mỗi attempt thất bại độc lập với xác suất `p` và tối đa `A` attempts, số attempts kỳ vọng là:

\[
E[\text{attempts}]
=\sum_{i=0}^{A-1}p^i
=\frac{1-p^A}{1-p}
\]

với `0\le p<1`.

Ví dụ `p=0.1`, `A=3`:

\[
E=1+0.1+0.01=1.11
\]

Đây chỉ là **mô hình độc lập**. Lỗi production thường **tương quan** (cùng node/region quá tải), nên retry ngay có thể làm xác suất attempt sau **cao hơn** trước.

## 14. Exponential backoff và jitter

Một chiến lược phổ biến:

\[
\operatorname{cap}_i
=\min(\text{maxBackoff},\ \text{base}\times2^{i-1})
\]

với attempt số `i` và một dạng **full jitter**:

\[
\operatorname{sleep}_i\sim U(0,\operatorname{cap}_i)
\]

Ví dụ minh họa `base=100ms`, `maxBackoff=2s`:

~~~text
Retry 1: random 0..100 ms
Retry 2: random 0..200 ms
Retry 3: random 0..400 ms
Retry 4: random 0..800 ms
...
~~~

Jitter tránh hàng nghìn client đồng loạt retry theo cùng nhịp.

### Nhưng backoff không thay deadline

Client có tổng deadline 2 giây không được ngủ 2 giây rồi bắt đầu attempt mới 5 giây. Mỗi retry cần xét **thời gian còn lại**, loại lỗi, trạng thái kết quả và ngân sách retry toàn hệ.

**Không retry mọi lỗi:** lỗi validation 400, dữ liệu không hợp lệ hoặc conflict logic thường không tự hết nếu lặp nguyên request.

## 15. Tổng deadline, per-attempt timeout và retry budget

Một thiết kế rõ ràng:

~~~yaml
operation: "readProduct"
totalDeadlineMillis: 2000
perAttemptTimeoutMillis: 500
maxAttempts: 3
backoff: "exponential full jitter"
retryable:
  - "Transient transport errors"
  - "Documented retryable overload responses"
nonRetryable:
  - "Invalid input"
  - "Business conflict without a new precondition"
~~~

Các con số là **ví dụ**, không phải cấu hình khuyến nghị cho mọi NoSQL/driver.

### Ba giới hạn cần có

1. **Per-attempt timeout:** một lần gọi được chờ tối đa bao lâu.
2. **Total deadline:** toàn bộ operation được phép tiêu tốn bao lâu.
3. **Retry budget:** một client/service được phép tạo thêm bao nhiêu attempt so với traffic gốc.

Nếu có nhiều tầng:

~~~text
Browser retry
   → API gateway retry
       → Application service retry
           → DB driver retry
~~~

ba lần retry ở từng tầng có thể tạo nhiều attempt tới DB hơn trực giác. Nên xác định **tầng chịu trách nhiệm retry**, tránh retry không kiểm soát chồng nhau.

## 16. Retry read khác retry write

**Read-only point lookup** thường dễ retry hơn nếu không có side effect và freshness contract cho phép. Nhưng:

- Retry tới replica khác có thể đọc bản cũ trong eventual consistency.
- Một paginated read có thể thay đổi snapshot.
- Một request scan lớn bị retry có thể tăng tài nguyên đáng kể.
- Nếu read cần monotonic reads, version watermark có thể phải theo request.

**Write** có thể thay đổi trạng thái. Đặc biệt:

~~~text
INSERT order
INCREMENT counter
DECREMENT inventory
SEND payment
APPEND event
~~~

thường đòi **idempotency hoặc conditional semantics** trước khi tự retry.

**Không suy từ tên HTTP method rằng operation chắc chắn idempotent trên mọi implementation.** Kiểm tra contract và side effects thực.

## 17. Quorum khi replica phản hồi chậm

Giả sử một partition có RF=3 với ba replica A, B, C:

~~~text
A responds in 10 ms
B responds in 12 ms
C responds in 3000 ms
~~~

Theo mô hình majority quorum đơn giản:

- Nếu operation cần **một** replica phù hợp, có thể hoàn tất nhanh từ A.
- Nếu cần **hai** replica phù hợp, A+B có thể đủ.
- Nếu cần **cả ba** replica, C có thể quyết định latency/timeout.

| Replica phản hồi | Điều kiện một replica | Majority 2/3 | All 3/3 |
| --- | --- | --- | --- |
| A và B nhanh, C chậm | Có thể đáp ứng | Có thể đáp ứng | Phải đợi/timeout C |
| Chỉ A reachable | Có thể đáp ứng | Không đủ | Không đủ |
| A chậm, B và C nhanh | Có thể đáp ứng | Có thể đáp ứng | Đợi A |
| Cả ba unreachable | Không | Không | Không |

Đây là **minh họa số học**, không thay thế giao thức Cassandra/MongoDB/Raft cụ thể. Điều kiện version, commit, leader và topology có thể làm kết quả khác.

### Không tự đồng nhất QUORUM với linearizability

Điều kiện giao nhau như `R+W>N` có ích nhưng chưa giải quyết concurrent writes, version ordering, commit semantics hoặc membership changes. Trong test cần kiểm **consistency thật được DBMS hứa**.

## 18. Mất gói trên một replica không đồng nghĩa mất quorum

Ví dụ:

~~~text
Client → Coordinator
           ├─→ Replica A: OK
           ├─→ Replica B: OK
           └─X Replica C: packet loss
~~~

Nếu write policy cho phép ACK khi A và B đáp ứng điều kiện, write có thể trả thành công dù C đang lỗi. Nhưng C sau khi trở lại cần được **bắt kịp** bằng cơ chế replication/repair phù hợp.

Một test chỉ dừng ngay sau khi thấy HTTP 200 chưa đầy đủ: còn cần kiểm tra:

1. Khi C trở lại, dữ liệu có được hội tụ theo contract không?
2. Những mutation đã ACK có còn sau node A/B restart không?
3. Read từ các replica có khác nhau trong giai đoạn đó không?
4. Có tombstone/TTL nào bị bỏ lỡ không?
5. Repair backlog có được giám sát không?

## 19. Mạng chia 2–1 khác node crash

~~~text
       Network partition

Group 1            Group 2
  A, B       X        C
~~~

Nếu hệ cần majority 2/3, nhóm A,B có thể có điều kiện tiếp tục những strong operations. C không nên tự commit những write xung đột nếu vẫn đòi một lịch nhất quán chung.

Khác với crash:

- C vẫn sống và có thể nhận request của client gần nó.
- C có thể giữ một bản sao cũ.
- C có thể tin leader cũ vẫn hợp lệ nếu protocol không xử lý đúng.
- Khi kết nối khôi phục, dữ liệu/term/membership có thể cần hội tụ.

### Kịch bản quan trọng

Tiêm partition, sau đó **cố ý gửi write vào cả hai phía** và kiểm invariant. Nếu phía minority trả lỗi thay vì nhận write mâu thuẫn, đó có thể là **hành vi đúng** cho tính nhất quán mạnh.

## 20. Mạng bất đối xứng gây lỗi khó phát hiện

~~~text
A → B : packets arrive
B → A : all packets dropped
~~~

Trên A:

~~~text
Request appears sent.
No response arrives.
~~~

Trên B:

~~~text
Request processed and response sent.
~~~

Đây là mô hình **lost response** ngay cả khi B khỏe. Một số heartbeat/health check có thể đi trên đường khác hoặc chiều khác, khiến dashboard cho rằng B UP trong khi write path gặp timeout.

Thử nghiệm cần có:

- Drop chiều request.
- Drop chiều response.
- Chặn cả hai chiều.
- Chặn chỉ một replica/coordinator.
- Chặn một nhóm node qua AZ/DC.

**Định nghĩa “reachable” nên dựa trên luồng operation cụ thể, không chỉ ping.**

## 21. TCP half-open và connection pool

Khi một đường mạng bị blackhole mà không gửi FIN/RST, mỗi đầu có thể tưởng TCP connection vẫn mở.

Ứng dụng có thể:

- Giữ connection trong pool dù không dùng được.
- Treo khi ghi/đọc socket cho tới deadline.
- Tạo nhiều connections mới sau timeout.
- Chạm giới hạn file descriptors hoặc pool size.
- Gây head-of-line blocking trong những mô hình multiplex/connection management.

Thử nghiệm cần đo:

| Metric | Điều cần quan sát |
| --- | --- |
| Active connections | Có bị tăng mãi không? |
| Pool wait time | Request chờ lấy connection bao lâu? |
| Reconnect attempts | Có retry theo backoff không? |
| Socket timeout | Có được cấu hình và thực thi không? |
| In-flight requests | Có tích tụ rồi không giải phóng? |
| File descriptors | Có rò rỉ tài nguyên không? |

**Một luồng kết nối đã lỗi phải được giải phóng hoặc thay thế theo driver/protocol**, không để tài nguyên kẹt vô hạn.

## 22. Slow node và tail latency

Giả sử 99% request mất 10 ms, nhưng 1% mất 5 giây:

~~~text
p50 ≈ 10 ms
p95 ≈ 10 ms
p99 có thể gần ranh giới 5 s tùy phân bố mẫu
~~~

Giá trị trung bình không phản ánh đầy đủ trải nghiệm ở đuôi phân bố.

Một request phải chờ nhiều thành phần:

~~~text
API → DB coordinator → 3 replica replies
~~~

có thể chịu độ trễ của replica chậm nếu policy yêu cầu đủ cả ba.

### Những phép đo cần có

- p50, p95, p99 và maximum theo từng operation.
- Per-replica latency/timeout.
- Queue depth, CPU, GC pauses.
- Disk write latency, compaction backlog.
- Thread pool và connection pool saturation.

Không nhìn mỗi CPU: node có CPU thấp vẫn có thể phản hồi chậm vì disk stall hoặc lock contention.

## 23. Slow node vs slow network

Hai tình huống có cùng tổng latency:

~~~text
Scenario A:
  Network RTT 1000 ms
  Server processing 10 ms

Scenario B:
  Network RTT 10 ms
  Server processing 1000 ms
~~~

Tuy client có thể cùng thấy khoảng 1 giây, cách xử lý khác:

- **Slow network:** timeout/retry routing, connection recovery, mạng liên vùng.
- **Slow processing:** queue, GC, disk, compaction, thread exhaustion, backpressure.

Để tách chúng trong lab:

1. Tiêm delay bằng network proxy trong một thí nghiệm.
2. Tiêm server-side processing delay qua test hook trong thí nghiệm khác.
3. Ghi timestamp tại client, proxy, handler, DB commit.
4. So sánh latency decomposition và hành vi retry.

Nếu chỉ dùng `Thread.sleep` trong API rồi gọi là “packet loss”, test sẽ không bao phủ những lỗi TCP/retransmission/half-open.

## 24. Lên kế hoạch thí nghiệm theo một giả thuyết

Một thí nghiệm tốt có cấu trúc:

~~~yaml
experimentId: "db-read-loss-01"
hypothesis: >
  When 10% of packets are dropped toward one replica,
  read-only lookups remain within a defined error budget
  and no requests hang beyond the total deadline.
steadyState:
  workload: "fixed-rate product lookup"
  readConsistency: "documented value"
  expectedErrorRate: "baseline-specific"
fault:
  location: "test proxy to replica C"
  direction: "request egress"
  type: "random packet loss"
  rate: "10%"
  duration: "60s"
abortConditions:
  - "In-flight count exceeds lab safety limit"
  - "Unintended nodes or services are affected"
verification:
  - "Latency and error metrics"
  - "Connection pool recovers"
  - "No stale operation presented as strong"
cleanup:
  - "Disable network toxic"
  - "Verify traffic restored"
~~~

Các ngưỡng trong YAML là ví dụ; giá trị thực dựa trên **SLO, loại workload và capacity của môi trường thử**.

**Mỗi thí nghiệm nên kiểm một giả thuyết chính**, để biết chính xác điều gì làm thay đổi kết quả.

## 25. Các bước tối thiểu của một fault-injection run

### Bước 1 — Định nghĩa trạng thái bình thường

Chạy workload ổn định không lỗi; ghi throughput, p95/p99, resource usage, replication lag và invariant.

### Bước 2 — Chọn phạm vi blast radius

Ví dụ **một client test và một replica giả lập**, không toàn production AZ.

### Bước 3 — Chạy workload có định danh

Mỗi operation có `requestId`, `tenantId` test, thời điểm bắt đầu/kết thúc, expected outcome.

### Bước 4 — Tiêm đúng một lỗi

Loss, disconnect hoặc slowdown đã xác định; ghi mốc bắt đầu/kết thúc.

### Bước 5 — Theo dõi trong lúc lỗi

Đo số request còn chờ, retries, duplicate effects, quorum errors, timeouts, backlog, leader changes.

### Bước 6 — Gỡ lỗi và quan sát hồi phục

Phục hồi mạng; kiểm sự hội tụ dữ liệu, connection pool, repair/reconnect và latency.

### Bước 7 — Đối soát dữ liệu

So business intents với committed effects, không chỉ đếm HTTP 200.

### Bước 8 — Ghi kết luận có điều kiện

Tách:

~~~text
Observed: 0 duplicate orders in 10,000 test intents.

Not proven: no duplicate orders under all possible races.
~~~

Đừng biến một lần test pass thành lời bảo đảm tuyệt đối.

## 26. Dùng proxy có thể bật/tắt lỗi

Một hướng thực hành phổ biến là đặt **fault-injection proxy** giữa client test và DB/service test:

~~~text
Test client
     |
     v
Fault proxy
     |
     v
Test DB node
~~~

Các công cụ như **Toxiproxy** cho phép tạo điểm proxy và những *toxics* mô phỏng delay, connection problems hoặc bandwidth limits trong phạm vi khả năng của công cụ/version.

### Lợi thế

- Không cần can thiệp network interface của cả host.
- Mỗi test có proxy riêng.
- Có thể bật/tắt fault theo giai đoạn.
- Dễ đưa vào integration test với Testcontainers hoặc docker-compose theo phiên bản hỗ trợ.

### Giới hạn

- Chỉ traffic **đi qua proxy** bị ảnh hưởng.
- DB driver có thể tự kết nối trực tiếp tới node khác qua metadata discovery.
- Proxy ở tầng TCP không thể luôn tiêm lỗi chính xác “sau database commit trước ACK” nếu không hiểu message boundary.
- Một số lỗi DNS/TLS/process cần thí nghiệm riêng.

**Không đặt proxy rồi mặc định toàn bộ đường replica-to-replica traffic cũng qua nó**; phải kiểm topology thực tế của test.

## 27. Network emulation trên Linux với `tc netem`

Trên Linux, `tc netem` có thể mô phỏng delay/loss/reorder/duplication trên một **network interface**. Ví dụ sau là **cú pháp minh họa trên interface lab riêng tên `veth-test`**.

~~~bash
# Chỉ thực hiện khi veth-test thuộc network namespace lab.
# Tiêm 10% packet loss trên egress của interface.
sudo tc qdisc replace dev veth-test root netem loss 10%

# Thay bằng độ trễ 200 ms, dao động 50 ms.
sudo tc qdisc replace dev veth-test root netem delay 200ms 50ms

# Phục hồi interface lab về trạng thái không có qdisc netem.
sudo tc qdisc del dev veth-test root
~~~

### Những điều phải hiểu trước khi chạy

1. `tc` cấu hình **egress** theo interface; muốn mô phỏng chiều ngược phải chọn điểm khác phù hợp.
2. Interface lab phải được xác nhận chính xác; **không thay bằng `eth0` của host đang phục vụ production**.
3. Lệnh `replace` **thay** qdisc trước đó, không tự cộng dồn hai faults.
4. Tỉ lệ loss là **packet-level**, không phải request-level.
5. Quyền root/sudo, network namespaces, quyền container và kernel modules ảnh hưởng khả năng chạy.
6. Lệnh cleanup phải được thử trước, và cần đường truy cập ngoài luồng nếu thử nghiệm trên host từ xa.

Để tránh vô tình làm mất SSH hoặc hệ thống chung, cách tốt hơn là **tạo interface/namespace hoặc container network dành riêng cho lab**, dùng công cụ tự dọn khi test kết thúc.

## 28. Không nhầm test mạng với lệnh phá hạ tầng

Có thể mô phỏng ngắt kết nối bằng:

- Ngắt đường tại proxy test.
- Drop traffic giữa những network namespaces riêng.
- Tạm tắt một service mô phỏng.
- Dùng fault-injection hooks ở storage/client layer.

Nhưng các cách này **khác nhau**:

~~~text
Kill process:
  Existing socket may reset/close.

Drop packets:
  Socket may remain half-open until timeout.

Reject connection:
  New connection can fail immediately.

Delay server handler:
  Connection lives; processing is slow.
~~~

Chỉ gọi “simulate disconnection” là chưa đủ để so kết quả. Mỗi test case phải chỉ rõ cơ chế.

## 29. Thử lỗi theo chiều và theo nhóm replica

Một test topology:

~~~text
                     Client
                        |
                        v
                   Coordinator
                     /  |  \
                    A   B   C
~~~

Các biến thể:

| ID | Fault | Mục tiêu quan sát |
| --- | --- | --- |
| N1 | Drop client → coordinator | Client timeout và retry |
| N2 | Drop coordinator → C | Quorum khi thiếu một replica |
| N3 | Drop C → coordinator | Replica xử lý nhưng ACK mất |
| N4 | Delay B 3 giây | Tail latency, quorum và timeout |
| N5 | Disconnect A-B cả hai chiều | Cluster membership, replication |
| N6 | Partition A+B với C | Strong write behavior mỗi phía |
| N7 | Reset existing TCP connection | Pool recovery |
| N8 | Blackhole TCP without reset | Half-open, total deadline |
| N9 | Burst loss 10 giây | Retry synchronization |
| N10 | Restore links after burst | Catch-up/repair |

Không được mặc định test N3 chỉ làm mất **reply cho đúng một write** nếu công cụ đang drop mọi packet trên link: cần ghi rõ độ hạt của fault.

## 30. Dữ liệu thử phải có oracle nghiệp vụ

Thử tạo 1.000 đơn hàng, mỗi đơn gắn **một ý định duy nhất**:

~~~text
intent-0001 → requestId r-0001
intent-0002 → requestId r-0002
...
intent-1000 → requestId r-1000
~~~

Sau lỗi và retry, đối soát:

~~~text
Số intents được xác nhận thành công
Số order rows thực tế
Số orderId duy nhất
Số idempotency keys duy nhất
Tổng inventory đã trừ
Số payment captures / outbox events
~~~

Invariant:

\[
\forall r:\ \operatorname{committedOrders}(r)\le 1
\]

Nếu hệ hứa “mỗi intent được xác nhận thành công có đúng một order”, cần kiểm:

\[
\operatorname{confirmed}(r)
\Rightarrow \operatorname{committedOrders}(r)=1
\]

**Đếm số response 201 không đủ**, bởi lost ACK có thể tạo committed order nhưng client chỉ thấy timeout.

## 31. Chọn workload để lỗi có ý nghĩa

Một bộ workload có thể gồm:

- **Read-only:** point lookup, query theo index, range scan.
- **Single-key write:** cập nhật profile/idempotent put.
- **Conditional write:** compare-and-set/giảm tồn kho.
- **Append/event:** ghi event với eventId ổn định.
- **Multi-record transaction:** nếu DBMS hỗ trợ trong phạm vi cần thiết.
- **Large payload:** upload/blob/document lớn, nhiều packets.
- **Hot key:** nhiều client tranh cùng một key.
- **Multi-tenant:** traffic của tenant nhỏ và tenant rất lớn.

Chỉ thử một GET nhỏ khi lỗi mạng không đủ để đánh giá write quorum, retries, pagination, streaming hoặc data invariants.

### Tách steady load và burst load

~~~text
Steady: 100 requests/s trong 5 phút.
Burst: 1.000 requests/s trong 10 giây.
~~~

Hai workload có thể phản ứng khác nhau vì queueing, connection pool và retry synchronization. Các con số chỉ minh họa, cần phù hợp capacity của môi trường lab.

## 32. Java: mô phỏng request drop và ACK loss

Ví dụ Java dưới đây chạy **hoàn toàn trong một JVM**, không mở socket và không tác động network thật. Nó mô phỏng ba tình huống:

1. Request bị mất trước khi tới server.
2. Request **đã commit**, nhưng response bị mất.
3. Client retry cùng `requestId` và nhận lại kết quả mà không tạo đơn thứ hai.

Để thấy rủi ro, chương trình cũng minh họa việc retry với **requestId mới** có thể tạo thêm một đơn.

Tạo file `FaultRetryDemo.java`:

~~~java
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

public final class FaultRetryDemo {

    enum Fault {
        NONE,
        DROP_REQUEST,
        DROP_RESPONSE_AFTER_COMMIT
    }

    static final class Result {
        final String orderId;
        final int remainingInventory;

        Result(String orderId, int remainingInventory) {
            this.orderId = orderId;
            this.remainingInventory = remainingInventory;
        }
    }

    static final class OrderServer {
        private final Map<String, Result> byRequest =
                new HashMap<>();
        private int inventory = 10;
        private int createdOrders = 0;

        // Trong mô hình một JVM, synchronized bảo đảm
        // kiểm tra requestId và commit là nguyên tử.
        synchronized Result create(String requestId) {
            Result existing = byRequest.get(requestId);
            if (existing != null) {
                return existing;
            }
            if (inventory == 0) {
                throw new IllegalStateException("Sold out");
            }
            inventory--;
            createdOrders++;
            Result result = new Result(
                    "O-" + createdOrders, inventory);
            byRequest.put(requestId, result);
            return result;
        }

        synchronized int countOrders() {
            return createdOrders;
        }
    }

    static final class FakeTransport {
        private final OrderServer server;

        FakeTransport(OrderServer server) {
            this.server = server;
        }

        Result send(String requestId, Fault fault)
                throws IOException {
            if (fault == Fault.DROP_REQUEST) {
                throw new IOException(
                        "Packet lost before server receives request");
            }
            Result response = server.create(requestId);
            if (fault == Fault.DROP_RESPONSE_AFTER_COMMIT) {
                throw new IOException(
                        "ACK lost after server commit");
            }
            return response;
        }
    }

    static void printResult(String label, Result result) {
        System.out.println(label + ": "
                + result.orderId
                + ", remaining=" + result.remainingInventory);
    }

    public static void main(String[] args)
            throws IOException {
        OrderServer server = new OrderServer();
        FakeTransport network = new FakeTransport(server);

        // Case 1: Request chưa tới server.
        try {
            network.send("req-A", Fault.DROP_REQUEST);
        } catch (IOException expected) {
            System.out.println("A: " + expected.getMessage());
        }
        System.out.println("Orders after A loss="
                + server.countOrders());

        // Retry cùng id: tạo đúng một order.
        Result a = network.send("req-A", Fault.NONE);
        printResult("A retry", a);

        // Case 2: Server đã commit nhưng ACK bị mất.
        try {
            network.send("req-B",
                    Fault.DROP_RESPONSE_AFTER_COMMIT);
        } catch (IOException expected) {
            System.out.println("B: " + expected.getMessage());
        }
        System.out.println("Orders after lost B ACK="
                + server.countOrders());

        // Retry cùng id: trả lại result cũ.
        Result b = network.send("req-B", Fault.NONE);
        printResult("B safe retry", b);
        System.out.println("Orders after safe retry="
                + server.countOrders());

        // Sai: cùng ý định nhưng dùng request ID mới.
        Result duplicate =
                network.send("req-B-new", Fault.NONE);
        printResult("B unsafe retry", duplicate);
        System.out.println("Orders after unsafe retry="
                + server.countOrders());
    }
}
~~~

Chạy trong một thư mục học tập:

~~~bash
javac FaultRetryDemo.java
java FaultRetryDemo
~~~

Kết quả dự kiến:

~~~text
A: Packet lost before server receives request
Orders after A loss=0
A retry: O-1, remaining=9
B: ACK lost after server commit
Orders after lost B ACK=2
B safe retry: O-2, remaining=8
Orders after safe retry=2
B unsafe retry: O-3, remaining=7
Orders after unsafe retry=3
~~~

### Giới hạn của mô phỏng

- Chưa có actual TCP, packet retransmission hoặc timeout clock.
- Không có nhiều node, crash, disk/WAL hay replication.
- `synchronized` chỉ bảo vệ một JVM; production cần idempotency record bền vững và commit đúng phạm vi.
- Không mô phỏng payload mismatch cùng key hoặc retention hết hạn.
- “ACK loss” là fault giả lập đúng giai đoạn để học ambiguous outcome.

**Thông điệp chính:** cùng một IOException có thể tương ứng với **chưa thực hiện** hoặc **đã commit**. Retry cùng intent phải được thiết kế cho cả hai lịch.

## 33. Java HTTP client: timeout không bảo đảm write chưa xảy ra

Java 11+ có `java.net.http.HttpClient`. Ví dụ cấu hình hai loại timeout:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(1))
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("http://localhost:8080/orders"))
        .timeout(Duration.ofSeconds(2))
        .header("Idempotency-Key", "req-801")
        .header("Content-Type", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(
                "{\"sku\":\"SKU-7\",\"quantity\":1}"))
        .build();
~~~

Đoạn mã mới **khởi tạo client/request**, chưa gửi request. Nếu sau đó `client.send(...)` báo timeout, client **không được tự suy** server chưa tạo đơn.

### Hai loại timeout

- **Connect timeout:** giới hạn giai đoạn thiết lập kết nối trong phạm vi API.
- **Request timeout:** giới hạn thời gian xử lý request theo semantics của thư viện.

Driver NoSQL và các protocol khác có thể thêm server-side timeout, coordinator timeout, heartbeat, socket timeout, total deadline... Không được đồng nhất chúng chỉ vì cùng dùng đơn vị mili giây.

## 34. Fault injection có tính quyết định và ngẫu nhiên

### Deterministic faults

Ví dụ:

~~~text
Request #1: drop before server receives.
Request #2: commit then drop ACK.
Request #3: delay response by 3 seconds.
~~~

Ưu điểm:

- Có thể tái hiện history cụ thể.
- Dễ kiểm invariant và debug.
- Phù hợp test regression sau khi sửa bug.

### Probabilistic faults

Ví dụ:

~~~text
Each packet: 5% random loss.
Each request: random delay 0..300 ms.
Network partition starts at random moment.
~~~

Ưu điểm:

- Khám phá interleavings khó dự đoán.
- Tạo tail latency và tải retry đa dạng.

Nhược điểm: khó tái hiện nếu không lưu **seed, vị trí, thời gian và lịch event**.

### Kết hợp

Dùng deterministic để **chứng minh một phản ví dụ đã biết không tái diễn trong test**, sau đó randomized fault injection để mở rộng độ bao phủ. Không dùng randomness làm lý do bỏ qua reproducibility.

## 35. Test thời điểm lỗi so với transaction

Đừng chỉ tiêm fault “vào thời gian ngẫu nhiên”. Với write quan trọng, tạo các hook:

~~~text
BEFORE_RECEIVE
AFTER_RECEIVE_BEFORE_VALIDATE
AFTER_VALIDATE_BEFORE_COMMIT
AFTER_COMMIT_BEFORE_ACK
AFTER_ACK_BEFORE_REPLICA_CATCHUP
~~~

Ví dụ:

~~~text
Test: AFTER_COMMIT_BEFORE_ACK
Expected:
  Client outcome may be unknown.
  Server committed exactly one business intent.
  Retried same requestId returns same result.
~~~

Đây là **phase-aware fault injection**. Nó giúp tìm bug mà network-only chaos khó đánh đúng thời điểm.

**Đừng thêm test hook production có thể bị người ngoài tùy ý kích hoạt.** Hook nên được giới hạn trong test build/isolated environment hoặc hệ thống có kiểm soát quyền rõ ràng.

## 36. Read-after-write khi retry sang replica khác

Giả sử:

~~~text
Client write x=7 → ACK từ một đường local.
Replica A: x=7
Replica B: x=7
Replica C: x=5 (chưa bắt kịp)
~~~

Client sau đó đọc lại nhưng driver chuyển đường tới C vì A mất kết nối.

Nếu API chỉ bảo đảm **eventual consistency**, read có thể trả `x=5` trong thời gian chờ hội tụ.

Nếu API hứa **read-your-writes** hoặc **linearizability**, phải có cơ chế bảo vệ đường đọc: consistency level, session token/version watermark hoặc một protocol phù hợp.

### Câu hỏi trong test

1. Read nào được phép stale?
2. Write ACK theo điều kiện nào?
3. Retry có thay coordinator/replica không?
4. Read có mang session/version token không?
5. Khi mạng phục hồi, replica chậm có bắt kịp không?

**Không gọi mọi stale read là bug** nếu đó là hành vi phù hợp contract; cũng không che giấu stale read nếu API cam kết dữ liệu mới nhất.

## 37. Retry writes trong hệ LWW có thể gây lỗi ordering

Một số hệ giải quyết conflict bằng timestamp/last-write-wins (LWW) theo quy tắc riêng.

Lịch:

~~~text
T0: Client gửi status=PAID, request W1.
T1: W1 bị delay.
T2: Client hoặc service mới ghi status=SHIPPED, W2.
T3: Retry của W1 tới muộn.
~~~

Nếu retry W1 được gán timestamp mới hoặc ghi không điều kiện, trạng thái có thể bị đưa lùi từ SHIPPED về PAID.

### Hướng bảo vệ

- Version check/conditional update.
- Event ordering theo sequence authoritative.
- Idempotency theo intent.
- State machine cấm transition ngược.
- Đọc/ghi consistency phù hợp.

**Idempotent retry theo request ID và tính hợp lệ của transition là hai lớp bảo vệ khác nhau.** Dedupe W1 không tự cấm một W1 hợp lệ cũ tới trước W2 nhưng bị áp sau nếu protocol không có ordering.

## 38. Circuit breaker và backpressure

Khi một node liên tục timeout, client có thể dùng **circuit breaker** để tạm ngừng gửi attempt tới node đó:

~~~text
CLOSED    → gửi bình thường
OPEN      → fail fast / route khác theo policy
HALF_OPEN → cho một lượng nhỏ probe
~~~

Điều này giúp hạn chế retry storm, nhưng:

- Không được failover sang replica stale cho strong operation nếu contract cấm.
- Không để circuit breaker mãi OPEN sau khi node phục hồi.
- Probe cần giới hạn để không gây tải mới.
- Health check cần đại diện cho operation path, không chỉ TCP connect.

**Backpressure** cũng quan trọng: khi queue/connection pool đầy, có thể cần từ chối sớm hoặc giảm admission thay vì giữ vô hạn request rồi timeout hàng loạt.

## 39. Hedged requests: giảm latency nhưng tăng tải

Một số hệ phát **request dự phòng** tới replica khác nếu request đầu tiên quá chậm:

~~~text
T0: Read gửi Replica A.
T1: A vẫn chậm, gửi thêm tới B.
T2: B trả nhanh, client dùng kết quả.
~~~

Kỹ thuật này có thể giảm p99 cho **một số read idempotent**, nhưng làm tăng tải DB và network. Khi cluster đã quá tải, hedging không kiểm soát có thể làm lỗi nặng hơn.

### Cẩn thận với write

Không tự hedge một non-idempotent write sang hai replica hoặc hai API servers nếu chưa có protocol dedupe và commit đảm bảo. “Request nhanh nhất thắng” không phải quy tắc nhất quán cho update tồn kho.

Trong thí nghiệm, nên đo:

- Hedging rate.
- Extra attempts/requests.
- p99 cải thiện hay xấu đi.
- Tải replica khác tăng bao nhiêu.
- Có vi phạm freshness/business invariant không.

## 40. Slow quorum member và leader election

Trong một replica set hoặc consensus cluster, một node phản hồi chậm có thể ảnh hưởng:

- Heartbeats.
- Quorum liveness.
- Leader elections.
- Log replication.
- Commit index advancement.
- Read-index/lease-based reads.

Nếu số lượng node chậm đủ lớn để majority không phản hồi kịp, write throughput có thể giảm hoặc hệ ngừng chấp nhận strong writes.

### Test cần tránh khẳng định sai

“Node vẫn UP nên leader không được đổi” — không đúng chung. Health status có thể khác failure detector hoặc election rule.

“Leader đổi thì đã mất dữ liệu” — cũng không đúng chung. Một protocol đúng có thể đổi leader mà vẫn giữ commit safety.

Nên đo:

- Term/epoch transitions.
- Election duration và churn.
- Log/replication lag.
- Committed vs uncommitted writes.
- Strong read behavior sau leader change.

## 41. Khôi phục mạng và sự hội tụ của dữ liệu

Khi lỗi kết thúc, **không dừng test ngay**:

~~~text
Fault OFF
   |
   v
Reconnect
   |
   v
Replica catch-up / repair
   |
   v
Backlog drains
   |
   v
Latency returns to baseline
   |
   v
Business reconciliation
~~~

Các câu hỏi:

1. Node có reconnect tự động không?
2. Streaming/repair backlog có về 0 hoặc mức chấp nhận không?
3. Dữ liệu đã ACK có còn đúng sau restart?
4. Không xuất hiện duplicate order/payment?
5. Circuit breaker/pool có tự phục hồi?
6. Replica cũ có thể gây resurrection sau tombstone/TTL không?
7. Mất bao lâu để p99 trở lại mức ổn định?

**Recovery time là một kết quả thử nghiệm riêng**, không chỉ là thời điểm ta gỡ rule chặn mạng.

## 42. Consistency khi restore một replica stale

Ví dụ ba replica A/B/C:

~~~text
T0: A,B,C chứa value=1.
T1: C mất liên lạc.
T2: A/B ghi value=2, ACK theo policy.
T3: A/B áp một DELETE hoặc TTL expiration.
T4: C trở lại với value=1.
~~~

Hệ cần cơ chế đưa C về trạng thái hợp lệ và **không để phiên bản cũ xuất hiện trở lại trái contract**.

Trong những storage engines dùng tombstones/anti-entropy, thời gian C offline, retention và repair schedule ảnh hưởng an toàn. Không tùy ý chỉnh tombstone grace hoặc tắt repair để test “chạy nhanh hơn”, rồi coi kết quả đại diện production.

## 43. Test matrix cho loss, disconnect và slowness

| Test ID | Fault tiêm | Workload | Quan sát chính |
| --- | --- | --- | --- |
| L01 | Packet loss 1% | GET theo key | p95/p99, retransmission |
| L02 | Packet loss 10% | GET theo key | Timeout, retry budget |
| L03 | Burst loss 100% trong 5s | Mixed reads/writes | Retry synchronization, recovery |
| L04 | Drop response direction | POST idempotent | Unknown outcome, duplicate effects |
| L05 | Drop before server receives | POST idempotent | Safe retry hoàn tất ý định |
| D01 | TCP RST | Đọc từ pool | Reconnect, pool cleanup |
| D02 | Silent blackhole | Đọc/ghi | Total deadline và half-open |
| D03 | Partition 2–1 replica | Strong write | Quorum và safety |
| D04 | Partition client → leader | Mixed workload | Election/route behavior |
| D05 | Partition một chiều | Conditional write | Ambiguous outcomes |
| S01 | Delay một replica 1s | Quorum read | Tail latency |
| S02 | GC pause 10s | Leader/coordinator | Failover và stale holder |
| S03 | Disk latency tăng | Write-heavy | Commit latency/backpressure |
| S04 | Bandwidth limit | Replication | Lag, backlog, write latency |
| S05 | Slow callback sau commit | POST | Late ACK, retry dedupe |
| R01 | Phục hồi liên lạc | Mixed workload | Catch-up và convergence |
| R02 | Node cũ trở lại | Reads/tombstones | Không hồi sinh dữ liệu cũ |

**Ma trận là nguồn ý tưởng**, không có expected output chung cho mọi Cassandra, MongoDB, Redis hay DynamoDB configuration. Trước mỗi test phải ghi consistency policy và invariant tương ứng.

## 44. Các điều kiện dừng thí nghiệm

Ngay cả trong staging, fault injection có thể ảnh hưởng dịch vụ dùng chung.

Ví dụ abort conditions:

- Sai network interface hoặc sai phạm vi node.
- Tỉ lệ lỗi lan sang service ngoài nhóm thử.
- Quá ngưỡng CPU/disk/connection pool.
- Thiếu disk do backlog/repair.
- Mất quyền truy cập quản trị để gỡ lỗi.
- Không còn đủ quorum để khôi phục theo kịch bản an toàn.
- Phát hiện dữ liệu nghiệp vụ thật trong môi trường thử.

### Khôi phục sau abort

1. Tắt toxic/rule lỗi tại chính nơi đã bật.
2. Kiểm các đường mạng được phục hồi hai chiều.
3. Kiểm cluster membership/quorum.
4. Đợi replication/repair hoàn tất theo policy.
5. So dữ liệu với oracle và rà lại resources bị leak.
6. Chỉ đánh dấu thí nghiệm kết thúc sau khi hệ trở về trạng thái ổn định được định nghĩa.

**Cleanup là một bước bắt buộc của test**, không phải “làm nếu còn thời gian”.

## 45. Những anti-pattern trong thử lỗi phân tán

| Cách làm sai | Vì sao sai | Cách tiếp cận đúng |
| --- | --- | --- |
| Chỉ tắt một node rồi gọi là đã thử packet loss | Crash khác network partition | Thử từng fault mode |
| Chỉ đo HTTP 200 | Có thể vi phạm invariant | Đối soát committed effects |
| Coi timeout là thất bại chắc chắn | ACK có thể mất sau commit | Unknown outcome/idempotency |
| Retry POST với request ID mới | Có thể tạo tác động lặp | Reuse stable idempotency key |
| Retry tất cả lỗi liên tục | Retry storm | Deadline, budget, backoff, jitter |
| Chọn p99 làm thời hạn bất khả vượt | p99 không phải hard bound | Phân biệt SLO và safety |
| Tiêm 10% packet loss rồi gọi 10% request failed | TCP có retransmission | Đo request outcomes |
| Chỉ thử packet loss ngẫu nhiên | Bỏ sót burst loss/partition | Thêm correlated fault |
| Chỉ drop hai chiều | Bỏ sót lost ACK một chiều | Thử asymmetric failures |
| Chỉ kill DB process | Không thấy half-open connection | Thử blackhole |
| Chỉ đo average latency | Bỏ sót tail latency | p95/p99, queue, pool |
| Thấy node UP là kết luận data mới | Replica có thể stale | Verify lag/repair |
| Dựa vào health ping thay write path | Ping khác RPC/commit path | Path-aware checks |
| Thử strong write trên minority rồi đòi HTTP 200 | Sai mục tiêu safety | Xem error như hành vi đúng |
| Gỡ fault là kết thúc test | Backlog chưa drain | Quan sát convergence |
| Tăng số retries mọi tầng | Khuếch đại tải | Tập trung retry policy |
| Dùng sleep thay packet drop | Không kiểm TCP/transport semantics | Test faults ở đúng layer |
| Dùng `tc` trên interface SSH production | Có thể tự khóa đường quản trị | Lab namespace/proxy |
| Coi một lần test pass là chứng minh mọi lịch | Chưa bao phủ interleavings | Regression + randomized histories |
| Không lưu seed/timestamps/fault config | Khó tái hiện lỗi | Record test provenance |

## 46. Một test plan đầy đủ cho dịch vụ đặt hàng

Giả sử service có API:

~~~text
POST /orders
GET  /orders/{orderId}
POST /inventory/reserve
~~~

Nghiệp vụ:

~~~text
Mỗi requestId tạo tối đa một order.
Không bán vượt tồn.
Order đã xác nhận không được mất sau lỗi đã nằm trong mức chịu lỗi cam kết.
~~~

### Workload

- 100 client giả lập với request IDs ổn định.
- Một phần client cùng đặt SKU nóng.
- Đọc lại đơn sau write.
- Một phần read dùng read model eventual, phần khác yêu cầu authoritative read.

### Fault phases

1. Baseline.
2. Drop client→API trước nhận.
3. Mất ACK sau commit.
4. Delay replica C.
5. Partition 2–1.
6. Restore và retry.
7. Restart replica từng bị cô lập.

### Expected behavior

- Không có hai order cho một requestId.
- Không decrement inventory hai lần vì retry.
- Trong minority mất quorum, strong operations có thể bị từ chối.
- Read eventual có thể stale trong phạm vi contract; strong read không trả sai.
- Sau restore, replicas hội tụ, metrics trở về mức chấp nhận.
- Không có request treo vô hạn vượt deadline.

### Artifact cần lưu

~~~text
run_id
fault_config
timeline
request_ids
client_observations
server_commit_log
replica_versions
metrics_before_during_after
reconciliation_report
cleanup_confirmation
~~~

**Không chỉ đưa screenshot dashboard xanh** làm bằng chứng một chaos test đạt yêu cầu.

## 47. Bài tập thực hành

### Bài 1 — Mất request hay mất ACK?

Client tạo đơn và nhận timeout. Hãy viết hai lịch: request không đến DB và DB đã commit nhưng ACK mất. Tại sao client không thể phân biệt chỉ từ timeout?

**Gợi ý:** cùng một quan sát có nhiều trạng thái server khả dĩ.

### Bài 2 — Retry không an toàn

Một endpoint `POST /orders` trừ tồn kho một lần mỗi request và không có idempotency key. Client timeout rồi retry ba lần. Nêu những số lần trừ tồn kho có thể xảy ra và cách bảo vệ.

**Gợi ý:** timeout không cho biết request nào đã commit; dùng dedupe/conditional update nguyên tử.

### Bài 3 — Gói vs request

Mạng được cấu hình 5% packet loss. Tại sao không thể kết luận 5% HTTP requests thất bại?

**Gợi ý:** TCP retransmission và mỗi request nhiều packets.

### Bài 4 — Lỗi một chiều

A gửi request tới B thành công, nhưng B→A bị drop toàn bộ. B có thể log gì và A thấy gì?

**Gợi ý:** B commit, A timeout.

### Bài 5 — RST và blackhole

Tại sao thử connection reset tức thời chưa bao phủ trường hợp đường mạng im lặng không gửi FIN/RST?

**Gợi ý:** half-open socket và timeout khác nhau.

### Bài 6 — Delay vs slow handler

Hai request đều mất 1 giây: một do RTT mạng, một do DB xử lý lâu. Hãy đề xuất metric và điểm fault injection để phân biệt.

**Gợi ý:** latency decomposition ở client, proxy và handler.

### Bài 7 — Quorum 2/3

Replica A, B phản hồi nhanh, C mất kết nối. Với một mô hình operation yêu cầu 2/3, operation có thể hoàn tất không? Điều gì còn phải xác minh ngoài số đếm?

**Gợi ý:** version, protocol và membership.

### Bài 8 — Minority partition

Ba replica bị chia 2–1. Một client yêu cầu strong write ở phía một node. Vì sao việc trả `unavailable` có thể là hành vi đúng?

**Gợi ý:** safety ưu tiên hơn việc xác nhận hai write xung đột.

### Bài 9 — Retry storm

Một service có ba tầng, mỗi tầng retry tối đa ba attempts. Tại sao số attempts tới DB có thể tăng rất lớn nếu tất cả cùng retry?

**Gợi ý:** chính sách retry có thể nhân lên qua tầng.

### Bài 10 — Jitter

Thiết kế exponential backoff có full jitter cho ba retries đầu với base=100 ms. Giải thích lợi ích của chọn delay ngẫu nhiên thay vì mọi client cố định 100/200/400 ms.

**Gợi ý:** tránh đồng bộ các đợt retry.

### Bài 11 — Deadline tổng

Client có total deadline 1,5 giây, per-attempt timeout 1 giây, backoff 500 ms. Sau attempt đầu timeout, còn bao nhiêu thời gian cho lần sau? Hệ nên làm gì khi thời gian còn lại quá ít?

**Gợi ý:** không vượt total budget.

### Bài 12 — Retry read sang replica stale

Read đầu từ A lỗi, driver chuyển sang C nhưng C chưa nhận write mới. Kết quả cũ có được phép không nếu API hứa eventual? Nếu hứa read-your-writes thì sao?

**Gợi ý:** xác định consistency contract.

### Bài 13 — Hot key

Một key bị 10.000 clients cập nhật; node chậm và tất cả retry. Vì sao tăng retry có thể làm throughput thành công giảm?

**Gợi ý:** queueing/retry amplification.

### Bài 14 — Toxiproxy

Vẽ sơ đồ client→proxy→DB. Nếu driver khám phá replica khác và kết nối thẳng, test qua proxy còn kiểm được toàn bộ traffic không?

**Gợi ý:** chỉ path đi qua proxy bị ảnh hưởng.

### Bài 15 — Netem

`tc qdisc ... netem loss 10%` trên egress interface lab ảnh hưởng chiều nào? Vì sao phải test cả request và response path?

**Gợi ý:** egress, asymmetric failure.

### Bài 16 — Sau restore

Node C offline trong lúc A/B ghi và xóa record. Khi C trở lại, nên kiểm những điều gì ngoài trạng thái UP?

**Gợi ý:** repair, tombstones, version convergence.

### Bài 17 — Java demo

Chạy `FaultRetryDemo.java`. Tại sao `req-B` retry cùng ID không làm tăng số order, nhưng `req-B-new` làm tăng?

**Gợi ý:** server dùng map idempotency theo requestId.

### Bài 18 — Code production khác demo

Trong Java demo, `synchronized` và `HashMap` giữ dedupe trong một JVM. Nếu server gồm ba instance và restart, cần những thay đổi gì?

**Gợi ý:** trạng thái durable, atomic commit/dedupe và xử lý đồng thời.

### Bài 19 — ACK sau commit

Tạo một fault hook đúng giai đoạn `AFTER_COMMIT_BEFORE_ACK`. Nêu expected invariant và các log fields cần ghi.

**Gợi ý:** một business intent, một side effect, outcome client có thể unknown.

### Bài 20 — Circuit breaker

Một circuit breaker OPEN khi một replica chậm. Vì sao failover read sang replica khác có thể hợp lý cho eventual read nhưng không tùy ý cho strong read?

**Gợi ý:** consistency và freshness phải được giữ.

### Bài 21 — Hedged request

Khi p99 cao, hệ gửi bản sao request read tới replica B. Hãy nêu hai lợi ích và ba rủi ro khi dùng hedging ở thời điểm cluster đã overload.

**Gợi ý:** giảm tail latency nhưng tăng QPS và rủi ro stale.

### Bài 22 — Slow leader

Leader vẫn heartbeat nhưng commit chậm. Những metrics nào giúp phân biệt replication lag, disk stall và election churn?

**Gợi ý:** commit index, per-replica lag, disk latency, term transitions.

### Bài 23 — Thí nghiệm có thể tái hiện

Hãy viết YAML test plan cho 10% packet loss một chiều, 60 giây, 1.000 point reads/s giả lập. Bao gồm baseline, source/destination, cleanup và abort conditions.

**Gợi ý:** lưu seed và chính xác đường bị lỗi.

### Bài 24 — Không vi phạm dữ liệu

Một API đặt ghế phải đảm bảo một ghế chỉ có một chủ. Test mất ACK sau commit rồi cho hai client retry đồng thời. Bạn sẽ đối soát invariant nào?

**Gợi ý:** kiểm toàn bộ committed state và idempotency records, không chỉ response.

### Bài 25 — Fault matrix

Lập bảng với ba loại fault: random loss, total connection blackhole, slow node. Cho mỗi loại nêu metrics, expected client exception và hành vi sau phục hồi.

**Gợi ý:** cùng một lỗi mạng có thể cho nhiều exception tùy timeout/protocol.

### Bài 26 — Business event duplication

Order service viết DB rồi publish event; ACK DB mất khiến client retry. Tại sao chỉ dedupe ở DB chưa chắc đủ nếu publish event ở một bước độc lập?

**Gợi ý:** outbox/transactional event handoff và consumer idempotency.

### Bài 27 — SLO và safety

Trong fault test, error rate tăng nhưng không có double booking và minority từ chối write. Tại sao đây có thể là kết quả safety đúng dù SLO availability bị ảnh hưởng?

**Gợi ý:** tách safety, liveness và performance.

### Bài 28 — Hệ NoSQL nhiều DC

Client ở DC-A ghi với local quorum, rồi read từ DC-B ngay khi WAN có 30% packet loss. Hãy phân biệt local write ACK, cross-DC replication lag và read freshness.

**Gợi ý:** không đồng nhất local commit với mọi remote replica đã nhận.

### Bài 29 — Client pool leak

Sau blackhole 30 giây, số connections tăng và không giảm sau restore. Hãy đề xuất metrics/giả thuyết để tìm leak.

**Gợi ý:** pool wait, open sockets, reconnect attempts và close-on-timeout.

### Bài 30 — Kế hoạch end-to-end

Thiết kế thí nghiệm cho 100 client tạo đơn, một coordinator chậm 2 giây, một replica bị drop response và client retry tối đa ba attempts. Ghi:

1. Fault target/chiều/độ dài.
2. Request IDs và các giai đoạn commit.
3. Retry budgets, deadlines và jitter.
4. Expected quorum behavior.
5. Invariants về đơn hàng/tồn kho.
6. Metrics và cách gỡ fault.
7. Reconciliation sau khi mạng phục hồi.

**Gợi ý:** mỗi yêu cầu hợp lệ được xác nhận phải ứng với một hiệu ứng nghiệp vụ; timeout có thể là unknown outcome.

## 48. Checklist trước khi kết luận test đạt

Một bài test mất gói/ngắt kết nối/slow node nên có câu trả lời cho:

1. Lỗi thực sự được tiêm ở **đường nào, chiều nào, tầng nào**?
2. Có baseline và workload tái hiện được không?
3. Loss rate được đo theo packet hay request?
4. Có thử lỗi **trước request** và **sau commit trước ACK** không?
5. Total deadline và per-attempt timeout được thực thi đúng không?
6. Retry có giới hạn, backoff và jitter không?
7. Có đo extra QPS do retries không?
8. Request ID có giữ ổn định qua retry không?
9. Dedupe ở server có atomic/durable đúng phạm vi không?
10. Có phân biệt error message với commit outcome không?
11. Có kiểm strong operations khi mất quorum không?
12. Có kiểm eventual reads và read-your-writes theo contract không?
13. Có thử network partition **bất đối xứng** không?
14. Có thử RST và silent blackhole riêng không?
15. Có thử slow handler/disk/GC ngoài network delay không?
16. Có quan sát connection pool, threads và in-flight requests không?
17. Có đo p95/p99 thay vì chỉ average không?
18. Có giám sát replication/repair lag sau restore không?
19. Có đối soát số business effects với intents không?
20. Có giới hạn blast radius và abort criteria rõ ràng không?
21. Có cleanup rule/proxy/namespace và xác minh traffic đã phục hồi không?
22. Có lưu fault seed/timeline/traces để tái hiện không?
23. Có ghi các giới hạn của kết quả thử nghiệm không?

Nếu chỉ ghi **“rút mạng một node rồi cluster vẫn chạy”**, chưa thể khẳng định retry đúng, không trùng dữ liệu hoặc read/write consistency được bảo vệ.

## 49. Tổng kết

Những điều quan trọng nhất khi **thử nghiệm mất gói, ngắt kết nối và nút phản hồi chậm**:

1. **Packet loss, connection reset, silent blackhole và slow response là những fault khác nhau.** Cần thử riêng theo nguồn, đích, chiều và tầng mạng.
2. **Timeout không nói chắc commit outcome.** Request có thể chưa tới server hoặc đã commit nhưng ACK mất. Lỗi thứ hai đặc biệt nguy hiểm khi tự retry writes.
3. **Idempotency phải được thực thi ở server/commit boundary.** Retry một ý định bằng request ID ổn định, có atomic/durable dedupe và kiểm payload mismatch theo contract.
4. **Retry có chi phí.** Thiết lập total deadline, max attempts, retry budget, exponential backoff/jitter và tránh nhiều tầng retry nhân tải lên nhau.
5. **Slow node có thể nguy hiểm hơn node chết rõ ràng.** Nó giữ resources, tạo p99 cao, kích hoạt retries và cascading failure.
6. **Quorum và partition quyết định khả năng phục vụ strong operations.** Phía thiếu quyền có thể phải từ chối ghi để bảo vệ safety.
7. **Tái kết nối chưa có nghĩa dữ liệu đã hội tụ.** Cần kiểm replication/repair, stale reads, tombstones và recovery time.
8. **Công cụ phải đúng lớp:** proxy test cho traffic đi qua proxy, `tc netem` cho packet-level ở interface lab, failpoints cho đúng ranh giới commit và Java simulator cho lịch deterministic.
9. **Đo cả safety, liveness và performance.** Một chaos test pass không chỉ là nhiều HTTP 200; cần kiểm invariant nghiệp vụ, p95/p99, duplicate effects và dữ liệu thực.
10. **Thí nghiệm phải kiểm soát được và có thể tái hiện.** Ghi workload, seed, fault config, timeline, cleanup và giới hạn kết luận.

**Nguyên tắc thực hành:** trước khi nói “client đã retry an toàn khi node chậm/mất kết nối”, hãy tạo hai lịch **request mất trước server** và **ACK mất sau commit**, sau đó chứng minh bằng trạng thái dữ liệu rằng **cả hai lịch đều kết thúc với đúng số hiệu ứng nghiệp vụ**. Tiếp theo mới mở rộng sang packet loss, network partition và các tình huống phục hồi của cluster NoSQL phân tán.
