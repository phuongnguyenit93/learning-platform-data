# Tính sẵn sàng theo CAP và các chỉ số khả dụng vận hành

## 1. Khi dịch vụ còn chạy nhưng người dùng không thể hoàn thành công việc

Giả sử ứng dụng bán vé có hai vùng hạ tầng. Trong một sự cố kết nối:

- Người dùng vẫn xem được danh sách sự kiện từ cache.
- Một vùng vẫn trả kết quả tìm kiếm trong 100 ms.
- Chức năng giữ ghế cuối cùng từ chối giao dịch vì không đạt quorum.
- API health check trả HTTP 200 trên các máy còn chạy.
- Nhiều khách bị timeout ở bước checkout.

Vậy hệ có **tính sẵn sàng (availability)** hay không?

Phải phân biệt hai câu hỏi:

1. **Availability theo CAP:** Khi các phần của hệ phân tán mất liên lạc, thuật toán có tiếp tục đáp ứng những thao tác được yêu cầu tại các node không lỗi mà vẫn giữ nhất quán mạnh hay không?
2. **Operational availability:** Bao nhiêu phần trăm yêu cầu thực của người dùng được xử lý đúng, đủ nhanh, trong một khoảng thời gian đo?

Một hệ có thể tiếp tục đáp ứng một số yêu cầu theo mô hình eventual consistency nhưng vẫn có operational SLI rất thấp vì quá tải hoặc bug. Ngược lại, một hệ dùng quorum/consensus cho giao dịch quan trọng vẫn có thể đạt SLO uptime rất cao trong điều kiện bình thường.

Đây là bài học thuộc chương **CAP và các đánh đổi** của module **Database No SQL**. Mục tiêu là hiểu đúng hai nghĩa của availability, đánh giá hành vi khi mạng phân vùng và xây bộ chỉ số khả dụng phục vụ vận hành.

Sau bài này, bạn cần:

- Phân biệt CAP Consistency, Availability và Partition tolerance.
- Hiểu vì sao partition tạo đánh đổi giữa đáp ứng trên mọi phía và linearizability.
- Tránh gán nhãn CP/AP bất biến cho một thương hiệu database.
- Chọn chính sách cho từng thao tác: đọc catalog, giữ ghế, thanh toán, thu hồi quyền.
- Thiết kế SLI/SLO/SLA, error budget, burn rate, latency và freshness.
- Hiểu failover, RTO/RPO, degradation và những nguyên nhân outage ngoài CAP.
- Tạo metric, dashboard, cảnh báo và kiểm thử lỗi có thể kiểm chứng.

## 2. Định lý CAP đề cập những thuộc tính nào?

### 2.1. C — Consistency

Trong phát biểu CAP, Consistency có nghĩa mạnh, thường được mô tả bằng **linearizability**: các thao tác trên trạng thái chia sẻ có thể được sắp vào một thứ tự duy nhất phù hợp thứ tự thời gian thực giữa những thao tác không chồng lắp.

Ví dụ:

~~~text
Client A: PUT K=2 -> success.
Sau đó Client B: GET K -> ?
~~~

Nếu GET được hứa linearizable và không có mutation khác, B không được trả K=1 cũ sau khi PUT của A đã hoàn tất.

Điều này khác **eventual consistency**, nơi bản sao chưa bắt kịp có thể tạm trả K=1, nhưng phải hội tụ dưới những điều kiện cần thiết.

### 2.2. A — Availability

Availability theo mô hình CAP là một tính chất **liveness**: mỗi request nhận bởi một node không lỗi phải cuối cùng nhận phản hồi hợp lệ theo đặc tả thao tác.

Không thể đáp ứng ý nghĩa của availability chỉ bằng một lỗi hạ tầng tức thời:

~~~http
HTTP/1.1 503 Service Unavailable
~~~

Nếu một hệ không thể phục vụ phép đọc/ghi theo contract mà luôn trả 503, việc có response bytes không làm thao tác trở thành khả dụng.

Tuy vậy, cần phân biệt một **business rejection hợp lệ** với lỗi hệ thống. Ví dụ yêu cầu đặt ghế đã thuộc người khác có thể nhận conflict đúng nghiệp vụ. Điều đó không giống từ chối vì hệ mất quyền quyết định do partition.

### 2.3. P — Partition tolerance

Partition xảy ra khi thông điệp giữa các phần của hệ bị mất hoặc bị trì hoãn rất lâu, làm các node không thể trao đổi trạng thái cần thiết.

~~~text
Nhóm A: node 1, node 2  |  Nhóm B: node 3
                       X
               Không liên lạc
~~~

Node 3 vẫn có thể hoạt động và phục vụ client địa phương. Vấn đề là nó không biết chắc các mutation mới ở node 1, 2.

Một hệ phân tán thật không thể loại bỏ hoàn toàn khả năng partition bằng cách cấu hình “P=false”. Cần mô tả hành vi **khi partition xảy ra**.

### 2.4. Không phải “chọn hai trong ba” ở mọi thời điểm

Cách nói tắt “pick any two” dễ gây hiểu lầm. Điểm chính xác hơn là:

> **Khi mạng phân vùng, không thể đồng thời bảo đảm tính nhất quán mạnh và tính sẵn sàng theo nghĩa CAP trên mọi phía liên quan đến cùng trạng thái.**

Khi mạng hoạt động bình thường, nhiều hệ có thể vừa phục vụ request vừa giữ linearizability trong phạm vi đã thiết kế.

CAP cũng không nói rằng các hệ ưu tiên consistency luôn có downtime, hay hệ ưu tiên availability tự động có uptime cao.

## 3. Thí nghiệm hai bản sao bị phân vùng

Ban đầu:

~~~text
Replica A: K=0
Replica B: K=0
~~~

Mạng giữa A và B bị ngắt. Client X nói chuyện với A, Client Y nói chuyện với B.

~~~mermaid
flowchart LR
    X["Client X"] --> A["Replica A"]
    Y["Client Y"] --> B["Replica B"]
    A -.- P["Network partition"]
    P -.- B
~~~

### 3.1. Ghi ở phía A

~~~text
t1: X gửi PUT K=1 tới A.
t2: A không thể liên lạc với B.
~~~

Nếu A trả success ngay, B có thể chưa biết K=1.

### 3.2. Đọc ở phía B

Sau khi X nhận success, Y mới gửi GET K tới B.

Nếu B trả K=0, hệ không còn đáp ứng linearizability cho cặp thao tác ấy. Nếu B từ chối hoặc chờ cho tới khi xác minh được trạng thái, tính availability của GET ở B giảm.

### 3.3. Hai phía cùng ghi

~~~text
Partition còn xảy ra.
A: PUT K="red" -> success.
B: PUT K="blue" -> success.
~~~

Khi mạng được nối lại, hệ cần quy tắc xử lý xung đột: chọn winner, giữ conflict cho ứng dụng giải quyết, hoặc merge theo một kiểu dữ liệu phù hợp.

Việc hai phía trả success không đảm bảo **hai ý định người dùng đều được bảo toàn**.

### 3.4. Điều kiện quan trọng

Không phải một bên đã “làm sai” do lỗi logic đơn giản. Khi mất liên lạc, mỗi bên không thể biết chắc bên còn lại đã chết, bị nghẽn hay vẫn đang xử lý ghi. Sự bất định đó là nguồn gốc tradeoff CAP.

## 4. Availability theo CAP không phải chỉ số uptime

### 4.1. Phạm vi là một thuật toán phân tán

CAP nói về khả năng thuật toán phản hồi yêu cầu trong mô hình lỗi mạng. Nó không trực tiếp đo:

- Tỷ lệ HTTP 5xx.
- Thời gian gateway bị outage.
- p99 latency.
- Số khách hoàn tất checkout.
- Tỷ lệ container đang Running.

Đây là các quan sát vận hành.

### 4.2. “Eventually responds” không có deadline mặc định

Mô hình liveness không tự hứa phản hồi trong 200 ms, 2 giây hay 30 giây. Nhưng trong hệ bán vé, request mất 10 giây có thể đã vượt timeout của UI.

~~~text
CAP availability: Có phản hồi hợp lệ cuối cùng không?
Operational SLI: Có kết quả tốt trong deadline không?
~~~

### 4.3. Node không lỗi khác dịch vụ hoạt động

Một node có thể mất điện, đầy đĩa, hết connection pool hoặc chết do OOM. Một process có thể sống nhưng xử lý sai payload. Những lỗi ấy ảnh hưởng operational availability dù không nhất thiết là tình huống partition đặc trưng trong CAP.

### 4.4. Endpoint khác nhau có yêu cầu khác nhau

Một ứng dụng có thể chọn:

~~~text
GET /catalog      -> eventual, cho phép dữ liệu cũ có giới hạn.
GET /my-profile   -> yêu cầu read-your-writes.
POST /reserve     -> yêu cầu quyền quyết định nguyên tử.
POST /payment     -> không chấp nhận xác nhận trùng.
GET /analytics    -> chấp nhận watermark cập nhật trễ.
~~~

Không nên ép mọi thao tác vào một nhãn CP hoặc AP.

### 4.5. Stale read có thể hợp lệ ở đúng hợp đồng

Nếu endpoint tìm kiếm được định nghĩa là eventual, một kết quả chưa cập nhật trong thời gian ngắn có thể hợp lệ. Nếu endpoint đọc trạng thái giao dịch được hứa linearizable, một kết quả stale sau mutation đã hoàn tất là vi phạm.

