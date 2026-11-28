# Bài tập mở rộng: gợi ý phim, tìm đường liên kết và tìm kiếm chuyên biệt

Trong ứng dụng khám phá phim, người dùng muốn nhận gợi ý phim dựa trên những gì người có sở thích gần giống đã xem và đánh giá, tìm đường liên kết giữa hai diễn viên thông qua các bộ phim họ cùng tham gia, đồng thời tìm nội dung phim theo từ khóa trong tiêu đề và phần mô tả. Đây là ba bài toán graph khác nhau: recommendation, path finding và full-text search.

Bài capstone này xây dựng một graph phim bằng Spring Data Neo4j (SDN), sau đó triển khai ba truy vấn chuyên biệt bằng Cypher và ánh xạ kết quả thành DTO. Ta sẽ dùng node `Person`, `Movie`, `Genre`; relationship `ACTED_IN`, `RATED`, `DIRECTED`, `IN_GENRE`; relationship properties cho vai diễn và điểm đánh giá; cùng full-text index cho nội dung phim.

## 1. Yêu cầu nghiệp vụ

Ứng dụng cần hỗ trợ ba chức năng:

1. **Gợi ý phim:** tìm phim người dùng chưa đánh giá, dựa trên những người dùng khác có cùng sở thích và đã đánh giá cao các phim họ cùng xem.
2. **Tìm đường liên kết:** tìm đường ngắn nhất giữa hai người thông qua các phim họ cùng tham gia diễn xuất.
3. **Tìm kiếm chuyên biệt:** tìm phim bằng từ hoặc cụm từ xuất hiện trong tiêu đề và phần mô tả, đồng thời trả về relevance score để xếp hạng.

Mỗi chức năng trả một read model riêng. Không cần tải toàn bộ graph phim vào entity rồi xử lý recommendation, path và search trong Java. Cypher sẽ thực hiện phần truy vấn graph; SDN ánh xạ các cột kết quả thành DTO.

## 2. Thiết kế graph phim

Mô hình gồm ba loại node:

| Node | Property chính | Vai trò |
|---|---|---|
| `Person` | `personId`, `name`, `born` | Diễn viên, đạo diễn hoặc người dùng đánh giá phim |
| `Movie` | `movieId`, `title`, `overview`, `releaseYear` | Phim cần tìm kiếm và gợi ý |
| `Genre` | `genreId`, `name` | Thể loại phim |

Các relationship:

| Relationship | Hướng | Property | Ý nghĩa |
|---|---|---|---|
| `ACTED_IN` | Person → Movie | `roleName`, `billingOrder` | Một người tham gia diễn xuất trong phim |
| `DIRECTED` | Person → Movie | — | Một người đạo diễn phim |
| `RATED` | Person → Movie | `score`, `ratedAt` | Một người đánh giá phim |
| `IN_GENRE` | Movie → Genre | — | Phim thuộc một thể loại |

Sơ đồ khái quát:

```text
(:Person)-[:ACTED_IN {roleName, billingOrder}]->(:Movie)
    |                                           |
    +--[:DIRECTED]------------------------------+
    |
    +--[:RATED {score, ratedAt}]--------------->(:Movie)

(:Movie)-[:IN_GENRE]->(:Genre)
```

`Person` là node dùng chung cho người tham gia làm phim và người đánh giá. Trong ứng dụng thực tế, có thể tách `User` và `Person` nếu tài khoản người dùng và hồ sơ diễn viên có vòng đời, bảo mật hoặc thuộc tính khác nhau. Trong capstone, dùng chung một node giúp truy vấn collaborative filtering dễ theo dõi.

## 3. Xác định dữ liệu thuộc node hay relationship

Một bộ phim có `title`, `overview` và `releaseYear` độc lập với người xem, vì vậy các property này thuộc node `Movie`. Tên vai diễn và thứ tự credit chỉ có ý nghĩa trong quan hệ giữa diễn viên và một bộ phim, nên đặt trên `ACTED_IN`. Điểm đánh giá và thời điểm đánh giá thuộc quan hệ giữa người dùng và phim, nên đặt trên `RATED`.

| Dữ liệu | Lưu ở đâu? | Lý do |
|---|---|---|
| Tên diễn viên | `Person.name` | Thuộc về người đó |
| Tên phim | `Movie.title` | Thuộc về bộ phim |
| Vai diễn | `ACTED_IN.roleName` | Một người có thể đóng vai khác nhau ở từng phim |
| Thứ tự credit | `ACTED_IN.billingOrder` | Phụ thuộc phim cụ thể |
| Điểm đánh giá | `RATED.score` | Mỗi người có thể đánh giá từng phim khác nhau |
| Thời điểm đánh giá | `RATED.ratedAt` | Thuộc về một lần đánh giá |

Trong capstone, mỗi cặp Person–Movie chỉ có một relationship `RATED` đại diện cho đánh giá hiện tại. Nếu cần lưu lịch sử nhiều lần đánh giá, nguồn đánh giá hoặc bình luận độc lập, hãy chuyển `Rating` thành node entity thay vì tạo nhiều cạnh giống nhau.

## 4. Khai báo entity Person

Tạo `Person.java`:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Person")
public class Person {

    @Id
    private String personId;

    @Version
    private Long version;

    private String name;
    private Integer born;

    @Relationship(type = "ACTED_IN", direction = Relationship.Direction.OUTGOING)
    private List<ActingCredit> actingCredits = new ArrayList<>();

    @Relationship(type = "RATED", direction = Relationship.Direction.OUTGOING)
    private List<MovieRating> ratings = new ArrayList<>();

