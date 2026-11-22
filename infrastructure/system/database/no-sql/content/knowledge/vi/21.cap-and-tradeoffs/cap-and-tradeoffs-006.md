# Phạm vi một thao tác và các điều kiện để phát biểu bảo đảm

## 1. Mở đầu: “Database này nhất quán” là một câu chưa đủ nghĩa

Khi thiết kế hệ thống NoSQL phân tán, chúng ta thường nghe những phát biểu:

- “MongoDB có transaction nên hệ thống nhất quán.”
- “Cassandra dùng QUORUM nên đọc lúc nào cũng mới nhất.”
- “DynamoDB hỗ trợ strongly consistent read.”
- “Redis chạy lệnh atomic.”
- “Hệ thống của tôi là CP.”
- “Hệ thống của tôi là AP và luôn sẵn sàng.”
- “Write được xác nhận rồi thì dữ liệu không thể mất.”
- “Hệ thống hỗ trợ eventual consistency nên mọi lỗi đọc cũ đều chấp nhận được.”

Những câu trên dễ gây hiểu nhầm vì **bỏ qua phạm vi và điều kiện của bảo đảm**.

Một lời cam kết đáng tin phải trả lời ít nhất:

1. **Thao tác nào?** Đọc một key, ghi một document, cập nhật có điều kiện, transaction, truy vấn index, batch job hay cả workflow thanh toán?
2. **Đối tượng nào?** Một item, một partition, một collection, một shard, nhiều bảng hay nhiều dịch vụ?
3. **Client nào?** Một phiên, mọi client trong region, hay client ở tất cả region?
4. **Thứ tự thời gian nào?** Sau write ACK, sau commit, tại snapshot, hay khi replication hoàn tất?
5. **Cơ chế nào?** Read/write concern, consistency level, transaction isolation, CAS, session token hay leader routing?
6. **Lỗi nào?** Replica chậm, process crash, mất node, network partition, mất availability zone hay mất cả region?
7. **Giả định nào?** Số replica còn sống, quorum, đồng hồ, topology, storage durability và giới hạn thời gian?
8. **Hành vi khi không thể đáp ứng?** Chờ, từ chối, timeout, trả dữ liệu cũ, chuyển hướng hay xử lý bất đồng bộ?

Bài học này nằm trong chương **CAP và các đánh đổi** của Database NoSQL. Trọng tâm không phải xếp hạng công nghệ thành “CP hay AP” bằng một nhãn cố định, mà là **xác định ranh giới của một thao tác và các giả định cần nêu trước khi hứa hẹn consistency, availability hoặc durability**.

### 1.1. Ví dụ xuyên suốt

Giả sử một nền tảng đặt vé có:

~~~text
Event: concert-42
Capacity: 100 ghế

Client A: giữ 1 ghế
Client B: giữ 1 ghế
Client C: xem số ghế còn lại
Payment service: xác nhận thanh toán
Search service: hiển thị ghế còn trống
~~~

Một thao tác cập nhật counter được thực hiện nguyên tử **trên một item** chưa đủ để nói rằng:

- Hai giữ chỗ trên **hai item khác nhau** cùng atomic.
- Payment và database commit **cùng một transaction**.
- Search index trả kết quả ngay sau write.
- Mọi region có cùng số lượng ở cùng một thời điểm.
- Khi mạng chia đôi, cả hai phía đều vừa tiếp tục bán vé vừa không thể oversell.
- Write vừa ACK vẫn được bảo vệ khi mất toàn region.

**Mỗi phát biểu phải được thu hẹp đến đúng đường dữ liệu và loại sự cố mà nó thực sự bao phủ.**

### 1.2. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt **operation**, **request**, **transaction**, **session** và **business workflow**.
- Giải thích nhất quán của CAP được hiểu theo **linearizability** trong mô hình lý thuyết và tại sao nó khác chữ “consistency” trong ACID.
- Phát biểu đúng đánh đổi consistency–availability khi mạng phân vùng.
- Phân biệt tính sẵn sàng theo CAP với uptime/SLA và một response lỗi HTTP.
- Chỉ ra các điều kiện của atomic single-item write, conditional update, multi-item transaction và session guarantees.
- Nhận diện những đường đọc có semantics khác nhau: primary, secondary, GSI, cache, materialized view và multi-region replica.
- Áp dụng cách đặt câu hỏi này cho MongoDB, DynamoDB, Cassandra, Redis và Azure Cosmos DB.
- Viết một **consistency contract** có thể kiểm thử, gồm failure model, phạm vi và hành vi timeout.
- Phân tích tình huống timeout, retry, quorum, failover và dữ liệu bên ngoài DB.
- Tránh suy diễn từ một bảo đảm hẹp thành cam kết quá mức cho toàn ứng dụng.

---

## 2. “Một thao tác” có thể có những ranh giới rất khác nhau

Một từ như “ghi đơn hàng” có thể đại diện cho nhiều bước, nhưng DBMS không nhất thiết coi tất cả là **một thao tác nguyên tử**.

### 2.1. Các phạm vi thường gặp

| Phạm vi | Ví dụ | Câu hỏi về bảo đảm |
|---|---|---|
| **Một key/item** | `PutItem(order-9001)` | Ghi có atomic trên đúng item này không? |
| **Một document** | Đổi `inventory.available` | Điều kiện và cập nhật có được xét cùng lúc không? |
| **Một partition** | Update nhiều row trong partition | Hệ đảm bảo thứ tự/atomicity tới đâu? |
| **Một collection/table** | Query tất cả đơn `PAID` | Có snapshot đồng nhất của toàn tập không? |
| **Nhiều item** | Giữ stock và tạo reservation | Cả hai có commit hoặc rollback cùng nhau không? |
| **Nhiều partition** | Giảm quota ở hai shard | Transaction có bao phủ cả hai không? |
| **Một session** | Ghi rồi đọc lại ở replica | Có read-your-writes không? |
| **Nhiều session/client** | Hai người cùng mua vé cuối | Có ngăn write conflict và overselling không? |
| **Nhiều region** | Ghi tại A, đọc tại B | Replication có đồng bộ trước ACK không? |
| **Nhiều dịch vụ** | Database + payment + event bus | Có cơ chế phối hợp và idempotency không? |
| **Một báo cáo/export** | Đọc 10 triệu order | Các page thuộc một snapshot hay nhiều mốc? |

Từ “operation” nên được gắn với **API cụ thể hoặc đơn vị giao dịch mà hệ bảo đảm**. Không thể dùng “một HTTP request” làm đơn vị mặc định, vì một request có thể gọi nhiều database, queue và dịch vụ ngoài.

### 2.2. Minh họa phạm vi

~~~mermaid
flowchart TD
    A["POST /checkout"] --> B["Đọc giỏ hàng"]
    A --> C["Giữ tồn kho"]
    A --> D["Tạo Order"]
    A --> E["Gọi Payment"]
    A --> F["Gửi OrderCreated"]
    C --> G["Atomic update trên item Inventory"]
    D --> H["Insert document Order"]
    F --> I["Message broker"]
    E --> J["Hệ thanh toán"]
~~~

Trong sơ đồ, **atomic update trên Inventory** không tự tạo atomicity cho toàn bộ `POST /checkout`. Nếu `Payment` thành công nhưng `Order` thất bại, ứng dụng cần một workflow phục hồi hoặc bù trừ riêng.

### 2.3. Một response “success” có thể đến từ nhiều tầng

~~~text
HTTP 200 từ API
  != database transaction commit
  != write đã được mọi replica nhận
  != journal đã fsync
  != search index đã cập nhật
  != email/event đã gửi
  != toàn workflow được hoàn tất
~~~

Mỗi bước có hợp đồng xác nhận riêng. Một thiết kế cẩn thận sẽ đặt tên trạng thái, ví dụ `ORDER_CREATED`, `PAYMENT_PENDING`, `PAID`, `FULFILLMENT_ACCEPTED`, thay vì dùng một trạng thái `SUCCESS` mơ hồ cho nhiều hành động không nguyên tử.

---

## 3. Xác định điểm bắt đầu và kết thúc của một thao tác

Khi đánh giá consistency, nên biểu diễn thao tác theo **lịch sử invocation/response**.

Giả sử một key `x` ban đầu có giá trị 0:

~~~text
T0: Client A bắt đầu W(x=1).
T1: Server nhận write.
T2: Server xác nhận commit.
T3: Client A nhận ACK.
T4: Client B bắt đầu R(x).
T5: Client B nhận kết quả.
~~~

Đối với những mô hình nhất quán mạnh như **linearizability**, quan hệ thứ tự thời gian thực giữa các thao tác **không chồng lấn** rất quan trọng.

Nếu write đã hoàn tất ở T3 và read bắt đầu ở T4, read sau đó phải phù hợp với một lịch sử tuần tự có write trước read, trừ khi có write hợp lệ khác xen vào hoặc phạm vi/semantics khác được nêu rõ.

### 3.1. Thao tác chồng lấn

~~~text
Client A: W(x=1)  [T0 ........ T4]
Client B: R(x)       [T2 ... T3]
~~~

Read bắt đầu khi write đang chạy. Trong linearizability, read có thể quan sát trước hoặc sau write, miễn tìm được một điểm tuyến tính hóa hợp lệ cho từng operation nằm trong khoảng invocation–response và lịch sử tuân thủ đặc tả đối tượng.

Không nên kết luận rằng mọi read concurrent với write **bắt buộc** trả giá trị mới.

### 3.2. Timeout không xác định kết quả commit

~~~text
Client gửi write
Database commit
Response bị mất
Client timeout
~~~

Write có thể đã xảy ra dù client không nhận ACK. Vì vậy phải phân biệt:

- `ACKNOWLEDGED`: đáp ứng điều kiện xác nhận của tầng đang xét.
- `REJECTED/NOT_APPLIED`: có bằng chứng thao tác không được áp dụng.
- `UNKNOWN`: chưa thể kết luận đã commit hay chưa.
- `PARTIALLY_COMPLETED`: workflow nhiều bước mới hoàn thành một phần, nếu hợp đồng nghiệp vụ có trạng thái này.

Không dùng một network timeout như bằng chứng chắc chắn database đã rollback.

### 3.3. Mốc thời gian nguồn của kết quả

Một API có thể trả “dữ liệu tại snapshot T” hoặc “dữ liệu mới nhất của primary”. Hai phát biểu này khác nhau:

- Snapshot cho phép đọc một trạng thái đồng nhất tại mốc xác định trong phạm vi hỗ trợ.
- Linearizable read có yêu cầu mạnh hơn về **thứ tự thời gian thực** của các operation theo đối tượng/phạm vi được cung cấp.
- Eventual read có thể chưa bao gồm write vừa được xác nhận ở nơi khác.

