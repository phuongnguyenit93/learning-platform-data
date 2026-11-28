# Thao tác entity bằng ReactiveNeo4jTemplate

Khi ứng dụng dùng Spring WebFlux hoặc một luồng xử lý reactive khác, tầng truy cập Neo4j cần trả về publisher thay vì chặn luồng để đợi kết quả. **`ReactiveNeo4jTemplate`** cung cấp API làm việc với entity đã ánh xạ của Spring Data Neo4j, đồng thời giữ các thao tác đọc và ghi trong mô hình Reactor với `Mono` và `Flux`.

Template cho phép đọc entity theo ID, tải nhiều entity, chạy Cypher tùy chỉnh rồi ánh xạ kết quả về domain type, lưu một hoặc nhiều entity, đếm và xóa dữ liệu. Khi ghép các thao tác thành một pipeline, ứng dụng có thể duy trì xử lý bất đồng bộ từ service đến driver, kết hợp transaction reactive và kiểm soát cách tiêu thụ kết quả.

## 1. ReactiveNeo4jTemplate là gì?

`ReactiveNeo4jTemplate` nằm trong package `org.springframework.data.neo4j.core`. Đây là phiên bản reactive của `Neo4jTemplate`, với các thao tác dữ liệu trả về kiểu reactive của Project Reactor.

Template dùng metadata mapping của Spring Data Neo4j để chuyển node và relationship thành entity Java. Bạn không cần tự đọc từng record của Neo4j Driver khi mục tiêu là làm việc với domain object.

| API | Kiểu trả về | Ý nghĩa |
|---|---|---|
| `findById(id, Person.class)` | `Mono<Person>` | Đọc một entity theo ID; không có kết quả thì publisher hoàn tất rỗng |
| `findAll(Person.class)` | `Flux<Person>` | Đọc nhiều entity theo domain type |
| `findAllById(ids, Person.class)` | `Flux<Person>` | Đọc các entity theo danh sách ID |
| `findOne(cypher, params, Person.class)` | `Mono<Person>` | Chạy Cypher tùy chỉnh và ánh xạ một entity |
| `findAll(cypher, params, Person.class)` | `Flux<Person>` | Chạy Cypher tùy chỉnh và ánh xạ nhiều entity |
| `save(person)` | `Mono<Person>` | Lưu một entity cùng các quan hệ được ánh xạ |
| `saveAll(people)` | `Flux<Person>` | Lưu nhiều entity từ một `Iterable` |
| `count(Person.class)` | `Mono<Long>` | Đếm entity theo domain type |
| `existsById(id, Person.class)` | `Mono<Boolean>` | Kiểm tra entity có tồn tại |
| `deleteById(id, Person.class)` | `Mono<Void>` | Xóa entity theo ID và hoàn tất bằng tín hiệu rỗng |

`Mono<T>` biểu diễn tối đa một giá trị; `Flux<T>` biểu diễn từ không đến nhiều giá trị. Các phương thức template trả về publisher, vì vậy service có thể ghép chúng bằng các toán tử Reactor như `map`, `flatMap`, `switchIfEmpty`, `then` và `concatMap`.

## 2. Khai báo entity và cấu hình template

Giả sử ứng dụng quản lý người dùng và địa chỉ. Một `Person` có thể liên kết đến một `Address`:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;
import org.springframework.data.annotation.Version;

@Node("Person")
public class Person {

    @Id
    private String personId;

    @Version
    private Long version;

    private String name;

    @Relationship(type = "LIVES_AT", direction = Relationship.Direction.OUTGOING)
    private Address address;

    protected Person() {
    }

    public Person(String personId, String name, Address address) {
        this.personId = personId;
        this.name = name;
        this.address = address;
    }

    public String getPersonId() {
        return personId;
    }

    public String getName() {
        return name;
    }

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }

    public void rename(String name) {
        this.name = name;
    }
}
```

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.annotation.Version;

@Node("Address")
public class Address {

    @Id
    private String addressId;

    @Version
    private Long version;

    private String city;
    private String street;

    protected Address() {
    }

    public Address(String addressId, String city, String street) {
        this.addressId = addressId;
        this.city = city;
        this.street = street;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
```

