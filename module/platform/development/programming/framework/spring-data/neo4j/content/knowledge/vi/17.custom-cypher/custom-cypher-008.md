# Truy vấn CREATE, MERGE, SET hoặc DELETE qua repository

Spring Data Neo4j (SDN) cung cấp `Neo4jRepository` cho các thao tác CRUD thông thường. Khi một nghiệp vụ cần kiểm soát chính xác cách tạo node, tạo relationship, cập nhật thuộc tính hoặc xóa dữ liệu, ta có thể khai báo Cypher trực tiếp bằng annotation `@Query` trên repository method.

Các lệnh `CREATE`, `MERGE`, `SET` và `DELETE` cho phép mô tả thay đổi đồ thị sát với nghiệp vụ. `CREATE` tạo cấu trúc mới; `MERGE` tìm hoặc tạo theo mẫu; `SET` cập nhật property hoặc label; `DELETE` xóa relationship hoặc node. Khi dùng chúng qua repository, cần chú ý bind tham số, kiểu dữ liệu trả về, transaction, tính lặp an toàn và tác động của truy vấn tới entity đang được ánh xạ.

Bài học sử dụng ví dụ danh mục phim: node `Movie` và `Person` được nối bằng relationship `ACTED_IN`. Một lượt diễn xuất lưu thêm thuộc tính `role` trên relationship.

## 1. Khi nào cần Cypher tùy chỉnh trong repository?

Với thao tác đơn giản, các method có sẵn như `save`, `findById`, `deleteById` hoặc derived query thường là lựa chọn phù hợp. Dùng `@Query` khi nghiệp vụ cần một hoặc nhiều thao tác Cypher được điều khiển rõ ràng, ví dụ:

- Tạo một node với những thuộc tính xác định và trả lại node vừa tạo.
- Dùng `MERGE` để upsert theo khóa nghiệp vụ.
- Tạo hoặc cập nhật relationship và property của relationship trong một câu lệnh.
- Cập nhật một vài property mà không phải tải cả aggregate về Java.
- Xóa một relationship cụ thể hoặc xóa node cùng các relationship gắn với nó.
- Kết hợp nhiều bước ghi trong một query để giảm số lần round trip tới database.

`@Query` nhận câu lệnh Cypher và bind tham số từ các đối số của method. Kết quả được SDN ánh xạ theo kiểu trả về nếu query có `RETURN`. Với method chỉ thực hiện lệnh ghi và không cần kết quả, có thể khai báo kiểu trả về `void`.

## 2. Mô hình dữ liệu và repository

Ví dụ dùng mã nghiệp vụ `code` làm ID của node. Mã này phải ổn định và duy nhất. Ta tạo unique constraint ở Neo4j để database bảo vệ quy tắc đó, kể cả khi có nhiều request ghi đồng thời.

```cypher
CREATE CONSTRAINT movie_code_unique IF NOT EXISTS
FOR (m:Movie)
REQUIRE m.code IS UNIQUE;

CREATE CONSTRAINT person_code_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.code IS UNIQUE;
```

Entity `Movie`:

```java
import java.util.HashSet;
import java.util.Set;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Movie")
public class Movie {
    @Id
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

    public String getCode() { return code; }
    public String getTitle() { return title; }
    public Integer getReleaseYear() { return releaseYear; }
    public Set<ActingCredit> getCast() { return cast; }
}
```

Entity `Person`:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {
    @Id
    private String code;

    private String name;

    protected Person() {
    }

    public Person(String code, String name) {
        this.code = code;
        this.name = name;
    }

    public String getCode() { return code; }
    public String getName() { return name; }
}
```

Relationship có thuộc tính:

```java
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class ActingCredit {
    @RelationshipId
    private Long id;

    private String role;

    @TargetNode
    private Person actor;

    protected ActingCredit() {
    }

    public String getRole() { return role; }
    public Person getActor() { return actor; }
}
```

Trong mô hình này, hướng relationship là `Person -[:ACTED_IN]-> Movie`. Collection `cast` đặt trên `Movie` vì vậy dùng `INCOMING`. `role` mô tả vai diễn trong một phim cụ thể nên thuộc về relationship, không phải thuộc tính dùng chung của `Person` hoặc `Movie`.

Repository sẽ khai báo `@Query` để chạy các câu Cypher. Các ví dụ sau có thể đặt trong `MovieRepository`:

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface MovieRepository extends Neo4jRepository<Movie, String> {
    // Các method CREATE, MERGE, SET và DELETE được khai báo ở phần sau.
}
```

