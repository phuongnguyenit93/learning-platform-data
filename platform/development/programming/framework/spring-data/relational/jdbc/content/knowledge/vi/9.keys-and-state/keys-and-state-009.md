# Giới hạn khóa ghép và chiến lược tương thích theo phiên bản

Trong cơ sở dữ liệu quan hệ, một hàng có thể được định danh bằng một cột khóa chính hoặc bằng tổ hợp nhiều cột. Khóa chính gồm nhiều thành phần được gọi là **composite primary key (khóa chính ghép)**. Kiểu khóa này thường xuất hiện khi danh tính một bản ghi được xác định bởi nhiều yếu tố nghiệp vụ, chẳng hạn mã tenant cùng mã sản phẩm, hoặc mã đơn hàng cùng số thứ tự dòng.

Khi dùng **Spring Data Relational JDBC**, cần phân biệt khả năng của database với khả năng mapping của phiên bản Spring Data JDBC đang chạy. Database có thể hỗ trợ khóa ghép hoàn toàn, nhưng repository và cơ chế ánh xạ object của một phiên bản framework cụ thể có thể có giới hạn riêng. Không nên suy ra rằng các annotation JPA như `@EmbeddedId` hay `@IdClass` sẽ tự động hoạt động trong Spring Data JDBC.

Bài học trình bày cách hiểu khóa ghép, những chỗ cần kiểm tra trong Spring Data JDBC, chiến lược tương thích khi nâng cấp hoặc phải hỗ trợ nhiều phiên bản, và cách chọn giữa khóa ghép với khóa thay thế (surrogate key).

## 1. Khóa chính ghép là gì?

Khóa chính ghép là khóa được tạo từ **hai hoặc nhiều cột**, trong đó tổ hợp giá trị phải duy nhất và từng thành phần đều tham gia xác định một hàng.

Ví dụ bảng `order_line`:

~~~sql
CREATE TABLE order_line (
    order_id BIGINT NOT NULL,
    line_number INTEGER NOT NULL,
    product_code VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    PRIMARY KEY (order_id, line_number)
);
~~~

Trong bảng này:

- `order_id` xác định đơn hàng.
- `line_number` xác định vị trí dòng bên trong đơn đó.
- Chỉ tổ hợp `(order_id, line_number)` mới định danh duy nhất một dòng hàng.

Hai hàng có thể cùng `line_number = 1` nếu thuộc hai đơn khác nhau. Hai hàng có thể cùng `order_id` nếu là hai dòng khác nhau. Không cột đơn lẻ nào trong hai cột trên đủ để làm khóa chính.

~~~text
order_id | line_number | product_code
---------+-------------+-------------
1001     | 1           | BOOK-A
1001     | 2           | PEN-B
1002     | 1           | BOOK-A

Khóa của hàng đầu tiên = (1001, 1)
Khóa của hàng thứ hai  = (1001, 2)
Khóa của hàng thứ ba   = (1002, 1)
~~~

### 1.1. Khóa chính ghép khác với một cột chứa chuỗi ghép

Có thể tạo chuỗi `"1001-1"` từ hai giá trị, nhưng đó không tự động trở thành khóa ghép. Một cột chuỗi như vậy có các vấn đề:

- Cần quy tắc mã hóa/giải mã để không nhầm ranh giới giữa các thành phần.
- Database không thể áp dụng kiểu dữ liệu và ràng buộc riêng cho từng phần.
- Sắp xếp, lọc và join theo từng thành phần trở nên phức tạp.
- Thay đổi quy tắc định dạng có thể ảnh hưởng đến dữ liệu và API.

Khóa ghép ở mức relational schema giữ từng cột riêng và khai báo tính duy nhất trên toàn bộ tổ hợp.

### 1.2. Ba khái niệm thường bị nhầm

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Primary key ghép | Nhiều cột cùng tạo thành khóa chính | `PRIMARY KEY (tenant_id, product_code)` |
| Unique constraint ghép | Nhiều cột phải duy nhất cùng nhau, nhưng không nhất thiết là primary key | `UNIQUE (tenant_id, email)` |
| Khóa thay thế (surrogate key) | Một khóa kỹ thuật được tạo để định danh hàng | `id BIGINT GENERATED ... PRIMARY KEY` |

Một bảng chỉ có một primary key constraint, nhưng khóa chính đó có thể chứa nhiều cột. Bảng cũng có thể có nhiều unique constraint để bảo vệ các định danh nghiệp vụ khác.

## 2. Vì sao nghiệp vụ chọn khóa ghép?

Khóa ghép thường phản ánh danh tính tự nhiên của dữ liệu.

### 2.1. Danh tính phụ thuộc phạm vi

Một mã sản phẩm có thể chỉ duy nhất trong một tenant:

~~~sql
CREATE TABLE tenant_product (
    tenant_id BIGINT NOT NULL,
    product_code VARCHAR(80) NOT NULL,
    name VARCHAR(200) NOT NULL,
    PRIMARY KEY (tenant_id, product_code)
);
~~~

