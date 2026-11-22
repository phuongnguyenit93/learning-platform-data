# Native protocol, cổng truy cập ứng dụng và tương thích giao thức

## 1. Native protocol giữ vai trò gì trong Apache Cassandra?

Trong kiến trúc wide-column phân tán của **Apache Cassandra**, ứng dụng gửi truy vấn CQL tới một node làm **coordinator**; node này định tuyến và phối hợp các replica dựa trên partition key, replication factor và consistency level. **Cassandra native protocol**, còn gọi là *CQL binary protocol*, là giao thức mạng mà các client như `cqlsh` và **Java Driver** sử dụng để trao đổi lệnh và kết quả với Cassandra.

Native protocol hoạt động trên kết nối **TCP** và truyền thông điệp dạng nhị phân. Nó hỗ trợ những hoạt động như khởi tạo phiên, xác thực, thực thi CQL, prepared statement, batch, paging và thông báo thay đổi topology/schema. Client không cần tự viết giao thức: driver đảm nhiệm kết nối, đóng gói thông điệp, chuyển kiểu dữ liệu, chọn coordinator và xử lý nhiều lỗi kết nối.

Đây là nội dung thuộc chương **Công cụ và kết nối** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Hiểu lớp giao thức giúp liên hệ bài thực hành CQL với kiến trúc cluster, mức nhất quán đọc/ghi, khả năng chịu lỗi và triển khai Java ngoài thực tế.

Sau bài học, bạn có thể:

1. Phân biệt **native client-to-node** với **giao tiếp giữa các node** và cổng quản trị.
2. Xác định đúng host, port, địa chỉ lắng nghe, địa chỉ công bố và cấu hình TLS cho ứng dụng.
3. Mô tả quá trình driver kết nối, thương lượng phiên bản giao thức và khám phá topology.
4. Thực hành kết nối bằng cqlsh và Java Driver, hiểu tại sao một truy vấn phải có partition key phù hợp.
5. Chẩn đoán vấn đề cổng mạng, xác thực, chứng chỉ, định tuyến, phiên bản driver và native protocol.

## 2. Phân biệt CQL, native protocol và kết nối nội bộ cluster

Ba lớp sau không đồng nghĩa với nhau:

| Thành phần | Ví dụ | Nhiệm vụ |
| --- | --- | --- |
| **Ngôn ngữ CQL** | `SELECT ... WHERE device_id = ?` | Biểu diễn truy vấn và thay đổi schema/dữ liệu. |
| **Native binary protocol** | `QUERY`, `PREPARE`, `EXECUTE`, `RESULT` | Chuyển truy vấn, tham số, kết quả, lỗi và sự kiện giữa driver/cqlsh và Cassandra. |
| **Giao tiếp internode** | Node trao đổi dữ liệu với các replica khác | Gossip, replication, streaming và phối hợp nội bộ cluster. |

Trong mô hình dưới đây, ứng dụng kết nối trực tiếp vào native port của các node; các node trao đổi với nhau qua kênh riêng. Tùy cấu hình, **mỗi request có thể chọn một coordinator khác nhau**.

~~~mermaid
flowchart LR
    A["Ứng dụng Java / cqlsh"] -->|"Native TCP: 9042 mặc định"| B["Node A<br/>coordinator của request 1"]
    A -->|"Native TCP: 9042 mặc định"| C["Node B<br/>coordinator của request 2"]
    B <-->|"Internode: cổng riêng"| C
    B <-->|"Internode: cổng riêng"| D["Node C / replica"]
    C <-->|"Internode: cổng riêng"| D
~~~

**Cần nhớ:** client kết nối được vào một node **không có nghĩa dữ liệu chỉ nằm trên node ấy**. Coordinator nhận request, định tuyến dựa trên token/partition key và replica của keyspace. Native protocol mang yêu cầu consistency của thao tác, nhưng mức đảm bảo thực tế còn phụ thuộc replication factor, trạng thái replica và truy vấn.

### 2.1. Native protocol không phải HTTP/REST

