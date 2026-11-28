# Backpressure, fetch size và tiêu thụ kết quả lớn

Spring Data Neo4j (SDN) reactive trả kết quả dưới dạng publisher của Reactive Streams, thường được sử dụng qua Project Reactor với **Flux** và **Mono**. Cách trả dữ liệu này cho phép ứng dụng tiêu thụ kết quả theo nhu cầu của subscriber thay vì bắt buộc tải toàn bộ graph vào bộ nhớ. Tuy nhiên, một pipeline reactive chỉ thực sự kiểm soát được lượng dữ liệu đang lưu chuyển khi backpressure được giữ xuyên suốt từ subscriber, qua các operator, tới Neo4j Java Driver.

Ba khái niệm cần phân biệt là **backpressure**, **fetch size** và **kích thước kết quả**. Backpressure điều khiển số phần tử downstream đang yêu cầu. Trong API Session/AsyncSession, fetch size quy định số record driver yêu cầu server gửi trong một batch. Kích thước kết quả là tổng số record mà câu Cypher có thể trả về. Chỉnh một giá trị không tự động giới hạn hai giá trị còn lại.

Bài học này trình bày cách đọc Flux lớn an toàn, cách điều tiết demand trong reactive driver và phân biệt nó với fetch size của API imperative/async, cách tránh các operator làm tích tụ dữ liệu và cách giữ transaction cùng tài nguyên kết nối trong suốt vòng đời subscription.

## Reactive Streams và backpressure

Trong Reactive Streams, subscriber không chỉ nhận dữ liệu. Subscriber có thể yêu cầu số phần tử mà nó sẵn sàng xử lý thông qua **Subscription.request(n)**. Publisher phát dữ liệu theo demand đã nhận, trong giới hạn hợp đồng của publisher.

Ví dụ, subscriber yêu cầu từng phần tử:

~~~text
Subscriber
   |
   | request(1)
   v
Reactor pipeline
   |
   | demand được truyền ngược upstream
   v
Reactive Neo4j Driver
   |
   | demand điều tiết việc kéo record từ server
   v
Neo4j
~~~

Nếu downstream xử lý chậm, backpressure cho phép làm chậm việc lấy thêm dữ liệu từ upstream. Điều này giảm lượng record phải chờ trong các buffer. Nếu một operator hoặc subscriber yêu cầu không giới hạn rồi tự giữ tất cả kết quả, lợi ích này có thể bị mất.

Trong SDN reactive, repository thường trả Flux cho nhiều kết quả và Mono cho tối đa một kết quả:

~~~java
import org.springframework.data.neo4j.repository.ReactiveNeo4jRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface PersonRepository
        extends ReactiveNeo4jRepository<Person, String> {

    Flux<Person> findByActiveTrue();

    Mono<Person> findOneByEmployeeCode(String employeeCode);
}
~~~

Flux có thể phát nhiều Person theo nhu cầu của subscriber. Mono biểu diễn tối đa một kết quả. Việc dùng Flux không có nghĩa toàn bộ kết quả được giữ trong RAM; cách tiêu thụ phía sau quyết định pipeline có giữ được đặc tính streaming hay không.

## Đọc kết quả lớn qua ReactiveNeo4jClient

ReactiveNeo4jClient cho phép viết Cypher và ánh xạ từng record thành DTO. Ví dụ, đọc mã và tên nhân viên theo thứ tự ổn định:

~~~java
public record PersonSummary(
    String employeeCode,
    String fullName
) {
}
~~~

~~~java
import org.springframework.data.neo4j.core.ReactiveNeo4jClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Flux;

@Repository
public class PersonStreamReader {

    private final ReactiveNeo4jClient client;

    public PersonStreamReader(ReactiveNeo4jClient client) {
        this.client = client;
    }

    public Flux<PersonSummary> streamActivePeople() {
        return client.query("""
                MATCH (p:Person)
                WHERE p.active = true
                RETURN p.employeeCode AS employeeCode,
                       p.fullName AS fullName
                ORDER BY p.employeeCode
                """)
            .fetchAs(PersonSummary.class)
            .mappedBy((typeSystem, record) -> new PersonSummary(
                record.get("employeeCode").asString(),
                record.get("fullName").asString()
            ))
            .all();
    }
}
~~~

