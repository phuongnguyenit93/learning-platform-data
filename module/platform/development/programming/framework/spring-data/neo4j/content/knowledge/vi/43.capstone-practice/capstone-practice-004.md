# Triển khai repository CRUD và truy vấn suy diễn

## Mục tiêu capstone

Trong bài thực hành này, bạn sẽ xây dựng một catalog phim bằng Spring Data Neo4j. Sau khi hoàn thành, bạn có thể:

- Khai báo repository cho từng node entity bằng `Neo4jRepository<T, ID>`.
- Thực hiện các thao tác tạo, đọc, cập nhật và xóa qua repository.
- Viết derived query từ tên method để lọc theo property, kết hợp điều kiện, giới hạn và sắp xếp kết quả.
- Tạo truy vấn suy diễn đi qua relationship và relationship properties.
- Phối hợp nhiều repository trong một service với transaction.
- Kiểm thử CRUD và derived query trên Neo4j.
- Nhận biết khi nào tên method đã quá phức tạp và cần chuyển sang `@Query` hoặc `Neo4jClient`.

## 1. Bài toán và mô hình graph

Catalog lưu thông tin phim và người xem. Một người có thể thích nhiều phim; một phim có thể được nhiều người thích. Thời điểm thích phim được lưu trên relationship.

Graph cần xây dựng:

~~~cypher
(:Person {name: 'Mina', email: 'mina@example.test'})
    -[:LIKES {likedAt: datetime('2026-01-10T09:00:00Z')}]->
(:Movie {title: 'The Graph Journey', releaseYear: 2025, genre: 'Adventure'})
~~~

Mô hình Java gồm:

- `Person`: node người xem, có tên và email.
- `Movie`: node phim, có tiêu đề, năm phát hành và thể loại.
- `Like`: relationship properties của `LIKES`, chứa thời điểm người xem thích phim và tham chiếu đến `Person`.

`Movie` là điểm truy cập phù hợp cho truy vấn “những phim được một người tên Mina thích”. Derived query sẽ đi theo đường:

~~~text
Movie
  └── likedBy          (relationship properties: Like)
        └── person     (target node: Person)
              └── name
~~~

Tên method tương ứng là `findByLikedByPersonName(String name)`. Đây là dạng truy vấn suy diễn xuyên qua relationship được Spring Data Neo4j hỗ trợ; tài liệu FAQ của SDN cũng dùng chính ví dụ `MovieRepository.findByLikedByPersonName(String name)`.

## 2. Khai báo node entity và relationship properties

### Person

Dùng UUID do ứng dụng sinh làm ID để các node có khóa định danh ổn định khi trao đổi giữa các thành phần. Trường `@Version` hỗ trợ optimistic locking khi nhiều thao tác cập nhật cùng một entity.

~~~java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.UUIDStringGenerator;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue(UUIDStringGenerator.class)
    private String id;

    @Version
    private Long version;

    private String name;
    private String email;

    protected Person() {
    }

    public Person(String name, String email) {
        this.name = requireText(name, "name");
        this.email = requireText(email, "email");
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value.trim();
    }

    public String getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public void rename(String name) {
        this.name = requireText(name, "name");
    }
}
~~~

### Like

`Like` không phải node entity. Đây là một relationship có property riêng nên được đánh dấu bằng `@RelationshipProperties`. Trường `@RelationshipId` do SDN quản lý để nhận diện relationship hiện hữu khi lưu graph.

~~~java
import java.time.Instant;
import java.util.Objects;

import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class Like {

    @RelationshipId
    private Long relationshipId;

    private Instant likedAt;

    @TargetNode
    private Person person;

    protected Like() {
    }

    public Like(Person person, Instant likedAt) {
        this.person = Objects.requireNonNull(person, "person is required");
        this.likedAt = Objects.requireNonNull(likedAt, "likedAt is required");
    }

    public Person getPerson() {
        return person;
    }

    public Instant getLikedAt() {
        return likedAt;
    }
}
~~~

