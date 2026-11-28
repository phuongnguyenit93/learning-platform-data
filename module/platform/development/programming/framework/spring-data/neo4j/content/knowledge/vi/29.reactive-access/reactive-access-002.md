# Mono, Flux, subscription và thời điểm truy vấn được thực thi

Bài học này thuộc chương **Truy cập reactive** của module **SPRING_DATA_NEO4J**. Spring Data Neo4j hỗ trợ cả cách truy cập imperative và reactive. Với reactive, repository, template và client trả về các kiểu publisher của Project Reactor như `Mono<T>` và `Flux<T>`. Các kiểu này mô tả một luồng kết quả sẽ được cung cấp cho subscriber; chúng không phải giá trị đã được lấy ngay từ database.

Điểm khác biệt quan trọng nhất là **tạo publisher và thực thi truy vấn là hai thời điểm khác nhau**. Khi gọi `repository.findById(id)`, ứng dụng nhận được một `Mono<Person>`. Lời gọi này mô tả công việc cần làm. Truy vấn Neo4j chỉ được kích hoạt khi có subscription. Vì vậy, reactive code cần kết hợp và trả về publisher để framework hoặc thành phần tiêu thụ thực hiện subscription ở đúng ranh giới.

## 1. Reactive access trong Spring Data Neo4j

Spring Data Neo4j dùng Project Reactor để biểu diễn các thao tác bất đồng bộ theo Reactive Streams. Những abstraction chính gồm:

- `ReactiveNeo4jRepository`: repository reactive cho entity.
- `ReactiveNeo4jTemplate`: thực hiện CRUD và truy vấn domain entity theo kiểu reactive.
- `ReactiveNeo4jClient`: chạy Cypher tùy biến và trả về publisher.
- `ReactiveNeo4jTransactionManager`: quản lý transaction reactive bằng Reactor Context.

Reactive API không yêu cầu ứng dụng phải tự tạo thread cho mỗi truy vấn. Thay vào đó, các thao tác được biểu diễn thành publisher và được điều phối theo subscription, demand và tín hiệu hoàn tất/lỗi. Neo4j Java Driver cung cấp reactive API nền tảng để SDN thực hiện truy vấn mà không cần chặn thread chờ kết quả.

Spring Data Neo4j hỗ trợ imperative và reactive trong cùng thư viện. Tuy nhiên, tài liệu SDN không khuyến nghị trộn hai kiểu truy cập trong cùng ứng dụng vì chúng có mô hình thực thi và transaction khác nhau. Một luồng reactive nên dùng repository, template và client reactive xuyên suốt.

## 2. Mono và Flux biểu diễn điều gì?

`Mono<T>` biểu diễn publisher có thể phát ra tối đa một phần tử kiểu `T`, sau đó hoàn tất hoặc phát lỗi. `Flux<T>` biểu diễn một chuỗi có thể phát ra từ không đến nhiều phần tử, sau đó hoàn tất hoặc phát lỗi.

| Kiểu | Số phần tử tối đa | Trường hợp thường dùng |
|---|---:|---|
| `Mono<Person>` | 1 | Tìm một người theo ID, lưu một người |
| `Mono<Long>` | 1 | Đếm số node |
| `Mono<Boolean>` | 1 | Kiểm tra tồn tại |
| `Mono<Void>` | 0 | Thao tác chỉ cần tín hiệu hoàn tất như xóa |
| `Flux<Person>` | Không giới hạn cố định | Tìm nhiều người hoặc đọc kết quả truy vấn |
| `Flux<Person>` từ `saveAll` | Không giới hạn cố định | Lưu nhiều entity và nhận các entity đã lưu |

`Mono` không có nghĩa luôn có một giá trị. Nó có thể hoàn tất rỗng (`Mono.empty()`), phát một giá trị rồi hoàn tất, hoặc phát lỗi. `Flux` cũng có thể hoàn tất mà không phát phần tử nào.

Ví dụ:

```java
Mono<Person> found = personRepository.findById("person-42");
Flux<Person> allPeople = personRepository.findAll();
Mono<Long> total = personRepository.count();
Mono<Boolean> exists = personRepository.existsById("person-42");
Mono<Void> deleted = personRepository.deleteById("person-42");
```

Các biến trên chỉ giữ publisher. Ở thời điểm khai báo, ứng dụng chưa nhận được `Person`, chưa biết số lượng kết quả và chưa hoàn thành thao tác xóa.

## 3. Khai báo reactive repository

Ví dụ entity `Person`:

```java
package com.example.graph.domain;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String name;

    private String city;

    public Person(String id, String name, String city) {
        this.id = id;
        this.name = name;
        this.city = city;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCity() {
        return city;
    }
}
```

Repository kế thừa `ReactiveNeo4jRepository`:

```java
package com.example.graph.repository;

import com.example.graph.domain.Person;
import org.springframework.data.neo4j.repository.ReactiveNeo4jRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface PersonRepository extends ReactiveNeo4jRepository<Person, String> {

    Mono<Person> findOneByName(String name);

    Flux<Person> findAllByCity(String city);
}
```

