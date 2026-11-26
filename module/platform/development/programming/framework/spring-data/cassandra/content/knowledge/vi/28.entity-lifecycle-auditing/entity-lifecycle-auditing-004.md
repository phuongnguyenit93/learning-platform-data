# Thay đổi entity trước chuyển đổi và điều chỉnh statement trước ghi trong Spring Data Cassandra

## 1. Vấn đề: một thay đổi đúng trong Java chưa chắc được lưu vào Cassandra

Ứng dụng Spring Boot dùng **Spring Data Cassandra** để lưu đơn hàng. Trước mỗi lần ghi, đội phát triển muốn:

- Chuẩn hóa `state`, chẳng hạn chuyển `" created "` thành `"CREATED"`.
- Điền thông tin audit như `createdAt`, `updatedAt` và người thực hiện.
- Ghi một số bản ghi với TTL riêng hoặc consistency level rõ ràng.
- Kiểm tra câu CQL cuối cùng trước khi gửi tới cluster.

Một lập trình viên thay đổi `entity.setState("CREATED")` trong callback `BeforeSaveCallback` và nghĩ rằng giá trị mới chắc chắn được lưu. Tuy nhiên, với Spring Data Cassandra, **`BeforeSaveCallback` chạy sau khi entity đã được chuyển thành CQL `Statement`**. Thay đổi entity tại thời điểm này **không tự sửa lại nội dung statement đã tạo**.

Đó là lý do cần phân biệt hai thời điểm:

1. **Trước chuyển đổi**: sửa dữ liệu entity để mapper dùng giá trị mới khi xây statement.
2. **Sau chuyển đổi, trước ghi**: quan sát/kiểm tra statement đã được tạo; muốn thay đổi CQL hoặc execution options phải dùng đúng API có khả năng cấu hình/thay thế statement, không chỉ sửa entity đã được mapping.

Bài học thuộc chương **Vòng đời và auditing** của module **SPRING_DATA_CASSANDRA**. Phạm vi là entity mapping, repository, `CassandraTemplate` và truy vấn CQL khi truy cập Apache Cassandra theo thiết kế bảng phục vụ truy vấn, partition key, mức nhất quán, paging và hiệu năng trong môi trường dữ liệu phân tán.

**Mục tiêu:**

1. Mô tả được thứ tự `BeforeConvertCallback` → entity-to-statement conversion → `BeforeSaveCallback` → database write.
2. Viết callback sửa và validate entity **trước khi converter đọc các property**.
3. Giải thích vì sao sửa entity tại `BeforeSaveCallback` không đảm bảo thay đổi dữ liệu trong statement.
4. Chọn `InsertOptions`, `UpdateOptions`, statement của Java driver hoặc custom gateway khi cần TTL, consistency, timeout hay CQL có điều kiện.
5. Phân biệt entity callbacks với lifecycle `ApplicationEvent`, auditing mặc định và reactive callbacks.
6. Kiểm thử giá trị thực sự được lưu vào Cassandra, thay vì chỉ nhìn object Java sau khi `save(...)`.

## 2. Sơ đồ pipeline ghi: điểm chặn trước và sau conversion

Với một đường ghi entity do Spring Data Cassandra quản lý, sơ đồ khái niệm:

~~~mermaid
flowchart TD
    A[Service gọi repository.save hoặc CassandraTemplate.insert/update] --> B[BeforeConvert event và EntityCallback]
    B --> C[Auditing callback và các callback theo thứ tự]
    C --> D[Converter ánh xạ entity thành CQL Statement]
    D --> E[BeforeSave event và BeforeSaveCallback]
    E --> F[Spring Data thực thi statement qua Cassandra driver]
    F --> G[Replica xử lý theo CQL và consistency]
    G --> H[AfterSave event / kết quả trả về]
~~~

Đây là **sơ đồ logic**; thứ tự chi tiết giữa từng event/callback và auditing phụ thuộc cách cấu hình, `Ordered` và phiên bản Spring Data. Hai mốc chắc chắn cần hiểu:

- `BeforeConvertCallback` chạy **trước** lúc mapper tạo `INSERT` hoặc `UPDATE` statement.
- `BeforeSaveCallback` nhận **statement đã tạo**, vì vậy chỉnh entity tại đây **không được converter chạy lại** chỉ bởi việc callback trả entity.

| Mốc | Đầu vào chính | Giá trị trả về | Ảnh hưởng đến CQL sắp thực thi |
| --- | --- | --- | --- |
| `BeforeConvertCallback<T>` | Entity, `CqlIdentifier tableName` | Entity cùng loại, có thể là instance mới | **Có**: mapper xây statement sau callback |
| Auditing callback | Entity và metadata mapping | Entity có thông tin audit | **Có**, khi chạy trước conversion |
| Entity-to-statement conversion | Entity đã được xử lý | CQL `Statement<?>` | Quyết định cột, giá trị và cấu trúc mutation |
| `BeforeSaveCallback<T>` | Entity, table name, `Statement<?>` | Entity | **Không tự động** làm statement đã xây phản ánh thay đổi mới của entity |
| Java driver execution | Statement đã hoàn tất | `ResultSet` hoặc async result | CQL gửi tới Cassandra |

**Không có một “transaction tự động quanh mọi callback”.** Nếu callback phát thêm câu CQL riêng hoặc gọi dịch vụ bên ngoài, những thao tác đó không mặc nhiên commit/rollback cùng mutation chính.

## 3. Schema minh họa và ranh giới bảng theo truy vấn

Giả sử API cần tìm đơn hàng theo `order_id`:

~~~sql
-- app_ks là keyspace đã được tạo với replication phù hợp môi trường.
CREATE TABLE app_ks.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    state text,
    note text,
    created_at timestamp,
    updated_at timestamp,
    created_by text,
    updated_by text
);
~~~

| Cột | Vai trò | Callback/auditing thường liên quan |
| --- | --- | --- |
| `order_id` | Primary key và partition key | Phải ổn định trước khi ghi |
| `customer_id` | Cột thường | Không tự chuyển thành khóa tìm theo customer |
| `state` | Cột thường | Chuẩn hóa, validate trước conversion |
| `note` | Cột thường | Phân biệt null, UNSET, giá trị cụ thể |
| `created_at` | Cột thường | `@CreatedDate` |
| `updated_at` | Cột thường | `@LastModifiedDate` |
| `created_by` | Cột thường | `@CreatedBy` |
| `updated_by` | Cột thường | `@LastModifiedBy` |

Một truy vấn hợp lệ theo key:

~~~sql
SELECT order_id, state, created_at, updated_at
FROM app_ks.orders_by_id
WHERE order_id = ?;
~~~

**Callback không làm thay đổi quy luật Cassandra:** nếu ứng dụng cần liệt kê đơn theo khách hàng/thời gian, phải thiết kế bảng phục vụ truy vấn đó hoặc một index phù hợp. Không nên dùng lifecycle callback để âm thầm phát thêm nhiều truy vấn quét rộng.

## 4. Entity ánh xạ bằng Spring Data Cassandra

