# RelationalMappingContext, R2dbcConverter và chiến lược truy cập dữ liệu

Trong Spring Data R2DBC, việc đọc và ghi một entity đi qua nhiều thành phần có trách nhiệm riêng. **RelationalMappingContext** mô tả cấu trúc entity và lưu metadata ánh xạ quan hệ; **R2dbcConverter** chuyển đổi giữa đối tượng Java và dữ liệu R2DBC; còn **chiến lược truy cập dữ liệu** phối hợp mapping, SQL và đặc điểm của hệ quản trị cơ sở dữ liệu để thực hiện thao tác.

Ba thành phần này giải quyết ba câu hỏi khác nhau:

- Một lớp Java có những thuộc tính nào được lưu vào bảng, và chúng tương ứng với bảng/cột nào?
- Giá trị trong entity được chuyển thành dữ liệu có thể bind vào câu SQL như thế nào, và dữ liệu một dòng được dựng lại thành entity ra sao?
- Ứng dụng nên thao tác qua repository, template hay SQL trực tiếp, và SQL cần thích nghi với dialect nào?

## 1. Vị trí của các thành phần trong kiến trúc

Khi ứng dụng dùng Spring Data R2DBC, đường đi phổ biến của một thao tác entity có thể hình dung như sau:

~~~mermaid
flowchart TB
    A["Ứng dụng / Service"]
    B["Repository reactive<br/>hoặc R2dbcEntityTemplate"]
    C["ReactiveDataAccessStrategy<br/>phối hợp mapping và SQL"]
    D["RelationalMappingContext<br/>metadata entity và property"]
    E["R2dbcConverter<br/>entity ↔ Row / OutboundRow"]
    F["R2dbcDialect<br/>quy tắc SQL và bind marker"]
    G["DatabaseClient"]
    H["ConnectionFactory"]
    I["R2DBC Driver"]
    J[("Cơ sở dữ liệu")]

    A --> B
    B --> C
    C --> D
    C --> E
    C --> F
    B --> G
    C --> G
    G --> H
    H --> I
    I --> J
~~~

Đây là sơ đồ khái niệm. Trong cấu hình thực tế, các thành phần được Spring tạo và liên kết với nhau; ứng dụng thường chỉ tương tác trực tiếp với repository hoặc template. Khi cần viết SQL, ứng dụng có thể dùng DatabaseClient.

Các vai trò cần được tách bạch:

| Thành phần | Trách nhiệm chính | Không đảm nhiệm |
|---|---|---|
| RelationalMappingContext | Xây dựng và cung cấp metadata ánh xạ entity quan hệ | Mở kết nối, chạy SQL hoặc tự bind tham số |
| R2dbcConverter | Đọc/ghi dữ liệu giữa entity và cấu trúc dữ liệu R2DBC | Quyết định toàn bộ câu SQL hoặc quản lý connection |
| ReactiveDataAccessStrategy | Phối hợp converter và dialect để hỗ trợ truy cập dữ liệu | Là repository hoặc connection pool |
| R2dbcDialect | Cung cấp khác biệt SQL theo hệ quản trị, như bind marker và cách biểu diễn một số câu lệnh | Thay thế R2DBC driver |
| DatabaseClient | Thực thi SQL qua hạ tầng Spring R2DBC | Cung cấp mô hình repository và aggregate mapping đầy đủ |
| ConnectionFactory / driver | Cung cấp kết nối và thực hiện giao tiếp theo R2DBC SPI | Ánh xạ domain entity theo quy ước Spring Data |

## 2. RelationalMappingContext: mô tả cấu trúc entity

RelationalMappingContext thuộc Spring Data Relational. Spring Data R2DBC sử dụng nó để biết một kiểu Java được ánh xạ vào mô hình dữ liệu quan hệ như thế nào.

Context không chỉ đọc annotation một lần rồi bỏ đi. Nó quản lý metadata ánh xạ cho các kiểu persistent entity, cho phép các thành phần mapping tra cứu thông tin về entity và từng property trong quá trình đọc/ghi.

### 2.1. Metadata của entity và property

Hai khái niệm metadata quan trọng là:

