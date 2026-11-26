# Tạo keyspace với chiến lược sao chép phù hợp môi trường

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **keyspace**, **replication strategy**, **replication factor (RF)** và mối liên hệ với data center, replica, partition và consistency level trong Apache Cassandra.
- Chọn cấu hình sao chép hợp lý cho máy phát triển một node, môi trường kiểm thử nhiều node và cụm production một hoặc nhiều data center.
- Tạo, kiểm tra và thay đổi keyspace bằng CQL; nhận biết tác động vận hành khi tăng RF hoặc mở thêm data center.
- Kết nối ứng dụng Spring Data Cassandra vào đúng keyspace/data center, lựa chọn consistency level theo yêu cầu nghiệp vụ và xác minh khả năng chịu lỗi.
- Phát hiện những cấu hình tưởng hợp lệ nhưng gây mất tính sẵn sàng, truy vấn lệch vùng hoặc chi phí sao chép lớn.

Bài học thuộc **SPRING_DATA_CASSANDRA**: truy cập Apache Cassandra bằng entity mapping, repository, `CassandraTemplate` và truy vấn CQL. Khi ứng dụng bắt đầu đọc/ghi dữ liệu, **keyspace là quyết định hạ tầng đầu tiên** ảnh hưởng đến cách Cassandra đặt bản sao dữ liệu, tính sẵn sàng, độ trễ và khả năng mở rộng. Thiết kế bảng theo truy vấn, partition key và paging vẫn cần làm đúng; keyspace không tự sửa được mô hình bảng chưa phù hợp.

## 1. Keyspace là gì?

Trong Cassandra, **keyspace** là vùng tên chứa các bảng, kiểu dữ liệu và một số đối tượng schema khác. Nó cũng định nghĩa chính sách sao chép dữ liệu cho các bảng thuộc keyspace đó.

Ví dụ ứng dụng quản lý đơn hàng có thể dùng:

~~~text
Keyspace: order_service
├── orders_by_id
├── orders_by_customer_month
└── orders_by_store_day
~~~

Khi đọc bảng `order_service.orders_by_id`, Cassandra xác định partition dựa trên partition key, tìm các node chịu trách nhiệm cho token tương ứng rồi phối hợp các replica theo consistency level của request. Chính sách sao chép do keyspace quy định; cách phân nhóm và sắp xếp dòng trong partition do **primary key của bảng** quy định.

Ba khái niệm thường bị nhầm lẫn:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Partition key** của bảng | Dữ liệu của một partition được định tuyến theo khóa nào? | `customer_id`, hoặc `(customer_id, month_bucket)` |
| **Replication strategy / RF** của keyspace | Partition được sao chép đến những node/data center nào, bao nhiêu bản? | `NetworkTopologyStrategy`, `dc1: 3` |
| **Consistency level** của thao tác | Cần bao nhiêu replica phản hồi để thao tác được coi là thành công? | `LOCAL_ONE`, `LOCAL_QUORUM` |

> **Quan trọng:** Replica trong Cassandra là các **bản sao vật lý của cùng dữ liệu** trên nhiều node. Nó khác với việc ứng dụng chủ động lưu một đơn hàng ở nhiều bảng `orders_by_id` và `orders_by_customer_month`. Sao chép replica không làm cho các bảng thiết kế theo truy vấn tự đồng bộ với nhau.

### 1.1. Điều gì xảy ra khi ghi một partition?

Giả sử một data center có ba node và keyspace dùng RF = 3:

~~~mermaid
flowchart LR
    A[Ứng dụng Spring Data Cassandra] --> C[Coordinator Cassandra]
    C --> R1[Node A: replica]
    C --> R2[Node B: replica]
    C --> R3[Node C: replica]
~~~

Node nhận request có thể làm coordinator; nó không nhất thiết là một trong các replica của partition. Cassandra tìm các replica cần nhận mutation. Nếu request đặt `LOCAL_QUORUM`, trong ví dụ RF = 3, coordinator cần nhận phản hồi thành công từ **ít nhất hai replica trong data center cục bộ**. Replica thứ ba vẫn là đích sao chép; việc client nhận thành công không có nghĩa tất cả replica đã đồng bộ ngay tại thời điểm đó.

RF là **số bản sao mong muốn của mỗi partition trong phạm vi được khai báo**, không phải số lần chia nhỏ partition, số lượng shard hay số node mà truy vấn cần quét. RF cao không tự xử lý được một partition nóng hoặc partition quá lớn.

## 2. Hai chiến lược sao chép cần biết

### 2.1. `NetworkTopologyStrategy`: lựa chọn mặc định nên ưu tiên

