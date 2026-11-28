# Đường đi ngắn và truy vấn nhiều bước có giới hạn

Trong graph, một quan hệ thường chỉ là một bước trên đường đi giữa hai node. Muốn tìm người có thể kết nối với một người khác qua bạn bè của bạn bè, hoặc tìm tuyến gồm ít chặng nhất giữa hai địa điểm, truy vấn phải đi qua nhiều relationship. Cypher hỗ trợ đường đi có độ dài biến đổi, đường đi ngắn nhất và các mẫu đường đi có giới hạn số bước.

Spring Data Neo4j (SDN) cho phép đưa những truy vấn này vào repository bằng `@Query`, rồi ánh xạ kết quả thành entity, projection hoặc DTO. Việc giới hạn độ sâu và chọn đúng kiểu kết quả giúp truy vấn dễ dự đoán, giảm lượng dữ liệu truyền về ứng dụng và tránh mở rộng graph quá mức.

## 1. Mô hình ví dụ

Giả sử ứng dụng có các node `Person`, kết nối với nhau bằng relationship `KNOWS`:

```text
(An)-[:KNOWS]->(Binh)-[:KNOWS]->(Chi)
  \                         /
   \------[:KNOWS]----------/
```

Mỗi người có mã duy nhất `code`, tên `name` và trạng thái `status`. Relationship có thể có thuộc tính `active` để biểu thị kết nối còn hiệu lực.

Entity tối thiểu:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {
    @Id
    private String code;

    private String name;
    private String status;

    protected Person() {
    }

    public String getCode() { return code; }
    public String getName() { return name; }
    public String getStatus() { return status; }
}
```

Constraint giúp Neo4j định danh nhanh node nguồn và đích:

```cypher
CREATE CONSTRAINT person_code_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.code IS UNIQUE;
```

Các ví dụ dùng mã `code` làm điểm neo. Trong hệ thống thật, cần chọn constraint/index phù hợp với thuộc tính định danh hoặc thuộc tính tìm kiếm thường dùng.

## 2. Đường đi cố định và đường đi có độ dài biến đổi

Đường đi cố định chỉ định rõ số relationship:

```cypher
MATCH (a:Person {code: $sourceCode})-[:KNOWS]->(b:Person)
MATCH (b)-[:KNOWS]->(c:Person)
RETURN c;
```

Mẫu này đi đúng hai bước `KNOWS`. Nếu độ dài có thể thay đổi, có thể dùng quantified relationship:

```cypher
MATCH p = (source:Person {code: $sourceCode})
          -[:KNOWS]->{1,3}
          (target:Person)
RETURN target, p, length(p) AS hops;
```

`{1,3}` nghĩa là lặp relationship pattern từ một đến ba lần. Truy vấn trả về các node `Person` có thể tiếp cận từ nguồn trong tối đa ba bước theo chiều `KNOWS`.

Các dạng lượng hóa thường gặp:

| Quantifier | Ý nghĩa |
|---|---|
| `+` | Một hoặc nhiều lần lặp trong quantified relationship hiện đại |
| `*` | Không hoặc nhiều lần lặp trong quantified relationship hiện đại |
| `{1,3}` | Từ một đến ba lần lặp |
| `{2,5}` | Từ hai đến năm lần lặp |
| `{0,4}` | Có thể không đi bước nào, hoặc đi tối đa bốn bước |
| `{3}` | Chính xác ba lần lặp |

Nếu phải đi qua ít nhất một relationship, dùng cận dưới `1`. Cận dưới `0` cho phép đường đi rỗng khi node nguồn cũng là node đích; điều này có thể làm kết quả khác với ý nghĩa nghiệp vụ “phải có kết nối”.

## 3. Quantified relationships và cú pháp variable-length cũ

Cypher hiện đại hỗ trợ quantified relationships, ví dụ:

```cypher
MATCH p = (source:Person {code: $sourceCode})
          -[:KNOWS]->{1,4}
          (target:Person)
