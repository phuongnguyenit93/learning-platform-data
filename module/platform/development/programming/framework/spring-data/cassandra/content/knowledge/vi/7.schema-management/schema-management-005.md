# Giới hạn của tạo lược đồ tự động khi bảng đã tồn tại

Trong **Spring Data Cassandra**, entity mapping giúp ứng dụng Java đọc và ghi dữ liệu Apache Cassandra qua repository, `CassandraTemplate` hoặc truy vấn CQL. Spring Boot có thể khởi tạo một phần lược đồ từ metadata của entity khi ứng dụng chạy. Điều này hữu ích ở môi trường học tập và thử nghiệm, nhưng dễ gây hiểu nhầm: **tạo bảng tự động không phải là cơ chế migration đáng tin cậy cho một bảng đã tồn tại**.

Bài thuộc chương **Quản lý lược đồ** của module **SPRING_DATA_CASSANDRA**. Ta sẽ xét chính xác điều gì xảy ra khi entity được sửa nhưng bảng Cassandra vẫn giữ cấu trúc cũ, tại sao partition key và clustering columns cần được quản lý có kế hoạch, và cách triển khai thay đổi schema mà vẫn bảo vệ dữ liệu cũng như truy vấn đang chạy.

## 1. Auto schema creation giải quyết bài toán nào?

Spring Data Cassandra có cơ chế **schema action** để kiểm soát ứng dụng có thực hiện thao tác quản lý lược đồ dựa trên metadata của các mapped entity hay không. Trong ứng dụng Spring Boot 3.x, cấu hình minh họa:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: commerce_ks
    schema-action: none
~~~

Tên datacenter, endpoint và keyspace phải khớp với cluster thực tế. Phần lớn ứng dụng production nên chủ động quản lý schema riêng, vì thế `schema-action: none` là lựa chọn khởi đầu phù hợp khi bảng đã được tạo bởi quy trình triển khai.

Các chế độ dưới đây thường gặp trong các phiên bản Spring Data Cassandra hỗ trợ `SchemaAction`; tên và hành vi chính xác cần được kiểm tra theo phiên bản Spring Boot/Spring Data thực tế:

| Schema action | Ý định chính | Điều cần cảnh giác |
| --- | --- | --- |
| `NONE` | Không yêu cầu Spring Data tạo/sửa schema khi khởi động | Bảng, keyspace và kiểu dữ liệu cần được chuẩn bị trước |
| `CREATE_IF_NOT_EXISTS` | Tạo các đối tượng schema cần thiết nếu chưa có | **Không đồng bộ mọi thay đổi** của entity vào bảng đã tồn tại |
| `RECREATE` | Tạo lại schema mà framework quản lý | Có thể làm mất dữ liệu, không dùng tùy tiện trên môi trường chứa dữ liệu thật |
| `RECREATE_DROP_UNUSED` | Tạo lại và xử lý cả những đối tượng không còn được mapping quản lý, tùy phiên bản | Nguy cơ phá hủy dữ liệu/đối tượng không được kỳ vọng |

**Điểm cốt lõi:** các chế độ có yếu tố **recreate/drop** không phải cách “tự động sửa bảng an toàn”. Chúng có thể phá hủy dữ liệu. Với bảng sản xuất đã tồn tại, cần migration CQL được thiết kế và chạy có kiểm soát, thay vì cho mọi instance ứng dụng tự tái tạo lược đồ.

## 2. Vì sao `CREATE TABLE IF NOT EXISTS` không phải migration?

Giả sử ban đầu hệ thống đọc đơn hàng **theo tenant và ngày**, từ mới tới cũ:

~~~sql
CREATE KEYSPACE IF NOT EXISTS commerce_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
};

CREATE TABLE IF NOT EXISTS commerce_ks.orders_by_tenant_day (
    tenant_id  uuid,
    order_day  date,
    placed_at  timestamp,
    order_id   uuid,
    amount     decimal,
    status     text,
    PRIMARY KEY ((tenant_id, order_day), placed_at, order_id)
) WITH CLUSTERING ORDER BY (placed_at DESC, order_id DESC);
~~~

Đây là **schema V1**. Lệnh `CREATE TABLE IF NOT EXISTS` chỉ giúp tránh lỗi “bảng đã tồn tại”. Nếu bảng thực tế đã có, Cassandra **không so sánh toàn bộ định nghĩa hiện tại** với câu `CREATE TABLE` mới rồi tự động áp dụng phần chênh lệch.

