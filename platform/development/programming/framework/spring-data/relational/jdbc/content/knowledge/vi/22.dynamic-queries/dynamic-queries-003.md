# Nhóm điều kiện AND/OR theo yêu cầu tìm kiếm trong Spring Data JDBC

## 1. Vì sao cần nhóm điều kiện tìm kiếm?

Một màn hình tìm kiếm thường có nhiều bộ lọc tùy chọn. Người dùng có thể nhập từ khóa, chọn trạng thái, khoảng ngày, thành phố hoặc nhóm sản phẩm. Không phải bộ lọc nào cũng luôn có giá trị; một số bộ lọc còn cần kết hợp nhiều lựa chọn bằng OR.

Ví dụ, một yêu cầu tìm khách hàng có thể mang ý nghĩa:

- Khách hàng thuộc tenant đang đăng nhập.
- Khách hàng đang hoạt động.
- Từ khóa khớp với tên **hoặc** email **hoặc** mã khách hàng.
- Nếu người dùng chọn khu vực, khách hàng thuộc thành phố **hoặc** quận được chọn.

Biểu thức logic:

\[
tenant \land active \land (name \lor email \lor code) \land (city \lor district)
\]

Nếu bỏ ngoặc hoặc ghép điều kiện không đúng, kết quả có thể rộng hơn dự kiến. Ví dụ:

~~~sql
WHERE tenant_id = :tenantId
  AND active = TRUE
  AND display_name LIKE :keyword
   OR email_address LIKE :keyword
~~~

Trong SQL, AND có độ ưu tiên cao hơn OR. Biểu thức trên tương đương:

~~~sql
WHERE (tenant_id = :tenantId AND active = TRUE
       AND display_name LIKE :keyword)
   OR email_address LIKE :keyword
~~~

Một khách hàng ở tenant khác vẫn có thể xuất hiện nếu email khớp từ khóa. Cách viết đúng là nhóm các lựa chọn OR trong ngoặc:

~~~sql
WHERE tenant_id = :tenantId
  AND active = TRUE
  AND (
      display_name LIKE :keyword
      OR email_address LIKE :keyword
  )
~~~

Trong Spring Data JDBC, có thể xây dựng nhóm điều kiện động bằng Criteria API của Spring Data Relational, rồi truyền Query vào JdbcAggregateTemplate. Khi cần SQL tùy chỉnh hoàn toàn, có thể dùng NamedParameterJdbcTemplate và tự xây dựng các nhóm predicate có tham số.

## 2. AND và OR biểu diễn điều gì?

- **AND** yêu cầu tất cả điều kiện được kết hợp phải đúng.
- **OR** yêu cầu ít nhất một điều kiện trong nhóm phải đúng.
- **NOT** phủ định một điều kiện hoặc nhóm điều kiện.

| Biểu thức | Ý nghĩa |
|---|---|
| `status = 'ACTIVE' AND city = 'Hue'` | Khách hàng vừa hoạt động vừa ở Huế |
| `city = 'Hue' OR city = 'Da Nang'` | Khách hàng ở Huế hoặc Đà Nẵng |
| `tenant_id = ? AND (name LIKE ? OR email LIKE ?)` | Đúng tenant và tên hoặc email khớp |
| `(status = 'ACTIVE' OR status = 'PENDING') AND tenant_id = ?` | Một trong hai trạng thái và vẫn thuộc tenant |
| `NOT (status = 'DELETED' OR status = 'BLOCKED')` | Không thuộc hai trạng thái bị loại |

Trong một yêu cầu tìm kiếm, các nhóm thường kết hợp với nhau bằng AND, còn những lựa chọn thay thế bên trong một nhóm thường kết hợp bằng OR.

## 3. Derived query phù hợp với tổ hợp điều kiện cố định

Spring Data JDBC hỗ trợ derived query, trong đó framework phân tích tên method repository để tạo predicate:

~~~java
List<Customer> findByStatusAndCity(
        CustomerStatus status,
        String city
);

List<Customer> findByStatusOrCity(
        CustomerStatus status,
        String city
);

List<Customer> findByStatusAndCityOrStatusAndCity(
        CustomerStatus firstStatus,
        String firstCity,
        CustomerStatus secondStatus,
        String secondCity
);
~~~

