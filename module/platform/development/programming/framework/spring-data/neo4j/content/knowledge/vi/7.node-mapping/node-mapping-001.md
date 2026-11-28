# Đánh dấu entity bằng @Node và nhận diện lớp trong mapping context

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của `@Node` trong việc ánh xạ một lớp Java thành node của Neo4j.
- Xác định nhãn node mặc định và cách đặt nhãn tường minh.
- Mô tả cách Spring Data Neo4j nhận diện domain class và xây dựng metadata trong mapping context.
- Phân biệt metadata ánh xạ trong ứng dụng với dữ liệu node đang tồn tại trong cơ sở dữ liệu.
- Tổ chức entity, định danh và repository để việc ánh xạ nhất quán.

## 1. Từ lớp Java đến node trong Neo4j

Trong Java, ta mô tả dữ liệu bằng lớp và đối tượng. Trong Neo4j, dữ liệu được lưu dưới dạng node, relationship và property. Spring Data Neo4j (SDN) cần một quy tắc để biết lớp nào đại diện cho node, thuộc tính nào là property, và cách chuyển đổi giữa đối tượng Java với dữ liệu đồ thị.

Ví dụ, ứng dụng quản lý người dùng có lớp `Person`. Khi lưu một đối tượng `Person`, SDN ánh xạ nó thành một node mang nhãn phù hợp, với các property tương ứng với những trường được ánh xạ:

~~~java
@Node("Person")
public class Person {

    @Id
    private String personId;

    private String fullName;
    private String email;
}
~~~

Một node được lưu có thể có hình dạng khái niệm như sau:

~~~cypher
(:Person {
    personId: "person-104",
    fullName: "Nguyen An",
    email: "an@example.com"
})
~~~

Ở đây:

- `Person` là nhãn node (label).
- `personId`, `fullName` và `email` là các property.
- `Person` trong Java là kiểu domain mà SDN dùng để chuyển đổi node thành đối tượng và ngược lại.

Nhãn giúp phân loại node trong đồ thị. Property lưu dữ liệu mô tả node. Một nhãn không phải là tên bảng, và một node có thể mang nhiều nhãn trong Neo4j. Relationship được dùng để biểu diễn liên kết giữa các node.

## 2. Vai trò của annotation @Node

`@Node` là annotation ở cấp lớp, dùng để đánh dấu một domain class được SDN ánh xạ thành node. Annotation này cũng cho phép chỉ định nhãn chính mà SDN sử dụng khi đọc và ghi node.

### Dùng nhãn mặc định

Nếu lớp được đánh dấu bằng `@Node` mà không chỉ định nhãn, SDN sử dụng tên lớp làm nhãn chính theo quy tắc mặc định:

~~~java
@Node
public class Person {
    @Id
    private String personId;

    private String fullName;
}
~~~

Với lớp trên, nhãn chính mặc định là `Person`. Tên lớp vì vậy có ảnh hưởng đến cách SDN nhận diện node nếu ta dựa vào quy tắc mặc định.

### Chỉ định nhãn tường minh

Có thể đặt nhãn rõ ràng bằng giá trị của annotation:

~~~java
@Node("Customer")
public class Person {
    @Id
    private String personId;

    private String fullName;
}
~~~

Lớp Java vẫn tên là `Person`, nhưng node được ánh xạ theo nhãn chính `Customer`. Cách này hữu ích khi tên lớp trong mã nguồn khác với thuật ngữ của mô hình đồ thị, hoặc khi muốn giữ nhãn ổn định trong lúc tái cấu trúc tên lớp.

Trong các phiên bản SDN có thuộc tính `primaryLabel`, có thể dùng tên thuộc tính này để diễn đạt rõ ý nghĩa của nhãn chính:

~~~java
@Node(primaryLabel = "Customer")
public class Person {
    @Id
    private String personId;
    private String fullName;
}
~~~

Hãy dùng cú pháp tương ứng với phiên bản Spring Data Neo4j của dự án. Dạng rút gọn `@Node("Customer")` là cách khai báo phổ biến và dễ đọc.

### Chọn nhãn có chủ đích

Nhãn là một phần của mô hình dữ liệu. Vì vậy, hãy chọn tên có ý nghĩa nghiệp vụ, thống nhất cách viết và tránh thay đổi tùy tiện. Neo4j phân biệt chữ hoa và chữ thường trong tên nhãn; `Person` và `person` là hai nhãn khác nhau.

