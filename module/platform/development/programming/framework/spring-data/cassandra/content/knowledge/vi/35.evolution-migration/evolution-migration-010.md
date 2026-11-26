# Nhận diện ví dụ Driver hoặc API bất đồng bộ thuộc thế hệ cũ

Khi học **SPRING_DATA_CASSANDRA**, bạn có thể gặp hai đoạn mã cùng truy vấn Apache Cassandra nhưng sử dụng những API rất khác nhau. Ví dụ cũ dùng `com.datastax.driver.core.Session`, `ResultSetFuture` và callback của Guava; ví dụ mới dùng `CqlSession`, `CompletionStage`, hoặc `ReactiveCassandraRepository` của Spring Data. Nếu sao chép một ví dụ thuộc thế hệ khác vào dự án hiện tại, lỗi có thể xuất hiện ngay ở import/compile, hoặc nguy hiểm hơn: ứng dụng chạy được nhưng block thread, tải quá nhiều trang kết quả hay xử lý timeout sai.

Bài học thuộc chương **Tiến hóa và di trú**. Mục tiêu là **nhận ra dấu vết của Java Driver và API bất đồng bộ thế hệ cũ**, phân biệt sự thay đổi ở *driver* với thay đổi ở *Spring Data Cassandra*, rồi biết cách đối chiếu và di trú ví dụ. Nội dung đặt trong ngữ cảnh truy cập dữ liệu phân tán: entity mapping, repository, `CassandraTemplate`, CQL, partition key, consistency, paging và hiệu năng.

> **Lưu ý về phiên bản:** “Cassandra 3.x/4.x” (phiên bản máy chủ) và “Java Driver 3.x/4.x” (thư viện client) là **hai trục khác nhau**. Tên `4.x` trong bài này chủ yếu nói về **thế hệ Java Driver**; việc chọn driver phải dựa trên phiên bản Spring Data, dependency thực tế và ma trận tương thích của dự án. API/package có thể khác ở một bản phân phối hoặc thế hệ driver mới hơn.

## 1. Vì sao nhận diện thế hệ API trước khi đọc ví dụ?

Giả sử dịch vụ cần lấy lịch sử đơn của một khách hàng theo khoảng thời gian. Bảng dữ liệu phục vụ truy vấn có thể là:

```sql
CREATE TABLE shop.orders_by_customer (
    customer_id uuid,
    placed_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    PRIMARY KEY ((customer_id), placed_at, order_id)
) WITH CLUSTERING ORDER BY (placed_at DESC, order_id ASC);
```

Với thiết kế này, `customer_id` là partition key; `placed_at` và `order_id` là clustering columns. Truy vấn phù hợp cần xác định partition và giới hạn phạm vi khi cần:

```sql
SELECT order_id, placed_at, status
FROM shop.orders_by_customer
WHERE customer_id = ?
  AND placed_at >= ?
  AND placed_at < ?;
```

Dấu `?` là bind marker dành cho prepared/bound statement, không phải literal để chạy trực tiếp trong `cqlsh`.

**CQL có thể giống nhau trong khi API Java hoàn toàn khác.** Cú pháp trả kết quả, cách đặt page size, loại future, cấu hình consistency và vòng đời session phụ thuộc thư viện bạn đang dùng. Vì vậy, việc đầu tiên khi gặp một snippet trên blog hoặc diễn đàn là xác định thế hệ và lớp trừu tượng của nó.

## 2. Bảng nhận diện nhanh: dấu vết của Driver 3.x và Driver 4.x

