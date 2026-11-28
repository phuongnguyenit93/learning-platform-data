# Khai báo Neo4jRepository với entity và kiểu ID

Spring Data Neo4j (SDN) cung cấp **Neo4jRepository** để ứng dụng thao tác với node entity mà không phải tự viết các câu Cypher cho những thao tác CRUD thông dụng. Khi khai báo repository, bạn kế thừa interface này với hai kiểu tổng quát: kiểu entity mà repository quản lý và kiểu Java của thuộc tính định danh trong entity.

Khai báo đúng hai kiểu này giúp Spring Data tạo repository proxy phù hợp, kiểm tra kiểu dữ liệu khi gọi các phương thức CRUD và ánh xạ kết quả Neo4j về đúng entity. Kiểu ID phải tương ứng với trường được đánh dấu **@Id** trong lớp **@Node**. Nếu entity dùng ID được Neo4j sinh, repository thường khai báo kiểu ID như **Long**; nếu ứng dụng tự gán mã định danh dạng chuỗi, repository dùng **String**.

Sau bài học, bạn có thể:

- Giải thích ý nghĩa hai tham số kiểu của **Neo4jRepository<T, ID>**.
- Khai báo node entity có ID và repository tương ứng.
- Phân biệt ID nội bộ do Neo4j sinh với ID nghiệp vụ do ứng dụng quản lý.
- Sử dụng các phương thức CRUD kế thừa từ repository.
- Nhận biết các lỗi thường gặp do khai báo sai entity, kiểu ID hoặc phạm vi quét repository.

## 1. Neo4jRepository là gì?

**Neo4jRepository** là interface repository của Spring Data Neo4j, cung cấp các thao tác dữ liệu dựa trên entity. Bạn chỉ cần khai báo một interface kế thừa repository; Spring Data sẽ tạo implementation dạng proxy khi Spring context khởi tạo.

Cấu trúc tổng quát:

~~~java
public interface EntityRepository
        extends Neo4jRepository<Entity, IdType> {
}
~~~

Hai tham số kiểu có ý nghĩa:

| Tham số | Ý nghĩa | Ví dụ |
|---|---|---|
| **Entity** | Lớp node entity mà repository quản lý | **Person** |
| **IdType** | Kiểu Java của thuộc tính được đánh dấu **@Id** trong entity | **Long**, **String** |

Ví dụ:

~~~java
public interface PersonRepository
        extends Neo4jRepository<Person, Long> {
}
~~~

Repository này quản lý entity **Person** và nhận ID kiểu **Long**. Vì vậy, phương thức kế thừa như **findById** nhận một giá trị **Long**, còn **save** nhận và trả về một entity **Person**.

Không chọn kiểu ID theo kiểu dữ liệu của một thuộc tính bất kỳ. Nếu **Person** có **name** kiểu String và **id** kiểu Long, tham số thứ hai của **Neo4jRepository** vẫn phải là **Long**. Điều kiện quyết định là kiểu của property được đánh dấu **@Id**.

## 2. Khai báo node entity và trường ID

Để repository làm việc với node, lớp miền phải được SDN nhận diện như một node entity. Annotation **@Node** khai báo label; **@Id** đánh dấu property định danh; các trường còn lại thường được ánh xạ thành property của node hoặc relationship tùy annotation được sử dụng.

Ví dụ dùng ID do SDN yêu cầu Neo4j sinh:

~~~java
package com.acme.graph.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String personCode;
    private String name;

    @Version
    private Long version;

    public Person() {
    }

    public Person(String personCode, String name) {
        this.personCode = personCode;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getPersonCode() {
        return personCode;
    }

    public String getName() {
        return name;
    }

    public Long getVersion() {
        return version;
    }

    public void setPersonCode(String personCode) {
        this.personCode = personCode;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Trong ví dụ:

- **@Node("Person")** ánh xạ lớp Java thành node có label **Person**.
- **@Id** đánh dấu property mà SDN sử dụng làm định danh entity.
- **@GeneratedValue** yêu cầu SDN sử dụng cơ chế sinh ID được cấu hình; với khai báo mặc định và kiểu **Long**, SDN dùng ID nội bộ Neo4j.
- **personCode** là mã nghiệp vụ riêng của ứng dụng, không phải ID repository trong ví dụ này.
- **@Version** hỗ trợ optimistic locking và tham gia cơ chế nhận diện trạng thái mới của entity.

Repository tương ứng:

~~~java
package com.acme.graph.repository;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import com.acme.graph.domain.Person;

public interface PersonRepository
        extends Neo4jRepository<Person, Long> {
}
~~~

Hai kiểu phải khớp: entity có **id** kiểu **Long**, repository dùng **Neo4jRepository<Person, Long>**. Nếu thay kiểu ID trong entity, hãy xem lại khai báo repository và tất cả nơi gọi các phương thức nhận ID.

## 3. Chọn kiểu ID phù hợp

Kiểu ID của repository không phải lựa chọn tùy ý. Nó phản ánh cách ứng dụng định danh entity.

### ID do Neo4j sinh

Với **@Id @GeneratedValue**, ứng dụng không cần cung cấp ID khi tạo node mới. SDN nhận ID được sinh trong quá trình lưu và dùng nó để nhận diện entity trong những lần thao tác tiếp theo.

~~~java
Person person = new Person("P-100", "An");
Person saved = personRepository.save(person);

Long generatedId = saved.getId();
Person loaded = personRepository.findById(generatedId)
    .orElseThrow();
~~~

Giá trị **generatedId** lấy từ entity trả về bởi **save**. Hãy làm việc với kết quả repository trả về vì đó là đối tượng thể hiện trạng thái sau khi lưu, bao gồm ID và version do tầng persistence quản lý.

ID nội bộ Neo4j phù hợp để SDN định vị node trong phạm vi cơ sở dữ liệu. Không nên dùng ID nội bộ làm mã công khai lâu dài trong API hoặc làm khóa trao đổi giữa nhiều hệ thống. ID nội bộ không phải định danh nghiệp vụ ổn định và có thể được tái sử dụng sau khi node bị xóa.

### ID do ứng dụng tự gán

Nếu miền nghiệp vụ đã có một mã định danh ổn định, ứng dụng có thể dùng mã đó làm ID entity. Khi đó trường được đánh dấu **@Id** có kiểu **String** và không dùng **@GeneratedValue**:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Customer")
public class Customer {

    @Id
    private String customerCode;

    private String name;

    @Version
    private Long version;

    public Customer() {
    }

    public Customer(String customerCode, String name) {
        this.customerCode = customerCode;
        this.name = name;
    }

    public String getCustomerCode() {
        return customerCode;
    }

    public String getName() {
        return name;
    }

    public Long getVersion() {
        return version;
    }
}
~~~

Repository tương ứng phải dùng **String**:

~~~java
public interface CustomerRepository
        extends Neo4jRepository<Customer, String> {
}
~~~

Khi lưu, ứng dụng đã biết ID:

~~~java
Customer customer = new Customer("CUS-100", "Bình");
Customer saved = customerRepository.save(customer);

Customer loaded = customerRepository.findById("CUS-100")
    .orElseThrow();
~~~

Vì ID do ứng dụng cấp, hãy bảo đảm mã không rỗng, ổn định và duy nhất. Ví dụ có thêm trường **@Version** kiểu **Long**. Khi version còn **null**, Spring Data có thể nhận diện entity là mới dù ID đã có giá trị; sau khi lưu, version được quản lý để hỗ trợ optimistic locking. Nếu không dùng version, hãy cung cấp một cơ chế nhận diện trạng thái mới phù hợp, chẳng hạn triển khai **Persistable**. Có thể tạo uniqueness constraint trong Neo4j để cơ sở dữ liệu bảo vệ quy tắc mã không trùng:

~~~cypher
CREATE CONSTRAINT customer_code_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerCode IS UNIQUE
~~~

Nếu dùng ID nghiệp vụ làm **@Id**, hãy xem property đó là định danh entity. Không khai báo thêm một **@GeneratedValue** cho cùng property. Nếu muốn giữ cả ID nội bộ do Neo4j sinh và mã nghiệp vụ, chọn một trường làm **@Id**, còn trường kia chỉ là property thông thường có constraint riêng nếu cần.

### Bảng quyết định

| Thiết kế entity | Khai báo ID | Kiểu repository |
|---|---|---|
| Neo4j sinh ID mặc định | **@Id @GeneratedValue Long id** | **Neo4jRepository<Person, Long>** |
| Ứng dụng gán mã chuỗi | **@Id String code** | **Neo4jRepository<Customer, String>** |

Với một kiểu ID tùy chỉnh, hãy xác nhận kiểu đó được SDN và cấu hình conversion của ứng dụng hỗ trợ. Quy tắc cốt lõi vẫn là tham số **ID** của repository phải đúng kiểu của property **@Id**.

## 4. Các phương thức CRUD được kế thừa

Sau khi khai báo repository, bạn có thể dùng các phương thức CRUD cơ bản mà không cần viết implementation:

| Phương thức | Công dụng | Kiểu trả về hoặc tham số |
|---|---|---|
| **save(entity)** | Tạo mới hoặc cập nhật entity | Trả về entity đã lưu |
| **saveAll(entities)** | Lưu nhiều entity | Trả về tập hợp các entity đã lưu |
| **findById(id)** | Tìm entity theo ID | **Optional<T>** |
| **findAll()** | Đọc tất cả entity thuộc loại repository | Trả về tập hợp entity |
| **existsById(id)** | Kiểm tra entity có tồn tại | **boolean** |
| **count()** | Đếm entity | **long** |
| **deleteById(id)** | Xóa entity theo ID | **void** |
| **delete(entity)** | Xóa entity đã biết | **void** |
| **deleteAll()** | Xóa các entity mà repository quản lý | **void** |

Ví dụ sử dụng:

~~~java
Person person = new Person("P-200", "Chi");

// Lưu node mới.
Person saved = personRepository.save(person);

// Đọc theo ID.
Person found = personRepository.findById(saved.getId())
    .orElseThrow(() -> new IllegalArgumentException(
        "Không tìm thấy Person"
    ));

// Kiểm tra tồn tại.
boolean exists = personRepository.existsById(saved.getId());

// Đếm số entity.
long total = personRepository.count();

// Xóa theo ID.
personRepository.deleteById(saved.getId());
~~~

**findById** trả về **Optional** vì node có thể không tồn tại. Hãy xử lý trường hợp rỗng bằng **orElse**, **orElseThrow** hoặc kiểm tra **isPresent**; không giả định mọi ID truyền vào đều tồn tại.

**save** có thể tạo node mới hoặc cập nhật node đã có, tùy theo trạng thái và ID của entity. Với entity dùng ID do ứng dụng gán, hãy đặc biệt chú ý trạng thái entity mới/cũ và cơ chế versioning nếu ứng dụng sử dụng optimistic locking. Repository không tự biến một mã nghiệp vụ bất kỳ thành ID nếu trường đó không được đánh dấu **@Id**.

Các thao tác xóa có thể ảnh hưởng đến relationship gắn với node tùy mapping và chính sách xóa của SDN. Hãy hiểu cấu trúc graph và các ràng buộc nghiệp vụ trước khi gọi **delete** hoặc **deleteAll** trong dữ liệu thật.

## 5. Đăng ký repository trong Spring context

Khai báo interface chưa đủ nếu Spring không quét package chứa repository. Bạn không cần tự viết lớp implementation hoặc gắn **@Repository** lên từng interface; Spring Data tạo proxy cho các repository đã nhận diện. Trong cấu hình thủ công, bật repository scanning bằng **@EnableNeo4jRepositories**:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.repository.config.EnableNeo4jRepositories;

@Configuration
@EnableNeo4jRepositories(
    basePackages = "com.acme.graph.repository"
)
public class Neo4jRepositoryConfiguration {
}
~~~

Trong ứng dụng Spring Boot dùng starter SDN, auto-configuration thường tự tìm repository trong phạm vi package phù hợp với lớp ứng dụng chính. Nếu repository nằm ngoài phạm vi đó, bạn có thể khai báo package rõ ràng bằng cấu hình repository scanning thích hợp.

Phạm vi quét repository và phạm vi mapping entity là hai việc liên quan nhưng khác nhau. Spring phải nhận diện được interface repository để tạo proxy, đồng thời SDN phải biết entity mà repository quản lý để ánh xạ node. Với cấu hình dựa trên **AbstractNeo4jConfig**, phạm vi entity có thể được tùy chỉnh qua **getMappingBasePackages()**. Đừng nhầm package chứa interface repository với package chứa các lớp **@Node**.

Khi inject repository vào service, hãy dùng constructor injection:

~~~java
import org.springframework.stereotype.Service;

import com.acme.graph.repository.PersonRepository;

@Service
public class PersonService {

    private final PersonRepository personRepository;

    public PersonService(PersonRepository personRepository) {
        this.personRepository = personRepository;
    }
}
~~~

Nếu Spring báo không tìm thấy bean **PersonRepository**, hãy kiểm tra repository scanning, package thực tế, cấu hình Neo4j và việc khởi tạo Spring context.

## 6. Entity ID và relationship ID là hai khái niệm khác nhau

Một node entity có property **@Id** để repository định vị node. Một lớp **@RelationshipProperties** có thể dùng **@RelationshipId** để SDN nhận diện relationship cụ thể trong object graph. Hai annotation này không thay thế cho nhau.

Ví dụ:

~~~java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @Relationship(type = "RATED")
    private List<Rating> ratings;
}

@RelationshipProperties
public class Rating {

    @RelationshipId
    private Long id;

    private int score;

    @TargetNode
    private Movie movie;
}
~~~

Repository của **Person** dùng kiểu ID của node:

~~~java
public interface PersonRepository
        extends Neo4jRepository<Person, Long> {
}
~~~

Không dùng kiểu của **@RelationshipId** làm tham số thứ hai của **Neo4jRepository**. Repository ở đây quản lý node **Person**, vì vậy kiểu ID là kiểu trường **Person.id**. Relationship là thành phần của graph mà entity quản lý, không phải entity gốc của repository.

## 7. Những lỗi thường gặp

**Khai báo sai kiểu ID.** Entity có **@Id Long id** nhưng repository kế thừa **Neo4jRepository<Person, String>**. Hai kiểu phải khớp chính xác.

**Đánh dấu nhầm property làm ID.** Một trường như **name** hoặc **email** chỉ nên là ID khi miền nghiệp vụ xác định nó là định danh ổn định và duy nhất. Nếu không, dùng ID riêng và giữ các giá trị đó làm property.

**Dùng ID nội bộ như mã nghiệp vụ.** ID sinh từ Neo4j phục vụ mapping. Nếu cần mã ổn định để trao đổi với hệ thống ngoài, hãy lưu một business key riêng.

**Không xử lý Optional từ findById.** Node có thể không tồn tại. Hãy xác định rõ hành vi của service khi không tìm thấy entity.

**Quên bật repository scanning.** Interface có thể viết đúng nhưng Spring không tạo bean vì package không nằm trong phạm vi quét.

**Nhầm repository scanning với entity mapping.** Spring tìm thấy repository nhưng SDN không ánh xạ được entity do package mapping hoặc annotation chưa đúng.

**Bỏ qua entity trả về từ save.** Hãy dùng đối tượng trả về, đặc biệt khi ID hoặc version được sinh/cập nhật trong quá trình lưu.

**Dùng deleteAll không đúng phạm vi.** Phương thức này có thể xóa lượng dữ liệu lớn. Chỉ dùng khi yêu cầu nghiệp vụ thực sự là xóa toàn bộ dữ liệu thuộc repository.

## 8. Tự kiểm tra

1. Hai tham số kiểu của **Neo4jRepository<T, ID>** biểu thị điều gì?
2. Nếu entity có trường **@Id Long id**, repository phải khai báo kiểu nào?
3. Khi nào nên dùng ID do Neo4j sinh và khi nào nên dùng ID nghiệp vụ dạng **String**?
4. Vì sao **findById** trả về **Optional<T>**?
5. **@Id** của node entity khác **@RelationshipId** của relationship properties như thế nào?
6. Vì sao repository interface cần được Spring quét trong quá trình khởi tạo context?

**Bài tập thực hành:** Tạo entity **Book** có label **Book**, ID nội bộ kiểu **Long** do Neo4j sinh và mã ISBN kiểu **String**. Khai báo **BookRepository extends Neo4jRepository<Book, Long>**. Viết service có các thao tác tạo sách, tìm theo ID, kiểm tra tồn tại và xóa theo ID. Sau đó thay thiết kế để dùng ISBN làm ID do ứng dụng cấp; cập nhật entity, kiểu repository và uniqueness constraint tương ứng. So sánh hai cách định danh và giải thích cách nào phù hợp hơn với yêu cầu của ứng dụng.

## Tài liệu tham khảo

- [Spring Data Neo4j Reference — Repository support](https://docs.spring.io/spring-data/neo4j/reference/repositories.html)
- [Spring Data Commons — CrudRepository API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html)
- [Neo4j Cypher Manual — Constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/)
