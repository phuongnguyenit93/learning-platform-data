# DTO constructor và Java record

Khi một use case chỉ cần vài trường dữ liệu từ Neo4j, việc tải toàn bộ entity graph thường không cần thiết. Spring Data Neo4j (SDN) cho phép truy vấn trả về DTO để biểu diễn đúng dữ liệu mà service hoặc API cần. DTO class có thể được tạo qua constructor; Java record cung cấp một cách viết gọn cho DTO bất biến với canonical constructor được xác định từ các record component.

Bài học thuộc module **SPRING_DATA_NEO4J**, tập trung vào xây dựng tầng dữ liệu đồ thị qua node entity, relationship, repository và truy vấn Cypher. Ví dụ dùng `Person`, `Movie` và `ACTED_IN` để xây dựng kết quả thống kê phim, sau đó ánh xạ kết quả sang DTO class và Java record bằng repository `@Query` hoặc `Neo4jClient`.

## 1. DTO khác entity như thế nào?

Entity SDN mô tả node trong graph và có thể chứa relationship tới các node khác. DTO mô tả hình dạng dữ liệu cho một tác vụ cụ thể, chẳng hạn một hàng thống kê hoặc dữ liệu hiển thị trên màn hình.

| Tiêu chí | Entity SDN | DTO |
|---|---|---|
| Mục đích | Đại diện node và quan hệ trong mô hình persistence | Chứa dữ liệu cần cho một use case |
| Annotation thường gặp | `@Node`, `@Relationship` | Thường không cần annotation persistence |
| Dữ liệu | Property node và relationship được ánh xạ | Các trường được truy vấn trả về |
| Lưu bằng repository | Có thể dùng `save()` nếu entity được cấu hình phù hợp | Không mặc định là đối tượng có thể lưu trực tiếp |
| Thiết kế | Theo mô hình graph/domain | Theo nhu cầu đọc hoặc trả dữ liệu |

Ví dụ, `Movie` là entity node có `title`, `released` và các relationship. Màn hình thống kê có thể chỉ cần tiêu đề phim, năm phát hành và số diễn viên. `MovieSummary` là DTO phù hợp hơn vì không cần tải toàn bộ danh sách `Person`.

## 2. Kết quả Cypher cần khớp với DTO

Hãy bắt đầu từ câu hỏi nghiệp vụ: mỗi dòng kết quả cần cung cấp trường nào? Ví dụ, đếm số diễn viên duy nhất của từng phim:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
RETURN m.title AS title,
       m.released AS released,
       count(DISTINCT p) AS actorCount
ORDER BY released DESC, title ASC;
```

Mỗi hàng có ba trường:

| Alias trong Cypher | Ý nghĩa | Kiểu Java dự kiến |
|---|---|---|
| `title` | Tiêu đề phim | `String` |
| `released` | Năm phát hành | `Integer` |
| `actorCount` | Số diễn viên duy nhất | `Long` |

Tên alias đóng vai trò hợp đồng giữa truy vấn và DTO. Với constructor mapping, hãy đặt tên tham số hoặc record component tương ứng với alias mà query trả về. Khi đổi alias, cần cập nhật DTO hoặc phần mapping thủ công cùng lúc.

## 3. DTO class với constructor

Một DTO class có thể dùng các trường `final` và constructor nhận tất cả dữ liệu cần thiết:

```java
public class MovieSummary {

    private final String title;
    private final Integer released;
    private final Long actorCount;

    public MovieSummary(
            String title,
            Integer released,
            Long actorCount) {
        this.title = title;
        this.released = released;
        this.actorCount = actorCount;
    }

    public String getTitle() {
        return title;
    }

    public Integer getReleased() {
        return released;
    }

    public Long getActorCount() {
        return actorCount;
    }
}
```

Các tham số constructor được ánh xạ từ kết quả truy vấn theo tên property. Vì vậy, `title`, `released` và `actorCount` cần khớp với alias Cypher. Kiểu tham số cũng phải tương thích với giá trị trả về. Dùng wrapper như `Integer` và `Long` nếu giá trị có thể vắng mặt hoặc là `null`.

Repository có thể khai báo phương thức trả về DTO:

```java
public interface MovieRepository extends Neo4jRepository<Movie, Long> {