| Dấu hiệu trong ví dụ | Java Driver thế hệ 3.x | Java Driver thế hệ 4.x (nhánh `com.datastax.oss.driver`) |
| --- | --- | --- |
| Package chính | `com.datastax.driver.core.*` | `com.datastax.oss.driver.api.*` |
| Entry point | `Cluster`, `Session` | `CqlSession` |
| Mở kết nối | `Cluster.builder().addContactPoint(...).build()` rồi `cluster.connect()` | `CqlSession.builder().build()` với driver config phù hợp |
| Đọc đồng bộ | `Session.execute(...)` trả `ResultSet` | `CqlSession.execute(...)` trả `ResultSet` thuộc package mới |
| Đọc bất đồng bộ | `Session.executeAsync(...)` trả `ResultSetFuture` | `CqlSession.executeAsync(...)` trả `CompletionStage<AsyncResultSet>` |
| Gắn callback | `ListenableFuture` / `FutureCallback` / Guava | `thenApply`, `thenCompose`, `whenComplete` trên `CompletionStage` |
| Kết quả async / paging | `ResultSetFuture`, `ResultSet`; có API `fetchMoreResults()` | `AsyncResultSet.currentPage()`, `hasMorePages()`, `fetchNextPage()` |
| Statement, consistency | Kiểu `Statement` và `ConsistencyLevel` trong `driver.core` | Kiểu `Statement` và `DefaultConsistencyLevel` trong các package API mới |
| Cách mapper của driver | `MappingManager` / `com.datastax.driver.mapping.Mapper` | Mapper API/code generation thuộc hệ `com.datastax.oss.driver.api.mapper.*` khi dùng extension tương ứng |
| Dependency Maven/Gradle thường gặp | `com.datastax.cassandra:cassandra-driver-core` | `com.datastax.oss:java-driver-core` |

Bảng chỉ nhằm **nhận diện dấu vết**, không phải lời khuyên khai báo phiên bản mới nhất. Khi dự án dùng driver do nền tảng quản lý, fork hoặc bản driver có namespace khác, hãy tin vào **dependency tree và import thật** của dự án. Một từ `Session` hoặc `ResultSet` đứng riêng không đủ phân biệt vì nhiều thư viện có kiểu trùng tên.

### 2.1. Mẫu code chắc chắn mang phong cách cũ

```java
import com.datastax.driver.core.Cluster;
import com.datastax.driver.core.Session;
import com.datastax.driver.core.ResultSetFuture;

Cluster cluster = Cluster.builder()
        .addContactPoint("127.0.0.1")
        .build();

Session session = cluster.connect("shop");

ResultSetFuture future = session.executeAsync(
        "SELECT order_id FROM orders_by_customer WHERE customer_id = "
                + "00000000-0000-0000-0000-000000000001");
```

Dấu hiệu quan trọng là **`com.datastax.driver.core` + `Cluster` + `ResultSetFuture`**. Đoạn này chỉ minh họa nhận diện API: trong ứng dụng thực, không mở cluster/session cho mỗi request, không tự nối giá trị đầu vào vào CQL và cần quản lý tài nguyên/secret/TLS rõ ràng.

### 2.2. Mẫu code phong cách Driver 4.x

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.util.concurrent.CompletionStage;

// Giả sử CqlSession được ứng dụng tạo và quản lý vòng đời trước đó.
CompletionStage<AsyncResultSet> stage = session.executeAsync(
        SimpleStatement.newInstance(
                "SELECT order_id FROM shop.orders_by_customer "
              + "WHERE customer_id = ?",
                customerId));
```

Với thế hệ này, `executeAsync` **hoàn thành một lần nhận được trang kết quả đầu tiên**, không có nghĩa toàn bộ dữ liệu của mọi trang đã nằm sẵn trong bộ nhớ. Tên `AsyncResultSet` và `CompletionStage` là hai dấu hiệu quan trọng.

## 3. Nhận diện các API async cũ: future không đồng nghĩa không chặn

Một đoạn code Driver 3.x thường sử dụng `ResultSetFuture` kế thừa cơ chế future của Guava:

```java
import com.datastax.driver.core.ResultSet;
import com.datastax.driver.core.ResultSetFuture;
import com.google.common.util.concurrent.FutureCallback;
import com.google.common.util.concurrent.Futures;
import java.util.concurrent.Executor;

ResultSetFuture future = oldSession.executeAsync(oldStatement);

