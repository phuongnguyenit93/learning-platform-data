# Lựa chọn API đồng bộ, bất đồng bộ hoặc reactive theo nhu cầu ứng dụng Neo4j

## 1. Bài toán: cùng một Cypher, ba cách ứng dụng Java xử lý

Một ứng dụng quản lý mạng lưới cung ứng lưu các node `Supplier`, `Product` và relationship `SUPPLIES` trong Neo4j. Người dùng muốn lấy danh sách sản phẩm từ một nhà cung cấp, hoặc phân tích hàng trăm nghìn mối quan hệ để lập báo cáo. Cả hai yêu cầu có thể dùng Cypher, nhưng **cách Java nhận kết quả và quản lý công việc trong khi chờ Neo4j** có ảnh hưởng lớn đến tài nguyên ứng dụng.

Neo4j Java Driver cung cấp ba kiểu API chính:

1. **Đồng bộ (synchronous/blocking):** gọi phương thức rồi chờ kết quả trước khi tiếp tục thực thi.
2. **Bất đồng bộ (asynchronous):** nhận một `CompletionStage` và định nghĩa thao tác tiếp theo khi I/O hoàn thành.
3. **Reactive:** nhận một `Publisher`, tiêu thụ khi có subscriber và điều tiết tốc độ nhận bản ghi theo **backpressure**.

Ba cách này vẫn gửi truy vấn tới **cùng Neo4j Database**, cùng các node, relationship, index, constraint và cơ chế transaction. Chọn API **không làm Cypher tự chạy nhanh hơn** hoặc giúp máy chủ xử lý nhiều query hơn nếu nguồn nghẽn nằm ở query plan, ổ đĩa, khóa hay tài nguyên server. Sự khác biệt chủ yếu là **thread, mô hình điều phối, tốc độ tiêu thụ kết quả và khả năng xử lý đồng thời ở phía client**.

Trong module `DATABASE_ENGINE_GRAPH_NEO4J`, lựa chọn API phải phù hợp với kiến trúc Java/Spring Data Neo4j, khối lượng dữ liệu và cách ứng dụng sử dụng kết quả Cypher.

## 2. So sánh nhanh trước khi chọn API

| Tiêu chí | Đồng bộ | Bất đồng bộ | Reactive |
| --- | --- | --- | --- |
| Session | `org.neo4j.driver.Session` | `org.neo4j.driver.async.AsyncSession` | `org.neo4j.driver.reactivestreams.ReactiveSession` hoặc `org.neo4j.driver.reactive.ReactiveSession` |
| Kết quả thao tác | Giá trị hoặc `Result` trực tiếp | `CompletionStage<T>` / `CompletableFuture<T>` | `Publisher<T>`; thường dùng Reactor `Flux`/`Mono` |
| Thread gọi | Có thể chờ I/O trong lúc thao tác | Không cần giữ thread chờ I/O; callback được gọi khi stage hoàn thành | Không cần giữ thread chờ I/O; subscriber yêu cầu dữ liệu theo nhu cầu |
| Tiêu thụ nhiều bản ghi | `Result.next()` / `list()` / `stream()` | `ResultCursor.nextAsync()` / `listAsync()` / `forEachAsync()` | `Publisher<Record>` với request/subscribe, hỗ trợ backpressure |
| Transaction quản lý | `executeRead` / `executeWrite` | `executeReadAsync` / `executeWriteAsync` | `executeRead` / `executeWrite` trả Publisher |
| Vòng đời session | `try-with-resources` rất tự nhiên | Đóng bằng `closeAsync()` sau khi stage hoàn thành | Gắn session với vòng đời subscription bằng `usingWhen` hoặc cơ chế resource tương đương |
| Độ phức tạp | Thấp | Trung bình; cần quản lý stage và lỗi | Cao hơn; cần hiểu subscription, backpressure, cancellation, context |
| Phù hợp nhất | CRUD, API đơn giản, batch/CLI, code imperative | Fan-out I/O, nhiều request đồng thời, tích hợp `CompletionStage` | Spring WebFlux/Reactor, pipeline streaming lớn có nhu cầu backpressure |
| Điểm dễ sai | Giữ thread quá lâu, `list()` trên tập lớn | Quên chờ `closeAsync()`, block I/O thread, thất lạc exception | Không subscribe, `block()` trên event loop, quên cleanup khi cancel |

**Mặc định nên bắt đầu bằng đồng bộ nếu ứng dụng imperative**. Với nhiều tác vụ I/O độc lập, chọn async khi kiến trúc ứng dụng đã dùng `CompletionStage`. Với ứng dụng **reactive end-to-end** hoặc yêu cầu backpressure rõ ràng, chọn reactive. Tài liệu Neo4j cũng khuyến nghị reactive cho ứng dụng vốn đã dùng mô hình reactive; những trường hợp còn lại thường dùng sync/async. Java 21+ với virtual threads còn mở thêm lựa chọn cho code imperative có nhiều I/O đồng thời.

## 3. Phạm vi phiên bản và những điểm thay đổi của Driver 6.x

Ví dụ trong bài sử dụng API **Neo4j Java Driver 6.x**. Khi dùng Driver 5.x hoặc mã nguồn cũ, kiểm tra migration guide trước khi sao chép.