**Không âm thầm nới hợp đồng consistency trong lúc outage rồi tự đánh giá request là tốt.**

## 5. Operational availability là gì?

Ở góc nhìn vận hành, một dịch vụ có khả dụng khi các tính năng mà người dùng cần được phục vụ theo **tiêu chí chất lượng** đã định nghĩa.

Ví dụ:

~~~text
Tìm sản phẩm: trả danh sách hợp lệ trong 500 ms.
Đặt ghế: trả kết quả đúng, không oversell trong 2 s.
Thu hồi token: token không còn được chấp nhận sau
              mốc revocation đã cam kết.
~~~

Một API trả 200 rất nhanh nhưng giá sai, booking không tồn tại hoặc trả dữ liệu đã thu hồi vẫn có thể là **bad event** theo nghiệp vụ.

### 5.1. Những nguyên nhân làm operational availability giảm

- Network partition hoặc route lỗi.
- Primary/leader failover.
- Replica lag hoặc quorum không đạt.
- Triển khai code sai.
- Query quá chậm, hot partition, compaction backlog.
- DNS, chứng chỉ, authentication, dependency không hoạt động.
- Throttling, rate limit, cạn CPU/memory/disk.
- Retry storm.
- Dữ liệu lỗi hoặc read model sai khiến người dùng không hoàn thành công việc.

Không phải nguyên nhân nào cũng có thể giải thích đơn giản bằng CAP.

### 5.2. Bảng phân biệt

| Tiêu chí | Availability theo CAP | Khả dụng vận hành |
|---|---|---|
| Câu hỏi | Trong partition, node có tiếp tục phục vụ thao tác mà vẫn giữ consistency mạnh không? | Người dùng có hoàn thành hành trình đúng hạn không? |
| Mô hình | Liveness và network partition | SLI, SLO, uptime, latency, correctness |
| Thời hạn | Không định nghĩa deadline cố định | Cần deadline, ví dụ 2 giây |
| Nguồn đo | Phân tích giao thức và lỗi | Edge telemetry, synthetic probes, tracing |
| Loại lỗi | Chủ yếu phân vùng kết nối trong định lý | Mọi dạng lỗi vận hành |
| Trạng thái 200 | Không đủ để suy kết luận | Có thể là good hoặc bad theo payload/deadline |
| Phạm vi | Thao tác trên trạng thái phân tán | Endpoint, Region, tenant, user journey |

## 6. Quorum ảnh hưởng khả dụng khi partition

### 6.1. Ví dụ ba bản sao

Giả sử một phép ghi có ba replica và cần hai xác nhận:

~~~text
RF=3
Write quorum=2

A <-> B liên lạc.
C bị cô lập.
~~~

Phía A+B có thể có đủ replica để tiếp tục những thao tác yêu cầu quorum theo giao thức phù hợp, còn phía chỉ có C không đủ.

Như vậy, **hệ còn phục vụ một phần của mạng** nhưng không thỏa availability trên mọi phía cho thao tác ấy.

### 6.2. W+R>N

Trong mô hình quorum cơ bản:

\[
W+R>N
\]

với:

- \(N\): số replica trong tập liên quan.
- \(W\): số xác nhận ghi cần thiết.
- \(R\): số replica tham gia đọc theo giao thức.

Điều kiện buộc tập đọc và ghi giao nhau nếu chúng lấy từ cùng tập N.

Ví dụ:

\[
N=3,\quad W=2,\quad R=2.
\]

Tập write quorum và read quorum có ít nhất một replica chung.

### 6.3. Giao tập không tự chứng minh linearizability

Công thức trên không đủ trong mọi hệ vì:

- Có thể có concurrent writers.
- Replica dùng timestamp/conflict resolution riêng.
- Membership thay đổi trong failover.
- Một số kiểu quorum có tập replica thực tế khác nhau.
- Multi-Region local quorum khác global quorum.
- Reader phải hòa giải những giá trị đã đọc theo giao thức.
- Transaction có thể cần isolation mạnh hơn single-key replica semantics.

Không nên dùng mỗi W+R>N để tuyên bố database luôn strong consistent.

### 6.4. Quorum có giá latency

Nếu cần hai replica ACK mà một replica chậm, request có thể phải đợi thêm so với chỉ cần một ACK. Đổi lại, quorum có thể đem lại bảo đảm mạnh hơn tùy hệ.

~~~text
Replica A trả sau 5 ms.
Replica B trả sau 12 ms.
Replica C trả sau 200 ms.
~~~

Một giao thức cần 2 ACK có thể hoàn tất sau A+B, còn giao thức đợi cả 3 có thể bị ảnh hưởng bởi C. Đây là ví dụ trực quan, không phải mô tả chính xác scheduler của mọi database.

### 6.5. Không đủ quorum nhưng node vẫn sống

Một node ở phía minority vẫn có thể đọc file trên đĩa và nhận TCP connection. Nếu không được phép commit, nó có thể trả lỗi hoặc chờ.

Đó là hành vi đúng khi hệ chọn bảo vệ consistency, không phải bằng chứng node đã chết.

## 7. CP và AP là cách mô tả lựa chọn trong một tình huống

### 7.1. Khi ưu tiên consistency

Nếu các node không đủ khả năng phối hợp để quyết định một cập nhật duy nhất, hệ có thể:

- Từ chối thao tác nhạy cảm.
- Chờ khôi phục quorum/leader.
- Chuyển request tới phía có quyền quyết định.

Các thao tác ấy mất availability tại một số vị trí hoặc thời điểm.

### 7.2. Khi ưu tiên availability

Một phía có thể tiếp tục phục vụ stale reads hoặc chấp nhận ghi local để đồng bộ sau, nếu hợp đồng nghiệp vụ cho phép.

Hệ phải xác định:

- Cách hòa giải ghi đồng thời.
- Dữ liệu nào được phép stale.
- Sự kiện/notification nào có thể xảy ra hai lần.
- Cách giải quyết các giao dịch đã được xác nhận ở hai phía.

### 7.3. Một lựa chọn có thể khác theo thao tác

| Tính năng | Lựa chọn khi partition |
|---|---|
Xem catalog | Có thể trả cache stale có nhãn |
Tìm kiếm | Có thể dùng index local nếu freshness policy cho phép |
Lưu nháp offline | Giữ local và sync sau |
Đặt ghế cuối | Chờ/từ chối nếu không thể xác minh owner |
Chuyển tiền | Không commit nếu không bảo vệ invariant |
Thu hồi quyền truy cập | Không dùng cache stale để tiếp tục cấp quyền |

### 7.4. Fail-open và fail-closed

**Fail-open:** Tiếp tục trên dữ liệu local hoặc với bảo đảm giảm đi. Phù hợp một số tính năng thông tin.

**Fail-closed:** Không thực thi thao tác khi thiếu điều kiện an toàn. Phù hợp nhiều thao tác security và giao dịch nhạy cảm.

Fail-closed có thể giảm availability tức thời nhưng bảo vệ safety. Một business rejection đúng vì ghế đã có owner khác không giống việc fail-closed do hệ không xác minh được ghế.

### 7.5. Không gán nhãn hãng database tuyệt đối

MongoDB, DynamoDB, Cassandra/ScyllaDB, Redis và những hệ NoSQL khác có replication, consistency levels, transaction/conditional-write và topology riêng.

Cùng một database có thể cho:

- Đọc eventual.
- Đọc mạnh hơn trong phạm vi hỗ trợ.
- Ghi có điều kiện trên một item.
- Transaction nhiều item trong phạm vi khác.

Vì vậy kết luận “database này AP nên mọi operation luôn available” là không chính xác.

## 8. Ví dụ hệ họ Cassandra/ScyllaDB

### 8.1. Consistency levels

Một bảng với RF=3 có thể được đọc/ghi theo các mức như ONE hoặc QUORUM tùy API và cấu hình.

~~~text
Write ONE:
  Có thể ACK khi một replica đáp ứng đủ điều kiện.

Write QUORUM:
  Cần đa số theo phạm vi replica của truy vấn.
~~~

Khi mất liên lạc với một số replica, mức consistency đã chọn ảnh hưởng liệu request có thể hoàn tất.

### 8.2. Cảnh báo về dữ liệu cũ

Một replica nhận ít mutation hơn có thể trả stale data ở đường đọc mức yếu. Hinted handoff và anti-entropy repair là các cơ chế liên quan tới quá trình hội tụ, nhưng có phạm vi và retention riêng.

### 8.3. LWT có đánh đổi khác

Nếu ứng dụng dùng INSERT IF NOT EXISTS để giành unique username, hệ cần một cơ chế phối hợp mạnh hơn so với ghi không điều kiện. Không nên suy rằng lightweight transaction có cùng availability khi partition với một write ONE thông thường.

### 8.4. Lỗi hiệu năng cũng gây outage

Partition rất lớn, tombstone-heavy query, compaction backlog, repair quá tải hoặc disk gần đầy có thể gây latency cao và timeout dù mạng đang hoạt động.

Điều này minh họa vì sao CAP không thay metric vận hành.

## 9. Ví dụ MongoDB

### 9.1. Replica set và write concern

