# Thuộc tính tính toán, trường do cơ sở dữ liệu sinh và rủi ro đồng bộ

Trong một entity JPA, không phải mọi giá trị đều được nhập trực tiếp từ người dùng hoặc lưu như một cột thông thường. Có giá trị được tính từ các field Java, có giá trị được Hibernate tính bằng biểu thức SQL khi đọc, và có giá trị do database tạo bằng DEFAULT, generated column hoặc trigger.

Các cơ chế này khác nhau về nơi tính toán, khả năng ghi, tính portable và thời điểm đồng bộ với object đang nằm trong persistence context. Chọn sai cơ chế có thể khiến entity hiển thị dữ liệu cũ, database và Java object lệch nhau, hoặc cùng một giá trị bị tính ở nhiều nơi với kết quả khác nhau.

Bài học này phân biệt thuộc tính Java dẫn xuất, @Transient, Hibernate @Formula, database default, @Generated, @GeneratedColumn và trigger; giải thích flush/refresh/clear, first-level và second-level cache, bulk update, transaction, migration, kiểm thử và các rủi ro khi có nhiều đường ghi dữ liệu.

## 1. Bốn nơi có thể tạo ra một giá trị

Giả sử OrderLine có quantity và unitPrice. Ứng dụng cần lineTotal = quantity × unitPrice.

Có nhiều cách triển khai:

1. Tính trực tiếp bằng Java khi getter được gọi.
2. Dùng Hibernate @Formula để tính từ biểu thức SQL khi entity được đọc.
3. Khai báo một generated column trong database để database tự tính khi dữ liệu nguồn thay đổi.
4. Lưu lineTotal như một cột thông thường và để service cập nhật cùng quantity/unitPrice.

Không có cách nào luôn tốt nhất. Quyết định phụ thuộc vào việc giá trị có cần lưu vật lý, có cần truy vấn/sắp xếp trong database, có cần chia sẻ công thức với các hệ thống khác và có yêu cầu audit hay không.

| Cách | Nơi tính | Có cột vật lý? | Ai sở hữu giá trị? |
|---|---|---|---|
| Java getter | JVM | Không | Ứng dụng |
| @Transient field/property | JVM | Không | Ứng dụng |
| Hibernate @Formula | Database khi SELECT | Không có cột lưu kết quả | Hibernate mapping + SQL expression |
| Database DEFAULT | Database khi INSERT bị bỏ cột | Có | Database |
| Generated column | Database theo biểu thức | Có cột generated | Database |
| Trigger + @Generated | Database khi INSERT/UPDATE | Có cột | Database |
| Cột dẫn xuất được service ghi | Ứng dụng | Có | Ứng dụng |

## 2. Thuộc tính tính toán bằng Java

Nếu giá trị chỉ cần để hiển thị hoặc phục vụ logic trong ứng dụng, getter tính toán thường là cách đơn giản nhất:

~~~java
@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "unit_price", nullable = false, precision = 12, scale = 2)
    private BigDecimal unitPrice;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {
    }

    public BigDecimal getJavaTotal() {
        if (unitPrice == null) {
            return null;
        }

        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
~~~

Với field access như ví dụ trên, getter không có backing persistent field nên không tạo cột trong database. Mỗi lần gọi getJavaTotal(), Java tính lại từ trạng thái hiện tại của object.

Ưu điểm:

- Kết quả phản ánh ngay các thay đổi chưa flush trong object.
- Không cần truy vấn database để tính.
- Không có cột dẫn xuất cần đồng bộ.
- Dễ kiểm thử bằng unit test.

Giới hạn:

- Không thể dùng getter này trực tiếp làm property trong JPQL hoặc SQL.
- Database không thể sắp xếp, lọc hoặc index theo kết quả Java getter.
- Nếu cùng phép tính được thực hiện ở nhiều service, UI hoặc batch job, quy tắc có thể bị nhân bản.
- Cần thống nhất xử lý null, scale, rounding và overflow.

Nếu API cần một trường tính toán cho response, DTO projection hoặc mapper có thể phù hợp hơn việc thêm một thuộc tính persistent vào entity.

## 3. @Transient cho thuộc tính không lưu

Jakarta Persistence cung cấp @Transient để đánh dấu field/property không được ánh xạ thành cột.

Ví dụ một field chỉ phục vụ hiển thị:

~~~java
@Entity
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    private BigDecimal price;

    private int quantity;

    @Transient
    private String displayLabel;

    public String getDisplayLabel() {
        return quantity + " x " + price;
    }
}
~~~

@Transient không có nghĩa database tự tính. Nó chỉ nói với JPA rằng thuộc tính này không thuộc persistent state.

Vị trí annotation cần phù hợp access strategy:

- Field access: đặt @Transient trên field.
- Property access: đặt @Transient trên getter.

Nếu dùng @PostLoad để tính một field transient sau khi entity được tải, hãy nhớ callback chỉ chạy tại thời điểm load. Khi quantity hoặc price thay đổi sau đó, field đã tính không tự cập nhật trừ khi ứng dụng tính lại.

## 4. Khi nào nên dùng getter thay vì @Formula?

Dùng Java getter khi:

- Giá trị chỉ cần trong Java và phải phản ánh ngay thay đổi trong object.
- Không cần database filter/order theo giá trị đó.
- Không cần chia sẻ công thức với các ứng dụng khác.
- Công thức nhỏ và chi phí tính toán thấp.

