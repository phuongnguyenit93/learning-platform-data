# Mô hình đồng bộ, bất đồng bộ và phản ứng trong Spring Data Cassandra

Khi truy cập **Apache Cassandra** từ ứng dụng Spring, chúng ta có thể thực hiện cùng một câu lệnh CQL theo ba mô hình: **đồng bộ (synchronous/imperative)**, **bất đồng bộ (asynchronous)** và **phản ứng (reactive)**. Chúng khác nhau chủ yếu ở cách mã gọi chờ kết quả, cách biểu diễn kết quả và cách tổ chức luồng xử lý; cả ba vẫn phải tuân theo thiết kế bảng theo truy vấn, khóa phân vùng, paging và mô hình nhất quán của Cassandra.

Bài học sử dụng **Spring Data Cassandra** để minh họa entity mapping, repository, `CassandraTemplate`, `AsyncCassandraTemplate`, `ReactiveCassandraTemplate` và khả năng kết hợp với CQL. Mục tiêu là biết mô hình nào phù hợp với từng kiểu tải và tránh nhầm lẫn giữa “không chặn luồng” với “truy vấn Cassandra nhanh hơn”.

## 1. Ba cách thực thi cùng một công việc

Giả sử một dịch vụ nhận yêu cầu đọc trạng thái thiết bị theo `device_id`. Ứng dụng phải gửi câu lệnh đến Cassandra, đợi cụm Cassandra phản hồi, ánh xạ hàng dữ liệu về đối tượng Java rồi trả kết quả cho bên gọi.

| Tiêu chí | Đồng bộ | Bất đồng bộ | Phản ứng |
|---|---|---|---|
| Giá trị trả về điển hình | `DeviceState`, `Optional<DeviceState>`, `List<T>` | `CompletableFuture<T>` | `Mono<T>`, `Flux<T>` |
| Luồng đang gọi | Chờ cho đến khi thao tác hoàn tất | Nhận future và có thể làm việc khác | Xây dựng pipeline, xử lý tín hiệu khi có subscription |
| API Spring Data Cassandra | `CassandraTemplate`, `CassandraRepository` | `AsyncCassandraTemplate`, `AsyncCassandraOperations` | `ReactiveCassandraTemplate`, `ReactiveCassandraRepository` |
| Kết hợp nhiều thao tác | Lệnh tuần tự, `try/catch` | `thenApply`, `thenCompose`, `exceptionally` | `map`, `flatMap`, `onErrorResume` |
| Dữ liệu nhiều hàng | List, Iterator hoặc paging tùy API | Future của một kết quả/tập kết quả | `Flux` phát từng phần tử, kết hợp paging |
| Điểm cần kiểm soát | Số request thread và thời gian chờ | Số thao tác đang bay, callback, lỗi và timeout | Subscription, nhu cầu tiêu thụ, concurrency và tác vụ blocking |

Hình dung vòng đời một yêu cầu:

~~~text
Đồng bộ:     Request ──> gọi Cassandra ──[luồng gọi chờ]──> kết quả ──> trả về
Bất đồng bộ: Request ──> bắt đầu I/O ──> Future ──[I/O hoàn thành]──> callback
Phản ứng:    Tạo Publisher ──> subscribe ──> truy vấn ──> onNext/onComplete
                                                           hoặc onError
~~~

Không có mô hình nào tự khắc phục được truy vấn sai partition key, partition quá lớn, timeout từ cluster hay lựa chọn consistency level không phù hợp. Mô hình thực thi giải quyết cách **ứng dụng quản lý I/O và tài nguyên**, còn mô hình dữ liệu giải quyết cách **Cassandra tìm và trả dữ liệu**.

## 2. Chuẩn bị dữ liệu chung cho ba mô hình

Ta có bảng lưu trạng thái hiện tại, mỗi thiết bị đúng một hàng:

~~~sql
CREATE TABLE device_state_by_device (
    device_id uuid PRIMARY KEY,
    status text,
    updated_at timestamp
);

-- Truy vấn được bảng hỗ trợ trực tiếp bằng partition key:
SELECT device_id, status, updated_at
FROM device_state_by_device
WHERE device_id = 8f6e37fa-7af2-47e2-b4be-542e83a83848;
~~~

