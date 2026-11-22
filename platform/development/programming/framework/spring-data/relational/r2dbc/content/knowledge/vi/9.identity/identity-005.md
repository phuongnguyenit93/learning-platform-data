# Tự cấp UUID hoặc định danh trước khi lưu

Trong Spring Data Relational R2DBC, định danh của một entity có thể được tạo bởi cơ sở dữ liệu hoặc được cấp ngay trong ứng dụng trước khi ghi. Tự cấp UUID giúp ứng dụng biết ID ngay khi tạo đối tượng, thuận tiện cho việc tạo quan hệ giữa các đối tượng, phát sự kiện, ghi log, xử lý dữ liệu phân tán và thiết kế thao tác idempotent.

Tuy nhiên, việc gán ID trước khi gọi `save` có một điểm quan trọng: Spring Data phải xác định entity là mới hay đã tồn tại. Một entity có ID khác `null` có thể bị xem là entity đã tồn tại và được cập nhật thay vì insert. Vì vậy, lựa chọn chiến lược ID cần đi cùng cách Spring Data nhận diện trạng thái mới của entity.

Bài học này trình bày cách tạo UUID trong ứng dụng, cách ánh xạ UUID vào schema, cách điều khiển new-entity detection, lựa chọn giữa ID ứng dụng và ID database, cũng như các vấn đề về tính duy nhất, hiệu năng và kiểm thử.

## 1. ID có vai trò gì trong mô hình dữ liệu?

ID là định danh ổn định của một bản ghi. Nó cho phép ứng dụng tham chiếu đến entity mà không phải dựa vào những thuộc tính có thể thay đổi như tên, email hoặc trạng thái.

Một khóa chính tốt thường có các đặc điểm:

- Duy nhất trong phạm vi bảng hoặc phạm vi được thiết kế.
- Ổn định trong suốt vòng đời của bản ghi.
- Không mang ý nghĩa nghiệp vụ dễ thay đổi.
- Có kiểu dữ liệu và cách biểu diễn nhất quán giữa entity, schema và các tham chiếu.
- Có constraint ở database để ngăn hai bản ghi dùng cùng một ID.

Ví dụ, email có thể được dùng để đăng nhập nhưng không phải lúc nào cũng là khóa chính phù hợp. Người dùng có thể đổi email; một ID riêng giúp các bảng khác tiếp tục tham chiếu đến cùng một người.

Trong Spring Data Relational, thuộc tính khóa chính thường được đánh dấu bằng `@Id`:

```java
import java.util.UUID;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public record Customer(
    @Id UUID id,
    String email,
    String displayName
) {}
```

`@Id` cho Spring Data biết property nào là định danh của entity. Annotation này không tự quy định ID được tạo ở đâu. Việc tạo ID có thể diễn ra trong ứng dụng, trong database hoặc trong một hệ thống cấp ID riêng.

## 2. Tạo UUID trong ứng dụng

Java cung cấp `java.util.UUID`. Cách đơn giản nhất để tạo UUID ngẫu nhiên là `UUID.randomUUID()`:

```java
import java.util.UUID;

UUID id = UUID.randomUUID();
```

Phương thức này tạo UUID phiên bản 4 dựa trên số ngẫu nhiên. ID có thể được tạo trước khi truy cập database, vì vậy ứng dụng biết định danh ngay khi khởi tạo entity.

Ví dụ tạo đơn hàng:

```java
import java.math.BigDecimal;
import java.util.UUID;

public record NewOrder(
    UUID id,
    Long customerId,
    BigDecimal total
) {
    public static NewOrder create(
            Long customerId,
            BigDecimal total) {
        return new NewOrder(
            UUID.randomUUID(),
            customerId,
            total
        );
    }
}
```

Service có thể chuyển command thành entity và lưu:

```java
public Mono<Order> create(NewOrder command) {
    Order order = new Order(
        command.id(),
        command.customerId(),
        command.total(),
        OrderStatus.NEW,
        null
    );

    return orders.save(order);
}
```

