# SimpleStrategy trong thực nghiệm và giới hạn lựa chọn topology

> **Chương:** Token và sao chép  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra, hệ cơ sở dữ liệu phân tán theo mô hình wide-column.

Một bản ghi Cassandra không thuộc về một máy cố định chỉ vì ứng dụng kết nối tới máy đó. Cassandra băm **partition key** thành **token**, xác định các node sở hữu khoảng token rồi dùng **replication strategy** của *keyspace* để chọn những node lưu bản sao. `SimpleStrategy` là cách đơn giản nhất để nhìn thấy quá trình này trong phòng thực hành; chính sự đơn giản ấy khiến nó không phù hợp khi hệ thống có nhiều rack hoặc datacenter.

Sau bài này, người học có thể:

- Giải thích cách `SimpleStrategy` chọn các node chứa replica từ vòng token, kể cả khi bật virtual nodes (vnodes).
- Tạo keyspace, ghi và đọc dữ liệu bằng CQL; đối chiếu replica thực tế bằng `nodetool`.
- Dự đoán hành vi khi một node lỗi ở các mức nhất quán `ONE`, `QUORUM` và `ALL`.
- Chỉ ra vì sao replication factor (RF) không đồng nghĩa với khả năng chịu lỗi rack/datacenter.
- Chọn `NetworkTopologyStrategy` cho topology thực tế và hiểu công việc vận hành khi đổi strategy.

## 1. SimpleStrategy chọn replica như thế nào?

### 1.1. Từ partition key tới tập replica

Xét bảng lưu số đo theo thiết bị:

~~~sql
CREATE TABLE events_by_device (
    device_id uuid,
    event_time timestamp,
    event_type text,
    measurement double,
    PRIMARY KEY ((device_id), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Trong khóa chính trên, `device_id` là **partition key**; `event_time` là **clustering column**. Mọi hàng có cùng `device_id` thuộc cùng một partition. Với partitioner thông dụng `Murmur3Partitioner`, Cassandra tính token từ partition key (không tính riêng token cho từng hàng theo `event_time`). Token quyết định vị trí logic của partition trên ring.

Mỗi **keyspace** chọn một replication strategy. Nếu keyspace dùng:

~~~sql
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 3
}
~~~

thì đối với mỗi partition, Cassandra tìm **ba node vật lý khác nhau** theo thứ tự token trên vòng. Quy trình khái quát là:

1. Tính token của partition key, tìm khoảng token chứa nó và node chịu trách nhiệm đầu tiên.
2. Duyệt các token kế tiếp theo chiều vòng tròn (clockwise), kể cả khi đi qua điểm cuối rồi quay về đầu.
3. Chỉ nhận thêm một replica nếu token tiếp theo thuộc **node vật lý chưa có trong tập replica**.
4. Dừng khi chọn đủ `RF` node khác nhau.

Điểm mấu chốt: `SimpleStrategy` **không xét datacenter, rack hoặc availability zone** trong bước chọn replica. Nó xét vị trí trên token ring. Một node có thể sở hữu nhiều vnode/token; đi qua hai token của cùng node không tạo ra hai bản sao độc lập.

### 1.2. Ví dụ ring rút gọn

Giả sử mỗi node chỉ có một token để dễ minh họa, và các token giả định có thứ tự `10 → 30 → 60 → 90 → 10`:

~~~mermaid
flowchart LR
    A["Node A · token 10"] --> B["Node B · token 30"]
    B --> C["Node C · token 60"]
    C --> D["Node D · token 90"]
    D --> A
~~~

| Token của partition | Node đầu tiên | RF = 1 | RF = 2 | RF = 3 |
|---|---|---|---|---|
| `25` | B | B | B, C | B, C, D |
| `75` | D | D | D, A | D, A, B |
| `5` | A | A | A, B | A, B, C |

Ví dụ này chỉ mô tả **thuật toán chọn node**. Token thực của Murmur3 nằm trong miền số nguyên 64 bit có dấu; trong cluster dùng vnodes, một node có nhiều vị trí trên ring và kết quả không đơn giản là lấy ba node có tên đứng cạnh nhau.

**Phân biệt ba khái niệm:**

| Khái niệm | Trả lời câu hỏi nào? | Quyết định bởi |
|---|---|---|
| Partition key/token | Partition nằm ở vị trí logic nào? | Thiết kế khóa bảng và partitioner |
| Replication strategy/RF | Những node nào phải giữ các bản sao? | Cấu hình replication của keyspace và topology ring |
| Consistency level (CL) | Bao nhiêu replica phải phản hồi để yêu cầu được coi là thành công? | Từng thao tác đọc/ghi của client/coordinator |

RF = 3 nghĩa là **ba node được chỉ định lưu bản sao**, không có nghĩa mọi yêu cầu ghi đều phải chờ cả ba node trả lời. Điều đó còn tùy CL.

## 2. Thực hành trên cluster một datacenter

### 2.1. Môi trường và điều kiện

Chuẩn bị **cluster Cassandra thử nghiệm có ít nhất ba node hoạt động** trong một datacenter, quyền sử dụng `cqlsh` và `nodetool`. Các lệnh minh họa dùng cú pháp Cassandra/CQL phổ biến ở các bản 4.x–5.x; địa chỉ node, tên container và cách khởi động tùy môi trường. Không thực hiện bài thử dừng node trên cluster đang phục vụ dữ liệu thực.

Trên một node, kiểm tra:

~~~bash
nodetool status
~~~

Đọc các cột `Status/State` (ví dụ `UN` là Up/Normal), `Tokens`, `Datacenter` và `Rack`. Ít nhất ba node cần ở trạng thái hoạt động trước thử nghiệm RF = 3. Cột `Tokens` thường lớn hơn một khi dùng vnodes; điều này **không** làm tăng số bản sao trên cùng một node.

### 2.2. Tạo keyspace và bảng

Mở `cqlsh` và chạy:

~~~sql
CREATE KEYSPACE IF NOT EXISTS lab_simple
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 3
}
AND durable_writes = true;