`NetworkTopologyStrategy` cho phép khai báo RF **riêng cho từng data center (DC)**. Cassandra phân bổ replica với nhận thức về topology data center/rack, trong phạm vi thông tin topology thực tế mà cluster cung cấp.

Ví dụ:

~~~sql
CREATE KEYSPACE IF NOT EXISTS order_service
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;
~~~

Lệnh trên yêu cầu mỗi partition của `order_service` có ba replica trong DC mang tên chính xác `dc1`. Đây là ví dụ thích hợp khi DC có **ít nhất ba node lành mạnh** và topology/rack được cấu hình đúng. Với nhiều DC:

~~~sql
CREATE KEYSPACE IF NOT EXISTS order_service_prod
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
}
AND durable_writes = true;
~~~

Mỗi partition lúc này có mục tiêu ba replica tại `dc1` và ba replica tại `dc2`: tổng cộng sáu bản sao trên toàn cụm, nếu hai DC đủ node. `dc1` và `dc2` **chỉ là tên minh họa**; phải thay bằng tên DC thật do cluster báo về. Tên có thể là `datacenter1`, `ap-southeast-1` hoặc một giá trị khác theo môi trường.

`NetworkTopologyStrategy` phù hợp cả khi phát triển chỉ có một DC. Nhờ vậy, cú pháp và tư duy cấu hình nhất quán giữa local, staging và production; vẫn phải đặt RF theo số node thực tế.

### 2.2. `SimpleStrategy`: chỉ dành cho tình huống giới hạn

`SimpleStrategy` gán replica mà không có chính sách riêng cho từng DC; nó không phù hợp cho cụm nhiều data center và không nên là lựa chọn production thông thường.

~~~sql
-- Ví dụ để nhận diện cú pháp, không phải đề xuất cho production.
CREATE KEYSPACE legacy_demo
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};
~~~

Ngay cả với máy local một node, có thể dùng `NetworkTopologyStrategy` với RF = 1. Chỉ cân nhắc `SimpleStrategy` cho bài tập/cluster thử nghiệm rất hạn chế khi hiểu rõ giới hạn của nó; tránh mang cấu hình mẫu này sang production.

| Tiêu chí | `NetworkTopologyStrategy` | `SimpleStrategy` |
| --- | --- | --- |
| RF theo từng DC | Có, khai báo tên DC và RF | Không |
| Nhận biết topology DC/rack | Có, dựa vào cấu hình topology | Không theo mô hình đa DC |
| Local một node | Dùng được với RF = 1 | Có thể dùng, nhưng không cần thiết |
| Production nhiều DC | Phù hợp, nếu được thiết kế và vận hành đúng | Không phù hợp |
| Khi thêm DC | Có thể thêm RF cho DC mới; cần quy trình đưa dữ liệu vào replica mới | Không có cơ chế khai báo RF theo DC |

## 3. Chọn replication factor theo môi trường

RF phải gắn với **số node thực tế trên từng DC**, yêu cầu chịu lỗi, lưu lượng và mức chi phí lưu trữ. Không thể viết `RF = 3` rồi cho rằng một cụm chỉ có một node đã có ba bản sao độc lập.

| Môi trường | Topology minh họa | Cấu hình khuyến nghị ban đầu | Ý nghĩa |
| --- | --- | --- | --- |
| Local học tập | 1 node, DC `datacenter1` | `NetworkTopologyStrategy`, `datacenter1: 1` | Đủ chạy CQL và Spring Data; **không chịu được lỗi node** |
| CI/integration test | 1 node test cô lập | RF = 1 | Nhanh, tiết kiệm tài nguyên; không dùng để chứng minh HA |
| Staging mô phỏng production | 3 node trong DC `dc1` | `dc1: 3` | Có thể kiểm thử quorum, replica và lỗi một node |
| Production một DC | Tối thiểu 3 node phù hợp trong `dc1` | Thường bắt đầu với `dc1: 3` | Cân bằng phổ biến giữa sẵn sàng, chi phí và consistency |
| Production hai DC | Mỗi DC có tối thiểu 3 node phù hợp | `dc1: 3`, `dc2: 3` | Dữ liệu có bản sao ở cả hai DC; tốn thêm dung lượng và lưu lượng mạng |

Đây là **ví dụ thiết kế**, không phải quy tắc tuyệt đối. RF thực tế còn phụ thuộc rack, khả năng chứa dữ liệu, yêu cầu khôi phục, kích thước cụm và SLA. Một DC cần đủ số node/rack phù hợp để chiến lược có thể bố trí replica như mong muốn. Không thể đạt phân tán lỗi rack chỉ bằng việc khai báo RF nếu các node cùng nằm trên một miền lỗi vật lý.