Ví dụ một entity mutable để làm rõ tác động của callback:

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

    @Column("customer_id")
    private UUID customerId;

    @Column("state")
    private String state;

    @Column("note")
    private String note;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @LastModifiedDate
    @Column("updated_at")
    private Instant updatedAt;

    @CreatedBy
    @Column("created_by")
    private String createdBy;

    @LastModifiedBy
    @Column("updated_by")
    private String updatedBy;

    protected OrderRow() {}

    public OrderRow(UUID orderId, UUID customerId,
                    String state, String note) {
        this.orderId = orderId;
        this.customerId = customerId;
        this.state = state;
        this.note = note;
    }

    public UUID getOrderId() { return orderId; }
    public UUID getCustomerId() { return customerId; }
    public String getState() { return state; }
    public String getNote() { return note; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public String getCreatedBy() { return createdBy; }
    public String getUpdatedBy() { return updatedBy; }

    public void setState(String state) { this.state = state; }
    public void setNote(String note) { this.note = note; }
}
~~~

Ví dụ cố ý không tự đặt `createdAt` hoặc `updatedAt` trong constructor: bài học sẽ dùng auditing callback để điền chúng.

**Điều kiện để chạy đúng:**

- Spring Data Cassandra/driver tương thích với phiên bản Spring Boot dự án.
- `CqlSession` và keyspace được cấu hình đúng; tên bảng `orders_by_id` tương ứng với schema trong keyspace đang dùng.
- Auditing phải được bật nếu muốn các annotation thời gian/người thực hiện có hiệu lực.
- Khi kiểm thử entity immutable, phải dùng constructor/copy method mà converter hỗ trợ; không dựa vào setter không tồn tại.

## 5. BeforeConvertCallback: thay đổi entity trước khi tạo statement

Spring Data Cassandra định nghĩa callback:

~~~java
package org.springframework.data.cassandra.core.mapping.event;

// Chữ ký API rút gọn để giải thích, không phải mã cần tự khai báo:
public interface BeforeConvertCallback<T> {
    T onBeforeConvert(T entity, CqlIdentifier tableName);
}
~~~

Chú ý đây là **chữ ký minh họa**; interface thực tế mở rộng `EntityCallback<T>` và do thư viện cung cấp. Trong Spring Data Cassandra sử dụng Java driver 4.x, `CqlIdentifier` nằm trong package `com.datastax.oss.driver.api.core`.

### 5.1. Viết một callback chuẩn hóa state

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import org.springframework.core.annotation.Order;
import org.springframework.data.cassandra.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
@Order(50)
public final class NormalizeOrderBeforeConvert
        implements BeforeConvertCallback<OrderRow> {

    private static final Set<String> VALID_STATES =
        Set.of("CREATED", "PAID", "CANCELLED");

    @Override
    public OrderRow onBeforeConvert(
            OrderRow entity, CqlIdentifier tableName) {
        Objects.requireNonNull(entity, "entity");
        Objects.requireNonNull(entity.getOrderId(), "orderId");

        String normalized = Objects.requireNonNull(
            entity.getState(), "state")
            .strip()
            .toUpperCase(Locale.ROOT);

        if (!VALID_STATES.contains(normalized)) {
            throw new IllegalArgumentException(
                "Unknown state: " + normalized);
        }

        entity.setState(normalized);
        return entity;
    }
}
~~~

**Ý nghĩa:**

1. Bean được đăng ký trong `ApplicationContext` qua `@Component`.
2. Kiểu generic `BeforeConvertCallback<OrderRow>` giới hạn callback vào domain type phù hợp.
3. Converter nhận **entity được trả về** và đọc giá trị `state` sau khi chuẩn hóa.
4. `@Order(50)` giúp nêu thứ tự tương đối với những entity callback khác có order rõ ràng; auditing của Spring Data Cassandra thường dùng order `100`.
5. Callback trả lại **entity**, không trả `Statement`.

Nếu gọi:

~~~java
OrderRow order = new OrderRow(
    orderId, customerId, " created ", null);

repository.save(order);
~~~

thì ở đường save entity được Spring Data quản lý, callback chuẩn hóa trước khi converter xây CQL, nên **cột `state` được gửi với giá trị `"CREATED"`**, nếu không có callback sau đó thay đổi lại.

**Không dùng callback để bí mật thực hiện business state transition** như `PAID → CANCELLED`. Chuẩn hóa định dạng hoặc validate cấu trúc là phù hợp; điều kiện tranh chấp phải được bảo vệ tại Cassandra nếu nhiều writer có thể cập nhật cùng hàng.

### 5.2. Callback chạy khi nào?

Callback được tích hợp trong các đường ghi entity của `CassandraTemplate`/repository tương ứng. Với truy vấn CQL trực tiếp qua `CqlSession.execute(...)`, bạn **không đi qua entity converter**, nên callback này không được tự động gọi.

Không được giả định mọi `@Query` modifying method, bulk update, raw CQL hoặc batch tự động phát cùng lifecycle callback. Tên API có chữ “save/update” không phải bằng chứng; hãy kiểm thử đúng đường ghi trong phiên bản framework.

## 6. Entity immutable: trả một bản mới, không ép dùng setter

Với immutable object, callback có thể **trả một instance mới** để mapper chuyển đổi, thay vì sửa trực tiếp. Ví dụ ý tưởng:

~~~java
// Kiểu immutable minh họa, có withState(String) tạo bản sao mới.
@Override
public ImmutableOrder onBeforeConvert(
        ImmutableOrder entity, CqlIdentifier tableName) {
    String next = entity.state()
        .strip()
        .toUpperCase(Locale.ROOT);
    return entity.withState(next);
}
~~~

Ở đây `ImmutableOrder` và `withState` là **kiểu/helper do ứng dụng định nghĩa**, không phải class có sẵn trong Spring Data. Phần quan trọng là:

- Không cần mutate entity tại chỗ.
- Callback trả instance mang dữ liệu mới **trước mapping**.
- Converter phải biết ánh xạ immutable entity, constructor và các property của nó.
- Đừng đưa object mutable dùng chung cho nhiều reactive subscription rồi sửa nó từ nhiều callback.

Nếu dùng Java `record` hoặc constructor binding, hãy xác minh phiên bản Spring Data Cassandra hỗ trợ cách ánh xạ đã chọn, cùng các trường audit có thể được cập nhật qua copy/constructor. Không viết callback trả một type khác hẳn rồi mong mapper bỏ qua generic contract.

## 7. Auditing tự động cũng diễn ra trước conversion

Spring Data Cassandra hỗ trợ auditing cho các annotation:

| Annotation | Giá trị phổ biến | Ý nghĩa |
| --- | --- | --- |
| `@CreatedDate` | `Instant createdAt` | Thời điểm entity được xác định là mới |
| `@LastModifiedDate` | `Instant updatedAt` | Thời điểm entity được đánh dấu đã chỉnh sửa |
| `@CreatedBy` | `String createdBy` | Actor tạo bản ghi |
| `@LastModifiedBy` | `String updatedBy` | Actor chỉnh sửa gần nhất |

Để bật auditing đồng bộ:

~~~java
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.cassandra.config.EnableCassandraAuditing;

@Configuration(proxyBeanMethods = false)
@EnableCassandraAuditing
public class CassandraAuditingConfig {

    @Bean
    AuditorAware<String> auditorAware() {
        // Demo: production phải lấy actor từ ngữ cảnh tin cậy.
        return () -> Optional.of("order-service");
    }
}
~~~

Auditing callback được framework đăng ký và tham gia **before-convert processing**. Vì vậy, khi converter xây `Statement`, các property audit có thể đã được điền.

**Giới hạn cần nhớ:**

