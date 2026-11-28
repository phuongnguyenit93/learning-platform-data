# Record của Neo4j khác gì entity trong mô hình miền?

Khi chạy Cypher bằng Neo4j Java Driver, kết quả được trả về dưới dạng các `Record`. Một `Record` biểu diễn một hàng kết quả với các trường có tên và giá trị tương ứng. Trong Spring Data Neo4j (SDN), entity như `Person` hoặc `Movie` lại biểu diễn một đối tượng trong mô hình ứng dụng, được ánh xạ từ node và relationship của đồ thị. Hai khái niệm có thể chứa dữ liệu liên quan đến cùng một người hoặc bộ phim, nhưng chúng có vai trò và cấu trúc khác nhau.

Bài học thuộc module **SPRING_DATA_NEO4J**, tập trung vào xây dựng tầng dữ liệu đồ thị qua node entity, relationship, repository và truy vấn Cypher. Ví dụ dùng `Person`, `Movie` và `ACTED_IN` để phân biệt kết quả dạng hàng của driver với entity miền, đồng thời chọn cách ánh xạ phù hợp khi dùng repository, `@Query` hoặc `Neo4jClient`.

## 1. Record là một hàng kết quả của truy vấn

Neo4j lưu dữ liệu dưới dạng graph gồm node, relationship và property. Khi chạy truy vấn, Cypher tạo ra một luồng kết quả gồm các hàng. Mỗi hàng là một `Record`; mỗi cột được xác định bởi tên hoặc alias trong mệnh đề `RETURN`.

Ví dụ:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
RETURN p.name AS actorName,
       m.title AS movieTitle;
```

Nếu một diễn viên tham gia ba phim, truy vấn có thể trả về ba hàng:

| actorName | movieTitle |
|---|---|
| Keanu Reeves | The Matrix |
| Keanu Reeves | John Wick |
| Keanu Reeves | Speed |

Mỗi hàng là một `Record` có hai trường `actorName` và `movieTitle`. `Record` không phải node `Person`, cũng không phải một entity `Person` được SDN quản lý. Nó chỉ mô tả dữ liệu của một hàng trong kết quả truy vấn đó.

Trong Java Driver, kiểu `org.neo4j.driver.Record` cung cấp cách truy cập các trường của hàng. Gọi `record.get("actorName")` trả về một `Value`; từ `Value`, ứng dụng chuyển sang kiểu Java phù hợp như chuỗi, số, boolean, node hoặc relationship.

## 2. Entity là đối tượng trong mô hình ứng dụng

Entity SDN là lớp Java được ánh xạ với node trong Neo4j bằng annotation `@Node`. Các trường của lớp đại diện cho property của node; thuộc tính có `@Relationship` mô tả các liên kết tới node khác.

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
    private Integer born;

    // Constructor, getter và setter được lược bỏ.
}
```

Khi repository đọc entity:

```java
Optional<Person> person = personRepository.findById(id);
```

SDN dùng mapping metadata để chuyển dữ liệu Neo4j thành một instance `Person`. Instance này phù hợp với kiểu dữ liệu và hành vi mà tầng service/domain sử dụng. Entity có thể chứa ID, version, relationship properties, phương thức nghiệp vụ và các invariant mà một hàng kết quả thô không có.

Trong nhiều ứng dụng, lớp `@Node` vừa là persistence entity vừa được dùng trong domain model. Ở ứng dụng có domain model phức tạp, có thể tách persistence entity khỏi domain object và chuyển đổi giữa hai kiểu. Dù chọn cách nào, cần phân biệt vai trò của entity với hàng kết quả do driver trả về.

## 3. Record, Value, Node và entity không phải cùng một kiểu

Các kiểu sau xuất hiện ở những tầng khác nhau:

| Kiểu | Package tiêu biểu | Ý nghĩa |
|---|---|---|
| `Record` | `org.neo4j.driver.Record` | Một hàng kết quả truy vấn, chứa các trường được đặt tên |
| `Value` | `org.neo4j.driver.Value` | Giá trị của một trường trong `Record`; có thể là scalar hoặc giá trị graph |
| `Node` | `org.neo4j.driver.types.Node` | Node ở mức API của Neo4j Java Driver |
| `Relationship` | `org.neo4j.driver.types.Relationship` | Relationship ở mức API của driver |
| `Person` | Lớp ứng dụng có `@Node("Person")` | Entity Java do SDN ánh xạ |