Ví dụ trên giả định entity `Order` có một thuộc tính version nullable được dùng để nhận diện entity mới; phần này sẽ được trình bày ở các mục tiếp theo. Nếu entity chỉ có ID được gán sẵn và không có cơ chế nhận diện trạng thái mới phù hợp, lời gọi `save` có thể đi theo nhánh update.

### Lợi ích của việc cấp ID sớm

Tự cấp ID trước khi lưu hữu ích trong các trường hợp:

- Tạo một aggregate gồm nhiều đối tượng cần tham chiếu lẫn nhau trước khi ghi.
- Đưa ID vào log, trace hoặc event ngay khi bắt đầu xử lý nghiệp vụ.
- Tạo message hoặc command có định danh ổn định trước khi transaction ghi database.
- Xây dựng thao tác idempotent, trong đó một request retry vẫn dùng cùng một ID đã xác định.
- Tạo dữ liệu ở nhiều node mà không cần hỏi database để lấy số thứ tự tiếp theo.

Việc có ID sớm không đồng nghĩa bản ghi đã tồn tại trong database. Ứng dụng cần phân biệt trạng thái “đã có định danh” với trạng thái “đã được lưu thành công”.

## 3. Chọn kiểu UUID và định dạng lưu trữ

UUID có độ dài logic 128 bit. Java biểu diễn nó bằng `java.util.UUID`, còn cách lưu trong database phụ thuộc hệ quản trị.

| Hệ quản trị | Kiểu thường dùng | Ghi chú |
| --- | --- | --- |
| PostgreSQL | `UUID` | Có kiểu UUID native và driver R2DBC hỗ trợ mapping tương ứng. |
| MySQL | `BINARY(16)` hoặc `CHAR(36)` | Cần thống nhất byte order và converter nếu dùng dạng nhị phân. |
| SQL Server | `uniqueidentifier` | Có kiểu UUID riêng của hệ quản trị. |
| Hệ quản trị không có UUID native | `CHAR(36)`, `VARCHAR(36)` hoặc `BINARY(16)` | Chọn định dạng và quy tắc chuyển đổi rõ ràng. |

Với PostgreSQL, schema có thể khai báo:

```sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total NUMERIC(12, 2) NOT NULL,
    status VARCHAR(20) NOT NULL
);
```

Entity dùng kiểu `UUID` tương ứng:

```java
@Table("orders")
public record Order(
    @Id UUID id,
    @Column("customer_id") Long customerId,
    BigDecimal total,
    OrderStatus status,
    @Version Long version
) {}
```

Với MySQL, nếu lưu UUID dưới dạng `BINARY(16)`, cần kiểm tra driver có mapping trực tiếp `UUID` hay không. Nếu không, có thể cần converter chuyển đổi UUID sang byte array và ngược lại. Nếu dùng `CHAR(36)`, cần thống nhất chữ hoa/thường, dấu gạch nối, collation và độ dài cột.

Không nên đổi kiểu cột giữa `BINARY(16)` và `CHAR(36)` mà không có migration chuyển dữ liệu. Các ứng dụng và dịch vụ khác tham chiếu cùng ID phải dùng cùng quy ước biểu diễn.

## 4. UUID v4, UUID v7 và các lựa chọn khác

Không phải mọi định danh đều có đặc tính giống nhau.

| Loại định danh | Đặc điểm | Khi cân nhắc |
| --- | --- | --- |
| UUID v4 | Ngẫu nhiên, không thể hiện thứ tự thời gian. Java `UUID.randomUUID()` tạo loại này. | Phù hợp cho định danh phân tán và triển khai đơn giản. |
| UUID v7 | Có thành phần thời gian giúp ID có thứ tự gần với thời điểm tạo. | Cân nhắc khi muốn cải thiện tính locality của index và vẫn cần UUID. |
| ULID | Chuỗi 26 ký tự, có thành phần thời gian và phần ngẫu nhiên. | Hữu ích khi cần ID dạng chuỗi có thứ tự từ điển theo thời gian. |
| Snowflake-style ID | Số nguyên kết hợp thời gian, node và sequence theo một thuật toán. | Phù hợp khi cần ID số có thứ tự và có hạ tầng cấp ID được quản lý. |
| Identity/sequence | Database cấp số theo cơ chế của hệ quản trị. | Phù hợp khi muốn khóa số nguyên và chấp nhận lấy ID từ database. |

