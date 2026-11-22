# Xác nhận ghi, đồng bộ xuống đĩa và phạm vi dữ liệu có thể mất

## 1. Vì sao “ghi thành công” chưa đủ để nói dữ liệu đã an toàn?

Một ứng dụng Java gửi yêu cầu tạo đơn hàng vào một cơ sở dữ liệu NoSQL. Server phản hồi thành công:

~~~json
{
  "orderId": "order-9001",
  "status": "CREATED"
}
~~~

Người mua nhìn thấy đơn đã tạo và tiếp tục thanh toán. Vài mili giây sau, một node cơ sở dữ liệu bị mất điện, lỗi ổ cứng hoặc bị thay thế trong quá trình failover. Bản ghi `order-9001` có còn không?

Không thể trả lời chỉ từ việc API đã nhận HTTP 200. Cần xác định **xác nhận ghi (write acknowledgement) được gửi sau bước nào**:

1. Máy chủ đã nhận request từ mạng.
2. DBMS đã áp dụng thay đổi vào bộ nhớ.
3. Thao tác được ghi vào journal/commit log.
4. Journal/commit log đã được đồng bộ xuống thiết bị lưu trữ.
5. Một hay nhiều replica đã nhận và xác nhận thay đổi.
6. Thay đổi đã đạt điều kiện commit theo giao thức cụm.
7. API trả kết quả cho client.

Không phải mọi NoSQL DBMS đều thực hiện theo đúng thứ tự này. Có hệ dùng WAL hoặc commit log, có hệ chủ yếu lưu trong bộ nhớ với persistence tùy chọn, có hệ là dịch vụ được quản lý mà người dùng không điều khiển fsync từng node. Điều kiện ACK cũng tùy hệ và cấu hình.

**Mục tiêu bài học** là hiểu từng mốc và trả lời: **dữ liệu đã được xác nhận bền trước loại sự cố nào, dữ liệu nào có thể mất, và khi client gặp timeout thì phải xử lý thế nào?**

### 1.1. Các trường hợp sử dụng điển hình

- Một **cache** có thể chấp nhận mất dữ liệu và tự tạo lại từ nguồn.
- Một **phiên đăng nhập** có thể bị mất khiến người dùng phải đăng nhập lại.
- Một **sự kiện đo lường** có thể mất mà thiết bị không gửi bù được.
- Một **đơn hàng** đã được người dùng xác nhận có hậu quả nghiệp vụ lớn nếu biến mất.
- Một **bản ghi thanh toán** hoặc **audit** có thể có yêu cầu lưu giữ và đối soát chặt chẽ.

Cùng một công nghệ NoSQL có thể phục vụ nhiều loại dữ liệu, nhưng không nhất thiết nên dùng **một mức độ bền** cho tất cả.

### 1.2. Kết quả mong đợi

Sau bài này, người học có thể:

- Phân biệt **memory write, buffered write, flush, fsync và journal commit**.
- Diễn giải **write concern, consistency level, replica acknowledgement**.
- Phân biệt **durability, consistency, availability, atomicity và backup**.
- Phân tích các failure mode: process crash, OS crash, power loss, mất ổ, mất node, zone và region.
- Hiểu nguyên tắc của MongoDB, Cassandra, DynamoDB và Redis khi xác nhận ghi.
- Tính gần đúng **cửa sổ dữ liệu có nguy cơ mất** trong giả định cho trước.
- Thiết kế retry idempotent khi request timeout nhưng thao tác có thể đã commit.
- Thiết kế monitoring, backup, phục hồi và diễn tập an toàn trong môi trường thử nghiệm.

---

## 2. Bốn bảo đảm khác nhau thường bị nhầm lẫn

| Thuật ngữ | Câu hỏi thực tế | Không tự bảo đảm điều gì? |
|---|---|---|
| **Acknowledgement** | Điều kiện nào phải đạt trước khi server báo ghi thành công? | Mọi replica đã có dữ liệu bền |
| **Durability** | Sau một failure model xác định, dữ liệu có phục hồi được không? | Mọi client đọc thấy dữ liệu ngay |
| **Consistency** | Những phép đọc/ghi quan sát trạng thái theo quy tắc nào? | Dữ liệu đã fsync hoặc có backup |
| **Atomicity** | Những thay đổi thuộc một giao dịch cùng commit/rollback không? | Toàn hệ có thể chống mất region |

**Availability** là trục thứ năm: dịch vụ có còn xử lý request khi một số thành phần không hoạt động hay không. Chờ nhiều replica hoặc journal sync có thể tăng độ bền trước một số lỗi, nhưng cũng có thể tăng latency hoặc khiến write không được chấp nhận khi không đủ node.

### 2.1. Durability phải gắn với một mô hình sự cố

Một hệ có thể bảo đảm dữ liệu chống được crash của tiến trình, nhưng không chống được mất toàn bộ node nếu chỉ có một bản.

Những lớp sự cố:

| Loại sự cố | Ví dụ | Điều có thể bị ảnh hưởng |
|---|---|---|
| Process crash | DBMS bị kill hoặc tự lỗi | Bộ nhớ của tiến trình, thao tác chưa hoàn thành |
| OS crash | Kernel panic, reboot đột ngột | OS page cache chưa sync |
| Power loss | Máy mất điện | RAM và cache storage không có bảo vệ |
| Drive failure | SSD/HDD hỏng không phục hồi | Mọi dữ liệu chỉ có trên ổ đó |
| Node loss | Máy và volume không còn dùng được | Bản dữ liệu trên node |
| Zone loss | Mất một miền lỗi hạ tầng | Các node cùng zone |
| Region loss | Mất cả vùng địa lý | Dữ liệu chỉ ở region đó |
| Logical error | Xóa nhầm, migration sai | Có thể lan ra mọi replica |
| Security incident | Lệnh xóa/sửa trái phép | Nguồn, replica, backup không được bảo vệ |

Một **fsync** có thể giúp khi OS crash nếu thiết bị lưu trữ đáp ứng hợp đồng bền, nhưng không cứu một ổ đã bị phá hủy. **Replication** có thể giúp khi mất một node, nhưng nếu thao tác xóa nhầm được replicate tới mọi node, nó không thể đưa dữ liệu cũ trở lại.

### 2.2. Đọc lại đúng giá trị không chứng minh fsync

Ví dụ:

~~~text
WRITE order-9001
ACK
READ order-9001 -> found
~~~

Nếu bản ghi đang ở RAM hoặc một replica có dữ liệu nhưng chưa đồng bộ vật lý, phép đọc vẫn có thể trả giá trị mới. Điều đó chứng minh **visibility** trên đường đọc được sử dụng, không tự chứng minh **durability** trước power loss.

Ngược lại, một bản ghi có thể đã durable trên primary nhưng read từ secondary trễ chưa trả về nó. Đây là **read consistency/replication lag**, không nhất thiết dữ liệu đã mất.

## 3. Một lệnh ghi đi từ client đến đĩa như thế nào?