Dùng @Formula hoặc generated column khi database phải tham gia tính toán, ví dụ query cần lọc theo kết quả, nhiều client cùng đọc dữ liệu hoặc công thức cần chạy thống nhất ở database.

Nếu chỉ cần một phép tính trong một truy vấn, có thể dùng JPQL projection thay vì thêm thuộc tính vào entity:

~~~java
public record LineTotalView(
    Long id,
    BigDecimal total
) {
}

@Query("""
    select new example.dto.LineTotalView(
        line.id,
        line.unitPrice * line.quantity
    )
    from OrderLine line
    where line.id = :id
    """)
Optional<LineTotalView> findTotal(@Param("id") Long id);
~~~

Projection chỉ tính giá trị cho truy vấn đó, không tạo cột mới và không làm entity managed mang thêm trạng thái dẫn xuất.

## 5. Hibernate @Formula là gì?

@Formula là annotation riêng của Hibernate để ánh xạ một biểu thức SQL thành thuộc tính chỉ đọc của entity.

Ví dụ:

~~~java
@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "unit_price", nullable = false)
    private BigDecimal unitPrice;

    @Column(nullable = false)
    private int quantity;

    @Formula("quantity * unit_price")
    private BigDecimal formulaTotal;
}
~~~

Khi Hibernate tải OrderLine, biểu thức quantity * unit_price được đưa vào SELECT để tính formulaTotal.

@Formula:

- Không tạo cột lưu kết quả.
- Không cho Hibernate ghi giá trị formulaTotal vào database.
- Dùng native SQL fragment, không phải JPQL expression.
- Là tính năng Hibernate-specific, không thuộc Jakarta Persistence.
- Có thể ảnh hưởng khả năng chuyển database nếu biểu thức dùng hàm hoặc cú pháp riêng.

Tên cột trong formula là tên cột database, không nhất thiết là tên property Java. Nếu mapping dùng @Column(name = "unit_price"), formula phải tham chiếu đúng unit_price.

## 6. @Formula không tự tính lại trong object đang managed

Một điểm dễ gây lỗi là formula được tính khi Hibernate đọc entity từ database. Nó không phải getter Java chạy lại mỗi lần truy cập.

Ví dụ:

~~~java
OrderLine line = entityManager.find(OrderLine.class, id);

BigDecimal before = line.getFormulaTotal();

line.setQuantity(5);
entityManager.flush();

BigDecimal stillInMemory = line.getFormulaTotal();
~~~

Sau khi quantity thay đổi trong object và Hibernate flush UPDATE, giá trị formulaTotal trong object có thể vẫn là kết quả của lần SELECT trước. Việc flush ghi field nguồn không tự đảm bảo Hibernate đọc lại formula trong mọi trường hợp.

Nếu cần giá trị mới, hãy refresh entity hoặc tải lại trong persistence context phù hợp:

~~~java
entityManager.flush();
entityManager.refresh(line);

BigDecimal refreshed = line.getFormulaTotal();
~~~

refresh đọc lại trạng thái database và ghi đè trạng thái hiện tại của entity. Chỉ gọi sau khi các thay đổi cần giữ đã được flush; nếu còn thay đổi chưa flush, refresh có thể làm mất chúng.

## 7. @Formula có thể phức tạp nhưng cần kiểm soát SQL

Hibernate cho phép formula là biểu thức SQL phức tạp, thậm chí có thể chứa subquery. Điều này hữu ích cho một số giá trị dẫn xuất từ bảng liên quan.

Tuy nhiên, formula phức tạp có thể:

- Tạo subquery lặp lại cho từng entity trong kết quả.
- Làm SELECT dài và khó tối ưu.
- Dùng hàm không portable giữa database.
- Gây khó khăn khi query filter/sort theo formula.
- Tăng chi phí khi entity được tải hàng loạt.

Không nên biến entity thành nơi chứa hàng chục formula để thay thế reporting query. Với báo cáo lớn, cân nhắc DTO projection, view, materialized view hoặc truy vấn tổng hợp riêng.

## 8. Database DEFAULT là gì?

DEFAULT là giá trị database dùng khi một INSERT không cung cấp giá trị cho cột.

Ví dụ DDL:

~~~sql
CREATE TABLE task (
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    status VARCHAR(30) DEFAULT 'PENDING'
);
~~~

Nếu INSERT bỏ cột status, database dùng PENDING. Nếu INSERT truyền một giá trị cụ thể, giá trị được truyền sẽ được dùng.

Trong SQL thông thường, truyền NULL tường minh không giống bỏ cột. DEFAULT không tự thay NULL bằng giá trị mặc định trừ khi database có cú pháp riêng như DEFAULT ON NULL.

Điểm này quan trọng với Hibernate: INSERT mặc định có thể đưa cột vào câu lệnh ngay cả khi Java field đang null. Khi đó database nhận NULL thay vì áp dụng DEFAULT.

## 9. @ColumnDefault và @DynamicInsert

Hibernate cung cấp @ColumnDefault để khai báo default expression trong DDL do Hibernate sinh:

~~~java
@Entity
@DynamicInsert
public class Task {

    @Id
    @GeneratedValue
    private Long id;

    private String title;

    @ColumnDefault("'PENDING'")
    private String status;
}
~~~

@DynamicInsert yêu cầu Hibernate tạo INSERT dựa trên các field có giá trị. Nếu status là null, cột status được bỏ khỏi INSERT, để database áp dụng DEFAULT.

Cần phân biệt:

- @ColumnDefault mô tả default trong DDL.
- @DynamicInsert quyết định bỏ cột null khỏi INSERT.
- @ColumnDefault không tự buộc Hibernate bỏ cột khỏi INSERT.
- @ColumnDefault không tự đọc giá trị database trả về vào object.

Nếu schema do Flyway/Liquibase quản lý, migration phải thực sự khai báo DEFAULT. Annotation không tự sửa schema production khi Hibernate chạy ở chế độ validate hoặc none.

## 10. Database default có thể khiến entity và database lệch nhau

Với ví dụ Task ở trên:

~~~java
Task task = new Task();
task.setTitle("Prepare report");

entityManager.persist(task);
entityManager.flush();
~~~

Nếu status null và @DynamicInsert bỏ cột status, database có thể lưu PENDING. Nhưng field task.status trong object Java vẫn có thể null vì Hibernate không tự đọc lại giá trị default nếu field không được đánh dấu generated.

Có thể đồng bộ bằng refresh:

~~~java
entityManager.refresh(task);
assertEquals("PENDING", task.getStatus());
~~~

Nếu database luôn sở hữu giá trị này, có thể ánh xạ rõ bằng @Generated như phần sau để Hibernate tự lấy giá trị sau INSERT.

## 11. Hibernate @Generated cho giá trị do database tạo

@Generated là annotation Hibernate dùng khi giá trị của thuộc tính được database tạo hoặc thay đổi trong INSERT/UPDATE.

Các tình huống thường gặp:

- Cột có DEFAULT trong DDL.
- Trigger điền hoặc sửa giá trị.
- SQL expression trong INSERT/UPDATE tạo giá trị.
- Database chuẩn hóa dữ liệu khi ghi.

Ví dụ cột status luôn do database cấp default:

~~~java
@Entity
public class Task {

    @Id
    @GeneratedValue
    private Long id;

    private String title;

    @Generated(event = EventType.INSERT)
    @ColumnDefault("'PENDING'")
    @Column(insertable = false, updatable = false)
    private String status;
}
~~~

Khi Hibernate INSERT Task, cột status không được đưa vào câu lệnh. Database áp dụng default; Hibernate biết status được sinh ở INSERT và lấy giá trị mới để đồng bộ entity.

Với field do database hoàn toàn sở hữu, insertable=false và updatable=false giúp Hibernate không ghi đè giá trị.

## 12. Chọn thời điểm @Generated

@Generated có thể khai báo các event tạo giá trị:

~~~java
@Generated(event = EventType.INSERT)
private String createdCode;
~~~

Chỉ đọc lại giá trị sau INSERT.

~~~java
@Generated(event = EventType.UPDATE)
private String recalculatedValue;
~~~

Đọc lại sau UPDATE.

~~~java
@Generated(event = {EventType.INSERT, EventType.UPDATE})
private String normalizedCode;
~~~

Đọc lại sau cả INSERT và UPDATE.

EventType thuộc Hibernate, package org.hibernate.generator. Nếu không chỉ định event, @Generated mặc định theo INSERT.

Hibernate có thể dùng SQL RETURNING hoặc cơ chế SELECT bổ sung tùy dialect và JDBC driver. Vì vậy, số câu SQL phát sinh phụ thuộc database/provider.

## 13. Trigger-generated value và @Generated

Trigger thường được dùng khi database phải chuẩn hóa dữ liệu hoặc áp dụng quy tắc chung cho mọi client ghi vào bảng.

Ví dụ PostgreSQL trigger chuẩn hóa mã sản phẩm:

~~~sql
CREATE OR REPLACE FUNCTION normalize_product_code()
RETURNS trigger AS $$
BEGIN
    NEW.normalized_code := upper(trim(NEW.code));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_product_normalize_code
BEFORE INSERT OR UPDATE OF code ON product
FOR EACH ROW
EXECUTE FUNCTION normalize_product_code();
~~~

Entity mapping:

~~~java
@Entity
@Table(name = "product")
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    private String code;

    @Generated(event = {EventType.INSERT, EventType.UPDATE})
    @Column(name = "normalized_code",
            insertable = false,
            updatable = false)
    private String normalizedCode;
}
~~~

Khi Hibernate thực hiện INSERT hoặc UPDATE, trigger cập nhật normalized_code. @Generated yêu cầu Hibernate đọc lại giá trị sau thao tác đó.

Nếu trigger chỉ chạy khi INSERT, dùng EventType.INSERT. Nếu trigger chạy khi INSERT và UPDATE, khai báo cả hai event.

Ví dụ SQL trigger ở trên dành cho PostgreSQL. MySQL, SQL Server, Oracle và các database khác có cú pháp trigger riêng.

## 14. Generated column trong database

Generated column là cột có giá trị được database tính từ biểu thức dựa trên các cột khác.

Ví dụ DDL theo cú pháp PostgreSQL:

~~~sql
CREATE TABLE order_line (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    line_total NUMERIC(14, 2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED
);
~~~

Database tự tính line_total khi INSERT hoặc khi quantity/unit_price thay đổi.

Tùy database, generated column có thể là VIRTUAL hoặc STORED:

- VIRTUAL: database tính giá trị khi đọc theo cơ chế của engine.
- STORED: database lưu kết quả đã tính tại thời điểm ghi.

Khả năng hỗ trợ, cú pháp và giới hạn biểu thức khác nhau theo database. Một số engine hạn chế hàm không deterministic, subquery hoặc tham chiếu cột khác bảng.

## 15. Hibernate @GeneratedColumn

Hibernate có @GeneratedColumn để ánh xạ cột DDL generated always as:

~~~java
@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @GeneratedValue
    private Long id;

    private int quantity;

    @Column(name = "unit_price", precision = 12, scale = 2)
    private BigDecimal unitPrice;

    @GeneratedColumn("quantity * unit_price")
    @Column(name = "line_total",
            insertable = false,
            updatable = false)
    private BigDecimal lineTotal;
}
~~~

