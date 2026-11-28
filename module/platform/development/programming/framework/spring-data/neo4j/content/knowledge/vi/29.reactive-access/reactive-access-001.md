# Phân biệt imperative, asynchronous và reactive API của driver

Khi ứng dụng truy cập Neo4j, cách gọi database ảnh hưởng trực tiếp đến cách luồng xử lý chờ kết quả, tiêu thụ record và quản lý tài nguyên. Neo4j Java Driver cung cấp API đồng bộ (imperative), API bất đồng bộ (asynchronous) và API reactive. Spring Data Neo4j (SDN) xây dựng hai mô hình truy cập ở cấp Spring: imperative và reactive.

Ba khái niệm này có liên quan nhưng không đồng nghĩa:

- **Imperative** gọi thao tác và chờ kết quả ngay trên luồng hiện tại. API trả về entity, danh sách hoặc kết quả thông thường.
- **Asynchronous** khởi chạy thao tác không chặn và biểu diễn kết quả tương lai bằng CompletionStage hoặc CompletableFuture. Mã ứng dụng kết hợp các callback hoặc stage để xử lý khi thao tác hoàn tất.
- **Reactive** mô tả một chuỗi xử lý bằng Publisher. Consumer yêu cầu dữ liệu theo nhu cầu; driver điều tiết việc lấy record để hỗ trợ backpressure.

Trong SDN, mô hình reactive dùng Project Reactor với Mono và Flux, cùng ReactiveNeo4jRepository, ReactiveNeo4jTemplate và ReactiveNeo4jClient. API asynchronous của Driver không có một bộ repository Spring Data riêng tương đương. Vì vậy, khi nói đến truy cập reactive trong SDN, trọng tâm là Reactive Streams và Reactor.

Sau bài học, bạn có thể:

- Phân biệt thao tác đồng bộ, bất đồng bộ và reactive.
- Chọn Session, AsyncSession hoặc ReactiveSession của Neo4j Java Driver.
- Nhận biết CompletionStage, Mono, Flux và Publisher.
- Khai báo reactive repository và xử lý kết quả theo chuỗi Reactor.
- Dùng ReactiveNeo4jTemplate và ReactiveNeo4jClient cho truy vấn tùy chỉnh.
- Cấu hình ReactiveNeo4jTransactionManager và phối hợp nhiều thao tác trong transaction reactive.
- Tránh block, subscribe thủ công và rò rỉ session trong pipeline reactive.

## 1. Ba mô hình xử lý kết quả

Giả sử ứng dụng cần tìm tất cả người dùng ở một thành phố. Cả ba mô hình đều có thể gửi cùng một câu Cypher, nhưng cách nhận kết quả khác nhau:

~~~mermaid
flowchart TD
    Q["MATCH Person theo city"] --> I["Imperative"]
    Q --> A["Asynchronous"]
    Q --> R["Reactive"]
    I --> I1["Chờ kết quả trên luồng gọi"]
    I1 --> I2["List<Person>"]
    A --> A1["Tiếp tục công việc khác"]
    A1 --> A2["CompletionStage / CompletableFuture"]
    R --> R1["Publisher chờ subscriber"]
    R1 --> R2["Flux<Person>"]
    R2 --> R3["Consumer yêu cầu record theo nhu cầu"]
~~~

| Tiêu chí | Imperative | Asynchronous | Reactive |
|---|---|---|---|
| Kiểu API Driver | Session | AsyncSession | ReactiveSession |
| Kiểu kết quả phổ biến | Giá trị trực tiếp, List, Record | CompletionStage, CompletableFuture | Publisher, Mono, Flux |
| Cách xử lý | Gọi rồi chờ | Kết hợp stage/callback | Khai báo chuỗi operator |
| Luồng gọi có bị chờ I/O? | Có | Không cần chờ tại lời gọi | Không cần chờ tại lời gọi |
| Điều tiết tốc độ nhận record | Driver quản lý việc lấy và buffer theo API đồng bộ | Xử lý cursor bất đồng bộ | Consumer điều khiển demand; driver hỗ trợ backpressure |
| Tích hợp SDN | Neo4jRepository, Neo4jTemplate, Neo4jClient | Không có bộ async repository riêng trong SDN | ReactiveNeo4jRepository, ReactiveNeo4jTemplate, ReactiveNeo4jClient |
| Phù hợp khi | Ứng dụng Spring MVC hoặc luồng xử lý tuần tự | Cần phối hợp các tác vụ không chặn qua CompletionStage | Ứng dụng dùng Reactive Streams từ đầu đến cuối |

