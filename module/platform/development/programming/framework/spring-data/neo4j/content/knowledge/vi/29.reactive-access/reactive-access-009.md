# Lựa chọn xử lý tuần tự hoặc có giới hạn đồng thời cho thao tác ghi

Khi ghi nhiều entity bằng Spring Data Neo4j (SDN) reactive, cách ghép các publisher quyết định có bao nhiêu thao tác được thực hiện cùng lúc và kết quả được phát ra theo thứ tự nào. `concatMap` xử lý từng thao tác một, phù hợp khi thứ tự quan trọng hoặc nhiều thay đổi cùng tác động lên một aggregate. `flatMap` cho phép nhiều thao tác chạy đồng thời; cần truyền giới hạn concurrency tường minh để kiểm soát số request đang chờ Neo4j.

Chọn toán tử phù hợp còn phụ thuộc vào ranh giới transaction. Một luồng `concatMap` nằm trong một reactive transaction có thể giữ các thao tác tuần tự trong cùng đơn vị commit/rollback. Ngược lại, xử lý đồng thời các bản ghi độc lập thường phù hợp hơn khi mỗi bản ghi có transaction riêng. Không nên tăng concurrency một cách máy móc nếu nhiều lệnh đang sửa cùng node hoặc cùng relationship.

## 1. Reactive write trả về publisher

Reactive repository sử dụng `Mono<T>` cho kết quả đơn và `Flux<T>` cho một luồng kết quả. Ví dụ:

~~~java
import org.springframework.data.neo4j.repository.ReactiveNeo4jRepository;

public interface PersonRepository
        extends ReactiveNeo4jRepository<Person, Long> {
}
~~~

Phương thức `save` trả về một `Mono<Person>`. Lệnh ghi chỉ được thực thi khi publisher được subscribe; việc tạo publisher chưa đồng nghĩa dữ liệu đã được lưu.

~~~java
Mono<Person> saved = personRepository.save(person);
~~~

Trong reactive pipeline, hãy trả publisher về cho caller hoặc ghép nó vào pipeline lớn hơn. Không gọi `subscribe()` thủ công trong service chỉ để khởi chạy lệnh ghi, vì cách đó tách thao tác khỏi vòng đời xử lý lỗi, backpressure và transaction context của caller.

## 2. `concatMap`: xử lý từng thao tác theo thứ tự

`concatMap` subscribe vào publisher con theo thứ tự phần tử nguồn và đợi publisher con hiện tại hoàn tất trước khi xử lý phần tử tiếp theo. Vì vậy, tại một thời điểm chỉ có một thao tác ghi từ chuỗi này đang được thực hiện.

~~~java
import reactor.core.publisher.Flux;

public Flux<Person> saveSequentially(Flux<Person> incoming) {
    return incoming.concatMap(personRepository::save);
}
~~~

Nếu nguồn phát ra `A`, `B`, `C`, thứ tự xử lý sẽ là:

~~~text
save(A) hoàn tất -> save(B) hoàn tất -> save(C) hoàn tất
~~~

Đặc điểm của `concatMap`:

- Giữ thứ tự xử lý theo nguồn.
- Không chạy đồng thời các publisher con.
- Giới hạn số thao tác ghi đang hoạt động ở mức một trong chuỗi.
- Phù hợp khi thao tác sau phụ thuộc kết quả hoặc trạng thái do thao tác trước tạo ra.

Ví dụ, nếu mỗi command cập nhật cùng một node `Account`, việc tuần tự hóa giúp tránh để hai lệnh trong cùng luồng cạnh tranh cập nhật version của entity đó.

## 3. Đặt `concatMap` trong một reactive transaction

Khi một batch cần tính nguyên tử, có thể đặt transaction ở service và dùng `concatMap` để xử lý từng phần tử trong cùng pipeline:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Flux;

@Service
public class PersonImportService {

    private final PersonRepository people;

    public PersonImportService(PersonRepository people) {
        this.people = people;
    }

    @Transactional
    public Flux<Person> saveBatchInOrder(Flux<Person> incoming) {
        return incoming.concatMap(people::save);
    }
}
~~~