| Thành phần | Driver 6.x | Ghi chú |
| --- | --- | --- |
| Session đồng bộ | `driver.session(SessionConfig)` | `Session` kế thừa `AutoCloseable` |
| Session async | `driver.session(AsyncSession.class, config)` | Không dùng `driver.asyncSession()` kiểu cũ |
| Session reactive Reactor | `driver.session(org.neo4j.driver.reactivestreams.ReactiveSession.class, config)` | Không dùng `driver.rxSession()` |
| Session reactive Java Flow | `driver.session(org.neo4j.driver.reactive.ReactiveSession.class, config)` | Trả `Flow.Publisher` từ Java 9 |
| Managed transaction | `executeRead` / `executeWrite` | `readTransaction` / `writeTransaction` cũ đã bị loại bỏ |
| Managed transaction async | `executeReadAsync` / `executeWriteAsync` | Dùng `AsyncTransactionCallback` |
| Reactive transaction | `executeRead` / `executeWrite` trên reactive session | Kết quả là publisher, được chạy khi subscribe |

**Phân biệt hai interface cùng tên `ReactiveSession`:** một thuộc package `reactivestreams` dành cho Reactive Streams/Reactor, một thuộc package `reactive` dùng `java.util.concurrent.Flow`. Chúng có mô hình publisher tương tự nhưng kiểu Java khác nhau, nên không trộn các import trong cùng ví dụ.

Một `Driver` thường được tạo **một lần và chia sẻ giữa các thread**; nó quản lý connection pool và routing. `Session` (kể cả session async/reactive) là **ngữ cảnh công việc ngắn**, không được chia sẻ để chạy nhiều transaction đồng thời. Mỗi concurrent request hoặc transaction độc lập nên có session riêng.

## 4. Chuẩn bị graph và truy vấn dùng chung

Ví dụ dùng label `DriverDemoUser` riêng, tránh trộn với schema thực tế của ứng dụng. Trên database thử nghiệm, tạo constraint để khóa ID duy nhất:

```cypher
CREATE CONSTRAINT driver_demo_user_id IF NOT EXISTS
FOR (u:DriverDemoUser) REQUIRE u.id IS UNIQUE;
```

Tạo node:

```cypher
UNWIND [
  {id: 'u001', name: 'An', active: true},
  {id: 'u002', name: 'Bình', active: true},
  {id: 'u003', name: 'Chi', active: false},
  {id: 'x004', name: 'Dũng', active: true}
] AS row
MERGE (u:DriverDemoUser {id: row.id})
SET u.name = row.name,
    u.active = row.active;
```

Ví dụ đọc dùng chung:

```cypher
MATCH (u:DriverDemoUser)
WHERE u.active = true AND u.id STARTS WITH $prefix
RETURN u.id AS id, u.name AS name
ORDER BY name
LIMIT $limit;
```

Tham số:

```json
{"prefix": "u", "limit": 100}
```

Với dữ liệu mẫu, dự kiến có `u001` và `u002`. Dùng **tham số** cho `$prefix` và `$limit` để tránh nối input của người dùng vào chuỗi Cypher; tạo index/constraint nếu cần bảo đảm khóa và tối ưu truy vấn trên graph lớn.

Trong các đoạn Java sau, giả sử đã có đối tượng `Driver driver` được tạo từ `GraphDatabase.driver(...)` và được **đóng khi ứng dụng shutdown**, không tạo một Driver mới mỗi lần gọi hàm.

Để đơn giản, đối tượng kết quả là record:

```java
record UserView(String id, String name) {}
```

## 5. API đồng bộ: đơn giản, dễ đọc và dễ kiểm soát transaction

### 5.1. Truy vấn đọc bằng managed transaction

```java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

static List<UserView> findActiveSync(Driver driver, String prefix) {
    String cypher = """
        MATCH (u:DriverDemoUser)
        WHERE u.active = true AND u.id STARTS WITH $prefix
        RETURN u.id AS id, u.name AS name
        ORDER BY name
        LIMIT $limit
        """;

    try (Session session = driver.session(
            SessionConfig.forDatabase("neo4j"))) {
        return session.executeRead(tx ->
            tx.run(cypher, Map.of("prefix", prefix, "limit", 100))
              .list(record -> new UserView(
                  record.get("id").asString(),
                  record.get("name").asString()
              ))
        );
    }
}
```

Cách hoạt động:

1. `driver.session(...)` tạo session nhẹ và lấy connection từ pool khi cần.
2. `executeRead(...)` điều phối một **managed read transaction**, tự retry một số lỗi tạm thời phù hợp.
3. `tx.run(...)` gửi Cypher với tham số; `list(...)` tiêu thụ toàn bộ kết quả bên trong transaction.
4. `try-with-resources` đóng session khi rời phạm vi, kể cả khi có exception.

Vì kết quả được **materialize thành List**, ví dụ này phù hợp khi có `LIMIT` nhỏ. Với vài triệu record, `list()` có thể dùng nhiều heap phía ứng dụng; dùng cách đọc tuần tự hoặc phân lô, không giữ cả tập trong bộ nhớ.

### 5.2. Khi nào chọn đồng bộ?

- Endpoint CRUD có lượng kết quả nhỏ và các bước xử lý tuyến tính.
- Dịch vụ Spring MVC hoặc command-line job viết theo imperative.
- Truy vấn cập nhật nhiều bước cần một transaction rõ ràng.
- Nhóm phát triển muốn dễ đọc stack trace và dễ kiểm thử.
- Tải I/O vừa phải, hoặc ứng dụng Java 21+ sử dụng virtual threads với chiến lược tài nguyên phù hợp.

