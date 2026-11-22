# Prepared statement, bind và định tuyến theo khóa

> **Chương:** Tối ưu truy vấn  
> **Phạm vi:** Apache Cassandra — cơ sở dữ liệu phân tán theo mô hình wide-column, thiết kế bảng theo truy vấn, khóa phân vùng, replication, mức nhất quán đọc/ghi và truy cập bằng Java.

## 1. Tại sao ba khái niệm này đi cùng nhau?

Trong Cassandra, một truy vấn có thể được gửi đến bất kỳ nút nào đủ điều kiện làm **coordinator**. Coordinator xác định các replica giữ dữ liệu rồi tổ chức đọc hoặc ghi theo mức nhất quán được yêu cầu. Nếu ứng dụng biết trước phân vùng cần truy cập, driver có thể chọn một coordinator phù hợp hơn và giảm các bước chuyển tiếp giữa các nút.

Ba khái niệm có vai trò khác nhau nhưng bổ trợ cho nhau:

| Khái niệm | Vai trò | Điều không tự động bảo đảm |
|---|---|---|
| **Prepared statement** | Chuẩn bị một mẫu CQL ổn định, tái sử dụng metadata và mã định danh câu lệnh | Không biến truy vấn quét nhiều phân vùng thành truy vấn nhanh |
| **Bind** | Điền các giá trị có kiểu dữ liệu vào dấu giữ chỗ của câu lệnh | Không thay thế việc thiết kế đúng khóa phân vùng |
| **Định tuyến theo khóa (token-aware routing)** | Dùng khóa phân vùng đã bind để tính token, ưu tiên gửi yêu cầu tới replica thích hợp | Không thay đổi replication factor hay consistency level |

Mục tiêu tối ưu là: **thiết kế bảng theo truy vấn → ràng buộc đủ khóa phân vùng → dùng prepared statement và bind → để driver tận dụng token-aware routing**. Với truy vấn trải rộng nhiều phân vùng, tối ưu cú pháp hay sử dụng prepared statement không thể loại bỏ chi phí phân tán vốn có.

Sau bài này, bạn có thể:
- Nhận diện khi nào driver biết chính xác phân vùng của một truy vấn.
- Dùng prepared statement và bind đúng kiểu dữ liệu trong Java.
- Phân biệt coordinator, replica, partition key, routing key và token.
- Giải thích vì sao định tuyến theo khóa không đồng nghĩa với mức nhất quán mạnh hơn.
- Kiểm tra và xử lý các tình huống prepared cache, metadata, truy vấn thiếu khóa và phân vùng quá lớn.

## 2. Bắt đầu từ bảng được thiết kế cho một truy vấn

Giả sử ứng dụng thường xuyên hỏi: “Lấy tối đa 20 sự kiện mới nhất của một khách hàng trong một ngày”. Một bảng Cassandra phù hợp có thể là:

~~~sql
-- Ví dụ dùng một datacenter tên dc1 có ít nhất 3 nút thích hợp.
CREATE KEYSPACE IF NOT EXISTS app
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS app.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    created_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), created_at, event_id)
) WITH CLUSTERING ORDER BY (created_at DESC, event_id ASC);
~~~

Trong lược đồ này:

- **Partition key** là cặp **(tenant_id, event_day)**. Tất cả sự kiện của cùng một khách hàng trong cùng ngày nằm trong một phân vùng logic.
- **Clustering columns** là **created_at, event_id**. Các hàng bên trong một phân vùng được sắp xếp theo thời điểm giảm dần, rồi theo mã sự kiện để phân biệt các hàng có cùng thời điểm.
- **Replica** là nút lưu bản sao của phân vùng theo replication strategy; ví dụ RF = 3 trong **dc1** nghĩa là ba bản sao logic trong datacenter đó khi topology cho phép.
- **Token** là kết quả hàm partitioner áp lên khóa phân vùng đã được tuần tự hóa. Token giúp ánh xạ phân vùng tới các vị trí trong vòng token và nhóm replica.

Truy vấn mục tiêu:

~~~sql
SELECT created_at, event_id, event_type, payload
FROM app.events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
LIMIT ?;
~~~

