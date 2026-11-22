# Đánh đổi giữa khả năng tùy biến SQL và chi phí bảo trì

Khi tích hợp **MyBatis** vào ứng dụng **Spring Data JDBC**, nhóm phát triển có thể chọn công cụ phù hợp cho từng loại truy vấn: Spring Data JDBC quản lý aggregate và các thao tác CRUD theo mapping, còn MyBatis cung cấp quyền kiểm soát SQL chi tiết cho truy vấn phức tạp, báo cáo hoặc thao tác đặc thù.

Khả năng tùy biến đó có giá phải trả. SQL được viết tường minh phải được duy trì cùng schema, dialect, mapping, transaction, cache và quy tắc nghiệp vụ. Nếu cả Spring Data JDBC lẫn MyBatis cùng ghi một aggregate mà không có ranh giới rõ ràng, ứng dụng dễ có hai bộ quy tắc persistence cạnh tranh nhau.

Vì vậy, quyết định tích hợp không chỉ là MyBatis viết SQL linh hoạt hơn. Cần cân nhắc **giá trị của quyền kiểm soát SQL so với chi phí bảo trì mà quyền kiểm soát đó tạo ra**. Bài này trình bày cách phân chia trách nhiệm, nhận diện chi phí ẩn, chọn đúng trường hợp dùng MyBatis và giữ hệ thống dễ kiểm thử khi hai công nghệ cùng tồn tại.

## 1. Vì sao kết hợp Spring Data JDBC với MyBatis?

Spring Data JDBC tập trung vào aggregate persistence. Framework đọc metadata của aggregate root, tạo SQL cho insert/update/delete, quản lý ID và hỗ trợ optimistic locking qua @Version. Cách tiếp cận này phù hợp khi nghiệp vụ được mô hình hóa theo aggregate và thao tác lưu thường xuyên là lưu cả aggregate root.

MyBatis tập trung vào SQL do lập trình viên kiểm soát. Mapper có thể khai báo SQL bằng annotation hoặc XML, dùng dynamic SQL, join nhiều bảng, projection tùy chỉnh và mapping kết quả vào DTO. Nó hữu ích khi truy vấn cần tận dụng tính năng riêng của database hoặc có hình dạng kết quả không tương ứng với một aggregate.

Một ứng dụng có thể dùng cả hai:

- Spring Data JDBC cho các thao tác domain thông thường như tạo đơn hàng, đổi trạng thái theo hành vi aggregate và lưu các collection con.
- MyBatis cho báo cáo, tìm kiếm phức tạp, join nhiều bảng, projection, truy vấn legacy hoặc SQL đã được tối ưu riêng.
- Application service điều phối use case và transaction, không để controller gọi lẫn lộn nhiều persistence API.

~~~mermaid
flowchart TD
    A[Controller / Job / Message Handler] --> B[Application Service]
    B --> C[Spring Data JDBC Repository]
    B --> D[MyBatis Mapper]
    C --> E[Aggregate Mapping]
    D --> F[Explicit SQL and Result Mapping]
    E --> G[Shared DataSource and Transaction Manager]
    F --> G
    G --> H[(Database)]
~~~

Cả hai công cụ có thể cùng truy cập một database, nhưng không có cùng mục đích. Spring Data JDBC quản lý aggregate theo metadata; MyBatis thực thi mapper statement do ứng dụng định nghĩa.

## 2. Lợi ích của SQL tùy biến

MyBatis tạo giá trị khi câu SQL cần được nhìn thấy và kiểm soát trực tiếp.

### Truy vấn join và projection

Một màn hình quản trị có thể cần dữ liệu từ đơn hàng, khách hàng và thanh toán. Kết quả là một dòng hiển thị, không phải aggregate root cần lưu:

~~~sql
SELECT
    o.id AS order_id,
    o.order_number,
    o.status,
    c.display_name AS customer_name,
    p.payment_status,
    o.total
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN payments p ON p.order_id = o.id
WHERE o.created_at >= #{from}
  AND o.created_at < #{to}
ORDER BY o.created_at DESC, o.id ASC
~~~

MyBatis có thể ánh xạ trực tiếp kết quả sang DTO. Không cần dựng toàn bộ aggregate chỉ để hiển thị một bảng báo cáo.

### Tối ưu truy vấn đặc thù

MyBatis cho phép nhóm phát triển chủ động viết:

- CTE và recursive query.
- Window functions.
- Database-specific JSON operators.
- Join và subquery có cấu trúc phức tạp.
- Bulk update có điều kiện.
- Hint hoặc cú pháp đặc thù của DBMS khi có lý do rõ ràng.
- Projection chỉ lấy các cột cần thiết.

Đây là lợi ích thật khi query đã được đo lường và SQL rõ ràng giúp kiểm soát execution plan. Tuy nhiên, có thể viết SQL phức tạp không đồng nghĩa nên viết SQL phức tạp. Một query khó đọc hoặc không có test sẽ làm chi phí bảo trì tăng nhanh.

## 3. Chi phí bảo trì phát sinh từ SQL tường minh

Khi dùng Spring Data JDBC, một phần SQL được sinh từ mapping metadata. Khi dùng MyBatis, nhóm phát triển trực tiếp chịu trách nhiệm nhiều quyết định hơn.

| Khía cạnh | Spring Data JDBC | MyBatis |
|---|---|---|
| SQL CRUD cơ bản | Framework sinh theo mapping | Thường phải viết mapper statement nếu dùng cho CRUD |
| Mapping property/cột | Dựa trên annotation và naming strategy | Dựa trên SQL alias, resultMap và cấu hình mapper |
| Insert/update aggregate | Có quy tắc aggregate persistence | Mapper chỉ chạy câu SQL đã khai báo |
| Optimistic locking | Được hỗ trợ trong đường save với @Version | Phải đưa version vào WHERE và tăng version tường minh |
| Child collection | Framework quản lý theo aggregate mapping | Phải viết SQL và thứ tự thao tác |
| Generated ID | Repository trả aggregate đã lưu | Cần cấu hình useGeneratedKeys/keyProperty hoặc cơ chế database tương ứng |
| Dynamic SQL | Query/Criteria có phạm vi được hỗ trợ | Có nhiều cấu trúc dynamic SQL |
| Join/projection tùy chỉnh | Có thể cần query hoặc JDBC tùy chỉnh | Là thế mạnh của mapper SQL |
| Portability | Dialect xử lý phần SQL framework sinh | SQL viết tay phải được kiểm soát theo DBMS |
| Chi phí bảo trì | Mapping tập trung, ít SQL CRUD thủ công | Nhiều mapper, resultMap, statement và test phải đồng bộ |