Nếu để nhãn mặc định, việc đổi tên lớp có thể làm thay đổi nhãn mà ứng dụng mong đợi. Nếu nhãn là một phần của schema đồ thị được chia sẻ với các ứng dụng hoặc truy vấn Cypher khác, nên khai báo nhãn tường minh để giảm sự phụ thuộc vào tên lớp Java.

Không nên dùng cùng một nhãn chính cho nhiều domain class không cùng ý nghĩa chỉ để tái sử dụng tên. Khi nhiều lớp cùng ánh xạ vào một loại node, cần thiết kế rõ cách SDN phân biệt kiểu đích khi đọc dữ liệu và cách các truy vấn trả về node đó.

## 3. Định danh của node là một phần bắt buộc của entity mapping

Một domain entity cần có thuộc tính định danh được đánh dấu bằng `@Id`. SDN dùng định danh này để nhận diện entity trong các thao tác lưu, cập nhật và tải dữ liệu.

Ví dụ trên dùng mã nghiệp vụ do ứng dụng cấp:

~~~java
@Node("Person")
public class Person {

    @Id
    private String personId;

    private String fullName;

    public Person(String personId, String fullName) {
        this.personId = personId;
        this.fullName = fullName;
    }

    public String getPersonId() {
        return personId;
    }

    public String getFullName() {
        return fullName;
    }
}
~~~

Mã nghiệp vụ như `personId` có thể ổn định khi dữ liệu được trao đổi giữa các hệ thống, miễn là ứng dụng bảo đảm tính duy nhất và quản lý vòng đời của mã đó.

SDN cũng hỗ trợ định danh nội bộ do Neo4j tạo thông qua `@GeneratedValue`:

~~~java
@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String fullName;
}
~~~

Định danh nội bộ phù hợp khi ứng dụng chỉ cần một khóa kỹ thuật để làm việc với node trong cơ sở dữ liệu. Nếu cần tham chiếu bền vững từ hệ thống bên ngoài, mã nghiệp vụ do ứng dụng quản lý thường là lựa chọn dễ kiểm soát hơn. Không nên xem internal ID như mã nghiệp vụ lâu dài.

Điểm quan trọng là kiểu ID trong repository phải khớp với kiểu của trường `@Id`. Ví dụ, entity dùng `String personId` thì repository có thể khai báo `Neo4jRepository<Person, String>`.

## 4. Mapping context nhận diện domain class như thế nào?

SDN không dựa vào tên biến hoặc suy đoán tùy ý khi chuyển đổi đối tượng. Framework xây dựng metadata mô tả các lớp domain và thuộc tính được ánh xạ. Thành phần quản lý metadata này được gọi là mapping context; trong SDN, triển khai tương ứng là `Neo4jMappingContext`.

Có thể hình dung quá trình như sau:

1. Spring khởi tạo cấu hình Spring Data Neo4j và các repository được khai báo trong ứng dụng.
2. SDN nhận biết domain type mà repository quản lý, ví dụ `Person` trong `Neo4jRepository<Person, String>`.
3. Mapping context phân tích lớp domain và các metadata liên quan, bao gồm annotation `@Node`, trường định danh và các thuộc tính được ánh xạ.
4. Khi gặp thuộc tính tham chiếu đến domain type khác qua quan hệ, metadata của kiểu liên quan cũng được xem xét để mô tả đồ thị đối tượng.
5. Mapping metadata được sử dụng trong quá trình chuyển đổi giữa node/relationship của Neo4j và đối tượng Java.

Sơ đồ khái quát:

~~~text
PersonRepository<Person, String>
              |
              v
      Neo4jMappingContext
              |
              v
    Neo4jPersistentEntity<Person>
              |
       +------+------+
       |             |
       v             v
  @Node label     Persistent properties
       |             |
       +------+------+
              |
              v
     Neo4j entity converter
              |
              v
      Neo4j node / properties
~~~

Mapping context lưu thông tin về cấu trúc domain class, chẳng hạn:

- Lớp được ánh xạ thành node và nhãn chính của nó.
- Thuộc tính nào là định danh.
- Tên thuộc tính Java và thông tin ánh xạ tương ứng.
- Kiểu dữ liệu của từng thuộc tính.
- Thuộc tính nào mô tả liên kết với domain type khác.

Các metadata này được biểu diễn thông qua mô hình persistent entity và persistent property của Spring Data. Trong SDN, các kiểu tương ứng thường được gọi là `Neo4jPersistentEntity` và `Neo4jPersistentProperty`.