Ví dụ nhóm phát triển thay entity V2 để thêm thuộc tính `channel`. Họ có thể nghĩ rằng khởi động lại ứng dụng ở chế độ `CREATE_IF_NOT_EXISTS` sẽ làm Cassandra thêm cột tương ứng. Tuy nhiên **bảng V1 đã tồn tại** nên không thể dựa vào thao tác tạo bảng để nâng nó thành V2.

~~~text
Entity V2 (Java)                        Bảng V1 (Cassandra)
----------------------------------      -------------------------------
tenantId        -> tenant_id            tenant_id
orderDay        -> order_day            order_day
placedAt        -> placed_at            placed_at
orderId         -> order_id             order_id
amount          -> amount               amount
status          -> status               status
channel         -> channel       X      không có cột channel

                     MAPPING LỆCH SCHEMA
~~~

Tùy thao tác và cách phát sinh CQL, lỗi có thể chỉ xuất hiện khi query hoặc ghi thực sự dùng cột mới, chẳng hạn thông báo kiểu **undefined/unknown column** từ Cassandra. Sự kiện ứng dụng khởi động thành công **không chứng minh** mọi entity và bảng đã tương thích.

## 3. Hai lớp schema cần được phân biệt

| Lớp | Ví dụ | Ai quyết định? |
| --- | --- | --- |
| **Entity mapping Java** | `@Table`, `@PrimaryKeyClass`, `@PrimaryKeyColumn`, `@Column` | Mã nguồn Spring Data Cassandra |
| **Schema CQL thực tế** | `CREATE TABLE`, partition/clustering key, kiểu cột, index, table options | Cassandra cluster |

Entity mapping mô tả cách Spring Data ánh xạ dữ liệu. Cassandra thực thi truy vấn dựa trên **schema hiện đang được cluster lưu và đồng thuận**, không dựa vào source code Java của một instance.

Điều này đặc biệt quan trọng với hệ thống phân tán:

- Nhiều instance có thể chạy **hai phiên bản code** trong một đợt rolling deployment.
- CQL schema thay đổi cần được các node nhận biết; **schema agreement** không phải lúc nào cũng tức thì.
- DDL thường ảnh hưởng toàn bộ bảng/keyspace; nó không chỉ tác động tới một repository của ứng dụng.
- Thay đổi tên hoặc kiểu khóa có thể khiến truy vấn không còn định tuyến đúng partition, dù entity vẫn compile thành công.

Vì vậy, so sánh Java class trước/sau **chưa đủ**. Cần xem CQL schema thực tế, dữ liệu hiện có, các consumer đang dùng, và kế hoạch triển khai.

## 4. Ví dụ entity V1 và V2 không đồng nghĩa bảng được cập nhật

Entity Java rút gọn tương ứng bảng V1:

~~~java
@PrimaryKeyClass
public class OrderKey implements Serializable {

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
                      type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "order_day", ordinal = 1,
                      type = PrimaryKeyType.PARTITIONED)
    private LocalDate orderDay;

    @PrimaryKeyColumn(name = "placed_at", ordinal = 2,
                      type = PrimaryKeyType.CLUSTERED,
                      ordering = Ordering.DESCENDING)
    private Instant placedAt;

    @PrimaryKeyColumn(name = "order_id", ordinal = 3,
                      type = PrimaryKeyType.CLUSTERED,
                      ordering = Ordering.DESCENDING)
    private UUID orderId;

    // Constructor, getter/setter, equals và hashCode theo mapping thực tế.
}

@Table("orders_by_tenant_day")
public class OrderRow {

    @PrimaryKey
    private OrderKey key;

    @Column("amount")
    private BigDecimal amount;

    @Column("status")
    private String status;
}
~~~

Ở V2, nhóm phát triển bổ sung:

~~~java
@Column("channel")
private String channel;
~~~

Đây là thay đổi **metadata ở phía Java**. Để lưu cột mới trong Cassandra, một migration schema tường minh có thể là:

~~~sql
ALTER TABLE commerce_ks.orders_by_tenant_day
ADD channel text;
~~~

Sau khi schema được áp dụng và các node đạt agreement, code mới có thể đọc/ghi `channel`. Những hàng cũ chưa có giá trị cột này thường được mapping thành `null`; nếu nghiệp vụ yêu cầu giá trị không rỗng, cần **backfill có giới hạn** hoặc dùng giá trị mặc định ở lớp ứng dụng. Cassandra không tự gán giá trị cho mọi hàng cũ chỉ vì field Java mới được thêm.