Hai điều kiện bằng trên **toàn bộ thành phần của partition key** giúp Cassandra xác định một phân vùng. Câu lệnh không cần **ALLOW FILTERING**. Giá trị **LIMIT** hạn chế số hàng trả về trong lần đọc; nó không giới hạn kích thước thực tế của phân vùng đã tích lũy.

> **Quy tắc thiết kế:** Nếu một khách hàng có thể tạo ra quá nhiều sự kiện trong một ngày, hãy xem lại kích thước bucket (ví dụ theo giờ) hoặc mô hình bảng. Prepared statement không chữa được phân vùng quá lớn. Quy ước xác định **event_day** từ timestamp và múi giờ nghiệp vụ phải nhất quán giữa lúc ghi và lúc đọc.

## 3. Prepared statement thực sự chuẩn bị gì?

Một prepared statement là **mẫu CQL với các bind marker**, thông thường ký hiệu bằng dấu hỏi. Ứng dụng chuẩn bị mẫu này một lần cho từng hình dạng truy vấn và tái sử dụng trong thời gian sống của session.

Luồng khái niệm:

~~~mermaid
sequenceDiagram
    participant A as Ứng dụng Java
    participant D as Cassandra driver
    participant N as Nút Cassandra
    A->>D: prepare(CQL có dấu ?)
    D->>N: PREPARE mẫu CQL
    N-->>D: ID câu lệnh và metadata biến
    D-->>A: PreparedStatement
    A->>D: bind(các giá trị)
    D->>D: Mã hóa giá trị, xác định routing key/token nếu đủ dữ liệu
    D->>N: EXECUTE ID + giá trị + tùy chọn request
    N-->>A: Kết quả qua driver
~~~

Các thông tin cần phân biệt:

1. **Chuẩn bị khác với thực thi.** Gọi prepare chưa đọc hay ghi dữ liệu của truy vấn; mỗi lần execute mới thực thi với các giá trị được bind.
2. **Prepared statement không phải stored procedure.** Nó không lưu logic nghiệp vụ hay giúp Cassandra tự tạo index phù hợp.
3. **Metadata bind quan trọng.** Driver biết vị trí và kiểu của các biến; với câu lệnh đủ điều kiện, nó có thể xác định biến nào thuộc partition key.
4. **Cache có phạm vi từng nút.** Các nút Cassandra quản lý cache prepared riêng. Khi nút khởi động lại, cache bị mất hoặc lược đồ thay đổi, có thể cần prepare lại; driver Java hiện đại thường xử lý tình huống server trả về **UNPREPARED**. Theo dõi lỗi/lần prepare bất thường thay vì giả định cache luôn tồn tại.
5. **Tái sử dụng mẫu ổn định.** Chuẩn bị lại trong mỗi request hoặc sinh hàng nghìn chuỗi CQL khác nhau (chẳng hạn nối literal vào câu lệnh) gây thêm network round-trip, CPU và áp lực cache.

Ví dụ, ba lần đọc dưới đây nên chia sẻ **cùng một** prepared statement và chỉ thay các giá trị **tenant_id**, **event_day**, **LIMIT**. Không cần xây một CQL string mới cho mỗi khách hàng.

## 4. Bind: giá trị, kiểu dữ liệu và giới hạn

Với mẫu:

~~~sql
SELECT created_at, event_id, event_type, payload
FROM app.events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
LIMIT ?;
~~~

Thứ tự bind tương ứng là:

| Vị trí | Kiểu CQL | Kiểu Java driver 4.x thông dụng | Ý nghĩa |
|---|---|---|---|
| 0 | uuid | java.util.UUID | tenant_id |
| 1 | date | java.time.LocalDate | event_day |
| 2 | int | int / Integer | Số hàng tối đa |

Bind làm việc ở mức **giá trị** với kiểu dữ liệu phù hợp. Nó giảm nguy cơ chèn CQL độc hại qua dữ liệu nhập vào và tránh tự ghép chuỗi escape thủ công. Tuy nhiên:

- Không thể dùng dấu hỏi để thay **tên bảng, tên cột, từ khóa CQL hoặc cấu trúc truy vấn**. Ví dụ, **SELECT * FROM ?** không phải cách chọn tên bảng bằng bind; tên đối tượng động phải được chọn từ danh sách cho phép và kiểm soát riêng.
- Với **partition key**, các thành phần bắt buộc phải có giá trị hợp lệ. Không bind **null** hoặc để unset cho khóa chính.
- Trong lệnh ghi/cập nhật, bind **null** vào cột không phải khóa có thể tạo tombstone; **unset** (khi giao thức/API hỗ trợ) mang nghĩa không cập nhật giá trị đó. Phân biệt hai trường hợp để tránh chi phí tombstone ngoài ý muốn.
- Không gán sai kiểu, ví dụ dùng chuỗi ngày tháng thay vì **LocalDate** cho cột **date**, hoặc dùng **UUID.randomUUID()** cho cột có kiểu **timeuuid**. Ví dụ trong bài dùng **uuid** nên UUID thông thường là phù hợp.
- Mỗi request nên tạo **BoundStatement** từ **PreparedStatement** dùng chung. Chú ý việc chia sẻ builder có trạng thái mutable giữa các luồng.

## 5. Vì sao bind đúng partition key giúp driver định tuyến?

Routing key là biểu diễn nhị phân của **toàn bộ partition key** theo quy tắc mã hóa Cassandra. Khi câu lệnh đã prepare và các bind marker của khóa phân vùng được gắn giá trị, driver có thể tạo routing key, tính token tương ứng rồi tra metadata topology/token map để chọn một nút điều phối phù hợp.

~~~mermaid
flowchart TD
    A["Prepared CQL + tenant_id + event_day"] --> B["Bind đủ các thành phần partition key"]
    B --> C["Driver mã hóa routing key"]
    C --> D["Tính token và tra token map"]
    D --> E["Ưu tiên coordinator phù hợp trong local DC"]
    E --> F["Coordinator liên hệ replica"]
    F --> G["Trả kết quả theo consistency level"]
~~~

Trong môi trường nhiều datacenter, chính sách cân bằng tải còn xét **local datacenter**, trạng thái nút, replica khả dụng và các chính sách request khác. **Token-aware** là một ưu tiên khi chọn coordinator, không phải cam kết rằng mọi lần thực thi đều vào cùng một nút. Retry, speculative execution, topology thay đổi hoặc metadata chưa đồng bộ có thể dẫn đến coordinator khác.

Cassandra cho phép cả **nút không giữ bản sao** làm coordinator. Nút đó vẫn có thể xử lý request bằng cách chuyển tiếp tới các replica, nhưng có thể tốn thêm một bước mạng. Lợi ích của token-aware routing là tăng cơ hội coordinator đã ở vị trí thuận lợi cho phân vùng cần truy cập.

### Trường hợp đủ hoặc thiếu thông tin định tuyến

| Hình dạng truy vấn | Một token cụ thể có xác định được không? | Hệ quả |
|---|---|---|
| **WHERE tenant_id = ? AND event_day = ?** | Thường có, khi cả hai giá trị được bind và driver có metadata cần thiết | Có thể token-aware |
| **INSERT** với đầy đủ các cột partition key được bind | Thường có | Có thể token-aware cho ghi |
| **WHERE tenant_id = ?** nhưng thiếu **event_day** | Không; với bảng mẫu truy vấn thường bị Cassandra từ chối do thiếu phần khóa | Phải thiết kế lại truy vấn hoặc bảng |
| **IN** trên partition key cho nhiều phân vùng | Không có một token đại diện cho tất cả | Không thể coi là một request đơn phân vùng |
| Điều kiện theo **token(...)** hoặc biểu thức khiến driver không suy ra khóa cụ thể | Có thể không | Có thể phải chọn coordinator theo chính sách dự phòng |
| Lọc theo cột thường, không ràng buộc partition key | Không | Dễ dẫn đến truy vấn không hợp lệ, quét nhiều phân vùng hoặc phải đổi mô hình dữ liệu |

**Lưu ý:** Khả năng suy ra routing key cụ thể phụ thuộc phiên bản driver, metadata lược đồ và cách viết CQL. Việc một truy vấn được server chấp nhận không đồng nghĩa driver chắc chắn tìm được token.

