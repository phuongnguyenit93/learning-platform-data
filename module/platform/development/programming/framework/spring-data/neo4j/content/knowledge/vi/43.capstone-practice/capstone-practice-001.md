# Phân tích câu hỏi nghiệp vụ trên đồ thị phim–diễn viên–đánh giá

Capstone này yêu cầu xây dựng một lát cắt dữ liệu cho nền tảng khám phá phim bằng Spring Data Neo4j (SDN). Bạn sẽ mô hình hóa phim, người tham gia sản xuất, thể loại, người dùng và đánh giá thành graph; sau đó chuyển các câu hỏi sản phẩm thành Cypher, ánh xạ kết quả sang DTO và kiểm chứng bằng Neo4j thật.

Trọng tâm là cách suy nghĩ từ nghiệp vụ đến graph pattern. Câu hỏi “diễn viên này đã đóng những phim nào?” cần một traversal cụ thể; câu hỏi “phim nào được đánh giá cao?” cần aggregation và ngưỡng số lượt đánh giá; câu hỏi “gợi ý phim cho người dùng” cần loại bỏ những phim họ đã đánh giá và tránh tính trùng người dùng tương tự. SDN cung cấp repository, mapping và transaction; Cypher quyết định dữ liệu nào được tìm và tổng hợp.

## 1. Bối cảnh sản phẩm và mục tiêu

Một dịch vụ xem phim muốn hỗ trợ người dùng khám phá nội dung qua các câu hỏi:

1. Diễn viên đã tham gia những phim nào, với vai diễn gì?
2. Phim nào được đánh giá cao trong một thể loại và khoảng năm nhất định, với số lượt đánh giá tối thiểu?
3. Những diễn viên nào thường xuất hiện cùng một diễn viên khác?
4. Có thể gợi ý phim nào cho người dùng dựa trên những người dùng khác đã đánh giá cao cùng các phim họ yêu thích?

Dữ liệu gồm phim, diễn viên/đạo diễn, thể loại, người dùng và điểm đánh giá. Mục tiêu của capstone là tạo được một mô hình graph dễ mở rộng, các truy vấn có semantics rõ ràng và một lớp persistence có thể kiểm thử.

## 2. Thiết kế graph domain

Dùng các node và relationship sau:

| Thành phần | Label/type | Property tiêu biểu | Vai trò |
| --- | --- | --- | --- |
| Phim | Movie | id, title, releaseYear, runtimeMinutes | Nội dung được khám phá |
| Người | Person | id, name, birthYear | Diễn viên, đạo diễn hoặc người làm phim |
| Người dùng | User | id, displayName, createdAt | Người đưa ra đánh giá |
| Thể loại | Genre | id, name | Nhóm phân loại phim |
| Diễn xuất | ACTED_IN | characterName, billingOrder | Người tham gia phim với vai diễn |
| Đạo diễn | DIRECTED | — | Người đạo diễn phim |
| Phân loại | IN_GENRE | — | Phim thuộc thể loại |
| Đánh giá | RATED | score, ratedAt | Người dùng đánh giá phim |

Graph pattern tổng quát:

~~~mermaid
flowchart LR
    P["Person"] -->|"ACTED_IN"| M["Movie"]
    D["Person"] -->|"DIRECTED"| M
    M -->|"IN_GENRE"| G["Genre"]
    U["User"] -->|"RATED: score, ratedAt"| M
~~~

Một Person có thể vừa là diễn viên vừa là đạo diễn. Không cần tạo hai loại node Actor và Director nếu chúng đại diện cho cùng một con người và có cùng định danh. Vai trò được thể hiện bằng relationship type.

Relationship ACTED_IN có property characterName và billingOrder nên cần được mô hình hóa như relationship properties khi ánh xạ bằng SDN. Relationship RATED cũng có score và ratedAt; đây là dữ liệu nghiệp vụ trên cạnh, không phải property của Movie hay User.

### 2.1. Quyết định mô hình hóa cần ghi lại

Trước khi viết entity, xác định rõ:

- id là khóa định danh ổn định do ứng dụng quản lý.
- releaseYear là số nguyên; score là số nguyên trong khoảng 1 đến 5 cho bộ bài tập.
- Một Person có thể có nhiều ACTED_IN tới nhiều Movie.
- Một Movie có thể có nhiều Genre.
- Một User có tối đa một đánh giá hiện hành cho một Movie trong mô hình bài tập.
- Cập nhật đánh giá là thao tác upsert điểm và thời gian, không tạo thêm relationship RATED.
- Phim chưa có đánh giá vẫn tồn tại và không xuất hiện trong danh sách top-rated yêu cầu tối thiểu một số lượt đánh giá.

