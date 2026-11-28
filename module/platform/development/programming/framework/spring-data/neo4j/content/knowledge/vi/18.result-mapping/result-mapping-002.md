# Yêu cầu một record chứa đủ dữ liệu cho một entity gốc

Bài học này thuộc chương **Ánh xạ kết quả** của module **SPRING_DATA_NEO4J**. Khi viết custom query bằng `@Query`, Spring Data Neo4j không chỉ cần biết node nào là kết quả. Framework còn cần các relationship và node liên quan để dựng entity graph theo metadata. Vì SDN xử lý kết quả theo từng record, hình dạng result set quyết định việc graph được ánh xạ có đầy đủ hay không.

Quy tắc quan trọng là: **mỗi entity gốc cần được biểu diễn bằng một record chứa đủ dữ liệu của entity đó và các quan hệ cần hydrate**. Nếu một truy vấn trả nhiều record lặp lại cùng node gốc, mỗi record chỉ mang một phần relationship, SDN không tự động hợp nhất các record đó thành một entity graph hoàn chỉnh. Với quan hệ một-nhiều, thường cần dùng `collect()` để gom relationship và các node ở đầu còn lại vào cùng record.

## 1. Entity gốc và record kết quả

Giả sử mô hình có một bộ phim và nhiều diễn viên. Relationship `ACTED_IN` đi từ `Person` đến `Movie`:

```text
(Person:An)-[:ACTED_IN {roles: ['Neo']}]->(Movie:The Matrix)
(Person:Bình)-[:ACTED_IN {roles: ['Trinity']}]->(Movie:The Matrix)
(Person:Chi)-[:ACTED_IN {roles: ['Morpheus']}]->(Movie:The Matrix)
```

Khi truy vấn bộ phim `The Matrix`, `Movie` là **entity gốc** cần được ánh xạ. Các `Person` và relationship `ACTED_IN` là dữ liệu liên quan để điền vào graph của `Movie`.

Ví dụ entity rút gọn:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;
import org.springframework.data.neo4j.core.schema.Relationship.Direction;

@Node("Movie")
public class Movie {

    @Id
    private String title;

    @Relationship(type = "ACTED_IN", direction = Direction.INCOMING)
    private List<ActorCredit> cast = new ArrayList<>();
}
```

Lớp relationship properties chứa dữ liệu của cạnh và node diễn viên ở đầu còn lại:

```java
import java.util.List;

import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class ActorCredit {

    @RelationshipId
    private Long id;

    private List<String> roles;

    @TargetNode
    private Person actor;
}
```

Vì `ACTED_IN` là relationship `INCOMING` so với `Movie`, `@TargetNode` trong `ActorCredit` trỏ tới `Person` ở đầu nguồn của relationship. Một `Movie` có thể có nhiều phần tử `ActorCredit` trong `cast`.

## 2. Vấn đề khi mỗi relationship tạo ra một record

Truy vấn đơn giản sau tìm bộ phim và từng diễn viên:

```cypher
MATCH (m:Movie {title: $title})<-[r:ACTED_IN]-(p:Person)
RETURN m, r, p;
```

Nếu phim có ba diễn viên, result set có thể chứa ba record:

| Record | `m` | `r` | `p` |
|---|---|---|---|
| 1 | The Matrix | ACTED_IN / Neo | An |
| 2 | The Matrix | ACTED_IN / Trinity | Bình |
| 3 | The Matrix | ACTED_IN / Morpheus | Chi |

Node `m` lặp lại ở cả ba record. Mỗi record chỉ có một relationship và một node liên quan. Vì SDN xử lý theo record, framework không thể mặc định gom ba phần kết quả này thành một `Movie` duy nhất với đầy đủ ba phần tử `cast`. Nếu ánh xạ kết quả thành danh sách, có thể xuất hiện các bản sao của root hoặc graph chỉ được hydrate một phần.

Đây là vấn đề hình dạng kết quả, không phải do `List<ActorCredit>` hay `Set<ActorCredit>` trong entity. Thay collection Java không giải quyết được việc một root node bị lặp qua nhiều record.

## 3. Dùng collect() để tạo một record cho root

Hãy gom các relationship và node liên quan bằng `collect()`:

```cypher
MATCH (m:Movie {title: $title})<-[r:ACTED_IN]-(p:Person)
RETURN m, collect(r) AS actingRelationships, collect(p) AS actors;
```

Thay vì ba record, truy vấn trả một record:

| `m` | `actingRelationships` | `actors` |
|---|---|---|
| The Matrix | `[r1, r2, r3]` | `[An, Bình, Chi]` |

Một record lúc này chứa node gốc cùng tập relationship và node đích cần thiết để SDN dựng collection `cast`. `collect(r)` giữ các relationship, bao gồm thuộc tính `roles`; `collect(p)` cung cấp các node ở đầu còn lại. Khi ánh xạ relationship properties, cần trả cả relationship và các node liên quan, không chỉ trả node gốc.

### Ánh xạ qua repository

Ví dụ repository trả về một `Movie` cùng dàn diễn viên:

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface MovieRepository extends Neo4jRepository<Movie, String> {

    @Query("""
        MATCH (m:Movie {title: $title})<-[r:ACTED_IN]-(p:Person)
        RETURN m, collect(r), collect(p)
        """)
    Optional<Movie> findWithCastByTitle(@Param("title") String title);
}
```