    @Query("""
        MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
        RETURN m.title AS title,
               m.released AS released,
               count(DISTINCT p) AS actorCount
        ORDER BY released DESC, title ASC
        """)
    List<MovieSummary> findMovieSummaries();
}
```

Ở đây SDN ánh xạ mỗi hàng kết quả vào một `MovieSummary` thông qua constructor. `MovieSummary` không cần `@Node`, vì nó không đại diện node `Movie` để lưu trữ; nó chỉ là hình dạng kết quả mà phương thức repository trả về.

### 3.1. Tên tham số constructor

Spring Data cần đọc được tên tham số để ghép chúng với các property kết quả. Với DTO class thông thường, hãy bật tùy chọn biên dịch giữ tên tham số Java (`-parameters`). Nếu không, reflection có thể chỉ thấy tên như `arg0`, `arg1`, khiến constructor mapping không xác định được trường tương ứng.

Với Maven, có thể cấu hình compiler plugin:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

Với Gradle:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
```

Một lựa chọn khác là cung cấp tên property bằng `@ConstructorProperties` của Java Beans:

```java
import java.beans.ConstructorProperties;

@ConstructorProperties({"title", "released", "actorCount"})
public MovieSummary(String title, Integer released, Long actorCount) {
    this.title = title;
    this.released = released;
    this.actorCount = actorCount;
}
```

Thứ tự tên trong annotation phải tương ứng với thứ tự tham số constructor. Không dùng annotation này để chọn constructor khi lớp có nhiều constructor; mục đích của nó là cung cấp tên property cho các tham số.

### 3.2. Nhiều constructor và @PersistenceCreator

Nếu DTO có nhiều constructor, hãy chỉ rõ constructor mà Spring Data dùng để tạo đối tượng bằng `@PersistenceCreator` của Spring Data Commons:

```java
import org.springframework.data.annotation.PersistenceCreator;

public class MovieSummary {

    private final String title;
    private final Integer released;
    private final Long actorCount;

    @PersistenceCreator
    public MovieSummary(
            String title,
            Integer released,
            Long actorCount) {
        this.title = title;
        this.released = released;
        this.actorCount = actorCount;
    }

    public MovieSummary(String title, Integer released) {
        this(title, released, 0L);
    }
}
```

Constructor ba tham số là persistence creator vì nó nhận đầy đủ dữ liệu của query. Constructor hai tham số là tiện ích cho code ứng dụng. Đánh dấu tường minh giúp Spring Data không phải suy luận giữa nhiều cách tạo đối tượng.

Không thêm constructor tiện dụng nếu nó không mang lại giá trị rõ ràng. Một constructor đầy đủ thường là lựa chọn đơn giản nhất cho DTO bất biến.

## 4. Java record là DTO bất biến gọn nhẹ

Java record phù hợp với DTO vì các component của record xác định dữ liệu, accessor và canonical constructor. Ví dụ:

```java
public record MovieSummary(
        String title,
        Integer released,
        Long actorCount) {
}
```

Record trên tương đương về ý nghĩa dữ liệu với DTO class có ba trường, constructor và accessor. Tên component `title`, `released`, `actorCount` được lưu trong metadata của record, nên không phụ thuộc vào compiler flag `-parameters` theo cách DTO class thông thường cần.

Repository dùng cùng câu Cypher:

```java
public interface MovieRepository extends Neo4jRepository<Movie, Long> {

    @Query("""
        MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
        RETURN m.title AS title,
               m.released AS released,
               count(DISTINCT p) AS actorCount
        ORDER BY released DESC, title ASC
        """)
    List<MovieSummary> findMovieSummaries();
}
```

SDN có thể dùng canonical constructor để tạo record từ các giá trị truy vấn. Mỗi alias cần khớp với tên component và kiểu dữ liệu phải tương thích. Record không cần setter và không cần constructor không tham số.

Java record được hỗ trợ từ Java 16. Hãy bảo đảm JDK và cấu hình source/target của dự án cho phép dùng record; các dự án chạy trên baseline Java cũ hơn cần dùng DTO class thông thường.

## 5. Compact constructor để kiểm tra dữ liệu record

Record cho phép khai báo compact constructor để kiểm tra hoặc chuẩn hóa dữ liệu trước khi tạo instance:

```java
public record MovieSummary(
        String title,
        Integer released,
        Long actorCount) {

    public MovieSummary {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title is required");
        }
        if (actorCount != null && actorCount < 0) {
            throw new IllegalArgumentException("actorCount must not be negative");
        }
    }
}
```

Compact constructor không khai báo lại danh sách tham số; Java tự cung cấp các component. Sau khi phần kiểm tra hoàn tất, compiler gán các tham số vào component tương ứng.