**Blocking không tự đồng nghĩa với “chậm”.** Nếu Neo4j trả 5 bản ghi nhanh và chỉ có vài request đồng thời, async/reactive có thể tăng độ phức tạp mà không làm latency tốt hơn. Với tải lớn, cần đo cả độ trễ, connection pool, chi phí CPU và khả năng cấp thread.

### 5.3. Truy vấn ghi và transaction

```java
try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    session.executeWriteWithoutResult(tx ->
        tx.run(
            """
            MERGE (u:DriverDemoUser {id: $id})
            SET u.name = $name
            """,
            Map.of("id", "u005", "name", "Hà")
        ).consume()
    );
}
```

`executeWriteWithoutResult` thích hợp khi callback không cần trả dữ liệu. Trong managed transaction, callback có thể được driver gọi lại nếu có transient failure. Vì vậy tránh **gửi email, trừ tiền ngoài Neo4j hoặc tăng biến global** bên trong callback; các side effect bên ngoài transaction có thể xảy ra nhiều lần. Dùng khóa nghiệp vụ, constraint và thiết kế idempotent khi cần.

## 6. API bất đồng bộ: `CompletionStage` và quản lý vòng đời chính xác

### 6.1. Cơ chế

`AsyncSession` trả về `CompletionStage<T>`. Thread gọi có thể tiếp tục công việc thay vì đợi Neo4j hoàn thành I/O. Các stage tiếp theo dùng `thenApply`, `thenCompose`, `handle` hoặc `whenComplete`.

- `thenApply`: chuyển đổi **giá trị đã hoàn thành** thành giá trị khác.
- `thenCompose`: ghép một thao tác vốn cũng trả `CompletionStage`, không tạo stage lồng stage.
- `handle`: xử lý cả thành công và thất bại.
- `whenComplete`: hook quan sát kết quả/lỗi; **không phải cơ chế tự động chờ công việc dọn dẹp async bên trong callback**.

Một quy tắc quan trọng: callback của stage có thể chạy trên **network I/O thread**. Không gọi `Thread.sleep(...)`, `join()`, `get()` hoặc làm tác vụ CPU nặng trong callback I/O này. Nếu phải tính toán nặng, chuyển qua `thenApplyAsync(..., executor)` với executor được quản lý.

### 6.2. Ví dụ async có đóng session sau khi xử lý

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

import org.neo4j.driver.Driver;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.async.AsyncSession;

static CompletionStage<List<UserView>> findActiveAsync(
        Driver driver, String prefix) {

    String cypher = """
        MATCH (u:DriverDemoUser)
        WHERE u.active = true AND u.id STARTS WITH $prefix
        RETURN u.id AS id, u.name AS name
        ORDER BY name
        LIMIT $limit
        """;

    AsyncSession session = driver.session(
        AsyncSession.class,
        SessionConfig.forDatabase("neo4j")
    );

    CompletionStage<List<UserView>> query = session.executeReadAsync(
        tx -> tx.runAsync(
                cypher, Map.of("prefix", prefix, "limit", 100)
            )
            .thenCompose(cursor -> cursor.listAsync(
                record -> new UserView(
                    record.get("id").asString(),
                    record.get("name").asString()
                )
            ))
    );

    CompletableFuture<List<UserView>> completed =
        new CompletableFuture<>();

    query.whenComplete((users, queryError) ->
        session.closeAsync().whenComplete((ignored, closeError) -> {
            if (queryError != null) {
                completed.completeExceptionally(queryError);
            } else if (closeError != null) {
                completed.completeExceptionally(closeError);
            } else {
                completed.complete(users);
            }
        })
    );

    return completed;
}
```

Ở đây:
- `executeReadAsync` và `runAsync` trả các stage; `listAsync` lấy toàn bộ tập kết quả và ánh xạ khi truy vấn vẫn ở trong transaction.
- Session async **không dùng `try-with-resources`** vì phạm vi cú pháp Java có thể kết thúc trước khi I/O hoàn tất.
- Stage trả về cho caller chỉ hoàn tất sau khi `closeAsync()` hoàn thành. Điều này giúp tránh kết thúc request mà quên session đang chờ cleanup.
- Cách xử lý lỗi trên ưu tiên lỗi truy vấn nếu cả truy vấn và đóng session cùng lỗi. Trong service production, ghi log cả lỗi cleanup thay vì làm mất dấu lỗi thứ hai.
- Đoạn minh họa giả định lời gọi tạo stage không ném exception đồng bộ trước khi gắn callback; khi đóng gói thành utility chung, nên xử lý cả trường hợp setup thất bại.

Sử dụng từ caller:

```java
findActiveAsync(driver, "u")
    .thenAccept(users -> users.forEach(System.out::println))
    .exceptionally(error -> {
        System.err.println("Neo4j async query failed: " + error);
        return null;
    });
