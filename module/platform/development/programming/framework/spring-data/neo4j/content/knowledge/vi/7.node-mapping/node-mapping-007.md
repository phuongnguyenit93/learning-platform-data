# Đối chiếu entity với node, label và property thực tế

Khi ứng dụng Spring Data Neo4j (SDN) kết nối với một graph đã có dữ liệu, lớp Java phải khớp với cấu trúc node và relationship đang tồn tại trong Neo4j. Một entity có thể biên dịch thành công nhưng vẫn đọc thiếu dữ liệu, không tìm thấy node hoặc ghi ra label/property khác với schema mà các ứng dụng khác đang sử dụng.

Vì vậy, trước khi khai báo `@Node`, `@Id`, `@Property` và `@Relationship`, hãy khảo sát dữ liệu thực tế, xác định label chính, tên property, định danh và hướng relationship. Sau đó mới ánh xạ các thành phần đó vào Java và kiểm tra bằng truy vấn Cypher. Annotation mô tả cách SDN ánh xạ dữ liệu; chúng không tự sửa hoặc di chuyển dữ liệu đã có trong database.

## 1. Phân biệt mô hình Java và graph đang lưu

Trong SDN, entity là góc nhìn hướng đối tượng của ứng dụng. Node và relationship là cấu trúc dữ liệu thực tế trong Neo4j. Hai phía cần thống nhất về ý nghĩa và tên gọi, nhưng không bắt buộc phải dùng cùng tên trong mã Java.

Ví dụ, graph hiện tại có thể lưu một bộ phim như sau:

```cypher
(:Film {
    movie_id: "M-101",
    title: "The Graph Journey",
    released: 2024
})
```

Ứng dụng có thể dùng lớp Java tên `Movie`, field `id` và `releaseYear`. SDN cần được chỉ dẫn rằng `Movie` ánh xạ vào label `Film`, `id` ánh xạ vào property `movie_id`, còn `releaseYear` ánh xạ vào `released`.

| Trong graph Neo4j | Trong Java | Cách ánh xạ |
| --- | --- | --- |
| Label `Film` | Lớp `Movie` | `@Node("Film")` |
| Property `movie_id` | Field `id` | `@Id` kết hợp `@Property("movie_id")` |
| Property `released` | Field `releaseYear` | `@Property("released")` |
| Relationship `DIRECTED` | Field `directors` trên `Movie` | `@Relationship(type = "DIRECTED", direction = INCOMING)` |
| Relationship `ACTED_IN` có property `role` | Field `cast` | `@RelationshipProperties` và `@TargetNode` |

Đừng giả định tên lớp Java phải trùng label, tên field phải trùng property hoặc tên field relationship phải trùng relationship type. SDN hỗ trợ ánh xạ khác tên thông qua annotation.

## 2. Khảo sát label và property trong Neo4j

Trước khi sửa entity, hãy chạy một số truy vấn đọc để biết graph thực sự đang chứa gì. Truy vấn sau cho thấy label và tập property của một số node:

```cypher
MATCH (n)
RETURN labels(n) AS labels,
       keys(n) AS propertyNames,
       n
LIMIT 20
```

Để xem những label phổ biến và số node tương ứng:

```cypher
MATCH (n)
UNWIND labels(n) AS label
RETURN label, count(*) AS nodeCount
ORDER BY nodeCount DESC
```

Sau khi biết label cần khảo sát, hãy xem các property thực tế trên node thuộc nhóm đó:

```cypher
MATCH (m:Film)
RETURN m.movie_id AS movieId,
       m.title AS title,
       m.released AS released,
       keys(m) AS allProperties
LIMIT 20
```

`keys(m)` giúp nhận biết property đang có trên từng node. Các node cùng label không nhất thiết có tập property giống hệt nhau: một số node có thể thiếu `released`, hoặc có thêm property do ứng dụng khác ghi. Neo4j không lưu property có giá trị `null`; vì vậy, property không xuất hiện có thể biểu thị dữ liệu chưa được cung cấp.

