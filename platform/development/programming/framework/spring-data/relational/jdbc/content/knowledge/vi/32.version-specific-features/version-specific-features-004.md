# Khóa ghép bằng @Id kết hợp @Embedded trong phiên bản hỗ trợ

Một số bảng không có một cột duy nhất đủ để định danh một hàng. Khóa chính của chúng gồm nhiều cột, ví dụ mã tổ chức kết hợp với số nhân viên, mã quốc gia kết hợp với mã bưu chính, hoặc mã đơn vị kết hợp với số chứng từ. Loại khóa này được gọi là **khóa ghép** (composite key/composite primary key).

Từ **Spring Data JDBC 4.0.0-M4**, Spring Data JDBC hỗ trợ ánh xạ khóa ghép thành một object Java. Tính năng này được phát hành chính thức trong dòng Spring Data Relational 4.0.0. Ứng dụng có thể đánh dấu property định danh bằng `@Id` và kết hợp `@Embedded` để ánh xạ các thành phần của object đó thành nhiều cột của cùng một bảng.

Ví dụ, Java biểu diễn ID nhân viên bằng `EmployeeId(organization, employeeNumber)`, trong khi database có hai cột `ID_ORGANIZATION` và `ID_EMPLOYEE_NUMBER` cùng tạo thành primary key.

Bài học trình bày phiên bản hỗ trợ, cách ánh xạ `@Id` với `@Embedded`, cấu trúc bảng, repository có kiểu ID là value object, cách Spring Data xác định entity mới/cũ, tạo ID cho aggregate mới và những lưu ý khi có khóa ngoại tham chiếu đến khóa ghép.

## 1. Khóa ghép là gì?

Khóa chính thông thường dùng một cột:

~~~sql
CREATE TABLE employee (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);
~~~

Mỗi hàng được xác định bằng một giá trị `id`. Tuy nhiên, một số mô hình dữ liệu dùng nhiều cột kết hợp để định danh duy nhất:

~~~sql
CREATE TABLE employee (
    organization VARCHAR(20) NOT NULL,
    employee_number BIGINT NOT NULL,
    name VARCHAR(100) NOT NULL,
    PRIMARY KEY (organization, employee_number)
);
~~~

Ở đây, `organization` riêng lẻ không duy nhất vì mỗi tổ chức có nhiều nhân viên. `employee_number` riêng lẻ cũng không nhất thiết duy nhất trên toàn hệ thống vì các tổ chức có thể đánh số nhân viên độc lập. Cặp giá trị mới là khóa chính.

Ví dụ:

| organization | employee_number | name |
| --- | ---: | --- |
| RND | 23 | Jens |
| SALES | 23 | Alex |
| RND | 24 | Linh |

Hai hàng có cùng số nhân viên 23 nhưng thuộc tổ chức khác nhau nên vẫn là hai hàng khác nhau.

### Khóa ghép trong Java

Thay vì truyền hai tham số rời rạc ở mọi nơi, ta gom các thành phần khóa vào một value object:

~~~java
public record EmployeeId(
    Organization organization,
    Long employeeNumber
) {
}
~~~

Entity dùng object đó làm ID:

~~~java
public class Employee {
    private EmployeeId id;
    private String name;
}
~~~

Spring Data JDBC 4.0 trở lên có thể ánh xạ các thuộc tính bên trong object ID thành các cột của bảng aggregate root.

## 2. Phiên bản nào hỗ trợ?

Composite ID được Spring Data JDBC và Spring Data R2DBC hỗ trợ bắt đầu từ **4.0.0-M4**. Tính năng này được đưa vào dòng phát hành ổn định **4.0.0**.

| Phiên bản Spring Data Relational | Hỗ trợ composite ID |
| --- | --- |
| 3.5.x và các dòng cũ hơn | Chưa có hỗ trợ mapping composite ID trực tiếp bằng tính năng này |
| 4.0.0-M4 | Có từ milestone này |
| 4.0.0 GA và các bản 4.0.x | Có |
| 4.1.x | Có |
| Các dòng mới hơn | Có, theo mapping reference hiện hành |

