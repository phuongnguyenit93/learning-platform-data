# So sánh JOIN với duyệt quan hệ qua ví dụ phim–diễn viên

Khi xây dựng ứng dụng quản lý phim, ta thường cần trả lời những câu hỏi như: một bộ phim có những diễn viên nào, một diễn viên đã tham gia những phim nào, hoặc hai diễn viên từng đóng chung bao nhiêu phim. Cả cơ sở dữ liệu quan hệ lẫn cơ sở dữ liệu đồ thị đều có thể lưu trữ dữ liệu này, nhưng cách biểu diễn và cách truy vấn quan hệ khác nhau.

Trong cơ sở dữ liệu quan hệ, quan hệ giữa phim và diễn viên thường được biểu diễn bằng khóa ngoại hoặc bảng trung gian rồi kết hợp các bảng bằng `JOIN`. Trong Neo4j, phim và diễn viên là các node; việc tham gia một bộ phim là một relationship có hướng và có thể mang thuộc tính như tên vai diễn. Cypher diễn đạt truy vấn bằng cách khớp và duyệt trực tiếp mẫu đồ thị đó. Spring Data Neo4j (SDN) giúp ánh xạ node, relationship và kết quả Cypher vào các đối tượng Java.

Sau bài học, bạn có thể:

- Biểu diễn cùng một miền dữ liệu phim–diễn viên bằng bảng quan hệ và bằng đồ thị.
- Đọc, so sánh truy vấn SQL dùng `JOIN` với truy vấn Cypher dùng mẫu quan hệ.
- Mô hình hóa node và relationship có thuộc tính bằng Spring Data Neo4j.
- Viết repository query, đặt transaction và nhận biết những điểm cần tối ưu khi duyệt đồ thị.

## 1. Bài toán và mô hình quan hệ

Giả sử ứng dụng có ba loại dữ liệu:

- `Movie`: phim, gồm mã phim, tiêu đề và năm phát hành.
- `Person`: người tham gia sản xuất, trong ví dụ này tập trung vào diễn viên.
- `Casting`: một lượt ghi nhận diễn viên tham gia một phim, gồm mã phim, mã người, tên nhân vật và thứ tự xuất hiện trong danh sách diễn viên.

Trong mô hình quan hệ, cấu trúc có thể được tổ chức như sau:

| Bảng | Cột tiêu biểu | Vai trò |
|---|---|---|
| `Movie` | `id`, `title`, `release_year` | Lưu thông tin phim |
| `Person` | `id`, `name` | Lưu thông tin diễn viên |
| `Casting` | `movie_id`, `person_id`, `character_name`, `billing_order` | Nối phim với diễn viên và lưu thông tin vai diễn |

`Casting.movie_id` tham chiếu `Movie.id`; `Casting.person_id` tham chiếu `Person.id`. Bảng trung gian là cần thiết vì một phim có nhiều diễn viên và một diễn viên có thể tham gia nhiều phim. Các thuộc tính như tên nhân vật thuộc về chính lần tham gia, nên được đặt trên `Casting` thay vì đặt trực tiếp trên `Movie` hoặc `Person`.

Để tìm diễn viên và nhân vật trong một phim, SQL phải kết hợp ba bảng:

```sql
SELECT p.name, c.character_name
FROM Movie AS m
JOIN Casting AS c ON c.movie_id = m.id
JOIN Person AS p ON p.id = c.person_id
WHERE m.title = :title
ORDER BY p.name;
```

Điều kiện `JOIN` ghép các hàng có khóa tương ứng. Cơ sở dữ liệu dùng bộ tối ưu truy vấn để chọn thứ tự kết hợp, cách truy cập chỉ mục và thuật toán join phù hợp. Với chỉ mục trên `Movie.title`, `Casting.movie_id` và `Person.id`, truy vấn có thể tìm phim trước rồi lần lượt tra các lượt casting và thông tin người.

Mô hình này rõ ràng, quen thuộc và phù hợp với dữ liệu có cấu trúc dạng bảng. Tuy nhiên, khi câu hỏi đi qua nhiều loại quan hệ, câu SQL phải thể hiện từng lần nối bảng. Điều đó không có nghĩa `JOIN` luôn chậm: hệ quản trị quan hệ được tối ưu rất tốt cho join, lọc, tổng hợp và các phép phân tích trên dữ liệu dạng bảng.

## 2. Biểu diễn cùng dữ liệu thành đồ thị Neo4j

Trong Neo4j, ta biểu diễn phim và diễn viên bằng node, còn việc tham gia phim bằng relationship:

```text
(Person)-[:ACTED_IN {character, billingOrder}]->(Movie)
```

Ví dụ, một node diễn viên có thể nối tới nhiều node phim. Một node phim cũng có thể nhận relationship `ACTED_IN` từ nhiều diễn viên. `character` và `billingOrder` là thuộc tính của relationship vì chúng mô tả vai diễn của một người trong một phim cụ thể.

Hướng relationship được chọn từ `Person` tới `Movie`: diễn viên `ACTED_IN` phim. Hướng này mang ý nghĩa miền dữ liệu và giúp đọc mẫu đồ thị nhất quán. Khi cần đi theo chiều ngược lại, Cypher có thể dùng mũi tên ngược mà không cần tạo thêm một relationship thứ hai.

Truy vấn tìm diễn viên trong một phim bằng Cypher:

```cypher
MATCH (m:Movie {title: $title})<-[r:ACTED_IN]-(p:Person)
RETURN p.name AS actor,
       r.character AS character
ORDER BY actor;
```

Đọc truy vấn theo từng phần:

1. `MATCH` tìm mẫu đồ thị cần khớp.
2. `(m:Movie {title: $title})` xác định node phim theo nhãn `Movie` và thuộc tính `title`.
3. `<-[r:ACTED_IN]-` đi từ node phim ngược theo relationship `ACTED_IN` tới diễn viên; `r` đại diện cho relationship để đọc thuộc tính của nó.
4. `(p:Person)` yêu cầu node ở đầu kia có nhãn `Person`.
5. `RETURN` chỉ lấy tên diễn viên và tên nhân vật cần hiển thị.

`$title` là tham số của truy vấn. Truyền giá trị qua tham số giúp tái sử dụng truy vấn và tránh ghép chuỗi dữ liệu đầu vào vào câu Cypher.

Để tìm các phim của một diễn viên, ta đảo chiều mẫu:

```cypher
MATCH (p:Person {id: $personId})-[:ACTED_IN]->(m:Movie)
RETURN m.title AS movie,
       m.releaseYear AS releaseYear
ORDER BY releaseYear DESC;
```

Không cần thêm một bảng nối hoặc một relationship ngược. Cypher chỉ mô tả hướng duyệt phù hợp với câu hỏi.

## 3. So sánh JOIN và duyệt relationship

| Khía cạnh | Cơ sở dữ liệu quan hệ | Neo4j và Cypher |
|---|---|---|
| Biểu diễn phim–diễn viên | Ba bảng `Movie`, `Person`, `Casting` liên kết bằng khóa | Hai loại node `Movie`, `Person` nối bằng `ACTED_IN` |
| Thông tin của lần tham gia | Các cột trên hàng của bảng `Casting` | Thuộc tính trên relationship `ACTED_IN` |
| Truy vấn dàn diễn viên | `JOIN` phim, bảng casting và người | Khớp phim rồi duyệt relationship tới diễn viên |
| Truy vấn nhiều bước | Thêm các phép `JOIN` theo từng quan hệ | Ghép các đoạn đường đi trong mẫu đồ thị |
| Điểm cần tối ưu | Chỉ mục, thứ tự join, bộ lọc, số hàng trung gian | Điểm bắt đầu, chỉ mục, độ rộng và độ dài đường đi, số kết quả trung gian |
| Thế mạnh thường gặp | Giao dịch dạng bảng, tổng hợp, báo cáo và quan hệ có cấu trúc ổn định | Truy vấn tập trung vào kết nối, đường đi và quan hệ nhiều bước |

Khác biệt cốt lõi nằm ở cách mô hình hóa và diễn đạt kết nối. SQL mô tả việc ghép các tập hàng qua điều kiện khóa. Cypher mô tả một mẫu node–relationship cần tìm và hướng duyệt qua các kết nối đó. Cả hai vẫn cần bộ tối ưu truy vấn và chỉ mục phù hợp.

### Ví dụ nhiều bước: tìm bạn diễn của một diễn viên

Giả sử cần tìm những diễn viên từng đóng chung phim với diễn viên có mã `$personId`, đồng thời đếm số phim họ đã cùng tham gia.

Trong SQL, truy vấn phải nối bảng `Casting` hai lần qua cùng bảng `Movie`, sau đó nối tới hai hàng `Person`:

```sql
SELECT co.name, COUNT(DISTINCT m.id) AS shared_movies
FROM Person AS actor
JOIN Casting AS actor_cast ON actor_cast.person_id = actor.id
JOIN Movie AS m ON m.id = actor_cast.movie_id
JOIN Casting AS co_cast ON co_cast.movie_id = m.id
JOIN Person AS co ON co.id = co_cast.person_id
WHERE actor.id = :person_id
  AND co.id <> actor.id
GROUP BY co.id, co.name
ORDER BY shared_movies DESC, co.name;
```

Trong Cypher, đường đi được thể hiện trực tiếp: diễn viên ban đầu đi tới phim, rồi từ phim đi tới diễn viên khác.

```cypher
MATCH (actor:Person {id: $personId})-[:ACTED_IN]->(m:Movie)
      <-[:ACTED_IN]-(coActor:Person)
WHERE coActor <> actor
RETURN coActor.name AS actor,
       count(DISTINCT m) AS sharedMovies
ORDER BY sharedMovies DESC, actor;
```

Đọc mẫu từ trái sang phải: `actor` tham gia `m`, và `coActor` cũng tham gia chính `m`. Điều kiện `coActor <> actor` loại chính diễn viên đang tìm khỏi kết quả. `count(DISTINCT m)` đếm số phim chung, tránh đếm lặp một phim trong trường hợp dữ liệu có nhiều đường khớp tương ứng.

Khi đường đi có nhiều loại quan hệ hoặc độ dài thay đổi, biểu thức mẫu Cypher có thể dễ đọc hơn một chuỗi join dài. Dù vậy, nếu câu hỏi chủ yếu là tổng hợp số liệu trên các cột, truy vấn SQL có thể tự nhiên và hiệu quả hơn. Nên chọn mô hình theo các truy vấn nghiệp vụ quan trọng, không chỉ theo hình thức dữ liệu.

## 4. Ánh xạ node và relationship bằng Spring Data Neo4j

Spring Data Neo4j cung cấp các annotation để ánh xạ mô hình Java vào đồ thị. Ví dụ dưới đây mô hình hóa phim có danh sách lượt casting. Mỗi lượt casting trỏ tới một `Person` và lưu thêm thông tin vai diễn.

```java
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
    private String id;

    private String title;
    private Integer releaseYear;

    @Relationship(
        type = "ACTED_IN",
        direction = Relationship.Direction.INCOMING
    )
    private Set<ActingCredit> cast = new HashSet<>();

    // Constructor, getter và setter được lược bớt.
}

@Node("Person")
public class Person {
    @Id
    private String id;

    private String name;

    // Constructor, getter và setter được lược bớt.
}

@RelationshipProperties
public class ActingCredit {
    @RelationshipId
    private Long id;

    private String character;
    private Integer billingOrder;

    @TargetNode
    private Person actor;

    // Constructor, getter và setter được lược bớt.
}
```

Các annotation có vai trò khác nhau:

- `@Node("Movie")` và `@Node("Person")` khai báo nhãn node tương ứng.
- `@Id` đánh dấu định danh của entity. Ví dụ dùng `String` do ứng dụng cấp; cần bảo đảm giá trị ổn định và duy nhất.
- `@Relationship` khai báo loại relationship và hướng của nó. Vì `ACTED_IN` đi từ `Person` vào `Movie`, thuộc tính `cast` trên `Movie` dùng hướng `INCOMING`.
- `@RelationshipProperties` biến lớp `ActingCredit` thành mô hình relationship có thuộc tính.
- `@TargetNode` xác định node ở đầu kia của relationship; trong ví dụ này là diễn viên.
- `@RelationshipId` là định danh nội bộ mà SDN dùng để nhận diện relationship đã ánh xạ. Đây không phải mã nghiệp vụ của lượt casting.

Tách `ActingCredit` thành một lớp riêng rất hữu ích. Nếu đặt `character` trên `Person`, ta sẽ không thể biểu diễn chính xác trường hợp cùng một diễn viên đóng vai khác nhau ở các phim khác nhau. Nếu đặt nó trên `Movie`, ta cũng không thể gắn đúng tên vai với từng diễn viên. Thuộc tính thuộc về quan hệ giữa hai node nên được đặt trên relationship.

Trong ví dụ, `id` của `Movie` và `Person` là mã do ứng dụng quản lý. Khi ghi dữ liệu, ứng dụng phải cấp mã duy nhất và cơ sở dữ liệu nên có unique constraint tương ứng. Ví dụ Cypher tạo ràng buộc:

```cypher
CREATE CONSTRAINT movie_id_unique IF NOT EXISTS
FOR (m:Movie) REQUIRE m.id IS UNIQUE;

CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person) REQUIRE p.id IS UNIQUE;
```

