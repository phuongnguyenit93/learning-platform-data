# Named query và vị trí cấu hình theo phiên bản

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích named query trong Spring Data Neo4j (SDN) là gì và được tra cứu ở tầng nào.
- Tổ chức câu lệnh Cypher trong file `.properties` thay vì viết trực tiếp trong repository.
- Đặt đúng tên khóa theo entity và tên phương thức repository.
- Cấu hình vị trí file named query bằng `namedQueriesLocation` ở các phiên bản SDN phù hợp.
- Phân biệt named query của Spring Data với `@Query`, derived query và các cơ chế named query của JPA.

## 1. Named query là gì?

Khi một phương thức repository cần thực hiện truy vấn Cypher, SDN có thể lấy câu truy vấn từ nhiều nơi. Cách thường gặp là viết trực tiếp bằng annotation `@Query` hoặc để Spring Data suy ra truy vấn từ tên phương thức. Một lựa chọn khác là lưu câu Cypher trong file properties của ứng dụng và để repository tham chiếu đến nó thông qua tên phương thức. Cách này được gọi là *named query*.

Ví dụ, repository có phương thức:

```java
Optional<Person> findByEmail(@Param("email") String email);
```

Thay vì viết Cypher trong annotation, ứng dụng khai báo truy vấn trong file `neo4j-named-queries.properties`:

```properties
Person.findByEmail=MATCH (p:Person {email: $email}) RETURN p
```

Khi phương thức được gọi, Spring Data tìm named query tương ứng và thực thi Cypher với tham số được truyền vào.

Named query trong SDN là cơ chế tra cứu truy vấn của Spring Data ở phía ứng dụng. Câu Cypher được đóng gói trong tài nguyên của ứng dụng và gửi đến Neo4j khi repository thực thi. Việc khai báo này không tạo một đối tượng truy vấn có tên bên trong máy chủ Neo4j, cũng không phải stored procedure.

## 2. Quy tắc đặt tên khóa named query

Quy tắc thông dụng của Spring Data là:

```text
<Tên đơn giản của entity>.<Tên phương thức repository>=<Câu truy vấn>
```

Ví dụ:

| Thành phần | Giá trị |
| --- | --- |
| Entity Java | `Person` |
| Repository | `PersonRepository` |
| Phương thức | `findFriendsByPersonId` |
| Khóa trong properties | `Person.findFriendsByPersonId` |

Tên entity trong khóa là tên lớp Java quản lý bởi repository, không phải tên interface repository. Nếu lớp `Person` được khai báo `@Node("People")`, khóa vẫn bắt đầu bằng `Person.` vì tên khóa dựa trên domain type.

Tên phương thức phải khớp chính xác với phương thức trong repository, bao gồm chữ hoa và chữ thường. Ví dụ:

```java
public interface PersonRepository
        extends Neo4jRepository<Person, String> {

    List<Person> findFriendsByPersonId(String personId);
}
```

Khóa tương ứng là `Person.findFriendsByPersonId`, không phải `PersonRepository.findFriendsByPersonId`.

## 3. Vị trí file named query

Named query được lưu trong file Java Properties nằm trên classpath của ứng dụng. Vị trí mặc định được dùng phổ biến trong tài liệu SDN là:

```text
src/main/resources/META-INF/neo4j-named-queries.properties
```

Sau khi build, file phải được đóng gói vào JAR tại đường dẫn tài nguyên tương ứng để Spring có thể đọc khi khởi tạo repository.

Ví dụ cấu trúc dự án:

```text
src/
└── main/
    ├── java/
    │   └── com/example/graph/
    │       ├── Person.java
    │       └── PersonRepository.java
    └── resources/
        └── META-INF/
            └── neo4j-named-queries.properties
```

Không đặt file này trong thư mục mã Java, không tạo nó trong Neo4j Browser và không nhầm nó với file cấu hình máy chủ Neo4j. Đây là tài nguyên cấu hình của ứng dụng Spring.

