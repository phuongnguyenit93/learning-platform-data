# Khi nào nên gọi stored procedure từ ứng dụng JPA

Stored procedure là chương trình được lưu và thực thi trong database. Ứng dụng Spring Data JPA có thể gọi procedure bằng `@Procedure` của Spring Data, `@NamedStoredProcedureQuery` của Jakarta Persistence hoặc API `StoredProcedureQuery` qua EntityManager.

Nên gọi stored procedure khi nghiệp vụ thực sự cần khả năng xử lý gần dữ liệu, cần tái sử dụng logic database đã tồn tại, cần thực hiện một thao tác set-based lớn hoặc phải tích hợp với hệ thống legacy. Với CRUD thông thường và truy vấn quan hệ có thể biểu diễn tốt bằng JPQL, derived query hoặc Criteria API, JPA query thường dễ bảo trì và di chuyển giữa các database hơn.

Stored procedure không tự động nhanh hơn JPQL và cũng không thay thế ranh giới transaction của ứng dụng. Trước khi chọn, cần cân nhắc tính di động, mapping kết quả, transaction, bảo mật, khả năng kiểm thử và quyền sở hữu logic nghiệp vụ.

## 1. Stored procedure là gì?

Stored procedure là một routine được định nghĩa trong database, thường có tên, tham số đầu vào/đầu ra và một hoặc nhiều câu lệnh SQL. Procedure có thể đọc dữ liệu, cập nhật nhiều bảng, tính toán, trả result set hoặc trả output parameter.

Ví dụ một procedure tính lại tổng tiền của khách hàng:

~~~sql
CREATE PROCEDURE recalculate_customer_total(
    IN p_customer_id BIGINT,
    OUT p_total DECIMAL(19, 2)
)
BEGIN
    SELECT COALESCE(SUM(total_amount), 0)
      INTO p_total
      FROM orders
     WHERE customer_id = p_customer_id;
END;
~~~

Đây là cú pháp minh họa theo phong cách MySQL. Cú pháp khai báo tham số, thân procedure, biến và cách trả kết quả thay đổi theo hệ quản trị database. Không sao chép nguyên văn ví dụ này sang PostgreSQL, SQL Server hoặc Oracle mà không điều chỉnh.

Khác với một câu SQL do ứng dụng gửi trong mỗi request, stored procedure được định nghĩa và quản lý trong schema database. Ứng dụng gọi procedure theo tên và truyền tham số.

## 2. Phân biệt stored procedure, function và JPQL

| Thành phần | Mục đích chính | Cách gọi thường gặp |
|---|---|---|
| JPQL | Truy vấn Entity và quan hệ theo mô hình JPA | Repository method, `@Query`, EntityManager |
| Native SQL | Gửi SQL phụ thuộc schema/database | `@Query(nativeQuery = true)`, native query |
| Stored procedure | Chạy routine đã lưu trong database, có thể đọc/ghi nhiều bảng và có tham số OUT | `@Procedure`, `StoredProcedureQuery`, JDBC CallableStatement |
| Database function | Tính toán và trả về một giá trị hoặc tập kết quả theo quy tắc của database | Biểu thức SQL, native query hoặc API provider |

Procedure thường được dùng cho một thao tác có nhiều bước hoặc có tham số OUT. Function thường được thiết kế để trả giá trị và có thể được gọi trong biểu thức SQL, nhưng quy tắc cụ thể phụ thuộc database.

JPQL mô tả truy vấn trên Entity và thuộc tính Java; native SQL và stored procedure làm việc gần schema database hơn. Stored procedure không phải một kiểu Repository query tự động có cùng semantics với derived query.

## 3. Khi nào nên cân nhắc stored procedure?

Các tình huống thường hợp lý:

1. **Xử lý dữ liệu lớn theo kiểu set-based:** cập nhật hoặc tổng hợp hàng nghìn/hàng triệu dòng ngay trong database, tránh tải từng Entity về ứng dụng.
2. **Logic đã tồn tại trong database:** hệ thống legacy đã có procedure được nhiều ứng dụng sử dụng và việc viết lại sẽ tạo rủi ro.
3. **Một thao tác cần nhiều câu SQL gần dữ liệu:** procedure có thể thực hiện nhiều bước và trả một kết quả tổng hợp trong một lần gọi.
4. **Tích hợp với hệ thống dùng chung schema:** nhiều client cần gọi cùng một database API được quản lý tập trung.
5. **Yêu cầu vận hành hoặc phân quyền:** DBA muốn cấp quyền EXECUTE trên một routine thay vì cấp quyền trực tiếp lên nhiều bảng, nếu mô hình quyền của database hỗ trợ.
6. **Tính năng đặc thù database:** cần dùng khả năng riêng của engine mà JPQL không biểu diễn được.

Ví dụ, một tác vụ cuối ngày có thể tổng hợp giao dịch, cập nhật bảng summary và ghi nhận kết quả batch trong một routine. Nếu việc tải toàn bộ giao dịch lên JVM rồi cập nhật từng Entity tạo quá nhiều round trip, procedure có thể phù hợp.

## 4. Khi nào không nên gọi stored procedure?

Không nên chọn procedure chỉ vì có thể viết SQL trong database. Các trường hợp sau thường nên giữ ở JPA/service:

- CRUD đơn giản như tìm theo ID, lưu Entity hoặc cập nhật một thuộc tính.
- Truy vấn có thể diễn đạt ngắn gọn bằng derived query hoặc JPQL.
- Logic thay đổi thường xuyên theo yêu cầu sản phẩm và cần review/test cùng mã ứng dụng.
- Dự án cần hỗ trợ nhiều hệ quản trị database với cùng một codebase.
- Procedure chỉ bọc một câu SELECT đơn giản mà không đem lại lợi ích rõ ràng.
- Ứng dụng gọi procedure một lần cho từng Entity trong vòng lặp, tạo ra hàng nghìn round trip.
- Không có quy trình quản lý version, migration, quyền truy cập và kiểm thử procedure.

Nếu logic là quy tắc nghiệp vụ cốt lõi, thay đổi thường xuyên và cần phối hợp nhiều dịch vụ, đặt logic ở service/domain layer thường giúp người phát triển hiểu và kiểm thử dễ hơn. Procedure phù hợp hơn khi database là nơi có lợi thế thực sự để thực hiện công việc đó.

## 5. So sánh quyết định: JPQL hay stored procedure?

| Tiêu chí | JPQL/Repository | Stored procedure |
|---|---|---|
| Mô hình | Entity và quan hệ JPA | Routine trong database |
| Tính di động | Thường cao hơn theo chuẩn JPA | Phụ thuộc engine và dialect |
| CRUD thông thường | Rất phù hợp | Thường không cần thiết |
| Xử lý set-based lớn | Có thể làm được, tùy query | Có thể phù hợp khi cần nhiều bước gần dữ liệu |
| Logic nghiệp vụ | Dễ đặt cùng service/domain và unit test | Logic nằm trong schema database |
| Kết quả | Entity, projection, DTO | Result set, OUT parameter, cursor hoặc nhiều kết quả |
| Versioning | Cùng vòng đời ứng dụng | Cần quản lý migration/version database |
| Bảo mật | Quyền trên bảng và query | Có thể cấp quyền EXECUTE theo routine |
| Debug | IDE, log SQL, JPA provider | Cần công cụ và quy trình debug database |
| Hiệu năng | Phụ thuộc SQL được sinh và số round trip | Không mặc định nhanh hơn; cần đo thực tế |

Quyết định nên dựa trên một yêu cầu cụ thể, không dựa trên sở thích rằng SQL trong database luôn nhanh hơn hoặc Java luôn dễ bảo trì hơn.

## 6. Cách 1: Gọi procedure bằng @Procedure

Spring Data JPA cung cấp annotation `@Procedure` trong package:

~~~java
import org.springframework.data.jpa.repository.query.Procedure;
~~~

Có thể khai báo procedure name trực tiếp trên Repository method:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Procedure(procedureName = "recalculate_customer_total")
    BigDecimal recalculateCustomerTotal(
            @Param("p_customer_id") Long customerId
    );
}
~~~

Ví dụ này minh họa procedure có một tham số IN và một tham số OUT. Phương thức nhận customerId và trả giá trị OUT kiểu BigDecimal. Tên procedure và tham số phải khớp định nghĩa thật trong database/provider.