### 3.1. Vì sao RF = 3 thường được dùng?

Với RF = 3 trong một DC, `LOCAL_QUORUM` cần:

\[
\left\lfloor\frac{RF}{2}\right\rfloor + 1
= \left\lfloor\frac{3}{2}\right\rfloor + 1 = 2
\]

Tức là có thể đạt quorum khi một trong ba replica không phản hồi, **với điều kiện các yếu tố khác vẫn bình thường**. Cùng lúc, mỗi partition phải có thêm hai bản sao so với RF = 1 nên chi phí lưu trữ, mạng và xử lý ghi tăng. RF = 2 có `LOCAL_QUORUM = 2`, tức phải nhận phản hồi của cả hai replica; nó không mang lại lợi thế chịu lỗi một replica ở mức quorum. Đây là một lý do RF lẻ như 3 thường thuận tiện cho thiết kế quorum.

### 3.2. Ước lượng lưu trữ không được bỏ qua

Nếu dữ liệu logic sau nén của một keyspace chiếm xấp xỉ 500 GB, RF = 3 có thể yêu cầu cỡ **1,5 TB dữ liệu bản sao trong DC** trước khi tính commit log, compaction, snapshot, tombstone, index, tăng trưởng dữ liệu và khoảng trống vận hành. Hai DC đều RF = 3 sẽ lưu bản sao ở cả hai nơi. Con số thực tế phải được đo từ workload, schema, hệ số nén và chính sách vận hành; không lấy phép nhân RF làm dự toán ổ đĩa cuối cùng.

Ngược lại, RF thấp giúp tiết kiệm tài nguyên nhưng có thể đánh đổi mất tính sẵn sàng và khả năng phục hồi. Cần quyết định theo yêu cầu môi trường, không chỉ theo dung lượng đĩa còn trống.

## 4. Thực hành tạo keyspace cho ba môi trường

### 4.1. Kiểm tra DC trước khi viết CQL

Trên một node Cassandra được phép vận hành, kiểm tra topology:

~~~bash
nodetool status
~~~

Kết quả chứa các nhóm `Datacenter: ...`, danh sách node, trạng thái `UN` (Up/Normal) và thông tin rack. Dùng **đúng tên DC** ở đây trong cấu hình keyspace và trong `spring.cassandra.local-datacenter` của ứng dụng.

Nếu `nodetool status` báo `Datacenter: datacenter1`, dùng `datacenter1` trong CQL. Đừng đổi thành `dc1` chỉ vì hướng dẫn minh họa như vậy. Nếu có node Down, Joining hoặc dữ liệu chưa ổn định, cần kiểm tra tình trạng cụm trước khi thay đổi topology/schema production.

### 4.2. Local một node

Giả sử node local được cấu hình thuộc DC `datacenter1`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS order_service_dev
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 1
}
AND durable_writes = true;

USE order_service_dev;

CREATE TABLE IF NOT EXISTS orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    status text,
    created_at timestamp
);
~~~

Điều kiện `IF NOT EXISTS` giúp việc chạy lại lệnh tạo không báo lỗi nếu keyspace/bảng đã tồn tại. Nó **không kiểm tra cấu hình cũ có đúng như mong muốn hay không**. Khi triển khai thật, migration hoặc quy trình kiểm tra phải so sánh schema hiện tại với schema mong đợi.

Trong `cqlsh` có thể thử:

~~~sql
INSERT INTO orders_by_id (order_id, customer_id, status, created_at)
VALUES (
    11111111-1111-4111-8111-111111111111,
    22222222-2222-4222-8222-222222222222,
    'NEW',
    '2026-01-15T09:00:00Z'
);

SELECT * FROM orders_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
~~~

Truy vấn dùng đúng partition key `order_id`. Nếu muốn truy vấn lịch sử đơn theo khách hàng, cần thiết kế bảng theo truy vấn riêng với partition key thích hợp; tăng RF không làm `WHERE customer_id = ...` trên bảng này trở thành truy vấn tối ưu.

### 4.3. Staging ba node, một DC

Với ba node ở `dc1`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS order_service_staging
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;
~~~

Staging nên mô phỏng các đặc tính production mà nhóm cần kiểm chứng, nhất là RF, consistency, lỗi node, timeout và khôi phục. Nếu staging thực tế chỉ có một node thì RF = 3 không phải phép thay thế cho việc dựng thêm node; hãy dùng RF = 1 và ghi rõ đây là môi trường không có khả năng kiểm thử chịu lỗi.

### 4.4. Production hai DC

Với hai DC độc lập, mỗi DC tối thiểu ba node đủ điều kiện:

~~~sql
CREATE KEYSPACE IF NOT EXISTS order_service_prod
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
}
AND durable_writes = true;
~~~