- **RelationalPersistentEntity**: mô tả một persistent entity, bao gồm tên bảng, định danh và danh sách property được lưu trữ.
- **RelationalPersistentProperty**: mô tả một property, bao gồm tên cột, kiểu dữ liệu, vai trò của property và metadata mapping liên quan.

Ví dụ, entity sau biểu diễn bảng đơn hàng:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public record PurchaseOrder(
    @Id Long id,
    @Column("order_code") String orderCode,
    @Column("customer_name") String customerName,
    @Version Long version
) {}
~~~

Từ khai báo này, metadata mapping có thể xác định:

| Property Java | Metadata | Cột quan hệ |
|---|---|---|
| id | @Id | Khóa định danh |
| orderCode | @Column("order_code") | order_code |
| customerName | @Column("customer_name") | customer_name |
| version | @Version | Cột version dùng cho optimistic locking |

**@Table** xác định bảng được ánh xạ. **@Column** cho phép chỉ định tên cột rõ ràng. **@Id** đánh dấu định danh và **@Version** đánh dấu thuộc tính phiên bản dùng trong cơ chế optimistic locking.

Nếu không khai báo tên bảng hoặc cột tường minh, quy tắc đặt tên của mapping context sẽ được áp dụng. Quy tắc này có thể được điều chỉnh bằng NamingStrategy. Vì vậy, khi schema hiện có dùng tên khác với quy ước của ứng dụng, hãy khai báo annotation hoặc cấu hình naming strategy nhất quán.

### 2.2. NamingStrategy và tên bảng/cột

NamingStrategy định nghĩa cách chuyển tên kiểu và tên property Java thành tên bảng, cột hoặc tên khóa quan hệ theo quy ước của ứng dụng.

Ví dụ, một ứng dụng có thể muốn tên property camelCase được chuyển thành snake_case:

| Tên Java | Tên SQL mong muốn |
|---|---|
| PurchaseOrder | purchase_order |
| orderCode | order_code |
| createdAt | created_at |
| customerAddress | customer_address |

Đây là ví dụ về quy tắc đặt tên; tên cuối cùng còn phụ thuộc naming strategy đang cấu hình và annotation trên entity.

Nên dùng NamingStrategy khi toàn dự án có một quy ước nhất quán. Dùng **@Table** hoặc **@Column** khi một bảng/cột có tên đặc biệt, hoặc khi cần ánh xạ một entity vào schema có sẵn mà không tuân theo quy ước chung.

Tránh để cùng một property vừa phụ thuộc naming strategy vừa bị đổi tên ở nhiều lớp khác nhau. Khi tên cột không khớp, lỗi thường xuất hiện lúc tạo SQL hoặc lúc đọc giá trị từ Row.

### 2.3. Property nào được đưa vào mapping?

Spring Data Relational dựa vào metadata để xác định property nào là dữ liệu persistent và cách biểu diễn chúng.

Một số annotation thường gặp:

- **@Id**: đánh dấu khóa định danh.
- **@Column**: khai báo tên cột.
- **@Table**: khai báo tên bảng.
- **@Transient**: loại property khỏi persistent mapping.
- **@Version**: khai báo trường version cho optimistic locking.
- **@MappedCollection**: mô tả cách ánh xạ collection thuộc aggregate, bao gồm cột liên kết và cột khóa nếu cần.
- **@Embedded**: ánh xạ các property của value object vào cùng hàng dữ liệu, có thể dùng prefix để tránh trùng tên cột.

Ví dụ về property không được lưu:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public record Customer(
    @Id Long id,
    String name,
    @Transient String displayLabel
) {}
~~~

**displayLabel** là giá trị phục vụ hiển thị trong ứng dụng. Annotation **@Transient** báo cho mapping rằng property này không phải cột cần đọc/ghi.

### 2.4. Mapping quan hệ đi theo mô hình aggregate

Spring Data Relational tổ chức việc lưu dữ liệu theo aggregate. Aggregate root là điểm bắt đầu của một nhóm đối tượng được lưu như một đơn vị. Những đối tượng thuộc aggregate có thể được ánh xạ thành các hàng ở bảng liên quan theo quy tắc relational mapping.

