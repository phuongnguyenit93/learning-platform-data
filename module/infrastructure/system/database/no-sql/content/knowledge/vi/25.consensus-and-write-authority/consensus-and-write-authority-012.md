# Đọc hợp đồng giao thức của sản phẩm trước khi thiết kế khóa hoặc điều phối

Một hệ thống phân tán thường phải trả lời những câu hỏi có vẻ đơn giản: **Ai được quyền xử lý đơn hàng này? Có thể bảo đảm hai worker không cùng thực hiện một tác vụ không? Một lệnh cập nhật có thật sự chỉ xảy ra một lần không? Nếu node giữ khóa mất mạng, worker còn lại có được tiếp quản không?** Nhiều nhóm phát triển bắt đầu bằng việc chọn một lệnh như `SET NX`, một compare-and-set (CAS), một TTL hoặc một API tạo lease, rồi xây quy trình nghiệp vụ xung quanh.

Cách làm đó dễ sai nếu chưa đọc **hợp đồng giao thức của sản phẩm** (*product/protocol contract*): nhà cung cấp **thực sự cam kết điều gì**, trong **phạm vi nào**, với **phiên bản, cấu hình, topology và điều kiện lỗi nào**. Một lệnh có tính nguyên tử trên một key không tự bảo đảm một quy trình nhiều hệ là nguyên tử. Một khóa có TTL không tự chặn worker cũ tiếp tục gửi lệnh sau khi lease đã hết hạn. Một response timeout không chứng minh write chưa được commit; một xác nhận từ replica không tự chứng minh dữ liệu đã tuyến tính toàn cục.

Trong chương **Đồng thuận và quyền ghi** của Database No SQL, bài học này hướng dẫn cách **đọc, chuyển hóa và kiểm chứng những bảo đảm chính thức** trước khi chọn kỹ thuật khóa hoặc điều phối công việc. Ta sẽ sử dụng một tình huống hai worker tranh quyền xử lý hóa đơn, sau đó phân tích CAS, leader election, lease, fencing, idempotency, retry, durability, failover và các ví dụ sản phẩm.

> **Nguyên tắc cốt lõi:** Không thiết kế một bất biến nghiệp vụ dựa trên bảo đảm mà API, driver và topology của sản phẩm **chưa từng hứa**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định **operation, phạm vi dữ liệu, fault model và cấu hình** cần xét khi đọc tài liệu kỹ thuật của một hệ NoSQL/coordination service.
2. Phân biệt ngữ nghĩa **atomicity, linearizability, serializability, durability, availability, lease, TTL, fencing, lock ownership và fairness**.
3. Chuyển phát biểu của tài liệu thành một bảng **assumption → guarantee → giới hạn → điều kiện áp dụng → phép kiểm chứng**.
4. Nhận diện lỗ hổng của distributed lock khi có **GC pause, partition, timeout, lease expiry, failover và stale holder**.
5. Biết khi nào **conditional write/CAS** phù hợp hơn distributed lock.
6. Giải thích vì sao **fencing token phải được tài nguyên đích thực thi**, không chỉ được khóa cấp phát.
7. Thiết kế **idempotency key, deduplication và reconciliation** cho operation có kết quả commit không rõ.
8. So sánh mang tính nguyên tắc các hợp đồng của **Redis, MongoDB, DynamoDB, Cassandra, etcd và ZooKeeper**, tránh suy diễn khả năng không được bảo đảm.
9. Xác định **đọc chính thức ở đâu**, câu nào cần xác minh theo phiên bản và dạng test nào phù hợp với từng claim.
10. Tạo một checklist design review giúp lựa chọn khóa/điều phối theo **bất biến cần bảo vệ**, không theo cú pháp API có vẻ tiện.

## 2. Tình huống xuyên suốt: hai worker cùng xử lý một hóa đơn

Giả sử một hệ thống tạo hóa đơn hàng tháng cho tenant. Tác vụ `generateInvoice(tenantId, period)` không được tạo hai hóa đơn cuối cùng cho cùng kỳ và không được ghi đè kết quả mới bằng một tiến trình cũ.

Ban đầu hệ thống dùng khóa có hạn:

~~~text
Lock key: invoice-lock:tenant-a:2026-11
Lease duration: 30 giây

Worker A -> acquire lock -> SUCCESS
Worker A -> tính toán hóa đơn
Worker A -> ghi kết quả và giải phóng lock
~~~

Trong môi trường đơn giản, logic có vẻ ổn. Nhưng một lịch khác:

| Thời điểm giả định | Worker A | Worker B | Khóa/nguồn dữ liệu |
| --- | --- | --- | --- |
| 12:00:00 | Lấy lock thành công, lease 30 s | — | Holder A |
| 12:00:05 | Đọc dữ liệu, bắt đầu tính | — | Holder A |
| 12:00:08 | Bị dừng do GC pause/VM suspend | — | Holder A |
| 12:00:30 | Vẫn chưa chạy lại | — | Lease A hết hạn |
| 12:00:31 | — | Lấy lock thành công | Holder B |
| 12:00:34 | — | Ghi hóa đơn phiên bản mới | Kết quả B |
| 12:00:40 | Tiếp tục chạy, tưởng vẫn có lock | — | A gửi ghi cũ |
| 12:00:41 | Ghi có thể đè kết quả B nếu storage không kiểm tra | — | **Sai bất biến** |

Điểm khó không nằm ở việc lệnh *acquire* có nguyên tử hay không. Ngay cả khi **mỗi thời điểm chỉ có một lease còn hiệu lực**, Worker A vẫn có thể giữ **ý định ghi cũ** và gửi tới tài nguyên đích **sau khi hết quyền**.

### 2.1. Những câu hỏi phải hỏi trước khi code

- Tài liệu nói khóa có thời hạn theo **đồng hồ phía nào**?
- Acquire có **nguyên tử** không, và với **một key hay nhiều key**?
- Lock có thể bị mất khi **node failover** không?
- Lease expiry có chặn process cũ gọi API khác không?
- Renew thất bại thì worker có biết chắc **đã mất quyền** không?
- Có **fencing token tăng đơn điệu** được cấp theo thứ tự quyền sở hữu không?
- **Database lưu hóa đơn** có từ chối ghi từ token cũ không?
- Nếu ghi thành công nhưng response mất, retry có thể tạo hóa đơn thứ hai không?
- Nghiệp vụ thực sự cần **một worker duy nhất** hay chỉ cần **một kết quả được commit hợp lệ**?

Câu hỏi cuối rất quan trọng: đôi khi một **conditional insert có khóa duy nhất** đủ bảo vệ kết quả, còn distributed lock chỉ làm tăng số thành phần và failure modes.

## 3. “Hợp đồng giao thức” cụ thể là gì?

Trong bài này, **hợp đồng giao thức** là tập hợp những bảo đảm và điều kiện được định nghĩa qua:

1. **Tài liệu API chính thức:** Phương thức nào, input/output nào, lỗi nào, precondition nào?
2. **Mô hình nhất quán:** Operation tuyến tính, eventual, causal, snapshot hay chỉ bảo đảm cục bộ?
3. **Phạm vi nguyên tử:** Một key, một document, một partition, một transaction hay nhiều region?
4. **Replication/commit/durability:** ACK có nghĩa đã ghi ở đâu, quorum nào và dưới điều kiện failover nào?
5. **Lease/lock semantics:** Acquire, renew, expire, release, session expiry, ordering và quyền ghi.
6. **Client/driver contract:** Retry tự động, timeout, idempotency, redirect, failover behavior, error classification.
7. **Topology và cấu hình:** Một instance, replica set, cluster, một region hay multi-region; read/write concern hoặc consistency mode.
8. **Phiên bản và giới hạn:** Tính năng có mặt từ version nào, có ngoại lệ hoặc hạn chế nào?

Không có một file duy nhất lúc nào cũng gọi là “protocol contract”. Nó thường nằm rải rác trong **API Reference, Consistency Model, Transactions, Replication, Failure Recovery, Client SDK, Locking, Migration Notes và Known Limitations**.

### 3.1. Một câu trong docs có thể có điều kiện ẩn trong đoạn kế

Giả sử tài liệu nói:

> “Conditional writes are atomic on an item.”

Không được tự diễn giải thành:

> “Một lệnh điều kiện trên item A và một HTTP call thanh toán bên ngoài sẽ commit nguyên tử với nhau.”

Muốn dùng claim đầu tiên, phải xác định:

- Item là đơn vị nào?
- Có áp dụng qua multi-region replicas không?
- Lệnh có nhận điều kiện từ một read trước đó không, hay server kiểm tra điều kiện atomically tại commit?
- Error/timeout có chứng minh không commit không?
- Nếu thao tác nhiều item, API nào và giới hạn nào?

**Đọc một câu khẳng định mà bỏ phạm vi/điều kiện là cách nhanh nhất để thiết kế sai.**

### 3.2. Bảng phân tầng mức độ tin cậy của thông tin

| Nguồn | Dùng để làm gì | Cảnh báo |
| --- | --- | --- |
| Tài liệu API và consistency model chính thức, đúng version | Xác định bảo đảm được công bố | Đọc mọi điều kiện và ngoại lệ |
| Design/specification của giao thức | Hiểu invariants, term/epoch, failure model | Phân biệt thiết kế lý thuyết với triển khai |
| Client SDK docs/release notes | Hiểu retry, timeout, failover, phiên bản | Driver có thể thay semantics quan sát |
| Official operational guide | Cấu hình quorum, persistence, topology | Bảo đảm đổi khi config đổi |
| Test và chaos lab | Phát hiện lỗi thực tế, kiểm nghiệm giả định | Test pass không tự chứng minh mọi lịch |
| Blog/talk/tutorial | Tạo trực giác và phương án | Không thay thế contract chính thức |
| Benchmark/marketing | Biết throughput/latency trong setup mẫu | Không phải correctness guarantee |

### 3.3. Contract theo phiên bản và cấu hình

Một phát biểu hữu ích phải đi kèm:

~~~yaml
product: "product-name"
version: "exact version or supported range"
clientSdk: "name and version"
deploymentMode: "single-node | replica-set | cluster | multi-region"
writeConfiguration: "write concern / consistency mode"
readConfiguration: "read concern / consistency mode"
failureModel:
  - "process crash"
  - "node restart"
  - "network partition"
  - "leader failover"
operation:
  api: "conditional update"
  scope: "one item"
assumedGuarantee: "condition checked atomically at commit"
officialSource: "document title + section + version"
openQuestions:
  - "timeout outcome"
  - "cross-region concurrent writers"
~~~

Đây là **mẫu ghi chép design review**, không phải cấu hình của một sản phẩm cụ thể.

## 4. Bắt đầu từ bất biến nghiệp vụ, không bắt đầu từ tên công cụ

Trước khi đọc docs của `SET NX` hay `CompareAndSwap`, hãy viết **bất biến cần bảo vệ**.

### 4.1. Bất biến về kết quả

Ví dụ:

~~~text
Mỗi (tenantId, invoicePeriod) có tối đa một invoice FINAL.
~~~

Một giải pháp có thể dùng **unique key + conditional insert**, không cần bảo đảm chỉ một worker từng chạy code tính toán. Có thể có hai worker tính cùng một hóa đơn, nhưng **chỉ một kết quả được commit**.

### 4.2. Bất biến về hành động bên ngoài

Ví dụ:

~~~text
Mỗi invoice chỉ được capture payment một lần.
~~~

Một lock trong NoSQL không thể làm **HTTP call sang payment gateway** trở thành giao dịch nguyên tử với database. Cần idempotency tại payment API, request ID, trạng thái workflow và reconciliation.

