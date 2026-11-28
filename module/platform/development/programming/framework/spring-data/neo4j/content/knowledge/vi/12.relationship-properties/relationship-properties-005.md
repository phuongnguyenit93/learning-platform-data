# Nhiều relationship cùng kiểu giữa cùng một cặp node

Trong Neo4j, một cặp node có thể được nối với nhau bằng nhiều relationship cùng type và cùng hướng. Những relationship song song này là cấu trúc hợp lệ của property graph. Chúng biểu diễn các lần tương tác độc lập giữa cùng hai thực thể, chẳng hạn một người đánh giá cùng một bộ phim nhiều lần, hai tài khoản thực hiện nhiều lần chuyển tiền, hoặc một khách hàng phát sinh nhiều lần giao dịch với cùng cửa hàng.

Điểm quan trọng là mỗi relationship có danh tính riêng và có thể mang bộ property riêng. Vì vậy, hai relationship cùng type giữa cùng cặp node vẫn có thể đại diện cho hai sự kiện khác nhau. Khi làm việc với Spring Data Neo4j (SDN), cần chọn kiểu collection phù hợp và dùng lớp **@RelationshipProperties** khi muốn ánh xạ thuộc tính của từng relationship thành một đối tượng Java riêng.

Sau bài học, bạn có thể:

- Giải thích vì sao Neo4j cho phép nhiều relationship cùng type giữa cùng hai node.
- Phân biệt việc tạo relationship mới với việc bảo đảm một relationship tồn tại bằng **CREATE** và **MERGE**.
- Thiết kế property nhận diện từng lần tương tác và chọn khi nào nên tạo node sự kiện.
- Ánh xạ nhiều relationship song song bằng **List** và **@RelationshipProperties**.
- Truy vấn, cập nhật và xóa đúng một relationship mà không vô tình tác động đến các relationship khác.

## 1. Relationship song song trong property graph

Relationship trong Neo4j kết nối một node bắt đầu với một node đích, có một type và có thể có các property. Một node có thể có nhiều relationship đi ra hoặc đi vào. Neo4j cũng cho phép nhiều relationship có cùng node bắt đầu, node đích và type.

Ví dụ, một người có thể gửi hai đánh giá khác nhau cho cùng một bộ phim ở hai thời điểm:

~~~mermaid
flowchart LR
    P["Person<br/>personCode: P-01"]
    M["Movie<br/>movieCode: M-10"]
    P -->|REVIEWED<br/>reviewCode: R-100<br/>score: 5| M
    P -->|REVIEWED<br/>reviewCode: R-101<br/>score: 4| M
~~~

Hai cạnh đều có type **REVIEWED**, cùng đi từ **Person** đến **Movie**, nhưng mỗi cạnh mô tả một lần đánh giá. Property **reviewCode**, **score** và **createdAt** có thể khác nhau giữa hai relationship.

Không nên nhầm relationship song song với hai relationship ngược chiều. Relationship trong Neo4j luôn có hướng lưu trữ xác định. Mẫu Cypher có mũi tên như **(a)-[:REVIEWED]->(b)** chỉ khớp theo hướng từ **a** đến **b**; mẫu không có mũi tên như **(a)-[:REVIEWED]-(b)** có thể khớp relationship theo cả hai hướng. Mẫu không có mũi tên không làm thay đổi hướng được lưu trong đồ thị.

Mỗi relationship là một thực thể liên kết riêng trong đồ thị, có thể được truy vấn và cập nhật độc lập. Nếu chỉ trả về node đích, kết quả truy vấn có thể lặp lại cùng một node khi có nhiều relationship cùng khớp. Nếu muốn phân biệt từng lần tương tác, hãy trả về cả relationship hoặc các property nhận diện nó.

## 2. Khi nào cần nhiều relationship cùng type?

Hãy dùng nhiều relationship cùng type khi mỗi liên kết biểu diễn một lần tương tác hoặc một sự kiện riêng giữa hai thực thể, và sự kiện đó có thể được mô tả gọn bằng property của relationship.

