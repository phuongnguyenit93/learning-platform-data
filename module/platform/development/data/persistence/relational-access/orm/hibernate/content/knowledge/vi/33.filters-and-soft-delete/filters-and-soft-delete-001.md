# Bộ lọc động với @FilterDef, @Filter và tham số theo Session

Trong Hibernate ORM, đôi khi cùng một entity phải được truy vấn với **điều kiện khác nhau theo ngữ cảnh đang chạy**:

- Người dùng thường chỉ được xem những tài liệu thuộc tenant của mình.
- Danh sách mặc định loại các hàng được đánh dấu xóa mềm, nhưng một màn hình quản trị có thể xem lịch sử.
- Báo cáo cần những bản ghi còn hiệu lực tại một thời điểm do người dùng chọn.
- Nhân viên một vùng chỉ xem dữ liệu thuộc những vùng được cấp quyền.
- Một collection chỉ nên hiển thị các phần tử thỏa một điều kiện tại thời điểm được load.

Có thể lặp các điều kiện đó trong từng HQL/JPQL query:

~~~java
List<Document> documents = session.createQuery(
    """
    select d from Document d
    where d.tenantId = :tenantId
      and d.deleted = false
    order by d.id
    """,
    Document.class
)
.setParameter("tenantId", tenantId)
.getResultList();
~~~

Nhưng khi hàng chục query cùng phụ thuộc một quy tắc, việc viết tay liên tục dễ gây thiếu điều kiện, làm logic phân tán và khiến việc đổi quy tắc khó kiểm soát.

Hibernate hỗ trợ **dynamic filter**, được định nghĩa bằng các annotation:

- `@FilterDef` — khai báo tên filter, tên/kiểu tham số, điều kiện mặc định và một số tùy chọn.
- `@Filter` — gắn một filter đã khai báo vào **entity hoặc persistent collection**, có thể cung cấp điều kiện SQL riêng.
- `@ParamDef` — khai báo tham số của filter để Hibernate biết cách bind giá trị.
- `Session.enableFilter(name)`, `setParameter(...)`, `disableFilter(name)` — bật/tắt và gán giá trị filter theo **từng Hibernate Session**.

Ví dụ cốt lõi:

~~~java
@FilterDef(
    name = "tenantScope",
    parameters = @ParamDef(
        name = "tenantId",
        type = String.class
    )
)
@Entity
@Table(name = "documents")
@Filter(
    name = "tenantScope",
    condition = "tenant_id = :tenantId"
)
public class Document {
    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;
}
~~~

Khi xử lý yêu cầu:

~~~java
session.enableFilter("tenantScope")
       .setParameter("tenantId", "tenant-a");

List<Document> documents = session.createQuery(
    "from Document d order by d.id",
    Document.class
).getResultList();
~~~

Hibernate bổ sung điều kiện tương ứng vào SQL mà query sử dụng, giúp query trên lấy dữ liệu phù hợp filter đang bật.

**Điểm quan trọng nhất:** filter được bật trong **một Session**, không phải tự động bật cho mọi Session, và **không phải hàng rào bảo mật tuyệt đối**. Direct loading theo ID, persistence context đã có entity, native SQL, bulk mutations và những đường truy cập khác có các quy tắc riêng. Những giới hạn đó sẽ được giải thích kỹ trong bài.

Bài thuộc chương **Bộ lọc và xóa mềm** của module *Data Persistence Relational Access ORM Hibernate*. Ví dụ hướng đến Hibernate ORM 6.6/7.2, Jakarta Persistence và database quan hệ thông dụng. Một số tùy chọn như `autoEnabled`, `resolver` và `applyToLoadByKey` yêu cầu phiên bản Hibernate phù hợp.

## 1. Bộ lọc động là gì?

Dynamic filter là một điều kiện SQL được gắn vào mapping, nhưng **chỉ có hiệu lực khi filter đang được bật** trong Session, trừ trường hợp nó được cấu hình tự động bật.

Hãy tưởng tượng:

~~~text
Ứng dụng tạo Hibernate Session
              |
              v
enableFilter("tenantScope")
  tenantId = "tenant-a"
              |
              v
HQL: from Document d
              |
              v
Hibernate tạo SQL với điều kiện từ mapping:
  SELECT ...
  FROM documents d
  WHERE d.tenant_id = ?
              |
              v
Bind "tenant-a" và thực thi
~~~

Một query HQL giống nhau có thể trả kết quả khác nhau giữa hai Sessions:

~~~text
Session A:
    tenantScope.tenantId = "tenant-a"
    => chỉ những row phù hợp tenant-a ở đường truy vấn áp dụng filter

Session B:
    tenantScope.tenantId = "tenant-b"
    => chỉ những row phù hợp tenant-b ở đường truy vấn áp dụng filter

Session C:
    tenantScope chưa bật
    => filter không giới hạn kết quả
~~~

Đó là sự khác nhau với một `WHERE` cố định trong HQL hoặc `@SQLRestriction` ở mapping.

## 2. Ba bước độc lập: định nghĩa, gắn, kích hoạt

Một filter hoạt động khi đủ các thành phần.

**Bước 1 — Khai báo filter:**

~~~java
@FilterDef(
    name = "visibleForTenant",
    parameters = @ParamDef(
        name = "tenantId",
        type = String.class
    )
)
~~~

`@FilterDef` định nghĩa filter tên `visibleForTenant` và một tham số `tenantId` kiểu `String`.

**Bước 2 — Gắn vào entity hoặc collection:**

~~~java
@Filter(
    name = "visibleForTenant",
    condition = "tenant_id = :tenantId"
)
~~~

`@Filter` nói rằng mapping này phải chịu tác động của filter và cung cấp điều kiện SQL.

**Bước 3 — Bật trong Session:**

~~~java
session.enableFilter("visibleForTenant")
       .setParameter("tenantId", currentTenantId);
~~~

Sau đó mới gọi query.

Nếu chỉ có `@FilterDef` mà không có `@Filter` trên entity/collection cần lọc, filter không tự lan sang mọi mapping. Nếu entity có `@Filter` nhưng Session không bật filter tương ứng, điều kiện thông thường không được thêm vào query.

### Bảng ghi nhớ

| Thành phần | Câu hỏi nó giải quyết |
| --- | --- |
| `@FilterDef(name=...)` | Filter được gọi là gì? Có tham số nào? |
| `@ParamDef(name,type)` | Tham số có kiểu Java/JDBC mapping nào? |
| `@Filter(name,condition)` | Filter ảnh hưởng mapping nào? SQL predicate là gì? |
| `session.enableFilter(name)` | Session này có dùng filter không? |
| `filter.setParameter(name,value)` | Với Session này, giá trị điều kiện là gì? |
| `session.disableFilter(name)` | Có ngừng áp dụng filter trong Session này không? |
| `@FilterDef(autoEnabled=true)` | Có tự bật filter khi tạo Session không? |
| `@FilterDef(applyToLoadByKey=true)` | Có áp dụng cho lookup trực tiếp theo ID không? |

## 3. Mô hình dữ liệu dùng trong ví dụ

Ứng dụng quản lý tài liệu theo tenant và xóa mềm:

~~~sql
CREATE TABLE folders (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    name VARCHAR(150) NOT NULL
);

CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    folder_id BIGINT,
    title VARCHAR(250) NOT NULL,
    status VARCHAR(32) NOT NULL,
    deleted BOOLEAN NOT NULL DEFAULT FALSE,
    valid_from TIMESTAMP NOT NULL,
    valid_to TIMESTAMP,
    CONSTRAINT fk_documents_folder
        FOREIGN KEY (folder_id) REFERENCES folders(id)
);

CREATE INDEX idx_documents_tenant_deleted
    ON documents(tenant_id, deleted, id);

CREATE INDEX idx_documents_folder
    ON documents(folder_id);
~~~

Dữ liệu ví dụ:

~~~sql
INSERT INTO folders (id, tenant_id, name) VALUES
(10, 'tenant-a', 'Hồ sơ A'),
(20, 'tenant-b', 'Hồ sơ B');

INSERT INTO documents (
    id, tenant_id, folder_id, title, status,
    deleted, valid_from, valid_to
) VALUES
(101, 'tenant-a', 10, 'A - công khai', 'PUBLISHED',
 FALSE, TIMESTAMP '2026-01-01 00:00:00', NULL),
(102, 'tenant-a', 10, 'A - đã xóa', 'ARCHIVED',
 TRUE, TIMESTAMP '2026-01-01 00:00:00', NULL),
(103, 'tenant-a', 10, 'A - chưa hiệu lực', 'DRAFT',
 FALSE, TIMESTAMP '2027-01-01 00:00:00', NULL),
(201, 'tenant-b', 20, 'B - công khai', 'PUBLISHED',
 FALSE, TIMESTAMP '2026-01-01 00:00:00', NULL);
~~~

Ví dụ SQL theo PostgreSQL. Có thể có thêm foreign key/index/constraints ràng buộc tenant đúng cách ở schema production; lược đồ này chỉ nhằm minh họa filters, **chưa đủ làm mô hình bảo mật đa tenant production**.

Các bài thực hành sẽ trả lời: làm sao Session của tenant-a chỉ thấy tài liệu tenant-a, làm sao ẩn tài liệu đã xóa và làm sao lấy tài liệu hợp lệ tại một thời điểm?

## 4. Viết entity cơ bản với `@FilterDef` và `@Filter`

~~~java
package com.example.documents.domain;

import java.time.LocalDateTime;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.FetchType;
import jakarta.persistence.Table;

import org.hibernate.annotations.Filter;
import org.hibernate.annotations.FilterDef;
import org.hibernate.annotations.ParamDef;

@Entity
@Table(name = "documents")
@FilterDef(
    name = "tenantScope",
    parameters = @ParamDef(
        name = "tenantId",
        type = String.class
    )
)
@Filter(
    name = "tenantScope",
    condition = "tenant_id = :tenantId"
)
public class Document {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "title", nullable = false)
    private String title;

    @Column(name = "status", nullable = false)
    private String status;

    @Column(name = "deleted", nullable = false)
    private boolean deleted;

    @Column(name = "valid_from", nullable = false)
    private LocalDateTime validFrom;

    @Column(name = "valid_to")
    private LocalDateTime validTo;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "folder_id")
    private Folder folder;

    protected Document() {
    }

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getTitle() {
        return title;
    }

    public boolean isDeleted() {
        return deleted;
    }
}
~~~

