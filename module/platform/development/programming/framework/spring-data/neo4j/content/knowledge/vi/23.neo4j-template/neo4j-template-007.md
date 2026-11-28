# Kết hợp template với converter, callback và giao dịch

`Neo4jTemplate` là API thao tác dữ liệu của Spring Data Neo4j dành cho những trường hợp cần gọi trực tiếp từ service hoặc custom repository fragment mà không muốn tự quản lý việc ánh xạ entity. Template dùng metadata domain để đọc, lưu và ánh xạ node cùng relationship. Khi kết hợp với custom converter, entity callback và transaction của Spring, ta có thể chuẩn hóa dữ liệu ở đúng thời điểm, xử lý kiểu Java riêng và gom nhiều thao tác đồ thị vào một đơn vị công việc nhất quán.

Bài học tập trung vào ba phần phối hợp: **converter** chuyển đổi kiểu dữ liệu giữa Java và Neo4j, **callback** can thiệp trước khi ghi hoặc sau khi đọc entity, và **transaction** xác định ranh giới commit/rollback cho các thao tác qua template.

## 1. Vai trò của Neo4jTemplate

Trong một ứng dụng Spring Data Neo4j, có thể truy cập dữ liệu qua repository hoặc `Neo4jTemplate`. Repository phù hợp với các thao tác theo hợp đồng CRUD và truy vấn đã đặt tên. Template phù hợp khi service cần gọi thao tác theo kiểu domain, kết hợp nhiều lần đọc/ghi hoặc chạy Cypher tùy chỉnh nhưng vẫn muốn SDN ánh xạ kết quả thành entity.

Một số thao tác imperative thường dùng:

| Thao tác | API minh họa | Mục đích |
|---|---|---|
| Đọc theo ID | `findById(id, Person.class)` | Trả về `Optional<Person>` |
| Đọc nhiều ID | `findAllById(ids, Person.class)` | Tải các entity theo danh sách định danh |
| Đọc theo Cypher | `findAll(query, parameters, Person.class)` | Chạy custom Cypher và ánh xạ kết quả thành `Person` |
| Lưu entity | `save(person)` | Lưu entity cùng các quan hệ được ánh xạ |
| Lưu nhiều entity | `saveAll(people)` | Lưu một tập entity |
| Đếm entity | `count(Person.class)` | Đếm số entity theo domain type |
| Xóa entity | `delete(person)` | Xóa entity theo quy tắc mapping của SDN |

Ví dụ sử dụng trong service:

```java
import org.springframework.data.neo4j.core.Neo4jTemplate;

@Service
public class PersonService {

    private final Neo4jTemplate neo4jTemplate;

    public PersonService(Neo4jTemplate neo4jTemplate) {
        this.neo4jTemplate = neo4jTemplate;
    }

    public Optional<Person> findPerson(String personId) {
        return neo4jTemplate.findById(personId, Person.class);
    }

    public Person save(Person person) {
        return neo4jTemplate.save(person);
    }

    public long countPeople() {
        return neo4jTemplate.count(Person.class);
    }
}
```

`Neo4jTemplate` biết kiểu domain `Person`, nên có thể dùng mapping metadata để chuyển dữ liệu từ Neo4j thành object Java và ngược lại. Nếu truy vấn trả về kết quả không phải entity hoặc cần ánh xạ từng cột theo ý muốn, `Neo4jClient` thường phù hợp hơn vì nó làm việc trực tiếp với record.

## 2. Chạy custom Cypher nhưng vẫn ánh xạ entity

Template hỗ trợ truy vấn Cypher dạng chuỗi hoặc statement Cypher-DSL, kèm map tham số. Ví dụ tìm những người đang hoạt động:

```java
public List<Person> findActivePeople(String city) {
    String query = """
        MATCH (p:Person)
        WHERE p.status = $status
          AND p.city = $city
        RETURN p
        """;

    Map<String, Object> parameters = Map.of(
        "status", "ACTIVE",
        "city", city
    );

    return neo4jTemplate.findAll(query, parameters, Person.class);
}
```