Nếu dự án đang dùng Spring Data Relational 3.5 hoặc thấp hơn, chỉ thêm annotation `@Embedded` vào một property không tạo ra composite primary key. Cần nâng cấp lên phiên bản hỗ trợ hoặc giữ một khóa thay thế đơn giản và xử lý khóa ghép bằng giải pháp riêng.

Khi nâng cấp, hãy dùng phiên bản Spring Data tương thích với Spring Boot hoặc release train mà dự án đang theo. Không nên nâng riêng một module Spring Data JDBC mà bỏ qua dependency management của ứng dụng.

## 3. @Id kết hợp @Embedded hoạt động như thế nào?

`@Id` đánh dấu property định danh của aggregate root. `@Embedded` cho Spring Data biết các thuộc tính của object được ánh xạ trực tiếp vào các cột của bảng chứa entity, thay vì tạo một bảng riêng.

Khi kết hợp hai annotation:

~~~java
@Id
@Embedded.Nullable
EmployeeId id;
~~~

Spring Data xem toàn bộ `EmployeeId` là một ID duy nhất ở cấp Java, nhưng trải các thành phần của nó thành nhiều cột ở cấp relational.

Ví dụ:

~~~java
public record EmployeeId(
    Organization organization,
    Long employeeNumber
) {
}
~~~

Các cột được tạo từ property của `EmployeeId`:

| Property Java | Cột database mặc định |
| --- | --- |
| `organization` | `ORGANIZATION` |
| `employeeNumber` | `EMPLOYEE_NUMBER` |

Khóa chính của bảng là cặp cột đó:

~~~sql
PRIMARY KEY (ORGANIZATION, EMPLOYEE_NUMBER)
~~~

`@Embedded` không tạo một bảng mới cho `EmployeeId`. Nó chỉ trải các property của value object vào cùng hàng với aggregate root.

### Có bắt buộc phải viết @Embedded không?

Khi ID là một kiểu phức hợp, Spring Data Relational 4.0 có thể tự xem các thuộc tính của ID như embedded trong những mapping đơn giản. Ví dụ `@Id EmployeeId id` đã có thể biểu diễn composite ID.

Viết rõ `@Embedded` hữu ích khi cần điều chỉnh cách ánh xạ, đặc biệt là thêm prefix cho tên cột hoặc chỉ định hành vi khi toàn bộ thành phần embedded đều null. Bài học dùng `@Id` kết hợp `@Embedded.Nullable` để thể hiện rõ cả vai trò định danh và quy tắc null của object ID.

## 4. Dùng @Embedded.Nullable và prefix cho cột khóa

Annotation `@Embedded` có thể nhận prefix để thêm vào tên các cột được ánh xạ từ object.

Ví dụ:

~~~java
@Id
@Embedded.Nullable(prefix = "id_")
EmployeeId id;
~~~

Với `EmployeeId` gồm `organization` và `employeeNumber`, tên cột sẽ có prefix:

| Property trong ID | Cột được ánh xạ |
| --- | --- |
| `organization` | `ID_ORGANIZATION` |
| `employeeNumber` | `ID_EMPLOYEE_NUMBER` |

DDL tương ứng:

~~~sql
CREATE TABLE employee (
    id_organization VARCHAR(20) NOT NULL,
    id_employee_number BIGINT NOT NULL,
    name VARCHAR(100) NOT NULL,
    PRIMARY KEY (id_organization, id_employee_number)
);
~~~

Tên cột thực tế còn phụ thuộc `NamingStrategy` và quy tắc identifier của database. Prefix giúp phân biệt cột thuộc ID với property thông thường có cùng tên hoặc cùng ý nghĩa.

### 4.1. Ý nghĩa của Nullable

`@Embedded.Nullable` là shortcut cho `@Embedded(onEmpty = USE_NULL)`. Khi Spring Data đọc hàng và tất cả cột của object embedded đều null, property embedded được khôi phục thành `null`.

Điều này hữu ích cho ID của aggregate mới: nếu ID chưa được gán, property ID có thể là null. Spring Data có thể dựa trên trạng thái đó để nhận diện entity mới.