Nếu hệ thống cần lưu lịch sử thay đổi điểm đánh giá, một relationship RATED hiện hành là chưa đủ. Khi đó hãy mô hình hóa Rating thành node có ID riêng và quan hệ từ User tới Rating, từ Rating tới Movie; mỗi lần đổi điểm có thể tạo một sự kiện lịch sử.

## 3. Constraint và index ban đầu

Tạo uniqueness constraint cho các ID nghiệp vụ:

~~~cypher
CREATE CONSTRAINT movie_id_unique IF NOT EXISTS
FOR (movie:Movie)
REQUIRE movie.id IS UNIQUE;

CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (person:Person)
REQUIRE person.id IS UNIQUE;

CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (user:User)
REQUIRE user.id IS UNIQUE;

CREATE CONSTRAINT genre_id_unique IF NOT EXISTS
FOR (genre:Genre)
REQUIRE genre.id IS UNIQUE;

CREATE CONSTRAINT genre_name_unique IF NOT EXISTS
FOR (genre:Genre)
REQUIRE genre.name IS UNIQUE;
~~~

Các constraint giúp bảo vệ định danh node và cung cấp backing index để tìm node theo ID. Nếu ứng dụng tìm phim theo tiêu đề thường xuyên, hãy xem xét range/text/full-text index dựa trên kiểu tìm kiếm thực tế. Không tạo index cho mọi property chỉ vì property tồn tại.

Constraint trên Genre.name giả định tên thể loại là canonical và duy nhất. Nếu hệ thống hỗ trợ nhiều ngôn ngữ hoặc tên hiển thị trùng nhau, dùng slug/normalizedName duy nhất hoặc truy vấn theo Genre.id thay vì ép tên hiển thị phải duy nhất.

Với mô hình một RATED relationship hiện hành trên mỗi cặp User–Movie, hãy ghi bằng MERGE theo hai node đã định danh:

~~~cypher
MATCH (user:User {id: $userId})
MATCH (movie:Movie {id: $movieId})
MERGE (user)-[rating:RATED]->(movie)
SET rating.score = $score,
    rating.ratedAt = datetime()
RETURN rating
~~~

MERGE giúp thao tác upsert lặp lại không tạo relationship mới nếu cặp node đã có cạnh phù hợp. Đây là quy ước ghi của ứng dụng; uniqueness constraint trên User.id và Movie.id không tự tạo một constraint duy nhất cho cặp endpoint của relationship. Nếu cần bảo đảm ở cấp dữ liệu mạnh hơn hoặc lưu nhiều lần đánh giá, cân nhắc chuyển Rating thành node có ratingId duy nhất.

## 4. Nạp dữ liệu mẫu theo cách idempotent

Dùng MERGE theo khóa ổn định để có thể chạy seed nhiều lần mà không nhân bản node:

~~~cypher
MERGE (actor:Person {id: $actorId})
SET actor.name = $actorName

MERGE (movie:Movie {id: $movieId})
SET movie.title = $title,
    movie.releaseYear = $releaseYear

MERGE (actor)-[credit:ACTED_IN]->(movie)
SET credit.characterName = $characterName,
    credit.billingOrder = $billingOrder
~~~

Để thêm đạo diễn:

~~~cypher
MATCH (director:Person {id: $directorId})
MATCH (movie:Movie {id: $movieId})
MERGE (director)-[:DIRECTED]->(movie)
~~~

Để thêm thể loại:

~~~cypher
MATCH (movie:Movie {id: $movieId})
MERGE (genre:Genre {id: $genreId})
SET genre.name = $genreName
MERGE (movie)-[:IN_GENRE]->(genre)
~~~

Để lưu đánh giá:

~~~cypher
MATCH (user:User {id: $userId})
MATCH (movie:Movie {id: $movieId})
MERGE (user)-[rating:RATED]->(movie)
SET rating.score = $score,
    rating.ratedAt = datetime()
~~~

Trong ứng dụng, validate score từ 1 đến 5 trước khi ghi. Các node đầu mút phải được tạo hoặc tìm thấy trước; nếu MATCH không tìm thấy User hoặc Movie thì query không tạo relationship. Đặt các bước ghi thuộc cùng một use case trong transaction khi cần tính nguyên tử.

## 5. Ánh xạ node và relationship bằng SDN

Dùng ID do ứng dụng cấp để ví dụ dễ đọc. Các entity dưới đây là phần lõi của mapping; bổ sung constructor, accessor, equals/hashCode và validation theo chuẩn dự án.

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Movie")
public class Movie {

    @Id
    private String id;

    private String title;
    private Integer releaseYear;
    private Integer runtimeMinutes;

    protected Movie() {
    }

