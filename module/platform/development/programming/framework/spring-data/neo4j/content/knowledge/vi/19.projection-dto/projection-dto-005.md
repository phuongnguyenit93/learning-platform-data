# Projection động qua tham số Class của phương thức repository

Trong Spring Data Neo4j (SDN), một repository method có thể trả về entity, interface projection hoặc DTO. Khi mỗi ca sử dụng cần một hình dạng dữ liệu khác nhau từ cùng một truy vấn, không nhất thiết phải tạo nhiều method gần giống nhau. Dynamic projection cho phép chọn kiểu kết quả ngay lúc gọi method thông qua tham số `Class<T>`.

Ví dụ, một chức năng danh bạ có thể cần toàn bộ `Person` cho thao tác chỉnh sửa, chỉ cần tên cho danh sách gọn, hoặc cần DTO chứa thông tin liên hệ cho một màn hình khác. Một method generic có thể phục vụ các nhu cầu này bằng cách nhận kiểu projection ở thời điểm gọi.

## 1. Dynamic projection là gì?

Projection là một góc nhìn có chọn lọc trên aggregate/entity. Interface projection chỉ công khai các thuộc tính cần đọc; DTO projection tạo một kiểu dữ liệu cụ thể cho kết quả. Với dynamic projection, kiểu projection được truyền vào repository thay vì cố định trong kiểu trả về của method.

Ví dụ chữ ký tổng quát:

~~~java
<T> List<T> findByStatus(String status, Class<T> projectionType);
~~~

Tham số `projectionType` quyết định kiểu dữ liệu của từng phần tử trong danh sách. Cùng method có thể trả về `Person`, một interface projection hoặc một DTO, tùy lớp được truyền vào.

Trong SDN, projection còn ảnh hưởng đến những property và relationship được chuyển từ Neo4j về ứng dụng. Vì vậy, chọn projection phù hợp có thể giảm lượng dữ liệu phải đọc và ánh xạ khi entity có nhiều thuộc tính hoặc quan hệ không cần thiết cho một use case.

## 2. Khai báo entity và các kiểu projection

Giả sử domain có entity `Person`:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {
    @Id
    private String id;

    private String name;

    private String email;

    private String status;

    // Constructor, getter và setter được lược bỏ.
}
~~~

Một interface projection chỉ cần mã và tên:

~~~java
public interface PersonNameView {
    String getId();
    String getName();
}
~~~

Một DTO record cho thông tin liên hệ:

~~~java
public record PersonContactDto(
    String id,
    String name,
    String email
) {}
~~~

Tên property trong projection phải khớp với property của domain entity, ví dụ `getName()` tương ứng với `name`. Với DTO, tên tham số constructor cũng cần tương ứng với property cần ánh xạ. Java record phù hợp vì có một canonical constructor và tên component rõ ràng.

## 3. Khai báo repository với Class<T>

Repository có thể kế thừa `Neo4jRepository` và bổ sung method generic:

~~~java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {
    <T> List<T> findByStatus(String status, Class<T> projectionType);
}
~~~

Spring Data nhận diện `Class<T>` là tham số chọn dynamic projection khi kiểu generic `T` của `Class<T>` trùng với kiểu generic trong phần trả về của method. Tham số này được dùng để chọn projection, không được bind như một tham số truy vấn Cypher thông thường.

Đặt tham số chọn projection ở cuối danh sách tham số để chữ ký method dễ nhận diện và nhất quán với quy ước của SDN.

Có thể gọi method theo ba cách:

~~~java
// Lấy entity đầy đủ theo mô hình Person.
List<Person> people = personRepository.findByStatus("ACTIVE", Person.class);

// Chỉ lấy ID và tên.
List<PersonNameView> names =
    personRepository.findByStatus("ACTIVE", PersonNameView.class);

// Lấy DTO thông tin liên hệ.
List<PersonContactDto> contacts =
    personRepository.findByStatus("ACTIVE", PersonContactDto.class);
~~~

Ba lời gọi dùng chung điều kiện `status = ACTIVE`, nhưng kiểu phần tử trả về khác nhau. Cách này giảm việc lặp các method như `findActivePeople`, `findActiveNames` và `findActiveContacts` khi truy vấn cơ sở giống nhau.

## 4. Dynamic projection với interface projection

Interface projection là lựa chọn phù hợp khi cần một tập property cố định từ entity. Spring Data tạo proxy cho interface và chuyển lời gọi getter đến dữ liệu projection.

Dynamic projection có thể chọn closed hoặc open interface projection. Với closed projection, framework biết trước các property được truy cập; open projection linh hoạt hơn nhờ SpEL nhưng khó tối ưu phạm vi dữ liệu hơn.

Ví dụ:

~~~java
public interface PersonNameView {
    String getId();
    String getName();
}
~~~

Khi gọi:

~~~java
List<PersonNameView> result =
    personRepository.findByStatus("ACTIVE", PersonNameView.class);
~~~

SDN dùng các accessor của projection để xác định dữ liệu cần thiết. Với closed projection, mọi accessor đều tương ứng trực tiếp với property đã biết của entity. Điều này giúp framework xác định rõ phần dữ liệu cần tải.