### 3.1. Khai báo nhiều named query

Một file properties có thể chứa nhiều truy vấn cho nhiều entity:

```properties
Person.findByEmail=MATCH (p:Person {email: $email}) RETURN p
Person.findFriendsByPersonId=MATCH (p:Person {personId: $personId})-[:KNOWS]->(friend:Person) RETURN friend ORDER BY friend.name
Movie.findByTitle=MATCH (m:Movie {title: $title}) RETURN m
```

Mỗi dòng là một cặp khóa và giá trị:

- Phần bên trái dấu `=` là khóa tra cứu.
- Phần bên phải là câu Cypher.
- Các tham số như `$email`, `$personId` và `$title` được bind từ tham số phương thức repository.

Vì đây là cú pháp Java Properties, nội dung một thuộc tính thường được viết trên một dòng. Nếu cần xuống dòng để dễ đọc, có thể dùng dấu gạch chéo ngược `\` ở cuối dòng theo quy tắc nối dòng của file properties. Hãy kiểm tra ký tự escape khi truy vấn có dấu gạch chéo hoặc ký tự đặc biệt.

## 4. Cấu hình namedQueriesLocation theo phiên bản

Cơ chế named query được duy trì qua nhiều thế hệ SDN, nhưng cách cấu hình và API repository thay đổi theo kiến trúc của từng phiên bản.

| Phiên bản SDN | Cách tổ chức | Điểm cần chú ý |
| --- | --- | --- |
| SDN 5.x và các thế hệ OGM trước đó | Tài liệu phiên bản này hướng dẫn file `META-INF/neo4j-named-queries.properties` với khóa dạng `Entity.methodName` | Dùng tài liệu đúng phiên bản vì API mapping và cách bind tham số có thể khác các bản mới |
| SDN 6.x | Kiến trúc dựa trên Neo4j Java Driver; cấu hình repository có thuộc tính `namedQueriesLocation` | Cypher dùng cú pháp tham số hiện đại như `$email`; có thể chỉ định tài nguyên named query trong annotation |
| SDN 7.x và 8.x | Tiếp tục hỗ trợ vị trí named query thông qua `namedQueriesLocation` trên cấu hình repository | Kiểm tra Javadoc của đúng phiên bản đang dùng; nếu muốn tránh phụ thuộc vị trí mặc định, hãy cấu hình đường dẫn tường minh |

Từ SDN 6, annotation cấu hình repository thuộc package:

```java
org.springframework.data.neo4j.repository.config.EnableNeo4jRepositories
```

Annotation này cung cấp thuộc tính `namedQueriesLocation` để chỉ định vị trí file properties. Với ứng dụng reactive, annotation tương ứng là `EnableReactiveNeo4jRepositories`, cũng có thuộc tính cấu hình vị trí named query.

Một chi tiết cần kiểm tra khi nâng cấp: Javadoc được sinh cho một số bản SDN 8.x mô tả đường dẫn mặc định bằng chuỗi `META-INFO/neo4j-named-queries.properties`, trong khi tài liệu các thế hệ trước và quy ước tài nguyên Java dùng `META-INF`. Để tránh phụ thuộc vào sự khác biệt trong mô tả mặc định giữa các phiên bản, hãy chỉ định rõ vị trí file bằng `namedQueriesLocation` và đặt tài nguyên đúng cùng đường dẫn đó.

## 5. Cấu hình vị trí file trong SDN 6.x, 7.x và 8.x

Nếu ứng dụng tự khai báo cấu hình repository, có thể đặt đường dẫn rõ ràng bằng `namedQueriesLocation`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.repository.config.EnableNeo4jRepositories;

@Configuration
@EnableNeo4jRepositories(
    basePackages = "com.example.graph.repository",
    namedQueriesLocation =
        "classpath:META-INF/neo4j-named-queries.properties"
)
public class Neo4jRepositoryConfiguration {
}
```

Trong ví dụ:

- `basePackages` chỉ định package chứa repository cần quét.
- `namedQueriesLocation` chỉ định tài nguyên properties trên classpath.
- Tiền tố `classpath:` yêu cầu Spring tìm file trong tài nguyên được đóng gói cùng ứng dụng.

Nếu muốn đặt file ở vị trí khác, ví dụ `src/main/resources/queries/graph-queries.properties`, hãy cấu hình đúng vị trí tương ứng:

```java
@EnableNeo4jRepositories(
    basePackages = "com.example.graph.repository",
    namedQueriesLocation = "classpath:queries/graph-queries.properties"
)
```

Khi dùng Spring Boot với cơ chế tự động quét repository, không cần thêm annotation cấu hình chỉ để bật repository nếu ứng dụng đã được cấu hình tự động. Tuy nhiên, khi muốn đổi vị trí named query khỏi mặc định, hãy cung cấp cấu hình repository tường minh và bảo đảm không đăng ký trùng hai nhóm repository.

Với ứng dụng reactive, dùng annotation `@EnableReactiveNeo4jRepositories` trong package `org.springframework.data.neo4j.repository.config` và khai báo thuộc tính `namedQueriesLocation` tương tự.

## 6. Ví dụ hoàn chỉnh: repository và file properties

Giả sử entity:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String personId;

    private String name;

    private String email;

    protected Person() {
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getPersonId() {
        return personId;
    }
}
```

Repository:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.repository.query.Param;

public interface PersonRepository
        extends Neo4jRepository<Person, String> {

    Optional<Person> findByEmail(@Param("email") String email);

    List<Person> findFriendsByPersonId(
        @Param("personId") String personId
    );
}
```

File `src/main/resources/META-INF/neo4j-named-queries.properties`:

```properties
Person.findByEmail=MATCH (p:Person {email: $email}) RETURN p
Person.findFriendsByPersonId=MATCH (p:Person {personId: $personId})-[:KNOWS]->(friend:Person) RETURN friend ORDER BY friend.name
```

Khi service gọi:

```java
Person person = personRepository.findByEmail("an@example.com")
    .orElseThrow();

List<Person> friends =
    personRepository.findFriendsByPersonId(person.getPersonId());
```

Spring Data tra cứu named query dựa trên entity và tên phương thức, bind giá trị tham số rồi thực thi Cypher. Kết quả node được SDN ánh xạ thành entity `Person` theo kiểu trả về của repository.

Trong ví dụ, `@Param` làm rõ tên tham số được dùng trong Cypher. Đây là cách an toàn khi muốn tránh phụ thuộc vào việc compiler có lưu tên tham số Java hay không.

## 7. Named query, @Query và derived query khác nhau thế nào?

Ba cách này đều có thể phục vụ truy vấn repository, nhưng phù hợp với nhu cầu khác nhau.

| Cách khai báo | Vị trí câu truy vấn | Khi phù hợp |
| --- | --- | --- |
| Derived query | Suy ra từ tên phương thức | Điều kiện đơn giản, có thể diễn đạt rõ bằng tên method |
| `@Query` | Ngay trên phương thức repository | Cypher ngắn hoặc muốn đọc method và truy vấn tại cùng một nơi |
| Named query | File properties riêng trên classpath | Cypher dài, muốn tách câu truy vấn khỏi interface hoặc quản lý tập trung |

Ví dụ derived query:

```java
List<Person> findByName(String name);
```

Ví dụ dùng `@Query`:

```java
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
    MATCH (p:Person {name: $name})
    RETURN p
    """)
Optional<Person> findPersonByName(@Param("name") String name);
```

Ví dụ named query:

```properties
Person.findPersonByName=MATCH (p:Person {name: $name}) RETURN p
```

Nếu truy vấn ngắn và chỉ phục vụ một phương thức, `@Query` thường dễ theo dõi vì câu lệnh nằm ngay tại nơi khai báo API repository. Nếu nhiều câu Cypher dài hoặc cần tách tài nguyên truy vấn khỏi mã Java, named query giúp repository gọn hơn.

