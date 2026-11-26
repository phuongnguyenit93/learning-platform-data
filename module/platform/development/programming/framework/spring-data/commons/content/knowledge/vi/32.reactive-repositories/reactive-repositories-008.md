# Backpressure, hủy đăng ký và quản lý tài nguyên

## 1. Bài toán: luồng dữ liệu nhanh hơn nơi tiêu thụ

Một tác vụ xuất danh mục đọc sản phẩm qua reactive repository rồi ghi từng sản phẩm sang một đích khác. Database có thể cung cấp dữ liệu nhanh hơn đích ghi. Người dùng cũng có thể dừng tác vụ khi mới đọc một phần danh mục.

Có ba vấn đề cần giải quyết cùng nhau:

1. Điều tiết số phần tử đang được yêu cầu và giữ trong luồng.
2. Truyền tín hiệu hủy khi phía tiêu thụ không cần dữ liệu nữa.
3. Kết thúc vòng đời cursor, connection và các tài nguyên liên quan, kể cả khi không đọc hết dữ liệu.

Bài thuộc chương **Repository reactive** của module **SPRING_DATA_COMMONS**. Trọng tâm là cách dùng abstraction repository cùng Reactor và Reactive Streams. Cách driver lấy dữ liệu, đóng cursor hoặc trả connection về pool vẫn phụ thuộc module và driver thực tế.

Một phương thức trả `Flux<Product>` không tự chứng minh ứng dụng có giới hạn bộ nhớ, query được tối ưu hoặc tài nguyên luôn được giải phóng đúng. Cần xét cả pipeline từ nguồn dữ liệu đến người tiêu thụ.

## 2. Backpressure là điều tiết demand

