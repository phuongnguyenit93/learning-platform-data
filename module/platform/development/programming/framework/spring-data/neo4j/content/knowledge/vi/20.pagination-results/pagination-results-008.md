# Phân trang node gốc trước khi mở rộng relationship

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao cần phân trang node gốc trước khi truy vấn các relationship của chúng.
- Phân biệt phân trang trên root node với phân trang trên các dòng kết quả sau khi nối relationship.
- Viết Cypher dùng WITH, ORDER BY, SKIP và LIMIT để chọn một trang root ổn định.
- Kết hợp OPTIONAL MATCH và collect để ánh xạ một root cùng các relationship vào một record.
- Cấu hình Page hoặc Slice trong repository Spring Data Neo4j.
- Viết countQuery đếm đúng số root node và tránh đếm trùng do relationship.
- Nhận biết khi nào cần giới hạn riêng số relationship của từng root.

## 1. Bài toán: phân trang danh sách có relationship

Giả sử ứng dụng quản lý Person. Mỗi người có thể theo dõi nhiều người khác và làm việc cùng nhiều đồng nghiệp:

~~~text
(Person)-[:FOLLOWS]->(Person)
(Person)-[:WORKS_WITH]->(Person)
~~~

Màn hình danh sách cần hiển thị 20 Person mỗi trang, đồng thời mỗi Person có tên và danh sách người họ theo dõi.

Một cách viết dễ gặp là MATCH Person, mở rộng relationship FOLLOWS, rồi đặt SKIP và LIMIT ở cuối. Cách đó có thể phân trang các dòng sau khi mở rộng relationship thay vì phân trang Person.

Giả sử dữ liệu:

| Person | Số người được theo dõi |
|---|---:|
| An | 4 |
| Bình | 1 |
| Chi | 3 |
| Dũng | 2 |

Nếu query trả một dòng cho mỗi cặp Person-friend, bốn Person tạo ra mười dòng. Khi giới hạn kết quả ở năm dòng, An có thể chiếm bốn dòng và Bình chiếm một dòng. Trang đầu chỉ chứa dữ liệu của hai Person, dù giới hạn được đặt là năm.

Đây là lỗi sai ở cấp độ nghiệp vụ: ứng dụng muốn năm Person, nhưng query đang giới hạn năm dòng relationship.

## 2. Phân biệt root node và relationship row

Trong truy vấn đồ thị, một root node là thực thể mà API muốn phân trang. Relationship và node ở đầu còn lại là dữ liệu mở rộng của root.

Ví dụ một Person có bốn FOLLOWS relationship. Khi mở rộng:

~~~cypher
MATCH (p:Person {personId: "p-1"})-[r:FOLLOWS]->(friend:Person)
RETURN p, r, friend
~~~

Neo4j trả bốn record, mỗi record chứa cùng node p nhưng một relationship và một friend khác nhau.

Nếu áp dụng LIMIT 2 lên các record này, kết quả chỉ chứa hai relationship của Person p-1. Nó không có nghĩa là đã lấy hai Person gốc.

Hãy xác định trước đơn vị phân trang:

- Nếu API trả danh sách Person, mỗi phần tử trang phải tương ứng một root Person.
- Nếu API trả danh sách relationship, mỗi phần tử trang có thể tương ứng một relationship.
- Nếu API trả danh sách đường đi, đơn vị phân trang là path hoặc record path theo thiết kế truy vấn.

Bài học này tập trung vào trường hợp đầu tiên: phân trang node gốc, sau đó mới lấy các relationship cần hiển thị cho từng node.

## 3. Dùng WITH để phân trang root trước

Cypher cho phép WITH chuyển một tập kết quả sang phần tiếp theo của truy vấn. ORDER BY, SKIP và LIMIT đặt trên WITH sẽ sắp xếp và giới hạn tập root trước khi các MATCH tiếp theo được thực thi.

Ví dụ lấy 20 Person đang hoạt động:

~~~cypher
MATCH (p:Person)
WHERE p.active = true
WITH p
ORDER BY p.createdAt DESC, p.personId ASC
SKIP 0
LIMIT 20
OPTIONAL MATCH (p)-[r:FOLLOWS]->(friend:Person)
RETURN p, collect(DISTINCT r), collect(DISTINCT friend)
~~~