`Optional.empty()` biểu thị không tìm thấy phim. Khi có kết quả, record chứa `m`, danh sách relationship và danh sách node liên quan để SDN ánh xạ vào `Movie` cùng `cast`.

## 4. Giữ lại root khi không có relationship

Truy vấn dùng `MATCH` bắt buộc phải tìm được relationship. Nếu phim chưa có diễn viên, toàn bộ kết quả có thể biến mất dù node `Movie` vẫn tồn tại.

Dùng `OPTIONAL MATCH` nếu cần trả root ngay cả khi không có relationship:

```cypher
MATCH (m:Movie {title: $title})
OPTIONAL MATCH (m)<-[r:ACTED_IN]-(p:Person)
RETURN m, collect(r) AS actingRelationships, collect(p) AS actors;
```

`OPTIONAL MATCH` giữ lại `m` khi không có diễn viên. Trong trường hợp đó, các giá trị null từ nhánh không khớp bị `collect()` bỏ qua, tạo collection rỗng. Kết quả vẫn có một record cho phim và hai collection rỗng.

Phân biệt hai trường hợp:

- Không tìm thấy `Movie`: không có record, repository trả `Optional.empty()`.
- Tìm thấy `Movie` nhưng không có `ACTED_IN`: có một record, `collect(r)` và `collect(p)` rỗng.

## 5. Một record cho mỗi root khi truy vấn nhiều root

Quy tắc này không có nghĩa toàn bộ truy vấn chỉ được trả về đúng một record. Nếu truy vấn cần trả nhiều phim, hãy tạo một record cho mỗi phim. Cypher gom kết quả theo các biểu thức không tổng hợp trong `RETURN`; khi trả node `m` cùng các biểu thức `collect()`, mỗi `m` trở thành một nhóm:

```cypher
MATCH (m:Movie)
OPTIONAL MATCH (m)<-[r:ACTED_IN]-(p:Person)
RETURN m, collect(r) AS actingRelationships, collect(p) AS actors;
```

Nếu có 20 phim phù hợp, kết quả có thể có 20 record, mỗi record đại diện một `Movie` và chứa đầy đủ tập relationship `ACTED_IN` của phim đó. Điều cần tránh là nhiều record cho cùng một root.

Hãy giữ node gốc trong `RETURN` để SDN nhận diện entity cần hydrate. Tránh thêm các giá trị không tổng hợp thay đổi theo từng relationship vào `RETURN`, vì chúng có thể chia một root thành nhiều nhóm. Nếu cần hiển thị thêm scalar theo từng relationship, hãy cân nhắc đưa scalar vào projection riêng hoặc gom chúng thành collection tương ứng.

## 6. Tránh tích Descartes khi có nhiều nhánh relationship