Mốc cần rõ ràng đến **nguồn dữ liệu thực sự được query**, không chỉ thời điểm server HTTP nhận request.

## 4. Nhất quán trong CAP là gì?

Trong cách trình bày CAP phổ biến, chữ **C** nói đến **linearizability/atomic consistency** của những thao tác trên một đối tượng chia sẻ (đặc biệt kiểu đọc/ghi một register) theo mô hình lý thuyết. Đây **không phải** toàn bộ các nghĩa của “consistency” mà lập trình viên gặp.

### 4.1. Linearizability trong ngôn ngữ thực hành

Một lịch sử thao tác trên đối tượng trông như mỗi thao tác có hiệu lực tức thời tại một điểm nào đó giữa lúc được gọi và lúc trả kết quả; thứ tự của các thao tác đã hoàn thành trước khi thao tác khác bắt đầu phải được tôn trọng.

Ví dụ key `x` ban đầu là 0:

~~~text
A: W(x=1) -> ACK
B: R(x)   -> 1
~~~

Nếu B đọc sau khi A hoàn tất và không có write mới, kết quả 1 phù hợp.

~~~text
A: W(x=1) -> ACK
B: R(x)   -> 0
~~~

Nếu những thao tác thuộc cùng register và contract hứa linearizability, lịch sử thứ hai vi phạm.

### 4.2. ACID consistency khác chữ C của CAP

Trong giao dịch ACID, **consistency** thường nói đến việc transaction giữ các bất biến của database và ràng buộc nghiệp vụ, chẳng hạn không trừ stock xuống âm hoặc không tạo hai username trùng.

Một database có thể thực hiện atomic update trên từng document nhưng không cung cấp mọi read linearizable qua tất cả replica. Ngược lại, một key-value store có thể cung cấp linearizable operations trên một key nhưng không tự bảo đảm tổng `available + reserved + sold = capacity` khi ứng dụng cập nhật các key riêng lẻ không cùng transaction.

**Không được dùng chữ “C” ở CAP để thay thế việc phân tích ACID transaction hoặc business invariant.**

### 4.3. Linearizable một key khác serializable nhiều key

| Bảo đảm | Đối tượng quan tâm | Ví dụ |
|---|---|---|
| Atomic single-item update | Một item/document | Điều kiện và trừ counter trong cùng item |
| Linearizable key operations | Một key/register | Read sau write hoàn tất thấy trạng thái mới nhất theo contract |
| Serializable transactions | Nhiều thao tác trong transaction | Lịch sử transaction tương đương một thứ tự tuần tự |
| Strict serializability | Transaction + thứ tự thời gian thực | Transaction đã hoàn tất trước transaction khác phải đi trước |
| Snapshot isolation | Transaction đọc snapshot theo phạm vi | Không mặc nhiên ngăn mọi write skew |
| Causal consistency | Phụ thuộc nhân quả | Bình luận chỉ xuất hiện với các phụ thuộc đã quan sát |
| Session guarantees | Một phiên logic | Read-your-writes, monotonic reads |

Không xem mọi bảo đảm trong bảng là một chuỗi cấp độ có thể thay thế nhau: mỗi bảo đảm có **phạm vi và những bất thường cho phép** khác nhau.

---

## 5. CAP nói điều gì khi mạng bị phân vùng?

CAP mô tả một đánh đổi: trong mô hình hệ thống phân tán có thể gặp **network partition**, không thể vừa bảo đảm **linearizability** vừa đáp ứng tính **availability** theo định nghĩa CAP cho mọi request hợp lệ trên những node không hỏng, ở mọi phía của phân vùng, trong mọi lịch sử được xét.

Nói ngắn hơn: khi các phần của hệ không trao đổi thông tin được, một bên có thể phải **chờ/từ chối một số thao tác** để giữ trạng thái nhất quán, hoặc **tiếp tục phục vụ thao tác** mà chấp nhận trạng thái chưa được điều phối giữa các bên.

### 5.1. Partition nghĩa là gì?

Trong bối cảnh này, **network partition** là sự cố truyền thông khiến những node lẽ ra phối hợp được không thể trao đổi một số message cần thiết trong một khoảng không bị chặn trên bởi giả định của hệ.

Nó khác với:

- **Data partition/sharding:** chia dữ liệu theo khóa để mở rộng.
- **Table partition:** chia bảng thành các nhóm vật lý.
- **Network latency bình thường:** message vẫn đến trong thời gian dự kiến.
- **Process crash:** node thực sự không còn hoạt động.
- **Throttling:** dịch vụ giới hạn tốc độ hoặc capacity.

Các hiện tượng có thể cùng xảy ra, nhưng từ “partition” trong CAP là **mất liên lạc giữa các thành phần cần phối hợp**.

### 5.2. Availability trong CAP được hiểu thế nào?

Trong định nghĩa lý thuyết phổ biến, mỗi request được gửi tới một node **không hỏng** phải cuối cùng nhận được response hợp lệ của thao tác, thay vì bị treo vô thời hạn vì mạng bị chia.

Điểm cần nhớ:

- Đây không phải uptime 99,9% hay tỷ lệ HTTP 200 trên dashboard.
- Trả một lỗi “không thể thực hiện do mất quorum” có thể là **xử lý lỗi tốt về mặt API**, nhưng không đáp ứng availability theo nghĩa **thành công của thao tác hợp lệ** đang xét trong CAP.
- Một timeout hữu hạn giúp tránh chờ vô hạn ở ứng dụng, nhưng không biến một write bị từ chối thành một write khả dụng theo định nghĩa CAP.
- Availability của **read**, **write**, **một key**, **một region** hay **một API** cần được nêu riêng.

### 5.3. Partition tolerance là điều kiện môi trường, không phải nút “bật P”

Một hệ phân tán thực tế phải quyết định sẽ làm gì **khi đường truyền bị chia**. “P” không đơn giản là một tính năng có thể bỏ để lấy “CA” mà vẫn phục vụ đầy đủ ở mọi phía của partition.

Nếu giả định mạng luôn ổn định, ta có thể thiết kế một hệ nhất quán và khả dụng trong điều kiện đó. Nhưng khi mạng thực sự phân vùng, ràng buộc của CAP xuất hiện đối với những thao tác cần phối hợp giữa các phía.

### 5.4. CAP không phát biểu mọi lúc chỉ được chọn một trong C và A

Khi **không có partition**, một hệ có thể vừa cung cấp các thao tác linearizable vừa đáp ứng request với độ sẵn sàng tốt. CAP không nói hệ luôn phải hy sinh consistency hoặc availability vào mọi thời điểm.

Mấu chốt là **khi network partition thực sự xảy ra** và các client có thể truy cập những phía khác nhau, yêu cầu C và A mạnh theo định nghĩa CAP xung đột.

---

## 6. Minh họa đánh đổi CAP trên một key

Giả sử có hai bản sao của cùng key `seat-42`:

~~~text
Trước sự cố:
  Replica A: seat-42 = FREE
  Replica B: seat-42 = FREE

Mạng giữa A và B bị đứt.
Client ở phía A muốn đặt seat-42.
Client ở phía B cũng muốn đặt seat-42.
~~~

### 6.1. Ưu tiên nhất quán mạnh

~~~mermaid
flowchart LR
    CA["Client A"] --> A["Replica A"]
    CB["Client B"] --> B["Replica B"]
    A -. "Network partition" .- B
    A --> OK["Có thể phục vụ nếu giữ được quyền commit"]
    B --> NO["Phải chờ/từ chối khi không thể xác định quyền"]
~~~

Nếu giao thức bầu leader/quorum xác định chỉ một phía có quyền commit, phía còn lại không thể đồng thời xác nhận đặt **cùng ghế** mà vẫn giữ một lịch sử tuyến tính hóa an toàn.

Kết quả có thể là:

~~~text
Client A: reservation succeeded
Client B: unavailable / timeout / retry later
~~~

Đây là sự đánh đổi **availability của thao tác đặt vé** để bảo vệ single-seat invariant.

### 6.2. Ưu tiên phục vụ tại cả hai phía

Nếu A và B độc lập trả thành công:

~~~text
Client A: "Bạn đã đặt seat-42"
Client B: "Bạn đã đặt seat-42"
~~~

Hệ phải giải quyết hai xác nhận mâu thuẫn sau khi mạng hồi phục. Có thể cần conflict resolution, compensation hoặc thông báo hủy một đặt chỗ.

Nếu business contract đã hứa **mỗi ghế được xác nhận tối đa một lần**, hai ACK độc lập trên hai phía không thể cùng thỏa hợp đồng đó trong mô hình đã nêu.

### 6.3. Không phải mọi thao tác đều cần phối hợp

Hai client ghi vào **hai key độc lập**, ví dụ:

~~~text
A: update profile:user-1
B: update profile:user-2
~~~

có thể không cần phối hợp với nhau để giữ tính đúng đắn **nếu** mỗi key có thẩm quyền phục vụ phù hợp. Do đó không nên suy từ “cluster bị chia” thành “mọi thao tác phải thất bại”.

Phạm vi của thao tác là yếu tố quyết định: hai thao tác độc lập thường dễ phục vụ hơn hai thao tác cùng thay đổi **một tài nguyên hữu hạn**.

### 6.4. Escrow và quyền cấp phát trước

Một hệ phân chia sẵn quota có thể:

~~~text
Tổng 100 vé
Partition A được cấp quyền bán 40
Partition B được cấp quyền bán 60
~~~

Trong partition, mỗi bên có thể tiếp tục bán **trong ngân sách đã được giao**, không cần giao tiếp tức thời; tổng không vượt 100.

Đây không phải phép màu “vượt CAP”, mà là **thay đổi đối tượng và quyền được cấp phát trước**. Khi muốn chuyển thêm quota giữa A/B, hệ lại cần một giao thức phối hợp an toàn.

---

## 7. Điều kiện để viết một phát biểu bảo đảm có thể kiểm chứng

Một phát biểu tốt có cấu trúc:

> **Đối với thao tác O**, trên **phạm vi S**, khi client dùng **API/cấu hình M**, trong **topology T** và dưới **mô hình sự cố F**, nếu **tiền điều kiện P** được thỏa và thao tác nhận **kết quả R**, hệ bảo đảm **thuộc tính G**; khi không thể đáp ứng sẽ **chờ/từ chối/timeout** theo chính sách H.

Ví dụ:

> Với cập nhật có điều kiện trên **một item Inventory**, ứng dụng chỉ giảm `available` nếu giá trị hiện tại đủ lớn theo thao tác atomic của DBMS. Điều này bảo vệ counter của **item đó** khỏi âm dưới các write cạnh tranh; nó **không bảo đảm** việc tạo reservation ở bảng khác cùng atomic nếu không dùng transaction hoặc giao thức thích hợp.

Ví dụ khác:

> Sau write đã được xác nhận ở **base table DynamoDB** trong vùng và phạm vi mà API hỗ trợ, một **strongly consistent GetItem** theo đúng khóa có thể được dùng để đọc trạng thái cập nhật; điều đó **không mở rộng** sang một query trên GSI eventual hoặc mọi replica đa vùng.

### 7.1. Mẫu tài liệu bảo đảm

~~~yaml
guarantee:
  name: "Inventory conditional allocation"
  operation: "Reserve(resourceId, quantity)"
  scope: "One authoritative Inventory item"
  preconditions:
    - "quantity > 0"
    - "resource exists"
    - "available >= quantity"
  mechanism: "Atomic conditional update"
  success_condition: "Database acknowledged requested write policy"
  property:
    - "available cannot be decremented below zero by this operation"
  exclusions:
    - "Reservation record in another item is not included"
    - "Search index visibility is not included"
    - "Cross-region failover durability requires separate analysis"
  on_unavailable: "Return retryable failure or unknown outcome; do not fabricate allocation"
~~~

Mẫu này là **tài liệu kỹ thuật minh họa**, không phải schema cấu hình của một DBMS.

### 7.2. Bảy câu hỏi để phản biện

1. **Ai là nguồn sự thật?** Primary, một quorum, một bảng nguồn hay read model?
2. **Thao tác nào chính xác?** `GetItem`, `Query`, `Scan`, update, transaction?
3. **Ranh giới atomicity?** Một item hay nhiều item/partition?
4. **Điều kiện thành công?** ACK từ ai, commit gì, sync tới đâu?
5. **Đường đọc nào?** Base table, secondary, cache, GSI, region khác?
6. **Mạng hoặc node lỗi thì sao?** Thao tác chờ, từ chối hay cho phép dữ liệu cũ?
7. **Làm sao kiểm tra?** Event history, version, transaction ID, error rate, failover tests?

Nếu không trả lời được, chưa nên hứa một bảo đảm mạnh ở cấp ứng dụng.

---

## 8. Tính nhất quán của từng kiểu thao tác khác nhau

Cùng một DBMS có thể cung cấp nhiều mức nhất quán tùy API.

### 8.1. Point lookup

~~~text
GET user:42
~~~

Đọc theo một khóa có thể hưởng cơ chế mạnh hơn hoặc khác với query rộng. Ví dụ dịch vụ có thể hỗ trợ strong read trên base item nhưng không hỗ trợ tương đương ở secondary index.

### 8.2. Range query

~~~text
Liệt kê 100 Order mới nhất trong tenant
~~~

Muốn phát biểu “100 record mới nhất”, cần hiểu:

- Read lấy dữ liệu ở snapshot nào?
- Có index/sort phù hợp không?
- Một query chạm bao nhiêu partition/shard?
- Dữ liệu mới được thêm khi query chạy có xuất hiện không?
- Khi phân trang, các page có chung snapshot hay không?

Atomicity của từng item **không tự biến một range query thành một snapshot toàn tập**.

### 8.3. Aggregate

~~~text
SELECT COUNT(*) trên toàn bộ trạng thái PENDING
~~~

Một truy vấn count có thể đọc các partition ở những mốc khác nhau nếu không có snapshot phù hợp. Vì thế số trả về có thể không biểu diễn một thời điểm duy nhất, dù từng item được ghi atomically.

### 8.4. Conditional update

~~~text
if available >= q:
    available -= q
~~~

Một thao tác kiểm tra và sửa **trong cùng atomic unit** có thể bảo vệ invariant trên item đó. Hai thao tác rời `read available` rồi `write` không tương đương.

### 8.5. Multi-item transaction

~~~text
Giảm Inventory
Tạo Reservation
Ghi OutboxEvent
~~~

Nếu cả ba nằm trong phạm vi transaction được hỗ trợ, có thể yêu cầu commit/rollback cùng nhau. Nhưng transaction có thể có các mức isolation khác nhau; atomicity không tự đồng nghĩa serializability hoặc strict serializability.

### 8.6. Side effect bên ngoài DB

~~~text
DB commit Order
Payment provider charge
Message broker publish
Email send
~~~

Đây là nhiều hệ với các mốc ACK khác nhau. Muốn “cả workflow exactly once” cần giao thức bổ sung, idempotency, outbox/saga và reconciliation. Không được gán bảo đảm transaction của DB cho payment hay email.

---

## 9. Phân biệt consistency, atomicity, isolation và durability

Để viết đúng phạm vi, cần tránh trộn những thuộc tính thuộc các trục khác nhau.

| Thuộc tính | Câu hỏi | Công cụ thiết kế thường gặp |
|---|---|---|
| Atomicity | Thay đổi cùng xảy ra hay cùng không? | Transaction/atomic item operation |
| Isolation | Transaction concurrent nhìn nhau thế nào? | Isolation level, serialization, CAS |
| Linearizability | Operation tôn trọng thứ tự thời gian thực thế nào? | Leader/quorum/consensus theo scope |
| Causal consistency | Phụ thuộc nhân quả có được giữ không? | Causal metadata/session token |
| Read-your-writes | Chính phiên có thấy write của mình? | Session/primary read/watermark |
| Durability | Write đã ACK còn sau sự cố nào? | WAL, sync, replication, backup |
| Availability | Request hợp lệ tiếp tục được phục vụ khi gì hỏng? | Topology, quorum, failover policy |

### 9.1. Ví dụ: atomic nhưng không read-your-writes qua GSI

Một item được update atomically trong bảng nguồn. Query ngay trên một global secondary index có thể chưa thấy nó. **Atomic update ở nguồn và eventual index visibility không mâu thuẫn** vì hai bảo đảm có phạm vi khác nhau.

### 9.2. Ví dụ: RYW nhưng vẫn oversell

Hai client mỗi bên có read-your-writes, nhưng cả hai cùng đọc `available=1` rồi ghi `available=0` bằng những thao tác không được kiểm tra nguyên tử. Mỗi người có thể đọc lại thấy `available=0`, nhưng có **hai reservation cho một ghế**.

RYW không thay thế conditional allocation.

### 9.3. Ví dụ: linearizable một key nhưng workflow không atomic

Một key `stock:sku42` có thao tác decrement linearizable. Sau khi giảm stock, service crash trước khi ghi `reservation:res9`. Counter đã giảm, nhưng không có reservation để xử lý expiry.

Phần thiếu là **transaction/protocol giữa hai key**, không phải linearizability của thao tác decrement đơn lẻ.

### 9.4. Ví dụ: durable nhưng stale

Write đã được majority committed và journal synced theo contract, nhưng một secondary replica chưa áp dụng bản mới. Read từ secondary ấy trả stale. Đây là vấn đề **read consistency**, không nhất thiết là mất durability.

---

## 10. Quorum: công thức giao nhau không phải giấy bảo đảm mọi thứ

Trong một số mô hình replicated storage có replication factor \(N\), người ta dùng:

- \(W\): số replica xác nhận write.
- \(R\): số replica tham gia read.
- \(N\): số bản sao có trách nhiệm lưu dữ liệu.

Điều kiện:

\[
R+W>N
\]

giúp tập đọc và tập ghi có ít nhất một replica **giao nhau về mặt số lượng**.

Ví dụ:

\[
N=3,\quad W=2,\quad R=2,\quad R+W=4>3.
\]

### 10.1. Vì sao giao nhau chưa đủ?

Để dùng giao nhau làm cơ sở cho bảo đảm cụ thể, còn phải xét:

- Các replica đọc/ghi có đúng **cùng tập membership và phiên bản topology** không?
- Replica đã ACK write ở **mức nào**: memory, journal, durable commit?
- Read coordinator xử lý dữ liệu từ nhiều replica ra sao?
- Các write concurrent được giải quyết bằng thứ tự/version nào?
- Có read repair, conflict resolution hoặc timestamp không?
- Client đang đọc trong cùng datacenter/region không?
- Quorum có được tính theo từng DC hay toàn cụm?
- Trong failover, replica mới có bảo toàn các write đã committed không?

**`R+W>N` là điều kiện giao nhau, không phải phép chứng minh linearizability hay transaction isolation cho mọi hệ.**

### 10.2. Quorum không làm mọi replica đồng bộ ngay

Nếu \(W=2\), replica thứ ba có thể chưa nhận write. Một read chỉ chạm replica ấy hoặc query qua read model khác vẫn có thể cũ nếu contract cho phép.

### 10.3. Quorum có thể mất availability ở một phía partition

Với cụm ba node bị tách 2–1, phía có một node không thể đạt quorum hai. Nếu mọi write cần quorum, phía đó phải chờ/từ chối write, dù node vẫn chạy bình thường.

Đây là trade-off dự kiến khi bảo vệ một commit history nhất quán, không tự động là bug.

### 10.4. Quorum read có chi phí

Chờ nhiều replica có thể làm tăng:

- Network traffic.
- Tail latency.
- Ảnh hưởng của replica chậm.
- CPU và work trên coordinator.
- Timeout khi thiếu replica.

Không nên chỉ chọn mức quorum vì “mạnh hơn”, mà phải biết **operation nào cần nó** và SLO tương ứng.

---

## 11. Availability theo CAP khác SLA dịch vụ

Một đội vận hành có thể tuyên bố “99,99% uptime” theo số request thành công trong tháng. Điều đó hữu ích, nhưng không phải một mệnh đề trực tiếp về **availability trong định lý CAP**.

### 11.1. Hai cách đo

**Availability vận hành** thường đo:

~~~text
successfulRequests / totalRequests
~~~

trong khoảng thời gian, loại request, khu vực và định nghĩa lỗi đã chọn.

**CAP availability** là thuộc tính lý thuyết rằng request hợp lệ gửi tới node không hỏng cuối cùng phải có response thành công của thao tác, kể cả dưới các network partition được xét.

### 11.2. Trả HTTP 503 có “available” không?

Từ góc độ kỹ thuật API, HTTP 503 có thể là hành vi đúng: fail fast thay vì trả dữ liệu sai. Nhưng nếu một thao tác hợp lệ liên tục bị từ chối chỉ vì thiếu quorum, hệ không đáp ứng **availability mạnh theo CAP** cho thao tác đó trong partition.

Không nên gộp:

- Liveness của server process.
- Response time bounded.
- Thành công của nghiệp vụ.
- CAP availability.
- SLA uptime.