Một socket TCP mở ở cổng 9042 không có nghĩa có HTTP server. Không gửi URL hay JSON trực tiếp tới 9042 bằng trình duyệt hoặc `curl` rồi kỳ vọng nhận kết quả CQL. Client cần triển khai native protocol, hoặc dùng một driver/công cụ có sẵn.

Các proxy/API HTTP do tổ chức tự triển khai (nếu có) là **lớp riêng**; chúng không làm Cassandra native protocol tự trở thành HTTP.

## 3. Các cổng liên quan và phạm vi sử dụng

| Cổng mặc định/thường gặp | Chức năng | Ai thường kết nối? |
| --- | --- | --- |
| **9042/TCP** | **CQL native transport** | cqlsh, Java/Python/Node.js/C# driver và các client CQL khác. |
| **9142/TCP** | Cổng native TLS bổ sung **nếu được cấu hình** trong các bản hỗ trợ | Client dùng TLS vào cổng riêng; không mặc định được mở. |
| **7000/TCP** | Giao tiếp internode thường | Các node Cassandra. |
| **7001/TCP** | Cổng internode TLS kiểu cấu hình cũ | Các node, tùy thiết lập; ở bản hiện đại có thể mã hóa trên cổng 7000. |
| **7199/TCP** | JMX cho công cụ quản trị, thường dùng bởi `nodetool` | Người/quy trình vận hành được cấp quyền. |
| **9160/TCP** | Thrift API lịch sử | Chỉ liên quan tới hệ Cassandra rất cũ; **không dùng** làm endpoint CQL hiện đại. |

Các số trên là giá trị mặc định hoặc lịch sử phổ biến, **không phải cam kết cho mọi bản triển khai**. Port có thể được đổi. Cassandra 5.0 đánh dấu cấu hình cổng native TLS riêng `native_transport_port_ssl` là **deprecated**; nên ưu tiên kiểm tra cấu hình phiên bản đang chạy và kế hoạch TLS trên native port chính.

**Quy tắc mạng:** ứng dụng thường cần quyền kết nối đến **native endpoint của mọi node mà driver có thể chọn**, không chỉ duy nhất contact point ban đầu. Các cổng internode/JMX phục vụ mục đích khác và không nên mở rộng bừa bãi cho client ứng dụng hoặc Internet.

## 4. Cấu hình địa chỉ lắng nghe và địa chỉ công bố

Các tham số quan trọng của Cassandra nằm trong `cassandra.yaml`. Đoạn dưới **minh họa tên thuộc tính và mối quan hệ**, chưa phải cấu hình triển khai hoàn chỉnh:

~~~yaml
# Ví dụ khái niệm: thay địa chỉ và bảo mật theo môi trường thực.
start_native_transport: true
native_transport_port: 9042
rpc_address: 0.0.0.0
broadcast_rpc_address: 192.0.2.10
~~~

Trong ví dụ, `192.0.2.10` là **địa chỉ tài liệu minh họa**, không phải IP của node có thể triển khai. Các tham số có ý nghĩa:

- `start_native_transport`: bật hoặc tắt dịch vụ native transport trên node.
- `native_transport_port`: cổng mà native transport nhận kết nối TCP, mặc định **9042**.
- `rpc_address`: địa chỉ/interface **bind** để native server lắng nghe. Dù tên mang chữ “rpc”, tham số này áp dụng cho native transport trong Cassandra hiện đại.
- `broadcast_rpc_address`: địa chỉ node **công bố cho driver và cluster** để client biết endpoint có thể kết nối. Nó cần là địa chỉ client thực tế định tuyến tới được.

Nếu đặt `rpc_address: 0.0.0.0` (nghe trên mọi IPv4 interface), phải cấu hình `broadcast_rpc_address` thành địa chỉ cụ thể, **không được** là `0.0.0.0`. Một địa chỉ bind không thể thay cho địa chỉ công bố: `0.0.0.0` không phải đích kết nối mà client từ xa có thể sử dụng.

Đừng nhầm `rpc_address`/`broadcast_rpc_address` với `listen_address`/`broadcast_address` của **giao tiếp internode**. Một cluster có thể dùng mạng riêng để các node trao đổi với nhau và mạng khác để ứng dụng gửi native requests.

