# Chiều sắp xếp, thứ tự NULL và khác biệt giữa cơ sở dữ liệu

Spring Data JPA cho phép sắp xếp kết quả bằng Sort, Pageable, derived query hoặc ORDER BY trong JPQL. Ngoài việc chọn tăng dần (ASC) hay giảm dần (DESC), truy vấn còn phải xác định cách xử lý giá trị NULL. Đây là điểm dễ gây khác biệt giữa các hệ quản trị: cùng một câu ORDER BY có thể đưa NULL lên đầu ở database này nhưng xuống cuối ở database khác.

Bài học này giải thích chiều sắp xếp, thứ tự của nhiều tiêu chí, các tùy chọn null handling trong Spring Data, hành vi mặc định của một số database, cách quy định NULL FIRST/LAST tường minh bằng JPQL CASE, ảnh hưởng đến phân trang và cách nhận sort request an toàn từ API.

## 1. ASC và DESC có nghĩa gì?

ORDER BY quy định thứ tự hàng trong kết quả truy vấn:

- **ASC (ascending)**: tăng dần.
- **DESC (descending)**: giảm dần.

Với số, ASC đưa giá trị nhỏ lên trước và DESC đưa giá trị lớn lên trước:

~~~sql
SELECT id, total
FROM purchase_orders
ORDER BY total ASC;
~~~

~~~sql
SELECT id, total
FROM purchase_orders
ORDER BY total DESC;
~~~

Với ngày giờ, ASC thường đưa thời điểm cũ lên trước và DESC đưa thời điểm mới lên trước. Với chuỗi, thứ tự phụ thuộc collation của database, quy tắc so sánh ký tự, hoa thường và dấu.

Trong JPQL, dùng tên entity và thuộc tính Java:

~~~jpql
select o
from PurchaseOrder o
order by o.createdAt desc
~~~

Không dùng tên bảng hoặc tên cột SQL nếu đang viết JPQL. Nếu field Java là createdAt nhưng cột là created_at, JPQL vẫn dùng o.createdAt.

## 2. Sắp xếp nhiều tiêu chí

Một truy vấn có thể sắp xếp theo nhiều biểu thức:

~~~jpql
select o
from PurchaseOrder o
order by o.status asc, o.createdAt desc, o.id desc
~~~

Database áp dụng các tiêu chí theo thứ tự từ trái sang phải:

1. Sắp xếp status tăng dần.
2. Nếu status bằng nhau, sắp xếp createdAt giảm dần.
3. Nếu cả status và createdAt đều bằng nhau, sắp xếp id giảm dần.

Tiêu chí cuối thường nên là khóa duy nhất để tạo thứ tự xác định. Nếu chỉ sắp xếp theo createdAt, nhiều bản ghi có cùng timestamp có thể đổi vị trí giữa các lần chạy.

Thứ tự ổn định đặc biệt quan trọng khi phân trang, xuất báo cáo, xử lý batch hoặc tiếp tục đọc dữ liệu từ trang trước.

## 3. Sort trong Spring Data JPA

Repository có thể nhận Sort để quyết định thứ tự lúc gọi:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(
        OrderStatus status,
        Sort sort
    );
}
~~~

Tạo Sort với một tiêu chí:

~~~java
Sort ascending = Sort.by(
    Sort.Direction.ASC,
    "createdAt"
);

Sort descending = Sort.by(
    Sort.Direction.DESC,
    "createdAt"
);
~~~

Tạo Sort nhiều tiêu chí:

~~~java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
~~~

Hoặc cấu hình từng Order:

~~~java
Sort sort = Sort.by(
    new Sort.Order(Sort.Direction.DESC, "createdAt"),
    new Sort.Order(Sort.Direction.ASC, "reference")
);
~~~

Tên thuộc tính trong Sort là property Java của entity. Không dùng tên cột SQL, trừ khi đang làm việc với native query và cột/alias được parser hỗ trợ.

## 4. Chiều sắp xếp độc lập với thứ tự NULL

ASC và DESC xác định hướng so sánh giữa các giá trị có thể so sánh với nhau. Nhưng NULL không phải giá trị thông thường. SQL xem NULL là trạng thái không có hoặc chưa biết giá trị, nên thứ tự của nó cần quy tắc riêng.

Ví dụ dữ liệu:

| id | dueAt |
|---:|---|
| 1 | 2026-03-01 |
| 2 | NULL |
| 3 | 2026-01-15 |
| 4 | NULL |
| 5 | 2026-02-10 |

Có hai yêu cầu độc lập:

- Sắp xếp ngày cũ trước hay mới trước?
- Giá trị NULL đứng trước hay đứng sau các ngày có giá trị?

Ví dụ:
- Ngày tăng dần, NULL lên đầu.
- Ngày tăng dần, NULL xuống cuối.
- Ngày giảm dần, NULL lên đầu.
- Ngày giảm dần, NULL xuống cuối.

Không nên giả định DESC luôn đưa NULL lên đầu hoặc ASC luôn đưa NULL xuống cuối. Mặc định phụ thuộc database.

## 5. Thứ tự NULL mặc định khác nhau giữa database

Nếu không chỉ định quy tắc NULL, các database phổ biến có mặc định sau:

| Database | ASC mặc định | DESC mặc định |
|---|---|---|
| PostgreSQL | NULL ở cuối | NULL ở đầu |
| Oracle Database | NULL ở cuối | NULL ở đầu |
| MySQL | NULL ở đầu | NULL ở cuối |
| SQL Server | NULL ở đầu | NULL ở cuối |
| SQLite | NULL ở đầu | NULL ở cuối |

Bảng này mô tả hành vi mặc định phổ biến của các hệ quản trị nêu trên. Hãy xác minh theo phiên bản và cú pháp cụ thể của database dự án, nhất là khi query chạy trên nhiều hệ quản trị hoặc có biểu thức sort phức tạp.

Hệ quả là cùng câu:

~~~sql
ORDER BY due_at ASC
~~~

có thể trả về thứ tự khác nhau giữa PostgreSQL và MySQL khi cột due_at có NULL.

Nếu ứng dụng chuyển database hoặc chạy test trên H2 nhưng production dùng database khác, test có thể không phát hiện khác biệt thứ tự NULL. Những yêu cầu về vị trí NULL cần được ghi rõ trong query và kiểm thử trên database mục tiêu.

## 6. NullHandling trong Sort.Order

Spring Data cung cấp các gợi ý về vị trí NULL qua Sort.Order:

~~~java
Sort nullsFirst = Sort.by(
    Sort.Order.asc("dueAt").nullsFirst()
);

Sort nullsLast = Sort.by(
    Sort.Order.asc("dueAt").nullsLast()
);

Sort nativeNullOrder = Sort.by(
    Sort.Order.asc("dueAt").nullsNative()
);
~~~

Các phương thức:

- **nullsFirst()**: yêu cầu/gợi ý NULL đứng trước.
- **nullsLast()**: yêu cầu/gợi ý NULL đứng sau.
- **nullsNative()**: để database hoặc datastore áp dụng hành vi mặc định.

Trong Spring Data, đây là metadata/hint về null handling của Order. JPA provider hoặc datastore có thể không thực hiện mọi hint theo cùng một cách. Không nên xem nullsFirst()/nullsLast() là bảo đảm portable tuyệt đối trên mọi provider và database.

Ví dụ kết hợp nhiều tiêu chí:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("dueAt").nullsLast(),
    Sort.Order.desc("priority"),
    Sort.Order.asc("id")
);
~~~

Ý định là dueAt tăng dần, NULL xuống cuối; trong các hàng có cùng dueAt thì priority giảm dần; cuối cùng id tăng dần.

Hãy kiểm tra SQL được sinh và kết quả trên hệ quản trị thực tế. Nếu vị trí NULL là yêu cầu nghiệp vụ bắt buộc phải giống nhau ở mọi database, hãy biểu diễn nó tường minh trong query.

## 7. NULLS FIRST và NULLS LAST trong SQL

Một số database hỗ trợ cú pháp đặt vị trí NULL trực tiếp trong ORDER BY:

~~~sql
SELECT id, due_at
FROM tasks
ORDER BY due_at ASC NULLS LAST;
~~~

Hoặc:

~~~sql
SELECT id, due_at
FROM tasks
ORDER BY due_at DESC NULLS FIRST;
~~~

Cú pháp NULLS FIRST/LAST được hỗ trợ bởi PostgreSQL và Oracle; SQLite cũng hỗ trợ cú pháp này ở các phiên bản hiện đại. MySQL và SQL Server không dùng cùng cú pháp này trong ORDER BY; cần dùng biểu thức thay thế như CASE.

