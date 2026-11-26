# Bài thực hành: Triển khai truy vấn CQL tham số hóa qua @Query hoặc CqlTemplate

Trong **Spring Data Cassandra**, truy vấn CQL tham số hóa cho phép tách **cấu trúc câu lệnh** khỏi **giá trị được đưa vào lúc chạy**. Thay vì ghép mã khách hàng, UUID hoặc trạng thái vào một chuỗi CQL, ứng dụng sử dụng các bind marker và để framework/Java Driver truyền giá trị theo đúng kiểu dữ liệu. Cách làm này giúp tránh lỗi cú pháp, giảm rủi ro CQL injection, có thể tận dụng prepared statements và làm rõ tham số thuộc về truy vấn nào.

Bài thuộc chương **Bài thực hành** của module `SPRING_DATA_CASSANDRA`. Người học sẽ tạo một bảng theo truy vấn, ánh xạ entity, triển khai truy vấn tham số bằng **`@Query` của `CassandraRepository`** và **`CqlTemplate`**, sau đó viết integration test chạy trên Cassandra thật. Bài cũng giải thích những giới hạn đặc thù của Cassandra: phải truy vấn theo partition key hợp lý, hiểu phân trang và consistency, không dùng bind marker để thay thế tên bảng/cột hay che một mô hình dữ liệu chưa phù hợp.

> **Phạm vi ví dụ:** Java 17, Spring Boot 3.x, Spring Data Cassandra dùng Java Driver 4.x, JUnit Jupiter và Testcontainers 1.x để minh họa. Một số tên dependency hoặc API khác nhau giữa các nhánh phiên bản. Chọn version thống nhất theo BOM của dự án và đối chiếu API nếu đang dùng Spring Boot/Testcontainers mới hơn.

## 1. Mục tiêu và kết quả cần đạt

Sau khi hoàn thành, bạn có thể:

1. Viết CQL có `?` thay cho các **giá trị** người dùng truyền vào.
2. Dùng `@Query` với cú pháp vị trí `?0`, `?1` của Spring Data Cassandra.
3. Dùng `CqlTemplate` với bind marker `?`, ánh xạ `Row` thành DTO chỉ đọc và cập nhật có tham số.
4. Hiểu sự khác nhau giữa `CqlTemplate`, `CassandraTemplate` và `CqlSession`.
5. Kiểm tra câu CQL có ràng buộc partition key, tránh `ALLOW FILTERING` chỉ để làm một truy vấn chạy được.
6. Viết test xác nhận cả hai đường truy vấn trả cùng dữ liệu và xử lý trường hợp không tìm thấy.
7. Phát hiện những nguy cơ như dùng `UPDATE` tạo row ngoài ý muốn, tải quá nhiều cột hay ghép chuỗi từ input.

Sản phẩm của bài thực hành là một chức năng nhỏ cho dịch vụ đơn hàng:

- Lấy đơn hàng bằng `order_id` từ repository có `@Query`.
- Lấy bản tóm tắt đơn hàng bằng `CqlTemplate`.
- Đổi `order_state` bằng CQL có tham số.
- Có integration test chứng minh dữ liệu thực sự được lưu/đọc từ Cassandra.

## 2. Bài toán và thiết kế bảng theo truy vấn

Giả sử API có yêu cầu: “khi đã biết ID của một đơn hàng, đọc trạng thái và tổng tiền của đơn hàng đó”. Bảng Cassandra cần phục vụ trực tiếp truy vấn theo `order_id`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS shop
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS shop.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    order_state text,
    total_cents bigint
);
~~~

Trong ví dụ này:

- `order_id` là **partition key**. Truy vấn `WHERE order_id = ?` xác định một partition.
- `customer_id`, `order_state` và `total_cents` là các cột dữ liệu thông thường.
- `bigint` ánh xạ thuận tiện sang Java `Long`; lưu tổng tiền theo đơn vị nhỏ nhất để tránh làm tròn dấu phẩy động.
- `SimpleStrategy` với RF=1 chỉ dùng cho một node trong bài thực hành. Cụm production nhiều datacenter cần replication strategy phù hợp như `NetworkTopologyStrategy` và replication factor được thiết kế riêng.

**Không nên dùng bảng này để liệt kê tất cả đơn hàng của một khách hàng bằng `WHERE customer_id = ?`.** Vì `customer_id` không phải partition key, truy vấn đó không phù hợp với bảng hiện tại. Nếu ứng dụng cần “đơn hàng của khách theo ngày”, hãy thiết kế thêm bảng theo truy vấn tương ứng, ví dụ `orders_by_customer_day` với composite partition key và clustering key phù hợp.