Khảo sát relationship cũng quan trọng như khảo sát node. Truy vấn sau cho biết label ở hai đầu, type và các property của relationship:

```cypher
MATCH (source)-[r]->(target)
RETURN labels(source) AS sourceLabels,
       type(r) AS relationshipType,
       labels(target) AS targetLabels,
       keys(r) AS relationshipProperties
LIMIT 30
```

Ví dụ kết quả có thể cho thấy `Person` nối đến `Film` bằng `DIRECTED`, còn `ACTED_IN` có property `role`. Đây là cơ sở để khai báo `direction` và `@RelationshipProperties` chính xác.

Nếu cần kiểm tra các ràng buộc và index hiện có trong Neo4j 5, có thể dùng:

```cypher
SHOW CONSTRAINTS;
SHOW INDEXES;
```

Các truy vấn khảo sát này chỉ đọc dữ liệu. Không suy ra schema từ một node duy nhất; hãy kiểm tra nhiều node đại diện, các trường hợp thiếu property và những loại relationship thực sự xuất hiện.

## 3. Đối chiếu label với `@Node`

Nếu `@Node` không chỉ định label, SDN dùng simple class name làm primary label. Ví dụ lớp `Movie` mặc định ánh xạ với label `Movie`. Nếu graph đang dùng label `Film`, cần khai báo tường minh:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Property;

@Node("Film")
public class Movie {

    @Id
    @Property("movie_id")
    private String id;

    private String title;

    @Property("released")
    private Integer releaseYear;
}
```

Ở đây, `@Node("Film")` đặt primary label là `Film`, còn tên lớp Java vẫn là `Movie`. Việc chỉ đổi tên lớp Java hoặc chỉ đổi annotation không tự đổi label của các node cũ. Nếu muốn chuyển schema từ `Movie` sang `Film`, cần lập kế hoạch cập nhật dữ liệu, truy vấn, index và constraint tương ứng.

Một node có thể có nhiều label, ví dụ `:Film:Searchable`. Primary label dùng để nhận diện loại entity; label bổ sung có thể thể hiện nhóm hoặc đặc tính chung. Khi ánh xạ một entity, hãy bảo đảm primary label được khai báo đúng với dữ liệu hiện có. Không dùng label bổ sung làm primary chỉ vì nó xuất hiện trên một số node.

Label phân biệt chữ hoa và chữ thường. `Film`, `film` và `FILM` là các label khác nhau. Khi truy vấn không trả kết quả như mong đợi, hãy kiểm tra chính tả và cách viết hoa trong database trước khi thay đổi mapping.

## 4. Đối chiếu property với field Java

Nếu tên property trong Neo4j trùng với tên field Java, SDN có thể ánh xạ theo tên mặc định. Khi hai bên khác nhau, dùng `@Property` để chỉ rõ tên property thực tế.

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Property;

@Node("Film")
public class Movie {

    @Id
    @Property("movie_id")
    private String id;

    private String title; // ánh xạ property title

    @Property("released")
    private Integer releaseYear;

    @Property("original_title")
    private String originalTitle;
}
```

Trong ví dụ:

- `id` đọc và ghi property `movie_id`.
- `title` giữ nguyên tên property `title`.
- `releaseYear` đọc và ghi property `released`.
- `originalTitle` đọc và ghi property `original_title`.

SDN không tự chuyển camelCase thành snake_case. Nếu graph dùng `original_title`, chỉ khai báo field `originalTitle` là chưa đủ; cần `@Property("original_title")`.

Một property có thể vắng mặt trên một số node. Với field kiểu tham chiếu như `Integer`, `String` hoặc `BigDecimal`, ứng dụng có thể nhận `null` khi dữ liệu không tồn tại. Hãy quyết định rõ field nào là tùy chọn và xử lý null ở tầng nghiệp vụ. Nếu property bắt buộc theo quy tắc miền nghiệp vụ, cần xác thực trước khi ghi và cân nhắc ràng buộc phù hợp trong database.

