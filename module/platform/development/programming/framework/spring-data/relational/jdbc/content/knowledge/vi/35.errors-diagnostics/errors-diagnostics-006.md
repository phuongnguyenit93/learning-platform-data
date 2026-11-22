# save chọn sai insert/update hoặc không lấy được generated key

Trong Spring Data JDBC, phương thức save không đơn giản luôn chạy INSERT hoặc luôn chạy UPDATE. Trước khi tạo SQL, Spring Data xác định aggregate root đang là **mới** hay **đã tồn tại**. Nếu aggregate mới, save tạo INSERT; nếu aggregate không mới, save thực hiện UPDATE.

Vì vậy, khi save chọn sai thao tác, nguyên nhân thường nằm ở trạng thái entity, cách khai báo ID/version hoặc cách ứng dụng tạo ID. Khi INSERT thành công nhưng không nhận được generated key, cần kiểm tra mapping, schema, dialect và JDBC driver.

Bài học giải thích cách Spring Data JDBC phát hiện entity mới, cách cấu hình ID tự tăng hoặc sequence, cách dùng Persistable cho ID do ứng dụng cấp và quy trình chẩn đoán khi save đi sai nhánh hoặc không trả về ID.

## 1. save quyết định INSERT hay UPDATE như thế nào?

Spring Data JDBC xác định trạng thái aggregate root trước khi tạo kế hoạch SQL:

~~~text
repository.save(aggregate)
          |
          v
    Is aggregate new?
       /        \
     Yes         No
      |           |
      v           v
   INSERT       UPDATE
      |           |
      v           v
  Generated     Match existing
  key returned  aggregate row
~~~

Nếu aggregate được xem là mới:

- INSERT aggregate root.
- INSERT các entity được sở hữu trực tiếp hoặc gián tiếp trong aggregate.
- Database có thể sinh ID cho root nếu cột được cấu hình tự tăng.
- Spring Data JDBC đưa ID đã sinh vào instance được trả về.

Nếu aggregate được xem là đã tồn tại:

- UPDATE aggregate root.
- Các entity được sở hữu bên trong aggregate được đồng bộ theo trạng thái aggregate được truyền vào; Spring Data JDBC có thể xóa các hàng con cũ rồi insert lại các hàng hiện tại.
- Nếu UPDATE không tác động đến hàng root mong đợi, thao tác có thể thất bại vì không tìm thấy bản ghi tương ứng.

Điểm quyết định là **trạng thái của instance được truyền vào save**, không phải chỉ việc database có hay không một hàng trùng ID.

## 2. Entity State Detection: Spring Data nhận biết entity mới bằng cách nào?

Spring Data cung cấp ba chiến lược phổ biến.

| Chiến lược | Quy tắc |
| --- | --- |
| Kiểm tra @Id | Mặc định: ID null hoặc 0 với kiểu primitive thì entity được xem là mới. |
| Kiểm tra @Version | Nếu có thuộc tính version, null hoặc 0 với kiểu primitive biểu thị entity mới; giá trị khác biểu thị entity đã tồn tại. |
| Implement Persistable | Spring Data gọi isNew() do entity cung cấp. |

Nếu không có thuộc tính @Version, Spring Data quay về kiểm tra ID. Nếu entity implement Persistable, isNew() là nguồn quyết định trạng thái mới.

### 2.1. Kiểm tra @Id mặc định

Ví dụ:

~~~java
@Table("products")
public record Product(
        @Id Long id,
        String name,
        BigDecimal price
) {
}
~~~

Khi tạo sản phẩm mới:

~~~java
Product product = new Product(
        null,
        "Mechanical Keyboard",
        new BigDecimal("120.00")
);

Product saved = repository.save(product);
~~~

ID null cho biết aggregate mới. Spring Data JDBC tạo INSERT.

Khi tải lại:

~~~java
Product loaded = repository.findById(saved.id())
        .orElseThrow();
~~~

ID đã có giá trị nên aggregate được xem là đã tồn tại. Save instance này sẽ đi theo nhánh UPDATE.

### 2.2. Kiểu wrapper và primitive

Với ID kiểu wrapper:

~~~java
@Id
private Long id;
~~~

Giá trị null thể hiện ID chưa được gán.

Với ID kiểu primitive:

~~~java
@Id
private long id;
~~~

Giá trị 0 được dùng để nhận diện entity mới. Nếu ứng dụng có quy tắc ID riêng mà 0 là một ID hợp lệ, cách nhận diện mặc định này có thể không phù hợp.

Trong nhiều mô hình dùng generated key, Long thường dễ biểu diễn trạng thái chưa có ID hơn long.

### 2.3. Khi có @Version

Ví dụ:

~~~java
@Table("products")
public record Product(
        @Id UUID id,
        String name,
        @Version Long version
) {
}
~~~

