# Giới hạn xử lý song song trên cùng session hoặc transaction

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt phạm vi của Neo4j `Driver`, `ReactiveSession` và `ReactiveTransaction`.
- Giải thích vì sao không nên chạy nhiều truy vấn đồng thời trên cùng session hoặc transaction.
- Nhận biết các toán tử Reactor có thể tạo xử lý đồng thời như `flatMap`, `flatMapSequential`, `Mono.zip` và `parallel()`.
- Tuần tự hóa thao tác database bằng `concatMap` khi chúng cần dùng chung một transaction.
- Tạo các transaction độc lập cho những công việc có thể chạy song song và giới hạn số luồng đồng thời.
- Hiểu vai trò của Reactor Context, `@Transactional` và vòng đời session trong ứng dụng Spring Data Neo4j (SDN).

## 1. Vì sao cần giới hạn song song trên cùng session?

Reactive programming cho phép một luồng xử lý nhiều tác vụ bất đồng bộ mà không phải chặn thread để chờ từng kết quả. Trong Project Reactor, các toán tử như `flatMap` hoặc `Mono.zip` có thể đăng ký nhiều publisher con cùng lúc.

Tuy nhiên, khả năng chạy đồng thời của Reactor không có nghĩa một Neo4j session hoặc transaction có thể được nhiều truy vấn sử dụng song song.

Neo4j Java Driver có các ranh giới tài nguyên rõ ràng:

- `Driver` là đối tượng dùng chung an toàn giữa nhiều thread.
- `Session` không thread-safe; không chia sẻ một session cho nhiều luồng công việc đồng thời.
- Một session chỉ có tối đa một transaction đang hoạt động tại một thời điểm.
- Một transaction là một đơn vị công việc có phạm vi riêng; các statement trong cùng transaction phải được điều phối theo một luồng thực thi tuần tự.

Trong reactive API, session và transaction được thao tác qua publisher. Điều đó loại bỏ việc chặn thread, nhưng không làm cho cùng một session/transaction trở thành tài nguyên có thể chạy nhiều truy vấn đồng thời.

Khái niệm transaction bị giới hạn trong một luồng thực thi không có nghĩa phải ép toàn bộ reactive pipeline chạy trên một OS thread cố định. Driver reactive có thể xử lý callback bất đồng bộ trên các thread I/O. Điều cần tránh là nhiều nhánh publisher độc lập cùng điều khiển một session hoặc transaction trong cùng thời điểm.

Ví dụ, một transaction đang cập nhật đơn hàng và tồn kho. Nếu hai nhánh trong cùng transaction cùng sử dụng session để gửi truy vấn một lúc, ứng dụng đang yêu cầu một tài nguyên transaction duy nhất xử lý các thao tác chồng lấn. Đây là cách sử dụng không an toàn và có thể dẫn đến lỗi thực thi hoặc hành vi khó dự đoán.

## 2. Phân biệt Driver, Session và Transaction

Ba đối tượng có vai trò khác nhau:

| Thành phần | Vai trò | Quy tắc sử dụng |
| --- | --- | --- |
| `Driver` | Quản lý kết nối và connection pool | Tạo một bean dùng chung cho ứng dụng |
| `ReactiveSession` | Kênh làm việc với Neo4j, quản lý causal consistency và transaction | Không chia sẻ để chạy nhiều luồng database đồng thời |
| `ReactiveTransaction` | Nhóm các statement thành một đơn vị commit hoặc rollback | Chỉ một transaction hoạt động trong một session; không điều khiển đồng thời từ nhiều nhánh |

Một session có thể thực hiện nhiều transaction lần lượt. Ví dụ, transaction thứ nhất commit xong thì session có thể bắt đầu transaction tiếp theo. Nhưng không thể mở nhiều transaction song song trên cùng một session.

Muốn có nhiều transaction đồng thời, cần nhiều session độc lập. Session được tạo khá nhẹ; driver sẽ lấy kết nối từ pool khi cần. Ứng dụng không cần tự quản lý connection vật lý.

Trong SDN, `ReactiveNeo4jTransactionManager` quản lý transaction và tài nguyên reactive tương ứng. Khi dùng repository trong một reactive transaction, không cần tự tạo session cho từng câu query. Điều quan trọng là giữ các thao tác tham gia cùng transaction trong một pipeline và không làm chúng chạy chồng lấn.

