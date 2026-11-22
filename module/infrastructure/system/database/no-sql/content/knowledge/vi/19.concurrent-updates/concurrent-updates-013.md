# Kiểm chứng lịch thực thi đồng thời bằng dữ liệu và thời điểm cụ thể

Khi một ứng dụng NoSQL có nhiều request cập nhật cùng dữ liệu, câu hỏi “database có hỗ trợ ghi nguyên tử hay không?” chưa đủ để kết luận hệ thống đúng. Một thao tác ghi trên một item có thể nguyên tử, nhưng hai request **đọc–tính–ghi** vẫn làm mất một cập nhật; hai transaction có thể không ghi đè trực tiếp lên nhau nhưng cùng phá vỡ một ràng buộc; hoặc một replica có thể trả giá trị cũ sau khi nguồn đã xác nhận ghi thành công.

Để xác định vấn đề, cần khôi phục **lịch thực thi đồng thời** (*concurrent execution history*): **ai gửi thao tác gì, đọc dữ liệu nào, vào thời điểm nào, ghi giá trị gì, nhận phản hồi nào và trạng thái cuối có thỏa hợp đồng hay không**. Các thông tin này phải dựa trên dữ liệu có thể quan sát hoặc một thí nghiệm được điều khiển, thay vì đoán thứ tự chỉ từ vài dòng log rời rạc.

Bài học đi theo một bộ ví dụ có số liệu và thời điểm cụ thể. Chúng ta sẽ:

- Dựng lịch mất cập nhật bằng hai phép tăng bộ đếm.
- Dựng lịch CAS/version có xung đột nhưng bảo toàn cả hai ý định.
- Phân biệt lịch **có thể linearize** với lịch **không thể linearize**.
- Phân tích **write skew** trên hai bản ghi và giới hạn của việc kiểm tra từng item.
- Thu thập request/response, version, mutation ID và trạng thái cuối để kiểm chứng thực nghiệm.
- Hiểu vì sao đồng hồ các node, read replica, retry và các operation chưa có phản hồi làm việc diễn giải lịch khó hơn.
- Áp dụng cách kiểm chứng với MongoDB, DynamoDB, Cassandra/CQL, Redis và Java/Python.

> **Phạm vi:** Đây là bài về **cách xây dựng và xác minh một history cụ thể**, không phải tuyên bố hệ quản trị nào cũng đảm bảo linearizability, serializability hay isolation giống nhau. Bảo đảm thực tế tùy thao tác, cấu hình nhất quán, topology và phiên bản. Các mốc giờ trong ví dụ là dữ liệu **giả lập để lập luận**, trừ khi một đoạn được ghi rõ là kết quả phải thu trong thí nghiệm.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt thời điểm **gửi yêu cầu**, **được database áp dụng** và **nhận kết quả**.
2. Biểu diễn một lịch bằng bảng thời gian, trục thời gian và danh sách các operation có giá trị đầu vào/đầu ra.
3. Dùng **thứ tự xảy ra trước** (*happens-before*) và những operation chồng lấn để tìm các thứ tự tuần tự có thể chấp nhận.
4. Kiểm chứng kết quả theo một **đặc tả tuần tự** (*sequential specification*) và một **bất biến nghiệp vụ**.
5. Phân biệt lost update của **ý định nghiệp vụ** với tính nguyên tử của từng GET/SET cơ sở dữ liệu.
6. Không kết luận sai về thứ tự từ timestamp giữa các máy có đồng hồ lệch.
7. Dùng CAS/version/conditional write và lịch sử phản hồi để giải thích vì sao một request thành công hoặc thất bại.
8. Thiết kế test tái lập race condition, fault injection và kiểm tra event trùng/sai thứ tự.
9. Hiểu những giới hạn của một trình kiểm tra history nhỏ và khi nào cần mô hình hoặc công cụ phân tích nghiêm ngặt hơn.

## 2. Lịch thực thi là gì?

Một **operation** có thể được biểu diễn bằng:

~~~text
Operation = (
    operationId,
    clientId,
    method,
    arguments,
    invokedAt,
    completedAt,
    response,
    targetKey
)
~~~

Ví dụ:

~~~json
{
  "operationId": "inc-A",
  "clientId": "client-A",
  "method": "incrementAndGet",
  "arguments": {
    "counterId": "visits:shop-12",
    "delta": 1
  },
  "invokedAt": "2026-11-14T09:00:00.000Z",
  "completedAt": "2026-11-14T09:00:00.023Z",
  "response": {
    "status": "SUCCESS",
    "newValue": 6
  }
}
~~~

Ở đây **invokedAt** là lúc client bắt đầu operation, **completedAt** là lúc client nhận một phản hồi cuối cùng cho operation ấy. Hai mốc tạo thành **khoảng thời gian của operation**, không nói chính xác lệnh đã được áp trong database ở mili giây nào.

### 2.1. Lịch không chỉ là chuỗi lệnh ghi

Một history dùng để kiểm chứng thường cần cả:

- **Lời gọi** (invocation) của read/write/CAS.
- **Phản hồi** (completion), gồm kết quả đọc, thành công, conflict hoặc timeout.
- **Giá trị** đã đọc trước khi tính toán.
- **Điều kiện ghi** đã gửi và **giá trị** thực sự được đề xuất.
- **ID phiên bản**, operation ID, request ID, transaction ID.
- **Lần đọc xác minh** sau khi những request cần xét đã kết thúc.

Nếu log chỉ có:

~~~text
09:00:00 Request A started
09:00:00 Request B started
09:00:00 Request A completed
09:00:00 Request B completed
~~~

ta **chưa biết** A/B đã đọc giá trị nào, có conflict không, có ghi thành công không, hoặc đã trừ tồn kho một hay hai lần.

### 2.2. Ba mốc trong một lần ghi

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Service
    participant D as Database
    C->>S: Invoke reserve (t0)
    S->>D: Conditional write
    Note over D: Một thời điểm/ranh giới áp mutation
    D-->>S: Commit acknowledgment
    S-->>C: Response (t1)
~~~

Trong trường hợp thao tác có thể được xem là nguyên tử, người phân tích thường tìm một **điểm tuyến tính hóa** (*linearization point*) nằm trong khoảng từ invocation tới response. Điểm ấy là **mô hình logic để giải thích thao tác như xảy ra tức thời**; không nhất thiết có thể đọc trực tiếp nó như một timestamp đơn lẻ trong log.

## 3. Thứ tự thực tế: trước, sau và chồng lấn

Giả sử cùng một đồng hồ kiểm soát dùng trong thí nghiệm:

~~~text
A:  |--------- invoke A --------- response A |
B:       |------ invoke B ------ response B |
C:                                                  |--- invoke C --- response C |
~~~

A và B **chồng lấn**: từ history cấp client, ta chưa thể khẳng định A phải linearize trước B hay ngược lại. Nhưng cả hai đã hoàn tất **trước lúc C bắt đầu**, nên nếu hệ thống cam kết linearizability của cùng object, C phải quan sát trạng thái phù hợp với cả hai operation thành công.

Ký hiệu:

\[
A \prec B \quad\text{khi response(A) xảy ra trước invocation(B)}
\]

Quan hệ \(\prec\) là ràng buộc **thứ tự thời gian thực được chứng minh**. Khi các operation chồng lấn, không có cạnh \(\prec\) chỉ dựa trên thứ tự invocation.

### 3.1. Ví dụ thứ tự bắt buộc

| Operation | Bắt đầu (ms) | Kết thúc (ms) | Quan hệ |
| --- | ---: | ---: | --- |
| A | 0 | 10 | Hoàn tất trước C |
| B | 5 | 15 | Chồng lấn A và C nếu C bắt đầu tại 12 |
| C | 12 | 20 | A bắt buộc trước C; B/C có thể đổi thứ tự |

Không thể chỉ nhìn “B bắt đầu trước C” rồi suy B đã hoàn thành trước C. **Thứ tự bắt đầu khác thứ tự hiệu lực**.

### 3.2. Concurrent nghĩa là gì?

Trong lập luận này, hai operation là *concurrent/overlapping* nếu các khoảng invocation–completion có giao nhau và lịch quan sát **không áp đặt quan hệ response-before-invocation** giữa chúng.

Điều đó không có nghĩa CPU chắc chắn chạy hai lệnh **cùng đúng một nanosecond**. Trên một database chỉ xử lý từng mutation theo một thứ tự, hai request vẫn có thể overlap ở lớp client, vì cả hai đang chờ lượt.

## 4. Lịch H1: hai lần tăng nhưng chỉ tăng được một

Đặc tả nghiệp vụ:

> Có một bộ đếm nguyên, ban đầu bằng **5**. Mỗi operation `incrementAndGet(counter, +1)` được xác nhận thành công phải tăng bộ đếm **đúng một** và trả giá trị sau tăng.

Hai client A/B cùng gọi tăng. Ứng dụng triển khai sai bằng **GET → tính +1 → SET**.

### 4.1. Timeline với mốc UTC cụ thể

Tất cả mốc dưới đây được giả định lấy trên **một trục thời gian đáng tin cậy** trong môi trường thử nghiệm:

| Thời điểm UTC | Actor | Hành động | Dữ liệu và kết quả |
| --- | --- | --- | --- |
| 09:00:00.000 | A | Gọi `incrementAndGet` | Bắt đầu operation A |
| 09:00:00.003 | B | Gọi `incrementAndGet` | Bắt đầu operation B |
| 09:00:00.008 | A | GET counter | Trả `5` |
| 09:00:00.010 | B | GET counter | Trả `5` |
| 09:00:00.015 | A | Tính giá trị mới | `5 + 1 = 6` |
| 09:00:00.017 | B | Tính giá trị mới | `5 + 1 = 6` |
| 09:00:00.020 | A | SET counter = 6 | Database chấp nhận |
| 09:00:00.023 | A | Trả thành công | Kết quả A = `6` |
| 09:00:00.026 | B | SET counter = 6 | Database chấp nhận |
| 09:00:00.030 | B | Trả thành công | Kết quả B = `6` |
| 09:00:00.040 | R | Đọc xác minh | Gọi GET counter |
| 09:00:00.044 | R | GET counter | Trả `6` |
| 09:00:00.050 | R | Trả kết quả | Kết quả R = `6` |