- `@CreatedDate` không phải bằng chứng row chưa từng tồn tại trong Cassandra.
- Việc xác định **entity mới hay cũ** phụ thuộc chiến lược nhận diện newness/ID và mapping của Spring Data.
- Không tự động suy từ `@LastModifiedDate` rằng mọi statement đều có **Cassandra write timestamp** tương ứng hoặc được CAS bảo vệ.
- `createdBy/updatedBy` chỉ chính xác nếu `AuditorAware` thật sự phản ánh principal/actor của request, chứ không phải một chuỗi demo cố định.
- Auditing mang ý nghĩa **metadata của bản ghi hiện tại**, không thay thế lịch sử sự kiện/audit trail bất biến.

### 7.1. Thứ tự với custom callback

Theo tài liệu Spring Data Cassandra, auditing callback thường có order `100`, còn callback thông thường khi không đặt order thường chạy ở `Ordered.LOWEST_PRECEDENCE`. Nếu logic cần chạy **trước** auditing, có thể dùng `@Order(50)`; nếu cần kiểm tra giá trị audit đã gắn **trước conversion**, có thể đăng ký callback theo order phù hợp lớn hơn `100`.

Tuy nhiên, không nên gắn hai callback có cùng order rồi phụ thuộc vào thứ tự ngẫu nhiên. Nếu một property được cả auditing và callback custom sửa, hãy **quy định một nơi sở hữu** và viết integration test xác nhận giá trị cuối.

### 7.2. Actor trong ứng dụng reactive

Nếu dùng reactive repository/template, auditing có đường cấu hình riêng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.config.EnableReactiveCassandraAuditing;
import org.springframework.data.domain.ReactiveAuditorAware;
import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableReactiveCassandraAuditing
public class ReactiveCassandraAuditingConfig {
    // Đăng ký ReactiveAuditorAware<String> trong ứng dụng reactive.
}
~~~

Với reactive auditing, actor có thể đến từ **Reactor Context/SecurityContext** theo thiết kế bảo mật của ứng dụng. Không dựa vào một `ThreadLocal` thuần như thể toàn bộ reactive chain chắc chắn chạy trên một thread. Nếu dùng JavaConfig, cần đăng ký `ReactiveAuditorAware` phù hợp và xác minh principal được truyền đúng.

## 8. BeforeSaveCallback: kiểm tra statement sau khi mapping

Spring Data Cassandra cung cấp callback:

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.cql.Statement;
import org.springframework.data.cassandra.core.mapping.event.BeforeSaveCallback;
import org.springframework.stereotype.Component;

@Component
public final class InspectOrderBeforeSave
        implements BeforeSaveCallback<OrderRow> {

    @Override
    public OrderRow onBeforeSave(
            OrderRow entity,
            CqlIdentifier tableName,
            Statement<?> statement) {

        if (entity.getOrderId() == null) {
            throw new IllegalArgumentException(
                "Missing orderId before save");
        }

        // Kiểm tra metadata, không log nội dung field nhạy cảm.
        String statementType =
            statement.getClass().getSimpleName();

        if (statementType.isBlank()) {
            throw new IllegalStateException(
                "Unexpected statement type");
        }

        return entity;
    }
}
~~~

**Tại sao callback này khác `BeforeConvertCallback`?**

- Tham số thứ ba là **`Statement<?>` đã được converter tạo**.
- Callback phù hợp cho **quan sát, validation muộn hoặc bổ sung thông tin trên object trả về** khi phù hợp.
- Nó **không cung cấp một giá trị trả về kiểu `Statement`** để thay toàn bộ statement đã tạo.
- Nếu bạn sửa `entity.setState(...)` trong callback này, giá trị mới **không tự được thêm vào statement** vì mapping đã hoàn tất.

Điều này đặc biệt quan trọng khi đưa logic **auditing, masking hoặc tính toán cột** vào thời điểm sai.

## 9. Lỗi điển hình: sửa entity trong BeforeSave nhưng dữ liệu lưu vẫn cũ

Giả sử entity ban đầu có `state = CREATED`. Lập trình viên viết:

~~~java
@Component
public class IncorrectLateUpdate
        implements BeforeSaveCallback<OrderRow> {

    @Override
    public OrderRow onBeforeSave(
            OrderRow entity, CqlIdentifier table,
            Statement<?> statement) {
        entity.setState("PAID");
        return entity;
    }
}
~~~

**Đây là anti-pattern minh họa, không phải callback nên đăng ký trong production.** Giả sử converter đã xây CQL với `state = CREATED`:

~~~text
T0: Object Java: state = CREATED
T1: BeforeConvert -> không đổi state
T2: Converter xây INSERT/UPDATE chứa state = CREATED
T3: BeforeSave -> entity.setState(PAID)
T4: Driver gửi statement đã xây ở T2
T5: Đọc lại Cassandra -> có thể vẫn thấy CREATED
    dù object trả về trong Java đang chứa PAID.
~~~

Sự khác nhau giữa **object trong JVM** và **mutation đã gửi** tạo một bug khó phát hiện nếu test chỉ assert:

~~~java
OrderRow result = repository.save(entity);
assertEquals("PAID", result.getState());
~~~

Test này **không chứng minh** cột được persist là `PAID`. Muốn xác minh, phải đọc lại từ Cassandra qua query độc lập hoặc quan sát statement/bind values.

### 9.1. Cách sửa đúng

Di chuyển logic sửa `state` sang `BeforeConvertCallback` hoặc service **trước khi gọi repository/template**, rồi để converter tạo statement từ giá trị đã chuẩn bị.

Nếu mục tiêu là **thêm điều kiện CQL `IF version = ?`**, thay giá trị entity chưa đủ: cần **một write API có hỗ trợ conditional write rõ ràng**.

Nếu mục tiêu là **đổi consistency/TTL/tracing của query**, nên dùng **write options hoặc statement builder** thay vì hy vọng một callback nhận `Statement<?>` có thể thay thế đối tượng statement.

## 10. Statement của Java driver 4.x là immutable

Một lý do quan trọng khiến thao tác “sửa statement ngay trong BeforeSave” dễ sai: **statement objects trong Java driver 4.x được thiết kế bất biến**.

Ví dụ:

~~~java
BoundStatement bound = prepared.bind(orderId, "CREATED");

// SAI: kết quả trả về bị bỏ qua.
bound.setConsistencyLevel(
    DefaultConsistencyLevel.LOCAL_QUORUM);

session.execute(bound);
~~~

Code trên **không đảm bảo** bound statement thực thi có CL mới, vì `setConsistencyLevel(...)` trả **một instance mới**.

Cách đúng:

~~~java
BoundStatement bound = prepared.bind(orderId, "CREATED")
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM)
    .setTimeout(Duration.ofSeconds(2));

session.execute(bound);
~~~

Hoặc:

~~~java
bound = bound.setConsistencyLevel(
    DefaultConsistencyLevel.LOCAL_QUORUM);
session.execute(bound);
~~~

**Liên hệ với callback:** `BeforeSaveCallback.onBeforeSave(...)` nhận `Statement<?>` nhưng trả **entity**. Nếu callback gọi `statement.setConsistencyLevel(...)` rồi **không có đường giao lại statement mới cho executor**, mutation đang chờ ghi **không tự sử dụng đối tượng mới**. Không giả định việc cast hoặc gán lại biến local sẽ thay thế statement trong `CassandraTemplate`.

## 11. Điều chỉnh câu ghi bằng InsertOptions và UpdateOptions

