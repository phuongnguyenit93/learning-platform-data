# Phân biệt lỗi, hoàn thành và hủy subscription đối với giao dịch

Trong Spring Data Neo4j (SDN) reactive, một transaction không kết thúc ngay khi method service trả về `Mono` hoặc `Flux`. Publisher chỉ mô tả công việc; transaction thực sự được mở và thực thi khi có subscriber tiêu thụ publisher. Kết quả cuối cùng phụ thuộc vào tín hiệu mà transaction boundary quan sát được: hoàn thành (`onComplete`), lỗi (`onError`) hay hủy subscription (`cancel`).

Ba tín hiệu này có ý nghĩa khác nhau. Hoàn thành bình thường cho phép commit; lỗi đi vào quy tắc rollback của cơ chế quản lý transaction; cancellation khiến Spring rollback từ phiên bản 5.3 vì transaction chưa được xác nhận hoàn tất. Một số operator Reactor như `take`, `next` và `timeout` có thể phát sinh cancellation mà code gọi không nhận ra. Hiểu rõ thứ tự operator quanh transaction boundary là điều cần thiết để tránh commit dữ liệu dở dang hoặc rollback ngoài dự kiến.

## 1. Transaction reactive bắt đầu khi publisher được subscribe

Một method reactive thường trả về publisher mà chưa chạy câu lệnh Cypher:

```java
@Transactional
public Mono<Void> register(Person person) {
    return personRepository.save(person)
        .flatMap(saved -> auditRepository.recordCreated(saved.getId()))
        .then();
}
```

Khi gọi `register(person)`, Spring tạo publisher có ranh giới transaction. Khi subscriber subscribe publisher được trả về, Spring mới mở transaction và thực thi các thao tác reactive trong Reactor chain. Khi chain kết thúc, Spring xử lý transaction theo tín hiệu kết thúc.

Điều này dẫn tới ba hệ quả:

- Nếu publisher không bao giờ được subscribe, các thao tác database chưa chạy và transaction chưa được mở.
- Mỗi lần subscribe vào một publisher reactive lạnh có thể thực thi lại các thao tác và tạo một transaction mới. Không subscribe lặp ngoài ý muốn với publisher ghi dữ liệu.
- Transaction reactive được gắn với Reactor Context. Các thao tác cần cùng transaction phải nằm trong cùng chain và giữ được context đó.

Với SDN, repository reactive thường kế thừa `ReactiveNeo4jRepository`; các thao tác repository, `ReactiveNeo4jTemplate` và `ReactiveNeo4jClient` có thể tham gia transaction do `ReactiveNeo4jTransactionManager` quản lý.

## 2. Ba tín hiệu kết thúc và kết quả transaction

Reactive Streams định nghĩa hai tín hiệu terminal là `onComplete` và `onError`; `cancel` là yêu cầu từ subscriber để dừng publisher. Transaction boundary của Spring phản ứng với cả ba trạng thái:

| Tín hiệu transaction boundary nhận được | Ý nghĩa | Kết quả thông thường |
|---|---|---|
| `onComplete` | Chuỗi công việc hoàn tất bình thường | Commit, trừ khi transaction đã được đánh dấu rollback-only |
| `onError` | Chuỗi công việc kết thúc bằng lỗi | Rollback theo rollback rule của transaction; `TransactionalOperator` thực hiện rollback khi lỗi được truyền tới nó |
| `cancel` | Subscriber dừng tiêu thụ trước khi publisher hoàn tất | Rollback từ Spring Framework 5.3 trở lên |

Với `Mono<T>`, một kết quả thành công thường phát `onNext(value)` rồi `onComplete`. Với `Mono<Void>`, không có `onNext`; tín hiệu `onComplete` biểu thị công việc hoàn tất. Với `Flux<T>`, publisher có thể phát nhiều `onNext` trước khi phát `onComplete`.

Nhận được một hoặc nhiều phần tử `onNext` không có nghĩa transaction đã commit. Chỉ khi transaction boundary nhận được tín hiệu hoàn tất phù hợp và quá trình commit thành công, thay đổi mới được xác nhận.