Trong `@Procedure`:
- `procedureName` là tên routine trong database.
- `name` là tên JPA named stored procedure đã khai báo bằng `@NamedStoredProcedureQuery`.
- `value` là alias của `procedureName` trong annotation.
- `outputParameterName` có thể dùng để chỉ định output parameter cần lấy trong các cấu hình phù hợp.

Nếu procedure chỉ trả một output parameter, method return type thường được dùng để nhận giá trị đó. Nếu cần nhiều OUT parameter hoặc xử lý result set cùng output parameter, hãy kiểm tra giới hạn mapping của phiên bản Spring Data và cân nhắc EntityManager để kiểm soát rõ hơn.

Không nhầm `@Procedure(name = "...")` với `@Procedure(procedureName = "...")`: một bên tham chiếu tên khai báo trong JPA metadata, bên còn lại tham chiếu tên routine ở database.

## 7. Cách 2: Khai báo @NamedStoredProcedureQuery

Jakarta Persistence cho phép khai báo stored procedure trong metadata Entity bằng `@NamedStoredProcedureQuery`.

Ví dụ:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "customers")
@NamedStoredProcedureQuery(
    name = "Customer.recalculateTotal",
    procedureName = "recalculate_customer_total",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_customer_id",
            type = Long.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_total",
            type = BigDecimal.class
        )
    }
)
public class Customer {

    @Id
    private Long id;

    private String name;

    protected Customer() {
    }
}
~~~

Các thuộc tính quan trọng:
- `name`: tên định danh của named procedure trong persistence unit.
- `procedureName`: tên procedure thật ở database.
- `parameters`: danh sách tham số theo thứ tự/định danh mà procedure yêu cầu.
- `resultClasses`: các lớp Entity dùng để ánh xạ result set.
- `resultSetMappings`: tên các `@SqlResultSetMapping` dùng để ánh xạ kết quả.

Repository có thể tham chiếu named procedure:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Procedure(name = "Customer.recalculateTotal")
    BigDecimal recalculateCustomerTotal(
            @Param("p_customer_id") Long customerId
    );
}
~~~

Named procedure giúp tách tên routine trong database khỏi tên dùng trong ứng dụng. Nó cũng tập trung metadata tham số và result mapping ở một nơi. Khi procedure có nhiều kết quả hoặc mapping phức tạp, cần xác minh cách Spring Data ánh xạ kết quả với chữ ký method thực tế.

## 8. Các ParameterMode của JPA

JPA định nghĩa các mode tham số cho stored procedure:

| Mode | Hướng dữ liệu | Ý nghĩa |
|---|---|---|
| IN | Ứng dụng → procedure | Tham số đầu vào |
| OUT | Procedure → ứng dụng | Procedure trả giá trị |
| INOUT | Hai chiều | Ứng dụng truyền giá trị và procedure có thể thay đổi |
| REF_CURSOR | Procedure → ứng dụng | Trả cursor/result set theo khả năng provider/database |

Ví dụ khai báo:

~~~java
@StoredProcedureParameter(
    mode = ParameterMode.IN,
    name = "p_customer_id",
    type = Long.class
)
~~~

~~~java
@StoredProcedureParameter(
    mode = ParameterMode.OUT,
    name = "p_total",
    type = BigDecimal.class
)
~~~

~~~java
@StoredProcedureParameter(
    mode = ParameterMode.INOUT,
    name = "p_counter",
    type = Integer.class
)
~~~

Không phải mọi database/provider đều hỗ trợ REF_CURSOR hoặc mọi cách bind tên tham số. REF_CURSOR thường có khác biệt giữa PostgreSQL, Oracle và các provider. Hãy kiểm tra tài liệu database, Hibernate và Jakarta Persistence version đang dùng.

## 9. Cách 3: Gọi StoredProcedureQuery bằng EntityManager

Khi cần nhiều OUT parameter, xử lý result set, cursor hoặc kiểm soát trình tự thực thi, EntityManager thường linh hoạt hơn `@Procedure`.

Ví dụ:

~~~java
import java.math.BigDecimal;

import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.StoredProcedureQuery;

