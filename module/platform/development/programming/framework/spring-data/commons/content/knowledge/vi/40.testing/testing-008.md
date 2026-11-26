# Kiểm thử projection, constructor và dữ liệu không được tải

## 1. Một projection đúng cần nhiều hơn một assertion về giá trị

Trong chương **Kiểm thử** của module **SPRING_DATA_COMMONS**, projection là một điểm giao giữa abstraction repository, metadata kiểu trả về, cách tạo đối tượng và khả năng truy vấn của từng store.

Ví dụ màn hình danh sách bài viết chỉ cần ID, tiêu đề và tiêu đề phụ. Nội dung đầy đủ có thể dài hàng nghìn ký tự. Có ba yêu cầu cần kiểm chứng riêng:

1. Kết quả trả về chứa đúng giá trị mà màn hình cần.
2. Kiểu projection hoặc DTO được tạo đúng, kể cả khi một giá trị được phép null.
3. Đường truy vấn thực sự không đưa nội dung đầy đủ vào tập dữ liệu được trả về từ backend.

Một test chỉ kiểm tra `getTitle()` chưa chứng minh yêu cầu thứ ba. Ngược lại, một câu SELECT có ít cột cũng chưa chứng minh constructor nhận đúng thứ tự và kiểu dữ liệu.

Bài này dùng **Java 17, Spring Boot 3.5, Spring Data JPA 3.5 và Hibernate 6.6** cho ví dụ SQL. Phần cuối phân biệt constructor của DTO, entity JPA và domain được materialize bởi mapper của Spring Data.

## 2. Phân biệt ba trạng thái dễ bị nhầm

| Trạng thái | Ý nghĩa | Bằng chứng phù hợp |
| --- | --- | --- |
| Giá trị thật sự null | Field được chọn nhưng dữ liệu không có giá trị | Fixture null và assertion về kết quả |
| Field không thuộc projection | Kiểu trả về không cung cấp field đó | Hợp đồng kiểu trả về |
| Field không được chọn hoặc association chưa được tải | Đường thực thi chưa lấy dữ liệu đó theo phạm vi đang xét | Query/command quan sát được hoặc API kiểm tra load state phù hợp |

`Optional.empty()` ở getter projection biểu diễn giá trị backing null theo hợp đồng wrapper. Nó không tự giải thích vì sao giá trị đó null.

Tương tự, một DTO không có thuộc tính `body` chứng minh caller không nhận thuộc tính đó qua DTO. Nó chưa chứng minh ứng dụng không tải entity đầy đủ rồi mới chuyển entity thành DTO.

Có thể hình dung các lớp cần quan sát:

~~~text
Repository method
        |
        v
Query chọn field nào?
        |
        v
Kết quả được map bằng proxy hay constructor nào?
        |
        v
Caller gọi getter / mapper / serializer nào?
        |
        v
Có phát sinh thêm truy vấn hoặc tải dữ liệu không?
~~~

Cần chọn assertion cho đúng lớp. Không dùng một dấu hiệu ở lớp cuối để suy ra toàn bộ hành vi ở lớp đầu.

## 3. Loại projection ảnh hưởng kế hoạch kiểm thử

| Dạng trả về | Điều cần kiểm tra |
| --- | --- |
| Closed interface projection | Getter khớp property, giá trị và query thực tế |
| Open projection dùng SpEL | Biểu thức, null và dữ liệu mà biểu thức có thể truy cập |
| DTO hoặc record | Constructor, thứ tự/kiểu giá trị và mapping từ query |
| Dynamic projection | Mỗi kiểu mà ứng dụng thực sự truyền vào |
| Nested projection | Quan hệ null, join và việc truy cập dữ liệu lồng nhau |
| Entity được tải một phần bằng cơ chế của store | Hợp đồng missing field, constructor và giới hạn cập nhật |

Closed projection tạo cơ hội tối ưu vì các property cần dùng có thể xác định trước. Với open projection, biểu thức SpEL có thể truy cập dữ liệu khác của aggregate, nên không được suy rằng nó có cùng tối ưu.

