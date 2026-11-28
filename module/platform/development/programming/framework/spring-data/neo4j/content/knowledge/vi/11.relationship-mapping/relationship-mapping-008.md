# Phân biệt xóa relationship với xóa node được liên kết

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt thao tác xóa một relationship với thao tác xóa node ở hai đầu.
- Giải thích sự khác nhau giữa Cypher DELETE và DETACH DELETE.
- Viết truy vấn xóa đúng đối tượng, có điều kiện rõ ràng.
- Dùng Neo4jClient trong Spring Data Neo4j để thực hiện thao tác xóa relationship hoặc node.
- Nhận biết ảnh hưởng đến dữ liệu liên quan, transaction và các trường hợp xóa nhầm thường gặp.

## 1. Relationship và node là hai loại phần tử khác nhau

Trong Neo4j, node biểu diễn thực thể, còn relationship biểu diễn liên kết có hướng và có kiểu giữa hai node. Ví dụ, hai người có thể quen biết nhau:

~~~text
(An:Person)-[:KNOWS]->(Binh:Person)
~~~

Ở đây có ba phần tử đồ thị:

- Node An.
- Node Bình.
- Relationship KNOWS nối An với Bình.

Khi nghiệp vụ yêu cầu hai người không còn quen biết, ta thường chỉ cần xóa relationship. Hai node Person vẫn tồn tại và vẫn có thể tham gia các relationship khác.

Ngược lại, khi nghiệp vụ yêu cầu xóa hồ sơ của An khỏi hệ thống, ta cần xóa node An. Vì node có thể đang liên kết với nhiều node khác, trước khi xóa phải xác định cách xử lý tất cả relationship gắn với nó.

Đây là khác biệt quan trọng: xóa một liên kết làm thay đổi cấu trúc kết nối của đồ thị; xóa một node loại bỏ thực thể và đòi hỏi xử lý các liên kết gắn với thực thể đó.

## 2. Xóa một relationship bằng DELETE

Để xóa relationship, truy vấn phải tìm đúng relationship và gán nó cho một biến. Sau đó dùng DELETE với biến relationship:

~~~cypher
MATCH (a:Person {personId: "person-101"})
      -[r:KNOWS]->
      (b:Person {personId: "person-202"})
DELETE r
~~~

Truy vấn trên tìm relationship có kiểu KNOWS đi từ An đến Bình và xóa chính relationship đó. Hai node Person ở hai đầu vẫn được giữ lại.

Có thể hình dung trước và sau thao tác:

~~~text
Trước:
(An:Person)-[:KNOWS]->(Binh:Person)

Sau DELETE r:
(An:Person)       (Binh:Person)
~~~

Nếu hai node còn relationship khác, những relationship đó vẫn tồn tại. Ví dụ:

~~~text
Trước:
(An)-[:KNOWS]->(Binh)
(An)-[:WORKS_WITH]->(Binh)
(An)-[:LIVES_IN]->(Hanoi)

Sau khi xóa KNOWS:
(An)       (Binh)
  \
   -[:WORKS_WITH]->(Binh)
  \
   -[:LIVES_IN]->(Hanoi)
~~~

Trong thực tế, hai node vẫn có thể kết nối qua những relationship còn lại. Lệnh DELETE chỉ tác động lên biến relationship được chỉ định trong truy vấn.

### Xóa relationship theo thuộc tính

Nếu giữa cùng hai node có nhiều relationship cùng kiểu, truy vấn chỉ dựa trên hai đầu node và kiểu relationship có thể khớp nhiều relationship. Ví dụ, một người có thể theo dõi một tài khoản nhiều lần theo các mốc nghiệp vụ khác nhau, hoặc hai node có nhiều relationship cùng loại mang các thuộc tính khác nhau.

Khi cần xóa một relationship cụ thể, hãy đưa thuộc tính định danh của relationship vào điều kiện:

~~~cypher
MATCH (a:Person)-[r:KNOWS]->(b:Person)
WHERE r.linkId = "link-9001"
DELETE r
~~~

Trong ví dụ, linkId là mã nghiệp vụ do ứng dụng quản lý và cần được bảo đảm duy nhất trong phạm vi mà nghiệp vụ yêu cầu. Nếu không có điều kiện đủ cụ thể, một truy vấn có thể xóa nhiều relationship cùng khớp.

