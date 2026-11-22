# Cô lập phần phụ thuộc provider và SQL đặc thù khi thiết kế Repository

Trong ứng dụng dùng JPA, Repository thường được xem là lớp che giấu thao tác truy cập dữ liệu. Tuy nhiên, chỉ đặt mọi câu truy vấn vào một interface có tên Repository chưa đủ để tách ứng dụng khỏi công nghệ lưu trữ. Một phương thức có chữ ký đẹp vẫn có thể phụ thuộc vào Hibernate, cú pháp PostgreSQL, kiểu dữ liệu Oracle, hàm SQL độc quyền hoặc giả định về cách cơ sở dữ liệu xử lý khóa.

Mục tiêu của việc **cô lập phần phụ thuộc provider và SQL đặc thù** là giữ cho nghiệp vụ diễn đạt *cần lấy hoặc thay đổi dữ liệu gì*, còn lớp hạ tầng quyết định *thực hiện bằng JPA provider, SQL dialect và JDBC driver nào*. Khi đổi provider hoặc hệ quản trị cơ sở dữ liệu (DBMS), phần lớn thay đổi phải nằm trong các adapter và cấu hình persistence có phạm vi rõ ràng.

## 1. Nhận diện chính xác loại phụ thuộc

Hai khái niệm dễ bị nhầm là:

- **JPA provider:** thư viện hiện thực Jakarta Persistence, chẳng hạn Hibernate ORM hoặc EclipseLink. Provider quản lý persistence context, dirty checking, lazy loading, tạo SQL và hiện thực các quy tắc JPA.
- **Database/SQL dialect:** hệ quy tắc và cú pháp mà cơ sở dữ liệu hỗ trợ, chẳng hạn PostgreSQL hoặc Oracle. Dialect của Hibernate giúp Hibernate sinh SQL phù hợp, nhưng không tự chuyển đổi mọi câu *native SQL do lập trình viên viết*.

Một ứng dụng có thể phải đổi Hibernate sang EclipseLink mà vẫn dùng PostgreSQL, hoặc giữ Hibernate nhưng chuyển từ PostgreSQL sang Oracle. Đây là hai trục thay đổi khác nhau.

| Thành phần | Ví dụ | Phạm vi phụ thuộc và hướng xử lý |
| --- | --- | --- |
| Jakarta Persistence chuẩn | EntityManager, JPQL, Criteria API, LockModeType | Thường tương thích giữa các provider, nhưng vẫn phải kiểm tra hành vi và SQL sinh ra |
| Tính năng riêng của provider | Hibernate Session, @Formula, @JdbcTypeCode, proprietary query hints | Giữ bên trong persistence adapter hoặc mapping hạ tầng |
| Native SQL riêng của DBMS | ILIKE, ON CONFLICT, MERGE, RETURNING, FETCH FIRST | Đặt trong adapter hoặc chiến lược SQL theo DBMS |
| Kiểu dữ liệu riêng | PostgreSQL jsonb, ARRAY; Oracle-specific object types | Chuyển thành kiểu dữ liệu và hợp đồng trung lập tại ranh giới Repository |
| DDL, chỉ mục, migration | GIN index, function-based index, sequence, identity | Quản lý theo database migration tương ứng |
| Lỗi và xử lý giao dịch | SQLSTATE, mã lỗi Oracle, deadlock, unique constraint | Phân loại ở hạ tầng, trả về lỗi ứng dụng có ý nghĩa |

**Không nên hứa tính di động tuyệt đối.** JPA chuẩn giúp giảm phụ thuộc, nhưng không đồng nhất collation, độ chính xác số và thời gian, mức cô lập giao dịch, cơ chế khóa hay kế hoạch thực thi giữa các hệ CSDL.

## 2. Đặt ranh giới giữa nghiệp vụ và persistence

