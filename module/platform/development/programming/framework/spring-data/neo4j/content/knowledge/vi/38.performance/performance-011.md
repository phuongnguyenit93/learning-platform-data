# Đo riêng chi phí Neo4j, driver và ánh xạ đối tượng

Khi một thao tác đọc bằng Spring Data Neo4j (SDN) chậm, thời gian người dùng chờ không chỉ là thời gian Neo4j chạy Cypher. Tổng thời gian có thể gồm lấy connection, routing tới server, gửi query qua Bolt, thực thi và đọc graph, truyền records về JVM, ánh xạ records thành entity hoặc projection, xử lý nghiệp vụ và tạo response.

Muốn tối ưu đúng chỗ, hãy đo từng lớp bằng công cụ phù hợp. Dùng timer ở application để biết thời gian end-to-end, dùng summary của Neo4j Java Driver để quan sát thời gian server, dùng `EXPLAIN`/`PROFILE` để hiểu query plan và DB hits, rồi so sánh entity mapping với projection có cùng query shape để ước lượng chi phí ánh xạ. Một con số duy nhất từ log không đủ để kết luận toàn bộ độ trễ đến từ database.

## 1. Phân rã thời gian của một lần đọc

~~~mermaid
flowchart LR
    A[HTTP request] --> B[Service / repository]
    B --> C[Driver: connection và Bolt]
    C --> D[Neo4j: lập kế hoạch và chạy Cypher]
    D --> E[Trả records]
    E --> F[SDN mapping]
    F --> G[Business logic và response]
    G --> H[HTTP response]
~~~

| Lớp | Công việc | Công cụ đo phù hợp |
|---|---|---|
| Application | Thời gian service hoặc repository hoàn tất | Micrometer `Timer`, trace |
| Driver và mạng | Session/connection, routing, round trip, nhận records | Driver summary, driver logs, trace |
| Neo4j server | Lập kế hoạch, index/page cache, duyệt graph, thực thi operator | `EXPLAIN`, `PROFILE`, query log, server metrics |
| SDN mapping | Chuyển records thành entity, relationship, collection và projection | So sánh cùng query với mapping khác nhau, JFR/profiler |
| Xử lý ứng dụng | Business logic, gom collection, serialize JSON | Timer quanh từng boundary, HTTP metrics |

Các lớp có thể chồng lấp. Timer quanh repository bao gồm thời gian chờ kết quả, truyền records và mapping entity. Vì vậy, không thể lấy timer repository trừ `resultAvailableAfter` rồi gọi phần chênh lệch là “mapping time”. Phần chênh lệch còn có thể chứa connection acquisition, network, result streaming, transaction và scheduling.

## 2. Đo end-to-end ở application

Đặt timer quanh đúng boundary muốn quan sát. Timer quanh service cho biết thời gian toàn use case; timer quanh repository thu hẹp phạm vi tới persistence operation.

Ví dụ imperative với Micrometer:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class PersonQueryService {

    private final PersonRepository people;
    private final Timer repositoryTimer;

    public PersonQueryService(PersonRepository people, MeterRegistry registry) {
        this.people = people;
        this.repositoryTimer = Timer.builder("app.neo4j.repository")
            .description("Time spent waiting for an SDN repository operation")
            .tag("operation", "find-by-person-key")
            .register(registry);
    }

    public Person findByPersonKey(String personKey) {
        return repositoryTimer.record(
            () -> people.findByPersonKey(personKey).orElse(null)
        );
    }
}
~~~

Timer trên đo toàn bộ lời gọi repository, gồm cả việc SDN nhận và ánh xạ kết quả. Nó không chỉ đo thời gian server chạy Cypher.

Với reactive repository, timer phải bắt đầu khi publisher được subscribe và dừng khi publisher kết thúc. Không tạo một `Timer.Sample` dùng chung ở ngoài publisher vì nhiều subscription có thể chạy ở các thời điểm khác nhau:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class ReactivePersonQueryService {

    private final ReactivePersonRepository people;
    private final MeterRegistry registry;
    private final Timer repositoryTimer;

    public ReactivePersonQueryService(
            ReactivePersonRepository people, MeterRegistry registry) {
        this.people = people;
        this.registry = registry;
        this.repositoryTimer = Timer.builder("app.neo4j.repository")
            .tag("operation", "find-by-region")
            .register(registry);
    }

    public Flux<Person> findByRegion(String region) {
        return Flux.defer(() -> {
            Timer.Sample sample = Timer.start(registry);
            return people.findByRegion(region)
                .doFinally(signal -> sample.stop(repositoryTimer));
        });
    }
}
~~~