MongoDB replica set có primary và secondary. Khi ghi yêu cầu majority write concern, thao tác phải đạt mức xác nhận theo hợp đồng majority trong cấu hình hỗ trợ.

Nếu không đủ thành viên đáp ứng yêu cầu ghi, request có thể timeout hoặc lỗi. Việc từ chối đó giúp tránh tuyên bố một ghi có mức bảo đảm mà hệ chưa đạt.

### 9.2. Secondary lag

~~~text
Primary:   profile version 12.
Secondary: profile version 11.
~~~

Một đọc từ secondary có thể thấy version 11. Nếu người dùng vừa sửa hồ sơ rồi phải nhìn thấy version 12, cần read concern, read preference và session semantics phù hợp.

### 9.3. Failover và operational SLI

Khi primary mất, election có thể gây một giai đoạn không ghi được. Đo:

- Thời gian từ mất primary đến ghi lại được.
- Số request timeout.
- Write đang bay có unknown outcome không.
- Driver retry có idempotent không.
- Có ghi đã ACK nào chịu rủi ro rollback theo cấu hình không.

### 9.4. Không nói MongoDB luôn CP trong mọi cấu hình

Read preferences, write concerns, transactions, replica set và sharding mang tới các bảo đảm khác nhau. Hãy mô tả cụ thể operation và topology.

## 10. Ví dụ DynamoDB

### 10.1. Read consistency

DynamoDB có eventual reads và strong reads trong những phạm vi API hỗ trợ. Global Secondary Index chỉ có eventually consistent reads.

~~~text
PutItem vào bảng chính -> success.
Query GSI ngay sau đó  -> có thể chưa thấy item.
~~~

Điều này không có nghĩa PutItem đã thất bại. GSI là một access path được đồng bộ bất đồng bộ.

### 10.2. Không dùng GSI để quyết định unique username

Nếu GSI còn lag, hai request cùng query thấy username chưa tồn tại. Để chỉ một owner thắng, dùng conditional write/transaction trên item claim có khóa nghiệp vụ trong phạm vi đảm bảo của DynamoDB.

### 10.3. Global Tables

Các chế độ Global Tables có consistency và replication semantics riêng. Với multi-Region eventual, ghi đồng thời cùng item ở hai Region có thể cần conflict resolution.

Không mặc định một conditional write local tạo global serializability trong mọi chế độ.

### 10.4. Availability vận hành

Một managed database vẫn có thể bị ứng dụng dùng sai khiến request không thành công:

- Hot partition.
- Throttling.
- Giới hạn request.
- IAM/credential sai.
- Client retries quá mạnh.
- Dependency mạng hoặc SDK timeout không hợp lý.

Đo toàn bộ hành trình người dùng, không chỉ service status của nhà cung cấp.

## 11. Ví dụ Redis và search engine

### 11.1. Redis replica

Với async replication, một replica Redis có thể chưa thấy SET mới ở primary. Nếu failover xảy ra trước khi trạng thái được bảo vệ theo mức mong muốn, có thể xuất hiện rủi ro mất thay đổi, tùy persistence/replication policy.

Một câu trả lời SET OK trên một node không tự biến thành bảo đảm consensus trên toàn cụm.

### 11.2. Redis cache khi nguồn không liên lạc được

API có thể phục vụ catalog từ cache cũ, nhưng cần chính sách về tuổi dữ liệu. Không nên dùng cache đó để xác nhận token đã được thu hồi hay số dư hiện tại nếu invariant không cho phép stale.

### 11.3. Search index

Elasticsearch/OpenSearch có refresh semantics. Một document đã được index nhưng search query có thể chưa nhìn thấy ngay. Đây là **freshness/visibility lag**, không nhất thiết là downtime của endpoint query.

### 11.4. Tách hai SLI

~~~text
Search availability SLI:
  Tỷ lệ query hợp lệ hoàn tất trong 500 ms.

Search freshness SLI:
  Tỷ lệ cập nhật được query nhìn thấy trong 5 giây
  sau source commit.
~~~

Search có thể rất nhanh nhưng dữ liệu mới bị trễ, nên một SLI không thay thế SLI còn lại.

## 12. PACELC: đánh đổi ngay cả khi không partition

CAP nhấn mạnh trường hợp partition. **PACELC** là một khung tư duy bổ sung:

~~~text
If Partition:
    Availability versus Consistency.
Else:
    Latency versus Consistency.
~~~

Ví dụ:

- Đợi nhiều replica xác nhận có thể tăng chi phí latency.
- Đọc local cache nhanh hơn nhưng dữ liệu có thể cũ.
- Đọc xuyên Region từ nguồn có thẩm quyền thường có chi phí mạng cao hơn.

PACELC không phải bảng xếp hạng các hãng database. Một sản phẩm có nhiều lựa chọn theo operation.

### 12.1. Thêm một chiều quan trọng: correctness

Một hệ có thể rất nhanh và gần như luôn trả success nhưng xác nhận trùng ghế. Đó không phải một giải pháp tốt.

Khi đánh đổi, phải xem đồng thời:

~~~text
Availability
Latency
Freshness
Durability
Business correctness
Operational cost
~~~

## 13. SLI, SLO, SLA

### 13.1. SLI — Service Level Indicator

SLI là phép đo chất lượng dịch vụ. Ví dụ:

~~~text
Tỷ lệ checkout requests hợp lệ được phục vụ
với kết quả đúng trong tối đa 2.000 ms.
~~~

SLI cần có tử số, mẫu số, điều kiện good/bad, nguồn dữ liệu và cửa sổ đo.

### 13.2. SLO — Service Level Objective

SLO là mục tiêu cho một SLI:

~~~text
Trong rolling 30 ngày:
  Ít nhất 99,9% eligible checkout requests
  phải được xử lý đúng trong 2.000 ms.
~~~

### 13.3. SLA — Service Level Agreement

SLA là thỏa thuận với khách hàng hoặc đối tác, có thể quy định cách tính, phạm vi, ngoại lệ và hậu quả khi không đạt.

SLA không chỉ là SLO được đổi tên. SLO nội bộ có thể chặt hơn SLA.

### 13.4. KPI hạ tầng không tự là SLI

Các metric CPU, RAM, số container Running, disk utilization và leader election rất hữu ích để điều tra. Nhưng CPU 20% không chứng minh khách có thể thanh toán.

Một SLI tốt nên đo **đầu ra người dùng quan tâm**.

## 14. Request-based availability SLI

### 14.1. Công thức

\[
\text{Availability SLI}
=\frac{\text{good eligible requests}}
{\text{all eligible requests}}\times100\%.
\]

Ví dụ:

~~~text
Eligible checkout requests: 2.000.000
Good:                       1.999.000
Bad:                            1.000
~~~

\[
\frac{1.999.000}{2.000.000}\times100\%
=99,95\%.
\]

### 14.2. Good event cần được định nghĩa rõ

Ví dụ:

~~~text
Good checkout request =
  request hợp lệ theo contract
  AND trả kết quả đúng nghiệp vụ
  AND latency <= 2.000 ms.
~~~

Nếu backend trả 200 sau 10 giây trong khi UI timeout ở 2 giây, không nên coi hành trình đó là thành công từ góc nhìn người dùng.

### 14.3. Không phải mọi HTTP 4xx đều là bad

Ghế đã được khách khác giữ trước có thể nhận 409 hợp lệ. Một yêu cầu sai format có thể nhận 422 đúng. Đây không nhất thiết là outage.

Tuy vậy, một 409 do race khiến hệ tạo hai reservation rồi phát hiện lỗi sau đó **không nên tự được tính good**. Phải phân loại theo domain, không chỉ status code.

### 14.4. HTTP 200 có thể vẫn bad

Ví dụ:

~~~json
{
  "reservationId": null,
  "status": "CONFIRMED"
}
~~~

Nếu payload tuyên bố đã xác nhận nhưng không có reservation bền vững, đây là lỗi correctness dù response code 200.

### 14.5. Chọn mẫu số minh bạch

Cần ghi rõ có tính:

- Timeout ở edge.
- Client abort.
- Synthetic requests.
- Invalid input.
- Rate-limited requests.
- Traffic từ bot.
- Health checks.
- Kỳ triển khai hoặc bảo trì.

Không được âm thầm loại request ở Region đang lỗi chỉ để tăng phần trăm.

## 15. Time-based availability và uptime

### 15.1. Công thức

\[
\text{Time Availability}
=\frac{\text{thời gian đạt trạng thái good}}
{\text{toàn bộ thời gian quan sát}}\times100\%.
\]

Nếu trong 720 giờ, hệ đạt trạng thái tốt 717 giờ:

\[
\frac{717}{720}\times100\%
\approx99,5833\%.
\]

### 15.2. Định nghĩa trạng thái “up”

Một /health trả 200 chỉ có thể chứng minh process còn chạy. Muốn đo đường phục vụ, synthetic check nên thử hành trình đại diện: tìm sản phẩm, đọc booking hoặc tạo/xóa test record theo cách không gây side effect ngoài ý muốn.

### 15.3. Hai phương pháp có thể cho kết quả khác nhau

Trong 23 giờ đầu có ít traffic và không lỗi. Trong giờ flash sale cuối, 30% checkout requests lỗi. Một time-based probe thưa có thể phản ánh sự cố khác request-based SLI, vốn tính đúng số request bị ảnh hưởng.