Không khai báo một field Java chỉ vì nó xuất hiện trong một node mẫu. Trước hết hãy xác định ứng dụng có cần dữ liệu đó hay không. Các property không được entity ánh xạ không trở thành field Java một cách tự động. Ngược lại, field được ánh xạ nhưng không có giá trị sẽ không tạo ra property Neo4j mang giá trị `null`.

## 5. Đối chiếu ID và định danh thực tế

`@Id` cho SDN biết field nào là định danh của entity. Field này phải tương ứng với chiến lược định danh đang dùng trong ứng dụng và database.

Nếu graph đã có business key như `movie_id`, có thể ánh xạ trực tiếp:

```java
@Node("Film")
public class Movie {

    @Id
    @Property("movie_id")
    private String id;

    private String title;
}
```

Trước khi chọn business key, kiểm tra rằng giá trị đó thực sự ổn định, có mặt trên các node cần quản lý và không bị trùng. Ví dụ:

```cypher
MATCH (m:Film)
WHERE m.movie_id IS NULL
RETURN count(m) AS missingIds
```

```cypher
MATCH (m:Film)
WHERE m.movie_id IS NOT NULL
WITH m.movie_id AS movieId, count(*) AS occurrences
WHERE occurrences > 1
RETURN movieId, occurrences
ORDER BY occurrences DESC
```

Nếu graph dùng internal ID hoặc một chiến lược sinh ID khác, hãy cấu hình theo cơ chế ID mà phiên bản SDN và ứng dụng đang sử dụng. Không tự coi một property có tên `id` là duy nhất nếu database chưa bảo đảm điều đó. `@Id` là metadata ánh xạ của SDN; để bảo vệ tính duy nhất trước các luồng ghi đồng thời, cần có uniqueness constraint tương ứng trong Neo4j.

Ví dụ tạo constraint cho business key trên Neo4j 5:

```cypher
CREATE CONSTRAINT film_movie_id_unique IF NOT EXISTS
FOR (m:Film)
REQUIRE m.movie_id IS UNIQUE
```

Trước khi tạo constraint, phải xử lý node thiếu ID hoặc trùng ID. Nếu không, lệnh tạo constraint có thể thất bại do dữ liệu hiện hữu vi phạm quy tắc.

## 6. Đối chiếu relationship type và direction

Relationship cần khớp cả type lẫn hướng so với node hiện tại. Giả sử graph lưu:

```cypher
(:Person)-[:DIRECTED]->(:Film)
(:Person)-[:ACTED_IN {role: "Mira"}]->(:Film)
```

Nếu lớp `Movie` đại diện cho node `Film` và có field chứa những người tham gia, relationship đi **vào** node phim. Vì vậy, mapping từ góc nhìn `Movie` cần dùng `INCOMING`:

```java
import java.util.Set;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;
import org.springframework.data.neo4j.core.schema.Relationship.Direction;

@Node("Film")
public class Movie {

    @Id
    @Property("movie_id")
    private String id;

    private String title;

    @Relationship(type = "DIRECTED", direction = Direction.INCOMING)
    private Set<Person> directors;
}
```

Từ `Movie`, SDN đi ngược theo relationship `DIRECTED` để lấy các node `Person` ở đầu nguồn. Nếu field nằm trên `Person` và biểu diễn phim mà người đó đạo diễn, cùng relationship này sẽ là `OUTGOING` từ góc nhìn của `Person`.

Không nên dựa vào tên field `directors` để đoán type hoặc hướng. Hãy nhìn mẫu relationship thực tế trong Cypher và khai báo rõ `type` cùng `direction`. Hướng mặc định của `@Relationship` là `OUTGOING`; nếu graph lưu hướng ngược lại, bỏ qua `direction` có thể làm mapping không đi theo đường liên kết mong muốn.

## 7. Ánh xạ relationship có property