## 3. onComplete — hoàn thành bình thường và commit

Khi toàn bộ thao tác trong chain hoàn tất bình thường, publisher phát `onComplete`. Spring gọi commit trên reactive transaction manager, trừ khi transaction đã được đánh dấu rollback-only hoặc quá trình commit gặp lỗi.

Ví dụ service lưu node và ghi audit trong cùng transaction:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class PersonRegistrationService {
    private final PersonRepository personRepository;
    private final AuditRepository auditRepository;

    public PersonRegistrationService(
            PersonRepository personRepository,
            AuditRepository auditRepository) {
        this.personRepository = personRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public Mono<Void> register(Person person) {
        return personRepository.save(person)
            .flatMap(saved -> auditRepository.recordCreated(saved.getId()))
            .then();
    }
}
```

Giả sử `recordCreated` trả về `Mono<Void>` và dùng cùng reactive transaction manager. Khi lưu người và ghi audit đều thành công, chain phát `onComplete`; transaction được commit. `.then()` chờ publisher ghi audit hoàn tất rồi mới phát completion.

Không dùng `subscribe()` bên trong method service để chạy một phần công việc rồi trả về publisher khác. Publisher được tách ra có thể chạy ngoài transaction hoặc chạy sau khi transaction đã hoàn tất.

## 4. onError — lỗi được truyền tới transaction boundary

Khi một thao tác phát `onError`, chain kết thúc bằng lỗi. Với `@Transactional`, Spring áp dụng rollback rule của annotation. Mặc định, `RuntimeException` và `Error` kích hoạt rollback; checked exception không kích hoạt rollback theo mặc định. Có thể khai báo `rollbackFor` cho checked exception cần rollback.

```java
@Transactional
public Mono<Void> register(Person person) {
    return personRepository.save(person)
        .flatMap(saved -> auditRepository.recordCreated(saved.getId()))
        .then(Mono.error(new IllegalStateException("Audit validation failed")));
}
```

`IllegalStateException` là unchecked exception. Khi lỗi được truyền ra khỏi publisher của method, transaction interceptor nhận lỗi và rollback những thay đổi thuộc transaction đó.

Nếu lỗi là checked exception:

```java
import java.io.IOException;

@Transactional(rollbackFor = IOException.class)
public Mono<Void> importPerson(Person person) {
    return personRepository.save(person)
        .then(Mono.error(new IOException("Invalid import record")));
}
```

Khi dùng `@Transactional`, cần kiểm tra rollback rule của phiên bản Spring Framework đang chạy. Spring Framework 6.2 trở lên còn hỗ trợ cấu hình mặc định rollback với tất cả exception qua `@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)`; cấu hình này áp dụng ở cấp transaction annotation infrastructure.

Với `TransactionalOperator`, khi lỗi được truyền tới operator, operator thực hiện rollback path. Nếu cần xử lý lỗi nghiệp vụ nhưng vẫn rollback, có thể đánh dấu rollback-only trong callback trước khi khôi phục kết quả.

## 5. Phân biệt doOnError, onErrorMap và onErrorResume

Các operator xử lý lỗi không có cùng tác động tới tín hiệu mà transaction boundary nhận được:

| Operator | Hành vi | Transaction boundary thường nhận |
|---|---|---|
| `doOnError` | Chỉ quan sát/log lỗi, không tiêu thụ lỗi | `onError` |
| `onErrorMap` | Đổi exception sang loại khác rồi truyền tiếp | `onError` với exception mới |
| `onErrorResume` | Chuyển sang publisher thay thế | Có thể là `onComplete` nếu publisher thay thế hoàn tất bình thường |
| `onErrorReturn` | Thay lỗi bằng một giá trị thành công | `onComplete` sau giá trị thay thế |
| `onErrorComplete` | Biến lỗi thành completion | `onComplete` |

`doOnError` phù hợp để ghi log hoặc metric mà không thay đổi outcome:

```java
return writePerson(person)
    .doOnError(error -> log.error("Person write failed", error))
    .as(transactionalOperator::transactional);
