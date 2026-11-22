# Giới hạn của cách diễn giải chọn hai trong ba một cách máy móc

Khi thảo luận cơ sở dữ liệu NoSQL, ta thường nghe câu: **“Định lý CAP nói rằng hệ phân tán chỉ được chọn hai trong ba: Consistency, Availability và Partition tolerance.”** Từ câu đó, người ta nhanh chóng phân loại một sản phẩm thành **CP**, **AP** hoặc **CA**, rồi coi nhãn ấy như đáp án cuối cùng cho mọi bài toán kiến trúc.

Cách nhớ này tiện nhưng **dễ dẫn đến quyết định sai**. Một hệ thống có thể vẫn cung cấp cả tính nhất quán mạnh lẫn khả năng phục vụ khi mạng khỏe; có thể **chặn ghi** tại một vùng bị cô lập nhưng **tiếp tục phục vụ đọc cũ** ở vùng đó; có thể giữ **quorum write** cho một loại dữ liệu trong khi sử dụng **search index bất đồng bộ** cho loại khác. Và một database được gọi là “AP” không tự giải quyết xung đột hoặc bảo đảm mọi request của ứng dụng đều thành công.

**CAP là một kết quả lý thuyết về những bảo đảm có thể đồng thời duy trì trong hệ thống phân tán khi xảy ra phân vùng truyền thông**, không phải một bảng chọn ba tính năng độc lập cho sản phẩm. Giá trị thực tiễn của CAP nằm ở chỗ nó buộc kiến trúc sư mô tả **thao tác nào phải đúng như thế nào, mạng có thể hỏng ra sao, và ứng dụng làm gì khi không thể đồng thời đáp ứng mọi yêu cầu**.

Bài học **Database No SQL → CAP và các đánh đổi** này phân tích sâu giới hạn của khẩu hiệu “chọn hai trong ba”, làm rõ định nghĩa chính xác hơn của C/A/P, nghiên cứu đường đọc–ghi theo từng yêu cầu, quorum và leader, các đánh đổi ngoài CAP như **PACELC**, dữ liệu nhiều vùng, khả năng xử lý xung đột, transaction, kiểm thử phân vùng mạng và lựa chọn ở tầng nghiệp vụ.

> **Lưu ý:** CAP nói về **khả năng bảo đảm**, không dự đoán trực tiếp độ trễ p99, giá hạ tầng hay tính năng của một phiên bản database cụ thể. Các con số, lưu lượng, sơ đồ và cấu hình trong bài là **ví dụ giả định** để luyện phân tích, không phải benchmark hay bảng xếp hạng MongoDB, Cassandra, DynamoDB, Redis, HBase hoặc các nhà cung cấp khác.

## 1. Khẩu hiệu “chọn hai trong ba” đã bỏ sót điều gì?

Cách kể thông dụng:

~~~~text
       Consistency
           /\
          /  \
         /    \
Availability--Partition tolerance

Hệ thống chọn:
  CA hoặc CP hoặc AP.
~~~~

Người mới học có thể suy diễn:

- Chọn CP nghĩa là hệ thống **không có Availability** ngay cả khi mọi node khỏe.
- Chọn AP nghĩa là dữ liệu **luôn không nhất quán**.
- Chọn CA nghĩa là kiến trúc có thể **không quan tâm phân vùng mạng**.
- Vì đã “chọn hai”, hệ thống không thể có **bất kỳ phần nào** của tính chất thứ ba.
- Mọi endpoint của một database có cùng một nhãn CP hoặc AP.
- Một hãng ghi “AP” nghĩa là mọi write luôn được nhận, không bao giờ timeout.
- Chọn CP hay AP sẽ cho biết luôn độ trễ, throughput, độ bền và chi phí.

**Không có kết luận nào trong số đó theo trực tiếp từ CAP.**

Một cách diễn giải sát bài toán hơn:

> **Khi một phân vùng truyền thông khiến các phần của hệ phân tán không thể trao đổi thông tin cần thiết, không thể bảo đảm đồng thời linearizable consistency và availability theo định nghĩa của CAP cho mọi thao tác tại mọi node không hỏng.**

Những từ khóa quan trọng ở đây là **khi xảy ra phân vùng**, **linearizable**, **availability theo định nghĩa CAP**, **mọi thao tác**, **mọi node không hỏng** và **bảo đảm đồng thời**.

## 2. Consistency trong CAP là gì?

Trong cách phát biểu kinh điển của định lý CAP, **C** được hiểu theo hướng **atomic consistency/linearizability** đối với hệ lưu trữ đối tượng hoặc thanh ghi chia sẻ.

Một thao tác có vẻ như xảy ra **nguyên tử tại một thời điểm** nằm giữa khi request được gửi và khi response được nhận, và lịch sử phải **tôn trọng thứ tự thời gian thực** của các thao tác không chồng lấp.

### 2.1. Ví dụ linearizable register

Giả sử khóa stock có giá trị ban đầu bằng 10:

~~~~text
T0  Client A bắt đầu WRITE(stock = 9)
T1  WRITE hoàn tất và A nhận success
T2  Client B mới bắt đầu READ(stock)
T3  B nhận kết quả
~~~~

Nếu không có write khác và đường đọc theo hợp đồng linearizable, B **không được trả 10**: Write đã hoàn tất trước khi Read bắt đầu.

Ký hiệu trực giác:

\[
finish(W_1)<start(R_2)
\Rightarrow
R_2\text{ phải quan sát }W_1\text{ hoặc trạng thái hợp lệ mới hơn}
\]

Trong khi đó, nếu W1 và R2 **chồng lấp về thời gian**, lịch sử có thể cho phép Read được sắp trước hoặc sau Write theo những điều kiện linearizability.

### 2.2. Không phải chữ C của ACID

**ACID Consistency** nói về việc bảo toàn các **ràng buộc/bất biến nghiệp vụ** qua giao dịch, theo schema và transaction semantics.

**CAP Consistency** nói về mô hình quan sát **như một đối tượng tuyến tính hóa** khi có truy cập đồng thời và phân tán.

Ví dụ một hệ có thể cung cấp linearizable reads cho một số key, nhưng code nghiệp vụ vẫn chấp nhận stock=-1 nếu ứng dụng gọi decrement không điều kiện. Ngược lại, một hệ dùng quy trình giữ chỗ có điều kiện có thể bảo vệ invariant không âm dù một read model ở vùng xa không được cung cấp strong read.

| Khái niệm | Câu hỏi |
| --- | --- |
| CAP C / linearizability | Read sau một write hoàn tất có thể quay về giá trị cũ không? |
| ACID Consistency | Giao dịch có giữ những invariant được định nghĩa không? |
| Atomicity | Những thay đổi trong một transaction có được áp dụng toàn bộ hoặc không? |
| Isolation | Các giao dịch đồng thời được phép nhìn thấy/ảnh hưởng nhau như thế nào? |
| Durability | Write đã được ACK tồn tại qua những sự cố nào? |
| Causal consistency | Thao tác phụ thuộc có thể bị quan sát trước nguyên nhân không? |
| Eventual consistency | Replica có hội tụ khi điều kiện hoạt động cho phép không? |

**Một database “mạnh về consistency” trong quảng cáo không đủ cho biết nó cung cấp loại nào và trên những API nào.**

### 2.3. Sequential, causal và eventual không giống linearizable

- **Eventual consistency** đặt trọng tâm vào hội tụ khi không có cập nhật mới và các giả định cần thiết được đáp ứng; không bắt buộc mọi read ngay sau write là mới nhất.
- **Causal consistency** giữ thứ tự những thao tác có quan hệ nguyên nhân–kết quả, nhưng không yêu cầu mọi client độc lập lập tức nhìn thấy write đã hoàn tất của người khác.
- **Sequential consistency** yêu cầu có thể giải thích thao tác bằng một thứ tự tuần tự tôn trọng program order của từng process, nhưng không nhất thiết tôn trọng real-time order giữa các process.
- **Linearizability** tôn trọng real-time order của các thao tác không chồng lấp.
- **Serializable transaction** liên quan thứ tự transaction, không tự đồng nghĩa linearizable; strict serializability kết hợp các yếu tố này ở cấp transaction.

Khi nói “hy sinh C” trong CAP, không có nghĩa hệ không còn **bất kỳ dạng nhất quán nào**. Nó có thể vẫn giữ causal order, monotonic reads, per-key order, unique operation IDs hoặc eventual convergence theo hợp đồng khác.

## 3. Availability trong CAP là gì?

Trong cách phát biểu hình thức thường dùng, **A** đòi mọi request gửi đến một node không hỏng **cuối cùng nhận được một response hợp lệ** theo đối tượng/hợp đồng đang xét. Một response đơn thuần báo **“không phục vụ vì đang phân vùng”** không tương đương thao tác read/write đã được đáp ứng thành công theo nghĩa availability đó.

Đây **không phải** cùng khái niệm với một SLA “uptime 99,99%” hay HTTP server luôn trả mã trạng thái trong 100 ms.

### 3.1. Availability CAP khác uptime/SLO

| Câu hỏi | CAP Availability | Availability SLO thực tế |
| --- | --- | --- |
| Đơn vị | Mọi request ở node không hỏng trong mô hình | Tỷ lệ request/giây/phút thành công theo đo lường |
| Ngưỡng thời gian | Có phản hồi cuối cùng, không nhất thiết SLA cố định | Ví dụ 99,95% request dưới 500 ms |
| Khi phân vùng dài vô hạn | Không thể chỉ đợi phía kia hồi phục rồi coi đã đáp ứng | Thường phân vùng tính là sự cố và tiêu tốn error budget |
| Response 503 do thiếu quorum | Không đáp ứng thao tác như yêu cầu | Có thể được tính là request lỗi |
| HTTP 200 nhưng trả dữ liệu cũ | Có thể hoàn tất read, nhưng vi phạm C nếu read được yêu cầu linearizable | Có thể được tính “success” sai nếu SLI chỉ xem status code |
| Một vùng bị cô lập | Phải xét request tới node không hỏng ở vùng đó | SLO còn phụ thuộc traffic routing và cách tính vùng |