import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class CustomerProcedureRepository {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public BigDecimal recalculateTotal(Long customerId) {
        StoredProcedureQuery query =
                entityManager.createStoredProcedureQuery(
                        "recalculate_customer_total"
                );

        query.registerStoredProcedureParameter(
                "p_customer_id",
                Long.class,
                ParameterMode.IN
        );

        query.registerStoredProcedureParameter(
                "p_total",
                BigDecimal.class,
                ParameterMode.OUT
        );

        query.setParameter("p_customer_id", customerId);

        query.execute();

        return (BigDecimal) query.getOutputParameterValue("p_total");
    }
}
~~~

Trình tự:
1. Tạo StoredProcedureQuery bằng tên procedure.
2. Đăng ký từng tham số với tên/position, kiểu Java và ParameterMode.
3. Gán giá trị cho tham số IN hoặc INOUT.
4. Gọi execute().
5. Đọc OUT parameter bằng getOutputParameterValue().
6. Ánh xạ result set nếu procedure có trả dữ liệu.

Tên tham số phải phù hợp procedure và cách provider bind tham số. Nếu database/provider chỉ hỗ trợ binding theo vị trí, hãy đăng ký và gán tham số theo ordinal thay vì dựa vào tên.

Method được đánh dấu `@Transactional` vì ví dụ procedure có thể thực hiện công việc database. Nếu procedure chỉ đọc, có thể dùng readOnly phù hợp, nhưng cần kiểm tra procedure thực tế không ghi dữ liệu.

## 10. Truyền tham số theo tên và theo vị trí

JPA StoredProcedureQuery hỗ trợ đăng ký tham số bằng tên hoặc vị trí tùy provider và procedure.

Theo tên:

~~~java
query.registerStoredProcedureParameter(
        "p_customer_id",
        Long.class,
        ParameterMode.IN
);
query.setParameter("p_customer_id", customerId);
~~~

Theo vị trí:

~~~java
query.registerStoredProcedureParameter(
        1,
        Long.class,
        ParameterMode.IN
);
query.setParameter(1, customerId);
~~~

Thứ tự tham số là một phần hợp đồng của procedure. Khi procedure thay đổi thứ tự hoặc tên tham số, cần cập nhật metadata/caller và integration test tương ứng.

Không nối chuỗi đầu vào vào câu lệnh gọi procedure. Dùng parameter binding để truyền giá trị. Tên procedure và identifier thường không thể bind như một value parameter; nếu cần chọn procedure động, hãy dùng danh sách tên được whitelist trong code.

## 11. Procedure trả result set

Procedure có thể trả nhiều dòng thay vì một OUT scalar. Với EntityManager, có thể tạo query ánh xạ kết quả thành Entity:

~~~java
StoredProcedureQuery query =
        entityManager.createStoredProcedureQuery(
                "find_customers_by_status",
                Customer.class
        );

query.registerStoredProcedureParameter(
        "p_status",
        String.class,
        ParameterMode.IN
);

query.setParameter("p_status", "ACTIVE");

@SuppressWarnings("unchecked")
List<Customer> customers = query.getResultList();
~~~

Đối số thứ hai của createStoredProcedureQuery chỉ định result class để ánh xạ các dòng về Entity. Result set phải có cột và kiểu tương thích với mapping của Customer theo provider/database.

Nếu procedure trả các cột tổng hợp hoặc DTO thay vì toàn bộ Entity, có thể dùng `@SqlResultSetMapping` cùng `ConstructorResult`, `ColumnResult` hoặc `EntityResult`, tùy dạng kết quả. Không khai báo result class là Entity đầy đủ nếu procedure chỉ SELECT một phần cột cần thiết cho Entity.

Ví dụ ý tưởng mapping DTO:

~~~java
@SqlResultSetMapping(
    name = "CustomerTotalMapping",
    classes = @ConstructorResult(
        targetClass = CustomerTotalDto.class,
        columns = {
            @ColumnResult(name = "customer_id", type = Long.class),
            @ColumnResult(name = "total_amount", type = BigDecimal.class)
        }
    )
)
~~~

Sau đó tạo StoredProcedureQuery với tên mapping:

~~~java
StoredProcedureQuery query =
        entityManager.createStoredProcedureQuery(
                "customer_totals",
                "CustomerTotalMapping"
        );
~~~

