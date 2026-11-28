# Chu trình, nhiều nhánh và cách giới hạn đồ thị cần đọc

## Mục tiêu

Sau bài học này, bạn có thể:

- Nhận diện chu trình và node tự tham chiếu trong mô hình đồ thị.
- Giải thích vì sao một node có nhiều nhánh liên kết có thể làm tăng mạnh lượng dữ liệu cần đọc.
- Giới hạn đường đi bằng Cypher, điều kiện lọc và giới hạn số kết quả.
- Dùng projection và aggregate boundary để kiểm soát phần đồ thị Spring Data Neo4j ánh xạ.
- Thiết kế truy vấn nhiều nhánh sao cho mỗi root node có một record kết quả phù hợp với cơ chế mapping của SDN.
- Tránh ghi đè hoặc xóa nhầm relationship khi lưu một đồ thị chỉ được đọc một phần.

## 1. Đồ thị có thể chứa chu trình

Trong mô hình quan hệ đơn giản, dữ liệu thường được hình dung theo cấu trúc cha-con hoặc danh sách. Đồ thị Neo4j linh hoạt hơn: một node có thể liên kết đến nhiều node, và các node có thể nối ngược về những node đã đi qua.

Ví dụ mạng theo dõi người dùng:

~~~text
(An)-[:FOLLOWS]->(Binh)
(Binh)-[:FOLLOWS]->(Chi)
(Chi)-[:FOLLOWS]->(An)
~~~

Ba node tạo thành một chu trình. Một node cũng có thể có relationship tự tham chiếu:

~~~text
(An)-[:FOLLOWS]->(An)
~~~

Trong Spring Data Neo4j (SDN), mô hình Java có thể biểu diễn relationship trỏ đến cùng loại entity:

~~~java
@Node("Person")
public class Person {

    @Id
    private String personId;

    private String fullName;

    @Relationship(
        type = "FOLLOWS",
        direction = Relationship.Direction.OUTGOING
    )
    private Set<Person> follows = new LinkedHashSet<>();

    // Constructor, getter và setter được lược bỏ.
}
~~~

Vì cả hai đầu của FOLLOWS đều là Person, một đối tượng Person có thể tham chiếu đến đối tượng Person khác, rồi đối tượng đó lại tham chiếu về đối tượng ban đầu. Đây là mô hình tự tham chiếu (self-referencing relationship).

Chu trình là cấu trúc hợp lệ của đồ thị. Nó có ý nghĩa trong các bài toán như mạng xã hội, phụ thuộc dịch vụ, tuyến vận chuyển, quan hệ tổ tiên hoặc liên kết giữa các tài liệu.

## 2. Chu trình ảnh hưởng thế nào đến việc đọc bằng SDN?

Khi repository đọc một entity, SDN không chỉ chuyển node gốc thành Java object. Framework còn ánh xạ các relationship được khai báo trong domain model và các node liên quan cần thiết để tạo đồ thị đối tượng.

Với mô hình tự tham chiếu hoặc schema có thể tạo chu trình, SDN sử dụng cơ chế tạo truy vấn theo dữ liệu (cascading/data-driven query creation). Framework bắt đầu từ node được yêu cầu, xem xét các node và relationship tìm được, rồi tiếp tục truy vấn những relationship được ánh xạ trên các node liên quan cho đến khi không tìm thấy node hoặc relationship mới.

Điều này giúp mô hình Java phản ánh được cấu trúc đồ thị mà ứng dụng đã khai báo. Tuy nhiên, nó cũng có nghĩa một lần đọc entity có thể đi xa hơn dự kiến nếu domain model chứa nhiều relationship tự tham chiếu hoặc liên kết đến các node có nhiều nhánh.

Ví dụ, khi đọc An:

~~~text
An
 ├── FOLLOWS → Binh
 │              ├── FOLLOWS → Chi
 │              │              └── FOLLOWS → An
 │              └── FOLLOWS → Dung
 └── FOLLOWS → Hoa
                ├── FOLLOWS → Khoa
                └── FOLLOWS → Lan
~~~

Nếu yêu cầu chỉ là hiển thị tên và số người An theo dõi, việc nạp tiếp toàn bộ những người được Bình, Chi, Dung, Hoa, Khoa và Lan theo dõi sẽ không cần thiết.