Với reactive transaction management, transaction được gắn vào Reactor context và tồn tại trong quá trình publisher được subscribe, chạy và hoàn tất. Các thao tác SDN trong pipeline có thể tham gia cùng transaction. Nếu một thao tác phát lỗi và lỗi được truyền ra ngoài, transaction có thể rollback toàn bộ batch.

Hãy giữ batch trong giới hạn hợp lý. Một stream rất dài hoặc không kết thúc trong một transaction sẽ giữ transaction và tài nguyên lâu, tăng contention và khiến rollback tốn kém. Có thể chia nguồn thành các batch hữu hạn, mỗi batch là một đơn vị transaction độc lập.

Không gọi `block()` hoặc `subscribe()` bên trong method transactional reactive. Làm vậy có thể khiến công việc chạy ngoài pipeline hoặc làm mất transaction context.

## 4. `flatMap`: cho phép nhiều thao tác chạy đồng thời

`flatMap` subscribe vào nhiều publisher con trước khi publisher trước hoàn tất. Đây là lựa chọn phù hợp khi các bản ghi độc lập và không cần giữ thứ tự thực thi:

~~~java
public Flux<Person> saveConcurrently(
        Flux<Person> incoming,
        int concurrency) {

    return incoming.flatMap(personRepository::save, concurrency);
}
~~~

Tham số `concurrency` giới hạn số publisher con được subscribe đồng thời. Ví dụ, `concurrency = 4` cho phép tối đa bốn thao tác save từ pipeline này đang hoạt động cùng lúc.

Kết quả có thể được phát ra theo thứ tự hoàn tất, không nhất thiết theo thứ tự phần tử đầu vào. Nếu `save(C)` hoàn tất trước `save(A)`, kết quả `C` có thể được phát trước `A`.

Không nên dùng `flatMap(mapper)` không giới hạn theo ý định nghiệp vụ khi chưa đánh giá tải. Overload có tham số concurrency giúp giới hạn số thao tác đồng thời và giảm nguy cơ tạo quá nhiều request, transaction hoặc công việc chờ trong driver.

## 5. Giới hạn concurrency theo cấu hình ứng dụng

Concurrency nên là cấu hình được kiểm soát ở phía server, không nhận một con số tùy ý từ client:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class PersonBatchService {

    private final PersonRepository people;
    private final int writeConcurrency;

    public PersonBatchService(
            PersonRepository people,
            @Value("${app.neo4j.write-concurrency:4}") int writeConcurrency) {
        this.people = people;
        this.writeConcurrency = writeConcurrency;
    }

    public Flux<Person> saveIndependent(Flux<Person> incoming) {
        return incoming.flatMap(people::save, writeConcurrency);
    }
}
~~~

Ví dụ cấu hình:

~~~yaml
app:
  neo4j:
    write-concurrency: 4
~~~

Giá trị `4` chỉ là điểm khởi đầu minh họa. Concurrency phù hợp phụ thuộc kích thước connection pool, năng lực Neo4j, độ phức tạp Cypher, độ trễ mạng và mức độ tranh chấp dữ liệu. Nên đo thời gian phản hồi, số transaction đang hoạt động, queue và tỷ lệ lỗi trước khi điều chỉnh.

Validate cấu hình khi ứng dụng khởi động để tránh giá trị bằng không hoặc âm:

~~~java
if (writeConcurrency < 1 || writeConcurrency > 16) {
    throw new IllegalArgumentException(
        "write-concurrency must be between 1 and 16"
    );
}
~~~

Giới hạn trên `16` trong ví dụ là chính sách ứng dụng, không phải giới hạn cố định của Neo4j hay Reactor.

## 6. `flatMapSequential`: phát kết quả theo thứ tự nhưng vẫn chạy đồng thời

`flatMapSequential` cho phép subscribe vào publisher con đồng thời giống `flatMap`, nhưng giữ thứ tự phát kết quả theo thứ tự phần tử nguồn:

~~~java
public Flux<Person> saveConcurrentlyInSourceOrder(
        Flux<Person> incoming,
        int concurrency) {

    return incoming.flatMapSequential(
        personRepository::save,
        concurrency
    );
}
~~~

Điểm cần phân biệt:

| Toán tử | Thực thi publisher con | Thứ tự phát kết quả |
|---|---|---|
| `concatMap` | Tuần tự, một publisher con tại một thời điểm | Theo thứ tự nguồn |
| `flatMap` | Đồng thời theo giới hạn concurrency | Theo thứ tự hoàn tất |
| `flatMapSequential` | Đồng thời theo giới hạn concurrency | Theo thứ tự nguồn |