CAP không cho ta trực tiếp p99, error budget hay **tỷ lệ availability**. Để làm SLO vận hành, phải đo riêng **request success rate**, **latency**, **staleness**, **business correctness**.

### 3.2. “Eventually responds” không phải “đáp ứng nhanh”

Nếu một request mất 30 phút mới hoàn tất, nó có thể không vi phạm một phát biểu liveness không giới hạn thời gian, nhưng đã thất bại theo SLO của API 200 ms.

Ngược lại, nếu hệ **chặn đến khi mạng lành** thì khi phân vùng có thể tồn tại **vô hạn**, không thể bảo đảm mọi request cuối cùng có kết quả. Đó là lý do lựa chọn chờ thông tin để bảo toàn C có thể đánh đổi A trong định lý.

### 3.3. Trả HTTP 202 có luôn bảo toàn A không?

Giả sử một node cô lập trả:

~~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "status": "QUEUED",
  "operationId": "OP-77"
}
~~~~

Đây có thể là **một API hữu ích**, nhưng phải hỏi: thao tác gốc là **“ghi dữ liệu và xác nhận đã commit”** hay chỉ **“nhận yêu cầu vào queue cục bộ”**?

Nếu API đã đổi đặc tả từ **committed write** sang **durable enqueue**, việc trả 202 không chứng minh cùng một register linearizable đã xử lý write. Nó **đổi loại thao tác và hợp đồng**, có thể hợp lý nhưng không phải lách định lý CAP bằng mã HTTP.

### 3.4. Node không hỏng khác mọi client/mọi network path

Định lý xét sự trao đổi thông điệp trong mô hình phân tán. Nếu client mất kết nối hoàn toàn với mọi node, hoặc thiết bị người dùng tắt điện, không có kiến trúc database nào bảo đảm đáp ứng được mọi HTTP request.

Nói “AP nghĩa là hệ luôn sẵn sàng trong mọi sự cố” là vượt quá phạm vi của khái niệm availability.

## 4. Partition tolerance nghĩa là gì?

**P** trong CAP xét khả năng hệ thống đối mặt với tình trạng **thông điệp giữa các node bị mất hoặc bị trì hoãn tùy ý**, khiến các nhóm node không thể trao đổi thông tin cần thiết.

Một phân vùng mạng có thể do:
- Đứt kết nối giữa hai vùng.
- Firewall hoặc routing cấu hình sai.
- Một phía nhận được request nhưng phản hồi không tới.
- Packet loss kéo dài, timeout hoặc network congestion cực đoan.
- Đứt kết nối giữa leader và một phần follower.
- Kênh một chiều hoạt động nhưng chiều ngược lại không.

Không nên đồng nhất partition với **cả data center tắt điện**. Trong CAP, hai nhóm node có thể **đều còn sống và phục vụ client**, nhưng **không nói chuyện được với nhau**.

### 4.1. P không phải tính năng bật/tắt

Trong một hệ thực sự phân tán qua mạng, **phân vùng là một dạng lỗi mà kiến trúc phải xử lý hoặc chấp nhận rủi ro**, không phải một checkbox độc lập mà ta bỏ chọn để nhận C+A miễn phí.

Có thể xây hệ đơn node hoặc hệ chỉ hoạt động trong môi trường mà ta **giả định kết nối không hỏng**. Khi giả định ấy đúng, cả consistency lẫn availability có thể cùng giữ. Nhưng điều đó không chứng minh một cụm nhiều vùng có thể **bảo đảm không bao giờ phân vùng**.

### 4.2. “Partition tolerance” không nghĩa hệ sẽ luôn xử lý được mọi request

Một hệ ưu tiên C có thể giữ **an toàn dữ liệu khi phân vùng** bằng cách từ chối những thao tác thiếu thông tin. Đó vẫn là một cách **chịu được phân vùng theo mục tiêu safety**, dù availability của một số request giảm.

Một hệ ưu tiên A có thể tiếp tục đáp ứng read/write tại nhiều nhóm nhưng chấp nhận divergent states và **reconciliation** sau khi mạng hồi phục.

Hai cách đều là **phản ứng trước partition**, không phải một bên “có P” và một bên “không P”.

## 5. Thí nghiệm tư duy cho thấy vì sao không thể giữ cả C và A

Xét hai replica A và B đang lưu cùng một register:

~~~~text
Ban đầu:
  A: x = 0
  B: x = 0

Mạng bị phân vùng:
  Client W <-> A       B <-> Client R
             XXXXXXXXX
          Không có liên lạc A-B
~~~~

Dòng thời gian:

1. Client W gửi **write x=1** cho A.
2. A **trả success** cho W, nghĩa là theo hợp đồng hệ đã hoàn tất write.
3. Sau khi W nhận success, Client R bắt đầu **read x** ở B.
4. B chưa biết write x=1, vì thông điệp A→B không thể đi qua partition.

B phải quyết định:

| Hành vi ở B | Availability cho read | Linearizability |
| --- | --- | --- |
| Trả **x=0** ngay | Có kết quả read | **Vi phạm**, vì write x=1 đã hoàn tất trước read |
| Đợi đủ thông tin, có thể mãi không tới | Không bảo đảm phản hồi trong partition kéo dài | Có thể bảo toàn C |
| Trả lỗi “không có quorum” | Không phục vụ read theo hợp đồng | Có thể bảo toàn C |
| Chuyển read sang A khi network path cho phép | Có thể phục vụ | Có thể giữ C, nhưng phụ thuộc đường truy cập |
| Trả “x chưa biết” | Đổi ngữ nghĩa read | Không phải read x đã được đáp ứng như mô hình register |

Đây là lõi trực giác của CAP. **B không thể vừa biết chắc giá trị mới vừa trả ngay một giá trị chính xác nếu mọi thông tin cần thiết bị chặn**.

### 5.1. Nếu A không ACK write thì sao?

A có thể đợi quorum/leader consensus trước khi phản hồi. Khi không đạt được điều kiện, nó không xác nhận write; đây là lựa chọn thường thấy ở đường ghi ưu tiên tính nhất quán.

Nhưng lúc đó request W **không được đáp ứng thành công theo hợp đồng write**, tức availability của write tại phần bị cô lập bị đánh đổi.

### 5.2. Nếu hai write độc lập được cả hai phía chấp nhận thì sao?

~~~~text
Client W1 -> A: x=1, success
Client W2 -> B: x=2, success
~~~~

Nếu hai phía không trao đổi được thông tin, sau khi mạng lành sẽ cần quy tắc giải quyết xung đột. Một hệ có thể:
- Giữ nhiều phiên bản và yêu cầu merge.
- Chọn winner theo timestamp/version.
- Dùng CRDT nếu phép toán hỗ trợ merge.
- Dùng một workflow nghiệp vụ giải quyết chênh lệch.

Không có **một thứ tự linearizable toàn cục cho cả hai write đã ACK** chỉ từ việc hai phía đều cho phép cập nhật độc lập trong partition.

### 5.3. Điều kiện của ví dụ rất quan trọng

Kết luận ở bước 4 sử dụng giả định:
- Write trên A đã **hoàn tất** trước Read trên B bắt đầu.
- Read trên B là read của **cùng đối tượng/hợp đồng**.
- B không có kênh khác để biết kết quả write.
- Hệ phải bảo đảm đúng cho mọi lịch sử hợp lệ, không chỉ vài lần chạy bình thường.

Nếu write và read chồng lấp, hoặc dữ liệu được định tuyến vào một nguồn khác mà B truy cập được, phân tích cụ thể có thể khác.

## 6. Khi mạng khỏe, không có quy tắc “phải bỏ một chữ”

CAP nói về **giới hạn trong những lịch sử có partition**. Khi các node có thể liên lạc đủ tốt, hệ có thể cung cấp:
- Read linearizable.
- Write linearizable.
- Khả năng phục vụ cao.
- Replication và failover.

Ví dụ một cluster có leader được bầu, quorum writes và read path phù hợp có thể xử lý phần lớn workload bình thường với C và A ở mức tốt. Nếu một link bị đứt nhưng đa số node còn kết nối, một số phần của cụm vẫn có thể tiếp tục phục vụ.

Vì vậy **“CP nghĩa là lúc bình thường cũng không available”** là suy diễn sai.

### 6.1. Không phải cứ có packet loss là toàn bộ cluster dừng

Partition có thể chia cụm 5 node thành nhóm 3 và nhóm 2. Một protocol dựa trên majority có thể tiếp tục hoạt động ở nhóm 3, trong khi nhóm 2 không đủ điều kiện xác nhận những write cần quorum.

~~~~text
Group 1: Node A, B, C  <--- 3/5: có thể đạt majority
                      X
Group 2: Node D, E     <--- 2/5: không đạt majority
~~~~

Trong tình huống đó:
- Write tới nhóm 3 **có thể** tiếp tục thành công.
- Write tới nhóm 2 có thể bị từ chối/chờ.
- Read ở nhóm 2 có thể được phục vụ ở consistency yếu hơn nếu API cho phép, hoặc bị chặn với strong read.
- Một số dịch vụ không liên quan partition này vẫn chạy bình thường.

**Availability là đặc tính của thao tác, đường đi và nhóm node tại thời điểm đó**, không phải nhãn tuyệt đối của mọi request.

## 7. “Chọn hai” nên được thay bằng “khi partition xảy ra, thao tác nào ưu tiên điều gì?”

Một ma trận thực tế:

| Thao tác | Khi mạng bình thường | Khi một vùng thiếu quorum | Lý do |
| --- | --- | --- | --- |
| Xem danh sách sản phẩm | Đọc index gần nhất | Có thể trả index cũ có nhãn độ mới | Trải nghiệm khám phá chấp nhận staleness |
| Xem chi tiết sản phẩm | Đọc source hoặc projection mới | Có thể fallback hoặc báo chưa đồng bộ | Cần cân bằng độ mới và UX |
| Tăng lượt xem | Ghi counter/event | Có thể ghi cục bộ nếu chấp nhận reconcile | Thống kê có thể eventual |
| Giữ tồn kho | Conditional reserve tại authority | **Không** tự xác nhận khi thiếu điều kiện an toàn | Tránh oversell |
| Tạo thanh toán | Ghi ledger/provider idempotent | UNKNOWN/PENDING khi chưa xác minh được | Không được debit hai lần |
| Thu hồi quyền | Kiểm tra policy có thẩm quyền | Fail closed nếu không đáp ứng chính sách | Hậu quả dữ liệu cũ nghiêm trọng |
| Feed cộng đồng | Tôn trọng causal dependencies | Có thể đọc cache và chờ phần phụ thuộc | Causal ordering quan trọng |
| Ghi log telemetry | Ingest có thể async | Ghi durable local queue nếu hợp đồng cho phép | Có thể tách nhận sự kiện và xử lý |

Bảng không nói tất cả các thao tác trên cùng một database nhất thiết có cùng mức consistency. Một ứng dụng có thể xây **nhiều đường lưu trữ** hoặc **nhiều consistency levels** cho các mục tiêu khác nhau.

### 7.1. Chọn theo invariant, không theo thương hiệu

Câu hỏi thiết kế nên là:

> “Ở partition, hệ thống được phép trả dữ liệu cũ nào, được phép chấp nhận loại write nào, và hành động nào phải dừng để tránh sai nghiệp vụ?”

Không nên chỉ hỏi:

> “Database nào AP hơn?”

Một nhãn phân loại rất rộng không mô tả đủ đường thao tác cần được bảo vệ.

## 8. Một hệ thống có thể trộn CP-like và AP-like theo đường truy cập

Hãy xét thương mại điện tử:

~~~~mermaid
flowchart LR
    USER["Người dùng"] --> SEARCH["Search API"]
    USER --> CHECKOUT["Checkout API"]
    SEARCH --> IDX[("Search index eventual")]
    CHECKOUT --> INV[("Inventory authority")]
    CHECKOUT --> ORD[("Order/operation ledger")]
    INV --> EVENTS["Outbox / CDC"]
    EVENTS --> IDX
~~~~

Khi partition:
- **Search API** có thể trả danh sách sản phẩm từ index cũ, kèm timestamp/độ mới.
- **Checkout API** có thể từ chối giữ hàng nếu không liên lạc được với authority hoặc không đủ quorum.
- **Order status API** có thể trả UNKNOWN/PENDING cho một commit chưa xác định.
- **Analytics** có thể chấp nhận event vào queue cục bộ rồi đồng bộ sau.

Ứng dụng này không thể được mô tả hữu ích bằng một nhãn **AP** hoặc **CP** duy nhất.

### 8.1. Cùng một request có nhiều bước consistency khác nhau

Ví dụ:

~~~~text
GET /search?q=book
  -> Search index eventual

POST /checkout
  -> Read current price at authority
  -> Conditional reserve stock
  -> Create order with idempotency key
  -> Outbox event
  -> Search index cập nhật sau
~~~~

Nếu query search cũ nhưng checkout có conditional guard, **business correctness** vẫn có thể giữ dù trải nghiệm search chưa thật mới.

### 8.2. Đừng ngụy trang thao tác thất bại bằng success

Trong partition, checkout API có thể ghi một “ý định đặt hàng” cục bộ và trả:

~~~~json
{
  "operationId": "OP-101",
  "status": "PENDING_CONFIRMATION"
}
~~~~

Đây là một **sản phẩm/hợp đồng khác** với:

~~~~json
{
  "operationId": "OP-101",
  "status": "CONFIRMED",
  "stockReserved": true
}
~~~~

Nếu chưa có bằng chứng đã giữ stock theo invariant, API **không được** giả vờ đã confirmed chỉ để tăng biểu đồ HTTP 2xx availability.

## 9. CP và AP là nhãn giản lược, không phải bản mô tả đầy đủ một sản phẩm

Thông thường:
- **CP-like:** Khi thiếu thông tin cần thiết, ưu tiên tính nhất quán mạnh; một số request phải chờ hoặc từ chối.
- **AP-like:** Khi bị phân vùng, cho phép nhiều phía tiếp tục phục vụ một số thao tác với semantics yếu hơn; cần hội tụ/xử lý xung đột.

Đây chỉ là **cách nói tắt**. Một database thực tế có thể có:
- Một read mode linearizable và một read mode eventual.
- Conditional writes tại một partition và scan/read từ replica khác.
- Leader/quorum cho metadata nhưng replication bất đồng bộ cho data.
- Local transactions nhưng global read model eventual.
- Strong single-item reads nhưng không có multi-item snapshot.
- Consistency phụ thuộc vùng, leader, replica và failover state.
- API write thành công ở đa số node, thất bại ở nhóm thiểu số.

**Đừng đọc trang giới thiệu của sản phẩm rồi suy ra mọi API cùng một điểm trên tam giác CAP.**

### 9.1. Một database có thể bảo đảm mạnh cho một khóa nhưng không cho nhiều khóa

Nếu key A và key B được quản lý riêng, từng read/write có thể được tuyến tính hóa theo hợp đồng, nhưng một truy vấn đọc cả A+B không tự thành transaction snapshot.

Cùng một nhãn CP không cho biết:
- Có multi-key atomicity không.
- Có serializable transactions không.
- Có snapshot reads không.
- Phân trang qua nhiều partition có nhất quán cùng mốc không.

### 9.2. “CA database” nghĩa gì?

Nói “CA” có thể hữu ích **trong mô hình không có phân vùng mạng**, hoặc khi hệ triển khai như một đối tượng đơn node với giới hạn failure model khác. Nhưng ở một hệ phân tán thật sự, giả định P không xảy ra là **chấp nhận một rủi ro vận hành**, không phải loại bỏ nó khỏi vật lý.

Một cluster có thể **không được thiết kế để tiếp tục hoạt động đúng khi partition**, nhưng đó không phải cách có được một bảo đảm C+A+“bỏ P” miễn phí. Khi phân vùng thực sự xảy ra, hệ có thể treo, trả lỗi hoặc cho ra lịch sử không đạt yêu cầu.

### 9.3. “AP database luôn cho phép read/write ở mọi vùng”

Không chính xác nếu:
- Node đã crash hoặc mất hết lưu trữ.
- Request không được route tới replica nào.
- Capacity/throttling giới hạn.
- Một partition không sở hữu key.
- Dịch vụ chỉ cho phép read ở vùng nhưng không cho local writes.
- Có xung đột nghiệp vụ phải từ chối.
- Mô hình consistency của operation cụ thể đòi coordinator.

Chỉ có thể khẳng định các bảo đảm **theo mô hình lỗi và API được nêu rõ**.

## 10. Quorum không phải câu thần chú bảo đảm CAP đúng

Một cách phổ biến để triển khai write/read mạnh là dựa trên quorum.

Giả sử có **N=3 replica**, ứng dụng muốn:
- **W=2** replica xác nhận ghi.
- **R=2** replica tham gia đọc.

Trong một mô hình replica nhất định:

\[
R+W>N
\]

nên read quorum và write quorum **phải giao nhau ít nhất một replica** nếu chúng được lấy từ cùng tập N ổn định.

Với N=3, R=W=2:

\[
2+2>3
\]

Tính chất giao nhau có ích khi xây protocol nhất quán.

### 10.1. Nhưng giao quorum chưa đủ tự động thành linearizable

Cần xem:
- Replica chứa dữ liệu **mới nhất** có trả đúng version không?
- Read có thực hiện reconciliation/read repair/version selection?
- Có leader term/ballot hoặc quy tắc ordering phù hợp?
- Membership có thay đổi cùng lúc không?
- Write chỉ được ACK sau điều kiện nào?
- Sloppy quorum/hinted handoff có dùng các node ngoài replica set gốc không?
- Concurrent reads/writes được sắp thứ tự thế nào?
- Có read từ cache/replica không tham gia quorum không?
- Có xung đột giữa hai leader và fencing token không?

**R+W>N là một điều kiện giao tập hợp trong mô hình đơn giản, không phải chứng minh đầy đủ linearizability của bất kỳ database nào.**

### 10.2. Phân vùng 2–1

~~~~text
Node A, B: kết nối được nhau
Node C: bị cô lập khỏi A, B
~~~~

Với một giao thức cần 2/3:
- A/B có thể hoàn tất những write đạt quorum.
- C một mình không thể xác nhận write cần quorum đó.
- A/C hoặc B/C có thể không giao tiếp được.
- Đường đọc tại C có thể bị chặn/timeout ở consistency mạnh.

Việc “một phía còn hoạt động” **không có nghĩa toàn cluster đạt CAP availability**, vì request ở node không hỏng C có thể không được phục vụ theo hợp đồng.

### 10.3. Chọn R=1, W=2 có phải AP?

Trong mô hình đọc từ một replica, R=1 giúp một số read trả kết quả khi chỉ một node khả dụng, nhưng chúng **có thể stale** tùy protocol. Write W=2 tại nhóm thiểu số vẫn không thành công. Đó là **hai đánh đổi khác nhau cho hai loại request**.

Không nên nhãn hóa cả hệ thống bằng một cặp R/W.

### 10.4. Sloppy quorum không giống quorum trên replica set gốc

Trong một số thiết kế leaderless, ghi có thể được nhận bởi các node thay thế khi replica chính không truy cập được, rồi chuyển dữ liệu về sau. Điều này tăng khả năng tiếp nhận write nhưng không bảo đảm read quorum trên tập replica chính lập tức thấy write.