Timer reactive dừng khi publisher kết thúc, lỗi hoặc bị hủy. Nếu downstream yêu cầu kết quả chậm, backpressure có thể kéo dài thời gian hoàn tất; hãy ghi rõ boundary đang đo và tránh so sánh với timer đo riêng server.

Theo dõi số lần gọi, throughput, median, p95/p99, tỷ lệ lỗi, timeout, cancellation và số records trả về. Không tạo metric tag từ `personKey`, email, query text hoặc request ID vì cardinality cao làm tăng số time series và có thể lộ dữ liệu. Dùng trace/span để giữ định danh của từng request.

## 3. Đọc thời gian server từ ResultSummary của Driver

Neo4j Java Driver trả về `ResultSummary` sau khi toàn bộ records được tiêu thụ. Hai trường thời gian quan trọng:

- `resultAvailableAfter`: thời gian server cần để kết quả sẵn sàng cho client bắt đầu tiêu thụ.
- `resultConsumedAfter`: thời gian server cần để tiêu thụ xong kết quả.

Hai giá trị này do server cung cấp. Chúng hữu ích để quan sát query, nhưng không phải thời gian end-to-end của JVM và không bao gồm toàn bộ chi phí mapping entity của SDN.

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.neo4j.driver.Driver;
import org.neo4j.driver.Record;
import org.neo4j.driver.ResultSummary;
import org.neo4j.driver.SessionConfig;

public class DriverQueryMeasurement {

    public Measurement readPeople(Driver driver, String database) {
        try (var session = driver.session(
                SessionConfig.builder().withDatabase(database).build())) {
            return session.executeRead(tx -> {
                var result = tx.run("""
                    MATCH (p:Person)
                    WHERE p.region = $region
                    RETURN p.personKey AS personKey, p.name AS name
                    """, Map.of("region", "North"));

                List<Record> records = result.list();
                ResultSummary summary = result.consume();
                return new Measurement(
                    records.size(),
                    summary.resultAvailableAfter(TimeUnit.MILLISECONDS),
                    summary.resultConsumedAfter(TimeUnit.MILLISECONDS)
                );
            });
        }
    }

    public record Measurement(
        int recordCount,
        long resultAvailableAfterMs,
        long resultConsumedAfterMs
    ) {}
}
~~~

Ví dụ dùng Driver trực tiếp để quan sát server summary và số records; nó không chạy qua SDN entity mapper. `result.list()` tiêu thụ records về JVM, còn `consume()` lấy summary sau khi kết quả đã được tiêu thụ. Với kết quả lớn, `list()` giữ toàn bộ records trong bộ nhớ; không dùng cách này như benchmark streaming cho dataset rất lớn.

Nếu chỉ cần server summary mà không cần nội dung kết quả, có thể gọi `consume()` trực tiếp. Khi muốn đo chi phí xử lý từng record ở client, hãy đọc records theo stream và đặt timer riêng quanh bước chuyển đổi.

## 4. Phân biệt server time với client wall-clock

Một query có thể có `resultAvailableAfter` thấp nhưng application timer cao. Một số nguyên nhân:

- Driver phải chờ connection khả dụng trong pool.
- Driver phải cập nhật routing table hoặc thiết lập kết nối mới.
- Network latency giữa application và Neo4j cao.
- Result stream có nhiều records hoặc payload lớn.
- JVM cần giải mã Bolt values và cấp phát object.
- SDN cần ánh xạ node, relationship, property và collection.
- Application xử lý kết quả trước khi publisher hoặc method hoàn tất.

Ngược lại, server time cao cùng với application time cao thường là dấu hiệu nên kiểm tra query plan, index, cardinality, page cache hoặc tải server.