Futures.addCallback(future, new FutureCallback<ResultSet>() {
    @Override
    public void onSuccess(ResultSet rows) {
        // Xử lý kết quả khi future hoàn tất.
    }

    @Override
    public void onFailure(Throwable error) {
        // Xử lý lỗi.
    }
}, callbackExecutor);
```

Ví dụ là dạng **Driver 3.x + Guava**; `oldSession`, `oldStatement`, `callbackExecutor` giả định đã được thiết lập. Callback API Guava còn có biến thể chữ ký khác theo phiên bản; không sao chép lẫn code của các đời Guava.

Một biến thể tưởng là async nhưng lại chặn:

```java
ResultSetFuture future = oldSession.executeAsync(oldStatement);

// get() chờ hoàn tất; gọi trên thread HTTP sẽ chặn thread đó.
ResultSet result = future.get();
```

`executeAsync()` không làm toàn bộ luồng xử lý tự động bất đồng bộ. Sau khi gọi `get()`, `getUninterruptibly()` hay các thao tác đọc trang có thể chặn, ứng dụng vẫn có nguy cơ chiếm thread trong lúc chờ Cassandra. Trên driver cũ cũng cần tránh thực hiện xử lý nặng trong callback chạy trên thread nhạy cảm của driver; chuyển công việc CPU/bộ nhớ lớn sang executor đã được giới hạn và giám sát.

### 3.1. Chuyển tư duy sang CompletionStage

Trong Driver 4.x, một phương thức trả `CompletionStage<AsyncResultSet>` và có thể ghép các bước xử lý:

```java
CompletionStage<Integer> numberOfRowsOnFirstPage =
    session.executeAsync(statement)
        .thenApply(page -> {
            int count = 0;
            for (Row ignored : page.currentPage()) {
                count++;
            }
            return count;
        });
```

Các biến `session`, `statement` được chuẩn bị từ trước; `Row` là `com.datastax.oss.driver.api.core.cql.Row`. Đoạn này **chỉ đếm hàng của trang đầu**, không phải số hàng toàn truy vấn.

- `thenApply`: biến đổi kết quả sẵn có của một stage.
- `thenCompose`: nối một thao tác cũng bất đồng bộ, chẳng hạn `fetchNextPage()`.
- `whenComplete`: quan sát kết quả/lỗi; tránh làm công việc chặn hoặc nặng trên thread hoàn thành stage.
- `toCompletableFuture().join()` hoặc `get()`: đưa thao tác quay lại dạng chờ đồng bộ; không nên xuất hiện trong request handler hướng tới non-blocking.

Không đổi mọi `ListenableFuture` thành `CompletableFuture` bằng thao tác sửa chữ mà bỏ qua luồng hoàn thành, cancellation, quản lý timeout và nghĩa của paging.

## 4. Khác biệt lớn nhất nằm ở cách xử lý paging

Cassandra có thể trả dữ liệu theo nhiều page. **Driver 3.x** và **Driver 4.x** cung cấp cách đi tiếp khác nhau, và chúng không thể tráo đổi API bằng import.

### 4.1. Driver 3.x: ResultSet có thể tải trang tiếp theo khi duyệt

Trong nhiều ví dụ cũ:

```java
ResultSetFuture resultFuture = oldSession.executeAsync(oldStatement);
ResultSet rs = resultFuture.getUninterruptibly();

for (Row row : rs) {
    process(row);
}
```

Đoạn này có thể làm người đọc nghĩ “async + for each” là đọc không chặn. Thực tế `getUninterruptibly()` đã chờ trang đầu; khi duyệt `ResultSet`, việc truy cập các hàng chưa tải có thể kích hoạt lấy page mới và chờ I/O. Trong ngữ cảnh API cần giới hạn latency, **duyệt hết tất cả hàng** còn có thể gây tốn CPU, bộ nhớ hoặc số request vượt dự kiến. Driver 3.x có cơ chế như `getAvailableWithoutFetching()` và `fetchMoreResults()` nhưng chúng cũng cần được dùng đúng với phiên bản và thời điểm fetch.

### 4.2. Driver 4.x: trang hiện tại và trang tiếp theo rõ ràng

```java
CompletionStage<AsyncResultSet> firstPage = session.executeAsync(statement);

CompletionStage<AsyncResultSet> secondPageIfAny =
    firstPage.thenCompose(page -> {
        for (Row row : page.currentPage()) {
            process(row);
        }
        return page.hasMorePages()
                ? page.fetchNextPage()
                : CompletableFuture.completedFuture(page);
    });