Một cách tổ chức dễ bảo trì là tách **port** (hợp đồng nghiệp vụ cần) khỏi **adapter** (cách đọc/ghi dữ liệu):

~~~text
Application Service
       |
       v
OrderReportReader (port thuộc application/domain)
       |
       +-- JpaOrderReportReader   -> EntityManager -> JPA provider
       |
       +-- JdbcOrderReportReader  -> OrderPageSql  -> SQL PostgreSQL
                                                   -> SQL Oracle
~~~

Ví dụ hệ thống cần đọc các đơn hàng gần nhất của một khách hàng:

~~~java
package com.example.orders.application;

import java.util.List;

public record OrderRow(long id, String status) {}

public interface OrderReportReader {
    List<OrderRow> findRecent(long customerId, int offset, int limit);
}
~~~

Interface trên chỉ nói về yêu cầu đọc. Nó không lộ EntityManager, Hibernate Session, java.sql.ResultSet, PGobject hay kiểu dữ liệu của Oracle. Đối tượng trả về là projection phục vụ use case, không nhất thiết là entity có trạng thái managed.

Trong dự án dùng Spring Data JPA, có thể tiếp tục giữ interface kỹ thuật riêng:

~~~java
package com.example.orders.infrastructure.jpa;

import org.springframework.data.jpa.repository.JpaRepository;

interface SpringDataOrderRepository
        extends JpaRepository<OrderEntity, Long> {

    boolean existsByCustomerIdAndStatus(long customerId, String status);
}
~~~

Interface Spring Data này thuộc **infrastructure**. Application Service gọi port nghiệp vụ, còn adapter có thể sử dụng SpringDataOrderRepository hoặc EntityManager để thực hiện. Nếu một ứng dụng chỉ có CRUD đơn giản và không có yêu cầu thay đổi adapter, sử dụng trực tiếp Spring Data trong tầng application cũng là lựa chọn thực dụng; cần hiểu rõ mức phụ thuộc được chấp nhận thay vì tạo nhiều abstraction rỗng.

### Nguyên tắc thiết kế hợp đồng

1. Đặt tên phương thức theo nhu cầu nghiệp vụ: findRecent, reserveStock, findEligibleInvoices; tránh đặt theo kỹ thuật như executeNativePostgresQuery.
2. Dùng kiểu tham số, kết quả và lỗi mà caller hiểu. Các kiểu JDBC, provider hoặc database không đi qua ranh giới port.
3. Xác định rõ ý nghĩa của thứ tự, phân trang, xử lý null, timezone, tính duy nhất và độ nhất quán. Đây là phần hợp đồng cần được bảo toàn khi đổi adapter.
4. Không tạo một port khổng lồ cho mọi thao tác. Chia các nhóm truy vấn có nhu cầu và mức tối ưu khác nhau.
5. Giữ transaction boundary ở use case/service khi một giao dịch bao trùm nhiều thao tác; adapter chịu trách nhiệm câu lệnh và mapping dữ liệu.

## 3. Ưu tiên JPA chuẩn cho truy vấn phổ thông

Nếu truy vấn biểu diễn được bằng JPQL hoặc Criteria API, hãy ưu tiên cách đó trước khi đưa native SQL vào code. Ví dụ adapter dùng EntityManager:

~~~java
package com.example.orders.infrastructure.jpa;

import com.example.orders.application.OrderReportReader;
import com.example.orders.application.OrderRow;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
@Profile("jpa")
public class JpaOrderReportReader implements OrderReportReader {

    @PersistenceContext
    private EntityManager em;

    @Override
    public List<OrderRow> findRecent(
            long customerId, int offset, int limit) {
        validatePage(offset, limit);

        return em.createQuery(
                """
                select o
                from OrderEntity o
                where o.customerId = :customerId
                order by o.createdAt desc, o.id desc
                """,
                OrderEntity.class)
            .setParameter("customerId", customerId)
            .setFirstResult(offset)
            .setMaxResults(limit)
            .getResultStream()
            .map(o -> new OrderRow(o.getId(), o.getStatus()))
            .toList();
    }

