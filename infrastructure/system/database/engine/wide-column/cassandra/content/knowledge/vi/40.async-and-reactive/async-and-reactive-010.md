# Hủy Future/subscription và công việc còn chạy phía server trong Cassandra Java Driver

> **Chương:** Bất đồng bộ và reactive  
> **Trọng tâm:** Khi ứng dụng Java hủy `CompletableFuture` hoặc `Subscription`, điều gì dừng ở phía **client**, phần việc nào vẫn có thể đang chạy trên **coordinator/replicas Cassandra**, và cách thiết kế deadline, paging, idempotency, backpressure, metrics, reconciliation. Ví dụ minh họa Java 17 + Apache Cassandra Java Driver **4.x** (đối chiếu 4.17–4.19), Reactor 3.x khi cần. Chỉ thực hiện lab trong keyspace và cluster được cho phép.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả khác biệt giữa **hủy sự quan tâm tới kết quả** của client và **dừng xử lý truy vấn** phía Cassandra.
2. Phân biệt `CompletionStage<AsyncResultSet>`, `CompletableFuture.cancel(...)`, dependent stages, `CancellationException` và kết quả CQL thực tế.
3. Giải thích vì sao `cancel(true)` **không** phải tín hiệu interrupt JVM thread của Cassandra.
4. Nhận diện các race windows: request còn trong queue, chưa gửi, đã gửi, coordinator đang xử lý, ACK đã đến và future đã hoàn tất.
5. Sử dụng `AsyncResultSet.currentPage()`/`fetchNextPage()` để **không fetch trang mới khi người dùng không còn cần**.
6. Hiểu `executeReactive()` là **cold, unicast, single-subscription-only**, dùng `Subscription.cancel()`/Reactor `Disposable.dispose()` đúng thời điểm.
7. Phân biệt reactive **backpressure cho SELECT paging** với giới hạn concurrency/rate đối với **writes**.
8. Chọn deadline tầng HTTP, tầng service và `basic.request.timeout` mà không biến hủy thành bằng chứng “write chưa xảy ra”.
9. Thiết kế idempotency key, audit/reconciliation cho thao tác ghi bị hủy, timeout hoặc mất phản hồi.
10. Quan sát `pool.orphaned-streams`, `pool.available-streams`, `pool.in-flight`, `cql-client-timeouts` và Cassandra read/write latency.
11. Hoàn thành lab CQL/Java async/reactive, giải thích sự khác biệt giữa **kết quả hủy** và **trạng thái dữ liệu**.

**Bối cảnh dịch vụ `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`:** Cassandra lưu dữ liệu wide-column trên nhiều natural replicas dựa vào partition key/token, replication factor (RF), consistency level (CL) và write/read path. `Future`, reactive cancellation và stream backpressure đều nằm phía client/driver; chúng **không thay đổi RF, CL, compaction, repair hay trạng thái mutations đã xử lý**.

## 2. Một nguyên tắc quan trọng hơn mọi dòng code

**Hủy một Future hoặc subscription là thay đổi việc ứng dụng *còn muốn nhận kết quả*; không phải lời xác nhận Cassandra *đã dừng thực thi*.** Với CQL native protocol v4/v5 thông thường, không có cơ chế `CANCEL QUERY` bảo đảm dừng một truy vấn đã gửi. Driver có thể chấm dứt theo dõi request, không phát thêm các yêu cầu page hoặc bỏ response đến muộn. Coordinator/replicas vẫn có thể đang đọc SSTables, ghi commit log/memtable hoặc trả phản hồi.

~~~text
HTTP client             Java Driver               Cassandra coordinator/replicas
     |                       |                               |
     |---- GET/POST -------->|                               |
     |                       |--- QUERY/EXECUTE ------------>|
     |                       |                               | đang thực thi
     X disconnect            |                               |
     |                       |                               |
     |                  cancel Future/Subscription            |
     |                       X không còn chờ result           |
     |                       |                               | vẫn có thể tiếp tục
     |                       |<---- RESULT/ACK đến muộn ------|
     |                       |   có thể bị bỏ qua             |
     |                       |                               |
     |                 Không thể suy: server đã rollback      |
~~~