Primary key của hàng đã lưu phải có đầy đủ giá trị. DDL nên khai báo các cột thành phần khóa là `NOT NULL`; database cũng không cho phép một primary key hợp lệ chứa giá trị null.

### 4.2. Phân biệt Nullable và Empty

`@Embedded.Empty` là shortcut cho `@Embedded(onEmpty = USE_EMPTY)`. Khi tất cả cột embedded đều null, Spring Data cố tạo một instance embedded với các giá trị property có thể null.

| Annotation | Khi mọi cột embedded đều null |
| --- | --- |
| `@Embedded.Nullable` | Property embedded trở thành `null` |
| `@Embedded.Empty` | Cố tạo object embedded với các property null |

Với ID ghép, `@Embedded.Nullable` thường phù hợp hơn vì một object ID rỗng không thể định danh một hàng hợp lệ. `@Embedded.Empty` có thể tạo một object ID mà mọi thành phần đều null, làm mờ ranh giới giữa ID chưa có và ID không hợp lệ.

## 5. Ví dụ đầy đủ: Employee có khóa ghép

Ta dùng enum `Organization` để biểu diễn đơn vị và record `EmployeeId` để gom hai thành phần của khóa.

~~~java
public enum Organization {
    RND,
    SALES,
    MARKETING
}
~~~

~~~java
public record EmployeeId(
    Organization organization,
    Long employeeNumber
) {
}
~~~

Aggregate root:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("employee")
public record Employee(

    @Id
    @Embedded.Nullable(prefix = "id_")
    EmployeeId id,

    String name,

    @Version
    Long version
) {
}
~~~

Trong ví dụ:

- `Employee` là aggregate root và được lưu vào bảng `employee`.
- `EmployeeId` là value object chứa các thành phần khóa.
- `@Id` đánh dấu toàn bộ object `EmployeeId` là identifier.
- `@Embedded.Nullable(prefix = "id_")` trải hai thành phần ID thành hai cột có prefix.
- `@Version` bật optimistic locking và hỗ trợ nhận diện entity mới khi version còn null.

Enum `Organization` được ánh xạ bằng tên enum; `employeeNumber` là kiểu số nguyên wrapper và được lưu bằng kiểu số tương ứng của database.

### Schema

~~~sql
CREATE TABLE employee (
    id_organization VARCHAR(20) NOT NULL,
    id_employee_number BIGINT NOT NULL,
    name VARCHAR(100) NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT pk_employee
        PRIMARY KEY (id_organization, id_employee_number)
);
~~~

Khi lưu nhân viên thuộc RND có số 23, hàng sẽ chứa:

| id_organization | id_employee_number | name | version |
| --- | ---: | --- | ---: |
| RND | 23 | Jens | 0 |

Cả `id_organization` và `id_employee_number` cùng tạo thành primary key.

## 6. Repository dùng composite ID làm generic type

Với repository, tham số generic thứ hai là kiểu của toàn bộ ID, tức `EmployeeId`:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface EmployeeRepository
        extends CrudRepository<Employee, EmployeeId> {
}
~~~

Không khai báo `Long` hoặc `String` nếu ID thực tế là object `EmployeeId`.

Các phương thức CRUD kế thừa nhận object ID:

~~~java
EmployeeId id = new EmployeeId(Organization.RND, 23L);

Optional<Employee> result = repository.findById(id);

boolean exists = repository.existsById(id);

repository.deleteById(id);
~~~

`findById` nhận một object composite ID. Spring Data phân rã object đó thành các giá trị cột để tạo điều kiện truy vấn theo toàn bộ primary key.

### Không truyền từng thành phần riêng lẻ

Không gọi repository bằng cách truyền hai đối số như:

~~~java
repository.findById(Organization.RND, 23L);
~~~

Hợp đồng repository vẫn nhận đúng một giá trị ID. Hãy tạo object:

~~~java
EmployeeId id = new EmployeeId(Organization.RND, 23L);
repository.findById(id);
~~~

Cách này giữ định nghĩa khóa ghép tập trung trong một kiểu Java và giúp các service dùng chung cùng một representation.

## 7. Cách Spring Data xác định entity mới hay đã tồn tại