    public Movie(
            String id,
            String title,
            Integer releaseYear,
            Integer runtimeMinutes) {
        this.id = id;
        this.title = title;
        this.releaseYear = releaseYear;
        this.runtimeMinutes = runtimeMinutes;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Integer getReleaseYear() {
        return releaseYear;
    }
}
~~~

Person sở hữu các credit diễn xuất đi ra tới Movie:

~~~java
import java.util.HashSet;
import java.util.Set;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String name;
    private Integer birthYear;

    @Relationship(
        type = "ACTED_IN",
        direction = Relationship.Direction.OUTGOING
    )
    private Set<ActingCredit> actingCredits = new HashSet<>();

    protected Person() {
    }

    public String getId() {
        return id;
    }

    public Set<ActingCredit> getActingCredits() {
        return actingCredits;
    }
}
~~~

Relationship properties lưu thông tin vai diễn và target Movie:

~~~java
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class ActingCredit {

    @RelationshipId
    private Long id;

    private String characterName;
    private Integer billingOrder;

    @TargetNode
    private Movie movie;

    protected ActingCredit() {
    }

    public Movie getMovie() {
        return movie;
    }

    public String getCharacterName() {
        return characterName;
    }

    public Integer getBillingOrder() {
        return billingOrder;
    }
}
~~~

User có thể ánh xạ relationship RATED theo cùng nguyên tắc:

~~~java
import java.util.HashSet;
import java.util.Set;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("User")
public class AppUser {

    @Id
    private String id;

    private String displayName;

    @Relationship(
        type = "RATED",
        direction = Relationship.Direction.OUTGOING
    )
    private Set<MovieRating> ratings = new HashSet<>();

    protected AppUser() {
    }
}
~~~

~~~java
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class MovieRating {

    @RelationshipId
    private Long id;

    private Integer score;
    private java.time.Instant ratedAt;

    @TargetNode
    private Movie movie;

    protected MovieRating() {
    }
}
~~~

SDN dùng @RelationshipId cho identity nội bộ của relationship properties. Không dùng giá trị này làm ID nghiệp vụ. Với các truy vấn báo cáo, không cần hydrate cả entity graph; DTO thường là lựa chọn rõ ràng và tiết kiệm hơn.

## 6. Chuyển câu hỏi nghiệp vụ thành query contract

Trước khi viết Cypher, mô tả input và output của từng câu hỏi:

| Use case | Input | Output | Quy tắc |
| --- | --- | --- | --- |
| Filmography | personId | Các phim, năm phát hành, vai diễn | Sắp xếp phim mới nhất trước |
| Top-rated movies | genre, fromYear, toYear, minimumRatings, page | Điểm trung bình, số lượt đánh giá | Chỉ lấy phim đạt ngưỡng lượt đánh giá |
| Co-actors | personId, page | Người từng đóng chung và số phim chung | Đếm mỗi phim một lần |
| Recommendations | userId, minimumLikedScore, minimumPeers, limit | Phim chưa được user đánh giá, số peer ủng hộ | Không đề xuất phim đã có RATED từ user |

Các query dưới đây dùng parameter binding. Không ghép giá trị đầu vào trực tiếp vào chuỗi Cypher.

## 7. Use case 1: phim của một diễn viên

Câu hỏi: “Diễn viên có ID đã cho từng tham gia những phim nào và đóng vai gì?”

Cypher:

~~~cypher
MATCH (person:Person {id: $personId})
      -[credit:ACTED_IN]->
      (movie:Movie)
RETURN movie.id AS movieId,
       movie.title AS title,
       movie.releaseYear AS releaseYear,
       credit.characterName AS characterName,
       credit.billingOrder AS billingOrder
ORDER BY movie.releaseYear DESC, movie.title ASC
~~~

Query trả một record cho mỗi credit diễn xuất. Đây là DTO theo từng phim, không phải entity Person có collection cần hydrate.

Ví dụ DTO:

~~~java
public record FilmographyItem(
    String movieId,
    String title,
    Integer releaseYear,
    String characterName,
    Integer billingOrder
) {}
~~~

Kết quả cần có thứ tự ổn định. Nếu diễn viên chưa có credit, query trả danh sách rỗng. Nếu một người tham gia cùng một phim trong nhiều vai và domain cho phép nhiều credit, mỗi credit có thể là một record riêng; hãy xác định rõ có cần gộp theo Movie hay không.

## 8. Use case 2: phim được đánh giá cao có đủ số lượt

Câu hỏi: “Trong thể loại và khoảng năm đã chọn, phim nào có điểm trung bình cao, nhưng chỉ tính phim có ít nhất N lượt đánh giá?”

Cypher:

~~~cypher
MATCH (movie:Movie)-[:IN_GENRE]->(:Genre {name: $genre})
WHERE movie.releaseYear >= $fromYear
  AND movie.releaseYear <= $toYear