### 4.3. Bất biến về thứ tự chủ sở hữu

Ví dụ:

~~~text
Worker với generation cũ không được ghi đè kết quả
được worker generation mới đã commit.
~~~

Đây là chỗ **fencing token** phù hợp nếu tài nguyên đích hỗ trợ kiểm tra token theo thứ tự quyền sở hữu.

### 4.4. Bất biến về tiến độ

Ví dụ:

~~~text
Khi worker giữ quyền chết, một worker khác phải
có thể tiếp quản sau một khoảng chấp nhận được.
~~~

Nếu chỉ tạo một lock vĩnh viễn mà không có cơ chế phục hồi, hệ có thể giữ safety nhưng mất **liveness**.

### 4.5. Bảng chọn primitive theo yêu cầu

| Bất biến/nhu cầu | Primitive cần xem trước | Cần kiểm tra thêm |
| --- | --- | --- |
| Một document không bị lost update | CAS/version conditional update | Atomic scope, retry, read version |
| Unique invoice theo tenant+period | Unique key/conditional insert | Uniqueness scope trong sharding |
| Worker takeover sau crash | Lease/queue visibility/session | Expiry, redelivery, fencing |
| Không cho stale worker ghi | Monotonic fencing token + guarded destination | Token được sinh và kiểm tra ở đâu |
| Chỉ một leader trong mỗi term | Leader election/quorum | Term, majority, partition policy |
| Không xử lý trùng sau timeout | Idempotency key + dedup record | Atomic commit với business effect |
| Nhiều item cùng commit | Transaction trong phạm vi được hỗ trợ | Isolation, read/write sets, conflict |
| Thực hiện side effect ngoài DB | Outbox/inbox, saga, idempotent external API | Exactly-once scope, reconciliation |

**Nếu một conditional write tại nguồn dữ liệu đã bảo vệ được invariant, không mặc định distributed lock là lớp an toàn bắt buộc.**

## 5. Bảng thuật ngữ trước khi đọc tài liệu sản phẩm

| Thuật ngữ | Ý nghĩa kiểm chứng | Điều không được suy ra |
| --- | --- | --- |
| **Atomic operation** | Operation có hiệu lực theo một đơn vị nguyên tử cụ thể | Toàn workflow nhiều service nguyên tử |
| **Linearizability** | Có thể đặt operation vào thứ tự tuyến tính tôn trọng thời gian thực | Mọi transaction đa key đều serializable |
| **Serializability** | Kết quả transaction tương đương lịch tuần tự | Tự có thứ tự thời gian thực |
| **Strict serializability** | Serializable và tôn trọng thứ tự thời gian thực | Mọi replica stale read cũng strong |
| **Durability** | Dữ liệu đã commit có bảo đảm sống sót qua lỗi được định nghĩa | Mọi ACK ở mọi config đều không thể rollback |
| **Availability** | Operation còn phục vụ dưới fault model đã chọn | Không bao giờ timeout |
| **Idempotency** | Cùng logical operation lặp lại không đổi kết quả ngoài một lần theo contract | Tự giải quyết concurrent operations khác ID |
| **CAS/conditional write** | Cập nhật chỉ khi điều kiện đúng tại điểm atomicity | Transaction bên ngoài DB được bảo vệ |
| **Lock** | Quyền truy cập mang tính loại trừ theo quy tắc nhất định | Stale holder không bao giờ chạy tiếp |
| **Lease** | Quyền có thời hạn cần renew theo giao thức | Process bị OS tự dừng khi lease expire |
| **Fencing token** | Thế hệ quyền sở hữu có thứ tự, dùng để chặn holder cũ | Token giúp ích nếu destination không kiểm tra |
| **TTL** | Chính sách thời hạn tồn tại hoặc cleanup | Xóa chính xác tức thời hoặc cấp thứ tự fencing |
| **Quorum** | Số/nhóm replica cần tham gia một quyết định | Mọi cấu hình R+W đều linearizable |
| **Leader term/epoch** | Thế hệ quyền điều phối/leadership | Document version hoặc wall-clock timestamp |
| **Watch/notification** | Tín hiệu có thay đổi | Mọi event đều được nhận chính xác một lần |
| **Fairness** | Chính sách ưu tiên waiter/không bỏ đói | Lock nguyên tử mặc nhiên FIFO |

### 5.1. Atomicity có scope

Nếu docs hứa **atomic update của một document**, hãy tìm câu trả lời cho:

~~~text
Atomic on which document?
Does condition evaluate at commit?
What happens across shards?
Are external HTTP effects included?
How are timeout and retries handled?
~~~

Một operation mạnh trong phạm vi **một item** không tự mở rộng thành một transaction xuyên **nhiều item, nhiều region hoặc nhiều dịch vụ**.

### 5.2. Consistency khác durability

Một giá trị có thể được đọc nhất quán trong lúc hệ hoạt động nhưng vẫn bị mất sau crash nếu ACK chưa tương ứng với durability mong muốn. Ngược lại, nhiều bản durable không tự bảo đảm read từ một replica bất kỳ thấy bản mới nhất.

**Bảo đảm nào thuộc read ordering? Bảo đảm nào thuộc crash recovery?** Phải đọc riêng hai hợp đồng.

### 5.3. Lock acquisition khác lock ownership trong suốt tác vụ

`acquire() -> SUCCESS` có nghĩa tại **một thời điểm** worker được nhận quyền theo protocol. Nó không nói rằng worker luôn còn quyền cho đến khi logic của ứng dụng hoàn tất, đặc biệt nếu có TTL/lease, pause hoặc partition.

## 6. Mô hình lỗi và câu hỏi về quyền ghi

Một bản design review nên phân tích ít nhất:

1. **Process crash:** Worker đang giữ lock chết.
2. **Stop-the-world pause:** Worker không chạy trong 45 giây dù lease chỉ 30 giây.
3. **Network partition:** Worker còn sống nhưng không liên lạc được với lock service.
4. **Lock service failover:** Primary mất, replica tiếp quản.
5. **Slow network/timeout:** Request có thể commit nhưng response đến muộn hoặc mất.
6. **Concurrent acquire:** Hai worker cùng xin quyền.
7. **Session expiry:** Coordination service coi session đã hết, nhưng worker ứng dụng vẫn chạy.
8. **Clock drift:** Đồng hồ client và server không trùng nhau.
9. **Partial workflow failure:** DB update xong, external API chưa xong hoặc ngược lại.
10. **Stale read:** Worker kiểm tra lock/status từ replica trễ.

### 6.1. Không thể đoán node đã chết từ timeout

Một request renew lease timeout có thể là:

~~~text
Renew không tới server.
Renew đã tới nhưng bị từ chối vì lease hết.
Renew đã thành công nhưng response bị mất.
~~~

Client có thể không biết chắc trạng thái quyền sở hữu. Trong trường hợp quyền không thể xác minh, **không được tự tiếp tục side effect nhạy cảm dựa vào suy đoán “chắc còn khóa”**.

### 6.2. Safety và liveness

**Safety:** Điều xấu không bao giờ xảy ra, ví dụ hai owner có quyền ghi xung đột.

**Liveness:** Cuối cùng hệ vẫn tiến lên, ví dụ worker khác có thể nhận tác vụ sau crash.

Lease thường cải thiện takeover/liveness nhưng làm phát sinh **stale holder problem**. Lock không hết hạn có thể giữ quyền dài hơn mong muốn sau crash. Một thiết kế phải nêu **cả hai**.

## 7. Lịch H1: lease hết hạn nhưng worker cũ vẫn ghi

Giả sử một service cho lease 30 giây, độ trễ và pause được tính theo thời gian thực trong ví dụ:

| Thời điểm UTC | Worker A | Worker B | Resource |
| --- | --- | --- | --- |
| 12:00:00 | Acquire lease generation 71 | — | Owner A |
| 12:00:08 | Bị pause 34 giây | — | Lease tiếp tục chạy |
| 12:00:30 | Chưa chạy lại | — | Generation 71 hết hạn |
| 12:00:31 | — | Acquire lease generation 72 | Owner B |
| 12:00:35 | — | Ghi `invoice=NEW` | State B |
| 12:00:42 | Resume, ghi `invoice=OLD` | — | **Nguy cơ ghi đè** |

Nếu destination chỉ nhận:

~~~text
PUT /invoice-result {value: "OLD"}
~~~

nó không biết request đến từ holder cũ. Một lock service có thể đã làm đúng hợp đồng lease, nhưng **ứng dụng vẫn sai** vì tưởng lock expiry sẽ tự dừng chương trình cũ.

### 7.1. Fencing token tăng theo thế hệ ownership

Giả sử lock/coordination protocol phát token có thứ tự:

~~~text
Worker A receives fencingToken = 71.
Worker B receives fencingToken = 72.
~~~

Mọi mutation gửi tới **tài nguyên đích** kèm token, và destination thực thi quy tắc:

~~~text
Reject a write whose fencingToken is lower than
the highest generation already accepted.
~~~

Trong lịch:

~~~text
B writes with 72 -> ACCEPT, maxSeenToken=72.
A resumes with 71 -> REJECT.
~~~

Điểm quan trọng: token chỉ có tác dụng nếu **destination tự so và từ chối**. Tạo số tăng ở lock service rồi chỉ ghi nó vào log không ngăn A ghi đè.

### 7.2. Vì sao check `stillOwnLock()` trước khi ghi chưa đủ?

~~~text
T1: A gọi stillOwnLock() -> true.
T2: A bị pause.
T3: Lease hết hạn, B lấy quyền và commit.
T4: A resume, gửi PUT.
~~~

Kiểm tra quyền và gửi PUT là **hai operation khác nhau**; quyền có thể mất ở giữa. Đó là race kiểu **time-of-check to time-of-use (TOCTOU)**. Cần điều kiện được **cưỡng chế tại ranh giới ghi**, không chỉ ở kiểm tra trước.

### 7.3. Token cần thứ tự thật, không phải timestamp tùy ý

Nếu A/B tạo token bằng `System.currentTimeMillis()` trên hai máy:

- Clock skew có thể làm worker cũ có số “lớn hơn” worker mới.
- Đồng hồ có thể chỉnh ngược.
- Hai owner có thể nhận timestamp trùng.

Token fencing cần **thứ tự phù hợp với quyền sở hữu** do cơ chế phối hợp đáng tin tạo ra. Không lấy random UUID hoặc timestamp cục bộ rồi gọi chúng là **monotonic fencing tokens**.

### 7.4. Fencing không giải quyết mọi side effect

Nếu destination là payment provider **không hỗ trợ kiểm tra fencing token**, token 72 không thể tự hủy một HTTP request do A đã gửi trước đó. Cần thêm **idempotency ở đích, workflow state, reconciliation**, hoặc thiết kế mọi external call đi qua một authority thực thi được invariant.

## 8. CAS/conditional write: đôi khi là giải pháp ngắn và mạnh hơn lock

Giả sử business invariant là:

~~~text
Invoice (tenantId, period) chỉ được chuyển
từ NEW sang FINAL đúng một lần.
~~~

Một worker có thể gửi lệnh điều kiện:

~~~text
UPDATE invoice
SET state=FINAL, result=...
WHERE tenantId=... AND period=... AND state=NEW
~~~

Nếu database **atomically** kiểm tra và thay đổi cùng record, chỉ một trong hai write tranh chấp có thể thắng, tùy contract.

### 8.1. So sánh hai cách

**Cách dùng lock ngoài DB:**