### 4.1. Vì sao cqlsh kết nối được nhưng Java Driver vẫn thất bại?

Driver thường bắt đầu bằng một hoặc vài **contact points**, sau đó đọc metadata cluster và khám phá các node khác để điều phối kết nối và request. Nếu node công bố địa chỉ riêng không tới được từ máy client (ví dụ IP của container, pod, NAT hoặc mạng nội bộ khác), phiên khởi tạo ban đầu có thể thành công nhưng các kết nối tới node được khám phá lại thất bại.

Ví dụ:

1. Ứng dụng kết nối vào `db-gateway.example.internal:9042`.
2. Node phản hồi metadata rằng một peer có native endpoint `10.40.0.12:9042`.
3. Ứng dụng ở mạng ngoài không có tuyến đến `10.40.0.12`, nên log báo không kết nối được peer dù gateway vẫn đáp ứng.

Cách xử lý là kiểm tra **địa chỉ thực tế driver khám phá**, tuyến mạng giữa client và các node, cấu hình địa chỉ công bố và cơ chế proxy/address translation nếu môi trường cần. Không giả định một TCP load balancer phía trước một node sẽ tự giải quyết toàn bộ khám phá topology của mọi driver.

## 5. Kết nối ban đầu và trao đổi thông điệp native

Một phiên native thường có các giai đoạn sau:

~~~mermaid
sequenceDiagram
    participant App as Java Driver / cqlsh
    participant Node as Cassandra native endpoint
    App->>Node: Mở kết nối TCP (+ TLS nếu cấu hình)
    opt Hỏi khả năng của server
        App->>Node: OPTIONS
        Node-->>App: SUPPORTED
    end
    App->>Node: STARTUP (CQL_VERSION, tùy chọn)
    alt Cần xác thực
        Node-->>App: AUTHENTICATE
        App->>Node: AUTH_RESPONSE / trao đổi auth
        Node-->>App: AUTH_SUCCESS
    else Không yêu cầu xác thực
        Node-->>App: READY
    end
    App->>Node: PREPARE hoặc QUERY
    Node-->>App: RESULT (hoặc ERROR)
    App->>Node: EXECUTE với bind values
    Node-->>App: RESULT (hoặc ERROR)
~~~

Sơ đồ là **luồng điển hình**, không bắt buộc mọi driver phải gửi `OPTIONS` trước `STARTUP` hoặc luôn `PREPARE` trước `QUERY`. Trong phiên hoạt động, driver còn có thể nhận sự kiện `EVENT` về thay đổi node/schema, gửi `BATCH`, lấy các trang kết quả và quản lý nhiều kết nối.

### 5.1. Giao thức mang dữ liệu gì?

Nhóm thông điệp thường gặp:

| Thông điệp | Vai trò |
| --- | --- |
| `OPTIONS` / `SUPPORTED` | Khám phá khả năng và lựa chọn kết nối được hỗ trợ. |
| `STARTUP` / `READY` | Bắt đầu phiên với CQL version và tùy chọn thích hợp. |
| `AUTHENTICATE` / `AUTH_RESPONSE` / `AUTH_SUCCESS` | Thực hiện xác thực khi server yêu cầu. |
| `QUERY` | Thực thi câu CQL truyền trực tiếp. |
| `PREPARE` / `EXECUTE` | Chuẩn bị truy vấn, sau đó thực thi với bind values. |
| `BATCH` | Gửi nhóm thao tác CQL theo semantics batch của Cassandra. |
| `RESULT` / `ERROR` | Trả dữ liệu, metadata, kết quả câu lệnh hoặc lỗi. |
| `REGISTER` / `EVENT` | Client đăng ký và nhận thông báo về thay đổi topology/schema/trạng thái. |

Native protocol cho phép nhiều request đang xử lý đồng thời qua cơ chế định danh luồng/request. **Nó không phải kết nối tuần tự chỉ được phép gửi một câu SQL rồi chờ**. Driver quản lý kết nối, backpressure, timeout và concurrency theo phiên bản và cấu hình của chính driver.