Đây là điểm quan trọng khi dùng composite ID.

Spring Data xem **toàn bộ property được đánh dấu `@Id`** là identifier. Với composite ID, object `EmployeeId` chính là ID; Spring Data không kiểm tra từng thành phần riêng lẻ để quyết định entity mới hay cũ.

Theo chiến lược mặc định, Spring Data kiểm tra property ID:

- ID là `null` thì entity được xem là mới và `save` thực hiện insert.
- ID đã có giá trị thì entity thường được xem là đã tồn tại và `save` thực hiện update.
- Nếu entity có property `@Version`, Spring Data dùng version để nhận diện trạng thái mới: version null hoặc 0 với kiểu primitive biểu thị entity mới.

Vì composite ID thường phải được cấp đầy đủ trước khi lưu, trường hợp ID đã có giá trị nhưng entity vẫn là mới cần được xử lý rõ ràng.

### 7.1. Dùng @Version khi ID đã được gán trước

Trong ví dụ `Employee` có property `@Version Long version`. Khi tạo entity mới, đặt version là null:

~~~java
Employee employee = new Employee(
    new EmployeeId(Organization.RND, 23L),
    "Jens",
    null
);

Employee saved = repository.save(employee);
~~~

Vì version là null, Spring Data xem aggregate là mới và thực hiện insert dù composite ID đã có giá trị. Giá trị version ban đầu được lưu là 0; các lần update tiếp theo sẽ tăng version và kiểm tra version cũ để phát hiện cập nhật cạnh tranh.

`@Version` vừa hỗ trợ nhận diện trạng thái mới trong trường hợp này, vừa cung cấp optimistic locking cho các lần cập nhật sau.

### 7.2. Dùng JdbcAggregateTemplate.insert khi biết chắc entity mới

Nếu không muốn dùng optimistic locking, có thể yêu cầu insert tường minh qua `JdbcAggregateTemplate`:

~~~java
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EmployeeWriter {

    private final JdbcAggregateTemplate template;

    public EmployeeWriter(JdbcAggregateTemplate template) {
        this.template = template;
    }

    @Transactional
    public Employee create(Employee employee) {
        return template.insert(employee);
    }
}
~~~

`insert` bỏ qua bước kiểm tra entity mới/cũ và giả định aggregate là mới. Nếu khóa ghép đã tồn tại, database sẽ từ chối insert do vi phạm primary key. Chỉ dùng cách này khi caller biết chắc đây là bản ghi mới.

Ngoài ra, entity có thể triển khai `Persistable` và cung cấp logic `isNew()` riêng. Đây là lựa chọn khi ứng dụng muốn tự quản lý trạng thái mới/cũ.

## 8. Gán composite ID bằng BeforeConvertCallback

Khóa ghép thường không thể được tạo tự động bằng một cột auto-increment đơn giản vì nó gồm nhiều thành phần. Ứng dụng cần cấp giá trị cho từng thành phần, ví dụ từ mã tổ chức và bộ cấp số nhân viên.

Spring Data JDBC cung cấp `BeforeConvertCallback` để gán ID trước khi aggregate được chuyển thành các thao tác SQL.

Ví dụ dùng record bất biến:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.relational.core.mapping.event.BeforeConvertCallback;

@Configuration
public class EmployeeCallbackConfiguration {

    @Bean
    BeforeConvertCallback<Employee> employeeIdCallback(
            EmployeeNumberGenerator generator) {

        return employee -> {
            if (employee.id() != null) {
                return employee;
            }

            EmployeeId id = new EmployeeId(
                Organization.RND,
                generator.nextEmployeeNumber()
            );

            return new Employee(
                id,
                employee.name(),
                employee.version()
            );
        };
    }
}
~~~

Bộ cấp số có thể được định nghĩa bằng interface:

~~~java
public interface EmployeeNumberGenerator {
    Long nextEmployeeNumber();
}
~~~

Ứng dụng triển khai generator bằng sequence của database hoặc một dịch vụ cấp ID có bảo đảm duy nhất. Không nên dùng một `AtomicLong` trong bộ nhớ làm nguồn ID production nếu nhiều instance ứng dụng có thể chạy hoặc tiến trình có thể khởi động lại.