## 3. Reactor Context giữ transaction như thế nào?

Transaction reactive của Spring không dựa vào `ThreadLocal` như transaction imperative. `ReactiveTransactionManager` gắn transaction và tài nguyên tương ứng vào Reactor Context.

Khi một phương thức reactive được đánh dấu `@Transactional`, transaction thường chỉ được bắt đầu khi publisher được subscribe. Các thao tác repository tham gia transaction nếu chúng chạy trong cùng Reactor Context và cùng reactive pipeline.

Các ví dụ `@Transactional` trong bài giả định ứng dụng đã cấu hình `ReactiveNeo4jTransactionManager` và reactive transaction management phù hợp với phiên bản Spring Boot/SDN đang dùng. Đừng giả định mọi cấu hình Boot đều tự tạo reactive transaction manager; hãy kiểm tra auto-configuration của phiên bản dự án.

Ví dụ:

```java
@Transactional
public Mono<Void> updatePerson(String id, String newName) {
    return personRepository.findById(id)
        .switchIfEmpty(Mono.error(
            new IllegalArgumentException("Person not found")
        ))
        .flatMap(person -> {
            person.setName(newName);
            return personRepository.save(person);
        })
        .then();
}
```

Lệnh đọc và lệnh lưu cùng tham gia transaction reactive của phương thức. Khi publisher hoàn tất thành công, transaction commit; khi có lỗi, transaction được rollback theo quy tắc transaction manager.

Việc chuyển scheduler bằng `publishOn()` hoặc `subscribeOn()` không tự tạo session hay transaction mới. Reactor Context được truyền theo subscription. Vì vậy, không thể dùng thread switch để tách các thao tác thành transaction độc lập.

Tương tự, gọi `subscribe()` bên trong một phương thức transactional tạo một subscription khác. Luồng mới không tự động tham gia transaction của pipeline ban đầu. Hãy trả publisher về tầng gọi và để framework quản lý subscription.

## 4. Toán tử Reactor nào có thể tạo truy vấn đồng thời?

Cần phân biệt toán tử tuần tự với toán tử có thể subscribe nhiều publisher con cùng lúc:

| Toán tử | Hành vi | Khi dùng chung một transaction |
| --- | --- | --- |
| `concatMap` | Subscribe và chờ từng publisher con hoàn tất rồi mới sang phần tử tiếp theo | Phù hợp để tuần tự hóa truy vấn |
| `flatMap` | Có thể subscribe nhiều publisher con đồng thời | Tránh dùng để chạy database calls chồng lấn trên cùng transaction |
| `flatMapSequential` | Subscribe nhiều publisher con đồng thời nhưng phát kết quả theo thứ tự nguồn | Không giải quyết vấn đề dùng chung session |
| `Mono.zip` | Subscribe các nguồn để chờ kết quả kết hợp | Không dùng để chạy song song các query cùng transaction |
| `parallel()` / `runOn()` | Chia công việc thành nhiều rail và scheduler | Không dùng để chia sẻ một session/transaction |

Một điểm dễ nhầm là `flatMapSequential` giữ thứ tự kết quả đầu ra nhưng vẫn có thể thực thi các publisher con đồng thời. Thứ tự phát kết quả không đồng nghĩa thứ tự truy vấn được thực thi.

`concatMap` là lựa chọn rõ ràng khi nhiều thao tác database phải dùng chung một transaction. Nó chỉ chuyển sang thao tác tiếp theo sau khi publisher trước hoàn tất.

## 5. Tuần tự hóa nhiều thao tác trong cùng transaction bằng concatMap

Giả sử cần cập nhật trạng thái của nhiều người trong cùng một transaction. Yêu cầu nghiệp vụ là tất cả cập nhật phải cùng commit hoặc cùng rollback.

Có thể viết:

```java
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class PersonBatchService {

    private final PersonRepository personRepository;

    public PersonBatchService(PersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    @Transactional
    public Mono<Void> activatePeople(List<String> ids) {
        return Flux.fromIterable(ids)
            .concatMap(id -> personRepository.findById(id)
                .switchIfEmpty(Mono.error(
                    new IllegalArgumentException("Missing person: " + id)
                ))
                .flatMap(person -> {
                    person.setActive(true);
                    return personRepository.save(person);
                }))
            .then();
    }
}
```