Reactive Streams dùng `Subscription.request(n)` để người nhận thể hiện nhu cầu nhận thêm phần tử. Demand được cộng dồn; publisher tuân thủ không được phát `onNext` vượt nhu cầu đã được yêu cầu. `Long.MAX_VALUE` có thể được hiểu là nhu cầu không giới hạn thực tế. [Reactive Streams JVM Specification](https://github.com/reactive-streams/reactive-streams-jvm/blob/v1.0.4/README.md).

Hình dung một subscription đơn giản:

```text
Subscriber                    Publisher
    |----- request(2) ----------->|
    |<---- product A -------------|
    |<---- product B -------------|
    |                             |
    |----- request(1) ----------->|
    |<---- product C -------------|
```

`request(2)` diễn đạt số phần tử, không phải hai byte, hai giây hoặc hai kết nối. Một sản phẩm nhỏ và một sản phẩm chứa nhiều dữ liệu vẫn đều có thể được tính là một phần tử ở đoạn stream đó.

Cần phân biệt các mục tiêu:

| Mục tiêu | Cơ chế cần xem xét |
| --- | --- |
| Điều tiết số phần tử được yêu cầu | Demand và operator trong pipeline |
| Giới hạn số bản ghi của query | Filter, limit hoặc phân trang của store |
| Giới hạn số tác vụ đang chạy đồng thời | Concurrency của operator và năng lực hệ thống đích |
| Giới hạn số request mỗi giây | Chính sách điều tiết theo thời gian ở tầng phù hợp |
| Giới hạn bộ nhớ | Số buffer, kích thước phần tử và các bước gom dữ liệu |

Backpressure không biến một query quét toàn bộ bảng thành query có index. Nó cũng không tự chia một truy vấn thành các trang nghiệp vụ.

## 3. Demand có thể thay đổi qua từng operator

Demand tại subscriber cuối không nhất thiết đi nguyên dạng đến driver. Các operator có thể gom phần tử, prefetch hoặc mở nhiều publisher con; ví dụ một nhu cầu nhận hai buffer kích thước mười cần được hiểu khác với nhu cầu nhận hai entity. [Reactor: Backpressure and Reshaping Requests](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html).

Hãy quan sát từng đoạn của chuỗi:

```text
Repository -> buffer hoặc hàng đợi operator -> xử lý con -> subscriber
     ^                    ^                        ^
     |                    |                        |
  demand A             demand B                 demand C
```

Các nhu cầu này có thể khác nhau mà pipeline vẫn tuân thủ giao thức. Do đó, việc subscriber cuối chỉ xử lý một phần tử tại một thời điểm chưa chứng minh upstream chỉ giữ đúng một phần tử.

### 3.1. limitRate điều tiết request, không giới hạn toàn bộ kết quả

`limitRate` chia nhu cầu lớn thành các request nhỏ hơn về phía upstream. Biến thể có `lowTide=0` dùng các đợt request theo mức `highTide`; nó không giới hạn tổng số phần tử của nguồn. [Reactor: Request Reshaping Operators](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html).

```java
Flux<Product> products = repository.findAll()
        .limitRate(32, 0);
```

Con số 32 trong ví dụ là lựa chọn để quan sát hành vi, không phải cấu hình tối ưu cho mọi database. Nó cũng không có nghĩa chỉ đọc 32 sản phẩm rồi kết thúc.

### 3.2. Concurrency và prefetch cần được chọn theo bước xử lý

Giả sử `writer.write(product)` trả `Mono<Void>` hoàn tất khi đích ghi đã xử lý sản phẩm:

```java
Mono<Void> sequential = repository.findAll()
        .limitRate(32, 0)
        .concatMap(writer::write, 1)
        .then();
```

Mẫu này ghép các lần ghi theo thứ tự, thay vì tự subscribe cho từng phần tử. Tham số prefetch của bước ghép và giới hạn request phía repository là hai lựa chọn riêng.

Nếu chuyển sang xử lý đồng thời, phải đánh giá thêm số tác vụ đang chạy, thứ tự kết quả, connection pool và giới hạn của đích ghi. Không chọn concurrency chỉ từ số lượng sản phẩm cần xuất.

## 4. Những cách dùng có thể làm dữ liệu tích tụ

Một pipeline reactive vẫn có thể giữ nhiều dữ liệu nếu ứng dụng chủ động yêu cầu gom hoặc sắp xếp toàn bộ kết quả.

| Cách dùng | Điều cần đánh giá |
| --- | --- |
| `collectList()` trên nguồn lớn | Danh sách tăng theo số phần tử đã đọc |
| Sorting trong pipeline | Có thể cần giữ dữ liệu để xác định thứ tự |
| Hàng đợi qua các bước bất đồng bộ | Prefetch, số phần tử đang chờ và kích thước phần tử |
| Buffer để chờ phía sau | Dung lượng tối đa và chính sách khi không còn chỗ |
| Subscriber yêu cầu không giới hạn | Các operator trước đó có tiếp tục giới hạn hợp lý không? |

Không thêm `onBackpressureBuffer()` như một cách sửa mặc định cho mọi tình huống đích chậm. Nếu nguồn đang tuân thủ demand, cần hiểu vì sao pipeline vẫn cần buffer và buffer ấy có giới hạn gì.

Với dữ liệu nghiệp vụ, chính sách bỏ phần tử cũng phải có ý nghĩa. Bỏ một cập nhật tồn kho hoặc một dòng chứng từ không giống bỏ một điểm hiển thị trạng thái có thể được thay bằng giá trị mới hơn.

Tương tự, `take(20)` ở pipeline không chứng minh database chỉ quét hoặc gửi đúng 20 bản ghi. R2DBC phân biệt flow control với giới hạn kết quả trong query; `fetchSize` còn là gợi ý mà driver có thể không áp dụng. [R2DBC: Performance Hints](https://r2dbc.io/spec/1.0.0.RELEASE/spec/html/#statements.performance).

## 5. Cancellation khác completion và error

Một subscriber có thể hủy subscription khi không còn cần dữ liệu. Theo Reactive Streams, tác động hủy có thể có độ trễ lan truyền; không được suy rằng lời gọi cancel đã đồng bộ dừng mọi công việc từ xa. [Reactive Streams: Cancellation Rules](https://github.com/reactive-streams/reactive-streams-jvm/blob/v1.0.4/README.md).

Ba kết quả cần được phân biệt khi vận hành:

| Tình huống | Ý nghĩa quan sát |
| --- | --- |
| Completion | Nguồn đã kết thúc thành công theo hợp đồng của đoạn stream |
| Error | Đoạn stream kết thúc bằng lỗi |
| Cancellation | Phía tiêu thụ yêu cầu ngừng subscription |

Không đợi `onComplete` như điều kiện duy nhất để giải phóng tài nguyên. Một lượt đọc bị hủy có thể không đi qua nhánh completion của nguồn.

### 5.1. Hủy tại ranh giới quản lý subscription

Ở một chương trình nền tự quản lý subscription, Reactor có thể trả `Disposable` để bên gọi giữ và hủy:

```java
reactor.core.Disposable handle = service.readProducts()
        .subscribe(
                product -> System.out.println(product.id()),
                error -> System.err.println(error.getMessage()));

// Khi tiến trình điều phối xác định không cần kết quả nữa:
handle.dispose();
```

Đây là ví dụ tại ranh giới có chủ thể quản lý subscription. Với một request reactive do framework quản lý, thường trả publisher cho framework để cancellation còn truyền được qua cùng chuỗi.

Không tạo một subscription bên trong service chỉ để công việc chạy rồi trả `Mono.empty()` cho bên ngoài. Khi đó, việc hủy publisher được trả về có thể không còn đại diện cho tác vụ đã tách ra.

### 5.2. Operator có thể chủ động hủy upstream

Ví dụ lấy một phần danh mục:

```java
Flux<Product> preview = service.readProducts().take(10);
```

Phía nhận `preview` có thể thấy completion sau đủ phần tử, trong khi nguồn phía trước `take` nhận cancellation. Vì thế, phải ghi rõ vị trí đặt hook quan sát khi đọc log complete hoặc cancel.

Không suy ra nguyên nhân nghiệp vụ chỉ từ cancellation: có thể người dùng dừng, một operator đã đủ dữ liệu hoặc một bước khác không còn cần nguồn.

## 6. Ví dụ repository: giữ luồng đọc và ghi trong cùng pipeline

Các ví dụ dùng Java 17, Reactor và Spring Data R2DBC có phiên bản tương thích. Mỗi public type đặt trong tệp Java riêng cùng package `example.streaming`; các đoạn mã lược dòng package. Ứng dụng cần cấu hình driver, database, schema và repository scanning tương ứng.

### 6.1. Entity và repository

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("products")
public record Product(
        @Id Long id,
        String name,
        @Column("price_in_cents") long priceInCents) {
}
```

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import org.springframework.data.repository.reactive.ReactiveSortingRepository;

public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long>,
                ReactiveSortingRepository<Product, Long> {
}
```

Mô hình minh họa giả định bảng có các cột `id`, `name`, `price_in_cents` với kiểu phù hợp và dữ liệu cần đọc không null. Mapping cho một store khác cần được thiết kế riêng.

### 6.2. Hợp đồng của đích ghi

```java
import reactor.core.publisher.Mono;

public interface ProductWriter {

    Mono<Void> write(Product product);
}
```

`write` phải trả publisher đại diện cho công việc thật. Nếu implementation tự tách một tác vụ nền rồi trả completion ngay, bước ghép phía service không còn chờ được công việc đó.

### 6.3. Service không tự subscribe

```java
import org.springframework.data.domain.Sort;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ProductExportService {

    private static final System.Logger LOGGER =
            System.getLogger(ProductExportService.class.getName());

    private final ProductRepository repository;
    private final ProductWriter writer;

    public ProductExportService(
            ProductRepository repository,
            ProductWriter writer) {
        this.repository = repository;
        this.writer = writer;
    }

    public Flux<Product> readProducts() {
        return repository.findAll(Sort.by("id"))
                .doOnRequest(amount -> LOGGER.log(
                        System.Logger.Level.DEBUG,
                        "Demand tại repository boundary: {0}", amount))
                .doOnCancel(() -> LOGGER.log(
                        System.Logger.Level.DEBUG,
                        "Đã nhận yêu cầu hủy nguồn đọc"))
                .limitRate(32, 0);
    }

    public Mono<Void> export() {
        return Mono.defer(() -> {
            long startedAt = System.nanoTime();

            return readProducts()
                    .concatMap(writer::write, 1)
                    .then()
                    .doFinally(signal -> LOGGER.log(
                            System.Logger.Level.DEBUG,
                            "Export kết thúc: signal={0}, elapsedNanos={1}",
                            signal, System.nanoTime() - startedAt));
        });
    }
}
```

Service nhận repository và writer đã được ứng dụng cung cấp. Nó trả publisher để bên điều phối quan sát được lỗi, completion và truyền cancellation.

`doOnRequest` ở đây chỉ quan sát demand tại đúng boundary được đặt hook. Nó không đếm số lần trao đổi network hoặc số row database đã quét.

`doFinally` đo vòng đời của lần export. Log ấy chưa phải xác nhận rằng mọi tài nguyên thấp hơn đã hoàn tất đóng bất đồng bộ.

## 7. doFinally dùng để quan sát kết thúc, không thay thế mọi cleanup

`doFinally` nhận loại tín hiệu khi luồng complete, error hoặc bị cancel. Nó thích hợp với các side effect ngắn như ghi nhận metric hoặc kết thúc phép đo thời gian. [Reactor: Using Resources and Finally](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html#_using_resources_and_the_finally_block).

Cần tránh hai nhầm lẫn:

1. Chỉ dùng `doOnComplete` rồi bỏ quên lỗi và hủy.
2. Gọi một API đóng bất đồng bộ trong hook nhưng không ghép publisher đóng vào vòng đời tài nguyên.

Ví dụ sai về quản lý connection R2DBC, giả sử `connection` đang có trong phạm vi:

```java
Flux<Product> rows = readRows(connection)
        .doFinally(signal -> connection.close());
```

`Connection.close()` trả một publisher. Bỏ qua publisher đó không thể hiện rằng thao tác đóng đã được thực thi và chờ hoàn tất.

Tự gọi `subscribe()` cho việc đóng trong hook cũng tách cleanup thành một vòng đời khác. Nếu cần gắn công việc bất đồng bộ vào complete, error và cancel, hãy dùng cơ chế quản lý tài nguyên phù hợp như `usingWhen`.

Vị trí operator còn ảnh hưởng điều bạn quan sát. Một hook trước `take` có thể thấy cancel trong khi hook sau nó thấy complete; không coi hai log này là mâu thuẫn.

## 8. Quản lý tài nguyên theo chủ thể sở hữu

Trước khi viết lệnh đóng, cần xác định ai mở và ai có trách nhiệm giải phóng tài nguyên.

| Tài nguyên | Chủ thể cần xem xét |
| --- | --- |
| Connection của repository hoặc template đã cấu hình | Hạ tầng Spring và driver tương ứng |
| Connection do code thấp hơn tự lấy để dùng riêng | Phạm vi code trực tiếp sở hữu connection |
| Connection gắn với transaction | Transaction manager và cơ chế truy cập tài nguyên của framework |
| Subscriber do ứng dụng tự tạo | Thành phần giữ subscription handle |
| Scheduler hoặc client dùng chung | Vòng đời bean hoặc ứng dụng, không mặc định một request |

Không lấy connection của framework rồi tự đóng ở mỗi entity như thể đó là connection riêng. Với Spring R2DBC, cơ chế `ConnectionFactoryUtils` hỗ trợ connection gắn với subscriber context; các client Spring dùng cơ chế tương ứng để tham gia transaction. [Spring Framework: Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html#r2dbc-connections).

Tương tự, hủy một subscription không phải lý do để đóng toàn bộ `ConnectionFactory`, pool hoặc client dùng chung cho những request khác.

Với connection pool, việc kết thúc quyền sử dụng một connection có thể là trả nó về pool thay vì đóng ngay kết nối vật lý. Khi điều tra rò rỉ, cần quan sát số tài nguyên đang được mượn và cách pool quản lý vòng đời, không chỉ đếm socket còn mở.

Một luồng đọc chậm cũng có thể giữ connection lâu dù không tích tụ nhiều entity. Backpressure giúp điều tiết dữ liệu, nhưng chưa tự giải quyết việc một tác vụ chiếm tài nguyên quá lâu.

## 9. usingWhen cho tài nguyên đóng bất đồng bộ

`Flux.usingWhen` gắn một tài nguyên được cấp theo subscription với publisher sử dụng nó và các nhánh cleanup bất đồng bộ. Biến thể đầy đủ cho phép chỉ rõ complete, error và cancel; các bước còn cần tài nguyên mở phải nằm trong phạm vi sử dụng tài nguyên. [API Flux.usingWhen](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html#usingWhen-org.reactivestreams.Publisher-java.util.function.Function-java.util.function.Function-java.util.function.BiFunction-java.util.function.Function-).

Ví dụ sau cố ý dùng R2DBC SPI trực tiếp để minh họa **quyền sở hữu connection riêng**, không phải cách tự đóng connection của `ProductRepository`. Nó không được trình bày như một thao tác tham gia transaction Spring đang quản lý.

```java
import io.r2dbc.spi.Connection;
import io.r2dbc.spi.ConnectionFactory;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class DirectProductReader {

    private final ConnectionFactory connectionFactory;

    public DirectProductReader(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public Flux<Product> readAll() {
        return Flux.usingWhen(
                Mono.defer(() -> Mono.from(connectionFactory.create())),
                this::readRows,
                this::close,
                (connection, failure) -> close(connection),
                this::close);
    }

    private Flux<Product> readRows(Connection connection) {
        String sql = "SELECT id, name, price_in_cents "
                + "FROM products ORDER BY id";

        return Flux.from(connection.createStatement(sql).execute())
                .concatMap(result -> result.map((row, metadata) ->
                        new Product(
                                row.get("id", Long.class),
                                row.get("name", String.class),
                                row.get("price_in_cents", Long.class))));
    }

    private Mono<Void> close(Connection connection) {
        return Mono.from(connection.close());
    }
}
```

Ví dụ giả định driver trả các cột số theo kiểu `Long` tương thích với schema đã chọn. Giá trị row được lấy bên trong mapper rồi chuyển thành `Product`; không giữ object row để tiếp tục đọc sau vòng đời result.

R2DBC yêu cầu đóng connection để giải phóng tài nguyên liên quan; `close()` cung cấp publisher mô tả quá trình ấy. [R2DBC: Closing Connections](https://r2dbc.io/spec/1.0.0.RELEASE/spec/html/#connections.close).

Ba nhánh cleanup trong mẫu cùng đóng connection vì ví dụ chỉ đọc dữ liệu và không quản lý transaction riêng. Nếu tài nguyên còn có nghĩa commit hoặc rollback, phải thiết kế các nhánh theo hợp đồng transaction tương ứng; không sao chép việc đóng đơn thuần thành một triển khai transaction.

Cleanup cũng có thể lỗi. Khi vận hành, cần phân biệt lỗi đọc, lỗi hủy và lỗi giải phóng; không coi việc đã gọi hàm cleanup là bằng chứng thao tác đóng đã hoàn tất thành công.

## 10. Timeout, hủy và kết quả ghi dữ liệu

Timeout ở tầng Reactor, giới hạn thực thi statement của database và thời gian chờ mượn connection là các chính sách khác nhau.

Ví dụ:

```java
Flux<Product> guarded = service.readProducts()
        .timeout(java.time.Duration.ofSeconds(5));
```

Với overload `Flux.timeout(Duration)`, khoảng chờ liên quan đến tín hiệu đầu và các phần tử tiếp theo; nó không đơn thuần là deadline tổng cho toàn bộ tác vụ đọc. Khi lựa chọn timeout, hãy nêu rõ bạn đang giới hạn giai đoạn nào của pipeline. [API Flux.timeout](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html#timeout-java.time.Duration-).

Nếu subscriber dừng chờ sau một thao tác ghi, không tự kết luận database chưa ghi gì. Công việc có thể đã được gửi hoặc một phần tác dụng đã xảy ra trước khi tín hiệu hủy đến nơi.

Với `TransactionalOperator` của Spring, tài liệu mô tả cancellation dẫn đến rollback từ Spring Framework 5.3 và lưu ý các operator như `take`, `next` hoặc `timeout` có thể phát sinh cancellation. Để transaction của một luồng nhiều phần tử hoàn tất, cần xét việc tiêu thụ đầy đủ output của publisher transaction. [Spring Framework: Cancel Signals](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html#tx-prog-operator-cancel).

Điều đó không đồng nghĩa mọi việc ghi ngoài transaction đều được hoàn tác. Trước khi retry một tác vụ đã bị hủy hoặc timeout, cần biết:

- Thao tác nào đã có thể tạo tác dụng.
- Transaction có thực sự bao quanh pipeline đó không.
- Kết quả commit hoặc rollback đã được quan sát bằng cách nào.
- Command có thể chạy lại an toàn hay cần định danh để tránh thực hiện trùng.

Đặc biệt, không thêm `take(1)` xuống cuối một publisher transaction nhiều phần tử chỉ để lấy một giá trị rồi mặc định toàn bộ công việc sẽ commit.

## 11. Tài nguyên trong các phần tử bị bỏ và giới hạn bộ nhớ

Ngoài connection, một số pipeline dùng object có vòng đời đặc biệt như buffer đếm tham chiếu hoặc dữ liệu ngoài heap. Với những kiểu đó, phần tử đã được prefetch nhưng bị bỏ khi cancel có thể cần cơ chế cleanup riêng. Reactor có các hook như `doOnDiscard` cho những trường hợp và operator được hỗ trợ. [Reactor: Objects That Need Cleanup](https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html).

Không áp dụng một lệnh release chung cho mọi entity Java. `Product` trong bài là dữ liệu thông thường; quyền sở hữu connection và quyền sở hữu một buffer đặc biệt là hai chuyện khác nhau.

Khi pipeline có dữ liệu cần giải phóng thủ công, cần làm rõ ai sở hữu phần tử sau mỗi bước và liệu hook có thể được gọi nhiều lần. Một kế hoạch cleanup phải phù hợp loại dữ liệu, tránh cả mất tài nguyên lẫn giải phóng lặp.

Về dung lượng, hãy ước lượng theo toàn bộ đường đi:

```text
Bộ nhớ đang giữ
+ dữ liệu driver đã lấy hoặc đang đệm
+ hàng đợi của các operator
+ dữ liệu trong tác vụ xử lý đang chạy
+ các tập kết quả do ứng dụng chủ động gom
```

Đây là cách kiểm kê thành phần, không phải công thức bảo đảm số byte chính xác. Kích thước entity, cách mapping và driver sẽ quyết định lượng bộ nhớ thực tế.

## 12. Kiểm thử demand, cancellation và cleanup

`StepVerifier` cho phép mô tả nhu cầu và các tín hiệu cần quan sát khi publisher được thực thi. Ví dụ kiểm thử nên có giới hạn thời gian và phân biệt việc subscriber đã cancel với thời điểm cleanup thực sự hoàn tất. [Reactor: Testing](https://projectreactor.io/docs/core/release/reference/testing.html).

Các đoạn dưới là hướng dẫn thực hành, không phải báo cáo đã chạy trên dự án. Chúng dùng JUnit Jupiter và `reactor-test`; không kèm cấu hình build hoặc driver.

### 12.1. Yêu cầu một phần dữ liệu rồi hủy

```java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

public class DemandAndCancelTest {

    @Test
    void requestsOnlyTheObservedPartThenCancels() {
        AtomicBoolean cancelled = new AtomicBoolean();
        Flux<Integer> source = Flux.range(1, 100)
                .doOnCancel(() -> cancelled.set(true));

        StepVerifier.create(source, 0)
                .thenRequest(2)
                .expectNext(1, 2)
                .thenRequest(1)
                .expectNext(3)
                .thenCancel()
                .verify(Duration.ofSeconds(5));

        assertTrue(cancelled.get());
    }
}
```

Nguồn trong test là một `Flux` đồng bộ để quan sát giao thức, không phải database. Test không chứng minh driver thực tế chỉ lấy đúng ba row qua network.

### 12.2. Quan sát riêng việc cleanup đã chạy

Ví dụ mô phỏng một tài nguyên và nhánh release có tín hiệu riêng:

```java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

public class ResourceCancellationTest {

    @Test
    void releasesAnAcquiredResourceAfterCancellation() {
        AtomicInteger releases = new AtomicInteger();
        Sinks.Empty<Void> released = Sinks.empty();

        Function<String, Mono<Void>> cleanup = resource ->
                Mono.fromRunnable(() -> {
                    releases.incrementAndGet();
                    released.tryEmitEmpty();
                });

        Flux<Integer> scoped = Flux.usingWhen(
                Mono.just("demo-resource"),
                resource -> Flux.range(1, 100),
                cleanup,
                (resource, failure) -> cleanup.apply(resource),
                cleanup);

        StepVerifier.create(scoped, 0)
                .thenRequest(2)
                .expectNext(1, 2)
                .thenCancel()
                .verify(Duration.ofSeconds(5));

        StepVerifier.create(released.asMono())
                .expectComplete()
                .verify(Duration.ofSeconds(5));

        assertEquals(1, releases.get());
    }
}
```

Đây là mô phỏng cơ chế release, không phải test đóng connection thật. Với cleanup bất đồng bộ thực tế, cần quan sát tín hiệu hoàn tất hoặc metric phù hợp thay vì kết luận ngay sau lời gọi cancel.

### 12.3. Kiểm tra tích hợp với store và pool

| Kịch bản | Bằng chứng cần tìm |
| --- | --- |
| Đọc hết kết quả | Luồng hoàn tất và tài nguyên đang mượn trở về mức phù hợp |
| Chỉ lấy một phần rồi hủy | Cancellation truyền đến nguồn và tài nguyên cuối cùng được giải phóng |
| Mapping hoặc writer báo lỗi | Không giữ connection hoặc tác vụ con vô thời hạn |
| Người tiêu thụ rất chậm | Hàng đợi, số tác vụ đang chạy và thời gian giữ connection có giới hạn đã chọn |
| Timeout trước phần tử đầu | Phân biệt chờ pool, chờ query và lỗi kết nối |
| Cleanup bị lỗi hoặc chậm | Có cách quan sát riêng để chẩn đoán |
| Hủy trong transaction | Kiểm tra kết quả rollback theo cấu hình thực tế |
| Nhiều subscription | Mỗi lượt có phạm vi tài nguyên đúng, không dùng lẫn connection riêng |

## 13. Bài tập áp dụng

Xây một tác vụ đọc danh mục qua `ProductRepository`, ghi bằng một `ProductWriter` có độ trễ kiểm soát được và trả publisher cho thành phần điều phối.

Thực hiện ba lượt: đọc hết, dừng sau một phần dữ liệu và cho writer báo lỗi. Với mỗi lượt, ghi lại demand tại boundary đã chọn, số tác vụ đang chạy, tín hiệu kết thúc và việc tài nguyên được giải phóng.

Sau đó giải thích:

1. Vì sao `limitRate(32, 0)` không tương đương query chỉ trả 32 sản phẩm?
2. Vì sao completion sau `take` có thể đi cùng cancellation ở phía nguồn?
3. Vì sao không dùng riêng `doOnComplete` để quản lý connection?
4. Khi nào ứng dụng sở hữu việc đóng tài nguyên, khi nào framework sở hữu?
5. Vì sao timeout một lần ghi chưa đủ để quyết định có thể retry mà không tạo tác dụng trùng?

Một thiết kế rõ ràng chỉ ra được demand ở từng đoạn, đường đi của cancellation và chủ thể sở hữu tài nguyên. Ba điều đó giúp reactive repository phối hợp đúng với driver và tầng tiêu thụ khi dữ liệu lớn, phía nhận chậm hoặc tác vụ bị dừng giữa chừng.
