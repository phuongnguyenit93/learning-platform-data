# Đường đi, số bước duyệt, chu trình và node có nhiều kết nối

Trong Neo4j, dữ liệu được tổ chức thành các node và relationship. Một truy vấn thường bắt đầu ở một node, đi theo một hoặc nhiều relationship, rồi tìm node đích. Khi làm việc với Spring Data Neo4j (SDN), ta có thể mô hình hóa các node và relationship bằng entity, còn những hành trình nhiều bước, việc tìm chu trình và thống kê node có nhiều kết nối thường được diễn đạt trực tiếp bằng Cypher.

Bài học này sử dụng mạng lưới người quen làm ví dụ. Mỗi `Person` là một node; relationship `KNOWS` có hướng từ người biết sang người được biết. Cùng một cách làm có thể áp dụng cho mạng lưới dịch vụ, danh mục sản phẩm, quan hệ phụ thuộc giữa các thành phần hoặc hệ thống khuyến nghị.

## 1. Đường đi trong đồ thị là gì?

Đường đi (path) là một chuỗi gồm các node được nối với nhau bằng các relationship. Ví dụ:

```text
(An)-[:KNOWS]->(Bình)-[:KNOWS]->(Chi)-[:KNOWS]->(Dũng)
```

Đường đi trên có bốn node và ba relationship. Trong các truy vấn dạng đường đi, số bước (hop) thường được tính bằng số relationship đã đi qua, không phải số node xuất hiện. Vì vậy đường đi trên có độ dài ba bước.

Tạo một mạng lưới nhỏ để thực hành:

```cypher
MERGE (an:Person {id: 'p01', name: 'An'})
MERGE (binh:Person {id: 'p02', name: 'Bình'})
MERGE (chi:Person {id: 'p03', name: 'Chi'})
MERGE (dung:Person {id: 'p04', name: 'Dũng'})
MERGE (an)-[:KNOWS]->(binh)
MERGE (binh)-[:KNOWS]->(chi)
MERGE (chi)-[:KNOWS]->(dung)
MERGE (an)-[:KNOWS]->(dung)
```

An có thể đến Dũng trực tiếp trong một bước, hoặc đi qua Bình và Chi trong ba bước. Ví dụ này giúp phân biệt giữa việc tìm tất cả đường đi phù hợp và việc tìm đường đi ngắn nhất.

## 2. Khớp đường đi có độ dài giới hạn

Cypher dùng cú pháp độ dài biến thiên để tìm một chuỗi relationship có số bước nằm trong một khoảng. Ví dụ sau tìm các đường đi từ An đến Dũng có từ một đến bốn bước:

```cypher
MATCH p = (start:Person {id: $startId})-[:KNOWS*1..4]->(target:Person {id: $targetId})
RETURN p,
       length(p) AS hops,
       nodes(p) AS pathNodes,
       relationships(p) AS pathRelationships
ORDER BY hops
```

Trong mẫu truy vấn:

- `p` là biến giữ toàn bộ đường đi được khớp.
- `[:KNOWS*1..4]` yêu cầu đi theo relationship `KNOWS` có hướng, tối thiểu một và tối đa bốn bước.
- `length(p)` trả về số relationship trên đường đi.
- `nodes(p)` trả về danh sách node theo thứ tự xuất hiện trong đường đi.
- `relationships(p)` trả về danh sách relationship theo thứ tự được duyệt.

Có thể thay khoảng bằng một số bước cụ thể, chẳng hạn `[:KNOWS*3]` để tìm đường đi đúng ba bước. Nếu bỏ giới hạn trên, truy vấn có thể mở rộng qua một vùng đồ thị rất lớn. Vì thế, hãy chọn giới hạn phù hợp với bài toán và quy mô dữ liệu.

Hướng relationship cũng ảnh hưởng trực tiếp đến kết quả. Mẫu `-[:KNOWS]->` chỉ đi theo chiều đã lưu; mẫu `-[:KNOWS]-` cho phép khớp theo cả hai chiều. Chỉ dùng mẫu không định hướng khi nghiệp vụ thực sự xem quan hệ là hai chiều.

## 3. Tìm đường đi ngắn nhất và đếm số bước

