# Kiểm tra tài liệu và kết quả thực nghiệm thay vì suy luận từ nhãn strong/eventual trong NoSQL

## 1. “Database này strong” là một câu trả lời chưa đủ

Giả sử một nhóm phát triển đang chọn hệ lưu trữ cho ứng dụng đặt hàng:

- Một bài giới thiệu sản phẩm viết: **“strong consistency”**.
- Một bài blog khác nhận xét: **“NoSQL thường eventual consistency”**.
- Một người thử ghi một document rồi đọc lại và thấy đúng ngay, nên kết luận hệ thống “linearizable”.
- Một người khác đọc từ search index thấy dữ liệu cũ sau khi ghi, nên kết luận database nguồn “không nhất quán”.

Cả bốn cách suy luận trên đều có thể sai vì chúng **không xác định chính xác thao tác, đường đọc/ghi, phạm vi dữ liệu, cấu hình và loại sự cố**.

Đối với một hệ NoSQL, những câu hỏi quan trọng hơn nhãn tiếp thị là:

1. **Strong theo nghĩa nào?** Linearizability, sequential consistency, serializability, causal consistency hay read-your-writes?
2. **Áp dụng ở đâu?** Một item, một document, một partition, một transaction nhiều item, hay toàn hệ nhiều region?
3. **Đường API nào?** Đọc primary, secondary, global secondary index, cache, search, change stream, hay read model riêng?
4. **Cấu hình nào?** Read concern, write concern, consistency level, session, transaction, routing và topology?
5. **ACK có nghĩa gì?** Đã commit, đã được đa số bản sao xác nhận, đã ghi bền vào log, hay chỉ đã nhận yêu cầu?
6. **Sự cố gì?** Đọc thông thường, ghi đồng thời, mất kết nối, failover, partition mạng hoặc crash?
7. **Nguồn bằng chứng ở đâu?** Tài liệu kỹ thuật chính thức, giới hạn đã công bố, kết quả đo có thể tái lập và history kiểm chứng được?

Bài học này hướng dẫn **đọc tài liệu một cách có phương pháp** và **thiết kế thực nghiệm kiểm tra hành vi quan sát** trước khi đưa ra kết luận về consistency của hệ NoSQL.

Mục tiêu không phải tìm một bảng xếp hạng database “mạnh nhất”, mà là viết được một **hợp đồng nhất quán có phạm vi**, hiểu giới hạn của bằng chứng và chọn đường đọc/ghi phù hợp với bất biến nghiệp vụ.

## 2. Một tuyên bố consistency đúng phải có đầy đủ ngữ cảnh

Thay vì:

> Database A có strong consistency.

Hãy viết theo cấu trúc:

> Khi dùng **API X** với **cấu hình Y** trên **topology Z**, đối với **đơn vị dữ liệu U**, hệ cung cấp **bảo đảm C** dưới những **điều kiện F**; các đường **R1/R2** nằm ngoài bảo đảm đó.

Ví dụ một tuyên bố mang tính mẫu, chưa gắn với nhà cung cấp cụ thể:

> Với yêu cầu đọc trực tiếp theo khóa từ leader, sau một write đã commit theo quorum trong cùng vùng, hệ được thiết kế để trả phiên bản mới nhất cho từng item khi không có write cạnh tranh. Truy vấn qua search projection cập nhật bất đồng bộ không thuộc bảo đảm này.

Câu trên cung cấp một phạm vi có thể kiểm chứng: **đường đọc theo key**, **ngữ nghĩa commit**, **một item**, **không có write cạnh tranh** và **ngoại lệ search**.

### Bảy chiều cần ghi trong một “consistency claim”

| Chiều | Ví dụ cần điền | Vì sao quan trọng? |
|---|---|---|
| **Operation** | `GetItem`, `Query`, `findOne`, `UPDATE`, transaction | Các API có semantics khác nhau |
| **Đối tượng** | Một key/document, tập item, partition, multi-key transaction | Bảo đảm trên một đối tượng không tự lan sang nhiều đối tượng |
| **Đường đọc** | Primary, replica, GSI, cache, search, endpoint cross-region | Các đường này có thể ở các phiên bản khác nhau |
| **Đường ghi/ACK** | Leader ACK, majority, journal, conditional write | Định nghĩa mốc write được coi là hoàn tất |
| **Phiên/định tuyến** | Client session, bookmark, session token, replica affinity | Quyết định quan hệ read-after-write được giữ thế nào |
| **Topology và lỗi** | Một vùng, multi-AZ, multi-region, failover, timeout | Có thể thay đổi hành vi khi leader/replica đổi |
| **Phiên bản/cấu hình** | Engine/SDK version, flags, isolation, read concern | Tài liệu và mặc định có thể thay đổi |

Nếu thiếu một trong các chiều trọng yếu, kết luận cần ghi rõ **“chưa xác minh”**, không tự chuyển thành nhận định về toàn bộ sản phẩm.

## 3. Đọc chính xác các mô hình nhất quán trước khi thử nghiệm

Trước khi đối chiếu documentation, cần phân biệt tên mô hình.

### 3.1. Linearizability

Với các thao tác trên một đối tượng hoặc một tập đối tượng được định nghĩa rõ, lịch sử có thể được sắp như **thao tác xảy ra nguyên tử tại một điểm giữa lúc gọi và trả kết quả**, đồng thời tôn trọng thứ tự **thời gian thực** giữa những thao tác không chồng lấn.

Ví dụ:

```text
A: W(x=1) -------- ACK
                         B: R(x) -> ?
```

Nếu B bắt đầu sau khi A đã hoàn tất và không có ghi cạnh tranh đưa x về giá trị cũ, một đường đọc linearizable phải trả `1`.

### 3.2. Sequential consistency

Yêu cầu tồn tại **một thứ tự tuần tự chung** giải thích mọi thao tác và bảo toàn **program order của mỗi client/process**. Nó **không bắt buộc** bảo toàn thứ tự thời gian thực giữa thao tác của hai client khác nhau.

Vì thế cùng ví dụ A ACK rồi B đọc `0` có thể vẫn phù hợp sequential consistency, nếu B và A độc lập và ta có thể đặt read B trước write A trong thứ tự logic.

### 3.3. Causal consistency

Bảo toàn thứ tự của những thay đổi có **quan hệ nhân quả**, như program order, write phụ thuộc một giá trị đã đọc và quan hệ bắc cầu. Những write độc lập có thể được nhìn theo các thứ tự khác nhau, tùy mô hình.

### 3.4. Eventual consistency

Thường mô tả việc replica **cuối cùng hội tụ** khi không còn cập nhật mới và các giả định về hoạt động/replication được đáp ứng. Nhãn này **không định nghĩa cụ thể** read cũ được phép kéo dài bao lâu, session có monotonic reads hay không, hoặc có thể mất write sau failover không.

### 3.5. Serializability và strict serializability

Đây là tính chất **cấp transaction**, không chỉ từng lệnh đọc/ghi rời. Serializability yêu cầu lịch sử tương đương các transaction chạy tuần tự; strict serializability bổ sung ràng buộc thời gian thực giữa các transaction không chồng lấn.

### 3.6. Session guarantees

Các bảo đảm như **read-your-writes**, **monotonic reads**, **monotonic writes** và **writes-follow-reads** áp dụng theo session hoặc client logic. Có session guarantees **không tự đồng nghĩa** một global sequential order cho tất cả client và key.

### Bảng phân biệt nhanh

| Mô hình | Đơn vị trọng tâm | Điều kiện quan trọng | Không tự đảm bảo |
|---|---|---|---|
| Linearizability | Operation/đối tượng | Thứ tự tuần tự hợp lệ + real-time order | Transaction atomic cho nhiều operation riêng |
| Sequential consistency | Operation/lịch sử | Một global order giữ program order | Real-time order giữa client |
| Causal consistency | Thao tác có quan hệ nhân quả | Causal order | Total order của write độc lập |
| Eventual consistency | Trạng thái replica | Hội tụ khi đủ điều kiện | Độ trễ tối đa hay read-your-writes mặc định |
| Serializability | Transaction | Tương đương một serial schedule | Real-time order |
| Strict serializability | Transaction | Serial schedule + real-time order | Chống mọi thảm họa lưu trữ |
| Read-your-writes | Session | Read sau write của chính session phản ánh write đã hoàn tất | Bảo đảm read của client khác |

**Durability, availability và authorization là các trục riêng.** Không thể suy ra RPO=0, uptime, hoặc quyền đọc đúng chỉ vì một hệ có linearizability.