**Đừng dựa vào việc khởi động lại N instance** để chạy lặp DDL. Migration được điều phối rõ ràng giúp tránh cuộc đua giữa các phiên bản code và dễ theo dõi lỗi hơn.

## 5. Đổi partition key hoặc clustering key không phải thêm field bình thường

Xét primary key V1:

~~~sql
PRIMARY KEY ((tenant_id, order_day), placed_at, order_id)
~~~

Trong đó:

- `(tenant_id, order_day)` là **composite partition key** quyết định dữ liệu thuộc partition nào.
- `placed_at` và `order_id` là **clustering columns** xác định hàng và thứ tự bên trong partition.

Giả sử V2 cần chia nhỏ partition hơn, chuyển sang:

~~~sql
PRIMARY KEY ((tenant_id, order_day, shard), placed_at, order_id)
~~~

Điều này làm thay đổi **vị trí dữ liệu và cách định tuyến truy vấn**. Không thể an toàn “thêm `shard` vào primary key” của bảng đã chứa dữ liệu bằng cách đổi annotation hoặc dùng auto schema creation. Cassandra không hỗ trợ thay đổi tự do cấu trúc primary key của bảng hiện có như sửa một cột bình thường.

Hướng xử lý thường là tạo **bảng V2 mới**, nạp dữ liệu có kiểm soát, chuyển việc ghi/đọc và chỉ loại bỏ bảng cũ khi chắc chắn:

~~~sql
CREATE TABLE commerce_ks.orders_by_tenant_day_v2 (
    tenant_id  uuid,
    order_day  date,
    shard      smallint,
    placed_at  timestamp,
    order_id   uuid,
    amount     decimal,
    status     text,
    channel    text,
    PRIMARY KEY ((tenant_id, order_day, shard), placed_at, order_id)
) WITH CLUSTERING ORDER BY (placed_at DESC, order_id DESC);
~~~

Với V2, mọi truy vấn theo một partition phải biết đủ `tenant_id`, `order_day` và `shard`. Khi hiển thị tất cả đơn của một tenant trong ngày, ứng dụng có thể phải truy vấn nhiều shard rồi **merge theo thứ tự clustering**. Chọn khóa mới vừa là bài toán schema, vừa là bài toán thiết kế truy vấn và hiệu năng.

Tương tự, thay đổi thứ tự các clustering column hoặc thiết kế lại cách sắp xếp không thể mặc định xử lý như một migration thêm cột. Chọn bảng mới và luồng chuyển dữ liệu thường rõ ràng, an toàn hơn.

## 6. Những thay đổi thường gặp trên bảng đã tồn tại

| Thay đổi mong muốn | Có thể chỉ sửa entity? | Cách tiếp cận |
| --- | --- | --- |
| Thêm một cột thường như `channel text` | **Không** | Migration `ALTER TABLE ... ADD` rồi cập nhật mapping/ứng dụng |
| Đổi tên cột thường hoặc đổi ý nghĩa dữ liệu | Không | Đánh giá hạn chế CQL theo version; thường thêm cột mới, chuyển dữ liệu và loại cũ có kiểm soát |
| Đổi kiểu dữ liệu cột | Không | Xác minh giới hạn CQL/compatibility; với thay đổi lớn thường tạo cột/bảng mới và chuyển đổi |
| Đổi partition key, clustering key | Không | Tạo bảng mới với primary key mới, backfill/cutover |
| Đổi thứ tự clustering | Không | Thường cần bảng mới, vì cấu trúc sắp xếp thuộc schema của bảng |
| Thêm/chỉnh index | Không tự suy ra từ field Java | Cân nhắc khả năng/chi phí index theo phiên bản, dùng DDL và theo dõi tác động |
| Thay TTL/compaction/table options | Không | DDL thay đổi option thích hợp và kiểm thử tác động; thay option không đồng nghĩa dữ liệu cũ được viết lại |
| Đổi replication factor của keyspace | Không | `ALTER KEYSPACE` và quy trình vận hành/repair tương ứng, không sửa entity |
| Xóa cột hoặc bảng không còn dùng | Không | Chỉ thực hiện sau khi hết consumer và có phương án rollback/backup |