Điều này khác với cách một ORM có thể tự động quản lý một object graph lớn bằng identity map và lazy loading. Với Spring Data R2DBC, không nên mặc định rằng mọi quan hệ Java sẽ tự động được tải bằng join hoặc proxy lazy. Hãy mô tả rõ cấu trúc aggregate, các khóa liên kết và truy vấn cần thiết.

Ví dụ, một đơn hàng có danh sách dòng hàng. Dòng hàng thuộc aggregate của đơn hàng; mapping collection cần xác định cột tham chiếu về đơn hàng và, nếu phù hợp, cột lưu thứ tự hoặc khóa phần tử. Nếu một đối tượng là aggregate độc lập, thường nên lưu tham chiếu định danh và truy vấn aggregate đó bằng thao tác riêng.

## 3. R2dbcConverter: chuyển đổi entity và dữ liệu R2DBC

RelationalMappingContext cho biết entity được mô tả như thế nào. R2dbcConverter sử dụng metadata đó để chuyển đổi dữ liệu khi đọc và ghi.

Trong Spring Data R2DBC, interface **R2dbcConverter** định nghĩa hợp đồng đọc/ghi. Triển khai mapping phổ biến là **MappingR2dbcConverter**.

Hai chiều chuyển đổi chính là:

- **Ghi**: entity Java → OutboundRow, chứa các giá trị được ánh xạ theo cột để bind vào câu lệnh SQL.
- **Đọc**: Row và metadata từ R2DBC → entity Java, thông qua constructor/property mapping và conversion phù hợp.

Converter không tự mở connection. Nó cũng không thay thế dialect hay SQL generator. Nhiệm vụ của nó là chuyển đổi dữ liệu theo metadata và quy tắc conversion.

### 3.1. Luồng ghi entity xuống cơ sở dữ liệu

Giả sử ứng dụng lưu một đơn hàng:

~~~java
PurchaseOrder order = new PurchaseOrder(
    null,
    "PO-2026-001",
    "Nguyen An",
    null
);
~~~

Ở mức khái niệm, quá trình ghi diễn ra như sau:

1. Thành phần truy cập dữ liệu nhận entity cần lưu.
2. RelationalMappingContext cung cấp metadata của PurchaseOrder và các property.
3. R2dbcConverter duyệt các property persistent, xác định tên cột và chuyển giá trị thành dạng có thể bind.
4. Kết quả mapping được biểu diễn bằng OutboundRow.
5. ReactiveDataAccessStrategy và dialect tham gia tạo câu SQL phù hợp, bao gồm bind marker theo hệ quản trị.
6. DatabaseClient thực thi câu SQL thông qua ConnectionFactory và R2DBC driver.

Có thể mô tả ngắn gọn:

~~~text
PurchaseOrder
    ↓ metadata
RelationalMappingContext
    ↓ entity/property mapping
R2dbcConverter
    ↓
OutboundRow
    ↓ SQL + bind marker
ReactiveDataAccessStrategy / R2dbcDialect
    ↓
DatabaseClient → R2DBC driver → Database
~~~

Ví dụ này chỉ mô tả luồng. Việc tạo giá trị ID, bỏ qua ID null khi insert, cập nhật version và cách phát sinh SQL phụ thuộc loại thao tác cùng cấu hình mapping.

### 3.2. Luồng đọc dữ liệu thành entity

Khi truy vấn trả về một dòng, driver cung cấp Row và metadata của các cột. Converter sử dụng metadata entity để dựng lại đối tượng:

1. SQL được thực thi và trả về kết quả.
2. Spring R2DBC nhận Row từ driver.
3. R2dbcConverter xác định entity đích và metadata property.
4. Giá trị từng cột được đọc, chuyển kiểu nếu cần.
5. Spring Data tạo entity thông qua constructor phù hợp hoặc cơ chế property access của entity.

~~~text
Database Row
    ↓
R2dbcConverter
    ↕ RelationalMappingContext
Kiểu dữ liệu / property conversion
    ↓
PurchaseOrder
~~~

Việc ánh xạ dựa trên tên cột và metadata. Nếu truy vấn SQL tùy chỉnh trả về alias không phù hợp với tên cột mà entity mong đợi, quá trình mapping có thể không tìm được giá trị tương ứng. Khi dùng projection hoặc SQL có alias riêng, cần bảo đảm alias khớp với mapping hoặc tự viết bước ánh xạ.