Một hệ dùng journal/commit log có thể được hình dung:

~~~mermaid
sequenceDiagram
    participant C as Java client
    participant S as DBMS node
    participant M as Memory / memtable
    participant L as Journal / commit log
    participant OS as OS page cache
    participant D as Storage device
    participant R as Replica

    C->>S: Write order-9001
    S->>L: Append log record
    S->>M: Apply in-memory state
    L->>OS: Buffered write
    OS->>D: Sync theo policy
    S->>R: Replicate write
    R-->>S: Replica ACK
    S-->>C: ACK theo cấu hình
~~~

**Đây là mô hình khái niệm.** Đường đi, thứ tự và điều kiện nhận ACK khác nhau giữa DBMS; không dùng sơ đồ như tài liệu mô tả vật lý chính xác của mọi hệ.

### 3.1. Request đã đến server

TCP gửi dữ liệu không đồng nghĩa DBMS đã xử lý write. Máy có thể dừng sau khi nhận request nhưng trước khi xác nhận ghi vào engine.

### 3.2. Thay đổi trong bộ nhớ

Engine có thể cập nhật memtable, buffer pool hoặc cấu trúc memory khác. Điều này giúp tốc độ cao, nhưng trạng thái chỉ trong RAM có thể mất sau power loss.

### 3.3. Append journal hoặc commit log

Nhiều storage engine ghi tuần tự một **log đủ thông tin để replay** khi khởi động lại. Cách này giúp phục hồi những cập nhật chưa flush vào file dữ liệu chính.

Nhưng chỉ gọi thao tác ghi file log **chưa bảo đảm nội dung đã được đồng bộ khỏi các tầng cache volatile**.

### 3.4. Sync xuống thiết bị

Engine có thể yêu cầu OS thực hiện fsync/fdatasync hoặc cách đồng bộ tương đương. Đây là một mốc khác với “đã append log”.

### 3.5. Replication

Node có thể gửi write tới replica khác; replica xác nhận theo một mức riêng. ACK của replica không mặc nhiên là “đã fsync”.

### 3.6. Trả ACK

DBMS trả thành công khi **chính sách xác nhận của request** được thỏa. Vì vậy câu hỏi đầu tiên khi debug durability là: *chính sách hiện tại cho thao tác cụ thể là gì?*

---

## 4. Write, flush, fsync và bộ nhớ đệm

### 4.1. Bộ đệm của ứng dụng

Một thao tác ghi trong Java có thể ghi vào buffer của thư viện, chưa qua OS.

Ví dụ:

~~~java
import java.io.BufferedOutputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;

try (FileOutputStream file = new FileOutputStream("demo.log");
     BufferedOutputStream stream = new BufferedOutputStream(file)) {

    stream.write("order-9001".getBytes(StandardCharsets.UTF_8));
    stream.flush();

    // BufferedOutputStream.flush() không tự đồng nghĩa
    // mọi byte đã fsync xuống thiết bị lưu trữ.
}
~~~

Đoạn mã chỉ minh họa sự khác nhau giữa các tầng buffer; **không dùng nó như cơ chế WAL đáng tin cậy cho production**.

### 4.2. OS page cache

OS có thể nhận dữ liệu vào các trang bộ nhớ, đánh dấu chúng chưa được ghi bền rồi đồng bộ về sau:

~~~text
Application write()
   |
   v
OS page cache (dirty pages)
   |
   v
Storage device ở thời điểm flush/sync
~~~

Nếu process DBMS crash nhưng OS còn sống, dữ liệu trong OS cache có thể còn. Nếu OS crash/mất điện, các trang chưa được đồng bộ có thể mất.

### 4.3. fsync và fdatasync

Các hệ POSIX có cơ chế như `fsync()` và `fdatasync()` để yêu cầu đồng bộ nội dung và metadata cần thiết theo hợp đồng của OS/filesystem/storage.

Lưu ý:

- `flush()` của một thư viện có thể chỉ chuyển từ user-space buffer sang kernel.
- `fsync()` liên quan đến durability theo hợp đồng OS/storage, không thay thế bản sao độc lập.
- Việc tạo/đổi tên file còn có các chi tiết metadata thư mục ảnh hưởng crash consistency.
- Ổ hoặc controller có write-back cache không được bảo vệ khi mất điện có thể là một nguồn rủi ro.
- SSD với **power-loss protection**, cấu hình storage và nhà cung cấp cloud có thể có bảo đảm khác nhau.

Không nên tự xây thuật toán WAL chỉ bằng cách gọi một hàm đồng bộ mà không hiểu recovery, metadata, thứ tự ghi và hardware behavior.

### 4.4. Các mức khác nhau về ý nghĩa

| Mốc | Điều thường biết | Điều không được suy ra |
|---|---|---|
| Server accepted request | Request đã tới tầng xử lý | Đã commit |
| In-memory applied | Trạng thái mới có trong RAM | Sống sót qua OS crash |
| Log appended | Write đi vào đường I/O log | Log đã được sync vật lý |
| Local fsync completed | Storage xác nhận sync theo contract | Có replica bền ở nơi khác |
| Replica acknowledged | Một replica thỏa điều kiện phản hồi | Điều kiện ấy luôn là fsync |
| Quorum acknowledged | Đủ số replica theo policy phản hồi | Chống được mọi failure model |
| API HTTP 200 | Ứng dụng trả thành công | Event, email, cache, backup đều cập nhật |

**Kết luận:** “đã ghi” phải luôn kèm một mốc cụ thể.

## 5. Write-ahead log và crash recovery

**Write-ahead log (WAL)**, journal hay commit log giúp DBMS có thể replay các thao tác còn cần thiết nếu cấu trúc dữ liệu chính chưa được flush.

~~~mermaid
flowchart TD
    A["Write request"] --> B["Append log"]
    A --> C["Update in-memory state"]
    B --> D{"Log đã sync theo policy?"}
    D -->|"Chưa"| E["Có cửa sổ rủi ro khi crash"]
    D -->|"Đã sync"| F["Có thể replay log sau restart"]
    C --> G["Flush data / memtable"]
    G --> H["Data files / SSTables"]
    F --> I["Crash recovery"]
~~~

### 5.1. Tại sao không fsync toàn bộ dữ liệu chính mỗi lần?

Nhiều cấu trúc index hoặc document có vị trí ghi khác nhau. Ghi tuần tự vào log có thể giảm số I/O ngẫu nhiên và giúp nhiều write được gộp. File dữ liệu chính được hoàn thiện ở bước flush hoặc compaction.

Vì vậy, một write có thể **chưa nằm trong SSTable** nhưng vẫn recover được từ một commit log đã bền.

### 5.2. Append log không đủ nếu chưa sync

Nếu write chỉ nằm trong OS cache của log mà không có bản bền khác, mất điện có thể làm mất cả thay đổi trong RAM lẫn log.

### 5.3. Log rotation và recovery

Engine phải quản lý:

- Log segment nào còn cần replay.
- Snapshot/checkpoint nào cho biết dữ liệu chính đã an toàn.
- Thứ tự log và checksum.
- Phục hồi khi một segment bị lỗi hoặc bị cắt dở.
- Điều kiện xóa log cũ sau flush/compaction.

Do đó, “có WAL” chưa đủ để khẳng định mức durability; **cần biết thời điểm WAL trở nên bền và cách recovery**.

## 6. Replication và số ACK cần chờ

Giả sử cụm có ba bản:

~~~text
Replica A (leader/coordinator)
Replica B
Replica C
~~~

Chính sách ACK có thể yêu cầu:

- Chỉ A phản hồi.
- A phản hồi sau journal sync.
- Hai trong ba replica phản hồi.
- Hai replica đạt một điều kiện bền cụ thể.
- Tất cả replica phản hồi.

Cần phân biệt **số lượng bản xác nhận** với **nội dung của xác nhận**.

### 6.1. Quorum

Với replication factor 3:

\[
Q=\left\lfloor\frac{3}{2}\right\rfloor+1=2.
\]

Hai ACK là một majority về số lượng, nhưng **không tự chứng minh cả hai replica đã fsync**.

Một số hệ có ACK theo trạng thái commit bền; hệ khác ACK khi ghi vào bộ nhớ hoặc commit log chưa được sync, tùy cấu hình.

### 6.2. Quorum read/write

Trong những mô hình phân tán, điều kiện \(R+W>RF\) giúp tập node đọc và ghi giao nhau:

\[
R+W>RF.
\]

Nhưng giao nhau không tự tạo serializable transaction hay linearizability nếu tồn tại các vấn đề đồng hồ, ghi cạnh tranh, conflict resolution hoặc giao thức khác. Phải xem hợp đồng của từng DBMS.

### 6.3. Miền lỗi độc lập

Ba replica trên ba máy cùng rack không bảo vệ tốt trước mất cả rack. Nếu mục tiêu là chống mất zone hoặc region, phải phân phối dữ liệu theo các **failure domain** phù hợp và kiểm tra cơ chế failover/DR.

### 6.4. Replication không thay thế backup

Lệnh xóa nhầm có thể được xác nhận và replicate tới cả ba node. Đó là một thay đổi **được lưu bền nhưng sai về nghiệp vụ**. Backup, point-in-time recovery và audit giải quyết một phần rủi ro logic này.

---

## 7. Phạm vi dữ liệu có thể mất

Bảng là mô hình tư duy chung, không phải cam kết cho từng sản phẩm.

| Failure mode | Chỉ có RAM | Local log đã sync | Có replica bền độc lập |
|---|---|---|---|
| Process crash | Có thể mất | Có cơ sở replay | Có bản khác |
| OS crash | Buffer chưa sync có thể mất | Có cơ sở phục hồi | Có thêm bản khôi phục |
| Power loss | Volatile state mất | Phụ thuộc storage contract | Có thể lấy từ bản khác |
| Drive failure | Bản local không dùng được | Fsync không cứu ổ đã hỏng | Replica có thể phục hồi |
| Node loss | Bản local mất khả dụng | Chưa đủ nếu chỉ nằm trên node đó | Phụ thuộc replica còn lại |
| Zone loss | Có thể mất các bản cùng zone | Không tự chống lỗi cả zone | Cần bản ở zone khác |
| Region loss | Bản trong region không đủ | Không giải quyết lỗi cả region | Cần multi-region/backup bên ngoài |
| Xóa nhầm được replicate | Dữ liệu đúng có thể mất | Log có thể ghi bền lệnh sai | Replica cũng có thể sai |

### 7.1. “Có thể mất” không đồng nghĩa chắc chắn mất

Nếu ACK trước fsync, nhiều lần crash vẫn có thể phục hồi do hệ kịp flush hoặc replica khác đã giữ bản ghi. Nhưng **độ bền không được thiết kế dựa trên kết quả may mắn**.

### 7.2. ACK mạnh vẫn cần mô hình sự cố

Một hợp đồng kỹ thuật có ý nghĩa có thể phát biểu:

> Những write đã được xác nhận theo policy X được bảo vệ trước mất một node nếu ít nhất Y replica bền ở failure domain độc lập còn hoạt động.

Không nên chỉ viết “DB bảo đảm không bao giờ mất dữ liệu”.

## 8. Cửa sổ dữ liệu có nguy cơ mất

Giả sử một cấu hình giả định gửi ACK trước khi sync log và không có bản replica bền khác trong khoảng chưa sync.

Đặt:

- \(r\): số write/giây.
- \(\Delta\): khoảng thời gian dữ liệu chưa được bảo vệ.
- \(s\): kích thước payload trung bình.

Số write có nguy cơ:

\[
N_{\text{risk}}\approx r\times\Delta.
\]

Dung lượng payload logic có nguy cơ:

\[
B_{\text{risk}}\approx N_{\text{risk}}\times s.
\]

### 8.1. Ví dụ

~~~text
Tốc độ: 2.000 write/giây
Cửa sổ chưa sync giả định: 1 giây
Payload: 800 byte/write
~~~

\[
N_{\text{risk}}\approx2000.
\]

\[
B_{\text{risk}}\approx2000\times800
=1\,600\,000\text{ byte}\approx1.6\text{ MB}.
\]

Đây là **ước lượng tình huống giả định**, không phải mức mất tối đa được bảo đảm bởi MongoDB, Cassandra, Redis hay dịch vụ khác. Sync có thể trễ, write rate biến động và replica có trạng thái khác nhau.

### 8.2. Mốc commit khác mốc replica nhận

Ví dụ:

~~~text
Latest accepted sequence: 960
Local synced sequence:   950
Replica B received:      940
Replica C received:      935
~~~

Không thể tự kết luận sẽ mất chính xác 25 bản ghi. Kết quả phụ thuộc ACK policy, commit point, khả năng recovery và quy tắc bầu leader.

### 8.3. Không trộn các loại lag

- **Fsync lag:** khoảng dữ liệu chưa bền ở một node.
- **Replication lag:** bản khác chưa theo kịp.
- **Index/search lag:** read model chưa có trạng thái mới.
- **Backup lag:** bản sao khôi phục mới nhất chưa bao phủ write hiện tại.

Bốn chỉ số phục vụ các câu hỏi khác nhau.

---

## 9. RPO và RTO

- **RPO (Recovery Point Objective):** lượng dữ liệu/thời gian mất dữ liệu được chấp nhận khi phục hồi sau một sự cố xác định.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để đưa dịch vụ trở lại trạng thái hoạt động được chấp nhận.

Ví dụ:

| Loại | RPO mong muốn | Yêu cầu phục hồi |
|---|---|---|
| Cache tái tạo được | Có thể mất toàn cache | Phục hồi bằng warm cache |
| Log debug ngắn hạn | Có thể mất một khoảng gần nhất | Không ảnh hưởng luồng chính |
| Đơn hàng đã ACK | Không muốn mất write đã xác nhận trong failure model | Phục hồi và đối soát |
| Audit quan trọng | Hạn chế mất và sửa trái phép | Bằng chứng lưu trữ và truy vết |