    @Relationship(type = "DIRECTED", direction = Relationship.Direction.OUTGOING)
    private List<Movie> directedMovies = new ArrayList<>();

    protected Person() {
    }

    public Person(String personId, String name, Integer born) {
        this.personId = personId;
        this.name = name;
        this.born = born;
    }

    public String getPersonId() {
        return personId;
    }

    public String getName() {
        return name;
    }

    public Integer getBorn() {
        return born;
    }

    public Long getVersion() {
        return version;
    }

    public List<ActingCredit> getActingCredits() {
        return List.copyOf(actingCredits);
    }

    public List<MovieRating> getRatings() {
        return List.copyOf(ratings);
    }

    public void addActingCredit(Movie movie, String roleName, int billingOrder) {
        actingCredits.add(new ActingCredit(movie, roleName, billingOrder));
    }

    public void rate(Movie movie, double score, java.time.ZonedDateTime ratedAt) {
        if (score < 0.0 || score > 10.0) {
            throw new IllegalArgumentException("Điểm đánh giá phải nằm trong khoảng 0 đến 10");
        }

        ratings.stream()
            .filter(rating -> rating.getMovie().getMovieId().equals(movie.getMovieId()))
            .findFirst()
            .ifPresentOrElse(
                rating -> rating.update(score, ratedAt),
                () -> ratings.add(new MovieRating(movie, score, ratedAt))
            );
    }
}
```

`Person` dùng business ID `personId` và `@Version Long` để SDN nhận diện entity mới cũng như kiểm soát cập nhật cạnh tranh. Với entity mới, version để `null`; không tự tăng version trong code nghiệp vụ.

Các relationship được khai báo theo hướng từ `Person` ra `Movie`. Đây là mô hình điều hướng cho thao tác ghi đơn giản. Các endpoint recommendation, path và search bên dưới dùng Cypher trả DTO để tránh hydrate toàn bộ filmography và ratings của một người.

## 5. Khai báo entity Movie và Genre

Tạo `Movie.java`:

```java
import java.util.HashSet;
import java.util.Set;

import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Movie")
public class Movie {

    @Id
    private String movieId;

    @Version
    private Long version;

    private String title;
    private String overview;
    private Integer releaseYear;

    @Relationship(type = "IN_GENRE", direction = Relationship.Direction.OUTGOING)
    private Set<Genre> genres = new HashSet<>();

    protected Movie() {
    }

    public Movie(String movieId, String title, String overview, Integer releaseYear) {
        this.movieId = movieId;
        this.title = title;
        this.overview = overview;
        this.releaseYear = releaseYear;
    }

    public String getMovieId() {
        return movieId;
    }

    public String getTitle() {
        return title;
    }

    public String getOverview() {
        return overview;
    }

    public Integer getReleaseYear() {
        return releaseYear;
    }

    public Set<Genre> getGenres() {
        return Set.copyOf(genres);
    }
}
```

Tạo `Genre.java`:

```java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Genre")
public class Genre {

    @Id
    private String genreId;

    @Version
    private Long version;

    private String name;

    protected Genre() {
    }

    public Genre(String genreId, String name) {
        this.genreId = genreId;
        this.name = name;
    }

    public String getGenreId() {
        return genreId;
    }

    public String getName() {
        return name;
    }
}
```

## 6. Ánh xạ relationship properties cho ACTED_IN và RATED

`ACTED_IN` có property về vai diễn. Tạo `ActingCredit.java`:

```java
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class ActingCredit {

    @RelationshipId
    private Long id;

    @TargetNode
    private Movie movie;

    private String roleName;
    private Integer billingOrder;

    protected ActingCredit() {
    }

    public ActingCredit(Movie movie, String roleName, Integer billingOrder) {
        this.movie = movie;
        this.roleName = roleName;
        this.billingOrder = billingOrder;
    }

    public Movie getMovie() {
        return movie;
    }

    public String getRoleName() {
        return roleName;
    }

    public Integer getBillingOrder() {
        return billingOrder;
    }
}
```

`RATED` có điểm và thời điểm đánh giá. Tạo `MovieRating.java`:

```java
import java.time.ZonedDateTime;

import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class MovieRating {

    @RelationshipId
    private Long id;

    @TargetNode
    private Movie movie;

    private double score;
    private ZonedDateTime ratedAt;

    protected MovieRating() {
    }

    public MovieRating(Movie movie, double score, ZonedDateTime ratedAt) {
        this.movie = movie;
        this.score = score;
        this.ratedAt = ratedAt;
    }

    public Movie getMovie() {
        return movie;
    }

    public double getScore() {
        return score;
    }

    public ZonedDateTime getRatedAt() {
        return ratedAt;
    }

    public void update(double score, ZonedDateTime ratedAt) {
        this.score = score;
        this.ratedAt = ratedAt;
    }
}
```

`@RelationshipProperties` ánh xạ class thành dữ liệu của relationship; `@TargetNode` xác định node ở đầu kia; `@RelationshipId` là identity nội bộ để SDN nhận diện relationship khi đồng bộ graph. Không dùng relationship ID nội bộ làm ID công khai của rating hoặc credit.

## 7. Tạo schema constraint cho node ID

Chạy schema Cypher qua migration hoặc quy trình triển khai schema của dự án:

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;

CREATE CONSTRAINT movie_id_unique IF NOT EXISTS
FOR (m:Movie)
REQUIRE m.movieId IS UNIQUE;

CREATE CONSTRAINT genre_id_unique IF NOT EXISTS
FOR (g:Genre)
REQUIRE g.genreId IS UNIQUE;
```