## 6. Ví dụ Java hoàn chỉnh với driver 4.x

Ví dụ dưới đây minh họa **prepare một lần**, bind nhiều giá trị, ghi một sự kiện, rồi đọc từ đúng phân vùng bằng **LOCAL_QUORUM**. Thư viện Java driver 4.x sử dụng các package **com.datastax.oss.driver.api**. Cần cài dependency **java-driver-core** tương thích trong dự án và kết nối tới Cassandra đang chạy.

~~~java
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public class CassandraPreparedRoutingDemo {
    public static void main(String[] args) {
        UUID tenantId = UUID.fromString(
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
        LocalDate eventDay = LocalDate.of(2026, 11, 21);
        Instant now = Instant.now();
        UUID eventId = UUID.randomUUID();

        // Thay dc1 và contact point bằng cấu hình cluster thực tế.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement insert = session.prepare(
                "INSERT INTO app.events_by_tenant_day " +
                "(tenant_id, event_day, created_at, event_id, " +
                " event_type, payload) VALUES (?, ?, ?, ?, ?, ?)");

            BoundStatement write = insert.bind(
                    tenantId, eventDay, now, eventId,
                    "login", "{\"success\":true}")
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            session.execute(write);

            PreparedStatement select = session.prepare(
                "SELECT created_at, event_id, event_type, payload " +
                "FROM app.events_by_tenant_day " +
                "WHERE tenant_id = ? AND event_day = ? LIMIT ?");

            BoundStatement read = select.bind(tenantId, eventDay, 20)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setPageSize(20);

            ResultSet result = session.execute(read);
            System.out.println(
                "Coordinator: " + result.getExecutionInfo().getCoordinator());

            for (Row row : result) {
                Instant createdAt = row.getInstant("created_at");
                UUID id = row.getUuid("event_id");
                String type = row.getString("event_type");
                String payload = row.getString("payload");
                System.out.printf("%s | %s | %s | %s%n",
                        createdAt, id, type, payload);
            }
        }
    }
}
~~~

Điều kiện chạy ví dụ:

- Keyspace/bảng ở mục 2 đã được tạo; datacenter của cluster thực sự có tên **dc1** hoặc bạn đã thay tên cho đúng.
- Với replication factor **3** và **LOCAL_QUORUM**, cần đủ replica ở datacenter cục bộ để đạt quorum. Một cluster chỉ có một nút không đáp ứng ví dụ RF = 3 và LOCAL_QUORUM một cách bình thường.
- Nếu viết ngày theo lịch nghiệp vụ, cần tính **eventDay** từ **now** theo múi giờ đã thống nhất; ở đây dùng ngày cố định để làm rõ thao tác bind.
- Ứng dụng thực tế nên đặt các đối tượng **PreparedStatement** vào thành phần được khởi tạo một lần cùng **CqlSession** dùng lâu dài, thay vì prepare trong mỗi lời gọi API. Ví dụ mở session trong **main** chỉ để chạy độc lập.

Khi đã có prepared statement, các lần đọc kế tiếp chỉ cần:

~~~java
BoundStatement anotherRead = select.bind(otherTenantId, otherDay, 20)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
ResultSet otherResult = session.execute(anotherRead);
~~~

Đoạn cuối được đặt trong phạm vi nơi **select**, **session**, **otherTenantId** và **otherDay** đã tồn tại; nó thể hiện cách tái sử dụng mẫu, không phải một chương trình Java độc lập.

### Truy vấn theo khoảng thời gian trong cùng phân vùng

Nếu cần lọc thêm các hàng của một ngày:

~~~sql
SELECT created_at, event_id, event_type
FROM app.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
  AND created_at >= ?
  AND created_at < ?
LIMIT ?;
~~~

Hai khóa phân vùng vẫn được ràng buộc bằng phép bằng; bộ lọc khoảng nằm trên clustering column **created_at**. Đây vẫn là truy vấn trong **một phân vùng** và có thể giữ lợi thế định tuyến theo khóa. Các điều kiện clustering phải tuân thủ quy tắc thứ tự cột của primary key.