| Nghiệp vụ | Node nguồn | Relationship | Node đích | Property ví dụ |
|---|---|---|---|---|
| Đánh giá phim nhiều lần | Person | **REVIEWED** | Movie | reviewCode, score, createdAt |
| Chuyển tiền nhiều lần | Account | **TRANSFERRED** | Account | transferCode, amount, occurredAt |
| Gửi tin nhắn giữa hai người | Person | **SENT_MESSAGE** | Person | messageCode, content, sentAt |
| Theo dõi và bỏ theo dõi rồi theo dõi lại | Person | **FOLLOWED** | Person | followCode, startedAt |

Trước khi tạo nhiều relationship, hãy xác định mỗi cạnh có ý nghĩa riêng hay chỉ là dữ liệu bị lặp do lỗi ghi. Ví dụ, hai bản ghi **REVIEWED** có **reviewCode** khác nhau có thể là hai lần đánh giá hợp lệ. Hai relationship giống hệt nhau được tạo lại do request retry có thể là dữ liệu trùng ngoài ý muốn.

Nếu sự kiện có vòng đời phức tạp, có nhiều thực thể tham gia, hoặc cần được tham chiếu từ nhiều nơi, hãy cân nhắc mô hình sự kiện thành node riêng. Ví dụ một lần chuyển tiền có mã giao dịch, trạng thái xử lý, người phê duyệt, tài khoản nguồn, tài khoản đích và lịch sử thay đổi. Khi đó node **Transfer** kết nối với hai node **Account** có thể rõ nghĩa hơn việc nhồi mọi thông tin vào relationship.

## 3. Tạo relationship song song bằng Cypher

### Dùng CREATE khi mỗi lần gọi là một lần tương tác mới

**CREATE** tạo mới mẫu được chỉ định. Nếu câu lệnh chạy hai lần, hai lần thực thi có thể tạo hai relationship khác nhau ngay cả khi cùng type và cùng cặp node.

~~~cypher
MATCH (p:Person {personCode: $personCode})
MATCH (m:Movie {movieCode: $movieCode})
CREATE (p)-[:REVIEWED {
    reviewCode: $reviewCode1,
    score: 5,
    createdAt: datetime()
}]->(m)
CREATE (p)-[:REVIEWED {
    reviewCode: $reviewCode2,
    score: 4,
    createdAt: datetime()
}]->(m)
~~~

Hai lệnh **CREATE** tạo hai relationship **REVIEWED** độc lập. Chúng cùng nối **p** với **m**, nhưng mang **reviewCode** và **score** khác nhau. Các tham số như **$personCode** và **$reviewCode1** giúp câu lệnh tái sử dụng được và tránh nối dữ liệu đầu vào trực tiếp vào chuỗi Cypher.

Nếu ứng dụng ghi từng đánh giá trong một request, một lệnh tạo một relationship thường dễ kiểm soát hơn:

~~~cypher
MATCH (p:Person {personCode: $personCode})
MATCH (m:Movie {movieCode: $movieCode})
CREATE (p)-[r:REVIEWED {
    reviewCode: $reviewCode,
    score: $score,
    createdAt: datetime()
}]->(m)
RETURN r.reviewCode AS reviewCode, r.score AS score
~~~

**CREATE** phù hợp khi mỗi request thực sự đại diện cho một sự kiện mới. Nếu client có thể gửi lại cùng request sau timeout, hãy thiết kế khóa idempotency hoặc cơ chế nhận diện sự kiện để tránh tạo relationship trùng do retry.

### Dùng MERGE khi cần bảo đảm một relationship theo khóa nghiệp vụ

**MERGE** tìm mẫu đã tồn tại hoặc tạo mẫu đó nếu chưa có. Với nhiều relationship song song, cần xác định chính xác điều gì làm một relationship trở thành cùng một sự kiện. Chỉ ghép type và hai node đầu cuối thường không đủ để phân biệt nhiều lần tương tác.

~~~cypher
MATCH (p:Person {personCode: $personCode})
MATCH (m:Movie {movieCode: $movieCode})
MERGE (p)-[r:REVIEWED {reviewCode: $reviewCode}]->(m)
ON CREATE SET
    r.score = $score,
    r.createdAt = datetime()
RETURN r.reviewCode AS reviewCode, r.score AS score
~~~