Chiến lược này yêu cầu Cassandra lưu bản sao dữ liệu ở hai DC. Cần xét thêm các chính sách về lưu lượng liên DC, thời gian khôi phục, mức độ đồng bộ mong muốn giữa khu vực và cách route request của client. **RF ở DC2 không có nghĩa mọi thao tác đọc tại DC2 lập tức nhìn thấy kết quả ghi vừa hoàn tất tại DC1 khi client chỉ yêu cầu `LOCAL_QUORUM` tại DC1.**

### 4.5. `durable_writes` nên đặt thế nào?

`durable_writes = true` là lựa chọn thông thường cho dữ liệu nghiệp vụ: Cassandra sử dụng commit log cho đường ghi bền vững theo cơ chế của nó. Đặt `false` có thể làm suy yếu khả năng phục hồi khi node gặp sự cố và không phải cách tối ưu hiệu năng mặc định cho dịch vụ quan trọng.

Tham số này **không** biến nhiều lệnh CQL thành giao dịch ACID đa bảng. Nó cũng không thay thế việc chọn consistency level hoặc xây dựng backup/khôi phục.

## 5. Phối hợp RF với consistency level

**Replication factor** quy định số replica mục tiêu. **Consistency level (CL)** quy định số phản hồi cần có cho từng thao tác. Hai cấu hình bổ sung cho nhau nhưng không đồng nghĩa.

Với `NetworkTopologyStrategy`, các mức thường gặp:

| Consistency level | Điều kiện phản hồi trong tình huống thông thường | Đánh đổi |
| --- | --- | --- |
| `LOCAL_ONE` | Một replica ở DC cục bộ | Độ trễ và yêu cầu sẵn sàng thấp hơn; có thể đọc bản sao chưa cập nhật |
| `LOCAL_QUORUM` | Đa số replica của keyspace trong DC cục bộ | Mạnh hơn cho đường đọc/ghi cùng DC, đổi lại cần nhiều phản hồi |
| `QUORUM` | Đa số replica trên toàn các DC có tham gia sao chép | Có thể làm phát sinh phụ thuộc liên DC; phải tính theo topology thực tế |
| `EACH_QUORUM` | Với ghi, đạt quorum ở **mỗi DC** trong cấu hình sao chép | Chi phí liên DC cao, giảm khả năng ghi khi một DC không đáp ứng |

`EACH_QUORUM` chủ yếu có ý nghĩa ở đường ghi, không xem như mức đọc thông thường. Các mức CL khác như `ONE`, `TWO`, `THREE`, `ALL`, `SERIAL`, `LOCAL_SERIAL` còn có mục đích riêng; với lightweight transaction (LWT), serial consistency là phần cấu hình khác với CL thông thường của thao tác.

Ví dụ trong một DC RF = 3:

| CL đọc | CL ghi | Số phản hồi tối thiểu | Điều cần nhớ |
| --- | --- | --- | --- |
| `LOCAL_ONE` | `LOCAL_ONE` | 1 đọc, 1 ghi | Sẵn sàng cao hơn nhưng đọc có thể gặp replica chưa cập nhật |
| `LOCAL_QUORUM` | `LOCAL_QUORUM` | 2 đọc, 2 ghi | Hai tập phản hồi bắt buộc giao nhau trong ba replica, dưới các giả định phù hợp |
| `LOCAL_QUORUM` | `LOCAL_ONE` | 2 đọc, 1 ghi | Tổng số không vượt RF; không có bảo đảm giao nhau từ phép tính quorum |
| `LOCAL_QUORUM` | `ALL` | 2 đọc, 3 ghi | Ghi phải có tất cả replica, nhạy với sự cố một replica |

Với một partition trong một DC, quy tắc quen thuộc là **R + W > RF** để tập replica được xác nhận ghi và tập replica phản hồi đọc có giao nhau. Tuy nhiên đây không phải cam kết “đọc luôn chính xác mới nhất” trong mọi trường hợp: còn ghi đồng thời, timestamp của mutation, lỗi/timeout, thay đổi topology và các cơ chế sửa/đồng bộ replica. Nếu ứng dụng cần điều kiện cập nhật kiểu so sánh giá trị hiện có, phải nghiên cứu LWT (`IF ...`), ràng buộc nghiệp vụ và tính đúng đắn khi retry.

### 5.1. Đa DC: đọc/ghi ở đâu?

Giả sử keyspace dùng `dc1: 3`, `dc2: 3`:

1. Client tại `dc1` ghi với `LOCAL_QUORUM`: cần hai phản hồi replica **tại dc1** để báo thành công.
2. Các replica tại `dc2` vẫn được Cassandra sao chép theo cơ chế cụm, nhưng không nằm trong điều kiện quorum cục bộ của client tại `dc1`.
3. Client ở `dc2` đọc ngay sau đó bằng `LOCAL_QUORUM`: không nên mặc định luôn thấy mutation mới nhất từ `dc1` tại chính thời điểm ghi ở `dc1` vừa hoàn tất.
4. Nếu sản phẩm yêu cầu đọc sau ghi xuyên DC với bảo đảm chặt, phải định nghĩa rõ hợp đồng consistency và thiết kế đường request/ghi/đọc phù hợp, đo độ trễ mạng và kiểm thử các trường hợp mất kết nối DC.

RF không giải quyết “đồng bộ hai bảng” hay “đọc sau ghi xuyên DC” chỉ bằng cách tăng từ 2 lên 3. Cần mô tả chính xác yêu cầu sản phẩm: dữ liệu nào chấp nhận trễ, được phép trễ bao lâu, khi mất một DC thì ưu tiên tính sẵn sàng hay tính nhất quán.

## 6. Kiểm tra keyspace sau khi tạo

### 6.1. Xem cấu hình replication trong schema

Chạy trong `cqlsh`:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'order_service_prod';
~~~

Kết quả mong đợi về mặt nội dung là `NetworkTopologyStrategy`, các cặp `dc1: 3`, `dc2: 3` và `durable_writes = true`. Trình bày/thứ tự các phần tử của map có thể khác nhau giữa client và phiên bản Cassandra.

Trong `cqlsh` cũng có thể dùng lệnh tiện ích:

~~~text
DESCRIBE KEYSPACE order_service_prod;
~~~

`DESCRIBE` là lệnh của `cqlsh`, không phải CQL query mà ứng dụng sẽ gửi qua driver theo cách thông thường.

### 6.2. Xem trạng thái cluster và kiểm tra đường đọc/ghi

~~~bash
nodetool status
~~~

Đối chiếu số node `UN` trên **từng DC**, rack và thông tin topology với RF. `status = UN` là một tín hiệu cần thiết nhưng **chưa đủ** để kết luận mọi replica đã đồng bộ đầy đủ sau khi tăng RF hoặc thêm DC. Kiểm tra thêm trạng thái hoạt động, quy trình rebuild/repair, lỗi driver và số liệu vận hành phù hợp với phiên bản Cassandra.

Trong `cqlsh`, thử thay CL của **phiên làm việc** để kiểm tra đường truy cập:

~~~text
CONSISTENCY LOCAL_QUORUM;
~~~

Sau đó chạy truy vấn theo partition key trên bảng thử nghiệm và quan sát lỗi, độ trễ. Đừng suy diễn rằng thử thành công một lần chứng minh khả năng chịu lỗi: cần kịch bản lỗi replica có kiểm soát, số liệu p95/p99 và kiểm tra khôi phục trên staging phù hợp.

### 6.3. Checklist trước khi cho ứng dụng sử dụng

- Tên DC trong keyspace khớp chính xác tên DC cluster cung cấp.
- Mỗi DC có đủ node lành mạnh cho RF dự kiến; phân bố rack/miền lỗi đạt mục tiêu triển khai.
- Schema keyspace thực tế khớp migration mong đợi, kể cả trường hợp `IF NOT EXISTS` đã bỏ qua việc tạo.
- Driver được cấu hình `local-datacenter` đúng với DC nơi ứng dụng ưu tiên truy cập.
- CL đọc/ghi được chọn dựa trên yêu cầu sản phẩm và được kiểm thử trong trường hợp lỗi.
- Có năng lực lưu trữ, băng thông, quan sát, backup và quy trình phục hồi phù hợp với số replica.

## 7. Kết nối Spring Data Cassandra vào keyspace

Ví dụ ứng dụng Spring Boot sử dụng Spring Data Cassandra, chạy gần các node ở `dc1`:

~~~yaml
spring:
  cassandra:
    contact-points:
      - cassandra-1.internal
      - cassandra-2.internal
      - cassandra-3.internal
    port: 9042
    local-datacenter: dc1
    keyspace-name: order_service_prod
    request:
      consistency: LOCAL_QUORUM
~~~

Tên thuộc tính là ví dụ theo quy ước cấu hình Spring Boot hiện đại; khi triển khai phải đối chiếu phiên bản Spring Boot/DataStax Java Driver đang dùng, vì cách cấu hình driver và lựa chọn mặc định có thể khác nhau. `contact-points` là các điểm khởi đầu khám phá cụm, không phải danh sách đủ mọi replica, và **không thay thế** cấu hình replication ở keyspace.

