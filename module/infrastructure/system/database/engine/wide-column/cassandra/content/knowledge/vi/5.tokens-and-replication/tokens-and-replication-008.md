# Vai trò replica và coordinator khi một nút bất kỳ nhận yêu cầu

## 1. Bài toán cần hiểu

Trong Apache Cassandra, client có thể gửi một yêu cầu đọc hoặc ghi đến **bất kỳ node Cassandra nào đang hoạt động và có thể nhận kết nối**. Node nhận yêu cầu đóng vai trò **coordinator** cho *yêu cầu đó*. Dữ liệu của một partition lại được lưu trên một tập node khác, gọi là **replica**. Vì vậy, node nhận truy vấn không nhất thiết là node chứa dữ liệu.

Đây là một phần quan trọng của kiến trúc phân tán, phi tập trung của Cassandra. Việc hiểu chính xác coordinator phối hợp các replica giúp giải thích cách partition key quyết định vị trí dữ liệu, cách replication factor hoạt động và vì sao consistency level ảnh hưởng đến độ trễ, tính sẵn sàng, mức độ nhất quán khi đọc/ghi.

Sau bài này, người học có thể:

- Phân biệt **coordinator** (vai trò theo từng request) với **replica** (vai trò theo từng partition và topology).
- Mô tả cách một node nhận request tìm replica từ partition key, token và cấu hình replication.
- Theo dõi luồng ghi, luồng đọc và cách Cassandra đếm xác nhận theo consistency level.
- Giải thích hành vi khi coordinator hoặc một số replica lỗi, đặc biệt với `LOCAL_QUORUM`.
- Chọn cách gửi truy vấn từ CQL/Java và chẩn đoán đường đi của request.

**Phạm vi ví dụ:** sử dụng các replica đầy đủ (*full replicas*) và truy vấn đọc/ghi thông thường; không xét transient replication. Lightweight transaction (LWT) được nhắc riêng vì có thêm pha đồng thuận.

## 2. Hai vai trò khác nhau

| Khái niệm | Định nghĩa | Điều cần nhớ |
| --- | --- | --- |
| **Coordinator** | Node trực tiếp tiếp nhận một request từ client và điều phối quá trình thực hiện request đó. | Mỗi request có một coordinator; node nào cũng có thể đảm nhiệm nếu có thể nhận request. |
| **Replica** | Node được chiến lược replication chọn để giữ bản sao của một partition. | Một node có thể là replica của partition A nhưng không phải partition B. |
| **Partition key** | Một hoặc nhiều cột trong primary key dùng để xác định partition. | Các hàng thuộc cùng partition key được phân bố theo cùng một token và nhóm replica. |
| **Token** | Giá trị hàm phân vùng tính từ partition key, thường bằng `Murmur3Partitioner`. | Token giúp xác định các vị trí trên vòng phân phối dữ liệu. |
| **Replication factor (RF)** | Số bản sao dữ liệu được cấu hình cho mỗi data center (với `NetworkTopologyStrategy`). | RF quyết định *bao nhiêu* replica lưu dữ liệu, không phải số xác nhận tối thiểu để request thành công. |
| **Consistency level (CL)** | Mức xác nhận mà coordinator cần đạt đối với một request. | CL tác động đến tính sẵn sàng, độ trễ và kết quả đọc/ghi. |

Một node **có thể đồng thời là coordinator và replica** nếu nó thuộc tập replica của partition đang truy vấn; khi đó nó thực hiện phần việc replica ngay trên chính node đó. Nếu không thuộc tập replica, nó vẫn có thể làm coordinator và chuyển tiếp yêu cầu đến các replica phù hợp.

### Ví dụ một coordinator không phải replica

~~~mermaid
flowchart LR
    Client["Java client / cqlsh"] -->|"Request cho account_id = a-42"| N4["Node N4: coordinator"]
    N4 -->|"Mutation hoặc read request"| N1["Node N1: replica"]
    N4 -->|"Mutation hoặc read request"| N2["Node N2: replica"]
    N4 -->|"Mutation hoặc read request"| N3["Node N3: replica"]
    N4 -.->|"Không cần lưu partition này"| Note["N4 không phải replica"]
~~~

