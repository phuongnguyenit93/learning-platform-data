# Schema action, migration và tách thay đổi DDL khỏi khởi tạo ứng dụng

> **Chương:** Spring Boot và Spring Data  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Phạm vi:** Apache Cassandra — hệ cơ sở dữ liệu phân tán wide-column, thiết kế bảng theo partition key và truy vấn, replication/consistency level, CQL, compaction, repair, xử lý lỗi và tích hợp Java.  
> **Trọng tâm:** Spring Boot, Spring Data Cassandra, schema action, migration có phiên bản và quy trình triển khai DDL độc lập với khởi tạo ứng dụng.

## 1. Bài toán: vì sao ứng dụng khởi động không nên đồng thời sửa schema?

Một dịch vụ đơn hàng chạy 20 instance Spring Boot. Tại thời điểm deploy, 20 instance mới khởi động gần như cùng lúc. Nếu mỗi instance đều cố tạo hoặc thay đổi bảng Cassandra bằng cơ chế tự động dựa trên entity Java, có thể xuất hiện các vấn đề:

- Nhiều tiến trình đồng thời gửi **CREATE/ALTER** khiến thao tác schema chồng chéo.
- Entity của bản mới và bản cũ cùng tồn tại trong rolling deployment nhưng có **hai cách hiểu schema** khác nhau.
- Một thay đổi column/UDT không tương thích làm startup fail; container orchestrator liên tục restart, phát thêm DDL.
- Một schema action có tính phá hủy có thể làm mất dữ liệu bảng hiện có.
- Tên field hoặc kiểu Java được suy ra không diễn tả **đầy đủ** replication, clustering order, TTL, compaction strategy hay cách vận hành dữ liệu của Cassandra.
- Quyền **CREATE/ALTER/DROP** phải cấp cho mọi instance chỉ để khởi động, mở rộng bề mặt rủi ro bảo mật.

Trong production, giải pháp phổ biến và dễ kiểm soát hơn là:

**Schema được quản lý bằng migration CQL có phiên bản, chạy một lần trong một giai đoạn triển khai được kiểm soát; ứng dụng Spring Boot khởi động với schema action NONE và chỉ thực thi nghiệp vụ.**

Điều này không có nghĩa phải viết mọi DDL bằng tay ở mọi môi trường. Ở test/lab, tự tạo schema có thể tiện lợi; nhưng không nên lẫn tiện ích local với chính sách production.

Sau bài này, bạn có thể:

1. Phân biệt **Spring Data mapping metadata** và **schema thật của Cassandra**.
2. Hiểu ý nghĩa, rủi ro và phạm vi của các **SchemaAction** trong Spring Data Cassandra.
3. Đặt **spring.cassandra.schema-action: none** ở Spring Boot 3.x và nhận biết khác biệt cấu hình giữa thế hệ Boot.
4. Tách migration DDL thành job/pipeline riêng, có thứ tự, checksum, owner, quyền và bằng chứng.
5. Thiết kế thay đổi theo **expand → migrate/backfill → switch → contract** để rolling deployment không làm gãy bản ứng dụng cũ.
6. Kiểm tra schema agreement, RF/DC, primary key, CQL và kết nối Java trước khi mở traffic.
7. Chuẩn bị runbook failure/rollback trong các thay đổi có thể không đảo ngược được.

> **Lưu ý phiên bản:** Cấu hình Boot, danh sách SchemaAction, hành vi tạo UDT/bảng, tích hợp migration tool và cú pháp CQL có thể khác theo **Spring Boot/Spring Data Cassandra/Cassandra** cụ thể. Các ví dụ trình bày cho hướng dùng **Spring Boot 3.x + Spring Data Cassandra + Java driver 4.x**. Khi dùng Boot 2.x hoặc bản phân phối Cassandra khác, cần đối chiếu đúng documentation, không sao chép property name hay API một cách máy móc.

## 2. Ba lớp trách nhiệm: entity, schema, dữ liệu

Spring Data Cassandra cho phép mô tả entity Java bằng annotation như **@Table**, **@PrimaryKey**, **@PrimaryKeyClass**, **@PrimaryKeyColumn** và **@Column**. Các annotation cung cấp **mapping metadata** để framework đọc/ghi row.

Cassandra lưu schema và dữ liệu trong cluster. DDL là các lệnh **CREATE KEYSPACE**, **CREATE TABLE**, **ALTER TABLE**, **CREATE TYPE**, **CREATE INDEX** và các thao tác thay đổi khác. Chúng ảnh hưởng tới nhiều node, không chỉ tiến trình Java đang khởi động.

~~~mermaid
flowchart LR
    E["Entity Java + repository"] --> M["Spring Data mapping"]
    M --> D["CQL SELECT/INSERT/UPDATE"]
    D --> C["Cassandra cluster\nschema + dữ liệu"]
    V["Migration CQL có phiên bản"] --> G["Migration job có quyền DDL"]
    G --> C
    A["Spring Boot application"] --> M
    P["CI/CD gates và phê duyệt"] --> G
~~~

### 2.1. Mapping không phải nguồn sự thật độc nhất

Ví dụ entity có trường **status** kiểu String. Nó không tự mô tả những lựa chọn vận hành quan trọng:

- Keyspace dùng **NetworkTopologyStrategy**, RF theo từng DC nào?
- Partition key có chia bucket theo ngày không? Một partition dự kiến lớn đến đâu?
- Clustering order phải **DESC/ASC** thế nào cho truy vấn chính?
- TTL, **gc_grace_seconds**, compaction hoặc compression của bảng được phê duyệt ra sao?
- UDT/index tồn tại theo phiên bản nào và có được các phiên bản ứng dụng cũ hiểu không?
- Có quyền DDL hay không? Có áp dụng đúng **data residency/security** theo DC không?

Các quyết định này thuộc **schema contract + kiến trúc dữ liệu + vận hành cluster**. Mapping Java cần **khớp** schema, nhưng không nên mặc định có quyền tái tạo schema production theo suy luận từ class.

### 2.2. Khác biệt với cơ sở dữ liệu quan hệ

Cassandra không được thiết kế để ứng dụng sửa schema tùy ý mỗi lần startup như một database local nhỏ. DDL được phân phối và đồng bộ metadata giữa các node; thêm nữa, **PRIMARY KEY quyết định vị trí/tổ chức dữ liệu**. Thay partition key hoặc clustering key thường không phải một lệnh ALTER nhỏ mà cần **bảng mới, di chuyển dữ liệu và chuyển truy vấn**.

Cassandra cũng không cung cấp transaction DDL đa bước theo kiểu “CREATE/ALTER nhiều bảng, nếu lệnh cuối lỗi thì ROLLBACK tất cả” cho migration. Một script chạy nửa chừng có thể để lại **trạng thái schema đã thay đổi một phần**.

## 3. SchemaAction của Spring Data Cassandra

Spring Data Cassandra có cấu hình **SchemaAction** để quyết định điều gì xảy ra với schema trong quá trình khởi tạo context, tùy framework và phiên bản. Các giá trị thường gặp gồm:

| Schema action | Ý nghĩa khái quát | Có thích hợp production chạy nhiều instance? |
|---|---|---|
| **NONE** | Không tự thực hiện hành động tạo/tái tạo schema dựa trên mapping khi startup | **Lựa chọn mặc định nên thiết lập tường minh** nếu schema được quản lý bằng migration riêng |
| **CREATE** | Tạo schema từ mapping theo cơ chế framework | Chỉ cân nhắc cho môi trường thử có lifecycle được kiểm soát |
| **CREATE_IF_NOT_EXISTS** | Tạo những đối tượng mapping cần nhưng chưa tồn tại, theo logic framework | Phù hợp một số lab/test, **không phải migration an toàn cho mọi schema đang tồn tại** |
| **RECREATE** | Tái tạo schema theo cơ chế framework; có thể làm rơi dữ liệu/bảng | **Không dùng trong production** |
| **RECREATE_DROP_UNUSED** | Biến thể tái tạo/dọn đối tượng không dùng theo mapping; có tính phá hủy | **Không dùng trong production** |

**Điểm cốt lõi:** **CREATE_IF_NOT_EXISTS không phải schema diff/migration engine.** Nếu bảng đã tồn tại nhưng thiếu cột mới, có sai kiểu CQL, thay đổi clustering key hoặc không đúng compaction settings, việc “nếu chưa tồn tại thì tạo” không tự bảo đảm nâng cấp schema đó chính xác.

Không nên coi **SchemaAction.NONE** là một bộ **validator schema**. NONE chỉ có nghĩa framework không tự tạo/sửa; ứng dụng vẫn có thể fail khi repository chuẩn bị CQL hoặc truy vấn cột chưa tồn tại. Cần kiểm chứng schema bằng migration job và integration tests riêng.

### 3.1. Giá trị phá hủy là nguy cơ đặc biệt

Một schema action tái tạo có thể phù hợp **test cluster tạm thời không chứa dữ liệu thật**. Trong production, nếu nó xóa/recreate bảng/UDT, hậu quả có thể gồm:

- Mất dữ liệu không thể sửa bằng restart application.
- Sự kiện DELETE/TTL/tombstone và replica không tự phục hồi nội dung đã xóa đúng theo nghiệp vụ.
- Một số app vẫn đang đọc/ghi bảng cũ trong rolling deployment.
- Backup có recovery point trước thao tác không chứa ghi mới sau đó.

**Không dựa vào replication factor để coi DROP/RECREATE là an toàn.** Replica là bản sao của những mutation/schema changes; backup độc lập và restore drill mới là lớp phục hồi khác miền lỗi.