API reactive không mặc nhiên làm một câu Cypher chạy nhanh hơn. Nó thay đổi cách ứng dụng sử dụng tài nguyên khi chờ I/O và tiêu thụ kết quả. Tốc độ thực tế vẫn phụ thuộc vào kế hoạch Cypher, index, số lượng record, độ trễ mạng và công việc xử lý sau truy vấn.

## 2. Imperative: gọi và nhận kết quả trực tiếp

API đồng bộ của Java Driver sử dụng Session. Khi gọi query và đọc kết quả, luồng hiện tại chờ cho đến khi driver nhận được dữ liệu cần thiết.

~~~java
import java.util.List;
import java.util.Map;

import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

public List<String> findPersonNames(Driver driver, String city) {
    try (Session session = driver.session()) {
        return session.executeRead(tx ->
            tx.run(
                """
                MATCH (p:Person {city: $city})
                RETURN p.name AS name
                ORDER BY name
                """,
                Map.of("city", city)
            )
            .list(record -> record.get("name").asString())
        );
    }
}
~~~

Ví dụ dùng managed read transaction của Driver. Session được đóng bằng try-with-resources sau khi công việc hoàn tất. Giá trị trả về là List<String>; phương thức chỉ trả quyền điều khiển cho caller sau khi thao tác đọc đã xong.

Ở cấp SDN, mô hình imperative thường dùng:

- Neo4jRepository với các phương thức trả entity, Optional hoặc collection.
- Neo4jTemplate với các phương thức trả entity hoặc List.
- Neo4jClient với kết quả được lấy theo API đồng bộ.

Ví dụ repository:

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository
        extends Neo4jRepository<Person, Long> {

    Optional<Person> findByEmail(String email);

    List<Person> findByCity(String city);
}
~~~

Mô hình imperative đơn giản để đọc và gỡ lỗi. Điểm cần cân nhắc là mỗi thao tác I/O sẽ giữ luồng gọi trong thời gian chờ kết quả. Trong ứng dụng có nhiều request đồng thời, số luồng chờ database là một yếu tố cần quản lý.

## 3. Asynchronous: dùng CompletionStage với AsyncSession

API asynchronous của Neo4j Java Driver sử dụng AsyncSession. Các thao tác như chạy truy vấn hoặc thực thi transaction trả về CompletionStage. Mã gọi có thể tiếp tục công việc khác và kết hợp các stage bằng thenApply, thenCompose hoặc whenComplete.

Ví dụ dưới đây chạy một truy vấn đọc và xử lý record khi cursor sẵn sàng:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.Map;

import org.neo4j.driver.Driver;
import org.neo4j.driver.async.AsyncSession;

public CompletionStage<List<String>> findPeople(Driver driver, String city) {
    AsyncSession session = driver.session(AsyncSession.class);

    CompletionStage<List<String>> work = session.executeReadAsync(tx ->
        tx.runAsync(
            """
            MATCH (p:Person {city: $city})
            RETURN p.name AS name
            """,
            Map.of("city", city)
        ).thenCompose(cursor -> {
            List<String> names = new ArrayList<>();
            return cursor.forEachAsync(record ->
                names.add(record.get("name").asString())
            ).thenApply(summary -> names);
        })
    );

    return work.handle((names, error) ->
        session.closeAsync().thenApply(ignored -> {
            if (error != null) {
                throw new CompletionException(error);
            }
            names.forEach(System.out::println);
            return names;
        })
    ).thenCompose(stage -> stage);
}
~~~

Các điểm cần chú ý:

- AsyncSession được tạo bằng Driver với kiểu session AsyncSession.
- executeReadAsync chạy transaction đọc được quản lý bởi Driver.
- runAsync trả về CompletionStage chứa cursor kết quả.
- forEachAsync xử lý record khi cursor cung cấp dữ liệu; ví dụ gom tên vào một danh sách cục bộ để trả về sau transaction.
- Session cần được đóng bằng closeAsync khi chuỗi công việc hoàn tất, kể cả khi có lỗi; ví dụ chờ luôn stage đóng session trước khi trả kết quả.