@GeneratedColumn khai báo biểu thức generated-column trong DDL và yêu cầu Hibernate lấy giá trị sau INSERT/UPDATE.

Annotation này thuộc Hibernate, không thuộc Jakarta Persistence. Nó có từ Hibernate ORM 6.0. Cần kiểm tra dialect có hỗ trợ generated column expression tương ứng và migration production có cùng định nghĩa hay không.

Nếu database schema được tạo bởi Flyway/Liquibase, migration phải khai báo generated column. Không giả định annotation tự thay đổi schema production.

## 16. @Generated khác @GeneratedColumn thế nào?

Hai annotation đều giúp Hibernate biết giá trị đến từ database, nhưng mục đích khác nhau:

| Cơ chế | Dùng cho |
|---|---|
| @Generated | Giá trị được tạo bởi DEFAULT, trigger hoặc SQL ghi dữ liệu |
| @GeneratedColumn | Cột được định nghĩa bằng DDL generated always as |
| @Formula | Biểu thức SQL đọc-only, không có cột lưu kết quả |
| @ColumnDefault | Khai báo default expression cho DDL |
| @CreationTimestamp/@UpdateTimestamp | Timestamp do Hibernate tạo theo chiến lược của annotation |
| @Transient | Thuộc tính Java không được lưu |

Không dùng @GeneratedColumn chỉ vì database có trigger. Trigger-generated value thường phù hợp với @Generated. Không dùng @Generated thay cho @GeneratedValue đối với identifier identity/autoincrement; identifier vẫn dùng @GeneratedValue theo mapping JPA.

## 17. @CreationTimestamp, @UpdateTimestamp và @CurrentTimestamp

Hibernate có các annotation tạo timestamp, nhưng nguồn thời gian khác nhau.

Trong Hibernate ORM 6.6:

- @CreationTimestamp tạo timestamp khi entity được tạo, mặc định dùng thời gian JVM.
- @UpdateTimestamp tạo timestamp khi entity được tạo/cập nhật, mặc định dùng thời gian JVM.
- @CurrentTimestamp dùng database current_timestamp theo chiến lược in-DB.

Ví dụ:

~~~java
@Entity
public class AuditRecord {

    @Id
    @GeneratedValue
    private Long id;

    @CreationTimestamp
    private Instant createdAt;

    @UpdateTimestamp
    private Instant updatedAt;

    @CurrentTimestamp(event = EventType.INSERT)
    private Instant databaseCreatedAt;
}
~~~

Nếu nhiều application server có clock lệch nhau, timestamp từ JVM có thể không đồng nhất. Nếu cần thời gian theo database, dùng chiến lược DB phù hợp và kiểm tra precision/time zone.

Đừng coi các annotation timestamp này là thay thế hoàn toàn auditing nghiệp vụ. Chúng không tự ghi người thực hiện, request ID hoặc lý do thay đổi.

## 18. @ColumnTransformer không phải generated property

@ColumnTransformer cho phép Hibernate dùng SQL expression để đọc/ghi một giá trị được lưu ở một hoặc nhiều cột.

Ví dụ lưu số tiền theo đơn vị cent nhưng ứng dụng làm việc với đơn vị tiền tệ:

~~~java
@Column(name = "amount_cents")
@ColumnTransformer(
    read = "amount_cents / 100.0",
    write = "? * 100"
)
private BigDecimal amount;
~~~

Khác biệt:

- @Formula là thuộc tính read-only được tính từ SQL.
- @ColumnTransformer vẫn ánh xạ một hoặc nhiều cột và có thể read/write.
- @Generated dùng khi database tạo giá trị và Hibernate cần đọc lại.
- @GeneratedColumn dùng cột generated always as.

Nếu read expression không đảo ngược chính xác write expression, trạng thái Java có thể không còn đồng bộ với database. Khi đó cần chiến lược refresh phù hợp hoặc cấu hình generated value theo tài liệu Hibernate.

## 19. Persistence context và first-level cache

EntityManager duy trì persistence context. Khi một entity đã được load, lần find tiếp theo trong cùng persistence context thường trả về cùng managed instance thay vì đọc lại toàn bộ row từ database.

Điều này đảm bảo identity trong một unit of work, nhưng cũng tạo rủi ro stale state:

1. Hibernate tải Product với normalizedCode = ABC.
2. Một trigger, native SQL hoặc ứng dụng khác cập nhật normalizedCode thành XYZ.
3. Product đang managed trong EntityManager vẫn có thể giữ ABC.
4. Gọi findById lại trong cùng persistence context có thể trả chính object cũ.

Database có thể đã đúng nhưng Java object chưa được đồng bộ.

## 20. flush, refresh và clear khác nhau thế nào?

**flush()** đẩy các thay đổi đang chờ trong persistence context xuống database. Flush không đồng nghĩa commit transaction.

**refresh(entity)** đọc lại trạng thái database cho một managed entity và ghi đè trạng thái trong memory.

**clear()** detach tất cả entity khỏi persistence context hiện tại. Lần find sau đó sẽ cần tạo/load instance mới.

Ví dụ:

~~~java
entityManager.flush();

entityManager.refresh(product);