WITH DISTINCT movie
MATCH (:User)-[rating:RATED]->(movie)
WITH movie,
     avg(rating.score) AS averageScore,
     count(rating) AS ratingCount
WHERE ratingCount >= $minimumRatings
RETURN movie.id AS movieId,
       movie.title AS title,
       movie.releaseYear AS releaseYear,
       averageScore AS averageScore,
       ratingCount AS ratingCount
ORDER BY averageScore DESC,
         ratingCount DESC,
         title ASC
SKIP $skip
LIMIT $limit
~~~

Ngưỡng minimumRatings giảm thiên lệch từ phim chỉ có một vài lượt đánh giá. Sắp xếp phụ theo ratingCount và title giúp thứ tự ổn định hơn khi điểm trung bình bằng nhau.

DTO:

~~~java
public record TopRatedMovie(
    String movieId,
    String title,
    Integer releaseYear,
    Double averageScore,
    Long ratingCount
) {}
~~~

Lưu ý nghiệp vụ:

- Phim chưa có đánh giá không được đưa vào kết quả này.
- count(rating) đếm relationship đánh giá; nếu dữ liệu có duplicate RATED relationship do import sai, cần làm sạch hoặc sửa quy trình upsert.
- Nếu một phim thuộc nhiều genre và query mở rộng thêm nhiều pattern, kiểm tra nguy cơ nhân bản rating trước khi tính average.
- Nếu điểm số được lưu dưới dạng số thập phân, xác định rõ quy tắc làm tròn ở tầng DTO/API, không làm tròn trước khi sắp xếp.

## 9. Use case 3: diễn viên thường đóng chung

Câu hỏi: “Những người nào từng đóng cùng diễn viên X nhiều nhất?”

Cypher:

~~~cypher
MATCH (actor:Person {id: $personId})
      -[:ACTED_IN]->
      (movie:Movie)
      <-[:ACTED_IN]-
      (coActor:Person)
WHERE coActor.id <> actor.id
RETURN coActor.id AS personId,
       coActor.name AS name,
       count(DISTINCT movie) AS sharedMovieCount
ORDER BY sharedMovieCount DESC, name ASC
SKIP $skip
LIMIT $limit
~~~

count(DISTINCT movie) đếm phim chung, tránh đếm lặp một Movie nếu có nhiều đường dẫn hoặc credit trùng. Nếu muốn đếm số vai diễn chung thay vì số phim chung, thay đổi aggregation và ghi rõ semantics.

Không trả toàn bộ path nếu client chỉ cần tên diễn viên và số phim chung. Projection DTO giúp giới hạn dữ liệu truyền qua Bolt và giảm chi phí mapping graph.

## 10. Use case 4: gợi ý phim dựa trên người dùng tương tự

Bài tập dùng một cách tiếp cận collaborative filtering đơn giản:

1. Lấy các phim mà user hiện tại đánh giá từ ngưỡng minimumLikedScore trở lên.
2. Tìm các peer cũng đánh giá cao ít nhất một phim trong tập đó.
3. Tìm các phim khác mà peer đánh giá cao.
4. Loại những phim user hiện tại đã đánh giá.
5. Đếm số peer khác nhau ủng hộ từng candidate và tính điểm trung bình từ peer.
6. Chỉ giữ candidate có ít nhất minimumPeers peer.

Cypher:

~~~cypher
MATCH (user:User {id: $userId})
      -[myRating:RATED]->
      (liked:Movie)
WHERE myRating.score >= $minimumLikedScore

MATCH (peer:User)-[peerLike:RATED]->(liked)
WHERE peer.id <> user.id
  AND peerLike.score >= $minimumLikedScore

WITH DISTINCT user, peer

MATCH (peer)-[peerRating:RATED]->(candidate:Movie)
WHERE peerRating.score >= $minimumLikedScore
  AND NOT EXISTS {
      MATCH (user)-[:RATED]->(candidate)
  }

WITH DISTINCT candidate, peer, peerRating
WITH candidate,
     count(DISTINCT peer) AS peerCount,
     avg(peerRating.score) AS peerAverageScore
WHERE peerCount >= $minimumPeers
RETURN candidate.id AS movieId,
       candidate.title AS title,
       candidate.releaseYear AS releaseYear,
       peerCount AS peerCount,
       peerAverageScore AS peerAverageScore
ORDER BY peerCount DESC,
         peerAverageScore DESC,
         title ASC
LIMIT $limit
~~~

WITH DISTINCT user, peer loại các đường dẫn trùng khiến cùng peer được tìm thấy qua nhiều phim đã thích. WITH DISTINCT candidate, peer, peerRating bảo đảm một peer-rating relationship chỉ đóng góp một lần cho candidate trước khi aggregation.