Giải thích:

- `keyspace-name` là keyspace ứng dụng sử dụng khi truy vấn bảng không ghi đầy đủ tên. Keyspace nên được provision và kiểm tra **trước** khi dịch vụ bắt đầu phục vụ request.
- `local-datacenter` điều khiển chính sách ưu tiên DC của driver và các consistency level `LOCAL_*`. Phải khớp tên DC của cụm, không suy từ tên region của ứng dụng.
- `request.consistency` thể hiện mức consistency mặc định của thao tác driver nếu không bị ghi đè bởi cấu hình riêng của câu lệnh.
- Số contact point không quyết định RF. Nếu có ba contact point trong cùng DC nhưng keyspace RF = 1, mỗi partition vẫn chỉ có một replica theo chính sách RF = 1.

Một repository có thể truy cập bảng trong keyspace đã cấu hình:

~~~java
@Table("orders_by_id")
public class OrderById {
    @PrimaryKey("order_id")
    private UUID orderId;

    @Column("customer_id")
    private UUID customerId;

    @Column("status")
    private String status;

    // Constructor, getter và setter...
}

public interface OrderByIdRepository
        extends CassandraRepository<OrderById, UUID> {
}
~~~

Repository hỗ trợ CRUD và entity mapping, nhưng việc chọn **keyspace/RF/CL** không do annotation `@Table` quyết định. `CassandraTemplate` và truy vấn CQL cũng phải tuân theo cùng đường phân vùng và mức consistency của cluster/driver. Với các bảng phục vụ truy vấn khác nhau, ứng dụng vẫn chịu trách nhiệm cập nhật dữ liệu được nhân bản ở cấp bảng.

Trong production, nên dùng cơ chế migration/schema provisioning có kiểm soát thay vì để mỗi instance ứng dụng tự tạo hoặc thay đổi keyspace khi khởi động. Nếu nhiều ứng dụng cùng kết nối, cần quy định rõ ai sở hữu schema, ai được phép chỉnh RF và cách triển khai thay đổi.

## 8. Thay đổi RF hoặc thêm data center: thao tác schema chưa đủ

Đây là phần dễ gây lỗi vận hành nhất. Giả sử keyspace ban đầu chỉ có `dc1: 3`, sau đó hạ tầng bổ sung DC `dc2`:

~~~sql
ALTER KEYSPACE order_service_prod
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
};
~~~

Lệnh `ALTER KEYSPACE` thay đổi **chính sách sao chép được khai báo**, nhưng không có nghĩa mọi dữ liệu lịch sử đã được truyền đầy đủ tới replica mới ngay lập tức. Việc tăng RF trong một DC cũng có thể tạo ra những replica mới cần được đồng bộ dữ liệu.

### 8.1. Quy trình thay đổi an toàn ở mức khái niệm

1. **Kiểm tra điều kiện trước thay đổi:** topology, số node/rack, sức chứa, tải hiện tại, trạng thái schema, backup, quyền thực hiện và mục tiêu chịu lỗi.
2. **Lập kế hoạch RF mới:** nêu rõ DC nào tăng RF/thêm mới, CL của ứng dụng, đường route traffic và cách đo thành công.
3. **Thay đổi schema có kiểm soát:** chạy `ALTER KEYSPACE` qua quy trình vận hành đã được duyệt, tránh nhiều automation chạy chồng nhau.
4. **Đưa dữ liệu cũ đến replica mới:** thực hiện quy trình rebuild/repair/streaming phù hợp với phiên bản Cassandra, kiểu thay đổi và topology. Thêm DC mới thường đòi hỏi kế hoạch `nodetool rebuild`; tăng RF có thể cần repair/đồng bộ theo hướng dẫn vận hành của phiên bản triển khai.
5. **Chờ việc đồng bộ hoàn tất và xác minh:** kiểm tra schema, node, luồng dữ liệu, lỗi, tính đầy đủ dữ liệu thử nghiệm, số liệu repair và độ trễ.
6. **Cập nhật client một cách có chủ đích:** thay đổi local DC, CL hoặc route traffic nếu kiến trúc yêu cầu; thử nghiệm đọc/ghi tại từng DC trước khi chuyển lưu lượng chính.

Không có một lệnh `nodetool` duy nhất phù hợp mọi kiểu mở rộng và mọi phiên bản. Vận hành production phải theo runbook cụ thể của cluster/version, bảo đảm tránh gây quá tải đường truyền, compaction và read/write. Sau khi giảm RF hoặc loại DC, cũng cần quy trình riêng để kiểm tra hệ quả dữ liệu, tài nguyên và khả năng khôi phục.

