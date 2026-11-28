# Thực hiện vòng CRUD và xác minh dữ liệu trong công cụ truy vấn Neo4j

Sau khi ứng dụng Spring Boot kết nối được tới Neo4j, bước tiếp theo là thực hiện vòng CRUD: tạo dữ liệu (Create), đọc dữ liệu (Read), cập nhật dữ liệu (Update) và xóa dữ liệu (Delete). Spring Data Neo4j cung cấp repository để thao tác với node entity, ánh xạ relationship và chạy Cypher. Neo4j Browser hoặc Cypher Shell giúp kiểm tra trực tiếp trạng thái đồ thị, nhờ đó ta có thể đối chiếu kết quả mà ứng dụng trả về với dữ liệu thực sự được lưu trong database.

Bài học dùng ví dụ danh mục phim. Mỗi phim có mã nghiệp vụ, tiêu đề và năm phát hành. Một phim có thể liên kết với nhiều diễn viên qua relationship `ACTED_IN`; relationship lưu tên nhân vật. Qua ví dụ này, ta sẽ thực hiện CRUD cho node và relationship, sau đó dùng Cypher để xác minh từng thay đổi.

## 1. Luồng CRUD với Spring Data Neo4j

Với Spring Data Neo4j (SDN), một luồng CRUD thường đi qua các thành phần:

1. Entity Java mô tả node và relationship cần ánh xạ.
2. Repository kế thừa `Neo4jRepository` cung cấp thao tác lưu, tìm kiếm và xóa.
3. Service kết hợp nhiều thao tác trong một transaction nếu một nghiệp vụ cần tính nguyên tử.
4. Neo4j Java Driver gửi câu lệnh tới database và SDN ánh xạ kết quả thành entity hoặc projection.
5. Neo4j Browser hoặc Cypher Shell truy vấn trực tiếp để xác minh node, relationship và thuộc tính.

CRUD không chỉ áp dụng cho node. Trong mô hình đồ thị, relationship cũng có thể được tạo, đọc, thay đổi thuộc tính và xóa. Khi relationship mang dữ liệu nghiệp vụ, chẳng hạn vai diễn của diễn viên trong một phim, ta cần kiểm tra cả hai đầu node lẫn thuộc tính trên relationship.

## 2. Khai báo entity và repository

Ví dụ dùng `Movie` và `Person` làm node. SDN cấp giá trị cho trường `id` bằng `@GeneratedValue`; đây là định danh phục vụ persistence. Ứng dụng còn có `code` là mã nghiệp vụ ổn định để tìm kiếm và trao đổi với hệ thống khác. Constraint duy nhất trong Neo4j bảo vệ `code` khỏi bị trùng.

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

import java.util.HashSet;
import java.util.Set;

@Node("Movie")
public class Movie {
    @Id
    @GeneratedValue
    private Long id;

    private String code;
    private String title;
    private Integer releaseYear;

    @Relationship(
        type = "ACTED_IN",
        direction = Relationship.Direction.INCOMING
    )
    private Set<ActingCredit> cast = new HashSet<>();

    protected Movie() {
    }

    public Movie(String code, String title, Integer releaseYear) {
        this.code = code;
        this.title = title;
        this.releaseYear = releaseYear;
    }

    public Long getId() { return id; }
    public String getCode() { return code; }
    public String getTitle() { return title; }
    public Integer getReleaseYear() { return releaseYear; }
    public Set<ActingCredit> getCast() { return cast; }

    public void setTitle(String title) { this.title = title; }
    public void setReleaseYear(Integer releaseYear) {
        this.releaseYear = releaseYear;
    }
}

@Node("Person")
public class Person {
    @Id
    @GeneratedValue
    private Long id;

    private String code;
    private String name;

    protected Person() {
    }

    public Person(String code, String name) {
        this.code = code;
        this.name = name;
    }

    public Long getId() { return id; }
    public String getCode() { return code; }
    public String getName() { return name; }
}

@RelationshipProperties
public class ActingCredit {
    @RelationshipId
    private Long id;

    private String character;

    @TargetNode
    private Person actor;

    protected ActingCredit() {
    }

    public ActingCredit(Person actor, String character) {
        this.actor = actor;
        this.character = character;
    }