Một root có thể có nhiều loại quan hệ, chẳng hạn phim có diễn viên và đạo diễn. Nếu nối hai nhánh độc lập trong cùng một truy vấn:

```cypher
MATCH (m:Movie {title: $title})<-[acted:ACTED_IN]-(actor:Person)
MATCH (m)<-[directed:DIRECTED]-(director:Person)
RETURN m,
       collect(acted), collect(actor),
       collect(directed), collect(director);
```

Giả sử phim có 5 diễn viên và 2 đạo diễn. Hai nhánh có thể tạo 5 × 2 = 10 dòng trung gian. Khi đó, mỗi relationship diễn viên bị lặp theo số đạo diễn và mỗi relationship đạo diễn bị lặp theo số diễn viên. Chỉ thêm `collect()` ở cuối có thể giữ lại các bản sao trong collection.

Có thể dùng `collect(DISTINCT ...)` để loại bản sao, nhưng truy vấn vẫn tạo tích các dòng trung gian. Cách rõ ràng hơn là gom từng nhánh độc lập trong một subquery tương quan:

```cypher
MATCH (m:Movie {title: $title})
CALL {
    WITH m
    OPTIONAL MATCH (m)<-[r:ACTED_IN]-(actor:Person)
    RETURN collect(r) AS actingRelationships,
           collect(actor) AS actors
}
CALL {
    WITH m
    OPTIONAL MATCH (m)<-[r:DIRECTED]-(director:Person)
    RETURN collect(r) AS directingRelationships,
           collect(director) AS directors
}
RETURN m,
       actingRelationships, actors,
       directingRelationships, directors;
```

Mỗi subquery nhận root `m`, xử lý một loại relationship và trả về các collection đã gom. Vì từng nhánh được tổng hợp riêng, số diễn viên không nhân với số đạo diễn. Record cuối cùng chứa một `Movie` cùng các collection của từng nhánh.

Khi dùng cú pháp `CALL { ... }`, cần bảo đảm phiên bản Neo4j hỗ trợ cú pháp subquery được sử dụng. Với truy vấn đơn giản chỉ có một nhánh relationship, `OPTIONAL MATCH` kết hợp `collect()` thường đã đủ.

## 7. Relationship properties cần cả cạnh và node đầu còn lại

Nếu entity dùng `@RelationshipProperties`, collection không chỉ chứa node đích. Nó còn chứa dữ liệu nằm trên cạnh. Ví dụ:

```text
(Person:An)-[:ACTED_IN {roles: ['Neo']}]->(Movie:The Matrix)
```

Để ánh xạ `ActorCredit`, truy vấn phải cung cấp:

- `m`: node gốc `Movie`.
- `r`: relationship `ACTED_IN` với property `roles`.
- `p`: node `Person` ở đầu còn lại.

Ví dụ:

```cypher
MATCH (m:Movie {title: $title})<-[r:ACTED_IN]-(p:Person)
RETURN m, collect(r), collect(p);
```

Chỉ trả `m` và `collect(p)` sẽ không cung cấp relationship object cùng thuộc tính cạnh. Chỉ trả `m` và `collect(r)` cũng không đủ node liên quan để hydrate `@TargetNode` một cách đầy đủ. Hãy trả cả hai tập dữ liệu tương ứng.

## 8. Ánh xạ graph sâu hơn một cấp

Ví dụ trước chỉ tải diễn viên của phim. Nhưng nếu mỗi diễn viên còn có những phim khác, graph cần hydrate có thể sâu hơn:

```text
(The Matrix)<-[:ACTED_IN]-(An)-[:ACTED_IN]->(John Wick)
             <-[:ACTED_IN]-(Bình)-[:ACTED_IN]->(Speed)
```

Truy vấn theo path có thể tìm nhiều nhánh:

```cypher
MATCH path = (m:Movie {title: $title})
             <-[:ACTED_IN]-(:Person)
             -[:ACTED_IN*0..]->(:Movie)
RETURN path;
```