Relationship `ACTED_IN` có property `role`. Đây là dữ liệu của lần một người tham gia một bộ phim, không phải thuộc tính cố định của `Person` hoặc `Film`. SDN dùng `@RelationshipProperties` và `@TargetNode` để ánh xạ kiểu dữ liệu này:

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
}
```

Trong entity `Movie`, khai báo collection relationship theo đúng hướng của graph:

```java
@Relationship(type = "ACTED_IN", direction = Direction.INCOMING)
private Set<ActingCredit> cast;
```

`ActingCredit` mô tả relationship từ `Person` đến `Film`; `actor` là node ở đầu kia khi nhìn từ `Movie`. `@RelationshipId` là metadata định danh relationship do Neo4j quản lý, không phải business key để ứng dụng tự tạo tùy ý.

Nếu relationship thực tế không có property nào, có thể ánh xạ trực tiếp đến entity đích như `Set<Person>`. Nếu có các thuộc tính như `role`, `joinedAt`, `source` hoặc `weight`, hãy xác định chúng mô tả liên kết hay một node riêng. Dữ liệu phụ thuộc vào từng lần kết nối thường phù hợp với relationship properties.

## 8. Một quy trình đối chiếu thực tế

Có thể thực hiện theo thứ tự sau để giảm lỗi mapping:

1. **Chọn nhóm node cần ánh xạ.** Dùng label thực tế để truy vấn một số node đại diện, kể cả node cũ và node mới.
2. **Ghi lại label.** Xác định primary label, label bổ sung và cách viết hoa chính xác.
3. **Lập danh sách property.** Ghi tên, kiểu dữ liệu, mức độ bắt buộc và tỷ lệ node có property đó.
4. **Xác minh định danh.** Kiểm tra null, trùng lặp và uniqueness constraint hiện có.
5. **Khảo sát relationship.** Ghi type, hướng, label ở hai đầu và property trên relationship.
6. **Khai báo annotation.** Dùng `@Node`, `@Id`, `@Property`, `@Relationship` và `@RelationshipProperties` theo schema đã xác nhận.
7. **Đọc thử.** Tìm một entity theo ID và kiểm tra field, label, relationship được ánh xạ đúng.
8. **Ghi thử trong môi trường kiểm thử.** Lưu entity rồi truy vấn lại bằng Cypher để so sánh node/relationship thực tế với ý định ban đầu.
9. **Kiểm tra constraint và index.** Bảo đảm các truy vấn quan trọng có ràng buộc dữ liệu và kế hoạch thực thi phù hợp.

Một bảng mapping nhỏ giúp đội phát triển và người quản trị database cùng kiểm tra:

| Thành phần | Graph hiện tại | Entity SDN | Kết quả cần xác minh |
| --- | --- | --- | --- |
| Primary label | `Film` | `@Node("Film")` trên `Movie` | Đọc đúng node phim |
| ID | `movie_id` | `@Id @Property("movie_id")` trên `id` | Tìm đúng entity, không trùng ID |
| Tên phim | `title` | `title` | Giá trị đọc/ghi nhất quán |
| Năm phát hành | `released` | `@Property("released")` trên `releaseYear` | Đúng tên và kiểu dữ liệu |
| Đạo diễn | `DIRECTED`, `Person -> Film` | `@Relationship(..., INCOMING)` | Duyệt đúng hướng |
| Vai diễn | `ACTED_IN` có `role` | `ActingCredit` | Property thuộc relationship |

## 9. Xác minh mapping bằng Cypher

Sau khi đọc entity bằng repository hoặc service, hãy kiểm tra dữ liệu thật bằng Cypher. Ví dụ, kiểm tra một node phim:

```cypher
MATCH (m:Film {movie_id: $movieId})
RETURN labels(m) AS labels,
       properties(m) AS properties
```

Kiểm tra các đạo diễn và diễn viên cùng relationship properties:

```cypher
MATCH (p:Person)-[r:DIRECTED|ACTED_IN]->(m:Film {movie_id: $movieId})
RETURN p.person_id AS personId,
       type(r) AS relationshipType,
       properties(r) AS relationshipProperties
