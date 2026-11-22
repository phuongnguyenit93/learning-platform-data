# Lựa chọn cơ chế soft delete hoặc filter theo phiên bản Hibernate

## Mục tiêu

Sau bài này, bạn có thể phân biệt soft delete với cơ chế filter dữ liệu; chọn `@SoftDelete`, `@SQLDelete` kết hợp restriction, `@SQLRestriction` hoặc `@Filter` theo phiên bản Hibernate; hiểu thay đổi từ `javax.persistence` sang `jakarta.persistence`; cấu hình filter theo Session; và kiểm thử việc xóa mềm, tải theo ID, quan hệ, truy vấn native và khôi phục dữ liệu.

Các ví dụ dùng Java 17+ và Spring Data JPA. Những annotation như `@SoftDelete`, `@SQLDelete`, `@SQLRestriction`, `@Filter` là API riêng của Hibernate, không thuộc Jakarta Persistence. Kiểm tra đúng phiên bản Hibernate được Spring Boot quản lý trước khi sao chép ví dụ.

## 1. Soft delete và filter giải quyết hai bài toán khác nhau

Soft delete là cách xử lý thao tác xóa một entity mà vẫn giữ hàng trong database. Thay vì phát lệnh `DELETE`, ORM cập nhật một cột đánh dấu, ví dụ `deleted = true` hoặc `deleted_at = CURRENT_TIMESTAMP`. Các truy vấn thông thường sẽ bỏ qua hàng đã bị xóa mềm.

Filter là điều kiện bổ sung vào truy vấn để giới hạn tập dữ liệu theo ngữ cảnh hiện tại. Ví dụ chỉ lấy tài liệu đang xuất bản, tài liệu thuộc tenant hiện tại, dữ liệu của một khoảng thời gian hoặc bản ghi có trạng thái được chọn. Filter thường có thể bật/tắt và truyền tham số theo từng Hibernate Session.

Ba cơ chế cần phân biệt:

| Cơ chế | Vai trò | Có tham số runtime? | Có thay thao tác DELETE? |
| --- | --- | --- | --- |
| `@SoftDelete` | Ánh xạ vòng đời xóa mềm ở cấp entity/collection được hỗ trợ | Không cần tham số filter cho trạng thái xóa | Có; Hibernate đổi thao tác xóa thành cập nhật cờ/timestamp |
| `@SQLDelete` + `@Where` hoặc `@SQLRestriction` | Tự viết SQL cập nhật cờ xóa và khai báo điều kiện ẩn hàng | Không; restriction là tĩnh | `@SQLDelete` có; restriction chỉ lọc đọc |
| `@Filter` | Bật điều kiện động theo Session, thường dùng cho phạm vi dữ liệu | Có | Không; filter không tự biến DELETE thành soft delete |
| `@SQLRestriction` | Thêm điều kiện SQL tĩnh vào truy vấn entity/collection | Không | Không; chỉ thay đổi điều kiện SQL được sinh |

Vì vậy, nếu yêu cầu là gọi `EntityManager.remove()` nhưng giữ lại hàng trong database, hãy chọn cơ chế soft delete. Nếu yêu cầu là cùng một entity có thể được truy vấn theo tenant, trạng thái hoặc thời gian khác nhau trong các Session, hãy xem `@Filter`. Có thể dùng cả hai khi nghiệp vụ cần, nhưng phải hiểu điều kiện nào luôn áp dụng và điều kiện nào chỉ có hiệu lực khi Session bật filter.

## 2. Bảng tương thích theo phiên bản Hibernate

| Phiên bản Hibernate | Cơ chế nên cân nhắc | Ghi chú quan trọng |
| --- | --- | --- |
| 5.6 | `@SQLDelete` + `@Where`; `@Filter` cho điều kiện động | Hibernate 5.6 dùng hệ `javax.persistence`; chưa có `@SoftDelete` hoặc `@SQLRestriction` |
| 6.0–6.2 | `@SQLDelete` + `@Where`; `@Filter` | Hibernate 6 chuyển sang `jakarta.persistence`; `@SoftDelete` chưa có |
| 6.3 | `@SQLDelete` + `@SQLRestriction`; `@Filter` | `@Where` bị deprecated từ 6.3; dùng `@SQLRestriction` cho restriction tĩnh |
| 6.4–6.5 | Ưu tiên `@SoftDelete` cho entity/collection được hỗ trợ; `@Filter` cho điều kiện động | `@SoftDelete` được thêm ở 6.4; các tài liệu 6.4/6.5 mô tả chiến lược boolean `ACTIVE` và `DELETED` |
| 6.6 | `@SoftDelete`, `@SQLRestriction`, `@Filter` | `@FilterDef` có thêm các tùy chọn như `applyToLoadByKey`; kiểm tra trạng thái incubating và đúng minor version |
| 7.x | `@SoftDelete`, `@SQLRestriction`, `@Filter` | Tài liệu Hibernate 7.4 hiện hành còn mô tả chiến lược `TIMESTAMP`; không mặc định tính năng này có mặt ở mọi minor 7.x hoặc ở Hibernate 6.x |