USE lab_simple;

CREATE TABLE IF NOT EXISTS events_by_device (
    device_id uuid,
    event_time timestamp,
    event_type text,
    measurement double,
    PRIMARY KEY ((device_id), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);

INSERT INTO events_by_device
    (device_id, event_time, event_type, measurement)
VALUES
    (d654b0fe-7357-497f-8db4-59b165d58a0f,
     '2026-11-21T09:00:00Z', 'temperature', 28.5);

INSERT INTO events_by_device
    (device_id, event_time, event_type, measurement)
VALUES
    (d654b0fe-7357-497f-8db4-59b165d58a0f,
     '2026-11-21T09:01:00Z', 'temperature', 28.7);
~~~

Hai hàng có cùng `device_id` đi vào **cùng partition**, nên có cùng tập replica theo quy tắc của keyspace. Câu truy vấn theo partition key phù hợp với thiết kế bảng theo truy vấn:

~~~sql
SELECT device_id, event_time, event_type, measurement
FROM events_by_device
WHERE device_id = d654b0fe-7357-497f-8db4-59b165d58a0f
ORDER BY event_time DESC
LIMIT 10;
~~~

Lưu ý: `IF NOT EXISTS` không cập nhật keyspace đã tồn tại. Nếu tên `lab_simple` đã được dùng, kiểm tra cấu hình hiện có và chọn tên lab mới trước khi so sánh; không suy luận rằng lệnh tạo đã đổi RF.

### 2.3. Xác minh ai là replica

Trong `cqlsh`:

~~~text
DESCRIBE KEYSPACE lab_simple
~~~

Kết quả cần thể hiện `SimpleStrategy` và `replication_factor = 3`. Tiếp theo, trên máy có `nodetool`:

~~~bash
nodetool getendpoints lab_simple events_by_device d654b0fe-7357-497f-8db4-59b165d58a0f
~~~

Lệnh `getendpoints` liệt kê các **endpoint được chỉ định sở hữu partition key**; với RF = 3 và đủ node vật lý, mong đợi ba endpoint khác nhau. Đối chiếu IP/node với `nodetool status`, đặc biệt cột datacenter và rack. Việc endpoint xuất hiện **không chứng minh** bản sao đã được đồng bộ hoàn toàn hoặc node đó đang Up: đây là danh sách chủ sở hữu theo metadata.

Ghi kết quả vào bảng quan sát:

| Bằng chứng | Cần ghi lại | Cách đọc |
|---|---|---|
| `DESCRIBE KEYSPACE` | Strategy, RF | Xác minh cấu hình ở cấp keyspace |
| `nodetool status` | Danh sách node, DC/rack, `UN`/`DN` | Xác minh topology và tình trạng sống |
| `nodetool getendpoints` | Các IP replica của một `device_id` | Đối chiếu RF với node được chọn |
| Truy vấn CQL | Dữ liệu của partition | Kiểm tra đường đọc ở CL đang chọn |

Để so sánh RF = 1, 2, 3, có thể lập **các keyspace thử nghiệm riêng** (mỗi keyspace một RF) với cùng cấu trúc bảng; nếu dùng cách này, cần tạo bảng trong từng keyspace trước khi chạy `getendpoints`. Kết quả dự kiến là một, hai, ba **node vật lý khác nhau** trên ring. Cách này tránh việc thay đổi RF giữa các lần đo rồi hiểu nhầm các bản sao mới đã được chuyển dữ liệu ngay lập tức.

## 3. Thử độ sẵn sàng và mức nhất quán

### 3.1. Vì sao RF và CL phải được xét cùng nhau?

Với RF = 3, điều kiện số replica phản hồi của các CL thường dùng là:

| CL | Số replica cần phản hồi với RF = 3 | Khi một trong ba replica Down |
|---|---:|---|
| `ONE` | 1 | Thường vẫn đọc/ghi được nếu replica khác còn truy cập được |
| `QUORUM` | `floor(3/2) + 1 = 2` | Thường vẫn đọc/ghi được nếu còn hai replica khả dụng |
| `ALL` | 3 | Không đáp ứng được CL do thiếu một replica |

Với RF = 2, `QUORUM = 2`; với RF = 1, `QUORUM = 1`. Không nên nói đơn giản rằng “QUORUM luôn chịu được một node hỏng”.

Trong `cqlsh`, lệnh:

~~~text
CONSISTENCY QUORUM
~~~

đặt CL mặc định cho các thao tác sau đó trong phiên shell; đây là **lệnh của cqlsh**, không phải câu lệnh CQL để đưa vào file schema. Thử truy vấn từ mục 2.2, sau đó đặt:

~~~text
CONSISTENCY ONE
~~~

và đọc lại. Việc cả hai truy vấn đều thành công khi không có lỗi là điều bình thường; thí nghiệm hữu ích nhất khi có sự khác biệt về số replica sẵn sàng.

Trong trường hợp ghi thành công ở CL = `QUORUM` và đọc ở `QUORUM` trên cùng tập RF = 3, hai tập phản hồi kích thước hai phải giao nhau (`2 + 2 > 3`). Đây là cơ sở của bảo đảm nhất quán theo quorum đối với một lịch sử không có ghi cạnh tranh. Nó **không** tự biến Cassandra thành giao dịch tuần tự tuyến tính cho mọi trường hợp: ghi đồng thời, timestamp, giải quyết xung đột và các thao tác điều kiện cần được xem xét riêng.

### 3.2. Thử lỗi node trong môi trường cô lập

1. Xác nhận ba node đang `UN` và đã ghi dữ liệu ở CL phù hợp (ví dụ `QUORUM`).
2. Dừng **một** node bằng cơ chế quản lý lab/container đang dùng; không tắt thêm node hoặc thay đổi dữ liệu thủ công.
3. Đợi trạng thái `nodetool status` phản ánh node Down (phát hiện lỗi không nhất thiết tức thì).
4. Thử đọc và ghi vào cùng partition với `ONE`, `QUORUM`, `ALL`; ghi lại thành công, lỗi và độ trễ.
5. Khởi động lại node, xác minh trạng thái trở về `UN`, sau đó theo dõi việc đồng bộ replica. Hinted handoff có thể hỗ trợ dữ liệu bị lỡ trong điều kiện thích hợp nhưng không thay thế chính sách `repair`.

Trên cluster đúng ba node và RF = 3, kết quả điển hình là `ONE` và `QUORUM` vẫn khả dụng khi một replica Down, còn `ALL` báo không đủ replica. Nếu quan sát khác, kiểm tra RF thực tế, danh sách endpoint, tình trạng node, sự chậm trễ phát hiện lỗi và khả năng kết nối tới coordinator trước khi kết luận.

**Phân biệt thành công và dữ liệu mới nhất:** CL = `ONE` có thể nhận phản hồi từ replica chưa thấy một cập nhật gần đây. CL = `QUORUM` làm tăng yêu cầu đồng thuận giữa các replica nhưng phải trả giá bằng số phản hồi cần chờ và khả năng sẵn sàng khi lỗi. Không có chiến lược replica nào thay thế việc chọn CL theo yêu cầu ứng dụng.

## 4. Giới hạn topology: SimpleStrategy không biết rack/datacenter

### 4.1. Trên nhiều datacenter, RF là một con số cho toàn cluster

Xem cluster giả định có bốn node, mỗi node một token:

| Node | Token minh họa | Datacenter | Rack |
|---|---:|---|---|
| A | 10 | `dc1` | `rack-a` |
| B | 30 | `dc1` | `rack-a` |
| C | 60 | `dc2` | `rack-b` |
| D | 90 | `dc2` | `rack-b` |

Với `SimpleStrategy`, RF = 3:

| Partition token | Replica | Trong `dc1` | Trong `dc2` |
|---|---|---:|---:|
| 25 | B, C, D | 1 | 2 |
| 75 | D, A, B | 2 | 1 |

Cùng một keyspace, partition khác nhau có số replica trong từng DC khác nhau. Vì vậy không thể cam kết “mỗi datacenter luôn có hai bản sao” bằng cách tăng RF của `SimpleStrategy`. Với vnodes, các token đan xen hơn nhưng quy tắc chọn vẫn **không bảo đảm phân bổ theo DC**.

Nếu `dc1` mất kết nối và ứng dụng ở `dc2` cần đọc ở mức quorum toàn cluster, partition token 75 chỉ còn một replica ở `dc2` nên không thể đạt `QUORUM = 2`, dù `dc2` vẫn còn hai node hoạt động. Tình trạng ngược lại có thể xảy ra với partition khác khi `dc2` lỗi.

### 4.2. Nhiều bản sao vẫn có thể cùng một điểm lỗi

Đổi ví dụ: A, B, C cùng một rack (hoặc một availability zone), D ở rack khác. Với token 5 và RF = 3, tập replica là **A, B, C**, tức cả ba bản sao cùng rack. Mất rack đó đồng thời làm mất mọi replica của partition, dù RF ghi trong schema vẫn là 3.

Đây là khác biệt giữa **node-level redundancy** và **failure-domain redundancy**:

- `SimpleStrategy` có thể giảm rủi ro khi một **node đơn lẻ** hỏng, miễn còn đủ replica và CL cho phép.
- Nó không chủ động phân tán bản sao giữa **rack, zone hoặc datacenter** để phòng sự cố chung.
- Ngay cả lúc nhìn thấy số bản sao phân bố đều trên một vài partition, đó chỉ là **quan sát của topology hiện tại**, không phải cam kết của strategy sau khi thêm/bớt node, thay token hoặc mở rộng cluster.

Không nên dùng `LOCAL_ONE` hay `LOCAL_QUORUM` như một cách “sửa” `SimpleStrategy` trong cluster nhiều DC. Các CL mang tính cục bộ chỉ hữu ích khi thiết kế replica thực sự đáp ứng yêu cầu đặt bản sao trong từng DC. `SimpleStrategy` không có tham số RF theo DC để đảm bảo điều đó.

## 5. Khi nào dùng SimpleStrategy, khi nào chọn NetworkTopologyStrategy?

| Tiêu chí | `SimpleStrategy` | `NetworkTopologyStrategy` (NTS) |
|---|---|---|
| Khai báo số replica | Một `replication_factor` cho toàn cluster | RF riêng theo từng datacenter |
| Cách chọn replica | Theo token ring; bỏ qua rack/DC | Theo token ring, xét DC và cố gắng phân tán rack trong mỗi DC |
| Lab nhỏ, thử token và CQL | Phù hợp để học cơ chế | Cũng sử dụng được, cần topology/snitch đúng |
| Cluster production một DC | Không được khuyến nghị | Được khuyến nghị, kể cả khi hiện tại chỉ có một DC |
| Nhiều DC, yêu cầu đọc/ghi cục bộ | Không bảo đảm phân bổ replica theo DC | Phù hợp với RF theo DC và các CL cục bộ |
| Chịu lỗi rack | Không có quy tắc phân tán rack | Cố gắng đặt replica vào các rack khác nhau khi topology cho phép |

Ví dụ NTS cho một DC có **ít nhất ba node**:

~~~sql
CREATE KEYSPACE app_events
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;
~~~

Ví dụ NTS cho hai DC, **mỗi DC có đủ ba node**:

~~~sql
CREATE KEYSPACE app_events_multi_dc
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
}
AND durable_writes = true;
~~~