### 3.2. Tại sao không “CREATE_IF_NOT_EXISTS ở production cho tiện”?

- Mọi instance vẫn cần quyền tạo schema, trong khi runtime chỉ cần DML.
- Nếu nhiều app version cùng startup, mapping của chúng có thể khác nhau.
- Lỗi migration không có lịch sử/checksum/phê duyệt rõ.
- Một thay đổi entity có thể vô tình phụ thuộc cột chưa migration.
- Logic tự tạo đối tượng có thể không quản lý đầy đủ replication, index/UDT, table options và thứ tự thay đổi.
- Một schema đã có tên đúng nhưng **cấu trúc sai** không được coi là hợp lệ chỉ vì tồn tại.

Vì vậy, **schema action NONE + migration độc lập** là lựa chọn dễ audit và kiểm soát rủi ro hơn cho hệ thống đang phục vụ.

## 4. Cấu hình Spring Boot: application không tự chạy DDL

Với Spring Boot **3.x** dùng auto-configuration Cassandra, một cấu hình minh họa:

~~~yaml
spring:
  application:
    name: order-api
  cassandra:
    contact-points:
      - cassandra-1.internal
      - cassandra-2.internal
    port: 9042
    local-datacenter: dc1
    keyspace-name: commerce
    schema-action: none
~~~

Ý nghĩa:

- **keyspace-name** chọn keyspace ứng dụng sử dụng; nó **không tự định nghĩa RF/topology** cho cluster.
- **local-datacenter** phải khớp tên DC thực tế để driver định tuyến phù hợp.
- **schema-action: none** yêu cầu Spring Data không tự tạo schema theo entity khi context khởi động.
- Contact points chỉ là địa chỉ bắt đầu khám phá cluster, không phải danh sách tất cả replica.
- Production cần **TLS, xác thực, secrets, network policy** phù hợp; không đưa mật khẩu vào YAML commit công khai.

**Không đồng nhất cấu hình giữa các đời Boot.** Một số phiên bản Spring Boot 2.x dùng namespace **spring.data.cassandra...**, còn các phiên bản 3.x dùng **spring.cassandra...** cho thuộc tính kết nối/schema. Kiểm tra tài liệu và **effective configuration** của đúng phiên bản trước khi rollout. Một property viết sai tên có thể không có hiệu lực như mong muốn.

### 4.1. Đặt schema action NONE ở mọi môi trường quan trọng

Có thể đặt **NONE** tường minh cho staging và production để kiểm chứng pipeline migration. Với unit/integration test hoàn toàn cô lập, có thể tạo schema bằng test fixture hoặc cơ chế tạo được kiểm soát.

Đừng xây logic kiểu:

~~~java
// Anti-pattern minh họa: API startup tự chạy DDL.
@Component
class SchemaOnStartup {
    @EventListener(ApplicationReadyEvent.class)
    void init() {
        // cqlSession.execute("ALTER TABLE ...");
    }
}
~~~

Đoạn pseudo-code trên **không phải một triển khai được phép dùng**. Nó cho thấy nguy cơ khi mỗi instance AppReady đều chạy DDL. Thay bằng **migration job** ở pipeline, trước khi mở version app cần schema mới.

### 4.2. Quyền của runtime khác quyền migration

| Actor | Quyền cần thiết | Không nên có thường xuyên |
|---|---|---|
| **Ứng dụng Spring Boot runtime** | SELECT, MODIFY trên bảng/keyspace phục vụ tính năng; các quyền metadata/connection cần thiết | CREATE/ALTER/DROP toàn keyspace/cluster |
| **Migration job** | CREATE/ALTER theo phạm vi keyspace, quyền đọc metadata phục vụ kiểm chứng | Toàn quyền cluster khi không cần |
| **DBA/SRE** | Quản lý replication, node, backup/restore và phê duyệt thay đổi | Dùng chung credential app cho mọi việc |
| **CI/CD orchestrator** | Chạy một migration versioned job, ghi log/audit, quản lý approval | Ghi secret vào artifact, chạy DDL tại mọi replica/app |

Cassandra có mô hình quyền theo version/authenticator/authorizer được cấu hình; xác nhận cú pháp **GRANT** và đối tượng quyền ở cluster cụ thể. Nguyên tắc là **least privilege + secret rotation + audit**.

## 5. CQL schema: ví dụ thiết kế đúng theo truy vấn

Giả sử API thường đọc **danh sách đơn hàng của một khách hàng trong một ngày, mới nhất trước**. Ta thiết kế một partition theo **(customer_id, order_day)** và các clustering columns.

### 5.1. Keyspace và replication

Ví dụ **lab** với RF 3 trong dc1:

~~~sql
-- Chỉ chạy khi dc1 có đủ node/phân bổ replica phù hợp.
CREATE KEYSPACE IF NOT EXISTS commerce
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
~~~

**Ở production**, keyspace/RF phải được DBA/SRE chốt theo topology, DC, rack và RPO/RTO. Không để một entity Java hoặc tiện ích auto-create ngầm quyết định replication. Việc thay RF cần kế hoạch vận hành/repair phù hợp và không phải chỉ sửa một dòng trong application.yml.

### 5.2. Tạo bảng đúng access pattern

