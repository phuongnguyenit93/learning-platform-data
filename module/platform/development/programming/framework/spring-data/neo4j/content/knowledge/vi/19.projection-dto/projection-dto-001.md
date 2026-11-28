# Tách dữ liệu trả về khỏi entity dùng cho ghi

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao entity dùng để lưu đồ thị không nhất thiết là kiểu dữ liệu phù hợp cho API đọc.
- Tạo interface projection để chỉ đọc các property và relationship cần thiết.
- Dùng DTO hoặc Java record để trả về dữ liệu đã chọn lọc, biến đổi hoặc tổng hợp.
- Phân biệt closed projection, open projection và dynamic projection.
- Ánh xạ DTO từ derived query và custom Cypher query.
- Tổ chức luồng đọc và luồng ghi riêng biệt, đồng thời hiểu cách SDN hỗ trợ lưu theo projection khi thật sự cần.

## 1. Vì sao nên tách mô hình đọc và mô hình ghi?

Một domain entity trong Spring Data Neo4j (SDN) mô tả node cùng các relationship mà ứng dụng quản lý. Entity thường chứa định danh, property và các liên kết cần cho nghiệp vụ ghi dữ liệu.

Trong khi đó, một màn hình hoặc API đọc thường chỉ cần một phần thông tin. Ví dụ, trang danh sách người dùng có thể chỉ hiển thị tên, email và tên thành phố. Nó không cần toàn bộ quan hệ công việc, nhóm, người theo dõi và các nhánh đồ thị khác của Person.

Nếu mọi truy vấn đều trả về entity đầy đủ, ứng dụng có thể đọc nhiều dữ liệu không cần thiết, truyền nhiều dữ liệu qua mạng và làm cho API phụ thuộc chặt vào cấu trúc persistence.

Có thể tách thành ba vai trò:

| Kiểu | Mục đích | Ví dụ |
|---|---|---|
| Domain entity | Mô hình hóa dữ liệu được quản lý và dùng trong nghiệp vụ ghi | Person |
| Projection | Mô tả một góc nhìn đọc giới hạn trên entity | PersonCard |
| DTO (Data Transfer Object) | Mang dữ liệu trả về theo cấu trúc riêng của use case/API | PersonCardDto |

Projection và DTO không thay thế entity. Chúng giúp ứng dụng chọn đúng dữ liệu cần trả về cho từng thao tác.

Kiểu projection cần là một kiểu riêng nằm ngoài hệ phân cấp của entity được chiếu. Nếu trả về chính entity, một lớp cha của entity hoặc interface mà entity đã triển khai, Spring Data có thể trả về entity đã materialize đầy đủ thay vì một projection giới hạn.

## 2. Interface projection: chỉ công bố những thuộc tính cần đọc

Interface projection là interface khai báo các accessor cho property cần truy xuất. SDN tạo proxy projection dựa trên domain object và chỉ chuyển những property hoặc relationship cần cho projection.

Giả sử domain entity:

~~~java
@Node("Person")
public class Person {

    @Id
    private String personId;

    private String firstName;
    private String lastName;
    private String email;

    @Relationship(type = "LIVES_IN")
    private City city;

    @Relationship(type = "WORKS_WITH")
    private Set<Person> colleagues = new LinkedHashSet<>();

    @Relationship(type = "FOLLOWS")
    private Set<Person> follows = new LinkedHashSet<>();

    // Constructor, getter và setter được lược bỏ.
}
~~~

Màn hình danh sách chỉ cần tên và email. Ta tạo projection:

~~~java
public interface PersonListItem {

    String getFirstName();

    String getLastName();

    String getEmail();
}
~~~

Repository có thể trả về projection thay cho entity:

~~~java
public interface PersonRepository
        extends Neo4jRepository<Person, String> {

    List<PersonListItem> findByLastName(String lastName);
}
~~~

Khi gọi findByLastName, kiểu trả về PersonListItem yêu cầu SDN cung cấp các thuộc tính được khai báo trong interface. Các relationship colleagues và follows không thuộc projection này nên không cần được lấy chỉ để phục vụ màn hình danh sách.

Tên accessor phải khớp với property của domain type. getFirstName() tương ứng property firstName; getEmail() tương ứng property email. Projection là một góc nhìn của entity gốc, vì vậy nó không tự định nghĩa một schema node mới trong Neo4j.

### Projection lồng nhau cho relationship

Nếu màn hình cần thêm tên thành phố, có thể khai báo projection lồng nhau:

~~~java
public interface PersonDetailView {