Các phương thức được tạo từ tên method cũng trả về reactive type. Với kết quả tối đa một entity, dùng `Mono<Person>`. Với nhiều entity, dùng `Flux<Person>`. Repository reactive kế thừa các thao tác CRUD reactive như `findById`, `findAll`, `save`, `saveAll`, `count`, `existsById`, `deleteById`.

Method trả `Mono<T>` cần có semantics tối đa một kết quả. Nếu điều kiện như `findOneByName` thực tế khớp nhiều node, repository sẽ báo lỗi số lượng kết quả thay vì tự chọn một node bất kỳ. Nếu nghiệp vụ cho phép nhiều kết quả, đổi kiểu trả về thành `Flux<T>`; nếu cần một kết quả duy nhất, bảo vệ điều kiện đó bằng unique constraint phù hợp trong Neo4j.

## 4. Các thao tác repository và kiểu trả về

Một số kiểu trả về thường gặp:

| Thao tác | Kiểu trả về | Ý nghĩa |
|---|---|---|
| `findById(id)` | `Mono<T>` | Có thể tìm thấy một entity hoặc hoàn tất rỗng |
| `findAll()` | `Flux<T>` | Phát các entity phù hợp, có thể rỗng |
| `findAllById(ids)` | `Flux<T>` | Phát các entity tìm được theo tập ID |
| `save(entity)` | `Mono<T>` | Phát entity đã lưu |
| `saveAll(entities)` | `Flux<T>` | Phát các entity đã lưu |
| `count()` | `Mono<Long>` | Phát số lượng |
| `existsById(id)` | `Mono<Boolean>` | Phát kết quả tồn tại |
| `deleteById(id)` | `Mono<Void>` | Hoàn tất khi thao tác xóa kết thúc |
| `deleteAll()` | `Mono<Void>` | Hoàn tất khi thao tác xóa kết thúc |

Với `Mono<Void>`, không có phần tử `onNext` để xử lý. Subscriber chỉ nhận tín hiệu hoàn tất hoặc lỗi. Nếu cần chạy bước tiếp theo sau thao tác xóa, dùng `then(...)` thay vì cố lấy một giá trị từ `Mono<Void>`.

## 5. Tạo publisher chưa chạy truy vấn

Reactive repository và `ReactiveNeo4jClient` trả về publisher. Đặc biệt, API `ReactiveNeo4jClient` quy định các thao tác chỉ được thực thi khi có subscription vào reactive sequence đã tạo.

Ví dụ:

```java
import com.example.graph.domain.Person;
import com.example.graph.repository.PersonRepository;
import reactor.core.publisher.Mono;

public Mono<Person> findPerson(String id) {
    Mono<Person> result = personRepository.findById(id);

    // Tại đây mới có publisher; truy vấn chưa được subscribe.
    return result;
}
```

Khi method trả về `Mono<Person>`, nó chưa cần chờ Neo4j trả kết quả. Một thành phần tiêu thụ ở phía trên sẽ subscribe và bắt đầu thực thi pipeline.

### Ví dụ với ReactiveNeo4jClient

`ReactiveNeo4jClient` cũng xây dựng publisher trước, rồi thực thi query khi publisher đó được subscribe:

```java
import org.springframework.data.neo4j.core.ReactiveNeo4jClient;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class PersonQueryService {

    private final ReactiveNeo4jClient neo4jClient;

    public PersonQueryService(ReactiveNeo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public Flux<String> findNamesInCity(String city) {
        return neo4jClient.query("""
                MATCH (p:Person {city: $city})
                RETURN p.name AS name
                ORDER BY name
                """)
            .bind(city).to("city")
            .fetchAs(String.class)
            .mappedBy((typeSystem, record) -> record.get("name").asString())
            .all();
    }
}
```

`.all()` trả về `Flux<String>` chứa các tên được truy vấn. Nếu cần chạy Cypher không trả record, dùng `run()`; phương thức này trả `Mono<ResultSummary>`. Cả hai publisher chỉ thực thi câu lệnh khi có subscription.

Có thể hình dung hai giai đoạn:

```text
Assembly time (xây dựng pipeline)
  personRepository.findById("person-42")
       |
       +--> tạo Mono<Person>
       +--> nối map / flatMap / filter / onErrorResume
       +--> trả publisher cho caller

Subscription time (bắt đầu thực thi)
  Subscriber đăng ký
       |
       +--> subscription được thiết lập
       +--> demand được truyền tới upstream
       +--> SDN/Driver thực thi truy vấn Neo4j
       +--> phát onNext, onComplete hoặc onError
```

Điều này cho phép ứng dụng xây dựng pipeline qua nhiều service mà không phải chặn tại mỗi bước để đợi giá trị.

## 6. Subscription và các tín hiệu Reactive Streams