UUID v4 phân bố ngẫu nhiên. Với một số cấu trúc B-tree, việc chèn ID ngẫu nhiên có thể làm tăng page split và giảm locality so với khóa có thứ tự. UUID v7 có thành phần thời gian, nên có thể cải thiện tính tuần tự của insert trong một số workload. Hiệu quả thực tế phụ thuộc database, index, phân bố tải và cách lưu trữ; cần đo bằng workload thật.

UUID v7 cũng để lộ thông tin thời gian gần đúng. Nếu thời điểm tạo là thông tin nhạy cảm trong miền nghiệp vụ, hãy cân nhắc hệ quả này.

Java `UUID.randomUUID()` không tạo UUID v7. Nếu chọn UUID v7, dùng thư viện hoặc cơ chế được hỗ trợ rõ ràng trong nền tảng và thống nhất định dạng giữa mọi producer.

ULID không phải UUID. Nếu schema dùng kiểu UUID native, không thể mặc nhiên bind chuỗi ULID như một UUID. Cần chọn kiểu cột và converter tương ứng.

## 5. Vấn đề quan trọng: Spring Data xác định entity mới như thế nào?

`ReactiveCrudRepository.save(entity)` không đơn giản luôn chạy `INSERT`. Spring Data cần xác định entity là mới hay đã tồn tại để chọn insert hoặc update.

Theo cơ chế mặc định, Spring Data sử dụng thông tin về version property nếu entity có `@Version`; nếu không, nó thường dựa vào ID. Với ID được gán sẵn và khác `null`, entity có thể bị nhận diện là đã tồn tại.

Ví dụ entity chỉ có ID:

```java
@Table("orders")
public record Order(
    @Id UUID id,
    Long customerId,
    BigDecimal total
) {}
```

Khi tạo đối tượng:

```java
Order order = new Order(
    UUID.randomUUID(),
    42L,
    new BigDecimal("125.00")
);
```

`id` đã khác `null`. Nếu dùng chiến lược nhận diện mặc định chỉ dựa trên ID, Spring Data có thể xem entity là đã tồn tại và thực hiện update. Vì bản ghi chưa có trong database, update có thể không tác động hàng nào hoặc dẫn đến hành vi không như mong đợi.

Cần thiết kế rõ cách đánh dấu entity mới.

## 6. Dùng @Version để nhận diện entity mới có ID được cấp sẵn

Một cách phù hợp là thêm thuộc tính version nullable và đánh dấu bằng `@Version`:

```java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("orders")
public record Order(
    @Id UUID id,
    Long customerId,
    BigDecimal total,
    @Version Long version
) {}
```

Khi tạo entity mới, truyền ID đã cấp nhưng để `version` là `null`:

```java
Order order = new Order(
    UUID.randomUUID(),
    42L,
    new BigDecimal("125.00"),
    null
);
```

Spring Data sử dụng version property để xác định entity mới. Version chưa có giá trị cho biết entity chưa được lưu. Sau insert, Spring Data khởi tạo version theo cơ chế optimistic locking. Khi entity được đọc lại, version đã có giá trị và lần `save` tiếp theo được xử lý như một thao tác cập nhật.

Có thể khai báo schema:

```sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total NUMERIC(12, 2) NOT NULL,
    version BIGINT NOT NULL
);
```

Version không chỉ phục vụ nhận diện trạng thái mới. Nó còn hỗ trợ optimistic locking: câu lệnh update kiểm tra version hiện tại. Nếu một transaction khác đã cập nhật bản ghi, thao tác với version cũ sẽ không cập nhật được và Spring Data báo lỗi optimistic locking.