Điểm chuyển phiên bản cần nhớ:

- Hibernate 5.6 thường đi cùng Spring Boot 2.x và import `javax.persistence.*`.
- Hibernate 6.x và 7.x dùng Jakarta Persistence, nên entity import `jakarta.persistence.*`.
- `@SoftDelete` có từ Hibernate 6.4. Nếu dự án dùng Hibernate 6.3 trở xuống, code có annotation này sẽ không biên dịch.
- `@Where` deprecated từ Hibernate 6.3; `@SQLRestriction` là API thay thế cho restriction SQL tĩnh.
- `@SoftDelete` là API Hibernate. Nếu cần đổi provider JPA, phải thiết kế lại hoặc chuyển logic sang tầng database/application.

Không chỉ nhìn phiên bản Spring Boot trong `pom.xml` để quyết định API. Hãy kiểm tra dependency thực tế, ví dụ bằng `mvn dependency:tree` hoặc `gradle dependencies`, vì dependency management có thể chọn một minor Hibernate khác với ví dụ trên.

## 3. Cơ chế `@SoftDelete` từ Hibernate 6.4

`@SoftDelete` là lựa chọn ưu tiên khi phiên bản Hibernate hỗ trợ và mapping phù hợp. Hibernate quản lý cột chỉ báo xóa: khi persist entity, hàng được tạo ở trạng thái chưa xóa; khi gọi `remove()`, Hibernate cập nhật cột chỉ báo thay vì xóa vật lý; các truy vấn entity thông thường tự thêm điều kiện để bỏ qua hàng đã xóa.

Ví dụ dùng chiến lược `DELETED`:

```java
package com.example.learning.document;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.SoftDelete;
import org.hibernate.annotations.SoftDeleteType;

@Entity
@Table(name = "documents")
@SoftDelete(strategy = SoftDeleteType.DELETED, columnName = "deleted")
public class Document {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    protected Document() {
    }

    public Document(String title) {
        this.title = title;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
}
```

Với chiến lược `DELETED`, giá trị `true` nghĩa là hàng đã bị xóa; `false` nghĩa là hàng còn hoạt động. Nếu không khai báo `strategy`, `DELETED` là mặc định. Cột mặc định cũng là `deleted`, nhưng nên khai báo `columnName` rõ ràng khi schema đã có quy ước khác.

### 3.1. Chiến lược ACTIVE và DELETED

`SoftDeleteType` trong các bản Hibernate 6.4/6.5 có hai cách diễn giải boolean:

| Strategy | Giá trị trong database | Ý nghĩa | Tên cột mặc định |
| --- | --- | --- | --- |
| `DELETED` | `true` | Đã xóa | `deleted` |
| `DELETED` | `false` | Còn hoạt động | `deleted` |
| `ACTIVE` | `true` | Còn hoạt động | `active` |
| `ACTIVE` | `false` | Đã xóa | `active` |

Ví dụ nếu schema hiện tại đã có cột `active`:

```java
@Entity
@Table(name = "documents")
@SoftDelete(strategy = SoftDeleteType.ACTIVE, columnName = "active")
public class Document {
    // Các thuộc tính entity
}
```

Không đảo ý nghĩa cột bằng cách tự viết converter theo hướng ngược. Converter chỉ chuyển giá trị boolean sang kiểu lưu trữ; Hibernate chịu trách nhiệm diễn giải strategy. Các converter thường dùng gồm `NumericBooleanConverter`, `YesNoConverter` và `TrueFalseConverter`. Chỉ cấu hình converter nếu kiểu cột hoặc schema yêu cầu.

### 3.2. Collection và entity inheritance

Hibernate hỗ trợ `@SoftDelete` trên entity và trên một số collection table:

- Đặt trên root entity của hierarchy để áp dụng cho các entity trong inheritance hierarchy.
- Có thể đặt trên `@ElementCollection` để xóa mềm từng hàng trong collection table.
- Có thể đặt trên `@ManyToMany` để xóa mềm hàng trong join table.
- Không đặt trực tiếp `@SoftDelete` trên association `@OneToMany`; Hibernate báo lỗi mapping. Nếu entity con cần xóa mềm, đặt `@SoftDelete` trên chính entity con.

Ví dụ collection table:

```java
@ElementCollection
@CollectionTable(name = "document_labels", joinColumns = @JoinColumn(name = "document_id"))
@Column(name = "label")
@SoftDelete(columnName = "deleted")
private Set<String> labels = new HashSet<>();
```

Đây là ví dụ cho `@ElementCollection`; cần các import và khai báo field trong một entity thực tế. Với `@OneToMany`, hãy xác định rõ việc xóa parent có cần xóa mềm child hay không và kiểm thử cascade/orphan removal. Không suy ra rằng đánh dấu parent đã xóa sẽ tự động đánh dấu mọi entity con.

### 3.3. Timestamp strategy trong Hibernate 7.x hiện hành

Tài liệu Hibernate 7.4 hiện hành mô tả thêm strategy `TIMESTAMP`, lưu thời điểm hàng bị xóa thay vì chỉ lưu boolean. Ví dụ:

```java
@Entity
@Table(name = "documents")
@SoftDelete(strategy = SoftDeleteType.TIMESTAMP, columnName = "deleted_at")
public class Document {
    // Các thuộc tính entity
}
```

Với strategy này, cột lưu thời điểm xóa; không cấu hình boolean `AttributeConverter` cùng `TIMESTAMP`. Tài liệu Hibernate 6.4/6.5 và 6.6 mô tả các strategy boolean, nên chỉ dùng `TIMESTAMP` khi Javadocs/User Guide của đúng phiên bản đang chạy xác nhận có hỗ trợ. Không lấy ví dụ 7.4 rồi đưa thẳng vào dự án 6.x.

`TIMESTAMP` giúp biết thời điểm xóa, nhưng không tự ghi người thực hiện, lý do xóa hoặc toàn bộ lịch sử thay đổi. Nếu cần audit đầy đủ, bổ sung các trường audit hoặc dùng cơ chế audit như Hibernate Envers theo yêu cầu.

## 4. Dùng `@SQLDelete` với Hibernate 5.6 đến 6.2

Trước Hibernate 6.4, một cách triển khai thường gặp là thay SQL DELETE mặc định bằng UPDATE, rồi thêm restriction để ẩn hàng đã xóa.

Ví dụ cho entity không có `@Version`:

```java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;
import org.hibernate.annotations.SQLDelete;
import org.hibernate.annotations.Where;

@Entity
@Table(name = "documents")
@SQLDelete(sql = "UPDATE documents SET deleted = true WHERE id = ?")
@Where(clause = "deleted = false")
public class Document {
    @Id
    private Long id;

    private String title;

    protected Document() {
    }
}
```

Đây là mapping minh họa cho Hibernate 5.6 dùng `javax.persistence`. Với Hibernate 6.0–6.2, thay import `javax.persistence.*` bằng `jakarta.persistence.*`; `@SQLDelete` và `@Where` vẫn là annotation Hibernate.

Hai annotation làm hai việc riêng:

- `@SQLDelete` thay câu DELETE do Hibernate phát ra khi entity bị remove bằng câu UPDATE đặt `deleted = true`.
- `@Where` thêm điều kiện SQL tĩnh để các truy vấn entity/collection bỏ qua hàng `deleted = true`.

Chỉ có `@SQLDelete` thì hàng đã đánh dấu vẫn có thể xuất hiện trong truy vấn. Chỉ có `@Where` thì thao tác remove vẫn có thể xóa vật lý. Muốn có soft delete bằng cách này, cần cả hai phần.

### 4.1. Entity có `@Version` cần chú ý thứ tự tham số

Nếu entity được version hóa, câu SQL custom phải có đúng số lượng placeholder `?` và đúng thứ tự Hibernate yêu cầu. Với `@SQLDelete`, các cột khóa chính đứng trước cột version. Ví dụ minh họa:

```java
@SQLDelete(
    sql = "UPDATE documents SET deleted = true WHERE id = ? AND version = ?"
)
```

Đây chỉ là fragment cho entity có một khóa chính và một cột version. Entity dùng khóa ghép hoặc mapping nhiều bảng cần câu SQL phù hợp với số cột và thứ tự tham số Hibernate thực sự bind. Hãy kiểm tra Javadocs `@SQLDelete`, SQL log và integration test trên đúng mapping; một placeholder sai có thể làm câu lệnh lỗi hoặc kiểm tra version không còn đúng.