Khi có @Version, Spring Data ưu tiên kiểm tra version để xác định entity mới. Version null hoặc 0 với kiểu primitive cho biết aggregate mới, kể cả khi ID đã được cấp trước, ví dụ UUID được tạo trong ứng dụng.

Sau lần lưu thành công, version được cập nhật để instance không còn được xem là mới.

@Version có thêm chức năng optimistic locking. Chỉ thêm version khi ứng dụng cần kiểm soát cập nhật đồng thời hoặc chấp nhận semantics đó; không coi nó đơn thuần là một cờ kỹ thuật không có tác động khác.

## 3. Vì sao save có thể chọn sai thao tác?

### 3.1. ID được gán trước nhưng entity không được đánh dấu là mới

Ví dụ ứng dụng tự tạo UUID:

~~~java
Product product = new Product(
        UUID.randomUUID(),
        "Keyboard",
        null
);
~~~

Nếu entity chỉ dùng kiểm tra @Id mặc định, ID khác null khiến Spring Data xem instance là đã tồn tại. Save có thể chạy UPDATE dù chưa có hàng trong database.

Kết quả có thể là lỗi update không tác động đến hàng nào, thường được biểu diễn bằng IncorrectUpdateSemanticsDataAccessException.

Các cách xử lý:

- Dùng @Version nếu aggregate cần optimistic locking và version null biểu thị entity mới.
- Implement Persistable để tự định nghĩa isNew().
- Dùng JdbcAggregateTemplate.insert() khi caller chắc chắn đang tạo aggregate mới.
- Sinh ID trong BeforeConvertCallback nếu aggregate bắt đầu với ID null và callback chỉ gán ID sau khi quyết định new/existing đã được thực hiện.

Không nên chỉ dựa vào việc UUID được tạo ở phía Java để kỳ vọng Spring Data tự hiểu đó là INSERT.

### 3.2. Entity đã tồn tại nhưng ID bị null hoặc trạng thái isNew vẫn là true

Nếu một aggregate đã có trong database nhưng instance truyền vào save lại có ID null, Spring Data có thể chọn INSERT.

Điều này có thể gây:

- Vi phạm primary key hoặc unique constraint.
- Tạo bản ghi trùng nếu ID được sinh mới.
- Tạo một aggregate mới ngoài ý muốn.
- Dữ liệu con bị insert thêm theo aggregate mới.

Kiểm tra mapping và cách dựng object. Nếu đang cập nhật, hãy giữ ID của aggregate root từ lần load trước hoặc dùng đúng ID của bản ghi cần cập nhật.

### 3.3. Persistable.isNew() luôn trả về true

Nếu entity implement Persistable nhưng isNew() không chuyển sang false sau lần insert đầu tiên, mỗi lần gọi save có thể tiếp tục đi theo nhánh INSERT.

Kết quả thường là duplicate key hoặc unique constraint violation.

Ngược lại, nếu isNew() luôn trả về false, lần lưu đầu tiên có thể chạy UPDATE và không tìm thấy hàng tương ứng.

### 3.4. Dùng nhầm annotation JPA

Spring Data JDBC dùng annotation ID của Spring Data:

~~~java
import org.springframework.data.annotation.Id;
~~~

Annotation jakarta.persistence.Id hoặc GeneratedValue thuộc JPA không thay thế mapping của Spring Data JDBC.

Ví dụ entity dùng JPA GeneratedValue nhưng không có Spring Data @Id có thể khiến Spring Data JDBC không nhận diện đúng primary key.

## 4. Dùng Persistable khi ứng dụng tự cấp ID

Persistable cho phép entity tự quyết định trạng thái mới thông qua isNew().

Ví dụ entity mutable với UUID do ứng dụng tạo:

~~~java
import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.domain.Persistable;
import org.springframework.data.relational.core.mapping.Table;

@Table("external_products")
public class ExternalProduct implements Persistable<UUID> {

    @Id
    private final UUID id;

    private String name;

    @Transient
    private boolean newEntity;

    protected ExternalProduct() {
        this.id = null;
        this.newEntity = false;
    }

    private ExternalProduct(
            UUID id,
            String name,
            boolean newEntity
    ) {
        this.id = id;
        this.name = name;
        this.newEntity = newEntity;
    }

    public static ExternalProduct create(
            UUID id,
            String name
    ) {
        return new ExternalProduct(id, name, true);
    }

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public void markPersisted() {
        this.newEntity = false;
    }

    public String getName() {
        return name;
    }

    public void rename(String name) {
        this.name = name;
    }
}
~~~

Vì ID được cấp trước khi save, cờ newEntity cho phép phân biệt:

- Aggregate mới có UUID nhưng chưa được insert.
- Aggregate đã được lưu và có cùng UUID đó.