### 9.1. RPO không phải chỉ là khoảng fsync

RPO thực tế còn phụ thuộc replication, backup, log retention, DR topology, broker, dữ liệu ngoài DB, quyền truy cập và khả năng khôi phục.

Một local fsync mạnh không tạo RPO bằng 0 khi mất toàn bộ volume/region nếu không có bản sao ở miền lỗi khác.

### 9.2. RTO không chỉ là “có backup”

Có backup nhưng mất hàng ngày để restore hàng chục TB, tái tạo index và bật API có thể không đáp ứng RTO. Cần **diễn tập restore**, không chỉ kiểm tra rằng file backup tồn tại.

### 9.3. Chống mất node khác chống mất lỗi logic

Replication giảm rủi ro mất một bản vật lý. Backup/PITR giúp phục hồi trạng thái trước một lỗi nghiệp vụ đã được nhân bản. Cả hai thường cần thiết đối với dữ liệu quan trọng.

---

## 10. MongoDB: write concern

MongoDB hỗ trợ **write concern** để quy định mức xác nhận ghi.

Những tham số thường gặp:

- `w`: số/mức xác nhận, ví dụ `1` hoặc `"majority"`.
- `j`: yêu cầu journaling theo semantics MongoDB.
- `wtimeout`: giới hạn thời gian chờ write concern.

### 10.1. ACK từ primary

~~~javascript
db.orders.insertOne(
  {
    _id: "order-9001",
    customerId: "customer-42",
    status: "CREATED"
  },
  {
    writeConcern: { w: 1 }
  }
);
~~~

`w:1` yêu cầu primary xác nhận theo contract. Điều đó **không tự có majority commit**. Trong một số kịch bản failover, write chưa đạt commit rule phù hợp có thể bị rollback.

### 10.2. Yêu cầu journal

~~~javascript
db.orders.insertOne(
  {
    _id: "order-9002",
    customerId: "customer-42",
    status: "CREATED"
  },
  {
    writeConcern: {
      w: 1,
      j: true
    }
  }
);
~~~

`j:true` yêu cầu điều kiện journaling theo semantics MongoDB, giúp bảo vệ trước một số local crash. Nhưng local journal sync **không tạo replica khác** và không cứu ổ đã mất hoàn toàn.

### 10.3. Majority và journal