`device_id` là **partition key**. Cassandra dùng khóa này để xác định replica chứa dữ liệu; truy vấn theo đúng khóa giúp tránh quét dữ liệu không cần thiết. Nếu nhu cầu thay đổi thành “đọc 100 sự kiện mới nhất của một thiết bị”, ta cần xem xét **bảng khác** như `events_by_device` với partition key `device_id` và clustering column theo thời gian, thay vì lấy `findAll()` rồi lọc ở Java.

Entity ánh xạ sang bảng:

~~~java
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("device_state_by_device")
public class DeviceState {
    @PrimaryKey("device_id")
    private UUID deviceId;

    @Column("status")
    private String status;

    @Column("updated_at")
    private Instant updatedAt;

    public DeviceState() {}

    public DeviceState(UUID deviceId, String status, Instant updatedAt) {
        this.deviceId = deviceId;
        this.status = status;
        this.updatedAt = updatedAt;
    }

    public UUID getDeviceId() { return deviceId; }
    public void setDeviceId(UUID deviceId) { this.deviceId = deviceId; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant updatedAt) { this.updatedAt = updatedAt; }
}
~~~

Các ví dụ tiếp theo giả định đã có cấu hình kết nối `CqlSession`, keyspace và các bean Spring Data Cassandra tương ứng. Đây là **ba cách triển khai để so sánh**, không yêu cầu một ứng dụng phải dùng đồng thời cả ba. Các đoạn mã service lược bỏ import thông thường để tập trung vào luồng dữ liệu.

## 3. Đồng bộ: gọi và chờ kết quả

Với API đồng bộ, phương thức truy cập dữ liệu chỉ trả về khi driver hoàn tất thao tác hoặc ném ngoại lệ. Luồng đang thực hiện lời gọi bị chặn trong thời gian đó.

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.stereotype.Service;

interface DeviceStateRepository
        extends CassandraRepository<DeviceState, UUID> {
}

@Service
class SyncDeviceStateService {
    private final DeviceStateRepository repository;

    SyncDeviceStateService(DeviceStateRepository repository) {
        this.repository = repository;
    }

    public Optional<DeviceState> find(UUID deviceId) {
        return repository.findById(deviceId); // Chờ kết quả đọc Cassandra.
    }
}
~~~

Khi cần truy cập ở mức template:

~~~java
// cassandraOperations được inject dưới dạng CassandraOperations.
DeviceState state =
        cassandraOperations.selectOneById(deviceId, DeviceState.class);
// Nếu không có hàng, kết quả có thể là null.
~~~

`CassandraTemplate` triển khai `CassandraOperations` và lo mapping hàng CQL sang entity. Repository phù hợp với CRUD và truy vấn được định nghĩa qua interface; template thích hợp khi cần ghép `Query`, `Criteria`, tùy chọn truy vấn hoặc thao tác linh hoạt hơn.

**Khi nên chọn:** dịch vụ Spring MVC truyền thống, batch nhỏ, thao tác đơn giản, tải vừa phải hoặc mã nghiệp vụ vốn đang chạy tuần tự. Cách viết dễ đọc, thuận tiện debug và xử lý lỗi bằng `try/catch`.

**Đánh đổi:** mỗi lời gọi đang đợi I/O chiếm thời gian của luồng gọi. Nếu lượng request đồng thời tăng, request-thread pool có thể cạn trước khi CPU đạt tải cao. Tăng số luồng vô hạn không giải quyết vấn đề và có thể làm xấu độ trễ.

## 4. Bất đồng bộ: nhận CompletableFuture rồi xử lý khi hoàn tất

`AsyncCassandraTemplate` triển khai `AsyncCassandraOperations`. Thay vì trả ngay một entity, API trả về `CompletableFuture` biểu diễn kết quả sẽ có trong tương lai.

~~~java
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import org.springframework.data.cassandra.core.AsyncCassandraOperations;
import org.springframework.stereotype.Service;

@Service
class AsyncDeviceStateService {
    private final AsyncCassandraOperations operations;

    AsyncDeviceStateService(AsyncCassandraOperations operations) {
        this.operations = operations;
    }