Ngược lại, nếu hệ ngừng hoạt động lúc 3 giờ sáng không có request, request-based SLI có thể không ghi nhận bad event, nhưng synthetic time-based probe có thể phát hiện.

### 15.4. Low-traffic service

API có 20 request/ngày, một request lỗi làm availability ngày chỉ còn 95%. Mẫu nhỏ khiến tỷ lệ dao động mạnh.

Cân nhắc cửa sổ dài hơn, synthetic probes và số mẫu tối thiểu. Không tự gán 100% khi mẫu số bằng 0.

## 16. Quy đổi uptime thành downtime trong 30 ngày

Giả sử 30 ngày = 720 giờ = 43.200 phút:

| Availability | Tỷ lệ downtime | Downtime tương đương |
|---|---:|---:|
| 99% | 1% | 432 phút = 7 giờ 12 phút |
| 99,5% | 0,5% | 216 phút = 3 giờ 36 phút |
| 99,9% | 0,1% | 43,2 phút |
| 99,95% | 0,05% | 21,6 phút |
| 99,99% | 0,01% | 4,32 phút |
| 99,999% | 0,001% | 0,432 phút = 25,92 giây |

### 16.1. Công thức

\[
\text{Allowed downtime}
=(1-\text{SLO fraction})\times\text{window duration}.
\]

Ví dụ:

\[
(1-0,999)\times43.200=43,2\text{ phút}.
\]

### 16.2. Giới hạn của phép quy đổi

Bảng trên áp dụng cho **time-based availability** trong cửa sổ đã cho. Một SLO request-based 99,9% không quy đổi thành chính xác 43,2 phút downtime khi lưu lượng giữa các giờ khác nhau.

### 16.3. Cái giá của thêm một số 9

Từ 99,9% lên 99,99% giảm downtime cho phép từ 43,2 phút xuống 4,32 phút: khắt khe gấp 10 lần theo tỷ lệ lỗi.

Chi phí có thể đến từ failover, test disaster recovery, giảm dependency, thay đổi triển khai, runbook, quan sát tail latency và hạ tầng đa vùng.

## 17. Error budget

### 17.1. Ngân sách lỗi

Với SLO 99,9%, tỷ lệ bad event được phép là:

\[
1-0,999=0,001=0,1\%.
\]

Nếu có 2 triệu eligible requests trong kỳ:

\[
2.000.000\times0,001=2.000
\]

bad requests là ngân sách theo cách tính minh họa. Nếu đã có 1.000 bad requests, còn 1.000 trong cùng cửa sổ và mẫu số giả định.

### 17.2. Error budget không phải giấy phép làm sai dữ liệu

Ngân sách lỗi giúp quản lý mức độ rủi ro và tốc độ thay đổi hệ thống. Nó không cho phép cố tình tạo double charge hoặc vi phạm quyền truy cập chỉ vì SLI chung còn đạt mục tiêu.

Integrity và security invariant phải được quản lý riêng, có thể nghiêm trọng dù số lượng lỗi rất ít.

### 17.3. Burn rate

\[
\text{Burn rate}
=\frac{\text{observed bad fraction}}
{\text{allowed bad fraction}}.
\]

Ví dụ SLO 99,9% cho phép 0,1% bad. Trong một giờ có 1% request bad:

\[
\text{Burn rate}=\frac{0,01}{0,001}=10.
\]

Error budget đang bị tiêu thụ với tốc độ gấp 10 lần tỷ lệ cho phép trung bình trong khoảng đo đó.

### 17.4. Tỷ lệ và số lượng tuyệt đối

Một endpoint chỉ có 10 request, một request lỗi tạo bad fraction 10%. Với 1 triệu request, 1% bad ảnh hưởng 10.000 request.

Để cảnh báo đúng, nên nhìn:

- Burn rate.
- Số request bị lỗi.
- Traffic và tính nghiêm trọng của hành trình.
- Tính liên tục của lỗi qua nhiều cửa sổ.

### 17.5. Multi-window alerts

Cửa sổ ngắn giúp phát hiện sự cố cấp tính; cửa sổ dài giảm báo động do một vài outlier. Chọn ngưỡng và thời lượng theo traffic thực thay vì một công thức cố định cho mọi service.

## 18. Latency và brownout

### 18.1. HTTP success cao vẫn có thể mất khả dụng

~~~text
HTTP 200 rate: 99,99%.
20% requests: latency > 8 giây.
Client timeout: 2 giây.
~~~

Từ góc nhìn ứng dụng backend, nhiều request cuối cùng thành công. Từ góc nhìn khách hàng, chúng đã thất bại vì quá thời gian chờ.

Đây là ví dụ **brownout**: hệ không tắt hoàn toàn nhưng chất lượng suy giảm nghiêm trọng.

### 18.2. Các phân vị latency

| Phân vị | Ý nghĩa |
|---|---|
| p50 | 50% request có latency không lớn hơn mốc |
| p95 | 95% request không lớn hơn mốc |
| p99 | 99% request không lớn hơn mốc |
| max | Request chậm nhất trong mẫu |

Một API trung bình 100 ms nhưng p99 8 giây có thể không đáp ứng trải nghiệm yêu cầu.

### 18.3. Không lấy trung bình p99 của từng node

p99 toàn dịch vụ không bằng trung bình cộng p99 của các node. Cần histogram/distribution được tổng hợp đúng, theo cùng định nghĩa request và cửa sổ.

### 18.4. Deadline end-to-end

Nếu checkout gọi:

~~~text
Gateway -> Auth -> Inventory -> Payment
~~~

latency end-to-end gồm thời gian mạng, queue, các dependency và retry. Một DB query chỉ mất 30 ms không chứng minh checkout đạt ngưỡng 2 giây.

### 18.5. Tail latency khi chờ quorum

Một request cần nhiều replica phản hồi có thể bị ảnh hưởng bởi replica chậm, tùy protocol. Hedged reads hoặc speculative retries có thể giảm latency trong một số đường đọc nhưng cũng tăng tải.

Không nhân bản request không kiểm soát khi hệ đã overload: có thể tạo retry storm.

## 19. Health checks và synthetic monitoring

### 19.1. Liveness

Liveness hỏi:

> Process còn có khả năng tiếp tục chạy không?

Nếu liveness phụ thuộc cứng vào mọi dịch vụ ngoài, một database chậm tạm thời có thể khiến cả cụm ứng dụng bị restart liên tục.

### 19.2. Readiness

Readiness hỏi:

> Instance có thể nhận traffic cho đường phục vụ được giao không?

Có thể xem connection pool, cấu hình, initialization, trạng thái draining và khả năng đáp ứng với tải hiện tại.

### 19.3. Deep health

Deep health có thể gọi một thao tác thật nhưng cần cân nhắc chi phí và tránh khiến chính health checks làm hệ quá tải.

### 19.4. Synthetic journey

Thay vì chỉ GET /health:

1. Đăng nhập bằng test account.
2. Tìm một product có sẵn.
3. Đọc thông tin cần thiết.
4. Tạo một reservation test idempotent nếu môi trường hỗ trợ.
5. Hủy/cleanup và ghi lại thời gian từng bước.

Không dùng thẻ thanh toán thật hoặc dữ liệu khách hàng thật trong synthetic probes.

### 19.5. Multi-location checks

Probe từ một Region không phát hiện được mọi lỗi ở Region khác. Có thể triển khai probes ở nhiều vị trí, nhưng phải tách lỗi của chính probe/network khỏi lỗi của hệ mục tiêu.

## 20. Success rate theo hành trình nghiệp vụ

### 20.1. Một SLI toàn bộ API có thể che tính năng quan trọng

Giả sử mỗi ngày:

~~~text
10 triệu GET catalog gần như không lỗi.
100.000 POST checkout có 10% lỗi.
~~~

Tổng tỷ lệ HTTP success có thể vẫn rất cao do catalog chiếm phần lớn traffic, nhưng doanh thu và trải nghiệm bị ảnh hưởng nặng.

### 20.2. Nên tách SLI

| Journey | Good event minh họa |
|---|---|
Tìm sản phẩm | Kết quả hợp lệ dưới 500 ms |
Xem sơ đồ ghế | Danh sách hợp lệ dưới 800 ms, có freshness metadata |
Giữ ghế | Chỉ một owner thắng, phản hồi đúng dưới 2 s |
Thanh toán | Không double charge; kết quả có thể đối soát |
Xem booking | Đọc được booking đã commit theo RYW contract |
Hủy booking | Trạng thái hủy bền vững và truy vấn được |

### 20.3. Business rejection có thể là good

Nếu ghế đã bán trước khi request đến, trả conflict hợp lệ là hành vi đúng. Nhưng một conflict xuất hiện do hệ đã cho hai khách cùng xác nhận ghế là lỗi.

Không dùng một bảng mã HTTP duy nhất để thay cách hiểu domain outcome.

### 20.4. Đo ở edge/client

~~~text
Edge timeout sau 2 giây.
Backend commit ở giây 3.
Client retry.
~~~

Metric backend ghi success nhưng người dùng đã thấy lỗi. Retry không idempotent có thể tạo double booking/payment.

Kết hợp edge telemetry, trace, domain outcome và idempotency status để đo đúng.

### 20.5. HTTP 202 không tự là hoàn tất

Một API có thể trả:

~~~json
{
  "requestId": "REQ-1001",
  "status": "QUEUED"
}
~~~