### 3.3. Conversion giữa kiểu Java và kiểu cơ sở dữ liệu

Không phải kiểu domain nào cũng có thể bind trực tiếp vào driver. Ví dụ, ứng dụng có thể biểu diễn tiền tệ bằng một kiểu riêng:

~~~java
import java.math.BigDecimal;

public record Money(BigDecimal amount, String currency) {}
~~~

Giả sử schema lưu tiền dưới dạng chuỗi có cấu trúc amount:currency. Có thể định nghĩa converter đọc và ghi:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@ReadingConverter
public class StringToMoneyConverter implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        String[] parts = source.split(":", 2);
        return new Money(
            new BigDecimal(parts[0]),
            parts[1]
        );
    }
}

@WritingConverter
public class MoneyToStringConverter implements Converter<Money, String> {

    @Override
    public String convert(Money source) {
        return source.amount() + ":" + source.currency();
    }
}
~~~

Đây là ví dụ minh họa quy tắc chuyển đổi; định dạng thực tế cần có kiểm tra dữ liệu đầu vào, quy tắc locale và xử lý lỗi phù hợp.

Các converter cần được đăng ký vào cấu hình custom conversions của Spring Data R2DBC, thường thông qua **R2dbcCustomConversions**. Chỉ tạo class converter mà không đăng ký thì mapping context/converter đang chạy sẽ không tự động sử dụng chúng.

Cần phân biệt hai lớp chuyển đổi:

- **Spring Data conversion** chuyển kiểu domain của ứng dụng sang kiểu Java mà tầng R2DBC có thể bind, hoặc chuyển ngược lại khi đọc.
- **R2DBC driver codec/type support** chịu trách nhiệm biểu diễn kiểu Java thành kiểu dữ liệu giao thức mà database driver hỗ trợ.

Nếu database có kiểu đặc thù như JSON, enum native hoặc kiểu hình học, hãy kiểm tra khả năng hỗ trợ của driver. Spring converter và codec của driver giải quyết hai phần khác nhau của quá trình.

## 4. ReactiveDataAccessStrategy và R2dbcDialect

Mapping entity mới giải quyết phần dữ liệu. Để thực thi truy vấn, ứng dụng còn cần chiến lược truy cập dữ liệu phối hợp mapping với SQL.

Trong Spring Data R2DBC, **ReactiveDataAccessStrategy** là abstraction tập hợp các quy tắc cần thiết cho truy cập dữ liệu reactive. Nó làm việc với converter và dialect để các thao tác entity có thể được chuyển thành SQL phù hợp.

**R2dbcDialect** đại diện cho khác biệt giữa các hệ quản trị cơ sở dữ liệu. Những khác biệt này có thể gồm cách tạo bind marker, cú pháp hoặc cách biểu diễn một số thao tác SQL và các chi tiết riêng của hệ quản trị.

Ví dụ về bind marker:

| Hệ quản trị / dialect | Dạng placeholder thường gặp |
|---|---|
| PostgreSQL | $1, $2 |
| H2 | ? |
| SQL Server | @P0, @P1 |

Bảng trên chỉ minh họa hình thức placeholder phổ biến. Cách bind thực tế do dialect và driver phối hợp quyết định; ứng dụng nên dùng API bind tham số của Spring thay vì tự ghép chuỗi placeholder.

Vai trò phối hợp:

- MappingContext cung cấp metadata entity và property.
- Converter tạo/đọc dữ liệu theo metadata và custom conversions.
- Dialect cung cấp các quy tắc SQL phụ thuộc database.
- ReactiveDataAccessStrategy kết hợp các thông tin này cho thao tác truy cập dữ liệu.
- DatabaseClient gửi câu SQL và tham số xuống hạ tầng R2DBC.

Không nên tự viết lại quy tắc bind marker trong repository hoặc service. Dùng dialect giúp mã truy cập dữ liệu thích nghi tốt hơn khi thay đổi hệ quản trị hoặc driver được hỗ trợ.

## 5. Chiến lược truy cập dữ liệu: Repository, Template hay DatabaseClient?

