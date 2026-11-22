# Sort, Sort.Order và sắp xếp theo nhiều thuộc tính trong Spring Data JPA

Spring Data cung cấp `Sort` để mô tả thứ tự sắp xếp của kết quả truy vấn. Một `Sort` gồm một hoặc nhiều `Sort.Order`; mỗi Order xác định **thuộc tính**, **chiều sắp xếp** (ASC/DESC), tùy chọn không phân biệt hoa thường và gợi ý xử lý giá trị NULL.

Khi cần sắp xếp theo nhiều thuộc tính, thứ tự khai báo các Order quyết định mức ưu tiên: thuộc tính đầu tiên được xét trước, thuộc tính tiếp theo chỉ dùng để phân định các hàng bằng nhau ở tiêu chí trước. Kết hợp `Sort` với repository method hoặc `Pageable` giúp thay đổi thứ tự kết quả mà không phải tạo một query riêng cho từng tổ hợp sắp xếp.

Tài liệu dùng Spring Data JPA trong Spring Boot 3 trở lên. Các ví dụ repository/service là những thành phần cần project Spring, entity, database và dependency tương ứng; không phải chương trình Java độc lập có thể chạy chỉ bằng `javac`.

## 1. Sort và Sort.Order là gì?

- **`Sort`** là đối tượng mô tả danh sách các tiêu chí sắp xếp. Nó có thể chứa một hoặc nhiều Order.
- **`Sort.Order`** mô tả một tiêu chí: property cần sắp xếp, Direction, case handling và null handling.
- **`Sort.Direction`** có hai giá trị chính: `ASC` (tăng dần) và `DESC` (giảm dần).
- **`Sort.NullHandling`** mô tả gợi ý về vị trí của giá trị NULL: native, first hoặc last.

Ví dụ đơn giản:

```java
Sort sort = Sort.by("name").ascending();
```

Tương đương tạo một Order tăng dần trên property `name`.

Sort không thực thi query và không chứa dữ liệu. Nó chỉ mô tả cách kết quả cần được sắp xếp; repository hoặc query execution sẽ chuyển mô tả này thành ORDER BY phù hợp với store.

## 2. Tạo Sort với một thuộc tính

Các cách thường dùng:

```java
Sort byNameAsc = Sort.by("name");
Sort byNameDesc = Sort.by("name").descending();

Sort byPriceAsc = Sort.by(Sort.Direction.ASC, "price");
Sort byCreatedDesc = Sort.by(Sort.Direction.DESC, "createdAt");
```

Nếu chỉ truyền property mà không chỉ định direction, mặc định là ASC.

Có thể tạo Order tường minh:

```java
Sort.Order order = Sort.Order.asc("name");
Sort sort = Sort.by(order);
```

Hoặc:

```java
Sort.Order order = Sort.Order.desc("createdAt");
Sort sort = Sort.by(order);
```

Cách dùng Order tường minh hữu ích khi cần thêm ignoreCase hoặc null handling.

Property truyền vào Sort là tên thuộc tính Java trong entity hoặc property path hợp lệ, không phải tên cột vật lý trong database. Ví dụ entity có `createdAt` ánh xạ tới cột `created_at`; Sort phải dùng `createdAt`.

## 3. Sort theo nhiều thuộc tính

Có nhiều cách tạo Sort với nhiều Order:

```java
Sort sort = Sort.by("lastName", "firstName");
```

Cả hai tiêu chí đều ASC. `lastName` được ưu tiên; khi hai hàng có cùng lastName, hệ thống mới xét firstName.

Có thể chỉ định direction chung:

```java
Sort sort = Sort.by(
    Sort.Direction.DESC,
    "createdAt",
    "id"
);
```

Cả createdAt và id đều DESC.

Khi mỗi thuộc tính có direction riêng, dùng nhiều Order:

```java
Sort sort = Sort.by(
    Sort.Order.asc("lastName"),
    Sort.Order.asc("firstName"),
    Sort.Order.desc("createdAt")
);
```