Các tham số được truyền riêng khỏi chuỗi Cypher. `RETURN p` trả node gốc để SDN ánh xạ thành `Person`. Nếu entity có relationship cần tải, truy vấn phải trả đủ node và relationship cần thiết cho mapping; trả về một phần đồ thị rồi dùng entity đó để ghi lại có thể làm mất những quan hệ chưa được tải.

Khi dùng template với Cypher-DSL, có thể xây dựng `Statement`, sau đó truyền statement cùng map tham số vào overload tương ứng của `findAll` hoặc `findOne`. Cách này hữu ích khi pattern được tạo động bằng code và muốn tránh nối chuỗi truy vấn.

## 3. Converter mặc định và khi nào cần converter riêng

Spring Data Neo4j đã hỗ trợ nhiều kiểu Java thông dụng như `String`, `Long`, `Integer`, `Double`, `Boolean`, `LocalDate`, `LocalDateTime`, `ZonedDateTime`, `UUID`, enum và các kiểu không gian được hỗ trợ. Trước khi viết converter mới, hãy kiểm tra kiểu hiện tại có được ánh xạ sẵn hay không.

Converter riêng cần thiết khi:

- Domain sử dụng value object riêng, ví dụ `EmailAddress`, `PhoneNumber` hoặc `Money`.
- Dữ liệu trong Neo4j có định dạng legacy cần chuyển sang kiểu Java mới.
- Một thuộc tính cần định dạng lưu trữ đặc thù, khác với cách chuyển đổi mặc định.
- Tham số của custom query dùng kiểu riêng và cần chuyển thành kiểu `Value` của Neo4j Java Driver.

Có hai phạm vi cấu hình thường gặp:

1. Converter toàn cục cho một kiểu domain, đăng ký trong `Neo4jConversions`.
2. Converter chỉ áp dụng cho một field cụ thể bằng `@ConvertWith`.

## 4. Đăng ký converter toàn cục qua Neo4jConversions

Giả sử domain dùng value object `EmailAddress`, nhưng Neo4j lưu email thành property chuỗi. Có thể triển khai `GenericConverter` để chuyển đổi hai chiều giữa `EmailAddress` và `Value` của Driver:

```java
public record EmailAddress(String value) {
    public EmailAddress {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Email không được để trống");
        }
    }
}
```

```java
import java.util.Set;

import org.neo4j.driver.Value;
import org.neo4j.driver.Values;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.GenericConverter;

public class EmailAddressConverter implements GenericConverter {

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Set.of(
            new ConvertiblePair(EmailAddress.class, Value.class),
            new ConvertiblePair(Value.class, EmailAddress.class)
        );
    }

    @Override
    public Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {

        if (source instanceof EmailAddress email) {
            return Values.value(email.value());
        }

        if (source instanceof Value value) {
            return value.isNull() ? null : new EmailAddress(value.asString());
        }

        throw new IllegalArgumentException("Không hỗ trợ chuyển đổi kiểu email này");
    }
}
```

Đăng ký converter với Spring:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.convert.Neo4jConversions;

@Configuration
public class Neo4jConversionConfiguration {