Trong ví dụ, **reviewCode** là khóa nghiệp vụ dùng để nhận diện lần đánh giá trong phạm vi cặp người và phim. Nếu chạy lại câu lệnh với cùng hai node và cùng **reviewCode**, **MERGE** có thể khớp relationship đã có thay vì tạo thêm một lần đánh giá. Với **reviewCode** mới, một relationship mới được tạo.

**MERGE** so khớp mẫu và các property được khai báo trong mẫu. Nếu đưa **score** vào mẫu, một lần đánh giá đã tồn tại nhưng có score khác có thể không khớp mẫu đó và dẫn đến tạo relationship khác. Vì vậy, hãy dùng các thuộc tính nhận diện sự kiện trong mẫu **MERGE**; đặt các thuộc tính có thể thay đổi trong **ON CREATE SET** hoặc **ON MATCH SET**.

Trong ví dụ, hai node đầu mút được tìm bằng **MATCH** trước khi gọi **MERGE**. Với relationship merge giữa hai node đã được bind như vậy, Neo4j dùng khóa trên hai node đầu mút khi cần để xử lý các lần ghi đồng thời cùng mẫu. Nếu **reviewCode** phải duy nhất trên tất cả relationship **REVIEWED**, hãy bổ sung relationship property uniqueness constraint. Constraint này được hỗ trợ từ Neo4j 5.7:

~~~cypher
CREATE CONSTRAINT review_code_unique IF NOT EXISTS
FOR ()-[r:REVIEWED]-()
REQUIRE r.reviewCode IS UNIQUE
~~~

Ràng buộc trên bảo vệ tính duy nhất của **reviewCode** trên toàn bộ relationship có type **REVIEWED**, kể cả khi các relationship nối những cặp node khác nhau. Nếu mã chỉ duy nhất trong phạm vi một cặp node, hãy chọn business key phù hợp và thiết kế cách kiểm tra tương ứng. Constraint cũng bảo vệ dữ liệu khi có các luồng ghi khác không đi qua câu lệnh **MERGE** này.

Các thuộc tính **personCode** và **movieCode** dùng để tìm node đầu mút cũng nên được bảo vệ bằng uniqueness constraint để một mã nghiệp vụ không vô tình khớp nhiều node:

~~~cypher
CREATE CONSTRAINT person_code_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personCode IS UNIQUE;

CREATE CONSTRAINT movie_code_unique IF NOT EXISTS
FOR (m:Movie)
REQUIRE m.movieCode IS UNIQUE;
~~~

### Đếm và xem từng relationship

Để liệt kê từng đánh giá, hãy trả về biến relationship:

~~~cypher
MATCH (p:Person {personCode: $personCode})
      -[r:REVIEWED]->
      (m:Movie {movieCode: $movieCode})
RETURN r.reviewCode AS reviewCode,
       r.score AS score,
       r.createdAt AS createdAt
ORDER BY r.createdAt DESC
~~~

Mỗi relationship khớp tạo ra một dòng kết quả. Nếu chỉ trả về **m**, cùng một node phim có thể xuất hiện nhiều lần vì có nhiều relationship **REVIEWED**. Có thể dùng **RETURN DISTINCT m** nếu mục tiêu là danh sách phim duy nhất, nhưng thao tác **DISTINCT** sẽ loại bỏ sự khác biệt về số lần đánh giá.

Để đếm số lần tương tác:

~~~cypher
MATCH (p:Person {personCode: $personCode})
      -[r:REVIEWED]->
      (m:Movie {movieCode: $movieCode})
RETURN count(r) AS reviewCount,
       avg(r.score) AS averageScore
~~~

**count(r)** đếm số relationship phù hợp; **avg(r.score)** tính điểm trung bình của các lần đánh giá. Khi cần thống kê, hãy xác định rõ đang đếm node, relationship hay sự kiện duy nhất theo business key.

## 4. Ánh xạ nhiều relationship trong Spring Data Neo4j

Trong SDN, một trường relationship có thể là collection. Khi mỗi relationship có property riêng, dùng lớp được đánh dấu **@RelationshipProperties**. Mỗi phần tử trong collection đại diện cho một relationship và tham chiếu node đích qua **@TargetNode**.