MyBatis không tự động tạo chi phí lớn trong mọi dự án. Chi phí phụ thuộc số lượng statement, độ phức tạp mapping, số DBMS được hỗ trợ và mức độ trùng lặp quy tắc persistence.

## 4. Thiết lập ranh giới trách nhiệm trước khi thêm mapper

Một nguyên tắc hữu ích là xác định công cụ sở hữu từng use case.

Ví dụ với aggregate PurchaseOrder:

- Tạo đơn hàng: Spring Data JDBC.
- Thay đổi trạng thái theo domain rule: Spring Data JDBC.
- Lưu danh sách OrderLine: Spring Data JDBC.
- Màn hình tìm kiếm kết hợp thông tin khách hàng/thanh toán: MyBatis read mapper.
- Báo cáo tổng doanh thu theo tháng: MyBatis read mapper.
- Bulk cập nhật hàng nghìn dòng: cân nhắc MyBatis nếu SQL trực tiếp là lựa chọn có kiểm soát, đồng thời xử lý version/audit/invariant.

Ranh giới này giúp một aggregate không bị nhiều đường ghi cùng sở hữu. Nếu MyBatis cần cập nhật một cột trên aggregate do Spring Data JDBC quản lý, phải quy định rõ ai chịu trách nhiệm version, auditing, callback, child collection và đồng bộ object đang nằm trong bộ nhớ.

Một cách tổ chức package:

~~~text
com.example.orders
  domain/
    PurchaseOrder.java
    OrderLine.java
  application/
    PurchaseOrderService.java
    PurchaseOrderSearchService.java
  persistence/
    jdbc/
      PurchaseOrderRepository.java
    mybatis/
      PurchaseOrderReadMapper.java
      PurchaseOrderReadMapper.xml
      PurchaseOrderSummary.java
~~~

Tên package không bắt buộc. Điều quan trọng là code cho thấy mapper phục vụ read/report hay là đường ghi nghiệp vụ. Có thể dùng tên như ReadMapper hoặc ReportMapper để biểu đạt ý định.

## 5. Ví dụ: Spring Data JDBC lưu aggregate, MyBatis đọc DTO

Aggregate root:

~~~java
import java.math.BigDecimal;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        @Version Long version,
        String orderNumber,
        Long customerId,
        String status,
        BigDecimal total
) {}
~~~

Repository:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

DTO cho màn hình quản trị:

~~~java
import java.math.BigDecimal;

public record PurchaseOrderSummary(
        Long orderId,
        String orderNumber,
        String customerName,
        String status,
        BigDecimal total
) {}
~~~

Mapper interface:

~~~java
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface PurchaseOrderReadMapper {
    List<PurchaseOrderSummary> search(
            @Param("status") String status,
            @Param("customerName") String customerName
    );
}
~~~

XML mapper:

~~~xml
<?xml version="1.0" encoding="UTF-8" ?>
<!DOCTYPE mapper
  PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"
  "https://mybatis.org/dtd/mybatis-3-mapper.dtd">