Khi một subscriber đăng ký với publisher, một subscription được tạo. Subscriber có thể yêu cầu số lượng phần tử cần nhận thông qua demand. Publisher phát các tín hiệu chính:

- `onSubscribe`: thông báo subscription đã được thiết lập.
- `onNext`: publisher phát một phần tử dữ liệu.
- `onComplete`: publisher báo chuỗi kết thúc thành công, có thể không có phần tử nào.
- `onError`: publisher báo chuỗi kết thúc do lỗi.
- `cancel`: subscriber gọi trên `Subscription` để yêu cầu hủy; đây là thao tác điều khiển, không phải tín hiệu `on...` được publisher phát.

Với `Mono<Person>`, tối đa một `onNext` được phát trước `onComplete`. Với `Flux<Person>`, có thể có nhiều `onNext` trước `onComplete`. `onError` là tín hiệu kết thúc thay thế cho hoàn tất thành công; một chuỗi không phát cả `onComplete` và `onError` cho cùng một subscription.

Ví dụ publisher đơn giản:

```java
import reactor.core.publisher.Flux;

Flux<String> names = Flux.just("An", "Bình", "Chi");

names.subscribe(
    name -> System.out.println("Tên: " + name),
    error -> System.err.println("Lỗi: " + error.getMessage()),
    () -> System.out.println("Đã hoàn tất")
);
```

Lời gọi `subscribe(...)` ở đây tạo subscription và kích hoạt nguồn `Flux`. Trong ứng dụng WebFlux, thường không cần gọi thủ công như ví dụ này; controller trả publisher để runtime WebFlux làm subscriber.

## 7. WebFlux là nơi tiêu thụ publisher

Một reactive controller có thể trả trực tiếp `Mono` hoặc `Flux`:

```java
package com.example.graph.web;

import com.example.graph.domain.Person;
import com.example.graph.service.PersonService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/people")
public class PersonController {

    private final PersonService personService;

    public PersonController(PersonService personService) {
        this.personService = personService;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Person>> findById(@PathVariable String id) {
        return personService.findById(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @GetMapping
    public Flux<Person> findAll() {
        return personService.findAll();
    }
}
```

WebFlux nhận publisher từ controller và subscribe khi xử lý request. `Mono` được dùng cho một response có thể vắng mặt; `Flux` được dùng cho nhiều kết quả. Không cần gọi `.subscribe()` trong controller để trả dữ liệu.

Nếu tự subscribe trong controller rồi trả `Mono.empty()`, request HTTP không còn được liên kết với subscription đã tạo. Runtime không thể điều phối đúng kết quả, lỗi, cancellation hoặc backpressure của công việc đó.

## 8. Kết hợp nhiều thao tác bằng operator

Reactive code được xây dựng bằng cách nối operator. Các operator không thực thi độc lập ngay tại thời điểm gọi; chúng tạo một publisher mới mô tả bước xử lý tiếp theo.

### map: biến đổi giá trị đồng bộ

`map` nhận một giá trị đã phát và biến đổi nó thành một giá trị khác:

```java
import com.example.graph.domain.Person;
import com.example.graph.repository.PersonRepository;
import reactor.core.publisher.Mono;

Mono<String> personName = personRepository.findById("person-42")
    .map(Person::getName);
```

Nếu repository hoàn tất rỗng, `map` không được gọi và kết quả vẫn là `Mono.empty()`.

### flatMap: nối một thao tác trả Mono

Khi bước tiếp theo cũng trả về publisher, dùng `flatMap` để nối pipeline thay vì tạo publisher lồng nhau:

Giả sử `ProfileRepository.findOneByPersonId(...)` trả `Mono<Profile>` và `PersonProfile` là DTO kết hợp hai đối tượng:

```java
package com.example.graph.domain;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Profile")
public record Profile(@Id String id, String personId, String bio) {
}
```

```java
package com.example.graph.domain;

public record PersonProfile(Person person, Profile profile) {
}
```

```java
package com.example.graph.repository;

import com.example.graph.domain.Profile;
import org.springframework.data.neo4j.repository.ReactiveNeo4jRepository;
import reactor.core.publisher.Mono;

public interface ProfileRepository extends ReactiveNeo4jRepository<Profile, String> {

    Mono<Profile> findOneByPersonId(String personId);
}
```

```java
import com.example.graph.domain.Person;
import com.example.graph.domain.PersonProfile;
import com.example.graph.repository.PersonRepository;
import com.example.graph.repository.ProfileRepository;
import reactor.core.publisher.Mono;

public Mono<PersonProfile> findProfile(String personId) {
    return personRepository.findById(personId)
        .flatMap(person -> profileRepository.findOneByPersonId(person.getId())
            .map(profile -> new PersonProfile(person, profile)));
}
```

`flatMap` subscribe vào publisher được tạo từ mỗi giá trị upstream và hợp nhất kết quả vào pipeline bên ngoài. Nếu dùng `map` trong trường hợp này, kiểu kết quả sẽ thành `Mono<Mono<Profile>>` hoặc `Mono<Mono<PersonProfile>>`, tức publisher lồng nhau.