```

`onErrorMap` vẫn truyền lỗi tới transaction boundary:

```java
return writePerson(person)
    .onErrorMap(
        Neo4jException.class,
        error -> new PersonPersistenceException("Cannot save person", error)
    )
    .as(transactionalOperator::transactional);
```

Ngược lại, `onErrorResume` có thể làm transaction boundary thấy một completion bình thường. Vị trí đặt operator quyết định transaction có nhìn thấy lỗi hay không; phần tiếp theo giải thích cụ thể.

## 6. onErrorResume bên trong hay bên ngoài transaction boundary

Hai đoạn code dưới đây có semantics khác nhau.

### Khôi phục lỗi bên trong transaction

```java
Mono<Void> result = writePerson(person)
    .onErrorResume(BusinessRuleException.class, error -> {
        log.warn("Registration rejected: {}", error.getMessage());
        return Mono.empty();
    })
    .as(transactionalOperator::transactional);
```

`onErrorResume` nằm trước transaction boundary. Khi xảy ra `BusinessRuleException`, operator thay lỗi bằng `Mono.empty()`. Transactional operator nhận `onComplete`, do đó đi theo nhánh commit nếu transaction chưa bị đánh dấu rollback-only và database vẫn cho phép commit.

Điều này có thể đúng nếu lỗi chỉ là một trường hợp nghiệp vụ được chấp nhận và các thay đổi trước đó cần được giữ. Nhưng nếu đã ghi một phần dữ liệu và yêu cầu rollback toàn bộ, không được chỉ nuốt lỗi rồi trả `Mono.empty()`.

### Khôi phục lỗi sau transaction boundary

```java
Mono<Void> result = writePerson(person)
    .as(transactionalOperator::transactional)
    .onErrorResume(BusinessRuleException.class, error -> {
        log.warn("Registration rolled back: {}", error.getMessage());
        return Mono.empty();
    });
```

Ở đây `TransactionalOperator` nhận lỗi trước. Nó rollback transaction rồi mới truyền lỗi xuống `onErrorResume` phía sau. Publisher cuối cùng có thể hoàn tất bình thường để caller nhận kết quả fallback, nhưng transaction đã rollback.

Với method `@Transactional`, quy tắc tương tự áp dụng theo ranh giới proxy:

- Nếu method service tự `onErrorResume` và trả publisher hoàn tất bình thường, interceptor chỉ nhìn thấy completion.
- Nếu caller đặt `onErrorResume` sau khi gọi method transactional, transaction interceptor đã quan sát lỗi và xử lý rollback trước khi caller khôi phục.

Không nên chọn vị trí dựa trên thói quen. Hãy quyết định rõ lỗi đó có được phép giữ các thay đổi đã thực hiện hay phải rollback toàn bộ.

## 7. Đánh dấu rollback-only khi cần khôi phục kết quả

Đôi khi service cần trả một kết quả nghiệp vụ bình thường nhưng vẫn muốn rollback các thay đổi đã thực hiện. Với `TransactionalOperator`, dùng callback API để đánh dấu transaction rollback-only:

```java
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public Mono<RegistrationResult> register(Person person) {
    return transactionalOperator.execute(status ->
        writePerson(person)
            .thenReturn(RegistrationResult.success())
            .onErrorResume(BusinessRuleException.class, error -> {
                status.setRollbackOnly();
                return Mono.just(RegistrationResult.rejected(error.getMessage()));
            })
    ).single();
}
```

Ở đây lỗi được chuyển thành một `RegistrationResult` để caller có thể xử lý; `setRollbackOnly()` bảo đảm transaction vẫn đi theo nhánh rollback khi callback hoàn tất. `execute(...)` trả về `Flux<T>`, vì vậy `.single()` phù hợp khi callback được thiết kế để phát đúng một kết quả.

Nếu không cần khôi phục lỗi thành kết quả nghiệp vụ, cách đơn giản nhất là để lỗi truyền ra ngoài transaction boundary. Chỉ dùng rollback-only khi có yêu cầu cụ thể về việc trả kết quả bình thường sau khi rollback.

## 8. cancel — subscriber dừng trước khi publisher hoàn tất

Cancellation không phải `onError` và cũng không phải `onComplete`. Subscriber gửi yêu cầu `cancel()` để dừng nhận dữ liệu. Publisher không gửi một terminal signal mới về phía subscriber để giải thích lý do dừng.

Spring Framework xử lý cancellation bằng rollback từ phiên bản 5.3. Lý do là transaction không thể biết subscriber dừng vì đã đủ dữ liệu, vì người dùng không còn quan tâm, vì timeout hay vì một thành phần upstream gặp sự cố. Rollback tạo kết quả xác định: transaction chỉ commit khi publisher hoàn tất đầy đủ.

Các tình huống thường tạo cancellation:

- `take(n)` dừng sau khi nhận đủ n phần tử.
- `next()` chỉ lấy phần tử đầu tiên từ một `Flux`.
- `timeout(...)` dừng upstream khi hết thời gian.
- Client HTTP đóng kết nối trong khi WebFlux đang stream response.
- Subscriber tự gọi `dispose()` hoặc `cancel()`.

Nếu transaction bao quanh một `Flux` nhiều phần tử, cần tiêu thụ toàn bộ output để transaction hoàn tất. Nhận được phần tử đầu tiên không có nghĩa toàn bộ transaction đã commit.

## 9. Operator take và next có thể làm rollback ngoài dự kiến

Giả sử repository trả về `Flux<Person>` và publisher đó đang được bao quanh bởi transaction:

```java
Flux<Person> transactionalPeople = personRepository.findAll()
    .as(transactionalOperator::transactional);

