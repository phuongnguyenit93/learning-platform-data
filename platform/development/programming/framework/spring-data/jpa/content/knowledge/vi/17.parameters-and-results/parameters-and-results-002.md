# Biểu thức giá trị trong @Query và biến entityName của Spring Data JPA

Spring Data JPA cho phép dùng **SpEL (Spring Expression Language)** bên trong `@Query` để tham chiếu tham số phương thức, truy cập thuộc tính của object đầu vào và dùng một số biến do Spring Data cung cấp. Một biến đặc biệt là `#{#entityName}`, giúp truy vấn JPQL trong repository tổng quát tham chiếu đúng entity mà repository cụ thể quản lý.

Cần phân biệt hai dạng biểu thức:

- **Template expression** như `#{#entityName}` được thay thế vào chuỗi JPQL để xác định tên entity.
- **Value expression** như `:#{#filter.status}` hoặc `?#{[0]}` được đánh giá thành giá trị và bind vào vị trí tham số của query.

SpEL không phải cơ chế để nối tùy ý tên bảng, tên cột hoặc mảnh SQL do người dùng gửi lên. Dùng nó để biểu đạt giá trị và metadata entity một cách rõ ràng, an toàn.

Tài liệu sử dụng Spring Data JPA với Jakarta Persistence trong Spring Boot 3 trở lên. Các ví dụ là thành phần repository/service cần project Spring đã cấu hình JPA, entity và database; chúng không phải chương trình độc lập chạy bằng `javac`.

## 1. JPQL trong @Query và entity name

JPQL truy vấn entity name và thuộc tính Java, không truy vấn trực tiếp tên bảng/cột vật lý.

Ví dụ:

```java
@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {
    @Id
    private Long id;

    private String status;
}
```

Tên entity mặc định là tên class `PurchaseOrder`. Query JPQL:

```java
@Query("select p from PurchaseOrder p where p.status = :status")
List<PurchaseOrder> findByStatus(@Param("status") String status);
```

SQL được provider sinh ra sẽ sử dụng bảng `purchase_order` theo mapping, nhưng JPQL dùng `PurchaseOrder`.

Có thể tùy chỉnh entity name:

```java
@Entity(name = "Purchase")
@Table(name = "purchase_order")
public class PurchaseOrder {
    // fields
}
```

Khi đó JPQL dùng `Purchase`:

```jpql
select p from Purchase p
```

`@Entity(name = ...)` định nghĩa entity name trong persistence model. `@Table(name = ...)` định nghĩa tên bảng vật lý. Hai giá trị này phục vụ hai tầng khác nhau.

## 2. Biến #{#entityName} là gì?

Spring Data JPA cung cấp biến SpEL `entityName` trong các biểu thức của query repository. Cú pháp dùng trong chuỗi `@Query` là:

```java
@Query("select e from #{#entityName} e")
List<T> findAllEntities();
```

Spring Data thay `#{#entityName}` bằng entity name của domain type mà repository đang quản lý.

Quy tắc xác định entity name:

1. Nếu entity khai báo `@Entity(name = "SomeName")`, dùng `SomeName`.
2. Nếu `@Entity` không chỉ định name, dùng tên đơn giản của class entity.
3. Đây là entity name trong JPQL, không phải tên bảng trong `@Table`.

Ví dụ:

```java
@Entity(name = "Purchase")
@Table(name = "purchase_order")
public class PurchaseOrder {
    @Id
    private Long id;
}
```

Query:

```java
@Query("select p from #{#entityName} p")
List<PurchaseOrder> findAllDynamicEntityName();
```

Khi repository quản lý PurchaseOrder, biểu thức được phân giải thành JPQL tương đương:

```jpql
select p from Purchase p
```

Không cần hard-code tên class hoặc entity name trong một repository generic.

## 3. Vì sao entityName hữu ích với generic repository?

Giả sử nhiều entity có chung thuộc tính `status`. Ta muốn viết một query dùng lại cho nhiều repository mà không phải lặp tên entity.

Có thể tạo mapped superclass:

```java
@MappedSuperclass
public abstract class AuditedRecord {
    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private RecordStatus status;

    public RecordStatus getStatus() {
        return status;
    }

    public void setStatus(RecordStatus status) {
        this.status = status;
    }
}
```

Các entity kế thừa:

```java
@Entity
public class PurchaseOrder extends AuditedRecord {
    @Id
    @GeneratedValue
    private Long id;
}

@Entity
public class Shipment extends AuditedRecord {
    @Id
    @GeneratedValue
    private Long id;
}
```

Định nghĩa repository cơ sở:

```java
@NoRepositoryBean
public interface StatusRepository<T extends AuditedRecord, ID>
        extends JpaRepository<T, ID> {

    @Query("""
        select e
        from #{#entityName} e
        where e.status = :status
        """)
    List<T> findAllByStatus(
        @Param("status") RecordStatus status
    );
}
```

Repository cụ thể:

```java
public interface PurchaseOrderRepository
        extends StatusRepository<PurchaseOrder, Long> {
}

public interface ShipmentRepository
        extends StatusRepository<Shipment, Long> {
}
```

Khi Spring Data tạo PurchaseOrderRepository, `#{#entityName}` được phân giải thành entity name của PurchaseOrder. Với ShipmentRepository, nó được phân giải thành entity name của Shipment.

`@NoRepositoryBean` đánh dấu interface generic là repository cơ sở, không tạo bean repository trực tiếp cho kiểu chưa xác định. Các repository cụ thể kế thừa nó sẽ được Spring Data tạo bean.

Điều kiện quan trọng: thuộc tính `status` phải tồn tại trong mô hình persistence của mọi entity dùng repository cơ sở. Mapped superclass là cách phổ biến để chia sẻ mapping thuộc tính này. Nếu một entity không có thuộc tính đó, query sẽ không hợp lệ khi được tạo/thực thi.

## 4. entityName không phải tên bảng hoặc tên cột

Đây là nhầm lẫn phổ biến nhất.

| Khai báo | Mục đích | Ví dụ |
|---|---|---|
| `@Entity(name = "Purchase")` | Entity name dùng trong JPQL | `from Purchase p` |
| `@Table(name = "purchase_order")` | Tên bảng vật lý | SQL `from purchase_order` |
| `@Column(name = "order_status")` | Tên cột vật lý | SQL `p.order_status` |
| `#{#entityName}` | Chèn entity name vào JPQL template | `from #{#entityName} p` |

Không dùng `#{#entityName}` để mong nhận được tên bảng `purchase_order`. Nếu viết native SQL, cần dùng tên bảng/cột vật lý phù hợp schema.

Ví dụ đúng với JPQL:

```java
@Query("select p from #{#entityName} p where p.status = :status")
List<T> findByStatus(@Param("status") String status);
```

Ví dụ native SQL cần tên bảng thật:

```java
@Query(
    value = "select * from purchase_order where order_status = ?1",
    nativeQuery = true
)
List<PurchaseOrder> findByPhysicalStatus(String status);
```

Biến `entityName` không được thiết kế để thay thế tên bảng trong native query. Không dựa vào nó để tạo SQL table identifier động.

## 5. SpEL value expression trong @Query

Ngoài template entity name, Spring Data JPA hỗ trợ SpEL expression để lấy giá trị tham số.

Named expression:

```java
@Query("""
    select u
    from User u
    where u.firstname = :#{#firstName}
    """)
List<User> findByFirstNameExpression(
    @Param("firstName") String firstName
);
```

`:#{#firstName}` được đánh giá từ tham số phương thức có tên `firstName`, sau đó giá trị được bind vào query parameter.

So sánh với named parameter thông thường:

```java
@Query("""
    select u
    from User u
    where u.firstname = :firstName
    """)
List<User> findByFirstName(
    @Param("firstName") String firstName
);
```

Nếu không cần biểu thức, cú pháp `:firstName` thường đơn giản hơn. SpEL hữu ích khi cần truy cập thuộc tính lồng nhau, tính giá trị từ tham số hoặc dùng biến query đặc biệt.

## 6. Truy cập tham số theo tên và theo vị trí

### 6.1. Named parameter expression

Dùng `@Param` để đặt tên rõ ràng:

```java
@Query("""
    select p
    from Product p
    where p.category = :#{#category}
      and p.price >= :#{#minimumPrice}
    """)
List<Product> search(
    @Param("category") String category,
    @Param("minimumPrice") BigDecimal minimumPrice
);
```

Cách này dễ đọc khi phương thức có nhiều tham số. Tên trong SpEL phải khớp tên được khai báo bằng `@Param`.

Nếu dựa vào tên tham số Java mà không khai báo `@Param`, cần bảo đảm quá trình compile giữ lại parameter name (ví dụ compiler option `-parameters`) và Spring Data phiên bản đang dùng có thể đọc tên đó. Để tránh phụ thuộc cấu hình build, `@Param` là lựa chọn rõ ràng.

### 6.2. Positional parameter expression

Có thể truy cập đối số theo index, bắt đầu từ 0:

```java
@Query("""
    select u
    from User u
    where u.firstname = ?#{[0]}
      and u.lastname = ?#{[1]}
    """)
List<User> findByNames(String firstName, String lastName);
```

- `[0]` là tham số đầu tiên.
- `[1]` là tham số thứ hai.

Đừng nhầm index của SpEL với positional parameter JPQL `?1`, vốn bắt đầu từ 1. Ví dụ `?#{[0]}` truy cập đối số thứ nhất rồi bind giá trị của nó vào vị trí query.

Khi method có nhiều tham số hoặc thường xuyên thay đổi chữ ký, named expression/`@Param` dễ bảo trì hơn.

## 7. Truy cập thuộc tính lồng nhau của object tham số

SpEL có thể đọc thuộc tính từ một object filter:

```java
public record ProductFilter(
    String category,
    BigDecimal minimumPrice,
    Boolean active
) {}
```

Repository:

```java
@Query("""
    select p
    from Product p
    where p.category = :#{#filter.category}
      and p.price >= :#{#filter.minimumPrice}
      and p.active = :#{#filter.active}
    """)
List<Product> search(
    @Param("filter") ProductFilter filter
);
```

`#filter` tham chiếu tham số phương thức, còn `.category`, `.minimumPrice`, `.active` truy cập property tương ứng.

Nếu property có thể null, cần thiết kế predicate phù hợp thay vì mặc định phép so sánh với NULL sẽ trả kết quả như mong đợi.

Ví dụ filter tùy chọn:

```java
@Query("""
    select p
    from Product p
    where (:#{#filter.category} is null
           or p.category = :#{#filter.category})
      and (:#{#filter.active} is null
           or p.active = :#{#filter.active})
    """)
List<Product> searchOptionalFilters(
    @Param("filter") ProductFilter filter
);
```

Khi category hoặc active null, nhánh đầu tương ứng đúng và filter đó được bỏ qua. Với query lớn có nhiều filter tùy chọn, các biểu thức OR có thể ảnh hưởng khả năng sử dụng index. Hãy cân nhắc Specification hoặc query động nếu có nhiều tổ hợp điều kiện.

Ngoài ra, cần xác định semantics của object filter null. Nếu cả `filter` là null, việc truy cập `filter.category` có thể không hợp lệ; validate input hoặc xử lý trường hợp đó ở service trước khi gọi repository.

## 8. Dùng entityName cùng với tham số SpEL

Hai dạng expression có thể xuất hiện trong cùng một query:

```java
@NoRepositoryBean
public interface SearchableRepository<T extends SearchableRecord, ID>
        extends JpaRepository<T, ID> {

    @Query("""
        select e
        from #{#entityName} e
        where e.code = :#{#code}
        """)
    Optional<T> findByCodeExpression(
        @Param("code") String code
    );
}
```

Ở đây:

- `#{#entityName}` là template expression để xác định entity name.
- `:#{#code}` là value expression để lấy tham số và bind vào query.
- Alias `e` là identification variable của JPQL.
- `e.code` là property của entity, không phải tên cột SQL.

Đây là pattern hữu ích cho generic repository khi nhiều entity có chung mapping property.

## 9. Dùng SpEL với LIKE và escape wildcard

Tìm kiếm chuỗi bằng LIKE cần chú ý hai wildcard:

- `%` khớp không hoặc nhiều ký tự.
- `_` khớp đúng một ký tự.

Nếu người dùng nhập `50%_off`, thông thường ta muốn tìm chính chuỗi có ký tự phần trăm/gạch dưới, chứ không muốn chúng trở thành wildcard.

Spring Data JPA cung cấp hàm SpEL `escape(String)` để escape hai wildcard chuẩn SQL/JPQL `%` và `_` theo escape character được cấu hình:

```java
@Query("""
    select u
    from User u
    where u.firstname like %?#{escape([0])}%
    """)
List<User> findContainingLiteral(String input);
```

`escape([0])` escape ký tự wildcard trong đối số thứ nhất trước khi thêm wildcard tìm kiếm ở hai đầu.

Có thể lấy ký tự escape cấu hình bằng `escapeCharacter()`. Nếu viết rõ ESCAPE clause, cần xác nhận cú pháp JPQL và provider đang dùng:

```java
@Query("""
    select u
    from User u
    where u.firstname like %?#{escape([0])}%
      escape ?#{escapeCharacter()}
    """)
List<User> findContainingLiteralWithEscape(String input);
```

Khả năng hỗ trợ cú pháp escape parameter có thể phụ thuộc provider/phiên bản; kiểm thử query trên database mục tiêu. Hàm `escape` chỉ xử lý wildcard chuẩn `%` và `_`, không bảo đảm escape mọi ký tự đặc thù của từng database.