Luồng thực thi:

1. Đọc người đầu tiên.
2. Cập nhật và lưu người đó.
3. Chờ thao tác lưu hoàn tất.
4. Chuyển sang người tiếp theo.
5. Chỉ hoàn tất publisher sau khi tất cả phần tử đã xử lý xong.

Vì các thao tác nằm trong cùng một pipeline transactional, chúng tham gia cùng transaction. `concatMap` bảo đảm không có nhiều thao tác repository con được chạy đồng thời trên tài nguyên transaction đó.

Nếu một phần tử gây lỗi và lỗi được truyền ra ngoài, transaction có thể rollback toàn bộ các thay đổi trước đó. Đây là lựa chọn phù hợp khi yêu cầu nghiệp vụ là một đơn vị nguyên tử.

### 5.1. Nối các thao tác phụ thuộc bằng flatMap

Không phải mọi trường hợp dùng `flatMap` đều tạo cạnh tranh. Khi nguồn chỉ phát ra một phần tử và thao tác tiếp theo phụ thuộc vào kết quả trước đó, `flatMap` tạo một chuỗi phụ thuộc:

```java
@Transactional
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
        .flatMap(savedOrder ->
            inventoryRepository.reserve(
                savedOrder.getProductId(),
                savedOrder.getQuantity()
            ).thenReturn(savedOrder)
        );
}
```

Lệnh reserve chỉ được subscribe sau khi `save(order)` phát ra kết quả. Đây là luồng tuần tự giữa các bước phụ thuộc, dù dùng `flatMap`.

Điều cần tránh là dùng `flatMap` trên một nguồn nhiều phần tử để tạo nhiều thao tác database cùng lúc trong một transaction.

## 6. Mẫu không an toàn: flatMap trên nhiều phần tử trong cùng transaction

Ví dụ sau dễ gây hiểu nhầm:

```java
@Transactional
public Flux<Person> activatePeople(List<String> ids) {
    return Flux.fromIterable(ids)
        .flatMap(id -> personRepository.findById(id)
            .flatMap(person -> {
                person.setActive(true);
                return personRepository.save(person);
            }), 8);
}
```

Tham số `8` cho phép tối đa tám publisher con hoạt động đồng thời. Nếu mọi lời gọi repository tham gia cùng transaction reactive bên ngoài, các nhánh đó cùng sử dụng transaction/session được gắn với Reactor Context.

Đây không phải cách tạo tám transaction độc lập. Nó chỉ tạo nhiều nhánh xử lý cùng tham gia một transaction.

Hậu quả có thể gặp:

- Nhiều query cố gắng sử dụng cùng session/transaction cùng lúc.
- Lỗi do truy cập tài nguyên không hỗ trợ concurrent use.
- Thứ tự đọc/ghi khó dự đoán.
- Khó xác định nhánh nào gây lỗi và thời điểm rollback.
- Không đạt được tính độc lập của transaction như kỳ vọng.

Nếu cần một transaction duy nhất cho toàn bộ batch, hãy đổi `flatMap` thành `concatMap`. Nếu cần xử lý song song thực sự, hãy thiết kế mỗi nhánh thành một transaction và session riêng.

## 7. Chạy song song bằng các transaction độc lập

Có những công việc không phụ thuộc nhau, chẳng hạn cập nhật trạng thái của các khách hàng khác nhau. Nếu không cần tất cả cùng commit hoặc rollback, có thể chạy từng công việc trong một transaction riêng.