    private static void validatePage(int offset, int limit) {
        if (offset < 0 || limit < 1 || limit > 200) {
            throw new IllegalArgumentException("Invalid page bounds");
        }
    }
}
~~~

Ví dụ giả định OrderEntity có các thuộc tính customerId, createdAt, id, status và mapping bảng tương ứng. Trong dự án thực tế, code có thể dùng constructor projection để chỉ chọn các cột cần thiết, tránh tải toàn bộ entity. Một ví dụ JPQL constructor projection yêu cầu lớp DTO có constructor phù hợp và tên lớp đầy đủ trong câu JPQL.

Ưu điểm của phiên bản JPA:

- Truy vấn dùng **tên thuộc tính entity**, không phụ thuộc trực tiếp vào tên bảng/cột vật lý.
- EntityManager tự chuyển setFirstResult/setMaxResults sang cơ chế phân trang của dialect tương ứng.
- Tham số được bind qua API thay vì ghép dữ liệu người dùng vào chuỗi SQL.
- Mức thay đổi khi chuyển DBMS thường nhỏ hơn so với native SQL.

Tuy vậy, hãy bảo đảm mệnh đề ORDER BY có **thứ tự ổn định**: ở đây createdAt giảm dần và id giảm dần làm khóa phụ để xử lý những đơn hàng cùng thời điểm. OFFSET có thể chậm khi dữ liệu lớn và dễ cho kết quả bị xê dịch nếu có ghi đồng thời; nếu cần tính ổn định cao, chuyển sang keyset/cursor pagination với hợp đồng rõ ràng.

Các tính năng chuẩn khác như Criteria API, @Convert, EntityGraph của Jakarta Persistence và LockModeType có thể sử dụng theo tình huống. Riêng annotation @EntityGraph của Spring Data là tiện ích ở tầng Spring Data; đừng nhầm nó với API độc lập của mọi framework.

## 4. Khi bắt buộc có native SQL: tách chiến lược theo DBMS

Một số use case cần tận dụng native SQL vì báo cáo phức tạp, hint/index cụ thể, tìm kiếm toàn văn, lệnh ghi hàng loạt hoặc tối ưu kế hoạch thực thi. Khi đó, đừng nhét các nhánh kiểm tra vendor vào cùng một phương thức Repository.

Giả sử yêu cầu đọc đơn hàng cần sử dụng JDBC và native SQL cho báo cáo. Ta giữ nguyên port OrderReportReader, tạo một hợp đồng nội bộ chỉ cung cấp câu SQL:

~~~java
package com.example.orders.infrastructure.sql;

interface OrderPageSql {
    String findRecentByCustomer();
}
~~~

Chiến lược PostgreSQL:

~~~java
package com.example.orders.infrastructure.sql;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("postgres")
class PostgresOrderPageSql implements OrderPageSql {

    @Override
    public String findRecentByCustomer() {
        return """
            SELECT o.id, o.status
            FROM orders o
            WHERE o.customer_id = :customerId
            ORDER BY o.created_at DESC, o.id DESC
            LIMIT :limit OFFSET :offset
            """;
    }
}
~~~

Chiến lược Oracle 12c trở lên:

~~~java
package com.example.orders.infrastructure.sql;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("oracle")
class OracleOrderPageSql implements OrderPageSql {

    @Override
    public String findRecentByCustomer() {
        return """
            SELECT o.id, o.status
            FROM orders o
            WHERE o.customer_id = :customerId
            ORDER BY o.created_at DESC, o.id DESC
            OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
            """;
    }
}
~~~

Cả hai truy vấn trả về các cột giống nhau và dùng thứ tự giống nhau. Cú pháp LIMIT/OFFSET thuộc PostgreSQL; OFFSET ... FETCH thuộc Oracle trong phạm vi phiên bản được nêu. Đó là phần phụ thuộc có chủ đích.