return transactionalPeople.take(10);
```

`take(10)` nằm downstream của transaction publisher. Khi nhận đủ 10 phần tử, nó hủy subscription upstream. Transaction boundary nhận cancellation và rollback theo semantics của Spring Framework 5.3 trở lên.

Tương tự:

```java
return personRepository.findAll()
    .as(transactionalOperator::transactional)
    .next();
```

`next()` chỉ cần một phần tử nên hủy phần còn lại của publisher được bao transaction. Không dùng cách này nếu mục tiêu là đọc toàn bộ stream trong một transaction.

Thứ tự operator cũng quan trọng. Nếu đặt `take(10)` trước transaction boundary:

```java
return personRepository.findAll()
    .take(10)
    .as(transactionalOperator::transactional);
```

Transaction boundary chỉ nhìn thấy publisher `take(10)` hoàn tất bình thường sau 10 phần tử; nó không nhận cancellation mà `take` gửi ngược lên nguồn. Do đó transaction có thể commit phần công việc của publisher đã giới hạn. Với truy vấn chỉ đọc, điều này thường chỉ có nghĩa là đọc 10 phần tử. Với một pipeline ghi nhiều phần tử, đây có thể là một transaction hợp lệ chỉ gồm 10 phần tử đầu, nhưng cần được thiết kế có chủ đích.

Nếu chỉ cần một bản ghi, hãy dùng method repository trả về `Mono<T>`, `findFirst...`, `findById` hoặc query Cypher có `LIMIT 1` thay vì mở transaction cho một `Flux` lớn rồi gọi `next()` ở phía sau.

## 10. timeout và client disconnect

`timeout(Duration)` có thể phát timeout error xuống downstream và hủy subscription upstream. Khi timeout nằm sau transactional publisher, transaction boundary nhận cancellation và rollback:

```java
return writePerson(person)
    .as(transactionalOperator::transactional)
    .timeout(Duration.ofSeconds(3));