Biểu diễn ngắn:

~~~text
09:00:00.000  A.invoke INC
09:00:00.003  B.invoke INC
09:00:00.008  A.GET -> 5
09:00:00.010  B.GET -> 5
09:00:00.020  A.SET(6) -> OK
09:00:00.023  A.response INC(6)
09:00:00.026  B.SET(6) -> OK
09:00:00.030  B.response INC(6)
09:00:00.040  R.invoke READ
09:00:00.050  R.response READ(6)
~~~

### 4.2. Kết quả kỳ vọng theo đặc tả tuần tự

Nếu cả hai operation tăng **thật sự thành công**, bất kể A hay B chạy trước:

~~~text
Ban đầu: 5
Sau lần tăng thứ nhất: 6
Sau lần tăng thứ hai: 7
R đọc sau khi cả hai hoàn tất: 7
~~~

Kết quả quan sát `R=6` **không thỏa** đặc tả “hai lần tăng thành công thì giá trị là 7”.

Ngoài ra, nếu API `incrementAndGet` phải trả số mới, không thể có **hai lần tăng liên tiếp** cùng trả số 6 trong một lịch tuần tự bắt đầu ở 5.

### 4.3. Điểm tinh tế: GET và SET vẫn có thể nguyên tử

Ta phải phân biệt hai tầng:

**Tầng database:**

~~~text
A.GET -> 5
B.GET -> 5
A.SET(6) -> OK
B.SET(6) -> OK
R.GET -> 6
~~~

Chuỗi GET/SET này hoàn toàn có thể phù hợp với **một register có các lệnh GET và SET nguyên tử**. Không có bằng chứng database thực thi từng GET hay SET sai.

**Tầng API nghiệp vụ:**

~~~text
A.incrementAndGet(+1) -> 6, SUCCESS
B.incrementAndGet(+1) -> 6, SUCCESS
R.read() -> 6
~~~

History không thể được giải thích bằng **hai lần increment nguyên tử thành công**. Lỗi nằm ở cách **ghép nhiều thao tác nguyên tử rời rạc thành một operation nghiệp vụ**, nhưng không có ranh giới nguyên tử cho toàn bộ phép tăng.

Đây là lý do khi kiểm chứng lịch, phải xác định **đối tượng và đặc tả của operation** trước: đang kiểm tra GET/SET thô, hay đang kiểm tra API `incrementAndGet` được hứa với người dùng?

### 4.4. Nếu chỉ nhìn giá trị cuối thì có đủ?

Trong ví dụ này, nếu biết chắc ban đầu = 5, có **đúng hai ý định tăng độc lập đã được xác nhận** và không có writer khác, cuối = 6 đã cho thấy bất biến bị vi phạm.

Nhưng trong production, chỉ có `counter=6` là **chưa đủ** để kết luận:

- Có thể một request thất bại.
- Có thể có một decrement hợp lệ khác.
- Có thể cả hai request dùng cùng `requestId` nên thực ra là một ý định bị retry.
- Có thể lần đọc cuối lấy từ replica stale.
- Có thể dữ liệu được reset bởi một thao tác có thẩm quyền.

Cần **history đầy đủ, kết quả từng operation và nguồn đọc xác minh**.

## 5. Lịch H2: dùng CAS/version để bảo toàn cả hai lần tăng

Giả sử ban đầu:

~~~json
{
  "counterId": "visits:shop-12",
  "value": 5,
  "version": 9
}
~~~

Ứng dụng dùng optimistic concurrency control (OCC): đọc cả `value` và `version`; khi ghi, điều kiện yêu cầu `version` **vẫn bằng version đã đọc**; nếu cập nhật thành công, tăng version **trong cùng mutation**.

### 5.1. Timeline CAS cụ thể

| Thời điểm UTC | Actor | Hành động | Dữ liệu/kết quả |
| --- | --- | --- | --- |
| 09:01:00.000 | A | Invoke increment | — |
| 09:01:00.003 | B | Invoke increment | — |
| 09:01:00.005 | A | Read | `value=5, version=9` |
| 09:01:00.007 | B | Read | `value=5, version=9` |
| 09:01:00.011 | A | CAS expected v9 → value6/v10 | **Success** |
| 09:01:00.013 | A | Response | `incrementAndGet -> 6` |
| 09:01:00.016 | B | CAS expected v9 → value6/v10 | **Conflict**, không ghi |
| 09:01:00.019 | B | Read lại | `value=6, version=10` |
| 09:01:00.025 | B | CAS expected v10 → value7/v11 | **Success** |
| 09:01:00.028 | B | Response | `incrementAndGet -> 7` |
| 09:01:00.040 | R | Read xác minh | `value=7, version=11` |

Kết quả đúng:

~~~text
initial: value=5, version=9
A commits: value=6, version=10
B CAS v9: rejected
B retries using v10
B commits: value=7, version=11
final read: value=7, version=11
~~~

### 5.2. Vì sao có thể tuyến tính hóa?

Hai operation API A và B overlap. Một thứ tự tuần tự hợp lệ:

~~~text
A.incrementAndGet -> 6
B.incrementAndGet -> 7
R.read -> 7
~~~

Thứ tự này phù hợp với đặc tả và ràng buộc thời gian: R bắt đầu sau khi A/B đã hoàn tất. Điểm hiệu lực logic của hai operation là những **CAS thành công**.

**CAS thất bại của B không phải một lần increment thành công**, nên không được cộng thêm vào số ý định đã được áp. B **cùng một operation nghiệp vụ** có thể thử ghi nhiều lần; chỉ một mutation CAS thành công được xem là hiệu lực.

### 5.3. Atomic increment có thể đơn giản hơn CAS

Nếu bài toán chỉ là “tăng 1 bất kể giá trị cũ”, một **atomic increment** như MongoDB `$inc` có thể phù hợp hơn việc đọc version, tranh CAS rồi retry.

Nhưng nếu quyết định phụ thuộc **điều kiện từ snapshot** (ví dụ chỉ chuyển trạng thái READY sang SHIPPED nếu đúng bản đã xem), CAS/version giúp phát hiện sự thay đổi mà atomic increment đơn giản không biểu đạt.

## 6. Bốn câu hỏi để xác minh một lịch

Với một history, hãy lần lượt hỏi:

1. **Đặc tả tuần tự là gì?** Sau một operation hợp lệ, dữ liệu phải chuyển thế nào và trả response gì?
2. **Những operation nào đã hoàn tất và được xác nhận?** Operation nào timeout, pending, thất bại có điều kiện?
3. **Thứ tự nào bị thời gian thực bắt buộc?** Nếu A hoàn tất trước khi B bắt đầu, có thể đặt B trước A không?
4. **Có tồn tại một thứ tự tuần tự vừa thỏa đặc tả vừa giữ những ràng buộc ấy không?**

Nếu tồn tại, history **có thể phù hợp với linearizability** theo mô hình và bằng chứng đang có. Nếu không tồn tại, **history vi phạm linearizability** của object/operation được định nghĩa, với giả định log và kết quả chính xác.

Lưu ý: việc tìm thấy một thứ tự hợp lệ chỉ xác minh **history đã quan sát**, không chứng minh mọi history tương lai của hệ thống đều đúng.

## 7. Linearizability: điều kiện rõ ràng hơn “các thao tác chạy tuần tự”

**Linearizability** là một thuộc tính của history trên object đồng thời. Trực giác: mỗi operation hoàn tất có thể xem như có hiệu lực tại **một điểm** giữa lúc gọi và lúc trả kết quả; các operation không chồng lấn phải tôn trọng thứ tự thời gian thực.

Với một register có:

~~~text
write(x) -> OK
read()   -> x
~~~

và giả định không có writer ẩn, ta có thể kiểm tra những lịch đơn giản bằng bảng thời gian.

### 7.1. Lịch H3: hai write chồng lấn, read trả giá trị của write bắt đầu trước

Ban đầu `x=0`:

| Operation | Invoke (ms) | Response (ms) | Kết quả |
| --- | ---: | ---: | --- |
| W1: `write(1)` | 0 | 30 | OK |
| W2: `write(2)` | 10 | 20 | OK |
| R: `read()` | 40 | 50 | 1 |

W2 **bắt đầu sau** W1 nhưng **hoàn tất trước** W1. Hai write overlap. Một thứ tự tuần tự hợp lệ là:

~~~text
W2.write(2) -> OK
W1.write(1) -> OK
R.read() -> 1
~~~

Điều này **không vi phạm linearizability**, dù W2 hoàn tất sớm hơn. Không được suy hiệu lực của operation chỉ từ **thời điểm invocation** hay **thời điểm response** khi chúng chồng lấn.

### 7.2. Lịch H4: write đã hoàn tất, read sau đó thấy giá trị cũ

Ban đầu `x=0`, không có write khác:

| Operation | Invoke (ms) | Response (ms) | Kết quả |
| --- | ---: | ---: | --- |
| W: `write(1)` | 0 | 10 | OK |
| R: `read()` | 20 | 30 | 0 |

W đã hoàn tất **trước** R bắt đầu. Để tuyến tính hóa, W phải đứng trước R; khi đó R phải trả 1. Trả 0 **không phù hợp với linearizability** của cùng register trong mô hình ấy.

Nhưng nếu R đọc từ **replica eventual-consistent** và hợp đồng hệ thống chỉ hứa eventual consistency, lịch trên **có thể là hành vi được phép** của cấu hình ấy. Kết luận đúng không phải “mọi database đọc 0 đều hỏng”, mà là:

> “History H4 không thỏa hợp đồng **linearizable read-after-write**; cần xem mức nhất quán mà API thực sự cam kết.”