### Movie

Relationship được khai báo ở phía `Movie` theo hướng incoming. Nghĩa là từ góc nhìn node Movie, relationship `LIKES` đi vào Movie: `(:Person)-[:LIKES]->(:Movie)`.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;
import org.springframework.data.neo4j.core.schema.UUIDStringGenerator;

@Node("Movie")
public class Movie {

    @Id
    @GeneratedValue(UUIDStringGenerator.class)
    private String id;

    @Version
    private Long version;

    private String title;
    private Integer releaseYear;
    private String genre;

    @Relationship(
        type = "LIKES",
        direction = Relationship.Direction.INCOMING
    )
    private List<Like> likedBy = new ArrayList<>();

    protected Movie() {
    }

    public Movie(String title, Integer releaseYear, String genre) {
        this.title = requireText(title, "title");
        this.releaseYear = Objects.requireNonNull(
            releaseYear, "releaseYear is required"
        );
        this.genre = requireText(genre, "genre");
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value.trim();
    }

    public void addLike(Person person, java.time.Instant likedAt) {
        Objects.requireNonNull(person, "person is required");

        if (person.getId() == null) {
            throw new IllegalArgumentException(
                "Save the person before linking it to a movie"
            );
        }

        boolean alreadyLiked = likedBy.stream()
            .anyMatch(like ->
                like.getPerson().getId().equals(person.getId())
            );

        if (alreadyLiked) {
            throw new IllegalStateException(
                "This person has already liked the movie"
            );
        }

        likedBy.add(new Like(person, likedAt));
    }

    public void changeGenre(String genre) {
        this.genre = requireText(genre, "genre");
    }

    public String getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getTitle() {
        return title;
    }

    public Integer getReleaseYear() {
        return releaseYear;
    }

    public String getGenre() {
        return genre;
    }

    public List<Like> getLikedBy() {
        return List.copyOf(likedBy);
    }
}
~~~

Ở ví dụ này, service sẽ tìm và lưu `Person` trước, sau đó thêm `Like` vào `Movie` rồi lưu lại `Movie`. Như vậy, hai endpoint của relationship đều đã có định danh.

## 3. Tạo repository CRUD

Repository là interface; Spring Data Neo4j tạo implementation tại runtime. Tham số generic đầu tiên là node entity, tham số thứ hai là kiểu ID của entity đó.

### PersonRepository

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    Optional<Person> findByEmailIgnoreCase(String email);

    boolean existsByEmailIgnoreCase(String email);

    List<Person> findByNameContainingIgnoreCase(String name);
}
~~~

### MovieRepository

~~~java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface MovieRepository extends Neo4jRepository<Movie, String> {

    List<Movie> findByTitleContainingIgnoreCase(String title);

    List<Movie> findByReleaseYearBetween(
        Integer fromYear,
        Integer toYear
    );

    List<Movie> findByLikedByPersonName(String name);

    long countByGenre(String genre);

    List<Movie> findTop5ByGenreOrderByReleaseYearDesc(String genre);

    Slice<Movie> findByGenre(String genre, Pageable pageable);
}
~~~

Không cần viết class implementation cho những method trên. Spring Data phân tích tên method, kiểm tra property path trong domain model và tạo truy vấn tương ứng.

## 4. Thực hiện CRUD qua repository

`Neo4jRepository` kế thừa các thao tác CRUD của Spring Data. Các method thường dùng:

| Method | Mục đích | Kết quả |
|---|---|---|
| `save(entity)` | Tạo mới hoặc lưu thay đổi của entity | Entity đã lưu |
| `saveAll(entities)` | Lưu nhiều entity cùng loại | Iterable entity |
| `findById(id)` | Tìm theo identity được đánh dấu `@Id` | `Optional<T>` |
| `findAll()` | Lấy tất cả entity thuộc loại repository | Iterable |
| `existsById(id)` | Kiểm tra identity có tồn tại | boolean |
| `count()` | Đếm entity thuộc loại repository | long |
| `delete(entity)` | Xóa entity được chỉ định | void |
| `deleteById(id)` | Xóa theo identity | void |
| `deleteAll()` | Xóa tất cả entity thuộc loại repository | void |