```

Ví dụ này **chỉ minh họa lấy tối đa thêm một trang**; nhánh không còn trang trả lại page cũ, không đọc lại các hàng đó. `CompletableFuture` ở đây thuộc `java.util.concurrent`. Trong triển khai thực tế, nên có hàm xử lý từng trang, kiểm soát số page, hạn mức dữ liệu, concurrency và khi nào dừng. Không dùng đệ quy thu thập tất cả trang vào một `List` nếu endpoint chỉ cần một trang.

Các lưu ý đặc biệt khi di trú:

1. `currentPage()` trả những hàng thuộc **trang hiện tại**, không phải mọi hàng còn lại của truy vấn.
2. `hasMorePages()` và `fetchNextPage()` điều khiển việc lấy trang tiếp theo; chúng không thay thế phân trang API HTTP có cursor riêng.
3. Kích thước trang và giới hạn số dòng không phải một: `page size/fetch size` ảnh hưởng chunk dữ liệu, `LIMIT` giới hạn kết quả logic.
4. Paging state phải dùng với **cùng câu truy vấn và bind values tương ứng**; không lấy state của tenant A để đọc tenant B.
5. Khi API trả danh sách từ nhiều partition/bucket/shard, Cassandra không tự trộn thành thứ tự toàn cục; tính nhất quán trang và sorting là nhiệm vụ của service.
6. Tăng page size không tự giải quyết được partition quá lớn hoặc hot partition key; hãy đo read latency, số partition và tải trên replica.

## 5. Spring Data Cassandra là lớp API khác với driver trực tiếp

Một câu hỏi dễ sai: “Dự án dùng Spring Data Cassandra, có nên thay `ResultSetFuture` bằng `ReactiveCassandraRepository` không?” Trước tiên cần phân biệt **ba cách truy cập**.

| Cách dùng | Ví dụ | Đặc điểm |
| --- | --- | --- |
| Driver trực tiếp, imperative | `CqlSession.execute(...)` | Điều khiển CQL/statement rõ ràng; lời gọi có thể chặn. |
| Driver trực tiếp, async | `CqlSession.executeAsync(...)` | Trả `CompletionStage<AsyncResultSet>`, người viết tự quản lý kết quả và các page. |
| Spring Data imperative | `CassandraRepository`, `CassandraTemplate` | Entity mapping, converter, query abstraction, giao diện thường trả đối tượng/collection; kiểm tra đặc điểm blocking của lời gọi. |
| Spring Data reactive | `ReactiveCassandraRepository`, `ReactiveCassandraTemplate` | API dùng Reactor `Mono`/`Flux`; có cơ chế subscription và điều khiển luồng, nhưng phải dùng đúng driver/module và tránh chặn bên trong pipeline. |

Các API có chữ **Async** từ những bài viết Spring Data Cassandra cũ có thể thuộc đời đã thay đổi hoặc không còn khuyến khích sử dụng ở nhánh hiện tại. Thấy `AsyncCassandraTemplate`, `AsyncCassandraOperations` hoặc `ListenableFuture` trong ví dụ là dấu hiệu cần **tra chính xác tài liệu của nhánh Spring Data đang dùng**, không tự kết luận class vẫn tồn tại trong dependency mới.

Không nhầm `@Async` của Spring với async driver: một phương thức đặt `@Async` có thể chạy code **blocking** trong thread pool và trả `CompletableFuture`. Điều đó giúp không chặn thread gọi ban đầu nhưng **vẫn dùng một worker thread để chờ I/O**. Reactive cũng mất lợi ích nếu thêm `block()` trên event loop.

### 5.1. Repository theo entity mapping không đổi quy tắc CQL

Ví dụ Spring Data repository imperative, giả sử `OrderByCustomer` và khóa `OrderKey` được ánh xạ đúng:

```java
public interface OrderRepository
        extends CassandraRepository<OrderByCustomer, OrderKey> {

    @Query("SELECT * FROM orders_by_customer "
         + "WHERE customer_id = ?0 "
         + "AND placed_at >= ?1 AND placed_at < ?2")
    List<OrderByCustomer> findInRange(
            UUID customerId, Instant fromInclusive, Instant toExclusive);
}
```

Cách viết `@Query` và binding tham số thuộc Spring Data Cassandra; truy vấn vẫn phải tuân theo partition key `customer_id` và clustering column `placed_at`. Nếu gọi một query sai khóa, việc dùng repository hoặc reactive không làm Cassandra chấp nhận câu lệnh.

Ở Spring Data reactive, kiểu trả về có thể là:

```java
public interface ReactiveOrderRepository
        extends ReactiveCassandraRepository<OrderByCustomer, OrderKey> {

    @Query("SELECT * FROM orders_by_customer "
         + "WHERE customer_id = ?0 "
         + "AND placed_at >= ?1 AND placed_at < ?2")
    Flux<OrderByCustomer> findInRange(
            UUID customerId, Instant fromInclusive, Instant toExclusive);
}
```

`Flux` là `reactor.core.publisher.Flux`. Với nhánh Spring Data phù hợp, Spring quản lý việc ánh xạ `Row` thành entity; song **không thể suy ra từ kiểu `Flux` rằng truy vấn chắc chắn có giới hạn page, không bao giờ bị chặn ở downstream hoặc đã tối ưu partition**. Cần xét cả cách subscribe, consumer, backpressure, timeout và lượng dữ liệu.

### 5.2. CassandraTemplate có phải API async không?

`CassandraTemplate` là API theo phong cách imperative trong Spring Data Cassandra. Việc gọi:

```java
List<OrderByCustomer> rows =
    cassandraTemplate.select(query, OrderByCustomer.class);
