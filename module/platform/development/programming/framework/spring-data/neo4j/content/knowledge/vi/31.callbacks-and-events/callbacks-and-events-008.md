# Giới hạn callback khi ghi Cypher trực tiếp hoặc dùng driver

Spring Data Neo4j (SDN) cung cấp entity callback để bổ sung dữ liệu trước khi lưu hoặc điều chỉnh object sau khi đọc. Ví dụ, `BeforeBindCallback` có thể tự điền `updatedAt`, `updatedBy` trước khi SDN chuyển entity thành map tham số cho Cypher. Cơ chế này rất hữu ích khi ứng dụng lưu entity qua repository hoặc `Neo4jTemplate`.

Tuy nhiên, callback là một điểm móc trong quy trình mapping entity của SDN, không phải trigger chạy ở database cho mọi thay đổi graph. Khi ghi bằng Cypher tùy chỉnh qua `@Query`, `Neo4jClient` hoặc Neo4j Java Driver, câu lệnh được thực thi trực tiếp theo nội dung đã khai báo. Không nên dựa vào `BeforeBindCallback` để tự bổ sung audit field, tạo domain event hoặc thực hiện logic nghiệp vụ cho những lệnh ghi đó. Muốn bảo đảm hành vi nhất quán, hãy đưa logic vào service/query dùng chung hoặc ghi rõ dữ liệu cần thiết trong Cypher.

## 1. Callback nằm ở đâu trong vòng đời SDN?

Entity callback được gọi tại một điểm cụ thể trong quy trình làm việc với object Java. Callback không quan sát mọi câu lệnh Bolt hay mọi transaction được gửi tới Neo4j.

| Callback | Thời điểm | Mục đích |
|---|---|---|
| `BeforeBindCallback<T>` | Trước khi entity được chuyển thành map để bind vào câu lệnh ghi | Sửa hoặc bổ sung dữ liệu trước khi lưu |
| `ReactiveBeforeBindCallback<T>` | Cùng điểm trước bind trong luồng reactive | Thực hiện logic bất đồng bộ và trả `Publisher<T>` |
| `AfterConvertCallback<T>` | Sau khi record đã được chuyển thành entity và các association đã được xử lý | Điều chỉnh object vừa hydrate |

`BeforeBindCallback` và `ReactiveBeforeBindCallback` được hỗ trợ từ SDN 6.0.2. `AfterConvertCallback` được bổ sung từ SDN 6.3.0 và không có biến thể reactive riêng; callback này có thể dùng cho cả luồng imperative lẫn reactive.

Một callback chỉ chạy khi luồng xử lý SDN đi qua đúng điểm lifecycle tương ứng. Ví dụ, `BeforeBindCallback` chạy trước khi SDN chuyển domain object thành map record. Một câu lệnh Cypher viết sẵn trong `@Query` không cần SDN phân rã một entity để tạo câu lệnh ghi, nên không thể xem `@Query` là một lời gọi `save(entity)` có thêm cú pháp Cypher.

## 2. Ví dụ callback trước khi bind entity

Giả sử `Person` có các trường kiểm toán:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.time.Instant;

import org.springframework.data.domain.AfterDomainEventPublication;
import org.springframework.data.domain.DomainEvents;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {
    @Id
    private String code;

    private String name;
    private Instant createdAt;
    private Instant updatedAt;
    private final List<Object> domainEvents = new ArrayList<>();

    protected Person() {
    }

    public String getCode() { return code; }
    public String getName() { return name; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }

    public void setUpdatedAt(Instant updatedAt) {
        this.updatedAt = updatedAt;
    }

    public void rename(String newName, String actor) {
        this.name = newName;
        domainEvents.add(new PersonRenamedEvent(code, newName, actor));
    }

    @DomainEvents
    Collection<Object> domainEvents() {
        return domainEvents;
    }

    @AfterDomainEventPublication
    void clearDomainEvents() {
        domainEvents.clear();
    }
}
```

Đăng ký callback như một Spring bean:

```java
import java.time.Clock;
import java.time.Instant;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.mapping.callback.BeforeBindCallback;

@Configuration
public class PersonCallbackConfiguration {