Một cách tổ chức với Spring là đặt thao tác transactional trong một bean riêng:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class PersonWriter {

    private final PersonRepository personRepository;

    public PersonWriter(PersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    @Transactional
    public Mono<Person> activateOne(String id) {
        return personRepository.findById(id)
            .switchIfEmpty(Mono.error(
                new IllegalArgumentException("Missing person: " + id)
            ))
            .flatMap(person -> {
                person.setActive(true);
                return personRepository.save(person);
            });
    }
}
```

Bean điều phối không mở transaction bao quanh toàn bộ batch:

```java
import java.util.List;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class PersonBatchCoordinator {

    private final PersonWriter personWriter;

    public PersonBatchCoordinator(PersonWriter personWriter) {
        this.personWriter = personWriter;
    }

    public Flux<Person> activateIndependently(List<String> ids) {
        return Flux.fromIterable(ids)
            .flatMap(personWriter::activateOne, 8);
    }
}
```

Trong cách tổ chức này:

- Coordinator không có `@Transactional`.
- Mỗi lời gọi `activateOne()` đi qua Spring proxy của bean `PersonWriter`.
- Mỗi publisher con được subscribe trong `flatMap` và mở transaction riêng.
- Transaction manager tạo tài nguyên session/transaction tương ứng cho mỗi nhánh.
- Tham số `8` giới hạn số publisher con hoạt động đồng thời.

Cần giữ hai bean riêng biệt để lời gọi đi qua transactional proxy. Nếu gọi một phương thức `@Transactional` khác bằng `this.activateOne()` trong cùng class, self-invocation không đi qua proxy và annotation có thể không được áp dụng như mong muốn.

Không đặt `@Transactional` trên coordinator trong ví dụ này. Nếu coordinator đã có transaction và các phương thức con dùng propagation mặc định `REQUIRED`, các nhánh có thể tham gia transaction bên ngoài thay vì tạo transaction độc lập.

### 7.1. Chọn concurrency phù hợp

Giá trị `8` chỉ là ví dụ, không phải cấu hình mặc định phù hợp với mọi hệ thống. Giới hạn cần cân nhắc:

- Connection pool và số session có thể mở.
- Số transaction đồng thời mà Neo4j có thể xử lý.
- Mức độ tranh chấp trên các node hoặc relationship.
- Thời gian xử lý mỗi transaction.
- Tải của các request khác trong ứng dụng.

Không nên dùng `flatMap` không giới hạn cho một danh sách lớn. Concurrency quá cao có thể làm cạn connection pool, tăng thời gian chờ, lock contention hoặc tải database.

## 8. Một transaction hay nhiều transaction độc lập?

Hai cách xử lý song song/tuần tự mang ý nghĩa nghiệp vụ khác nhau:

| Yêu cầu | Cách tổ chức |
| --- | --- |
| Tất cả thao tác phải commit hoặc rollback cùng nhau | Một transaction, dùng `concatMap` |
| Mỗi phần tử có thể thành công hoặc thất bại độc lập | Mỗi phần tử một transaction/session, dùng `flatMap` có giới hạn |
| Các bước sau phụ thuộc kết quả bước trước | Nối bằng `flatMap` trên Mono hoặc `concatMap` trên Flux |
| Nhiều truy vấn chỉ đọc, không cần chung snapshot/transaction | Có thể chạy độc lập bằng các publisher/transaction riêng |
| Nhiều query cần đọc kết quả ghi trước trong cùng đơn vị nghiệp vụ | Giữ cùng transaction và tuần tự hóa |
| Cần kết hợp kết quả của nhiều công việc độc lập | Chạy publisher độc lập rồi kết hợp bằng `collectList()`, `zip()` hoặc toán tử phù hợp |

Khi tách thành nhiều transaction, tính nguyên tử toàn batch không còn. Một số nhánh có thể commit thành công trước khi nhánh khác thất bại. Nếu nghiệp vụ cần phục hồi toàn bộ batch, phải thiết kế cơ chế bù trừ, trạng thái tiến trình hoặc giữ một transaction duy nhất.

## 9. Mono.zip và các nhánh đọc trong cùng transaction

`Mono.zip()` hữu ích để kết hợp kết quả của nhiều nguồn độc lập:

```java
Mono<Customer> customer = customerRepository.findById(customerId);
Mono<Account> account = accountRepository.findById(accountId);

return Mono.zip(customer, account)
    .map(tuple -> new CustomerAccountView(
        tuple.getT1(),
        tuple.getT2()
    ));
```

Nếu hai publisher được thực thi ngoài một reactive transaction chung, mỗi thao tác có thể sử dụng transaction/session riêng theo cơ chế repository. Đây có thể là lựa chọn hợp lý khi chỉ cần ghép hai kết quả độc lập.

Nhưng nếu đoạn code nằm trong một phương thức `@Transactional` và cả hai repository dùng cùng transaction manager, các thao tác tham gia cùng Reactor Context và tài nguyên transaction. `zip()` subscribe hai nguồn để chạy đồng thời, vì vậy không nên dùng cách này để phát nhiều truy vấn song song trên cùng session/transaction.

Nếu cần giữ cùng transaction, hãy tuần tự hóa:

```java
@Transactional
public Mono<CustomerAccountView> loadConsistently(
        String customerId,
        String accountId) {

    return customerRepository.findById(customerId)
        .flatMap(customer ->
            accountRepository.findById(accountId)
                .map(account ->
                    new CustomerAccountView(customer, account)
                )
        );
}
```

Ở đây, truy vấn account chỉ bắt đầu sau khi truy vấn customer phát ra kết quả. Hai thao tác vẫn nằm trong cùng transaction.

## 10. Session thủ công phải được tạo trong reactive lifecycle

Khi sử dụng trực tiếp Neo4j Java Driver, không tạo một `ReactiveSession` rồi lưu vào field của singleton service để nhiều request cùng sử dụng.

Session cần được tạo và đóng theo subscription. Reactor cung cấp pattern `usingWhen` để quản lý resource bất đồng bộ do Driver tạo:

```java
import org.neo4j.driver.Driver;
import org.neo4j.driver.reactivestreams.ReactiveSession;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux.usingWhen(
    Mono.fromSupplier(() -> driver.session(ReactiveSession.class)),
    session -> runWork(session),
    session -> Mono.from(session.close()),
    (session, error) -> Mono.from(session.close()),
    session -> Mono.from(session.close())
);
```

Ví dụ trên minh họa vòng đời:

1. Tạo session khi publisher được subscribe.
2. Chạy công việc reactive trên session đó.
3. Đóng session khi hoàn tất thành công.
4. Đóng session khi có lỗi hoặc bị cancel.

Nếu cần chạy nhiều công việc song song, mỗi nhánh phải có session riêng. Không truyền cùng một biến `session` vào nhiều publisher con của `flatMap`.

Với repository SDN, thông thường không cần tự quản lý session. Hãy để `ReactiveNeo4jTransactionManager` và các abstraction của SDN quản lý vòng đời này.

## 11. Backpressure không đồng nghĩa với giới hạn truy vấn đồng thời

Backpressure điều khiển tốc độ publisher phát dữ liệu và subscriber yêu cầu dữ liệu. Nó giúp tránh việc producer đẩy dữ liệu nhanh hơn khả năng tiêu thụ của consumer.

Tuy nhiên, backpressure không tự bảo đảm chỉ có một query đang chạy trên session. Ví dụ:

- `limitRate()` điều chỉnh số phần tử được yêu cầu upstream.
- `flatMap(..., concurrency)` giới hạn số publisher con được subscribe đồng thời.
- `concatMap()` tuần tự hóa việc subscribe publisher con.

Nếu yêu cầu là không chạy song song các thao tác database trên cùng transaction, hãy dùng `concatMap()`. Đừng dựa vào `limitRate()` để thay thế concurrency control.

## 12. Kiểm thử giới hạn song song

Kiểm thử nên xác nhận cả hai trường hợp:

- Nhiều thao tác trong cùng transaction được thực hiện tuần tự và rollback cùng nhau khi một thao tác thất bại.
- Nhiều công việc độc lập được cấp transaction riêng và concurrency không vượt giới hạn cấu hình.

Dùng `StepVerifier` để subscribe và kiểm tra kết quả reactive. Với kiểm thử tích hợp, dùng Neo4j test database riêng, không dùng database phát triển dùng chung.

Ví dụ kiểm tra pipeline tuần tự:

```java
StepVerifier.create(
        personBatchService.activatePeople(List.of("p-1", "p-2"))
    )
    .verifyComplete();
```

Ví dụ này xác minh publisher hoàn tất. Để xác minh tính nguyên tử, cần thêm assertion đọc lại dữ liệu sau khi cố ý làm một phần tử phát sinh lỗi và xác nhận các thay đổi trong transaction đã rollback.

Đối với xử lý song song, hãy kiểm tra số lượng transaction/session độc lập đang hoạt động bằng test instrumentation hoặc log phù hợp. Không chỉ đo thời gian chạy; một test nhanh không chứng minh rằng các publisher đã dùng tài nguyên tách biệt.

## 13. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `flatMap` cho nhiều query trong một transaction | Nhiều nhánh dùng chung session/transaction đồng thời | Dùng `concatMap` |
| Nghĩ `flatMapSequential` tuần tự hóa việc thực thi | Inner publisher vẫn có thể chạy đồng thời | Dùng `concatMap` nếu cần tuần tự |
| Dùng `Mono.zip()` cho nhiều query cùng transaction | Các nguồn được subscribe đồng thời trong cùng context | Nối truy vấn theo thứ tự hoặc tách transaction |
| Gọi `publishOn()` để tạo transaction mới | Thread đổi nhưng Reactor Context vẫn mang transaction hiện tại | Tạo transaction/session độc lập |
| Gọi `subscribe()` trong service transactional | Tạo subscription tách khỏi pipeline ban đầu | Trả publisher cho tầng gọi |
| Dùng một ReactiveSession trong singleton | Nhiều request có thể truy cập cùng session | Tạo session theo subscription và đóng bằng `usingWhen` |
| Mở nhiều transaction trên một session | Vi phạm giới hạn một transaction hoạt động mỗi session | Dùng session riêng cho từng transaction đồng thời |
| Đặt `@Transactional` trên coordinator cần chạy độc lập | Các nhánh có thể tham gia transaction bên ngoài | Bỏ transaction ngoài hoặc thiết kế propagation có chủ đích |
| Dùng self-invocation cho phương thức transactional | Lời gọi không đi qua Spring proxy | Tách writer sang bean riêng |
| Dùng concurrency quá cao | Tăng áp lực lên pool và database | Chọn giới hạn phù hợp và theo dõi tải |
| Tách transaction nhưng vẫn kỳ vọng atomic toàn batch | Một số nhánh có thể commit trước khi nhánh khác lỗi | Giữ một transaction tuần tự hoặc thiết kế bù trừ |

## 14. Câu hỏi tự kiểm tra

1. Vì sao `Driver` có thể dùng chung nhưng `ReactiveSession` không nên chia sẻ cho nhiều nhánh đồng thời?
2. Một session có thể có bao nhiêu transaction đang hoạt động tại cùng thời điểm?
3. Transaction reactive của Spring được lưu trong ThreadLocal hay Reactor Context?
4. Vì sao `publishOn()` không tạo transaction hoặc session mới?
5. `concatMap()` khác `flatMap()` ở cách subscribe publisher con như thế nào?
6. Vì sao `flatMapSequential()` không bảo đảm query được thực thi tuần tự?
7. Khi nào nên dùng một transaction duy nhất với `concatMap()`?
8. Khi nào nên dùng nhiều transaction/session độc lập với `flatMap()` có giới hạn?
9. Vì sao coordinator trong ví dụ song song không được đặt `@Transactional`?
10. Backpressure khác concurrency control như thế nào?
11. Khi tự quản lý ReactiveSession, vì sao nên tạo và đóng session bằng `usingWhen()`?
12. Nếu một nhánh trong nhiều transaction độc lập thất bại, điều gì xảy ra với các nhánh đã commit?

## Tài liệu tham khảo

- [Neo4j Java Driver – Reactive API](https://neo4j.com/docs/java-manual/current/reactive/)
- [Neo4j Java Driver – Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [ReactiveSession API – Neo4j Java Driver](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/reactivestreams/ReactiveSession.html)
- [Spring Framework – Reactive Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Data Neo4j – ReactiveNeo4jTransactionManager API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/transaction/ReactiveNeo4jTransactionManager.html)

## Kết luận

Reactive API cho phép nhiều publisher hoạt động đồng thời, nhưng một Neo4j session chỉ có thể có một transaction hoạt động tại một thời điểm và session không phải tài nguyên để chia sẻ giữa nhiều luồng database song song. Trong SDN, các thao tác repository cùng Reactor Context sẽ tham gia transaction reactive hiện tại; việc chuyển scheduler không tạo transaction mới.

Khi nhiều thao tác phải cùng commit hoặc rollback, giữ chúng trong một transaction và dùng `concatMap()` hoặc nối các bước phụ thuộc theo thứ tự. Khi các công việc có thể thành công độc lập, hãy cấp mỗi nhánh một transaction/session riêng và dùng `flatMap()` với giới hạn concurrency rõ ràng. Không dùng `flatMapSequential()`, `Mono.zip()` hoặc `publishOn()` như cách thay thế cho việc tách transaction. Thiết kế đúng ranh giới tài nguyên sẽ giúp reactive pipeline tận dụng concurrency mà vẫn giữ được tính nhất quán và khả năng kiểm soát lỗi.