String currentCode = product.getNormalizedCode();
~~~

Chỉ refresh sau khi đã flush các thay đổi cần giữ. refresh có thể ghi đè giá trị Java chưa được lưu.

Nếu chỉ cần tải lại một entity, refresh thường rõ ràng hơn clear toàn bộ context. Nếu vừa chạy bulk operation trên nhiều entity, clear có thể phù hợp hơn.

## 21. @Generated giảm nhu cầu refresh thủ công nhưng không giải quyết mọi đường ghi

Khi Hibernate thực hiện INSERT/UPDATE và field được đánh dấu @Generated, Hibernate tự lấy lại giá trị database sau event tương ứng.

Tuy nhiên, @Generated không tự chạy khi:

- Một ứng dụng khác ghi trực tiếp vào database.
- DBA chạy script SQL.
- JDBC/JdbcTemplate thực hiện UPDATE ngoài entity lifecycle.
- Bulk JPQL mutation bỏ qua entity state synchronization.
- Một job bên ngoài cập nhật bảng sau khi transaction của Hibernate đã kết thúc.

Trong những trường hợp đó, persistence context đang mở vẫn có thể chứa dữ liệu cũ. Cần refresh, clear hoặc kết thúc unit of work trước khi đọc lại.

## 22. Bulk JPQL update/delete và persistence context

Bulk JPQL update/delete thao tác trực tiếp trên database, không tải và cập nhật từng entity instance đang managed.

Ví dụ Spring Data:

~~~java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    update Product p
    set p.code = :code
    where p.id = :id
    """)
int updateCode(
    @Param("id") Long id,
    @Param("code") String code
);
~~~

flushAutomatically đẩy thay đổi pending trước bulk query. clearAutomatically xóa persistence context sau bulk query để tránh tiếp tục dùng entity state cũ.

Nếu không clear hoặc refresh, entity Product đã load trước đó có thể giữ code/normalizedCode cũ dù database đã được trigger cập nhật.

Bulk query cũng không gọi setter, entity callback hoặc dirty checking như thao tác từng entity. Nếu nghiệp vụ phụ thuộc các cơ chế đó, hãy thiết kế riêng.

## 23. Native SQL, JDBC và hệ thống bên ngoài

Khi dùng JdbcTemplate hoặc native SQL trực tiếp:

~~~java
jdbcTemplate.update(
    "update product set code = ? where id = ?",
    newCode,
    productId
);
~~~

Hibernate không tự biết row nào đã đổi nếu câu lệnh đi ngoài cơ chế quản lý entity.

Nếu cùng transaction đang có Product managed:

- Flush trước khi chạy JDBC nếu cần bảo toàn thay đổi Hibernate đang pending.
- Sau khi JDBC update, refresh Product hoặc clear persistence context.
- Nếu có second-level/query cache, cân nhắc evict/invalidate cache liên quan.
- Nếu database trigger cập nhật thêm bảng khác, các entity tương ứng cũng có thể stale.

Với hệ thống ngoài ứng dụng, cần quy ước cache invalidation hoặc giới hạn thời gian sống của cache. @Generated không thay thế giao thức đồng bộ giữa nhiều application.

## 24. Second-level cache và query cache

First-level cache nằm trong persistence context của EntityManager. Second-level cache và query cache có thể tồn tại lâu hơn, dùng chung giữa nhiều session.

Nếu database bị thay đổi ngoài Hibernate, việc refresh một entity trong một EntityManager không nhất thiết làm mọi cache khác tự biết.

Cần đánh giá:

- Entity có bật second-level cache không.
- Query có dùng query cache không.
- Native SQL có khai báo query spaces/synchronized entities để Hibernate biết bảng bị ảnh hưởng không.
- Có cache Spring hoặc Redis ở tầng service không.
- Ai chịu trách nhiệm invalidate cache khi hệ thống ngoài ghi database.

Với dữ liệu thay đổi bởi nhiều hệ thống, cache policy cần được thiết kế như một phần của kiến trúc consistency, không chỉ là một annotation trên entity.

## 25. @Version và cập nhật đồng thời

@Generated giúp đọc lại giá trị do database tạo; nó không giải quyết xung đột khi hai transaction cùng sửa một entity.

JPA @Version hỗ trợ optimistic locking:

~~~java
@Entity
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    private String code;

    @Version
    private long version;
}
~~~

Nếu hai transaction cùng đọc một version rồi cùng cập nhật, transaction ghi sau với version cũ có thể thất bại bằng optimistic locking exception thay vì âm thầm ghi đè thay đổi của transaction kia.

Cần phân biệt:

- @Version phát hiện cập nhật cạnh tranh.
- @Generated/@GeneratedColumn đồng bộ giá trị do database sinh.
- refresh đọc lại trạng thái hiện tại.
- cache invalidation làm mới dữ liệu giữa các persistence context.

Một trigger cập nhật các cột khác không tự thay thế optimistic locking. Nếu database trigger cũng sửa version column, cần thiết kế mapping/provider nhất quán; tránh để Hibernate và trigger cùng tăng version theo hai quy tắc không phối hợp.

## 26. Transaction và giá trị được sinh

Giá trị do database tạo trong transaction chỉ nhìn thấy theo quy tắc transaction/isolation của database.

Các điểm cần nhớ:

- save() có thể chưa phát SQL ngay; Hibernate có thể trì hoãn tới flush.
- saveAndFlush() hoặc entityManager.flush() buộc phát SQL sớm hơn nhưng không commit transaction.
- @Generated đọc lại giá trị sau INSERT/UPDATE của Hibernate.
- Transaction rollback sẽ rollback cả dữ liệu được trigger/generated trong transaction đó.
- Nếu transaction rollback sau khi Java object đã nhận generated value, object trong memory có thể vẫn giữ giá trị đó dù row không được commit. Không tái sử dụng detached object đó như nguồn sự thật.
- Transaction khác thường không nhìn thấy thay đổi chưa commit.

Nếu một trigger gửi tác vụ bất đồng bộ sau commit và giá trị chỉ được cập nhật sau đó, @Generated đọc ngay sau INSERT không thể chờ kết quả tương lai. Dùng polling, outbox/event hoặc trạng thái xử lý riêng cho quy trình bất đồng bộ.

## 27. Nhiều nguồn ghi và nguy cơ lệch công thức

Một lỗi kiến trúc thường gặp là lưu một giá trị dẫn xuất rồi để nhiều nơi tự tính và cập nhật:

- REST service cập nhật lineTotal.
- Batch job cũng cập nhật lineTotal.
- Script import chỉ cập nhật quantity/unitPrice.
- Trigger cập nhật thêm lineTotal.
- Một client cũ không biết cột mới.

Sau một thời gian, lineTotal có thể không còn bằng quantity × unitPrice.

Để giảm rủi ro:

1. Chọn một nguồn sự thật cho công thức.
2. Nếu database là nguồn sự thật, ưu tiên generated column hoặc trigger.
3. Nếu application là nguồn sự thật, tập trung phép tính trong domain/service và bảo đảm mọi đường ghi đều đi qua.
4. Dùng constraint hoặc generated expression nếu database có thể kiểm tra.
5. Khi thêm cột dẫn xuất, backfill dữ liệu cũ trước khi ứng dụng phụ thuộc vào nó.
6. Kiểm thử các đường ghi: Hibernate, bulk SQL, JDBC, import và migration.

Không lưu trùng một giá trị chỉ để tránh một phép nhân nhỏ nếu chưa có lý do hiệu năng rõ ràng.

## 28. Migration và schema drift

Các annotation Hibernate không tự bảo đảm schema production giống schema local.

Ví dụ:

- @ColumnDefault có thể tham gia DDL generation nhưng migration vẫn phải tạo DEFAULT.
- @GeneratedColumn cần generated expression đúng cú pháp database.
- Trigger cần function và trigger DDL.
- @Formula không tạo cột vật lý.
- @Generated chỉ hướng dẫn Hibernate đọc lại giá trị; nó không tự tạo trigger/default.

Với Flyway hoặc Liquibase, migration cần tạo:

- Cột và kiểu dữ liệu.
- DEFAULT/generated expression.
- Trigger/function nếu có.
- Index nếu cần query theo giá trị generated.
- Backfill cho dữ liệu cũ nếu migration thêm cột vật lý mới.

Dùng ddl-auto=validate trong môi trường cần kiểm tra mapping với schema do migration quản lý. Không dựa vào ddl-auto=update để triển khai generated column hoặc trigger phức tạp trong production.

## 29. Backfill và thay đổi công thức

Khi thay đổi công thức từ quantity × unitPrice sang một quy tắc mới có rounding/discount, cần xác định dữ liệu lịch sử sẽ được xử lý thế nào.

Nếu dùng generated column, database thường tính theo biểu thức hiện tại cho dữ liệu đang được đọc/ghi theo semantics của engine. Nếu dùng cột dẫn xuất lưu thủ công, cần migration/backfill để cập nhật mọi row cũ.

Các bước an toàn:

1. Viết migration bổ sung schema/column.
2. Backfill dữ liệu hiện có.
3. Kiểm tra row count và các invariant.
4. Triển khai code đọc theo schema mới.
5. Chuyển write path sang cơ chế mới.
6. Theo dõi sai lệch bằng query kiểm tra.
7. Xóa logic cũ sau khi xác nhận không còn client ghi theo cách cũ.

Nếu công thức liên quan tiền tệ, rounding mode và precision phải được thống nhất giữa Java và database. BigDecimal và DECIMAL/NUMERIC phù hợp hơn floating-point cho tiền tệ.

## 30. Hiệu năng của từng cách

| Cách | Chi phí chính | Cách tối ưu |
|---|---|---|
| Java getter | CPU trong JVM khi gọi | Tính khi cần, tránh tính lặp nếu biểu thức đắt |
| @Formula | SQL expression trong SELECT | Giữ formula đơn giản, xem execution plan |
| Generated virtual column | Database tính theo engine khi đọc | Kiểm tra khả năng index của database |
| Generated stored column | Chi phí tính khi ghi và dung lượng lưu | Index nếu query thường xuyên |
| Trigger | Chi phí trigger mỗi INSERT/UPDATE | Giữ trigger ngắn, kiểm thử lock/recursion |
| Cột dẫn xuất do service ghi | Thêm dữ liệu ghi và consistency logic | Centralize write path, đo lợi ích thật |

Không thể kết luận generated column luôn nhanh hơn @Formula. Stored generated column có thể hữu ích khi giá trị được query thường xuyên và database hỗ trợ index. Formula có thể đủ tốt nếu số lượng hàng nhỏ hoặc expression rẻ.

## 31. Kiểm thử bằng database thật

Các tính năng generated column, trigger và DEFAULT phụ thuộc database dialect. H2 có thể không mô phỏng chính xác PostgreSQL, MySQL, SQL Server hoặc Oracle.

Nên dùng Testcontainers với database production tương ứng cho integration test.

Ví dụ cấu hình PostgreSQL container bằng DynamicPropertySource:

~~~java
@DataJpaTest
@Testcontainers
class OrderLineGeneratedColumnTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void generatedColumnIsReadBackAfterInsert() {
        OrderLine line = new OrderLine(
            3,
            new BigDecimal("12.50")
        );

        entityManager.persist(line);
        entityManager.flush();

        entityManager.refresh(line);

        assertEquals(
            new BigDecimal("37.50"),
            line.getLineTotal()
        );
    }
}
~~~

Test giả định migration tạo generated column line_total và entity có constructor/getter tương ứng. Với Hibernate @GeneratedColumn, Hibernate sẽ lấy giá trị sau INSERT; refresh ở đây làm rõ bước đọc lại khi kiểm tra test và có thể bỏ nếu đã xác minh generated-state được đồng bộ tự động trong phiên bản/provider cụ thể.

## 32. Bộ test đồng bộ cần có

Với entity có thuộc tính do database tạo, nên kiểm thử:

1. INSERT có áp dụng DEFAULT khi cột bị bỏ.
2. INSERT truyền NULL tường minh có hành vi đúng theo DDL.
3. @DynamicInsert chỉ bỏ các field null theo mong muốn.
4. @Generated(event=INSERT) đọc được giá trị trigger/default.
5. @Generated(event=UPDATE) đọc lại giá trị sau trigger update.
6. @GeneratedColumn trả kết quả đúng sau thay đổi cột nguồn.
7. @Formula đúng khi load entity mới.
8. @Formula sau khi sửa field nguồn cần refresh/reload để cập nhật.
9. Bulk JPQL update không để persistence context tiếp tục dùng state cũ.
10. Native SQL/JDBC update có quy trình refresh/clear/cache invalidation.
11. Rollback không để lại dữ liệu generated đã commit.
12. Nhiều transaction cập nhật đồng thời không làm mất dữ liệu.
13. Migration tạo đúng default, generated expression và trigger.
14. Các database version được hỗ trợ cho generated-column syntax.
15. Precision, scale, rounding và timezone thống nhất.
16. @Version phát hiện cập nhật cạnh tranh theo đúng transaction boundary.

Không chỉ kiểm tra giá trị trong object sau save. Hãy đọc lại row bằng query độc lập hoặc EntityManager mới để xác nhận database thật sự lưu đúng.

## 33. Lỗi thường gặp và cách khắc phục

**1. Database có DEFAULT nhưng Java field vẫn null**

Hibernate có thể đã INSERT cột null thay vì bỏ cột. Dùng @DynamicInsert khi cần bỏ null column, hoặc ánh xạ field do DB sở hữu bằng @Generated và insertable=false.

**2. @ColumnDefault không làm database tự áp dụng default**

Kiểm tra DDL thật. @ColumnDefault không tự thay đổi schema production nếu migration chưa tạo DEFAULT.

**3. @Formula không cập nhật sau setter**

Formula được tính khi SELECT. Flush không đảm bảo field trong managed object được tính lại; dùng refresh/reload khi cần.

**4. @Generated không đọc giá trị trigger**

Kiểm tra event INSERT/UPDATE, mapping insertable/updatable, trigger timing, SQL thật và version Hibernate.

**5. Generated column không tạo được trên database**

Kiểm tra dialect và cú pháp generated expression của database. Không phải mọi database hỗ trợ cùng tính năng hoặc cùng loại expression.

**6. Entity hiện tại vẫn chứa dữ liệu cũ sau JDBC update**

Đây là persistence context stale state. Flush trước khi JDBC chạy nếu cần, sau đó refresh entity hoặc clear context.

**7. Bulk update không đồng bộ entity đã load**

Bulk JPQL bỏ qua managed entity instances. Dùng flushAutomatically/clearAutomatically hoặc refresh các entity cần tiếp tục sử dụng.

**8. Second-level cache trả dữ liệu cũ**

Evict/invalidate cache liên quan khi cập nhật ngoài Hibernate. Kiểm tra query cache và cache ở tầng service.

**9. Trigger làm ghi dữ liệu chậm**

Đo thời gian trigger, index, lock và số lần trigger chạy. Giữ logic trigger ngắn và tránh truy vấn lặp lại.

**10. Giá trị Java và database khác nhau do rounding**

Thống nhất BigDecimal scale, rounding mode và kiểu DECIMAL/NUMERIC; không dùng double cho tiền tệ.

**11. Test qua H2 nhưng production lỗi**

Chạy Testcontainers trên cùng database engine/version và dùng migration thực tế.

**12. Nhiều đường ghi tạo giá trị dẫn xuất không nhất quán**

Chọn một nguồn sự thật, dùng generated column/trigger hoặc centralize write path; bổ sung backfill và invariant checks.

## 34. Quy trình chọn cơ chế phù hợp

1. Xác định giá trị chỉ phục vụ Java hay phải query/sort tại database.
2. Nếu chỉ dùng trong Java, dùng getter hoặc @Transient.
3. Nếu cần biểu thức SQL read-only khi load, cân nhắc @Formula.
4. Nếu cần cột database tính từ các cột khác, cân nhắc generated column và @GeneratedColumn.
5. Nếu database tạo giá trị bằng DEFAULT hoặc trigger, dùng @Generated với event phù hợp.
6. Nếu chỉ cần default khi INSERT, bảo đảm cột thực sự bị bỏ khỏi INSERT.
7. Xác định ai là source of truth: Java hay database.
8. Kiểm tra flush/refresh/clear và cache behavior.
9. Kiểm tra bulk JPQL, native SQL, JDBC và hệ thống bên ngoài.
10. Viết migration cho DEFAULT, generated expression và trigger.
11. Kiểm thử trên database production tương ứng.
12. Đo SQL, trigger cost, index và query plan.
13. Định nghĩa quy trình backfill và cache invalidation khi thay đổi công thức.

## 35. Checklist tự đánh giá

- [ ] Tôi phân biệt Java getter với thuộc tính persistent.
- [ ] Tôi biết dùng @Transient theo access strategy.
- [ ] Tôi hiểu @Formula là Hibernate-specific, read-only và dùng SQL.
- [ ] Tôi hiểu formula được tính khi SELECT, không tự cập nhật trong object sau setter.
- [ ] Tôi phân biệt database DEFAULT với generated column.
- [ ] Tôi biết @ColumnDefault chỉ mô tả DDL.
- [ ] Tôi biết @DynamicInsert ảnh hưởng việc bỏ cột null khỏi INSERT.
- [ ] Tôi biết @Generated và EventType.INSERT/UPDATE.
- [ ] Tôi biết khi nào cần insertable=false/updatable=false.
- [ ] Tôi biết @GeneratedColumn cho generated always as.
- [ ] Tôi phân biệt @Generated với @GeneratedColumn.
- [ ] Tôi hiểu trigger có thể làm entity state lệch nếu Hibernate không đọc lại.
- [ ] Tôi biết flush không đồng nghĩa commit.
- [ ] Tôi biết refresh ghi đè trạng thái hiện tại từ database.
- [ ] Tôi biết clear detach toàn bộ entity trong persistence context.
- [ ] Tôi hiểu first-level và second-level cache có vòng đời khác nhau.
- [ ] Tôi biết bulk JPQL/native SQL có thể làm managed entity stale.
- [ ] Tôi có chiến lược cache invalidation cho cập nhật ngoài Hibernate.
- [ ] Tôi có migration/backfill cho cột generated hoặc default.
- [ ] Tôi hiểu @Version phát hiện cập nhật cạnh tranh nhưng không thay thế refresh.
- [ ] Tôi kiểm thử trên database production bằng Testcontainers.

## 36. Câu hỏi ôn tập

**1. Khi nào dùng Java getter thay vì @Formula?**

Khi giá trị chỉ cần trong Java và phải phản ánh ngay thay đổi trong object, không cần database filter/sort theo giá trị đó.

**2. @Transient có tạo cột database không?**

Không. Nó đánh dấu thuộc tính không được JPA lưu trong bảng.

**3. @Formula có phải Jakarta Persistence standard không?**

Không. Đây là annotation Hibernate, dùng native SQL fragment và có thể ảnh hưởng database portability.

**4. Vì sao @Formula có thể stale sau setter?**

Hibernate tính formula trong SELECT. Thay đổi field nguồn trong object không tự chạy lại SQL formula.

**5. @ColumnDefault có đủ để database dùng DEFAULT không?**

Không. Schema thật phải có DEFAULT và INSERT phải bỏ cột thay vì truyền NULL tường minh.

**6. @Generated dùng trong trường hợp nào?**

Khi database tạo giá trị bằng default, trigger hoặc SQL expression và Hibernate cần đọc lại giá trị sau INSERT/UPDATE.

**7. @GeneratedColumn khác @Generated thế nào?**

@GeneratedColumn dành cho DDL generated always as. @Generated dùng cho giá trị được tạo bởi cơ chế như trigger, default hoặc SQL generation.

**8. Vì sao phải refresh sau native SQL?**

Hibernate không tự biết câu lệnh JDBC bên ngoài đã thay đổi row. Entity đang managed có thể tiếp tục giữ snapshot cũ.

**9. flush có làm commit transaction không?**

Không. Flush gửi SQL xuống database trong transaction hiện tại; commit mới hoàn tất transaction.

**10. @Version giải quyết vấn đề gì?**

Nó phát hiện cập nhật cạnh tranh và ngăn transaction ghi đè một phiên bản đã thay đổi. Nó không tự đồng bộ giá trị generated hoặc cache.

**11. Vì sao cần Testcontainers?**

Generated column, trigger, default và SQL expression khác nhau giữa database engine. Testcontainers giúp xác nhận hành vi trên cùng loại database với production.

Thuộc tính tính toán và giá trị do database sinh cần có một nguồn sự thật rõ ràng. Getter Java phù hợp với giá trị dẫn xuất trong memory; @Formula phù hợp với biểu thức SQL read-only; @Generated và @GeneratedColumn giúp Hibernate đồng bộ giá trị database tạo sau DML. Khi hiểu persistence context, cache, bulk SQL, optimistic locking và transaction, ứng dụng tránh được trạng thái stale và giữ dữ liệu nhất quán qua nhiều đường ghi.

## Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide — @Formula](https://docs.hibernate.org/orm/6.6/userguide/html_single/#mapping-column-formula)
- [Hibernate ORM 6.6 User Guide — Generated properties](https://docs.hibernate.org/orm/6.6/userguide/html_single/#mapping-generated)
- [Hibernate ORM — @Generated Javadoc](https://docs.hibernate.org/orm/current/javadocs/org/hibernate/annotations/Generated.html)
- [Hibernate ORM — @GeneratedColumn Javadoc](https://docs.hibernate.org/orm/7.0/javadocs/org/hibernate/annotations/GeneratedColumn.html)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