    @Bean
    BeforeBindCallback<Person> updateTimestamp(Clock clock) {
        return person -> {
            person.setUpdatedAt(Instant.now(clock));
            return person;
        };
    }
}
```

Với bean `Clock` đã được cấu hình, mỗi lần SDN lưu một `Person` qua entity persistence path, callback có thể cập nhật `updatedAt` trước khi entity được chuyển thành map và bind vào Cypher. Callback có thể trả về cùng instance đã sửa hoặc một instance mới, điều này cũng hỗ trợ entity immutable.

Nếu có nhiều callback cùng loại, SDN gọi chúng theo thứ tự được xác định bởi `Ordered` hoặc `@Order`. Hãy làm cho callback có thể dự đoán được; tránh để thứ tự không rõ ràng quyết định giá trị cuối cùng của một field.

## 3. Callback reactive có hợp đồng riêng

Repository reactive cần callback reactive tương ứng. Không triển khai callback imperative rồi kỳ vọng reactive repository sẽ tự gọi nó.

```java
import java.time.Clock;
import java.time.Instant;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.mapping.callback.ReactiveBeforeBindCallback;

import reactor.core.publisher.Mono;

@Configuration
public class ReactivePersonCallbackConfiguration {

    @Bean
    ReactiveBeforeBindCallback<Person> reactiveUpdateTimestamp(Clock clock) {
        return person -> Mono.fromSupplier(() -> {
            person.setUpdatedAt(Instant.now(clock));
            return person;
        });
    }
}
```

`ReactiveBeforeBindCallback` trả về `Publisher<T>`, nên có thể kết hợp dữ liệu bất đồng bộ vào luồng reactive. Không gọi `.block()` bên trong callback; việc chặn thread có thể làm hỏng lợi ích của reactive pipeline và gây nghẽn event loop.

Không có `ReactiveAfterConvertCallback` riêng trong SDN hiện hành. `AfterConvertCallback` dùng chung cho cả hai loại workload. Callback sau convert chỉ sửa object sau khi đọc; nó không ghi lại thay đổi đó vào Neo4j.

## 4. Auditing cũng dựa trên entity persistence path

SDN hỗ trợ các annotation auditing của Spring Data:

- `@CreatedBy` và `@CreatedDate` cho thông tin tạo mới.
- `@LastModifiedBy` và `@LastModifiedDate` cho thông tin cập nhật.

Ví dụ:

```java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;

public class AuditableFields {
    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedBy
    private String updatedBy;

    @LastModifiedDate
    private Instant updatedAt;
}
```

`AuditableFields` chỉ minh họa các annotation; trong ứng dụng thật, đưa những field này vào entity được đánh dấu `@Node`. Bật auditing bằng `@EnableNeo4jAuditing` và cung cấp `AuditorAware<T>` cùng `DateTimeProvider` khi cần nguồn người dùng hoặc thời gian tùy chỉnh. Với reactive, dùng `ReactiveAuditorAware<T>`.

Auditing được triển khai thông qua các callback trước bind. Vì vậy, nó áp dụng cho thao tác lưu entity do SDN quản lý. Nếu câu lệnh `@Query` tự chạy `SET p.updatedAt = ...`, SDN không tự chèn `@LastModifiedDate` vào Cypher đó. Tương tự, raw Driver không tự gọi auditing callback chỉ vì node được cập nhật.

## 5. @Query ghi trực tiếp không phải repository.save

`@Query` cho phép khai báo Cypher tùy chỉnh ngay trên repository. Repository proxy thực thi câu lệnh đã khai báo và bind các method argument vào named parameter. Ví dụ:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (p:Person {code: $code})
        SET p.name = $name,
            p.updatedAt = datetime(),
            p.updatedBy = $actor
        RETURN p
        """)
    Person rename(
        @Param("code") String code,
        @Param("name") String name,
        @Param("actor") String actor
    );
}
```

Ở đây Cypher tự ghi `updatedAt` và `updatedBy`. `BeforeBindCallback<Person>` không phải nơi để chờ SDN bổ sung hai field này cho câu lệnh `SET`. Nếu logic audit là bắt buộc, phải đưa nó vào query hoặc gọi một service dùng chung để tạo các giá trị cần bind.

Nếu query trả về `Person`, SDN có thể chuyển record trả về thành entity theo mapping đã khai báo. Đây là bước ánh xạ kết quả đọc. Không nhầm nó với callback trước bind của thao tác lưu. Một query trả entity cũng không có nghĩa SDN đã gọi `save(entity)` trước khi chạy Cypher.