Không sao chép cú pháp native SQL của một database vào ứng dụng chạy trên hệ quản trị khác mà không kiểm tra. JPQL chuẩn cũng không nên phụ thuộc cú pháp NULLS FIRST/LAST đặc thù của một dialect. Để có cách diễn đạt portable hơn, dùng CASE trong JPQL.

## 8. Quy định NULL tường minh bằng CASE trong JPQL

Có thể tạo một khóa sắp xếp phụ để phân loại NULL và non-NULL.

Ví dụ ngày tăng dần, NULL xuống cuối:

~~~java
@Query("""
    select t
    from Task t
    order by
        case when t.dueAt is null then 1 else 0 end asc,
        t.dueAt asc,
        t.id asc
    """)
List<Task> findAllByDueDateAscendingNullsLast();
~~~

Giải thích:

- Với dueAt có giá trị, CASE trả 0.
- Với dueAt là NULL, CASE trả 1.
- Sắp xếp khóa CASE tăng dần nên nhóm có ngày (0) đứng trước nhóm NULL (1).
- dueAt ASC sắp xếp ngày cũ trước ngày mới trong nhóm có giá trị.
- id ASC tạo thứ tự phụ ổn định.

Ngày tăng dần, NULL lên đầu:

~~~jpql
order by
    case when t.dueAt is null then 0 else 1 end asc,
    t.dueAt asc,
    t.id asc
~~~

Ngày giảm dần, NULL xuống cuối:

~~~jpql
order by
    case when t.dueAt is null then 1 else 0 end asc,
    t.dueAt desc,
    t.id desc
~~~

Ngày giảm dần, NULL lên đầu:

~~~jpql
order by
    case when t.dueAt is null then 0 else 1 end asc,
    t.dueAt desc,
    t.id desc
~~~

Quy tắc CASE luôn được sắp xếp ASC để điều khiển nhóm NULL/non-NULL. Chiều của thuộc tính ngày được quyết định riêng bằng ASC hoặc DESC.

CASE trong JPQL là cách biểu diễn rõ ràng, tránh phụ thuộc mặc định NULL của database. Vẫn cần chạy integration test với JPA provider và database đang dùng.

## 9. Ví dụ entity và repository

Entity Task có dueAt nullable:

~~~java
package example.domain;

import jakarta.persistence.*;
import java.time.LocalDate;

@Entity
@Table(name = "tasks")
public class Task {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(name = "due_at")
    private LocalDate dueAt;

    @Column(nullable = false)
    private int priority;

    protected Task() {
    }