Thứ tự tương ứng trong SQL có ý nghĩa:

```sql
order by last_name asc,
         first_name asc,
         created_at desc
```

SQL trên chỉ minh họa; tên cột và cú pháp thực tế do mapping, provider và database quyết định.

### 3.1. Thứ tự ưu tiên của các Order

Giả sử dữ liệu:

| lastName | firstName | score |
|---|---|---:|
| Nguyen | An | 90 |
| Nguyen | Binh | 85 |
| Tran | An | 95 |
| Nguyen | An | 98 |

Sort:

```java
Sort sort = Sort.by(
    Sort.Order.asc("lastName"),
    Sort.Order.asc("firstName"),
    Sort.Order.desc("score")
);
```

Kết quả theo logic:

| lastName | firstName | score |
|---|---|---:|
| Nguyen | An | 98 |
| Nguyen | An | 90 |
| Nguyen | Binh | 85 |
| Tran | An | 95 |

lastName được xét trước; trong nhóm Nguyen thì firstName được xét; trong nhóm cùng Nguyen/An thì score DESC quyết định thứ tự.

Đừng đảo thứ tự Order nếu nghiệp vụ yêu cầu ưu tiên khác. `Sort.by("firstName", "lastName")` không tương đương `Sort.by("lastName", "firstName")`.

## 4. Dùng Sort.Order để cấu hình chi tiết

Một Order có thể được tạo bằng factory method:

```java
Sort.Order ascending = Sort.Order.asc("name");
Sort.Order descending = Sort.Order.desc("createdAt");
```

Có thể dùng constructor:

```java
Sort.Order order = new Sort.Order(
    Sort.Direction.DESC,
    "createdAt"
);
```

Các method thường dùng:

| Method | Tác dụng |
|---|---|
| `Sort.Order.asc(property)` | Tạo Order tăng dần |
| `Sort.Order.desc(property)` | Tạo Order giảm dần |
| `ignoreCase()` | Yêu cầu sắp xếp chuỗi không phân biệt hoa thường |
| `nullsFirst()` | Gợi ý đưa NULL lên đầu |
| `nullsLast()` | Gợi ý đưa NULL xuống cuối |
| `nullsNative()` | Dùng hành vi NULL mặc định của datastore |
| `with(direction)` | Tạo Order cùng property nhưng direction khác |
| `reverse()` | Đảo direction của Order |
| `isAscending()` / `isDescending()` | Kiểm tra chiều sắp xếp |
| `getProperty()` | Lấy property path |
| `getDirection()` | Lấy direction |
| `getNullHandling()` | Lấy null handling hint |

Order là immutable value object; các method cấu hình trả về Order mới. Hãy gán kết quả trả về khi chain method.

## 5. Sắp xếp không phân biệt hoa thường

Với thuộc tính chuỗi, có thể dùng `ignoreCase()`:

```java
Sort sort = Sort.by(
    Sort.Order.asc("name").ignoreCase()
);
```

Ví dụ các giá trị `alpha`, `Beta`, `CHARLIE` được sắp theo dạng không phân biệt casing theo cách provider/database thực thi.

Kết hợp với nhiều property:

```java
Sort sort = Sort.by(
    Sort.Order.asc("lastName").ignoreCase(),
    Sort.Order.asc("firstName").ignoreCase(),
    Sort.Order.asc("id")
);
```

Lưu ý:

- Chỉ dùng ignoreCase cho property chuỗi.
- Provider có thể chuyển thành biểu thức như `LOWER(column)` hoặc dùng cơ chế database tương ứng.
- Collation của database cũng ảnh hưởng cách so sánh chữ hoa/thường, dấu và locale.
- Áp dụng function lên cột có thể khiến index B-tree thông thường không được dùng trực tiếp; cần kiểm tra execution plan hoặc cân nhắc functional index/collation phù hợp.
- IgnoreCase không tự động chuẩn hóa dấu tiếng Việt hay quy tắc sắp xếp theo locale.

