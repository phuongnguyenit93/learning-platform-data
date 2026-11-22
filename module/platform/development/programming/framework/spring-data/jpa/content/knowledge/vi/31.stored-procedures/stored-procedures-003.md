# Định nghĩa @NamedStoredProcedureQuery và tham số thủ tục

Stored procedure là thủ tục được định nghĩa và thực thi trong database. Spring Data JPA cho phép gọi thủ tục này qua repository; Jakarta Persistence cung cấp cơ chế khai báo ánh xạ bằng @NamedStoredProcedureQuery hoặc tạo StoredProcedureQuery trực tiếp qua EntityManager.

Khi tích hợp, cần phân biệt hai tên thường dễ nhầm:

- **Tên JPA đã đăng ký:** thuộc tính name của @NamedStoredProcedureQuery, dùng để tham chiếu cấu hình trong ứng dụng.
- **Tên thủ tục trong database:** thuộc tính procedureName, là tên procedure thực tế mà database cung cấp.

Ngoài ra, cần khai báo đúng tham số IN, OUT, INOUT hoặc REF_CURSOR, đúng kiểu Java và đúng cách ánh xạ kết quả. Ví dụ dưới đây sử dụng một thủ tục đóng đơn hàng và trả về mã kết quả.

## 1. Stored procedure là gì?

Stored procedure là một chương trình được lưu trong database và có thể được gọi bằng tên. Thủ tục có thể nhận tham số đầu vào, thay đổi dữ liệu, trả tham số đầu ra hoặc trả một tập kết quả.

Ví dụ về thủ tục MySQL:

~~~sql
DELIMITER //

CREATE PROCEDURE close_purchase_order(
    IN p_order_id BIGINT,
    OUT p_result VARCHAR(30)
)
BEGIN
    DECLARE v_status VARCHAR(30);
    DECLARE v_not_found BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_not_found = TRUE;

    -- Call inside an active transaction; purchase_orders must use InnoDB.
    -- The caller commits or rolls back after this procedure returns.
    SELECT status
      INTO v_status
      FROM purchase_orders
     WHERE id = p_order_id
     FOR UPDATE;

    IF v_not_found THEN
        SET p_result = 'NOT_FOUND';
    ELSEIF v_status = 'CLOSED' THEN
        SET p_result = 'ALREADY_CLOSED';
    ELSE
        UPDATE purchase_orders
           SET status = 'CLOSED'
         WHERE id = p_order_id;

        SET p_result = 'CLOSED';
    END IF;
END //

DELIMITER ;
~~~

Thủ tục khóa dòng đơn hàng bằng SELECT ... FOR UPDATE trước khi đọc trạng thái. Handler NOT FOUND đánh dấu trường hợp không có bản ghi; nếu đơn hàng đã tồn tại và trạng thái là CLOSED, thủ tục trả ALREADY_CLOSED; nếu trạng thái chưa CLOSED, thủ tục cập nhật và trả CLOSED. Bảng purchase_orders cần dùng InnoDB và lệnh CALL phải chạy trong transaction đang hoạt động (ví dụ từ phương thức service có @Transactional). Procedure không tự START TRANSACTION hoặc COMMIT để transaction do ứng dụng quản lý giữ khóa cho đến khi kết thúc. Cú pháp tạo procedure thay đổi theo hệ quản trị cơ sở dữ liệu; đoạn trên là cú pháp MySQL, không phải SQL dùng chung cho mọi database.

Trong ứng dụng Java, ta muốn gọi thủ tục mà không phải tự quản lý JDBC CallableStatement ở mọi nơi. JPA và Spring Data JPA cung cấp API để khai báo tham số, truyền giá trị và nhận kết quả.

## 2. Khai báo @NamedStoredProcedureQuery

@NamedStoredProcedureQuery là annotation của Jakarta Persistence dùng để đăng ký một ánh xạ stored procedure có tên trong persistence unit. Annotation thường được đặt trên entity class.

Ví dụ:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.NamedStoredProcedureQuery;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureParameter;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
@NamedStoredProcedureQuery(
    name = "PurchaseOrder.closeOrder",
    procedureName = "close_purchase_order",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_order_id",
            type = Long.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_result",
            type = String.class
        )
    }
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    // Các thuộc tính khác của đơn hàng
}
~~~