### 7.3. Read từ một replica khác không phải bằng chứng đầy đủ về commit

Nếu W chỉ được một coordinator chấp nhận nhưng chưa đạt điều kiện ack/commit yêu cầu, hoặc R dùng chế độ đọc yếu hơn, phải ghi rõ:

- Mức nhất quán của W.
- Điểm/loại ack mà W trả.
- Mức nhất quán của R.
- R đọc từ primary, quorum hay read replica.
- Có failover, split-brain, partition hoặc retry đang diễn ra không.

Không áp tiêu chí linearizability vào hai đường API có hợp đồng consistency khác nhau mà không nêu rõ giả định.

## 8. Serializability, strict serializability và linearizability

Các khái niệm có quan hệ nhưng **không đồng nghĩa**.

| Khái niệm | Đối tượng chính | Ràng buộc quan trọng |
| --- | --- | --- |
| **Linearizability** | Operation trên object concurrent | Kết quả tương đương chuỗi nguyên tử **và** tôn trọng thứ tự thực giữa operation không overlap |
| **Serializability** | Các transaction | Kết quả tương đương một thứ tự transaction tuần tự, **không nhất thiết giữ thứ tự real-time** |
| **Strict serializability** | Các transaction | Serializability cộng ràng buộc real-time |
| **Snapshot isolation** | Transaction trên snapshot | Có thể ngăn nhiều xung đột, nhưng **có thể vẫn cho write skew** |
| **Eventual consistency** | Replica/read model | Các replica có thể tạm khác nhau; hội tụ khi không còn thay đổi, theo giả định của hệ |

Không nên suy:

~~~text
Mỗi document update nguyên tử
=> toàn workflow nhiều document serializable
~~~

hoặc:

~~~text
Transaction commit thành công
=> mọi read trên mọi replica ngay lập tức linearizable
~~~

Phải xét **ranh giới object/transaction, read/write mode và isolation** cụ thể.

### 8.1. Vì sao phải viết đặc tả cho đúng phạm vi?

Nếu hệ quản trị chỉ hứa **atomic conditional write trên một item**, hãy kiểm tra invariant của item ấy. Nếu nghiệp vụ hứa **giữ stock + tạo reservation luôn đồng bộ**, cần kiểm tra lịch nhiều entity và các transaction/workflow tương ứng.

Một bằng chứng về linearizability của một key **không tự bảo vệ ràng buộc xuyên hai key**.

## 9. Lịch H5: write skew trên hai bản ghi

Hệ thống phân ca:

~~~text
Doctor A: ON_DUTY
Doctor B: ON_DUTY

Invariant: A hoặc B phải ON_DUTY.
~~~

Hai bác sĩ độc lập yêu cầu rời ca, mỗi người chỉ được rời nếu người còn lại đang trực. Các transaction:

~~~text
TA: đọc A/B, thấy B=ON_DUTY -> ghi A=OFF_DUTY.
TB: đọc A/B, thấy A=ON_DUTY -> ghi B=OFF_DUTY.
~~~

### 9.1. Lịch cụ thể

| Thời điểm UTC | Transaction | Thao tác | Quan sát |
| --- | --- | --- | --- |
| 09:03:00.000 | TA | BEGIN | — |
| 09:03:00.002 | TB | BEGIN | — |
| 09:03:00.006 | TA | READ(A,B) | (ON, ON) |
| 09:03:00.008 | TB | READ(A,B) | (ON, ON) |
| 09:03:00.013 | TA | WRITE A=OFF | Đang giao dịch |
| 09:03:00.015 | TB | WRITE B=OFF | Đang giao dịch |
| 09:03:00.021 | TA | COMMIT | SUCCESS |
| 09:03:00.024 | TB | COMMIT | SUCCESS |
| 09:03:00.032 | R | READ(A,B) | (OFF, OFF) |

Không có hai transaction cùng ghi một record, nên **CAS chỉ trên bản ghi mình sửa** có thể không phát hiện conflict.

### 9.2. Vì sao không có thứ tự transaction tuần tự hợp lệ?

Nếu TA chạy trước:

~~~text
TA thấy B=ON -> A=OFF
TB chạy sau thấy A=OFF -> TB không được tắt B
~~~

Nếu TB chạy trước:

~~~text
TB thấy A=ON -> B=OFF
TA chạy sau thấy B=OFF -> TA không được tắt A
~~~

Không thứ tự nào cho phép **cả hai** cùng rời ca theo quy tắc. Đây là **write skew**, một ví dụ vi phạm serializability của logic giao dịch ấy.

### 9.3. Phương án bảo vệ invariant

Có thể:

- Gom quy tắc vào **một entity có thẩm quyền** (ví dụ row/record `onDutyCount` cập nhật có điều kiện).
- Dùng transaction/isolation có khả năng **phát hiện xung đột đọc–ghi** hoặc cơ chế tạo write conflict cho invariant.
- Dùng **conditional transaction** thích hợp trên các item liên quan, với đọc/điều kiện kiểm soát đúng.
- Áp một service/khóa điều phối có bảo đảm rõ cho quyết định rời ca.

Chỉ bọc hai lần đọc và hai lần ghi vào “transaction” không đủ nếu **isolation** vẫn cho phép write skew. Cần kiểm tra đặc tả và hành vi của engine đang dùng.

## 10. Lịch H6: timeout không cho biết mutation đã thực thi hay chưa

Một khách gửi yêu cầu giữ hàng:

~~~json
{
  "requestId": "reserve-42",
  "sku": "SKU-7",
  "quantity": 1
}
~~~

Giả sử stock ban đầu là 5:

| Thời điểm UTC | Actor | Sự kiện |
| --- | --- | --- |
| 09:04:00.000 | Client | Gửi `reserve-42` |
| 09:04:00.006 | Database | Chấp nhận decrement từ 5 → 4 |
| 09:04:00.009 | Network | Phản hồi bị mất |
| 09:04:00.050 | Client | Timeout |
| 09:04:00.060 | Client | Retry **cùng `requestId`** |
| 09:04:00.067 | Database | Nếu không dedup: decrement từ 4 → 3 |
| 09:04:00.072 | Client | Nhận SUCCESS |

Client có thể tin rằng “một request đã thành công”, trong khi stock giảm **2**. Atomic decrement không giúp biết hai lần decrement này là **một ý định bị retry**.

### 10.1. Phải phân biệt logical operation và attempt

Một request nghiệp vụ có thể có nhiều lần thử:

~~~text
logicalRequestId = reserve-42
    attemptId = reserve-42-attempt-1  -> timeout/unknown
    attemptId = reserve-42-attempt-2  -> success
~~~

Log phải giữ cả hai tầng:

- **Logical request ID** ổn định qua retry, định danh **một ý định**.
- **Attempt ID** riêng cho từng lần gửi để dựng timeline network/driver.
- **Mutation/transaction ID** hoặc dấu vết nguồn đủ để biết ý định đã được áp hay chưa.

### 10.2. Idempotency ledger

Ví dụ record:

~~~json
{
  "requestId": "reserve-42",
  "payloadHash": "canonical-request-hash",
  "state": "SUCCEEDED",
  "reservationId": "R42",
  "appliedStockDelta": -1
}
~~~

Khi nhận retry:

- Nếu ID và payload khớp, trả kết quả đã lưu, không trừ thêm.
- Nếu ID khớp nhưng payload khác, từ chối tái sử dụng ID.
- Nếu đang xử lý, cung cấp trạng thái `PENDING`/đường đối soát.
- Ledger và mutation cần được phối hợp **trong một ranh giới giao dịch hoặc một workflow phục hồi được**; nếu ghi ledger sau khi trừ stock mà crash giữa hai bước, vẫn có cửa sổ double apply.

### 10.3. Đừng gán “FAILED” cho mọi timeout

Lúc 09:04:00.050, client chỉ biết **chưa nhận phản hồi**. Nó không biết database đã commit hay chưa nếu không có tín hiệu độc lập. Trong bảng lịch, phải ghi:

~~~text
result = UNKNOWN_OUTCOME
~~~

Không tự đổi thành:

~~~text
result = WRITE_NOT_APPLIED
~~~

nếu không có bằng chứng.

## 11. Một log history tốt cần thu những trường nào?

Đối với mỗi operation, nên có:

| Nhóm | Field ví dụ | Mục đích |
| --- | --- | --- |
| Định danh | `traceId`, `operationId`, `logicalRequestId`, `attemptId` | Liên kết các lần thử và nhiều dịch vụ |
| Đối tượng | `tenantId`, `entityId`, `partitionKey` | Biết hai request có tranh chấp cùng dữ liệu không |
| Operation | `method`, `arguments`, `expectedVersion` | Viết được đặc tả tuần tự |
| Bắt đầu/kết thúc | `clientInvokedAt`, `clientCompletedAt` | Xác định khoảng operation |
| Server | `serverReceivedAt`, `serverRespondedAt` | Phân biệt queue/network với DB execution |
| Kết quả read | `readValue`, `observedVersion` | Biết snapshot dùng tính toán |
| Kết quả write | `conditionMatched`, `newVersion`, `mutationAck` | Thành công, conflict hay không rõ |
| Routing | `nodeId`, `shardId`, `consistencyMode` | Diễn giải replica/leader/partition |
| Transaction | `transactionId`, `commitToken` nếu có | Liên hệ commit, snapshot và event log |
| Retry | `retryReason`, `retryCount` | Không đếm attempt thành nhiều ý định |
| Correlation | `sourceEventVersion`, `outboxId` | Theo dõi projection và replay |

### 11.1. Ví dụ một dòng log có cấu trúc