| Quan sát | Giả thuyết cần kiểm tra |
|---|---|
| Server time cao, client time cũng cao | Cypher, index, DB hits, lock contention, server resource |
| Server time thấp, client time cao | Network, pool wait, routing, streaming, mapping hoặc application |
| `resultAvailableAfter` thấp nhưng `resultConsumedAfter` cao | Kết quả lớn hoặc server mất thời gian tạo/stream phần còn lại |
| Repository entity chậm hơn custom projection với cùng query | Có thể có chi phí mapping entity hoặc graph object lớn |
| Lần đầu chậm, các lần sau nhanh | JVM warm-up, connection setup, page cache hoặc query plan cache |

Đây là hướng điều tra, không phải kết luận tự động. Hãy đo lặp lại và kiểm tra thêm các lớp liên quan.

## 5. Dùng EXPLAIN và PROFILE để đo phần việc của Cypher

`EXPLAIN` yêu cầu Neo4j lập execution plan nhưng không chạy query. Nó cung cấp số hàng ước tính và các operator dự kiến.

`PROFILE` thực thi query và trả execution plan kèm số liệu thực tế:

- `Rows`: số hàng thực tế đi qua operator.
- `DB Hits`: số thao tác truy cập storage engine.
- `Memory (Bytes)`: bộ nhớ peak do operator sử dụng.
- `Page Cache Hits/Misses`: thông tin page cache khi edition và runtime hỗ trợ.
- `Time (ms)`: thời gian ở pipeline/operator trong các runtime có hỗ trợ.
- `Indexes Used`: index mà query thực sự sử dụng.

Ví dụ:

~~~cypher
PROFILE
MATCH (p:Person {personKey: $personKey})
OPTIONAL MATCH (p)-[:MEMBER_OF]->(team:Team)
RETURN p.personKey, p.name, collect(team.name) AS teams;
~~~

Khi đọc plan:

1. Xem operator đầu tiên có dùng index seek hay phải scan nhiều node.
2. So sánh `Estimated Rows` với `Rows` thực tế để phát hiện ước lượng cardinality sai lệch.
3. Tìm operator có nhiều DB hits hoặc tạo nhiều rows trung gian.
4. Kiểm tra `Expand(All)`, `CartesianProduct`, `Sort`, `EagerAggregation` và các operator tiêu tốn bộ nhớ.
5. Xác nhận query trả đúng số records và đúng dữ liệu nghiệp vụ sau khi tối ưu.

`PROFILE` thực sự chạy câu lệnh. Nếu query có `CREATE`, `MERGE`, `SET` hoặc `DELETE`, nó có thể thay đổi dữ liệu. Chỉ chạy profiling trên dữ liệu thử nghiệm hoặc query có thể thực thi an toàn; không đưa `PROFILE` vào luồng request production. Profiling cũng tiêu tốn thêm tài nguyên nên chỉ dùng khi đang điều tra.

Tài liệu chính thức: [Understanding query plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/).

## 6. Tách chi phí ánh xạ entity khỏi chi phí query

Timer quanh repository đo cả query, truyền dữ liệu và mapping. Để kiểm tra phần mapping, hãy dùng cùng một query và cùng result shape, rồi so sánh:

- SDN repository trả về entity đầy đủ.
- `Neo4jClient` trả về projection/DTO tối giản.
- Mapping function chạy trên records đã lấy về trong bộ nhớ nếu cần benchmark riêng chi phí chuyển đổi object.

Ví dụ custom projection với `Neo4jClient`:

~~~java
import java.util.List;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class PersonReadProjection {

    private final Neo4jClient client;

    public PersonReadProjection(Neo4jClient client) {
        this.client = client;
    }

    public List<PersonView> findByRegion(String region) {
        return client.query("""
                MATCH (p:Person)
                WHERE p.region = $region
                RETURN p.personKey AS personKey, p.name AS name
                """)
            .bind(region).to("region")
            .fetchAs(PersonView.class)
            .mappedBy((typeSystem, record) ->
                new PersonView(
                    record.get("personKey").asString(),
                    record.get("name").asString()
                )
            )
            .all();
    }

    public record PersonView(String personKey, String name) {}
}
~~~

Khi so sánh với repository, hãy giữ nguyên điều kiện lọc, parameter, database, số records, property trả về và trạng thái cache. Nếu repository load thêm relationship trong khi projection chỉ trả hai scalar property, phép đo phản ánh cả khác biệt về lượng dữ liệu, không chỉ chi phí mapper.