Chỉ đặt invariant phù hợp với mọi nguồn tạo record trong compact constructor. Nếu dữ liệu từ database có thể hợp lệ dù một trường là `null`, đừng áp đặt kiểm tra bắt buộc khiến việc ánh xạ thất bại. Khi cần giá trị mặc định, hãy xác định rõ quy tắc nghiệp vụ và tránh che giấu dữ liệu thiếu ngoài dự kiến.

## 6. So sánh DTO class và Java record

| Tiêu chí | DTO class | Java record |
|---|---|---|
| Cú pháp | Nhiều mã khai báo hơn | Ngắn gọn |
| Constructor | Tự khai báo | Có canonical constructor tự sinh |
| Accessor | Thường là getter `getTitle()` | Là accessor `title()` |
| Tính bất biến | Cần thiết kế `final`, không setter | Bất biến nông theo component mặc định |
| Nhiều constructor | Có thể đánh dấu `@PersistenceCreator` | Có thể thêm constructor phụ; canonical constructor vẫn là cấu trúc chính |
| Tên tham số | Cần metadata tên tham số hoặc `@ConstructorProperties` | Tên component có sẵn trong metadata record |
| Kiểm tra đầu vào | Constructor thông thường | Có thể dùng compact constructor |
| Phiên bản Java | Dùng được trên các phiên bản Java hỗ trợ class thông thường | Cần Java 16 trở lên |

Chọn record khi DTO là cấu trúc dữ liệu gọn, bất biến và dự án dùng Java 16+. Chọn class khi cần tương thích với baseline Java cũ, cần kế thừa hoặc có vòng đời tạo đối tượng phức tạp hơn. Cả hai đều có thể làm kết quả truy vấn; chúng không tự động trở thành entity Neo4j.

## 7. Ánh xạ dữ liệu quan hệ vào DTO phẳng

DTO thường hữu ích khi kết quả truy vấn kết hợp dữ liệu từ nhiều node hoặc relationship. Ví dụ, danh sách diễn viên cùng số phim tham gia:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
RETURN p.personId AS personId,
       p.name AS personName,
       count(DISTINCT m) AS movieCount
ORDER BY movieCount DESC, personName ASC;
```

Record DTO:

```java
public record PersonActivity(
        String personId,
        String personName,
        Long movieCount) {
}
```

Repository:

```java
@Query("""
    MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
    RETURN p.personId AS personId,
           p.name AS personName,
           count(DISTINCT m) AS movieCount
    ORDER BY movieCount DESC, personName ASC
    """)
List<PersonActivity> findPersonActivity();
```

Kết quả này không cần tải danh sách `Movie` hoặc các `ActingCredit` của từng người. Neo4j thực hiện phép đếm; SDN chỉ ánh xạ ba trường đã trả về vào DTO. Cách làm này giảm lượng dữ liệu truyền về ứng dụng và làm rõ hợp đồng kết quả.

Nếu cần danh sách phim trong DTO, có thể dùng `collect(m.title) AS movieTitles` và một component `List<String> movieTitles`, nhưng cần kiểm tra kiểu dữ liệu collection được mapping hỗ trợ trong phiên bản đang dùng.

## 8. Khi nào cần @Query và khi nào dùng Neo4jClient?

Repository với `@Query` phù hợp khi câu Cypher có cấu trúc cố định và kiểu DTO trả về đã biết:

```java
@Query("""
    MATCH (m:Movie)
    WHERE m.released >= $fromYear
    OPTIONAL MATCH (p:Person)-[:ACTED_IN]->(m)
    RETURN m.title AS title,
           m.released AS released,
           count(DISTINCT p) AS actorCount
    ORDER BY released DESC
    """)
List<MovieSummary> findRecentMovies(Integer fromYear);
```

Truy vấn vẫn trả về phim không có diễn viên nhờ `OPTIONAL MATCH`; `count(DISTINCT p)` khi đó cho kết quả `0`. Ba alias tiếp tục khớp với constructor của `MovieSummary`.

`Neo4jClient` phù hợp khi cần kiểm soát mapping chi tiết, truy vấn động hoặc chuyển đổi dữ liệu phức tạp:

```java
List<MovieSummary> summaries = neo4jClient.query("""
        MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
        RETURN m.title AS title,
               m.released AS released,
               count(DISTINCT p) AS actorCount
        ORDER BY released DESC, title ASC
        """)
    .fetchAs(MovieSummary.class)
    .mappedBy((typeSystem, record) -> new MovieSummary(
        record.get("title").asString(),
        record.get("released").asInt(),
        record.get("actorCount").asLong()
    ))
    .all();