### 4.1. Cập nhật trạng thái sau save

Nếu isNew() vẫn true sau INSERT, lần save tiếp theo sẽ lại chọn INSERT. Với entity mutable, có thể dùng AfterSaveCallback để đánh dấu instance đã được lưu:

~~~java
import org.springframework.data.relational.core.mapping.event.AfterSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class ExternalProductSavedCallback
        implements AfterSaveCallback<ExternalProduct> {

    @Override
    public ExternalProduct onAfterSave(ExternalProduct aggregate) {
        aggregate.markPersisted();
        return aggregate;
    }
}
~~~

AfterSaveCallback chạy sau khi aggregate đã được lưu và có thể trả về cùng instance hoặc instance đã thay đổi.

Thuộc tính newEntity được đánh dấu @Transient để không trở thành cột database. Nếu sử dụng property access, chú ý các accessor của Persistable có thể được phát hiện như property mapping; hãy giữ metadata này ở dạng transient theo quy tắc mapping.

Với entity immutable, callback có thể trả về một instance mới có trạng thái isNew=false thay vì sửa object hiện tại.

### 4.2. Kiểm thử Persistable

~~~java
@Test
void assignedUuidIsInsertedOnlyOnce() {
    UUID id = UUID.randomUUID();

    ExternalProduct created =
            ExternalProduct.create(id, "Keyboard");

    ExternalProduct saved = repository.save(created);

    assertEquals(id, saved.getId());
    assertFalse(saved.isNew());

    saved.rename("Mechanical Keyboard");

    ExternalProduct updated = repository.save(saved);

    assertEquals(id, updated.getId());
    assertEquals(
            "Mechanical Keyboard",
            updated.getName()
    );
}
~~~

Test này xác nhận ID do ứng dụng cấp không làm Spring Data nhầm INSERT thành UPDATE và trạng thái new được chuyển đúng sau lần save.

## 5. @Version cũng có thể giúp nhận diện entity mới

Nếu aggregate đã cần optimistic locking, thuộc tính version là cách tự nhiên để Spring Data nhận diện new/existing.

~~~java
@Table("products")
public record Product(
        @Id UUID id,
        String name,
        @Version Long version
) {
}
~~~

Khởi tạo:

~~~java
Product product = new Product(
        UUID.randomUUID(),
        "Keyboard",
        null
);

Product saved = repository.save(product);
~~~

Version null biểu thị aggregate mới. Sau INSERT, Spring Data cập nhật version trong instance trả về. Những lần save sau sẽ đi theo nhánh UPDATE và version được kiểm tra để phát hiện stale write.

Không tự đặt version khác null cho một aggregate mới nếu vẫn muốn dùng chiến lược detection này.

## 6. Dùng JdbcAggregateTemplate.insert() và update() khi đã biết trạng thái

JdbcAggregateTemplate cung cấp các thao tác:

- save(): áp dụng entity state detection giống repository save().
- insert(): bỏ qua kiểm tra new/existing và luôn INSERT.
- update(): bỏ qua kiểm tra new/existing và luôn UPDATE.
- upsert(): insert nếu ID chưa tồn tại, update nếu đã tồn tại, khi dialect hỗ trợ single-statement upsert.

Ví dụ:

~~~java
@Service
public class ProductPersistenceService {

    private final JdbcAggregateTemplate template;

    public ProductPersistenceService(
            JdbcAggregateTemplate template
    ) {
        this.template = template;
    }

    public Product create(Product product) {
        return template.insert(product);
    }

    public Product update(Product product) {
        return template.update(product);
    }
}
~~~

Dùng insert khi caller chắc chắn đang tạo aggregate mới, kể cả ID đã được gán. Dùng update khi caller chắc chắn aggregate đã tồn tại.

Không dùng insert như cách né entity state detection cho mọi thao tác. Nếu hàng đã tồn tại, INSERT sẽ vi phạm constraint. Nếu update với ID không tồn tại, thao tác có thể thất bại do không có hàng được cập nhật.

### 6.1. Upsert có phải luôn là cách tốt nhất?

Upsert có thể hữu ích khi database dialect hỗ trợ câu lệnh upsert một bước. Trong Spring Data Relational 4.1.2, JdbcAggregateOperations cung cấp upsert từ phiên bản 4.1.

Tuy nhiên:

- Aggregate root phải có ID.
- Dialect hoặc DataAccessStrategy phải hỗ trợ upsert.
- Upsert hiện không hỗ trợ optimistic locking.
- Semantics update/insert của database có thể khác nhau theo vendor.

Không thay save bằng upsert chỉ để tránh lỗi nhận diện entity mới. Hãy chọn theo semantics nghiệp vụ và concurrency requirements.

## 7. Generated key hoạt động như thế nào?