Cách này phù hợp khi số tổ hợp điều kiện ít và ổn định. Nhưng khi mỗi request có thể bật/tắt nhiều bộ lọc, số method cần định nghĩa tăng nhanh. Với 6 bộ lọc tùy chọn, mỗi bộ lọc có thể có hoặc không, số tổ hợp khả dĩ là:

\[
2^6 = 64
\]

Không nên tạo hàng chục method chỉ để bao phủ mọi tổ hợp. Với điều kiện động, hãy xây dựng predicate tại runtime bằng Criteria API hoặc custom SQL.

Một lưu ý: derived query dùng property Java, chẳng hạn `findByCustomerCode`. Criteria API làm việc với tên cột relational trong query mapping. Hãy dùng tên cột nhất quán với schema và mapping `@Column` của entity.

## 4. Criteria API trong Spring Data Relational

Spring Data Relational cung cấp `Criteria` và `Query` để mô tả điều kiện truy vấn bằng Java. Đây là lựa chọn phù hợp khi cần lắp ghép AND/OR tùy theo filter của request.

Các import thường dùng:

~~~java
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
~~~

`Criteria.where("column")` bắt đầu một điều kiện trên cột. Các phép so sánh như `is`, `like`, `greaterThan`, `between` và `isNull` tạo predicate. Có thể nối điều kiện bằng `and(...)` và `or(...)`.

Ví dụ:

~~~java
Criteria criteria = Criteria.where("status").is("ACTIVE")
        .and("city").is("Hue");
~~~

Điều kiện trên tương ứng:

~~~sql
WHERE status = 'ACTIVE'
  AND city = 'Hue'
~~~

Nhóm OR:

~~~java
Criteria criteria = Criteria.where("city").is("Hue")
        .or("city").is("Da Nang");
~~~

Tương ứng:

~~~sql
WHERE city = 'Hue'
   OR city = 'Da Nang'
~~~

Có thể truyền một Criteria khác vào `and(...)` hoặc `or(...)` để kết hợp cả nhóm như một đơn vị logic. Đây là cách tạo ngoặc cho các biểu thức lồng nhau.

## 5. Đưa một nhóm OR vào trong điều kiện AND

Giả sử cần tìm khách hàng thuộc tenant hiện tại, đang hoạt động, và tên hoặc email khớp từ khóa.

SQL mong muốn:

~~~sql
SELECT id, tenant_id, customer_code, display_name, email_address, status
FROM customers
WHERE tenant_id = :tenantId
  AND status = :status
  AND (
      display_name LIKE :pattern
      OR email_address LIKE :pattern
  );
~~~

Dùng Criteria:

~~~java
Criteria textMatch = Criteria.where("display_name").like(pattern)
        .or("email_address").like(pattern);

Criteria criteria = Criteria.where("tenant_id").is(tenantId)
        .and("status").is("ACTIVE")
        .and(textMatch);
~~~

Ở đây `textMatch` là nhóm OR độc lập. Khi đưa nó vào `criteria.and(textMatch)`, toàn bộ nhóm phải đúng cùng với điều kiện tenant và status.

Có thể đọc biểu thức theo cấu trúc:

~~~text
AND
├── tenant_id = tenantId
├── status = ACTIVE
└── OR
    ├── display_name LIKE pattern
    └── email_address LIKE pattern
~~~

Không nên viết ba điều kiện rời rồi nối bằng OR ở cấp ngoài cùng, vì điều đó có thể làm mất ràng buộc tenant hoặc trạng thái.

## 6. Nhóm nhiều lựa chọn OR và nhiều nhóm AND

Một tìm kiếm thực tế có thể gồm nhiều nhóm:

~~~text
tenant_id = tenant hiện tại
AND status = ACTIVE
AND (
    display_name chứa keyword
    OR email_address chứa keyword
    OR customer_code chứa keyword
)
AND (
    city = cityFilter
    OR district = districtFilter
)
AND created_at >= fromDate
AND created_at < untilDate
~~~

Có thể xây dựng từng nhóm riêng:

~~~java
Criteria keywordGroup = Criteria.where("display_name").like(pattern)
        .or("email_address").like(pattern)
        .or("customer_code").like(pattern);

Criteria locationGroup = Criteria.where("city").is(city)
        .or("district").is(district);

Criteria criteria = Criteria.where("tenant_id").is(tenantId)
        .and("status").is("ACTIVE")
        .and(keywordGroup)
        .and(locationGroup)
        .and("created_at").greaterThanOrEquals(fromDate)
        .and("created_at").lessThan(untilDate);