Có thể dùng mẫu không chỉ định hướng nếu nghiệp vụ cần tìm liên kết giữa hai node bất kể chiều:

~~~cypher
MATCH (a:Person {personId: "person-101"})
      -[r:KNOWS]-
      (b:Person {personId: "person-202"})
DELETE r
~~~

Mẫu không định hướng khớp relationship nối hai node theo một trong hai chiều. Bản thân relationship vẫn giữ hướng đã được lưu; truy vấn chỉ đang tìm nó theo cách không ràng buộc hướng.

## 3. DELETE node và điều kiện không còn relationship

Lệnh DELETE có thể xóa node khi node không còn relationship gắn với nó:

~~~cypher
MATCH (p:Person {personId: "person-101"})
DELETE p
~~~

Nếu node Person đang có bất kỳ relationship nào, Neo4j từ chối thao tác và báo lỗi vì node vẫn được kết nối. Điều kiện này giúp tránh vô tình xóa một thực thể trong khi các liên kết của nó còn tồn tại.

Muốn xóa node bằng DELETE, ứng dụng phải bảo đảm tất cả relationship liên quan đã được xử lý trước. Có thể xóa từng relationship theo nghiệp vụ rồi mới xóa node:

~~~cypher
MATCH (p:Person {personId: "person-101"})-[r]-()
DELETE r
~~~

Sau đó mới thực hiện:

~~~cypher
MATCH (p:Person {personId: "person-101"})
DELETE p
~~~

Truy vấn đầu tiên xóa mọi relationship nối trực tiếp với Person có mã đã chỉ định, bao gồm relationship đi vào và đi ra. Các node ở đầu còn lại vẫn tồn tại. Truy vấn thứ hai xóa node khi nó đã không còn relationship.

Cách tách bước này hữu ích khi ứng dụng cần áp dụng quy tắc riêng cho từng loại relationship, ví dụ lưu lịch sử, chuyển liên kết sang node khác hoặc chỉ xóa một số loại liên kết. Nếu có yêu cầu tất cả bước phải cùng thành công hoặc cùng rollback, hãy đặt chúng trong cùng một transaction.

## 4. DETACH DELETE: xóa node cùng tất cả relationship gắn trực tiếp

Khi nghiệp vụ yêu cầu xóa node và loại bỏ mọi relationship gắn với node đó, Cypher cung cấp DETACH DELETE:

~~~cypher
MATCH (p:Person {personId: "person-101"})
DETACH DELETE p
~~~

DETACH DELETE thực hiện hai việc trong cùng thao tác:

1. Xóa tất cả relationship đi vào hoặc đi ra khỏi node được chọn.
2. Xóa node đó.

Ví dụ trước khi xóa:

~~~text
(Binh:Person)<-[:KNOWS]-(An:Person)-[:LIVES_IN]->(Hanoi:City)
(An:Person)-[:WORKS_WITH]->(Chi:Person)
~~~

Sau DETACH DELETE An:

~~~text
(Binh)                 (Hanoi)       (Chi)
~~~

Các node Bình, Hà Nội và Chi vẫn tồn tại. Chỉ An và những relationship nối trực tiếp với An bị xóa. Những relationship khác giữa các node còn lại không bị tác động.

Bảng sau tóm tắt hành vi:

| Lệnh | Đối tượng bị xóa | Điều kiện và ảnh hưởng |
|---|---|---|
| DELETE r | Relationship r | Giữ nguyên hai node ở hai đầu |
| DELETE n | Node n | Chỉ thành công khi n không còn relationship |
| DETACH DELETE n | Node n và mọi relationship gắn trực tiếp với n | Các node lân cận vẫn được giữ |

DETACH DELETE không có nghĩa là xóa toàn bộ vùng đồ thị có thể đi tới từ node. Nó chỉ xóa node được chọn và các relationship gắn trực tiếp với node đó. Các node lân cận và những liên kết khác của chúng vẫn còn.

## 5. Chọn thao tác theo yêu cầu nghiệp vụ

Trước khi viết lệnh xóa, hãy xác định chính xác đối tượng cần biến mất khỏi đồ thị.