Lúc này với mỗi partition, mục tiêu là **ba replica trong `dc1` và ba replica trong `dc2`** (tổng sáu node vật lý), khác hẳn `SimpleStrategy` với RF = 3 chỉ chọn ba node trong toàn cluster. Ứng dụng đặt CL = `LOCAL_QUORUM` ở một DC có RF = 3 thường cần hai replica **trong DC đó** phản hồi, giảm phụ thuộc đường mạng liên DC đối với yêu cầu cục bộ.

Tên `dc1`/`dc2` phải **khớp chính xác, có phân biệt chữ hoa/thường** với tên datacenter do Cassandra/snitch báo ra. Cần cấu hình snitch và rack phù hợp từ lúc xây dựng cluster. NTS cố phân bố replica qua các rack hiện hữu; nếu rack quá ít so với RF thì không thể có một bản sao riêng trên mỗi rack. NTS không khắc phục được việc khai báo rack sai hoặc đặt tất cả node trong cùng một miền lỗi vật lý.

**Quy tắc chọn nhanh:** dùng `SimpleStrategy` để minh họa thuật toán trong lab tách biệt. Với môi trường chuẩn bị vận hành thật, chọn `NetworkTopologyStrategy` từ đầu, kể cả mới có một datacenter, và kiểm tra topology vật lý trước khi quyết định RF.

