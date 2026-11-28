# Viết truy vấn nhiều bước, projection và phân trang

Trong capstone này, bạn sẽ xây dựng chức năng tìm kiếm danh mục phim trên một graph Neo4j. Một request có thể lọc phim theo tiêu đề, thể loại và khoảng năm phát hành; kết quả cần có danh sách thể loại và diễn viên nhưng mỗi phim chỉ xuất hiện một lần. API còn phải trả tổng số kết quả để giao diện phân trang. Một endpoint chi tiết sẽ tổng hợp diễn viên, đạo diễn và thể loại của một phim.

Bài thực hành kết hợp ba kỹ năng cốt lõi của Spring Data Neo4j (SDN): viết Cypher nhiều bước bằng WITH và OPTIONAL MATCH, chiếu graph thành DTO chỉ chứa dữ liệu cần thiết, và phân trang sau khi đã gom nhóm theo node gốc. Ta sẽ xây query, repository, service, controller và integration test theo một yêu cầu xuyên suốt.

## 1. Mục tiêu và sản phẩm cần hoàn thành

Bạn đang xây dựng API Movie Catalog cho một ứng dụng xem và khám phá phim. Graph lưu phim, người tham gia sản xuất và thể loại:

~~~mermaid
graph LR
    P1[Person: An] -->|ACTED_IN| M1[Movie: The Graph]
    P2[Person: Binh] -->|ACTED_IN| M1
    P3[Person: Lan] -->|DIRECTED| M1
    M1 -->|IN_GENRE| G1[Genre: Sci-Fi]
    M1 -->|IN_GENRE| G2[Genre: Drama]
    P1 -->|ACTED_IN| M2[Movie: Query Paths]
    P3 -->|DIRECTED| M3[Movie: Graph Stories]
    M2 -->|IN_GENRE| G1
    M3 -->|IN_GENRE| G2
~~~

Khi hoàn thành, ứng dụng cần có:

1. Endpoint tìm kiếm phim theo title, genre, fromYear và toYear.
2. Kết quả có movieId, title, released, genreNames và actorNames.
3. Mỗi phim chỉ xuất hiện một lần dù có nhiều diễn viên và thể loại.
4. Phân trang ổn định theo released giảm dần, movieId tăng dần.
5. Tổng số phim khớp bộ lọc được tính chính xác bằng count query.
6. Endpoint chi tiết phim trả diễn viên, đạo diễn và thể loại trong một DTO.
7. Endpoint gợi ý phim khác dựa trên diễn viên chung.
8. Integration test chứng minh query, projection, count và pagination hoạt động cùng nhau.

Các endpoint mẫu:

| Method | URL | Mục đích |
|---|---|---|
| GET | /api/movies?genre=Sci-Fi&page=0&size=10 | Tìm phim và phân trang |
| GET | /api/movies/M-01 | Xem chi tiết một phim |
| GET | /api/movies/M-01/similar?limit=5 | Tìm phim có diễn viên chung |

## 2. Thiết kế graph và quy tắc dữ liệu

Capstone dùng ba label và ba relationship type:

| Thành phần | Property chính | Ý nghĩa |
|---|---|---|
| Person | personId, name, born | Diễn viên hoặc đạo diễn |
| Movie | movieId, title, released | Phim |
| Genre | name | Thể loại phim |
| ACTED_IN | — | Person tham gia diễn xuất trong Movie |
| DIRECTED | — | Person đạo diễn Movie |
| IN_GENRE | — | Movie thuộc Genre |

Hướng relationship được thống nhất như sau:

- Person -[:ACTED_IN]-> Movie
- Person -[:DIRECTED]-> Movie
- Movie -[:IN_GENRE]-> Genre

Đặt uniqueness constraint cho business key:

~~~cypher
CREATE CONSTRAINT person_id IF NOT EXISTS
FOR (p:Person) REQUIRE p.personId IS UNIQUE;

CREATE CONSTRAINT movie_id IF NOT EXISTS
FOR (m:Movie) REQUIRE m.movieId IS UNIQUE;

CREATE CONSTRAINT genre_name IF NOT EXISTS
FOR (g:Genre) REQUIRE g.name IS UNIQUE;
~~~

Constraint bảo vệ tính duy nhất khi nhiều request tạo dữ liệu đồng thời. Repository dùng business ID làm @Id; trong capstone này ID được cấp từ ứng dụng, nên entity không dùng @GeneratedValue.

## 3. Tạo dữ liệu mẫu

Chạy Cypher sau trên database dùng cho bài thực hành:

~~~cypher
MERGE (an:Person {personId: 'P-01'})
SET an.name = 'An', an.born = 1988
MERGE (binh:Person {personId: 'P-02'})
SET binh.name = 'Binh', binh.born = 1990
MERGE (chi:Person {personId: 'P-03'})
SET chi.name = 'Chi', chi.born = 1985
MERGE (lan:Person {personId: 'P-04'})
SET lan.name = 'Lan', lan.born = 1978
MERGE (minh:Person {personId: 'P-05'})
SET minh.name = 'Minh', minh.born = 1980

MERGE (scifi:Genre {name: 'Sci-Fi'})
MERGE (drama:Genre {name: 'Drama'})

MERGE (m1:Movie {movieId: 'M-01'})
SET m1.title = 'The Graph', m1.released = 2024
MERGE (m2:Movie {movieId: 'M-02'})
SET m2.title = 'Query Paths', m2.released = 2022
MERGE (m3:Movie {movieId: 'M-03'})
SET m3.title = 'Graph Stories', m3.released = 2025
MERGE (m4:Movie {movieId: 'M-04'})
SET m4.title = 'Pattern Lab', m4.released = 2021