Không gọi get() hoặc join() trên CompletableFuture ngay trong luồng xử lý nếu mục tiêu là tránh chờ đồng bộ; các lời gọi đó sẽ biến thao tác asynchronous thành chờ blocking. Hãy kết hợp stage bằng thenApply, thenCompose, exceptionally hoặc whenComplete.

Asynchronous không đồng nghĩa với reactive. CompletionStage biểu diễn một kết quả tương lai, nhưng không cung cấp hợp đồng demand theo Reactive Streams để consumer yêu cầu từng lượng record. Driver có API cursor bất đồng bộ để xử lý kết quả theo từng record; tuy vậy, kiểu composition vẫn là CompletionStage và callback.

Trong Java 21 trở lên, tài liệu Neo4j cũng đề cập async API như một lựa chọn phù hợp với virtual threads. Khi chọn mô hình, hãy cân nhắc cả cấu trúc ứng dụng và khả năng vận hành thay vì chỉ dựa vào nhãn non-blocking.

Các transaction function được quản lý như **executeReadAsync** và **executeWriteAsync** có thể được Driver chạy lại khi gặp lỗi tạm thời. Vì vậy, tránh thực hiện side effect bên ngoài database bên trong callback, chẳng hạn gửi email hoặc phát message không có cơ chế chống trùng. Hãy thực hiện sau khi transaction hoàn tất hoặc thiết kế thao tác có tính idempotent.

## 4. Reactive: mô tả luồng dữ liệu bằng Publisher

Reactive API của Neo4j Java Driver sử dụng ReactiveSession và trả về Publisher theo Reactive Streams. Trong hệ sinh thái Spring, Project Reactor cung cấp hai kiểu thường dùng:

Driver có hai biến thể reactive: package **org.neo4j.driver.reactivestreams** triển khai Reactive Streams và tích hợp với Reactor; package **org.neo4j.driver.reactive** dùng Java Flow API như **Flow.Publisher**. SDN sử dụng mô hình Reactive Streams/Project Reactor trong các API reactive của Spring.

| Kiểu | Số phần tử | Ý nghĩa |
|---|---:|---|
| Mono<T> | 0 hoặc 1 | Một kết quả hoặc không có kết quả |
| Flux<T> | 0 đến nhiều | Một luồng kết quả có thể gồm nhiều phần tử |

Ví dụ, một người theo email phù hợp với Mono<Person>; danh sách người theo thành phố phù hợp với Flux<Person>.

Một Publisher chỉ mô tả công việc cần thực hiện. Query reactive chỉ bắt đầu khi có subscriber đăng ký. Trong WebFlux, framework thường subscribe cho ứng dụng khi xử lý request. Trong test, StepVerifier có thể subscribe và kiểm tra tín hiệu.

Reactive Streams có cơ chế backpressure. Consumer phát tín hiệu demand để cho biết nó sẵn sàng nhận bao nhiêu phần tử; driver điều tiết việc yêu cầu record từ server theo tốc độ tiêu thụ. Điều này hữu ích khi kết quả lớn hoặc xử lý từng record mất thời gian, vì ứng dụng không phải nhận và giữ trước toàn bộ kết quả.

## 5. Dùng ReactiveNeo4jRepository

SDN cung cấp ReactiveNeo4jRepository cho mô hình reactive. Interface này kế thừa các hợp đồng reactive của Spring Data, bao gồm ReactiveCrudRepository, ReactiveSortingRepository và ReactiveQueryByExampleExecutor.

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import org.springframework.data.neo4j.repository.ReactiveNeo4jRepository;

public interface ReactivePersonRepository
        extends ReactiveNeo4jRepository<Person, Long> {

    Mono<Person> findByEmail(String email);

    Flux<Person> findByCity(String city);
}
~~~

Các phương thức kế thừa cũng trả về kiểu reactive:

- findById(id) trả Mono<Person>.
- findAll() trả Flux<Person>.
- save(person) trả Mono<Person>.
- saveAll(entities) trả Flux<Person>.
- deleteById(id) trả Mono<Void>.
- count() trả Mono<Long>.

Ví dụ service tìm kiếm theo thành phố:

~~~java
import reactor.core.publisher.Flux;

import org.springframework.stereotype.Service;

@Service
public class PersonQueryService {

    private final ReactivePersonRepository personRepository;