Khi thảo luận R+W>N, cần xác định **quorum thực sự lấy ở tập node nào**. Không áp dụng bất đẳng thức một cách máy móc nếu replica set có thể thay đổi hoặc ghi nằm trên node thay thế.

## 11. Leader và failover: chọn C hay A ở đâu?

Một hệ single-leader thường định tuyến write qua leader. Nếu leader bị cô lập:
- Nhóm đủ điều kiện có thể bầu leader mới theo protocol.
- Nhóm không đủ điều kiện có thể từ chối/chờ write.
- Những write chưa đạt điều kiện commit có thể có trạng thái chưa rõ.
- Trong giai đoạn failover, availability giảm tạm thời.

### 11.1. Split brain và fencing

Nếu hai nhóm cùng tin mình là leader và đồng thời ACK write xung đột mà không có quy tắc bảo vệ, hệ có thể tạo lịch sử không tuyến tính hóa được.

Một protocol đúng cần các cơ chế như:
- Majority/consensus decision.
- Leader term/epoch.
- Fencing token.
- Log commit index.
- Quy tắc leader step-down khi mất điều kiện an toàn.
- Quy trình reconcile/rollback những thao tác chưa commit theo hợp đồng.

**Chỉ thêm load balancer hoặc kiểm tra heartbeat** không tự loại bỏ split brain khi mạng bị phân vùng.

### 11.2. Lease cũng phụ thuộc mô hình thời gian

Một số thiết kế sử dụng leader lease hoặc read lease để giảm latency. Nhưng việc chứng minh an toàn cần giả định cụ thể về clock drift, lease expiration và fencing. Nếu lease hết hạn ở một nơi trong khi node cũ vẫn có thể ghi vào nguồn không kiểm tra epoch, có rủi ro hai writer cùng hoạt động.

Không nên coi một khóa Redis có TTL hoặc leader flag trong cache là bằng chứng đủ cho linearizable ownership nếu storage bị tác động không kiểm tra **fencing epoch**.

### 11.3. Timeout khi commit không bằng rollback

Một client gửi write tới leader rồi mất kết nối:

~~~~text
Write có thể chưa tới.
Write có thể đang chờ quorum.
Write có thể đã commit, ACK bị mất.
Write có thể bị reject khi leader đổi.
~~~~

Client phải phân biệt **COMMITTED, REJECTED, UNKNOWN**. Tự retry với operationId mới có thể tạo tác dụng phụ trùng, đặc biệt với increment, debit và tạo order.

CAP không thay thế **idempotency/transaction outcome reconciliation**.

## 12. PACELC: ngay cả khi không partition vẫn có đánh đổi

Khẩu hiệu CAP hay bị dùng để giải thích mọi vấn đề performance. Nhưng khi mạng bình thường, hệ phân tán vẫn phải cân bằng **độ trễ và mức nhất quán**.

Mô hình **PACELC** thường được diễn giải:

> **Nếu có Partition (P), hệ cân bằng Availability (A) với Consistency (C); Else (E), tức khi không có partition, hệ vẫn có thể cân bằng Latency (L) với Consistency (C).**

~~~~text
Partition xảy ra?
  |-- Có  -> ưu tiên thao tác nào được đáp ứng và đảm bảo nào?
  |
  |-- Không -> cần đồng bộ/phối hợp bao xa để có read/write mới nhất?
             Chi phí latency ra sao?
~~~~

PACELC là **khung tư duy**, không phải bảng đánh giá chắc chắn của một sản phẩm.

### 12.1. Ví dụ đọc tại local replica

Người dùng ở Việt Nam muốn đọc tài khoản do một leader ở vùng xa quản lý.

- **Local eventual read:** có thể nhanh vì chỉ tới replica gần.
- **Remote/strong read:** có thể cần request tới leader/quorum hoặc giao thức đọc nhất quán, làm tăng RTT.
- **Session causal read:** có thể đọc local nếu dependency đã đến; nếu chưa, phải chờ/reroute.

Khi không có partition, khác biệt latency vẫn tồn tại. **CAP một mình không cho biết lựa chọn nào nhanh**, vì cần xét topology, loại dữ liệu, indexes, cache, RTT, protocol và mức tải.

### 12.2. Không phải strong read lúc nào cũng chậm nhiều

Nếu leader nằm gần người dùng, network RTT thấp hoặc read protocol hiệu quả, chênh lệch có thể nhỏ. Nếu một eventual read phải quét index lớn trong khi strong point read được cache tốt, eventual read **có thể chậm hơn**.

Câu hỏi đúng là **đo p99 và chi phí của đường truy cập thực tế**, không phải dùng nhãn C/A/L như dự báo định lượng.

### 12.3. Bản chất đánh đổi liên tục hơn nhị phân

Một API có thể cung cấp:
- Stale read tối đa trong một khoảng được đo, khi hệ có cơ chế ràng buộc phù hợp.
- Monotonic reads trong session.
- Read-your-writes.
- Causal read với token.
- Strong read cho một item.
- Snapshot read cho một transaction.
- Eventual read cho feed.

Thực tế có **nhiều mức contract**, không chỉ “strong” hoặc “eventual”.

## 13. Những đánh đổi CAP không nói hết

Một thiết kế NoSQL còn phải chọn:

| Trục đánh đổi | Câu hỏi cần trả lời |
| --- | --- |
| **Durability** | Ghi đã ACK tồn tại sau crash/đứt vùng nào? |
| **Isolation** | Các transaction đồng thời có thể gây lost update/write skew không? |
| **Atomicity** | Một hay nhiều item/partition được commit cùng nhau? |
| **Freshness** | Lag sao chép/đánh chỉ mục tối đa và p99 là bao nhiêu? |
| **Latency** | Cần bao nhiêu round trips và qua vùng nào? |
| **Throughput** | Hot partition, leader bottleneck và replica I/O ở đâu? |
| **Cost** | Cross-region network, số replica, index, WAL, compaction, lưu trữ? |
| **Data residency** | Dữ liệu có được phép chuyển sang vùng khác không? |
| **Security** | Quyền mới thu hồi có hiệu lực ngay tại mọi điểm quyết định không? |
| **Operations** | Recovery, failover, backup/restore và reconciliation khó đến đâu? |
| **Semantics** | Những conflict concurrent nào được phép, merge ra sao? |
| **User experience** | UI phải báo trạng thái pending/stale thế nào? |

CAP không trực tiếp trả lời những câu hỏi ấy.

### 13.1. Durability khác consistency

Một hệ có thể phản hồi read nhất quán với dữ liệu leader hiện tại nhưng mất một write chưa được nhân bản/bền vững đúng mức sau sự cố, nếu cấu hình cho phép. Ngược lại, một local queue ghi rất bền có thể nhận event nhưng chưa bảo đảm mọi vùng đọc thấy event ngay.

**Không dùng CP/AP để suy đoán RPO/RTO.**

### 13.2. Atomicity khác linearizability

Một key có linearizable increment không tự bảo đảm hai key cùng được update hoặc cùng rollback. Nếu giảm tồn kho một SKU và ghi Order ở hai database khác nhau, cần transaction được hỗ trợ hoặc saga/compensation.

### 13.3. Availability kỹ thuật khác khả năng hoàn thành nghiệp vụ

Search API trả HTTP 200 với dữ liệu cũ vẫn là một endpoint hoạt động, nhưng khách bấm “Mua” có thể bị checkout từ chối. Nếu search dùng dữ liệu cũ để cấp phát luôn, hệ có thể tạo oversell.

Hãy theo dõi **business completion rate** bên cạnh HTTP availability.

## 14. Xung đột ở hệ ưu tiên tiếp nhận ghi: cái giá nằm ở đâu?

Một hệ cho phép hai vùng chấp nhận write độc lập khi không liên lạc được có thể tránh chặn người dùng ngay lúc partition. Nhưng sau khi mạng lành, nó phải giải quyết những phiên bản không có quan hệ nhân quả rõ ràng.

### 14.1. Last-write-wins không phải “không mất dữ liệu”

Ví dụ:

~~~~text
Ban đầu:
  Customer.shippingAddress = "A"

Region VN:
  a: address = "B"

Region EU:
  b: address = "C"

Hai write concurrent, cả hai ACK ở vùng riêng.
~~~~

Nếu resolver dùng last-write-wins, một write có thể bị loại khỏi **giá trị cuối**. Hệ có thể hội tụ thành B hoặc C theo quy tắc version/timestamp, nhưng điều đó **không chứng minh lựa chọn đúng ý người dùng**.

Clock skew càng làm một timestamp-based rule khó dự đoán.

### 14.2. Multi-value và resolver nghiệp vụ

Hệ có thể lưu hai sibling versions:

~~~~json
{
  "addressCandidates": [
    { "value": "B", "version": "v-vn-12" },
    { "value": "C", "version": "v-eu-9" }
  ],
  "needsResolution": true
}
~~~~

Đây là trạng thái **có thể phục vụ read nhưng chưa có một địa chỉ shipping đã quyết định**. UX cần yêu cầu người dùng chọn hoặc áp dụng policy nghiệp vụ.

### 14.3. CRDT chỉ giải quyết những phép toán có đại số phù hợp

Một bộ đếm lượt thích, tập hợp tag hoặc cấu trúc hợp tác có thể được mô hình hóa bằng CRDT để các replica merge xác định.

Nhưng:
- Một PN-counter có thể âm.
- Add-wins/remove-wins có ngữ nghĩa khác nhau.
- Update duplicate vẫn cần hiểu event identity tùy implementation.
- Một số bất biến như **số vé còn lại không âm trên toàn hệ** không tự đúng chỉ vì counter hội tụ.

**Convergence không đồng nghĩa không vi phạm invariant trong lúc partition.**