Ví dụ service:

```java
public Mono<Order> create(Long customerId, BigDecimal total) {
    Order order = new Order(
        UUID.randomUUID(),
        customerId,
        total,
        null
    );

    return orders.save(order);
}
```

Hãy giữ version property trong entity được tải và truyền qua các bước cập nhật. Không tự đặt lại version về `null` cho entity đã tồn tại, vì việc đó có thể khiến Spring Data hiểu sai trạng thái của entity.

Nếu ứng dụng không cần optimistic locking, `@Version` vẫn mang ý nghĩa bổ sung về concurrency. Hãy quyết định có muốn bảo vệ cập nhật đồng thời hay không thay vì thêm version một cách máy móc.

## 7. Dùng Persistable khi muốn tự điều khiển trạng thái mới

Một lựa chọn khác là implement `Persistable<ID>`. Interface này cung cấp `getId()` và `isNew()`, cho phép entity tự quyết định nó đang ở trạng thái mới hay đã tồn tại.

Ví dụ cấu trúc:

```java
import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.domain.Persistable;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer implements Persistable<UUID> {

    @Id
    private UUID id;

    private String email;

    @Transient
    private boolean newEntity = true;

    protected Customer() {
    }

    public Customer(UUID id, String email) {
        this.id = id;
        this.email = email;
    }

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public void markNotNew() {
        this.newEntity = false;
    }
}
```

`@Transient` đánh dấu `newEntity` là trạng thái trong bộ nhớ, không phải cột của bảng. `isNew()` trả về `true` để yêu cầu insert và `false` để yêu cầu update.

Điểm cần quản lý cẩn thận là thời điểm chuyển `newEntity` sang `false`. Chỉ đánh dấu entity đã tồn tại sau khi insert thành công. Nếu đánh dấu trước khi publisher hoàn tất rồi insert thất bại, lần thử tiếp theo có thể bị định tuyến sang update.

Với entity được tải từ database, trạng thái `newEntity` phải được khởi tạo là `false`. Có thể quản lý điều này bằng entity callback của Spring Data Relational hoặc một cơ chế mapping tập trung. Không nên để một entity được tải lại vẫn báo `isNew() == true`.

Chọn `Persistable` khi ứng dụng có lý do rõ ràng để tự quản lý trạng thái mới. Nếu entity đã có `@Version` và version property phù hợp, dùng cơ chế version thường đơn giản hơn.

## 8. Phân biệt ID được cấp trước với ID do database tạo

Có hai chiến lược chính:

### Ứng dụng cấp ID

Ứng dụng tạo UUID trước khi gọi repository:

```java
UUID id = UUID.randomUUID();

Order order = new Order(
    id,
    customerId,
    total,
    OrderStatus.NEW,
    null
);

return orders.save(order);
```

Ưu điểm:

- Có ID ngay khi tạo entity.
- Có thể tạo các tham chiếu trước khi ghi.
- Không phụ thuộc sequence hoặc identity của database.
- Thuận tiện cho message, event, log và idempotency key.
- Dễ tạo dữ liệu ở nhiều instance ứng dụng.

Điểm cần chú ý:

- Phải xử lý đúng new-entity detection.
- Database vẫn cần primary key hoặc unique constraint.
- Cần thống nhất định dạng UUID giữa các dịch vụ.
- UUID ngẫu nhiên có thể ảnh hưởng locality của index tùy workload.

### Database cấp ID

Với ID tự tăng hoặc UUID default trong database, ứng dụng thường để ID là `null` và database tạo giá trị khi insert.

Ví dụ PostgreSQL:

```sql
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id BIGINT NOT NULL,
    total NUMERIC(12, 2) NOT NULL
);
```

Entity trước khi insert có ID null:

```java
Order order = new Order(
    null,
    customerId,
    total,
    OrderStatus.NEW,
    null
);
```

