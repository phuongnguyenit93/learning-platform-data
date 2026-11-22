# Tùy chỉnh SQL insert, update hoặc delete và trách nhiệm giữ đúng trạng thái

Trong Hibernate/JPA, ứng dụng thường thao tác với entity bằng các lệnh `persist()`, thay đổi thuộc tính trên đối tượng managed, hoặc `remove()`. Hibernate theo dõi trạng thái entity và sinh SQL `INSERT`, `UPDATE`, `DELETE` thích hợp khi flush. Đây là con đường được ưu tiên vì ORM có thể đồng bộ định danh, khóa phiên bản, quan hệ, callback và persistence context dựa trên mapping.

Tuy nhiên, một số hệ thống cần **thay thế SQL mà Hibernate mặc định phát ra**: xóa mềm bằng `UPDATE` thay vì `DELETE`, gọi stored procedure, ghi thêm cột audit do database quản lý, hoặc tương thích với schema hiện hữu có quy tắc DML đặc biệt. Hibernate cung cấp các annotation như **`@SQLInsert`, `@SQLUpdate` và `@SQLDelete`** để khai báo câu SQL tùy chỉnh cho thao tác ghi của entity.

Khả năng viết SQL tùy chỉnh đi kèm trách nhiệm: **Hibernate vẫn quản lý vòng đời và trạng thái entity theo quy tắc ORM, nhưng câu SQL tự viết phải giữ đúng những giả định đó**. Một câu SQL chạy thành công ở database chưa chắc làm trạng thái trong bộ nhớ, khóa optimistic locking, quan hệ và kết quả đọc về sau trở nên nhất quán.

Bài học tập trung vào các tình huống sử dụng, cơ chế thực thi, thứ tự tham số, số hàng ảnh hưởng, xóa mềm, đồng bộ trạng thái và những rủi ro thực tế khi làm việc với Hibernate ORM.

## 1. SQL mặc định của Hibernate đến từ đâu?

Giả sử entity:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "catalog_items")
public class CatalogItem {

    @Id
    private Long id;

    @Column(nullable = false)
    private String label;

    protected CatalogItem() {}

    public CatalogItem(Long id, String label) {
        this.id = id;
        this.label = label;
    }

    public void rename(String newLabel) {
        this.label = newLabel;
    }
}
~~~

Khi dùng:

~~~java
CatalogItem item = new CatalogItem(10L, "Original");
entityManager.persist(item);
entityManager.flush();
~~~

Hibernate thường gửi một lệnh có ý nghĩa tương đương:

~~~sql
INSERT INTO catalog_items (label, id)
VALUES (?, ?);
~~~

Khi thay đổi một entity đang managed:

~~~java
CatalogItem managed = entityManager.find(CatalogItem.class, 10L);
managed.rename("Updated");
entityManager.flush();
~~~

Hibernate có thể gửi:

~~~sql
UPDATE catalog_items
SET label = ?
WHERE id = ?;
~~~

Khi xóa:

~~~java
entityManager.remove(managed);
entityManager.flush();
~~~

Hibernate có thể gửi:

~~~sql
DELETE FROM catalog_items
WHERE id = ?;
~~~

Đây là **SQL minh họa**, không phải cam kết thứ tự cột hoặc chính xác từng lệnh ở mọi phiên bản. SQL thực tế phụ thuộc metadata, dialect, chiến lược ID, cấu hình cập nhật, khóa phiên bản và các mapping liên quan.

Thông thường, Hibernate có nhiệm vụ:

1. Quyết định **khi nào** cần INSERT, UPDATE hoặc DELETE.
2. Xác định entity và các thuộc tính persistent tham gia thao tác.
3. Tạo SQL phù hợp schema và dialect.
4. Bind các tham số JDBC tương ứng.
5. Thực thi trong transaction đang hoạt động.
6. Đồng bộ trạng thái entity, kiểm tra số hàng ảnh hưởng và khóa phiên bản theo cấu hình.

Khi thay SQL bằng câu tùy chỉnh, phần lớn trách nhiệm từ bước 1, 2, 4, 5 và quản lý persistence context **vẫn tồn tại**. Bạn phải viết câu SQL khớp các giả định của những bước còn lại.

## 2. Ba annotation Hibernate dùng để thay DML

Các annotation được import từ Hibernate:

~~~java
import org.hibernate.annotations.SQLInsert;
import org.hibernate.annotations.SQLUpdate;
import org.hibernate.annotations.SQLDelete;
~~~

| Annotation | Thao tác ORM gắn với nó | Mục đích |
| --- | --- | --- |
| `@SQLInsert` | SQL khi Hibernate insert hàng entity | Thay `INSERT` mặc định |
| `@SQLUpdate` | SQL khi Hibernate update hàng entity | Thay `UPDATE` mặc định |
| `@SQLDelete` | SQL khi Hibernate delete hàng entity | Thay `DELETE` mặc định; có thể dùng `UPDATE` để xóa mềm |

Các annotation này là **tính năng của Hibernate**, không thuộc chuẩn Jakarta Persistence/JPA. Nếu chuyển provider khác, code sẽ phải thay thế hoặc điều chỉnh.

Ví dụ minh họa ba cú pháp trên một entity tối giản có ID tự gán và một trường persistent:

~~~java
import jakarta.persistence.*;
import org.hibernate.annotations.SQLDelete;
import org.hibernate.annotations.SQLInsert;
import org.hibernate.annotations.SQLUpdate;

@Entity
@Table(name = "catalog_flags")
@SQLInsert(sql = """
    INSERT INTO catalog_flags (enabled, id)
    VALUES (?, ?)
    """)
@SQLUpdate(sql = """
    UPDATE catalog_flags SET enabled = ?
    WHERE id = ?
    """)
@SQLDelete(sql = """
    DELETE FROM catalog_flags
    WHERE id = ?
    """)
public class CatalogFlag {

    @Id
    private Long id;

    @Column(nullable = false)
    private boolean enabled;

    protected CatalogFlag() {}