Ví dụ tạo và đọc Person:

~~~java
Person person = personRepository.save(
    new Person("Mina", "mina@example.test")
);

String personId = person.getId();

Person loaded = personRepository.findById(personId)
    .orElseThrow();

boolean exists = personRepository.existsById(personId);
long totalPeople = personRepository.count();
~~~

Hãy dùng entity được trả về từ `save`. SDN có thể gán ID và cập nhật version trong quá trình lưu. Với entity mới, ID có thể chưa tồn tại trước khi gọi `save`.

Ví dụ tạo và cập nhật Movie:

~~~java
Movie movie = movieRepository.save(
    new Movie("The Graph Journey", 2025, "Adventure")
);

movie.changeGenre("Science Fiction");

Movie updated = movieRepository.save(movie);
~~~

`save` được dùng cho cả tạo mới và cập nhật. Cơ chế xác định entity mới hay cũ phụ thuộc ID generation và metadata newness như `@Version`. Không tự gán giá trị cho ID sinh tự động hoặc version.

Ví dụ xóa theo ID:

~~~java
if (movieRepository.existsById(movieId)) {
    movieRepository.deleteById(movieId);
}
~~~

Trong ứng dụng thật, thao tác xóa cần theo chính sách nghiệp vụ. Nếu entity có relationship, hãy xác định trước các liên kết cần giữ, gỡ hoặc xử lý cùng thao tác xóa. Không dùng `deleteAll()` trong luồng nghiệp vụ thông thường; method này phù hợp hơn với môi trường test hoặc thao tác quản trị đã được kiểm soát.

## 5. Hiểu cấu trúc tên derived query

Một derived query thường có hai phần:

~~~text
find...By + điều kiện property
└── subject   └── predicate
~~~

Ví dụ:

`findByTitleContainingIgnoreCase(String title)`

- `find` cho biết đây là truy vấn đọc.
- `By` đánh dấu phần điều kiện.
- `Title` là property của Movie.
- `Containing` yêu cầu tìm chuỗi con.
- `IgnoreCase` yêu cầu so sánh không phân biệt hoa thường cho property phù hợp.

Ví dụ khác:

~~~java
List<Movie> findByGenreAndReleaseYearGreaterThan(
    String genre,
    Integer year
);
~~~

Điều kiện được kết hợp bằng `AND`. Thứ tự tham số phải khớp thứ tự property trong tên method.

Các từ khóa thường dùng:

| Nhóm | Từ khóa | Ý nghĩa |
|---|---|---|
| Kết hợp | `And`, `Or` | Kết hợp điều kiện |
| So sánh | `GreaterThan`, `LessThan`, `Between` | So sánh số, ngày hoặc kiểu tương thích |
| Chuỗi | `Containing`, `StartingWith`, `EndingWith` | Tìm chuỗi con, tiền tố hoặc hậu tố |
| Tập hợp | `In`, `NotIn` | So sánh với tập giá trị |
| Null | `IsNull`, `IsNotNull` | Kiểm tra null |
| Boolean | `True`, `False` | Kiểm tra giá trị boolean |
| Phân biệt hoa thường | `IgnoreCase`, `AllIgnoreCase` | Điều chỉnh so sánh chuỗi |
| Sắp xếp tĩnh | `OrderByPropertyAsc`, `OrderByPropertyDesc` | Sắp xếp theo property |
| Giới hạn | `First`, `Top` | Giới hạn số kết quả |