```

Tình huống này có hai tín hiệu ở hai phía: downstream có thể nhận `TimeoutException`, còn transaction publisher upstream nhận cancellation. Không chỉ nhìn exception ở controller để suy luận transaction đã commit hay rollback.

Trong WebFlux, một endpoint trả `Flux<T>` có thể giữ transaction mở trong suốt quá trình stream dữ liệu tới client. Nếu client ngắt kết nối trước khi stream hoàn tất, cancellation có thể làm transaction rollback. Tránh dùng một transaction dài để stream dữ liệu lớn cho client; cân nhắc chia batch hoặc kết thúc transaction trước khi truyền dữ liệu ra mạng.

## 11. Đọc hết Flux mà không gom toàn bộ vào bộ nhớ

Nếu cần xử lý mọi phần tử, hãy nối thao tác xử lý vào chain và đợi nguồn hoàn tất. `then()` bỏ qua giá trị phát ra nhưng vẫn chờ publisher hoàn tất:

```java
public Mono<Void> rebuildSearchIndex() {
    return personRepository.findAll()
        .concatMap(person -> searchIndexWriter.update(person))
        .then()
        .as(transactionalOperator::transactional);
}
```

`concatMap` xử lý từng phần tử theo thứ tự và chờ publisher xử lý hiện tại hoàn tất trước khi chuyển sang phần tử kế tiếp. `.then()` chỉ phát completion sau khi toàn bộ nguồn đã hoàn tất. Vì vậy transaction boundary có thể commit sau khi mọi cập nhật chỉ mục đã hoàn tất.

Không dùng `collectList()` chỉ để tránh cancellation nếu tập dữ liệu lớn; operator này giữ toàn bộ kết quả trong bộ nhớ. Nếu cần xử lý rất nhiều bản ghi, hãy chia theo page/window hoặc batch và đặt transaction theo từng batch khi semantics nghiệp vụ cho phép.

## 12. Retry và transaction boundary

Retry có thể tạo subscription mới. Vị trí của `retryWhen` quyết định mỗi lần thử có transaction riêng hay nhiều lần thử nằm trong cùng một transaction.

Đặt retry bên ngoài transaction publisher:

```java
public Mono<Void> saveWithRetry(Person person) {
    return Mono.defer(() -> writePerson(person)
            .as(transactionalOperator::transactional))
        .retryWhen(Retry.max(2)
            .filter(this::isTransientFailure));
}
```

Mỗi lần retry subscribe lại publisher transaction, nên lần thử mới có thể mở transaction mới sau khi lần trước rollback. Dùng `Mono.defer` để tạo lại pipeline cho mỗi subscription.

Nếu đặt retry bên trong transaction boundary:

```java
return writePerson(person)
    .retryWhen(Retry.max(2))
    .as(transactionalOperator::transactional);
```

Các lần thử được thực hiện bên trong cùng transaction boundary. Sau một lỗi database, transaction có thể đã bị đánh dấu rollback hoặc không còn ở trạng thái có thể tiếp tục. Không mặc định rằng retry nội bộ sẽ tạo transaction mới.

Chỉ retry lỗi transient có thể phục hồi. Ghi dữ liệu cần idempotent hoặc có khóa nghiệp vụ để tránh tạo dữ liệu trùng khi lần thử trước đã hoàn tất ở database nhưng client chưa nhận được kết quả xác nhận.

## 13. Quan sát outcome bằng doFinally và doOnCancel

Reactor cung cấp `doFinally` để quan sát loại tín hiệu kết thúc:

```java
return writePerson(person)
    .as(transactionalOperator::transactional)
    .doFinally(signal -> {
        switch (signal) {
            case ON_COMPLETE -> metrics.record("tx.complete");
            case ON_ERROR -> metrics.record("tx.error");
            case CANCEL -> metrics.record("tx.cancel");
        }
    });
```

`doFinally` hữu ích cho log và metric vì nó phân biệt completion, error và cancel. Callback này chỉ quan sát tín hiệu; nó không thay đổi kết quả transaction và không thay thế `setRollbackOnly()`.

Có thể dùng `doOnCancel` để ghi nhận cancellation riêng:

```java
return repository.findAll()
    .as(transactionalOperator::transactional)
    .doOnCancel(() -> log.warn("Person stream was cancelled"));