DTO cần constructor phù hợp với thứ tự và kiểu các cột. Tên alias trong result set phải khớp ColumnResult. Cú pháp routine trả result set và cách driver expose kết quả phụ thuộc database.

## 12. Procedure trả nhiều kết quả

Một procedure có thể trả result set, update count và OUT parameter. Khi có nhiều kết quả, không nên giả định chỉ cần gọi getResultList() một lần là đã tiêu thụ hết.

JPA StoredProcedureQuery cung cấp các thao tác như:
- execute(): thực thi procedure và cho biết kết quả đầu tiên có phải result set hay không.
- hasMoreResults(): chuyển/kiểm tra kết quả tiếp theo.
- getResultList(): đọc result set hiện tại.
- getUpdateCount(): lấy update count hiện tại.
- getOutputParameterValue(): đọc output parameter.

Việc đọc kết quả theo thứ tự và thời điểm có thể chịu ảnh hưởng của database, JDBC driver và provider. Với procedure trả nhiều result set, hãy kiểm thử cách chuyển giữa result set/update count trên đúng engine và driver production.

Nếu method chỉ cần một OUT parameter đơn giản, `@Procedure` thường ngắn gọn hơn. Nếu cần điều khiển nhiều kết quả, EntityManager/StoredProcedureQuery hoặc JDBC CallableStatement có thể phù hợp hơn.

## 13. Transaction khi gọi stored procedure

Gọi procedure từ JPA không tự động tạo ra một ranh giới transaction độc lập theo ý nghĩa nghiệp vụ. Procedure thường chạy trên connection/resource đang được transaction manager quản lý.

Nếu procedure cập nhật nhiều bảng và những thay đổi đó phải nguyên tử với các thao tác JPA khác, gọi nó bên trong service transaction:

~~~java
@Service
public class CustomerMaintenanceService {

    private final CustomerProcedureRepository procedureRepository;
    private final CustomerRepository customerRepository;

    public CustomerMaintenanceService(
            CustomerProcedureRepository procedureRepository,
            CustomerRepository customerRepository) {
        this.procedureRepository = procedureRepository;
        this.customerRepository = customerRepository;
    }

    @Transactional
    public void recalculateAndMark(Long customerId) {
        procedureRepository.recalculateTotal(customerId);

        Customer customer = customerRepository.findById(customerId)
                .orElseThrow();

        customer.markTotalRecalculated();
    }
}
~~~

Nếu các thao tác dùng cùng transaction manager và resource, procedure và JPA update có thể tham gia cùng transaction. Nếu bước sau thất bại và transaction rollback, thay đổi procedure cũng rollback khi procedure/database tôn trọng transaction của caller.

**Cần đặc biệt chú ý:** một số procedure có thể tự COMMIT, ROLLBACK, dùng autonomous transaction hoặc gọi thao tác không transactional theo đặc thù database. Khi đó procedure có thể phá vỡ kỳ vọng atomicity của transaction Spring. Nếu service cần rollback toàn bộ, tránh transaction control nội bộ trong procedure trừ khi đã thiết kế và kiểm thử rõ.

Không giả định một procedure chạy qua database khác hoặc một connection độc lập sẽ tham gia transaction JPA hiện tại. Nhiều datasource cần transaction manager hoặc giải pháp phân tán riêng.

## 14. Flush persistence context trước khi gọi procedure

JPA có persistence context và có thể trì hoãn SQL cho đến flush. Nếu procedure đọc dữ liệu vừa được thay đổi bởi Entity đang managed, cần bảo đảm những thay đổi đó đã được đồng bộ xuống database trước khi procedure chạy.

Ví dụ:

~~~java
@Transactional
public void updateAndRecalculate(Long customerId) {
    Customer customer = customerRepository.findById(customerId)
            .orElseThrow();

    customer.changePricingTier("GOLD");

    entityManager.flush();

    procedureRepository.recalculateTotal(customerId);
}
~~~

flush() đẩy các thay đổi đang chờ trong persistence context xuống database trong transaction hiện tại. Nó không commit transaction; các thay đổi vẫn có thể rollback.