~~~

Cấu trúc logic:

\[
tenant \land active \land (name \lor email \lor code)
\land (city \lor district) \land from \le createdAt < until
\]

Trong ứng dụng thật, không phải nhóm nào cũng luôn có mặt. Nếu keyword trống, bỏ toàn bộ keywordGroup. Nếu người dùng không chọn địa điểm, bỏ locationGroup. Không tạo điều kiện so sánh với chuỗi rỗng hoặc giá trị null ngoài ý muốn.

## 7. Xây dựng Criteria động từ filter tùy chọn

Tạo DTO mô tả yêu cầu tìm kiếm:

~~~java
import java.time.Instant;

public record CustomerSearchFilter(
        String status,
        String keyword,
        String city,
        String district,
        String postalCode,
        Instant createdFrom,
        Instant createdUntil,
        int limit
) {}
~~~

Một custom repository có thể nhận filter, tạo Criteria rồi dùng `JdbcAggregateTemplate`:

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerSearchRepository {

    private final JdbcAggregateTemplate template;

    public CustomerSearchRepository(JdbcAggregateTemplate template) {
        this.template = template;
    }

    public List<Customer> search(
            UUID tenantId,
            CustomerSearchFilter filter
    ) {
        Criteria criteria = Criteria.where("tenant_id").is(tenantId);

        if (filter.status() != null && !filter.status().isBlank()) {
            criteria = criteria.and("status").is(filter.status());
        }

        if (filter.keyword() != null && !filter.keyword().isBlank()) {
            String pattern = "%" + filter.keyword().trim() + "%";

            Criteria keywordGroup =
                    Criteria.where("display_name").like(pattern)
                            .or("email_address").like(pattern)
                            .or("customer_code").like(pattern);

            criteria = criteria.and(keywordGroup);
        }

        if (filter.city() != null && !filter.city().isBlank()
                && filter.district() != null && !filter.district().isBlank()) {
            Criteria locationGroup =
                    Criteria.where("city").is(filter.city())
                            .or("district").is(filter.district());

            criteria = criteria.and(locationGroup);
        } else if (filter.city() != null && !filter.city().isBlank()) {
            criteria = criteria.and("city").is(filter.city());
        } else if (filter.district() != null && !filter.district().isBlank()) {
            criteria = criteria.and("district").is(filter.district());
        }

        if (filter.createdFrom() != null) {
            criteria = criteria.and("created_at")
                    .greaterThanOrEquals(filter.createdFrom());
        }

        if (filter.createdUntil() != null) {
            criteria = criteria.and("created_at")
                    .lessThan(filter.createdUntil());
        }

        int limit = Math.max(1, Math.min(filter.limit(), 200));
        Query query = Query.query(criteria).limit(limit);

        return template.findAll(query, Customer.class);
    }
}
~~~

Ví dụ bắt đầu bằng điều kiện tenant bắt buộc. Những điều kiện khác chỉ được thêm khi filter có giá trị hợp lệ. Điều này giúp đảm bảo mọi truy vấn đều bị giới hạn theo tenant, kể cả khi client không gửi từ khóa.

`JdbcAggregateTemplate` thực thi Query theo metadata của aggregate. Các tên cột trong Criteria phải khớp với schema và mapping relational của ứng dụng; nếu entity dùng `@Column`, hãy dùng đúng tên cột đã ánh xạ. API cụ thể có thể khác theo phiên bản Spring Data JDBC đang dùng.

### 7.1. Vì sao phải khởi tạo từ điều kiện bắt buộc?

Nếu bắt đầu từ một filter tùy chọn rồi vô tình không thêm điều kiện nào, ứng dụng có thể truy vấn toàn bảng. Trong hệ thống multi-tenant, điều kiện tenant thường phải được thêm trước tất cả filter do client cung cấp.

Mẫu an toàn:

~~~java
Criteria criteria = Criteria.where("tenant_id").is(authenticatedTenantId);

// Chỉ thêm filter tùy chọn sau điều kiện tenant.
if (status != null) {
    criteria = criteria.and("status").is(status);
}
~~~

`authenticatedTenantId` cần lấy từ security context hoặc session đã xác thực ở server. Không dùng tenant ID do client tự gửi mà chưa kiểm tra quyền truy cập.

### 7.2. Phân biệt filter không gửi và yêu cầu tìm NULL

Hai trường hợp này có ý nghĩa khác nhau:

- `email == null` trong DTO có thể có nghĩa người dùng không lọc theo email.
- `email IS NULL` là một điều kiện tìm kiếm cụ thể.

Nếu API cần hỗ trợ tìm những hàng có email NULL, hãy biểu diễn ý định đó riêng (ví dụ một cờ `emailIsNull`) và thêm:

~~~java
criteria = criteria.and("email_address").isNull();
~~~

Không diễn giải mọi giá trị null trong filter thành `IS NULL`; nếu làm vậy, việc bỏ trống một field sẽ vô tình loại phần lớn dữ liệu.

## 8. Tạo nhóm OR từ danh sách điều kiện

Đôi khi số lựa chọn OR không cố định. Ví dụ người dùng chọn nhiều trạng thái, nhiều thành phố hoặc nhiều loại sự kiện.

Với một tập trạng thái, cách đơn giản nhất thường là toán tử `in`:

~~~java
Criteria criteria = Criteria.where("status").in(statuses);
~~~

Điều này tương ứng `status IN (...)` và thường rõ nghĩa hơn nối nhiều điều kiện OR cùng cột.

Nếu các điều kiện OR nằm trên nhiều cột hoặc mỗi điều kiện có giá trị khác nhau, có thể tạo danh sách Criteria rồi gộp:

~~~java
import java.util.ArrayList;
import java.util.List;

List<Criteria> alternatives = new ArrayList<>();

if (filter.city() != null && !filter.city().isBlank()) {
    alternatives.add(Criteria.where("city").is(filter.city()));
}

if (filter.district() != null && !filter.district().isBlank()) {
    alternatives.add(Criteria.where("district").is(filter.district()));
}

if (filter.postalCode() != null && !filter.postalCode().isBlank()) {
    alternatives.add(Criteria.where("postal_code").is(filter.postalCode()));
}

if (!alternatives.isEmpty()) {
    Criteria locationGroup = alternatives.get(0);

    for (int i = 1; i < alternatives.size(); i++) {
        locationGroup = locationGroup.or(alternatives.get(i));
    }

    criteria = criteria.and(locationGroup);
}
~~~

Nhóm locationGroup chỉ được thêm nếu có ít nhất một lựa chọn. Không nên tạo OR group rỗng. Với một tập giá trị trên cùng một cột, ưu tiên `IN` vì ngắn gọn và biểu đạt trực tiếp ý nghĩa.

## 9. Nhóm điều kiện AND động

Tương tự, có thể xây dựng điều kiện bắt buộc hoặc điều kiện tùy chọn bằng cách nối `and(...)`:

~~~java
Criteria criteria = Criteria.where("tenant_id").is(tenantId);

if (filter.status() != null) {
    criteria = criteria.and("status").is(filter.status());
}

if (filter.createdFrom() != null) {
    criteria = criteria.and("created_at")
            .greaterThanOrEquals(filter.createdFrom());
}

if (filter.createdUntil() != null) {
    criteria = criteria.and("created_at")
            .lessThan(filter.createdUntil());
}
~~~

Nếu tất cả filter đều được gửi, predicate là giao của tất cả điều kiện. Nếu một filter không được gửi, điều kiện tương ứng không xuất hiện trong query.

Cần phân biệt việc bỏ qua một filter với việc thay filter bằng một giá trị mặc định. Ví dụ, không có status thường có nghĩa là không giới hạn trạng thái; không nên tự gán ACTIVE trừ khi đó là quy tắc sản phẩm.

## 10. Dùng Query và JdbcAggregateTemplate để thực thi

Sau khi tạo Criteria, đóng gói nó thành Query:

~~~java
Query query = Query.query(criteria);
List<Customer> result = template.findAll(query, Customer.class);
~~~

Có thể thêm giới hạn kết quả để tránh trả về tập dữ liệu quá lớn:

~~~java
Query query = Query.query(criteria).limit(100);
~~~

Với truy vấn chỉ đọc, service có thể đặt transaction read-only:

~~~java
@Service
public class CustomerSearchService {

    private final CustomerSearchRepository repository;