~~~sql
CREATE TABLE IF NOT EXISTS commerce.orders_by_customer_day (
    customer_id uuid,
    order_day date,
    created_at timestamp,
    order_id uuid,
    status text,
    amount decimal,
    PRIMARY KEY ((customer_id, order_day), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

- **(customer_id, order_day)** là composite partition key. Query phải bind đủ hai thành phần.
- **created_at, order_id** là clustering key, hỗ trợ thứ tự trong partition.
- **status, amount** là dữ liệu nghiệp vụ; một số truy vấn khác theo order_id có thể cần **bảng riêng theo truy vấn**.
- Một khách hàng rất nóng vẫn có thể tạo partition theo ngày lớn. Cần đo row count/bytes và cân nhắc bucket nhỏ hơn/shard khi cần.
- **CREATE TABLE IF NOT EXISTS** giúp lệnh tạo có thể lặp trong điều kiện đối tượng chưa có, nhưng **không bảo đảm table options/columns của bảng đang tồn tại khớp với migration**.

### 5.3. Truy vấn CQL điển hình

~~~sql
SELECT created_at, order_id, status, amount
FROM commerce.orders_by_customer_day
WHERE customer_id = ?
  AND order_day = ?
LIMIT ?;
~~~

Đây là query cho **PreparedStatement** trong Java. Không dùng **ALLOW FILTERING** để chữa việc thiếu partition key. Nếu API cần xem nhiều ngày, phải truy vấn các bucket có giới hạn và merge theo thứ tự nghiệp vụ.

## 6. Mapping Spring Data Cassandra khớp với primary key

Spring Data có thể map entity theo mô hình bảng trên. Ví dụ Java tối giản:

~~~java
import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;

@PrimaryKeyClass
public class OrderEventKey implements Serializable {
    @PrimaryKeyColumn(
        name = "customer_id", ordinal = 0,
        type = PrimaryKeyType.PARTITIONED)
    private UUID customerId;

    @PrimaryKeyColumn(
        name = "order_day", ordinal = 1,
        type = PrimaryKeyType.PARTITIONED)
    private LocalDate orderDay;

    @PrimaryKeyColumn(
        name = "created_at", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED)
    private Instant createdAt;

    @PrimaryKeyColumn(
        name = "order_id", ordinal = 3,
        type = PrimaryKeyType.CLUSTERED)
    private UUID orderId;

    public OrderEventKey() {}

    public OrderEventKey(
            UUID customerId, LocalDate orderDay,
            Instant createdAt, UUID orderId) {
        this.customerId = customerId;
        this.orderDay = orderDay;
        this.createdAt = createdAt;
        this.orderId = orderId;
    }

    public UUID getCustomerId() { return customerId; }
    public LocalDate getOrderDay() { return orderDay; }
    public Instant getCreatedAt() { return createdAt; }
    public UUID getOrderId() { return orderId; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderEventKey)) return false;
        OrderEventKey that = (OrderEventKey) other;
        return Objects.equals(customerId, that.customerId)
            && Objects.equals(orderDay, that.orderDay)
            && Objects.equals(createdAt, that.createdAt)
            && Objects.equals(orderId, that.orderId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(customerId, orderDay, createdAt, orderId);
    }
}
~~~

Entity:

~~~java
import java.math.BigDecimal;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_customer_day")
public class OrderEvent {
    @PrimaryKey
    private OrderEventKey key;

    @Column("status")
    private String status;

    @Column("amount")
    private BigDecimal amount;

    public OrderEvent() {}

    public OrderEvent(
            OrderEventKey key, String status, BigDecimal amount) {
        this.key = key;
        this.status = status;
        this.amount = amount;
    }

    public OrderEventKey getKey() { return key; }
    public String getStatus() { return status; }
    public BigDecimal getAmount() { return amount; }
}
~~~

Repository:

~~~java
import java.util.UUID;

import org.springframework.data.cassandra.repository.CassandraRepository;

public interface OrderEventRepository
        extends CassandraRepository<OrderEvent, OrderEventKey> {
    // Khai báo phương thức truy vấn theo access pattern
    // và kiểm chứng CQL được tạo, thay vì suy tên method tùy ý.
}
~~~

> **Lưu ý mã nguồn:** Mỗi class/interface ở trên thuộc **file Java tương ứng**, có package phù hợp. Khi dùng thực tế cần kiểm tra phiên bản Spring Data, annotation/constructor và unit tests. Bài này **không tạo file Java trong repository**.

**Điều quan trọng:** Mapping gồm đủ cả **partition** và **clustering columns**; thay đổi order/kiểu khóa trong entity không sửa primary key Cassandra đã có. Nếu entity Java thay đổi còn table chưa thay, startup có thể vẫn thành công nhưng query/deserialize hoặc save fail.

### 6.1. Một lỗi về mapper rất dễ bỏ sót

Nếu CQL schema có **order_day date** nhưng Java tự tính ngày theo timezone local còn service khác dùng UTC, dữ liệu có thể bị ghi sang **hai partition khác nhau**. Đây không phải lỗi Cassandra DDL, mà là lỗi quy tắc tạo partition key. Migration cần thử cả dữ liệu ở mốc đổi ngày/TTL và nhiều client version.

### 6.2. Repository không thay thế kiểm chứng schema

Một repository interface compile thành công không bảo đảm:

- Bảng đã tồn tại trên cluster.
- Clustering order và partition key đúng.
- Schema đã lan truyền tới mọi node.
- Role runtime có SELECT/MODIFY.
- Driver tương thích kiểu CQL/UDT.
- Consistency level đáp ứng RF/DC.
- Các method derived queries có access pattern hợp lệ và không gây scan.

Vì vậy cần **integration tests trên cluster Cassandra đại diện**, không chỉ context-load test hoặc mock repository.
## 7. Tách migration DDL khỏi vòng đời khởi động Spring Boot

Mô hình triển khai nên có hai thành phần với quyền, trách nhiệm và thời điểm chạy khác nhau:

~~~mermaid
flowchart TD
    A["Commit code + CQL migration"] --> B["Build/test và review schema"]
    B --> C["Phê duyệt thay đổi"]
    C --> D["Một migration job được điều phối"]
    D --> E["Cassandra schema được thay đổi"]
    E --> F["Kiểm tra schema agreement + metadata + smoke test"]
    F --> G{"Đã đạt gate?"}
    G -->|Không| H["Dừng rollout, điều tra/khôi phục"]
    G -->|Có| I["Triển khai Spring Boot vNext"]
    I --> J["App kết nối với schema-action NONE"]
    J --> K["Quan sát SLO và correctness"]
~~~

**Vòng đời migration** thuộc CI/CD hoặc job vận hành riêng. **Vòng đời ứng dụng** là khởi động process, tạo session, mapper, repository và phục vụ request.

### 7.1. Vì sao job chỉ chạy một lần?

Nếu có 20 instance application, không muốn 20 lần startup quyết định chạy migration. Thay vào đó:

- Pipeline có **một execution owner** cho mỗi môi trường/keyspace.
- Migration job được serialize qua hệ điều phối (deployment lock/change ticket/job singleton).
- Không dùng **Cassandra schema metadata** như mutex ngầm giữa nhiều tiến trình.
- Khi job thất bại, không cho version ứng dụng phụ thuộc schema mới nhận traffic.
- Mỗi phiên bản migration chỉ được ghi nhận hoàn tất sau **kiểm chứng hậu điều kiện**.

Chỉ chạy một process không làm các DDL bỗng trở thành transaction. Nó giảm race và dễ quy trách nhiệm khi xảy ra lỗi.

### 7.2. Quyền riêng và đường đi secret

Migration job cần credential có quyền phù hợp để tạo/sửa schema trên **keyspace được ủy quyền**. Runtime app nên có credential hạn chế cho **SELECT/MODIFY** theo bảng cần dùng.

~~~text
CI/CD change approval
       |
       +--> Migration identity (DDL permissions, thời hạn ngắn)
       |         |
       |         +--> CREATE/ALTER + schema checks
       |
       +--> Application identity (DML permissions)
                 |
                 +--> Spring Boot startup
                 +--> SELECT/INSERT/UPDATE/DELETE có kiểm soát
~~~

Không commit password/CQL auth token vào repository. Dùng secret manager và audit; mã hóa kết nối TLS, kiểm tra chứng chỉ, giới hạn network policy. Không dùng một credential admin dài hạn cho mọi pod của ứng dụng.

### 7.3. Tránh startup DDL dưới tên “init helper”

Một số dự án không bật SchemaAction.CREATE nhưng lại có một trong các cơ chế sau:

- **CommandLineRunner** hoặc **ApplicationRunner** gọi **CqlSession.execute("CREATE TABLE ...")**.
- **@PostConstruct** tạo keyspace/bảng.
- **ApplicationReadyEvent** kích hoạt ALTER TABLE.
- Một bean tự tạo index/UDT mỗi khi context refresh.
- Test fixture vô tình được nạp trong production profile.
- Một third-party starter hoặc custom Cassandra configuration kích hoạt schema initialization.

**Tắt SchemaAction mới là một phần của kiểm soát.** Cần kiểm tra cả **code path DDL tùy biến** và quyền của runtime. Cách thực tế nhất để phòng DDL ngoài ý muốn là: **runtime credential không được cấp quyền DDL** và migration chỉ có identity riêng.

## 8. Migration CQL có phiên bản: một mô hình tối thiểu

Một bộ migration thường gồm **file CQL bất biến**, tên phiên bản, checksum, mô tả, thông tin review và thứ tự chạy. Ví dụ chỉ là **cấu trúc đề xuất**, không phải format bắt buộc của Spring Data Cassandra:

~~~text
db/cassandra/
  V001__create_orders_by_customer_day.cql
  V002__add_fulfillment_channel.cql
  V003__create_order_lookup_table.cql

manifest:
  version
  filename
  sha256
  reviewed_by
  approved_change
  expected_precondition
  expected_postcondition
~~~

Bài học không tạo các file minh họa đó; chúng mô tả cách tổ chức trong một dự án Java thật.

### 8.1. Migration V001: create table

~~~sql
-- V001__create_orders_by_customer_day.cql
-- Preconditions:
--   keyspace commerce đã được tạo với RF/DC được duyệt
--   table orders_by_customer_day chưa tồn tại
-- Postconditions:
--   partition/clustering keys, column types và options đúng spec

CREATE TABLE IF NOT EXISTS commerce.orders_by_customer_day (
    customer_id uuid,
    order_day date,
    created_at timestamp,
    order_id uuid,
    status text,
    amount decimal,
    PRIMARY KEY ((customer_id, order_day), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

**Không dừng xác minh tại câu “CREATE không lỗi”.** Nếu bảng đã tồn tại với kiểu hoặc cấu trúc khác, **IF NOT EXISTS** có thể bỏ qua thao tác; migration vẫn cần so **schema thật** với postcondition.

### 8.2. Migration V002: thêm cột, giữ tương thích cũ

~~~sql
-- V002__add_fulfillment_channel.cql
-- Preconditions:
--   V001 đã đạt, cột fulfillment_channel chưa tồn tại
-- Postconditions:
--   fulfillment_channel có kiểu text, không đổi primary key

ALTER TABLE commerce.orders_by_customer_day
ADD fulfillment_channel text;
~~~

Đây là thay đổi **additive**. Row cũ chưa có giá trị cột mới thường được đọc là **null** cho đến khi được backfill/ghi mới. Các ứng dụng cũ không tham chiếu cột này có thể tiếp tục hoạt động, nếu những giả định khác vẫn được giữ nguyên.

**Tuy nhiên**, một thay đổi additive cũng có thể làm lỗi ứng dụng khi:

- Spring Data mapper của bản mới kỳ vọng field **non-null** nhưng dữ liệu cũ vẫn null.
- Query mới tham chiếu cột trước khi DDL lan truyền/được áp.
- Cột mới được tạo khác kiểu so với mapping code.
- Logic **save** ghi null ngoài ý muốn, tạo tombstone cho field đang có.
- Truy vấn từ app cũ dùng **SELECT * / positional mapping** với giả định thứ tự/field cố định không bền vững.

Vì vậy migration cần kiểm thử **old reader, new reader, old writer và new writer**.

### 8.3. Migration V003: thêm bảng theo access pattern khác

Giả sử API mới cần tìm **một order theo (customer_id, order_id)** mà không biết ngày. Thay vì quét mọi bucket ngày hoặc bật ALLOW FILTERING, ta tạo bảng riêng:

~~~sql
-- V003__create_order_lookup_table.cql

CREATE TABLE IF NOT EXISTS commerce.order_lookup_by_id (
    customer_id uuid,
    order_id uuid,
    order_day date,
    created_at timestamp,
    status text,
    PRIMARY KEY ((customer_id), order_id)
);
~~~

Ứng dụng cần có cơ chế đồng bộ giữa **orders_by_customer_day** và **order_lookup_by_id** theo nghiệp vụ (event-driven, dual write được thiết kế cẩn thận, idempotent projection hoặc reconciliation). **Không có transaction ACID đa partition** tự động chỉ nhờ thêm bảng. Ngoài ra, khi một khách hàng có số order cực lớn, partition theo **customer_id** trong bảng lookup có thể tăng lớn; cần đánh giá cardinality/tải và có thể chọn **((customer_id, order_id))** hoặc bucket khác cho truy vấn point lookup.

### 8.4. Phân biệt “chạy lại” với “lần đầu hoàn thành”

Một migration có thể dừng giữa chừng: CREATE TABLE thành công nhưng bước kiểm chứng/checksum ledger thất bại. Khi chạy lại:

- Không mặc định chạy tiếp từ trạng thái ban đầu.
- Kiểm tra **precondition và postcondition thật** trên cluster.
- Chỉ đánh dấu hoàn thành khi schema phù hợp.
- Nếu một bước trước đó đã chạy nhưng có schema sai, cần dừng và phê duyệt hướng sửa.
- Không chỉnh nội dung migration đã apply rồi giữ nguyên version; thay bằng **migration tiếp theo** có changelog rõ.

**IF NOT EXISTS không phải migration transaction hoặc distributed lock.** Nó giảm lỗi “đối tượng đã có”, chứ không xác minh tính tương thích schema hoặc hoàn nguyên các bước thất bại.

## 9. Migration ledger, checksum và công cụ thực thi

Một quy trình migration có thể lưu lịch sử các lần đã áp dụng, ví dụ:

~~~sql
-- Minh họa ledger riêng nếu tổ chức tự xây runner.
CREATE TABLE IF NOT EXISTS commerce.schema_migrations (
    version text PRIMARY KEY,
    checksum text,
    applied_at timestamp,
    description text,
    applied_by text
);
~~~

Ledger chỉ giúp **theo dõi/audit**, không phải nguồn sự thật duy nhất. Phải đối chiếu **system_schema** và hậu điều kiện của từng DDL.

### 9.1. Vì sao một hàng ledger không làm DDL atomic?

Giả sử runner làm:

~~~text
1. INSERT version='V002' IF NOT EXISTS trong ledger
2. ALTER TABLE ... ADD fulfillment_channel
3. Ghi kết quả hoàn thành
~~~

Nếu process chết giữa bước 1 và 2, ledger có thể nói migration đã được nhận nhưng DDL chưa thực hiện. Nếu đảo thứ tự **ALTER trước rồi INSERT ledger**, process vẫn có thể chết giữa hai bước. Cassandra không cung cấp transaction atomic bao trùm **schema change + ledger row**.

**Thiết kế đáng tin cậy hơn:**

1. Serialize runner bằng **orchestrator lock** hoặc cơ chế điều phối đã phê duyệt.
2. Ghi **intention/attempt** vào audit riêng, không coi đó là COMPLETE.
3. Kiểm tra precondition.
4. Thực thi DDL trong thứ tự cố định.
5. Chờ và kiểm tra schema agreement theo tiêu chí được duyệt.
6. Xác minh postcondition trên metadata và CQL smoke test.
7. Chỉ khi đạt mới ghi **APPLIED** kèm checksum/version.
8. Nếu job chết giữa chừng, runner sau **đọc lại cluster schema** rồi quyết định resume/fix, không mù chạy lại.

Không tự xây một distributed lock bằng LWT rồi tin rằng lock đó đồng thời bảo vệ mọi DDL nhiều node. Nếu dùng lock, phải có lease/fencing/owner và xử lý trường hợp mất kết nối, lock stale, process chết; đơn giản hơn là dùng **một pipeline executor duy nhất**.

### 9.2. Chọn công cụ phù hợp Cassandra, không giả định JDBC migration

Một số hệ sinh thái có công cụ migration hỗ trợ **CQL**, extension cho Liquibase hoặc runner được viết riêng. Khả năng hỗ trợ Cassandra của từng tool/extension phụ thuộc phiên bản.

**Không mặc định rằng Flyway/Liquibase JDBC phổ biến cho relational database có thể chạy trực tiếp trên Cassandra mà không cần connector/extension và thử nghiệm.** Cần xác minh:

- Hỗ trợ phiên bản Cassandra/driver/JDK và authentication/TLS.
- Cách thực thi file nhiều statement; cách nhận biết câu CQL đã lỗi.
- Chờ schema agreement và retry DDL theo ngữ nghĩa nào.
- Checksum, version order, audit và xử lý migration thất bại một phần.
- Có làm thay đổi keyspace/role ngoài phạm vi không?
- Có thể chạy dưới một Kubernetes Job hoặc pipeline step duy nhất không?

Nếu dùng **cqlsh -f** làm runner đơn giản trong lab, không chỉ dựa vào exit code mà bỏ qua log và postcondition. Hành vi báo lỗi/cơ chế ngừng khi có lỗi có thể khác theo bản cqlsh; trong production cần wrapper/runner đã được kiểm thử.

## 10. Expand–migrate–switch–contract trong rolling deployment

Một hệ thống production hiếm khi có thể tắt toàn bộ API, sửa schema và bật tất cả phiên bản mới cùng lúc. Cần xử lý lúc **app v1 và v2 cùng tồn tại**.

~~~mermaid
flowchart TD
    A["Bước 0: app v1 + schema S1"] --> B["EXPAND: chạy migration tạo S2 tương thích v1"]
    B --> C["VERIFY: schema agreement, metadata, smoke tests"]
    C --> D["DEPLOY: app v2 đọc được cả dữ liệu cũ/mới"]
    D --> E["BACKFILL: ghi bổ sung có giới hạn và đối soát"]
    E --> F["SWITCH: chuyển reader/writer sang schema mới"]
    F --> G["OBSERVE: không còn consumer v1"]
    G --> H["CONTRACT: cleanup/drop có phê duyệt riêng"]
~~~

### 10.1. Bước expand: thêm trước, không phá schema cũ

- Thêm **cột mới nullable** hoặc **bảng mới**.
- Không đổi tên/xóa ngay cột cũ nếu app v1 còn đọc.
- Không thay partition/clustering key của bảng đang dùng.
- Đợi schema được nhận biết và xác minh cả reader/writer cũ.
- Nếu thêm UDT field, kiểm tra mapper/codec của mọi app version và dữ liệu null.

Đối với Cassandra, **thay primary key** thường cần bảng mới với khóa khác, không phải ALTER trong cùng bảng. Vì schema gắn chặt với phân vùng dữ liệu, phải đo token distribution, partition size và consistency cho bảng mới.

### 10.2. Bước deploy: app v2 chịu được trạng thái chuyển tiếp

Ví dụ v2 dùng trường **fulfillment_channel**:

~~~java
// Ý tưởng nghiệp vụ trong bản ứng dụng v2:
String channel = row.getString("fulfillment_channel");
if (channel == null) {
    channel = "LEGACY";
}
~~~

Đây là đoạn minh họa cách xử lý **row cũ thiếu cột mới**, không phải repository implementation hoàn chỉnh. Phải bảo đảm DDL đã chạy trước khi query **tham chiếu** cột mới; xử lý null chỉ giúp dữ liệu cũ chưa có giá trị, **không giúp query chạy trên schema chưa có cột**.

### 10.3. Backfill: quá trình dữ liệu riêng với DDL

Khi cần điền dữ liệu cột mới, chạy job có:

- **Nguồn dữ liệu có thể xác minh** cho từng row, không tự bịa giá trị nếu cần invariant.
- Partition key và clustering columns đầy đủ khi UPDATE.
- **Rate limit/concurrency bound** để không làm quá tải hot partition.
- Checkpoint, idempotency và retry budget.
- Đối soát row count, sampled fixtures và invariant giữa bảng cũ/mới.
- Theo dõi disk I/O, GC, compaction/tombstones, repair/streaming.
- Phương án tiếp tục từ lỗi và phân biệt complete/incomplete.

**Không coi backfill là một lệnh ALTER TABLE.** DDL thường nhỏ về câu lệnh nhưng tác động metadata; backfill là tải dữ liệu thực, có thể kéo dài hàng giờ và ảnh hưởng SLA.

### 10.4. Switch: chuyển nơi đọc/ghi

Khi dữ liệu đã đủ, có thể:

1. Bật **dual read/compare** để đối chiếu dữ liệu cũ/mới theo tỷ lệ có kiểm soát.
2. Đưa các writer mới vào hoạt động và bảo đảm idempotency.
3. Chuyển reader dần qua feature flag.
4. Giữ khả năng đọc đường cũ trong cửa sổ tương thích.
5. Chạy reconciliation khi có sai lệch.
6. Chỉ khi tất cả client/consumer cũ đã ngừng mới xem xét contract.

**Dual write** tự thân có failure modes: một bảng ghi thành công, bảng kia timeout. Phải thiết kế event/outbox, idempotent retry hoặc reconciliation; không tự coi hai INSERT thành một transaction phân tán.

### 10.5. Contract: bước phá hủy có cổng phê duyệt riêng

Sau khi đã xác minh không còn consumer cũ:

- Có thể bỏ field/bảng/index không còn dùng theo thủ tục CQL được hỗ trợ.
- DDL drop/alter destructive phải có **recovery point, backup/restore drill, thời gian retention và change approval**.
- Đánh giá tombstone, compaction và disk trước khi thao tác lớn.
- Không coi rollback application là đủ sau khi đã drop column/table.

Một **contract migration** không nên chạy cùng lúc deploy app v2 nếu app v1 vẫn có thể tồn tại trong rolling rollout hoặc rollback window.

## 11. Thứ tự triển khai: migration trước, app sau, cleanup cuối

Một kế hoạch điển hình:

| Giai đoạn | Actor | Điều kiện vào | Điều kiện ra |
|---|---|---|---|
| **0. Review** | DBA/SRE + Java owners | CQL diff, version matrix, backup và KPI | Change được duyệt |
| **1. Preflight** | Migration runner | Cluster khỏe, RF/DC/CL đủ, secrets hợp lệ | Có baseline và recovery path |
| **2. Apply expand migration** | **Một** migration job | Không có runner khác, schema precondition đạt | DDL áp dụng, log/audit có |
| **3. Verify schema** | Job + smoke tests | Schema agreement và system_schema phù hợp | CQL old/new fixture PASS |
| **4. Deploy app** | CD orchestrator | App v2 compatible cả trạng thái cũ/mới | Canary/rolling deployment PASS |
| **5. Backfill/switch** | Data job + app team | Capacity đủ, idempotency/rollback kế hoạch | Dữ liệu đối soát, traffic chuyển |
| **6. Contract** | Migration runner + DBA | Không còn reader/writer cũ, recovery approved | Cleanup PASS, backup/restore kiểm tra lại |

### 11.1. Nếu migration thất bại trước deploy

- **Không deploy** phiên bản phụ thuộc cột/bảng mới.
- Giữ app v1 đang chạy nếu vẫn tương thích với trạng thái schema hiện tại.
- Xem lại DDL đã áp dụng một phần; xác minh metadata từng đối tượng.
- Chọn fix-forward migration an toàn hoặc restore khi có mất dữ liệu/điểm một chiều, theo runbook.
- Ghi rõ trạng thái **BLOCKED**, owner, bằng chứng và điều kiện chạy lại.

### 11.2. Nếu app v2 fail nhưng schema đã expand

Trong một thay đổi additive đúng thiết kế, thường có thể **rollback application về v1** trong khi **giữ cột/bảng mới chưa dùng**. Nhưng phải kiểm tra:

- App v1 có đọc/ghi bình thường khi cột mới tồn tại không?
- App v2 đã ghi dữ liệu mới mà v1 không hiểu hoặc làm thay đổi logic nghiệp vụ chưa?
- Đã đổi feature flag hoặc ghi vào bảng mới chưa? Có cần reconciliation không?
- Không có bước contract/destructive nào chạy trước đó chứ?
- RPO/RTO và backup còn đáp ứng cam kết không?

**Rollback code không đồng nghĩa rollback dữ liệu/schema.** Việc để lại cột additive tạm thời thường an toàn hơn cố drop ngay trong incident, nhưng phải được xác minh trên version cụ thể.
## 12. Schema agreement và hậu điều kiện: migration chạy xong chưa đủ

Cassandra phân phối schema metadata giữa nhiều node. Sau DDL, có thể có khoảng thời gian các node chưa đồng ý cùng một schema version. Vì vậy, một migration chỉ được đánh dấu thành công sau khi **đúng cấu trúc và trạng thái schema agreement đã đạt yêu cầu**.

### 12.1. Kiểm tra bằng CQL metadata

Kiểm tra replication của keyspace:

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'commerce';
~~~

Kiểm tra bảng tồn tại:

~~~sql
SELECT keyspace_name, table_name
FROM system_schema.tables
WHERE keyspace_name = 'commerce'
  AND table_name = 'orders_by_customer_day';
~~~

Kiểm tra tên/kiểu/vị trí cột:

~~~sql
SELECT column_name, kind, position, type
FROM system_schema.columns
WHERE keyspace_name = 'commerce'
  AND table_name = 'orders_by_customer_day';
~~~

Những câu SELECT này kiểm tra **metadata mà node đang kết nối nhìn thấy**. Chúng không tự chứng minh mọi node đã thống nhất. Trên một cluster phân tán cần kiểm tra **schema agreement** theo API/công cụ đúng version và đối chiếu log/metrics từ các node.

### 12.2. Lệnh quan sát trên node

~~~bash
# Node UP/DOWN và phân bố DC/rack.
nodetool status

# Thông tin schema agreement/versions theo công cụ có ở phiên bản.
nodetool describecluster

# Thông tin công việc nền để đánh giá tác động deployment.
nodetool tpstats
nodetool compactionstats

# Sau khi deploy/query, kiểm tra bảng phục vụ workload.
nodetool tablestats commerce.orders_by_customer_day
~~~

**nodetool describecluster** có thể hiển thị thông tin schema versions theo phiên bản; không áp đặt cách parse output cố định. Nếu node không thống nhất hoặc unreachable, không tuyên bố đã kiểm chứng toàn cluster chỉ vì một câu SELECT từ coordinator thành công.

**Nếu schema disagreement kéo dài:** giữ pipeline ở PAUSE, kiểm tra node health, gossip/network, log schema và version compatibility. Không vội restart toàn cluster hoặc chạy lệnh repair để “sửa schema”. **Repair dữ liệu** không phải công cụ thay thế cho xử lý schema agreement.

### 12.3. Hậu điều kiện phải bao gồm ý nghĩa, không chỉ tên

Một bảng có thể tồn tại nhưng không đúng thiết kế. Với **orders_by_customer_day**, cần xác minh:

- Partition key đúng **customer_id + order_day** với đúng thứ tự.
- Clustering key đúng **created_at + order_id** và thứ tự DESC/ASC như spec.
- **amount** có kiểu decimal, **status** kiểu text.
- **fulfillment_channel** có kiểu text sau V002.
- Keyspace dùng replication strategy và RF/DC đã được duyệt.
- Bảng/index/UDT và các table options liên quan khớp migration.
- Runtime role có quyền cần thiết và không được quyền DDL dư thừa.
- Driver và Spring Data mapping đọc/ghi được qua prepared CQL trên ít nhất các key fixture.

Nếu chỉ kiểm tra **table_name** thì một bảng có partition key sai vẫn có thể vượt gate, rồi gây lỗi query hoặc hotspot trong production.

## 13. Spring Boot chỉ kiểm tra contract, không sửa schema

Sau khi migration job đã chạy và xác minh metadata, ứng dụng vNext có thể làm một **lightweight compatibility check** ở quá trình deploy/readiness. Điều này khác hẳn với “tự tạo schema”.

Ví dụ Spring bean kiểm tra tồn tại cột cần thiết qua Java Driver metadata:

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.metadata.schema.TableMetadata;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public final class CassandraSchemaContractCheck
        implements ApplicationRunner {

    private final CqlSession session;

    public CassandraSchemaContractCheck(CqlSession session) {
        this.session = session;
    }

    @Override
    public void run(ApplicationArguments args) {
        CqlIdentifier commerce =
            CqlIdentifier.fromCql("commerce");
        CqlIdentifier tableName =
            CqlIdentifier.fromCql("orders_by_customer_day");

        TableMetadata table = session.getMetadata()
            .getKeyspace(commerce)
            .flatMap(ks -> ks.getTable(tableName))
            .orElseThrow(() -> new IllegalStateException(
                "Schema contract chưa tồn tại: commerce.orders_by_customer_day"));

        if (!table.getColumns().containsKey(
                CqlIdentifier.fromCql("status"))) {
            throw new IllegalStateException(
                "Thiếu cột status theo schema contract");
        }
    }
}
~~~

**Giới hạn của ví dụ:**

- Đây là **read-only check** thông qua driver metadata, không gửi DDL.
- Driver metadata có thể chưa phản ánh ngay schema vừa cập nhật nếu các node chưa đồng ý hoặc session chưa nhận sự kiện schema; vì vậy migration job vẫn cần gate schema agreement riêng.
- Kiểm tra **status** tồn tại mới chỉ là kiểm tra tối thiểu; production nên kiểm tra cả **DataType, primary key, clustering order, keyspace RF/replication** và các query quan trọng.
- Fail startup có thể phù hợp khi schema tối thiểu bắt buộc không có, nhưng nếu migration job chưa hoàn tất thì nên **chặn rollout ở pipeline** chứ không để hàng trăm pod crash-loop.
- Nếu startup check thực hiện query nặng hoặc liên hệ server quá thường xuyên ở mọi pod, chính nó cũng có thể tạo tải. Hãy ưu tiên kiểm chứng mạnh trong migration job và readiness phù hợp.
- Mỗi class Java có package/import hợp lệ trong dự án thật; code giả định Spring Boot auto-configuration tạo bean CqlSession phù hợp.

### 13.1. Application context thành công chưa phải kiểm chứng dữ liệu

Một Spring Boot context có thể mở CqlSession và tạo repository bean, nhưng chưa thực hiện một SELECT/INSERT thực tế. Một số lỗi chỉ xuất hiện sau khi gọi method:

- Column không tồn tại hoặc sai kiểu.
- Query thiếu partition key hoặc cần bảng theo access pattern khác.
- **CodecNotFoundException** với UDT/collection mapping.
- **Unavailable/ReadTimeout** do RF/CL và trạng thái replica.
- Credential runtime không có SELECT/MODIFY.
- Dữ liệu cũ null nhưng code mới dùng primitive hoặc validation không cho null.

Do đó **smoke test bằng prepared CQL thật** trên dữ liệu tổng hợp được phép là cổng triển khai quan trọng.

## 14. Ví dụ CQL và Java kiểm chứng sau migration

### 14.1. Query fixture sau V002

~~~sql
-- Truy vấn một partition đã biết, không quét toàn bảng.
SELECT created_at, order_id, status, amount,
       fulfillment_channel
FROM commerce.orders_by_customer_day
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-21'
LIMIT 20;
~~~

Khi chưa backfill, **fulfillment_channel** của row cũ có thể null. Điều này **không tự chứng minh migration thất bại** nếu contract cho phép null trong giai đoạn chuyển tiếp.

### 14.2. Java Driver smoke test trong môi trường lab

~~~java
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class OrderSchemaSmoke {
    private final CqlSession session;

    public OrderSchemaSmoke(CqlSession session) {
        this.session = session;
    }

    public void check() {
        UUID customerId = UUID.fromString(
            "11111111-1111-4111-8111-111111111111");
        LocalDate day = LocalDate.of(2026, 11, 21);

        PreparedStatement query = session.prepare(
            "SELECT order_id, status, fulfillment_channel " +
            "FROM commerce.orders_by_customer_day " +
            "WHERE customer_id = ? AND order_day = ? LIMIT ?");

        for (Row row : session.execute(
                query.bind(customerId, day, 20)
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM))) {
            if (row.getUuid("order_id") == null) {
                throw new IllegalStateException(
                    "Schema/data fixture thiếu order_id");
            }
            // Null hợp lệ trong giai đoạn chưa backfill.
            String channel = row.getString(
                "fulfillment_channel");
            if (channel != null && channel.isBlank()) {
                throw new IllegalStateException(
                    "fulfillment_channel rỗng không hợp lệ");
            }
        }
    }
}
~~~

**Điều kiện chạy:** đúng schema sau V002, RF/DC đủ cho LOCAL_QUORUM; data fixture phải được cài trong staging nếu muốn **assert** số row hoặc giá trị kỳ vọng. Đoạn trên chỉ xác minh query/mapping không lỗi và invariant tối thiểu, **không chứng minh mọi dữ liệu đã đúng hoặc toàn cluster đã đồng ý schema**.

Trong ứng dụng thật cần test **non-empty fixture** với order ID/trạng thái mong đợi, không coi kết quả 0 row là PASS. TLS/auth và secrets phải cấu hình đúng cho CqlSession của Spring Boot.

### 14.3. Backfill một hàng theo đầy đủ khóa

Chỉ minh họa một hàng fixture đã được xác minh tồn tại:

~~~sql
UPDATE commerce.orders_by_customer_day
SET fulfillment_channel = 'LEGACY'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-21'
  AND created_at = '2026-11-21T08:00:00Z'
  AND order_id = 22222222-2222-4222-8222-222222222222;
~~~

**Cassandra UPDATE có ngữ nghĩa upsert.** Nếu hàng không tồn tại, lệnh UPDATE có thể tạo dữ liệu mà app không mong muốn. Migration/backfill thật phải kiểm tra nguồn dữ liệu và target row bằng cơ chế phù hợp, dùng idempotent event IDs/checkpoint và không chạy UPDATE vô điều kiện trên khóa chưa xác minh.

Không dùng một CQL query **quét toàn bộ keyspace** rồi UPDATE hàng loạt ngay trong migration DDL. Tải backfill nên tách khỏi schema migration, dùng rate limit và theo dõi replica/disk/compaction.

## 15. Những thay đổi DDL Cassandra cần đặc biệt cẩn trọng

| Thay đổi | Có thể là expand/contract? | Rủi ro |
|---|---|---|
| **ALTER TABLE ADD** cột | Expand | Row cũ null, code mới không chịu null, schema propagation |
| **CREATE TABLE mới** theo truy vấn | Expand | Cần đồng bộ/backfill, partition size, dual-write divergence |
| **CREATE/ALTER TYPE** UDT | Expand nếu tương thích | Mapping/codec của Java clients khác version có thể fail |
| **CREATE INDEX** | Expand có điều kiện | Backfill index, resource load; không chữa mọi access pattern |
| **ALTER TABLE DROP** cột | Contract | Mất dữ liệu cột, app cũ fail, restore/rollback phức tạp |
| **DROP TABLE** | Destructive | Mất bảng/dữ liệu; không tự phục hồi từ replica |
| **TRUNCATE** | Destructive | Xóa dữ liệu ở phạm vi lớn, khó hoàn tác |
| **Thay partition/clustering key** | Thường cần bảng mới | Repartition/backfill và thay query, không phải ALTER đơn giản |
| **Đổi compaction/TTL options** | Cần đánh giá riêng | Tải nền, tombstone, retention và disk I/O |
| **Thay RF/DC keyspace** | Thay đổi hạ tầng dữ liệu | Bố trí replica, repair/streaming/capacity, availability |

Đây là **bảng đánh giá phương pháp**, không khẳng định mọi DDL tương thích giữa mọi phiên bản. Đặc biệt, **DROP rồi ADD lại cùng tên** có thể có rủi ro lịch sử schema/tombstone và phiên bản; không tự “revert” cột bằng cách thêm tên cũ mà không có hướng dẫn cụ thể.

### 15.1. TTL, tombstone và compaction

Nếu một thay đổi DDL đặt **default_time_to_live** hoặc thay retention, row có thể hết hạn theo chính sách khác. Hành vi tombstone/compaction và thời gian phục hồi ảnh hưởng tới dữ liệu, disk và repair.

**Không dùng ALTER TABLE để che truy vấn chậm** mà chưa đo partition distribution, SSTable count, tombstone và I/O. Thay compaction strategy có thể cần thời gian/capacity và giám sát riêng; không gộp với deploy phiên bản Java mới nếu không có lý do rõ.

### 15.2. UDT và collection

UDT giúp nhóm dữ liệu có cấu trúc nhưng vẫn ràng buộc kiểu CQL; thay UDT field trong lúc nhiều version Java đang chạy có thể làm một số custom codec không tương thích. Collection lớn hoặc frozen structures gây mutation nặng và áp lực compaction; schema action tự động không quyết định giới hạn nghiệp vụ của collection.

### 15.3. Primary key là thiết kế vật lý, không phải annotation trang trí

Nếu app cần từ query **orders_by_customer_day** sang **orders_by_status** trên toàn tenant, chỉ thêm repository method **findByStatus** vào entity hiện tại không làm Cassandra tự xuất hiện index/truy vấn tối ưu. Cần:

1. Xác định access pattern và cardinality.
2. Thiết kế bảng hoặc index thích hợp theo version/features đã hỗ trợ.
3. Chạy migration tạo schema.
4. Backfill/dual write/reconciliation có giới hạn.
5. Đổi Spring repository/query code sau khi dữ liệu sẵn sàng.

Không bật ALLOW FILTERING hay scan toàn cluster làm đường tắt “đỡ phải migration” cho workload sản xuất.

## 16. Schema drift: khi database và repository khác nhau

**Schema drift** là trạng thái schema production không còn khớp với contract/migration đã duyệt: ai đó ALTER thủ công, job áp thiếu version, hoặc một ứng dụng cũ đã tạo bảng khác cấu trúc.

### 16.1. Dấu hiệu drift

- Cùng migration version nhưng checksum CQL khác giữa hai bản deploy.
- **system_schema.columns** không khớp tập DataType/primary-key kỳ vọng.
- Một datacenter/node chưa có schema mới.
- Một môi trường staging khác production vì chạy **CREATE_IF_NOT_EXISTS** lâu ngày.
- App mới báo unknown column/invalid query, trong khi app cũ vẫn hoạt động.
- Tên bảng đúng nhưng options/RF khác.
- Một bản deploy đã rollback code nhưng migration vẫn ở version mới.

### 16.2. Xử lý drift an toàn

1. **Dừng migration mới**, chụp lại metadata hiện tại và trạng thái node.
2. Xác định đã có dữ liệu nghiệp vụ mới được ghi theo schema lệch chưa.
3. So contract, checksum, schema versions và logs từng lần apply.
4. Không tự chạy RECREATE/DROP để “đưa về đúng”.
5. Lập migration **fix-forward** có pre/postcondition hoặc kế hoạch restore cô lập nếu có mất dữ liệu.
6. Kiểm tra app cũ/mới và dữ liệu theo partition key.
7. Chỉ cập nhật migration ledger khi trạng thái thật đã được xác minh.

Tránh sửa trực tiếp **system_schema** hoặc các bảng metadata hệ thống như một cách làm “schema đồng bộ”. DDL phải đi qua cơ chế Cassandra được hỗ trợ.

## 17. Tình huống triển khai có timeline

Giả sử dịch vụ đang chạy **app v1** đọc bảng orders_by_customer_day với hai cột nghiệp vụ **status** và **amount**. App v2 cần trường **fulfillment_channel**. Cluster có ba node ở local dc1, RF = 3, endpoint quan trọng dùng **LOCAL_QUORUM**.

| Mốc giả định (UTC) | Hành động | Gate |
|---|---|---|
| 09:00 | Kiểm tra backup, RF/DC, schema và SLO baseline | GO nếu preflight PASS |
| 09:10 | Một migration job chạy V002 ADD COLUMN | Không có runner khác |
| 09:12 | Verify metadata, schema agreement và CQL SELECT | PASS trước app v2 |
| 09:20 | Deploy một canary app v2 | Không có unknown column/codec/timeout bất thường |
| 09:30 | Canary đọc row cũ có channel null đúng fallback | PASS correctness |
| 09:40 | Tiếp tục rolling deploy app v2 | CL/latency/replica healthy |
| 10:10 | Chạy backfill đã rate-limit | Không vượt resource/error budget |
| 11:00 | Đối soát, bật feature flag đọc channel mới | PASS theo dữ liệu đã backfill |
| Những ngày sau | Xem xét contract nếu còn đối tượng cũ không dùng | Approval/backup riêng |

**Thời điểm là minh họa**, không phải bảo đảm rằng DDL/schema agreement luôn chỉ mất hai phút. Một migration phải chờ được kiểm tra qua điều kiện thực, không dùng sleep cố định làm bằng chứng.

### 17.1. Nếu canary fail lúc 09:20

Một lỗi **CodecNotFoundException** xuất hiện do Spring Data mapping của v2 dùng enum custom codec chưa được cấu hình.

**Quyết định:** Dừng rollout v2; giữ schema đã ADD cột nếu v1 vẫn tương thích. Sửa codec/dependency và test lại, hoặc rollback ứng dụng v2 về v1. **Không DROP cột mới theo phản xạ**, vì schema ADD có thể không phải nguyên nhân và các ghi đã phát sinh cần được đối soát.

### 17.2. Nếu DDL bị timeout lúc 09:10

Migration runner mất phản hồi sau ALTER TABLE; không biết schema đã áp trên những node nào.

**Quyết định:** Dừng bước tiếp, kiểm tra **system_schema/metadata/schema agreement** và logs, không gửi lệnh ALTER lần nữa ngay lập tức. Khi đã xác minh precondition/postcondition, có thể cập nhật ledger hoặc chạy một **fix-forward migration** được duyệt.

### 17.3. Nếu backfill gây quá tải lúc 10:10

p99 read/write tăng mạnh, compaction pending và Java service có ReadTimeout/Overloaded.

**Quyết định:** Pause/throttle backfill, không tự hạ consistency level hoặc retry hàng loạt. Theo dõi disk/GC/partition, giảm request in-flight, dùng checkpoint để tiếp tục sau. DDL đã apply không có nghĩa job backfill phải chạy hết bằng mọi giá.

## 18. Rollback, downgrade và khôi phục dữ liệu

**Rollback application**, **rollback một CQL migration** và **restore dữ liệu** là ba việc khác nhau.

| Tình huống | Lựa chọn thường khả thi | Điều cần cảnh giác |
|---|---|---|
| Thêm cột nullable, app v2 lỗi, v1 vẫn dùng được | Rollback app về v1, giữ schema additive | Ghi từ v2 và logic mới có thể đã thay đổi dữ liệu |
| Thêm bảng lookup, sync chưa hoàn thành | Tắt feature flag đọc bảng mới, tiếp tục reconciliation | Không giả định lookup đã đủ |
| DROP cột/bảng chứa dữ liệu | Có thể cần restore/khôi phục từ nguồn độc lập | Không có DDL transaction rollback tự động |
| Thay primary key qua bảng mới | Quay reader về bảng cũ nếu vẫn còn dữ liệu đúng | Dual-write và dữ liệu mới cần đối soát |
| Chuyển compaction/TTL hoặc RF | Dùng runbook phiên bản/topology | Các thao tác nền có thể kéo dài và tiêu tốn tài nguyên |
| Cluster vừa nâng phiên bản Cassandra và chạy DDL mới | Xem compatibility/downgrade guide | Binary cũ có thể không hiểu SSTable/schema mới |

### 18.1. Một restore point tốt cần gì?

Trước một bước phá hủy:

- Backup/snapshot đầy đủ phạm vi node/token và bảng/UDT liên quan.
- Schema CQL, manifest/checksum, Cassandra version và khóa giải mã.
- Recovery point/cutoff được ghi rõ.
- Bản backup độc lập với miền lỗi production, quyền đọc/restore đã thử.
- Diễn tập restore trên cluster cô lập và đối soát dữ liệu qua nhiều partition.
- Cách xử lý ghi hợp lệ sau cutoff, **RPO/RTO** được thông báo.

Replication không thay thế backup. DDL DROP/DELETE sai có thể được thấy bởi cả các replica; **repair không phục hồi phiên bản dữ liệu đã bị xóa hợp lệ theo cơ chế Cassandra**.

### 18.2. Contract là bước nên trì hoãn

Một chiến lược an toàn: sau khi v2 chạy ổn và đã hết rollback window của v1, mới đánh giá drop bảng/cột cũ ở một change window khác. Có thể cần thêm chu kỳ retention/audit và kiểm tra client ngoài Spring Boot (batch, Java driver trực tiếp, BI, CDC). **Không xóa chỉ vì một repository Java không còn tham chiếu.**

## 19. Ma trận kiểm thử migration với nhiều phiên bản ứng dụng

Đối với migration **thêm cột**, cần kiểm chứng từng tổ hợp:

| App | Schema S1 chưa ADD cột | Schema S2 đã ADD cột | Mục tiêu |
|---|---|---|---|
| **v1** không biết cột mới | Chạy đúng | **Phải tiếp tục chạy đúng** | Rollback app v2 còn đường về |
| **v2** tham chiếu cột mới | Có thể lỗi unknown column, **không deploy** | Chạy đúng với dữ liệu null/cũ | Cần gate migration trước deploy |
| **v2** sau backfill | Không phù hợp | Đọc dữ liệu mới và cũ theo contract | Đối soát và xác nhận ready |
| **Batch/job cũ** | Chạy đúng | Phải được kiểm thử | Không bỏ qua client ngoài Spring |
| **App vNext sau contract** | Không hỗ trợ schema cũ | Chỉ chạy sau contract được phê duyệt | Phải hết rollback window |

**Đừng chỉ kiểm thử app v2 + schema S2**. Bài toán khó nhất thường là **app v1 + schema S2** trong rolling deployment và rollback.

### 19.1. Các lớp test

**Unit tests:**

- Mapping kiểu Java: UUID, LocalDate, Instant, BigDecimal, nullable fields.
- Quy tắc tính bucket/partition key và ngữ nghĩa null/UNSET.
- Feature flag fallback, idempotent projection và reconciliation.

**Integration tests với Cassandra lab:**

- Chạy migration V001 → V002 → V003 trên cluster/version tương thích.
- Kiểm tra schema metadata, DataType, partition/clustering key và UDT nếu dùng.
- Đọc/ghi bằng Spring Data repository và Java Driver prepared statements.
- Cả app v1 và v2 dùng schema S2, gồm row cũ thiếu cột mới.
- Kiểm tra LOCAL_QUORUM theo RF/DC của lab, không suy từ một node sang ba replica.
- Thử migration thất bại một phần và chạy lại sau postcondition.
- Thử quyền: runtime không được DDL, migration identity chỉ có quyền được phê duyệt.

**Staging/load tests:**

- Một migration job chạy khi app v1 vẫn đang phục vụ, dưới tải đại diện.
- Schema agreement và health gate trước triển khai canary.
- Backfill có rate limit, không gây ReadTimeout/Overloaded/compaction backlog ngoài ngưỡng.
- Monitoring latency, repair/streaming, disk và memory.
- Rollback app v2 về v1 mà không phải chạy destructive DDL.
- Restore drill cho thay đổi contract/destructive đã lên kế hoạch.

### 19.2. Ba loại test không thay thế nhau

- Một **context-load test** chỉ biết Spring Boot tạo bean, không xác minh dữ liệu CQL.
- Một **repository save/find** chứng minh một path, không chứng minh tất cả partition/tombstone/TTL/row cũ.
- Một **migration test** trên một node không chứng minh schema agreement và replication của multi-DC production.

Cần ghi rõ **phạm vi chứng cứ**: server/driver/JDK version, số node/DC, RF, CL, dataset, query shape, thời gian, kết quả và các giới hạn chưa kiểm tra.

## 20. Các anti-pattern thường gặp

| Anti-pattern | Vì sao nguy hiểm | Hướng thay thế |
|---|---|---|
| **schema-action: recreate** trong production | Có thể drop/recreate, gây mất dữ liệu | **none** + migration độc lập |
| **create-if-not-exists** được coi là migration đầy đủ | Không bảo đảm schema hiện tại khớp contract | Versioned CQL + postcondition |
| Tất cả pods chạy ALTER khi startup | Race và khó quản lý quyền/history | Single migration job trước deploy |
| Migration runner chạy song song ở hai pipeline | DDL xung đột, ledger race | Serialization/lock có owner |
| Chỉ ghi ledger rồi tin “APPLIED” | DDL và ledger không atomic | Kiểm chứng metadata và hậu điều kiện |
| Sửa file migration đã apply nhưng giữ version | Checksum không khớp, lịch sử mất tính tin cậy | Thêm migration mới để fix-forward |
| Mặc định app runtime có quyền DROP/ALTER | Rủi ro do bug/cấu hình tấn công | Least privilege và secret riêng |
| App v2 tham chiếu cột trước DDL | Unknown column/prepare error | Expand migration trước deploy |
| DROP cột ngay khi app v2 lên canary | App v1 còn chạy/rollback fail | Contract sau compatibility window |
| Đổi primary key bằng sửa annotation | Cassandra table không tự repartition | Bảng mới, backfill, switch |
| Backfill trong startup bean | Nhiều pods duplicate work, quá tải | Data job riêng, checkpoint/rate limit |
| Đổi RF trong application.yml | App config không tạo kế hoạch replica | DBA/SRE kiểm soát keyspace topology |
| Dùng ALLOW FILTERING thay migration bảng mới | Scan tốn tài nguyên, latency thất thường | Thiết kế bảng theo access pattern |
| Chỉ kiểm tra bảng tồn tại | Table có thể sai type/PK/options | Compare full schema contract |
| Tự sửa system_schema khi disagreement | Phá metadata và hỗ trợ vận hành | Dùng cơ chế DDL/diagnostics chính thức |
| Gộp DROP vào release có thể rollback | Không còn đường về khi app v1 chạy lại | Expand-contract nhiều đợt |
| Dùng repair để hoàn tác DELETE/DDL sai | Repair đồng bộ replica, không biết nghiệp vụ | Backup/restore/reconciliation có kiểm soát |

## 21. Bài tập thực hành và hướng giải

### Bài 1 — SchemaAction nào cho production?

Dịch vụ Spring Boot có 12 pods, bảng Cassandra đã chứa dữ liệu thật. Team muốn startup tự tạo và sửa schema, đề xuất **RECREATE** để môi trường luôn giống entity Java.

**Câu hỏi:** Có phù hợp không? Cần cấu hình gì?

**Đáp án gợi ý:** Không. RECREATE có rủi ro phá hủy dữ liệu. Cấu hình **schema-action: none** cho runtime, quản lý CQL qua migration job riêng, chạy test và phê duyệt trước khi app vNext deploy.

### Bài 2 — Vì sao IF NOT EXISTS không đủ?

Một môi trường đã có bảng **orders_by_customer_day**, nhưng **amount** đang là **text** thay vì **decimal**. Migration dùng **CREATE TABLE IF NOT EXISTS** với schema đúng.

**Câu hỏi:** Có thể báo migration thành công vì lệnh không lỗi?

**Đáp án gợi ý:** Không. Bảng hiện có có thể được giữ nguyên với kiểu sai. Phải kiểm tra **system_schema.columns**, primary key/table options và thiết kế fix-forward hoặc migration dữ liệu tương thích. IF NOT EXISTS không sửa schema lệch.

### Bài 3 — Thứ tự deploy app và DDL

App v2 đọc **fulfillment_channel**. App v1 không biết field này. Team deploy v2 trước, chờ tất cả pods lên rồi chạy ALTER TABLE ADD.

**Câu hỏi:** Rủi ro gì? Thứ tự phù hợp?

**Đáp án gợi ý:** v2 có thể fail khi prepare/query cột chưa tồn tại. Chạy **expand migration** trước, đợi schema agreement và smoke tests, sau đó canary v2; backfill/switch riêng, contract cuối cùng.

### Bài 4 — Rollback ứng dụng khi đã ADD cột

Sau khi V002 ADD cột và v2 canary, Spring mapper của v2 lỗi. App v1 đã được xác minh chạy bình thường với schema S2.

**Câu hỏi:** Có cần chạy DROP COLUMN để rollback không?

**Đáp án gợi ý:** Thường không. Có thể rollback **application** về v1, giữ cột additive cho đến khi sửa/deploy tiếp, tránh DDL phá hủy trong incident. Vẫn phải đối soát ghi v2 đã phát sinh.

### Bài 5 — Thay partition key

Bảng có **PRIMARY KEY ((customer_id, order_day), created_at, order_id)**. Yêu cầu mới cần tra cứu order theo **order_id** mà không biết ngày. Developer đổi annotation Java thành **@PrimaryKey orderId** và dùng **schema-action: create-if-not-exists**.

**Câu hỏi:** Có làm bảng cũ trở thành truy vấn theo orderId không?

**Đáp án gợi ý:** Không. Primary key quyết định phân vùng vật lý của Cassandra. Cần thiết kế bảng mới theo truy vấn, migration, backfill/dual write/reconciliation và chuyển API; không dùng ALLOW FILTERING làm giải pháp mặc định.

### Bài 6 — Hai pipeline cùng chạy V002

Một job chạy ALTER TABLE ADD cột thành công nhưng chết trước khi ghi ledger. Pipeline khác thấy thiếu APPLIED và chạy lại V002.

**Câu hỏi:** Lỗi thiết kế là gì? Phải làm gì?

**Đáp án gợi ý:** Runner chưa được serialize và chỉ dựa ledger; DDL và ledger không atomic. Dừng các runner trùng, xác minh metadata/postcondition, ghi lại audit/checksum khi trạng thái đúng, dùng orchestrator lock/owner cho lần sau.

### Bài 7 — Backfill gây Overloaded

V002 đã thành công. Backfill quét/gửi UPDATE hàng triệu row không giới hạn, gây p99 tăng từ 120 ms lên 1.800 ms và Overloaded.

**Câu hỏi:** Có nên tăng Spring driver timeout lên 10 giây?

**Đáp án gợi ý:** Không phải xử lý chính. Dừng hoặc throttle backfill, giới hạn in-flight/rate, dùng checkpoint theo khóa, điều tra disk/compaction/hot partition. Không giảm CL ngoài cam kết để che quá tải. Timeout chỉ cần hiệu chỉnh sau khi hiểu SLO và tải.

### Bài 8 — Quyền ứng dụng

App runtime chạy với một role có CREATE, ALTER, DROP trên toàn cluster vì migration từng được chạy trong một ApplicationRunner.

**Câu hỏi:** Nguy cơ và cách chỉnh?

**Đáp án gợi ý:** Lỗi code/credential leak có thể ảnh hưởng rộng; khó audit người thay đổi schema. Chuyển DDL sang job riêng có quyền tối thiểu theo keyspace, role runtime chỉ cần DML; xoay secret và ghi audit.

### Bài 9 — Schema agreement

Migration V002 trả kết quả thành công từ một coordinator, nhưng app v2 thỉnh thoảng nhận unknown column khi kết nối một số node.

**Câu hỏi:** Nguyên nhân có thể là gì? Gate nào thiếu?

**Đáp án gợi ý:** Schema có thể chưa được một số node nhận hoặc node/driver metadata chưa cập nhật; cần kiểm tra agreement, node health, driver/schema events và logs. Gate không chỉ là “DDL return success”.

### Bài 10 — Schema và dữ liệu cũ

App v2 có trường Java **fulfillmentChannel** và validation yêu cầu non-null. Các row từ v1 đều chưa có cột này.

**Câu hỏi:** Vì sao vẫn fail sau khi ALTER ADD thành công?

**Đáp án gợi ý:** Thêm cột không tự backfill giá trị. Cần fallback/nullable mapping, backfill có kiểm chứng và chỉ bật validation non-null sau khi dữ liệu đã được đối soát.

### Bài 11 — So sánh một test thiếu

Một integration test tạo 1 row, gọi repository.findById thành công trên cluster một node RF 1. Team tuyên bố đã kiểm tra migration production RF 3, LOCAL_QUORUM và rolling deployment.

**Câu hỏi:** Bằng chứng còn thiếu?

**Đáp án gợi ý:** Schema agreement đa node, RF/DC, quorum failures, cùng lúc app v1/v2, rollback, backfill, TLS/auth và performance dưới tải. Một node test chỉ chứng minh đường mapping/query hẹp.

### Bài 12 — DDL phá hủy không thể rollback chỉ bằng code

Một contract migration DROP bảng cũ ngay sau deploy v2. Sau đó v2 lỗi và cần rollback app v1 vẫn đọc bảng cũ.

**Câu hỏi:** Tại sao rollback code không đủ?

**Đáp án gợi ý:** Bảng đã mất; app v1 không thể đọc dữ liệu chỉ bằng đổi container image. Cần backup/restore hoặc nguồn dữ liệu khác, chịu RPO/RTO và downtime. Nên trì hoãn contract qua hết rollback window và phê duyệt riêng.

## 22. Checklist triển khai schema và Spring Boot

- [ ] Có **schema contract** chứa keyspace, RF/DC, primary key, clustering order, DataType, index/UDT, table options và quy tắc query.
- [ ] Đã đối chiếu phiên bản Spring Boot, Spring Data Cassandra, Cassandra và Java driver/JDK.
- [ ] Production đặt **spring.cassandra.schema-action: none** theo đúng namespace của bản Boot; kiểm tra effective configuration.
- [ ] Không có startup bean/runner tự thực thi DDL ở runtime.
- [ ] Role runtime không có CREATE/ALTER/DROP ngoài nhu cầu được duyệt.
- [ ] Migration job có identity/secret riêng, được serialize và có owner.
- [ ] Mọi migration có version, checksum, precondition, postcondition, audit và phê duyệt.
- [ ] Không chỉnh migration đã APPLIED; dùng migration tiếp theo để fix-forward.
- [ ] Không tin **IF NOT EXISTS** là schema diff hay transaction.
- [ ] Đã xác minh **schema agreement**, metadata đầy đủ và keyspace replication trước deploy.
- [ ] Đã chạy CQL/Java prepared smoke test với non-empty fixture và đúng CL/RF/DC.
- [ ] Entity annotation khớp composite partition key, clustering key, CQL types và null semantics.
- [ ] Expand migration không phá app v1 đang chạy trong rolling deployment.
- [ ] App v2 chịu được dữ liệu cũ, trường null và eventual rollout.
- [ ] Backfill/switch tách khỏi DDL, có rate limit, checkpoint, idempotency và reconciliation.
- [ ] Không dùng repository derived query thiếu partition key/ALLOW FILTERING để che thiết kế sai.
- [ ] Không gộp DROP/contract với canary nếu còn rollback window.
- [ ] Trước destructive DDL có backup đầy đủ, manifest/schema/khóa và restore drill.
- [ ] Có điều kiện PAUSE/STOP/ROLLBACK APP/FIX-FORWARD/RECOVER và người quyết định.
- [ ] Theo dõi p95/p99, Cassandra node health, errors, disk/GC, tombstone, compaction/repair khi migration/backfill chạy.
- [ ] TLS/auth/secrets/audit đúng và không log payload/credential thật.
- [ ] Đã thử migration lỗi giữa chừng, runner chạy trùng, app v1/v2 coexist và rollback.
- [ ] Chỉ đánh dấu APPLIED/GO khi hậu điều kiện và smoke test PASS; không chỉ vì script exit thành công.

## 23. Tổng kết

**SchemaAction** là cơ chế Spring Data Cassandra có thể tạo/tái tạo schema theo mapping trong quá trình khởi tạo ứng dụng. Nó có ích ở một số môi trường thử nghiệm, nhưng **không thay thế quy trình migration CQL có phiên bản** khi Cassandra đang chạy production nhiều instance, có dữ liệu thật và yêu cầu rollback an toàn.

Thiết kế nên tách **DDL migration job** khỏi **Spring Boot runtime**: migration có quyền và thời điểm chạy riêng, kiểm tra **schema agreement + postcondition**, ứng dụng dùng **schema-action NONE** và quyền DML tối thiểu. Với thay đổi dữ liệu, thực hiện **expand → deploy tương thích → backfill/đối soát → switch → contract** qua nhiều cổng phê duyệt, không xem DROP hoặc thay primary key là thay đổi Java annotation đơn giản.

Với Apache Cassandra, schema là một phần của kiến trúc phân tán: **partition key quyết định định tuyến, replication và consistency level quyết định điều kiện phục vụ, còn compaction/repair và dữ liệu tombstone ảnh hưởng tải khi migration/backfill**. Một quy trình tốt phải chứng minh được **dữ liệu đúng, ứng dụng v1/v2 tương thích, khả năng phục hồi và tính lặp lại có kiểm soát**, thay vì chỉ làm ứng dụng khởi động được.