Khi database có cột ID tự tăng, Spring Data JDBC có thể lấy generated key từ JDBC driver sau INSERT và gán ID vào aggregate được trả về.

Ví dụ entity:

~~~java
@Table("products")
public record Product(
        @Id Long id,
        String name,
        BigDecimal price
) {
}
~~~

Schema H2 hoặc PostgreSQL:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL
);
~~~

Schema MySQL:

~~~sql
CREATE TABLE products (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL
);
~~~

Repository save:

~~~java
Product saved = repository.save(
        new Product(
                null,
                "Mechanical Keyboard",
                new BigDecimal("120.00")
        )
);

Long generatedId = saved.id();
~~~

Điều kiện quan trọng:

1. ID được đánh dấu bằng Spring Data @Id.
2. Schema có cơ chế sinh ID phù hợp.
3. Database dialect được phát hiện đúng.
4. JDBC driver hỗ trợ trả generated key theo cách Spring Data JDBC sử dụng.
5. Ứng dụng dùng instance trả về từ save.

### 7.1. Luôn giữ instance trả về từ save

Spring Data JDBC hỗ trợ immutable aggregate. Với record hoặc class immutable, generated ID và version được phản ánh trong instance trả về.

Ví dụ không nên làm:

~~~java
Product product = new Product(
        null,
        "Keyboard",
        new BigDecimal("120.00")
);

repository.save(product);

// Không giả định object immutable ban đầu đã nhận ID.
Long id = product.id();
~~~

Cách đúng:

~~~java
Product saved = repository.save(product);
Long id = saved.id();
~~~

Đối với mutable entity, Spring Data có thể cập nhật ID trong object, nhưng việc giữ giá trị trả về vẫn giúp code hoạt động đúng với cả mutable và immutable aggregate.

### 7.2. Database có sinh ID nhưng object trả về vẫn null

Nếu INSERT thành công nhưng ID không xuất hiện trong object trả về, hãy kiểm tra:

- Field ID có đúng annotation org.springframework.data.annotation.Id không?
- Column có thật sự là identity/auto-increment không?
- Mapping table/column có trùng với schema migration không?
- Driver và database version có hỗ trợ generated key?
- Dialect có được resolver nhận diện đúng không?
- Có đang dùng SQL INSERT tự viết qua @Query hoặc JdbcTemplate thay cho repository/template không?
- Có trigger hoặc cơ chế ID custom mà driver không trả về qua generated-key API không?

Không nên chỉ nhìn log rằng INSERT thành công rồi kết luận generated key đã được map.

## 8. Dùng database sequence với @Sequence

Một số database sử dụng sequence thay vì auto-increment column.

Spring Data JDBC hỗ trợ @Sequence trên property ID nếu dialect hỗ trợ sequence.

Ví dụ:

~~~java
@Table("products")
public class Product {

    @Id
    @Sequence(
            sequence = "product_seq",
            schema = "public"
    )
    private Long id;

    private String name;
}
~~~

Tạo sequence:

~~~sql
CREATE SEQUENCE product_seq
    START WITH 1
    INCREMENT BY 1;
~~~

Khi lưu, Spring Data JDBC thực hiện một SELECT lấy giá trị tiếp theo từ sequence rồi dùng giá trị đó trong INSERT.

Ví dụ PostgreSQL:

~~~sql
SELECT nextval('public.product_seq');
~~~

Sau đó:

~~~sql
INSERT INTO products(id, name)
VALUES (:generatedId, :name);
~~~

Sequence support trong Spring Data Relational 4.1.2 có trên H2, HSQL, PostgreSQL, DB2, Oracle và SQL Server. MySQL không hỗ trợ sequence theo cơ chế này; MySQL thường dùng AUTO_INCREMENT.

Việc lấy sequence value và INSERT là hai thao tác riêng. Nên chạy chúng trong transaction bao quanh để giữ tính nguyên tử phù hợp với use case.

## 9. Dùng BeforeConvertCallback để cấp ID trong ứng dụng

Nếu ID được tạo ở application layer nhưng aggregate ban đầu chưa có ID, có thể dùng BeforeConvertCallback để gán ID trước khi chuyển object thành kế hoạch SQL.

Ví dụ:

~~~java
import java.util.UUID;

import org.springframework.data.relational.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class ProductIdCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(Product product) {
        if (product.id() != null) {
            return product;
        }

        return new Product(
                UUID.randomUUID(),
                product.name(),
                product.price()
        );
    }
}
~~~

Tuy nhiên, có một chi tiết quan trọng: Spring Data JDBC quyết định INSERT hay UPDATE **trước** khi gọi BeforeConvertCallback.

Vì vậy:

- Nếu aggregate ban đầu có ID null, Spring đã nhận diện nó là mới; callback có thể gán UUID rồi INSERT.
- Nếu aggregate đã có UUID trước khi gọi save, kiểm tra ID mặc định có thể coi nó là đã tồn tại.
- Nếu cần cấp ID trước khi save và vẫn muốn INSERT, dùng @Version hoặc Persistable để thể hiện trạng thái mới.

Không dùng BeforeSaveCallback để tạo ID. Ở thời điểm đó quyết định INSERT/UPDATE và kế hoạch persistence đã được tạo. BeforeConvertCallback mới là hook phù hợp cho việc tạo ID.

## 10. Khi nào nên dùng Generated ID, UUID hay Sequence?

| Chiến lược | Ưu điểm | Điểm cần chú ý |
| --- | --- | --- |
| Identity/auto-increment | Đơn giản, database quản lý | Cần generated key từ driver; schema theo vendor |
| Sequence | Có thể lấy ID trước INSERT, hỗ trợ nhiều database | Cần sequence tồn tại và dialect hỗ trợ |
| UUID do ứng dụng tạo | Có ID trước khi insert, thuận tiện phân tán | Phải xử lý entity state detection |
| UUID do database tạo | Tận dụng khả năng database | Cần mapping/driver phù hợp và kiểm tra generated value |
| ID do hệ thống ngoài cấp | Phù hợp tích hợp | Cần Persistable hoặc insert rõ ràng |

Không có một chiến lược ID phù hợp cho mọi hệ thống. Hãy cân nhắc phân tán, tính sắp xếp, kích thước index, khả năng tích hợp và database mục tiêu.

## 11. Chẩn đoán save chạy UPDATE thay vì INSERT

Triệu chứng phổ biến:

- Lưu entity mới nhưng nhận lỗi update không ảnh hưởng đến hàng nào.
- Không thấy INSERT trong SQL log.
- Có UPDATE theo ID nhưng không có row tương ứng.
- Entity dùng UUID đã gán trước khi save.
- Entity implement Persistable nhưng isNew() trả false.

Quy trình kiểm tra:

1. Xem giá trị ID ngay trước save.
2. Kiểm tra annotation ID có đúng package Spring Data không.
3. Kiểm tra entity có implement Persistable không.
4. Nếu có @Version, kiểm tra version null/0 hay đã có giá trị.
5. Bật SQL logging để xem INSERT hay UPDATE thực tế.
6. Kiểm tra hàng có tồn tại trong database không.
7. Nếu ID được gán trước, chọn Persistable, @Version hoặc template.insert() phù hợp.
8. Không dùng save cho một thao tác đã biết chắc cần INSERT nếu entity state detection không thể biểu diễn đúng trạng thái.

Ví dụ chẩn đoán:

~~~java
log.debug(
        "Saving product: id={}, version={}, isNew={}",
        product.id(),
        product.version(),
        product.isNew()
);
~~~

Nếu entity không implement Persistable hoặc không có version, bỏ phần gọi isNew() và chỉ log các field có thật.

## 12. Chẩn đoán save chạy INSERT thay vì UPDATE

Triệu chứng:

- Lưu entity đã tồn tại nhưng bị duplicate primary key.
- Unique constraint violation.
- Một aggregate có ID nhưng version null.
- Persistable luôn trả true.
- Entity được dựng lại thủ công mà không giữ ID/version.

Kiểm tra:

1. ID có đúng với bản ghi đang cập nhật không?
2. Version có phải version hiện tại không?
3. Persistable.isNew() có trả false cho aggregate đã lưu không?
4. Có vô tình tạo object mới với ID cũ nhưng trạng thái new không?
5. Có dùng insert() thay cho update()/save() không?
6. Aggregate root có bị mất ID khi chuyển qua DTO hoặc mapper không?

Không giải quyết lỗi duplicate key bằng cách xóa constraint. Constraint đang bảo vệ tính duy nhất; cần sửa trạng thái entity và luồng save.

## 13. Chẩn đoán generated key không được trả về

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| ID null sau save | Object ban đầu immutable và không dùng giá trị trả về | Gán kết quả save vào biến mới |
| INSERT không có ID nhưng database không sinh | Cột thiếu identity/auto-increment/default | Kiểm tra DDL |
| Spring không nhận ID property | Dùng nhầm JPA @Id hoặc thiếu Spring Data @Id | Kiểm tra import |
| Sequence không chạy | Sequence chưa tồn tại hoặc dialect không hỗ trợ | Kiểm tra @Sequence và database |
| MySQL không lấy sequence | MySQL không hỗ trợ sequence | Dùng AUTO_INCREMENT |
| Custom SQL insert không trả key | SQL tự viết không dùng generated-key handling của repository | Dùng KeyHolder hoặc template |
| Test H2 pass, production fail | Schema, dialect hoặc driver khác nhau | Chạy integration test trên database production |
| ID trả về nhưng không reload được | ID map sai kiểu hoặc schema/table mapping không khớp | Kiểm tra giá trị ID và query trực tiếp |