Sau khi procedure cập nhật trực tiếp các dòng tương ứng với Entity đang managed, persistence context có thể chứa trạng thái cũ. Cần cân nhắc:
- refresh(Entity) để đọc lại một Entity cụ thể.
- clear() để bỏ toàn bộ Entity khỏi persistence context.
- Không tiếp tục dùng object cũ nếu procedure đã thay đổi các cột mà object đó đang giữ.

Ví dụ:

~~~java
entityManager.refresh(customer);
~~~

Chỉ refresh khi Entity còn managed và procedure đã cập nhật dữ liệu tương ứng. Nếu có nhiều Entity bị ảnh hưởng, hãy thiết kế việc clear/reload cẩn thận để không làm mất thay đổi chưa flush.

## 15. Stored procedure và @Modifying query khác nhau

`@Modifying` thường được dùng với JPQL/native DML khai báo qua `@Query`, ví dụ UPDATE hoặc DELETE. Nó không phải annotation để gọi stored procedure.

Ví dụ JPQL bulk update:

~~~java
@Modifying
@Query("""
    update Customer c
       set c.active = false
     where c.lastLoginAt < :cutoff
    """)
int deactivateInactiveCustomers(
        @Param("cutoff") Instant cutoff
);
~~~

Bulk update được thực thi như DML trên database và không gọi lifecycle callback cho từng Entity. Sau bulk operation, persistence context có thể cần clear/refresh.

Nếu thao tác đã được đóng gói trong stored procedure, dùng `@Procedure`, StoredProcedureQuery hoặc JDBC callable API. Không cố gắn `@Modifying` vào một method chỉ để biến nó thành lời gọi procedure.

## 16. Bảo mật khi gọi procedure

Stored procedure không tự động an toàn chỉ vì SQL nằm trong database. Cần bảo vệ cả đầu vào, quyền thực thi và nội dung routine.

Thực hành tốt:
- Dùng parameter binding cho mọi giá trị đầu vào.
- Không nối chuỗi người dùng vào dynamic SQL trong procedure.
- Nếu procedure phải tạo dynamic identifier, dùng whitelist và validate chặt.
- Cấp quyền EXECUTE đúng procedure cần thiết.
- Hạn chế quyền trực tiếp lên bảng nếu mô hình security của database cho phép.
- Xem xét quyền chạy theo owner/definer hoặc invoker theo semantics database.
- Không đưa dữ liệu nhạy cảm hoặc SQL đầy đủ vào log nếu không cần.
- Kiểm soát quyền truy cập theo tenant/user ở database hoặc application layer một cách nhất quán.

Nếu procedure chạy với quyền owner/definer, người gọi có thể thực hiện thao tác mà tài khoản ứng dụng không được phép làm trực tiếp. Đây có thể là thiết kế bảo mật có chủ đích, nhưng routine phải kiểm tra quyền và tham số cẩn thận.

## 17. Hiệu năng: procedure có luôn nhanh hơn không?

Không. Stored procedure có thể giảm round trip và xử lý dữ liệu gần database, nhưng kết quả cuối cùng phụ thuộc execution plan, index, dữ liệu, locking và số lần gọi.

Procedure có thể có lợi khi:
- Thực hiện nhiều thao tác set-based trong một lần gọi.
- Tránh tải lượng lớn Entity lên JVM chỉ để cập nhật.
- Tính toán hoặc tổng hợp gần nơi dữ liệu được lưu.
- Dùng execution plan phù hợp và tránh các round trip lặp.

Procedure có thể kém hiệu quả khi:
- Ứng dụng gọi một lần cho mỗi bản ghi trong vòng lặp.
- Routine chứa nhiều query không có index phù hợp.
- Procedure trả result set quá lớn.
- Procedure giữ lock lâu hoặc chạy transaction kéo dài.
- Mỗi lần gọi tạo nhiều chuyển đổi giữa JVM và database.
- Logic bị lặp lại giữa procedure và service khiến hệ thống khó tối ưu.

Đo cả thời gian database và thời gian end-to-end. Dùng execution plan của database để kiểm tra index, join, sort, scan và số dòng thực tế. Không kết luận procedure nhanh hơn chỉ vì nó chạy trong database.

## 18. Versioning và migration của procedure

Procedure là một phần của database schema contract. Khi thay đổi tên, thứ tự tham số, kiểu dữ liệu, output parameter hoặc result set, các ứng dụng gọi nó có thể bị ảnh hưởng.