Điều này chỉ có nghĩa công việc đã được chấp nhận theo contract. Cần SLI bổ sung cho **tỷ lệ job đạt terminal outcome đúng trong deadline**. Đổi mọi 503 thành 202 nhưng làm mất queue không phải cải thiện availability thật.

## 21. Composite availability: nhiều dependency bắt buộc

### 21.1. Critical path

Một checkout có thể đi qua:

~~~text
Gateway
   |
   v
Authentication
   |
   v
Inventory
   |
   v
Order database
   |
   v
Payment provider
~~~

Nếu mỗi dependency là bắt buộc và một dependency không phục vụ, checkout có thể thất bại dù những thành phần còn lại khỏe.

### 21.2. Ví dụ nhân xác suất dưới giả định độc lập

Giả sử ba dependency bắt buộc **độc lập** và mỗi dependency có xác suất available 99,9% cho một yêu cầu tương ứng:

\[
P(\text{all good})=0,999^3\approx0,997003.
\]

Tỷ lệ tương đương khoảng **99,7003%**, thấp hơn 99,9% của từng dependency.

Đây chỉ là phép tính minh họa. Trong thực tế lỗi thường **tương quan**, chẳng hạn cùng nằm trong một Region, DNS, mạng hoặc một bản deploy. Khi đó không được nhân xác suất một cách mù quáng.

### 21.3. Fallback có thể giảm coupling

Nếu recommendation service lỗi, checkout có thể không cần chờ. Nếu search lỗi, catalog có thể tạm phục vụ từ cache với độ mới chấp nhận được.

Nhưng nếu inventory service lỗi, không nên trả “bán thành công” dựa trên tồn kho stale chỉ để tăng success rate.

### 21.4. Cắt dependency khỏi đường đồng bộ

Analytics và email confirmation thường có thể xử lý qua outbox/event worker sau khi transaction nguồn đã commit.

~~~mermaid
flowchart TD
    A["Checkout API"] --> B["Transaction nguồn"]
    B --> C["Commit Order + Outbox"]
    C --> D["Trả kết quả có thể kiểm chứng"]
    C --> E["Event worker"]
    E --> F["Email"]
    E --> G["Analytics"]
    E --> H["Search projection"]
~~~

Nếu email provider chậm, checkout không nhất thiết phải mất availability. Tuy nhiên worker vẫn cần retry, idempotency và giám sát backlog.

### 21.5. Hệ bất đồng bộ cũng có SLO

Tách dependency khỏi synchronous path không có nghĩa bỏ qua nó:

~~~text
99,9% outbox events được xử lý trong 1 phút.
99% search updates visible trong 5 giây.
99,9% emails hợp lệ được xử lý theo policy.
~~~

Đây là các ví dụ mục tiêu, không phải bảo đảm mặc định của một database.

## 22. Replication, fault domain và giới hạn của “thêm node”

### 22.1. Replication

Thêm bản sao có thể giảm rủi ro mất dịch vụ khi một node chết, nhưng còn tùy:

- Bản sao có nằm ở fault domain độc lập không?
- Client có thể kết nối và chuyển sang bản sao khỏe không?
- Ghi phải đợi bao nhiêu ACK?
- Replica lag có được phép phục vụ không?
- Hệ có quản lý membership/failover an toàn không?

Ba replica trên cùng một máy vật lý không bảo vệ khỏi lỗi máy ấy. Ba replica cùng Availability Zone có thể cùng chịu ảnh hưởng một sự cố vùng.

### 22.2. Multi-AZ

Phân tán qua nhiều Availability Zone giúp giảm xác suất cùng mất khả năng phục vụ do lỗi hạ tầng cục bộ. Tuy nhiên tăng network hops và đòi thiết kế quorum, routing và capacity khi một AZ bị mất.

### 22.3. Multi-Region

Nhiều Region có thể hỗ trợ disaster recovery hoặc phục vụ khách ở gần, nhưng tạo thêm:

- Cross-Region replication lag.
- Chi phí mạng.
- Failover và DNS propagation.
- Conflict resolution nếu active-active.
- RTO/RPO.
- Nguy cơ split-brain nếu hai Region tự cho mình là nguồn có thẩm quyền.

### 22.4. Không phải multi-Region nghĩa toàn hệ luôn ghi được

Trong partition, nếu chỉ Region có leader/quorum hợp lệ được commit, Region khác có thể phải từ chối. Đây là tradeoff bảo vệ invariant, không phải kiến trúc thất bại.

### 22.5. Replication không thay thế backup

Nếu một lệnh DELETE sai được nhân bản tới mọi replica, replication giữ các bản sao nhất quán với **một quyết định sai**. Backup/snapshot giúp khôi phục trạng thái lịch sử, nhưng restore cần đối soát quyết định xóa hợp lệ xảy ra sau snapshot.

## 23. RTO và RPO: hai mục tiêu phục hồi khác nhau

### 23.1. RTO — Recovery Time Objective

**RTO** là thời gian mục tiêu để khôi phục khả năng phục vụ sau sự cố.

Ví dụ:

~~~text
Mục tiêu RTO checkout: 10 phút.
~~~

Nếu checkout không hoạt động lúc 09:00 và phục vụ lại đúng hợp đồng lúc 09:07, thời gian gián đoạn quan sát được khoảng 7 phút trong tình huống đó.

### 23.2. RPO — Recovery Point Objective

**RPO** là lượng mất dữ liệu có thể chấp nhận, biểu diễn bằng khoảng thời gian giữa trạng thái khôi phục và trạng thái mới nhất cần bảo vệ.

Ví dụ:

~~~text
RPO mục tiêu 5 phút trong một kịch bản disaster recovery.
~~~

Điều này nghĩa kiến trúc được thiết kế để hạn chế mức mất mutation theo mục tiêu đó. Không được hiểu là luôn mất đúng 5 phút hoặc lúc nào cũng đáp ứng nếu không kiểm thử.

### 23.3. So sánh

| Khía cạnh | RTO | RPO |
|---|---|---|
| Câu hỏi | Bao lâu phục vụ lại? | Có thể mất bao nhiêu dữ liệu? |
| Loại mục tiêu | Khả dụng/khôi phục | Durability và integrity |
| Phụ thuộc | Failover, routing, runbook, capacity | Replication, WAL, backup, commit policy |
| Rủi ro | Outage kéo dài | Mất mutation đã được nhận |

### 23.4. Failover nhanh nhưng mất ghi

~~~text
Primary ACK một payment record.
Replica dự phòng chưa nhận mutation.
Primary hỏng.
Replica được nâng vai trò trong 5 giây.
~~~

Service có thể có **RTO tốt** nhưng trạng thái payment quan trọng bị thiếu. Với thanh toán, rủi ro ấy có thể không chấp nhận được.

Không nên chọn failover chỉ theo tốc độ mà bỏ qua **nguồn sự thật nào được khôi phục**.

### 23.5. RTO hoàn tất khi chức năng phục vụ đúng

Process khởi động xong không tự nghĩa checkout đã phục hồi. Cần xác minh:

- Routing hoạt động.
- Đọc/ghi đạt consistency đã chọn.
- Không có stale leader tiếp tục commit.
- Unknown-outcome requests được đối soát.
- Cache/read models đủ đáp ứng hành trình.

## 24. Availability và tính toàn vẹn của giao dịch

### 24.1. Safety và liveness

Hai nhóm yêu cầu:

**Safety:** Không bao giờ có hai booking được xác nhận cho cùng một ghế; không tạo double charge; không cấp quyền trái phép.

**Liveness:** Yêu cầu hợp lệ có thể hoàn tất; hệ không kẹt mãi nếu điều kiện hạ tầng cuối cùng phục hồi.

Một giải pháp chỉ quan tâm liveness có thể trả success nhanh nhưng vi phạm safety. Một giải pháp chỉ bảo vệ safety mà không có phương án phục hồi có thể kẹt quá lâu.

### 24.2. Sự hội tụ không sửa được mọi hậu quả

~~~text
Region A bán Seat S1 cho O1.
Region B bán Seat S1 cho O2.
Hai bên cùng gửi email xác nhận.
Sau đó LWW giữ O2 trong database.
~~~

Dữ liệu cuối hội tụ về một trạng thái, nhưng O1 đã được xác nhận và có thể đã thanh toán. Conflict resolution ở storage không tự hoàn tác email hoặc giao dịch bên ngoài.

### 24.3. Reservation có thẩm quyền

Có thể dùng:

- Conditional write bảo vệ một claim theo khóa ghế/sự kiện.
- Transaction trong phạm vi hệ hỗ trợ.
- Một leader/quorum quyết định quyền sở hữu.
- Phân bổ hạn mức tồn kho trước cho từng Region, nếu có thiết kế chống vượt tổng.

Không dùng hai PUT độc lập rồi kết luận cả hai không thể cùng thắng.

### 24.4. Kết quả không rõ sau timeout

~~~text
Client gửi POST /reserve.
Server commit thành công.
Response bị mất.
Client thấy timeout.
~~~

Client không biết thao tác đã commit hay chưa. Retry phải dùng requestId/operationId ổn định, có cách truy vấn trạng thái và không tạo reservation thứ hai.

### 24.5. Error budget không áp dụng kiểu “cho phép 0,1% oversell”