Có thể tạo projection lồng nhau nếu domain có cấu trúc quan hệ phù hợp. Tuy nhiên, mỗi tầng projection có thể làm phát sinh thêm dữ liệu cần tải. Hãy giữ cấu trúc projection ở đúng độ sâu mà use case cần, nhất là khi quan hệ có số lượng lớn.

Open projection dùng `@Value` và SpEL có thể tính giá trị dựa trên target entity. Vì biểu thức có thể truy cập nhiều thuộc tính, khả năng tối ưu phạm vi property thường kém rõ ràng hơn closed projection. Nếu chỉ cần ghép vài trường, cân nhắc default method trên interface projection hoặc DTO.

## 5. Dynamic projection với DTO class hoặc record

Nếu muốn kiểu trả về có cấu trúc dữ liệu cụ thể, có thể dùng class hoặc record thay cho interface. Ví dụ `PersonContactDto` ở trên:

~~~java
List<PersonContactDto> contacts =
    personRepository.findByStatus("ACTIVE", PersonContactDto.class);
~~~

DTO projection không tạo proxy. SDN ánh xạ dữ liệu vào constructor của DTO. Với DTO class, nên cung cấp một constructor duy nhất để Spring Data xác định các input property. Nếu class có nhiều constructor, đánh dấu constructor cần dùng bằng `@PersistenceCreator`.

Ví dụ DTO class có constructor được chỉ định:

~~~java
import org.springframework.data.annotation.PersistenceCreator;

public class PersonCard {
    private final String id;
    private final String name;