Ví dụ, **Person** có thể đánh giá cùng một **Movie** nhiều lần:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String personCode;

    @Relationship(
        type = "REVIEWED",
        direction = Relationship.Direction.OUTGOING
    )
    private List<Review> reviews = new ArrayList<>();

    // Constructor, getter và các phương thức miền được lược bớt.
}
~~~

Node đích:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Movie")
public class Movie {

    @Id
    @GeneratedValue
    private Long id;

    private String movieCode;
    private String title;

    // Constructor, getter và setter được lược bớt.
}
~~~

Lớp quan hệ:

~~~java
import java.time.LocalDateTime;

import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class Review {

    @RelationshipId
    private Long id;

    private String reviewCode;
    private int score;
    private LocalDateTime createdAt;

    @TargetNode
    private Movie movie;

    // Constructor, getter và setter được lược bớt.
}
~~~

Ở đây:

- **Person** và **Movie** là node entity.
- **@Relationship(type = "REVIEWED")** xác định type và hướng của các cạnh đi ra từ **Person**.
- **List<Review>** chứa nhiều đối tượng quan hệ, kể cả khi nhiều phần tử cùng trỏ đến một **Movie**.
- **@RelationshipProperties** cho biết **Review** mô tả property của relationship.
- **@TargetNode** xác định node đích của mỗi relationship.
- **@RelationshipId** là định danh nội bộ để SDN nhận diện relationship khi materialize và cập nhật graph. Lớp relationship properties cần có trường này để SDN xác định relationship nào có thể được ghi đè an toàn khi lưu graph.

**reviewCode** là mã nghiệp vụ do ứng dụng quản lý; **id** được đánh dấu **@RelationshipId** phục vụ mapping nội bộ của SDN. Không dùng ID nội bộ của relationship làm mã giao dịch hoặc định danh công khai trong API. Nếu cần tra cứu một lần đánh giá cụ thể từ nghiệp vụ, hãy dùng **reviewCode** và bảo đảm tính duy nhất theo phạm vi đã chọn.

### Vì sao nên dùng List?

Khi nhiều relationship cùng type có thể trỏ đến cùng node đích, **List<Review>** thể hiện trực tiếp số lượng relationship và giữ được nhiều phần tử có cùng target. Dùng **Set** có thể làm mất phần tử nếu **equals()** và **hashCode()** của lớp quan hệ xem hai phần tử là bằng nhau, chẳng hạn chỉ dựa trên **movie**. Nếu nghiệp vụ cần giữ từng lần tương tác, hãy tránh quy tắc equality làm gộp các relationship khác nhau.

Thứ tự phần tử trong Java **List** không tự động có nghĩa là thứ tự tạo relationship trong Neo4j. Khi cần thứ tự theo thời gian, hãy sắp xếp rõ ràng theo **createdAt** trong truy vấn hoặc trong logic ứng dụng.

## 5. Tạo và cập nhật relationship từ repository

Ứng dụng có thể cập nhật object graph rồi lưu entity nguồn. Ví dụ:

~~~java
Review first = new Review(
    "R-100",
    5,
    LocalDateTime.now(),
    movie
);

Review second = new Review(
    "R-101",
    4,
    LocalDateTime.now(),
    movie
);

person.getReviews().add(first);
person.getReviews().add(second);

Person saved = personRepository.save(person);
~~~

Ví dụ minh họa hai đối tượng **Review** khác nhau cùng tham chiếu một **Movie**. SDN dùng collection relationship để lưu các cạnh tương ứng. Lớp **Review** cần constructor và accessor phù hợp với cách ánh xạ của phiên bản SDN mà ứng dụng sử dụng. Nếu thiết kế entity bất biến, hãy thay collection bằng bản sao mới và nhận instance mới từ phương thức miền trước khi gọi **save()**.