Mức hỗ trợ `ALTER TABLE`, `RENAME` và thay đổi kiểu phụ thuộc **phiên bản Cassandra** và ràng buộc schema cụ thể. Không nên xem ví dụ SQL bất kỳ trên Internet là thao tác có thể chạy nguyên vẹn ở production.

**Lưu ý:** trong Cassandra, thay đổi schema không tự giải quyết chuyện dữ liệu phân tán, consistency và paging. Một cột mới có thể tồn tại ở schema nhưng truy vấn quét nhiều partition hoặc partition khổng lồ vẫn là vấn đề về data model.

## 7. Vì sao `RECREATE` không phải đường nâng cấp?

Giả sử bảng `orders_by_tenant_day` đã chứa hàng triệu đơn. Một người muốn “đồng bộ schema nhanh” bằng cách bật:

~~~yaml
spring:
  cassandra:
    schema-action: recreate
~~~

Đây là **một cấu hình nguy hiểm nếu dùng trên dữ liệu cần giữ**. Chế độ recreate mang ý nghĩa tái tạo các đối tượng schema mà Spring Data quản lý, có thể xóa rồi tạo lại, tức **dữ liệu hiện hữu có nguy cơ bị mất**. Chế độ recreate/drop-unused cũng có nguy cơ ảnh hưởng những đối tượng khác, tùy cách framework xác định phạm vi quản lý.

Trong môi trường dev/test dùng dữ liệu giả có thể chấp nhận tái tạo để khởi động nhanh. Trong production, thay đổi schema phải là hoạt động độc lập, có kế hoạch và có thể đánh giá trước khi thực thi.

Không dùng `RECREATE` để sửa tình trạng “mapping thiếu một cột” nếu mục tiêu là bảo toàn dữ liệu. Một DDL có kiểm soát hoặc kế hoạch bảng V2 sẽ có phạm vi tác động rõ ràng hơn nhiều.

## 8. Quy trình migration an toàn theo từng giai đoạn

Một cách làm thực tế là **expand → migrate/backfill → switch → contract**:

~~~text
Code V1 + Schema V1 đang phục vụ
        |
        v
EXPAND: thêm cột hoặc tạo bảng V2, không phá V1
        |
        v
MIGRATE: backfill/dual-write có kiểm soát nếu cần
        |
        v
SWITCH: chuyển reader/writer, kiểm tra dữ liệu và hiệu năng
        |
        v
CONTRACT: dừng dùng cấu trúc cũ, dọn khi đã đủ điều kiện
~~~

### Bước 1 — Khảo sát và định nghĩa thay đổi

Ghi rõ version schema đang có, các bảng được sử dụng, kiểu cột và khóa; xác định những repository, `CassandraTemplate` và CQL thủ công nào đang tham chiếu bảng. Thống kê cả job batch, reporting và hệ thống khác có thể đọc cùng dữ liệu.

Đối chiếu truy vấn thực tế: chúng có cung cấp đủ partition key? Có đọc khoảng thời gian bằng nhiều partition? Có paging dựa trên paging state không? Thay đổi primary key thường kéo theo **thay đổi hợp đồng đọc/ghi**, không chỉ thay đổi DDL.

### Bước 2 — Expand schema trước khi deploy code phụ thuộc

Với thay đổi thêm cột, chạy migration tường minh trong một quy trình quản lý tập trung:

~~~sql
ALTER TABLE commerce_ks.orders_by_tenant_day
ADD channel text;
~~~

Nếu cột có thể đã được tạo trước đó, migration runner phải kiểm tra trạng thái hoặc dùng cú pháp idempotent **được phiên bản Cassandra hỗ trợ**. Không tự giả định mọi lệnh `ALTER TABLE` đều có `IF NOT EXISTS`.

Với thay đổi khóa, tạo `orders_by_tenant_day_v2` trước, xác minh keyspace, replication, table options và schema của bảng mới.

### Bước 3 — Chờ schema agreement và xác minh

Cassandra phân tán thông tin schema giữa các node. Sau DDL, cần kiểm tra các node đã đạt **schema agreement** trước khi cho nhiều writer dùng cột/bảng mới; công cụ driver/quản trị có cơ chế kiểm tra phù hợp với phiên bản.

Có thể kiểm tra cấu trúc bảng qua CQL schema metadata:

~~~sql
SELECT column_name, kind, position, type
FROM system_schema.columns
WHERE keyspace_name = 'commerce_ks'
  AND table_name = 'orders_by_tenant_day';