    String getFirstName();

    String getLastName();

    String getEmail();

    CityView getCity();

    interface CityView {
        String getName();
    }
}
~~~

Repository:

~~~java
Optional<PersonDetailView> findByPersonId(String personId);
~~~

SDN sẽ đọc property của Person và phần name được khai báo trong projection của City. Các property khác của City và những relationship không xuất hiện trong projection không cần được tải cho góc nhìn này.

Projection lồng nhau phù hợp với graph có cấu trúc rõ. Mỗi cấp lồng nhau tương ứng một cấp dữ liệu cần đọc. Nếu khai báo quá nhiều cấp, truy vấn vẫn có thể mở rộng thành một graph lớn; hãy thiết kế projection theo đúng màn hình hoặc use case.

## 3. Closed và open interface projection

### Closed projection

Một interface projection là closed projection khi các accessor của nó chỉ trỏ đến property có sẵn trên aggregate root hoặc các kiểu được chiếu. Vì SDN biết trước những property cần thiết, framework có thể tối ưu truy vấn và chỉ chuyển phần dữ liệu phục vụ projection.

Ví dụ:

~~~java
public interface PersonNameView {

    String getFirstName();

    String getLastName();
}
~~~

Projection này chỉ yêu cầu hai property. Đây là lựa chọn nên ưu tiên khi cần một góc nhìn dữ liệu đơn giản và có thể xác định trước.

### Open projection

Open projection dùng annotation Value và SpEL để tính giá trị từ target object:

~~~java
import org.springframework.beans.factory.annotation.Value;

public interface PersonGreetingView {

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();
}
~~~

Biểu thức có thể truy cập các property của target. Vì framework không thể biết trước biểu thức sẽ cần những property nào, khả năng tối ưu truy vấn theo projection bị hạn chế.

Nếu phép tính chỉ cần các accessor đã khai báo, có thể dùng default method để giữ projection ở dạng closed:

~~~java
public interface PersonNameView {

    String getFirstName();

    String getLastName();

    default String getDisplayName() {
        return getFirstName() + " " + getLastName();
    }
}
~~~

Với phép biến đổi phức tạp, hãy chuyển logic sang service hoặc Spring bean chuyên trách thay vì nhồi nhiều biểu thức vào SpEL.

## 4. DTO projection: trả về cấu trúc dữ liệu riêng

DTO là lớp hoặc record chỉ chứa dữ liệu mà use case cần truyền ra ngoài. Không giống interface projection, DTO được khởi tạo thành đối tượng thực, không phải proxy dựa trên entity.

Ví dụ màn hình chỉ cần tên đầy đủ và email:

~~~java
public record PersonContactDto(
    String firstName,
    String lastName,
    String email
) {
}
~~~

Repository có thể dùng DTO làm kiểu trả về:

~~~java
public interface PersonRepository
        extends Neo4jRepository<Person, String> {

    List<PersonContactDto> findByLastName(String lastName);
}
~~~

Với DTO dựa trên constructor, SDN dùng tên tham số constructor để xác định property cần lấy. Java record rất phù hợp vì constructor canonical và tên component được khai báo rõ ràng.

Nếu dùng một class DTO thông thường, hãy cung cấp constructor phù hợp. Khi có nhiều constructor, dùng annotation PersistenceCreator trên constructor mà Spring Data cần sử dụng để xác định các input property.

Ví dụ:

~~~java
import org.springframework.data.annotation.PersistenceCreator;

public class PersonContactDto {

    private final String firstName;
    private final String email;

    protected PersonContactDto() {
        this.firstName = null;
        this.email = null;
    }