RETURN target, length(p) AS hops;
```

Đây là cách viết ngắn cho một relationship pattern được lặp lại. Cypher cũng hỗ trợ quantified path patterns khi mỗi bước gồm nhiều node/relationship hoặc cần điều kiện trên các node trung gian.

Các phiên bản trước thường dùng variable-length relationship:

```cypher
MATCH p = (source:Person {code: $sourceCode})
          -[:KNOWS*1..4]->
          (target:Person)
RETURN target, length(p) AS hops;
```

`[:KNOWS*1..4]` vẫn được hỗ trợ để tương thích với truy vấn cũ, nhưng quantified relationships là cú pháp GQL-conformant được khuyến nghị cho truy vấn mới. Quantified relationship đặt số lần lặp sau toàn bộ relationship pattern; variable-length cũ đặt dấu `*` và giới hạn bên trong dấu ngoặc vuông. Lưu ý `*` không kèm giới hạn trong variable-length relationship cũ mặc định có cận dưới là một, còn `*` trong quantified relationship hiện đại có nghĩa là không hoặc nhiều lần lặp.

Path selectors dạng từ khóa `SHORTEST` được giới thiệu từ Neo4j 5.21. Nếu ứng dụng chạy Neo4j cũ hơn, dùng `shortestPath()` hoặc `allShortestPaths()` với variable-length relationship và kiểm tra cú pháp theo phiên bản server.

## 4. Giới hạn hướng và loại relationship

Hướng relationship quyết định những cạnh nào được phép đi qua:

```cypher
// Chỉ đi theo chiều outgoing KNOWS.
MATCH p = (source:Person {code: $sourceCode})-[:KNOWS]->{1,3}(target:Person)
RETURN target, p;
```

```cypher
// Chỉ đi theo chiều incoming KNOWS.
MATCH p = (source:Person {code: $sourceCode})<-[:KNOWS]-{1,3}(target:Person)
RETURN target, p;
```

```cypher
// Đi theo cả hai chiều của KNOWS.
MATCH p = (source:Person {code: $sourceCode})-[:KNOWS]-{1,3}(target:Person)
RETURN target, p;
```

Chỉ bỏ arrowhead khi nghiệp vụ thực sự xem quan hệ là hai chiều. Nếu `FOLLOWS` là quan hệ có hướng, chuyển nó thành pattern không hướng có thể làm xuất hiện những đường đi không hợp lệ.

Có thể cho phép nhiều loại relationship:

```cypher
MATCH p = (source:Person {code: $sourceCode})
          -[:KNOWS|COLLEAGUE]-{1,3}
          (target:Person)
RETURN target, p;
```

Giới hạn loại relationship giúp graph traversal tránh đi qua những quan hệ không thuộc nghiệp vụ đang truy vấn.

## 5. Tìm một đường đi ngắn nhất với SHORTEST

Path selector `SHORTEST k` chọn tối đa `k` đường đi ngắn nhất theo số relationship trong mỗi cặp node đầu-cuối:

```cypher
MATCH p = SHORTEST 1
          (source:Person {code: $sourceCode})
          -[:KNOWS]-{1,8}
          (target:Person {code: $targetCode})
RETURN p, length(p) AS hops;
```

Trong ví dụ, `SHORTEST 1` trả về một đường đi có ít relationship nhất từ người nguồn tới người đích, giới hạn tối đa tám bước. Nếu không có đường đi thỏa mãn, truy vấn không trả về dòng nào.

Độ dài của path được đo bằng số relationship, không phải tổng trọng số của relationship. Nếu có nhiều đường đi cùng độ dài ngắn nhất, `SHORTEST 1` chỉ chọn một trong số đó; không nên dựa vào thứ tự ổn định giữa các đường đi đồng hạng.

## 6. Chọn tất cả đường đi đồng hạng ngắn nhất

Nếu cần tất cả các đường đi có cùng độ dài ngắn nhất, dùng `ALL SHORTEST`:

```cypher
MATCH p = ALL SHORTEST
          (source:Person {code: $sourceCode})
          -[:KNOWS]-{1,8}
          (target:Person {code: $targetCode})
