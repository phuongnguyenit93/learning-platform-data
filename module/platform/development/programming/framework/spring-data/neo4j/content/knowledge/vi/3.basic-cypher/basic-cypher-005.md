# DELETE, DETACH DELETE và phạm vi xóa dữ liệu

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt DELETE và DETACH DELETE trong Cypher.
- Xóa relationship độc lập hoặc xóa node cùng các relationship gắn với node đó.
- Dự đoán chính xác node nào còn lại sau một truy vấn xóa.
- Giới hạn phạm vi xóa bằng MATCH và WHERE, đồng thời kiểm tra tập dữ liệu trước khi thực thi.
- Quản lý thao tác xóa trong transaction và nhận biết rủi ro khi xóa theo lô.

Trong Neo4j, node và relationship là hai thành phần dữ liệu riêng biệt của property graph. Một node có thể nối với nhiều node khác thông qua relationship có hướng và có kiểu. Vì vậy, khi xóa dữ liệu, cần xác định rõ muốn xóa một relationship, một node đã cô lập, hay một node cùng tất cả liên kết trực tiếp của nó.

Spring Data Neo4j cho phép gửi các câu lệnh Cypher này qua repository hoặc client trong ứng dụng Spring. Hiểu đúng phạm vi tác động của DELETE và DETACH DELETE giúp tránh xóa nhầm một phần lớn đồ thị.

## 1. DELETE dùng để xóa relationship hoặc node đã không còn liên kết

DELETE là mệnh đề xóa trong Cypher. Nó có thể xóa relationship được MATCH và có thể xóa node nếu node đó không còn relationship nào gắn với nó.

### Xóa một relationship

Giả sử đồ thị có hai người và một liên kết bạn bè:

~~~cypher
MATCH (an:Person {personId: 'P-100'})-[r:KNOWS]->(binh:Person {personId: 'P-200'})
DELETE r
~~~

Truy vấn tìm relationship KNOWS có hướng từ An đến Bình, sau đó xóa chính relationship đó. Hai node Person vẫn tồn tại. Những relationship khác gắn với An hoặc Bình cũng không bị tác động.

Nếu muốn xóa mọi relationship KNOWS giữa hai node theo cả hai hướng, cần MATCH đúng cả hai chiều:

~~~cypher
MATCH (an:Person {personId: 'P-100'})-[r:KNOWS]-(binh:Person {personId: 'P-200'})
DELETE r
~~~

Dấu gạch ngang không có mũi tên trong mẫu relationship biểu thị việc khớp theo cả hai hướng. Cần chọn mẫu phù hợp với quy tắc dữ liệu của ứng dụng.

### Xóa một node không có relationship

Một node cô lập, tức không có relationship đi vào hoặc đi ra, có thể được xóa bằng DELETE:

~~~cypher
MATCH (draft:Article {articleId: 'A-900', status: 'DRAFT'})
DELETE draft
~~~

Nếu node còn bất kỳ relationship nào, truy vấn DELETE node sẽ thất bại. Neo4j không tự bỏ các relationship để hoàn tất thao tác này. Điều kiện này bảo vệ tính toàn vẹn cấu trúc của đồ thị, tránh để lại relationship trỏ đến node không còn tồn tại.

Ví dụ sau có thể gây lỗi nếu An còn kết nối với bất kỳ node nào:

~~~cypher
MATCH (p:Person {personId: 'P-100'})
DELETE p
~~~

Thông báo lỗi cụ thể phụ thuộc phiên bản, nhưng nguyên nhân là node đang có relationship. Nếu nghiệp vụ yêu cầu giữ lại các node liên quan, hãy xóa relationship được chọn trước rồi mới xóa node khi nó đã cô lập. Nếu nghiệp vụ yêu cầu bỏ toàn bộ liên kết trực tiếp của node, dùng DETACH DELETE.

## 2. DETACH DELETE xóa node và relationship gắn trực tiếp với node

DETACH DELETE xóa node được chỉ định cùng tất cả relationship đi vào hoặc đi ra từ node đó. Các node ở đầu còn lại của những relationship này vẫn tồn tại.

Ví dụ:

~~~cypher
MATCH (p:Person {personId: 'P-100'})
DETACH DELETE p
~~~

Giả sử An có các liên kết sau:

~~~text
(An:Person)-[:KNOWS]->(Binh:Person)
(Chi:Person)-[:FOLLOWS]->(An:Person)
(An:Person)-[:PURCHASED]->(Book:Product)
~~~