~~~json
{
  "traceId": "trace-8f2",
  "logicalRequestId": "reserve-42",
  "attemptId": "reserve-42-1",
  "entityKey": "merchant-a/SKU-7",
  "operation": "reserve",
  "quantity": 1,
  "clientInvokedAt": "2026-11-14T09:04:00.000Z",
  "serverReceivedAt": "2026-11-14T09:04:00.002Z",
  "sourceVersionBefore": 13,
  "sourceVersionAfter": 14,
  "databaseOutcome": "APPLIED",
  "clientOutcome": "TIMEOUT",
  "readConsistency": "specified-by-service",
  "writeConsistency": "specified-by-service"
}
~~~

Đây là **ví dụ dữ liệu cấu trúc**, không phải format bắt buộc của một vendor. `databaseOutcome=APPLIED` chỉ nên được ghi khi server/hệ thống **có bằng chứng đáng tin**, không suy từ việc client timeout.

### 11.2. Cần bảo vệ log

Không log password, access token, dữ liệu thanh toán nhạy cảm hoặc toàn bộ document khách hàng chỉ để dựng lịch. Có thể dùng:

- Entity ID giả danh/hashed có quản lý quyền phù hợp.
- Phiên bản, số lượng, status và delta đã được cho phép.
- Hash payload thay cho payload đầy đủ nếu cần đối chiếu.
- Retention và quyền truy cập log riêng.

Một công cụ quan sát đồng thời không nên tự tạo bản sao dữ liệu nhạy cảm ngoài chính sách lưu giữ.

## 12. Đồng hồ giữa các node không phải một thước đo tuyệt đối

Giả sử:

~~~text
Node A: đồng hồ chạy nhanh hơn UTC thật 200 ms
Node B: đồng hồ chạy chậm hơn UTC thật 150 ms
~~~

Sự kiện thực:

~~~text
UTC thật 09:05:00.100: A gửi write.
UTC thật 09:05:00.150: B nhận bản tin từ A.
~~~

Timestamp ghi log:

~~~text
A log: 09:05:00.300
B log: 09:05:00.000
~~~

Nếu sort log theo chuỗi timestamp, nhìn như B nhận **trước** khi A gửi 300 ms, dù quan hệ causal thật là **A gửi trước B nhận**.

### 12.1. Dùng monotonic clock cho thời lượng trong một process

Để đo khoảng thời gian:

~~~java
long startNs = System.nanoTime();
// Thực hiện request.
long elapsedNs = System.nanoTime() - startNs;
~~~

`System.nanoTime()` phục vụ **elapsed-time đo trong một JVM/điều kiện phù hợp**, không phải UTC instant và không được so trực tiếp những số nanoTime từ các JVM/máy khác nhau như cùng một trục thời gian toàn cục.

### 12.2. Wall-clock UTC vẫn hữu ích nhưng cần độ bất định

UTC timestamp giúp liên kết log, nhưng cần biết:

- Đồng hồ có được đồng bộ NTP/PTP không?
- Độ lệch ước lượng và mức **uncertainty** là bao nhiêu?
- Clock có bị điều chỉnh gần thời điểm thử nghiệm không?
- Log được ghi lúc event xảy ra hay sau khi queue/buffer flush?
- Có dùng timestamp do client gửi không đáng tin không?

Nếu không có bound đồng hồ đủ tốt, **không thể chứng minh cạnh response-before-invocation giữa hai node chỉ bằng việc sort timestamp**.

### 12.3. Quan hệ nhân quả đáng tin hơn số mili giây thiếu đồng bộ

Một số quan hệ có thể suy từ sự kiện:

~~~text
A gửi message M
    -> B nhận đúng message M
    -> B tạo operation X do M
~~~

Đây là quan hệ *happens-before* theo thông tin causal và message ID, không phụ thuộc việc hai timestamp wall clock có đảo thứ tự.

Lamport clocks, vector clocks hoặc hybrid logical clocks có thể giúp ghi nhận **thứ tự logic/quan hệ causal** trong những hệ hỗ trợ; nhưng **không tự biến các API đọc/ghi thành linearizable hoặc serializable**. Hơn nữa, thứ tự logic không thay thế mọi yêu cầu về thứ tự real-time của linearizability.

### 12.4. Đừng tự gán thứ tự cho các operation overlap

Nếu A và B overlap theo bằng chứng:

~~~text
A: [invoke ---------------- response]
B:       [invoke ----- response]
~~~

thì hệ thống **có thể** linearize B trước A. Để kết luận “B bắt buộc trước A”, cần chứng cứ mạnh hơn một timestamp log bị lệch, ví dụ thứ tự commit nguồn đáng tin trong cùng sequencer hoặc bằng chứng giao dịch cụ thể.

## 13. Lấy snapshot dữ liệu thế nào để không kiểm chứng nhầm?

Một truy vấn xác minh sau khi chạy concurrent test nên nói rõ:

1. **Đọc từ đâu?** Primary, leader, quorum, replica hay read model?
2. **Đọc với consistency nào?**
3. **Đã đợi tất cả operation cần xét hoàn tất chưa?**
4. **Có writer nền nào khác không?**
5. **Có phải cùng một generation/version của entity không?**
6. **Đọc nhiều key có thuộc cùng một snapshot logic không?**

### 13.1. Đọc xác minh một key

Ví dụ sau khi hai CAS thành công:

~~~text
expected: value=7, version=11
observed: value=7, version=11
~~~

Điều đó phù hợp với history H2, nhưng chỉ có final snapshot chưa chứng minh **mọi thao tác trung gian** đều tuân thủ điều kiện; log và outcome vẫn quan trọng.

### 13.2. Đọc xác minh nhiều key

Giả sử:

~~~text
Order.status = CONFIRMED
Inventory.available = 0
Reservation.status = ACTIVE
~~~

Nếu đọc ba key từ ba dịch vụ tại ba thời điểm khác nhau, kết quả là **ba quan sát**, không mặc nhiên là một snapshot transaction. Dữ liệu có thể thay đổi trong lúc kiểm tra.

Với invariant đa entity, cần chọn nguồn/transaction/snapshot có bảo đảm phù hợp, hoặc dùng **version/checkpoint và đối soát** để chứng minh chúng tương ứng với cùng một giai đoạn logic.

### 13.3. Một entity có thể bị xóa rồi tạo lại

Nếu record `SKU-7` bị xóa và tạo lại với cùng khóa, `version=1` hiện tại không nhất thiết giống `version=1` cũ. Khi có vòng đời recreate, nên quan sát thêm **generation/epoch**, unique entity ID hoặc deletion marker để không ghép nhầm hai lịch của hai thế hệ entity khác nhau.

## 14. MongoDB: ghi lại lịch conditional update theo version

Giả sử collection:

~~~javascript
db.counters.insertOne({
  _id: "visits:shop-12",
  value: 5,
  version: 9
});
~~~

Một request A đã đọc:

~~~javascript
const old = db.counters.findOne({
  _id: "visits:shop-12"
});

// old.value = 5, old.version = 9
~~~

Thay vì ghi đè dựa trên `old.value` với filter chỉ theo ID, dùng:

~~~javascript
const result = db.counters.updateOne(
  {
    _id: "visits:shop-12",
    version: old.version
  },
  {
    $set: { value: old.value + 1 },
    $inc: { version: 1 }
  }
);

if (result.modifiedCount === 1) {
  print("CAS_APPLIED");
} else {
  print("CAS_CONFLICT_OR_NOT_FOUND");
}
~~~

Nếu A đã cập nhật v9→v10 trước B, một B vẫn dùng expectedVersion 9 sẽ không khớp. **Cần log cả expectedVersion, modifiedCount, lỗi/timeout và version đọc lại**.

### 14.1. Atomic increment tốt hơn cho counter đơn giản

Nếu ý định chỉ là tăng `value` một đơn vị, không cần tính toán dựa trên snapshot:

~~~javascript
db.counters.updateOne(
  { _id: "visits:shop-12" },
  { $inc: { value: 1, version: 1 } }
);
~~~

Hai mutation `$inc` thành công trên **cùng document** không tự làm mất phép tăng như hai lệnh `$set` lấy từ cùng snapshot cũ. Tuy nhiên, nếu một logical request có thể gửi lại, vẫn cần idempotency để không cộng hai lần.

### 14.2. Nên ghi gì khi phân tích?

| Field | Ví dụ |
| --- | --- |
| `operationId` | inc-A |
| `readValue/version` | 5 / 9 |
| `updateFilter` | `_id + version=9` |
| `proposedValue` | 6 |
| `modifiedCount` | 1 |
| `postVersion` | 10 |
| `clientStart/end` | Timestamps cùng nguồn quan sát |
| `writeConcern/readConcern` | Cấu hình thực |
| `retryableWrite/idempotency` | Quy tắc thực tế |

Không khẳng định một read từ bất kỳ replica nào luôn thấy mutation ngay sau ack. Các bảo đảm đọc của MongoDB phụ thuộc **read concern, write concern, session/causal context và cấu hình cluster**.

### 14.3. Hai document và transaction

Nếu bất biến liên quan cả Order và Inventory, atomic update trên **mỗi document riêng** không chứng minh toàn workflow nguyên tử. Cần transaction nhiều document hoặc thiết kế workflow khác theo bảo đảm của engine. Khi kiểm chứng, history phải bao gồm **transaction begin/read/write/commit outcome** và những reads quan sát hậu quả.

## 15. DynamoDB: history với ConditionExpression

DynamoDB hỗ trợ conditional write trên một item. Ví dụ item:

~~~json
{
  "PK": "COUNTER#visits:shop-12",
  "value": 5,
  "version": 9
}
~~~

Một mutation có điều kiện bằng Python/boto3:

~~~python
import boto3
from botocore.exceptions import ClientError

table = boto3.resource("dynamodb").Table("CounterLab")
expected_version = 9
new_value = 6

try:
    result = table.update_item(
        Key={"PK": "COUNTER#visits:shop-12"},
        UpdateExpression="SET #value = :new, #ver = #ver + :one",
        ConditionExpression="#ver = :expected",
        ExpressionAttributeNames={
            "#value": "value",
            "#ver": "version",
        },
        ExpressionAttributeValues={
            ":new": new_value,
            ":one": 1,
            ":expected": expected_version,
        },
        ReturnValues="ALL_NEW",
    )
    print("APPLIED", result["Attributes"])