<mapper namespace="com.example.orders.persistence.mybatis.PurchaseOrderReadMapper">

  <select id="search"
          resultType="com.example.orders.persistence.mybatis.PurchaseOrderSummary">
    SELECT
      o.id AS orderId,
      o.order_number AS orderNumber,
      c.display_name AS customerName,
      o.status AS status,
      o.total AS total
    FROM purchase_orders o
    JOIN customers c ON c.id = o.customer_id
    <where>
      <if test="status != null and status != ''">
        AND o.status = #{status}
      </if>
      <if test="customerName != null and customerName != ''">
        AND c.display_name LIKE CONCAT('%', #{customerName}, '%')
      </if>
    </where>
    ORDER BY o.id DESC
  </select>

</mapper>
~~~

Application service:

~~~java
@Service
public class PurchaseOrderService {
    private final PurchaseOrderRepository repository;
    private final PurchaseOrderReadMapper readMapper;

    public PurchaseOrderService(
            PurchaseOrderRepository repository,
            PurchaseOrderReadMapper readMapper
    ) {
        this.repository = repository;
        this.readMapper = readMapper;
    }

    @Transactional
    public PurchaseOrder create(PurchaseOrder order) {
        return repository.save(order);
    }

    @Transactional(readOnly = true)
    public List<PurchaseOrderSummary> search(
            String status,
            String customerName
    ) {
        return readMapper.search(status, customerName);
    }
}
~~~

Ví dụ trên minh họa sự phân chia: repository sở hữu thao tác lưu aggregate; MyBatis sở hữu truy vấn đọc kết hợp nhiều bảng. DTO giúp màn hình không phụ thuộc vào cấu trúc aggregate nội bộ.

Cú pháp CONCAT có thể khác giữa DBMS. Nếu ứng dụng hỗ trợ nhiều database, cần chọn cú pháp portable hoặc tách mapper statement theo database. MyBatis không tự chuyển toàn bộ SQL viết tay sang cú pháp tương đương của database khác.

## 6. Annotation SQL hay XML mapper?

MyBatis cho phép khai báo SQL ngay trên interface hoặc đặt trong XML.

### Annotation phù hợp khi

- Statement ngắn.
- Query ít dynamic branch.
- SQL dễ đọc trên một màn hình.
- Mapper nhỏ và không cần resultMap phức tạp.

Ví dụ:

~~~java
@Mapper
public interface CustomerReadMapper {

    @Select("""
        SELECT id, display_name AS name, email
        FROM customers
        WHERE id = #{id}
        """)
    CustomerSummary findSummaryById(@Param("id") Long id);
}
~~~

### XML phù hợp khi

- SQL dài hoặc có nhiều điều kiện động.
- Có resultMap phức tạp.
- Cần tái sử dụng SQL fragment.
- Muốn tách SQL khỏi Java interface.
- Query cần được đọc, review hoặc tối ưu độc lập.

~~~xml
<mapper namespace="com.example.CustomerReadMapper">
  <resultMap id="customerSummary"
             type="com.example.CustomerSummary">
    <id property="id" column="id"/>
    <result property="name" column="display_name"/>
    <result property="email" column="email"/>
  </resultMap>

  <select id="findSummaryById" resultMap="customerSummary">
    SELECT id, display_name, email
    FROM customers
    WHERE id = #{id}
  </select>
</mapper>
~~~

Không có quy tắc annotation luôn tốt hơn XML hoặc ngược lại. Chọn cách biểu diễn giúp statement dễ đọc và dễ bảo trì trong codebase. Tránh trộn cả hai kiểu cho cùng một mapper nếu không có quy ước.

## 7. Dynamic SQL: linh hoạt nhưng phải giới hạn đầu vào

Dynamic SQL là một lợi ích nổi bật của MyBatis. Các phần tử như if, choose, trim, where, set và foreach giúp tạo statement theo tham số.

Ví dụ lọc đơn hàng:

~~~xml
<select id="search" resultType="PurchaseOrderSummary">
  SELECT id, order_number, status, total
  FROM purchase_orders
  <where>
    <if test="status != null and status != ''">
      AND status = #{status}
    </if>
    <if test="minimumTotal != null">
      AND total >= #{minimumTotal}
    </if>
    <if test="createdFrom != null">
      AND created_at >= #{createdFrom}
    </if>
    <if test="createdTo != null">
      AND created_at < #{createdTo}
    </if>
  </where>
  ORDER BY created_at DESC, id ASC
</select>
~~~

Giá trị truyền bằng #{...} được bind thành parameter. Không dùng cú pháp thay chuỗi trực tiếp trong SQL cho dữ liệu người dùng chưa kiểm soát vì có thể tạo SQL injection.

Nếu cần sort động, ánh xạ lựa chọn của client sang danh sách identifier được phép trong code hoặc dùng choose với các nhánh cố định:

~~~xml
<choose>
  <when test="sortBy == 'amount'">
    ORDER BY total
  </when>
  <when test="sortBy == 'created'">
    ORDER BY created_at
  </when>
  <otherwise>
    ORDER BY id
  </otherwise>
</choose>
~~~

Direction ASC/DESC cũng phải được giới hạn bằng nhánh cố định. Parameter binding bảo vệ value; nó không biến identifier hoặc keyword thành parameter hợp lệ.

Dynamic SQL càng nhiều nhánh thì số hình dạng SQL cần kiểm thử càng lớn. Hãy giới hạn số bộ lọc, viết test cho các tổ hợp quan trọng và tránh tạo một mapper statement làm mọi thứ.

## 8. Chi phí mapping và resultMap

Spring Data JDBC dựa trên metadata entity để ánh xạ aggregate. MyBatis có mô hình mapping riêng: resultType, resultMap, constructor mapping, association và collection mapping.

Một DTO phẳng thường dễ ánh xạ:

~~~xml
<select id="findSummary" resultType="PurchaseOrderSummary">
  SELECT
    id AS orderId,
    order_number AS orderNumber,
    status,
    total
  FROM purchase_orders
  WHERE id = #{id}
</select>
~~~

Khi tên cột không khớp property, dùng alias hoặc resultMap. Với mapping lồng nhau, resultMap cần chỉ rõ quan hệ giữa cột và property.

Chi phí bảo trì tăng khi:

- Nhiều mapper tự khai báo lại cùng một result mapping.
- Alias cột không nhất quán.
- Query SELECT * làm thay đổi schema ảnh hưởng ngầm đến mapping.
- Một DTO được dùng chung cho nhiều query có hình dạng cột khác nhau.
- Collection join tạo duplicate row nhưng resultMap không xử lý đúng identity.
- Nullability/constructor mapping không khớp kiểu Java.

Để giảm chi phí:

- Dùng DTO riêng cho read model có mục đích rõ.
- Chỉ select các cột cần thiết.
- Đặt alias nhất quán theo property.
- Dùng resultMap khi mapping có cấu trúc, không cố ép resultType cho mọi trường hợp.
- Tránh dùng MyBatis để dựng toàn bộ aggregate Spring Data JDBC nếu không thật sự cần.

## 9. Đừng tạo hai chủ sở hữu cho một aggregate

Một rủi ro lớn là Spring Data JDBC và MyBatis cùng cập nhật bảng aggregate root.

Giả sử PurchaseOrder có @Version. Khi gọi repository.save, Spring Data JDBC kiểm tra version hiện tại và tăng version theo cơ chế optimistic locking.

Nếu MyBatis chạy:

~~~sql
UPDATE purchase_orders
SET status = #{status}
WHERE id = #{id}
~~~

thì câu lệnh không kiểm tra version và không tăng version. Một request cũ có thể ghi đè trạng thái mới mà không bị Spring Data JDBC phát hiện.

Nếu bắt buộc cập nhật qua MyBatis, phải tự đưa version vào điều kiện:

~~~sql
UPDATE purchase_orders
SET status = #{status},
    version = version + 1
WHERE id = #{id}
  AND version = #{expectedVersion}
~~~

Sau đó kiểm tra số hàng bị tác động:

- 1: cập nhật thành công.
- 0: ID không tồn tại hoặc version không còn khớp.
- Lớn hơn 1: bất thường nếu id là khóa chính.

Cũng cần reload aggregate trước khi tiếp tục thao tác bằng repository. Object cũ trong bộ nhớ vẫn giữ version cũ và có thể bị optimistic locking từ chối khi save.

Cách an toàn hơn trong phần lớn use case domain là để repository sở hữu mọi thao tác ghi aggregate; MyBatis chỉ đọc projection hoặc bảng báo cáo. Nếu MyBatis phải ghi, hãy coi đó là một đường ghi có hợp đồng riêng và kiểm thử concurrency.

## 10. Aggregate child và quan hệ dữ liệu

Spring Data JDBC quản lý child thuộc aggregate qua mapping như @MappedCollection. Khi save root, framework có thể tạo nhiều thao tác insert/delete/update để đồng bộ collection.

MyBatis không tự biết collection đó là một phần của aggregate root. Mapper SQL chỉ thực hiện statement đã khai báo.

Ví dụ MyBatis xóa một dòng order_lines:

~~~sql
DELETE FROM order_lines
WHERE order_id = #{orderId}
  AND line_no = #{lineNo}
~~~

Nếu object PurchaseOrder trong bộ nhớ vẫn chứa dòng đó, lần repository.save(order) tiếp theo có thể tái tạo dòng hoặc đồng bộ collection theo trạng thái cũ. Ngược lại, SQL trực tiếp có thể bỏ qua invariant như tổng đơn phải bằng tổng các dòng.

Trước khi ghi child bằng MyBatis, cần xác định:

- Child có thuộc vòng đời aggregate root không?
- Repository có thể save lại root sau thao tác mapper không?
- ID/key của child được giữ đúng không?
- Version root có cần tăng không?
- Có cần kiểm tra domain invariant và cập nhật total không?

Nếu child thực sự có vòng đời độc lập, có thể xem lại mô hình aggregate. Không nên dùng MyBatis để né quy tắc sở hữu của aggregate mà không thiết kế lại domain.

## 11. Transaction chung giữa Spring Data JDBC và MyBatis

Một lợi ích của tích hợp Spring là repository JDBC và MyBatis có thể tham gia cùng transaction nếu được cấu hình đúng.

MyBatis-Spring cung cấp SqlSessionTemplate và tích hợp mapper với transaction Spring. Khi Spring Data JDBC và MyBatis dùng cùng DataSource và transaction manager, các câu SQL có thể commit hoặc rollback cùng nhau.

Ví dụ service:

~~~java
@Service
public class OrderWorkflowService {
    private final PurchaseOrderRepository orders;
    private final OrderAuditMapper auditMapper;

    public OrderWorkflowService(
            PurchaseOrderRepository orders,
            OrderAuditMapper auditMapper
    ) {
        this.orders = orders;
        this.auditMapper = auditMapper;
    }

    @Transactional
    public PurchaseOrder approve(Long id) {
        PurchaseOrder current = orders.findById(id).orElseThrow();

        PurchaseOrder approved = new PurchaseOrder(
                current.id(),
                current.version(),
                current.orderNumber(),
                current.customerId(),
                "APPROVED",
                current.total()
        );

        PurchaseOrder saved = orders.save(approved);

        auditMapper.insertApproval(
                saved.id(),
                saved.version(),
                "APPROVED"
        );

        return saved;
    }
}
~~~

Trong ví dụ, Spring Data JDBC cập nhật aggregate; MyBatis ghi audit. Nếu insert audit thất bại và exception làm transaction rollback, update aggregate cũng rollback khi hai công nghệ tham gia cùng transaction vật lý.

### Điều kiện cần có

1. MyBatis SqlSessionFactory và Spring Data JDBC repository dùng cùng DataSource.
2. Transaction manager quản lý DataSource đó.
3. MyBatis được tích hợp qua MyBatis-Spring, thường dùng SqlSessionTemplate hoặc mapper proxy do integration tạo.
4. Service method chạy qua Spring transaction proxy.
5. Không tự mở JDBC connection riêng rồi commit độc lập.
6. Không đặt một mapper vào transaction manager khác mà không chủ đích.

Nếu có nhiều DataSource, chỉ dùng cùng @Transactional không tự tạo transaction nguyên tử giữa tất cả database. Cần transaction manager phù hợp hoặc một kiến trúc nhất quán phân tán.

## 12. MyBatis cache có thể không biết Spring Data JDBC vừa ghi

Đây là một chi phí dễ bị bỏ qua khi dùng hai persistence framework.

MyBatis có local cache theo SqlSession. Mapper statement trong cùng session có thể tái sử dụng kết quả theo cấu hình cache. MyBatis cũng hỗ trợ second-level cache theo mapper namespace khi được bật.

Nếu Spring Data JDBC cập nhật một bảng, MyBatis không tự biết rằng cache của mapper namespace khác cần được invalidated. Ví dụ:

1. MyBatis đọc PurchaseOrder và cache kết quả.
2. Spring Data JDBC cập nhật status của PurchaseOrder.
3. MyBatis đọc lại trong phạm vi cache còn hiệu lực.
4. Kết quả cũ có thể được trả về nếu cache không được xóa theo cách phù hợp.

Tương tự, MyBatis update không tự đồng bộ một cache khác của ứng dụng nếu có.

Cách giảm rủi ro:

- Giữ cache MyBatis ở mức tối thiểu khi cùng bảng có nhiều writer.
- Không bật second-level cache cho dữ liệu thường xuyên thay đổi qua framework khác nếu không có invalidation strategy.
- Cân nhắc flushCache cho statement ghi MyBatis trong namespace liên quan, nhưng lưu ý nó không tự xóa cache của namespace khác.
- Dùng cache ở application layer với invalidation rõ ràng.
- Kiểm tra kết quả đọc sau update trong integration test.
- Nếu cần cache phân tán, thiết kế event/invalidation có transaction semantics phù hợp.

Không nên bật cache chỉ vì query có vẻ đọc nhiều. Đo hiệu năng trước và xác định rõ ai có quyền ghi dữ liệu được cache.

## 13. Transaction và cache không phải cùng một thứ

Transaction bảo đảm tính nguyên tử và isolation của các thao tác database trong transaction manager. Cache là bản sao dữ liệu nằm ngoài hoặc bên trong persistence framework.

Một transaction commit thành công không đồng nghĩa mọi cache trong ứng dụng tự cập nhật. MyBatis cache, application cache, distributed cache và read replica có vòng đời riêng.

Nếu một use case cập nhật qua Spring Data JDBC rồi đọc qua MyBatis, cần kiểm tra:

- Mapper có đang dùng local cache trong cùng SqlSession không?
- Second-level cache có bật không?
- Mapper statement có cache namespace riêng không?
- Cache có được flush khi mapper khác ghi không?
- Có read replica hoặc routing datasource làm dữ liệu chưa cập nhật xuất hiện không?

Giữ cache đơn giản thường rẻ hơn duy trì một hệ thống invalidation phức tạp.

## 14. Generated keys khi dùng MyBatis

Spring Data JDBC có thể trả aggregate đã lưu cùng ID do database sinh. Với MyBatis, mapper cần khai báo cách lấy generated key phù hợp với driver/database.

Ví dụ annotation:

~~~java
@Mapper
public interface CustomerMapper {

    @Insert("""
        INSERT INTO customers(display_name, email)
        VALUES(#{name}, #{email})
        """)
    @Options(
        useGeneratedKeys = true,
        keyProperty = "id",
        keyColumn = "id"
    )
    int insert(CustomerInsertCommand command);
}
~~~

Command có property id để MyBatis gán giá trị được sinh:

~~~java
public class CustomerInsertCommand {
    private Long id;
    private String name;
    private String email;

    // constructors, getters and setters
}
~~~

Tính năng generated keys phụ thuộc JDBC driver/database. Một số DBMS cần sequence hoặc RETURNING/OUTPUT với statement riêng. Hãy xác nhận cách lấy key trên database mục tiêu.

Đừng dùng MAX(id) để lấy ID vừa insert vì có thể lấy ID của transaction khác khi có insert đồng thời.

Cần phân biệt:

- Giá trị trả về của mapper method kiểu int thường là số hàng bị tác động.
- Giá trị id trong command có thể được MyBatis gán qua generated key.
- Hai thông tin này không giống nhau.

## 15. TypeHandler và converter: tránh hai cách biểu diễn dữ liệu

Spring Data JDBC có custom converter; MyBatis có TypeHandler. Hai cơ chế không tự dùng chung.

Ví dụ domain enum:

~~~java
public enum OrderStatus {
    NEW, PAID, SHIPPED
}
~~~

Spring Data JDBC có thể dùng converter để lưu mã N/P/S. MyBatis nếu mặc định lưu tên enum sẽ ghi NEW/PAID/SHIPPED. Khi cả hai đọc cùng cột, một bên có thể không hiểu dữ liệu của bên kia.

Cần thống nhất một quy tắc lưu:

| Domain value | Giá trị vật lý |
|---|---|
| NEW | N |
| PAID | P |
| SHIPPED | S |

Trong MyBatis, TypeHandler chuyển đổi enum sang mã:

~~~java
@MappedTypes(OrderStatus.class)
@MappedJdbcTypes(JdbcType.VARCHAR)
public class OrderStatusTypeHandler
        extends BaseTypeHandler<OrderStatus> {

    @Override
    public void setNonNullParameter(
            PreparedStatement ps,
            int index,
            OrderStatus value,
            JdbcType jdbcType
    ) throws SQLException {
        ps.setString(index, switch (value) {
            case NEW -> "N";
            case PAID -> "P";
            case SHIPPED -> "S";
        });
    }

    @Override
    public OrderStatus getNullableResult(ResultSet rs, String column)
            throws SQLException {
        return fromCode(rs.getString(column));
    }

    @Override
    public OrderStatus getNullableResult(ResultSet rs, int column)
            throws SQLException {
        return fromCode(rs.getString(column));
    }

    @Override
    public OrderStatus getNullableResult(CallableStatement cs, int column)
            throws SQLException {
        return fromCode(cs.getString(column));
    }

    private OrderStatus fromCode(String code) {
        if (code == null) return null;
        return switch (code) {
            case "N" -> OrderStatus.NEW;
            case "P" -> OrderStatus.PAID;
            case "S" -> OrderStatus.SHIPPED;
            default -> throw new IllegalArgumentException(
                    "Unknown order status code: " + code);
        };
    }
}
~~~

Đây là ví dụ TypeHandler minh họa; cần đăng ký TypeHandler trong MyBatis configuration hoặc chỉ định trên mapper/resultMap. Spring Data JDBC converter cũng phải chuyển đổi đúng cùng mã vật lý.

Các kiểu cần thống nhất gồm enum, UUID, JSON, timestamp, timezone, decimal và value object. Một converter hoạt động với repository không đảm bảo MyBatis tự dùng cùng converter.

## 16. Khác biệt dialect và SQL portability

Spring Data JDBC dùng dialect để tạo một số cú pháp SQL như pagination và generated key theo database. MyBatis chạy SQL được khai báo trong mapper; nếu SQL có cú pháp riêng, nhóm phát triển phải quản lý sự khác biệt đó.

Ví dụ pagination:

~~~sql
-- PostgreSQL / MySQL
SELECT id, status
FROM purchase_orders
ORDER BY id
LIMIT #{limit} OFFSET #{offset}
~~~

SQL Server thường dùng dạng:

~~~sql
SELECT id, status
FROM purchase_orders
ORDER BY id
OFFSET #{offset} ROWS FETCH NEXT #{limit} ROWS ONLY
~~~

Nếu ứng dụng chỉ hỗ trợ một DBMS, có thể chấp nhận SQL đặc thù và ghi rõ giả định. Nếu hỗ trợ nhiều DBMS, có thể dùng databaseId trong MyBatis mapper hoặc tách mapper statement theo database:

~~~xml
<select id="search" databaseId="postgresql"
        resultType="PurchaseOrderSummary">
  SELECT id, status
  FROM purchase_orders
  ORDER BY id
  LIMIT #{limit} OFFSET #{offset}
</select>

<select id="search" databaseId="sqlserver"
        resultType="PurchaseOrderSummary">
  SELECT id, status
  FROM purchase_orders
  ORDER BY id
  OFFSET #{offset} ROWS FETCH NEXT #{limit} ROWS ONLY
</select>
~~~

Database ID phải được cấu hình nhất quán với vendor identification trong MyBatis. Cách tách này làm tăng số statement phải kiểm thử, nhưng giữ khác biệt SQL ở đúng nơi.

Không nên tuyên bố hỗ trợ nhiều database nếu chỉ test mapper trên một engine.

## 17. Chi phí schema evolution và migration

Khi schema thay đổi, cả Spring Data JDBC mapping lẫn MyBatis mapper phải được cập nhật.

Ví dụ đổi cột display_name thành full_name:

- Entity cần cập nhật @Column hoặc naming convention.
- Derived query có thể cần đổi property.
- MyBatis XML/annotation cần đổi tên cột và alias.
- ResultMap cần cập nhật nếu mapping phụ thuộc cột cũ.
- TypeHandler có thể cần thay đổi nếu kiểu vật lý đổi.
- Migration phải bảo toàn dữ liệu và constraint.
- Test fixture và integration test cần cập nhật.

Nếu có nhiều mapper tự lặp lại cùng tên cột hoặc resultMap, chi phí sửa đổi tăng theo số bản sao.

Cách giảm:

- Dùng naming convention ổn định.
- Tránh SELECT *.
- Dùng SQL fragment cho các đoạn lặp lại có ý nghĩa.
- Giữ DTO và resultMap theo mục đích rõ.
- Tìm kiếm mapper references khi thay đổi schema.
- Chạy migration từ phiên bản trước trên database test, không chỉ tạo schema mới.

## 18. Dynamic SQL và số lượng nhánh cần bảo trì

Một mapper có 8 bộ lọc tùy chọn có thể tạo rất nhiều hình dạng SQL khác nhau. Không nhất thiết phải test mọi tổ hợp toán học, nhưng cần chọn test đại diện:

- Không có bộ lọc.
- Chỉ có từng bộ lọc quan trọng.
- Kết hợp các điều kiện AND/OR.
- Giá trị null và chuỗi rỗng.
- Danh sách IN rỗng và có phần tử.
- Sort hợp lệ và sort không hợp lệ.
- Page đầu, page sâu và page rỗng.

Đặc biệt, foreach với danh sách rỗng cần xử lý rõ. Một điều kiện IN rỗng có thể không hợp lệ với database. Dùng choose/if để quyết định hành vi khi danh sách rỗng: bỏ điều kiện, trả không kết quả hoặc từ chối request theo contract nghiệp vụ.

Không để một mapper statement chứa mọi logic lọc, sort, phân trang, join, permission và cập nhật. Chia statement theo use case để SQL dễ hiểu.

## 19. Kiểm soát SQL injection

MyBatis cung cấp hai cách thay tham số thường được nhắc đến:

- #{value}: bind giá trị qua PreparedStatement.
- Cú pháp thay chuỗi trực tiếp bằng dấu đô la và ngoặc nhọn: chèn nội dung vào câu SQL.

Dùng #{...} cho giá trị:

~~~xml
WHERE customer_id = #{customerId}
~~~

Không dùng cú pháp thay chuỗi trực tiếp cho dữ liệu người dùng:

~~~xml
ORDER BY sortColumn direction
~~~

Nếu cần thay identifier, dùng whitelist ánh xạ từ lựa chọn đã kiểm tra sang tên cột cố định. Không dùng regex đơn giản như chỉ cho chữ và số làm cơ chế duy nhất nếu vẫn cho phép identifier tùy ý; whitelist rõ ràng dễ kiểm soát hơn.

SQL injection không chỉ là vấn đề MyBatis. Mọi câu SQL tự viết qua JdbcTemplate hoặc repository query đều cần phân biệt parameter value với SQL structure.

## 20. Chi phí vận hành và quan sát

Thêm MyBatis làm tăng một số khía cạnh vận hành:

- Cần biết mapper statement nào đang chạy khi truy vấn chậm.
- Cần theo dõi SQL và parameter bind mà không làm lộ dữ liệu nhạy cảm.
- Cần thống nhất logging giữa Spring Data JDBC và MyBatis.
- Cần quản lý cache riêng.
- Cần theo dõi connection pool và transaction duration khi một service gọi nhiều mapper.
- Cần xử lý timeout và exception translation phù hợp.

Log SQL hữu ích khi debug nhưng parameter có thể chứa email, token, địa chỉ hoặc thông tin thanh toán. Không bật log bind nhạy cảm trên production nếu không có chính sách bảo vệ phù hợp.

Nên dùng metrics/tracing để quan sát thời gian query, số hàng trả về, lỗi và pool usage. Đặt tên mapper statement dễ nhận diện để truy vấn chậm có thể truy ngược về use case.

## 21. Kiểm thử tích hợp giữa hai công nghệ

Unit test mapper chỉ kiểm tra một phần logic. Khi tích hợp Spring Data JDBC với MyBatis, cần test trên cùng cấu hình DataSource và transaction manager.

Các tình huống quan trọng:

1. Lưu aggregate qua repository rồi đọc DTO qua MyBatis.
2. MyBatis ghi audit trong cùng transaction với repository save.
3. Cố ý làm mapper insert thất bại và xác nhận aggregate update rollback.
4. Kiểm tra version khi MyBatis cập nhật aggregate versioned.
5. Kiểm tra converter/TypeHandler đọc và ghi cùng giá trị.
6. Kiểm tra generated key với đúng JDBC driver.
7. Kiểm tra cache không trả dữ liệu cũ sau khi framework còn lại ghi.
8. Kiểm tra pagination và sort trên DBMS mục tiêu.
9. Chạy migration từ schema phiên bản cũ.
10. Kiểm tra SQL injection ở các tham số dynamic.

Ví dụ test rollback khái quát:

~~~java
@SpringBootTest
class OrderWorkflowIntegrationTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Autowired
    OrderWorkflowService service;

    @Test
    void rollsBackRepositoryWriteWhenMapperFails() {
        PurchaseOrder order = orders.save(newOrder());

        assertThrows(RuntimeException.class, () ->
                service.approveAndFailAudit(order.id())
        );

        PurchaseOrder reloaded = orders.findById(order.id()).orElseThrow();
        assertEquals("NEW", reloaded.status());
    }
}
~~~