## 4. Bốn tầng bằng chứng: quảng bá, hợp đồng, cấu hình và quan sát

Khi nghiên cứu một NoSQL engine, phân cấp bằng chứng theo khả năng trả lời câu hỏi cụ thể.

| Tầng | Nguồn | Giá trị | Giới hạn |
|---|---|---|---|
| **Giới thiệu/marketing** | Trang sản phẩm, bài giới thiệu | Biết mục tiêu thiết kế và thuật ngữ nhà cung cấp | Thường lược bỏ điều kiện và ngoại lệ |
| **Tài liệu API/hợp đồng** | Official docs, reference, consistency model, limitations | Biết những gì được cam kết trong phạm vi xác định | Cần khớp version/topology |
| **Cấu hình đang chạy** | Cluster topology, read/write settings, SDK options, IAM | Biết ứng dụng có thực sự dùng chế độ đã đọc không | Chưa chứng minh runtime đúng hoặc không có lỗi |
| **Thực nghiệm/observability** | Histories, traces, logs, fault tests, metrics | Đánh giá behavior thực tế, phát hiện mismatch | Không chứng minh tính đúng cho mọi lịch sử có thể xảy ra |

Một phép thử thành công **không nâng tài liệu mơ hồ thành theorem**. Một thí nghiệm phát hiện phản ví dụ rõ ràng có thể bác bỏ một tuyên bố cụ thể, nhưng cần phân loại **lỗi thử nghiệm, sai giả định, read path ngoài phạm vi** hay lỗi thực sự của hệ.

### Không biến quảng bá thành theorem

Ví dụ câu quảng bá “mọi thao tác được xử lý với strong consistency” chưa trả lời:

- Có bao gồm **GSI/query projection** hay chỉ base table lookup?
- Có bao gồm **multi-region reads**?
- Có áp dụng cho **read sau timeout ghi chưa rõ kết quả**?
- Có bảo đảm **một snapshot nhiều key**?
- Có yêu cầu **đọc từ leader**?
- Có áp dụng khi dùng **SDK retry/failover**?

Tài liệu kỹ thuật tốt phải giúp xác định các điều kiện đó. Nếu không, cần đánh dấu điểm chưa rõ và kiểm thử có mục tiêu thay vì tự suy luận.

## 5. Quy trình đọc tài liệu chính thức

Khi tìm hiểu một datastore, ưu tiên đọc **tài liệu của đúng phiên bản/kiểu triển khai** theo thứ tự:

1. **Consistency model / guarantees:** định nghĩa thuật ngữ và phạm vi.
2. **Read API reference:** kết quả có thể cũ không, default option, những đường không hỗ trợ strong read.
3. **Write API / acknowledgment:** khi nào lệnh được xác nhận, write concern và điều kiện ghi.
4. **Transactions / isolation:** nguyên tử một hay nhiều key, mức isolation, giới hạn.
5. **Replication / failover:** leader election, replica lag, rollback, tính nhất quán liên vùng.
6. **Indexes / read model:** secondary indexes, materialized views, search refresh, CDC.
7. **Timeout / retry semantics:** điều gì xảy ra nếu commit đã thành công nhưng ACK mất?
8. **Release notes / migration notes:** defaults, thuật ngữ hoặc option có thay đổi không?
9. **Operational limitations:** topology bắt buộc, region, quota, quyền, monitoring.

### Bảng trích xuất bằng chứng

Một phiếu đọc tài liệu nên có:

```text
Claim ID: C-ORD-001
Database/engine version: <exact version>
Topology: <single node / replica set / multi-DC / multi-region>
Operation: Get order by primary key
Read path: base table / primary
Write ACK mode: <exact settings>
Read mode: <exact settings>
Object scope: one item
Concurrent writes: <assumptions>
Failure scope: <normal / failover / partition>
Document reference: <official docs page + version + section>
Quote/interpretation: <short grounded summary>
Exceptions: <indexes, replicas, timeouts>
Unknowns: <what is not specified>
Proposed test: <history and expected outcome>
```

Đây là một **bản khai hợp đồng có thể kiểm chứng**, không chỉ một ghi chú “database mạnh”.

### “Default” là dữ liệu cần xác nhận

Nếu tài liệu nói “có hỗ trợ strong read”, không có nghĩa **ứng dụng đang bật strong read**. SDK có thể dùng default eventual, request có thể chọn GSI, endpoint có thể route sang read replica, hoặc một service trung gian trả cache. Cần quan sát request thực tế, không chỉ đọc code khởi tạo database.

### Khi tài liệu nhiều thế hệ mâu thuẫn

Giả sử bài viết cũ mô tả một phương thức read, còn API reference mới nói có giới hạn. Nên:

- Chốt phiên bản triển khai thực tế.
- Ưu tiên API reference/release notes chính thức cùng phiên bản.
- Ghi lại sự khác biệt giữa hai nguồn và điều kiện áp dụng.
- Thử một scenario nhỏ để xác nhận option đang hoạt động.
- Không trộn những cam kết thuộc **managed service** với bản **self-hosted** khác topology.

## 6. Xác định hành vi theo đường dữ liệu end-to-end

Một người dùng nhấn “xác nhận đơn” và ngay sau đó tìm kiếm:

```text
Browser
   |
   v
Order API ----> MongoDB source
   |
   +---------> Redis cache
   |
   +---------> Search API ----> Elasticsearch index
                                  ^
                                  |
                              CDC/Outbox
                                  ^
                                  |
                             MongoDB source
```

Nếu MongoDB đã commit nhưng Elasticsearch chưa refresh, màn hình tìm kiếm có thể chưa thấy đơn. Phát hiện này **không tự nói gì về tính tuyến tính hóa của MongoDB point lookup**.

Tương tự:

- API đọc Redis cache có thể trả giá trị cũ dù source read mạnh.
- Một endpoint đi qua API gateway với cache HTTP có thể giữ dữ liệu cũ.
- Một ứng dụng dùng primary cho ghi, secondary cho đọc có thể không thấy write mới ngay.
- Màn hình kết hợp base table, GSI và search có thể quan sát các version khác nhau.

Vì vậy phải vẽ **đúng đường đọc/ghi sản phẩm đang đi qua**, đặt từng kết quả đo vào đúng tầng, rồi mới đánh giá consistency.

### Kiểm tra dữ liệu nguồn khác kiểm tra read model

Giả sử:

```text
Source order version = 8
Search document version = 7
Cache order version = 6
```

Tuyên bố hợp lý là “**hai projection đang trễ so với source**” nếu biết source là authoritative và có version đúng. Không thể từ đó suy ra “source có eventual consistency” hoặc “mọi thao tác trên toàn hệ không serializable”.

## 7. Chọn bất biến nghiệp vụ trước khi chọn bài test

Không phải mọi chức năng cần cùng mức nhất quán.

| Tình huống | Bất biến thực sự | Điều cần xác minh |
|---|---|---|
| Tra cứu mô tả sản phẩm | Có thể thấy dữ liệu cũ một khoảng cho phép | Convergence/lag, TTL, query visibility |
| Xem đơn sau khi tự tạo | User phải thấy đơn vừa tạo | Read-your-writes/session behavior |
| Cập nhật trạng thái theo version | Không ghi đè thay đổi mới | Atomic conditional update/CAS |
| Đặt chỗ cuối cùng | Không cấp cùng một chỗ cho hai người | Linearizable decision hoặc transaction phù hợp |
| Chuyển tiền | Không đọc/ghi trạng thái nửa giao dịch | Transaction atomicity + isolation phù hợp |
| Danh sách đơn qua GSI | Có thể chậm nhưng không mất vĩnh viễn | Eventual index convergence, index lag, replay |
| Thu hồi quyền xem tài liệu | Không trả nội dung bị cấm sau mốc quyền có hiệu lực | Authorization tại nguồn/đường đọc mạnh phù hợp |
| Thống kê doanh thu | Có thể hội tụ, không cộng event trùng | Idempotency, reconciliation, watermark |

Một SLA có thể yêu cầu **linearizable reservation** nhưng chỉ cần **eventually consistent search**. Nếu áp một nhãn “strong/eventual” cho toàn bộ ứng dụng, ta sẽ bỏ sót ranh giới quyết định và có thể trả chi phí điều phối không cần thiết.

## 8. Thực nghiệm phải kiểm tra lịch sử, không chỉ một request

Một bài thử “ghi rồi đọc lại, thấy đúng” chỉ chứng minh **một quan sát**. Nó không đủ để phân biệt phần lớn consistency models.

Để kiểm tra nghiêm túc, thu thập **history** gồm:

```text
operationId
clientId / sessionId
programSequence
operationType: READ | WRITE | COMPARE_AND_SET | TRANSACTION
key / aggregateId
writeValue hoặc expectedVersion
readResult hoặc updateResult
invokeTime
completeTime
responseStatus / timeout
readPath: primary | replica | GSI | cache | search
topology / replica / region
configurationVersion
```

History phải bao gồm **mọi thao tác liên quan** trong thử nghiệm. Nếu có một writer nền không được ghi lại, phép đọc tưởng “không thể giải thích” có thể thực ra được giải thích bằng write bị thiếu.

### Phân biệt sự kiện invoke và complete

Một operation có khoảng:

```text
invoke -------- execution -------- complete/response
```

Nếu thao tác A hoàn tất trước khi B bắt đầu, **linearizability** bắt buộc A trước B. Nếu hai operation chồng lấn, linearizability có thể cho phép một số thứ tự phù hợp với điểm linearization của từng thao tác.

Với **sequential consistency**, phải giữ program order của từng client, nhưng không tự thêm mọi ràng buộc thời gian thực xuyên client.

### Pending operation

Nếu request timeout sau khi server có thể đã commit, history có một operation **chưa biết kết quả**. Bộ kiểm tra phải xử lý theo mô hình phù hợp: có thể xem write pending là đã xảy ra hoặc chưa xảy ra khi đánh giá lịch sử, thay vì tự gán “timeout = rollback”.

Nếu ứng dụng retry bằng ID mới, chính retry có thể làm thay đổi lịch sử. **Tính đúng nghiệp vụ cần idempotency**, không chỉ consistency checker.

## 9. Bài test đầu tiên: read-your-writes

Giả sử key `x=0` và không có writer khác.

```text
Client A:
  W(x=1) -> ACK
  R(x)   -> ?
```

Nếu read thuộc cùng client/session theo hợp đồng, hệ có read-your-writes phải không trả `0` sau khi write hoàn tất. Với lịch sử thao tác đơn giản này, kết quả `0` cũng không thể giải thích bằng sequential consistency nếu program order bắt buộc write trước read.

### Cách chạy tốt hơn một lần lặp

1. Dùng key mới hoặc version riêng cho từng lượt, tránh dữ liệu tồn dư.
2. Ghi một giá trị có ID duy nhất, chẳng hạn `run-42-v1`.
3. Chờ ACK thực sự của write.
4. Đọc qua **đường API cần kiểm tra**, không vô tình chuyển sang một path mạnh hơn.
5. Ghi cả những lần đọc thấy cũ, request timeout và read replica.
6. Lặp lại khi router đổi replica, khi xảy ra failover và khi concurrency cao.

### Kết luận đúng mức

- Nếu luôn thấy giá trị mới: **chưa tìm thấy vi phạm** trong những lượt thử.
- Nếu thấy giá trị cũ và đúng là cùng session, không có writer khác: có **phản ví dụ** đối với read-your-writes trong phạm vi đã thử.
- Nếu client đổi session hoặc read từ API không cam kết session stickiness: cần xem hợp đồng trước khi coi đó là lỗi của hệ.

**Read-your-writes không chứng minh linearizability cho những client khác.**

## 10. Test phân biệt linearizability với sequential consistency

Ban đầu `x=0`:

```text
Thời gian thực:

Client A:  W(x=1) -------- ACK
                                 Client B: R(x) -> 0
```

Giả sử B bắt đầu **sau khi** A đã nhận ACK, không có write cạnh tranh đưa x về 0.

- **Linearizability:** kết quả `0` là phản ví dụ nếu hai operation thuộc cùng đối tượng được cam kết.
- **Sequential consistency:** có thể đặt `R_B(x)=0` trước `W_A(x=1)` trong thứ tự logic; **chưa có phản ví dụ**.
- **Eventual consistency:** một read cũ có thể phù hợp nếu hợp đồng cho phép replication lag; phải kiểm tra thêm điều kiện hội tụ.

### Cần bảo đảm mốc thời gian thật

Đừng dùng wall-clock của hai máy độc lập rồi so trực tiếp nếu đồng hồ có thể lệch. Một controller có thể **nhận xác nhận A hoàn tất rồi mới gửi yêu cầu B đọc**, tạo quan hệ happens-before rõ ràng.

```text
Controller
   |
   +--> send WRITE A
   |       |
   |<-- response A complete
   |
   +--> send READ B
           |
        response B
```

Đây là cách tạo **non-overlapping operations** không phụ thuộc việc đồng hồ hai client có đồng bộ tới mili giây.

### Nếu B đọc qua search index?

Nếu tài liệu chỉ cam kết strong read ở base table, phát hiện stale result trên search/GSI **không bác bỏ** claim cho base table. Phải ghi rõ read path và kiểm tra claim đúng phạm vi.

## 11. Test monotonic reads và chuyển replica

Một client đọc:

```text
R(x) -> version 8
R(x) -> version 6
```

Nếu không có thao tác hợp lệ đưa x quay về version 6 và version là monotonic, client đã quan sát **read regression**.

Đặc biệt dễ xảy ra khi router chuyển client từ replica bắt kịp sang replica còn trễ:

```text
Replica A at version 8
Replica B at version 6

Client -> A : v8
Client -> B : v6
```

Một hệ có **monotonic reads** theo session cần tránh hiện tượng đó, chẳng hạn bằng:

- Session token hoặc watermark yêu cầu replica đã áp tối thiểu version 8.
- Chờ replica bắt kịp.
- Fallback về primary hoặc đường đọc mạnh hơn.
- Routing/session affinity có kiểm soát.

**Không nhầm session monotonicity với global linearizability.** Một client chỉ thấy version tăng dần vẫn chưa chứng minh mọi client chia sẻ một thứ tự toàn phần.

## 12. Test message passing: quan sát phụ thuộc theo đúng thứ tự

Ban đầu:

```text
payload = 0
ready = 0
```

Writer:

```text
W(payload=1)
W(ready=1)
```

Reader:

```text
R(ready)   -> 1
R(payload) -> 0
```

Với chỉ các thao tác trên, kết quả đó **không thể được giải thích bằng sequential consistency**.

Chứng minh:

```text
W(payload=1)         < W(ready=1)       (program order writer)
W(ready=1)           < R(ready)=1       (reader thấy write)
R(ready)=1           < R(payload)=0     (program order reader)
R(payload)=0         < W(payload=1)     (reader thấy giá trị khởi tạo)

=> tạo một vòng trước-sau, không có total order hợp lệ.
```

Đây là test hữu ích khi hai field nằm trên nhiều replica/key khác nhau.

### Điều kiện để test có ý nghĩa

- Chỉ có writer nói trên, không có write ẩn reset `payload` về 0.
- Các thao tác của writer/reader được gửi **theo đúng thứ tự**, không phải chạy song song ngoài ý muốn.
- Reader đọc hai key trong cùng phạm vi bảo đảm được tuyên bố.
- Trạng thái ban đầu được xác minh hoặc khởi tạo từ namespace mới.

Nếu nhà cung cấp chỉ cam kết strong read **trên từng item riêng**, phép thử cross-key này có thể nằm **ngoài hợp đồng**. Nó vẫn có ích để hiểu hệ thống, nhưng không được gán nhãn “bug” vượt quá phạm vi nhà cung cấp cam kết.

## 13. Test store buffering: mỗi client ghi rồi đọc key kia

Ban đầu `x=y=0`:

```text
Client P1            Client P2
---------            ---------
W(x=1)               W(y=1)
R(y)=0               R(x)=0
```

Nếu mỗi client giữ thứ tự write trước read, hai read đều 0 tạo chu trình:

```text
W1(x) -> R1(y)=0 -> W2(y) -> R2(x)=0 -> W1(x)
```

**Không có lịch sử sequentially consistent** dưới những giả định này.

### Vì sao test khó hơn trông tưởng?

Nếu hai write được gửi không có ACK và read bắt đầu khi write còn pending, cần biết program order, completion và semantics mà ứng dụng sử dụng. Với consistency checker, operation pending có thể được sắp vào history theo cách khác tùy mô hình. Để test rõ ràng, mỗi client nên **đợi write hoàn tất** trước read, và ghi đủ thông tin completion.

Việc mỗi client tự nhìn thấy write của mình không chứng minh toàn bộ hệ đạt SC; phép thử này buộc phải xét **một thứ tự chung** trên hai key.

## 14. Test IRIW: hai reader thấy hai thứ tự độc lập khác nhau

**Independent Reads of Independent Writes**:

```text
Ban đầu x = 0, y = 0

P1                    P2
W(x=1)                W(y=1)

P3                    P4
R(x)=1                R(y)=1
R(y)=0                R(x)=0
```

P3 quan sát write x nhưng chưa thấy write y; P4 quan sát y nhưng chưa thấy x. Không thể có một thứ tự toàn phần phù hợp cả hai chuỗi read.

Một bộ kiểm tra SC sẽ tìm được vòng ràng buộc:

\[
W(x) < W(y) < W(x)
\]

Điểm chính: **thứ tự riêng của mỗi key không đủ để có global sequential consistency**. Đây là lý do tài liệu nói “reads and writes to a single item are strongly consistent” chưa đủ để kết luận tính chất nhiều key.

### Khi nào IRIW không bác bỏ claim?

Nếu tài liệu chỉ hứa consistency **theo một partition/item** và không hứa thứ tự xuyên hai key/partition, kết quả IRIW chỉ cho thấy **giới hạn có thể quan sát được** của hệ, không nhất thiết vi phạm hợp đồng.

Việc kiểm chứng phải bám vào **đơn vị bảo đảm** đã ghi ở đầu bài.

## 15. Test transaction: khác với test operation-level consistency

Giả sử có hai tài khoản ban đầu:

```text
A = 100
B = 100
Tổng = 200
```

Một giao dịch chuyển 10:

```text
T1:
  A = 90
  B = 110
```

Reader thấy `A=90, B=100`. Điều này **không tự vi phạm SC của hai thao tác update riêng**, vì một global order có thể đặt read giữa hai write.

Nhưng nếu ứng dụng cam kết cập nhật **atomic transaction** cho cặp tài khoản, việc đọc snapshot nửa transaction có thể vi phạm atomic visibility hoặc isolation theo hợp đồng.

### Test cần phân biệt

| Điều cần kiểm | Test phù hợp |
|---|---|
| Một key không đọc giá trị cũ sau write đã hoàn tất của client khác | Linearizability |
| Thứ tự mọi thao tác có thể được tuần tự hóa giữ program order | Sequential consistency |
| Một transaction không lộ nửa thay đổi | Atomic visibility/transaction |
| Nhiều transaction tương đương một serial schedule | Serializability |
| Serial transactions còn giữ real-time order | Strict serializability |
| Hai writer không ghi đè version ngoài ý định | Conditional update/CAS/lost-update test |
| Hai transaction cùng thấy điều kiện rồi cùng cập nhật gây write skew | Isolation/serializability test |

### Write skew không thể dùng để kết luận từ một nhãn chung

Hai bác sĩ cùng kiểm tra “còn ít nhất một người trực” rồi mỗi người bỏ ca riêng. Nếu cả hai transaction đọc snapshot cũ và cùng commit, có thể xảy ra **write skew** dưới một số mức snapshot isolation. Đây là bài test về **bảo vệ invariant giao dịch**, không chỉ về một read sau write theo khóa.

Không nên cho rằng “snapshot read” đồng nghĩa serializable, hoặc “linearizable single-item operations” đồng nghĩa atomic transaction cho nhiều item.

## 16. Sự cố, partition mạng và failover phải có trong kế hoạch thử

Một hệ có thể hoạt động đúng ở trạng thái bình thường nhưng gặp thay đổi rõ khi:

- Leader mất kết nối.
- Replica chưa theo kịp và được bầu leader mới.
- Một AZ/region tạm mất.
- Client timeout sau khi write đã commit.
- Network partition chia hai nhóm node.
- Clock skew hoặc sự cố timestamp ordering.
- Retry, connection pool và routing chuyển endpoint.

### Ma trận thí nghiệm

| Kịch bản | Điều cần quan sát | Không được suy luận vội |
|---|---|---|
| Normal single writer | Read-your-writes, ACK→read | Thấy đúng không chứng minh toàn hệ linearizable |
| Concurrent writers | CAS/lost update, conflicts | Last-write-wins không phải serializable transaction |
| Read replica lag | Stale read, monotonicity | Read cũ trên replica không bác bỏ cam kết chỉ dành cho primary |
| Leader failover | Write đã ACK còn không, read cũ/rollback | Mất write và stale read cần phân biệt durability/consistency |
| Network partition | Availability/timeout và kết quả được phép | Không coi timeout là sai consistency |
| Multi-region | Lag, conflicts, read-after-write | Một region mạnh không đồng nghĩa mọi region |
| Search/GSI | Index projection lag | Index trễ không chứng minh base item mất |
| Transaction concurrent | Atomicity, write skew, isolation | Một update atomic không đủ chứng minh multi-item serializable |

### ACK ambiguity

```text
Client gửi W(x=1)
Server commit thành công
Response bị mất
Client timeout
```

Thử nghiệm không được tự xem write đã thất bại. Nếu sau đó đọc `x=1`, có thể đây là write đã commit. Nếu client retry, cần **idempotency key** hoặc conditional write để tránh tạo hai hiệu ứng nghiệp vụ.

Trong formal history, request chưa có kết quả thuộc nhóm **pending/unknown**. Bộ kiểm tra cần xử lý nó đúng quy tắc chứ không âm thầm loại bỏ tùy ý để làm cho history “đẹp”.

## 17. Đồng hồ, độ trễ và điều kiện thực nghiệm

### Đừng nhầm thời điểm đo với thời điểm commit

Từ log:

```text
Client A send:  10:00:00.001
Client A recv:  10:00:00.030
Client B send:  10:00:00.040
Client B recv:  10:00:00.050
```

nếu hai client dùng **đồng hồ lệch**, những timestamp đó không đủ để chứng minh non-overlap. Nên điều phối bằng một controller và ghi causal handoff “A response đã về trước khi gửi B request”.

### Kiểm tra độ tải và replication lag

Phát hiện một read cũ trong 1.000 request có thể là dữ liệu hữu ích; nhưng không nên biến tần suất đó thành tỷ lệ chung cho mọi workload. Các yếu tố:

- Number of clients, concurrency, key distribution.
- Read/write ratio, burstiness.
- Cấu hình read/write concern và routing.
- Cache nóng/lạnh.
- Replica lag, compaction, log replay.
- Kích thước request/response, network RTT.
- Vị trí vùng, topology và failover.

Ghi rõ môi trường để người khác có thể tái lập.

### Không “sửa” test bằng việc chèn sleep

Nếu chương trình viết rồi gọi `sleep(1000)` trước read, không phát hiện stale read, điều đó chỉ cho thấy **sau một giây trong môi trường ấy** hệ thường đã hội tụ. Nó không chứng minh read ngay sau ACK có consistency mạnh.

Ngược lại, ép delay nhân tạo có thể giúp tái hiện race, nhưng phải ghi rõ đó là **fault injection**, không phải hành vi mặc định.

## 18. Một harness kiểm thử ở Java: ghi nhận lịch sử thay vì chỉ assert một kết quả

Ví dụ Java sau mô tả cách một test có thể ghi các thao tác bằng một interface datastore, **không ràng buộc SDK cụ thể**.

```java
import java.time.Instant;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicLong;

interface RegisterStore {
    void write(String key, String value) throws Exception;
    String read(String key) throws Exception;
}

record OperationLog(
    long operationId,
    String clientId,
    int clientSequence,
    String operationType,
    String key,
    String argument,
    String result,
    long startedNano,
    long completedNano,
    String outcome
) {}

final class HistoryRecorder {
    private final AtomicLong ids = new AtomicLong();
    private final List<OperationLog> events = new CopyOnWriteArrayList<>();

    void write(
        RegisterStore store, String clientId, int sequence,
        String key, String value
    ) {
        long id = ids.incrementAndGet();
        long started = System.nanoTime();
        String outcome = "OK";
        try {
            store.write(key, value);
        } catch (Exception failure) {
            outcome = "UNKNOWN_OR_ERROR";
        }
        long completed = System.nanoTime();
        events.add(new OperationLog(
            id, clientId, sequence, "WRITE", key, value, null,
            started, completed, outcome
        ));
    }

    String read(
        RegisterStore store, String clientId, int sequence,
        String key
    ) {
        long id = ids.incrementAndGet();
        long started = System.nanoTime();
        String result = null;
        String outcome = "OK";
        try {
            result = store.read(key);
        } catch (Exception failure) {
            outcome = "UNKNOWN_OR_ERROR";
        }
        long completed = System.nanoTime();
        events.add(new OperationLog(
            id, clientId, sequence, "READ", key, null, result,
            started, completed, outcome
        ));
        return result;
    }

    List<OperationLog> snapshot() {
        return List.copyOf(events);
    }
}
```