Nên:
1. Quản lý DDL procedure bằng Flyway hoặc Liquibase.
2. Đặt migration có thứ tự và có thể review.
3. Đồng bộ version procedure với version ứng dụng.
4. Tránh thay đổi breaking contract mà không có kế hoạch rollout.
5. Kiểm thử migration từ schema phiên bản trước.
6. Kiểm tra quyền EXECUTE sau khi tạo/thay thế routine.
7. Có kế hoạch rollback hoặc forward-fix cho procedure production.

Nếu nhiều ứng dụng cùng gọi một procedure, hãy xem tên và chữ ký của nó như API dùng chung. Có thể cần tạo procedure version mới thay vì đổi trực tiếp hợp đồng cũ.

## 19. Khả năng di động giữa các database

Stored procedure phụ thuộc database ở nhiều điểm:
- Ngôn ngữ procedural và cú pháp khai báo.
- Cách đặt tên/schema và overload routine.
- Cách truyền tham số theo tên hay vị trí.
- Kiểu dữ liệu số, thời gian và null.
- Result set, cursor và REF_CURSOR.
- Transaction control và exception handling.
- Cách cấp quyền EXECUTE.
- Cách driver JDBC expose nhiều kết quả.

JPA chuẩn hóa API gọi stored procedure ở một mức nhất định, nhưng không làm cho phần định nghĩa procedure trở nên portable. Một procedure Oracle không tự chạy trên PostgreSQL chỉ vì ứng dụng dùng `@Procedure`.

Nếu cần hỗ trợ nhiều database, có thể:
- Giữ logic chính trong JPQL/Criteria/service.
- Tách procedure theo dialect/schema và dùng migration riêng.
- Tạo adapter/repository riêng cho từng database.
- Dùng interface service chung nhưng implementation khác theo profile/configuration.
- Kiểm thử trên từng database engine thực sự hỗ trợ.

## 20. Kiểm thử stored procedure

Unit test service có thể mock repository/procedure caller để kiểm tra điều phối, nhưng không chứng minh procedure chạy đúng. Cần integration test trên database có procedure thực tế.

Nên kiểm tra:
1. Procedure tồn tại sau khi chạy migration.
2. Tham số IN được bind đúng.
3. OUT/INOUT trả kiểu và giá trị đúng.
4. Result set ánh xạ đúng Entity/DTO.
5. Procedure không có dữ liệu và dữ liệu biên.
6. Giá trị null, precision/scale và timestamp.
7. Quyền EXECUTE của tài khoản ứng dụng.
8. Transaction rollback khi bước JPA sau procedure thất bại.
9. Flush trước procedure và refresh sau procedure khi cần.
10. Nhiều result set/update count nếu procedure hỗ trợ.
11. Hành vi trên database và JDBC driver production.
12. Thời gian chạy, lock và execution plan với dữ liệu đủ lớn.

Ví dụ integration test khái niệm:

~~~java
@SpringBootTest
class CustomerProcedureIntegrationTest {

    @Autowired
    private CustomerProcedureRepository procedureRepository;

    @Test
    void returnsCalculatedTotal() {
        // Tạo fixture customer và order bằng repository.
        BigDecimal total =
                procedureRepository.recalculateCustomerTotal(100L);

        assertEquals(new BigDecimal("150.00"), total);
    }
}
~~~

Fixture phải tạo đúng dữ liệu cho customer ID 100 và tổng đơn hàng mong đợi. Không dùng H2 để kết luận procedure PostgreSQL/Oracle/MySQL hoạt động giống production nếu cú pháp và semantics phụ thuộc engine. Testcontainers với đúng database image thường hữu ích cho integration test.

## 21. Lỗi thường gặp khi gọi procedure từ JPA

**Nhầm tên named procedure với tên procedure database**

`@Procedure(name = "...")` tham chiếu JPA named query; `procedureName` tham chiếu tên routine database. Kiểm tra đúng thuộc tính.

**Tham số không đúng thứ tự hoặc tên**

Một số driver/provider yêu cầu binding theo vị trí. Đối chiếu chữ ký procedure và cách đăng ký tham số.

**Kiểu Java không khớp kiểu database**