Sau khi thực thi DETACH DELETE An:

- Node An bị xóa.
- Relationship KNOWS, FOLLOWS và PURCHASED gắn trực tiếp với An bị xóa.
- Node Bình, Chi và Book vẫn còn.
- Các relationship khác giữa Bình, Chi và Book không bị tác động.

Đây là điểm cần nhớ: DETACH DELETE xóa node cùng các relationship kề trực tiếp, không tự động xóa đệ quy các node ở đầu kia hoặc toàn bộ vùng đồ thị có thể đi tới từ node đó.

### So sánh DELETE và DETACH DELETE

| Mệnh đề | Đối tượng được xóa | Điều kiện và phạm vi |
|---|---|---|
| DELETE r | Relationship r | Xóa relationship đã khớp; các node ở hai đầu vẫn còn |
| DELETE n | Node n | Chỉ thành công khi n không còn relationship |
| DETACH DELETE n | Node n và mọi relationship gắn trực tiếp với n | Các node ở đầu kia của relationship vẫn còn |

DETACH là thao tác tách node khỏi các liên kết trước khi xóa node. Nó không có nghĩa là xóa toàn bộ node liên quan, không phải cơ chế cascade delete theo cây đối tượng và cũng không tự đi theo một đường dẫn nhiều bước.

### Xóa nhiều node cùng lúc

Có thể MATCH nhiều node và xóa tất cả bằng một câu lệnh:

~~~cypher
MATCH (p:Person)
WHERE p.status = 'INACTIVE'
DETACH DELETE p
~~~

Tập node được xóa là những Person có status bằng INACTIVE. Tất cả relationship gắn với từng node được chọn cũng bị xóa. Một node khác nhãn ở đầu kia của relationship vẫn tồn tại, kể cả khi relationship giữa nó và Person bị xóa.

Cần đặc biệt chú ý phạm vi của MATCH. Nếu bỏ WHERE trong ví dụ trên, truy vấn sẽ chọn mọi node có nhãn Person. Nếu một Person có liên kết tới Movie, Order hoặc node thuộc nhãn khác, những relationship đó cũng bị xóa khi Person bị detach.

## 3. MATCH và WHERE quyết định phạm vi xóa

DELETE và DETACH DELETE tác động lên các biến đã được MATCH. Do đó, độ chính xác của mẫu MATCH và điều kiện WHERE quyết định dữ liệu nào bị xóa.

### Xác định đối tượng bằng khóa nghiệp vụ

Khi xóa một thực thể cụ thể, nên dùng thuộc tính định danh ổn định và duy nhất:

~~~cypher
MATCH (p:Person {personId: $personId})
DETACH DELETE p
~~~

Tham số personId được truyền từ ứng dụng. Để giả định mỗi mã chỉ xác định một Person, mô hình dữ liệu cần bảo đảm tính duy nhất bằng constraint thích hợp, ví dụ:

~~~cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE
~~~

Constraint giúp ngăn nhiều node Person có cùng personId. Nếu dữ liệu cũ đã vi phạm điều kiện duy nhất, cần xử lý dữ liệu trước khi tạo constraint.

### Kết hợp nhiều điều kiện

Có thể dùng WHERE để giới hạn đối tượng theo nhiều thuộc tính:

~~~cypher
MATCH (p:Person)
WHERE p.status = 'INACTIVE'
  AND p.lastActiveAt < date('2024-01-01')
DETACH DELETE p
~~~

Câu lệnh này chỉ chọn Person thỏa mãn cả hai điều kiện. Trong hệ thống thực tế, hãy xác định rõ ý nghĩa của thời điểm, múi giờ và giá trị thiếu trước khi dùng điều kiện thời gian làm căn cứ xóa dữ liệu.

Có thể lọc relationship trước khi xóa node nếu nghiệp vụ chỉ yêu cầu xóa một loại liên kết. Ví dụ sau chỉ xóa các relationship FOLLOWS được MATCH:

~~~cypher
MATCH (p:Person {personId: $personId})-[r:FOLLOWS]->()
DELETE r
~~~

Node Person vẫn còn, và các relationship loại khác cũng được giữ lại.

### Không có kết quả MATCH thì sao?