RETURN p, length(p) AS hops;
```

Ví dụ, có thể có hai đường đi đều gồm ba relationship. `ALL SHORTEST` trả cả hai. Số đường đi đồng hạng có thể tăng nhanh trong graph nhiều nhánh, do đó chỉ dùng khi ứng dụng thật sự cần toàn bộ kết quả.

Các selector liên quan:

| Selector | Ý nghĩa |
|---|---|
| `SHORTEST 1` | Một đường đi ngắn nhất |
| `SHORTEST k` | Tối đa k đường đi đầu tiên theo độ dài; việc chọn giữa các đường đi đồng hạng không có thứ tự bảo đảm |
| `ALL SHORTEST` | Tất cả đường đi đồng hạng ngắn nhất |
| `SHORTEST k GROUPS` | Các đường đi thuộc k nhóm độ dài ngắn nhất; mỗi nhóm gồm các đường đi có cùng độ dài |
| `ANY` hoặc `ANY k` | Một hoặc k đường đi bất kỳ, không cam kết ngắn nhất |

`SHORTEST 2 GROUPS` không có nghĩa là chỉ trả hai đường đi. Nó trả các đường đi thuộc hai nhóm độ dài ngắn nhất; mỗi nhóm có thể chứa nhiều đường đi.

## 7. Khác biệt giữa SHORTEST và shortestPath()

Trước khi có path selector dạng từ khóa, Cypher dùng hai hàm:

- `shortestPath(pattern)` tương tự `SHORTEST 1`.
- `allShortestPaths(pattern)` tương tự `ALL SHORTEST`.

Ví dụ cú pháp cũ:

```cypher
MATCH p = shortestPath(
    (source:Person {code: $sourceCode})
    -[:KNOWS*1..8]-
    (target:Person {code: $targetCode})
)
RETURN p, length(p) AS hops;
```

Hai hàm cũ vẫn được hỗ trợ, nhưng không tuân thủ GQL. Pattern truyền vào hàm bị giới hạn ở một relationship pattern variable-length; cận dưới độ dài nên là `0` hoặc `1`. Không truyền quantified path pattern hoặc ghép thêm relationship pattern thứ hai bên trong hàm.

Với truy vấn mới trên Neo4j hỗ trợ path selector, ưu tiên `SHORTEST` và `ALL SHORTEST`. Khi cần tương thích server cũ, dùng hàm legacy và giới hạn pattern theo quy tắc của nó.

## 8. Lọc cạnh trước khi chọn đường đi ngắn nhất

Một điểm dễ nhầm là vị trí của điều kiện `WHERE`. Với path selector, predicate đặt trong graph pattern có thể được áp dụng trước khi chọn đường đi; predicate ở `WHERE` cấp `MATCH` được áp dụng sau bước chọn path.

Ví dụ cần tìm đường đi ngắn nhất chỉ qua các quan hệ còn hiệu lực:

```cypher
MATCH p = SHORTEST 1
          (source:Person {code: $sourceCode})
          ((a:Person)-[r:KNOWS]->(b:Person) WHERE r.active = true){1,8}
          (target:Person {code: $targetCode})
RETURN p, length(p) AS hops;
```

Điều kiện `r.active = true` nằm bên trong quantified path pattern nên mỗi lần lặp chỉ chấp nhận relationship đang hoạt động; các cạnh không hoạt động bị loại trước khi chọn đường đi ngắn nhất.

Nếu viết điều kiện ở graph `WHERE`:

```cypher
MATCH p = SHORTEST 1
          (source:Person {code: $sourceCode})
          -[:KNOWS]-{1,8}
          (target:Person {code: $targetCode})
WHERE all(r IN relationships(p) WHERE r.active = true)
RETURN p;
```

Đây là post-filter. Cypher chọn đường đi ngắn nhất trước rồi mới kiểm tra tất cả relationship có hoạt động hay không. Nếu đường ngắn nhất chứa một cạnh inactive, truy vấn có thể trả về không có kết quả dù vẫn tồn tại đường dài hơn chỉ đi qua cạnh active.

Khi yêu cầu nghiệp vụ là “đường đi ngắn nhất thỏa điều kiện”, hãy đặt điều kiện ngay trong node/relationship pattern hoặc parenthesized path pattern để nó trở thành pre-filter. Không mặc định rằng mọi `WHERE` đều được áp dụng trước khi chọn shortest path.

## 9. Lọc node trung gian trong quantified path pattern

Khi cần điều kiện trên các node trung gian, quantified path pattern cho phép đặt predicate tại node pattern lặp lại:

```cypher
MATCH p = SHORTEST 1
          (source:Person {code: $sourceCode})
          ((a:Person)-[:KNOWS]->(b:Person WHERE b.status = 'ACTIVE')){1,6}
          (target:Person {code: $targetCode})