Luồng xử lý:

1. MATCH tìm các Person thỏa điều kiện.
2. WITH p chuyển các Person sang phần tiếp theo.
3. ORDER BY xác định thứ tự ổn định.
4. SKIP và LIMIT chọn đúng 20 Person gốc.
5. OPTIONAL MATCH mở rộng FOLLOWS cho từng Person đã được chọn.
6. collect gom relationship và node đích vào một record cho mỗi Person.

Vì việc phân trang xảy ra trước OPTIONAL MATCH, số lượng root trong trang không bị ảnh hưởng bởi việc mỗi Person có một hay nhiều relationship.

### Vì sao cần ORDER BY ổn định?

Nếu không có ORDER BY, Neo4j không bảo đảm thứ tự record giữa các lần chạy. Một node có thể xuất hiện ở trang trước trong lần gọi này và chuyển sang trang khác ở lần gọi tiếp theo.

Ngay cả khi sắp xếp theo một property, nếu nhiều node có cùng giá trị thì thứ tự giữa chúng vẫn chưa được xác định hoàn toàn. Hãy thêm một thuộc tính duy nhất làm tie-breaker:

~~~cypher
WITH p
ORDER BY p.createdAt DESC, p.personId ASC
SKIP $skip
LIMIT $limit
~~~

Trong ví dụ, createdAt xác định thứ tự chính và personId phân biệt các node có cùng thời điểm tạo.

Thứ tự ổn định giúp phân trang có tính dự đoán. Nếu dữ liệu liên tục được thêm, sửa trong khi người dùng chuyển trang, offset pagination vẫn có thể dịch chuyển kết quả; phần cuối bài sẽ nói thêm về keyset pagination.

## 4. Vì sao OPTIONAL MATCH và collect cần đặt sau phân trang?

Sau khi đã chọn root node, query mới mở rộng relationship:

~~~cypher
OPTIONAL MATCH (p)-[r:FOLLOWS]->(friend:Person)
RETURN p, collect(DISTINCT r), collect(DISTINCT friend)
~~~

OPTIONAL MATCH giữ lại Person ngay cả khi họ chưa theo dõi ai. Nếu dùng MATCH bắt buộc, Person không có FOLLOWS relationship sẽ biến mất khỏi kết quả.

collect gom nhiều relationship và node đích thành các collection. Khi không có relationship, collection thu được là rỗng thay vì loại bỏ root node.

Trong custom query ánh xạ entity SDN, việc trả về root node cùng collection relationship và node đích giúp framework hydrate các relationship đã khai báo trong domain model.

Ví dụ entity:

~~~java
@Node("Person")
public class Person {

    @Id
    private String personId;

    private String fullName;
    private boolean active;
    private LocalDateTime createdAt;

    @Relationship(type = "FOLLOWS", direction = Relationship.Direction.OUTGOING)
    private Set<Person> follows = new LinkedHashSet<>();
}
~~~

Query trả về một record cho mỗi Person gốc, với collection FOLLOWS đã gom lại. Nếu chỉ trả p, SDN có thể không nhận được dữ liệu relationship mà màn hình cần từ custom query.

## 5. Repository với Page và countQuery

Spring Data Neo4j hỗ trợ Page và Slice trên repository.

Với derived finder method, SDN xử lý Pageable cho query được tạo từ tên phương thức. Với custom @Query, câu Cypher phải tự sử dụng hai tham số phân trang $skip và $limit.

Ví dụ derived finder có thể khai báo ngắn gọn:

~~~java
Page<Person> findByActiveTrue(Pageable pageable);
~~~

Với phương thức này, SDN tạo query và áp dụng Pageable. Ứng dụng có thể truyền Sort trong Pageable để chọn thứ tự. Khi tự viết Cypher bằng @Query, hãy đặt ORDER BY trực tiếp trong query và truyền Pageable không có Sort; SDN không tự chèn thứ tự từ Pageable vào custom query.