Nếu MATCH không tìm thấy node hoặc relationship, truy vấn xóa không có đối tượng để xử lý và không xóa dữ liệu. Đây là hành vi hữu ích khi ứng dụng gọi thao tác xóa lặp lại, nhưng ứng dụng vẫn nên quyết định rõ cách phản hồi khi không tìm thấy bản ghi cần xóa.

## 4. Xóa node được chọn không đồng nghĩa xóa toàn bộ đồ thị liên quan

Một nhầm lẫn thường gặp là cho rằng DETACH DELETE sẽ xóa cả những node có quan hệ với node đích. Hãy xem đồ thị:

~~~text
(UserA)-[:MEMBER_OF]->(Team)
(Team)-[:OWNS]->(Project)
(UserB)-[:MEMBER_OF]->(Team)
~~~

Nếu chạy:

~~~cypher
MATCH (u:User {userId: 'A'})
DETACH DELETE u
~~~

Chỉ UserA và relationship MEMBER_OF của UserA bị xóa. Team, Project, UserB và các relationship còn lại giữa chúng vẫn tồn tại.

Nếu muốn xóa cả Team, phải MATCH và xóa Team một cách rõ ràng. Tuy nhiên, điều đó có thể ảnh hưởng đến UserB và Project. Hãy mô tả chính xác tập node cần xóa trong truy vấn và kiểm tra các liên kết liên quan trước khi thực thi.

Ví dụ xóa một Team cùng các relationship trực tiếp:

~~~cypher
MATCH (t:Team {teamId: $teamId})
DETACH DELETE t
~~~

UserA, UserB và Project vẫn tồn tại sau thao tác này, nhưng các relationship MEMBER_OF và OWNS nối trực tiếp với Team bị xóa. Nếu nghiệp vụ yêu cầu xóa cả Project hoặc thành viên, phải xây dựng quy tắc và MATCH riêng cho các node đó.

## 5. Xóa toàn bộ node trong phạm vi database

Một câu lệnh thường gặp khi làm sạch dữ liệu thử nghiệm là:

~~~cypher
MATCH (n)
DETACH DELETE n
~~~

MATCH (n) khớp tất cả node trong graph hiện tại. DETACH DELETE xóa tất cả node được khớp cùng relationship gắn với chúng. Đây là thao tác có phạm vi rất rộng và có thể làm mất toàn bộ dữ liệu nghiệp vụ trong database đang kết nối.

Lệnh này không tương đương với việc xóa database hoặc xóa schema. Các index và constraint là thành phần schema được quản lý riêng; xóa node không tự động xóa định nghĩa index hoặc constraint. Những cấu trúc schema đó vẫn tồn tại cho đến khi được quản lý bằng các lệnh schema tương ứng.

Không chạy câu lệnh này trong môi trường có dữ liệu cần giữ lại. Khi cần làm sạch một phần dữ liệu, hãy MATCH theo nhãn, khóa hoặc điều kiện nghiệp vụ cụ thể. Với dữ liệu dùng chung giữa nhiều nhóm hoặc dịch vụ, cần xác định database và môi trường kết nối trước khi thực thi.

## 6. Kiểm tra trước khi xóa

Một quy trình an toàn bắt đầu bằng việc chạy chính mẫu MATCH dưới dạng truy vấn đọc để xem tập đối tượng dự kiến bị tác động.

### Bước 1: Đếm số node sẽ bị chọn

Thay vì xóa ngay, chạy:

~~~cypher
MATCH (p:Person)
WHERE p.status = 'INACTIVE'
RETURN count(p) AS candidateCount
~~~

Kết quả cho biết có bao nhiêu Person thỏa điều kiện. Nếu số lượng bất ngờ, hãy dừng lại và kiểm tra điều kiện.

### Bước 2: Xem các node cụ thể

~~~cypher
MATCH (p:Person)
WHERE p.status = 'INACTIVE'
RETURN p.personId AS personId, p.name AS name, p.status AS status
ORDER BY personId
LIMIT 50
~~~

Xem các mã và thông tin đại diện giúp phát hiện điều kiện WHERE quá rộng, dữ liệu bất thường hoặc nhầm lẫn giữa các môi trường.

### Bước 3: Kiểm tra relationship bị ảnh hưởng

~~~cypher
MATCH (p:Person)
WHERE p.status = 'INACTIVE'
OPTIONAL MATCH (p)-[r]-()
RETURN p.personId AS personId, count(r) AS connectedRelationships
ORDER BY personId
~~~