### 8.2. Vì sao không nên dùng `CREATE KEYSPACE IF NOT EXISTS` để “nâng cấp”?

Giả sử keyspace đang là `dc1: 1`, bạn chạy lại:

~~~sql
CREATE KEYSPACE IF NOT EXISTS order_service_prod
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
~~~

Lệnh có thể kết thúc mà không thay đổi keyspace đã tồn tại. Do đó phải **đọc lại schema** và dùng `ALTER KEYSPACE` khi thực sự cần cập nhật cấu hình hiện hành. Tương tự, thay RF trong `application.yml` của Spring Boot không có tác dụng nếu ứng dụng không thực hiện thay đổi schema trên Cassandra.

## 9. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `UnavailableException` khi ghi `LOCAL_QUORUM` | Không đủ replica ở DC cục bộ, RF/topology khác dự kiến hoặc node đang lỗi | Xem `nodetool status`, schema keyspace và log, khôi phục replica rồi mới quyết định đổi CL |
| Cấu hình `dc1: 3` nhưng cụm chỉ có một node | RF vượt quá số node có thể lưu các replica độc lập | Đặt RF theo môi trường hoặc mở rộng đủ node; không coi RF khai báo là HA đã đạt |
| `InvalidQueryException` hoặc driver không kết nối đúng DC | Sai tên keyspace/DC, schema chưa tạo, cấu hình local DC không khớp hoặc quyền truy cập thiếu | So sánh `system_schema.keyspaces`, `nodetool status`, driver config và log xác thực |
| Đọc tại DC2 chưa thấy ghi mới nhất từ DC1 | CL cục bộ ở hai DC không tự bảo đảm read-after-write xuyên DC | Xác định yêu cầu consistency, route request và chiến lược đọc/ghi phù hợp |
| Tăng RF xong nhưng dữ liệu lịch sử chưa đủ ở replica mới | Chưa hoàn tất streaming/rebuild/repair cần thiết | Thực hiện đúng runbook và xác minh dữ liệu trước khi đổi lưu lượng |
| Ghi/đọc chậm sau khi tăng RF | Băng thông, đĩa, compaction, replica không ổn định hoặc CL quá cao so với hạ tầng | Theo dõi p95/p99, timeout, queue, tải node và dung lượng; điều chỉnh dựa trên số đo |
| Đơn hàng hiển thị lệch giữa hai bảng | Read model ở cấp ứng dụng chưa cập nhật đồng bộ | Kiểm tra cơ chế đồng bộ bảng, retry, revision và đối soát; tăng RF không giải quyết |

> **Không hạ consistency level ngay khi gặp lỗi quorum chỉ để request thành công.** Giảm CL có thể là quyết định có chủ đích trong một chính sách degrade, nhưng phải biết nghiệp vụ có chấp nhận việc đọc dữ liệu cũ hoặc độ bền ghi thay đổi hay không. Ưu tiên tìm nguyên nhân node, mạng, topology và RF trước.

## 10. Theo dõi gì sau khi đưa keyspace vào sử dụng?

Một cấu hình đúng lúc tạo có thể trở nên không phù hợp khi dữ liệu và tải tăng. Các nhóm chỉ số nên theo dõi:

| Nhóm | Quan sát | Lý do |
| --- | --- | --- |
| Trạng thái cụm | Node up/down, rack/DC, schema và thao tác streaming/repair | Xác định có đủ replica và cluster ổn định không |
| Độ trễ đọc/ghi | p50, p95, p99 theo CL và DC | Đánh giá chi phí của RF, CL và đường mạng |
| Lỗi | Read/write timeout, unavailable, retry, lỗi driver | Phát hiện giảm khả năng phục vụ hoặc lỗi cấu hình |
| Dung lượng | Dữ liệu trên đĩa, compaction, snapshot, tăng trưởng | Dự toán chi phí nhân theo RF và tránh cạn dung lượng |
| Phân vùng | Partition size, hot partition, tombstone | Phát hiện vấn đề thiết kế bảng mà RF không khắc phục |
| Đa DC | Băng thông liên DC, replica lag và kiểm thử failover | Kiểm tra kỳ vọng khôi phục và đọc/ghi giữa các vùng |

Chỉ kiểm tra `nodetool status` lúc triển khai là chưa đủ. Phải kiểm chứng hệ thống sau khi lưu lượng thực tế chạy, khi thay đổi schema và khi diễn tập sự cố.

## 11. Tình huống thực hành: từ local lên production

Nhóm phát triển ứng dụng đơn hàng đang chạy Cassandra local một node với DC `datacenter1`. Khi chuẩn bị ra production, hạ tầng có sáu node ở hai DC, mỗi DC ba node. API chi tiết đơn hàng yêu cầu không trả dữ liệu cũ sau khi cập nhật trong cùng khu vực khi hệ thống ổn định; màn hình báo cáo có thể chấp nhận độ trễ.