Luồng lưu với callback:

1. Ứng dụng tạo Employee mới với ID null và version null.
2. Spring Data nhận diện aggregate là mới dựa trên trạng thái ID/version.
3. `BeforeConvertCallback` tạo một `EmployeeId` và trả về record mới.
4. Spring Data ánh xạ hai thành phần ID thành hai cột.
5. Database insert hàng với composite primary key.
6. Repository trả về aggregate đã được lưu.

Callback phải trả về instance mới khi entity là record hoặc immutable object. Với entity mutable, có thể cập nhật property rồi trả về cùng instance.

### Không gán ID ở BeforeSaveCallback

`BeforeSaveCallback` chạy sau khi Spring Data đã tạo `AggregateChange`. Nếu ID quyết định cấu trúc thao tác insert/update, hãy gán nó ở `BeforeConvertCallback` để mapping nhận được giá trị đúng từ đầu.

## 9. Khóa ghép và khóa ngoại tham chiếu

Khi một bảng khác tham chiếu đến entity có composite ID, khóa ngoại cũng cần nhiều cột. Database phải tham chiếu toàn bộ các thành phần của primary key.

Ví dụ, một bảng `person` có ID gồm `firstName` và `lastName`:

~~~java
@Table("person")
public record Person(
    @Id
    @Embedded.Nullable
    Name id,

    String nickName
) {
}

public record Name(String firstName, String lastName) {
}
~~~

Bảng gốc:

~~~sql
CREATE TABLE person (
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    nick_name VARCHAR(100),
    PRIMARY KEY (first_name, last_name)
);
~~~

Nếu một entity khác thuộc aggregate tham chiếu đến `Person`, back-reference gồm nhiều cột. Theo quy tắc đặt tên mặc định được Spring Data mô tả, các cột này được ghép từ tên bảng của entity được tham chiếu và tên từng thành phần ID, ví dụ `PERSON_FIRST_NAME` và `PERSON_LAST_NAME`.

Bảng con minh họa:

~~~sql
CREATE TABLE person_address (
    id BIGINT PRIMARY KEY,
    person_first_name VARCHAR(100) NOT NULL,
    person_last_name VARCHAR(100) NOT NULL,
    city VARCHAR(100) NOT NULL,
    FOREIGN KEY (person_first_name, person_last_name)
        REFERENCES person(first_name, last_name)
);
~~~

Tên back-reference thực tế phụ thuộc table name, naming strategy và cấu hình mapping. Với composite ID, cần tạo đủ các cột khóa ngoại và khai báo constraint tham chiếu đủ tất cả thành phần khóa.

### Lưu ý về ranh giới aggregate

Spring Data JDBC xử lý quan hệ entity con trong aggregate root theo mô hình aggregate. Nếu đối tượng được tham chiếu thuộc một aggregate độc lập, hãy xem nó như một aggregate khác và biểu diễn quan hệ bằng ID/reference phù hợp. Không nên tạo object entity lồng nhau chỉ để mô phỏng khóa ngoại tới một aggregate khác.

## 10. Truy vấn và thao tác với composite ID

Khi dùng repository, các thao tác theo ID nhận value object:

~~~java
EmployeeId employeeId =
    new EmployeeId(Organization.SALES, 23L);

Optional<Employee> employee =
    employeeRepository.findById(employeeId);

boolean exists =
    employeeRepository.existsById(employeeId);

employeeRepository.deleteById(employeeId);
~~~

`findById` là phương thức dành riêng của repository để truy vấn theo identifier property, bất kể tên property trong entity là `id` hay `pk`. Kiểu tham số vẫn là kiểu composite ID.

Khi cần tìm theo một phần khóa hoặc kết hợp khóa với thuộc tính khác, có thể định nghĩa query method dựa trên property path hoặc dùng `@Query`. Cần kiểm tra tên đường dẫn property và cú pháp SQL theo phiên bản Spring Data JDBC đang dùng. Đừng thay kiểu ID generic của repository bằng một trong các thành phần khóa.