~~~javascript
db.orders.insertOne(
  {
    _id: "order-9003",
    customerId: "customer-42",
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

Điều này thể hiện ý muốn chờ majority acknowledgement cùng yêu cầu journaling và timeout. Tương tác cụ thể giữa majority, journal và commit point phụ thuộc phiên bản/config của replica set.

### 10.4. Ví dụ Java

~~~java
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

// Giả định database đã được cấu hình.
MongoCollection<Document> orders = database
    .getCollection("orders")
    .withWriteConcern(
        WriteConcern.MAJORITY
            .withJournal(true)
            .withWTimeout(5, TimeUnit.SECONDS)
    );

orders.insertOne(
    new Document("_id", "order-9004")
        .append("customerId", "customer-42")
        .append("status", "CREATED")
);
~~~

Ví dụ chỉ minh họa cấu hình write concern. Đường ghi production phải xử lý exception, kết quả commit không rõ, ID ổn định và retry.

### 10.5. Timeout không chứng minh chưa ghi

Timeline:

~~~text
T1: Primary nhận và áp dụng write.
T2: Chưa đủ majority ACK trước wtimeout.
T3: Client nhận write concern timeout.
T4: Replica có thể bắt kịp sau đó.
~~~

Write **có thể tồn tại** dù client thấy timeout. Vì thế, retry với `orderId` mới có nguy cơ tạo trùng.

### 10.6. Read concern khác write concern

Write concern xác định điều kiện xác nhận **ghi**; read concern/read preference/session semantics quyết định một phần cách **đọc**.

Một secondary trễ có thể chưa thấy record mới mặc dù primary/majority đã ACK. Không được dùng một phép đọc stale để kết luận record không bền.

### 10.7. Cần kiểm tra khi vận hành

- Default write concern trong cluster.
- Endpoint nào override `w` hoặc `j`.
- Số voting/data-bearing members.
- Trạng thái journal và storage.
- Replication lag, rollback, write concern timeout.
- Backup/PITR và khả năng khôi phục khi mất node/zone.

## 11. Cassandra: consistency level và commit-log sync

Cassandra tiếp nhận write qua coordinator và các replica chịu trách nhiệm với partition.

### 11.1. Consistency level

Giả sử replication factor 3:

| Mức | Ý nghĩa khái quát |
|---|---|
| `ONE` | Một replica xác nhận |
| `QUORUM` | Đa số replica xác nhận |
| `ALL` | Các replica liên quan phải phản hồi |
| `LOCAL_QUORUM` | Quorum trong local datacenter |
| `EACH_QUORUM` | Quorum ở từng datacenter theo contract |

CL xác định **phạm vi phản hồi**, không tự buộc mỗi replica fsync trước ACK nếu commit-log sync mode không yêu cầu như vậy.

### 11.2. Commit log và memtable

~~~text
Coordinator gửi write
   ├── Replica A: commit log + memtable
   ├── Replica B: commit log + memtable
   └── Replica C: commit log + memtable

Coordinator ACK khi đạt CL yêu cầu
~~~

Memtable được flush thành SSTable về sau; log phục vụ crash recovery theo cơ chế engine.

### 11.3. Periodic và batch sync

Tùy phiên bản/config Cassandra có các chế độ đồng bộ commit log:

- **Periodic:** sync theo chu kỳ; ACK có thể đến trước fsync của vòng hiện tại.
- **Batch:** nhóm write được đồng bộ theo policy trước khi phản hồi của cơ chế đó.

Ví dụ cấu hình minh họa:

~~~yaml
commitlog_sync: periodic
commitlog_sync_period: 10000ms
~~~

Tên tham số, đơn vị và những mode được hỗ trợ cần kiểm tra theo phiên bản Cassandra thực tế. Không sao chép ví dụ lên production mà chưa xác minh.

### 11.4. Quorum không tự nghĩa hai fsync

Nếu A và B ACK ở mức commit log/memory nhưng chưa có local sync xong, cùng lúc mất điện A/B có thể tạo cửa sổ rủi ro. Quorum tăng số replica tham gia ACK nhưng **durability còn phụ thuộc mức bảo vệ trên các replica đó**.

### 11.5. Hinted handoff không phải backup

Cơ chế hints có thể giúp replica vắng mặt bắt kịp trong điều kiện phù hợp. Nó có hạn mức/retention và không thay thế backup, đồng bộ commit log hoặc bảo đảm phân bố replica.

### 11.6. Không suy ra transaction SQL từ QUORUM

Trong một số giả định, chọn `R+W>RF` tạo giao nhau giữa tập replica đọc/ghi, nhưng Cassandra còn có timestamp, conflict resolution và các semantics riêng. `QUORUM` không tự cho serializable transaction nhiều partition.

### 11.7. Monitoring

- Commit-log sync latency và backlog.
- Mutation p95/p99, timeouts.
- Dropped mutations.
- Memtable flush/compaction.
- Replica availability, repair health.
- Disk pressure và failure domains.

---

## 12. DynamoDB: durability của managed service

DynamoDB quản lý storage/replication ở tầng dịch vụ; application không cấu hình fsync trên từng node như Cassandra/Redis tự quản lý.

### 12.1. Ghi có điều kiện

Ví dụ AWS SDK JavaScript v3:

~~~javascript
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import {
  DynamoDBDocumentClient,
  PutCommand
} from "@aws-sdk/lib-dynamodb";

const client = DynamoDBDocumentClient.from(
  new DynamoDBClient({})
);

await client.send(new PutCommand({
  TableName: "Orders",
  Item: {
    orderId: "order-9001",
    customerId: "customer-42",
    status: "CREATED"
  },
  ConditionExpression: "attribute_not_exists(orderId)"
}));
~~~

Conditional write giúp tránh ghi đè theo khóa. Nếu response lần đầu mất, retry có thể gặp condition failure vì item đã tồn tại; cần **đọc lại và so payload**, không mặc định tạo Order mới.

### 12.2. Durability trong region khác propagation đa region

DynamoDB có cơ chế redundancy/durability theo hợp đồng dịch vụ trong AWS Region. Nếu ứng dụng sử dụng global tables, sự sao chép giữa region có semantics/lag riêng. Ghi thành công ở region A **không tự có nghĩa region B đã nhận ngay**.

RPO khi mất toàn region cần được đánh giá trên cấu hình multi-region, backup và khả năng failover thực tế.

### 12.3. GSI lag khác mất write

GSI DynamoDB hỗ trợ eventual-consistent reads. Sau PutItem thành công, query trên GSI có thể chưa thấy item dù nguồn đã lưu.

~~~text
PutItem on base table -> success
Query GSI by status   -> not yet visible
GetItem base key      -> may be visible with appropriate read
~~~

Không lấy GSI rỗng làm bằng chứng ghi nguồn thất bại.

### 12.4. Transaction không thay thế DR

DynamoDB transaction có thể cung cấp atomicity trên các item theo giới hạn của dịch vụ, nhưng không tự bảo đảm replication đa region tức thời hoặc backup phục hồi logic. Cần phân biệt các trục này.

## 13. Redis: in-memory ACK, RDB và AOF

Redis có thể vận hành như cache hoặc kho dữ liệu chính, tùy cấu hình persistence.

### 13.1. Không có persistence

~~~text
SET cache:product-8 "price=450000"
~~~

Nếu Redis là cache có thể tái tạo từ nguồn, mất key sau crash có thể chấp nhận. Nếu lưu đơn hàng duy nhất ở một Redis không persistence, mất toàn bộ instance có thể làm biến mất dữ liệu đã ACK.

### 13.2. RDB snapshot

~~~text
T0: Snapshot được tạo.
T1: Write A.
T2: Write B.
T3: Power loss trước snapshot tiếp theo.
~~~

Nếu chỉ còn snapshot T0 và không có bản sao/log bền khác, A/B có thể mất. RDB có cửa sổ thay đổi sau snapshot cần được cân nhắc.

### 13.3. Append Only File

Redis có AOF để replay các thao tác ghi. Những chế độ `appendfsync` thường gặp:

| Mode | Ý nghĩa khái quát | Đánh đổi |
|---|---|---|
| `always` | Đồng bộ AOF rất thường xuyên theo semantics Redis | Bảo vệ local mạnh hơn, tăng latency/I/O |
| `everysec` | Sync định kỳ gần mỗi giây | Cân bằng hiệu năng và cửa sổ rủi ro |
| `no` | Dựa nhiều hơn vào chính sách sync của OS | Rủi ro phụ thuộc hạ tầng |

`everysec` không phải lời hứa tuyệt đối “chỉ mất tối đa đúng một giây” trong mọi sự cố. Tải I/O, scheduling và hardware behavior có thể ảnh hưởng.

### 13.4. Replication và WAIT

~~~text
SET order:9001 "CREATED"
WAIT 1 1000
~~~

Lệnh `WAIT` có thể chờ số replica xác nhận nhận write theo ngữ nghĩa Redis. Nó **không tự chứng minh AOF đã được fsync trên replica** và không biến Redis replication thành transaction durable tuyệt đối.

Nếu phiên bản Redis có những cơ chế chờ persistence nâng cao, phải kiểm tra chính xác điều kiện và cấu hình, không suy ra chúng từ `WAIT`.

### 13.5. Replica không thay thế backup

Lệnh `DEL` sai có thể được replicate và ghi AOF rất bền. Muốn phục hồi dữ liệu trước thao tác sai, cần backup/PITR hoặc nguồn đáng tin khác.

---

## 14. Tổng hợp theo từng DBMS

| Hệ | Điều cần kiểm tra | Sai lầm phổ biến |
|---|---|---|
| MongoDB | `w`, `j`, `wtimeout`, commit point, replica set | `w:1` tự tương đương majority |
| Cassandra | RF, CL, commit-log sync, repair, topology | `QUORUM` tự là fsync ở mọi replica |
| DynamoDB | Service durability, region, GSI consistency, global tables | GSI chưa thấy item đồng nghĩa write nguồn thất bại |
| Redis | Persistence mode, RDB/AOF, `appendfsync`, `WAIT` | WAIT hoặc memory ACK luôn durable |
| External read model | CDC/outbox, version, checkpoint, lag | ACK DB nguồn nghĩa search/cache đã cập nhật |

Không có ý nghĩa khi xếp hạng một hệ “durable hơn” mà không xác định cấu hình, workload và loại sự cố.

## 15. Timeout và trạng thái không chắc chắn

Một client gửi create Order và gặp timeout. Có ít nhất ba khả năng:

~~~mermaid
flowchart TD
    A["Client sends write"] --> B{"Outcome"}
    B --> C["Request did not reach DB"]
    B --> D["DB committed, response not sent"]
    B --> E["DB committed, ACK lost in network"]
    C --> F["Client sees timeout"]
    D --> F
    E --> F
    F --> G["Cannot infer not-applied from timeout"]
~~~

### 15.1. Không retry bằng ID mới

Sai:

~~~text
First request: order-9001 -> timeout
Retry: order-9002
~~~

Nếu request đầu đã commit, hai ID tạo hai Order.

Nên giữ:

~~~json
{
  "requestId": "create-order-9001",
  "orderId": "order-9001",
  "customerId": "customer-42",
  "totalVnd": 1050000
}
~~~

### 15.2. Một quy trình retry có kiểm soát

1. Giữ nguyên `requestId` và `orderId`.
2. Kiểm tra kết quả đã lưu của request cũ.
3. Thử ghi có điều kiện nếu chưa xử lý.
4. Nếu nhận ACK, lưu/trả kết quả ổn định.
5. Nếu timeout/unknown, đọc trạng thái theo consistency phù hợp.
6. Nếu item tồn tại đúng payload, coi thao tác đã thực hiện.
7. Nếu ID tồn tại với payload khác, trả conflict.
8. Nếu chưa kết luận được, trả trạng thái pending hoặc reconciliation.

**Có requestId trong payload không tự tạo idempotency** nếu hệ không kiểm tra/lưu nó một cách cạnh tranh an toàn.

### 15.3. Driver retryable writes

Một số driver/DBMS hỗ trợ retry các lệnh nhất định theo giao thức riêng. Điều đó không thay thế idempotency của workflow gồm thanh toán, trừ tồn kho, gửi email hoặc phát event.

## 16. Java: ứng dụng cần làm gì với write concern timeout?

Ví dụ Java MongoDB driver:

~~~java
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

public final class OrderWriter {
    private final MongoCollection<Document> orders;

    public OrderWriter(MongoDatabase database) {
        this.orders = database.getCollection("orders")
            .withWriteConcern(
                WriteConcern.MAJORITY
                    .withJournal(true)
                    .withWTimeout(5, TimeUnit.SECONDS)
            );
    }

    public void create(String orderId, String customerId) {
        orders.insertOne(
            new Document("_id", orderId)
                .append("customerId", customerId)
                .append("status", "CREATED")
        );
    }
}
~~~

Đây là ví dụ cấu hình chứ không phải service production hoàn chỉnh. Khi exception xảy ra, không được mặc định mọi lỗi nghĩa là chưa ghi.

### 16.1. Phân loại kết quả

| Kết quả | Cách ứng dụng nên suy nghĩ |
|---|---|
| ACK đầy đủ | Ghi đã thỏa policy, có thể trả thành công |
| Validation failure rõ ràng | Không hợp lệ, không retry nguyên yêu cầu |
| Duplicate key | Kiểm tra request cũ có cùng ID/payload hay không |
| Timeout/network error | Kết quả có thể không rõ; kiểm tra/reconcile |
| Write concern failure | Phải hiểu write có thể đã được áp dụng |
| Kết quả tồn tại đúng payload | Có thể coi request idempotent đã hoàn thành |
| Kết quả tồn tại khác payload | Conflict, không ghi đè tùy tiện |

### 16.2. Đọc lại qua GSI/secondary có thể gây sai kết luận

Nếu read model hoặc replica lag, một query rỗng chưa chứng minh nguồn chưa có record. Cần đường đọc hoặc trạng thái request được bảo đảm phù hợp.

## 17. Transaction atomic không đồng nghĩa mọi hệ cùng durable

Giả sử thao tác nghiệp vụ tạo:

~~~text
Order
OrderItems
InventoryReservation
OrderCreated event
~~~

Nếu các bảng nằm trong cùng DBMS và phạm vi transaction được hỗ trợ, atomicity có thể nhóm những thay đổi được phép. Nhưng event bus, email và dịch vụ thanh toán có thể nằm **ngoài transaction đó**.

### 17.1. Hai cửa sổ lỗi phổ biến

~~~text
DB commit Order thành công
Application crashes before publish OrderCreated
~~~

Order có nhưng consumer không biết.

~~~text
Publish OrderCreated thành công
DB transaction rolls back
~~~

Consumer có thể xử lý Order không tồn tại.

### 17.2. Transactional outbox

~~~mermaid
sequenceDiagram
    participant App as Order service
    participant DB as Database
    participant Relay as Outbox worker
    participant Bus as Broker
    participant Consumer as Downstream

    App->>DB: Atomic Order + OutboxEvent
    DB-->>App: Commit ACK per durability policy
    Relay->>DB: Fetch pending event
    Relay->>Bus: Publish OrderCreated
    Bus-->>Relay: Broker ACK
    Consumer->>Bus: Consume
    Consumer->>Consumer: Idempotent action
~~~

Order và outbox phải được ghi **trong cùng phạm vi atomicity thật**. Nếu DBMS không hỗ trợ transaction tương ứng, hai insert nối nhau không tự trở thành atomic.

Broker cũng có ACK và durability policy riêng. Consumer phải xử lý khả năng nhận event nhiều lần.

## 18. Failover và rollback

Giả sử ba replica A/B/C:

~~~text
T0: A là leader.
T1: Client gửi write X.
T2: A nhận X.
T3: A ACK X theo policy một node.
T4: A mất kết nối, X chưa đạt majority commit.
T5: B thành leader.
T6: A trở lại và đồng bộ theo lịch sử được chấp nhận.
~~~

Trong những giao thức/cấu hình phù hợp, X có thể bị rollback khi chưa đạt điều kiện commit cần thiết trước failover. Client có ACK theo policy yếu, nhưng write có thể không nằm trong lịch sử chính sau đó.

### 18.1. Majority commitment và election

Một số giao thức replicated DB có quy tắc bảo vệ những write đã majority-committed khi leader đổi. Chi tiết election, journal và commit point là **đặc thù DBMS**, không thể dùng số replica để suy ra mọi bảo đảm.

### 18.2. Trạng thái unknown

Khi đổi leader, một write có thể đã commit nhưng client gặp timeout. Retry tới leader mới phải dùng identity ổn định. Trong quá trình đó, replica/read model trễ có thể khiến client đọc không thấy write mới.

### 18.3. Observability

Nếu DBMS expose applied index, durable index, committed index hoặc replication point, chúng có thể giúp phân tích sau sự cố. Nhưng những mốc này phải được diễn giải theo semantics của sản phẩm.

---

## 19. Vì sao backup vẫn bắt buộc với dữ liệu quan trọng?

Nhiều replica không ngăn được:

- Xóa nhầm được propagate.
- Lỗi ứng dụng ghi sai giá trị lên tất cả node.
- Migration hỏng schema.
- Xâm nhập quyền quản trị.
- Hỏng logic được phát hiện muộn.
- Sự cố đồng thời tại failure domain chung.

Một kế hoạch phục hồi có thể gồm:

- Snapshot định kỳ.
- Log/PITR để khôi phục đến thời điểm phù hợp.
- Bản sao ngoài zone/region.
- Mã hóa, kiểm soát quyền và kiểm soát xóa backup.
- Bài thử restore định kỳ.
- Đối soát hệ phụ thuộc sau khi phục hồi.

### 19.1. Snapshot đã có không có nghĩa restore sẽ thành công

Cần thử:

1. Snapshot có đầy đủ data/schema/metadata không?
2. Key mã hóa có sẵn và được phép sử dụng không?
3. Có thể replay log đến mốc mong muốn không?
4. Cần bao lâu để dựng cluster, index và API?
5. Phục hồi từ backup cũ có làm dữ liệu đã xóa theo yêu cầu xuất hiện lại không?
6. Payment, event bus, cache và downstream cần đối soát thế nào?

### 19.2. Khôi phục cả hệ khác khôi phục một DB

Nếu DB Order quay về T0 nhưng hệ thanh toán đang ở T1, có thể có thanh toán không còn Order tương ứng. DR phải có cách reconcile các hệ, không chỉ câu lệnh restore.

## 20. Hiệu năng và durability trade-off

| Cơ chế | Lợi ích | Chi phí/rủi ro |
|---|---|---|
| Sync journal thường xuyên | Giảm cửa sổ chưa bền local | I/O và write latency |
| Group commit | Gộp nhiều log record vào một sync | Có thể chờ batch |
| ACK từ một node | Một số tình huống phản hồi nhanh | Chưa có replica đủ bền |
| Quorum ACK | Nhiều bản sao xác nhận | Chờ network/replica, availability trade-off |
| Replication đa vùng đồng bộ | Giảm một số rủi ro DR | RTT và phụ thuộc cross-region |
| Replication bất đồng bộ | Local write nhanh | Replica xa có thể lag |
| Backup thường xuyên | Nhiều mốc khôi phục | Storage/network/ops |
| Journal/WAL | Crash recovery nếu log còn bền | Log I/O, lưu trữ và replay |

### 20.1. Group commit

~~~text
Write A at 10:00:00.001
Write B at 10:00:00.002
Write C at 10:00:00.003
Journal sync at 10:00:00.005
ACK per policy after sync
~~~

Nhiều write dùng chung một lần fsync giúp tăng hiệu quả. Nếu ACK vẫn chờ journal durable, group commit không tự làm giảm contract độ bền; nó thay cách phân bổ latency.

### 20.2. Đo dưới tải thật

Một cấu hình có p50 write nhanh nhưng p99 rất chậm khi replica lag có thể vi phạm SLO.

Cần đo:

- Write ACK p50/p95/p99.
- Journal/commit-log sync latency.
- Flush backlog.
- Replica lag, quorum timeout.
- Storage IOPS và disk errors.
- Failover duration.
- Reconciliation mismatch.
- Backup age và restore success.

## 21. Chọn chính sách theo dữ liệu

| Dữ liệu | Có thể dựng lại? | Hậu quả mất | Định hướng |
|---|---|---|---|
| Cache sản phẩm | Có | Chậm hoặc cache miss | Có thể chấp nhận persistence thấp |
| Session | Một phần | Người dùng login lại | Xét UX và bảo mật |
| Raw telemetry | Không phải lúc nào | Mất đo lường | Đặt tỷ lệ mất chấp nhận, buffer nguồn |
| Order đã ACK | Khó | Sai nghiệp vụ | Durability, idempotency, DR |
| Thanh toán | Rất nhạy cảm | Sai tiền | Audit, atomicity, reconciliation |
| Search index | Thường rebuild được | Stale kết quả | Source bền, view có thể eventual |
| Audit log | Có thể bắt buộc giữ | Mất bằng chứng | Integrity, retention, phục hồi |

Cùng một hệ NoSQL có thể chứa tất cả các loại trên. Policy cần dựa vào **dữ liệu và rủi ro**, không chỉ công nghệ.

## 22. Kiểm thử độ bền trong môi trường an toàn

**Chỉ thực hiện kiểm thử crash/failover trong môi trường được cấp phép, với dữ liệu thử và kế hoạch khôi phục; không gây hỏng production để kiểm tra.**

Quy trình minh họa:

1. Ghi nhận phiên bản DBMS, cấu hình sync, replication và storage.
2. Tạo 10.000 write có ID/sequence duy nhất.
3. Lưu manifest client phân biệt `ACKNOWLEDGED`, `UNKNOWN` và `NOT_APPLIED`.
4. Trong test environment, kích hoạt một failure scenario có kiểm soát.
5. Cho hệ khôi phục.
6. Đọc lại nguồn với consistency phù hợp.
7. Đối chiếu các write đã ACK.
8. Phân loại write timeout có/không tồn tại.
9. Ghi recovery duration và các log liên quan.
10. Điều tra mismatch và so với failure model đã đặt.

### 22.1. Manifest

~~~json
{
  "runId": "durability-drill-20261114",
  "writeId": "write-00291",
  "key": "order-00291",
  "clientResult": "ACKNOWLEDGED",
  "writePolicy": "majority-and-journal",
  "clientObservedAt": "2026-11-14T08:15:27Z"
}
~~~

Giá trị `writePolicy` chỉ có ý nghĩa khi khớp cấu hình thực tế được đo.

### 22.2. Phân loại kết quả

| Client | Sau recovery | Nhận định |
|---|---|---|
| ACK | Đúng payload | Phù hợp với bài thử |
| ACK | Thiếu | Cần điều tra theo policy và failure model |
| ACK | Khác payload | Có thể lost update, cạnh tranh ghi, lỗi recovery |
| Timeout | Có bản ghi | Có thể commit trước khi ACK mất |
| Timeout | Không có | Chưa biết chắc trạng thái giữa đường nếu không có thêm bằng chứng |

Một bài thử thành công **không chứng minh mọi failure scenario khác đều không làm mất dữ liệu**.

---

## 23. Bài tập 1: điều gì đã được xác nhận?

Một hệ giả định có ba replica:

~~~text
T0: Client gửi X.
T1: A áp dụng X trong RAM.
T2: A append journal vào OS page cache.
T3: A ACK X, không chờ fsync.
T4: B nhận X trong RAM.
T5: A và B mất điện trước sync.
T6: C chưa nhận X.
~~~

Câu hỏi:

1. Tại T3 client biết điều gì?
2. Có thể khẳng định X vẫn còn sau T5 không?
3. Nếu A đã fsync trước T3 nhưng ổ A hỏng hoàn toàn, cần gì để phục hồi?
4. Nếu B có bản bền độc lập trước T5, kết luận thay đổi thế nào?
5. Vì sao vẫn cần biết quy tắc election/commit?
6. Nếu client thấy timeout, retry bằng ID nào?

**Gợi ý:** RAM và cache chưa sync có thể mất; fsync local không cứu ổ đã mất; replica bền giúp chống lỗi node nhưng kết quả còn phụ thuộc giao thức.

## 24. Bài tập 2: tính số write có nguy cơ

Giả định một hệ tạo 5.000 event/giây, mỗi event 600 byte logic, và có cửa sổ chưa bảo vệ tối đa 0,5 giây trong failure scenario đã cho.

\[
N=5000\times0.5=2500\ \text{event}.
\]

\[
B=2500\times600=1\,500\,000\ \text{byte}\approx1.5\text{ MB}.
\]

Thảo luận:

- Nếu ACK sau sync local, loại rủi ro nào giảm?
- Nếu có ba replica nhưng chỉ đợi một ACK, còn nguy cơ nào?
- Nếu cần hai replica đạt durable condition rõ, chống được loại lỗi nào tốt hơn?
- Nếu mất cả region, cần thiết kế gì?
- Vì sao 0,5 giây không phải RPO chung của hệ?

Đây là phép tính minh họa, không phải cam kết của một DBMS.

## 25. Bài tập 3: Java và kết quả không chắc chắn

Thiết kế hàm:

~~~java
CreateOrderResult createOrder(
    String requestId,
    String orderId,
    String customerId
) {
    // 1. Kiểm tra payload và quyền.
    // 2. Giữ requestId/orderId ổn định.
    // 3. Ghi có điều kiện.
    // 4. Nếu ACK, trả trạng thái đã commit.
    // 5. Nếu timeout/unknown, đọc lại theo consistency phù hợp.
    // 6. Có item với payload cũ -> idempotent success.
    // 7. Có item nhưng payload khác -> conflict.
    // 8. Không xác định -> pending hoặc reconciliation.
    // 9. Event/payment/email phải idempotent riêng.
    return null; // Placeholder.
}
~~~

Trả lời:

1. Vì sao không tạo orderId mới khi timeout?
2. Tại sao query qua GSI/secondary trễ có thể khiến kết luận sai?
3. Vì sao duplicate-key đôi khi là dấu hiệu request cũ đã commit?
4. Làm cách nào không trừ tồn kho hoặc gửi email hai lần?

## 26. Bài tập 4: thiết kế RPO/RTO theo loại dữ liệu

Lập bảng:

| Loại dữ liệu | Tái tạo được? | Failure model | ACK policy | Backup/DR |
|---|---|---|---|---|
| Cache | ? | ? | ? | ? |
| Session | ? | ? | ? | ? |
| Order | ? | ? | ? | ? |
| Audit | ? | ? | ? | ? |

Giải thích tại sao một cấu hình giống nhau cho mọi loại dữ liệu có thể quá đắt hoặc quá yếu.

## 27. Bài tập 5: báo cáo diễn tập failover

Viết một báo cáo mẫu:

~~~markdown
# Durability drill

## Cấu hình
- DBMS/version:
- Replication topology:
- Journal / commit-log sync:
- Write concern / consistency level:
- Storage contract:

## Workload
- Tổng requests:
- ACK:
- Timeout/unknown:
- Lỗi rõ:

## Failure
- Loại lỗi thử:
- Thời điểm:
- Phạm vi:

## Recovery
- RTO quan sát:
- ACKed writes thiếu:
- Unknown writes nhưng tồn tại:
- Replication/commit evidence:

## Kết luận
- Failure model đã kiểm chứng:
- Giới hạn phép thử:
- Thay đổi đề xuất:
~~~

Không suy ra “không bao giờ mất write” chỉ vì một lượt test không phát hiện mất dữ liệu.

## 28. Những ngộ nhận phổ biến

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “HTTP 200 nghĩa mọi dữ liệu đã fsync.” | HTTP phản ánh hợp đồng ứng dụng; cần biết ACK policy DBMS. |
| “Đã nằm trong RAM tức đã bền.” | RAM có thể mất sau power loss. |
| “flush và fsync là một.” | Flush của thư viện có thể chưa đồng bộ xuống storage. |
| “Đã append WAL tức journal bền.” | WAL chưa sync có thể mất khi OS/power crash. |
| “fsync thì không thể mất dữ liệu.” | Mất ổ/node/region hoặc lỗi logic vẫn là rủi ro. |
| “Ba replica chống mọi sự cố.” | Phụ thuộc topology, quorum, storage và miền lỗi. |
| “QUORUM nghĩa mọi replica đã fsync.” | Số ACK không tự định nghĩa nội dung ACK. |
| “Timeout chứng minh lệnh chưa ghi.” | Server có thể commit rồi mất response. |
| “Retry với ID mới là an toàn.” | Có thể tạo dữ liệu trùng. |
| “Đọc thấy item chứng minh item nằm trên disk.” | Read có thể lấy từ RAM hoặc replica chưa durable. |
| “Cassandra CL=QUORUM là transaction SQL.” | CL và serializable transaction khác nhau. |
| “Redis WAIT chứng minh replica đã fsync AOF.” | WAIT có semantics replication riêng. |
| “GSI chưa thấy record nghĩa DynamoDB ghi lỗi.” | GSI eventual consistent. |
| “Có transaction là không thể mất dữ liệu.” | Atomicity và durability khác nhau. |
| “Replication thay thế backup.” | Xóa nhầm và dữ liệu sai có thể được nhân bản. |
| “RPO chính xác bằng thời gian fsync.” | RPO còn phụ thuộc replication/backup/DR và loại sự cố. |
| “DB ACK nghĩa email/event đã gửi.” | Side effect ngoài DB có quy trình riêng. |
| “Có backup là đạt RTO.” | Phải thử khôi phục và đo thời gian thực. |

## 29. Checklist khi thiết kế lưu trữ NoSQL

- ACK được gửi sau mốc nào?
- Mức write concern/consistency/persistence của endpoint là gì?
- Log có được sync trước ACK không?
- Replica ACK khi nhận/apply/durable/commit?
- Failure domain của replica và backup?
- Có thể rollback write đã ACK sau failover không?
- Có ghi nhận unknown outcome và retry idempotent không?
- Read-after-write phải dùng đường đọc nào?
- Các side effect khác có outbox/dedupe không?
- RPO/RTO mục tiêu là gì và áp dụng cho loại sự cố nào?
- Có backup, PITR và restore drill thực tế không?
- Có metric journal/fsync/replication lag và alert?
- Khi restore, dữ liệu các hệ phụ thuộc được đối soát ra sao?
- Độ trễ và throughput của policy đã được đo dưới tải thực tế chưa?

## 30. Tổng kết

Một write trong NoSQL có thể trải qua nhiều mốc: **nhận request → cập nhật memory → append log → sync storage → replica ACK → commit theo giao thức → phản hồi client**. Không có một thứ tự hay điều kiện ACK chung cho mọi DBMS.

Các nguyên tắc cốt lõi:

1. **ACK chỉ có ý nghĩa khi biết chính sách xác nhận và failure model.**
2. **Flush không mặc định là fsync**, và local fsync không tạo bản sao ở miền lỗi độc lập.
3. **Quorum là phạm vi phản hồi**, chưa đủ để suy ra từng replica đã durable nếu không biết contract.
4. **Replication không thay thế backup**, vì nó có thể nhân bản cả lỗi logic.
5. **Timeout không chứng minh write chưa được thực hiện**; ứng dụng phải retry idempotent.
6. **Transaction atomicity và storage durability khác nhau**, cũng như read consistency khác với độ bền.
7. **RPO/RTO là mục tiêu nghiệp vụ cần kiểm chứng**, không phải nhãn tự động đạt bằng một setting.
8. **Độ bền cao hơn có chi phí** về latency, throughput, availability và vận hành.

**Một kiến trúc NoSQL đáng tin cậy phải chỉ rõ dữ liệu được xác nhận tại mốc nào, còn cửa sổ có thể mất nào, chịu được loại sự cố nào và sẽ phục hồi ra sao.**
