# Biểu diễn bộ lọc bằng Query và Criteria

Trong **Spring Data Relational JDBC**, một truy vấn có thể cần lọc theo nhiều thuộc tính mà người dùng chọn tùy từng request. Ví dụ màn hình tìm sản phẩm cho phép lọc theo trạng thái, danh mục, khoảng giá, từ khóa và thời điểm tạo. Nếu viết một repository method riêng cho mọi tổ hợp, số lượng method sẽ tăng nhanh. Nếu ghép SQL bằng chuỗi tùy tiện, code dễ khó bảo trì và có nguy cơ SQL injection.

Spring Data Relational cung cấp **Query** và **Criteria** để biểu diễn điều kiện truy vấn bằng Java. **Criteria** mô tả điều kiện trên các thuộc tính được ánh xạ; **Query** đóng gói điều kiện cùng những tùy chọn truy vấn như sắp xếp, giới hạn và offset. Trong Spring Data JDBC, các đối tượng này có thể được dùng cùng **JdbcAggregateTemplate** để tìm, đếm, kiểm tra tồn tại hoặc xóa aggregate theo điều kiện.

Bài học tập trung vào cách xây dựng bộ lọc động bằng Query và Criteria, kết hợp điều kiện AND/OR, xử lý tham số tùy chọn và tập rỗng, sắp xếp/phân trang, thực thi truy vấn trên aggregate, cùng những giới hạn cần nhận biết khi truy vấn phức tạp hơn mô hình aggregate.

## 1. Vì sao cần Query và Criteria?

Giả sử ứng dụng quản lý sản phẩm. Một request tìm kiếm có thể gửi:

~~~text
status = ACTIVE
categoryId = 12
minimumPrice = 100000
maximumPrice = 500000
nameContains = "book"
sort = PRICE_ASC
page = 0
size = 20
~~~

Một request khác có thể chỉ gửi trạng thái; request thứ ba chỉ gửi danh mục và từ khóa. Các điều kiện không cố định trong mọi lần gọi.

Có ba cách thường gặp:

1. Khai báo nhiều derived query method cho từng trường hợp.
2. Viết một câu SQL có nhiều nhánh điều kiện tùy chọn.
3. Xây dựng điều kiện từ các tham số hiện có rồi tạo Query để thực thi.

Query và Criteria giúp cách thứ ba rõ ràng hơn:

~~~text
SearchFilter
    |
    v
Tạo Criteria từ các filter có giá trị
    |
    v
Kết hợp điều kiện
    |
    v
Query(criteria)
    +-- sort
    +-- limit
    +-- offset
    |
    v
JdbcAggregateTemplate
    |
    v
SQL được tạo theo mapping và dialect
    |
    v
Aggregate kết quả
~~~

Thay vì phải tự nối SQL cho mỗi tổ hợp, ứng dụng mô tả điều kiện theo thuộc tính miền và để Spring Data JDBC tạo câu lệnh phù hợp với mapping metadata.

## 2. Vai trò của Criteria và Query

Hai lớp thường dùng nằm trong package:

~~~java
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
~~~

### 2.1. Criteria biểu diễn điều kiện

Criteria mô tả một hoặc nhiều điều kiện trên thuộc tính được ánh xạ. Ví dụ:

~~~java
Criteria.where("status").is("ACTIVE");
~~~

Điều kiện này có nghĩa thuộc tính status bằng ACTIVE.

Kết hợp thêm điều kiện:

~~~java
Criteria.where("status").is("ACTIVE")
        .and("priceMinorUnits").greaterThanOrEquals(100_000L);
~~~

Điều kiện biểu diễn:

~~~sql
status = 'ACTIVE'
AND price_minor_units >= 100000
~~~

Đây là mô tả logic; SQL thực tế được framework tạo và bind tham số.

### 2.2. Query đóng gói điều kiện truy vấn

Query kết hợp Criteria với các tùy chọn đọc:

~~~java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
);
~~~

Query có thể mang thêm sort, limit và offset:

~~~java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
).sort(Sort.by(Sort.Order.desc("createdAt")))
 .limit(20)
 .offset(0);
~~~

Import Sort:

~~~java
import org.springframework.data.domain.Sort;
~~~

Criteria trả lời **lọc những hàng nào**; Query mô tả **truy vấn tập dữ liệu đó theo cách nào**, chẳng hạn thứ tự và số lượng kết quả.

### 2.3. Query và Criteria không phải câu SQL

Đây là DSL (domain-specific language) Java cho truy vấn relational. Khi dùng:

~~~java
Criteria.where("priceMinorUnits").greaterThan(100_000L)
~~~

ta đang mô tả điều kiện trên thuộc tính Java được ánh xạ. Spring Data Relational dùng metadata để chuyển property thành tên cột phù hợp với schema/naming strategy.

Điều này khác với SQL trong @Query, nơi người viết dùng tên bảng và cột của database. Không đưa tên cột SQL tùy tiện vào Criteria nếu đó không phải tên property mà mapping mong đợi.

## 3. Thực thi Query bằng JdbcAggregateTemplate

Spring Data JDBC cung cấp JdbcAggregateTemplate để thao tác aggregate bằng các đối tượng Query/Criteria.