Ví dụ repository trả Page<Person>:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository
        extends Neo4jRepository<Person, String> {

    @Query(
        value = """
            MATCH (p:Person)
            WHERE p.active = $active
            WITH p
            ORDER BY p.createdAt DESC, p.personId ASC
            SKIP $skip
            LIMIT $limit
            OPTIONAL MATCH (p)-[r:FOLLOWS]->(friend:Person)
            RETURN p, collect(DISTINCT r), collect(DISTINCT friend)
            """,
        countQuery = """
            MATCH (p:Person)
            WHERE p.active = $active
            RETURN count(DISTINCT p)
            """
    )
    Page<Person> findActivePeopleWithFollows(
        @Param("active") boolean active,
        Pageable pageable
    );
}
~~~

Các điểm quan trọng:

- $skip và $limit được SDN liên kết với Pageable.
- Query chính phân trang root Person trong WITH trước khi mở rộng FOLLOWS.
- countQuery chạy riêng để tính tổng số root Person phù hợp với bộ lọc.
- countQuery không cần mở rộng relationship nếu điều kiện lọc chỉ dựa trên property của Person.
- countQuery phải phản ánh cùng tập root node mà query chính dùng.

Nếu dùng Page, Spring cần tổng số phần tử để tính totalElements và totalPages. Vì vậy custom query cần countQuery riêng.

Quy tắc Pageable không có Sort cũng áp dụng cho custom query trả Page. Hãy để ORDER BY trong Cypher quyết định thứ tự ổn định của root node.

### Chọn Slice nếu không cần tổng số trang

Slice chỉ cần biết còn trang tiếp theo hay không. Nó không cần tổng số phần tử chính xác, vì vậy không cần countQuery.

~~~java
@Query("""
    MATCH (p:Person)
    WHERE p.active = $active
    WITH p
    ORDER BY p.createdAt DESC, p.personId ASC
    SKIP $skip
    LIMIT $limit
    OPTIONAL MATCH (p)-[r:FOLLOWS]->(friend:Person)
    RETURN p, collect(DISTINCT r), collect(DISTINCT friend)
    """)
Slice<Person> findActivePeopleSlice(
    @Param("active") boolean active,
    Pageable pageable
);
~~~

Với custom query trả Slice:

- Query phải có cả $skip và $limit.
- Cần cung cấp ORDER BY ổn định ngay trong Cypher.
- Pageable truyền vào nên không có Sort; SDN không dùng thông tin Sort của Pageable để sửa custom query.
- Không cần countQuery.

Quy tắc Pageable không có Sort cũng áp dụng ở đây vì query đã tự khai báo ORDER BY.

Nếu chỉ cần lấy một đoạn kết quả mà không cần Page metadata, có thể dùng List<T> cùng Pageable. Tuy nhiên, List không cung cấp totalElements hoặc thông tin trang tiếp theo như Page và Slice.

## 6. Bộ lọc dựa trên relationship mà không nhân bản root

Một trường hợp phổ biến là chỉ lấy Person thuộc một Group cụ thể. Nếu dùng MATCH qua relationship trước khi phân trang:

~~~cypher
MATCH (p:Person)-[:MEMBER_OF]->(g:Group {groupCode: $groupCode})
RETURN p
~~~

Một Person có thể có nhiều relationship MEMBER_OF phù hợp, khiến root p xuất hiện nhiều lần. Nếu phân trang trên các dòng này, cùng một Person có thể chiếm nhiều vị trí.

Có hai cách xử lý.

### Dùng EXISTS để lọc root

Nếu chỉ cần kiểm tra Person có ít nhất một relationship phù hợp, EXISTS giữ kết quả ở cấp Person:

~~~cypher
MATCH (p:Person)
WHERE p.active = true
  AND EXISTS {
      MATCH (p)-[:MEMBER_OF]->(:Group {groupCode: $groupCode})
  }
WITH p
ORDER BY p.createdAt DESC, p.personId ASC
SKIP $skip
LIMIT $limit
OPTIONAL MATCH (p)-[r:FOLLOWS]->(friend:Person)
RETURN p, collect(DISTINCT r), collect(DISTINCT friend)
~~~