    public Person getActor() { return actor; }
    public String getCharacter() { return character; }
    public void setCharacter(String character) {
        this.character = character;
    }
}
```

Đây là các lớp minh họa cho cùng một mô hình; trong dự án Java, đặt mỗi lớp top-level (`Movie`, `Person`, `ActingCredit`) trong file riêng tương ứng. Các getter, setter và constructor phụ trợ được rút gọn để tập trung vào phần ánh xạ.

Trong ví dụ, relationship có hướng từ `Person` tới `Movie`, vì vậy collection `cast` khai báo trên `Movie` dùng `INCOMING`. `ActingCredit` lưu thuộc tính `character` của lần diễn xuất và `@TargetNode` trỏ tới node diễn viên. `@RelationshipId` là định danh nội bộ của relationship được SDN ánh xạ; không dùng nó làm mã nghiệp vụ.

Các repository có kiểu ID khớp với trường `@Id`:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import java.util.List;
import java.util.Optional;

public interface MovieRepository
        extends Neo4jRepository<Movie, Long> {
    Optional<Movie> findByCode(String code);
    List<Movie> findByReleaseYearGreaterThanEqual(Integer year);
}

public interface PersonRepository
        extends Neo4jRepository<Person, Long> {
    Optional<Person> findByCode(String code);
}
```

`Neo4jRepository<Movie, Long>` cung cấp sẵn các phương thức như `save`, `findById`, `findAll`, `existsById`, `count`, `delete` và `deleteById`. Các phương thức `findByCode` và `findByReleaseYearGreaterThanEqual` minh họa query derivation: SDN tạo truy vấn dựa trên tên phương thức và thuộc tính entity.

Tạo constraint cho mã nghiệp vụ trước khi nạp dữ liệu:

```cypher
CREATE CONSTRAINT movie_code_unique IF NOT EXISTS
FOR (m:Movie)
REQUIRE m.code IS UNIQUE;

CREATE CONSTRAINT person_code_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.code IS UNIQUE;
```

`id` được SDN sinh tự động để quản lý entity; `code` là thuộc tính do ứng dụng cấp và có ý nghĩa trong nghiệp vụ. Không nên dùng ID nội bộ của Neo4j như một mã công khai lâu dài trong API hoặc hệ thống bên ngoài.

## 3. Create — tạo node mới

Tạo một phim bằng cách khởi tạo entity rồi gọi `save`:

```java
Movie movie = new Movie("MOV-001", "The Matrix", 1999);
Movie saved = movieRepository.save(movie);

System.out.println(saved.getId());
System.out.println(saved.getCode());
```

Vì entity mới chưa có giá trị `id` được sinh, SDN tạo node `Movie` và trả về entity có định danh đã được gán. Hãy dùng đối tượng được trả về để đọc ID hoặc các giá trị được cập nhật trong quá trình lưu.

Tạo một diễn viên:

```java
Person actor = new Person("PER-001", "Keanu Reeves");
Person savedActor = personRepository.save(actor);
```

Nếu request tạo phim có thể được gửi lặp, constraint trên `code` sẽ ngăn hai node `Movie` có cùng mã. Ứng dụng cần xử lý lỗi vi phạm constraint theo quy tắc nghiệp vụ, ví dụ trả về lỗi trùng mã hoặc đọc lại bản ghi đã tồn tại. Không nên chỉ kiểm tra `findByCode` rồi mới `save` như một cơ chế chống trùng tuyệt đối, vì hai request đồng thời vẫn có thể cùng vượt qua bước kiểm tra.

Có thể đóng gói thao tác tạo trong service:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MovieService {
    private final MovieRepository movieRepository;

    public MovieService(MovieRepository movieRepository) {
        this.movieRepository = movieRepository;
    }

    @Transactional
    public Movie createMovie(String code, String title, int releaseYear) {
        Movie movie = new Movie(code, title, releaseYear);
        return movieRepository.save(movie);
    }
}
```

Một lời gọi `save` thường đã có transaction do repository quản lý. Đặt `@Transactional` ở service đặc biệt hữu ích khi một nghiệp vụ gồm nhiều lần lưu node và relationship cần commit hoặc rollback cùng nhau.

## 4. Read — đọc và tìm kiếm node

Đọc theo ID:

```java
Movie movie = movieRepository.findById(movieId)
    .orElseThrow(() -> new IllegalArgumentException("Movie not found"));
```

Đọc theo mã nghiệp vụ:

```java
Movie movie = movieRepository.findByCode("MOV-001")
    .orElseThrow(() -> new IllegalArgumentException("Movie not found"));
```

Đọc danh sách phim từ một năm nhất định:

```java
List<Movie> recentMovies =
    movieRepository.findByReleaseYearGreaterThanEqual(2020);