```

không được xem là non-blocking chỉ vì driver bên dưới có `executeAsync`. Khi cần mô hình reactive, dùng `ReactiveCassandraTemplate` hoặc repository reactive phù hợp với phiên bản và kiến trúc ứng dụng; không “di trú” bằng cách bọc hàng loạt `CassandraTemplate.select()` trong `Mono.just(...)` vì lệnh blocking có thể đã được thực hiện ngay lúc tạo Mono.

## 6. Cách chuyển một ví dụ Driver 3.x sang Driver 4.x

Hãy thực hiện theo **hành vi** thay vì đổi tên class một cách cơ học.

### 6.1. Ví dụ Driver 3.x dùng prepared statement

```java
// Legacy imports: com.datastax.driver.core.*
PreparedStatement prepared = oldSession.prepare(
    "SELECT order_id, status FROM shop.orders_by_customer "
  + "WHERE customer_id = ?");

BoundStatement bound = prepared.bind(customerId);
ResultSetFuture future = oldSession.executeAsync(bound);

// Không nên bê nguyên mô hình get()/for-each sang async 4.x.
```

Trong ví dụ này, `oldSession` thuộc Driver 3.x, `PreparedStatement`/`BoundStatement`/`ResultSetFuture` là các kiểu trong package cũ. `customerId` có kiểu `UUID`.

### 6.2. Ví dụ tương ứng với Driver 4.x

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

// session: CqlSession do ứng dụng quản lý vòng đời.
// Chỉ minh họa một lần chuẩn bị; trong thực tế tái sử dụng prepared statement.
PreparedStatement prepared = session.prepare(
    "SELECT order_id, status FROM shop.orders_by_customer "
  + "WHERE customer_id = ?");

BoundStatement bound = prepared.bind(customerId);

CompletionStage<List<UUID>> orderIdsOnFirstPage =
    session.executeAsync(bound)
        .thenApply(page -> {
            List<UUID> ids = new ArrayList<>();
            for (Row row : page.currentPage()) {
                ids.add(row.getUuid("order_id"));
            }
            return ids;
        });
```

Kết quả là **`CompletionStage<List<UUID>>` cho trang đầu**; nếu API cần nhiều trang, thêm chiến lược paging rõ ràng. Đặt `prepare` ở điểm khởi tạo/tái sử dụng phù hợp, vì chuẩn bị statement lặp lại mỗi request có chi phí. Tên biến `session` khác `Session` cũ: đối tượng là `CqlSession`.