Không phải mọi từ khóa chung của Spring Data đều có ý nghĩa cho mọi kiểu property hoặc mọi datastore. Hãy kiểm tra tài liệu từ khóa của phiên bản SDN đang sử dụng và kiểu dữ liệu thực tế.

## 6. Truy vấn suy diễn qua relationship

Đây là phần graph-specific quan trọng của capstone.

Method:

~~~java
List<Movie> findByLikedByPersonName(String name);
~~~

được phân tích thành đường property:

~~~text
Movie.likedBy.person.name
~~~

Trong đó:

- `likedBy` là field relationship trên Movie.
- `person` là field `@TargetNode` trong class `Like`.
- `name` là property của Person.

Ứng dụng có thể dùng:

~~~java
List<Movie> moviesLikedByMina =
    movieRepository.findByLikedByPersonName("Mina");
~~~

Bạn không cần viết Cypher thủ công cho điều kiện này. SDN sử dụng metadata mapping để điều hướng qua relationship đã khai báo trong domain model.

Có thể hình dung truy vấn Cypher tương đương về ý tưởng như sau:

~~~cypher
MATCH (person:Person)-[:LIKES]->(movie:Movie)
WHERE person.name = $name
RETURN movie
~~~

Đây là sơ đồ logic giúp hiểu đường truy vấn; Cypher thực tế do SDN sinh ra có thể thêm các phần projection cần thiết để ánh xạ entity và relationship properties.

Nếu một method trả về nhiều root entity có thể khớp nhiều đường relationship, cân nhắc modifier `Distinct` khi nghiệp vụ yêu cầu loại bỏ kết quả trùng:

~~~java
List<Movie> findDistinctByLikedByPersonName(String name);
~~~

Hãy chỉ thêm `Distinct` khi thực sự cần semantics đó và xác nhận truy vấn trên database test.

## 7. Derived query với nhiều điều kiện, giới hạn và sắp xếp

Các method dưới đây minh họa truy vấn theo thuộc tính node:

~~~java
List<Movie> findByTitleContainingIgnoreCase(String title);

List<Movie> findByReleaseYearBetween(
    Integer fromYear,
    Integer toYear
);

long countByGenre(String genre);

List<Movie> findTop5ByGenreOrderByReleaseYearDesc(String genre);
~~~

Cách gọi:

~~~java
List<Movie> scienceFiction =
    movieRepository.findByTitleContainingIgnoreCase("graph");

List<Movie> moviesFromPeriod =
    movieRepository.findByReleaseYearBetween(2020, 2026);

long adventureCount =
    movieRepository.countByGenre("Adventure");

List<Movie> latestFive =
    movieRepository.findTop5ByGenreOrderByReleaseYearDesc("Adventure");
~~~

Tên method nên phản ánh một điều kiện dễ đọc. Nếu tên trở nên quá dài hoặc chứa nhiều nhánh điều kiện, hãy cân nhắc một query được khai báo bằng `@Query` thay vì cố nhồi toàn bộ logic vào tên method.

### Phân trang với Pageable và Slice

`Pageable` cho phép truyền số trang, kích thước trang và sort động:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

var pageable = PageRequest.of(
    0,
    20,
    Sort.by("releaseYear").descending()
);

Slice<Movie> firstSlice =
    movieRepository.findByGenre("Adventure", pageable);
~~~

`Slice` cho biết có trang tiếp theo hay không mà không cần tổng số trang. Nếu nghiệp vụ cần tổng số bản ghi và tổng số trang, có thể trả về `Page<Movie>`:

Thêm method sau vào `MovieRepository` (repository đã import `Page`):

~~~java
Page<Movie> findPageByGenre(String genre, Pageable pageable);
~~~

`Page` thường cần thêm count query để tính tổng kết quả. Với tập dữ liệu lớn, thao tác đếm có thể tốn kém. Nếu giao diện chỉ cần nút “Xem thêm”, `Slice` thường phù hợp hơn.

