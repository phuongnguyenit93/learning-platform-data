# Callback với entity bất biến và đối tượng được trả về

Spring Data Neo4j (SDN) hỗ trợ entity bất biến: object không có setter và trạng thái của nó không thay đổi sau khi được tạo. Thiết kế này giúp mô hình miền dễ dự đoán hơn, nhưng đòi hỏi ứng dụng hiểu rõ cách Spring Data tạo object và cách callback chuyển object mới sang bước tiếp theo.

Điểm cốt lõi là **entity callback trả về một instance**. Với callback trước khi lưu, SDN dùng instance được trả về để tạo dữ liệu ghi xuống Neo4j. Với callback sau khi đọc, instance được trả về là object tiếp tục đi tới repository, template hoặc tầng gọi. Nếu callback tạo object mới nhưng không trả object đó, thay đổi sẽ bị mất.

Trong SDN, hai callback quan trọng cho bài học này là:

- **BeforeBindCallback<T>**: chạy trước khi entity được chuyển thành dữ liệu để ghi. Callback có thể trả chính entity đầu vào hoặc một instance mới.
- **AfterConvertCallback<T>**: chạy sau khi SDN đã chuyển record thành entity và xử lý các association. Callback trả entity được dùng tiếp sau bước hydrate.

Sau bài học, bạn có thể:

- Giải thích vì sao callback cần trả lại object thay vì chỉ thay đổi biến cục bộ.
- Tạo entity bất biến bằng constructor, factory method và wither.
- Dùng **BeforeBindCallback** để chuẩn hóa dữ liệu trước khi lưu.
- Dùng **AfterConvertCallback** để biến đổi object sau khi đọc.
- Phân biệt callback imperative, callback reactive và application event.
- Đăng ký callback bằng bean, sắp thứ tự và kiểm tra object thực sự được trả về.

## 1. Vòng đời callback khi lưu và đọc entity

Callback tham gia vào các điểm cụ thể của quá trình mapping. Nó không thay thế repository hoặc template; nó bổ sung bước xử lý entity ở đúng thời điểm.

~~~mermaid
flowchart TD
    A["repository.save(entity)"] --> B["BeforeBindCallback"]
    B --> C["Nhận entity callback trả về"]
    C --> D["Chuyển entity thành map/property"]
    D --> E["Ghi node và relationship vào Neo4j"]
    E --> F["save() trả entity đã lưu"]
    G["Đọc record từ Neo4j"] --> H["SDN hydrate node và association"]
    H --> I["AfterConvertCallback"]
    I --> J["Nhận entity callback trả về"]
    J --> K["Trả object cho repository/template"]
~~~

| Callback | Thời điểm | Giá trị trả về được dùng ở đâu? |
|---|---|---|
| **BeforeBindCallback<T>** | Trước khi entity được bind thành record | Dùng làm đầu vào cho bước chuyển đổi và ghi dữ liệu |
| **AfterConvertCallback<T>** | Sau khi record đã được hydrate đầy đủ, gồm association | Dùng làm object trả về cho tầng gọi |
| **ReactiveBeforeBindCallback<T>** | Trong reactive flow, trước khi entity được bind | Publisher phát ra entity được dùng để ghi |

`BeforeBindCallback` được gọi trước khi SDN chuyển entity thành một `Map` chứa dữ liệu record. Vì vậy, thay đổi được thực hiện trên instance trả về sẽ ảnh hưởng đến dữ liệu được ghi. `AfterConvertCallback` chạy sau khi entity cùng các association đã được xử lý; nó thích hợp để bổ sung hoặc điều chỉnh object đọc được.

## 2. Tạo entity bất biến

Ví dụ một node `Person` có ID do Neo4j tạo, tên, email và thời điểm tạo:

~~~java
package com.acme.graph.domain;