### Sử dụng JdbcAggregateTemplate

Template cũng nhận toàn bộ object ID:

~~~java
Employee employee = template.findById(
    new EmployeeId(Organization.RND, 23L),
    Employee.class
);
~~~

Các phương thức `findById`, `deleteById`, `existsById` và thao tác CRUD khác làm việc với ID như một giá trị duy nhất ở cấp Java. Spring Data chịu trách nhiệm phân rã nó thành nhiều cột khi tạo SQL.

## 11. Tính bất biến và equals/hashCode của ID

Composite ID là value object, vì vậy nên thiết kế nó bất biến. Java record là lựa chọn phù hợp:

~~~java
public record EmployeeId(
    Organization organization,
    Long employeeNumber
) {
}
~~~

Record tự cung cấp `equals` và `hashCode` dựa trên tất cả thành phần. Điều này giúp hai object ID có cùng giá trị thành phần được xem là cùng một khóa.

Nếu dùng class thông thường, cần triển khai `equals` và `hashCode` nhất quán dựa trên toàn bộ thành phần ID. Không đưa thuộc tính có thể thay đổi như tên hiển thị, địa chỉ hoặc trạng thái nhân viên vào ID.

Khóa ghép phải ổn định trong suốt vòng đời của hàng. Thay đổi một thành phần khóa đồng nghĩa thay đổi identity của hàng và có thể yêu cầu cập nhật các khóa ngoại liên quan. Trong đa số mô hình, nên xem ID là immutable và tạo một bản ghi mới nếu nghiệp vụ thực sự cần identity khác.

## 12. Composite ID khác với @Embedded thông thường

`@Embedded` có thể dùng cho một value object không phải ID. Cả hai trường hợp đều trải property của object thành cột trong cùng bảng, nhưng ý nghĩa khác nhau:

| Cách khai báo | Ý nghĩa |
| --- | --- |
| `@Embedded Address address` | Các cột của Address là thuộc tính thông thường của hàng |
| `@Id @Embedded Name id` | Các cột của Name cùng tạo thành primary key |
| `@Id Long id` | Một cột duy nhất là primary key |

Ví dụ một entity có khóa đơn và địa chỉ embedded:

~~~java
@Table("customer")
public record Customer(
    @Id Long id,
    @Embedded(prefix = "address_") Address address,
    String name
) {
}

public record Address(String city, String postalCode) {
}
~~~

Bảng có thể chứa `id`, `address_city`, `address_postal_code` và `name`. Chỉ cột `id` là primary key.

Trong composite ID, các cột thành phần của object được đánh dấu `@Id` mới là khóa chính. `@Embedded` quyết định cách trải object đó thành các cột.

## 13. Những giới hạn và lưu ý thiết kế

- **Phiên bản:** cần Spring Data Relational 4.0.0-M4 trở lên; bản ổn định bắt đầu từ 4.0.0.
- **Schema:** database phải có primary key gồm đúng các cột thành phần. Annotation không tự sửa schema hoặc tạo migration.
- **Giá trị khóa:** tất cả thành phần khóa phải có giá trị hợp lệ và không null khi insert.
- **Newness detection:** nếu ID đã được cấp trước, mặc định Spring Data có thể xem entity là đã tồn tại. Dùng `@Version`, `Persistable` hoặc `JdbcAggregateTemplate.insert` theo use case.
- **Sinh ID:** không thể trông chờ một cột auto-increment tự tạo toàn bộ tuple khóa ghép. Ứng dụng phải cấp các thành phần khóa bằng quy tắc phù hợp.
- **Kiểu thành phần:** nên dùng kiểu đơn giản được JDBC hỗ trợ, như String, số, enum hoặc kiểu có converter thích hợp.
- **Tên cột:** prefix và naming strategy ảnh hưởng đến tên cột. Hãy bảo đảm migration và mapping thống nhất.
- **Khóa ngoại:** entity tham chiếu đến composite ID cần nhiều cột back-reference và foreign key.
- **Đổi khóa:** thay đổi thành phần ID ảnh hưởng đến identity và quan hệ tham chiếu. Nên xem composite ID là immutable.