except ClientError as exc:
    if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
        print("CONFLICT")
    else:
        raise
~~~

Ở ví dụ này, mỗi client phải tính `new_value` từ `value` đã đọc cùng `expected_version`. Client B đọc v9 rồi gửi sau A sẽ nhận **ConditionalCheckFailedException**, thay vì ghi đè thành 6.

### 15.1. Đọc eventual consistent và CAS

Nếu B đọc một trạng thái stale, CAS có điều kiện vẫn kiểm tra tại nguồn phục vụ mutation theo bảo đảm của DynamoDB; B bị conflict thay vì ghi dựa trên version cũ. Nhưng một test đang kiểm tra **read-after-write** phải cấu hình mức nhất quán của read phù hợp:

- Có phân biệt table/LSI với GSI không?
- Request có sử dụng strong read ở nơi được hỗ trợ không?
- Có global tables/cross-region replication không?
- Timestamps và outcome có thuộc cùng một region/nguồn authority không?

Không kết luận “DynamoDB sai” khi đọc từ một index eventual-consistent theo hợp đồng cho phép độ trễ.

### 15.2. Multi-item invariant

Nếu cần thay cả Inventory và Reservation, dùng transaction như `TransactWriteItems` trong phạm vi được hỗ trợ, hoặc workflow. History phải ghi **transaction-level outcome** thay vì coi hai `UpdateItem` độc lập là một commit.

## 16. Cassandra: kiểm chứng CAS/LWT trên partition

Cassandra/CQL hỗ trợ conditional mutation qua **lightweight transactions (LWT)** trong phạm vi và phiên bản engine phù hợp.

~~~sql
CREATE TABLE counter_by_id (
    counter_id text PRIMARY KEY,
    value int,
    version bigint
);
~~~

Khởi tạo một lần trong môi trường bài lab:

~~~sql
INSERT INTO counter_by_id (counter_id, value, version)
VALUES ('visits:shop-12', 5, 9)
IF NOT EXISTS;
~~~

Đọc:

~~~sql
SELECT value, version
FROM counter_by_id
WHERE counter_id = 'visits:shop-12';
~~~

Conditional update:

~~~sql
UPDATE counter_by_id
SET value = 6,
    version = 10
WHERE counter_id = 'visits:shop-12'
IF version = 9 AND value = 5;
~~~

Trong CQL, kết quả điều kiện thường có trường `[applied]`:

~~~text
Request A: [applied] = true
Request B: [applied] = false (đã có thay đổi)
~~~

Nếu B vẫn muốn tăng một lần, nó **đọc lại** rồi tính `value=7, version=11` và gửi CAS tương ứng. Không xem LWT thất bại là một lần increment đã áp.

### 16.1. LWT không chỉ là lệnh UPDATE thông thường

Cơ chế conditional write liên quan tới quá trình phối hợp/đồng thuận theo phạm vi Cassandra hỗ trợ, thường có latency cao hơn ghi không điều kiện. Khi test phải ghi:

- Consistency level và serial consistency đang dùng.
- Giá trị/phiên bản đọc trước mutation.
- Kết quả `[applied]`, timeout và retry.
- Tỷ lệ contention khi nhiều client cùng một partition.
- Có writer khác dùng UPDATE không điều kiện phá vỡ quy tắc version hay không.

Không suy rằng một `BATCH` thường hoặc counter column CQL tự cung cấp mọi bảo đảm giống LWT, hay LWT một partition bảo vệ mọi invariant giữa nhiều partition.

### 16.2. Đừng nhầm status CAS với số hàng đọc

`[applied] = false` nghĩa là **điều kiện CAS không đạt** theo operation, không phải toàn bộ query đều sai hay thất bại hạ tầng. Nếu timeout, cần ghi **unknown outcome**, không ép thành `[applied] = false`.

## 17. Redis: một key có thể nguyên tử, nhưng GET/SET tách rời thì không

Với Redis:

~~~text
GET counter
  -> 5
SET counter 6
~~~

hai client có thể cùng đọc 5 rồi SET 6. Các lệnh riêng lẻ có thể được server xử lý tuần tự, nhưng **chuỗi hai lệnh của ứng dụng không nguyên tử**.

### 17.1. Atomic INCR

~~~text
SET visits:shop-12 5
INCR visits:shop-12
INCR visits:shop-12
GET visits:shop-12
~~~

Trong một thí nghiệm không có writer khác và không có retry trùng:

~~~text
Lần INCR thành công thứ nhất -> 6
Lần INCR thành công thứ hai -> 7
GET -> 7
~~~

Đây là cách biểu đạt intent “cộng một” ở nơi dữ liệu được cập nhật. Tuy nhiên, persistence/failover và khả năng một request bị gửi lại **không đồng nghĩa** chỉ với atomicity của một lệnh; nếu yêu cầu có durability/idempotency mạnh hơn, phải xét cấu hình và thiết kế đầy đủ.

### 17.2. WATCH/MULTI/EXEC

Nếu cần tính từ trạng thái đã đọc:

~~~text
WATCH visits:shop-12
GET visits:shop-12      -> 5
MULTI
SET visits:shop-12 6
EXEC
~~~

Nếu key đã đổi sau WATCH trước EXEC, Redis có thể hủy transaction theo cơ chế WATCH. Log cần ghi **EXEC có được áp hay không**, không chỉ ghi “lệnh SET đã được queue”.

Một script Lua có thể đọc, kiểm tra và cập nhật key trong một lần xử lý, tránh bị lệnh khác chen vào. Nhưng script không tự phối hợp transaction với MongoDB hoặc external API, và không có rollback tự động cho mọi mutation đã xảy ra trước một lỗi runtime.

### 17.3. Key expiration cũng là thay đổi trạng thái

Nếu key hết TTL giữa lúc client WATCH rồi EXEC, điều đó có thể ảnh hưởng kết quả WATCH/transaction theo cách Redis xử lý thay đổi key. Một thí nghiệm CAS trên Redis nên ghi rõ:

- TTL/expiration có đang bật không?
- Key có thể bị eviction không?
- Có failover hoặc replica read không?
- Tác động của một script có được ghi lại sau lỗi không?

Nếu thiếu những thông tin ấy, history có thể có “writer vô hình” từ cơ chế expire hoặc service nền.

## 18. Sử dụng một bảng trạng thái để dựng lịch

Ngoài log operation, nên có bảng **trạng thái nguồn sau mỗi mutation được xác nhận** khi môi trường lab cho phép.

Ví dụ history H2:

| Seq logic | Operation | Before | Condition | Applied? | After |
| ---: | --- | --- | --- | --- | --- |
| 0 | Khởi tạo | — | — | — | value=5, v9 |
| 1 | A CAS | value=5,v9 | expected v9 | Yes | value=6,v10 |
| 2 | B CAS cũ | value=6,v10 | expected v9 | No | value=6,v10 |
| 3 | B CAS mới | value=6,v10 | expected v10 | Yes | value=7,v11 |
| 4 | R read | value=7,v11 | — | Read | value=7,v11 |

Bảng này là cách rất trực quan để chứng minh rằng:

- Không có **double apply** từ attempt CAS thất bại.
- Mỗi lần increment thành công tạo đúng một delta.
- B dùng version mới sau conflict.
- Read xác minh sau cùng thấy trạng thái được mong đợi.

Nhưng cột `Seq logic` phải đến từ **bằng chứng đáng tin** (chẳng hạn thứ tự commit có thể kiểm chứng trong lab hoặc một thứ tự tuyến tính hóa hợp lệ được dựng có chủ đích), không tự suy ra bằng cách sort log từ các node lệch đồng hồ.

## 19. Dùng Python kiểm tra history nhỏ theo đặc tả tuần tự

Một chương trình đơn giản có thể thử các thứ tự tuyến tính hóa cho một **bộ đếm với operation đã hoàn tất**. Đây là ví dụ học thuật để hiểu khái niệm, **không phải checker production**.

Ta định nghĩa:

- `inc()` tăng 1 và trả **giá trị mới**.
- `read()` trả giá trị hiện tại.
- Ban đầu counter bằng 5.
- Mỗi operation có `start`, `end` theo **cùng một trục thời gian đáng tin**.
- Nếu `end(A) <= start(B)`, A bắt buộc đứng trước B.
- Nếu overlap, có thể thử cả hai thứ tự miễn giữ những ràng buộc khác.

~~~python
from functools import lru_cache


def is_linearizable(history, initial_value):
    """
    Chỉ dành cho history nhỏ, đã hoàn tất.
    kind: "inc" trả giá trị SAU tăng; "read" trả giá trị hiện tại.
    start/end: mốc trên một trục thời gian chung, đơn vị bất kỳ.
    """
    n = len(history)
    full_mask = (1 << n) - 1

    # predecessors[i] chứa các operation phải đứng trước i.
    predecessors = []
    for i, op in enumerate(history):
        mask = 0
        for j, other in enumerate(history):
            if i != j and other["end"] <= op["start"]:
                mask |= 1 << j
        predecessors.append(mask)

    @lru_cache(maxsize=None)
    def search(completed_mask, current_value):
        if completed_mask == full_mask:
            return True

        for i, op in enumerate(history):
            bit = 1 << i
            if completed_mask & bit:
                continue
            if predecessors[i] & completed_mask != predecessors[i]:
                continue

            if op["kind"] == "inc":
                next_value = current_value + 1
                if op["result"] != next_value:
                    continue
            elif op["kind"] == "read":
                next_value = current_value
                if op["result"] != current_value:
                    continue
            else:
                raise ValueError("unsupported kind")

            if search(completed_mask | bit, next_value):
                return True

        return False

    return search(0, initial_value)