Một SLO request success rate cho phép một số request lỗi theo budget. Điều này **không có nghĩa** cho phép cùng tỷ lệ giao dịch sai tiền hoặc bán trùng ghế.

Integrity invariant cần thước đo, cảnh báo và xử lý riêng, có thể là mục tiêu không chấp nhận vi phạm.

## 25. Graceful degradation trong sự cố

### 25.1. Read-only mode

Nếu đường ghi không đạt quorum nhưng cache đọc còn sử dụng được, ứng dụng có thể chuyển sang read-only với thông báo rõ:

~~~json
{
  "serviceMode": "READ_ONLY",
  "asOf": "2026-11-14T09:00:00Z",
  "message": "Đang bảo trì khả năng đặt vé; có thể xem danh sách."
}
~~~

Không nên cung cấp dữ liệu stale như trạng thái hiện tại nếu policy không cho phép.

### 25.2. Tạm xếp hàng

Một thao tác có thể được đưa vào queue bền vững và trả 202, nếu người dùng chấp nhận kết quả chưa hoàn tất:

~~~text
PENDING
  -> PROCESSING
  -> CONFIRMED hoặc FAILED
~~~

Queue cần:

- Durability.
- Deadlines.
- Idempotency.
- Retry với backoff.
- Status query.
- Reconciliation.

Không biến một 503 thành 202 chỉ để SLI đẹp hơn khi hệ không thật sự giữ hoặc xử lý được request.

### 25.3. Stale cache có tuổi tối đa

Một chính sách:

~~~text
Catalog cache:
  có thể phục vụ nếu tuổi <= 10 phút;
  trả age/asOf trong response.

Inventory checkout:
  không dùng cache stale làm nguồn chốt.
~~~

Mức 10 phút là ví dụ, phải chọn theo nghiệp vụ.

### 25.4. Fail-closed đúng lúc

Với thu hồi quyền, nếu cache chứa token còn hạn nhưng nguồn đã revoke, tiếp tục cấp quyền chỉ vì nguồn không liên lạc có thể sai. Một deletion/revocation gate với consistency phù hợp giúp bảo vệ.

### 25.5. Degradation cần được đo

Một hệ có thể có:

~~~text
FULL_SERVICE
READ_ONLY
SEARCH_DEGRADED
CHECKOUT_UNAVAILABLE
~~~

SLO theo journey vẫn phải ghi nhận những thao tác không còn thực hiện được, chứ không bỏ chúng khỏi mẫu số.

## 26. Kiểm soát quá tải để bảo vệ tính khả dụng

### 26.1. Load shedding

Nếu traffic vượt năng lực xử lý, từ chối sớm những request ít quan trọng có thể giúp tránh timeout hàng loạt:

~~~text
Ưu tiên:
  Checkout, authorization, order status.

Giảm tải:
  Recommendation, report nặng, prefetch.
~~~

Load shedding có thể cải thiện SLO của critical journey, nhưng những request bị từ chối vẫn phải được phản ánh đúng trong SLI của chức năng đó.

### 26.2. Bounded queues

Hàng đợi không giới hạn có thể tiêu thụ hết RAM khi database chậm. Queue nên có capacity, deadline và chính sách khi đầy.

### 26.3. Circuit breaker

~~~text
CLOSED: cho request tới dependency.
OPEN: chặn tạm để bảo vệ tài nguyên.
HALF_OPEN: thử phục hồi có kiểm soát.
~~~

Circuit breaker giúp tránh cascade failure, nhưng **không tự tạo kết quả giao dịch đúng** khi dependency đang lỗi.

### 26.4. Retry có giới hạn

Một ví dụ chính sách:

~~~text
maxAttempts = 3
backoff = exponential + jitter
overallDeadline = 2 giây
~~~

Giới hạn này chỉ minh họa. Retry không giới hạn có thể tạo retry storm, tăng tải đúng lúc hệ cần giảm tải.

### 26.5. Bulkhead

Nếu analytics query chiếm toàn bộ connection pool, checkout có thể không kết nối được database. Tách pool/concurrency theo chức năng giúp giới hạn blast radius.

### 26.6. Idempotency bảo vệ retry

Trên đường ghi, client có thể retry sau timeout không rõ trạng thái. Các thao tác như charge card, increment counter hoặc gửi email không được thực hiện lặp mà không có dedup/operationId tương ứng.

## 27. SLI theo Region, tenant và loại request

### 27.1. Global average có thể che outage cục bộ

Giả sử:

~~~text
Region A: 99,99% requests good.
Region B: 92% requests good.
~~~

Nếu B chỉ có 1% lưu lượng, tỷ lệ toàn cầu vẫn có thể rất cao dù người dùng B chịu outage nghiêm trọng.

### 27.2. Breakdown cần thiết

Nên phân tích theo:

- Region và Availability Zone.
- Endpoint và method.
- Loại đường đọc/ghi.
- Tenant/tier.
- Client platform.
- Dependency hoặc operation type.
- Đường synchronous so với asynchronous.

Không dùng userId, email hay secret làm nhãn metric cardinality cao.

### 27.3. Weighted availability

Một dashboard có thể tổng hợp:

\[
\text{Weighted Score}=\sum_i w_i\times\text{SLI}_i
\]

với \(\sum_i w_i=1\).

Nhưng số trung bình có trọng số vẫn có thể che sự sụp đổ của một critical journey. Luôn hiển thị các SLI trọng yếu riêng.

### 27.4. Tác động tính theo người dùng

Một người bị retry 100 lần tạo 100 failed requests, trong khi một outage login khiến khách bỏ cuộc không còn gửi request. Có thể bổ sung metric về:

- Số session không hoàn tất.
- Số khách/tổ chức bị ảnh hưởng.
- Số giao dịch pending.
- Số lần khách phải thử lại.

Các metric này không thay thế request SLI nhưng giúp giải thích hậu quả.

## 28. Metric, log và distributed tracing

### 28.1. Các metric mẫu

~~~text
service_requests_total{endpoint,result,region}
service_request_duration_seconds_bucket{endpoint,region,le}
db_operations_total{operation,consistency_level,outcome}
db_operation_duration_seconds_bucket{operation,le}
replication_lag_seconds{region,replica}
replication_backlog_items{region}
leader_election_duration_seconds
checkout_unknown_outcomes_total
~~~

Đây là **tên metric minh họa**, không phải tên tiêu chuẩn do một thư viện bắt buộc phải xuất.

### 28.2. Request-based SLI bằng PromQL

Giả sử ứng dụng đã phân loại eligible requests thành result=good hoặc result=bad theo đúng domain contract:

~~~promql
sum(rate(service_requests_total{
  endpoint="checkout",result="good"
}[30m]))
/
sum(rate(service_requests_total{
  endpoint="checkout",result=~"good|bad"
}[30m]))
~~~

Biểu thức trả tỷ lệ từ 0 tới 1 cho cửa sổ 30 phút. Nhân 100 nếu cần phần trăm.

Nếu mẫu số bằng 0, không nên gán ngầm kết quả 100% mà không có chính sách no-data rõ ràng.

### 28.3. Bad-event fraction

~~~promql
sum(rate(service_requests_total{
  endpoint="checkout",result="bad"
}[1h]))
/
sum(rate(service_requests_total{
  endpoint="checkout",result=~"good|bad"
}[1h]))
~~~

Nếu SLO 99,9%, chia bad fraction cho 0,001 để tính burn rate.

Các công thức chỉ đúng khi hệ telemetry thu được timeout ở edge, có mẫu số phù hợp và result label phân loại chính xác.

### 28.4. Distributed tracing

Một trace checkout:

~~~text
Edge tổng: 2.100 ms.
  Auth: 40 ms.
  Inventory: 1.700 ms.
    Quorum wait: 1.550 ms.
  Payment: 200 ms.
  Other: 160 ms.
~~~

Trace giúp thấy nơi chậm. Nhưng trace không phải lúc nào cũng có mọi request nếu sampling được bật, và phải tránh lưu token/thẻ thanh toán/PII trong span attributes.

### 28.5. Internal metric khác user SLI

Replica lag=0 không chứng minh checkout hoạt động nếu một feature flag sai. Ngược lại, lag 10 giây có thể chấp nhận được cho analytics nhưng nguy hiểm cho thu hồi quyền.

SLI trả lời “người dùng bị ảnh hưởng không?”, metric nội bộ hỗ trợ trả lời “vì sao?”.

## 29. Cảnh báo theo triệu chứng và theo nguyên nhân

### 29.1. Cảnh báo ưu tiên tác động

Ví dụ:

~~~text
Checkout good-event rate dưới mục tiêu.
Burn rate cao ở cả cửa sổ ngắn và dài.
Số timeout ở edge tăng mạnh.
~~~

Đây là triệu chứng trực tiếp của sự cố ảnh hưởng người dùng.

### 29.2. Cảnh báo hỗ trợ chẩn đoán

~~~text
Không đạt quorum.
Replica lag tăng.
Leader election kéo dài.
Connection pool cạn.
Disk gần đầy.
Compaction backlog tăng.
Outbox consumer lag cao.
~~~

Chúng có thể báo trước nguy cơ outage, nhưng cần runbook và ngưỡng phù hợp để tránh alert fatigue.

### 29.3. Multi-window error-budget alert

Một cách là kết hợp điều kiện burn rate trong vài phút với một cửa sổ dài hơn, chỉ page khi có dấu hiệu ảnh hưởng nghiêm trọng đủ liên tục.