Ví dụ inject template:

~~~java
import java.util.List;
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final JdbcAggregateTemplate template;

    public ProductSearchService(JdbcAggregateTemplate template) {
        this.template = template;
    }

    public List<Product> findActiveProducts() {
        Query query = Query.query(
                Criteria.where("status").is("ACTIVE")
        );
        return template.findAll(query, Product.class);
    }
}
~~~

Các thao tác thường dùng của template gồm:

| Thao tác | Mục đích |
| --- | --- |
| findAll(query, type) | Tìm tất cả aggregate phù hợp |
| findOne(query, type) | Tìm một aggregate phù hợp |
| count(query, type) | Đếm số aggregate phù hợp |
| exists(query, type) | Kiểm tra có aggregate phù hợp hay không |
| delete(query, type) | Xóa aggregate phù hợp với điều kiện |

Tên và chữ ký API cụ thể cần được xác nhận theo phiên bản Spring Data JDBC mà ứng dụng đang dùng. Các ví dụ trong bài sử dụng API JdbcAggregateTemplate phổ biến của Spring Data JDBC.

### 3.1. Vì sao dùng template thay vì repository method?

Repository interface phù hợp với các truy vấn có hợp đồng cố định, ví dụ:

~~~java
Optional<Product> findBySku(String sku);
List<Product> findByStatus(String status);
~~~

Khi filter thay đổi theo request, service có thể tạo Query rồi gọi template. Cách này tránh phải khai báo một method cho mỗi tổ hợp filter.

Không cần thay mọi repository bằng JdbcAggregateTemplate. Có thể giữ repository cho CRUD và derived query, chỉ dùng template ở service hoặc custom repository fragment cho phần tìm kiếm động.

## 4. Các toán tử Criteria thường dùng

Criteria cung cấp các phép so sánh và kiểm tra phổ biến.

| Toán tử | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| is | where("status").is("ACTIVE") | Bằng giá trị |
| not | where("status").not("DELETED") | Khác giá trị |
| isNull | where("deletedAt").isNull() | Cột là SQL NULL |
| isNotNull | where("deletedAt").isNotNull() | Cột không NULL |
| greaterThan | where("price").greaterThan(100) | Lớn hơn |
| greaterThanOrEquals | where("price").greaterThanOrEquals(100) | Lớn hơn hoặc bằng |
| lessThan | where("price").lessThan(500) | Nhỏ hơn |
| lessThanOrEquals | where("price").lessThanOrEquals(500) | Nhỏ hơn hoặc bằng |
| between | where("price").between(100, 500) | Nằm trong khoảng |
| in | where("status").in(values) | Thuộc tập giá trị |
| notIn | where("status").notIn(values) | Không thuộc tập giá trị |
| like | where("name").like("%book%") | So khớp mẫu SQL LIKE |

Các toán tử cụ thể có thể thay đổi theo release. Kiểm tra API của dependency trong dự án nếu cần một phép toán ít dùng.

### 4.1. So sánh bằng và khác

~~~java
Criteria active = Criteria.where("status").is("ACTIVE");

Criteria notDeleted = Criteria.where("status").not("DELETED");
~~~

Nếu nghiệp vụ có giá trị enum:

~~~java
Criteria criteria = Criteria.where("status").is(ProductStatus.ACTIVE);
~~~

Cách chuyển enum thành giá trị lưu phụ thuộc mapping/converter của entity. Hãy dùng cùng kiểu biểu diễn mà Spring Data JDBC đã cấu hình cho property.

### 4.2. So sánh số và ngày giờ

~~~java
Criteria priceRange = Criteria.where("priceMinorUnits")
        .greaterThanOrEquals(100_000L)
        .and("priceMinorUnits")
        .lessThanOrEquals(500_000L);
~~~

Với thời gian:

~~~java
Criteria createdAfter = Criteria.where("createdAt")
        .greaterThanOrEquals(fromTime);
~~~

Kiểu giá trị truyền vào nên tương thích với kiểu property. Tránh so sánh một cột timestamp với chuỗi ngày giờ tự định dạng vì có thể gây chuyển đổi ngầm, lỗi timezone hoặc mất khả năng dùng index.

### 4.3. IN và NOT IN

~~~java
Criteria statuses = Criteria.where("status")
        .in(List.of("ACTIVE", "PENDING"));
~~~

Điều kiện tương đương:

~~~sql
status IN ('ACTIVE', 'PENDING')
~~~

Với danh sách bị loại trừ:

~~~java
Criteria excluded = Criteria.where("status")
        .notIn(List.of("DELETED", "ARCHIVED"));
~~~

Không nên truyền collection rỗng mà không xác định ý nghĩa. SQL có thể không chấp nhận danh sách IN rỗng hoặc framework có cách xử lý riêng. Hãy xử lý trường hợp đó ở tầng ứng dụng trước khi tạo Criteria.

### 4.4. BETWEEN

~~~java
Criteria price = Criteria.where("priceMinorUnits")
        .between(100_000L, 500_000L);
~~~