Named query không thay thế custom repository implementation. Khi truy vấn cần xây dựng động theo nhiều nhánh nghiệp vụ, thao tác nhiều bước hoặc xử lý kết quả đặc biệt, có thể dùng `Neo4jClient`, `Neo4jTemplate` hoặc custom repository implementation.

## 8. Cách Spring Data chọn truy vấn

Spring Data repository infrastructure hỗ trợ chiến lược tra cứu truy vấn. Chiến lược phổ biến `CREATE_IF_NOT_FOUND` ưu tiên tìm truy vấn đã khai báo trước; nếu không có, framework mới thử tạo truy vấn từ tên phương thức.

Điều này có nghĩa một phương thức có thể có tên giống derived query nhưng vẫn được thực thi bằng Cypher trong named query file nếu khóa tương ứng tồn tại.

Ví dụ:

```java
Optional<Person> findByEmail(String email);
```

Nếu file có:

```properties
Person.findByEmail=MATCH (p:Person {email: $email}) RETURN p
```

truy vấn đã khai báo được sử dụng thay cho truy vấn suy ra từ tên phương thức theo cơ chế lookup mặc định.

Trong SDN 8.x, Javadoc của `@EnableNeo4jRepositories` tập trung vào các thuộc tính cấu hình repository và có `namedQueriesLocation`; không nên sao chép máy móc ví dụ `queryLookupStrategy` từ module Spring Data khác nếu annotation của phiên bản SDN đang dùng không có thuộc tính đó. Hãy đối chiếu API đúng phiên bản trước khi thêm cấu hình.

## 9. Tham số trong named query

Named query sử dụng cùng nguyên tắc bind tham số như Cypher trong `@Query`. Với cú pháp Cypher hiện đại, tham số được viết bằng ký hiệu `$`:

```properties
Person.findByStatus=MATCH (p:Person {status: $status}) RETURN p
```

Repository:

```java
List<Person> findByStatus(@Param("status") String status);
```

Tên trong `@Param("status")` phải khớp với `$status` trong câu Cypher. Không ghép giá trị đầu vào vào chuỗi query bằng nối chuỗi Java. Bind tham số giúp tái sử dụng truy vấn và giảm nguy cơ injection từ dữ liệu đầu vào.

Nếu dự án dựa vào tên tham số Java thay vì `@Param`, hãy bảo đảm build có lưu thông tin tên tham số bằng tùy chọn compiler phù hợp. Khai báo `@Param` tường minh thường dễ đọc và ít phụ thuộc cấu hình build hơn.