Đặc biệt, khi `@Query` chỉ trả một phần thuộc tính hoặc relationship, object trả về có thể chưa được hydrate đầy đủ. Không dùng object đó như một aggregate hoàn chỉnh rồi gọi `save` toàn phần nếu chưa nạp lại graph cần thiết; những field hoặc relationship thiếu có thể bị ghi đè hoặc xóa khi đồng bộ.

## 6. Neo4jClient giữ transaction integration, nhưng mapping do bạn chọn

`Neo4jClient` cho phép chạy Cypher tùy chỉnh, bind tham số và ánh xạ kết quả bằng `mappedBy`. Client tích hợp với transaction management của Spring, nhưng không biến mọi query thành thao tác lưu entity qua lifecycle callback.

Ví dụ cập nhật trực tiếp:

```java
import org.springframework.data.neo4j.core.Neo4jClient;

public class PersonGraphWriter {
    private final Neo4jClient neo4jClient;

    public PersonGraphWriter(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public void updateName(String code, String name, String actor) {
        neo4jClient.query("""
                MATCH (p:Person {code: $code})
                SET p.name = $name,
                    p.updatedAt = datetime(),
                    p.updatedBy = $actor
                """)
            .bind(code).to("code")
            .bind(name).to("name")
            .bind(actor).to("actor")
            .run();
    }
}
```

Nếu method service gọi `updateName` trong `@Transactional`, query của `Neo4jClient` có thể tham gia transaction Spring hiện hành. Tuy nhiên, `BeforeBindCallback<Person>` không được gọi chỉ vì câu Cypher đã thay đổi node `Person`: không có entity `Person` nào được đưa qua bước bind map của SDN.

Khi dùng `fetchAs(Person.class).mappedBy(...)`, bạn đang chọn cách chuyển record thành kết quả. Nếu tự viết mapper, hãy chịu trách nhiệm cho logic mapping và mọi bước hậu xử lý cần thiết. Không giả định callback lifecycle của entity sẽ tự chạy cho mọi object được tạo bằng một lambda mapping tùy chỉnh.

## 7. Neo4j Java Driver trực tiếp nằm ngoài entity lifecycle của SDN

Driver thực thi Cypher ở mức thấp hơn. Khi code mở `Session`, chạy `tx.run(...)` và commit, nó không gọi repository save hoặc entity converter của SDN.

```java
import java.util.Map;

import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

public class DriverPersonWriter {
    private final Driver driver;

    public DriverPersonWriter(Driver driver) {
        this.driver = driver;
    }

    public void updateName(String code, String name, String actor) {
        try (Session session = driver.session()) {
            session.executeWrite(tx -> {
                tx.run("""
                    MATCH (p:Person {code: $code})
                    SET p.name = $name,
                        p.updatedAt = datetime(),
                        p.updatedBy = $actor
                    """, Map.of(
                        "code", code,
                        "name", name,
                        "actor", actor
                    )).consume();
                return null;
            });
        }
    }
}
```

Driver không biết `Person` là entity SDN, không biết callback bean nào được đăng ký và không tự thực hiện auditing annotation. Các quy tắc như cập nhật `updatedAt`, ghi lịch sử, tạo domain event hoặc kiểm tra quyền phải được thể hiện trong code/query mà ứng dụng chủ động gọi.

Ngoài giới hạn callback, raw `driver.session()` tạo session/transaction theo vòng đời Driver. Một session mới mở thủ công không tự động tham gia transaction Spring đang chạy. Nếu cần query tùy chỉnh vẫn nằm trong transaction Spring, ưu tiên `Neo4jClient` hoặc API query runner được quản lý bởi client thay vì tự mở transaction Driver độc lập.

## 8. So sánh đường ghi và callback có thể kỳ vọng

| Đường thực thi | `BeforeBindCallback` | Auditing trước bind | Transaction Spring | Ghi chú |
|---|---|---|---|---|
| `repository.save(entity)` | Có | Có, nếu auditing được bật và cấu hình đúng | Có thể tham gia transaction hiện hành | SDN chuyển entity thành dữ liệu ghi |
| `repository.saveAll(entities)` | Có cho các entity được lưu qua persistence path | Có | Có thể tham gia transaction hiện hành | Callback có thể chạy theo từng entity |
| `Neo4jTemplate.save(entity)` | Có | Có, nếu được cấu hình | Có thể tham gia transaction hiện hành | Vẫn là entity persistence path |
| `repository` method với `@Query` ghi Cypher | Không nên dựa vào | Không tự động | Có thể tham gia transaction Spring | Query tự quyết định property được ghi |
| `Neo4jClient.query(...).run()` | Không | Không tự động | Có thể tham gia transaction hiện hành; nếu không có thì dùng auto-commit | Cypher được chạy trực tiếp, không bind domain entity |
| Neo4j Java Driver `tx.run(...)` | Không | Không tự động | Không tự động; session tự mở có transaction độc lập | Code tự quản lý transaction và dữ liệu ghi |