    @Bean
    Neo4jConversions neo4jConversions() {
        return new Neo4jConversions(List.of(new EmailAddressConverter()));
    }
}
```

Khi `EmailAddress` xuất hiện trong entity hoặc trong tham số truy vấn được hỗ trợ, SDN có thể dùng converter đã đăng ký để chuyển giữa kiểu domain và giá trị Neo4j. Với thuộc tính entity, cần có cả chiều ghi và chiều đọc. Nếu converter chỉ phục vụ một chiều ghi tham số cho custom query, có thể đăng ký cặp chuyển đổi một chiều phù hợp.

Khi dùng converter giữa các kiểu Java thông thường thay vì Driver `Value`, cần khai báo rõ hướng đọc/ghi bằng các annotation `@ReadingConverter` hoặc `@WritingConverter` nếu Spring không thể tự xác định chiều chuyển đổi. Tránh đăng ký một converter mơ hồ như `String` sang `Long` mà không xác định rõ hướng, vì nó có thể ảnh hưởng các trường chuỗi khác trong ứng dụng.

## 5. Converter chỉ áp dụng cho một thuộc tính bằng @ConvertWith

Nếu chỉ một field cần định dạng đặc biệt, không nên thay đổi cách ánh xạ toàn bộ thuộc tính cùng kiểu trong ứng dụng. `@ConvertWith` cho phép gắn `Neo4jPersistentPropertyConverter` trực tiếp lên field của node entity hoặc relationship properties.

Ví dụ, chỉ thuộc tính `contactEmail` của `Customer` dùng `EmailAddress`:

```java
import org.neo4j.driver.Value;
import org.neo4j.driver.Values;
import org.springframework.data.neo4j.core.convert.Neo4jPersistentPropertyConverter;

public class EmailAddressPropertyConverter
        implements Neo4jPersistentPropertyConverter<EmailAddress> {

    @Override
    public Value write(EmailAddress source) {
        return source == null ? Values.NULL : Values.value(source.value());
    }

    @Override
    public EmailAddress read(Value source) {
        if (source == null || source.isNull()) {
            return null;
        }
        return new EmailAddress(source.asString());
    }
}
```

Gắn converter vào field:

```java
import org.springframework.data.neo4j.core.convert.ConvertWith;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Customer")
public class Customer {

    @Id
    private String customerId;

    private String name;

    @ConvertWith(converter = EmailAddressPropertyConverter.class)
    private EmailAddress contactEmail;
}
```

Converter cần có constructor mặc định nếu được tạo trực tiếp qua `converter`. Nếu cần phụ thuộc Spring bean hoặc cấu hình theo property, có thể dùng `converterRef` để tham chiếu bean triển khai `Neo4jPersistentPropertyConverter`, hoặc cung cấp factory tương ứng.

`@ConvertWith` cũng có thể đặt trên field trong lớp `@RelationshipProperties`. Nhờ vậy, cùng một kiểu Java có thể được lưu theo quy tắc riêng tùy thuộc thuộc tính đang ánh xạ.

Lưu ý về tham số truy vấn: converter gắn riêng bằng `@ConvertWith` được áp dụng cho property và các tham số repository suy ra từ property đó, bao gồm derived query và Query by Example. Không nên mặc định converter riêng của field cũng tự áp dụng cho tham số của string-based `@Query`; với trường hợp này, dùng converter toàn cục hoặc chuyển giá trị sang kiểu mà truy vấn hỗ trợ trước khi bind.

## 6. Callback trước khi ghi: BeforeBindCallback

Entity callback cho phép can thiệp vào object tại một thời điểm xác định trong quá trình mapping. `BeforeBindCallback<T>` được gọi trước khi entity được chuyển thành record để lưu. Callback có thể trả lại chính object ban đầu hoặc một instance đã được sửa đổi.

Ví dụ chuẩn hóa tên người trước khi lưu:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.mapping.callback.BeforeBindCallback;

@Configuration
public class PersonCallbackConfiguration {

    @Bean
    BeforeBindCallback<Person> normalizePersonName() {
        return person -> {
            person.setName(person.getName().trim());
            return person;
        };
    }
}
```

Khi entity `Person` được lưu qua Spring Data Neo4j, callback chuẩn hóa khoảng trắng trước khi mapping tạo dữ liệu ghi. Vì callback chạy ở tầng mapping, nó có thể áp dụng nhất quán cho các thao tác lưu qua repository và template.

Nếu cần tạo một instance mới thay vì sửa object hiện tại, callback cũng có thể trả về instance mới:

```java
@Bean
BeforeBindCallback<Person> normalizePerson() {
    return person -> new Person(
        person.getPersonId(),
        person.getName().trim().replaceAll("\\s+", " ")
    );
}
```

Ví dụ này giả định `Person` có constructor nhận `personId` và `name`. Với entity có nhiều thuộc tính hoặc relationship, phải bảo toàn những trường cần ghi khi tạo instance mới.

Có thể đăng ký nhiều callback. Nếu cần thứ tự xác định, triển khai `Ordered` hoặc dùng `@Order`. Hãy giữ callback ngắn, có tính xác định và tránh gọi dịch vụ bên ngoài hoặc thực hiện tác vụ kéo dài trong giai đoạn bind.

## 7. Callback sau khi đọc: AfterConvertCallback

`AfterConvertCallback<T>` được gọi sau khi record Neo4j đã được chuyển thành entity và các association của entity đã được xử lý. Callback nhận ba đối số: instance đã ánh xạ, metadata entity và record nguồn.

Ví dụ bổ sung nhãn hiển thị chỉ tồn tại trong bộ nhớ:

```java
import org.springframework.data.annotation.Transient;
import org.springframework.data.neo4j.core.mapping.callback.AfterConvertCallback;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String personId;

    private String name;

    @Transient
    private String displayName;

    // getters and setters
}
```

```java
@Configuration
public class PersonReadCallbackConfiguration {

    @Bean
    AfterConvertCallback<Person> assignDisplayName() {
        return (person, entity, source) -> {
            person.setDisplayName(person.getName().toUpperCase(Locale.ROOT));
            return person;
        };
    }
}
```

`displayName` được tính sau khi đọc và đánh dấu `@Transient`, nên không trở thành property được lưu trong Neo4j. `AfterConvertCallback` không có reactive variant riêng và có thể dùng cho cả luồng imperative lẫn reactive.

Không dùng callback sau đọc để âm thầm sửa dữ liệu trong database. Nếu cần thay đổi dữ liệu đã lưu, hãy thực hiện một thao tác ghi có chủ đích trong service hoặc transaction riêng. Callback này nên phục vụ việc hoàn thiện object sau mapping, chẳng hạn tính trường dẫn xuất hoặc bổ sung dữ liệu không lưu trữ.

## 8. Callback, auditing và application event khác nhau thế nào?

Spring Data Neo4j hỗ trợ auditing và entity callback. Các annotation như `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy` và `@LastModifiedBy` có thể được xử lý thông qua cấu hình auditing. `BeforeBindCallback` cũng có thể dùng để chuẩn hóa hoặc bổ sung dữ liệu trước khi entity được ghi.

Không nên nhầm entity callback với Spring application event:

| Cơ chế | Thời điểm | Mục đích phù hợp |
|---|---|---|
| `BeforeBindCallback` | Trước khi entity được bind để ghi | Chuẩn hóa hoặc bổ sung field trước khi lưu |
| `AfterConvertCallback` | Sau khi record đã được ánh xạ thành entity | Hoàn thiện object sau khi đọc |
| Auditing | Trong luồng ghi entity | Tự động điền người tạo, thời điểm tạo và cập nhật |
| Application event | Khi một sự kiện trong ứng dụng được phát | Thông báo cho thành phần khác, tích hợp hoặc xử lý hậu kỳ |
| `DomainEvents` trên aggregate root | Theo vòng đời lưu aggregate | Công bố sự kiện miền gắn với thay đổi aggregate |

Application event có thể được cấu hình chạy bất đồng bộ, vì vậy không nên dựa vào listener bất đồng bộ để sửa entity trước khi ghi hoặc thực hiện công việc bắt buộc nằm trong transaction. Nếu cần sửa object trước khi persist, entity callback là lựa chọn phù hợp hơn.

## 9. Quản lý giao dịch bằng @Transactional