### 11.3. Read availability khác write availability

Một node có thể tiếp tục phục vụ **stale reads** trong lúc từ chối **writes**:

~~~text
GET profile -> 200 (version cũ, có nhãn freshness)
PUT profile -> 503 (thiếu quorum)
~~~

Nói “dịch vụ còn hoạt động” không đủ; cần chỉ ra **đọc hay ghi, mạnh hay yếu, phạm vi nào**.

### 11.4. Availability không phải thứ được đo bằng một lỗi riêng lẻ

Một hệ có thể đạt SLA rất cao trong điều kiện bình thường nhưng vẫn chủ động từ chối write trong partition. Hai câu không mâu thuẫn vì chúng đánh giá những tính chất khác nhau.

---

## 12. “CP” và “AP” là nhãn rút gọn, không phải đặc tính bất biến của sản phẩm

Trong tài liệu phổ thông, “CP” thường gợi ý **ưu tiên giữ consistency mạnh khi partition**, chấp nhận không phục vụ một số request. “AP” thường gợi ý **tiếp tục phục vụ request trong partition**, chấp nhận những kiểu trạng thái phân kỳ/đọc cũ nhất định.

Nhưng một sản phẩm NoSQL hiện đại có thể hỗ trợ:

- Nhiều consistency level theo request.
- Primary/secondary reads.
- Conditional writes trên item.
- Transaction nhiều item.
- Secondary index eventual.
- Global replication bất đồng bộ.
- Session tokens.
- Region/partition-specific behavior.

Do đó, một nhãn đơn **không mô tả được mọi thao tác của cùng sản phẩm**.

### 12.1. Cách viết không tốt

> “Cassandra là AP, vậy mọi write đều thành công khi partition.”

Điều này bỏ qua consistency level, số replica, topology, trạng thái node và phạm vi operation. Một write cần `QUORUM` vẫn có thể thất bại nếu không đủ replica liên lạc được.

### 12.2. Cách viết tốt hơn

> “Với RF=3 và write consistency level ONE trong datacenter được chỉ định, một request có thể được xác nhận sau phản hồi của một replica phù hợp. Với CL=QUORUM, coordinator cần đủ số replica phản hồi theo semantics của Cassandra; khi thiếu, request có thể timeout hoặc trả lỗi. Các phát biểu về visibility/durability/failover cần được kiểm tra riêng.”

### 12.3. Cùng một application có thể chọn khác nhau theo nghiệp vụ

~~~text
Product feed:
  Cho phép stale read trong một khoảng để tăng availability.

Payment ledger:
  Ưu tiên commit/transaction mạnh.
  Khi thiếu quorum, từ chối xử lý thay vì tự xác nhận thanh toán.

Search:
  Eventual index, có freshness SLO.

Session/profile:
  Read-your-writes theo phiên nếu sản phẩm yêu cầu.
~~~

Đây là **lựa chọn trên từng đường truy cập**, không phải tuyên bố toàn bộ hệ thống “là CP/AP” trong mọi trường hợp.

---

## 13. Phạm vi consistency qua một document/item

Nhiều hệ NoSQL cung cấp thao tác nguyên tử mạnh trên **một item hoặc document**.

Ví dụ inventory:

~~~json
{
  "_id": "sku-42",
  "capacity": 100,
  "available": 1,
  "held": 99
}
~~~

Hai request cùng giữ một đơn vị:

~~~text
A: reserve(sku-42, 1)
B: reserve(sku-42, 1)
~~~

Một conditional update:

~~~javascript
db.inventory.updateOne(
  {
    _id: "sku-42",
    available: { $gte: 1 }
  },
  {
    $inc: {
      available: -1,
      held: 1
    }
  }
);
~~~

Trong MongoDB, match điều kiện và update trên **cùng document** là một thao tác nguyên tử theo semantics sản phẩm. Hai request không thể cùng giảm từ `available=1` xuống giá trị hợp lệ nếu cả hai yêu cầu điều kiện tương ứng và dữ liệu được cập nhật đúng.

### 13.1. Phát biểu đúng

> Với một document Inventory tồn tại và lượng yêu cầu hợp lệ, thao tác `updateOne` có filter `available >= qty` chỉ thay đổi document khi đủ số lượng, vì điều kiện và cập nhật trên document đó là nguyên tử. Không kết luận gì về record Reservation khác nếu nó không nằm trong cùng transaction.

### 13.2. Phát biểu sai

> “MongoDB atomic nên toàn bộ checkout không bao giờ oversell hoặc mất Order.”

Bảo đảm một document không tự bao trùm Order, payment, message broker, search index, rollback và failover.

### 13.3. Nhiều document cần thêm câu hỏi

Khi ứng dụng cần:

~~~text
Inventory.available -= 1
Reservations.insert(res-9001)
Outbox.insert(event-9001)
~~~

hãy hỏi:

- Có transaction chung không?
- Transaction có phạm vi collection/shard nào?
- Isolation level và conflict behavior thế nào?
- Commit được ACK ở mức write concern nào?
- Nếu commit outcome unknown, retry xử lý ra sao?
- Ngoài DB, event broker nhận message lúc nào?

---

## 14. Transaction: ba điều kiện không nên bỏ qua

Một transaction giúp gom nhiều thao tác, nhưng không nên chỉ nói “có transaction là đủ”.

### 14.1. Phạm vi atomicity

Xác định rõ những item/bảng nào được transaction bao phủ. Ví dụ một DBMS hỗ trợ transaction chỉ trong một bảng, một partition hoặc một vùng; không được coi mọi item/region/service đều thuộc cùng một transaction.

### 14.2. Isolation

Hai transaction cùng chạy có thể quan sát dữ liệu theo snapshot hoặc mức cô lập khác nhau. **Atomic commit** không tự ngăn mọi write skew hoặc lost update nếu ứng dụng dùng isolation không đủ mạnh cho bất biến.

Ví dụ hai bác sĩ cùng đọc rằng vẫn có bác sĩ khác trực, rồi mỗi người đánh dấu mình nghỉ. Nếu cập nhật vào hai record khác nhau và isolation không bảo vệ predicate/bất biến “luôn có ít nhất một bác sĩ trực”, kết quả có thể vi phạm dù mỗi transaction atomic.

### 14.3. Durability và trạng thái commit

Một transaction commit ACK phải được hiểu theo write concern/replication/journal/managed-service contract. Nếu timeout sau khi server đã commit, client có thể không biết trạng thái cuối.

Không được retry một checkout bằng Order ID mới một cách mù quáng sau commit timeout.

### 14.4. Transaction bên trong DB không bao gồm thanh toán bên ngoài

~~~mermaid
sequenceDiagram
    participant API as Checkout API
    participant DB as Database
    participant PAY as Payment Provider
    participant BUS as Message Broker

    API->>DB: Transaction: Inventory + Order
    DB-->>API: Commit ACK
    API->>PAY: Charge
    PAY-->>API: Payment response
    API->>BUS: Publish OrderPaid
~~~

Đây là ba hệ có ba hợp đồng. Kể cả DB transaction mạnh cũng không tạo atomic all-or-nothing cho toàn flow. Cần idempotency, outbox, compensation/saga và reconciliation nếu nghiệp vụ yêu cầu.

---

## 15. Session guarantees: khi phạm vi là một phiên, không phải mọi người dùng

Các bảo đảm theo phiên thường gồm:

| Bảo đảm | Nội dung |
|---|---|
| Read-your-writes | Sau write thành công, phiên đọc thấy write đó hoặc trạng thái hợp lệ mới hơn |
| Monotonic reads | Phiên không quay lại trạng thái cũ hơn những gì đã đọc |
| Monotonic writes | Các write của phiên được duy trì theo thứ tự |
| Writes-follow-reads | Write mới của phiên tôn trọng những phụ thuộc đã thấy qua read |

### 15.1. Một phiên có thể qua nhiều HTTP request

~~~text
Request 1: UPDATE profile -> ACK, version=12
Request 2: GET profile từ replica chậm -> version=10
~~~

Nếu ứng dụng hứa read-your-writes cho phiên, read version 10 không đáp ứng contract. Hệ cần route, đợi, fallback nguồn hoặc trả lỗi.

### 15.2. Session scope cần chỉ rõ

Một session có thể gắn với:

- Một DB driver session.
- Một tab trình duyệt.
- Một thiết bị.
- Một chuỗi request được gắn token.
- Một user trên nhiều thiết bị nếu app chủ động chia sẻ causal context.

Không mặc định cùng tài khoản nghĩa mọi thiết bị có cùng watermark.

### 15.3. Token không phải chứng nhận durability

Session token có thể mang mốc đã quan sát. Nếu một write vừa được ACK yếu rồi bị rollback trong failover, token không tự làm write đó sống lại.

### 15.4. Session consistency không thay thế invariant

Đọc thấy write của chính mình không ngăn hai client cùng đặt ghế cuối nếu thao tác cấp phát không có conditional atomicity.

---

## 16. Phạm vi của read path quan trọng ngang write path

Một hệ có thể vừa phục vụ read từ:

- Base table / primary.
- Follower / secondary replica.
- Local replica trong datacenter.
- Global secondary index.
- Materialized view.
- Redis cache.
- Search index.
- Data warehouse.
- CDN hoặc application memory.

**Không nên gộp tất cả dưới một câu “database đọc nhất quán”.**

### 16.1. Ghi nguồn, đọc index

~~~text
WRITE Order vào base table: ACK
READ qua GSI: chưa thấy Order
~~~

Nếu GSI eventual, hai kết quả này có thể phù hợp contract. Atomicity của write nguồn không áp lên index visibility.

### 16.2. Ghi nguồn, đọc cache

~~~text
DB source: profile.version = 12
Cache:     profile.version = 10
~~~

Dù DB có strong read, ứng dụng vẫn vi phạm read-your-writes nếu GET trả cache version 10 mà không kiểm tra watermark.

### 16.3. Range query có nhất quán snapshot không?

Giả sử API trả hai page danh sách Order:

~~~text
Page 1: read lúc T1
Page 2: read lúc T2
~~~

Nếu không giữ snapshot/cursor phù hợp, việc thêm/xóa record giữa T1–T2 có thể gây thiếu/trùng dữ liệu. Chỉ có strong point reads không chứng minh một quá trình phân trang dài là một snapshot chung.

### 16.4. Dữ liệu bị xóa vẫn cần version

Một session đã thấy tombstone version 12, sau đó GET từ replica stale trả record version 10. Đó có thể là vi phạm monotonic reads. Cần xác định semantics của delete/tombstone và version theo dữ liệu nguồn, không chỉ so nội dung response.

---