    public PersonQueryService(ReactivePersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    public Flux<PersonSummary> findByCity(String city) {
        return personRepository.findByCity(city)
            .map(person -> new PersonSummary(
                person.getPersonCode(),
                person.getName(),
                person.getCity()
            ));
    }
}
~~~

Phương thức trả Flux cho caller. Không cần gọi subscribe() trong service và không cần chuyển kết quả thành List chỉ để trả cho controller. Nếu controller WebFlux trả Flux<PersonSummary>, framework có thể tiêu thụ luồng dữ liệu theo mô hình reactive.

## 6. Kết hợp nhiều thao tác bằng Reactor

Trong mô hình imperative, mã thường gọi repository, nhận entity rồi tiếp tục gọi thao tác tiếp theo. Trong reactive, hãy nối các Publisher bằng operator như flatMap, map, then, zip hoặc switchIfEmpty.

Ví dụ tạo hồ sơ rồi ghi một sự kiện bằng ReactiveNeo4jClient:

~~~java
import reactor.core.publisher.Mono;

import org.springframework.data.neo4j.core.ReactiveNeo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonRegistrationService {

    private final ReactivePersonRepository personRepository;
    private final ReactiveNeo4jClient neo4jClient;

    public PersonRegistrationService(
            ReactivePersonRepository personRepository,
            ReactiveNeo4jClient neo4jClient) {
        this.personRepository = personRepository;
        this.neo4jClient = neo4jClient;
    }

    @Transactional
    public Mono<Person> register(Person person) {
        return personRepository.save(person)
            .flatMap(saved ->
                neo4jClient.query("""
                    MATCH (p:Person {personCode: $personCode})
                    CREATE (p)-[:HAS_EVENT]->(
                        :PersonEvent {eventType: $eventType}
                    )
                    """)
                    .bind(saved.getPersonCode()).to("personCode")
                    .bind("REGISTERED").to("eventType")
                    .run()
                    .thenReturn(saved)
            );
    }
}
~~~

Luồng này có các bước:

1. save(person) phát ra Mono<Person>.
2. flatMap nhận entity đã lưu và tạo Publisher cho truy vấn ghi sự kiện.
3. run() trả Mono<ResultSummary>; thao tác ghi chỉ chạy khi có subscriber.
4. thenReturn(saved) đợi truy vấn sự kiện hoàn tất rồi phát lại entity.

Vì phương thức được đánh dấu Transactional và trả về Mono, Spring có thể quản lý transaction reactive bao quanh toàn bộ chuỗi. Nếu thao tác ghi sự kiện lỗi và lỗi thoát ra khỏi chuỗi, transaction có thể rollback cả node Person vừa lưu.

Không gọi subscribe() bên trong register(). Nếu tự subscribe, chuỗi ghi sự kiện sẽ tách khỏi Publisher mà Spring đang quản lý; transaction có thể hoàn tất trước khi công việc tách rời kết thúc và lỗi không được truyền về caller.

## 7. Dùng ReactiveNeo4jTemplate cho truy vấn entity

ReactiveNeo4jTemplate là phiên bản reactive của template SDN. Nó cung cấp thao tác với entity đã ánh xạ mà không bắt buộc phải khai báo repository riêng cho từng loại node.

Ví dụ tìm tất cả người trong một thành phố bằng Cypher:

~~~java
import java.util.Map;

import reactor.core.publisher.Flux;

import org.springframework.data.neo4j.core.ReactiveNeo4jTemplate;
import org.springframework.stereotype.Service;

@Service
public class PersonTemplateService {

    private final ReactiveNeo4jTemplate template;

    public PersonTemplateService(ReactiveNeo4jTemplate template) {
        this.template = template;
    }

    public Flux<Person> findPeopleInCity(String city) {
        return template.findAll(
            """
            MATCH (p:Person)
            WHERE p.city = $city
            RETURN p
            ORDER BY p.name
            """,
            Map.of("city", city),
            Person.class
        );
    }
}
~~~

Một số kiểu kết quả thường gặp của template:

| Phương thức | Kiểu trả về |
|---|---|
| findById(id, Person.class) | Mono<Person> |
| findAll(Person.class) | Flux<Person> |
| findAll(cypher, params, Person.class) | Flux<Person> |
| findOne(cypher, params, Person.class) | Mono<Person> |
| save(person) | Mono<Person> |
| count(Person.class) | Mono<Long> |
| deleteById(id, Person.class) | Mono<Void> |

Các thao tác đều trả Publisher. Đừng giả định rằng chỉ cần gọi phương thức là truy vấn đã được gửi tới Neo4j.

## 8. Kiểm thử Publisher với StepVerifier

Không cần gọi block() để kiểm tra kết quả trong unit test. Reactor Test cung cấp StepVerifier để subscribe, phát tín hiệu demand và xác minh các phần tử cũng như trạng thái hoàn tất:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;

import reactor.test.StepVerifier;

@DataNeo4jTest
class ReactivePersonRepositoryTests {