Trong trường hợp này, `product_code` không duy nhất toàn hệ thống. Danh tính phải gồm cả `tenant_id` và `product_code`.

### 2.2. Dữ liệu con được đánh số trong phạm vi cha

Một dòng hàng có thể được định danh bằng `(order_id, line_number)`. Số dòng chỉ có ý nghĩa trong một đơn hàng. Dữ liệu con này thường có vòng đời gắn với đơn hàng.

### 2.3. Bảng liên kết giữa hai thực thể

Một bảng nối giữa sinh viên và khóa học có thể dùng tổ hợp:

~~~sql
CREATE TABLE enrollment (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    enrolled_at TIMESTAMP NOT NULL,
    PRIMARY KEY (student_id, course_id)
);
~~~

Tổ hợp hai khóa ngoại ngăn một sinh viên đăng ký cùng khóa học hai lần. Nếu bảng cần lưu nhiều lần đăng ký theo đợt, cần bổ sung thành phần định danh như `term_id` hoặc `attempt_number`; thiết kế khóa phải phản ánh đúng quy tắc nghiệp vụ.

### 2.4. Ưu điểm và chi phí

**Ưu điểm**

- Khóa có ý nghĩa trực tiếp với nghiệp vụ.
- Có thể tránh một cột ID kỹ thuật nếu tổ hợp tự nhiên đã ổn định và duy nhất.
- Ràng buộc duy nhất được database bảo vệ ngay trên các thành phần nghiệp vụ.
- Dữ liệu con có thể thể hiện rõ phạm vi định danh của nó.

**Chi phí**

- Khóa ngoại tham chiếu phải mang đủ các thành phần.
- Join, update, delete và query cần cung cấp đầy đủ thành phần khóa.
- Index và khóa ngoại có thể rộng hơn, tốn dung lượng hơn.
- Khi một thành phần khóa thay đổi, việc cập nhật tham chiếu phức tạp.
- Framework ORM/JDBC mapping có thể có giới hạn riêng đối với kiểu ID nhiều thành phần.

Do đó, “khóa tự nhiên” không phải lúc nào cũng là “khóa tốt nhất để dùng làm primary key”.

## 3. Khả năng của database và khả năng của Spring Data JDBC là hai việc khác nhau

Database như PostgreSQL, MySQL hoặc SQL Server có thể khai báo primary key gồm nhiều cột. Nhưng ứng dụng không chỉ cần schema hợp lệ; framework còn phải biết:

1. Đọc từng thành phần khóa từ row.
2. Tạo object Java biểu diễn đầy đủ khóa.
3. Nhận diện object mới hay đã tồn tại.
4. Tạo câu SQL có điều kiện trên toàn bộ thành phần khóa.
5. Bind tham số đúng kiểu dữ liệu.
6. Xử lý ID khi lưu và khi đọc lại.
7. Truyền đủ khóa qua quan hệ giữa aggregate hoặc entity con nếu mapping yêu cầu.

Một database chấp nhận:

~~~sql
PRIMARY KEY (tenant_id, product_code)
~~~

không có nghĩa repository có thể tự động xử lý mọi class Java chứa hai field đó. **Khả năng relational schema không chứng minh khả năng object mapping của framework.**

### 3.1. Không chuyển nguyên mẫu JPA sang Spring Data JDBC

Trong JPA, lập trình viên thường gặp:

- `@EmbeddedId` để khai báo một object ID nhúng.
- `@IdClass` để mô tả lớp khóa ghép.
- `@Embeddable` để khai báo kiểu khóa/value được nhúng.

Spring Data JDBC sử dụng mapping của Spring Data Relational. `jakarta.persistence.EmbeddedId` và `jakarta.persistence.IdClass` không phải hợp đồng mapping của Spring Data JDBC. Thêm annotation JPA vào class không tự tạo hỗ trợ composite ID trong JDBC.

Tương tự, `@Embedded` của Spring Data Relational là annotation cho object được ánh xạ thành các cột trong hàng. Nó không nên được xem là bí danh có cùng ngữ nghĩa với toàn bộ cơ chế `@EmbeddedId` của JPA.

Luôn kiểm tra package import:

~~~java
// Spring Data JDBC:
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

// Không lấy các annotation sau làm cơ chế khóa ghép của Spring Data JDBC:
// import jakarta.persistence.EmbeddedId;
// import jakarta.persistence.IdClass;
~~~

## 4. Kiểm tra hỗ trợ composite ID theo phiên bản

Khả năng ánh xạ khóa ghép là một phần của hợp đồng framework, không chỉ là chi tiết DDL. Spring Data JDBC và Spring Data Relational đã phát triển qua nhiều release; không nên giả định một project cũ và một project mới có cùng khả năng.

Khi đánh giá composite ID, cần xác minh ít nhất:

- Phiên bản `spring-data-relational` thực tế được resolve.
- Phiên bản `spring-data-jdbc` tương ứng.
- Release train và Spring Framework tương thích.
- Phiên bản Spring Boot/BOM đang quản lý dependency.
- Kiểu composite ID được hỗ trợ trong phiên bản đó và quy tắc ánh xạ từng component.
- Khả năng tương thích của dialect/database và các thao tác repository cần dùng.