### 5.2. Prepared statement và paging phụ thuộc giao thức

Khi dùng prepared statement, driver gửi `PREPARE` để server trả metadata/id rồi gửi `EXECUTE` kèm các giá trị bind. Đây là cách phổ biến cho truy vấn lặp lại có tham số; tránh tự ghép chuỗi CQL từ input người dùng.

Khi kết quả lớn, native protocol có thể trả về từng **page** và **paging state**. Paging state là token nhị phân opaque phụ thuộc truy vấn và chi tiết giao thức; không nên sửa, tự suy diễn nội dung hay tái sử dụng cho truy vấn khác. Đặc biệt, tài liệu native protocol nêu paging state của **v3 và v4 không tương thích với nhau**. Khi chuyển phiên bản giao thức trong quá trình nâng cấp, phải kiểm thử logic tiếp tục phân trang/khôi phục cursor.

## 6. Native protocol version và ma trận tương thích thực tế

Cần phân biệt ít nhất **bốn “phiên bản”**:

| Loại phiên bản | Ví dụ | Phản ánh |
| --- | --- | --- |
| **Cassandra server version** | Một bản phát hành Cassandra 4.x hoặc 5.x | Hành vi và tính năng của node/cluster. |
| **CQL language version** | CQL 3.x | Ngữ pháp và semantics của ngôn ngữ truy vấn. |
| **Native protocol version** | v3, v4, v5 | Cấu trúc gói nhị phân và khả năng trao đổi client–server. |
| **Driver/client version** | Java Driver 4.x, bản cqlsh đi kèm server | Giao thức và tính năng mà thư viện công cụ hỗ trợ. |

**Không suy ra** “Cassandra 5.x ⇒ Java Driver 5.x” hoặc “CQL 3.x ⇒ native protocol v3”. Chúng có vòng đời khác nhau. Một driver tương thích có thể chọn phiên bản native mà cả client và server đều hỗ trợ; khả năng cụ thể phụ thuộc bản driver, bản Cassandra và cấu hình cluster.

### 6.1. Điều gì thay đổi giữa các native protocol?

Các phiên bản v3, v4 và v5 có cùng mục đích nhưng không cùng tất cả khả năng và encoding:

- **v3** là một giao thức đã được dùng rộng rãi trong các hệ Cassandra cũ.
- **v4** bổ sung một số metadata/kiểu dữ liệu/cảnh báo và thay đổi encoding một số kết quả, bao gồm **paging state không tương thích với v3**.
- **v5** thay đổi cơ chế framing/negotiation, thêm một số khả năng như metadata cho kết quả prepared. Ở một số bản Cassandra, v5 có thể được báo là **beta**; phải kiểm tra khả năng thực tế thay vì mặc định bật.

Đừng ép driver dùng v5 chỉ dựa vào số version của Cassandra. Khi không chắc, để **driver được hỗ trợ thương lượng** phiên bản chung, rồi kiểm tra log/metadata xem đang dùng native protocol nào.

### 6.2. Các bước kiểm tra tương thích trước nâng cấp

1. Ghi lại **server version**, **Java Driver version** và **native protocol đang được chọn**, không chỉ CQL syntax.
2. Đối chiếu tài liệu tương thích của đúng bản driver với phiên bản Cassandra sẽ nâng cấp.
3. Trong staging, thử khởi tạo session, auth/TLS, metadata discovery, prepared statement, paging, consistency, LWT và các kiểu dữ liệu đang dùng.
4. Với rolling upgrade nhiều phiên bản node cùng tồn tại, dùng cấu hình driver được hỗ trợ cho **tập phiên bản giao thức chung**; theo dõi kết nối tới từng node.
5. Chú ý lại prepared statement sau thay đổi schema/node restart và paging state đã lưu từ trước; ứng dụng cần chính sách retry và checkpoint phù hợp.

Nếu gặp thông báo như `Unsupported protocol version`, `ProtocolError` hoặc server đóng socket ngay khi khởi tạo, hãy tra log trên cả client và server. Nguyên nhân có thể là phiên bản native không chung, cấu hình TLS/port sai, hoặc driver quá cũ.