    public Task(String title, LocalDate dueAt, int priority) {
        this.title = title;
        this.dueAt = dueAt;
        this.priority = priority;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public LocalDate getDueAt() {
        return dueAt;
    }

    public int getPriority() {
        return priority;
    }
}
~~~

Repository có thể cung cấp các cách sắp xếp khác nhau:

~~~java
package example.repository;

import example.domain.Task;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface TaskRepository extends JpaRepository<Task, Long> {

    @Query("""
        select t
        from Task t
        order by
            case when t.dueAt is null then 1 else 0 end asc,
            t.dueAt asc,
            t.id asc
        """)
    List<Task> findDueDateAscendingNullsLast();

    @Query("""
        select t
        from Task t
        order by
            case when t.dueAt is null then 0 else 1 end asc,
            t.dueAt desc,
            t.id desc
        """)
    List<Task> findDueDateDescendingNullsFirst();

    List<Task> findAll(Sort sort);
}
~~~

Các method JPQL cố định thể hiện rõ thứ tự NULL mà không phụ thuộc mặc định của database. Method findAll(Sort) cho phép sắp xếp động theo property path; hãy dùng nó khi quy tắc NULL của datastore phù hợp hoặc đã được kiểm thử.

## 10. Khi nào dùng Sort hint, khi nào dùng CASE?

| Yêu cầu | Cách phù hợp |
|---|---|
| Chấp nhận mặc định database | Sort.Order.nullsNative() hoặc Sort thường |
| Muốn khai báo gợi ý NULL first/last qua repository | Sort.Order.nullsFirst()/nullsLast(), sau đó kiểm thử provider |
| Bắt buộc NULL có cùng vị trí trên nhiều database | JPQL CASE hoặc Criteria API CASE |
| Query native SQL chỉ chạy trên một database đã xác định | Cú pháp NULLS FIRST/LAST hoặc CASE theo dialect |
| Cần hướng sắp xếp động và quy tắc NULL cố định | Criteria API/custom repository hoặc các query được whitelist |
| Cần sắp xếp phức tạp theo nhiều biểu thức | JPQL/Criteria/native query được kiểm soát |

Sort tiện khi thuộc tính là property path đơn giản. CASE hữu ích khi quy tắc sắp xếp cần biểu thức bổ sung, ví dụ NULL luôn ở cuối bất kể ngày tăng hay giảm.

Không nên dùng JpaSort.unsafe với chuỗi sort tùy ý từ người dùng để ghép CASE hoặc SQL. Nếu cần biểu thức động, hãy xây dựng bằng Criteria API hoặc chọn từ những query/biểu thức được định nghĩa sẵn.

## 11. Sắp xếp động cả chiều và vị trí NULL

Một màn hình có thể cho người dùng chọn dueAt ASC hoặc DESC và NULL FIRST hoặc LAST.

Nếu chỉ dùng Sort.Order, có thể truyền direction và null handling:

~~~java
Sort.Order order = new Sort.Order(direction, "dueAt")
    .nullsLast();
~~~

Cách này thể hiện ý định nhưng vẫn chịu giới hạn hint của provider/datastore.

Nếu phải bảo đảm chính xác cùng quy tắc trên nhiều database, custom repository có thể dùng CriteriaBuilder tạo CASE expression. Ví dụ:

~~~java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<Task> query = cb.createQuery(Task.class);
Root<Task> task = query.from(Task.class);

Expression<Integer> nullRank = cb.<Integer>selectCase()
    .when(cb.isNull(task.get("dueAt")), 1)
    .otherwise(0);

List<jakarta.persistence.criteria.Order> orders =
    new ArrayList<>();

orders.add(cb.asc(nullRank));

if (direction == Sort.Direction.ASC) {
    orders.add(cb.asc(task.get("dueAt")));
    orders.add(cb.asc(task.get("id")));
} else {
    orders.add(cb.desc(task.get("dueAt")));
    orders.add(cb.desc(task.get("id")));
}

query.select(task).orderBy(orders);
~~~

Ví dụ trên cố định NULL xuống cuối và thay đổi chiều của dueAt/id theo direction. Để hỗ trợ NULL FIRST, đổi giá trị nullRank thành 0 cho NULL và 1 cho non-NULL. Trong custom repository thật, cần thêm predicate, TypedQuery, tham số, pagination và whitelist sort property phù hợp.

## 12. Phân biệt NULL với chuỗi rỗng

NULL không giống chuỗi rỗng:

- NULL biểu diễn không có hoặc chưa biết giá trị.
- Chuỗi rỗng là một giá trị String có độ dài bằng 0 ở các database phân biệt hai trạng thái này.

Một số hệ quản trị có quy tắc riêng. Oracle Database xử lý chuỗi ký tự có độ dài bằng 0 như NULL trong nhiều ngữ cảnh SQL. PostgreSQL và MySQL phân biệt chuỗi rỗng với NULL.

Vì vậy, nếu cột là VARCHAR và ứng dụng lưu cả NULL lẫn chuỗi rỗng, thứ tự sort có thể khác nhau. Hãy quyết định domain có coi hai trạng thái là giống nhau hay không và chuẩn hóa dữ liệu ở tầng phù hợp.

Không dùng IS NULL để tìm chuỗi rỗng trong database phân biệt hai trạng thái. Muốn tìm chuỗi rỗng, dùng điều kiện so sánh với chuỗi rỗng theo semantics của database.

## 13. Collation, hoa thường và dấu tiếng Việt

Thứ tự chuỗi không chỉ phụ thuộc ASC/DESC. Database còn dùng collation để so sánh ký tự:

- Có phân biệt hoa thường hay không.
- Có phân biệt dấu hay không.
- Thứ tự chữ cái theo locale.
- Cách xử lý ký tự Unicode và chuẩn hóa.

Ví dụ tên "An", "Ánh", "an" có thể được sắp xếp khác nhau giữa các collation. Spring Data Sort.Order.ignoreCase() có thể yêu cầu so sánh không phân biệt hoa thường, nhưng cách dịch và hiệu quả phụ thuộc provider/database.

Nếu ứng dụng cần thứ tự tiếng Việt nhất quán, hãy cấu hình collation phù hợp ở database hoặc biểu thức sort đã chuẩn hóa. Kiểm thử với dữ liệu có dấu, chữ hoa/thường và ký tự Unicode thực tế. Đừng giả định Java String.compareTo() và database ORDER BY có cùng quy tắc.

## 14. NULL và phân trang

Phân trang cần thứ tự ổn định. Nếu sort key có NULL, query phải có quy tắc vị trí NULL rõ ràng khi kết quả cần nhất quán giữa các lần gọi.

Ví dụ:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("dueAt").nullsLast(),
    Sort.Order.asc("id")
);