Nếu cần thứ tự theo ngôn ngữ cụ thể, hãy xác định collation mong muốn ở database và kiểm thử dữ liệu có dấu, thay vì giả định ignoreCase giải quyết mọi quy tắc ngôn ngữ.

## 6. Sắp xếp giá trị NULL

Có thể đặt gợi ý vị trí NULL trên từng Order:

```java
Sort nullFirst = Sort.by(
    Sort.Order.asc("publishedAt").nullsFirst()
);

Sort nullLast = Sort.by(
    Sort.Order.asc("publishedAt").nullsLast()
);
```

Ba lựa chọn chính:

- `nullsFirst()`: yêu cầu NULL đứng trước giá trị khác.
- `nullsLast()`: yêu cầu NULL đứng sau giá trị khác.
- `nullsNative()`: để database/provider dùng hành vi mặc định.

**Null handling là gợi ý cho datastore; không phải mọi database/provider đều bảo đảm thực hiện giống nhau.** Hành vi mặc định khi sort ASC/DESC cũng khác giữa các database. Nếu thứ tự NULL là quy tắc nghiệp vụ quan trọng, phải kiểm tra SQL được sinh và integration test trên đúng database production.

Nếu cần thứ tự portable hơn, có thể biểu diễn quy tắc NULL bằng CASE trong JPQL:

```jpql
select p
from Product p
order by
    case when p.publishedAt is null then 1 else 0 end asc,
    p.publishedAt desc,
    p.id asc
```

Biểu thức CASE đưa hàng có publishedAt NULL xuống sau các hàng có ngày. Tuy nhiên, khi kết hợp dynamic Sort, cần tránh tạo hai tiêu chí xung đột trên cùng property và kiểm tra execution plan vì CASE có thể ảnh hưởng việc sử dụng index.

## 7. Kết hợp nhiều Order với direction, ignoreCase và NULL

Mỗi Order có thể cấu hình độc lập:

```java
Sort sort = Sort.by(
    Sort.Order.asc("country").ignoreCase().nullsLast(),
    Sort.Order.asc("city").ignoreCase().nullsLast(),
    Sort.Order.desc("createdAt").nullsLast(),
    Sort.Order.asc("id")
);
```

Ý nghĩa:

1. Country ASC, không phân biệt hoa thường, NULL cuối.
2. City ASC, không phân biệt hoa thường, NULL cuối.
3. CreatedAt DESC, NULL cuối.
4. ID ASC để phân định các hàng còn bằng nhau.

Không phải mọi datastore đều thực thi mọi null hint; kiểm tra behavior thực tế. ignoreCase chỉ phù hợp cho property chuỗi.

Có thể tạo Order rồi thay direction:

```java
Sort.Order newestFirst = Sort.Order.asc("createdAt")
    .with(Sort.Direction.DESC);

Sort sort = Sort.by(newestFirst, Sort.Order.asc("id"));
```

## 8. Ghép và đảo Sort

Có thể kết hợp hai Sort bằng `and()`:

```java
Sort primary = Sort.by(
    Sort.Order.asc("lastName"),
    Sort.Order.asc("firstName")
);

Sort tieBreaker = Sort.by(
    Sort.Order.asc("id")
);

Sort combined = primary.and(tieBreaker);
```

Các Order của primary đứng trước, sau đó tới các Order của tieBreaker.

Có thể đảo chiều toàn bộ Sort:

```java
Sort reversed = combined.reverse();
```

Reverse đảo ASC thành DESC và ngược lại cho từng Order. Nó không tự thay đổi thứ tự ưu tiên của các property.

Có thể kiểm tra Sort:

```java
if (sort.isSorted()) {
    // Có ít nhất một Order.
}

Sort none = Sort.unsorted();
boolean sorted = none.isSorted(); // false
```

Dùng `Sort.unsorted()` khi không muốn áp dụng sắp xếp động. Không truyền null nếu API cho phép dùng giá trị unsorted rõ ràng.