| Yêu cầu nghiệp vụ | Thao tác phù hợp | Kết quả |
|---|---|---|
| Hai người không còn là bạn | DELETE relationship FRIENDS_WITH | Hai Person vẫn tồn tại |
| Một nhân viên rời một phòng ban | DELETE relationship WORKS_IN | Nhân viên và phòng ban vẫn tồn tại |
| Xóa một hồ sơ Person và bỏ mọi liên kết của hồ sơ đó | DETACH DELETE node Person | Person và relationship gắn trực tiếp bị xóa |
| Chỉ xóa node đã không còn liên kết | DELETE node | Node bị xóa nếu không còn relationship |
| Xóa một số liên kết trước, sau đó xóa node | DELETE relationship theo điều kiện, rồi DELETE node | Có thể áp dụng quy tắc cho từng loại liên kết |

Ví dụ, một nhân viên chuyển phòng ban không đồng nghĩa với việc xóa node nhân viên hoặc node phòng ban. Ứng dụng cần xóa relationship WORKS_IN cũ và tạo relationship WORKS_IN mới đến phòng ban mới.

~~~cypher
MATCH (p:Person {personId: "employee-10"})
      -[old:WORKS_IN]->
      (oldDepartment:Department)
DELETE old
~~~

Sau khi xóa liên kết cũ, ứng dụng có thể tạo liên kết mới bằng CREATE hoặc MERGE tùy quy tắc nghiệp vụ:

~~~cypher
MATCH (p:Person {personId: "employee-10"})
MATCH (d:Department {departmentCode: "engineering"})
MERGE (p)-[:WORKS_IN]->(d)
~~~

Cả node nhân viên và hai node phòng ban vẫn được giữ lại. Chỉ mối quan hệ cũ bị thay thế bằng mối quan hệ mới.

## 6. Thực hiện thao tác xóa bằng Spring Data Neo4j

Spring Data Neo4j cung cấp repository cho thao tác ở cấp entity và Neo4jClient để chạy Cypher tùy chỉnh. Khi yêu cầu nghiệp vụ là xóa một relationship cụ thể nhưng giữ nguyên node ở hai đầu, truy vấn Cypher tường minh giúp thể hiện chính xác mục tiêu.

Ví dụ service dùng Neo4jClient:

~~~java
@Service
public class RelationshipService {

    private final Neo4jClient neo4jClient;