Tuy nhiên, Spring Data Neo4j không ánh xạ trực tiếp giá trị `PATH` thành entity graph theo cách thông thường. Cần trích xuất node và relationship từ path rồi đưa chúng vào record.

### Gom path và để SDN làm phẳng ở phía client

```cypher
MATCH path = (m:Movie {title: $title})
             <-[:ACTED_IN]-(:Person)
             -[:ACTED_IN*0..]->(:Movie)
RETURN m,
       collect(nodes(path)) AS pathNodes,
       collect(relationships(path)) AS pathRelationships;
```

`collect(nodes(path))` và `collect(relationships(path))` tạo cấu trúc danh sách lồng nhau, ví dụ `[[node1, node2], [node1, node3]]`. Spring Data Neo4j hỗ trợ làm phẳng các danh sách lồng nhau của node và relationship trong quá trình mapping. Cách này chuyển một tập path thành một record chứa root và các node/relationship cần thiết.

### Giảm path ở phía database

Nếu muốn loại trùng trước khi trả kết quả, có thể gom path rồi dùng `reduce()` để tạo danh sách node và relationship duy nhất:

```cypher
MATCH path = (m:Movie {title: $title})
             <-[:ACTED_IN]-(:Person)
             -[:ACTED_IN*0..]->(:Movie)
WITH m, collect(path) AS paths
WITH m,
     reduce(allNodes = [], p IN paths |
         reduce(acc = allNodes, n IN nodes(p) |
             CASE WHEN n IN acc THEN acc ELSE acc + n END
         )
     ) AS uniqueNodes,
     reduce(allRels = [], p IN paths |
         reduce(acc = allRels, r IN relationships(p) |
             CASE WHEN r IN acc THEN acc ELSE acc + r END
         )
     ) AS uniqueRelationships
RETURN m, uniqueRelationships, uniqueNodes;
```

Cả hai cách đều cần cân nhắc kích thước graph. Database-side reduction tạo và xử lý các path trong bộ nhớ Neo4j; client-side reduction có thể chuyển nhiều dữ liệu hơn về ứng dụng và tăng mức dùng bộ nhớ phía client. Chọn theo số lượng path và kích thước dữ liệu thực tế.

### Khi cần trả tất cả node trong các path

Nếu mục tiêu là trả về tất cả entity xuất hiện trong các path, không chỉ hydrate một root, có thể trả trực tiếp các path:

```cypher
MATCH path = (root:SomeEntity {number: $number})
             -[:SOME_RELATION_TO*]-(:SomeEntity)
RETURN path;
```

Đây là trường hợp khác với truy vấn chỉ muốn trả một root cùng các nhánh quan hệ. Các path có thể xuất hiện thành nhiều record, mỗi path liên kết các node trong graph; SDN có thể populate và trả về các node liên quan theo kết quả path. Hãy chọn dạng kết quả dựa trên mục tiêu: hydrate một entity gốc hay trả danh sách mọi entity trên các đường đi.

## 9. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Root entity xuất hiện lặp | Mỗi relationship tạo một record có cùng root | Gom relationship và node liên quan bằng `collect()` |
| Collection relationship bị thiếu phần tử | Query chỉ trả một phần cạnh trong mỗi record | Trả đủ relationship và node đích trong một record cho root |
| Root biến mất khi không có quan hệ | Dùng `MATCH` bắt buộc trên nhánh relationship | Dùng `OPTIONAL MATCH` rồi `collect()` |
| Collection có phần tử trùng | Nhiều nhánh relationship tạo tích Descartes | Gom từng nhánh bằng subquery hoặc dùng `DISTINCT` khi phù hợp |
| `@RelationshipProperties` không có target node | Query chỉ trả relationship mà thiếu node đầu còn lại | Trả cả relationship và node liên quan |
| Không ánh xạ được path thành entity | Trả `PATH` trong khi mapping cần node và relationship | Dùng `nodes(path)` và `relationships(path)` rồi gom chúng |
| Root được hydrate nhưng không có các entity sâu | Query chỉ thu thập một cấp quan hệ | Xác định graph cần tải và gom các node/cạnh ở các cấp tiếp theo |