Hai entity trên dùng ID do ứng dụng cấp. Với entity dùng assigned ID, `@Version` giúp Spring Data Neo4j phân biệt entity mới với entity đã lưu và phát hiện cập nhật cạnh tranh; field version kiểu `Long` để `null` trên object mới và được SDN quản lý khi lưu. Trong ứng dụng dùng ID sinh tự động, có thể chọn chiến lược ID tương ứng của domain model.

Spring Boot với starter reactive của Spring Data Neo4j thường cấu hình `ReactiveNeo4jTemplate`, reactive client và transaction manager theo các bean của ứng dụng. Có thể inject template trực tiếp vào service:

Luồng reactive cần dùng reactive Neo4j client/driver mà SDN cấu hình. Nếu gọi API imperative như `Neo4jTemplate` hoặc mở session blocking của Driver trong pipeline, thao tác đó có thể chặn thread và không tham gia reactive transaction context.

Các ví dụ service phía dưới sử dụng những kiểu Java và Reactor sau:

```java
import java.util.Collection;
import java.util.List;
import java.util.Map;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
```

```java
import org.springframework.data.neo4j.core.ReactiveNeo4jTemplate;
import org.springframework.stereotype.Service;

@Service
public class PersonService {

    private final ReactiveNeo4jTemplate template;

    public PersonService(ReactiveNeo4jTemplate template) {
        this.template = template;
    }
}
```

Nếu tự cấu hình hạ tầng hoặc dùng nhiều database, cần bảo đảm template và reactive transaction manager dùng cùng `Driver` và cùng database selection. Khi dùng `@EnableReactiveNeo4jRepositories`, có thể chỉ định bean template và transaction manager cho repository reactive qua các thuộc tính cấu hình tương ứng.

## 3. Đọc entity theo ID bằng findById

`findById` trả về `Mono<T>`. Nếu entity tồn tại, publisher phát ra một entity; nếu không tồn tại, publisher hoàn tất mà không phát giá trị.

```java
public Mono<Person> getPerson(String personId) {
    return template.findById(personId, Person.class);
}
```

Khi cần chuyển trường hợp không tìm thấy thành lỗi nghiệp vụ, dùng `switchIfEmpty`:

```java
public Mono<Person> getRequiredPerson(String personId) {
    return template.findById(personId, Person.class)
        .switchIfEmpty(Mono.error(
            new PersonNotFoundException(personId)
        ));
}
```

`switchIfEmpty` chỉ chạy khi nguồn không phát ra entity. `PersonNotFoundException` là exception do ứng dụng định nghĩa. Không cần kiểm tra `null` sau khi subscribe; trong Reactor, trạng thái không có kết quả được biểu diễn bằng publisher rỗng.

Để kiểm tra tồn tại mà không cần tải entity, dùng `existsById`:

```java
public Mono<Boolean> personExists(String personId) {
    return template.existsById(personId, Person.class);
}
```

Kết quả là `Mono<Boolean>`, vì vậy controller WebFlux hoặc service gọi tiếp có thể ghép trực tiếp với các publisher khác.

## 4. Đọc nhiều entity bằng findAll và findAllById

`findAll(Person.class)` trả về `Flux<Person>`:

```java
public Flux<Person> findAllPeople() {
    return template.findAll(Person.class);
}
```

Nếu chỉ cần đọc một nhóm ID đã biết:

```java
public Flux<Person> findPeople(Collection<String> personIds) {
    return template.findAllById(personIds, Person.class);
}
```

`Flux` phát từng entity khi có dữ liệu. Không cần chuyển toàn bộ kết quả thành `List` nếu tầng gọi có thể xử lý theo luồng. Ví dụ, WebFlux có thể ghi từng phần tử ra response stream khi endpoint trả về `Flux<Person>`.

`findAll` không tự chia kết quả thành các trang. Nếu tập dữ liệu lớn, hãy giới hạn bằng Cypher có `ORDER BY`, `SKIP` và `LIMIT`, hoặc dùng reactive repository với API phân trang phù hợp. Tránh tải toàn bộ node chỉ để hiển thị một trang nhỏ.

Nếu cần thêm điều kiện lọc trên domain type, có thể dùng fluent find API của template:

Fluent find API của template cũng có thể bắt đầu bằng `find(Person.class)`, nhận filter Cypher bằng `matching(String)` hoặc `matching(Statement)`, rồi thực thi bằng `all()`. Filter cần tham chiếu đúng symbolic name của node gốc trong query do SDN sinh. Với yêu cầu sort, giới hạn hoặc traversal nhiều relationship, hãy thể hiện rõ trong custom Cypher bằng `ORDER BY`, `SKIP`, `LIMIT` và phần `RETURN` cần thiết; ví dụ dùng `findAll(cypher, parameters, Person.class)` ở phần tiếp theo.

## 5. Lưu entity bằng save

`save(entity)` trả về `Mono<T>` chứa entity đã lưu. Thao tác ghi chỉ được thực thi khi publisher được subscribe.

```java
public Mono<Person> createPerson(Person person) {
    return template.save(person);
}
```

Nếu entity có relationship được ánh xạ, template lưu entity cùng các entity liên quan theo mapping. Ví dụ `Person` tham chiếu đến `Address`; khi lưu `Person`, SDN xử lý relationship `LIVES_AT` và node đích theo cấu hình mapping.

Có thể ghép nhiều bước bằng `flatMap`:

```java
public Mono<Person> renamePerson(String personId, String newName) {
    return template.findById(personId, Person.class)
        .switchIfEmpty(Mono.error(new PersonNotFoundException(personId)))
        .flatMap(person -> {
            person.rename(newName);
            return template.save(person);
        });
}
```

`flatMap` dùng khi hàm bên trong trả về publisher khác. Nếu chỉ biến đổi một object Java đồng bộ, dùng `map`; khi cần gọi tiếp thao tác database trả về `Mono` hoặc `Flux`, dùng `flatMap` hoặc `concatMap` tùy yêu cầu thứ tự.

Không gọi `subscribe()` bên trong service chỉ để kích hoạt thao tác lưu. Hãy trả publisher cho tầng gọi để lỗi, kết quả và transaction tiếp tục nằm trong cùng pipeline.

## 6. Lưu nhiều entity bằng saveAll

`saveAll` nhận một `Iterable` entity và trả về `Flux<T>`:

```java
public Flux<Person> createPeople(List<Person> people) {
    return template.saveAll(people);
}
```

Publisher phát các entity đã lưu. Nếu dữ liệu đầu vào đã nằm trong `List`, `saveAll` là cách gọn để gửi một nhóm entity.

Nếu dữ liệu đầu vào đã là `Flux<Person>`, API `saveAll(Iterable<T>)` không nhận trực tiếp publisher. Có thể nối từng phần tử với `save`:

```java
public Flux<Person> importPeople(Flux<Person> people) {
    return people.concatMap(template::save);
}
```

`concatMap` xử lý tuần tự và giữ thứ tự phát ra của nguồn. Nếu các bản ghi độc lập và nghiệp vụ cho phép ghi song song có giới hạn, có thể dùng `flatMap(template::save, concurrency)` với giá trị concurrency được cân nhắc theo tải database. Không nên mở concurrency không giới hạn cho một luồng nhập dữ liệu lớn.

## 7. Chạy custom Cypher và vẫn ánh xạ entity

Khi cần pattern hoặc điều kiện Cypher riêng nhưng kết quả vẫn là entity `Person`, dùng `findAll` hoặc `findOne` với query, map tham số và domain type.

```java
public Flux<Person> findPeopleInCity(String city) {
    String cypher = """
        MATCH (p:Person)-[r:LIVES_AT]->(a:Address)
        WHERE a.city = $city
        RETURN p, collect(r), collect(a)
        ORDER BY p.name
        """;

    Map<String, Object> parameters = Map.of("city", city);

    return template.findAll(cypher, parameters, Person.class);
}
```

Để tìm một entity:

```java
public Mono<Person> findPersonByName(String name) {
    String cypher = """
        MATCH (p:Person {name: $name})
        OPTIONAL MATCH (p)-[r:LIVES_AT]->(a:Address)
        RETURN p, collect(r), collect(a)
        LIMIT 1
        """;

    return template.findOne(
        cypher,
        Map.of("name", name),
        Person.class
    );
}
```

`findOne` trả `Mono<Person>` và cần query được thiết kế để chỉ trả tối đa một entity. `LIMIT 1` làm rõ giới hạn kết quả trong ví dụ; nếu cần phát hiện trường hợp có nhiều kết quả thay vì chọn tùy ý, hãy dùng truy vấn/kiểm tra riêng để bảo đảm tính duy nhất.