`@FilterDef` và `@Filter` trên cùng class phục vụ hai mục đích khác nhau. Tên `tenantScope` phải khớp chính xác.

### SQL predicate thuộc tầng SQL, không phải JPQL

Trong:

~~~java
condition = "tenant_id = :tenantId"
~~~

`tenant_id` là **tên cột database**. Không viết `d.tenantId = :tenantId` theo JPQL alias/entity property; `@Filter.condition` là một **mảnh SQL predicate**, sau đó Hibernate chèn vào SQL tương ứng.

Tham số `:tenantId` là tên đã định nghĩa trong `@ParamDef`. Hibernate bind giá trị do `Filter.setParameter` nhận, thay vì ghép chuỗi trực tiếp.

## 5. Gắn `@FilterDef` một nơi, dùng `@Filter` nhiều nơi

`@FilterDef` là định nghĩa có tên trong persistence unit. Không cần khai báo lại cùng filter ở mọi entity.

Ví dụ trong `package-info.java`:

~~~java
@FilterDef(
    name = "tenantScope",
    parameters = @ParamDef(
        name = "tenantId",
        type = String.class
    )
)
package com.example.documents.domain;

import org.hibernate.annotations.FilterDef;
import org.hibernate.annotations.ParamDef;
~~~

Document:

~~~java
@Entity
@Filter(
    name = "tenantScope",
    condition = "tenant_id = :tenantId"
)
public class Document {
    // ...
}
~~~

Folder:

~~~java
@Entity
@Filter(
    name = "tenantScope",
    condition = "tenant_id = :tenantId"
)
public class Folder {
    // ...
}
~~~

Hai entity chịu cùng filter khi Session bật `tenantScope`, với cùng tham số `tenantId`.

Chú ý:

- `@FilterDef` có target **TYPE hoặc PACKAGE** theo Hibernate 6.x/7.x.
- Một filter name phải duy nhất trong persistence unit.
- Có thể dùng annotation repeatable để khai báo nhiều FilterDef.
- Mỗi entity/collection cần `@Filter` tương ứng nếu muốn mapping đó bị lọc.
- Khi filter được bật, điều kiện khác nhau trên các mappings có thể dùng **cùng parameter**.

Không khai báo hai `@FilterDef` trùng tên nhưng khác kiểu/semantics trong các modules khác nhau; điều đó tạo xung đột khi Hibernate bootstrap.

## 6. Kích hoạt filter ngay khi bắt đầu Session

Native Hibernate:

~~~java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    try {
        session.enableFilter("tenantScope")
               .setParameter("tenantId", "tenant-a")
               .validate();

        List<Document> documents =
            session.createSelectionQuery(
                "from Document d order by d.id",
                Document.class
            ).getResultList();

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
}
~~~

`validate()` của `org.hibernate.Filter` kiểm tra trạng thái tham số đã được cung cấp phù hợp ở mức Hibernate hỗ trợ. Trong các ví dụ nhỏ có thể bỏ gọi tường minh vì Hibernate cũng kiểm tra filter khi sử dụng, nhưng việc gọi ngay sau cấu hình hữu ích để phát hiện thiếu tham số sớm.

**Hãy bật filter và set đầy đủ tham số trước mọi thao tác đọc liên quan trong Session.** Tài liệu Hibernate khuyến nghị set parameter ngay sau `enableFilter` và trước khi dùng Session.

### SQL minh họa

HQL:

~~~hql
from Document d order by d.id
~~~

SQL do Hibernate tạo có thể có ý nghĩa tương đương:

~~~sql
SELECT d.id, d.tenant_id, d.title, d.status,
       d.deleted, d.valid_from, d.valid_to
FROM documents d
WHERE d.tenant_id = ?
ORDER BY d.id;
~~~

Driver nhận bind value `tenant-a`.

SQL cụ thể phụ thuộc dialect, query shape và mapping. Điều đáng nhớ là predicate được bổ sung **vì filter đang bật**, không phải vì HQL tự viết WHERE.

## 7. Mỗi Session có trạng thái filter riêng

Ví dụ:

~~~java
try (Session sessionA = sessionFactory.openSession();
     Session sessionB = sessionFactory.openSession()) {

    sessionA.enableFilter("tenantScope")
            .setParameter("tenantId", "tenant-a");

    sessionB.enableFilter("tenantScope")
            .setParameter("tenantId", "tenant-b");

    List<Document> a = sessionA.createSelectionQuery(
        "from Document", Document.class
    ).getResultList();

    List<Document> b = sessionB.createSelectionQuery(
        "from Document", Document.class
    ).getResultList();
}
~~~

Đây là hai ngữ cảnh độc lập. Tham số ở Session A **không** tự chuyển sang Session B.

Filter state không thuộc toàn bộ JVM, không thuộc một static variable, và không phải property tự thay đổi trên SessionFactory.

### Điều gì xảy ra với Session mới?

Trừ khi filter được định nghĩa `autoEnabled=true`, Session mới **không tự kế thừa filter đã bật trong Session cũ**.

Một request khác tạo Session mới mà quên bật `tenantScope` có thể chạy query không có predicate tenant. Vì vậy trong ứng dụng production cần một **đường khởi tạo Session được kiểm soát**, hoặc dùng cơ chế đa tenant/database-level security phù hợp khi tenant isolation là yêu cầu bảo mật.

## 8. Tắt filter bằng `disableFilter`

Sau khi bật:

~~~java
session.enableFilter("tenantScope")
       .setParameter("tenantId", "tenant-a");
~~~

có thể tắt:

~~~java
session.disableFilter("tenantScope");
~~~

Từ đó các query tương lai mà Hibernate tạo có thể không còn điều kiện `tenantScope` (trừ khi nó được bật lại). **Nhưng điều này không tự xóa các managed entities đã nạp** trong persistence context.

Trong code có Session được dùng lại cho nhiều thao tác độc lập, hãy kiểm soát vùng scope:

~~~java
session.enableFilter("tenantScope")
       .setParameter("tenantId", "tenant-a");

try {
    // Chỉ thực hiện query phù hợp tenant-a.
} finally {
    session.disableFilter("tenantScope");
}
~~~

Mẫu `finally` dọn filter state trong Session. Tuy nhiên, nó **không biến một Session dài hạn trở thành tenant-isolated an toàn** nếu Session đã giữ các entity/collection được load với filter khác. Với multi-tenancy, thông thường nên dùng một Session/transaction theo từng ngữ cảnh request và không đổi tenant giữa vòng đời persistence context.

## 9. Vì sao bật filter muộn có thể sai?

Giả sử:

~~~java
Document document =
    session.find(Document.class, 201L);

session.enableFilter("tenantScope")
       .setParameter("tenantId", "tenant-a");
~~~

Có hai vấn đề:

1. Direct `find` theo primary key mặc định **không áp dụng filter** trừ khi có cấu hình `applyToLoadByKey` tương ứng.
2. Entity 201 đã có thể được đưa vào persistence context. Bật filter sau đó **không loại bỏ** managed object đang được giữ.

Tương tự:

~~~java
Folder folder = session.find(Folder.class, 10L);
int countBefore = folder.getDocuments().size();

session.enableFilter("notDeleted");

int countAfter = folder.getDocuments().size();
~~~

Nếu collection `documents` đã được initialized, filter bật sau đó **không tự tải lại một collection khác**. Nó vẫn có thể chứa các phần tử đã nạp ở lần trước.

**Quy tắc:** đặt filter state ngay đầu Session, trước query và trước khởi tạo collections. Không toggle filter trong một Session dài hạn rồi dựa vào đó như một ranh giới dữ liệu chắc chắn.

## 10. Thêm filter xóa mềm có thể bật/tắt

Entity Document có cột:

~~~sql
deleted BOOLEAN NOT NULL DEFAULT FALSE
~~~

Khai báo:

~~~java
@FilterDef(name = "notDeleted")
@Filter(
    name = "notDeleted",
    condition = "deleted = false"
)
@Entity
public class Document {
    // ...
}
~~~

Ở Session bình thường:

~~~java
session.enableFilter("notDeleted");

List<Document> visible = session.createSelectionQuery(
    "from Document d order by d.id",
    Document.class
).getResultList();
~~~

Ở Session quản trị cần xem cả rows đã xóa:

~~~java
// Không enable notDeleted cho luồng đặc biệt
// sau khi đã xác thực quyền quản trị.
List<Document> all = adminSession.createSelectionQuery(
    "from Document d order by d.id",
    Document.class
).getResultList();
~~~

Ưu điểm là **khả năng bật/tắt**. Nhược điểm là quên bật filter ở một Session có thể làm lộ hàng đã xóa hoặc đưa dữ liệu đó vào workflow sai.

### Filter không thực hiện soft delete DML

`@Filter(name="notDeleted")` chỉ ảnh hưởng đọc dữ liệu khi filter áp dụng. Nó **không** thay:

~~~java
session.remove(document);
~~~

thành:

~~~sql
UPDATE documents SET deleted = true WHERE id = ?;
~~~

Nếu muốn thao tác remove biến thành UPDATE, cần cơ chế soft-delete mapping riêng. Hibernate 6.4+ có `@SoftDelete`, thường được ưu tiên khi toàn bộ domain có quy tắc xóa mềm cố định.

**Filter có thể hỗ trợ chế độ xem linh hoạt, nhưng bản thân filter không định nghĩa hành vi xóa.**

## 11. `@SoftDelete`, `@SQLRestriction` và `@Filter` khác gì?

| Cơ chế | Động theo Session? | Nhận tham số? | Mục đích |
| --- | --- | --- | --- |
| `@Filter` | Có | Có | Predicate có thể bật/tắt theo Session |
| `@FilterDef` | Khai báo, không tự áp vào mapping | Khai báo param types | Định nghĩa filter |
| `@SQLRestriction` | Không | Không | Predicate SQL tĩnh trên mapping |
| `@SoftDelete` (Hibernate 6.4+) | Theo mapping, không phải toggle filter | Không theo mô hình `@Filter` | Soft-delete semantics chính thức |
| JPQL/HQL `where` | Theo từng query | Có | Điều kiện của một truy vấn |
| Database row-level security | Theo DB policy và connection/user context | Theo DB | Enforce quyền dưới database |
| Hibernate multi-tenancy | Theo tenant selection/schema/connection | Theo cấu hình | Phân vùng dữ liệu ở persistence layer |