BETWEEN thường bao gồm cả hai biên. Nếu nghiệp vụ yêu cầu khoảng nửa mở, ví dụ từ ngày bắt đầu bao gồm nhưng ngày kết thúc không bao gồm, dùng hai điều kiện:

~~~java
Criteria period = Criteria.where("createdAt")
        .greaterThanOrEquals(startInclusive)
        .and("createdAt")
        .lessThan(endExclusive);
~~~

Cách này thường phù hợp với khoảng thời gian [start, end), tránh lỗi khi thời gian có độ chính xác phần giây khác nhau.

### 4.5. LIKE

~~~java
Criteria nameContains = Criteria.where("name").like("%book%");
~~~

LIKE dùng wildcard SQL:

- % khớp với chuỗi ký tự bất kỳ, kể cả rỗng.
- _ khớp với một ký tự.

Nếu input người dùng được đưa vào mẫu LIKE, cần xác định có cho phép wildcard hay không. Nếu muốn tìm literal text, phải escape ký tự wildcard theo quy tắc SQL/database phù hợp.

Tính không phân biệt hoa thường của LIKE phụ thuộc collation/database hoặc phép chuyển đổi được dùng. Không giả định một tiêu chí LIKE tự động có semantics giống IgnoreCase trong derived query ở mọi dialect.

## 5. Kết hợp điều kiện AND và OR

### 5.1. Kết hợp AND

Ví dụ sản phẩm phải đang ACTIVE và có giá từ 100.000:

~~~java
Criteria criteria = Criteria.where("status").is("ACTIVE")
        .and("priceMinorUnits").greaterThanOrEquals(100_000L);
~~~

Logic:

~~~sql
WHERE status = 'ACTIVE'
  AND price_minor_units >= 100000
~~~

Mỗi điều kiện bổ sung thu hẹp tập kết quả.

### 5.2. Kết hợp OR

Ví dụ chấp nhận hai trạng thái:

~~~java
Criteria criteria = Criteria.where("status").is("ACTIVE")
        .or("status").is("PENDING");
~~~

Logic:

~~~sql
WHERE status = 'ACTIVE'
   OR status = 'PENDING'
~~~

Khi dùng OR, số kết quả có thể tăng vì chỉ cần một nhánh đúng.

### 5.3. Cẩn thận với biểu thức AND/OR phức tạp

Xét yêu cầu:

~~~text
(status = ACTIVE OR status = PENDING)
AND price >= 100000
~~~

Đây là hai nhóm logic khác nhau. Không nên viết một chuỗi AND/OR dài rồi dựa vào trí nhớ về precedence. Trong SQL, AND thường có độ ưu tiên cao hơn OR; nếu không có ngoặc, biểu thức có thể được hiểu khác ý định.

Với điều kiện lồng nhiều nhóm:

- Tách nhóm logic thành các Criteria riêng theo API composition mà phiên bản hỗ trợ.
- Kiểm tra SQL được sinh để xác nhận dấu ngoặc.
- Viết integration test có dữ liệu phân biệt từng nhánh.
- Nếu biểu thức quá phức tạp hoặc cần join/subquery, cân nhắc @Query hoặc custom repository.

Không giả định mọi cách nối Criteria đều tạo đúng nhóm ngoặc mà người viết tưởng tượng. Hãy kiểm tra API cụ thể của release.

### 5.4. Ví dụ kiểm tra logic bằng dữ liệu

Với điều kiện:

~~~text
(ACTIVE OR PENDING) AND price >= 100
~~~

| Sản phẩm | Status | Price | Có khớp? |
| --- | --- | ---: | --- |
| A | ACTIVE | 150 | Có |
| B | PENDING | 100 | Có |
| C | ACTIVE | 50 | Không |
| D | ARCHIVED | 200 | Không |

Test nên bao phủ cả trường hợp một nhánh OR đúng nhưng điều kiện AND cuối sai.

## 6. Xây dựng Criteria từ filter tùy chọn

Đây là trường hợp dùng Query/Criteria phổ biến nhất. Ta không biết trước request sẽ có những bộ lọc nào.

Định nghĩa filter:

~~~java
public record ProductFilter(
        String status,
        Long categoryId,
        Long minimumPrice,
        Long maximumPrice,
        String nameContains,
        List<String> statuses
) {
}
~~~

Tạo Criteria theo từng giá trị:

~~~java
Criteria criteria = Criteria.empty();

if (filter.status() != null) {
    criteria = criteria.and("status").is(filter.status());
}

if (filter.categoryId() != null) {
    criteria = criteria.and("categoryId").is(filter.categoryId());
}

if (filter.minimumPrice() != null) {
    criteria = criteria.and("priceMinorUnits")
            .greaterThanOrEquals(filter.minimumPrice());
}

if (filter.maximumPrice() != null) {
    criteria = criteria.and("priceMinorUnits")
            .lessThanOrEquals(filter.maximumPrice());
}

if (filter.nameContains() != null
        && !filter.nameContains().isBlank()) {
    criteria = criteria.and("name")
            .like("%" + filter.nameContains().trim() + "%");
}

Query query = Query.query(criteria);
List<Product> products = template.findAll(query, Product.class);
~~~

Ý tưởng của đoạn code:

1. Bắt đầu từ Criteria rỗng.
2. Chỉ thêm điều kiện khi filter có giá trị.
3. Kết hợp các điều kiện theo AND.
4. Tạo Query từ Criteria cuối cùng.
5. Dùng JdbcAggregateTemplate để đọc aggregate.

Property trong Criteria là tên thuộc tính được ánh xạ của Product, ví dụ categoryId hoặc priceMinorUnits. Spring Data Relational xử lý chuyển đổi sang tên cột theo mapping context.

### 6.1. Null có nghĩa là không áp dụng bộ lọc

Trong ví dụ, status null có nghĩa caller không yêu cầu lọc theo status. Điều kiện status không được thêm.

Đây là một quy ước API cần ghi rõ. Nếu null có ý nghĩa “tìm các bản ghi có status SQL NULL”, hãy tạo Criteria isNull thay vì bỏ qua filter.

### 6.2. Phân biệt null, chuỗi rỗng và chuỗi chỉ có khoảng trắng

Với filter dạng text:

- null: không áp dụng filter.
- chuỗi rỗng: thường coi như không có từ khóa.
- chuỗi chỉ có khoảng trắng: thường trim rồi coi như không có từ khóa.
- chuỗi có nội dung: thêm điều kiện tìm kiếm.

Ví dụ:

~~~java
if (filter.nameContains() != null
        && !filter.nameContains().isBlank()) {
    String term = filter.nameContains().trim();
    criteria = criteria.and("name").like("%" + term + "%");
}
~~~

Nếu quy tắc tìm kiếm yêu cầu chuỗi rỗng là một giá trị có ý nghĩa, không được tự động bỏ qua.

### 6.3. Bộ lọc khoảng giá

Người dùng có thể chỉ nhập giá tối thiểu, chỉ nhập giá tối đa hoặc nhập cả hai:

~~~java
if (filter.minimumPrice() != null) {
    criteria = criteria.and("priceMinorUnits")
            .greaterThanOrEquals(filter.minimumPrice());
}

if (filter.maximumPrice() != null) {
    criteria = criteria.and("priceMinorUnits")
            .lessThanOrEquals(filter.maximumPrice());
}
~~~

Trước khi truy vấn, kiểm tra minimum không lớn hơn maximum:

~~~java
if (filter.minimumPrice() != null
        && filter.maximumPrice() != null
        && filter.minimumPrice() > filter.maximumPrice()) {
    throw new IllegalArgumentException(
            "Giá tối thiểu không được lớn hơn giá tối đa"
    );
}
~~~

Validation đầu vào giúp tránh truy vấn vô nghĩa và làm rõ contract API.

## 7. Bộ lọc IN và quy ước tập rỗng

Tập tham số rỗng là trường hợp cần quyết định rõ vì nó có thể mang hai ý nghĩa:

1. Caller không chọn bất kỳ giá trị nào nên muốn bỏ qua filter.
2. Caller chủ động cung cấp tập rỗng nên không có bản ghi nào được phép khớp.

Không nên để semantics phụ thuộc ngẫu nhiên vào cách framework hoặc database xử lý IN rỗng.

Ví dụ filter trạng thái:

~~~java
public record ProductFilter(List<String> statuses) {
}
~~~

Quy ước:

| Giá trị statuses | Ý nghĩa được chọn trong ví dụ |
| --- | --- |
| null | Không lọc theo trạng thái |
| Danh sách rỗng | Không có trạng thái nào được phép, trả kết quả rỗng |
| Danh sách có phần tử | Chỉ lấy trạng thái nằm trong tập |

Triển khai:

~~~java
if (filter.statuses() != null) {
    if (filter.statuses().isEmpty()) {
        return List.of();
    }
    criteria = criteria.and("status").in(filter.statuses());
}
~~~

Nếu API muốn quy ước danh sách rỗng là “bỏ qua filter”, hãy thực hiện điều đó có chủ đích và ghi trong hợp đồng. Không dùng cùng một cách xử lý cho mọi endpoint mà không xét ý nghĩa nghiệp vụ.

### 7.1. Loại bỏ phần tử null

Một danh sách trạng thái như:

~~~java
List.of("ACTIVE", null, "PENDING")
~~~

không hợp lệ với List.of và cũng không nên được dùng làm tập filter. Kiểm tra phần tử null trước khi tạo Criteria. Nếu null đại diện cho trạng thái SQL NULL, phải mô tả điều kiện đó bằng isNull hoặc một nhánh logic riêng.

### 7.2. Giới hạn kích thước tập IN

Danh sách ID rất lớn có thể tạo câu SQL có nhiều placeholder, vượt giới hạn database/driver hoặc làm truy vấn chậm. Hãy:

- Giới hạn số phần tử đầu vào.
- Chia lô nếu nghiệp vụ cho phép.
- Dùng bảng tạm/table-valued parameter hoặc cơ chế database phù hợp khi tập rất lớn.
- Đo execution plan và chi phí bind.

## 8. Tạo Query với sort, limit và offset

Query không chỉ mang Criteria mà còn có thể chứa tùy chọn sắp xếp và giới hạn kết quả.

Ví dụ:

~~~java
Query query = Query.query(criteria)
        .sort(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id")
        ))
        .limit(20)
        .offset(0);
~~~

Ý nghĩa:

- Sắp xếp theo createdAt giảm dần.
- Nếu createdAt trùng nhau, sắp xếp theo id tăng dần để có thứ tự ổn định.
- Chỉ lấy tối đa 20 kết quả.
- Bỏ qua 0 kết quả trước đó.

### 8.1. Whitelist thuộc tính sort

Nếu người dùng gửi sort field từ API, không nên truyền trực tiếp một chuỗi tùy ý vào Sort. Chỉ cho phép các property được hỗ trợ:

~~~java
Sort sort = switch (requestedSort) {
    case NEWEST -> Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.asc("id")
    );
    case PRICE_LOW_TO_HIGH -> Sort.by(
            Sort.Order.asc("priceMinorUnits"),
            Sort.Order.asc("id")
    );
    case NAME -> Sort.by(
            Sort.Order.asc("name"),
            Sort.Order.asc("id")
    );
};
~~~

Whitelist ngăn request yêu cầu sort theo property không tồn tại hoặc theo thuộc tính không được phép lộ ra.

### 8.2. Giới hạn page size

Không cho caller yêu cầu một page size vô hạn:

~~~java
int pageSize = Math.min(Math.max(requestedSize, 1), 100);
long offset = (long) page * pageSize;
~~~

Kiểu long cho offset giúp giảm nguy cơ overflow khi nhân page và pageSize. Cũng cần kiểm tra page không âm và giới hạn tổng số trang/offset theo nhu cầu ứng dụng.

### 8.3. Offset pagination và keyset pagination

Offset pagination dễ hiểu:

~~~java
Query query = Query.query(criteria)
        .sort(Sort.by(Sort.Order.asc("id")))
        .limit(pageSize)
        .offset((long) page * pageSize);
~~~

Khi offset rất lớn, database có thể phải duyệt/bỏ qua nhiều hàng trước khi trả trang. Keyset pagination thường hiệu quả hơn nếu có khóa sắp xếp ổn định:

~~~java
Criteria afterLastSeen = Criteria.where("id").greaterThan(lastSeenId);
Query query = Query.query(afterLastSeen)
        .sort(Sort.by(Sort.Order.asc("id")))
        .limit(pageSize);
~~~

Keyset cần kết hợp các filter ban đầu và điều kiện sau khóa cuối cùng. Ví dụ trên chỉ minh họa trường hợp đơn giản sắp xếp theo ID tăng dần. Nếu sort theo nhiều cột, cursor phải mang đủ giá trị để tạo điều kiện tiếp tục chính xác.

## 9. Dùng Query cho find, count, exists và delete

Một Criteria có thể được tái sử dụng để phục vụ các thao tác có mục đích khác nhau.

~~~java
Criteria criteria = Criteria.where("status").is("ACTIVE")
        .and("categoryId").is(categoryId);

Query query = Query.query(criteria);

List<Product> products = template.findAll(query, Product.class);
long count = template.count(query, Product.class);
boolean exists = template.exists(query, Product.class);
~~~

Các thao tác:

- findAll: trả danh sách aggregate phù hợp.
- count: trả số lượng aggregate phù hợp.
- exists: trả true nếu có kết quả.
- delete: xóa aggregate phù hợp.

### 9.1. Cẩn trọng với delete(Query)

Xóa theo Criteria có thể tác động đến nhiều aggregate. Trước khi gọi:

- Xác nhận điều kiện đủ hẹp.
- Kiểm tra số lượng bằng count nếu use case cần xác nhận.
- Đặt transaction phù hợp.
- Xem xét foreign key và quan hệ child.
- Kiểm tra chính sách lưu lịch sử/soft delete.

Không dùng Query có filter tùy chọn mà tất cả đều null rồi gọi delete. Criteria rỗng có thể dẫn đến phạm vi rất rộng tùy API và mapping. Với thao tác phá hủy dữ liệu, yêu cầu điều kiện bắt buộc rõ ràng và kiểm tra trước khi thực thi.

### 9.2. Count và findAll có thể tốn chi phí khác nhau

Nếu chỉ cần tổng số kết quả, dùng count thay vì tải toàn bộ aggregate rồi gọi size. Nếu chỉ cần biết có ít nhất một kết quả, dùng exists thay vì findAll.

Các thao tác này giúp database thực hiện công việc phù hợp hơn và tránh materialize object graph không cần thiết.

## 10. Tách filter request khỏi Criteria

Không nên để controller tạo Criteria trực tiếp từ request. Hãy dùng một object filter/criteria của ứng dụng để xác định semantics trước khi chuyển sang persistence DSL.

Ví dụ:

~~~java
public record ProductSearchRequest(
        String status,
        Long categoryId,
        Long minPrice,
        Long maxPrice,
        String keyword,
        Integer page,
        Integer size
) {
}
~~~

Service chuyển request thành filter đã validate:

~~~java
public record ProductSearchFilter(
        String status,
        Long categoryId,
        Long minPrice,
        Long maxPrice,
        String keyword
) {
}
~~~