```

Trong ứng dụng thực tế, cần bảo đảm hệ thống **giữ vòng đời** của stage và không đóng Driver khi công việc chưa xong. Dùng `join()` ở lớp ngoài cùng của công cụ CLI chỉ khi chủ động muốn chờ; làm như vậy trong callback I/O sẽ phá lợi ích non-blocking.

### 6.3. Không nhầm async với xử lý lượng kết quả lớn

`listAsync()` vẫn **materialize toàn bộ result trong Java heap**. Nó chỉ bất đồng bộ về cách chờ I/O, không tự áp backpressure end-to-end theo nhu cầu xử lý bản ghi. Với output lớn:

- `nextAsync()`: yêu cầu bản ghi tiếp theo từng bước.
- `forEachAsync(...)`: áp dụng consumer cho từng record; consumer phải nhanh và không blocking.
- Reactive API: phù hợp hơn khi cần **consumer quyết định tốc độ lấy thêm record** theo chuẩn Reactive Streams.

Không dùng nhiều query đồng thời trên **cùng AsyncSession** rồi mong mỗi query có một transaction độc lập an toàn. Một session chỉ có một transaction hoạt động tại một thời điểm; dùng session riêng cho các operation độc lập.

## 7. Reactive API: subscriber, backpressure và vòng đời tài nguyên

### 7.1. Reactive khác async ở đâu?

`CompletionStage` biểu diễn **một kết quả sẽ có trong tương lai**. Nó có thể hoàn tất bằng một `List` rất lớn.

`Publisher` mô tả một **chuỗi tín hiệu** theo mô hình Reactive Streams: `onSubscribe`, `onNext`, `onError`, `onComplete`. Subscriber gọi `request(n)` để yêu cầu tối đa `n` phần tử tiếp theo. Nhờ đó driver có cơ chế điều tiết số record nhận từ Neo4j theo tốc độ tiêu thụ.

```text
Neo4j server
     |
     | Bolt / kết quả truy vấn
     v
Neo4j ReactiveSession
     |
     | Publisher<Record>
     v
Subscriber (Reactor Flux/Mono)
     |
     +-- request(10) --> nhận tối đa số phần tử được yêu cầu
     +-- xử lý 10 record
     +-- request(10) --> nhận thêm khi còn nhu cầu
```

Đây là **mô hình khái niệm**; driver, giao thức Bolt và Reactor có cơ chế buffer/prefetch, vì vậy “request 10” không nhất thiết đồng nghĩa chính xác 10 gói tin hay 10 record nằm trong memory ở mọi tầng. Backpressure giúp kiểm soát luồng dữ liệu, **không tự làm thuật toán Cypher phía Neo4j xử lý ít dòng hơn**.

### 7.2. Hai biến thể reactive của Java Driver 6.x

| Package | Chuẩn Publisher | Dùng trong |
| --- | --- | --- |
| `org.neo4j.driver.reactivestreams` | `org.reactivestreams.Publisher` | Project Reactor, Spring WebFlux và code đã dùng Reactive Streams |
| `org.neo4j.driver.reactive` | `java.util.concurrent.Flow.Publisher` | Ứng dụng dùng Java Flow API, không nhất thiết phụ thuộc Reactor |

Để dùng Reactor, cần thêm dependency `reactor-core` phù hợp với BOM của dự án và tương thích với phiên bản Driver/Spring. Nếu đang dùng Spring Boot, ưu tiên BOM và dependency management của phiên bản Boot đã chọn, thay vì tự ghép các bản Reactor không tương thích.

### 7.3. Ví dụ Reactor với quản lý session theo subscription

```java
import java.util.Map;

import org.neo4j.driver.Driver;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.reactivestreams.ReactiveSession;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

static Flux<UserView> findActiveReactive(
        Driver driver, String prefix) {

    String cypher = """
        MATCH (u:DriverDemoUser)
        WHERE u.active = true AND u.id STARTS WITH $prefix
        RETURN u.id AS id, u.name AS name
        ORDER BY name
        LIMIT $limit
        """;

    return Flux.usingWhen(
        Mono.fromSupplier(() ->
            driver.session(
                ReactiveSession.class,
                SessionConfig.forDatabase("neo4j")
            )
        ),
        session -> Flux.from(session.executeRead(
            tx -> Flux.from(tx.run(
                cypher,
                Map.of("prefix", prefix, "limit", 100)
            ))
            .flatMap(result -> Flux.from(result.records()))
            .map(record -> new UserView(
                record.get("id").asString(),
                record.get("name").asString()
            ))
        )),
        ReactiveSession::close
    );
}
```

Điểm thiết kế:
- `Mono.fromSupplier` tạo session **khi có subscription**, tránh mở session rồi không dùng.
- `executeRead` quản lý transaction ở dạng reactive; `tx.run(...)` trả publisher của result và `result.records()` trả publisher các bản ghi.
- `Flux.usingWhen` đóng session bằng publisher cleanup khi stream kết thúc; với overload dùng cleanup chung, Reactor xử lý cả completion, error và cancellation theo hành vi `usingWhen`.
- Không có `block()` ở bên trong pipeline. **Không sử dụng `subscribe()` bừa bãi trong tầng repository/service** rồi mất quyền kiểm soát lifecycle và lỗi. Thay vào đó trả `Flux` cho tầng gọi tiếp tục compose.
- Một subscription nên sở hữu một session riêng; đừng giữ `ReactiveSession` dùng chung toàn ứng dụng.

Cách xử lý trong service:

```java
Flux<UserView> names = findActiveReactive(driver, "u")
    .filter(user -> user.name() != null)
    .doOnError(error -> System.err.println(error.getMessage()));
