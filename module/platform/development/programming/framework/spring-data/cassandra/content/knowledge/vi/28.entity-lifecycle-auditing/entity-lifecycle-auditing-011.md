# Các đường ghi CQL trực tiếp cần kiểm tra phạm vi auditing trong Spring Data Cassandra

## 1. Một thay đổi dữ liệu thành công nhưng không có dấu vết người sửa

Ứng dụng Spring Boot dùng **Spring Data Cassandra** lưu trạng thái đơn hàng. Entity có các trường `createdAt`, `createdBy`, `updatedAt` và `updatedBy`. Khi gọi `repository.save(entity)`, lập trình viên quan sát thấy thời điểm và người sửa được điền tự động.

Sau đó, để tối ưu một API đổi trạng thái, nhóm phát triển chuyển sang câu CQL trực tiếp:

~~~sql
UPDATE app_ks.orders_by_id
SET state = 'PAID'
WHERE order_id = ?;
~~~

Mutation có thể được Cassandra chấp nhận nhưng `updated_at`, `updated_by` **vẫn mang giá trị cũ**. Việc đã bật các annotation auditing trên entity **không có nghĩa** database tự can thiệp vào mọi câu CQL được gửi từ bất kỳ nguồn nào.

Đó là chủ đề bài **“Các đường ghi CQL trực tiếp cần kiểm tra phạm vi auditing”** trong chương **Vòng đời và auditing**, thuộc module **SPRING_DATA_CASSANDRA**. Nội dung gắn với entity mapping, repository, `CassandraTemplate`, truy vấn CQL, thiết kế bảng theo truy vấn, partition key, consistency, paging và kiểm soát hiệu năng của hệ dữ liệu phân tán.

**Mục tiêu sau bài học:**