Giả sử RF = 3 và partition của `account_id = 'a-42'` được sao chép tại N1, N2, N3. Client kết nối N4 thì **N4 là coordinator**, còn **N1–N3 là replica**. Nếu client kết nối N2, N2 vừa là coordinator vừa là một replica. Việc chọn coordinator không làm thay đổi nơi partition được lưu.

> Cassandra không có một node *primary/leader* cố định cho tất cả thao tác đọc/ghi thông thường. Các replica được xác định theo token và topology; coordinator là vai trò tạm thời của từng request, không phải quyền sở hữu dữ liệu.

## 3. Khi một node bất kỳ nhận request, chuyện gì diễn ra?

Đối với một thao tác nhắm vào **một partition cụ thể**, coordinator thực hiện quy trình khái quát:

1. **Nhận và kiểm tra request.** Client hoặc driver gửi CQL đến một node đang hoạt động. Node đó xử lý xác thực, quyền truy cập và lập kế hoạch thực hiện truy vấn theo loại statement.
2. **Xác định partition.** Với truy vấn có partition key, coordinator tính token từ các thành phần partition key bằng partitioner của cluster. Ví dụ `PRIMARY KEY ((account_id), event_time)` có partition key là `account_id`.
3. **Tìm tập replica.** Từ metadata vòng token, topology data center/rack và replication strategy của keyspace, coordinator biết các node chịu trách nhiệm lưu partition đó. Với `NetworkTopologyStrategy`, việc chọn replica được tính riêng theo từng data center.
4. **Điều phối request.** Coordinator gửi thông điệp đọc/ghi cho các replica cần thiết, có thể xử lý cục bộ nếu bản thân là replica, đồng thời quản lý timeout và phản hồi.
5. **Áp dụng consistency level.** Coordinator chỉ trả thành công khi điều kiện CL của thao tác được đáp ứng; nếu thiếu replica khả dụng hoặc thiếu phản hồi đúng hạn thì trả lỗi tương ứng.

Điểm phân biệt quan trọng: **driver chọn node nhận request; Cassandra xác định tập replica của partition**. Driver hỗ trợ *token-aware routing* thường ưu tiên một replica trong data center gần client để giảm bước chuyển tiếp, nhưng request vẫn hợp lệ khi một node không chứa partition làm coordinator. Các *contact point* trong cấu hình driver chủ yếu dùng để khám phá cluster, không phải danh sách duy nhất những coordinator được phép sử dụng.

Nếu truy vấn trải qua nhiều partition, coordinator có thể phải điều phối nhiều nhóm replica; không thể suy luồng xử lý của toàn bộ truy vấn như thể nó chỉ có một partition.

## 4. Luồng **ghi**: coordinator gửi mutation đến replica

Ví dụ cluster có một data center `dc1`, RF = 3, partition do N1, N2, N3 giữ; N4 nhận `INSERT` với CL = `LOCAL_QUORUM`.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant K as N4 / Coordinator
    participant R1 as N1 / Replica
    participant R2 as N2 / Replica
    participant R3 as N3 / Replica
    C->>K: INSERT, LOCAL_QUORUM
    K->>R1: Mutation
    K->>R2: Mutation
    K->>R3: Mutation
    R1-->>K: Acknowledgement
    R2-->>K: Acknowledgement
    K-->>C: Success (đã đủ 2/3 local replica)
    Note over K,R3: Replica thứ ba có thể hoàn tất sau phản hồi client
    R3-->>K: Acknowledgement (nếu đến kịp)
~~~

Diễn giải:

1. Coordinator lập kế hoạch cho mutation và gửi đến các replica của partition (trực tiếp hoặc qua cơ chế chuyển tiếp nội bộ khi trải qua nhiều data center). Một yêu cầu ghi thông thường hướng đến **toàn bộ tập replica**, dù chỉ cần một phần xác nhận để đạt CL.
2. Replica nhận mutation, cập nhật **commit log** và **memtable** theo write path, rồi gửi acknowledgement. Việc commit log được đồng bộ xuống đĩa chính xác lúc nào còn tùy cấu hình commit-log sync; không nên hiểu một ACK là mọi SSTable đã được ghi xuống đĩa.
3. Với RF = 3 tại `dc1`, `LOCAL_QUORUM` cần **2 xác nhận từ các replica của dc1**. Khi N1 và N2 xác nhận thành công, N4 có thể phản hồi thành công cho client, dù N3 chưa xác nhận.
4. Nếu một replica tạm thời không nhận được ghi, coordinator có thể lưu **hint** khi điều kiện cho phép; hint giúp phát lại dữ liệu sau khi replica hồi phục. Hinted handoff không thay thế **anti-entropy repair** để đồng bộ lâu dài.