    @Autowired
    private ReactivePersonRepository personRepository;

    @Test
    void findsPeopleByCity() {
        StepVerifier.create(personRepository.findByCity("Da Nang"))
            .expectNextMatches(person ->
                person.getCity().equals("Da Nang")
            )
            .expectNextCount(1)
            .verifyComplete();
    }
}
~~~

Ví dụ giả định dữ liệu test có đúng hai người ở thành phố Đà Nẵng. Trong test thực tế, hãy chuẩn bị dữ liệu xác định trước khi xác minh số phần tử. StepVerifier cũng hỗ trợ kiểm tra lỗi bằng **expectError** hoặc **expectErrorMatches**.

## 9. Dùng ReactiveNeo4jClient cho kết quả tùy chỉnh

ReactiveNeo4jClient phù hợp khi truy vấn trả về scalar, map hoặc DTO thay vì entity graph. Ví dụ, đọc tên người theo thành phố:

~~~java
import reactor.core.publisher.Flux;

import org.springframework.data.neo4j.core.ReactiveNeo4jClient;
import org.springframework.stereotype.Service;

@Service
public class PersonReadClient {

    private final ReactiveNeo4jClient client;

    public PersonReadClient(ReactiveNeo4jClient client) {
        this.client = client;
    }

    public Flux<String> findNames(String city) {
        return client.query("""
            MATCH (p:Person)
            WHERE p.city = $city
            RETURN p.name AS name
            ORDER BY name
            """)
            .bind(city).to("city")
            .fetchAs(String.class)
            .mappedBy((typeSystem, record) ->
                record.get("name").asString()
            )
            .all();
    }
}
~~~

all() trả Flux với tất cả record. first() trả Mono chứa record đầu tiên nếu có. one() yêu cầu chính xác một record và phát lỗi nếu có nhiều hơn một. Với lệnh ghi không cần đọc record, dùng run() để nhận Mono<ResultSummary>.

ReactiveNeo4jClient chỉ thực thi truy vấn khi Publisher được subscribe. Vì vậy, có thể tạo Publisher trong service, kết hợp nó với thao tác khác và trả về caller mà không chặn luồng.

## 10. Cấu hình reactive transaction manager

Spring Boot tự cấu hình truy cập Neo4j reactive khi Project Reactor có trên classpath. Tuy nhiên, tài liệu Spring Boot hiện hành lưu ý ReactiveTransactionManager không được tự cấu hình trong ứng dụng reactive. Nếu cần dùng transaction annotation hoặc reactive transaction template, hãy khai báo ReactiveNeo4jTransactionManager.

~~~java
import org.neo4j.driver.Driver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.EnableTransactionManagement;

import org.springframework.data.neo4j.core.ReactiveDatabaseSelectionProvider;
import org.springframework.data.neo4j.core.transaction.ReactiveNeo4jTransactionManager;

@Configuration
@EnableTransactionManagement
public class ReactiveNeo4jTransactionConfiguration {

    @Bean
    ReactiveNeo4jTransactionManager reactiveTransactionManager(
            Driver driver,
            ReactiveDatabaseSelectionProvider databaseSelectionProvider) {

        return new ReactiveNeo4jTransactionManager(
            driver,
            databaseSelectionProvider
        );
    }
}
~~~

Trong cấu hình này, transaction manager sử dụng Driver và database selection provider do Spring quản lý. Reactive repository mặc định tìm bean transaction manager tên reactiveTransactionManager; có thể chỉ định tên bean khác bằng transactionManagerRef trong EnableReactiveNeo4jRepositories.

Nếu không dùng Spring Boot, SDN cung cấp AbstractReactiveNeo4jConfig để thiết lập reactive infrastructure. Có thể kế thừa lớp này, cung cấp Driver, bật EnableReactiveNeo4jRepositories và EnableTransactionManagement. Cấu hình trừu tượng tạo các bean reactive cần thiết như ReactiveNeo4jClient, ReactiveNeo4jTemplate và ReactiveNeo4jTransactionManager theo Driver được cung cấp.

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.AuthTokens;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.config.AbstractReactiveNeo4jConfig;
import org.springframework.data.neo4j.repository.config.EnableReactiveNeo4jRepositories;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableReactiveNeo4jRepositories(basePackages = "com.acme.graph.repository")
@EnableTransactionManagement
public class Neo4jReactiveConfiguration extends AbstractReactiveNeo4jConfig {