Nếu một `Mono` cần mở rộng thành nhiều kết quả, dùng `flatMapMany`:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Skill")
public record Skill(@Id String id, String name, String personId) {
}
```

```java
import com.example.graph.domain.Skill;
import org.springframework.data.neo4j.repository.ReactiveNeo4jRepository;
import reactor.core.publisher.Flux;

public interface SkillRepository extends ReactiveNeo4jRepository<Skill, String> {

    Flux<Skill> findAllByPersonId(String personId);
}
```

```java
import com.example.graph.domain.Person;
import com.example.graph.domain.Skill;
import com.example.graph.repository.PersonRepository;
import com.example.graph.repository.SkillRepository;
import reactor.core.publisher.Flux;

public Flux<Skill> findSkills(String personId) {
    return personRepository.findById(personId)
        .flatMapMany(person -> skillRepository.findAllByPersonId(person.getId()));
}
```

Trong ví dụ, `findById` phát tối đa một `Person`, còn `findAllByPersonId` có thể phát nhiều `Skill`. `flatMapMany` chuyển pipeline từ `Mono<Person>` sang `Flux<Skill>`.

### then: chờ hoàn tất và bỏ qua giá trị trước

`then` phù hợp với thao tác trả `Mono<Void>` hoặc khi chỉ quan tâm thứ tự hoàn tất:

Giả sử `AuditRepository.save(...)` trả `Mono<AuditEntry>` và `AuditEntry` là một kiểu dữ liệu audit đơn giản:

```java
package com.example.graph.domain;

import java.util.UUID;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("AuditEntry")
public record AuditEntry(@Id String id, String action, String reference) {

    public static AuditEntry created(String personId) {
        return new AuditEntry(UUID.randomUUID().toString(), "CREATE_PERSON", personId);
    }

    public static AuditEntry deleted(String personId) {
        return new AuditEntry(UUID.randomUUID().toString(), "DELETE_PERSON", personId);
    }
}
```

```java
package com.example.graph.repository;

import com.example.graph.domain.AuditEntry;
import org.springframework.data.neo4j.repository.ReactiveNeo4jRepository;

public interface AuditRepository extends ReactiveNeo4jRepository<AuditEntry, String> {
}
```

```java
import com.example.graph.domain.AuditEntry;
import com.example.graph.repository.AuditRepository;
import com.example.graph.repository.PersonRepository;
import reactor.core.publisher.Mono;

// AuditEntry là kiểu dữ liệu ghi nhận thao tác; repository trả Mono<AuditEntry>.
public Mono<Void> deletePerson(String id) {
    return personRepository.deleteById(id)
        .then(auditRepository.save(AuditEntry.deleted(id)))
        .then();
}
```

Audit chỉ được lưu sau khi thao tác xóa hoàn tất thành công. Nếu xóa phát lỗi, bước sau không được chạy và lỗi đi tiếp xuống subscriber. Kết quả cuối là `Mono<Void>`.

### zip: kết hợp các publisher độc lập

Khi hai truy vấn không phụ thuộc kết quả của nhau, có thể chạy và kết hợp kết quả bằng `Mono.zip`:

`Dashboard` là DTO giữ hai số đếm; các repository được inject vào service:

```java
package com.example.graph.domain;

public record Dashboard(long peopleCount, long movieCount) {
}
```

```java
import com.example.graph.domain.Dashboard;
import com.example.graph.repository.MovieRepository;
import com.example.graph.repository.PersonRepository;
import reactor.core.publisher.Mono;

// Dashboard là DTO; hai repository đã được inject vào service.
public Mono<Dashboard> loadDashboard() {
    Mono<Long> peopleCount = personRepository.count();
    Mono<Long> movieCount = movieRepository.count();

    return Mono.zip(peopleCount, movieCount)
        .map(tuple -> new Dashboard(tuple.getT1(), tuple.getT2()));
}
```

`zip` chờ các nguồn cung cấp phần tử để tạo tuple. Nếu một nguồn hoàn tất rỗng, không thể tạo tuple đầy đủ và kết quả kết hợp cũng có thể hoàn tất rỗng. Nếu cần giá trị mặc định, hãy xử lý từng `Mono` bằng `defaultIfEmpty(...)` trước khi zip.

## 9. Phân biệt Mono.just, defer và publisher trả về từ repository

`Mono.just(value)` giữ một giá trị đã có tại thời điểm gọi. Nó không phải công cụ để bọc một thao tác blocking rồi biến thao tác đó thành non-blocking.

Ví dụ sai về kiểu dữ liệu:

```java
import com.example.graph.domain.Person;
import com.example.graph.repository.PersonRepository;
import reactor.core.publisher.Mono;

Mono<Mono<Person>> nested = Mono.just(personRepository.findById("person-42"));
```

Đoạn này tạo `Mono` chứa một publisher khác. Nó không tự flatten publisher bên trong và không phải cách gọi repository thông thường.

Hãy trả trực tiếp publisher từ repository:

```java
import com.example.graph.domain.Person;
import com.example.graph.repository.PersonRepository;
import reactor.core.publisher.Mono;