LIKE escaping không thay thế parameter binding. Luôn bind input như giá trị, không nối input trực tiếp vào query string.

## 10. Biểu thức giá trị không thể thay tên cột hoặc keyword

Parameter và SpEL value expression được dùng để truyền giá trị, ví dụ:

```java
@Query("select p from Product p where p.price >= :#{#minimum}")
List<Product> findAtLeast(@Param("minimum") BigDecimal minimum);
```

Không thể dùng parameter để thay identifier:

```java
// Không có ý nghĩa như mong đợi:
@Query("select p from Product p order by :#{#sortProperty}")
List<Product> search(@Param("sortProperty") String sortProperty);
```

`:sortProperty` được bind như một giá trị, không biến thành tên property trong ORDER BY. Database có thể hiểu đó là một hằng số cho mọi hàng, khiến kết quả không được sắp xếp theo cột mong muốn.

Tương tự, không thể bind tên bảng, tên entity, tên cột hoặc keyword như `ASC`/`DESC` bằng value parameter.

Nếu cần sort động, dùng Spring Data `Sort`/`Pageable` với property được cho phép, hoặc xây dựng custom query với whitelist:

```java
String orderExpression = switch (sortKey) {
    case "name" -> "p.name";
    case "price" -> "p.price";
    case "createdAt" -> "p.createdAt";
    default -> "p.id";
};
```

Chỉ nối identifier do ứng dụng kiểm soát từ whitelist. Mọi giá trị dữ liệu vẫn phải bind parameter. Không đưa chuỗi sort hoặc mảnh JPQL do người dùng gửi lên trực tiếp vào query.

## 11. entityName và nativeQuery

`#{#entityName}` phục vụ JPQL entity name. Native SQL sử dụng bảng/cột vật lý:

```java
@Query(
    value = "select * from purchase_order where order_status = ?1",
    nativeQuery = true
)
List<PurchaseOrder> findByStatusNative(String status);
```

Không giả định `#{#entityName}` sẽ chuyển thành `purchase_order`. Entity name và table name khác nhau; native SQL cần schema identifier đúng với database.

Một số phiên bản Spring Data JPA hỗ trợ SpEL value expression trong native query cho tham số, nhưng điều đó không biến entityName thành table-name resolver. Khi dùng native SQL, kiểm tra tài liệu phiên bản, cú pháp và khả năng binding của provider. Nếu query cần portable giữa nhiều database, ưu tiên JPQL khi đáp ứng được yêu cầu.

## 12. Biểu thức trong countQuery và phân trang

Repository có thể dùng `entityName` trong cả query dữ liệu và count query:

```java
@Query(
    value = """
        select e
        from #{#entityName} e
        where e.status = :status
        """,
    countQuery = """
        select count(e)
        from #{#entityName} e
        where e.status = :status
        """
)
Page<T> findPageByStatus(
    @Param("status") RecordStatus status,
    Pageable pageable
);
```

Query dữ liệu trả entity; count query trả tổng số entity thỏa điều kiện. Điều kiện WHERE của hai query phải tương đương, nếu không `totalElements` sẽ sai.

Nếu query có JOIN collection, DISTINCT, GROUP BY hoặc subquery phức tạp, count query có thể cần viết riêng và kiểm thử. Không mặc định Spring Data luôn suy ra count query chính xác từ mọi JPQL/native SQL.

Với Page, Spring Data có thể thực hiện thêm count query. Nếu không cần tổng số trang, cân nhắc Slice để tránh chi phí đếm tổng.

## 13. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| JPQL báo entity không tồn tại | Dùng tên bảng hoặc class name không đúng entity name | Kiểm tra `@Entity(name)`; dùng entity name hoặc `#{#entityName}` |
| Query generic repository lỗi property | Entity cụ thể không có property được query tham chiếu | Dùng mapped superclass/interface mapping phù hợp hoặc tách repository |
| `#{#entityName}` không tạo tên bảng native | Nhầm entity name với table name | Native SQL dùng tên bảng/cột vật lý |
| SpEL không tìm thấy tham số | Tên `@Param` và tên trong expression không khớp | Đồng bộ tên hoặc dùng positional expression |
| `?#{[0]}` lấy sai tham số | Nhầm index 0-based của SpEL với positional JPQL 1-based | Kiểm tra lại thứ tự đối số |
| Expression đọc property null | Object filter hoặc nested property null | Validate input, xử lý null hoặc dùng predicate phù hợp |
| ORDER BY không đổi theo parameter | Parameter được bind như giá trị, không phải identifier | Dùng Sort/Pageable hoặc whitelist query động |
| LIKE tìm cả wildcard như ký tự đặc biệt | Input chưa được escape | Dùng `escape([0])` và kiểm tra ESCAPE clause |
| Native query không hiểu entityName | Entity name không phải tên bảng SQL | Dùng table name vật lý trong native SQL |
| Count của Page sai | Count query không tương đương query dữ liệu | Viết countQuery rõ ràng và test |
| Query hoạt động trên một provider nhưng lỗi provider khác | SpEL/native binding hoặc function phụ thuộc implementation | Dùng cú pháp portable khi cần và test provider/database mục tiêu |