### Không nhầm với @EmbeddedId của JPA

Spring Data JDBC dùng `org.springframework.data.annotation.Id` và `org.springframework.data.relational.core.mapping.Embedded`. Không dùng annotation `jakarta.persistence.EmbeddedId` của JPA cho entity Spring Data JDBC.

Hai module có thể dùng cùng khái niệm khóa ghép nhưng API mapping không giống nhau. Hãy import annotation đúng package của Spring Data Relational.

## 14. Kiểm thử composite ID

Một integration test nên xác nhận Spring Data ghi cả hai cột khóa và có thể đọc lại aggregate bằng value object ID.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;

@DataJdbcTest
class EmployeeRepositoryTest {

    @Autowired
    EmployeeRepository employees;

    @Test
    void savesAndFindsEmployeeByCompositeId() {
        EmployeeId id =
            new EmployeeId(Organization.RND, 23L);

        Employee draft = new Employee(id, "Jens", null);

        Employee saved = employees.save(draft);

        assertThat(saved.id()).isEqualTo(id);
        assertThat(saved.version()).isZero();

        Employee loaded = employees.findById(id).orElseThrow();

        assertThat(loaded.id()).isEqualTo(id);
        assertThat(loaded.name()).isEqualTo("Jens");
    }
}
~~~

Ví dụ giả định test database đã chạy migration tạo bảng `employee` với primary key gồm `id_organization` và `id_employee_number`, đồng thời Spring context đã nạp repository. Vì entity có `@Version` null, Spring Data nhận diện đây là entity mới dù ID đã được gán trước.

Nên kiểm thử thêm:

1. Hai nhân viên cùng employee number nhưng khác organization có thể cùng tồn tại.
2. Hai hàng có cùng toàn bộ thành phần ID bị database từ chối.
3. `findById` hoạt động với object ID có đầy đủ thành phần.
4. Save entity mới có version null tạo insert.
5. Update entity đã load giữ nguyên ID và tăng version.
6. Callback gán ID cho entity mới tạo ra object ID đầy đủ trước khi persist.
7. Khóa ngoại tới aggregate có composite ID chứa đủ cột thành phần.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không ánh xạ được object ID thành cột | Dùng phiên bản Spring Data JDBC chưa hỗ trợ composite ID | Nâng lên Spring Data Relational 4.0 trở lên |
| Repository không nhận kiểu ID | Generic repository vẫn khai báo `Long` hoặc `String` | Dùng kiểu value object, ví dụ `EmployeeId` |
| Save entity mới lại chạy UPDATE | ID đã có giá trị và không có version/newness strategy | Dùng `@Version` null, `Persistable` hoặc `insert` tường minh |
| Insert báo duplicate primary key | Một hoặc nhiều thành phần ID đã tồn tại | Kiểm tra bộ cấp ID và constraint |
| Object ID đọc lại thành null | Các cột embedded đều null hoặc mapping prefix sai | Kiểm tra dữ liệu, `@Embedded.Nullable` và tên cột |
| Không tìm thấy hàng theo ID | Thành phần truyền vào không khớp đầy đủ khóa | Tạo ID object với tất cả thành phần chính xác |
| Cột khóa ngoại thiếu một thành phần | Schema chỉ tạo một cột tham chiếu | Tạo đủ các cột FK theo composite ID |
| Enum trong ID không map đúng | Giá trị lưu trữ khác tên enum hoặc converter chưa đăng ký | Kiểm tra converter và dữ liệu enum |
| Migration chạy được nhưng repository lỗi | Tên cột trong schema khác naming/prefix | Đồng bộ `@Embedded` prefix, `@Column` và migration |
| Dùng nhầm annotation JPA | Import `jakarta.persistence.EmbeddedId` hoặc `Embedded` | Dùng annotation Spring Data JDBC đúng package |

## 16. Quy trình triển khai khóa ghép

Khi một bảng cần composite primary key, hãy thực hiện theo trình tự:

1. Xác định chính xác những cột nào cùng tạo thành identity của hàng.
2. Xác nhận dự án dùng Spring Data Relational 4.0.0-M4 trở lên.
3. Tạo immutable value object chứa các thành phần ID.
4. Đánh dấu property ID bằng `@Id` và `@Embedded`; dùng prefix nếu cần.
5. Chọn `@Embedded.Nullable` khi null toàn bộ object biểu thị entity chưa có ID.
6. Tạo DDL với composite primary key và `NOT NULL` cho từng thành phần.
7. Khai báo repository generic với kiểu ID là value object.
8. Chọn chiến lược nhận diện entity mới: ID null, version null, Persistable hoặc insert tường minh.
9. Nếu cần, tạo ID qua `BeforeConvertCallback` hoặc dịch vụ cấp ID.
10. Cập nhật khóa ngoại tham chiếu thành nhiều cột.
11. Kiểm thử insert, find, update, delete và constraint trên database mục tiêu.

## 17. Bài tập tự thực hành

### Bài 1 — Tạo EmployeeId

Tạo record `EmployeeId` gồm `Organization` và `employeeNumber`. Giải thích vì sao từng thành phần riêng lẻ chưa đủ để định danh nhân viên trên toàn hệ thống.

### Bài 2 — Mapping bằng @Id và @Embedded

Tạo entity `Employee` có property ID được đánh dấu `@Id @Embedded.Nullable(prefix = "id_")`. Dự đoán tên cột và viết DDL với composite primary key.

### Bài 3 — Repository generic type

Tạo `EmployeeRepository extends CrudRepository<Employee, EmployeeId>`. Viết các thao tác tìm, kiểm tra tồn tại và xóa theo composite ID.

### Bài 4 — Newness detection

Tạo entity có composite ID được cấp trước và property `@Version` null. Lưu entity, quan sát insert và version ban đầu. Bỏ `@Version` trong một nhánh thử nghiệm để so sánh cách Spring Data nhận diện trạng thái mới.

### Bài 5 — BeforeConvertCallback

Viết callback tạo `EmployeeId` khi entity mới chưa có ID. Dùng bộ cấp số duy nhất và xác nhận callback trả về instance có ID đầy đủ.

### Bài 6 — Khóa ngoại ghép

Tạo bảng con tham chiếu đến `Person` có ID gồm firstName và lastName. Viết DDL chứa hai cột foreign key và constraint tham chiếu cả hai cột primary key.

### Bài 7 — Prefix

Thử cùng một ID object với và không có prefix. So sánh schema và SQL được Spring Data JDBC tạo.

### Bài 8 — Kiểm thử duplicate key

Lưu hai entity có cùng composite ID và xác nhận database từ chối bản ghi thứ hai. Sau đó đổi một thành phần khóa và xác nhận hai hàng có thể tồn tại.

## 18. Tài liệu tham khảo chính thức

- [Spring Data JDBC and R2DBC 4.0 will support Composite IDs](https://spring.io/blog/2025/07/22/spring-data-jdbc-composite-id/): công bố composite ID từ Spring Data 4.0.0-M4, ví dụ ID object, prefix và cách tạo ID cho entity mới.
- [Spring Data Relational — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): mục Embedded Ids, cách kết hợp `@Id` và `@Embedded`, quy tắc onEmpty, prefix và back-reference nhiều cột.
- [Spring Data Relational — Core Concepts](https://docs.spring.io/spring-data/relational/reference/repositories/core-concepts.html): generic type của repository và các chiến lược nhận diện entity mới bằng ID, version hoặc `Persistable`.
- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): cách `save`, `insert`, `update` hoạt động và vai trò của `@Version`.

Khóa ghép trong Spring Data JDBC từ phiên bản 4.0 cho phép mô hình hóa nhiều cột primary key thành một value object Java. Kết hợp `@Id` với `@Embedded.Nullable` giúp Spring Data ánh xạ toàn bộ object ID thành các cột khóa, trong khi repository vẫn làm việc với một kiểu ID duy nhất. Hãy đặc biệt chú ý chiến lược nhận diện entity mới khi ID đã được cấp trước, vì toàn bộ object ID được xem là identifier và trạng thái của nó ảnh hưởng trực tiếp đến việc Spring Data chọn insert hay update.