    @PersistenceCreator
    public PersonCard(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() { return id; }
    public String getName() { return name; }
}
~~~

Tên tham số constructor cần giữ được metadata tên để ánh xạ đúng property; với class Java thông thường, hãy bảo đảm quá trình biên dịch giữ tên tham số (ví dụ bật tùy chọn `-parameters`). Java record thường đơn giản hơn vì component name và canonical constructor đã được xác định rõ.

## 6. Dùng dynamic projection với @Query tùy chỉnh

Dynamic projection cũng có thể kết hợp với method dùng `@Query`. Điều quan trọng là phần `RETURN` phải cung cấp dữ liệu phù hợp với kiểu projection được chọn.

Ví dụ, màn hình hồ sơ cần thêm số nhóm mà một người tham gia. Đây là giá trị tính toán không phải property của `Person`, vì vậy dùng DTO có thêm `teamCount`:

~~~java
public record PersonTeamCountDto(
    String id,
    String name,
    Long teamCount
) {}
~~~

Repository khai báo method generic với Cypher tùy chỉnh:

~~~java
import java.util.List;

import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
    MATCH (person:Person {status: $status})
    OPTIONAL MATCH (person)-[:MEMBER_OF]->(team:Team)
    RETURN person, count(DISTINCT team) AS teamCount
    """)
<T> List<T> findByStatusWithTeamCount(
    @Param("status") String status,
    Class<T> projectionType
);
~~~

Khi gọi với `PersonTeamCountDto.class`, SDN dùng node `person` để lấy các property thuộc domain và tìm thêm cột `teamCount` trong record Cypher. Tên alias `teamCount` phải khớp chính xác với property của DTO. Với custom query, DTO có thể khai báo thêm các property đơn giản hoặc kiểu persistent entity mà record trả về có thể cung cấp; collection của các kiểu này cũng được hỗ trợ, còn map không phải kiểu bổ sung được ánh xạ theo cơ chế DTO projection này.

~~~java
List<PersonTeamCountDto> profiles =
    personRepository.findByStatusWithTeamCount("ACTIVE", PersonTeamCountDto.class);
~~~

Với custom query có giá trị tính toán bổ sung, DTO projection thường phù hợp hơn interface projection nếu giá trị đó không phải property của domain entity. Interface projection chủ yếu truy cập property thuộc domain type.

## 7. Phân biệt Class<T> chọn projection với Class<?> là tham số truy vấn

Spring Data kiểm tra tham số kiểu `Class` để xác định nó có phải dynamic projection selector hay không. Nếu generic type của `Class<T>` trùng với generic return type `T`, tham số đó được xem là projection selector và không có sẵn để dùng trong truy vấn hoặc biểu thức SpEL.

Ví dụ dynamic projection selector:

~~~java
<T> List<T> findByStatus(String status, Class<T> projectionType);
~~~

Nếu muốn truyền một đối tượng `Class` như dữ liệu truy vấn thông thường, dùng `Class<?>` để Spring Data không hiểu nhầm đó là selector:

`Class<?>` vẫn có thể được tham chiếu trong query hoặc biểu thức SpEL. Nếu Cypher cần một giá trị để so sánh với property, hãy chuyển class thành scalar được Neo4j hỗ trợ, chẳng hạn tên class (`categoryType.name` hoặc `categoryType.getName()`), rồi mới bind giá trị đó. Không truyền trực tiếp đối tượng `Class` như một property value của Neo4j.

Nếu một method vừa cần tham số `Class` cho query vừa cần dynamic projection, hãy khai báo hai tham số riêng với vai trò và kiểu generic phân biệt rõ; không dùng cùng một tham số cho cả hai mục đích.

## 8. Những giới hạn và lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không nhận projection được truyền vào | Chữ ký method không dùng `Class<T>` khớp với kiểu trả về generic | Kiểm tra `<T> List<T>` và `Class<T>` cùng dùng một `T` |
| Tham số Class không xuất hiện trong Cypher | Spring Data đã nhận diện nó là dynamic projection selector | Đây là hành vi dự kiến; dùng `Class<?>` nếu cần tham chiếu tham số trong query/SpEL và chuyển nó thành scalar trước khi bind |
| Projection không có giá trị ở một getter | Tên accessor không khớp property domain hoặc alias kết quả | Đối chiếu tên property và alias trong `RETURN` |
| DTO không khởi tạo được | Có nhiều constructor nhưng chưa chỉ định constructor persistence | Dùng một constructor hoặc `@PersistenceCreator` |
| DTO thiếu trường tính toán | Custom query không trả alias tương ứng hoặc kiểu không hỗ trợ | Bổ sung cột với đúng tên và kiểu phù hợp |
| Query trả quá nhiều dữ liệu | Projection có nhiều property/relationship hoặc nested projection quá sâu | Thu hẹp projection và kiểm tra truy vấn được tạo |
| Dùng projection trên method CRUD kế thừa | Method đang override base repository method và vẫn gọi implementation gốc | Tạo query method riêng, không ghi đè method CRUD chỉ để đổi kiểu trả về |

Dynamic projection chỉ thay đổi hình dạng kết quả và phạm vi dữ liệu được ánh xạ. Nó không tự thay đổi điều kiện nghiệp vụ, không thay thế authorization và không cho phép client tùy ý yêu cầu mọi kiểu Java trong ứng dụng.

## 9. Chọn kiểu projection an toàn ở tầng service

Không nên nhận tên class từ request HTTP rồi tải class bằng reflection để truyền thẳng vào repository. Hãy để service chọn một trong những kiểu projection được ứng dụng hỗ trợ:

~~~java
public List<PersonNameView> findActiveNames() {
    return personRepository.findByStatus("ACTIVE", PersonNameView.class);
}

public List<PersonContactDto> findActiveContacts() {
    return personRepository.findByStatus("ACTIVE", PersonContactDto.class);
}
~~~

Cách này giữ kiểu trả về tường minh ở API service và giới hạn các projection được phép sử dụng. Nếu endpoint cần nhiều dạng response, có thể định nghĩa các endpoint hoặc phương thức service riêng; không nhất thiết phải phơi bày tham số `Class<T>` ra giao diện bên ngoài.

## 10. Kiểm thử dynamic projection

Với mỗi repository method dynamic, nên kiểm tra các trường hợp:

1. Truyền `Person.class` và xác nhận entity có các property cần thiết.
2. Truyền interface projection và xác nhận chỉ các getter đã khai báo truy cập được dữ liệu đúng.
3. Truyền DTO/record và xác nhận constructor nhận đúng property.
4. Với `@Query`, xác nhận alias của các giá trị tính toán khớp chính xác với property DTO.
5. Kiểm tra kết quả rỗng và dữ liệu có property null.
6. Xác nhận các relationship không cần thiết không bị tải ngoài dự kiến.

Nếu dùng DTO có nhiều constructor, cần kiểm thử constructor được `@PersistenceCreator` chọn. Nếu projection có quan hệ lồng nhau, hãy kiểm tra cả trường hợp không có node liên quan và trường hợp có nhiều node liên quan.

## 11. Bài tập tự kiểm tra

1. Dynamic projection khác projection cố định ở điểm nào?
2. Vì sao method `<T> List<T> findByStatus(String status, Class<T> type)` có thể trả về entity hoặc projection khác nhau?
3. Tên getter của interface projection cần tương ứng với property nào?
4. Khi DTO có nhiều constructor, dùng annotation nào để chỉ định constructor ánh xạ?
5. Vì sao `Class<T>` có thể không được bind thành tham số Cypher, và khi nào cần dùng `Class<?>`?
6. Với custom `@Query` trả thêm `teamCount`, vì sao DTO cần property có đúng alias `teamCount`?
7. Vì sao không nên cho client bên ngoài truyền tên class tùy ý để chọn projection?

Khi hoàn thành bài học, bạn cần thiết kế được repository method generic dùng `Class<T>`, chọn entity/interface/DTO tại thời điểm gọi, hiểu quy tắc nhận diện tham số projection và bảo đảm kết quả Cypher tương thích với kiểu Java. Đây là cách tái sử dụng truy vấn hiệu quả mà vẫn giữ hợp đồng dữ liệu rõ ràng cho từng use case.

## Tài liệu tham khảo

- [Spring Data Neo4j – Projections](https://docs.spring.io/spring-data/neo4j/reference/projections/sdn-projections.html)
- [Spring Data Commons – Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html)
