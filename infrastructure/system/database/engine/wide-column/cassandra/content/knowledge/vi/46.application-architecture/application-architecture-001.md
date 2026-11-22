# Chọn vai trò Cassandra trong hệ thống và xác định nguồn dữ liệu chuẩn

## 1. Mục tiêu học tập và bối cảnh

Apache Cassandra là cơ sở dữ liệu NoSQL phân tán theo mô hình **wide-column**, được thiết kế để mở rộng ngang, duy trì dịch vụ khi một phần nút gặp lỗi và phục vụ truy vấn dựa trên khóa phân vùng với độ trễ có thể dự đoán được. Trong kiến trúc ứng dụng Java, chọn Cassandra không chỉ là chọn công nghệ lưu trữ: nhóm phải quyết định **dữ liệu nào thuộc Cassandra, ai có quyền ghi dữ liệu chuẩn và hệ thống phục hồi trạng thái khi có bất đồng hoặc lỗi như thế nào**.

Sau bài này, người học có thể:

1. Phân biệt *system of record* (hệ thống ghi nhận dữ liệu có thẩm quyền) với *read model* (mô hình phục vụ truy vấn), bộ nhớ đệm và bản sao dữ liệu.
2. Xác định khi nào Cassandra thích hợp làm nguồn dữ liệu chuẩn, khi nào nên là mô hình đọc được tạo từ PostgreSQL, log sự kiện hay hệ thống khác.
3. Thiết kế đường đi của dữ liệu, chọn bảng CQL theo truy vấn và khóa phân vùng để tránh phân vùng quá nóng hoặc quá lớn.
4. Đánh giá tác động của replication, consistency level, timeout, retry, compaction và repair đến cam kết nghiệp vụ.
5. Đưa ra quyết định có thể kiểm chứng bằng tài liệu kiến trúc, thử nghiệm tải và kịch bản phục hồi.

**Phạm vi bài:** tập trung vào vai trò của Cassandra trong kiến trúc ứng dụng và việc xác định dữ liệu chuẩn; các ví dụ CQL, vận hành và Java nhằm chứng minh tính khả thi của quyết định đó.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Câu hỏi phải trả lời | Ví dụ |
|---|---|---|
| **System of record (SoR)** | Hệ thống nào có thẩm quyền xác nhận bản ghi nghiệp vụ hiện hành? | PostgreSQL xác nhận đơn hàng và thanh toán hợp lệ. |
| **Source of truth (nguồn dữ liệu chuẩn)** | Khi hai hệ thống mâu thuẫn, dữ liệu nào được dùng để phân xử và tái tạo phần còn lại? | Bản ghi đơn hàng đã commit trong dịch vụ Orders; sự kiện phát ra từ bản ghi này. |
| **Read model / projection** | Bảng nào tối ưu để trả lời một nhóm truy vấn và có thể tạo lại từ nguồn chuẩn? | Cassandra lưu danh sách đơn hàng theo khách hàng để hiển thị nhanh. |
| **Cache** | Bản sao nào được phép bỏ hoặc nạp lại mà không mất dữ liệu nghiệp vụ? | Redis lưu kết quả truy vấn ngắn hạn; Cassandra thường được dùng làm *serving store* bền vững hơn là cache thông thường. |
| **Event log** | Chuỗi sự kiện bất biến nào mô tả các thay đổi và có thể phát lại? | Log thay đổi đơn hàng lưu đủ lâu để dựng lại projection. |
| **Data owner** | Dịch vụ nào được phép tạo, kiểm tra quy tắc và sửa dữ liệu của một miền? | Orders Service sở hữu vòng đời đơn hàng; Reporting Service chỉ tiêu thụ bản sao. |

**Không có quy tắc “cả hệ thống chỉ được có một database chuẩn”.** Nguồn chuẩn được xác định theo *miền dữ liệu*, thậm chí theo nhóm thuộc tính: đơn hàng, thanh toán, cấu hình thiết bị và bản ghi cảm biến có thể do các dịch vụ khác nhau sở hữu. Tuy nhiên, **mỗi sự thật nghiệp vụ cần một quy tắc phân xử rõ ràng**. Hai database cùng cho phép sửa trực tiếp một trường mà không có cơ chế đồng bộ và xử lý xung đột là một thiết kế thiếu thẩm quyền.