Adapter thực thi dùng Spring JDBC:

~~~java
package com.example.orders.infrastructure.sql;

import com.example.orders.application.OrderReportReader;
import com.example.orders.application.OrderRow;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Map;

@Repository
@Profile("native")
public class JdbcOrderReportReader implements OrderReportReader {

    private final NamedParameterJdbcTemplate jdbc;
    private final OrderPageSql sql;

    public JdbcOrderReportReader(
            NamedParameterJdbcTemplate jdbc,
            OrderPageSql sql) {
        this.jdbc = jdbc;
        this.sql = sql;
    }

    @Override
    public List<OrderRow> findRecent(
            long customerId, int offset, int limit) {
        if (offset < 0 || limit < 1 || limit > 200) {
            throw new IllegalArgumentException("Invalid page bounds");
        }

        return jdbc.query(
            sql.findRecentByCustomer(),
            Map.of(
                "customerId", customerId,
                "offset", offset,
                "limit", limit),
            (rs, rowNum) -> new OrderRow(
                rs.getLong("id"),
                rs.getString("status")));
    }
}
~~~

Các import và cấu hình DataSource được rút gọn để tập trung vào ranh giới thiết kế. Phần SQL dùng named parameter, được NamedParameterJdbcTemplate chuyển thành bind parameter cho JDBC driver; không nối trực tiếp customerId, offset hay limit vào SQL.

Trong ví dụ này chỉ kích hoạt **một adapter** cho port:

~~~yaml
# Chạy với PostgreSQL và native SQL
spring:
  profiles:
    active: native,postgres
~~~

Với Oracle dùng profile native,oracle. Nếu chọn JPA thuần, dùng profile jpa và không cần bean OrderPageSql. Cơ chế profile là một ví dụ; hệ thống production có thể dùng cấu hình điều kiện dựa trên thuộc tính, kèm kiểm tra sự phù hợp với JDBC URL hoặc database metadata khi khởi động. Trường hợp bật đồng thời nhiều bean không mong muốn cần báo lỗi cấu hình ngay từ đầu.

**Lưu ý:** OrderPageSql là chiến lược SQL do ứng dụng định nghĩa, không phải org.hibernate.dialect.Dialect. Không nên tùy tiện kế thừa Hibernate Dialect chỉ để lưu vài câu native SQL.

### Đặt phần phụ thuộc ở đâu?

Một cấu trúc thư mục có thể là:

~~~text
orders/
  application/
    OrderReportReader.java
    OrderRow.java
    OrderService.java
  infrastructure/
    jpa/
      OrderEntity.java
      SpringDataOrderRepository.java
      JpaOrderReportReader.java
    sql/
      JdbcOrderReportReader.java
      OrderPageSql.java
      PostgresOrderPageSql.java
      OracleOrderPageSql.java
  config/
    PersistenceConfiguration.java
~~~

Các câu lệnh native SQL có thể lưu trong file resource riêng thay vì Java text block nếu dài. Dù ở đâu, chúng vẫn thuộc adapter, được phiên bản hóa cùng schema migration và có kiểm thử với DBMS tương ứng.

## 5. Cô lập tính năng riêng của JPA provider

Native SQL không phải nguồn phụ thuộc duy nhất. Ví dụ thường gặp với Hibernate:

~~~java
import org.hibernate.Session;

Session session = entityManager.unwrap(Session.class);
session.setJdbcBatchSize(50);
~~~

Đây là API Hibernate, không phải hành vi được bảo đảm bởi Jakarta Persistence. Nếu gọi nó trong service nghiệp vụ, việc thay Hibernate bằng provider khác sẽ ảnh hưởng đến service.

Cách xử lý phù hợp:

- Chỉ gọi unwrap, query hint vendor, StatelessSession hoặc API batch riêng trong lớp infrastructure có tên và trách nhiệm cụ thể.
- Cấu hình các tùy chọn provider ở lớp khởi tạo persistence, không phân tán trong nghiệp vụ.
- Với annotation riêng như Hibernate @Formula, @SQLRestriction, @JdbcTypeCode hoặc @BatchSize, đặt entity mapping trong module infrastructure. Nếu semantics này ảnh hưởng kết quả nghiệp vụ, phải nêu rõ và xác minh ở các adapter thay thế.
- Ưu tiên API chuẩn như AttributeConverter, JPQL, Criteria API hoặc EntityManager.flush khi chúng diễn đạt đúng yêu cầu; không thay mọi tính năng vendor bằng API chuẩn bằng mọi giá nếu semantics khác nhau.

Ví dụ với một thuộc tính trạng thái logic:

~~~java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class ActiveFlagConverter
        implements AttributeConverter<Boolean, String> {

    @Override
    public String convertToDatabaseColumn(Boolean value) {
        if (value == null) {
            return null;
        }
        return value ? "Y" : "N";
    }

    @Override
    public Boolean convertToEntityAttribute(String dbValue) {
        if (dbValue == null) {
            return null;
        }
        return switch (dbValue) {
            case "Y" -> true;
            case "N" -> false;
            default -> throw new IllegalArgumentException(
                "Unknown active flag: " + dbValue);
        };
    }
}
~~~

AttributeConverter là một cơ chế JPA chuẩn cho mapping giá trị đơn giản. Tuy nhiên, nó **không** giải quyết mọi trường hợp JSONB, array, kiểu object Oracle hoặc operator chuyên biệt. Khi cần truy vấn bằng operator native trên một kiểu dữ liệu riêng, phần truy vấn và chuyển kiểu phải nằm trong adapter tương ứng.

## 6. Phân biệt khả năng kỹ thuật với ý nghĩa nghiệp vụ

Việc hai DBMS có câu lệnh “trông tương tự” không chứng minh chúng có cùng ngữ nghĩa. Xét chức năng ghi đè số lượng tồn kho theo khóa SKU:

~~~sql
-- PostgreSQL, giả định sku có UNIQUE constraint
INSERT INTO inventory_stock (sku, quantity)
VALUES (:sku, :quantity)
ON CONFLICT (sku)
DO UPDATE SET quantity = EXCLUDED.quantity;
~~~

~~~sql
-- Oracle, giả định sku có UNIQUE constraint
MERGE INTO inventory_stock dst
USING (
    SELECT :sku AS sku, :quantity AS quantity
    FROM dual
) src
ON (dst.sku = src.sku)
WHEN MATCHED THEN
    UPDATE SET dst.quantity = src.quantity
WHEN NOT MATCHED THEN
    INSERT (sku, quantity)
    VALUES (src.sku, src.quantity);
~~~

Cả hai có thể hiện thực hợp đồng saveLatestQuantity(sku, quantity) trong tình huống thông thường, nhưng **không được mặc định tương đương dưới mọi cạnh tranh ghi**. MERGE và ON CONFLICT có cơ chế phát hiện xung đột và hành vi khóa khác nhau; Oracle MERGE có thể gặp vi phạm unique constraint trong một số cuộc đua đồng thời. Cần xác định ứng dụng mong muốn idempotency, retry, thứ tự sự kiện và isolation như thế nào.

Tương tự, các tính năng sau thường cần adapter riêng hoặc thay đổi thiết kế:

| Nhu cầu | Điểm phụ thuộc | Cần chuẩn hóa ở hợp đồng |
| --- | --- | --- |
| Tìm kiếm không phân biệt hoa/thường | ILIKE, LOWER, collation, accent handling | Quy tắc hoa/thường, dấu và thứ tự sắp xếp |
| Full-text search | PostgreSQL tsvector/tsquery; Oracle Text | Cách tokenize, ngôn ngữ, ranking và fallback |
| JSON query | jsonb operators; Oracle JSON functions | Đường dẫn JSON, kiểu kết quả, xử lý giá trị thiếu |
| Phân trang | LIMIT/OFFSET; OFFSET/FETCH; keyset | Thứ tự ổn định, kích thước, hành vi khi có ghi |
| Lấy khóa sinh tự động | IDENTITY, SEQUENCE, RETURNING | Thời điểm ID có giá trị, batch insert |
| Khóa/chọn hàng cho worker | FOR UPDATE, SKIP LOCKED, NOWAIT | Chờ hay bỏ qua khóa; thứ tự nhận việc; timeout |
| Sắp xếp chuỗi và NULL | Collation, NULLS FIRST/LAST | Thứ tự chuẩn cần quan sát từ bên ngoài |

Ví dụ với full-text search, thay PostgreSQL full-text bằng điều kiện LIKE trên Oracle có thể làm thay đổi hành vi tìm kiếm và hiệu năng. Hợp đồng nên mô tả rõ kết quả mong muốn và khả năng được hỗ trợ. Nếu một nền tảng không có tính năng tương đương, ứng dụng nên báo unsupported capability hoặc dùng fallback đã xác định rõ; không âm thầm thay đổi nghĩa của tính năng.

Có thể biểu diễn lựa chọn bằng interface chuyên dụng:

~~~java
public interface ProductTextSearch {
    List<ProductHit> search(String phrase, int limit);
}
~~~

Hạ tầng có thể cung cấp PostgresTextSearch và OracleTextSearch. ProductHit là kết quả trung lập; các chi tiết tsvector, CONTAINS, index và syntax của query chỉ nằm trong adapter. Không đưa giá trị ranking vendor-specific vào hợp đồng nếu không có định nghĩa chuyển đổi ổn định.

## 7. Quản lý mapping, cấu hình và schema theo cùng ranh giới

### Mapping entity và kiểu dữ liệu

Entity là mô hình persistence, có thể khác domain model. Khi schema có những kiểu cột riêng, tránh để domain object chứa trực tiếp PGobject, oracle.sql.* hoặc annotation của Hibernate. Chuyển đổi dữ liệu ở mapping layer:

~~~text
Domain Value Object
       |
       v
Persistence Mapper / AttributeConverter
       |
       v
Entity field / JDBC value / database-specific column
~~~

Đặc biệt cần quy định nhất quán việc lưu Instant/OffsetDateTime, độ chính xác timestamp, kiểu UUID, decimal precision, enum và chuỗi rỗng. Ví dụ Oracle xem chuỗi VARCHAR2 rỗng là NULL trong nhiều trường hợp; mã nghiệp vụ cần phân biệt chuỗi rỗng và null có thể không đạt cùng semantics nếu giữ nguyên thiết kế lưu trữ.

### Cấu hình provider và dialect

Hibernate thường có thể suy ra dialect qua JDBC metadata khi có kết nối thích hợp. Nếu đặt dialect thủ công, hãy dùng tên class và phiên bản tương ứng với bản Hibernate đang chạy, ví dụ org.hibernate.dialect.PostgreSQLDialect hoặc org.hibernate.dialect.OracleDialect. Đổi provider đòi hỏi xem lại toàn bộ cấu hình liên quan; không nên coi thuộc tính spring.jpa.database-platform là hợp đồng dùng chung cho mọi provider.

Tránh gắn if (isOracle) hoặc if (isPostgres) trong domain service. Việc chọn adapter phù hợp nên tập trung tại cấu hình, và sai lệch giữa cấu hình adapter, driver, DBMS và schema phải được phát hiện sớm.

### Migration và chỉ mục