Không nên dùng một ngưỡng duy nhất từ một phút ít traffic để đánh thức on-call quá thường xuyên.

### 29.4. SLO breach không chứng minh CAP là nguyên nhân

Khi checkout SLO tụt, có thể do:

- Lỗi code.
- Quorum mất.
- DNS.
- Capacity.
- Network partition.
- Payment provider.
- Queue backlog.

Phải điều tra nguyên nhân bằng trace/metric, không tự quy mọi outage cho định lý CAP.

## 30. Case study: dịch vụ bán vé hai Region

### 30.1. Kiến trúc

~~~mermaid
flowchart TD
    U["Users"] --> A["API Gateway"]
    A --> C["Catalog/Search local replicas"]
    A --> O["Seat ownership service"]
    O --> D["Authoritative reservation store"]
    D --> E["Outbox"]
    E --> S["Search, cache, analytics"]
    A --> P["Payment workflow"]
    P --> D
~~~

Catalog chấp nhận eventual, nhưng reservation phải có một điểm quyết định đủ mạnh để không có hai confirmed bookings trên cùng ghế.

### 30.2. Mục tiêu minh họa

~~~text
Catalog SLO:
  99,95% query good trong 500 ms / rolling 30 ngày.

Reservation SLO:
  99,9% eligible requests có kết quả đúng
  trong 2 giây / rolling 30 ngày.

Safety invariant:
  Không có hai confirmed bookings cùng event+seat.

Freshness SLO:
  99% catalog updates visible trong 10 giây.
~~~

Đây là các ví dụ do bài học giả định, không phải khuyến nghị mặc định cho mọi hệ.

### 30.3. Partition cô lập một Region khỏi nguồn quyết định

Ứng dụng có thể:

1. Tiếp tục trả catalog từ cache còn trong giới hạn tuổi dữ liệu.
2. Hiển thị thông tin ghế là tham khảo nếu không có trạng thái hiện tại.
3. Chặn hoặc route giao dịch giữ ghế tới nguồn có quyền quyết định.
4. Không cấp reservation dựa trên local stale state.
5. Với công việc phù hợp, chấp nhận vào queue bền vững nhưng trả PENDING thay vì CONFIRMED.

### 30.4. Kết quả CAP và vận hành

Trong thời gian sự cố:

- Catalog có thể vẫn khả dụng theo cách nới consistency.
- Reservation có thể không khả dụng ở phía không có quorum.
- Checkout SLI có thể giảm nếu khách ở phía đó không thể hoàn tất.
- Dữ liệu không được phép xuất hiện double booking chỉ để tăng request success.

### 30.5. Khi mạng hồi phục

Cần:

- Xác minh leader/quorum và không có split-brain.
- Đối soát những request có kết quả không rõ.
- Kiểm tra outbox và projection lag.
- Hòa giải stale reads trong cache/search.
- Kiểm tra safety invariant, không chỉ số booking còn tồn tại.
- Tính ảnh hưởng SLI, error budget, RTO/RPO.

## 31. Runbook khi tính khả dụng giảm

### 31.1. Xác minh tác động

Xem:

~~~text
Endpoint nào lỗi?
Region nào lỗi?
Bao nhiêu eligible requests bị ảnh hưởng?
Lỗi timeout, stale hay wrong result?
Có invariant quan trọng bị phá không?
~~~

### 31.2. Khoanh vùng

Phân biệt:

- Application bug/deploy.
- Mất quorum/leader election.
- Network partition.
- Database overload.
- Dependency bên ngoài.
- Hot partition/tenant.

### 31.3. Bảo vệ dữ liệu trước khi tối ưu uptime

Đừng hạ consistency trên checkout hoặc quyền truy cập một cách tùy tiện chỉ vì muốn giảm HTTP 503. Phải xác định hậu quả khi hai vùng đồng thời ghi hoặc khi một cache stale phục vụ quyết định.

### 31.4. Giảm tác động

Tùy tình huống:

- Route tới vùng có thể phục vụ.
- Chuyển read-only/degraded mode.
- Shed tải không quan trọng.
- Chặn retry storm.
- Rollback cấu hình lỗi.
- Khôi phục replica/capacity theo runbook.

### 31.5. Đối soát sau phục hồi

- Kiểm tra những mutation đã ACK trước failover.
- Xử lý payment/booking unknown outcomes.
- Repair và khôi phục replica cần thiết.
- Xác nhận cache/search không hiển thị dữ liệu sai.
- Đo end-to-end SLI trở lại mục tiêu.

### 31.6. Postmortem

Ghi timeline, phạm vi ảnh hưởng, error-budget impact, nguyên nhân, vì sao biện pháp bảo vệ không đủ, và các hành động có owner/deadline.

CAP là nền tảng để hiểu sự cố phân tán, không phải lý do để ngừng cải thiện quy trình vận hành.

## 32. Fault injection: kiểm thử khi phân vùng

### 32.1. Cắt một replica khỏi cụm

Trong môi trường thử nghiệm:

~~~text
Replicas A, B, C.
RF=3.

C bị cô lập khỏi A/B.
~~~

Gửi GET/PUT/DELETE tại nhiều vị trí, thu:

- Tỷ lệ good/bad responses.
- Độ trễ p95/p99.
- Version đọc được.
- Consistency level.
- Replication/repair lag.
- Kết quả sau khi C trở lại.

### 32.2. Majority partition

Với giao thức majority trên năm node:

~~~text
Phía A: 3 node.
Phía B: 2 node.
~~~

Kiểm tra thao tác nào được commit ở mỗi phía, các client ở minority được trả gì, và có giữ được quyền quyết định duy nhất không.

### 32.3. Concurrent multi-Region writes

~~~text
Region A: reserve S1 cho O1.
Region B: reserve S1 cho O2.
~~~

Đánh giá:

1. Có hai success local không?
2. Nếu có, nghiệp vụ có chấp nhận hậu quả không?
3. Sau replication, dữ liệu hội tụ thế nào?
4. Có cách tránh double booking hoặc bù trừ đúng không?

### 32.4. Brownout thay vì outage hoàn toàn

Thử tăng network delay và giảm I/O capacity có kiểm soát để đo:

- Tail latency.
- Retry count.
- Connection pool exhaustion.
- Good-event rate theo deadline.
- Backpressure.

Nhiều outage production xuất hiện như **quá chậm để dùng**, không phải mất kết nối 100%.

### 32.5. Failover có write đang bay

Giả lập response của một mutation bị mất ngay trước failover. Xem request retry có nhân đôi side effect không, và có thể truy vấn trạng thái bằng requestId hay không.

### 32.6. An toàn thử nghiệm

Không tạo network partition phá dữ liệu trên production nếu chưa có phê duyệt, kế hoạch phục hồi và giới hạn tác động. Fault injection phải có điều kiện dừng, owner và telemetry phù hợp.

## 33. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| CAP nghĩa chọn bất kỳ hai thuộc tính trong mọi thời điểm | Tradeoff C/A đặc biệt phát sinh khi có partition |
| Chọn AP thì uptime tự cao | CAP availability khác operational SLI |
| Chọn CP thì hệ luôn unavailable | Trong mạng bình thường vẫn có thể đạt SLO rất cao |
| Có response 503 tức là thỏa CAP availability | Không đáp ứng thao tác theo hợp đồng chỉ bằng lỗi hạ tầng |
| Gửi HTTP 200 thì mọi thứ tốt | Payload, latency, consistency có thể sai |
| Mọi 4xx đều là bad event | Business rejection hợp lệ có thể đúng |
| Eventual đồng nghĩa mọi replica giống nhau trong 1 giây | Mô hình không có bound mặc định |
| Mọi NoSQL chỉ thuộc CP hoặc AP | Cần xét operation, topology và consistency level |
| W+R>N tự bảo đảm linearizable | Cần xét giao thức, concurrent writes và tập replica |
| Thêm replica luôn tăng availability | Fault domain, coordination, failover cũng quan trọng |
| Multi-Region active-active không thể conflict | Các ghi đồng thời có thể tranh cùng key |
| Cache stale luôn được phục vụ | Không phù hợp nhiều thao tác security và giao dịch |
| 99,9% uptime luôn bằng chính xác 43,2 phút lỗi | Chỉ là quy đổi time-based cho cửa sổ 30 ngày |
| 200 từ /health nghĩa checkout sử dụng được | Health check không thay synthetic journey |
| Error budget cho phép double charge | Correctness invariant không thể thay bằng tỷ lệ success |
| p99 tổng bằng trung bình p99 của từng node | Phải tổng hợp distribution đúng |
| Trả 202 là xử lý xong request | 202 có thể chỉ accepted/queued |
| Timeout luôn nghĩa write thất bại | Có thể commit nhưng response mất |
| Failover nhanh nghĩa RPO=0 | RTO và RPO khác nhau |
| Retry vô hạn sẽ tăng availability | Có thể tạo retry storm |
| Consumer lag=0 nghĩa search mới | Refresh/visibility còn có thể trễ |
| SLI toàn hệ cao nghĩa tất cả Region đều tốt | Khu vực ít traffic có thể outage |
| SLI tốt chứng minh không có vi phạm safety | Một lỗi giao dịch nghiêm trọng vẫn có thể xảy ra |
| Mẫu số không có request thì availability 100% | Không có đủ bằng chứng, cần chính sách no-data |