Ví dụ `@SQLRestriction`:

~~~java
@Entity
@SQLRestriction("deleted = false")
public class Document {
    // ...
}
~~~

Không thể `disableFilter` để bỏ `@SQLRestriction` vì nó không phải named dynamic filter. Điều kiện là tĩnh.

Ví dụ Hibernate `@SoftDelete`:

~~~java
@Entity
@SoftDelete(
    strategy = SoftDeleteType.DELETED,
    columnName = "deleted"
)
public class Document {
    // ...
}
~~~

Đây là minh họa concept với `@SoftDelete` của Hibernate 6.4+. Nếu dùng thuộc tính boolean `deleted` được map đồng thời như một field writable, phải xem quy tắc mapping tránh trùng cột/duplicate writes; ví dụ không phải đề xuất chép đè nguyên entity trước đó.

**Nên ưu tiên `@SoftDelete`** cho chính sách soft delete bất biến và chuẩn hóa. `@Filter` phù hợp khi cần trạng thái đọc động như quản trị xem deleted records hoặc điều kiện theo tenant/time window.

## 12. Nhiều filters cùng bật: điều kiện kết hợp

Entity có nhiều `@FilterDef`/`@Filter`:

~~~java
@FilterDef(
    name = "tenantScope",
    parameters = @ParamDef(
        name = "tenantId",
        type = String.class
    )
)
@FilterDef(name = "notDeleted")
@Entity
@Filter(
    name = "tenantScope",
    condition = "tenant_id = :tenantId"
)
@Filter(
    name = "notDeleted",
    condition = "deleted = false"
)
@Table(name = "documents")
public class Document {
    // ...
}
~~~

Bật cả hai:

~~~java
session.enableFilter("tenantScope")
       .setParameter("tenantId", "tenant-a");

session.enableFilter("notDeleted");
~~~

SQL logic:

~~~sql
SELECT ...
FROM documents d
WHERE d.tenant_id = ?
  AND d.deleted = false;
~~~

Thông thường các active filter predicates áp dụng cho cùng table/query được kết hợp như những điều kiện **AND**, bên cạnh predicates từ HQL và mapping khác.

Nếu muốn **OR** giữa hai điều kiện nghiệp vụ, đừng đơn giản bật hai filters rồi mong Hibernate tự đổi sang OR. Hãy biểu diễn OR trong **một condition rõ ràng** hoặc một query phù hợp.

### Filter và query WHERE cùng tồn tại

HQL:

~~~hql
select d
from Document d
where d.status = :status
order by d.id
~~~

Khi bật tenantScope và notDeleted, SQL logic có:

~~~sql
WHERE d.status = ?
  AND d.tenant_id = ?
  AND d.deleted = false
~~~

`:status` là parameter của query; `:tenantId` là parameter của filter. Hai cơ chế binding độc lập dù đều dùng ký hiệu tên bắt đầu bằng dấu hai chấm.

## 13. Dùng một filter với tham số boolean

Một use case muốn trả tài liệu đã xóa **theo chế độ xem**:

~~~java
@FilterDef(
    name = "deletionView",
    parameters = @ParamDef(
        name = "includeDeleted",
        type = Boolean.class
    )
)
@Filter(
    name = "deletionView",
    condition = "(:includeDeleted = true OR deleted = false)"
)
@Entity
public class Document {
    // ...
}
~~~

Bật với `false`:

~~~java
session.enableFilter("deletionView")
       .setParameter("includeDeleted", false);
~~~

Bật với `true`:

~~~java
session.enableFilter("deletionView")
       .setParameter("includeDeleted", true);
~~~

Khi tham số false, predicate chỉ giữ rows `deleted=false`; khi true, predicate luôn đúng.

**Lưu ý portability:** SQL boolean literal `true`/`false` trong filter condition phụ thuộc dialect và cột boolean của DB. Với database lưu flag dạng `CHAR(1)` hoặc số, cần predicate/Java type mapping tương thích, không sao chép SQL boolean của PostgreSQL cho mọi hệ quản trị.

Trong nhiều ứng dụng, hai lựa chọn “bật notDeleted” hoặc “không bật” dễ hiểu hơn việc dùng một filter boolean phức tạp. Nhưng chế độ không bật phải được bảo vệ bằng authorization, không phó mặc request parameter.

## 14. Filter theo thời điểm hiệu lực

Giả sử mỗi Document có:

~~~text
valid_from: thời điểm bắt đầu hiệu lực
valid_to:   thời điểm kết thúc, có thể NULL
~~~

Điều kiện trong khoảng nửa mở:

\[
validFrom \leq at < validTo
\]

với `validTo = NULL` nghĩa không có ngày hết hạn.

Khai báo:

~~~java
@FilterDef(
    name = "validAt",
    parameters = @ParamDef(
        name = "at",
        type = LocalDateTime.class
    )
)
@Filter(
    name = "validAt",
    condition = """
        valid_from <= :at
        AND (valid_to IS NULL OR valid_to > :at)
        """
)
@Entity
public class Document {
    // ...
}
~~~

Trong source Java annotation, text block hỗ trợ trên những phiên bản Java phù hợp; nếu code style/build giới hạn annotation constant expression hoặc muốn tránh khác biệt cú pháp, dùng chuỗi nối:

~~~java
@Filter(
    name = "validAt",
    condition = "valid_from <= :at " +
                "and (valid_to is null or valid_to > :at)"
)
~~~

Bật:

~~~java
LocalDateTime asOf =
    LocalDateTime.of(2026, 11, 15, 9, 0);

session.enableFilter("validAt")
       .setParameter("at", asOf);
~~~

**Một tham số filter có thể xuất hiện nhiều lần** trong condition. Giá trị cùng tên sẽ được Hibernate bind theo mapping thích hợp.

### Vì sao dùng khoảng nửa mở?

Với dữ liệu phiên bản:

~~~text
Version 1: [09:00, 10:00)
Version 2: [10:00, 11:00)
~~~

Tại đúng 10:00, version 1 đã hết hiệu lực và version 2 bắt đầu. Khoảng nửa mở giúp tránh hai phiên bản cùng được coi là còn hiệu lực ở thời điểm biên.

**Time zone:** Nếu database dùng TIMESTAMP WITHOUT TIME ZONE, cần thống nhất ý nghĩa thời gian. Với dữ liệu toàn cầu hoặc audit, nên thiết kế kiểu thời gian và conversion theo UTC/offset nhất quán; ví dụ `LocalDateTime` ở đây phục vụ biểu diễn ý tưởng filter, không tự xử lý mọi vấn đề timezone.

## 15. Định nghĩa điều kiện mặc định bằng `defaultCondition`

`@FilterDef` có thể khai báo predicate dùng chung:

~~~java
@FilterDef(
    name = "notDeleted",
    defaultCondition = "deleted = false"
)
~~~

Entity chỉ cần:

~~~java
@Entity
@Filter(name = "notDeleted")
public class Document {
    // ...
}
~~~

Đối tượng khác cũng có cột `deleted`:

~~~java
@Entity
@Filter(name = "notDeleted")
public class Folder {
    // ...
}
~~~

Khi bật filter, hai entity áp dụng condition mặc định.

Có thể override ở mapping có schema khác:

~~~java
@Entity
@Filter(
    name = "notDeleted",
    condition = "archived_flag = 'N'"
)
public class LegacyRecord {
    // ...
}
~~~

**`defaultCondition` không tự tạo `@Filter` cho mọi entity.** Nó chỉ cung cấp condition mặc định cho mappings đã gắn tên filter.

Nếu một module có nhiều bảng lưu trạng thái xóa khác nhau, việc tái sử dụng tên filter cần được thiết kế nhất quán. Không để condition mặc định trỏ tới cột không tồn tại.

## 16. Dùng `setParameterList` với IN

Một ứng dụng có thể cho phép nhiều trạng thái tài liệu:

~~~java
@FilterDef(
    name = "allowedStatuses",
    parameters = @ParamDef(
        name = "statuses",
        type = String.class
    )
)
@Filter(
    name = "allowedStatuses",
    condition = "status IN (:statuses)"
)
@Entity
public class Document {
    // ...
}
~~~

Bật:

~~~java
session.enableFilter("allowedStatuses")
       .setParameterList(
           "statuses",
           List.of("PUBLISHED", "REVIEW")
       );
~~~

Ở Hibernate `org.hibernate.Filter`, `setParameterList` hỗ trợ collection hoặc array cho IN-style predicate.

### Không truyền list vào `setParameter` chỉ vì Java nhận Object

Sai ý định:

~~~java
session.enableFilter("allowedStatuses")
       .setParameter(
           "statuses",
           List.of("PUBLISHED", "REVIEW")
       );
~~~

Dùng `setParameterList` để truyền giá trị IN theo contract của Hibernate.

### List rỗng thì sao?

`IN ()` không có cùng cách xử lý ở mọi database. Không phụ thuộc vào một hành vi nhất định cho empty parameter list nếu chưa xác minh Hibernate/dialect.

Nếu danh sách quyền truy cập rỗng, ứng dụng nên **fail closed**:

~~~java
if (allowedStatuses.isEmpty()) {
    return List.of();
}

session.enableFilter("allowedStatuses")
       .setParameterList(
           "statuses",
           allowedStatuses
       );
~~~

Hoặc thay thế bằng một query luôn false theo cách an toàn. Không tắt filter khi danh sách quyền rỗng, vì như vậy có thể mở rộng truy cập thành “tất cả trạng thái”.

## 17. Lấy filter đang bật và kiểm tra trạng thái

Hibernate Session cung cấp:

~~~java
Filter filter = session.getEnabledFilter("tenantScope");
~~~

Kết quả có thể là `null` nếu filter chưa được bật.

Ví dụ:

~~~java
Filter active = session.getEnabledFilter("tenantScope");