## 7. Định tuyến và consistency level là hai quyết định độc lập

**Routing** trả lời câu hỏi: “Ứng dụng gửi request ban đầu tới coordinator nào?”  
**Consistency level** trả lời câu hỏi: “Coordinator cần bao nhiêu replica đáp ứng trước khi xác nhận kết quả?”

Ví dụ RF = 3 ở datacenter cục bộ:

| Consistency level | Cách hiểu ở mức đơn giản | Đổi token-aware routing có làm thay đổi yêu cầu này không? |
|---|---|---|
| **ONE** | Thường chỉ cần một replica xác nhận | Không |
| **LOCAL_QUORUM** | Cần đa số replica trong local DC; với RF = 3 là **2** | Không |
| **ALL** | Cần toàn bộ replica áp dụng cho thao tác theo ngữ nghĩa của mức này | Không |

Với mô hình RF = 3, đọc và ghi đều **LOCAL_QUORUM** trong cùng datacenter cho phép tập replica xác nhận đọc/ghi giao nhau (2 + 2 > 3), giúp tăng khả năng đọc thấy ghi đã xác nhận trong các điều kiện thông thường. Còn độ mới thực tế chịu ảnh hưởng bởi thao tác đồng thời, lỗi, timeout và các cơ chế của Cassandra. Định tuyến tới replica gần hơn **không** tự động nâng **ONE** thành **QUORUM**.

Tùy workload, mức nhất quán khác nhau tạo ra đánh đổi giữa độ trễ, tính sẵn sàng và số bản sao phải phản hồi. Các lệnh **lightweight transaction** với điều kiện **IF** còn liên quan đến serial consistency riêng; không nên đánh đồng với bind hay token-aware.

## 8. Những lỗi hiệu năng và vận hành thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Gọi prepare ở mỗi request | Tốn round-trip, xử lý lại và làm nhiễu cache | Prepare lúc khởi tạo, giữ statement dùng chung |
| Ghép literal trực tiếp vào CQL | Nhiều chuỗi query khác nhau, khó cache, có nguy cơ CQL injection | Dùng bind marker cho dữ liệu |
| Có bind nhưng đọc rất chậm | Truy vấn không khoanh vùng phân vùng, hoặc phân vùng quá lớn | Kiểm tra primary key, bucket và kích thước phân vùng |
| Không biết được routing key | Thiếu một phần khóa, dùng điều kiện phức tạp, thiếu metadata | Dùng equality trên đầy đủ partition key, kiểm tra metadata driver |
| Coordinator thay đổi giữa các lần chạy | Load balancing, retry, trạng thái nút hoặc topology đổi | Xem coordinator trong execution info và cấu hình driver |
| Lỗi **UNPREPARED** sau restart/schema change | Cache prepared phía nút không còn | Dùng driver có cơ chế reprepare, theo dõi nếu lỗi kéo dài |
| Nhiều timeout dù token-aware | Replica chậm, quorum không đủ, hotspot hoặc network quá tải | Đo latency theo node, kiểm tra replication/consistency và tải phân vùng |
| Ghi nhiều vào một partition key nóng | Partition và replica liên quan chịu áp lực lớn | Thiết kế thêm bucket hợp lý, phân bố khóa theo workload |
| Sử dụng **LIMIT** như biện pháp chia phân vùng | LIMIT chỉ cắt kết quả trả về | Giới hạn kích thước partition ngay từ mô hình dữ liệu |
| Đặt mọi truy vấn vào một BATCH lớn | BATCH không phải công cụ tăng tốc truy vấn đa phân vùng | Chỉ dùng BATCH khi cần ngữ nghĩa phù hợp, đánh giá chi phí |

### Prepared không thay thế chăm sóc dữ liệu phân tán