MERGE (an)-[:ACTED_IN]->(m1)
MERGE (binh)-[:ACTED_IN]->(m1)
MERGE (lan)-[:DIRECTED]->(m1)
MERGE (m1)-[:IN_GENRE]->(scifi)
MERGE (m1)-[:IN_GENRE]->(drama)

MERGE (an)-[:ACTED_IN]->(m2)
MERGE (minh)-[:DIRECTED]->(m2)
MERGE (m2)-[:IN_GENRE]->(scifi)

MERGE (binh)-[:ACTED_IN]->(m3)
MERGE (chi)-[:ACTED_IN]->(m3)
MERGE (lan)-[:DIRECTED]->(m3)
MERGE (m3)-[:IN_GENRE]->(drama)

MERGE (minh)-[:DIRECTED]->(m4)
MERGE (m4)-[:IN_GENRE]->(drama);
~~~

Dữ liệu được thiết kế có chủ đích:

- M-01 có hai diễn viên và hai thể loại để kiểm tra trường hợp nhiều relationship.
- M-02 và M-03 có diễn viên chung lần lượt với M-01 để kiểm tra gợi ý.
- M-04 không có diễn viên để kiểm tra OPTIONAL MATCH.
- M-01 có năm phát hành 2024; M-02 là 2022; M-03 là 2025; M-04 là 2021.

Kiểm tra graph:

~~~cypher
MATCH (m:Movie)
OPTIONAL MATCH (p:Person)-[:ACTED_IN]->(m)
WITH m, collect(DISTINCT p.name) AS actors
OPTIONAL MATCH (m)-[:IN_GENRE]->(g:Genre)
RETURN m.movieId AS movieId,
       m.title AS title,
       actors,
       collect(DISTINCT g.name) AS genres
ORDER BY movieId;
~~~

## 4. Khai báo entity và DTO projection

Entity Movie là aggregate root của repository:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Movie")
public class Movie {

    @Id
    private String movieId;

    private String title;

    private Integer released;

    protected Movie() {
    }

    public Movie(String movieId, String title, Integer released) {
        this.movieId = movieId;
        this.title = title;
        this.released = released;
    }

    public String getMovieId() { return movieId; }
    public String getTitle() { return title; }
    public Integer getReleased() { return released; }
}
~~~

Entity chỉ khai báo các property của Movie. Các endpoint đọc sẽ dùng custom Cypher để lấy relationship cần thiết, không cần tải toàn bộ graph vào entity.

DTO cho kết quả tìm kiếm:

~~~java
import java.util.List;

public record MovieSearchRow(
        String movieId,
        String title,
        Integer released,
        List<String> genreNames,
        List<String> actorNames) {
}
~~~

Ba property đầu tương ứng với domain entity Movie. Hai property cuối là dữ liệu bổ sung do custom query trả về. Với DTO projection trong SDN, tên property bổ sung phải khớp chính xác với alias trong record Cypher; simple type và collection của simple type được hỗ trợ, còn Map không được hỗ trợ trong cơ chế DTO projection này.

DTO cho trang chi tiết:

~~~java
import java.util.List;

public record MovieDetailRow(
        String movieId,
        String title,
        Integer released,
        List<String> genreNames,
        List<String> directorNames,
        List<String> actorNames) {
}
~~~

DTO cho gợi ý:

~~~java
import java.util.List;

public record SimilarMovieRow(
        String movieId,
        String title,
        Integer released,
        Long sharedActorCount,
        List<String> sharedActorNames,
        List<String> genreNames) {
}
~~~

Các DTO này là read model. Không dùng chúng làm entity để ghi lại graph; chúng chỉ chứa dữ liệu của một use case đọc.

## 5. Viết truy vấn tìm kiếm nhiều bước

Yêu cầu tìm kiếm là:

- Lọc Movie theo title chứa chuỗi tìm kiếm, không phân biệt hoa thường.
- Lọc theo khoảng năm nếu người dùng cung cấp.
- Lọc theo genre nếu người dùng cung cấp.
- Trả mỗi Movie một lần cùng danh sách genre và actor.
- Sắp xếp, sau đó mới áp dụng pagination.

Query:

~~~cypher
MATCH (m:Movie)
WHERE ($title IS NULL OR toLower(m.title) CONTAINS toLower($title))
  AND ($fromYear IS NULL OR m.released >= $fromYear)
  AND ($toYear IS NULL OR m.released <= $toYear)

OPTIONAL MATCH (m)-[:IN_GENRE]->(g:Genre)
WITH m, collect(DISTINCT g.name) AS genreNames
WHERE $genre IS NULL
   OR any(name IN genreNames WHERE toLower(name) = toLower($genre))

OPTIONAL MATCH (m)<-[:ACTED_IN]-(actor:Person)
WITH m,
     genreNames,
     collect(DISTINCT actor.name) AS actorNames

RETURN m, genreNames, actorNames
ORDER BY m.released DESC, m.movieId ASC
SKIP $skip
LIMIT $limit;
~~~

### 5.1. Đọc từng bước của query

**Bước 1 — MATCH và lọc property của Movie**

~~~cypher
MATCH (m:Movie)
WHERE ($title IS NULL OR toLower(m.title) CONTAINS toLower($title))
  AND ($fromYear IS NULL OR m.released >= $fromYear)
  AND ($toYear IS NULL OR m.released <= $toYear)
~~~

Ở bước này mỗi hàng đại diện cho một Movie. Các điều kiện dùng tham số null để cho phép bộ lọc tùy chọn. Service cần chuyển chuỗi rỗng thành null để tránh một chuỗi tìm kiếm rỗng khớp mọi tiêu đề.