if (active == null) {
    throw new IllegalStateException(
        "Tenant filter chưa được bật"
    );
}
~~~

Dùng import `org.hibernate.Filter`, không nhầm với annotation `org.hibernate.annotations.Filter`.

Phân biệt hai types:

~~~java
import org.hibernate.Filter;                 // Runtime Filter object
import org.hibernate.annotations.FilterDef;  // Annotation
~~~

Khi cùng dùng annotation `@Filter` và runtime interface `Filter`, nên viết fully-qualified type ở một chỗ để tránh import collision:

~~~java
org.hibernate.Filter runtimeFilter =
    session.enableFilter("tenantScope");
~~~

`getEnabledFilter` giúp kiểm tra state, nhưng việc filter object có mặt **không chứng minh** mọi đường SQL đều được lọc hoặc tất cả entities đã managed đều đúng tenant.

## 18. `autoEnabled = true`: tự bật mỗi Session

Từ Hibernate 6.5, `@FilterDef` hỗ trợ `autoEnabled`:

~~~java
@FilterDef(
    name = "notDeleted",
    autoEnabled = true,
    defaultCondition = "deleted = false"
)
@Entity
@Filter(name = "notDeleted")
public class Document {
    // ...
}
~~~

Khi tạo Session, filter `notDeleted` được bật tự động, không cần:

~~~java
session.enableFilter("notDeleted");
~~~

Tuy nhiên, `autoEnabled=true` không biến filter thành ràng buộc bảo mật hoặc DDL constraint. Session có thể tắt filter, và đường direct load theo ID mặc định có quy tắc khác nếu không bật `applyToLoadByKey`.

### Không có tham số

Với filter không có tham số như `deleted=false`, autoEnabled tương đối đơn giản.

### Có tham số

Với filter tenant:

~~~java
@FilterDef(
    name = "tenantScope",
    autoEnabled = true,
    parameters = @ParamDef(
        name = "tenantId",
        type = String.class,
        resolver = CurrentTenantSupplier.class
    )
)
~~~

Hibernate cần một cơ chế cung cấp giá trị `tenantId` cho từng Session/current context. `@ParamDef.resolver` là cách định nghĩa một `Supplier` cho tham số. Không chỉ bật autoEnabled rồi để tham số tenant bị thiếu.

## 19. Resolver cho filter auto-enabled

Một resolver có thể triển khai:

~~~java
package com.example.documents.security;

import java.util.function.Supplier;

public final class CurrentTenantSupplier
        implements Supplier<String> {

    private final CurrentTenantContext tenantContext;

    public CurrentTenantSupplier(
            CurrentTenantContext tenantContext) {
        this.tenantContext = tenantContext;
    }

    @Override
    public String get() {
        String tenant = tenantContext.requiredTenantId();

        if (tenant == null || tenant.isBlank()) {
            throw new IllegalStateException(
                "Không xác định được tenant hiện tại"
            );
        }

        return tenant;
    }
}
~~~

`CurrentTenantContext` là interface/application component do ứng dụng định nghĩa, không phải Hibernate API.

`@ParamDef.resolver` yêu cầu một class triển khai `Supplier`. Theo Hibernate documentation, resolver được tích hợp như một managed bean, vì vậy constructor injection chỉ chạy nếu Hibernate có bean container integration tương thích (ví dụ trong một ứng dụng Spring được cấu hình đúng).

Khai báo:

~~~java
@FilterDef(
    name = "tenantScope",
    autoEnabled = true,
    parameters = @ParamDef(
        name = "tenantId",
        type = String.class,
        resolver = CurrentTenantSupplier.class
    )
)
@Filter(
    name = "tenantScope",
    condition = "tenant_id = :tenantId"
)
@Entity
public class Document {
    // ...
}
~~~

### Những rủi ro cần kiểm soát

- Không có tenant trong context thì **ném lỗi**, không trả null để vô tình mở rộng truy cập.
- Resolver phải được quản lý đúng scope và dependency injection.
- Không đọc tenant ID từ một global mutable variable không thread-safe.
- Nếu dùng ThreadLocal, cần dọn sau request và đảm bảo context propagation qua async/executor.
- Không tin tenant ID do client tự gửi nếu chưa xác thực và authorize.
- Session đã giữ entity trước khi giá trị tenant thay đổi không tự refilter managed state.
- Filter autoEnabled không thay thế database RLS hoặc multi-tenancy enforcement.

**autoEnabled là cơ chế tiện ích cho filter state, không phải nơi giải quyết toàn bộ hệ thống xác thực/ủy quyền.**

## 20. `applyToLoadByKey`: ngoại lệ quan trọng của filter

Theo mặc định, Hibernate dynamic filters áp dụng cho entity queries, nhưng **không nhất thiết áp dụng cho trực tiếp load entity theo primary key**.

Ví dụ:

~~~java
session.enableFilter("tenantScope")
       .setParameter("tenantId", "tenant-a");

Document doc = session.find(Document.class, 201L);
~~~

Nếu mapping chỉ có:

~~~java
@FilterDef(
    name = "tenantScope",
    parameters = @ParamDef(
        name = "tenantId",
        type = String.class
    )
)
~~~

thì `find` có thể vẫn tải Document 201 của tenant-b theo ID. Đây là **hành vi thiết kế**, không phải bug.

Hibernate 6.6/7.2 hỗ trợ:

~~~java
@FilterDef(
    name = "tenantScope",
    applyToLoadByKey = true,
    parameters = @ParamDef(
        name = "tenantId",
        type = String.class
    )
)
~~~

Với cấu hình này, filter có thể được áp dụng vào các thao tác load trực tiếp theo ID, bao gồm những đường tải to-one association tương ứng.

**Tuy nhiên, đây là tùy chọn SPI còn được đánh dấu `@Incubating` trong tài liệu một số versions.** Khi dùng phải kiểm tra version cụ thể và integration tests.

## 21. `applyToLoadByKey=true` có thể ảnh hưởng quan hệ to-one

Giả sử Order có FK tới Customer:

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
~~~

Customer bị gắn filter với `applyToLoadByKey=true`. Khi Hibernate cần load Customer theo FK nhưng filter loại row đó, association vốn kỳ vọng tồn tại có thể không được thỏa mãn.

Hibernate Javadocs mô tả rằng trường hợp filter làm một to-one association bị null hóa có thể ném `EntityFilterException`.

Vì sao?

~~~text
orders.customer_id = 15      // FK tồn tại
customers.id = 15            // row tồn tại
customers.tenant_id = 'B'    // filter Session tenant A loại row
~~~

Nếu Hibernate âm thầm biến association thành null, entity state không còn phản ánh đúng foreign key/constraint.

Đặc biệt cẩn thận khi kết hợp `@NotFound(action=IGNORE)` với filter theo load-by-key. Hibernate documentation cảnh báo cách đó có thể đưa association thành null và trong một số trường hợp dẫn tới update FK ngoài ý muốn khi flush.

**Đừng bật applyToLoadByKey cho toàn bộ mappings mà không kiểm tra các association và entity graphs liên quan.**

## 22. Filter không tự loại managed entity đã nằm trong L1 cache

Persistence context của Session là cache tầng một (L1):

~~~java
Document first = session.find(Document.class, 201L);

// Một entity đã được nạp và managed.
session.enableFilter("tenantScope")
       .setParameter("tenantId", "tenant-a");

Document again = session.find(Document.class, 201L);
~~~

Nếu entity 201 vẫn đang managed, Hibernate có thể trả **cùng object đã có** mà không phát SQL. Filter được thêm vào query SQL mới không thể retroactively xóa object khỏi Java persistence context.

Ngay cả với `applyToLoadByKey=true`, không được mặc định nó sẽ biến một Session đã chứa entity khác tenant thành một Session an toàn sau khi đổi parameter.

Các nguyên tắc:

1. Xác định tenant/context trước khi tạo hoặc sử dụng Session.
2. Bật filter trước mọi load.
3. Không đổi tenant trong cùng persistence context.
4. Không chia sẻ Session giữa threads/requests.
5. Không dùng `session.clear()` như một cách khắc phục bảo mật tổng quát; nó còn có thể làm mất pending changes.
6. Với isolation nghiêm ngặt, enforce ở DB hoặc dùng multi-tenancy design phù hợp.

## 23. Filter áp dụng thế nào lên collection?

Giả sử Folder có nhiều Document:

~~~java
@Entity
@Table(name = "folders")
public class Folder {

    @Id
    private Long id;

    @OneToMany(
        mappedBy = "folder",
        fetch = FetchType.LAZY
    )
    @Filter(
        name = "notDeleted",
        condition = "deleted = false"
    )
    private List<Document> documents = new ArrayList<>();

    public List<Document> getDocuments() {
        return documents;
    }
}
~~~

Giả sử `notDeleted` đã được định nghĩa qua `@FilterDef` ở package/class metadata. Khi Session bật `notDeleted`:

~~~java
session.enableFilter("notDeleted");

Folder folder = session.find(Folder.class, 10L);

List<Document> visible = folder.getDocuments();
visible.size(); // Collection lazy có thể được initialized.
~~~

SQL load collection có thể thêm:

~~~sql
SELECT d.*
FROM documents d
WHERE d.folder_id = ?
  AND d.deleted = false;
~~~

**Annotation trên collection role không đồng nghĩa toàn bộ root entity query khác tự bị filter.** Nếu cần cả hai, gắn filter trên entity Document **và** trên collection mapping phù hợp.

### Collection đã initialized thì sao?

Nếu `folder.getDocuments()` đã được load khi filter tắt, bật filter sau đó **không tự cắt phần tử khỏi List/Set Java hiện có**. Cần thiết kế lifecycle Session/collection nhất quán.

## 24. Phân biệt filter entity và filter join table

Với ManyToMany:

~~~sql
CREATE TABLE tags (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE document_tags (
    document_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (document_id, tag_id)
);
~~~

`Tag` là entity; `document_tags` là bảng liên kết.

Nếu muốn lọc **trạng thái của row trong bảng liên kết**, dùng `@FilterJoinTable`:

~~~java
@FilterDef(name = "activeDocumentTagLinks")
@Entity
public class Document {

    @Id
    private Long id;

    @ManyToMany
    @JoinTable(
        name = "document_tags",
        joinColumns = @JoinColumn(name = "document_id"),
        inverseJoinColumns = @JoinColumn(name = "tag_id")
    )
    @FilterJoinTable(
        name = "activeDocumentTagLinks",
        condition = "active = true"
    )
    private Set<Tag> tags = new HashSet<>();
}
~~~

Bật:

~~~java
session.enableFilter("activeDocumentTagLinks");
~~~

Khi load `document.getTags()`, filter liên quan **cột `active` của join table**, không phải thuộc tính `Tag`.

Trong khi đó, một `@Filter` gắn vào `Tag` hoặc collection có condition liên quan các cột target table khác ý nghĩa.

### Bảng so sánh

| Annotation | Predicate hướng tới |
| --- | --- |
| `@Filter` trên entity | Bảng/hàng của entity |
| `@Filter` trên collection | Phần tử/collection rows theo mapping |
| `@FilterJoinTable` trên association | Bảng liên kết association |
| `@SQLJoinTableRestriction` | Predicate tĩnh ở join table |
| `@SQLRestriction` | Predicate tĩnh ở entity/collection table |

Đừng viết condition `active = true` lên `Tag` nếu cột `active` thực sự nằm trong `document_tags`.

## 25. Điều kiện filter là SQL fragment và vấn đề alias

Thông thường, Hibernate tự chèn table alias vào SQL fragment:

~~~java
@Filter(
    name = "notDeleted",
    condition = "deleted = false"
)
~~~

Khi query phức tạp, tên cột có thể mơ hồ hoặc bộ suy luận alias nhầm một token trong SQL expression là tên cột.

Ví dụ cần kiểm soát alias tường minh:

~~~java
@Filter(
    name = "tenantScope",
    condition = "{alias}.tenant_id = :tenantId",
    deduceAliasInjectionPoints = false
)
~~~

Khi `deduceAliasInjectionPoints=false`, Hibernate chỉ chèn alias tại placeholder `{alias}` được chỉ định rõ.

Đây là cách giảm ambiguity khi SQL fragment có:

- SQL function names.
- Keywords giống tên cột.
- Cột có tên đặc biệt.
- Subquery.
- Nhiều bảng và complex join.
- SQL fragment yêu cầu alias một cách có chủ đích.

### Định danh alias theo table

Hibernate có `@SqlFragmentAlias` để ánh xạ placeholder với table:

~~~java
@Filter(
    name = "tenantScope",
    condition = "{doc}.tenant_id = :tenantId",
    deduceAliasInjectionPoints = false,
    aliases = @SqlFragmentAlias(
        alias = "doc",
        table = "documents"
    )
)
~~~

Ví dụ này dùng import `org.hibernate.annotations.SqlFragmentAlias`. Placeholder `{doc}` được liên kết với alias của table `documents` trong SQL mà Hibernate tạo, theo metadata mapping/dialect.

**Không tự ghép một SQL alias từ HQL** như `d.tenant_id` nếu Hibernate có thể sinh alias khác; hãy dùng cơ chế alias injection dành riêng cho `@Filter`.

## 26. Condition không phải một câu SQL SELECT đầy đủ

`@Filter.condition` có dạng predicate:

~~~java
condition = "tenant_id = :tenantId"
~~~

Không viết:

~~~java
condition = "SELECT * FROM documents WHERE tenant_id = :tenantId"
~~~

vì Hibernate chèn condition vào SQL hiện tại. Đây không phải native query nguyên vẹn.

Filter condition có thể chứa SQL expression hoặc subquery phù hợp dialect, nhưng không được tự tùy tiện thêm JOIN clauses như đang viết toàn bộ FROM tree. Nếu cần logic join phức tạp, cân nhắc subquery/EXISTS với alias đúng, hoặc truy vấn rõ ràng ở repository.

Ví dụ subquery mang tính ý tưởng:

~~~java
@Filter(
    name = "allowedDocument",
    deduceAliasInjectionPoints = false,
    condition = """
        exists (
            select 1
            from document_acl a
            where a.document_id = {alias}.id
              and a.user_id = :userId
        )
        """
)
~~~

FilterDef cần có parameter `userId` và SQL phải được kiểm tra trên database/dialect thực tế. Nếu ACL là security invariant, chỉ dựa vào Hibernate filter **chưa đủ** vì vẫn có những đường truy cập không qua filter.

## 27. Filter và SQL injection

Filter parameters được Hibernate bind thông qua:

~~~java
session.enableFilter("tenantScope")
       .setParameter("tenantId", userTenantId);
~~~

Đó là cách an toàn hơn so với tự ghép giá trị vào SQL fragment.

Không làm:

~~~java
String dynamicCondition =
    "tenant_id = '" + userTenantId + "'";
~~~

`@Filter.condition` là annotation metadata cố định, không nên được biến thành SQL string động lấy từ input không tin cậy.

Nếu ứng dụng xây các tên cột/table/order-by động, bind parameter không bảo vệ được identifiers; phải dùng allowlist/thiết kế query cố định.

Đặc biệt với multi-tenant, **tenant ID lấy từ authenticated authorization context**, không tin một header do client truyền nếu chưa kiểm tra quyền tenant.

## 28. Filter và multi-tenancy: nguy cơ bỏ lọt dữ liệu

Một filter tên `tenantScope` mang tính tiện lợi, nhưng không được xem là lớp bảo mật duy nhất cho tenant separation.

Các đường có thể đi ngoài mong đợi:

- Session nào đó quên `enableFilter`.
- `EntityManager.find` theo ID không áp filter mặc định.
- Entity đã có trong L1 từ trước khi filter được bật.
- Native SQL/JDBC không tự kế thừa filter.
- Một bulk HQL/native mutation có semantics khác entity SELECT.
- Một collection không được gắn `@Filter`.
- Một background job tự mở Session khác.
- Lỗi ThreadLocal tenant context khi async request.
- Cache/application-level DTO cache thiếu tenant key.
- Service trả entity reference không qua authorization ở tầng service.

Với yêu cầu phân tách tenant nghiêm ngặt, cần xem:

1. Database-per-tenant/schema-per-tenant hoặc row discriminator theo thiết kế.
2. Hibernate multi-tenancy support nếu phù hợp.
3. Database row-level security (RLS) nếu database hỗ trợ và cần cưỡng chế mọi SQL.
4. ID design và composite foreign keys đảm bảo không nối chéo tenants.
5. Authorization ở service/API.
6. Integration tests cho **mọi** đường read/write.
7. Không chia sẻ persistence context giữa tenants.

Filter có thể là **một lớp hỗ trợ** nhưng không thay database authorization boundary.

## 29. Ví dụ lỗi bảo mật với direct find

Giả sử endpoint nhận document ID từ URL:

~~~text
GET /documents/201
~~~

Implementation:

~~~java
session.enableFilter("tenantScope")
       .setParameter("tenantId", "tenant-a");

Document document = session.find(Document.class, 201L);
~~~

Nếu filter chưa có `applyToLoadByKey=true`, lookup theo ID có thể tải tài liệu của tenant-b. Nếu service sau đó trả response mà không kiểm tra quyền, dữ liệu bị lộ.

Một cách bảo vệ ở cấp query rõ ràng:

~~~java
Document document = session.createSelectionQuery(
    """
    select d
    from Document d
    where d.id = :id
      and d.tenantId = :tenantId
    """,
    Document.class
)
.setParameter("id", 201L)
.setParameter("tenantId", authenticatedTenantId)
.uniqueResult();
~~~

Query trên biểu diễn điều kiện tenant ngay trong HQL, nhưng vẫn cần authorization/business logic, filter state và kiểm tra các association được tải theo đường khác.

Nếu domain cần cưỡng chế mọi SQL truy cập dữ liệu tenant, database-level policy hoặc kiến trúc multi-tenancy mạnh hơn cần được cân nhắc.

## 30. Filter và soft delete có thể tương tác với association

Giả sử Order có association:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "document_id", nullable = false)
private Document document;
~~~

Nếu `Document` được lọc để ẩn deleted rows:

- Query Documents có thể không trả các hàng đã xóa.
- Direct loading theo ID có thể bỏ qua filter nếu không bật `applyToLoadByKey`.
- Nếu bật `applyToLoadByKey` và target bị filter loại, Hibernate có thể báo `EntityFilterException` với association to-one thay vì giả định FK không tồn tại.
- Nếu người dùng cần xem historical Order vẫn tham chiếu tới deleted Document, phải thiết kế fetch/soft-delete semantics cẩn thận.

Đây là điểm khác biệt giữa:

**Ẩn Document khỏi danh sách tìm kiếm** và **cấm mọi association tham chiếu Document đã xóa**.

Hai quy tắc không phải lúc nào giống nhau. Đừng bật global filter mà chưa xem use cases về lịch sử, báo cáo, audit và foreign keys.

## 31. Ảnh hưởng lên L1 cache và Collection state

L1 cache (persistence context) giữ managed entities. Khi query:

~~~java
session.enableFilter("tenantScope")
       .setParameter("tenantId", "tenant-a");

List<Document> docs = session.createSelectionQuery(
    "from Document", Document.class
).getResultList();
~~~

Hibernate có thể dùng SQL predicate để chọn rows. Nhưng nếu Document đã managed trong Session với state cũ, Hibernate identity map có thể giữ/reuse instance đó.

Với collections:

~~~java
Folder folder = session.find(Folder.class, 10L);
folder.getDocuments().size(); // Collection initialized.

session.enableFilter("notDeleted");
~~~

Collection không tự được lọc lại trong bộ nhớ.

Vì vậy, **filter state nên ổn định suốt Session**. Hãy coi Session như một unit of work có tenant/visibility context cố định.

## 32. Second-level cache và filtered collections

Hibernate User Guide 6.6/7.2 nêu một giới hạn quan trọng:

**Không thể kết hợp collection `@Filter` với collection `@Cache` theo cách thông thường.**

Vì sao?

~~~text
Session A:
  filter notDeleted = enabled
  Folder.documents -> [Document 101]

Nếu cache collection chỉ lưu subset:
  collection cache ownerId=10 -> [101]