```

Không gọi thao tác ghi database mới trong `doFinally` hoặc `doOnCancel` rồi kỳ vọng chúng nằm trong transaction vừa kết thúc. Transaction đã đi vào giai đoạn hoàn tất hoặc cleanup.

## 14. Kiểm thử completion, error và cancellation

Với reactive code, `StepVerifier` giúp điều khiển subscription và terminal signal. Test cần xác minh cả tín hiệu downstream và trạng thái graph sau khi transaction kết thúc.

### Kiểm thử completion dẫn tới commit

```java
StepVerifier.create(service.register(person))
    .verifyComplete();

StepVerifier.create(personRepository.findById(person.getId()))
    .expectNextCount(1)
    .verifyComplete();
```

Test này xác nhận publisher hoàn tất và node đã được lưu. Trong test thực tế, cần truy vấn trạng thái audit để xác nhận cả nhóm thay đổi cùng commit.

### Kiểm thử error dẫn tới rollback

```java
StepVerifier.create(service.registerAndFail(person))
    .expectError(IllegalStateException.class)
    .verify();

StepVerifier.create(personRepository.findById(person.getId()))
    .verifyComplete();
```

`registerAndFail` cần phát sinh unchecked exception sau thao tác ghi nhưng trước khi transaction hoàn tất. Sau khi publisher kết thúc bằng lỗi, truy vấn lại để xác nhận node không tồn tại.

### Kiểm thử cancellation

```java
StepVerifier.create(service.writeManyAndStream())
    .thenRequest(1)
    .expectNextCount(1)
    .thenCancel()
    .verify();