Test này cần database thật hoặc Testcontainers, transaction manager và mapper integration được cấu hình đúng. Nếu test method tự mở transaction bao quanh toàn bộ test, cần hiểu transaction test đó tương tác thế nào với transaction của service để tránh kết luận sai.

## 22. Đo hiệu năng trước khi chọn MyBatis vì lý do tốc độ

MyBatis không mặc nhiên nhanh hơn Spring Data JDBC. Hai công cụ cuối cùng đều dùng JDBC driver và database. Hiệu năng phụ thuộc SQL, execution plan, index, số round trip, số cột đọc, mapping và transaction.

MyBatis có thể cải thiện use case khi:

- Query hiện tại tải cả aggregate nhưng màn hình chỉ cần vài cột.
- Có N+1 query do cách đọc dữ liệu chưa phù hợp.
- Cần join/projection trong một lần truy vấn.
- Cần bulk update thay vì lưu từng aggregate.
- SQL được tối ưu dựa trên execution plan thực tế.

Nhưng MyBatis có thể chậm hoặc tốn tài nguyên hơn nếu:

- SQL trả quá nhiều cột/hàng.
- ResultMap dựng object graph lớn.
- Dynamic SQL tạo query plan khó tối ưu.
- Cache làm dữ liệu cũ hoặc tốn bộ nhớ.
- Mapper gọi nhiều query tuần tự.
- Transaction giữ connection lâu.