Session B:
  filter notDeleted = disabled
  Folder.documents cần [101, 102, 103]

Nhưng cached collection chỉ chứa [101] -> sai!
~~~

Cache collection trong L2 thường lưu membership của **toàn bộ collection** theo owner, không lưu tập con với mọi tổ hợp filter parameters.

Do đó Hibernate hạn chế sử dụng collection cache với filtered collections để tránh cached subset bị dùng sai ở Session khác.

### Entity L2 cache có thể tạo hiểu nhầm

Entity cache có thể lưu state theo ID; nó không tự mã hóa mọi filter condition/tenant visibility hiện hành. Một entity được nạp theo đường ID có thể sử dụng cache bất kể filter state nếu direct lookup behavior không áp filter.

**Đừng bật cache rồi xem cache hit là bằng chứng đã có row-level authorization.** Cache và filter giải quyết những vấn đề khác nhau; cần kiểm chứng cụ thể.

## 33. Query cache và filter parameters

Query cache lưu kết quả truy vấn theo metadata và query inputs phù hợp, còn entity/collection L2 cache lưu data theo entity/owner identity.

Một query:

~~~java
session.enableFilter("tenantScope")
       .setParameter("tenantId", "tenant-a");

List<Document> docs = session.createSelectionQuery(
    "from Document order by id",
    Document.class
)
.setCacheable(true)
.getResultList();
~~~

chỉ nên cache khi đã bật/configure Hibernate query cache và có lý do hiệu năng. Hibernate có mechanisms để phân biệt query results theo inputs/filters, nhưng không được coi đó là giải pháp bảo mật đa tenant.

Điểm cần nhớ:

- Query cache không tự bật chỉ vì một filter active.
- Dynamic filter parameters làm đa dạng query cache keys và giảm reuse giữa tenants/time windows.
- Cache invalidation khi dữ liệu thay đổi vẫn quan trọng.
- L1 và entity L2 caching có lifecycle khác.
- Native SQL hoặc external DB writers có thể làm kết quả stale nếu integration không xử lý.
- Tính đúng đắn của quyền truy cập không được phụ thuộc query cache key.

Nếu có hàng nghìn tenant và nhiều tổ hợp filter, cache theo từng tổ hợp có thể gây memory churn mà lợi ích nhỏ.

## 34. Native SQL/JDBC có bị filter không?

Không được mặc định.

Ví dụ:

~~~java
List<Object[]> rows = session.createNativeQuery(
    "select id, tenant_id, title from documents",
    Object[].class
).getResultList();
~~~

Một SQL native raw không tự được Hibernate biến thành:

~~~sql
SELECT ...
FROM documents
WHERE tenant_id = :tenantId;
~~~

chỉ vì Session đã bật `tenantScope`. Native SQL do ứng dụng cung cấp phải tự bảo đảm predicate/authorization tương ứng.

JDBC trực tiếp:

~~~java
session.doWork(connection -> {
    // PreparedStatement tạo trực tiếp từ connection.
});
~~~

cũng không tự áp dụng `@Filter` cho SQL bạn viết.

Các đường SQL ngoài Hibernate càng củng cố nguyên tắc: **dynamic filters không thay thế database row-level security**.

## 35. Bulk HQL UPDATE/DELETE và filter

Bulk HQL operations khác với việc truy vấn entity rồi sửa managed state:

~~~java
int changed = session.createMutationQuery(
    "update Document d set d.status = :newStatus"
)
.setParameter("newStatus", "ARCHIVED")
.executeUpdate();
~~~

Không nên suy luận rằng một `@Filter` được bật sẽ được áp dụng **giống hệt** mọi entity SELECT vào mọi bulk UPDATE/DELETE trong mọi version/dialect. Bulk operations đi qua đường mutation riêng, bypass entity-by-entity lifecycle/dirty checking và có nhiều hệ quả về persistence context/cache.

Với thao tác mutation nhạy cảm theo tenant, cách an toàn dễ review:

~~~java
int changed = session.createMutationQuery(
    """
    update Document d
    set d.status = :newStatus
    where d.tenantId = :tenantId
      and d.deleted = false
    """
)
.setParameter("newStatus", "ARCHIVED")
.setParameter("tenantId", authenticatedTenantId)
.executeUpdate();
~~~

Và vẫn phải enforce business authorization. Nếu cần database áp cưỡng chế mọi mutation, dùng database constraints/RLS hoặc tenancy isolation phù hợp.

Không xem việc `@Filter` có ảnh hưởng tới một phiên bản bulk HQL cụ thể là lời bảo đảm phổ quát cho mọi DML trong hệ thống.

## 36. Dynamic filter không tự thay đổi cách DELETE

Filter chọn rows cho các thao tác đọc trong đường áp dụng, nhưng không phải DML policy.

Nếu ứng dụng gọi:

~~~java
session.remove(document);
~~~

Hibernate có thể DELETE row thật theo entity mapping, trừ khi có `@SoftDelete` hoặc cơ chế khác.

Nếu chỉ bật:

~~~java
session.enableFilter("notDeleted");
~~~

thì thao tác remove **không mặc nhiên trở thành** `UPDATE deleted=true`.

Phải thiết kế soft delete với đầy đủ các yếu tố:

- Ghi soft-delete flag theo đúng transaction.
- Ẩn dữ liệu ở read paths mong muốn.
- Xử lý associations, orphan removal và cascade.
- Đảm bảo uniqueness business key với soft-delete rows (partial unique index nếu phù hợp).
- Xác định có cho restore hay không.
- Xử lý cache invalidation và audit.
- Đánh giá soft-delete semantics chính thức của Hibernate 6.4+.

Đừng coi `@Filter` là toàn bộ chiến lược soft delete.

## 37. Trường hợp autoEnabled kết hợp quyền quản trị

Ví dụ `notDeleted` tự bật:

~~~java
@FilterDef(
    name = "notDeleted",
    autoEnabled = true,
    defaultCondition = "deleted = false"
)
~~~

Dành cho luồng quản trị hợp lệ:

~~~java
if (!authorization.canViewDeletedDocuments()) {
    throw new AccessDeniedException(
        "Không được truy cập tài liệu đã xóa"
    );
}

session.disableFilter("notDeleted");

List<Document> all = session.createSelectionQuery(
    "from Document", Document.class
).getResultList();
~~~

Đây là ví dụ nguyên tắc, `authorization`/`AccessDeniedException` thuộc ứng dụng/framework tương ứng.

**Authorization phải được kiểm tra trước khi disable filter.** Không lấy boolean `includeDeleted` từ request làm đủ bằng chứng người dùng được phép xem dữ liệu đó.

Dù đang có quyền admin, cần Session/transaction riêng khi đổi visibility scope để tránh reuse collection/entity state đã được nạp với điều kiện khác.

## 38. Spring `@Transactional` và `EntityManager.unwrap`

Trong ứng dụng Spring Data JPA dùng Hibernate:

~~~java
@Service
public class DocumentSearchService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(readOnly = true)
    public List<DocumentSummary> listCurrentTenantDocuments(
            String authenticatedTenantId) {

        Session session =
            entityManager.unwrap(Session.class);

        session.enableFilter("tenantScope")
               .setParameter(
                   "tenantId",
                   authenticatedTenantId
               );

        session.enableFilter("notDeleted");

        return entityManager.createQuery(
            """
            select new com.example.documents.dto.DocumentSummary(
                d.id, d.title
            )
            from Document d
            order by d.id
            """,
            DocumentSummary.class
        ).getResultList();
    }
}
~~~

Giả định `DocumentSummary` có constructor tương ứng, Hibernate là JPA provider và các imports của Spring/JPA được cấu hình đúng.

Điều cần nhớ:

- `@Transactional` xác định transaction boundary theo Spring.
- `entityManager.unwrap(Session.class)` lấy Hibernate Session hiện hành.
- Filter state áp dụng cho Session được dùng bởi EntityManager.
- DTO projection giảm việc giữ managed entity không cần thiết.
- Không tự mở Session khác trong repository nếu cần kế thừa filter state của transaction.
- Không tự `session.close()` với Session do Spring quản lý.

### Nên dùng finally để disable?

Trong transaction-scoped EntityManager/Session được quản lý đúng, Session kết thúc theo transaction/request scope. Nếu code tái sử dụng Session theo cơ chế dài hạn hoặc Open Session in View, cần đặc biệt lưu ý filter state, visibility và cleanup.

Thực tế an toàn hơn là định nghĩa một **policy rõ ở entry point**: Session mới có tenant filter trước query, transaction scope ngắn và không đổi tenant trong cùng context. Việc disable cuối method không giải quyết L1 đã nạp sai scope.

## 39. Open Session in View và filter state

Với web application bật Open Session in View, EntityManager/Session có thể tồn tại qua phần controller/view rendering sau khi service transaction kết thúc.

Nguy cơ:

- Service bật filter nhưng view lazy-load associations sau đó.
- Một code path không bật filter như service khác.
- Session giữ managed objects nhiều hơn kỳ vọng.
- Filter được bật/tắt giữa request rendering và service logic.
- Dữ liệu nhạy cảm bị serialize khi association auto-initialize ở lớp JSON.

Với dữ liệu multi-tenant/visibility quan trọng, nên cân nhắc tắt OSIV và trả DTO đã được tạo hoàn chỉnh trong service transaction, hoặc thiết kế một Session context initializer có kiểm soát.

Không dựa vào điều kiện filter bật trong service A để bảo đảm mọi lazy load ở view layer sau đó đều đúng.

## 40. Không chia sẻ `Session` giữa threads

Hibernate `Session` không thread-safe. Ví dụ sai:

~~~java
static Session sharedSession;
~~~

rồi mỗi request:

~~~java
sharedSession.enableFilter("tenantScope")
             .setParameter("tenantId", requestTenant);
~~~

Trong hệ thống concurrent, request A có thể đặt tenant-a trong khi request B đặt tenant-b lên **cùng Session**, dẫn đến query bị áp tham số sai hoặc trạng thái persistence context trộn lẫn.

Giải pháp:

- Một Session/persistence context thích hợp cho mỗi unit of work/request.
- Không dùng static global Session.
- Không truyền Session sang asynchronous thread khác tùy tiện.
- Không thay filter parameter trong lúc nhiều threads đang dùng một Session.
- Tenant context phải được propagate và dọn đúng.