Không nên giả định cơ chế mapping sẽ tự giới hạn đồ thị theo số tầng phù hợp với mọi màn hình. Hãy xác định rõ phần dữ liệu mà use case cần, rồi chọn query, projection hoặc aggregate boundary tương ứng.

## 3. Nhiều nhánh làm tăng lượng dữ liệu rất nhanh

Một node có thể có nhiều loại relationship cùng lúc:

~~~text
                         ┌── FOLLOWS ──> Person
                         │
Person ──────────────────┼── WORKS_WITH -> Person
                         │
                         ├── MEMBER_OF -> Group
                         │
                         └── CONTRIBUTES_TO -> Project
~~~

Giả sử một Person có:

- 20 người được theo dõi.
- 8 đồng nghiệp.
- 5 nhóm thành viên.
- 4 dự án tham gia.

Nếu ứng dụng tiếp tục đọc thêm các relationship của từng node liên quan, số node được khám phá có thể tăng rất nhanh. Khi mỗi node ở tầng tiếp theo cũng có nhiều liên kết, lượng dữ liệu tăng theo cả độ sâu lẫn độ rộng.

Hai khái niệm cần phân biệt:

- **Độ sâu (depth):** số bước relationship từ node gốc đến node cần đọc.
- **Độ rộng (breadth/fan-out):** số node hoặc relationship được mở rộng tại mỗi bước.

Giới hạn độ sâu vẫn chưa đủ nếu mỗi node có hàng nghìn liên kết. Ngược lại, giới hạn số kết quả mỗi nhánh vẫn có thể chưa đủ nếu truy vấn đi qua quá nhiều tầng. Cần phối hợp giới hạn độ sâu, loại relationship, hướng, điều kiện lọc và số kết quả.

## 4. Giới hạn đường đi bằng Cypher

Cypher hỗ trợ relationship có độ dài thay đổi. Có thể chỉ định khoảng số bước để truy vấn không đi qua toàn bộ đồ thị.

Ví dụ tìm người mà An có thể tiếp cận qua từ một đến ba bước FOLLOWS:

~~~cypher
MATCH path = (start:Person {personId: $personId})
             -[:FOLLOWS*1..3]->
             (target:Person)
RETURN path
~~~

**\*1..3** có nghĩa đường đi phải có ít nhất một relationship và tối đa ba relationship. Nếu dùng **\*1..** mà không có giới hạn trên, truy vấn có thể phải khám phá rất nhiều đường đi trong đồ thị lớn.

Một số cách viết thường gặp:

| Mẫu | Ý nghĩa |
|---|---|
| **[:FOLLOWS]** | Đúng một relationship FOLLOWS |
| **[:FOLLOWS*1..2]** | Từ một đến hai relationship |
| **[:FOLLOWS*2..4]** | Từ hai đến bốn relationship |
| **[:FOLLOWS*1..]** | Một hoặc nhiều relationship, không có giới hạn trên |
| **[:FOLLOWS*0..3]** | Từ không đến ba relationship; có thể trả về chính node gốc |

Hãy chọn cận trên theo yêu cầu nghiệp vụ. Ví dụ gợi ý bạn bè cấp gần có thể chỉ cần hai bước; phân tích phụ thuộc dịch vụ có thể cần ba hoặc bốn bước.

### Chu trình và tính duy nhất của đường đi

Theo quy tắc mặc định của Cypher, một relationship không được đi qua nhiều lần trong cùng một kết quả đường đi. Tuy nhiên, node có thể xuất hiện lại trong đường đi nếu được nối qua các relationship khác nhau.

Vì vậy, giới hạn độ dài đường đi vẫn cần thiết ngay cả khi Cypher đã ngăn việc lặp relationship trong một path. Nếu yêu cầu nghiệp vụ đòi hỏi một đường đi không được lặp lại node, cần thêm điều kiện kiểm tra danh sách node của path hoặc sử dụng cơ chế path mode phù hợp với phiên bản Neo4j đang triển khai.

Ví dụ loại bỏ path kết thúc lại ở node gốc:

~~~cypher
MATCH path = (start:Person {personId: $personId})
             -[:FOLLOWS*1..4]->
             (target:Person)
WHERE target <> start
RETURN path
~~~

Điều kiện **target <> start** loại bỏ đường đi quay về đúng node ban đầu. Nó không bảo đảm mọi node trung gian đều khác nhau. Hãy phân biệt rõ điều kiện này với yêu cầu tìm simple path không lặp bất kỳ node nào.

Nếu nghiệp vụ yêu cầu mỗi node chỉ xuất hiện một lần trong path, có thể kiểm tra tính duy nhất của danh sách node:

~~~cypher
MATCH path = (start:Person {personId: $personId})
             -[:FOLLOWS*1..4]->
             (target:Person)
WHERE all(n IN nodes(path) WHERE single(m IN nodes(path) WHERE m = n))
RETURN path
~~~

Điều kiện này kiểm tra từng node trong path chỉ xuất hiện đúng một lần. Nó có thêm chi phí xử lý, vì vậy vẫn nên giới hạn độ dài path và chỉ dùng khi nghiệp vụ thật sự cần simple path.

### Lọc loại relationship và hướng

Nếu chỉ cần duyệt FOLLOWS theo hướng đi ra, hãy chỉ định rõ:

~~~cypher
MATCH (p:Person {personId: $personId})
      -[:FOLLOWS*1..3]->
      (target:Person)
RETURN DISTINCT target
~~~

Truy vấn này tránh mở rộng sang các relationship không liên quan như WORKS_WITH hoặc MEMBER_OF. Nếu nghiệp vụ cần cả hai chiều, có thể dùng mẫu không chỉ định hướng, nhưng hãy cân nhắc rằng số nhánh được khớp có thể tăng lên.

### Giới hạn số kết quả

LIMIT giúp giới hạn số record trả về:

~~~cypher
MATCH (p:Person {personId: $personId})-[:FOLLOWS]->(friend:Person)
RETURN friend
ORDER BY friend.fullName
LIMIT 20
~~~

Tuy nhiên, LIMIT ở cuối truy vấn không phải lúc nào cũng giới hạn số node mà database phải khám phá trước đó. Với truy vấn có đường đi nhiều bước hoặc nhiều nhánh, hãy giới hạn ngay trong phần mở rộng tương ứng, dùng điều kiện lọc và cận trên của path. Luôn kiểm tra execution plan bằng EXPLAIN hoặc PROFILE khi truy vấn chạy trên đồ thị lớn.

## 5. Giới hạn phần entity được ánh xạ bằng projection

Projection cho phép SDN chỉ tải những property và relationship mà một use case cần. Có hai dạng phổ biến:

- **Interface projection:** khai báo các accessor cần đọc. SDN dùng chúng để tạo truy vấn cho phần dữ liệu được yêu cầu.
- **DTO projection:** ánh xạ kết quả vào một lớp dữ liệu riêng, phù hợp khi API cần một cấu trúc trả về khác domain entity.

Ví dụ domain entity:

~~~java
@Node("Person")
public class Person {

    @Id
    private String personId;

    private String fullName;

    @Relationship(type = "FOLLOWS")
    private Set<Person> follows = new LinkedHashSet<>();

    @Relationship(type = "WORKS_WITH")
    private Set<Person> colleagues = new LinkedHashSet<>();
}
~~~

Màn hình danh sách chỉ cần tên người dùng và tên những người được theo dõi trực tiếp. Có thể định nghĩa projection:

~~~java
public interface PersonCard {

    String getFullName();

    Set<FollowedPerson> getFollows();

    interface FollowedPerson {
        String getFullName();
    }
}
~~~

Repository:

~~~java
public interface PersonRepository
        extends Neo4jRepository<Person, String> {

    Optional<PersonCard> findProjectedByPersonId(String personId);
}
~~~

Projection trên chỉ yêu cầu fullName của Person gốc và fullName của các node được theo dõi trực tiếp. Nó không khai báo follows bên trong FollowedPerson, nên truy vấn không tiếp tục đi theo chuỗi FOLLOWS qua các tầng tiếp theo.

Một projection nhiều tầng có thể khai báo rõ số tầng cần đọc:

~~~java
public interface PersonNetworkCard {

    String getFullName();

    Set<LevelOnePerson> getFollows();

    interface LevelOnePerson {
        String getFullName();

        Set<LevelTwoPerson> getFollows();
    }

    interface LevelTwoPerson {
        String getFullName();
    }
}
~~~

Projection nhiều tầng được giới hạn theo cấu trúc đã khai báo. Dù domain graph có chu trình, logic projection không tiếp tục theo chu trình vô hạn; SDN tạo truy vấn không có chu trình theo cấu trúc projection.

### DTO projection cho kết quả tổng hợp

Nếu giao diện chỉ cần tên và số lượng người được theo dõi, không cần trả về toàn bộ node liên quan:

~~~java
public record PersonSummary(
    String personId,
    String fullName,
    Long followedCount
) {
}
~~~

Repository có thể trả về DTO từ custom query:

~~~java
public interface PersonRepository
        extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (p:Person {personId: $personId})
        OPTIONAL MATCH (p)-[:FOLLOWS]->(friend:Person)
        RETURN p.personId AS personId,
               p.fullName AS fullName,
               count(friend) AS followedCount
        """)
    Optional<PersonSummary> findSummary(String personId);
}
~~~

Truy vấn chỉ trả về hai property của node gốc và một giá trị tổng hợp. Các node friend không cần được hydrate thành entity Java.

Với DTO projection, tên property trong record kết quả cần khớp tên field hoặc accessor của DTO. Custom query có thể bổ sung giá trị tổng hợp mà domain entity không khai báo. Collections của kiểu đơn giản hoặc persistent entity được hỗ trợ trong projection; Map không phải kiểu collection projection được hỗ trợ theo cách này.

## 6. Đặt ranh giới đồ thị bằng @Node aggregateBoundary

Projection phù hợp khi từng use case cần một hình dạng dữ liệu khác nhau. Nếu một loại node luôn là ranh giới của aggregate, SDN còn hỗ trợ khai báo ranh giới ngay trên annotation @Node thông qua thuộc tính aggregateBoundary.

Ví dụ, Movie có liên kết đến nhiều Person. Khi đọc đồ thị Movie, ứng dụng chỉ muốn nhận định danh của Person liên quan và không muốn tiếp tục đọc thuộc tính hoặc relationship của Person:

~~~java
@Node(value = "Movie", aggregateBoundary = Person.class)
public class Movie {

    @Id
    private String movieId;

    private String title;

    @Relationship(type = "ACTED_IN", direction = Relationship.Direction.INCOMING)
    private Set<Person> actors = new LinkedHashSet<>();
}
~~~

Khi Person là aggregate boundary được khai báo, SDN chỉ trả về trường @Id của các Person ở ranh giới đó; framework không đi tiếp theo relationship của Person và không tải các property khác của Person trong quá trình đọc graph này.

Aggregate boundary hữu ích khi:

- Một loại node được chia sẻ bởi nhiều aggregate.
- Entity có liên kết ngược hoặc liên kết tự tham chiếu rộng.
- Muốn tránh nạp toàn bộ dữ liệu của node liên quan trong mọi truy vấn.
- Ranh giới nghiệp vụ giữa các aggregate đã được xác định rõ.

Hãy chọn boundary theo ranh giới domain thực tế. Nếu một use case cần đầy đủ thông tin Person, có thể dùng projection riêng phù hợp cho use case đó. Không nên đặt boundary tùy tiện nếu ứng dụng thường xuyên cần dữ liệu ở phía bên kia.

Các ví dụ cũ dùng annotation @Depth thuộc thế hệ Spring Data Neo4j dựa trên Neo4j-OGM. Với SDN hiện đại, hãy kiểm tra đúng phiên bản và ưu tiên projection, aggregate boundary hoặc custom Cypher có cận path thay vì sao chép cấu hình depth từ tài liệu cũ.

## 7. Nhiều nhánh trong custom query và lỗi Cartesian product

Spring Data Neo4j xử lý kết quả truy vấn theo record. Khi ánh xạ một root entity có nhiều relationship, thông thường cần một record chứa root node cùng các tập relationship và node liên quan tương ứng.

Giả sử An có ba người bạn và bốn đồng nghiệp. Truy vấn ghép hai nhánh độc lập theo cách ngây thơ:

~~~cypher
MATCH (p:Person {personId: $personId})
      -[knows:KNOWS]->(friend:Person)
MATCH (p)-[works:WORKS_WITH]->(colleague:Person)
RETURN p, knows, friend, works, colleague
~~~

Nếu có 3 bạn và 4 đồng nghiệp, kết quả có thể có 12 record cho cùng một Person gốc. Mỗi người bạn bị lặp lại theo từng đồng nghiệp và ngược lại. Khi SDN ánh xạ các record này thành entity, dữ liệu lặp có thể làm kết quả khó dùng hoặc sai với cấu trúc mong muốn.

### Gom từng nhánh bằng collect

Có thể gom relationship và node của nhánh thứ nhất trước khi mở rộng nhánh tiếp theo:

~~~cypher
MATCH (p:Person {personId: $personId})
OPTIONAL MATCH (p)-[knows:KNOWS]->(friend:Person)
WITH p,
     collect(DISTINCT knows) AS knowsRelationships,
     collect(DISTINCT friend) AS friends
OPTIONAL MATCH (p)-[works:WORKS_WITH]->(colleague:Person)
RETURN p,
       knowsRelationships,
       friends,
       collect(DISTINCT works) AS workRelationships,
       collect(DISTINCT colleague) AS colleagues
~~~

Truy vấn gom nhánh KNOWS thành các collection trước, rồi mới tìm nhánh WORKS_WITH. Kết quả có một record cho Person gốc và các collection chứa phần tử của từng nhánh. DISTINCT loại bỏ phần tử trùng trong collection.

Khi dùng custom query để trả về entity, các relationship và node được trả về phải khớp với mapping của domain class. Nếu query chỉ cần một bản tóm tắt, DTO projection thường rõ ràng hơn việc cố hydrate toàn bộ graph.

### Dùng subquery để giới hạn riêng từng nhánh

Nếu mỗi nhánh cần giới hạn số node khác nhau, correlated subquery giúp áp dụng điều kiện riêng cho từng nhánh:

~~~cypher
MATCH (p:Person {personId: $personId})
CALL {
    WITH p
    OPTIONAL MATCH (p)-[:FOLLOWS]->(friend:Person)
    WITH friend
    ORDER BY friend.fullName
    LIMIT 10
    RETURN collect(friend.fullName) AS topFriends
}
CALL {
    WITH p
    OPTIONAL MATCH (p)-[:WORKS_WITH]->(colleague:Person)
    WITH colleague
    ORDER BY colleague.fullName
    LIMIT 5
    RETURN collect(colleague.fullName) AS closeColleagues
}
RETURN p.personId AS personId,
       p.fullName AS fullName,
       topFriends,
       closeColleagues
~~~

Mỗi subquery được thực thi theo node p hiện tại và có giới hạn riêng: tối đa 10 tên người được theo dõi và 5 đồng nghiệp. Vì kết quả trả về là dữ liệu tổng hợp, có thể ánh xạ vào DTO thay vì entity graph đầy đủ.

Correlated subquery với CALL { ... } yêu cầu phiên bản Neo4j hỗ trợ cú pháp này. Hãy kiểm tra phiên bản database trước khi dùng trong ứng dụng.

## 8. Đọc đường đi nhưng vẫn giữ một record cho root

Khi truy vấn nhiều đường đi từ cùng một node gốc, MATCH path = ... RETURN path thường tạo nhiều record, mỗi record ứng với một path. SDN không tự hiểu một path là toàn bộ entity graph cần hydrate.

Trả về path rất hữu ích khi xem đường đi trong Neo4j Browser hoặc khi ứng dụng tự xử lý path. Nếu muốn SDN ánh xạ thành entity graph, cần trích xuất node và relationship thành các collection trong record; không chỉ trả về biến path.

Nếu cần ánh xạ root entity cùng các node và relationship từ nhiều path, hãy trích xuất nodes(path) và relationships(path), sau đó gom dữ liệu thành một record cho root. Có thể dùng collect và reduce ở database để gộp các phần tử trùng.

Ví dụ khái niệm:

~~~cypher
MATCH path = (root:Person {personId: $personId})
             -[:FOLLOWS*1..3]->
             (target:Person)
WITH root, collect(path) AS paths
WITH root,
     reduce(allNodes = [],
            path IN paths | allNodes + nodes(path)) AS nodeCandidates,
     reduce(allRelationships = [],
            path IN paths | allRelationships + relationships(path)) AS relationshipCandidates
RETURN root,
       reduce(uniqueNodes = [],
              n IN nodeCandidates |
              CASE
                  WHEN n IN uniqueNodes THEN uniqueNodes
                  ELSE uniqueNodes + n
              END) AS graphNodes,
       reduce(uniqueRelationships = [],
              r IN relationshipCandidates |
              CASE
                  WHEN r IN uniqueRelationships THEN uniqueRelationships
                  ELSE uniqueRelationships + r
              END) AS graphRelationships
~~~

Truy vấn minh họa việc:

1. Giới hạn path từ một đến ba bước.
2. Gom các path của cùng root.
3. Trích xuất node và relationship từ mỗi path.
4. Gộp các node và relationship trùng nhau.
5. Trả về một record cho root cùng các collection đã hợp nhất.

Việc gộp ở database làm giảm lượng dữ liệu phải truyền về ứng dụng, nhưng các path vẫn cần được tạo và xử lý trong bộ nhớ database. Với đồ thị có nhiều nhánh, hãy cân nhắc giới hạn path và điều kiện lọc trước khi dùng collect/reduce trên số lượng lớn đường đi.

## 9. Chọn công cụ giới hạn phù hợp

| Nhu cầu | Cách phù hợp | Kết quả |
|---|---|---|
| Chỉ cần một vài property của node | Interface hoặc DTO projection | Không tải các property/relationship không được khai báo |
| Cần một số tầng relationship cố định | Multi-level projection | Graph đọc theo cấu trúc projection |
| Một loại node luôn là ranh giới aggregate | @Node(aggregateBoundary = ...) | Node ở ranh giới chỉ trả ID |
| Cần duyệt quan hệ có độ sâu thay đổi | Cypher variable-length path có cận trên | Giới hạn số bước duyệt |
| Mỗi nhánh có số lượng tối đa riêng | Correlated subquery với ORDER BY/LIMIT | Giới hạn từng nhánh |
| Cần nhiều nhánh trong một entity graph | collect và gom từng nhánh | Một record cho mỗi root |
| Cần dữ liệu tổng hợp cho API | Custom query trả DTO | Không cần hydrate toàn bộ entity graph |

Không có một giới hạn duy nhất phù hợp với mọi tình huống. Hãy bắt đầu từ hình dạng dữ liệu mà use case cần trả về, rồi chọn công cụ ở đúng tầng.

## 10. Lưu ý khi lưu một đồ thị đã đọc một phần

Một lỗi nguy hiểm là đọc một phần graph để hiển thị, thay đổi một property, rồi lưu lại entity như thể đã tải toàn bộ graph.

Ví dụ, An có 20 relationship FOLLOWS nhưng projection chỉ đọc 5 người đầu tiên. Nếu ứng dụng biến projection đó thành một entity Person rồi gọi save, SDN có thể đồng bộ các relationship theo trạng thái Java hiện có. Những relationship không có trong entity có thể bị xem là đã bị loại bỏ khỏi mô hình cần lưu.

Vì vậy:

- Dùng projection/DTO cho use case chỉ đọc hoặc hiển thị.
- Nếu cần cập nhật entity, hãy tải đầy đủ các property và relationship mà nghiệp vụ sẽ ghi lại.
- Khi cần lưu một phần có chủ đích, cân nhắc API projection của Neo4jTemplate như saveAs để chỉ cập nhật các trường và relationship nằm trong projection.
- Không lấy một graph đã cắt bớt rồi dùng làm nguồn dữ liệu đầy đủ cho thao tác save.

Projection có thể dùng làm blueprint cho thao tác lưu. Tuy nhiên, nếu mục tiêu là giữ lại các relationship hiện có, hãy bảo đảm dữ liệu cần giữ đã được nạp trước khi lưu.

## 11. Bài tập thực hành

Tạo mạng theo dõi có chu trình và nhiều nhánh:

~~~cypher
CREATE (an:Person {personId: "p-1", fullName: "An"})
CREATE (binh:Person {personId: "p-2", fullName: "Binh"})
CREATE (chi:Person {personId: "p-3", fullName: "Chi"})
CREATE (dung:Person {personId: "p-4", fullName: "Dung"})
CREATE (hoa:Person {personId: "p-5", fullName: "Hoa"})
CREATE (an)-[:FOLLOWS]->(binh)
CREATE (an)-[:FOLLOWS]->(chi)
CREATE (binh)-[:FOLLOWS]->(dung)
CREATE (chi)-[:FOLLOWS]->(hoa)
CREATE (dung)-[:FOLLOWS]->(an)
CREATE (hoa)-[:FOLLOWS]->(an)
~~~

Thực hiện các yêu cầu:

1. Tìm những người An theo dõi trực tiếp bằng một relationship.
2. Tìm các node có thể tiếp cận trong tối đa hai bước.
3. Tìm đường đi từ An quay về An và giải thích vì sao đó là chu trình.
4. Viết projection chỉ lấy tên An và tên những người An theo dõi trực tiếp.
5. Viết DTO query trả về tên An cùng số người được theo dõi.
6. Thêm một nhánh WORKS_WITH và viết query gom hai nhánh mà không tạo Cartesian product.
7. So sánh số node/relationship được trả về khi đọc root entity và khi dùng projection.

Các truy vấn kiểm tra:

~~~cypher
MATCH (p:Person {personId: "p-1"})-[:FOLLOWS*1..2]->(target:Person)
RETURN DISTINCT target.personId, target.fullName
ORDER BY target.personId
~~~

~~~cypher
MATCH path = (p:Person {personId: "p-1"})
             -[:FOLLOWS*1..4]->
             (p)
RETURN path
~~~

~~~cypher
MATCH (p:Person {personId: "p-1"})-[r:FOLLOWS]->(target:Person)
RETURN p.personId,
       collect(DISTINCT r) AS relationships,
       collect(DISTINCT target) AS targets
~~~

Sau khi chạy, hãy trả lời:

- Truy vấn nào tạo nhiều record cho cùng một root?
- Điều gì xảy ra nếu bỏ cận trên của variable-length path?
- Vì sao projection không đi theo chu trình được khai báo trong domain entity?
- Khi nào nên dùng aggregate boundary thay vì projection?
- Vì sao không nên lưu một entity đã được đọc thiếu relationship?

## Kết luận

Chu trình và nhiều nhánh là cấu trúc tự nhiên của đồ thị, nhưng chúng có thể làm lượng dữ liệu cần đọc tăng mạnh. SDN hỗ trợ mô hình tự tham chiếu bằng cơ chế truy vấn theo dữ liệu; vì vậy ứng dụng cần chủ động xác định ranh giới graph cho từng use case.

Hãy giới hạn đường đi bằng cận trên và điều kiện Cypher, dùng projection để chọn property/relationship cần đọc, dùng aggregate boundary cho ranh giới domain ổn định, và gom các nhánh trong custom query để mỗi root có một record phù hợp với mapping. Khi lưu dữ liệu, chỉ ghi lại graph đã được tải đầy đủ theo phạm vi nghiệp vụ cần cập nhật để tránh vô tình loại bỏ relationship còn tồn tại.

## Tài liệu tham khảo

- [Spring Data Neo4j: Projections và aggregate boundaries](https://docs.spring.io/spring-data/neo4j/reference/projections/sdn-projections.html)
- [Spring Data Neo4j: Custom queries và ánh xạ nhiều relationship](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
- [Spring Data Neo4j: Cách tạo query và xử lý graph khi đọc](https://docs.spring.io/spring-data/neo4j/reference/appendix/query-creation.html)
- [Neo4j Cypher Manual: Variable-length paths](https://neo4j.com/docs/cypher-manual/current/patterns/variable-length-paths/)
- [Neo4j Cypher Manual: Paths with unique relationships](https://neo4j.com/docs/cypher-manual/current/patterns/unique-relationship-paths/)