    @Override
    @Bean
    public Driver driver() {
        return GraphDatabase.driver(
            "bolt://localhost:7687",
            AuthTokens.basic("neo4j", "secret")
        );
    }
}
~~~

Không tạo thêm Driver hoặc ReactiveNeo4jClient riêng nếu không có nhu cầu cấu hình khác biệt. Repository, template, client và transaction manager cần dùng chung hạ tầng Driver phù hợp để tham gia đúng transaction.

## 11. Transaction reactive hoạt động theo Reactor Context

Transaction imperative của Spring thường gắn với thread thực thi. Transaction reactive được truyền qua Reactor Context. Vì vậy, một chuỗi Publisher có thể chuyển qua scheduler mà vẫn giữ ngữ cảnh transaction nếu tiếp tục nằm trong cùng pipeline Reactor.

Ví dụ:

~~~java
@Transactional
public Mono<PurchaseOrder> createOrder(PurchaseOrder order) {
    return orderRepository.save(order)
        .flatMap(saved ->
            eventClient.createOrderEvent(saved.getOrderCode())
                .thenReturn(saved)
        );
}
~~~

Ranh giới transaction tồn tại trong quá trình subscribe và hoàn tất chuỗi Publisher. Các thao tác database bên trong chuỗi sẽ tham gia cùng transaction reactive được Spring quản lý.

Các nguyên tắc cần nhớ:

- Phương thức transactional reactive nên trả về Mono hoặc Flux để Spring quản lý vòng đời transaction.
- Trả Publisher ra ngoài thay vì tự subscribe trong service.
- Không gọi block() trong pipeline của ứng dụng reactive.
- Dùng cùng reactive transaction manager và Driver được cấu hình cho SDN.
- Nếu dùng ReactiveNeo4jClient hoặc ReactiveNeo4jTemplate, hãy để chúng tham gia transaction thông qua hạ tầng Spring.
- Không mở transaction Driver riêng bên trong pipeline nếu muốn thao tác đó rollback cùng transaction Spring.

Có thể dùng TransactionalOperator khi muốn điều khiển ranh giới transaction bằng mã:

~~~java
import org.springframework.transaction.reactive.TransactionalOperator;

public Mono<Person> registerWithOperator(Person person) {
    return personRepository.save(person)
        .flatMap(saved ->
            eventService.writeRegisteredEvent(saved)
                .thenReturn(saved)
        )
        .as(transactionalOperator::transactional);
}
~~~

TransactionalOperator nhận ReactiveTransactionManager đã được cấu hình và bao chuỗi Publisher trong một transaction. Cách này hữu ích khi transaction cần áp dụng cho một đoạn pipeline cụ thể thay vì toàn bộ phương thức.

## 12. Backpressure và quản lý bộ nhớ

Reactive Streams cho phép consumer điều khiển tốc độ nhận record. Khi consumer xử lý chậm, nó không yêu cầu thêm record cho đến khi sẵn sàng. Driver có thể điều tiết việc lấy kết quả từ Neo4j theo nhu cầu này.

Ví dụ, stream dữ liệu qua Flux:

~~~java
public Flux<PersonSummary> streamPeople(String city) {
    return personRepository.findByCity(city)
        .map(this::toSummary);
}
~~~

Không gom toàn bộ kết quả vào List nếu use case cần stream:

~~~java
// Cách này tiêu thụ toàn bộ kết quả vào bộ nhớ trước khi phát ra một List.
public Mono<List<Person>> loadAllPeople() {
    return personRepository.findAll().collectList();
}
~~~

collectList() phù hợp khi tập dữ liệu có giới hạn và caller thật sự cần một collection hoàn chỉnh. Với tập dữ liệu lớn, hãy giữ Flux và xử lý từng phần tử hoặc phân trang ở tầng truy vấn.

Backpressure không giới hạn độ lớn của dữ liệu được tạo bởi một phần tử. Nếu một record chứa object graph rất lớn hoặc ứng dụng tự giữ tất cả phần tử trong cache, bộ nhớ vẫn có thể tăng cao. Hãy giới hạn dữ liệu ở Cypher, chỉ nạp relationship cần thiết và kiểm soát các operator có khả năng buffer.

## 13. Quản lý session và subscription

Khi sử dụng SDN ReactiveNeo4jRepository, ReactiveNeo4jTemplate hoặc ReactiveNeo4jClient, hãy ưu tiên bean do Spring cấu hình để SDN quản lý session, transaction và mapping.

Nếu dùng trực tiếp ReactiveSession của Driver, session phải được tạo và đóng bên trong pipeline. Publisher chỉ chạy khi có subscriber; tạo session trước rồi để Publisher chờ có thể giữ session mở mà chưa thực hiện query.

Driver minh họa cách quản lý tài nguyên reactive bằng usingWhen:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import org.neo4j.driver.Record;
import org.neo4j.driver.Driver;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.reactivestreams.ReactiveResult;
import org.neo4j.driver.reactivestreams.ReactiveSession;

// driver được inject từ Spring.
Flux<Record> records = Flux.usingWhen(
    Mono.fromSupplier(() -> driver.session(
        ReactiveSession.class,
        SessionConfig.builder().build()
    )),
    session -> Mono.fromDirect(
        session.run("MATCH (p:Person) RETURN p.name AS name")
    ).flatMapMany(ReactiveResult::records),
    ReactiveSession::close
);
~~~

usingWhen gắn việc tạo session, thực thi query và đóng session vào cùng vòng đời Publisher. Khi kết thúc, có lỗi hoặc bị hủy, cleanup được thực hiện theo các callback tài nguyên tương ứng. Với ứng dụng SDN thông thường, không cần tự quản lý session theo cách này vì ReactiveNeo4jClient và ReactiveNeo4jTemplate đã đảm nhiệm phần đó.

## 14. Chọn mô hình phù hợp

| Bối cảnh ứng dụng | Gợi ý |
|---|---|
| Spring MVC, CRUD tuần tự, đội ngũ quen mã đồng bộ | Imperative repository và Neo4jTemplate |
| Ứng dụng cần phối hợp tác vụ bất đồng bộ bằng CompletionStage | Neo4j Java Driver AsyncSession |
| Spring WebFlux và pipeline Reactor từ HTTP đến database | ReactiveNeo4jRepository, ReactiveNeo4jTemplate và ReactiveNeo4jClient |
| Kết quả lớn cần được tiêu thụ dần theo tốc độ consumer | Reactive API với Flux và backpressure |
| Ứng dụng imperative chạy trên Java 21+ và muốn đánh giá virtual threads | So sánh sync/async API với tải thực tế |

Tài liệu Neo4j khuyến nghị reactive API cho ứng dụng đã xây dựng theo phong cách reactive và có nhu cầu của reactive workflow. Với các trường hợp còn lại, sync hoặc async API thường là lựa chọn phù hợp; async cũng được nhắc đến như một lựa chọn tốt khi dùng virtual threads trên Java 21 trở lên.

Không nên chuyển sang reactive chỉ vì cho rằng mọi ứng dụng sẽ nhanh hơn. Nếu toàn bộ stack đang imperative, thêm một số Mono hoặc Flux vào giữa không tự động làm các lời gọi blocking trở thành non-blocking. Hãy chọn một mô hình nhất quán từ tầng web, service đến data access.

Spring Data Neo4j không khuyến nghị trộn imperative và reactive database access trong cùng một ứng dụng. Khi có nhu cầu chuyển đổi từ hệ thống cũ, hãy giữ ranh giới rõ ràng và tránh gọi imperative repository từ reactive event loop.

## 15. Những lỗi thường gặp

**Nhầm asynchronous với reactive.** CompletionStage biểu diễn kết quả tương lai; Reactive Streams bổ sung Publisher và demand/backpressure. Hai mô hình có cách composition khác nhau.

**Dùng imperative repository trong WebFlux.** Repository đồng bộ sẽ chặn luồng đang xử lý request. Hãy dùng ReactiveNeo4jRepository trong pipeline reactive.

**Gọi block() trong request pipeline.** block() chờ kết quả và làm mất lợi ích non-blocking. Hãy trả Mono hoặc Flux cho framework.

**Gọi subscribe() trong service.** Việc này tạo một subscription tách rời khỏi luồng mà caller đang quản lý. Hãy trả Publisher để caller quyết định thời điểm thực thi.

**Tạo reactive session trước khi Publisher được subscribe.** Session có thể bị giữ mà chưa có query chạy. Hãy để session được tạo và đóng trong pipeline hoặc dùng SDN client/template.

**Gom Flux thành List quá sớm.** collectList() giữ toàn bộ kết quả trong bộ nhớ. Dùng Flux khi cần stream và xử lý từng record.

**Thiếu ReactiveNeo4jTransactionManager.** Spring Boot có thể cấu hình reactive access khi Reactor có trên classpath, nhưng reactive transaction manager cần được khai báo rõ theo cấu hình hiện hành.

**Gọi Driver trực tiếp ngoài transaction SDN.** Một session reactive hoặc async tự mở không tự động tham gia transaction Spring đang quản lý. Dùng ReactiveNeo4jClient hoặc query runner được gắn với transaction hiện tại.

**Trộn hai mô hình truy cập trong cùng đường xử lý.** Gọi blocking repository từ reactive pipeline có thể chiếm event loop. Hãy dùng reactive API xuyên suốt hoặc giữ phần imperative ở ranh giới riêng có kiểm soát.

## 16. Tự kiểm tra

1. Imperative, asynchronous và reactive khác nhau ở cách biểu diễn kết quả như thế nào?
2. AsyncSession trả về kiểu dữ liệu nào cho các thao tác bất đồng bộ?
3. Mono và Flux khác nhau về số phần tử ra sao?
4. Backpressure giúp kiểm soát luồng record từ Neo4j đến consumer như thế nào?
5. Vì sao SDN có ReactiveNeo4jRepository nhưng không có bộ AsyncNeo4jRepository tương đương?
6. Khi nào nên dùng ReactiveNeo4jTemplate hoặc ReactiveNeo4jClient thay cho repository?
7. Vì sao ReactiveNeo4jTransactionManager cần được cấu hình riêng trong Spring Boot?
8. Vì sao không nên gọi block() hoặc subscribe() trong service reactive?
9. Vì sao cần tạo và đóng ReactiveSession trong cùng vòng đời Publisher?
10. Khi nào async API với CompletionStage có thể phù hợp hơn reactive API?

**Bài tập thực hành:** Xây dựng ứng dụng quản lý Person với ba phiên bản truy cập. Phiên bản thứ nhất dùng Neo4jRepository và trả List<Person>. Phiên bản thứ hai dùng AsyncSession và CompletionStage để xử lý kết quả sau khi query hoàn tất. Phiên bản thứ ba dùng ReactiveNeo4jRepository để trả Flux<Person> theo thành phố và Mono<Person> theo email. Mở rộng phiên bản reactive bằng ReactiveNeo4jClient để ghi một event trong cùng phương thức @Transactional. Dùng StepVerifier kiểm tra kết quả, trường hợp không tìm thấy, lỗi truy vấn và xác minh transaction rollback khi bước ghi event thất bại. Cuối cùng, so sánh cách quản lý luồng record, session và bộ nhớ giữa ba phiên bản.

## Tài liệu tham khảo

- [Spring Data Neo4j — Getting Started: imperative and reactive models](https://docs.spring.io/spring-data/neo4j/reference/getting-started.html)
- [Spring Data Neo4j API — ReactiveNeo4jRepository](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/ReactiveNeo4jRepository.html)
- [Spring Data Neo4j API — ReactiveNeo4jTemplate](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/ReactiveNeo4jTemplate.html)
- [Spring Data Neo4j API — ReactiveNeo4jClient](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/ReactiveNeo4jClient.html)
- [Spring Data Neo4j API — EnableReactiveNeo4jRepositories](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/config/EnableReactiveNeo4jRepositories.html)
- [Spring Boot — Working with Neo4j and reactive transaction configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Neo4j Java Driver Manual — Control results flow with reactive streams](https://neo4j.com/docs/java-manual/current/reactive/)
- [Neo4j Java Driver Manual — Run non-blocking asynchronous queries](https://neo4j.com/docs/java-manual/current/async/)