Một dữ liệu có thể “được lưu bền vững” trong Cassandra nhưng vẫn chỉ là projection: độ bền của bản sao không tự biến bản sao đó thành nguồn chuẩn.

## 3. Cassandra nên giữ vai trò gì?

### 3.1. Các lựa chọn kiến trúc

| Vai trò | Khi phù hợp | Ai được ghi? | Cách phục hồi / giới hạn |
|---|---|---|---|
| **Nguồn chuẩn cho sự kiện hoặc bản ghi theo khóa** | Lượng ghi lớn, truy cập theo thiết bị/tài khoản và khoảng thời gian, bản ghi độc lập, yêu cầu giao dịch đa thực thể thấp. | Dịch vụ ingestion hoặc domain service sở hữu sự kiện. | Snapshot/backup, repair, lưu trữ đủ lâu; cần quy tắc chống ghi trùng và quy trình sửa dữ liệu. |
| **Serving store / read model** | Cần nhiều cách đọc tối ưu riêng, truy vấn ổn định, dữ liệu chuẩn nằm ở hệ thống khác. | Chỉ projection consumer hoặc pipeline đồng bộ. | Phát lại sự kiện hoặc dựng lại từ nguồn chuẩn; chấp nhận độ trễ cập nhật đã công bố. |
| **Kho timeline / activity feed** | Truy vấn lặp lại dạng “N hoạt động mới nhất theo người dùng/đối tượng”, ghi nhiều, sắp xếp theo thời gian. | Dịch vụ tạo hoạt động hoặc consumer có thẩm quyền. | Phải biết feed có phải dữ liệu gốc hay có thể tái tạo; quản lý partition theo thời gian. |
| **Kho dữ liệu phụ cho tìm kiếm/báo cáo** | Chỉ khi truy vấn được cố định theo partition key và mô hình dữ liệu phù hợp. | Pipeline từ nguồn chuẩn. | Cassandra không thay thế trực tiếp công cụ tìm kiếm toàn văn, OLAP hoặc SQL phân tích tùy ý. |

Cassandra thường **không phải lựa chọn mặc định** cho nghiệp vụ cần nhiều phép JOIN, truy vấn tùy ý, ràng buộc khóa ngoại, tổng hợp toàn cục hoặc giao dịch ACID trải trên nhiều thực thể. Những nhu cầu đó có thể được phục vụ phù hợp hơn bằng hệ quản trị quan hệ, search engine hoặc data warehouse. Cũng không nên chọn Cassandra chỉ vì “dữ liệu lớn”: phải chỉ ra *truy vấn chủ đạo, khóa phân vùng, tốc độ ghi/đọc, mức nhất quán và cách vận hành*.

### 3.2. Quy trình chọn vai trò

1. **Liệt kê bất biến nghiệp vụ.** Ví dụ: không thể xác nhận hoàn tiền vượt quá số tiền đã thanh toán; không được có hai số dư cuối cùng khác nhau. Những bất biến cần cập nhật đồng bộ nhiều hàng hoặc nhiều partition là tín hiệu cần cân nhắc SoR dạng giao dịch.
2. **Liệt kê truy vấn thực tế.** Ghi rõ điều kiện lọc, thứ tự sắp xếp, kích thước kết quả, tần suất và SLO. Ví dụ: “lấy 100 sự kiện gần nhất của một thiết bị trong ngày”, không phải “truy vấn sự kiện”.
3. **Xác định chủ sở hữu và quy tắc phân xử.** Dịch vụ nào được ghi? Khi Cassandra và database khác không khớp, tin bên nào? Ai chịu trách nhiệm sửa?
4. **Xác định đường cập nhật và độ trễ chấp nhận.** Cập nhật trực tiếp, thông qua sự kiện, hay thông qua pipeline? Người dùng có cần read-your-write ngay không?
5. **Mô phỏng lỗi và tái tạo.** Nếu consumer dừng 30 phút, một lần ghi timeout, một node hỏng hoặc cần rebuild toàn bộ bảng Cassandra, hệ thống phục hồi bằng dữ liệu nào?
6. **Thử nghiệm tải theo partition thực.** Kiểm tra phân phối khóa, partition lớn, truy vấn phân trang, compaction và tombstone; tăng số node không cứu được một partition đơn lẻ bị truy cập quá nóng.