`Neo4jClient` vẫn dùng Driver và vẫn có chi phí network/record decoding. So sánh này giúp đánh giá overhead của đường mapping trong một use case gần thực tế; nó không phải phép đo thuần CPU của mapper.

## 7. Benchmark riêng mapping function trong bộ nhớ

Khi cần biết chi phí tạo object, có thể lấy một tập records đại diện rồi benchmark mapping function mà không gọi database trong vòng đo. JMH phù hợp cho microbenchmark CPU và allocation:

~~~java
import java.util.List;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
public class PersonMappingBenchmark {

    private List<PersonRow> rows;

    @Setup
    public void setUp() {
        rows = java.util.stream.IntStream.range(0, 1_000)
            .mapToObj(i -> new PersonRow("person-" + i, "Person " + i))
            .toList();
    }

    @Benchmark
    public List<PersonView> mapRows() {
        return rows.stream()
            .map(row -> new PersonView(row.personKey(), row.name()))
            .toList();
    }

    public record PersonRow(String personKey, String name) {}
    public record PersonView(String personKey, String name) {}
}
~~~

Đoạn mã minh họa cấu trúc benchmark; dự án benchmark cần thêm JMH dependency và cấu hình runner phù hợp. Dùng dataset đủ lớn và giống phân bố thực tế. JMH nên được chạy ngoài production với cấu hình JVM và warm-up phù hợp.

Benchmark này chỉ đo việc tạo DTO từ object đã có trong bộ nhớ. Nó không đo SDN metadata lookup, driver decoding, relationship mapping, transaction hoặc Neo4j. Để điều tra allocation và CPU trong ứng dụng thật, có thể dùng Java Flight Recorder hoặc profiler tương đương.

## 8. Các yếu tố làm chi phí mapping tăng

Chi phí mapping thường phụ thuộc vào kích thước kết quả và độ phức tạp của object graph:

- Số records được trả về.
- Số property trên mỗi node/relationship.
- Số relationship cần ánh xạ.
- Fan-out của relationship và số entity duy nhất được tạo.
- Kiểu dữ liệu cần chuyển đổi, ví dụ temporal, spatial hoặc collection.
- Constructor, converter và custom mapping function.
- Số object trung gian và lượng allocation/GC.

Một query trả 100 `Person` với vài scalar property thường khác đáng kể với query trả 100 `Person`, mỗi người có hàng trăm `Order` và nhiều relationship properties.

Hãy chỉ trả những dữ liệu use case cần. Với màn hình danh sách, projection nhỏ thường phù hợp hơn việc hydrate toàn bộ aggregate. Với use case nghiệp vụ cần thay đổi graph, load entity đầy đủ có thể là lựa chọn đúng dù chi phí mapping cao hơn.

## 9. Tránh đo nhầm do result size và relationship fan-out

Hai query có thời gian server tương đương vẫn có thể tạo chi phí client khác nhau nếu một query trả nhiều records hoặc payload lớn hơn.

Ví dụ query có `collect()` có thể trả ít records nhưng mỗi record chứa một list lớn. Query không `collect()` có thể trả nhiều records nhỏ. Hãy ghi nhận:

- Số records ở top-level.
- Kích thước collection được trả trong mỗi record.
- Số node/relationship được materialize.
- Dung lượng payload gần đúng.
- Số object được tạo và lượng heap sau khi xử lý.

Đừng chỉ nhìn số hàng trả về để kết luận mapping nhẹ. Một record chứa hàng nghìn relationship cũng có thể tạo object graph lớn.

## 10. Kiểm tra logging của Spring Data Neo4j

Từ Spring Data Neo4j 7.1.5, SDN cung cấp logger `org.springframework.data.neo4j.cypher` cho các statement được SDN gọi và các notification do server gửi về. Các logger con cho phép phân loại notification:

- `org.springframework.data.neo4j.cypher.performance`
- `org.springframework.data.neo4j.cypher.hint`
- `org.springframework.data.neo4j.cypher.unrecognized`
- `org.springframework.data.neo4j.cypher.unsupported`
- `org.springframework.data.neo4j.cypher.deprecation`
- `org.springframework.data.neo4j.cypher.generic`
- `org.springframework.data.neo4j.cypher.security`
- `org.springframework.data.neo4j.cypher.topology`