**Bước 2 — Lấy thể loại và gom nhóm theo phim**

~~~cypher
OPTIONAL MATCH (m)-[:IN_GENRE]->(g:Genre)
WITH m, collect(DISTINCT g.name) AS genreNames
~~~

OPTIONAL MATCH giữ Movie ngay cả khi không có Genre. Khi không tìm thấy node g, giá trị g.name là null; collect bỏ qua null nên genreNames là danh sách rỗng. WITH kết thúc phần mở rộng thể loại và gom tất cả thể loại về một hàng cho mỗi Movie.

**Bước 3 — Lọc theo danh sách thể loại đã gom**

~~~cypher
WHERE $genre IS NULL
   OR any(name IN genreNames WHERE toLower(name) = toLower($genre))
~~~

Điều kiện này nằm sau WITH vì lúc này genreNames mới tồn tại. Nếu đặt điều kiện theo g.name trước khi gom nhóm, query sẽ lọc từng relationship row và có thể làm mất các thể loại còn lại khỏi danh sách trả về.

**Bước 4 — Lấy diễn viên sau khi đã gom thể loại**

~~~cypher
OPTIONAL MATCH (m)<-[:ACTED_IN]-(actor:Person)
WITH m,
     genreNames,
     collect(DISTINCT actor.name) AS actorNames
~~~

Query mở rộng diễn viên sau khi đã gom thể loại. Vì vậy, danh sách diễn viên không nhân chéo với danh sách thể loại. DISTINCT loại bỏ tên trùng nếu graph có nhiều relationship cùng dẫn tới một người.

**Bước 5 — Trả node gốc và các giá trị bổ sung**

~~~cypher
RETURN m, genreNames, actorNames
ORDER BY m.released DESC, m.movieId ASC
SKIP $skip
LIMIT $limit
~~~

Query trả node m để SDN ánh xạ các property domain vào DTO; genreNames và actorNames là các property bổ sung. Thứ tự sắp xếp có movieId làm tie-breaker, nên các phim cùng năm vẫn có thứ tự xác định.

### 5.2. Vì sao không MATCH mọi relationship cùng lúc?

Một query ngây thơ có thể viết:

~~~cypher
MATCH (m:Movie)
OPTIONAL MATCH (m)<-[:ACTED_IN]-(actor:Person)
OPTIONAL MATCH (m)-[:IN_GENRE]->(genre:Genre)
RETURN m,
       collect(actor.name) AS actorNames,
       collect(genre.name) AS genreNames;
~~~

Nếu một phim có 3 diễn viên và 2 thể loại, hai OPTIONAL MATCH tạo ra tối đa 6 hàng trung gian cho phim đó. Khi collect, tên diễn viên và thể loại có thể bị lặp. Dùng collect(DISTINCT ...) có thể loại bỏ trùng trong output, nhưng query vẫn tạo và xử lý các hàng kết hợp không cần thiết.

Tách các nhánh bằng WITH và aggregate sau từng nhánh giúp kiểm soát cardinality:

~~~mermaid
flowchart TD
    A[MATCH Movie] --> B[OPTIONAL MATCH Genre]
    B --> C[WITH Movie + collect genres]
    C --> D[Filter genre]
    D --> E[OPTIONAL MATCH Actor]
    E --> F[WITH Movie + genres + collect actors]
    F --> G[RETURN DTO row]
    G --> H[ORDER BY / SKIP / LIMIT]
~~~

### 5.3. Vai trò của WITH

WITH có ba tác dụng quan trọng:

- Truyền những biến cần dùng sang bước tiếp theo.
- Gom nhóm hoặc tính aggregate như count, collect, max và avg.
- Lọc kết quả trung gian bằng WHERE sau khi aggregate.

Biến không được liệt kê trong WITH sẽ không còn nằm trong scope của phần query sau. Ví dụ nếu viết WITH m, collect(g.name) AS genreNames thì biến actor từ bước trước (nếu có) sẽ không còn được sử dụng.

## 6. Viết count query tương ứng

Khi repository trả Page, SDN cần biết tổng số kết quả để tạo totalElements và totalPages. Count query phải áp dụng cùng điều kiện lọc với query lấy trang:

~~~cypher
MATCH (m:Movie)
WHERE ($title IS NULL OR toLower(m.title) CONTAINS toLower($title))
  AND ($fromYear IS NULL OR m.released >= $fromYear)
  AND ($toYear IS NULL OR m.released <= $toYear)

OPTIONAL MATCH (m)-[:IN_GENRE]->(g:Genre)
WITH m, collect(DISTINCT g.name) AS genreNames
WHERE $genre IS NULL
   OR any(name IN genreNames WHERE toLower(name) = toLower($genre))

RETURN count(m);
~~~

Count query không cần mở rộng relationship ACTED_IN vì actorNames không tham gia bộ lọc. Sau WITH, mỗi Movie chỉ còn một hàng nên count(m) là số phim phù hợp. Nếu bỏ bước gom genre hoặc đếm sau một phép mở rộng nhiều relationship, count có thể lớn hơn số Movie thực tế.

Hãy giữ query filter và count query đồng bộ. Nếu query trang có điều kiện genre nhưng count query quên điều kiện đó, nội dung trang có thể chỉ chứa 2 phim trong khi totalElements báo 4.

## 7. Repository với Page và DTO projection

Repository kết hợp query trang và count query:

~~~java
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface MovieRepository extends Neo4jRepository<Movie, String> {

    @Query(
        value = """
            MATCH (m:Movie)
            WHERE ($title IS NULL OR toLower(m.title) CONTAINS toLower($title))
              AND ($fromYear IS NULL OR m.released >= $fromYear)
              AND ($toYear IS NULL OR m.released <= $toYear)
            OPTIONAL MATCH (m)-[:IN_GENRE]->(g:Genre)
            WITH m, collect(DISTINCT g.name) AS genreNames
            WHERE $genre IS NULL
               OR any(name IN genreNames WHERE toLower(name) = toLower($genre))
            OPTIONAL MATCH (m)<-[:ACTED_IN]-(actor:Person)
            WITH m, genreNames, collect(DISTINCT actor.name) AS actorNames
            RETURN m, genreNames, actorNames
            ORDER BY m.released DESC, m.movieId ASC
            SKIP $skip
            LIMIT $limit
            """,
        countQuery = """
            MATCH (m:Movie)
            WHERE ($title IS NULL OR toLower(m.title) CONTAINS toLower($title))
              AND ($fromYear IS NULL OR m.released >= $fromYear)
              AND ($toYear IS NULL OR m.released <= $toYear)
            OPTIONAL MATCH (m)-[:IN_GENRE]->(g:Genre)
            WITH m, collect(DISTINCT g.name) AS genreNames
            WHERE $genre IS NULL
               OR any(name IN genreNames WHERE toLower(name) = toLower($genre))
            RETURN count(m)
            """
    )
    Page<MovieSearchRow> search(
        @Param("title") String title,
        @Param("genre") String genre,
        @Param("fromYear") Integer fromYear,
        @Param("toYear") Integer toYear,
        Pageable pageable
    );

    @Query("""
        MATCH (m:Movie {movieId: $movieId})
        OPTIONAL MATCH (m)-[:IN_GENRE]->(g:Genre)
        WITH m, collect(DISTINCT g.name) AS genreNames
        OPTIONAL MATCH (m)<-[:DIRECTED]-(director:Person)
        WITH m, genreNames, collect(DISTINCT director.name) AS directorNames
        OPTIONAL MATCH (m)<-[:ACTED_IN]-(actor:Person)
        WITH m, genreNames, directorNames,
             collect(DISTINCT actor.name) AS actorNames
        RETURN m, genreNames, directorNames, actorNames
        """)
    Optional<MovieDetailRow> findDetailByMovieId(
        @Param("movieId") String movieId
    );

    @Query("""
        MATCH (source:Movie {movieId: $movieId})
              <-[:ACTED_IN]-(shared:Person)-[:ACTED_IN]->(candidate:Movie)
        WHERE candidate <> source
        WITH candidate,
             count(DISTINCT shared) AS sharedActorCount,
             collect(DISTINCT shared.name) AS sharedActorNames
        OPTIONAL MATCH (candidate)-[:IN_GENRE]->(genre:Genre)
        WITH candidate, sharedActorCount, sharedActorNames,
             collect(DISTINCT genre.name) AS genreNames
        RETURN candidate,
               sharedActorCount,
               sharedActorNames,
               genreNames
        ORDER BY sharedActorCount DESC,
                 candidate.released DESC,
                 candidate.movieId ASC
        LIMIT $limit
        """)
    List<SimilarMovieRow> findSimilarMovies(
        @Param("movieId") String movieId,
        @Param("limit") int limit
    );
}
~~~

Lưu ý:

- Custom query dùng Pageable phải tự có cả tham số $skip và $limit trong Cypher.
- Với Page, cần countQuery để tính chính xác tổng số kết quả.
- Pageable truyền vào custom query nên dùng Sort.unsorted(); query tự khai báo ORDER BY ổn định và SDN không áp dụng sort từ Pageable cho mẫu này.
- Không đưa Pageable cùng Sort hoặc Limit riêng vào một method; Pageable đã chứa thông tin phân trang và sort.
- Query trả root node m/candidate cùng các giá trị bổ sung để SDN map DTO projection.
- Các alias genreNames, actorNames, directorNames, sharedActorCount phải khớp chính xác tên property trong record.

## 8. Phân trang từ service và controller

Không để client truyền page size tùy ý. Service cần kiểm tra page không âm và giới hạn size để bảo vệ database:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

@Service
public class MovieCatalogService {

    private static final int MAX_PAGE_SIZE = 100;

    private final MovieRepository movieRepository;

    public MovieCatalogService(MovieRepository movieRepository) {
        this.movieRepository = movieRepository;
    }

    @Transactional(readOnly = true)
    public MoviePageResponse search(
            String title,
            String genre,
            Integer fromYear,
            Integer toYear,
            int page,
            int size) {

        if (page < 0) {
            throw new IllegalArgumentException("page must be zero or greater");
        }
        if (size < 1 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException("size must be between 1 and 100");
        }
        if (fromYear != null && toYear != null && fromYear > toYear) {
            throw new IllegalArgumentException("fromYear must not exceed toYear");
        }

        String normalizedTitle = StringUtils.hasText(title) ? title.trim() : null;
        String normalizedGenre = StringUtils.hasText(genre) ? genre.trim() : null;

        Pageable pageable = PageRequest.of(page, size, Sort.unsorted());
        Page<MovieSearchRow> result = movieRepository.search(
            normalizedTitle,
            normalizedGenre,
            fromYear,
            toYear,
            pageable
        );

        return new MoviePageResponse(
            result.getContent(),
            result.getNumber(),
            result.getSize(),
            result.getTotalElements(),
            result.getTotalPages(),
            result.hasNext()
        );
    }
}
~~~

DTO response cho pagination:

~~~java
import java.util.List;