Điểm mấu chốt: **thành công theo CL không có nghĩa là mọi replica đã xác nhận tại thời điểm client nhận kết quả**.

### Mức xác nhận của một lệnh ghi trong RF = 3, một data center

| CL ghi | Số replica tối thiểu phải xác nhận | Nếu chỉ N1, N2 còn hoạt động |
| --- | ---: | --- |
| `ONE` / `LOCAL_ONE` | 1 | Có thể thành công |
| `QUORUM` / `LOCAL_QUORUM` | 2 | Có thể thành công |
| `ALL` | 3 | Không đủ replica để thành công |

Coordinator **không được tính như một replica thứ tư**. Nếu N4 không sở hữu partition, ACK từ N4 không được tính vào ngưỡng CL. Trong mô hình một data center này, `QUORUM` và `LOCAL_QUORUM` cùng cần hai replica, nhưng chúng có thể khác nhau khi keyspace có nhiều data center.

## 5. Luồng **đọc**: coordinator tổng hợp kết quả từ replica

Đọc không đơn giản là hỏi một node bất kỳ rồi trả về dữ liệu đầu tiên nhận được. Coordinator phải thu thập đủ phản hồi theo CL và có thể đối chiếu dữ liệu giữa các replica.

1. Client gửi `SELECT` với partition key và consistency level.
2. Coordinator xác định tập replica. Với đường đọc thông thường, nó có thể yêu cầu **dữ liệu đầy đủ** từ một replica, và **digest** (bản tóm tắt dùng để đối chiếu) từ các replica khác để đạt CL; kế hoạch cụ thể phụ thuộc phiên bản, trạng thái và tối ưu hóa của Cassandra.
3. Nếu các phản hồi phù hợp, coordinator trả dữ liệu cho client sau khi đủ điều kiện CL.
4. Nếu digest không khớp, coordinator phải lấy đủ thông tin để **reconcile** các bản dữ liệu theo timestamp/tombstone và có thể thực hiện **read repair**, tùy phiên bản và cấu hình bảng. Trường hợp này tăng số lượt trao đổi và độ trễ.

Ví dụ với RF = 3, `LOCAL_QUORUM`: N4 có thể hỏi N1, N2. N1 trả dữ liệu đầy đủ, N2 trả digest. Nếu kết quả phù hợp, N4 trả dữ liệu; nếu khác nhau, N4 phải truy vấn, hợp nhất và xử lý chênh lệch theo cơ chế của Cassandra.

`ONE` hoặc `LOCAL_ONE` thường giảm số phản hồi cần chờ, nhưng có thể đọc một bản replica chưa được cập nhật. `QUORUM` hoặc `LOCAL_QUORUM` tăng khả năng quan sát bản ghi mới đã được xác nhận bởi quorum, với chi phí thêm phản hồi và đôi khi read repair.

Quy tắc thường gặp **W + R > RF** (ví dụ RF = 3, ghi 2 và đọc 2) cho biết hai nhóm replica xác nhận có ít nhất một phần tử giao nhau trong mô hình đơn giản. Đây là trực giác để thiết kế mức nhất quán, **không phải lời hứa tuyến tính hóa mọi thao tác**: ghi đồng thời, timestamp xung đột, clock skew, tombstone, lỗi và phạm vi data center vẫn cần được xét. Cassandra giải quyết xung đột dữ liệu thông thường chủ yếu bằng timestamp, không duy trì một leader tuần tự hóa mọi write.

## 6. Consistency level thay đổi yêu cầu với replica như thế nào?

CL áp dụng cho **từng request**, không chuyển ownership của partition và không thay RF trong keyspace.