**Không lấy số phiên bản Spring Boot để đoán trực tiếp khả năng của Spring Data JDBC.** Spring Boot quản lý một tập dependency thông qua BOM; điều cần xem là phiên bản artifact thực tế sau khi Gradle resolve dependency.

### 4.1. Xác định phiên bản dependency thực tế bằng Gradle

Trên Windows:

~~~powershell
.\gradlew.bat dependencyInsight --dependency spring-data-relational --configuration runtimeClasspath
~~~

Và kiểm tra module JDBC:

~~~powershell
.\gradlew.bat dependencyInsight --dependency spring-data-jdbc --configuration runtimeClasspath
~~~

Trên Linux/macOS:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-data-relational \
  --configuration runtimeClasspath
~~~

Lệnh `dependencyInsight` giúp xác định version được chọn và đường dependency dẫn tới version đó. Điều này hữu ích khi dependency được quản lý qua Spring Boot plugin, platform/BOM hoặc bị một thư viện khác kéo vào.

Nếu project dùng configuration khác `runtimeClasspath` (ví dụ module không phải application hoặc cấu hình custom), hãy chọn configuration thích hợp. Không nên nhìn riêng version khai báo trong một file rồi kết luận đó là version đang chạy.

### 4.2. Đọc tài liệu đúng release

Khi cần composite ID:

1. Lấy version `spring-data-relational`/`spring-data-jdbc` đã resolve.
2. Mở reference documentation và release notes đúng dòng version đó.
3. Tìm phần mapping identifier/composite identifier.
4. Kiểm tra kiểu ID được hỗ trợ, cách đặt annotation và cách mapping các thành phần.
5. Kiểm tra giới hạn liên quan đến generated ID, child references, repository CRUD và custom query.
6. Viết integration test với database/dialect thực tế trước khi áp dụng rộng.

Không dùng tài liệu của nhánh mới nhất để khẳng định một ứng dụng đang chạy phiên bản cũ có cùng hành vi. Tài liệu mới có thể mô tả tính năng chưa tồn tại trong release mà ứng dụng đang dùng.

### 4.3. Ma trận quyết định theo năng lực phiên bản

Thay vì dựa vào một phỏng đoán về mốc release, có thể phân loại theo khả năng đã xác nhận:

| Tình huống | Chiến lược |
| --- | --- |
| Phiên bản hiện tại không hỗ trợ composite ID theo cách mô hình cần | Dùng surrogate key làm primary key; bảo vệ danh tính nghiệp vụ bằng unique constraint ghép. |
| Phiên bản có hỗ trợ composite ID nhưng chỉ đáp ứng một số kiểu mapping | Chỉ dùng khi tất cả thao tác cần thiết đã được kiểm chứng; nếu còn thiếu, dùng surrogate key. |
| Phiên bản hỗ trợ đầy đủ kiểu ID và quan hệ cần thiết | Có thể dùng composite ID trực tiếp nếu lợi ích nghiệp vụ vượt chi phí tham chiếu. |
| Ứng dụng phải chạy trên nhiều release khác nhau | Chọn thiết kế giao nhau mà mọi release đều hỗ trợ, thường là surrogate key + unique constraint. |
| Có kế hoạch nâng cấp framework | Tách việc nâng cấp khỏi việc đổi schema/ID nếu có thể; kiểm thử từng thay đổi để khoanh vùng rủi ro. |

Ma trận này có chủ đích dựa trên **khả năng được xác minh của artifact**, thay vì gán một tính năng cho mọi phiên bản mà không kiểm tra release notes. Mốc hỗ trợ cụ thể phải lấy từ tài liệu đúng phiên bản mà ứng dụng định dùng.

## 5. Chiến lược tương thích rộng: surrogate key và unique constraint

Khi cần hỗ trợ nhiều phiên bản Spring Data JDBC hoặc muốn repository đơn giản, cách tiếp cận thường dễ tương thích nhất là:

- Dùng một khóa kỹ thuật đơn giản làm primary key.
- Giữ các thành phần nghiệp vụ trong các cột riêng.
- Khai báo unique constraint trên tổ hợp nghiệp vụ.

Ví dụ bảng tenant product:

~~~sql
CREATE TABLE tenant_product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    product_code VARCHAR(80) NOT NULL,
    name VARCHAR(200) NOT NULL,
    CONSTRAINT uk_tenant_product_code
        UNIQUE (tenant_id, product_code)
);
~~~

Entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("tenant_product")
public class TenantProduct {

    @Id
    private Long id;

    private Long tenantId;
    private String productCode;
    private String name;