`flatMapSequential` không biến các lệnh ghi thành tuần tự. Các thao tác vẫn có thể chạy đồng thời và cạnh tranh cập nhật cùng dữ liệu. Chỉ dùng nó khi cần giữ thứ tự kết quả ở downstream nhưng các thao tác con độc lập và có thể chạy song song.

## 7. Chọn transaction boundary khi ghi đồng thời

Một điểm quan trọng là `flatMap` không tự tạo transaction riêng cho từng phần tử. Transaction phụ thuộc vào cách publisher được gọi và context mà nó nhận:

- Nếu toàn bộ pipeline nằm trong một method `@Transactional` reactive, các thao tác con có thể tham gia cùng transaction hiện tại.
- Nếu mỗi thao tác được gọi qua một bean có method reactive `@Transactional` và không có transaction bên ngoài, mỗi subscription có thể mở transaction riêng.
- Nếu có transaction bên ngoài với propagation `REQUIRED`, method con thường tham gia transaction đó thay vì tự tạo transaction độc lập.

Đối với các bản ghi độc lập cần concurrency, có thể tách một lần ghi vào bean riêng:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Component
public class PersonWriteUnit {

    private final PersonRepository people;

    public PersonWriteUnit(PersonRepository people) {
        this.people = people;
    }

    @Transactional
    public Mono<Person> saveOne(Person person) {
        return people.save(person);
    }
}
~~~

Orchestrator không mở transaction bao quanh toàn bộ batch:

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class ConcurrentPersonImportService {

    private final PersonWriteUnit writeUnit;

    public ConcurrentPersonImportService(PersonWriteUnit writeUnit) {
        this.writeUnit = writeUnit;
    }

    public Flux<Person> importIndependent(
            Flux<Person> incoming,
            int concurrency) {

        return incoming.flatMap(writeUnit::saveOne, concurrency);
    }
}
~~~

`PersonWriteUnit` là bean khác nên lời gọi đi qua Spring proxy. Khi không có transaction bao ngoài, mỗi publisher `saveOne` được subscribe có thể mở transaction riêng. Không đặt `@Transactional` lên `importIndependent` nếu mục tiêu là mỗi record có transaction riêng; nếu có transaction bao ngoài, propagation mặc định `REQUIRED` có thể khiến các lần ghi tham gia cùng transaction đó.

Với cách này, các record có thể commit độc lập. Nếu một record lỗi, những record khác đã commit có thể vẫn còn trong database. Đây không phải một batch all-or-nothing.

## 8. Khi nào cần cùng transaction và khi nào cần transaction riêng?

| Yêu cầu nghiệp vụ | Cách tổ chức phù hợp | Hệ quả |
|---|---|---|
| Nhiều thay đổi phải cùng thành công hoặc cùng rollback | Một transaction reactive, dùng `concatMap` | Có tính nguyên tử trong phạm vi transaction |
| Các node độc lập, chấp nhận commit từng phần | Một transaction cho mỗi lần ghi, dùng `flatMap` có giới hạn | Có thể đạt throughput cao hơn; batch có thể hoàn thành một phần |
| Nhiều command cùng sửa một aggregate | Tuần tự hóa theo aggregate/key | Giảm cạnh tranh và xung đột version |
| Cần phát kết quả theo thứ tự nguồn nhưng ghi độc lập | `flatMapSequential` với concurrency giới hạn | Thứ tự output được giữ, execution vẫn đồng thời |
| Dữ liệu rất lớn, cần commit theo lô | Chia thành batch hữu hạn rồi xử lý từng batch | Giới hạn thời gian sống và kích thước transaction |

Đừng dùng một transaction khổng lồ chỉ để đạt tính nguyên tử cho hàng triệu bản ghi. Hãy xác định đơn vị nghiệp vụ thực sự cần commit cùng nhau và chia nhỏ phần còn lại.

## 9. Tránh cập nhật đồng thời cùng một entity

Giới hạn concurrency không tự bảo đảm an toàn khi hai phần tử cùng tham chiếu một node. Nếu hai publisher cùng tải một entity có `@Version`, sửa và lưu, một thao tác có thể thành công còn thao tác kia gặp `OptimisticLockingFailureException`.