public record MoviePageResponse(
        List<MovieSearchRow> content,
        int page,
        int size,
        long totalElements,
        int totalPages,
        boolean hasNext) {
}
~~~

Controller:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/movies")
public class MovieController {

    private final MovieCatalogService movieCatalogService;

    public MovieController(MovieCatalogService movieCatalogService) {
        this.movieCatalogService = movieCatalogService;
    }

    @GetMapping
    public MoviePageResponse search(
            @RequestParam(required = false) String title,
            @RequestParam(required = false) String genre,
            @RequestParam(required = false) Integer fromYear,
            @RequestParam(required = false) Integer toYear,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {

        return movieCatalogService.search(
            title, genre, fromYear, toYear, page, size
        );
    }
}
~~~

Ví dụ request:

~~~http
GET /api/movies?genre=Sci-Fi&page=0&size=10
~~~

Response có dạng:

~~~json
{
  "content": [
    {
      "movieId": "M-01",
      "title": "The Graph",
      "released": 2024,
      "genreNames": ["Sci-Fi", "Drama"],
      "actorNames": ["An", "Binh"]
    },
    {
      "movieId": "M-02",
      "title": "Query Paths",
      "released": 2022,
      "genreNames": ["Sci-Fi"],
      "actorNames": ["An"]
    }
  ],
  "page": 0,
  "size": 10,
  "totalElements": 2,
  "totalPages": 1,
  "hasNext": false
}
~~~

Trong ứng dụng thực tế, nên ánh xạ lỗi tham số không hợp lệ sang HTTP 400 bằng validation hoặc exception handler. Không trả stack trace hay Cypher nội bộ cho client.

## 9. Query chi tiết: tổng hợp nhiều nhánh relationship

Endpoint chi tiết cần danh sách genre, director và actor. Ba nhánh relationship phải được gom lần lượt:

~~~cypher
MATCH (m:Movie {movieId: $movieId})

OPTIONAL MATCH (m)-[:IN_GENRE]->(g:Genre)
WITH m, collect(DISTINCT g.name) AS genreNames

OPTIONAL MATCH (m)<-[:DIRECTED]-(director:Person)
WITH m, genreNames,
     collect(DISTINCT director.name) AS directorNames

OPTIONAL MATCH (m)<-[:ACTED_IN]-(actor:Person)
WITH m, genreNames, directorNames,
     collect(DISTINCT actor.name) AS actorNames

RETURN m, genreNames, directorNames, actorNames;
~~~

Query này minh họa một nguyên tắc: mỗi nhánh relationship được aggregate trước khi mở nhánh tiếp theo. Nếu phim không có diễn viên hoặc đạo diễn, OPTIONAL MATCH vẫn giữ phim và collection tương ứng là danh sách rỗng.

Service:

~~~java
@Transactional(readOnly = true)
public MovieDetailRow findDetail(String movieId) {
    return movieRepository.findDetailByMovieId(movieId)
        .orElseThrow(() -> new MovieNotFoundException(movieId));
}
~~~

Thêm method này vào MovieCatalogService ở phần phân trang; đây là một read operation nên có thể dùng cùng read-only transaction boundary.

Controller có thể cung cấp endpoint:

~~~java
@GetMapping("/{movieId}")
public MovieDetailRow getDetail(@PathVariable String movieId) {
    return movieCatalogService.findDetail(movieId);
}
~~~

MovieNotFoundException là exception do ứng dụng định nghĩa và cần được ánh xạ sang HTTP 404. DTO detail không chứa entity Person hay Genre đầy đủ; nó chỉ có tên và ID của phim cùng danh sách scalar cần hiển thị.

## 10. Query gợi ý: tìm phim có diễn viên chung

Một yêu cầu graph-oriented khác là gợi ý phim có diễn viên chung với phim đang xem:

~~~cypher
MATCH (source:Movie {movieId: $movieId})
      <-[:ACTED_IN]-(shared:Person)-[:ACTED_IN]->(candidate:Movie)
WHERE candidate <> source

WITH candidate,
     count(DISTINCT shared) AS sharedActorCount,
     collect(DISTINCT shared.name) AS sharedActorNames

OPTIONAL MATCH (candidate)-[:IN_GENRE]->(genre:Genre)
WITH candidate, sharedActorCount, sharedActorNames,
     collect(DISTINCT genre.name) AS genreNames

RETURN candidate,
       sharedActorCount,
       sharedActorNames,
       genreNames
ORDER BY sharedActorCount DESC,
         candidate.released DESC,
         candidate.movieId ASC
LIMIT $limit;
~~~

Query thực hiện các bước:

1. Từ source movie đi ngược tới diễn viên.
2. Từ diễn viên đi tới các phim khác.
3. Bỏ phim nguồn.
4. Gom số diễn viên chung và tên diễn viên theo từng candidate.
5. Lấy genre của candidate.
6. Sắp xếp theo số diễn viên chung, năm phát hành và ID.
7. Giới hạn số kết quả.

Điểm cần chú ý là WITH candidate, ... tạo một hàng cho mỗi phim gợi ý trước khi lấy thể loại. Nếu không gom nhóm, mỗi candidate có nhiều diễn viên và thể loại sẽ tạo fan-out.

Service có thể giới hạn limit trong khoảng 1 đến 20 và gọi repository:

~~~java
@Transactional(readOnly = true)
public List<SimilarMovieRow> findSimilar(String movieId, int limit) {
    if (limit < 1 || limit > 20) {
        throw new IllegalArgumentException("limit must be between 1 and 20");
    }
    return movieRepository.findSimilarMovies(movieId, limit);
}
~~~

Thêm endpoint gợi ý vào MovieController:

~~~java
import java.util.List;

@GetMapping("/{movieId}/similar")
public List<SimilarMovieRow> getSimilar(
        @PathVariable String movieId,
        @RequestParam(defaultValue = "5") int limit) {
    return movieCatalogService.findSimilar(movieId, limit);
}
~~~

## 11. Khi nào chọn Page, Slice hay List?

| Return type | Metadata | Query count | Khi nên dùng |
|---|---|---|---|
| Page<T> | Tổng phần tử, tổng trang, trang hiện tại | Cần count query riêng với custom query | UI cần hiển thị tổng số trang |
| Slice<T> | Có trang tiếp theo hay không | Không cần count query | Cuộn hoặc tải thêm từng trang |
| List<T> | Chỉ có danh sách | Không tạo metadata Page | Kết quả nhỏ, giới hạn cố định |
| Flux<T> | Luồng phần tử | Streaming theo reactive driver | Xử lý reactive hoặc dữ liệu lớn theo luồng |

Với custom Cypher trả Slice, query vẫn phải có $skip và $limit, phải có ORDER BY ổn định và Pageable nên là unsorted. SDN có thể xác định trang kế tiếp bằng cách lấy thêm một phần tử. Với Page, cần khai báo countQuery riêng. Count query có thể tốn chi phí nếu bộ lọc phức tạp hoặc graph lớn; chỉ yêu cầu tổng số khi giao diện thực sự cần.

## 12. Pagination ổn định và hiệu năng

### 12.1. Luôn có thứ tự xác định

Không phân trang một query nếu không có ORDER BY. Khi nhiều phim có cùng released, chỉ sắp xếp theo năm vẫn có thể làm kết quả giữa các request không ổn định. Hãy thêm business ID làm tie-breaker:

~~~cypher
ORDER BY m.released DESC, m.movieId ASC
~~~

### 12.2. Phân trang sau khi aggregate theo root node

Trong capstone, mỗi row cuối cùng đại diện cho một Movie. SKIP/LIMIT nằm sau các WITH aggregate để phân trang phim, không phân trang từng hàng actor/genre trung gian.

Nếu đặt SKIP/LIMIT trước khi gom relationship, một phim có nhiều relationship có thể chiếm nhiều slot và làm trang trả ít phim hơn mong muốn.

### 12.3. Offset lớn sẽ đắt

SKIP lớn buộc database đi qua các hàng trước offset để xác định phần cần trả. Khi số trang rất lớn, offset pagination có thể chậm. Một phương án là keyset pagination dựa trên khóa sắp xếp cuối cùng của trang trước.

Ví dụ nếu thứ tự là released giảm dần, movieId tăng dần, trang tiếp theo sau cursor (lastReleased, lastMovieId) có điều kiện:

~~~cypher
MATCH (m:Movie)
WHERE m.released < $lastReleased
   OR (m.released = $lastReleased AND m.movieId > $lastMovieId)
RETURN m
ORDER BY m.released DESC, m.movieId ASC
LIMIT $limit;
~~~

Ví dụ này giả định released không null. Nếu dữ liệu cho phép released null, hãy định nghĩa rõ thứ tự null và đưa trạng thái null vào cursor. Keyset pagination tránh phải bỏ qua toàn bộ các hàng của những trang trước, nhưng API phải lưu và trả cursor thay vì page number.

### 12.4. Giữ count query đơn giản

Count query chỉ nên tính số root Movie phù hợp bộ lọc. Không cần thu thập actorNames nếu danh sách diễn viên không dùng để lọc. Không dùng COUNT(*) sau một phép nối nhiều relationship nếu chưa gom về một hàng cho mỗi Movie.

## 13. Kiểm thử integration

Test cần chạy trên Neo4j test database đã được cấu hình cho Spring context, ví dụ Test Harness hoặc Testcontainers. Dữ liệu fixture phải giống cấu trúc của capstone.

Ví dụ test repository:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

@DataNeo4jTest
class MovieRepositoryCapstoneTest {

