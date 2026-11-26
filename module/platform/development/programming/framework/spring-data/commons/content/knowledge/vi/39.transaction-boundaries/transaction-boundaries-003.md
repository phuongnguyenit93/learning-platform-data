# Phối hợp repository, fragment và template trong cùng giao dịch

## 1. Ranh giới phải bao trùm một kết quả nghiệp vụ

Trong chương **Ranh giới giao dịch** của module **SPRING_DATA_COMMONS**, câu hỏi quan trọng là: khi một nghiệp vụ dùng nhiều đường truy cập dữ liệu, điều gì bảo đảm chúng cùng thành công hoặc cùng bị hủy?

Giả sử thao tác đặt hàng gồm ba bước:

1. Dùng repository để lưu đơn hàng.
2. Dùng repository fragment để giữ số lượng tồn kho bằng SQL có điều kiện.
3. Dùng template để ghi một sự kiện vào bảng dữ liệu nội bộ.

Kết quả nghiệp vụ mong muốn là:

~~~text
Có đơn hàng + đã giữ hàng + có sự kiện nội bộ
hoặc
Không có đơn hàng mới + tồn kho không đổi + không có sự kiện mới
~~~

Nếu bước thứ hai thất bại sau khi bước thứ nhất đã commit, ứng dụng có một đơn hàng chưa được giữ hàng. Nếu bước thứ ba tự commit bằng connection khác, một lần rollback phía service vẫn có thể để lại sự kiện không tương ứng với đơn hàng nào.

Repository, fragment và template là các cách tổ chức truy cập dữ liệu. Chúng không tự tạo ra ba giao dịch độc lập, cũng không tự bảo đảm cùng một giao dịch. Phải xét transaction manager, tài nguyên được quản lý và ngữ cảnh thực thi.

## 2. Vai trò của từng thành phần

| Thành phần | Trách nhiệm trong ví dụ | Điều cần tránh suy diễn |
| --- | --- | --- |
| Repository | Lưu aggregate đơn hàng bằng abstraction CRUD | Một lần gọi `save` không tự bao trùm những lần gọi khác trong service |
| Fragment | Đóng gói thao tác giữ tồn kho đặc thù | Là một phần của repository không có nghĩa mọi tài nguyên bên trong đều tự tham gia |
| Data access template | Chạy SQL ghi sự kiện và SQL trong fragment | Tên có chữ Template không đồng nghĩa có một transaction manager riêng |
| Service | Xác định toàn bộ đơn vị công việc đặt hàng | Annotation chỉ có tác dụng khi hạ tầng transaction thực sự áp dụng |
| Transaction manager | Bắt đầu, tham gia, commit hoặc rollback tài nguyên phù hợp | Một manager cục bộ không tự quản lý mọi database và mọi store |

Trong mô hình fragment của Spring Data Commons, repository kế thừa một interface bổ sung và dùng implementation tương ứng. Implementation có thể nhận dependency qua Spring, chẳng hạn một `JdbcTemplate`. Đây là khả năng mở rộng repository, không phải cam kết giao dịch xuyên mọi store. [Tài liệu custom repository implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html).

Cần phân biệt hai nghĩa của “template”:

- **Data access template** như `JdbcTemplate`, `MongoTemplate` hoặc `R2dbcEntityTemplate` thực hiện thao tác dữ liệu.
- **TransactionTemplate** là API xác định ranh giới giao dịch bằng callback cho luồng imperative.

Đưa SQL vào `JdbcTemplate` không thay thế việc xác định ranh giới cho toàn bộ nghiệp vụ.

## 3. Điều kiện để cùng tham gia

Trước khi viết code, hãy lập bản đồ tài nguyên:

| Câu hỏi | Câu trả lời trong ví dụ chính |
| --- | --- |
| Module truy cập dữ liệu nào? | Spring Data JDBC |
| Store nào? | Một database quan hệ có hỗ trợ transaction |
| Tài nguyên do manager quản lý? | Một `DataSource` dùng chung |
| Manager nào? | Bean `ordersTransactionManager` |
| Fragment dùng gì? | `ordersJdbcTemplate` |
| Template ghi sự kiện dùng gì? | Cũng `ordersJdbcTemplate` |
| Cách thực thi? | Gọi đồng bộ trong luồng imperative |
| Điểm bắt đầu đơn vị công việc? | Method `placeOrder` trên service do Spring quản lý |

Với JDBC transaction manager cục bộ, Spring gắn connection giao dịch với ngữ cảnh luồng và tài nguyên `DataSource`. `JdbcTemplate` dùng cơ chế lấy connection có nhận biết transaction của Spring. Vì thế nó có thể tham gia giao dịch hiện hữu thay vì tự mở một đường ghi độc lập. [DataSourceTransactionManager API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html).