## 10. Những lỗi thường gặp khi cấu hình named query

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Repository không tìm thấy named query | Khóa không khớp tên entity hoặc method | Kiểm tra dạng `Entity.methodName` |
| Đặt khóa theo tên repository | Nhầm domain type với repository interface | Dùng tên lớp entity Java |
| File không được nạp | File nằm ngoài classpath hoặc sai đường dẫn | Đặt trong `src/main/resources` và kiểm tra `namedQueriesLocation` |
| Dùng `META-INFO` thay cho `META-INF` | Nhầm lẫn do mô tả mặc định ở một số Javadoc | Chỉ định rõ vị trí tài nguyên và đặt file đúng đường dẫn |
| Cypher báo thiếu tham số | Tên `$param` không khớp `@Param` | Đồng bộ tên hai phía |
| Named query không được sử dụng | Phương thức có khai báo truy vấn khác hoặc khóa không được tìm thấy | Kiểm tra `@Query`, tên khóa và cấu hình lookup |
| Properties bị tách thành nhiều dòng sai | Dùng xuống dòng không theo quy tắc Java Properties | Viết một dòng hoặc nối dòng bằng `\` đúng cú pháp |
| Dùng cú pháp tham số Cypher cũ | Sao chép truy vấn từ ví dụ Neo4j rất cũ | Với Neo4j hiện đại, dùng `$parameter` |

## 11. Quy trình kiểm tra khi named query không hoạt động

Khi gọi repository nhưng truy vấn không được lấy từ file properties, hãy kiểm tra lần lượt:

1. Xác nhận phương thức repository quản lý đúng entity mong muốn.
2. Tạo khóa bằng tên lớp entity đơn giản và tên phương thức chính xác.
3. Kiểm tra file có nằm trong classpath của ứng dụng sau khi build hay không.
4. Kiểm tra vị trí file mặc định hoặc giá trị `namedQueriesLocation` đã cấu hình.
5. Đối chiếu từng tham số `$name` trong Cypher với `@Param("name")`.
6. Kiểm tra phương thức có khai báo `@Query` hoặc cơ chế truy vấn khác khiến named query không được chọn.
7. Kiểm tra cú pháp Cypher độc lập trong Neo4j Browser với cùng cấu trúc dữ liệu và tham số mẫu.
8. Kiểm tra log khởi tạo repository để tìm lỗi đọc properties hoặc lỗi phân tích truy vấn.

Khi nâng cấp SDN, hãy xác minh package annotation, vị trí tài nguyên và cách bind tham số theo tài liệu của phiên bản đích. Không lấy ví dụ từ SDN 5.x rồi áp dụng nguyên xi cho SDN 6.x trở lên, vì các phiên bản này có thay đổi kiến trúc driver và mapping.

## 12. Câu hỏi tự kiểm tra

1. Named query của SDN được lưu ở tầng ứng dụng hay trong Neo4j server?
2. Khóa `Person.findByEmail` được tạo từ tên entity hay tên repository?
3. File named query mặc định thường được đặt ở thư mục nào trong classpath?
4. Thuộc tính `namedQueriesLocation` của `@EnableNeo4jRepositories` dùng để làm gì?
5. Từ SDN 6 trở đi, vì sao cần đối chiếu package và API cấu hình theo phiên bản?
6. Tên tham số trong `@Param` cần khớp với phần nào của Cypher?
7. Khi nào nên chọn named query thay cho `@Query`?
8. Vì sao không nên nhầm named query của SDN với `@NamedQuery` của JPA?
9. Nếu named query không được tìm thấy, cần kiểm tra những thành phần nào trước?

## Tài liệu tham khảo

- [Spring Data Neo4j – EnableNeo4jRepositories API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/config/EnableNeo4jRepositories.html)
- [Spring Data Neo4j – Defining Query Methods](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-methods-details.html)
- [Spring Data Neo4j 5.3 – Reference Documentation](https://docs.spring.io/spring-data/neo4j/docs/5.3.6.RELEASE/reference/html/)
- [Spring Data Neo4j 6.0 – Reference Documentation](https://docs.spring.io/spring-data/neo4j/docs/6.0.1/reference/html/)

## Kết luận

Named query cho phép tách câu Cypher khỏi repository interface bằng cách lưu truy vấn trong file properties trên classpath. Khóa truy vấn được đặt theo tên đơn giản của entity và tên phương thức repository, còn tham số được bind từ các đối số phương thức.

Với SDN 5.x, tài liệu phiên bản hướng dẫn file `META-INF/neo4j-named-queries.properties`. Từ SDN 6.x, cấu hình repository có thuộc tính `namedQueriesLocation`; SDN 7.x và 8.x tiếp tục hỗ trợ cơ chế này. Khi nâng cấp, hãy kiểm tra API của đúng phiên bản và chỉ định rõ đường dẫn tài nguyên để tránh nhầm lẫn về vị trí mặc định.

Chọn named query khi cần quản lý tập Cypher dài hoặc tách truy vấn khỏi mã Java. Với truy vấn ngắn, `@Query` thường dễ đọc hơn; với điều kiện đơn giản, derived query vẫn là lựa chọn gọn. Dù chọn cách nào, hãy đặt tên khóa chính xác, bind tham số rõ ràng và kiểm tra file properties được đóng gói cùng ứng dụng.