Nếu Cypher trả về:

```cypher
MATCH (p:Person {name: $name})
RETURN p AS person;
```

kết quả vẫn là một `Record` có trường `person`. Giá trị trường đó là một `Value` có thể biểu diễn node. Việc `RETURN p` không tự biến hàng kết quả thành entity `Person`; tầng SDN phải thực hiện mapping nếu ứng dụng muốn nhận entity.

Tương tự, `RETURN p.name AS name` trả về một trường scalar, không phải một node. `RETURN p, m` trả về hai giá trị graph trong cùng một hàng; `RETURN p, m.title AS title` trộn một giá trị node và một scalar. Hình dạng kết quả phụ thuộc hoàn toàn vào biểu thức được trả về.

## 4. Record là dữ liệu theo hàng; entity có thể đại diện một phần graph

Một hàng kết quả thường mô tả một tổ hợp giá trị. Entity lại được thiết kế quanh một thực thể trong mô hình ứng dụng và có thể chứa quan hệ tới các thực thể khác.

Ví dụ truy vấn:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
RETURN p AS person, m AS movie;
```

Nếu một người đóng trong nhiều phim, người đó xuất hiện trong nhiều `Record`, mỗi hàng có cùng node `person` nhưng node `movie` khác nhau. Không thể kết luận rằng mỗi hàng là một `Person` riêng.

Nếu mục tiêu là một đối tượng thống kê cho mỗi người, có thể tổng hợp kết quả:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
RETURN p.personId AS personId,
       p.name AS name,
       collect(m.title) AS movieTitles,
       count(DISTINCT m) AS movieCount;
```

Lúc này mỗi hàng có thể mô tả một `PersonSummary` với danh sách phim và số lượng phim. `PersonSummary` là DTO/projection phục vụ một use case; nó không nhất thiết là entity `Person` có thể lưu ngược lại bằng repository.

## 5. Đọc Record trực tiếp từ Neo4j Java Driver

Khi làm việc trực tiếp với driver, mỗi `Record` cung cấp các trường đã được truy vấn trả về. Ví dụ minh họa:

```java
try (var session = driver.session()) {
    var result = session.run("""
        MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
        WHERE p.name = $name
        RETURN p.name AS actorName,
               m.title AS movieTitle
        ORDER BY movieTitle
        """, Map.of("name", "Keanu Reeves"));

    while (result.hasNext()) {
        org.neo4j.driver.Record record = result.next();

        String actorName = record.get("actorName").asString();
        String movieTitle = record.get("movieTitle").asString();

        System.out.println(actorName + " - " + movieTitle);
    }
}
```

Đoạn code dùng Java Driver trực tiếp. `record.get(...)` trả về `Value`; `asString()` chuyển giá trị sang `String`. Tên `actorName` và `movieTitle` phải trùng với alias trong `RETURN`. Nếu đổi alias mà không đổi code đọc record, ứng dụng có thể báo lỗi vì không tìm thấy trường tương ứng.

Khi cần kiểm tra dữ liệu tùy chọn, đừng gọi ngay `asString()` hoặc `asLong()` trên một giá trị có thể là `null`. Hãy kiểm tra `Value.isNull()` trước hoặc dùng cách chuyển đổi có giá trị mặc định phù hợp. Chọn phương thức chuyển đổi đúng kiểu: `asLong()` cho số nguyên dài, `asDouble()` cho số thực, `asBoolean()` cho boolean.

## 6. Ánh xạ kết quả thành entity qua repository

Nếu mục tiêu là làm việc với entity trong mô hình SDN, hãy ưu tiên repository. Ví dụ:

```java
public interface PersonRepository extends Neo4jRepository<Person, Long> {

    Optional<Person> findByName(String name);
}
```

Spring Data phân tích tên phương thức, thực thi truy vấn phù hợp và ánh xạ kết quả sang `Person`. Service không cần tự đọc `Record` hoặc tự chuyển từng property.