**Lưu ý về ví dụ:**

- Đây là **khung minh họa**, không phải test runner production hoàn chỉnh.
- `System.nanoTime()` đo khoảng thời gian trong cùng JVM/process, không nên ghép trực tiếp các mốc này từ nhiều máy độc lập.
- `UNKNOWN_OR_ERROR` cố ý không suy ra write đã rollback. Implementation thật cần lưu phân loại exception/timeout và kết quả SDK.
- Cần ghi thêm **session ID, read path, region, replica, write concern, retry ID** nếu chúng quan trọng với claim.
- `CopyOnWriteArrayList` phù hợp để minh họa recorder với ít sự kiện, nhưng có overhead khi ghi nhiều; tải lớn có thể dùng queue/buffer được thiết kế riêng.
- Test có thể cần tách **invoke** và **completion** thành hai event để giữ cả request đang pending khi process chết. Với recorder này, nếu process test chết trước khi ghi `events.add`, operation đó không được lưu, nên cần log độc lập/bền nếu thử crash thật.

### Cách dùng cho litmus test

Một controller tạo key độc nhất `run-42-x` và `run-42-y`, sau đó điều phối hai thread/client:

```text
P1: write(x, "1") -> ACK -> read(y)
P2: write(y, "1") -> ACK -> read(x)
```

Đừng chỉ lưu giá trị cuối. Hãy lưu **operationId, process sequence, invoke/complete, result và trạng thái lỗi**. Sau đó áp consistency checker đúng mô hình.

## 19. Một bộ kiểm tra nhỏ cho sequential consistency

Với history **ít thao tác, một thanh ghi/key và không có transaction**, có thể tìm một thứ tự toàn phần bằng duyệt hoán vị, kiểm tra program order và kết quả read.

```python
from itertools import permutations

# (client_id, operation, key, write_value, read_result)
# Thứ tự xuất hiện của các thao tác cùng client là program order.
history = [
    ("P1", "WRITE", "x", 1, None),
    ("P1", "READ",  "y", None, 0),
    ("P2", "WRITE", "y", 1, None),
    ("P2", "READ",  "x", None, 0),
]

def has_sequential_witness(ops, initial):
    n = len(ops)

    for ordering in permutations(range(n)):
        position = {op_index: rank
                    for rank, op_index in enumerate(ordering)}

        # Giữ program order trong từng client.
        order_ok = all(
            not (
                ops[i][0] == ops[j][0]
                and position[i] > position[j]
            )
            for i in range(n)
            for j in range(i + 1, n)
        )
        if not order_ok:
            continue

        state = dict(initial)
        valid = True

        for index in ordering:
            _, kind, key, written, observed = ops[index]
            if kind == "WRITE":
                state[key] = written
            elif kind == "READ":
                if state.get(key) != observed:
                    valid = False
                    break
            else:
                raise ValueError("Unsupported operation")

        if valid:
            return True, ordering

    return False, None

print(has_sequential_witness(history, {"x": 0, "y": 0}))
# (False, None): store buffering với cả hai READ trả 0
```

### Giới hạn quan trọng

- Đây là bộ tìm chứng nhân **cho history nhỏ, đã biết mọi thao tác hoàn thành**.
- Độ phức tạp tối đa gần \(n!\); không dùng trực tiếp trên hàng triệu operation.
- Không xử lý transaction, CAS, retry mơ hồ hoặc pending operation.
- Không phân tích real-time order, nên **không phải linearizability checker**.
- Nếu cùng client thực sự chạy operation song song, mối quan hệ program order phải phản ánh chương trình chứ không lấy thứ tự append log một cách tùy tiện.
- Một witness tìm thấy chỉ nói **history cụ thể này có thể giải thích theo SC**, không chứng minh mọi lịch sử hệ thống đều đúng.

Với kiểm thử chuyên nghiệp, có thể dùng các checker/model phù hợp, kết hợp **property-based workloads**, fault injection và thu thập history chính xác. Kết quả checker cần được giải thích theo **mô hình và giả định về các operation pending**.

## 20. Đọc bằng chứng cho MongoDB mà không phóng đại phạm vi

Khi dùng MongoDB, các khái niệm cần đối chiếu trong documentation:

- **Write concern**: `w:1`, `w:"majority"`, journaling và thời điểm ACK.
- **Read concern**: các mức đọc được API hỗ trợ, ví dụ `local`, `majority`, `snapshot` và `linearizable` với điều kiện áp dụng riêng.
- **Read preference**: đọc primary hay secondary.
- **Causal-consistent session**: session có giữ quan hệ nhân quả khi các điều kiện được đáp ứng không?
- **Transaction**: atomic multi-document, isolation và write concern của commit.
- **Replica set failover**: những write chưa đủ điều kiện có thể bị rollback, replication lag và đọc bản cũ.

### Một câu hỏi dễ sai

> “Tôi dùng `readConcern: majority` nên mọi read đều linearizable phải không?”

Không được suy như vậy. `majority` và `linearizable` mô tả những đặc tính khác nhau. Cần đọc **đúng điều kiện của từng read concern** trên topology và API đang dùng. Một read từ secondary có thể phản ánh mốc majority nhưng không nhất thiết là phiên bản mới nhất tại thời điểm bắt đầu theo real-time requirement.

### Ví dụ yêu cầu MongoDB cần đo

```javascript
// Ví dụ học tập: tạo document có ID duy nhất.
db.consistency_demo.insertOne(
  { _id: "run-42", value: 1, version: 1 },
  { writeConcern: { w: "majority", j: true } }
);

// Đọc với read concern được chỉ định qua runCommand.
db.runCommand({
  find: "consistency_demo",
  filter: { _id: "run-42" },
  readConcern: { level: "majority" }
});
```

Không diễn giải việc read này thấy `version=1` thành bằng chứng mọi read sau ACK trên mọi secondary/region đều linearizable. Cần thiết kế thử nghiệm với routing thật, nhiều client, các phiên bản tăng dần và biết chính xác scope read concern.

### Khi dùng `linearizable`

Nếu tài liệu triển khai hỗ trợ read concern này, phải tuân thủ **đúng điều kiện sử dụng**, gồm đường đọc primary, write concern liên quan và các timeout thích hợp. Không tự áp option cho transaction/cursor/path ngoài phạm vi mà tài liệu không cho phép.

## 21. Đọc bằng chứng cho DynamoDB: base table, LSI, GSI và Global Tables

Một sai lầm phổ biến là thấy chữ **“strongly consistent read”** trong tài liệu DynamoDB rồi áp cho mọi query.

Điều cần phân biệt:

- **GetItem/Query/Scan** trên base table theo đường đọc được hỗ trợ.
- **Local secondary index (LSI)** và những lựa chọn consistency tương ứng.
- **Global secondary index (GSI)**, với đặc điểm eventual consistency theo tài liệu API.
- **Global tables** và semantics replication/consistency của kiểu triển khai multi-region cụ thể.
- **Transactions/conditional writes** để bảo vệ nhiều item hoặc invariant nghiệp vụ theo phạm vi API.

Ví dụ low-level `GetItem`:

```json
{
  "TableName": "Orders",
  "Key": {
    "PK": { "S": "ORDER#ORD-1001" },
    "SK": { "S": "META" }
  },
  "ConsistentRead": true
}
```

Ví dụ này giả định khóa chính đúng là `PK` và `SK`, và thao tác thuộc đường API cho phép `ConsistentRead`. Nó **không nói** rằng query GSI cùng lúc cũng có strong read.

### Một thí nghiệm có ý nghĩa

1. Ghi item base table với version mới.
2. Đợi ACK.
3. Đọc lại qua base table với `ConsistentRead: true`.
4. Query một GSI dẫn xuất từ item.
5. Ghi riêng thời điểm mỗi đường thấy version mới.

Nếu bước 3 thấy mới và bước 4 thấy cũ, đây là **khác biệt giữa đường base table và GSI**, không phải hai bằng chứng mâu thuẫn về cùng một API.

### Multi-region phải kiểm tra kiểu triển khai

Không tự khẳng định “Global Tables luôn eventual” hoặc “mọi region đều strong” mà không xem **phiên bản và chế độ multi-region** đang dùng. Chính sách replication và conflict handling có thể khác tùy tính năng/triển khai. Để đánh giá read-after-write xuyên region, cần ghi **region ghi, region đọc, đường API và loại ACK**.

## 22. Đọc bằng chứng cho Cassandra: consistency level không phải nhãn toàn cục