```

Sau cancellation, kiểm tra database để xác nhận các thay đổi thuộc transaction đã rollback. Không chỉ kiểm tra rằng subscriber đã dừng nhận dữ liệu; cần xác minh trạng thái Neo4j sau cleanup.

### Kiểm thử lỗi được khôi phục

Viết hai test cho hai vị trí `onErrorResume`:

1. Khôi phục lỗi bên trong transaction và xác nhận completion đi vào commit path.
2. Khôi phục lỗi bên ngoài transaction và xác nhận transaction đã rollback trước khi fallback được phát ra.

Đây là cách kiểm tra dễ phát hiện lỗi do đặt operator sai vị trí.

## 15. Bảng quyết định cho các operator phổ biến

| Operator/tình huống | Tín hiệu transaction boundary có thể nhận | Lưu ý |
|---|---|---|
| `doOnError` | `onError` | Chỉ log/metric; không tiêu thụ lỗi |
| `onErrorMap` | `onError` | Lỗi vẫn được truyền tiếp; rollback rule vẫn áp dụng |
| `onErrorResume` trước boundary | `onComplete` nếu fallback hoàn tất | Transaction có thể commit nếu không rollback-only |
| `onErrorResume` sau boundary | Boundary đã nhận lỗi trước đó | Fallback chạy sau khi transaction xử lý rollback |
| `onErrorComplete` trước boundary | `onComplete` | Không còn lỗi để boundary xử lý |
| `take(n)` sau boundary | `cancel` khi đủ n phần tử | Rollback từ Spring 5.3+ |
| `next()` sau boundary | `cancel` sau phần tử đầu | Rollback từ Spring 5.3+ |
| `timeout()` sau boundary | `cancel` tới upstream transaction | Transaction rollback; downstream thường nhận timeout error |
| Subscriber tiêu thụ hết `Flux` | `onComplete` | Commit nếu không rollback-only |
| Subscriber tự cancel | `cancel` | Rollback từ Spring 5.3+ |
| `retryWhen` ngoài boundary | Mỗi lần thử resubscribe transaction publisher | Mỗi lần thử có thể dùng transaction mới |

## 16. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ghi một phần rồi vẫn commit | `onErrorResume` đã nuốt lỗi trước transaction boundary | Để lỗi truyền ra, chuyển recovery ra ngoài boundary hoặc gọi rollback-only |
| Chỉ đọc một phần Flux nhưng transaction rollback | `take`/`next` gây cancellation downstream | Dùng query có giới hạn trả `Mono`/`Flux` hữu hạn hoặc tiêu thụ hết stream |
| Client nhận fallback nhưng dữ liệu đã rollback | `onErrorResume` đặt sau transaction boundary | Đây là semantics hợp lệ; phân biệt kết quả API với outcome database |
| Checked exception không rollback | `@Transactional` dùng rollback rule mặc định | Khai báo `rollbackFor` hoặc cấu hình mặc định rollback tất cả exception nếu phiên bản hỗ trợ |
| Timeout gây rollback dù không thấy lỗi database | `timeout` cancel upstream transaction publisher | Đặt timeout phù hợp và hiểu cancellation semantics |
| Retry không phục hồi được transaction | Retry nằm bên trong boundary hoặc transaction đã rollback-only | Đặt retry ngoài transaction để mỗi lần thử có transaction mới |
| Transaction chạy nhưng không hoàn tất | Publisher chưa được subscribe hoặc chain bị tách | Trả publisher từ service và nối toàn bộ thao tác vào chain |
| Metric chỉ ghi nhận lỗi, không phân biệt cancel | Chỉ dùng `doOnError` | Dùng `doFinally` để phân biệt `ON_COMPLETE`, `ON_ERROR`, `CANCEL` |
| WebFlux giữ transaction lâu khi stream response | Transaction bao quanh publisher dài và phụ thuộc tốc độ client | Dùng batch/window hoặc kết thúc transaction trước khi stream ra mạng |

## 17. Quy trình thiết kế transaction reactive an toàn

1. Xác định những thao tác Neo4j nào phải commit hoặc rollback cùng nhau.
2. Đặt `@Transactional` hoặc `TransactionalOperator` quanh đúng publisher chứa các thao tác đó.
3. Quyết định rõ lỗi nào phải rollback; cấu hình rollback rule cho checked exception nếu cần.
4. Không nuốt lỗi trước transaction boundary nếu vẫn cần rollback.
5. Nếu cần trả fallback sau rollback, đặt recovery sau boundary hoặc đánh dấu rollback-only trong callback.
6. Kiểm tra operator có thể cancel như `take`, `next`, `timeout` và vị trí của chúng so với boundary.
7. Với `Flux`, tiêu thụ toàn bộ output nếu muốn transaction hoàn tất bình thường.
8. Đặt retry bên ngoài boundary khi mỗi lần thử cần transaction mới.
9. Dùng `doFinally` để quan sát outcome, không dùng hook quan sát để điều khiển commit/rollback.
10. Kiểm thử completion, error, cancellation và trạng thái graph sau mỗi tình huống.

## 18. Tự kiểm tra

1. Vì sao gọi một method trả về `Mono` chưa có nghĩa transaction đã bắt đầu?
2. Khác biệt giữa `onComplete`, `onError` và `cancel` là gì?
3. Vì sao `onNext` không chứng minh transaction đã commit?
4. `doOnError` khác `onErrorResume` như thế nào đối với tín hiệu mà transaction boundary nhận?
5. Điều gì xảy ra khi `onErrorResume` được đặt trước transaction boundary?
6. Làm thế nào để trả fallback nhưng vẫn rollback transaction?
7. Vì sao `take(10)` sau transactional publisher có thể làm rollback?
8. Vì sao Spring Framework 5.3 thay đổi cách xử lý cancellation thành rollback?
9. Vì sao retry ngoài transaction boundary thường an toàn hơn retry bên trong cùng một transaction?
10. Làm thế nào dùng `doFinally` để phân biệt completion, error và cancellation?

## Tài liệu tham khảo

- [Spring Framework — Programmatic Transaction Management: TransactionalOperator và Cancel Signals](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Framework — Using @Transactional với reactive return types](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Rollback rules cho @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Data Neo4j — Reactive Transactions](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