```

Với `mappedBy`, ứng dụng tự tạo DTO từ `Record`; do đó việc ghép alias với constructor được viết tường minh trong callback. Cách này hữu ích khi cần đổi tên trường, xử lý giá trị null, chuyển kiểu hoặc kết hợp nhiều cột theo quy tắc riêng.

Khi một giá trị có thể là `null`, hãy kiểm tra `record.get("...").isNull()` trước khi gọi `asString()`, `asInt()` hoặc `asLong()`. Không dùng kiểu nguyên thủy trong DTO nếu query có thể trả `null` cho component đó.

## 9. Lỗi thường gặp khi ánh xạ DTO constructor

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Constructor parameter không khớp alias | Tên tham số khác tên cột kết quả | Đồng bộ alias và tên tham số/component |
| Tên tham số thành `arg0`, `arg1` | Compiler không giữ parameter names | Bật `-parameters` hoặc dùng `@ConstructorProperties` |
| DTO có nhiều constructor nhưng chọn sai | Không chỉ định persistence creator | Đánh dấu constructor phù hợp bằng `@PersistenceCreator` |
| Kiểu Java không tương thích | Ví dụ query trả integer nhưng DTO nhận kiểu không phù hợp | Chọn kiểu tương ứng và kiểm tra mapping conversion |
| Dùng primitive cho trường có thể null | Không thể biểu diễn `null` | Dùng wrapper như `Integer`, `Long`, `Double` |
| Record component không khớp alias | SDN không tìm thấy giá trị để truyền vào canonical constructor | Đổi alias hoặc tên component cho đồng nhất |
| Dùng DTO như entity | DTO không có metadata node/ID cần thiết | Dùng DTO cho kết quả; chuyển sang entity khi cần lưu |
| DTO chứa nhiều trường nhưng query chỉ trả một phần | Constructor không nhận đủ dữ liệu | Bổ sung alias hoặc thiết kế DTO nhỏ hơn |
| Dùng record trên JDK không hỗ trợ | Source/target Java không tương thích | Nâng baseline hoặc dùng DTO class |

## 10. Quy trình thiết kế DTO kết quả

1. Xác định use case cần những trường dữ liệu nào.
2. Viết Cypher trả đúng các trường đó và đặt alias rõ ràng.
3. Chọn DTO class hoặc Java record theo baseline Java và yêu cầu thiết kế.
4. Đồng bộ alias với tên constructor parameter hoặc record component.
5. Kiểm tra kiểu dữ liệu, giá trị null và collection.
6. Nếu DTO class có nhiều constructor, đánh dấu persistence creator.
7. Dùng repository `@Query` khi mapping theo quy ước là đủ; dùng `Neo4jClient` khi cần mapping thủ công.
8. Kiểm thử trường hợp không có kết quả, giá trị null, nhiều hàng và dữ liệu relationship không đầy đủ.

## 11. Bài tập thực hành

1. Tạo DTO class `MovieSummary` có `title`, `released`, `actorCount` và constructor tương ứng.
2. Viết Cypher thống kê số diễn viên của mỗi phim; đặt alias khớp constructor.
3. Tạo repository method `findMovieSummaries()` trả về `List<MovieSummary>`.
4. Tắt `-parameters`, quan sát ảnh hưởng đến constructor mapping rồi khắc phục bằng compiler option hoặc `@ConstructorProperties`.
5. Thêm constructor tiện ích cho `MovieSummary`, đánh dấu constructor persistence bằng `@PersistenceCreator`.
6. Chuyển DTO class thành `record MovieSummary(...)` và so sánh số lượng mã cần viết.
7. Thêm compact constructor để kiểm tra `title` và `actorCount`; xác định trường hợp nào nên chấp nhận `null`.
8. Dùng `Neo4jClient.fetchAs(...).mappedBy(...)` để ánh xạ cùng truy vấn thành record.
9. Viết DTO `PersonActivity` từ truy vấn tổng hợp và giải thích vì sao không cần tải entity graph đầy đủ.

Khi hoàn thành, bạn cần biết cách thiết kế constructor DTO theo alias của Cypher, khi nào cần `@PersistenceCreator`, cách Java record dùng canonical constructor và lúc nào nên chọn mapping tự động qua repository hay mapping tường minh qua `Neo4jClient`. Những kỹ năng này giúp tầng đọc của Spring Data Neo4j trả về dữ liệu gọn, rõ ràng và phù hợp với từng use case.