## 14. Kiểm thử repository có SpEL

Không chỉ kiểm tra query có khởi động được. Hãy kiểm thử kết quả và các trường hợp biên:

- Repository generic được kế thừa bởi ít nhất hai entity có entity name khác nhau.
- Entity có `@Entity(name = "...")` tùy chỉnh vẫn được phân giải đúng.
- Tham số named expression nhận đúng giá trị.
- Positional expression `[0]` và `[1]` ánh xạ đúng thứ tự.
- Nested filter property xử lý null theo yêu cầu.
- LIKE escape xử lý chuỗi chứa `%` và `_`.
- Native query dùng tên bảng vật lý và không phụ thuộc entityName.
- Sort động chỉ nhận identifier trong whitelist.
- Page content và countQuery trả kết quả nhất quán.
- Input chứa dấu nháy, ký tự đặc biệt và chuỗi giống SQL không thể thay đổi cấu trúc query.

Dùng `@DataJpaTest` với database tương thích production hoặc Testcontainers khi query phụ thuộc dialect. Mock repository không thực thi SpEL, JPQL parser hay SQL nên không đủ để xác minh mapping.

## 15. Hướng dẫn chọn cú pháp

| Nhu cầu | Cú pháp nên dùng |
|---|---|
| Query JPQL trong generic repository | `#{#entityName}` |
| Bind một tham số có tên | `:status` |
| Lấy giá trị tham số bằng SpEL | `:#{#status}` |
| Lấy thuộc tính nested object | `:#{#filter.minimumPrice}` |
| Lấy đối số theo index | `?#{[0]}` |
| Escape wildcard LIKE | `escape([0])` |
| Sắp xếp theo property động | `Sort`/`Pageable` hoặc whitelist |
| Truy vấn bảng vật lý | Native SQL với table/column name thực tế |

Nếu query chỉ cần một tham số đơn giản, `:status` rõ ràng hơn `:#{#status}`. Dùng SpEL khi thực sự cần biểu thức, object lồng nhau hoặc biến entityName.

## 16. Checklist trước khi đưa @Query SpEL vào production

- [ ] Đang viết JPQL hay native SQL?
- [ ] Entity name có bị tùy chỉnh bằng `@Entity(name)` không?
- [ ] Có đang nhầm entity name với `@Table(name)`?
- [ ] Generic repository có `@NoRepositoryBean`?
- [ ] Mọi entity kế thừa có các property được query sử dụng?
- [ ] Tên `@Param` khớp expression?
- [ ] Positional SpEL index có đúng 0-based?
- [ ] Object/nested property có thể null không?
- [ ] Giá trị người dùng luôn được bind, không nối chuỗi?
- [ ] Sort/identifier động có whitelist?
- [ ] LIKE wildcard có được escape đúng?
- [ ] Count query có cùng predicate với query dữ liệu?
- [ ] Integration test chạy trên provider và database mục tiêu?

## 17. Kết luận

`#{#entityName}` giúp viết JPQL tổng quát theo domain type của repository và tự phân giải entity name của entity cụ thể. Nó hữu ích nhất trong generic repository, nơi cùng một query có thể dùng cho nhiều entity có mapping chung.

Các biểu thức `:#{#parameter}` và `?#{[0]}` giúp lấy giá trị từ tham số phương thức hoặc property lồng nhau rồi bind vào query. Chúng không thay tên bảng, tên cột hay keyword. Với native SQL, hãy dùng tên bảng/cột vật lý; với dynamic sorting, dùng Sort/Pageable hoặc whitelist identifier.

Giữ query dễ đọc bằng cách ưu tiên named parameter thông thường khi đủ dùng, giới hạn SpEL vào các trường hợp thực sự cần và kiểm thử integration trên đúng provider/database. Điều đó giúp tận dụng khả năng tái sử dụng mà không làm query khó hiểu hoặc tạo lỗ hổng khi xử lý input.