## 17. MongoDB: document atomicity, transaction và linearizable reads

MongoDB có nhiều cơ chế với những phạm vi khác nhau:

- Thao tác ghi trên **một document** có atomicity ở mức document.
- Có thể dùng **multi-document transaction** trong cấu hình/topology hỗ trợ.
- Read concern và write concern quy định những khía cạnh khác nhau của read/write.
- Causal session giúp các bảo đảm theo phiên khi đáp ứng điều kiện của sản phẩm.
- Linearizable read concern có điều kiện, phạm vi và giới hạn riêng.

### 17.1. Conditional update một document

~~~javascript
const qty = 1;

const result = db.inventory.updateOne(
  {
    _id: "sku-42",
    available: { $gte: qty }
  },
  {
    $inc: {
      available: -qty,
      held: qty
    }
  }
);

if (result.modifiedCount !== 1) {
  // Không còn đủ quantity hoặc resource không tồn tại.
}
~~~

**Phạm vi:** một Inventory document. Không kết luận việc ghi sang `reservations` cũng atomic nếu là bước thứ hai ngoài transaction.

### 17.2. Write concern

~~~javascript
db.orders.insertOne(
  {
    _id: "order-9001",
    status: "CREATED"
  },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 5000
    }
  }
);
~~~

Đây là cấu hình yêu cầu mức xác nhận majority/journaling theo MongoDB. Nó liên quan **acknowledgement và durability/replication**, nhưng không tự nói mọi query `find()` qua mọi replica là linearizable.

### 17.3. Read concern linearizable

Đối với những thao tác đọc được hỗ trợ, MongoDB có **read concern `linearizable`**, thường được dùng với đọc từ primary và cần quan tâm điều kiện write concern majority cùng những hạn chế của DBMS.

Ví dụ minh họa dùng `runCommand` cho một document:

~~~javascript
db.runCommand({
  find: "inventory",
  filter: { _id: "sku-42" },
  limit: 1,
  singleBatch: true,
  readConcern: { level: "linearizable" },
  maxTimeMS: 2000
});
~~~

Cần kiểm tra phiên bản MongoDB, read preference, điều kiện/topology hỗ trợ và behavior khi thiếu majority. **Một linearizable read trên một document không tự chuyển tất cả aggregation, index reads hoặc multi-document operations sang strong global consistency.**

### 17.4. Causal session không phải transaction

Nếu sử dụng causally consistent session với các read/write concerns thích hợp, MongoDB có thể hỗ trợ RYW/MR và các bảo đảm nhân quả theo session. Nhưng các write độc lập qua session không tự trở thành transaction atomic.

### 17.5. Những phát biểu nên dùng

Tốt:

> “`updateOne` có điều kiện bảo vệ một document Inventory không bị giảm dưới 0; những tài liệu Reservation khác cần transaction/protocol riêng.”

Tốt:

> “Request đọc `inventory._id` dùng read concern tuyến tính hóa theo phạm vi MongoDB hỗ trợ, với timeout và fallback được định nghĩa; khi không thể đáp ứng, API không giả vờ trả bản mới nhất.”

Không tốt:

> “MongoDB là CP nên mọi endpoint đều linearizable.”

---

## 18. DynamoDB: strong read phụ thuộc kiểu đọc và phạm vi vùng

DynamoDB có các thao tác:

- `GetItem` theo khóa.
- `Query` theo partition/sort key.
- `Scan`.
- `PutItem` / `UpdateItem` với condition.
- Transaction trên nhiều item theo giới hạn của dịch vụ.
- Global Secondary Index (GSI) và Local Secondary Index (LSI).

### 18.1. Strongly consistent read trên đường được hỗ trợ

AWS SDK for JavaScript v3:

~~~javascript
import { GetCommand } from "@aws-sdk/lib-dynamodb";

const response = await documentClient.send(new GetCommand({
  TableName: "Orders",
  Key: { orderId: "order-9001" },
  ConsistentRead: true
}));

console.log(response.Item);
~~~

Đường đọc base table có hỗ trợ `ConsistentRead: true` theo contract DynamoDB. Điều kiện và phạm vi cần được hiểu trong region/table đang truy cập và sau một write đã thành công.

### 18.2. GSI eventual consistency

GSI **không hỗ trợ strongly consistent reads** như base table. Một query GSI ngay sau ghi có thể trả trạng thái cũ.

Vì thế câu:

> “DynamoDB supports strong reads”

phải được diễn đạt lại:

> “Các thao tác đọc từ base table (và các phạm vi index được hỗ trợ) có thể yêu cầu strongly consistent read theo API; GSI chỉ hỗ trợ eventual consistency.”

### 18.3. Conditional write một item

~~~javascript
import { UpdateCommand } from "@aws-sdk/lib-dynamodb";

await documentClient.send(new UpdateCommand({
  TableName: "Inventory",
  Key: { resourceId: "sku-42" },
  UpdateExpression:
    "SET available = available - :q, held = held + :q",
  ConditionExpression:
    "attribute_exists(resourceId) AND available >= :q",
  ExpressionAttributeValues: {
    ":q": 1
  }
}));
~~~

Đây là thao tác **điều kiện trên một item**. Nó bảo vệ invariant của item trước các update tranh chấp trong phạm vi dịch vụ nhưng không bao gồm một reservation ở item/bảng khác.

### 18.4. Transaction cho nhiều item

Muốn cập nhật Inventory và tạo Reservation cùng atomic theo DynamoDB, có thể dùng `TransactWriteItems` trong những giới hạn số item/dung lượng/region được hỗ trợ.

Nhưng transaction vẫn cần:

- Điều kiện xác minh availability.
- Stable request ID.
- Retry khi kết quả unknown.
- Phạm vi tất cả item có liên quan.
- Phân biệt atomicity với eventual GSI update.

### 18.5. Global tables và nhiều region

Một write thành công ở Region A không tự đảm bảo Region B đã có ngay phiên bản đó trong mọi chế độ global replication. Cần phân biệt strong read **trong phạm vi hỗ trợ** với replication đa vùng, conflict resolution và DR contract.

---

## 19. Cassandra: consistency level, partition key và LWT

Cassandra cho phép cấu hình consistency level trên request như `ONE`, `LOCAL_QUORUM`, `QUORUM`, `ALL`, với semantics phụ thuộc RF/topology.

### 19.1. ONE khác QUORUM

Giả sử RF=3. Một write `ONE` có thể được xác nhận khi một replica phù hợp phản hồi; `QUORUM` yêu cầu nhiều phản hồi hơn theo topology.

Khi một node không liên lạc được, một write ở CL thấp có thể vẫn được xử lý trong tình huống CL cao không đạt. Đó là sự đánh đổi **theo request**, không phải một nhãn AP cố định.

### 19.2. Query theo partition key

~~~sql
CREATE TABLE events_by_device_day (
  tenant_id text,
  device_id text,
  event_day date,
  event_at timestamp,
  event_id text,
  value text,
  PRIMARY KEY (
    (tenant_id, device_id, event_day),
    event_at,
    event_id
  )
);
~~~

~~~sql
SELECT event_id, event_at, value
FROM events_by_device_day
WHERE tenant_id = 'tenant-7'
  AND device_id = 'sensor-01'
  AND event_day = '2026-11-14';
~~~

Query xác định một partition key hợp lệ. Điều đó giúp routing, nhưng **không có nghĩa query tự có snapshot transaction qua nhiều row hoặc strong linearizability toàn hệ**.

### 19.3. LWT cho conditional update

~~~sql
CREATE TABLE inventory_by_resource (
  resource_id text PRIMARY KEY,
  available int,
  version bigint
);
~~~

Nếu đã đọc `available=1`, `version=7`, ứng dụng có thể thử:

~~~sql
UPDATE inventory_by_resource
SET available = 0,
    version = 8
WHERE resource_id = 'sku-42'
IF version = 7;
~~~

Lightweight Transaction (LWT)/CAS sử dụng cơ chế đồng thuận trong phạm vi hỗ trợ của Cassandra để giải quyết điều kiện cạnh tranh. Nó có độ trễ và chi phí khác với write thông thường.

Các giả định quan trọng:

- Client chỉ chấp nhận kết quả `applied=true`.
- Nếu CAS thất bại, client đọc lại trước khi tính state mới.
- Nếu timeout, outcome có thể unknown; cần kiểm tra/retry theo protocol.
- Không coi CAS một row là transaction atomic cùng Reservation ở partition khác.
- Quorum CL của thao tác thường không tự tương đương semantics LWT.

### 19.4. Timestamp conflict resolution

Cassandra có quy tắc timestamp/conflict resolution; việc hai request được gửi theo thứ tự client không đủ để suy ra mọi replica luôn áp dụng theo thứ tự đó trong mọi trường hợp.

Với bất biến mạnh, cần xác định cơ chế conditional update và phạm vi của nó; **không chỉ chọn CL=QUORUM rồi bỏ qua xung đột ghi**.

### 19.5. LWT không được mở rộng tùy tiện

Nếu yêu cầu “chỉ cho một người đặt cả 5 ghế thuộc 5 partition” không được bao phủ bởi atomicity của một LWT trên một row. Có thể cần đổi mô hình key, thêm coordinator transactional hoặc thiết kế phân bổ trước với quyền cấp phát rõ.

---

## 20. Redis: nguyên tử trên primary, replication và persistence là ba chuyện khác nhau

Redis có thể thực hiện một số thao tác theo kiểu tuần tự trên primary và hỗ trợ Lua script cho logic kiểm tra/cập nhật trong phạm vi một node.

### 20.1. Lệnh nguyên tử không tự bảo vệ cả workflow

~~~text
DECR available
HSET reservation:9001 state HELD
~~~

Nếu là hai lệnh rời và process crash giữa chúng, counter có thể giảm nhưng reservation chưa được tạo.

Một Lua script có thể gom điều kiện và update nhiều key cùng slot trên Redis node phù hợp, nhưng điều này chỉ giải quyết **atomicity trong phạm vi script**.

### 20.2. Replication bất đồng bộ

Sau primary ACK, replica có thể chưa nhận write. Đọc từ replica có thể stale. Nếu primary mất trong cửa sổ chưa replicate/durable, cần xét nguy cơ mất write sau failover.

### 20.3. Persistence

AOF/RDB và `appendfsync` liên quan độ bền local. Chúng không tự tạo linearizable reads trên tất cả replica.

### 20.4. Lệnh WAIT

`WAIT` có thể chờ số replica nhận write theo semantics Redis. Nhưng nhận write và fsync AOF là hai điều kiện khác nhau; không suy từ `WAIT` thành bảo đảm durability/linearizability mọi replica.