1. Phân biệt **auditing do Spring Data thực hiện trong mapping/callback pipeline** và **mutation CQL thực thi trực tiếp tại Cassandra**.
2. Lập danh sách các đường ghi như repository, template, `@Query`, `CqlSession`, asynchronous/reactive, batch, LWT và job ngoài ứng dụng.
3. Xác định lúc nào các annotation `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, `@LastModifiedBy` có thể được áp dụng; không suy diễn rằng mọi đường ghi đều đi qua chúng.
4. Thiết kế và bind **cột audit tường minh** ở những đường ghi CQL trực tiếp, không sửa `created_at` sai thời điểm.
5. Gắn kết audit với **conditional write/LWT**, `[applied]`, optimistic concurrency, retry và idempotency.
6. Nhận biết giới hạn của metadata audit hiện tại so với **nhật ký sự kiện bất biến** hoặc audit trail phục vụ pháp lý.
7. Viết test tích hợp chứng minh trường audit đúng **với từng đường ghi thực sự**.

## 2. Auditing trong ứng dụng khác audit trail độc lập

Từ **auditing** có thể chỉ những yêu cầu không giống nhau:

| Nhu cầu | Dữ liệu thường lưu | Có thể dùng vào việc gì? |
| --- | --- | --- |
| **Metadata của entity** | `created_at`, `created_by`, `updated_at`, `updated_by` | Biết trạng thái bản ghi hiện tại và thông tin ghi gần nhất |
| **Optimistic concurrency** | `version` | Phát hiện cập nhật trên phiên bản cũ |
| **Lịch sử thay đổi nghiệp vụ** | `command_id`, event type, actor, before/after hoặc delta | Truy lại nhiều thay đổi theo thời gian |
| **Audit trail tuân thủ/điều tra** | Dấu vết bất biến, nguồn danh tính, thời điểm, correlation, tính toàn vẹn | Điều tra, đối soát hoặc chứng minh một hành động |
| **Log kỹ thuật** | Request ID, query latency, exception | Gỡ lỗi, đo hiệu năng và giám sát |

**Một cột `updated_by` chỉ chứa người sửa gần nhất; nó không phải lịch sử đầy đủ.** Nếu B cập nhật sau A, giá trị A có thể không còn trong hàng hiện tại. Việc dùng `@LastModifiedBy` không tự ghi ra một bảng event riêng và cũng không tự mã hóa giá trị trước thay đổi.

**Nguyên tắc đầu tiên:** hãy viết rõ ứng dụng cần **metadata hiện tại** hay một **dòng sự kiện có thể truy vết**, rồi mới quyết định cơ chế.

### 2.1. Vì sao cần ranh giới auditing?

Spring Data là một **tầng ở phía ứng dụng**: nó có thể xử lý entity, lifecycle callbacks và mapping trước khi gửi CQL. Cassandra server chỉ nhìn thấy **statement và bind values** đã đến. Nó không tự biết:

- Java entity nào đã có `@CreatedDate`.
- Request HTTP được xác thực bằng người dùng nào.
- Ai là `AuditorAware` của Spring.
- Logic `BeforeSaveCallback` của ứng dụng.
- Một `UPDATE` CQL có xuất phát từ repository, một script hay một dịch vụ khác.

Do đó, auditing phía Spring có phạm vi **những đường đi qua cơ chế Spring Data tương ứng**. Nó **không tương đương một database trigger phổ quát** và không tự bao phủ các câu CQL trực tiếp.

## 3. Bảng theo truy vấn để minh họa metadata auditing

Giả sử màn hình lấy đơn hàng theo `order_id`. Bảng minh họa:

~~~sql
-- Keyspace app_ks phải tồn tại với replication phù hợp.
CREATE TABLE app_ks.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    state text,
    version bigint,
    created_at timestamp,
    created_by text,
    updated_at timestamp,
    updated_by text,
    last_command_id uuid
);
~~~

| Cột | Vai trò | Quy tắc đề xuất |
| --- | --- | --- |
| `order_id` | Primary key, đồng thời là partition key | Định danh ổn định của đơn |
| `customer_id` | Cột thường | Tham chiếu nghiệp vụ |
| `state` | Cột thường | `CREATED`, `PAID`, `CANCELLED` |
| `version` | Cột thường | Tăng có điều kiện nếu dùng optimistic concurrency |
| `created_at` | Audit metadata | Được gán khi tạo hợp lệ; không viết lại trong update |
| `created_by` | Audit metadata | Chủ thể tạo được xác định bằng ngữ cảnh đáng tin |
| `updated_at` | Audit metadata | Thời điểm thay đổi nghiệp vụ được chấp nhận |
| `updated_by` | Audit metadata | Chủ thể thực hiện lần thay đổi được chấp nhận |
| `last_command_id` | Correlation/idempotency hỗ trợ | Không tự thay thế lịch sử tất cả command |

**Thiết kế bảng theo truy vấn** vẫn bắt buộc: đường đọc chính là `WHERE order_id = ?`. Auditing không tạo secondary index theo `updated_by` và không làm truy vấn `WHERE state = ?` tự trở nên hợp lệ/hiệu quả. Muốn lọc theo người sửa hoặc theo ngày, cần đánh giá thêm bảng truy vấn/index phù hợp.

### 3.1. Cột timestamp nghiệp vụ và write timestamp của Cassandra

`created_at`/`updated_at` là những giá trị **ứng dụng đưa vào CQL**. Chúng khác với **write timestamp** của Cassandra dùng để hòa giải cell:

~~~sql
SELECT order_id, state, updated_at, updated_by,
       WRITETIME(state)
FROM app_ks.orders_by_id
WHERE order_id = ?;
~~~

`WRITETIME(state)` có thể giúp điều tra write timestamp của một cột thường được hỗ trợ, nhưng **không cho biết người sửa** hoặc đủ lịch sử các phiên bản. Một CQL `UPDATE` chỉ thay `state` có thể làm `WRITETIME(state)` đổi trong khi `updated_at`/`updated_by` không đổi.

**Không dùng `WRITETIME(...)` làm hệ thống auditing nghiệp vụ.** Nó là metadata kỹ thuật của phiên bản cell, không phải event ID, command ID hoặc identity đã xác thực.

## 4. Spring Data auditing thường được áp dụng ở giai đoạn nào?

Spring Data Commons cung cấp các annotation như:

- `@CreatedDate`: thời điểm tạo.
- `@LastModifiedDate`: thời điểm sửa gần nhất.
- `@CreatedBy`: chủ thể tạo.
- `@LastModifiedBy`: chủ thể sửa gần nhất.

Các annotation này có ý nghĩa khi **cơ chế auditing được bật và đường ghi đi qua pipeline có hỗ trợ**. Những phần sau dùng Spring Data Cassandra làm bối cảnh, nhưng phải đối chiếu chính xác **phiên bản Spring Data, Spring Boot và driver** của dự án.

### 4.1. Entity minh họa

~~~java
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_id")
public class OrderRow {
    @PrimaryKey("order_id")
    private UUID orderId;

    @Column("state")
    private String state;

    @Column("version")
    private Long version;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @CreatedBy
    @Column("created_by")
    private String createdBy;

    @LastModifiedDate
    @Column("updated_at")
    private Instant updatedAt;

    @LastModifiedBy
    @Column("updated_by")
    private String updatedBy;

    protected OrderRow() {}

    public UUID getOrderId() { return orderId; }
    public String getState() { return state; }
    public Long getVersion() { return version; }
    public Instant getCreatedAt() { return createdAt; }
    public String getCreatedBy() { return createdBy; }
    public Instant getUpdatedAt() { return updatedAt; }
    public String getUpdatedBy() { return updatedBy; }
}
~~~

Ví dụ chỉ hiển thị các trường liên quan; một entity production cần constructor/setter/immutable mapping phù hợp. Nếu dùng mapping entity theo keyspace không mặc định, bảo đảm repository/template trỏ đúng keyspace của bảng đã tạo.

### 4.2. Bật auditing và cung cấp actor

Với dòng Spring Data Cassandra hỗ trợ annotation cấu hình tương ứng, hình thức bật auditing có thể như sau:

~~~java
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.cassandra.config.EnableCassandraAuditing;

@Configuration(proxyBeanMethods = false)
@EnableCassandraAuditing
public class CassandraAuditConfiguration {
    @Bean
    AuditorAware<String> currentAuditor() {
        return () -> {
            // Ví dụ tối giản: thay bằng nguồn principal đáng tin.
            return Optional.of("system-job");
        };
    }
}
~~~

**Lưu ý:** ví dụ minh họa cơ chế; `"system-job"` không phải phương án mặc định phù hợp cho tất cả request. Trong ứng dụng có xác thực, phải lấy principal từ **security context đáng tin**, không nhận trực tiếp giá trị `updatedBy` do client tự khai báo.

Các phiên bản/framework khác nhau có thể yêu cầu cấu hình `AuditorAware`, callback và date-time provider khác nhau; với reactive auditing cần **cơ chế cung cấp auditor không đồng bộ phù hợp**. Kiểm tra dependency, API được hỗ trợ và integration test thực tế.

### 4.3. Vòng đời entity không tương đương vòng đời CQL

Một pipeline entity được Spring Data hỗ trợ có thể trải qua các bước **chuyển đổi/ánh xạ, entity callback và sinh CQL**. Những callback cụ thể chạy ở bước nào phụ thuộc loại thao tác và phiên bản.

**Không suy luận ngược**: vì một `@CreatedDate` hoạt động khi gọi `repository.save`, mọi câu `UPDATE` có bảng `orders_by_id` đều phải chạy callback đó. Câu CQL đến từ driver không có đối tượng `OrderRow` để Spring tự chỉnh sửa trước khi gửi.

## 5. Auditing chỉ đúng khi nhận diện được “entity mới”

Một vấn đề đặc biệt của Cassandra là `INSERT` thông thường có thể **upsert**. Trong khi đó, auditing entity cần quyết định lúc nào đặt **created** và lúc nào đặt **last modified**.

Ví dụ hai thao tác:

~~~sql
INSERT INTO app_ks.orders_by_id
    (order_id, state)
VALUES (?, 'CREATED');

-- Lần gọi sau vẫn có thể dùng INSERT với cùng khóa.
INSERT INTO app_ks.orders_by_id
    (order_id, state)
VALUES (?, 'PAID');
~~~

Nếu đường Spring Data dùng tiêu chí **entity is-new** để quyết định created/modified, cần hiểu rõ cách entity được đánh dấu mới: ID có sẵn, `@Version`, `Persistable` hoặc cấu hình mapping có thể ảnh hưởng việc nhận diện. Không được suy rằng Cassandra server sẽ kiểm tra hàng thật sự chưa tồn tại chỉ vì entity có `@CreatedDate`.

**Tính mới của entity trong một mapping pipeline** và **tính chưa tồn tại của hàng tại primary key trong Cassandra** là hai khái niệm khác nhau.

Để yêu cầu **create-only**, một câu `INSERT ... IF NOT EXISTS` hoặc cơ chế được xác minh tương đương mới là điều kiện dữ liệu tại server. Khi ấy audit fields của lần tạo phải được bind **trong chính conditional insert**, và chỉ coi sự kiện “đã tạo” là thành công nếu `[applied] = true`.

### 5.1. Không ghi lại created_at khi sửa

Quy tắc nghiệp vụ thường dùng:

- Lúc tạo: gán `created_at` và `created_by`; có thể đồng thời gán `updated_at`, `updated_by` theo quy ước.
- Lúc sửa: chỉ gán `updated_at` và `updated_by`; **không sửa `created_at`/`created_by`**.
- Khi CAS không áp dụng: **không** ghi nhận một lần sửa thành công vào metadata entity.

Nếu code CQL ghi lại `created_at` trên mỗi `UPDATE`, thời điểm tạo ban đầu có thể mất dù auditing ở nơi khác được cấu hình hoàn hảo.

## 6. Ma trận kiểm tra phạm vi các đường ghi

Đây là bảng rà soát nên lập trước khi tuyên bố “hệ thống đã bật auditing”:

| Đường ghi | Có đi qua pipeline entity auditing? | Cách xác minh/cần làm |
| --- | --- | --- |
| `CassandraRepository.save(entity)` | **Có thể**, nếu cấu hình auditing và callback được hỗ trợ | Test created/modified và actor thực tế |
| Reactive repository `save(entity)` | **Có thể**, tùy hỗ trợ reactive auditing | Test nguồn auditor/reactive context |
| `CassandraTemplate.insert(entity)`/`update(entity)` | Tùy operation và phiên bản/callback | Xem tài liệu API và integration test |
| Template update bằng query criteria và update definition | **Không được mặc định có entity callback** | Kiểm tra CQL sinh ra; set audit fields tường minh nếu cần |
| Repository `@Query` với `INSERT/UPDATE/DELETE` | **Không được mặc định chạy auditing entity** | Kiểm tra kiểu modifying/query và CQL thật |
| `CqlTemplate`/`CqlOperations` chạy CQL | **Không có lý do tự đi qua auditing entity** | Bind cột audit trong CQL hoặc gọi gateway chính sách |
| Java driver `CqlSession.execute(...)` | **Bỏ qua mapping/callback Spring Data** | Tự bind audit fields |
| `CqlSession.executeAsync(...)` | **Bỏ qua mapping/callback Spring Data** | Tự bind audit fields trong async flow |
| `BatchStatement`/CQL `BEGIN BATCH` | **Không tự áp auditing cho từng mutation** | Mỗi mutation cần audit fields/cơ chế riêng |
| LWT `IF NOT EXISTS`/`IF version = ?` | **Server kiểm điều kiện, không tự biết auditor** | Bind audit fields; chỉ coi applied=true là ghi thành công |
| CQL ở `cqlsh`, migration, ETL, script | **Không qua Spring Data** | Quy trình vận hành/audit riêng |
| Một ứng dụng khác dùng cùng keyspace | **Không qua callback của ứng dụng này** | Hợp đồng schema/gateway chung hoặc event audit đáng tin |

**Quan trọng:** bảng này không tuyên bố mọi template operation chắc chắn có/không một callback ở mọi phiên bản. Những đường đi **trực tiếp CQL** thì không nên mong annotation entity tự chạy; những đường đi **entity mapping** phải được kiểm chứng.

## 7. Repository.save và CassandraTemplate: kiểm tra đường thực thi

Repository thường thuận tiện cho CRUD:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface OrderRepository
        extends CassandraRepository<OrderRow, UUID> {
}
~~~

Lệnh:

~~~java
OrderRow saved = repository.save(order);
~~~

có thể đưa entity qua mapping/auditing pipeline khi được cấu hình đúng. Nhưng để biết **chính xác**:

1. Tạo một entity mới trong integration test.
2. Ghi bằng `save`.
3. Đọc lại bằng CQL/driver để xác minh `created_at`, `created_by`, `updated_at`, `updated_by` đã được persist.
4. Sửa cùng entity, gọi `save` lại, đọc lại và kiểm tra created fields không bị thay đổi, modified fields đổi theo hợp đồng.
5. Ghi nhận **CQL/statement options thực tế** nếu test cần xác minh cột nào được mutation.

### 7.1. Đường template cần kiểm tra riêng

Trong một codebase có thể đồng thời có:

~~~java
// API dạng entity - pipeline phụ thuộc Spring Data version.
cassandraTemplate.insert(order);

// API update qua query/Update object: không có lý do tự đồng nhất
// với toàn bộ callback của thao tác lưu entity.
cassandraTemplate.update(query, update, OrderRow.class);
~~~

Đây là ví dụ **hình thức API khái niệm**; kiểu query/update và overload cụ thể cần đối chiếu phiên bản. Mục đích là chỉ ra **đường ghi khác nhau phải test khác nhau**.

Nếu path `template.update(query, update, ...)` chỉ biết tên cột/giá trị mà **không có một entity đầy đủ**, đừng mặc định nó sẽ biết principal, created metadata hay chạy đủ callbacks như `save(entity)`.

**Checklist cho mỗi template operation:** nó có nhận entity không, callback nào chạy, auditor được resolve ở đâu, field audit có xuất hiện trong CQL cuối cùng không, và write có đang dùng TTL/IF không?

## 8. @Query và @Modifying: một câu lệnh trực tiếp dễ bị bỏ sót

Giả sử nhóm phát triển thêm một repository method:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.Modifying;
import org.springframework.data.cassandra.repository.Query;

public interface OrderWriteRepository
        extends CassandraRepository<OrderRow, UUID> {

    @Modifying
    @Query("UPDATE app_ks.orders_by_id " +
           "SET state = ?0 WHERE order_id = ?1")
    void changeState(String nextState, UUID orderId);
}
~~~

**Vấn đề:** câu CQL chỉ nhắc đến `state`. Annotation `@LastModifiedDate` trên `OrderRow` **không tự thêm `updated_at = ?`** vào câu CQL được viết tường minh. Đường modifying query cần được xem là **một đường ghi phải kiểm tra riêng**.

Đường sửa được thiết kế rõ hơn:

~~~sql
UPDATE app_ks.orders_by_id
SET state = ?, updated_at = ?, updated_by = ?,
    last_command_id = ?
WHERE order_id = ?;
~~~

Khi query được khai báo trong repository, phải xét cú pháp binding và return type của `@Modifying` theo **đúng phiên bản Spring Data Cassandra**. Đặc biệt:

- Trả `void` không nghĩa database chắc chắn đã cập nhật **một hàng tồn tại**; Cassandra có upsert semantics.
- Trả `boolean` không được mặc nhiên hiểu là `[applied]` nếu method/framework không có hợp đồng rõ.
- Một method dùng `@Query` có thể được gọi từ service vốn được bật auditing, nhưng CQL literal vẫn **không tự sinh thêm các cột audit**.
- Nếu muốn biết điều kiện CAS, nên có đường nhận kết quả LWT tường minh, ví dụ `ResultSet.wasApplied()`.

## 9. CqlTemplate và CqlSession: auditing phải nằm trong mutation

Khi dùng `CqlTemplate`, `CqlOperations` hoặc Java driver `CqlSession`, lập trình viên thường tự viết CQL và bind parameters. Ví dụ thiếu auditing:

~~~sql
UPDATE app_ks.orders_by_id
SET state = 'PAID'
WHERE order_id = ?;
~~~

Để lưu metadata phù hợp:

~~~sql
UPDATE app_ks.orders_by_id
SET state = 'PAID',
    updated_at = ?,
    updated_by = ?,
    last_command_id = ?
WHERE order_id = ?;
~~~

Đây vẫn là **UPDATE không điều kiện**: có thể upsert nếu hàng chưa tồn tại và không bảo vệ state transition. Nếu nghiệp vụ cần “chỉ thanh toán đơn còn CREATED ở version 7”, phải kết hợp `IF`, không chỉ thêm audit fields.

### 9.1. Ai tạo updated_by?

Một actor audit cần xuất phát từ một **nguồn tin cậy**:

- Principal đã xác thực từ Spring Security.
- Identity của một service account khi chạy job.
- Thông tin được xác thực qua hệ thống message/command envelope.
- Một định danh kỹ thuật có thể đối chiếu trong logging/tracing.

Không nên:

~~~java
String actor = request.getParameter("updatedBy"); // Không tin cậy.
~~~

vì client có thể giả danh người khác. Các hệ thống cần phân biệt **người khởi phát** và **service thực thi**, ví dụ `actor_user_id`, `executed_by_service` hoặc correlation ID riêng. Không đặt một username không kiểm soát vào audit chỉ vì nó có trong JSON.

### 9.2. Audit fields đi cùng mutation

Nếu state thay đổi và updated fields nằm trong **cùng UPDATE CQL**, Cassandra xử lý chúng trong phạm vi statement/partition tương ứng. Cách này tránh tạo một khoảng trống cố ý giữa hai lệnh:

~~~text
Sai về thiết kế:
  1. UPDATE state = 'PAID'
  2. UPDATE updated_at = ..., updated_by = ...
  Nếu tiến trình dừng ở giữa: state mới, audit cũ.

Tốt hơn:
  UPDATE state = 'PAID',
         updated_at = ?,
         updated_by = ?,
         last_command_id = ?
  WHERE order_id = ?;
~~~

Đặt cùng mutation **không làm câu write không điều kiện thành CAS**, cũng không tạo audit history bất biến. Nó chỉ giúp các field thuộc cùng quyết định ghi không bị tách thành hai request do code của chúng ta.

## 10. Java driver 4.x: gateway ghi audit tường minh

Một gateway sử dụng `CqlSession` được Spring quản lý, `PreparedStatement` chuẩn bị một lần và `BoundStatement` cho từng request:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public final class OrderAuditCqlGateway {
    private final CqlSession session;
    private final PreparedStatement createIfAbsent;
    private final PreparedStatement payIfUnchanged;

    public OrderAuditCqlGateway(CqlSession session) {
        this.session = Objects.requireNonNull(session);
        this.createIfAbsent = session.prepare(
            "INSERT INTO app_ks.orders_by_id " +
            "(order_id, state, version, " +
            " created_at, created_by, updated_at, updated_by, " +
            " last_command_id) " +
            "VALUES (?, 'CREATED', 1, ?, ?, ?, ?, ?) " +
            "IF NOT EXISTS"
        );
        this.payIfUnchanged = session.prepare(
            "UPDATE app_ks.orders_by_id " +
            "SET state = 'PAID', version = ?, " +
            " updated_at = ?, updated_by = ?, last_command_id = ? " +
            "WHERE order_id = ? IF version = ? AND state = 'CREATED'"
        );
    }

    public boolean create(
            UUID orderId, String actor, UUID commandId,
            Instant now) {
        ResultSet result = session.execute(
            createIfAbsent.bind(
                orderId, now, actor, now, actor, commandId)
        );
        return result.wasApplied();
    }

    public boolean pay(
            UUID orderId, long expectedVersion,
            String actor, UUID commandId, Instant now) {
        if (expectedVersion == Long.MAX_VALUE) {
            throw new IllegalArgumentException("Version overflow");
        }
        ResultSet result = session.execute(
            payIfUnchanged.bind(
                expectedVersion + 1, now, actor, commandId,
                orderId, expectedVersion)
        );
        return result.wasApplied();
    }
}
~~~

Đây là ví dụ Java driver **4.x** với class do ứng dụng đăng ký làm Spring bean. CQL được chuẩn bị một lần, **bind values** cho từng request, không ghép giá trị người dùng vào chuỗi query.

**Những bất biến thể hiện ngay trong CQL:**

- Tạo đơn: `IF NOT EXISTS`, đồng thời gán cả created/updated metadata.
- Thanh toán: `IF version = ? AND state = 'CREATED'`, cập nhật `state`, `version`, `updated_at`, `updated_by`, `last_command_id` trong **cùng conditional mutation**.
- Không sửa `created_at` và `created_by` trong lệnh thanh toán.
- `ResultSet.wasApplied()` trả kết quả **điều kiện**, không phải chỉ một lời xác nhận “query đã được gửi”.

**Quan trọng:** ví dụ không tự lấy actor từ security context — service phải cung cấp actor đã được xác thực. `Instant now` nên đến từ đồng hồ/nguồn thời gian ứng dụng được kiểm soát, có thể inject `Clock` để test; không nên chấp nhận thời gian tùy ý từ request nếu business yêu cầu audit đáng tin.

### 10.1. Đừng tự đóng CqlSession sau mỗi ghi

`CqlSession` thường là bean dùng chung cho repository/template/gateway. Đóng nó sau từng write sẽ ảnh hưởng những request khác, tạo thêm chi phí kết nối và phá lifecycle của ứng dụng.

Spring/ApplicationContext nên quản lý vòng đời session. **Không** tạo `CqlSession.builder().build()` cho mỗi audit update chỉ để điền vài cột.

## 11. LWT: không được cập nhật audit khi điều kiện không thỏa

Xét hai writer cạnh tranh trên cùng hàng:

~~~text
Order X: state=CREATED, version=7, updated_by=creator
Writer A: chuyển PAID nếu version=7, actor=alice
Writer B: chuyển CANCELLED nếu version=7, actor=bob
~~~

Nếu cả hai dùng LWT/CAS đúng cách và không có write ngoài luồng, một writer có thể được áp dụng, writer kia nhận `[applied] = false`.

~~~mermaid
sequenceDiagram
    participant A as Alice
    participant DB as Cassandra LWT
    participant B as Bob
    A->>DB: UPDATE state=PAID, updated_by=alice IF version=7
    B->>DB: UPDATE state=CANCELLED, updated_by=bob IF version=7
    DB-->>A: Một thao tác có thể [applied] = true
    DB-->>B: Thao tác kia có thể [applied] = false
~~~

Nếu request B thất bại do điều kiện, **không ghi `updated_by = bob`** vào hàng ở một request khác để “ghi dấu đã thử”. Điều đó sẽ biến người thử thất bại thành người sửa thành công.

Muốn audit **nỗ lực bị từ chối**, hãy ghi một **loại sự kiện riêng** như `PaymentRejected` hoặc `TransitionConflict`, phân biệt với thành công. Lưu nỗ lực thất bại vào metadata last-modified của entity là sai ngữ nghĩa.

### 11.1. Ba kết quả phải tách bạch

| Kết quả LWT | Ý nghĩa | Cách xử lý auditing |
| --- | --- | --- |
| `[applied] = true` | Điều kiện thỏa, mutation được áp dụng | Metadata updated nằm trong mutation đã được ghi |
| `[applied] = false` | Điều kiện không thỏa | Metadata của mutation này **không được áp dụng** |
| Timeout/Unavailable/lỗi | Không có phản hồi CAS hợp lệ; trạng thái có thể chưa rõ | **Không** tự báo audit thành công hoặc thất bại chắc chắn |

Một callback ở client chạy **trước khi gửi** mutation cũng không chứng minh server đã chấp nhận conditional write. Khi cần audit về **kết quả đã áp dụng**, phải căn cứ vào response/đối soát, không chỉ callback “trước lưu”.

## 12. Audit fields và optimistic locking phải nhất quán

Lưu cột `version` giúp diễn đạt “bản đang lưu còn giống bản tôi đã đọc”:

~~~sql
UPDATE app_ks.orders_by_id
SET state = ?,
    version = ?,
    updated_at = ?,
    updated_by = ?,
    last_command_id = ?
WHERE order_id = ?
IF version = ?;
~~~

**Quy tắc quan trọng:**

1. Đọc `version` hiện tại và giữ expected version.
2. Khi cập nhật, tăng version và ghi audit metadata trong **cùng mutation có điều kiện**.
3. Nếu `false`, đọc lại/quyết định conflict hoặc retry dựa trên state mới.
4. Không chuyển sang `repository.save(entity)` không điều kiện để “cứ ghi cho được”, nếu làm vậy sẽ phá version guard.
5. Mọi writer liên quan phải theo cùng chính sách, kể cả batch job và endpoint nội bộ.

Một field Java tên `version` không tự bắt mọi đường CQL trực tiếp tham gia CAS. Nếu dùng hỗ trợ `@Version` của Spring Data Cassandra trong phiên bản tương ứng, hãy kiểm tra chính xác **đường nào** áp dụng và không trộn vô thức với gateway tự tăng version.

### 12.1. Auditing không thay CAS

Hai writer có thể ghi `updated_at` khác nhau nhưng vẫn cùng thay state không điều kiện. Timestamp audit chỉ mô tả một thời điểm, **không kiểm tra trạng thái hiện tại** của hàng.

`updated_by` và `updated_at` là metadata; `IF state/version` là **điều kiện đồng thuận**. Không dùng một thay cho cái kia.

## 13. Batch: nhiều mutation không tự kích hoạt entity callbacks

Ví dụ CQL batch cập nhật hai hàng thuộc một partition theo schema phù hợp:

~~~sql
CREATE TABLE app_ks.order_steps_by_order (
    order_id uuid,
    step_no int,
    state text,
    updated_at timestamp,
    updated_by text,
    PRIMARY KEY ((order_id), step_no)
);
~~~

~~~sql
BEGIN UNLOGGED BATCH
    UPDATE app_ks.order_steps_by_order
    SET state = 'DONE', updated_at = ?, updated_by = ?
    WHERE order_id = ? AND step_no = 1;

    UPDATE app_ks.order_steps_by_order
    SET state = 'READY', updated_at = ?, updated_by = ?
    WHERE order_id = ? AND step_no = 2;
APPLY BATCH;
~~~

Vì cả hai row thuộc cùng partition trong cùng bảng, đây là một ví dụ batch theo partition đơn giản để nghiên cứu. **Không có entity Java nào bắt buộc đi qua callback chỉ vì câu CQL xuất hiện trong source của một ứng dụng Spring.**

**Rà soát batch:**

- Mọi mutation nào thực sự thay dữ liệu phải chứa cột audit tương ứng nếu use case yêu cầu.
- Các actor/time bind có được lấy từ **một command đáng tin** không?
- Trạng thái `created_at` có bị ghi lại ngoài ý muốn không?
- Có những row/cột được DELETE/TTL hoặc câu counter update không thể dùng cùng mẫu audit không?
- Batch loại `LOGGED`/`UNLOGGED`/`COUNTER` nào, trong bao nhiêu partition, có ràng buộc CQL nào?
- Nếu batch timeout, outcome có thể chưa rõ; audit không thể kết luận toàn bộ đã hoàn tất chỉ từ exception.

**Không nhầm `LOGGED BATCH` với transaction SQL đa bảng có isolation.** Batchlog và các bảo đảm atomicity trong Cassandra có phạm vi/đánh đổi riêng, không tự bảo vệ một lịch sử audit xuyên các bảng/partition và external systems theo thứ tự tuyến tính.

## 14. Reactive và async: đổi API không thay auditing boundary

Một ứng dụng có thể sử dụng:

- `ReactiveCassandraRepository`.
- Reactive template theo phiên bản Spring Data.
- Java driver `CqlSession.executeAsync(...)`.
- Reactor `Mono`/`Flux` bọc `CompletionStage`.

**Nếu statement là CQL trực tiếp, các annotation trên entity không tự được thực thi** chỉ vì nó được đặt trong một `Mono.defer(...)`.

### 14.1. Async LWT với audit fields

Từ gateway phần 10, có thể biểu đạt một phương thức reactive mới bằng Java driver:

~~~java
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import java.time.Instant;
import java.util.UUID;
import reactor.core.publisher.Mono;

public Mono<Boolean> payAsync(
        UUID orderId, long expectedVersion,
        String actor, UUID commandId, Instant now) {
    return Mono.defer(() -> {
        if (expectedVersion == Long.MAX_VALUE) {
            return Mono.error(
                new IllegalArgumentException("Version overflow")
            );
        }
        BoundStatement bound = payIfUnchanged.bind(
            expectedVersion + 1, now, actor, commandId,
            orderId, expectedVersion
        );
        return Mono.fromCompletionStage(
                () -> session.executeAsync(bound))
            .map(AsyncResultSet::wasApplied);
    });
}
~~~

Đoạn method minh họa nằm **trong class có field `session` và `payIfUnchanged`** ở phần trước; cần import Reactor và driver phù hợp. Đối với API thuần `CompletionStage`, logic tương đương nhưng không cần `Mono`.

Với `Mono.defer(...)`, query được tạo và gửi **theo subscription**. Một retry/resubscription có thể gửi lại mutation. Actor, command ID, thời điểm nghiệp vụ và expected version phải có chính sách **ổn định khi retry** hoặc được đối soát, không tự sinh lại như một command hoàn toàn mới.

### 14.2. Principal của reactive request không nhất thiết ở ThreadLocal

Trong WebFlux/Reactor, execution có thể chuyển thread. Không nên dựa vào một `ThreadLocal` tùy ý để lấy principal ở mọi callback. Auditing reactive thường cần tích hợp với **Reactor Context/security context** hoặc truyền thông tin actor đã xác thực qua command object.

Một hướng thiết kế:

~~~text
HTTP authenticated request
    -> trích xuất actor từ security context phù hợp
    -> tạo command {orderId, actorId, commandId, expectedVersion}
    -> reactive gateway bind state + audit fields
    -> nhận applied/false/error
~~~

**Không** phát một câu CQL rồi mới lấy actor ở operator chạy sau nó. Auditing muốn ghi vào cùng mutation phải có actor ngay khi bind statement.

### 14.3. Cancellation không có nghĩa rollback

Client ngắt kết nối có thể hủy subscription, nhưng Cassandra có thể đã nhận hoặc commit CQL. Một request bị cancel sau khi `state` và `updated_by` được ghi sẽ **không tự quay lại giá trị cũ**.

Nếu nghiệp vụ yêu cầu xử lý bền vững kể cả khi HTTP client rời đi, dùng **command/job có trạng thái bền vững**, không chỉ `subscribe()` thủ công rồi tin rằng nó luôn hoàn thành.

## 15. DELETE, TTL, UNSET và tác động lên auditing

### 15.1. DELETE có thể làm biến mất cả metadata hiện tại

~~~sql
DELETE FROM app_ks.orders_by_id
WHERE order_id = ?;
~~~

Nếu hàng bị xóa, các cột `created_at` và `updated_by` trên **chính hàng đó** cũng không còn là dữ liệu sống để đọc. Vì vậy, nếu yêu cầu là **theo dõi ai đã xóa**, lưu thông tin **trong cùng hàng trước khi xóa** rồi xóa hàng không bảo đảm audit trail còn tồn tại.

Các lựa chọn theo mục tiêu:

- **Soft delete**: cập nhật `deleted_at`, `deleted_by`/`state=DELETED`, có chính sách truy vấn/retention rõ ràng.
- **Append audit event** `OrderDeleted` vào nguồn lưu lịch sử đáng tin.
- **Quy trình xóa có đối soát** nếu cần xóa dữ liệu cá nhân nhưng giữ metadata tối thiểu theo luật/quy định.

Không mặc định soft delete giải quyết mọi yêu cầu quyền riêng tư hoặc compliance; retention và quyền xóa phải được thiết kế riêng.

### 15.2. TTL tự hết hạn không phải “một người đã xóa”

Cassandra TTL có thể làm cell hết hạn mà không có HTTP request tại thời điểm hết hạn. Auditing callback của Spring **không tự chạy mỗi khi TTL hết hạn**.

Một hàng được ghi với TTL có thể về sau không còn dữ liệu sống nhưng `updated_by` vẫn phản ánh người sửa trước khi hết hạn, hoặc cột audit cũng đã hết hạn tùy TTL được áp dụng.

Nếu nghiệp vụ cần biết **khi nào tài nguyên dự kiến hết hạn**, lưu `expires_at` theo quy tắc riêng; nếu cần event **đã hết hạn**, cần cơ chế phát hiện/xử lý expiry được thiết kế, không coi Cassandra TTL là một sự kiện ứng dụng tự phát ra.

### 15.3. UNSET giữ nguyên audit fields, NULL có thể xóa chúng

Với prepared statement:

~~~sql
UPDATE app_ks.orders_by_id
SET state = ?, updated_at = ?, updated_by = ?
WHERE order_id = ?;
~~~

Nếu dùng `BoundStatement.unset(...)` cho `updated_at`/`updated_by`, mutation có thể **không đụng đến các cell đó** trong vị trí CQL hỗ trợ UNSET. Đây có thể là ý định giữ nguyên metadata, nhưng **sai** nếu `state` thực sự thay đổi và contract bắt buộc audit modified fields.

Nếu bind `NULL` cho `updated_by`, mutation có thể tạo **tombstone**, làm mất identity người sửa. Không sử dụng Java `null` mơ hồ để biểu đạt “giữ nguyên” mà không kiểm soát mapping/bind semantics.

**Kết luận:** ở đường PATCH, hãy xác định field nào thay đổi và liệu thay đổi đó có phải một modification cần ghi audit không. Tránh viết metadata mới khi request **no-op**, nhưng cũng không được để một mutation nghiệp vụ thật sự diễn ra mà không cập nhật modified metadata theo chính sách.

## 16. Timestamp audit không phải đồng hồ logic của Cassandra

Một nguồn nhầm lẫn khác là dùng `updated_at` như phiên bản để quyết định mutation nào thắng:

~~~text
Writer A: updated_at = 10:00:00
Writer B: updated_at = 09:59:59 vì clock skew
~~~

Nếu hai writer cùng ghi `state` không điều kiện, Cassandra hòa giải theo **write timestamp của mutation/cell**, không nhất thiết theo `updated_at` business. Không thể chỉ nhìn cột audit và kết luận trình tự commit.

**Với state machine cần chống tranh chấp**, dùng `IF version = ?`, `IF state = ?` hoặc cơ chế điều phối tương đương. Metadata audit chỉ phục vụ truy vết, không phải khóa lạc quan.

### 16.1. Chọn nguồn thời gian có thể kiểm soát

Trong ứng dụng Java:

~~~java
import java.time.Clock;
import java.time.Instant;

public final class AuditClock {
    private final Clock clock;

    public AuditClock(Clock clock) {
        this.clock = clock;
    }

    public Instant now() {
        return Instant.now(clock);
    }
}
~~~

`Clock` có thể được inject với timezone UTC hoặc mock/fixed clock trong test. Cột CQL `timestamp` thường có độ chính xác mili giây; nếu cần assert round-trip chính xác, chuẩn hóa `Instant` cho phù hợp và chú ý múi giờ khi hiển thị.

**Tránh tự tin quá mức:** một đồng hồ ứng dụng đồng bộ tốt vẫn không chứng minh thứ tự nhân quả của hai writer phân tán; event sequence/version mới là công cụ phù hợp cho những yêu cầu khác nhau.

## 17. Audit trail append-only khác metadata last-modified

Nếu nghiệp vụ phải trả lời “ai thay đổi gì vào mỗi lần, kể cả lệnh bị từ chối?”, một hàng snapshot không đủ.

Ví dụ bảng timeline theo đơn:

~~~sql
CREATE TABLE app_ks.order_audit_by_order (
    order_id uuid,
    audit_no bigint,
    audit_id uuid,
    command_id uuid,
    actor_id text,
    action text,
    outcome text,
    occurred_at timestamp,
    details text,
    PRIMARY KEY ((order_id), audit_no)
) WITH CLUSTERING ORDER BY (audit_no ASC);
~~~

Truy vấn:

~~~sql
SELECT audit_no, audit_id, actor_id, action, outcome, occurred_at
FROM app_ks.order_audit_by_order
WHERE order_id = ? AND audit_no >= ?
LIMIT 100;
~~~

**Ưu điểm của event/audit table:**

- Lưu được nhiều thay đổi thay vì chỉ lần gần nhất.
- Phân biệt `ACCEPTED`, `REJECTED`, `ERROR`, `PENDING` theo quy tắc nghiệp vụ.
- Có thể phục vụ audit timeline/paging theo order.

**Những giới hạn phải tự thiết kế:**

- `audit_no` không tự tăng an toàn khi nhiều writer làm `SELECT MAX + 1`.
- `INSERT` Cassandra có **upsert semantics**, không tự biến hàng audit thành bất biến; muốn chặn đè cùng khóa, xét `IF NOT EXISTS` hoặc một cơ chế append an toàn.
- `audit_id`/`command_id` ở cột thường **không tự unique trên toàn bảng** nếu không phải một phần khóa kiểm soát.
- Event payload cần version/schema, giới hạn kích thước, mã hóa/ẩn dữ liệu nhạy cảm và retention.
- Audit có yêu cầu pháp lý mạnh có thể cần giải pháp lưu trữ **tamper-evident/append-only** riêng ngoài một bảng Cassandra mà nhiều writer có quyền UPDATE/DELETE.

## 18. Hai lần ghi vào hai bảng không được mặc định là một transaction

Một service có thể làm:

~~~text
1. LWT update orders_by_id:
   state=PAID, updated_by=alice, version=8 -> [applied]=true

2. INSERT order_audit_by_order:
   action=OrderPaid, actor=alice -> timeout/error
~~~

Kết quả có thể là trạng thái chính **đã PAID** trong khi audit timeline **chưa có event**. Nếu đảo thứ tự, audit có thể báo “đã thanh toán” khi CAS đổi trạng thái lại thất bại.

~~~mermaid
flowchart TD
    A[CAS state + audit metadata cùng statement] --> B{Applied?}
    B -->|false| C[Conflict; không cập nhật metadata]
    B -->|true| D[Cần phát audit event ở bảng khác]
    D --> E{Append event hoàn tất?}
    E -->|Có| F[Workflow hoàn tất]
    E -->|Lỗi hoặc không chắc| G[Retry/đối soát có lưu trạng thái bền vững]
~~~

**Không nhầm:**

- Metadata cập nhật **cùng một conditional mutation của hàng chính** có thể nằm trong quyết định CAS đó.
- Ghi **bảng event riêng** là một bước khác, cần thiết kế tính bền vững/handoff.
- Một reactive `then(...)` giữa hai bước chỉ **sắp thứ tự**, không rollback bước đầu nếu bước hai thất bại.
- `LOGGED BATCH` trong Cassandra có cơ chế phục hồi mutation theo batch nhưng không cung cấp isolation/transaction SQL đa partition tùy ý; conditional batch còn có giới hạn partition/CQL theo phiên bản.

### 18.1. Chọn nguồn sự thật và cơ chế đối soát

Có thể lựa chọn:

1. **Snapshot là nguồn sự thật**: commit state và audit metadata ở hàng chính; tạo một **handoff bền vững** hoặc reconciliation worker để bổ sung event thiếu.
2. **Event log là nguồn sự thật**: commit sự kiện hợp lệ theo giao thức append/version an toàn; các bảng snapshot là projection có thể xây lại.
3. **Workflow/saga**: ghi nhận trạng thái từng bước, retry có kiểm soát, idempotency và cơ chế bù trừ khi thích hợp.
4. **Audit sink riêng** cho yêu cầu pháp lý: xác định rõ thời điểm được coi là ghi thành công, khóa truy cập, retention và cách chống sửa/xóa.

Không tuyên bố “hệ thống có audit đầy đủ” nếu **lỗi ở giữa hai bước có thể làm mất event** mà không có cách phát hiện/khôi phục.

## 19. Timeout, retry và idempotency ảnh hưởng audit thế nào?

Giả sử client gửi conditional insert với `command_id = C` và actor `alice`. Cassandra có thể áp dụng mutation nhưng client mất response. Retry cùng `command_id` và cùng khóa có thể nhận `[applied] = false` vì hàng đã tồn tại.

**False trong lần retry không chứng minh lệnh đầu chưa thành công.** Nếu ứng dụng gửi audit event `CreateRejected` chỉ dựa trên kết quả false mà không đối chiếu request ID, lịch sử có thể ghi một sự kiện từ chối sai bản chất.

### 19.1. Ba lớp kết quả cần phân biệt

| Tình huống | Dữ liệu đã đổi chưa? | Hướng xử lý audit |
| --- | --- | --- |
| LWT trả `true` | Đã áp dụng theo ngữ nghĩa LWT | Ghi nhận accepted/committed |
| LWT trả `false` | Mutation này không áp dụng | Conflict; đối chiếu command ID trước khi phân loại retry |
| Timeout sau khi gửi | **Chưa biết chắc** từ phía client | Không khẳng định success hoặc reject; đối soát |
| Lỗi schema/auth trước khi thực thi hợp lệ | Không có thao tác dữ liệu thành công như mong đợi | Ghi log lỗi kỹ thuật, không giả thành sự kiện nghiệp vụ |
| Projector/notification lỗi sau commit chính | Commit chính vẫn có thể tồn tại | Retry bước phụ theo command/event ID ổn định |

### 19.2. Một cột last_command_id chỉ nhớ một lệnh

`last_command_id` có thể giúp đối chiếu lệnh vừa áp dụng, nhưng khi một lệnh khác đến và cập nhật cột đó, giá trị cũ mất. Với yêu cầu **deduplicate hàng nghìn command**, cần một **ledger/event log** có khóa, retention và quy trình ghi bền vững riêng.

Khi replay/retry, **không tự cấp audit_id mới cho cùng một thay đổi đã được chấp nhận** nếu điều đó dẫn đến hai event nghiệp vụ. Chính sách ID/sequence phải được thiết kế trước.

## 20. Không dùng callback để thực hiện side effect không kiểm soát

Entity callback có thể hấp dẫn để:

~~~text
BeforeSave(entity):
  -> gửi Kafka event
  -> gọi API bên ngoài
  -> ghi bảng audit khác
  -> gửi email
~~~

Nhưng một callback phía ứng dụng có thể chạy **trước khi Cassandra xác nhận mutation**. Nếu mutation bị từ chối bởi `IF`, timeout hoặc lỗi, side effect ở callback vẫn có thể đã xảy ra. Ngoài ra, callback có thể được gọi nhiều lần khi save được retry.

**Khuyến nghị thiết kế:** callback auditing nên tập trung vào **gán/chuẩn hóa metadata và kiểm tra cục bộ**, không tùy tiện phát side effect khó rollback như email hoặc message mà không có giao thức outbox/idempotency.

Nếu vẫn có event listener/callback chuyên biệt, phải mô tả:

- Nó chạy **trước hay sau** câu CQL?
- Có biết mutation đã thật sự được applied không?
- Có chạy cho `@Query`/`CqlSession` raw không?
- Khi lỗi/timeout/retry, có thể chạy nhiều lần không?
- Side effect có ID ổn định để deduplicate không?

Không một tên như `AfterSave` tự chứng minh “đây là giao dịch đã commit toàn cục” nếu framework/database không có bảo đảm như vậy.

## 21. Cách rà soát một codebase có nhiều đường ghi

Đừng chỉ tìm annotation `@CreatedDate`; hãy liệt kê **mọi cách dữ liệu có thể được mutation**:

1. `save`/`saveAll`/`delete` của repository đồng bộ và reactive.
2. `CassandraTemplate` insert/update/delete, entity update và query-based update.
3. `@Query` chứa `INSERT`, `UPDATE`, `DELETE`, `BATCH` hoặc modifying annotation.
4. `CqlTemplate`, `CqlOperations` và những đoạn CQL text.
5. `CqlSession.execute(...)`, `executeAsync(...)`, prepared/bound statements.
6. CQL batch, LWT, TTL, counter updates và những mutation chuyên biệt.
7. Job scheduler, migration, import/export, ETL, admin scripts, `cqlsh`.
8. Các dịch vụ khác sở hữu quyền ghi vào cùng bảng/keyspace.

**Lưu ý phạm vi bài:** đây là phương pháp review. Worker STEP 4 chỉ viết tài liệu, không thực hiện tìm kiếm hay đọc code của repository thực tế.

### 21.1. Ma trận review cho mỗi đường ghi

| Câu hỏi | Ví dụ câu trả lời cần ghi lại |
| --- | --- |
| Chủ thể nào gọi đường ghi? | HTTP user, service account, job |
| Nguồn actor đáng tin là gì? | Spring Security principal, command envelope đã xác thực |
| CQL/operation thực thi gì? | `UPDATE orders_by_id SET state = ? ...` |
| Có đi qua entity callbacks không? | Đã xác minh bằng integration test |
| Khi tạo có set created fields không? | `created_at`, `created_by` có trong insert |
| Khi sửa có preserve created fields không? | UPDATE không ghi `created_*` |
| Khi sửa có set modified fields không? | `updated_at`, `updated_by` cùng statement |
| Khi CAS false có cập nhật audit không? | Không; conflict xử lý riêng |
| Khi DELETE/TTL audit còn đâu? | Soft delete/event trail theo retention |
| Khi timeout/retry có đối soát không? | Command ID, idempotency ledger |
| Khi ghi nhiều bảng có handoff bền vững không? | Outbox/event source/reconciliation |
| Bằng chứng test nào? | Tên integration test, CQL thực tế, observed values |

Review cần gắn với **đúng query shape và đúng phiên bản framework**, không chỉ đánh dấu “OK” vì đã thấy một annotation.

## 22. Kiểm thử tích hợp: entity save và CQL trực tiếp cho kết quả khác nhau

### 22.1. Chuẩn bị fixture

Tạo bảng trong một Cassandra test cluster có keyspace `app_ks` và replication phù hợp. Dùng `CqlSession` để đọc lại kết quả, cùng một repository được bật auditing nếu phiên bản hỗ trợ.

Test hai nhánh:

1. Dùng `repository.save(newEntity)`; kiểm tra Spring auditing có set các trường cần thiết theo cấu hình.
2. Dùng CQL trực tiếp `UPDATE ... SET state = ?`; kiểm tra **không có phép màu tự bổ sung** `updated_at`/`updated_by`.
3. Dùng CQL trực tiếp **đã thêm audit fields**; kiểm tra những giá trị này được persist.

**Mục đích:** chứng minh ranh giới của pipeline bằng kết quả thật, không chỉ phỏng đoán từ tên method.

### 22.2. Ví dụ integration test cho direct CQL

Giả sử đã có `CqlSession session` trong test fixture và có một hàng đã tạo:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

@Test
void rawCqlMustWriteAuditColumnsExplicitly() {
    UUID id = UUID.randomUUID();
    Instant created = Instant.parse("2026-11-25T08:00:00Z");
    Instant changed = Instant.parse("2026-11-25T09:00:00Z");

    PreparedStatement insert = session.prepare(
        "INSERT INTO app_ks.orders_by_id " +
        "(order_id, state, version, created_at, created_by, " +
        " updated_at, updated_by) " +
        "VALUES (?, 'CREATED', 1, ?, 'creator', ?, 'creator')"
    );
    session.execute(insert.bind(id, created, created));

    PreparedStatement raw = session.prepare(
        "UPDATE app_ks.orders_by_id " +
        "SET state = 'PAID' WHERE order_id = ?"
    );
    session.execute(raw.bind(id));

    PreparedStatement read = session.prepare(
        "SELECT state, created_at, created_by, " +
        "updated_at, updated_by FROM app_ks.orders_by_id " +
        "WHERE order_id = ?"
    );

    Row afterRaw = session.execute(read.bind(id)).one();
    assertNotNull(afterRaw);
    assertEquals("PAID", afterRaw.getString("state"));
    assertEquals(created, afterRaw.getInstant("updated_at"));
    assertEquals("creator", afterRaw.getString("updated_by"));

    PreparedStatement explicit = session.prepare(
        "UPDATE app_ks.orders_by_id " +
        "SET state = 'CANCELLED', " +
        "updated_at = ?, updated_by = ? WHERE order_id = ?"
    );
    session.execute(explicit.bind(changed, "operator", id));

    Row afterExplicit = session.execute(read.bind(id)).one();
    assertNotNull(afterExplicit);
    assertEquals(changed, afterExplicit.getInstant("updated_at"));
    assertEquals("operator", afterExplicit.getString("updated_by"));
    assertEquals(created, afterExplicit.getInstant("created_at"));
    assertEquals("creator", afterExplicit.getString("created_by"));
}
~~~

Test dùng Java driver 4.x và JUnit 5, với session/schema do fixture tạo. Các thời điểm được chọn ở độ chính xác mili giây để so sánh với CQL `timestamp`; test cần dùng consistency phù hợp, làm sạch dữ liệu và không chạy trên production.

### 22.3. Những test không nên thiếu

| Tình huống | Kỳ vọng |
| --- | --- |
| Entity save lần đầu với auditing bật | Created fields được điền theo hợp đồng |
| Entity save lần sau | Created fields ổn định; modified fields theo chính sách |
| Raw CQL UPDATE chỉ đổi state | Audit fields không tự được Spring bổ sung |
| Raw CQL UPDATE có audit binds | Audit fields thay đổi cùng mutation |
| `@Query/@Modifying` tùy biến | Kiểm tra CQL thật và giá trị audit, không suy từ annotation |
| Template update theo query | Xác minh callback hoặc bổ sung audit tường minh |
| Reactive save | Auditor được resolve đúng từ context tương ứng |
| Java driver `executeAsync` | Giá trị actor/command ID được bind trước khi gửi |
| LWT true | State/version và modified fields đổi nhất quán |
| LWT false | Không biến actor của request thua thành last modifier |
| LWT timeout | Không ghi audit thành công giả; có trạng thái đối soát |
| Retry cùng command | Không thêm hai event nghiệp vụ chỉ vì subscribe lại |
| DELETE hàng | Biết metadata hiện tại có thể mất, dùng event/soft delete nếu cần |
| TTL hết hạn | Không giả callback Spring tự tạo audit event |
| Batch hai mutation | Mỗi mutation có metadata cần thiết, hiểu phạm vi batch |
| Job admin ghi trực tiếp | Có actor/service identity và quy trình audit riêng |

### 22.4. Unit test không chứng minh phạm vi auditing thật

Mock repository có thể chứng minh service đã gọi `save`, nhưng không chứng minh callback auditing có được gắn vào mapping pipeline hay không. Mock `CqlSession` có thể chứng minh method truyền tham số, nhưng không chứng minh CQL và kiểu kết quả LWT được Cassandra chấp nhận.

Vì vậy cần **integration test trên Cassandra thật với đúng driver/framework version**, kết hợp assertion về dữ liệu đã lưu và những trường hợp cạnh tranh khi yêu cầu.

## 23. Kiểm thử actor và đồng hồ một cách ổn định

### 23.1. Clock cố định

Khi tạo audit metadata bằng ứng dụng:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock testClock = Clock.fixed(
    Instant.parse("2026-11-25T09:00:00Z"),
    ZoneOffset.UTC
);
Instant auditTime = Instant.now(testClock);
~~~

Điều này tránh test bị flaky do phụ thuộc vào `Instant.now()` của hai lời gọi ở hai thời điểm khác nhau. Nhưng với timestamp do Spring auditing provider tạo, phải inject/thiết lập **chính provider đó** trong test; inject một `Clock` khác mà provider không dùng sẽ không giúp gì.

### 23.2. Actor khác nhau theo đường đi

Test nên có ít nhất:

- HTTP user `alice` tạo, `bob` sửa.
- Background job `reconciliation-service` cập nhật theo quyền service.
- Reactive request có context `charlie`, dù operator chuyển thread.
- Request giả mạo body `updatedBy=admin` nhưng principal thực `alice` — audit phải ghi nguồn identity được xác thực theo chính sách.
- Authentication không có: API phải từ chối hoặc dùng actor kỹ thuật có định nghĩa rõ, không tự ghi chuỗi mơ hồ như `unknown` cho thao tác quan trọng.

Audit actor là một phần của **hợp đồng tin cậy và ủy quyền**, không chỉ là một chuỗi Java bất kỳ.

## 24. Tác động vận hành và bảo mật

### 24.1. Không bật audit theo cách làm tăng dữ liệu quá mức

Một cột `updated_by` có chi phí nhỏ, nhưng **event audit đầy đủ** có thể tăng đáng kể write volume, partition size, replication và retention. Thiết kế theo use case:

- Metadata hiện tại có thể lưu cùng entity chính.
- Audit timeline cần partition key theo đối tượng/ngày/bucket phù hợp, tránh partition vô hạn.
- Event payload chỉ nên chứa dữ liệu cần để điều tra, không log mật khẩu, token hoặc PII không cần thiết.
- Dùng paging và projection khi đọc lịch sử; không tải toàn bộ event thành `List`.
- Có chính sách retention, mã hóa, quyền đọc/ghi, kiểm soát thao tác xóa và giám sát.

### 24.2. Không dùng audit để che vấn đề consistency

Một `updated_at` được gắn ở phía app **không tạo read-after-write guarantee** ở mọi replica/datacenter. Hãy chọn read/write consistency theo topology, hiểu khác biệt của `LOCAL_QUORUM` giữa các DC và xử lý timeout.

Một `updated_by` đúng cũng không ngăn hai writer cùng ghi đè dữ liệu. Khi cần kiểm soát state transition hoặc version, sử dụng **LWT/CAS** hay kiến trúc phân xử khác.

### 24.3. Observability cho audit coverage

| Chỉ số/kiểm soát | Mục đích |
| --- | --- |
| Số mutation theo đường repository/template/raw CQL | Biết tỷ trọng đường có/không callback |
| Tỷ lệ bản ghi thiếu created/modified metadata | Phát hiện lỗ hổng coverage |
| Tỷ lệ request không xác định được actor | Phát hiện lỗi security/context propagation |
| LWT `[applied] = false` và timeout | Phân biệt conflict với lỗi điều kiện chưa rõ |
| Pending audit/outbox/reconciliation | Biết event phụ có bị trễ/mất không |
| Retry/duplicate command IDs | Phát hiện phát audit lặp |
| Partition/tombstone/TTL metrics | Phát hiện vấn đề lưu trữ và truy vấn audit |
| Cross-DC failover events | Đánh giá tính sẵn có của metadata sau chuyển vùng |

Đừng chỉ đo “bao nhiêu callback đã chạy” rồi suy ra “bao nhiêu mutation Cassandra đã commit”: callback trước ghi có thể chạy trong request thất bại, còn mutation raw có thể commit mà không gọi callback.

## 25. Sai lầm thường gặp

| Hiểu nhầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| “Bật `@EnableCassandraAuditing` là mọi CQL được audit.” | Raw CQL thiếu modified fields | Rà soát từng đường ghi và bind metadata |
| “`@LastModifiedDate` là database trigger.” | Dựa vào cơ chế không tồn tại | Hiểu auditing chạy trong pipeline Spring Data |
| “`@Query UPDATE` tự gắn updated_by.” | Không lưu người sửa | Thêm audit binds trong câu CQL hoặc dùng path có callback được kiểm chứng |
| “CqlTemplate dùng Spring nên có toàn bộ entity callbacks.” | Bỏ sót metadata | Test thực tế CQL và callback |
| “save có audit nghĩa là hàng mới thật sự chưa tồn tại.” | Có thể upsert làm sai created fields | Phân biệt is-new trong framework và `IF NOT EXISTS` ở Cassandra |
| “updated_at là write timestamp dùng để hòa giải state.” | Hiểu sai xung đột | Phân biệt CQL timestamp với `WRITETIME` |
| “Auditing thay optimistic locking.” | Lost update vẫn xảy ra | Dùng `IF state/version` nếu cần |
| “CAS false vẫn phải ghi updated_by của người gọi.” | Audit báo sai ai đã sửa | Không cập nhật last-modified cho mutation không áp dụng |
| “Timeout có nghĩa chắc chắn chưa commit.” | Audit/ retry mâu thuẫn | Đối soát bằng command ID/nguồn sự thật |
| “Ghi state rồi ghi audit ở câu tiếp là nguyên tử.” | Thiếu audit khi bước hai lỗi | Cùng statement cho metadata; workflow bền vững cho event |
| “LOGGED BATCH tạo transaction SQL cho mọi bảng.” | Tuyên bố isolation sai | Tuân thủ phạm vi atomicity Cassandra và giới hạn CQL |
| “Reactive cancel rollback Cassandra.” | Sai trạng thái sau disconnect | Thiết kế idempotency và phục hồi |
| “@CreatedBy được lấy từ JSON updatedBy.” | Giả mạo identity | Dùng principal/service identity đáng tin |
| “TTL tự kích hoạt callback audit khi hết hạn.” | Mất sự kiện expiry | Tạo xử lý expiry riêng nếu nghiệp vụ yêu cầu |
| “Xóa entity vẫn còn audit trong chính entity.” | Không còn lịch sử | Event trail/soft delete/retention phù hợp |
| “@Version trên một đường ghi bảo vệ mọi raw CQL.” | Writer ngoài luồng phá concurrency | Thống nhất policy cho mọi write path |

## 26. Bài thực hành tổng hợp: kiểm toán mọi đường ghi

**Bối cảnh:** hệ thống đơn hàng có API tạo, thanh toán, hủy và một job định kỳ điều chỉnh trạng thái. Phần lớn CRUD dùng `CassandraRepository`, nhưng một số thao tác tối ưu dùng `@Query`, `CqlTemplate` và `CqlSession`.

**Yêu cầu nghiệp vụ:**

- Tạo đơn lưu đúng `created_at`/`created_by`.
- Mọi **thay đổi thành công** lưu đúng `updated_at`/`updated_by`.
- Tạo lần hai cùng ID không ghi lại metadata tạo.
- Thanh toán thất bại vì version/state cũ không ghi lại last-modifier của người thua.
- Một job/service account được định danh rõ, không giả làm người dùng.
- Nếu cần lịch sử mọi hành động, có nguồn audit event bền vững.

**Các bước:**

1. Tạo bảng `orders_by_id` và cấu hình Cassandra auditing entity phù hợp phiên bản.
2. Tạo entity `OrderRow` với bốn annotation created/modified; tạo auditor provider từ nguồn tin cậy.
3. Ghi bằng `repository.save(entity)` và đọc lại bằng CQL để xác minh các trường audit.
4. Ghi bằng một `@Query UPDATE` chỉ đổi state; quan sát raw CQL **không tự điền audit fields**.
5. Sửa `@Query` hoặc chuyển sang gateway CQL có bind `updated_at`/`updated_by`.
6. Ghi bằng `CqlTemplate`/`CqlSession` và kiểm tra cùng tiêu chí.
7. Thêm lệnh `INSERT IF NOT EXISTS` có created/updated metadata; kiểm tra `[applied]` và giữ metadata ban đầu khi tạo trùng.
8. Thêm `UPDATE ... IF version = ?` có modified metadata cùng statement; tạo hai writer cạnh tranh và chứng minh writer thua không trở thành last-modifier.
9. Thử timeout sau khi gửi LWT; dùng command ID để đối soát, không tự log accepted hoặc rejected chắc chắn.
10. Thử reactive gateway dùng `executeAsync(...)` và truyền actor từ security/reactive context theo policy.
11. Thử một batch có hai mutation; xác định metadata của mỗi mutation và giới hạn atomicity.
12. Xóa/TTL một hàng test; giải thích tại sao callback Spring không tự sinh event “đã hết hạn”.
13. Thêm `order_audit_by_order` khi yêu cầu timeline; chọn nguồn sự thật và worker đối soát nếu ghi hai bảng không nguyên tử.
14. Viết ma trận review cho mọi đường ghi của ứng dụng, kể cả scheduler/admin script và dịch vụ khác có quyền ghi.
15. Thu thập các chỉ số missing metadata, actor resolution failure, CAS conflict, reconciliation backlog, latency và chi phí event.

**Tiêu chí đạt:** người học phân biệt đúng **auditing của entity pipeline** với **auditing của câu CQL trực tiếp**, không để mutation quan trọng thiếu actor/thời điểm, không gắn metadata sai cho CAS thất bại, và không tuyên bố một event audit đa bảng đã commit nếu thiếu cơ chế bảo đảm.

## 27. Câu hỏi tự kiểm tra

1. `@CreatedDate` và `@LastModifiedBy` được xử lý ở tầng Spring hay Cassandra server?
2. Vì sao `CqlSession.execute(...)` không tự kích hoạt callback auditing của `OrderRow`?
3. Khi nào `repository.save(entity)` có thể đi qua auditing pipeline?
4. Vì sao cần phân biệt cách framework nhận diện entity mới với việc hàng đã tồn tại trong Cassandra?
5. Vì sao `@Query UPDATE` chỉ ghi `state` có thể bỏ sót `updated_at`?
6. Vì sao `CassandraTemplate.update(entity)` và query-based update cần kiểm tra riêng?
7. Khi nào nên bind `updated_by` trong cùng UPDATE CQL với `state`?
8. Vì sao không nên lấy `updatedBy` trực tiếp từ HTTP body chưa được xác thực?
9. Trong reactive WebFlux, vì sao một ThreadLocal tùy ý có thể không đủ cho auditor?
10. `WRITETIME(state)` có chứa identity người sửa hoặc lịch sử các giá trị state không?
11. Vì sao `created_at` không nên bị thay đổi khi UPDATE đơn hàng?
12. `IF NOT EXISTS` giúp giải quyết ranh giới “created” nào mà repository upsert không tự bảo đảm?
13. Nếu một LWT trả `[applied] = false`, có nên ghi `updated_by` của người vừa thử không?
14. Timeout sau conditional write chứng minh mutation chưa áp dụng hay không?
15. `last_command_id` có thể giúp gì và vì sao nó không phải idempotency ledger đầy đủ?
16. Đặt `updated_at` trong cùng mutation với `state` giải quyết điều gì và **không** giải quyết điều gì?
17. Batch CQL có tự đi qua Spring Data entity callbacks cho từng mutation không?
18. Vì sao logged batch đa partition không được coi là transaction SQL có isolation?
19. Khi DELETE hàng, vì sao audit metadata nằm trong chính hàng có thể không còn?
20. Cassandra TTL có tự gọi entity lifecycle callback khi hết hạn không?
21. Vì sao UNSET một cột audit khác với bind NULL vào cột đó?
22. Một callback trước save gửi Kafka event có thể gây sai lệch lịch sử như thế nào?
23. Audit metadata hiện tại khác gì với event sourcing hoặc audit trail append-only?
24. Khi cập nhật state ở bảng A thành công nhưng ghi audit event ở bảng B lỗi, cần cơ chế phục hồi nào?
25. Vì sao audit actor của background job cần phân biệt với người dùng trực tiếp?
26. Các integration test nào giúp chứng minh coverage của từng đường ghi hơn là chỉ mock repository?
27. Nếu nhiều dịch vụ cùng ghi một keyspace, vì sao bật auditing trong một service là chưa đủ?

**Ghi nhớ:** **auditing của Spring Data Cassandra gắn với những đường thao tác đi qua entity mapping/callback phù hợp; nó không phải trigger của Cassandra áp dụng lên mọi câu CQL.** Khi ghi bằng `@Query`, `CqlTemplate`, `CqlSession`, async/reactive hay batch, phải **kiểm tra và ghi các cột audit tường minh theo hợp đồng**. Với LWT, metadata của mutation chỉ được áp dụng nếu điều kiện thỏa; `false` và timeout cần xử lý khác nhau. Nếu cần lưu lịch sử bất biến thay vì người sửa gần nhất, phải thiết kế event/audit trail, idempotency và quy trình phục hồi nhiều bảng. Mọi lựa chọn vẫn phải tôn trọng **partition key, consistency, paging, TTL/tombstone và hiệu năng của mô hình dữ liệu phân tán**.