Spring Data có thể nhận diện entity mới dựa trên ID/version và tạo insert. Tuy nhiên, khả năng lấy lại giá trị được database sinh phụ thuộc driver và cách generated values được hỗ trợ. Nếu cần chắc chắn nhận được UUID ngay sau insert, hãy xác minh hành vi với driver thực tế hoặc dùng SQL tường minh có cơ chế trả về ID.

Với PostgreSQL, có thể dùng `DatabaseClient` và `RETURNING`:

```java
return databaseClient.sql("""
        INSERT INTO orders (customer_id, total)
        VALUES (:customerId, :total)
        RETURNING id
        """)
    .bind("customerId", customerId)
    .bind("total", total)
    .map((row, metadata) -> row.get("id", UUID.class))
    .one();
```

Câu lệnh bỏ cột `id`, vì vậy default `gen_random_uuid()` được áp dụng. `RETURNING` phát ID vừa được tạo. Cú pháp này là PostgreSQL-specific; hệ quản trị khác có cơ chế generated key riêng.

## 9. Không nhầm @Id với @GeneratedValue của JPA

Spring Data Relational R2DBC dùng `org.springframework.data.annotation.Id` để đánh dấu ID. Không nên bê nguyên chiến lược `@GeneratedValue` của JPA sang R2DBC rồi kỳ vọng driver xử lý giống Hibernate.

Cơ chế sinh ID trong Spring Data Relational phụ thuộc cách entity được nhận diện là mới, metadata mapping, khả năng generated values của driver và schema database. Với UUID tự cấp, ứng dụng gán giá trị trực tiếp. Với ID do database cấp, schema và câu lệnh insert phải cho database cơ hội tạo giá trị.

Nếu một dự án dùng cả JPA và R2DBC, hãy tránh import nhầm annotation cùng tên hoặc giả định một entity mapping dùng được nguyên vẹn cho cả hai công nghệ.

## 10. Tạo ID trước cho aggregate có nhiều đối tượng

Một lợi ích rõ ràng của UUID là có thể tạo ID cho nhiều đối tượng liên quan trước khi lưu.

Ví dụ một đơn hàng có nhiều dòng hàng:

```java
UUID orderId = UUID.randomUUID();

Order order = new Order(
    orderId,
    customerId,
    total,
    OrderStatus.NEW,
    null
);

List<OrderLine> lines = items.stream()
    .map(item -> new OrderLine(
        UUID.randomUUID(),
        orderId,
        item.productId(),
        item.quantity()
    ))
    .toList();
```

Các `OrderLine` có thể tham chiếu đến `orderId` ngay cả khi đơn hàng chưa được insert. Điều này hữu ích khi ứng dụng cần tạo toàn bộ command hoặc cấu trúc dữ liệu trước khi bắt đầu ghi.

Tuy nhiên, ID có sẵn không thay thế transaction. Nếu đơn hàng và các dòng hàng phải được lưu cùng nhau, hãy dùng reactive transaction để bảo đảm toàn bộ thao tác thành công hoặc rollback theo đúng yêu cầu.

Nếu các đối tượng thuộc nhiều aggregate độc lập, đừng tự động gom chúng vào một transaction dài chỉ vì đã tạo ID trước. Hãy xác định ranh giới consistency theo nghiệp vụ.

## 11. UUID và tính duy nhất trong hệ thống phân tán

UUID v4 có không gian định danh rất lớn, nên xác suất trùng ngẫu nhiên cực thấp trong điều kiện tạo đúng chuẩn. Nhưng không nên bỏ constraint chỉ vì xác suất thấp.

Luôn khai báo khóa chính hoặc unique constraint:

```sql
CREATE TABLE customer (
    id UUID PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE
);
```

Database là nơi bảo vệ tính duy nhất cuối cùng. Ứng dụng cần xử lý lỗi duplicate key nếu xảy ra, thay vì giả định không thể có collision.