    @Autowired
    MovieRepository movieRepository;

    @Autowired
    Neo4jClient neo4jClient;

    @BeforeEach
    void createFixture() {
        neo4jClient.query("""
            CREATE (an:Person {personId: 'P-01', name: 'An'})
            CREATE (binh:Person {personId: 'P-02', name: 'Binh'})
            CREATE (chi:Person {personId: 'P-03', name: 'Chi'})
            CREATE (lan:Person {personId: 'P-04', name: 'Lan'})
            CREATE (minh:Person {personId: 'P-05', name: 'Minh'})
            CREATE (scifi:Genre {name: 'Sci-Fi'})
            CREATE (drama:Genre {name: 'Drama'})
            CREATE (m1:Movie {movieId: 'M-01', title: 'The Graph', released: 2024})
            CREATE (m2:Movie {movieId: 'M-02', title: 'Query Paths', released: 2022})
            CREATE (m3:Movie {movieId: 'M-03', title: 'Graph Stories', released: 2025})
            CREATE (m4:Movie {movieId: 'M-04', title: 'Pattern Lab', released: 2021})
            CREATE (an)-[:ACTED_IN]->(m1)
            CREATE (binh)-[:ACTED_IN]->(m1)
            CREATE (lan)-[:DIRECTED]->(m1)
            CREATE (m1)-[:IN_GENRE]->(scifi)
            CREATE (m1)-[:IN_GENRE]->(drama)
            CREATE (an)-[:ACTED_IN]->(m2)
            CREATE (minh)-[:DIRECTED]->(m2)
            CREATE (m2)-[:IN_GENRE]->(scifi)
            CREATE (binh)-[:ACTED_IN]->(m3)
            CREATE (chi)-[:ACTED_IN]->(m3)
            CREATE (lan)-[:DIRECTED]->(m3)
            CREATE (m3)-[:IN_GENRE]->(drama)
            CREATE (minh)-[:DIRECTED]->(m4)
            CREATE (m4)-[:IN_GENRE]->(drama)
            """).run();
    }