```

Các phương thức trên trả về entity đã được SDN ánh xạ. Nếu màn hình chỉ cần một số thuộc tính, hãy cân nhắc projection hoặc một truy vấn Cypher tường minh để giới hạn dữ liệu được trả về. Khi đọc quan hệ, kết quả phụ thuộc vào cách truy vấn và độ sâu ánh xạ được cấu hình; nếu cần một tập relationship cụ thể, nên viết query thể hiện rõ mẫu đồ thị.

Ví dụ projection đọc dàn diễn viên của phim:

```java
public interface CastMemberView {
    String getActor();
    String getCharacter();
}
```

Bổ sung phương thức truy vấn sau vào `MovieRepository` đã khai báo ở trên:

```java
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
    MATCH (m:Movie {code: $code})<-[r:ACTED_IN]-(p:Person)
    RETURN p.name AS actor,
           r.character AS character
    ORDER BY actor
    """)
List<CastMemberView> findCastByCode(@Param("code") String code);
```

Các bí danh trong `RETURN` phải khớp với tên getter của projection. Query này chỉ trả về tên diễn viên và tên nhân vật thay vì toàn bộ node và relationship.

## 5. Update — cập nhật thuộc tính node

Đối với cập nhật thông thường, đọc entity hiện tại, thay đổi thuộc tính rồi gọi `save`:

```java
Movie movie = movieRepository.findByCode("MOV-001")
    .orElseThrow(() -> new IllegalArgumentException("Movie not found"));

movie.setTitle("The Matrix — Remastered");
movie.setReleaseYear(1999);

Movie updated = movieRepository.save(movie);
```

Vì entity đã được đọc từ database và có ID, SDN nhận diện node cần cập nhật. Chỉ sửa những thuộc tính nghiệp vụ có chủ đích; tránh tạo một entity mới với ID cũ rồi vô tình ghi đè các thuộc tính hoặc relationship chưa tải.

Khi cập nhật nhiều dữ liệu liên quan, dùng một transaction ở service:

```java
@Transactional
public Movie renameMovie(String code, String newTitle) {
    Movie movie = movieRepository.findByCode(code)
        .orElseThrow(() -> new IllegalArgumentException("Movie not found"));
    movie.setTitle(newTitle);
    return movieRepository.save(movie);
}
```

Nếu nhiều request có thể cập nhật cùng một node, cân nhắc optimistic locking bằng thuộc tính `@Version` để phát hiện xung đột. Khi xảy ra xung đột, ứng dụng cần đọc lại dữ liệu và quyết định hợp nhất hoặc trả lỗi; không tự động ghi đè mà không có quy tắc.

## 6. CRUD cho relationship

Node `Person` và `Movie` đã tồn tại. Để tạo relationship `ACTED_IN`, lấy hai entity rồi thêm `ActingCredit` vào collection của `Movie`:

```java
Movie movie = movieRepository.findByCode("MOV-001")
    .orElseThrow(() -> new IllegalArgumentException("Movie not found"));
Person actor = personRepository.findByCode("PER-001")
    .orElseThrow(() -> new IllegalArgumentException("Person not found"));

movie.getCast().add(new ActingCredit(actor, "Neo"));
movieRepository.save(movie);
```

Vì `cast` là relationship được ánh xạ trên entity `Movie`, lưu aggregate sẽ lưu thay đổi relationship theo mapping đó. Với một nghiệp vụ gồm tìm hai node và nối chúng, đặt thao tác trong cùng một service transaction để tránh trạng thái dở dang.

Đọc relationship bằng query Cypher hoặc phương thức projection `findCastByCode` đã trình bày ở phần Read. Để kiểm tra trực tiếp trong Neo4j Browser:

```cypher
MATCH (p:Person)-[r:ACTED_IN]->(m:Movie)
WHERE m.code = 'MOV-001'
RETURN p.code AS personCode,
       p.name AS actor,
       r.character AS character,
       m.code AS movieCode,
       m.title AS movie
ORDER BY actor;
```

Cập nhật thuộc tính relationship bằng cách sửa đối tượng `ActingCredit` đã tải rồi lưu lại aggregate:

```java
ActingCredit credit = movie.getCast().stream()
    .filter(item -> item.getActor().getCode().equals("PER-001"))
    .findFirst()
    .orElseThrow(() -> new IllegalArgumentException("Casting not found"));

credit.setCharacter("Thomas Anderson");
movieRepository.save(movie);
```

Ví dụ giả định mỗi cặp người–phim chỉ có một lượt `ACTED_IN` trong collection. Nếu nghiệp vụ cho phép nhiều lượt hoặc nhiều vai diễn giữa cùng hai node, cần có khóa nghiệp vụ riêng cho lượt tham gia để chọn đúng relationship cần sửa.

Xóa relationship bằng cách loại lượt casting khỏi collection được quản lý rồi lưu aggregate:

```java
movie.getCast().removeIf(
    item -> item.getActor().getCode().equals("PER-001")
);
movieRepository.save(movie);
```

Thao tác này chỉ xóa relationship khỏi đồ thị; node `Person` vẫn tồn tại và có thể tiếp tục tham gia các phim khác. Nếu relationship không được ánh xạ trong aggregate hoặc cần cập nhật một lượng lớn quan hệ, dùng Cypher chuyên biệt để kiểm soát chính xác phạm vi thay đổi.

## 7. Delete — xóa node và hiểu tác động lên relationship

Xóa một phim theo ID:

```java
movieRepository.deleteById(movieId);
```

Hoặc xóa entity đã tải:

```java
Movie movie = movieRepository.findByCode("MOV-001")
    .orElseThrow(() -> new IllegalArgumentException("Movie not found"));
movieRepository.delete(movie);
```

Trong đồ thị, một node có thể đang nối với nhiều node khác. Neo4j không cho phép `DELETE` một node vẫn còn relationship gắn vào nó. Lệnh Cypher `DETACH DELETE` xóa node cùng tất cả relationship gắn trực tiếp vào node đó; các node ở đầu kia vẫn tồn tại. Với ví dụ phim, xóa `Movie` không có nghĩa xóa các `Person` từng tham gia phim.

Có thể kiểm tra tác động bằng Cypher trong môi trường thử nghiệm:

```cypher
MATCH (m:Movie {code: 'MOV-001'})
DETACH DELETE m;
```

`DETACH DELETE` là thao tác phá hủy dữ liệu. Trước khi dùng trong nghiệp vụ, xác định rõ relationship nào sẽ bị xóa, có cần lưu lịch sử hoặc kiểm tra tham chiếu hay không. Nếu cần bảo toàn lịch sử, có thể chuyển trạng thái phim sang `ARCHIVED` thay vì xóa node. Khi xóa qua repository, hãy hiểu mapping và hành vi xóa của phiên bản SDN đang dùng; nếu cần bảo đảm quy tắc xóa cụ thể, thể hiện rõ bằng query/service và kiểm thử trên dữ liệu mẫu.

Sau khi xóa, xác minh:

```cypher
MATCH (m:Movie {code: 'MOV-001'})
RETURN count(m) AS remainingMovies;
```

Kết quả `remainingMovies = 0` cho biết không còn node phim có mã đó. Nếu cần kiểm tra diễn viên vẫn tồn tại:

```cypher
MATCH (p:Person {code: 'PER-001'})
RETURN p.code, p.name;
```

## 8. Xác minh dữ liệu trong Neo4j Browser

Neo4j Browser là công cụ chạy Cypher và hiển thị kết quả dạng bảng hoặc đồ thị. Trong môi trường phát triển cục bộ, mở địa chỉ HTTP đã cấu hình cho Neo4j Browser, đăng nhập đúng database rồi chạy các truy vấn xác minh. Browser thường dùng cổng HTTP `7474`; ứng dụng Spring Data Neo4j vẫn kết nối qua Bolt, thường là `7687`.

**Kiểm tra node Movie:**

```cypher
MATCH (m:Movie)
RETURN m.code AS code,
       m.title AS title,
       m.releaseYear AS releaseYear
ORDER BY code;
```

**Kiểm tra node Person:**

```cypher
MATCH (p:Person)
RETURN p.code AS code, p.name AS name
ORDER BY code;
```

**Kiểm tra relationship và thuộc tính:**

```cypher
MATCH (p:Person)-[r:ACTED_IN]->(m:Movie)
RETURN p, r, m;
```

Truy vấn cuối trả về cả hai node và relationship, nên Browser có thể hiển thị trực quan đồ thị. Có thể chuyển sang chế độ Table để xem từng thuộc tính và so sánh với kết quả mà service trả về.

**Đếm số node và relationship:**

```cypher
MATCH (m:Movie)
RETURN count(m) AS movieCount;

MATCH ()-[r:ACTED_IN]->()
RETURN count(r) AS actingCreditCount;
```

Khi chạy truy vấn kiểm tra sau mỗi bước CRUD, nên lọc theo `code` thay vì chỉ `MATCH` toàn bộ dữ liệu. Điều này giúp tránh nhầm lẫn khi database có dữ liệu từ các lần chạy trước.

## 9. Xác minh bằng Cypher Shell

Cypher Shell là công cụ dòng lệnh để gửi Cypher trực tiếp tới endpoint Bolt. Ví dụ kết nối database cục bộ:

```bash
cypher-shell -a bolt://localhost:7687 -u neo4j
```

Nhập mật khẩu khi được hỏi, sau đó chạy truy vấn:

```cypher
MATCH (m:Movie {code: 'MOV-001'})
RETURN m.code, m.title, m.releaseYear;
```

Cypher Shell hữu ích trong môi trường không có giao diện đồ họa hoặc khi muốn lưu một tập truy vấn xác minh vào quy trình triển khai. Không đưa mật khẩu thật vào tham số dòng lệnh hoặc script được commit; ưu tiên cơ chế nhập tương tác hoặc secret của môi trường chạy.

## 10. Quy trình kiểm thử trọn vòng CRUD

Một kịch bản kiểm thử thủ công có thể thực hiện theo thứ tự sau:

1. **Chuẩn bị:** tạo unique constraint cho `Movie.code` và `Person.code`; xác nhận ứng dụng và Browser trỏ tới cùng database.
2. **Create:** gọi service tạo `Movie(code = "MOV-001", title = "The Matrix", releaseYear = 1999)` và lưu `Person(code = "PER-001", name = "Keanu Reeves")`.
3. **Verify create:** chạy `MATCH` theo từng `code` trong Browser và xác nhận mỗi mã chỉ có một node.
4. **Read:** gọi `findByCode("MOV-001")`, kiểm tra tiêu đề và năm phát hành; so sánh với kết quả Cypher.
5. **Create relationship:** thêm `ActingCredit` với nhân vật `Neo`, lưu `Movie`, rồi truy vấn `(Person)-[:ACTED_IN]->(Movie)` để xác nhận.
6. **Update:** đổi tiêu đề phim hoặc tên nhân vật, lưu lại và chạy query xác minh để thấy giá trị mới.
7. **Delete relationship:** xóa lượt casting khỏi collection, lưu aggregate và xác nhận relationship không còn trong khi hai node vẫn tồn tại.
8. **Delete node:** xóa phim thử nghiệm, sau đó kiểm tra số node phim còn lại và xác nhận node diễn viên vẫn tồn tại.

Nếu một bước thất bại, ghi nhận thao tác nào đã chạy và trạng thái hiện tại trong database trước khi chạy lại. `save` và `MERGE` có thể được thiết kế để lặp an toàn theo khóa nghiệp vụ, nhưng một lệnh tạo mới không tự động trở thành idempotent nếu mỗi lần chạy sinh một mã khác.

## 11. Các lỗi thường gặp khi thực hiện CRUD

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra hoặc xử lý |
|---|---|---|
| `findByCode` không trả kết quả | Sai mã, sai database hoặc node chưa commit | Kiểm tra `spring.data.neo4j.database`, `code` và query trong Browser |
| Tạo node trùng | Thiếu unique constraint hoặc mỗi lần tạo dùng một code mới | Tạo constraint và dùng mã nghiệp vụ ổn định |
| `save` tạo node mới ngoài dự kiến | Entity mới được tạo lại hoặc ID không được giữ đúng | Đọc entity hiện tại rồi cập nhật; kiểm tra trường `@Id` |
| Không thấy relationship sau khi lưu | Hướng relationship hoặc mapping collection không đúng, target node chưa được quản lý phù hợp | Kiểm tra `@Relationship`, `direction`, `@TargetNode` và Cypher trực tiếp |
| Projection trả về null | Bí danh trong `RETURN` không khớp getter hoặc property không tồn tại | Đối chiếu tên cột trả về với projection và kiểm tra dữ liệu |
| Xóa node báo còn relationship | Node vẫn có cạnh gắn vào | Xác định quan hệ cần giữ/xóa; dùng quy tắc xóa rõ ràng, cân nhắc `DETACH DELETE` |
| Browser không thấy dữ liệu vừa lưu | Browser và ứng dụng đang kết nối khác database hoặc transaction chưa commit | Kiểm tra database đang chọn và ranh giới transaction |

## 12. Tự kiểm tra

1. `Neo4jRepository<Movie, Long>` cho biết điều gì về entity và kiểu định danh?
2. Vì sao ví dụ dùng cả `id` được sinh tự động và `code` nghiệp vụ?
3. Khi nào nên đặt `@Transactional` ở service thay vì chỉ dựa vào transaction của repository?
4. Vì sao `character` được lưu trên relationship `ACTED_IN`?
5. Làm thế nào xác minh rằng cập nhật tiêu đề trong ứng dụng đã được lưu vào Neo4j?
6. `DETACH DELETE` ảnh hưởng thế nào tới node đích và các node ở đầu kia của relationship?
7. Nếu repository trả về phim nhưng projection dàn diễn viên rỗng, bạn sẽ kiểm tra mapping và Cypher theo thứ tự nào?