~~~

Đồng thời có thể dùng `DESCRIBE TABLE commerce_ks.orders_by_tenant_day;` trong **cqlsh** để xem DDL đã được biểu diễn; `DESCRIBE` là lệnh tiện ích của cqlsh, không phải câu CQL thông thường nên không gửi nguyên văn qua mọi API driver.

### Bước 4 — Backfill và triển khai tương thích

Với cột `channel` mới: dữ liệu cũ có thể thiếu channel. Nếu cần tra cứu theo channel, tạo quy trình backfill theo partition có giới hạn và đo tải trước khi quét dữ liệu. Không quét toàn bộ bảng với `SELECT *` hoặc `ALLOW FILTERING` vô điều kiện trên cluster bận.

Với bảng V2 mới: chia backfill thành các partition/bucket rõ ràng, có checkpoint và khả năng tiếp tục; nếu dữ liệu tiếp tục thay đổi, cân nhắc dual-write hoặc cơ chế đồng bộ chênh lệch. Tính đến ngữ nghĩa upsert/timestamp, retry, TTL, tombstone và consistency của Cassandra để tránh bản ghi bị ghi đè sai hoặc hết hạn lệch.

Thực hiện rolling deployment sao cho **code V1 vẫn chạy được khi schema được expand**, và code V2 không chạy trước các DDL bắt buộc. Đừng xóa cột/bảng cũ khi còn instance V1 hoặc consumer bên ngoài sử dụng.

### Bước 5 — Cutover và contract

Chuyển luồng đọc sang schema V2 khi kết quả và performance đã được đối chiếu. Theo dõi độ trễ p95/p99, lỗi CQL, partition size, paging, write amplification và khác biệt số bản ghi.

Chỉ loại bỏ dữ liệu/bảng cũ sau khi hoàn tất kiểm chứng, có kế hoạch rollback và thời gian bảo lưu phù hợp. “Rollback code” không nhất thiết rollback được một lệnh DDL phá hủy hoặc dữ liệu đã di chuyển.

## 9. Quản lý migration riêng với vòng đời ứng dụng

Trong production, hướng tổ chức khuyến nghị:

1. **DDL được version hóa:** lưu các thay đổi CQL có mô tả mục tiêu và điều kiện chạy, đi qua review giống code.
2. **Một workflow áp dụng schema:** triển khai migration trước hoặc trong bước release có thứ tự rõ ràng, tránh tất cả instance tự tranh nhau thực thi DDL lúc startup.
3. **Cơ chế kiểm soát trạng thái:** ghi migration nào đã áp dụng; xác minh schema hiện tại trước và sau.
4. **Quyền hạn phân tách:** tài khoản runtime ứng dụng chủ yếu có quyền DML cần thiết, còn tài khoản migration có quyền DDL theo phạm vi được phép.
5. **Thử nghiệm tương thích:** kiểm tra các phiên bản code chạy song song với schema ở các giai đoạn trung gian; đo thời gian schema propagation và tác động lên cluster.

Có thể dùng migration framework/công cụ tổ chức hỗ trợ Cassandra hoặc hệ thống release nội bộ, miễn là nó **thực sự quản lý CQL, thứ tự, trạng thái và lỗi**. Không nên cho rằng mọi công cụ migration dành cho JDBC/SQL quan hệ đều hiểu Cassandra giống nhau.

Ví dụ cấu hình ứng dụng runtime:

~~~yaml
spring:
  cassandra:
    keyspace-name: commerce_ks
    local-datacenter: datacenter1
    contact-points: cassandra.service.internal
    schema-action: none
~~~

Khi đó **schema đã được chuẩn bị trước bởi migration**, ứng dụng chỉ sử dụng nó. Tên thuộc tính ở đây phù hợp kiểu cấu hình Spring Boot 3.x; các dự án Boot đời cũ có thể sử dụng namespace `spring.data.cassandra.*`, cần đối chiếu theo version.

## 10. Chú ý dữ liệu cũ, TTL, index và UDT

Các thay đổi sau dễ gây hiểu lầm ngay cả khi DDL đã chạy thành công:

**Cột mới trên hàng cũ:** Cassandra không mặc định tự quét để điền giá trị cho tất cả hàng. Khi query một hàng không có giá trị cột mới, ứng dụng cần xử lý giá trị thiếu; với ràng buộc nghiệp vụ bắt buộc có giá trị, cần chính sách backfill.