Đo query trước/sau với dữ liệu gần production, cùng database, index, driver và concurrency. Không chọn thêm framework chỉ dựa trên giả định về tốc độ.

## 23. Khi nào nên dùng MyBatis?

MyBatis thường đáng cân nhắc khi có một hoặc nhiều điều kiện:

- Truy vấn đọc có join/projection phức tạp.
- Cần SQL đặc thù của database và chấp nhận khóa vào DBMS đó.
- Có legacy SQL đã được kiểm chứng cần giữ lại.
- Cần kiểm soát chính xác statement và result mapping.
- Bulk operation có lợi ích rõ ràng và đã thiết kế version/audit/invariant.
- Team có kỹ năng đọc, review, tối ưu và kiểm thử SQL.
- Số mapper có thể được quản lý bằng quy ước package, naming và ownership.

Không nên thêm MyBatis chỉ vì một derived query hơi dài hoặc vì muốn viết mọi câu CRUD bằng SQL. Hãy cân nhắc Criteria/Query của Spring Data JDBC, derived query hoặc @Query trước nếu chúng diễn đạt use case rõ ràng và đủ khả năng.

## 24. Khi nào chi phí bảo trì lớn hơn lợi ích?

Cân nhắc không dùng hoặc giới hạn MyBatis nếu:

- Phần lớn query chỉ là findById, findByStatus hoặc CRUD đơn giản.
- Mapper trùng lặp nhiều logic với repository.
- Không có integration test trên database mục tiêu.
- Team không có quy trình review SQL.
- Cùng aggregate bị ghi từ nhiều nơi mà không có quy tắc version.
- Nhiều DBMS được hỗ trợ nhưng mapper chứa cú pháp vendor-specific không có biến thể.
- Cache không có invalidation strategy.
- TypeHandler và Spring Data converter biểu diễn cùng một property khác nhau.
- Mỗi thay đổi schema đòi sửa nhiều mapper và resultMap thủ công.
- Không có người chịu trách nhiệm duy trì mapper.

Một dấu hiệu cảnh báo là cùng một câu truy vấn hoặc cùng một quy tắc nghiệp vụ xuất hiện trong repository, XML mapper và service. Khi đó chi phí sửa đổi sẽ tăng và các đường code có thể lệch nhau theo thời gian.

## 25. Ma trận quyết định theo use case

| Use case | Công cụ nên bắt đầu | Lý do |
|---|---|---|
| Tạo/sửa aggregate root và child | Spring Data JDBC repository | Framework quản lý aggregate mapping và version |
| Tìm theo một vài property | Derived query | Ít SQL thủ công, dễ đọc |
| Bộ lọc động vừa phải trên aggregate | Criteria + JdbcAggregateTemplate | Dùng mapping Spring Data |
| Truy vấn join/projection cho màn hình | MyBatis read mapper | SQL và DTO rõ ràng |
| Báo cáo tổng hợp nhiều bảng | MyBatis hoặc SQL/reporting layer | Có thể dùng window/group/CTE |
| Bulk update có quy tắc rõ | MyBatis/JdbcTemplate có kiểm soát | Tùy biến SQL, nhưng phải xử lý version/audit |
| Ghi audit cùng transaction | Repository hoặc MyBatis mapper | Cả hai có thể tham gia transaction nếu cấu hình chung |
| Cập nhật child thuộc aggregate | Spring Data JDBC | Giữ ownership và đồng bộ collection |
| Query đặc thù DBMS | MyBatis | Chấp nhận SQL phụ thuộc dialect |
| CRUD đơn giản trên bảng legacy không phải aggregate | MyBatis có thể phù hợp | Mapper SQL tường minh có thể là mô hình đơn giản hơn |