Khi cần biết khoảng cách theo số relationship giữa hai node, có thể dùng `shortestPath`:

```cypher
MATCH p = shortestPath(
  (start:Person {id: $startId})-[:KNOWS*1..8]->(target:Person {id: $targetId})
)
RETURN p, length(p) AS hops
```

Truy vấn trả về một đường đi ngắn nhất tìm được trong phạm vi tối đa tám bước. Nếu cần tất cả đường đi có cùng độ dài ngắn nhất, dùng `allShortestPaths` với cùng mẫu đường đi:

```cypher
MATCH p = allShortestPaths(
  (start:Person {id: $startId})-[:KNOWS*1..8]->(target:Person {id: $targetId})
)
RETURN p, length(p) AS hops
```

Hai hàm này đo độ dài theo số relationship. Chúng không tự tính trọng số như thời gian, chi phí hay mức độ tin cậy. Nếu bài toán cần đường đi có tổng trọng số nhỏ nhất, cần mô hình hóa trọng số và chọn thuật toán phù hợp, chẳng hạn các thuật toán đường đi trong Graph Data Science khi hệ thống đã cài đặt thư viện đó.

Không có kết quả nghĩa là không tìm thấy đường đi thỏa điều kiện trong phạm vi truy vấn. Cũng cần phân biệt kết quả rỗng với khoảng cách bằng không: mẫu `*1..8` yêu cầu ít nhất một bước, nên truy vấn không xem node xuất phát là đường đi đến chính nó có độ dài không.

## 4. Nhận diện chu trình

Chu trình (cycle) là đường đi bắt đầu và kết thúc tại cùng một node. Ví dụ, quan hệ phụ thuộc `A -> B -> C -> A` tạo thành một chu trình. Chu trình có thể biểu thị dữ liệu bất thường trong cây phân cấp, vòng phụ thuộc dịch vụ hoặc một nhóm quan hệ khép kín.

Với một người cụ thể, truy vấn sau tìm các chu trình có độ dài từ hai đến sáu bước bắt đầu và kết thúc ở người đó:

```cypher
MATCH p = (start:Person {id: $personId})-[:KNOWS*2..6]->(start)
RETURN p, length(p) AS hops
ORDER BY hops
```

Việc dùng lại biến `start` ở cuối mẫu có nghĩa node cuối phải chính là node đầu. Giới hạn `2..6` bỏ qua self-loop một bước và giới hạn phạm vi tìm kiếm. Nếu nghiệp vụ cho phép relationship tự nối một node, có thể điều chỉnh cận dưới thành một.

Để chỉ kiểm tra có tồn tại chu trình hay không, không cần trả về toàn bộ đường đi:

```cypher
MATCH p = (start:Person {id: $personId})-[:KNOWS*2..6]->(start)
RETURN count(p) > 0 AS hasCycle
```

Trong các bài toán kiểm tra tính hợp lệ, hãy xác định rõ loại relationship nào tạo nên chu trình và hướng đi có ý nghĩa ra sao. Chẳng hạn, vòng phụ thuộc thường cần kiểm tra theo chiều `DEPENDS_ON`; nếu truy vấn không định hướng, một chuỗi quan hệ không có hướng nghiệp vụ có thể bị xem như chu trình ngoài ý muốn.

## 5. Node có nhiều kết nối: degree

Bậc (degree) của một node là số relationship nối với node đó. Node có degree cao thường được gọi là node có nhiều kết nối hoặc hub. Trong mạng xã hội, đó có thể là người có nhiều mối quan hệ; trong đồ thị dịch vụ, đó có thể là thành phần được nhiều thành phần khác phụ thuộc.

Hàm `degree(node)` trả về tổng số relationship gắn với node, xét cả chiều vào và chiều ra, trên mọi loại relationship. Có thể xếp hạng các node theo giá trị này:

```cypher
MATCH (person:Person)
RETURN person.id AS personId,
       person.name AS name,
       degree(person) AS degree
ORDER BY degree DESC
LIMIT 10
```

Nếu chỉ quan tâm relationship `KNOWS`, có thể đếm riêng loại đó:

```cypher
MATCH (person:Person)
OPTIONAL MATCH (person)-[r:KNOWS]-()
RETURN person.id AS personId,
       person.name AS name,
       count(r) AS knowsDegree
ORDER BY knowsDegree DESC
```

Mẫu `OPTIONAL MATCH` giữ lại cả những người chưa có relationship `KNOWS`; với họ, `count(r)` bằng không. Dấu gạch ngang không có mũi tên trong mẫu này đếm relationship theo cả hai chiều.

Khi cần tách số kết nối đi ra và đi vào, hãy đếm ở hai bước riêng:

```cypher
MATCH (person:Person)
OPTIONAL MATCH (person)-[outgoing:KNOWS]->()
WITH person, count(outgoing) AS outgoingCount
OPTIONAL MATCH (person)<-[incoming:KNOWS]-()
RETURN person.id AS personId,
       person.name AS name,
       outgoingCount,
       count(incoming) AS incomingCount
ORDER BY outgoingCount + incomingCount DESC
```

`WITH` tổng hợp số relationship đi ra trước khi khớp các relationship đi vào, nhờ đó hai phép đếm không nhân chéo số dòng với nhau. Degree chỉ phản ánh số kết nối trực tiếp; nó không tự nói lên tầm ảnh hưởng, chất lượng hay mức độ quan trọng của node. Những câu hỏi đó có thể cần thêm thuộc tính nghiệp vụ hoặc các thước đo trung tâm khác.

## 6. Ánh xạ node và truy vấn bằng Spring Data Neo4j

SDN ánh xạ node thành lớp được đánh dấu `@Node`, còn trường quan hệ có thể được khai báo bằng `@Relationship`. Ví dụ tối giản:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

import java.util.HashSet;
import java.util.Set;

@Node("Person")
public class Person {
    @Id
    private String id;

    private String name;

    @Relationship(type = "KNOWS", direction = Relationship.Direction.OUTGOING)
    private Set<Person> knows = new HashSet<>();

    // Constructor, getter và setter được lược bỏ.
}
```

`@Relationship` mô tả quan hệ mà SDN ánh xạ khi đọc hoặc ghi entity. Với các truy vấn đường đi nhiều bước, ta thường viết Cypher tường minh để giới hạn độ sâu và chỉ trả về dữ liệu cần dùng. Không nhất thiết phải tải toàn bộ mạng lưới quan hệ vào object graph của Java.

Repository có thể khai báo truy vấn tìm những người có thể đến được trong tối đa bốn bước:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (start:Person {id: $startId})-[:KNOWS*1..4]->(target:Person)
        RETURN DISTINCT target
        """)
    List<Person> findReachableWithinFourHops(@Param("startId") String startId);
}
```

SDN ánh xạ node `target` được trả về thành `Person`. `DISTINCT` loại bỏ trường hợp cùng một người được tìm thấy qua nhiều đường đi khác nhau. Tên tham số `$startId` trong Cypher phải tương ứng với tham số Java được truyền vào.

Nếu giao diện cần hiển thị số bước ngắn nhất đến từng người, có thể trả về projection chỉ chứa các giá trị cần thiết:

```java
public interface ReachabilityView {
    String getTargetId();
    Long getHops();
}
```

```java
@Query("""
    MATCH p = (start:Person {id: $startId})-[:KNOWS*1..5]->(target:Person)
    RETURN target.id AS targetId, min(length(p)) AS hops
    ORDER BY hops, targetId
    """)
List<ReachabilityView> findReachableWithDistance(@Param("startId") String startId);
```

Các bí danh `targetId` và `hops` trong kết quả Cypher khớp với tên thuộc tính projection. `min(length(p))` gộp nhiều đường đi đến cùng một đích thành số bước nhỏ nhất. Projection giúp lớp ứng dụng nhận đúng dữ liệu cần hiển thị mà không phải tải toàn bộ đường đi.

Có thể áp dụng cách tương tự để trả về degree:

```java
public interface PersonDegreeView {
    String getPersonId();
    String getName();
    Long getDegree();
}
```

```java
@Query("""
    MATCH (person:Person)
    RETURN person.id AS personId,
           person.name AS name,
           degree(person) AS degree
    ORDER BY degree DESC
    LIMIT $limit
    """)
List<PersonDegreeView> findMostConnected(@Param("limit") int limit);
```