Khi dùng Spring, để transaction manager quản lý EntityManager scope và không giữ một EntityManager/Session thật như singleton mutable request state.

## 41. Test bằng hai tenant và ba loại đường truy cập

Một bài integration test cần phân biệt:

1. HQL/JPQL entity query.
2. Direct `find` theo ID.
3. Collection initialization.

Pseudo-test:

~~~java
try (Session session = sessionFactory.openSession()) {
    session.enableFilter("tenantScope")
           .setParameter("tenantId", "tenant-a");

    List<Document> result =
        session.createSelectionQuery(
            "from Document d order by d.id",
            Document.class
        ).getResultList();

    // Kỳ vọng không có Document tenant-b.
}
~~~

Direct find:

~~~java
try (Session session = sessionFactory.openSession()) {
    session.enableFilter("tenantScope")
           .setParameter("tenantId", "tenant-a");

    Document byId = session.find(Document.class, 201L);

    // Kiểm thử kỳ vọng theo applyToLoadByKey configuration.
}
~~~

Collection:

~~~java
try (Session session = sessionFactory.openSession()) {
    session.enableFilter("notDeleted");

    Folder folder = session.find(Folder.class, 10L);

    // Kiểm tra folder.getDocuments() khi collection có @Filter.
}
~~~

Đó là ba trường hợp khác nhau. Chỉ test rằng `from Document` có tenant predicate chưa chứng minh mọi đường truy cập đều an toàn.

## 42. Các điều kiện biên cần thử

Với filter thời gian:

~~~text
valid_from <= at
AND (valid_to IS NULL OR valid_to > at)
~~~

Cần thử:

| Tình huống | Kỳ vọng |
| --- | --- |
| `at` trước `valid_from` | Không thấy |
| `at == valid_from` | Thấy |
| `at` nằm giữa khoảng | Thấy |
| `at == valid_to` | Không thấy |
| `valid_to IS NULL` và at sau valid_from | Thấy |
| `valid_to <= valid_from` | Dữ liệu không hợp lệ; cần constraint/validation |

Với tenant filter:

| Tình huống | Kỳ vọng |
| --- | --- |
| Tenant A truy vấn A | Thấy các hàng thỏa những filters khác |
| Tenant A truy vấn B | Không thấy qua đường query áp filter |
| Không có tenant context | Fail closed |
| Gán tenant ID rỗng | Lỗi validation/authorization |
| Direct load ID của B | Xác minh hành vi `applyToLoadByKey` |
| Native SQL không có tenant WHERE | Phải chặn bằng policy riêng |
| Đổi tenant giữa cùng Session | Không cho phép trong service design |

Đây là các tình huống để thiết kế integration tests ở giai đoạn kiểm thử, không phải lệnh thực thi trong bài Markdown.

## 43. Debug SQL của Hibernate filter

Khi phát triển có thể bật SQL logging:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Logger cụ thể và khả năng in binding thay đổi theo Hibernate/Spring version. Không log bind values nhạy cảm trên production nếu chưa được phép.

Khi kiểm tra filter:

1. Xác minh Session thực sự đã bật filter.
2. Xác minh tham số có giá trị đúng.
3. Quan sát SQL WHERE/ON có predicate hay không.
4. Kiểm tra bảng/alias condition được chèn vào.
5. Xác định direct find, lazy association, collection hay entity query.
6. Đối chiếu mapping có `@Filter` đúng tên.
7. Kiểm tra L1 đã giữ object hay collection initialized trước đó.
8. Kiểm tra có native SQL/bulk mutation bypass.
9. Kiểm tra dialect và data types.
10. Nếu query chậm, xem index và execution plan.

**Đừng kết luận filter hỏng chỉ vì một managed entity trong L1 không biến mất**. Nó không được thiết kế để xóa object Java đang managed khi parameter đổi.

## 44. Hiệu năng của dynamic filter

Thêm filter đồng nghĩa thêm predicate vào SQL, có thể thay đổi query plan.

Ví dụ:

~~~sql
WHERE tenant_id = ?
  AND deleted = false
ORDER BY id
LIMIT 20;
~~~

Một index có thể hữu ích:

~~~sql
CREATE INDEX idx_documents_tenant_visible_id
ON documents(tenant_id, deleted, id);
~~~

Tính phù hợp của index phụ thuộc data distribution, selectivity, các cột sort/filter khác và query plan thực tế.

Các trade-off:

- Thêm điều kiện có thể tăng selectivity và giảm rows đọc.
- Nếu index không phù hợp, DB có thể scan nhiều hơn.
- Nhiều filters + OR/subquery phức tạp có thể làm optimizer khó dùng index.
- Mỗi tenant/time-window có thể khiến cached query results kém tái sử dụng.
- Filter ở collection có thể gây thêm SQL khi lazy initialization, không tự giải quyết N+1.
- Predicate chứa function trên cột có thể cản index nếu không có functional index phù hợp.
- Một query trả ít rows vẫn có thể phải scan/sort nhiều data.

Đo bằng EXPLAIN/EXPLAIN ANALYZE và metrics đúng workload, không tăng/giảm số filters theo cảm tính.

## 45. Có nên dùng filter cho mọi yêu cầu truy cập?

Không nhất thiết.

### Phù hợp

- Visibility theo tenant trong một số read use cases có scope rõ.
- Soft-delete view động với quy tắc quản trị được kiểm soát.
- Truy vấn theo as-of date/effective period.
- Filter các phần tử collection theo điều kiện động.
- Library có nhiều queries cùng dùng predicate đã thống nhất.
- Chọn khu vực/trạng thái theo Session request context.

### Không phù hợp nếu là cơ chế duy nhất

- Bảo mật tenant isolation nghiêm ngặt với nhiều đường SQL khác nhau.
- Authorization theo ACL phức tạp, thay đổi theo từng row/user.
- Chính sách xóa mềm cần cả DELETE semantics.
- Kiểm tra business invariants trước ghi.
- Truy vấn báo cáo chỉ dùng một lần, có WHERE rõ hơn.
- Native SQL/JDBC pipeline nơi Hibernate filters không tự áp.
- Điều kiện phải bảo đảm ở database bất kể ORM provider.

Một predicate lặp lại trong vài query đơn giản có thể dễ hiểu hơn filter ẩn bên trong mapping, nhất là khi đội cần kiểm soát chính xác query behavior.

## 46. Bộ lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Query vẫn trả mọi tenant | Filter chưa bật | Enable ở đầu Session |
| Filter bật nhưng không tác dụng | Entity/collection thiếu `@Filter` | Kiểm tra mapping và tên |
| Hibernate báo unknown filter | Không có `@FilterDef` đúng tên | Khai báo definition |
| Filter parameter chưa set | Thiếu `setParameter` | Set ngay sau enable rồi validate |
| Filter IN list lỗi | Dùng `setParameter` thay vì `setParameterList` | Dùng list binding |
| Empty list tạo SQL không mong muốn | Không xử lý danh sách rỗng | Fail closed |
| `find(id)` vẫn trả row bị loại | Mặc định không apply filter to load-by-key | Xem `applyToLoadByKey` và authorization |
| To-one load ném EntityFilterException | applyToLoadByKey loại target FK | Thiết kế association visibility |
| Session đã nạp row trước khi enable | L1 giữ entity | Bật filter sớm, Session scope ngắn |
| Collection không đổi sau enable | Collection đã initialized | Tránh toggle giữa Session |
| Không thấy predicate trên native SQL | Native query bypass filter | Thêm SQL guard/DB RLS |
| Bulk update ảnh hưởng rows ngoài dự kiến | Không có explicit mutation predicate | Viết tenant WHERE rõ |
| Filter autoEnabled nhưng thiếu tenant | Resolver/bean context sai | Fail closed, cấu hình resolver |
| Bean resolver không inject được | BeanContainer integration thiếu | Cấu hình managed bean |
| Filter condition gây SQL grammar error | Sai column/alias/function | SQL fragment và alias injection |
| ParamDef type không tương thích cột | Sai Java type/SQL type | Dùng type mapping đúng |
| Query chậm sau khi bật filter | Không có index/plan phù hợp | EXPLAIN và index |
| Soft delete bật nhưng remove vẫn DELETE | Filter chỉ điều chỉnh đọc | Dùng `@SoftDelete` hoặc DML policy khác |
| Collection cache xung đột | Filtered collection không phù hợp `@Cache` | Bỏ collection cache hoặc đổi kiến trúc |
| User khác tenant nhìn thấy data từ cache/service | Session/L1/cache scope thiếu isolation | Rà soát mọi đường truy cập |
| ThreadLocal tenant bị giữ sau request | Không cleanup context | Dọn request context an toàn |
| Hibernate 5 code không compile trên 6/7 | `@ParamDef.type` API thay đổi | Dùng `type=String.class` theo version mới |

## 47. Sơ đồ lựa chọn cách lọc

~~~mermaid
flowchart TD
    A["Cần điều kiện lọc dữ liệu"] --> B{"Điều kiện cố định ở mapping?"}
    B -- "Có" --> C{"Là chính sách xóa mềm?"}
    C -- "Có" --> D["@SoftDelete nếu phù hợp"]
    C -- "Không" --> E["@SQLRestriction"]
    B -- "Không" --> F{"Thay đổi theo request/Session?"}
    F -- "Không" --> G["WHERE của query/repository"]
    F -- "Có" --> H{"Có nhiều query dùng cùng predicate?"}
    H -- "Không" --> G
    H -- "Có" --> I["@FilterDef + @Filter"]
    I --> J["enableFilter + setParameter ở đầu Session"]
    J --> K{"Có access-by-ID hoặc collection?"}
    K -- "Có" --> L["Xem applyToLoadByKey, collection mapping, L1"]
    K -- "Không" --> M["Kiểm tra SQL được sinh"]
    L --> M
    M --> N{"Là security boundary?"}
    N -- "Có" --> O["DB RLS/multi-tenancy + authorization + test"]
    N -- "Không" --> P["Kiểm tra performance và caching"]
~~~

## 48. Bài tập thực hành