Không bắt buộc mọi ứng dụng phải dùng cả hai công cụ. Nếu Spring Data JDBC đáp ứng đủ use case, thêm MyBatis chỉ làm tăng số khái niệm và quy tắc cần duy trì.

## 26. Quy trình tích hợp MyBatis có kiểm soát

Khi quyết định thêm MyBatis, thực hiện theo các bước:

1. **Chọn use case cụ thể**: nêu rõ query hoặc thao tác nào không phù hợp với repository/template.
2. **Chọn ownership**: quyết định mapper chỉ đọc hay được phép ghi; xác định ai sở hữu aggregate.
3. **Cấu hình DataSource chung**: dùng Spring-managed DataSource và transaction manager nếu cần transaction chung.
4. **Tổ chức mapper**: package, namespace, tên statement và XML/annotation nhất quán.
5. **Thiết kế DTO/resultMap**: chỉ lấy cột cần thiết, alias rõ ràng và không phụ thuộc SELECT *.
6. **Chuẩn hóa type mapping**: đồng bộ MyBatis TypeHandler với Spring Data converters.
7. **Kiểm soát dynamic SQL**: bind value bằng #{...}, whitelist identifier và xử lý list rỗng.
8. **Thiết kế version/auditing**: nếu mapper ghi aggregate, tự thực hiện optimistic locking và audit.
9. **Kiểm soát cache**: chỉ bật cache khi có invalidation strategy giữa mọi writer.
10. **Kiểm thử**: transaction rollback, generated keys, type mapping, pagination và migration.
11. **Đo hiệu năng**: xác nhận lợi ích bằng dữ liệu và execution plan.
12. **Ghi lại giả định DBMS**: nếu SQL đặc thù, nêu rõ database/driver/version được hỗ trợ.