### CQL được phép và không phù hợp

~~~sql
-- Tốt: định vị đúng một partition.
SELECT order_id, order_state, total_cents
FROM shop.orders_by_id
WHERE order_id = ?;

-- Không phù hợp với bảng này: customer_id không thuộc primary key.
SELECT order_id, order_state
FROM shop.orders_by_id
WHERE customer_id = ?;
~~~

Tham số hóa không thay đổi luật chọn partition của Cassandra. Một câu CQL được bind đúng kiểu vẫn có thể không hợp lệ hoặc có hiệu năng kém nếu bảng không hỗ trợ access pattern.

## 3. Chuẩn bị dự án Spring Boot

Các dependency Gradle Groovy DSL cơ bản:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-cassandra'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:cassandra'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Ví dụ sử dụng **Testcontainers 1.x** với module `org.testcontainers:cassandra` và import `org.testcontainers.containers.CassandraContainer`. Trên Testcontainers 2.x, module/import Cassandra đã đổi; cần dùng bộ dependency nhất quán theo phiên bản thực tế. Dự án không dùng Spring Boot BOM phải tự khóa version tương thích.

Cấu hình Cassandra cho ứng dụng khi chạy với cluster ngoài Docker test:

~~~yaml
spring:
  cassandra:
    contact-points:
      - localhost:9042
    local-datacenter: datacenter1
    keyspace-name: shop
    schema-action: NONE
~~~

Các giá trị host/port và tên datacenter chỉ là ví dụ; trong integration test phía dưới, Testcontainers sẽ cung cấp endpoint và datacenter lúc chạy. `schema-action: NONE` thể hiện schema do script/migration chuẩn bị, không để ứng dụng tự ý tạo/xóa bảng.

Cần một lớp ứng dụng Spring Boot và các class cùng package hoặc package con để component scanning hoạt động:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Khi chạy test, cần Docker Engine hoặc runtime container được Testcontainers hỗ trợ, đủ CPU/RAM để Cassandra khởi động.

## 4. Entity mapping cho bảng orders_by_id

Tạo `CustomerOrder.java`:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_id")
public class CustomerOrder {

    @PrimaryKey("order_id")
    private UUID orderId;

    @Column("customer_id")
    private UUID customerId;

    @Column("order_state")
    private String orderState;

    @Column("total_cents")
    private Long totalCents;

    public CustomerOrder() {
    }

    public CustomerOrder(UUID orderId, UUID customerId,
                         String orderState, Long totalCents) {
        this.orderId = orderId;
        this.customerId = customerId;
        this.orderState = orderState;
        this.totalCents = totalCents;
    }

    public UUID getOrderId() {
        return orderId;
    }

    public void setOrderId(UUID orderId) {
        this.orderId = orderId;
    }

    public UUID getCustomerId() {
        return customerId;
    }

    public void setCustomerId(UUID customerId) {
        this.customerId = customerId;
    }

    public String getOrderState() {
        return orderState;
    }

    public void setOrderState(String orderState) {
        this.orderState = orderState;
    }

    public Long getTotalCents() {
        return totalCents;
    }

    public void setTotalCents(Long totalCents) {
        this.totalCents = totalCents;
    }
}
~~~

Mapping đầy đủ giúp repository đọc/ghi entity. Với một API chỉ trả trạng thái và tổng tiền, ta có thể đọc **ít cột hơn** qua `CqlTemplate` và ánh xạ DTO riêng.

Không lấy entity chỉ có một phần cột rồi gọi `save()` như đối tượng đầy đủ: những trường không được tải có thể trở thành `null`, và ý nghĩa của `null` khi ghi tùy vào query/write options. Một DTO chỉ đọc giảm nguy cơ ghi nhầm dữ liệu.

## 5. Cách 1: @Query trong CassandraRepository

Tạo `CustomerOrderRepository.java`:

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;

public interface CustomerOrderRepository
        extends CassandraRepository<CustomerOrder, UUID> {

    @Query("SELECT * FROM orders_by_id WHERE order_id = ?0")
    Optional<CustomerOrder> findViaCql(UUID orderId);
}
~~~

Giải thích:

- `@Query` cho biết CQL cụ thể thay vì để Spring Data suy ra query từ tên method.
- `?0` là tham số ở **vị trí 0** của method Java, ở đây là `orderId`. Spring Data xử lý marker này và liên kết giá trị khi thực thi.
- Giá trị UUID được truyền như một giá trị CQL; **không bọc `?0` bằng dấu nháy đơn**.
- `Optional<CustomerOrder>` biểu thị trường hợp không tìm thấy row.
- Nếu mục tiêu chỉ là tìm theo primary key, `findById(orderId)` có sẵn trong `CassandraRepository`. `@Query` được dùng ở đây để học truy vấn CQL tùy biến, không phải vì CRUD mặc định không làm được.

Ví dụ gọi từ service:

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class OrderLookupService {

    private final CustomerOrderRepository repository;

    public OrderLookupService(CustomerOrderRepository repository) {
        this.repository = repository;
    }

    public Optional<CustomerOrder> findFullOrder(UUID orderId) {
        return repository.findViaCql(orderId);
    }
}
~~~

### Thêm tham số thứ hai khi schema có composite key

Bài cơ bản dùng một khóa `order_id`, nên một tham số là đủ. Với một bảng khác có primary key `((customer_id), order_id)`, cú pháp tham số vị trí sẽ là:

~~~java
// Ví dụ riêng cho bảng có composite key, không áp dụng trực tiếp cho
// schema orders_by_id ở trên.
@Query("""
    SELECT * FROM orders_by_customer
    WHERE customer_id = ?0 AND order_id = ?1
    """)
List<CustomerOrderByCustomer> findByCustomerAndOrder(
    UUID customerId, UUID orderId);
~~~

Trong ví dụ minh họa này, `CustomerOrderByCustomer` là entity ánh xạ **bảng khác** và khóa tương ứng; cần định nghĩa class nếu triển khai mở rộng. Cách đánh số `?0` và `?1` theo thứ tự tham số method, khác với marker CQL thuần `?` của `CqlTemplate`.

Không thay `?0` bằng chuỗi nội suy từ controller như `"... WHERE order_id = " + input`. Ngoài bảo mật, việc đó làm binding kiểu dữ liệu trở nên khó kiểm soát.

## 6. Cách 2: CqlTemplate để đọc một DTO gọn

`CqlTemplate` nằm trong package `org.springframework.data.cassandra.core.cql`. Nó cung cấp API làm việc với CQL và ánh xạ trực tiếp từ `Row`, thay vì yêu cầu luôn phải dùng entity đầy đủ.

Tạo DTO chỉ đọc:

~~~java
import java.util.UUID;

public record OrderSummary(
    UUID orderId,
    String orderState,
    Long totalCents
) {}
~~~

Tạo component `OrderSummaryReader.java`:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.cassandra.core.cql.CqlTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderSummaryReader {

    private static final String FIND_BY_ID = """
        SELECT order_id, order_state, total_cents
        FROM shop.orders_by_id
        WHERE order_id = ?
        """;

    private final CqlTemplate cqlTemplate;

    public OrderSummaryReader(CqlTemplate cqlTemplate) {
        this.cqlTemplate = cqlTemplate;
    }

    public Optional<OrderSummary> findSummary(UUID orderId) {
        List<OrderSummary> rows = cqlTemplate.query(
            FIND_BY_ID,
            (row, rowNum) -> new OrderSummary(
                row.getUuid("order_id"),
                row.getString("order_state"),
                row.isNull("total_cents")
                    ? null
                    : row.getLong("total_cents")
            ),
            orderId
        );

        return rows.stream().findFirst();
    }
}
~~~

Trong lời gọi này:

- CQL chứa `?` là **bind marker**.
- Tham số `orderId` ở cuối lời gọi `query(...)` được bind theo vị trí marker.
- `RowMapper` chỉ đọc ba cột được SELECT, đúng với cấu trúc `OrderSummary`.
- `row.isNull("total_cents")` giúp phân biệt cột chưa có giá trị với `0L` khi nghiệp vụ cần phân biệt.
- Khi không có kết quả, method trả `Optional.empty()`.

Đây là biến thể có lợi khi chỉ cần bản tóm tắt cho response. Nó không tạo entity thiếu cột rồi tái sử dụng làm đối tượng ghi.

### Nếu dự án chưa có bean CqlTemplate

Tùy cách cấu hình Spring Data Cassandra, bean `CqlTemplate` có thể đã được đăng ký. Nếu chưa có, có thể cấu hình một bean dùng chung từ `CqlSession` do Spring quản lý:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.cql.CqlTemplate;