~~~text
Acquire lock -> Read invoice -> Compute -> Save invoice -> Release lock
~~~

Phải xử lý lease, renew, stale owner, timeout, network giữa lock service và DB.

**Cách conditional update tại source:**

~~~text
Compute candidate ->
Compare-and-set state NEW -> FINAL
~~~

Có thể cho nhiều worker cùng compute nhưng chỉ một kết quả được commit. Nếu compute là side effect đắt tiền hoặc phải ngăn nhiều external calls, cần phân tích thêm; conditional update không tự bảo vệ phần công việc xảy ra **trước khi commit**.

### 8.2. Optimistic concurrency control (OCC)

Một mẫu khác:

~~~text
Read document version = 17.
Compute change.
UPDATE only if version = 17.
If success: version = 18.
If conflict: re-read and decide.
~~~

Nếu version 17 đã bị worker khác update, lệnh điều kiện phải từ chối. **Từ chối xung đột là kết quả đúng**, không được tự retry bằng cách cập nhật version mới mà không xét lại intent.

### 8.3. Không trộn atomicity của một item với nghiệp vụ nhiều item

Ví dụ:

~~~text
Decrement inventory item
AND
Create order item
AND
Capture payment externally
~~~

Một CAS trên inventory không khiến ba bước này trở thành một transaction. Cần xem transaction scope, saga/outbox, idempotency và compensation.

## 9. Unknown commit outcome và idempotency

Lịch:

| Thời điểm | Sự kiện |
| --- | --- |
| 12:10:00.000 | Client gửi `reserve(requestId=R42)` |
| 12:10:00.250 | Server commit reservation |
| 12:10:00.260 | Response bị mất |
| 12:10:00.800 | Client timeout |

Timeout **không chứng minh reserve chưa thực thi**. Nếu client retry bằng một request ID mới, có thể tạo hai reservation.

### 9.1. Logical request ID so với network attempt ID

~~~text
logicalOperationId = R42
attempt 1: gửi, timeout
attempt 2: retry, cùng R42
~~~

Server có thể giữ ledger:

~~~json
{
  "operationId": "R42",
  "payloadHash": "hash-of-canonical-request",
  "status": "SUCCEEDED",
  "reservationId": "RES-901",
  "resultVersion": 18
}
~~~

Khi nhận lại `R42` cùng payload, hệ có thể trả kết quả đã ghi thay vì trừ stock thêm lần nữa. Request ID phải đủ ổn định và uniqueness trong **phạm vi nghiệp vụ**; cùng ID nhưng payload khác phải bị xử lý như conflict, không được xem là request tương đương.

### 9.2. Cập nhật business effect và dedup record phải gắn kết

Nguy hiểm:

~~~text
T1: decrement stock.
T2: process crash.
T3: chưa ghi dedup ledger.
T4: client retry R42 -> decrement lần nữa.
~~~

Phải dùng transaction/conditional protocol phù hợp hoặc workflow có thể phục hồi để đạt **atomicity/consistency cần thiết giữa business effect và bản ghi chống trùng**.

### 9.3. “Exactly once” luôn cần nói rõ scope

Một sản phẩm có thể hứa một message được deliver một lần **trong phạm vi hệ hoặc API xác định**, nhưng điều đó không tự đồng nghĩa:

~~~text
Exactly once:
  dequeue event
  + update database
  + call third-party HTTP service
  + send email
~~~

Nếu các hệ không có một giao thức commit chung, cần idempotent consumers, outbox/inbox, deduplication và reconciliation. Đừng dùng từ “exactly once” không kèm **phạm vi và failure model**.

## 10. Một phương pháp đọc tài liệu giao thức theo 7 bước

Đừng chỉ tìm Google với cụm “distributed lock in X”. Hãy bắt đầu từ một **vấn đề có thể kiểm chứng** và tìm bảo đảm cần thiết trong tài liệu chính thức.

### Bước 1 — Viết operation và invariant

Ví dụ:

~~~text
Operation: finalizeInvoice(tenantId, period)
Invariant: At most one FINAL invoice per tenant-period.
Failure model: worker pause, crash, network timeout, DB failover.
~~~

Tách **invariant cần bảo vệ** khỏi giải pháp đã hình dung. Không bắt đầu bằng “ta cần Redis lock” khi chưa chứng minh cần lock.

### Bước 2 — Xác định boundary

Chỉ rõ phạm vi:

~~~text
One Redis key?
One MongoDB document?
One DynamoDB item?
One Cassandra partition/LWT?
One etcd key/transaction?
One ZooKeeper znode/session?
One database shard?
Cross-region?
External payment gateway?
~~~

Nếu operation nghiệp vụ đi qua nhiều boundary, bảo đảm của primitive trên một boundary **không tự phủ qua các boundary còn lại**.

### Bước 3 — Khoanh vùng phiên bản/cấu hình/topology

Ví dụ:

~~~text
Engine version: fixed
Driver version: fixed
Deployment: single instance / replica set / cluster
Replication: mode and number of replicas
Read consistency: chosen setting
Write acknowledgment/durability: chosen setting
Failover and cross-region mode: enabled/disabled
~~~

Nếu tài liệu nói “strongly consistent read được hỗ trợ” nhưng ứng dụng đang đọc qua một loại index/region không hỗ trợ mode đó, claim ấy **không áp dụng**.

### Bước 4 — Đọc phát biểu chuẩn kèm ngoại lệ

Ghi nguyên **ý nghĩa ngắn gọn**, liên kết tới tài liệu chính thức, tiêu đề mục và điều kiện:

| Claim cần xác minh | Tìm trong docs | Câu hỏi phụ |
| --- | --- | --- |
| Conditional write atomic | API Reference / Transactions | Scope một item hay nhiều item? |
| Lock acquire atomic | Commands / Locking Guide | Một key/một leader/multi-node? |
| Lease expire | Lease / Session Documentation | Clock nào, cơ chế thu hồi quyền? |
| Failover durability | Replication / Persistence | ACK có thể rollback không? |
| Strong read | Consistency / Read Concern | Đường đọc nào hỗ trợ? |
| Cross-region semantics | Global Replication | Concurrent writer xử lý conflict ra sao? |
| Retryability | Client Driver / SDK | Retry được những lỗi nào? |

Không nên lấy một ví dụ tutorial làm bằng chứng sản phẩm cam kết mọi case.

### Bước 5 — Ghi *negative space*: tài liệu không hứa gì?

Ví dụ tài liệu chỉ xác nhận:

> “SET key với tùy chọn không ghi đè và thời hạn là thao tác nguyên tử trong một instance.”

Các điều **chưa được chứng minh**:

- Lock sống sót qua failover như một transaction consensus?
- Worker bị stop-the-world pause có bị chặn ghi external resource?
- Lock release luôn chỉ xóa của chính owner không?
- Acquire có FIFO/fairness không?
- Multi-key business workflow có atomic không?
- Token cấp từ khóa có tăng đơn điệu theo từng lần đổi owner không?

**Thiếu bảo đảm công khai không tự động có nghĩa sản phẩm sai.** Nó có nghĩa design chưa được phép **dựa vào giả định đó** nếu chưa có nguồn hoặc một lớp giao thức bổ sung.

### Bước 6 — Chuyển claim thành test có thể quan sát

Ví dụ claim:

~~~text
After lease expires, stale worker cannot overwrite
an accepted write by a newer owner.
~~~

Test:

1. Cho A acquire generation 71.
2. Pause A lâu hơn lease.
3. B acquire generation 72.
4. B commit kết quả mới.
5. Resume A và cho nó gửi write cũ.
6. Quan sát destination: A bị reject hay đã ghi đè?

**Test pass không chứng minh mọi lịch lỗi**, nhưng có thể phát hiện nhanh một giả định sai và hỗ trợ kiểm nghiệm implementation.

### Bước 7 — Ghi quyết định, giới hạn và owner

Mẫu:

~~~yaml
decisionId: invoice-finalization
businessInvariant: "one FINAL per tenant-period"
chosenPrimitive: "conditional insert at authoritative record"
productVersion: "specific supported release"
clientVersion: "specific supported release"
supportedGuarantee: "atomic condition check on one record"
unsupportedAssumptions:
  - "no cross-service atomic commit"
  - "network timeout is not proof of no commit"
applicationSafeguards:
  - "unique idempotency key"
  - "reconciliation for external payment"
verification:
  - "concurrent finalize"
  - "crash after server commit"
owner: "team responsible for design"
reviewTrigger:
  - "upgrade"
  - "switch to multi-region"
  - "change consistency settings"
~~~

Đây là tài liệu thiết kế để team review, không phải cú pháp chạy của một database.

## 11. Redis: đọc chính xác hợp đồng của lệnh trước khi dùng khóa

Redis thường xuất hiện trong tutorial vì có các primitive gọn. Nhưng phải phân biệt **một lệnh nguyên tử trên một instance**, **replication/failover**, và **workflow bên ngoài Redis**.

### 11.1. Khóa với SET NX PX

Mẫu cú pháp minh họa:

~~~redis
SET invoice-lock:tenant-a:2026-11 4b8d3f... NX PX 30000
~~~

Ý nghĩa hướng tới:

- `NX`: Chỉ thiết lập key nếu key chưa tồn tại.
- `PX 30000`: Gắn thời gian hết hạn theo mili giây.
- Value chứa **token ngẫu nhiên duy nhất của owner** để tránh xóa khóa của worker khác.

Một lệnh có thể tránh race “`GET` rồi `SET`” trên **cùng key tại instance xử lý lệnh**, nhưng **không tự bảo đảm** worker cũ không chạy tiếp sau expiry, hoặc hệ có khả năng phục hồi theo mọi lỗi failover.

### 11.2. Không release bằng DEL vô điều kiện

Lịch lỗi:

~~~text
A holds value=tokenA, lease expires.
B acquires value=tokenB.
A resumes and runs DEL lockKey.
=> A xóa lock của B.
~~~

Cần **compare owner token rồi delete atomically**, chẳng hạn một script/lệnh CAS được hỗ trợ ở sản phẩm/phiên bản đang dùng.

Pseudocode Lua:

~~~lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
~~~

Script bảo vệ **release nhầm lock của owner khác** trên instance xử lý, nhưng **không tự tạo fencing** cho hệ ghi hóa đơn bên ngoài Redis.

### 11.3. Renew cũng phải kiểm tra ownership

Một cách làm sai:

~~~text
PEXPIRE lockKey 30000
~~~

nếu không xác minh value có còn là token của mình. Worker A có thể vô tình gia hạn lock của B.

Phải dùng operation **check token và renew atomically** theo contract phù hợp; đồng thời hiểu rằng renew timeout vẫn có thể tạo **unknown lease state**. Khi quyền không chắc chắn, worker không nên tiếp tục tác động nhạy cảm mà không có fencing tại đích.

### 11.4. Redis replication/failover

Redis có các mô hình primary–replica và persistence theo cấu hình; ứng dụng không được tự suy rằng:

~~~text
SET NX success on one primary
=> no other primary can ever grant the same lock
   under all network partitions and failovers.
~~~

Nếu replication bất đồng bộ và failover xảy ra trước khi lock được tái tạo trên replica tiếp quản, có thể phát sinh các lịch không khớp với giả định lock duy nhất. Cần đọc **replication, failover, durability, write acknowledgement và consistency guarantees** của topology đang triển khai.

### 11.5. WAIT / persistence không tự là consensus

Một số lệnh/cấu hình có thể tăng mức xác nhận replica hoặc durability. Nhưng **ack từ replica** không tự tương đương một consensus transaction có linearizability và fencing đối với external storage.