Ràng buộc giúp bảo vệ tính duy nhất ở tầng dữ liệu, kể cả khi có nhiều luồng hoặc nhiều ứng dụng cùng ghi.

## 5. Repository và truy vấn Cypher trong Spring Data Neo4j

Với thao tác cơ bản, repository có thể kế thừa `Neo4jRepository`:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;

import java.util.List;
import java.util.Optional;

public interface MovieRepository
        extends Neo4jRepository<Movie, String> {

    Optional<Movie> findOneByTitle(String title);

    @Query("""
        MATCH (m:Movie {title: $title})<-[r:ACTED_IN]-(p:Person)
        RETURN p.name AS actor,
               r.character AS character
        ORDER BY actor
        """)
    List<ActorCreditView> findCastByTitle(String title);
}

public interface ActorCreditView {
    String getActor();
    String getCharacter();
}
```

`Neo4jRepository<Movie, String>` cung cấp các thao tác CRUD cho entity `Movie` có kiểu định danh `String`. Phương thức `findOneByTitle` minh họa truy vấn được suy ra từ tên phương thức. Với câu hỏi cần một mẫu đồ thị cụ thể, `@Query` cho phép viết Cypher tường minh.

`ActorCreditView` là projection chỉ chứa hai trường cần hiển thị. Các bí danh `actor` và `character` trong `RETURN` khớp với các getter của projection. Cách này tránh chuyển toàn bộ entity và các quan hệ không cần thiết khi màn hình chỉ cần danh sách diễn viên cùng tên vai.

Một service có thể đặt ranh giới transaction cho thao tác nghiệp vụ:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
public class MovieCatalogService {
    private final MovieRepository movieRepository;

    public MovieCatalogService(MovieRepository movieRepository) {
        this.movieRepository = movieRepository;
    }

    @Transactional(readOnly = true)
    public List<ActorCreditView> getCast(String title) {
        return movieRepository.findCastByTitle(title);
    }
}
```

Các phương thức repository có cơ chế transaction riêng cho thao tác dữ liệu. Đặt `@Transactional` ở service hữu ích khi một nghiệp vụ cần nhiều lần đọc hoặc ghi và các thao tác đó phải thuộc cùng một đơn vị công việc. Với nghiệp vụ ghi cả node lẫn relationship, transaction giúp bảo đảm toàn bộ thay đổi được commit hoặc rollback cùng nhau khi có lỗi. `readOnly = true` diễn đạt ý định của luồng đọc; nó không thay thế việc thiết kế truy vấn chỉ lấy dữ liệu cần thiết.

Khi lưu một `Movie` cùng tập `ActingCredit`, hãy bảo đảm các `Person` đích đã có định danh hợp lệ và được quản lý đúng theo vòng đời entity. Cần kiểm tra hành vi lưu của aggregate trong phiên bản SDN đang dùng, nhất là khi cập nhật một tập relationship lớn hoặc khi entity đích đã tồn tại. Với cập nhật quan hệ phức tạp, một câu Cypher chuyên biệt có thể thể hiện rõ thao tác `MATCH`, `MERGE` và `SET` hơn việc dựng một đồ thị đối tượng lớn trong bộ nhớ.

## 6. Tối ưu truy vấn đồ thị

Duyệt relationship thường phát huy lợi thế khi truy vấn bắt đầu từ một node có thể xác định nhanh rồi đi theo những quan hệ liên quan. Nó không làm mọi truy vấn tự động nhanh hơn. Nếu điểm bắt đầu phải quét toàn bộ node, hoặc một node có số lượng relationship rất lớn, truy vấn vẫn có thể tốn kém.

Một số nguyên tắc thực tế:

1. **Tìm điểm bắt đầu có chọn lọc.** Dùng mã định danh hoặc thuộc tính có chỉ mục để tìm node đầu tiên. Ví dụ, tạo chỉ mục cho tiêu đề phim nếu nghiệp vụ thường tìm theo tiêu đề:

   ```cypher
   CREATE INDEX movie_title_index IF NOT EXISTS
   FOR (m:Movie) ON (m.title);
   ```

   Nếu `title` phải duy nhất theo quy tắc nghiệp vụ, hãy cân nhắc unique constraint thay cho index thông thường. Không nên giả định tiêu đề phim luôn duy nhất nếu dữ liệu có nhiều phiên bản hoặc nhiều thị trường.