Khi relationship đã tồn tại, SDN cần nhận diện đúng cạnh để cập nhật thay vì tạo cạnh mới. **@RelationshipId** cung cấp định danh nội bộ của relationship đã được materialize. Nếu ứng dụng dựng lại một đối tượng quan hệ mới mà không giữ được identity của cạnh cũ, SDN có thể coi đó là relationship mới. Hãy giữ lại các đối tượng quan hệ đã đọc hoặc dùng truy vấn Cypher rõ ràng theo business key khi cập nhật một sự kiện riêng lẻ.

Với truy vấn tùy chỉnh, repository có thể trả về projection chứa dữ liệu của từng relationship:

~~~java
import java.time.LocalDateTime;

public interface ReviewSummary {
    String getReviewCode();
    Integer getScore();
    LocalDateTime getCreatedAt();
    String getMovieTitle();
}
~~~

~~~java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository
        extends Neo4jRepository<Person, Long> {

@Query("""
    MATCH (p:Person {personCode: $personCode})
          -[r:REVIEWED]->
          (m:Movie {movieCode: $movieCode})
    RETURN r.reviewCode AS reviewCode,
           r.score AS score,
           r.createdAt AS createdAt,
           m.title AS movieTitle
    ORDER BY r.createdAt DESC
    """)
List<ReviewSummary> findReviews(
    @Param("personCode") String personCode,
    @Param("movieCode") String movieCode
);
}
~~~

Projection giúp đọc từng lần đánh giá mà không cần tải toàn bộ object graph. Các alias trong **RETURN** phải khớp với property hoặc getter của projection. Nếu trả về entity, hãy viết truy vấn theo quy tắc mapping của SDN và trả về đủ dữ liệu cần thiết để dựng graph.

## 6. Cập nhật hoặc xóa đúng một relationship

Khi có nhiều relationship cùng type giữa hai node, truy vấn chỉ dựa vào hai đầu mút và type sẽ khớp nhiều cạnh. Muốn thay đổi một lần tương tác cụ thể, hãy lọc bằng business key hoặc một thuộc tính nhận diện đủ duy nhất.

Cập nhật điểm của một đánh giá:

~~~cypher
MATCH (p:Person {personCode: $personCode})
      -[r:REVIEWED {reviewCode: $reviewCode}]->
      (m:Movie {movieCode: $movieCode})
SET r.score = $newScore
RETURN r.reviewCode AS reviewCode, r.score AS score
~~~

Xóa một đánh giá:

~~~cypher
MATCH (p:Person {personCode: $personCode})
      -[r:REVIEWED {reviewCode: $reviewCode}]->
      (m:Movie {movieCode: $movieCode})
DELETE r
~~~

Điều kiện **reviewCode** phải nhận diện đúng một đánh giá trong phạm vi cặp node. Nếu mã không duy nhất, câu lệnh có thể cập nhật hoặc xóa nhiều relationship. Trong trường hợp cần bảo đảm duy nhất, hãy thiết kế constraint phù hợp hoặc mô hình sự kiện thành node có khóa duy nhất.

Ngược lại, truy vấn dưới đây sẽ xóa tất cả relationship **REVIEWED** giữa người và phim đã chọn:

~~~cypher
MATCH (p:Person {personCode: $personCode})
      -[r:REVIEWED]->
      (m:Movie {movieCode: $movieCode})
DELETE r
~~~

Chỉ dùng mẫu xóa nhiều cạnh khi nghiệp vụ thực sự yêu cầu xóa toàn bộ lịch sử đánh giá của cặp node đó. Nếu cần xóa một sự kiện, hãy bổ sung điều kiện nhận diện trước khi thực thi.

## 7. Khi nào nên chuyển relationship thành node sự kiện?

Relationship properties phù hợp với sự kiện gọn, gắn chặt với đúng hai node và không cần có quan hệ riêng. Khi sự kiện trở thành đối tượng nghiệp vụ độc lập, hãy cân nhắc mô hình nó thành node.

| Tiêu chí | Relationship có properties | Node sự kiện |
|---|---|---|
| Số đầu mút chính | Hai node | Có thể kết nối nhiều node |
| Thuộc tính riêng | Có | Có |
| Định danh nghiệp vụ độc lập | Có thể lưu property, nhưng identity vẫn là relationship | Tự nhiên hơn với ID hoặc business key riêng |
| Quan hệ với các thực thể khác | Hạn chế, thường phải đi qua hai đầu mút | Có thể có nhiều relationship riêng |
| Ví dụ | Một lần đánh giá phim | Đơn hàng, giao dịch chuyển tiền có vòng đời, phiếu hỗ trợ |