Mono<Person> person = personRepository.findById("person-42");
```

Nếu cần trì hoãn cả việc tạo publisher cho tới subscription, dùng `Mono.defer`:

```java
import com.example.graph.domain.Person;
import com.example.graph.repository.PersonRepository;
import reactor.core.publisher.Mono;

Mono<Person> person = Mono.defer(
    () -> personRepository.findById("person-42")
);
```

Với reactive repository, bản thân thao tác database đã được biểu diễn thành publisher và được thực thi khi subscribe. `defer` hữu ích khi việc tạo publisher phụ thuộc vào dữ liệu hoặc trạng thái cần đọc ở thời điểm subscription; không cần bọc mọi lời gọi repository bằng `defer` một cách máy móc.

## 10. Publisher cold và nhiều lần subscription

`Mono` và `Flux` mô tả số lượng phần tử, không tự cho biết nguồn là cold hay hot. Nhiều publisher do repository và reactive client tạo ra có hành vi cold: mỗi subscription khởi động lại nguồn dữ liệu. Điều này có nghĩa cùng một publisher có thể chạy truy vấn Neo4j nhiều lần nếu có nhiều subscriber độc lập.

Ví dụ:

```java
import com.example.graph.domain.Person;
import com.example.graph.repository.PersonRepository;
import reactor.test.StepVerifier;

Mono<Person> person = personRepository.findById("person-42");

StepVerifier.create(person).expectNextCount(1).verifyComplete();
StepVerifier.create(person).expectNextCount(1).verifyComplete();
```

Đây là ví dụ kiểm thử có chủ đích: mỗi `StepVerifier` tạo một subscription mới, vì vậy publisher cold có thể thực hiện truy vấn riêng cho từng lần. Trong code ứng dụng, không tạo nhiều subscription như vậy chỉ để dùng lại cùng kết quả; hãy chia sẻ kết quả trong một pipeline bằng các operator phù hợp.

Nếu thật sự cần chia sẻ hoặc cache kết quả giữa nhiều subscriber, Reactor có các operator như `cache()` hoặc `share()`. Tuy nhiên, chúng thay đổi semantics của nguồn:

- `cache()` giữ tín hiệu đã phát để subscriber sau nhận lại mà không chạy lại nguồn trong thời gian cache còn hiệu lực.
- `share()` multicast subscription đang chạy cho nhiều subscriber; subscriber đến muộn có thể không nhận lại các phần tử đã phát trước đó.

Không thêm `cache()` chỉ để tránh viết lại pipeline. Với dữ liệu database, cache cần chính sách hết hạn, invalidation và tính nhất quán rõ ràng. Một query được cache có thể trả dữ liệu cũ sau khi graph đã thay đổi.

## 11. Không tự subscribe trong service

Trong một ứng dụng reactive, service nên trả publisher để caller tiếp tục điều phối. Tự gọi `subscribe()` bên trong service thường tạo một subscription tách rời khỏi pipeline của request.

Ví dụ không nên dùng:

```java
import com.example.graph.domain.Person;
import com.example.graph.repository.PersonRepository;
import reactor.core.publisher.Mono;

public Mono<Void> createPerson(Person person) {
    personRepository.save(person).subscribe();
    return Mono.empty();
}
```

Method trả về ngay một `Mono.empty()` khác, trong khi thao tác save chạy ở subscription riêng. Caller không thể chờ kết quả save, nhận lỗi save hoặc hủy thao tác save qua publisher mà method trả về.

Hãy trả trực tiếp publisher:

```java
import com.example.graph.domain.Person;
import com.example.graph.repository.PersonRepository;
import reactor.core.publisher.Mono;

public Mono<Person> createPerson(Person person) {
    return personRepository.save(person);
}
```

Nếu cần thêm bước sau khi lưu:

```java
import com.example.graph.domain.AuditEntry;
import com.example.graph.domain.Person;
import com.example.graph.repository.AuditRepository;
import com.example.graph.repository.PersonRepository;
import reactor.core.publisher.Mono;

public Mono<Person> createPerson(Person person) {
    return personRepository.save(person)
        .flatMap(saved -> auditRepository.save(AuditEntry.created(saved.getId()))
            .thenReturn(saved));
}
```

Giờ đây save và audit thuộc cùng một pipeline. Lỗi, cancellation và transaction context có thể được truyền xuyên suốt chuỗi thao tác.

Có những ranh giới imperative như listener hoặc callback bên ngoài WebFlux buộc ứng dụng tự subscribe. Trong trường hợp đó, phải xử lý lỗi và giữ `Disposable` nếu cần hủy công việc. Đây là trường hợp tích hợp có chủ đích, không phải mẫu mặc định cho controller hay service.

## 12. Tránh block trong reactive pipeline

Các phương thức `block()`, `blockOptional()`, `blockFirst()` và `blockLast()` subscribe vào publisher rồi chặn thread hiện tại để chờ kết quả. Chúng hữu ích trong một số ranh giới imperative hoặc mã kiểm thử đơn giản, nhưng không nên dùng trong controller, service reactive hoặc event-loop của WebFlux.

Ví dụ không nên dùng:

```java
import com.example.graph.domain.Person;
import com.example.graph.repository.PersonRepository;
import reactor.core.publisher.Mono;