Pageable pageable = PageRequest.of(0, 20, sort);
Page<Task> page = taskRepository.findAll(pageable);
~~~

Nếu provider/database không thực hiện null handling hint như mong muốn, kết quả phân trang có thể khác. Khi cần tính portable, dùng query có CASE hoặc custom Criteria query.

Offset pagination cũng có thể dịch chuyển khi dữ liệu mới được thêm/xóa giữa hai lần lấy trang. Tie-breaker duy nhất giúp thứ tự xác định tại mỗi lần truy vấn, nhưng không tự tạo snapshot nhất quán qua nhiều request.

Với keyset scrolling, các trường sắp xếp tham gia điều kiện tiếp tục đọc. NULL làm điều kiện so sánh phức tạp hơn; nhiều cơ chế keyset yêu cầu sort key không null hoặc có giới hạn riêng theo phiên bản. Ưu tiên khóa sắp xếp không null nếu cần keyset, hoặc xác minh hỗ trợ của phiên bản Spring Data/provider trước khi thiết kế.

## 15. Index và hiệu năng khi sắp xếp

ORDER BY có thể dùng index nếu cấu trúc index và query phù hợp. Ví dụ:

~~~sql
CREATE INDEX idx_tasks_due_at_id
    ON tasks(due_at, id);
~~~

Index trên due_at và id có thể hỗ trợ truy vấn sắp xếp theo hai cột, tùy database, chiều index, điều kiện lọc và execution plan.

Khi dùng CASE để sắp xếp theo nhóm NULL, database có thể cần tính expression cho nhiều hàng. Một index thông thường trên due_at không phải lúc nào cũng đáp ứng toàn bộ ORDER BY CASE, due_at, id.

Các lựa chọn:

- Kiểm tra EXPLAIN/EXPLAIN ANALYZE.
- Tạo index theo điều kiện lọc và thứ tự thực tế.
- Cân nhắc expression/function index nếu database hỗ trợ và query có thể tận dụng.
- Dùng cột normalized hoặc sort key được duy trì nếu nghiệp vụ cần và chi phí cập nhật chấp nhận được.
- Tránh sắp xếp trên tập dữ liệu quá lớn trước khi giới hạn nếu có cách lọc hiệu quả hơn.

Không tạo index chỉ dựa trên tên cột. Đo query với dữ liệu đại diện và xem execution plan của database production.

## 16. Nhận sort request từ API một cách an toàn

Không cho client gửi tên thuộc tính bất kỳ rồi chuyển thẳng vào Sort. Hãy định nghĩa whitelist:

~~~java
private static final Map<String, String> SORT_FIELDS = Map.of(
    "due-date", "dueAt",
    "priority", "priority",
    "title", "title"
);

public Sort buildSort(String requestedField, String requestedDirection) {
    String property = SORT_FIELDS.get(requestedField);

    if (property == null) {
        throw new IllegalArgumentException("Unsupported sort field");
    }

    Sort.Direction direction = switch (
        requestedDirection == null
            ? ""
            : requestedDirection.toLowerCase(Locale.ROOT)
    ) {
        case "asc" -> Sort.Direction.ASC;
        case "desc" -> Sort.Direction.DESC;
        default -> throw new IllegalArgumentException(
            "Direction must be asc or desc"
        );
    };

    return Sort.by(
        new Sort.Order(direction, property).nullsLast()
    );
}
~~~

Ví dụ trên:

- Chỉ cho phép ba sort key công khai.
- Ánh xạ chúng sang property Java.
- Chỉ nhận direction asc hoặc desc.
- Áp dụng nullsLast như một hint.