```

Kết quả Cypher giúp phân biệt lỗi mapping với lỗi dữ liệu. Nếu Cypher không tìm thấy node, hãy kiểm tra label và ID thực tế. Nếu Cypher tìm thấy node nhưng entity thiếu field, kiểm tra tên property, kiểu dữ liệu và annotation. Nếu node đúng nhưng collection relationship rỗng, kiểm tra type, direction và label ở hai đầu.

## 10. Lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra hoặc xử lý |
| --- | --- | --- |
| Repository không tìm thấy node | Primary label mặc định khác label thực tế | Khảo sát `labels(n)` và khai báo `@Node` tường minh |
| ID không khớp hoặc không tìm được entity | `@Id` ánh xạ sai property, ID null hoặc trùng | Kiểm tra property ID và constraint |
| Field Java luôn null | Tên property không trùng field hoặc dữ liệu thực sự không có | Dùng `keys(n)`, `properties(n)` và `@Property` |
| Field không được ghi vào đúng key | Thiếu alias property hoặc schema dùng quy ước tên khác | Khai báo `@Property` rõ ràng |
| Relationship không được ánh xạ | Sai type, direction hoặc label ở đầu kia | Kiểm tra mẫu `(source)-[r:TYPE]->(target)` |
| Relationship properties bị thiếu | Ánh xạ trực tiếp sang node đích dù relationship có dữ liệu riêng | Dùng `@RelationshipProperties` và `@TargetNode` |
| Ghi dữ liệu tạo label/property mới ngoài dự kiến | Annotation không khớp schema hiện tại | Đối chiếu metadata trước khi lưu và sửa mapping |
| Một số entity có field null | Property không tồn tại trên các node đó | Xác định field có thực sự bắt buộc và xử lý null |

## 11. Annotation không thay thế migration schema

Một lỗi dễ gặp khi tích hợp graph có sẵn là sửa annotation rồi kỳ vọng dữ liệu tự đổi theo. Ví dụ, đổi `@Node("Movie")` thành `@Node("Film")` không có nghĩa tất cả node `Movie` cũ tự động được gắn label `Film`. Tương tự, đổi `@Property("release_year")` thành `@Property("released")` không tự di chuyển property đã lưu.

Nếu cần đổi schema, hãy thực hiện migration có kế hoạch:

- Xác định node và relationship cần chuyển đổi bằng Cypher.
- Kiểm tra dữ liệu thiếu, trùng hoặc xung đột trước khi cập nhật.
- Chuyển label/property bằng migration script hoặc quy trình triển khai dữ liệu có kiểm soát.
- Cập nhật index, constraint, truy vấn Cypher và tất cả ứng dụng cùng dùng graph.
- Kiểm tra số lượng node, relationship và dữ liệu sau migration.
- Chỉ chuyển ứng dụng sang mapping mới sau khi schema đã sẵn sàng.

`@Id`, `@Node` và các annotation mapping không tự tạo uniqueness constraint hoặc index theo ý nghĩa nghiệp vụ. Hãy quản lý constraint và index bằng công cụ migration/schema phù hợp với dự án. Không sửa dữ liệu production chỉ để làm cho một entity mẫu đọc được; trước hết phải xác nhận thay đổi có đúng với graph schema và các ứng dụng khác không.

## Kết luận

Để entity SDN phản ánh đúng node thực tế, hãy khảo sát label, property, ID và relationship trực tiếp trong Neo4j trước khi khai báo annotation. Dùng `@Node` để chỉ định label, `@Id` và `@Property` để ánh xạ định danh cùng tên property, `@Relationship` để khớp type và direction, và `@RelationshipProperties` khi liên kết có dữ liệu riêng. Cuối cùng, xác minh bằng cả truy vấn Cypher và thao tác đọc/ghi của ứng dụng. Khi graph schema thay đổi, thực hiện migration dữ liệu có kiểm soát thay vì chỉ đổi annotation Java.