Phải xem chính xác lệnh bảo đảm gì, phản hồi nghĩa là gì và khi failover có trường hợp mất write đã ack không.

### 11.6. Redlock: không biến tên thuật toán thành kết luận

Redis có tài liệu về distributed locks nhiều instance và một số thuật toán như Redlock. Khi đánh giá cho nghiệp vụ nhạy cảm:

- Đọc đầy đủ các **giả định về thời gian, đa số, độ trễ, clock drift, thời hạn lease và failure behavior** của thuật toán.
- Phân biệt safety mà giao thức công bố với điều ứng dụng muốn bảo vệ.
- Xem tác động của client pause/stale holder và yêu cầu fencing tại destination.
- Không xem “acquire majority succeeded” là chứng minh external resource sẽ từ chối writer cũ.

Với invariant khó bồi thường, thiết kế có thể đơn giản hơn khi dùng **conditional write tại nguồn authoritative** hoặc một coordination service có giao thức nhất quán thích hợp, rồi bổ sung fencing/transaction trong phạm vi cần.

### 11.7. Checklist Redis

| Câu hỏi đọc docs | Vì sao quan trọng |
| --- | --- |
| Lệnh `SET NX PX` được bảo đảm trong phạm vi nào? | Atomic acquire |
| Expiry do server xử lý thế nào? | Lease semantics |
| Release/renew kiểm tra owner token atomically không? | Không phá khóa của người khác |
| Redis chạy standalone, Sentinel hay Cluster? | Failover/topology |
| ACK và replication nghĩa là gì? | Durability/safety dưới lỗi |
| Node restart hoặc network split có thể gây double ownership không? | Lock protocol |
| Đích dữ liệu có fencing không? | Stale holder |
| Retry sau timeout có idempotent không? | Unknown outcome |

## 12. MongoDB: conditional update, uniqueness và transaction scope

Khi tác vụ cần bảo vệ kết quả trên một document, MongoDB thường có thể dùng điều kiện ngay tại lệnh cập nhật thay cho lock riêng.

### 12.1. Claim cần đọc: atomicity của single-document mutation

Giả sử collection `invoices` có một document cho mỗi tenant+period:

~~~javascript
{
  tenantId: "tenant-a",
  period: "2026-11",
  state: "NEW",
  version: 17
}
~~~

Một lệnh minh họa:

~~~javascript
db.invoices.findOneAndUpdate(
  {
    tenantId: "tenant-a",
    period: "2026-11",
    state: "NEW",
    version: 17
  },
  {
    $set: { state: "FINAL", totalVnd: 1250000 },
    $inc: { version: 1 }
  },
  { returnDocument: "after" }
);
~~~

Nhóm cần đọc tài liệu phiên bản đang dùng để xác minh **atomic scope của single-document update** và ngữ nghĩa lệnh trả kết quả. Với condition kiểm tra ở server tại mutation, một worker thứ hai có thể không còn match `state=NEW,version=17`.

### 12.2. Không bỏ qua unique index

Nếu hai worker cùng cố **insert** document cho tenant+period, một conditional update trên document chưa tồn tại không tự bảo vệ unique business key. Có thể cần unique index theo:

~~~javascript
db.invoices.createIndex(
  { tenantId: 1, period: 1 },
  { unique: true }
);
~~~

Tuy nhiên trong **sharded collection**, các hạn chế về unique index và shard key cần được đọc theo **phiên bản/topology chính thức**. Không mặc định uniqueness cục bộ của một shard luôn bảo đảm global uniqueness.

### 12.3. Transaction nhiều document

Nếu finalization phải cập nhật cả `invoices` và `invoiceJobs`, cần xem MongoDB transactions, isolation, write/read concern, retry và commit outcome trong phạm vi hỗ trợ.

Không kéo một payment gateway HTTP bên ngoài vào transaction bằng cách gọi nó giữa hai MongoDB commands rồi tự gọi tổng thể đó là atomic.

### 12.4. TTL indexes không phải hệ khóa hết hạn chính xác tức thời

MongoDB có TTL indexes phục vụ cơ chế dọn document hết hạn theo quá trình background. **Không dùng việc document TTL chắc chắn đã bị xóa đúng giây X** làm nền tảng cho một protocol lease/ownership nếu tài liệu không cam kết điều đó.

Nếu cần lease, phải định nghĩa cách condition kiểm tra thời hạn và source of time, không chỉ hy vọng background cleanup xảy ra đúng lúc.

### 12.5. Read/write concerns và failover

Một write được ACK với cấu hình này có thể có ngữ nghĩa durability/failover khác cấu hình kia. Read từ secondary có thể stale. Hãy ghi rõ:

~~~text
Deployment: replica set / sharded cluster
Read path: primary / secondary / selected concern
Write concern: explicit
Transaction mode: enabled or not
Driver retryable-write behavior: known
~~~

Đừng suy mọi API MongoDB đều linearizable trên mọi đường đọc chỉ vì single-document update atomic.

## 13. DynamoDB: condition expressions, transaction và TTL

Một cách bảo vệ result là để database đánh giá điều kiện **trong cùng một write**.

### 13.1. Conditional update trên item

Giả sử một item:

~~~json
{
  "PK": "INVOICE#tenant-a#2026-11",
  "SK": "STATE",
  "status": "NEW",
  "version": 17
}
~~~

Pseudocode API:

~~~text
UpdateItem(
  Key = (PK, SK),
  ConditionExpression =
    "status = :expected AND version = :oldVersion",
  UpdateExpression =
    "SET status = :final, version = :newVersion"
)
~~~

Phải đọc docs để xác minh **condition evaluation/atomicity trong phạm vi item và API hỗ trợ**. Một conditional failure báo **điều kiện không thỏa**; không tự retry bằng cách bỏ điều kiện.

### 13.2. PutItem với attribute_not_exists

Nếu nghiệp vụ là “mỗi invoice ID chỉ có một item”, condition `attribute_not_exists` trên khóa item có thể hỗ trợ một conditional create. Nhưng nếu uniqueness mong muốn là theo field khác khóa item, phải có thiết kế authority/key khác; không suy item condition ngăn trùng toàn bảng theo một attribute bất kỳ.

### 13.3. TTL không phải lease coordination

DynamoDB TTL là cơ chế **expiration/deletion** có tính bất đồng bộ theo dịch vụ. Không được coi việc đến thời điểm TTL là bằng chứng item đã bị xóa tức thời và khóa đã được thu hồi với những bảo đảm fencing/ordering.

Nếu dùng một item làm “lease”, phải có **conditional update/epoch/expiry semantics** được định nghĩa rõ, không chỉ bật TTL.

### 13.4. Transactions và global tables

`TransactWriteItems` có phạm vi, điều kiện và giới hạn theo tài liệu. Cần phân biệt transaction trong vùng hỗ trợ với **multi-region replication/global tables** và chính sách giải quyết ghi đồng thời giữa các region.

Không suy một CAS trên một region tạo ra **global linearizable ownership** trên nhiều region nếu docs không nói như vậy.

### 13.5. Unknown outcome

Một client timeout sau `UpdateItem` có thể không biết đã commit chưa. Hãy thiết kế idempotency/reconciliation, nhất là với lệnh làm tăng/giảm counter hay tác động bên ngoài. Không thay `ConditionExpression` bằng một vòng read-then-write không nguyên tử.

### 13.6. Hợp đồng cần ghi chép

| Chủ đề | Câu hỏi |
| --- | --- |
| Atomic conditional write | Một item hay nhiều item? |
| Isolation | Transaction nào, phạm vi nào? |
| Read consistency | Table/index/region nào hỗ trợ mode nào? |
| TTL | Expiry là logical condition hay background deletion? |
| Global tables | Concurrent writes và conflict resolution? |
| Retry | SDK retry lỗi nào, outcome timeout ra sao? |
| Idempotency | Token nào do API hay ứng dụng bảo vệ? |

## 14. Cassandra/ScyllaDB: regular writes và LWT không cùng hợp đồng

Trong các hệ wide-column kiểu Cassandra/ScyllaDB, regular write và **lightweight transaction (LWT)** có cơ chế/chi phí/guarantee khác nhau.

### 14.1. Regular update không phải CAS

Ví dụ:

~~~sql
UPDATE invoices
SET status = 'FINAL'
WHERE tenant_id = 'tenant-a'
  AND invoice_period = '2026-11';
~~~

Lệnh này tự nó chưa diễn tả “chỉ ghi nếu state còn NEW”. Khi hai writer concurrent, hệ có thể áp mutation theo semantics replication/conflict của regular writes.

### 14.2. IF như conditional write (LWT)

Một ví dụ minh họa trên schema phù hợp:

~~~sql
UPDATE invoices
SET status = 'FINAL'
WHERE tenant_id = 'tenant-a'
  AND invoice_period = '2026-11'
IF status = 'NEW';
~~~

Đây là hướng dùng **LWT/CAS**. Cần đọc tài liệu sản phẩm/phiên bản về:

- Phạm vi partition/row/conditional statement.
- Cơ chế phối hợp và số vòng mạng.
- Consistency level của regular và serial phases.
- `SERIAL`/`LOCAL_SERIAL` và topology multi-DC.
- Contention, timeouts, retries và những trường hợp không nên trộn đường cập nhật khác nhau.
- Bảo đảm nếu sử dụng các regular mutations song song trên cùng dữ liệu.

Không mặc định mọi lệnh `UPDATE` CQL đã có cùng semantics của LWT.

### 14.3. Một partition là ranh giới quan trọng

Nhiều thiết kế Cassandra dựa vào partition key để xác định locality của dữ liệu. Một conditional operation trên một partition không tự trở thành transaction across arbitrary partitions.

Nếu muốn “unique invoice theo tenant+period”, cần chọn khóa và bảng theo access pattern sao cho **một authority/conditional path** bảo vệ đúng business key.

### 14.4. Quorum overlap chưa đủ

Công thức `R+W>N` mô tả overlap quorum trong tập replica cố định; nó không tự tạo linearizability cho mọi regular write, không giải quyết conflict timestamp hay cung cấp fencing bên ngoài.

### 14.5. TTL của row không phải fencing

TTL/tombstone/compaction liên quan vòng đời dữ liệu. Không được coi “lock row hết TTL” là bảo đảm một stale process sẽ không tiếp tục gửi write vào bảng khác; cần quyền ghi theo thế hệ và check tại destination hoặc CAS thích hợp.

## 15. etcd: lease, revision, transaction và watch

etcd là một hệ key-value thường được dùng làm **coordination store**. Các tính năng như **transactions compare-and-swap, leases, revisions và watches** có thể hỗ trợ leader election hoặc quản lý owner, nhưng mỗi tính năng có **contract riêng**.

### 15.1. Mẫu compare-and-put ở cấp key

Pseudocode khái niệm:

~~~text
Txn(
  IF createRevision("/locks/invoice/A") == 0
  THEN put("/locks/invoice/A", ownerToken, leaseId)
  ELSE return LOCK_BUSY
)
~~~

Cần đọc docs chính thức để biết cách diễn đạt compare condition, transactional scope, value/revision và lease attachment. Một transaction trên etcd có thể bảo vệ metadata ownership ở store, nhưng **không tự làm external database update atomic với store**.

### 15.2. Lease là quyền gắn với thời gian

Key có thể gắn lease và bị xóa khi lease hết theo giao thức. Worker phải hiểu:

- Cách cấp lease/keep-alive.
- Khi keep-alive timeout, có thể biết chắc lease còn không?
- Khi session/lease hết, key bị xử lý như thế nào?
- Nếu worker pause rồi resume, nó còn được phép tác động không?