Cassandra sử dụng **replication factor (RF)** và **consistency level (CL)** như `ONE`, `QUORUM`, `LOCAL_QUORUM`, `ALL`, cùng cơ chế đặc thù cho **lightweight transactions (LWT)**.

Một thiết kế theo partition:

```sql
CREATE TABLE orders_by_customer (
    tenant_id text,
    customer_id text,
    created_at timestamp,
    order_id text,
    status text,
    PRIMARY KEY ((tenant_id, customer_id), created_at, order_id)
);
```

### Đừng suy quá mức từ \(R+W>RF\)

Trong nhiều mô tả quorum, điều kiện:

\[
R + W > RF
\]

cho biết tập replica đọc và ghi có giao nhau theo các giả định tương ứng. Nó **không tự trở thành chứng minh linearizability hoặc serializability** cho mọi thao tác Cassandra.

Còn phải xét:

- Các write cạnh tranh và cơ chế last-write-wins/timestamp.
- Clock skew giữa writer.
- Replica recovery, hinted handoff, repair và stale values.
- Phạm vi trong datacenter nào.
- Chế độ read/repair và hệ xử lý concurrent update.
- Bảo đảm đặc thù của **LWT/Paxos** nếu dùng conditional update.

### Ordinary write khác LWT

```sql
UPDATE orders_by_customer
SET status = 'SUBMITTED'
WHERE tenant_id = 'T01'
  AND customer_id = 'C007'
  AND created_at = '2026-11-14T09:00:00Z'
  AND order_id = 'ORD-1001';
```

Một lệnh ghi thông thường và lệnh conditional update dùng `IF` không nên được coi là có cùng semantics concurrency. Nếu muốn bảo vệ “chỉ đổi DRAFT → SUBMITTED nếu hiện vẫn DRAFT”, cần nghiên cứu **LWT, serial consistency và giới hạn theo partition** trên phiên bản Cassandra đang chạy.

LWT có cơ chế điều phối và chi phí cao hơn một write thông thường. Không tự nâng mọi bảng/partition thành “linearizable toàn cụm” chỉ vì hệ hỗ trợ LWT.

## 23. Redis: tuần tự trong một server khác đồng nhất toàn topology

Redis core xử lý nhiều lệnh như `GET`, `SET`, `INCR` trên một server theo semantics của lệnh. Nhưng hệ production có thể gồm:

```text
Primary -> asynchronous replicas
  |
  +--> Cluster shards / failover
  |
  +--> application cache layers
```

Một `SET` trả ACK từ primary và một `GET` từ replica sau đó có thể có hành vi khác một `GET` từ chính primary.

### Đừng lấy một lệnh atomic để suy ra transaction toàn hệ

```redis
INCR order:ORD-1001:version
GET order:ORD-1001:version
```

Một lệnh `INCR` nguyên tử không tự tạo:

- Transaction giữa Redis và MongoDB.
- Atomic visibility của nhiều shard.
- Guarantee read-after-write khi client chuyển sang replica trễ.
- Durability khi primary mất trước replication/persistence.

### `WAIT` không phải tuyên bố universal strong consistency

Redis có các cơ chế đợi replica xác nhận replication ở một số chế độ/API. Nhưng việc đợi số replica phản hồi không tự biến mọi đường đọc/failover thành linearizable transaction, và không tự đồng nghĩa dữ liệu đã fsync bền trên tất cả replica.

Khi đánh giá Redis, đọc **replication/failover contract, ACL, persistence và route của client**; sau đó thử behavior thực tế theo cấu hình.

## 24. Neo4j, graph reads và bookmark/session semantics

Trong cơ sở dữ liệu graph có cluster, một traversal có thể:

```cypher
MATCH (c:Customer {tenantId: $tenantId, customerId: $customerId})
      -[:PLACED]->(o:Order)
RETURN o.orderId;
```

Muốn đánh giá consistency, cần biết:

- Transaction được commit ở đâu?
- Query tiếp theo đọc từ server nào?
- Session có **bookmark/causal chaining** không?
- Query là một transaction read hay nhiều request độc lập?
- Những relationship mới đã được replica đọc áp dụng chưa?
- Bảo đảm nào áp dụng khi leader failover?

Với Neo4j driver, **bookmarks** có thể là cơ chế quan trọng để giữ quan hệ nhân quả giữa những transaction/session được phối hợp theo cách được hỗ trợ. Nhưng causal chaining **không đồng nghĩa** mọi client trên mọi server có một global linearizable read mặc định.

Một lần query thấy node nhưng chưa thấy edge liên quan có thể do phạm vi transaction, replica lag hoặc do ứng dụng thực tế tạo node và edge ở **hai transaction khác nhau**. Đừng quy toàn bộ kết quả cho storage consistency nếu chưa xác định mô hình ghi.

## 25. Elasticsearch/OpenSearch: refresh/visibility không phải durability của source

Search engines thường cập nhật **near-real-time index**. Sau index request, document có thể chưa hiện trong `_search` cho tới khi refresh.

```text
Source commit (MongoDB) -- CDC --> Search index write -- refresh --> _search visible
```

Có ít nhất ba mốc khác:

1. Source record đã commit.
2. Search index đã nhận/ACK write.
3. Search view đã refresh để người dùng tìm thấy.

Nếu API hỗ trợ những tùy chọn như `refresh=wait_for`, phải hiểu chính xác chúng đảm bảo **search visibility** trong phạm vi nào. Không diễn giải refresh thành journal/fsync của nguồn, hoặc thành transaction chung với Redis/broker.

### Hai bài test khác nhau

**Test source consistency:** đọc bằng API nguồn theo read concern/consistency level đã chọn.

**Test projection lag:** đo thời gian từ source commit tới khi search trả một document có `sourceVersion` bằng version nguồn.

Nếu source mạnh mà projector chậm, cần sửa **CDC/outbox, checkpoint, refresh hoặc lag**, không chỉ thay database nguồn.

## 26. Tính nhất quán khi có cache, CDN và ứng dụng trung gian

Một hệ thường có nhiều lớp:

```text
Browser cache
   |
   v
CDN / reverse proxy
   |
   v
API response cache
   |
   v
Redis cache
   |
   v
Database
```

Nếu client nhận giá trị cũ, hãy xác định **lớp nào thực sự trả response** trước khi kết luận database vi phạm claim.

### Một trace nên có

```json
{
  "requestId": "req-42",
  "logicalOperation": "ReadOrder",
  "orderId": "ORD-1001",
  "readPath": "redis-cache",
  "sourceVersion": 8,
  "returnedVersion": 6,
  "cacheAgeMs": 4200,
  "replicaRegion": "region-A"
}
```

Ví dụ dùng dữ liệu giả. Trong log production cần tránh lưu thông tin nhạy cảm, token hoặc ID cá nhân không cần thiết. **Không trả `sourceVersion` từ chính cache cũ rồi coi nó là version có thẩm quyền**; nếu cần so với nguồn, phải lấy watermark/metadata xác thực từ nguồn hoặc pipeline phù hợp.

Một query tester chỉ đo API cuối có thể kiểm tra **hợp đồng end-to-end**, nhưng để điều tra nguyên nhân phải có tracing qua từng tầng.

## 27. Kết quả thực nghiệm: “không thấy lỗi” khác “đã chứng minh đúng”

Giả sử chạy 100.000 lượt read-after-write và tất cả đều thấy giá trị mới.

Kết luận chính xác:

> Trong môi trường, tải, đường API, cấu hình và kịch bản thử đã ghi, không quan sát thấy stale read.

Không nên viết:

> Database bảo đảm linearizability trong mọi trường hợp.

Lý do:

- Có thể chưa thử **failover**.
- Chưa có **concurrent writers**.
- Test chỉ trên **một key**.
- Cache luôn nóng hoặc mọi request luôn vào primary.
- Chưa thử **multi-region**, read replica, GSI và transaction.
- Có race rất hiếm chỉ xuất hiện dưới tải hoặc mạng bất thường.
- Test có thể bỏ qua các request timeout/pending.

### Phản ví dụ mạnh hơn thống kê “chưa thấy lỗi”

Một history được ghi đầy đủ, đúng phạm vi claim, không thể giải thích theo consistency model sẽ là **bằng chứng bác bỏ** claim đó cho lần thử cụ thể. Tuy nhiên vẫn cần kiểm tra:

1. Có thao tác nền không được ghi không?
2. Giá trị ban đầu có đúng không?
3. Hai operation có thực sự thuộc cùng session/đối tượng không?
4. Client có retry ngầm không?
5. Đường API có nằm trong hợp đồng không?
6. Checker có xử lý pending write đúng không?
7. Có lỗi ở test harness hoặc đồng hồ không?