@Configuration
class CqlAccessConfiguration {

    @Bean
    CqlTemplate cqlTemplate(CqlSession session) {
        return new CqlTemplate(session);
    }
}
~~~

**Chỉ thêm cấu hình này khi thật sự cần.** Đăng ký bean trùng với cấu hình hiện hữu có thể gây ambiguity khi tiêm dependency. Không tạo một `CqlSession` mới trong mỗi repository call; session nên được dùng chung và đóng theo vòng đời Spring context.

### CqlTemplate khác CassandraTemplate thế nào?

| API | Thế mạnh | Mức ánh xạ |
| --- | --- | --- |
| `CassandraRepository` và `@Query` | Repository interface, CRUD và truy vấn CQL có sẵn trong method | Ánh xạ entity / projection của Spring Data |
| `CassandraTemplate` | Entity operations và query/update API của Spring Data | Thường làm việc với mapping entity, conversion và table metadata |
| `CqlTemplate` | Thực thi CQL thấp hơn, truyền bind parameters, RowMapper | Tự quyết định ánh xạ dữ liệu hàng |
| `CqlSession` | API Java Driver trực tiếp, prepared/bound statement và paging chi tiết | Tự quản lý câu CQL, row/result và options |

Trong một ứng dụng, có thể dùng repository cho các thao tác thông thường và `CqlTemplate` cho đường đọc chuyên biệt. Sử dụng abstraction đơn giản nhất đáp ứng access pattern và độ kiểm soát cần thiết.

## 7. Cập nhật giá trị bằng CqlTemplate với tham số

Cho tình huống đơn hàng đã tồn tại và cần đổi trạng thái. Tạo thêm một method trong component chuyên xử lý write hoặc trong một service ghi riêng:

~~~java
import java.util.Set;
import java.util.UUID;
import org.springframework.data.cassandra.core.cql.CqlTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderStateWriter {

    private static final Set<String> ALLOWED_STATES =
        Set.of("NEW", "CONFIRMED", "CANCELLED");

    private final CqlTemplate cqlTemplate;

    public OrderStateWriter(CqlTemplate cqlTemplate) {
        this.cqlTemplate = cqlTemplate;
    }

    public void changeState(UUID orderId, String newState) {
        if (orderId == null || !ALLOWED_STATES.contains(newState)) {
            throw new IllegalArgumentException("Invalid order or state");
        }

        cqlTemplate.execute(
            "UPDATE shop.orders_by_id " +
            "SET order_state = ? WHERE order_id = ?",
            newState,
            orderId
        );
    }
}
~~~

Ở đây có **hai marker `?`**: marker đầu nhận `newState`, marker thứ hai nhận `orderId`. Vị trí giá trị phải khớp đúng thứ tự CQL. Việc nối hai **chuỗi hằng do lập trình viên kiểm soát** để trình bày query không đưa dữ liệu người dùng vào cú pháp CQL; tránh nối các biến runtime vào chuỗi CQL.

**Giới hạn quan trọng:** `UPDATE` của Cassandra có ngữ nghĩa **upsert**. Nếu `orderId` chưa tồn tại, lệnh trên có thể tạo partition/row mới chỉ có cột `order_state`. Vì vậy một API “chỉ cập nhật nếu đơn hàng tồn tại” cần thêm hợp đồng nghiệp vụ, hoặc một conditional update phù hợp và xử lý kết quả `[applied]` của lightweight transaction (LWT) nếu thực sự cần điều kiện nguyên tử. Một bước `SELECT` rồi `UPDATE` riêng biệt **không** ngăn được race condition giữa hai request.

Trong bài tập cơ bản, ta sẽ gọi `changeState` **chỉ với order đã được tạo**. Không suy ra rằng method này đảm bảo sự tồn tại hoặc chuyển trạng thái hợp lệ giữa các trạng thái chỉ vì nó dùng parameter binding.

## 8. Vì sao cách ghép chuỗi trực tiếp không phù hợp?

Ví dụ không nên dùng:

~~~java
String cql = "SELECT * FROM shop.orders_by_id " +
    "WHERE order_id = " + userSuppliedId;
~~~

Ngoài rủi ro chèn dữ liệu không đáng tin cậy vào cấu trúc truy vấn, cách này dễ gây lỗi cú pháp, nhầm kiểu UUID với text và khiến mỗi tập giá trị tạo ra một chuỗi CQL khác nhau.