JPA schema generation không thay thế cho migration có kiểm soát ở production. Quản lý DDL bằng Flyway, Liquibase hoặc cơ chế migration của dự án, với script riêng khi cú pháp khác nhau. Ví dụ index PostgreSQL dùng GIN cho jsonb/full-text không thể chuyển nguyên văn sang Oracle.

Migration, native SQL và mapping entity phải tiến hóa cùng nhau. Nếu thêm cột, đổi kiểu hoặc đổi index chỉ trên một database, adapter còn lại cần được đánh giá về tính năng và hợp đồng tương ứng.

## 8. Transaction, exception và hiệu năng cần giữ nhất quán

**Transaction:** với Spring, đặt @Transactional ở service/use case khi một hành động nghiệp vụ cần nhiều thao tác cùng giao dịch. Không dựa vào việc mỗi Repository tự mở transaction độc lập. Nếu phối hợp JPA và JDBC trong một giao dịch, phải xác minh chúng dùng cùng DataSource và transaction manager phù hợp; một giao dịch của JPA không tự bảo đảm tất cả kết nối ngoài hệ thống cùng tham gia.

**Locking:** LockModeType.PESSIMISTIC_WRITE là API JPA chuẩn nhưng kết quả phụ thuộc SQL và mức isolation. Nếu nghiệp vụ đòi NOWAIT/SKIP LOCKED, thời gian chờ cụ thể hoặc thứ tự cấp phát công việc, đưa khả năng này thành hợp đồng rõ ràng và hiện thực/test riêng theo DBMS.

**Exception:** application không nên xử lý trực tiếp SQLSTATE hoặc vendor error code ở nhiều nơi. Adapter có thể chuyển unique violation, optimistic lock conflict hoặc lỗi kết nối thành các lỗi ứng dụng thích hợp. Spring DataAccessException là một tầng dịch lỗi hữu ích nhưng cũng là phụ thuộc Spring; nếu port cần độc lập framework, map về exception thuộc application. Không retry bừa mọi lỗi database; chỉ retry trường hợp đã được phân loại có thể khôi phục và thao tác an toàn để thực hiện lại.

**Hiệu năng:** thay provider hoặc DBMS có thể làm thay đổi số truy vấn, batching, fetch strategy, kế hoạch thực thi và mức sử dụng index. Cẩn thận với N+1, fetch join các collection khi phân trang, kích thước batch và count query. Tính năng tương đương về kết quả vẫn có thể không tương đương về độ trễ hoặc mức sử dụng bộ nhớ.

**An toàn SQL:** bind tất cả giá trị dữ liệu. Các định danh SQL như tên bảng, cột hay từ khóa ORDER BY thường không được bind như tham số thông thường; nếu cần sort động, ánh xạ từ danh sách trường cho phép sang tên cột cố định. Không nối trực tiếp chuỗi do client gửi vào native SQL, kể cả khi adapter đã tách riêng.

## 9. Kiểm thử hợp đồng qua các adapter

Việc cô lập phụ thuộc chỉ có giá trị khi các adapter thực hiện cùng một hợp đồng quan sát được. Có thể dùng một bộ **contract tests** cho mọi implementation của OrderReportReader:

| Kịch bản | Kết quả cần thống nhất |
| --- | --- |
| Khách hàng chưa có đơn | Trả danh sách rỗng |
| Nhiều đơn cùng createdAt | Sắp theo id giảm dần để ổn định |
| offset = 0, limit = 2 | Trả tối đa hai kết quả đầu |
| offset âm, limit = 0 hoặc quá giới hạn | Từ chối tham số không hợp lệ |
| Dữ liệu chứa Unicode, null, timezone | Giữ semantics đã định nghĩa |
| Có giao dịch khác ghi đồng thời | Bảo đảm nhất quán theo mức isolation được công bố |
| Vi phạm ràng buộc unique hoặc deadlock | Trả lỗi phù hợp và xử lý retry theo chính sách |

Ví dụ định hướng test bằng JUnit:

~~~java
abstract class OrderReportReaderContract {

