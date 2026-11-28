# Khai báo ReactiveNeo4jRepository và các kiểu kết quả phù hợp

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Khai báo repository reactive bằng `ReactiveNeo4jRepository<T, ID>`.
- Hiểu các repository interface mà `ReactiveNeo4jRepository` kế thừa và nhóm thao tác được cung cấp.
- Chọn `Mono<T>`, `Flux<T>`, `Mono<Boolean>`, `Mono<Long>` và `Mono<Void>` theo số lượng kết quả.
- Khai báo derived query và custom Cypher với kiểu trả về reactive.
- Sử dụng `Sort`, giới hạn kết quả và xây dựng truy vấn phân trang phù hợp với reactive.
- Tránh chuyển luồng reactive thành thao tác đồng bộ bằng `block()` hoặc tự gọi `subscribe()` trong tầng repository/service.

## 1. Reactive repository trong Spring Data Neo4j

Spring Data Neo4j (SDN) hỗ trợ hai mô hình truy cập dữ liệu: imperative và reactive. Mô hình reactive dựa trên Reactive Streams và Project Reactor, cho phép biểu diễn kết quả database bằng publisher thay vì trả về object hoặc collection đồng bộ.

Repository reactive chuyên biệt của SDN là:

```java
org.springframework.data.neo4j.repository.ReactiveNeo4jRepository
```

Interface này được tham số hóa bằng:

- `T`: kiểu entity mà repository quản lý.
- `ID`: kiểu của trường định danh `@Id` trong entity.

Ví dụ, nếu entity `Movie` có ID kiểu `String`, repository được khai báo là `ReactiveNeo4jRepository<Movie, String>`.

Reactive repository không làm thay đổi cách mô hình hóa node và relationship. Entity vẫn dùng các annotation như `@Node`, `@Id`, `@Relationship` và `@RelationshipProperties`. Điểm thay đổi nằm ở API truy cập: các thao tác đọc và ghi trả về `Mono` hoặc `Flux`.

## 2. Chuẩn bị reactive infrastructure

Reactive access yêu cầu Spring reactive infrastructure và Neo4j reactive driver support. SDN chứa cả imperative lẫn reactive programming model trong cùng thư viện; ứng dụng cần có các dependency reactive phù hợp, thường là Reactor và Spring WebFlux.

Với Spring Boot, dependency thường dùng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-neo4j</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

Cấu hình kết nối Neo4j vẫn dùng namespace `spring.neo4j`:

```properties
spring.neo4j.uri=bolt://localhost:7687
spring.neo4j.authentication.username=neo4j
spring.neo4j.authentication.password=secret
```

Reactive model yêu cầu Neo4j server phiên bản 4 trở lên và Spring reactive stack. Nếu dùng Spring Boot starter, repository thường được tự động bật theo cơ chế auto-configuration. Không cần tự khai báo annotation enable repository nếu cấu hình mặc định đã quét đúng package.

Nếu ứng dụng tự cấu hình repository, có thể dùng `@EnableReactiveNeo4jRepositories`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.repository.config.EnableReactiveNeo4jRepositories;

@Configuration
@EnableReactiveNeo4jRepositories(
    basePackages = "com.example.graph.repository"
)
public class ReactiveNeo4jConfiguration {
}
```

Annotation này cho phép chỉ định package repository cần quét và các thành phần reactive tương ứng như `ReactiveNeo4jTemplate` hoặc `ReactiveNeo4jTransactionManager` khi ứng dụng có cấu hình riêng.

Không nên trộn imperative và reactive database access tùy tiện trong cùng một luồng nghiệp vụ. Dù SDN hỗ trợ cả hai mô hình trong cùng binary, việc trộn chúng khiến ranh giới transaction và cách thực thi khó dự đoán hơn.

## 3. Entity dùng trong ví dụ

Giả sử ứng dụng quản lý phim. Entity được khai báo như một node thông thường:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Movie")
public class Movie {

    @Id
    private String id;

    private String title;

    private Integer released;

    private String imdbId;

    protected Movie() {
    }

    public Movie(
            String id,
            String title,
            Integer released,
            String imdbId) {
        this.id = id;
        this.title = title;
        this.released = released;
        this.imdbId = imdbId;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Integer getReleased() {
        return released;
    }

    public String getImdbId() {
        return imdbId;
    }
}
```