RETURN p, length(p) AS hops;
```

Predicate `b.status = 'ACTIVE'` thuộc pattern được lặp lại nên chỉ các đường đi có node đích của từng bước ở trạng thái ACTIVE mới được xét. Cách này phù hợp khi mọi node trung gian phải thỏa một quy tắc, chẳng hạn tài khoản chưa bị khóa hoặc địa điểm đang mở.

Quantified path pattern có thể biểu diễn một bước gồm nhiều node và relationship. Quantified relationship ngắn gọn hơn khi chỉ một relationship pattern được lặp lại. Chọn cú pháp đơn giản nhất thể hiện đúng graph traversal cần thực hiện.

## 10. Truy vấn tất cả node trong phạm vi N bước

Không phải lúc nào bài toán cũng cần đường đi ngắn nhất. Đôi khi chỉ cần tìm mọi người có thể tiếp cận trong tối đa ba bước:

```cypher
MATCH (source:Person {code: $sourceCode})
      -[:KNOWS]->{1,3}
      (target:Person)
WHERE target.status = 'ACTIVE'
RETURN DISTINCT target.code AS code,
       target.name AS name
ORDER BY name;
```

Truy vấn này trả về node đích ở khoảng cách một, hai hoặc ba relationship. `DISTINCT` loại bỏ một người có thể được tiếp cận qua nhiều đường đi khác nhau.

Nếu cần biết số bước ngắn nhất để tới từng node, có thể dùng path selector theo từng cặp nguồn/đích:

```cypher
MATCH p = SHORTEST 1
          (source:Person {code: $sourceCode})
          -[:KNOWS]-{1,3}
          (target:Person)
RETURN target.code AS code,
       target.name AS name,
       length(p) AS minHops
ORDER BY minHops, name;
```

Path selection được phân vùng theo từng cặp node đầu-cuối. Khi có nhiều node đích phù hợp, truy vấn có thể trả đường đi ngắn nhất cho từng cặp nguồn/đích, không phải chỉ một đường đi toàn cục tới một node đích bất kỳ. Sau đó `ORDER BY` có thể sắp xếp các node theo khoảng cách.

## 11. Kết hợp nhiều bước graph trong cùng truy vấn

Một truy vấn có thể thực hiện traversal giới hạn rồi tiếp tục đi sang loại node khác. Ví dụ tìm công ty nơi những người trong mạng lưới ba bước đang làm việc:

```cypher
MATCH (source:Person {code: $sourceCode})
      -[:KNOWS]->{1,3}
      (candidate:Person)
WHERE candidate.status = 'ACTIVE'
WITH DISTINCT candidate
MATCH (candidate)-[:WORKS_AT]->(company:Company)
RETURN DISTINCT company.code AS code,
       company.name AS name
ORDER BY name
LIMIT $limit;
```

`WITH DISTINCT candidate` thu gọn kết quả traversal trước khi tiếp tục match relationship `WORKS_AT`. Điều này giúp tránh nhân bản kết quả khi một công ty có nhiều nhân viên nằm trong mạng lưới.

Có thể nối nhiều pattern qua `WITH`, dùng aggregation, lọc và sắp xếp ở từng giai đoạn. Tuy nhiên, mỗi lần mở rộng graph nên có mục đích rõ ràng, loại relationship và giới hạn độ sâu phù hợp.

## 12. Đưa truy vấn vào Spring Data Neo4j repository

SDN hỗ trợ custom Cypher qua `@Query`. Với truy vấn trả entity đầy đủ, repository có thể trả về `Person`. Với truy vấn chỉ trả một vài thuộc tính hoặc thêm thông tin như số bước, nên dùng DTO projection.

Repository:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (source:Person {code: $sourceCode})
              -[:KNOWS]->{1,3}
              (target:Person)
        WHERE target.status = 'ACTIVE'
        RETURN DISTINCT target.code AS code,
               target.name AS name
        ORDER BY name
        """)
    List<ReachablePerson> findActivePeopleWithinThreeHops(
        @Param("sourceCode") String sourceCode
    );

    @Query("""
        MATCH p = SHORTEST 1
                  (source:Person {code: $sourceCode})
                  -[:KNOWS]-{1,8}
                  (target:Person {code: $targetCode})
        RETURN target.code AS targetCode,
               target.name AS targetName,
               length(p) AS hops
        """)
    Optional<PathSummary> findShortestPath(
        @Param("sourceCode") String sourceCode,
        @Param("targetCode") String targetCode
    );
}
```