- **Replication:** đảm bảo replication strategy và số replica thực tế phù hợp topology.
- **Compaction:** theo dõi SSTable và chi phí đọc/ghi; đọc chậm có thể xuất phát từ nhiều SSTable, tombstone hoặc compaction backlog.
- **Repair:** sửa khác biệt giữa replica theo lịch vận hành; chuẩn bị truy vấn không giúp replica tự nhất quán.
- **Xử lý lỗi:** tách lỗi kết nối/coordinator, timeout không rõ kết quả ghi, lỗi truy vấn CQL, và lỗi schema. Retry chỉ khi hiểu tính idempotent của thao tác; không tự tăng số lần retry vô hạn.
- **Observability:** theo dõi độ trễ, timeout, số lần prepare/reprepare, tải node, tombstone, kích thước partition và coordinator được chọn.

## 9. Cách kiểm chứng trong môi trường thực hành

1. **Kiểm tra schema.** Xác nhận khóa chính thật sự là **((tenant_id, event_day), created_at, event_id)**. Nếu ứng dụng có mẫu truy vấn khác (ví dụ tìm theo **event_type** trên nhiều ngày), hãy thiết kế bảng truy vấn tương ứng thay vì ép bảng này xử lý bằng lọc tràn lan.
2. **Chạy Java demo.** Quan sát dòng **Coordinator** lấy từ **result.getExecutionInfo()**. Lặp lại với nhiều partition key để thấy node điều phối có thể thay đổi theo token, topology và chính sách chọn node.
3. **Giữ nguyên statement, thay bind.** Truy vấn cùng mẫu cho khách hàng/ngày khác; kiểm chứng dữ liệu trả về chỉ thuộc phân vùng yêu cầu.
4. **Thử truy vấn thiếu khóa.** Chạy trong môi trường thử nghiệm điều kiện chỉ có **tenant_id = ?**. Quan sát lỗi hoặc giới hạn CQL và giải thích vì sao không thể xác định một phân vùng.
5. **So sánh truy vấn trong một phân vùng với nhiều phân vùng.** Đo độ trễ p50/p95, số request, kích thước kết quả và tải replica. So sánh trên dữ liệu đủ lớn, có kiểm soát để tránh kết luận chỉ từ một lần đo.
6. **Theo dõi hệ thống.** Khi cần, dùng query tracing có kiểm soát và chỉ số driver/cluster để xác minh coordinator, replica liên hệ và bước tốn thời gian. Tracing có overhead; không bật đại trà cho toàn bộ lưu lượng production.

**Câu hỏi tự kiểm tra**

1. Bảng có partition key ghép **(tenant_id, event_day)**. Chỉ bind **tenant_id** thì driver tính được chính xác token chưa? Vì sao?
2. Dùng **LOCAL_QUORUM** có bảo đảm driver gửi request đến replica cục bộ không? Vai trò của chính sách chọn coordinator là gì?
3. Nếu mọi request đều dùng prepared statement nhưng truy vấn vẫn cần quét hàng trăm phân vùng, nên sửa ở tầng nào trước?
4. Vì sao không nên tạo câu CQL mới bằng cách nối một **UUID** khác nhau vào chuỗi truy vấn mỗi lần?
5. Khi nút coordinator khởi động lại và mất cache prepared, điều gì phải xảy ra để các lần execute tiếp tục hoạt động?

**Đáp án gợi ý:** (1) Chưa, vì thiếu một thành phần khóa phân vùng; (2) không, consistency và routing là hai cơ chế khác nhau; (3) thiết kế bảng và mẫu truy vấn; (4) phá khả năng tái sử dụng mẫu, thêm chi phí prepare và nguy cơ ghép chuỗi; (5) prepare lại trên nút cần thiết rồi thực thi, thông thường do driver xử lý.

## 10. Tổng kết

Để truy vấn Cassandra hiệu quả, hãy bắt đầu từ **access pattern** và **partition key**, sau đó dùng **prepared statement** để tái sử dụng mẫu CQL và **bind** đúng kiểu để chuyển dữ liệu cho mỗi lần thực thi. Khi driver suy ra đủ khóa phân vùng, nó có thể tận dụng **token-aware routing** để chọn coordinator thuận lợi hơn. Cách chọn coordinator chỉ tối ưu đường đi của request; tính đúng đắn, mức nhất quán và chi phí đọc/ghi còn phụ thuộc vào replication, consistency level, kích thước phân vùng, compaction, repair và trạng thái cluster.