## 9. Dùng Sort trong derived query method

Spring Data JPA hỗ trợ thêm tham số Sort vào repository method:

```java
public interface UserRepository
        extends JpaRepository<User, Long> {

    List<User> findByActiveTrue(Sort sort);
}
```

Gọi từ service:

```java
Sort sort = Sort.by(
    Sort.Order.asc("lastName"),
    Sort.Order.asc("firstName"),
    Sort.Order.desc("createdAt")
);

List<User> users = userRepository.findByActiveTrue(sort);
```

Spring Data tạo predicate từ tên method và thêm thứ tự sắp xếp theo Sort truyền vào.

Một số method có thể khai báo static ordering ngay trong tên:

```java
List<User> findByActiveTrueOrderByLastNameAscFirstNameAsc();
```

Static OrderBy phù hợp khi thứ tự cố định. Tham số Sort phù hợp khi caller cần chọn thứ tự tại runtime. Tránh thiết kế method vừa có static OrderBy vừa truyền dynamic Sort nếu chưa xác định rõ thứ tự kết hợp; hãy kiểm tra query thực tế để tránh ORDER BY lặp hoặc xung đột.

## 10. Dùng Sort với @Query JPQL

Sort cũng dùng được với repository method có `@Query`:

```java
@Query("""
    select u
    from User u
    where u.active = true
    """)
List<User> findActiveUsers(Sort sort);
```

Gọi:

```java
List<User> users = userRepository.findActiveUsers(
    Sort.by(
        Sort.Order.asc("lastName").ignoreCase(),
        Sort.Order.asc("firstName").ignoreCase()
    )
);
```

Spring Data JPA có thể thêm ORDER BY động vào JPQL. Property trong Sort phải được phân giải thành property của domain model hoặc alias hợp lệ có trong query.

Ví dụ projection có alias:

```java
@Query("""
    select u.firstname as firstName,
           length(u.firstname) as nameLength
    from User u
    where u.active = true
    """)
List<Object[]> findNamesAndLengths(Sort sort);
```

Nếu query khai báo alias hợp lệ và Spring Data nhận diện được, có thể sort theo alias đó, ví dụ `Sort.by("nameLength")`. Cần xác nhận với kiểu projection/query cụ thể.

## 11. Sort theo nested property path

Sort có thể dùng property path qua association:

```java
Sort sort = Sort.by(
    Sort.Order.asc("department.name"),
    Sort.Order.asc("lastName")
);
```

Nếu User có quan hệ tới Department, `department.name` là đường dẫn thuộc tính trong mô hình entity. Provider có thể tạo JOIN cần thiết để sắp xếp.

Lưu ý:

- Property path phải tồn tại và đúng tên Java mapping.
- Sort qua association có thể làm query phát sinh JOIN.
- Sort qua quan hệ to-one thường dễ xác định hơn.
- Sắp xếp theo collection-valued association thường không có một giá trị đơn rõ ràng cho mỗi entity cha; cần viết query/aggregate rõ ràng thay vì truyền property path tùy tiện.
- JOIN có thể làm query phức tạp, ảnh hưởng pagination, count và index.

Không dùng tên cột vật lý như `department_name` nếu đó không phải property path hoặc alias được query hỗ trợ.

## 12. Dùng Sort với Pageable và phân trang

`Pageable` chứa page number, page size và Sort. Có thể tạo bằng `PageRequest.of(page, size, sort)`:

```java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
    )
);

Page<User> result = userRepository.findByActiveTrue(pageable);
```

Page index bắt đầu từ 0. Ví dụ page 0 là trang đầu tiên, size 20 là tối đa 20 kết quả.

Repository:

```java
Page<User> findByActiveTrue(Pageable pageable);
```

Sort có thể được truyền riêng hoặc gắn vào Pageable. Khi đã dùng Pageable, không cần thêm một tham số Sort riêng cho cùng mục đích.

### 12.1. Page, Slice và List