bad = [
    {"id": "A", "kind": "inc",  "start": 0,  "end": 7,  "result": 6},
    {"id": "B", "kind": "inc",  "start": 2,  "end": 9,  "result": 6},
    {"id": "R", "kind": "read", "start": 10, "end": 11, "result": 6},
]

good = [
    {"id": "A", "kind": "inc",  "start": 0,  "end": 7,  "result": 6},
    {"id": "B", "kind": "inc",  "start": 2,  "end": 9,  "result": 7},
    {"id": "R", "kind": "read", "start": 10, "end": 11, "result": 7},
]

print(is_linearizable(bad, initial_value=5))   # False
print(is_linearizable(good, initial_value=5))  # True
~~~

### 19.1. Cách checker hoạt động

Chương trình:

1. Tạo quan hệ **phải đứng trước** từ các khoảng thời gian.
2. Lần lượt chọn một operation chưa đặt mà các predecessor của nó đã được đặt.
3. Kiểm tra kết quả operation có phù hợp với bộ đếm ở trạng thái hiện tại không.
4. Nếu có một thứ tự hợp lệ cho tất cả operation, trả `True`.
5. Nếu mọi thứ tự đều sai, trả `False`.

Với `bad`, hai lần increment cùng trả 6 nên không có thứ tự tuần tự hợp lệ. Với `good`, có thể đặt A trước B rồi R và thu được 6, 7, 7.

### 19.2. Giới hạn rất quan trọng

Đoạn mã trên **không**:

- Xử lý operation pending/timeout chưa có phản hồi.
- Xử lý failed CAS hoặc operation có kết quả không xác định.
- Mô hình transaction nhiều key, nested operation hay external side effects.
- Kiểm tra tính đúng của đồng hồ khác máy.
- Mô phỏng replica lag, partition hoặc crash/recovery.
- Chứng minh hệ thống đúng cho mọi lịch tương lai.
- Mở rộng tốt khi history lớn: có thể phải thử rất nhiều permutation.

Một checker nghiêm túc cần mô hình đặc tả đúng, cách xử lý incomplete operations, lỗi, transaction và giới hạn thời gian; có thể kết hợp model-based testing, property-based testing hoặc công cụ phân tích history được thiết kế riêng. **Không chạy script này để kết luận về production nếu chưa thỏa các giả định.**

## 20. Tái hiện lịch lost update bằng barrier trong Java

Để quan sát race condition thay vì chờ nó xuất hiện ngẫu nhiên, có thể **ép hai thread đều đọc trước khi thread nào ghi**.