Khi mã từ blog chỉ có tên class mà không có import, hãy kiểm tra dependency và IDE trước khi sao chép. `Row`, `ResultSet`, `PreparedStatement` trùng tên nhưng **khác package, API và mô hình dữ liệu**, nên không nên dùng import tự động tùy ý.

### 6.3. Thay API cấu hình consistency, retry, timeout một cách có chủ đích

Ở các mẫu cũ, có thể gặp:

```java
// Driver 3.x: kiểu ConsistencyLevel thuộc com.datastax.driver.core.
oldStatement.setConsistencyLevel(ConsistencyLevel.LOCAL_QUORUM);
```

Driver 4.x có hệ cấu hình và kiểu nhất quán khác, ví dụ tùy API statement:

```java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;

BoundStatement withConsistency =
    bound.setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
```

Trong API 4.x, statement thường theo hướng **immutable**: phương thức `setConsistencyLevel(...)` trả statement mới, vì vậy cần dùng **giá trị trả về** khi thực thi. Việc gọi setter rồi bỏ kết quả có thể khiến truy vấn vẫn dùng cấu hình cũ. Tùy loại statement, consistency còn có thể được cấu hình qua driver config; đọc quy tắc ưu tiên cấu hình của phiên bản sử dụng.

Không giữ nguyên timeout/retry policy của driver cũ bằng suy đoán. Kiểm tra idempotence của từng lệnh, read/write timeout, request timeout, cấu hình local datacenter và kết quả ghi có thể chưa xác định khi timeout. Với LWT, phải xác định ý nghĩa `[applied]`; đổi Java API không thay đổi tính chất phân tán của Cassandra.

## 7. Quy trình nhận diện ví dụ cũ trong dự án

Khi thấy một snippet có vẻ không tương thích, hãy làm các bước sau:

1. **Xác định dependency thật:** xem cây phụ thuộc `cassandra-driver-core`/ `java-driver-core`, phiên bản Spring Data Cassandra, Java và cách nền tảng quản lý driver. Không đoán từ phiên bản Cassandra server.
2. **Nhìn import trước:** `com.datastax.driver.core.*`, `ResultSetFuture`, Guava callback, `Cluster` thường là thế hệ 3.x; `com.datastax.oss.driver.api.*`, `CqlSession`, `AsyncResultSet` thường là 4.x.
3. **Xác định abstraction:** code dùng driver trực tiếp, Spring Data imperative hay Spring Data reactive? Một project có thể trộn các tầng; không đổi toàn bộ khi chỉ cần sửa một đường truy vấn.
4. **Đọc chữ ký kiểu trả về:** `ResultSetFuture` khác `CompletionStage<AsyncResultSet>` và khác `Flux<Entity>`. Ghi rõ ai chịu trách nhiệm lấy page, chuyển row thành entity và xử lý lỗi.
5. **Tìm điểm chặn:** `get()`, `getUninterruptibly()`, `join()`, `block()`, các vòng lặp duyệt hết kết quả hoặc gọi `CassandraTemplate` trong event loop.
6. **Đối chiếu CQL/schema:** query vẫn phải đúng partition/clustering key và kiểu dữ liệu CQL; chuyển driver không hợp thức hóa `ALLOW FILTERING`, `ORDER BY` không đúng hoặc quét nhiều partition.
7. **Xác định giới hạn paging/consistency/timeout:** so sánh behavior khi dữ liệu lớn, node chậm, replica unavailable và page cuối.
8. **Chuyển từng đường gọi:** sửa import, API, config và xử lý lỗi theo một transaction/flow có thể kiểm thử, thay vì bulk replace toàn repository.

Bảng câu hỏi giúp phân loại đoạn code:

| Nhìn thấy trong ví dụ | Nên tự hỏi |
| --- | --- |
| `new Cluster.Builder()` / `cluster.connect()` | Đây có phải Java Driver 3.x? Driver nào có trong dependency? |
| `ResultSetFuture` / `ListenableFuture` | Ai chờ kết quả? Callback có block thread driver không? |
| `getUninterruptibly()` | Đang chặn thread nào? Có fetch page tiếp theo một cách vô tình không? |
| `CqlSession.executeAsync()` | Có xử lý `currentPage()` và `fetchNextPage()` không? |
| `AsyncCassandraTemplate` từ một bài viết cũ | Class ấy có thuộc đúng Spring Data release train đang dùng không? |
| `Flux` với `block()` | Có phá vỡ chuỗi reactive và gây nghẽn thread không? |
| `Session` không kèm import | Là session của driver nào? Hay một loại session khác? |
| `SimpleStatement` / `BoundStatement` | Đây là statement thuộc package nào, có immutable không? |