## 10. Quy trình thiết kế custom query cho entity graph

Trước khi viết `@Query`, hãy xác định rõ hình dạng dữ liệu cần trả:

1. **Chọn root node.** Xác định entity nào là kết quả chính của repository method.
2. **Liệt kê relationship cần hydrate.** Ghi rõ type, direction, node đầu còn lại và property trên relationship.
3. **Kiểm tra số record theo root.** Mỗi root cần đúng một record sau bước tổng hợp.
4. **Gom các nhánh quan hệ.** Dùng `collect(r)` và `collect(p)`; với nhiều nhánh độc lập, cân nhắc subquery để tránh tích Descartes.
5. **Giữ root khi quan hệ không tồn tại.** Dùng `OPTIONAL MATCH` nếu phương thức cần trả entity ngay cả khi collection rỗng.
6. **Xử lý graph sâu.** Trích xuất node và relationship từ path; chọn giảm dữ liệu ở database hoặc client.
7. **Kiểm tra record shape.** Dùng dữ liệu có 0, 1 và nhiều relationship; xác nhận một record cho mỗi root và các collection không bị thiếu hoặc trùng.

## 11. Kiểm thử kết quả ánh xạ

Nên kiểm thử bằng Neo4j Test Harness hoặc Testcontainers với dữ liệu đại diện. Một bộ kiểm thử nên có:

- Một root không có relationship, để xác nhận `OPTIONAL MATCH` giữ root và collection rỗng.
- Một root có một relationship, để kiểm tra trường hợp đơn giản.
- Một root có nhiều relationship cùng type, để xác nhận `collect()` trả đủ cạnh và node đích.
- Nhiều root, để xác nhận mỗi root chỉ xuất hiện một lần trong result set.
- Hai nhánh relationship độc lập, để phát hiện tích Descartes và phần tử lặp.
- Relationship có properties, để xác nhận thuộc tính cạnh và `@TargetNode` được hydrate.
- Graph có nhiều cấp path, để kiểm tra danh sách node và relationship sâu hơn.

Ngoài việc xác nhận số lượng entity, hãy kiểm tra identity, property của relationship, node ở đầu còn lại và các cạnh trong graph sau mapping. Một kết quả có đúng số lượng root nhưng thiếu relationship vẫn là kết quả không hợp lệ đối với domain model.

## 12. Nguyên tắc cần nhớ

- Spring Data Neo4j xử lý custom query theo record; không tạo nhiều record cho cùng một root rồi kỳ vọng framework tự hợp nhất chúng.
- Với quan hệ một-nhiều, dùng `collect()` để gom relationship và node liên quan thành một record cho root.
- Trả cả relationship và node ở đầu còn lại khi ánh xạ `@RelationshipProperties`.
- Dùng `OPTIONAL MATCH` khi cần giữ root dù không có relationship.
- Khi có nhiều nhánh quan hệ, tránh tích Descartes; tổng hợp từng nhánh độc lập nếu phù hợp.
- Để ánh xạ graph sâu, trích xuất `nodes(path)` và `relationships(path)`; không giả định SDN ánh xạ trực tiếp `PATH` thành entity graph.
- Nếu muốn trả mọi entity trên path, xác định rõ đây là use case khác với hydrate một root duy nhất.
- Luôn kiểm tra số record, collection và identity bằng integration test.

Một custom query tốt không chỉ tìm đúng node. Nó phải trả dữ liệu theo hình dạng mà Spring Data Neo4j có thể ánh xạ chính xác. Giữ một record đầy đủ cho mỗi entity gốc giúp framework dựng đúng relationship graph, tránh root trùng, tránh thiếu cạnh và giữ cho repository trả về object graph phù hợp với domain model.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.2.0 – Custom queries](https://docs.spring.io/spring-data/neo4j/reference/8.2/appendix/custom-queries.html)
- [Spring Data Neo4j – Custom queries and custom mappings](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
- [Neo4j Cypher Manual – Aggregating functions](https://neo4j.com/docs/cypher-manual/current/functions/aggregating/)
- [Neo4j Cypher Manual – Subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/)