Entity vẫn là mô hình dữ liệu được SDN ánh xạ sang node `Movie`. Reactive repository không yêu cầu entity phải kế thừa một lớp đặc biệt hoặc chứa `Mono`/`Flux` trong từng field.

## 4. Khai báo ReactiveNeo4jRepository

Repository chỉ cần kế thừa `ReactiveNeo4jRepository` và khai báo domain type cùng ID type:

```java
import org.springframework.data.neo4j.repository.ReactiveNeo4jRepository;

public interface MovieRepository
        extends ReactiveNeo4jRepository<Movie, String> {
}
```

`ReactiveNeo4jRepository` kế thừa các interface sau:

| Interface cha | Chức năng |
| --- | --- |
| `ReactiveCrudRepository<T, ID>` | Các thao tác CRUD reactive |
| `ReactiveSortingRepository<T, ID>` | Các thao tác tìm kiếm có sắp xếp |
| `ReactiveQueryByExampleExecutor<T>` | Tìm kiếm theo Example trong mô hình reactive |
| `Repository<T, ID>` | Marker interface của Spring Data repository |

Vì vậy, repository có sẵn các thao tác như tìm theo ID, tìm tất cả, lưu, xóa, kiểm tra tồn tại và đếm dữ liệu. Không cần tự viết implementation cho những thao tác CRUD cơ bản.

## 5. Các kiểu kết quả reactive quan trọng

Trong Project Reactor, SDN chủ yếu dùng hai kiểu publisher:

- `Mono<T>`: phát ra không phần tử hoặc một phần tử.
- `Flux<T>`: phát ra không, một hoặc nhiều phần tử.

Chọn kiểu trả về theo số lượng kết quả mà phương thức được kỳ vọng:

| Kiểu trả về | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `Mono<Movie>` | Không có hoặc tối đa một Movie | Tìm theo mã duy nhất |
| `Flux<Movie>` | Không, một hoặc nhiều Movie | Tìm phim theo năm phát hành |
| `Mono<Boolean>` | Kết quả kiểm tra đúng/sai | Kiểm tra node tồn tại |
| `Mono<Long>` | Một giá trị đếm | Đếm số node |
| `Mono<Void>` | Chỉ quan tâm thao tác hoàn tất | Xóa entity |

### 5.1. Mono<T> cho kết quả đơn

`Mono<T>` phù hợp khi điều kiện truy vấn được kỳ vọng trả về tối đa một entity, chẳng hạn tìm theo một mã nghiệp vụ duy nhất:

```java
import reactor.core.publisher.Mono;

public interface MovieRepository
        extends ReactiveNeo4jRepository<Movie, String> {

    Mono<Movie> findByImdbId(String imdbId);
}
```

Hành vi:

- Có một node phù hợp: `Mono` phát ra Movie.
- Không có node phù hợp: `Mono.empty()`.
- Có nhiều node phù hợp: query method yêu cầu một kết quả có thể phát sinh `IncorrectResultSizeDataAccessException`.

Vì vậy, nếu dùng `Mono<Movie>` cho `findByImdbId`, dữ liệu nên bảo đảm `imdbId` là duy nhất bằng unique constraint hoặc quy tắc nghiệp vụ tương ứng.

Không dùng `Optional<Movie>` làm kiểu trả về reactive. `Mono<Movie>` đã biểu diễn trường hợp có hoặc không có giá trị mà không cần bọc thêm `Optional`.

### 5.2. Flux<T> cho nhiều kết quả

Khi truy vấn có thể trả về nhiều node, dùng `Flux<T>`:

```java
import reactor.core.publisher.Flux;

public interface MovieRepository
        extends ReactiveNeo4jRepository<Movie, String> {

    Flux<Movie> findByReleasedGreaterThanEqual(Integer year);
}
```