## 8. Những lỗi thường gặp sau khi di trú

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `Cannot resolve symbol Cluster/ResultSetFuture` | Đã nâng driver, nhưng source vẫn import 3.x. | Đổi sang `CqlSession`/ `CompletionStage` và điều chỉnh logic, không thêm lại driver cũ chỉ để compile. |
| `ClassCastException` / API mismatch giữa `Row`, `PreparedStatement` | Hai package bị trộn hoặc dependency conflict. | Kiểm tra dependency tree và import hoàn chỉnh; loại bản driver thừa qua quản lý dependency thích hợp. |
| API async chậm ngang sync | `join/get/block`, callback nặng, gọi template blocking trong reactive chain. | Truy vết thread và đo thời gian chờ, xử lý async end-to-end hoặc cách ly blocking có chủ đích. |
| API trả thiếu dữ liệu | Chỉ xử lý `currentPage()` nhưng tưởng đã có mọi trang. | Thiết kế paging rõ ràng, kiểm tra `hasMorePages()` và giới hạn fetch. |
| Tăng đột biến bộ nhớ | Tự động gom tất cả trang thành collection lớn. | Trả từng trang/cursor, giới hạn page size và tổng dữ liệu/endpoint. |
| Consistency không có tác dụng như kỳ vọng | Lờ đi statement mới trả từ setter/override config. | Đối chiếu API immutable/config và xác minh thông số thực thi. |
| Exception mapping không khớp | Gói class ngoại lệ và hành vi translation đã đổi. | Phân loại theo root cause và operation; cập nhật handler ở Spring Data/driver tương ứng. |
| Ghi trùng sau timeout | Retry thao tác non-idempotent khi kết quả ghi chưa xác định. | Thiết kế idempotency key, đối soát và retry policy theo nghiệp vụ. |
| Query vẫn timeout dù driver mới | Partition quá lớn, hot key, đọc quá nhiều page hoặc consistency quá tốn. | Đo cluster, truy vấn và partition; điều chỉnh mô hình dữ liệu thay vì chỉ tăng timeout. |

**Đừng tự động ánh xạ mọi lỗi Cassandra thành lỗi đầu vào HTTP `400`.** Truy vấn sai khóa hoặc lỗi mapping thường là lỗi phía dịch vụ. Trả thông báo an toàn cho client, lưu request ID/operation/loại lỗi, tránh lộ CQL và bound values.

## 9. Kiểm thử hành vi khi thay API bất đồng bộ

Khi thay Driver 3.x bằng 4.x hoặc chuyển từ thao tác imperative sang reactive, cần kiểm tra hơn mức “build xanh”. Tập trung vào khác biệt có thể gây mất dữ liệu, block thread hoặc thay đổi độ trễ.

### 9.1. Kịch bản xác minh đề xuất

| Kịch bản | Điều cần chứng minh |
| --- | --- |
| Một partition, ít hơn một trang | Nhận đủ hàng, đúng thứ tự clustering và đúng kiểu Java/CQL. |
| Một partition, nhiều trang | Không mất hoặc lặp hàng, biết khi nào fetch trang tiếp theo, không fetch quá mức. |
| Không có hàng | Trả danh sách rỗng/ `Mono.empty()` đúng hợp đồng, không coi là lỗi driver. |
| CQL sai partition key/kiểu UUID | Lỗi được phân loại đúng; không bị che bởi callback hoặc exception wrapper. |
| Replica chậm hoặc timeout | Stage/reactive pipeline hoàn thành thất bại đúng nhánh, không treo request; logic retry không gây trùng ghi. |
| Consumer xử lý chậm | Không kéo tất cả trang vượt quá giới hạn bộ nhớ; có cơ chế áp lực ngược hoặc giới hạn fetch. |
| Hủy request | Kiểm tra lifecycle/cancellation theo API cụ thể; không giả định hủy stage đồng nghĩa hủy tác vụ đã gửi tới Cassandra. |
| Tải đồng thời cao | Đo request p95/p99, thread pool, số connection, pending requests và timeout rate. |
| Consistency/paging cấu hình | Kiểm tra statement thật nhận đúng consistency, page size và keyspace. |