Với truy vấn Cypher tùy chỉnh, repository có thể dùng `@Query`:

```java
public interface PersonRepository extends Neo4jRepository<Person, Long> {

    @Query("""
        MATCH (p:Person {personId: $personId})
        RETURN p
        """)
    Optional<Person> findGraphPerson(String personId);
}
```

Trong trường hợp này, `RETURN p` cung cấp node để SDN ánh xạ vào kiểu `Person`. Nếu entity cần relationship hoặc dữ liệu bổ sung, câu truy vấn phải trả về đủ cấu trúc mà mapping của entity yêu cầu. Không nên giả định chỉ trả về node gốc là đủ để materialize mọi relationship ở mọi độ sâu.

## 7. Khi kết quả là DTO hoặc projection

Nhiều truy vấn không nhằm tải một entity đầy đủ. Ví dụ màn hình thống kê cần mã người, tên và số phim. Có thể khai báo projection:

```java
public interface PersonMovieStats {
    String getPersonId();
    String getName();
    Long getMovieCount();
}
```

Repository trả về projection với alias tương ứng:

```java
public interface PersonRepository extends Neo4jRepository<Person, Long> {

    @Query("""
        MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
        RETURN p.personId AS personId,
               p.name AS name,
               count(DISTINCT m) AS movieCount
        ORDER BY name
        """)
    List<PersonMovieStats> findMovieStats();
}
```

Tên alias trong `RETURN` cần khớp với property mà projection yêu cầu. Projection là hình dạng kết quả dành cho use case; nó không tự động trở thành entity có thể gọi `save()`.

Khi dùng DTO class hoặc Java record thay vì interface projection, hãy kiểm tra quy tắc constructor mapping và kiểu dữ liệu mà phiên bản SDN đang sử dụng hỗ trợ. Với kết quả phức tạp, có thể chủ động ánh xạ bằng `Neo4jClient`.

## 8. Dùng Neo4jClient để ánh xạ Record thành DTO

`Neo4jClient` cho phép ứng dụng kiểm soát Cypher và cách chuyển từng hàng kết quả sang kiểu Java. Đây là ranh giới rõ giữa API driver và DTO ứng dụng.

Ví dụ DTO:

```java
public record PersonMovieSummary(
        String personId,
        String name,
        long movieCount) {
}
```

Ví dụ mapping:

```java
List<PersonMovieSummary> summaries = neo4jClient.query("""
        MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
        RETURN p.personId AS personId,
               p.name AS name,
               count(DISTINCT m) AS movieCount
        ORDER BY name
        """)
    .fetchAs(PersonMovieSummary.class)
    .mappedBy((typeSystem, record) -> new PersonMovieSummary(
        record.get("personId").asString(),
        record.get("name").asString(),
        record.get("movieCount").asLong()
    ))
    .all();
```

Ở đây `record` là một `org.neo4j.driver.Record` được cung cấp cho callback mapping. `mappedBy` chuyển hàng kết quả thành `PersonMovieSummary`; `all()` thu thập các DTO thành danh sách. Callback phải đọc đúng alias và chuyển đúng kiểu. Nếu trường có thể null, cần xử lý null trước khi gọi phương thức chuyển đổi.

Không cần chuyển `Record` thành entity chỉ để hiển thị một báo cáo. DTO/projection giúp kết quả chỉ chứa dữ liệu mà use case cần và tránh tạo một object graph lớn không cần thiết.

## 9. Chọn cách ánh xạ theo mục đích

| Mục đích | API phù hợp | Kiểu kết quả thường dùng |
|---|---|---|
| Đọc, lưu và cập nhật một entity | `Neo4jRepository` | `Person`, `Movie`, `Optional<Person>` |
| Truy vấn Cypher nhưng vẫn muốn entity SDN | Repository với `@Query` | Entity hoặc collection entity |
| Trả về một tập trường cho màn hình/báo cáo | Projection hoặc DTO | `PersonMovieStats`, `PersonMovieSummary` |
| Kiểm soát từng trường của kết quả driver | `Neo4jClient` với `fetchAs(...).mappedBy(...)` | DTO hoặc kiểu Java tùy chỉnh |
| Làm việc trực tiếp ở tầng driver | Neo4j Java Driver | `Record`, `Value`, `Node`, `Relationship`, `Path` |