`AfterConvertCallback` là callback phía đọc. Nó có thể được áp dụng khi SDN thực sự hydrate entity qua conversion path tương ứng, nhưng không biến một lệnh ghi trực tiếp thành entity save. Khi dùng mapper thủ công trên `Neo4jClient` hoặc Driver, hãy xác định rõ phần hậu xử lý do ứng dụng chịu trách nhiệm.

## 9. Domain event cũng có giới hạn theo repository method

Spring Data hỗ trợ `@DomainEvents` trên aggregate root. Repository infrastructure gọi phương thức này để lấy event khi một số repository method nhận aggregate instance được gọi, chẳng hạn `save(...)`, `saveAll(...)`, `delete(...)` và các biến thể xóa nhận entity/collection.

Entity `Person` ở ví dụ đầu bài có thể giữ domain event phát sinh từ thay đổi trạng thái. Khi gọi `person.rename(...)` rồi `personRepository.save(person)`, repository infrastructure đọc `@DomainEvents`, phát các event như Spring application event và gọi `@AfterDomainEventPublication` để dọn danh sách event.

Event có thể là một record bất biến:

```java
public record PersonRenamedEvent(String personCode, String name, String actor) {
}
```

`deleteById(...)` là trường hợp cần lưu ý: repository có thể xóa trực tiếp theo ID mà không nạp aggregate instance, nên không có event từ aggregate để công bố. Tương tự, `@Query` ghi/xóa Cypher, `Neo4jClient` và Driver không tự gọi phương thức `@DomainEvents` chỉ vì graph đã thay đổi.

Nếu dùng custom Cypher, service cần chủ động công bố event hoặc ghi một outbox record trong cùng transaction. Đừng coi `@DomainEvents` là database change stream hoặc trigger toàn cục.

Entity callback và application event có mục đích khác nhau. Dùng callback để sửa entity tại một điểm đồng bộ, có thứ tự trong persistence lifecycle. Dùng event để thông báo cho thành phần khác về điều đã xảy ra. Application event được phân phối qua `ApplicationEventMulticaster`; nếu cấu hình executor bất đồng bộ, listener có thể chạy ở thread khác và không còn nằm trong transaction context ban đầu. Khi cần hành động sau commit, dùng `@TransactionalEventListener` và không giả định listener bất đồng bộ có thể sửa entity trước khi lưu.

## 10. Dùng application event cho thông báo sau khi commit

Với một custom query, service có thể công bố application event sau khi gọi repository method. Dùng `@TransactionalEventListener` để listener chỉ xử lý sau khi transaction commit:

```java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonService {
    private final PersonRepository repository;
    private final ApplicationEventPublisher events;

    public PersonService(
            PersonRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public void rename(String code, String name, String actor) {
        repository.rename(code, name, actor);
        events.publishEvent(new PersonRenamedEvent(code, name, actor));
    }
}
```

Listener:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class PersonNotificationListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onPersonRenamed(PersonRenamedEvent event) {
        // Gửi thông báo hoặc cập nhật hệ thống phụ sau khi Neo4j commit.
    }
}
```

Event được công bố thủ công từ service, nên logic này áp dụng cả khi thao tác ghi là `@Query` hoặc `Neo4jClient`. Listener chỉ chạy sau commit khi có transaction tương ứng. Cách này tránh gửi thông báo cho một thay đổi đã rollback.

Application event vẫn là thông báo trong tiến trình. Nếu ứng dụng dừng đột ngột sau khi Neo4j commit nhưng trước khi listener hoàn thành, thông báo có thể bị mất. Với yêu cầu giao nhận bền vững, hãy ghi outbox node trong cùng transaction với thay đổi graph rồi dùng worker riêng để phát lại event và đánh dấu đã xử lý.

## 11. Giữ audit logic nhất quán giữa save và custom Cypher

Nếu một domain có cả `repository.save(entity)` và custom Cypher write, có ba cách thường dùng:

### Đưa giá trị audit vào service dùng chung

Service lấy actor và thời điểm một lần, sau đó truyền chúng cho repository hoặc custom query. Cách này làm rõ nghiệp vụ và tránh phụ thuộc vào callback trong đường ghi trực tiếp.

```java
import java.time.Instant;