### 9.2. Đo đúng giá trị của di trú

Việc nâng phiên bản có thể thay đổi pooling, retry, request execution, metrics và tracing. Hãy đo trước/sau ở tải tương đương:

- Throughput và p50/p95/p99 latency cho read/write theo query chính.
- Số request CQL và số page mỗi HTTP request; số partition bị truy cập.
- Mức sử dụng thread, CPU, heap, GC, backpressure và số stage đang chờ.
- Read/write timeout, unavailable, retry count; kết quả ghi sau timeout.
- Ảnh hưởng của kích thước partition, hot key, consistency level và local datacenter routing.

Không kết luận “non-blocking nhanh hơn” chỉ vì kiểu trả về là `CompletionStage` hoặc `Flux`. Khả năng mở rộng còn phụ thuộc việc không block ở các bước tiếp theo, giới hạn đồng thời, số page và đặc tính Cassandra cluster.

## 10. Tình huống thực hành: một đoạn code từ blog năm cũ

Bạn tìm thấy đoạn sau và định đặt vào một service Spring Data Cassandra hiện tại:

```java
ResultSetFuture future = session.executeAsync(statement);
ResultSet rs = future.getUninterruptibly();

for (Row row : rs) {
    response.add(row.getUUID("order_id"));
}
```

**Phân tích dấu hiệu:**

1. `ResultSetFuture`, `getUninterruptibly()`, phương thức `row.getUUID(...)` và kiểu `Session` phù hợp với phong cách **Java Driver 3.x**.
2. Ví dụ được gọi `executeAsync()` nhưng ngay sau đó chặn bằng `getUninterruptibly()`.
3. Vòng lặp có thể đọc nhiều page không chủ đích; `response` có thể tăng không giới hạn nếu toàn bộ kết quả lớn.
4. Nếu service hiện tại dùng `CqlSession` của Driver 4.x, những kiểu/phương thức trên không thể đơn giản sao chép và đổi import.
5. Nếu ứng dụng đã dùng Spring Data repository, cần hỏi liệu có cần thao tác driver trực tiếp hay đã có query/entity mapping tương ứng; chuyển cả tầng trừu tượng có thể không cần thiết.

**Hướng xử lý:** xác định dependency tree; giữ CQL hợp lệ theo partition key; lựa chọn `CqlSession.executeAsync(...)` và xử lý `AsyncResultSet.currentPage()`/`fetchNextPage()`, hoặc dùng repository/reactive template khi phù hợp; giới hạn số hàng/trang; bổ sung kiểm thử paging, timeout, consistency và tải đồng thời. Không kết luận đã di trú xong chỉ vì compiler không còn báo lỗi.

## Ghi nhớ

- `com.datastax.driver.core.Cluster/Session/ResultSetFuture` cùng Guava callback là dấu hiệu thường thấy của **Java Driver 3.x**.
- `com.datastax.oss.driver.api.core.CqlSession`, `CompletionStage<AsyncResultSet>` và `currentPage()/fetchNextPage()` là phong cách **Driver 4.x** thuộc nhánh package tương ứng.
- **Spring Data Cassandra** (repository/`CassandraTemplate`/reactive API) là một lớp abstraction khác; đừng đánh đồng `@Async`, `CompletableFuture` và non-blocking end-to-end.
- Khi di trú, phải xem lại **paging, blocking, consistency, retry, exception handling, session lifecycle và entity mapping**, ngoài import.
- CQL vẫn phải thiết kế theo **partition key**, tải thực và mô hình phân tán; nâng cấp driver không tự chữa hot partition, query filtering đắt đỏ hay lỗi dữ liệu.