Ví dụ Java chỉ mô phỏng một register **trong bộ nhớ**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class ControlledLostUpdate {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger shared = new AtomicInteger(5);
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrites = new CountDownLatch(1);

        Runnable unsafeIncrement = () -> {
            int snapshot = shared.get();
            System.out.println(
                Thread.currentThread().getName()
                    + " read " + snapshot
            );
            bothRead.countDown();
            try {
                allowWrites.await();
                shared.set(snapshot + 1);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(unsafeIncrement, "A");
        Thread b = new Thread(unsafeIncrement, "B");
        a.start();
        b.start();

        bothRead.await();
        allowWrites.countDown();
        a.join();
        b.join();

        System.out.println("final = " + shared.get());
        // final = 6 dù có hai ý định tăng.
    }
}
~~~

`AtomicInteger` có các thao tác `get` và `set` thread-safe, nhưng `get` và `set(snapshot+1)` **không phải cùng một atomic increment**.

Đổi thành:

~~~java
int result = shared.incrementAndGet();
~~~

thì mỗi thao tác tăng trên `AtomicInteger` trong một JVM được áp atomically theo primitive tương ứng.

**Không nhầm `AtomicInteger` với tính nguyên tử khi nhiều service/process cập nhật database**. Lock/counter nằm trong một JVM không bảo vệ các writer ở những máy khác. Khi cần so NoSQL thật, phải dùng atomic mutation hoặc CAS của engine.

### 20.1. Barrier không chứng minh mọi interleaving

Barrier giúp **tái hiện một lịch cụ thể** có tính giải thích. Nó không thay thế test ngẫu nhiên, test tải, fault injection và phân tích tất cả đường lỗi. Mỗi test nên lưu history đủ thông tin để biết vì sao đúng/sai, không chỉ in giá trị cuối.

## 21. Kiểm thử end-to-end với NoSQL: quy trình thực nghiệm

Một bài lab có thể chọn **một database thật**, tạo key duy nhất cho test và chạy nhiều client độc lập.

### 21.1. Giai đoạn chuẩn bị

~~~text
Test run ID: lab-274-2026-11-14-a
Counter key: visits:lab-274-a
Initial value: 5
Initial version: 9
Logical operations: A.inc(+1), B.inc(+1), R.read()
Expected result if both inc succeed: 7
~~~

Quy định:

- Không có background writer trên key.
- Hai request có ID riêng.
- Ghi cả invocation/response ở client và các mutation được xác nhận ở source.
- Chỉ dùng nguồn có thẩm quyền và consistency phù hợp để xác minh cuối.
- Với read–modify–write, có hook/barrier để ép cả hai đọc version 9 trước khi ghi.

### 21.2. Chạy phiên bản sai

~~~text
1. Set value=5, version=9.
2. A và B đồng thời đọc.
3. Barrier bảo đảm A/B đều có snapshot=5/v9.
4. Cả hai gọi unconditional SET(value=6,version=10).
5. Thu response từng client và đọc lại từ source.
6. Dựng bảng thời gian/giá trị.
~~~

Nếu cả hai được xác nhận tăng và cuối vẫn là 6, đã có **lịch gây lost update ở cấp API increment**.

### 21.3. Chạy phiên bản có điều kiện

~~~text
1. Reset nguồn: value=5, version=9.
2. A/B đều đọc 5/v9.
3. A CAS expected v9 -> 6/v10, thành công.
4. B CAS expected v9 -> bị từ chối.
5. B đọc 6/v10 và CAS -> 7/v11, thành công.
6. R đọc và xác minh 7/v11.
7. So history với thứ tự tuần tự hợp lệ.
~~~

Nếu vì lịch chạy thật mà B thắng CAS trước A, đó **không phải lỗi**; cần dựng witness tương ứng B rồi A. Quan trọng là hai intent độc lập đều được áp một lần, không bị mất hoặc đúp.

### 21.4. Ghi những gì sau mỗi lần chạy

Một bảng kết quả:

| Run | Cơ chế | A response | B response | Final | Kết luận trong phạm vi test |
| --- | --- | --- | --- | ---: | --- |
| L1 | Read + unconditional SET | SUCCESS(6) | SUCCESS(6) | 6 | Vi phạm đặc tả hai increment |
| L2 | CAS + bounded retry | SUCCESS(6) | SUCCESS(7) | 7 | Phù hợp lịch tuần tự A→B |
| L3 | Atomic increment, không retry trùng | SUCCESS(6) | SUCCESS(7) | 7 | Phù hợp hai increment |
| L4 | Atomic increment nhưng retry cùng intent mù | Một timeout/unknown | Một success | Cần đối soát | Không đủ bằng chứng nếu thiếu requestId |

Đây là bảng **minh họa kết quả có thể có**, không phải log thực đã chạy. Trong bài lab, cần điền kết quả đo và lý do nếu khác mẫu.

## 22. Kiểm chứng nguồn, replica và projection

Một hệ thống có thể có:

~~~text
Primary / leader / quorum
   | 
   +--> Read replica
   +--> Redis cache
   +--> Search index
   +--> Analytics read model
~~~

Một read sau write có thể nhìn thấy các version khác nhau:

| Hệ được đọc | Giá trị quan sát | Diễn giải có thể |
| --- | --- | --- |
| Source có thẩm quyền | value=7, v11 | Hai increment đã áp |
| Replica trễ | value=6, v10 | Chưa bắt kịp v11 |
| Redis cache | value=5 | Chưa invalidate/refresh |
| Read model | value=7 nhưng summary chưa cập nhật | Projection nhiều field có độ trễ khác nhau |

**Đừng trộn những giá trị này thành một history của một register linearizable** nếu thực tế đang quan sát các hệ/phạm vi consistency khác nhau.

### 22.1. Read-after-write contract

Nếu ứng dụng cam kết người dùng **ngay sau khi cập nhật sẽ thấy bản mới**, cần:

- Trả giá trị/version mới từ kết quả mutation.
- Hoặc đọc từ nguồn/quorum với consistency phù hợp.
- Hoặc dùng causal context/session token nếu engine hỗ trợ.
- Hoặc đợi projection bắt kịp một `sourceVersion` cụ thể.

Nếu sản phẩm chấp nhận UI hiển thị chậm vài giây, vẫn phải ghi rõ **freshness SLO**, không gọi đó là linearizable read.

### 22.2. Failover và cùng một logical key

Khi leader chuyển vai, một test cần ghi:

- Operation nào đã được acknowledged theo write concern/consistency đã chọn?
- Replica mới có những commit nào?
- Client có retry sau khi đổi leader không?
- Read và write có cùng generation/epoch/partition mapping không?

Không đánh đồng “server A báo OK” với “mọi node đã durable/linearizable” nếu cấu hình không bảo đảm điều ấy.

## 23. Kiểm chứng event đến sai thứ tự và replay

Nguồn Order:

~~~text
v5 = PAID
v6 = READY_TO_SHIP
v7 = SHIPPED
~~~

Pipeline nhận:

| Thời điểm consumer | Event | Điều kiện nếu projector sai | Kết quả |
| --- | --- | --- | --- |
| 09:06:00.005 | v7 | Ghi status SHIPPED | SHIPPED |
| 09:06:00.011 | v6 | Ghi status READY vô điều kiện | READY (sai, đi lùi) |

Một projector đúng cần dùng **sourceVersion** hoặc thứ tự sự kiện có thẩm quyền:

~~~text
if event.version <= lastAppliedSourceVersion:
    ignore
else:
    apply update atomically with progress, or use a recoverable strategy
~~~

### 23.1. Sparse read model có rủi ro đặc biệt

Nếu read model chỉ chứa Order READY, event v7 có thể **xóa row**. Khi row bị xóa, marker `lastAppliedSourceVersion=7` cũng có thể biến mất. Event v6 đến muộn sẽ **tạo lại row READY** nếu không còn watermark.

Cần deletion/version ledger độc lập, hoặc cách lưu progress/tombstone đủ bền. History kiểm chứng phải chứa **các event áp dụng**, trạng thái projection sau từng event và trạng thái cuối từ nguồn.

### 23.2. Progress phải gắn với mutation

Nếu worker:

~~~text
1. Cập nhật summary/read model.
2. Cập nhật checkpoint event.
~~~

rồi chết giữa hai bước, retry có thể áp lại delta. Đảo thứ tự cũng có lỗi bỏ qua mutation. Cần transaction khi thích hợp hoặc thiết kế idempotent/reconciliation. **Version trên event không tự làm hai lần ghi khác nơi thành một transaction.**

## 24. Phân tích lỗi lịch thực thi bằng quan hệ nhân quả

Một kỹ thuật thực tế là tạo một **đồ thị phụ thuộc**:

- Cạnh từ operation A đến B nếu **A hoàn tất trước B bắt đầu**.
- Cạnh từ read đến write **dùng giá trị read đó**.
- Cạnh source event đến consumer mutation.
- Cạnh từ commit đến acknowledgement tương ứng.
- Cạnh version từ `vN` đến `vN+1` khi nguồn có quy tắc version tin cậy.

~~~mermaid
flowchart LR
    A["A read value=5 / v9"] --> C["A CAS -> v10 success"]
    B["B read value=5 / v9"] --> D["B CAS v9 conflict"]
    C --> D
    D --> E["B read value=6 / v10"]
    E --> F["B CAS -> v11 success"]
    F --> G["Final read value=7 / v11"]
~~~

Đồ thị giúp nhìn rõ **dữ liệu nào là căn cứ của quyết định**. Nếu một cạnh không có log chứng minh, hãy ghi “chưa xác định” thay vì tự tạo thứ tự chỉ vì timestamp được sort.

### 24.1. Ghi cả chứng cứ phản bác

Một báo cáo tốt không chỉ trình bày timeline phù hợp giả thuyết. Nó phải ghi:

- Request nào thiếu response?
- Có background writer/TTL/eviction nào không?
- Có read từ replica khác không?
- Clock skew có thể khiến hai timestamp đảo thứ tự không?
- Có event/commit log nào mâu thuẫn với timeline dự kiến?

Nếu dữ liệu không đủ, kết luận nên là **INCONCLUSIVE**, không phải “pass” hoặc “fail” dựa vào suy đoán.

## 25. Lưu ý khi chạy test nhiều client

### 25.1. Barrier tạo điều kiện tranh chấp, không tạo transaction

Barrier ở client giúp ép interleaving của **lần đọc** nhưng không thay đổi nguyên tắc atomicity của database. Phải tránh cấu hình test khiến một worker chết trước barrier làm mọi worker treo; đặt timeout, cleanup tài nguyên và log lỗi.

### 25.2. Đọc một kết quả cuối có thể bỏ sót sai lệch

Ví dụ stock ban đầu = 1. Hai đơn được xác nhận, cuối stock = 0. Nếu chỉ kiểm tra stock không âm sẽ bỏ qua **oversell**. Cần thêm:

~~~text
successfulUniqueReservations <= initialStock
~~~

và xác minh mỗi reservation gắn với một requestId độc lập, không phải retry của cùng ý định.

### 25.3. Test duplicate khác test concurrent

| Test | Mục tiêu |
| --- | --- |
| A và B là hai request ID khác nhau | Bảo vệ các ý định đồng thời độc lập |
| Một request ID được gửi 2 lần | Kiểm tra idempotency |
| Một request timeout sau commit | Kiểm tra unknown outcome |
| Client đọc từ replica trễ | Kiểm tra CAS khi snapshot stale |
| Node đổi leader trong lúc commit | Kiểm tra ack/retry/durability |
| Event v7 đến trước v6 | Kiểm tra version gating |
| Snapshot phục hồi từ trước v7 | Kiểm tra replay/reconciliation |

Chạy tất cả như “100 request đồng thời” sẽ không phân biệt được lỗi cơ chế nào.

## 26. Một mẫu báo cáo điều tra lịch thực thi

~~~yaml
experimentId: concurrent-history-274-a
dataModel:
  object: counter
  key: visits:shop-12
  initialValue: 5
  initialVersion: 9
sequentialSpecification:
  method: incrementAndGet(+1)
  returns: newValue
  expectedForTwoIndependentSuccesses: 7
historySource:
  clientClock: monotonic-per-process
  wallClock: UTC-with-measured-uncertainty
  authoritativeCommitOrder: "nếu có, ghi nguồn thực"
  readConsistency: "ghi mode thực"
  writeConsistency: "ghi mode thực"
operations:
  - id: A
    kind: incrementAndGet
    invokedAt: "2026-11-14T09:00:00.000Z"
    completedAt: "2026-11-14T09:00:00.023Z"
    observedValue: 5
    returnedValue: 6
    outcome: SUCCESS
  - id: B
    kind: incrementAndGet
    invokedAt: "2026-11-14T09:00:00.003Z"
    completedAt: "2026-11-14T09:00:00.030Z"
    observedValue: 5
    returnedValue: 6
    outcome: SUCCESS
verification:
  readInvokedAt: "2026-11-14T09:00:00.040Z"
  readReturnedAt: "2026-11-14T09:00:00.050Z"
  finalValue: 6
  source: authoritative-counter-read
assessment:
  modeledObject: logical-increment-counter
  conclusion: NON_LINEARIZABLE_FOR_INCREMENT_SPEC
  reason: both increments reported success but only one delta appears
limitations:
  - all events are a controlled illustrative history
  - no other writers assumed
~~~

Đây là **báo cáo minh họa**, không phải kết quả đo thật. Khi dùng thực tế cần bổ sung evidence link, raw trace/sanitized logs, phiên bản engine, topology, client/driver, phạm vi thời gian và clock uncertainty.

### 26.1. Các mức kết luận phù hợp

| Kết luận | Khi nào nên dùng |
| --- | --- |
| **PASS for observed history** | Có một thứ tự hợp lệ, dữ liệu/outcome đủ theo mô hình đã chốt |
| **VIOLATION** | Không tồn tại thứ tự hợp lệ trong giả định chứng cứ |
| **INCONCLUSIVE** | Thiếu response, clock không đủ tin cậy, không có snapshot/nguồn authority |
| **EXPECTED EVENTUAL STALENESS** | Read trễ phù hợp hợp đồng consistency yếu được công bố |
| **BUSINESS INVARIANT VIOLATION** | Ví dụ oversell/write skew dù từng item mutation nguyên tử |

Không dùng “PASS” của một history làm bằng chứng mọi lịch đều an toàn. Không dùng “VIOLATION” của hợp đồng tuyến tính hóa để cáo buộc một hệ chỉ hứa eventual consistency đã vi phạm chính lời hứa của nó.

## 27. Các lỗi phân tích thường gặp

| Lỗi | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Sort mọi dòng log theo timestamp rồi coi là commit order | Các node có clock skew/log buffering | Ghi uncertainty, causal IDs và commit order có thẩm quyền |
| Đồng nhất invoke time với linearization point | Operation overlap có thể đổi thứ tự hiệu lực | Xét toàn khoảng invocation–response |
| Chỉ log request started/finished | Không biết read value, condition, mutation outcome | Thu inputs/outputs/version |
| Thấy final value đúng nên khẳng định đúng | Có thể có update sai rồi bù/trừ khác | Kiểm tra toàn history và invariant |
| Thấy final value sai rồi đổ lỗi DB | RMW phía ứng dụng có thể là nguyên nhân | Phân biệt GET/SET thô với API increment |
| Đếm attempt thành số logical operation | Retry bị tính thành hai ý định | Phân biệt requestId và attemptId |
| Timeout được ghi là write failed | Commit có thể đã xảy ra | Ghi UNKNOWN và xác minh |
| Đọc từ replica stale để xác nhận commit | Có thể chưa bắt kịp source | Chọn consistency và authority đúng |
| Xem CAS failed là một update thành công | Điều kiện không áp mutation | Chỉ đếm mutation applied |
| Kiểm tra stock >= 0 là đủ | Hai đơn có thể thành công khi chỉ còn một hàng | Đếm reservation độc lập được xác nhận |
| So version nhưng một writer không tăng version | OCC không phát hiện mọi thay đổi | Chuẩn hóa mọi đường ghi |
| Dùng CAS từng doctor để bảo vệ số người trực | Bất biến trên hai row, write skew | Transaction/isolation/invariant authority |
| Chỉ đọc trạng thái cuối của nhiều key riêng lẻ | Không cùng snapshot logic | Snapshot/checkpoint/transaction phù hợp |
| Test một lần với dữ liệu ít | Không gặp interleaving/timeout | Barrier, nhiều seed, fault injection |
| Checker chỉ mô hình completed ops nhưng kết luận cả timeout | Pending op có thể đã commit | Mô hình incomplete operations |
| Hai history khác consistency bị so như nhau | Khác hợp đồng đọc/ghi | Ghi rõ mode của từng operation |
| Bỏ qua source generation sau delete/recreate | Version cũ có thể khớp entity mới | Dùng generation/tombstone |

## 28. Bài tập vận dụng

### Bài 1 — Khôi phục lost update từ dữ liệu

Ban đầu `counter=5`. Hai request `INC(+1)` cùng trả thành công và giá trị `6`; read sau khi cả hai hoàn tất trả `6`.

1. Hãy liệt kê hai thứ tự tuần tự có thể có của A và B.
2. Với mỗi thứ tự, viết giá trị sau từng increment.
3. Vì sao không thứ tự nào cho hai response cùng bằng 6?
4. Nếu các thao tác DB là GET/SET riêng, database có nhất thiết vi phạm linearizability của register không?

### Bài 2 — Xem xét hai write chồng lấn

Ban đầu `x=0`:

~~~text
W1 write(1): invoke=0, response=30
W2 write(2): invoke=10, response=20
R read:      invoke=40, response=50, result=1
~~~

Lịch có thể linearize không? Nếu có, hãy đưa ra một witness. Nếu đổi W2 thành `invoke=31,response=35` thì read=1 có còn hợp lệ không, với giả định không có write khác?

### Bài 3 — Read stale và hợp đồng consistency

~~~text
W write(1): invoke=0, response=10
R read():   invoke=20, response=30, result=0
~~~

Ban đầu `x=0`, không có writer khác. Hãy phân biệt kết luận khi:

- R là linearizable read của cùng register.
- R đọc từ replica eventual consistent.
- W chỉ nhận một ack chưa chứng minh durability theo hợp đồng đang kiểm tra.

### Bài 4 — CAS với version

Ban đầu `value=5, version=9`. A/B cùng đọc v9. A CAS thành công, B thất bại.

1. B phải đọc lại dữ liệu gì?
2. B gửi giá trị/expectedVersion nào để tăng hợp lệ lần thứ hai?
3. Nếu B retry dùng version 9 vô hạn, điều gì xảy ra?
4. Nếu B nhận timeout thay vì conflict, có được phép kết luận B chưa ghi không?

### Bài 5 — Dựng write skew

Doctor A và B đều đang trực. Hai transaction cùng đọc (ON,ON), TA tắt A và TB tắt B, cả hai commit.

1. Viết lịch với ít nhất 8 sự kiện có mốc thời gian.
2. Thử tuần tự hóa TA trước TB rồi ngược lại.
3. Vì sao invariant “ít nhất một bác sĩ trực” bị vi phạm?
4. Đề xuất một thiết kế tạo xung đột chung cho hai transaction.

### Bài 6 — Clock skew

Node A nhanh 200 ms, node B chậm 150 ms. A gửi một message ở UTC thật 09:00:00.100 và B nhận ở 09:00:00.150.

1. A và B sẽ ghi timestamp log gì?
2. Nếu sort theo timestamp, thứ tự bị hiểu sai thế nào?
3. Message ID hoặc causal edge giúp chứng minh quan hệ nào?
4. `System.nanoTime()` trên hai JVM có thể so trực tiếp được không?

### Bài 7 — Operation timeout và retry

Stock ban đầu 5, `requestId=R42` trừ 1. Database áp từ 5→4 nhưng response mất; client retry và hệ thống trừ tiếp 4→3.

- Số ý định nghiệp vụ là bao nhiêu? Số attempt là bao nhiêu?
- Vì sao atomic decrement không bảo vệ idempotency?
- Thiết kế ledger có `requestId` và `payloadHash`.
- Làm sao xử lý crash giữa stock mutation và ghi ledger?

### Bài 8 — Thử checker Python

Dùng hàm `is_linearizable` ở mục 19:

1. Xác minh history `bad` và `good`.
2. Đổi thời gian để R bắt đầu **trước khi B hoàn tất**; cách tìm witness thay đổi thế nào?
3. Thử thêm một read trả giá trị 6 giữa hai lần increment.
4. Giải thích vì sao checker chưa xử lý được một request tăng bị timeout.

### Bài 9 — Thực nghiệm MongoDB hoặc DynamoDB

Thiết kế một lab với:

- Initial counter = 5, version = 9.
- Hai writer đọc trước khi ghi nhờ barrier.
- Lượt 1 dùng unconditional SET.
- Lượt 2 dùng CAS/ConditionExpression.
- Ghi `operationId`, `expectedVersion`, `modifiedCount`/condition result và timestamp.
- Đọc source sau khi toàn bộ operation hoàn tất.

Nêu bằng chứng tối thiểu để kết luận lượt 1 mất cập nhật nhưng lượt 2 có một lịch tuần tự hợp lệ.

### Bài 10 — Event sai thứ tự ở read model

Nguồn Order có v6 READY và v7 SHIPPED. Consumer áp v7 rồi mới v6.

1. Mô tả kết quả nếu consumer ghi status vô điều kiện.
2. Thiết kế `lastAppliedSourceVersion` để bỏ event cũ.
3. Với read model chỉ chứa Order READY, tại sao xóa row v7 có thể làm mất watermark?
4. Khi replay snapshot cũ, làm sao tránh tạo lại Order đã SHIPPED?

### Bài 11 — Kiểm tra số reservation thay vì stock cuối

Inventory ban đầu bằng 1. Lịch có hai API `reserve(1)` báo SUCCESS, cuối stock bằng 0.

- Bất biến nào bị vi phạm?
- Nếu một SUCCESS chỉ là duplicate response của cùng `requestId`, cách tính ý định khác gì?
- Những log nào cần có để biết một hay hai reservation độc lập đã được chấp nhận?
- Tại sao một CAS trên stock không tự ghi Reservation atomically nếu nó ở database khác?

### Bài 12 — Thiết kế báo cáo điều tra

Từ một hệ có 3 service và 2 replica, hãy tạo mẫu báo cáo gồm:

1. Hợp đồng nghiệp vụ/consistency.
2. Nguồn authority và identity/generation.
3. Mốc invoke/response, đồng hồ và uncertainty.
4. Operation ID, request ID và attempt ID.
5. Read value/version, write condition, mutation outcome.
6. Snapshot/read xác minh cùng phạm vi.
7. Một witness tuần tự nếu có hoặc một chu trình/bất biến vi phạm nếu không.
8. Kết luận PASS, VIOLATION hoặc INCONCLUSIVE kèm giới hạn chứng cứ.

## 29. Tóm tắt quy trình giải một lịch thực thi

~~~mermaid
flowchart TD
    A["Thu thập operation và dữ liệu nguồn"] --> B["Chốt sequential spec / business invariant"]
    B --> C["Ghép requestId, attemptId, version"]
    C --> D["Xác định thứ tự thực chứng và overlap"]
    D --> E["Dựng giá trị trước/sau mutation"]
    E --> F{"Có dữ liệu đủ để kiểm chứng?"}
    F -->|Không| G["INCONCLUSIVE, bổ sung trace/snapshot"]
    F -->|Có| H["Thử thứ tự tuần tự hợp lệ"]
    H --> I{"Có witness thỏa spec + real-time?"}
    I -->|Có| J["PASS cho history đã quan sát"]
    I -->|Không| K["VIOLATION theo mô hình đã chốt"]
    J --> L["Kiểm tra thêm retry, crash, tải, replica"]
    K --> M["Xác định root cause và sửa ranh giới nguyên tử"]
~~~

Một quy trình thực tế:

1. **Nêu đặc tả:** `INC` phải cộng đúng một, `reserve` không oversell, hoặc các transaction phải giữ invariant.
2. **Chọn object và ranh giới:** một key, nhiều item, một transaction hay workflow liên dịch vụ?
3. **Thu history đầy đủ:** invocation, response, read value, proposed write, condition, version, retry, lỗi.
4. **Xác định thứ tự được chứng minh:** real-time khi đáng tin, causal events, commit/version order có thẩm quyền.
5. **Tìm một tuần tự hóa:** tôn trọng các operation không overlap và kết quả của sequential spec.
6. **Đối chiếu dữ liệu cuối:** đọc đúng nguồn/consistency, tránh kết luận từ replica stale.
7. **Xử lý những chỗ không biết:** timeout, pending operation, clock uncertainty phải được ghi là giới hạn.
8. **Kiểm thử cơ chế sửa:** CAS, atomic conditional write, transaction, idempotency, event version-gating.
9. **Không dừng ở một lần chạy:** thử nhiều interleaving, fault injection và khối lượng đồng thời phù hợp.

## Kết luận

**Kiểm chứng một lịch thực thi đồng thời không phải chỉ sort log theo thời gian và nhìn giá trị cuối.** Cần mô tả operation được hứa với người dùng, những giá trị đã đọc, điều kiện đã ghi, kết quả được xác nhận và quan hệ xảy ra trước dựa trên bằng chứng đáng tin.

Những điểm cần nhớ:

- **Hai request overlap không bắt buộc linearize theo thứ tự chúng bắt đầu hoặc kết thúc.** Quan hệ response-before-invocation mới tạo ràng buộc thứ tự thực rõ ràng.
- **Lost update ở cấp API không nhất thiết là lỗi nguyên tử của GET/SET riêng lẻ.** Lỗi có thể nằm ở chuỗi read–modify–write tại ứng dụng.
- **Atomic increment và CAS giải quyết những dạng cạnh tranh khác nhau.** CAS thất bại không được tính thành một mutation thành công.
- **Dữ liệu cụ thể giúp kiểm chứng:** ban đầu 5, hai lần tăng thành công thì phải là 7; CAS v9→v10→v11 giải thích được kết quả 7.
- **Linearizability khác serializability.** Một key có thể an toàn nhưng invariant giữa hai record vẫn bị write skew.
- **Clock skew, replica lag và unknown commit outcome có thể đánh lừa timeline.** Dùng ID, version, causal edges, consistency mode và ghi mức bất định khi cần.
- **Retry có thể nhân đôi tác động dù mỗi mutation nguyên tử.** Phân biệt logical request và attempt, thiết kế idempotency/reconciliation.
- **Một history PASS chỉ xác nhận history đó theo mô hình đã chốt.** Muốn đánh giá hệ thống, cần nhiều phép thử đồng thời, lỗi mạng, failover và giám sát production.

Một hệ NoSQL được thiết kế tốt không chỉ có những lệnh update đúng cú pháp, mà có khả năng **giải thích và kiểm chứng từng kết quả cập nhật bằng một lịch thực thi nhất quán với dữ liệu, phiên bản, thời điểm và bất biến nghiệp vụ**.