    public CatalogFlag(Long id, boolean enabled) {
        this.id = id;
        this.enabled = enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

Ví dụ cố tình giữ **chỉ hai cột persistent: `enabled` và `id`**, không có `@Version` hoặc ID tự sinh để minh họa ý tưởng về tham số. Những câu lệnh này gần như trùng SQL mặc định, nên trong ứng dụng thật **không có lý do tốt để ghi đè chỉ nhằm lặp lại SQL Hibernate đã tạo**.

Với entity phức tạp, cấu hình cột thứ cấp, cột sinh bởi database, khóa phiên bản hoặc ID tự động, danh sách và thứ tự dấu `?` có thể thay đổi. Không được lấy ví dụ tối giản làm mẫu sao chép nguyên xi.

### 2.1. Hibernate vẫn quyết định lúc nào chạy SQL

`@SQLUpdate` không buộc Hibernate gửi UPDATE khi setter được gọi. Nếu entity không có thay đổi persistent hoặc không được Hibernate coi là cần update, câu SQL tùy chỉnh có thể **không chạy**.

Tương tự, `@SQLDelete` được áp dụng khi Hibernate thực hiện thao tác delete entity theo vòng đời thích hợp. Nó không có nghĩa mọi câu SQL xóa hàng từ bất kỳ nguồn nào đều tự biến thành câu tùy chỉnh.

### 2.2. Annotation khai báo SQL tĩnh

Chuỗi trong `sql = "..."` được khai báo tại mapping. Giá trị entity vẫn được Hibernate bind vào các tham số `?`. Không nối trực tiếp dữ liệu người dùng vào câu SQL, và không xem annotation như công cụ thay đổi tên bảng hoặc điều kiện truy vấn theo tham số nghiệp vụ ở mỗi request.

Nếu cần thao tác khác nhau theo từng trạng thái hoặc request, hãy cân nhắc dùng phương thức domain, service, SQL riêng có tham số, converter, event, hoặc cơ chế Hibernate thích hợp thay vì cố nhét mọi nhánh nghiệp vụ vào SQL DML tĩnh.

## 3. Thứ tự dấu hỏi (?) là hợp đồng rất chặt

Một vấn đề quan trọng của custom SQL: **Hibernate bind tham số theo thứ tự mà metadata của nó quy định**, không theo tên biến Java bạn tự chọn.

Ví dụ:

~~~java
@SQLUpdate(sql = """
    UPDATE catalog_flags SET enabled = ?
    WHERE id = ?
    """)
~~~

SQL yêu cầu dấu `?` thứ nhất nhận `enabled` và dấu `?` thứ hai nhận `id`. Nếu viết nhầm:

~~~sql
UPDATE catalog_flags
SET id = ?
WHERE enabled = ?;
~~~

mà Hibernate vẫn bind theo thứ tự ban đầu, database có thể nhận giá trị sai loại, update sai hàng hoặc phát lỗi. **SQL có số dấu hỏi đúng chưa chắc đã đúng nghĩa.**

Với Hibernate custom DML, các cột dùng để định vị hàng, như khóa chính và các cột kiểm tra optimistic locking, có vị trí tham số do Hibernate quy định. Các thuộc tính khác cũng có thứ tự dựa trên mapping Hibernate; **không nên đoán từ thứ tự field hiển thị trong class**.

Đặc biệt, khi entity có:

- Khóa chính tổng hợp (`@EmbeddedId`, `@IdClass`);
- `@Version`;
- Thuộc tính kiểu composite/embeddable;
- Nhiều bảng (`@SecondaryTable`);
- Cột do database tạo;
- Kế thừa hoặc association phức tạp;

thì số lượng và thứ tự bind có thể khác ví dụ đơn giản. Câu SQL tùy chỉnh phải phù hợp với **đúng phiên bản Hibernate và mapping hiện tại**.

### 3.1. Cách tiếp cận khi triển khai

Trước khi thay SQL:

1. Xác định mapping entity, cột persistent và cột thuộc từng bảng.
2. Quan sát SQL do Hibernate sinh trước khi override.
3. Xác nhận các JDBC bind parameter mà Hibernate mong đợi cho thao tác tương ứng.
4. Viết SQL tùy chỉnh với số `?`, thứ tự và kiểu JDBC phù hợp.
5. Xem kết quả thực tế trong môi trường test với database/driver tương tự production.
6. Xem lại mapping mỗi khi bổ sung cột, version hoặc thay đổi chiến lược ID.

Ở Hibernate 6, logger SQL và logger bind có thể hỗ trợ quan sát:

~~~yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

Chỉ bật binding log chi tiết trong môi trường phù hợp vì nó có thể chứa dữ liệu nhạy cảm. Cũng cần hiểu rằng SQL tùy chỉnh có thể khó suy luận hơn từ log so với SQL do Hibernate tự sinh; khi cần hãy kiểm tra giá trị được ghi vào database.

## 4. @SQLInsert: tùy chỉnh cách tạo hàng

`@SQLInsert` thay câu INSERT do Hibernate phát ra cho entity/bảng được ánh xạ. Các trường hợp có thể dùng:

- Cần gọi stored procedure ghi dữ liệu do database quy định.
- Tương thích với schema legacy yêu cầu biểu thức SQL đặc biệt khi insert.
- Có lý do cụ thể để đưa một phép biến đổi vào SQL.
- Cần thao tác database chuyên biệt mà mapping thông thường không diễn đạt được.

Ví dụ về ý định:

~~~java
@SQLInsert(sql = """
    INSERT INTO catalog_flags (enabled, id)
    VALUES (?, ?)
    """)
~~~

Ở đây application tiếp tục gọi `persist()`; Hibernate dùng SQL đã khai báo thay SQL INSERT mà nó tự tạo.

### 4.1. ID tự sinh là rủi ro quan trọng

Khi ID được database tạo, chẳng hạn:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Hibernate có kỳ vọng cụ thể về **cách nhận khóa mới** từ lệnh INSERT. Một custom INSERT dùng stored procedure, `RETURNING` hoặc cấu trúc khác phải tương thích cơ chế lấy ID của Hibernate và JDBC driver.

Không nên tùy ý thêm `@SQLInsert` cho entity dùng IDENTITY rồi giả định Hibernate luôn đọc được ID sau đó. Nếu mục tiêu chỉ là điền một giá trị default, thường nên dùng database default, mapping generated value hoặc callback phù hợp mà không cần thay toàn bộ INSERT.

### 4.2. Cột default và giá trị sinh ở database

Ví dụ bảng có:

~~~sql
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
~~~

Nếu một INSERT tùy chỉnh **không gửi** cột `created_at`, database có thể sinh giá trị, nhưng entity Java đang managed chưa chắc lập tức có timestamp chính xác đó.

Cần xem xét:

- Hibernate có biết cột được database generate không?
- Có mapping generated value tương ứng không?
- Khi nào cần đọc lại giá trị?
- Có cần `refresh()` hoặc truy vấn bổ sung không?
- Giá trị của object trong persistence context có đồng bộ với database sau INSERT không?

Một cách khai báo có thể dùng annotation Hibernate `@Generated` cho thuộc tính database-generated theo phiên bản đang dùng; với các mapping khác, có thể cần cơ chế lấy giá trị phát sinh riêng. **Viết INSERT thành công chưa đồng nghĩa trạng thái Java đã đúng.**

### 4.3. Không biến @SQLInsert thành upsert tùy tiện

Một yêu cầu dễ gặp: “nếu chưa có thì insert, nếu đã có thì update”. Một số database hỗ trợ `INSERT ... ON CONFLICT ...` hoặc `ON DUPLICATE KEY UPDATE`. Tuy nhiên, đưa upsert vào `@SQLInsert` không tự làm Hibernate hiểu rằng entity đã tồn tại.

Hibernate vẫn đang thực hiện **một thao tác INSERT trong vòng đời ORM**; nó có kỳ vọng về số hàng ảnh hưởng, identity, version, callback và cache. Nếu SQL thực tế lại cập nhật hàng cũ hoặc bỏ qua insert, object managed có thể không khớp thực tế.

Đối với upsert nghiệp vụ, thường nên có repository method/native SQL riêng và thiết kế rõ cách đồng bộ persistence context, xử lý khóa và kết quả trả về; chỉ dùng `@SQLInsert` cho trường hợp này khi đã hiểu đầy đủ hợp đồng của Hibernate.

## 5. @SQLUpdate: tùy chỉnh SQL khi entity thay đổi

`@SQLUpdate` can thiệp câu UPDATE Hibernate phát khi entity managed cần đồng bộ thay đổi persistent.

Ví dụ một entity chỉ có `id` và `enabled`:

~~~java
@SQLUpdate(sql = """
    UPDATE catalog_flags
    SET enabled = ?
    WHERE id = ?
    """)
~~~

Hibernate vẫn dùng dirty checking để quyết định có cần UPDATE; annotation chỉ định **câu SQL nào sẽ được thực thi khi UPDATE được lên lịch**.

### 5.1. SQL tùy chỉnh không thay dirty checking

Giả sử entity có:

~~~java
CatalogFlag flag = entityManager.find(CatalogFlag.class, id);
flag.setEnabled(true);
~~~

Nếu `enabled` ban đầu đã là `true`, Hibernate có thể không nhận diện một thay đổi persistent cần update. Một phép tính audit đặt bên trong custom UPDATE **sẽ không tự chạy** trong trường hợp không có update.

Vì vậy, dùng custom SQL để biểu diễn một hành vi như “ghi lại mọi lần người dùng nhấn nút”, dù dữ liệu không thay đổi, có thể không phù hợp. Hành vi đó cần một thao tác nghiệp vụ tường minh, ví dụ insert audit event qua service hoặc truy vấn riêng.

### 5.2. Khi SQL cập nhật thêm cột ngoài state Java

Ví dụ một ý định hợp lý là để database cập nhật timestamp:

~~~sql
UPDATE catalog_flags
SET enabled = ?,
    updated_at = CURRENT_TIMESTAMP
WHERE id = ?;
~~~

Nhưng nếu entity cũng có `updatedAt`, object managed sau flush có thể **vẫn giữ giá trị cũ** nếu Hibernate không biết đây là cột do database sinh.

Tùy cấu hình, nên đánh dấu cột là generated để Hibernate đọc lại, hoặc chủ động `refresh()` sau flush khi cần. Đừng giả định database trigger hay biểu thức `CURRENT_TIMESTAMP` làm field Java tự đổi.

### 5.3. Cột không cập nhật được và mapping riêng

Nếu một field khai báo:

~~~java
@Column(name = "external_code", updatable = false)
private String externalCode;
~~~

thì Hibernate không xem nó như một giá trị nên ghi lại trong UPDATE thông thường. Khi tự viết SQL, phải bảo đảm **không vô tình phá** ngữ nghĩa read-only hoặc cập nhật trường mà ứng dụng hứa không thay đổi.

Tương tự, nếu entity có nhiều cột persistent nhưng custom UPDATE chỉ cập nhật một phần, thay đổi những field còn lại có thể bị **mất âm thầm**: Hibernate có thể cho rằng thao tác update đã hoàn thành, trong khi SQL không ghi hết dữ liệu mà ứng dụng vừa thay đổi.

Vì vậy, custom UPDATE phải phù hợp với toàn bộ nhóm thuộc tính Hibernate dự kiến đồng bộ hoặc phải có chiến lược tách mapping/chỉnh mô hình có chủ đích.

## 6. @SQLDelete: tùy chỉnh cách xóa hàng

`@SQLDelete` cho phép Hibernate thực thi một SQL khác khi entity được xóa qua vòng đời ORM. Nó có thể là DELETE đặc biệt, stored procedure, hoặc một UPDATE đánh dấu xóa mềm.

Ví dụ thông thường:

~~~java
@SQLDelete(sql = """
    DELETE FROM catalog_flags
    WHERE id = ?
    """)
~~~

Không có lợi ích khi câu SQL y hệt mặc định, nhưng cơ chế này trở nên hữu ích khi muốn **soft delete**.

### 6.1. Soft delete: thay DELETE bằng UPDATE

Xóa mềm nghĩa là giữ hàng vật lý, nhưng đánh dấu hàng không còn được hiển thị trong các truy vấn nghiệp vụ thông thường:

~~~sql
UPDATE documents
SET deleted = true
WHERE id = ?;
~~~

Một mapping Hibernate 6 minh họa:

~~~java
import jakarta.persistence.*;
import org.hibernate.annotations.SQLDelete;
import org.hibernate.annotations.SQLRestriction;

@Entity
@Table(name = "documents")
@SQLDelete(sql = """
    UPDATE documents SET deleted = true
    WHERE id = ?
    """)
@SQLRestriction("deleted = false")
public class Document {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @Column(nullable = false)
    private boolean deleted = false;

    protected Document() {}

    public Document(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
~~~

Để tránh làm phức tạp thứ tự bind, ví dụ này **chưa có `@Version`**. Mỗi hàng chỉ có một khóa chính đơn; SQL delete tùy chỉnh dùng một tham số ID.

Khi ứng dụng gọi:

~~~java
Document document = entityManager.find(Document.class, id);
entityManager.remove(document);
entityManager.flush();
~~~

Hibernate sẽ thực thi SQL dạng `UPDATE documents SET deleted = true WHERE id = ?` thay vì xóa vật lý hàng. Đồng thời, thao tác `remove()` vẫn có ý nghĩa **xóa entity khỏi persistence context** theo vòng đời JPA. Bạn không nên tiếp tục coi object vừa remove là một entity managed bình thường chỉ vì database giữ lại hàng.

### 6.2. @SQLRestriction xử lý mặt đọc, @SQLDelete xử lý mặt ghi

Nếu chỉ có:

~~~java
@SQLDelete(sql = """
    UPDATE documents SET deleted = true WHERE id = ?
    """)
~~~

thì câu delete đã đổi sang update, nhưng các query khác **vẫn có thể đọc hàng `deleted = true`**. Vì vậy nhiều cách triển khai soft delete cũ cần thêm điều kiện lọc trên các câu truy vấn.

Hibernate cung cấp `@SQLRestriction("deleted = false")` trong những phiên bản hỗ trợ annotation này để bổ sung điều kiện lọc tĩnh theo mapping:

~~~java
@SQLRestriction("deleted = false")
~~~

Điều kiện này là **SQL fragment**, không phải JPQL, và không hỗ trợ tham số động như một Hibernate filter có parameter. Nó thường phù hợp khi mọi lần đọc qua entity này đều phải loại hàng đã xóa.

Một số giới hạn quan trọng:

- Điều kiện tĩnh có thể khiến màn hình quản trị cần xem hàng đã xóa phải dùng một đường truy cập khác có chủ đích.
- Truy vấn **native SQL tự viết** không tự có điều kiện này.
- Những thao tác bulk DML có đường đi riêng so với entity lifecycle.
- Logic soft delete còn có thể ảnh hưởng association, cascade, uniqueness và xóa bản ghi con.

Với Hibernate mới có hỗ trợ **`@SoftDelete`** (từ dòng Hibernate 6.4), nên cân nhắc khả năng tích hợp sẵn thay cho tự ghép `@SQLDelete` và điều kiện lọc. API, phạm vi và giới hạn cụ thể phụ thuộc phiên bản Hibernate; không nên trộn hai cơ chế tùy ý trong một entity.

### 6.3. Xóa mềm không biến database thành “đã xóa”

Sau `remove()`:

- Hàng trong database **vẫn tồn tại** với `deleted = true`.
- Một query Hibernate có filter sẽ không trả hàng đó trong tập dữ liệu thông thường.
- Một native query không lọc có thể vẫn tìm thấy hàng.
- Các khóa ngoại của bảng khác vẫn có thể tham chiếu hàng.
- UNIQUE constraint áp dụng trên toàn bảng vẫn coi giá trị ở hàng đã xóa là đang chiếm chỗ.
- Kho lưu trữ tăng theo thời gian nếu không có chính sách purge/archive.

Ví dụ PostgreSQL khi muốn chỉ bắt buộc mã tài liệu duy nhất giữa những hàng chưa bị xóa:

~~~sql
CREATE UNIQUE INDEX ux_documents_active_code
ON documents (code)
WHERE deleted = false;
~~~

Cú pháp **partial unique index** trên là đặc thù PostgreSQL. Điều kiện duy nhất trên hàng active phải được thiết kế theo nhu cầu nghiệp vụ và DB đang dùng; `@SQLDelete` không tự tạo index đó.

## 7. Kiểm tra số hàng ảnh hưởng: SQL chạy không có nghĩa thao tác đúng

Một lệnh `UPDATE ... WHERE id = ?` có thể hoàn tất không lỗi nhưng ảnh hưởng **0 hàng**. Điều này có thể xảy ra khi:

- Hàng đã bị xóa bởi transaction khác.
- Điều kiện version không còn khớp.
- Tenant hoặc predicate bảo vệ không khớp.
- Dữ liệu bị thay đổi trước đó.
- Câu SQL custom viết sai điều kiện WHERE.

Nếu Hibernate cho rằng đã update hoặc delete một entity tồn tại, nhưng database không thay đổi hàng nào, trạng thái ORM có thể trở nên không nhất quán.

### 7.1. Expectation kiểm tra row count

Trong các phiên bản Hibernate mới có hỗ trợ thuộc tính `verify` trên annotation custom DML, có thể cấu hình kỳ vọng kiểm tra row count:

~~~java
import org.hibernate.jdbc.Expectation;

@SQLDelete(
    sql = "UPDATE documents SET deleted = true WHERE id = ?",
    verify = Expectation.RowCount.class
)
~~~

Cấu hình này yêu cầu Hibernate kiểm tra kết quả thao tác thông qua expectation phù hợp. Với SQL dạng update một entity theo khóa đơn, thường kỳ vọng ảnh hưởng **1 hàng**. Khi số hàng không khớp, Hibernate có cơ chế báo lỗi/stale state tương ứng, giúp ứng dụng tránh giả định rằng update đã thành công.

**Chi tiết API phụ thuộc phiên bản Hibernate.** Một số phiên bản cũ sử dụng thuộc tính `check` cùng `ResultCheckStyle`; các phiên bản mới dùng `verify` và lớp `Expectation`. Cần chọn cú pháp phù hợp đúng Hibernate version trong dự án.

Không nên luôn áp dụng “phải đúng 1 hàng” cho stored procedure hoặc lệnh đặc biệt có ngữ nghĩa row count khác. Với các thao tác đó, xác định expectation/điều kiện thành công rõ ràng trước khi thiết kế SQL custom.

### 7.2. Tác động với optimistic locking

Nếu entity có:

~~~java
@Version
private long version;
~~~

Hibernate mặc định thường dùng version trong `WHERE` khi cập nhật/xóa để phát hiện sửa đổi cạnh tranh:

~~~sql
UPDATE documents
SET title = ?, version = ?
WHERE id = ? AND version = ?;
~~~

Hoặc:

~~~sql
DELETE FROM documents
WHERE id = ? AND version = ?;
~~~

Khi thay DML, bạn phải bảo toàn ngữ nghĩa tương ứng. Nếu viết custom DELETE chỉ có:

~~~sql
DELETE FROM documents WHERE id = ?;
~~~

thì có thể **làm mất kiểm tra version**, thậm chí số placeholder cũng không khớp kỳ vọng Hibernate.

Với soft delete trên entity versioned, một thiết kế có thể cần logic kiểu:

~~~sql
UPDATE documents
SET deleted = true,
    version = version + 1
WHERE id = ?
  AND version = ?;
~~~

Đây là **mẫu SQL giải thích ý tưởng**, không phải một đoạn annotation hoàn chỉnh để dán vào mọi mapping. Cần đối chiếu thứ tự bind chính xác mà Hibernate yêu cầu đối với ID và version, cách Hibernate quản lý version khi delete và cơ chế xác minh row count.

Điều kiện version và việc kiểm tra số hàng ảnh hưởng bổ trợ cho nhau: `WHERE version = ?` giới hạn cập nhật vào phiên bản mong đợi; kiểm tra row count phát hiện trường hợp phiên bản không khớp.

## 8. Trạng thái entity trong persistence context sau custom DML

Hibernate duy trì một **persistence context** (first-level cache) chứa những entity đang managed và snapshot cần thiết cho dirty checking. Một SQL custom có thể làm database thay đổi theo cách Hibernate không hiểu đầy đủ.

Ví dụ trong một transaction:

~~~java
Document doc = entityManager.find(Document.class, documentId);
String original = doc.getTitle();
~~~

Sau đó một câu SQL tùy chỉnh hoặc trigger trong database thay đổi `title`. Object `doc` **không tự cập nhật** chỉ vì hàng DB đã đổi. Khi gọi:

~~~java
Document again = entityManager.find(Document.class, documentId);
~~~

trong cùng persistence context, Hibernate thường trả về **chính instance đã managed** và có thể không gửi truy vấn mới. Giá trị `title` có thể vẫn là giá trị cũ.

### 8.1. Khi nào cần flush, refresh hoặc clear?

| Phương thức | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `flush()` | Đồng bộ các thay đổi persistent đang chờ của context tới DB | Không tự làm managed object nhận mọi giá trị DB vừa được trigger tính |
| `refresh(entity)` | Đọc lại trạng thái persistent của entity từ DB | Cần entity còn managed và hợp lệ để refresh |
| `clear()` | Detach toàn bộ managed entities khỏi context | Mọi thay đổi chưa flush có thể bị mất khỏi kế hoạch đồng bộ |
| `detach(entity)` | Detach một entity cụ thể | Entity cũ vẫn giữ giá trị trong RAM nhưng không còn managed |

Nếu custom SQL làm thay đổi cột mà Hibernate không biết, có thể dùng `refresh()` sau khi flush nếu entity vẫn còn managed và đọc được từ DB. Nếu vừa gọi `remove()`, entity đang ở trạng thái removed; **không nên cố refresh nó như một managed entity bình thường**. Khi cần quan sát trạng thái soft-deleted, hãy dùng một transaction mới hoặc một truy vấn chuyên dụng phù hợp với filter hiện có.

### 8.2. Cột generated phải có hợp đồng mapping

Một cách bền vững hơn việc gọi `refresh()` khắp service là khai báo rõ rằng cột được database generate hoặc cập nhật trong các sự kiện thích hợp, dùng khả năng mapping của Hibernate mà phiên bản đang hỗ trợ, chẳng hạn `@Generated`.

Ví dụ nếu SQL custom tự tăng `last_modified_at` tại database, Hibernate cần có cơ chế đọc lại hoặc biết field đó không còn mang giá trị do Java tự gán.

Tránh tình huống:

1. Java đổi `status`.
2. SQL custom đồng thời đổi `calculated_total`.
3. Hibernate vẫn giữ `calculatedTotal` cũ.
4. Service đọc từ entity rồi trả response dựa trên giá trị cũ.
5. Đến transaction sau dữ liệu mới xuất hiện, gây hành vi khó giải thích.

### 8.3. Second-level cache và query cache

First-level cache thuộc một `Session`/`EntityManager`. Nếu ứng dụng bật **second-level cache** hoặc query cache, những thay đổi ngoài cơ chế Hibernate hiểu cũng có thể làm cache liên phiên bị cũ.

Custom SQL do Hibernate thực thi trong entity lifecycle có một số cơ chế phối hợp với hành động entity. Nhưng **đừng mặc định mọi cột, mọi bảng hay mọi kết quả đọc gián tiếp mà câu SQL tự viết tác động đều được cache invalidation chính xác**.

Đặc biệt cần cảnh giác khi SQL custom:

- Cập nhật thêm bảng khác ngoài bảng Hibernate nghĩ đang ghi.
- Gọi stored procedure thay đổi nhiều entity.
- Kích hoạt trigger cập nhật bảng tổng hợp.
- Thay đổi cột mà mapping Hibernate đánh dấu không được cập nhật.

Trong những trường hợp đó, cần thiết kế đồng bộ/cache eviction/refresh và giao dịch phù hợp, hoặc tránh đặt những hiệu ứng phụ rộng trong DML của một entity.

## 9. Vòng đời JPA vẫn có ý nghĩa

Khi gọi `persist()`, `remove()` hoặc thay đổi một entity managed, Hibernate còn có thể áp dụng:

- Entity state transitions: transient, managed, removed, detached.
- Dirty checking.
- Callback như `@PrePersist`, `@PostPersist`, `@PreUpdate`, `@PostUpdate`, `@PreRemove`, `@PostRemove` theo các điều kiện JPA.
- Cascade của quan hệ khi được cấu hình.
- Optimistic locking.
- Xử lý transaction và flush.

Thay SQL bằng `@SQLDelete` **không có nghĩa** xóa mềm trở thành một thao tác update entity theo mọi khía cạnh callback. Ở tầng lifecycle, Hibernate đang xử lý yêu cầu `remove(entity)`, dù SQL là UPDATE.

Ví dụ:

~~~java
@PreRemove
private void beforeRemove() {
    // Callback của thao tác remove entity.
}
~~~

Với soft delete qua `@SQLDelete`, `@PreRemove` có thể vẫn là callback phù hợp vì sự kiện ORM là remove. Không nên kỳ vọng `@PreUpdate` sẽ được gọi chỉ vì câu SQL thực tế có từ `UPDATE`.

Ngược lại, SQL do database trigger thực hiện sẽ **không gọi ngược** lifecycle callback Java cho những entity khác mà trigger vô tình cập nhật.

### 9.1. Cascade vẫn phải phản ánh nghiệp vụ

Giả sử `Order` có `OrderLine` với `cascade = REMOVE`. Khi xóa Order qua Hibernate, cascade remove có thể dẫn đến các thao tác xóa đối với OrderLine. Nhưng nếu chỉ Order được gắn `@SQLDelete`, còn OrderLine vẫn dùng DELETE thật, kết quả có thể là:

- Order được đánh dấu `deleted = true`.
- Các dòng hàng bị xóa vật lý, tùy mapping cascade.

Đây có thể là kết quả mong muốn, hoặc có thể làm mất thông tin lịch sử mà bạn định giữ. Vì thế, **soft delete cần được thiết kế ở cấp aggregate**, không chỉ thêm annotation cho một class rồi xem như hoàn tất.

### 9.2. Database cascade không thay Java cascade

FK `ON DELETE CASCADE` do database thực hiện khi có DELETE vật lý hàng cha. Nếu `@SQLDelete` chuyển thao tác thành UPDATE, **database không nhận một DELETE cha**, nên FK `ON DELETE CASCADE` thông thường không tự kích hoạt theo cách cũ.

Nếu hệ thống trước đây dựa vào `ON DELETE CASCADE` để xóa child khi xóa parent, đổi sang soft delete có thể làm những hàng child còn nguyên. Cần cân nhắc chiến lược lọc/soft delete child riêng, ràng buộc FK và truy vấn liên quan.

## 10. Native SQL và bulk DML đi đường khác

Đây là nguồn lỗi dễ bị bỏ qua: **custom SQL của entity không thay thế mọi đường ghi vào bảng**.

Ví dụ:

~~~java
entityManager.createQuery("""
    UPDATE Document d
    SET d.title = :title
    WHERE d.id = :id
    """)
    .setParameter("title", "New title")
    .setParameter("id", id)
    .executeUpdate();
~~~

Đây là JPQL **bulk UPDATE**. Nó thao tác theo tập hàng ở database và không áp dụng dirty checking/lifecycle entity như việc tìm entity rồi gọi setter. Do đó, đừng mặc định `@SQLUpdate` của entity sẽ được áp dụng cho bulk update.

Tương tự:

~~~java
entityManager.createQuery("""
    DELETE FROM Document d
    WHERE d.id = :id
    """)
    .setParameter("id", id)
    .executeUpdate();
~~~

Đây là bulk DELETE; không thể dựa vào `@SQLDelete` để bảo đảm nó tự biến thành soft delete như `entityManager.remove(entity)`. Khi thiết kế xóa mềm, cần **kiểm soát tất cả đường xóa**, gồm JPQL/HQL bulk delete, repository batch-delete và SQL direct từ các công cụ khác.

Native SQL:

~~~java
entityManager.createNativeQuery("""
    DELETE FROM documents WHERE id = :id
    """)
    .setParameter("id", id)
    .executeUpdate();
~~~

là lệnh bạn viết trực tiếp. Nó không tự dùng annotation `@SQLDelete` của entity.

### 10.1. Bulk DML có thể làm entity managed bị cũ

Giả sử một `Document` đã được nạp trong persistence context, sau đó bulk UPDATE đổi dữ liệu hàng đó. Object đã nạp có thể giữ snapshot cũ.

Một cách xử lý tùy use case:

~~~java
entityManager.flush();

int changed = entityManager.createQuery("""
    UPDATE Document d
    SET d.title = :newTitle
    WHERE d.id = :id
    """)
    .setParameter("newTitle", "Updated")
    .setParameter("id", id)
    .executeUpdate();

entityManager.clear();
~~~

`flush()` đảm bảo các thay đổi persistent đang chờ được đồng bộ trước thao tác bulk. `clear()` detach các entity cũ để những lần đọc tiếp phải nạp lại. Tuy nhiên, thao tác này có ảnh hưởng tới mọi entity managed trong context, nên phải đặt ở ranh giới nghiệp vụ hợp lý.

Nếu hệ thống dùng soft delete, bulk delete nên được thay bằng **bulk update với cờ deleted và các điều kiện version/tenant phù hợp**, hoặc dùng một API chuyên biệt thay vì `DELETE FROM` tùy tiện.

## 11. Transaction và concurrency: giữ đúng ngữ nghĩa

Custom DML chạy trong transaction Hibernate đang sử dụng. Nhưng chính bạn phải bảo đảm SQL **đúng tính nguyên tử và điều kiện thành công** của thao tác.

### 11.1. SQL phải chạy trong transaction phù hợp

Nếu Hibernate thực thi SQL custom khi flush, nó tham gia transaction của session theo cấu hình thông thường. Với Spring, transaction có thể do `@Transactional` quản lý:

~~~java
@Service
public class DocumentService {

    private final EntityManager em;

    public DocumentService(EntityManager em) {
        this.em = em;
    }

    @Transactional
    public void removeDocument(Long id) {
        Document document = em.find(Document.class, id);

        if (document == null) {
            throw new IllegalArgumentException("Không tìm thấy tài liệu");
        }

        em.remove(document);
    }
}
~~~

Ứng dụng không cần tự gọi JDBC `commit()` trong annotation. Điều quan trọng là transaction manager nhận được lỗi khi câu SQL tùy chỉnh không thỏa kỳ vọng, để rollback phù hợp.

### 11.2. Race condition khi xóa mềm

Hai request có thể cùng tải một document active và cùng xóa. Nếu SQL là:

~~~sql
UPDATE documents
SET deleted = true
WHERE id = ?;
~~~

cả hai lệnh có thể đều báo ảnh hưởng một hàng, vì một số database vẫn tính UPDATE trùng giá trị là update. Nếu nghiệp vụ yêu cầu phát hiện “đã xóa rồi”, có thể cân nhắc thêm điều kiện:

~~~sql
UPDATE documents
SET deleted = true
WHERE id = ?
  AND deleted = false;
~~~

Lúc này thao tác xóa lần hai có thể ảnh hưởng 0 hàng. Khi dùng expectation kiểm tra row count, ứng dụng cần quyết định 0 hàng là **lỗi cạnh tranh** hay một thao tác **idempotent** được chấp nhận. Không có chính sách đúng cho mọi nghiệp vụ.

Nếu entity versioned, có thể cần cả điều kiện version để phát hiện cập nhật cạnh tranh. Việc thêm điều kiện/placeholder tùy ý vào annotation phải tương thích đúng cách Hibernate bind tham số.

### 11.3. Multi-tenancy và điều kiện bảo vệ dữ liệu

Trong ứng dụng đa tenant, một câu custom SQL chỉ có:

~~~sql
UPDATE documents SET deleted = true WHERE id = ?;
~~~

có thể không đủ nếu ID chỉ duy nhất trong từng tenant hoặc quyền ghi phải bị giới hạn bởi `tenant_id`. Điều kiện tenant, database row-level security, discriminator multi-tenancy hoặc mapping Hibernate phải bảo đảm đúng giới hạn truy cập.

Cần kiểm tra **hành vi cụ thể của custom SQL đối với mô hình multi-tenancy**. Không nên giả định một filter của SELECT tự được chèn vào mọi câu DML tĩnh. Thiết kế an toàn có thể cần query rõ điều kiện tenant hoặc cơ chế bảo vệ database độc lập với SQL Hibernate tạo.

### 11.4. Trigger và side effects

Nếu một stored procedure hoặc trigger làm thay đổi bảng khác, transaction có thể bao phủ những thao tác đó, nhưng Hibernate chưa chắc biết:

- Những entity nào cần refresh.
- Query cache nào cần invalidated.
- Version hoặc timestamp nào thay đổi.
- Callback nghiệp vụ nào không được gọi.

Vì thế, side effect của custom SQL phải được tài liệu hóa và kết hợp với chiến lược đồng bộ. Nếu logic quá rộng, việc đặt nó ở application service hoặc một repository command riêng có thể minh bạch hơn.

## 12. Câu SQL tùy chỉnh ảnh hưởng schema như thế nào?

Khi dùng SQL do Hibernate tự sinh, mapping metadata thường là nguồn hướng dẫn chính cho cột và kiểu JDBC. Với custom DML, câu SQL lại chứa trực tiếp:

- Tên bảng và tên cột.
- Hàm SQL của database.
- Danh sách cột cần bind.
- Predicate WHERE.
- Cú pháp `RETURNING`, stored procedure hoặc cast nếu có.

Nếu migration đổi tên cột từ `deleted` sang `is_deleted` nhưng annotation vẫn ghi `deleted`, code có thể compile bình thường rồi **hỏng khi chạy DML**.

### 12.1. Hạn chế tính di động

Ví dụ PostgreSQL:

~~~sql
UPDATE documents
SET deleted_at = now()
WHERE id = ?;
~~~

Cú pháp `now()` và các hàm thời gian khác không nhất thiết giống nhau trên mọi database. Tương tự, `RETURNING`, `ON CONFLICT`, CTE dùng trong DML hoặc named function có thể phụ thuộc dialect.

Nếu ứng dụng chạy trên nhiều DB vendor, custom SQL nhiều khi là khoản chi phí bảo trì cần chủ động chấp nhận. DML mặc định do Hibernate/dialect sinh có lợi thế giảm phụ thuộc SQL riêng của database.

### 12.2. Nhiều bảng và secondary table

Một entity có `@SecondaryTable` hoặc kế thừa theo JOINED có thể cần ghi nhiều bảng. Khi đó custom DML thường phải xem xét **đúng bảng mục tiêu** và cách Hibernate xử lý thứ tự insert/update/delete giữa các bảng.

Những phiên bản Hibernate có hỗ trợ tham số `table` trong annotation custom DML để nhắm tới bảng nhất định. Không nên lấy một câu `@SQLUpdate` cho bảng chính rồi giả định nó sẽ thay tất cả SQL ghi vào secondary table hoặc bảng subtype.

Cần xem mapping và API chính xác của Hibernate version trong dự án khi override từng bảng, đồng thời bảo đảm khóa ngoại và thứ tự thao tác hợp lệ.

### 12.3. Association và collection table

Các thao tác thêm/xóa phần tử trong bảng liên kết hoặc collection table có thể không đi qua `@SQLInsert`/`@SQLDelete` của entity chứa collection theo cách bạn mong đợi. Hibernate có các cơ chế riêng để tùy chỉnh SQL cho collection/join table ở những phiên bản tương ứng.

Ví dụ thêm một phần tử vào `@ManyToMany` thường là insert hàng trong **join table**, không phải insert entity đích. Khi cần custom SQL ở đó, phải chọn mapping annotation tương ứng, không áp dụng nhầm entity-level DML.

## 13. Cùng một yêu cầu, những giải pháp khác có thể phù hợp hơn

Không phải lần nào cần khác SQL mặc định cũng nên thay toàn bộ DML.

| Yêu cầu | Cách nên cân nhắc | Lý do |
| --- | --- | --- |
| Xóa mềm đơn giản | Hibernate `@SoftDelete` nếu phiên bản hỗ trợ, hoặc `@SQLDelete` + điều kiện lọc | Cần đồng bộ hành vi ghi và đọc |
| Cập nhật timestamp tự động | Database default/trigger + mapping generated, hoặc callback | Không nhất thiết thay cả câu UPDATE |
| Biến đổi một giá trị trước khi lưu | `AttributeConverter` hoặc custom type | Tập trung vào mapping giá trị |
| Chỉ ghi một phần cột | Mapping update semantics, `@DynamicUpdate` khi phù hợp | Giữ Hibernate quản lý DML |
| Update hàng loạt | JPQL/HQL bulk DML hoặc native SQL command | Đơn vị công việc là tập hàng, không phải entity lifecycle |
| Gọi stored procedure nghiệp vụ | Repository/service command rõ ràng hoặc procedure mapping | Có thể cần input/output và nhiều side effect |
| Bổ sung audit trail | Domain event, audit table, trigger hoặc giải pháp auditing | Audit có vòng đời khác entity chính |
| Kiểm soát ghi theo tenant | Transaction/security/row-level security hoặc query có predicate rõ | Bảo vệ dữ liệu là ràng buộc nghiệp vụ và bảo mật |
| Tránh UPDATE khi không đổi | Dirty checking mặc định của Hibernate | Không cần custom SQL |
| Đồng bộ optimistic locking | `@Version` và DML mặc định | Hibernate đã biết quy tắc version |

Đặc biệt với soft delete, chọn giải pháp có khả năng xử lý nhất quán **truy vấn, quan hệ, cascade và bulk operations** quan trọng hơn việc tạo được một câu UPDATE thay DELETE.

## 14. Một ví dụ thiết kế soft delete ở cấp nghiệp vụ

Giả sử hệ thống tài liệu cần:

1. Người dùng bình thường chỉ xem tài liệu active.
2. Xóa tài liệu giữ lịch sử.
3. Admin có thể xem tài liệu đã xóa để khôi phục.
4. Code không xóa vật lý dữ liệu nếu chưa qua quy trình purge.

Nếu gắn `@SQLDelete` và `@SQLRestriction` lên cùng một entity, việc ẩn hàng active có thể thuận tiện nhưng **admin cũng khó đọc hàng deleted qua mapping đã restriction**. Một thiết kế có thể tách hai đường truy cập:

- Entity thông thường dùng filter/soft-delete mapping thích hợp cho nghiệp vụ active.
- Một repository/admin read model hoặc DTO query riêng, có điều kiện bảo mật rõ, cho phép xem bản ghi deleted.
- Lệnh restore được thiết kế riêng và bảo đảm trạng thái trong persistence context được làm mới.
- Purge vật lý là thao tác riêng có kiểm soát, không gọi ngẫu nhiên một bulk delete vào bảng.

Ví dụ restore bằng native SQL minh họa:

~~~java
@Transactional
public boolean restoreDocument(Long id) {
    int changed = entityManager.createNativeQuery("""
        UPDATE documents
        SET deleted = false
        WHERE id = :id
          AND deleted = true
        """)
        .setParameter("id", id)
        .executeUpdate();

    return changed == 1;
}
~~~

Đoạn này cần được dùng trong **service/repository có phân quyền admin** và chính sách cạnh tranh phù hợp. Nếu cùng transaction đã nạp document cũ, cần xử lý cache/persistence context để tránh stale state; nếu mapping restriction khiến document không load được khi deleted, có thể dùng đọc chuyên biệt.

Nếu dự án có Hibernate `@SoftDelete` hỗ trợ soft delete/restore theo nhu cầu, cần đánh giá tính năng và giới hạn thực tế trước khi tự duy trì cơ chế này.

### 14.1. Unique constraint và khôi phục

Giả sử mã tài liệu phải duy nhất giữa các tài liệu active. Khi tài liệu A xóa mềm, người dùng tạo tài liệu B có cùng mã. Sau đó admin muốn restore A.

Nếu database dùng partial unique index chỉ áp dụng `deleted = false`, lệnh restore có thể **vi phạm unique constraint** vì B đang active. Đây là quyết định nghiệp vụ: có thể từ chối restore, yêu cầu đổi mã hoặc thực hiện một quy trình giải quyết xung đột.

`@SQLDelete` không xử lý các quy tắc này; nó chỉ thay SQL của thao tác delete.

## 15. Trạng thái đúng nghĩa là gì?

Trong bài này, “giữ đúng trạng thái” không chỉ nghĩa là database nhận được UPDATE. Cần kiểm soát nhiều lớp trạng thái đồng thời:

~~~mermaid
flowchart LR
    A["Domain state<br/>quy tắc nghiệp vụ"] --> B["Managed entity<br/>persistence context"]
    B --> C["Custom DML<br/>INSERT / UPDATE / DELETE"]
    C --> D[("Database state")]
    D --> E["Đọc lại / cache / truy vấn"]
    E --> A
~~~

| Lớp trạng thái | Điều phải đúng | Ví dụ sai |
| --- | --- | --- |
| Domain | Invariant và lifecycle có ý nghĩa | Đơn hàng đã confirmed vẫn được đổi dòng hàng vì SQL đi tắt |
| Managed entity | Thuộc tính Java phản ánh đúng dữ liệu cần dùng | Trigger đổi timestamp nhưng entity còn timestamp cũ |
| JDBC bind | Mỗi dấu `?` nhận đúng cột, kiểu và vị trí | `id` và `version` bị bind đảo |
| Database | Dữ liệu, constraint và hàng ảnh hưởng đúng | WHERE quá rộng cập nhật nhiều tenant |
| Concurrency | Version và conflict được phát hiện | Custom UPDATE bỏ điều kiện version |
| ORM lifecycle | Cascade, callback, state transition phù hợp | Soft-delete parent nhưng hard-delete child ngoài ý định |
| Query và cache | Các lần đọc sau thấy dữ liệu hợp lý | Hàng deleted vẫn xuất hiện trong native query |
| Vận hành | Migration và logging nhất quán | Đổi tên cột, annotation SQL chưa đổi |

Cần bảo đảm các lớp này có **một hợp đồng rõ ràng**. Custom SQL càng mạnh, càng phải chủ động về những phần Hibernate không còn tự suy luận được.

## 16. Các tình huống dễ mắc lỗi

### 16.1. SQL UPDATE thiếu một cột

Entity có `name` và `price`, nhưng custom SQL chỉ cập nhật `name`. Khi người dùng đổi giá, dirty checking có thể lên lịch UPDATE và SQL vẫn chạy, nhưng database không nhận thay đổi `price`. Khi transaction kết thúc, response có thể hiển thị giá mới từ RAM, còn request sau đọc lại giá cũ.

### 16.2. SQL DELETE thiếu version

Entity có `@Version`, nhưng custom delete chỉ WHERE theo ID. Có thể bỏ qua kiểm tra concurrency hoặc không khớp số tham số Hibernate kỳ vọng. Phải bảo toàn logic version và kiểm tra row count.

### 16.3. Soft delete không lọc truy vấn

`@SQLDelete` đổi DELETE thành UPDATE `deleted = true`, nhưng `findAll()` vẫn đọc cả hàng deleted nếu không có cơ chế lọc. Xóa mềm gồm cả **ghi và đọc**, không chỉ một annotation.

### 16.4. Soft delete cùng cascade không nhất quán

Xóa mềm entity cha nhưng cascade loại bỏ entity con khỏi database. Dữ liệu lịch sử thiếu quan hệ để khôi phục. Thiết kế vòng đời cho toàn aggregate trước khi cấu hình.

### 16.5. Gọi native SQL ngoài hạ tầng ORM

Một stored procedure thay đổi hàng nhưng entity managed đã nạp không đổi. Trong cùng transaction, `em.find()` trả về object cũ. Cần refresh/clear hoặc tránh giữ object đã mất đồng bộ.

### 16.6. Sử dụng bulk delete qua repository

Một phương thức repository thực hiện bulk HQL/SQL DELETE và bỏ qua custom `@SQLDelete` của entity. Hệ thống âm thầm xóa vật lý dữ liệu thay vì xóa mềm. Cần quy định API cho các đường ghi và kiểm tra query thực tế.

### 16.7. Ghi audit trong SQL nhưng không có thay đổi entity

Custom `@SQLUpdate` thêm `updated_at = CURRENT_TIMESTAMP`, nhưng Hibernate không phát UPDATE nếu entity không dirty. Không nên gắn hành vi audit bắt buộc mỗi request vào một UPDATE chỉ xảy ra khi dữ liệu đổi.

### 16.8. Nhầm số hàng ảnh hưởng

SQL có câu điều kiện `WHERE deleted = false`, lần xóa thứ hai ảnh hưởng 0 hàng. Nếu ứng dụng coi “xóa lại” là idempotent success nhưng Hibernate expectation đòi 1 hàng, sẽ báo lỗi. Cần chọn rõ semantics thành công của nghiệp vụ.

## 17. Quy trình triển khai custom DML có kiểm soát

Khi thực sự cần `@SQLInsert`, `@SQLUpdate` hoặc `@SQLDelete`, nên làm theo trình tự sau:

1. **Xác định nhu cầu không đáp ứng được bằng mapping mặc định.** Viết rõ database phải làm thêm điều gì và tại sao.
2. **Xác định entity lifecycle.** Đây là một persist/update/remove entity hay thao tác bulk/command riêng?
3. **Kiểm tra schema và constraints.** Tên bảng/cột, PK, version, FK, tenant, unique, generated columns.
4. **Xác định SQL của đúng phiên bản Hibernate.** Đếm placeholder, thứ tự bind, kết quả trả về và cách lấy generated key.
5. **Chọn cơ chế kiểm tra thành công.** Row count, returned value, version conflict hoặc expectation tương ứng.
6. **Chọn chiến lược đồng bộ state.** Generated mapping, flush/refresh, clear, cache invalidation hoặc thiết kế service không dựa vào object cũ.
7. **Kiểm tra cascade và callback.** Hành vi với entity cha/con và với đường ghi ngoài ORM.
8. **Kiểm soát các đường đọc.** Với soft delete, bao gồm entity query, native SQL, report và admin restoration.
9. **Kiểm tra concurrency và transaction.** Hai request xóa/cập nhật cùng lúc, row count 0, lock, rollback.
10. **Quản lý migration/rollout.** SQL tĩnh trong annotation phải được cập nhật cùng schema database.

Một nguyên tắc tốt là **giữ SQL tùy chỉnh càng hẹp càng tốt**. Khi nhu cầu là một thao tác nghiệp vụ khác biệt, hãy cân nhắc tạo command/repository method riêng thay vì âm thầm thay SQL của mọi thao tác trên entity.

## 18. Bài tập vận dụng

### Bài tập 1 — Chẩn đoán soft delete thiếu điều kiện lọc

Một entity khai báo:

~~~java
@SQLDelete(sql = "UPDATE notes SET deleted = true WHERE id = ?")
@Entity
class Note {
    @Id Long id;
    boolean deleted;
    String body;
}
~~~

Sau khi gọi `remove(note)`, người dùng vẫn nhìn thấy ghi chú qua một query khác. Hãy giải thích vì sao và đề xuất cơ chế lọc phù hợp với phiên bản Hibernate đang dùng. Trường hợp admin cần xem ghi chú đã xóa thì nên thiết kế thế nào?

### Bài tập 2 — Optimistic locking

Entity có `@Id Long id` và `@Version long version`. Một developer tự viết:

~~~sql
UPDATE items SET name = ? WHERE id = ?;
~~~

Hãy nêu vấn đề về tham số, điều kiện version và row count. Vì sao không nên chỉ nhìn SQL chạy thành công để kết luận entity update đúng?

### Bài tập 3 — Database trigger và state trong RAM

Trigger tự cập nhật `updated_at` khi hàng bị UPDATE. Sau khi đổi `name` và flush, entity vẫn có `updatedAt` cũ. Giải thích nguyên nhân và nêu hai cách đồng bộ giá trị đó.

### Bài tập 4 — Cascade và xóa mềm

`Order` dùng `@SQLDelete` để đổi DELETE thành UPDATE `deleted = true`. `OrderLine` được cấu hình cascade REMOVE nhưng không có soft delete. Khi xóa Order qua Hibernate, dữ liệu lịch sử có thể bị ảnh hưởng thế nào? Hãy đề xuất quy tắc lifecycle nhất quán cho cả aggregate.

### Bài tập 5 — Bulk operation

Một repository dùng:

~~~java
entityManager.createQuery("""
    DELETE FROM Note n WHERE n.id = :id
    """)
    .setParameter("id", id)
    .executeUpdate();
~~~

Có thể giả định câu này chạy `@SQLDelete` của `Note` hay không? Khi ứng dụng yêu cầu xóa mềm, cần sửa quy trình theo hướng nào?

### Bài tập 6 — Kiểm tra đa tenant

Bảng `documents` có `id` và `tenant_id`. Một lệnh custom UPDATE chỉ có `WHERE id = ?`. Hãy nêu tình huống có thể sai và các lớp bảo vệ cần xem xét trước khi dùng production.

### Định hướng trả lời

- **Bài 1:** `@SQLDelete` chỉ thay thao tác ghi; cần filter/`@SQLRestriction` hoặc `@SoftDelete` phù hợp và thiết kế riêng đường đọc admin.
- **Bài 2:** Custom DML phải phù hợp kỳ vọng bind ID/version của Hibernate, bảo toàn điều kiện version và xác minh số hàng ảnh hưởng.
- **Bài 3:** Trigger chạy ở database không tự cập nhật managed object; dùng generated mapping thích hợp hoặc flush rồi refresh khi entity còn managed.
- **Bài 4:** Parent soft-deleted có thể vẫn còn hàng vật lý, còn child bị xóa thật; phải quyết định rõ chính sách lịch sử và cascade cho cả hai.
- **Bài 5:** Bulk delete không đi qua remove entity theo cách thông thường; cần một API xóa mềm rõ ràng hoặc Hibernate feature hỗ trợ phù hợp.
- **Bài 6:** Điều kiện tenant phải được bảo vệ bằng mapping/transaction/query/row-level security và constraint phù hợp, không dựa vào filter SELECT tự đi vào SQL tĩnh.

---

**Ghi nhớ:** `@SQLInsert`, `@SQLUpdate` và `@SQLDelete` cho phép thay SQL của thao tác ghi trong vòng đời entity Hibernate. Chúng **không thay thế trách nhiệm bảo đảm tính đúng đắn** của ID, version, row count, cascade, callback, persistence context, cache, constraint và truy vấn sau đó. Hãy dùng chúng cho nhu cầu rõ ràng, xác minh hợp đồng bind theo phiên bản Hibernate, và chọn cơ chế đồng bộ state phù hợp với hành vi nghiệp vụ.