DTO projection cho danh sách node tiếp cận được:

```java
public record ReachablePerson(String code, String name) {
}
```

DTO projection cho đường đi ngắn nhất:

```java
public record PathSummary(
    String targetCode,
    String targetName,
    Long hops
) {
}
```

Tên alias trong `RETURN` cần khớp với tên thuộc tính DTO. Khi không có đường đi, method trả `Optional.empty()`. Kiểu số của `length(p)` có thể được chuyển đổi sang `Long` trong DTO.

SDN hỗ trợ interface-based và DTO-based projection. Với custom query, DTO linh hoạt hơn khi cần thêm thuộc tính tính toán như `hops`. Tránh trả về một entity domain chỉ có một phần property/relationship rồi dùng chính object đó cho lệnh ghi toàn phần; SDN coi domain mapping là mô hình đầy đủ và dữ liệu bị thiếu có thể bị ghi đè hoặc xóa khi lưu lại.

## 13. Trả về danh sách mã node trên đường đi

Nếu UI chỉ cần hiển thị tuyến đi, có thể trả một danh sách mã thay vì toàn bộ graph entity:

```cypher
MATCH p = SHORTEST 1
          (source:Person {code: $sourceCode})
          -[:KNOWS]-{1,8}
          (target:Person {code: $targetCode})
RETURN [n IN nodes(p) | n.code] AS route,
       length(p) AS hops;
```

DTO:

```java
import java.util.List;

public record PathCodes(List<String> route, Long hops) {
}
```

Danh sách `nodes(p)` có cả node đầu và node cuối. Nếu path có ba relationship thì danh sách node thường có bốn phần tử. `relationships(p)` trả các relationship theo thứ tự trên path; có thể dùng để lấy loại quan hệ hoặc thuộc tính từng chặng.

## 14. Đường đi ngắn nhất không đồng nghĩa chi phí thấp nhất

Cypher path selector `SHORTEST` tối ưu theo số relationship. Nó không tự cộng thuộc tính `cost`, `distance` hoặc `travelTime` của các cạnh.

Ví dụ có hai đường đi:

| Đường đi | Số relationship | Tổng thời gian |
|---|---:|---:|
| A → B → D | 2 | 90 phút |
| A → C → E → D | 3 | 25 phút |

`SHORTEST 1` chọn đường hai bước A → B → D, mặc dù đường ba bước nhanh hơn về thời gian.

Nếu cần tối ưu theo trọng số dương như khoảng cách, thời gian hoặc chi phí, cân nhắc Neo4j Graph Data Science (GDS), ví dụ Dijkstra hoặc A*. Các thuật toán GDS hỗ trợ cấu hình relationship weight property. Chúng yêu cầu graph projection và GDS library tương thích với phiên bản Neo4j triển khai.

Ví dụ khái quát với Dijkstra trên named graph đã được project:

```cypher
MATCH (source:Station {code: $sourceCode}),
      (target:Station {code: $targetCode})
CALL gds.shortestPath.dijkstra.stream('transportGraph', {
    sourceNode: id(source),
    targetNode: id(target),
    relationshipWeightProperty: 'travelTime'
})
YIELD totalCost, path
RETURN totalCost, path;
```