countQuery tương ứng:

~~~cypher
MATCH (p:Person)
WHERE p.active = true
  AND EXISTS {
      MATCH (p)-[:MEMBER_OF]->(:Group {groupCode: $groupCode})
  }
RETURN count(p)
~~~

EXISTS chỉ kiểm tra sự tồn tại của pattern. Nó không nhân bản Person theo số lượng Group relationship phù hợp.

### Dùng DISTINCT khi cần MATCH relationship

Nếu cần dữ liệu từ Group để lọc hoặc sắp xếp, có thể dùng DISTINCT để đưa tập kết quả về một root cho mỗi Person trước khi phân trang:

~~~cypher
MATCH (p:Person)-[:MEMBER_OF]->(g:Group)
WHERE g.groupCode IN $groupCodes
WITH DISTINCT p
ORDER BY p.createdAt DESC, p.personId ASC
SKIP $skip
LIMIT $limit
OPTIONAL MATCH (p)-[r:FOLLOWS]->(friend:Person)
RETURN p, collect(DISTINCT r), collect(DISTINCT friend)
~~~

countQuery phải đếm cùng tập Person duy nhất:

~~~cypher
MATCH (p:Person)-[:MEMBER_OF]->(g:Group)
WHERE g.groupCode IN $groupCodes
RETURN count(DISTINCT p)
~~~

Hãy bảo đảm predicate trong countQuery giống predicate dùng để chọn root trong query chính. Nếu một bên lọc theo điều kiện khác, totalElements và các trang dữ liệu sẽ không nhất quán.

## 7. Mở rộng nhiều nhánh relationship sau khi đã phân trang

Một Person có thể vừa có FOLLOWS vừa có WORKS_WITH. Nếu MATCH hai nhánh độc lập trong cùng một phần truy vấn, số dòng trung gian có thể nhân lên.

Ví dụ một Person có 4 người được theo dõi và 3 đồng nghiệp. MATCH cả hai nhánh có thể tạo 12 dòng cho cùng root. Điều này làm dữ liệu lặp và gây khó khăn khi ánh xạ graph.

Hãy phân trang root trước, sau đó gom từng nhánh riêng bằng subquery:

~~~cypher
MATCH (p:Person)
WHERE p.active = true
WITH p
ORDER BY p.createdAt DESC, p.personId ASC
SKIP $skip
LIMIT $limit

CALL {
    WITH p
    OPTIONAL MATCH (p)-[f:FOLLOWS]->(friend:Person)
    RETURN collect(DISTINCT f) AS followsRelationships,
           collect(DISTINCT friend) AS followedPeople
}

CALL {
    WITH p
    OPTIONAL MATCH (p)-[w:WORKS_WITH]->(colleague:Person)
    RETURN collect(DISTINCT w) AS workRelationships,
           collect(DISTINCT colleague) AS colleagues
}

RETURN p,
       followsRelationships,
       followedPeople,
       workRelationships,
       colleagues
~~~

Mỗi subquery nhận một Person đã được chọn vào trang. Nó thu thập riêng relationship và node đích của nhánh tương ứng. Kết quả cuối cùng vẫn có một record cho mỗi root Person.

Nếu dùng custom query để hydrate entity, các collection trả về phải khớp với relationship được khai báo trong domain model. Nếu query chỉ phục vụ màn hình, DTO projection có thể phù hợp hơn việc hydrate entity đầy đủ.

## 8. Một ví dụ hoàn chỉnh với Page<Person>

Domain model:

~~~java
@Node("Person")
public class Person {

    @Id
    private String personId;

    private String fullName;
    private boolean active;
    private LocalDateTime createdAt;

    @Relationship(type = "FOLLOWS")
    private Set<Person> follows = new LinkedHashSet<>();

    @Relationship(type = "WORKS_WITH")
    private Set<Person> colleagues = new LinkedHashSet<>();

    // Constructor, getter và setter được lược bỏ.
}
~~~

Repository:

~~~java
public interface PersonRepository
        extends Neo4jRepository<Person, String> {

    @Query(
        value = """
            MATCH (p:Person)
            WHERE p.active = $active
            WITH p
            ORDER BY p.createdAt DESC, p.personId ASC
            SKIP $skip
            LIMIT $limit

            CALL {
                WITH p
                OPTIONAL MATCH (p)-[f:FOLLOWS]->(friend:Person)
                RETURN collect(DISTINCT f) AS followsRelationships,
                       collect(DISTINCT friend) AS followedPeople
            }

            CALL {
                WITH p
                OPTIONAL MATCH (p)-[w:WORKS_WITH]->(colleague:Person)
                RETURN collect(DISTINCT w) AS workRelationships,
                       collect(DISTINCT colleague) AS colleagues
            }

            RETURN p,
                   followsRelationships,
                   followedPeople,
                   workRelationships,
                   colleagues
            """,
        countQuery = """
            MATCH (p:Person)
            WHERE p.active = $active
            RETURN count(p)
            """
    )
    Page<Person> findActivePeopleWithNetwork(
        @Param("active") boolean active,
        Pageable pageable
    );
}
~~~

Service:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonDirectoryService {

    private final PersonRepository people;

    public PersonDirectoryService(PersonRepository people) {
        this.people = people;
    }

    @Transactional(readOnly = true)
    public Page<Person> findActivePeople(int page, int size) {
        Pageable pageable = PageRequest.of(page, size);
        return people.findActivePeopleWithNetwork(true, pageable);
    }
}
~~~

Trong ví dụ này, query tự quy định thứ tự nên Pageable không truyền Sort. Mỗi trang có tối đa size root Person; relationship được nạp sau khi các root đã được chọn.

Trong ứng dụng thực tế, hãy giới hạn size tối đa để tránh một request yêu cầu hàng nghìn root cùng toàn bộ relationship. Cũng cần cân nhắc số lượng relationship trung bình và lớn nhất của mỗi root.

## 9. Kiểm tra số lượng root và relationship

Để xác minh query có phân trang đúng cấp root, hãy kiểm tra ba đại lượng riêng:

1. Số root node trong trang.
2. Tổng số relationship được mở rộng cho các root đó.
3. Tổng số root thỏa bộ lọc trên toàn bộ database.

Ví dụ kiểm tra trang đầu:

~~~cypher
MATCH (p:Person)
WHERE p.active = true
WITH p
ORDER BY p.createdAt DESC, p.personId ASC
SKIP 0
LIMIT 20
RETURN count(p) AS rootCount
~~~

Kết quả mong đợi: rootCount không vượt quá 20.

Kiểm tra tổng relationship của trang:

~~~cypher
MATCH (p:Person)
WHERE p.active = true
WITH p
ORDER BY p.createdAt DESC, p.personId ASC
SKIP 0
LIMIT 20
OPTIONAL MATCH (p)-[r:FOLLOWS]->()
RETURN count(DISTINCT p) AS rootCount,
       count(r) AS followsCount
~~~

rootCount phản ánh số Person trong trang; followsCount phản ánh số relationship FOLLOWS của những Person đó. Hai con số không nhất thiết bằng nhau.

Kiểm tra tổng số root cho countQuery:

~~~cypher
MATCH (p:Person)
WHERE p.active = true
RETURN count(p) AS totalActivePeople
~~~

Nếu countQuery và query chính dùng cùng điều kiện chọn root, tổng số trang được tính đúng theo Person thay vì theo số dòng relationship.

## 10. Giới hạn riêng số relationship của mỗi root

Phân trang root không giới hạn số relationship mà mỗi root có. Một Person có thể theo dõi 10 người, nhưng cũng có thể theo dõi hàng trăm nghìn người.

Nếu màn hình chỉ cần năm người được theo dõi gần đây nhất cho mỗi Person, hãy giới hạn riêng nhánh relationship bằng correlated subquery:

~~~cypher
MATCH (p:Person)
WHERE p.active = true
WITH p
ORDER BY p.createdAt DESC, p.personId ASC
SKIP $skip
LIMIT $limit