Neo4j yêu cầu thao tác ghi chạy trong transaction. Spring Data Neo4j tích hợp với transaction manager của Spring, vì vậy service có thể xác định một đơn vị công việc bằng `@Transactional`.

Ví dụ tạo một người và một địa chỉ trong cùng transaction:

```java
import org.springframework.data.neo4j.core.Neo4jTemplate;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RegistrationService {

    private final Neo4jTemplate neo4jTemplate;

    public RegistrationService(Neo4jTemplate neo4jTemplate) {
        this.neo4jTemplate = neo4jTemplate;
    }

    @Transactional
    public Person register(Person person, Address address) {
        neo4jTemplate.save(address);
        person.setAddress(address);
        return neo4jTemplate.save(person);
    }
}
```

Hai thao tác lưu tham gia cùng transaction do Spring quản lý. Nếu một lỗi khiến transaction bị rollback, các thay đổi trong đơn vị công việc đó được rollback cùng nhau. Điều này giúp tránh trạng thái chỉ lưu được địa chỉ nhưng chưa tạo được người dùng liên kết với địa chỉ.

Với luồng chỉ đọc, có thể đánh dấu:

```java
@Transactional(readOnly = true)
public Optional<Person> getPerson(String personId) {
    return neo4jTemplate.findById(personId, Person.class);
}
```

`readOnly = true` thể hiện ý định chỉ đọc và có thể giúp hệ thống Neo4j cluster định tuyến truy vấn phù hợp. Không dùng transaction read-only cho phương thức có thao tác ghi.

`@Transactional` được áp dụng thông qua Spring proxy. Vì vậy, lời gọi từ bên ngoài vào phương thức được quản lý mới kích hoạt transaction interceptor theo cách thông thường. Tự gọi một phương thức khác trong cùng class (self-invocation), hoặc đặt annotation trên phương thức private, không tạo ranh giới transaction như mong đợi.

## 10. Dùng TransactionTemplate khi cần điều khiển tường minh

Khi muốn chạy transaction trong một đoạn code nội bộ, private method hoặc trường hợp không thuận tiện dùng proxy, có thể dùng `TransactionTemplate`:

```java
import org.springframework.data.neo4j.core.Neo4jTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class ImportService {

    private final Neo4jTemplate neo4jTemplate;
    private final TransactionTemplate transactionTemplate;

    public ImportService(
            Neo4jTemplate neo4jTemplate,
            PlatformTransactionManager transactionManager) {
        this.neo4jTemplate = neo4jTemplate;
        this.transactionTemplate = new TransactionTemplate(transactionManager);
    }

    public Person importPerson(Person person, Address address) {
        return transactionTemplate.execute(status -> {
            neo4jTemplate.save(address);
            person.setAddress(address);
            return neo4jTemplate.save(person);
        });
    }
}
```

`execute` mở transaction, chạy callback và commit khi hoàn tất bình thường. Nếu exception thoát khỏi callback, transaction bị rollback theo quy tắc transaction manager. `TransactionTemplate` cũng cho phép cấu hình read-only, isolation hoặc propagation khi nghiệp vụ cần.

Nếu một service đã có `@Transactional`, các thao tác qua `Neo4jTemplate` và `Neo4jClient` có thể tham gia transaction hiện tại. Tránh tự mở session/transaction bằng Neo4j Java Driver rồi giả định nó tự tham gia transaction do Spring quản lý; giao dịch do Driver tự tạo là một phạm vi quản lý riêng.

## 11. Kết hợp converter, callback và transaction trong một luồng

Ba cơ chế có trách nhiệm khác nhau nhưng phối hợp trong cùng quy trình:

1. Service nhận dữ liệu đầu vào và kiểm tra quy tắc nghiệp vụ.
2. `@Transactional` hoặc `TransactionTemplate` mở ranh giới giao dịch.
3. Service gọi `Neo4jTemplate.save(entity)`.
4. `BeforeBindCallback` chuẩn hóa entity trước khi mapping.
5. Converter chuyển các value object thành kiểu Neo4j Driver `Value`.
6. SDN tạo câu lệnh ghi và gửi đến Neo4j trong transaction hiện tại.
7. Khi đọc lại, converter chuyển property thành kiểu Java và `AfterConvertCallback` hoàn thiện entity sau mapping.

Ví dụ, entity có `EmailAddress` dùng `@ConvertWith`, đồng thời tên được chuẩn hóa bằng `BeforeBindCallback`. Khi service lưu entity, cả hai cơ chế đều được áp dụng mà service không phải tự chuyển email thành chuỗi hoặc trim tên ở từng vị trí gọi repository/template.

Để luồng này dễ bảo trì, hãy giữ validation nghiệp vụ ở service/domain model, converter tập trung vào chuyển đổi biểu diễn, callback tập trung vào thao tác mapping xuyên suốt và transaction bao quanh đơn vị công việc.

## 12. Lựa chọn imperative hay reactive template

Spring Data Neo4j cung cấp cả `Neo4jTemplate` và `ReactiveNeo4jTemplate`:

| Imperative | Reactive |
|---|---|
| `Neo4jTemplate` | `ReactiveNeo4jTemplate` |
| Trả về entity, `Optional`, `List` hoặc kiểu đồng bộ | Trả về `Mono<T>`, `Flux<T>` hoặc publisher tương ứng |
| `BeforeBindCallback<T>` | `ReactiveBeforeBindCallback<T>` |
| `AfterConvertCallback<T>` dùng được cho cả hai luồng | `AfterConvertCallback<T>` dùng được cho cả hai luồng |
| `PlatformTransactionManager` và `TransactionTemplate` | Reactive transaction manager và `TransactionalOperator`/reactive transaction support |

Không gọi blocking `Neo4jTemplate` bên trong reactive pipeline. Hãy dùng `ReactiveNeo4jTemplate` cùng reactive transaction support để giữ luồng bất đồng bộ xuyên suốt. `AfterConvertCallback` là ngoại lệ có thể dùng chung vì callback này không có reactive variant riêng và được thiết kế để dùng ở cả hai loại workload.

## 13. Kiểm thử converter, callback và transaction

Integration test với Neo4j cô lập nên kiểm tra riêng từng lớp và sau đó kiểm tra cách chúng phối hợp:

1. Lưu entity có value object, đọc lại và xác nhận converter khôi phục đúng kiểu Java.
2. Kiểm tra converter xử lý null theo quy tắc đã định.
3. Lưu entity có chuỗi thừa khoảng trắng và xác nhận `BeforeBindCallback` chuẩn hóa trước khi ghi.
4. Đọc entity và xác nhận `AfterConvertCallback` tạo trường dẫn xuất đúng.
5. Kiểm tra callback được áp dụng cho cả thao tác lưu qua repository và `Neo4jTemplate`.
6. Tạo hai thao tác ghi trong một transaction, cố ý phát sinh lỗi ở thao tác thứ hai và xác nhận cả hai thay đổi được rollback.
7. Kiểm tra transaction read-only không thực hiện thao tác ghi.
8. Nếu có nhiều callback, xác nhận thứ tự bằng `@Order` hoặc `Ordered`.