Phương thức all() trả về Flux<PersonSummary>. Record được ánh xạ khi subscriber tiêu thụ publisher. Việc trả DTO thay vì entity graph có thể giảm lượng dữ liệu cần truyền và ánh xạ nếu màn hình chỉ cần một vài thuộc tính.

Hãy chọn RETURN đủ hẹp cho use case. RETURN p có thể yêu cầu ánh xạ entity cùng các quan hệ theo phạm vi query và mapping; nếu chỉ cần hai trường, trả đúng hai trường sẽ giúp giảm kích thước record và chi phí chuyển đổi.

## Backpressure ở phía Reactor

Một Flux hỗ trợ backpressure cho phép operator điều tiết demand upstream. **limitRate(n)** chia yêu cầu downstream thành các request nhỏ hơn trước khi truyền lên upstream:

~~~java
public Flux<PersonSummary> streamInControlledBatches() {
    return personStreamReader.streamActivePeople()
        .limitRate(128);
}
~~~

limitRate(128) điều chỉnh nhịp request mà Reactor gửi upstream. Nó không thay đổi tổng số record mà Cypher có thể trả về, cũng không tương đương với LIMIT 128 trong Cypher. Nếu cần chỉ lấy tối đa 128 người, hãy dùng LIMIT trong câu truy vấn.

Có thể đặt giới hạn ở nhiều tầng:

- WHERE giảm số node phù hợp.
- RETURN chọn các cột cần thiết.
- LIMIT giới hạn tổng số dòng của một truy vấn.
- Backpressure điều chỉnh tốc độ và số phần tử downstream yêu cầu.
- Fetch size cấu hình số record mỗi batch cho Session/AsyncSession; reactive session dùng subscription demand.

Mỗi tầng giải quyết một vấn đề khác nhau. Một query trả về hàng triệu dòng vẫn có thể được tiêu thụ theo luồng, nhưng nó vẫn phải xử lý tổng lượng dữ liệu lớn và giữ tài nguyên database trong thời gian cần thiết.

### Xử lý từng phần tử mà không chặn thread

Có thể biến mỗi phần tử thành một thao tác xử lý bất đồng bộ bằng concatMap hoặc flatMap:

~~~java
public Flux<ProcessedPerson> processPeople() {
    return personStreamReader.streamActivePeople()
        .concatMap(person ->
            enrichmentService.enrich(person)
        );
}
~~~

concatMap xử lý tuần tự từng publisher con và giữ thứ tự phát ra. Cách này phù hợp khi thao tác xử lý tiếp theo cần giới hạn số việc đang chạy hoặc phụ thuộc thứ tự.

Nếu các thao tác độc lập và có thể chạy song song, flatMap cho phép giới hạn concurrency và prefetch:

~~~java
public Flux<ProcessedPerson> processPeopleConcurrently() {
    return personStreamReader.streamActivePeople()
        .flatMap(
            person -> enrichmentService.enrich(person),
            8,
            1
        );
}
~~~

Ở đây concurrency là 8 publisher con cùng hoạt động và prefetch là 1 phần tử cho mỗi publisher con. Hãy chọn các giá trị dựa trên độ trễ và lượng tài nguyên mà mỗi tác vụ tiêu thụ. Tăng concurrency quá cao có thể làm tăng số request đồng thời, buffer và tải database/dịch vụ downstream.

publishOn cũng có thể tạo hàng đợi giữa các scheduler. Khi dùng operator có tham số prefetch, hãy chọn kích thước phù hợp thay vì mặc định tăng buffer không cần thiết:

~~~java
import reactor.core.scheduler.Schedulers;

public Flux<PersonSummary> processOnCpuScheduler() {
    return personStreamReader.streamActivePeople()
        .publishOn(Schedulers.parallel(), 64)
        .map(this::calculateSummary);
}
~~~

Chỉ chuyển scheduler khi có lý do về xử lý CPU hoặc tách luồng công việc. Không dùng Schedulers.boundedElastic() để che giấu thao tác blocking trong pipeline database reactive; hãy thay thao tác blocking bằng API reactive hoặc cô lập nó một cách có chủ đích.

## Fetch size và cơ chế kéo dữ liệu của reactive driver

Trong API imperative và async của Neo4j Java Driver, **fetch size** là số record được yêu cầu trong mỗi batch. Có thể cấu hình mặc định bằng **Config.Builder.withFetchSize(...)** hoặc ghi đè theo session bằng **SessionConfig.Builder.withFetchSize(...)**. Các tùy chọn này áp dụng cho **Session** và **AsyncSession**.