Nếu truy vấn tìm các phim phát hành từ năm 2020 trở đi, `Flux<Movie>` phát ra lần lượt các kết quả phù hợp. Nếu không có kết quả, publisher hoàn tất mà không phát phần tử nào.

`Flux` phù hợp với kết quả có số lượng thay đổi. Không cần biết trước có bao nhiêu phim được trả về khi khai báo method.

### 5.3. Các kiểu trả về từ CRUD kế thừa

Các phương thức CRUD cũng sử dụng kiểu reactive:

| Phương thức | Kiểu trả về thường gặp | Ý nghĩa |
| --- | --- | --- |
| `findById(id)` | `Mono<T>` | Tìm một entity theo ID |
| `findAll()` | `Flux<T>` | Đọc nhiều entity |
| `findAllById(ids)` | `Flux<T>` | Đọc các entity theo nhiều ID |
| `save(entity)` | `Mono<S>` | Lưu một entity và phát ra entity đã lưu |
| `saveAll(entities)` | `Flux<S>` | Lưu nhiều entity |
| `existsById(id)` | `Mono<Boolean>` | Kiểm tra tồn tại |
| `count()` | `Mono<Long>` | Đếm entity |
| `deleteById(id)` | `Mono<Void>` | Xóa theo ID |

Ví dụ sử dụng:

```java
Mono<Movie> saved = movieRepository.save(
    new Movie("m-101", "Example Film", 2024, "tt1234567")
);

Mono<Movie> found = movieRepository.findById("m-101");

Mono<Boolean> exists = movieRepository.existsById("m-101");

Mono<Long> total = movieRepository.count();

Mono<Void> deleted = movieRepository.deleteById("m-101");
```

Các biến trên chỉ giữ publisher mô tả thao tác. Chúng chưa nhất thiết đã thực thi truy vấn tại thời điểm được tạo.

## 6. Kết hợp derived query với Mono và Flux

Các quy tắc đặt tên derived query vẫn dựa trên property của entity. Khác biệt là kiểu trả về được chọn theo số lượng kết quả:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import org.springframework.data.domain.Sort;
import org.springframework.data.neo4j.repository.ReactiveNeo4jRepository;

public interface MovieRepository
        extends ReactiveNeo4jRepository<Movie, String> {

    Mono<Movie> findByImdbId(String imdbId);

    Flux<Movie> findByReleasedGreaterThanEqual(Integer year);

    Flux<Movie> findByTitleContainingIgnoreCase(
        String keyword,
        Sort sort
    );

    Flux<Movie> findTop10ByReleasedGreaterThanEqualOrderByReleasedDesc(
        Integer year
    );
}
```

Ví dụ gọi:

```java
Flux<Movie> recentMovies =
    movieRepository.findByReleasedGreaterThanEqual(2020);

Flux<Movie> sortedMovies =
    movieRepository.findByTitleContainingIgnoreCase(
        "star",
        Sort.by(Sort.Order.asc("title"), Sort.Order.desc("released"))
    );

Flux<Movie> topMovies =
    movieRepository.findTop10ByReleasedGreaterThanEqualOrderByReleasedDesc(
        2015
    );
```

Lưu ý:

- `Sort` dùng tên property của entity, ví dụ `title` hoặc `released`.
- `Top10` giới hạn số kết quả được trả về.
- Với kết quả nhiều phần tử, dùng `Flux` kể cả khi truy vấn có giới hạn số lượng.
- Với truy vấn một kết quả, hãy bảo đảm điều kiện thực sự có tối đa một bản ghi.

## 7. Custom Cypher cũng trả về Mono hoặc Flux

Phương thức dùng `@Query` có thể trả về publisher tương ứng với kết quả Cypher:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface MovieRepository
        extends ReactiveNeo4jRepository<Movie, String> {

    @Query("""
        MATCH (m:Movie)
        WHERE m.released >= $year
        RETURN m
        ORDER BY m.released DESC, m.title ASC
        """)
    Flux<Movie> findReleasedSince(@Param("year") Integer year);

    @Query("""
        MATCH (m:Movie {imdbId: $imdbId})
        RETURN m
        """)
    Mono<Movie> findOneByImdbId(@Param("imdbId") String imdbId);
}
```