Lợi ích:

- API không phụ thuộc trực tiếp vào Spring Data classes.
- Validation và semantics null/empty được đặt ở application boundary.
- Có thể thay cách truy vấn mà không đổi hợp đồng HTTP.
- Test filter logic không cần database.
- Cùng filter có thể được dùng trong nhiều query implementation.

### 10.1. Validation trước khi tạo Criteria

Ví dụ:

~~~java
private ProductSearchFilter validate(ProductSearchRequest request) {
    if (request.minPrice() != null
            && request.maxPrice() != null
            && request.minPrice() > request.maxPrice()) {
        throw new IllegalArgumentException("Khoảng giá không hợp lệ");
    }

    if (request.page() != null && request.page() < 0) {
        throw new IllegalArgumentException("page không được âm");
    }

    if (request.size() != null
            && (request.size() < 1 || request.size() > 100)) {
        throw new IllegalArgumentException("size phải từ 1 đến 100");
    }

    String keyword = request.keyword();
    if (keyword != null) {
        keyword = keyword.trim();
        if (keyword.isEmpty()) {
            keyword = null;
        }
    }

    return new ProductSearchFilter(
            request.status(),
            request.categoryId(),
            request.minPrice(),
            request.maxPrice(),
            keyword
    );
}
~~~

Sau khi validate, code dựng Criteria đơn giản hơn vì không phải xử lý lại dữ liệu sai hoặc trạng thái bất thường.

## 11. Tách bộ dựng Query thành thành phần riêng

Nếu một service có nhiều use case tìm kiếm, có thể tách logic tạo Query:

~~~java
public class ProductQueryFactory {

    public Query create(ProductSearchFilter filter, Sort sort,
                        int limit, long offset) {

        Criteria criteria = Criteria.empty();

        if (filter.status() != null) {
            criteria = criteria.and("status").is(filter.status());
        }

        if (filter.categoryId() != null) {
            criteria = criteria.and("categoryId").is(filter.categoryId());
        }

        if (filter.minPrice() != null) {
            criteria = criteria.and("priceMinorUnits")
                    .greaterThanOrEquals(filter.minPrice());
        }

        if (filter.maxPrice() != null) {
            criteria = criteria.and("priceMinorUnits")
                    .lessThanOrEquals(filter.maxPrice());
        }

        if (filter.keyword() != null) {
            criteria = criteria.and("name")
                    .like("%" + filter.keyword() + "%");
        }

        return Query.query(criteria)
                .sort(sort)
                .limit(limit)
                .offset(offset);
    }
}
~~~

Factory không thực thi SQL. Nó chỉ chuyển filter đã validate thành Query. Service hoặc custom repository chịu trách nhiệm gọi JdbcAggregateTemplate.

### 11.1. Unit test cho query factory

Có thể kiểm thử validation và lựa chọn filter riêng khỏi database. Tuy nhiên, việc kiểm tra object Criteria nội bộ có thể phụ thuộc API equals/toString của framework. Một cách đáng tin cậy là integration test kết quả truy vấn trên database với các fixture đại diện.

## 12. Criteria làm việc với property được ánh xạ

Khi viết:

~~~java
Criteria.where("priceMinorUnits").greaterThan(100_000L);
~~~

đối số thường là tên property trong entity domain model. Spring Data Relational dùng mapping context để chuyển property đó thành tên cột trong schema.

Ví dụ:

~~~java
@Table("products")
public class Product {

    @Id
    private Long id;

    @Column("price_minor_units")
    private long priceMinorUnits;
}
~~~

Criteria dùng:

~~~java
Criteria.where("priceMinorUnits").greaterThan(100_000L);
~~~

không nhất thiết dùng chuỗi price_minor_units. Nếu mapping property được tùy chỉnh bằng @Column, framework có thể chuyển property sang column đã khai báo.

### 12.1. Property không được ánh xạ

Một field @Transient không phải persistent property. Không thể dùng Criteria để lọc SQL theo một giá trị chỉ tồn tại trong bộ nhớ:

~~~java
@Transient
private String displayLabel;
~~~

Nếu cần lọc theo displayLabel, hãy xác định dữ liệu nguồn trong database hoặc biểu thức SQL phù hợp. Criteria không thể truy vấn một thuộc tính không có mapping lưu trữ.

### 12.2. Embedded value object

Với value object được nhúng bằng @Embedded, cách tham chiếu property con phụ thuộc mapping path và phiên bản Spring Data Relational. Hãy kiểm tra cách DSL hỗ trợ property path cho embedded object trong release đang dùng. Nếu đường dẫn không được hỗ trợ hoặc điều kiện phức tạp, cân nhắc query SQL rõ ràng.

## 13. Giới hạn của Criteria và Query

Query/Criteria không phải công cụ thay thế mọi câu SQL.

Thường phù hợp:

- Lọc aggregate root theo các property được ánh xạ.
- So sánh, khoảng giá trị, null, IN và LIKE.
- Kết hợp điều kiện.
- Sắp xếp và giới hạn kết quả.
- Count, exists, delete theo điều kiện.

Không nên giả định DSL có thể diễn đạt mọi tính năng SQL:

- Join tùy ý qua nhiều aggregate root.
- CTE phức tạp.
- Window function.
- Subquery lồng sâu.
- Biểu thức vendor-specific.
- Projection tổng hợp nhiều bảng phức tạp.
- Dynamic table/column identifier.

Khi cần những khả năng đó, dùng @Query hoặc custom repository với JdbcClient/NamedParameterJdbcTemplate. Lựa chọn theo hình dạng bài toán, không cố ép mọi truy vấn vào Criteria.

### 13.1. Query aggregate khác query báo cáo

JdbcAggregateTemplate làm việc với aggregate mapping. Một Query tìm Product sẽ trả Product aggregate theo mapping. Nếu cần kết quả join giữa Product, Category và Supplier thành một DTO, đó là read projection; dùng SQL/projection phù hợp thay vì kỳ vọng Query/Criteria tự dựng một join bất kỳ.

### 13.2. Không dùng Criteria để thay thế bảo vệ database

Criteria chỉ mô tả điều kiện ứng dụng gửi xuống database. Nó không thay thế:

- Primary key và unique constraint.
- Foreign key.
- Check constraint.
- Phân quyền truy cập.
- Validation nghiệp vụ.
- Transaction và optimistic locking.

Ví dụ kiểm tra SKU tồn tại trước khi insert không thay thế unique constraint trên SKU. Hai request đồng thời vẫn có thể cùng vượt qua bước kiểm tra.

## 14. Kết hợp Query/Criteria với transaction

Một truy vấn đọc đơn giản có thể được gọi từ service read-only:

~~~java
@Transactional(readOnly = true)
public List<Product> search(ProductSearchFilter filter) {
    Criteria criteria = buildCriteria(filter);
    Query query = Query.query(criteria);
    return template.findAll(query, Product.class);
}
~~~

Với thao tác nhiều bước, đặt transaction ở service boundary để các lệnh cùng datasource tham gia một transaction theo cấu hình.

Nếu dùng Query để delete:

~~~java
@Transactional
public void deleteDiscontinuedProducts() {
    Criteria criteria = Criteria.where("status").is("DISCONTINUED");
    Query query = Query.query(criteria);
    template.delete(query, Product.class);
}
~~~

Chỉ dùng ví dụ xóa khi điều kiện đã được xác định rõ và chính sách dữ liệu cho phép xóa. Nếu cần giữ lịch sử, dùng soft delete hoặc quy trình archive.

### 14.1. Read-only không phải bảo đảm snapshot tuyệt đối

@Transactional(readOnly = true) thể hiện ý định đọc. Mức nhất quán khi nhiều câu SQL được chạy phụ thuộc transaction isolation và database. Nếu use case yêu cầu snapshot nhất quán, chọn isolation level phù hợp và kiểm thử trên database mục tiêu.

## 15. Xử lý sort và filter an toàn

Criteria bind các giá trị điều kiện theo cơ chế framework. Tuy nhiên, API vẫn cần kiểm soát input:

- Không cho request chọn property bất kỳ để sort.
- Validate giới hạn số filter và số phần tử IN.
- Kiểm tra min/max.
- Xác định rõ null/empty.
- Chuẩn hóa chuỗi theo quy tắc domain.
- Không nhận raw SQL từ client.

Sort nên được ánh xạ từ enum:

~~~java
public enum ProductSort {
    NEWEST,
    NAME,
    PRICE_LOW_TO_HIGH
}
~~~

~~~java
private Sort toSort(ProductSort sort) {
    return switch (sort) {
        case NEWEST -> Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
        );
        case NAME -> Sort.by(
                Sort.Order.asc("name"),
                Sort.Order.asc("id")
        );
        case PRICE_LOW_TO_HIGH -> Sort.by(
                Sort.Order.asc("priceMinorUnits"),
                Sort.Order.asc("id")
        );
    };
}
~~~

Chỉ các property đã được lập trình viên cho phép mới có thể được dùng làm sort field. Thêm khóa phụ như id giúp thứ tự ổn định khi giá trị sort chính trùng nhau.

## 16. Kiểm thử bộ lọc động

Một integration test nên chuẩn bị các sản phẩm có trạng thái, danh mục và giá khác nhau, sau đó xác nhận từng tổ hợp filter.

Ví dụ dữ liệu:

| SKU | Status | Category | Price |
| --- | --- | ---: | ---: |
| BOOK-A | ACTIVE | 10 | 150000 |
| BOOK-B | ACTIVE | 10 | 300000 |
| PEN-A | ACTIVE | 20 | 20000 |
| BOOK-C | PENDING | 10 | 180000 |
| BOOK-D | ARCHIVED | 10 | 250000 |

Filter:

~~~java
ProductSearchFilter filter = new ProductSearchFilter(
        "ACTIVE",
        10L,
        100_000L,
        250_000L,
        "BOOK"
);
~~~

Kết quả kỳ vọng gồm BOOK-A. Test cần xác nhận:

- Từng điều kiện được áp dụng khi có giá trị.
- Điều kiện không được áp dụng khi filter là null theo contract.
- Min/max có bao gồm biên đúng không.
- Chuỗi tìm kiếm xử lý wildcard đúng ý định.
- Sort có thứ tự ổn định.
- Limit/offset trả đúng trang.
- Collection IN rỗng có semantics đã định.
- Root không có kết quả trả list rỗng.