Một số nguyên tắc:

- Không tự tạo UUID bằng cách ghép timestamp và random string tùy ý.
- Không dùng `Math.random()` để tự dựng UUID.
- Không cắt UUID xuống một đoạn ngắn chỉ để ID dễ nhìn.
- Không loại bỏ constraint ở database vì đã tạo ID trong ứng dụng.
- Khi retry một request cần idempotency, hãy giữ nguyên ID hoặc idempotency key của lần nghiệp vụ đó; không tạo ID mới ở mỗi lần thử nếu mục tiêu là tránh tạo bản ghi trùng.

UUID không phải cơ chế phân quyền. Biết ID khó đoán không thay thế kiểm tra người dùng có quyền truy cập bản ghi hay không.

## 12. Dùng ID ổn định cho idempotency

Trong hệ thống reactive, một request có thể gặp timeout sau khi database đã commit nhưng client chưa nhận được response. Client gửi lại request có thể tạo bản ghi trùng nếu ứng dụng sinh ID mới ở mỗi lần retry.

Một cách xử lý là nhận idempotency key từ client hoặc tạo operation ID ổn định ở ranh giới tiếp nhận request. Database lưu key đó với unique constraint:

```sql
CREATE TABLE payment_request (
    id UUID PRIMARY KEY,
    idempotency_key VARCHAR(100) NOT NULL UNIQUE,
    amount NUMERIC(12, 2) NOT NULL,
    status VARCHAR(20) NOT NULL
);
```

Khi nhận lại cùng một key, service có thể tìm kết quả đã được xử lý thay vì tạo thao tác mới. Cần xác định rõ phạm vi unique của key, thời hạn lưu, cách xử lý request cùng key nhưng payload khác nhau và trạng thái đang xử lý.

UUID của entity và idempotency key có thể là hai giá trị khác nhau. Một ID định danh bản ghi; idempotency key định danh một yêu cầu nghiệp vụ có thể được gửi lại.

## 13. ID có thứ tự và tác động đến index

Khóa tăng dần như identity/sequence thường có locality tốt với B-tree vì các giá trị mới tập trung ở vùng cuối index. UUID v4 phân bố ngẫu nhiên nên insert có thể rải ra nhiều vùng index.

Tùy database và workload, điều này có thể làm tăng page split, cache miss hoặc dung lượng index. Tuy nhiên, không nên kết luận UUID luôn chậm hơn số nguyên. Kích thước index, mức độ ghi, cache, phân vùng và thiết kế truy vấn đều ảnh hưởng đến kết quả.

Có thể cân nhắc:

- UUID v7 nếu cần UUID có thứ tự thời gian gần đúng.
- ID số do database cấp nếu cần khóa gọn và có một database trung tâm.
- Binary UUID thay vì chuỗi 36 ký tự nếu hệ quản trị và driver hỗ trợ mapping ổn định.
- Dùng UUID làm public identifier và khóa số nội bộ nếu hệ thống có lý do rõ ràng để tách hai loại định danh.

Nếu dùng UUID v7 hoặc định danh có thành phần thời gian, cần xem xét khả năng lộ thời điểm tạo và mức độ đồng bộ đồng hồ giữa các node.

Đo hiệu năng bằng dữ liệu và truy vấn thật. Đừng đổi loại ID chỉ dựa trên giả định rằng một định dạng luôn tốt hơn trong mọi hệ thống.

## 14. Xử lý lỗi và retry khi lưu entity có UUID

Khi gọi `save`, publisher có thể phát entity đã lưu hoặc tín hiệu lỗi. Lỗi chỉ xuất hiện khi publisher được subscribe, vì vậy xử lý lỗi phải nằm trong chuỗi reactive.

Ví dụ:

```java
return orders.save(order)
    .onErrorMap(
        DuplicateKeyException.class,
        ex -> new OrderIdConflictException(order.id(), ex)
    );
```