Query giả định mỗi cặp User–Movie chỉ có một RATED relationship hiện hành. Quy trình ghi phải dùng MERGE theo hai endpoint đã định danh; dữ liệu cũ có nhiều RATED cạnh cho cùng cặp cần được đối soát. Đây là gợi ý cơ bản, không phải thuật toán recommendation hoàn chỉnh: chưa tính độ tương đồng có trọng số, độ phổ biến, thời gian, thể loại hoặc cold-start.

Nếu user chưa có đánh giá tích cực, query không có peer và trả danh sách rỗng. Hãy xác định fallback của sản phẩm, ví dụ top-rated theo thể loại phổ biến hoặc danh sách phim mới, thay vì âm thầm trả kết quả không có cơ sở.

## 11. Đưa query vào repository SDN

Các query trên trả scalar columns có alias khớp với tên component trong Java record. Khai báo DTO cho từng use case:

~~~java
public record CoActorSummary(
    String personId,
    String name,
    Long sharedMovieCount
) {}

public record RecommendationItem(
    String movieId,
    String title,
    Integer releaseYear,
    Long peerCount,
    Double peerAverageScore
) {}
~~~

Repository có thể khai báo như sau:

~~~java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface MovieInsightsRepository
        extends Neo4jRepository<Movie, String> {

    @Query("""
        MATCH (person:Person {id: $personId})
              -[credit:ACTED_IN]->
              (movie:Movie)
        RETURN movie.id AS movieId,
               movie.title AS title,
               movie.releaseYear AS releaseYear,
               credit.characterName AS characterName,
               credit.billingOrder AS billingOrder
        ORDER BY movie.releaseYear DESC, movie.title ASC
        """)
    List<FilmographyItem> findFilmography(
        @Param("personId") String personId
    );

    @Query("""
        MATCH (movie:Movie)-[:IN_GENRE]->(:Genre {name: $genre})
        WHERE movie.releaseYear >= $fromYear
          AND movie.releaseYear <= $toYear
        WITH DISTINCT movie
        MATCH (:User)-[rating:RATED]->(movie)
        WITH movie,
             avg(rating.score) AS averageScore,
             count(rating) AS ratingCount
        WHERE ratingCount >= $minimumRatings
        RETURN movie.id AS movieId,
               movie.title AS title,
               movie.releaseYear AS releaseYear,
               averageScore AS averageScore,
               ratingCount AS ratingCount
        ORDER BY averageScore DESC,
                 ratingCount DESC,
                 title ASC
        SKIP $skip
        LIMIT $limit
        """)
    List<TopRatedMovie> findTopRated(
        @Param("genre") String genre,
        @Param("fromYear") int fromYear,
        @Param("toYear") int toYear,
        @Param("minimumRatings") long minimumRatings,
        @Param("skip") long skip,
        @Param("limit") long limit
    );

    @Query("""
        MATCH (actor:Person {id: $personId})
              -[:ACTED_IN]->
              (movie:Movie)
              <-[:ACTED_IN]-
              (coActor:Person)
        WHERE coActor.id <> actor.id
        RETURN coActor.id AS personId,
               coActor.name AS name,
               count(DISTINCT movie) AS sharedMovieCount
        ORDER BY sharedMovieCount DESC, name ASC
        SKIP $skip
        LIMIT $limit
        """)
    List<CoActorSummary> findCoActors(
        @Param("personId") String personId,
        @Param("skip") long skip,
        @Param("limit") long limit
    );

    @Query("""
        MATCH (user:User {id: $userId})
              -[myRating:RATED]->
              (liked:Movie)
        WHERE myRating.score >= $minimumLikedScore
        MATCH (peer:User)-[peerLike:RATED]->(liked)
        WHERE peer.id <> user.id
          AND peerLike.score >= $minimumLikedScore
        WITH DISTINCT user, peer
        MATCH (peer)-[peerRating:RATED]->(candidate:Movie)
        WHERE peerRating.score >= $minimumLikedScore
          AND NOT EXISTS {
              MATCH (user)-[:RATED]->(candidate)
          }
        WITH DISTINCT candidate, peer, peerRating
        WITH candidate,
             count(DISTINCT peer) AS peerCount,
             avg(peerRating.score) AS peerAverageScore
        WHERE peerCount >= $minimumPeers
        RETURN candidate.id AS movieId,
               candidate.title AS title,
               candidate.releaseYear AS releaseYear,
               peerCount AS peerCount,
               peerAverageScore AS peerAverageScore
        ORDER BY peerCount DESC,
                 peerAverageScore DESC,
                 title ASC
        LIMIT $limit
        """)
    List<RecommendationItem> recommendForUser(
        @Param("userId") String userId,
        @Param("minimumLikedScore") int minimumLikedScore,
        @Param("minimumPeers") long minimumPeers,
        @Param("limit") long limit
    );
}
~~~