| Consistency level | Ý nghĩa thực tế | Phạm vi |
| --- | --- | --- |
| `ONE` | Cần 1 phản hồi replica phù hợp cho đọc/ghi. | Có thể sử dụng replica không thuộc data center của coordinator. |
| `LOCAL_ONE` | Cần 1 phản hồi replica trong data center của coordinator. | Phù hợp khi ưu tiên độ trễ theo vùng. |
| `QUORUM` | Cần đa số replica của **tổng RF**: `floor(total_RF / 2) + 1`. | Tính trên các data center có replica. |
| `LOCAL_QUORUM` | Cần đa số replica của **RF tại data center cục bộ**. | Thường dùng để tránh phụ thuộc vào phản hồi từ data center xa. |
| `ALL` | Cần phản hồi từ tất cả full replica liên quan. | Khó đạt khi một replica lỗi. |
| `EACH_QUORUM` | Ghi phải đạt quorum trong **mỗi** data center. | Dùng cho write, không dùng như consistency level đọc thông thường. |
| `ANY` | Write có thể được xác nhận ngay cả khi chỉ lưu được hint ở node nhận, tùy trường hợp. | Chỉ dành cho ghi; không bảo đảm một replica đã có dữ liệu để đọc ngay. |
| `SERIAL`, `LOCAL_SERIAL` | Mức nhất quán của **pha serial/Paxos** trong lightweight transaction. | Không thay thế trực tiếp CL đọc/ghi thông thường. |

### Ví dụ hai data center

Keyspace dùng `NetworkTopologyStrategy`, RF(`dc1`) = 3 và RF(`dc2`) = 3. Một request do coordinator trong `dc1` nhận:

| CL | Điều kiện để ghi thành công trong ví dụ |
| --- | --- |
| `LOCAL_ONE` | 1 replica ở `dc1` phản hồi. |
| `LOCAL_QUORUM` | 2 trong 3 replica ở `dc1` phản hồi. |
| `QUORUM` | 4 trong tổng 6 replica phản hồi. |
| `EACH_QUORUM` | Ít nhất 2 replica ở **mỗi** `dc1` và `dc2` phản hồi. |
| `ALL` | Cả 6 replica phản hồi. |

Với `LOCAL_QUORUM`, request ghi vẫn có thể được chuyển đến các replica ở `dc2`, nhưng **không cần chờ `dc2`** để trả thành công. Trong khi đó, nếu hai replica của `dc1` không khả dụng thì `LOCAL_QUORUM` thất bại dù toàn bộ `dc2` còn khỏe. Vì vậy phải cấu hình data center cục bộ của Java driver đúng với vị trí ứng dụng; `LOCAL_` được hiểu theo data center của **coordinator**.

## 7. Khi node hoặc mạng gặp lỗi

| Tình huống | Hành vi thường gặp | Kết luận |
| --- | --- | --- |
| Node được chọn làm coordinator ngừng hoạt động **trước khi nhận request** | Driver có thể chọn node sống khác theo chính sách retry/load balancing. | Không có một coordinator cố định; client phải quản lý kết nối và timeout. |
| Coordinator chết **sau khi gửi ghi** nhưng trước khi trả response | Một số replica có thể đã áp dụng mutation, trong khi client thấy timeout hoặc mất kết nối. | Kết quả ghi có thể **không xác định từ góc nhìn client**; retry cần xét idempotency. |
| N3 lỗi, N1 và N2 sống, RF = 3, CL = `LOCAL_QUORUM` | Hai replica sống có thể đáp ứng cả đọc và ghi. | Một replica lỗi không nhất thiết làm request thất bại. |
| Chỉ N1 sống, RF = 3, CL = `LOCAL_QUORUM` | Không đủ 2 replica để đáp ứng CL. | Request thất bại dù coordinator còn sống. |
| Một replica chậm nhưng chưa được phát hiện chết | Coordinator có thể chờ đến timeout, hoặc dùng chính sách/speculative retry phù hợp với đường đọc. | Độ trễ phụ thuộc replica và mạng, không chỉ sức khỏe coordinator. |
| Replica vừa phục hồi nhưng bỏ lỡ một số write | Hints có thể giúp cập nhật một phần; repair đối chiếu và đồng bộ các replica. | Không coi hinted handoff là cơ chế bảo đảm hội tụ duy nhất. |