Truy vấn này cho biết mỗi Person có bao nhiêu relationship đi vào hoặc đi ra. OPTIONAL MATCH giữ lại cả Person không có relationship. Khi đếm, count(r) bỏ qua giá trị null nên node cô lập có số lượng bằng 0.

### Bước 4: Chạy lệnh xóa với cùng điều kiện

Sau khi xác nhận đúng tập dữ liệu, dùng lại chính mẫu MATCH và WHERE:

~~~cypher
MATCH (p:Person)
WHERE p.status = 'INACTIVE'
DETACH DELETE p
~~~

Trong môi trường có dữ liệu thay đổi đồng thời, kết quả kiểm tra trước đó có thể khác tập dữ liệu tại thời điểm xóa. Với thao tác quan trọng, hãy phối hợp ranh giới transaction, quyền truy cập, quy trình phê duyệt và cửa sổ bảo trì phù hợp.

## 7. Transaction và xóa dữ liệu theo lô

Một câu lệnh DELETE hoặc DETACH DELETE thông thường được thực thi trong transaction. Nếu câu lệnh thất bại, transaction có thể rollback thay đổi của câu lệnh đó. Khi một nghiệp vụ gồm nhiều thao tác liên quan, có thể đặt chúng trong cùng transaction để bảo đảm tính nhất quán.

Trong ứng dụng Spring Data Neo4j, có thể khai báo truy vấn xóa tại repository:

~~~java
public interface PersonRepository extends Neo4jRepository<Person, Long> {

    @Query("""
        MATCH (p:Person {personId: $personId})
        DETACH DELETE p
        """)
    void deletePersonGraphByPersonId(String personId);
}
~~~

Tên phương thức là do ứng dụng đặt; nội dung Cypher quyết định hành vi thực tế. Với thao tác xóa được gọi từ tầng dịch vụ, có thể đặt ranh giới giao dịch ở tầng dịch vụ:

~~~java
@Service
public class PersonService {

    private final PersonRepository people;

    public PersonService(PersonRepository people) {
        this.people = people;
    }

    @Transactional
    public void removePerson(String personId) {
        people.deletePersonGraphByPersonId(personId);
    }
}
~~~

Ví dụ tập trung vào vị trí đặt transaction; ứng dụng cần cấu hình Spring Data Neo4j và transaction manager tương ứng. Hãy kiểm tra hành vi thực tế của phương thức repository với phiên bản SDN đang dùng và thiết kế phản hồi phù hợp khi mã personId không tồn tại.

### Khi nào cần xóa theo lô?

Một transaction xóa quá nhiều node và relationship có thể tiêu thụ nhiều bộ nhớ, giữ khóa lâu và làm tăng thời gian ảnh hưởng đến các thao tác khác. Với tập dữ liệu lớn, có thể chia công việc thành nhiều transaction nhỏ bằng subquery transaction nếu phiên bản Neo4j hỗ trợ:

~~~cypher
MATCH (p:Person)
WHERE p.status = 'INACTIVE'
CALL {
    WITH p
    DETACH DELETE p
} IN TRANSACTIONS OF 500 ROWS
~~~

Mẫu này đưa các dòng đầu vào qua subquery và thực hiện xóa theo các nhóm 500 dòng. Cú pháp IN TRANSACTIONS cần được chạy trong implicit transaction, chẳng hạn một lần gửi truy vấn trực tiếp từ Neo4j Browser hoặc driver ở chế độ auto-commit; không đặt truy vấn này bên trong một transaction tường minh đang mở, chẳng hạn phương thức dịch vụ đã được bao bởi @Transactional.

Các batch có thể commit độc lập. Nếu một batch sau gặp lỗi, các batch đã commit trước đó vẫn giữ kết quả. Vì vậy, trước khi dùng cách này, cần chuẩn bị khả năng chạy tiếp, ghi nhận tiến độ và xử lý dữ liệu còn lại. Hãy thử trên dữ liệu đại diện và chọn kích thước batch phù hợp với tải của hệ thống.

Nếu chỉ muốn xóa tối đa một số lượng nhỏ để kiểm tra, có thể giới hạn tập MATCH:

~~~cypher
MATCH (p:Person)
WHERE p.status = 'INACTIVE'
WITH p
ORDER BY p.personId
LIMIT 100
DETACH DELETE p
~~~