### 13.1. Kiểm tra generated key qua JDBC metadata

Có thể kiểm tra thông tin cột bằng DatabaseMetaData:

~~~java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    try (ResultSet columns = metadata.getColumns(
            null,
            null,
            "products",
            "id"
    )) {
        while (columns.next()) {
            System.out.println(
                    "Column: " + columns.getString("COLUMN_NAME")
            );
            System.out.println(
                    "Auto increment: "
                            + columns.getString("IS_AUTOINCREMENT")
            );
        }
    }
}
~~~

Metadata do driver cung cấp có thể khác nhau giữa database. Dùng cách này để chẩn đoán, đồng thời kiểm tra DDL thật bằng công cụ của database.

### 13.2. Nếu tự viết JDBC INSERT

Nếu không dùng repository/template mà thực hiện INSERT bằng JdbcTemplate, hãy yêu cầu generated key một cách tường minh bằng KeyHolder:

~~~java
KeyHolder keyHolder = new GeneratedKeyHolder();

jdbc.update(connection -> {
    PreparedStatement statement = connection.prepareStatement(
            "INSERT INTO products(name, price) VALUES (?, ?)",
            Statement.RETURN_GENERATED_KEYS
    );

    statement.setString(1, "Keyboard");
    statement.setBigDecimal(2, new BigDecimal("120.00"));

    return statement;
}, keyHolder);

Number generatedKey = keyHolder.getKey();
~~~

Cách này dành cho đường JDBC tự viết. Nếu đã dùng Spring Data JDBC repository, hãy để mapping và dialect quản lý generated key theo cấu hình chuẩn.

## 14. Kiểm thử INSERT, UPDATE và generated key

Một integration test cơ bản nên kiểm tra toàn bộ vòng đời:

~~~java
@SpringBootTest
class ProductPersistenceTest {

    @Autowired
    ProductRepository repository;

    @Test
    void insertsThenUpdatesProduct() {
        Product created = repository.save(
                new Product(
                        null,
                        "Keyboard",
                        new BigDecimal("100.00")
                )
        );

        assertNotNull(created.id());
        assertTrue(repository.existsById(created.id()));

        Product updated = repository.save(
                new Product(
                        created.id(),
                        "Mechanical Keyboard",
                        new BigDecimal("120.00")
                )
        );

        assertEquals(created.id(), updated.id());

        Product loaded = repository.findById(created.id())
                .orElseThrow();

        assertEquals("Mechanical Keyboard", loaded.name());
        assertEquals(
                new BigDecimal("120.00"),
                loaded.price()
        );
    }
}
~~~

Test này cần schema được tạo bằng migration thực tế hoặc DDL tương ứng. Nếu dùng record, luôn lấy object trả về từ save để giữ generated ID.

### 14.1. Kiểm thử ID do ứng dụng cấp

Nếu dùng UUID:

1. Tạo entity với UUID trước khi save.
2. Đánh dấu entity mới bằng Persistable hoặc @Version phù hợp.
3. Save và xác nhận INSERT.
4. Xác nhận ID giữ nguyên.
5. Đánh dấu entity đã lưu.
6. Save lần nữa và xác nhận UPDATE thay vì INSERT.
7. Kiểm tra database chỉ có một hàng cho ID đó.

### 14.2. Kiểm thử sequence

Với database hỗ trợ sequence:

1. Tạo sequence trong migration.
2. Mapping ID bằng @Id và @Sequence.
3. Save aggregate mới.
4. Xác nhận ID được cấp từ sequence.
5. Reload bằng ID.
6. Kiểm tra sequence permission của database user.
7. Xác nhận cả sequence fetch và INSERT chạy trong transaction phù hợp.

### 14.3. Chạy trên database thật

H2 có thể dùng cho phản hồi nhanh, nhưng generated key behavior cần được kiểm tra trên database production target.

Dùng Testcontainers với đúng server/driver:

- PostgreSQL với PostgreSQL JDBC driver.
- MySQL với MySQL Connector/J.
- H2 cho smoke test và mapping cơ bản.

Pin phiên bản server gần production. Một bài test chỉ chạy trên H2 không đủ chứng minh generated key được trả đúng trên PostgreSQL hoặc MySQL.

## 15. Các lỗi thường gặp

**“save luôn chạy INSERT.”** Không. Spring Data JDBC kiểm tra trạng thái aggregate rồi chọn INSERT hoặc UPDATE.

**“Có ID nghĩa là entity chắc chắn tồn tại.”** Không. ID có thể do ứng dụng cấp trước khi insert; cần biểu diễn trạng thái new đúng cách.

**“ID null luôn là cách duy nhất để nhận diện entity mới.”** Không. @Version và Persistable cũng có thể tham gia entity state detection.