## 6. Chuyển từ SimpleStrategy sang NTS: schema mới chưa phải dữ liệu đã đúng chỗ

Giả sử keyspace `lab_simple` đang dùng `SimpleStrategy` RF = 3 và ba node đều thuộc datacenter `dc1`. Sau khi kiểm tra tên DC bằng `nodetool status` và xác nhận cấu hình snitch/rack đúng, có thể đổi metadata bằng:

~~~sql
ALTER KEYSPACE lab_simple
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
~~~

Tuy nhiên **`ALTER KEYSPACE` chỉ đổi cách Cassandra xác định các replica mong muốn**. Nó không có nghĩa mọi replica mới đã lập tức nhận đủ dữ liệu lịch sử. Kế hoạch vận hành thực tế cần:

1. Kiểm kê node, số rack/DC, tên DC từ snitch, RF hiện tại, các ứng dụng và CL đang dùng; sao lưu/đảm bảo đường khôi phục phù hợp.
2. Xác định topology đích và khả năng chứa dữ liệu; nếu bổ sung DC mới, lập quy trình bootstrap/streaming/migration riêng thay vì chỉ thêm tên DC vào CQL.
3. Thay cấu hình replication của keyspace; xác minh schema đã thống nhất và metadata đúng.
4. Thực hiện **full repair** trên các node bị ảnh hưởng theo runbook của phiên bản Cassandra đang vận hành để phân phối và đồng bộ dữ liệu sau thay đổi vị trí hoặc tăng RF; theo dõi tải đĩa, mạng và thời gian hoàn tất.
5. Kiểm tra lại endpoint cho các partition mẫu, xác minh từng datacenter và chạy thử các mức nhất quán ứng dụng dự kiến sử dụng.