Nếu vị trí NULL bắt buộc phải nhất quán giữa các database, hãy định tuyến đến query CASE hoặc Criteria API đã được kiểm soát thay vì dựa vào hint. Cũng cần giới hạn số sort criteria và page size.

## 17. Kiểm thử thứ tự NULL và khác biệt database

Một bộ integration test nên có dữ liệu gồm:

- Một hàng có dueAt cũ.
- Một hàng có dueAt mới.
- Ít nhất hai hàng có dueAt NULL.
- Hai hàng có cùng dueAt nhưng ID khác nhau.
- Chuỗi có chữ hoa/thường và tiếng Việt có dấu nếu sort text là yêu cầu.

Kiểm tra:

1. ASC và DESC sắp xếp các giá trị non-null đúng chiều.
2. nullsFirst/nullsLast có hành vi thực tế đúng với provider/database.
3. CASE expression đưa NULL đúng vị trí.
4. Tie-breaker tạo thứ tự xác định khi giá trị chính trùng nhau.
5. Page có thứ tự nhất quán giữa các trang.
6. Native SQL dùng cú pháp đúng với database mục tiêu.
7. Chuỗi rỗng và NULL được phân biệt theo database.
8. Collation cho kết quả phù hợp với yêu cầu ngôn ngữ.

Nếu production dùng PostgreSQL, MySQL, Oracle hoặc SQL Server, nên chạy integration test trên đúng hệ quản trị đó. H2 có thể hữu ích cho test nhanh nhưng không chứng minh mặc định NULL và collation giống database production.

## 18. Lỗi thường gặp và cách khắc phục

**1. ASC/DESC cho kết quả NULL ngược mong đợi**

Kiểm tra mặc định NULL của database. Dùng Sort.Order.nullsFirst/nullsLast như hint hoặc CASE nếu cần quy tắc rõ ràng.

**2. Cùng query cho thứ tự khác nhau ở local và production**

Kiểm tra database engine, phiên bản, collation và NULL ordering. Test trên cùng database mục tiêu.

**3. Sort không tìm thấy thuộc tính**

Dùng tên property Java của entity thay vì tên cột SQL. Với query projection, kiểm tra alias.

**4. nullsLast() không tạo ra kết quả mong đợi**

Đây là hint và có thể phụ thuộc provider/datastore. Xem SQL được sinh; nếu cần portable behavior, dùng CASE trong JPQL/Criteria.

**5. Phân trang lặp hoặc bỏ sót hàng**

Thêm tiêu chí sắp xếp duy nhất làm tie-breaker. Xem xét dữ liệu thay đổi giữa các lần lấy trang và dùng keyset khi phù hợp.

**6. Sắp xếp chuỗi tiếng Việt không đúng thứ tự mong muốn**

Kiểm tra collation và cách xử lý hoa thường/dấu. ignoreCase không tự giải quyết mọi quy tắc locale.

**7. Dùng NULL thay cho chuỗi rỗng**

Kiểm tra semantics của database. Oracle có quy tắc riêng với chuỗi rỗng; các database khác có thể phân biệt rõ.

**8. Query CASE chậm**

Xem execution plan và index. CASE có thể làm database khó tận dụng index sort hiện có; cân nhắc expression index hoặc thiết kế sort key phù hợp.

**9. Đưa raw sort field từ client vào query**

Whitelist sort key và direction. Không dùng JpaSort.unsafe với đầu vào chưa kiểm soát.

## 19. Quy trình thiết kế thứ tự kết quả

Khi xây dựng repository query có sắp xếp, hãy đi theo trình tự:

1. Xác định thuộc tính cần sắp xếp và kiểu dữ liệu của nó.
2. Chọn ASC hoặc DESC theo yêu cầu nghiệp vụ.
3. Xác định giá trị NULL phải đứng đầu hay cuối.
4. Nếu chấp nhận mặc định database, dùng native behavior và ghi rõ phụ thuộc.
5. Nếu dùng Sort.Order.nullsFirst/nullsLast, kiểm thử hint trên provider thực tế.
6. Nếu cần cùng kết quả trên nhiều database, dùng CASE hoặc Criteria API.
7. Thêm khóa duy nhất làm tie-breaker.
8. Kiểm tra collation nếu sort trên chuỗi.
9. Whitelist sort key và direction từ API.
10. Kiểm tra phân trang, keyset và count query.
11. Xem execution plan và index trên database mục tiêu.
12. Viết integration test có cả NULL, giá trị trùng và dữ liệu thực tế.