### 14.4. Escrow/bounded counter

Với tồn kho 100 đơn vị, có thể cấp trước quyền bán:

~~~~text
Region VN:   40 quyền
Region EU:   35 quyền
Region US:   25 quyền
---------------------
Total:      100 quyền
~~~~

Mỗi vùng được bán trong giới hạn quyền đã cấp, ngay cả khi mất kết nối tạm thời. Muốn làm đúng phải bảo vệ **quyền cấp/chuyển/thu hồi**, không phát hai lần và không “sao chép” quyền khi failover.

Escrow là một thiết kế chuyên biệt để cải thiện **khả năng hoạt động cục bộ trong khi giữ một bất biến**, không phải bằng chứng CAP sai: hệ đã **đặt trước/giới hạn tài nguyên được quyền tiêu dùng**, nên những write không đủ quyền vẫn phải chờ hoặc bị từ chối.

## 15. Multi-region khiến “availability” và “consistency” trở thành câu hỏi theo địa lý

Giả sử ba vùng VN, EU, US:

~~~~text
VN <----replication----> EU
 \                        /
  \------ replication ---/
             US
~~~~

Có thể phân vùng mạng chỉ giữa VN–EU, nhưng VN vẫn trao đổi với US và EU cũng trao đổi với US. Nếu cơ chế routing/protocol có thể dùng US làm đường trao đổi, **không được kết luận có hai nhóm hoàn toàn bị cô lập** chỉ từ một link VN–EU bị lỗi.

### 15.1. Network topology thực quan trọng

Cần đo:
- Connectivity matrix giữa các node/region.
- Hướng đi được và hướng về được.
- Packet loss, jitter và delay.
- Link giữa app và database, không chỉ giữa replica.
- Vị trí leader và quorum voters.
- Request routing sau failover.

Một sơ đồ hai bán cầu A/B có ích để chứng minh CAP, nhưng sự cố production thường là **partial reachability**, không phải cắt đôi đẹp đẽ.

### 15.2. Local read, global write

Một chiến lược có thể:
- Cho phép **local eventual reads** từ replica gần.
- Gửi **strong writes** tới leader/quorum.
- Dùng **session token** bảo vệ read-your-writes.
- Chờ index async cập nhật cho full-text.

Trong partition, local read có thể vẫn phục vụ trong khi global write bị chặn. Đây là một **quyết định hợp đồng theo operation**.

### 15.3. Global strong constraints có chi phí

Nếu muốn bảo đảm không hai vùng cùng bán một sản phẩm cuối, cần một cơ chế quyết định đúng. Giải pháp có thể là:
- Một primary/leader hoặc quorum có thẩm quyền.
- Transaction/conditional write đủ mạnh.
- Phân bổ inventory rights trước.
- Đóng băng xác nhận bán tại vùng không thể bảo vệ invariant.

Không có “AP flag” nào cho phép **hai bên tự xác nhận bán cùng đơn vị cuối** mà vẫn bảo đảm mỗi đơn vị chỉ bán một lần theo lịch sử toàn cục.

## 16. Ví dụ một sản phẩm NoSQL không mang một nhãn duy nhất

### 16.1. MongoDB

MongoDB có replication, election, write/read concerns, transaction và các mode đọc khác nhau. Một số read có thể được thực hiện trên primary hoặc secondary theo lựa chọn; secondary có thể lag. Một transaction với concerns được cấu hình phù hợp có hợp đồng khác với **một read từ secondary**.

Vì thế, việc nói “MongoDB là CP” rồi suy ra mọi read đều linearizable hoặc mọi transaction đa vùng đều nhất quán theo cùng ngữ nghĩa là không đủ. Cần xét **lệnh, collection, read preference, read concern, write concern, topology và failover**.

### 16.2. Cassandra

Cassandra có consistency levels khác nhau cho read/write và cơ chế replica/repair. Một ứng dụng có thể chọn mức nhanh hơn nhưng có nguy cơ đọc cũ, hoặc mức yêu cầu nhiều replica hơn nhưng dễ timeout khi network bị partition.

Tuy nhiên:
- Một consistency level không tự chứng minh toàn hệ serializable.
- R+W>N là trực giác giao quorum, chưa đủ cho mọi concurrent history.
- LWT/CAS có ngữ nghĩa khác write thông thường.
- Counter và multi-partition workflows cần xét riêng.

Không đánh giá mọi workload Cassandra chỉ bằng một chữ AP.

### 16.3. DynamoDB

DynamoDB có **strongly consistent reads** cho những đường đọc bảng thích hợp theo phạm vi dịch vụ, đồng thời **Global Secondary Index** được duy trì bất đồng bộ và chỉ hỗ trợ eventual reads theo hợp đồng đó. Transaction và global replication còn có ngữ nghĩa riêng.

Một ứng dụng có thể:
- Dùng UpdateItem có condition ở bảng chính để giữ invariant.
- Dùng GSI eventual để tìm candidate.
- Kiểm tra lại source trong checkout.

Tính chất tổng thể phụ thuộc **đường truy cập**, không phải một nhãn cho mọi dữ liệu của dịch vụ.

### 16.4. Redis

Redis thường xử lý một lệnh nguyên tử tại instance, nhưng replication, failover và persistence có bảo đảm riêng. **Atomic INCR** không chứng minh write được leader ACK sẽ xuất hiện ở mọi replica sau failover theo bất kỳ cấu hình nào; cũng không tự bảo đảm multi-node transaction.

Một ứng dụng dùng Redis cho cache eventual và database khác cho ledger có thể đưa ra hai hợp đồng rất khác nhau.

### 16.5. Search/read models

OpenSearch/Elasticsearch hoặc một index bất đồng bộ có thể cho kết quả tìm kiếm trễ hơn source commit vì update pipeline và refresh. Đó là **freshness của read model**, không phải bằng chứng tất cả write ở database nguồn đã từ bỏ linearizability.

**Với mọi sản phẩm:** thay nhãn marketing bằng bảng **API → consistency mode → scope → failure behavior → durability → cost**.

## 17. Phân biệt phân vùng với sự cố thường gặp khác

Một hiện tượng latency cao có thể có nguyên nhân:

| Triệu chứng | Có nhất thiết là partition CAP? | Cần kiểm tra |
| --- | --- | --- |
| SSD/compaction làm write p99 tăng | Không | Disk I/O, queue, write stalls |
| Leader election | Có thể đi cùng sự cố mạng hoặc crash | Term, quorum, failover |
| Network delay tăng từ 10 ms lên 2 s | Có thể trở thành indistinguishable với failure trong deadline | RTT, timeout policy, path |
| Search index chậm 5 giây | Không nhất thiết | Broker lag, refresh và indexer |
| Một node crash | Failure khác với hai node còn sống nhưng không liên lạc | Quorum và replica placement |
| Two-way packet loss giữa hai vùng | Có thể tạo partition | Connectivity matrix |
| DNS trả sai endpoint | Có thể gây route failure | Resolver, proxy, client configuration |
| Rate limit/throttling | Không | Provisioned capacity, hot key |
| Application bug trả dữ liệu sai | Không | Logic, cache invalidation, isolation |
| Clock skew | Không nhất thiết | Lease, LWW, timestamp/order |

**Không dùng CAP làm lời giải thích chung cho mọi sự cố NoSQL.** Nó là mô hình chỉ rõ một dạng giới hạn, không phải công cụ thay thế profiling và observability.

### 17.1. Network timeout không chứng minh request chưa commit

Khi client gửi COMMIT rồi timeout, hệ có thể đã commit và làm mất ACK. Client nên giữ trạng thái **UNKNOWN** và retry/reconcile với **cùng operationId** theo hợp đồng.

Phân tích CAP không giải quyết thay **idempotency** hoặc khả năng tra commit outcome.

### 17.2. Một request bị chặn không chứng minh cả database “CP”

Một write thiếu quorum có thể bị chặn, nhưng một read eventual khác được phục vụ; hoặc một partition khác của dataset vẫn hoạt động. Cần xem **loại request** và **tập node liên quan**.

## 18. Xây một bảng quyết định thay cho tam giác marketing

Trước khi chọn storage, lập bảng ở mức **hành động nghiệp vụ**:

| Hành động | Có được đọc cũ? | Có được ACK write ở vùng cô lập? | Bất biến | Hành vi khi thiếu điều kiện |
| --- | --- | --- | --- | --- |
| Feed timeline | Có, trong hạn cho phép | Có thể nhận event cục bộ | Giữ dependency nếu hứa causal | Render stale có nhãn |
| Đọc product listing | Có | Không áp dụng | Chỉ để khám phá | Trả cache hoặc degrade |
| Đặt hàng 1 SKU cuối | Không cho quyết định cuối | **Không**, trừ khi có quyền escrow hợp lệ | Không oversell | PENDING/REJECTED hoặc wait |
| Trừ ví | Không | Không xác nhận khi thiếu authority | Không double debit | UNKNOWN rồi reconcile |
| Ghi metric | Có thể | Có thể enqueue durable local | Không mất vượt RPO cho phép | Queue/ack theo hợp đồng |
| Thay đổi quyền admin | Không cho phép sai policy | Có thể lưu intent nhưng chưa hiệu lực toàn cục | Authorization safety | Chặn quyết định nhạy cảm |
| Comment sau Post | Có độ trễ nhưng không đảo nhân quả | Có thể buffer tới khi dependency visible | Causal ordering | Wait/buffer/fallback |

Nên bổ sung các cột:
- **Source of truth**.
- **Atomicity/isolation scope**.
- **Failure model**.
- **Write/read concern**.
- **Timeout và retry semantics**.
- **SLO freshness/p99**.
- **Replica/region coverage**.
- **Reconciliation owner**.
- **RPO/RTO**.
- **Đường degrade được người dùng chấp nhận**.