**“Dùng JPA @GeneratedValue để Spring Data JDBC sinh ID.”** Không. Spring Data JDBC dùng @Id của Spring Data và cơ chế identity/sequence do dialect hỗ trợ.

**“UUID đã gán trước thì save tự hiểu cần INSERT.”** Không. Với ID khác null và không có version/Persistable, mặc định entity có thể bị xem là đã tồn tại.

**“BeforeConvertCallback có thể đổi quyết định UPDATE thành INSERT.”** Không. Quyết định new/existing diễn ra trước callback; callback phù hợp để gán ID cho entity đã được nhận diện là mới.

**“BeforeSaveCallback là nơi tạo ID.”** Không nên. Kế hoạch persistence đã được tạo; dùng BeforeConvertCallback cho việc cấp ID.

**“Persistable.isNew() có thể luôn trả true.”** Không. Sau insert phải chuyển trạng thái sang not-new, nếu không lần save sau lại INSERT.

**“Persistable.isNew() có thể luôn trả false.”** Không. Entity mới sẽ đi theo UPDATE và không tìm thấy hàng tương ứng.

**“Không cần giữ giá trị trả về của save.”** Không đúng với immutable aggregate. Generated ID và version có thể nằm trong instance mới được trả về.

**“Database đã insert thành công thì JDBC chắc chắn trả generated key.”** Không phải mọi đường SQL/driver/schema đều giống nhau. Cần kiểm tra identity, dialect, driver và generated-key support.

**“@Sequence dùng được trên mọi database.”** Không. Chỉ các dialect có hỗ trợ sequence mới dùng được; MySQL không hỗ trợ sequence theo cơ chế này.

**“insert() giống save().”** Không. insert() bỏ qua entity state detection và luôn INSERT. update() luôn UPDATE. Chỉ dùng khi caller biết chắc trạng thái.

**“upsert giải quyết mọi vấn đề save.”** Không. Upsert cần ID đã có, chỉ hoạt động khi dialect hỗ trợ và hiện không hỗ trợ optimistic locking.

**“Không lấy được ID thì nên tự query MAX(id).”** Không. MAX(id) có race condition khi nhiều transaction insert đồng thời. Dùng generated key hoặc sequence đúng cơ chế.

## 16. Quy trình xử lý lỗi save và generated key

Khi save chạy sai INSERT/UPDATE hoặc không trả ID, hãy kiểm tra theo thứ tự:

1. **Xác nhận mapping:** field primary key dùng Spring Data @Id và tên bảng/cột đúng.
2. **Kiểm tra trạng thái entity:** ID null/0, version null/0 hoặc Persistable.isNew().
3. **Xác định ID được cấp ở đâu:** database identity, sequence, UUID trong ứng dụng hay hệ thống ngoài.
4. **Chọn đúng chiến lược new detection:** mặc định, @Version hoặc Persistable.
5. **Kiểm tra callback:** nếu gán ID bằng callback, dùng BeforeConvertCallback và nhớ quyết định new/existing đã xảy ra trước đó.
6. **Kiểm tra schema:** identity/auto-increment/default/sequence tồn tại và đúng kiểu.
7. **Kiểm tra dialect/driver:** JDBC metadata nhận đúng database, driver hỗ trợ generated key.
8. **Xem SQL thực tế:** xác nhận save đang phát INSERT hay UPDATE.
9. **Giữ instance trả về:** lấy ID/version từ object do save trả về.
10. **Kiểm tra database:** query trực tiếp theo ID, không chỉ nhìn object Java.
11. **Kiểm thử insert rồi update:** xác nhận cùng một aggregate đi đúng hai nhánh.
12. **Chạy integration test trên database production:** pin server và JDBC driver gần môi trường thật.

~~~mermaid
flowchart TD
    A["Gọi save(aggregate)"] --> B{"Entity được xem là mới?"}
    B -->|Có| C["INSERT"]
    B -->|Không| D["UPDATE"]
    C --> E{"Database sinh ID?"}
    E -->|Có| F["Đọc generated key và trả saved instance"]
    E -->|Không| G["Kiểm tra ID app/sequence/callback"]
    D --> H{"Có hàng được cập nhật?"}
    H -->|Có| I["Trả saved instance"]
    H -->|Không| J["Kiểm tra ID, isNew, version và row tồn tại"]
    F --> K["Dùng instance trả về"]
    G --> K
    I --> K
    J --> L["Sửa entity state hoặc mapping"]
~~~

## 17. Bài tập thực hành

Tạo aggregate Product có id, name, price và repository tương ứng.

### Bài 1: Quan sát INSERT và UPDATE