Ví dụ, hai command cùng cập nhật một `Person`:

~~~java
commands.flatMap(command -> personService.apply(command), 4);
~~~

Nếu các command có thể cùng `personKey`, chúng có thể chạy đồng thời trên cùng aggregate. Hãy cân nhắc:

- Dùng `concatMap` nếu thứ tự command toàn luồng phải được giữ.
- Nhóm command theo aggregate key rồi xử lý tuần tự trong từng nhóm, đồng thời cho phép các nhóm độc lập chạy song song.
- Thiết kế thao tác idempotent hoặc dùng optimistic locking cùng chính sách xử lý conflict.
- Dùng constraint ở Neo4j để bảo vệ invariant dữ liệu mà nhiều request cùng có thể vi phạm.

Một pattern theo key có thể được biểu diễn như sau:

~~~java
commands
    .groupBy(PersonCommand::personKey)
    .flatMap(group -> group.concatMap(personService::apply), 4);
~~~

Các command của cùng một `personKey` được xử lý tuần tự trong group đó; tối đa bốn group có thể được xử lý đồng thời. Với nguồn có số lượng key rất lớn hoặc không giới hạn, cần cân nhắc vòng đời group và bộ nhớ của `groupBy`; không dùng pattern này mà không kiểm soát cardinality.

## 10. Backpressure và tải lên Neo4j

Reactive Streams có cơ chế backpressure để downstream điều tiết lượng phần tử upstream phát ra. Tuy nhiên, backpressure không thay thế giới hạn tài nguyên ở mọi tầng:

- `flatMap` với concurrency lớn vẫn có thể tạo nhiều transaction đồng thời.
- Driver connection pool có giới hạn riêng; thao tác có thể phải chờ connection.
- Cypher nặng có thể làm Neo4j quá tải dù số publisher không quá lớn.
- Một upstream phát nhanh có thể tạo hàng đợi nếu pipeline giữ nhiều phần tử chờ xử lý.

Hãy điều chỉnh concurrency dựa trên đo đạc thực tế. Theo dõi latency, throughput, lỗi timeout, số connection đang sử dụng và tải server. Tăng concurrency có thể cải thiện throughput đến một ngưỡng; sau ngưỡng đó, contention và queue có thể khiến latency tăng.

Nếu cần ghi rất nhiều node theo cùng một mẫu, hãy đánh giá một Cypher query nhận danh sách map và dùng `UNWIND` để ghi theo lô. Batch query có thể giảm round trip, nhưng phải kiểm soát kích thước batch và transaction duration.

## 11. Xử lý lỗi trong pipeline ghi

Mặc định, lỗi phát ra từ một publisher con có thể kết thúc pipeline `flatMap` và hủy các publisher còn lại chưa hoàn tất. Với các transaction riêng, một số thao tác khác có thể đã commit trước khi lỗi được truyền ra. Vì vậy, kết quả batch có thể là một phần thành công.

Nếu nghiệp vụ yêu cầu tiếp tục xử lý các phần tử còn lại và thu thập lỗi từng record, hãy chuyển lỗi thành kết quả ở phạm vi publisher con:

~~~java
public Flux<WriteOutcome> writeAndCollectOutcomes(
        Flux<Person> incoming,
        int concurrency) {

    return incoming.flatMap(person ->
        writeUnit.saveOne(person)
            .map(saved -> WriteOutcome.success(person.getPersonKey()))
            .onErrorResume(error ->
                reactor.core.publisher.Mono.just(
                    WriteOutcome.failure(person.getPersonKey(), error.getMessage())
                )
            ),
        concurrency
    );
}
~~~

`WriteOutcome` là DTO kết quả do ứng dụng định nghĩa. Cách này biến lỗi của từng phần tử thành dữ liệu để downstream tổng hợp. Chỉ dùng khi nghiệp vụ chấp nhận partial success và đã xác định lỗi nào có thể tiếp tục. Không nên nuốt mọi exception; lỗi cấu hình, lỗi xác thực hoặc lỗi hệ thống nghiêm trọng có thể cần dừng cả pipeline.