**Không né tránh phản ví dụ**, nhưng cũng không công bố kết luận quá mức dựa trên history thiếu dữ kiện.

### Số lần thử và niềm tin thống kê

Nếu một thí nghiệm độc lập có xác suất lỗi không đổi \(p\), việc không thấy lỗi trong \(n\) lần có xác suất xấp xỉ:

\[
P(\text{0 lỗi}\mid p) = (1-p)^n
\]

Đây là công thức minh họa **dưới giả định độc lập và phân bố không đổi**. Trong hệ phân tán, lỗi có thể tương quan với failover, load spike và network partition, nên không được dùng máy móc số lần thử để suy ra tỷ lệ lỗi tuyệt đối hoặc bảo đảm hình thức.

Một bài test có **fault injection đúng vào cửa sổ nguy hiểm** thường mang nhiều giá trị hơn hàng triệu lượt chỉ đọc/ghi tuần tự trong điều kiện bình thường.

## 28. Kết hợp consistency verification với phép đo hiệu năng

Mạnh hơn về consistency có thể kéo theo chi phí coordination, nhưng không có định luật rằng “strong luôn chậm” trong mọi workload và triển khai. Cần đo trên hệ thật.

Một bảng thí nghiệm:

| Chế độ read/write | p50 | p95 | p99 | Throughput | Timeout | Vi phạm quan sát |
|---|---:|---:|---:|---:|---:|---:|
| Mode A, primary read | đo | đo | đo | đo | đo | theo history |
| Mode B, replica read | đo | đo | đo | đo | đo | theo history |
| Mode C, quorum | đo | đo | đo | đo | đo | theo history |
| Mode D, failover | đo | đo | đo | đo | đo | theo history |

**Không điền số giả định như thể là kết quả thực nghiệm.** Với mỗi dòng phải ghi rõ engine version, số node, RF, placement, network RTT, workload, read/write ratio, dữ liệu và bộ điều kiện được thử.

### Những điều có thể đánh đổi

- Coordination/quorum có thể tăng latency tail trong mạng chậm.
- Local replica read thường nhanh hơn nhưng có thể cũ nếu hợp đồng cho phép.
- GSI/search giúp truy vấn nhanh nhưng có index propagation lag.
- Session tokens/read barriers giúp bảo vệ trải nghiệm một client nhưng có thể phải chờ replica bắt kịp.
- Multi-region strong coordination có thể ảnh hưởng availability/latency khi có partition.

Một lựa chọn tốt không chỉ đạt **kết quả đúng**, mà còn có throughput và latency phù hợp SLO.

## 29. Viết báo cáo thí nghiệm có thể phản biện

Một báo cáo nên có các mục:

### 29.1. Tuyên bố cần kiểm

```text
Claim: Read-after-write trên base table ở region A,
       với ConsistentRead=true, không thấy phiên bản cũ
       sau write ACK khi không có write cạnh tranh.
```

Đây là một tuyên bố cụ thể hơn “DynamoDB strong”.

### 29.2. Phạm vi và nguồn tài liệu

Ghi service, version/kiểu triển khai, API, exact read/write options, topology, đường đọc, tài liệu tham chiếu và các ngoại lệ đã biết.

### 29.3. Workload và phương pháp

Nêu key, dữ liệu ban đầu, thao tác từng client, concurrency, cách tạo non-overlap, thời gian chạy, số lượt, fault injection và cách thu thập history.

### 29.4. Kết quả thô và phân tích

Nêu:

- Số thao tác thành công/thất bại/timeout.
- Tần suất stale read trong phạm vi đo.
- Số history không có witness theo checker.
- Latency p50/p95/p99.
- Mẫu phản ví dụ nếu có.
- Bối cảnh replica lag/failover tại thời điểm xảy ra.

### 29.5. Kết luận với giới hạn

Ví dụ:

> Không quan sát thấy read cũ trong 50.000 lần read-after-write trên primary với cấu hình C, nhưng chưa thử khi leader failover hoặc khi đọc cross-region. Kết quả này ủng hộ hành vi dự kiến trong phạm vi thử, không thay thế hợp đồng chính thức và không chứng minh global linearizability.

Hoặc:

> Khi client chuyển từ replica A sang B, đã ghi được một lịch sử cùng-session đọc version 8 rồi 6, không có ghi hồi quy. Đây là phản ví dụ của monotonic reads trong đường đọc này nếu hợp đồng cam kết monotonic reads; cần xác minh session token có được chuyển đúng không.

### 29.6. Đề xuất kỹ thuật

Chọn action dựa trên phát hiện: đổi read path, bật mode phù hợp, dùng session token, thêm atomic conditional write, gom dữ liệu chung một aggregate, dùng transaction, đặt watermark cho search hoặc giảm SLA consistency nơi không cần thiết.

## 30. Những câu hỏi thiết kế để tránh suy luận nhầm

| Câu hỏi | Nếu không trả lời được |
|---|---|
| “Strong” là linearizable operation hay serializable transaction? | Không nên dùng nhãn strong một mình |
| Read path có đúng API mà docs bảo đảm không? | Chưa có cơ sở áp claim |
| Một key hay multi-key? | Không suy từ single-key sang cross-key |
| Primary hay replica/index? | Không suy từ primary sang GSI/search |
| Write ACK đã đạt mức nào? | Không mặc định dữ liệu đã bền hoặc đã replication |
| Có session semantics khi client đổi replica? | Không mặc định read-your-writes |
| Read bắt đầu sau ACK hay chồng lấn write? | Không kết luận linearizability chỉ từ timestamp thiếu điều phối |
| Có writer/reset ẩn hoặc retry không? | History có thể không đầy đủ |
| Pending operation được checker xử lý ra sao? | Kết luận có thể sai |
| Có transaction nhiều item không? | Không đánh đồng atomicity và ordering |
| Tài liệu áp dụng cho version/topology nào? | Không ngoại suy khác phiên bản |
| Failover/cross-region đã được thử chưa? | Giới hạn claim phải nêu rõ |
| Có cả cache/CDN/search trong API không? | Phải phân loại source vs projection |
| Không thấy lỗi qua bao nhiêu lượt? | Chỉ kết luận trong phạm vi thử |
| Phản ví dụ có đầy đủ history và thời điểm không? | Cần xác minh trước khi quy lỗi |

## 31. Những ngộ nhận thường gặp

| Ngộ nhận | Lý do sai | Cách diễn đạt đúng |
|---|---|---|
| “NoSQL = eventual consistency” | Các engine/API hỗ trợ nhiều mô hình | Đọc docs theo API và scope |
| “Strong = linearizable toàn hệ” | Strong không là một định nghĩa kỹ thuật duy nhất | Nêu model, đối tượng, topology |
| “Thấy read đúng một lần là strong” | Test ít concurrency không phân biệt mô hình | Thu thập history nhiều client |
| “Read cũ sau ACK luôn vi phạm sequential consistency” | SC không bắt buộc real-time order xuyên client | Kiểm tra linearizability vs SC |
| “Mỗi key strong thì multi-key transaction serializable” | Operation vs transaction khác nhau | Thử atomicity/isolation riêng |
| “Quorum đương nhiên linearizable” | Còn concurrency, timestamp, failover và hợp đồng CL | Xem API, giao thức và history |
| “ReadConcern majority = linearizable” | Mục đích/điều kiện khác nhau | Dùng đúng read concern theo claim |
| “DynamoDB strong read bao gồm mọi GSI” | GSI có semantics riêng | Phân biệt base table/LSI/GSI |
| “Kafka offset là global order mọi partition” | Offset có phạm vi partition | Xác định aggregate/partition boundary |
| “Redis primary atomic command đảm bảo cluster luôn strong” | Replication/failover/other systems khác | Kiểm tra đúng read path |
| “Search chưa thấy document nghĩa source không commit” | Search có pipeline và refresh delay | Đo source và projection riêng |
| “Timeout = write thất bại” | Commit có thể thành công nhưng ACK mất | Idempotency và kiểm tra nguồn |
| “Session token đủ cho global SC” | Bảo vệ session chưa chắc tạo total order | Xem quan hệ cross-key/client |
| “Không thấy lỗi qua 1 triệu lượt = chứng minh” | Không bao phủ mọi lịch sử/sự cố | Nêu phạm vi và giả định |
| “Sleep vài giây rồi đọc đúng = strong” | Chỉ quan sát hội tụ sau thời gian chờ | Thử read ngay sau ACK |
| “Strong consistency bảo vệ dữ liệu khỏi mất điện” | Consistency khác durability | Kiểm tra WAL/fsync/replica riêng |
| “Snapshot isolation = serializable” | Một số anomaly như write skew còn có thể | Test transaction isolation |
| “Không có phản ví dụ thì claim đúng mọi nơi” | Testing không phải proof tổng quát | Kết hợp contract + thí nghiệm |