Đối với entity write do Spring Data Cassandra quản lý, hãy dùng các **write options chính thức** khi cần chỉnh TTL, regular/serial consistency, timeout, tracing hoặc điều kiện được hỗ trợ.

Ví dụ dùng `CassandraTemplate` (hoặc `CassandraOperations`) với `InsertOptions`:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import java.time.Duration;
import org.springframework.data.cassandra.core.CassandraOperations;
import org.springframework.data.cassandra.core.InsertOptions;

public final class OrderWriteService {
    private final CassandraOperations operations;

    public OrderWriteService(CassandraOperations operations) {
        this.operations = operations;
    }

    public void insertTemporary(OrderRow order) {
        InsertOptions options = InsertOptions.builder()
            .ttl(Duration.ofHours(1))
            .consistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .build();

        operations.insert(order, options);
    }
}
~~~

**Vì sao đây là “điều chỉnh statement trước ghi” đúng chỗ?**

- `InsertOptions` được cung cấp **trước khi template hoàn tất thực thi mutation**.
- Template chịu trách nhiệm xây CQL/statement phù hợp với mapping và options.
- TTL và CL được nêu **tường minh trong API ghi**, thay vì cố thay đổi entity vào thời điểm đã quá muộn.

**Cần hiểu chính xác TTL:** TTL áp dụng cho các cell/mutation được ghi theo quy tắc Cassandra, không phải một “hẹn giờ JVM xóa object”. Nếu entity có nhiều cột, các cột được ghi chịu tác động theo write options và schema; kiểm tra thật kỹ trường null, TTL mặc định và kiểu dữ liệu.

### 11.1. UpdateOptions và update-only

~~~java
import org.springframework.data.cassandra.core.UpdateOptions;

UpdateOptions options = UpdateOptions.builder()
    .consistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM)
    .timeout(Duration.ofSeconds(2))
    .build();

operations.update(order, options);
~~~

Đoạn trích nằm trong scope có `operations` và `order`, cùng các imports liên quan. `UpdateOptions` có thể mang những tuỳ chọn khác như TTL hoặc `IF EXISTS` theo API version.

**Lưu ý:** `UPDATE` thông thường trong Cassandra có thể mang nghĩa upsert; nếu nghiệp vụ yêu cầu update-only, phải dùng API/CQL có `IF EXISTS` hợp lệ, và **đọc đúng kết quả điều kiện**. Không xem một object/entity được trả từ phương thức update là bằng chứng mọi CAS condition đã thỏa nếu chưa xác minh contract.

### 11.2. Không sử dụng callback để tự thay đổi routing/keyspace ngầm

Nếu cùng entity được ghi vào nhiều keyspace, hoặc tenant có bảng khác nhau, hãy cấu hình **đường ghi rõ ràng**, session và options phù hợp. Không tự thay table name/partition key sau conversion bằng cách thao tác một statement object bị cast tùy tiện.

Mỗi bảng Cassandra có partition key và quy tắc replication riêng. Sai keyspace không được sửa chỉ bằng callback “nhìn thấy tên bảng” rồi log cảnh báo.

## 12. Khi cần IF, USING TTL hoặc CQL tùy chỉnh: gateway rõ ràng

Có những điều chỉnh vượt khỏi một property entity:

- Thêm `IF state = ?`, `IF version = ?` để chống lost update.
- Tùy chỉnh tập cột cập nhật của PATCH theo ba trạng thái **KEEP/CLEAR/SET**.
- Dùng `USING TTL` cho một số cột cụ thể.
- Chọn regular/serial consistency đặc thù hoặc thực thi một conditional batch.
- Muốn đọc `ResultSet.wasApplied()` chính xác.

Khi đó một **custom repository fragment** hoặc gateway dùng `CqlSession` có thể rõ ràng hơn việc nhét logic vào lifecycle callback.

### 12.1. Ví dụ chuẩn bị UPDATE và đặt CL trước execute

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.util.UUID;

public final class OrderStateGateway {
    private final CqlSession session;
    private final PreparedStatement updateIfState;

    public OrderStateGateway(CqlSession session) {
        this.session = session;
        this.updateIfState = session.prepare(
            "UPDATE app_ks.orders_by_id " +
            "SET state = ?, updated_at = ? " +
            "WHERE order_id = ? " +
            "IF state = ?"
        );
    }

    public boolean changeState(
            UUID orderId, String expected,
            String next, Instant now) {
        BoundStatement bound = updateIfState.bind(
                next, now, orderId, expected)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setSerialConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_SERIAL);

        return session.execute(bound).wasApplied();
    }
}
~~~

Trong ví dụ, gateway tự tạo statement có điều kiện; `wasApplied()` là cờ CAS. **Đường này không tự phát `BeforeConvertCallback`/`BeforeSaveCallback` của entity**, vì không đi qua entity mapping. Nếu muốn cùng quy tắc chuẩn hóa, hãy **gọi một thành phần domain/shared normalizer tường minh** thay vì phụ thuộc callback chỉ chạy ở repository/template.

Chọn `LOCAL_QUORUM`/`LOCAL_SERIAL` chỉ là minh họa cho topology phù hợp; trong multi-DC cần đánh giá phạm vi đồng thuận và read-after-write. Không mặc định một LWT bảo vệ mọi bảng hoặc partition khác.

### 12.2. Statement option không thay thế business rule

`setConsistencyLevel(LOCAL_QUORUM)` yêu cầu phản hồi replica phù hợp nhưng **không chống ghi đè** nếu không có điều kiện `IF`. `setTimeout(...)` chỉ điều chỉnh khoảng chờ; timeout không chứng minh mutation chưa diễn ra.

**Bất biến nghiệp vụ** và **execution options** là hai quyết định khác nhau. Hãy đặt cả hai ở tầng API có contract rõ.

## 13. Lifecycle ApplicationEvent và EntityCallback khác nhau thế nào?

Spring Data Cassandra vẫn hỗ trợ các lifecycle events, thường qua `AbstractCassandraEventListener<T>`, song song với entity callbacks:

~~~java
import org.springframework.data.cassandra.core.mapping.event.AbstractCassandraEventListener;
import org.springframework.data.cassandra.core.mapping.event.BeforeSaveEvent;
import org.springframework.stereotype.Component;

@Component
public class OrderLifecycleListener
        extends AbstractCassandraEventListener<OrderRow> {
    @Override
    public void onBeforeSave(BeforeSaveEvent<OrderRow> event) {
        // Thường chỉ kiểm tra hoặc quan sát metadata.
        // Không mặc định thay đổi entity ở đây sẽ tái tạo statement.
    }
}
~~~

Ví dụ này cố ý chỉ quan sát, không thực thi thêm truy vấn. `BeforeSaveEvent` cũng được phát **sau khi converter xây statement**, nên vấn đề “sửa entity quá muộn” vẫn tồn tại.

### 13.1. So sánh hai cơ chế

| Tiêu chí | `ApplicationEvent` / listener | `EntityCallback` |
| --- | --- | --- |
| Cơ chế | Event publication/multicaster | Callback theo checkpoint xác định |
| Thay entity và trả instance mới | Không phải hợp đồng trọng tâm | **Có**, chính là giá trị trả về của callback |
| Thứ tự trong reactive pipeline | Event multicaster async có thể làm thứ tự khó đoán | Có reactive callbacks riêng, tham gia chain |
| Tính phù hợp cho immutable entity | Dễ gặp vấn đề nếu cố mutate object cũ | Trả entity mới phù hợp hơn |
| Thời điểm `BeforeSave` | Sau chuyển đổi | Sau chuyển đổi |
| Sử dụng khuyến nghị để thay dữ liệu trước mapping | Không phải lựa chọn ưu tiên | **`BeforeConvertCallback`** |