Ví dụ lệnh repair trên node cần xử lý:

~~~bash
nodetool repair --full lab_simple
~~~

Full repair có chi phí I/O và mạng đáng kể; chạy theo kế hoạch bảo trì và phạm vi các node bị ảnh hưởng, không đồng loạt thiếu kiểm soát. Trong cluster thật, việc chuyển DC, đổi snitch hoặc đổi cách gán rack có ràng buộc vận hành theo phiên bản và có thể cần quy trình di chuyển riêng. Không thay đổi nhãn rack/DC của cluster đang chạy một cách tùy tiện.

**Phân biệt với compaction:** compaction gộp và sắp xếp lại SSTable cục bộ trên một node; nó không chọn replica cho partition và không thay thế anti-entropy repair giữa các node. Hinted handoff cũng không phải bảo đảm đồng bộ vô thời hạn.

## 7. Liên hệ thiết kế bảng và Java client

Việc dùng `SimpleStrategy` hay NTS **không thay đổi** khóa phân vùng của bảng. Với `PRIMARY KEY ((device_id), event_time)`, ứng dụng đọc các sự kiện của một thiết bị bằng `WHERE device_id = ?`, còn `event_time` sắp thứ tự bên trong partition. Nếu một thiết bị tạo lượng dữ liệu quá lớn, partition có thể trở nên quá rộng hoặc quá nóng; tăng RF không giải quyết được thiết kế partition key chưa phù hợp.