Repository cho `Person` có thể khai báo một upsert riêng:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MERGE (p:Person {code: $code})
        ON CREATE SET p.name = $name
        ON MATCH SET p.name = $name
        RETURN p
        """)
    Person upsertPerson(
        @Param("code") String code,
        @Param("name") String name
    );
}
```

## 3. CREATE — tạo node hoặc relationship mới

`CREATE` luôn tạo một node hoặc relationship mới theo mẫu được chỉ định. Nếu chạy cùng một lệnh nhiều lần, Neo4j sẽ tạo thêm dữ liệu ở mỗi lần chạy. Vì vậy, hãy dùng `CREATE` khi ứng dụng thực sự muốn tạo một thực thể mới và đã có quy tắc kiểm soát trùng lặp.

Ví dụ tạo phim:

```java
@Query("""
    CREATE (m:Movie {
        code: $code,
        title: $title,
        releaseYear: $releaseYear
    })
    RETURN m
    """)
Movie createMovie(
    @Param("code") String code,
    @Param("title") String title,
    @Param("releaseYear") Integer releaseYear
);
```

`RETURN m` trả node vừa tạo để SDN ánh xạ thành `Movie`. Các tham số `$code`, `$title` và `$releaseYear` được bind từ method argument. Nếu `code` đã tồn tại, unique constraint sẽ khiến thao tác thất bại; service có thể chuyển lỗi đó thành phản hồi nghiệp vụ như “mã phim đã được sử dụng”.

Tạo relationship mới giữa hai node đã tồn tại:

```java
@Query("""
    MATCH (p:Person {code: $personCode})
    MATCH (m:Movie {code: $movieCode})
    CREATE (p)-[r:ACTED_IN {role: $role}]->(m)
    RETURN count(r) AS createdCount
    """)
long createActingCredit(
    @Param("personCode") String personCode,
    @Param("movieCode") String movieCode,
    @Param("role") String role
);
```

Nếu cả hai node được tìm thấy, query tạo relationship và trả số relationship đã tạo. Nếu một node không tồn tại, `MATCH` không tạo dòng kết quả nên không có relationship nào được tạo; kết quả tổng hợp là `0`. Nếu nghiệp vụ yêu cầu báo lỗi khi thiếu node, service cần kiểm tra kết quả hoặc thực hiện bước xác minh riêng trong cùng transaction.

`CREATE` không kiểm tra xem một relationship cùng loại giữa hai node đã có hay chưa. Nếu query bị gửi lại, có thể xuất hiện nhiều relationship `ACTED_IN` giống nhau. Với thao tác có thể retry hoặc nhận thông điệp lặp, cân nhắc `MERGE` ở phần tiếp theo.

## 4. MERGE — tìm hoặc tạo theo khóa ổn định

`MERGE` tìm mẫu trong graph. Nếu mẫu chưa tồn tại, Neo4j tạo mẫu đó; nếu đã tồn tại, Neo4j sử dụng phần tử phù hợp. Đây là công cụ phổ biến để thực hiện upsert.

Ví dụ tạo mới hoặc cập nhật phim theo `code`:

```java
@Query("""
    MERGE (m:Movie {code: $code})
    ON CREATE SET
        m.title = $title,
        m.releaseYear = $releaseYear,
        m.createdAt = datetime(),
        m.updatedAt = datetime()
    ON MATCH SET
        m.title = $title,
        m.releaseYear = $releaseYear,
        m.updatedAt = datetime()
    RETURN m
    """)
Movie upsertMovie(
    @Param("code") String code,
    @Param("title") String title,
    @Param("releaseYear") Integer releaseYear
);
```

`code` là khóa ổn định dùng để xác định phim. `ON CREATE SET` chạy khi node mới được tạo; `ON MATCH SET` chạy khi node đã tồn tại. Các thuộc tính có thể thay đổi như `title` và `releaseYear` được cập nhật bên ngoài mẫu `MERGE`.

Không nên đưa tất cả thuộc tính thay đổi vào mẫu `MERGE`:

```cypher
// Không phù hợp nếu title có thể thay đổi.
MERGE (m:Movie {code: $code, title: $title})
RETURN m;
```

`MERGE` so khớp toàn bộ mẫu. Nếu cùng `code` nhưng tiêu đề khác, mẫu có thể không khớp node hiện có và tạo node khác. Hãy dùng khóa định danh ổn định trong mẫu, sau đó dùng `ON CREATE SET`, `ON MATCH SET` hoặc `SET` để cập nhật thuộc tính mô tả.

Unique constraint vẫn cần thiết. `MERGE` giúp diễn đạt tìm-hoặc-tạo, nhưng constraint là cơ chế database bảo vệ tính duy nhất khi có transaction đồng thời.

### MERGE node và relationship trong cùng nghiệp vụ

Giả sử ứng dụng nhận sự kiện diễn viên tham gia phim. Có thể tìm hoặc tạo hai node, rồi tìm hoặc tạo relationship:

```java
@Query("""
    MERGE (p:Person {code: $personCode})
    ON CREATE SET p.name = $personName
    ON MATCH SET p.name = $personName

    MERGE (m:Movie {code: $movieCode})
    ON CREATE SET m.title = $movieTitle

    MERGE (p)-[r:ACTED_IN]->(m)
    ON CREATE SET r.role = $role, r.createdAt = datetime()
    ON MATCH SET r.role = $role, r.updatedAt = datetime()

    RETURN count(r) AS relationshipCount
    """)
long upsertActingCredit(
    @Param("personCode") String personCode,
    @Param("personName") String personName,
    @Param("movieCode") String movieCode,
    @Param("movieTitle") String movieTitle,
    @Param("role") String role
);
```

Ví dụ giả định mỗi cặp diễn viên–phim chỉ có một relationship `ACTED_IN`. Nếu nghiệp vụ cho phép một người đóng nhiều vai trong cùng phim và mỗi vai cần một relationship riêng, phải đưa khóa phân biệt lượt diễn xuất vào mô hình và mẫu `MERGE` theo quy tắc đó. Không dùng thuộc tính thay đổi như `role` làm khóa nếu muốn cập nhật vai diễn trên relationship hiện có.

Trong trường hợp node đã được tạo bởi các repository method khác, có thể chỉ `MATCH` hai node rồi `MERGE` relationship. Ví dụ method này có thể được gọi sau `upsertMovie` và `upsertPerson` trong cùng service transaction:

```java
@Query("""
    MATCH (p:Person {code: $personCode})
    MATCH (m:Movie {code: $movieCode})
    MERGE (p)-[r:ACTED_IN]->(m)
    ON CREATE SET r.role = $role, r.createdAt = datetime()
    ON MATCH SET r.role = $role, r.updatedAt = datetime()
    RETURN count(r) AS relationshipCount
    """)
long linkExistingActor(
    @Param("personCode") String personCode,
    @Param("movieCode") String movieCode,
    @Param("role") String role
);
```

## 5. SET — cập nhật property và label

`SET` cập nhật property của node hoặc relationship. Ví dụ đổi tiêu đề và năm phát hành của phim:

```java
@Query("""
    MATCH (m:Movie {code: $code})
    SET m.title = $title,
        m.releaseYear = $releaseYear,
        m.updatedAt = datetime()
    RETURN m
    """)
Optional<Movie> updateMovie(
    @Param("code") String code,
    @Param("title") String title,
    @Param("releaseYear") Integer releaseYear
);
```

Nếu không tìm thấy phim, `MATCH` không tạo dòng kết quả và method trả `Optional.empty()`. Service có thể chuyển trường hợp đó thành lỗi “không tìm thấy phim” hoặc phản hồi phù hợp với API. Query chỉ trả về node `m`, không trả các relationship `ACTED_IN`; vì vậy không xem kết quả này là một aggregate đã được nạp đầy đủ để lưu lại với mục đích đồng bộ toàn bộ graph.

Cập nhật thuộc tính relationship cũng dùng `SET`:

```java
@Query("""
    MATCH (p:Person {code: $personCode})-[r:ACTED_IN]->
          (m:Movie {code: $movieCode})
    SET r.role = $role,
        r.updatedAt = datetime()
    RETURN count(r) AS updatedCount
    """)
long updateActingRole(
    @Param("personCode") String personCode,
    @Param("movieCode") String movieCode,
    @Param("role") String role
);
```

Có thể cập nhật nhiều property từ một map tham số:

```cypher
MATCH (m:Movie {code: $code})
SET m += $properties
RETURN m;
```

Phân biệt hai cách gán map:

- `SET m += $properties` thêm hoặc cập nhật các key có trong map và giữ lại các property khác của node.
- `SET m = $properties` thay thế toàn bộ map property hiện có bằng map mới. Những property không có trong map sẽ bị loại bỏ.

Trong Cypher, gán một property bằng `null` sẽ xóa property đó. Vì vậy, nếu map truyền vào có key với giá trị `null`, thao tác cập nhật có thể xóa property tương ứng. Hãy kiểm tra dữ liệu đầu vào trước khi dùng map update, đặc biệt với request PATCH cần phân biệt trường không được gửi và trường được yêu cầu xóa.

`SET` cũng có thể gắn label:

```cypher
MATCH (m:Movie {code: $code})
SET m:Featured
RETURN m;
```

Query này thêm label `Featured` cho node. Nếu label thuộc schema cố định của ứng dụng, nên quản lý nó có chủ đích trong domain model hoặc migration; không dùng dữ liệu đầu vào tùy ý làm label hay tên relationship.

## 6. DELETE — xóa relationship hoặc node

Trong đồ thị, xóa relationship và xóa node là hai thao tác khác nhau. Có thể xóa một lượt diễn xuất mà vẫn giữ cả diễn viên lẫn phim:

```java
@Query(value = """
    MATCH (p:Person {code: $personCode})-[r:ACTED_IN]->
          (m:Movie {code: $movieCode})
    DELETE r
    """, delete = true)
void deleteActingCredit(
    @Param("personCode") String personCode,
    @Param("movieCode") String movieCode
);
```

Thuộc tính `delete = true` đánh dấu custom query này là truy vấn xóa của SDN. Cypher `DELETE r` chỉ xóa relationship được match; node `Person` và `Movie` vẫn tồn tại.

Neo4j không cho phép xóa node còn relationship gắn vào nó bằng `DELETE`. Nếu muốn xóa phim cùng mọi relationship gắn trực tiếp với phim, dùng `DETACH DELETE`:

```java
@Query(value = """
    MATCH (m:Movie {code: $code})
    DETACH DELETE m
    """, delete = true)
void deleteMovieAndRelationships(@Param("code") String code);
```

`DETACH DELETE m` xóa node phim và tất cả relationship gắn với node đó. Các node ở đầu kia của relationship, ví dụ `Person`, vẫn tồn tại. Đây là thao tác có phạm vi rộng hơn xóa một relationship, nên cần chắc chắn nghiệp vụ cho phép xóa các liên kết đó.

Nếu muốn xóa node nhưng bảo toàn một số quan hệ, hãy xóa có chọn lọc các relationship cần bỏ trước, kiểm tra node còn relationship nào rồi mới dùng `DELETE`. Không dùng `DETACH DELETE` như một cách né lỗi khi chưa hiểu tác động tới graph.

## 7. Gắn tham số an toàn cho repository method

Tham số Cypher dùng cú pháp `$parameterName`. Spring Data Neo4j bind giá trị từ method argument; nên dùng `@Param` để chỉ rõ tên tham số khi muốn code dễ đọc và không phụ thuộc vào việc compiler giữ tên tham số.

```java
@Query("""
    MATCH (m:Movie {code: $code})
    SET m.title = $title
    RETURN m
    """)
Optional<Movie> renameMovie(
    @Param("code") String code,
    @Param("title") String title
);
```

Không ghép chuỗi đầu vào vào Cypher:

```java
// Không làm theo cách này.
String cypher = "MATCH (m:Movie {code: '" + code + "'}) RETURN m";
```

Ghép chuỗi vừa làm tăng nguy cơ Cypher injection, vừa khiến query khó tái sử dụng và khó kiểm soát. Dùng parameter binding cho giá trị. Label và relationship type không thể bind như property value thông thường; hãy giữ chúng tĩnh trong query hoặc dùng cơ chế literal có kiểm soát và whitelist nếu thực sự cần tên động.

## 8. Transaction khi có nhiều lệnh ghi

Một nghiệp vụ có thể gồm nhiều query: tạo phim, tìm hoặc tạo diễn viên, rồi nối relationship. Nếu một bước thất bại, có thể cần rollback toàn bộ thay đổi để graph không ở trạng thái dở dang. Đặt transaction ở ranh giới service:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MovieCatalogService {
    private final MovieRepository movieRepository;
    private final PersonRepository personRepository;

    public MovieCatalogService(
            MovieRepository movieRepository,
            PersonRepository personRepository) {
        this.movieRepository = movieRepository;
        this.personRepository = personRepository;
    }

    @Transactional
    public void registerMovieWithActor(
            String movieCode,
            String title,
            Integer releaseYear,
            String personCode,
            String personName,
            String role) {

        movieRepository.upsertMovie(movieCode, title, releaseYear);
        personRepository.upsertPerson(personCode, personName);
        movieRepository.linkExistingActor(personCode, movieCode, role);
    }
}
```

Đây là ví dụ minh họa transaction bao quanh nhiều repository method. `PersonRepository.upsertPerson` được khai báo ở phần mô hình; `MovieRepository.linkExistingActor` là method dùng `MATCH` hai node đã tồn tại rồi `MERGE` relationship. Khi tất cả lời gọi tham gia cùng transaction manager của Neo4j, một lỗi trong phương thức service sẽ khiến các thay đổi thuộc transaction đó được rollback theo quy tắc rollback của Spring.

Không đánh dấu write method là `@Transactional(readOnly = true)`. SDN không phân tích Cypher tùy chỉnh để tự xác định query có ghi hay không; custom query có thể chứa `MERGE` hoặc procedure có side effect. Với query chỉ đọc, hãy khai báo read-only rõ ràng ở method hoặc service tương ứng.

Không cần dùng `@Modifying` của Spring Data JPA cho các method Cypher của Spring Data Neo4j. Với custom delete method, SDN cung cấp thuộc tính `delete` trên `@Query`; phần còn lại được diễn đạt bằng câu lệnh Cypher tương ứng.

## 9. Hiểu kết quả trả về và trạng thái entity

Khi custom query trả về node hoặc relationship, tên alias và cấu trúc record phải phù hợp với kiểu Java cần ánh xạ.

| Query result | Kiểu method phù hợp | Ý nghĩa |
|---|---|---|
| `RETURN m` với một node `Movie` | `Movie` hoặc `Optional<Movie>` | Ánh xạ node thành entity |
| `RETURN count(r) AS updatedCount` | `long` hoặc `Long` | Trả một giá trị tổng hợp |
| Query ghi không có `RETURN` | `void` | Chỉ quan tâm thao tác hoàn tất |
| `RETURN m, collect(r), collect(p)` | Entity root có relationship mapping | Trả một record cho root cùng các relationship và node liên quan |

Nếu muốn SDN ánh xạ một `Movie` cùng danh sách diễn viên, tránh trả một dòng riêng cho mỗi diễn viên vì nhiều record có cùng root node có thể tạo kết quả lặp hoặc không ánh xạ graph như mong muốn. Hãy gom relationship và node liên quan trong một record:

```cypher
MATCH (m:Movie {code: $code})
OPTIONAL MATCH (m)<-[r:ACTED_IN]-(p:Person)
RETURN m, collect(r), collect(p);
```

Đối với query ghi trả về entity, hãy trả về node cần ánh xạ. Nếu chỉ cần một con số hoặc trạng thái, trả scalar/projection thay vì tải toàn bộ graph.

Một custom Cypher query thay đổi database không tự sửa những object Java đã được tải trước đó. Nếu cần trạng thái mới sau khi ghi, hãy đọc lại entity bằng repository hoặc trả dữ liệu cần thiết trực tiếp từ query. Tránh lấy một entity chỉ được tải một phần rồi lưu ngược lại như thể nó là toàn bộ graph; việc lưu aggregate có thể đồng bộ relationship theo mô hình đã ánh xạ và làm mất những quan hệ mà query trước đó không tải.

## 10. CREATE, MERGE, SET và DELETE khác nhau thế nào?

| Lệnh | Hành vi | Khi nên dùng | Rủi ro cần kiểm soát |
|---|---|---|---|
| `CREATE` | Luôn tạo node/relationship mới | Tạo thực thể hoặc quan hệ mới theo yêu cầu rõ ràng | Chạy lặp có thể tạo dữ liệu trùng |
| `MERGE` | Tìm mẫu hoặc tạo nếu chưa có | Upsert theo khóa ổn định, xử lý sự kiện gửi lặp | Mẫu so khớp sai hoặc thiếu unique constraint có thể tạo bản ghi không mong muốn |
| `SET` | Gán property hoặc label | Cập nhật node/relationship hiện có | Gán `null` xóa property; `SET n = map` thay toàn bộ property map |
| `DELETE` | Xóa relationship hoặc node không còn relationship | Xóa liên kết cụ thể hoặc node đã được tháo liên kết | Xóa node còn relationship sẽ lỗi |
| `DETACH DELETE` | Xóa node cùng tất cả relationship gắn trực tiếp | Xóa node theo chính sách xóa toàn bộ liên kết | Có thể xóa nhiều quan hệ hơn dự kiến |

Một quy trình ghi thường có thể kết hợp các lệnh: `MERGE` tìm hoặc tạo node, `SET` cập nhật thuộc tính, `MERGE` relationship và `DELETE` những quan hệ cũ không còn hợp lệ. Hãy viết query sao cho khóa so khớp, phạm vi cập nhật và phạm vi xóa đều thể hiện rõ.

## 11. Kiểm tra query sau khi thực hiện

Sau mỗi thao tác ghi, có thể xác minh dữ liệu trực tiếp bằng Neo4j Browser hoặc Cypher Shell.

Kiểm tra phim:

```cypher
MATCH (m:Movie {code: $code})
RETURN m.code, m.title, m.releaseYear, m.createdAt, m.updatedAt;
```

Kiểm tra lượt diễn xuất:

```cypher
MATCH (p:Person {code: $personCode})-[r:ACTED_IN]->
      (m:Movie {code: $movieCode})
RETURN p.name AS actor, r.role AS role, m.title AS movie;
```

Kiểm tra số relationship còn lại của phim:

```cypher
MATCH (m:Movie {code: $code})
OPTIONAL MATCH (p:Person)-[r:ACTED_IN]->(m)
RETURN count(r) AS actingCreditCount;
```

Kiểm tra node đã bị xóa:

```cypher
MATCH (m:Movie {code: $code})
RETURN count(m) AS remainingMovies;
```

Nếu `remainingMovies` bằng `0`, không còn node phim mang mã đó. Sau `DETACH DELETE`, có thể kiểm tra node `Person` để xác nhận các node đầu kia vẫn còn nếu đó là yêu cầu nghiệp vụ.

## 12. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Gọi lại API tạo nhiều node giống nhau | Dùng `CREATE` cho thao tác có thể retry | Dùng `MERGE` theo khóa ổn định và tạo unique constraint |
| `MERGE` vẫn tạo node khác khi tên thay đổi | Đưa thuộc tính mô tả vào mẫu `MERGE` | Chỉ `MERGE` theo ID/key ổn định; cập nhật tên bằng `SET` |
| Query không tạo relationship | Một trong hai `MATCH` không tìm thấy node | Kiểm tra mã node, database và kết quả match |
| Cập nhật làm mất property khác | Dùng `SET n = $map` thay cho `SET n += $map` | Chọn đúng semantics map update và lọc key null |
| Không xóa được node | Node vẫn còn relationship gắn vào | Xóa relationship cần thiết hoặc dùng `DETACH DELETE` nếu nghiệp vụ cho phép |
| Entity Java không phản ánh dữ liệu mới | Object đã tải trước custom Cypher write | Đọc lại entity hoặc trả kết quả mới từ query |
| Kết quả entity có node root bị lặp | Query trả nhiều record cho cùng root | Dùng `collect(relationship)` và `collect(node)` để tạo một record cho root |
| Query lỗi do trùng mã khi ghi đồng thời | Chưa có unique constraint hoặc chưa xử lý lỗi constraint | Tạo constraint và xử lý xung đột theo nghiệp vụ |

## 13. Quy trình thiết kế write query

Trước khi thêm method ghi Cypher vào repository, hãy làm rõ các điểm sau:

1. Xác định node hoặc relationship cần thay đổi và khóa dùng để tìm chúng.
2. Chọn `CREATE` nếu luôn tạo mới; chọn `MERGE` nếu cần tìm hoặc tạo theo một mẫu ổn định.
3. Tạo unique constraint cho khóa nghiệp vụ để bảo vệ tính duy nhất ở database.
4. Đưa giá trị đầu vào qua named parameter, không nối chuỗi Cypher.
5. Dùng `SET` để cập nhật thuộc tính; xác định rõ giữ hay thay toàn bộ property map.
6. Dùng `DELETE` cho relationship cụ thể và chỉ dùng `DETACH DELETE` khi chấp nhận xóa mọi liên kết của node.
7. Chọn kiểu trả về: entity, projection, scalar hoặc `void`.
8. Đặt transaction ở service nếu nghiệp vụ có nhiều thao tác ghi cần nguyên tử.
9. Kiểm tra query bằng integration test, kể cả trường hợp node không tồn tại, request lặp và dữ liệu trùng.
10. Đọc lại graph sau thao tác để xác minh đúng node, relationship và property đã thay đổi.

## 14. Tự kiểm tra

1. Khác biệt giữa `CREATE` và `MERGE` là gì khi một request có thể được gửi lặp?
2. Vì sao `MERGE (m:Movie {code: $code, title: $title})` có thể tạo node mới khi tiêu đề thay đổi?
3. Unique constraint bổ sung bảo vệ điều gì khi nhiều transaction cùng upsert một node?
4. Khác biệt giữa `SET m += $properties` và `SET m = $properties` là gì?
5. Vì sao gán `null` cho property trong Cypher có thể làm dữ liệu biến mất?
6. Khi nào nên dùng `DELETE r`, khi nào nên dùng `DETACH DELETE m`?
7. `@Query(delete = true)` có ý nghĩa gì với một custom delete method trong SDN?
8. Vì sao một query ánh xạ entity root có nhiều relationship nên gom các node và relationship vào một record?
9. Vì sao cần `@Transactional` ở service khi một nghiệp vụ gọi nhiều repository write method?

## Tài liệu tham khảo

- [Spring Data Neo4j — Custom Queries](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
- [Spring Data Neo4j — `@Query` API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/query/Query.html)
- [Spring Data Neo4j — FAQ: Transactions and read-only queries](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