- `Page<T>` chứa content, thông tin trang và tổng số phần tử/trang. Thường cần count query để tính tổng.
- `Slice<T>` cho biết có trang tiếp theo hay không mà không yêu cầu tổng số trang đầy đủ.
- `List<T>` với Pageable có thể giới hạn kết quả nhưng không cung cấp metadata trang như Page.

Dùng Slice nếu UI chỉ cần nút “tiếp theo” và không cần tổng số bản ghi. Sort trong Pageable vẫn xác định thứ tự kết quả.

### 12.2. Thứ tự ổn định khi phân trang

Khi phân trang, hãy thêm một property unique làm tie-breaker:

```java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
```

Nếu chỉ sort theo createdAt và nhiều hàng có cùng timestamp, thứ tự giữa các hàng bằng nhau không xác định. Khi dữ liệu thay đổi giữa các request, người dùng có thể thấy hàng lặp hoặc bị bỏ qua ở các trang khác nhau.

Unique tie-breaker tạo thứ tự xác định hơn. Tuy vậy, offset pagination vẫn có thể dịch chuyển khi dữ liệu mới được insert/delete ở đầu danh sách. Với tập dữ liệu lớn và luồng ghi liên tục, cân nhắc keyset/scrolling pagination theo khả năng Spring Data và query.

## 13. Dynamic Sort từ API và whitelist

Không nên nhận tên property tùy ý từ request rồi chuyển thẳng vào Sort mà không kiểm soát. Dù Spring Data kiểm tra property path trong nhiều trường hợp, whitelist giúp API chỉ cho phép những tiêu chí được thiết kế và tránh đưa identifier không tin cậy vào query đặc biệt.

Ví dụ mapping giá trị sort từ API:

```java
public enum UserSortKey {
    NAME,
    CREATED_AT,
    EMAIL
}
```

Tạo Sort từ enum:

```java
public Sort toSort(UserSortKey key, Sort.Direction direction) {
    return switch (key) {
        case NAME -> Sort.by(
            new Sort.Order(direction, "lastName"),
            new Sort.Order(direction, "firstName"),
            Sort.Order.asc("id")
        );
        case CREATED_AT -> Sort.by(
            new Sort.Order(direction, "createdAt"),
            Sort.Order.asc("id")
        );
        case EMAIL -> Sort.by(
            new Sort.Order(direction, "email"),
            Sort.Order.asc("id")
        );
    };
}
```

Trong ví dụ, ID ASC luôn là tie-breaker. Nếu direction cũng đến từ request, chỉ chuyển đổi từ các giá trị ASC/DESC được cho phép; từ chối giá trị lạ thay vì ghép chuỗi vào query.

Có thể cho API nhận nhiều tiêu chí, nhưng nên giới hạn số lượng, property được phép và direction. Việc whitelist cần dựa trên domain property path, không phải tên cột SQL.

## 14. JpaSort.unsafe và sắp xếp theo biểu thức

Thông thường Spring Data JPA xác thực Sort property để nó tương ứng property path hoặc alias hợp lệ. Một biểu thức như `LENGTH(u.firstname)` không phải property đơn giản nên có thể bị từ chối khi truyền qua Sort thông thường.

Spring Data JPA có `JpaSort.unsafe(...)` để thêm biểu thức ORDER BY không được kiểm tra theo property path:

```java
import org.springframework.data.jpa.domain.JpaSort;

Sort sort = JpaSort.unsafe(
    Sort.Direction.ASC,
    "LENGTH(u.firstname)"
);
```

Dùng unsafe có rủi ro vì biểu thức được đưa vào query string. Chỉ dùng literal do lập trình viên kiểm soát; **không bao giờ truyền biểu thức, tên cột hoặc fragment sort do người dùng cung cấp trực tiếp vào JpaSort.unsafe**.

Khi có thể, hãy chọn một trong các cách an toàn hơn:

1. Đưa biểu thức vào SELECT với alias hợp lệ rồi sort theo alias.
2. Viết query JPQL có ORDER BY cố định.
3. Tạo custom repository với danh sách biểu thức được whitelist.
4. Dùng function/column đã được thiết kế và index phù hợp ở database.