    public RelationshipService(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    @Transactional
    public void removeKnows(String fromId, String toId) {
        neo4jClient.query("""
            MATCH (a:Person {personId: $fromId})
                  -[r:KNOWS]->
                  (b:Person {personId: $toId})
            DELETE r
            """)
            .bind(fromId).to("fromId")
            .bind(toId).to("toId")
            .run();
    }
}
~~~

Các điểm cần chú ý:

- Truy vấn chọn hai node bằng mã nghiệp vụ.
- Biến r đại diện cho relationship cần xóa.
- DELETE r chỉ xóa relationship được khớp.
- Tham số được bind riêng, tránh ghép chuỗi dữ liệu đầu vào trực tiếp vào Cypher.
- Transaction do Spring quản lý bao quanh thao tác của service.

Nếu có nhiều relationship KNOWS giữa cùng hai node, truy vấn trên xóa tất cả relationship thỏa mẫu. Khi chỉ muốn xóa một liên kết, cần bổ sung thuộc tính nhận diện duy nhất vào WHERE.

### Xóa node bằng Neo4jClient

Nếu yêu cầu là xóa hồ sơ Person cùng mọi liên kết gắn với hồ sơ đó, có thể viết:

~~~java
@Transactional
public void deletePerson(String personId) {
    neo4jClient.query("""
        MATCH (p:Person {personId: $personId})
        DETACH DELETE p
        """)
        .bind(personId).to("personId")
        .run();
}
~~~

Truy vấn chỉ chọn node Person có personId tương ứng. DETACH DELETE xóa node này và mọi relationship gắn trực tiếp với nó.

Nếu ứng dụng cần giữ lại một số relationship, không dùng DETACH DELETE một cách mặc định. Hãy xác định các liên kết cần xử lý, xóa hoặc chuyển chúng theo quy tắc nghiệp vụ, rồi mới xóa node bằng DELETE.

### Repository và thao tác ở cấp entity

Repository như Neo4jRepository cung cấp các phương thức thao tác trên entity, ví dụ tìm theo ID hoặc xóa entity. Đây là thao tác ở cấp node/entity. Nếu mục tiêu là chỉ xóa một relationship và giữ nguyên các node, hãy dùng một truy vấn nhắm trực tiếp đến relationship bằng Neo4jClient hoặc một truy vấn tùy chỉnh đã được kiểm tra.

Khi cập nhật một entity có thuộc tính relationship được ánh xạ, cần hiểu trạng thái đồ thị mà thao tác save sẽ ghi lại theo mapping của SDN và phiên bản đang sử dụng. Không nên xóa relationship bằng cách thay đổi collection trong Java nếu chưa xác nhận rõ hành vi cập nhật quan hệ của mapping đó. Với thao tác xóa có tác động nghiệp vụ cụ thể, Cypher tường minh thường giúp reviewer nhìn thấy chính xác phần tử bị xóa.

## 7. Transaction khi xóa nhiều phần tử

Giả sử nghiệp vụ yêu cầu xóa mọi relationship KNOWS của một người trước khi xóa node Person. Hai thao tác cần cùng thành công hoặc cùng thất bại. Có thể đặt chúng trong một phương thức transactional:

~~~java
@Transactional
public void deletePersonAfterRemovingLinks(String personId) {
    neo4jClient.query("""
        MATCH (p:Person {personId: $personId})-[r:KNOWS]-()
        DELETE r
        """)
        .bind(personId).to("personId")
        .run();

    neo4jClient.query("""
        MATCH (p:Person {personId: $personId})
        DELETE p
        """)
        .bind(personId).to("personId")
        .run();
}
~~~

Truy vấn đầu tiên chỉ xóa relationship KNOWS đi vào hoặc đi ra từ Person được chọn. Nếu node còn relationship loại khác, lệnh DELETE p ở bước sau vẫn thất bại. Transaction sẽ rollback các thay đổi trong transaction nếu thao tác sau lỗi.

Điểm này rất quan trọng: xóa một tập con relationship không bảo đảm node đã cô lập. Nếu nghiệp vụ thật sự yêu cầu xóa mọi relationship thì cần xử lý tất cả loại liên kết, hoặc dùng DETACH DELETE. Không nên dựa vào giả định rằng một node chỉ có một loại relationship.

Nếu muốn giữ node và chỉ xóa một số liên kết, không thực hiện bước xóa node. Transaction có thể bao quanh nhiều thao tác xóa relationship và tạo relationship mới để bảo đảm đồ thị chuyển từ trạng thái cũ sang trạng thái mới một cách nhất quán.

## 8. Những lưu ý khi thiết kế truy vấn xóa

### Luôn chọn node bằng định danh hoặc điều kiện rõ ràng

Tránh truy vấn xóa không có điều kiện:

~~~cypher
MATCH (p:Person)
DETACH DELETE p
~~~

Truy vấn trên xóa toàn bộ node Person và tất cả relationship gắn với từng node Person được khớp. Đây có thể là thao tác quản trị dữ liệu lớn, không phải thao tác xóa một hồ sơ.

Với thao tác theo yêu cầu người dùng, hãy lọc theo mã định danh hoặc điều kiện nghiệp vụ đã xác định.

### Nhận biết truy vấn khớp nhiều relationship

Mẫu:

~~~cypher
MATCH (a:Person)-[r:KNOWS]->(b:Person)
WHERE a.personId = $fromId AND b.personId = $toId
DELETE r
~~~

sẽ xóa mọi relationship phù hợp. Nếu mô hình cho phép nhiều relationship cùng loại giữa một cặp node, hãy thêm điều kiện theo property của relationship để giới hạn đúng đối tượng.

### Hiểu khác biệt giữa incoming và outgoing

Relationship trong Neo4j có hướng. Mẫu:

~~~cypher
MATCH (a)-[r:KNOWS]->(b)
~~~

chỉ khớp hướng từ a sang b. Mẫu:

~~~cypher
MATCH (a)-[r:KNOWS]-(b)
~~~

khớp liên kết giữa a và b bất kể hướng. Khi dùng DETACH DELETE node, cả relationship đi vào và đi ra đều được gỡ bỏ.

### Xử lý trường hợp không tìm thấy dữ liệu

MATCH không tìm thấy node hoặc relationship thì truy vấn không có hàng để xử lý và không xóa phần tử nào. Ứng dụng cần xác định đây là kết quả hợp lệ (ví dụ yêu cầu xóa lặp lại) hay cần trả lỗi nghiệp vụ như không tìm thấy hồ sơ.

Nếu cần thông báo chính xác số relationship hoặc node đã xóa, hãy đọc update counters trong ResultSummary mà Neo4j Driver trả về từ thao tác chạy Cypher, rồi chuyển thành kết quả phù hợp ở tầng service.

### Cẩn trọng với thao tác xóa hàng loạt

Trước khi chạy truy vấn xóa diện rộng, hãy chạy phần MATCH tương ứng dưới dạng truy vấn đọc để xem chính xác node và relationship sẽ bị chọn. Có thể giới hạn theo batch khi dữ liệu lớn. Luôn đánh giá số phần tử bị tác động và transaction duration trên dữ liệu đại diện.

## 9. Bảng so sánh nhanh

| Tiêu chí | Xóa relationship | Xóa node bằng DELETE | Xóa node bằng DETACH DELETE |
|---|---|---|---|
| Phần tử chính bị xóa | Relationship | Node | Node |
| Relationship gắn với node | Chỉ relationship được chọn | Không được phép còn relationship | Tất cả relationship gắn trực tiếp |
| Node ở hai đầu relationship | Giữ lại | Node đích bị xóa nếu hợp lệ | Node đích bị xóa; node lân cận giữ lại |
| Trường hợp dùng | Bỏ liên kết, thay đổi quan hệ nghiệp vụ | Xóa node đã cô lập | Xóa node cùng toàn bộ liên kết trực tiếp |
| Rủi ro chính | Match quá rộng làm mất nhiều liên kết | Lệnh thất bại nếu còn liên kết | Mất mọi liên kết gắn với node được chọn |

## 10. Bài tập thực hành

Giả sử đồ thị có dữ liệu:

~~~cypher
CREATE (an:Person {personId: "p-1", name: "An"})
CREATE (binh:Person {personId: "p-2", name: "Binh"})
CREATE (chi:Person {personId: "p-3", name: "Chi"})
CREATE (an)-[:KNOWS {since: 2020}]->(binh)
CREATE (an)-[:WORKS_WITH]->(chi)
~~~

Thực hiện các yêu cầu sau:

1. Xóa relationship KNOWS từ An đến Bình. Kiểm tra hai node Person vẫn tồn tại.
2. Thử xóa node An bằng DELETE khi An còn relationship WORKS_WITH. Quan sát lỗi do node vẫn được kết nối.
3. Xóa relationship WORKS_WITH, sau đó xóa An bằng DELETE.
4. Tạo lại dữ liệu ban đầu rồi dùng DETACH DELETE An. Kiểm tra Bình và Chi vẫn tồn tại, còn An cùng các relationship nối trực tiếp với An đã biến mất.

Các truy vấn kiểm tra:

~~~cypher
MATCH (p:Person)
RETURN p.personId, p.name
ORDER BY p.personId
~~~

~~~cypher
MATCH (a:Person)-[r]->(b:Person)
RETURN a.personId, type(r), b.personId
~~~

Sau mỗi thao tác, hãy trả lời:

- Node nào còn tồn tại?
- Relationship nào đã bị xóa?
- Vì sao node lân cận không bị xóa cùng?
- Nếu có thêm một relationship loại khác nối với An, lệnh DELETE An có thành công không?

Kết quả cần đạt là hiểu rõ phạm vi tác động của từng lệnh trước khi thực hiện trên dữ liệu thật.

## Kết luận

DELETE relationship chỉ loại bỏ liên kết được truy vấn chọn và giữ lại các node ở hai đầu. DELETE node chỉ thành công khi node không còn relationship. DETACH DELETE xóa node cùng tất cả relationship gắn trực tiếp với nó, nhưng không xóa các node lân cận.

Trong Spring Data Neo4j, hãy xác định thao tác ở cấp relationship hay entity trước khi chọn API. Dùng Neo4jClient với Cypher tường minh khi cần xóa một liên kết cụ thể; dùng thao tác xóa node khi nghiệp vụ thực sự yêu cầu loại bỏ thực thể. Với nhiều bước thay đổi đồ thị, đặt transaction ở tầng service, giới hạn điều kiện MATCH và kiểm tra update counters để biết chính xác dữ liệu đã bị tác động.