    @Test
    void shouldReturnOneMoviePerRowAndCorrectTotal() {
        Page<MovieSearchRow> firstPage = movieRepository.search(
            null,
            "sci-fi",
            null,
            null,
            PageRequest.of(0, 1, Sort.unsorted())
        );

        assertThat(firstPage.getTotalElements()).isEqualTo(2);
        assertThat(firstPage.getContent()).hasSize(1);

        MovieSearchRow first = firstPage.getContent().get(0);
        assertThat(first.movieId()).isEqualTo("M-01");
        assertThat(first.genreNames())
            .containsExactlyInAnyOrder("Sci-Fi", "Drama");
        assertThat(first.actorNames())
            .containsExactlyInAnyOrder("An", "Binh");

        Page<MovieSearchRow> secondPage = movieRepository.search(
            null,
            "Sci-Fi",
            null,
            null,
            PageRequest.of(1, 1, Sort.unsorted())
        );

        assertThat(secondPage.getTotalElements()).isEqualTo(2);
        assertThat(secondPage.getContent()).hasSize(1);
        assertThat(secondPage.getContent().get(0).movieId()).isEqualTo("M-02");
    }

    @Test
    void shouldKeepMovieWithoutActors() {
        MovieDetailRow detail = movieRepository.findDetailByMovieId("M-04")
            .orElseThrow();

        assertThat(detail.movieId()).isEqualTo("M-04");
        assertThat(detail.actorNames()).isEmpty();
        assertThat(detail.directorNames()).containsExactly("Minh");
        assertThat(detail.genreNames()).containsExactly("Drama");
    }