Tham số `$city` và `$name` được truyền qua map riêng, không nối chuỗi đầu vào vào Cypher. Khi truy vấn trả entity có relationship cần ánh xạ, hãy trả đủ node và relationship cần thiết cho graph mapping. Chỉ trả node gốc có thể không đủ nếu use case cần hydrate collection relationship.

## 8. Đếm và xóa entity

Đếm entity theo domain type:

```java
public Mono<Long> countPeople() {
    return template.count(Person.class);
}
```

Xóa entity theo ID:

```java
public Mono<Void> deletePerson(String personId) {
    return template.deleteById(personId, Person.class);
}
```

`deleteById` trả `Mono<Void>`, tức là publisher chỉ báo hiệu hoàn tất hoặc lỗi, không phát entity đã xóa. Nếu cần trả trạng thái cho API, có thể nối thêm `thenReturn`:

```java
public Mono<String> deletePersonAndRespond(String personId) {
    return template.deleteById(personId, Person.class)
        .thenReturn("Đã gửi yêu cầu xóa người dùng");
}
```

Lưu ý: xóa entity theo mapping có thể xóa các entity liên quan theo quy tắc xóa của SDN. Hãy hiểu rõ mô hình ownership và relationship trước khi gọi `deleteById`; không dùng nó thay cho thao tác xóa riêng một relationship nếu node đích cần được giữ lại.

## 9. Kết hợp nhiều thao tác trong một reactive pipeline

Một service thường cần đọc entity, kiểm tra điều kiện, lưu thay đổi rồi trả kết quả. Có thể biểu diễn tuần tự bằng `flatMap`:

```java
public Mono<Person> changeCity(String personId, String newCity) {
    return template.findById(personId, Person.class)
        .switchIfEmpty(Mono.error(new PersonNotFoundException(personId)))
        .flatMap(person -> {
            Address address = person.getAddress();
            if (address == null) {
                return Mono.error(new IllegalStateException(
                    "Người dùng chưa có địa chỉ"
                ));
            }

            address.setCity(newCity);
            return template.save(person);
        });
}
```

Toàn bộ pipeline được mô tả bằng publisher. Không có thao tác chờ kết quả đồng bộ giữa bước đọc và bước ghi. Khi có transaction reactive bao quanh, các thao tác database trong cùng pipeline có thể tham gia cùng transaction.

Ví dụ giả định `Person.address` đã được hydrate khi đọc entity. Nếu truy vấn hoặc độ sâu mapping chỉ tải node `Person` mà không tải relationship `LIVES_AT`, `getAddress()` có thể trả `null`. Hãy bảo đảm query/depth đọc đủ association cần cập nhật; lưu một entity graph chưa được tải đầy đủ có thể làm mất relationship ngoài ý muốn.

Nếu có nhiều nhánh độc lập, có thể kết hợp bằng `Mono.zip` hoặc `Mono.when`. Chỉ chạy song song khi các nhánh không phụ thuộc kết quả của nhau và transaction/database có thể xử lý concurrency đó. Với các bước phụ thuộc thứ tự hoặc cập nhật cùng một entity, giữ chuỗi tuần tự bằng `flatMap`/`concatMap` rõ ràng hơn.

## 10. Quản lý transaction reactive

Spring Data Neo4j cung cấp `ReactiveNeo4jTransactionManager`, triển khai `ReactiveTransactionManager` của Spring. Trong cấu hình Spring Boot reactive chuẩn, transaction manager phù hợp thường được auto-configure; khi tự cấu hình, cần tạo manager bằng cùng Neo4j `Driver` và database selection được dùng bởi reactive client/template.

Ví dụ cấu hình tường minh khi cần:

```java
import org.neo4j.driver.Driver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.transaction.ReactiveNeo4jTransactionManager;

@Configuration
public class ReactiveNeo4jTransactionConfiguration {

    @Bean
    ReactiveNeo4jTransactionManager reactiveTransactionManager(Driver driver) {
        return new ReactiveNeo4jTransactionManager(driver);
    }
}
```

Đặt `@Transactional` trên service method trả về `Mono` hoặc `Flux`:

```java
import org.springframework.data.neo4j.core.ReactiveNeo4jTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class PersonAddressService {

    private final ReactiveNeo4jTemplate template;

    public PersonAddressService(ReactiveNeo4jTemplate template) {
        this.template = template;
    }

    @Transactional
    public Mono<Person> movePerson(String personId, String addressId) {
        return template.findById(personId, Person.class)
            .switchIfEmpty(Mono.error(new PersonNotFoundException(personId)))
            .flatMap(person -> template.findById(addressId, Address.class)
                .switchIfEmpty(Mono.error(new AddressNotFoundException(addressId)))
                .flatMap(address -> {
                    person.setAddress(address);
                    return template.save(person);
                }));
    }
}
```

`PersonNotFoundException` và `AddressNotFoundException` là exception nghiệp vụ do ứng dụng định nghĩa. Hai lần đọc và lần lưu nằm trong cùng một publisher trả về từ phương thức transactional; khi publisher được subscribe, reactive transaction bao quanh chuỗi thao tác đó.

Spring nhận diện kiểu trả về reactive để dùng reactive transaction management. Transaction reactive lưu trạng thái trong Reactor Context, không dựa vào `ThreadLocal` như transaction imperative. Vì vậy, các thao tác cần tham gia cùng transaction phải nằm trong cùng reactive pipeline/context.

Không gọi `.subscribe()` bên trong phương thức transactional để chạy một nhánh tách rời. Subscription mới có thể không mang transaction context của pipeline hiện tại. Cũng không gọi `.block()` để chờ một thao tác khác; việc block làm mất lợi ích non-blocking và có thể gây deadlock hoặc cạn event-loop thread.

Nếu ứng dụng có nhiều transaction manager, chỉ định rõ reactive manager phù hợp bằng cấu hình `@Transactional(transactionManager = "...")` để tránh Spring chọn nhầm imperative manager.

## 11. Dùng TransactionalOperator khi cần transaction tường minh

Khi không muốn dùng annotation hoặc cần bọc một pipeline ở cấp chương trình, dùng `TransactionalOperator`:

Giả sử ứng dụng cần lưu một người dùng và một node audit riêng trong cùng một nghiệp vụ:

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("PersonAudit")
public class PersonAudit {

    @Id
    @GeneratedValue
    private Long id;

    private String personId;
    private String action;

    protected PersonAudit() {
    }

    public PersonAudit(String personId, String action) {
        this.personId = personId;
        this.action = action;
    }

    public String getPersonId() {
        return personId;
    }

    public String getAction() {
        return action;
    }
}
```

```java
import org.springframework.data.neo4j.core.ReactiveNeo4jTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Service
public class PersonRegistrationWorkflow {

    private final ReactiveNeo4jTemplate template;
    private final TransactionalOperator transactionalOperator;

    public PersonRegistrationWorkflow(
            ReactiveNeo4jTemplate template,
            ReactiveTransactionManager transactionManager) {
        this.template = template;
        this.transactionalOperator = TransactionalOperator.create(transactionManager);
    }

    public Mono<Person> createPerson(Person person) {
        Mono<Person> work = template.save(person)
            .flatMap(saved -> template.save(
                new PersonAudit(saved.getPersonId(), "CREATED")
            ).thenReturn(saved));

        return work.as(transactionalOperator::transactional);
    }
}
```

`TransactionalOperator` bọc toàn bộ publisher `work`. Khi publisher hoàn tất thành công, transaction commit; khi có lỗi, transaction rollback theo quy tắc reactive transaction. Cách viết `.as(transactionalOperator::transactional)` giữ nguyên pipeline và làm rõ phạm vi transaction.

Reactive transaction được bắt đầu khi có subscription. Nếu một consumer hủy subscription trước khi luồng transactional hoàn tất, transaction có thể rollback. Với `Flux` nhiều phần tử, cần cân nhắc các toán tử như `take`, `next` hoặc timeout vì chúng có thể phát tín hiệu cancel trước khi toàn bộ kết quả được tiêu thụ.

## 12. Publisher chỉ thực thi khi được subscribe

Một lỗi phổ biến khi mới dùng reactive template là nghĩ rằng gọi phương thức đã thực hiện truy vấn:

```java
Mono<Person> saved = template.save(person);
// Chưa có thao tác ghi nào được kích hoạt chỉ vì tạo publisher.
```

Publisher mô tả công việc sẽ thực hiện. Công việc được kích hoạt khi có subscriber. Trong ứng dụng WebFlux, framework subscribe vào publisher được controller trả về. Trong luồng messaging hoặc batch, framework tích hợp tương ứng cũng có thể quản lý subscription.

Ví dụ controller:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/people")
public class PersonController {

    private final PersonService service;

    public PersonController(PersonService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<Person> get(@PathVariable String id) {
        return service.getRequiredPerson(id);
    }

    @GetMapping
    public Flux<Person> list() {
        return service.findAllPeople();
    }
}
```