Offset pagination cũng có thể chậm khi offset tăng rất lớn vì database phải xử lý phần kết quả đứng trước vị trí cần lấy. Với tập dữ liệu lớn, hãy cân nhắc chiến lược scrolling hoặc keyset pagination phù hợp với API và phiên bản Spring Data.

## 8. Tên method đặc biệt và lỗi property path

Một số method kế thừa từ repository là reserved methods. Ví dụ `findById(id)` luôn tìm theo property được đánh dấu `@Id`, bất kể field định danh thực tế có tên là gì.

Giả sử entity có:

~~~java
@Id
private String movieKey;

private String id;
~~~

Method:

~~~java
Optional<Movie> findById(String id);
~~~

vẫn trỏ tới `movieKey` vì đây là method reserved của repository. Nếu muốn tìm property thường tên `id`, hãy dùng một descriptive token để tránh xung đột:

~~~java
Optional<Movie> findMovieById(String id);
~~~

### Property path bị nhập nhằng

Giả sử class có cả property `addressZip` và object `address.zipCode`. Một method tên `findByAddressZipCode` có thể bị parser hiểu nhầm theo property trực tiếp.

Có thể dùng dấu gạch dưới để chỉ rõ ranh giới path:

~~~java
List<Person> findByAddress_ZipCode(String zipCode);
~~~

Dấu gạch dưới được dùng làm ký hiệu phân tách path. Vì vậy, nên dùng quy ước đặt tên Java camelCase cho property và dành dấu gạch dưới cho derived query path.

### Sai tên property

Nếu entity không có property mà method nhắc tới, repository có thể lỗi khi Spring khởi tạo application context. Hãy đối chiếu từng đoạn trong tên method với field của entity, relationship properties class và target node.

## 9. Khi nào nên chuyển sang @Query hoặc Neo4jClient?

Derived query phù hợp với điều kiện trên property và đường relationship được mô hình hóa. Nó không phải công cụ phù hợp cho mọi truy vấn graph.

| Nhu cầu | Cách tiếp cận |
|---|---|
| Lọc theo một vài property | Derived query |
| Kết hợp điều kiện và sắp xếp đơn giản | Derived query |
| Truy vấn qua relationship đã map | Derived query với property path |
| Pattern graph đặc biệt hoặc variable-length path | `@Query` hoặc `Neo4jClient` |
| Aggregation, projection hoặc nhiều bước Cypher | `@Query` hoặc `Neo4jClient` |
| Procedure, dynamic query structure hoặc mapping record tùy chỉnh | `Neo4jClient` |
| Query khó đọc nếu biểu diễn bằng tên method | `@Query` |

Ví dụ query tùy chỉnh có thể viết trực tiếp trong repository:

Thêm method sau vào §MovieRepository§ và import §Query§ cùng §Param§ từ Spring Data Neo4j/Spring Data Commons:

~~~java
@Query("""
    MATCH (person:Person)-[:LIKES]->(movie:Movie)
    WHERE person.email = $email
RETURN DISTINCT movie
    """)
List<Movie> findMoviesLikedByEmail(@Param("email") String email);
~~~

Khi dùng `@Query`, hãy bind dữ liệu qua named parameters. Không nối trực tiếp input người dùng vào chuỗi Cypher.

## 10. Tổ chức CRUD và derived query trong service

Repository nên tập trung vào persistence. Service điều phối nghiệp vụ, kiểm tra điều kiện và xác định transaction boundary.

Ví dụ service:

~~~java
import java.time.Clock;
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MovieCatalogService {

    private final MovieRepository movies;
    private final PersonRepository people;
    private final Clock clock;

    public MovieCatalogService(
            MovieRepository movies,
            PersonRepository people,
            Clock clock
    ) {
        this.movies = movies;
        this.people = people;
        this.clock = clock;
    }

    @Transactional
    public Movie createMovie(
            String title,
            Integer releaseYear,
            String genre
    ) {
        return movies.save(
            new Movie(title, releaseYear, genre)
        );
    }

    @Transactional(readOnly = true)
    public Movie getMovie(String movieId) {
        return movies.findById(movieId)
            .orElseThrow(() ->
                new MovieNotFoundException(movieId)
            );
    }

    @Transactional
    public Movie changeGenre(String movieId, String genre) {
        Movie movie = movies.findById(movieId)
            .orElseThrow(() ->
                new MovieNotFoundException(movieId)
            );

        movie.changeGenre(genre);
        return movies.save(movie);
    }

    @Transactional
    public Movie likeMovie(String movieId, String personId) {
        Movie movie = movies.findById(movieId)
            .orElseThrow(() ->
                new MovieNotFoundException(movieId)
            );

        Person person = people.findById(personId)
            .orElseThrow(() ->
                new PersonNotFoundException(personId)
            );

        movie.addLike(person, clock.instant());

        return movies.save(movie);
    }

    @Transactional(readOnly = true)
    public List<Movie> findMoviesLikedBy(String personName) {
        return movies.findByLikedByPersonName(personName);
    }

    @Transactional
    public void deleteMovie(String movieId) {
        Movie movie = movies.findById(movieId)
            .orElseThrow(() ->
                new MovieNotFoundException(movieId)
            );

        movies.delete(movie);
    }
}
~~~

Exception nghiệp vụ:

~~~java
public class MovieNotFoundException extends RuntimeException {

    public MovieNotFoundException(String movieId) {
        super("Movie not found: " + movieId);
    }
}
~~~

~~~java
public class PersonNotFoundException extends RuntimeException {

    public PersonNotFoundException(String personId) {
        super("Person not found: " + personId);
    }
}
~~~

Cấu hình bean Clock trong ứng dụng:

~~~java
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Các điểm quan trọng:

- Service đọc Movie và Person trong cùng một thao tác nghiệp vụ.
- Nếu một trong hai node không tồn tại, service dừng với exception nghiệp vụ.
- Thay đổi relationship được thực hiện trên aggregate Movie rồi lưu lại Movie.
- `@Transactional` giúp nhiều thao tác repository trong một service method tham gia cùng transaction.
- `readOnly = true` thể hiện rõ mục đích của luồng đọc.
- Dùng Clock giúp test thời điểm `likedAt` ổn định.

Nếu có nhiều repository calls cần nhất quán, hãy đặt transaction ở service method điều phối. Không dựa vào việc từng method repository riêng lẻ sẽ tự tạo thành một transaction chung.

## 11. Lưu ý khi lưu aggregate có relationship

SDN lưu entity cùng các entity và relationship được khai báo trong object graph mà nó quản lý. Vì vậy, cần xác định rõ root entity nào chịu trách nhiệm cho từng quan hệ.

Trong capstone:

- `Movie` sở hữu field `likedBy`.
- `Like` chứa metadata của relationship.
- `Person` là target node của relationship.
- Thao tác thêm Like được thực hiện thông qua Movie rồi gọi `movieRepository.save(movie)`.

Không nên tải một phần graph, chỉnh sửa collection relationship không đầy đủ rồi lưu lại nếu bạn không hiểu rõ tác động lên những relationship được map. Một object graph không đầy đủ có thể dẫn tới các thay đổi relationship ngoài ý muốn. Hãy xác định phạm vi aggregate, kiểm tra dữ liệu sau save và viết integration test cho trường hợp thêm, cập nhật, gỡ relationship.

Quy tắc chống thích trùng trong method `Movie.addLike` là kiểm tra nghiệp vụ ở bộ nhớ. Nếu có nhiều request đồng thời, hai transaction vẫn có thể cùng vượt qua kiểm tra trước khi một transaction lưu. Nếu quan hệ phải duy nhất tuyệt đối, hãy thiết kế thao tác idempotent ở database bằng Cypher `MERGE` hoặc mô hình hóa liên kết thành node có business key và uniqueness constraint.