## 5. Từ Hibernate 6.3: thay `@Where` bằng `@SQLRestriction`

`@Where` bị deprecated từ Hibernate 6.3. Với restriction cố định, dùng `@SQLRestriction`:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.SQLDelete;
import org.hibernate.annotations.SQLRestriction;

@Entity
@Table(name = "documents")
@SQLDelete(sql = "UPDATE documents SET deleted = true WHERE id = ?")
@SQLRestriction("deleted = false")
public class Document {
    @Id
    private Long id;

    private String title;

    protected Document() {
    }
}
```

`@SQLRestriction` là predicate SQL native được thêm vào SQL Hibernate tạo cho entity hoặc collection. Nó luôn được áp dụng và không thể tắt ở runtime; không hỗ trợ bind parameter. Vì vậy, nó phù hợp cho điều kiện cố định như `deleted = false`, không phù hợp cho tenant ID hoặc status cần thay đổi theo request.

Đối với join table, Hibernate có `@SQLJoinTableRestriction`. Với phiên bản cũ, annotation tương ứng là `@WhereJoinTable`, cũng bị deprecated từ 6.3 để chuyển sang `@SQLJoinTableRestriction`.

## 6. Dùng `@Filter` cho điều kiện động theo Session

`@Filter` dành cho trường hợp điều kiện lọc cần thay đổi theo runtime. Một filter được định nghĩa bằng `@FilterDef`, gắn vào entity hoặc collection bằng `@Filter`, rồi bật trên Hibernate `Session` trước khi chạy query.

Ví dụ lọc tài liệu theo trạng thái:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import org.hibernate.annotations.Filter;
import org.hibernate.annotations.FilterDef;
import org.hibernate.annotations.ParamDef;

@Entity
@FilterDef(
    name = "documentStatus",
    parameters = @ParamDef(name = "status", type = String.class)
)
@Filter(
    name = "documentStatus",
    condition = "status = :status"
)
public class Document {
    @Id
    private Long id;

    private String status;

    // Constructor và accessor
}
```

Điều kiện trong `@Filter` là SQL fragment, nên dùng tên cột database (`status` trong ví dụ), không mặc định dùng tên property Java nếu tên cột đã được đổi bằng `@Column`.

Bật filter trong một transaction:

```java
import jakarta.persistence.EntityManager;
import org.hibernate.Filter;
import org.hibernate.Session;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentSearchService {
    private final EntityManager entityManager;

    public DocumentSearchService(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional(readOnly = true)
    public List<Document> findByStatus(String status) {
        Session session = entityManager.unwrap(Session.class);
        Filter filter = session.enableFilter("documentStatus");
        filter.setParameter("status", status);
        try {
            return entityManager.createQuery(
                "select d from Document d order by d.id", Document.class
            ).getResultList();
        } finally {
            session.disableFilter("documentStatus");
        }
    }
}
```

Ví dụ này minh họa việc bật filter trong cùng Session đang thực thi JPQL. Cần import `java.util.List`. Nếu Session được dùng chung cho nhiều thao tác trong cùng transaction, hãy quản lý bật/tắt filter ở một ranh giới rõ ràng để điều kiện của request trước không ảnh hưởng request sau.

Filter không có hiệu lực nếu chưa bật, trừ khi phiên bản Hibernate và cấu hình filter hỗ trợ auto-enable. Có thể gắn filter vào nhiều entity hoặc collection, nhưng mỗi mapping phải khai báo filter tương ứng.

### 6.1. Filter và tải entity bằng khóa chính

Đây là một khác biệt quan trọng khi chọn `@Filter` cho dữ liệu cần ẩn:

- Trong Hibernate 5.6, filter áp dụng cho entity query nhưng không mặc định áp dụng khi tải entity trực tiếp bằng `EntityManager.find()` hoặc khi resolve một association theo khóa chính.
- Tài liệu Hibernate 6.6 có `@FilterDef(applyToLoadByKey = true)`. Mặc định vẫn là `false`; tùy chọn này được đánh dấu incubating trong Javadocs 6.6.
- Với các phiên bản mới hơn, kiểm tra đúng Javadocs và thử cả `find()`, lazy to-one association và entity query. Khi filter loại một hàng được tham chiếu bởi to-one association, Hibernate có thể phát sinh `EntityFilterException` thay vì xử lý như một query thông thường.