## 32. Bài tập thực hành

### Bài 1 — Viết lại một claim mơ hồ

Một đồng nghiệp nói: “Hệ X strong và hệ Y eventual.” Hãy chuyển câu này thành hai mẫu claim có **operation, object scope, read path, write ACK, topology, version và failure assumptions**. Những điều nào chưa có nguồn để kết luận?

### Bài 2 — Đọc sau ACK của client khác

A ghi `x=1` và nhận ACK. Sau đó B bắt đầu đọc `x` và nhận `0`, không có ghi khác. Lịch sử này bác bỏ linearizability hay sequential consistency? Giải thích bằng thứ tự thực tế và thứ tự logic.

### Bài 3 — Read-your-writes

Cùng client A ghi `x=1`, nhận ACK rồi đọc `x=0`, không có writer khác. Kết quả có thể sequentially consistent không? Nếu SDK làm client chuyển session sau write, bạn cần xác minh điều gì trước khi gọi đây là vi phạm hợp đồng?

### Bài 4 — IRIW và phạm vi single-key

P1 ghi x, P2 ghi y; hai reader quan sát x rồi y và y rồi x theo những kết quả trái nhau như mục 14. Chứng minh history không SC. Nếu tài liệu chỉ cam kết per-key consistency, có quyền kết luận database vi phạm claim không?

### Bài 5 — Base table và GSI

Ghi item DynamoDB, base table strongly consistent read trả version 8 nhưng GSI query trả version 7. Cách giải thích hợp lý là gì? Viết kế hoạch thí nghiệm tách độ trễ của hai đường.

### Bài 6 — MongoDB concern

Một ứng dụng dùng `w:"majority"` cho ghi, `readConcern:"majority"` cho đọc từ secondary. Có thể tự công bố “mọi read linearizable” không? Cần đọc những phần docs nào và thử các tình huống nào?

### Bài 7 — Cassandra quorum

RF=3, W=QUORUM và R=QUORUM. Từ \(R+W>RF\), ta biết gì trong mô hình quorum? Vì sao chưa đủ chứng minh strict serializability cho mọi transaction xuyên partition?

### Bài 8 — Store buffering

P1 ghi x=1 rồi đọc y=0; P2 ghi y=1 rồi đọc x=0. Hãy viết các cạnh ràng buộc và chỉ ra chu trình ngăn một sequential witness.

### Bài 9 — Transaction nửa cập nhật

Chuyển 10 đơn vị từ A sang B bằng hai update riêng; reader thấy A đã giảm nhưng B chưa tăng. Điều này có vi phạm SC của các thao tác rời không? Mô hình nào cần thiết nếu nghiệp vụ yêu cầu giao dịch atomic?

### Bài 10 — Session migration

Một client đọc version 8 qua replica A rồi version 6 qua replica B. Hãy phân biệt “monotonic reads violation”, “read-your-writes violation” và “linearizability violation” dựa vào history và contract thực tế.

### Bài 11 — Tạo experiment report

Thiết kế một test gồm bốn client, hai key, workload concurrent, recorder và fault injection. Lập bảng ghi kết quả thô (operation ID, program sequence, invoke/complete, value, API, region). Những ràng buộc nào checker SC cần, ràng buộc nào checker linearizability cần thêm?

### Bài 12 — Đánh giá bằng chứng

Một nhóm chạy 100.000 lượt ghi rồi đọc trên primary, không thấy giá trị cũ, p95=8ms. Hãy viết **kết luận không phóng đại**, liệt kê ít nhất năm tình huống chưa được kiểm tra và đề xuất hai bài thử ưu tiên tiếp theo.

### Bài 13 — End-to-end consistency

MongoDB source version 9, Redis cache version 7, Elasticsearch index version 8. Một API trả cache version 7 sau khi người dùng vừa cập nhật. Hãy xác định tầng gây stale result và đề xuất giải pháp read-your-writes hoặc version barrier mà không suy ra MongoDB source đã không nhất quán.

### Bài 14 — Ưu tiên nghiệp vụ

Ba tính năng: tìm kiếm sản phẩm, cấp chỗ ngồi cuối cùng và thu hồi quyền xem hồ sơ. Với từng tính năng, chọn:

- Bất biến phải đúng ngay.
- Stale read có được chấp nhận không, nếu có trong phạm vi nào?
- API/source nào có thẩm quyền?
- Bài test nào đủ nhạy để phát hiện lỗi quan trọng?
- Metric và hành động fallback khi consistency target không đạt?

## 33. Checklist trước khi ra quyết định chọn NoSQL

Một checklist thực dụng, không phải “chứng chỉ strong”:

1. **Đã định nghĩa mô hình cụ thể chưa?** Linearizability, SC, causal, session hay transaction isolation?
2. **Đã nêu phạm vi chưa?** Key, document, partition, transaction, region, index?
3. **Đã kiểm tra đúng official docs theo phiên bản chưa?** Có ngoại lệ/giới hạn API?
4. **Đã xác nhận runtime configuration chưa?** Read/write concern, SDK, routing, replicas?
5. **Đã vẽ đường end-to-end chưa?** Source, GSI, cache, search, CDC và API gateway?
6. **Đã đặt bất biến nghiệp vụ chưa?** Không bán vượt, không trùng thanh toán, quyền truy cập?
7. **Đã thiết kế history thay vì một request chưa?** Nhiều client, độc lập và phụ thuộc, same/cross key?
8. **Đã kiểm tra overlap và non-overlap chưa?** Timestamp, completion và happens-before?
9. **Đã phân loại timeout/pending và retry chưa?** Tránh coi timeout là rollback?
10. **Đã thử failover/network partition chưa?** Trong môi trường cô lập với dữ liệu giả?
11. **Đã đo latency/tail và availability chưa?** Không hy sinh SLO ngoài dự kiến?
12. **Đã công bố kết luận đúng phạm vi chưa?** Không ngoại suy kết quả test thành bảo đảm toàn hệ?

Nếu một trong các câu hỏi quan trọng chưa có lời giải, nên ghi **unknown/assumption** và lên kế hoạch xác minh thay vì tô một ô “strong” hoặc “eventual”.

## 34. Kết luận

Trong NoSQL, những nhãn **“strong consistency”** và **“eventual consistency”** chỉ hữu ích như điểm bắt đầu thảo luận. Chúng **không thay thế** hợp đồng kỹ thuật về operation, object scope, path, topology và read/write settings.

Phương pháp làm việc có thể tin cậy gồm:

1. **Định nghĩa chính xác bảo đảm cần thiết** theo nghiệp vụ: một key cần linearizable read-after-write, một session cần monotonic reads, hay một transaction cần serializability?
2. **Đọc tài liệu chính thức của đúng API và phiên bản**, ghi lại điều kiện, mặc định và các ngoại lệ như replica, GSI, search, cross-region.
3. **Kiểm tra cấu hình runtime** để chắc ứng dụng thật dùng chế độ được mô tả.
4. **Thu thập history nhiều client** gồm program order, invoke/complete, giá trị đọc, ACK, timeout và đường read/write.
5. **Dùng litmus test nhạy với từng dị thường**: read-your-writes, read-after-ACK, message passing, store buffering, IRIW, transaction isolation và failover.
6. **Đánh giá bằng checker phù hợp**, phân biệt phản ví dụ cụ thể với việc chưa tìm thấy lỗi.
7. **Đo cả chi phí và giới hạn**, gồm latency, availability, replication lag, read-model lag và khả năng phục hồi.

Một hệ “strong” theo **single-item base table read** vẫn có thể có **eventual GSI**, còn một hệ hỗ trợ transaction mạnh có thể dùng **search cache bất đồng bộ**. Không có mâu thuẫn khi ta đã xác định **mỗi claim thuộc phạm vi nào**.

**Quy tắc quan trọng nhất:**

> Đừng kết luận “NoSQL này strong” hay “NoSQL kia eventual” chỉ từ tên sản phẩm hoặc một lần ghi–đọc. Hãy viết thành một tuyên bố có điều kiện, tìm nguồn tài liệu kiểm chứng được, rồi thu thập lịch sử thực nghiệm đúng phạm vi để xác nhận hoặc bác bỏ nó.
