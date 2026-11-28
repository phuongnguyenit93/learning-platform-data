# Giới hạn điều kiện lồng nhau, collection và truy vấn relationship

Query by Example (QBE) giúp tạo truy vấn từ một đối tượng mẫu (*probe*) mà không phải viết Cypher cho các điều kiện đơn giản. Tuy nhiên, probe không phải là một bộ mô tả đầy đủ cho mọi biểu thức graph. Khi điều kiện đi sâu qua nhiều relationship, kiểm tra phần tử bên trong collection hoặc cần nhóm logic `AND`/`OR` phức tạp, QBE có giới hạn cần hiểu rõ.

Bài học thuộc module **SPRING_DATA_NEO4J**, tập trung xây dựng tầng dữ liệu đồ thị qua node entity, relationship, repository và Cypher. Ví dụ dùng `Person`, `Movie`, thuộc tính danh sách `genres` và relationship `ACTED_IN` để phân biệt property lồng nhau, collection lưu trên node và collection node liên kết trong graph.

## 1. QBE biểu diễn điều gì?

QBE có bốn thành phần chính:

- **Probe:** đối tượng mẫu chứa các giá trị muốn dùng làm điều kiện.
- **ExampleMatcher:** quy định cách so khớp, xử lý null, bỏ qua property và cấu hình riêng cho từng property.
- **Example:** kết hợp probe với matcher để tạo yêu cầu tìm kiếm.
- **Fluent query:** cho phép bổ sung sort, limit, projection, page hoặc slice khi thực thi.

Với repository SDN, có thể dùng `findAll(Example)` hoặc `findBy(Example, queryFunction)` khi repository hỗ trợ `QueryByExampleExecutor`.

Ví dụ đơn giản:

```java
Person probe = new Person();
probe.setName("Keanu Reeves");

Example<Person> example = Example.of(probe);
List<Person> people = personRepository.findAll(example);
```

Probe ở đây có một property được đặt là `name`; các property tham chiếu khác vẫn `null` và mặc định bị bỏ qua. QBE tạo điều kiện theo giá trị của probe và quy tắc mặc định của store.

## 2. Các quy tắc mặc định ảnh hưởng đến probe

QBE mặc định chỉ đưa các property có giá trị vào điều kiện. Property `null` thường bị bỏ qua. Các kiểu primitive như `int`, `long` hoặc `boolean` luôn có giá trị mặc định (`0`, `false`), nên có thể vô tình trở thành điều kiện nếu không được bỏ qua rõ ràng.

| Giá trị trong probe | Hành vi mặc định thường gặp |
|---|---|
| `name = "Keanu"` | Đưa điều kiện so khớp tên vào query |
| `born = null` với `Integer` | Bỏ qua property `born` |
| `born = 1964` | So khớp giá trị số chính xác |
| `active = false` với `boolean` | Giá trị primitive vẫn được xem là điều kiện |
| `tags = null` | Bỏ qua property `tags` |

Với các trường tìm kiếm tùy chọn, nên dùng wrapper như `Integer`, `Long`, `Boolean` thay vì primitive để biểu diễn được trạng thái “không lọc theo trường này”. Nếu entity có field không thuộc điều kiện tìm kiếm như ID hoặc relationship collection, hãy loại trừ nó bằng `withIgnorePaths(...)`.

Ví dụ:

```java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnorePaths("id", "actedIn");

Example<Person> example = Example.of(probe, matcher);
```

Điều này giúp probe tập trung vào các property scalar cần tìm, tránh việc vô tình đưa ID hoặc quan hệ vào điều kiện.

## 3. Property lồng nhau và điều kiện logic lồng nhau là hai việc khác nhau

Tài liệu QBE cho phép cấu hình matcher theo property path, ví dụ `address.city`, nếu mô hình và store hỗ trợ property path đó. Điều này có nghĩa ta có thể chỉ định cách so khớp cho một property con.

```java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withMatcher("address.city", match -> match.startsWith().ignoreCase());
```

Tuy nhiên, khả năng chỉ định matcher cho một property path không có nghĩa QBE hỗ trợ mọi cấu trúc điều kiện lồng nhau. QBE không cung cấp bộ dựng tổng quát cho biểu thức logic như:

```text
name = 'Keanu'
OR (born = 1964 AND status = 'ACTIVE')
```

`matching()` kết hợp các điều kiện được khai báo theo kiểu AND; `matchingAny()` kết hợp các điều kiện thành OR ở cùng một mức. QBE không biểu diễn trực tiếp nhóm ngoặc tùy ý như `(A OR B) AND (C OR D)`, hoặc một nhóm con `A OR (B AND C)`.