    public CustomerSearchService(CustomerSearchRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<Customer> search(
            UUID tenantId,
            CustomerSearchFilter filter
    ) {
        return repository.search(tenantId, filter);
    }
}
~~~

Nếu kết quả cần sắp xếp, phân trang hoặc projection phức tạp, kiểm tra khả năng của Query trong phiên bản đang sử dụng. Khi query vượt quá khả năng biểu đạt thuận tiện của Criteria, có thể chuyển sang custom SQL thay vì cố tạo một cây Criteria quá khó đọc.

## 11. Khi cần SQL tùy chỉnh: NamedParameterJdbcTemplate

Một lựa chọn khác là xây dựng predicate SQL trong code và bind mọi giá trị bằng named parameter. Cách này phù hợp khi cần cú pháp SQL đặc thù, nhiều nhóm ngoặc hoặc query có join phức tạp.

Ví dụ:

~~~java
public List<Customer> search(UUID tenantId, CustomerSearchFilter filter) {
    StringBuilder sql = new StringBuilder("""
            SELECT id, tenant_id, customer_code, display_name,
                   email_address, status, city, district, created_at
            FROM customers
            WHERE tenant_id = :tenantId
            """);

    MapSqlParameterSource params = new MapSqlParameterSource()
            .addValue("tenantId", tenantId);

    if (filter.status() != null && !filter.status().isBlank()) {
        sql.append(" AND status = :status");
        params.addValue("status", filter.status());
    }

    if (filter.keyword() != null && !filter.keyword().isBlank()) {
        sql.append("""
                 AND (
                     display_name LIKE :pattern
                     OR email_address LIKE :pattern
                     OR customer_code LIKE :pattern
                 )
                """);

        params.addValue(
                "pattern",
                "%" + filter.keyword().trim() + "%"
        );
    }

    if (filter.createdFrom() != null) {
        sql.append(" AND created_at >= :createdFrom");
        params.addValue("createdFrom", filter.createdFrom());
    }

    if (filter.createdUntil() != null) {
        sql.append(" AND created_at < :createdUntil");
        params.addValue("createdUntil", filter.createdUntil());
    }

    sql.append(" ORDER BY created_at DESC, id DESC LIMIT :limit");
    params.addValue("limit", Math.max(1, Math.min(filter.limit(), 200)));

    return namedParameterJdbcTemplate.query(
            sql.toString(),
            params,
            customerRowMapper
    );
}
~~~

Các mảnh SQL được thêm vào đều là chuỗi cố định do code kiểm soát. Dữ liệu từ người dùng chỉ được truyền qua parameter như `:status`, `:pattern` và `:createdFrom`.

**Không nối trực tiếp giá trị người dùng vào SQL.** Prepared/named parameters bảo vệ giá trị dữ liệu, nhưng không thể bind tên bảng, tên cột hoặc từ khóa SQL. Nếu cần sort động, ánh xạ lựa chọn của client qua allowlist:

~~~java
String orderBy = switch (requestedSort) {
    case "name" -> "display_name";
    case "createdAt" -> "created_at";
    default -> "id";
};
~~~

Chỉ các fragment cố định đã được allowlist mới được đưa vào câu SQL. Không dùng requestedSort trực tiếp trong ORDER BY.

### 11.1. Khi nào chọn Criteria, khi nào chọn SQL?

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Filter động trên một aggregate, điều kiện cột phổ biến | Criteria + Query |
| Nhóm AND/OR lồng nhau vừa phải | Criteria với nested Criteria |
| Truy vấn cần join, CTE hoặc window function | SQL tùy chỉnh |
| Predicate cần biểu thức database riêng | SQL tùy chỉnh |
| Cần tận dụng mapping và aggregate template | JdbcAggregateTemplate |
| Cần kiểm soát từng cột SELECT và RowMapper | NamedParameterJdbcTemplate |

Với SQL template, ứng dụng phải tự duy trì mapping ResultSet, kiểu dữ liệu, null handling và quy tắc tenant. `@Column` trên entity không tự động cấu hình một RowMapper viết thủ công.

## 12. Quy tắc nhóm ngoặc và thứ tự ưu tiên

SQL ưu tiên AND trước OR. Dù biết quy tắc này, hãy viết ngoặc tường minh cho mọi nhóm OR trong truy vấn nghiệp vụ. Điều đó giúp người đọc nhận ra ý định và tránh lỗi khi thêm điều kiện mới.

Ví dụ yêu cầu:

~~~text
(status = ACTIVE OR status = PENDING)
AND tenant_id = currentTenant
AND (city = Hue OR district = Hai Chau)
~~~

SQL:

~~~sql
WHERE (status = 'ACTIVE' OR status = 'PENDING')
  AND tenant_id = :tenantId
  AND (city = :city OR district = :district)
~~~

Criteria:

~~~java
Criteria statusGroup = Criteria.where("status").is("ACTIVE")
        .or("status").is("PENDING");

Criteria locationGroup = Criteria.where("city").is("Hue")
        .or("district").is("Hai Chau");

Criteria criteria = statusGroup
        .and("tenant_id").is(tenantId)
        .and(locationGroup);
~~~

Hai nhóm OR được xây dựng riêng, sau đó nối với các điều kiện AND. Đây là cách làm dễ đọc hơn việc viết một chuỗi dài gồm nhiều OR và AND xen kẽ.

## 13. Các trường hợp biên cần quyết định rõ

### 13.1. Từ khóa rỗng

Nếu keyword null hoặc chỉ chứa khoảng trắng, thông thường nên bỏ nhóm tìm kiếm keyword. Không nên tạo pattern `%%` trừ khi muốn nó khớp mọi chuỗi và đã chấp nhận chi phí truy vấn.

### 13.2. Collection rỗng

Với filter dạng danh sách, cần xác định ý nghĩa của danh sách rỗng:

- Không chọn trạng thái nào có thể có nghĩa là không lọc trạng thái.
- Một danh sách được gửi rõ ràng nhưng rỗng có thể có nghĩa là không có giá trị nào được phép.

Hai semantics này khác nhau. Hãy phân biệt “field không được gửi” và “field được gửi với danh sách rỗng” trong DTO/API. Không xây dựng `IN ()` khi không có phần tử.

### 13.3. Giá trị NULL

Không thêm điều kiện `isNull()` chỉ vì tham số filter là null. Chỉ dùng `isNull()` khi người dùng thực sự chọn lọc các hàng có giá trị NULL.

### 13.4. Ký tự wildcard

Với `LIKE`, `%` và `_` có ý nghĩa wildcard trong SQL. Nếu tìm kiếm theo chuỗi literal, cần có chính sách escape thống nhất. Nếu muốn người dùng nhập pattern, hãy nói rõ `%` và `_` được hiểu như wildcard.

### 13.5. Tenant và quyền truy cập

Tenant, owner và quyền truy cập phải được thêm từ server-side security context. Không cho phép một OR group do client điều khiển làm điều kiện tenant trở thành tùy chọn.

### 13.6. Khoảng thời gian

Với khoảng thời gian, thường nên dùng dạng nửa mở:

~~~sql
created_at >= :from
AND created_at < :until
~~~

Điều này giúp hai khoảng liên tiếp không trùng nhau tại ranh giới. Thống nhất timezone và kiểu Java/SQL khi truyền timestamp.

## 14. Hiệu năng của nhóm AND/OR

Cấu trúc Criteria giúp tạo predicate chính xác, nhưng không tự bảo đảm query nhanh. Database cần đánh giá các điều kiện dựa trên index và statistics.

Một số nguyên tắc:

- Tạo index cho các filter được dùng thường xuyên sau khi xem workload.
- Với tenant-scoped query, index bắt đầu bằng tenant key có thể hữu ích.
- OR trên nhiều cột có thể làm planner khó chọn index tối ưu hơn so với một predicate đơn.
- `LIKE '%keyword%'` thường khó tận dụng B-tree index thông thường; cân nhắc full-text search, trigram hoặc search engine nếu yêu cầu tìm kiếm lớn.
- Không tạo index cho mọi tổ hợp filter; index làm tăng chi phí ghi và dung lượng.
- Kiểm tra query plan trên database thật với dữ liệu có phân bố gần production.

Ví dụ một index hỗ trợ truy vấn theo tenant và status:

~~~sql
CREATE INDEX idx_customers_tenant_status
ON customers (tenant_id, status);
~~~

Nếu thường tìm theo tenant và thời gian:

~~~sql
CREATE INDEX idx_customers_tenant_created
ON customers (tenant_id, created_at);
~~~

Các index trên chỉ là ví dụ. Chọn index dựa trên truy vấn thực tế, selectivity, thứ tự sort và chi phí ghi.

## 15. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Kết quả chứa tenant khác | OR không được nhóm trong ngoặc cùng điều kiện tenant | Tạo nhóm OR riêng rồi AND vào predicate chính |
| Kết quả rộng hơn dự kiến | Nhầm ưu tiên AND/OR | Viết ngoặc tường minh và kiểm thử truth table |
| Filter null làm mất kết quả | Null bị chuyển thành IS NULL dù ý định là bỏ qua filter | Chỉ thêm predicate khi filter được cung cấp rõ |
| Không tìm thấy dữ liệu theo tên cột | Nhầm property Java với cột vật lý trong Criteria/SQL | Kiểm tra @Column và dùng tên cột đúng |
| Criteria động không có điều kiện | Không khởi tạo predicate bắt buộc hoặc nhóm rỗng | Bắt đầu bằng tenant/scope bắt buộc và chỉ thêm nhóm OR không rỗng |
| IN với danh sách rỗng gây lỗi hoặc semantics sai | Không xác định ý nghĩa của collection rỗng | Xử lý riêng trước khi tạo Criteria |
| LIKE trả quá nhiều kết quả | % và _ trong input được hiểu là wildcard | Escape hoặc quy định rõ pattern semantics |
| Query động bị SQL injection | Nối giá trị request vào SQL | Bind mọi giá trị bằng parameter |
| Sort động bị khai thác | Đưa trực tiếp tên cột từ request vào SQL | Dùng allowlist tên cột/sort direction |
| Query chậm khi có nhiều OR | Index/query plan không phù hợp hoặc tìm contains | Dùng EXPLAIN, cân nhắc full-text/trigram |
| Filter tenant bị thiếu ở một nhánh | Lắp ghép predicate không có cấu trúc | Thêm tenant ở ngoài cùng bằng AND |
| Query Criteria khó bảo trì | Một biểu thức lồng quá nhiều nhóm | Tách mỗi nhóm thành biến Criteria có tên |

## 16. Bài tập thực hành

### Bài 1 — AND cơ bản

Tạo tìm kiếm khách hàng theo tenant và status. Dùng Criteria để thêm điều kiện status khi filter được gửi. Xác nhận khi status null thì chỉ còn điều kiện tenant.

### Bài 2 — OR trong một nhóm AND

Tạo yêu cầu tìm theo tenant và keyword. Keyword có thể khớp display_name, email_address hoặc customer_code. Dùng một nhóm OR và AND nhóm đó vào điều kiện tenant.

### Bài 3 — Hai nhóm OR

Mở rộng tìm kiếm để có nhóm keyword và nhóm địa điểm. Viết biểu thức logic và SQL có ngoặc trước khi chuyển thành Criteria.

### Bài 4 — Nhóm OR động

Cho phép chọn nhiều loại liên hệ hoặc nhiều địa điểm. Xây dựng danh sách Criteria, gộp bằng OR và chỉ thêm nhóm khi danh sách không rỗng.

### Bài 5 — Criteria và custom SQL

Triển khai cùng một filter bằng Criteria/JdbcAggregateTemplate và NamedParameterJdbcTemplate. So sánh khả năng đọc, kiểm soát SQL và trách nhiệm mapping.

### Bài 6 — Kiểm thử logic

Tạo dữ liệu ở hai tenant, nhiều trạng thái và nhiều email/tên. Kiểm tra các tổ hợp để xác nhận không có hàng ngoài tenant xuất hiện khi nhóm OR khớp.

### Bài 7 — Hiệu năng

Bật SQL logging, kiểm tra query plan cho nhóm AND/OR. Thử index theo tenant/status và đánh giá tác động của LIKE chứa từ khóa.

## 17. Ghi nhớ

- AND kết hợp các điều kiện bắt buộc cùng đúng; OR kết hợp các lựa chọn thay thế.
- Luôn nhóm OR bằng ngoặc logic trước khi kết hợp với điều kiện AND bên ngoài.
- Derived query phù hợp với tổ hợp cố định; filter động nên dùng Criteria/Query hoặc custom SQL.
- Criteria có thể được ghép lồng bằng `and(Criteria)` và `or(Criteria)` để thể hiện các nhóm logic.
- Trong ví dụ Criteria, dùng tên cột theo schema và mapping `@Column`; derived query lại dùng property Java.
- Bắt đầu từ điều kiện tenant/security bắt buộc rồi mới thêm filter tùy chọn.
- Phân biệt filter không được gửi, filter có giá trị NULL và collection rỗng.
- Khi dùng SQL động, chỉ ghép các fragment cố định do ứng dụng kiểm soát và bind mọi giá trị bằng parameter.
- Criteria không thay thế việc đo query plan; index, collation và dạng LIKE ảnh hưởng lớn đến hiệu năng.