## 34. Bài tập thực hành

### Bài 1. Hai nghĩa availability

Một hệ có:

~~~text
/health: 200 trong 100% phút.
/search: 99,99% requests good.
/checkout: 12% requests timeout.
~~~

Hãy:

1. Giải thích vì sao không thể tuyên bố checkout available 100%.
2. Phân biệt CAP availability với operational availability.
3. Thiết kế good-event SLI cho checkout.
4. Nêu một synthetic journey phù hợp hơn /health.

### Bài 2. Partition hai replica

A và B cùng lưu K=0. Mạng bị chia. X gửi PUT K=1 tới A và nhận success. Sau đó Y bắt đầu GET K tại B.

1. Nếu GET hứa linearizability, B có thể trả 0 không?
2. Nếu B chờ/từ chối, thuộc tính CAP nào bị ảnh hưởng?
3. Nếu B trả 0, thuộc tính nào bị nới?
4. Nếu cả A/B tiếp tục chấp nhận PUT khác nhau, cần làm gì khi mạng phục hồi?

### Bài 3. Quorum

Hệ có N=5, write majority=3. Partition tách thành nhóm 3 node và 2 node.

1. Nhóm nào có thể đạt majority?
2. Vì sao 2 node còn sống vẫn có thể phải từ chối ghi?
3. W=3 và R=3 có giao nhau trong mô hình chung N=5 không?
4. Vì sao giao nhau không tự chứng minh serializable transaction trong mọi triển khai?

### Bài 4. Tính downtime

Với cửa sổ 30 ngày:

1. Tính thời gian lỗi tương đương của 99,9%.
2. Tính của 99,99%.
3. So sánh độ khắt khe.
4. Giải thích tại sao request-based SLO không suy ra đúng số phút lỗi khi traffic tăng mạnh lúc flash sale.

**Gợi ý:** 43,2 phút so với 4,32 phút.

### Bài 5. Request SLI

Trong rolling 30 ngày:

~~~text
Eligible requests: 4.000.000
Good:              3.996.500
Bad:                   3.500
SLO: 99,9%
~~~

1. Tính availability SLI.
2. Tính tổng bad requests được phép theo SLO.
3. Tính error budget còn lại.
4. Nếu toàn bộ 3.500 lỗi xảy ra trong 10 phút flash sale, tại sao tác động có thể rất nghiêm trọng dù SLO tháng chưa bị vi phạm?

### Bài 6. Burn rate

SLO 99,95% cho phép 0,05% bad. Trong một giờ có 1% bad requests.

1. Tính burn rate.
2. Vì sao cần số request lỗi tuyệt đối?
3. Vì sao cần cửa sổ ngắn và dài?
4. Nếu endpoint có cực ít request, nên xử lý alert như thế nào?

**Gợi ý:** \(1\%/0,05\%=20\).

### Bài 7. HTTP status và nghiệp vụ

POST /reserve-seat trả:

~~~text
200, reservation được tạo đúng.
409, ghế đã có owner khác từ trước.
422, thiếu seatId.
503, không xác minh được quorum.
200, status CONFIRMED nhưng không có record bền vững.
~~~

Phân loại good/bad theo một SLI dựa trên contract, giải thích vì sao mã HTTP một mình không đủ.

### Bài 8. Brownout

Một dịch vụ có:

~~~text
HTTP success: 99,99%.
p50: 70 ms.
p95: 500 ms.
p99: 9 giây.
Client timeout: 2 giây.
~~~

1. Vì sao success rate không phản ánh đủ?
2. Đề xuất good-event deadline.
3. Cần đo thêm metric nào để xác định bottleneck?
4. Tại sao tăng client timeout lên 20 giây chưa chắc là giải pháp tốt?

### Bài 9. RTO/RPO

Region chính hỏng lúc 09:00. Hệ phục vụ lại lúc 09:07 trên Region dự phòng, nhưng thiếu một số mutation đã ACK từ 08:59 đến 09:00.

1. RTO quan sát xấp xỉ bao nhiêu?
2. Có thể kết luận RPO bằng 0 không?
3. Tại sao điều này rủi ro với thanh toán?
4. Nêu một cách cải thiện durability contract.

### Bài 10. Composite availability

Ba dependency bắt buộc, độc lập, mỗi dependency available 99,9%.

1. Tính xác suất cả ba cùng available.
2. Tại sao lỗi tương quan làm giả định độc lập không thực tế?
3. Hãy bỏ một dependency không quan trọng khỏi synchronous critical path.
4. Fallback về cache có phù hợp cho payment không? Vì sao?

### Bài 11. Phân tích CAP policy

Một ứng dụng có:

- Tìm kiếm sản phẩm.
- Đặt ghế cuối.
- Lưu draft offline.
- Thu hồi quyền.
- Thanh toán.
- Dashboard doanh thu.

Với mỗi tính năng:

1. Có thể cho phép stale data không?
2. Khi partition, nên tiếp tục, chờ hay từ chối?
3. Invariant nào không được phá?
4. SLI/SLO nên đo gì?

### Bài 12. Đo theo Region

Global API SLI là 99,98%, nhưng Region B chỉ có 92% good requests.

1. Làm sao breakdown theo Region/endpoint/tenant?
2. Vì sao Region B có thể bị che trong global average?
3. Synthetic check từ những vị trí nào là hợp lý?
4. Nên alert theo global SLI hay per-Region critical journey?

### Bài 13. Multi-Region concurrent writes

~~~text
VN: reserve seat S1 cho O1.
SG: reserve seat S1 cho O2.
~~~

Cả hai Region có eventual replication và đã báo success.

1. Vì sao hai success có thể cùng xảy ra?
2. Last-write-wins có tự sửa được hậu quả với hai khách không?
3. Đề xuất một home Region hoặc ownership protocol.
4. Khi home Region unavailable, khả năng giữ consistency ảnh hưởng availability thế nào?

### Bài 14. Fault injection

Cụm RF=3, cô lập replica C trong lúc PUT và DELETE tới A/B.

Thiết kế bài test đo:

- Kết quả read/write theo consistency level.
- Stale reads.
- Tail latency.
- Repair backlog.
- Tombstone và nguy cơ dữ liệu hồi sinh.
- Khả năng phục hồi khi C quay lại.
- Good-event rate của những endpoint liên quan.

### Bài 15. Runbook ứng phó

Trong một deploy, checkout SLI tụt còn 95%, DB xuất hiện quorum timeout nhưng catalog vẫn đọc cache thành công.

Lập runbook gồm:

1. Xác minh tác động người dùng.
2. Khoanh vùng deploy/network/DB.
3. Bảo vệ invariant checkout.
4. Giảm retry storm và tải nền.
5. Route/rollback/failover có kiểm soát.
6. Đối soát giao dịch unknown outcome.
7. Tính error-budget impact và cập nhật postmortem.

## 35. Tổng kết

**Tính sẵn sàng theo CAP** và **khả dụng vận hành** cùng dùng chữ *availability*, nhưng không trả lời cùng một câu hỏi.

Trong **CAP**, khi mạng bị phân vùng, hệ không thể đồng thời bảo đảm **linearizability** và **khả năng phản hồi hợp lệ ở mọi phía không lỗi** cho các thao tác liên quan cùng dữ liệu. Hệ cần chọn khi nào tiếp tục với nhất quán được nới lỏng, và khi nào chờ/từ chối để bảo vệ tính đúng đắn.

Trong **vận hành**, khả dụng phải được đo theo **người dùng có hoàn tất công việc đúng hạn hay không**, với tiêu chí good/bad, mẫu số, cửa sổ và nguồn đo xác định.

Các nguyên tắc quan trọng:

1. **Đừng hiểu CAP là luôn được chọn hai trong ba thuộc tính.** Tradeoff nổi bật lúc network partition.
2. **Không gán nhãn CP/AP tuyệt đối cho một sản phẩm NoSQL.** Xem thao tác, consistency level và topology.
3. **Không dùng dữ liệu stale để chốt invariant nhạy cảm** như giữ ghế, tiền, uniqueness hoặc quyền nếu thiếu biện pháp bảo vệ.
4. **SLI phải bám trải nghiệm thực**, bao gồm correctness và deadline, không chỉ mã HTTP.
5. **SLO, SLA, error budget và burn rate có vai trò khác nhau**; phần trăm downtime không luôn tương đương phần trăm failed requests.
6. **RTO khác RPO:** Khôi phục service nhanh không bảo đảm không mất mutation.
7. **Thiết kế retry, circuit breaker, load shedding, degradation và failover có kiểm soát**, tránh đổi số liệu đẹp lấy kết quả sai.
8. **Đo theo hành trình, Region và tenant**, bởi trung bình toàn hệ có thể che outage nghiêm trọng.
9. **Kiểm thử sự cố trước khi nó xảy ra**, quan sát cả availability lẫn tính đúng đắn và khả năng hội tụ sau repair.

Câu hỏi khi thiết kế không chỉ là **“Hệ có available không?”**, mà là:

> **“Trong loại lỗi này, thao tác nào còn có thể được xử lý đúng hợp đồng, tính nhất quán nào bắt buộc phải giữ, bao nhiêu yêu cầu người dùng hoàn tất trong deadline, và chúng ta đo — phục hồi — đối soát kết quả ấy như thế nào?”**