CALL {
    WITH p
    OPTIONAL MATCH (p)-[r:FOLLOWS]->(friend:Person)
    WITH r, friend
    ORDER BY r.createdAt DESC, friend.personId ASC
    LIMIT 5
    RETURN collect(r) AS recentFollowRelationships,
           collect(friend) AS recentFollowedPeople
}

RETURN p,
       recentFollowRelationships,
       recentFollowedPeople
~~~

Mỗi root vẫn nằm trong trang đã chọn, nhưng collection relationship chỉ chứa tối đa năm phần tử.

Cần hiểu rõ đây là graph được đọc một phần. Nếu domain entity ánh xạ toàn bộ relationship FOLLOWS, collection trả về chỉ có năm phần tử không chứng minh rằng Person chỉ có năm relationship trong database.

Với dữ liệu đọc để hiển thị, hãy trả về DTO hoặc projection thể hiện rõ đây là danh sách giới hạn. Tránh lưu lại entity đã được nạp thiếu relationship như thể đó là trạng thái đầy đủ của node; thao tác save có thể loại bỏ những relationship không có trong graph đã hydrate.

Nếu API cần phân trang danh sách relationship độc lập, hãy tạo một query riêng nhận personId và Pageable để trả về các relationship hoặc node đích của Person đó.

## 11. Offset pagination và keyset pagination

Page và Slice với SKIP/LIMIT là offset pagination. Cách này phù hợp với giao diện có số trang và nhu cầu nhảy đến một trang cụ thể.

Tuy nhiên, với trang rất sâu, database phải bỏ qua nhiều root trước khi trả kết quả. Khi dữ liệu thường xuyên thay đổi, vị trí của node giữa các trang cũng có thể dịch chuyển.

Keyset pagination dùng giá trị cuối cùng của trang trước làm mốc để tìm trang tiếp theo. Ví dụ sắp xếp theo createdAt giảm dần và personId tăng dần:

~~~cypher
MATCH (p:Person)
WHERE p.active = true
  AND (
      p.createdAt < $lastCreatedAt
      OR (
          p.createdAt = $lastCreatedAt
          AND p.personId > $lastPersonId
      )
  )
WITH p
ORDER BY p.createdAt DESC, p.personId ASC
LIMIT $limit
OPTIONAL MATCH (p)-[r:FOLLOWS]->(friend:Person)
RETURN p, collect(DISTINCT r), collect(DISTINCT friend)
~~~

Lần đầu cần một query riêng không có điều kiện mốc. Các lần tiếp theo truyền createdAt và personId của root cuối cùng ở trang trước.

Keyset pagination tránh phải bỏ qua một số lượng lớn root như SKIP. Nó phù hợp với danh sách cuộn liên tục hoặc dữ liệu lớn, nhưng không cung cấp số trang và tổng số trang như Page. Nếu dùng cursor, hãy đưa đủ các trường sắp xếp vào cursor và bảo đảm thứ tự có tie-breaker duy nhất.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Trang có ít Person hơn page size | LIMIT áp dụng sau khi mở rộng relationship rows | Phân trang root trong WITH trước khi OPTIONAL MATCH |
| Một Person xuất hiện ở nhiều trang | Root bị nhân bản bởi MATCH qua nhiều relationship | Dùng EXISTS hoặc WITH DISTINCT p trước phân trang |
| Person không có relationship bị biến mất | Dùng MATCH thay vì OPTIONAL MATCH | Dùng OPTIONAL MATCH khi nhánh có thể không tồn tại |
| Relationship bị lặp trong entity | Nhiều nhánh tạo Cartesian product | Gom từng nhánh bằng collect hoặc subquery |
| totalElements lớn hơn số Person thực tế | countQuery đếm relationship rows | Đếm root bằng count(DISTINCT p) hoặc dùng EXISTS |
| Trang thay đổi thứ tự giữa các lần gọi | Thiếu ORDER BY ổn định hoặc sort không duy nhất | Thêm tie-breaker duy nhất |
| Custom Slice trả kết quả sai số lượng | Query thiếu $skip hoặc $limit | Dùng cả hai tham số trong custom Cypher |
| Pageable sort không có tác dụng | Custom query đã khai báo ORDER BY riêng | Đặt Pageable không có Sort và quản lý thứ tự trong Cypher |
| Query trả một số Person nhưng thiếu relationship | Collection được giới hạn riêng theo root | Thể hiện dữ liệu giới hạn bằng DTO hoặc query riêng |
| Save làm mất relationship | Lưu entity được hydrate từ một phần graph | Tách read model và write entity; tải đầy đủ graph cần bảo toàn |

