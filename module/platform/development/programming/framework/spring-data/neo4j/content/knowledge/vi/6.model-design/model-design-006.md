# Tránh quan hệ hai chiều làm mở rộng đồ thị đối tượng quá mức

Neo4j lưu dữ liệu dưới dạng node và relationship. Một relationship có hướng trong đồ thị, nhưng Cypher có thể tìm nó từ cả hai đầu bằng cách đổi chiều mẫu truy vấn. Vì vậy, ứng dụng không cần khai báo thuộc tính Java ở cả hai phía của mọi relationship chỉ để có thể truy cập dữ liệu theo hai hướng.

Trong Spring Data Neo4j (SDN), các thuộc tính được đánh dấu `@Relationship` xác định những quan hệ mà mapper dùng để tạo object graph trong Java. Nếu một mô hình vừa khai báo quan hệ đi ra, vừa khai báo quan hệ ngược ở node đích, các entity có thể tham chiếu lẫn nhau. Khi tải nhiều cấp quan hệ, object graph có thể lớn nhanh, chứa chu trình và khó chuyển thành JSON hoặc DTO.

Bài học này tập trung vào cách chọn một hướng ánh xạ phù hợp, truy vấn chiều ngược bằng Cypher, giới hạn độ sâu dữ liệu được tải và trả về projection gọn cho từng chức năng.

## 1. Phân biệt đồ thị Neo4j và object graph trong Java

Giả sử đồ thị có hai node `Person` và relationship:

~~~text
(An)-[:FOLLOWS]->(Bình)
~~~

Trong Neo4j, relationship `FOLLOWS` được lưu theo hướng từ An đến Bình. Tuy nhiên, truy vấn sau vẫn tìm được An khi bắt đầu từ Bình và đi ngược relationship:

~~~cypher
MATCH (person:Person {id: $personId})<-[:FOLLOWS]-(follower:Person)
RETURN follower
~~~

Điều này không yêu cầu tạo thêm relationship ngược từ Bình đến An. Mũi tên trong mẫu Cypher chỉ mô tả hướng khớp trên relationship đã tồn tại.

Object graph trong Java là tập hợp object và các tham chiếu giữa chúng. Nếu entity `Person` có cả `follows` và `followers`, hai node có thể giữ tham chiếu đến nhau. Khi ứng dụng tải nhiều tầng quan hệ, mỗi tầng lại mở rộng thêm các object liên quan. Nếu dữ liệu có chu trình như An theo dõi Bình và Bình theo dõi An, object graph cũng có thể chứa tham chiếu vòng.

Hai khái niệm cần được tách biệt:

- **Đồ thị lưu trữ:** các node và relationship thực sự nằm trong Neo4j; có thể truy vấn theo hướng phù hợp với nghiệp vụ.
- **Object graph được ánh xạ:** những entity và relationship mà SDN đưa vào bộ nhớ theo các thuộc tính ánh xạ và độ sâu tải dữ liệu.

Một đồ thị Neo4j có thể có nhiều quan hệ và chu trình mà không bắt buộc mọi entity Java phải giữ tham chiếu đến toàn bộ vùng đồ thị đó.

## 2. Chọn một hướng ánh xạ cho quan hệ

Ví dụ, ứng dụng cần hiển thị danh sách những người mà một người đang theo dõi. Ta có thể ánh xạ quan hệ đi ra trên `Person`:

~~~java
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

    @Relationship(type = "FOLLOWS", direction = Relationship.Direction.OUTGOING)
    private Set<Person> follows = new HashSet<>();

    // Constructor, getter và setter được lược bỏ.
}
~~~

Thuộc tính `follows` biểu diễn relationship đi ra từ node `Person` hiện tại. Trong SDN, `Relationship.Direction.OUTGOING` chỉ rõ hướng này; đây cũng là hướng mặc định nếu không khai báo `direction`.

Với mô hình trên, không cần thêm thuộc tính `followers` vào cùng entity chỉ để truy cập những người đang theo dõi một người. Chiều ngược có thể được truy vấn trực tiếp:

~~~cypher
MATCH (person:Person {id: $personId})<-[:FOLLOWS]-(follower:Person)
RETURN follower.id AS id, follower.name AS name
ORDER BY name
~~~

Nếu nghiệp vụ chính lại xoay quanh việc một người nhận được lượt theo dõi, có thể chọn ánh xạ quan hệ `FOLLOWS` theo chiều `INCOMING` trên một mô hình đọc phù hợp. Điều quan trọng là xác định rõ ý nghĩa của relationship và hướng mà thuộc tính Java đại diện.

`@Relationship(direction = INCOMING)` không tạo thêm relationship ngược trong Neo4j. Nó chỉ khai báo cách SDN đọc hoặc ghi relationship so với node đang được ánh xạ. Khi đổi hướng ánh xạ, hãy kiểm tra lại truy vấn Cypher và quy ước ghi dữ liệu để tránh hai phần của ứng dụng hiểu khác nhau về cùng một quan hệ.

## 3. Vì sao ánh xạ hai chiều có thể làm object graph phình to?

Giả sử mô hình có hai thuộc tính:

~~~java
@Relationship(type = "FOLLOWS", direction = Relationship.Direction.OUTGOING)
private Set<Person> follows;

@Relationship(type = "FOLLOWS", direction = Relationship.Direction.INCOMING)
private Set<Person> followers;
~~~

Khi ánh xạ cả hai phía, một entity có thể tham chiếu đến entity khác qua `follows`, trong khi entity kia tham chiếu ngược lại qua `followers`. Nếu truy vấn tải sâu nhiều cấp, quá trình ánh xạ có thể đưa vào bộ nhớ một mạng lưới object lớn hơn mức màn hình hoặc nghiệp vụ đang cần.

Ví dụ, nếu mỗi người có trung bình `b` kết nối và ứng dụng tải đến độ sâu `d`, số object hoặc nhánh quan hệ cần xem xét có thể tăng gần theo cấp số nhân trong trường hợp đồ thị phân nhánh rộng. Đây chỉ là ước lượng trực quan; số object thực tế còn phụ thuộc vào node trùng lặp, chu trình, cách mapper xử lý định danh và hình dạng kết quả truy vấn.

Các hệ quả thường gặp:

- Tăng lượng dữ liệu cần đọc từ Neo4j và lượng object cần tạo trong bộ nhớ.
- Tốn bộ nhớ và thời gian xử lý khi một node có nhiều relationship hoặc vùng đồ thị có độ phân nhánh lớn.
- Entity chứa tham chiếu vòng, khiến serializer JSON có thể lặp vô hạn nếu tuần tự hóa trực tiếp cả hai phía.
- API trả về nhiều dữ liệu hơn yêu cầu, làm payload lớn và khó giữ ổn định khi mô hình dữ liệu mở rộng.
- Việc cập nhật entity trở nên khó hiểu vì nhiều thuộc tính có thể cùng thể hiện một relationship từ hai góc nhìn.

Độ sâu tải dữ liệu có giới hạn giúp kiểm soát số tầng được ánh xạ, nhưng không thay thế việc thiết kế đúng hình dạng dữ liệu cho từng chức năng. Một node có hàng nghìn relationship trực tiếp vẫn có thể tạo collection rất lớn ngay ở tầng đầu tiên.

## 4. Truy vấn chiều ngược mà không cần thuộc tính Java ngược

Repository có thể cung cấp chức năng tìm người theo dõi một tài khoản bằng Cypher. Nếu API chỉ cần mã và tên, hãy trả về projection thay vì toàn bộ entity:

~~~java
public interface PersonSummary {
    String getId();
    String getName();
}
~~~

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (person:Person {id: $personId})<-[:FOLLOWS]-(follower:Person)
        RETURN follower.id AS id, follower.name AS name
        ORDER BY name
        LIMIT $limit
        """)
    List<PersonSummary> findFollowers(
        @Param("personId") String personId,
        @Param("limit") int limit
    );
}
~~~

Truy vấn bắt đầu ở người được chỉ định, đi ngược relationship `FOLLOWS` để tìm người theo dõi. Các bí danh `id` và `name` khớp với getter của projection. Phương thức chỉ trả về hai thuộc tính mà chức năng cần; không cần dựng toàn bộ object graph của `Person`.

Nếu chỉ cần số lượng người theo dõi, hãy dùng phép tổng hợp:

~~~cypher
MATCH (person:Person {id: $personId})
OPTIONAL MATCH (person)<-[:FOLLOWS]-(follower:Person)
RETURN person.id AS id,
       person.name AS name,
       count(DISTINCT follower) AS followerCount
~~~

Kết quả có thể ánh xạ vào một projection khác:

~~~java
public interface FollowerCountView {
    String getId();
    String getName();
    Long getFollowerCount();
}
~~~

`OPTIONAL MATCH` vẫn trả về người được tìm ngay cả khi chưa có follower nào; trong trường hợp đó, `count` là không. Phép tổng hợp tránh tải toàn bộ danh sách entity chỉ để đếm số lượng.

Với các truy vấn trả về danh sách lớn, hãy lọc theo điều kiện nghiệp vụ, sắp xếp ổn định và giới hạn số kết quả. Tham số hóa giá trị đầu vào như `$personId` và `$limit` giúp truy vấn rõ ràng và tránh ghép chuỗi Cypher từ dữ liệu người dùng.

## 5. Giới hạn độ sâu khi tải entity

SDN có cơ chế kiểm soát độ sâu của quan hệ được ánh xạ. Độ sâu càng lớn, mapper càng có thể đưa thêm các node liên quan vào object graph. Hãy chọn độ sâu dựa trên chức năng đang thực hiện thay vì mặc định tải toàn bộ vùng đồ thị.

Khi dùng `Neo4jTemplate`, có thể chỉ định độ sâu ngay tại thao tác đọc. Ví dụ:

~~~java
import org.springframework.data.neo4j.core.Neo4jTemplate;

import java.util.Optional;

public class PersonQueryService {

    private final Neo4jTemplate neo4jTemplate;

    public PersonQueryService(Neo4jTemplate neo4jTemplate) {
        this.neo4jTemplate = neo4jTemplate;
    }

    public Optional<Person> findPersonWithDirectConnections(String personId) {
        return neo4jTemplate.findById(personId, Person.class, 1);
    }
}
~~~

Độ sâu `1` phù hợp với ví dụ cần đọc node và các quan hệ trực tiếp được ánh xạ. Hãy xác nhận API và hành vi mặc định theo phiên bản Spring Data Neo4j mà dự án sử dụng; các phương thức repository, template và truy vấn tùy chỉnh có cách xác định hình dạng kết quả khác nhau.

Không nên tăng độ sâu chỉ để làm cho một màn hình có đủ dữ liệu. Nếu màn hình cần một danh sách con, một bộ đếm hoặc vài trường tóm tắt, hãy viết truy vấn riêng và trả về projection tương ứng. Điều đó giúp giới hạn rõ dữ liệu cần lấy và tránh phụ thuộc vào cấu trúc entity nội bộ.

## 6. Dùng mô hình đọc riêng cho từng nhu cầu

Một entity lưu trữ có thể có quan hệ cần thiết cho nghiệp vụ ghi dữ liệu, trong khi màn hình đọc chỉ cần một phần nhỏ thông tin. Có thể giữ entity làm mô hình persistence và tạo projection hoặc DTO cho từng truy vấn.

Ví dụ, trang hồ sơ chỉ cần tên người dùng và số lượng người theo dõi, không cần tải danh sách follower:

~~~java
public interface PersonProfileView {
    String getId();
    String getName();
    Long getFollowerCount();
}
~~~

~~~java
@Query("""
    MATCH (person:Person {id: $personId})
    OPTIONAL MATCH (person)<-[:FOLLOWS]-(follower:Person)
    RETURN person.id AS id,
           person.name AS name,
           count(DISTINCT follower) AS followerCount
    """)
Optional<PersonProfileView> findProfile(@Param("personId") String personId);
~~~

Với trang danh sách người theo dõi, dùng projection `PersonSummary` ở phần trước. Với trang thống kê, dùng `FollowerCountView`. Mỗi truy vấn chỉ trả về trường phù hợp với hợp đồng của chức năng.

Không nên trả thẳng entity persistence ra API chỉ vì repository đã trả về entity đó. DTO giúp kiểm soát trường nào được công khai, tránh lộ thuộc tính nội bộ và tránh serializer đi theo các tham chiếu hai chiều. Các annotation của thư viện JSON có thể xử lý một số vòng tham chiếu ở tầng trình bày, nhưng không làm giảm lượng dữ liệu SDN đã tải vào bộ nhớ.

## 7. Khi nào nên dùng quan hệ hai chiều?

Ánh xạ hai chiều không phải lúc nào cũng sai. Nó có thể phù hợp khi cả hai phía thực sự là một phần của mô hình nghiệp vụ, số lượng quan hệ được kiểm soát và ứng dụng thường xuyên cần điều hướng từ cả hai đầu trong cùng một use case.

Trước khi thêm thuộc tính ngược, hãy cân nhắc:

1. Cả hai phía có cần tồn tại trong object graph của cùng một thao tác không?
2. Số lượng relationship trực tiếp có thể lớn đến mức nào?
3. Có cần cập nhật quan hệ từ cả hai phía hay chỉ cần truy vấn chiều ngược?
4. Độ sâu đọc đã được xác định rõ chưa?
5. API có trả entity trực tiếp và có nguy cơ tuần tự hóa vòng tham chiếu không?

Nếu chỉ một chức năng cần chiều ngược, truy vấn Cypher hoặc projection riêng thường là lựa chọn đơn giản hơn. Nếu thật sự cần ánh xạ hai chiều, hãy xác định rõ phía chịu trách nhiệm cập nhật relationship, giới hạn độ sâu đọc và kiểm thử cả trường hợp đồ thị có chu trình.

## 8. Danh sách kiểm tra thiết kế

Trước khi hoàn thiện một entity có quan hệ, hãy kiểm tra:

- Mỗi thuộc tính `@Relationship` có mục đích truy cập cụ thể và có hướng đúng với mô hình dữ liệu.
- Không khai báo thuộc tính ngược chỉ để thuận tiện cho một truy vấn đơn lẻ.
- Các thao tác đọc có giới hạn độ sâu phù hợp với lượng dữ liệu cần thiết.
- Truy vấn chiều ngược dùng mẫu Cypher có hướng rõ ràng và tham số hóa đầu vào.
- Danh sách lớn được lọc, giới hạn và chỉ trả về các trường cần thiết.
- API sử dụng projection hoặc DTO khi không cần toàn bộ entity.
- Kiểm thử bao gồm node không có quan hệ, node có nhiều quan hệ và đồ thị có chu trình.

Thiết kế quan hệ một cách có chủ đích giúp SDN ánh xạ đúng phần đồ thị mà use case cần. Neo4j vẫn giữ khả năng truy vấn linh hoạt từ cả hai phía của relationship, trong khi ứng dụng Java chỉ tải và trả về lượng dữ liệu phù hợp với chức năng đang thực hiện.