Vì vậy, `@Filter` không nên là lớp bảo vệ duy nhất để che dữ liệu nhạy cảm. Nếu dùng cho tenant hoặc quyền truy cập, phải kiểm tra mọi đường tải dữ liệu, bao gồm repository `findById`, `getReference`, lazy association, native SQL và query do ứng dụng khác thực hiện.

## 7. Chọn cơ chế nào cho từng nhu cầu?

| Nhu cầu | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| `remove()` phải cập nhật cờ xóa và query thường bỏ qua hàng đã xóa | `@SoftDelete` từ Hibernate 6.4 | Hibernate quản lý cả thao tác xóa và điều kiện đọc |
| Dự án Hibernate 5.6–6.2 cần soft delete | `@SQLDelete` + `@Where` | Tương thích các phiên bản chưa có `@SoftDelete` |
| Dự án Hibernate 6.3 cần restriction tĩnh | `@SQLRestriction`; kết hợp `@SQLDelete` nếu cần xóa mềm | Thay thế `@Where` đã deprecated |
| Lọc theo tenant/status/thời gian thay đổi theo Session | `@Filter` | Có tham số runtime và bật/tắt theo Session |
| Điều kiện cố định trên entity/collection, không cần tham số | `@SQLRestriction` | Luôn áp dụng, không phải quản lý enable/disable |
| Lọc riêng các hàng trong join table | `@SQLJoinTableRestriction` hoặc `@FilterJoinTable` | Điều kiện được đặt trên bảng liên kết |
| Cần khôi phục hàng đã xóa | Luồng restore riêng, có quyền kiểm soát | Các cơ chế soft delete không tự tạo API undelete chung |

Một thiết kế thường gặp là `@SoftDelete` cho vòng đời xóa và `@Filter` cho phạm vi tenant hoặc trạng thái hiển thị. Khi kết hợp, kiểm tra SQL cuối cùng để chắc chắn cả hai điều kiện được áp dụng như dự kiến.

## 8. Dùng filter cho tenant và phạm vi dữ liệu

Ví dụ filter tenant có thể khai báo:

```java
@FilterDef(
    name = "tenantScope",
    parameters = @ParamDef(name = "tenantId", type = Long.class)
)
@Filter(
    name = "tenantScope",
    condition = "tenant_id = :tenantId"
)
@Entity
@Table(name = "documents")
public class Document {
    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;
}
```

Trước khi truy vấn, ứng dụng bật `tenantScope` và lấy tenant ID từ principal/security context đã xác thực. Không lấy tenant ID từ query parameter rồi tin trực tiếp. Filter là một lớp hỗ trợ tạo SQL; authorization vẫn phải được kiểm tra ở service/security layer, và các native query hoặc đường truy cập khác cũng phải được bảo vệ.

Với filter dùng chung trong một Session, đặt tenant parameter một lần ở ranh giới transaction/request. Nếu ứng dụng dùng Open Session in View hoặc Session tồn tại lâu, phải bảo đảm Session không mang tenant/filter state của một request sang request khác.

## 9. Giới hạn của soft delete trong quan hệ và vòng đời entity

Soft delete giữ hàng trong database, nên nó ảnh hưởng tới những quy tắc vốn dựa vào việc hàng bị xóa vật lý:

- Foreign key vẫn tham chiếu tới hàng đã xóa mềm; database không tự coi hàng đó là đã biến mất.
- `CascadeType.REMOVE` và `orphanRemoval = true` cần được kiểm thử với mapping soft delete. Entity con chỉ được xóa mềm nếu mapping của entity con cũng hỗ trợ cơ chế đó; không mặc định parent flag sẽ tự lan sang mọi bảng.
- `@SoftDelete` trên `@ManyToMany` đánh dấu hàng join table; nó không đồng nghĩa với xóa mềm entity ở đầu bên kia.
- Với `@OneToMany`, đặt `@SoftDelete` trên entity con nếu muốn xóa mềm child; không gắn annotation trực tiếp lên collection `@OneToMany`.
- Các truy vấn native SQL, JDBC trực tiếp hoặc công cụ báo cáo ngoài Hibernate không tự nhận restriction/filter mapping.

Nếu một parent đã xóa mềm thì không muốn child xuất hiện trong màn hình, hãy quyết định rõ điều kiện đó nằm ở mapping của child, query join, service predicate hay filter. Không để mỗi màn hình tự thêm điều kiện một cách không nhất quán.

## 10. Schema, unique constraint và chỉ mục

Trước khi bật soft delete, chuẩn bị schema bằng migration có kiểm soát:

1. Thêm cột `deleted` boolean/bit hoặc kiểu phù hợp, có `NOT NULL` và default biểu thị chưa xóa.
2. Backfill toàn bộ hàng hiện tại về trạng thái chưa xóa.
3. Cập nhật mapping và kiểm thử SQL insert/update/delete.
4. Kiểm tra index trên các điều kiện truy vấn thường dùng, ví dụ `deleted` kết hợp tenant hoặc trạng thái.
5. Xem xét partial/filtered unique index nếu giá trị unique chỉ cần duy nhất trong các hàng chưa xóa.

Unique constraint hiện có vẫn nhìn thấy cả hàng đã xóa mềm. Ví dụ nếu `email` có unique constraint toàn bảng, xóa mềm một tài khoản không tự cho phép tạo tài khoản mới dùng lại email đó. Partial unique index chỉ áp dụng cho `deleted = false` là giải pháp ở một số database, nhưng cú pháp và khả năng hỗ trợ khác nhau; không giả định là portable.

Đừng dùng `columnDefinition` trong entity làm thay thế migration cho schema production. Hãy quản lý default, check constraint, index và thay đổi dữ liệu bằng công cụ migration của dự án.

## 11. Khôi phục, audit và truy vấn dữ liệu đã xóa

`@SoftDelete` chủ yếu chuẩn hóa thao tác đánh dấu xóa và cách Hibernate loại hàng đó khỏi truy vấn thông thường. Nó không cung cấp một API restore chung cho mọi use case.

Nếu cần restore:

- Tạo use case admin riêng, có authorization và audit.
- Dùng câu lệnh cập nhật được kiểm soát để đổi trạng thái xóa; với mapping Hibernate, cân nhắc cache/persistence context và refresh/clear sau thao tác native.
- Kiểm tra unique constraint, association và trạng thái liên quan trước khi khôi phục.
- Ghi lại ai khôi phục, lúc nào và lý do nếu nghiệp vụ yêu cầu.

Nếu cần truy vấn dữ liệu đã xóa, hãy tạo repository/query admin rõ ràng hoặc dùng native SQL/reporting path được kiểm soát. Không tắt toàn bộ filter/restriction một cách ngẫu nhiên trong request người dùng thông thường.

Soft delete không phải audit log. Nếu cần lịch sử trước/sau của nhiều lần cập nhật, người thao tác và revision, dùng bảng audit hoặc giải pháp như Hibernate Envers. Chiến lược `TIMESTAMP` trong Hibernate 7.x có thể lưu thời điểm xóa, nhưng không lưu đầy đủ người thực hiện hay lý do.

## 12. Bulk DML và native SQL cần kiểm tra riêng

Không giả định mọi đường ghi đều đi qua cùng một lifecycle:

- `EntityManager.remove(entity)` đi qua entity lifecycle và là đường cần kiểm thử khi dùng `@SoftDelete` hoặc `@SQLDelete`.
- Bulk JPQL/HQL `DELETE`, native `DELETE` và JDBC trực tiếp có thể không đi qua cùng cơ chế remove từng entity. Kiểm tra SQL thực tế; nếu cần xóa mềm hàng loạt, dùng câu `UPDATE` có điều kiện rõ ràng hoặc cơ chế bulk được xác nhận cho phiên bản Hibernate.
- Native SELECT không tự nhận `@Filter` hoặc `@SQLRestriction`; tự thêm predicate cần thiết.
- Bulk UPDATE/DELETE có thể làm trạng thái entity đã load trong persistence context bị cũ. Cần clear/refresh phù hợp sau khi chạy bulk DML.

Đối với tác vụ xóa hàng loạt, hãy kiểm tra số hàng bị tác động, optimistic/version semantics, cache và foreign key. Không dựa vào tên method repository để kết luận câu SQL là UPDATE hay DELETE.

## 13. Kiểm thử `@SoftDelete`

Test tối thiểu nên xác nhận `remove()` giữ hàng trong database nhưng truy vấn entity thông thường không còn trả hàng đó. Ví dụ cho Hibernate 6.4+ với cột boolean `deleted`:

```java
package com.example.learning.document;

import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class DocumentSoftDeleteTest {
    @Autowired
    private EntityManager entityManager;

    @Test
    void removeMarksDocumentDeletedButKeepsDatabaseRow() {
        Document document = new Document("Hibernate guide");
        entityManager.persist(document);
        entityManager.flush();
        Long id = document.getId();

        entityManager.remove(document);
        entityManager.flush();
        entityManager.clear();

        assertThat(entityManager.find(Document.class, id)).isNull();

        Number rowCount = (Number) entityManager.createNativeQuery(
            "select count(*) from documents where id = :id and deleted = true"
        ).setParameter("id", id).getSingleResult();

        assertThat(rowCount.longValue()).isEqualTo(1L);
    }
}
```