## 13. Bài tập thực hành

Tạo dữ liệu Person có số relationship khác nhau:

~~~cypher
CREATE (an:Person {personId: "p-1", fullName: "An", active: true, createdAt: datetime("2025-01-05T10:00:00")})
CREATE (binh:Person {personId: "p-2", fullName: "Binh", active: true, createdAt: datetime("2025-01-04T10:00:00")})
CREATE (chi:Person {personId: "p-3", fullName: "Chi", active: true, createdAt: datetime("2025-01-03T10:00:00")})
CREATE (dung:Person {personId: "p-4", fullName: "Dung", active: true, createdAt: datetime("2025-01-02T10:00:00")})
CREATE (hoa:Person {personId: "p-5", fullName: "Hoa", active: true, createdAt: datetime("2025-01-01T10:00:00")})
CREATE (an)-[:FOLLOWS]->(binh)
CREATE (an)-[:FOLLOWS]->(chi)
CREATE (an)-[:FOLLOWS]->(dung)
CREATE (an)-[:FOLLOWS]->(hoa)
CREATE (binh)-[:FOLLOWS]->(chi)
CREATE (chi)-[:FOLLOWS]->(dung)
~~~

Thực hiện:

1. Viết query lấy hai Person gốc đầu tiên theo createdAt.
2. Mở rộng FOLLOWS sau khi đã chọn hai root.
3. Viết lại query bằng cách MATCH FOLLOWS trước rồi đặt LIMIT ở cuối; so sánh số root thực tế.
4. Tạo repository method trả về Slice<Person> với Pageable.
5. Tạo Page<Person> cùng countQuery đếm root node.
6. Thêm điều kiện lọc Person thuộc một Group và bảo đảm countQuery không đếm trùng.
7. Thêm nhánh WORKS_WITH và gom riêng hai nhánh.
8. Giới hạn tối đa hai FOLLOWS cho mỗi root và giải thích vì sao kết quả đó là graph đọc một phần.

Các câu hỏi tự kiểm tra:

- Vì sao phân trang root cần thực hiện trước khi mở rộng relationship?
- Khi nào nên dùng EXISTS thay cho MATCH relationship?
- Vì sao Page cần countQuery còn Slice thì không?
- Vì sao ORDER BY nên có thêm một thuộc tính duy nhất?
- Nếu mỗi root có rất nhiều relationship, phân trang root đã đủ để giới hạn tổng dữ liệu trả về chưa?
- Vì sao không nên lưu entity được hydrate từ một collection relationship đã giới hạn?

## Kết luận

Khi API cần phân trang node gốc cùng các relationship, hãy chọn root node trước bằng MATCH, WITH, ORDER BY, SKIP và LIMIT. Sau đó mới dùng OPTIONAL MATCH để mở rộng relationship và collect để gom node cùng relationship vào một record cho mỗi root.

Với repository custom query, Page cần countQuery đếm đúng root node; Slice cần $skip và $limit cùng thứ tự ổn định nhưng không cần tổng số trang. Nếu bộ lọc dựa trên relationship, dùng EXISTS hoặc DISTINCT để tránh nhân bản root. Nếu một root có quá nhiều relationship, hãy giới hạn riêng nhánh hoặc tạo endpoint phân trang relationship, đồng thời xem kết quả đó là graph đọc một phần và không dùng nó để ghi lại entity đầy đủ.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.2: FAQ — Page và Slice với custom query](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Neo4j Cypher Manual: WITH — ORDER BY, SKIP và LIMIT trước các clause tiếp theo](https://neo4j.com/docs/cypher-manual/current/clauses/with/)
- [Neo4j Cypher Manual: Các clause và thứ tự xử lý truy vấn](https://neo4j.com/docs/cypher-manual/current/clauses/)