2. **Giới hạn phần đồ thị cần duyệt.** Đưa điều kiện lọc vào mẫu `MATCH` hoặc `WHERE` càng sớm càng tốt khi điều kiện đó giúp giảm số kết quả trung gian. Với quan hệ có độ dài thay đổi, đặt giới hạn độ dài đường đi khi nghiệp vụ cho phép; tránh mẫu duyệt không giới hạn trên đồ thị lớn.

3. **Chỉ trả về dữ liệu cần dùng.** Dùng projection hoặc `RETURN` các thuộc tính cụ thể thay vì trả về toàn bộ node và quan hệ nếu giao diện chỉ cần vài trường. Điều này giảm dữ liệu truyền về ứng dụng và khối lượng ánh xạ entity.

4. **Tránh tải toàn bộ đồ thị rồi lọc trong Java.** Để Neo4j thực hiện lọc, đếm và sắp xếp trong Cypher. Ví dụ truy vấn bạn diễn ở trên dùng `count(DISTINCT m)` ngay trong cơ sở dữ liệu.

5. **Đo kế hoạch thực thi.** Dùng `EXPLAIN` để xem kế hoạch mà không chạy truy vấn và `PROFILE` để chạy truy vấn, đo các bước thực tế. Quan sát operator, số hàng đi qua từng bước và `DB Hits`; sau đó điều chỉnh chỉ mục, điểm bắt đầu hoặc mẫu duyệt dựa trên số liệu.

6. **Giữ truy vấn có thể tái sử dụng.** Truyền dữ liệu qua tham số như `$title` và `$personId`. Tránh ghép giá trị đầu vào vào chuỗi Cypher.

Trong Spring Data Neo4j, hãy cân nhắc giữa việc trả về entity và projection. Entity phù hợp khi nghiệp vụ cần làm việc với aggregate và quan hệ đã ánh xạ. Projection phù hợp với truy vấn đọc phục vụ một màn hình hoặc báo cáo chỉ cần một phần dữ liệu. Việc chọn kiểu kết quả đúng giúp giới hạn lượng dữ liệu cần ánh xạ.

## 7. Chọn cách tiếp cận phù hợp

Với ví dụ phim–diễn viên, mô hình đồ thị trở nên tự nhiên khi sản phẩm thường xuyên hỏi về các kết nối: diễn viên nào đóng chung, một chuỗi cộng tác nối hai người ra sao, hoặc các phim liên quan qua nhiều cấp quan hệ. Relationship có thể mang dữ liệu nghiệp vụ như vai diễn, thứ tự credit hoặc thời điểm tham gia.

Mô hình quan hệ vẫn phù hợp khi phần lớn nghiệp vụ là CRUD trên các bản ghi có cấu trúc, báo cáo tổng hợp theo cột, hoặc dữ liệu đã gắn chặt với hệ thống quan hệ hiện có. Nhiều phép `JOIN` không tự nó là lý do đủ để chuyển sang Neo4j; cần xem xét cấu trúc truy vấn, tần suất, quy mô dữ liệu và chi phí vận hành.

Khi dùng Spring Data Neo4j, hãy bắt đầu từ các câu hỏi nghiệp vụ quan trọng, xác định node và relationship tương ứng, rồi kiểm tra xem các entity và repository có biểu đạt đúng mô hình đó hay không. Dùng Cypher cho các mẫu duyệt cần kiểm soát, đặt transaction ở ranh giới nghiệp vụ và đo truy vấn bằng `PROFILE` trước khi kết luận một cách mô hình hóa có hiệu quả hơn.

## 8. Tự kiểm tra

1. Vì sao `character` nên là thuộc tính của `ACTED_IN` thay vì thuộc tính của `Person`?
2. Trong truy vấn Cypher tìm diễn viên của một phim, ký hiệu `<-[r:ACTED_IN]-` thể hiện hướng duyệt nào?
3. Khi tìm diễn viên từng đóng chung phim, vì sao cần loại `coActor` trùng với `actor`?
4. `@RelationshipProperties` và `@TargetNode` phối hợp với nhau như thế nào trong mô hình `ActingCredit`?
5. Khi màn hình chỉ cần tên diễn viên và nhân vật, vì sao projection có thể phù hợp hơn việc trả về toàn bộ entity `Movie`?
6. Hãy dùng `PROFILE` để kiểm tra truy vấn tìm diễn viên theo tiêu đề phim. Bạn sẽ xem những chỉ số hoặc operator nào để đánh giá điểm bắt đầu và số lượng relationship được duyệt?