**Key tự hết hạn không bắt worker process tự ngừng tính toán**. Cần fenced writes hoặc kiểm tra điều kiện tại đích.

### 15.3. Revision và fencing

etcd cung cấp revision liên quan lịch sử thay đổi KV. Có thể dùng một **thế hệ có thứ tự từ giao thức** cho thiết kế fencing khi bảo đảm được tính đơn điệu và phạm vi cần thiết.

Nhưng không được lấy bất kỳ trường revision nào rồi mặc định nó chính là token hợp lệ cho mọi lock:

- Revision có scope và ngữ nghĩa cụ thể.
- Recreate key, compaction, watch resume cần hiểu rõ.
- Resource đích vẫn phải so token.

### 15.4. Watch không thay authority

Watch giúp nhận thay đổi, nhưng client có thể bị ngắt kết nối hoặc bỏ lỡ lịch sử đã compact. Khi watch không thể tiếp tục từ revision cũ, cần **resync snapshot theo protocol**, không suy “không thấy event” nghĩa leadership không thay đổi.

### 15.5. Đọc docs theo từng endpoint

| Primitive etcd | Cần xác minh |
| --- | --- |
| `Txn/Compare` | Điều kiện có tính nguyên tử và scope nào? |
| `LeaseGrant/KeepAlive` | TTL thực tế, tình huống mất session |
| `Watch` | Thứ tự event, resume, compaction |
| `Revision` | Thứ tự và phạm vi dùng làm fencing |
| `Range/Read` | Chọn consistency mode nào? |
| `Cluster membership` | Quorum, failover, partition semantics |

## 16. ZooKeeper: ephemeral node, session và sequential node

ZooKeeper thường được dùng cho coordination như leader election, membership và locks. Những khái niệm quan trọng gồm **znode, ephemeral znode, sequential znode, session và watches**.

### 16.1. Ephemeral node không có nghĩa process bị dừng

Một worker có thể tạo ephemeral node gắn session. Khi session hết hạn, node có thể bị xóa theo giao thức, cho phép worker khác nhận quyền.

Tuy nhiên process cũ có thể vẫn đang chạy và gửi lệnh tới một **database bên ngoài**. Session expiry không tự thu hồi tất cả side effects của worker đã từng giữ lock.

### 16.2. Sequential nodes và thứ tự

Một lock recipe có thể dùng ephemeral sequential znodes để xếp waiter theo thứ tự. Khi sử dụng cần:

- Đọc đúng algorithm/lock recipe chính thức.
- Xem watcher được đặt trên node nào để tránh herd effect.
- Phân biệt thứ tự sequence znode với **fencing token được đích chấp nhận**.
- Xử lý session expiration và reconnect đúng protocol.

Không suy “có sequential node” nghĩa mọi external write được serializable.

### 16.3. Watch event và reconnect

Các watch có semantics và giới hạn riêng (tùy API/phiên bản). Client phải hiểu:

- Watch có dùng một lần hay persistent theo API?
- Event nào có thể bị mất trong disconnect/reconnect?
- Làm sao đọc lại state và đăng ký watch đúng?
- Nếu session expired, các ephemeral nodes/lock ownership ra sao?

### 16.4. Fencing vẫn cần ở đích

Ngay cả khi election xác định đúng leader mới, worker cũ có thể đang pause hoặc bị cô lập. Đích cập nhật cần **token/order/conditional authority** để ngăn worker cũ ghi sau khi leader mới đã commit.

## 17. So sánh các primitive qua cùng một nghiệp vụ

Giả sử operation là `finalizeInvoice(tenant,period)`.

| Giải pháp | Bảo vệ được gì khi dùng đúng? | Chưa tự bảo vệ được gì? |
| --- | --- | --- |
| Redis `SET NX PX` | Cạnh tranh tạo một key khóa tại một instance theo contract | Failover, stale worker, external write |
| MongoDB conditional update | Điều kiện trên một document tại source | External payment và nhiều boundary khác |
| DynamoDB condition | Điều kiện được check tại item write hỗ trợ | Global uniqueness tùy ý, cross-region workflow |
| Cassandra LWT | Conditional coordination theo phạm vi hỗ trợ | Arbitrary multi-partition business transaction |
| etcd lease + txn | Coordination state có protocol/lease/atomic compare | External DB bị worker cũ ghi sau expiry |
| ZooKeeper ephemeral sequential recipe | Session-based ownership/waiter ordering theo recipe | External side effects có fencing |
| Idempotency ledger | Không lặp lại cùng logical operation nếu storage/commit đúng | Xung đột giữa các logical operation khác ID |
| Outbox/inbox | Giảm khoảng trống crash giữa DB state và event delivery | Không tự tạo atomic commit với remote service |

**Cùng một từ “lock” không có nghĩa mọi sản phẩm có cùng fault tolerance, commit semantics hoặc liveness.** Phải đọc hợp đồng gốc của primitive đang thực sự sử dụng.

## 18. Từ product contract sang application contract

Một workflow có thể đi qua nhiều thành phần:

~~~text
Coordination store
    |
    | lock/lease
    v
Worker process
    |
    +-- Read source database
    +-- Update output database
    +-- Call payment provider
    +-- Publish event
~~~

**Product contract** mô tả bảo đảm của từng API trong từng hệ; **application contract** mô tả bất biến mà người dùng và nghiệp vụ mong muốn. Một lock bên ngoài không tạo transaction bao trùm cả database, provider và event broker.

| Boundary | Bảo đảm phải đọc | Khoảng trống ứng dụng phải xử lý |
| --- | --- | --- |
| Lock/lease | Acquire, renew, release, expiry | Worker cũ tiếp tục chạy |
| Source DB | Read consistency, version | Dữ liệu thay đổi sau read |
| Output DB | Conditional update/transaction | Side effect ở hệ khác |
| Payment provider | Idempotency và outcome lookup | DB/payment không có chung commit |
| Message broker | Delivery và ordering scope | Consumer duplicate side effects |
| Search index | Indexing lag/read consistency | Chưa thấy dữ liệu source mới |
| HTTP client | Deadline và retry | Unknown commit outcome |

### 18.1. Một authoritative record có thể giảm coordination

Nếu bất biến chỉ là mỗi `(tenantId,invoicePeriod)` có một invoice FINAL, ta có thể biểu diễn:

~~~text
InvoiceState:
  tenantId
  period
  status = NEW | PROCESSING | FINAL | FAILED
  version
  operationId
  result
~~~

Conditional mutation/unique key trên authoritative record có thể bảo vệ kết quả trực tiếp hơn việc tin một lock ngoài DB. Nhưng chỉ đúng nếu **engine bảo đảm atomicity cho tất cả điều kiện và field liên quan tại commit**.

### 18.2. Khi nào vẫn cần coordination service?

Khi bài toán đòi leader election, membership, phân công worker, barrier, thứ tự generation hay lease cho một tập resource, coordination service có thể phù hợp. Tuy nhiên câu hỏi then chốt vẫn là:

> **Destination nào cưỡng chế invariant nếu holder cũ tiếp tục gửi command?**

Nếu chỉ coordination store biết khóa đã hết, còn database đích nhận write vô điều kiện, hệ chưa được bảo vệ trước stale holder.

## 19. Contract tối thiểu của một distributed lock

Trước khi dùng lock để bảo vệ một mutation nhạy cảm, ghi rõ:

~~~text
Acquire:
  - Atomic trên đơn vị nào?
  - Ai được quyền nhận SUCCESS?
  - Failover hoặc partition có thể cấp quyền trùng không?

Renew/expiry:
  - Clock và session nào xác định expiry?
  - Renew timeout có nghĩa gì?
  - Worker bị pause có biết đã mất quyền không?

Release:
  - Chỉ owner hợp lệ mới được release?
  - Check token và delete có atomic không?

Handoff:
  - Owner generation/term được tạo thế nào?
  - Có monotonic fencing token không?
  - Destination có chặn generation cũ không?

Recovery:
  - Khi response mất, tìm outcome ở đâu?
  - Khi process chết, ai takeover?
  - Khi metadata/replica lag, read/write policy là gì?
~~~

### 19.1. Check lock rồi write vẫn có race

~~~text
T1: Worker A kiểm tra stillOwnLock() -> true.
T2: A bị pause.
T3: Lease hết hạn; B lấy quyền.
T4: B commit kết quả mới.
T5: A resume và gửi write.
~~~

Kiểm tra quyền ở T1 không được thực thi **nguyên tử với write ở T5**. Muốn chặn A cần điều kiện được kiểm tra tại tài nguyên đích, không chỉ một heartbeat hoặc API `stillOwnLock`.

### 19.2. Khóa kéo dài qua HTTP call có chi phí

~~~text
Acquire lock
  -> Read database
  -> Call payment API (có thể mất nhiều giây)
  -> Update database
Release lock
~~~

Nếu payment request timeout, có thể đã thành công; nếu worker bị pause, lease có thể đã hết. Với workflow này, thường cần persistent intent, idempotency key ở provider, state machine và reconciliation ngay cả khi vẫn dùng lock để giảm cạnh tranh.

## 20. Fencing token: hiểu cả giới hạn

Giả sử generation của A là 71, của B là 72. Destination giữ `maxSeenEpoch` và từ chối write có token thấp hơn.

### 20.1. Lịch được bảo vệ

~~~text
T1: A holds 71, rồi bị pause.
T2: A lease hết hạn.
T3: B acquires 72.
T4: B writes with 72 -> destination records 72.
T5: A resumes, writes with 71 -> REJECT.
~~~

Điều này ngăn **stale owner ghi đè một mutation đã được chấp nhận từ owner mới hơn**.

### 20.2. Lịch cần bảo đảm mạnh hơn

~~~text
T1: A holds 71, lease expires.
T2: B acquires 72 nhưng chưa gửi write tới destination.
T3: A sends write with 71.
T4: B sends write with 72.
~~~

Nếu destination mới biết `maxSeenEpoch=70` lúc T3, quy tắc chỉ kiểm tra `token < maxSeenEpoch` có thể vẫn chấp nhận write của A **trước khi thấy 72**.

Nếu invariant đòi **mọi write của A đều bị chặn ngay từ thời điểm B được cấp quyền**, cần một giao thức cập nhật/kiểm tra authority ở destination hoặc cơ chế khác đủ mạnh. Đừng coi fencing đơn giản tại write là lời giải cho mọi yêu cầu chặn tức thời.

### 20.3. Epoch, version và idempotency là ba rào chắn khác nhau

~~~text
ownerGeneration   -> chặn stale owner
documentVersion   -> chặn lost update
logicalOperationId -> chặn retry cùng ý định
businessState     -> chặn chuyển trạng thái sai
~~~

Cùng generation có thể gửi nhiều lệnh; vì vậy vẫn cần quy tắc duplicate xử lý riêng.

### 20.4. Mã giả ranh giới commit

~~~java
// Pseudocode: atomic scope phải do product contract bảo đảm.
Result applyCommand(Command cmd) {
    return authoritativeStore.atomic(() -> {
        State s = load(cmd.entityKey());

        if (cmd.fencingEpoch() < s.maxAcceptedEpoch()) {
            return Result.STALE_OWNER;
        }
        if (s.wasProcessed(cmd.logicalOperationId())) {
            return s.previousResult(cmd.logicalOperationId());
        }
        if (!businessTransitionAllowed(s, cmd)) {
            return Result.CONFLICT;
        }

        State next = applyBusinessChange(s, cmd);
        next.maxAcceptedEpoch(Math.max(
            s.maxAcceptedEpoch(), cmd.fencingEpoch()
        ));
        next.recordProcessed(cmd.logicalOperationId());
        save(next);
        return Result.SUCCESS;
    });
}
~~~

