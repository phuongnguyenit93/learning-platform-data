# Trả entity, scalar hoặc DTO theo mục tiêu truy vấn

Với Spring Data Neo4j (SDN), một câu Cypher tùy chỉnh có thể trả về node để ánh xạ thành entity, một giá trị đơn như số hoặc chuỗi, hoặc một cấu trúc dữ liệu gọn cho màn hình và API. Kiểu trả về của repository method nên phản ánh chính xác dữ liệu mà ca sử dụng cần.

Nếu chỉ cần đếm số kết nối, trả về một số nguyên sẽ rõ ràng và nhẹ hơn việc tải toàn bộ node liên quan. Nếu cần hiển thị vài trường, projection hoặc DTO tránh đưa cả entity graph vào tầng trình bày. Nếu nghiệp vụ cần làm việc với entity và quan hệ đã mô hình hóa, hãy trả về node cùng phần graph cần ánh xạ.

## 1. Ba kiểu kết quả thường gặp

| Kiểu kết quả | Ví dụ Cypher | Kiểu Java thường dùng | Khi phù hợp |
| --- | --- | --- | --- |
| Entity | `RETURN p` | `Person`, `Optional<Person>`, `List<Person>` | Cần làm việc với node theo mô hình domain |
| Scalar | `RETURN count(p) AS total` | `Long`, `Boolean`, `String`, `List<String>` | Chỉ cần một giá trị hoặc một cột đơn giản |
| Projection/DTO | `RETURN p.id AS id, p.name AS name` | Interface projection hoặc DTO | Cần một tập trường cụ thể cho use case |

Không có kiểu trả về nào luôn tốt nhất. Hãy bắt đầu từ câu hỏi nghiệp vụ: caller cần thay đổi entity, hiển thị vài trường, hay chỉ cần một kết quả tính toán? Câu trả lời quyết định cả phần `RETURN` của Cypher lẫn kiểu Java ở repository.

## 2. Trả về entity khi cần mô hình domain

Giả sử entity `Person` được ánh xạ từ node có nhãn `Person`:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {
    @Id
    private String id;

    private String name;

    private String status;

    // Constructor, getter và setter được lược bỏ.
}
~~~

Khi cần đọc node theo ID bằng Cypher tùy chỉnh, repository có thể trả về entity:

~~~java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (p:Person {id: $personId})
        RETURN p
        """)
    Optional<Person> findPersonGraphById(@Param("personId") String personId);
}
~~~

`RETURN p` trả về node `Person` để SDN ánh xạ các property mà entity khai báo. `Optional<Person>` phù hợp khi truy vấn dự kiến trả về không quá một node; nếu có thể có nhiều kết quả, hãy dùng `List<Person>` hoặc kiểu collection phù hợp.

Nếu entity có các trường `@Relationship` và use case cần các quan hệ đó, truy vấn phải cung cấp phần graph cần thiết cho mapper. Ví dụ, để lấy người cùng các nhóm liên quan, truy vấn cần trả về node và relationship tương ứng, thay vì chỉ trả về `p`:

~~~cypher
MATCH (p:Person {id: $personId})-[r:MEMBER_OF]->(team:Team)
RETURN p, r, team
~~~

Hình dạng dữ liệu graph trả về cần tương thích với entity mapping và phiên bản SDN đang sử dụng. Với quan hệ nhiều nhánh, hãy kiểm tra kết quả thực tế và tránh trả về các node hoặc relationship ngoài phạm vi domain cần thiết. Nếu caller chỉ cần tên nhóm, projection thường phù hợp hơn việc dựng cả graph.

## 3. Trả về scalar cho kết quả đơn giản

Scalar là một giá trị đơn như số lượng, chuỗi, boolean hoặc thời điểm. Ví dụ đếm số người đang hoạt động:

~~~java
@Query("""
    MATCH (p:Person {status: $status})
    RETURN count(p) AS total
    """)
Long countByStatus(@Param("status") String status);
~~~

`count(p)` tạo một hàng kết quả với giá trị số. Neo4j Driver biểu diễn số nguyên Cypher dưới dạng số nguyên 64-bit, nên `Long` là lựa chọn phù hợp cho số đếm có thể lớn. Nếu nghiệp vụ cần một giá trị luôn có kết quả, có thể dùng kiểu primitive tương ứng, nhưng kiểu wrapper giúp thể hiện khả năng `null` khi truy vấn không trả hàng.

Truy vấn có thể trả về boolean để kiểm tra tồn tại:

~~~java
@Query("""
    MATCH (p:Person {id: $personId})
    RETURN count(p) > 0 AS found
    """)
Boolean existsPerson(@Param("personId") String personId);
~~~

Hoặc trả về danh sách một cột:

~~~java
@Query("""
    MATCH (p:Person {status: $status})
    RETURN p.name AS name
    ORDER BY name
    """)
List<String> findNamesByStatus(@Param("status") String status);
~~~

Khi truy vấn chỉ trả về một cột scalar, hãy chọn kiểu Java tương ứng với kiểu Cypher. Không khai báo `Person` làm kiểu trả về nếu Cypher chỉ trả `p.name`; mapper không thể dựng một entity đầy đủ từ một chuỗi tên.

## 4. Trả về interface projection khi chỉ cần một phần dữ liệu

Projection cho phép định nghĩa một hợp đồng đọc chỉ gồm những trường mà use case cần. Ví dụ trang danh bạ chỉ hiển thị ID và tên:

~~~java
public interface PersonSummary {
    String getId();
    String getName();
}
~~~

Repository trả về projection bằng cách đặt alias trong Cypher khớp với tên property/getter:

~~~java
@Query("""
    MATCH (p:Person {status: $status})
    RETURN p.id AS id,
           p.name AS name
    ORDER BY name
    """)
List<PersonSummary> findSummariesByStatus(@Param("status") String status);
~~~

Alias `id` khớp với `getId()` và alias `name` khớp với `getName()`. Việc đặt alias rõ ràng giúp hợp đồng giữa truy vấn và Java dễ đọc, đồng thời tránh phụ thuộc vào tên biểu thức mặc định của Cypher.

Có thể thêm trường tính toán vào projection. Ví dụ, trang hồ sơ cần tên và số người theo dõi:

~~~java
public interface PersonProfileView {
    String getId();
    String getName();
    Long getFollowerCount();
}
~~~

~~~java
@Query("""
    MATCH (p:Person {id: $personId})
    OPTIONAL MATCH (p)<-[:FOLLOWS]-(follower:Person)
    RETURN p.id AS id,
           p.name AS name,
           count(DISTINCT follower) AS followerCount
    """)
Optional<PersonProfileView> findProfile(@Param("personId") String personId);
~~~

`OPTIONAL MATCH` giữ lại người được tìm ngay cả khi chưa có follower. Khi không có follower, `count(DISTINCT follower)` trả về 0. Kết quả chỉ chứa ba trường được yêu cầu, thay vì tải danh sách follower hoặc toàn bộ entity graph.

## 5. Dùng DTO class hoặc record

Interface projection phù hợp với nhiều truy vấn đọc cố định. Nếu ứng dụng muốn trả về một kiểu dữ liệu cụ thể do mình quản lý, có thể dùng DTO class hoặc Java record. Với kết quả Cypher động hoặc khi cần kiểm soát rõ việc chuyển kiểu, `Neo4jClient` cho phép ánh xạ từng cột thành DTO:

~~~java
public record PersonProfileDto(
    String id,
    String name,
    Long followerCount
) {}
~~~

~~~java
import java.util.Optional;

import org.springframework.data.neo4j.core.Neo4jClient;

public class PersonReadService {
    private final Neo4jClient neo4jClient;

    public PersonReadService(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public Optional<PersonProfileDto> findProfile(String personId) {
        return neo4jClient.query("""
                MATCH (p:Person {id: $personId})
                OPTIONAL MATCH (p)<-[:FOLLOWS]-(follower:Person)
                RETURN p.id AS id,
                       p.name AS name,
                       count(DISTINCT follower) AS followerCount
                """)
            .bind(personId).to("personId")
            .fetchAs(PersonProfileDto.class)
            .mappedBy((typeSystem, record) -> new PersonProfileDto(
                record.get("id").asString(),
                record.get("name").asString(),
                record.get("followerCount").asLong()
            ))
            .one();
    }
}
~~~

Ở đây, `mappedBy` chuyển các giá trị trong record của Neo4j Driver thành constructor arguments của record Java. Cách này làm rõ kiểu dữ liệu và quy tắc chuyển đổi, đặc biệt hữu ích khi kết quả chứa giá trị có thể vắng mặt hoặc kiểu dữ liệu đặc thù. Hãy kiểm tra giá trị có thể `null` trước khi gọi các hàm như `asString()` hoặc `asLong()` nếu truy vấn không bảo đảm trường luôn có giá trị.

## 6. Chọn số lượng kết quả phù hợp

Kiểu trả về còn thể hiện kỳ vọng về số hàng mà truy vấn tạo ra:

| Kiểu Java | Ý nghĩa sử dụng |
| --- | --- |
| `Person` | Một entity, khi truy vấn bảo đảm có một kết quả phù hợp |
| `Optional<Person>` | Không hoặc một entity |
| `List<Person>` | Không hoặc nhiều entity |
| `Long`, `Boolean`, `String` | Một giá trị scalar |
| `List<String>` | Nhiều giá trị scalar cùng kiểu |
| `Optional<PersonSummary>` | Không hoặc một projection |
| `List<PersonSummary>` | Nhiều projection |

Nếu truy vấn có thể trả về nhiều hàng nhưng method khai báo kiểu đơn, hãy sửa truy vấn để giới hạn đúng một kết quả hoặc đổi kiểu trả về. Không dùng `LIMIT 1` chỉ để che giấu việc điều kiện lọc không đủ chính xác; nếu có nhiều node cùng khớp, cần quyết định quy tắc chọn node bằng `ORDER BY` và tiêu chí nghiệp vụ.

Với aggregate như `count`, truy vấn thường trả về một hàng ngay cả khi không có node nào khớp. Với truy vấn tìm node thông thường, không có kết quả có thể dẫn đến `Optional.empty()` hoặc collection rỗng tùy kiểu trả về.

## 7. Tránh trả về quá nhiều dữ liệu

Một lỗi thường gặp là trả về entity graph trong khi API chỉ cần vài trường. Ví dụ, màn hình danh sách chỉ cần ID và tên nhưng repository lại trả về `List<Person>` có các relationship lớn. Điều đó có thể làm tăng dữ liệu đọc, chi phí ánh xạ object và payload API.

Hãy dùng các quy tắc sau:

1. Nếu cần cập nhật entity hoặc áp dụng hành vi domain, trả entity và tải các quan hệ cần thiết.
2. Nếu chỉ cần số lượng, tổng hợp bằng Cypher và trả scalar.
3. Nếu cần vài trường cố định, trả interface projection hoặc DTO.
4. Nếu kết quả có cấu trúc động, dùng `Neo4jClient` và ánh xạ record rõ ràng.
5. Chỉ trả về các node, relationship và property cần thiết trong phần `RETURN`.

Tránh `RETURN *` trong truy vấn phục vụ API. Nó làm hợp đồng kết quả phụ thuộc vào toàn bộ biến đang có trong `MATCH`, dễ gây dư dữ liệu và khiến việc ánh xạ khó kiểm soát khi truy vấn mở rộng.

## 8. Kiểm tra alias và kiểu dữ liệu

Khi một truy vấn trả về DTO hoặc projection, alias và kiểu dữ liệu phải khớp với hợp đồng Java. Ví dụ:

| Cypher | Kiểu Java thường dùng |
| --- | --- |
| `p.id` dạng chuỗi | `String` |
| `p.age` dạng số nguyên | `Long` hoặc kiểu số phù hợp sau chuyển đổi |
| `count(p)` | `Long` |
| `p.active` | `Boolean` |
| `collect(p.name)` | `List<String>` |

Nếu alias bị đổi từ `followerCount` thành `followers`, projection có getter `getFollowerCount()` sẽ không còn khớp. Hãy xem alias như một phần hợp đồng của method repository và cập nhật kiểm thử khi thay đổi.

Với ngày giờ, số thập phân, danh sách và giá trị có thể null, hãy chọn kiểu Java tương ứng và kiểm tra conversion của phiên bản Neo4j Driver/SDN đang dùng. Không ép kiểu tùy tiện chỉ để làm cho code biên dịch.

## 9. Kiểm thử truy vấn và kiểu trả về

Mỗi method `@Query` nên có kiểm thử tích hợp với Neo4j hoặc môi trường kiểm thử tương thích. Các trường hợp cơ bản gồm:

- Có đúng một node phù hợp và node được ánh xạ thành entity.
- Không có node phù hợp và `Optional` hoặc collection thể hiện đúng kết quả rỗng.
- Truy vấn scalar trả đúng kiểu và giá trị, kể cả trường hợp không có node khớp.
- Projection/DTO nhận đúng alias và kiểu dữ liệu.
- Truy vấn trả nhiều hàng không bị khai báo nhầm thành kết quả đơn.
- Relationship cần thiết có trong graph trả về khi method cần ánh xạ quan hệ.

Ví dụ kiểm thử có thể xác nhận tổng số người theo trạng thái:

~~~java
assertThat(personRepository.countByStatus("ACTIVE")).isEqualTo(3L);
~~~

Đồng thời, kiểm tra projection chỉ chứa các trường mong muốn và không làm tải thêm relationship không cần thiết. Kiểm thử truy vấn là cách phát hiện sớm lỗi alias, kiểu trả về và thay đổi hình dạng kết quả.

## 10. Bài tập tự kiểm tra

1. Khi nào repository method nên trả về `Person` thay vì `PersonSummary`?
2. Vì sao truy vấn `RETURN count(p) AS total` phù hợp với kiểu `Long`?
3. Alias trong Cypher cần tương ứng với projection Java như thế nào?
4. Khi nào nên dùng `Neo4jClient.fetchAs(...).mappedBy(...)` để tạo DTO?
5. Vì sao `RETURN p` có thể chưa đủ nếu use case cần ánh xạ các relationship liên quan?
6. Những vấn đề nào có thể xảy ra nếu method trả một entity nhưng truy vấn thực tế tạo nhiều hàng?

Khi hoàn thành bài học, bạn cần lựa chọn được entity, scalar hoặc DTO/projection theo mục tiêu truy vấn, đồng thời thiết kế phần `RETURN`, alias và kiểu Java nhất quán. Đây là nền tảng để viết Cypher tùy chỉnh rõ ràng, tiết kiệm dữ liệu và dễ kiểm thử trong Spring Data Neo4j.