import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public final class Person {

    @Id
    @GeneratedValue
    private final Long id;

    private final String name;
    private final String email;
    private final Instant createdAt;

    public Person(
            Long id,
            String name,
            String email,
            Instant createdAt) {
        this.id = id;
        this.name = name;
        this.email = email;
        this.createdAt = createdAt;
    }

    public static Person create(String name, String email) {
        return new Person(null, name, email, null);
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Person withId(Long id) {
        return new Person(id, name, email, createdAt);
    }

    public Person withEmail(String email) {
        return new Person(id, name, email, createdAt);
    }

    public Person withCreatedAt(Instant createdAt) {
        return new Person(id, name, email, createdAt);
    }

    public Person withName(String name) {
        return new Person(id, name, email, createdAt);
    }
}
~~~

Các trường đều là `final`; class không có setter. Muốn thay đổi một thuộc tính, phương thức `with...` tạo instance mới và giữ nguyên các thuộc tính còn lại.

### Constructor và object mapping

Spring Data cần biết constructor nào dùng để tạo entity:

- Nếu có constructor không tham số, Spring Data ưu tiên constructor đó và bỏ qua các constructor khác.
- Nếu chỉ có một constructor có tham số, Spring Data dùng constructor đó.
- Nếu có nhiều constructor có tham số, đánh dấu constructor cần dùng bằng `@PersistenceCreator`.
- Tên tham số constructor phải khớp tên property. Tên tham số cần có trong bytecode hoặc được khai báo bằng `@ConstructorProperties`.

Với entity bất biến, nên dùng một constructor đầy đủ cho các persistent properties và factory method tĩnh cho các cách tạo object theo nghiệp vụ. Cách này tránh phải tạo nhiều constructor rồi phân giải bằng `@PersistenceCreator`.

### Vì sao cần withId?

Khi `@GeneratedValue` tạo ID, object ban đầu có thể chưa có ID. Do thuộc tính `id` là `final`, Spring Data không thể gán trực tiếp giá trị mới. Nếu entity cung cấp `withId(Long id)`, Spring Data gọi wither để tạo instance mới có ID vừa sinh.

Wither phải giữ lại những thuộc tính khác:

~~~java
public Person withId(Long id) {
    return new Person(id, name, email, createdAt);
}
~~~

Nếu wither vô tình đặt `email` hoặc `createdAt` thành `null`, object mới sẽ làm mất dữ liệu của object cũ. Vì vậy, mỗi wither phải sao chép đầy đủ trạng thái không thay đổi.

## 3. Dùng BeforeBindCallback để thay đổi object trước khi lưu

Giả sử email cần được loại bỏ khoảng trắng ở hai đầu và chuẩn hóa chữ thường trước khi ghi. Với entity bất biến, callback không thể gọi setter. Nó phải gọi `withEmail()` và trả object mới.

~~~java
package com.acme.graph.config;

import java.util.Locale;
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.mapping.callback.BeforeBindCallback;

import com.acme.graph.domain.Person;

@Configuration
public class PersonCallbackConfiguration {

    @Bean
    Clock systemClock() {
        return Clock.systemUTC();
    }

    @Bean
    BeforeBindCallback<Person> preparePersonForBinding(Clock clock) {
        return person -> {
            String email = person.getEmail();
            Person updated = person;

            if (email != null) {
                String normalizedEmail =
                    email.strip().toLowerCase(Locale.ROOT);
                updated = updated.withEmail(normalizedEmail);
            }

            if (updated.getCreatedAt() == null) {
                updated = updated.withCreatedAt(clock.instant());
            }

            return updated;
        };
    }
}
~~~

Không cần cấu hình registrar riêng. SDN nhận diện callback bean trong `ApplicationContext` và gọi nó tại điểm lifecycle tương ứng.

Khi gọi:

~~~java
Person person = Person.create(
    "An Nguyen",
    "  AN.NGUYEN@EXAMPLE.COM  "
);

Person saved = personRepository.save(person);
~~~

Callback tạo một instance có email `an.nguyen@example.com` và `createdAt` được lấy từ `Clock`; instance đó được chuyển thành dữ liệu ghi xuống Neo4j. Biến `person` ban đầu vẫn giữ email gốc và `createdAt` null vì entity bất biến. Biến `saved` là kết quả của thao tác lưu và là object cần dùng tiếp.

### Luôn dùng object được trả về

Với callback bất biến, không được giả định object ban đầu sẽ tự thay đổi:

~~~java
// Sai: kết quả của withEmail bị bỏ đi.
person.withEmail("an@example.com");
return person;
~~~

~~~java
// Đúng: trả về instance mới.
return person.withEmail("an@example.com");
~~~

Quy tắc tương tự áp dụng cho repository save:

~~~java
Person saved = personRepository.save(person);

// Dùng saved vì ID do Neo4j tạo có thể được gắn vào instance mới.
Long generatedId = saved.getId();
~~~

Không tiếp tục dùng object đầu vào để đọc ID hoặc các giá trị được callback và mapping bổ sung. Với entity bất biến, những thay đổi đó nằm trên instance mới được trả về.

## 4. AfterConvertCallback trả object sau khi đọc

`AfterConvertCallback<T>` được gọi sau khi SDN đã hydrate entity từ Neo4j. Tham số gồm:

- `instance`: object vừa được tạo từ record.
- `Neo4jPersistentEntity<T>`: metadata mô tả entity.
- `MapAccessor`: record nguồn dùng để hydrate object.

Callback phải trả object được dùng tiếp. Ví dụ, chuẩn hóa khoảng trắng trong tên ở object trả về:

~~~java
package com.acme.graph.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.mapping.callback.AfterConvertCallback;

import com.acme.graph.domain.Person;

@Configuration
public class PersonReadCallbackConfiguration {

    @Bean
    AfterConvertCallback<Person> normalizeNameAfterRead() {
        return (person, entity, source) -> {
            String name = person.getName();
            if (name == null) {
                return person;
            }

            return person.withName(name.strip());
        };
    }
}
~~~

Instance mới được trả về từ callback sẽ là object mà repository hoặc template cung cấp cho caller. Callback này chỉ thay đổi object đang được hydrate trong bộ nhớ; nó không tự ghi thay đổi trở lại Neo4j. Muốn lưu thay đổi, ứng dụng phải gọi thao tác ghi riêng.

### Khi nào dùng AfterConvertCallback?

Callback sau khi convert phù hợp với xử lý cần biết toàn bộ object graph đã được dựng xong, ví dụ:

- Chuẩn hóa giá trị hiển thị sau khi đọc.
- Tính thuộc tính dẫn xuất từ các property và association đã hydrate.
- Bổ sung giá trị transient cho object trả về.
- Áp dụng một quy tắc trình bày nhất quán cho entity được đọc từ nhiều repository.

Không dùng callback này để giả định rằng dữ liệu đã được cập nhật trong database. Nó chỉ điều chỉnh object được trả về từ lần đọc hiện tại.

## 5. Callback reactive và imperative

SDN có callback riêng cho thao tác ghi reactive:

| API | Callback trước khi bind | Kiểu trả về |
|---|---|---|
| Imperative repository/template | `BeforeBindCallback<T>` | `T` |
| Reactive repository/template | `ReactiveBeforeBindCallback<T>` | `Publisher<T>` |
| Đọc entity sau khi hydrate | `AfterConvertCallback<T>` | `T` |

Ví dụ callback reactive:

~~~java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.mapping.callback.ReactiveBeforeBindCallback;

import reactor.core.publisher.Mono;

import com.acme.graph.domain.Person;

@Configuration
public class ReactivePersonCallbackConfiguration {

    @Bean
    ReactiveBeforeBindCallback<Person> normalizePersonEmailReactive() {
        return person -> Mono.fromSupplier(() -> {
            String email = person.getEmail();
            if (email == null) {
                return person;
            }

            return person.withEmail(
                email.strip().toLowerCase(Locale.ROOT)
            );
        });
    }
}
~~~

`ReactiveBeforeBindCallback` trả Publisher phát ra entity cần ghi. Không gọi `block()` hoặc `subscribe()` bên trong callback. Để SDN quản lý Publisher trong luồng reactive và sử dụng instance được Publisher phát ra.

Spring Data tách callback theo loại API: thao tác imperative gọi callback imperative; thao tác reactive gọi callback reactive. Nếu ứng dụng hỗ trợ cả hai mô hình, hãy cung cấp đúng callback cho từng đường truy cập. Có thể tách logic chuẩn hóa thành một hàm thuần để hai callback cùng gọi và tránh lệch quy tắc.

`AfterConvertCallback` là ngoại lệ đáng chú ý: SDN không có reactive variant riêng cho callback này. API hiện tại dùng cùng `AfterConvertCallback<T>` cho cả workload imperative và reactive.

## 6. Thứ tự khi có nhiều callback

Một entity có thể đi qua nhiều callback cùng kiểu. Spring Data gọi các callback theo thứ tự được cấu hình:

- Dùng `@Order` trên bean hoặc `Ordered` để xác định thứ tự.
- Giá trị order nhỏ hơn được thực thi trước.
- Instance được callback trả về trở thành đầu vào cho callback tiếp theo.

Ví dụ:

~~~java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.data.neo4j.core.mapping.callback.BeforeBindCallback;

import com.acme.graph.domain.Person;

@Configuration
class OrderedPersonCallbacks {

    @Bean
    @Order(10)
    BeforeBindCallback<Person> normalizeEmail() {
        return person -> {
            String email = person.getEmail();
            return email == null
                ? person
                : person.withEmail(email.strip().toLowerCase(Locale.ROOT));
        };
    }

    @Bean
    @Order(20)
    BeforeBindCallback<Person> addDefaultName() {
        return person -> {
            if (person.getName() != null && !person.getName().isBlank()) {
                return person;
            }
            return person.withName("Unknown");
        };
    }
}
~~~

Trong ví dụ, callback chuẩn hóa email chạy trước, sau đó callback đặt tên mặc định nhận instance đã được callback đầu tiên trả về. Mỗi callback cần trả về một object hợp lệ để chuỗi mapping tiếp tục.

Tránh tạo nhiều callback có thứ tự phụ thuộc ngầm. Nếu thứ tự ảnh hưởng dữ liệu được lưu, hãy khai báo `@Order` rõ ràng và kiểm thử kết quả cuối cùng.

## 7. Callback khác application event như thế nào?

Entity callback và application event đều là điểm mở rộng trong lifecycle, nhưng hợp đồng của chúng khác nhau:

| Tiêu chí | Entity callback | Application event |
|---|---|---|
| Hợp đồng | Nhận entity và trả entity hoặc Publisher | Phát sự kiện cho listener |
| Mục đích phù hợp | Biến đổi object trong quy trình mapping | Thông báo cho thành phần khác về sự kiện |
| Entity bất biến | Có thể trả instance mới để SDN dùng tiếp | Listener không trả instance thay thế cho quy trình lưu |
| Thứ tự | Được điều phối bởi EntityCallbacks và order | Theo cơ chế ApplicationEventMulticaster |
| Thực thi bất đồng bộ | Callback được thực thi trong chuỗi xử lý tương ứng | Event multicaster có thể cấu hình async |

Nếu cần chuẩn hóa hoặc tạo một instance mới trước khi lưu, dùng `BeforeBindCallback`. Listener nhận một application event không có hợp đồng trả object thay thế; thay đổi một biến tham chiếu trong listener không thể thay entity mà SDN đang xử lý.

Application event phù hợp hơn khi muốn thông báo hoặc kích hoạt một phản ứng khác. Cần cẩn trọng nếu event listener được chạy bất đồng bộ: listener có thể chạy ở thread khác và không còn nằm trong đúng thứ tự hoặc transaction của thao tác ghi. Với sự kiện nghiệp vụ cần bảo đảm nhất quán cùng thay đổi aggregate, cân nhắc domain events hoặc outbox theo thiết kế transaction của ứng dụng.

## 8. Giới hạn khi dùng entity bất biến trong graph

Entity bất biến hoạt động tốt với constructor đầy đủ và wither, nhưng mô hình graph có một số trường hợp cần cân nhắc:

**Quan hệ hai chiều có tham chiếu vòng.** Nếu constructor của `Person` yêu cầu `Company`, trong khi constructor của `Company` cũng yêu cầu đúng instance `Person`, SDN không thể tạo đầy đủ hai object cùng lúc. Khi record chứa cấu trúc tham chiếu vòng như vậy, mapping có thể ném `MappingException`. Có thể dùng thuộc tính relationship có thể thay đổi hoặc điều chỉnh aggregate boundary để tránh vòng tham chiếu trong constructor.

**Thiếu wither cho property được gán sau constructor.** Property bất biến không nằm trong constructor mà cũng không có wither sẽ không thể được populate theo cách thông thường. Với ID do database tạo, đặc biệt cần wither như `withId`.

**Wither làm mất property khác.** Mỗi wither cần tạo instance mới và sao chép mọi property còn lại, gồm các relationship properties cần giữ.

**Constructor không khớp property.** Nếu tham số constructor không khớp tên property hoặc thiếu thông tin tên tham số, Spring Data có thể không tạo được entity đúng cách. Kiểm tra constructor mapping và `@PersistenceCreator` khi có nhiều constructor.

**Callback trả về null.** Callback phải trả về entity hợp lệ hoặc Publisher phát ra entity. Không trả null để biểu thị “không thay đổi”; hãy trả chính instance đầu vào.

## 9. Nguyên tắc thiết kế callback

- Giữ callback ngắn, xác định và tập trung vào vòng đời mapping.
- Với entity bất biến, ưu tiên constructor và wither thay vì reflection hoặc setter.
- Luôn trả về instance mới sau khi biến đổi; không bỏ kết quả của wither.
- Bảo toàn ID, version, property và association không thay đổi khi tạo instance mới.
- Dùng `BeforeBindCallback` cho dữ liệu cần ghi; dùng `AfterConvertCallback` cho object đã hydrate.
- Với reactive write, trả `Publisher<T>` từ `ReactiveBeforeBindCallback`; không block hoặc subscribe thủ công.
- Không gửi email, gọi HTTP hoặc thực hiện side effect bên ngoài trong callback mapping. Những việc đó thuộc application service hoặc cơ chế event/outbox phù hợp.
- Dùng `@Order` nếu nhiều callback có phụ thuộc thứ tự.
- Dùng object trả về từ `repository.save()` thay vì tiếp tục dùng object đầu vào.

## 10. Tự kiểm tra

1. `BeforeBindCallback<T>` được gọi ở thời điểm nào trong quy trình ghi?
2. Vì sao callback cần trả về `T` thay vì khai báo phương thức `void`?
3. Khi callback gọi `withEmail()` nhưng trả về entity đầu vào, điều gì xảy ra?
4. Vì sao entity có ID `final` và `@GeneratedValue` nên cung cấp `withId()`?
5. `AfterConvertCallback<T>` được gọi trước hay sau khi association được hydrate?
6. Thay đổi do `AfterConvertCallback` có tự động được ghi trở lại Neo4j không?
7. `ReactiveBeforeBindCallback<T>` khác `BeforeBindCallback<T>` ở kiểu trả về như thế nào?
8. Vì sao application event listener không thay thế được entity callback khi cần trả một object mới?
9. Khi có nhiều callback, cách nào kiểm soát thứ tự thực thi?
10. Vì sao quan hệ hai chiều có tham chiếu vòng có thể gây lỗi với constructor bất biến?

**Bài tập thực hành:** Tạo entity `Person` bất biến với `id`, `name`, `email` và `createdAt`. Cung cấp constructor đầy đủ, factory method `create()`, cùng các wither `withId()`, `withEmail()` và `withCreatedAt()`. Đăng ký `BeforeBindCallback<Person>` để chuẩn hóa email và điền `createdAt` nếu chưa có. Lưu một Person, kiểm tra object đầu vào vẫn giữ nguyên và object do `save()` trả về có ID cùng email đã chuẩn hóa. Tiếp theo, tạo `AfterConvertCallback<Person>` để chuẩn hóa tên của object được đọc, rồi chứng minh thay đổi này không tự cập nhật node trong Neo4j. Cuối cùng, triển khai `ReactiveBeforeBindCallback<Person>` trả về `Mono<Person>` và kiểm tra bằng reactive repository.

## Tài liệu tham khảo

- [Spring Data Neo4j FAQ — Modifying entities before save](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j API — BeforeBindCallback](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/mapping/callback/BeforeBindCallback.html)
- [Spring Data Neo4j API — AfterConvertCallback](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/mapping/callback/AfterConvertCallback.html)
- [Spring Data Neo4j API — ReactiveBeforeBindCallback](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/mapping/callback/ReactiveBeforeBindCallback.html)
- [Spring Data Neo4j — Spring Data Object Mapping Fundamentals](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/sdc-object-mapping.html)
- [Spring Data Commons — Entity Callbacks](https://docs.spring.io/spring-data/commons/reference/entity-callbacks.html)