public Person findPerson(String id) {
    return personRepository.findById(id).block();
}
```

Method này chuyển reactive repository thành lời gọi đồng bộ và chặn thread cho đến khi Neo4j trả kết quả. Nếu chạy trên event-loop, nó có thể làm giảm khả năng phục vụ các request khác hoặc gây lỗi do blocking call trên non-blocking scheduler.

Giữ kiểu trả về reactive:

```java
import com.example.graph.domain.Person;
import com.example.graph.repository.PersonRepository;
import reactor.core.publisher.Mono;

public Mono<Person> findPerson(String id) {
    return personRepository.findById(id);
}
```

Không dùng `subscribeOn` để che giấu một repository imperative hoặc lời gọi blocking. Chuyển scheduler chỉ đổi nơi thực thi; nó không biến API blocking thành reactive I/O. Nếu phải gọi thư viện blocking bên ngoài, tách rõ ranh giới và dùng scheduler phù hợp như `Schedulers.boundedElastic()` theo hướng dẫn Reactor.

## 13. Xử lý lỗi trong pipeline

Reactive pipeline truyền lỗi qua tín hiệu `onError`. Lỗi có thể đến từ kết nối Neo4j, câu Cypher, mapping, validation hoặc logic trong operator.

`doOnError` dùng để quan sát hoặc ghi log, không biến lỗi thành kết quả thành công:

```java
import com.example.graph.repository.PersonRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import reactor.core.publisher.Mono;

private static final Logger log = LoggerFactory.getLogger(PersonService.class);

return personRepository.findById(id)
    .doOnError(error -> log.error("Không thể tải Person {}", id, error));
```

`onErrorResume` có thể thay publisher lỗi bằng một publisher khác:

```java
import com.example.graph.repository.PersonRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import reactor.core.publisher.Mono;

private static final Logger log = LoggerFactory.getLogger(PersonService.class);

return personRepository.findById(id)
    .onErrorResume(DataAccessException.class, error -> {
        log.warn("Neo4j tạm thời không truy cập được", error);
        return Mono.empty();
    });
```

Chỉ chuyển lỗi thành `Mono.empty()` nếu hợp đồng nghiệp vụ cho phép coi lỗi đó như không có dữ liệu. Không nuốt mọi exception, vì điều đó có thể khiến lỗi database bị hiểu nhầm là kết quả tìm kiếm rỗng.

Với lỗi tạm thời, có thể cân nhắc `retryWhen`, nhưng chỉ retry khi thao tác an toàn để chạy lại. Một thao tác ghi không idempotent có thể tạo dữ liệu trùng nếu lần đầu đã ghi thành công ở database nhưng phản hồi bị mất. Dùng khóa nghiệp vụ, `MERGE`, constraint và chính sách retry có giới hạn để bảo đảm an toàn.

## 14. Cancellation và backpressure với Flux

`Flux<T>` có thể phát nhiều phần tử. Reactive Streams cho phép subscriber kiểm soát demand để nguồn không cần phát vô hạn dữ liệu vượt quá khả năng xử lý của downstream. Khi subscriber hủy, cancellation được truyền ngược về upstream để nguồn dừng và giải phóng tài nguyên khi có thể.

Điều này hữu ích khi client HTTP ngắt kết nối hoặc khi một luồng xử lý chỉ cần một phần kết quả. Ví dụ:

```java
import com.example.graph.domain.Person;
import com.example.graph.repository.PersonRepository;
import reactor.core.publisher.Flux;

public Flux<Person> firstTwentyPeople() {
    return personRepository.findAll()
        .take(20);
}
```

`take(20)` giới hạn số phần tử downstream nhận. Tuy nhiên, nếu cần giới hạn công việc ngay tại database, hãy thiết kế truy vấn có `LIMIT` hoặc phân trang phù hợp thay vì luôn tải toàn bộ graph rồi cắt ở phía ứng dụng.

Không gọi `collectList()` một cách vô điều kiện trên một `Flux` lớn:

```java
import java.util.List;

import com.example.graph.domain.Person;
import com.example.graph.repository.PersonRepository;
import reactor.core.publisher.Mono;