Ví dụ mô hình một giao dịch thành node:

~~~cypher
(source:Account)-[:SENT]->(transfer:Transfer)
(transfer)-[:RECEIVED_BY]->(target:Account)
~~~

Node **Transfer** có thể lưu mã giao dịch, số tiền, trạng thái và thời gian; các node khác như người phê duyệt hoặc yêu cầu hoàn tiền có thể kết nối trực tiếp với giao dịch. Cách mô hình này tránh biến một relationship thành nơi chứa quá nhiều thông tin và giúp sự kiện có vòng đời riêng.

## 8. Những lỗi thường gặp

**Cho rằng một cặp node chỉ có một relationship cho mỗi type.** Neo4j cho phép nhiều cạnh song song. Hãy kiểm tra số relationship thực tế thay vì giả định một cặp node chỉ có một liên kết.

**Dùng MERGE mà không xác định business key.** Nếu chỉ dùng type và hai đầu mút, các lần tương tác khác nhau có thể bị gộp hoặc không được nhận diện đúng. Hãy xác định thuộc tính nào phân biệt từng sự kiện.

**Dùng CREATE khi request có thể retry.** Request lặp có thể tạo nhiều relationship giống nhau. Hãy dùng khóa idempotency và chiến lược MERGE phù hợp với khóa đó.

**Chỉ trả về node đích khi cần phân biệt các cạnh.** Nhiều relationship có thể làm cùng node xuất hiện nhiều lần trong kết quả. Hãy trả về biến relationship và property nhận diện.

**Dùng Set cho các lần tương tác có thể trùng target.** Quy tắc **equals()** và **hashCode()** có thể làm mất phần tử. Dùng **List** khi cần bảo toàn từng relationship.

**Cập nhật hoặc xóa bằng type và hai đầu mút.** Mẫu này có thể khớp mọi relationship song song. Thêm business key hoặc điều kiện đủ chọn lọc.

**Dùng relationship ID nội bộ làm mã nghiệp vụ.** Hãy lưu một mã nghiệp vụ riêng, ổn định và có quy tắc duy nhất rõ ràng.

## 9. Tự kiểm tra

1. Neo4j có cho phép hai node được nối bằng nhiều relationship cùng type và cùng hướng không? Mỗi relationship có thể khác nhau ở điểm nào?
2. Khi nào nên dùng **CREATE**, khi nào nên dùng **MERGE** để ghi relationship?
3. Vì sao **List<Review>** phù hợp hơn **Set<Review>** nếu nhiều đánh giá cùng trỏ đến một bộ phim?
4. **@RelationshipId** và **reviewCode** khác nhau như thế nào?
5. Vì sao câu lệnh xóa chỉ lọc theo hai node và relationship type có thể xóa nhiều cạnh?
6. Nêu một dấu hiệu cho thấy sự kiện nên được mô hình hóa thành node thay vì relationship properties.

**Bài tập thực hành:** Thiết kế graph cho nghiệp vụ một tài khoản có thể chuyển tiền nhiều lần cho cùng một tài khoản đích. Mỗi lần chuyển có mã giao dịch, số tiền, thời điểm và trạng thái. Viết hai câu Cypher: một câu dùng **CREATE** để ghi một giao dịch mới và một câu dùng **MERGE** theo mã giao dịch để xử lý request retry. Sau đó mô hình **Account** với **List<TransferRelationship>** và lớp **@RelationshipProperties** tương ứng trong SDN. Viết truy vấn trả về từng giao dịch, rồi viết truy vấn cập nhật trạng thái đúng một giao dịch theo mã giao dịch.

## Tài liệu tham khảo

- [Spring Data Neo4j — Metadata-based Mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
- [Neo4j Cypher Manual — CREATE](https://neo4j.com/docs/cypher-manual/current/clauses/create/)
- [Neo4j Cypher Manual — MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Neo4j Cypher Manual — Constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/)