    @Test
    void shouldFindSimilarMoviesBySharedActors() {
        var recommendations = movieRepository.findSimilarMovies("M-01", 5);

        assertThat(recommendations)
            .extracting(SimilarMovieRow::movieId)
            .containsExactly("M-03", "M-02");

        assertThat(recommendations)
            .extracting(SimilarMovieRow::sharedActorCount)
            .containsOnly(1L);
    }
}
~~~

Fixture được tạo bằng Neo4jClient trong @BeforeEach. Với @DataNeo4jTest, thao tác này tham gia transaction test và được rollback sau mỗi test; nếu thay bằng Driver/session độc lập, hãy tự quản lý việc dọn dữ liệu.

### 13.1. Các ca kiểm thử bắt buộc

| Ca kiểm thử | Điều cần xác nhận |
|---|---|
| Không truyền filter | Trả toàn bộ phim theo thứ tự ổn định |
| Filter genre Sci-Fi | Chỉ có M-01 và M-02 |
| Filter title Query | Chỉ khớp Query Paths |
| Khoảng năm 2023–2025 | Có M-01 và M-03 |
| M-01 có nhiều actor/genre | Một row, không lặp tên |
| M-04 không có actor | Query vẫn trả phim và actorNames rỗng |
| Page size 1 | Hai trang có hai phim khác nhau |
| Count query | totalElements khớp số phim, không phải số relationship row |
| page âm hoặc size ngoài giới hạn | Service từ chối request |
| Không tồn tại movieId | Detail endpoint trả 404 |

## 14. Đánh giá query bằng PROFILE

Sau khi test đúng kết quả, dùng PROFILE để kiểm tra query có làm việc thừa hay không:

~~~cypher
PROFILE
MATCH (m:Movie)
WHERE m.released >= 2022
OPTIONAL MATCH (m)-[:IN_GENRE]->(g:Genre)
WITH m, collect(DISTINCT g.name) AS genreNames
WHERE 'Sci-Fi' IN genreNames
OPTIONAL MATCH (m)<-[:ACTED_IN]-(actor:Person)
WITH m, genreNames, collect(DISTINCT actor.name) AS actorNames
RETURN m, genreNames, actorNames
ORDER BY m.released DESC, m.movieId ASC
SKIP 0
LIMIT 10;
~~~

Quan sát:

- Rows trước và sau mỗi WITH để thấy cardinality giảm như thế nào.
- DB Hits để nhận biết operator truy cập nhiều node/relationship.
- Operator expand và index seek/scan.
- Sort và aggregation có thể cần memory.
- Page cache hit/miss nếu có trong profile.

Đừng chỉ tối ưu theo số record cuối cùng. Query trả 10 phim vẫn có thể duyệt hàng triệu relationship trước khi gom nhóm. Với dữ liệu lớn, hãy xem query plan, thêm index/constraint phù hợp với điều kiện lọc và xem xét full-text index nếu chức năng tìm title cần tìm kiếm toàn văn.

## 15. Các lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Một phim xuất hiện nhiều lần | Nhiều MATCH relationship tạo nhiều row | Aggregate theo Movie bằng WITH và collect(DISTINCT ...) |
| actorNames bị lặp theo số genre | Actor và genre được MATCH song song trước aggregate | Aggregate một nhánh trước khi mở nhánh tiếp |
| Phim không có actor biến mất | Dùng MATCH thay cho OPTIONAL MATCH | Dùng OPTIONAL MATCH nếu quan hệ không bắt buộc |
| genreNames bị rỗng khi filter genre | Lọc g.name trước khi collect | Gom genre trước, rồi lọc danh sách trong WHERE sau WITH |
| totalElements lớn hơn số phim | Count sau join relationship tạo nhiều row | Count root node sau khi gom về một hàng mỗi Movie |
| Page chỉ trả ít phim hơn pageSize | SKIP/LIMIT áp dụng trước khi aggregate | Phân trang sau bước gom nhóm theo root node |
| Query Page báo thiếu tham số | Custom query không có $skip hoặc $limit | Thêm cả hai tham số vào Cypher |
| Custom Page không có tổng số chính xác | Thiếu countQuery | Khai báo countQuery tương ứng với toàn bộ filter |
| DTO field null hoặc mapping lỗi | Alias không khớp tên property DTO | Dùng tên alias chính xác, kiểm tra kiểu dữ liệu |
| DTO projection không nhận Map | SDN DTO projection không hỗ trợ Map bổ sung | Dùng scalar/collection hoặc Neo4jClient mapper riêng |
| Kết quả giữa các trang bị đổi thứ tự | ORDER BY không có tie-breaker | Thêm business ID vào ORDER BY |
| Trang sâu chạy chậm | Offset SKIP lớn | Dùng keyset/cursor pagination |
| Query trả payload lớn | Trả node/relationship không cần thiết hoặc collect không giới hạn | Chỉ trả field cần và giới hạn collection |
| Page count quá chậm | Count query phải duyệt graph lớn | Dùng Slice nếu UI không cần tổng số hoặc tối ưu điều kiện lọc |

## 16. Tiêu chí nghiệm thu capstone

Capstone được xem là hoàn thành khi:

- Graph có đủ Person, Movie, Genre và relationship đúng hướng.
- Constraint bảo đảm business ID duy nhất.
- Query tìm kiếm dùng ít nhất hai bước WITH và có OPTIONAL MATCH.
- Query trả đúng một row cho mỗi Movie.
- Query không nhân chéo actor với genre.
- DTO projection nhận được root Movie và các collection bổ sung.
- Page query có ORDER BY ổn định, $skip và $limit.
- Count query dùng cùng bộ lọc với query lấy trang.
- Service xác thực page, size và khoảng năm.
- API trả response DTO với pagination metadata.
- Query detail và similar movies đều dùng multi-step Cypher.
- Integration test kiểm tra filter, projection, count, pagination và trường hợp không có relationship.
- PROFILE được dùng để xem query plan và cardinality.

## 17. Mở rộng sau capstone

Khi đã hoàn thành phiên bản cơ bản, có thể mở rộng:

1. Thêm filter theo đạo diễn và số diễn viên tối thiểu.
2. Thêm khoảng điểm đánh giá và sort theo released hoặc rating.
3. Trả relationship property như vai diễn bằng @RelationshipProperties và DTO riêng.
4. Dùng full-text index để tìm kiếm tiêu đề và mô tả.
5. Thay Page bằng Slice cho infinite scroll.
6. Thêm cursor pagination để tránh offset lớn.
7. Tạo projection riêng cho mobile và web để giảm payload.
8. Thêm authorization để chỉ một số vai trò được xem trường nội bộ.
9. Đo thời gian query, record count và payload size cho từng endpoint.
10. Viết test cho graph có nhiều diễn viên, nhiều thể loại và relationship bị thiếu.

## 18. Bài tập tự đánh giá

1. Giải thích vì sao query có hai OPTIONAL MATCH song song có thể tạo tích Descartes giữa actor và genre.
2. Viết lại query để chỉ trả một hàng cho mỗi Movie.
3. Giải thích tại sao WITH m, collect(g.name) AS genreNames làm thay đổi scope.
4. Chuyển điều kiện genre filter từ trước WITH sang sau WITH và so sánh kết quả.
5. Viết countQuery tương ứng với bộ lọc title, year và genre.
6. Thay Page bằng Slice và nêu khác biệt về count query.
7. Cố ý bỏ $skip hoặc $limit trong custom query và quan sát cảnh báo/kết quả.
8. Bỏ movieId khỏi ORDER BY và giải thích vì sao phân trang có thể không ổn định.
9. Thêm relationship IN_GENRE thứ hai vào M-01 và xác nhận không làm actorNames lặp.
10. Thêm một phim không có relationship ACTED_IN và kiểm tra OPTIONAL MATCH.
11. Dùng PROFILE để tìm operator tạo nhiều hàng nhất.
12. Viết keyset pagination dựa trên released và movieId.
13. Giải thích vì sao DTO projection custom query cần trả root node m cùng các property bổ sung.
14. Đưa MovieSearchRow thành DTO response riêng và viết test JSON.
15. Đề xuất một query count rẻ hơn nếu giao diện chỉ cần biết có trang tiếp theo.

## Tài liệu tham khảo

- [Spring Data Neo4j — Projections](https://docs.spring.io/spring-data/neo4j/reference/projections/sdn-projections.html)
- [Spring Data Neo4j — Repository projections](https://docs.spring.io/spring-data/neo4j/reference/repositories/projections.html)
- [Spring Data Neo4j FAQ — Custom queries with Page and Slice](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j — Query methods and pagination](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-methods-details.html)
- [Neo4j Cypher Manual — WITH](https://neo4j.com/docs/cypher-manual/current/clauses/with/)
- [Neo4j Cypher Manual — OPTIONAL MATCH](https://neo4j.com/docs/cypher-manual/current/clauses/optional-match/)
- [Neo4j Cypher Manual — Aggregating functions](https://neo4j.com/docs/cypher-manual/current/functions/aggregating/)
- [Neo4j Cypher Manual — ORDER BY, SKIP and LIMIT](https://neo4j.com/docs/cypher-manual/current/clauses/order-by/)
- [Neo4j Cypher Manual — Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/)