### 20.5. Redis Cluster và hash slot

Một Lua script nhiều key trong Redis Cluster thường yêu cầu các key nằm trong cùng hash slot. Vì vậy atomicity của script không thể được phát biểu như transaction xuyên mọi node/key trong cả cluster.

### 20.6. Phát biểu tốt

> “Với các key cùng hash slot trên node xử lý, script Lua kiểm tra và cập nhật trạng thái như một đơn vị nguyên tử của Redis trong phạm vi hỗ trợ; bảo đảm không mất write sau failover cần đánh giá riêng persistence và replication.”

---

## 21. Azure Cosmos DB: consistency level và session token

Azure Cosmos DB cung cấp nhiều mức consistency được dịch vụ hỗ trợ như Strong, Bounded Staleness, Session, Consistent Prefix và Eventual, với phạm vi/topology/giới hạn theo cấu hình và phiên bản dịch vụ.

### 21.1. Session consistency

Một phiên có thể được hỗ trợ:

- Read-your-writes.
- Monotonic reads.
- Monotonic writes.
- Writes-follow-reads.

SDK có thể quản lý **session token** để những request sau biết mốc phiên đã quan sát.

### 21.2. Session không tự là global strong consistency

Một client khác không mang token tương ứng có thể thấy dữ liệu cũ theo contract của Session consistency. Hai thiết bị của cùng user không mặc định chia sẻ session token.

### 21.3. Khi chuyển region

Một session token có phạm vi và cách sử dụng được định nghĩa bởi dịch vụ. Nếu chuyển request giữa các region, ứng dụng phải tuân thủ cách SDK đảm bảo mốc phiên; không tự giả định mọi replica đã bắt kịp.

### 21.4. Một API service qua nhiều backend

Nếu API backend tạo mới database client/token state cho mỗi HTTP request, phải kiểm tra cách context được giữ xuyên request. Không nên phát biểu “session consistency xuyên mọi request” nếu token hoặc session state bị bỏ mất giữa các API instances.

### 21.5. Tại sao Cosmos cũng cần hợp đồng cụ thể?

Vì tính nhất quán của một item read, query nhiều partition, multi-region write hoặc cache ứng dụng không tự đồng nhất chỉ từ tên consistency level đã chọn. Cần xem **thao tác, scope, SDK context và topology thực tế**.

---

## 22. Multi-region: phải phân biệt local và global

Giả sử hệ có Region A và Region B:

~~~text
Client ở A ghi profile.version=20.
Region A trả ACK.
Region B còn profile.version=18.
Client chuyển sang B và đọc.
~~~

Một tuyên bố:

> “Read-your-writes được bảo đảm trong region A sau write ACK, khi đọc từ đường nguồn phù hợp.”

khác rất nhiều với:

> “Mọi request của mọi thiết bị ở mọi region sẽ luôn thấy version 20 ngay sau ACK.”

### 22.1. Local consistency không tự suy ra global

Nếu replication giữa region là async, region B có thể chưa có write mới. Để đáp ứng RYW xuyên region, ứng dụng có thể:

- Chuyển read về A.
- Chờ B đạt session watermark.
- Sử dụng global consistency mode mạnh hơn nếu dịch vụ hỗ trợ.
- Trả trạng thái chưa sẵn sàng thay vì dữ liệu cũ.

### 22.2. Multi-leader conflict

Nếu cả A và B nhận concurrent write cùng key:

~~~text
A: status = PAID
B: status = CANCELLED
~~~

cần quy tắc conflict resolution và business invariant. Một chiến lược last-write-wins theo timestamp có thể bỏ một write, nhưng điều đó không tự giải quyết tính đúng đắn của payment/reservation.

### 22.3. Cross-region latency

Chờ xác nhận đồng bộ qua region thường có thêm RTT và phụ thuộc network. Một hệ có thể chọn local write availability và eventual replication cho feed, nhưng yêu cầu điều phối mạnh cho thanh toán.

Cần ghi quyết định **theo operation**, không gắn một nhãn duy nhất lên toàn hệ.

### 22.4. DR và CAP khác nhau

CAP nói về khả năng duy trì linearizability và availability khi giao tiếp bị phân vùng. **Disaster recovery** còn liên quan bản sao, backup, durability, mất cả region và thời gian restore.

Không lấy “hệ là CP” làm bằng chứng RPO bằng 0 khi region bị xóa, cũng không lấy “hệ là AP” làm bằng chứng mọi node có backup.

---

## 23. Hợp đồng khi client nhìn thấy timeout hoặc lỗi

Một API nghiêm túc cần phân biệt những trạng thái sau:

| Kết quả | Có thể kết luận? | Hành động |
|---|---|---|
| ACK thành công theo write policy | Thao tác đạt điều kiện xác nhận được hứa | Tiếp tục workflow theo contract |
| Conditional check failed rõ ràng | Điều kiện cấp phát không thỏa | Trả business conflict/out-of-stock |
| Không đủ quorum | Không đáp ứng yêu cầu consistency/availability đã chọn | Thử lại có kiểm soát hoặc báo tạm thời không khả dụng |
| Network timeout | Có thể đã commit hoặc chưa | Giữ ID ổn định, đối soát |
| Read không đạt watermark | Không thể trả bản thỏa session guarantee kịp | Chờ/route/fallback/error |
| GSI/search chưa theo kịp | Read model chưa có version mới | Đọc nguồn hoặc chờ index |
| Transaction commit unknown | Không biết outcome cuối | Xác minh bằng request ID hoặc transaction protocol |

### 23.1. Idempotency khác consistency

Một `Idempotency-Key` giúp nhận diện retry cùng hành động. Nó không tự bảo đảm linearizable read, global transaction hoặc journal sync.

Một session token giúp bảo vệ thứ tự quan sát, nhưng cũng không ngăn cùng một payment bị thu hai lần nếu thiếu idempotency của payment provider.

### 23.2. Ví dụ Java: xử lý outcome có cấu trúc

~~~java
public enum WriteOutcome {
    COMMITTED,
    REJECTED_BY_CONDITION,
    UNKNOWN
}

public record WriteResult(
    WriteOutcome outcome,
    String operationId
) {}
~~~

Pseudocode:

~~~java
WriteResult reserve(
    String operationId,
    String resourceId,
    int quantity
) {
    // 1. Kiểm tra quyền và quantity hợp lệ.
    // 2. Dùng operationId ổn định qua mọi retry.
    // 3. Ghi có điều kiện trong phạm vi atomic được hỗ trợ.
    // 4. Nếu ACK -> COMMITTED.
    // 5. Nếu điều kiện thất bại rõ -> REJECTED_BY_CONDITION.
    // 6. Nếu timeout hoặc commit outcome không rõ:
    //    đọc trạng thái request ở nguồn có consistency phù hợp,
    //    không tự khẳng định chưa ghi.
    // 7. Nếu vẫn không rõ -> UNKNOWN + reconciliation.
    throw new UnsupportedOperationException("Pseudocode");
}
~~~

### 23.3. Retry phải có ngân sách

Trên một phía partition thiếu quorum, retry vô hạn chỉ tạo thêm tải. Sử dụng:

- Deadline tổng.
- Exponential backoff có jitter.
- Circuit breaker theo dependency.
- Stable request ID.
- Phân biệt business reject với transient failure.
- Trạng thái `PENDING/UNKNOWN` khi chưa xác định outcome.

Một API fail fast minh bạch thường tốt hơn **trả “thành công” khi chưa đạt điều kiện nghiệp vụ**.

---

## 24. Viết tài liệu bảo đảm cho một endpoint thật

Ví dụ endpoint:

~~~http
POST /reservations
Idempotency-Key: hold-9001
Content-Type: application/json

{
  "resourceId": "seat-42",
  "quantity": 1
}
~~~

### 24.1. Phát biểu chưa đủ

> “Endpoint này strong consistent và high availability.”

Thiếu:

- Strong consistent ở thao tác nào?
- Khi network partition thì hành vi thế nào?
- Reservation record nằm đâu?
- Điều kiện nhận ACK là gì?
- Nếu payment timeout thì sao?
- GET status đi nguồn nào?

### 24.2. Phát biểu cụ thể hơn

> `POST /reservations` có điểm quyết định cấp phát tại item `Inventory(resourceId)`. Trong một transaction được hỗ trợ của DBMS, hệ chỉ tạo reservation và giảm available nếu còn đủ chỗ. Chỉ trả trạng thái `HELD` sau khi transaction commit được xác nhận theo write policy đã định. Nếu không đạt điều kiện commit trong thời hạn, API trả lỗi/unknown và không xác nhận giữ ghế. Các bản sao hiển thị/search có thể trễ; `GET /reservations/{id}` dùng đường đọc nguồn đáp ứng consistency contract. Payment confirmation ngoài DB có quy trình idempotency riêng.

Câu này vẫn cần bổ sung:

- Tên DBMS và phiên bản.
- Transaction scope và isolation.
- Replication topology.
- Failure model.
- Mức write concern/CL.
- Giới hạn timeout và RPO/RTO.
- Các trường hợp counter/record repair.
- Cách xử lý failover và kết quả commit không rõ.

### 24.3. Một mẫu ADR ngắn

~~~markdown
# ADR: Tính nhất quán của Reserve Seat

## Business invariant
- Mỗi seat chỉ có tối đa một reservation được CONFIRMED.
- Không tạo HELD nếu seat đã được cấp.

## Operation scope
- Atomic transaction trên Seat + Reservation.
- Payment/notification nằm ngoài transaction.

## Consistency
- Conditional update/transaction theo DBMS đã chọn.
- Read status từ nguồn phù hợp, không từ search index eventual.

## Availability under partition
- Nếu không đạt commit/quorum yêu cầu, từ chối reserve.
- Cho phép GET trạng thái từ cache có nhãn freshness,
  nhưng không dùng cache để quyết định cấp phát.

## Durability
- Nêu write ACK/journal/replication policy.
- Xác định failure model và backup/DR.

## Retry
- Stable idempotency key.
- Unknown commit được đối soát theo reservationId.

## Observability
- Oversell count, condition failures, write p99,
  quorum failures, unknown outcomes, replica lag.

## Validation
- Concurrency tests và fault-injection trong staging.
~~~

Khi review ADR, phải kiểm tra rằng mọi cụm từ “mạnh”, “luôn”, “không bao giờ” đều có điều kiện và bằng chứng đi kèm.

---

## 25. Phát biểu bảo đảm trong điều kiện bình thường và khi sự cố

Một hệ có thể có hai **chế độ vận hành**:

### 25.1. Bình thường