Ví dụ query có alias:

```java
@Query("""
    select u.firstname as firstName,
           length(u.firstname) as nameLength
    from User u
    where u.active = true
    """)
List<Object[]> findActiveNames(Sort sort);
```

Có thể cân nhắc sort theo `nameLength` nếu query parser và projection hỗ trợ alias đó. Kiểm thử SQL thực tế với phiên bản Spring Data JPA đang dùng.

## 15. Sort không thay đổi dữ liệu và không đảm bảo thứ tự nếu thiếu Order

Sort chỉ thay đổi thứ tự các hàng trong kết quả query. Nó không:

- Cập nhật giá trị entity.
- Thay đổi thứ tự vật lý của hàng trong database.
- Tạo index tự động.
- Bảo đảm thứ tự nếu query không có ORDER BY.
- Thay thế filter trong WHERE.
- Thay thế phân trang hoặc giới hạn số hàng.

Nếu không truyền Sort và query không có ORDER BY, database không bảo đảm một thứ tự ổn định. Không dựa vào thứ tự insert, ID hoặc lần chạy trước đó.

Một Sort rỗng có thể được biểu diễn bằng `Sort.unsorted()`. Nếu query có ORDER BY cố định, query vẫn có thể sắp xếp theo thứ tự đó dù Sort động không được truyền.

## 16. Index và hiệu năng sắp xếp

ORDER BY có thể yêu cầu database sort kết quả bằng memory hoặc temporary storage nếu index không hỗ trợ thứ tự cần thiết. Một số nguyên tắc:

- Index các cột thường dùng trong WHERE/JOIN/ORDER BY theo workload thực tế.
- Với filter theo status và sort theo createdAt, có thể đánh giá composite index gồm status và createdAt.
- Nếu sort nhiều cột, thứ tự cột trong index có ý nghĩa.
- DESC/ASC và khả năng scan ngược phụ thuộc database/index implementation.
- Sort theo LOWER(property) hoặc CASE có thể cần functional index hoặc expression index.
- Sort qua association có thể thêm JOIN và tăng chi phí.
- Index giúp đọc/sắp xếp nhưng làm tăng dung lượng và chi phí INSERT/UPDATE/DELETE.

Ví dụ query:

```jpql
select u
from User u
where u.active = true
order by u.createdAt desc, u.id desc
```

Một index ứng viên có thể bắt đầu bằng `active`, sau đó `created_at` và `id`, nhưng cấu trúc tối ưu phụ thuộc selectivity, số lượng hàng, database và các query khác. Dùng EXPLAIN/EXPLAIN ANALYZE trên dữ liệu gần production để kiểm tra plan thay vì tạo index theo cảm tính.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Sort không tìm thấy property | Dùng tên cột SQL hoặc sai property path | Dùng tên thuộc tính Java hoặc alias query hợp lệ |
| Kết quả sort nhiều tiêu chí sai thứ tự | Đảo thứ tự Order | Đặt tiêu chí quan trọng nhất trước |
| Mọi property cùng direction ngoài ý muốn | Dùng `Sort.by(Direction, ...)` với direction chung | Tạo từng `Sort.Order` riêng |
| IgnoreCase không như mong muốn | Property không phải String, collation hoặc provider khác nhau | Chỉ dùng cho String; test locale/collation |
| NULL xuất hiện sai vị trí | Database/provider bỏ qua null handling hint | Kiểm tra SQL; dùng CASE hoặc database-specific query |
| Sort nested property làm query chậm | Provider tạo JOIN hoặc thiếu index | Kiểm tra SQL/EXPLAIN; cân nhắc projection |
| Pagination có hàng lặp/bị bỏ qua | Thứ tự không unique hoặc dữ liệu thay đổi giữa trang | Thêm tie-breaker unique; cân nhắc keyset pagination |
| Sort động không hoạt động trong native query | Khả năng rewrite SQL native có giới hạn | Dùng ORDER BY cố định hoặc custom query với whitelist |
| Function trong Sort bị từ chối | Function không phải property path hợp lệ | Dùng alias/query cố định hoặc JpaSort.unsafe với literal tin cậy |
| SQL injection qua sort expression | Ghép identifier/fragment từ input | Whitelist property và tuyệt đối không dùng input trực tiếp với unsafe |
| Index không được sử dụng | Function, thứ tự cột hoặc selectivity không phù hợp | Kiểm tra execution plan và thiết kế index theo workload |