### 16.1. Kiểm thử bằng database thật

Query/Criteria được chuyển thành SQL theo dialect. Dù DSL giảm phụ thuộc cú pháp, behavior vẫn có thể chịu ảnh hưởng của:

- Kiểu dữ liệu và collation.
- Null semantics.
- LIKE escape.
- Boolean representation.
- Limit/offset.
- Index và optimizer.

Với các truy vấn quan trọng, dùng integration test trên database production hoặc Testcontainers tương ứng. H2 hữu ích cho một số test nhanh nhưng không thay thế kiểm thử dialect thật khi có khác biệt.

### 16.2. Kiểm tra SQL được sinh

Trong môi trường test/dev, bật logging phù hợp hoặc dùng datasource proxy để quan sát:

- Cột và điều kiện WHERE.
- Parameter binding.
- ORDER BY.
- Limit/offset.
- Số query được phát ra.
- Query plan và index khi cần.

Không log dữ liệu nhạy cảm ở production nếu chưa có chính sách bảo vệ phù hợp.

## 17. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng tên cột SQL thay cho property mapping | Criteria không tìm được property hoặc mapping sai | Dùng tên property Java và xác nhận @Column/naming strategy |
| Thêm filter null như điều kiện bằng null | SQL semantics không như mong muốn | Bỏ filter hoặc dùng isNull theo contract |
| Truyền collection IN rỗng | SQL/semantics không rõ | Xử lý tập rỗng trước khi tạo Criteria |
| Ghép nhiều AND/OR mà không kiểm tra grouping | Điều kiện logic khác yêu cầu | Tách nhóm, kiểm tra SQL và viết integration test |
| Sort bằng property từ request | Property không hợp lệ hoặc mở rộng bề mặt tấn công | Dùng enum/whitelist |
| Dùng Criteria để join aggregate khác | DSL không đáp ứng join tùy ý | Dùng @Query hoặc custom JDBC |
| Dùng Query để trả DTO báo cáo phức tạp | Nhầm aggregate mapping với read projection | Viết SQL/projection riêng |
| Dùng delete(Query) với filter rỗng | Có thể xóa phạm vi quá rộng | Bắt buộc điều kiện an toàn và kiểm tra trước |
| Tải tất cả rồi lọc trong Java | Tốn bộ nhớ và database round-trip | Đưa điều kiện xuống Query/Criteria |
| Dùng offset rất lớn | Truy vấn chậm | Cân nhắc keyset pagination |
| Không kiểm tra kiểu filter | Driver/database chuyển đổi ngầm hoặc lỗi | Dùng kiểu tương thích với property |
| Nghĩ Criteria thay unique constraint | Dữ liệu trùng vẫn có thể xuất hiện đồng thời | Bảo vệ invariant ở database |

## 18. Quy trình xây dựng bộ lọc động

Khi triển khai một màn hình tìm kiếm:

1. **Định nghĩa filter contract.** Quy định null, chuỗi rỗng, tập rỗng và giá trị mặc định.
2. **Validate input.** Kiểm tra khoảng số, ngày, kích thước tập IN, page size và sort.
3. **Tạo Criteria.** Bắt đầu từ Criteria rỗng và thêm điều kiện theo filter đã validate.
4. **Kết hợp logic.** Dùng AND/OR có chủ đích; kiểm tra grouping cho biểu thức phức tạp.
5. **Tạo Query.** Gắn sort, limit và offset.
6. **Chọn thao tác.** findAll cho aggregate, count khi cần số lượng, exists khi chỉ cần boolean.
7. **Giữ đúng ranh giới.** Dùng Query/Criteria cho aggregate mapping; dùng SQL/projection cho join và báo cáo phức tạp.
8. **Quản lý transaction.** Đặt ranh giới service khi use case gồm nhiều thao tác.
9. **Kiểm thử semantics.** Có dữ liệu, không có dữ liệu, null, tập rỗng, biên và nhiều nhóm logic.
10. **Đo hiệu năng.** Quan sát SQL, index, execution plan và kích thước kết quả.

## Ghi nhớ

**Criteria** mô tả các điều kiện lọc trên thuộc tính được ánh xạ; **Query** kết hợp Criteria với sort, limit và offset; **JdbcAggregateTemplate** thực thi các thao tác tìm, đếm, kiểm tra tồn tại hoặc xóa aggregate theo Query.

Khi xây bộ lọc động, hãy thêm điều kiện chỉ khi filter có ý nghĩa, xác định rõ semantics của null và collection rỗng, whitelist sort field và kiểm tra grouping AND/OR. Query/Criteria phù hợp với truy vấn aggregate theo mapping. Khi cần join tùy ý, CTE, window function hoặc projection báo cáo phức tạp, dùng SQL tùy chỉnh hoặc custom repository. Cách phân chia này giúp bộ lọc linh hoạt mà vẫn giữ rõ aggregate boundary, kiểu dữ liệu và trách nhiệm của từng tầng.