Ví dụ DECIMAL có precision/scale khác BigDecimal mong đợi, hoặc timestamp khác kiểu Instant. Kiểm tra JDBC mapping thực tế.

**Chỉ có một OUT parameter nhưng method return type không tương thích**

Chọn kiểu trả về phù hợp. Với nhiều OUT parameter hoặc result set phức tạp, dùng EntityManager để đọc rõ từng kết quả.

**Dùng Entity làm result class nhưng procedure SELECT thiếu cột**

Entity mapping cần dữ liệu phù hợp. Dùng DTO/result set mapping khi kết quả không phải Entity đầy đủ.

**Quên transaction khi procedure cập nhật dữ liệu**

Đặt ranh giới transaction ở service/use case và xác nhận procedure tham gia transaction của caller.

**Procedure tự COMMIT**

Có thể phá vỡ kỳ vọng rollback của Spring. Tránh transaction control nội bộ khi cần atomicity với JPA operations.

**Persistence context chứa dữ liệu cũ**

Procedure cập nhật trực tiếp bảng trong khi Entity vẫn managed. Flush trước khi procedure đọc thay đổi pending; refresh/clear sau khi procedure ghi dữ liệu có thể cần thiết.

**Gọi procedure trong vòng lặp cho từng Entity**

Tạo nhiều round trip. Cân nhắc một lần gọi theo lô hoặc query set-based.

**Không version hóa DDL**

Ứng dụng mới có thể gọi routine chưa tồn tại hoặc chữ ký đã thay đổi. Dùng migration và kiểm tra schema trước rollout.

**Tin rằng procedure luôn nhanh và portable**

Đo execution plan và kiểm thử trên database mục tiêu. JPA API không chuẩn hóa ngôn ngữ bên trong procedure.

## 22. Quy trình ra quyết định và triển khai

Khi một yêu cầu có thể dùng stored procedure, hãy đi theo trình tự:

1. Xác định vấn đề có thể giải quyết bằng derived query, JPQL, Criteria hoặc native SQL đơn giản hay không.
2. Xác định lợi ích cụ thể của procedure: set-based processing, logic legacy, nhiều thao tác gần dữ liệu, phân quyền hoặc tính năng database riêng.
3. Xác định routine là API dùng chung hay chỉ phục vụ một ứng dụng.
4. Chốt chữ ký: tên procedure, schema, IN/OUT/INOUT/REF_CURSOR, kiểu và thứ tự tham số, result set.
5. Chọn `@Procedure` cho trường hợp đơn giản; chọn `@NamedStoredProcedureQuery` khi cần metadata JPA; chọn EntityManager/JDBC khi cần kiểm soát nhiều kết quả hoặc binding.
6. Xác định transaction manager và bảo đảm procedure không tự commit trái với invariant nghiệp vụ.
7. Xác định flush/refresh/clear cần thiết cho persistence context.
8. Quản lý DDL và quyền EXECUTE bằng migration.
9. Viết integration test trên database/driver mục tiêu.
10. Đo execution plan, round trip, thời gian, lock và lượng dữ liệu trả về.
11. Lập kế hoạch versioning và rollout cho mọi ứng dụng đang gọi procedure.

## 23. Kết luận

Hãy gọi stored procedure từ JPA khi database có lợi thế rõ ràng: xử lý set-based lớn, tích hợp logic legacy, thực hiện nhiều thao tác gần dữ liệu hoặc cung cấp một database API được quản lý tập trung. Spring Data JPA hỗ trợ `@Procedure`; Jakarta Persistence hỗ trợ `@NamedStoredProcedureQuery` và `StoredProcedureQuery` qua EntityManager. Chọn API đơn giản cho một OUT parameter hoặc result set cơ bản, và dùng EntityManager/JDBC khi cần nhiều tham số, cursor hoặc nhiều kết quả. Giữ transaction ở service/use case, kiểm soát flush và persistence context, tránh procedure tự COMMIT nếu cần rollback chung, quản lý DDL bằng migration và kiểm thử trên database thật. Procedure không mặc định nhanh hơn hay portable hơn JPQL; chỉ giữ nó khi lợi ích về dữ liệu, vận hành hoặc tích hợp đáng với chi phí bảo trì.