Với **Reactive Session**, batch size được điều khiển bởi demand từ subscription. Vì vậy, không nên coi **Config.Builder.withFetchSize(...)** là nút điều chỉnh fetch batch cho **ReactiveNeo4jClient**. Trong pipeline SDN reactive, subscriber và các Reactor operator quyết định lượng demand được truyền upstream; driver dùng demand đó để điều tiết việc kéo record từ Neo4j.

Điều này tạo ra ba khái niệm cần tách biệt:

| Khái niệm | Phạm vi | Tác dụng |
|---|---|---|
| **Subscription demand** | Reactive Streams | Số phần tử downstream đang yêu cầu |
| **limitRate/prefetch** | Reactor pipeline | Cách chia và giới hạn request truyền lên upstream |
| **Driver fetch size** | Session/AsyncSession imperative hoặc async | Số record trong mỗi batch của các API đó; không cấu hình batch cho Reactive Session |

Không khái niệm nào trong ba khái niệm trên giới hạn tổng số dòng mà Cypher trả về. Nếu query có 500.000 dòng, pipeline reactive vẫn có thể phát đủ 500.000 dòng qua nhiều lần request. Dùng **LIMIT** hoặc điều kiện lọc nếu cần giới hạn tổng kết quả.

### Config.Builder.withFetchSize dùng cho Session và AsyncSession

Đoạn cấu hình sau minh họa fetch size cho Driver dùng với API imperative hoặc async:

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Config;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;

Config config = Config.builder()
    .withFetchSize(512)
    .build();

Driver driver = GraphDatabase.driver(
    "neo4j://localhost:7687",
    AuthTokens.basic("neo4j", "password"),
    config
);
~~~

Đây là ví dụ cấu hình Driver độc lập cho **Session** và **AsyncSession**. Giá trị 512 không điều chỉnh batch của Reactive Session. Trong ứng dụng Spring Boot đã tự cấu hình Driver, không tạo thêm Driver thứ hai chỉ để thay đổi cấu hình cho một use case. Nếu ứng dụng đồng thời dùng API imperative/async và reactive, hãy hiểu rõ phạm vi áp dụng của fetch size trước khi thay đổi cấu hình chung.

Không sao chép mật khẩu ví dụ vào source code. Dùng secret/configuration bên ngoài và cơ chế authentication phù hợp với môi trường triển khai.

### Điều chỉnh demand và operator prefetch bằng đo lường

Trong pipeline reactive, hãy điều chỉnh request size qua các operator có hỗ trợ backpressure thay vì dựa vào Driver fetch size. Record có thể chỉ gồm vài scalar hoặc chứa nhiều node, relationship và property; vì vậy, cùng một demand vẫn có thể tương ứng với lượng byte khác nhau.

Khi tinh chỉnh:

1. Bắt đầu với pipeline đơn giản và giữ nguyên query, dữ liệu thử nghiệm.
2. Dùng **limitRate** hoặc tham số prefetch của operator ở mức vừa phải.
3. Đo thời gian tới record đầu tiên, throughput và thời gian hoàn thành.
4. Theo dõi bộ nhớ heap, số kết nối đang dùng và thời gian giữ connection.
5. Thử các mức demand, prefetch và concurrency khác nhau.
6. Lặp lại khi có nhiều subscription đồng thời và record có kích thước đại diện.

Tải nhiều stream đồng thời làm tổng buffer tăng. Có thể hình dung gần đúng lượng dữ liệu đang chờ theo số subscription hoạt động, số phần tử được prefetch ở từng operator và kích thước trung bình mỗi record. Đây chỉ là mô hình ước lượng: driver, protocol và pipeline có thể giữ dữ liệu theo nhiều cấu trúc khác nhau.

## Những operator có thể làm tích tụ dữ liệu

Một pipeline reactive có thể trở nên tốn bộ nhớ nếu operator buộc phải giữ nhiều hoặc toàn bộ phần tử trước khi phát kết quả.

### collectList và collectMap

collectList() tiêu thụ toàn bộ Flux rồi tạo một List chứa mọi phần tử:

~~~java
Mono<List<PersonSummary>> allPeople =
    personStreamReader.streamActivePeople()
        .collectList();