## 7. TLS, xác thực và quyền truy cập

Native transport có thể được bảo vệ bằng **TLS** (mã hóa kết nối client–node), **authentication** (xác thực danh tính) và **authorization** (kiểm soát quyền CQL). Chúng giải quyết những vấn đề khác nhau:

| Cơ chế | Trả lời câu hỏi |
| --- | --- |
| TLS server authentication | Client đang kết nối đúng server không, dữ liệu có được mã hóa khi truyền không? |
| Mutual TLS, nếu cấu hình | Server có yêu cầu client xuất trình chứng chỉ hợp lệ không? |
| Cassandra authentication | Tài khoản/định danh đăng nhập là ai? |
| Authorization | Định danh đó được `SELECT`, `MODIFY` hoặc quản lý schema nào? |

Cấu hình TLS phía Cassandra thuộc `client_encryption_options` và yêu cầu chứng chỉ/keystore/truststore thực tế. Một deployment có thể:

- Chạy TLS trên **chính cổng 9042**.
- Ở các phiên bản/cấu hình có hỗ trợ, bật thêm native TLS port riêng, thường được minh họa là **9142**.
- Trong giai đoạn chuyển đổi, có thể cho phép cả kết nối mã hóa và không mã hóa khi cấu hình `optional` tương ứng; cấu hình này phải được kiểm soát và loại bỏ khi hoàn tất chuyển đổi.

**Không kết luận “9042 = không TLS” hay “9142 = luôn có TLS”.** Chỉ cấu hình và thử handshake mới xác nhận được. Không dùng kiểu “trust all certificates” trong ứng dụng thật; cần kiểm tra chuỗi tin cậy và danh tính host theo chính sách TLS đang áp dụng.

Ví dụ kết nối cqlsh đến server có TLS (tùy phiên bản cqlsh và cấu hình chứng chỉ của môi trường):

~~~bash
# Máy chủ phải bật native TLS ở đúng port.
cqlsh db.example.internal 9042 --ssl -u student
~~~

Tài khoản có thể cần nhập mật khẩu qua prompt hoặc cấu hình credential bảo vệ bằng quyền file phù hợp. **Tránh đưa mật khẩu trực tiếp vào tham số lệnh** hoặc script được commit. `--ssl` chỉ yêu cầu chế độ TLS; việc kiểm tra chứng chỉ CA/hostname phải tuân theo cấu hình cqlsh đang sử dụng.

## 8. Thực hành kiểm tra cổng và endpoint

### 8.1. Kiểm tra mạng trước khi kiểm tra CQL

Từ **máy chạy ứng dụng**, xác nhận DNS/IP và khả năng mở kết nối TCP:

~~~bash
# Linux/macOS: chỉ kiểm tra khả năng kết nối TCP, không gửi CQL.
nc -vz db.example.internal 9042

# Nếu endpoint yêu cầu TLS: quan sát chứng chỉ/handshake.
openssl s_client -connect db.example.internal:9042 -servername db.example.internal
~~~

Từ PowerShell trên Windows:

~~~powershell
Test-NetConnection -ComputerName db.example.internal -Port 9042
~~~

Những phép thử này **chỉ xác nhận một phần**: TCP mở không chứng minh native handshake, auth, schema access hoặc truy vấn CQL hoạt động. `openssl s_client` chỉ hợp lệ khi endpoint đó thực sự nói TLS; với port không TLS, kết quả lỗi handshake là điều có thể dự đoán.

### 8.2. Kiểm tra chính native transport và cluster

Từ node hoặc máy vận hành có quyền phù hợp:

~~~bash
# Trạng thái dịch vụ native transport của node thông qua nodetool/JMX.
nodetool statusbinary

# Trạng thái các node trong cluster, không thay thế statusbinary.
nodetool status
~~~

`nodetool statusbinary` cho biết dịch vụ native transport trên node đang ở trạng thái nào; `nodetool status` nói về tình trạng cluster/ring, không tự chứng minh cổng 9042 đã mở ra đúng mạng client. Để kiểm tra từ bên ngoài, vẫn cần thử kết nối từ đúng mạng ứng dụng.