Hai connection pool cùng URL, tài khoản và database vẫn có thể cấp hai connection độc lập. Trong ví dụ này, mọi đường truy cập phải nhận đúng `DataSource` đã cấu hình cho manager; “cùng URL” chưa đủ.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant P as Service proxy
    participant S as OrderService
    participant R as OrderRepository
    participant F as Inventory fragment
    participant T as JdbcTemplate
    participant D as Database
    C->>P: placeOrder(...)
    P->>D: Bắt đầu transaction T1
    P->>S: Gọi nghiệp vụ
    S->>R: save đơn hàng
    R->>D: INSERT trong T1
    S->>F: reserveUnits(...)
    F->>T: UPDATE có điều kiện
    T->>D: UPDATE trong T1
    S->>T: Ghi sự kiện nội bộ
    T->>D: INSERT trong T1
    S-->>P: Kết quả
    alt Mọi bước và commit thành công
        P->>D: COMMIT T1
        P-->>C: Trả kết quả
    else Phát sinh lỗi yêu cầu rollback
        P->>D: ROLLBACK T1
        P-->>C: Truyền lỗi
    end
~~~

Sơ đồ giả định caller chưa có giao dịch bao ngoài. Nếu method tham gia giao dịch của caller, quyền kết thúc giao dịch vật lý thuộc ranh giới ngoài đó.

## 4. Schema cho bài toán đặt hàng

Ví dụ dùng schema có cú pháp identity phù hợp với PostgreSQL hoặc H2 được cấu hình tương ứng:

~~~sql
CREATE TABLE inventory_item (
    id BIGINT PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0)
);

CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    item_id BIGINT NOT NULL REFERENCES inventory_item(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    customer_ref VARCHAR(120) NOT NULL
);

CREATE TABLE order_event (
    event_id VARCHAR(36) PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_order(id),
    event_type VARCHAR(40) NOT NULL
);
~~~

DDL cần được điều chỉnh theo dialect thực tế. Ví dụ yêu cầu các bảng và các câu lệnh tham gia transaction; không đưa DDL vào giữa nghiệp vụ rồi mặc định nó rollback như DML trên mọi database.

Một bộ dữ liệu ban đầu:

~~~sql
INSERT INTO inventory_item(id, available) VALUES (101, 10);
~~~

Bảng `order_event` là dữ liệu nội bộ cùng database. Nó chưa đại diện cho việc gửi email hay publish message ra hệ thống bên ngoài. Một transaction database không tự thu hồi các tác dụng phụ đó.

## 5. Cấu hình để các đường truy cập dùng chung tài nguyên

Ví dụ cấu hình thủ công dưới đây giả định đã có một bean `DataSource` tên `ordersDataSource`. Các repository và class minh họa đặt trong cùng package được quét; service và fragment cần được component scan hoặc khai báo bean.

~~~java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
@EnableJdbcRepositories(
    basePackageClasses = {
        PurchaseOrderRepository.class,
        InventoryRepository.class
    },
    transactionManagerRef = "ordersTransactionManager"
)
public class OrdersPersistenceConfig extends AbstractJdbcConfiguration {