    @PersistenceCreator
    public PersonContactDto(String firstName, String email) {
        this.firstName = firstName;
        this.email = email;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Trong ví dụ, constructor được đánh dấu là constructor Spring Data dùng để xác định hai property cần chiếu. Với Java record chỉ có canonical constructor, thường không cần thêm annotation này.

DTO projection phù hợp khi:

- API cần cấu trúc khác với domain entity.
- Cần gộp dữ liệu từ nhiều node thành một kết quả phẳng.
- Cần trả về số lượng, điểm, trạng thái hoặc giá trị tính toán.
- Muốn tránh đưa persistence entity trực tiếp ra lớp controller.

### Interface projection và DTO khác nhau thế nào?

| Khía cạnh | Interface projection | DTO projection |
|---|---|---|
| Dạng khai báo | Interface accessor | Class hoặc record |
| Đối tượng trả về | Proxy dựa trên entity | Instance DTO thực |
| Nested projection | Có thể dùng interface lồng nhau | Không hỗ trợ nested projection theo cơ chế DTO |
| Logic tính toán | Default method hoặc SpEL | Constructor, method hoặc logic ở service |
| Thuộc tính bổ sung từ custom query | Phụ thuộc mapping projection | Có thể nhận property bổ sung nếu query trả alias phù hợp |
| Mục đích phổ biến | Góc nhìn đọc một phần entity | Hợp đồng dữ liệu độc lập cho API/use case |

DTO không phải một domain entity mới. Nó không được lưu thành node chỉ vì có cùng tên property với entity.

## 5. DTO với custom Cypher query

Một lợi thế của DTO trong SDN là custom query có thể trả về thêm property không tồn tại trong domain entity.

Giả sử cần trả về tên người dùng, tên thành phố và số đồng nghiệp. Ta định nghĩa DTO:

~~~java
public record PersonOverviewDto(
    String firstName,
    String lastName,
    String cityName,
    Long colleagueCount
) {
}
~~~

Repository:

~~~java
@Query("""
    MATCH (p:Person {personId: $personId})
    OPTIONAL MATCH (p)-[:LIVES_IN]->(c:City)
    CALL {
        WITH p
        OPTIONAL MATCH (p)-[:WORKS_WITH]->(colleague:Person)
        RETURN count(DISTINCT colleague) AS colleagueCount
    }
    RETURN p.firstName AS firstName,
           p.lastName AS lastName,
           c.name AS cityName,
           colleagueCount
    """)
Optional<PersonOverviewDto> findOverview(
    @Param("personId") String personId
);
~~~

Các alias trong RETURN phải khớp chính xác với property hoặc component của DTO:

- firstName khớp firstName.
- lastName khớp lastName.
- cityName khớp cityName.
- colleagueCount khớp colleagueCount.

cityName và colleagueCount là dữ liệu được tạo bởi truy vấn, không cần trở thành property của entity Person. Đây là cách giữ domain model gọn trong khi vẫn cung cấp dữ liệu tổng hợp cho API.

Ví dụ trên giả định mỗi Person có tối đa một City theo quan hệ LIVES_IN. Nếu một Person có thể liên kết với nhiều City, query sẽ tạo nhiều record cho Person; khi đó cần xác định rõ DTO muốn trả về một City hay danh sách City và thiết kế query tương ứng.

### Kiểu dữ liệu DTO được hỗ trợ

Với DTO projection, SDN lấy property từ domain type trước. Nếu DTO khai báo thêm thuộc tính, framework tìm giá trị tương ứng trong record mà query trả về. Tên property phải khớp chính xác.

Các kiểu đơn giản mà SDN nhận biết và các persistent entity được hỗ trợ; collection của những kiểu này cũng có thể được ánh xạ. Map không được hỗ trợ như một kiểu collection projection theo cơ chế này.

Nếu DTO yêu cầu một giá trị nhưng query không trả alias tương ứng, giá trị đó có thể không được ánh xạ như mong đợi hoặc việc tạo DTO có thể thất bại. Hãy kiểm tra constructor/component name và record output cùng nhau.

## 6. Dynamic projection: chọn kiểu trả về lúc gọi phương thức

Trong một số trường hợp, cùng một điều kiện tìm kiếm cần trả về nhiều góc nhìn khác nhau. Spring Data hỗ trợ dynamic projection thông qua tham số Class<T>:

~~~java
public interface PersonRepository
        extends Neo4jRepository<Person, String> {

    <T> List<T> findByLastName(
        String lastName,
        Class<T> projectionType
    );
}
~~~

Có thể gọi cùng một phương thức theo các kiểu khác nhau:

~~~java
List<Person> people =
    repository.findByLastName("Nguyen", Person.class);

List<PersonNameView> names =
    repository.findByLastName("Nguyen", PersonNameView.class);

List<PersonContactDto> contacts =
    repository.findByLastName("Nguyen", PersonContactDto.class);
~~~

Cách này giảm số lượng finder method khi điều kiện lọc giống nhau nhưng caller cần các kiểu dữ liệu khác nhau. Dùng dynamic projection khi các kiểu kết quả đều phù hợp với cùng domain type và truy vấn nền. Nếu mỗi kiểu kết quả cần phép join, aggregation hoặc cấu trúc Cypher khác nhau, hãy khai báo các phương thức query riêng.

## 7. Giữ luồng đọc và luồng ghi tách biệt

Projection và DTO nên được xem là hợp đồng dữ liệu cho thao tác đọc. Khi cập nhật nghiệp vụ, service nên tải domain entity cần thay đổi, áp dụng quy tắc nghiệp vụ rồi lưu entity đó.

Ví dụ command DTO nhận yêu cầu đổi email:

~~~java
public record ChangeEmailCommand(
    String personId,
    String newEmail
) {
}
~~~

Service tải entity và thực hiện thay đổi:

~~~java
@Service
public class PersonService {

    private final PersonRepository people;

    public PersonService(PersonRepository people) {
        this.people = people;
    }

    @Transactional
    public void changeEmail(ChangeEmailCommand command) {
        Person person = people.findById(command.personId())
            .orElseThrow(() ->
                new IllegalArgumentException("Person not found")
            );

        person.setEmail(command.newEmail());
        people.save(person);
    }
}
~~~

Ở đây:

- ChangeEmailCommand là dữ liệu đầu vào của thao tác ghi.
- Person là entity được dùng để áp dụng quy tắc nghiệp vụ.
- PersonRepository lưu entity sau khi thay đổi.
- Projection hoặc DTO đọc có thể được dùng riêng để trả kết quả cho controller.

Cách tổ chức này giúp API không phụ thuộc vào toàn bộ cấu trúc entity. Việc thay đổi domain model cũng ít ảnh hưởng đến hợp đồng đọc nếu DTO vẫn giữ nguyên.

## 8. Dùng projection làm phạm vi lưu với Neo4jTemplate

Trong SDN, projection không chỉ giới hạn dữ liệu đọc. Nó còn có thể được dùng làm blueprint cho thao tác lưu thông qua Neo4jTemplate.

Ví dụ projection chỉ cho phép cập nhật tên và email:

~~~java
public interface PersonContactWriteView {

    String getFirstName();

    String getLastName();

    String getEmail();
}
~~~

Nếu đã có domain object cần lưu, có thể chỉ định projection cho thao tác save:

~~~java
PersonContactWriteView savedView =
    neo4jTemplate.saveAs(person, PersonContactWriteView.class);
~~~

Hoặc bắt đầu thao tác lưu bằng domain type và truyền projection value:

~~~java
public record PersonContactWriteDto(
    String firstName,
    String lastName,
    String email
) {
}

PersonContactWriteDto savedDto =
    neo4jTemplate.save(Person.class).one(contactDto);
~~~

Các phương thức trên là API fluent của Neo4jTemplate. Chúng giới hạn property và relationship được cập nhật theo projection. Biến contactDto là một DTO đã được tạo với dữ liệu cần lưu. Chỉ dùng cách này khi muốn kiểm soát rõ phạm vi ghi ở tầng persistence.

Có hai lưu ý quan trọng:

1. Nếu cần cập nhật property của node liên quan, projection phải bao gồm association property tương ứng.
2. Hãy tải ít nhất toàn bộ dữ liệu mà bạn muốn giữ lại khi lưu. Nếu một relationship hiện có không được tải và không có trong projection lưu, thao tác lưu có thể loại bỏ relationship đó.

Projection interface thường là góc nhìn chỉ đọc và không thể sửa trực tiếp như một DTO mutable. Nếu cần thay đổi dữ liệu, hãy tạo domain entity từ projection hoặc dùng DTO có thể cập nhật, sau đó gọi API lưu phù hợp.

Không nên dùng một projection đọc thiếu dữ liệu rồi gọi repository.save như thể đó là entity đầy đủ. Nếu chỉ muốn cập nhật một property độc lập, hãy cân nhắc custom Cypher SET để phạm vi ghi được xác định trực tiếp.

## 9. Chọn projection hay DTO trong từng tình huống

| Tình huống | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Danh sách chỉ cần vài property của entity | Closed interface projection | Khai báo ngắn, SDN biết chính xác property cần đọc |
| Cần một relationship lồng nhau ở vài cấp | Nested interface projection | Diễn đạt trực tiếp cấu trúc graph cần đọc |
| Cần tính một giá trị từ các accessor đã có | Default method trong projection | Không cần tải thêm dữ liệu để tính |
| Cần biểu thức SpEL trên target | Open projection | Linh hoạt nhưng ít cơ hội tối ưu query |
| API cần dữ liệu phẳng hoặc tổng hợp | DTO/record | Hợp đồng trả về độc lập với entity |
| Custom Cypher trả về giá trị tính toán bổ sung | DTO projection | Alias trong record có thể cấp thêm property |
| Nhiều caller cần các kiểu kết quả khác nhau trên cùng finder | Dynamic projection | Chọn kiểu tại thời điểm gọi |
| Cần cập nhật một phần graph có chủ đích | Neo4jTemplate save projection hoặc custom Cypher | Kiểm soát rõ phạm vi persistence |

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Getter projection trả về null | Tên accessor không khớp property domain | Đối chiếu tên Java property và getter |
| Projection không giảm dữ liệu như kỳ vọng | Dùng open projection hoặc khai báo quá nhiều nested accessor | Ưu tiên closed projection và chỉ khai báo trường cần thiết |
| Nested projection không có dữ liệu | Domain relationship chưa được ánh xạ hoặc query không trả đủ dữ liệu | Kiểm tra mapping và record Cypher |
| DTO không tạo được | Constructor/component không khớp property hoặc thiếu alias trong custom query | Đối chiếu constructor và tên alias |
| DTO không nhận property tổng hợp | Query không trả alias chính xác | Dùng alias khớp tên DTO |
| DTO cần nested projection | Class-based DTO không hỗ trợ nested projection như interface | Dùng interface projection hoặc làm phẳng DTO |
| Dynamic projection không được nhận diện | Chữ ký Class<T> không khớp generic return type | Kiểm tra chữ ký phương thức |
| Thay đổi projection làm mất relationship | Lưu projection không chứa association cần giữ | Nạp và đưa vào projection tất cả dữ liệu cần bảo toàn |
| Entity bị ghi thiếu dữ liệu | Dùng object đọc một phần như entity đầy đủ để gọi save | Tách read DTO và write entity; dùng save projection có chủ đích |

## 11. Thực hành: xây dựng API danh sách và cập nhật Person

Tạo entity Person có các property personId, firstName, lastName, email và relationship đến City.

### Bài đọc

Tạo interface projection:

~~~java
public interface PersonDirectoryItem {

    String getFirstName();

    String getLastName();

    String getEmail();

    CityItem getCity();

    interface CityItem {
        String getName();
    }
}
~~~

Khai báo repository:

~~~java
public interface PersonRepository
        extends Neo4jRepository<Person, String> {

    List<PersonDirectoryItem> findByLastName(String lastName);
}
~~~

Thử gọi repository và xác nhận:

- Kết quả có tên, email và tên thành phố.
- Các relationship colleagues và follows không xuất hiện trong hợp đồng projection.
- Thay đổi domain entity bằng cách thêm một property không làm API phải trả property đó nếu projection không khai báo.

### Bài DTO

Tạo DTO:

~~~java
public record PersonDirectoryDto(
    String firstName,
    String lastName,
    String cityName
) {
}
~~~

Viết custom query trả về các alias firstName, lastName và cityName. Kiểm tra DTO được khởi tạo với đúng dữ liệu.

### Bài ghi

Tạo ChangeEmailCommand và service:

1. Nhận personId và newEmail.
2. Tải Person bằng repository.
3. Thay đổi email theo quy tắc nghiệp vụ.
4. Lưu Person trong transaction.
5. Đọc lại bằng PersonDirectoryItem để xác nhận kết quả.

Cuối cùng, thử thêm một relationship mới vào Person và so sánh dữ liệu trả về giữa entity, projection và DTO. Giải thích vì sao mỗi kiểu có một phạm vi dữ liệu khác nhau.

## Kết luận

Projection và DTO giúp tách hợp đồng đọc khỏi domain entity dùng cho ghi. Interface projection phù hợp với góc nhìn giới hạn trên entity và relationship; DTO phù hợp với dữ liệu phẳng, tổng hợp hoặc cấu trúc riêng của API. Custom query có thể bổ sung property cho DTO bằng alias khớp chính xác với tên thuộc tính.

Hãy ưu tiên closed projection cho truy vấn đọc đơn giản, dùng nested projection khi cần một phần graph, và dùng DTO khi kết quả không còn giống cấu trúc entity. Với thao tác ghi, tải domain entity và áp dụng quy tắc nghiệp vụ trong service. Nếu cần lưu một phần graph có chủ đích, dùng API save projection của Neo4jTemplate và bảo đảm mọi property/relationship cần giữ đều được đưa vào phạm vi lưu.

## Tài liệu tham khảo

- [Spring Data Neo4j: Projections](https://docs.spring.io/spring-data/neo4j/reference/projections/sdn-projections.html)
- [Spring Data Commons: Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html)
- [Neo4jTemplate API: save và saveAs](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jTemplate.html)