~~~

Với tập kết quả nhỏ, đây là cách tiện lợi. Với hàng trăm nghìn hoặc hàng triệu record, list có thể chiếm nhiều heap và gây OutOfMemoryError. collectMap() cũng giữ dữ liệu theo key cho tới khi upstream hoàn tất.

Nếu downstream có thể xử lý từng record, hãy giữ kiểu trả về Flux<T> và xử lý từng phần tử. Nếu nghiệp vụ thực sự cần tổng hợp toàn bộ dữ liệu, hãy giới hạn số lượng đầu vào hoặc chuyển việc tổng hợp sang database.

### sort và buffer không giới hạn

Các thao tác sort toàn bộ Flux thường phải thu thập dữ liệu trước khi có thể phát theo thứ tự. Không dùng sort trong bộ nhớ cho một kết quả rất lớn nếu Neo4j có thể sắp xếp bằng ORDER BY:

~~~cypher
MATCH (p:Person)
WHERE p.active = true
RETURN p.employeeCode AS employeeCode,
       p.fullName AS fullName
ORDER BY p.employeeCode;
~~~

onBackpressureBuffer() không giới hạn có thể giữ một lượng lớn phần tử khi upstream phát nhanh hơn downstream. Với nguồn đã hỗ trợ backpressure như reactive driver, hãy ưu tiên truyền demand đúng cách. Nếu cần buffer, đặt giới hạn rõ ràng và định nghĩa cách xử lý khi đầy; không dùng buffer vô hạn để che giấu downstream chậm.

Không dùng onBackpressureDrop() hoặc onBackpressureLatest() cho kết quả truy vấn nghiệp vụ nếu mỗi record đều phải được xử lý. Những operator này có thể bỏ record cũ hoặc thay record chưa xử lý bằng record mới.

### publishOn, flatMap và prefetch

Các operator bất đồng bộ có thể tạo hàng đợi nội bộ. Một pipeline dùng flatMap với concurrency lớn và prefetch cao có thể giữ nhiều publisher con và nhiều phần tử đang chờ cùng lúc.

Giảm concurrency, prefetch hoặc dùng concatMap khi cần giới hạn số việc đồng thời. Không tăng các giá trị này chỉ để cải thiện throughput của một bài đo đơn lẻ; phải kiểm tra cả độ ổn định của heap và connection pool dưới tải thực tế.

## Kết hợp LIMIT, phân trang và streaming

Streaming không thay thế mọi hình thức phân trang. Chọn chiến lược dựa trên cách client sử dụng dữ liệu:

| Nhu cầu | Chiến lược |
|---|---|
| Giao diện hiển thị một trang nhỏ | Cypher SKIP/LIMIT hoặc API phân trang phù hợp |
| Xuất dữ liệu lớn theo luồng | Flux streaming với backpressure |
| Xử lý tuần tự từng record | concatMap hoặc limitRate |
| Xử lý song song có giới hạn | flatMap với concurrency/prefetch được chọn |
| Duyệt dữ liệu rất lớn, có cập nhật liên tục | Keyset/cursor pagination theo khóa ổn định |
| Chỉ cần thống kê hoặc tổng hợp | Thực hiện count, collect hoặc aggregation trong Cypher khi phù hợp |

Ví dụ lấy một trang hữu hạn:

~~~java
public Flux<PersonSummary> findPage(long skip, long limit) {
    return client.query("""
            MATCH (p:Person)
            WHERE p.active = true
            RETURN p.employeeCode AS employeeCode,
                   p.fullName AS fullName
            ORDER BY p.employeeCode
            SKIP $skip
            LIMIT $limit
            """)
        .bind(skip).to("skip")
        .bind(limit).to("limit")
        .fetchAs(PersonSummary.class)
        .mappedBy((typeSystem, record) -> new PersonSummary(
            record.get("employeeCode").asString(),
            record.get("fullName").asString()
        ))
        .all();
}
~~~

Đây là một Flux hữu hạn do Cypher giới hạn bằng LIMIT. Với trang sâu, offset lớn có thể tốn chi phí; cân nhắc keyset pagination dựa trên employeeCode nếu thứ tự nghiệp vụ cho phép.