Spring Data R2DBC cung cấp nhiều mức trừu tượng. Việc chọn API nên dựa trên độ phức tạp của thao tác và mức kiểm soát SQL mà ứng dụng cần.

### 5.1. Repository: phù hợp với thao tác aggregate phổ biến

Repository thích hợp khi ứng dụng cần CRUD và các truy vấn có thể mô tả bằng tên phương thức hoặc truy vấn khai báo.

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface PurchaseOrderRepository
        extends ReactiveCrudRepository<PurchaseOrder, Long> {

    Flux<PurchaseOrder> findByCustomerName(String customerName);
}
~~~

Service có thể sử dụng repository và giữ kiểu reactive xuyên suốt:

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    public Mono<PurchaseOrder> findById(Long id) {
        return repository.findById(id);
    }

    public Flux<PurchaseOrder> findByCustomer(String customerName) {
        return repository.findByCustomerName(customerName);
    }
}
~~~

Ưu điểm là mã service tập trung vào nghiệp vụ, trong khi Spring Data xử lý phần lớn thao tác repository. Repository phù hợp khi mô hình aggregate và truy vấn không cần kiểm soát SQL quá chi tiết.

### 5.2. R2dbcEntityTemplate: thao tác entity linh hoạt

Khi cần truy vấn hoặc cập nhật entity theo điều kiện động, nhưng vẫn muốn tận dụng mapping của Spring Data, có thể dùng **R2dbcEntityTemplate**.

~~~java
import org.springframework.data.r2dbc.core.R2dbcEntityTemplate;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import reactor.core.publisher.Flux;

public class PurchaseOrderQuery {

    private final R2dbcEntityTemplate template;

    public PurchaseOrderQuery(R2dbcEntityTemplate template) {
        this.template = template;
    }

    public Flux<PurchaseOrder> findByCustomer(String customerName) {
        Query query = Query.query(
            Criteria.where("customerName").is(customerName)
        );

        return template.select(query, PurchaseOrder.class);
    }
}
~~~

Template làm việc ở mức entity và dùng chiến lược mapping của Spring Data. Ứng dụng không cần tự viết toàn bộ quy trình chuyển từng cột thành property như khi dùng SQL trực tiếp.

Tên property trong Criteria cần khớp với mapping của entity. Khi có annotation đổi tên cột, hãy kiểm tra cách API diễn giải property path và SQL identifier trong phiên bản Spring Data đang dùng.

Template hữu ích khi:

- Điều kiện truy vấn được xây dựng động.
- Cần thao tác insert/update/select/delete ở mức entity.
- Repository abstraction không diễn đạt thuận tiện truy vấn.
- Muốn giữ entity mapping và conversion của Spring Data.

### 5.3. DatabaseClient: kiểm soát SQL trực tiếp

Khi truy vấn có join, CTE, window function, SQL đặc thù hoặc projection riêng, **DatabaseClient** cho phép ứng dụng viết SQL trực tiếp.

~~~java
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Flux;

public class PurchaseOrderSqlQuery {

    private final DatabaseClient databaseClient;