Các khái niệm interface projection, nullable wrapper và dynamic projection được mô tả trong [Projections của Spring Data Commons](https://docs.spring.io/spring-data/commons/reference/3.5/repositories/projections.html).

Một getter tính toán bằng default method chỉ từ các getter đã có khác với biểu thức dùng thêm thuộc tính của target. Hãy xem dữ liệu mà phép tính thực sự cần, thay vì chỉ nhìn tên getter.

## 4. Mô hình minh họa: danh sách bài viết

Các public type sau đặt trong các file Java riêng, cùng package `example.article`. Ứng dụng có cấu hình Boot ở package phù hợp để tìm entity và repository.

Đối với integration test, cần JPA, bộ thư viện test của Boot và database test phù hợp. Ví dụ tối thiểu có thể dùng H2 trong phạm vi test; với yêu cầu phụ thuộc dialect, chạy cùng hành vi trên backend đại diện của dự án.

### 4.1. Entity có nội dung đầy đủ

~~~java
package example.article;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "article_record")
public class Article {

    @Id
    @GeneratedValue
    private Long id;

    @Column(name = "title_text", nullable = false)
    private String title;

    @Column(name = "subtitle_text")
    private String subtitle;

    @Column(name = "body_text", nullable = false, length = 4096)
    private String body;

    private boolean published;

    protected Article() {
    }

    public Article(
            String title,
            String subtitle,
            String body,
            boolean published) {

        this.title = title;
        this.subtitle = subtitle;
        this.body = body;
        this.published = published;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getSubtitle() {
        return subtitle;
    }

    public String getBody() {
        return body;
    }

    public boolean isPublished() {
        return published;
    }
}
~~~

Tên cột `body_text` được khai báo rõ để phục vụ yêu cầu kiểm tra SELECT. Ví dụ không đánh dấu body là lazy: việc không tải body cần đến từ đường projection, không dựa vào giả định về lazy basic field.

### 4.2. Closed interface projection

~~~java
package example.article;

import java.util.Optional;

public interface ArticleTitle {

    Long getId();

    String getTitle();

    Optional<String> getSubtitle();
}
~~~

Các getter tương ứng với property của `Article`. Getter subtitle dùng wrapper để caller xử lý trường hợp null rõ ràng.

Projection không mở rộng `Article` và `Article` cũng không triển khai interface này. Việc trả một supertype của entity không tương đương tạo một view độc lập.

### 4.3. DTO bằng record

~~~java
package example.article;

public record ArticleCard(
        Long id,
        String title,
        String subtitle) {

    public ArticleCard {
        if (id == null) {
            throw new IllegalArgumentException("Thiếu id");
        }

        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Thiếu tiêu đề");
        }
    }
}
~~~

Record có canonical constructor cho ba thành phần của view. Nó cho phép subtitle null nhưng yêu cầu ID và title.

Không thêm điều kiện “body phải có giá trị” vào constructor này: body không thuộc hợp đồng của card. Các quy tắc yêu cầu dữ liệu đầy đủ cần đặt trong kiểu hoặc thao tác có đủ dữ liệu để kiểm tra.

### 4.4. Repository

~~~java
package example.article;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface ArticleRepository
        extends JpaRepository<Article, Long> {

    List<ArticleTitle>
    findByPublishedTrueOrderByTitleAscIdAsc();

    @Query("""
            select new example.article.ArticleCard(
                a.id, a.title, a.subtitle)
              from Article a
             where a.published = true
             order by a.title asc, a.id asc
            """)
    List<ArticleCard> findPublishedCards();

    <T> List<T> findByPublishedTrueOrderByTitleAscIdAsc(
            Class<T> viewType);
}
~~~

Query DTO dùng constructor expression tường minh với tên class đầy đủ. Dynamic query cho phép chọn kiểu view tại lời gọi.