Trong cqlsh:

~~~bash
cqlsh 127.0.0.1 9042
~~~

~~~sql
SHOW HOST;
SHOW VERSION;

-- Xác nhận metadata của node đang kết nối.
SELECT cluster_name, data_center, release_version
FROM system.local;
~~~

Kết quả `data_center` sẽ được dùng để cấu hình **local datacenter** của Java Driver. Tên thường thấy trong lab có thể là `datacenter1`, nhưng **không được tự giả định** tên này ở môi trường thật.

### 8.3. Lab CQL qua native protocol

Ví dụ sau chỉ dành cho **lab một node**, để có dữ liệu cho phần Java. Các câu CQL chạy trong cqlsh:

~~~sql
CREATE KEYSPACE IF NOT EXISTS native_protocol_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS native_protocol_lab.readings_by_device_day (
  device_id text,
  reading_day date,
  read_at timestamp,
  temp_c double,
  PRIMARY KEY ((device_id, reading_day), read_at)
) WITH CLUSTERING ORDER BY (read_at DESC);

INSERT INTO native_protocol_lab.readings_by_device_day
  (device_id, reading_day, read_at, temp_c)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z', 25.1);

INSERT INTO native_protocol_lab.readings_by_device_day
  (device_id, reading_day, read_at, temp_c)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z', 25.3);

SELECT read_at, temp_c
FROM native_protocol_lab.readings_by_device_day
WHERE device_id = 'sensor-01'
  AND reading_day = '2026-11-21'
LIMIT 10;
~~~

Kỳ vọng có **2 row**, bản ghi lúc 01:05 đứng trước 01:00. Ở ví dụ này, `(device_id, reading_day)` là composite partition key; không thể thay truy vấn thành `WHERE temp_c > 25` rồi mong Cassandra tự có index phù hợp. Thiết kế bảng theo truy vấn và khóa phân vùng vẫn là phần cốt lõi ngay cả khi client đã kết nối thành công.

`SimpleStrategy` + RF = 1 phù hợp minh họa đơn node. Với cluster nhiều node/datacenter, thường dùng `NetworkTopologyStrategy` và khai báo RF theo tên datacenter thực tế.

## 9. Java Driver: kết nối và thực thi prepared query

Ví dụ Java bên dưới dùng API `CqlSession` của **Java Driver 4.x**, tương thích với các bản driver có package `com.datastax.oss.driver.api`. Cần thêm dependency driver phù hợp với phiên bản Java/Cassandra trong dự án; thay contact points và datacenter bằng thông tin của môi trường đã kiểm tra.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.LocalDate;

public class CassandraNativeDemo {
    public static void main(String[] args) {
        // datacenter1 chỉ là ví dụ: đọc data_center từ system.local.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            PreparedStatement ps = session.prepare(
                "SELECT read_at, temp_c " +
                "FROM native_protocol_lab.readings_by_device_day " +
                "WHERE device_id = ? AND reading_day = ?");

            ResultSet rs = session.execute(
                ps.bind("sensor-01", LocalDate.of(2026, 11, 21)));

            for (Row row : rs) {
                System.out.println(
                    row.getInstant("read_at") + " -> " +
                    row.getDouble("temp_c"));
            }
        }
    }
}
~~~

**Diễn giải đường đi:** khi gọi `session.execute(...)`, driver đóng gói câu lệnh đã chuẩn bị và các bind values thành thông điệp native protocol, chọn coordinator theo chính sách driver, nhận result và chuyển đổi dữ liệu về kiểu Java. Driver có thể duy trì nhiều kết nối đến nhiều node, nên `CqlSession` là đối tượng sống lâu, thường dùng chung trong ứng dụng và được đóng khi ứng dụng dừng.

### 9.1. Nhiều contact points và khám phá node

Trong hệ nhiều node, nên cung cấp hơn một **contact point** ở các endpoint ứng dụng truy cập được và đặt đúng datacenter:

~~~java
CqlSession session = CqlSession.builder()
    .addContactPoint(new InetSocketAddress("db-node-1.internal", 9042))
    .addContactPoint(new InetSocketAddress("db-node-2.internal", 9042))
    .withLocalDatacenter("dc1")
    .build();
~~~

`dc1` ở đây là ví dụ. Contact points là **đầu vào ban đầu để khám phá cluster**, không phải danh sách duy nhất những node mà driver có thể dùng. Driver có thể lấy metadata và xây dựng danh sách kết nối theo load-balancing policy, local DC và topology. Đảm bảo client định tuyến được đến các native endpoints được công bố.

Ví dụ cuối chỉ minh họa tạo session; ứng dụng phải đóng session ở thời điểm phù hợp, thường qua `try-with-resources` khi vòng đời ngắn hoặc hook shutdown của service.

### 9.2. Bảo mật và kiểm soát phiên

Nếu server yêu cầu xác thực, cấu hình auth provider hoặc credentials qua cơ chế quản lý secrets của ứng dụng. Nếu server yêu cầu TLS, cấu hình `SSLContext` tin cậy CA/chứng chỉ thực tế cho Java Driver; việc đổi sang port 9142 **không đủ** để tự bật TLS phía client. Tránh hard-code mật khẩu trong source và tránh bỏ kiểm tra hostname/chứng chỉ để “cho kết nối được”.

Trong ứng dụng có nhiều request, đặt request timeout, consistency, retry policy và paging phù hợp, đồng thời dùng prepared statements. Cấu hình này nằm ở driver/statement và **không phụ thuộc** các lệnh `CONSISTENCY`, `PAGING` hay `TRACING` của một phiên cqlsh bên ngoài.

## 10. Chẩn đoán lỗi theo từng lớp

Khi Java hoặc cqlsh không kết nối được, đừng bắt đầu bằng cách đổi mức consistency. Xác định lỗi xuất hiện ở **DNS/TCP**, **TLS**, **native handshake**, **authentication**, **metadata discovery**, hay **thực thi CQL**.

| Dấu hiệu | Lớp cần kiểm tra | Cách xử lý phù hợp |
| --- | --- | --- |
| `Connection refused` tới host:9042 | TCP/native listener | Kiểm tra địa chỉ, port, `start_native_transport`, `rpc_address`, dịch vụ và firewall. |
| Kết nối bị timeout | Mạng/DNS/routing | Thử từ chính máy ứng dụng, kiểm tra tuyến tới node và cổng. |
| `SSLHandshakeException` hoặc handshake thất bại | TLS | Xác nhận port có bật TLS, CA/truststore, SAN/hostname và cấu hình client. |
| `AuthenticationException` | Xác thực | Kiểm tra credentials, auth provider và cấu hình server. |
| `Unauthorized` khi SELECT/CREATE | Authorization CQL | Kiểm tra role và quyền trên keyspace/bảng; đây không phải lỗi port. |
| `Unsupported protocol version` / `ProtocolError` | Native protocol | Đối chiếu hỗ trợ protocol của server/driver; kiểm tra nhầm port/TLS trước khi ép version. |
| Java kết nối được contact point nhưng mất peer | Discovery/topology | Kiểm tra `broadcast_rpc_address`, routing tới từng peer, local DC, NAT/container/proxy. |
| Driver báo không tìm thấy node phù hợp | Driver policy/local datacenter | Xác nhận `data_center` thực tế và các contact points thuộc đúng DC. |
| `Unprepared` hoặc lỗi sau schema change | Prepared statement/schema metadata | Kiểm tra đồng bộ schema và cơ chế reprepare của driver; không giả định server luôn còn prepared cache. |
| `ReadTimeout` / `WriteTimeout` | Replica/consistency/thời gian xử lý | Xem RF, CL, trạng thái node, network, load, compaction và log; lỗi có thể xảy ra sau handshake thành công. |
| CQL trả lỗi thiếu partition key | Thiết kế truy vấn | Kiểm tra `PRIMARY KEY`, mô hình bảng theo truy vấn; không chữa bằng đổi cổng/protocol. |