Cách đúng khi dùng `CqlTemplate`:

~~~java
cqlTemplate.query(
    "SELECT order_id FROM shop.orders_by_id WHERE order_id = ?",
    (row, rowNum) -> row.getUuid("order_id"),
    orderId
);
~~~

Hoặc với `@Query`:

~~~java
@Query("SELECT * FROM orders_by_id WHERE order_id = ?0")
Optional<CustomerOrder> findViaCql(UUID orderId);
~~~

**Không viết** `WHERE order_id = '?0'` hoặc `WHERE order_id = '?'`. Dấu nháy làm marker trở thành nội dung chuỗi thay vì placeholder cần bind, hoặc khiến query parser hoạt động không như mong đợi.

### Marker chỉ thay thế giá trị, không thay thế identifier

Sai ý tưởng:

~~~sql
SELECT * FROM ? WHERE order_id = ?;
SELECT ? FROM shop.orders_by_id WHERE order_id = ?;
~~~

Không thể dùng bind marker để chọn tùy ý **tên bảng** hoặc **tên cột**. Những identifier này thuộc cú pháp CQL.

Nếu phải chọn một trong vài bảng hợp lệ, ứng dụng phải dùng **allowlist xác định trước**:

~~~java
String table = switch (view) {
    case "by-id" -> "shop.orders_by_id";
    case "by-customer-day" -> "shop.orders_by_customer_day";
    default -> throw new IllegalArgumentException("Unsupported view");
};
// Bảng thứ hai chỉ là ví dụ của một read model đã được tạo riêng.
// Giá trị truyền vào WHERE vẫn phải dùng bind markers.
~~~

Không dùng `view` nguyên văn từ request làm tên bảng. Trong Cassandra, việc lựa chọn bảng còn liên quan trực tiếp đến partition key và access pattern, không chỉ xác minh chuỗi tên hợp lệ.

### Bind marker không thay thế kiểm tra nghiệp vụ

Parameter binding không tự kiểm tra rằng người dùng HTTP có quyền xem đơn hàng này. Khi service là hệ thống đa khách hàng, cần kiểm tra quyền truy cập/tenant trong lớp nghiệp vụ hoặc thiết kế bảng với tenant ID trong partition key phù hợp. Một query an toàn về cú pháp vẫn có thể làm lộ dữ liệu nếu authorization bị bỏ qua.

## 9. Chuẩn bị schema và dữ liệu thử

Lưu script sau trong **`src/test/resources/cassandra/schema.cql`**:

~~~sql
CREATE KEYSPACE IF NOT EXISTS shop
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS shop.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    order_state text,
    total_cents bigint
);
~~~

Thử trực tiếp bằng `cqlsh` nếu có Cassandra:

~~~sql
INSERT INTO shop.orders_by_id (
    order_id, customer_id, order_state, total_cents
) VALUES (
    11111111-1111-1111-1111-111111111111,
    22222222-2222-2222-2222-222222222222,
    'NEW',
    125000
);

SELECT order_state, total_cents
FROM shop.orders_by_id
WHERE order_id = 11111111-1111-1111-1111-111111111111;
~~~

Giá trị `125000` được hiểu là **125.000 đơn vị nhỏ nhất** (ví dụ cent với đồng tiền có phần thập phân), không tự suy ra đơn vị tiền tệ khi dữ liệu không có thông tin đó.

Trên môi trường thực hành có Testcontainers, chúng ta không cần insert thủ công vào `cqlsh`: test sẽ tạo row với UUID ngẫu nhiên, đọc và xóa sau mỗi ca kiểm thử.

## 10. Viết integration test chạy trên Cassandra thật

Một unit test mock `CqlTemplate` có thể chỉ xác nhận method được gọi; nó không chứng minh CQL đúng schema hay bind marker đúng kiểu. Để xác nhận toàn bộ luồng, dùng `CassandraContainer` để khởi chạy Cassandra thật trong Docker.

Ví dụ lớp `ParameterizedCqlIT.java`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.CassandraContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest(properties = "spring.cassandra.schema-action=NONE")
class ParameterizedCqlIT {

    @Container
    static final CassandraContainer<?> CASSANDRA =
        new CassandraContainer<>(
            DockerImageName.parse("cassandra:4.1")
        ).withInitScript("cassandra/schema.cql");