Vì vậy, cần phân biệt:

- **Property path:** đường dẫn tới property được mapping, ví dụ `address.city`, nếu được hỗ trợ.
- **Nhóm logic:** cách kết hợp nhiều predicate bằng ngoặc, AND và OR tùy ý. Đây là khả năng QBE bị giới hạn.

Trong SDN, một field `@Relationship` trỏ tới node khác là quan hệ graph. Không nên mặc định nó tương đương một object value lồng nhau như `address.city`; truy vấn đi qua relationship cần được kiểm tra riêng và thường nên diễn đạt bằng Cypher khi cần kiểm soát rõ.

## 4. matching() và matchingAny() không tạo được nhóm ngoặc tùy ý

`ExampleMatcher.matching()` là chế độ mặc định: các property có giá trị trong probe phải cùng khớp. Ví dụ:

```java
Person probe = new Person();
probe.setName("Keanu Reeves");
probe.setBorn(1964);

Example<Person> example = Example.of(
    probe,
    ExampleMatcher.matching()
);
```

Ý nghĩa gần tương đương:

```cypher
MATCH (p:Person)
WHERE p.name = 'Keanu Reeves'
  AND p.born = 1964
RETURN p;
```

`matchingAny()` yêu cầu khớp ít nhất một trong các điều kiện có trong probe:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAny();
Example<Person> example = Example.of(probe, matcher);
```

Ý nghĩa gần tương đương:

```cypher
MATCH (p:Person)
WHERE p.name = 'Keanu Reeves'
   OR p.born = 1964
RETURN p;
```

Không thể dùng một probe duy nhất để biểu diễn chính xác biểu thức `name = ? OR (born = ? AND status = ?)` vì matcher chỉ chọn cách kết hợp chung cho các điều kiện, không cho định nghĩa các nhóm con độc lập.

Khi yêu cầu nghiệp vụ có nhóm logic lồng nhau, hãy chuyển sang `@Query` với Cypher rõ ràng hoặc xây dựng truy vấn động bằng `Neo4jClient`.

## 5. Collection property trên node khác với collection relationship

Trong mô hình Neo4j, cần phân biệt hai loại collection:

1. **Collection property:** một property dạng mảng trên node, ví dụ `genres: ["Sci-Fi", "Action"]` hoặc `tags: ["award-winning", "classic"]`.
2. **Collection relationship:** danh sách node liên kết qua relationship, ví dụ `Person.actedIn` chứa nhiều `Movie` qua `ACTED_IN`.

Hai loại collection có ngữ nghĩa lưu trữ khác nhau. QBE không phải công cụ tổng quát để diễn đạt mọi phép kiểm tra phần tử, lượng từ hoặc traversal trên collection.

| Trường hợp | Ví dụ | Câu hỏi cần diễn đạt |
|---|---|---|
| Scalar property | `Movie.title` | Tiêu đề bằng hoặc chứa chuỗi nào? |
| Collection property | `Movie.genres` | Danh sách có đúng bằng mẫu hay có chứa một phần tử? |
| Relationship collection | `Person.actedIn` | Người đó có liên kết tới phim nào? |
| Relationship properties | `ACTED_IN.roles` | Cạnh có vai diễn cụ thể nào? |

QBE có thể phù hợp với các điều kiện property đơn giản. Khi cần hỏi “collection có chứa phần tử X không?”, “có ít nhất một relationship thỏa điều kiện không?” hoặc “mọi phần tử đều thỏa điều kiện?”, Cypher thể hiện rõ hơn và tránh nhầm phép so khớp chính xác với phép kiểm tra thành viên.

## 6. Collection property: không nhầm so khớp toàn bộ với chứa phần tử

Giả sử `Movie` có một property danh sách `genres`:

```java
@Node("Movie")
public class Movie {

    @Id
    @GeneratedValue
    private Long id;

    private String title;
    private List<String> genres;
}
```

Một probe có `genres = List.of("Sci-Fi")` không nên được hiểu mặc định là “tìm mọi phim có chứa genre Sci-Fi”. Đó là hai yêu cầu khác nhau:

- **So khớp collection:** so sánh giá trị collection theo khả năng mapping và quy tắc của store.
- **Kiểm tra membership:** tìm node mà một phần tử trong collection bằng giá trị cần tìm.

Để tìm phim có chứa một genre, Cypher diễn đạt trực tiếp:

```cypher
MATCH (m:Movie)
WHERE $genre IN m.genres
RETURN m
ORDER BY m.title;
```

Để yêu cầu phim có cả hai genre:

```cypher
MATCH (m:Movie)
WHERE 'Sci-Fi' IN m.genres
  AND 'Action' IN m.genres