## 20. Checklist tự đánh giá

- [ ] Tôi giải thích được ASC và DESC.
- [ ] Tôi biết sắp xếp nhiều tiêu chí theo thứ tự ưu tiên.
- [ ] Tôi hiểu NULL không phải giá trị thông thường trong phép sắp xếp SQL.
- [ ] Tôi biết mặc định NULL khác nhau giữa PostgreSQL, Oracle, MySQL, SQL Server và SQLite.
- [ ] Tôi biết Sort.Order.nullsFirst(), nullsLast() và nullsNative().
- [ ] Tôi hiểu null handling trong Sort là hint và cần kiểm thử provider.
- [ ] Tôi biết dùng CASE trong JPQL để đặt NULL lên đầu hoặc xuống cuối.
- [ ] Tôi biết phân biệt NULL với chuỗi rỗng.
- [ ] Tôi hiểu collation ảnh hưởng thứ tự chuỗi và tiếng Việt.
- [ ] Tôi thêm tie-breaker duy nhất để tạo thứ tự ổn định.
- [ ] Tôi hiểu tác động của NULL sort key với pagination/keyset.
- [ ] Tôi biết whitelist sort key và direction từ API.
- [ ] Tôi kiểm tra index và execution plan khi dùng biểu thức CASE.
- [ ] Tôi có integration test trên database mục tiêu.

## 21. Câu hỏi ôn tập

**1. ASC và DESC khác nhau thế nào?**

ASC sắp xếp tăng dần; DESC sắp xếp giảm dần. Với ngày giờ, ASC thường là cũ đến mới, DESC là mới đến cũ.

**2. Vì sao không thể suy ra vị trí NULL chỉ từ ASC/DESC?**

Vì NULL có quy tắc sắp xếp riêng và mặc định khác nhau giữa các database. Cần dùng native null ordering, Sort hint hoặc biểu thức CASE.

**3. Sort.Order.nullsLast() có bảo đảm giống nhau trên mọi database không?**

Không tuyệt đối. Đây là hint cho datastore/provider. Hãy kiểm thử và dùng CASE/Criteria khi cần quy tắc portable.

**4. Làm sao đưa NULL xuống cuối khi ngày sắp xếp tăng dần?**

Dùng CASE để gán 0 cho ngày có giá trị và 1 cho NULL, sắp xếp CASE ASC rồi sắp xếp ngày ASC và ID ASC.

**5. Làm sao đưa NULL xuống cuối khi ngày sắp xếp giảm dần?**

Giữ CASE null-rank tăng dần với NULL là 1, sau đó sắp xếp ngày DESC và thêm khóa duy nhất làm tie-breaker.

**6. Vì sao cần tie-breaker khi phân trang?**

Nhiều hàng có thể cùng giá trị sort chính. Khóa duy nhất tạo thứ tự xác định để các trang ít bị thay đổi vị trí ngoài dự kiến.

**7. Collation ảnh hưởng gì đến Sort?**

Collation quyết định cách database so sánh chuỗi, bao gồm hoa thường, dấu và locale. Vì vậy kết quả sort text có thể khác giữa database.

**8. Khi nào nên dùng Criteria API thay cho Sort đơn giản?**

Khi cần sort động theo biểu thức CASE, kiểm soát NULL portable, nhiều điều kiện hoặc whitelist biểu thức mà Sort property path không thể diễn đạt.

Khi tách rõ chiều ASC/DESC, vị trí NULL và quy tắc so sánh chuỗi, ứng dụng có thể tạo kết quả nhất quán hơn giữa các database, đặc biệt khi kết hợp Sort với phân trang.

## Tài liệu tham khảo

- [Spring Data Commons — Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [PostgreSQL — Sorting Rows](https://www.postgresql.org/docs/current/queries-order.html)
- [MySQL — Sorting Rows](https://dev.mysql.com/doc/refman/8.4/en/sorting-rows.html)
- [Oracle Database — Sorting Query Results](https://docs.oracle.com/en/database/oracle/oracle-database/23/sqlrf/Sorting-Query-Results.html)
- [SQLite — SELECT and ORDER BY](https://www.sqlite.org/lang_select.html)