    public CompletableFuture<Optional<DeviceState>> find(UUID deviceId) {
        return operations.selectOneById(deviceId, DeviceState.class)
                .thenApply(Optional::ofNullable);
    }
}
~~~

Nếu ứng dụng chưa khai báo bean cho giao diện async, có thể cấu hình `AsyncCassandraTemplate` từ `CqlSession` dùng chung:

~~~java
@Configuration
class AsyncCassandraConfig {
    @Bean
    AsyncCassandraOperations asyncCassandraOperations(CqlSession session) {
        return new AsyncCassandraTemplate(session);
    }
}
~~~

Cần import `org.springframework.context.annotation.Configuration`, `Bean`, `com.datastax.oss.driver.api.core.CqlSession` và các kiểu `AsyncCassandraOperations`, `AsyncCassandraTemplate` từ `org.springframework.data.cassandra.core`. Chỉ thêm cấu hình này nếu application context chưa cung cấp bean phù hợp.

Hai phép biến đổi phổ biến:

~~~java
CompletableFuture<DeviceState> future =
        operations.selectOneById(deviceId, DeviceState.class);

// Xử lý giá trị sau khi I/O hoàn thành.
CompletableFuture<String> label = future.thenApply(
        state -> state == null ? "UNKNOWN" : state.getStatus());

// Nếu bước tiếp theo cũng bất đồng bộ, dùng thenCompose để không lồng future.
CompletableFuture<String> normalized = label.thenCompose(
        status -> CompletableFuture.completedFuture(status.toLowerCase()));
~~~

Ở đây, `thenCompose` chỉ minh họa quy tắc ghép các bước bất đồng bộ; việc đổi chữ thường không thực sự cần một future mới. Trong thực tế, bước thứ hai có thể là truy vấn một bảng khác hoặc gọi dịch vụ I/O khác.

**Lưu ý quan trọng:**

- `CompletableFuture` không đồng nghĩa “tạo thêm một thread cho mỗi query”. Driver Cassandra có cơ chế I/O bất đồng bộ; cần tránh thực hiện tính toán nặng hoặc lời gọi blocking trong callback chạy trên luồng I/O.
- Gọi `future.get()` hoặc `future.join()` ngay sau khi tạo future sẽ khiến luồng gọi **chờ trở lại** và làm mất lợi ích của bất đồng bộ.
- Ngoại lệ từ tác vụ xuất hiện khi future hoàn tất thất bại; xử lý bằng `handle`, `exceptionally` hoặc `whenComplete`, đồng thời duy trì logging và timeout phù hợp.
- Việc áp timeout cho future ở tầng ứng dụng không bảo đảm đã hủy được truy vấn đang chạy trong Cassandra. Cần phối hợp timeout ở driver và quản trị retry.

**Khi nên chọn:** muốn chồng lấp nhiều thao tác I/O độc lập, ghép các bước bằng future hoặc tích hợp vào ứng dụng chưa tổ chức toàn bộ xử lý theo Reactive Streams.

## 5. Phản ứng: Publisher và luồng dữ liệu có kiểm soát nhu cầu

Spring Data Cassandra cung cấp `ReactiveCassandraTemplate`/`ReactiveCassandraOperations` và `ReactiveCassandraRepository`, thường dùng với Project Reactor:

- `Mono<T>`: phát **0 hoặc 1** giá trị rồi hoàn tất (chẳng hạn tìm entity bằng khóa).
- `Flux<T>`: phát **0 đến nhiều** giá trị (chẳng hạn đọc nhiều hàng của một truy vấn).
- `onError` và `onComplete`: biểu diễn lỗi và hoàn tất bằng tín hiệu, thay vì buộc bên gọi lấy kết quả đồng bộ.

Ví dụ repository và service:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.ReactiveCassandraRepository;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

interface ReactiveDeviceStateRepository
        extends ReactiveCassandraRepository<DeviceState, UUID> {
}

@Service
class ReactiveDeviceStateService {
    private final ReactiveDeviceStateRepository repository;

    ReactiveDeviceStateService(ReactiveDeviceStateRepository repository) {
        this.repository = repository;
    }

    public Mono<DeviceState> find(UUID deviceId) {
        return repository.findById(deviceId);
    }
}
~~~