Đối với xuất dữ liệu, không nhất thiết phải dùng collectList() để tạo một file hoặc payload lớn trong bộ nhớ. Có thể ghi từng phần tử vào một sink hỗ trợ streaming hoặc xử lý theo từng chunk có giới hạn. Sink phải hỗ trợ backpressure hoặc có chiến lược buffer hữu hạn để tốc độ ghi không làm bộ nhớ tăng vô hạn.

## Transaction và vòng đời subscription

Reactive transaction được gắn với Reactor Context, không dựa vào thread-local như cách quản lý imperative thông thường. Vì vậy, không nên tự subscribe bên trong service rồi trả về một publisher khác; việc đó tách subscription thực tế khỏi pipeline mà transaction manager đang quản lý.

Có thể dùng TransactionalOperator để bọc một publisher:

~~~java
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Flux;

public Flux<PersonSummary> streamInTransaction(
        TransactionalOperator transactionalOperator) {

    return personStreamReader.streamActivePeople()
        .as(transactionalOperator::transactional);
}
~~~

TransactionalOperator cần được tạo từ ReactiveTransactionManager của Neo4j. Các thao tác database trong publisher phải dùng cùng transaction manager và giữ trong cùng Reactor Context.

Một stream rất dài trong một transaction có thể giữ connection và transaction lâu. Điều này làm giảm số connection còn sẵn cho request khác, tăng thời gian giữ transaction state và có thể gây áp lực lên pool. Với tác vụ export kéo dài, cân nhắc chia thành các trang hoặc chunk có transaction ngắn, thay vì mở một transaction duy nhất trong thời gian rất dài.

Khi subscriber hủy subscription, publisher upstream nhận tín hiệu cancel. Driver có thể dừng việc lấy thêm record và giải phóng tài nguyên khi kết quả/transaction được đóng theo vòng đời tương ứng. Đừng nuốt cancellation hoặc chuyển query sang subscription tự tạo không được quản lý; cần để pipeline hoàn tất hoặc bị hủy một cách rõ ràng.

Không gọi block(), blockFirst() hoặc blockLast() trên event-loop thread của ứng dụng WebFlux. Các lời gọi này chặn thread và phá vỡ lợi ích của mô hình reactive. Trả publisher cho framework WebFlux hoặc ghép publisher vào pipeline của tầng gọi.

## Kiểm thử backpressure và cancellation

Có thể dùng Reactor Test StepVerifier để xác nhận publisher không phát dữ liệu trước khi subscriber yêu cầu:

~~~java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

@Test
void emitsOnlyWhenDemandArrives() {
    StepVerifier.create(personStreamReader.streamActivePeople(), 0)
        .thenRequest(1)
        .expectNextCount(1)
        .thenRequest(2)
        .expectNextCount(2)
        .thenCancel()
        .verify();
}
~~~

Test tạo subscriber ban đầu với demand bằng 0, sau đó yêu cầu một phần tử rồi thêm hai phần tử. Cuối cùng subscriber cancel. Đây là cách kiểm tra hành vi demand của pipeline ở mức Reactor; để kiểm tra tích hợp driver và database, chạy cùng test với Neo4j test instance hoặc Testcontainers và fixture có ít nhất ba người phù hợp.

Nên bổ sung các tình huống:

- Downstream xử lý chậm trong khi query có nhiều record.
- Hủy subscription sau một số phần tử và xác nhận tài nguyên được giải phóng.
- Nhiều subscription đồng thời với demand, prefetch và concurrency khác nhau.
- Record chứa nhiều property hoặc relationship hơn trường hợp thông thường.
- Pipeline có publishOn hoặc flatMap với prefetch/concurrency được giới hạn.
- Kiểm tra heap và connection pool trong một bài kiểm thử tải đại diện.

Có thể quan sát request và vòng đời stream khi phát triển:

~~~java
return personStreamReader.streamActivePeople()
    .doOnRequest(n -> log.debug("Requested {} records", n))
    .doFinally(signal -> log.debug("Stream finished with {}", signal));
~~~

Không ghi toàn bộ nội dung record vào log cho một luồng dữ liệu lớn. Log số lượng request, thời gian, trạng thái hoàn tất/hủy và định danh truy vấn đủ để chẩn đoán mà không làm tăng I/O hoặc lộ dữ liệu.

## Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Cho rằng Flux luôn giữ bộ nhớ thấp | Operator phía sau có thể gom toàn bộ kết quả | Kiểm tra từng operator và giữ pipeline streaming |
| Nhầm fetch size với LIMIT | Query vẫn trả tổng số record không giới hạn | Dùng Cypher LIMIT nếu cần giới hạn tổng số dòng |
| Tăng fetch size quá lớn cho Session/AsyncSession | Tăng lượng dữ liệu đang chờ trong mỗi batch của API đó | Đo dưới tải thực tế; với reactive session hãy điều chỉnh demand và operator prefetch |
| Dùng collectList() cho hàng triệu record | List chiếm heap lớn hoặc gây OOM | Xử lý từng phần tử hoặc theo chunk hữu hạn |
| Dùng sort() trong Reactor cho stream lớn | Phải giữ nhiều hoặc toàn bộ kết quả trước khi phát | Đưa ORDER BY vào Cypher |
| Dùng buffer không giới hạn | Bộ nhớ tăng khi downstream chậm | Giữ backpressure hoặc đặt giới hạn buffer |
| flatMap concurrency/prefetch quá lớn | Nhiều tác vụ và phần tử chờ đồng thời | Giới hạn concurrency và prefetch |
| Gọi block() trên WebFlux event loop | Chặn thread xử lý request | Trả Mono/Flux và ghép pipeline |
| Tự subscribe() trong service | Mất kiểm soát lỗi, cancellation và transaction context | Trả publisher cho tầng gọi |
| Giữ một transaction cho export rất lâu | Giữ connection và transaction state lâu | Chia thành chunk hoặc trang có transaction ngắn |
| Hủy stream nhưng không quản lý vòng đời | Có thể giữ tài nguyên lâu hơn cần thiết | Để driver và transaction manager xử lý cancel/cleanup qua publisher |

## Bài tập thực hành

Với repository PersonRepository và entity Person, hãy thực hiện:

1. Viết reactive repository method trả Flux<Person> cho các nhân viên đang hoạt động.
2. Viết ReactiveNeo4jClient query chỉ trả employeeCode và fullName thành DTO.
3. Thêm limitRate(128) và quan sát request upstream.
4. Dùng concatMap để xử lý từng Person theo thứ tự.
5. Dùng flatMap với concurrency 8 và prefetch 1; so sánh với pipeline tuần tự.
6. Dùng **Config.Builder.withFetchSize(...)** trong một ví dụ Session/AsyncSession và xác nhận setting này không điều khiển Reactive Session.
7. Với reactive query, so sánh các mức demand qua **limitRate** với **LIMIT** trong Cypher bằng cách giữ nguyên dữ liệu và thay đổi từng giá trị riêng biệt.
8. Thử collectList() trên tập dữ liệu lớn rồi so sánh bộ nhớ với pipeline xử lý từng record.
9. Dùng StepVerifier yêu cầu từng phần tử, sau đó cancel và xác nhận publisher kết thúc.
10. Bọc publisher bằng TransactionalOperator và quan sát thời gian giữ transaction/connection khi stream kéo dài.
11. Thiết kế một luồng export theo chunk có giới hạn để tránh giữ toàn bộ kết quả trong heap.
12. Viết integration/load test với nhiều subscriber đồng thời để chọn demand, operator prefetch và concurrency phù hợp.

Khi tiêu thụ kết quả lớn từ Spring Data Neo4j reactive, hãy giữ demand có kiểm soát từ subscriber tới driver, điều chỉnh **limitRate**, prefetch và concurrency dựa trên kích thước record cùng tải đồng thời, đồng thời tránh các operator gom toàn bộ dữ liệu vào bộ nhớ. Driver fetch size cấu hình qua Config.Builder áp dụng cho Session/AsyncSession; Reactive Session điều tiết batch theo subscription demand. Dùng LIMIT hoặc cursor khi cần giới hạn tập kết quả, giữ transaction trong thời gian hợp lý và để cancellation đi xuyên suốt pipeline để giải phóng tài nguyên.

Tài liệu tham khảo chính thức:

- [Spring Data Neo4j - Neo4jClient và ReactiveNeo4jClient](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
- [Neo4j Java Driver - Reactive programming](https://neo4j.com/docs/java-manual/current/reactive/)
- [Neo4j Java Driver API - Config.ConfigBuilder](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/Config.ConfigBuilder.html)
- [Neo4j Java Driver API - SessionConfig.Builder](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/SessionConfig.Builder.html)
- [Project Reactor - Backpressure and request](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html)