Đây là thông tin mà nhãn CA/CP/AP không biểu diễn.

## 19. Phân tích SLO: hệ vẫn “available” nhưng sai nghiệp vụ?

Một dashboard hiển thị:

~~~~text
HTTP success:                 99.98%
Search response p99:          90 ms
Checkout response p99:       120 ms
Wrong confirmed orders:        12
Duplicate charge incidents:     2
~~~~

Chỉ nhìn HTTP success rate có thể cho rằng dịch vụ rất tốt. Nhưng **wrong confirmed orders** là lỗi nghiêm trọng dù API phản hồi nhanh.

Hệ phân tán cần theo dõi ít nhất ba chiều:

1. **Availability vận hành:** tỷ lệ request được đáp ứng theo contract.
2. **Freshness/consistency:** những request đã đáp ứng có quan sát trạng thái phù hợp không?
3. **Business safety:** invariant có bị vi phạm không?

### 19.1. Error budget phải phân biệt loại lỗi

Một API có thể có:
- 503 vì không đạt quorum: giảm availability nhưng giữ safety.
- 200 với dữ liệu stale: có thể phù hợp với search, nhưng sai nếu là điểm kiểm tra tồn kho.
- 202 PENDING: hợp lệ nếu request chỉ hứa nhận ý định xử lý.
- 200 CONFIRMED khi stock chưa thực sự được giữ: sai contract nghiêm trọng.

**Đừng đổi 503 sang 200 để làm đẹp SLO mà không thay đổi và công bố semantics.**

### 19.2. Các SLI nên đo riêng

| SLI | Định nghĩa mẫu |
| --- | --- |
| Strong-operation success ratio | Tỷ lệ thao tác yêu cầu linearizable semantics hoàn tất đúng trong deadline |
| Weak-read freshness | p99 thời gian từ source commit đến index query-visible |
| RYW violation count | Lần đọc trong session trả view cũ hơn trạng thái đã ACK |
| Conditional-invariant violations | Số lần stock âm hoặc một slot có hai holder |
| Unknown-commit age | Tuổi operation chưa xác minh commit sau timeout |
| Minority partition rejection | Số write không đạt quorum ở vùng thiểu số |
| Conflict resolution lag | Thời gian reconcile hai bản concurrent |
| Recovery convergence time | Thời gian các replica hội tụ sau khi mạng lành |
| Cross-region p99 | Độ trễ theo vùng và loại consistency mode |
| Data-loss RPO | Phần dữ liệu có thể mất theo kịch bản failover đã công bố |

Không nên dùng một SLI **“DB available 99,9%”** để thay thế mọi yêu cầu trên.

## 20. Thiết kế API Java theo consistency contract

Tầng service nên diễn tả **ý định nghiệp vụ**, không chỉ gọi một hàm DB chung với tham số boolean useStrongConsistency.

Ví dụ Java 21 mô hình hóa loại đường đọc:

~~~~java
public enum ReadMode {
    EVENTUAL_FOR_DISCOVERY,
    CAUSAL_FOR_SESSION,
    AUTHORITATIVE_FOR_DECISION
}

public record ReadRequirement(
        ReadMode mode,
        String requiredSessionToken
) {}

public record ProductView(
        String productId,
        long priceMinor,
        boolean availableHint,
        long sourceVersion
) {}
~~~~

Các kiểu này là mô hình của ứng dụng, không phải API chuẩn của mọi NoSQL. Chúng buộc người viết controller **tuyên bố read này dùng để làm gì**.

### 20.1. Search và checkout phải có đường đọc khác

Một thiết kế tầng ứng dụng:

~~~~java
public final class ProductService {
    private final SearchIndex search;
    private final ProductAuthority authority;

    public ProductService(
            SearchIndex search,
            ProductAuthority authority
    ) {
        this.search = search;
        this.authority = authority;
    }

    // Đường khám phá: dữ liệu có thể trễ theo hợp đồng.
    public ProductView searchPreview(String productId) {
        return search.findPreview(productId);
    }

    // Đường ra quyết định: phải đọc/kiểm tra nguồn có thẩm quyền.
    public ProductView checkoutPrice(String productId) {
        return authority.readForDecision(productId);
    }
}
~~~~

Đây là **mã khung**: các interface chưa được định nghĩa và chưa đủ để compile. Điều quan trọng là **readForDecision** phải thật sự dùng read contract phù hợp; một method có tên “strong” nhưng trỏ đến cache stale không cung cấp tính nhất quán mạnh.

### 20.2. Bảo vệ bất biến tồn kho tại lệnh ghi

Một primitive:

~~~~java
public interface InventoryAuthority {
    ReservationOutcome reserveIfAvailable(
            String sku,
            long quantity,
            String operationId
    );
}

public sealed interface ReservationOutcome {
    record Confirmed(String reservationId)
            implements ReservationOutcome {}

    record Rejected(String reason)
            implements ReservationOutcome {}

    record Unknown(String operationId)
            implements ReservationOutcome {}
}
~~~~

Hệ phải đảm bảo:
- Quantity được validate.
- Condition **available >= quantity** và decrement nằm trong atomic/transaction scope hỗ trợ.
- Cùng operationId không tạo hai reservation khi retry.
- Commit timeout dẫn đến UNKNOWN và reconciliation.
- Những request không đạt safety precondition không được chuyển thành CONFIRMED chỉ để phục vụ trong partition.

### 20.3. Một chiến lược degrade có kiểm soát

~~~~text
readProductForListing():
    try indexed read
    if index available:
        return ProductPreview(stalenessHint)
    else:
        return cachedPreview if within UX policy
        or unavailable

reserveStock():
    try authoritative conditional transaction
    if committed:
        return CONFIRMED
    if definite business conflict:
        return REJECTED
    if timeout/unknown:
        return UNKNOWN with operationId
    if missing quorum:
        do not fake confirmation
~~~~

Cấu trúc cho phép ứng dụng có **availability linh hoạt ở đường khám phá** nhưng giữ **safety ở đường giao dịch**. Đó là một quyết định sản phẩm, không phải “chọn CP” cho toàn bộ service.

## 21. Mô hình thất bại cần bao gồm crash, partition và recovery

Một thiết kế thực tế không chỉ chịu một phân vùng hoàn hảo. Cần kết hợp:

- Mất link A↔B.
- Mất một chiều A→B hoặc B→A.
- Leader crash giữa commit.
- Replica restart với snapshot cũ.
- Client disconnect sau gửi write nhưng trước ACK.
- Partition heal rồi log replay.
- Message trùng/sai thứ tự.
- Disk I/O chậm hoặc full.
- Quorum membership đổi khi failover.
- Search index/CDC lag sau khi source phục hồi.

Những lỗi này tương tác nhau. Ví dụ khi partition lành, **replication replay** có thể làm tăng CPU/I/O, khiến p99 cao thêm dù network đã bình thường.

### 21.1. Safety và liveness

**Safety:** Điều xấu không bao giờ xảy ra, ví dụ hai booking cùng giữ một slot.

**Liveness:** Một thao tác được yêu cầu cuối cùng có thể hoàn thành dưới các điều kiện phù hợp.

Trong partition:
- Để giữ safety, hệ có thể phải **chờ/từ chối** một số thao tác.
- Để tiếp tục đáp ứng, hệ có thể phải **giảm một số bảo đảm** và xử lý conflict về sau.

Không đánh giá liveness chỉ bằng success trong 30 giây; cũng không đánh giá safety chỉ bằng counter cuối cùng có vẻ đúng. Cần **lịch sử thao tác và invariant**.

## 22. Kiểm thử CAP bằng fault injection

Không nên nhận định “cụm này AP” chỉ vì một lần tắt một node mà API vẫn trả 200. Thử nghiệm phải tạo được **phân vùng giữa những node còn sống**, điều khiển request routing và biết các thao tác nào đã ACK.

### 22.1. Bước chuẩn bị

1. Xác định topology (node, replica, vùng, leader, quorum).
2. Ghi rõ read/write contract của từng endpoint.
3. Dựng tập dữ liệu với giá trị/version ban đầu xác định.
4. Ghi operationId, invoke time, response time và result cho mọi request.
5. Phân biệt request **completed, rejected, timeout, unknown**.
6. Theo dõi log/term/epoch, replica offset và network connectivity.
7. Chạy trong môi trường có thể cô lập an toàn; **không phá kết nối production tùy tiện**.

### 22.2. Ma trận sự cố

| Kịch bản | Thao tác | Điều cần chứng minh |
| --- | --- | --- |
| Healthy cluster | Strong read/write bình thường | C+A có thể cùng đạt khi không partition |
| Partition 2–1 với N=3 | Write cả nhóm đa số và thiểu số | Chỉ đường đủ điều kiện commit được ACK theo contract |
| Partition giữa hai vùng active | Concurrent write cùng key | Conflict hoặc blocking đúng semantics |
| Strong read ở minority | Read sau write majority ACK | Không trả giá trị cũ dưới nhãn strong |
| Eventual read ở minority | Read tương tự | Nếu trả stale, API phải có semantics cho phép |
| Client chuyển vùng | Read-your-writes sau khi đổi replica | Không đi lùi nếu session guarantee được hứa |
| Lost commit ACK | Ngắt phản hồi sau DB commit | Retry same operationId không duplicate |
| Sloppy quorum/handoff | Node thay thế nhận write | Đọc/khôi phục đáp ứng hợp đồng thực |
| Heal partition | Reconcile versions | Hội tụ đúng quy tắc; không mất update trái hợp đồng |
| Concurrent delete/update | Một bên delete, một bên update | Tombstone/conflict rule đúng |
| Leader switch | Hai node tưởng là leader | Fencing/term ngăn split-brain write |
| Strong inventory | Hai vùng cùng reserve last item | Không double confirm |
| Search lag | Source write, index thiếu | Checkout không dựa vào index stale |
| Slow link thay vì link chết | RTT tăng nhiều lần | Timeout/failover không gây sai dữ liệu |
| Quorum membership change | Thêm/bớt voter khi phân vùng | Không tạo hai quorum không giao đúng protocol |
| Recovery under load | Dồn replay/repair traffic | p99, backlog và headroom có giới hạn |