    public TenantProduct(
            Long id,
            Long tenantId,
            String productCode,
            String name
    ) {
        this.id = id;
        this.tenantId = tenantId;
        this.productCode = productCode;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public String getProductCode() {
        return productCode;
    }

    public String getName() {
        return name;
    }
}
~~~

Repository có khóa đơn giản:

~~~java
public interface TenantProductRepository
        extends CrudRepository<TenantProduct, Long> {

    Optional<TenantProduct> findByTenantIdAndProductCode(
            Long tenantId,
            String productCode
    );
}
~~~

Kết quả:

- Spring Data JDBC dùng `id` làm identifier của entity.
- Nghiệp vụ vẫn tra cứu bằng `tenantId + productCode`.
- Database đảm bảo tổ hợp đó không bị trùng dù có nhiều request đồng thời.
- Khóa ngoại từ bảng khác chỉ cần tham chiếu một cột `id`.
- Khi mã sản phẩm đổi theo quy tắc nghiệp vụ, primary key kỹ thuật không cần đổi.

### 5.1. Unique constraint là lớp bảo vệ cuối cùng

Kiểm tra tồn tại ở Java trước khi insert không đủ để bảo đảm duy nhất:

~~~java
if (!repository.existsByTenantIdAndProductCode(tenantId, code)) {
    repository.save(product);
}
~~~

Hai request có thể cùng kiểm tra “chưa tồn tại” trước khi request nào insert. Sau đó cả hai cùng cố tạo một bản ghi trùng.

Database unique constraint giải quyết cuộc đua đó:

~~~text
Request A: SELECT -> chưa có
Request B: SELECT -> chưa có
Request A: INSERT -> thành công
Request B: INSERT -> vi phạm unique constraint
~~~

Ứng dụng vẫn có thể kiểm tra trước để trả thông báo thân thiện, nhưng phải xử lý lỗi constraint khi lưu. Không dùng một câu query kiểm tra trước thay cho unique constraint.

### 5.2. Khi nào surrogate key là lựa chọn tốt?

Surrogate key đặc biệt hữu ích khi:

- Thành phần khóa nghiệp vụ có thể thay đổi.
- Khóa có nhiều cột và được nhiều bảng tham chiếu.
- Hệ thống cần tương thích với nhiều phiên bản persistence framework.
- Aggregate có nhiều quan hệ hoặc thao tác CRUD cần một ID đơn giản.
- API và event cần một identifier ngắn, ổn định.

Nhược điểm là thêm một cột và một unique constraint. Tuy nhiên, chi phí đó thường nhỏ hơn độ phức tạp của việc truyền khóa ghép qua toàn bộ hệ thống.

## 6. Khi nào nên dùng composite ID trực tiếp?

Composite ID có thể hợp lý nếu tổ hợp khóa:

- Ổn định trong suốt vòng đời dữ liệu.
- Không chứa thành phần có thể chỉnh sửa tùy ý.
- Có ý nghĩa tự nhiên trong miền.
- Được database bảo vệ bằng primary key.
- Được framework đang dùng hỗ trợ đầy đủ.
- Không tạo gánh nặng quá lớn cho các quan hệ tham chiếu và API.

Ví dụ `EnrollmentId`:

~~~java
public record EnrollmentId(Long studentId, Long courseId) {
    public EnrollmentId {
        if (studentId == null || studentId <= 0) {
            throw new IllegalArgumentException("studentId không hợp lệ");
        }
        if (courseId == null || courseId <= 0) {
            throw new IllegalArgumentException("courseId không hợp lệ");
        }
    }
}
~~~

Kiểu record này biểu diễn value của khóa một cách rõ ràng và có equality theo hai thành phần. Nhưng việc khai báo record **không tự làm Spring Data JDBC hỗ trợ mapping composite ID**. Cần tuân theo chính xác cách khai báo ID mà phiên bản Spring Data Relational đang dùng yêu cầu.

Nếu release hỗ trợ composite ID với ID value type, cấu trúc conceptual có thể là:

~~~text
Enrollment
  id: EnrollmentId
       studentId
       courseId
  enrolledAt

Database:
  enrollment.student_id
  enrollment.course_id
  PRIMARY KEY (student_id, course_id)
~~~

Đây là mô hình khái niệm. Trước khi dùng trong code thực tế, xác nhận annotation/flattening convention mà release hỗ trợ; không tự áp dụng `@EmbeddedId` của JPA hay giả định mọi field trong record sẽ tự động được bung thành cột khóa.

### 6.1. Khóa ghép nên bất biến

Nếu `studentId` hoặc `courseId` thay đổi, danh tính enrollment cũng thay đổi. Việc đổi khóa có thể yêu cầu:

- Cập nhật tất cả foreign key tham chiếu.
- Xử lý cascade hoặc thứ tự cập nhật.
- Tránh khoảng thời gian có dữ liệu không nhất quán.
- Xem xét event, cache key và URL/API đã phát hành.

Do đó, các thành phần composite ID nên là giá trị ổn định. Nếu thành phần thường xuyên thay đổi, cân nhắc surrogate key.

### 6.2. Không dùng giá trị nullable trong khóa

Primary key của database không chấp nhận null theo ngữ nghĩa thông thường. Mỗi thành phần khóa phải có giá trị hợp lệ trước khi lưu. Value type của ID nên kiểm tra điều này ở constructor/factory; schema cũng phải khai báo các cột khóa là `NOT NULL`.

### 6.3. Equality và hash code

ID ghép thường là value object. So sánh hai ID theo toàn bộ thành phần là hợp lý:

~~~java
EnrollmentId a = new EnrollmentId(10L, 20L);
EnrollmentId b = new EnrollmentId(10L, 20L);

System.out.println(a.equals(b)); // true
~~~

Java record tự tạo `equals()` và `hashCode()` theo component, phù hợp với kiểu ID immutable như trên. Nếu dùng class thường, phải cài đặt hai phương thức nhất quán theo toàn bộ thành phần khóa.

## 7. Khóa ghép trong quan hệ và foreign key

Một hạn chế lớn của khóa ghép không nằm ở bảng gốc mà ở **mọi bảng tham chiếu nó**.

Nếu `tenant_product` dùng primary key `(tenant_id, product_code)`, bảng tồn kho có thể cần:

~~~sql
CREATE TABLE inventory (
    tenant_id BIGINT NOT NULL,
    product_code VARCHAR(80) NOT NULL,
    warehouse_code VARCHAR(40) NOT NULL,
    available_quantity INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, product_code, warehouse_code),
    FOREIGN KEY (tenant_id, product_code)
        REFERENCES tenant_product (tenant_id, product_code)
);
~~~