Controller trả publisher cho WebFlux xử lý. Không cần tự subscribe trong controller hoặc service.

## 13. Backpressure và tiêu thụ Flux

`Flux` tuân theo Reactive Streams, cho phép subscriber điều tiết lượng phần tử muốn nhận thông qua demand. Điều này hữu ích khi đọc nhiều entity, nhưng không có nghĩa mọi pipeline tự động sử dụng bộ nhớ hằng định.

Ví dụ xử lý từng người mà không gom toàn bộ kết quả:

```java
public Flux<String> listPersonNames() {
    return template.findAll(Person.class)
        .map(Person::getName);
}
```

Nếu gọi `collectList()`, toàn bộ kết quả được giữ trong bộ nhớ trước khi phát ra `Mono<List<Person>>`:

```java
public Mono<List<Person>> loadAllPeopleIntoMemory() {
    return template.findAll(Person.class).collectList();
}
```

Chỉ dùng `collectList()` khi kích thước kết quả được giới hạn và việc giữ toàn bộ danh sách là cần thiết. Với dữ liệu lớn, ưu tiên streaming, phân trang hoặc giới hạn số phần tử. Backpressure giúp phối hợp tốc độ producer/consumer nhưng không thay thế việc thiết kế truy vấn có giới hạn.

## 14. Phân biệt ReactiveNeo4jTemplate và ReactiveNeo4jRepository

Hai API cùng dùng reactive mapping của SDN nhưng phục vụ cách tổ chức code khác nhau:

| Tiêu chí | `ReactiveNeo4jRepository` | `ReactiveNeo4jTemplate` |
|---|---|---|
| Cách dùng | Repository interface theo domain | API template được inject vào service hoặc custom fragment |
| CRUD | Có sẵn qua reactive repository interfaces | Gọi trực tiếp qua các phương thức template |
| Truy vấn | Derived query, `@Query`, QBE và repository extensions | Cypher tùy chỉnh, statement Cypher-DSL và fluent operations |
| Tổ chức | Hợp đồng truy cập dữ liệu tách riêng | Linh hoạt khi phối hợp nhiều thao tác domain trong service |
| Kiểu kết quả | `Mono` và `Flux` | `Mono` và `Flux` |

Nếu ứng dụng đã có repository cho entity, không cần thay toàn bộ repository bằng template. Có thể giữ repository cho CRUD thông thường và inject template ở service khi cần một thao tác domain đặc biệt. Cả hai dùng chung mapping infrastructure nếu được cấu hình đúng.

## 15. Những lỗi cần tránh

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Truy vấn không chạy | Tạo `Mono`/`Flux` nhưng không có subscriber | Trả publisher cho WebFlux hoặc subscribe ở đúng application boundary. |
| Pipeline reactive bị chặn | Gọi `Neo4jTemplate` imperative hoặc blocking Driver trong luồng reactive | Dùng `ReactiveNeo4jTemplate`/reactive repository và reactive client xuyên suốt. |
| Ghi dữ liệu chạy ngoài transaction | Gọi `.subscribe()` tạo subscription riêng bên trong service | Ghép thao tác bằng `flatMap`/`then` trong cùng pipeline. |
| Event loop bị chặn | Dùng `.block()` hoặc gọi API imperative blocking | Dùng `ReactiveNeo4jTemplate` và trả publisher xuyên suốt. |
| `Mono` không có giá trị | Không tìm thấy entity | Dùng `switchIfEmpty` để xử lý not-found. |
| Dùng `saveAll` với `Flux` đầu vào | API nhận `Iterable`, không nhận Publisher | Dùng `concatMap(template::save)` hoặc chuẩn bị Iterable phù hợp. |
| Transaction không rollback như mong đợi | Pipeline bị tách subscription hoặc reactive manager không được chọn | Kiểm tra Reactor Context, transaction manager và vị trí subscribe. |
| Đọc nhiều dữ liệu gây tốn bộ nhớ | Gom `Flux` bằng `collectList()` không giới hạn | Streaming, pagination hoặc giới hạn kết quả. |
| Transaction bị rollback khi client ngắt luồng | Subscription bị cancel trước khi publisher hoàn tất | Thiết kế endpoint/consumer và toán tử giới hạn phù hợp với transaction scope. |
| Entity trả về thiếu relationship | Custom Cypher không trả đủ dữ liệu cần hydrate | Trả node và relationship cần thiết cho mapping. |