```

`names` là **mô tả luồng**. Nó chưa truy vấn database cho đến khi có subscriber thực sự. Với Spring WebFlux, HTTP runtime thường subscribe vào publisher do controller trả về. Với ứng dụng tự viết, caller phải tạo subscription có chủ đích và quản lý vòng đời.

### 7.4. Reactive không có nghĩa “không bao giờ dùng RAM”

Backpressure điều tiết **đầu ra** nhưng:
- `collectList()` vẫn thu tất cả record vào một List, có thể gây OOM phía client.
- `sort()` trên Flux có thể phải giữ toàn bộ dữ liệu trước khi phát ra.
- `flatMap` với concurrency/prefetch quá lớn có thể mở nhiều truy vấn hoặc giữ buffer đáng kể.
- Gọi thư viện blocking (JDBC, đọc file đồng bộ, HTTP client chặn thread) trong `map(...)`/`flatMap(...)` có thể làm nghẽn event loop. Nếu bắt buộc, cần đưa tác vụ sang scheduler chuyên dụng theo hướng dẫn Reactor.
- Một query có `ORDER BY` hoặc aggregation lớn có thể đã phải xử lý nhiều dữ liệu **trên server** trước khi phát bản ghi đầu tiên.

Vì vậy, reactive có giá trị khi **toàn bộ đường xử lý** (driver → service → controller → client) tôn trọng mô hình non-blocking và backpressure, không chỉ vì đổi chữ ký Java sang `Flux`.

## 8. Chọn API theo kiểu ứng dụng

| Tình huống | Lựa chọn thường hợp lý | Lý do |
| --- | --- | --- |
| Spring MVC REST CRUD, kết quả vài dòng | **Sync** | Đơn giản, rõ transaction, dễ debug; virtual threads là lựa chọn thêm trên Java 21+ |
| CLI migration hoặc batch nghiệp vụ tuyến tính | **Sync** | Quy trình tuần tự và lỗi có điểm dừng rõ ràng |
| Gateway gọi Neo4j và nhiều service I/O độc lập | **Async** | Ghép `CompletionStage` mà không giữ thread chờ từng I/O |
| Event-driven service dùng `CompletableFuture` | **Async** | Tương thích với pipeline đã có; xử lý lỗi bất đồng bộ |
| Spring WebFlux + Reactor từ đầu tới cuối | **Reactive** | Phù hợp `Flux`/`Mono`, context và backpressure |
| Export/stream lượng record rất lớn, consumer chậm | **Reactive** | Có cơ chế điều tiết nhu cầu nhận record, tránh buffer vô hạn ở client |
| Tính toán CPU nặng trên mỗi bản ghi | Tùy workload; thường kết hợp streaming và worker pool | Không chạy phép tính blocking/nặng trên I/O thread |
| Graph query nặng vì Cypher không dùng index | **Tối ưu query trước** | Đổi API không giải quyết query plan kém |
| Chỉ cần một câu truy vấn ngắn | **Sync**, có thể dùng `Driver.executableQuery` | Tránh vòng đời callback phức tạp khi không cần |

**Một hệ thống không cần dùng duy nhất một kiểu API cho mọi tác vụ.** Tuy nhiên, việc trộn kiểu phải có ranh giới rõ ràng. Tránh tạo request WebFlux nhưng gọi repository blocking trên event loop. Tránh chuyển tất cả code imperative sang Reactor khi đội ngũ chưa có cơ chế giám sát lỗi và cancellation phù hợp.

## 9. Ranh giới transaction, retry và consistency dùng chung

### 9.1. Chọn managed transaction hay auto-commit

| Nhu cầu | API sử dụng |
| --- | --- |
| Một nghiệp vụ đọc/ghi cần transaction với tự retry lỗi tạm thời | Sync `executeRead/executeWrite`, async `executeReadAsync/executeWriteAsync`, reactive `executeRead/executeWrite` |
| Một câu Cypher chạy auto-commit | Sync `session.run`, async `session.runAsync`, reactive `session.run` |
| Kiểm soát `commit`/`rollback` thủ công | `beginTransaction` và biến thể async/reactive tương ứng |
| Cypher `CALL { ... } IN TRANSACTIONS` | **Auto-commit/implicit transaction**; không bọc trong managed transaction |

Managed transaction được Neo4j Driver **tự động thử lại khi lỗi được xác định là transient**. Vì callback có thể chạy lại, tránh side effect bên ngoài database bên trong callback. Khi xử lý payment, gửi email hoặc ghi hệ thống khác, dùng idempotency key/outbox hoặc kiến trúc giao dịch phù hợp.

Ví dụ lỗi thường gặp:

```java
// SAI với truy vấn tự phân lô bằng CALL ... IN TRANSACTIONS:
session.executeWrite(tx ->
    tx.run("""
        LOAD CSV WITH HEADERS FROM $source AS row
        CALL (row) {
          MERGE (:DriverDemoUser {id: row.id})
        } IN TRANSACTIONS OF 1000 ROWS
        """,
        Map.of("source", csvUrl)
    ).consume()
);
```

Câu lệnh này tự mở các transaction con, vì vậy phải chạy trong **implicit transaction** của `session.run(...)` hoặc tương đương async/reactive. Đồng thời, file CSV phải truy cập được từ Neo4j server theo cấu hình.

### 9.2. Kết quả chỉ có hiệu lực khi transaction còn sống

- Với sync, `Result` còn phụ thuộc transaction/session; trong callback nên map thành DTO/list cần thiết trước khi trả.
- Với async, `ResultCursor` phụ thuộc transaction; tiêu thụ bằng `listAsync`/`forEachAsync`/`consumeAsync` **bên trong stage của callback**. Không trả cursor ra ngoài rồi đóng session.
- Với reactive, trả publisher **đúng phạm vi transaction** và giữ session sống tới khi stream kết thúc/cancel; không giữ `ReactiveResult` để dùng sau khi transaction đóng.

Một câu truy vấn có thể được gửi nhưng kết quả được **lấy lười (lazy)**. Muốn chắc chắn thao tác auto-commit đã hoàn tất, tiêu thụ kết quả hoặc đóng/commit transaction/session đúng vòng đời.

### 9.3. Routing, bookmarks và cluster

Với URI `neo4j://` trỏ tới cluster, chọn `executeRead`/`executeReadAsync`/`executeRead` reactive giúp driver route thao tác đọc, còn write transaction được route đến server thích hợp. Đây là **hướng định tuyến**, không phải quyền hạn bảo mật; RBAC vẫn do Neo4j kiểm soát.