Hoặc dùng template:

~~~java
// reactiveOperations được inject dưới dạng ReactiveCassandraOperations.
Mono<DeviceState> result =
        reactiveOperations.selectOneById(deviceId, DeviceState.class);
// Không tìm thấy dữ liệu: Mono.empty(), không phát null.
~~~

Một endpoint **Spring WebFlux** có thể giữ pipeline từ HTTP đến Cassandra:

~~~java
@GetMapping("/devices/{id}")
public Mono<ResponseEntity<DeviceState>> find(@PathVariable UUID id) {
    return reactiveService.find(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

Trong đó, controller đã inject `ReactiveDeviceStateService reactiveService`; các kiểu `GetMapping`, `PathVariable`, `ResponseEntity` thuộc Spring Web. Trên nhánh không tìm thấy, `Mono` hoàn thành rỗng và endpoint trả HTTP 404.

### 5.1. Subscription và tính lazy

Với các thao tác đọc reactive thông thường, việc tạo `Mono` hoặc `Flux` mới chủ yếu là **mô tả công việc**. Truy vấn được thực thi khi có subscriber; trong WebFlux, framework thường thực hiện subscription cho publisher mà controller trả về. Không tự gọi `subscribe()` bên trong service để “kích hoạt cho chắc”: cách đó tách công việc khỏi lifecycle của request và làm khó việc truyền lỗi, hủy hoặc kiểm soát tải.

~~~java
Mono<DeviceState> pipeline =
        reactiveOperations.selectOneById(deviceId, DeviceState.class)
                .map(state -> state); // Chưa có giá trị để xử lý nếu chưa subscribe.
~~~

Mỗi subscription có thể kích hoạt lại thao tác truy cập dữ liệu. Vì vậy, không xem `Mono` như một giá trị đã cache, và không tự động retry một thao tác ghi nếu chưa xác định được tính idempotent của câu lệnh.

### 5.2. Backpressure và paging không phải cùng một thứ

Trong Reactive Streams, downstream thể hiện nhu cầu nhận phần tử; upstream có thể điều tiết việc phát theo nhu cầu đó. Trên phía Cassandra, driver thường lấy dữ liệu **theo trang**. `Flux` có thể lần lượt phát hàng và lấy trang tiếp theo khi cần, nhưng **một tín hiệu `request(1)` không có nghĩa một truy vấn mạng chỉ trả đúng một hàng**.

Backpressure giúp kiểm soát luồng tiêu thụ dữ liệu; nó không sửa được truy vấn CQL quét quá rộng, hot partition hay số lượng truy vấn độc lập chạy đồng thời quá lớn. Ví dụ:

~~~java
Flux<DeviceState> states = Flux.fromIterable(deviceIds)
        .flatMap(id -> reactiveRepository.findById(id), 8);
// Tối đa 8 truy vấn tra cứu trong phép flatMap này đang hoạt động đồng thời.
~~~

Để ví dụ trên chạy, `deviceIds` là danh sách `UUID` và `reactiveRepository` là `ReactiveDeviceStateRepository`. Số `8` chỉ là **giới hạn minh họa**, cần đo tải thực để chọn. Đây là 8 lượt tra cứu theo khóa, không phải một câu CQL đọc 8 thiết bị.

**Sai lầm thường gặp:** gọi `.block()` trên `Mono` trong một WebFlux request, hoặc gọi thư viện blocking ngay trong `map/flatMap`, có thể làm nghẽn event-loop. Khi bắt buộc tích hợp thư viện blocking, có thể chuyển tạm sang bounded elastic scheduler; đó là cách cô lập phần blocking bằng luồng khác, **không biến thao tác Cassandra đồng bộ thành I/O non-blocking thật sự**.

## 6. So sánh trong một kịch bản tải thực tế

Giả sử API phải xử lý 2.000 lượt đọc trạng thái trong một khoảng thời gian ngắn, mỗi lượt đọc theo `device_id` và cluster có độ trễ mạng đáng kể:

1. **Đồng bộ:** mã gọn, dễ kiểm soát; cần đủ request thread để chịu những lời gọi đang chờ. Nếu thread pool nhỏ, yêu cầu có thể xếp hàng.
2. **Bất đồng bộ:** ứng dụng khởi phát I/O rồi xử lý khi `CompletableFuture` hoàn tất; có thể phối hợp nhiều truy vấn mà không giữ mỗi luồng gọi chờ trực tiếp. Cần đặt giới hạn số request đang bay.
3. **Phản ứng:** rất phù hợp với chuỗi endpoint WebFlux → service → reactive repository, nhất là khi xử lý nhiều hàng và nhiều bước I/O bằng `Mono/Flux`. Cần thiết kế subscription, concurrency và streaming cẩn thận.

Ba cách **không mặc nhiên có cùng throughput và độ trễ**: còn phụ thuộc dữ liệu, replication, consistency, kích thước partition, số connection, timeout, kích thước trang, GC và mức cạnh tranh trên cluster. Hãy benchmark dưới tải thực tế thay vì suy luận “reactive luôn nhanh nhất”.

## 7. Những điều vẫn phải làm đúng trong Cassandra

### 7.1. Thiết kế bảng theo truy vấn

Cassandra không phải cơ sở dữ liệu quan hệ phục vụ truy vấn tùy ý. Bảng `device_state_by_device` ở trên tối ưu cho câu hỏi “trạng thái của một thiết bị là gì?”.

Một truy vấn như:

~~~sql
-- Không phải lối truy cập hiệu quả theo bảng đã thiết kế:
SELECT * FROM device_state_by_device WHERE status = 'OFFLINE';
~~~

không có đường truy cập phù hợp qua partition key. Không thêm `ALLOW FILTERING` chỉ để lệnh “chạy được” trong production; hãy thiết kế một bảng riêng phục vụ truy vấn theo trạng thái (với partitioning hợp lý), hoặc cân nhắc khả năng lập chỉ mục theo yêu cầu và tính chất dữ liệu.

### 7.2. Consistency level độc lập với mô hình thực thi

`LOCAL_ONE` và `LOCAL_QUORUM` quy định mức phản hồi replica cần thiết cho một thao tác trong datacenter cục bộ. Chúng áp dụng cho cả ba mô hình. Chọn consistency theo yêu cầu sản phẩm và replication factor, không theo chuyện code trả `T`, `Future<T>` hay `Mono<T>`.

Ví dụ, Spring Data Cassandra hỗ trợ khai báo consistency trên query method bằng `@Consistency`:

~~~java
@Consistency(ConsistencyLevel.LOCAL_QUORUM)
Optional<DeviceState> findByDeviceId(UUID deviceId);
~~~

Đây là **chữ ký minh họa** trong một `CassandraRepository`; cần import `org.springframework.data.cassandra.repository.Consistency` và `com.datastax.oss.driver.api.core.ConsistencyLevel`. Với bảng mẫu, `findById(deviceId)` đã đáp ứng nhu cầu và có thể cấu hình consistency ở cấp statement/driver khi phù hợp. Consistency level cao hơn có thể tăng chi phí và độ trễ; nó không biến mọi chuỗi nhiều câu lệnh thành giao dịch ACID.

### 7.3. Paging là tiến về phía trước theo paging state

Cassandra dùng **paging state** thay vì cơ chế `OFFSET` tùy ý như nhiều hệ quản trị quan hệ. Với repository đồng bộ:

~~~java
Slice<DeviceState> first =
        repository.findAll(CassandraPageRequest.first(20));

if (first.hasNext()) {
    Slice<DeviceState> next =
            repository.findAll(first.nextPageable());
}
~~~

`CassandraPageRequest` thuộc `org.springframework.data.cassandra.core.query`, còn `Slice` thuộc `org.springframework.data.domain`. Ví dụ chỉ nhằm minh họa API `Slice` và paging state; **không nên dùng `findAll` để quét toàn bộ bảng lớn trong một API production**. Với truy vấn thực tế, nên giới hạn theo partition key và dùng `Slice`/paging state của chính truy vấn ấy. Bản reactive có thể trả `Mono<Slice<T>>` đối với các truy vấn phân trang.

### 7.4. Timeout, retry, paging và quan sát vận hành

- Đặt timeout theo SLA và cấu hình Cassandra driver; phân biệt timeout của HTTP/request với timeout của statement.
- Retry chỉ khi thao tác được xác định an toàn/idempotent, tránh tạo bão truy vấn lúc cluster quá tải.
- Giới hạn tổng số thao tác đồng thời. Bất đồng bộ/reactive có thể tăng số query đang bay rất nhanh nếu bỏ giới hạn.
- Giữ `fetch size` đủ nhỏ để hạn chế bùng bộ nhớ, nhưng không quá nhỏ khiến tăng lượt mạng; đo theo truy vấn.
- Theo dõi **p50/p95/p99 latency**, timeout, số thao tác đang chạy, hàng đợi, mức sử dụng thread và các chỉ số Cassandra (read latency, tombstones, hot partitions). So sánh khi cấu hình và tải đầu vào tương đương.

## 8. Chọn API theo trường hợp sử dụng

| Trường hợp | Lựa chọn khởi đầu phù hợp | Lý do |
|---|---|---|
| Ứng dụng Spring MVC hiện có, truy vấn nhỏ và tuyến tính | `CassandraRepository` hoặc `CassandraTemplate` | Mã dễ đọc, phù hợp xử lý blocking |
| Service xử lý nhiều lời gọi I/O độc lập nhưng chưa dùng Reactor | `AsyncCassandraTemplate` | Dễ ghép `CompletableFuture`, tránh chờ trực tiếp |
| API Spring WebFlux theo chuỗi non-blocking | `ReactiveCassandraRepository` hoặc `ReactiveCassandraTemplate` | Giữ luồng `Mono/Flux` xuyên suốt các tầng |
| Truy vấn CQL riêng, cần điều khiển statement và mapping | Template hoặc driver ở mức phù hợp | Linh hoạt cấu hình statement/consistency/paging |
| Đọc nhiều hàng từ partition đã thiết kế | API có paging; cân nhắc `Flux` khi cần streaming | Kiểm soát bộ nhớ và tốc độ tiêu thụ |

**Quy tắc thực hành:** chọn mô hình nhất quán với stack ứng dụng, đừng trộn blocking call vào reactive pipeline nếu không có lý do rõ ràng. Đo độ trễ, số truy vấn đang chạy và mức sử dụng tài nguyên, sau đó mới điều chỉnh concurrency hoặc đổi mô hình.

## 9. Tự kiểm tra kiến thức

1. Một endpoint WebFlux đang dùng `ReactiveCassandraRepository` nhưng gọi `.block()` trước khi trả response. Điều gì có thể xảy ra khi nhiều request cùng đến?
2. `AsyncCassandraTemplate.selectOneById(...)` trả về kiểu gì, và tại sao gọi `.join()` ngay sau đó làm mất một phần lợi ích?
3. Nếu cần “lấy các sự kiện mới nhất theo `device_id`”, vì sao thiết kế partition/clustering key quan trọng hơn việc chọn `Flux` thay cho `List`?
4. `Flux` có backpressure thì đã đảm bảo một consumer chậm không gây tải lớn cho Cassandra chưa? Còn giới hạn đồng thời và fetch size thì sao?
5. Khi đổi từ đồng bộ sang reactive, liệu mức nhất quán đọc/ghi của Cassandra tự động thay đổi không? Vì sao?

**Gợi ý đáp án:** (1) blocking có thể làm nghẽn event-loop; (2) `CompletableFuture<T>`, `join()` chặn luồng; (3) khóa xác định vị trí và thứ tự truy cập dữ liệu; (4) chưa, vẫn cần hạn chế truy vấn và paging; (5) không, consistency là thuộc tính vận hành của truy vấn/driver.

## Tài liệu tham khảo

- [Spring Data Cassandra – Persisting Entities (Template API)](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html).
- [Spring Data Cassandra – Reactive Infrastructure](https://docs.spring.io/spring-data/cassandra/reference/cassandra/reactive-cassandra.html).
- [Spring Data Cassandra – Cassandra Repositories và paging](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/repositories.html).
- [Spring Data Cassandra – Query Methods và consistency](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html).
- [Spring Data Cassandra – AsyncCassandraOperations API](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/AsyncCassandraOperations.html).