`transportGraph` phải được tạo trước và chứa đúng node/relationship cần tính toán. `travelTime` là property trọng số trên relationship trong named graph. Chọn thuật toán theo ý nghĩa trọng số, quy mô graph và yêu cầu về đường đi; không dùng `SHORTEST` nếu nghiệp vụ đang hỏi tổng chi phí nhỏ nhất.

## 15. Tối ưu hiệu năng truy vấn nhiều bước

Traversal có thể mở rộng rất nhanh. Nếu mỗi node có trung bình 10 relationship phù hợp, số đường đi tiềm năng có thể tăng theo cấp số nhân khi độ sâu tăng. Một vài nguyên tắc giúp kiểm soát:

1. Neo node nguồn và đích bằng label cùng property có index/unique constraint.
2. Đặt giới hạn hop rõ ràng thay vì dùng độ dài không giới hạn.
3. Chọn đúng chiều và loại relationship.
4. Đặt predicate ngay trong pattern khi muốn loại node/relationship trước khi chọn path.
5. Chỉ trả property hoặc node cần thiết, tránh trả toàn bộ path nếu UI chỉ cần DTO.
6. Dùng `DISTINCT` sau traversal khi một node có thể được tiếp cận qua nhiều đường khác nhau.
7. Cân nhắc `SHORTEST 1` thay cho `ALL SHORTEST` nếu chỉ cần một tuyến.
8. Giới hạn số đích và số kết quả; tránh tìm mọi path trong graph lớn.
9. Dùng `PROFILE` để xem số row, số DB hits và operator thực tế.

Cypher planner thường có thể dùng bidirectional breadth-first search hiệu quả khi xác định được một cặp node nguồn/đích cụ thể. Nếu truy vấn tạo ra nhiều cặp nguồn/đích tiềm năng, planner có thể phải tìm đường đi cho nhiều cặp, làm chi phí tăng. Neo node đầu/cuối càng sớm càng tốt và kiểm tra query plan thay vì dựa vào phỏng đoán.

Ví dụ kiểm tra kế hoạch:

```cypher
PROFILE
MATCH p = SHORTEST 1
          (source:Person {code: $sourceCode})
          -[:KNOWS]-{1,8}
          (target:Person {code: $targetCode})
RETURN length(p) AS hops;
```

Kiểm tra index seek cho node đầu/cuối, số row trước khi shortest-path operator chạy và số DB hits. Nếu planner quét nhiều node, xem lại constraint/index và độ chọn lọc của điều kiện đầu vào.

## 16. Quy tắc về node và relationship lặp lại

Trong path matching thông thường, Cypher không cho một relationship xuất hiện lặp lại trong cùng một path. Tuy nhiên, node có thể xuất hiện nhiều lần; vì vậy đường đi có thể chứa chu trình nếu pattern cho phép.

Giới hạn số bước vẫn quan trọng ngay cả khi relationship không được lặp lại. Một graph có nhiều nhánh vẫn có thể tạo ra số lượng path lớn. Nếu nghiệp vụ yêu cầu đường đi không lặp node, hãy chọn cú pháp và tính năng path semantics phù hợp với phiên bản Cypher đang dùng, rồi kiểm thử rõ ràng; đừng nhầm quy tắc relationship uniqueness mặc định với điều kiện path không chu trình.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Truy vấn trả về quá nhiều kết quả | Không giới hạn số bước hoặc không lọc loại relationship | Dùng `{min,max}`, hướng và relationship type phù hợp |
| Không tìm thấy đường đi | Chọn sai chiều relationship hoặc cận dưới quá lớn | Kiểm tra hướng graph và dữ liệu thực tế |
| Truy vấn trả đường ngắn nhất nhưng không thỏa điều kiện nghiệp vụ | Predicate nằm trong `WHERE` post-filter | Đưa điều kiện vào node/relationship pattern trước path selection |
| Chỉ nhận một trong nhiều đường đồng hạng | Dùng `SHORTEST 1` | Dùng `ALL SHORTEST` nếu cần mọi đường đồng hạng |
| Kết quả thay đổi giữa các lần chạy khi có tie | `SHORTEST k` không bảo đảm thứ tự giữa các path đồng hạng | Dùng `ALL SHORTEST` hoặc xác định tiêu chí nghiệp vụ bổ sung |
| Dùng `SHORTEST 2 GROUPS` nhưng nhận nhiều hơn hai path | `GROUPS` đếm nhóm độ dài, không đếm path | Dùng `SHORTEST k` nếu cần giới hạn số path |
| Dùng shortest path nhưng không tối ưu thời gian/chi phí | `SHORTEST` chỉ đếm số relationship | Dùng GDS Dijkstra/A* với weight property |
| Repository mapping lỗi với DTO | Alias Cypher không khớp tên DTO | Đồng bộ alias và constructor component |
| Entity trả về thiếu relationship | Custom query chỉ trả một phần graph | Dùng DTO/projection cho read model hoặc nạp đầy đủ trước khi ghi |
| Query chậm khi tìm một path | Nguồn/đích không được neo bằng index hoặc nhiều cặp candidate | Dùng unique key, lọc endpoint và xem `PROFILE` |