Một session nối các transaction theo **causal consistency**. Nếu có luồng ghi ở request A rồi đọc ở request B qua **hai session riêng**, cần dùng bookmark manager/bookmarks theo API phiên bản tương ứng nếu muốn bảo đảm khả năng thấy thay đổi đã commit trên cluster. Không tự giả định mọi read replica cập nhật tức thì ngay sau ghi.

### 9.4. Cancellation và timeout

- Timeout ở tầng Java HTTP hay Reactor **không đồng nghĩa chắc chắn Neo4j đã rollback mọi tác vụ**. Cần xử lý trạng thái transaction và xác minh sau lỗi/kết nối mất.
- `CompletionStage.cancel(...)` không nên được xem là cơ chế nghiệp vụ chắc chắn hủy query trên server.
- Reactive subscription có tín hiệu `cancel`, driver có thể dọn session/transaction, nhưng nếu thao tác ghi đã commit thì cancel phía client **không hoàn tác commit**.
- Khi cần deadline cho transaction, dùng `TransactionConfig` với `withTimeout(...)` và cấu hình thích hợp; đánh giá thêm timeout của gateway, pool và server.

Nếu response bị mất sau write, ứng dụng có thể không biết write đã commit hay chưa. Dùng khóa nghiệp vụ và `MERGE`/constraint để retry an toàn thay vì `CREATE` vô điều kiện.

## 10. Bộ nhớ, connection pool, thread và hiệu năng

### 10.1. Driver dùng chung, session theo operation

Một `Driver` giữ connection pool. Việc tạo session thường nhẹ; **không giữ một session toàn cục cho mọi request**. Session không thread-safe và không xử lý nhiều transaction độc lập đồng thời. Nếu có 1.000 request đồng thời nhưng pool chỉ có số connection hữu hạn, một số request phải **chờ lấy connection** bất kể sử dụng sync/async/reactive.

Điều chỉnh pool cần xem:
- Mức đồng thời thực, query latency và số database/địa chỉ server.
- `maxConnectionPoolSize`, thời gian chờ lấy connection và giới hạn phía server.
- Tỷ lệ request timeout, retry và transaction dài giữ connection.
- Số record truyền về, kích thước fetch và heap của client.

**Không tăng pool vô hạn** với hy vọng mọi request sẽ nhanh hơn: Neo4j server còn giới hạn CPU, bộ nhớ, page cache, I/O và khóa. Một query chậm do full scan có thể làm tình hình tệ hơn khi mở thêm rất nhiều request song song.

### 10.2. Async/Reactive và thread

- Sync giữ một thread trong lúc chờ I/O; mô hình servlet truyền thống cần đủ thread, Java virtual threads giảm chi phí giữ thread khi phù hợp.
- Async trả stage để caller không phải block; nhưng mọi callback phải tuân thủ quy tắc **không blocking network I/O thread**.
- Reactive điều phối subscriber, prefetch và backpressure; vẫn cần thread để xử lý sự kiện và CPU.
- Khi xử lý nhiều bản ghi có CPU work nặng, dùng executor/scheduler chuyên dụng; đo latency và queue thay vì tạo thread không giới hạn.

### 10.3. Đo đúng thứ cần cải thiện

| Metric | Ý nghĩa |
| --- | --- |
| Latency p50/p95/p99 | Trải nghiệm người dùng khi query + driver + ứng dụng hoàn tất |
| Throughput (requests/s) | Khả năng phục vụ khi số request tăng |
| Thời gian chờ connection | Pool có phải điểm nghẽn không |
| Số session/transaction đang hoạt động | Có thao tác bị giữ quá lâu không |
| JVM heap và GC | Có buffer quá nhiều record/list không |
| Event loop/worker utilization | Async/reactive có bị blocking ở callback không |
| Server CPU, I/O, page cache | Nghẽn thực sự có nằm phía Neo4j không |
| `EXPLAIN` / `PROFILE` Cypher | Có index seek, fan-out, Cartesian product, DB Hits lớn không |

So sánh ba API chỉ công bằng khi dùng **cùng câu Cypher, cùng tham số, cùng dữ liệu, cùng cấu hình pool và tương đồng tải**. `async` không tự giảm DB Hits hoặc số relationship Neo4j phải duyệt.

## 11. Spring Data Neo4j: chọn cả stack, không chỉ đổi Driver API

Spring Data Neo4j (SDN) được xây dựng trên Neo4j Java Driver, nhưng thêm ánh xạ entity, repository, template/client và cơ chế transaction của Spring.

### 11.1. Ứng dụng imperative

Một ứng dụng Spring MVC có thể dùng:

- `Neo4jRepository<T, ID>`.
- `Neo4jClient` (imperative).
- `Neo4jTemplate` và Spring transaction manager.
- Java Driver sync trực tiếp khi cần truy vấn đặc biệt, với điều kiện hiểu rõ ranh giới transaction.

Ví dụ repository:

```java
interface UserRepository
        extends org.springframework.data.neo4j.repository.Neo4jRepository<
            DriverDemoUserEntity, String> {

    java.util.List<DriverDemoUserEntity> findByActiveTrue();
}
```

Đây là **mẫu chữ ký giao diện**, còn entity phải được ánh xạ đúng theo version SDN, có `@Node` và `@Id` phù hợp. Repository mặc định đi theo mô hình imperative; không nên gọi trên event loop WebFlux nếu không có chiến lược đưa công việc blocking ra ngoài.

### 11.2. Ứng dụng reactive

Ứng dụng WebFlux có thể dùng:

- `ReactiveNeo4jRepository<T, ID>`.
- `ReactiveNeo4jClient`.
- `ReactiveNeo4jTemplate` và reactive transaction manager.
- Java Driver reactive trực tiếp nếu cần kiểm soát publisher/chức năng cụ thể.

Mẫu repository:

```java
interface ReactiveUserRepository
        extends org.springframework.data.neo4j.repository.ReactiveNeo4jRepository<
            DriverDemoUserEntity, String> {

    reactor.core.publisher.Flux<DriverDemoUserEntity> findByActiveTrue();
}
```

Một phương thức trả `Flux` **chưa đủ bảo đảm non-blocking** nếu bên trong service gọi thêm API blocking. Reactive transaction trong Spring dựa vào **Reactor context**; không thể dựa vào ThreadLocal của transaction imperative để tự truyền qua chuỗi async/reactive.

**Chú ý:** nếu ứng dụng lấy bean `Driver` và tự gọi `driver.session(...)`/`executeWrite(...)`, những transaction driver đó không mặc nhiên tham gia vào một `@Transactional` đang do Spring Data Neo4j quản lý. Chọn một chiến lược transaction rõ ràng để tránh lầm tưởng nhiều thao tác ở hai tầng thuộc cùng giao dịch nguyên tử.

### 11.3. Phân biệt “async trong Java” với “reactive trong Spring”

`CompletableFuture` không tự biến `Neo4jRepository` thành repository bất đồng bộ có backpressure. Spring Data Neo4j hỗ trợ imperative và reactive; nếu cần async cho một workflow riêng, có thể dùng **Driver AsyncSession** trong component chủ động quản lý transaction, không cần chuyển cả ứng dụng thành WebFlux.

## 12. Những lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- |
| Async API vẫn block request thread | Gọi `join()` / `get()` ngay khi nhận stage | Compose với `thenCompose`/`thenApply` và trả stage lên tầng gọi |
| Deadlock/độ trễ bất thường | Callback trên I/O thread gọi hàm blocking | Chuyển CPU/blocking task sang executor thích hợp |
| `Connection acquisition timed out` | Pool hết slot vì nhiều transaction giữ connection | Kiểm tra thời gian giữ session, query plan và pool sizing |
| Memory tăng mạnh dù dùng `listAsync` | Vẫn gom toàn bộ kết quả thành List | Dùng incremental cursor hoặc reactive backpressure |
| Trả `Flux` nhưng không có query nào chạy | Không có subscriber | Trả publisher cho controller/reactive runtime hoặc subscribe có quản lý |
| Query chạy hai lần khi hai subscriber độc lập | Publisher lạnh được subscribe hai lần | Hiểu semantics mỗi subscription và thiết kế cache/share khi đúng nghiệp vụ |
| Reactor bị nghẽn | `block()` hoặc JDBC/HTTP blocking trong pipeline | Tránh block event loop; dùng scheduler chuyên dụng nếu buộc phải bridge |
| Session leak | Quên `closeAsync` hoặc không cleanup publisher khi cancel | `closeAsync` trong chain; `usingWhen` cho reactive |
| Lỗi `ResultConsumedException` | Dùng cursor sau khi transaction/session đóng | Map/consume result trong transaction scope |
| Viết duplicate khi retry | Callback có side effect hoặc `CREATE` không có khóa | Sử dụng constraint, `MERGE` và idempotent logic |
| Java Driver 6 không có `rxSession()` | API cũ đã bị xóa | Dùng `driver.session(ReactiveSession.class, ...)` |
| `CALL ... IN TRANSACTIONS` báo lỗi transaction | Được gọi trong managed transaction | Gọi bằng implicit/auto-commit query |
| WebFlux + SDN blocking bị chậm | Repository imperative được gọi trên event loop | Dùng reactive repository/client hoặc tách blocking có kiểm soát |
| Reactive stream rất lớn nhưng server chậm | Cypher sort/aggregate/full scan vẫn tốn tài nguyên | Tối ưu `EXPLAIN`/`PROFILE`, predicate/index và output |
| Request đã timeout nhưng dữ liệu vẫn được ghi | Client timeout/cancel xảy ra sau commit | Thiết kế retry an toàn và kiểm tra trạng thái thực |

## 13. Bài tập thực hành