Khi truy vấn là một phần của nghiệp vụ gồm nhiều thao tác đọc/ghi, đặt ranh giới transaction ở tầng service bằng `@Transactional` để các thao tác tham gia cùng transaction quản lý bởi Spring. Với luồng chỉ đọc, có thể đánh dấu `readOnly = true` khi phù hợp với cấu hình và cách truy cập dữ liệu của ứng dụng. Không nên xem thuộc tính này là cơ chế phân quyền hay bảo đảm rằng truy vấn không thể ghi dữ liệu.

## 7. Tối ưu truy vấn đường đi và thống kê kết nối

Truy vấn đường đi có thể mở rộng nhanh vì mỗi node có thể nối với nhiều node khác. Một vài nguyên tắc thực tế giúp kiểm soát chi phí:

1. **Bắt đầu từ node xác định rõ.** Dùng nhãn và thuộc tính định danh như `Person.id` để giới hạn node xuất phát. Tạo uniqueness constraint cho định danh thường dùng:

   ```cypher
   CREATE CONSTRAINT person_id IF NOT EXISTS
   FOR (person:Person)
   REQUIRE person.id IS UNIQUE
   ```

2. **Giới hạn độ sâu.** Chọn khoảng bước theo yêu cầu nghiệp vụ, ví dụ `*1..4`. Tránh mở rộng không giới hạn nếu không có lý do rõ ràng.

3. **Chỉ đi qua loại relationship cần thiết.** `[:KNOWS*1..4]` thường thu hẹp không gian tìm kiếm tốt hơn việc duyệt mọi loại relationship.

4. **Chỉ trả về dữ liệu cần dùng.** Nếu giao diện chỉ cần node đích và số bước, hãy trả về các thuộc tính đó thay vì toàn bộ `p`, `nodes(p)` và `relationships(p)`.

5. **Giới hạn kết quả và loại bỏ trùng lặp khi phù hợp.** `LIMIT` giảm số bản ghi trả về; `DISTINCT` hữu ích khi nhiều đường đi dẫn đến cùng một node. Tuy nhiên, `LIMIT` không thay thế việc giới hạn độ sâu của phần duyệt đồ thị.

6. **Đo kế hoạch thực thi.** Dùng `EXPLAIN` để xem kế hoạch dự kiến và `PROFILE` để chạy truy vấn, quan sát số dòng, DB hits và các bước mở rộng. Kiểm tra truy vấn với dữ liệu gần quy mô thực tế vì số lượng kết nối của node có thể làm thay đổi mạnh chi phí.

Đặc biệt, `allShortestPaths` có thể trả về nhiều đường đi nếu có nhiều tuyến cùng độ dài ngắn nhất. Chỉ dùng khi ứng dụng thực sự cần tất cả các tuyến đó. Nếu chỉ cần khoảng cách, hãy trả về độ dài hoặc projection gọn.

## 8. Bài tập tự kiểm tra

Với mạng lưới An, Bình, Chi và Dũng ở phần đầu, hãy thử trả lời các câu hỏi sau bằng Cypher:

1. Tìm mọi đường đi từ An đến Dũng có tối đa ba bước và trả về `length(p)`.
2. Tìm đường đi ngắn nhất từ An đến Dũng. Kết quả có bao nhiêu bước?
3. Thêm relationship `Dũng -> An`, sau đó kiểm tra chu trình bắt đầu từ An.
4. Xếp hạng bốn người theo số relationship `KNOWS` nối với mỗi người.
5. Viết một phương thức repository chỉ trả về `Person` có thể đến được trong tối đa hai bước từ một `startId` nhận qua tham số.

Khi hoàn thành, hãy tự kiểm tra ba điểm: số bước được tính bằng relationship; hướng relationship trong mẫu Cypher khớp với ý nghĩa dữ liệu; và truy vấn SDN trả về đúng kiểu dữ liệu mà lớp Java cần. Đây là nền tảng để xây dựng các chức năng như gợi ý kết nối, phát hiện vòng phụ thuộc và phân tích node trung tâm trên Neo4j.