**Bước 1 — Chọn keyspace cho local:**

~~~sql
CREATE KEYSPACE IF NOT EXISTS order_service_dev
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 1
}
AND durable_writes = true;
~~~

**Bước 2 — Chọn keyspace cho production:**

~~~sql
CREATE KEYSPACE IF NOT EXISTS order_service_prod
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
}
AND durable_writes = true;
~~~

**Bước 3 — Chọn đường truy cập:** Ứng dụng chạy tại `dc1` ưu tiên coordinator/replica của `dc1` và có thể bắt đầu kiểm thử với `LOCAL_QUORUM` cho đường đọc/ghi dữ liệu quan trọng. Một ứng dụng báo cáo chấp nhận dữ liệu trễ có thể cân nhắc CL thấp hơn nếu SLA cho phép; việc quyết định phải có thử nghiệm và chính sách lỗi rõ ràng.

**Bước 4 — Xác minh:** So sánh schema, kiểm tra đủ ba node hoạt động mỗi DC, chạy workload với CL dự kiến và diễn tập lỗi một replica trên staging. Nếu ứng dụng chuyển giữa hai DC, kiểm tra riêng tính nhất quán quan sát được sau ghi xuyên DC thay vì mặc định giống kiểm thử trong cùng DC.

**Bước 5 — Giữ đúng ranh giới dữ liệu:** Với `orders_by_id` và `orders_by_customer_month`, tạo read model theo partition key mà màn hình cần. Keyspace RF3 bảo vệ replica của **mỗi bảng**, còn việc cập nhật hai bảng khi trạng thái đơn thay đổi vẫn là trách nhiệm của ứng dụng hoặc luồng đồng bộ được thiết kế riêng.

### Câu hỏi tự kiểm tra

1. Máy local có một node thuộc `datacenter1`. Vì sao khai báo `NetworkTopologyStrategy` với `dc1: 3` là sai dù CQL có thể trông hợp lệ?
2. Với RF = 3 ở một DC, `LOCAL_QUORUM` cần bao nhiêu replica phản hồi? RF = 2 thì sao?
3. Vì sao khi thêm `dc2: 3` vào keyspace, chỉ chạy `ALTER KEYSPACE` chưa đủ để bảo đảm dữ liệu lịch sử xuất hiện tại mọi replica mới?
4. `IF NOT EXISTS` có xác nhận keyspace đang có RF giống câu lệnh `CREATE KEYSPACE` mới hay không?
5. Hai API cùng đọc `LOCAL_QUORUM` nhưng ở hai DC khác nhau có tự động có bảo đảm read-after-write xuyên DC không?
6. Vì sao Spring Data Cassandra repository không thể sửa một truy vấn sai partition key chỉ bằng cách tăng RF?

### Gợi ý đáp án

1. RF vượt quá số node độc lập và tên DC không khớp topology thực tế; cấu hình không tạo được ba replica độc lập.
2. RF = 3 cần hai phản hồi; RF = 2 cũng cần hai phản hồi, nên mất một replica sẽ không đạt quorum.
3. Thay đổi schema không tự xác nhận việc truyền hết dữ liệu cũ; cần quy trình rebuild/repair/streaming thích hợp rồi xác minh.
4. Không. `IF NOT EXISTS` bỏ qua việc tạo nếu đã tồn tại; cần kiểm tra schema và dùng `ALTER KEYSPACE` nếu muốn thay đổi.
5. Không. Quorum cục bộ ở một DC không bảo đảm quorum cục bộ ở DC kia đã quan sát mutation vừa ghi.
6. RF điều khiển vị trí bản sao của partition; truy vấn hiệu quả phụ thuộc thiết kế bảng và khóa, không phụ thuộc số replica.

## Kết luận

Tạo keyspace là bước kết nối yêu cầu dữ liệu của ứng dụng với topology vật lý của Cassandra. Với **Spring Data Cassandra**, hãy ưu tiên `NetworkTopologyStrategy`, khai báo RF theo **tên DC thật** và số node thực tế, phối hợp consistency level với SLA, rồi kiểm tra schema và khả năng chịu lỗi trước khi đưa repository, `CassandraTemplate` và CQL vào phục vụ. Thay đổi RF hoặc thêm DC là một công việc **vừa có phần schema vừa có phần vận hành dữ liệu**. Thiết kế bảng theo truy vấn, giới hạn partition, paging và cơ chế đồng bộ dữ liệu giữa nhiều bảng vẫn cần được xử lý ở đúng tầng của chúng.