Nếu cấu hình `ApplicationEventMulticaster` với executor bất đồng bộ, listener có thể chạy trên thread khác. Do đó không dùng event handler để **đảm bảo sửa entity đồng bộ đúng trước write**, vì lúc đó statement có thể đã xây hoặc thậm chí request đang tiếp tục.

**Entity callbacks** được Spring Data thiết kế làm điểm can thiệp dữ liệu rõ ràng hơn; event vẫn hữu ích cho một số mục đích quan sát, nhưng không nên lẫn event với transaction/outbox.

### 13.2. Các event khác trong vòng đời

Những điểm thường gặp:

- `BeforeConvert`: trước chuyển entity thành statement.
- `BeforeSave`: statement đã được tạo, sắp thực thi.
- `AfterSave`: sau save qua template theo contract.
- `AfterLoad`: sau lấy `Row` từ Cassandra.
- `AfterConvert`: sau khi `Row` được ánh xạ thành entity.
- `BeforeDelete`/`AfterDelete`: trước/sau thao tác delete do template quản lý.

Không có bảo đảm rằng **mọi query SELECT CQL raw, batch hoặc @Query** đều phát toàn bộ event này. Kiểm tra theo API gọi và phiên bản.

## 14. ReactiveBeforeConvert và ReactiveBeforeSave

Reactive Spring Data Cassandra có callback riêng:

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import org.reactivestreams.Publisher;
import org.springframework.data.cassandra.core.mapping.event.ReactiveBeforeConvertCallback;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public final class ReactiveOrderNormalize
        implements ReactiveBeforeConvertCallback<OrderRow> {

    @Override
    public Publisher<OrderRow> onBeforeConvert(
            OrderRow entity, CqlIdentifier tableName) {
        return Mono.fromSupplier(() -> {
            String state = entity.getState()
                .strip().toUpperCase(java.util.Locale.ROOT);
            entity.setState(state);
            return entity;
        });
    }
}
~~~

**Ý nghĩa:** reactive callback trả một `Publisher<OrderRow>`; kết quả được dùng trong pipeline **trước conversion**. Nó không nên chạy blocking I/O như gọi `Future.get()` hoặc JDBC đồng bộ trên event-loop.

Reactive `BeforeSaveCallback` có chữ ký tương ứng:

~~~java
// Chữ ký rút gọn để diễn giải:
Publisher<T> onBeforeSave(
    T entity, CqlIdentifier tableName, Statement<?> statement);
~~~

Nó vẫn chạy **sau conversion**, nên sửa entity mà không thay statement đúng cách vẫn không đưa giá trị mới vào mutation đã xây.

**Lưu ý quan trọng về registration:** Spring Data phân biệt đường synchronous và reactive callbacks. Nếu ứng dụng có cả hai, phải đăng ký đúng loại callback cho mỗi đường ghi; một `BeforeConvertCallback` đồng bộ không mặc nhiên thay thế `ReactiveBeforeConvertCallback`.

### 14.1. Không làm tác dụng phụ trong callback reactive

Nếu một reactive save được subscribe lại do retry, callback có thể chạy lại. Vì vậy:

- Không sinh `UUID.randomUUID()` cho một sự kiện nghiệp vụ mới mỗi lần callback nếu command cần idempotent.
- Không gửi email/thông báo tới hệ khác trong `ReactiveBeforeConvertCallback`.
- Không đóng `CqlSession` dùng chung khi subscription bị hủy.
- Không giả định cancellation đảm bảo CQL chưa được Cassandra thực thi.

Callback nên **deterministic, nhanh và ít side effect**. Những tác vụ cần handoff bền vững phải nằm trong workflow được thiết kế riêng.

## 15. Callback trên root entity, không tự áp dụng đệ quy mọi object con

Spring Data Cassandra mô tả lifecycle events theo các **root-level types**. Một UDT hoặc complex property nằm trong aggregate root **không mặc nhiên** nhận event riêng như một aggregate độc lập.

Ví dụ entity có:

~~~java
@Table("orders_by_id")
class OrderWithAddress {
    @PrimaryKey("order_id")
    UUID orderId;

    @Column("shipping_address")
    ShippingAddress address;
}
~~~

`ShippingAddress` là kiểu domain giả định được mapping thành UDT theo cấu hình ứng dụng; ví dụ chỉ minh họa quan hệ aggregate. Không tự giả định `BeforeConvertCallback<ShippingAddress>` sẽ được gọi khi lưu `OrderWithAddress`.

Nếu cần chuẩn hóa địa chỉ:

1. Chuẩn hóa tại **domain/service** trước save; hoặc
2. Chuẩn hóa trong `BeforeConvertCallback<OrderWithAddress>` và trả về aggregate có address đã hợp lệ; hoặc
3. Dùng converter/type mapping được cấu hình rõ khi trách nhiệm thuộc conversion.

Thiết kế đúng phải xác minh phạm vi callback/UDT của **phiên bản Spring Data** đang sử dụng.

## 16. Chọn đúng nơi cho từng loại thay đổi

| Yêu cầu | Nơi phù hợp | Tại sao? |
| --- | --- | --- |
| Chuẩn hóa `state`, cắt khoảng trắng | Domain service hoặc `BeforeConvertCallback` | Mapper dùng dữ liệu đã chuẩn hóa |
| Điền `createdAt/updatedAt`, actor | Auditing callback đã bật | Có checkpoint trước conversion |
| Validate ID/field bắt buộc | Service/domain + `BeforeConvertCallback` | Phát lỗi trước khi gửi CQL |
| Kiểm tra loại statement được tạo | `BeforeSaveCallback` | Có `Statement<?>` để quan sát |
| TTL cho một insert | `InsertOptions` hoặc CQL `USING TTL` | Cần thay cách tạo/thi hành mutation |
| Consistency/timeout riêng một write | Write options hoặc bound statement | Là thuộc tính execution, không phải entity property |
| Chỉ cập nhật nếu version còn bằng N | Conditional CQL/LWT hoặc hỗ trợ optimistic locking đã xác minh | Bảo vệ trên server, không chỉ validate ở Java |
| PATCH chỉ sửa một tập cột | Selective update hoặc bind UNSET hợp lệ | Tránh ghi lại field không yêu cầu |
| Phát event cho hệ thống khác | Outbox/command workflow bền vững | Callback không cung cấp atomic cross-system |
| Đổi keyspace/table động | Kiến trúc session/mapping/gateway rõ ràng | Không sửa lén statement sau converter |
| Log hoạt động mapping | Callback/event hoặc metrics an toàn | Không log payload nhạy cảm |

**Quy tắc quyết định:** nếu sự thay đổi liên quan **giá trị cột**, thường phải thực hiện **trước conversion**. Nếu liên quan **CQL/execution policy**, điều chỉnh ở **API xây/chạy statement**. Nếu liên quan **nghiệp vụ đa bước**, đặt ở **service/workflow** với idempotency và phục hồi.

## 17. Callback không thay thế tính nhất quán và khóa lạc quan

Giả sử callback chuẩn hóa state và gắn updatedAt. Hai worker cùng đọc order version cũ rồi đều gọi `save(...)`:

~~~text
Worker A đọc: state=CREATED
Worker B đọc: state=CREATED

A: BeforeConvert normalize -> save PAID
B: BeforeConvert normalize -> save CANCELLED

Cả hai có thể ghi thành công nếu không dùng điều kiện.
Giá trị cuối phụ thuộc quy tắc Cassandra/timestamp.
~~~

**Không được** xem một callback trước ghi là **mutex** hoặc **transaction check-and-set**. Bất biến “chỉ thanh toán nếu chưa bị hủy” cần conditional mutation:

~~~sql
UPDATE app_ks.orders_by_id
SET state = 'PAID', updated_at = ?
WHERE order_id = ?
IF state = 'CREATED';
~~~

Ở đây LWT giúp Cassandra kiểm tra điều kiện tại thời điểm ghi theo cơ chế Paxos. Nếu lệnh được thực thi qua driver, cần đọc `ResultSet.wasApplied()` để biết `true`/`false`; nếu đi qua Spring Data API, xác minh contract trả về của phiên bản.

### 17.1. Callback có thể chạy dù write cuối cùng thất bại

Một `BeforeConvertCallback` hoặc `BeforeSaveCallback` có thể đã chạy, rồi:

- CQL bị từ chối vì schema hoặc validation server.
- LWT trả `[applied] = false`.
- Replica không đủ để đạt CL.
- Client nhận timeout, không biết chắc mutation đã được áp dụng hay chưa.
- Reactive subscription bị hủy.

Do đó, **không ghi audit event “đã thanh toán thành công” vào một hệ thống khác ngay trong before callback**. Callback thể hiện intent/chuẩn bị, chưa phải quyết định đã commit.

### 17.2. Thời điểm audit và write timestamp

`@LastModifiedDate` ghi một **property thời gian nghiệp vụ**. Cassandra còn có **write timestamp** nội bộ để hòa giải cell, và mỗi mutation có thể có TTL. Không tự suy rằng ba giá trị này luôn bằng nhau hoặc được reset theo cùng cơ chế.

~~~sql
SELECT state, updated_at,
       WRITETIME(state),
       TTL(state)
FROM app_ks.orders_by_id
WHERE order_id = ?;
~~~

`WRITETIME(state)` và `TTL(state)` có điều kiện áp dụng theo kiểu cột và phiên bản Cassandra. `updated_at` là dữ liệu do application/auditing cung cấp; **không tự là Cassandra write timestamp**.

Một callback cố đổi `updated_at` sau conversion có thể làm object Java “mới hơn” nhưng statement vẫn ghi thời gian cũ; đó là lỗi dữ liệu chứ không đơn giản là lỗi hiển thị.

## 18. Null, UNSET và side effect của mapping

Một API PATCH chỉ sửa `note` không nên tự động xóa `state` hoặc làm mới TTL của những cột khác.

| Đầu vào | Ý định | Tác động kỳ vọng nếu CQL/bind được tạo đúng |
| --- | --- | --- |
| Field không gửi | KEEP | Không tạo mutation cho cột |
| Field gửi `null` | CLEAR | Ghi xóa/tombstone nếu contract định nghĩa như vậy |
| Field có giá trị | SET | Ghi phiên bản mới của cell |

Spring Data Cassandra mapping có những lựa chọn xử lý property null, nhưng **một Java field `null` không tự cho biết field vắng mặt trong PATCH hay client muốn xóa**. Vì vậy:

- Mô hình hóa KEEP/CLEAR/SET ở DTO/service, thay vì sửa hàng loạt các field null trong `BeforeConvertCallback`.
- Với CQL tường minh, có thể dùng `BoundStatement.unset(...)` cho cột bỏ qua, `setToNull(...)` cho cột cần xóa, và set-value cho cột cập nhật, **ở những vị trí bind được hỗ trợ**.
- Không UNSET partition key trong `WHERE`.
- Không lấy một entity snapshot cũ rồi `save(...)` toàn bộ mà mặc nhiên kỳ vọng không đụng đến giá trị/TTL của cột khác.

Nếu phải điều chỉnh statement cho một PATCH, dùng **selective update** do application kiểm soát sẽ rõ ràng hơn một callback cố đọc lại object sau mapping.

## 19. Testing: assert CQL được persist, không chỉ assert callback được gọi

### 19.1. Unit test BeforeConvert

~~~java
import static org.junit.jupiter.api.Assertions.*;
import com.datastax.oss.driver.api.core.CqlIdentifier;
import java.util.UUID;
import org.junit.jupiter.api.Test;

@Test
void normalizesStateBeforeConversion() {
    OrderRow input = new OrderRow(
        UUID.randomUUID(), UUID.randomUUID(),
        " created ", null);

    NormalizeOrderBeforeConvert callback =
        new NormalizeOrderBeforeConvert();

    OrderRow result = callback.onBeforeConvert(
        input, CqlIdentifier.fromCql("orders_by_id"));

    assertEquals("CREATED", result.getState());
}
~~~

Unit test này xác minh **logic callback**, chưa chứng minh Spring thực sự gọi callback trong pipeline entity mapping của ứng dụng.

### 19.2. Integration test trên Cassandra thật

Chuẩn bị Spring context có repository/template, auditing config và callback đã đăng ký; keyspace/bảng của bài tồn tại trên Cassandra test. Một test hướng dẫn:

~~~java
@Test
void mappedInsertPersistsNormalizedState() {
    UUID id = UUID.randomUUID();
    OrderRow original = new OrderRow(
        id, UUID.randomUUID(), " created ", "note");

    operations.insert(original);

    PreparedStatement select = session.prepare(
        "SELECT state, created_at, updated_at " +
        "FROM app_ks.orders_by_id WHERE order_id = ?");

    Row persisted = session.execute(select.bind(id)).one();

    assertNotNull(persisted);
    assertEquals("CREATED", persisted.getString("state"));
    // Kiểm tra audit fields riêng theo chính sách nhận diện entity mới/cũ.
}
~~~

Đoạn test cần các import JUnit 5, `UUID`, driver `PreparedStatement`/`Row`, và fixture `CassandraOperations operations`, `CqlSession session`. Test riêng `created_at` chỉ nên assert khác null **sau khi** đã cấu hình và xác minh entity được nhận diện là *mới* (ví dụ qua chiến lược newness hoặc `Persistable` thích hợp). ID UUID đã được gán trước có thể khiến một số cách nhận diện newness coi entity là *đã tồn tại*. Bật auditing đơn thuần không bảo đảm `@CreatedDate` được điền trong mọi đường ghi. Dùng Cassandra thực hoặc Testcontainers với phiên bản mục tiêu; **không chạy test này trên production**.

**Tại sao test này quan trọng?** Nó đọc lại CQL data bằng driver, không lấy object Java trả về từ `operations.insert(...)` làm bằng chứng duy nhất.

### 19.3. Test “BeforeSave sửa entity quá muộn”

Trong một **test context cô lập**, chỉ đăng ký callback `IncorrectLateUpdate` từ phần 9:

1. Ghi entity có `state = CREATED`.
2. Callback `BeforeSave` sửa object thành `PAID`.
3. Đọc lại `state` từ Cassandra bằng `SELECT` tường minh.
4. Xác minh giá trị **không tự thay đổi** chỉ vì entity được sửa sau lúc statement đã tạo.
5. Không đưa callback anti-pattern này vào môi trường production hoặc chạy cùng callback chuẩn hóa thật trong test dễ gây lẫn.