Mỗi thao tác join cần đủ hai cột:

~~~sql
SELECT i.warehouse_code, i.available_quantity
FROM inventory i
JOIN tenant_product p
  ON p.tenant_id = i.tenant_id
 AND p.product_code = i.product_code
WHERE p.tenant_id = ?
  AND p.product_code = ?;
~~~

Nếu dùng surrogate key, quan hệ có thể đơn giản hơn:

~~~sql
CREATE TABLE tenant_product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    product_code VARCHAR(80) NOT NULL,
    CONSTRAINT uk_tenant_product UNIQUE (tenant_id, product_code)
);

CREATE TABLE inventory (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_product_id BIGINT NOT NULL
        REFERENCES tenant_product(id),
    warehouse_code VARCHAR(40) NOT NULL,
    available_quantity INTEGER NOT NULL,
    CONSTRAINT uk_inventory_product_warehouse
        UNIQUE (tenant_product_id, warehouse_code)
);
~~~

Khóa ngoại ngắn hơn, index tham chiếu thường đơn giản hơn và thay đổi mã nghiệp vụ không làm thay đổi khóa được tham chiếu.

### 7.1. Liên hệ với aggregate trong Spring Data JDBC

Spring Data JDBC lưu một aggregate qua root. Collection child thường được liên kết với root bằng khóa ngoại và metadata mapping tương ứng. Nếu root có composite ID, cần xác minh release hỗ trợ truyền đủ thành phần khóa đến bảng con và tạo SQL cho collection.

Đừng chỉ kiểm tra thao tác đọc root đơn lẻ. Cần kiểm tra:

- Insert root mới.
- Đọc root theo ID.
- Cập nhật root.
- Insert/update/delete child collection.
- Xóa aggregate và xử lý child.
- Tham chiếu aggregate từ bảng hoặc aggregate khác.

Một composite ID có thể hoạt động ở thao tác đơn giản nhưng còn thiếu hỗ trợ trong một đường mapping khác. Integration test phải bao phủ đúng các thao tác ứng dụng thực sự dùng.

## 8. Repository và truy vấn với khóa ghép

Với surrogate key, repository CRUD đơn giản:

~~~java
interface TenantProductRepository
        extends CrudRepository<TenantProduct, Long> {
}
~~~

Tra cứu theo danh tính nghiệp vụ:

~~~java
Optional<TenantProduct> findByTenantIdAndProductCode(
        Long tenantId,
        String productCode
);
~~~

Với composite ID, nếu phiên bản hỗ trợ, repository có thể dùng kiểu ID value object ở tham số generic:

~~~java
// Minh họa hình dạng API khi composite ID được release hỗ trợ.
interface EnrollmentRepository
        extends CrudRepository<Enrollment, EnrollmentId> {
}
~~~

Đoạn khai báo trên chỉ phù hợp khi mapping composite identifier đã được xác nhận trong phiên bản đang dùng. Generic type Java không thể bổ sung khả năng persistence mà framework chưa có.

### 8.1. Truy vấn thủ công

Nếu cần SQL tùy chỉnh, luôn truyền đủ các thành phần:

~~~java
@Query("""
       SELECT student_id, course_id, enrolled_at
       FROM enrollment
       WHERE student_id = :studentId
         AND course_id = :courseId
       """)
Optional<Enrollment> findEnrollment(
        Long studentId,
        Long courseId
);
~~~

Tên placeholder và khả năng bind phụ thuộc API query được sử dụng. Với `JdbcClient`, có thể viết rõ:

~~~java
return jdbcClient.sql("""
        SELECT student_id, course_id, enrolled_at
        FROM enrollment
        WHERE student_id = :studentId
          AND course_id = :courseId
        """)
    .param("studentId", studentId)
    .param("courseId", courseId)
    .query(Enrollment.class)
    .optional();