1. Chạy bộ dữ liệu `DriverDemoUser` và viết một truy vấn đọc bằng sync `executeRead`, trả `List<UserView>`. Đo thời gian tổng với `LIMIT 10` và `LIMIT 1000` trên dữ liệu thử đủ lớn.
2. Viết lại bài 1 bằng `AsyncSession`, bảo đảm stage trả về chỉ hoàn thành sau `closeAsync`. Giải thích vì sao dùng `join()` ngay sau `executeReadAsync` loại bỏ lợi ích async ở thread gọi.
3. Chuyển bài 1 thành Reactor `Flux<UserView>`. Chạy với subscriber yêu cầu chậm, theo dõi sự khác nhau giữa `flatMap`, `concatMap` và `collectList`.
4. Một service Spring MVC có 40 request/s, mỗi request trả 5 node; một service WebFlux nhận 5.000 subscriber và stream mỗi subscriber 10.000 record. Đề xuất API cho từng dịch vụ và cách kiểm soát pool/heap.
5. Viết một thao tác ghi cập nhật quan hệ `(:Supplier)-[:SUPPLIES]->(:Product)` bằng managed transaction. Nêu vì sao gửi thông báo Kafka trực tiếp trong callback `executeWrite` có nguy cơ phát nhiều lần.
6. Với một query import dùng `CALL { ... } IN TRANSACTIONS`, chỉ ra tại sao phải chạy auto-commit ở cả ba API và vì sao cần đối soát dữ liệu khi batch đã commit một phần.
7. Viết checklist smoke test Java Driver 5 → 6: session factory, transaction callback, reactive import, vòng đời session, retry, timeout, mapping và driver closing.
8. Nếu một `Flux` bị cancel sau khi cập nhật graph, có chắc database rollback không? Đề xuất cách ghi idempotency key và kiểm tra kết quả.
9. Một pipeline dùng `Flux.from(session.executeRead(...))` nhưng vẫn gọi `collectList()` với hàng triệu node. Phân tích nơi có thể hết heap và thiết kế phương án tiêu thụ an toàn.
10. Giải thích vì sao một ứng dụng có nhiều request async vẫn có thể chậm nếu `PROFILE` cho thấy hàng triệu `DB Hits` và không có index chọn lọc.

## 14. Checklist chọn giải pháp trước khi triển khai

1. **Kiến trúc:** hệ thống hiện là imperative, `CompletionStage` hay Reactor/Flow?
2. **Nhu cầu đầu ra:** trả một DTO, vài chục bản ghi hay stream hàng triệu record?
3. **Mức đồng thời:** bao nhiêu request thực sự hoạt động, bao nhiêu connection sẵn có?
4. **Transaction:** read/write, managed/auto-commit, retry và idempotency thế nào?
5. **Vòng đời:** Driver chia sẻ, mỗi operation có session riêng, dọn dẹp theo lỗi/hủy?
6. **Thread:** có callback blocking, CPU nặng hoặc `block()` trong event loop không?
7. **Dữ liệu:** câu Cypher có index/constraint phù hợp, có fan-out và aggregation lớn không?
8. **Phiên bản:** Driver/Neo4j/SDN/Reactor tương thích; có dùng API đã bị xóa trong 6.x không?
9. **Giám sát:** có latency p95, pool wait, JVM heap, retry, query log, `EXPLAIN`/`PROFILE` không?
10. **Thử tải:** đo với dữ liệu và request mix đại diện; chọn giải pháp đơn giản nhất đáp ứng SLO.

## 15. Ghi nhớ

- **Sync** là lựa chọn rõ ràng cho imperative CRUD và nghiệp vụ có luồng tuyến tính; Java 21+ với virtual threads cũng đáng cân nhắc khi tải I/O đồng thời cao.
- **Async** dùng `AsyncSession` và `CompletionStage` khi ứng dụng cần ghép nhiều tác vụ I/O không chặn thread; tiêu thụ cursor và chờ `closeAsync` đúng cách.
- **Reactive** dùng `ReactiveSession`, `Publisher` và backpressure cho pipeline vốn đã reactive, đặc biệt khi consumer cần điều tiết tốc độ nhận record.
- **Async không đồng nghĩa reactive**: `listAsync()` vẫn có thể gom cả kết quả vào RAM; `collectList()` trong Reactor cũng vậy.
- **Driver dùng chung, Session theo operation**. Session không thread-safe; mỗi transaction độc lập cần ngữ cảnh riêng.
- **Managed transaction có thể retry**, nên callback cần an toàn khi chạy lại; `CALL { ... } IN TRANSACTIONS` cần implicit transaction.
- **Spring Data Neo4j imperative và reactive có transaction manager khác nhau**; gọi driver trực tiếp không tự tham gia transaction do Spring quản lý.
- Chọn API theo **kiến trúc, dữ liệu, số request đồng thời và nhu cầu backpressure**; xác minh bằng profiling và load test thay vì giả định API nào cũng nhanh hơn.

### Tài liệu tham khảo

- [Neo4j Java Driver Manual — Query the database](https://neo4j.com/docs/java-manual/current/query-simple/)
- [Neo4j Java Driver Manual — Run your own transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual — Non-blocking asynchronous queries](https://neo4j.com/docs/java-manual/current/async/)
- [Neo4j Java Driver Manual — Control results flow with reactive streams](https://neo4j.com/docs/java-manual/current/reactive/)
- [Neo4j Java Driver Manual — Upgrade from older versions](https://neo4j.com/docs/java-manual/current/upgrade/)
- [Neo4j Java Driver API — AsyncSession](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/async/AsyncSession.html)
- [Neo4j Java Driver API — ResultCursor (Async)](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/async/ResultCursor.html)
- [Neo4j Java Driver API — ReactiveSession (Flow)](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/reactive/ReactiveSession.html)
- [Spring Data Neo4j — Building Blocks](https://docs.spring.io/spring-data/neo4j/reference/introduction-and-preface/building-blocks.html)
- [Spring Data Neo4j — Reference Documentation](https://docs.spring.io/spring-data/neo4j/reference/)