## 12. Kiểm thử repository với Neo4j

Unit test có thể kiểm tra logic của method `addLike` hoặc parser enum. Nhưng để xác nhận SDN tạo đúng node, relationship type, direction và property, cần integration test với Neo4j.

Ví dụ test repository:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;

@DataNeo4jTest
class MovieRepositoryIntegrationTest {

    @Autowired
    private PersonRepository people;

    @Autowired
    private MovieRepository movies;

    @Test
    void findsMoviesThroughLikedByRelationship() {
        Person person = people.save(
            new Person("Mina", "mina@example.test")
        );

        Movie movie = new Movie(
            "The Graph Journey",
            2025,
            "Adventure"
        );

        movie.addLike(
            person,
            Instant.parse("2026-01-10T09:00:00Z")
        );

        movies.save(movie);

        var result = movies.findByLikedByPersonName("Mina");

        assertThat(result)
            .extracting(Movie::getTitle)
            .contains("The Graph Journey");
    }

    @Test
    void supportsCrudLifecycle() {
        Movie saved = movies.save(
            new Movie("Temporary Film", 2024, "Drama")
        );

        assertThat(saved.getId()).isNotBlank();
        assertThat(movies.existsById(saved.getId())).isTrue();

        Movie loaded = movies.findById(saved.getId()).orElseThrow();
        assertThat(loaded.getTitle()).isEqualTo("Temporary Film");

        movies.deleteById(saved.getId());

        assertThat(movies.existsById(saved.getId())).isFalse();
    }
}
~~~

`@DataNeo4jTest` cấu hình phần test slice của Spring Data Neo4j. Nó không tự tạo một Neo4j server cho bạn. Hãy cung cấp kết nối test phù hợp, chẳng hạn Neo4j Test Harness hoặc Testcontainers với phiên bản Neo4j tương thích.

Bộ integration test nên kiểm tra:

1. Lưu Person mới và xác nhận ID được sinh.
2. Lưu Movie mới và đọc lại bằng ID.
3. Cập nhật property Movie rồi đọc lại để xác nhận thay đổi.
4. Tạo relationship LIKES cùng property likedAt.
5. Truy vấn Movie qua đường likedBy → person → name.
6. Kiểm tra derived query có lọc đúng genre, năm phát hành và title.
7. Xác nhận xóa Movie theo chính sách relationship của ứng dụng.
8. Kiểm tra hai lần lưu cập nhật có xử lý version theo mong đợi.

Test nên dùng dữ liệu riêng và database được làm sạch giữa các test để tránh kết quả của lần chạy trước ảnh hưởng lần chạy sau.

## 13. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Application context không khởi động | Tên property trong derived query không tồn tại | Đối chiếu method name với domain model |
| `findById` trả kết quả bất ngờ | Method reserved luôn nhắm tới field `@Id` | Dùng tên descriptive như `findMovieById` nếu cần tìm property thường tên id |
| Derived query qua relationship không có kết quả | Sai tên path, relationship type hoặc direction | Kiểm tra field relationship và graph thực tế |
| Movie bị trả nhiều lần | Nhiều đường relationship cùng thỏa điều kiện | Cân nhắc `Distinct` và kiểm thử semantics |
| Lưu Movie nhưng không có LIKES | Person chưa được lưu hoặc relationship không được thêm vào aggregate root | Lưu Person, thêm Like vào Movie rồi save Movie |
| Property likedAt bị mất sau update | Relationship identity không được map đúng hoặc object graph thiếu metadata | Kiểm tra `@RelationshipId` và `@TargetNode` |
| Thay đổi property không được lưu | Đã sửa object nhưng chưa gọi save trong luồng ghi | Gọi repository.save với aggregate root |
| Lỗi optimistic locking | Version cũ do một transaction khác đã cập nhật entity | Đọc lại entity mới nhất và xử lý xung đột |
| Trang dữ liệu tải chậm | Dùng Page khi không cần tổng số bản ghi hoặc offset quá lớn | Cân nhắc Slice/scrolling và query plan |
| Derived query quá dài, khó đọc | Method biểu diễn quá nhiều điều kiện hoặc graph pattern phức tạp | Chuyển sang @Query hoặc Neo4jClient |