Không dùng `onErrorContinue` như một cách bỏ qua lỗi chung chung cho mọi lệnh ghi. Hãy xử lý lỗi ở publisher con tương ứng để biết chính xác record nào thất bại và giữ được ngữ nghĩa transaction.

## 12. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `flatMap` không giới hạn cho batch lớn | Quá nhiều transaction và request đồng thời | Truyền concurrency giới hạn theo cấu hình |
| Dùng `flatMap` nhưng kỳ vọng thứ tự nguồn | Kết quả có thể phát theo thứ tự hoàn tất | Dùng `concatMap` hoặc `flatMapSequential` nếu cần output order |
| Nghĩ `flatMapSequential` thực thi tuần tự | Các publisher con vẫn chạy đồng thời | Dùng `concatMap` nếu cần tuần tự hóa thao tác ghi |
| Đặt `flatMap` trong một transaction chung rồi giả định mỗi record commit riêng | Các thao tác có thể tham gia cùng transaction | Thiết kế transaction boundary ở bean ghi riêng và không có transaction bao ngoài |
| Dùng `flatMap` cho nhiều command cùng sửa một aggregate | Tăng optimistic locking conflict hoặc race condition | Tuần tự hóa theo aggregate key hoặc thiết kế xử lý conflict |
| Dùng một transaction cho stream vô hạn | Giữ transaction và tài nguyên quá lâu | Chia stream thành batch hữu hạn |
| Gọi `subscribe()` hoặc `block()` trong service | Mất liên kết với backpressure, error và transaction context | Trả `Mono`/`Flux` và ghép pipeline |
| Cho rằng batch có transaction riêng sẽ all-or-nothing | Một số record có thể đã commit trước khi record khác lỗi | Chọn một transaction chung hoặc chấp nhận partial success |
| Nuốt lỗi để pipeline tiếp tục | Mất thông tin record thất bại và lỗi hệ thống | Chuyển lỗi thành outcome có cấu trúc, chỉ tiếp tục theo chính sách |

## 13. Quy trình lựa chọn toán tử

1. Xác định các thao tác có độc lập dữ liệu hay cùng sửa một aggregate.
2. Xác định có cần giữ thứ tự xử lý, thứ tự output hay cả hai.
3. Nếu cần tuần tự và cùng transaction, dùng `concatMap` trong một reactive transaction có giới hạn kích thước.
4. Nếu các thao tác độc lập và có thể commit riêng, dùng `flatMap` với concurrency được cấu hình và đo đạc.
5. Nếu chỉ cần giữ thứ tự phát kết quả trong khi thao tác độc lập chạy đồng thời, cân nhắc `flatMapSequential`.
6. Đặt transaction boundary đúng chỗ; không để một transaction ngoài vô tình làm các lần ghi độc lập tham gia cùng transaction.
7. Xác định chính sách lỗi: rollback toàn bộ, dừng khi lỗi đầu tiên hay trả outcome riêng cho từng record.
8. Kiểm thử tải, optimistic locking conflict, partial failure và việc hủy pipeline.

## 14. Tự kiểm tra

1. `concatMap` khác `flatMap` ở cách subscribe publisher con như thế nào?
2. Vì sao `flatMap` nên nhận tham số concurrency khi ghi vào Neo4j?
3. `flatMapSequential` giữ thứ tự nào và có tuần tự hóa thao tác ghi không?
4. Khi nào một reactive transaction bao quanh toàn bộ pipeline?
5. Vì sao mỗi lần ghi độc lập cần một transaction boundary riêng nếu dùng bounded concurrency?
6. Điều gì có thể xảy ra khi nhiều publisher cùng cập nhật một entity có `@Version`?
7. Vì sao một batch dùng transaction riêng cho từng record có thể chỉ thành công một phần?
8. Khi nào nên dùng `groupBy(...).concatMap(...)`?

Hãy chọn `concatMap` khi cần tuần tự hóa thao tác ghi và giữ thứ tự; chọn `flatMap` với concurrency giới hạn khi các thao tác độc lập có thể chạy trong những transaction riêng; dùng `flatMapSequential` khi chỉ cần giữ thứ tự phát kết quả trong lúc thực thi đồng thời. Quyết định cuối cùng phải phù hợp với aggregate đang được cập nhật, transaction boundary và chính sách partial failure của nghiệp vụ.