Chọn kiểu kết quả dựa trên số record mà Cypher có thể trả về, không chỉ dựa vào việc query có dùng `MATCH` hay không.

- `Flux<Movie>` khi có thể có nhiều node.
- `Mono<Movie>` khi query phải trả tối đa một node.
- Nếu custom query trả nhiều record nhưng khai báo `Mono<Movie>`, nhiều kết quả sẽ tạo lỗi cardinality thay vì tự chọn ngẫu nhiên một node.

Với custom Cypher, hãy bảo đảm phần `RETURN` có cấu trúc phù hợp với entity mà SDN cần ánh xạ.

## 8. Phân trang, giới hạn và sắp xếp trong reactive repository

`ReactiveNeo4jRepository` kế thừa `ReactiveSortingRepository`, do đó có API sắp xếp bằng `Sort`. Các derived query cũng có thể nhận `Sort` khi cần thứ tự động.

Reactive repository hướng tới publisher `Flux` và `Mono`; `Page<T>` là wrapper đồng bộ có metadata tổng số trang nên không phải kiểu kết quả reactive phù hợp. Nếu cần trả dữ liệu theo từng nhóm, có thể chọn một trong các cách:

- Dùng `Flux<T>` với `Sort` để sắp xếp kết quả.
- Dùng từ khóa `First` hoặc `Top` để giới hạn số lượng.
- Với custom Cypher, bind `SKIP` và `LIMIT` rồi trả về `Flux<T>`.
- Nếu cần tổng số bản ghi, thực hiện thêm truy vấn đếm trả về `Mono<Long>` và kết hợp hai publisher thành DTO kết quả.

Ví dụ custom query có offset và limit rõ ràng:

```java
@Query("""
    MATCH (m:Movie)
    WHERE m.released >= $year
    RETURN m
    ORDER BY m.released DESC, m.id ASC
    SKIP $skip
    LIMIT $limit
    """)
Flux<Movie> findMovieWindow(
    @Param("year") Integer year,
    @Param("skip") long skip,
    @Param("limit") long limit
);
```

Có thể khai báo truy vấn đếm riêng:

```java
@Query("""
    MATCH (m:Movie)
    WHERE m.released >= $year
    RETURN count(m)
    """)
Mono<Long> countMoviesReleasedSince(@Param("year") Integer year);
```

Trong custom query, ứng dụng chịu trách nhiệm bảo đảm `ORDER BY`, `SKIP` và `LIMIT` được đặt đúng thứ tự. Hãy dùng thứ tự ổn định, ví dụ thêm ID làm tiêu chí phụ khi nhiều node có cùng năm phát hành.

## 9. Publisher là lazy: truy vấn chạy khi có subscription

Một đặc điểm quan trọng của Reactor là publisher thường lazy. Khi gọi repository, ứng dụng nhận được mô tả của một thao tác; truy vấn được thực thi khi có subscriber tiêu thụ publisher.

Ví dụ:

```java
Mono<Movie> moviePublisher =
    movieRepository.findByImdbId("tt1234567");
```

Đoạn code trên tạo publisher. Nếu không có subscriber, không có kết quả được tiêu thụ và thao tác có thể chưa được thực thi.

Trong tầng service, nên trả publisher cho tầng gọi tiếp theo:

```java
import reactor.core.publisher.Flux;
import org.springframework.stereotype.Service;

@Service
public class MovieService {

    private final MovieRepository movieRepository;

    public MovieService(MovieRepository movieRepository) {
        this.movieRepository = movieRepository;
    }

    public Flux<Movie> findRecentMovies(Integer fromYear) {
        return movieRepository.findByReleasedGreaterThanEqual(fromYear);
    }
}
```

Trong Spring WebFlux, controller có thể trả trực tiếp `Flux` hoặc `Mono`; framework sẽ subscribe và ghi kết quả vào HTTP response.