~~~

Truy vấn thủ công cho phép khai báo rõ từng cột, nhưng không tự động giải quyết mọi thao tác save/delete aggregate. Cần quyết định rõ phần nào do repository quản lý và phần nào do SQL tùy chỉnh quản lý để tránh hai đường cập nhật mâu thuẫn.

### 8.2. Không ghép khóa bằng chuỗi SQL

Tránh:

~~~java
String sql = "SELECT * FROM enrollment WHERE student_id = "
        + studentId + " AND course_id = " + courseId;
~~~

Dùng bind parameter để giữ kiểu dữ liệu và tránh SQL injection:

~~~java
jdbcClient.sql("""
        SELECT *
        FROM enrollment
        WHERE student_id = :studentId
          AND course_id = :courseId
        """)
    .param("studentId", studentId)
    .param("courseId", courseId)
    .query(Enrollment.class);
~~~

Không dùng một chuỗi `studentId + "-" + courseId` làm tham số duy nhất nếu database có hai cột khóa riêng.

## 9. Chiến lược migration khi đổi từ khóa ghép sang surrogate key

Một hệ thống đã chạy với composite primary key có thể muốn chuyển sang surrogate key để đơn giản hóa persistence mapping. Đây là thay đổi schema quan trọng vì nhiều bảng có thể đang tham chiếu các thành phần khóa cũ.

Giả sử bảng gốc:

~~~sql
CREATE TABLE tenant_product (
    tenant_id BIGINT NOT NULL,
    product_code VARCHAR(80) NOT NULL,
    name VARCHAR(200) NOT NULL,
    PRIMARY KEY (tenant_id, product_code)
);
~~~

Mục tiêu:

~~~sql
CREATE TABLE tenant_product (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    product_code VARCHAR(80) NOT NULL,
    name VARCHAR(200) NOT NULL,
    UNIQUE (tenant_id, product_code)
);
~~~

Một chiến lược chuyển đổi theo pha:

**Pha 1 — Thêm cột ID**

- Thêm cột `id` với cơ chế sinh giá trị phù hợp.
- Backfill ID cho toàn bộ hàng cũ.
- Tạo unique index/constraint cho `id`.
- Giữ nguyên composite primary key trong giai đoạn ứng dụng cũ còn phụ thuộc.

**Pha 2 — Cập nhật bảng tham chiếu**

- Thêm cột `tenant_product_id` vào từng bảng con/consumer cần tham chiếu.
- Backfill bằng join trên khóa cũ.
- Tạo foreign key và index mới.
- Kiểm tra không còn bản ghi tham chiếu thiếu hoặc sai.

**Pha 3 — Triển khai ứng dụng tương thích**

- Phiên bản ứng dụng chuyển dần sang đọc/ghi ID mới theo chiến lược migration đã chọn.
- Nếu phải chạy song song phiên bản cũ và mới, cần xác định rõ phiên bản nào ghi các cột nào và cách đồng bộ.
- Không xóa khóa cũ khi còn instance hoặc job cũ cần dùng nó.

**Pha 4 — Chuyển primary key**

- Chỉ sau khi mọi tham chiếu và ứng dụng đã dùng ID mới, chuyển primary key sang `id`.
- Giữ unique constraint trên `(tenant_id, product_code)` để bảo vệ danh tính nghiệp vụ.
- Loại bỏ foreign key/index cũ sau khi xác minh không còn consumer.

Thứ tự DDL, khả năng đổi constraint trực tuyến và cú pháp backfill phụ thuộc database. Với bảng lớn, cần đánh giá lock, thời gian tạo index, replication lag và chiến lược rollout. Không áp dụng một script chung cho mọi hệ quản trị.

### 9.1. Migration ngược lại: từ surrogate key sang composite ID

Đổi từ một ID đơn giản sang composite ID thường có chi phí tham chiếu lớn hơn lợi ích:

- Mọi foreign key phải mở rộng thành nhiều cột.
- API, cache, log, event và URL có thể phải đổi.
- Repository generic ID và method signature phải thay đổi.
- Các consumer ngoài hệ thống có thể phụ thuộc ID cũ.

Nếu mục tiêu chỉ là bảo vệ tính duy nhất nghiệp vụ, **giữ surrogate primary key và thêm unique constraint ghép** thường đủ. Chỉ đổi primary key khi có lý do kiến trúc rõ ràng.

## 10. Quản lý version dependency để tránh lệch tương thích

Trong Gradle, Spring Boot thường quản lý phiên bản Spring Data thông qua dependency management/BOM. Việc khai báo thủ công một version khác cho riêng `spring-data-jdbc` hoặc `spring-data-relational` có thể tạo ra tổ hợp không được kiểm thử cùng nhau.

### 10.1. Ưu tiên một nguồn quản lý phiên bản

Ví dụ dùng Spring Boot plugin/BOM:

~~~groovy
plugins {
    id 'org.springframework.boot' version '<boot-version>'
    id 'io.spring.dependency-management' version '<plugin-version>'
    id 'java'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Các placeholder phải được thay bằng version đã chọn theo compatibility matrix của dự án. Khi dùng starter, để BOM quản lý Spring Data artifacts trừ khi có chủ đích nâng cấp đã được kiểm thử.

Nếu quản lý Spring Data độc lập với Spring Boot, dùng release train/BOM tương ứng và xác minh compatibility với Spring Framework cùng Java baseline. Không chỉ nâng một module con rồi để các module Spring Data khác ở release train cũ.

### 10.2. Tránh override một artifact để “mở khóa” tính năng

Ví dụ rủi ro:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    implementation 'org.springframework.data:spring-data-relational:<new-version>'
}
~~~

Nếu version override không tương thích với Spring Data JDBC được starter quản lý, ứng dụng có thể gặp lỗi binary/API hoặc hành vi mapping không được hỗ trợ. Để dùng một tính năng mới:

1. Xác định release train có tính năng đó.
2. Chọn Spring Boot/Spring Framework phù hợp với release train.
3. Nâng BOM/platform đồng bộ.
4. Chạy compile, integration test và kiểm tra SQL.
5. Chỉ dùng version override riêng nếu tài liệu chính thức cho phép và đã kiểm thử tổ hợp đó.

### 10.3. Compatibility không chỉ là compile thành công

Một class có thể compile dù mapping composite ID không được framework hỗ trợ theo cách mong muốn. Runtime mới là lúc SQL được sinh, ID được bind và row được materialize. Kiểm tra ít nhất các thao tác persistence quan trọng trên database thật hoặc Testcontainers với đúng dialect.

## 11. Kiểm thử composite ID và tương thích phiên bản

Kiểm thử nên xác nhận cả schema, mapping và hành vi CRUD.

### 11.1. Kiểm tra uniqueness ở database

~~~sql
INSERT INTO enrollment(student_id, course_id, enrolled_at)
VALUES (10, 20, CURRENT_TIMESTAMP);

-- Tổ hợp giống nhau phải bị từ chối.
INSERT INTO enrollment(student_id, course_id, enrolled_at)
VALUES (10, 20, CURRENT_TIMESTAMP);
~~~

Lệnh thứ hai phải vi phạm primary key/unique constraint. Test nên xác nhận exception được ứng dụng xử lý đúng.

### 11.2. Kiểm tra vòng đời repository

| Ca kiểm thử | Điều cần xác nhận |
| --- | --- |
| Insert entity mới | Mọi thành phần khóa được ghi đúng; không bị bỏ sót hoặc bind sai thứ tự/kiểu. |
| Load bằng ID | Có thể dựng đúng object ID từ tất cả cột khóa. |
| Save/update | Điều kiện cập nhật dùng đủ thành phần khóa. |
| Delete | Chỉ xóa đúng hàng có toàn bộ thành phần ID. |
| Child collection | Khóa root được truyền đúng tới bảng con. |
| Foreign key | Tham chiếu từ bảng khác được bảo vệ đúng. |
| Custom query | Parameter mapping và projection hoạt động với kiểu dữ liệu thực. |
| Concurrency | Unique constraint/optimistic locking xử lý cạnh tranh như mong đợi. |
| Migration | Dữ liệu cũ và tham chiếu cũ vẫn hợp lệ sau rollout. |

### 11.3. Kiểm tra generated SQL

Bật logging SQL ở môi trường test phù hợp hoặc dùng datasource proxy để quan sát:

- Số cột trong `INSERT`.
- Điều kiện `WHERE` của `UPDATE` và `DELETE`.
- Từng tham số bind và kiểu dữ liệu.
- SQL thao tác collection child.
- Việc có dùng index phù hợp hay không qua execution plan.

Không chỉ xác nhận repository trả về object đúng. Một test có thể vô tình chỉ kiểm tra dữ liệu đã được insert qua một đường SQL khác; cần đảm bảo đường mapping Spring Data JDBC đang được kiểm thử thực sự.

### 11.4. Chạy ma trận phiên bản

~~~text
                 Integration test suite
                          |
             +------------+------------+
             |            |            |
          Version A    Version B    Version C
             |            |            |
             v            v            v
        insert/load   insert/load   insert/load
        update/delete update/delete update/delete
        child refs    child refs    child refs
             |            |            |
             +------------+------------+
                          |
                 Compare expected behavior
~~~

Mỗi phiên bản cần dùng dependency set đúng release train của nó. Không cố chạy một classpath chứa nhiều version Spring Data cùng lúc; hãy tách build/test matrix theo module hoặc job riêng.

## 12. Lựa chọn khóa cho từng loại dữ liệu