`@Id` trong Java không tự tạo uniqueness constraint. Các constraint bảo vệ business ID ở database trước mọi client ghi dữ liệu. Full-text index được tạo riêng ở phần 15 sau khi mô hình dữ liệu đã sẵn sàng.

## 8. Tạo dữ liệu mẫu để thực hành

Có thể dùng một tập dữ liệu nhỏ sau để kiểm tra ba chức năng. `MERGE` giúp lệnh seed có thể chạy lại mà không tạo thêm node có cùng business ID:

```cypher
MERGE (alice:Person {personId: 'P-100'})
SET alice.name = 'Alice', alice.born = 1988
MERGE (bob:Person {personId: 'P-200'})
SET bob.name = 'Bob', bob.born = 1985
MERGE (carol:Person {personId: 'P-300'})
SET carol.name = 'Carol', carol.born = 1990

MERGE (m1:Movie {movieId: 'M-101'})
SET m1.title = 'Graph of Stars',
    m1.overview = 'A science fiction story about friendship and distant galaxies.',
    m1.releaseYear = 2022
MERGE (m2:Movie {movieId: 'M-102'})
SET m2.title = 'The Last Orbit',
    m2.overview = 'An astronaut searches for a lost station beyond the moon.',
    m2.releaseYear = 2023
MERGE (m3:Movie {movieId: 'M-103'})
SET m3.title = 'City of Echoes',
    m3.overview = 'A detective follows clues through a city full of secrets.',
    m3.releaseYear = 2021
MERGE (m4:Movie {movieId: 'M-104'})
SET m4.title = 'Beyond the Nebula',
    m4.overview = 'A crew travels through a nebula to discover a new world.',
    m4.releaseYear = 2024

MERGE (g1:Genre {genreId: 'G-SF'})
SET g1.name = 'Science Fiction'
MERGE (g2:Genre {genreId: 'G-MYSTERY'})
SET g2.name = 'Mystery'
MERGE (m1)-[:IN_GENRE]->(g1)
MERGE (m2)-[:IN_GENRE]->(g1)
MERGE (m3)-[:IN_GENRE]->(g2)
MERGE (m4)-[:IN_GENRE]->(g1)

MERGE (alice)-[a1:ACTED_IN]->(m1)
SET a1.roleName = 'Mira', a1.billingOrder = 1
MERGE (bob)-[b1:ACTED_IN]->(m1)
SET b1.roleName = 'Jon', b1.billingOrder = 2
MERGE (bob)-[b2:ACTED_IN]->(m2)
SET b2.roleName = 'Pilot', b2.billingOrder = 1
MERGE (carol)-[c1:ACTED_IN]->(m2)
SET c1.roleName = 'Dr. Lee', c1.billingOrder = 2
MERGE (alice)-[a2:ACTED_IN]->(m3)
SET a2.roleName = 'Detective Mai', a2.billingOrder = 1
MERGE (carol)-[:DIRECTED]->(m3)

MERGE (alice)-[ar1:RATED]->(m1)
SET ar1.score = 9.0, ar1.ratedAt = datetime('2026-10-01T10:00:00Z')
MERGE (alice)-[ar2:RATED]->(m3)
SET ar2.score = 8.0, ar2.ratedAt = datetime('2026-10-02T10:00:00Z')
MERGE (bob)-[br1:RATED]->(m1)
SET br1.score = 8.5, br1.ratedAt = datetime('2026-10-03T10:00:00Z')
MERGE (bob)-[br2:RATED]->(m2)
SET br2.score = 9.0, br2.ratedAt = datetime('2026-10-04T10:00:00Z')
MERGE (carol)-[cr1:RATED]->(m2)
SET cr1.score = 8.5, cr1.ratedAt = datetime('2026-10-05T10:00:00Z')
MERGE (carol)-[cr2:RATED]->(m4)
SET cr2.score = 9.5, cr2.ratedAt = datetime('2026-10-06T10:00:00Z');
```

Alice và Bob cùng đánh giá cao `Graph of Stars`; Bob và Carol cùng đánh giá cao `The Last Orbit`. Alice chưa đánh giá `The Last Orbit` và `Beyond the Nebula`, nên đây là những ứng viên có thể được gợi ý qua mạng lưới người dùng tương đồng.

Đường diễn viên ngắn nhất giữa Alice và Carol đi qua Bob và hai phim `Graph of Stars`, `The Last Orbit`:

```text
Alice --ACTED_IN--> Graph of Stars <--ACTED_IN-- Bob
Bob   --ACTED_IN--> The Last Orbit <--ACTED_IN-- Carol
```

## 9. Tạo repository cho thao tác entity cơ bản

Tạo `PersonRepository.java`:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {
}
```

Tạo `MovieRepository.java`:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface MovieRepository extends Neo4jRepository<Movie, String> {
}
```

Repository phục vụ CRUD và thao tác aggregate thông thường. Recommendation, path finding và full-text search là read model chuyên biệt; ta sẽ dùng `Neo4jClient` để chỉ trả những cột cần thiết.

Một service ghi có thể tải hai đầu mút, thêm hoặc cập nhật relationship properties rồi lưu aggregate `Person`:

```java
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MovieRatingService {

    private final PersonRepository personRepository;
    private final MovieRepository movieRepository;

    public MovieRatingService(
            PersonRepository personRepository,
            MovieRepository movieRepository) {
        this.personRepository = personRepository;
        this.movieRepository = movieRepository;
    }

    @Transactional
    public Person rate(String personId, String movieId, double score) {
        Person person = personRepository.findById(personId)
            .orElseThrow(() -> new PersonNotFoundException(personId));
        Movie movie = movieRepository.findById(movieId)
            .orElseThrow(() -> new MovieNotFoundException(movieId));

        person.rate(movie, score, ZonedDateTime.now(ZoneOffset.UTC));
        return personRepository.save(person);
    }
}
```

`PersonNotFoundException` và `MovieNotFoundException` là exception nghiệp vụ do ứng dụng định nghĩa. Vì `Person` khai báo cả `ACTED_IN`, `RATED` và `DIRECTED`, thao tác repository có thể hydrate các nhánh đã mapping. Với hồ sơ có rất nhiều rating/credit, hãy cân nhắc một lệnh Cypher `MERGE` cập nhật đúng relationship hoặc một aggregate nhỏ hơn để tránh tải graph lớn chỉ nhằm đổi một điểm số.

## 10. Gợi ý phim bằng collaborative filtering

Collaborative filtering dựa trên hành vi của những người dùng khác. Ý tưởng đơn giản trong capstone:

1. Tìm những phim mà người hiện tại và người khác đều đánh giá từ ngưỡng `minRating` trở lên.
2. Đếm số phim cùng được đánh giá cao để ước lượng độ chồng lấp sở thích (`overlap`).
3. Chỉ giữ người dùng có ít nhất `minOverlap` phim chung.
4. Lấy phim họ đánh giá cao mà người hiện tại chưa đánh giá.
5. Xếp hạng theo tổng support, số người ủng hộ và điểm trung bình.

Cypher:

```cypher
MATCH (me:Person {personId: $personId})-[myRating:RATED]->(shared:Movie)
      <-[theirRating:RATED]-(neighbor:Person)
WHERE neighbor <> me
  AND myRating.score >= $minRating
  AND theirRating.score >= $minRating
WITH me, neighbor, count(DISTINCT shared) AS overlap
WHERE overlap >= $minOverlap
MATCH (neighbor)-[candidateRating:RATED]->(candidate:Movie)
WHERE candidateRating.score >= $minRating
  AND NOT EXISTS {
      MATCH (me)-[:RATED]->(candidate)
  }
WITH candidate,
     sum(overlap) AS support,
     count(DISTINCT neighbor) AS neighborCount,
     avg(candidateRating.score) AS averageScore
RETURN candidate.movieId AS movieId,
       candidate.title AS title,
       candidate.releaseYear AS releaseYear,
       support,
       neighborCount,
       averageScore
ORDER BY support DESC, averageScore DESC, title ASC
LIMIT $limit;
```

Giải thích:

- `shared` là phim được cả người hiện tại và neighbor đánh giá cao.
- `overlap` đếm số phim chung, không đếm số relationship trùng.
- `NOT EXISTS` loại phim người hiện tại đã đánh giá.
- `support` cộng độ chồng lấp của các neighbor ủng hộ ứng viên.
- `neighborCount` cho biết có bao nhiêu người dùng khác đề xuất phim đó.
- `averageScore` là điểm trung bình các neighbor đã cho ứng viên.

Đây là thuật toán gợi ý minh họa, không phải mô hình machine learning đã huấn luyện. Trong production, có thể bổ sung trọng số theo độ tương đồng, thời gian đánh giá, độ phổ biến, thể loại và giới hạn ảnh hưởng của người dùng hoạt động quá nhiều.

## 11. DTO cho recommendation result

Không trả nguyên node `Movie` cùng toàn bộ relationship. Định nghĩa DTO:

```java
public record MovieRecommendation(
    String movieId,
    String title,
    Integer releaseYear,
    Long support,
    Long neighborCount,
    Double averageScore
) {}
```

Các cột trả về trong Cypher có alias trùng tên component DTO. Với `count()` trong Neo4j Driver, dùng `asLong()` để đọc giá trị số nguyên. `avg()` trả số thực, dùng `asDouble()`.

## 12. Tìm đường liên kết ngắn nhất giữa hai diễn viên

Bài toán path finding ở đây là tìm chuỗi diễn viên liên kết qua các phim họ cùng tham gia. Mỗi bước `ACTED_IN` nối một người với một phim; path có dạng:

```text
Person -> Movie -> Person -> Movie -> Person
```

Dùng `shortestPath` với giới hạn tối đa 6 relationship:

```cypher
MATCH (source:Person {personId: $fromPersonId})
MATCH (target:Person {personId: $toPersonId})
MATCH path = shortestPath(
    (source)-[:ACTED_IN*1..6]-(target)
)
RETURN [n IN nodes(path) |
    CASE
        WHEN n:Person THEN {
            kind: 'PERSON',
            id: n.personId,
            label: n.name
        }
        ELSE {
            kind: 'MOVIE',
            id: n.movieId,
            label: n.title
        }
    END
] AS nodes,
[
    r IN relationships(path) |
    {
        type: type(r),
        roleName: r.roleName
    }
] AS edges,
length(path) AS hops;
```

`shortestPath` trả một đường đi ngắn nhất theo số relationship, không tính trọng số. `*1..6` giới hạn độ dài path và tránh traversal không giới hạn. Vì pattern không định hướng, Neo4j có thể đi từ Person tới Movie và từ Movie ngược về Person.

Nếu hai người không có đường nối trong giới hạn, query không trả record. Nếu `fromPersonId` và `toPersonId` giống nhau, service có thể trả path rỗng gồm chính node đó mà không chạy pattern `*1..6`.