`authoritativeStore.atomic` chỉ là placeholder. Nếu entity, generation và dedup ledger nằm ở các shards khác nhau mà engine không hỗ trợ transaction tương ứng, ví dụ **không còn có nghĩa atomic đã trình bày**.

## 21. CAS, lease hay workflow bất đồng bộ?

~~~mermaid
flowchart TD
    A["Viết business invariant"] --> B{"Có thể kiểm tra tại một authoritative record?"}
    B -->|Có| C["Conditional mutation / unique business key"]
    B -->|Không| D{"Cần owner/leader cho nhiều bước?"}
    D -->|Có| E["Xem coordination/lease"]
    D -->|Không| F["Workflow idempotent, outbox, saga"]
    E --> G["Lease + term + fencing + destination guard"]
    C --> H["Read official API contract"]
    F --> H
    G --> H
    H --> I["Fault injection + invariant verification"]
~~~

| Tình huống | Primitive nên xem trước | Điều không được quên |
| --- | --- | --- |
| Một Order chuyển NEW→FINAL | Conditional update | Conflict và timeout |
| Unique invoice theo tenant-period | Unique key/conditional create | Shard/global uniqueness scope |
| Scheduler chỉ một leader | Election/lease | Stale worker, fencing |
| Queue work với nhiều consumers | Visibility lease/claim | Redelivery, idempotency |
| External payment | Provider idempotency + ledger | Unknown outcome |
| Multi-item mutation | Transaction được hỗ trợ | Isolation, participants, retries |
| Side effect liên service | Outbox/inbox hoặc saga | Không có global atomicity tự động |

**Chi phí trade-off:** lock có renew và lease risk; CAS có contention/recomputation; transaction có coordination overhead; async workflow có eventual completion và reconciliation. Chọn theo invariant chứ không theo cú pháp API ngắn nhất.

## 22. Contract matrix cho buổi design review

| Claim cần có | API/scope | Cấu hình | Failure case | Bằng chứng cần thu |
| --- | --- | --- | --- | --- |
| Chỉ một conditional write thắng | Item/document | Key, consistency mode | Concurrent writers | Official API docs + test |
| Read thấy write đã ack | Read path | Read concern/consistency | Replica lag | Official consistency docs |
| ACK bền qua failover | Commit path | Durability/write concern | Crash sau ack | Replication docs |
| Lease thu hồi quyền | Lock/session | TTL/keepalive | Pause/disconnect | Lease docs |
| Generation có thứ tự | Coordination transaction | Term/revision scope | Leader failover | Protocol spec |
| Old owner không ghi được | Destination | Fencing check | Zombie process | Application invariant + test |
| Retry không gây double effect | Business effect | Idempotency ledger | Lost response | DB transaction + app test |
| Nhiều item commit nguyên tử | Transaction | Topology/scope | Crash/partition | Transaction docs |
| Watch không mất state khi reconnect | Watch/read | Revision/resync | Compaction/session expiry | Watch docs |
| Cross-region uniqueness | Global operation | Regions/config | Simultaneous writes | Official cross-region docs |

Một claim chỉ được dùng cho design khi có:

~~~text
Required behavior
  -> Product guarantee
     -> Preconditions/configuration
        -> Implementation and client behavior
           -> Verification and fallback
~~~

Nếu chưa có bằng chứng cho một mắt xích, ghi thành **open assumption** và thiết kế fallback, không suy từ tên “strong”, “atomic” hay “distributed”.

### 22.1. Khi nào phải đọc lại tài liệu?

Khi upgrade engine/SDK, đổi single-node thành replica set, mở thêm region, thay read/write concern, bật sharding, đổi TTL/retry policy, đưa hệ sang active-active hoặc đổi coordination service. Những thay đổi ấy có thể làm một claim từng đúng **không còn áp dụng trong điều kiện mới**.

## 23. Hợp đồng sản phẩm và hợp đồng API của ứng dụng

**Product contract:**

~~~text
Conditional update is atomic on a supported item.
~~~

**Application contract:**

~~~text
POST /invoices/finalize
  - at most one FINAL per tenant-period
  - retry with same requestId returns same logical outcome
  - timeout may be UNKNOWN/PENDING
  - stale worker cannot overwrite newer accepted result
  - completed invoice survives the documented failure model
~~~

Ứng dụng phải **tổng hợp** nhiều primitive thành hợp đồng của chính nó. Product API có thể vận hành đúng tất cả cam kết của nó nhưng ứng dụng vẫn sai vì suy diễn vượt phạm vi.

### 23.1. State machine thay vì một cờ `locked`

~~~text
NEW
 |
 v
CLAIMED(ownerGeneration=72, operationId=R42)
 |                           |
 |                           v
 |                    RETRYABLE_FAILURE
 v
FINAL(resultId, version)
~~~

Mỗi transition cần một điều kiện có thể cưỡng chế ở nguồn dữ liệu:

- `NEW → CLAIMED`: Conditional claim, queue visibility hoặc lease protocol.
- `CLAIMED → FINAL`: Owner/version guard, idempotency, business conditions.
- `CLAIMED → RETRYABLE_FAILURE`: Failure status và retry policy.
- `FINAL`: Terminal state; duplicate logical request không tạo side effect mới.

Một khóa bên ngoài có thể giúp tránh cạnh tranh khi tính toán nhưng không thay điều kiện commit trên state machine.

### 23.2. Response semantics của ứng dụng

| Quan sát ở client | Ý nghĩa phải ghi rõ |
| --- | --- |
| `HTTP 200` | Commit đã được xác nhận ở mức nào? |
| `HTTP 202` | Intent đã được lưu bền ở đâu, hay mới nhận RAM? |
| `HTTP 409` | Business conflict hay stale owner? Có nên retry? |
| `HTTP 503` | Từ chối trước mutation hay outcome không rõ? |
| Network timeout | Có cách tra operation status theo ID không? |

**Mã HTTP không tự mang đầy đủ ngữ nghĩa của transaction hay lease.**

## 24. Lịch H2: leader cũ không nhận tin bị thay thế

Một scheduler có ba replica điều phối:

~~~text
Leader A: term 9
Follower B: term 9
Follower C: term 9
~~~

Network partition:

~~~text
{ A }  |  { B, C }
~~~

Nếu giao thức quorum cho phép B/C bầu leader mới term 10, A có thể còn sống nhưng cô lập, không biết term đã thay đổi.

| Mốc | Worker A | B/C | Hệ ngoài |
| --- | --- | --- | --- |
| T0 | Leader term 9 | Follows term 9 | — |
| T1 | Bị cô lập | B/C liên lạc được | — |
| T2 | Vẫn giữ cờ `isLeader=true` | B thành leader term 10 | — |
| T3 | Gửi `createBatch` | B cũng gửi `createBatch` | Hai command tới DB |

Nếu database chỉ thực hiện:

~~~text
INSERT batch(tenantId, day, generatedAt)
~~~

mà không có unique business key hoặc fencing, có thể tạo hai batch. **Election đúng không tự làm external side effect đúng**.

### 24.1. Hai cách bảo vệ tại nguồn

1. **Unique business key** cho `(tenantId,day)`, với scope global/shard phù hợp.
2. **Owner term/fencing** nếu một worker cũ phải bị chặn không chỉ ở final record mà còn trong một chuỗi mutation.

Một số hệ có thể sử dụng cả hai để bảo vệ lớp khác nhau.

### 24.2. Khi mất quorum, phải xét availability

Nếu A không còn quorum, một hệ ưu tiên strong consistency có thể từ chối operation mạnh tại A. Không dựa vào ping thành công hay một biến RAM để cho A tiếp tục commit.

## 25. Lịch H3: người cũ xóa khóa của người mới

~~~text
T0: A SET lockKey=randomA, TTL=30s.
T1: A bị pause 40s.
T2: Lock A hết hạn.
T3: B SET lockKey=randomB, thành công.
T4: A resume và gọi DEL lockKey.
~~~

`DEL` vô điều kiện ở T4 có thể **xóa khóa mới của B**.

### 25.1. Compare-and-delete phải atomic

Đúng hơn:

~~~text
IF lockKey.value == randomA:
    delete lockKey
ELSE:
    do not delete
~~~

Kiểm tra value và xóa phải nằm trong một operation **nguyên tử**. Hai lệnh `GET` rồi `DEL` có race:

~~~text
A GET -> randomA.
Lock expires.
B SET -> randomB.
A DEL -> xóa lock của B.
~~~

Nhưng **compare-and-delete chỉ bảo vệ release**, không bảo vệ dữ liệu đích khỏi stale write sau lease expiry.

## 26. Queue visibility timeout cũng là một loại hợp đồng lease

Một message queue có thể tạm ẩn message khỏi worker khác trong thời gian nhất định. Tuy nhiên không được suy:

~~~text
Message delivered at most once
AND
external business effect applied exactly once.
~~~

Ví dụ:

~~~text
T0: Worker A receives message M.
T1: A xử lý chậm.
T2: Visibility timeout hết.
T3: Worker B cũng nhận message M.
T4: B xử lý và commit.
T5: A resume và cũng cố commit.
~~~

Một hợp đồng queue có thể **cho phép redelivery**, điều này phục vụ khả năng recovery nhưng buộc consumer phải idempotent. Renew visibility có thể cải thiện liveness/giảm duplicate attempts, song không thay thế destination-side guard.

### 26.1. Những điều phải tìm trong docs queue

- Visibility/ack timeout và extension semantics.
- Delivery guarantee và điều kiện redelivery.
- Ordering scope: queue toàn cục hay từng partition/message group?
- Retry/redrive/dead-letter behavior.
- Message retention và duplicate detection window.
- Ack mất response có thể tạo replay không?
- Tác động ngoài queue có được bảo vệ bởi transaction nào không?

### 26.2. Ordering broker không luôn là ordering commit

Broker có thể deliver A trước B, nhưng worker A bị pause và worker B commit trước. Nếu business invariant phụ thuộc thứ tự commit, cần **sequence/version/fencing hoặc processing serialization**, không chỉ dựa trên delivery order.

## 27. Driver/SDK cũng là một phần của hợp đồng

Ngay cả khi database contract rõ, client SDK có thể:

- Retry một số lệnh tự động.
- Đổi host/coordinator sau failover.
- Hủy request phía client nhưng server vẫn đang thực thi.
- Thay cách đọc replica theo routing/topology.
- Chuẩn hóa hoặc gộp error codes.
- Giới hạn timeout khác business deadline.

### 27.1. Checklist dành riêng cho driver

1. SDK retry **những error class nào**?
2. Retry có giữ cùng transaction/request ID không?
3. Command có idempotent trong mọi đường retry được dùng không?
4. Connection reset có thể xảy ra **sau commit** không?
5. Client deadline có hủy operation tại server thật không?
6. Error nào chắc chắn no-op, error nào unknown?
7. Driver chọn primary/replica thế nào khi topology thay đổi?
8. Release/lease methods có thể bị SDK retry không?

### 27.2. Retry amplification

Giả sử:

~~~text
Logical operations/s = 10.000
Average attempts per operation = 1,25
~~~

\[
\text{RPC attempts/s} = 10000\times1{,}25=12500
\]

Các retries làm tải tăng trong sự cố. Cần **bounded retries, overall deadline, exponential backoff và jitter**, nhưng những biện pháp này chỉ kiểm soát tải; **tính an toàn của retry** còn phụ thuộc idempotency và outcome.