- Leader và quorum có thể liên lạc.
- Strong writes được ACK.
- Replication lag ở mức mục tiêu.
- Read từ replica có thể gần nguồn.
- Transaction và conditional update thành công dưới tải thường.

### 25.2. Mất kết nối giữa các node

- Một phía vẫn giữ quyền commit.
- Phía không đủ quorum có thể không nhận writes mạnh.
- Stale reads có thể vẫn phục vụ nếu hợp đồng cho phép.
- Một số API chọn eventual availability có thể tiếp tục ghi/đọc phân kỳ trong scope riêng.
- Sau khi mạng hồi phục, hệ phải reconcile theo giao thức.

### 25.3. Failover

- Client có thể gặp timeout/unknown result.
- Leader mới có thể chưa có những write chưa được commit theo policy.
- Session token hoặc read model có thể cần bắt kịp.
- Retry không được tạo side effect trùng.

### 25.4. Mất region

- Local consistency của region không giải quyết sự cố mất cả region.
- Hệ cần replication/backup ngoài region và DR runbook.
- RPO/RTO phải đo riêng.
- Một số trạng thái cross-region có thể cần reconcile.

### 25.5. Đặt bốn câu hỏi cho từng chế độ

| Chế độ | Có phục vụ read? | Có phục vụ write? | Mức dữ liệu trả về? | Nếu không đáp ứng? |
|---|---|---|---|---|
| Bình thường | ? | ? | Strong/session/eventual? | ? |
| Network partition | ? | ? | Stale được phép không? | ? |
| Leader failover | ? | ? | Commit point nào? | ? |
| Region loss | ? | ? | Recovery point nào? | ? |

Không để ô trống trong tài liệu quyết định production nếu nghiệp vụ yêu cầu một bảo đảm cụ thể.

---

## 26. Kiểm thử consistency phải dùng lịch sử thao tác, không chỉ snapshot cuối

Nếu chỉ kiểm tra giá trị cuối sau 1.000 write, có thể bỏ qua một read từng thấy trạng thái cũ sai thời điểm.

### 26.1. Lịch sử đơn giản

~~~text
A starts W(x=1) at 00:00:00.000
A gets ACK         at 00:00:00.100
B starts R(x)      at 00:00:00.200
B sees x=0         at 00:00:00.220
~~~

Nếu cùng key và contract hứa linearizable read/write, không có write mới, lịch sử này là bằng chứng cần điều tra.

### 26.2. Lịch sử có thao tác chồng lấn

~~~text
A starts W(x=1) at 00:00:00.000
B starts R(x)   at 00:00:00.050
B sees x=0      at 00:00:00.060
A gets ACK      at 00:00:00.100
~~~

Read trong khoảng write chưa hoàn tất có thể được linearize trước write. Không tự coi đây là vi phạm.

### 26.3. Những dữ liệu cần ghi

- Operation ID và session/client ID.
- Key hoặc partition scope.
- Invocation và response timestamps.
- Request payload/condition.
- Read value/version hoặc hash.
- Write ACK policy và trạng thái.
- Node/region/shard routing.
- Error, timeout, retry, failover events.
- DBMS/server/driver version và topology.

Không log payload nhạy cảm không cần thiết; có thể dùng hash và ID giả lập trong môi trường thử nghiệm.

### 26.4. Fault injection hợp lệ

Trong staging/test environment được phép:

1. Ghi sequence có ID ổn định.
2. Cấu hình các mức consistency cần thử.
3. Tạo network partition giữa replica bằng công cụ kiểm thử được phê duyệt.
4. Gửi read và write tới các phía.
5. Lưu lịch sử request.
6. Kiểm tra thao tác nào được ACK, lỗi hoặc timeout.
7. Cho mạng hồi phục, kiểm tra conflict resolution và recovery.
8. Đối soát business invariant.

**Không thử phá network hoặc storage production nếu chưa có quy trình, phạm vi và quyền rõ ràng.**

### 26.5. Phân biệt tính đúng và hiệu năng

Một hệ có thể giữ linearizability bằng cách chờ một request đến timeout khi thiếu quorum. Đó có thể là quyết định đúng về consistency nhưng không đáp ứng latency/availability target. Báo cáo phải nêu cả hai, không đánh giá chỉ bằng số read stale.

---

## 27. Những chỉ số cần theo dõi theo loại bảo đảm

| Bảo đảm | Metric | Diễn giải |
|---|---|---|
| Single-item invariant | Số item có counter âm | Dấu hiệu vi phạm conditional allocation |
| Transaction atomicity | Số state nửa vời sau recovery | Có thể do phạm vi transaction sai |
| Linearizable read | Lịch sử read sau acknowledged write trả bản cũ | Có thể vi phạm contract |
| RYW | Số session đọc thiếu write của mình | Trải nghiệm sau lưu |
| Monotonic reads | Số session đọc version lùi | Routing/cache/session token |
| Quorum availability | Tỷ lệ request thiếu quorum | Đánh đổi khi partition/failure |
| Replication | Lag và committed/applied index | Đường đọc có bắt kịp không |
| Journal/durability | Fsync latency, rollback incidents | Bảo vệ acknowledged writes |
| Multi-region | Cross-region propagation lag | RYW hoặc DR giữa vùng |
| API availability | 2xx, 4xx, 5xx, timeouts theo operation | SLO vận hành |
| Idempotency | Duplicate request/replayed side effect | Retry và unknown outcome |
| Workflow | DB/event/payment mismatch | Bảo đảm ngoài một transaction |
| Backup/DR | Restore success, observed RPO/RTO | Phục hồi khi mất dữ liệu |
| Cost | Read/write units, CPU/I/O, p99 | Chi phí của policy mạnh |

### 27.1. Ghi metric theo operation

Một dashboard gộp tất cả API có thể che mất việc:

- GET feed vẫn sẵn sàng.
- POST payment bị từ chối khi thiếu quorum.
- Query search trả stale.
- Read profile cần chờ session token.

Hãy phân nhóm **API + operation + consistency policy + region**.

### 27.2. Không dùng tỷ lệ 2xx thay consistency proof

Một API trả 200 cho hai client cùng giữ một ghế vẫn có thể có 100% success rate nhưng vi phạm business invariant. Ngược lại, từ chối một phía partition có thể bảo vệ invariant nhưng làm success rate giảm.

Cả hai trục đều phải được theo dõi.

---

## 28. Những phát biểu sai thường thấy và cách sửa

| Phát biểu quá rộng | Vấn đề | Cách phát biểu có phạm vi |
|---|---|---|
| “NoSQL là eventual.” | Có nhiều mức theo operation | Nêu read/write API và consistency mode |
| “MongoDB là CP.” | Không nói read/write/transaction scope | Nêu read concern, write concern và topology |
| “DynamoDB luôn strong.” | GSI và multi-region khác | Strong read trên đường được hỗ trợ, GSI eventual |
| “Cassandra QUORUM là linearizable.” | Công thức quorum chưa đủ | Nêu CL, LWT/conditional semantics và phạm vi |
| “Redis atomic nên không mất write.” | Atomicity khác durability | Nêu script scope, AOF/replication/failover |
| “Có 3 replica thì mọi write được bảo vệ.” | Chưa biết ACK và miền lỗi | Nêu số ACK, storage durability, topology |
| “HTTP 200 nghĩa workflow hoàn tất.” | API gồm nhiều bước | Nêu trạng thái từng dependency |
| “Write ACK nghĩa mọi cache cập nhật.” | Cache/index asynchronous | Nêu RYW strategy và freshness |
| “Transaction có nên dữ liệu toàn hệ consistent.” | Transaction scope/isolations khác | Nêu các item, isolation và ngoại vi |
| “Network partition sẽ không ảnh hưởng API.” | Có trade-off CAP | Nêu behavior từng read/write path |
| “Từ chối request vẫn là CAP availability.” | Định nghĩa CAP khác API liveness | Phân biệt phản hồi lỗi và thành công hợp lệ |
| “P có thể bỏ đi để lấy CA.” | Mạng có thể phân vùng | Nêu giả định failure model |
| “Một key strong thì mọi aggregate cũng strong.” | Query nhiều item có snapshot khác | Nêu snapshot/isolation cho query |
| “Strong read ở region A là global strong.” | Cross-region semantics riêng | Nêu region và replication mode |
| “RYW nghĩa không oversell.” | RYW không chống race giữa client | Dùng conditional transaction |
| “Timeout nghĩa write không tồn tại.” | Commit có thể xảy ra trước timeout | Idempotency và reconciliation |
| “Có journal là đạt RPO=0 mọi thảm họa.” | Local disk và region loss khác | Nêu durability/DR và loại sự cố |
| “CAP dự đoán toàn bộ latency hằng ngày.” | CAP tập trung partition trade-off | Đo thêm latency, cost, PACELC nếu cần |
| “Đang thấy v10 rồi v9 là bình thường vì eventual.” | Có thể vi phạm session contract | Kiểm tra monotonic reads |
| “Read ở primary luôn nhanh hơn.” | Tùy tải/network/route | Benchmark theo workload và SLO |

### 28.1. CAP không đủ để chọn hệ thống

Ngoài partition, ứng dụng còn cần đánh đổi **latency và consistency trong điều kiện bình thường**. Các mô hình thảo luận khác như PACELC giúp nhắc rằng khi không partition, latency vẫn là chi phí đáng xét.

CAP không tự quyết định:

- Data model và access patterns.
- Indexing.
- Transaction scope.
- Storage cost.
- Consistency của cache/read model.
- RPO/RTO.
- Khả năng phục hồi lỗi logic.
- Quan sát và vận hành.

Dùng CAP như **một khung đặt câu hỏi**, không phải bảng chọn sản phẩm bằng hai chữ cái.

---

## 29. Bài tập 1: phân loại ranh giới thao tác

Một ứng dụng checkout gọi:

~~~text
A. Update Inventory item nếu available >= 1.
B. Insert Reservation document.
C. Publish ReservationCreated lên broker.
D. Gọi payment provider.
E. Query search index để hiển thị vé đã đặt.
~~~

Hãy trả lời:

1. Nếu A là atomic conditional update, điều gì được bảo vệ?
2. Nếu A thành công nhưng B thất bại, nguy cơ gì xuất hiện?
3. Nếu A/B cùng transaction, liệu C/D/E tự nằm trong transaction không?
4. Nếu DB nguồn đã ACK nhưng E chưa thấy, đó là vấn đề consistency nào?
5. Nếu mạng bị partition và không đạt quorum cần thiết, endpoint nên làm gì để không tự xác nhận đặt vé?
6. Nếu client timeout sau commit của A/B, retry với ID nào?
7. Những ràng buộc nào cần đưa vào consistency contract?