Không nhất thiết mọi phiên bản framework có cùng chi tiết object lifecycle sau save, nhưng **ranh giới đã tạo statement** là điều cần được kiểm thử với phiên bản chính xác.

### 19.4. Test write options

1. Thực hiện `operations.insert(order, InsertOptions.builder().ttl(Duration.ofSeconds(120))...build())` trên hàng thử nghiệm.
2. Đọc `TTL(state)` và `WRITETIME(state)`; ghi nhận write có TTL và timestamp riêng.
3. So sánh với insert không có TTL trên hàng khác, không lấy một giá trị TTL từ JVM làm kết luận duy nhất.
4. Xác minh CL/timeout/tracing được áp dụng theo options bằng statement metadata hoặc test vận hành phù hợp.
5. Với conditional write, xác minh `[applied] = true/false` qua API có hợp đồng cụ thể.
6. Không giả định timeout sau mutation nghĩa là write chắc chắn chưa xảy ra.

## 20. Reactive và callback ordering: test thứ tự, không đoán

Một test reactive có thể dùng `StepVerifier` kiểm tra một callback `ReactiveBeforeConvertCallback`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void reactiveCallbackEmitsModifiedEntity() {
    OrderRow input = new OrderRow(
        UUID.randomUUID(), UUID.randomUUID(),
        " created ", null);

    ReactiveOrderNormalize callback =
        new ReactiveOrderNormalize();

    StepVerifier.create(Mono.from(
        callback.onBeforeConvert(
            input, CqlIdentifier.fromCql("orders_by_id"))))
        .assertNext(value ->
            assertEquals("CREATED", value.getState()))
        .verifyComplete();
}
~~~

Test này xác minh Publisher từ callback; integration test với `ReactiveCassandraTemplate`/repository vẫn cần để chứng minh **đường ghi thật** đã gọi đúng reactive callback và data persisted.

Các điểm thử thêm:

- Callback A có order 50, auditing order 100, callback B order 200; kiểm tra giá trị cuối **trước conversion**.
- Một callback ném exception: hệ thống có dừng và **không gửi statement** không?
- Reactive callback trả `Mono.error(...)`: caller có nhận lỗi đúng không?
- Một publisher được subscribe nhiều lần: callback có được gọi lại không? Có side effect nào không idempotent?
- Callback chỉ đăng ký cho `OrderRow` có bị gọi trên entity type khác không?
- Đường raw `CqlSession.execute(...)` có bỏ qua entity callbacks như kỳ vọng không?

## 21. Các anti-pattern thường gặp

| Cách làm sai | Hậu quả | Thay bằng |
| --- | --- | --- |
| Sửa field entity tại `BeforeSaveCallback` và kỳ vọng lưu ngay | Statement đã được tạo, thay đổi mới không phản ánh trong CQL | `BeforeConvertCallback` hoặc sửa trước save |
| Bỏ qua giá trị trả từ `Statement.setConsistencyLevel(...)` | Driver 4.x dùng immutable statements; thay đổi bị mất | Chain/gán lại returned statement |
| Dùng listener async để thay dữ liệu trước persist | Không có checkpoint đồng bộ đáng tin | Entity callback phù hợp |
| Gắn audit actor bằng chuỗi demo cố định trong production | Không truy vết được người dùng thật | `AuditorAware`/`ReactiveAuditorAware` từ nguồn tin cậy |
| Coi `@CreatedDate` là lịch sử audit đầy đủ | Chỉ giữ metadata snapshot | Event log/audit history được thiết kế riêng |
| Dùng `@LastModifiedDate` làm write timestamp Cassandra | Nhầm thời điểm nghiệp vụ và metadata hòa giải cell | Phân biệt `updated_at` và `WRITETIME` |
| Dùng callback để kiểm tra state rồi `save` không điều kiện | Race condition giữa đọc và ghi | LWT `IF version/state = ?` |
| Dùng callback để gửi email sau save | Không có giao dịch cross-system, callback có thể chạy nhiều lần | Durable outbox/workflow |
| Mong mọi `@Query`/raw CQL phát lifecycle callbacks | Các đường CQL có thể bypass mapping | Chuẩn hóa/validate ở service hoặc gateway |
| Cho callback thay partition key sau statement được tạo | Statement có thể trỏ khóa cũ hoặc sai | Định danh PK ổn định trước mapping |
| Sử dụng entity mutable chung trong nhiều subscription | Race giữa callbacks/threads | Instance riêng hoặc immutable copy |
| Nhầm Java `null` thành UNSET | Vô tình tạo tombstone hoặc ghi đè | Tri-state PATCH + selective update |
| Đặt TTL/CL bằng cách sửa object trong callback | Options không phải là entity fields | `InsertOptions`, `UpdateOptions`, bound statement |
| Chỉ assert object trả từ `save` | Có thể không khớp data persisted | Query độc lập từ Cassandra |
| Khi timeout, coi callback chưa chạy hoặc write không xảy ra | Trạng thái chưa chắc chắn | Idempotency, đối soát, retry đúng chính sách |

## 22. Giám sát, bảo mật và hiệu năng

Callback thường chạy trên **mọi write entity của domain type được đăng ký**. Một callback tốn vài chục mili giây hoặc phát thêm SELECT sẽ có thể ảnh hưởng trực tiếp tới latency và tải cluster ở lưu lượng cao.

Một số nguyên tắc:

1. **Ưu tiên pure transformation/validation:** chuẩn hóa string, kiểm tra giá trị bất biến, trả entity mới khi cần.
2. **Hạn chế I/O trong callback:** không gọi Cassandra để “xác nhận state” rồi viết tiếp như thể đó là CAS.
3. **Không phát side effect không idempotent:** email, message, payment charge không nên được tạo từ before callback.
4. **Không log PII:** `Statement`, entity và bound values có thể chứa dữ liệu nhạy cảm. Ghi metric theo loại bảng, thao tác, thời gian, lỗi; tránh log payload thô.
5. **Quản lý thứ tự:** dùng `@Order`/`Ordered` rõ ràng, không đặt logic phụ thuộc thứ tự trên các callback có cùng precedence.
6. **Kiểm soát số callback:** đăng ký class typed thay vì một lambda không có thông tin type phù hợp khi application có nhiều entity.
7. **Đo phân vị latency:** p95/p99 của đường save, số callback errors, Cassandra timeouts, LWT conflict, number of queries per request.
8. **Không đóng CqlSession theo request:** bean session được dùng lâu dài và do Spring quản lý vòng đời.
9. **Sử dụng query-first:** callback không sửa được một bảng có partition key sai, partition quá lớn hoặc truy vấn lọc không hỗ trợ.

### 22.1. Checklist quan sát

| Tín hiệu | Câu hỏi cần xác minh |
| --- | --- |
| Callback invocation count | Có chạy đúng số lần và đúng entity không? |
| Failed validation | Có chặn mutation trước khi gửi CQL không? |
| Statement type/table | Converter đã chọn đúng bảng và operation chưa? |
| Auditing values | `created_at`/`updated_at`/actor có được persist thật không? |
| TTL và write consistency | Options có được áp trên statement thực thi không? |
| Reactive cancellation/retry | Có callback lặp và side effect bất ngờ không? |
| WriteTimeout/Unavailable | Có quy trình trạng thái chưa rõ và idempotency không? |
| CQL count/partition access | Có query phụ hoặc scan phát sinh từ callback không? |