RETURN m;
```

Để yêu cầu có ít nhất một trong hai genre:

```cypher
MATCH (m:Movie)
WHERE 'Sci-Fi' IN m.genres
   OR 'Action' IN m.genres
RETURN m;
```

Các phép `IN`, AND và OR trên cho thấy rõ semantics của collection. Nếu cần exact matching toàn bộ property collection bằng QBE, hãy xác minh hành vi của phiên bản SDN và kiểu property cụ thể; đừng dùng nó thay cho membership query.

## 7. Relationship collection: probe không phải truy vấn traversal tổng quát

Xét entity `Person` có nhiều phim đã tham gia:

```java
@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
    private Integer born;

    @Relationship(type = "ACTED_IN", direction = Direction.OUTGOING)
    private List<Movie> actedIn = new ArrayList<>();
}
```

`actedIn` không phải một property mảng chuỗi trên node `Person`; nó biểu diễn các relationship tới node `Movie`. Khi tạo probe:

```java
Person probe = new Person();
probe.setName("Keanu Reeves");
```

QBE phù hợp để tìm theo các property scalar như `name` và `born`. Nếu muốn dùng probe này để yêu cầu “Person đã tham gia một Movie có title chứa Matrix”, đó là điều kiện traversal qua `ACTED_IN`, không phải một phép so khớp scalar đơn giản trên node gốc.

Với probe chỉ tìm theo thông tin người, nên bỏ qua relationship collection:

```java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnorePaths("id", "actedIn");

Example<Person> example = Example.of(probe, matcher);
List<Person> people = personRepository.findAll(example);
```

Không nên đặt một `Movie` mẫu vào `actedIn` rồi giả định QBE sẽ tự tạo pattern `(:Person)-[:ACTED_IN]->(:Movie)` với các điều kiện tùy ý trên node đích. Hợp đồng QBE chung không cung cấp bộ dựng graph traversal, cardinality và quantifier cho collection relationship.

## 8. Truy vấn relationship bằng Cypher khi cần chính xác

Nếu yêu cầu là tìm người tham gia một phim có tiêu đề chứa chuỗi đầu vào, hãy viết pattern rõ ràng:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WHERE toLower(m.title) CONTAINS toLower($titlePart)
RETURN DISTINCT p
ORDER BY p.name;
```

`DISTINCT p` quan trọng vì một người có thể khớp nhiều phim và xuất hiện trên nhiều dòng trung gian. Truy vấn trả về mỗi người một lần.

Có thể khai báo trong repository:

```java
public interface PersonRepository extends Neo4jRepository<Person, Long> {

    @Query("""
        MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
        WHERE toLower(m.title) CONTAINS toLower($titlePart)
        RETURN DISTINCT p
        ORDER BY p.name
        """)
    List<Person> findActorsForMovieTitle(String titlePart);
}
```

Đây là truy vấn chuyên biệt cho relationship. Nếu entity `Person` cần materialize thêm các relationship khác, hãy kiểm tra dữ liệu được trả về và yêu cầu mapping của SDN; truy vấn custom phải cung cấp cấu trúc phù hợp với kiểu kết quả mà repository khai báo.

## 9. Kết hợp nhiều điều kiện động trên node và relationship

Một màn hình tìm kiếm có thể có các trường tùy chọn: tên người, năm sinh, tiêu đề phim và vai diễn. Đây là điều kiện phức tạp hơn một probe QBE đơn giản vì có nhiều nguồn dữ liệu và có thể cần logic `EXISTS`.

Ví dụ Cypher với tham số tùy chọn:

```cypher
MATCH (p:Person)
WHERE ($namePart IS NULL
       OR toLower(p.name) CONTAINS toLower($namePart))
  AND ($born IS NULL OR p.born = $born)
  AND ($moviePart IS NULL OR EXISTS {
      MATCH (p)-[credit:ACTED_IN]->(m:Movie)
      WHERE toLower(m.title) CONTAINS toLower($moviePart)
  })
  AND ($role IS NULL OR EXISTS {
      MATCH (p)-[credit:ACTED_IN]->(:Movie)
      WHERE $role IN credit.roles
  })
RETURN p
ORDER BY p.name, p.personId;
```

Truy vấn trên:

- Bỏ qua điều kiện tên nếu `namePart` là `null`.
- Bỏ qua điều kiện năm sinh nếu `born` là `null`.
- Dùng `EXISTS` để kiểm tra có ít nhất một relationship `ACTED_IN` dẫn tới phim phù hợp.
- Dùng `EXISTS` thứ hai để kiểm tra có ít nhất một credit chứa vai diễn cần tìm.
- Trả về mỗi node `Person` một lần vì mỗi node gốc chỉ xuất hiện một lần từ `MATCH (p:Person)`; các relationship được kiểm tra bên trong `EXISTS`.

Ví dụ minh họa cách thể hiện điều kiện động bằng Cypher; trong repository thật, khai báo các tham số tương ứng và xác thực giá trị đầu vào ở service. Nếu `credit.roles` có thể `null`, biểu thức `$role IN credit.roles` không khớp khi property không có giá trị.

## 10. Trường hợp nested property path

QBE và `ExampleMatcher` có thể nhận property path như `address.city` để cấu hình cách so khớp một property con trong mô hình có mapping tương ứng:

```java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withMatcher("address.city", match -> match.contains().ignoreCase());
```

Điều này không đồng nghĩa mọi object lồng nhau hoặc mọi quan hệ graph đều được hỗ trợ tự động. Cần xác định `address` trong mô hình Java được SDN ánh xạ như loại property nào:

- Nếu là một cấu trúc property được mapping hỗ trợ, property path có thể dùng được tùy phiên bản và kiểu dữ liệu.
- Nếu `address` là node liên kết qua `@Relationship`, điều kiện `address.city` thực chất cần traversal qua relationship.
- Nếu cần nhiều bước relationship, nhiều nhánh hoặc điều kiện trên property của cạnh, hãy dùng Cypher tường minh.

Không nên chỉ nhìn cú pháp `address.city` trong ExampleMatcher rồi kết luận QBE hỗ trợ mọi nested graph query.

## 11. Khi nào QBE phù hợp, khi nào nên chuyển sang Cypher?

| Yêu cầu | QBE | Cypher / @Query |
|---|---|---|
| Tìm `Person` theo tên chính xác | Phù hợp | Có thể dùng nhưng thường không cần |
| Tìm chuỗi bắt đầu/kết thúc/chứa | Phù hợp nếu matcher và store hỗ trợ | Dùng khi cần điều khiển hàm và collation rõ ràng |
| Kết hợp các property scalar bằng AND | Phù hợp | Có thể dùng |
| Kết hợp các property scalar bằng OR cùng mức | `matchingAny()` | Có thể dùng |
| Biểu thức `(A OR B) AND C` | Không biểu diễn trực tiếp | Phù hợp |
| Kiểm tra một phần tử nằm trong property array | Không có toán tử membership tổng quát qua probe | Phù hợp với `IN` |
| Tìm qua `ACTED_IN` tới `Movie` | Không nên dựa vào probe collection | Phù hợp với `MATCH` hoặc `EXISTS` |
| Kiểm tra property của relationship | Không phải use case QBE đơn giản | Phù hợp với biến relationship trong Cypher |
| Nhiều bước traversal và aggregation | Không phù hợp | Phù hợp |

Một quy tắc thực tế: dùng QBE khi điều kiện chủ yếu là các property đơn giản của entity gốc và cách kết hợp là AND/OR cùng mức. Dùng Cypher khi câu hỏi bắt đầu nói về “có ít nhất một”, “tất cả”, “không có”, “trên relationship nào”, hoặc các nhóm điều kiện có ngoặc.

## 12. Kiểm soát QBE bằng Fluent API

Sau khi tạo `Example`, fluent API cho phép sắp xếp, giới hạn, phân trang hoặc chiếu kết quả:

```java
Example<Person> example = Example.of(
    probe,
    ExampleMatcher.matching()
        .withIgnorePaths("id", "actedIn")
        .withMatcher("name", match -> match.contains().ignoreCase())
);

Page<PersonSummary> page = personRepository.findBy(
    example,
    query -> query
        .as(PersonSummary.class)
        .page(PageRequest.of(0, 20, Sort.by("name").ascending()))
);
```

Fluent API giúp xử lý kết quả QBE, nhưng không mở rộng khả năng biểu diễn predicate. `page`, `sortBy`, `limit`, `as` và `project` điều khiển cách lấy/trả kết quả; chúng không biến QBE thành một bộ dựng truy vấn Cypher tổng quát cho nested group hoặc graph traversal.