### 10.1. Quy trình kiểm tra tối thiểu

1. **Từ máy ứng dụng:** hostname có phân giải đúng không và TCP có tới được port cấu hình không?
2. **Trên node:** `nodetool statusbinary` có báo native transport hoạt động, listener có bind đúng địa chỉ và cổng không?
3. **TLS/auth:** server và client có cùng kỳ vọng về mã hóa, CA, hostname và thông tin đăng nhập không?
4. **CQL:** `cqlsh` có chạy được `SHOW VERSION` và `SELECT ... FROM system.local` không?
5. **Driver:** log cho thấy protocol version nào, các peer được khám phá ở địa chỉ nào, local datacenter là gì?
6. **Truy vấn:** câu lệnh có đủ partition key, đúng keyspace, đúng consistency và được cấp quyền không?

Trong môi trường production, hạn chế bật log chứa toàn bộ bind values hay credentials. Khi cần điều tra latency, kết hợp application metrics, driver metrics, server logs và tracing chọn lọc. **Mở được TCP 9042 không chứng minh Cassandra đã sẵn sàng nhận truy vấn hợp lệ.**

## 11. Bài thực hành và câu hỏi tự kiểm tra

1. Liệt kê ý nghĩa của **9042**, **7000** và **7199**. Giải thích vì sao ứng dụng Java thông thường không cần mở JMX.
2. Dùng `Test-NetConnection` hoặc `nc` kiểm tra cổng native từ máy client. Dùng cqlsh kiểm tra `SHOW HOST` và `SHOW VERSION`. Nêu sự khác biệt giữa “TCP open” và “CQL query thành công”.
3. Chạy lab `native_protocol_lab`, rồi dùng Java Driver đọc hai kết quả với prepared statement. Kiểm tra `data_center` trước khi điền `withLocalDatacenter`.
4. Giả sử node dùng `rpc_address: 0.0.0.0` nhưng không đặt `broadcast_rpc_address` hợp lệ. Giải thích tại sao driver khám phá topology có thể gặp lỗi và cách xác minh địa chỉ được công bố.
5. Giả sử server yêu cầu TLS trên 9042, nhưng cqlsh được chạy không có `--ssl`. Lỗi thuộc lớp nào và cần kiểm tra những thông số nào?
6. Phân biệt **Cassandra server version**, **CQL language version**, **native protocol version** và **Java Driver version**. Vì sao không thể suy ra một phiên bản từ phiên bản còn lại?
7. Trong rolling upgrade, tại sao một paging state lấy qua native v3 không thể tùy tiện dùng với v4? Đề xuất cách ứng dụng xử lý các cursor cũ.
8. Giả sử contact point là hostname công khai còn peer công bố địa chỉ riêng không định tuyến được. Nêu ít nhất ba phép kiểm tra để xác định nguyên nhân kết nối lúc được lúc không.

**Tiêu chí hoàn thành:** bạn có thể vẽ đường đi ứng dụng → native endpoint → coordinator/replica, phân biệt được nhóm cổng, kết nối bằng cqlsh và Java, giải thích vai trò của địa chỉ bind/broadcast, và chọn đúng nhóm kiểm tra khi gặp lỗi giao thức hay truy vấn.

## 12. Tài liệu tham khảo

- [Apache Cassandra — Cassandra.yaml configuration](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): `start_native_transport`, `native_transport_port`, `rpc_address`, `broadcast_rpc_address` và `client_encryption_options`.
- [Apache Cassandra — Native Protocol Versions](https://cassandra.apache.org/doc/stable/cassandra/reference/native-protocol.html): thông điệp, thương lượng, thay đổi giữa v3/v4/v5, paging và error codes.
- [Apache Cassandra — nodetool statusbinary](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/statusbinary.html): kiểm tra trạng thái native transport.
- [Apache Cassandra — CQL](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/index.html): ngôn ngữ truy vấn, schema và khóa chính.
- [Apache Cassandra Java Driver — Core](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/index.html): cấu hình contact points và local datacenter.
- [Apache Cassandra Java Driver — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html): result paging, paging state và giới hạn tái sử dụng.