Có thể bật log có chọn lọc ở môi trường development hoặc staging:

~~~yaml
logging:
  level:
    org.springframework.data.neo4j.cypher: INFO
    org.springframework.data.neo4j.cypher.performance: WARN
    org.springframework.data.neo4j.cypher.deprecation: WARN
~~~

Điều chỉnh level theo logging backend và phiên bản SDN của dự án. Không bật log quá chi tiết lâu dài trong production nếu chưa đánh giá dung lượng log, tác động hiệu năng và nguy cơ lộ query/parameter nhạy cảm.

Tài liệu: [Spring Data Neo4j – Logging](https://docs.spring.io/spring-data/neo4j/reference/appendix/logging.html).

## 11. Theo dõi phía Neo4j server

Khi application timer và driver summary cho thấy server là phần chậm, hãy quan sát thêm tài nguyên Neo4j:

- CPU và memory của server.
- Heap, garbage collection và số thread.
- Bolt connections và tải request.
- Page cache hit/miss và eviction.
- Transaction đang hoạt động, lock wait và deadlock.
- Database operation metrics.
- Query log và các query có thời gian thực thi cao.

Neo4j Operations Manual có các metric cho Bolt, page cache, GC, thread, database operation, web server và JVM. Việc xuất metrics và một số nhóm metric phụ thuộc edition/cấu hình. Đối chiếu metric server với timestamp và trace của request ứng dụng để tránh ghép nhầm hai khoảng thời gian.

Tài liệu: [Neo4j Operations Manual – Metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/).

## 12. Thiết kế benchmark công bằng

Để so sánh hai cách truy cập SDN, hãy cố định các yếu tố:

1. Cùng Neo4j instance, database, user và topology.
2. Cùng dataset, index, constraint và trạng thái page cache.
3. Cùng Cypher logic, parameters và số records đầu ra.
4. Cùng số lượng request đồng thời và giới hạn connection pool.
5. Có warm-up JVM và query plan trước khi ghi số liệu steady-state.
6. Chạy đủ nhiều lần để tính median, p95 và p99.
7. Tách kết quả cold start với warm steady-state.
8. Đo allocation/GC nếu nghi ngờ mapping tạo nhiều object.
9. Lưu query plan, server summary và application timer cho cùng lượt đo.
10. Xác nhận kết quả dữ liệu giống nhau trước khi so sánh tốc độ.

Không lấy lần chạy đầu của một phương án so với lần chạy thứ mười của phương án khác. Lần đầu có thể bao gồm thiết lập connection, tải page cache, JIT compilation hoặc compile query plan.

## 13. Đọc kết quả và chọn bước tối ưu

| Dấu hiệu | Bước điều tra tiếp theo |
|---|---|
| `PROFILE` cho thấy scan lớn hoặc DB hits cao | Kiểm tra label/property predicate, index, relationship pattern và cardinality |
| Estimated Rows lệch xa Rows thực tế | Kiểm tra statistics, index và hình dạng query |
| Server time tốt nhưng repository chậm | Đo connection/pool, result transfer, entity mapping và business logic |
| Entity mapping chậm hơn projection rõ rệt | Kiểm tra số property/relationship được hydrate và custom converter |
| Heap allocation/GC cao khi đọc graph | Giảm result size, projection, collection fan-out hoặc batch size |
| p95 tăng khi concurrency tăng | Kiểm tra connection pool, server saturation, lock contention và backpressure |
| Lần đầu chậm, sau đó nhanh | Tách cold start, page cache, query plan cache và JVM warm-up |

Chỉ tối ưu một lớp sau khi có số đo cho thấy lớp đó là bottleneck. Nếu query plan cho thấy Neo4j đang scan hàng triệu node, chuyển sang custom DTO mapper sẽ không giải quyết nguyên nhân chính. Nếu query server rất nhanh nhưng object graph khổng lồ được tạo ở JVM, thêm index có thể không cải thiện đáng kể.

## 14. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng thời gian repository làm thời gian Cypher | Đổ nhầm chi phí driver và mapping cho Neo4j | Đối chiếu application timer với Driver summary và `PROFILE` |
| Dùng `resultAvailableAfter` như tổng thời gian request | Bỏ qua result streaming, mapping và application | Đo wall-clock ở application riêng |
| So sánh hai query trả số lượng property khác nhau | Không thể cô lập chi phí mapper | Giữ query shape và result size tương đương |
| Chỉ đo một lần | Bị ảnh hưởng bởi cache, JIT và connection setup | Warm-up và đo nhiều lần |
| Dùng `PROFILE` cho write query trên production | Có thể thay đổi dữ liệu và tăng tải | Profile trên môi trường thử nghiệm với dữ liệu an toàn |
| Materialize kết quả rất lớn bằng `list()` | Tăng heap và GC, có thể OOM | Dùng streaming/backpressure hoặc batch có giới hạn |
| Bật log Cypher chi tiết lâu dài | Tăng dung lượng log và nguy cơ lộ thông tin | Bật có chọn lọc trong thời gian điều tra |
| Gắn tag metric bằng ID hoặc query text | Cardinality tăng mạnh | Dùng operation name có tập giá trị hữu hạn |
| Cho rằng DTO luôn nhanh hơn entity | Có thể bỏ qua nhu cầu nghiệp vụ hoặc query shape khác | Đo với cùng dữ liệu và yêu cầu đầu ra |
| Tối ưu mapper khi server query đang scan lớn | Không tác động bottleneck chính | Tối ưu query plan và index trước |

## 15. Quy trình đo và điều tra hiệu năng

1. Đặt timer ở service và repository boundary để biết thời gian end-to-end.
2. Ghi nhận số records, payload size, throughput, median và p95/p99.
3. Lấy `ResultSummary` từ Driver cho query đại diện để quan sát `resultAvailableAfter` và `resultConsumedAfter`.
4. Chạy `EXPLAIN` để xem plan ước tính; dùng `PROFILE` có kiểm soát để đo rows, DB hits, memory và index usage.
5. Bật SDN Cypher notification logging có chọn lọc trong môi trường phù hợp.
6. So sánh entity mapping với `Neo4jClient` projection trên cùng query và result shape.
7. Nếu cần cô lập CPU mapping, benchmark mapper trong bộ nhớ bằng JMH hoặc dùng JFR/profiler.
8. Đối chiếu với Neo4j server metrics, Bolt connections, page cache, CPU và GC.
9. Thay đổi một yếu tố mỗi lần, chạy lại cùng workload và xác nhận kết quả nghiệp vụ.
10. Ghi lại baseline, query plan và cấu hình để so sánh sau các lần nâng cấp.

## 16. Tự kiểm tra

1. Vì sao thời gian gọi repository không đồng nghĩa thời gian Neo4j chạy Cypher?
2. `resultAvailableAfter` và `resultConsumedAfter` đo những gì?
3. Vì sao phải tiêu thụ hết records trước khi lấy `ResultSummary`?
4. `EXPLAIN` khác `PROFILE` ở việc thực thi query như thế nào?
5. Vì sao `PROFILE` có thể làm thay đổi dữ liệu?
6. Làm thế nào so sánh chi phí entity mapping với custom projection công bằng?
7. Vì sao số records không đủ để ước lượng kích thước object graph?
8. Khi nào nên dùng JMH và khi nào nên dùng integration benchmark?
9. Các dấu hiệu nào cho thấy bottleneck nằm ở driver/network thay vì Neo4j server?
10. Vì sao cần so sánh median và percentile thay vì chỉ nhìn trung bình?

Đo hiệu năng SDN hiệu quả cần tách ba góc nhìn: thời gian end-to-end ở application, thời gian server và query plan từ Neo4j, cùng chi phí nhận records và ánh xạ thành object trong JVM. Dùng cùng query, dữ liệu và điều kiện chạy khi so sánh; chỉ tối ưu lớp đã được số liệu xác nhận là bottleneck.

Tài liệu tham khảo:

- [Spring Data Neo4j – Logging](https://docs.spring.io/spring-data/neo4j/reference/appendix/logging.html)
- [Spring Data Neo4j – Neo4jClient](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
- [Neo4j Java Driver – Explore the query execution summary](https://neo4j.com/docs/java-manual/current/result-summary/)
- [Neo4j Java Driver API – ResultSummary](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/summary/ResultSummary.html)
- [Neo4j Cypher Manual – Understanding query plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Spring Framework – Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Neo4j Operations Manual – Metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/)