Mapping context là metadata phía ứng dụng. Nó không phải bản sao dữ liệu của Neo4j, không tự tạo node chỉ vì một lớp có annotation `@Node`, và cũng không phải một công cụ tự động quét mọi lớp Java trong toàn bộ project rồi lưu chúng vào database. Node được tạo hoặc cập nhật khi ứng dụng thực hiện thao tác ghi, chẳng hạn thông qua repository hoặc client phù hợp.

## 5. Domain class được đưa vào mapping context qua đâu?

Trong ứng dụng Spring Data Neo4j thông thường, repository là một đầu mối quan trọng để SDN biết domain type cần quản lý.

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository
        extends Neo4jRepository<Person, String> {
}
~~~

Khai báo trên cho SDN biết repository quản lý entity `Person` với kiểu định danh `String`. Trong quá trình cấu hình repository, SDN cần metadata của `Person` để thực hiện các thao tác như lưu entity, tìm theo ID và chuyển kết quả truy vấn thành đối tượng.

Nếu entity có thuộc tính liên kết đến một domain type khác, SDN cũng cần metadata của kiểu được tham chiếu để hiểu cấu trúc đồ thị. Ví dụ, một lớp `Person` có thể liên kết đến `Department`; khi đó cả hai kiểu cần được mô tả đúng trong mapping.

~~~java
@Node("Department")
public class Department {

    @Id
    private String departmentCode;

    private String name;
}

@Node("Person")
public class Person {

    @Id
    private String personId;

    private String fullName;

    @Relationship(type = "WORKS_IN")
    private Department department;
}
~~~

Ví dụ này cho thấy mapping context phải hiểu cả domain type gốc lẫn kiểu node được tham chiếu. Annotation `@Relationship` mô tả liên kết; annotation `@Node` trên `Department` mô tả kiểu node ở đầu còn lại. Chi tiết về ánh xạ relationship sẽ được học ở phần riêng.

Trong ứng dụng có cấu hình tùy chỉnh, tập entity ban đầu có thể được cung cấp cho mapping context qua cơ chế cấu hình của SDN. Phần lớn ứng dụng dùng Spring Boot và repository tiêu chuẩn không cần tự tạo mapping context bằng tay.

## 6. Từ metadata đến thao tác repository

Khi metadata đã sẵn sàng, repository có thể dùng nó để lưu và đọc entity:

~~~java
@Service
public class PersonService {

    private final PersonRepository people;

    public PersonService(PersonRepository people) {
        this.people = people;
    }

    public Person register(String id, String fullName) {
        Person person = new Person(id, fullName);
        return people.save(person);
    }

    public Optional<Person> find(String id) {
        return people.findById(id);
    }
}
~~~

Trong thao tác `save`, SDN dựa vào metadata của `Person` để biết nhãn node, thuộc tính định danh và các property cần ghi. Khi `findById` trả về kết quả, SDN dùng metadata tương ứng để tạo đối tượng Java từ node đọc được.

Có thể truy vấn trực tiếp bằng Cypher và trả về node có nhãn phù hợp:

~~~java
public interface PersonRepository
        extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (p:Person {personId: $id})
        RETURN p
        """)
    Optional<Person> findPersonNode(String id);
}
~~~

Vì truy vấn trả về node `p`, SDN có thể ánh xạ node đó thành `Person` dựa trên metadata và cấu trúc kết quả. Nếu truy vấn chỉ trả về một property như `p.fullName`, kết quả là một giá trị đơn hoặc projection phù hợp, không phải một entity `Person` đầy đủ.

Nhãn và tên property trong Cypher cần khớp với mô hình đồ thị mà entity mapping sử dụng. Ví dụ, truy vấn `MATCH (p:Person ...)` sẽ không tìm được node chỉ mang nhãn `Customer` nếu không có nhãn `Person` tương ứng.

## 7. Phân biệt ba khái niệm thường bị nhầm

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| Java domain class | Kiểu đối tượng trong mã nguồn | `Person` |
| Node label | Nhãn phân loại node trong Neo4j | `Person`, `Customer` |
| Mapping context | Metadata giúp SDN hiểu cách ánh xạ class và property | `Neo4jMappingContext` |

Một lớp Java có thể mang tên `Person` nhưng ánh xạ đến nhãn `Customer`. Mapping context lưu thông tin về mối liên hệ này để converter và repository thực hiện việc đọc, ghi. Nó không phải node và cũng không phải label.

Cũng cần phân biệt annotation với thao tác lưu dữ liệu:

- Thêm `@Node` giúp SDN nhận diện cách ánh xạ domain class.
- Khai báo repository giúp ứng dụng có điểm truy cập các thao tác trên entity.
- Gọi `save` hoặc thực thi thao tác ghi mới làm dữ liệu được tạo hoặc cập nhật trong Neo4j.

Chỉ thêm annotation không tự động ghi một node xuống cơ sở dữ liệu.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Repository không khởi tạo được do thiếu metadata entity | Domain type chưa được nhận diện hoặc khai báo chưa đúng | Kiểm tra generic type của repository và annotation `@Node` |
| Không tìm thấy node khi truy vấn | Nhãn trong Cypher khác nhãn mà entity mapping sử dụng | Kiểm tra nhãn thực tế trong Neo4j và giá trị của `@Node` |
| Lỗi khi lưu entity vì thiếu ID | Lớp entity chưa khai báo trường `@Id` hợp lệ | Kiểm tra trường định danh và kiểu ID của repository |
| Entity đọc về thiếu property | Property trong graph không trùng với tên ánh xạ hoặc truy vấn không trả về node đầy đủ | Kiểm tra property và hình dạng kết quả Cypher |
| Đổi tên lớp làm truy vấn cũ không còn khớp | Ứng dụng đang dựa vào nhãn mặc định theo tên lớp | Khai báo nhãn tường minh và lập kế hoạch điều chỉnh dữ liệu/truy vấn |
| Repository dùng sai kiểu ID | Kiểu ID generic không khớp trường `@Id` | Đối chiếu `Neo4jRepository<Person, String>` với trường ID thực tế |

Khi gặp lỗi mapping, hãy kiểm tra theo thứ tự: domain class có được đánh dấu đúng không, nhãn chính là gì, trường `@Id` có tồn tại không, repository dùng đúng domain type và ID type không, rồi mới kiểm tra dữ liệu thực tế và truy vấn Cypher.

## 9. Thực hành: ánh xạ lớp Person

Hãy tạo một entity đơn giản để quản lý người dùng:

~~~java
@Node("Person")
public class Person {

    @Id
    private String personId;

    private String fullName;
    private String email;

    public Person(String personId, String fullName, String email) {
        this.personId = personId;
        this.fullName = fullName;
        this.email = email;
    }

    public String getPersonId() {
        return personId;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Khai báo repository:

~~~java
public interface PersonRepository
        extends Neo4jRepository<Person, String> {
}
~~~

Sau khi ứng dụng được cấu hình kết nối Neo4j và repository được khởi tạo, thử lưu một entity:

~~~java
Person person = new Person(
    "person-104",
    "Nguyen An",
    "an@example.com"
);

people.save(person);
~~~

Kiểm tra node trong Neo4j bằng Cypher:

~~~cypher
MATCH (p:Person {personId: "person-104"})
RETURN p
~~~

Kết quả mong đợi là một node mang nhãn `Person` với ba property `personId`, `fullName` và `email`. Giá trị cụ thể phụ thuộc vào dữ liệu mà ứng dụng đã lưu.

Tự kiểm tra:

1. Nếu bỏ `@Node("Person")` và dùng `@Node`, nhãn chính mặc định của lớp `Person` là gì?
2. Nếu đổi thành `@Node("Customer")`, truy vấn `MATCH (p:Person)` còn khớp node chỉ mang nhãn `Customer` không?
3. Vì sao repository có kiểu `Neo4jRepository<Person, String>` trong ví dụ này?
4. Mapping context có tự tạo node ngay khi đọc annotation `@Node` không?

Đáp án cần nắm: nhãn mặc định theo tên lớp là `Person`; truy vấn theo nhãn `Person` không khớp node chỉ mang nhãn `Customer`; kiểu ID repository phải khớp trường `@Id`; mapping context quản lý metadata, còn node chỉ được ghi khi ứng dụng thực hiện thao tác lưu.

## Kết luận

`@Node` đánh dấu domain class được ánh xạ thành node và xác định nhãn chính mà SDN sử dụng. Tên lớp có thể trở thành nhãn mặc định, hoặc nhãn có thể được khai báo tường minh để mô hình Java và schema đồ thị giữ được sự ổn định.

Mapping context của Spring Data Neo4j quản lý metadata về entity và property để repository cùng bộ chuyển đổi có thể đọc, ghi dữ liệu đồ thị thành đối tượng Java. Khi xây dựng entity, hãy khai báo nhãn có chủ đích, định nghĩa trường `@Id` đúng kiểu, và bảo đảm repository, Cypher cùng dữ liệu Neo4j sử dụng cùng một mô hình nhãn và property.