### 27.3. Retry nhiều tầng

~~~text
Gateway retries 3 times
  -> Service SDK retries 3 times
     -> Coordinator may retry 2 times
~~~

Không được để mỗi tầng độc lập retry không kiểm soát. Phải xác định **tầng sở hữu retry**, attempt budget chung và logical operation ID xuyên các tầng.

## 28. Các phát biểu nghe hợp lý nhưng thiếu bằng chứng

| Phát biểu | Lỗ hổng | Bằng chứng cần tìm |
| --- | --- | --- |
| “Lock key đang tồn tại nên tôi là owner.” | Key có thể đã thuộc session khác | Token/lease authority tại commit |
| “Renew đã gửi nên lease còn.” | Renew có thể thất bại hoặc response mất | Renew outcome |
| “Có lock rồi không worker nào khác ghi được.” | Stale worker sau expiry | Fencing tại destination |
| “Primary ACK thì không mất dữ liệu.” | Tùy durability/replication | Write concern/failover docs |
| “Replica đã thấy bản mới thì mọi replica đều thấy.” | Replication lag | Read contract |
| “CAS một item đủ cho nhiều service.” | External side effects | Transaction boundaries |
| “TTL hết nghĩa đã xóa đúng thời điểm.” | Cleanup có thể bất đồng bộ | TTL semantics |
| “Timeout chứng minh chưa commit.” | Response có thể mất | Outcome lookup |
| “FIFO broker nghĩa commit ngoài DB cũng FIFO.” | Worker có thể chạy lệch | Commit ordering |
| “Election chọn leader rồi, process cũ sẽ dừng.” | Zombie worker có thể tiếp tục | Term/fencing |
| “R+W>N đủ cho mọi write linearizable.” | Overlap chưa đủ protocol | Read/write algorithm |
| “Có ba replica là chịu mọi partition.” | Quorum/failure domain | Fault model |
| “Test 100 lần pass chứng minh không bao giờ sai.” | Chưa bao phủ mọi lịch | Contract + model + tests |

## 29. Bài thực hành phân tích một thiết kế có vấn đề

Giả sử một đồng nghiệp mô tả:

> “Tôi dùng TTL key trong Redis để chặn hai worker. Worker có lock thì đọc dữ liệu, gọi payment provider, cập nhật database rồi `DEL` trong `finally`. Nếu lỗi mạng thì retry đến khi thành công.”

Những giả định cần đánh dấu:

1. Acquire thực sự dùng lệnh nguyên tử nào?
2. Worker pause lâu hơn TTL sẽ làm gì?
3. `DEL` có thể xóa khóa của holder mới không?
4. Failover của Redis có thể ảnh hưởng lock state như thế nào theo topology?
5. Payment API có idempotency key không?
6. Nếu payment đã thành công nhưng DB write timeout, trạng thái nào đúng?
7. Nếu DB write đã commit nhưng response mất, retry có gây double effect không?
8. Có thể dùng conditional write và operation ledger thay lock ngoài không?
9. Nếu vẫn cần lease, destination có fencing guard không?
10. Bất biến nghiệp vụ được kiểm chứng **ở đâu** chứ không chỉ ở lock service?

### 29.1. Một workflow có đường hồi phục

~~~text
1. Client gửi logicalOperationId.
2. Service ghi durable intent bằng conditional/transaction API.
3. Worker claim job theo protocol được docs hỗ trợ.
4. External call dùng idempotency key của provider.
5. Persist outcome bằng conditional state transition.
6. Nếu outcome không rõ, tra lại provider/source.
7. Dùng outbox để phát event sau source commit.
8. Consumer downstream dedup nếu delivery có thể lặp.
~~~

Lock có thể vẫn hữu ích để giảm tính toán trùng, nhưng **không phải chứng minh duy nhất cho toàn workflow**.

## 30. Lab: kiểm thử hợp đồng lease và stale worker trong môi trường an toàn

Một thiết kế có thể trông đúng trong điều kiện bình thường nhưng thất bại khi process bị pause, lease hết hạn hoặc response mất. Lab này cần **môi trường thử nghiệm riêng, dữ liệu giả và cơ chế fault injection có thể đảo ngược**.

### 30.1. Chốt điều cần chứng minh

Ví dụ:

~~~yaml
experiment: stale-holder-fencing
businessKey: "invoice/tenant-a/2026-11"
initialState: "NEW"
workers:
  - "A"
  - "B"
leaseDurationSeconds: 30
fault:
  kind: "pause worker A longer than lease"
guaranteesToVerify:
  - "at most one FINAL invoice"
  - "stale A cannot overwrite accepted result from B"
  - "duplicate operationId does not cause duplicate business effect"
capture:
  - "leaseId and fencingEpoch"
  - "attemptId and logicalOperationId"
  - "invoke/response time"
  - "mutation result and document version"
  - "destination-side rejection reason"
~~~

Đây là **mẫu ghi kế hoạch**, không phải cấu hình trực tiếp cho một fault-injection tool.

### 30.2. Case A — Stale holder sau pause

1. A acquire lease, nhận generation 71.
2. A đọc input, bắt đầu tính toán.
3. Pause A lâu hơn TTL.
4. Cho B acquire generation 72 và commit kết quả.
5. Resume A, để A thực sự cố gửi write generation 71.
6. Kiểm tra **destination đã từ chối** A hay chưa.
7. Kiểm tra state FINAL, version và audit log.

Nếu chỉ quan sát “A không acquire lại được lock” mà không thử **write từ stale holder tới đích**, test chưa đụng lỗi cốt lõi.

### 30.3. Case B — Response mất sau commit

1. Cho A gửi mutation với logicalOperationId `op-42`.
2. Server commit thành công.
3. Fault injection làm mất response.
4. Client timeout.
5. Retry cùng `op-42` theo thiết kế.
6. Kiểm tra chỉ có **một business effect** và outcome có thể được xác minh lại.

Không đổi ID khi retry cùng một ý định. Nếu cùng ID nhưng payload khác, ứng dụng nên phát hiện conflict theo contract.

### 30.4. Case C — Release sau expiry

1. A acquire value tokenA.
2. Pause A cho lock hết hạn.
3. B acquire tokenB.
4. A resume, gọi release.
5. Kiểm tra **lock của B vẫn tồn tại và vẫn được bảo vệ**.

Nếu `DEL` xóa lock của B, compare-and-delete đã không được thực thi đúng.

### 30.5. Case D — Failover coordination store

1. Acquire lock hoặc conditional ownership record.
2. Fault một node/leader theo test topology.
3. Quan sát leader election/failover và ownership state.
4. Cho worker khác thử acquire.
5. Kiểm tra product contract cho phép gì và invariant có bị phá không.

**Không kết luận sản phẩm vi phạm hợp đồng** khi ứng dụng dùng cấu hình yếu hơn điều kiện mà docs yêu cầu. Kết quả phải gắn với version, deployment mode, durability/consistency configuration.

### 30.6. Case E — Network partition

1. Tách network thành majority/minority (nếu giao thức có quorum).
2. Gửi acquire/renew/write từ cả hai phía.
3. Thu response, timeout, epoch/term.
4. Kiểm tra phía không đủ authority có bị từ chối operation mạnh không.
5. Heal mạng, đối soát journal và business state.

Điều cần kiểm chứng là **không có hai owner cùng được công nhận để commit các side effects xung đột**, chứ không phải “mọi node đều trả HTTP 200 khi network split”.

### 30.7. Case F — Queue redelivery

1. Worker A nhận message và chưa ack.
2. Pause A quá visibility timeout.
3. Worker B nhận lại message, thực hiện side effect.
4. A resume và cũng cố thực hiện side effect.
5. Kiểm tra idempotent consumer và destination guard.

## 31. Lưu execution history để phân biệt chứng cứ với suy đoán

Một log thử nghiệm hữu ích:

~~~json
{
  "logicalOperationId": "op-42",
  "attemptId": "op-42-2",
  "businessKey": "invoice/tenant-a/2026-11",
  "workerId": "B",
  "leaseId": "lease-901",
  "ownerGeneration": 72,
  "expectedDocumentVersion": 17,
  "consistencyMode": "configured-mode",
  "writeAcknowledgment": "configured-ack",
  "invokedAt": "2026-11-14T12:00:34.010Z",
  "completedAt": "2026-11-14T12:00:34.060Z",
  "outcome": "COMMITTED",
  "resultDocumentVersion": 18
}
~~~

Mỗi attempt cần log các dữ kiện thực sự quan sát được, không tự thêm `committed=true` nếu client chỉ thấy timeout.

### 31.1. Không nhầm timestamp giữa các node

Đồng hồ A nhanh 200 ms, B chậm 150 ms có thể làm thứ tự log theo wall-clock trái với **thứ tự nhân quả**. Dùng:

- Request/attempt ID.
- Server commit sequence/term/revision khi được engine cung cấp.
- Trace span và causal edges.
- Monotonic duration trong từng process.
- Clock uncertainty hoặc synchronization evidence khi so thời gian giữa node.

Không so `System.nanoTime()` trên hai JVM như một đồng hồ tuyệt đối.

### 31.2. Phân loại outcome

| Outcome | Khi nào dùng |
| --- | --- |
| `COMMITTED` | Có xác nhận phù hợp write/commit contract |
| `REJECTED_NO_APPLY` | API bảo đảm điều kiện từ chối trước mutation |
| `CONFLICT` | Business/conditional predicate không đạt |
| `UNKNOWN` | Timeout/mất response, chưa xác minh commit |
| `PENDING` | Application đã ghi nhận intent nhưng chưa kết thúc |
| `COMPENSATED` | Side effect đã xảy ra và đã thực hiện bước bù trừ |

Một lệnh `write` bị timeout không được tự gắn `REJECTED_NO_APPLY`.

### 31.3. Chính sách log dữ liệu nhạy cảm

Không log token bí mật, raw payment credentials hoặc toàn bộ dữ liệu hóa đơn ngoài nhu cầu. Logging nên dùng **operation ID, business key được ẩn/hashed phù hợp, phiên bản và trạng thái**. Fencing token là dữ liệu điều phối nhưng vẫn có thể tiết lộ topology/sequence; cần quyền truy cập có kiểm soát.

## 32. Kiểm tra ba lớp bảo đảm riêng biệt

Một giải pháp khóa hoặc điều phối phải được xem ở ba lớp:

### Lớp 1 — Coordination correctness

Hỏi:

~~~text
Can two different owners both legitimately acquire
the same lock under the supported failure model?
~~~

Đây là phạm vi contract của lock/election/lease/transaction store. Lệnh CAS/leader protocol phải được kiểm tra theo version/topology.

### Lớp 2 — Destination correctness

Hỏi:

~~~text
If an old owner continues running,
can its side effect overwrite a newer accepted state?
~~~

Cần fencing/conditional update/unique key tại đích, hoặc một cơ chế tương đương bảo vệ business invariant.

### Lớp 3 — End-to-end workflow correctness

Hỏi:

~~~text
What if DB commit succeeds but response is lost?
What if payment succeeds before DB transaction fails?
What if message is redelivered?
~~~

Cần request ID, idempotency, outbox/inbox, recovery và reconciliation. **Một thiết kế có thể pass lớp 1 nhưng fail lớp 2 hoặc lớp 3.**

## 33. Checklist trước khi chọn distributed lock