**Gợi ý:** chỉ xem A là một atomic operation trên item, trừ khi có chứng cứ B nằm cùng transaction. Event bus/payment/search có xác nhận và tính nhất quán riêng.

## 30. Bài tập 2: phân tích CAP trên một ghế

Hai replica A/B cùng lưu `seat-42=FREE`. Mạng bị chia tách hoàn toàn giữa chúng. Client X tới A, client Y tới B; cả hai muốn đặt cùng ghế.

### Phần A — Yêu cầu strict

Nghiệp vụ cam kết một ghế chỉ được xác nhận một lần.

Trả lời:

- Nếu A được quyền commit, B có thể trả ACK đặt ghế thành công mà không liên hệ A không?
- Khi B thiếu quorum hoặc không có quyền leader, phản hồi nào phù hợp?
- Hành vi ấy giảm availability của thao tác nào?
- B có thể tiếp tục trả thông tin seat theo stale read nếu API cho phép không?
- Vì sao một HTTP 503 hữu hạn không đồng nghĩa tính availability CAP được giữ?

### Phần B — Yêu cầu offline-first

Nghiệp vụ cho phép mỗi bên tạm nhận yêu cầu rồi reconcile.

Trả lời:

- Khi mạng hồi phục và có hai đặt ghế mâu thuẫn, business xử lý ra sao?
- Có cần đánh dấu `PENDING` thay vì `CONFIRMED` không?
- Có thể hỗ trợ user bằng waitlist/refund/compensation không?
- Nếu chia trước quota/seat ownership cho từng region, bài toán thay đổi thế nào?

### Phần C — Hai ghế độc lập

Nếu X đặt seat-42 và Y đặt seat-43, hai request còn cần coordination giống nhau không? Trả lời dựa trên **phạm vi shared state và invariant**, không chỉ nhãn CP/AP.

## 31. Bài tập 3: viết contract cho DynamoDB

Bảng `Orders` có primary key `orderId`, một GSI `status-createdAt`, và global table ở nhiều region.

Yêu cầu:

1. Viết bảo đảm của `PutItem` trên base table.
2. Viết bảo đảm của `GetItem(orderId, ConsistentRead=true)` theo phạm vi được hỗ trợ.
3. Viết rõ vì sao `Query` qua GSI không tự là strong read.
4. Chỉ ra yêu cầu khi đọc ở một region khác ngay sau write.
5. Nếu Order và PaymentLog là hai item, cần API/transaction nào để atomic?
6. Nếu timeout sau `PutItem`, làm sao dùng ID ổn định và conditional write?
7. Những chỗ nào cần dựa vào tài liệu tính năng/giới hạn hiện hành của dịch vụ?

Soạn hai phát biểu: một phát biểu **quá rộng** và một phát biểu **đã giới hạn đúng scope**.

## 32. Bài tập 4: Cassandra và điều kiện quorum

Giả định RF=3, replica A/B/C.

Lịch sử:

~~~text
T0: A nhận write x=7.
T1: A trả ACK ở CL=ONE.
T2: B và C chưa thấy x=7.
T3: Read ở CL=ONE từ B thấy x=6.
~~~

Câu hỏi:

1. Read này có thể xảy ra theo các điều kiện nêu không?
2. Nếu API hứa read-your-writes cho client, cần thêm gì?
3. Nếu write CL=QUORUM, read CL=QUORUM, điều kiện giao nhau là gì?
4. Những giả định nào còn thiếu để suy ra một bảo đảm mạnh?
5. Nếu muốn “chỉ trừ inventory khi đủ”, QUORUM thông thường có thay thế LWT/CAS không?
6. Nếu trạng thái nằm trên nhiều partition, CAS một row có đủ không?

**Gợi ý:** một điều kiện số replica phản hồi không tự chứng minh atomic conditional update hoặc transaction nhiều partition.

## 33. Bài tập 5: thiết kế API cho hệ đặt vé

Bối cảnh:

~~~text
1.000.000 vé được bán trong nhiều ngày.
100.000 client đồng thời vào một sự kiện hot.
Có 3 region phục vụ web.
Payment provider nằm ngoài database.
Search index được cập nhật qua CDC.
Nghiệp vụ không cho phép overselling ghế đánh số.
~~~

Hãy soạn tài liệu gồm:

### 33.1. Business invariants

- Mỗi seat ID được `CONFIRMED` tối đa một lần.
- Hold có thời hạn và confirm/cancel/expiry cạnh tranh an toàn.
- Payment callback trùng không làm confirm hai lần.
- Không tự trả ACK đặt vé khi commit chưa thỏa điều kiện.

### 33.2. Operation matrix

| Operation | Scope | Consistency | Availability during partition | Retry |
|---|---|---|---|---|
| `GET event summary` | ? | ? | ? | ? |
| `GET seat availability` | ? | ? | ? | ? |
| `POST hold seat` | ? | ? | ? | ? |
| `POST confirm` | ? | ? | ? | ? |
| `GET reservation status` | ? | ? | ? | ? |
| `SEARCH booked events` | ? | ? | ? | ? |

### 33.3. Failure model

- Mất một replica.
- Network partition giữa hai region.
- Commit timeout.
- Search index lag.
- Payment callback đến sau expiry.
- Region loss.

Với mỗi lỗi, ghi **điều gì được bảo đảm, điều gì không, và phản hồi API ra sao**.

### 33.4. Kiểm thử

Đề xuất lịch sử thao tác ghi/đọc, concurrency race, mô phỏng partition trong staging, đo quorum failures, oversell count và reconciliation sau phục hồi.

Không thực hiện fault injection phá hủy trên production.

---

## 34. Bài tập 6: kiểm tra một tuyên bố kiến trúc

Nhóm phát triển đưa ra câu:

> “Chúng tôi có ba replica, consistency QUORUM, transaction và cache Redis. Vì vậy toàn bộ app vừa CP vừa AP, mọi read đều strong, không thể mất dữ liệu và luôn trả kết quả sau 50 ms.”

Hãy chỉ ra ít nhất mười thông tin còn thiếu.

Gợi ý:

1. DBMS/phiên bản/driver?
2. `QUORUM` dùng cho read hay write?
3. RF, membership và topology?
4. ACK của replica là memory hay fsync?
5. Transaction scope và isolation?
6. Redis là cache hay nguồn?
7. Read có qua replica/GSI/search không?
8. Khi thiếu quorum, endpoint nào bị từ chối?
9. Network partition giữa các region sẽ xử lý thế nào?
10. Durability/backup/DR có phạm vi nào?
11. P95/P99 được đo với workload gì?
12. Unknown commit outcome và idempotency ra sao?
13. API có thực hiện external side effects không?
14. Phiên/người dùng có RYW/MR không?
15. Kỳ vọng “50 ms” có áp vào read strong cross-region không?

Viết lại câu trên thành nhiều **bảo đảm nhỏ có điều kiện và có thể kiểm chứng**.

---

## 35. Checklist cuối cùng: trước khi hứa một thuộc tính phân tán

Mỗi khi viết tài liệu thiết kế, ADR, SLA hoặc phản hồi review cho một hệ NoSQL, hãy điền:

| Trường | Nội dung bắt buộc |
|---|---|
| **Operation** | API/lệnh cụ thể và kết quả mong đợi |
| **Data scope** | Key, item, partition, table, nhiều item hay workflow |
| **Client scope** | Một session, một tenant, mọi client, region nào |
| **Consistency model** | Linearizable, session, causal, eventual hoặc ràng buộc transaction |
| **Mechanism** | Read/write concern, CL, CAS, LWT, transaction, token |
| **ACK condition** | Khi nào client được coi là ghi thành công |
| **Read source** | Primary, replica, GSI, cache, search, regional view |
| **Failure assumptions** | Node/zone/region, partition, quorum, clocks, storage |
| **On failure** | Chờ, reject, timeout, stale có nhãn, reconcile |
| **Durability** | Write được bảo vệ trước lỗi gì, backup/PITR ra sao |
| **Time bounds** | Deadline, consistency wait, p95/p99 target |
| **Excluded paths** | Những hệ/đường đọc không được bảo đảm |
| **Verification** | Lịch sử operation, invariant, test/fault injection, metrics |

### 35.1. Đặc biệt cảnh giác với những từ tuyệt đối

- “**Luôn luôn** nhất quán.”
- “**Không bao giờ** mất dữ liệu.”
- “**Tất cả** bản sao được cập nhật ngay.”
- “**Mọi** read đều strong.”
- “**Mọi lúc** hệ đều sẵn sàng.”
- “**Bất kỳ** transaction nào đều atomic.”
- “**Không thể** oversell.”

Đây là những phát biểu cần **ràng buộc operation, topology, giả định và thời gian**; nếu không, chúng gần như chắc chắn quá rộng.

## 36. Tổng kết

Trong hệ NoSQL phân tán, **bảo đảm không tồn tại như một nhãn độc lập**. Nó luôn gắn với một thao tác, một phạm vi dữ liệu, một tập client, một cơ chế xác nhận, một mô hình lỗi và một cách hệ xử lý khi không thể đáp ứng.

Những nguyên tắc quan trọng nhất:

1. **CAP nói về đánh đổi giữa linearizability và availability khi mạng phân vùng**, không phải một trò chơi chọn hai trong ba nhãn cho mọi thời điểm.
2. **Một item atomic không làm cả workflow atomic.** Transaction, session và event bus có phạm vi riêng.
3. **Một strong read không có nghĩa mọi read đều strong.** Base table, replica, secondary index, cache và cross-region có thể khác semantics.
4. **Quorum là điều kiện phản hồi/giao nhau trong mô hình xác định**, không tự thay thế commit protocol, conflict resolution hoặc durability.
5. **ACK chỉ có nghĩa theo write policy.** Timeout có thể để lại trạng thái commit chưa xác định; retry cần idempotency.
6. **Consistency khác durability, availability, isolation và nghiệp vụ.** Không dùng một thuật ngữ bao trùm tất cả.
7. **Khi partition xảy ra, phải nói rõ thao tác nào được phục vụ, thao tác nào bị từ chối và dữ liệu cũ nào được phép trả.**
8. **Phát biểu đúng là phát biểu có thể kiểm thử.** Ghi operation history, metadata, topology, failure assumptions và SLO cho từng đường truy cập.

**Thay vì nói “hệ thống này là CP/AP và dữ liệu luôn đúng”, hãy nói chính xác: “với thao tác này, trên những đối tượng này, sau điều kiện xác nhận này và trong những sự cố này, hệ bảo đảm điều gì — còn khi không thể bảo đảm, nó sẽ làm gì”.**