Mono<List<Person>> allPeople = personRepository.findAll().collectList();
```

`collectList()` chờ toàn bộ sequence hoàn tất và giữ các phần tử trong bộ nhớ để tạo một `List`. Nó phù hợp khi tập kết quả nhỏ và cần xử lý như một khối; với dữ liệu lớn, hãy xử lý từng phần tử, dùng phân trang hoặc streaming response.

## 15. Transaction reactive và Reactor Context

Reactive transaction không gắn với một thread cố định. `ReactiveNeo4jTransactionManager` quản lý native transaction của Neo4j trong Reactor Context. Vì vậy, các thao tác database muốn cùng tham gia một transaction cần nằm trong cùng reactive pipeline/context.

Ví dụ service:

```java
import com.example.graph.domain.AuditEntry;
import com.example.graph.domain.Person;
import com.example.graph.repository.AuditRepository;
import com.example.graph.repository.PersonRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class PersonService {

    private final PersonRepository personRepository;
    private final AuditRepository auditRepository;

    public PersonService(
            PersonRepository personRepository,
            AuditRepository auditRepository) {
        this.personRepository = personRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public Mono<Person> create(Person person) {
        return personRepository.save(person)
            .flatMap(saved -> auditRepository.save(AuditEntry.created(saved.getId()))
                .thenReturn(saved));
    }
}
```

Vì method trả về `Mono<Person>` và các thao tác được nối trong cùng pipeline, transaction interceptor có thể mở reactive transaction và giữ transaction context cho các thao tác repository. Nếu bước audit phát lỗi, transaction có thể rollback thao tác lưu person theo quy tắc rollback của Spring.

Không gọi `.subscribe()` bên trong method `@Transactional`. Subscription tách rời có thể không tham gia Reactor Context của transaction hiện tại. Không chuyển một giá trị đã lấy ra khỏi publisher rồi gọi repository imperative nếu muốn thao tác đó cùng thuộc reactive transaction.

Khi Spring dùng `ReactiveNeo4jTransactionManager`, method được đánh dấu `@Transactional` cần trả về một reactive pipeline như `Mono` hoặc `Flux`. Method trả `void` hoặc kiểu Java thông thường đi theo transaction imperative (`PlatformTransactionManager`), không tự trở thành reactive transaction chỉ vì bên trong có gọi reactive repository.

### Khác biệt với thread-bound transaction

Trong imperative, Spring thường gắn transaction resource vào thread hiện tại. Với reactive, transaction state được gắn vào Reactor Context của subscription. Một pipeline có thể chuyển scheduler/thread mà vẫn giữ context khi các operator Reactor truyền context đúng cách. Vì vậy, không dùng `ThreadLocal` để tự lấy transaction trong reactive code.

### Cấu hình transaction manager

Khi dùng Spring Boot, reactive repositories và `ReactiveNeo4jTemplate` được auto-configure nếu Project Reactor có trên classpath. Tuy nhiên, Boot không tự cấu hình `ReactiveTransactionManager` cho kiểu truy cập reactive. Nếu cần `@Transactional` reactive, khai báo `ReactiveNeo4jTransactionManager`:

```java
import org.neo4j.driver.Driver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.ReactiveDatabaseSelectionProvider;
import org.springframework.data.neo4j.core.transaction.ReactiveNeo4jTransactionManager;

@Configuration(proxyBeanMethods = false)
public class ReactiveNeo4jTransactionConfiguration {

    @Bean
    ReactiveNeo4jTransactionManager reactiveTransactionManager(
            Driver driver,
            ReactiveDatabaseSelectionProvider databaseSelectionProvider) {
        return new ReactiveNeo4jTransactionManager(driver, databaseSelectionProvider);
    }
}
```

Ví dụ này giả định Boot đã cung cấp `Driver` và `ReactiveDatabaseSelectionProvider`. Nếu không dùng Boot, có thể kế thừa `AbstractReactiveNeo4jConfig`, bật `@EnableReactiveNeo4jRepositories` và `@EnableTransactionManagement` để đăng ký hạ tầng reactive.

## 16. Kiểm thử bằng StepVerifier

Không cần gọi `block()` trong test reactive. `StepVerifier` tạo subscription, kiểm tra các tín hiệu được phát và xác nhận sequence kết thúc đúng như kỳ vọng.

Ví dụ kiểm thử tìm một người:

```java
import com.example.graph.repository.PersonRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.data.neo4j.test.Neo4jIntegrationTest;
import reactor.test.StepVerifier;

@Neo4jIntegrationTest
@DataNeo4jTest
class PersonRepositoryTest {

    @Autowired
    PersonRepository personRepository;

    @Test
    void shouldFindPerson() {
        StepVerifier.create(personRepository.findById("person-42"))
            .expectNextMatches(person -> "An".equals(person.getName()))
            .verifyComplete();
    }
}
```

`StepVerifier.create(...)` subscribe vào publisher. `expectNextMatches` kiểm tra phần tử; `verifyComplete()` chờ và xác nhận tín hiệu hoàn tất. Nếu repository phát lỗi hoặc không phát phần tử, test sẽ thất bại theo expectation.

Với một `Flux`, có thể xác nhận số lượng và thứ tự:

```java
import com.example.graph.repository.PersonRepository;
import reactor.test.StepVerifier;

StepVerifier.create(personRepository.findAllByCity("Hà Nội"))
    .expectNextCount(2)
    .verifyComplete();
```

Nên kiểm tra cả trường hợp publisher rỗng, lỗi, cancellation, nhiều subscription và transaction rollback. Khi test thao tác ghi, hãy xác nhận dữ liệu sau khi publisher hoàn tất và transaction commit.

## 17. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Truy vấn không chạy | Chỉ tạo `Mono`/`Flux` nhưng không có subscriber | Trả publisher cho WebFlux hoặc subscribe tại ranh giới tiêu thụ hợp lệ |
| Repository trả publisher lồng nhau | Dùng `map` khi bước tiếp theo trả `Mono`/`Flux` | Dùng `flatMap` hoặc `flatMapMany` |
| Lưu dữ liệu nhưng response không đợi kết quả | Gọi `.subscribe()` riêng trong service | Trả publisher và nối các bước bằng operator |
| Event-loop bị chặn | Gọi `block()` hoặc API imperative trong pipeline | Dùng reactive API từ đầu đến cuối |
| Cùng publisher chạy truy vấn nhiều lần | Có nhiều subscription vào publisher cold | Chỉ tạo một pipeline hoặc chia sẻ/cache có chính sách rõ ràng |
| Lỗi bị mất khỏi request | Tự subscribe và không nối error signal với caller | Dùng `onErrorResume` có chủ đích hoặc để lỗi truyền lên WebFlux |
| Transaction không bao trùm các thao tác | Tạo subscription riêng hoặc thiếu reactive transaction manager | Nối thao tác trong cùng Reactor Context và cấu hình manager |
| Dùng `ThreadLocal` lấy transaction | Áp dụng mô hình imperative cho reactive | Dùng Reactor Context và abstraction transaction của Spring |
| Bộ nhớ tăng khi đọc nhiều node | Gom toàn bộ `Flux` bằng `collectList()` | Streaming, phân trang hoặc xử lý theo lô |

## 18. Nguyên tắc cần nhớ

- `Mono<T>` biểu diễn tối đa một phần tử; `Flux<T>` biểu diễn từ không đến nhiều phần tử.
- Repository reactive trả publisher, không trả entity đã được lấy ngay tại thời điểm gọi method.
- Truy vấn reactive được thực thi khi có subscription.
- WebFlux có thể subscribe publisher do controller trả về; không cần tự subscribe trong controller hoặc service.
- Dùng `map` cho biến đổi đồng bộ, `flatMap` để nối thao tác trả publisher, `then` để nối theo tín hiệu hoàn tất và `zip` để kết hợp nguồn độc lập.
- Publisher cold có thể thực thi lại nguồn cho mỗi subscription; cache/share chỉ dùng khi semantics và thời hạn dữ liệu đã rõ.
- Tránh `block()` trong reactive pipeline và không xem scheduler là cách biến API blocking thành non-blocking.
- Dùng cancellation, backpressure, giới hạn truy vấn và phân trang để kiểm soát luồng dữ liệu lớn.
- Reactive transaction dùng Reactor Context, không dùng thread-bound resource; các thao tác cần cùng transaction phải nằm trong cùng pipeline/context.
- Dùng `StepVerifier` để kiểm thử subscription và các tín hiệu reactive.

Khi làm việc với Spring Data Neo4j reactive, hãy coi `Mono` và `Flux` là hợp đồng mô tả công việc và kết quả bất đồng bộ. Chỉ khi publisher được subscribe, truy vấn mới được thực thi và các tín hiệu dữ liệu, lỗi hoặc hoàn tất mới đi qua pipeline. Việc kết hợp publisher thay vì tự subscribe hoặc block giúp giữ đúng cancellation, error handling, backpressure và transaction context của toàn bộ thao tác.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.1.2 – Getting started](https://docs.spring.io/spring-data/neo4j/reference/getting-started.html)
- [Spring Data Neo4j 8.1.2 – FAQ: Reactive configuration and ReactiveNeo4jTemplate](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j 8.1.2 – ReactiveNeo4jRepository API](https://docs.spring.io/spring-data/data-neo4j/reference/api/java/org/springframework/data/neo4j/repository/ReactiveNeo4jRepository.html)
- [Spring Data Neo4j 8.1.2 – ReactiveNeo4jClient API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/ReactiveNeo4jClient.html)
- [Spring Data Neo4j 8.1.2 – ReactiveNeo4jTransactionManager API](https://docs.spring.io/spring-data/data-neo4j/reference/api/java/org/springframework/data/neo4j/core/transaction/ReactiveNeo4jTransactionManager.html)
- [Project Reactor – Mono](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Project Reactor – Flux](https://projectreactor.io/docs/core/release/reference/coreFeatures/flux.html)
- [Project Reactor – Hot Versus Cold](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html)
- [Spring Framework – Reactive Transaction Context](https://docs.spring.io/spring/reference/7.0/data-access/transaction/declarative/tx-decl-explained.html)