Đây là repository minh họa; đặt các DTO record trong package mà dự án có thể truy cập và kiểm tra custom result mapping bằng integration test. Nếu phiên bản SDN hoặc quy ước projection của dự án yêu cầu constructor/annotation khác, điều chỉnh theo API đang dùng.

Với query trả DTO, alias là hợp đồng giữa Cypher và constructor. Đổi alias mà không đổi DTO có thể làm mapping thất bại hoặc tạo giá trị thiếu. Hãy kiểm tra cả trường hợp null và kiểu số.

## 12. Tầng service và validation đầu vào

Service nên xác thực input, gọi repository và áp dụng quy tắc ứng dụng như giới hạn page size:

~~~java
import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class MovieDiscoveryService {

    private final MovieInsightsRepository repository;

    public MovieDiscoveryService(MovieInsightsRepository repository) {
        this.repository = repository;
    }

    public List<TopRatedMovie> topRated(
            String genre,
            int fromYear,
            int toYear,
            long minimumRatings,
            long page,
            long size) {

        if (genre == null || genre.isBlank()) {
            throw new IllegalArgumentException("genre is required");
        }
        if (fromYear > toYear) {
            throw new IllegalArgumentException("invalid year range");
        }
        if (minimumRatings < 1) {
            throw new IllegalArgumentException("minimumRatings must be positive");
        }
        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException("invalid page request");
        }

        long skip = Math.multiplyExact(page, size);
        return repository.findTopRated(
            genre, fromYear, toYear, minimumRatings, skip, size
        );
    }
}
~~~

Math.multiplyExact giúp phát hiện overflow khi page và size quá lớn. Trong API thực tế, chuyển lỗi validation thành response 400 có cấu trúc; không đưa raw Cypher hoặc thông tin kết nối database vào response lỗi.

Các query đọc có thể được gọi qua service mà không cần mở transaction dài cho toàn bộ request nếu chỉ có một thao tác đọc. Nếu một use case cần nhiều thao tác nhất quán, xác định transaction boundary và giữ nó ngắn.

Ví dụ service ghi rating bằng Neo4jClient trong transaction:

~~~java
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RatingCommandService {

    private final Neo4jClient neo4jClient;

    public RatingCommandService(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    @Transactional
    public void rateMovie(String userId, String movieId, int score) {
        if (score < 1 || score > 5) {
            throw new IllegalArgumentException("score must be from 1 to 5");
        }

        neo4jClient.query("""
                MATCH (user:User {id: $userId})
                MATCH (movie:Movie {id: $movieId})
                MERGE (user)-[rating:RATED]->(movie)
                SET rating.score = $score,
                    rating.ratedAt = datetime()
                """)
            .bind(userId).to("userId")
            .bind(movieId).to("movieId")
            .bind(score).to("score")
            .run();
    }
}
~~~

Method public được gọi qua Spring bean để transaction interceptor hoạt động. Nếu User hoặc Movie không tồn tại, hai MATCH không tạo relationship và query không ghi gì; API cần kiểm tra trường hợp này để trả lỗi nghiệp vụ phù hợp. Nếu phải ghi thêm audit event trong cùng use case, nối thao tác đó trong cùng method/transaction.

## 13. Kiểm thử bằng Neo4j thật

Dùng repository test với Neo4j thật, chẳng hạn Testcontainers, để xác minh Cypher và mapping. Fixture tối thiểu cần có:

- Ít nhất ba Movie ở các năm khác nhau.
- Hai Person có credit ACTED_IN trùng một Movie.
- Một Person không có credit.
- Hai Genre để kiểm tra lọc thể loại.
- Nhiều User đánh giá các Movie với điểm khác nhau.
- Một Movie không có rating.
- Một User chưa có rating để kiểm tra cold-start.

Các assertion chính:

| Use case | Fixture cần kiểm tra | Assertion |
| --- | --- | --- |
| Filmography | Diễn viên có nhiều phim và vai diễn | Đúng Movie, characterName và thứ tự |
| Top-rated | Phim có điểm cao nhưng ít rating; phim đủ rating | Phim dưới ngưỡng bị loại |
| Co-actors | Hai diễn viên đóng chung nhiều phim | Đếm số Movie phân biệt, loại chính actor |
| Recommendation | Hai peer cùng thích một phim và đánh giá candidate | Candidate có peerCount đúng, không gồm phim user đã rate |
| Upsert rating | Gửi cùng user/movie nhiều lần | Chỉ còn một rating hiện hành theo quy ước ghi |
| Empty case | Person/User không có relationship | Trả collection rỗng, không lỗi mapping |

Ví dụ test cho filmography:

~~~java
@Test
void returnsFilmographyWithActingCreditProperties() {
    List<FilmographyItem> result =
        repository.findFilmography("person-actor-1");

    assertEquals(2, result.size());
    assertEquals("movie-2024", result.get(0).movieId());
    assertEquals("Detective", result.get(0).characterName());
}
~~~

Ví dụ test top-rated cần tạo một phim có average cao nhưng chỉ một rating và một phim có average thấp hơn nhưng đạt minimumRatings. Assertion phải chứng minh query ưu tiên điểm trung bình trong tập đã đạt ngưỡng, thay vì chọn phim có một vote cao nhất.

Không mock repository trong test dùng để chứng minh Cypher. Mock vẫn phù hợp cho unit test service validation và xử lý lỗi.

## 14. Kiểm tra hiệu năng và tính đúng của aggregation

Chạy EXPLAIN trước để xem planner dự kiến dùng index hoặc scan. Chạy PROFILE trên dữ liệu test đủ lớn để quan sát Rows, DB Hits và operator traversal/aggregation.

Một số điểm cần xem:

- Các node bắt đầu Person, Movie, User, Genre có được tìm qua index phù hợp không?
- Query co-actor có mở rộng từ Person có ID chọn lọc trước không?
- Query top-rated có nhân số rating khi thêm pattern genre hoặc nhiều collection không?
- Recommendation query có loại peer trùng trước khi đếm và tính average không?
- Sort, aggregation và page có xử lý quá nhiều dòng trung gian không?
- Kết quả có đúng khi cùng một cặp actor/movie có dữ liệu credit trùng do import không?

Index không sửa được semantics sai. Nếu query nhân bản mỗi rating qua nhiều pattern, average và count có thể sai ngay cả khi query chạy nhanh. Trước tiên phải bảo đảm cardinality đúng, sau đó mới tối ưu execution plan.

Không dùng PROFILE với query ghi trên dữ liệu dùng chung vì PROFILE thực thi query. Chỉ chạy trên fixture hoặc môi trường an toàn.

## 15. Phân trang và API contract

Các endpoint minh họa cho sản phẩm:

| HTTP | Endpoint | Kết quả |
| --- | --- | --- |
| GET | /api/people/{personId}/filmography | Danh sách phim và vai diễn |
| GET | /api/movies/top-rated | Phim theo genre, year range, minimumRatings |
| GET | /api/people/{personId}/co-actors | Diễn viên đóng chung |
| GET | /api/users/{userId}/recommendations | Phim gợi ý cho user |
| PUT | /api/users/{userId}/ratings/{movieId} | Tạo hoặc cập nhật rating |

Với endpoint phân trang, giới hạn page size ở service/API. Dùng thứ tự ổn định trong Cypher để tránh kết quả đổi vị trí tùy ý giữa các lần gọi. Nếu dữ liệu thay đổi liên tục, offset pagination có thể dịch chuyển kết quả giữa các trang; với tập dữ liệu lớn, cân nhắc keyset pagination theo các trường sắp xếp.

Không trả toàn bộ graph cho API chỉ vì database là graph. Dùng DTO theo use case, tránh tải các nhánh relationship mà màn hình không sử dụng.

## 16. Bảo mật và tính toàn vẹn dữ liệu

- Dùng parameter binding cho mọi giá trị đầu vào; không nối chuỗi Cypher từ input.
- Xác thực người dùng trước khi ghi rating hoặc truy vấn dữ liệu cá nhân.
- Chỉ cho phép user cập nhật rating của chính họ, trừ vai trò quản trị.
- Validate score, year range, page size và ID trước khi gọi repository.
- Dùng uniqueness constraint cho ID node.
- Dùng MERGE theo cặp User–Movie để upsert rating hiện hành.
- Không log token, mật khẩu hoặc nội dung review nhạy cảm.
- Cấp quyền Neo4j tối thiểu cho tài khoản ứng dụng; migration/admin dùng credential riêng.
- Giới hạn kích thước review và số lượng kết quả để tránh lạm dụng tài nguyên.

## 17. Các nhiệm vụ cần hoàn thành

Hoàn thành capstone theo thứ tự:

1. Vẽ graph model và ghi lại semantics của từng node/relationship.
2. Tạo uniqueness constraints và index thực sự cần cho query.
3. Viết entity Movie, Person, User và relationship properties cho ACTED_IN/RATED.
4. Tạo seed data có thể chạy lặp mà không nhân bản node/relationship.
5. Viết DTO cho filmography, top-rated, co-actors và recommendations.
6. Viết repository custom Cypher cho bốn câu hỏi nghiệp vụ.
7. Viết service validation và quy tắc page size.
8. Viết API hoặc command-line adapter gọi service.
9. Viết repository integration tests trên Neo4j thật.
10. Kiểm tra trường hợp rỗng, rating thiếu, duplicate dữ liệu và cold-start.
11. Chạy EXPLAIN/PROFILE với dataset lớn hơn và lưu lại nhận xét.
12. Viết hướng dẫn chạy ứng dụng, nạp fixture và gọi từng use case.

## 18. Tiêu chí nghiệm thu và rubric

| Tiêu chí | Trọng số | Bằng chứng |
| --- | ---: | --- |
| Graph model | 15% | Node, relationship direction và relationship properties đúng domain |
| Schema và dữ liệu | 10% | Constraint, seed idempotent, không tạo duplicate ngoài ý muốn |
| Cypher correctness | 25% | Bốn câu hỏi trả đúng tập kết quả và aggregation |
| SDN mapping/repository | 15% | Entity mapping, DTO aliases và repository method hoạt động |
| Transaction và validation | 10% | Rating upsert có kiểm soát, input hợp lệ, boundary rõ |
| Integration testing | 15% | Neo4j thật, fixture nhiều trường hợp, assertion có ý nghĩa |
| Performance reasoning | 10% | Giải thích plan, index và cardinality dựa trên số liệu |

Capstone đạt yêu cầu khi:

- Bốn use case chạy được với dữ liệu mẫu.
- Query top-rated loại phim không đủ số rating.
- Query co-actor không trả chính diễn viên đầu vào.
- Recommendation không đề xuất phim user đã đánh giá và không đếm peer lặp.
- Relationship properties của ACTED_IN được trả đúng.
- Repository test chạy trên Neo4j thật.
- Mọi truy vấn dùng parameter binding.
- Có ghi chú về index, execution plan và giới hạn thuật toán recommendation.

## 19. Mở rộng sau capstone

Khi phần cơ bản hoạt động, có thể mở rộng:

- Rating history bằng Rating node thay vì một RATED relationship hiện hành.
- Recommendation có trọng số theo similarity, recency và genre preference.
- Phân biệt diễn viên chính/phụ qua billingOrder.
- Tìm đường kết nối giữa hai người trong ngành phim.
- Full-text search trên title, synopsis và person name.
- Phân trang keyset cho filmography và co-actors.
- Cache các aggregate phổ biến và invalidation khi rating thay đổi.
- Đo query latency p95/p99 trên dữ liệu có degree và cardinality gần production.

Mỗi phần mở rộng cần có câu hỏi nghiệp vụ, query contract, fixture và tiêu chí nghiệm thu riêng. Tránh thêm graph traversal chỉ để làm mô hình phức tạp hơn khi sản phẩm không cần câu trả lời đó.

## 20. Bài tập tự đánh giá

1. Vì sao Person phù hợp để biểu diễn cả Actor và Director?
2. Khi nào dữ liệu nên nằm trên relationship thay vì node?
3. Vì sao ACTED_IN cần relationship properties?
4. Tại sao uniqueness constraint cho Movie.id không tự bảo đảm một RATED relationship cho mỗi cặp User–Movie?
5. Vì sao top-rated cần minimumRatings?
6. count(DISTINCT movie) khác count(movie) như thế nào trong query co-actor?
7. Recommendation query loại candidate đã được user đánh giá bằng cách nào?
8. Vì sao cần loại peer trùng trước khi tính số người ủng hộ?
9. Khi nào nên chuyển Rating từ relationship thành node?
10. Vì sao DTO phù hợp hơn entity graph cho truy vấn báo cáo?
11. Những fixture nào cần có để kiểm tra cold-start và empty relationship?
12. Làm thế nào xác minh query đúng trước khi tối ưu bằng index?

Khi hoàn thành, bạn có một lát cắt ứng dụng Spring Data Neo4j có thể trả lời câu hỏi sản phẩm trên graph phim–diễn viên–đánh giá. Quan trọng hơn, bạn đã thực hành toàn bộ chuỗi công việc: phân tích nghiệp vụ, thiết kế graph, viết Cypher, ánh xạ DTO/entity, kiểm thử bằng Neo4j thật và đánh giá execution plan.

## Tài liệu tham khảo

- [Spring Data Neo4j – Object Mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping.html)
- [Spring Data Neo4j – Repository query methods](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-methods-details.html)
- [Spring Data Neo4j – Custom queries](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
- [Neo4j Cypher Manual – MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Neo4j Cypher Manual – Aggregating functions](https://neo4j.com/docs/cypher-manual/current/functions/aggregating/)
- [Neo4j Cypher Manual – EXISTS subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/existential/)
- [Neo4j Cypher Manual – Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/)