## 16. Kiểm thử publisher reactive

Khi kiểm thử `ReactiveNeo4jTemplate`, cần subscribe vào publisher để thao tác database thực sự chạy. `StepVerifier` trong `reactor-test` giúp xác nhận giá trị, publisher rỗng và lỗi mà không cần gọi `block()` trong test.

Ví dụ kiểm tra entity tồn tại và trường hợp không tìm thấy:

```java
import reactor.test.StepVerifier;

StepVerifier.create(template.findById("P-100", Person.class))
    .expectNextMatches(person -> "An".equals(person.getName()))
    .verifyComplete();

StepVerifier.create(template.findById("missing", Person.class))
    .verifyComplete();
```

Có thể kiểm tra thao tác ghi theo cùng cách:

```java
StepVerifier.create(template.save(person))
    .expectNextMatches(saved -> saved.getPersonId().equals(person.getPersonId()))
    .verifyComplete();
```

Với transaction, hãy tạo một kịch bản mà bước sau phát sinh lỗi rồi xác nhận các thay đổi trước đó đã rollback. Sau đó đọc lại database bằng một publisher mới để kiểm tra trạng thái đã commit thực tế. Test nên chạy trên Neo4j cô lập và không dùng chung dữ liệu giữa các trường hợp.

## 17. Quy trình áp dụng ReactiveNeo4jTemplate

1. Xác định entity và relationship cần thao tác; dùng mapping annotation của Spring Data Neo4j.
2. Inject `ReactiveNeo4jTemplate` vào service hoặc custom repository fragment.
3. Chọn `Mono` cho kết quả tối đa một giá trị và `Flux` cho nhiều giá trị.
4. Dùng `findById`, `findAll`, `findAllById`, `findOne` hoặc `findAll` với Cypher tùy nhu cầu.
5. Dùng `save`, `saveAll`, `count`, `existsById` và `deleteById` cho thao tác tương ứng.
6. Ghép các bước bằng toán tử Reactor; không gọi `block()` hoặc `subscribe()` bên trong service.
7. Đặt `@Transactional` trên phương thức trả reactive type hoặc dùng `TransactionalOperator`.
8. Bảo đảm mọi thao tác trong một transaction nằm trong cùng Reactor Context.
9. Kiểm soát backpressure, tránh gom dữ liệu lớn vào bộ nhớ và kiểm thử cả lỗi/cancel.

## 18. Ghi nhớ

`ReactiveNeo4jTemplate` cung cấp API domain-aware để thao tác entity Neo4j trong mô hình reactive. `findById` và `findOne` trả `Mono`; `findAll` và `findAllById` trả `Flux`; `save` trả `Mono`; `saveAll` trả `Flux`; `count` trả `Mono<Long>`; còn `deleteById` trả `Mono<Void>`. Custom Cypher vẫn có thể ánh xạ về entity nếu trả đủ dữ liệu cần cho mapping.

Publisher chỉ thực thi khi được subscribe, vì vậy hãy trả `Mono` hoặc `Flux` xuyên suốt service/controller thay vì tự subscribe hoặc block. Dùng `ReactiveNeo4jTransactionManager` với `@Transactional` reactive hoặc `TransactionalOperator`; transaction state nằm trong Reactor Context và các thao tác cần nguyên tử phải ở cùng pipeline. Khi đọc nhiều dữ liệu, tận dụng streaming và backpressure, đồng thời tránh `collectList()` cho tập kết quả không giới hạn.

## Tài liệu tham khảo

- [Spring Data Neo4j – ReactiveNeo4jTemplate API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/ReactiveNeo4jTemplate.html)
- [Spring Data Neo4j – ReactiveNeo4jOperations API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/ReactiveNeo4jOperations.html)
- [Spring Data Neo4j – ReactiveNeo4jTransactionManager API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/transaction/ReactiveNeo4jTransactionManager.html)
- [Spring Framework – Reactive Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