**TTL:** sửa `default_time_to_live` thường tác động tới **các ghi mới** theo cấu hình, không tự “gia hạn” hoặc “rút ngắn” TTL đã được thiết lập trên dữ liệu trước đó. Xóa/hết TTL tạo tombstone; dung lượng đĩa được giải phóng qua compaction theo điều kiện thực tế, không ngay khi metadata thay đổi.

**Index:** thêm index không biến mọi truy vấn theo mọi cột thành truy vấn rẻ. Cần xem phân phối giá trị, độ chọn lọc, kích thước partition và hệ thống index hỗ trợ ở phiên bản Cassandra hiện dùng; index cũng có chi phí duy trì.

**UDT và collection:** đổi định nghĩa user-defined type hoặc kiểu dữ liệu tổ hợp có thể ảnh hưởng mapping và độ tương thích của dữ liệu cũ. Cần thử nghiệm schema và driver codec; không chỉ sửa Java class rồi kỳ vọng Cassandra tự chuyển đổi.

**Clustering order:** cấu hình `WITH CLUSTERING ORDER BY (...)` của bảng chi phối thứ tự đọc cục bộ theo khóa. Một thay đổi annotation Spring Data không tự cập nhật thứ tự clustering của bảng tồn tại.

## 11. Tương thích với repository, CassandraTemplate và truy vấn CQL

Giả sử repository V2 yêu cầu cột mới:

~~~java
public interface OrderRepository
        extends CassandraRepository<OrderRow, OrderKey> {

    @Query("""
        SELECT tenant_id, order_day, placed_at, order_id,
               amount, status, channel
        FROM orders_by_tenant_day
        WHERE tenant_id = ?0 AND order_day = ?1
        LIMIT 50
        """)
    List<OrderRow> recentByTenantAndDay(UUID tenantId, LocalDate day);
}
~~~

Đoạn mã dùng cú pháp **Java text block** (Java 15+); nếu dự án dùng Java cũ hơn, viết chuỗi nối thông thường. Ví dụ giả định ứng dụng đã cấu hình keyspace mặc định `commerce_ks`.

Nếu `channel` chưa tồn tại, câu CQL có thể thất bại ngay khi được chuẩn bị/thực thi. `CassandraTemplate` và `ReactiveCassandraTemplate` cũng chịu giới hạn schema tương tự; chúng **không tự ALTER TABLE** để sửa cột thiếu.

Reactive repository trả `Mono`/`Flux` thay vì chặn thread, nhưng không miễn trừ yêu cầu schema đã triển khai hoặc partition key phù hợp. Thay đổi bảng và CQL query phải được phối hợp với cả đường đọc đồng bộ lẫn phản ứng nếu hai mô hình cùng được sử dụng.

Ngoài tên cột, kiểm tra cả tên keyspace/bảng được tham chiếu, kiểu CQL và Java codec, giá trị null, metadata primary key, và truy vấn viết tay nằm ngoài repository. Mapping “compile được” không đủ đảm bảo chạy đúng ở runtime.

## 12. Kiểm thử migration và phương án khi deploy lỗi

Trước khi thay đổi bảng chứa dữ liệu thật, nên có những kiểm tra phù hợp:

| Kiểm tra | Điều cần chứng minh |
| --- | --- |
| Schema trước migration | Đúng keyspace, bảng, columns, primary key và options dự kiến |
| Chạy migration trên dữ liệu mẫu V1 | Thay đổi thành công và không làm mất hàng cần giữ |
| Khởi chạy code V1 trên schema đã expand | V1 vẫn đọc/ghi được trong rolling deployment |
| Khởi chạy code V2 sau migration | V2 hoạt động với cột/bảng mới |
| Dữ liệu lịch sử | Các trường mới nullable/default/backfill được xử lý |
| Truy vấn theo partition key | Không tạo quét dữ liệu ngoài dự kiến |
| Paging và consistency | Trang dữ liệu, thứ tự, CL vẫn phù hợp |
| Tình huống deploy thất bại | Có cách rollback code/cutover mà không yêu cầu phục hồi dữ liệu đã xóa |

Ví dụ hai kiểu lỗi và hướng xử lý:

**Lỗi A — Code V2 chạy quá sớm:** instance mới query `channel` nhưng DDL chưa được áp dụng; hệ thống báo cột không tồn tại. Cách xử lý là đưa schema về trạng thái tương thích trước, hoặc tạm rollback code V2 trong khi chuẩn bị migration. Chỉ bật `CREATE_IF_NOT_EXISTS` không đủ nếu bảng vốn đã tồn tại.