    public PurchaseOrderSqlQuery(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Flux<PurchaseOrderSummary> findSummary(String customerName) {
        return databaseClient.sql("""
                SELECT order_code, customer_name
                FROM purchase_order
                WHERE customer_name = :customerName
                ORDER BY order_code
                """)
            .bind("customerName", customerName)
            .map((row, metadata) -> new PurchaseOrderSummary(
                row.get("order_code", String.class),
                row.get("customer_name", String.class)
            ))
            .all();
    }
}
~~~

Trong ví dụ này, ứng dụng tự kiểm soát SQL và cách ánh xạ kết quả thành projection. DatabaseClient không tự suy ra mọi quy tắc entity mapping như repository hoặc template; callback map là nơi ứng dụng chuyển dữ liệu Row thành kiểu kết quả mong muốn.

~~~java
public record PurchaseOrderSummary(
    String orderCode,
    String customerName
) {}
~~~

DatabaseClient phù hợp khi SQL là phần quan trọng của thao tác. Hãy bind tham số thay vì nối giá trị đầu vào vào chuỗi SQL để tránh lỗi quoting và nguy cơ SQL injection.

### 5.4. So sánh các lựa chọn

| Tiêu chí | Repository | R2dbcEntityTemplate | DatabaseClient |
|---|---|---|---|
| Mức trừu tượng | Cao | Trung bình, ở mức entity | Thấp hơn, ở mức SQL |
| Entity mapping | Tự động qua Spring Data | Tự động qua Spring Data | Thường do ứng dụng viết trong mapping callback |
| CRUD phổ biến | Rất phù hợp | Phù hợp | Phải tự viết SQL |
| Điều kiện động | Tùy khả năng repository/query | Linh hoạt với query API | Linh hoạt bằng SQL |
| SQL đặc thù, join phức tạp | Có thể dùng query khai báo khi phù hợp | Có giới hạn theo API entity | Kiểm soát trực tiếp |
| Khi nên chọn | Nghiệp vụ CRUD và truy vấn ổn định | Truy vấn entity linh hoạt | Cần SQL tùy chỉnh hoặc projection riêng |

Các lựa chọn này có thể cùng tồn tại trong một ứng dụng. Ví dụ, repository xử lý CRUD thông thường, template xử lý bộ lọc động, còn DatabaseClient xử lý báo cáo có SQL phức tạp. Nên đặt mỗi kiểu truy cập sau một ranh giới service/repository rõ ràng để dễ kiểm soát transaction và kiểm thử.

## 6. Cấu hình mapping và custom conversion

Spring Boot thường tự cấu hình các bean cần thiết khi có dependency và cấu hình kết nối phù hợp. Trong ứng dụng cấu hình thủ công, cần bảo đảm các thành phần sử dụng cùng một bộ metadata, converter và dialect tương thích với R2DBC driver.

Các điểm cấu hình quan trọng gồm:

1. **NamingStrategy**: thống nhất cách suy ra tên bảng, cột và khóa liên kết.
2. **Mapping annotations**: khai báo tên bảng/cột hoặc các property đặc biệt ngay trên entity.
3. **R2dbcCustomConversions**: đăng ký converter đọc/ghi cho kiểu domain riêng.
4. **R2dbcDialect**: sử dụng dialect tương ứng với hệ quản trị cơ sở dữ liệu.
5. **ConnectionFactory**: trỏ tới R2DBC driver và database mà ứng dụng thực sự dùng.

Khi mở rộng cấu hình, nên tùy chỉnh đúng extension point mà phiên bản Spring Data R2DBC đang dùng hỗ trợ. Các API cấu hình có thể thay đổi giữa các thế hệ Spring Data, vì vậy không nên sao chép một đoạn cấu hình từ phiên bản khác mà chưa kiểm tra dependency và tài liệu tương ứng.

## 7. Các lỗi thường gặp và cách xử lý

### 7.1. Không tìm thấy cột hoặc giá trị trả về là null

Nguyên nhân thường gặp:

- Tên cột trong database khác với tên được suy ra từ property.
- Annotation **@Column** không khớp schema.
- SQL tùy chỉnh dùng alias không khớp tên mà converter đang ánh xạ.
- Projection chỉ select một phần cột nhưng lại yêu cầu dựng entity đầy đủ.

Cách xử lý: kiểm tra metadata mapping, tên cột thực tế và danh sách cột được select. Với SQL tùy chỉnh, đặt alias rõ ràng hoặc tự ánh xạ sang projection riêng.

### 7.2. Không chuyển đổi được kiểu dữ liệu

Nguyên nhân thường gặp:

- Property dùng kiểu domain riêng nhưng chưa đăng ký converter.
- Converter chỉ được viết cho chiều đọc hoặc chiều ghi trong khi ứng dụng cần cả hai.
- Giá trị Java sau conversion không được R2DBC driver hỗ trợ.
- Database dùng kiểu native cần codec riêng của driver.

Cách xử lý: xác định lỗi xảy ra ở conversion Spring Data hay ở driver; đăng ký converter đúng chiều và kiểm tra kiểu bind mà driver hỗ trợ.

### 7.3. Tên placeholder không phù hợp với database

Nguyên nhân thường gặp: SQL được viết với placeholder theo một hệ quản trị khác hoặc ứng dụng tự ghép placeholder thủ công.

Cách xử lý: dùng named parameter và API bind của Spring R2DBC; để dialect và driver xử lý cách biểu diễn bind marker.

### 7.4. Truy vấn trả về entity không đầy đủ

Nguyên nhân thường gặp: SQL chỉ select một vài cột, trong khi converter đang cố dựng entity có constructor/property bắt buộc cần thêm dữ liệu.

Cách xử lý: chọn đủ cột cần thiết cho entity hoặc ánh xạ kết quả sang projection/DTO riêng. Với báo cáo, projection thường mô tả chính xác dữ liệu trả về hơn entity ghi dữ liệu.

### 7.5. Kỳ vọng quan hệ tự tải hoặc lazy loading

Spring Data R2DBC không nên được sử dụng với giả định rằng nó có đầy đủ hành vi của một ORM blocking truyền thống. Hãy thiết kế aggregate và truy vấn rõ ràng; nếu cần dữ liệu từ aggregate khác, thực hiện truy vấn tương ứng và kết hợp publisher trong service.

### 7.6. Đưa thao tác blocking vào luồng reactive

R2DBC được thiết kế cho I/O reactive. Nếu một converter hoặc callback tự thực hiện file I/O, gọi JDBC hay chờ một dịch vụ blocking, thao tác đó có thể làm nghẽn luồng xử lý. Converter nên tập trung vào chuyển đổi dữ liệu trong bộ nhớ; công việc I/O nên được đặt ở tầng thích hợp và điều phối rõ ràng.

## 8. Nguyên tắc thiết kế khi triển khai

Một số nguyên tắc giúp giữ mapping và truy cập dữ liệu dễ bảo trì:

- Giữ entity mapping tập trung và nhất quán. Dùng annotation cho ngoại lệ của schema; dùng NamingStrategy cho quy ước chung.
- Xem RelationalMappingContext là nguồn metadata cho entity. Tránh tự tạo một bộ quy tắc tên cột khác trong service.
- Viết converter nhỏ, xác định rõ chiều đọc/ghi và có xử lý dữ liệu không hợp lệ.
- Đăng ký converter một cách tường minh qua cấu hình Spring Data R2DBC.
- Dùng repository cho thao tác aggregate phổ biến, template cho thao tác entity linh hoạt và DatabaseClient cho SQL tùy chỉnh.
- Bind tham số bằng API thay vì nối chuỗi SQL.
- Khi đổi database, kiểm tra dialect, driver, kiểu dữ liệu và các truy vấn đặc thù.
- Giữ publisher reactive xuyên suốt tầng service; tránh chặn luồng bằng cách gọi block() hoặc subscribe() tùy tiện trong mã nghiệp vụ.
- Với kết quả báo cáo hoặc projection một phần, dùng kiểu kết quả riêng thay vì cố dựng entity đầy đủ.

## 9. Tóm lược luồng xử lý

Khi một repository lưu entity, Spring Data R2DBC phối hợp các thành phần theo chuỗi trách nhiệm sau:

1. Repository hoặc R2dbcEntityTemplate nhận yêu cầu thao tác.
2. RelationalMappingContext cung cấp metadata của entity và property.
3. R2dbcConverter chuyển entity thành dữ liệu ghi hoặc chuyển Row thành entity.
4. ReactiveDataAccessStrategy phối hợp conversion và R2dbcDialect để chuẩn bị thao tác SQL.
5. DatabaseClient thực thi SQL thông qua ConnectionFactory và R2DBC driver.
6. Kết quả được chuyển đổi thành entity hoặc projection và phát ra dưới dạng publisher reactive.

Khi lựa chọn API, hãy bắt đầu từ nhu cầu của thao tác: repository cho CRUD và truy vấn nghiệp vụ phổ biến; R2dbcEntityTemplate khi cần truy vấn entity linh hoạt; DatabaseClient khi cần toàn quyền kiểm soát SQL. Dù chọn cách nào, RelationalMappingContext và R2dbcConverter vẫn giúp giữ quy tắc ánh xạ dữ liệu quan hệ nhất quán trong tầng Spring Data R2DBC.