1. **Bất biến là gì?** Một bản ghi FINAL, một thanh toán hay một leader?
2. Có thể bảo vệ bằng **conditional write/unique key** ngay tại source không?
3. Lock service được triển khai với **topology/replication/consistency** nào?
4. API acquire có atomic trong **đúng phạm vi** không?
5. Lease được cấp và hết hạn bằng **đồng hồ/quy tắc** nào?
6. Worker có thể **pause lâu hơn TTL** không?
7. Renew thất bại/timeout thì worker có biết mình mất quyền không?
8. Release có **check owner token atomically** không?
9. Token nào tạo **thứ tự generation** khi đổi owner?
10. Destination có **kiểm tra fencing tại commit** không?
11. Có điều kiện để một owner mới ghi trước khi old owner hết quyền không?
12. Có **quorum/term/election** bảo vệ khi network split không?
13. ACK/durability có đúng yêu cầu khi failover không?
14. Read path có đủ mới để ra quyết định ghi không?
15. SDK tự động retry những operation nào?
16. Timeout có được xem là **UNKNOWN** không?
17. Dedup ledger có được lưu bền/atomic với business effect không?
18. Bất biến có bắc qua **nhiều item/shard/region/service** không?
19. Nếu dùng queue, delivery/visibility/ordering contract là gì?
20. Có test pause, failover, partition, duplicate delivery, response loss chưa?
21. Đã lưu **bản ghi link/tên mục/phiên bản docs chính thức** cho từng claim chưa?
22. Khi nâng cấp sản phẩm hoặc thay topology, ai chịu trách nhiệm **review contract lại**?

## 34. Bài tập vận dụng

### Bài 1 — Đọc câu bảo đảm đúng phạm vi

Tài liệu giả định ghi “Atomic conditional update on a single item”.

1. Nó có chứng minh transaction hai items không?
2. Có bảo đảm HTTP payment ngoài DB được commit cùng không?
3. Nếu client timeout, có chắc condition chưa được áp không?
4. Cần câu hỏi bổ sung nào về region và write ACK?

### Bài 2 — Lease và pause

A giữ lease 30 giây, bị pause 45 giây. B lấy lease mới và ghi thành công. Sau đó A resume.

- Lock service có thể đã vận hành đúng chưa?
- Nếu A ghi đè B, lỗi thuộc lớp nào?
- Fencing token cần được cấp và kiểm tra ở đâu?
- Kiểm tra `stillOwnLock` trước write có đủ không?

### Bài 3 — Fencing chỉ theo maxSeenToken

Destination có `maxSeenEpoch=70`. Lease A generation71 đã hết, B vừa nhận generation72 nhưng chưa gửi write. A gửi write token71.

1. Guard `token < maxSeenEpoch` có thể chấp nhận A không?
2. Nếu invariant cấm mọi write của A sau khi B acquire, cần giao thức mạnh hơn ở đâu?
3. Phân biệt kết quả này với lịch B đã ghi token72 trước A.

### Bài 4 — Compare-and-delete

Với khóa Redis value tokenA, A pause quá TTL, B chiếm khóa với tokenB.

- Vì sao `DEL lockKey` của A là sai?
- Nêu lệnh/script compare-and-delete nguyên tử.
- Compare-and-delete có tự ngăn A ghi sang database khác không?
- Renew phải kiểm tra token không?

### Bài 5 — Conditional update thay khóa

Hai worker cùng muốn chuyển Invoice từ NEW sang FINAL, cả hai đọc version17.

1. Lệnh CAS nên có predicate nào?
2. Một worker thắng, worker còn lại nhận conflict; có phải sự cố không?
3. Nếu invoice chưa tồn tại, cần unique key/conditional create thế nào?
4. Nếu invoice nằm ở sharded collection, cần xác minh uniqueness scope gì?

### Bài 6 — DynamoDB TTL

Nhóm đang định dùng TTL attribute làm lease để giữ stock.

- TTL deletion có nhất thiết đúng giây expiry không?
- Làm sao dùng conditional expression thay việc đợi background delete?
- Khi có hai region nhận ghi, cần đọc contract nào?
- Nếu conditional update timeout, xử lý sao?

### Bài 7 — Cassandra LWT

Hai client cập nhật cùng một partition:

~~~sql
UPDATE invoices
SET status = 'FINAL'
WHERE tenant_id = 'tenant-a'
  AND invoice_period = '2026-11'
IF status = 'NEW';
~~~

- Vì sao `IF` khác regular `UPDATE`?
- Cần xem `SERIAL`/`LOCAL_SERIAL` và topology nào?
- Điều gì chưa được bảo đảm cho external API?
- Có nên retry mù nếu response timeout không?

### Bài 8 — MongoDB write concern

Một worker nhận ACK rồi node primary gặp sự cố ngay sau đó.

- Vì sao phải biết write concern/durability config?
- Read từ secondary có thể thấy dữ liệu cũ không?
- Single-document atomicity có chứng minh durability ở mọi cấu hình không?
- Transaction hai document có cùng contract với một update không?

### Bài 9 — etcd lease và watch

Worker A giữ key gắn lease; network disconnect lâu, session/lease hết; B tiếp quản.

1. Watch event có tự dừng process A không?
2. Revision/term nào có thể là thông tin generation?
3. Nếu watch bị ngắt hoặc lịch sử compact, client phục hồi trạng thái thế nào?
4. Destination có cần chặn stale A không?

### Bài 10 — ZooKeeper ephemeral sequential

Một leader election/lock recipe dùng ephemeral sequential znodes.

- Điều gì xảy ra khi session hết hạn?
- Tại sao worker cũ vẫn có thể chạy sau khi znode biến mất?
- Sequence numbers giúp xếp waiter nhưng có đủ cho external fencing không?
- Khi disconnect rồi reconnect cần đọc lại state ra sao?

### Bài 11 — Redis replication/failover

Một client dùng `SET NX PX` trên Redis có replication và failover.

1. Điều gì được atomic trong lệnh trên một instance?
2. Những điều gì phải đọc thêm trong replication/failover docs?
3. `WAIT` có tự chứng minh consensus lock không?
4. Nếu mục tiêu là một invoice FINAL duy nhất, có cách bảo vệ trực tiếp tại DB không?

### Bài 12 — Unknown outcome và retry

Client gửi `capturePayment(op-42)`, payment provider xử lý xong nhưng response mất.

- Tại sao timeout không chứng minh thất bại?
- Retry cần giữ token nào?
- Phải xác minh outcome bằng API/log nào?
- Nếu provider không hỗ trợ idempotency, ứng dụng có những rủi ro/bước đối soát gì?

### Bài 13 — Queue redelivery

Message M được A nhận, A pause quá visibility timeout, B nhận lại M.

1. Contract của queue có thể cho phép chuyện này không?
2. Nếu A/B cùng gọi external side effect, cần invariant gì?
3. Visibility heartbeat có thay fencing không?
4. Dedup ledger nên ở đâu?

### Bài 14 — Bảng evidence

Lập một bảng cho sản phẩm bạn chọn với:

~~~text
Product/version/driver
Operation and scope
Required guarantee
Official docs section
Configuration
Failure assumptions
What the docs do NOT guarantee
Fallback
Test scenario
~~~

Điền ít nhất năm claim về atomicity, availability/failover, durability, lease và retry. Không dùng một bài blog duy nhất làm nguồn.

### Bài 15 — Design review thực tế

Một hệ cần chạy batch tính khuyến mại theo ngày:

~~~text
4 worker instances
Multiple AZs
Batch execution: 2–5 minutes
Database stores final discount results
External email provider sends notification
Network can partition for 60 seconds
~~~

Hãy đề xuất:

1. Business invariants nào cần ưu tiên?
2. Cần lock/lease hay conditional finalization?
3. Nếu cần lease, renew và fencing ra sao?
4. Khi worker A pause hơn lease rồi resume, nó có thể gây lỗi gì?
5. Nếu email gửi thành công nhưng DB response mất, làm sao đối soát?
6. Tài liệu chính thức của những sản phẩm nào cần đọc?
7. Những lỗi nào nên được fault-injection test?
8. SLO latency, duplicate side effects và recovery cần được đo thế nào?

## 35. Mẫu kết quả design review hoàn chỉnh

Một bản tóm tắt có thể được viết theo cấu trúc:

~~~yaml
design: "invoice finalization"
invariant:
  - "at most one FINAL invoice per tenant-period"
  - "same logicalOperationId cannot produce duplicate effect"
  - "old owner cannot overwrite newer accepted result"
technology:
  databaseVersion: "pinned release"
  driverVersion: "pinned release"
  deploymentMode: "documented topology"
  consistencyConfiguration: "explicit"
productGuarantees:
  - claim: "conditional update of one item is atomic"
    scope: "one authoritative document"
    source: "official API section + version"
  - claim: "configured write ACK has documented durability"
    scope: "selected deployment mode"
    source: "official replication section + version"
notAssumed:
  - "lease expiry forcibly stops a paused worker"
  - "network timeout means no commit"
  - "external payment is in the DB transaction"
applicationSafeguards:
  - "unique business key"
  - "conditional finalization/version"
  - "operation ID and durable outcome lookup"
  - "fencing where external ownership applies"
  - "outbox and reconciliation"
failureTests:
  - "two concurrent finalizations"
  - "pause past lease duration"
  - "lost response after commit"
  - "leader failover / network partition"
  - "duplicate message delivery"
reviewTriggers:
  - "product/driver upgrade"
  - "region/topology or consistency setting change"
  - "new external side effect"
~~~

Đây là **mẫu báo cáo**; mọi claim trong tài liệu thực phải có nguồn chính thức cụ thể và được đánh giá theo phiên bản/cấu hình đang chạy.

## Kết luận

Trước khi tạo một distributed lock, bầu leader, dùng lease, CAS, TTL hay message queue để điều phối công việc, hãy **đọc hợp đồng giao thức của sản phẩm** và đối chiếu với bất biến nghiệp vụ cần bảo vệ.

Những điều quan trọng nhất:

- **Đặt invariant trước, chọn primitive sau.** Không dùng khóa chỉ vì có sẵn API `acquire()`.
- **Một guarantee luôn có scope.** Atomicity một key/document không tự biến workflow nhiều service thành transaction.
- **Lease expiry không dừng một worker cũ.** Process bị pause vẫn có thể resume và ghi vào destination.
- **Fencing cần được destination cưỡng chế**, đồng thời phải xác định rõ mức bảo vệ và thế hệ owner.
- **CAS/unique key có thể đơn giản hơn distributed lock** khi mục tiêu chỉ là một trạng thái cuối hợp lệ tại nguồn.
- **Timeout không có nghĩa chưa commit**; retry cần logical operation ID, idempotency và outcome reconciliation.
- **Replication, leader election, durability và read consistency là những hợp đồng riêng**; không suy ra lẫn nhau.
- **TTL cleanup không mặc nhiên là lease/lock protocol chính xác**; cần hiểu semantics của sản phẩm.
- **Queue redelivery và SDK automatic retry có thể tạo duplicate attempts**; ứng dụng phải bảo vệ business effect.
- **Phiên bản, topology, cấu hình và fault model là phần của hợp đồng**, không phải phần phụ.
- **Đọc nguồn chính thức, ghi rõ điều được bảo đảm và điều chưa được bảo đảm**, rồi kiểm chứng bằng history có dữ liệu, thời điểm và kết quả commit.

Câu hỏi đúng không phải “Sản phẩm có khóa phân tán không?”, mà là: **“Sản phẩm thực sự hứa điều gì cho operation này, dưới những lỗi nào, và những bất biến quan trọng nhất được cưỡng chế ở đúng ranh giới dữ liệu hay chưa?”**