JPA có cơ chế riêng cho interface projection, DTO constructor expression và truy vấn lồng quan hệ. Xem [Using Projections with JPA](https://docs.spring.io/spring-data/jpa/reference/3.5/repositories/projections.html#projections.jpa).

Không đổi kiểu trả về của một CRUD base method theo phỏng đoán để tạo projection. Ví dụ dùng các query method riêng cho mục đích này.

## 5. Unit test constructor: kiểm tra hợp đồng của DTO

~~~java
package example.article;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ArticleCardTest {

    @Test
    void acceptsMissingOptionalSubtitle() {
        ArticleCard card = new ArticleCard(7L, "Alpha", null);

        assertThat(card.id()).isEqualTo(7L);
        assertThat(card.title()).isEqualTo("Alpha");
        assertThat(card.subtitle()).isNull();
    }

    @Test
    void rejectsBlankTitle() {
        assertThatThrownBy(
                () -> new ArticleCard(7L, " ", null))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Thiếu tiêu đề");
    }

    @Test
    void rejectsMissingId() {
        assertThatThrownBy(
                () -> new ArticleCard(null, "Alpha", null))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Thiếu id");
    }
}
~~~

Các test này chứng minh constructor chấp nhận hoặc từ chối đầu vào theo hợp đồng. Chúng không chứng minh query đưa đúng dữ liệu vào constructor.

Integration test vẫn cần thiết để phát hiện đảo title/subtitle, thiếu tham số hoặc kiểu kết quả không tương thích. Hai tham số cùng là `String` khiến lỗi đảo thứ tự có thể không bị phát hiện bằng kiểm tra kiểu đơn thuần.

Không mock `ArticleCard` trong test mapping. Khi đối tượng bị mock, constructor thật có thể hoàn toàn không chạy.

## 6. Thu thập SQL trong integration test Hibernate

Để kiểm tra yêu cầu không chọn body, ví dụ dùng `StatementInspector`. Đây là API Hibernate quan sát SQL trước khi JDBC statement được chuẩn bị, không phải API chung của Commons.

Theo [API StatementInspector 6.6](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/resource/jdbc/spi/StatementInspector.html), inspector đăng ký ở session factory có thể được chia sẻ giữa các session. Bộ thu thập dưới đây giữ dữ liệu theo thread cho ví dụ JPA imperative chạy trên thread gọi test.

### 6.1. Bộ thu thập dùng trong test

~~~java
package example.article;

import java.util.ArrayList;
import java.util.List;

import org.hibernate.resource.jdbc.spi.StatementInspector;

public final class SqlCapture implements StatementInspector {

    private final ThreadLocal<List<String>> captured =
            ThreadLocal.withInitial(ArrayList::new);

    @Override
    public String inspect(String sql) {
        captured.get().add(sql);
        return sql;
    }

    public List<String> statements() {
        return List.copyOf(captured.get());
    }

    public void reset() {
        captured.remove();
    }
}
~~~

`inspect` trả nguyên SQL để không đổi hành vi thực thi. `reset` dùng để bắt đầu phạm vi đo và dọn dữ liệu của thread sau test.

Đây là bộ thu thập nhỏ cho ví dụ đồng bộ. Khi công việc chạy trên thread khác, phải có cơ chế gắn các statement với đúng kịch bản; không mặc định ThreadLocal đi theo tác vụ bất đồng bộ.

### 6.2. Đăng ký bằng cấu hình test

~~~java
package example.article;

import org.springframework.boot.autoconfigure.orm.jpa.HibernatePropertiesCustomizer;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
public class SqlCaptureConfiguration {

    @Bean
    SqlCapture sqlCapture() {
        return new SqlCapture();
    }

    @Bean
    HibernatePropertiesCustomizer statementInspector(
            SqlCapture capture) {

        return properties -> properties.put(
                "hibernate.session_factory.statement_inspector",
                capture);
    }
}
~~~

`HibernatePropertiesCustomizer` cho phép bổ sung thuộc tính trước khi Boot tạo `EntityManagerFactory`. Xem [API HibernatePropertiesCustomizer](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/orm/jpa/HibernatePropertiesCustomizer.html).

Nếu dự án đã có inspector khác, cần tích hợp với cấu hình đang dùng. Không thay nó một cách vô thức khiến test mất quan sát khác mà dự án cần.

## 7. Integration test giá trị, constructor và cột được chọn

### 7.1. Fixture có dữ liệu phân biệt

| Bài viết | Subtitle | Body | Published | Mục đích |
| --- | --- | --- | --- | --- |
| Alpha | null | Chuỗi dài không rỗng | true | Kiểm tra null hợp lệ |
| Beta | Preview | Chuỗi dài không rỗng | true | Kiểm tra mapping giá trị khác nhau |
| Draft | Hidden | Chuỗi không rỗng | false | Bắt lỗi thiếu điều kiện lọc |

Body phải có dữ liệu thật. Nếu fixture đã để body null, assertion kết quả null không thể phân biệt “không chọn body” với “đã chọn một giá trị null”.

### 7.2. Test hoàn chỉnh

~~~java
package example.article;

import java.util.List;
import java.util.Locale;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(properties = {
        "spring.jpa.hibernate.ddl-auto=create-drop",
        "spring.jpa.properties.hibernate.use_sql_comments=false",
        "spring.jpa.properties.hibernate.cache.use_query_cache=false",
        "spring.jpa.properties.hibernate.cache.use_second_level_cache=false"
})
@Import(SqlCaptureConfiguration.class)
class ArticleViewsTest {

    @Autowired
    private ArticleRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private SqlCapture sqlCapture;

    private Long alphaId;
    private Long betaId;

    @BeforeEach
    void setUp() {
        String body = "BODY_" + "x".repeat(2048);

        Article alpha = repository.save(
                new Article("Alpha", null, body, true));
        Article beta = repository.save(
                new Article("Beta", "Preview", body, true));

        repository.save(
                new Article("Draft", "Hidden", body, false));

        entityManager.flush();
        alphaId = alpha.getId();
        betaId = beta.getId();
        entityManager.clear();

        sqlCapture.reset();
    }

    @AfterEach
    void clearCapturedSql() {
        sqlCapture.reset();
    }

    @Test
    void mapsClosedProjectionAndNullableWrapper() {
        List<ArticleTitle> views = repository
                .findByPublishedTrueOrderByTitleAscIdAsc();

        assertThat(views)
                .extracting(ArticleTitle::getTitle)
                .containsExactly("Alpha", "Beta");

        assertThat(views.get(0).getId()).isEqualTo(alphaId);
        assertThat(views.get(0).getSubtitle()).isEmpty();

        assertThat(views.get(1).getId()).isEqualTo(betaId);
        assertThat(views.get(1).getSubtitle())
                .contains("Preview");

        assertNoBodyInObservedSelects();
    }

    @Test
    void mapsConstructorExpressionIntoRecord() {
        List<ArticleCard> cards =
                repository.findPublishedCards();

        assertThat(cards).containsExactly(
                new ArticleCard(alphaId, "Alpha", null),
                new ArticleCard(betaId, "Beta", "Preview"));

        assertNoBodyInObservedSelects();
    }

    @Test
    void mapsDynamicProjectionIntoRequestedDto() {
        List<ArticleCard> cards = repository
                .findByPublishedTrueOrderByTitleAscIdAsc(
                        ArticleCard.class);

        assertThat(cards).containsExactly(
                new ArticleCard(alphaId, "Alpha", null),
                new ArticleCard(betaId, "Beta", "Preview"));

        assertNoBodyInObservedSelects();
    }

    private void assertNoBodyInObservedSelects() {
        List<String> selects = sqlCapture.statements().stream()
                .map(sql -> sql.toLowerCase(Locale.ROOT))
                .filter(sql -> sql.stripLeading()
                        .startsWith("select"))
                .toList();

        assertThat(selects).isNotEmpty();

        assertThat(selects).allSatisfy(sql ->
                assertThat(sql)
                        .contains("title_text", "subtitle_text")
                        .doesNotContain("body_text", "*"));
    }
}
~~~

Ví dụ giả định database test riêng, không có seed ngoài fixture. `create-drop` tạo schema minh họa trong môi trường đó; kiểm thử migration là một mục tiêu khác.

### 7.3. Vì sao thứ tự chuẩn bị dữ liệu quan trọng?

Fixture được lưu và flush trước khi clear persistence context. Sau đó mới reset bộ thu thập SQL.

Nếu reset trước flush, INSERT của fixture có thể lẫn vào phạm vi quan sát. Nếu giữ entity trong persistence context hoặc bật query cache cho một kịch bản khác, test có thể không quan sát đúng đường tải dữ liệu cần đánh giá.

Các assertion gọi getter projection trước khi đọc SQL đã thu thập. Vì vậy, phạm vi đo bao gồm cả cách caller truy cập các giá trị trong ví dụ.

Test yêu cầu có SELECT thật, tránh việc danh sách SQL rỗng làm assertion “không chứa body” thành công một cách vô nghĩa.

### 7.4. Assertion SQL bảo vệ điều gì?

Với các query đơn giản của ví dụ, test kiểm tra statement SELECT quan sát được có các cột cần dùng, không có `body_text` và không dùng wildcard.

Không so sánh nguyên chuỗi SQL, alias hay khoảng trắng do Hibernate tạo. Những chi tiết đó có thể thay đổi mà hợp đồng cần bảo vệ vẫn đúng.

Đây là bằng chứng ở mức statement/cột của đường JPA đang kiểm tra. Nó không phải phép đo số byte vật lý database đã đọc từ đĩa.

Nếu query có subquery, aggregate, comment hoặc cấu trúc phức tạp, cần bộ quan sát/phân tích phù hợp hơn helper minh họa này. Không mở rộng một phép kiểm chuỗi đơn giản thành kết luận chung cho mọi SQL.

## 8. Constructor DTO, constructor entity và persistence creator khác nhau

| Đối tượng | Cơ chế cần kiểm tra | Lỗi điển hình |
| --- | --- | --- |
| Record DTO của ví dụ | Canonical constructor nhận kết quả projection | Đảo tham số, null ngoài hợp đồng |
| DTO class có nhiều constructor | Metadata chọn constructor hoặc constructor expression của query | Chọn nhầm chữ ký, thiếu thông tin cần thiết |
| Entity JPA | Cơ chế tạo và nạp entity của JPA provider | Áp nhầm quy tắc creator của module khác |
| Domain được mapper Spring Data tạo | Creator và property population của module đó | Constructor yêu cầu field không có trong kết quả |

`@PersistenceCreator` đánh dấu constructor hoặc factory được ưu tiên trong các cơ chế hỗ trợ nó. Annotation không tự bổ sung một field bị query loại ra và không sửa thứ tự sai trong một JPQL constructor expression. Xem [API PersistenceCreator](https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/annotation/PersistenceCreator.html).

Khi dùng DTO class có nhiều constructor cho projection suy ra từ metadata, cần khai báo constructor phù hợp theo cơ chế của module. Với class thường, còn phải bảo đảm metadata tên tham số cần thiết có mặt trong bản build.

Không áp nguyên thuật toán materialization của Commons cho entity JPA. [Object Mapping Fundamentals](https://docs.spring.io/spring-data/commons/reference/3.5/object-mapping.html) nêu rõ phạm vi của phần mapping này và yêu cầu tham khảo module lưu trữ.

Một constructor có thể chạy đúng khi gọi bằng `new` nhưng vẫn không được mapper chọn. Vì vậy, cần test trực tiếp qua repository/converter thật cho trường hợp quan trọng.

## 9. Dữ liệu không được tải và invariant của domain

Giả sử một domain đầy đủ yêu cầu body không null trong constructor. Nếu store cho phép truy vấn chỉ lấy ID và title rồi materialize lại chính domain đó, constructor có thể nhận đầu vào không đủ để duy trì invariant.

Không nên sửa bằng cách tự động gán body rỗng chỉ để việc đọc thành công, nếu body rỗng có ý nghĩa nghiệp vụ khác. Cách thiết kế phù hợp thường là dùng một read model riêng với các field thực sự được chọn.

Kế hoạch kiểm thử nên tách:

1. Unit test invariant của domain đầy đủ.
2. Unit test hợp đồng của DTO đọc.
3. Integration test mapping của từng đường repository.
4. Kiểm tra query/command giới hạn dữ liệu theo yêu cầu.

Trường hợp field bị thiếu, field có giá trị null và field có giá trị mặc định cần fixture riêng nếu chúng có ý nghĩa khác nhau. Với kiểu primitive, không mặc định một field vắng mặt luôn được chuyển thành 0 hoặc false theo cùng cách ở mọi mapper; có thể có lỗi tạo đối tượng hoặc chuyển đổi.

Các field như version, trạng thái duyệt hoặc metadata auditing cũng không tự xuất hiện trong một view chỉ vì domain đầy đủ có chúng.

Đối tượng đọc một phần không nên được dùng như thể là aggregate đầy đủ cho thao tác lưu. Nếu muốn cập nhật từ màn hình danh sách, truyền ID cùng lệnh cập nhật rõ ràng và tải/điều phối dữ liệu cần thiết cho nghiệp vụ.

## 10. Nested projection, lazy loading và consumer thực tế

### 10.1. Nested projection không bảo đảm ít join

Trong JPA, projection giới hạn thuộc tính ở cấp trên cùng; đường property lồng nhau cần join có thể làm dữ liệu quan hệ được materialize rộng hơn. Một interface lồng nhỏ không chứng minh backend chỉ chọn đúng một cột lồng.

Nếu yêu cầu là “không tải quan hệ author”, không đưa getter author vào view rồi suy rằng quan hệ vẫn chưa được tải. Hãy quan sát query và hành vi khi consumer đọc dữ liệu.

### 10.2. Dùng load-state API cho entity phù hợp

Với entity thực sự có association lazy, có thể kiểm tra load state bằng `PersistenceUnitUtil.isLoaded(entity, attributeName)` trước khi truy cập association.

API này dành cho entity thuộc persistence unit, không dùng tùy tiện trên record DTO hoặc proxy interface projection. Xem [PersistenceUnitUtil của Jakarta Persistence](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/PersistenceUnitUtil.html).

Đừng gọi getter của association, `toString()` hoặc một assertion sâu có thể tải quan hệ trước khi đo trạng thái. Khi đã truy cập, test đang quan sát một thời điểm khác với ý định ban đầu.

### 10.3. Đo cả phần sử dụng kết quả

Một query ban đầu có thể nhỏ nhưng mapper, serializer hoặc getter tính toán gọi tiếp dữ liệu khác. Khi hợp đồng liên quan đến toàn bộ màn hình/API, phạm vi quan sát cần bao gồm consumer đó.

Với yêu cầu không có thêm query sau khi rời repository, có thể ghi nhận SQL trước và sau khi chạy mapper hoặc serialization thật. Nếu dùng projection có khả năng trì hoãn truy cập, cần test ở ranh giới transaction mà ứng dụng thực sự sử dụng.

Không coi “chưa phát sinh query khi vừa nhận danh sách” là kết luận rằng mọi thao tác tiếp theo đều không tải thêm dữ liệu.

## 11. Áp dụng cho store khác

Với MongoDB, field restriction và document trả về là điểm cần quan sát thay vì SELECT. Tài liệu có ví dụ chỉ chọn một số field và các property không được lấy không được thiết lập như một lần đọc đầy đủ. Xem [JSON-based Query Methods and Field Restriction](https://docs.spring.io/spring-data/mongodb/reference/4.5/mongodb/repositories/query-methods.html#mongodb.repositories.queries.json-based).

Khi test, nên kiểm tra cả command/projection gửi đến MongoDB và đối tượng sau mapping. Một property Java null chưa phân biệt chắc chắn document gốc chứa null hay field đã bị loại khỏi kết quả.

Với JDBC hoặc R2DBC, dùng khả năng quan sát query/mapping của module và driver tương ứng. Đối với reactive, phải bảo đảm pipeline được subscribe, đọc đủ kết quả và kết thúc trong phạm vi quan sát; việc chỉ tạo publisher chưa thực thi truy vấn.

Tên `Projection`, `Repository` hay annotation dùng chung không làm các store có cùng cơ chế constructor, join hoặc tải dữ liệu. Bộ test cần thể hiện những khả năng mà ứng dụng thật sự đang dựa vào.

## 12. Ma trận lỗi và cách phát hiện

| Lỗi có thể xảy ra | Test có sức phân biệt |
| --- | --- |
| Getter trỏ nhầm property | Fixture có các giá trị khác nhau, assert từng field |
| Subtitle null làm caller lỗi | Fixture null và test wrapper/DTO tương ứng |
| Hai tham số String bị đảo | Integration test constructor với giá trị phân biệt |
| Mapper chọn nhầm constructor | Đọc qua repository/converter thật |
| DTO loại body nhưng query vẫn tải entity đầy đủ | Quan sát SELECT/command trong phạm vi query và consumer |
| SQL dùng wildcard | Kiểm tra riêng wildcard, không chỉ tìm tên body |
| Query cache làm không có statement | Yêu cầu quan sát được query trong kịch bản đo |
| Nested getter gây truy vấn thêm | Đo cả sau khi truy cập getter |
| Assertion vô tình tải association | Kiểm tra load state trước truy cập, tránh duyệt sâu |
| Missing field bị coi như dữ liệu đầy đủ | Test riêng read model và thao tác cập nhật |
| Unit test constructor xanh nhưng mapping sai | Giữ integration test cho đường tạo DTO thực tế |
| Dynamic projection chỉ đúng với một kiểu | Chạy các kiểu mà ứng dụng thực sự dùng |

Một bộ test projection hữu ích cần chứng minh đúng giá trị, đúng đường tạo đối tượng và đúng phạm vi dữ liệu truy vấn. Mỗi kết luận nên dựa vào bằng chứng trực tiếp của lớp đang được kiểm tra, đồng thời giữ rõ giới hạn của module lưu trữ đã chọn.
