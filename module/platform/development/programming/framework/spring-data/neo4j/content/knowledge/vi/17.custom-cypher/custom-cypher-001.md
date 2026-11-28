# Khai báo @Query từ package Spring Data Neo4j hiện đại

## Mục tiêu

Sau bài học này, bạn có thể:

- Xác định đúng package của annotation @Query trong Spring Data Neo4j (SDN) hiện đại.
- Khai báo custom Cypher query trên phương thức repository.
- Truyền tham số bằng cú pháp $name và @Param.
- Chọn kiểu kết quả phù hợp: domain entity, projection hoặc DTO.
- Trả về dữ liệu quan hệ theo định dạng mà SDN có thể ánh xạ chính xác.
- Khai báo phân trang, dùng SpEL cho cấu trúc truy vấn và tránh các lỗi thường gặp.

## 1. @Query dùng để làm gì?

Spring Data Neo4j hỗ trợ derived query, tức là tạo truy vấn từ tên phương thức repository. Cách này tiện cho các điều kiện tìm kiếm phổ biến. Khi cần mô tả chính xác đường đi trong đồ thị, kết hợp nhiều relationship, dùng hàm Cypher hoặc trả về dữ liệu tổng hợp, ta có thể viết truy vấn trực tiếp bằng Cypher qua annotation @Query.

Trong SDN hiện đại, annotation này nằm ở package:

~~~java
import org.springframework.data.neo4j.repository.query.Query;
~~~

Một repository thường đồng thời dùng Neo4jRepository và @Query:

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface MovieRepository extends Neo4jRepository<Movie, String> {

    @Query("""
        MATCH (m:Movie {title: $title})
        RETURN m
        """)
    Optional<Movie> findOneByTitleWithCypher(@Param("title") String title);

    @Query("""
        MATCH (m:Movie)
        RETURN m
        ORDER BY m.title
        """)
    List<Movie> findAllWithCypher();
}
~~~

@Query được đặt trên phương thức repository. Chuỗi bên trong annotation là câu Cypher được gửi đến Neo4j. SDN dùng kiểu trả về của phương thức cùng metadata domain để ánh xạ record thành đối tượng Java.

Đừng nhầm import hiện đại với các ví dụ cũ từ tài liệu Spring Data Neo4j dựa trên Neo4j-OGM hoặc với annotation @Query của module Spring Data khác. Hãy dùng đúng package của dependency SDN mà dự án đang sử dụng.

## 2. Viết Cypher trong annotation

Có thể truyền query bằng chuỗi thông thường:

~~~java
@Query("MATCH (p:Person) RETURN p")
List<Person> findAllPeople();
~~~

Với truy vấn dài, Java text block giúp giữ định dạng Cypher dễ đọc hơn:

~~~java
@Query("""
    MATCH (p:Person)
    WHERE p.fullName CONTAINS $keyword
    RETURN p
    ORDER BY p.fullName
    """)
List<Person> searchByName(@Param("keyword") String keyword);
~~~

Text block chỉ là cú pháp Java để viết chuỗi nhiều dòng. Khi chạy, SDN vẫn gửi một câu Cypher đến database.

Nên giữ câu truy vấn đủ rõ để người đọc nhận ra:

- Node gốc mà repository cần trả về.
- Relationship được duyệt và hướng duyệt.
- Điều kiện lọc.
- Các biến được trả về trong RETURN.
- Cách kết quả được nhóm nếu có nhiều nhánh quan hệ.

Một query custom không tự động được sửa theo tên field Java. Nhãn, kiểu relationship và property trong Cypher phải khớp với mô hình dữ liệu Neo4j.

## 3. Truyền tham số bằng $name và @Param

Tham số Cypher dùng cú pháp $parameterName, giống cách chạy truy vấn trong Neo4j Browser hoặc Cypher Shell:

~~~java
@Query("""
    MATCH (p:Person {personId: $personId})
    RETURN p
    """)
Optional<Person> findPerson(@Param("personId") String id);
~~~

@Param("personId") liên kết tham số Java id với tham số Cypher $personId. Tên trong @Param phải khớp với tên được tham chiếu trong query.

Có thể bỏ @Param nếu dự án được biên dịch với tùy chọn giữ tên tham số (-parameters) để Spring đọc được tên tham số Java:

~~~java
@Query("""
    MATCH (p:Person {personId: $personId})
    RETURN p
    """)
Optional<Person> findPerson(String personId);
~~~

Các plugin Maven và Gradle của Spring Boot thường cấu hình tùy chọn này. Tuy nhiên, dùng @Param tường minh giúp phương thức dễ hiểu và không phụ thuộc vào cách biên dịch.

SDN cũng hỗ trợ tham chiếu tham số theo vị trí như $0, nhưng tên có ý nghĩa thường dễ bảo trì hơn:

~~~java
@Query("""
    MATCH (m:Movie)
    WHERE m.released >= $0
    RETURN m
    """)
List<Movie> findReleasedSince(int year);
~~~

### Không nối chuỗi dữ liệu đầu vào vào Cypher

Không tạo query bằng cách ghép chuỗi từ giá trị người dùng:

~~~java
// Không nên: ghép trực tiếp dữ liệu đầu vào vào câu query.
String query = "MATCH (p:Person {fullName: '" + name + "'}) RETURN p";
~~~

Cách này có thể làm hỏng cú pháp khi dữ liệu chứa dấu nháy và mở ra nguy cơ Cypher injection.

Hãy dùng tham số:

~~~java
@Query("""
    MATCH (p:Person {fullName: $name})
    RETURN p
    """)
List<Person> findByFullName(@Param("name") String name);
~~~

Tham số phù hợp cho giá trị property, số, ngày tháng và danh sách giá trị. Trong Cypher, tên label và relationship type là thành phần cấu trúc của câu truy vấn, không thể thay bằng tham số giá trị thông thường. Phần tiếp theo trình bày cách xử lý trường hợp đó.

## 4. Khi cần label hoặc relationship type động

Ví dụ muốn tìm node theo label do cấu hình quyết định. Không thể viết MATCH (n:$label) và mong Cypher xem $label như một label động. Tham số Cypher chỉ đại diện cho giá trị.

SDN cung cấp SpEL và literal extension cho những vị trí cấu trúc mà Cypher không nhận tham số:

~~~java
@Query("""
    MATCH (n:`:#{literal(#label)}`)
    RETURN n
    """)
List<Person> findByDynamicLabel(@Param("label") String label);
~~~