## 14. Bài tập hoàn thiện capstone

Hoàn thiện catalog theo các yêu cầu sau:

1. Tạo Person và Movie với UUID generated ID.
2. Tạo relationship properties Like có likedAt và target node Person.
3. Khai báo hai repository kế thừa Neo4jRepository.
4. Thêm CRUD cho Person và Movie.
5. Thêm derived query tìm Person theo email không phân biệt hoa thường.
6. Thêm derived query tìm Movie theo title chứa từ khóa.
7. Thêm derived query tìm Movie trong khoảng năm phát hành.
8. Thêm derived query tìm Movie qua relationship likedBy → person → name.
9. Thêm count query theo genre.
10. Thêm top 5 query theo genre, sắp xếp năm phát hành giảm dần.
11. Thêm query phân trang với Slice và Pageable.
12. Viết service tạo Movie, đổi genre, thích Movie và xóa Movie.
13. Đặt transaction cho các use case cần nhiều thao tác repository.
14. Viết integration test cho CRUD và derived query qua relationship.
15. Kiểm tra graph bằng Cypher để xác nhận node, relationship type, direction và likedAt.
16. Thử cập nhật Movie đồng thời từ hai transaction để quan sát optimistic locking.

Cypher kiểm tra graph sau khi chạy:

~~~cypher
MATCH (person:Person)-[like:LIKES]->(movie:Movie)
RETURN person.name AS person,
       movie.title AS movie,
       like.likedAt AS likedAt
ORDER BY likedAt DESC
~~~

Câu hỏi tự kiểm tra:

- Repository generic type gồm những thông tin nào?
- Khác biệt giữa `findById` và derived query `findBy...` là gì?
- `findByLikedByPersonName` đi qua những property nào?
- Vì sao relationship properties class cần `@RelationshipId` và `@TargetNode`?
- Khi nào nên trả về `Slice` thay cho `Page`?
- Vì sao `save` trả về entity cần được sử dụng?
- Khi nào cần đặt `@Transactional` ở service?
- Vì sao kiểm tra duplicate relationship trong Java chưa đủ cho request đồng thời?
- Khi nào nên chuyển từ derived query sang `@Query` hoặc `Neo4jClient`?
- Integration test cần xác minh điều gì mà unit test không thể xác minh?

## Kết luận

Spring Data Neo4j cung cấp repository CRUD và cơ chế tạo truy vấn từ tên method. Với một mô hình graph được khai báo rõ, repository có thể tìm node qua property trực tiếp hoặc qua nhiều bước relationship. Trong capstone này, `MovieRepository.findByLikedByPersonName` truy vấn Movie thông qua relationship properties `Like` và target node `Person` mà không cần viết Cypher thủ công.

Hãy để repository phụ trách thao tác dữ liệu, service điều phối nghiệp vụ và transaction, còn domain model thể hiện relationship cùng quy tắc của nó. Kiểm thử CRUD, derived query và mapping relationship trên Neo4j để xác nhận toàn bộ luồng lưu và đọc hoạt động đúng.

## Tài liệu tham khảo

- [Spring Data Neo4j: FAQ — derived queries across relationships and repository usage](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j: Defining Query Methods](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-methods-details.html)
- [Spring Data Neo4j: Repository query keywords](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-keywords-reference.html)
- [Spring Data Neo4j: Metadata-based Mapping — relationships and relationship properties](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
- [Spring Data Neo4j: Neo4jRepository API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/Neo4jRepository.html)
- [Spring Boot: Testing Spring Boot applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