Không dùng `allShortestPaths` một cách không giới hạn trong endpoint công khai. Một cặp node có thể có rất nhiều đường đi cùng độ dài; nếu nghiệp vụ chỉ cần một lời giải thích ngắn nhất, `shortestPath` thường phù hợp hơn.

## 13. Phân biệt shortest path và weighted path

`shortestPath` mặc định tối thiểu hóa số relationship (số hop). Nó không tự hiểu `billingOrder`, độ phổ biến hoặc điểm đánh giá là chi phí.

Nếu nghiệp vụ cần đường đi có trọng số, ví dụ ưu tiên mối liên hệ trực tiếp hoặc đường đi qua phim có độ tin cậy cao, cần định nghĩa cost rõ ràng. Có thể:

- Dùng Cypher để tính một metric trên tập path đã giới hạn nếu graph nhỏ và giới hạn traversal chặt.
- Dùng Neo4j Graph Data Science (GDS) với thuật toán Dijkstra hoặc Yen nếu đã cài plugin và tạo graph projection phù hợp.

GDS là thư viện riêng, không phải tính năng tự động có sẵn chỉ vì ứng dụng dùng Spring Data Neo4j. Cần kiểm tra edition, version và cấu hình plugin trước khi xây dựng weighted path.

## 14. DTO cho đường đi và ánh xạ bằng Neo4jClient

Định nghĩa các record:

```java
import java.util.List;

public record PathNode(String kind, String id, String label) {}

public record PathEdge(String type, String roleName) {}

public record ConnectionPath(
    List<PathNode> nodes,
    List<PathEdge> edges,
    Integer hops
) {}
```