Ý nghĩa từng thuộc tính:

- name = "PurchaseOrder.closeOrder": tên JPA dùng để tìm cấu hình đã đăng ký. Đây không phải tên procedure trong database.
- procedureName = "close_purchase_order": tên procedure thực tế trong database.
- parameters: danh sách tham số được đăng ký theo thứ tự khai báo.
- mode: hướng truyền dữ liệu của tham số.
- name: tên tham số phía procedure, khi provider và database hỗ trợ binding theo tên.
- type: kiểu Java tương ứng với tham số.

Tên JPA trong thuộc tính name cần duy nhất trong phạm vi persistence unit. Có thể đặt annotation trên entity khác nếu phù hợp với mô hình, nhưng đặt trên entity liên quan thường giúp dễ tìm và bảo trì.

## 3. Các loại tham số của stored procedure

Jakarta Persistence định nghĩa các giá trị ParameterMode sau:

| Chế độ | Ý nghĩa | Cách sử dụng |
|---|---|---|
| IN | Tham số đầu vào | Ứng dụng truyền giá trị cho procedure |
| OUT | Tham số đầu ra | Procedure gán giá trị để ứng dụng đọc |
| INOUT | Vừa vào vừa ra | Ứng dụng truyền giá trị ban đầu, procedure cập nhật giá trị |
| REF_CURSOR | Con trỏ kết quả | Procedure trả về tập kết quả qua cursor; phụ thuộc provider/database |

### 3.1. IN

IN là tham số truyền từ Java vào database. Ví dụ p_order_id trong thủ tục close_purchase_order nhận ID đơn hàng.

Khi khai báo:

~~~java
@StoredProcedureParameter(
    mode = ParameterMode.IN,
    name = "p_order_id",
    type = Long.class
)
~~~

ứng dụng phải cung cấp giá trị trước khi thực thi procedure.

### 3.2. OUT

OUT là tham số do procedure tạo ra. Ví dụ p_result trả về CLOSED hoặc NOT_FOUND. Ứng dụng đọc giá trị sau khi procedure thực thi thành công.

~~~java
@StoredProcedureParameter(
    mode = ParameterMode.OUT,
    name = "p_result",
    type = String.class
)
~~~

OUT không phải giá trị đầu vào; không truyền một giá trị nghiệp vụ cho nó như với IN.

### 3.3. INOUT

INOUT cho phép gửi giá trị ban đầu và nhận giá trị đã được procedure cập nhật. Ví dụ procedure nhận một số nguyên, tăng lên một đơn vị rồi trả kết quả qua chính tham số đó.

~~~java
@StoredProcedureParameter(
    mode = ParameterMode.INOUT,
    name = "p_counter",
    type = Integer.class
)
~~~

Với INOUT, ứng dụng phải đặt giá trị ban đầu trước khi gọi. Sau khi thực thi, ứng dụng đọc giá trị đầu ra từ cùng tham số.

### 3.4. REF_CURSOR

REF_CURSOR biểu diễn một cursor chứa tập kết quả. Đây là cách thường gặp ở một số database như Oracle và PostgreSQL, nhưng khả năng hỗ trợ và cách đăng ký cụ thể phụ thuộc database, JDBC driver và JPA provider.

Có thể khai báo bằng ParameterMode.REF_CURSOR khi stack persistence hỗ trợ. Không nên giả định mọi database đều hỗ trợ REF_CURSOR hoặc cùng một cú pháp khai báo.

Nếu procedure trả về các hàng dữ liệu, cần xác định cách ánh xạ kết quả thành entity hoặc DTO. Jakarta Persistence cung cấp resultClasses và resultSetMappings trong @NamedStoredProcedureQuery để mô tả kết quả. Với procedure trả nhiều result set hoặc cursor, cần kiểm tra hỗ trợ của provider và driver đang dùng.

## 4. Gọi named stored procedure bằng Spring Data JPA

Sau khi khai báo @NamedStoredProcedureQuery, repository có thể tham chiếu tên JPA bằng @Procedure(name = ...).

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.query.Procedure;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Procedure(name = "PurchaseOrder.closeOrder")
    String closeOrder(@Param("p_order_id") Long orderId);
}
~~~

Trong ví dụ:

- name của @Procedure trỏ đến tên JPA PurchaseOrder.closeOrder đã đăng ký trên entity.
- @Param("p_order_id") ánh xạ tham số phương thức vào tham số IN có tên tương ứng.
- Giá trị trả về String nhận tham số OUT p_result.

Spring Data JPA gọi procedure và ánh xạ tham số đầu ra đơn theo kiểu trả về của phương thức. Kiểu trả về cần tương thích với kiểu Java được khai báo cho tham số OUT.

Có thể gọi repository từ service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public String closeOrder(Long orderId) {
        return repository.closeOrder(orderId);
    }
}
~~~

Transaction ở service giúp xác định ranh giới giao dịch của ca sử dụng. Cấu hình transaction và hành vi commit thực tế còn phụ thuộc cách procedure được gọi, database và transaction manager. Nếu procedure thực hiện cập nhật dữ liệu, hãy kiểm tra quyền thực thi, quyền cập nhật và hành vi rollback trong database mục tiêu.

## 5. Phân biệt name và procedureName trong @Procedure

Spring Data JPA có thể gọi procedure trực tiếp mà không cần khai báo @NamedStoredProcedureQuery trên entity.

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Procedure(procedureName = "close_purchase_order")
    String closeOrder(@Param("p_order_id") Long orderId);
}
~~~

Hai cách có ý nghĩa khác nhau:

- @Procedure(name = "PurchaseOrder.closeOrder") tham chiếu named stored procedure query được đăng ký bằng @NamedStoredProcedureQuery.
- @Procedure(procedureName = "close_purchase_order") chỉ định trực tiếp tên procedure trong database.
- Thuộc tính value của @Procedure là alias cho procedureName trong Spring Data JPA.

Nếu đã dùng named mapping, cách tham chiếu qua name giúp giữ khai báo tham số tập trung trên entity. Nếu chỉ có một thao tác đơn giản, gọi trực tiếp procedureName có thể ngắn gọn hơn.

Không nhầm name trong @Procedure với procedureName. Một bên là tên cấu hình JPA trong ứng dụng; bên kia là tên đối tượng procedure thực tế trong database.

## 6. Procedure có nhiều tham số OUT

Một procedure có thể có nhiều tham số OUT, ví dụ trả về mã trạng thái và số dòng bị ảnh hưởng. Trong Spring Data JPA, khi cần nhận nhiều giá trị đầu ra, phương thức repository có thể trả về Map<String, Object> nếu named procedure mapping và provider hỗ trợ cách ánh xạ đó.

Ví dụ khai báo:

~~~java
@NamedStoredProcedureQuery(
    name = "PurchaseOrder.closeOrderWithDetails",
    procedureName = "close_purchase_order_details",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_order_id",
            type = Long.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_result",
            type = String.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_affected_rows",
            type = Integer.class
        )
    }
)
~~~

Repository:

~~~java
@Procedure(name = "PurchaseOrder.closeOrderWithDetails")
Map<String, Object> closeOrderWithDetails(
        @Param("p_order_id") Long orderId);
~~~

Map chứa các tham số OUT được ánh xạ theo tên mà provider trả về. Cần kiểm tra tên key thực tế trong môi trường database/driver đang dùng và tránh giả định mọi provider đều chuẩn hóa chữ hoa/chữ thường giống nhau.

Nếu procedure chỉ có một tham số OUT, trả về kiểu cụ thể như String, Integer hoặc Long thường dễ dùng hơn Map. Chỉ dùng Map khi thực sự cần nhiều giá trị đầu ra.

## 7. Gọi procedure động bằng EntityManager

Khi tên procedure hoặc tham số được quyết định tại runtime, có thể dùng StoredProcedureQuery thay vì khai báo named mapping cố định.

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureQuery;
import org.springframework.stereotype.Repository;

@Repository
public class PurchaseOrderProcedureRepository {

    private final EntityManager entityManager;