Không chỉ kiểm tra object trong bộ nhớ. Hãy đọc lại property trong Neo4j bằng repository, template hoặc Cypher để xác nhận dữ liệu đã được lưu theo biểu diễn mong muốn.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Field value object không ánh xạ được | Chưa đăng ký converter hoặc thiếu chiều đọc/ghi | Đăng ký trong `Neo4jConversions` hoặc gắn `@ConvertWith` cho field. |
| Converter ảnh hưởng các field không liên quan | Đăng ký converter toàn cục quá rộng hoặc mơ hồ | Thu hẹp cặp kiểu và dùng qualifier đọc/ghi khi cần. |
| `BeforeBindCallback` không chạy theo thứ tự mong muốn | Có nhiều callback nhưng chưa cấu hình order | Dùng `@Order` hoặc triển khai `Ordered`. |
| Giá trị callback không được lưu | Callback không trả lại instance đã sửa hoặc sửa sai object | Trả về entity đã cập nhật; kiểm tra thứ tự callback. |
| Trường dẫn xuất hiện trong Neo4j dù chỉ dùng khi đọc | Quên đánh dấu trường dẫn xuất là `@Transient` | Đánh dấu `@Transient` hoặc tính ở DTO/service. |
| `@Transactional` không rollback nhiều thao tác | Gọi nội bộ qua self-invocation hoặc dùng transaction Driver độc lập | Đặt transaction ở public service method được proxy hoặc dùng `TransactionTemplate`. |
| Một phần dữ liệu vẫn được ghi khi thao tác sau lỗi | Các thao tác không cùng transaction | Bảo đảm cùng Spring transaction manager và không mở transaction độc lập. |
| Reactive pipeline bị chặn | Gọi `Neo4jTemplate` imperative trong luồng reactive | Dùng `ReactiveNeo4jTemplate` và reactive transaction support. |

## 15. Quy trình áp dụng trong dự án

1. Dùng `Neo4jTemplate` cho thao tác domain cần gọi từ service hoặc custom repository fragment.
2. Kiểm tra kiểu Java có được SDN hỗ trợ mặc định trước khi viết converter.
3. Chọn `Neo4jConversions` cho kiểu value object dùng chung, hoặc `@ConvertWith` cho field đặc thù.
4. Dùng `BeforeBindCallback` để chuẩn hóa entity trước mapping; dùng `AfterConvertCallback` để hoàn thiện object sau đọc.
5. Giữ callback ngắn, xác định và sắp xếp bằng `@Order` nếu có nhiều callback.
6. Đặt `@Transactional` ở ranh giới nghiệp vụ; dùng `TransactionTemplate` khi cần điều khiển chương trình hoặc không đi qua proxy.
7. Không trộn transaction do Driver tự quản lý với transaction Spring nếu kỳ vọng tính nguyên tử chung.
8. Kiểm thử cả dữ liệu trong Neo4j, object sau mapping và hành vi rollback.

## 16. Ghi nhớ

`Neo4jTemplate` cung cấp API domain-aware để đọc, lưu, đếm, xóa và chạy custom Cypher có ánh xạ về entity. Converter đảm nhiệm chuyển đổi biểu diễn dữ liệu: dùng `Neo4jConversions` cho kiểu dùng chung hoặc `@ConvertWith` cho một thuộc tính. `BeforeBindCallback` can thiệp trước khi entity được ghi, còn `AfterConvertCallback` chạy sau khi record và association đã được ánh xạ.

Transaction xác định các thao tác nào phải commit hoặc rollback cùng nhau. `@Transactional` phù hợp với ranh giới service được Spring quản lý; `TransactionTemplate` phù hợp khi cần điều khiển tường minh. Khi kết hợp đúng ba cơ chế này, tầng dữ liệu Neo4j có thể giữ mapping nhất quán, xử lý kiểu domain rõ ràng và thực hiện các thay đổi đồ thị trong phạm vi giao dịch đáng tin cậy.

## Tài liệu tham khảo

- [Spring Data Neo4j – Neo4jTemplate API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jTemplate.html)
- [Spring Data Neo4j – Conversions](https://docs.spring.io/spring-data/neo4j/reference/appendix/conversions.html)
- [Spring Data Neo4j – FAQ: Entity callbacks and transactions](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j – BeforeBindCallback API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/mapping/callback/BeforeBindCallback.html)
- [Spring Data Neo4j – AfterConvertCallback API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/mapping/callback/AfterConvertCallback.html)