1. Tạo Product với ID null.
2. Save và bật SQL logging.
3. Xác nhận câu INSERT được thực thi.
4. Lấy ID từ instance trả về.
5. Đọc lại aggregate.
6. Thay đổi tên và save.
7. Xác nhận UPDATE được thực thi.

### Bài 2: Mô phỏng save chọn sai UPDATE

1. Tạo Product mới với UUID được cấp trước.
2. Không implement Persistable hoặc @Version.
3. Gọi save.
4. Quan sát Spring xem entity là existing.
5. Xác nhận update không tác động đến hàng nào.
6. Thử lại với Persistable.isNew() trả true.

### Bài 3: Kiểm tra Persistable state

1. Tạo entity có UUID và cờ newEntity=true.
2. Implement Persistable.
3. Đăng ký AfterSaveCallback để chuyển cờ sang false.
4. Save lần đầu.
5. Save lần thứ hai sau khi sửa tên.
6. Xác nhận lần đầu INSERT và lần hai UPDATE.

### Bài 4: Kiểm tra generated key

1. Tạo bảng có identity/auto-increment.
2. Mapping ID bằng Spring Data @Id.
3. Save entity có ID null.
4. Xác nhận ID được trả về.
5. Reload bằng ID.
6. Thử với immutable record và xác nhận phải dùng instance trả về.

### Bài 5: Kiểm tra sequence

1. Tạo sequence trên PostgreSQL hoặc H2.
2. Mapping @Id cùng @Sequence.
3. Save aggregate.
4. Kiểm tra sequence value được lấy trước INSERT.
5. Xác nhận ID và dữ liệu sau save.
6. Thử trên MySQL và giải thích vì sao cần dùng AUTO_INCREMENT thay cho @Sequence.

### Bài 6: Kiểm tra trên database production target

1. Chạy test identity trên H2.
2. Chạy cùng test trên PostgreSQL Testcontainer hoặc MySQL Testcontainer.
3. So sánh ID trả về và SQL được thực thi.
4. Kiểm tra JDBC driver version.
5. Thử migration từ schema cũ sang schema mới.
6. Ghi regression test cho lỗi đã phát hiện.

## 18. Ghi nhớ

- Spring Data JDBC quyết định INSERT hay UPDATE dựa trên entity state detection trước khi tạo SQL.
- Mặc định, ID null hoặc 0 với primitive biểu thị entity mới.
- Nếu có @Version, null hoặc 0 với primitive biểu thị entity mới; version khác biểu thị entity đã tồn tại.
- Implement Persistable để tự định nghĩa isNew() khi ID do ứng dụng hoặc hệ thống ngoài cấp.
- Persistable phải chuyển trạng thái sang not-new sau khi lưu thành công.
- @Id phải là annotation org.springframework.data.annotation.Id, không phải JPA @Id.
- BeforeConvertCallback phù hợp để cấp ID cho aggregate đã được nhận diện là mới; callback không đổi quyết định INSERT/UPDATE đã xảy ra trước đó.
- JdbcAggregateTemplate.insert() luôn INSERT; update() luôn UPDATE; save() dùng entity state detection.
- upsert() yêu cầu ID đã được gán, phụ thuộc dialect và hiện không hỗ trợ optimistic locking.
- Với identity/auto-increment, database sinh key và Spring Data JDBC đưa key vào instance trả về.
- Luôn giữ instance trả về từ save, nhất là với record hoặc immutable aggregate.
- @Sequence chỉ hoạt động trên dialect hỗ trợ sequence; MySQL dùng AUTO_INCREMENT.
- Khi không lấy được generated key, kiểm tra mapping @Id, DDL, dialect, JDBC driver và đường SQL thực tế.
- Kiểm thử cả INSERT lẫn UPDATE trên database production target, không chỉ H2.

**save chỉ chọn đúng INSERT/UPDATE khi trạng thái entity phản ánh đúng vòng đời của aggregate.** Hãy kiểm tra ID, version và isNew trước khi sửa schema. Với generated key, xác nhận database thực sự sinh ID và luôn dùng instance trả về từ save. Cách này giúp tránh duplicate insert, update không có hàng, và lỗi mất generated key khi làm việc với Spring Data JDBC.

## Tài liệu tham khảo

- [Spring Data Relational 4.1.2 — Persisting Entities and ID Generation](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html)
- [Spring Data Commons 4.1.2 — Entity State Detection](https://docs.spring.io/spring-data/relational/reference/data-commons/is-new-state-detection.html)
- [Spring Data Relational 4.1.2 — Sequence Support](https://docs.spring.io/spring-data/relational/reference/jdbc/sequences.html)
- [Spring Data Relational 4.1.2 — JdbcAggregateOperations API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateOperations.html)
- [Spring Data Commons 4.1.2 — Persistable API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/Persistable.html)
- [Spring Data Relational 4.1.2 — AfterSaveCallback API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/AfterSaveCallback.html)

