# Đo với mô hình dữ liệu, topology và phân bố tải đại diện

**Chương: Hiệu năng — Spring Data Cassandra**

Một bài kiểm thử có thể báo **50.000 truy vấn/giây** trên Cassandra nhưng hệ thống thật vẫn trễ hoặc timeout nếu phép đo dùng partition key phân bố đều, bảng rất nhỏ, một node chạy trên cùng máy với ứng dụng và chỉ đọc một hàng mỗi lần. Trong sản xuất, yêu cầu có thể tập trung vào một số ít partition, đọc qua nhiều trang, ghi đồng thời với compaction và phải đạt `LOCAL_QUORUM` qua nhiều replica.

Đối với **Spring Data Cassandra**, hiệu năng đến từ sự phối hợp của **mô hình dữ liệu theo truy vấn**, cấu hình entity/repository/`CassandraTemplate`, truy vấn CQL, partition key, tính nhất quán, paging, cấu hình Java Driver, topology cluster và hành vi thực tế của người dùng. Để kết quả benchmark có ý nghĩa, cần giữ những yếu tố ấy đủ giống workload cần phục vụ.

Bài này trình bày cách **thiết kế một phép đo có thể tái lập**, từ giả thuyết và dữ liệu mẫu đến điều khiển tải, thu thập số liệu và kết luận. Mục tiêu không phải chạy được một con số throughput cao nhất, mà là **biết hệ thống sẽ ứng xử thế nào ở mức tải và dữ liệu dự kiến**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Xác định những đặc tính của **schema và partition** phải bảo toàn khi tạo dữ liệu benchmark: số partition, số hàng/partition, độ lớn hàng, skew, TTL, tombstone và độ tuổi dữ liệu.
- Thiết lập cluster thử có **topology, replication factor, local datacenter, consistency và network** phù hợp với câu hỏi hiệu năng.
- Mô phỏng tỷ lệ đọc/ghi, các loại query, page size, mức đồng thời, tốc độ đến và các đợt tăng tải; phân biệt offered load với throughput thực đạt.
- Đo latency từ góc nhìn người dùng Spring Data và đối chiếu với số liệu Java Driver và Cassandra.
- Phát hiện hot partition, retry khuếch đại tải, client bottleneck, coordinated omission và kết luận sai khi dùng Cassandra một node.
- Thiết kế thí nghiệm thay đổi từng yếu tố, ghi điều kiện chạy để so sánh được giữa các lần benchmark.

## 2. “Đại diện” là đại diện cho điều gì?

Một benchmark cần trả lời một câu hỏi có phạm vi rõ ràng, chẳng hạn:

> Với 1.500 request/giây, tỷ lệ đọc/ghi 85/15, dữ liệu có 5% khách hàng hoạt động rất thường xuyên, ứng dụng có giữ được p99 đọc dưới 200 ms và tỷ lệ lỗi dưới 0,1% khi đọc ở `LOCAL_QUORUM` không?

Đó là một **giả thuyết kiểm tra được**. “Cassandra nhanh bao nhiêu?” thì không đủ cụ thể để chọn thiết kế, tạo dữ liệu hay giải thích kết quả.

Ba trụ cột của phép đo là:

| Trụ cột | Điều cần tái hiện | Nếu làm sai, kết quả bị lệch |
|---|---|---|
| **Mô hình dữ liệu** | Schema, query shape, partition key, clustering, số hàng/partition, kích thước row, tombstone, TTL | Bảng nhỏ và partition đều che giấu truy vấn đắt, hotspot hoặc compaction |
| **Topology hệ thống** | Số node, DC/rack/AZ, RF, consistency, CPU/RAM/disk/network, vị trí ứng dụng | Một node local không thể đại diện latency quorum hay hoạt động khi replica thiếu |
| **Phân bố tải** | Tỷ lệ read/write, hot keys, concurrency, arrival rate, burst, page size, thời gian chạy | Chỉ chạy sequential read vào cache tạo p99 và throughput thiếu thực tế |

~~~mermaid
flowchart LR
    A["Phân bố yêu cầu thực tế"] --> B["API / Service Spring"]
    B --> C["Repository / CassandraTemplate"]
    C --> D["Cassandra Java Driver"]
    D --> E["Cluster Cassandra: DC, node, replica"]
    F["Schema và dữ liệu đã nạp"] --> E
    G["CPU, disk, network, compaction"] --> E
    H["Metrics client + Driver + node"] -.-> B
    H -.-> D
    H -.-> E
~~~

Đo **đầu cuối ứng dụng** giúp thấy chi phí API, mapping, logic nghiệp vụ và serialization. Đo riêng CQL/Driver giúp phân biệt nguyên nhân trong tầng truy cập dữ liệu. Hai phép đo bổ sung cho nhau; không lấy latency của lệnh CQL đơn giản thay cho latency người dùng nhìn thấy.

## 3. Bắt đầu từ query shape và thiết kế bảng

Cassandra thường được thiết kế **bảng theo truy vấn**, thay vì một mô hình chuẩn hóa duy nhất rồi cho phép tùy ý lọc bằng mọi cột. Benchmark muốn có ý nghĩa phải chạy đúng các query mà ứng dụng sử dụng.

### 3.1. Ví dụ: lịch sử đơn hàng theo khách hàng và tháng

Giả sử API hiển thị các đơn hàng gần đây của một khách hàng trong một tháng. Thiết kế tối giản:

~~~sql
CREATE KEYSPACE IF NOT EXISTS app_perf
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS app_perf.orders_by_customer_month (
    customer_id uuid,
    order_month text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_cents bigint,
    PRIMARY KEY ((customer_id, order_month), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
~~~

- **Partition key** là cặp `(customer_id, order_month)`. Tất cả đơn hàng của một khách trong cùng tháng thuộc một partition.
- `created_at` và `order_id` là **clustering columns** để sắp thứ tự và bảo đảm nhiều đơn cùng timestamp vẫn có khóa duy nhất.
- `order_month` ở dạng `YYYY-MM` là **bucket thời gian**: giảm nguy cơ tích lũy toàn bộ lịch sử của một khách vào một partition không giới hạn.
- Keyspace dùng `NetworkTopologyStrategy` với RF=3 trong `dc1` làm ví dụ cho benchmark cluster nhiều node; tên DC phải khớp môi trường thực. Nó **không phù hợp** nếu bạn chỉ chạy một Cassandra container đơn node.

Truy vấn đại diện cho màn hình lấy đơn gần đây:

~~~sql
SELECT customer_id, order_month, created_at, order_id, status, total_cents
FROM app_perf.orders_by_customer_month
WHERE customer_id = ? AND order_month = ?
LIMIT 50;
~~~

Truy vấn trong cùng partition, tận dụng clustering order. Truy vấn khác như “đơn có trạng thái `CANCELLED` của mọi khách trong ngày” **không thể giả định** chạy nhanh trên bảng này; nên được hỗ trợ bởi bảng đọc khác, chỉ mục phù hợp hoặc tuyến xử lý riêng theo yêu cầu thực tế. Benchmark cần bao gồm từng query shape đang phục vụ, không chỉ query nhanh nhất.

### 3.2. Tránh benchmark sai kiểu truy vấn

Ví dụ không phù hợp khi chỉ có bảng trên:

~~~sql
-- Không có ràng buộc partition key; đây không phải query shape được tối ưu.
SELECT * FROM app_perf.orders_by_customer_month
WHERE status = 'PAID';
~~~

Việc thêm `ALLOW FILTERING` để chạy được trong lab không chứng minh truy vấn phù hợp với production. Nếu ứng dụng thật cần truy vấn theo trạng thái, phải quyết định cách truy cập dữ liệu và đo cách triển khai đó.

Một benchmark dùng duy nhất `SELECT ... WHERE customer_id = ? AND order_month = ?` không thể chứng minh hiệu năng cho truy vấn theo trạng thái, quét toàn bảng, truy vấn nhiều bucket hoặc truy xuất nhiều partition cùng lúc.

### 3.3. Spring Data phải dùng đúng CQL và mapping

Khi truy cập bảng này từ Spring Data Cassandra, một entity có thể chứa khóa tổng hợp:

~~~java
import java.io.Serializable;
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class OrderKey implements Serializable {
    @PrimaryKeyColumn(name = "customer_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID customerId;

    @PrimaryKeyColumn(name = "order_month", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private String orderMonth;

    @PrimaryKeyColumn(name = "created_at", ordinal = 2,
            type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private Instant createdAt;

    @PrimaryKeyColumn(name = "order_id", ordinal = 3,
            type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private UUID orderId;

    // No-arg constructor, getters, setters, equals/hashCode được lược bỏ.
}
~~~

~~~java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_customer_month")
public class OrderRow {
    @PrimaryKey
    private OrderKey key;

    @Column("status")
    private String status;

    @Column("total_cents")
    private Long totalCents;

    // Constructors và accessors được lược bỏ.
}
~~~

Repository dùng truy vấn được xác định tường minh:

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;

public interface OrderRepository extends CassandraRepository<OrderRow, OrderKey> {

    @Query("SELECT customer_id, order_month, created_at, order_id, "
         + "status, total_cents FROM orders_by_customer_month "
         + "WHERE customer_id = ?0 AND order_month = ?1 LIMIT 50")
    List<OrderRow> findRecent(UUID customerId, String orderMonth);
}
~~~

Để chạy ví dụ trên, cần thêm constructor/accessor thích hợp cho entity, cấu hình keyspace `app_perf` ở Spring, và schema đúng với mapping. Query sử dụng tên bảng **không kèm keyspace** vì session Spring đã được cấu hình keyspace tương ứng.

Khi đo, hãy gọi đúng đường đi production: controller/service → repository, `CassandraTemplate` hoặc CQL tùy tính năng. Nếu production cần mapper để chuyển entity sang DTO hoặc đọc nhiều tháng theo logic riêng, phần ấy cũng phải xuất hiện trong bài đo đầu cuối.

## 4. Tạo dữ liệu đại diện: đừng chỉ “insert N dòng”

Hai bộ dữ liệu cùng 20 triệu row có thể cho latency hoàn toàn khác nhau:

- 20 triệu partition, mỗi partition một row: dễ phân tán, ít row phải đọc mỗi partition.
- 1.000 partition, mỗi partition 20.000 row: nhiều row/partition, tập trung truy cập và tiềm ẩn hotspot.
- 19 triệu row hoạt động và 1 triệu tombstone do cập nhật/TTL: chi phí đọc khác dữ liệu mới nạp hoàn toàn.

Do vậy, **số dòng tổng** không đủ mô tả dữ liệu benchmark.

### 4.1. Hồ sơ dữ liệu cần ghi lại

| Đại lượng | Ví dụ giả định | Vì sao cần |
|---|---|---|
| Số partition | Hàng triệu tổ hợp khách/tháng | Ảnh hưởng phân tán token và index |
| Row/partition | p50=8, p95=150, p99=1.200 | Phát hiện đuôi dài partition lớn |
| Kích thước row | p50=250 B, p99=2 KB | Ảnh hưởng I/O, network, serialization |
| Partition nóng | 5% khách tạo 40% lượt đọc | Tạo load skew giống thực tế |
| Phân bố thời gian | 70% đọc tháng hiện tại | Ảnh hưởng working set/cache |
| TTL và tombstone | Có dữ liệu hết hạn và xóa | Ảnh hưởng đọc, compaction, disk |
| Update/overwrite | Một phần hàng được cập nhật nhiều lần | Tạo cấu trúc SSTable khác bulk-load |
| Kích thước dataset trên disk | So với RAM và cache từng node | Phân biệt cache hit với đọc đĩa |

**Các số trong bảng chỉ để minh họa phương pháp**, không phải cấu hình tối ưu mặc định. Cần đo workload thật, sau đó chọn dataset thử có các phân vị và phân bố tương ứng.

### 4.2. Partition key không thể hoàn toàn đồng đều

Một trình tạo tải chọn `customer_id` ngẫu nhiên đều theo UUID sẽ ít tạo hot partition. Trong sản xuất, có thể tồn tại khách hàng doanh nghiệp nhiều đơn, chiến dịch tăng đột biến theo thời gian hoặc những tenant có lưu lượng vượt xa trung bình.

Nên xây dựng bộ phân phối khóa từ histogram thực đã ẩn danh, hoặc mô hình có trọng số:

~~~text
Nhóm A: 5% customer ID, nhận 40% request
Nhóm B: 20% customer ID, nhận 35% request
Nhóm C: 75% customer ID, nhận 25% request
~~~

**Không** chọn 5% ID ngẫu nhiên khác nhau ở *mỗi request* để giả lập “hot keys”: cách đó vẫn làm đều tải theo thời gian. Phải giữ ổn định một tập khách nóng trong từng cửa sổ đo, và nếu sản phẩm có xu hướng thay đổi hot key theo giờ thì mô phỏng sự dịch chuyển ấy.

Tại Cassandra, partition key quyết định token và placement; cùng partition thường bị đọc/ghi tập trung lên các replica sở hữu nó. Tăng tổng số node không nhất thiết cứu một partition bị nóng bất thường.

### 4.3. Tạo kích thước và vòng đời dữ liệu giống thật

Khi tạo fixture:

1. Sinh khóa và số row/partition theo phân bố mục tiêu, bao gồm cả ngoại lệ ở đuôi p99.
2. Dùng phân bố thời gian giống thực tế; nếu là dữ liệu một năm tuổi, không biến toàn bộ thành timestamp mới.
3. Tạo nội dung có kích thước và cấu trúc gần thật; tránh ghi một chuỗi ngắn giống nhau cho mọi row.
4. Mô phỏng tỷ lệ update, delete, TTL nếu production có dùng; thao tác xóa và TTL có thể sinh tombstone.
5. Nạp đủ dữ liệu để kiểm tra working set vượt cache, nếu đây là trường hợp production cần.
6. Để hệ thống đi qua trạng thái compaction hợp lý trước khi kết luận về baseline; đồng thời đo trạng thái có compaction phát sinh nếu nó xảy ra trong giờ cao điểm thực.

Cần phân biệt **benchmark nạp dữ liệu** với **benchmark serving**. Chạy tải đọc ngay sau một lần bulk insert lớn có thể đang đo đợt flush/compaction bất thường, trong khi đọc toàn bộ từ page cache trên bộ dữ liệu bé có thể quá lạc quan. Chọn trạng thái dựa trên câu hỏi, ghi rõ trạng thái vào báo cáo.

### 4.4. Nếu phải thu nhỏ dữ liệu thì thu nhỏ có nguyên tắc

Không thể luôn sao chép nguyên trạng production. Với mô hình nhỏ hơn, cần giải thích biến nào vẫn giữ tương quan:

- **Số row/partition và phân bố partition nóng:** ưu tiên giữ hình dạng phân bố.
- **Tổng working set/RAM và data/disk mỗi node:** cần xét tỷ lệ, không chỉ dung lượng tuyệt đối.
- **Tỷ lệ read/write và kích thước row:** giữ gần yêu cầu sản phẩm.
- **RF và consistency:** nếu giảm xuống RF=1, phải ghi rằng phép thử không còn đại diện cho quorum của cluster RF=3.

Kết quả từ mô hình thu nhỏ hữu ích để so sánh **tương đối** hai query hoặc hai cách mapping dưới cùng điều kiện; thường **không đủ** để ngoại suy throughput tuyệt đối sang cluster lớn.

## 5. Topology phải khớp câu hỏi hiệu năng

### 5.1. Số node, replication và consistency

Ví dụ production có sáu node ở một datacenter, chia qua ba availability zone, với `RF=3`. Ứng dụng dùng `LOCAL_QUORUM` cho đọc và ghi. Trong một DC có RF=3, quorum cần **2 phản hồi replica**.

Một test Cassandra đơn node với `RF=1` có ích cho integration test repository, entity mapping, CQL và logic ứng dụng, nhưng **không tái hiện** được việc coordinator chờ hai replica, giao tiếp qua các zone, phân bố tải giữa node hoặc biến động khi một replica chậm.

| Môi trường | Hữu ích cho | Giới hạn cần nêu |
|---|---|---|
| Cassandra một node/Testcontainers | Correctness của mapping, repository, CQL, paging cơ bản | Không mô phỏng quorum nhiều replica hay network giữa node |
| Ba node, RF=3, một DC | Read/write với quorum và biến động một replica | Chưa hẳn cùng số node, dung lượng, topology và rack như production |
| Cluster tương đương topology thực | Đo capacity, p99, compaction và bottleneck đa node | Cần kiểm soát tài nguyên, dữ liệu và quy trình chạy |
| Cluster nhiều DC | Cross-DC client routing và replication/failure | Phải chỉ rõ local DC, consistency và latency mạng |

**Không** thay `LOCAL_QUORUM` bằng `ONE` chỉ để benchmark có con số đẹp hơn nếu hợp đồng đúng đắn dữ liệu yêu cầu quorum. Kết quả của `ONE` và `LOCAL_QUORUM` phải được ghi là **hai cấu hình thí nghiệm khác nhau**.

### 5.2. CPU, RAM, disk và mạng

Cassandra có đặc trưng nhạy với I/O và compaction. Khi đặt cluster thử, cần ghi:

- Kiểu và giới hạn CPU, RAM, heap/JVM, container limit; tránh để node bị throttling khác production.
- Loại storage, giới hạn IOPS/throughput, latency đĩa và mức sử dụng disk.
- Số node, phân bố rack/AZ/DC, network RTT/bandwidth giữa node và từ ứng dụng đến node.
- Cassandra version, compaction strategy, compression, TTL, cache, cấu hình GC và schema.
- Java Driver/Spring Boot/Spring Data versions, resource limit của ứng dụng, pool connections, timeout và retry policy.

Hai hệ thống có cùng 3 node, cùng RF=3 nhưng một bên đặt cả ứng dụng và Cassandra trên cùng một máy, bên kia gọi qua mạng thực giữa AZ sẽ có p99 khác nhau.

### 5.3. Local datacenter của Java Driver

Java Driver 4.x chọn node dựa trên load balancing và local datacenter. Khi chạy benchmark ứng dụng Spring Boot 3.x, cấu hình nên phản ánh chính xác nơi client hoạt động:

~~~yaml
spring:
  cassandra:
    contact-points: ${CASSANDRA_CONTACT_POINTS}
    port: ${CASSANDRA_PORT:9042}
    local-datacenter: ${CASSANDRA_LOCAL_DC:dc1}
    keyspace-name: app_perf
    request:
      timeout: 2s
~~~

Đây là ví dụ với **Spring Boot 3.x**; tham số và tiền tố cấu hình cần khớp phiên bản thực tế. Trong các dự án Spring Boot 2.x, một số thuộc tính Cassandra thuộc `spring.data.cassandra.*`. Giá trị `2s` chỉ là timeout mẫu, cần chọn theo SLO và hành vi retry thực tế.

Không benchmark từ một client kết nối xuyên vùng địa lý nếu ứng dụng production đặt cùng datacenter với Cassandra, trừ khi bạn chủ đích đo đường gọi xuyên vùng. Hãy xác định rõ benchmark đang đo **client-to-cluster** hay **end-to-end HTTP**.

## 6. Phân bố tải: chọn đúng công việc và cách đưa request vào

### 6.1. Thiết kế workload mix

Ví dụ giả định của một chức năng đơn hàng:

| Loại thao tác | Tỷ lệ trong tổng request | Mẫu dữ liệu/truy vấn |
|---|---:|---|
| Đọc 50 đơn gần nhất trong tháng | 65% | Partition khách/tháng, phần lớn tháng hiện tại |
| Đọc đơn lịch sử theo tháng | 20% | Partition tháng cũ, cache hit có thể thấp |
| Ghi đơn mới | 10% | Insert với partition key đúng |
| Cập nhật trạng thái đơn | 5% | Update cùng khóa đầy đủ |

Tổng cộng **85% đọc, 15% ghi**. Đây là ví dụ, không phải tỷ lệ chuẩn của Cassandra. Với hệ thống có batch, LWT, counters, truy vấn nhiều page hoặc ghi TTL, các thao tác đó phải có tỷ trọng riêng vì chi phí và ngữ nghĩa rất khác.

Trong 85% đọc, cần ghi tiếp:

- Bao nhiêu request truy xuất dữ liệu ở **tháng hiện tại** và bao nhiêu ở bucket cũ?
- Bao nhiêu request trả 0 row, 1 row, 50 row hoặc nhiều page?
- Bao nhiêu request rơi vào tập **hot partition**?
- Có truy vấn đọc theo một khóa, nhiều khóa, hay đọc qua nhiều tháng không?
- API có thực hiện nhiều lời gọi repository trong một request không?

Không đủ nếu chỉ nói “85% SELECT”: hai query đọc có thể chênh lệch chi phí hàng chục lần.

### 6.2. Arrival rate, concurrency và throughput thực đạt

**Offered load** là số yêu cầu trình phát tải **cố gắng gửi vào hệ thống**, ví dụ 1.500 request/giây. **Achieved throughput** là số yêu cầu hệ thống thực sự hoàn tất mỗi giây, có thể thấp hơn khi queue tăng, lỗi hoặc timeout xuất hiện.

Với hệ thống ở trạng thái ổn định, định luật Little cho trung bình:

\[
L = \lambda W
\]

Trong đó `L` là số request đồng thời trung bình đang ở hệ thống, `\lambda` là throughput hoàn tất và `W` là thời gian phản hồi trung bình (đơn vị giây). Ví dụ, 1.500 request/giây với trung bình 40 ms tương ứng khoảng 60 request đang xử lý. Đây chỉ là **trung bình** ở trạng thái ổn định; p99, burst và hàng đợi có thể làm mức đồng thời cao hơn nhiều.

Hai kiểu tải cần phân biệt:

- **Closed-loop:** một virtual user gửi request, đợi phản hồi rồi mới gửi tiếp. Khi hệ thống chậm, tốc độ phát tải tự giảm. Dễ tạo phép đo đẹp giả tạo tại điểm bão hòa.
- **Open-loop / arrival-rate controlled:** yêu cầu đến theo tốc độ dự kiến độc lập với response trước. Phù hợp để quan sát queue và độ trễ khi nhu cầu bên ngoài vẫn tăng.

Khi chọn load generator, cần có khả năng ghi **độ trễ tính từ thời điểm request dự kiến đến**, tránh **coordinated omission**: lúc server nghẽn, công cụ chỉ ghi các request thật sự gửi sau khi được giải phóng và bỏ lỡ khoảng chờ mà người dùng đáng lẽ phải chịu.

### 6.3. Burst, chu kỳ nóng và tải nền

Chỉ chạy mức tải đều 10 phút không thể tái hiện:

- Đột biến ngay sau một chiến dịch, khi cùng nhiều người truy cập tập khách/tenant nóng.
- Job nền ghi hoặc xóa dữ liệu, tạo flush và compaction.
- Trang đầu danh sách nhanh nhưng các page tiếp theo tải nhiều.
- Một node chậm khiến read/write ở quorum tăng tail latency.
- Tải tăng từng bước, đạt điểm bão hòa rồi phục hồi.

Hãy mô phỏng theo cửa sổ thời gian thực tế: giờ thấp điểm, tải trung bình, cao điểm, burst ngắn và giai đoạn hồi phục. Cần giữ nguyên phân bố khóa nóng trong cửa sổ đo và thay đổi có chủ đích giữa các cửa sổ.

## 7. Phép đo ở tầng Spring Data Cassandra

### 7.1. Đo đường đi nào?

Một chức năng đọc thường có nhiều phần:

~~~mermaid
flowchart LR
    A["HTTP / job caller"] --> B["Validation và nghiệp vụ"]
    B --> C["Spring Data Repository / CassandraTemplate"]
    C --> D["Java Driver: queue, pool, network"]
    D --> E["Cassandra coordinator và replica"]
    E --> D
    D --> C
    C --> B
    B --> F["DTO / serialization / response"]
~~~

Đo riêng `CqlSession.execute(...)` không bao gồm mọi chi phí Spring mapping hoặc HTTP. Ngược lại, một p99 HTTP xấu không mặc nhiên có nghĩa Cassandra chậm. Nên thu cả **latency đầu cuối**, **thời gian repository/service** và **metric Driver/Cassandra** trong cùng cửa sổ và bằng cùng trace/request identifier nếu có.

### 7.2. Ví dụ đo thời gian service bằng Micrometer

Trong ứng dụng có Spring Boot Actuator và Micrometer, một cách đơn giản là tạo timer với tag có cardinality thấp:

~~~java
import java.util.List;
import java.util.UUID;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class OrderReadService {
    private final OrderRepository repository;
    private final MeterRegistry registry;

    public OrderReadService(OrderRepository repository, MeterRegistry registry) {
        this.repository = repository;
        this.registry = registry;
    }

    public List<OrderRow> recent(UUID customerId, String orderMonth) {
        Timer.Sample sample = Timer.start(registry);
        boolean success = false;
        try {
            List<OrderRow> result = repository.findRecent(customerId, orderMonth);
            success = true;
            return result;
        } finally {
            sample.stop(registry.timer(
                    "orders.read.duration",
                    "operation", "findRecent",
                    "outcome", success ? "success" : "error"));
        }
    }
}
~~~

Timer sẽ ghi cả thời gian đến khi lời gọi repository đồng bộ trả kết quả hoặc ném ngoại lệ. Có thể xuất histogram để lấy p50/p95/p99 theo backend giám sát phù hợp. Nếu sử dụng **reactive repository**, phép đo phải bao quanh thực thi publisher khi subscribe/hoàn tất, không chỉ thời gian tạo `Mono`/`Flux`.

**Không** dùng `customerId`, `orderId`, CQL thô hoặc exception message làm metric tag: cardinality sẽ rất cao, tăng chi phí và làm hệ giám sát quá tải. Nên dùng tag ổn định như `operation=findRecent`, `outcome=success/error` và loại truy vấn đã được phân nhóm.

### 7.3. Chạy đúng phiên bản ứng dụng và cấu hình Driver

Khi so sánh hai lần đo, lưu lại:

- Phiên bản Spring Boot, Spring Data Cassandra, Java Driver, Java runtime và build ứng dụng.
- Contact points, local DC, consistency, request timeout, page size, retry/speculative execution policy.
- Cấu hình pool/connection, giới hạn concurrency, executor/reactive scheduler, thread pool và CPU của client.
- Repository method và CQL thực tế, có chuẩn bị statement hay không, cách mapping entity sang DTO.
- Số instance ứng dụng và vị trí đặt load generator.

Driver có thể tự retry một số lỗi trước khi Spring nhận exception. Nếu application còn retry bên ngoài, **số CQL thực gửi vào Cassandra** có thể nhiều hơn số request đến API. Benchmark chỉ đếm request HTTP mà không đo retry sẽ bỏ sót nguồn gây khuếch đại tải.

### 7.4. Paging và số row trả về

Truy vấn có `LIMIT 50` trong ví dụ chỉ trả tối đa 50 row, nên không đo được một workload thật sự lấy 500 row qua nhiều trang Driver. Nếu ứng dụng có chức năng đó, hãy đo riêng:

~~~java
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

int countOrders(CqlSession session, UUID customerId, String month) {
    SimpleStatement statement = SimpleStatement.builder(
            "SELECT order_id FROM app_perf.orders_by_customer_month "
                    + "WHERE customer_id = ? AND order_month = ?")
            .addPositionalValues(customerId, month)
            .setPageSize(100)
            .build();

    ResultSet result = session.execute(statement);
    int count = 0;
    for (Row ignored : result) {
        count++; // Vòng lặp có thể kích hoạt fetch các page tiếp theo.
    }
    return count;
}
~~~

Đoạn Java ở trên minh họa **Driver CQL paging** và được dùng để phân biệt request một page với quét toàn bộ các page; nó **không** thay thế đường đo Spring Data ở trên. Driver có thể tự lấy trang kế tiếp khi duyệt toàn bộ kết quả, làm tăng số round-trip. Nếu API chỉ trả một trang mỗi request, benchmark cần đo đúng một trang và quá trình truyền/nhận paging state, không tự động đọc hết mọi row.

Cần ghi rõ: kích thước page, số row thực trả, tỷ lệ query đi tới page 2/3/..., bytes trên mạng, thời gian page đầu so với thời gian toàn bộ. Giới hạn page size là điều kiện thực nghiệm, không phải “vặn càng lớn càng nhanh”.

## 8. Thu thập metric ở cả ba tầng

Một số đơn lẻ như throughput trung bình không mô tả đủ trạng thái. Một lần chạy nên thu được các nhóm sau:

| Tầng | Metric cần theo dõi | Câu hỏi giải đáp |
|---|---|---|
| Load generator/API | Offered RPS, achieved RPS, số request hoàn tất/thất bại, latency p50/p95/p99, queue, timeout | Người dùng thấy gì khi tăng tải? |
| Spring/Java Driver | Thời gian repository/CQL, số request đang bay, connection pool, in-flight, retry, speculative execution, node lỗi | Độ trễ phát sinh trước mạng, trong Driver hay do retry? |
| Cassandra node | CPU, heap/GC, disk latency/IOPS, read/write latency, pending tasks, compaction, dropped messages, timeout | Node nào đang bão hòa và vì sao? |
| Dữ liệu/partition | Kích thước partition, row/partition, tombstone, cache hit, SSTable/read amplification | Query nào tạo nhiều công việc nội bộ? |
| Network/topology | RTT, băng thông, retransmission, traffic giữa node/DC, mất node | p99 có liên quan đường truyền hoặc quorum không? |

Các chỉ số node có thể được thu qua hệ thống metrics/JMX và công cụ vận hành Cassandra; `nodetool tablestats`, `tablehistograms`, `tpstats` và `compactionstats` là những điểm kiểm tra hữu ích tùy phiên bản. Không đọc kết quả của một node rồi suy ra toàn cluster bình thường: bottleneck thường tập trung ở **một vài node/partition**.

### 8.1. Vì sao p99 quan trọng hơn trung bình?

Giả sử hai ứng dụng đều có trung bình 40 ms:

- Trường hợp A: phần lớn request nằm trong 25–70 ms.
- Trường hợp B: đa số request chỉ mất 10 ms nhưng 1% request mất trên 1 giây.

Hai trải nghiệm rất khác nhau. Người dùng chịu đựng các request chậm, và API có deadline có thể timeout trước khi request hoàn tất.

Nên báo cáo tối thiểu: p50, p95, p99, throughput thực đạt, tỷ lệ lỗi/timeout và khoảng đo. Phân loại theo query shape và read/write; **p99 gộp** có thể che giấu một truy vấn hiếm nhưng cực chậm. Khi so sánh giữa nhiều cửa sổ, nên tổng hợp từ histogram phù hợp thay vì lấy trung bình số học của các giá trị p99 riêng lẻ.

### 8.2. Xem lỗi cùng với latency

Một hệ thống có thể báo p99 tốt hơn vì những request chậm nhất đã timeout và **bị loại khỏi tập “thành công”**. Do đó:

- Báo cáo latency của request thành công **cùng** tỷ lệ lỗi, timeout và queue.
- Nếu có thể, đo latency của toàn bộ request kể cả lỗi và phân loại outcome.
- Phân biệt timeout do client, timeout từ coordinator, unavailable và lỗi truy vấn.
- Ghi cả số request phát ra ban đầu lẫn số CQL attempt do retry/speculative execution.

Không tự kết luận “nhanh hơn” khi p99 giảm nhưng tỷ lệ lỗi tăng mạnh.

### 8.3. Điểm bão hòa và capacity headroom

Tăng offered load theo bước: 500 → 750 → 1.000 → 1.250 → 1.500 request/giây (con số **minh họa**). Ở mỗi bước, quan sát độ trễ, backlog, throughput đạt và lỗi:

~~~text
RPS đề nghị tăng ────────────────────────────►
Throughput đạt  tăng ─────── gần trần ──────►
Queue/p99        thấp ─────── tăng vọt ─────►
Errors           thấp ─────── tăng dần ─────►
                            điểm gãy
~~~

**Capacity dùng được** thường nằm trước điểm gãy, có thêm dư địa cho burst, compaction, GC, mạng và mất replica. Không lấy throughput cực đại tại lúc lỗi/timeouts tăng làm mục tiêu vận hành lâu dài.

## 9. Quy trình benchmark có thể tái lập

### Bước 1 — Viết hợp đồng và câu hỏi đo

Xác định SLO/SLI, loại thao tác, consistency, payload, số row trả về, yêu cầu về dữ liệu và lỗi. Ví dụ: `p99 < 200 ms` cho 85% đọc và 15% ghi ở tải thường, không quá 0,1% request lỗi. **Đây là mục tiêu giả định**, cần điều chỉnh cho hệ thống của bạn.

### Bước 2 — Chốt schema, topology và version

Lưu DDL, bản mapping Spring Data, CQL thực tế, RF, số node, DC/rack, consistency, phần cứng, vị trí client, runtime/Driver version và retry policy. Không đổi schema hoặc request timeout giữa chừng mà vẫn gọi hai lần đo là cùng một điều kiện.

### Bước 3 — Nạp dữ liệu có phân bố xác định

Tạo dữ liệu cho số lượng partition, phân bố row/partition, hot key và độ tuổi cần thiết. Nếu dùng seed để sinh dữ liệu, lưu seed; tạo cùng dataset khi so sánh hai phương án.

### Bước 4 — Kiểm tra correctness và readiness

Đợi Cassandra sẵn sàng trả CQL, xác nhận schema đã có, các replica phù hợp consistency có thể phục vụ và phép đọc/ghi round-trip qua Spring Data thành công. Không đưa lỗi setup vào báo cáo hiệu năng như thể ứng dụng đã xử lý request thật.

### Bước 5 — Warm up có kiểm soát

Khởi động đủ lâu để JVM JIT, Driver connection/session, cache và hệ thống ổn định tới mức phù hợp. Ghi rõ kết quả **cold** và **warm** nếu cả hai quan trọng. Không bỏ qua compaction/flush còn đang diễn ra nếu chúng là phần tự nhiên của tải production.

### Bước 6 — Chạy pha tải và thu metrics

Chạy baseline ở mức tải bình thường, sau đó tăng từng bước và thử burst. Duy trì mỗi pha đủ lâu để quan sát tail latency, compaction, GC và working set; đồng bộ timestamp giữa các hệ thống đo.

### Bước 7 — Lặp lại và kiểm soát biến

Lặp nhiều lần trong điều kiện tương đương. Mỗi thí nghiệm chỉ nên chủ đích thay một nhóm tham số: ví dụ page size 100 so với 500, hoặc phân bố đều so với skew thực. Nếu thay đồng thời page size, RF, dataset và số thread, khó biết yếu tố nào tạo khác biệt.

### Bước 8 — Báo cáo kết quả cùng điều kiện

Một báo cáo đủ để người khác tái lập nên có:

~~~text
Scenario: recent-order reads + writes, 85/15
Schema/version: orders_by_customer_month, DDL hash + app build id
Dataset: number of partitions, rows/partition distribution, hot-key share, TTL
Topology: node count, DC/rack/AZ, RF, CL, CPU/RAM/disk/network
Client: instances, Driver version, timeout, retry, page size
Load: offered RPS, pattern, duration, warmup, seed
Result: achieved RPS, p50/p95/p99, errors, timeouts, retries
Server: max CPU, disk latency, GC, compaction, pending tasks, hottest nodes
Conclusion: supported load and constraints; remaining uncertainty
~~~

Tránh báo cáo chỉ một biểu đồ throughput mà không cho biết dataset, consistency, tỷ lệ request và mức lỗi.

## 10. Ví dụ đọc kết quả: “nhanh hơn” có thật sự tốt hơn?

Bảng sau là **số liệu giả lập để luyện phân tích**, không phải kết quả đo Cassandra:

| Kịch bản | Offered RPS | Achieved RPS | p99 đọc thành công | Lỗi/timeout | Tín hiệu |
|---|---:|---:|---:|---:|---|
| A — workload đều | 1.000 | 997 | 85 ms | 0,1% | Còn dư địa |
| B — cùng schema, hot keys thực tế | 1.000 | 962 | 280 ms | 2,3% | Hot partition hoặc replica quá tải |
| C — workload skew, thêm burst | 1.500 | 1.080 | 690 ms | 8,0% | Backlog/timeout tăng; đạt điểm gãy |
| D — đọc đều, hạ CL thành ONE | 1.000 | 999 | 52 ms | 0,0% | **Khác consistency**, không so trực tiếp với A |

**Cách phân tích:**

1. A và B khác nhau ở **phân bố khóa**; dù cùng offered RPS, B có p99 cao hơn nhiều và throughput đạt thấp hơn. Cần kiểm tra node/partition nóng, phân bố dữ liệu và queue, không vội kết luận “Cassandra quá chậm”.
2. C tăng offered load nhưng achieved throughput tăng ít hơn; p99 và error tăng mạnh. Hệ thống đã tiến gần hoặc vượt capacity phù hợp SLO.
3. D không phải bản tối ưu tương đương A: hạ consistency thay đổi bảo đảm nhất quán. Chỉ dùng nếu bài toán chấp nhận thay đổi đó và ghi rõ đánh đổi.
4. Chưa thể kết luận nguyên nhân chính của B/C chỉ từ bảng. Phải đối chiếu metrics Driver, CPU/disk/node, compaction, GC và topology.

### 10.1. Ma trận thí nghiệm nên thử

| Thí nghiệm | Giữ cố định | Thay đổi | Câu hỏi |
|---|---|---|---|
| Key skew | Schema, topology, offered RPS, mix | Uniform → skew thực | Hot partition ảnh hưởng p99 bao nhiêu? |
| Page size | Query, dữ liệu, concurrency | Page 100 → 500 | Page size ảnh hưởng RTT, bộ nhớ và p99 ra sao? |
| Dataset size | Query, tải, topology | Working set nhỏ → lớn hơn RAM | Cache hit đang che chi phí I/O không? |
| Compaction | Data, load, topology | Quiet → compaction nền | Tail latency tăng thế nào khi có ghi dài hạn? |
| Consistency | Data, query, topology | `LOCAL_ONE` → `LOCAL_QUORUM` | Chi phí độ trễ của bảo đảm nhất quán mong muốn? |
| Failure | Cluster và workload | Một replica chậm/down | SLO và retry ứng xử thế nào? |

Với các thử nghiệm làm node chậm/down, nên dùng **môi trường thử riêng**, có kiểm soát. Cần phân biệt lỗi do test injection và lỗi tự nhiên của workload.

## 11. Từ kết quả đo đến quyết định tối ưu

### 11.1. p99 tăng cùng kích thước partition

Giả thuyết: một số partition có quá nhiều row hoặc query quét vùng clustering quá rộng. Kiểm tra histogram kích thước/row per partition, CQL query shape, số row trả về, tombstone và latency theo key nhóm.

Hướng xem xét: thay đổi bucket thời gian, giới hạn phạm vi đọc, tạo bảng theo truy vấn, phân tách tenant lớn nếu hợp đồng dữ liệu cho phép. Không thêm bucket chỉ vì thấy p99 xấu: partition quá nhỏ cũng làm tăng số query/cross-partition ở tầng service; cần đo lại chi phí đầu cuối.

### 11.2. Throughput không tăng khi thêm thread tải

Có thể bottleneck nằm ở client (CPU, pool, serialization) hoặc Cassandra (CPU/IO, queue, coordinator). Xem offered/achieved RPS, in-flight Driver, pending tasks, CPU hai phía và network. Tăng số worker khi Cassandra đã bão hòa chỉ tạo hàng đợi dài hơn.

### 11.3. Lỗi write timeout xuất hiện khi tăng tải

Kiểm tra CL, số replica cần xác nhận, tình trạng compaction, disk, network, pending writes và retry. **Write timeout không chứng minh mutation hoàn toàn chưa được ghi.** Một retry có thể làm tăng tải và có tác dụng phụ nếu thao tác không idempotent.

### 11.4. Benchmark ấn tượng nhưng production vẫn chậm

Các nguyên nhân điển hình: workload benchmark bỏ qua hot keys, row nhỏ hơn thật, test không có TTL/tombstone, không đo page tiếp theo, cluster gần client hơn, dùng RF/CL thấp hơn, hoặc chỉ ghi latency thành công khi request chậm đã timeout.

Tốt nhất là lập bảng sai khác giữa **môi trường đo** và **môi trường mục tiêu**, sắp theo mức ảnh hưởng dự kiến; sau đó bổ sung thí nghiệm có chủ đích.

## 12. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Chỉ benchmark một CQL lấy theo key ngẫu nhiên đều | Không thấy hot partition và query khác | Mô phỏng query mix và phân bố key thực |
| Đếm 10 triệu row rồi kết luận dataset đại diện | Che mất p99 row/partition và kích thước dữ liệu | Lưu histogram row/partition, row size, TTL/tombstone |
| Dùng Cassandra một node để công bố capacity cluster RF=3 | Không đo quorum, topology và network | Benchmark với cluster đại diện khi quyết định capacity |
| Giữ cố định thread và chỉ nhìn RPS hoàn tất | Load tự giảm khi server chậm | Ghi offered RPS, queue, open-loop pattern và coordinated omission |
| Lấy average latency, bỏ p99 và errors | Tail timeout bị che khuất | Thu histogram, p50/p95/p99 và tỷ lệ lỗi |
| Thay nhiều tham số cùng lúc | Không biết nguyên nhân tăng/giảm | Cố định baseline, thay từng yếu tố |
| Benchmark ngay sau khi nạp toàn dữ liệu mà không ghi trạng thái | Kết quả bị lệch bởi cache/compaction | Tách cold/warm, ghi trạng thái hệ thống |
| Dùng `ALLOW FILTERING` làm truy vấn thuận tiện | Benchmark một thiết kế không phản ánh đường đọc tốt | Tạo bảng/index theo query shape cần đo |
| Tăng retry để bù node nghẽn | Khuếch đại offered load vào Cassandra | Phân tích lỗi, giới hạn retry và xét idempotence |
| Dùng raw Driver benchmark thay toàn bộ Spring API | Bỏ mapping, business logic, DTO và HTTP | Đo cả đường đầu cuối và tầng CQL |

## 13. Bài tập áp dụng

**Bài tập A — Chọn dataset.** Hai bộ dữ liệu đều có 5 triệu đơn hàng. Bộ 1 có 5 triệu partition, mỗi partition một đơn; bộ 2 có 50.000 partition, kích thước không đều và một nhóm partition rất nóng. Hệ thống production giống bộ 2. Có nên dùng kết quả bộ 1 để cam kết p99 production?

**Gợi ý:** Không. Tổng số hàng bằng nhau không bảo toàn phân bố truy cập/partition. Phải đo hoặc mô phỏng histogram và hot keys tương ứng bộ 2.

**Bài tập B — Chọn topology.** Production có RF=3 và `LOCAL_QUORUM`, nhưng test chỉ chạy một Cassandra Testcontainers với RF=1. Những gì kết quả test có thể và không thể chứng minh?

**Gợi ý:** Hữu ích cho mapping, repository, CQL và latency đơn node trong lab; không chứng minh capacity/quorum/availability hay p99 qua nhiều replica giống production.

**Bài tập C — Đọc throughput.** Tool gửi 2.000 request/giây, server hoàn tất 1.300 request/giây; p99 là 700 ms và lỗi tăng. Có thể công bố “hệ thống đạt 2.000 RPS” không?

**Gợi ý:** Không. `2.000` là offered load; đạt được `1.300`, còn có queue/lỗi. Phải xét SLO, tỷ lệ thành công và các metric liên quan.

**Bài tập D — Paging.** API thật cho phép lấy tối đa 500 row theo các trang 50 row. Benchmark luôn `LIMIT 1` rồi kết luận request p99 thấp. Có điểm mù nào?

**Gợi ý:** Chưa đo số row thực, trang sau, paging state, bytes, mapping và số round-trip. Phải benchmark các kiểu page request đúng tỷ lệ sử dụng.

**Bài tập E — Chẩn đoán hot partition.** Khi tăng tải từ 900 lên 1.200 RPS, một node CPU 95% và p99 đọc tăng mạnh, các node khác chỉ 40%. Bạn cần xem dữ liệu gì tiếp theo?

**Gợi ý:** Kiểm tra phân bố token/replica, hot partition, query per key, compaction/GC, disk I/O, node coordinator, retry và phân bố load balancing trước khi tăng node hoặc timeout.

## 14. Checklist trước khi kết luận benchmark

- [ ] Câu hỏi đo và SLO được viết cụ thể theo thao tác.
- [ ] Schema, entity mapping, CQL và thiết kế partition đúng production.
- [ ] Dataset có phân bố row/partition, hot key, row size, TTL/tombstone đại diện.
- [ ] Topology, RF, DC/rack, consistency, disk/network và Java Driver được ghi rõ.
- [ ] Workload mix, arrival rate, concurrency, burst và paging có tỷ lệ phù hợp.
- [ ] Có số liệu **offered** và **achieved** throughput.
- [ ] Có latency p50/p95/p99, lỗi/timeout và retry; không bỏ qua request thất bại.
- [ ] Có metrics Spring/Driver và Cassandra node trong cùng cửa sổ đo.
- [ ] Đã kiểm soát warmup, compaction, fixture, seed và điều kiện lặp lại.
- [ ] Kết luận nêu rõ giới hạn ngoại suy và khoảng cách giữa lab với production.

## 15. Tổng kết

Đối với **Spring Data Cassandra**, bài đo hiệu năng chỉ hữu ích khi **mô hình dữ liệu, topology và phân bố tải** phản ánh đủ sát chức năng cần đánh giá. Schema xác định cách đọc partition; topology và replication/consistency xác định số replica và đường mạng tham gia; workload mix, hot keys, page size và burst xác định hệ thống bị đặt dưới áp lực nào.

Hãy đo cùng lúc latency từ ứng dụng, hành vi Driver và metrics Cassandra; báo cáo p99 cùng throughput đạt, lỗi và retry. Chạy các thí nghiệm có kiểm soát, quan sát điểm bão hòa và ghi điều kiện tái lập. Một con số benchmark cao đơn lẻ không thay thế được bằng chứng hệ thống **đạt SLO trên dữ liệu và tải đại diện**.

## Tài liệu tham khảo

- [Apache Cassandra Documentation — Data modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/intro.html)
- [Apache Cassandra Documentation — CQL](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/index.html)
- [Spring Data Cassandra Reference](https://docs.spring.io/spring-data/cassandra/reference/)
- [Spring Boot Actuator — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [DataStax Java Driver 4.x — Metrics](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/metrics/index.html)