### 22.3. Một bài test linearizability tối thiểu

Giả sử register x:

~~~~text
Initial x=0.

1. Gây partition A|B.
2. Gửi WRITE x=1 tới A.
3. Nếu WRITE trả SUCCESS:
     sau thời điểm ACK, gửi READ x tới B.
4. Nếu READ trả SUCCESS:
     kiểm tra giá trị và history.
5. Nếu READ timeout/reject:
     ghi nhận availability tradeoff.
6. Nếu WRITE không thành công:
     không coi nó là write committed để assert read.
~~~~

Để kiểm tra tổng quát hơn, dùng **history recorder và linearizability checker** dựa trên invoke/return intervals, chứ không chỉ so một lần read/write. Các thao tác timeout phải được xử lý cẩn thận vì kết quả của chúng có thể UNKNOWN, không được tùy tiện ghi là failed.

### 22.4. Đừng dùng đồng hồ tường làm bằng chứng duy nhất

Khi hai client ở hai máy có clock skew, timestamp log không nhất thiết phản ánh thứ tự thực. Cần:
- Đồng bộ clock khi có thể.
- Dùng điều khiển test để biết Write ACK đã xảy ra **trước khi** gửi Read.
- Giữ order theo từng client.
- Ghi invoke/return cùng unique operationId.
- Đối soát trạng thái sau recovery.

Một phép thử mà Write và Read chồng lấp có thể cho kết quả cũ mà **không tự vi phạm linearizability**.

## 23. Benchmark đánh đổi latency, availability và freshness

Một cấu hình giả định:

~~~~yaml
experiment: cap-not-pick-two
topology:
  regions: [VN, EU, US]
  replicas: 3
  leaderElection: enabled
workload:
  offeredWritesPerSecond: 5000
  offeredReadsPerSecond: 20000
  operations:
    - eventual_product_search
    - authoritative_price_read
    - conditional_inventory_reserve
    - idempotent_order_create
    - telemetry_append
faults:
  - healthy
  - region_partition
  - asymmetric_packet_loss
  - slow_inter_region_link
  - leader_failover
  - lost_write_ack
  - replay_after_heal
measure:
  - per_endpoint_success_and_rejection_rate
  - p50_p95_p99_per_consistency_mode
  - stale_read_version_and_age
  - linearizability_history
  - business_invariant_violations
  - unknown_commit_age
  - replica_lag_and_recovery_time
  - conflict_resolution_latency
  - queue_backlog_and_disk_IO
~~~~

Đây là **đặc tả minh họa**, không phải lệnh có thể chạy trực tiếp. Tùy sản phẩm, cấu hình leader election, quorum và consistency mode có thể khác nhau hoặc do nhà cung cấp quản lý.

### 23.1. Kết quả giả định

| Trạng thái | Strong reserve success | Eventual search success | Strong read p99 | Search p99 | Lỗi cần xem |
| --- | ---: | ---: | ---: | ---: | --- |
| Healthy | 99,99% | 99,99% | 75 ms | 45 ms | Không có partition |
| Partition, majority side | 99,7% | 99,9% | 110 ms | 70 ms | Failover/retry |
| Partition, minority side | 0% trong vùng cô lập | 99,0% | Timeout/503 | 55 ms | Search có thể stale |
| Sau khi heal | 99,8% | 99,9% | 140 ms | 95 ms | Replay/repair backlog |

**Toàn bộ số liệu giả định.** Đọc bảng phải biết traffic được route thế nào và “success” được định nghĩa ra sao:
- 0% strong reserve ở minority có thể là **chủ động giữ invariant**, không phải lỗi correctness.
- 99% search success có thể vẫn chứa dữ liệu cũ; cần **freshness SLI**.
- Strong read p99 chỉ tính request thành công có thể bỏ qua timeout; phải báo **error rate cùng latency**.
- Sau khi heal, hệ còn có thể phải reconcile conflict và chạy repair.

### 23.2. SLI nên tách theo endpoint

Ví dụ các chỉ số:

\[
Availability_{\text{strong}} =
\frac{\text{Strong operations hoàn tất đúng theo contract}}
{\text{Tổng strong operations được yêu cầu}}
\]

\[
Freshness_{5s} =
\frac{\text{Các thay đổi source query-visible trong 5 giây}}
{\text{Tổng thay đổi hợp lệ theo tập đánh giá}}
\]

\[
InvariantViolationRate =
\frac{\text{Số action vi phạm bất biến}}
{\text{Tổng action liên quan}}
\]

Các mẫu số cần định nghĩa rõ: request timeout, retry, operationId trùng và những thay đổi chưa visible không được **tự loại bỏ** khỏi thống kê chỉ vì khó đo.

## 24. Runbook khi cụm phân vùng và API có hành vi khác nhau

### Bước 1 — Xác nhận có partition thật

- Kiểm tra connectivity giữa **các node còn sống**.
- Xác định hướng mạng bị chặn, latency/packet loss.
- Tìm leader/quorum/term hiện tại.
- Phân biệt client routing failure với replica partition.
- Kiểm tra ổ đĩa, CPU, GC và network saturation trước khi quy mọi timeout cho CAP.

### Bước 2 — Xác định operation bị ảnh hưởng

- Strong read/write hay eventual search?
- Đường nào phải giữ invariant không âm/không trùng?
- Có client nào đã nhận ACK rồi request sau đọc cũ không?
- Có thao tác đang UNKNOWN sau commit timeout không?
- Vùng nào còn đủ quorum/authority?

### Bước 3 — Bảo vệ nghiệp vụ quan trọng

- Không xác nhận checkout nếu chưa giữ stock đúng contract.
- Không debit lại khi payment outcome UNKNOWN.
- Với quyền truy cập nhạy cảm, fail closed hoặc dùng nguồn quyết định phù hợp.
- Cho phép read stale ở những endpoint đã **công bố rõ**.
- Trả PENDING/UNKNOWN nếu chỉ có ý định cục bộ chưa được commit tại authority.
- Bảo toàn operationId và log dấu vết để đối soát.

### Bước 4 — Khôi phục mà không tạo xung đột mới

- Xác nhận node nào có quyền leader; dùng fencing/term theo protocol.
- Không ép hai leader cùng nhận write.
- Không xóa tombstone/hinted handoff/repair metadata tùy tiện.
- Cho replication bắt kịp và giải quyết concurrent writes theo quy tắc.
- Đối soát trạng thái inventory/ledger/order.
- Cảnh giác **retry storm** từ client/gateway sau khi mạng hồi phục.

### Bước 5 — Đánh giá kết quả thật

- Có linearizability/invariant violation không?
- Có dữ liệu stale ngoài hợp đồng không?
- Số operation UNKNOWN còn lại bao nhiêu?
- Time-to-recovery và conflict resolution lag?
- SLO availability, p99, freshness bị ảnh hưởng thế nào?
- Có cần thay routing, quorum placement, retry/idempotency hoặc degrade mode không?

**Không kết luận “đây là hành vi CP bình thường” rồi bỏ qua việc điều tra những endpoint đã công bố một hợp đồng khác.**

## 25. Các câu nói dễ sai và cách sửa

| Câu nói quá đơn giản | Cách diễn đạt có ích hơn |
| --- | --- |
| “CAP bắt chọn hai trong ba.” | Khi partition khiến node thiếu thông tin, không thể bảo đảm đồng thời linearizability và CAP availability cho mọi operation. |
| “CP nghĩa là không available.” | Những operation thiếu quorum có thể bị chặn, còn operation/vùng khác vẫn phục vụ. |
| “AP nghĩa là luôn available.” | Một số operation có thể tiếp tục trong partition dưới contract yếu hơn; crash/capacity/routing vẫn gây lỗi. |
| “CA nghĩa là không có partition.” | CA chỉ hữu ích dưới giả định không partition hoặc mô hình lỗi hạn chế; mạng không bảo đảm như vậy mãi. |
| “Consistency CAP là ACID C.” | CAP C gắn với linearizability, khác bất biến nghiệp vụ ACID. |
| “AP không có consistency.” | Có thể vẫn có eventual, causal, per-key order, monotonic sessions. |
| “CP không có eventual read.” | Cùng hệ có thể cung cấp nhiều read mode theo đường truy cập. |
| “Quorum là linearizable.” | Cần protocol đầy đủ: membership, version, leader/ballot, concurrent operations, read path. |
| “R+W>N là đủ trong mọi hệ.” | Chỉ là giao tập hợp trong một mô hình; sloppy quorum/dynamic membership và protocol cụ thể quan trọng. |
| “Timeout chứng minh write thất bại.” | Có thể đã commit và ACK mất; giữ UNKNOWN, reconcile bằng operationId. |
| “Hai replica trả khác nhau là database bị hỏng.” | Có thể là hành vi eventual hợp lệ trong phạm vi đã công bố, nhưng không hợp lệ nếu strong read. |
| “CAP cho biết performance.” | CAP không định lượng p99; đo RTT, contention, cache và PACELC-like tradeoffs. |
| “Chọn AP là tránh coordination miễn phí.” | Phải trả chi phí conflict resolution, anti-entropy, reconcile và invariant design. |
| “Strong consistency giải quyết oversell.” | Còn cần conditional guard/transaction và scope invariant phù hợp. |
| “Search cache còn hoạt động nghĩa hệ an toàn.” | Checkout/security vẫn cần source có thẩm quyền. |
| “Availability chỉ là HTTP 200.” | Response phải đúng contract; 200 sai nghiệp vụ không phải thành công. |
| “Mọi endpoint database là CP hoặc AP.” | Cần mô tả per-operation, per-read-mode, per-partition và failure state. |
| “Không partition thì không còn đánh đổi.” | Latency, durability, isolation, cost và freshness vẫn là những lựa chọn. |
| “Causal consistency đủ để thu hồi quyền ngay toàn cầu.” | Causal không đòi real-time visibility giữa client độc lập; policy có thể cần mạnh hơn. |
| “CRDT giải quyết mọi bất biến không cần coordination.” | CRDT giúp hội tụ cho phép toán phù hợp; quota/stock cứng cần thiết kế thêm. |