## 18. Kiểm thử Sort

Integration test nên xác nhận thứ tự thực tế trên database/provider mục tiêu:

- Một property ASC và DESC.
- Nhiều property với direction khác nhau.
- Hai hàng bằng nhau ở tiêu chí đầu và được phân định bởi tiêu chí tiếp theo.
- IgnoreCase với chữ hoa/thường.
- NULLS FIRST/LAST theo database đang dùng.
- Nested property sort và JOIN phát sinh.
- Sort kết hợp PageRequest và Page/Slice.
- Thứ tự ổn định khi nhiều hàng có cùng giá trị sort.
- Property không nằm trong whitelist bị từ chối ở API layer.
- Native query và JpaSort.unsafe được kiểm soát, không nhận fragment từ người dùng.

Ví dụ test logic nhiều tiêu chí:

```java
@Test
void sortsByLastNameThenFirstName() {
    Sort sort = Sort.by(
        Sort.Order.asc("lastName"),
        Sort.Order.asc("firstName"),
        Sort.Order.asc("id")
    );

    List<User> users = repository.findByActiveTrue(sort);

    assertThat(users)
        .extracting(User::getLastName, User::getFirstName)
        .containsSubsequence(
            tuple("Nguyen", "An"),
            tuple("Nguyen", "Binh"),
            tuple("Tran", "An")
        );
}
```

Ví dụ giả định repository, entity, fixture và AssertJ tuple assertions đã được cấu hình. Nếu nhiều hàng có cùng lastName/firstName, thêm fixture và kiểm tra ID tie-breaker để xác nhận thứ tự đầy đủ.

## 19. Checklist trước khi đưa Sort vào production

- [ ] Property trong Sort là domain property path hoặc query alias hợp lệ?
- [ ] Order quan trọng nhất được đặt trước?
- [ ] Direction được cấu hình riêng cho từng property khi cần?
- [ ] ignoreCase chỉ dùng với property chuỗi?
- [ ] Null handling đã được kiểm thử trên database thực tế?
- [ ] Có tie-breaker unique khi phân trang?
- [ ] Dynamic sort từ request đã được whitelist?
- [ ] Không truyền input người dùng vào JpaSort.unsafe?
- [ ] Native query có hỗ trợ dynamic Sort trong cấu trúc hiện tại?
- [ ] Nested association sort có tạo JOIN ngoài dự kiến?
- [ ] Index và execution plan đã được kiểm tra?
- [ ] Page/count query có trả metadata đúng?

## 20. Kết luận

`Sort` là tập hợp các tiêu chí sắp xếp; `Sort.Order` mô tả một property, direction và các tùy chọn như ignoreCase/null handling. Khi sort nhiều thuộc tính, thứ tự Order quyết định ưu tiên: property đầu tiên phân loại trước, property sau dùng làm tie-breaker.

Dùng `Sort.by(...)` cho trường hợp đơn giản, `Sort.Order` khi cần direction/NULL/case riêng, `Sort.and()` để ghép tiêu chí và `PageRequest.of(..., sort)` khi phân trang. Property phải là tên Java mapping hoặc alias query hợp lệ, không phải tên cột SQL. Với sort động, whitelist property và direction; chỉ dùng `JpaSort.unsafe` cho biểu thức tĩnh đáng tin cậy. Cuối cùng, kiểm tra SQL, execution plan và thứ tự NULL trên đúng database trước khi triển khai.