| Loại dữ liệu | Khóa thường phù hợp | Lý do |
| --- | --- | --- |
| Người dùng, đơn hàng, sản phẩm có vòng đời dài | Surrogate ID đơn giản, kèm unique key nghiệp vụ nếu cần | ID ổn định khi thuộc tính nghiệp vụ đổi. |
| Bảng nối hai ID bất biến, không có vòng đời độc lập | Composite key gồm hai foreign key hoặc surrogate ID + unique constraint | Chọn theo hỗ trợ framework và nhu cầu tham chiếu. |
| Dòng hàng có số thứ tự trong phạm vi đơn | `(order_id, line_number)` hoặc surrogate child ID | Số dòng có ý nghĩa trong aggregate; cân nhắc việc sắp xếp/xóa/chèn lại. |
| Mã sản phẩm chỉ duy nhất theo tenant | `UNIQUE(tenant_id, product_code)`; primary key đơn giản hoặc ghép tùy kiến trúc | Phạm vi duy nhất phải được database bảo vệ. |
| Dữ liệu lịch sử có nhiều phiên bản của cùng đối tượng | ID phiên bản riêng hoặc composite key chứa version/effective time | Danh tính cần phân biệt từng bản ghi lịch sử. |
| Event có nguồn và số thứ tự trong nguồn | `(source_id, sequence_number)` có thể phù hợp | Tổ hợp ổn định và phản ánh thứ tự duy nhất trong nguồn. |

Không chọn composite ID chỉ vì hai cột hiện tại có vẻ duy nhất. Cần hỏi liệu chúng có tiếp tục duy nhất, không null và không thay đổi trong toàn bộ vòng đời hay không.

## 13. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `@EmbeddedId`/`@IdClass` theo thói quen JPA | Spring Data JDBC không hiểu annotation theo hợp đồng JPA | Dùng annotation Spring Data Relational đúng với release hoặc chọn surrogate ID. |
| Nghĩ database hỗ trợ thì repository cũng hỗ trợ | Runtime mapping hoặc CRUD có thể thất bại | Kiểm tra reference docs, release notes và integration test. |
| Khai báo composite ID bằng record rồi cho rằng tự động hoạt động | Record chỉ tạo kiểu Java, không cung cấp mapping feature | Xác minh cách framework ánh xạ ID value type. |
| Chỉ truyền một phần khóa trong query | Đọc nhầm hoặc cập nhật/xóa sai hàng | Luôn bind đủ mọi thành phần. |
| Dùng chuỗi ghép để giả lập khóa | Mất kiểu dữ liệu và quy tắc từng cột | Giữ các thành phần thành cột riêng. |
| Không có unique constraint | Hai request đồng thời có thể tạo bản ghi trùng | Bảo vệ tính duy nhất tại database. |
| Thành phần khóa có thể thay đổi thường xuyên | Cập nhật dây chuyền foreign key và cache | Dùng surrogate ID ổn định. |
| Override riêng một version Spring Data | Có thể tạo dependency không tương thích | Nâng đồng bộ qua BOM/release train. |
| Kiểm tra bằng H2 rồi kết luận cho production DB | Dialect, identity và constraint behavior có thể khác | Test với database/dialect thực tế hoặc Testcontainers. |
| Chỉ test findById | Bỏ sót lỗi update/delete/child mapping | Test toàn bộ vòng đời aggregate. |

## 14. Quy trình ra quyết định

Khi thiết kế bảng hoặc aggregate cần khóa ghép, có thể đi theo trình tự:

1. **Xác định danh tính nghiệp vụ.** Viết rõ các thành phần nào kết hợp để định danh một bản ghi.
2. **Kiểm tra độ ổn định.** Thành phần có thể đổi, null, chuẩn hóa hoặc tái sử dụng không?
3. **Thiết kế constraint.** Dùng primary key hoặc unique constraint để database thực thi quy tắc.
4. **Kiểm tra framework.** Xác định phiên bản Spring Data JDBC thực tế và khả năng mapping cần thiết.
5. **Đánh giá quan hệ.** Đếm các bảng, aggregate và API phải mang đủ các thành phần khóa.
6. **Chọn phương án.** Dùng composite ID nếu hỗ trợ đầy đủ và có lợi ích rõ; nếu không, dùng surrogate key cùng unique constraint ghép.
7. **Kiểm thử runtime.** Xác nhận insert, load, update, delete, child collection, foreign key và concurrency.
8. **Lập kế hoạch nâng cấp.** Khi version thay đổi, kiểm tra lại mapping contract trước khi loại bỏ giải pháp tương thích cũ.

## Ghi nhớ

Khóa ghép là lựa chọn hợp lệ ở tầng relational database, nhưng khả năng sử dụng trực tiếp trong Spring Data JDBC phụ thuộc vào mapping contract của phiên bản framework. Đừng lấy annotation JPA làm bằng chứng hỗ trợ. Hãy xác định artifact version đã resolve, đọc tài liệu đúng release và kiểm thử đầy đủ các thao tác cần dùng.

Khi cần tương thích rộng hoặc muốn đơn giản hóa quan hệ, **surrogate primary key kết hợp unique constraint trên các thành phần nghiệp vụ** thường là chiến lược bền vững: repository có ID đơn giản, database vẫn bảo vệ danh tính tự nhiên, và các bảng tham chiếu không phải mang cả tổ hợp khóa qua hệ thống.