## 26. Bài tập tình huống: thương mại điện tử ba vùng

Một hệ thương mại điện tử có:
- **VN, EU, US**; mỗi vùng có client API.
- **10 triệu sản phẩm**.
- **20.000 lượt search/s** và **5.000 hành động checkout/s** giờ cao điểm.
- Search index được cập nhật bất đồng bộ từ Product Store.
- Inventory có một authority/conditional transaction trên mỗi SKU hoặc một chiến lược phân bổ quyền phù hợp.
- Payment service dùng provider bên ngoài với merchant operationId.
- Đơn hàng được đẩy sang báo cáo qua outbox/CDC.
- Một phần dữ liệu người dùng phải giữ trong vùng địa lý theo chính sách.
- Mục tiêu tìm kiếm: p99 dưới 200 ms, cho phép trễ dữ liệu tối đa theo SLO riêng.
- Tồn kho: **không xác nhận bán quá số lượng thực**, kể cả trong partition.
- Payment: **không debit trùng cùng ý định**.
- Khi mạng giữa các vùng lỗi, API cần báo trạng thái trung thực.

### Phần A — Phân loại C/A/P theo định nghĩa chuẩn

Giải thích:
1. CAP C có nghĩa gì đối với một register stock?
2. CAP A có nghĩa gì đối với request ở node không hỏng?
3. Tại sao phân vùng mạng không phải một tính năng có thể bỏ qua bằng cấu hình “CA”?
4. Vì sao availability SLO 99,99% không phải cùng định nghĩa với CAP A?

### Phần B — Hai replica không thể trao đổi thông tin

Ban đầu x=0. Vùng A ACK write x=1. Sau ACK, vùng B không nhận được thông tin và một client bắt đầu strong read x tại B.

Hãy liệt kê các lựa chọn của B: **trả 0, chờ, trả lỗi, route nơi khác, trả UNKNOWN**. Đối với mỗi lựa chọn, xác định nó có thực hiện read theo cùng contract không và đánh đổi consistency/availability ra sao.

### Phần C — Quorum và phân vùng 3 node

Giả sử N=3, W=2, R=2 trong một mô hình quorum ổn định. A/B nằm cùng phía, C bị cô lập.

1. Nhóm nào có thể đáp ứng write quorum?
2. C có thể tự ACK một strong write không?
3. Nếu C trả stale read, request đó có thể được gọi là strong read không?
4. Vì sao R+W>N không tự chứng minh linearizability nếu có sloppy quorum hoặc leader failover sai?
5. Nếu ứng dụng chạy eventual read tại C nhưng checkout cần strong write, cần đặt hai contract thế nào?

### Phần D — Checkout và search

Search ở EU cho biết còn **1** sản phẩm. Một khách VN đã giữ sản phẩm cuối thành công tại inventory authority, nhưng index EU chưa cập nhật.

1. EU search có thể trả “còn hàng” theo contract eventual không?
2. Checkout EU phải làm gì trước khi CONFIRMED?
3. Có được trả HTTP 200 CONFIRMED nếu chỉ xếp request vào queue cục bộ không?
4. Thiết kế UI cho PENDING/OUT_OF_STOCK/UNKNOWN.
5. Đặt metric **stale stock display** khác **oversell invariant violation** thế nào?

### Phần E — Partition và retry

Payment provider đã xử lý capture, nhưng checkout mất ACK.

1. Client có được tạo paymentOperationId mới để retry không?
2. Dùng merchant reference/idempotency key thế nào?
3. Khi chưa biết kết quả, UI nên báo trạng thái nào?
4. CAP có trực tiếp giải quyết vấn đề mất ACK hoặc exactly-once không?

### Phần F — Xung đột AP

Người dùng đổi địa chỉ giao hàng ở VN và EU trong khi hai vùng bị cô lập. Hai write được ACK.

So sánh:
- Last-write-wins.
- Multi-value siblings.
- Hợp nhất theo chính sách nghiệp vụ.

Đâu là khả năng mất ý định người dùng? Cần audit/merge/version nào? Vì sao eventual convergence không có nghĩa hai thay đổi đều được giữ nguyên?

### Phần G — PACELC và latency

Không có partition. Strong price read từ VN phải liên hệ với leader vùng xa; eventual listing đọc local replica. Hãy lập bảng **RTT, p99, freshness, business risk và cost** cho hai đường. Vì sao không thể kết luận ngay strong read chậm hơn eventual read 10 lần chỉ từ tên consistency?

### Phần H — Fault injection và dashboard

Thiết kế tối thiểu tám kịch bản:
1. Healthy.
2. Partition 2–1.
3. Read từ minority sau majority ACK.
4. Dual active write xung đột.
5. Network delay lớn nhưng không đứt hoàn toàn.
6. Lost ACK sau commit.
7. Leader failover/split-brain attempt.
8. Heal partition và conflict reconciliation.
9. Search lag trong checkout.
10. Replica restart từ snapshot cũ.

Với mỗi test, chỉ ra:
- Operation nào được gửi?
- ACK nào đã nhận?
- Contract nào được yêu cầu?
- Kết quả nào là hợp lệ?
- Đo latency, errors, freshness, unknown operations, conflict và invariant ra sao?

### Phần I — Viết câu trả lời cho kiến trúc sư

Một đồng nghiệp kết luận:

> “Chúng ta chọn AP vì muốn uptime cao, nên dùng dữ liệu cache để xác nhận thanh toán. Hệ CP thì chắc chắn không dùng được cho người dùng đa vùng.”

Hãy phản biện bằng định nghĩa CAP và đề xuất **một kiến trúc phân tách search eventual, checkout authoritative, payment idempotent và outbox async**. Nêu rõ hành vi khi vùng mất quorum, thay vì chỉ gọi hệ thống “hybrid”.

### Gợi ý hướng giải

Một giải pháp hợp lý có thể:
- Cung cấp **eventual search** với freshness SLO và last-updated khi cần.
- Giữ **conditional/transactional inventory authority** hoặc quyền escrow được cấp phát an toàn.
- Dùng **operationId** để xử lý retry và UNKNOWN commit.
- Đồng bộ index/báo cáo qua **outbox/CDC**.
- Khi thiếu quorum, trả **PENDING/temporarily unavailable** cho checkout thay vì giả vờ CONFIRMED.
- Sau partition, chạy **reconcile** và kiểm tra stock/ledger invariant.
- Đo **availability, p99, stale reads và business safety** theo từng endpoint.

Không có một nhãn **CP** hay **AP** duy nhất mô tả đầy đủ kiến trúc này.

## 27. Checklist câu hỏi trước khi ra quyết định

Trước khi chốt một hệ NoSQL vì “CAP”, hãy trả lời được:

1. **Cụ thể C là gì?** Linearizable read/write, causal, snapshot hay consistency của transaction?
2. **A đo theo nghĩa nào?** CAP availability hay SLO 99,95% trong 500 ms?
3. **Partition nào được xét?** Hai replica, ba vùng, asymmetric link, client-to-DB hay leader-to-follower?
4. **Node nào còn sống và nhận request?**
5. **Thao tác nào vẫn được phép phục vụ khi thiếu quorum?**
6. **Read stale có được công bố rõ trong API không?**
7. **Write được ACK tại mốc nào?** Memory, WAL, quorum, consensus commit hay outbox enqueue?
8. **Strong read có dùng đúng đường primary/quorum không?**
9. **Cách xử lý concurrent write và delete là gì?**
10. **Có bảo vệ bất biến tồn kho/quyền/payment riêng không?**
11. **Retry sau timeout có idempotency và reconciliation không?**
12. **Khi partition heal, replica hội tụ bằng cơ chế nào?**
13. **Ở mạng bình thường, p99/cost của strong và eventual path khác thế nào?**
14. **Read model/cache/search có freshness SLO và fallback không?**
15. **Có thử nghiệm network partition thật với node còn sống không?**
16. **Có ghi đủ operation history để kiểm chứng linearizability không?**
17. **Có tính cả timeout khi báo SLO và p99 không?**
18. **Failover, RPO/RTO, snapshot và repair có được kiểm chứng không?**
19. **Khi không thể đáp ứng contract, API báo gì cho người dùng?**
20. **Đường nào được fail open, đường nào phải fail closed?**

**Kết luận:** **“Chọn hai trong ba” chỉ là lời nhắc sơ lược, không phải quy tắc phân loại database hay quyết định kiến trúc.** CAP đặt ra giới hạn khi phân vùng mạng khiến node không thể trao đổi thông tin: hệ không thể đồng thời bảo đảm **linearizable consistency** và **availability theo định nghĩa CAP** cho mọi request trong mô hình đó. Nhưng khi mạng khỏe, các bảo đảm ấy có thể cùng tồn tại; khi lỗi, một hệ có thể **ưu tiên khác nhau theo vùng, endpoint, read/write mode và bất biến nghiệp vụ**. Quorum, leader, replication, causal context, PACELC, durability, idempotency và conflict resolution đều cần phân tích riêng. Hãy thay câu hỏi “database này chọn CP hay AP?” bằng câu hỏi kiểm chứng được: **“Trong lịch sử sự cố cụ thể, thao tác này được phép trả gì, phải chờ gì, không được làm sai điều gì và làm sao chứng minh bằng đo lường?”**