**Bài 1 — Vai trò của `@FilterDef` và `@Filter`.** Nếu entity chỉ có `@FilterDef` mà không có `@Filter`, điều kiện có tự áp cho entity không?

**Đáp án:** Không. `@FilterDef` định nghĩa filter; entity/collection phải gắn filter bằng `@Filter` thích hợp.

**Bài 2 — Filter chưa bật.** Entity có `@Filter` nhưng Session không `enableFilter`. Query có bị lọc không?

**Đáp án:** Thông thường không, trừ khi definition có `autoEnabled=true`.

**Bài 3 — Tham số tenant.** Sử dụng API nào?

~~~java
session.enableFilter("tenantScope")
       .setParameter("tenantId", tenantId);
~~~

**Đáp án:** `Session.enableFilter` và runtime `org.hibernate.Filter.setParameter`. Giá trị được bind qua Hibernate.

**Bài 4 — Hai Session khác tenant.** Session A set tenant-a có tự ảnh hưởng Session B không?

**Đáp án:** Không. Filter state gắn với từng Session.

**Bài 5 — Filter không có tham số.** `notDeleted` có cần `setParameter` không?

**Đáp án:** Không nếu filter condition không có parameter và definition không khai báo parameter cần gán.

**Bài 6 — Nhiều filters.** Bật tenantScope và notDeleted có mặc định nghĩa OR không?

**Đáp án:** Không. Các predicates trên cùng query/mapping thường kết hợp như AND.

**Bài 7 — `setParameterList`.** Tại sao filter `status in (:statuses)` cần API này?

**Đáp án:** Để bind một danh sách các values vào IN-style predicate theo Hibernate contract.

**Bài 8 — Direct find.** Tại sao `find(Document.class, id)` có thể bỏ qua filter?

**Đáp án:** Direct loading theo primary key không áp dynamic filter mặc định, trừ khi cấu hình `applyToLoadByKey=true` trên FilterDef phiên bản hỗ trợ.

**Bài 9 — L1 cache.** Bật tenant filter sau khi entity được load có xóa entity khỏi Session?

**Đáp án:** Không. Persistence context vẫn có thể giữ managed instance.

**Bài 10 — To-one association.** Khi `applyToLoadByKey` làm target của FK bị lọc, điều gì có thể xảy ra?

**Đáp án:** Hibernate có thể ném `EntityFilterException`; phải thiết kế association visibility.

**Bài 11 — Collection.** Thêm `@Filter` trên Folder.documents có ý nghĩa gì?

**Đáp án:** Collection load có thể áp predicate cho các phần tử khi filter đang bật và collection chưa initialized.

**Bài 12 — Join table.** Cột `active` nằm trong bảng `document_tags`, nên đặt annotation nào?

**Đáp án:** `@FilterJoinTable` trên ManyToMany association.

**Bài 13 — Dynamic soft delete.** Chỉ có `@Filter(notDeleted)` thì `session.remove` có tự cập nhật deleted flag?

**Đáp án:** Không. Cần soft-delete DML mapping như `@SoftDelete` hoặc cơ chế ghi riêng.

**Bài 14 — AutoEnabled có tham số.** Dùng cơ chế nào để cung cấp tenantId?

**Đáp án:** `@ParamDef.resolver` với một `Supplier` được quản lý, hoặc set parameter theo API thích hợp. Phải fail closed nếu thiếu tenant context.

**Bài 15 — Native SQL.** Một câu `select * from documents` tự có tenant predicate nếu Session bật tenantScope?

**Đáp án:** Không được mặc định. Native SQL/JDBC cần guard riêng hoặc database policy.

**Bài 16 — Collection cache.** Vì sao không thể kết hợp tùy ý `@Filter` và collection `@Cache`?

**Đáp án:** Cached membership chỉ chứa subset từ một Session có thể bị dùng sai ở Session khác với filter parameter khác.

**Bài 17 — Bật filter muộn.** Collection Folder.documents đã initialized rồi mới enable notDeleted; collection Java có tự cắt bớt phần tử không?

**Đáp án:** Không. Filter ảnh hưởng các operations cần load dữ liệu về sau, không retroactively đổi collection state.

**Bài 18 — SQL fragment.** Vì sao `d.tenantId = :tenantId` không đúng cú pháp condition đáng tin cậy?

**Đáp án:** Filter condition là SQL với database column names, không phải HQL với entity property names.

**Bài 19 — Security.** Chỉ dùng `@Filter` đã đủ multi-tenant isolation chưa?

**Đáp án:** Chưa. Có các đường bypass và Session/cache state; cần authorization/multi-tenancy/RLS phù hợp.

**Bài 20 — Index.** Filter tenant/deleted hoạt động nhưng query chậm; nên sửa gì trước?

**Đáp án:** Đọc execution plan, xem index và row selectivity; không bỏ filter chỉ để query nhanh hơn.

## 49. Checklist trước khi triển khai

- Tên `@FilterDef` duy nhất và trùng `@Filter.name`.
- Mỗi mapping cần lọc có `@Filter` hoặc `@FilterJoinTable` thích hợp.
- Condition sử dụng **SQL column names**, không nhầm entity field names.
- ParamDef có đúng Java type và SQL mapping.
- Parameter values được bind qua `setParameter`/`setParameterList`.
- Enable filter ngay đầu Session, trước mọi query/collection load.
- Không chia sẻ Session giữa threads hoặc tenants.
- Không đổi tenant/filter giữa một persistence context đã nạp dữ liệu.
- Xác định có dùng `autoEnabled` và resolver hay không.
- Resolver fail closed nếu thiếu tenant/current context.
- Kiểm tra `applyToLoadByKey` cho direct find và to-one association.
- Không giả định native SQL hoặc bulk mutation tự chịu filter.
- Không dùng filter như soft-delete write policy.
- Không kết hợp filtered collection với second-level collection cache sai cách.
- Không để administrator disable filter chỉ theo flag client chưa authorize.
- Nếu dùng tenant filter như lớp bảo mật, có DB/authorization enforcement bổ sung.
- Kiểm tra query SQL và plan trên DB/dialect thực tế.
- Test tenant A/B, deleted/visible, temporal boundaries, collection, find và native access.
- Đánh giá effects lên query cache, L1 state và Hibernate mapping versions.
- Xem Hibernate 6.4+ `@SoftDelete` và `@SQLRestriction` khi dynamic filter không cần thiết.

## 50. Tổng kết

**`@FilterDef`, `@Filter` và `Session.enableFilter` cho phép khai báo một điều kiện SQL ở mapping nhưng quyết định bật/tắt và gán tham số theo Session đang chạy.** Đây là khả năng mạnh của Hibernate khi cùng một entity hoặc collection cần những góc nhìn khác nhau theo tenant, trạng thái hoặc thời gian hiệu lực.

Những điều phải nhớ:

1. **`@FilterDef` định nghĩa**, `@Filter` gắn vào entity/collection, **`enableFilter` kích hoạt** trong Session.
2. Dùng `@ParamDef(type=SomeClass.class)` và `setParameter` hoặc `setParameterList` để bind tham số.
3. Filter mặc định không bật; `autoEnabled=true` có thể tự bật nếu Hibernate version hỗ trợ.
4. Filter có tham số auto-enabled có thể dùng `@ParamDef.resolver` qua managed `Supplier`.
5. Multiple filters thường kết hợp bằng AND; muốn OR phải thể hiện rõ trong predicate.
6. Filter condition là **SQL fragment**; alias injection có thể được điều khiển bằng `{alias}` và `deduceAliasInjectionPoints=false`.
7. Direct `find` theo ID mặc định không chịu filter; `applyToLoadByKey` có thể đổi hành vi nhưng ảnh hưởng to-one associations và không sửa entity đã managed.
8. Collection filter và `@FilterJoinTable` tác động vào những phần khác nhau của mapping; collection đã load không tự refilter.
9. **Filter không tạo soft-delete UPDATE**; Hibernate 6.4+ `@SoftDelete` phù hợp hơn cho một chính sách xóa mềm cố định.
10. **Native SQL, JDBC và một số đường bulk mutation phải được kiểm soát riêng**; filter không phải database authorization rule.
11. Filtered collections không được cache tùy ý trong second-level collection cache, vì cache không lưu mọi biến thể theo tham số.
12. Session phải được scope đúng request/transaction; không chia sẻ giữa threads, không đổi tenant giữa một unit of work.
13. Với multi-tenancy bảo mật nghiêm ngặt, cần **RLS, Hibernate multi-tenancy hoặc authorization design phù hợp**, không chỉ một dynamic filter.
14. Quan sát SQL, caching và execution plan trên database thật để bảo đảm điều kiện được áp và hiệu năng chấp nhận được.

Dynamic filter hữu ích nhất khi ứng dụng chủ động kiểm soát **khi nào filter bật, Session nào nhận tham số, mapping nào áp dụng điều kiện và những đường truy cập nào nằm ngoài cơ chế đó**. Hiểu đúng giới hạn sẽ giúp tận dụng tính linh hoạt của Hibernate mà không tạo lỗ hổng dữ liệu.

## Tài liệu tham khảo

- [Hibernate ORM 7.2 User Guide — Filtering entities and associations](https://docs.hibernate.org/orm/7.2/userguide/html_single/)
- [Hibernate ORM 6.6 User Guide — @Filter, @FilterDef và collection filtering](https://docs.hibernate.org/orm/6.6/userguide/html_single/)
- [Hibernate ORM 7.2 Javadocs — @FilterDef](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/annotations/FilterDef.html)
- [Hibernate ORM 7.2 Javadocs — @Filter](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/annotations/Filter.html)
- [Hibernate ORM 7.2 Javadocs — Filter runtime API](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Filter.html)
- [Hibernate ORM 7.2 Javadocs — @ParamDef](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/annotations/ParamDef.html)
- [Hibernate ORM 7.2 Javadocs — @FilterJoinTable](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/annotations/FilterJoinTable.html)
- [Hibernate ORM 7.2 Introduction — Filters và các giới hạn](https://docs.hibernate.org/orm/7.2/introduction/html_single/)
- [Hibernate ORM 6.6 User Guide — Soft delete](https://docs.hibernate.org/orm/6.6/userguide/html_single/)