Test này giả định entity có constructor `Document(String title)`, getter `getId()`, bảng `documents` và cột boolean `deleted`. Native SQL dùng cú pháp boolean của database test; nếu database dùng `BIT`, `NUMBER` hoặc kiểu khác, điều chỉnh predicate theo dialect. `@DataJpaTest` thường chạy trong transaction test; dữ liệu sẽ rollback khi test kết thúc.

## 14. Kiểm thử `@Filter` và tải theo ID

Với filter, cần test cả hai trường hợp: filter tắt và filter bật. Ngoài query JPQL, hãy kiểm tra `EntityManager.find()` và lazy to-one association:

```java
Session session = entityManager.unwrap(Session.class);

List<Document> allWithoutFilter = entityManager.createQuery(
    "select d from Document d", Document.class
).getResultList();

session.enableFilter("documentStatus").setParameter("status", "PUBLISHED");
List<Document> published = entityManager.createQuery(
    "select d from Document d", Document.class
).getResultList();
session.disableFilter("documentStatus");
```

Đây là fragment minh họa, cần fixture có nhiều trạng thái và entity đã khai báo `@FilterDef`/`@Filter`. Bổ sung assertion cho số lượng trước và sau khi bật filter. Với phiên bản cũ, kiểm tra rằng `find()` theo ID có thể không chịu filter. Với Hibernate 6.6+, nếu dùng `applyToLoadByKey = true`, kiểm tra thêm trường hợp association to-one bị filter loại bỏ.

Đối với soft delete, bổ sung test cho:

- Tải bằng repository `findById` sau khi xóa mềm.
- JPQL query, collection lazy load và association join.
- Cascade remove/orphan removal.
- Native query và bulk DML.
- Restore, unique constraint và cache nếu các use case đó được hỗ trợ.

Chạy integration test trên cùng database/driver với production, tốt nhất bằng Testcontainers. H2 có thể khác database production về kiểu boolean, partial index, SQL custom, constraint và cách tối ưu query.

## 15. Lộ trình nâng cấp từ `@SQLDelete` sang `@SoftDelete`

Khi nâng dự án từ Hibernate 5.6/6.2 lên 6.4+, có thể chuyển mapping theo từng entity:

1. Kiểm kê `@SQLDelete`, `@Where`, `@WhereJoinTable`, `@Filter` và các repository tự thêm điều kiện `deleted = false`.
2. Xác nhận ý nghĩa cột hiện tại: `true` là deleted hay active; kiểm tra giá trị null và dữ liệu lịch sử.
3. Chọn `SoftDeleteType.DELETED` hoặc `ACTIVE` sao cho khớp dữ liệu; cấu hình `columnName` và converter nếu cần.
4. Thêm `@SoftDelete` trên entity hoặc root hierarchy phù hợp; không giữ `@SQLDelete` cũ cho cùng thao tác nếu nó gây xung đột với cơ chế mới.
5. Xóa restriction thủ công bị trùng sau khi xác nhận `@SoftDelete` đã tự lọc đúng.
6. Giữ `@Filter` cho những điều kiện động độc lập như tenant/status; không xóa filter chỉ vì đã thêm soft delete.
7. Kiểm thử query theo ID, association, collection, bulk DML, native SQL, cascade và restore.
8. Triển khai migration/schema và giám sát số hàng được đánh dấu, truy vấn chậm và lỗi constraint.

Đối với Hibernate 6.3, chuyển `@Where` sang `@SQLRestriction` khi phù hợp nhưng vẫn cần `@SQLDelete` nếu mục tiêu là soft delete; `@SQLRestriction` không thay thao tác xóa.

## 16. Những lỗi thường gặp