Truy vấn này chỉ xử lý tối đa 100 dòng được chọn trong lần chạy đó. ORDER BY giúp thứ tự lựa chọn rõ ràng nếu personId có giá trị phù hợp. Đây không phải cơ chế tự động tiếp tục các batch; muốn xóa phần còn lại, ứng dụng cần gọi lại có kiểm soát và xác minh số lượng còn lại.

## 8. Các lỗi và nhầm lẫn thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| DELETE node báo lỗi | Node vẫn có relationship đi vào hoặc đi ra | Xóa relationship cần thiết trước, hoặc dùng DETACH DELETE nếu nghiệp vụ cho phép |
| Xóa một Person làm mất liên kết tới node khác | DETACH DELETE xóa mọi relationship trực tiếp của Person | Kiểm tra các relationship và node ở đầu kia trước khi xóa |
| Xóa nhiều dữ liệu hơn dự kiến | MATCH thiếu điều kiện hoặc WHERE không đủ chặt | Chạy truy vấn RETURN trước, kiểm tra số lượng và mẫu dữ liệu |
| Không xóa được node nào | MATCH không tìm thấy node hoặc điều kiện không khớp | Kiểm tra nhãn, khóa, kiểu dữ liệu và giá trị điều kiện |
| Dùng DETACH DELETE cho relationship | DETACH DELETE nhận node làm đối tượng xóa | Dùng DELETE r cho relationship |
| Muốn xóa thuộc tính nhưng lại xóa node | Nhầm thao tác xóa node với xóa property | Dùng REMOVE cho property hoặc label theo cú pháp Cypher phù hợp |
| Xóa lô lớn bị gián đoạn | Transaction quá lớn hoặc batch sau gặp lỗi | Chia lô, theo dõi tiến độ và thiết kế cách tiếp tục an toàn |

Một nguyên tắc hữu ích là luôn đọc lại câu lệnh như một câu mô tả nghiệp vụ: “Tôi đang MATCH những node nào, relationship nào; DELETE sẽ xóa đúng biến nào; DETACH sẽ loại bỏ những liên kết trực tiếp nào?” Nếu không thể trả lời rõ, chưa nên thực thi.

## 9. Bài tập thực hành

Giả sử graph có các node Person, Team và Project. Person có thể MEMBER_OF Team; Team có thể OWNS Project; Person cũng có thể KNOWS Person.

Hãy viết và giải thích các truy vấn sau:

1. Xóa relationship KNOWS từ An đến Bình, giữ nguyên cả hai node.
2. Xóa một Person có personId được truyền vào cùng mọi relationship trực tiếp của người đó.
3. Tìm các Person có status là INACTIVE, đếm số lượng và hiển thị tối đa 20 mã trước khi xóa.
4. Xóa Team theo teamId và giải thích điều gì xảy ra với Person, Project và các relationship của chúng.
5. Viết một truy vấn xóa tối đa 50 Person theo thứ tự personId, rồi giải thích vì sao truy vấn đó chỉ xử lý một phần dữ liệu trong lần chạy.
6. Giải thích khác biệt về khả năng rollback giữa một transaction xóa duy nhất và thao tác xóa chia thành nhiều batch IN TRANSACTIONS.

Gợi ý kiểm tra:

- Với câu 1, biến được DELETE phải là relationship.
- Với câu 2 và 4, hãy liệt kê node đích cùng toàn bộ relationship trực tiếp sẽ bị xóa.
- Với câu 3 và 5, dùng cùng điều kiện lọc ở truy vấn kiểm tra và truy vấn xóa.
- Với câu 6, phân biệt rollback của một transaction với các batch đã commit độc lập.

## 10. Kết luận

DELETE xóa relationship hoặc node đã cô lập. DETACH DELETE xóa node cùng tất cả relationship gắn trực tiếp với node đó; các node ở đầu kia của relationship vẫn tồn tại. Phạm vi dữ liệu bị tác động bắt đầu từ các biến được MATCH, vì vậy điều kiện MATCH và WHERE cần được thiết kế, kiểm tra kỹ lưỡng.

Khi đưa thao tác xóa vào ứng dụng Spring Data Neo4j, hãy chọn đúng Cypher, đặt ranh giới transaction phù hợp, dùng tham số cho dữ liệu đầu vào và kiểm tra trước số lượng đối tượng sẽ bị xóa. Với tập dữ liệu lớn, chia batch có thể giảm áp lực của một transaction dài, nhưng cần tính đến việc mỗi batch commit độc lập và có thể để lại tiến độ một phần khi xảy ra lỗi.