    @DynamicPropertySource
    static void cassandraProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.cassandra.contact-points",
            CASSANDRA::getHost);
        registry.add("spring.cassandra.port",
            () -> CASSANDRA.getMappedPort(9042));
        registry.add("spring.cassandra.local-datacenter",
            CASSANDRA::getLocalDatacenter);
        registry.add("spring.cassandra.keyspace-name",
            () -> "shop");
    }

    @Autowired
    CustomerOrderRepository repository;

    @Autowired
    OrderSummaryReader summaryReader;

    @Autowired
    OrderStateWriter stateWriter;

    @Test
    void queryAndTemplateReturnSameOrder() {
        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();

        repository.save(
            new CustomerOrder(orderId, customerId, "NEW", 125000L)
        );

        try {
            CustomerOrder fromRepository =
                repository.findViaCql(orderId).orElseThrow();

            OrderSummary fromTemplate =
                summaryReader.findSummary(orderId).orElseThrow();

            assertThat(fromRepository.getOrderId())
                .isEqualTo(orderId);
            assertThat(fromTemplate.orderId())
                .isEqualTo(orderId);
            assertThat(fromTemplate.orderState())
                .isEqualTo("NEW");
            assertThat(fromTemplate.totalCents())
                .isEqualTo(125000L);

            stateWriter.changeState(orderId, "CONFIRMED");

            assertThat(repository.findViaCql(orderId)
                .orElseThrow().getOrderState())
                .isEqualTo("CONFIRMED");
        } finally {
            repository.deleteById(orderId);
        }
    }

    @Test
    void missingOrderReturnsEmpty() {
        UUID missingId = UUID.randomUUID();

        assertThat(repository.findViaCql(missingId)).isEmpty();
        assertThat(summaryReader.findSummary(missingId)).isEmpty();
    }
}
~~~

Test xác minh:

1. `repository.save(...)` ghi dữ liệu bằng Spring Data Cassandra.
2. `@Query` đọc đúng row theo partition key.
3. `CqlTemplate` nhận tham số, đọc đúng ba cột và ánh xạ thành DTO.
4. `UPDATE ... SET order_state = ? WHERE order_id = ?` thay đổi trường đích.
5. Query với UUID không tồn tại trả về `Optional.empty()` ở cả hai đường.
6. Dữ liệu thử được xóa theo ID ngay cả khi assertion thất bại.

Thời gian khởi động Cassandra có thể đáng kể. `@Container static` cho phép một test class tái sử dụng container giữa các test method. Không mặc định rằng các test class khác sẽ dùng cùng container, và cần chú ý Spring context caching nếu thay đổi cách chia sẻ container giữa nhiều lớp.

**Lưu ý:** Với Testcontainers, không hard-code host mapped port thành `localhost:9042`. `getHost()` và `getMappedPort(9042)` phản ánh endpoint mà JVM test thực sự truy cập. `getLocalDatacenter()` giúp Spring/driver dùng đúng datacenter của container.

### Dấu hiệu đạt yêu cầu

- Context Spring Boot khởi động được và mở kết nối tới container.
- Script init tạo keyspace/bảng trước lúc repository chạy.
- Test đọc/ghi không ném `InvalidQueryException`, mapping exception hoặc lỗi connection.
- Hai cách đọc trả cùng `orderId`, trạng thái và tổng tiền.
- Sau cleanup, bản ghi test không còn trong Cassandra.

Nếu test không chạy vì runner không có Docker, đây là **lỗi điều kiện môi trường** chứ chưa phải bằng chứng CQL sai. Kiểm tra Docker daemon, quyền truy cập, tài nguyên và registry image trước khi sửa query.

## 11. Kiểm soát lỗi truy vấn và ngoại lệ

Các lỗi có thể gặp:

| Triệu chứng | Nguyên nhân thường gặp | Hướng khắc phục |
| --- | --- | --- |
| `InvalidQueryException` vì cột không tồn tại | Tên cột CQL không trùng schema | Đối chiếu DDL, mapping và query |
| `InvalidQueryException` về thiếu primary key | Query không ràng buộc partition key đúng | Đổi access pattern hoặc thiết kế bảng mới |
| Lỗi số lượng marker | Số `?`/`?0` không khớp số tham số | Kiểm tra thứ tự và số lượng bind values |
| Type mismatch | Đưa `String` thay vì `UUID`/`Long` hoặc mapping sai type | Bind đúng kiểu dữ liệu Java/CQL |
| Kết quả không map được | RowMapper đọc tên cột không có trong `SELECT` | Chọn đúng cột hoặc sửa mapper |
| Row không tồn tại | Partition key không khớp hoặc dữ liệu chưa có | Trả `Optional.empty()`, kiểm tra ID và phạm vi nghiệp vụ |
| `AllNodesFailedException` | Driver không kết nối/khám phá được node thích hợp | Đọc lỗi con theo node: DNS, TCP, TLS, auth, datacenter |
| Lỗi thiếu quyền | Role Cassandra không có quyền `SELECT`/`MODIFY` | Cấp quyền tối thiểu trên đúng bảng |
| UPDATE làm xuất hiện row không mong muốn | Cassandra upsert khi khóa chưa tồn tại | Dùng điều kiện tồn tại/logic nghiệp vụ phù hợp |