**Lỗi B — Đổi primary key bằng cách sửa annotation:** code V2 ghi với `shard` nhưng bảng V1 không có shard trong primary key. Không thể giải quyết bằng restart. Cần tạo bảng V2, chuyển dữ liệu và đổi đường truy cập đúng kế hoạch.

**Lỗi C — Chọn recreate trên production:** nguy cơ mất dữ liệu đã lưu. Phương án xử lý phụ thuộc backup, snapshot và trạng thái cluster; không được giả định có rollback schema tức thì. Đây là lý do kiểm soát quyền chạy DDL và review cấu hình môi trường là cần thiết.

## 13. Checklist trước khi chọn schema action

- [ ] Đã biết rõ phiên bản Spring Boot, Spring Data Cassandra và Apache Cassandra.
- [ ] Đã kiểm tra schema thực tế trên cluster, không chỉ đọc entity Java.
- [ ] Đã phân biệt thao tác **tạo bảng mới** với **nâng cấp bảng đã có dữ liệu**.
- [ ] Đã xác định thay đổi chỉ liên quan cột thường hay ảnh hưởng primary key/clustering.
- [ ] Đã có migration script/quy trình được version hóa nếu là production.
- [ ] Đã kiểm tra schema agreement trước khi bật code cần cột/bảng mới.
- [ ] Đã tính đến dữ liệu cũ, TTL, tombstone, index, query và paging.
- [ ] Đã thử tương thích trong rolling deployment và có phương án rollback.
- [ ] Ứng dụng production không vô tình bật `RECREATE` hoặc các chế độ xóa schema.
- [ ] Sau triển khai có monitoring lỗi CQL, độ trễ, kích thước partition và replica.

## 14. Tự kiểm tra

**Câu 1.** Bảng `orders_by_tenant_day` đã tồn tại, entity bổ sung `channel`. Bật `CREATE_IF_NOT_EXISTS` có chắc chắn tạo thêm cột không?

**Đáp án:** Không. Chế độ này hướng tới tạo đối tượng chưa tồn tại; không phải migration tổng quát để đồng bộ mọi cột của bảng đã có. Cần kiểm tra và áp dụng migration phù hợp.

**Câu 2.** Có thể đổi từ `PRIMARY KEY ((tenant_id, order_day), placed_at)` sang `PRIMARY KEY ((tenant_id, order_day, shard), placed_at)` chỉ bằng annotation không?

**Đáp án:** Không. Đây là thay đổi cấu trúc phân vùng và cách định tuyến dữ liệu. Thường phải tạo bảng mới và chuyển dữ liệu/đường truy vấn.

**Câu 3.** Vì sao application startup thành công chưa đủ chứng minh schema V2 tương thích?

**Đáp án:** Lỗi mismatch có thể chỉ xuất hiện khi ứng dụng thực thi truy vấn hay ghi cột cụ thể. Bảng đã tồn tại cũng không bị Spring Data tự nâng cấp tương ứng với mọi thay đổi entity.

**Câu 4.** Muốn thêm cột thường vào bảng đang phục vụ production, thứ tự an toàn cơ bản là gì?

**Đáp án:** Tạo migration mở rộng schema → kiểm tra schema agreement → triển khai code tương thích → backfill nếu cần → chuyển luồng xử lý và theo dõi → chỉ dọn cấu trúc cũ sau khi hết consumer.

**Câu 5.** Đổi starter từ đồng bộ sang reactive có sửa được schema thiếu cột hoặc partition key sai không?

**Đáp án:** Không. Cả hai đều thực thi CQL dựa trên schema thực tế của cluster; reactive chỉ thay đổi cách xử lý I/O trong ứng dụng.

---

**Ghi nhớ:** tạo lược đồ tự động hữu ích khi **khởi tạo môi trường mới**, nhưng **bảng Cassandra đã tồn tại không tự tiến hóa theo entity Java**. Với production, thường nên để `schema-action: none` và quản lý thay đổi CQL riêng, có kiểm tra schema agreement, khả năng tương thích code V1/V2, kế hoạch dữ liệu và rollback. Đặc biệt, thay đổi **partition key hoặc clustering key** là thay đổi thiết kế dữ liệu và truy vấn; không phải một thao tác auto schema đơn giản.