Không gọi `subscribe()` bên trong repository hoặc service chỉ để kích hoạt query. Làm vậy tách thao tác khỏi pipeline của bên gọi và khiến việc quản lý lỗi, cancellation, transaction hoặc kết quả trở nên khó kiểm soát.

Cũng không gọi `block()` trong luồng reactive thông thường. `block()` chuyển thao tác thành đồng bộ, có thể chặn event-loop và làm mất lợi ích của reactive execution.

## 10. Kết hợp nhiều publisher mà không chặn luồng

Reactor cung cấp các toán tử để kết hợp publisher. Ví dụ, cần trả danh sách phim cùng tổng số phim phù hợp:

```java
import reactor.core.publisher.Mono;

public record MovieSearchResult(
    java.util.List<Movie> movies,
    long total
) {
}
```

Service có thể kết hợp `Flux<Movie>` và `Mono<Long>`:

```java
public Mono<MovieSearchResult> searchMovies(
        Integer year,
        long skip,
        long limit) {

    Mono<java.util.List<Movie>> movies =
        movieRepository.findMovieWindow(year, skip, limit)
            .collectList();

    Mono<Long> total =
        movieRepository.countMoviesReleasedSince(year);

    return Mono.zip(movies, total)
        .map(tuple -> new MovieSearchResult(
            tuple.getT1(),
            tuple.getT2()
        ));
}
```

`collectList()` gom các phần tử của Flux vào một List và chỉ hoàn tất khi Flux kết thúc. Cách này phù hợp khi trang đã được giới hạn kích thước. Không nên gom một Flux không giới hạn vào bộ nhớ chỉ để tiện trả JSON.

`Mono.zip()` kết hợp hai kết quả độc lập. Nếu một publisher không phát ra giá trị (ví dụ một `Mono.empty()`), zip có thể hoàn tất mà không tạo DTO; trong ví dụ, truy vấn đếm nên trả một giá trị số kể cả khi không có node phù hợp.

## 11. Kiểm thử kiểu kết quả reactive

Không nên kiểm thử reactive repository bằng cách gọi `block()` ở mọi test. Project Reactor cung cấp `StepVerifier` để xác minh các tín hiệu mà publisher phát ra.

Ví dụ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import reactor.test.StepVerifier;

@SpringBootTest
class MovieRepositoryTest {

    @Autowired
    MovieRepository movieRepository;

    @Test
    void findsMovieByImdbId() {
        StepVerifier.create(movieRepository.findByImdbId("tt1234567"))
            .assertNext(movie ->
                assertThat(movie.getTitle()).isEqualTo("Example Film")
            )
            .verifyComplete();
    }