- **Dùng `@SoftDelete` trên Hibernate trước 6.4.** Annotation chưa tồn tại; dùng fallback tương thích hoặc nâng phiên bản.
- **Dùng `@Where` trong Hibernate 6.3+.** Annotation deprecated; chuyển sang `@SQLRestriction` cho điều kiện tĩnh.
- **Chỉ khai báo `@SQLDelete`.** Hàng đã đánh dấu vẫn có thể xuất hiện nếu không có restriction hoặc query predicate phù hợp.
- **Chỉ khai báo `@Where`/`@SQLRestriction`.** Restriction không đổi câu DELETE thành UPDATE.
- **Dùng `@Filter` nhưng quên enable.** Filter mặc định không hoạt động nếu chưa bật hoặc chưa cấu hình auto-enable phù hợp.
- **Cho rằng `@Filter` luôn áp dụng khi `find(id)`.** Direct fetch theo khóa chính có thể bỏ qua filter; kiểm tra `applyToLoadByKey` và phiên bản.
- **Dùng filter như lớp authorization duy nhất.** Native SQL, đường tải theo ID và filter chưa bật có thể bỏ qua điều kiện; authorization phải được thực thi ở server.
- **Đặt `@SoftDelete` trực tiếp trên collection `@OneToMany`.** Mapping này không được hỗ trợ; đánh dấu soft delete trên entity con.
- **Quên rằng `@SQLRestriction` là SQL native và không có parameter.** Dùng `@Filter` khi cần điều kiện runtime.
- **Sai placeholder trong `@SQLDelete`.** SQL phải có đúng số lượng và thứ tự tham số Hibernate mong đợi, đặc biệt với khóa ghép hoặc `@Version`.
- **Giả định unique constraint bỏ qua hàng đã xóa.** Unique index thông thường vẫn tính cả hàng soft-deleted.
- **Cho rằng soft delete tự tạo audit/restore.** Cần use case riêng cho restore và audit.
- **Không kiểm tra bulk DML/native SQL.** Những đường này có thể không theo lifecycle xóa từng entity.

## 17. Checklist chọn và triển khai

- [ ] Đã xác định đây là xóa mềm hay lọc dữ liệu theo runtime.
- [ ] Đã kiểm tra phiên bản Hibernate thực tế và import `javax`/`jakarta` tương ứng.
- [ ] Hibernate 6.4+ dùng `@SoftDelete` nếu entity/collection mapping được hỗ trợ.
- [ ] Hibernate 5.6–6.2 dùng fallback `@SQLDelete` + `@Where` nếu cần soft delete.
- [ ] Hibernate 6.3+ dùng `@SQLRestriction` thay `@Where` cho predicate tĩnh.
- [ ] `@Filter` được enable và set parameter trong đúng Session/transaction.
- [ ] Đã kiểm tra đường tải bằng ID và association, bao gồm `applyToLoadByKey` nếu phiên bản hỗ trợ.
- [ ] Schema có cột trạng thái không null, default và index phù hợp.
- [ ] Đã đánh giá unique constraint, foreign key, cascade và orphan removal.
- [ ] Native SQL và bulk DML có predicate/UPDATE phù hợp.
- [ ] Có test cho remove, truy vấn thường, `findById`, collection, filter, restore và cache.
- [ ] Integration test chạy trên database tương thích production.

## Kết luận

Chọn cơ chế theo đúng mục đích và phiên bản. Hibernate 6.4+ có `@SoftDelete` để quản lý thao tác xóa mềm; Hibernate 5.6–6.2 thường cần `@SQLDelete` kết hợp `@Where`; từ 6.3 dùng `@SQLRestriction` thay cho `@Where` khi cần predicate tĩnh. `@Filter` dành cho điều kiện động được bật trên Session và cần chú ý khác biệt giữa entity query với tải theo khóa chính. Hãy kiểm tra schema, association, unique constraint, bulk/native SQL và test trên database mục tiêu trước khi đưa mapping vào production.

## Tài liệu chính thức

- [Hibernate ORM 5.6 User Guide – Filtering entities and associations](https://docs.hibernate.org/orm/5.6/userguide/html_single/)
- [Hibernate ORM 6.3 `@Where` Javadocs – deprecated in favor of `SQLRestriction`](https://docs.hibernate.org/orm/6.3/javadocs/org/hibernate/annotations/Where.html)
- [Hibernate ORM 6.3 `@SQLRestriction` Javadocs](https://docs.hibernate.org/orm/6.3/javadocs/org/hibernate/annotations/SQLRestriction.html)
- [Hibernate ORM 6.4 User Guide – `@SoftDelete`](https://docs.hibernate.org/orm/6.4/userguide/html_single/)
- [Hibernate ORM 6.4 Migration Guide – soft delete added in 6.4](https://docs.hibernate.org/orm/6.4/migration-guide/)
- [Hibernate ORM 6.6 `@FilterDef` Javadocs – `applyToLoadByKey`](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/FilterDef.html)
- [Hibernate ORM current User Guide – soft delete and filters](https://docs.hibernate.org/orm/current/userguide/html_single/)