Ví dụ minh họa chuyển lỗi duplicate key thành lỗi miền. Tên exception và cách phân loại cụ thể phụ thuộc driver và lớp dịch lỗi của Spring.

Không retry mọi lỗi insert một cách mù quáng. Nếu lỗi là duplicate key, tạo UUID mới có thể che giấu một lỗi logic hoặc phá vỡ idempotency. Nếu lỗi là timeout sau khi server có thể đã commit, cần tra cứu theo ID hoặc idempotency key trước khi quyết định thử lại.

Khi tạo UUID trước transaction, ứng dụng có thể giữ ID đó xuyên suốt các lần retry. Điều này giúp kiểm tra kết quả của lần ghi trước và tránh tạo định danh mới cho cùng một thao tác nghiệp vụ.

## 15. Kiểm thử chiến lược tự cấp UUID

Nên kiểm tra cả việc tạo ID, new-entity detection và hành vi database.

| Tình huống | Kết quả cần xác nhận |
| --- | --- |
| Tạo entity mới với UUID và version null | Spring Data thực hiện insert. |
| Insert thành công | Entity trả về có ID và version theo cấu hình. |
| Đọc lại entity | Entity được nhận diện là đã tồn tại. |
| Save entity đã đọc | Spring Data thực hiện update. |
| Hai entity có cùng UUID | Primary key/unique constraint từ chối bản ghi trùng. |
| Update với version cũ | Optimistic locking phát hiện xung đột nếu dùng `@Version`. |
| Database tự tạo UUID | Insert bỏ cột ID và trả về ID theo cơ chế driver hỗ trợ. |
| Retry sau timeout | Không tạo bản ghi nghiệp vụ trùng; giữ nguyên idempotency key. |

Ví dụ kiểm thử bằng Reactor Test:

```java
@Test
void insertsOrderWithApplicationAssignedUuid() {
    UUID id = UUID.randomUUID();

    Order order = new Order(
        id,
        42L,
        new BigDecimal("125.00"),
        OrderStatus.NEW,
        null
    );

    StepVerifier.create(orders.save(order))
        .assertNext(saved -> {
            assertEquals(id, saved.id());
            assertNotNull(saved.version());
        })
        .verifyComplete();
}
```

Test cần chạy với database thật tương thích và schema có cột version. Mock repository không chứng minh Spring Data đã chọn insert hay update, cũng không xác nhận driver ánh xạ UUID đúng.

## 16. Quy trình chọn và triển khai chiến lược ID

Khi thiết kế định danh cho một aggregate, có thể đi theo trình tự:

1. **Chọn phạm vi định danh:** ID duy nhất trong một bảng, một database hay toàn hệ thống phân tán?
2. **Chọn kiểu:** UUID, số nguyên, ULID hoặc định danh theo thuật toán riêng.
3. **Chọn nơi tạo:** ứng dụng, database hay dịch vụ cấp ID.
4. **Chọn schema:** kiểu cột, primary key, unique constraint và index.
5. **Chọn entity mapping:** `@Id`, kiểu Java/Kotlin và converter nếu cần.
6. **Thiết kế new-entity detection:** ID null, `@Version` hoặc `Persistable.isNew()`.
7. **Xác định transaction:** các đối tượng liên quan có cần được lưu nguyên tử không?
8. **Thiết kế idempotency:** retry có giữ nguyên ID hoặc request key không?
9. **Kiểm thử driver thật:** xác minh insert/update, generated values, duplicate key và optimistic locking.
10. **Đo hiệu năng:** kiểm tra kích thước index và tốc độ ghi với dữ liệu đại diện.

Tự cấp UUID giúp ứng dụng có định danh trước khi ghi và hỗ trợ các luồng phân tán. Để sử dụng đúng trong Spring Data R2DBC, phải phối hợp kiểu ID, schema, cơ chế xác định entity mới và cách driver thực hiện insert. Khi những quyết định đó nhất quán, UUID trở thành một phần tự nhiên của mô hình dữ liệu và luồng xử lý reactive.