## 13. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng primitive cho trường tìm kiếm tùy chọn | Giá trị mặc định như `0` hoặc `false` trở thành điều kiện | Dùng wrapper hoặc bỏ qua path rõ ràng |
| Quên ignore ID hoặc relationship collection | Probe vô tình ràng buộc thêm property không mong muốn | Dùng `withIgnorePaths(...)` |
| Hiểu `matchingAny()` là nhóm OR tùy ý | Không tạo được biểu thức logic có ngoặc | Dùng Cypher cho nhóm điều kiện phức tạp |
| Dùng `address.city` và nghĩ rằng mọi relationship đều được duyệt | Nhầm property path với graph traversal | Kiểm tra mapping; dùng `MATCH` nếu là relationship |
| Đặt `List<String>` vào probe để tìm một phần tử | Có thể thành so khớp collection thay vì membership | Dùng Cypher `$value IN n.listProperty` |
| Đặt `List<Movie>` vào probe để tìm phim liên quan | Mong đợi semantics traversal/any/all không được QBE đảm bảo | Dùng `EXISTS { MATCH ... }` |
| Bỏ `DISTINCT` khi MATCH qua relationship | Một entity gốc có thể xuất hiện nhiều lần | Dùng `RETURN DISTINCT root` hoặc `EXISTS` |
| Dùng QBE cho điều kiện property của relationship | Không biểu đạt rõ property cạnh và hướng cạnh | Dùng pattern Cypher có biến relationship |
| Cho rằng fluent API khắc phục giới hạn predicate | Query vẫn bị giới hạn ở biểu thức QBE | Chuyển sang `@Query` hoặc `Neo4jClient` |

## 14. Checklist trước khi chọn QBE

- Xác định các điều kiện nằm trên property của node gốc hay trên node/relationship liên quan.
- Dùng wrapper cho filter tùy chọn; tránh primitive có giá trị mặc định không mong muốn.
- Xác định AND hay OR cùng mức; nếu cần nhóm ngoặc, chuyển sang Cypher.
- Phân biệt property path lồng nhau với traversal qua `@Relationship`.
- Phân biệt collection property dạng array với collection relationship.
- Không giả định QBE có toán tử contains-element, any/all hoặc relationship existence.
- Bỏ qua ID và relationship fields khỏi probe nếu chúng không phải điều kiện tìm kiếm.
- Kiểm tra hành vi string matcher theo SDN version và store.
- Dùng `DISTINCT` hoặc `EXISTS` khi truy vấn graph có nguy cơ nhân bản node gốc.
- Kiểm thử với entity không có relationship, collection rỗng/null và nhiều relationship cùng khớp.

## 15. Bài tập thực hành

1. Tạo probe `Person` chỉ có `name`; tìm người bằng `Example.of(probe)`.
2. Thêm `born` kiểu `Integer`, dùng `matching()` và giải thích vì sao kết quả phải thỏa cả tên lẫn năm sinh.
3. Dùng `matchingAny()` và so sánh với `matching()`.
4. Thêm field `actedIn` dạng `List<Movie>`; dùng `withIgnorePaths("actedIn")` để chỉ tìm theo property của người.
5. Tạo `Movie.genres` dạng `List<String>`; viết Cypher tìm phim có chứa một genre bằng toán tử `IN`.
6. Viết truy vấn tìm `Person` có ít nhất một relationship `ACTED_IN` tới phim có tiêu đề chứa chuỗi đầu vào bằng `EXISTS`.
7. Viết biểu thức `(name CONTAINS ? OR born = ?) AND status = 'ACTIVE'`; giải thích vì sao QBE không thể mô tả nhóm ngoặc này bằng một matcher.
8. Viết lại yêu cầu trên bằng `@Query` và tham số có tên.
9. So sánh `RETURN p` với `RETURN DISTINCT p` khi một người tham gia nhiều phim.
10. Dùng Fluent API để phân trang một Example scalar và chỉ ra phần nào của query được điều khiển bởi fluent API.

Khi hoàn thành, bạn cần phân biệt được property lồng nhau với nhóm logic lồng nhau, collection property với collection relationship, và điều kiện scalar với graph traversal. QBE giúp tạo nhanh truy vấn đơn giản từ probe; khi nghiệp vụ cần kiểm tra phần tử trong collection hoặc điều kiện trên relationship, Cypher cho phép mô tả chính xác node, cạnh, hướng và logic cần tìm.

## Tài liệu tham khảo

- [Spring Data Neo4j — Query by Example](https://docs.spring.io/spring-data/neo4j/reference/query-by-example.html)
- [Spring Data Neo4j — Custom queries and relationships](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
- [Spring Data Commons — Query by Example](https://docs.spring.io/spring-data/commons/reference/repositories/query-by-example.html)