Đây là điểm có cơ sở trong [Speculative execution — Apache Java Driver](https://apache.github.io/cassandra-java-driver/4.18.1/core/speculative_execution/): khi driver “cancel” một execution thua cuộc, nó **bỏ response** khi response đến sau; Cassandra không hỗ trợ hủy request đang chạy theo ngữ nghĩa đó. [Native protocol v5](https://cassandra.apache.org/doc/latest/cassandra/reference/native-protocol.html) mô tả những message như `QUERY`, `EXECUTE`, `BATCH` và `RESULT` chứ không có một message `CANCEL` tiêu chuẩn cho truy vấn đang chạy.

### 2.1. Bốn việc dễ bị gọi chung là “hủy”

| Cơ chế | Tác động đáng tin cậy | Điều **không** được suy ra |
|---|---|---|
| `CompletableFuture.cancel(false)` | Hoàn tất Future ở trạng thái cancelled nếu chưa hoàn tất | Cassandra không ghi/đọc nữa |
| `CompletableFuture.cancel(true)` | Với `CompletableFuture` JDK, cờ `mayInterruptIfRunning` không cấp quyền kill server | Server bị interrupt |
| Reactive `Subscription.cancel()` | Subscriber ngừng yêu cầu/nhận thêm dữ liệu; driver dừng phát thêm nhu cầu phù hợp | Mọi CQL đã gửi đều được server huỷ |
| Driver `DriverTimeoutException` | Client hết ngân sách chờ một logical request | Mutation đã rollback hoặc không replica nào áp |
| Không gọi `fetchNextPage()` | **Không khởi tạo** các page requests tiếp theo trong luồng async | Truy vấn/page **đã gửi** được thu hồi |

Hãy tách hai câu hỏi: **“Kết quả ở client đã bị hủy chưa?”** và **“Tác động ở Cassandra đã xảy ra chưa?”**. Câu đầu có thể kiểm qua Future/subscription; câu sau cần dữ liệu, trace/metrics, consistency và audit phù hợp.

### 2.2. Hủy không phải giao dịch rollback

~~~text
Client cancel ACK                     Không chứng minh:
  [x] client ngừng quan tâm             [ ] mutation không được áp dụng
  [x] có thể không fetch thêm pages     [ ] mọi replica đã dừng
  [x] future/stream không còn result    [ ] batch tự rollback toàn bộ
                                        [ ] TTL/tombstone chưa được ghi
                                        [ ] retry sau đó luôn an toàn
~~~

Với write quan trọng như đơn hàng, thanh toán, nhập kho, ghi offset CDC, nếu cancel xảy ra sau khi gửi, kết quả thường phải xem là **UNKNOWN_OUTCOME** cho tới khi đối chiếu.

## 3. Vòng đời của một request bất đồng bộ

~~~text
T0: Application tạo statement, deadline/CL/idempotence
T1: session.executeAsync(statement) được gọi
T2: Driver đưa request qua throttler/queue (nếu có)
T3: Driver chọn coordinator, mượn connection/stream ID
T4: Request frame được gửi qua network
T5: Coordinator xử lý, giao tiếp natural replicas
T6: Replica trả response; coordinator tổng hợp theo CL
T7: Response frame về driver, decode
T8: CompletionStage<AsyncResultSet> hoàn tất
T9: Application xử lý rows / có thể fetchNextPage()
~~~

Một cancellation có thể xảy ra tại **bất kỳ** T1–T9:

- **Trước T3/T4:** nếu driver đã nhận cancellation và request chưa được gửi, có thể tránh được network/server work. Nhưng race vẫn có thể xảy ra, và mức độ propagation tới throttler **phụ thuộc phiên bản**.
- **Sau T4, trước T8:** server có thể vẫn xử lý; client có thể không nhận kết quả cuối.
- **Sau T8:** Future đã complete; `cancel` thường trả `false` và **không thu hồi kết quả**.
- **Sau T9, khi còn pages:** request cho trang đầu đã hoàn thành. Dừng ở đó sẽ tránh các **page requests chưa phát**; page request nào đã phát vẫn có thể đang chạy.

### 3.1. Tại sao thời điểm hủy không hoàn toàn quan sát được?

Các operations chạy trên JVM caller, queue của driver, Netty I/O thread, TCP, coordinator và replicas, nên không có một đồng hồ đơn cho “đã gửi/đang ghi/xong hết”. Đọc `isCancelled()` chỉ biết trạng thái một Future, **không cho biết server execution checkpoint**. Ngay cả khi client thấy cancellation trước response, request vẫn có thể hoàn tất ngay sau đó ở server.

### 3.2. Client trước/sau gửi — bảng phân loại

| Điểm dừng | Điều ta biết | Việc cần làm |
|---|---|---|
| Chưa gọi `executeAsync` | Không có request này do API gửi | Không thực thi là lựa chọn tốt nhất |
| Đang chờ trong throttler | Có thể chưa gửi, nhưng cần biết cancel đã được nhận chưa | Kiểm driver version/throttle metrics; không giả định |
| Chưa có network write, xác nhận được | Coordinator chưa nhận message này | Có thể ghi kết quả NOT_SENT nếu **có bằng chứng đáng tin** |
| Đã gửi frame, chưa response | **Không biết** mutation có xảy ra không | UNKNOWN_OUTCOME nếu là write |
| Response đã về, Future completed | Driver biết kết quả request theo CL | Xử lý result bình thường; hủy sau không đổi |
| Reactive đã phát vài rows | Những rows đã phát đã tới client | Không suy tất cả pages đã được đọc |

## 4. `CompletionStage` và `CompletableFuture`: hai abstraction khác nhau

Java Driver 4.x trả về `CompletionStage<T>` thay vì công khai một Future tùy ý mutate. API:

~~~java
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import java.util.concurrent.CompletionStage;

CompletionStage<AsyncResultSet> stage =
    session.executeAsync(statement);
~~~

Theo [FAQ của Java Driver 4.x](https://apache.googlesource.com/cassandra-java-driver/+/refs/tags/4.18.1/faq), `CompletionStage` hướng người dùng tới **composition**, tránh tùy tiện hoàn tất Future mà driver sở hữu. `toCompletableFuture()` tồn tại để tương tác với JDK APIs, **không** phải hợp đồng cho việc server sẽ ngừng hoạt động khi bị cancel.

### 4.1. Hủy từ tầng ứng dụng

~~~java
import java.util.concurrent.CompletableFuture;

CompletionStage<AsyncResultSet> stage =
    session.executeAsync(statement);

CompletableFuture<AsyncResultSet> future =
    stage.toCompletableFuture();

boolean changed = future.cancel(false);

System.out.println("future cancelled now? " + changed);
System.out.println("future.isCancelled = " + future.isCancelled());
~~~

**Ý nghĩa `changed=true`:** Future chưa hoàn tất và chuyển sang cancelled. **Không có nghĩa:** Cassandra nhận thông điệp “STOP” hoặc mutation chưa được thực thi. Nếu Future đã hoàn thành, `changed=false`. Giữa lúc kiểm `isDone` và gọi `cancel` có thể có race, nên phải dùng kết quả của thao tác cancel/observe thật, không dựa vào `if (!isDone())` rồi chắc chắn thành công.

### 4.2. `cancel(true)` không phải interrupt Cassandra

~~~java
boolean changed = future.cancel(true);
~~~

Trong `CompletableFuture` của JDK, tham số `mayInterruptIfRunning` **không điều khiển interruption** như cách một `FutureTask` trên thread pool có thể làm. Với Cassandra, coordinator ở **JVM khác**, nên một cờ boolean ở client càng không thể dừng thread đang xử lý bên server. Nếu chương trình sử dụng một `Future` *khác* do framework cung cấp, semantics cancel/interrupt thuộc framework đó; luôn xem đúng abstraction đang sở hữu.

### 4.3. `CancellationException` là client outcome

~~~java
future.whenComplete((result, error) -> {
    if (error == null) {
        System.out.println("Client received result");
    } else if (error instanceof java.util.concurrent.CancellationException) {
        System.out.println("Cancelled at client boundary");
    } else {
        System.out.println("Request failed: " +
            error.getClass().getSimpleName());
    }
});
~~~

Trong chains, lỗi có thể được bọc trong `CompletionException`; nếu muốn phân loại, unwrap có kiểm soát và giữ nguyên stack/cause cho logs nội bộ. **Cancellation** không đồng nghĩa `ReadTimeoutException`, `WriteTimeoutException`, `DriverTimeoutException` hoặc lỗi transaction rollback.

### 4.4. Future đã hoàn thành không bị “undo”

~~~java
CompletableFuture<String> done =
    CompletableFuture.completedFuture("PAID");

System.out.println(done.cancel(false));  // false
System.out.println(done.join());         // PAID
~~~

Đoạn này có thể chạy thuần JDK, không cần Cassandra. Nó minh họa rằng cancellation là **chuyển trạng thái của một Future chưa hoàn tất**, không phải thay đổi các kết quả đã được hoàn tất hay dữ liệu backend.

## 5. Hủy dependent stage khác hủy request gốc

Với `CompletableFuture`, đồ thị callback có thể giống:

~~~text
                          executeAsync(CQL)  [root]
                                  |
                    +-------------+-------------+
                    |                           |
              thenApply(parse)             whenComplete(metrics)
                    |
             thenCompose(next)
                    |
              HTTP response stage
                    |
              Client disconnected
                    |
                cancel(false)
~~~

**Hủy một stage phía dưới không mặc định truyền ngược lên mọi parent stage** của JDK, và càng không tự truyền tới Cassandra. Đó là hai phạm vi hủy khác nhau:

1. **Graph cancellation:** Stage nào bị đánh dấu canceled; callback/child nào không cần chạy nữa.
2. **Driver request cancellation:** Driver có nhận tín hiệu bỏ theo dõi request gốc không, ở giai đoạn nào?

### 5.1. Thí nghiệm thuần JDK

~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> upstream = new CompletableFuture<>();
CompletableFuture<Integer> downstream =
    upstream.thenApply(String::length);

downstream.cancel(false);

System.out.println(downstream.isCancelled()); // true
System.out.println(upstream.isCancelled());   // false

upstream.complete("abc");
System.out.println(upstream.join());          // abc
~~~

Thí nghiệm này chứng minh rằng **cancel child không đồng nghĩa cancel parent**. Nếu dịch vụ HTTP chỉ hủy một `thenApply` downstream trong khi request `executeAsync()` ở upstream vẫn sống, driver có thể tiếp tục nhận response. **Đừng thiết kế dựa trên propagation không được framework/JDK cam kết**.

### 5.2. Giữ lifecycle handle do request sở hữu

Một controller/service nên có:

~~~text
RequestContext {
  cancelled flag
  overall deadline
  root CompletionStage (nếu còn thuộc quyền quản lý)
  paging loop state
  in-flight operations count
  business operation ID nếu là write
}
~~~

Khi HTTP client ngắt:

- Đánh dấu context không còn cần response.
- Dừng phát **những page requests hoặc follow-up operations chưa bắt đầu**.
- Hủy những công việc ứng dụng có thể hủy an toàn, theo **API contract** của chính framework.
- Đối với CQL đã gửi, không báo “DB đã dừng” hay “write chắc chắn fail”.
- Dọn subscriptions, timers, log correlation và resources theo ownership.

Nếu ứng dụng dùng Spring WebFlux/Reactor, cancellation có thể lan qua một số operators do framework triển khai, nhưng **không nên mặc định mọi `CompletionStage` đã biến đổi đều bị hủy**. Cần integration test cho đúng version + reactive adapter.

### 5.3. `completeOnTimeout` và `orTimeout`

~~~java
CompletableFuture<AsyncResultSet> f =
    session.executeAsync(statement).toCompletableFuture();

f.orTimeout(1, java.util.concurrent.TimeUnit.SECONDS);
~~~

`CompletableFuture.orTimeout` hoàn tất **chính Future đó** với `TimeoutException` nếu chưa completed; `completeOnTimeout` hoàn tất chính Future với **giá trị thay thế**. Chúng **không gửi server-side CANCEL**. Khi áp lên Future do driver cung cấp, còn có thể ảnh hưởng lifecycle/cancellation handling bên trong; không coi đây là “timeout driver tương đương” với `basic.request.timeout`. Ưu tiên quản lý **deadline ở tầng ứng dụng**, dùng driver request timeout và tracing thực tế đã được review.

**Cực kỳ nguy hiểm với write:** `completeOnTimeout(fakeSuccess, ...)` có thể làm tầng HTTP tưởng đã ghi xong chỉ vì client tự đặt giá trị mặc định. Đối với read, fallback cache có thể được phép nếu business policy công bố rõ stale/fallback.

## 6. Native protocol, stream IDs và kết quả đến muộn

### 6.1. Stream ID là gì?

Trên mỗi connection CQL native protocol, driver gửi nhiều request song song. Mỗi message có **stream ID** để ghép đúng response với request:

~~~text
TCP connection to coordinator A

  stream 5  -> SELECT partition P
  stream 9  -> INSERT partition Q
  stream 13 -> SELECT partition R
                   |
            Responses có thể về không theo thứ tự gửi.
            Header stream ID giúp driver biết response thuộc request nào.
~~~

Khi client hủy một request **đã gửi**, driver vẫn phải xử lý khả năng **response cũ đến trễ**. Không thể tái sử dụng stream ID ấy tùy tiện cho request mới, nếu không response cũ có thể bị gắn nhầm vào request khác.

### 6.2. Orphaned streams

~~~text
T0:  stream 9 -> request A được gửi
T1:  A bị cancel hoặc một speculative attempt khác thắng
T2:  driver không quan tâm kết quả A nữa
T3:  stream 9 trở thành orphan/pending until late response
T4:  response A đến -> driver có thể thu hồi stream 9
     hoặc connection bị recycle theo ngưỡng riêng
~~~

Đọc [Speculative execution — Stream ID exhaustion](https://apache.github.io/cassandra-java-driver/4.18.1/core/speculative_execution/): nếu nhiều requests bị bỏ theo dõi nhưng chưa có response, `pool.orphaned-streams` tăng, `pool.available-streams` giảm và driver có thể **đóng/tạo lại connections**. Khi chỉ nhìn API-level cancellation, bạn có thể bỏ sót chi phí pool/churn này.

### 6.3. Hủy nhiều không tự giảm tải đã phát

Nếu ứng dụng bắn 10.000 SELECTs/s rồi hủy 80% vì người dùng cuộn nhanh:

| Sự kiện | Hệ quả có thể có |
|---|---|
| Nhiều queries đã vượt T4 | Cassandra vẫn phải xử lý phần đã phát |
| Subscriber không còn đòi pages | Giảm **các trang chưa fetch** trong tương lai |
| Orphaned stream IDs tăng | Pool ít capacity hơn, có thể recycle connections |
| HTTP response rate trông giảm | Không chứng minh QPS server đã giảm tương ứng |
| Phát sinh retry/speculative attempts | Có thể tăng số coordinator messages hơn nữa |

Giải pháp chính là **không gửi các truy vấn thừa từ đầu**: debounce, coalesce, cache, giới hạn concurrency, thực thi truy vấn theo partition key và giới hạn page/rows. Cancel là “phanh” sau khi hoạt động đã bắt đầu, không thay admission control.

### 6.4. Đóng socket để “kill query”?

Không nên đóng một connection chung hoặc toàn bộ `CqlSession` chỉ để hủy một CQL. Việc đó:

- Ảnh hưởng các requests khác trên cùng connection/session.
- Không bảo đảm coordinator dừng mutation đã nhận.
- Có thể tăng reconnect churn, prepared reprepare và request failures.

Session nên được **tái sử dụng** cho nhiều requests và đóng có kiểm soát khi ứng dụng shutdown. Một CancellationToken trong service không nên gọi `session.close()` cho một HTTP request riêng lẻ.

## 7. Công việc phía Cassandra tiếp diễn thế nào sau khi hủy?

### 7.1. Write path

~~~text
Client ---> coordinator
              |
              +-- xác định token/natural replicas
              +-- gửi mutation tới replicas
              |      |
              |      +-- commit log
              |      +-- memtable update
              |      +-- ACK khi đủ điều kiện CL
              |
              +-- ACK/timeout về client

Client cancellation có thể xảy ra khi bất kỳ bước nào đang diễn ra.
~~~

Nếu application `cancel` trước khi nhận ACK, **một hoặc nhiều replicas vẫn có thể ghi mutation**. Ghi có thể đạt CL sau đó hoặc không; điều bạn biết chỉ là ứng dụng đã **không nhận được xác nhận thành công** theo request đang theo dõi. Đừng kết luận “không ghi” hoặc “đã ghi” chỉ từ `isCancelled`.

### 7.2. Read path

Coordinator có thể đang:

- Đọc memtable và SSTables cho partition range.
- Hợp nhất phiên bản cells theo timestamp/TTL/tombstones.
- Liên hệ nhiều replicas/digest để đáp ứng CL.
- Đọc thêm SSTables do tombstone density hoặc partition lớn.
- Trả trang đầu đã được tính; sau đó các trang khác sẽ được yêu cầu riêng.

Nếu client hủy sau khi request trang đầu đã gửi, **server vẫn có thể hoàn tất trang đầu**. Với ordinary paging, **không gọi `fetchNextPage()`** giúp tránh phát những page requests tiếp theo. Reactive demand cancellation có thể giảm pagination tương tự, nhưng không “rewind” công việc đã làm.

### 7.3. CQL write ACK, commit log và compaction

Ngay cả khi ACK đã trả trước khi client cancel, các công việc downstream như **memtable flush, compaction hoặc replication maintenance/repair** vẫn sẽ diễn ra. Cả việc nhận ACK lẫn cancellation **không yêu cầu** các tầng lưu trữ phải dừng công việc theo lệnh phía Java.

**Tách khái niệm:**

- **CQL request lifecycle:** lần read/write/ACK theo CL.
- **Storage lifecycle:** memtable → SSTable → compaction, tombstone reclamation.
- **Replica convergence:** hints/repair/anti-entropy theo topology/điều kiện.

Không dùng cancellation làm cơ chế “xóa write khỏi disk” hoặc “dừng compaction”.

## 8. Trạng thái ghi không chắc chắn và idempotency

### 8.1. Case đặt hàng

~~~text
1. POST /orders nhận order_id=O-123, tenant=T-1
2. Java gửi INSERT ... order_id=O-123, status=NEW
3. HTTP client disconnect
4. Java cancel future; không nhận ACK
5. Cassandra có thể đã lưu row O-123
6. Client HTTP thử POST lại
~~~

Nếu lần POST thứ hai sinh **order_id khác**, hai rows có thể xuất hiện. Tác động phụ như trừ kho/gửi email cũng có thể bị lặp. Do đó:

- Sinh **business operation ID/idempotency key** ổn định ở boundary.
- Thiết kế primary key, event version và retry semantics có thể đối soát.
- Dùng điều kiện/version/outbox/dedup khi cần đúng nghiệp vụ.
- Với kết quả client bị hủy, lưu trạng thái `UNKNOWN_OUTCOME` hoặc reconciliation event; đừng thay bằng “FAILED, safe to retry”.

### 8.2. Idempotent flag không biến write thành idempotent

~~~java
BoundStatement write = insertPrepared.bind(
        tenantId, orderId, "NEW")
    .setIdempotent(true);
~~~

Chỉ dùng `setIdempotent(true)` khi **đã kiểm** replay cùng PK/values/timestamp/TTL và mọi side effects theo nghiệp vụ an toàn. Với COUNTER increment, LIST append, tự sinh UUID mỗi lần retry hoặc thao tác ngoài Cassandra, không tự đặt true. Driver dựa vào flag để quyết định retry/speculative execution trong một số đường lỗi; flag **không phải** transaction hay dedup.

### 8.3. Không suy “cancel = zero write” từ một SELECT ngay sau đó

Đọc lại ở CL `ONE` sau khi hủy write và thấy **không có row** không chứng minh chẳng replica nào đã ghi. Có thể:

- Mutation đang chờ ở coordinator/replica hoặc ACK chưa về.
- Replica được đọc chưa có phiên bản mới.
- Tombstone/TTL hoặc reconciliation thay đổi visibility.
- Query dùng sai partition/day/CL.

Reconciliation phải dùng **CL thích hợp**, đối chiếu event log/source-of-truth, version/timestamp và cửa sổ ổn định; đọc một lần ở `ONE` chỉ là **một quan sát**, không phải bằng chứng cuối cùng.

### 8.4. Ví dụ sai và đúng

**Sai:**

~~~java
future.cancel(true);
// "Vì đã cancel nên INSERT chắc chắn không tồn tại".
// generateNewOrderIdAndRetry();
~~~

**Đúng về nguyên tắc:**

~~~java
future.cancel(false);
// Mark outcome as unknown if write had possibly been sent.
// Do not invent a new business key.
// Reconcile orderId against authoritative business state.
// Retry only via reviewed idempotency policy and within deadline.
~~~

Đây là **pseudocode vận hành**: API thực để ghi trạng thái/reconcile nằm ngoài Java Driver và phụ thuộc kiến trúc ứng dụng.

## 9. Async paging: chỗ nên dừng để tránh công việc chưa bắt đầu

Trong Java Driver 4.x, `session.executeAsync` trả `AsyncResultSet` cho **một trang**. Duyệt `currentPage()` không tự gọi trang kế tiếp; ứng dụng chủ động gọi `fetchNextPage()`. [Async paging — Apache Java Driver](https://apache.github.io/cassandra-java-driver/4.18.0/core/paging/).

### 9.1. Đọc một trang

~~~java
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.concurrent.CompletionStage;

CompletionStage<AsyncResultSet> first =
    session.executeAsync(statement);

first.thenAccept(page -> {
    for (Row row : page.currentPage()) {
        System.out.println(row.getUuid("event_id"));
    }
    // Không gọi fetchNextPage():
    // dừng ở trang hiện tại, dù page.hasMorePages() có thể true.
});
~~~

Nếu code không gọi `fetchNextPage()`, **các trang sau chưa được request** trong luồng này. Nhưng trang đầu đã được request từ trước khi `first` hoàn tất. **Không** suy rằng server chưa đọc dữ liệu cho trang đầu hoặc toàn bộ SSTables chưa được chạm.

### 9.2. Dừng khi có cancellation flag

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.atomic.AtomicBoolean;

static CompletionStage<Integer> consumePages(
        AsyncResultSet page,
        AtomicBoolean cancelled,
        int previouslySeen) {

    int seen = previouslySeen;
    for (Row row : page.currentPage()) {
        if (cancelled.get()) {
            return CompletableFuture.completedFuture(seen);
        }
        // Chỉ đếm; business side effect bên trong callback
        // cần cơ chế idempotency riêng nếu có.
        seen++;
    }

    if (cancelled.get() || !page.hasMorePages()) {
        return CompletableFuture.completedFuture(seen);
    }

    final int nextSeen = seen;
    return page.fetchNextPage()
        .thenCompose(next ->
            consumePages(next, cancelled, nextSeen));
}
~~~

Gọi từ service:

~~~java
AtomicBoolean cancelled = new AtomicBoolean(false);

CompletionStage<Integer> consumed =
    session.executeAsync(statement)
        .thenCompose(first ->
            consumePages(first, cancelled, 0));

// HTTP disconnect handler / job stop event:
cancelled.set(true);

consumed.whenComplete((count, error) -> {
    if (error != null) {
        System.err.println("Async read failed");
    } else {
        System.out.println("rows consumed before stop=" + count);
    }
});
~~~

**Lưu ý quan trọng về tính cạnh tranh:** Có thể một `fetchNextPage()` đã xảy ra đúng lúc thread khác đổi flag. `AtomicBoolean` cho tính hiển thị/cross-thread coordination, **không tạo tính nguyên tử** giữa việc kiểm flag và gửi request tới server. Vì vậy code chỉ hứa **“không cố ý phát các trang tiếp theo sau khi đã quan sát cancelled=true”**, không hứa “hủy xong thì tuyệt đối không còn message nào đang đi”.

### 9.3. Hủy future của trang đang fetch

~~~java
CompletionStage<AsyncResultSet> nextStage =
    page.fetchNextPage();

CompletableFuture<AsyncResultSet> nextFuture =
    nextStage.toCompletableFuture();

nextFuture.cancel(false);
~~~

Future trang kế tiếp có thể chuyển sang cancelled, nhưng **page request đã gửi có thể vẫn chạy**. Với async paging thông thường, không có API “cancel toàn bộ SELECT đã chạy trên coordinator và rollback read I/O”. Hãy kết hợp cancellation flag để **không fetch các trang sau nữa**.

### 9.4. Page size và LIMIT không phải cùng khái niệm

~~~java
BoundStatement read = prepared.bind(tenantId, day)
    .setPageSize(100)
    .setIdempotent(true);
~~~

`page-size=100` là kích thước trang gợi ý, không phải tổng số rows của kết quả. Nếu user yêu cầu tối đa 50 rows, có thể cần **CQL `LIMIT 50`** và/hoặc giới hạn API ở tầng trên. Với partition rộng và tombstones, một trang 100 rows vẫn có thể gây scan lớn. Nếu downstream đã hủy vì không muốn đọc nữa, **đừng tự fetch đủ 100 trang để “cho sạch server”**.

### 9.5. Khi nào dùng reactive thay async paging thủ công?

| Nhu cầu | Async `fetchNextPage` | Reactive subscription |
|---|---|---|
| Xử lý từng trang rõ ràng | Phù hợp | Ít trực tiếp hơn |
| Muốn dừng trước trang kế tiếp | Kiểm flag trước `fetchNextPage` | Hủy downstream demand |
| Kết nối reactive HTTP stream | Cần adapter | Phù hợp tự nhiên |
| Người dùng muốn N rows | Duyệt/đếm thủ công | `take(N)` có thể hủy upstream |
| Điều tiết write concurrency | Tự quản futures/semaphore | Reactor `flatMap(..., concurrency)` |
| Biết server đã dừng vì cancel | **Không bảo đảm** | **Không bảo đảm** |

## 10. Reactive CQL: chỉ chạy khi có subscription

Java Driver 4.x có `CqlSession.executeReactive` trả `ReactiveResultSet`, một `Publisher<ReactiveRow>`. Do lịch sử dự án, loại reactive nằm dưới namespace `com.datastax.dse.driver.api.core.cql.reactive`, **nhưng vẫn hỗ trợ Cassandra OSS**.

~~~java
import com.datastax.dse.driver.api.core.cql.reactive.ReactiveResultSet;

ReactiveResultSet publisher =
    session.executeReactive(statement);

// Chưa subscribe => CQL chưa được gửi do publisher này.
~~~

Theo [Reactive Style Programming — Apache Java Driver](https://apache.github.io/cassandra-java-driver/4.18.1/core/reactive/), publisher mặc định là:

- **Cold:** chưa subscribe thì chưa execute CQL.
- **Unicast:** một nguồn dành cho một luồng tiêu thụ.
- **Single-subscription-only:** cùng `ReactiveResultSet` không cho subscribe hai lần.

### 10.1. Timeline khác hẳn executeAsync

~~~text
executeAsync(statement):
  gọi hàm -> logical request được bắt đầu
  lấy CompletionStage -> chờ response/fetch pages

executeReactive(statement):
  gọi hàm -> publisher object (chưa gửi CQL)
  subscribe -> mới bắt đầu execute
  request(n) -> subscriber đòi tối đa n items
  cancel -> ngừng tiêu thụ/demand upstream
~~~

Vì thế nếu tạo một reactive publisher rồi **không bao giờ subscribe**, không có CQL từ publisher đó gửi tới Cassandra. Đây là cách “ngăn request thừa” chắc chắn hơn hủy sau khi gửi. Nhưng **đã subscribe và đã phát request** thì quay lại quy tắc không có server-side kill.

### 10.2. Mã tạo publisher nhưng không thực thi

~~~java
ReactiveResultSet ignored = session.executeReactive(
    "SELECT release_version FROM system.local");

// Không có subscriber: không có CQL execution từ ignored.
// Tạo object không đồng nghĩa bắt đầu query.
~~~

Lỗi thường gặp khi viết reactive write:

~~~java
// SAI: doOnNext chỉ tạo ReactiveResultSet rồi bỏ đi.
Flux.just(insertStatement)
    .doOnNext(session::executeReactive);
// Nếu không có subscribe vào ReactiveResultSet,
// INSERT này không được thực thi theo pipeline trên.
~~~

**Cách đúng** là làm publisher con thành một phần chain có người subscribe:

~~~java
Flux.just(insertStatement)
    .flatMap(s -> Flux.from(session.executeReactive(s)))
    .then();
// Đây mới chỉ là Mono<Void>; cần subscribe/return đến framework.
~~~

Một lần nữa, **toàn bộ chain** vẫn phải được subscribe (chẳng hạn framework reactive HTTP làm việc đó). Chỉ tạo `Mono<Void>` rồi bỏ cũng không thực thi write.

## 11. Reactive `Subscription.cancel()`: ngừng nhận rows, không kill server

### 11.1. Code thuần Reactive Streams

~~~java
import org.reactivestreams.Subscriber;
import org.reactivestreams.Subscription;
import com.datastax.dse.driver.api.core.cql.reactive.ReactiveRow;

ReactiveResultSet source = session.executeReactive(readStatement);

source.subscribe(new Subscriber<ReactiveRow>() {
    private Subscription subscription;
    private int seen;

    @Override
    public void onSubscribe(Subscription s) {
        subscription = s;
        s.request(1); // Một row tại một thời điểm.
    }

    @Override
    public void onNext(ReactiveRow row) {
        seen++;
        System.out.println(row.getUuid("event_id"));
        if (seen >= 2) {
            subscription.cancel();
        } else {
            subscription.request(1);
        }
    }

    @Override
    public void onError(Throwable error) {
        System.err.println(
            "Reactive request failed: " +
            error.getClass().getSimpleName());
    }

    @Override
    public void onComplete() {
        System.out.println("All requested results completed");
    }
});
~~~

Trong Reactive Streams, `cancel` thường **không tạo `onComplete`**; nó là terminal decision phía subscriber và cho phép upstream dừng. Đoạn code trên có thể chạy callback trên driver I/O thread, vì vậy **không đặt I/O blocking/CPU-heavy trong `onNext`** ở production. Ví dụ chỉ in 2 rows trên lab; ứng dụng thật nên chuyển xử lý sang executor/scheduler phù hợp.

### 11.2. Hủy subscriber sau khi query đã được gửi

~~~text
subscribe()
    |
onSubscribe -> request(1)
    |
driver gửi SELECT cho trang đầu
    |
coordinator đang thực hiện
    |
onNext(row1)
    |
subscriber.cancel()
    |
driver không còn demand
    |
CQL trang đầu đã gửi VẪN có thể hoàn tất
~~~

**Phân biệt “không còn demand” và “không còn server work”.** Cassandra native protocol không trao đổi trực tiếp một tín hiệu `request(1)`/`cancel` để điều khiển việc đang đọc SSTables; driver dùng backpressure để quyết định **khi nào fetch pages mới**.

### 11.3. Không dùng `onComplete` làm ACK khi đã cancel

Nếu subscriber hủy ở row thứ hai, `onComplete` có thể không chạy, mặc dù **hai rows đã được deliver**. Đừng dùng “không thấy onComplete” để kết luận query thất bại; đó có thể là kết quả hợp lệ của việc client chủ động ngừng tiêu thụ.

Ngược lại, `onComplete` ở reactive write (không có rows) là tín hiệu client nhận **hoàn tất Publisher thành công**, theo CL/request semantics, không bảo đảm các hậu công việc compaction/repair đã kết thúc.

### 11.4. Đừng subscribe cùng `ReactiveResultSet` hai lần

~~~java
ReactiveResultSet rs = session.executeReactive(readStatement);

Flux<ReactiveRow> first = Flux.from(rs);
Flux<ReactiveRow> second = Flux.from(rs);

// Subscribe first rồi second trên cùng rs => lần thứ hai có thể
// phát IllegalStateException: publisher single-subscription-only.
~~~

Nếu cần retry/resubscribe có chủ đích:

~~~java
Flux<ReactiveRow> freshEachTime =
    Flux.defer(() -> Flux.from(
        session.executeReactive(readStatement)));
~~~

`Flux.defer` tạo `ReactiveResultSet` mới mỗi subscription. Điều này cũng có nghĩa **mỗi subscription sẽ tạo request mới**; không dùng `retryWhen` tùy tiện với writes không idempotent. Với multi-consumer read, cân nhắc shared/cache phù hợp **kích thước dữ liệu**, không cache bảng lớn vào heap.

## 12. Reactive backpressure và `take(N)`

### 12.1. Backpressure không phải giao thức nói trực tiếp với Cassandra

Reactive Streams có `Subscription.request(n)` để downstream thể hiện nhu cầu. **CQL native protocol không có frame `REQUEST_N_ROWS` cho từng subscriber**, nên driver thực hiện backpressure chủ yếu bằng cách:

1. Không phát quá nhiều rows tới subscriber khi demand chưa có.
2. Khi cần tiếp, driver yêu cầu **trang CQL tiếp theo**.
3. Khi subscriber ngừng/hủy, driver không cần tiếp tục request trang mới của cùng kết quả (trừ những pages đã in-flight/race).

Với SELECT lớn, cơ chế này **điều tiết tốc độ yêu cầu pages**, không có nghĩa mọi row trong trang đầu được server đọc đúng theo `request(1)`. Trang đầu có thể chứa hàng chục/hàng trăm rows đã được server xây dựng.

### 12.2. Reactor `take(2)`

~~~java
import reactor.core.publisher.Flux;
import com.datastax.dse.driver.api.core.cql.reactive.ReactiveRow;
import java.time.Duration;
import java.util.List;

List<ReactiveRow> firstTwo =
    Flux.from(session.executeReactive(readStatement))
        .doOnCancel(() ->
            System.out.println("Upstream subscription cancelled"))
        .take(2)
        .collectList()
        .block(Duration.ofSeconds(5));
~~~

Khi đã lấy 2 rows, `take(2)` có thể phát cancellation **upstream**, nên không tiếp tục đọc hết hàng nghìn rows chỉ để trả hai rows cho API. Nhưng dữ liệu trong trang đầu có thể đã được đọc/gửi. Nếu request thứ hai đã bắt đầu do prefetch, phần đó vẫn có thể được xử lý.

**Chi tiết operator:** `doOnCancel` được đặt **trước `take(2)`** trong pipeline để bắt tín hiệu hủy upstream. Nếu chỉ đặt `doFinally` sau `take`, tín hiệu downstream thường là `ON_COMPLETE` vì `take` hoàn tất bình thường sau N rows; đó không chứng minh upstream không bị hủy.

### 12.3. `take(N)` khác CQL `LIMIT N`

~~~text
SELECT ... LIMIT 2
   -> Cassandra có thể giới hạn tập kết quả hợp lệ ở server.

Reactive take(2)
   -> Application yêu cầu CQL có thể lớn hơn,
      rồi ngừng tiêu thụ sau 2 items.

Để tối ưu read:
  dùng CQL LIMIT đúng yêu cầu + partition key tốt
  và take/HTTP cancellation để chặn việc đọc tiếp khi client bỏ đi.
~~~

Nếu CQL quét partition rất rộng và có tombstones, `take(2)` không tự giảm chi phí của **trang đầu** hoặc công việc coordinator đã làm. Query-first data model vẫn là nền tảng trong Cassandra.

### 12.4. Reactive demand không tự giới hạn write concurrency

Khi ứng dụng **gửi writes**:

~~~java
Flux<Statement<?>> writes = ...;

// Nguy hiểm nếu upstream cực lớn và flatMap mở concurrency quá cao.
writes.flatMap(session::executeReactive);
~~~

Cassandra không thể dùng `Subscription.request(n)` phía client để ép coordinator đang nhận writes giảm rate tương ứng một cách tuyệt đối. Cần **bounded concurrency** và/hoặc rate limiting:

~~~java
Flux<Statement<?>> writes = ...;

// Tối đa 8 subscription CQL write đồng thời
// trong operator này (không phải 8 writes/giây).
Flux<Integer> completions = writes.flatMap(
    statement ->
        Flux.from(session.executeReactive(statement))
            .thenReturn(1),
    8
);
~~~

`flatMap(..., 8)` giới hạn số publisher con active ở operator ấy; tổng service còn có thể chạy **nhiều operators/jobs/instances** nên phải kiểm tổng số in-flight và cluster capacity. Giá trị `8` chỉ dành cho minh họa lab, không phải recommendation chung.

## 13. Reactive write không phát rows: thế nào mới là hoàn tất?

### 13.1. INSERT thường tạo publisher không có row item

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Mono<Void> writeCompleted =
    Flux.from(session.executeReactive(insertStatement))
        .then();
~~~

`Mono<Void>` ở trên chỉ hoàn tất **khi reactive source complete** (hoặc error). **Phải subscribe** hoặc trả Mono cho framework; chỉ tạo object `writeCompleted` chưa làm CQL chạy.

Nếu có completion thành công, client đã nhận tín hiệu hoàn tất theo driver/CL. Với logged write, đó **không** là bảo đảm compaction/repair đã hoàn tất. Nếu subscription bị hủy trước completion, trạng thái ghi có thể không chắc chắn.

### 13.2. Sai lầm `next()` và count

~~~java
// Không nên dùng số lượng emitted rows để đo số INSERTs:
Flux.from(session.executeReactive(insertStatement))
    .count();
// Một INSERT thông thường phát 0 data rows => count=0,
// dù write có thể thành công.
~~~

Cần đếm **statement completions**, không đếm rows. Ví dụ (chỉ nếu mỗi statement có idempotency và error policy riêng):

~~~java
Flux<Statement<?>> statements = ...;

Mono<Long> completedWrites = statements
    .flatMap(
        s -> Flux.from(session.executeReactive(s))
            .thenReturn(1L),
        8
    )
    .reduce(0L, Long::sum);
~~~

Trong trường hợp lỗi, chain có thể ngừng sớm và những inner writes đang in-flight vẫn có thể tiếp tục phía Cassandra. Đừng nói “flatMap đã cancel phần còn lại ⇒ mọi write chưa lưu”. Quản lý **write IDs/outcomes** riêng cho từng phần tử.

### 13.3. Cancellation trong một flow nhiều mutations

~~~text
Publisher<Event> ---> flatMap(write, concurrency=8) ---> downstream
    |                            |
event 1..8                8 writes đã subscribe/gửi
    |
Downstream cancel
    |
event 9..N chưa subscribe: có thể được tránh
event 1..8 đã gửi:       outcome có thể không chắc chắn
~~~

Thiết kế bulk write cần manifest theo event IDs, ack từng record, error queue, backpressure và recovery. **Không** chỉ dùng tổng `onComplete` của stream làm bằng chứng tất cả events được ghi khi stream bị hủy/timeout giữa chừng.

### 13.4. Reactor `doFinally` giúp ghi lý do dừng

~~~java
Mono<Void> operation =
    Flux.from(session.executeReactive(insertStatement))
        .doFinally(signal ->
            System.out.println("client terminal signal=" + signal))
        .then();
~~~

`doFinally` có thể nhận `CANCEL`, `ON_ERROR` hoặc `ON_COMPLETE` tùy upstream. Các tín hiệu này nói về **lifecycle stream phía client**, không là transaction status. Đừng thống kê `CANCEL` như `WRITE_FAILURE_CONFIRMED`.

## 14. Timeout của Reactor, driver, server và HTTP — bốn đồng hồ

~~~text
HTTP gateway timeout
       |
Application workflow deadline
       |
Reactor timeout(Duration...)
       |
Driver basic.request.timeout / setTimeout(...)
       |
Cassandra server-side read/write timeouts
       |
Actual coordinator/replica work and storage lifecycle
~~~

Các đồng hồ có thể kết thúc theo **thứ tự khác nhau**. Cái nào kết thúc trước quyết định **lỗi phía client thấy**, không quyết định chắc chắn trạng thái cuối của mutation ở server.

| Timeout/cancel | Signal thường thấy | Điều không chứng minh |
|---|---|---|
| Reactor `timeout` | `TimeoutException` từ Reactor, upstream bị cancel | Cassandra dừng CQL |
| `CompletableFuture.orTimeout` | JDK `TimeoutException` trên Future | Driver/server đã thu hồi mutation |
| Driver `basic.request.timeout` | `DriverTimeoutException` | Không replica nào đã ghi |
| Cassandra server `read_request_timeout_in_ms` | `ReadTimeoutException` qua coordinator | Client có quyền “làm lại mọi write” |
| Cassandra server `write_request_timeout_in_ms` | `WriteTimeoutException` qua coordinator | Write chưa được áp dụng |
| HTTP disconnect | Hủy HTTP response pipeline | Mọi downstream IO/CQL đều ngừng |

**Server-side timeouts** còn phụ thuộc phiên bản Cassandra, loại thao tác (read, write, range, CAS, counter, truncate) và các settings của cluster; không có một đồng hồ universal cho toàn bộ storage work.

### 14.1. Reactor timeout trên một SELECT

~~~java
import reactor.core.publisher.Flux;
import java.time.Duration;

Flux<ReactiveRow> stream =
    Flux.from(session.executeReactive(readStatement))
        .timeout(Duration.ofSeconds(2));
~~~

Với Reactor `Flux.timeout(Duration)`, timer có thể được làm mới theo mỗi tín hiệu item; **nó không mặc định là deadline tuyệt đối 2 giây cho toàn bộ 100 trang**. Một stream phát row mỗi 1 giây vẫn có thể chạy dài. Khi cần hard end-to-end deadline, phải dùng **request-scoped deadline tuyệt đối** hoặc timeout bao toàn bộ completion thay vì chỉ đo khoảng cách giữa các items.

### 14.2. Deadline end-to-end và remaining budget

Giả sử SLO API là 1500 ms:

~~~text
T0: HTTP request bắt đầu
T1: validation + auth mất 100ms
T2: Cassandra query nhận còn 1400ms
T3: first-page mất 700ms
T4: user cancel hoặc deadline còn 700ms
T5: page fetch kế tiếp chỉ được bắt đầu nếu còn budget
~~~

Đừng tạo 5 requests tuần tự, mỗi request timeout 2 giây, rồi công bố API có timeout 2 giây. Trong service:

- Giữ một deadline monotonic (ví dụ `System.nanoTime`) để tính remaining budget.
- Trước mỗi bước/fetch page, kiểm cancelled/deadline.
- Đặt `Statement.setTimeout` trong giới hạn còn lại khi phù hợp.
- Dừng work chưa bắt đầu và trả error/fallback được phép.
- Với writes đã phát, giữ outcome unknown để reconcile.

### 14.3. Hủy không làm RetryPolicy biến mất hoàn toàn

Nếu Driver đã bắt đầu một logical request, có thể có **retry do DefaultRetryPolicy** hoặc speculative executions tùy timeout, idempotence và profile. Khi app-level timeout/cancel xảy ra, một số attempts có thể **đã được gửi**. Không suy “cancel signal gửi trước 2 giây” nghĩa là không có retry nào đã chạy trên cluster.

## 15. Throttler queue, backpressure và ranh giới cancellation

### 15.1. Request có thể timeout khi chưa được gửi

Java Driver có `advanced.throttler` (pass-through mặc định, cũng có concurrency/rate limiting). Khi yêu cầu quá nhiều, request có thể **đợi trong queue** trước khi coordinator được chọn/gửi:

~~~text
session.executeAsync()
       |
  driver throttler queue (optional)
       |
   wait capacity
       |
   acquire pool/stream id
       |
   send to Cassandra
~~~

Theo [Request throttling](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/throttling/), `basic.request.timeout` **bao gồm cả thời gian chờ throttler queue**. Request có thể timeout **trước khi network write xảy ra**. Điều đó khác hủy sau khi đã gửi, nhưng muốn tuyên bố “chưa gửi” phải có telemetry/contract đáng tin của bản driver đang chạy.

### 15.2. Mẫu config có giới hạn

~~~hocon
datastax-java-driver {
  basic.request.timeout = 2 seconds

  advanced.throttler {
    class = ConcurrencyLimitingRequestThrottler
    max-concurrent-requests = 128
    max-queue-size = 512
  }
}
~~~

Các số **128/512 là ví dụ**, cần hiệu chỉnh theo QPS, p99, nodes, connections và hệ thống. Driver throttler giúp giảm burst, **không thay** limit tổng ở HTTP/reactive operator hay rate limit upstream.

### 15.3. Hủy request đang queued có được loại ngay khỏi queue?

Không nên trả lời vô điều kiện cho tất cả driver 4.x: implementation và version ảnh hưởng cancellation propagation. [Changelog Apache Java Driver 4.19](https://github.com/apache/cassandra-java-driver/blob/trunk/changelog/README.md) có mục **JAVA-3149 — Async Query Cancellation Not Propagated To RequestThrottler** được sửa trong dòng 4.19. Vì vậy:

- Kiểm **artifact/version** của Java Driver đang chạy.
- Thử cancellation với throttler enabled trong staging và đo `throttling.queue-size`, `throttling.errors`, cancelled futures và actual sends.
- Không tự khẳng định mọi cancelled queued request trong 4.17 đều bị loại tức thì.
- Khi cần chắc chắn **không tạo request**, tránh gọi `executeAsync`/subscribe từ đầu nếu đã có cancellation flag/deadline.

### 15.4. RequestThrottlingException

Nếu queue đầy, driver có thể ném `RequestThrottlingException`. Đây là **admission overload phía client**, không phải bằng chứng Cassandra đã nhận request. Không loop retry tức thời; áp backoff/rate control hoặc HTTP 429/503 theo policy dịch vụ. Kết quả cần phân loại riêng với `DriverTimeoutException` và server `OverloadedException`.

## 16. Retry, speculative execution và những công việc “thừa” đã gửi

### 16.1. Một logical request có thể có nhiều executions

~~~text
Java logical SELECT
       |
  Coordinator A
       |
  A phản hồi chậm
       |
  Speculative execution -> coordinator B
       |
  B phản hồi trước
       |
  Driver trả kết quả từ B
       |
  A được "cancel" phía client
       |
  A vẫn có thể đang đọc dữ liệu/chuẩn bị response
~~~

Speculative execution **khác retry**: driver có thể gửi request thứ hai **trước khi** request đầu thất bại. Tài liệu [Speculative execution](https://apache.github.io/cassandra-java-driver/4.18.1/core/speculative_execution/) mô tả việc hủy execution thua cuộc chỉ là **không dùng response tới trễ**, không phải dừng node A. Điều này góp phần làm `pool.orphaned-streams` tăng.

### 16.2. Idempotence là điều kiện an toàn của speculative execution

Driver 4.x mặc định **không bật** speculative executions; khi bật, chỉ áp dụng với statement được xem là **idempotent**. Không đặt toàn bộ writes thành idempotent chỉ để giảm tail latency:

| CQL/action | Có thể replay an toàn? | Rủi ro nếu hai attempts cùng chạy |
|---|---|---|
| Point SELECT thuần | Thường có | Tăng CPU/read I/O, nhưng không side effect CQL |
| UPSERT cùng PK, values, timestamp ổn định | Có điều kiện | Xung đột với writes mới hơn; TTL/timestamp thay đổi |
| COUNTER increment | **Không** | Double increment |
| LIST append/prepend | **Không** | Duplicate elements |
| LWT `IF NOT EXISTS` | Phải xem business outcome | Retry có thể trả `[applied]=false` dù lần đầu áp dụng |
| Ghi row rồi gửi email | Toàn workflow không tự idempotent | Duplicate notification |

Ngay cả với SELECT an toàn về dữ liệu, bật speculation khiến cluster phải thực thi **nhiều request vật lý**; nếu disk/GC đã nghẽn, speculation có thể làm nặng hơn.

### 16.3. Cancel trước khi driver retry xong

Nếu request logic đang retry hoặc speculate, cancellation ở application có thể xảy ra khi:

- Attempt A đã gửi, response chưa về.
- Attempt B được lên lịch hoặc đã gửi.
- Một attempt đã thắng nhưng Future downstream chưa xử lý.

Đừng giả định cancel một stage của app có thể “thu hồi” mọi attempts đồng thời ở phía server. Hạn chế số attempts với policy và deadline đúng, giám sát retry/speculation metrics; nếu cần chắc chắn, phải dùng application-side admission control **trước khi** gửi.

### 16.4. Không dùng default retry + reactive retry không giới hạn

~~~java
// NGUY HIỂM cho mutation không idempotent:
Flux.defer(() -> Flux.from(session.executeReactive(writeStatement)))
    .retry();  // retry vô hạn nếu lỗi, có thể replay mutation
~~~

Reactive `retry()` tạo một **subscription mới** sau error. Khi dùng `Flux.defer`, mỗi subscribe tạo một request CQL mới; trong khi driver có thể **đã retry nội bộ** trong mỗi request. Số physical attempts có thể tăng rất nhanh. Dùng bounded retries, backoff/jitter, time budget và phân loại lỗi; với writes unknown outcome, reconcile trước khi retry.

## 17. Observability: metric client và server phải nhìn cùng lúc

### 17.1. Driver metrics liên quan cancellation

Tùy driver version và metrics backend, có thể bật:

~~~hocon
datastax-java-driver {
  advanced.metrics {
    session.enabled = [
      cql-requests,
      cql-client-timeouts,
      throttling.delay,
      throttling.queue-size,
      throttling.errors
    ]

    node.enabled = [
      cql-messages,
      pool.open-connections,
      pool.in-flight,
      pool.available-streams,
      pool.orphaned-streams,
      retries.total,
      speculative-executions
    ]
  }
}
~~~

Đây là **tên options trong HOCON**, không phải tên series Prometheus được bảo đảm trong mọi exporter. Metrics có thể tắt mặc định và cần Micrometer/Dropwizard/registry phù hợp; kiểm endpoint scrape thực trước khi vẽ dashboard. Đối chiếu [Java Driver metrics](https://apache.github.io/cassandra-java-driver/4.18.1/core/metrics/) và reference config của binary đang chạy.

### 17.2. Đọc đúng ý nghĩa

| Metric/trace | Cấp | Trả lời câu hỏi |
|---|---|---|
| Application `cancelled_http_requests` | Service | Bao nhiêu caller không còn quan tâm? |
| Application `cancelled_future_count` | Service | Bao nhiêu future chuyển trạng thái cancelled? |
| Application `rows_delivered`/`pages_requested` | Query family | Đã trả bao nhiêu rows, đã gọi bao nhiêu page requests? |
| `cql-requests` | Driver session | Logical CQL requests/latency |
| `cql-messages` | Driver node | Network messages/attempts tới coordinator |
| `pool.in-flight` | Driver node | Messages còn chờ response |
| `pool.available-streams` | Driver node | Stream IDs có thể sử dụng |
| `pool.orphaned-streams` | Driver node | Stream IDs chưa thể giải phóng sau cancellation/orphan |
| `speculative-executions` | Driver node | Extra attempts vì speculative policy |
| `retries.total` | Driver node | Retry do policy ghi nhận |
| `cql-client-timeouts` | Driver session | Deadlines của driver hết |
| `throttling.queue-size` | Driver session | Requests trong throttler queue |
| Cassandra `ClientRequest.Read/Write.Latency` | Server | Coordinator xử lý requests thực tế |
| Disk/GC/compaction/replica metrics | Server | Nút thắt vật lý kéo dài sau client cancel |

**Không dùng một metric `cancelled_future_count` để suy số request server đã ngừng.** Tương tự, `cql-requests` và `cql-messages` không cùng denominator khi có pages/retries/speculation, cần chuẩn hóa cùng cửa sổ thời gian và scope.

### 17.3. Các tỷ lệ hữu ích

Định nghĩa trong một cửa sổ cùng service/query family:

\[
\text{cancelRatio} =
\frac{\text{logical requests bị client hủy}}{\text{logical requests bắt đầu}},
\qquad
\text{extraAttemptRatio} \approx
\frac{\text{node messages}}{\text{logical requests}}.
\]

Đây là metrics **tham khảo**, không phải đẳng thức để suy số rows/replica I/O; vì mỗi trang async có thể là một logical request và metrics scopes thay đổi. Thêm các chỉ số:

- **Pages requested after client disconnect:** lý tưởng tiệm cận 0, nhưng hiểu race/in-flight.
- **Cancel-to-response lag:** nếu có tracing, bao lâu sau cancel một response muộn mới về.
- **Orphaned streams/available streams:** phát hiện pool pressure do abort/speculation.
- **Client vs server QPS:** cancellation chỉ giảm HTTP completed responses nhưng CQL QPS vẫn cao là tín hiệu gửi quá nhiều trước lúc hủy.
- **Unknown write outcomes:** số operations cần reconciliation.

### 17.4. Server-side commands read-only

~~~bash
nodetool status
nodetool tpstats
nodetool compactionstats
nodetool gcstats
nodetool tablestats cancel_lab.events_by_day
~~~

`nodetool status` không trả lời liệu một **request cụ thể** đã commit hay chưa. Nó giúp kiểm ring/replica availability. `compactionstats` là backlog storage, không phải “số truy vấn chưa bị hủy”. Muốn biết outcome nghiệp vụ, đối chiếu PK/version/event log.

### 17.5. Trace và log an toàn

~~~text
request_family=events.listByDay
mode=reactive
profile=history_read
client_cancelled=true
cancel_reason=http_disconnect
rows_delivered=2
pages_requested=1
cql_outcome=UNKNOWN_NOT_ACKNOWLEDGED
server_work_stopped=NOT_KNOWN
~~~

**Không** đưa raw CQL bind values, tenant IDs, email, customer names, payment IDs vào metric labels. Nếu cần correlation, dùng tracing ID hoặc hashed/tokenized operation ID theo chính sách bảo mật; tránh high-cardinality dimensions trong Prometheus.

### 17.6. Canary đo hiệu quả giảm công việc thừa

~~~text
Before:
  100 HTTP requests cancel ở 1 giây
  500 CQL page requests được phát

After:
  100 HTTP requests cancel ở 1 giây
  150 CQL page requests được phát

Kết luận có thể bảo vệ:
  Ít trang được request hơn sau thay đổi.

Không kết luận:
  "Cassandra đã dừng 350 truy vấn đang chạy".
~~~

Tiếp tục theo dõi Cassandra CPU/disk/latency và pool orphaned streams để biết thay đổi có thực sự giảm **server load** hay chỉ giảm network pages ở những truy vấn nhỏ.

## 18. Lab CQL: tạo dữ liệu để thử dừng việc đọc

**Mục tiêu:** Có 5 rows trên một partition để dùng page-size 2 và thử dừng sau 2 rows. Dữ liệu giả lập, không thực hiện fault injection hay làm node chậm. Các thí nghiệm write cancellation chỉ minh họa **race**, không được coi là deterministic oracle.

### 18.1. Môi trường

- Cassandra 4.1/5.0 trên **một node lab**, `cqlsh` hoạt động.
- Java 17 và Java Driver 4.x, Reactor 3.x nếu thử reactive.
- Port `9042` và local DC đúng, ví dụ `datacenter1`; kiểm `nodetool status`.
- Keyspace `cancel_lab` là độc lập; không dùng bảng sản xuất.

### 18.2. Tạo keyspace và bảng

~~~sql
CREATE KEYSPACE IF NOT EXISTS cancel_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS cancel_lab.events_by_day (
  tenant_id text,
  day date,
  seq int,
  event_id uuid,
  status text,
  PRIMARY KEY ((tenant_id, day), seq)
) WITH CLUSTERING ORDER BY (seq ASC);

CREATE TABLE IF NOT EXISTS cancel_lab.operations_by_id (
  tenant_id text,
  operation_id uuid,
  status text,
  PRIMARY KEY ((tenant_id), operation_id)
);
~~~

`SimpleStrategy`/RF1 chỉ dùng trong lab. Với production multi-DC, dùng `NetworkTopologyStrategy`, RF và CL theo hợp đồng dữ liệu. Bài này kiểm cancellation, không benchmark consistency.

### 18.3. Nạp 5 rows ổn định

~~~sql
CONSISTENCY ONE;

INSERT INTO cancel_lab.events_by_day
  (tenant_id, day, seq, event_id, status)
VALUES ('tenant-a', '2026-11-21', 1,
        11111111-1111-1111-1111-111111111111, 'NEW');

INSERT INTO cancel_lab.events_by_day
  (tenant_id, day, seq, event_id, status)
VALUES ('tenant-a', '2026-11-21', 2,
        22222222-2222-2222-2222-222222222222, 'PAID');

INSERT INTO cancel_lab.events_by_day
  (tenant_id, day, seq, event_id, status)
VALUES ('tenant-a', '2026-11-21', 3,
        33333333-3333-3333-3333-333333333333, 'PACKED');

INSERT INTO cancel_lab.events_by_day
  (tenant_id, day, seq, event_id, status)
VALUES ('tenant-a', '2026-11-21', 4,
        44444444-4444-4444-4444-444444444444, 'SHIPPED');

INSERT INTO cancel_lab.events_by_day
  (tenant_id, day, seq, event_id, status)
VALUES ('tenant-a', '2026-11-21', 5,
        55555555-5555-5555-5555-555555555555, 'DELIVERED');
~~~

### 18.4. Baseline bằng SELECT

~~~sql
SELECT seq, event_id, status
FROM cancel_lab.events_by_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21';
~~~

Kỳ vọng 5 rows theo `seq ASC`. Nếu đã từng chạy lab và có thêm dữ liệu ở đúng partition, hãy dùng **keyspace/partition lab mới có kiểm soát** hoặc đối chiếu state trước; không dùng `TRUNCATE` trên dữ liệu chưa được phê duyệt.

## 19. Lab Java Async: kiểm soát page fetch và thử cancel race

### 19.1. Dependency/API

Với Java Driver 4.17, dependency Maven minh họa:

~~~xml
<dependency>
  <groupId>com.datastax.oss</groupId>
  <artifactId>java-driver-core</artifactId>
  <version>4.17.0</version>
</dependency>
~~~

Từ 4.18, Java Driver được Apache Software Foundation duy trì; hãy đối chiếu Maven coordinates/BOM của phiên bản đang dùng. Bài chỉ cung cấp code mẫu, **không tạo thêm file dự án, không chạy Maven/Gradle** trong STEP 4.

### 19.2. Chương trình đầy đủ

~~~java
package example;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public final class CancelAsyncLab {
    private CancelAsyncLab() {}

    public static void main(String[] args) {
        // Thay datacenter1 bằng tên DC THẬT trong nodetool status.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            PreparedStatement p = session.prepare(
                "SELECT seq, event_id, status " +
                "FROM cancel_lab.events_by_day " +
                "WHERE tenant_id = ? AND day = ?");

            BoundStatement read = p.bind(
                    "tenant-a", LocalDate.parse("2026-11-21"))
                .setPageSize(2)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setIdempotent(true);

            // Bước A: hoàn tất bất đồng bộ 3 rows, dừng trước page sau.
            CompletionStage<Integer> firstThree =
                session.executeAsync(read).thenCompose(
                    page -> countAtMost(page, 3, 0));

            int observed = firstThree.toCompletableFuture().join();
            System.out.println("rows consumed=" + observed);
            if (observed != 3) {
                throw new IllegalStateException("Expected 3 rows");
            }

            // Bước B: hủy một request read độc lập.
            // SELECT nhỏ có thể complete trước cancel -> nondeterministic.
            CompletableFuture<AsyncResultSet> future =
                session.executeAsync(read).toCompletableFuture();

            boolean cancelled = future.cancel(false);
            System.out.println("cancel returned=" + cancelled);
            System.out.println("isCancelled=" + future.isCancelled());

            // Không suy ra Cassandra đã dừng work.
            // Không gọi join() trên future đã cancel.
            // Không đóng session trong callback I/O.
        }
    }

    private static CompletionStage<Integer> countAtMost(
            AsyncResultSet page, int maxRows, int previouslySeen) {

        int seen = previouslySeen;
        for (Row row : page.currentPage()) {
            if (seen >= maxRows) {
                return CompletableFuture.completedFuture(seen);
            }
            System.out.println("seq=" + row.getInt("seq"));
            seen++;
        }

        if (seen >= maxRows || !page.hasMorePages()) {
            return CompletableFuture.completedFuture(seen);
        }

        final int count = seen;
        return page.fetchNextPage()
            .thenCompose(next -> countAtMost(next, maxRows, count));
    }
}
~~~

### 19.3. Kết quả dự kiến

~~~text
seq=1
seq=2
seq=3
rows consumed=3
cancel returned=true/false
isCancelled=true/false
~~~

Hai dòng cuối **không có một giá trị cố định** vì query có thể đã complete trước khi `cancel`. Đây chính là race cần học, **không phải test bị flaky cần sửa bằng cách ép Cassandra chậm**. Bài lab đạt khi người học giải thích được:

- `page-size=2` nhưng vẫn có thể nhận 3 rows sau khi gọi `fetchNextPage` đúng một lần.
- Hàm không gọi fetch nữa sau khi đạt `maxRows=3`; các rows đã đến trong trang hiện tại không bị rollback.
- `cancel(false)` thành công/chưa thành công là client Future state, không chứng minh coordinator dừng.
- `session.executeAsync(read)` đã bắt đầu request **trước** khi lấy `CompletableFuture` để cancel.

### 19.4. Thêm cancellation flag trong ứng dụng thật

Trong một REST service, thay số rows cố định bằng `AtomicBoolean cancelled` và điều kiện deadline trước mỗi `fetchNextPage()` như mục 9. Không để client disconnect nhưng loop vẫn tự động đọc toàn bộ partition cho “đủ dữ liệu”; đó là nguồn gây nhiều QPS dư thừa.

**Về recursion:** Với số trang rất lớn, cân nhắc loop/trampoline hoặc stream processing có giới hạn để tránh tạo nhiều dependent stages/callbacks. Đừng gom toàn bộ `AsyncResultSet` vào `List<Row>` nếu API chỉ cần vài rows.

## 20. Lab Java Reactor: cold publisher, `take(2)` và `dispose()`

### 20.1. Phụ thuộc Reactor

Ngoài `java-driver-core` 4.x và Reactive Streams API, ví dụ này dùng Reactor Core 3.x. Driver có dependency vào Reactive Streams API, nhưng **Reactor không phải library bắt buộc của driver**; cần khai báo Reactor dependency trong project của người học nếu chưa có.

### 20.2. Chương trình đầy đủ

~~~java
package example;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.dse.driver.api.core.cql.reactive.ReactiveResultSet;
import com.datastax.dse.driver.api.core.cql.reactive.ReactiveRow;
import java.net.InetSocketAddress;
import java.time.Duration;
import java.time.LocalDate;
import java.util.List;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;

public final class CancelReactiveLab {
    private CancelReactiveLab() {}

    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            PreparedStatement prepared = session.prepare(
                "SELECT seq, event_id, status " +
                "FROM cancel_lab.events_by_day " +
                "WHERE tenant_id = ? AND day = ?");

            BoundStatement read = prepared.bind(
                    "tenant-a", LocalDate.parse("2026-11-21"))
                .setPageSize(2)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setIdempotent(true);

            // Tạo publisher, nhưng CHƯA query.
            ReactiveResultSet cold =
                session.executeReactive(read);

            // subscribe qua block() chỉ để minh họa trong main lab.
            List<ReactiveRow> rows = Flux.from(cold)
                .doOnCancel(() ->
                    System.out.println("upstream CANCEL"))
                .take(2)
                .collectList()
                .block(Duration.ofSeconds(5));

            System.out.println("rows delivered=" + rows.size());
            for (ReactiveRow row : rows) {
                System.out.println("seq=" + row.getInt("seq"));
            }

            // Publisher MỚI cho thao tác stop bằng Disposable.
            Disposable subscription =
                Flux.from(session.executeReactive(read))
                    .doOnCancel(() ->
                        System.out.println("explicit CANCEL"))
                    .subscribe(
                        row -> System.out.println(
                            "observed seq=" + row.getInt("seq")),
                        error -> System.err.println(
                            "error=" +
                            error.getClass().getSimpleName()));

            // RACE: có thể hủy trước/giữa/sau response.
            subscription.dispose();

            // Đừng khẳng định Cassandra đã kill SELECT.
        }
    }
}
~~~

### 20.3. Kỳ vọng và những điều không nên assert

Kỳ vọng nhánh `take(2)` trên partition lab sạch:

~~~text
upstream CANCEL
rows delivered=2
seq=1
seq=2
~~~

Tín hiệu `explicit CANCEL` ở nhánh `dispose()` **không luôn xuất hiện**: stream có thể đã complete đồng bộ/trước khi `dispose` được gọi. Không cố gắng dùng `Thread.sleep` trên I/O callback hoặc gây overload server để tạo một “output đẹp”.

### 20.4. Vì sao không subscribe lại cùng publisher?

`cold` là single-subscription-only. Nếu code gọi tiếp `Flux.from(cold).blockLast()` lần nữa, publisher mặc định có thể trả `IllegalStateException`. Muốn một query mới, gọi `session.executeReactive(read)` mới; muốn dùng lại **cùng dataset đã materialize**, chỉ cache trong client khi size thực sự nhỏ và chấp nhận footprint/correctness.

### 20.5. Trong ứng dụng WebFlux

Controller nên **return** `Flux/Mono` để framework quản lý subscription và HTTP disconnect thay vì tự `subscribe()` rồi bỏ `Disposable`:

~~~java
public Flux<ReactiveRow> findEvents(
        CqlSession session, BoundStatement read) {
    return Flux.defer(
        () -> Flux.from(session.executeReactive(read)));
}
~~~

Nếu HTTP client hủy downstream, Reactor có thể propagate `cancel` tới publisher Cassandra. Điều này giúp dừng demand/paging, **không** bảo đảm dừng query đã gửi. Code ngoài framework phải bảo đảm return stage/Flux được **subscribe đúng một lần** và không bị chạy nền không ai sở hữu.

## 21. Lab thuần JDK — deterministic: hủy Future, task độc lập vẫn chạy

Lab Cassandra thực có race nên `cancel` đôi khi trả true, đôi khi false. Nếu muốn **chứng minh khái niệm** mà không gây tải hay lỗi cluster, hãy dùng hai threads/latches dưới đây. Đây chỉ là **mô hình của client và server tách biệt**, không phải implementation/native protocol của Cassandra.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class CancellationIsNotRollback {
    public static void main(String[] args) throws Exception {
        ExecutorService simulatedServer =
            Executors.newSingleThreadExecutor();

        CountDownLatch accepted = new CountDownLatch(1);
        CountDownLatch resumeWork = new CountDownLatch(1);
        AtomicBoolean mutationApplied = new AtomicBoolean(false);
        CompletableFuture<String> response = new CompletableFuture<>();

        try {
            simulatedServer.execute(() -> {
                accepted.countDown(); // "server nhận request"
                try {
                    resumeWork.await(); // chỉ lab, không phải driver callback
                    mutationApplied.set(true);
                    response.complete("ACK");
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    response.completeExceptionally(interrupted);
                }
            });

            if (!accepted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Simulated server not ready");
            }

            boolean cancelled = response.cancel(true);
            System.out.println("client cancel returned=" + cancelled);

            // Cho phép "server" hoàn tất sau khi client đã cancel.
            resumeWork.countDown();
            simulatedServer.shutdown();

            if (!simulatedServer.awaitTermination(
                    5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Server task still running");
            }

            System.out.println("future cancelled=" +
                response.isCancelled());
            System.out.println("mutation applied=" +
                mutationApplied.get());
        } finally {
            resumeWork.countDown();
            simulatedServer.shutdownNow();
        }
    }
}
~~~

**Kết quả dự kiến:**

~~~text
client cancel returned=true
future cancelled=true
mutation applied=true
~~~

Trong mô hình này, `response.cancel(true)` không interrupt task mô phỏng vì `response` là một `CompletableFuture` riêng, không phải `FutureTask` đang quản lý thread đó. Task vẫn chạy và `response.complete("ACK")` không thể thay trạng thái cancelled. Tương tự về **nguyên lý**, client Future bị hủy không đủ để khẳng định server mutation chưa xảy ra. **Không suy rằng mọi cancelled Cassandra query luôn hoàn tất**; kết quả phụ thuộc timeout, errors và server execution. Lab chỉ chứng minh cancellation không tạo bảo đảm rollback.

## 22. Lab write cancellation: một kết quả không thể đoán trước

### 22.1. Chỉ dùng khóa cố định trong keyspace lab

Giả sử đã tạo `cancel_lab.operations_by_id` ở mục 18. Dùng một operation ID ổn định:

~~~java
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;

UUID operationId = UUID.fromString(
    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");

PreparedStatement insert = session.prepare(
    "INSERT INTO cancel_lab.operations_by_id " +
    "(tenant_id, operation_id, status) VALUES (?, ?, ?)");

BoundStatement write = insert.bind(
        "tenant-a", operationId, "STARTED")
    .setConsistencyLevel(DefaultConsistencyLevel.ONE)
    .setIdempotent(false); // Bảo thủ để minh họa, không auto retry.

CompletableFuture<AsyncResultSet> inFlight =
    session.executeAsync(write).toCompletableFuture();

boolean cancelled = inFlight.cancel(false);
System.out.println("write future cancelled=" + cancelled);

PreparedStatement lookup = session.prepare(
    "SELECT status FROM cancel_lab.operations_by_id " +
    "WHERE tenant_id = ? AND operation_id = ?");

Row observed = session.execute(
    lookup.bind("tenant-a", operationId)
        .setConsistencyLevel(DefaultConsistencyLevel.ONE)).one();

System.out.println(
    "immediate read=" +
    (observed == null ? "NOT_VISIBLE_YET" :
        observed.getString("status")));
~~~

**Không có output cố định.** Cancel có thể thắng/rớt cuộc đua với response; SELECT ngay sau cancel có thể thấy row hoặc không. Trong một lab RF1, tình huống thường hoàn tất rất nhanh. Dù thấy `NOT_VISIBLE_YET`, bạn **không được** kết luận row sẽ không bao giờ xuất hiện. Nếu lab đã chạy trước đó, row có thể đã tồn tại từ lần trước; dùng operation ID khác **được ghi nhận ổn định cho đúng lần thử**, không sinh ngẫu nhiên cho mỗi retry.

### 22.2. Không làm thế nào để “chắc chắn thấy hủy”?

Đừng:

- Khóa network/iptables trên production.
- Cố tình làm đầy disk hoặc làm DOWN replica.
- Thay Cassandra server timeout xuống vài ms để gây lỗi hàng loạt.
- Dùng `TRUNCATE` để xóa dấu vết trạng thái chưa đối soát.
- Retry INSERT liên tục với operation ID mới mỗi lần.

Nếu cần kiểm sâu behavior cancellation, dùng integration test với **proxy/fault injection trong staging được cho phép**, instrumentation driver/server và source-of-truth; không coi test phá server là một phần bắt buộc của bài học cơ bản.

### 22.3. Một cách ghi kết quả đúng trong hệ thống thật

~~~text
operation_id: aaaaaaaa-...
client_cancelled: true
request_maybe_sent: true
write_outcome: UNKNOWN
last_observation: SELECT at T1 (visibility dependent on CL)
next_step: reconcile with business event log + version
retry_allowed: only after idempotency decision
~~~

“Đã cancel” là **thuộc tính của client request**; “đã ghi” là **thuộc tính của dữ liệu và replicas**. Chúng có thể đồng thời đúng.

## 23. Tình huống thực tế: thấy cancellation rồi phải làm gì?

### Ca 1 — Người dùng đóng trang sau khi bấm “Xem lịch sử”

**Tình huống:** WebSocket/HTTP stream đang gửi rows, client disconnect tại row thứ 20/1000.

**Đúng:** Propagate cancel tới stream, ngừng fetch các pages chưa phát, giảm downstream work. Nếu trang đầu chứa 100 rows đã trả về driver, coordinator vẫn có thể đã tính đủ trang ấy.

**Sai:** Báo “Cassandra dừng SELECT ngay tại row thứ 20”, hoặc tiếp tục fetch cả 1000 rows để cập nhật cache không có owner.

### Ca 2 — Dùng `take(1)` với partition rộng, nhưng CPU Cassandra vẫn cao

**Nguyên nhân:** Server đã phải scan tombstones/SSTables hoặc tính trang đầu; `take(1)` là **giới hạn downstream items**, không sửa query shape/partition. Query có thể không có partition key tốt.

**Xử lý:** Dùng `LIMIT` đúng, partition bucketing, index/design theo truy vấn, page-size và metrics server. Đừng chỉ tăng cancellation rate.

### Ca 3 — POST tạo đơn hàng bị hủy vì HTTP client mất mạng

**Nguy cơ:** Mutation đã gửi và được ghi; HTTP caller không nhận ACK, retry tạo đơn khác.

**Xử lý:** Dùng idempotency key và operation ID cố định, lưu outbox/dedup, reconcile trước khi replay; không trả “order not created” chỉ dựa `Future.isCancelled()`.

### Ca 4 — Future cancel trả `false` trong lab

**Giải thích:** Request có thể đã hoàn tất quá nhanh hoặc Future ở terminal state khác trước cancel.

**Xử lý:** Đây là race hợp lệ. Không cố chèn `Thread.sleep` trong Netty callback hay làm Cassandra chậm để ép `true`. Dùng bài thử thuần JDK ở mục 21 khi muốn chứng minh trạng thái Future.

### Ca 5 — Future cancel trả `true` nhưng SELECT thấy row mới

**Giải thích:** Client đã ngừng chờ response, nhưng server đã xử lý mutation trước/sau cancellation.

**Xử lý:** Không gọi đó là bug “Future đã bị hủy mà Cassandra vẫn ghi”. Kiểm operation ID, deadline, write timestamps/CL và reconciliation. Sự kiện này **phù hợp với giới hạn native protocol**.

### Ca 6 — Hủy một `thenApply` cuối pipeline không giảm CQL QPS

**Nguyên nhân:** Hủy child stage **không bắt buộc** hủy upstream `executeAsync`. Root đã gửi CQL.

**Xử lý:** Giữ request ownership/context, propagate stop flag xuống paging, kiểm nơi root Future được giữ và xử lý; tối ưu admission trước khi phát request.

### Ca 7 — Cùng reactive result set subscribe hai lần

**Triệu chứng:** Subscription thứ hai trả `IllegalStateException`.

**Giải thích:** `ReactiveResultSet` mặc định single-subscription-only.

**Xử lý:** Dùng publisher mới cho lần query mới, hoặc share/cache dữ liệu có giới hạn và ý thức data freshness. Không coi lỗi subscription thứ hai là Cassandra unavailable.

### Ca 8 — Reactive write “chạy” nhưng không có dữ liệu

**Nguyên nhân:** Application tạo `ReactiveResultSet` trong `doOnNext` nhưng không subscribe vào nó, hoặc tạo `Mono<Void>` rồi bỏ mà không return/subscribe.

**Xử lý:** Xây pipeline `flatMap`/`then` có terminal subscriber/framework owner. **Cold** đồng nghĩa chưa có effect trước subscribe.

### Ca 9 — `dispose()` làm log `CANCEL` nhưng server vẫn có write metrics

**Giải thích:** Nhiều writes đã được submit trước dispose; cancellation chỉ tránh phần chưa subscribe/nhận.

**Xử lý:** Ghi outcome per-event ID, so `cql-messages`/write latency, duy trì reconciliation. Không tính mọi writes pending là failed rồi reimport ngay.

### Ca 10 — `pool.orphaned-streams` tăng cùng connection churn

**Nguyên nhân khả dĩ:** Canceled/speculative executions nhiều, response tới muộn; stream IDs không reuse ngay.

**Xử lý:** Giảm requests thừa từ đầu, xem speculation threshold, page prefetch và timeout quá thấp; đo `pool.available-streams`, `pool.in-flight`, open connections, Netty/OS sockets. Không đóng session cho mỗi user để “xóa orphan”.

### Ca 11 — Reactive timeout 2s nhưng HTTP trả sau 30s

**Nguyên nhân:** `Flux.timeout(Duration.ofSeconds(2))` đo khoảng cách giữa emitted items; stream có row mới đều đặn, tổng thời gian không bị giới hạn.

**Xử lý:** Thực hiện **absolute end-to-end deadline** tại HTTP/service, kiểm remaining time trước page/DB calls, không dùng idle timeout làm SLA tổng.

### Ca 12 — Timeout driver khi request còn trong throttler queue

**Tình huống:** `throttling.queue-size` lớn, request hết `basic.request.timeout` trước khi đến socket.

**Xử lý:** Admission limit/rate control, backpressure và capacity. Không kết luận server đã timeout/ghi sai; nhưng với ứng dụng quan sát ngoài, vẫn cần phân loại bằng telemetry và version trước khi tuyên bố chắc chắn chưa gửi.

### Ca 13 — Async cancellation không giải phóng throttler capacity ở một bản 4.x

**Khả năng:** Behavior/version issue; changelog 4.19 sửa `JAVA-3149` về cancellation propagation tới request throttler.

**Xử lý:** Xác minh library version, chạy regression test dưới throttler load, so queue/in-flight trước/sau. Không áp một kết luận cho mọi 4.x mà không test.

### Ca 14 — Speculative SELECT thắng ở node B, node A còn đọc SSTables

**Giải thích:** “Cancel losing execution” phía driver chỉ bỏ response của node A; không có server-side kill cho ordinary CQL.

**Xử lý:** Với workload CPU/IO nặng, cân nhắc giảm speculation, sửa hot partition/GC/disk; giữ idempotence đúng và giám sát orphaned streams.

### Ca 15 — HTTP 504 nhưng Cassandra row đã tồn tại

**Nguyên nhân:** Gateway/application deadline kết thúc trước khi coordinator ACK hoặc response qua mạng trở lại.

**Xử lý:** Response contract nên trả operation ID, trạng thái retry-safe/unknown; client truy vấn status endpoint hoặc poll theo event ID. Không cho caller tạo mới operation ID mù khi gặp 504.

### Ca 16 — Reactive `retryWhen` phát thêm INSERTs sau lỗi

**Nguyên nhân:** Mỗi resubscription qua `Flux.defer` gọi `executeReactive` lần nữa; driver lại có internal retry/speculation.

**Xử lý:** Bounded retry theo lớp lỗi/idempotency, global rate limit và deadline. Với mutation không idempotent, không bật retry auto; reconcile unknown outcomes.

### Ca 17 — Ngắt một ứng dụng batch giữa 1000 writes

**Nguy cơ:** Có một số event chưa subscribe, một số đã gửi, một số đã ACK; kết thúc `Flux` không cho phép phân loại mọi row bằng một flag chung.

**Xử lý:** Manifest per-event, confirmed/failed/unknown, source offsets, writer concurrency ≤ capacity. Khi resume chỉ replay những operations theo chính sách idempotency và checkpoints được đối chiếu.

### Ca 18 — DSE continuous paging có API `cancel()` riêng

**Phân biệt:** Một số API **ContinuousAsyncResultSet** của DataStax Enterprise có `cancel()` và semantics dành riêng cho *continuous paging*. Đây **không** phải bằng chứng rằng Cassandra OSS `AsyncResultSet`/native CQL thường có phương thức `kill query` tương đương. Khi đọc tài liệu DSE, không áp chéo API vào Cassandra OSS 4.x/5.x. [ContinuousAsyncResultSet Javadoc](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/dse/driver/api/core/cql/continuous/ContinuousAsyncResultSet.html).

### Ca 19 — Service shutdown khi còn async CQL

**Nguy cơ:** Một shutdown hook gọi `session.close()` quá sớm sau khi hủy HTTP response, làm lỗi hàng trăm requests khác; việc đóng connections cũng không bảo đảm server rollback những writes đã gửi.

**Xử lý:** Bắt đầu **graceful shutdown**: từ chối requests mới, ngừng phát pages/jobs mới, chờ bounded in-flight deadline, ghi unknown outcomes, đóng session theo lifecycle của ứng dụng và báo cáo những operations cần reconciliation.

### Ca 20 — Đội phát triển đếm cancel như write failure

**Sai KPI:** `cancelled_futures = failed_writes` dẫn đến báo động sai, tự retry và viết dữ liệu trùng.

**Đúng KPI:** Phân loại `CANCELLED_CLIENT`, `ACKNOWLEDGED_SUCCESS`, `SERVER_ERROR`, `UNKNOWN_WRITE_OUTCOME` và `RECONCILED_FINAL_STATE`. Một operation có thể **client-cancelled nhưng server-success**.

## 24. Runbook: hủy request nhưng vẫn bảo vệ tính đúng dữ liệu

### 24.1. Trước khi triển khai

Ghi rõ cho từng **query family**:

| Câu hỏi | Ví dụ cần trả lời |
|---|---|
| Request là read hay write? | `events.listByDay` là SELECT; `orders.create` là INSERT |
| Đã có partition key tốt? | `(tenant_id,day)` và clustering range |
| CL và RF theo DC? | RF=3, `LOCAL_QUORUM` cho orders quan trọng |
| Deadline HTTP/service/driver? | 1500/1300/1000 ms, phù hợp retry/paging |
| Có thể hủy ở tầng nào? | Trước execute, trước fetchNextPage, reactive subscription |
| Có cần idempotency key? | Write với POST retry/unknown outcome |
| Có thể cache/fallback read? | Chỉ với API cho phép dữ liệu stale |
| Chỉ số để xác nhận giảm tải? | Pages requested, server QPS, orphaned streams, p99 |
| Library version? | Java Driver 4.17/4.19, Reactor, Netty config |

**Không** dùng một HTTP cancellation handler chung để gọi `session.close()`. Session là shared resource. Phân biệt read-only query có thể **ngừng fetch** với write cần **reconciliation**.

### 24.2. Luồng xử lý khi phát hiện caller không còn đợi

~~~text
                 HTTP/gRPC/job cancellation
                           |
                   Mark request cancelled
                           |
                   CQL đã bắt đầu chưa?
                  /                      \
                NO                       YES
                |                         |
        Không gọi execute         CQL là read hay write?
        hoặc không subscribe        /           \
                                   READ          WRITE
                                     |             |
                              Dừng page demand    Có thể đã gửi?
                              /fetchNextPage      /         \
                                     |          NO*          YES/UNKNOWN
                                     |           |             |
                              Không kill         Drop        Mark UNKNOWN
                              server work      unsent work   + operation ID
                                     |                         |
                                     |                   Reconcile theo
                                     |                   source of truth
                                     \                         /
                                      \                       /
                                        Metrics và guardrails
                                               |
                                        GO/HOLD/STOP

* NO chỉ khi có bằng chứng đáng tin, không suy từ cancel=true.
~~~

### 24.3. Những gì cần log theo timeline

~~~text
T0 request_started_utc
T1 query_family/profile/CL/partition_category
T2 executeAsync_called hoặc reactive_subscribed
T3 page_requested_count / rows_delivered_count
T4 cancel_requested_utc + reason
T5 client terminal signal: CANCEL/ERROR/COMPLETE
T6 request stage outcome: ACK/ERROR/UNKNOWN
T7 business reconciliation result (nếu write)
T8 metrics window và rollback decision
~~~

**Không** cố ghi một timestamp `SERVER_STOPPED_AT_T4` nếu server không cung cấp bằng chứng. Với Java async/HTTP, đồng hồ ở client và server còn có clock skew; đánh giá latency bằng monotonic deltas và timestamps UTC cho correlation.

### 24.4. GO/HOLD/STOP

| Quan sát | Hành động | Lý do |
|---|---|---|
| Dừng page fetch sớm; server QPS và p99 giảm | **GO** mở rộng canary | Giảm được work chưa gửi mà không đổi dữ liệu |
| Reactive `take` trả đúng N rows nhưng orphaned streams tăng mạnh | **HOLD** | Có thể phát nhiều in-flight requests trước khi cancel |
| Cancellation ratio tăng, CQL messages không giảm | **HOLD** | Cancel quá muộn hoặc upstream stage không được propagate |
| Write bị cancel, không có ACK, chưa reconcile | **STOP blind retry** | Outcome unknown |
| Dùng `completeOnTimeout(fakeSuccess)` cho write | **STOP** | Che outcome sai nghiệp vụ |
| Driver throttler queue tăng sau cancel ở version cũ | **HOLD** | Kiểm version-specific propagation |
| Speculation/retries làm node CPU/disk xấu | **HOLD/ROLLBACK** | Extra physical attempts |
| Node DOWN, thiếu CL hoặc data correctness sai | **STOP/ESCALATE** | Không thể sửa bằng Future cancellation |
| Canary xác minh pages saved, p99 ổn, write audit đúng | **GO** từng batch | Có evidence và headroom |

Ngưỡng thật phải theo QPS/SLO/baseline và đủ sample; một ngưỡng “orphaned > 10” không phù hợp mọi pool size/driver version.

### 24.5. Sau rollback

Nếu thay đổi dừng paging/timeout đã gây lỗi:

1. Khôi phục config/feature flag theo source-of-truth, xác nhận **effective options** trên JVM.
2. Kiểm requests mới có behavior mong đợi; những in-flight requests trước rollback có thể vẫn đang chạy.
3. Với writes bị cancel hoặc timeout, giữ danh sách UNKNOWN để reconcile; **rollback code không undo Cassandra mutations**.
4. Đo client p99/error, `pool.orphaned-streams`/connections và server latency/GC/disk.
5. Ghi lại nguyên nhân, điều kiện tái hiện và regression test (đặc biệt với driver version/queue).

### 24.6. Graceful shutdown của service

~~~text
SIGTERM
   |
Stop admitting HTTP/jobs mới
   |
Signal cancellations cho streams do service sở hữu
   |
Stop fetching new pages / scheduling new writes
   |
Bounded drain của in-flight tasks trong deadline
   |
Persist UNKNOWN write outcomes + checkpoints
   |
Close shared CqlSession theo đúng lifecycle
   |
Exit với báo cáo còn pending
~~~

Không dùng `forceCloseAsync`/đóng socket sớm như cách bảo đảm writes đã rollback. Shutdown là quản lý **tài nguyên client**, còn thông tin dữ liệu đã được ghi phải dựa vào ACK/CL và reconciliation.

## 25. Checklist khi code review và vận hành cancellation

### 25.1. Async Future và lifecycle

- [ ] `CqlSession` tái sử dụng; không tạo/đóng session per-request.
- [ ] Nắm `executeAsync` **bắt đầu request khi được gọi**.
- [ ] Xác định stage nào là root và ai sở hữu lifecycle; không giả định hủy dependent stage truyền ngược.
- [ ] `CompletableFuture.cancel(true)` không bị nhầm với interruption của server.
- [ ] Không gọi `join/get` trên future đã canceled mà không xử lý `CancellationException`.
- [ ] Phân biệt cancel result, error result và successful completion.
- [ ] Có AtomicBoolean/deadline trước `fetchNextPage()`.
- [ ] Biết race giữa kiểm flag và gửi page tiếp; không hứa zero in-flight after cancel.
- [ ] Callbacks trên driver I/O threads không blocking/CPU-heavy.
- [ ] Không dùng `completeOnTimeout` để trả write success giả.
- [ ] Dùng deadline end-to-end, không chỉ request timeout per-page.
- [ ] Nếu Future bị cancel ở HTTP layer, code vẫn xử lý metrics/unknown write outcome.

### 25.2. Reactive Streams/Reactor

- [ ] Biết `executeReactive` trả cold publisher, chỉ gửi CQL **khi subscribe**.
- [ ] Có một subscriber/owner thật; không tạo publisher trong `doOnNext` rồi bỏ.
- [ ] `ReactiveResultSet` single-subscription-only; retry cần publisher mới và policy đúng.
- [ ] `Subscription.cancel()`/`dispose()` chỉ điều khiển client stream/demand.
- [ ] `take(N)` không bị nhầm với CQL `LIMIT N` hoặc server-side kill.
- [ ] Với write publisher không emit rows, dùng completion signal chứ không đếm `onNext`.
- [ ] Dùng `flatMap(..., boundedConcurrency)` hoặc giới hạn tương đương cho bulk writes.
- [ ] Tránh `retry()` vô hạn, đặc biệt với mutation không idempotent.
- [ ] `Flux.timeout(Duration)` được hiểu đúng như timeout giữa items, không mặc định deadline toàn API.
- [ ] Khi dùng framework HTTP, trả `Mono/Flux` thay vì tự subscribe không quản lý.
- [ ] Không cache/multicast hàng triệu result rows vào heap chỉ để tránh subscribe lại.
- [ ] Có metric cho cancelled subscription, rows delivered, pages requested, retry/error.

### 25.3. Cassandra correctness

- [ ] Partition key/CL/RF/DC đúng theo access pattern.
- [ ] Write cancellation được phân loại **UNKNOWN_OUTCOME** nếu có khả năng đã gửi.
- [ ] Idempotency key/operation ID ổn định qua HTTP retry.
- [ ] Không bật `idempotent=true` cho counter, list append, arbitrary LWT hoặc side effect tùy ý.
- [ ] Không dùng `SELECT` ở `ONE` ngay sau cancel làm bằng chứng cuối cùng “write không tồn tại”.
- [ ] Có event audit/version/reconciliation theo business policy.
- [ ] Không mặc định compaction/flush/repair dừng vì request cancel.
- [ ] Không hạ CL/giảm durability để làm timeout biến mất.
- [ ] Failure injection chỉ trong staging có quyền và rollback plan.
- [ ] Không tiết lộ PII/credentials/raw CQL values qua cancellation logs.

### 25.4. Giám sát và rollout

- [ ] Theo dõi phiên bản driver, đặc biệt các bản sửa về request throttling/cancellation.
- [ ] Driver `cql-requests`, `cql-messages`, retries và speculative executions được tách biệt.
- [ ] Có `pool.orphaned-streams`/`pool.available-streams`/`pool.in-flight` nếu backend hỗ trợ.
- [ ] Có `throttling.queue-size`, request/client timeouts, HTTP cancel ratios.
- [ ] Có Cassandra server read/write latency, disk/GC, tombstone/compaction metrics.
- [ ] Dùng canary/control theo cùng workload và nhìn resource chung.
- [ ] Đặt GO/HOLD/STOP theo SLO và correctness thay vì một ngưỡng fix cho mọi cluster.
- [ ] Sau rollback kiểm **cả application SLO lẫn unknown outcomes**, không chỉ config file.

## 26. Câu hỏi tự đánh giá và gợi ý đáp án

**Câu 1.** `executeAsync(statement)` gửi CQL lúc gọi hay chờ `thenApply`?  
**Gợi ý:** Bắt đầu xử lý request khi gọi `executeAsync`; callback chỉ tiêu thụ kết quả.

**Câu 2.** `executeReactive(statement)` gọi xong chưa subscribe có gửi CQL không?  
**Gợi ý:** Chưa; publisher cold mặc định chỉ execute khi subscribe.

**Câu 3.** `CompletableFuture.cancel(true)` có gửi tín hiệu dừng thread của Cassandra không?  
**Gợi ý:** Không; JDK Future flag không có quyền kill server JVM và native protocol không có ordinary CQL cancel frame.

**Câu 4.** `cancel(false)` trả true chứng minh điều gì?  
**Gợi ý:** Future chưa hoàn tất và đã chuyển sang trạng thái canceled; không chứng minh server chưa xử lý.

**Câu 5.** `cancel(false)` trả false có luôn là query thất bại không?  
**Gợi ý:** Không; có thể Future đã hoàn thành thành công/error trước khi cancel.

**Câu 6.** Hủy một dependent `thenApply` có chắc hủy root `executeAsync` không?  
**Gợi ý:** Không. JDK cancellation thường không propagate ngược từ child lên parent.

**Câu 7.** Nếu hủy Future sau khi INSERT đã gửi, có thể trả client “chắc chắn chưa ghi” không?  
**Gợi ý:** Không; đánh dấu unknown write outcome và reconcile.

**Câu 8.** Trong native protocol v5, có message `CANCEL QUERY` tiêu chuẩn cho ordinary CQL execution không?  
**Gợi ý:** Không theo các opcode message thông thường; cancellation phía driver bỏ response/stop demand.

**Câu 9.** Tại sao một stream ID bị orphan sau cancellation?  
**Gợi ý:** Response của request cũ có thể tới muộn, nên không thể cấp lại ID ngay cho request khác.

**Câu 10.** `pool.orphaned-streams` tăng có thể kéo theo gì?  
**Gợi ý:** `pool.available-streams` giảm, kết nối bị recycle/churn, pool pressure tăng.

**Câu 11.** Khi chỉ đọc current page của `AsyncResultSet` rồi không gọi `fetchNextPage()`, điều gì được tránh?  
**Gợi ý:** Các page requests tiếp theo chưa được khởi tạo; trang đầu vẫn đã được gửi.

**Câu 12.** Nếu flag cancel được set cùng lúc code gọi `fetchNextPage()`, có chắc không còn request nào mới được gửi không?  
**Gợi ý:** Không; race giữa kiểm flag và gửi request.

**Câu 13.** `page-size=100` có đồng nghĩa toàn bộ query chỉ có 100 rows không?  
**Gợi ý:** Không; page-size là cỡ trang, khác CQL `LIMIT`/giới hạn API.

**Câu 14.** Reactive `Subscription.request(1)` có yêu cầu Cassandra đọc đúng một row từ SSTables rồi dừng không?  
**Gợi ý:** Không; driver điều tiết phát rows/fetch pages, native CQL không có demand protocol tương ứng.

**Câu 15.** `Subscription.cancel()` có gọi `onComplete()` bắt buộc không?  
**Gợi ý:** Không; cancellation là ngừng subscription, thường không tạo terminal onComplete signal.

**Câu 16.** Reactor `take(2)` phát upstream cancel sau 2 rows nghĩa là server đã dừng đúng row 2?  
**Gợi ý:** Không; server có thể đã tính/gửi cả trang đầu.

**Câu 17.** Reactive `take(2)` và `SELECT ... LIMIT 2` khác nhau ở đâu?  
**Gợi ý:** take là giới hạn downstream; LIMIT là restriction của CQL phía server.

**Câu 18.** Cùng một `ReactiveResultSet` có thể subscribe hai lần để đọc lại không?  
**Gợi ý:** Không theo publisher mặc định single-subscription-only; tạo publisher mới hoặc share/cache có kiểm soát.

**Câu 19.** `Flux.defer(() -> session.executeReactive(stmt))` thay đổi gì với retry?  
**Gợi ý:** Tạo publisher/request mới cho mỗi subscription; retry có thể thực thi lại CQL.

**Câu 20.** Một INSERT reactive emit bao nhiêu rows bình thường?  
**Gợi ý:** 0 rows; thành công được biết nhờ hoàn tất Publisher, không nhờ số onNext.

**Câu 21.** Vì sao đếm `Flux.from(insert).count()` không phải số writes thành công?  
**Gợi ý:** Nó đếm row items; INSERT thành công thường không emit rows.

**Câu 22.** Nếu flatMap write có concurrency=8 rồi downstream cancel, 8 writes đã in-flight có chắc không chạy nữa không?  
**Gợi ý:** Không; những writes đã gửi có thể tiếp tục, các writes chưa subscribe có thể tránh được.

**Câu 23.** Vì sao write-heavy reactive pipeline cần limit concurrency?  
**Gợi ý:** Cassandra native protocol không áp Reactive Streams backpressure trực tiếp cho server write input; quá nhiều messages có thể overload.

**Câu 24.** `Flux.timeout(Duration.ofSeconds(2))` có là hard deadline 2s cho toàn stream 100 pages không?  
**Gợi ý:** Không mặc định; nó thường đo khoảng im lặng giữa các items.

**Câu 25.** `CompletableFuture.orTimeout` có dừng server query không?  
**Gợi ý:** Không; nó hoàn tất Future phía JDK bằng TimeoutException, không phải server kill.

**Câu 26.** `DriverTimeoutException` và `ReadTimeoutException` khác nhau thế nào?  
**Gợi ý:** Client deadline vs server/coordinator read timeout; có thể cùng xuất hiện trong các tình huống khác nhau.

**Câu 27.** Vì sao HTTP 504 vẫn có thể đi kèm row mới trên Cassandra?  
**Gợi ý:** Gateway đã ngừng chờ nhưng mutation/ACK có thể hoàn tất ở server.

**Câu 28.** Nếu muốn bảo đảm retry POST tạo order không tạo hai rows, cần gì ngoài cancellation?  
**Gợi ý:** Stable operation ID/idempotency key, source-of-truth, version/dedup/outbox/reconciliation.

**Câu 29.** `setIdempotent(true)` có tự biến counter increment thành idempotent không?  
**Gợi ý:** Không; flag chỉ hướng dẫn driver retry/speculation, không sửa semantics.

**Câu 30.** Request bị timeout trong throttler queue có nhất thiết đã tới coordinator không?  
**Gợi ý:** Không; timeout có thể xảy ra trước network write. Nhưng phải có telemetry/version evidence để xác nhận một request cụ thể chưa gửi.

**Câu 31.** Changelog Java Driver 4.19 có lỗi nào liên quan async cancellation?  
**Gợi ý:** JAVA-3149 — cancellation chưa được truyền đúng tới request throttler ở các phiên bản trước, được sửa trong 4.19.

**Câu 32.** `RequestThrottlingException` có chứng minh lỗi `OverloadedException` của Cassandra server không?  
**Gợi ý:** Không; throttler phía driver từ chối, còn OverloadedException do server trả.

**Câu 33.** Speculative execution thắng ở node B thì node A chắc chắn dừng đọc ngay không?  
**Gợi ý:** Không; “cancellation” losing execution chủ yếu bỏ response ở client.

**Câu 34.** Vì sao không gọi `CqlSession.close()` khi một HTTP client disconnect?  
**Gợi ý:** Session là shared resource; đóng nó ảnh hưởng các requests khác và không bảo đảm server rollback.

**Câu 35.** Khi cancel ratio tăng nhưng CQL QPS không giảm, điều tra gì?  
**Gợi ý:** Cancel có thể quá muộn, không propagate đến paging, child future cancel không chạm root, speculation/retry/prefetch tăng messages.

**Câu 36.** Hai metrics giúp phát hiện stream ID pressure do cancel/speculation là gì?  
**Gợi ý:** `pool.orphaned-streams` và `pool.available-streams`, kết hợp `pool.in-flight`/connections.

**Câu 37.** Một statement reactive không có subscriber nhưng log “created publisher”. Có nghĩa write đã chạy không?  
**Gợi ý:** Không; publisher cold, cần subscribe.

**Câu 38.** Tại sao phải dùng monotonic time để tính remaining HTTP deadline?  
**Gợi ý:** Tránh ảnh hưởng clock adjustments; timestamps UTC dùng để correlation khác với duration.

**Câu 39.** Hủy reactive stream có tự xóa tombstones/flush queue/compaction backlog không?  
**Gợi ý:** Không; những công việc thuộc storage lifecycle tiếp tục theo Cassandra.

**Câu 40.** Một operation `CANCELLED_CLIENT` có đồng thời mang trạng thái `RECONCILED_SUCCESS` không?  
**Gợi ý:** Có; client hủy trước ACK nhưng business reconciliation sau xác minh write đã xảy ra.

## 27. Tổng kết: giới hạn đáng nhớ của cancellation

~~~text
                     JAVA APPLICATION
                            |
                 Chọn execution model
                    /             \
             ASYNC FUTURE        REACTIVE
              eager send       cold publisher
                    |               |
           executeAsync()       subscribe()
                    |               |
               request bắt đầu/gửi CQL
                            |
                 Cancel/timeout/disconnect
                            |
              +-------------+-------------+
              |                           |
      CLIENT-SIDE OUTCOME           SERVER-SIDE WORK
      Cancel future/result         Coordinator/replicas
      Stop demand/paging           Có thể đã nhận CQL
      Discard late response        Có thể đang đọc/ghi
      Mark UNKNOWN write           Có thể ACK đến muộn
              |                           |
              +-------------+-------------+
                            |
                  Observability + audit
                            |
            READ: dừng page fetch chưa bắt đầu
            WRITE: reconcile theo operation ID
                            |
                     SLO + correctness
~~~

### 27.1. Sáu nguyên tắc thực hành

1. **Không phát request thừa từ đầu:** Kiểm deadline/cancel trước `executeAsync` hoặc trước subscribe; kiểm trước mỗi page fetch.
2. **Không nhầm hủy Future với server rollback:** `cancel(true/false)` và `dispose()` phản ánh lifecycle client.
3. **Reactive SELECT:** Backpressure giúp điều tiết **trang tiếp theo**, không làm server dừng phần đã xử lý của trang hiện tại.
4. **Reactive WRITE:** Cần concurrency/rate limit; ngừng subscriber không khôi phục mutations đã gửi.
5. **Write outcome:** Hãy thiết kế idempotency/reconciliation cho caller disconnect, timeout và missing ACK.
6. **Quan sát cả hai bên:** Metrics cancel/timeout ở ứng dụng phải đặt cạnh node messages, orphaned streams, server read/write latency và dữ liệu nghiệp vụ.

**Thông điệp cốt lõi:** Cassandra Java Driver 4.x cho phép Java ứng dụng **ngừng chờ**, **ngừng tiêu thụ** hoặc **không gửi thêm** một phần công việc. Nhưng với CQL đã gửi qua native protocol, **không thể dùng trạng thái bị hủy của Future/subscription làm lời xác nhận coordinator/replicas đã dừng**. Điều quyết định sự an toàn là thời điểm gửi, semantics read/write, idempotency key, CL/RF, deadline và khả năng kiểm chứng trạng thái cuối cùng.

## Tài liệu tham khảo

- [Apache Java Driver 4.18 — Async programming](https://apache.github.io/cassandra-java-driver/4.18.0/core/async/) — `CompletionStage`, I/O thread callbacks và async error handling.
- [Apache Java Driver 4.18 — Paging](https://apache.github.io/cassandra-java-driver/4.18.0/core/paging/) — `AsyncResultSet.currentPage`/`fetchNextPage`, paging state và read pagination.
- [Apache Java Driver 4.18 — Reactive Streams](https://apache.github.io/cassandra-java-driver/4.18.1/core/reactive/) — cold/unicast publisher, subscription, backpressure, bounded write concurrency và retry/defer.
- [Apache Java Driver 4.18 — Speculative execution](https://apache.github.io/cassandra-java-driver/4.18.1/core/speculative_execution/) — hủy losing execution, không có server-side in-flight cancellation, `pool.orphaned-streams`.
- [Apache Java Driver 4.18 — Non-blocking](https://apache.github.io/cassandra-java-driver/4.18.1/core/non_blocking/) — I/O thread, async/reactive non-blocking guarantees.
- [Apache Java Driver 4.18 — Idempotence](https://apache.github.io/cassandra-java-driver/4.18.1/core/idempotence/) — retry/speculation và side effects.
- [Apache Java Driver 4.18 — Metrics](https://apache.github.io/cassandra-java-driver/4.18.1/core/metrics/) — metrics session/node, pool streams, retries và speculative executions.
- [DataStax Java Driver 4.17 — Request throttling](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/throttling/) — client throttler, deadline cả thời gian chờ queue, `RequestThrottlingException`.
- [DataStax Java Driver 4.17 — Reference configuration](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/configuration/reference/) — request timeout và các options Netty/metrics/throttler.
- [DataStax Java Driver 4.17 — ReactiveResultSet Javadoc](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/dse/driver/api/core/cql/reactive/ReactiveResultSet.html) — Publisher contract, single subscription, I/O thread concerns.
- [DataStax Java Driver 4.17 — AsyncResultSet Javadoc](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/cql/AsyncResultSet.html) — async pages và fetch next.
- [DataStax Java Driver 4.17 — DriverTimeoutException Javadoc](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/DriverTimeoutException.html) — client deadline, khác server READ/WRITE_TIMEOUT.
- [Apache Java Driver — Changelog](https://github.com/apache/cassandra-java-driver/blob/trunk/changelog/README.md) — 4.19 fix `JAVA-3149` về async query cancellation/request throttler.
- [Apache Cassandra — Native protocol v5](https://cassandra.apache.org/doc/latest/cassandra/reference/native-protocol.html) — QUERY/EXECUTE/RESULT, stream IDs và message model.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — coordinator, natural replicas, RF, CL và token routing.
- [Apache Cassandra — Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — server read/write latency, compaction và thread pools.
- [Apache Cassandra — Data modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html) — thiết kế theo truy vấn, phân vùng và tránh hotspots.
- [DataStax Enterprise — ContinuousAsyncResultSet](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/dse/driver/api/core/cql/continuous/ContinuousAsyncResultSet.html) — API cancellation **riêng cho continuous paging**, không áp vào ordinary Cassandra CQL.