literal(#label) chèn giá trị dưới dạng literal Cypher. Có thể áp dụng ý tưởng tương tự khi cần relationship type động.

Hãy chỉ cho phép những label hoặc relationship type nằm trong danh sách được ứng dụng kiểm soát. Không xem dữ liệu tùy ý từ request là một phần cấu trúc truy vấn hợp lệ. Trong đa số trường hợp, tham số $name thông thường vẫn là lựa chọn phù hợp hơn.

### SpEL cho giá trị tham số

SpEL có thể tạo giá trị tham số trong biểu thức :#{...}:

~~~java
@Query("""
    MATCH (p:Person)
    WHERE p.fullName = :#{#firstName + ' ' + #lastName}
    RETURN p
    """)
Optional<Person> findByFullNameParts(
    @Param("firstName") String firstName,
    @Param("lastName") String lastName
);
~~~

Biểu thức SpEL được đánh giá trong Spring, sau đó giá trị được truyền vào query. Đừng nhầm :#{...} của SpEL với cú pháp tham số Cypher $name. Khi không cần biểu thức động, nên dùng tham số Cypher trực tiếp để query đơn giản hơn.

## 5. Chọn kiểu kết quả của phương thức @Query

Kiểu trả về quyết định cách SDN xử lý record. Hãy bảo đảm phần RETURN tương ứng với kiểu Java.

### Trả về domain entity

Khi muốn đọc một Movie, trả về node Movie:

~~~java
@Query("""
    MATCH (m:Movie {title: $title})
    RETURN m
    """)
Optional<Movie> findMovie(@Param("title") String title);
~~~

Với nhiều node cùng kiểu, có thể trả về List<Movie> hoặc kiểu collection phù hợp. Với kết quả có thể không có bản ghi, Optional<Movie> thể hiện rõ trường hợp không tìm thấy.

Không nên trả về riêng một property như m.title rồi khai báo kiểu trả về là Movie. Nếu chỉ cần title, hãy trả về String hoặc projection phù hợp.

### Trả về projection hoặc DTO

Nếu API cần một hình dạng dữ liệu khác domain entity, có thể dùng interface projection hoặc DTO.

Ví dụ DTO tổng hợp:

~~~java
public record MovieSummary(
    String title,
    Long actorCount
) {
}
~~~

Repository:

~~~java
@Query("""
    MATCH (m:Movie {title: $title})
    OPTIONAL MATCH (m)<-[:ACTED_IN]-(p:Person)
    RETURN m.title AS title,
           count(p) AS actorCount
    """)
Optional<MovieSummary> findSummary(@Param("title") String title);
~~~

Tên alias trong RETURN như title và actorCount cần khớp với thuộc tính hoặc accessor mà DTO cung cấp. DTO projection hữu ích khi query trả về dữ liệu tổng hợp mà domain entity không có, chẳng hạn số lượng, điểm xếp hạng hoặc trạng thái tính toán.

Interface projection phù hợp khi cần một góc nhìn giới hạn trên các property và relationship đã được mô tả trong domain model. Không nên dùng projection như một domain entity đầy đủ để ghi lại dữ liệu nếu projection chỉ chứa một phần graph.

### Trả về giá trị đơn

Nếu truy vấn chỉ cần một con số, có thể trả về kiểu đơn:

~~~java
@Query("""
    MATCH (m:Movie)
    RETURN count(m)
    """)
long countMoviesWithCypher();
~~~

Trong trường hợp này, query trả về một giá trị số chứ không phải node. Chọn kiểu Java tương thích với kiểu dữ liệu được Neo4j trả về.

## 6. Trả về entity có relationship

Khi query cần hydrate một Movie cùng các diễn viên và relationship ACTED_IN, chỉ trả về node Movie có thể chưa cung cấp đầy đủ dữ liệu cho các relationship mà domain model khai báo.

Giả sử domain model có dạng:

~~~java
@Node("Movie")
public class Movie {

    @Id
    private String title;

    @Relationship(
        type = "ACTED_IN",
        direction = Relationship.Direction.INCOMING
    )
    private Set<ActingCredit> actors = new LinkedHashSet<>();
}

@RelationshipProperties
public class ActingCredit {

    @RelationshipId
    private Long id;

    private List<String> roles;

    @TargetNode
    private Person person;
}
~~~

Custom query nên trả về node gốc, các relationship và các node liên quan:

~~~java
@Query("""
    MATCH (m:Movie {title: $title})
    OPTIONAL MATCH (m)<-[r:ACTED_IN]-(p:Person)
    RETURN m, collect(r), collect(p)
    """)
Optional<Movie> findMovieWithActors(@Param("title") String title);
~~~

Các collection được gom lại để tạo một record cho Movie gốc. SDN có thể dùng record này để gắn từng relationship và node đích vào đúng entity.

### Tránh nhiều record cho cùng một root

Giả sử một Movie có 5 diễn viên. Query sau trả về 5 record, mỗi record lặp lại node Movie:

~~~cypher
MATCH (m:Movie {title: $title})
MATCH (m)<-[r:ACTED_IN]-(p:Person)
RETURN m, r, p
~~~

Khi SDN ánh xạ kết quả, Movie có thể xuất hiện lặp lại và các relationship không được gom thành một graph hoàn chỉnh như mong muốn.

Với một root entity có nhiều relationship, hãy gom các relationship và node đích:

~~~cypher
MATCH (m:Movie {title: $title})
OPTIONAL MATCH (m)<-[r:ACTED_IN]-(p:Person)
RETURN m, collect(r), collect(p)
~~~

Nếu query mở rộng nhiều nhánh độc lập, các nhánh có thể tạo Cartesian product. Khi đó hãy gom từng nhánh trước khi kết hợp chúng, hoặc dùng subquery để giữ số record phù hợp. Quy tắc quan trọng là một entity gốc cần được trả về trong một record chứa đủ dữ liệu để hydrate các relationship cần thiết.

SDN làm việc theo record; framework không tự đoán rằng nhiều record lặp cùng một root phải được hợp nhất thành một aggregate tùy ý.

### Lưu ý khi trả về path

Cypher có thể trả về một path đã đặt tên. SDN hỗ trợ một số cách ánh xạ path thành các entity trên đường đi. Tuy nhiên, nếu mục tiêu là hydrate một root entity cùng các nhánh quan hệ của nó, cần kiểm tra cấu trúc record và bảo đảm các node/relationship cần thiết đều được trả về.

Đối với query xây dựng graph cho một root, cách dễ kiểm soát thường là trả về root node cùng collection node và relationship. Không mặc định rằng một biến path đơn lẻ sẽ thay thế được mọi cấu trúc kết quả mà domain mapping cần.

## 7. Phân trang với @Query

Derived query có thể xử lý Pageable tự động. Với custom query, câu Cypher phải xử lý tham số phân trang.

Ví dụ trả về Page<Movie>:

~~~java
@Query(
    value = """
        MATCH (m:Movie)
        WHERE m.title CONTAINS $keyword
        RETURN m
        ORDER BY m.title
        SKIP $skip
        LIMIT $limit
        """,
    countQuery = """
        MATCH (m:Movie)
        WHERE m.title CONTAINS $keyword
        RETURN count(m)
        """
)
Page<Movie> findMoviePage(
    @Param("keyword") String keyword,
    Pageable pageable
);
~~~

Các điểm cần nhớ:

- Custom query cần sử dụng $skip và $limit để áp dụng phân trang.
- Page<T> cần countQuery riêng để tính tổng số phần tử.
- Slice<T> không cần biết tổng số trang nên không cần count query.
- Cung cấp thứ tự ổn định, ví dụ ORDER BY m.title.
- Với custom query, không dựa vào Sort trong Pageable để tự thay đổi thứ tự Cypher; hãy khai báo thứ tự cần dùng trong query và truyền Pageable không có sort.

Nếu không có SKIP và LIMIT trong query, kết quả có thể không tuân theo phân trang như người gọi mong đợi.

## 8. Query có thể thực hiện ghi dữ liệu

@Query có thể chứa câu Cypher đọc hoặc ghi. Ví dụ cập nhật tên một Person và trả về node đã cập nhật:

~~~java
@Query("""
    MATCH (p:Person {personId: $personId})
    SET p.fullName = $newName
    RETURN p
    """)
Optional<Person> rename(
    @Param("personId") String personId,
    @Param("newName") String newName
);
~~~

Nếu nghiệp vụ gồm nhiều thao tác cần cùng thành công hoặc rollback, đặt ranh giới transaction ở service:

~~~java
@Service
public class PersonService {

    private final PersonRepository people;

    public PersonService(PersonRepository people) {
        this.people = people;
    }

    @Transactional
    public Person rename(String id, String newName) {
        return people.rename(id, newName)
            .orElseThrow(() ->
                new IllegalArgumentException("Person not found")
            );
    }
}
~~~

Không dùng custom query chỉ đọc một phần graph rồi lấy entity đó ghi lại như thể nó chứa đầy đủ dữ liệu. Nếu query không trả về các relationship đang tồn tại, thao tác ghi sau đó có thể làm mất hoặc thay đổi dữ liệu mà query không hề tải.

Với dữ liệu trả về chỉ phục vụ màn hình hoặc báo cáo, hãy ưu tiên projection hoặc DTO. Nếu cần thay đổi một phần graph, thiết kế query và thao tác ghi sao cho phạm vi cập nhật được xác định rõ.

## 9. Khi nào nên dùng @Query?

Dùng @Query khi:

- Finder method không thể diễn đạt rõ đường đi hoặc điều kiện Cypher cần thiết.
- Cần gọi hàm Cypher, subquery, aggregation hoặc xử lý nhiều nhánh.
- Cần projection/DTO với dữ liệu tổng hợp bổ sung.
- Cần kiểm soát chính xác record trả về để SDN ánh xạ graph.

Nếu chỉ cần lọc theo property đơn giản, derived query thường ngắn gọn hơn. Nếu cần query động phức tạp, nhiều cấu trúc truy vấn khác nhau hoặc mapping tùy chỉnh, hãy cân nhắc repository fragment, Neo4jClient, Neo4jTemplate hoặc Cypher-DSL thay vì nhồi toàn bộ logic vào một chuỗi annotation dài.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy annotation khi import | Dùng package từ ví dụ SDN cũ hoặc module Spring Data khác | Dùng org.springframework.data.neo4j.repository.query.Query |
| Không bind được tham số | Tên $parameter không khớp @Param | Đối chiếu tên trong query và annotation |
| Query lỗi cú pháp khi dữ liệu có dấu nháy | Ghép chuỗi đầu vào trực tiếp vào Cypher | Dùng $parameter |
| Không tìm được label động | Cố dùng $label như một label Cypher | Dùng literal extension với giá trị đã được allowlist |
| Entity trả về thiếu relationship | Query chỉ trả root node hoặc thiếu relationship/node liên quan | Trả về các collection relationship và node cần hydrate |
| Entity gốc bị lặp | Một root tạo nhiều record do nhiều nhánh MATCH | Gom từng nhánh bằng collect và kiểm tra Cartesian product |
| DTO có giá trị null | Alias của RETURN không khớp tên property DTO | Dùng alias chính xác |
| Page có tổng số phần tử sai | Thiếu hoặc viết sai countQuery | Tạo count query có cùng điều kiện lọc |
| Page/Slice không giới hạn kết quả | Custom query thiếu $skip hoặc $limit | Thêm hai tham số phân trang vào Cypher |
| Dữ liệu mất sau khi save entity đọc từ custom query | Entity được hydrate một phần nhưng lại dùng để ghi như graph đầy đủ | Dùng projection/DTO cho đọc hoặc tải đầy đủ phần cần ghi |

## 11. Thực hành: tạo repository dùng @Query

Giả sử ứng dụng quản lý Movie và Person. Tạo repository:

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface MovieRepository extends Neo4jRepository<Movie, String> {

    @Query("""
        MATCH (m:Movie {title: $title})
        RETURN m
        """)
    Optional<Movie> findMovie(@Param("title") String title);

    @Query("""
        MATCH (m:Movie)
        WHERE m.released >= $year
        RETURN m
        ORDER BY m.released DESC, m.title
        """)
    List<Movie> findReleasedAfter(@Param("year") int year);

    @Query("""
        MATCH (m:Movie {title: $title})
        OPTIONAL MATCH (m)<-[r:ACTED_IN]-(p:Person)
        RETURN m, collect(r), collect(p)
        """)
    Optional<Movie> findMovieWithActors(@Param("title") String title);
}
~~~

Thử các thao tác:

1. Gọi findMovie với tiêu đề tồn tại và tiêu đề không tồn tại.
2. Gọi findReleasedAfter với các năm khác nhau.
3. Gọi findMovieWithActors và kiểm tra collection actors được ánh xạ đúng.
4. Thử thay collect(r), collect(p) bằng r, p, quan sát số record trả về khi phim có nhiều diễn viên.
5. Tạo DTO MovieSummary có thuộc tính title và actorCount, sau đó viết query trả về alias trùng tên hai thuộc tính.
6. Thử thêm Pageable và countQuery cho danh sách phim.

Truy vấn có thể kiểm tra trực tiếp trong Neo4j Browser trước khi đưa vào annotation:

~~~cypher
MATCH (m:Movie {title: $title})
OPTIONAL MATCH (m)<-[r:ACTED_IN]-(p:Person)
RETURN m, collect(r), collect(p)
~~~

Khi truy vấn đã chạy đúng với dữ liệu mẫu, đặt cùng câu Cypher vào @Query, khai báo tham số và kiểu trả về tương ứng.

## Kết luận

Trong Spring Data Neo4j hiện đại, annotation @Query được import từ org.springframework.data.neo4j.repository.query.Query và đặt trên phương thức repository để khai báo custom Cypher. Dùng $name cho tham số giá trị, @Param để liên kết tên rõ ràng, và chọn kiểu trả về phù hợp với record mà query tạo ra.

Khi trả về entity có relationship, hãy bảo đảm query cung cấp đủ node và relationship cần hydrate, thường bằng cách gom các nhánh trong một record cho mỗi root. Với DTO, dùng alias khớp tên thuộc tính; với Page hoặc Slice, khai báo phân trang ngay trong Cypher. Hãy dùng SpEL literal có kiểm soát cho thành phần cấu trúc như label hoặc relationship type, còn giá trị dữ liệu nên được bind thành tham số Cypher.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.2: Custom queries](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
- [Spring Data Neo4j: FAQ về Page, Slice và custom query](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j: Projections](https://docs.spring.io/spring-data/neo4j/reference/projections/sdn-projections.html)