**Phân biệt hai lỗi thường gặp:**

- **Unavailable:** coordinator xác định ngay từ đầu rằng số replica hiện được xem là khả dụng không đủ đáp ứng CL.
- **Read/Write timeout:** coordinator đã chờ xử lý nhưng không nhận đủ phản hồi hợp lệ trong giới hạn thời gian. Ghi có thể đã thành công ở một số replica dù client nhận timeout.

Không nên retry vô điều kiện mọi write. Ghi theo kiểu upsert với khóa và giá trị ổn định thường dễ xử lý khi thử lại hơn các thao tác có tác dụng phụ như cập nhật counter hoặc nối thêm phần tử vào list. Driver cần khai báo **idempotency** đúng bản chất statement và áp dụng retry policy phù hợp.

### Hinted handoff, read repair và anti-entropy repair khác nhau

- **Hinted handoff:** hỗ trợ phát lại mutation gửi hụt cho replica tạm thời không khả dụng, trong giới hạn cấu hình và thời gian lưu hints.
- **Read repair:** phát hiện và có thể sửa khác biệt khi một read chạm đến các replica không đồng nhất; hành vi chính xác phụ thuộc phiên bản, bảng và consistency level.
- **Anti-entropy repair:** chạy để so sánh và đồng bộ dữ liệu giữa các replica trên diện rộng; rất quan trọng cho sự nhất quán lâu dài, đặc biệt với tombstone và dữ liệu ít được đọc.
- **Compaction:** tổ chức/hợp nhất SSTable trên từng node; **không thay thế repair giữa các replica**.

## 8. Thực hành CQL: quan sát coordinator và replica qua một partition

Giả sử có cluster với data center tên `dc1` và **ít nhất ba node Cassandra** trong data center đó. Dùng keyspace và bảng sau để nhóm các sự kiện theo tài khoản:

~~~sql
CREATE KEYSPACE IF NOT EXISTS webshop
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS webshop.events_by_account (
  account_id text,
  event_time timestamp,
  event_id uuid,
  event_type text,
  PRIMARY KEY ((account_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

`account_id` là partition key, còn `event_time` và `event_id` là clustering columns. Với cùng `account_id`, các hàng thuộc một partition và dùng cùng tập replica. Đây cũng là ví dụ của **thiết kế bảng theo truy vấn**: truy vấn lịch sử sự kiện của một tài khoản có thể định tuyến theo partition key.

Trong `cqlsh`, chạy:

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

INSERT INTO webshop.events_by_account
  (account_id, event_time, event_id, event_type)
VALUES
  ('a-42', '2026-01-01T10:00:00Z',
   550e8400-e29b-41d4-a716-446655440000, 'checkout');

SELECT event_time, event_id, event_type
FROM webshop.events_by_account
WHERE account_id = 'a-42'
LIMIT 20;

TRACING OFF;
~~~

`CONSISTENCY` và `TRACING` là lệnh điều khiển của **cqlsh**, không phải cú pháp SQL/CQL gửi qua Java driver. Kết quả tracing có thể cho biết coordinator đã chuyển request đến những endpoint nào, thời điểm gửi thông điệp và độ trễ ở từng pha; chi tiết sự kiện thay đổi theo phiên bản. Lặp lại truy vấn từ các node khác nhau và đối chiếu: **coordinator có thể đổi, còn tập replica của partition về cơ bản vẫn do token và replication quyết định** (trừ khi topology thay đổi).

Trong vận hành, có thể đối chiếu thêm `nodetool status` để thấy trạng thái node/data center và xem chỉ số read/write timeout, latency. Không kết luận một node là replica chỉ vì nó đang là contact point hoặc coordinator. Trên môi trường sản xuất, cân nhắc chi phí tracing và số lượng truy vấn khi bật trace.

## 9. Từ ứng dụng Java: chọn mức nhất quán theo từng statement

Ví dụ dưới đây sử dụng API của **Apache Cassandra Java Driver 4.x**. Driver khám phá topology từ contact point, định tuyến request đến các node phù hợp và node nhận request sẽ làm coordinator.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;

public class ReadAccountEvents {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement prepared = session.prepare(
                    "SELECT event_time, event_id, event_type " +
                    "FROM webshop.events_by_account " +
                    "WHERE account_id = ? LIMIT 20");

            BoundStatement request = prepared.bind("a-42")
                    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            ResultSet rows = session.execute(request);
            for (Row row : rows) {
                System.out.println(row.getString("event_type"));
            }
        }
    }
}
~~~

- `withLocalDatacenter("dc1")` giúp driver ưu tiên tuyến đến node thuộc `dc1`, nơi app dự kiến hoạt động. Giá trị phải khớp tên data center thật.
- `LOCAL_QUORUM` được đặt trên statement để yêu cầu đủ phản hồi từ replica của data center cục bộ. Nó **không buộc contact point trở thành replica**.
- Bind partition key bằng prepared statement giúp driver hiểu routing key để áp dụng token-aware routing. Việc thực thi vẫn được coordinator xử lý, dù driver đã tối ưu chọn node.
- Với cluster triển khai thực tế, khai báo contact point có thể tiếp cận được, cấu hình xác thực/TLS và timeout theo môi trường; `127.0.0.1` chỉ minh họa cho lab chạy cục bộ.

## 10. Các câu hỏi tự kiểm tra

**Tình huống A.** RF = 3 tại `dc1`. N4 nhận write `LOCAL_QUORUM` của partition lưu tại N1, N2, N3. N1 và N2 ACK; N3 chưa trả lời. Request có thành công không? **Có**, vì đủ hai phản hồi local. N4 vẫn chỉ là coordinator, không biến thành replica thứ tư.

**Tình huống B.** Vẫn topology trên, N1 đang sống nhưng N2 và N3 đều không khả dụng. Client gửi read `LOCAL_QUORUM` đến N4. Request có thể thành công không? **Không đủ điều kiện**: chỉ còn một replica local trong khi yêu cầu hai. Đổi coordinator sang N1 cũng không tạo ra một replica mới.

**Tình huống C.** Keyspace có RF = 3 ở `dc1`, RF = 3 ở `dc2`; coordinator ở `dc1`. Hai replica tại `dc1` đều lỗi, cả ba replica ở `dc2` hoạt động. Write `LOCAL_QUORUM` có thành công không? **Không**: yêu cầu hai ACK trong `dc1`; replica ở `dc2` không được dùng để bù số ACK local còn thiếu.

**Tình huống D.** Driver gửi cùng partition key đến hai coordinator khác nhau. Có phải dữ liệu tự động được sao chép sang hai bộ replica khác nhau? **Không**. Tập replica được tính theo token, topology và chiến lược replication; coordinator được chọn theo từng request.

## 11. Ghi nhớ khi thiết kế và xử lý sự cố

1. **Coordinator trả lời cho request; replica chịu trách nhiệm giữ partition.** Hai vai trò có thể cùng tồn tại trên một node nhưng không đồng nghĩa.
2. **Partition key quyết định token, token cùng replication strategy quyết định replica.** Chọn khóa phân vùng tốt giúp hạn chế hotspot và truy vấn dàn trải; chọn coordinator khác không sửa được partition key thiết kế chưa hợp lý.
3. **RF xác định số bản sao; CL xác định số phản hồi cần chờ.** Một write báo thành công theo quorum không hàm ý mọi bản sao đều đã bắt kịp.
4. **Lỗi coordinator và lỗi replica có ý nghĩa khác nhau.** Client có thể mất response dù một phần write đã được áp dụng; retry phải xét idempotency.
5. **`LOCAL_QUORUM` phụ thuộc data center của coordinator.** Đặt local DC và routing đúng với vị trí ứng dụng để đạt mục tiêu độ trễ và phạm vi chịu lỗi.
6. **Hints, read repair và anti-entropy repair giải quyết các tình huống khác nhau.** Không dùng một cơ chế để mặc định thay thế tất cả.

Khi phân tích một request Cassandra, hãy trả lời theo thứ tự: **partition key nào? token nào? replica nào trong từng data center? node nào đang làm coordinator? CL yêu cầu bao nhiêu ACK? những replica nào thực sự phản hồi?** Chuỗi câu hỏi này giải thích được phần lớn hiện tượng timeout, ghi vẫn thành công khi một node lỗi, hoặc đọc cũ khi hạ consistency level.