Một quy tắc hữu ích: nếu service cần hành vi và quan hệ của một thực thể trong mô hình, trả entity; nếu service chỉ cần dữ liệu cho một tác vụ hoặc màn hình, trả projection/DTO; nếu cần điều khiển mapping chi tiết ở mức hàng driver, dùng `Neo4jClient` hoặc driver trực tiếp.

## 10. Các lỗi thường gặp khi nhầm Record với entity

| Nhầm lẫn | Hệ quả | Cách xử lý |
|---|---|---|
| Coi một `Record` là một node | Diễn giải sai cấu trúc hàng kết quả | Kiểm tra alias và giá trị từng trường |
| Coi `RETURN p` là tự động trả về `Person` | Lẫn kiểu driver với kiểu SDN | Dùng repository mapping hoặc ánh xạ qua `Neo4jClient` |
| Dùng `record.get("name").asString()` khi trường có thể null | Lỗi chuyển đổi tại runtime | Kiểm tra `Value.isNull()` trước khi chuyển |
| Đổi alias Cypher nhưng quên sửa callback | Không tìm thấy key hoặc đọc sai dữ liệu | Đồng bộ alias với tên projection/DTO |
| Trả về nhiều hàng rồi coi mỗi hàng là một aggregate | Một entity xuất hiện lặp lại theo từng relationship | Dùng `collect`, `DISTINCT` hoặc nhóm kết quả đúng nhu cầu |
| Dùng DTO như entity để gọi `save()` | DTO thiếu mapping metadata và trạng thái persistence | Chuyển đổi DTO sang entity hoặc dùng repository phù hợp |
| Trả về entity cho báo cáo chỉ cần vài scalar | Tải dữ liệu không cần thiết và tạo coupling | Dùng projection hoặc DTO |

## 11. Checklist thiết kế result mapping

- Đọc rõ các biểu thức trong `RETURN` và alias của từng trường.
- Xác định kết quả là scalar, node, relationship, path hay tổ hợp nhiều giá trị.
- Không nhầm `org.neo4j.driver.Record` với entity `@Node` hoặc Java `record`.
- Nếu cần entity, dùng repository mapping và trả về cấu trúc phù hợp với entity.
- Nếu cần projection, đặt alias khớp tên getter/property.
- Nếu dùng `Neo4jClient`, chuyển từng `Value` sang kiểu Java đúng và xử lý null.
- Nếu truy vấn tạo nhiều hàng cho cùng node, cân nhắc `DISTINCT` hoặc aggregation.
- Chỉ trả về các trường cần thiết để tránh tải dư dữ liệu.
- Kiểm thử mapping với dữ liệu có quan hệ không tồn tại, property null và nhiều relationship.

## 12. Bài tập thực hành

1. Chạy Cypher trả về `p.name AS actorName` và `m.title AS movieTitle`; giải thích vì sao mỗi hàng là một `Record`.
2. Dùng Neo4j Java Driver đọc hai alias từ `Record` và chuyển `Value` sang `String`.
3. Viết `PersonRepository.findByName` và so sánh kiểu kết quả với việc đọc `Record` trực tiếp.
4. Viết `@Query` trả về node `p` và ánh xạ thành `Person`.
5. Viết projection `PersonMovieStats` với `personId`, `name`, `movieCount` và bảo đảm alias Cypher khớp.
6. Dùng `Neo4jClient.fetchAs(...).mappedBy(...)` để chuyển `Record` thành DTO `PersonMovieSummary`.
7. Tạo truy vấn có một người tham gia nhiều phim; so sánh số hàng trước và sau khi dùng `collect(m.title)`.
8. Thử trường hợp property có thể null và xử lý `Value` trước khi gọi `asString()`.

Khi hoàn thành, bạn cần giải thích được `Record` là một hàng kết quả của driver, `Value` là giá trị của một trường, còn entity là đối tượng được SDN ánh xạ vào mô hình ứng dụng. Từ đó, bạn có thể chọn repository, projection, DTO hoặc `Neo4jClient` theo đúng hình dạng dữ liệu và trách nhiệm của tầng đang xử lý.