## 23. Bài thực hành tổng hợp

**Đề bài:** xây API Spring Boot tạo và cập nhật đơn hàng. Yêu cầu: `state` phải được chuẩn hóa, trường auditing tự điền, một số insert được gắn TTL/CL riêng, còn cập nhật trạng thái từ `CREATED` sang `PAID` phải có điều kiện Cassandra.

Thực hiện:

1. Tạo keyspace thử nghiệm với replication phù hợp; tạo bảng `orders_by_id` theo schema của bài.
2. Tạo entity `OrderRow` với `@Table`, `@PrimaryKey`, `@Column`, `@CreatedDate` và `@LastModifiedDate`.
3. Bật `@EnableCassandraAuditing` và một `AuditorAware<String>` chỉ dùng cho test/demo.
4. Đăng ký `NormalizeOrderBeforeConvert` để normalize `" created "` thành `"CREATED"`.
5. Ghi entity qua `CassandraTemplate.insert(...)`; đọc lại trực tiếp từ Cassandra và assert giá trị đã chuẩn hóa.
6. Đăng ký một `BeforeSaveCallback<OrderRow>` chỉ quan sát `tableName`/statement type; xác minh nó được gọi **sau converter**.
7. Trong test context cô lập, thử cố sửa `state` ở `BeforeSave`; so sánh entity Java với giá trị đọc lại từ Cassandra.
8. Ghi một entity khác với `InsertOptions` có TTL và `LOCAL_QUORUM`; đọc `TTL(state)` để xác minh mutation.
9. Viết `OrderStateGateway` dùng prepared CQL `IF state = 'CREATED'` và `wasApplied()`.
10. Gửi hai request cạnh tranh chuyển `CREATED` sang hai trạng thái; kiểm tra kết quả true/false, không dùng callback làm khóa.
11. Viết thêm reactive `ReactiveBeforeConvertCallback` và `StepVerifier` để kiểm tra callback trả publisher chứa entity mới.
12. Thử raw `CqlSession.execute(...)` và ghi lại việc nó **không đi qua callback entity** như đường template.
13. Mô phỏng timeout và phân biệt trạng thái chưa rõ với LWT `[applied] = false`.
14. Đo latency của callback và số CQL request thực tế; đảm bảo không có database query ẩn trong normalizer.
15. Viết một báo cáo chỉ rõ **điểm thay entity**, **điểm inspect statement**, **điểm cấu hình statement**, **điểm kiểm tra bất biến trên server**.

**Tiêu chí hoàn thành:** bạn giải thích chính xác vì sao thay dữ liệu trong `BeforeConvert` được phản ánh vào statement, còn sửa entity tại `BeforeSave` không tự cập nhật statement; dùng đúng API write options/gateway cho chính sách thực thi và phân biệt auditing metadata với tính nguyên tử nghiệp vụ.

## 24. Câu hỏi tự kiểm tra

1. `BeforeConvertCallback` khác `BeforeSaveCallback` ở thời điểm nào của pipeline?
2. Nếu callback muốn chuẩn hóa `state` để lưu vào Cassandra, nên chọn hook nào?
3. Vì sao một object Java thay đổi ở `BeforeSave` chưa chắc làm database thay đổi tương ứng?
4. Tham số `Statement<?>` trong `BeforeSaveCallback` dùng để làm gì?
5. Tại sao callback không thể đơn giản trả một `Statement` khác từ `onBeforeSave`?
6. Java driver 4.x xử lý `BoundStatement.setConsistencyLevel(...)` theo kiểu mutable hay immutable?
7. Nếu gọi `setConsistencyLevel(...)` nhưng bỏ qua giá trị trả về, có nguy cơ gì?
8. Khi cần TTL và CL khác nhau theo use case, nên dùng API nào của Spring Data Cassandra?
9. `InsertOptions` và `UpdateOptions` giúp điều chỉnh gì trong lúc ghi?
10. Khi muốn `IF version = ?`, vì sao chỉ sửa entity trước save vẫn chưa đủ?
11. Vai trò của `@CreatedDate` và `@LastModifiedDate` là gì?
12. Auditing callback được gọi ở giai đoạn nào so với conversion?
13. `@CreatedBy` và `@LastModifiedBy` lấy actor từ đâu khi auditing được cấu hình đúng?
14. Vì sao phải kiểm tra newness detection khi dùng auditing?
15. `@LastModifiedDate` có tự quyết định Cassandra write timestamp hay không?
16. Khi immutable entity không có setter, callback có thể trả về gì?
17. Lifecycle `ApplicationEvent` khác `EntityCallback` ra sao về thứ tự và khả năng trả entity?
18. Vì sao async event multicaster không nên được dùng để thay dữ liệu quyết định mutation?
19. Đường CQL raw qua `CqlSession` có gọi callback entity Spring Data không?
20. Reactive callback có thể dùng `ThreadLocal` như một cách lấy actor luôn đúng không?
21. Vì sao không gửi email từ `BeforeSaveCallback` để coi là sau commit?
22. Unit test callback và integration test đọc lại dữ liệu khác nhau ở điểm nào?
23. Khi LWT trả false hoặc timeout sau callback, thông tin audit có nghĩa “đã commit thành công” không?
24. Vì sao một callback normalize state không giải quyết check-then-act race giữa hai writer?
25. Tại sao UNSET/NULL/PATCH phải có hợp đồng rõ thay vì xem mọi Java null là KEEP?
26. Những metrics nào giúp phát hiện callback gây thêm tải hoặc làm tăng p99 write latency?

## 25. Tài liệu đối chiếu và kết luận

Các phần API được mô tả theo tài liệu chính thức của Spring Data Cassandra và Java driver, nên cần đối chiếu **phiên bản dependency thực tế của dự án** trước khi copy ví dụ:

- [Spring Data Cassandra — Lifecycle Events và Entity Callbacks](https://docs.spring.io/spring-data/cassandra/reference/cassandra/events.html)
- [Spring Data Cassandra — Auditing Configuration](https://docs.spring.io/spring-data/cassandra/reference/cassandra/auditing.html)
- [Spring Data Cassandra — BeforeConvertCallback API](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/mapping/event/BeforeConvertCallback.html)
- [Spring Data Cassandra — BeforeSaveCallback API](https://docs.spring.io/spring-data/cassandra/reference/api/java/org/springframework/data/cassandra/core/mapping/event/BeforeSaveCallback.html)
- [Java Driver 4 — Statement immutability](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/)

**Ghi nhớ:** trong **Spring Data Cassandra**, **`BeforeConvertCallback`** là nơi sửa entity **trước khi converter sinh CQL statement**; thay đổi được phản ánh vào câu ghi. **`BeforeSaveCallback`** chạy **sau conversion**, phù hợp để kiểm tra statement/entity nhưng **không tự đưa thay đổi muộn của entity vào statement đã tạo**. Nếu muốn đổi TTL, consistency hoặc CQL điều kiện, hãy dùng **`InsertOptions`/`UpdateOptions` hoặc statement/gateway được xây trước lúc execute** và nhớ driver 4.x dùng statement bất biến. Auditing bổ sung metadata tại checkpoint phù hợp, nhưng không thay thế **LWT/CAS**, idempotency, thiết kế partition key, paging hay quy trình phục hồi của hệ dữ liệu phân tán.