## 27. Các lỗi thường gặp khi phối hợp Spring Data JDBC và MyBatis

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Mapper đọc dữ liệu cũ sau repository save | MyBatis cache không được invalidated bởi Spring Data JDBC | Giảm cache hoặc thiết kế invalidation rõ |
| Repository không phát hiện mapper update đồng thời | MyBatis không kiểm tra/tăng @Version | Thêm version vào WHERE và tăng version |
| Child bị mất sau lần save root | MyBatis sửa bảng child trong khi aggregate object cũ | Giữ root là writer hoặc reload và đồng bộ aggregate |
| Audit không rollback cùng aggregate | Hai công nghệ dùng DataSource/transaction manager khác nhau | Dùng cùng Spring transaction infrastructure |
| Mapper insert không có ID | Chưa cấu hình generated keys hoặc driver không hỗ trợ theo cách đó | Cấu hình useGeneratedKeys/keyProperty hoặc strategy theo DB |
| Enum không đọc đúng | TypeHandler và converter khác quy ước | Dùng chung mã lưu và test hai chiều |
| SQL chạy trên một DB nhưng lỗi DB khác | Mapper chứa cú pháp riêng | Tách databaseId hoặc strategy riêng, test từng DB |
| Dynamic sort có nguy cơ SQL injection | Dùng thay chuỗi trực tiếp với đầu vào không tin cậy | Whitelist identifier, dùng #{...} cho value |
| DTO thiếu dữ liệu hoặc null bất ngờ | Alias/resultMap không khớp | Kiểm tra cột, constructor và nullability |
| Nhiều mapper cùng sửa một logic | Không có ownership và quy ước | Tách read/write, gom logic dùng chung |
| Query nhanh ở local nhưng chậm production | Khác dữ liệu, index, driver hoặc execution plan | Đo trên DBMS và dữ liệu gần production |

## 28. Nguyên tắc ghi nhớ

- Spring Data JDBC phù hợp với persistence theo aggregate; MyBatis phù hợp khi cần kiểm soát SQL và mapping kết quả tường minh.
- Dùng MyBatis khi lợi ích cụ thể của join, projection, bulk SQL hoặc database-specific query lớn hơn chi phí mapper và test.
- Ưu tiên một đường ghi chuẩn cho mỗi aggregate; tránh để repository và mapper cùng ghi mà không có quy tắc version/audit/child.
- MyBatis TypeHandler và Spring Data custom converter là hai cơ chế riêng; phải thống nhất giá trị vật lý.
- Mapper SQL không tự áp dụng optimistic locking, aggregate lifecycle, callbacks hoặc auditing của Spring Data JDBC.
- Dùng chung DataSource và transaction manager để hai công nghệ tham gia cùng transaction Spring.
- MyBatis cache không tự biết Spring Data JDBC đã thay đổi dữ liệu; cache cần invalidation rõ ràng.
- Dùng #{...} để bind value; whitelist identifier và tránh thay chuỗi trực tiếp với dữ liệu không tin cậy.
- SQL trong mapper có thể phụ thuộc DBMS; dùng databaseId hoặc strategy riêng khi hỗ trợ nhiều engine.
- Kiểm thử transaction rollback, generated key, mapping, cache và pagination trên database mục tiêu.
- Đo hiệu năng trước khi kết luận MyBatis nhanh hơn.
- Giữ mapper nhỏ theo use case và tài liệu hóa giả định SQL để giảm chi phí bảo trì.

MyBatis bổ sung khả năng kiểm soát SQL cho ứng dụng Spring Data JDBC, đặc biệt với join, projection, báo cáo và câu lệnh đặc thù. Giá trị đó chỉ bền vững khi nhóm phát triển giữ ranh giới rõ giữa aggregate persistence và SQL mapper, đồng bộ type mapping, quản lý transaction/cache và kiểm thử các khác biệt theo database. Hãy thêm MyBatis cho những use case mà quyền kiểm soát SQL giải quyết được một nhu cầu cụ thể; mỗi mapper mới cần có chủ sở hữu, contract và cách kiểm chứng tương xứng với chi phí bảo trì mà nó mang lại.

## Tài liệu tham khảo

- [MyBatis 3 — Getting Started](https://mybatis.org/mybatis-3/getting-started.html)
- [MyBatis 3 — Mapper XML Files](https://mybatis.org/mybatis-3/sqlmap-xml.html)
- [MyBatis 3 — Dynamic SQL](https://mybatis.org/mybatis-3/dynamic-sql.html)
- [MyBatis-Spring Reference](https://mybatis.org/spring/)
- [MyBatis-Spring — Transactions](https://mybatis.org/spring/transactions.html)
- [MyBatis-Spring — SqlSessionTemplate](https://mybatis.org/spring/sqlsession.html)
- [Spring Data Relational Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html)