## 4. Tình huống A: PostgreSQL giữ đơn hàng chuẩn, Cassandra phục vụ truy vấn

Giả sử nền tảng bán hàng có nghiệp vụ xác nhận thanh toán, thay đổi trạng thái đơn hàng và kiểm tra tồn kho. Dữ liệu cần nhất quán qua nhiều bảng và ràng buộc giao dịch. Ứng dụng cũng phải hiển thị “50 đơn gần đây của khách hàng” với lưu lượng đọc lớn.

**Quyết định:**

- **Orders Service + PostgreSQL** là SoR cho trạng thái đơn hàng; Payment Service và hệ thống thanh toán có quy tắc đối soát riêng cho thanh toán.
- **Cassandra** giữ projection phục vụ trang lịch sử đơn hàng. Bản ghi ở đây được phép trễ vài giây theo SLO đã thống nhất; không dùng nó để quyết định có được hoàn tiền hay không.
- Chỉ Orders Service có quyền phát lệnh thay đổi nghiệp vụ. Consumer cập nhật Cassandra; API liệt kê đơn đọc projection, còn API xác nhận hoặc thao tác tiền đọc nguồn chuẩn.

~~~mermaid
flowchart LR
    A[Ứng dụng web / mobile] --> B[Orders Service]
    B -->|Giao dịch: đơn hàng + outbox| C[(PostgreSQL - SoR)]
    C -->|Outbox relay / CDC| D[Event stream]
    D --> E[Projection consumer]
    E --> F[(Cassandra - read model)]
    A --> G[Order History API]
    G -->|Danh sách đơn theo khách| F
    F -. Lỗi hoặc lệch dữ liệu .-> H[Rebuild / reconcile từ SoR]
    C --> H
~~~

### 4.1. Vì sao cần transactional outbox?

Nếu code Java lần lượt commit vào PostgreSQL rồi gửi sự kiện, tiến trình có thể chết giữa hai bước: đơn hàng đã thay đổi nhưng Cassandra không nhận được cập nhật. Nếu gửi sự kiện trước khi commit, projection có thể hiển thị đơn hàng chưa tồn tại hoặc cuối cùng bị rollback.

Với **transactional outbox**, cùng một giao dịch PostgreSQL ghi thay đổi đơn hàng và một dòng outbox. Relay/CDC phát dòng đó đến hệ thống sự kiện; consumer áp dụng vào Cassandra. Đường truyền thường có ngữ nghĩa **at-least-once**, nên phải chấp nhận sự kiện gửi lặp.

Ví dụ payload:

~~~json
{
  "eventId": "fdf7a157-a5f1-4280-a413-9639add340a5",
  "type": "OrderStatusChanged",
  "orderId": "ORD-1024",
  "customerId": "CUS-88",
  "version": 7,
  "status": "SHIPPED",
  "occurredAt": "2026-11-21T03:10:00Z"
}
~~~

Hai điểm dễ sai:

- **Trùng sự kiện:** sử dụng khóa sự kiện ổn định, lưu dấu đã xử lý hoặc thiết kế upsert idempotent; không tự động tăng bộ đếm doanh thu mỗi khi nhận lại cùng một event.
- **Đảo thứ tự:** nếu version 7 đến trước version 6, ghi đè mù theo “sự kiện đến sau” sẽ làm trạng thái lùi. Cần đảm bảo thứ tự tiêu thụ theo orderId và kiểm tra phiên bản/đối soát; nơi phải bảo vệ phiên bản ở chính hàng Cassandra có thể dùng lightweight transaction (LWT) có điều kiện, với chi phí đồng thuận cao hơn ghi thông thường.

Không nên xem thao tác ghi Cassandra và thao tác commit PostgreSQL là một giao dịch phân tán mặc định. Thiết kế phải cho phép *replay*, *reconciliation*, lag monitoring và xử lý lỗi có kiểm soát.

### 4.2. Projection theo truy vấn

Truy vấn sản phẩm là “liệt kê đơn của một khách theo tháng, mới nhất trước”. Có thể thiết kế bảng:

~~~sql
CREATE TABLE order_read.orders_by_customer_month (
    customer_id text,
    order_month text,       -- Ví dụ '2026-11'
    created_at timestamp,
    order_id text,
    status text,
    total_amount decimal,
    PRIMARY KEY ((customer_id, order_month), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);

SELECT order_id, created_at, status, total_amount
FROM order_read.orders_by_customer_month
WHERE customer_id = 'CUS-88' AND order_month = '2026-11'
LIMIT 50;
~~~

Khóa phân vùng gồm **customer_id + order_month** giới hạn dữ liệu tích lũy trong một partition theo thời gian. **created_at + order_id** tạo thứ tự xác định và tránh trùng primary key nếu hai đơn có thời điểm tạo bằng nhau. Khi cần nhiều tháng, ứng dụng truy vấn các partition tương ứng rồi ghép kết quả có giới hạn; Cassandra không tự hỗ trợ JOIN giữa các bảng như cơ sở dữ liệu quan hệ.

Trạng thái cập nhật trong projection có thể trễ. Nếu khách hàng vừa đặt đơn và cần nhìn thấy ngay trên màn hình xác nhận, API có thể trả dữ liệu từ kết quả ghi SoR hoặc đọc đơn trực tiếp từ Orders Service. Phải ghi rõ ngoại lệ này trong hợp đồng API.

## 5. Tình huống B: Cassandra là nguồn chuẩn cho telemetry theo thời gian

Một nền tảng IoT nhận hàng triệu sự kiện nhiệt độ, rung hoặc vị trí; yêu cầu thường gặp là “lấy sự kiện của thiết bị X trong ngày D, theo thời gian gần nhất”. Sự kiện độc lập, ghi nhiều, không cần JOIN và có chính sách lưu giữ rõ ràng. Cassandra **có thể** là SoR cho các sự kiện đã được chấp nhận trong khoảng lưu giữ đã cam kết.

~~~mermaid
flowchart LR
    S[Thiết bị] --> I[Ingestion API: xác thực / chuẩn hóa]
    I --> Q[Hàng đợi bền vững nếu cần chịu tải đột biến]
    Q --> W[Java writer: idempotency]
    W --> C[(Cassandra - telemetry SoR)]
    C --> R[Telemetry Query API]
    C --> A[Backup / archive theo chính sách]
    M[(Device registry - SoR riêng)] --> I
~~~

Ở đây, **Device Registry** (sở hữu đăng ký, khóa và cấu hình thiết bị) vẫn có thể nằm trong PostgreSQL. Cassandra chỉ là SoR của *miền telemetry*. Nếu dữ liệu Cassandra có TTL 90 ngày, khái niệm “nguồn chuẩn” cũng chỉ áp dụng cho dữ liệu còn trong thời hạn 90 ngày; nếu nghiệp vụ yêu cầu chứng cứ trong nhiều năm, cần một kho lưu trữ bền vững được xác định rõ là nguồn chuẩn lịch sử.

### 5.1. Thiết kế CQL từ truy vấn, không từ mô hình thực thể

~~~sql
CREATE KEYSPACE telemetry
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE telemetry.events_by_device_day (
    device_id text,
    day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload_json text,
    PRIMARY KEY ((device_id, day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

SELECT event_time, event_id, event_type, payload_json
FROM telemetry.events_by_device_day
WHERE device_id = 'sensor-17'
  AND day = '2026-11-21'
  AND event_time >= '2026-11-21T00:00:00Z'
  AND event_time < '2026-11-22T00:00:00Z'
LIMIT 100;
~~~

Giải thích:

- **Partition key (device_id, day):** quyết định vị trí logic của dữ liệu trên các replica, đồng thời giới hạn một phép đọc vào một partition. Đây không phải cơ chế phân chia tải tự động bên trong một partition.
- **Clustering columns (event_time, event_id):** sắp xếp sự kiện trong partition; event_id phân biệt hai sự kiện cùng thời gian.
- **Khóa chính không đồng nghĩa ràng buộc duy nhất toàn hệ thống cho một eventId.** Nếu gửi cùng eventId nhưng thay device_id hoặc day, sẽ thành hàng khác. Bên ghi phải xác thực tính nhất quán của định danh.
- **Bảng tạo cho truy vấn:** nếu sản phẩm bổ sung “tất cả cảnh báo của một khu vực trong giờ qua”, cần thiết kế projection/bảng khác hoặc công cụ chuyên biệt; không mặc nhiên quét toàn cụm bằng ALLOW FILTERING.
- **Tránh partition nóng/lớn:** một thiết bị phát hàng chục nghìn event mỗi giây có thể cần bucket theo giờ, theo shard có kiểm soát hoặc cơ chế ingestion khác. Bucket càng nhỏ thì truy vấn dài ngày càng phải đọc nhiều partition; chọn bằng đo đạc.

Ví dụ ghi một sự kiện có định danh ổn định:

~~~sql
INSERT INTO telemetry.events_by_device_day
    (device_id, day, event_time, event_id, event_type, payload_json)
VALUES
    ('sensor-17', '2026-11-21', '2026-11-21T03:10:00Z',
     2f75b225-46f8-486c-96eb-a2743ae83365,
     'temperature', '{"celsius":28.4}');
~~~

Ứng dụng **phải giữ nguyên event_id và partition key khi retry cùng sự kiện**. Nếu tự tạo UUID mới mỗi lần gửi lại, hệ thống sẽ có các sự kiện trùng về ngữ nghĩa. Lưu thêm bản ghi “latest temperature” là một projection khác; hai bảng ghi độc lập không tạo thành một giao dịch nguyên tử toàn cục.

### 5.2. Lưu giữ, xóa dữ liệu và bền vững

TTL giúp dữ liệu tự hết hạn nhưng tạo **tombstone**, và việc dọn file dữ liệu phụ thuộc compaction. Với chuỗi thời gian có thời điểm ghi/hết hạn đồng nhất, có thể đánh giá **TimeWindowCompactionStrategy (TWCS)**. Cần đo tombstone, kích thước SSTable, đọc chậm, đĩa sử dụng và thời gian compaction; không chọn TWCS chỉ vì tên bảng có cột thời gian.

TTL không thay thế chính sách backup/archival. Nếu sự kiện là chứng cứ nghiệp vụ hoặc pháp lý, hãy xác định rõ nguồn lưu giữ dài hạn, thời điểm chuyển dữ liệu, cách kiểm chứng đã chuyển đủ và cách khôi phục. Xóa theo TTL/DELETE cũng yêu cầu vận hành đúng repair và các mốc liên quan đến tombstone để tránh dữ liệu đã xóa xuất hiện lại trong tình huống replica lỗi kéo dài.

## 6. Consistency level và phạm vi bảo đảm

Cassandra sao chép dữ liệu theo **replication factor (RF)**. Trong một data center có RF = 3, ghi **LOCAL_QUORUM** cần phản hồi từ ít nhất 2 replica tại data center đó; đọc LOCAL_QUORUM cũng cần 2. Mối quan hệ thường dùng:

\[
R + W > RF
\]

Với R = 2, W = 2 và RF = 3, tập replica xác nhận đọc và ghi có giao nhau trong điều kiện mô hình này. Đây là một cơ sở để chọn consistency level, **không phải cam kết giao dịch ACID xuyên nhiều partition, tuyến tính tuyệt đối cho mọi luồng ghi đồng thời, hay không bao giờ đọc trạng thái cũ**. Timestamp của mutation, write conflict, replica hỏng, dữ liệu đã hết hạn và cách ứng dụng xử lý ghi đồng thời vẫn quan trọng.

| Nhu cầu | Cấu hình thường cân nhắc | Phần ứng dụng vẫn phải xử lý |
|---|---|---|
| Telemetry chịu được chậm cập nhật rất ngắn, ưu tiên khả dụng | ONE hoặc LOCAL_ONE cho một số đường đọc/ghi phù hợp với cam kết | Dữ liệu cũ khi đọc, mất phản hồi replica, đối soát và repair. |
| Đọc/ghi quan trọng trong một data center | LOCAL_QUORUM với RF phù hợp, sau khi đo latency | Timeout không xác định đã commit hay chưa; ghi đồng thời, retry idempotent. |
| Ghi có điều kiện cho một hàng cần kiểm soát tranh chấp | LWT / IF với mức serial consistency phù hợp | Độ trễ và throughput thấp hơn ghi thường; không suy rộng thành transaction nhiều partition. |
| Yêu cầu giao dịch cập nhật tồn kho, thanh toán qua nhiều thực thể | SoR giao dịch hoặc phối hợp nghiệp vụ chuyên biệt | Cassandra không tự cung cấp ràng buộc SQL/ACID đa thực thể. |

**Timeout có kết quả mơ hồ:** client không nhận được phản hồi **không chứng minh ghi đã thất bại**; một số replica có thể đã lưu thành công. Với thao tác ghi sự kiện, dùng định danh ổn định và retry an toàn; với thanh toán/đếm tiền, dùng cơ chế idempotency nghiệp vụ tại chủ sở hữu. Không retry vô hạn hoặc tăng consistency level mà chưa kiểm tra khả năng phục vụ khi mất node.

**Replication không phải backup.** Sao chép cũng sao chép lỗi ghi hoặc thao tác xóa. Cần snapshot/backup theo RPO/RTO, diễn tập restore, theo dõi replication lag/repair, compaction backlog, lỗi coordinator và lượng tombstone. **Repair** giúp các replica hội tụ dữ liệu; nó không thể tự quyết định một đơn hàng “đã thanh toán” hay “đã hủy” khi hai nguồn thẩm quyền mâu thuẫn.

## 7. Kết nối từ ứng dụng Java

Java driver nên quản lý một **CqlSession dùng chung**, kết nối theo cấu hình cluster và data center thực tế; dùng prepared statement cho truy vấn lặp lại. Ví dụ ghi telemetry (trích đoạn Java dùng API driver 4.x):

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

// Cấu hình contact points, TLS, xác thực và timeout ở môi trường triển khai.
try (CqlSession session = CqlSession.builder()
        .withLocalDatacenter("dc1")
        .build()) {
    PreparedStatement insert = session.prepare(
        "INSERT INTO telemetry.events_by_device_day " +
        "(device_id, day, event_time, event_id, event_type, payload_json) " +
        "VALUES (?, ?, ?, ?, ?, ?)");

    String deviceId = "sensor-17";
    Instant eventTime = Instant.parse("2026-11-21T03:10:00Z");
    // ID được nhận từ upstream và giữ nguyên khi retry cùng một sự kiện.
    UUID eventId = UUID.fromString("2f75b225-46f8-486c-96eb-a2743ae83365");
    LocalDate day = eventTime.atZone(ZoneOffset.UTC).toLocalDate();

    BoundStatement write = insert.bind(
            deviceId, day, eventTime, eventId,
            "temperature", "{\"celsius\":28.4}")
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

    session.execute(write);
}
~~~

Trong dịch vụ thực tế, tạo session một lần trong vòng đời ứng dụng (ví dụ bean singleton) rồi đóng khi shutdown; đoạn trên chỉ minh họa một tác vụ độc lập. Cấu hình data center, replication, TLS và profile consistency phải khớp môi trường triển khai. Khi dùng asynchronous API, kiểm soát số request đang bay và backpressure để tải đột biến không gây cạn connection, queue hoặc bộ nhớ.

Nếu ghi timeout, mã ứng dụng cần có chính sách retry dựa trên **tính idempotent của thao tác**; ghi cùng eventId chưa đủ nếu có hiệu ứng phụ không idempotent ở dịch vụ khác. Gắn traceId/eventId, đo latency theo consistency level, tỷ lệ timeout, lỗi unavailable và backlog consumer để truy ngược nguồn sai lệch.

## 8. Hợp đồng dữ liệu chuẩn giữa các dịch vụ

Trước khi thêm Cassandra vào hệ thống, nên tạo một *data ownership contract* ngắn nhưng kiểm chứng được:

| Trường hợp cần quy định | Ví dụ quyết định rõ ràng |
|---|---|
| Miền dữ liệu và chủ sở hữu | Orders Service sở hữu trạng thái đơn; Telemetry Service sở hữu sự kiện cảm biến. |
| Bản ghi có thẩm quyền | PostgreSQL orders cho trạng thái đơn; Cassandra events_by_device_day cho telemetry còn trong thời hạn. |
| Ai được phép ghi | Chỉ domain service hoặc projection consumer được ghi đúng bảng; BI không sửa trực tiếp dữ liệu gốc. |
| Khóa nghiệp vụ và phiên bản | orderId + version; deviceId + day + eventTime + eventId; eventId giữ nguyên khi retry. |
| Quy tắc khi xung đột | Trạng thái đơn dựng lại từ PostgreSQL; sự kiện telemetry đối chiếu theo định danh nguồn và ingest log. |
| Yêu cầu nhất quán và freshness | Thao tác tiền đọc SoR; lịch sử đơn có thể trễ tối đa theo SLO; telemetry đo latency P95/P99. |
| Lưu giữ và khôi phục | TTL, archival, lịch backup, RPO/RTO, nguồn phát lại, người chịu trách nhiệm diễn tập. |
| Dấu hiệu cần cảnh báo | Lag consumer, projection mismatch, partition hot, tombstone, read/write timeout, repair overdue. |

### 8.1. Checklist nghiệm thu kiến trúc

- [ ] Với từng miền dữ liệu, đã nêu rõ **SoR, data owner, dữ liệu dẫn xuất** và quyền ghi.
- [ ] Mọi endpoint quan trọng đã ghi truy vấn theo partition key, kích thước partition dự kiến và SLO.
- [ ] Đã xác định trường hợp cần giao dịch nhiều thực thể; chúng không phụ thuộc vào hai lệnh ghi Cassandra độc lập.
- [ ] Có cơ chế idempotency, bảo vệ thứ tự/version và cách xử lý timeout kết quả mơ hồ.
- [ ] Nếu Cassandra là projection, có nguồn để rebuild, cách phát lại và kiểm tra chênh lệch.
- [ ] Nếu Cassandra là SoR, có chính sách TTL/archival/backup/restore phù hợp thời gian lưu giữ.
- [ ] Đã kiểm thử tải lệch khóa (hot partition), mất node, consumer backlog, dữ liệu trùng và out-of-order.
- [ ] Đã chọn và đo consistency level, replication factor, compaction, repair trên môi trường gần sản xuất.

### 8.2. Bài tập thiết kế

Hệ thống quản lý giao hàng có ba yêu cầu: (1) thanh toán và hoàn tiền chính xác; (2) cập nhật tọa độ tài xế mỗi 3 giây; (3) hiển thị 20 đơn gần nhất của khách. Hãy xác định cho từng nhóm dữ liệu SoR, vai trò của Cassandra, partition key, độ trễ có thể chấp nhận và chiến lược phục hồi khi consumer ngừng hoạt động một giờ.

Một phương án hợp lý: đặt trạng thái thanh toán ở dịch vụ giao dịch có thẩm quyền; lưu vị trí/timeline trong Cassandra theo tài xế và bucket thời gian nếu truy vấn phù hợp; tạo bảng lịch sử đơn trong Cassandra dưới dạng read model từ domain events. **Phương án cuối cùng phải phụ thuộc vào bất biến nghiệp vụ và truy vấn đã đo**, đặc biệt khi có yêu cầu tính giá theo hành trình, tranh chấp về vị trí, lưu giữ lâu năm hoặc truy vấn phân tích trên toàn bộ tài xế.

## 9. Kết luận

Vị trí đúng của Cassandra được quyết định từ **quyền sở hữu dữ liệu, bất biến nghiệp vụ và mẫu truy vấn**, sau đó mới đến CQL và kích thước cluster. Cassandra rất phù hợp cho bản ghi có khóa phân vùng rõ ràng, luồng sự kiện lớn và mô hình đọc phân tán; cũng có thể là SoR cho một miền dữ liệu đủ đơn giản về giao dịch. Khi dữ liệu chuẩn nằm ở hệ thống khác, phải xem Cassandra là projection có thể dựng lại và thiết kế rõ đường phát sự kiện, chống trùng, xử lý lệch thứ tự, độ trễ và đối soát. Một kiến trúc hoàn chỉnh luôn trả lời được câu hỏi: **“Nếu hai bản sao không giống nhau, ta tin nguồn nào và khôi phục ra sao?”**