## 18. Quy trình thiết kế truy vấn đường đi

1. Xác định bài toán cần một đường đi ngắn nhất, mọi đường đồng hạng hay mọi node trong phạm vi N bước.
2. Xác định relationship type và hướng traversal.
3. Chọn cận dưới/cận trên cho số bước.
4. Neo node nguồn và đích bằng label cùng property có index.
5. Đặt predicate tại pattern nếu điều kiện phải được áp dụng trước path selection.
6. Chọn `SHORTEST`, `ALL SHORTEST`, `SHORTEST k GROUPS` hoặc truy vấn bounded traversal phù hợp.
7. Chọn kết quả entity, projection hoặc DTO theo dữ liệu caller cần.
8. Nếu cần trọng số, chuyển sang thuật toán GDS phù hợp.
9. Chạy `EXPLAIN`/`PROFILE` và kiểm thử graph có nhiều nhánh, chu trình, node thiếu và nhiều đường đồng hạng.
10. Đặt giới hạn kết quả và theo dõi hiệu năng trên dữ liệu gần với production.

## 19. Tự kiểm tra

1. Khác biệt giữa fixed-length path và quantified relationship là gì?
2. `-[:KNOWS]->{1,3}` có ý nghĩa gì?
3. Vì sao cận dưới `0` có thể trả về path rỗng?
4. `SHORTEST 1` và `ALL SHORTEST` khác nhau như thế nào?
5. `SHORTEST 2 GROUPS` giới hạn số path hay số nhóm độ dài?
6. Vì sao `WHERE` ở cấp graph pattern có thể loại bỏ path ngắn nhất mà không tìm path thay thế?
7. Khi nào nên dùng quantified path pattern thay vì quantified relationship?
8. Vì sao Cypher `SHORTEST` không phù hợp để tối ưu tổng chi phí relationship?
9. Khi nào cần dùng GDS Dijkstra hoặc A*?
10. Vì sao DTO projection phù hợp hơn entity khi custom query chỉ trả một phần graph?
11. Tại sao cần neo node nguồn và đích bằng index/constraint?
12. Cypher mặc định ngăn relationship lặp lại trong path có đồng nghĩa node không thể lặp lại không?

## Tài liệu tham khảo

- [Neo4j Cypher Manual — Shortest paths](https://neo4j.com/docs/cypher-manual/current/patterns/shortest-paths/)
- [Neo4j Cypher Manual — Variable-length paths](https://neo4j.com/docs/cypher-manual/current/patterns/variable-length-paths/)
- [Neo4j Cypher Manual — Path selectors reference](https://neo4j.com/docs/cypher-manual/current/patterns/reference/shortest-paths/)
- [Neo4j Cypher Manual — Query plans and PROFILE](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Spring Data Neo4j — Projections](https://docs.spring.io/spring-data/neo4j/reference/repositories/projections.html)
- [Spring Data Neo4j — FAQ: Custom queries](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Neo4j Graph Data Science — Dijkstra Source-Target Shortest Path](https://neo4j.com/docs/graph-data-science/current/algorithms/dijkstra-source-target/)
- [Neo4j Graph Data Science — A* Shortest Path](https://neo4j.com/docs/graph-data-science/current/algorithms/astar/)