    @Test
    void returnsEmptyWhenMovieDoesNotExist() {
        StepVerifier.create(movieRepository.findByImdbId("missing"))
            .verifyComplete();
    }
}
```

`StepVerifier` subscribe vào publisher, kiểm tra các phần tử và tín hiệu kết thúc. Nó cũng có thể xác minh lỗi, chẳng hạn trường hợp `Mono` nhận nhiều kết quả hơn dự kiến.

Trong ví dụ, `@SpringBootTest` khởi tạo application context và inject repository. Test environment cần cấu hình Neo4j test database cùng dữ liệu mẫu trước khi xác minh. Test nên kiểm tra cả trường hợp có dữ liệu, không có dữ liệu và cardinality không đúng với kiểu trả về.

## 12. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Repository kế thừa `Neo4jRepository` nhưng method trả `Mono` | Trộn imperative repository với reactive return type | Dùng `ReactiveNeo4jRepository` |
| Dùng `Optional<T>` cho reactive method | Không biểu diễn được pipeline reactive | Dùng `Mono<T>` |
| Dùng `Mono<T>` cho query có thể trả nhiều node | Phát sinh lỗi nếu có hơn một kết quả | Dùng `Flux<T>` hoặc giới hạn rõ query |
| Dùng `Flux<T>` cho kết quả duy nhất mà không cần nhiều | Hợp đồng method quá rộng, khó phát hiện dữ liệu trùng | Dùng `Mono<T>` khi có ràng buộc tối đa một kết quả |
| Mong đợi `Mono.empty()` là lỗi | Xử lý nhầm trường hợp không tìm thấy | Dùng `switchIfEmpty`, `defaultIfEmpty` hoặc xử lý ở controller |
| Trả `Page<T>` từ reactive repository | Dùng wrapper đồng bộ trong API reactive | Dùng `Flux<T>` và `Mono<Long>` cho dữ liệu và tổng số |
| Gọi `block()` trong service reactive | Chặn thread xử lý reactive | Nối publisher bằng toán tử Reactor |
| Gọi `subscribe()` bên trong service | Tách query khỏi pipeline của bên gọi | Trả publisher cho controller hoặc tầng gọi |
| Gọi `collectList()` trên Flux rất lớn | Tải toàn bộ kết quả vào bộ nhớ | Xử lý từng phần tử hoặc giới hạn kết quả |
| Không có reactive infrastructure | Repository không thể thực thi theo reactive model | Bổ sung Reactor, reactive Spring và driver tương thích |
| Trộn imperative và reactive access trong cùng luồng | Transaction và execution khó dự đoán | Chọn một mô hình nhất quán cho luồng nghiệp vụ |

## 13. Câu hỏi tự kiểm tra

1. `ReactiveNeo4jRepository<T, ID>` kế thừa những interface nào?
2. Tham số `T` và `ID` biểu diễn điều gì?
3. Khi nào nên khai báo `Mono<Movie>`?
4. `Mono.empty()` có ý nghĩa gì khi truy vấn không tìm thấy node?
5. Điều gì xảy ra nếu query method trả về `Mono<T>` nhưng Cypher tìm thấy nhiều node?
6. Khi nào nên dùng `Flux<Movie>`?
7. Các phương thức `count()`, `existsById()` và `deleteById()` có kiểu trả về reactive nào?
8. `ReactiveSortingRepository` cung cấp khả năng gì?
9. Vì sao `Page<T>` không phù hợp làm kiểu kết quả reactive?
10. Làm thế nào để giới hạn kết quả custom Cypher mà vẫn trả về `Flux<T>`?
11. Khi nào publisher thực sự thực thi truy vấn?
12. Vì sao không nên gọi `block()` hoặc `subscribe()` bên trong service?
13. `StepVerifier` hỗ trợ kiểm thử publisher như thế nào?

## Tài liệu tham khảo

- [Spring Data Neo4j – Getting started và reactive repositories](https://docs.spring.io/spring-data/neo4j/reference/getting-started.html)
- [ReactiveNeo4jRepository API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/ReactiveNeo4jRepository.html)
- [EnableReactiveNeo4jRepositories API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/config/EnableReactiveNeo4jRepositories.html)
- [Spring Data Neo4j – Repository query return types](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-return-types-reference.html)
- [Project Reactor – Reference Guide](https://projectreactor.io/docs/core/release/reference/)

## Kết luận

`ReactiveNeo4jRepository<T, ID>` là repository chuyên biệt cho truy cập Neo4j theo mô hình reactive. Nó kế thừa CRUD, sorting và query-by-example reactive, đồng thời cung cấp các thao tác repository với publisher thay vì kết quả đồng bộ.

Chọn `Mono<T>` khi truy vấn có tối đa một kết quả và `Flux<T>` khi có thể có nhiều kết quả. Các thao tác kiểm tra tồn tại, đếm và xóa lần lượt có thể biểu diễn bằng `Mono<Boolean>`, `Mono<Long>` và `Mono<Void>`. Với tập kết quả lớn, dùng Flux và xử lý theo pipeline; khi cần giới hạn, sắp xếp hoặc phân trang, hãy dùng Sort, Top/First hoặc custom Cypher có `SKIP`/`LIMIT` và truy vấn đếm riêng khi cần.

Reactive repository chỉ phát huy tác dụng khi publisher được nối vào pipeline và được subscribe ở tầng thực thi. Hãy trả `Mono` hoặc `Flux` qua các tầng service/controller, tránh chặn luồng bằng `block()`, và kiểm thử hành vi bằng `StepVerifier`.