Khi kết nối từ Java, replication strategy được cấu hình **phía Cassandra/keyspace**, còn CL có thể chọn **theo request** của driver. Ví dụ với Java Driver 4.x, trên một `CqlSession` đã kết nối:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.util.UUID;

UUID deviceId = UUID.fromString("d654b0fe-7357-497f-8db4-59b165d58a0f");

SimpleStatement statement = SimpleStatement.builder(
        "SELECT event_time, measurement " +
        "FROM lab_simple.events_by_device WHERE device_id = ? LIMIT 10")
    .addPositionalValue(deviceId)
    .setConsistencyLevel(DefaultConsistencyLevel.QUORUM)
    .build();

session.execute(statement);
~~~

Ở môi trường NTS nhiều DC, ứng dụng thường chọn datacenter cục bộ cho driver và cân nhắc `LOCAL_QUORUM` theo yêu cầu sẵn sàng, độ trễ và tính nhất quán. CL của Java không thể buộc `SimpleStrategy` phân phối replica theo DC; đó là trách nhiệm của replication strategy.

## 8. Bài tập tình huống và tự kiểm tra

**Tình huống A — đọc bảng ring:** Bốn node có token 10/30/60/90 theo vòng A/B/C/D; partition có token 75 và `SimpleStrategy` RF = 3. Replica là node nào?

<details>
<summary>Đáp án</summary>

Đi từ D (token 90), vòng qua A (token 10), rồi B (token 30): **D, A, B**. Nếu dùng vnodes, cần xem token ring thực tế; không áp dụng máy móc thứ tự tên node.
</details>

**Tình huống B — giới hạn rack:** Ba replica đều ở ba node khác nhau nhưng cùng rack. RF = 3 có bảo đảm chịu được sự cố cả rack không?

<details>
<summary>Đáp án</summary>

**Không.** Ba node vẫn thuộc một miền lỗi chung. `SimpleStrategy` không xét rack khi chọn replica. Muốn có khả năng phân tán rack, chọn NTS cùng topology/snitch được cấu hình đúng.
</details>

**Tình huống C — thay RF:** Keyspace RF = 2 được đổi thành RF = 3, `ALTER KEYSPACE` trả thành công. Có thể kết luận dữ liệu lịch sử đã đủ ba bản sao chưa?

<details>
<summary>Đáp án</summary>

**Chưa.** Metadata chọn replica thay đổi trước khi toàn bộ dữ liệu cũ được chuyển/đối soát. Cần quy trình full repair và xác minh trên các node liên quan.
</details>

**Tình huống D — topology production:** Một cluster hiện chỉ có một datacenter, nhưng dự kiến mở rộng sang datacenter thứ hai. Nên bắt đầu với strategy nào?

<details>
<summary>Đáp án</summary>

**NetworkTopologyStrategy**, khai báo RF của datacenter hiện tại, cấu hình topology đúng và lên kế hoạch mở rộng DC khi cần. Đây cũng là lựa chọn được khuyến nghị cho production một DC.
</details>

### Checklist hoàn thành lab

- [ ] Giải thích được vì sao hai hàng cùng partition key có cùng tập replica.
- [ ] Đọc được strategy/RF bằng `DESCRIBE KEYSPACE` và node/DC/rack bằng `nodetool status`.
- [ ] Dùng `getendpoints` để quan sát đúng số node vật lý chứa replica theo RF.
- [ ] Phân biệt RF với CL và tính được quorum cho RF = 1, 2, 3.
- [ ] Chứng minh bằng ví dụ rằng `SimpleStrategy` không bảo đảm replica theo rack/DC.
- [ ] Biết khi nào phải dùng NTS và vì sao đổi replication metadata có thể cần full repair.

## Tài liệu tham khảo

1. Apache Cassandra Documentation — [Dynamo: Replication Strategy, SimpleStrategy, NetworkTopologyStrategy](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html).
2. Apache Cassandra Documentation — [CQL: Data Definition, CREATE/ALTER KEYSPACE](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html).
3. Apache Cassandra Documentation — [nodetool getendpoints](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/getendpoints.html) và [cqlsh CONSISTENCY](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html).
4. Apache Cassandra Documentation — [Repair và full repair khi thay đổi RF](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html), [Production recommendations](https://cassandra.apache.org/doc/stable/cassandra/getting-started/production.html).