    @Bean("ordersTransactionManager")
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean("ordersJdbcTemplate")
    JdbcTemplate ordersJdbcTemplate(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    NamedParameterJdbcOperations namedParameterJdbcOperations(
            @Qualifier("ordersJdbcTemplate") JdbcTemplate jdbcTemplate) {
        return new NamedParameterJdbcTemplate(jdbcTemplate);
    }
}
~~~

Ở đây:

- Repository dùng hạ tầng Spring Data JDBC được cung cấp từ `AbstractJdbcConfiguration`.
- `NamedParameterJdbcOperations` dùng cùng `JdbcTemplate` với fragment và service.
- Transaction manager nhận đúng `ordersDataSource`.
- `transactionManagerRef` chọn manager cho repository.
- Method service cũng sẽ chọn bean `ordersTransactionManager` một cách tường minh.

Cấu trúc thiết lập JDBC repositories và các bean mapping có trong [hướng dẫn cấu hình Spring Data JDBC](https://docs.spring.io/spring-data/relational/reference/jdbc/getting-started.html); lựa chọn manager cho repository được mô tả tại [EnableJdbcRepositories API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/config/EnableJdbcRepositories.html).

`JdbcTransactionManager` là một JDBC transaction manager có thêm exception translation ở bước commit/rollback. [JdbcTransactionManager API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html).

Đây là cấu hình minh họa cho một nhóm repository JDBC. Khi ứng dụng dùng Spring Boot auto-configuration, cần phối hợp với cấu hình sẵn có thay vì đăng ký thêm một bộ bean trùng chức năng. Với nhiều nhóm store, hãy kiểm tra từng nhóm repository nhận mapping infrastructure và manager nào.

## 6. Repository và fragment của ví dụ

Các public type bên dưới được hiểu là nằm trong các file Java riêng khi đưa vào một dự án.

### 6.1. Aggregate và repository lưu đơn hàng

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public record PurchaseOrder(
    @Id Long id,
    @Column("item_id") Long itemId,
    int quantity,
    @Column("customer_ref") String customerRef
) {
}
~~~

~~~java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Record yêu cầu mức Java phù hợp. Constructor, mapping và cơ chế sinh ID cần được dự án cấu hình theo phiên bản đang sử dụng. Trong luồng sau, code luôn dùng instance trả về từ `save` để lấy ID của entity bất biến.

### 6.2. Repository tồn kho mở rộng fragment

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("inventory_item")
public record InventoryItem(@Id Long id, int available) {
}
~~~

~~~java
public interface InventoryReservation {
    void reserveUnits(long itemId, int units);
}
~~~

~~~java
import org.springframework.data.repository.CrudRepository;

public interface InventoryRepository
        extends CrudRepository<InventoryItem, Long>,
                InventoryReservation {
}
~~~

### 6.3. Implementation fragment dùng JdbcTemplate

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class InventoryReservationImpl
        implements InventoryReservation {

    private final JdbcTemplate jdbcTemplate;

    public InventoryReservationImpl(
            @Qualifier("ordersJdbcTemplate")
            JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void reserveUnits(long itemId, int units) {
        if (units <= 0) {
            throw new IllegalArgumentException("units phải lớn hơn 0");
        }

        int updated = jdbcTemplate.update(
            """
            UPDATE inventory_item
               SET available = available - ?
             WHERE id = ?
               AND available >= ?
            """,
            units, itemId, units
        );

        if (updated != 1) {
            throw new InsufficientStockException(itemId);
        }
    }
}
~~~

~~~java
public class InsufficientStockException extends RuntimeException {
    public InsufficientStockException(long itemId) {
        super("Không thể giữ tồn kho cho item " + itemId);
    }
}
~~~

Tên `InventoryReservationImpl` bám theo tên fragment với hậu tố `Impl`. Cần đặt nó trong phạm vi discovery tương ứng; việc ghép fragment vẫn là một phần cấu hình cần được xác nhận trong ứng dụng.

Điều kiện `available >= ?` đặt kiểm tra số lượng ngay trong câu cập nhật. Code không dùng một lần đọc tồn kho trước đó làm căn cứ duy nhất để quyết định ghi. Nếu hai yêu cầu cạnh tranh, phải xét thêm isolation, khóa và khả năng database báo lỗi concurrency; bài này không tuyên bố transaction tự giải quyết mọi tranh chấp.

Trong ví dụ, “không có item” và “không đủ tồn kho” được gộp thành không thể giữ hàng. Nếu API cần phân biệt, hãy thiết kế hợp đồng lỗi rõ ràng. Một lần đọc bổ sung cũng cần được đánh giá trong bối cảnh cạnh tranh dữ liệu.

Fragment cố ý không tự bắt đầu một giao dịch mới. Nó tham gia giao dịch do service mở thông qua `JdbcTemplate` dùng chung tài nguyên. Nếu cho phép gọi fragment độc lập, cần xác định riêng hợp đồng transaction của đường gọi đó.

## 7. Service phối hợp cả ba thao tác

~~~java
import java.util.Objects;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final PurchaseOrderRepository orders;
    private final InventoryRepository inventory;
    private final JdbcTemplate jdbcTemplate;

    public OrderService(
            PurchaseOrderRepository orders,
            InventoryRepository inventory,
            @Qualifier("ordersJdbcTemplate")
            JdbcTemplate jdbcTemplate) {
        this.orders = orders;
        this.inventory = inventory;
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public Long placeOrder(
            long itemId, int quantity, String customerRef) {

        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải lớn hơn 0");
        }
        if (customerRef == null
                || customerRef.isBlank()
                || customerRef.length() > 120) {
            throw new IllegalArgumentException("customerRef không hợp lệ");
        }

        PurchaseOrder saved = orders.save(
            new PurchaseOrder(null, itemId, quantity, customerRef)
        );
        Long orderId = Objects.requireNonNull(
            saved.id(), "ID phải được cấp sau khi lưu"
        );

        inventory.reserveUnits(itemId, quantity);

        int inserted = jdbcTemplate.update(
            """
            INSERT INTO order_event(event_id, order_id, event_type)
            VALUES (?, ?, ?)
            """,
            UUID.randomUUID().toString(),
            orderId,
            "ORDER_PLACED"
        );

        if (inserted != 1) {
            throw new IllegalStateException("Không ghi được sự kiện");
        }

        return orderId;
    }
}
~~~

Thứ tự lưu đơn trước rồi giữ tồn kho được chọn để thể hiện rollback của thao tác đã chạy. Có thể chọn thứ tự khác theo nghiệp vụ và chiến lược khóa, nhưng mọi bước bắt buộc vẫn cần cùng nằm trong ranh giới đã xác định.

Trong Spring Data JDBC, các CRUD method có cấu hình transaction mặc định. Một service có transaction bao ngoài là cách tổ chức đơn vị công việc gồm nhiều lần gọi repository; không thể chỉ dựa vào transaction của từng CRUD method để đạt kết quả toàn nghiệp vụ. [Transactionality trong Spring Data JDBC](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html).

Caller phải gọi bean service thông qua cơ chế proxy có hiệu lực. Trong chế độ proxy mặc định, gọi nội bộ kiểu `this.placeOrder(...)` không kích hoạt interceptor của method đó; annotation cũng cần hạ tầng transaction được bật. [Cách áp dụng @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).

### 7.1. Kết quả kỳ vọng

Giả sử item 101 có 10 đơn vị và chưa có giao dịch bao ngoài:

| Tình huống | Đơn hàng mới | Tồn kho sau khi kết thúc | Sự kiện mới |
| --- | --- | --- | --- |
| Đặt 3 đơn vị và commit thành công | Có | 7 | Có |
| Đặt 11 đơn vị, fragment ném lỗi | Không | 10 | Không |
| Giữ 3 đơn vị thành công nhưng insert sự kiện thất bại | Không | 10 | Không |
| Validation đầu vào thất bại | Không | 10 | Không |

Nếu phương thức kết thúc phần thân bình thường nhưng commit thất bại, caller vẫn có thể nhận exception từ proxy. Không dùng việc đã đi tới câu `return` bên trong method để kết luận đã commit.

ID đã được cấp trước rollback cũng không chứng minh bản ghi còn tồn tại. Database có thể không thu hồi giá trị sequence/identity đã tiêu thụ; khoảng trống ID không phải bằng chứng mất tính nguyên tử.

## 8. REQUIRED, rollback và cấu hình bên trong

Với `REQUIRED`, một lời gọi có thể mở giao dịch khi chưa có hoặc tham gia giao dịch hiện hữu. Khi tham gia, nó không có một lần commit vật lý riêng chỉ vì method repository đã trả về. `REQUIRES_NEW` tạo giao dịch độc lập nên có thể phá yêu cầu tất cả cùng thành công của ví dụ. Các thuộc tính như isolation và read-only của phạm vi tham gia không tự ghi đè cấu hình giao dịch ngoài. [Transaction propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html).

Vì vậy, không thêm `REQUIRES_NEW` vào fragment giữ tồn kho hoặc bước ghi sự kiện để “chắc chắn dữ liệu được lưu”. Nếu tồn kho commit riêng rồi bước sau rollback, người dùng có thể bị giữ hàng dù đơn đặt không tồn tại.

Khi một helper chỉ hợp lệ bên trong giao dịch, có thể thiết kế nó như một Spring bean được intercept với `Propagation.MANDATORY`. Cấu hình đó cần chọn đúng manager và được gọi qua proxy có hiệu lực; nó không kiểm tra thay cho việc template có dùng đúng tài nguyên hay không.

Theo cấu hình rollback mặc định thông thường, `RuntimeException` và `Error` dẫn tới rollback, còn checked exception cần được xét bằng quy tắc cấu hình tương ứng. Dự án có thể thay đổi mặc định; khi dùng checked business exception, hãy khai báo chính sách rõ ràng, chẳng hạn `rollbackFor = ReservationRejectedException.class`. [Quy tắc rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html).

Đặc biệt tránh đoạn xử lý:

~~~java
try {
    inventory.reserveUnits(itemId, quantity);
} catch (InsufficientStockException ex) {
    return orderId; // Biến một nghiệp vụ thất bại thành kết quả bình thường.
}
~~~

Nếu không có thành phần nào đánh dấu rollback-only, nuốt lỗi như vậy có thể để đơn hàng commit. Nếu một phạm vi đã đánh dấu rollback-only, catch lỗi cũng không làm giao dịch trở lại khả năng commit. Hợp đồng xử lý lỗi phải giữ ý nghĩa nghiệp vụ thay vì chỉ làm mất exception.

## 9. Dùng TransactionTemplate khi cần ranh giới bằng callback

Một lựa chọn khác cho luồng imperative là `TransactionTemplate`. Ví dụ bên dưới dùng lại các dependency `orders`, `inventory` và `jdbcTemplate` của nghiệp vụ, cùng manager đã được inject đúng qualifier:

~~~java
import java.util.Objects;
import java.util.UUID;

import org.springframework.transaction.support.TransactionTemplate;

// ordersTransactionManager là bean được inject bằng qualifier tương ứng.
// Khởi tạo và cấu hình boundary một lần khi tạo bean.
TransactionTemplate boundary =
    new TransactionTemplate(ordersTransactionManager);

// Bên trong một method nghiệp vụ, sau validation đầu vào:
Long orderId = boundary.execute(status -> {
    PurchaseOrder saved = orders.save(
        new PurchaseOrder(null, itemId, quantity, customerRef)
    );

    Long savedId = Objects.requireNonNull(saved.id());
    inventory.reserveUnits(itemId, quantity);

    int inserted = jdbcTemplate.update(
        """
        INSERT INTO order_event(event_id, order_id, event_type)
        VALUES (?, ?, ?)
        """,
        UUID.randomUUID().toString(), savedId, "ORDER_PLACED"
    );

    if (inserted != 1) {
        throw new IllegalStateException("Không ghi được sự kiện");
    }

    return savedId;
});
~~~

Đây là phần thân minh họa, không phải một compilation unit độc lập. Validation vẫn theo hợp đồng của `placeOrder`; các lời gọi dữ liệu cần cùng nằm trong callback.

`TransactionTemplate` dùng manager được truyền vào, còn `JdbcTemplate` thực hiện SQL. Với propagation mặc định, callback cũng có thể tham gia giao dịch bên ngoài; kết thúc callback không phải lúc nào cũng đồng nghĩa giao dịch vật lý đã commit. Spring cung cấp `TransactionalOperator` cho ranh giới lập trình trong luồng reactive. [Programmatic transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html).

Chọn một cách biểu đạt ranh giới chính cho cùng đoạn nghiệp vụ để người đọc dễ xác định phạm vi. Bao nhiều lớp annotation và callback không làm dữ liệu nguyên tử hơn nếu chúng vẫn dùng sai tài nguyên.

## 10. Các đường khiến thao tác rời khỏi giao dịch

### 10.1. Tự mở native connection

Ví dụ dễ gây nhầm:

~~~java
try (var connection = dataSource.getConnection()) {
    // Chạy SQL bằng connection vừa lấy.
}
~~~

Nếu `dataSource` là pool thông thường, đoạn này không thể được coi là đã dùng connection mà Spring gắn cho transaction. Chỉ vì method đang mang `@Transactional` không có nghĩa mọi connection được tạo bên trong đều tự được quản lý.

Ưu tiên `JdbcTemplate` hoặc một API có tích hợp transaction của Spring. Khi buộc phải dùng JDBC mức thấp, cần dùng đúng cơ chế lấy và giải phóng connection có nhận biết transaction; không tự commit hoặc đóng tài nguyên giao dịch đang do manager quản lý. [Quản lý JDBC connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html).

### 10.2. Đổi DataSource trong fragment

Giả sử repository dùng `ordersDataSource`, nhưng fragment inject một template mặc định trỏ sang `reportingDataSource`. Cả hai class vẫn có thể chạy bình thường; lỗi chỉ xuất hiện ở tính nhất quán khi rollback.

Cách tìm lỗi là theo dấu dependency:

~~~text
Repository -> JDBC operations -> DataSource A
Fragment   -> JdbcTemplate   -> DataSource B
Service    -> Manager       -> DataSource A
~~~

Hãy sửa wiring để chúng dùng cùng tài nguyên nếu đó là mục tiêu nghiệp vụ. Nếu thực sự cần A và B độc lập, phải thiết kế phối hợp nhiều tài nguyên theo khả năng hạ tầng, thay vì coi đây là một transaction cục bộ.

### 10.3. Chuyển công việc sang luồng khác

Tách ghi sự kiện sang `@Async`, `CompletableFuture` hoặc executor không giữ nguyên giả định của ví dụ imperative. Công việc mới cần hợp đồng giao dịch và xử lý lỗi riêng.

Ví dụ:

~~~text
Luồng chính:   lưu đơn -> giữ hàng -> commit
Luồng khác:                  ghi sự kiện -> lỗi
~~~

Lỗi ở luồng khác không làm giao dịch đã commit của luồng chính quay lại trạng thái trước đó. Ngay cả khi chờ future, vẫn phải xác định tài nguyên của công việc đó tham gia bằng cơ chế nào; chờ hoàn thành không tự tạo liên kết transaction.

### 10.4. Trả kết quả lazy sau khi ranh giới đã kết thúc

Nếu helper chỉ chuẩn bị một công việc để chạy sau, cần xem thời điểm SQL thực sự xảy ra. Đối với reactive, tạo publisher khác với subscribe và hoàn tất thao tác. Với tài nguyên đọc lazy, cũng cần bảo đảm thời gian sống của tài nguyên phù hợp với thời điểm sử dụng.

Phạm vi gọi method trên sơ đồ không thể thay thế việc xác định phạm vi thực thi dữ liệu.

## 11. Áp dụng theo khả năng từng store

Spring Data Commons cung cấp abstraction dùng chung, còn cơ chế tham gia transaction thuộc Spring Framework và từng module store.

| Stack | Tài nguyên cần đối chiếu | Điều cần chú ý khi phối hợp |
| --- | --- | --- |
| Spring Data JDBC + JdbcTemplate | Cùng DataSource và JDBC transaction manager | Giữ repository và template trên cùng đường connection do Spring quản lý |
| Spring Data JPA + fragment dùng EntityManager | Cùng EntityManagerFactory và JpaTransactionManager | Dùng EntityManager được tích hợp với ngữ cảnh transaction |
| JPA + JdbcTemplate | DataSource tương ứng với EntityManagerFactory | Cần hỗ trợ của JpaDialect và cơ chế lấy connection phù hợp |
| Spring Data MongoDB + MongoTemplate | MongoDatabaseFactory và session giao dịch tương ứng | Cần transaction manager cùng hạ tầng MongoDB hỗ trợ transaction |
| Spring Data R2DBC + template reactive | ConnectionFactory và reactive transaction manager | Giữ các thao tác trong cùng reactive transaction context |

### 11.1. JPA: chia sẻ transaction chưa thay thế đồng bộ trạng thái

`JpaTransactionManager` có thể phối hợp JPA với JDBC trên cùng DataSource khi cấu hình provider/dialect và connection access đáp ứng yêu cầu. Không nên thay manager JPA bằng một JDBC manager chỉ vì nghiệp vụ có thêm SQL. [JpaTransactionManager API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html).

Ngoài transaction, phải xét trạng thái đang được persistence context quản lý. Chẳng hạn, nếu một đoạn SQL cập nhật tồn kho còn code sau đó dùng một entity đã đọc trước đó, hãy kiểm chứng entity đó có phản ánh cập nhật hay không. Tương tự, SQL phụ thuộc một thay đổi JPA chưa đồng bộ xuống database cần có thứ tự thực thi phù hợp.

Không thêm `flush`, `refresh` hay `clear` vào mọi method theo thói quen. Chỉ dùng khi có yêu cầu đồng bộ cụ thể và đã xét tác động tới các entity đang được quản lý. Bài toán JDBC chính không dựa vào persistence context JPA.

### 11.2. MongoDB: cùng session là điều kiện cần xét

Đối với MongoDB, repository và `MongoTemplate` cần được cấu hình để hoạt động trong ngữ cảnh transaction phù hợp; server topology cũng phải hỗ trợ transaction. Gọi native collection API từ template không bảo đảm session tự được truyền vào mọi thao tác native. [Sessions và transactions trong Spring Data MongoDB](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html).

Vì vậy, một fragment dùng native driver phải được xem xét đến tham số session và đường gọi thực tế. Đổi tên `JdbcTemplate` thành `MongoTemplate` trong service không chuyển nguyên vẹn cơ chế JDBC sang MongoDB.

### 11.3. Reactive: phối hợp một pipeline hoàn chỉnh

Trong luồng R2DBC, thiết kế chuỗi thao tác tương ứng:

~~~text
Lưu đơn bằng repository reactive
    -> flatMap nhận đơn đã lưu
    -> thực hiện giữ tồn kho bằng fragment reactive
    -> then ghi sự kiện bằng template reactive
    -> hoàn tất dưới một ranh giới reactive transaction
~~~

Các collaborator phải có API reactive thực sự, cùng cấu hình ConnectionFactory và manager phù hợp. Fragment `void reserveUnits` của ví dụ JDBC không phải fragment reactive.

Không tự gọi `subscribe()` giữa service rồi trả publisher khác. Khi đó công việc đã tách khỏi chuỗi completion/error mà ranh giới bao ngoài cần quan sát. Cũng không dùng một transaction JDBC imperative để tuyên bố bao trùm I/O R2DBC; hai đường truy cập cần cơ chế quản lý tương ứng.

Với coroutine, cần kiểm tra adapter và transaction API được stack hỗ trợ. `suspend` mô tả khả năng tạm dừng, không tự chứng minh mọi thao tác nằm trong cùng transaction.

## 12. Ghi sự kiện cùng database và tác dụng phụ bên ngoài

Trong ví dụ, `order_event` là bảng nội bộ nên có thể rollback cùng đơn hàng. Điều đó tạo ra một dấu vết bền vững trong database khi commit thành công.

Nếu thay bước này bằng lời gọi HTTP tới dịch vụ gửi email, tình huống có thể là:

1. Email đã được gửi.
2. Database gặp lỗi ở commit.
3. Đơn hàng không được ghi nhận, nhưng email vẫn tới khách hàng.

Một thiết kế có thể cân nhắc là ghi thông tin cần phát đi vào bảng outbox cùng transaction, rồi có tiến trình riêng chuyển nó tới đích. Khi đó cần giải quyết thêm retry, đánh dấu đã xử lý, quan sát lỗi và xử lý lặp ở bên nhận. Việc ghi cùng database giải quyết một ranh giới; nó không tự chứng minh toàn bộ đường phát sự kiện chỉ chạy đúng một lần.

Bảng `order_event` hiện tại chưa có các cột và cơ chế vận hành của một outbox hoàn chỉnh. Cần bổ sung theo yêu cầu nếu muốn dùng theo mô hình đó.

Tương tự, metadata auditing như người tạo và thời điểm sửa là dữ liệu được cập nhật theo cơ chế auditing của module. Nó không tự thay thế một event nghiệp vụ, và một event log riêng cũng không tự bảo đảm auditing đã được cấu hình.

## 13. Kiểm chứng bằng kết quả sau khi giao dịch kết thúc

Một mock xác nhận đã gọi `save`, `reserveUnits` và `update` chỉ chứng minh sự điều phối lời gọi. Nó không chứng minh các câu lệnh chia sẻ transaction vật lý.

Cần kiểm thử tích hợp với store và transaction manager thực tế trong môi trường test cô lập. Một ma trận tối thiểu cho ví dụ:

| Điểm gây lỗi | Kết quả cần quan sát sau khi service kết thúc |
| --- | --- |
| Không lỗi | Có đơn, tồn kho giảm đúng, có event |
| Fragment từ chối vì thiếu hàng | Không có đơn/event mới, tồn kho giữ nguyên |
| Insert event bị database từ chối | Đơn và thay đổi tồn kho đã chạy đều bị rollback |
| Lỗi ở commit nếu hạ tầng tái hiện được | Caller không được nhận kết luận thành công sai |
| Fragment cố ý trỏ sang tài nguyên khác trong test cấu hình | Test phát hiện dữ liệu không còn nguyên tử |

Trường hợp cuối là phép kiểm tra cấu hình trong bộ test chuyên biệt, không phải một cách triển khai production.

### 13.1. Tránh để transaction của test che ranh giới service

Nếu test tự mở một transaction, service `REQUIRED` có thể tham gia transaction đó. Khi ấy một test vẫn có thể qua dù annotation ở service bị thiếu, vì môi trường test đã cung cấp ranh giới bao ngoài.

Để kiểm chứng service tự tạo và kết thúc transaction, có thể dùng test không có transaction test bao ngoài, gọi bean service rồi đọc lại dữ liệu sau khi lời gọi trả về hoặc ném lỗi. Cần phân biệt test-managed transaction với transaction của ứng dụng. [Transaction management trong Spring TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html).

Ví dụ dưới đây giả định ứng dụng test đã được cấu hình bằng Spring Boot, có schema trên và database chỉ dành cho bộ test này:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class OrderTransactionTest {

    @Autowired
    OrderService service;

    @Autowired
    @Qualifier("ordersJdbcTemplate")
    JdbcTemplate jdbc;

    @BeforeEach
    void resetData() {
        // Chỉ chạy trên database test cô lập, không dùng chung song song.
        jdbc.update("DELETE FROM order_event");
        jdbc.update("DELETE FROM purchase_order");
        jdbc.update("DELETE FROM inventory_item");
        jdbc.update(
            "INSERT INTO inventory_item(id, available) VALUES (?, ?)",
            101L, 10
        );
    }

    @Test
    void successfulOrderCommitsAllThreeEffects() {
        Long id = service.placeOrder(101L, 3, "customer-A");

        assertNotNull(id);
        assertEquals(1L, count("purchase_order"));
        assertEquals(1L, count("order_event"));
        assertEquals(7, available());

        Long eventOrderId = jdbc.queryForObject(
            "SELECT order_id FROM order_event",
            Long.class
        );
        assertEquals(id, eventOrderId);
    }

    @Test
    void insufficientStockRollsBackOrderInsert() {
        assertThrows(
            InsufficientStockException.class,
            () -> service.placeOrder(101L, 11, "customer-B")
        );

        assertEquals(0L, count("purchase_order"));
        assertEquals(0L, count("order_event"));
        assertEquals(10, available());
    }

    private long count(String table) {
        // table chỉ nhận hằng tên bảng trong code test này.
        Long result = jdbc.queryForObject(
            "SELECT COUNT(*) FROM " + table,
            Long.class
        );
        return result.longValue();
    }

    private int available() {
        Integer result = jdbc.queryForObject(
            "SELECT available FROM inventory_item WHERE id = ?",
            Integer.class, 101L
        );
        return result.intValue();
    }
}
~~~

Test này không có `@Transactional` trên class hoặc method. Dữ liệu fixture cần được quản lý riêng; khi chạy song song phải dùng database/schema hoặc tập khóa được cô lập.

Hai test trên chưa bao phủ lỗi sau khi tồn kho đã giảm. Cần thêm một tình huống khiến database từ chối insert `order_event`, chẳng hạn một constraint hoặc trigger chỉ có trong fixture chuyên biệt, rồi xác nhận cả đơn lẫn tồn kho quay về trạng thái ban đầu. Cơ chế gây lỗi phải phù hợp database test.

Không thay template thật bằng một mock rồi chỉ kiểm tra exception để kết luận thao tác SQL đã rollback. Muốn chứng minh tham gia tài nguyên, phải quan sát trạng thái đã lưu ở đúng store sau ranh giới.

Các đoạn test trong bài là hướng dẫn thiết kế kiểm chứng; chúng chưa phải báo cáo đã chạy trong một dự án cụ thể.

## 14. Chẩn đoán theo dấu hiệu

| Dấu hiệu | Giả thuyết cần xét | Bằng chứng hữu ích |
| --- | --- | --- |
| Đơn còn tồn tại sau lỗi thiếu hàng | Service không có ranh giới hiệu lực hoặc lỗi bị nuốt | Đường gọi proxy, chính sách lỗi, dữ liệu sau khi method kết thúc |
| Tồn kho vẫn giảm dù đơn rollback | Fragment dùng giao dịch/tài nguyên độc lập | Qualifier, DataSource thực tế, cấu hình propagation |
| Event tồn tại nhưng đơn không tồn tại ở một store khác | Bước event không thuộc tài nguyên của manager | Sơ đồ dependency và đích ghi thật |
| Chỉ test tích hợp có transaction ngoài mới qua | Test đang cung cấp ranh giới thay service | Chạy tình huống service không có transaction test bao ngoài |
| Có ID trả về trong debug nhưng caller vẫn nhận lỗi | Commit hoặc interceptor sau phần thân thất bại | Exception ngoài proxy và trạng thái database |
| Reactive service trả về trước nhưng tác vụ còn chạy riêng | Subscription bị tách | Vị trí subscribe, chuỗi completion/error |
| Kết quả khác giữa các kiểu truy cập JPA và SQL | Trạng thái persistence context chưa đồng bộ | SQL thực thi, thứ tự flush và entity đang được quản lý |

Log “transaction active” hoặc kiểm tra một cờ trong thread chỉ là đầu mối chẩn đoán. Một thread có transaction cho tài nguyên A không chứng minh template đang ghi tài nguyên B đã tham gia. Trạng thái lưu sau commit/rollback vẫn là bằng chứng hành vi cần có.

Khi bật log transaction/SQL trong test, hãy dùng nó để xác định thứ tự thao tác, manager và connection. Không đưa dữ liệu nhạy cảm vào log chỉ để theo dõi giao dịch.

## 15. Tự kiểm tra kiến thức

1. Vì sao transaction mặc định của từng CRUD method chưa đủ cho nghiệp vụ có ba bước?
2. Điều gì cần giống nhau giữa repository JDBC, fragment dùng JdbcTemplate và transaction manager?
3. Hai DataSource cùng URL có đủ để kết luận chúng cùng transaction không?
4. Nếu fragment gọi native connection hoặc chuyển việc sang executor, cần kiểm tra lại giả định nào?
5. Vì sao thêm REQUIRES_NEW vào bước giữ tồn kho có thể làm sai hợp đồng đặt hàng?
6. Khi lỗi bị catch rồi trả về kết quả bình thường, những điều kiện nào quyết định giao dịch còn commit được không?
7. Vì sao test không có transaction test bao ngoài giúp đánh giá ranh giới service rõ hơn?
8. Cần quan sát gì để chứng minh lỗi ở bước ghi event đã rollback cả tồn kho?
9. Đâu là khác biệt giữa JdbcTemplate và TransactionTemplate?
10. Khi chuyển sang JPA, MongoDB hoặc R2DBC, tài nguyên và ngữ cảnh nào phải được đối chiếu lại?

Điểm quyết định là xác định một đơn vị công việc rõ ràng, để mọi đường truy cập dữ liệu tham gia đúng tài nguyên và đúng cơ chế quản lý của store. Repository giữ abstraction, fragment đóng gói thao tác đặc thù, template cung cấp cách truy cập phù hợp; ranh giới giao dịch cần phối hợp cả ba theo cùng hợp đồng nghiệp vụ.