    protected abstract OrderReportReader reader();
    protected abstract void insertOrder(
        long id, long customerId, String status,
        java.time.Instant createdAt);

    @org.junit.jupiter.api.Test
    void usesStableOrderWhenTimestampsMatch() {
        var timestamp = java.time.Instant.parse(
            "2026-01-01T00:00:00Z");

        insertOrder(10L, 7L, "NEW", timestamp);
        insertOrder(11L, 7L, "PAID", timestamp);

        var ids = reader().findRecent(7L, 0, 10).stream()
            .map(OrderRow::id)
            .toList();

        org.junit.jupiter.api.Assertions.assertEquals(
            java.util.List.of(11L, 10L), ids);
    }
}
~~~

Đây là khung minh họa: mỗi suite adapter cần cấu hình persistence, schema, dữ liệu test và reset trạng thái độc lập. Kiểm thử JPA trên H2 có thể hữu ích cho logic cơ bản, nhưng **không chứng minh** native SQL của PostgreSQL chạy trên Oracle hoặc ngược lại.

Với tính năng SQL riêng, nên có integration test trên đúng phiên bản DBMS mục tiêu (ví dụ PostgreSQL container và một Oracle test instance/container phù hợp). Kiểm tra cả SQL chạy được, dữ liệu trả về, tính nguyên tử, hành vi cạnh tranh và execution plan với bộ dữ liệu đủ đại diện. Chỉ mock OrderPageSql rồi khẳng định string SQL không cho biết câu SQL có thực thi đúng hay không.

## 10. Từng bước tách Repository đang bị khóa vào vendor

Giả sử một Spring Data repository đang chứa:

~~~java
public interface OrderRepository
        extends JpaRepository<OrderEntity, Long> {

    @Query(
        value = """
            SELECT *
            FROM orders
            WHERE customer_id = :customerId
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """,
        nativeQuery = true)
    List<OrderEntity> findRecentNative(
        @Param("customerId") long customerId,
        @Param("limit") int limit);
}
~~~

Truy vấn này khóa câu SQL vào LIMIT và chứa quyết định kỹ thuật trong interface. Nếu chỉ cần đọc danh sách thông thường, trước hết cân nhắc chuyển sang JPQL và setMaxResults/Pageable phù hợp. Nếu native SQL thật sự cần thiết:

1. Xác định hợp đồng nghiệp vụ, ví dụ OrderReportReader.findRecent, cùng giới hạn phân trang, thứ tự và chính sách lỗi.
2. Viết một adapter hiện thực hành vi hiện tại, giữ nguyên đầu ra quan sát được của use case.
3. Chuyển native SQL sang chiến lược dành cho DBMS đang dùng; đưa tên cột, hint và operator vendor vào đúng adapter.
4. Thêm adapter DBMS thứ hai nếu thực sự hỗ trợ; không tạo implementation giả hoặc fallback thay đổi ngữ nghĩa.
5. Chọn adapter bằng cấu hình tập trung, giữ lỗi cấu hình hiển thị rõ lúc khởi động.
6. Chạy cùng bộ kiểm thử hợp đồng và integration test trên DBMS thực, đồng thời đo kế hoạch thực thi cho truy vấn quan trọng.
7. Sau khi chuyển caller sang port mới, bỏ entry point cũ để tránh hai đường truy cập có semantics khác nhau.

Một thiết kế Repository được cô lập tốt có ba đặc điểm: **caller chỉ phụ thuộc hợp đồng dữ liệu/nghiệp vụ; mọi SQL và API độc quyền có nơi sở hữu cụ thể; tính đúng đắn được xác minh trên chính provider và DBMS mà ứng dụng triển khai**. Nhờ đó, việc đổi công nghệ lưu trữ trở thành một thay đổi có phạm vi và có thể kiểm chứng, thay vì phải chỉnh sửa lan rộng qua service và domain.