Khi trả lỗi ra API, không để lộ thông tin đăng nhập, CQL bind values nhạy cảm hoặc topology nội bộ. Lỗi Cassandra authentication của **service** không tự đồng nghĩa người dùng HTTP cần đăng nhập lại.

## 12. Điều kiện hiệu năng và phân trang của truy vấn tham số

Chỉ dùng bind marker không đảm bảo hiệu năng. Cần kiểm tra đồng thời:

- **Partition key:** truy vấn ở bài này có `WHERE order_id = ?` nên tiếp cận một partition. Nếu cần tìm theo `customer_id`, hãy tạo read model phù hợp.
- **Projection:** `CqlTemplate` chỉ đọc ba cột cần cho `OrderSummary`, tránh gửi dữ liệu không cần thiết.
- **Số row:** bài hiện tại trả tối đa một row do primary key. Với bảng danh sách theo partition key, thêm `LIMIT` hợp lý và dùng paging state của driver/Spring Data Cassandra.
- **Prepared statement:** cả đường Spring Data binding và `CqlTemplate` có thể tận dụng cơ chế chuẩn bị/thực thi CQL tùy API/phiên bản; không tạo vô hạn câu lệnh với tên bảng hay điều kiện khác nhau.
- **Consistency level:** phải phù hợp replication factor và yêu cầu đọc/ghi của nghiệp vụ. Một node RF=1 trong Testcontainers không kiểm chứng được quorum/failover của production.
- **Timeout và retry:** một write timeout không chứng minh chắc chắn dữ liệu chưa được ghi. Nếu cần retry, phải xem xét idempotency; không retry vô hạn vì lỗi CQL sai hoặc thiếu quyền.

Khi query nhiều dòng, cần phân biệt `LIMIT` và driver page size. `LIMIT 50` giới hạn tổng số row của câu CQL; page size quyết định số row driver lấy theo từng lần fetch. Nếu code duyệt toàn bộ `ResultSet`, driver có thể lấy nhiều page, nên page size không tự hạn chế kích thước HTTP response.

## 13. Mở rộng bài thực hành

### Bài A — Thêm query nhiều điều kiện theo đúng primary key

Yêu cầu: tìm toàn bộ order theo một khách hàng **trong một ngày**. Đừng cố viết `WHERE customer_id = ?` trên `orders_by_id`.

Đề xuất bảng riêng:

~~~sql
CREATE TABLE shop.orders_by_customer_day (
    customer_id uuid,
    order_day date,
    placed_at timestamp,
    order_id uuid,
    order_state text,
    total_cents bigint,
    PRIMARY KEY ((customer_id, order_day), placed_at, order_id)
) WITH CLUSTERING ORDER BY (placed_at DESC, order_id ASC);
~~~

Truy vấn tham số:

~~~sql
SELECT placed_at, order_id, order_state, total_cents
FROM shop.orders_by_customer_day
WHERE customer_id = ?
  AND order_day = ?
LIMIT 20;
~~~

Bảng này giới hạn theo partition **`(customer_id, order_day)`**. Hãy triển khai một entity composite key phù hợp, dùng `@Query` với `?0`/`?1` hoặc `CqlTemplate` với hai marker `?`, rồi viết test với hai khách hàng để chứng minh không trộn dữ liệu.

Để lấy nhiều ngày, ứng dụng phải xử lý nhiều partition và phân trang/gộp kết quả có giới hạn; không giả định một query thiếu partition key với `LIMIT 20` là đủ.

### Bài B — Kiểm tra thứ tự binding

Đổi nhầm thứ tự hai tham số trong `changeState`:

~~~java
// Sai: kiểu tham số không tương ứng với marker.
cqlTemplate.execute(
    "UPDATE shop.orders_by_id " +
    "SET order_state = ? WHERE order_id = ?",
    orderId,
    newState
);
~~~

Hãy chạy test để quan sát lỗi kiểu dữ liệu CQL. Sửa lại thứ tự thành `newState, orderId` và xác nhận kiểm thử đạt.

### Bài C — Thêm kiểm tra điều kiện tồn tại

Yêu cầu: đổi trạng thái **chỉ khi order tồn tại**. Hãy tìm hiểu lệnh CQL:

~~~sql
UPDATE shop.orders_by_id
SET order_state = ?
WHERE order_id = ?
IF EXISTS;
~~~

Đây là **lightweight transaction (LWT)**. Hãy dùng API trả về kết quả có thể đọc cột `[applied]` và kiểm tra giá trị đó trước khi nói cập nhật thành công. `IF EXISTS` tăng chi phí và độ trễ so với update thông thường; chỉ dùng khi hợp đồng nghiệp vụ thực sự yêu cầu tính nguyên tử của điều kiện.

### Bài D — Đánh giá đọc đúng cột

Thêm một cột `shipping_note text` rất dài vào bảng. Đo và so sánh response/payload khi:

1. Repository trả entity với `SELECT *`.
2. `CqlTemplate` chỉ trả `order_id`, `order_state`, `total_cents`.

Cần hiểu rằng giảm cột chắc chắn giảm dữ liệu **được trả về**, nhưng tiết kiệm I/O disk phía Cassandra còn phụ thuộc cấu trúc lưu trữ, cache và kích thước cột; nên đo trên workload đại diện.

## 14. Tiêu chí tự đánh giá

| Tiêu chí | Đạt khi |
| --- | --- |
| CQL tham số hóa | Không ghép dữ liệu request trực tiếp vào query |
| `@Query` | Dùng `?0` đúng vị trí, trả `Optional<CustomerOrder>` |
| `CqlTemplate` | Dùng `?` và RowMapper, trả DTO chỉ có dữ liệu cần |
| Schema | Có partition key phù hợp với điều kiện `WHERE` |
| Đọc dữ liệu | Repository và template cùng trả đúng giá trị |
| Ghi dữ liệu | Update có binding đúng thứ tự, test xác minh trạng thái |
| Trường hợp vắng mặt | Không ném lỗi null khi ID không tồn tại |
| Isolation | UUID test riêng, cleanup theo primary key |
| Bảo mật | Không nối identifier/input tùy ý, có kiểm soát quyền nghiệp vụ |
| Vận hành | Có kiểm soát giới hạn query, timeout và retry theo ngữ nghĩa |

## 15. Checklist hoàn thành

- [ ] Schema `shop.orders_by_id` được tạo và có đúng partition key `order_id`.
- [ ] Entity mapping `CustomerOrder` và `CustomerOrderRepository` hoạt động với Cassandra thật.
- [ ] `@Query` sử dụng `?0` đúng và không đặt marker trong nháy đơn.
- [ ] `CqlTemplate.query(...)` dùng bind marker `?` và mapper đọc đúng cột.
- [ ] `CqlTemplate.execute(...)` update đúng `order_state`, `order_id`.
- [ ] Hiểu rằng UPDATE không kèm điều kiện có thể upsert khi row chưa có.
- [ ] Không dùng bind marker thay tên bảng/cột hoặc dùng `ALLOW FILTERING` để bù lỗi partition key.
- [ ] Đã chạy integration test trong môi trường có Docker và kiểm tra cả ID tồn tại/vắng mặt.
- [ ] Không tạo `CqlSession` theo từng request; endpoint Testcontainers được lấy động.
- [ ] Khi cần đọc theo `customer_id`, có kế hoạch bảng/read model theo truy vấn phù hợp.
- [ ] Mức consistency, paging và hiệu năng production được kiểm tra riêng trên cluster đại diện.

**Ghi nhớ:** `@Query` và `CqlTemplate` cùng giúp thực thi **CQL có tham số**, nhưng ở hai mức trừu tượng khác nhau: `@Query` gắn truy vấn vào repository, còn `CqlTemplate` cho phép chủ động đọc từng cột và ánh xạ kết quả. Trong Cassandra, truy vấn đúng còn phải có **partition key, giới hạn dữ liệu và hợp đồng nghiệp vụ** phù hợp. Hãy kiểm chứng bằng dữ liệu thật và test cả đường đọc lẫn đường ghi.