`Neo4jClient` có thể ánh xạ các list map mà Cypher trả về:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class MovieGraphQueries {

    private final Neo4jClient neo4jClient;

    public MovieGraphQueries(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public Optional<ConnectionPath> findConnection(
            String fromPersonId,
            String toPersonId) {

        return neo4jClient.query("""
            MATCH (source:Person {personId: $fromPersonId})
            MATCH (target:Person {personId: $toPersonId})
            MATCH path = shortestPath(
                (source)-[:ACTED_IN*1..6]-(target)
            )
            RETURN [n IN nodes(path) |
                CASE
                    WHEN n:Person THEN {
                        kind: 'PERSON', id: n.personId, label: n.name
                    }
                    ELSE {
                        kind: 'MOVIE', id: n.movieId, label: n.title
                    }
                END
            ] AS nodes,
            [r IN relationships(path) |
                {type: type(r), roleName: r.roleName}
            ] AS edges,
            length(path) AS hops
            """)
            .bind(fromPersonId).to("fromPersonId")
            .bind(toPersonId).to("toPersonId")
            .fetchAs(ConnectionPath.class)
            .mappedBy((typeSystem, record) -> new ConnectionPath(
                record.get("nodes").asList(value -> new PathNode(
                    value.get("kind").asString(),
                    value.get("id").asString(),
                    value.get("label").asString()
                )),
                record.get("edges").asList(value -> new PathEdge(
                    value.get("type").asString(),
                    value.get("roleName").isNull()
                        ? null
                        : value.get("roleName").asString()
                )),
                record.get("hops").asInt()
            ))
            .one();
    }
}
```

`Optional.empty()` biểu thị không tìm thấy đường đi trong giới hạn query hoặc một trong hai người không tồn tại. Nếu API cần phân biệt hai trường hợp, hãy kiểm tra sự tồn tại của hai node trước hoặc trả trạng thái kết quả tường minh trong cùng transaction.

## 15. Tạo full-text index cho Movie

Full-text index cho phép tìm từ trong nhiều property văn bản:

```cypher
CREATE FULLTEXT INDEX movieSearch IF NOT EXISTS
FOR (m:Movie)
ON EACH [m.title, m.overview];
```

Index cần ở trạng thái `ONLINE` trước khi query. Full-text index dùng analyzer để tokenize nội dung; analyzer mặc định của Neo4j là `standard-no-stop-words`. Nếu dữ liệu chủ yếu là tiếng Việt, hãy đánh giá analyzer phù hợp và kiểm thử cách tách từ với dữ liệu thực tế; không mặc định dùng analyzer tiếng Anh.

Full-text index không được Cypher planner tự động chọn như range index. Query cần gọi tường minh index bằng `SEARCH` hoặc procedure full-text tương ứng với phiên bản Neo4j/Cypher đang dùng.

## 16. Tìm kiếm phim bằng SEARCH trong Cypher 25

Với Neo4j 2026.09 trở lên và Cypher 25, dùng `SEARCH` clause:

```cypher
MATCH (movie:Movie)
SEARCH movie IN (
    FULLTEXT INDEX movieSearch
    FOR $term
    LIMIT $limit
)
SCORE AS score
RETURN movie.movieId AS movieId,
       movie.title AS title,
       movie.releaseYear AS releaseYear,
       score
ORDER BY score DESC, title ASC;
```

`SCORE AS score` trả relevance score của Lucene. Điểm số cao hơn thường cho biết kết quả liên quan hơn trong cùng truy vấn; nó không phải xác suất đúng hoặc phần trăm tương đồng. Không nên so sánh raw score giữa các query string hoặc analyzer khác nhau.

Parameter `$term` là query string theo cú pháp Lucene, không phải literal Cypher. Việc bind parameter ngăn đầu vào trở thành cú pháp Cypher, nhưng người dùng vẫn có thể nhập cú pháp Lucene như phrase, `AND`, `OR` hoặc field prefix. API cần quyết định có cho phép cú pháp nâng cao đó hay chỉ cung cấp ô tìm kiếm đơn giản.

## 17. Tương thích full-text procedure trên phiên bản cũ

Với Neo4j trước 2026.09 hoặc ứng dụng dùng Cypher 5, có thể dùng procedure:

```cypher
CALL db.index.fulltext.queryNodes(
    'movieSearch',
    $term,
    {limit: $limit}
)
YIELD node, score
RETURN node.movieId AS movieId,
       node.title AS title,
       node.releaseYear AS releaseYear,
       score
ORDER BY score DESC, title ASC;
```

Trong Cypher 25, `db.index.fulltext.queryNodes()` đã deprecated từ Neo4j 2026.10 để chuyển sang `SEARCH`. Với triển khai mới trên Cypher 25, ưu tiên cú pháp `SEARCH`; chỉ dùng procedure khi cần tương thích với server/cấu hình cũ.

## 18. DTO cho kết quả tìm kiếm

Định nghĩa `MovieSearchHit.java`:

```java
public record MovieSearchHit(
    String movieId,
    String title,
    Integer releaseYear,
    Double score
) {}
```

DAO có thể ánh xạ kết quả `SEARCH` bằng `Neo4jClient`:

```java
import java.util.List;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class MovieSearchDao {

    private final Neo4jClient neo4jClient;

    public MovieSearchDao(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public List<MovieSearchHit> search(String term, int limit) {
        return neo4jClient.query("""
            MATCH (movie:Movie)
            SEARCH movie IN (
                FULLTEXT INDEX movieSearch
                FOR $term
                LIMIT $limit
            )
            SCORE AS score
            RETURN movie.movieId AS movieId,
                   movie.title AS title,
                   movie.releaseYear AS releaseYear,
                   score
            ORDER BY score DESC, title ASC
            """)
            .bind(term).to("term")
            .bind(limit).to("limit")
            .fetchAs(MovieSearchHit.class)
            .mappedBy((typeSystem, record) -> new MovieSearchHit(
                record.get("movieId").asString(),
                record.get("title").asString(),
                record.get("releaseYear").isNull()
                    ? null
                    : record.get("releaseYear").asInt(),
                record.get("score").asDouble()
            ))
            .all()
            .stream()
            .toList();
    }
}
```

Giữ alias trong Cypher khớp component DTO. `Neo4jClient` trả DTO phẳng, không hydrate toàn bộ entity graph của Movie.

## 19. Kết hợp ba truy vấn trong service

Tạo service read-only cho ba use case:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MovieDiscoveryService {

    private final MovieGraphQueries graphQueries;
    private final MovieSearchDao searchDao;
    private final MovieRecommendationDao recommendationDao;

    public MovieDiscoveryService(
            MovieGraphQueries graphQueries,
            MovieSearchDao searchDao,
            MovieRecommendationDao recommendationDao) {
        this.graphQueries = graphQueries;
        this.searchDao = searchDao;
        this.recommendationDao = recommendationDao;
    }

    @Transactional(readOnly = true)
    public List<MovieRecommendation> recommend(
            String personId,
            double minRating,
            int minOverlap,
            int limit) {
        return recommendationDao.recommend(personId, minRating, minOverlap, limit);
    }

    @Transactional(readOnly = true)
    public Optional<ConnectionPath> connection(String fromId, String toId) {
        return graphQueries.findConnection(fromId, toId);
    }

    @Transactional(readOnly = true)
    public List<MovieSearchHit> search(String term, int limit) {
        return searchDao.search(term, limit);
    }
}
```

Các DAO được inject như Spring bean; `MovieRecommendationDao` được triển khai ở phần 20. Với query chỉ đọc, `readOnly = true` mô tả đúng access mode của transaction và có thể hỗ trợ định tuyến tới reader nếu ứng dụng kết nối cluster bằng routing URI.

## 20. DAO cho collaborative recommendation

Tạo `MovieRecommendationDao.java`:

```java
import java.util.List;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class MovieRecommendationDao {

    private final Neo4jClient neo4jClient;

    public MovieRecommendationDao(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public List<MovieRecommendation> recommend(
            String personId,
            double minRating,
            int minOverlap,
            int limit) {

        return neo4jClient.query("""
            MATCH (me:Person {personId: $personId})-[myRating:RATED]->(shared:Movie)
                  <-[theirRating:RATED]-(neighbor:Person)
            WHERE neighbor <> me
              AND myRating.score >= $minRating
              AND theirRating.score >= $minRating
            WITH me, neighbor, count(DISTINCT shared) AS overlap
            WHERE overlap >= $minOverlap
            MATCH (neighbor)-[candidateRating:RATED]->(candidate:Movie)
            WHERE candidateRating.score >= $minRating
              AND NOT EXISTS {
                  MATCH (me)-[:RATED]->(candidate)
              }
            WITH candidate,
                 sum(overlap) AS support,
                 count(DISTINCT neighbor) AS neighborCount,
                 avg(candidateRating.score) AS averageScore
            RETURN candidate.movieId AS movieId,
                   candidate.title AS title,
                   candidate.releaseYear AS releaseYear,
                   support,
                   neighborCount,
                   averageScore
            ORDER BY support DESC, averageScore DESC, title ASC
            LIMIT $limit
            """)
            .bind(personId).to("personId")
            .bind(minRating).to("minRating")
            .bind(minOverlap).to("minOverlap")
            .bind(limit).to("limit")
            .fetchAs(MovieRecommendation.class)
            .mappedBy((typeSystem, record) -> new MovieRecommendation(
                record.get("movieId").asString(),
                record.get("title").asString(),
                record.get("releaseYear").isNull()
                    ? null
                    : record.get("releaseYear").asInt(),
                record.get("support").asLong(),
                record.get("neighborCount").asLong(),
                record.get("averageScore").asDouble()
            ))
            .all()
            .stream()
            .toList();
    }
}
```

Trong service/controller, validate `minRating` nằm trong khoảng 0–10, `minOverlap >= 1` và `limit` trong một khoảng nhỏ đã cấu hình. Không cho client yêu cầu hàng nghìn recommendation trong một request.

## 21. Đọc kết quả seed data và diễn giải recommendation

Với dữ liệu mẫu:

- Alice và Bob cùng đánh giá `Graph of Stars` từ 8 điểm trở lên.
- Bob và Carol cùng đánh giá `The Last Orbit` từ 8 điểm trở lên.
- Bob đánh giá `The Last Orbit` 9 điểm; Carol đánh giá `Beyond the Nebula` 9.5 điểm.
- Alice chưa đánh giá hai phim này.

Khi gọi recommendation cho Alice với `minRating = 8`, `minOverlap = 1`, query có thể gợi ý `The Last Orbit` thông qua Bob. `Beyond the Nebula` cần neighbor có overlap với Alice và đã đánh giá phim đó; trong seed hiện tại, Carol không trực tiếp overlap với Alice nên phim này chưa được gợi ý theo quy tắc đơn giản.

Điều này giúp thấy thuật toán phụ thuộc vào dữ liệu tương tác. Người dùng mới hoặc graph rating thưa có thể không có recommendation. Production thường cần fallback như phim phổ biến, phim mới, cùng thể loại hoặc nội dung tương tự.

## 22. Giới hạn và cải tiến thuật toán recommendation

Truy vấn capstone ưu tiên tính dễ hiểu, không phải thuật toán xếp hạng hoàn chỉnh. Có thể cải tiến theo các hướng:

| Hướng cải tiến | Cách làm |
|---|---|
| Similarity score | Dùng cosine similarity hoặc Pearson correlation trên vector rating chung |
| Chống neighbor quá phổ biến | Giảm trọng số neighbor có quá nhiều rating hoặc dùng inverse frequency |
| Content-based fallback | So sánh genre, keyword hoặc embedding của phim người dùng thích |
| Recency | Tăng trọng số rating gần đây |
| Diversity | Giới hạn số phim cùng genre hoặc cùng franchise trong top kết quả |
| Cold start | Dùng phim phổ biến, phim mới hoặc onboarding preference |
| Rating history | Chuyển `RATED` thành node `Rating` nếu cần nhiều sự kiện đánh giá |

Nếu một cặp Person–Movie có thể có nhiều relationship `RATED`, query phải xác định rating hiện hành hoặc aggregate theo quy tắc rõ ràng. Không để duplicate relationship làm tăng support giả tạo.

Một fallback content-based đơn giản có thể dựa trên genre của phim người dùng đã đánh giá cao:

```cypher
MATCH (me:Person {personId: $personId})-[rating:RATED]->(liked:Movie)
      -[:IN_GENRE]->(genre:Genre)<-[:IN_GENRE]-(candidate:Movie)
WHERE rating.score >= $minRating
  AND NOT EXISTS {
      MATCH (me)-[:RATED]->(candidate)
  }
WITH candidate, count(DISTINCT genre) AS sharedGenres
RETURN candidate.movieId AS movieId,
       candidate.title AS title,
       sharedGenres
ORDER BY sharedGenres DESC, title ASC
LIMIT $limit;
```

Query này không cần neighbor rating; nó tìm phim cùng thể loại với phim người dùng thích. Có thể dùng khi người dùng mới chưa có đủ overlap cho collaborative filtering. Trong production, nên kết hợp hai nguồn theo một ranking policy rõ ràng và tránh hiển thị cùng một phim hai lần.

## 23. Bảo vệ query và giới hạn tài nguyên

Ba endpoint đều nhận dữ liệu từ client, vì vậy cần validate:

- Recommendation: `minRating` từ 0 đến 10, `minOverlap` dương, `limit` có trần.
- Path: ID nguồn/đích không rỗng, độ dài path cố định ở Cypher, không cho client truyền relationship type tùy ý.
- Full-text search: query string có độ dài tối đa, `limit` nhỏ, xử lý rõ cú pháp Lucene được phép.

Bind tất cả giá trị qua parameter; không nối `personId`, từ khóa hoặc limit trực tiếp vào chuỗi Cypher. Label, relationship type và tên index là cấu trúc query/schema, nên giữ cố định trong code.

Đặt transaction/query timeout phù hợp, rate limit các endpoint graph nặng và dùng DTO để giới hạn response. Dùng `PROFILE` với dữ liệu gần production để xem cardinality, DB hits và số row trung gian. `LIMIT` giới hạn số kết quả trả về nhưng không tự bảo đảm traversal phía trước rẻ.

## 24. Kiểm thử ba chức năng

Integration test cần dùng Neo4j thực hoặc môi trường Neo4j test tương thích với Cypher và index đang triển khai.

**Recommendation:**

1. Seed người dùng có một hoặc nhiều phim được đánh giá cao.
2. Tạo neighbor có phim chung và phim ứng viên được đánh giá cao.
3. Xác nhận phim đã được người hiện tại đánh giá không xuất hiện.
4. Xác nhận `support`, `neighborCount`, `averageScore` đúng và thứ tự xếp hạng ổn định.
5. Kiểm tra người dùng mới không có đủ overlap trả danh sách rỗng hoặc dùng fallback.

**Path finding:**

1. Tạo hai diễn viên cùng phim và xác nhận path có hai node, một edge.
2. Tạo chuỗi ba diễn viên liên kết qua hai phim và xác nhận số hop.
3. Tạo hai người không có liên kết và xác nhận `Optional.empty()`.
4. Kiểm tra cùng source/target và giới hạn path tối đa.
5. Xác nhận DTO chỉ trả tên node, ID và relationship type/property cần thiết.

**Full-text search:**

1. Tạo full-text index và chờ trạng thái `ONLINE`.
2. Tìm từ có trong title và từ chỉ có trong overview.
3. Kiểm tra phrase search và cú pháp Lucene nếu được bật.
4. Xác nhận score là số và kết quả được xếp theo score giảm dần.
5. Kiểm tra limit và trường hợp không có kết quả.

Không chỉ kiểm tra số lượng kết quả. Hãy xác nhận đúng node, đúng đường đi, đúng loại phim, alias DTO và thứ tự xếp hạng.

## 25. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không có recommendation | Người dùng không có phim chung hoặc ngưỡng overlap quá cao | Kiểm tra dữ liệu rating, giảm ngưỡng hợp lý hoặc dùng fallback cold start. |
| Phim đã đánh giá vẫn xuất hiện | Thiếu điều kiện `NOT EXISTS` | Loại candidate đã có `RATED` từ người hiện tại. |
| Support cao bất thường | Có nhiều relationship `RATED` trùng giữa một cặp người/phim | Bảo đảm invariant một rating hiện tại hoặc chuyển lịch sử rating thành node. |
| Không tìm thấy đường liên kết | Không có path trong giới hạn hop hoặc dữ liệu ACTED_IN thiếu | Kiểm tra relationship direction/type và giới hạn độ dài. |
| Path query quá tốn tài nguyên | Traversal không có upper bound hoặc dùng `allShortestPaths` trên graph lớn | Giới hạn hop và chỉ trả một shortest path nếu đủ nghiệp vụ. |
| Full-text query không tìm thấy phim | Index chưa `ONLINE`, sai index name hoặc property chưa được index | Kiểm tra `SHOW FULLTEXT INDEXES` và schema. |
| `SEARCH` không được hỗ trợ | Neo4j/Cypher version cũ | Dùng procedure full-text tương thích với Cypher 5 hoặc nâng cấp. |
| DTO có field null | Alias không khớp component hoặc query không trả cột | Đối chiếu `RETURN` alias và mapper. |
| Score bị hiểu như phần trăm | Nhầm relevance score với xác suất | Dùng score để xếp hạng tương đối trong cùng truy vấn. |
| Query chậm dù `LIMIT` nhỏ | Nhiều candidate được duyệt trước khi limit | Giới hạn traversal, lọc sớm, index root và kiểm tra `PROFILE`. |

## 26. Quy trình hoàn thành capstone

1. Tạo node model `Person`, `Movie`, `Genre` với business ID và `@Version`.
2. Tạo `ActingCredit` và `MovieRating` bằng `@RelationshipProperties`, `@TargetNode`, `@RelationshipId`.
3. Tạo uniqueness constraints cho `personId`, `movieId`, `genreId`.
4. Tạo full-text index `movieSearch` trên `Movie.title` và `Movie.overview`.
5. Seed graph nhỏ có người, phim, diễn xuất và rating để kiểm thử.
6. Tạo repository cho thao tác CRUD entity.
7. Viết collaborative filtering query và ánh xạ `MovieRecommendation`.
8. Viết shortest path query có giới hạn hop và ánh xạ `ConnectionPath`.
9. Viết full-text query theo Cypher version và ánh xạ `MovieSearchHit`.
10. Gom ba chức năng vào service read-only và validate tham số ở API boundary.
11. Dùng integration test kiểm tra kết quả, ranking, path, index state và trường hợp không có dữ liệu.
12. Dùng `PROFILE` và dữ liệu lớn hơn để đánh giá chi phí query trước khi triển khai.

## 27. Ghi nhớ

Recommendation, path finding và full-text search là ba cách khai thác graph khác nhau. Collaborative filtering tìm người có rating chung rồi lấy phim họ đánh giá cao mà người hiện tại chưa xem. `shortestPath` tìm một đường đi ít relationship nhất trong phạm vi hop được giới hạn; nó không phải weighted path algorithm. Full-text index dùng Lucene để tìm token trong property văn bản và trả relevance score để xếp hạng.

Trong Spring Data Neo4j, hãy dùng `@Node` cho thực thể độc lập, `@RelationshipProperties` cho dữ liệu thuộc cạnh và `@Version` cho optimistic locking. Với các truy vấn chuyên biệt, `Neo4jClient` giúp bind tham số, kiểm soát Cypher và ánh xạ record thành DTO mà không hydrate toàn bộ graph. Luôn tạo constraint/index qua schema migration, giới hạn query, kiểm thử trên Neo4j thật và đo bằng `PROFILE` trước khi đưa capstone vào production.

## Tài liệu tham khảo

- [Spring Data Neo4j – Object Mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping.html)
- [Spring Data Neo4j – Neo4jClient](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Neo4j Cypher Manual – Shortest paths](https://neo4j.com/docs/cypher-manual/current/patterns/shortest-paths/)
- [Neo4j Cypher Manual – Full-text indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-indexes/full-text-indexes/)
- [Neo4j Graph Data Science – Path finding](https://neo4j.com/docs/graph-data-science/current/algorithms/pathfinding/)