public record AuditContext(String actor, Instant occurredAt) {
}

public AuditContext currentAuditContext() {
    return new AuditContext(currentUser(), clock.instant());
}
```

### Ghi audit field tường minh trong Cypher

```cypher
MATCH (p:Person {code: $code})
SET p.name = $name,
    p.updatedAt = $occurredAt,
    p.updatedBy = $actor
RETURN p;
```

Với custom query, hãy dùng named parameter và cùng quy tắc tên property với entity mapping. Nếu cần audit cả quan hệ, cập nhật property của relationship ngay trong query đó.

### Dùng helper hoặc repository fragment dùng chung

Nếu nhiều method custom query cần cùng quy tắc, gom phần lấy audit context và cách tạo query vào một service hoặc repository fragment. Tránh copy-paste mỗi câu lệnh một bộ quy tắc khác nhau. `Neo4jClient` phù hợp khi cần viết Cypher nhưng vẫn muốn giữ transaction integration của Spring.

## 12. Không dùng callback như cơ chế bảo vệ toàn vẹn dữ liệu

Callback chạy ở ứng dụng và chỉ ở những đường thực thi có gọi nó. Một script chạy trong Neo4j Browser, một ứng dụng khác, một job dùng Driver hoặc một câu lệnh Cypher tùy chỉnh có thể thay đổi graph mà không đi qua callback.

Vì vậy:

- Dùng unique constraint và constraint phù hợp của Neo4j để bảo vệ các quy tắc database hỗ trợ.
- Kiểm tra quyền và invariant nghiệp vụ tại service/use case, kể cả khi đường ghi là custom Cypher.
- Đặt audit field trong chính query ghi nếu query bỏ qua entity callback.
- Dùng transaction để nhóm thay đổi graph và outbox record khi cần phát event bền vững.
- Kiểm tra mọi đường ghi được phép trong ứng dụng: repository save, `@Query`, `Neo4jClient`, Driver và script vận hành.

Không có callback Java nào có thể bảo đảm một quy tắc được thực thi cho mọi client kết nối trực tiếp tới Neo4j. Nếu một invariant phải đúng bất kể client nào ghi dữ liệu, hãy dùng cơ chế database hỗ trợ hoặc kiểm soát quyền truy cập để chỉ cho phép các đường ghi đã được quản lý.

## 13. Kiểm thử để chứng minh giới hạn callback

Nên có integration test kiểm tra riêng từng đường ghi. Có thể dùng callback ghi nhận số lần được gọi hoặc kiểm tra audit field trong graph.

| Bài kiểm thử | Thao tác | Kỳ vọng |
|---|---|---|
| Entity save | Gọi `repository.save(person)` | `BeforeBindCallback` chạy; field do callback bổ sung được lưu |
| Template save | Gọi `neo4jTemplate.save(person)` | Callback trước bind chạy theo entity persistence path |
| Custom Cypher | Gọi repository method `@Query` có `SET` | Query chỉ ghi các field được khai báo; không dựa vào callback để bổ sung audit |
| Neo4jClient | Chạy `neo4jClient.query(...).run()` | Query chạy theo Cypher; service/query phải tự ghi audit |
| Raw Driver | Chạy `tx.run(...)` | Không có entity callback SDN; kiểm tra trực tiếp property sau commit |
| Domain event | Gọi repository `save(aggregate)` | Event từ `@DomainEvents` được công bố |
| Custom query event | Gọi `@Query` cập nhật graph | Không tự gọi `@DomainEvents`; event chỉ có nếu service chủ động công bố |
| Rollback | Ghi graph và publish event trong transaction rồi làm transaction rollback | Listener `AFTER_COMMIT` không chạy |

Khi kiểm thử `AfterConvertCallback`, cần thực hiện một thao tác đọc thực sự hydrate entity qua SDN converter. Khi mapper kết quả do ứng dụng tự viết, kiểm tra rõ mapper đó có gọi logic hậu xử lý cần thiết hay không.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `updatedAt` không đổi sau custom `@Query` | Chờ `BeforeBindCallback` chạy cho câu Cypher viết sẵn | Đưa timestamp vào query hoặc service parameter |
| `@LastModifiedBy` không được ghi khi dùng Driver | Driver không chạy SDN auditing callback | Bind actor và ghi property trực tiếp bằng Cypher |
| Domain event không được phát sau `@Query` | `@DomainEvents` gắn với repository method nhận aggregate instance | Công bố application event từ service hoặc ghi outbox |
| Listener gửi thông báo dù transaction rollback | Dùng listener thông thường ngay khi event được publish | Dùng `@TransactionalEventListener(AFTER_COMMIT)` |
| Callback chạy cho save nhưng không chạy cho delete theo ID | Delete method không có aggregate instance hoặc không đi qua entity bind path | Xử lý delete audit/event tại service hoặc query |
| Kết quả `@Query` không có giá trị hậu xử lý như mong đợi | Nhầm read-side conversion với write-side callback | Xác định result có được SDN hydrate hay do mapper tự viết |
| Raw Driver và repository có hành vi audit khác nhau | Chỉ một đường ghi đi qua callback | Chuẩn hóa audit context và ghi tường minh trong các đường custom |
| Application event bị mất khi ứng dụng dừng đột ngột | Event chỉ tồn tại trong bộ nhớ sau commit | Dùng transactional outbox cho yêu cầu giao nhận bền vững |

## 15. Quy trình chọn đúng cơ chế

1. Xác định thao tác có đi qua `save(entity)`/`Neo4jTemplate.save(entity)` hay thực thi Cypher trực tiếp.
2. Nếu cần sửa entity trước khi SDN bind dữ liệu, dùng `BeforeBindCallback` hoặc `ReactiveBeforeBindCallback` tương ứng.
3. Nếu cần xử lý object sau khi SDN hydrate record, dùng `AfterConvertCallback` và nhớ đây là logic phía đọc.
4. Nếu query ghi qua `@Query`, `Neo4jClient` hoặc Driver, đưa audit field và logic cần thiết vào service/query.
5. Nếu cần công bố domain event từ aggregate, dùng `@DomainEvents` với repository method hỗ trợ; với custom Cypher, công bố event thủ công hoặc ghi outbox.
6. Dùng `@TransactionalEventListener(AFTER_COMMIT)` cho side effect cần chạy sau commit.
7. Nếu dùng raw Driver, quản lý transaction/session đúng cách và không giả định session tự mở tham gia transaction Spring.
8. Kiểm thử tất cả đường ghi được ứng dụng hỗ trợ để bảo đảm audit và event không phụ thuộc vào một callback bị bỏ qua.

## 16. Tự kiểm tra

1. `BeforeBindCallback` được gọi ở bước nào của entity persistence?
2. Vì sao callback không phải database trigger cho mọi câu lệnh Cypher?
3. Khác biệt giữa `BeforeBindCallback` và `AfterConvertCallback` là gì?
4. Vì sao `@LastModifiedDate` không tự động cập nhật khi raw Driver chạy `SET`?
5. `Neo4jClient` có tích hợp transaction Spring không, và điều đó có đồng nghĩa nó gọi entity callback không?
6. Vì sao một repository method `@Query` ghi Cypher không nên được xem như `repository.save(entity)`?
7. Khi nào `@DomainEvents` được gọi và vì sao `deleteById` là trường hợp đặc biệt?
8. Làm thế nào phát application event sau khi custom Cypher commit thành công?
9. Khi nào nên dùng transactional outbox thay vì chỉ dùng application event?
10. Làm thế nào kiểm thử để chứng minh từng đường ghi đã ghi đầy đủ audit field?

## Tài liệu tham khảo

- [Spring Data Neo4j — FAQ: Auditing, BeforeBindCallback và ReactiveBeforeBindCallback](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j — BeforeBindCallback API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/mapping/callback/BeforeBindCallback.html)
- [Spring Data Neo4j — ReactiveBeforeBindCallback API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/mapping/callback/ReactiveBeforeBindCallback.html)
- [Spring Data Neo4j — AfterConvertCallback API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/mapping/callback/AfterConvertCallback.html)
- [Spring Data Neo4j — Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/neo4j/reference/repositories/core-domain-events.html)
- [Spring Data Neo4j — FAQ: Custom queries, Neo4jClient và transaction integration](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