    public PurchaseOrderProcedureRepository(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    public String closeOrder(Long orderId) {
        StoredProcedureQuery query =
                entityManager.createStoredProcedureQuery(
                        "close_purchase_order");

        query.registerStoredProcedureParameter(
                "p_order_id", Long.class, ParameterMode.IN);
        query.registerStoredProcedureParameter(
                "p_result", String.class, ParameterMode.OUT);

        query.setParameter("p_order_id", orderId);
        query.execute();

        return (String) query.getOutputParameterValue("p_result");
    }
}
~~~

Trình tự thực hiện:

1. Tạo StoredProcedureQuery bằng tên procedure trong database.
2. Đăng ký từng tham số với tên hoặc vị trí, kiểu Java và mode.
3. Gán giá trị cho tham số IN hoặc INOUT.
4. Gọi execute().
5. Đọc giá trị OUT hoặc INOUT sau khi procedure thực thi.

Một số database/driver không hỗ trợ binding tham số theo tên đồng nhất. Khi đó, hãy đăng ký theo vị trí và bảo đảm thứ tự khớp chính xác với chữ ký procedure. Khả năng hỗ trợ tham số tên và cursor cần được kiểm tra với provider/driver thực tế.

## 8. Ánh xạ result set trả về từ procedure

Procedure có thể trả về một tập hàng thay vì chỉ có tham số OUT. Với JPA, @NamedStoredProcedureQuery có thể khai báo resultClasses hoặc resultSetMappings.

Ví dụ khung khai báo khi procedure trả về các hàng tương ứng entity PurchaseOrder:

~~~java
@NamedStoredProcedureQuery(
    name = "PurchaseOrder.findOpenOrders",
    procedureName = "find_open_orders",
    resultClasses = PurchaseOrder.class
)
~~~

Khi result set không khớp trực tiếp entity, có thể dùng @SqlResultSetMapping để ánh xạ cột sang entity, constructor DTO hoặc scalar result theo khả năng của provider.

Đối với procedure trả nhiều result set, REF_CURSOR hoặc kết quả trộn giữa result set và OUT parameters, cần xem tài liệu của database, JDBC driver và Hibernate version đang sử dụng. Không nên giả định một phương thức repository có thể tự động ánh xạ mọi cấu trúc kết quả phức tạp.

## 9. Các lưu ý quan trọng khi sử dụng

### 9.1. Đồng bộ persistence context sau khi procedure cập nhật dữ liệu

Stored procedure chạy trực tiếp trong database và có thể thay đổi dữ liệu bên dưới JPA. Nếu entity tương ứng đã được load và đang được quản lý trong persistence context, trạng thái trong bộ nhớ có thể cũ so với database.

Ví dụ: entity PurchaseOrder đã được load với status = PENDING. Procedure cập nhật status thành CLOSED. Object Java đang được quản lý có thể vẫn giữ giá trị PENDING.

Có thể xử lý bằng cách:

- Gọi EntityManager.refresh(entity) để đọc lại một entity cụ thể.
- Gọi EntityManager.clear() khi cần loại bỏ toàn bộ entity đang được quản lý, sau đó tải lại khi cần.
- Thiết kế luồng gọi procedure trước khi load entity nếu phù hợp.

Không gọi clear() một cách tùy tiện vì thao tác này detach tất cả entity trong persistence context; các thay đổi chưa flush có thể không còn được quản lý theo cách mong đợi. Hãy xác định rõ thứ tự flush, gọi procedure và refresh/clear.

### 9.2. Kiểu dữ liệu và giá trị NULL

Kiểu Java khai báo trong @StoredProcedureParameter phải tương thích với kiểu tham số của database. Ví dụ:

- BIGINT thường ánh xạ với Long.
- INTEGER thường ánh xạ với Integer.
- VARCHAR thường ánh xạ với String.
- DECIMAL/NUMERIC thường ánh xạ với BigDecimal.
- DATE/TIMESTAMP cần chọn kiểu Java phù hợp với JDBC driver và mapping của ứng dụng.

Cần kiểm tra quy tắc chuyển đổi kiểu, độ chính xác số, múi giờ và khả năng nhận NULL. Với tham số OUT có thể trả NULL, kiểu wrapper như Integer, Long phù hợp hơn kiểu primitive.

### 9.3. Tham số tên và tham số vị trí

Khi dùng tên tham số, tên trong @StoredProcedureParameter và @Param phải khớp với tên procedure theo cách provider/driver hỗ trợ. Một số hệ quản trị hoặc driver có giới hạn về named binding; dùng vị trí là phương án thay thế khi cần tính tương thích.

Thứ tự đăng ký tham số phải nhất quán với định nghĩa procedure nếu gọi theo vị trí. Không tự đổi thứ tự tham số IN, OUT hoặc INOUT.

### 9.4. Quyền database và transaction

Tài khoản database của ứng dụng cần có quyền EXECUTE procedure và các quyền dữ liệu mà procedure yêu cầu. Nếu procedure thay đổi nhiều bảng, hãy kiểm tra transaction và rollback bằng chính database mục tiêu.

Không phải mọi procedure đều phù hợp chạy trong một transaction do ứng dụng quản lý; một số database procedure có thể có lệnh điều khiển transaction riêng hoặc hành vi đặc biệt. Hãy thiết kế transaction boundary theo hệ quản trị và quy tắc nghiệp vụ.

### 9.5. Tránh ghép tên procedure từ dữ liệu không tin cậy

Tên procedure, tên tham số và cấu trúc SQL nên là cấu hình cố định hoặc được kiểm soát. Giá trị đầu vào của người dùng phải được bind qua tham số, không ghép trực tiếp vào chuỗi SQL. Điều này giúp giảm nguy cơ SQL injection và lỗi cú pháp.

## 10. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
|---|---|---|
| Không tìm thấy named procedure | Sai name trong @Procedure hoặc tên JPA chưa đăng ký | Đối chiếu name với @NamedStoredProcedureQuery.name |
| Procedure không tồn tại | Sai procedureName hoặc schema | Kiểm tra tên, schema và quyền EXECUTE |
| Không bind được tham số | Sai tên, sai thứ tự hoặc driver không hỗ trợ named binding | So khớp chữ ký procedure; thử binding theo vị trí |
| Sai kiểu tham số | Java type không tương thích kiểu SQL | Kiểm tra metadata và kiểu JDBC |
| Không đọc được OUT | Sai mode, tên tham số hoặc đọc trước execute() | Đăng ký OUT/INOUT đúng và đọc sau execute() |
| Không ánh xạ được result set | Thiếu resultClasses/resultSetMappings hoặc khác cấu trúc cột | Kiểm tra result mapping và hỗ trợ provider |
| Entity hiển thị dữ liệu cũ | Procedure cập nhật ngoài cơ chế dirty checking | Refresh entity hoặc clear persistence context có chủ đích |

## 11. Quy trình triển khai và kiểm thử

1. Tạo procedure trong database và kiểm tra thủ công bằng công cụ SQL.
2. Ghi lại chữ ký procedure: tên, thứ tự tham số, kiểu dữ liệu và mode IN/OUT/INOUT.
3. Khai báo @NamedStoredProcedureQuery trên entity hoặc dùng EntityManager nếu cần gọi động.
4. Ánh xạ tham số với @StoredProcedureParameter, chọn đúng kiểu Java.
5. Tạo repository method bằng @Procedure(name = ...) hoặc @Procedure(procedureName = ...).
6. Gọi từ service với transaction phù hợp.
7. Kiểm thử giá trị trả về, tác động dữ liệu, NULL, trường hợp không tìm thấy bản ghi và rollback khi có lỗi.
8. Nếu procedure cập nhật entity đang được quản lý, kiểm tra persistence context sau lời gọi.

Một kiểm thử tích hợp nên xác nhận cả kết quả OUT lẫn trạng thái thực tế trong database. Chỉ kiểm tra giá trị trả về là chưa đủ nếu procedure còn thực hiện cập nhật dữ liệu.

## Kết luận

@NamedStoredProcedureQuery đăng ký một ánh xạ stored procedure có tên trong JPA; procedureName trỏ đến thủ tục thật trong database, còn name là khóa tham chiếu từ ứng dụng. @StoredProcedureParameter mô tả tên, kiểu và hướng truyền dữ liệu của từng tham số.

Spring Data JPA có thể gọi named mapping bằng @Procedure(name = ...), gọi trực tiếp bằng @Procedure(procedureName = ...), hoặc dùng StoredProcedureQuery qua EntityManager khi cần linh hoạt. Để tích hợp ổn định, hãy kiểm tra chữ ký procedure, mapping tham số, kiểu dữ liệu, transaction, result set và trạng thái persistence context sau khi procedure cập nhật dữ liệu.