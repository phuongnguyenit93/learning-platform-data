# DriverTimeout, AllNodesFailed và thông tin lỗi theo từng nút trong Cassandra Java Driver

## 1. Mục tiêu bài học và ngữ cảnh

Apache Cassandra là cơ sở dữ liệu phân tán dạng **wide-column**: dữ liệu được xác định vị trí bằng **partition key**, phân phối theo token và sao chép đến các **replica** nhờ replication strategy. Khi Java client thực thi CQL, một node **coordinator** tiếp nhận yêu cầu và chờ phản hồi từ replica theo **consistency level (CL)** được chọn.

Lỗi truy vấn từ Java không chỉ có một loại. Một request có thể bị chậm ở ứng dụng, trong connection pool, trên đường truyền đến coordinator, tại coordinator hoặc trong lúc replica đọc SSTable/ghi commit log. Khi xảy ra lỗi, ta cần phân biệt:

- **`DriverTimeoutException`**: ngân sách thời gian yêu cầu ở phía Java Driver đã hết.
- **`AllNodesFailedException`**: driver không thực thi thành công request qua các node ứng viên; cần xem lỗi theo từng node bằng **`getAllErrors()`**.
- **`ReadTimeoutException` / `WriteTimeoutException`**: Cassandra server trả lỗi về điều kiện đọc/ghi và replica responses.
- **`UnavailableException`**: không đủ replica được coi là khả dụng cho CL.
- Lỗi **CQL/schema/authentication/authorization**: có thể là sai truy vấn hoặc cấu hình, không phải sự cố nên retry.

Bài thuộc chương **Retry và lỗi Java** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Sau khi học, bạn có thể:

1. Phân biệt deadline client với timeout server/coordinator và outage của replica.
2. Đọc danh sách lỗi của từng **coordinator ứng viên** mà Java Driver đã thử.
3. Triển khai phân loại exception trong Java Driver 4.x, cả đồng bộ và bất đồng bộ.
4. Phân tích tính **idempotent** trước khi retry, đặc biệt với counter, LWT, TTL và mutation không rõ kết quả.
5. Kết hợp metrics, `nodetool`, RF/CL, compaction, repair và driver telemetry để tìm nguyên nhân.
6. Thiết kế backoff, deadline và retry budget nhằm tránh retry storm.

Ví dụ sử dụng **Java Driver 4.x**, package `com.datastax.oss.driver.api.*`. Phiên bản 3.x dùng package khác, cùng các API retry/connection khác. Tên setting, chính sách mặc định và chi tiết các exception phải đối chiếu với release thực tế.

## 2. Đường đi request và ba nơi phát sinh lỗi

~~~mermaid
sequenceDiagram
    participant App as Java API
    participant Driver as Java Driver
    participant C as Coordinator
    participant A as Replica A
    participant B as Replica B
    App->>Driver: execute(BoundStatement)
    Driver->>C: CQL request
    C->>A: Read / write
    C->>B: Read / write
    Note over App,Driver: HTTP deadline và driver request timeout
    Note over C,B: Server timeout và CL
    A-->>C: Replica response
    B-->>C: Chậm hoặc lỗi
    C-->>Driver: Success hoặc server error nếu kịp
    Driver-->>App: ResultSet / exception
~~~

Một request thành công có thể cần nhiều replica, còn một request lỗi không có nghĩa tất cả replica đều chết. Đặc biệt, khi hết timeout **ở phía client**, coordinator hoặc replica có thể vẫn đang xử lý mutation.

| Phạm vi | Dấu hiệu thường thấy | Chúng ta biết gì? | Chúng ta chưa biết gì? |
|---|---|---|---|
| Driver request deadline | `DriverTimeoutException` | Request vượt ngân sách thời gian client | Server đã apply write hay chưa |
| Query plan/coordinator connection | `AllNodesFailedException` | Không có coordinator ứng viên nào hoàn tất request theo quy trình driver | Mọi replica có down không; mutation đã được ghi ở đâu |
| Server read | `ReadTimeoutException` | Coordinator không hoàn tất read theo điều kiện và thời hạn server | Dữ liệu có thật sự biến mất không |
| Server write | `WriteTimeoutException` | Coordinator không hoàn tất write theo điều kiện và thời hạn server | Mutation đã được một số replica ghi chưa |
| Server replica availability | `UnavailableException` | Không đủ replica được coi là có thể phục vụ cho CL | Khi nào có thể đạt quorum trở lại |
| Query/schema/security | Invalid query/syntax/auth errors | Truy vấn/quyền/config có vấn đề | Retry cùng input liệu có giúp không (thường không) |

**Đừng dùng một exception type để tự động quyết định có thể chạy lại mutation.** Trạng thái nghiệp vụ có thể không chắc chắn, kể cả khi Java nhận lỗi.

## 3. `DriverTimeoutException`: hết deadline phía client

### 3.1. Timeout này có ý nghĩa gì?

`DriverTimeoutException` trong Driver 4.x biểu thị một yêu cầu hết **request timeout** ở driver. Đồng hồ này thuộc lớp ứng dụng/driver, khác đồng hồ chờ replica của Cassandra server.

Ví dụ:

~~~text
T0  Service gửi INSERT qua driver
T1  Driver chọn coordinator, gửi request
T2  Replica A đã áp dụng mutation, B/C đang chậm
T3  Deadline phía driver hết
T4  Java nhận DriverTimeoutException
T5  Server có thể tiếp tục/hoàn tất request muộn hơn

Điều KHÔNG thể suy từ T4:
  - chưa node nào nhận mutation;
  - mutation chắc chắn đã rollback;
  - lỗi chỉ nằm ở một replica cụ thể.
~~~

Đây là timeline minh họa; Cassandra có đường ghi/ACK và timeout khác nhau tùy thao tác/version.

### 3.2. Nguyên nhân thường gặp

- Query shape sai, thiếu partition key, partition rộng hoặc nhiều tombstone/SSTable.
- Disk chậm do compaction, flush, repair, streaming hoặc thiếu headroom.
- Coordinator/replica quá tải CPU, GC, thread pool hoặc commit-log I/O.
- Driver connection pool bị dồn request, in-flight quá cao.
- Mạng app→coordinator có RTT tăng, packet loss, TLS/connection issue.
- Request timeout cấu hình nhỏ hơn thời gian cần cho workload.
- Retry/speculative execution và các attempt tiêu thụ ngân sách.
- Cluster vừa restart hoặc thay topology, metadata/connection chưa ổn định.

**Tăng timeout không sửa nguyên nhân**. Nó có thể khiến số exception giảm nhưng request giữ tài nguyên lâu hơn, p99 API tăng và queue tiếp tục tích lũy.

### 3.3. Cấu hình timeout

Ví dụ HOCON dành cho Java Driver 4.x:

~~~hocon
datastax-java-driver {
  basic.request.timeout = 3 seconds
}
~~~

`3 seconds` chỉ là **giá trị minh họa**, không phải mặc định hay khuyến nghị chung. Một statement có thể override theo API phiên bản:

~~~java
import java.time.Duration;

BoundStatement statement = prepared.bind(deviceId, day)
    .setTimeout(Duration.ofSeconds(3))
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
~~~

Hãy phân chia deadline end-to-end. Nếu HTTP API có giới hạn 1 giây, không đặt mỗi attempt Cassandra 3 giây rồi mong API phản hồi đúng hạn. Timeout phải tính cả validation, query, mapping, retry, backoff và trả response.

### 3.4. Điều không nên kết luận

Không được viết trong incident:

- “Driver timeout nghĩa là Cassandra không nhận request.”
- “Hết deadline nghĩa mọi replica đều down.”
- “Driver timeout chứng minh mutation không được ghi.”
- “Cứ retry đủ lần sẽ thành công.”
- “Tăng request timeout là giải pháp tối ưu chắc chắn.”

Cần bổ sung **idempotency, operation ID, server metrics, timeout/latency distribution và hậu kiểm dữ liệu**.

## 4. `AllNodesFailedException`: các node ứng viên đều không thực thi thành công

### 4.1. Hiểu đúng tên exception

`AllNodesFailedException` biểu thị rằng driver không thể thực hiện request thành công qua các node ứng viên được xem xét/thử trong **query plan**. Bên trong có thể là các lỗi khác nhau về kết nối, pool, handshake, metadata hoặc khả năng sử dụng coordinator.

“ALL” **không đồng nghĩa**:

- Tất cả node Cassandra trong mọi DC đã chết.
- Mọi replica của partition đều mất dữ liệu.
- Driver thực sự thử **từng node vật lý** trong cluster.
- Cassandra đã báo quorum timeout trên tất cả replica.
- Query chắc chắn chưa từng đến server trong mọi attempt.

Ví dụ ứng dụng chạy trong `dc1`, driver chỉ ưu tiên các coordinator ở local DC. Nếu đường mạng đến các node ấy lỗi, app có thể gặp `AllNodesFailedException` dù node `dc2` vẫn UP.

### 4.2. Các nguyên nhân cần phân loại

| Dấu hiệu | Khả năng | Hành động chẩn đoán |
|---|---|---|
| TLS handshake lỗi ở nhiều node | Truststore/cert rotation, hostname verification | Kiểm tra security config và timeline deploy |
| Lỗi authentication liên tục | Credentials/role/protocol không khớp | Kiểm tra secrets, auth/TLS, không retry vô hạn |
| Pool/connection busy | In-flight/concurrency quá cao, node xử lý chậm | Driver metrics, CPU/GC, disk/p99 |
| Connection reset/refused | Node restart, mạng/firewall, native transport | Status, logs, network path |
| Không coordinator nào phù hợp | Local DC, query plan, discovered nodes | Session config, topology metadata |
| Lỗi chỉ trên một số node | Hotspot, node health, routing, network zone | Per-node timeline + token/replica placement |

**Không chỉ đọc thông báo exception tổng quát**; phải xem lỗi chi tiết theo node và loại.

## 5. `getAllErrors()`: thông tin lỗi **theo từng node**

### 5.1. Cấu trúc API Driver 4.x

~~~java
Map<Node, List<Throwable>> byNode = exception.getAllErrors();
~~~

Với một `AllNodesFailedException`:

- **`Node`** là node/coordinator ứng viên driver ghi nhận.
- **`List<Throwable>`** chứa một hoặc nhiều lỗi liên quan node ấy trong quá trình thực thi.
- Một node có nhiều lỗi không có nghĩa nhiều replica đều đã thất bại.
- Một node không có entry trong map **không chứng minh node đó khỏe**; có thể nó nằm ngoài query plan hoặc không được thử.
- Số entries **không phải tổng số node cluster**.

**Ranh giới quan trọng:** `getAllErrors()` phản ánh **driver→candidate coordinator attempts**, không phải danh sách **coordinator→replica ACK/failure**. Không dùng map để suy ra replica nào fsync mutation.

### 5.2. Ví dụ map minh họa

~~~text
AllNodesFailedException
  node-A (coordinator candidate)
    - connection initialization failed
    - connection closed
  node-B (coordinator candidate)
    - pool busy
  node-C (coordinator candidate)
    - transport failure

Node D không xuất hiện:
  chưa kết luận D UP/DOWN, có dữ liệu hay không.
~~~

Đây chỉ là cấu trúc diễn giải, **không phải format mặc định** của `toString()`. Class lỗi cụ thể thay đổi theo driver/runtime và đường connection.

### 5.3. Đọc map bằng Java, không ghi dữ liệu nhạy cảm

~~~java
import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.metadata.Node;
import java.util.List;
import java.util.Map;
import java.util.logging.Level;
import java.util.logging.Logger;

public final class NodeFailureInspector {
    private NodeFailureInspector() {}

    public static void report(AllNodesFailedException ex,
                              String queryId,
                              Logger log) {
        Map<Node, List<Throwable>> perNode = ex.getAllErrors();

        log.log(Level.WARNING,
                "all_nodes_failed queryId={0} nodeEntries={1}",
                new Object[] {queryId, perNode.size()});

        for (Map.Entry<Node, List<Throwable>> entry
                : perNode.entrySet()) {
            Node node = entry.getKey();
            String nodeId = node == null
                ? "unknown" : String.valueOf(node.getHostId());
            String dc = node == null
                ? "unknown" : String.valueOf(node.getDatacenter());

            for (Throwable error : entry.getValue()) {
                String type = error == null
                    ? "unknown" : error.getClass().getSimpleName();

                log.log(Level.WARNING,
                    "cassandra_node_failure queryId={0} nodeId={1} " +
                    "dc={2} errorType={3}",
                    new Object[] {queryId, nodeId, dc, type});
            }
        }
    }
}
~~~

**`queryId` phải là tên query template cố định**, ví dụ `read_device_day`; không truyền raw CQL hoặc tenant/device ID. Metadata node có thể được xem là thông tin nội bộ nên chỉ ghi ở log sink được phép.

Không mặc định log `error.getMessage()`, `Throwable.toString()` hoặc toàn bộ stack trace vào log công khai; thông điệp có thể chứa endpoint, dữ liệu cấu hình, TLS details hoặc query context. Dùng kênh audit/debug hạn chế quyền khi cần chẩn đoán sâu.

### 5.4. Đọc lỗi theo thời gian, không chỉ một lần

Ví dụ:

~~~text
10:00  node-A handshake error    node-B handshake error
10:01  node-A handshake error    node-B handshake error
10:05  cấu hình truststore được sửa
10:06  lỗi giảm và request thành công
~~~

Giả thuyết mạnh hơn là **mismatch TLS** chứ không phải Cassandra mất dữ liệu. Nhưng vẫn phải kiểm chứng bằng logs/config/endpoint; map lỗi chỉ là **bằng chứng một phần**.

Mẫu thứ hai:

~~~text
11:00  node-A pool busy          node-B connection okay
11:05  node-A pool busy          node-B timeout
11:10  disk await ở node-A tăng, read backlog tăng
~~~

Cần xem traffic, token hotspot, in-flight và disk/GC, không chỉ tăng pool size. `AllNodesFailedException` đơn lẻ không ghi kèm những request thành công khác; bảng trên là **tổng hợp nhiều quan sát**.

## 6. Phân biệt timeout server và lỗi availability

### 6.1. `ReadTimeoutException` và `WriteTimeoutException`

`ReadTimeoutException`/`WriteTimeoutException` thường là **server errors** được coordinator trả khi thao tác đọc/ghi không hoàn thành theo điều kiện CL và thời hạn xử lý của Cassandra.

- **DriverTimeout:** deadline client đã hết; driver có thể không nhận được server response kịp.
- **ReadTimeout/WriteTimeout:** server/coordinator đã phát sinh thông báo timeout theo điều kiện thực thi.
- **AllNodesFailed:** driver thất bại qua những node coordinator ứng viên theo query plan, cần đọc per-node cause.

Nếu driver deadline ngắn hơn server timeout, Java có thể thấy `DriverTimeoutException` ngay cả khi coordinator đang chuẩn bị trả `ReadTimeoutException`.

### 6.2. RF=3 và LOCAL_QUORUM

~~~text
Partition P: replicas A, B, C
LOCAL_QUORUM tại dc1: cần 2 phản hồi phù hợp

Trường hợp 1: A trả, B/C chậm
  -> coordinator có thể trả server read/write timeout.

Trường hợp 2: driver hết deadline sớm
  -> Java thấy DriverTimeoutException.

Trường hợp 3: driver không có coordinator kết nối được
  -> Java có thể thấy AllNodesFailedException.
~~~

Sơ đồ chỉ mang tính khái quát, không mô tả mọi loại read/write, các pha LWT và speculative executions. **Node coordinator không nhất thiết chính là một trong các replica**.

### 6.3. `UnavailableException`

Khi server biết số replica sẵn sàng không đủ để đáp ứng CL, có thể trả `UnavailableException`. Đây là dấu hiệu cần xem **RF, DC, node UP/DOWN, topology và CL**.

Nếu RF=3 và chỉ một replica phản hồi được ở local DC thì `LOCAL_QUORUM` không thể đạt. Retry liên tục hoặc tăng deadline không làm một node down tự nhiên biến thành replica khỏe.

### 6.4. Lỗi query/auth không nên được retry như timeout

Sai partition key, CQL không hợp lệ, thiếu quyền, mật khẩu/TLS không đúng hoặc data type mismatch cần **sửa nguyên nhân**. Một retry policy không nên thử mãi cùng statement đã bị từ chối vì cú pháp hoặc quyền.

## 7. Tạo schema thực hành để gắn lỗi với CQL

Ví dụ lab sử dụng `NetworkTopologyStrategy` và DC tên `dc1`; phải điều chỉnh RF theo cluster lab thực tế:

~~~cql
CREATE KEYSPACE telemetry_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE telemetry_lab.readings_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    reading_value double,
    status text,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

**Partition key** là `(device_id, event_day)`. Query có đủ partition key:

~~~cql
SELECT event_time, reading_value, status
FROM telemetry_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
LIMIT 20;
~~~

Truy vấn hợp lệ theo access pattern không đồng nghĩa **không thể timeout**. Một partition quá rộng, nhiều SSTable/tombstone hoặc replica disk chậm vẫn khiến read p99 tăng.

Nếu source dùng query thiếu partition key hoặc `ALLOW FILTERING` trên phạm vi lớn, cần xem lại mô hình dữ liệu; không đặt hy vọng vào retry và token-aware routing.

## 8. Java Driver 4.x: phân loại lỗi đồng bộ

### 8.1. Ví dụ service dùng prepared query

~~~java
import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.DriverTimeoutException;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.UnavailableException;
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;

import java.time.Duration;
import java.time.LocalDate;
import java.util.UUID;
import java.util.logging.Logger;

public final class ReadingService {
    private static final Logger LOG =
        Logger.getLogger(ReadingService.class.getName());

    private final CqlSession session;
    private final PreparedStatement find;

    public ReadingService(CqlSession session) {
        this.session = session;
        this.find = session.prepare(
            "SELECT event_time, reading_value, status " +
            "FROM telemetry_lab.readings_by_device_day " +
            "WHERE device_id = ? AND event_day = ? LIMIT 20"
        );
    }

    public Row first(UUID deviceId, LocalDate day) {
        BoundStatement statement = find.bind(deviceId, day)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true)
            .setTimeout(Duration.ofSeconds(3));

        try {
            ResultSet result = session.execute(statement);
            return result.one(); // Có thể null nếu không có row.
        } catch (AllNodesFailedException ex) {
            NodeFailureInspector.report(ex, "read_device_day", LOG);
            throw ex;
        } catch (DriverTimeoutException ex) {
            LOG.warning("read_device_day: driver_timeout");
            throw ex;
        } catch (ReadTimeoutException ex) {
            LOG.warning("read_device_day: server_read_timeout");
            throw ex;
        } catch (WriteTimeoutException ex) {
            LOG.warning("read_device_day: server_write_timeout");
            throw ex;
        } catch (UnavailableException ex) {
            LOG.warning("read_device_day: unavailable");
            throw ex;
        }
    }
}
~~~

`NodeFailureInspector` là class ở phần 5.3, cần có trong project. Session được tạo/đóng theo vòng đời service với local DC, auth/TLS, không mở session cho từng HTTP request.

### 8.2. Vì sao catch riêng từng loại?

Nếu code chỉ làm:

~~~java
try {
    return session.execute(statement).one();
} catch (RuntimeException ex) {
    return null; // ANTI-PATTERN.
}
~~~

thì ứng dụng đã đánh đồng **request thất bại** với **không có row**. HTTP có thể trả `404` sai thay vì thông báo sự cố, và downstream có thể tạo lại dữ liệu vì tưởng bản ghi chưa tồn tại.

Hướng đúng là **ghi outcome riêng**, giữ exception class/cause cho lớp xử lý, và chỉ chuyển thành not-found khi SELECT **thành công** nhưng `one()==null`.

### 8.3. Những giới hạn của ví dụ

- `setIdempotent(true)` được dùng cho **SELECT đọc đơn giản**; không gắn cho mọi mutation.
- Timeout ba giây chỉ là ví dụ; phải căn theo API SLO.
- Catch `WriteTimeoutException` trong read service là minh họa phân nhóm; SELECT thường không kỳ vọng lỗi write timeout.
- Có nhiều exception khác cần được xử lý trong hệ thống thực; không coi danh sách catch là đầy đủ.
- Phân loại lỗi chưa tự quyết định **retry**; policy và nghiệp vụ phải đánh giá riêng.

## 9. Async: CompletionException có thể bọc lỗi driver

### 9.1. Vì sao không nên chỉ kiểm tra class wrapper?

Với Java Driver 4.x:

~~~java
CompletionStage<AsyncResultSet> stage =
    session.executeAsync(statement);
~~~

Khi dùng `CompletableFuture.join()` hoặc `Future.get()`, lỗi có thể được bọc trong `CompletionException` hoặc `ExecutionException`. Cần mở đúng lớp wrapper để biết nguyên nhân driver.

~~~java
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

static Throwable unwrapFutureFailure(Throwable error) {
    Throwable current = error;
    while ((current instanceof CompletionException
            || current instanceof ExecutionException)
           && current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
~~~

Không tùy tiện bỏ mọi lớp cause vì có thể mất ngữ cảnh. Hàm chỉ mở những wrapper bất đồng bộ phổ biến.

### 9.2. Trong callback

~~~java
stage.whenComplete((result, error) -> {
    if (error == null) {
        recordOutcome("read_device_day", "success");
        return;
    }

    Throwable cause = unwrapFutureFailure(error);

    if (cause instanceof AllNodesFailedException) {
        NodeFailureInspector.report(
            (AllNodesFailedException) cause,
            "read_device_day",
            LOGGER);
    } else if (cause instanceof DriverTimeoutException) {
        LOGGER.warning("read_device_day: driver_timeout");
    } else {
        LOGGER.warning(
            "read_device_day: " + cause.getClass().getSimpleName());
    }

    recordOutcome("read_device_day", "failure");
});
~~~

Đây là đoạn ghép **minh họa**: `stage`, `LOGGER` và `recordOutcome` cần được khai báo ở service. Không block callback thread bằng I/O dài; dùng executor riêng có queue giới hạn nếu cần.

## 10. Retry: ba điều kiện phải đồng thời đúng

Một lỗi chỉ nên được retry khi:

1. **Operation an toàn khi lặp lại** theo semantics nghiệp vụ, không chỉ theo hình thức CQL.
2. **Lỗi có khả năng transient**, không phải cú pháp, auth hoặc cấu hình vĩnh viễn.
3. **Còn ngân sách deadline, retry và khả năng phục vụ**, tránh khiến cluster đã nghẽn phải nhận thêm tải.

| Thao tác/lỗi | Có thể retry tự động? | Rủi ro |
|---|---|---|
| SELECT theo partition key, lỗi mạng ngắn | Có thể, có backoff và giới hạn | Read fanout, load, timeout |
| INSERT cùng primary key và nội dung cố định | Cần xét timestamp/TTL và update cạnh tranh | Kết quả cuối có thể không giống kỳ vọng |
| Counter increment | **Không retry mù** | Có thể cộng hai lần |
| LWT `IF NOT EXISTS` | Xử lý riêng, có read/verify | Timeout có thể xảy ra sau khi apply |
| Mutation tạo UUID mới trên mỗi attempt | Không lặp với ID mới | Có thể tạo dữ liệu trùng |
| Syntax error/invalid query | Không | Query giữ nguyên vẫn sai |
| Auth/permission error | Không trước khi sửa cấu hình | Retry không cấp thêm quyền |
| `AllNodesFailedException` chứa lỗi TLS | Không mặc định | Permanent failure có thể kéo dài |
| DriverTimeout khi cluster overload | Thường phải giảm tải trước | Retry storm làm p99 xấu hơn |

Bảng là **khung suy nghĩ**, không mô tả mọi default retry policy của Java Driver 4.x.

## 11. Idempotency và kết quả write không chắc chắn

### 11.1. INSERT với khóa ổn định

~~~cql
INSERT INTO telemetry_lab.readings_by_device_day
(device_id, event_day, event_time, reading_value, status)
VALUES (?, ?, ?, ?, ?);
~~~

Nếu retry với cùng primary key và cùng giá trị, thường không tạo row mới khác khóa. Tuy nhiên:

- Mutation timestamp mới có thể thắng update mới hơn theo chính sách timestamp.
- TTL có thể được tính lại, làm lệch thời điểm hết hạn.
- Side effect bên ngoài hoặc trigger có thể bị lặp.
- Một lần retry sau thời gian dài có thể ghi đè trạng thái mới.

**Idempotency phải đánh giá theo nghiệp vụ.** Không gắn `setIdempotent(true)` cho mọi write vì nghĩ INSERT luôn an toàn tuyệt đối.

### 11.2. Counter

Để chạy ví dụ trên lab, trước tiên cần có một bảng counter hợp lệ:

~~~cql
CREATE TABLE telemetry_lab.device_counters (
    device_id uuid PRIMARY KEY,
    samples counter
);
~~~

~~~cql
-- Ví dụ: không retry vô điều kiện khi outcome không rõ.
UPDATE telemetry_lab.device_counters
SET samples = samples + 1
WHERE device_id = ?;
~~~

Nếu lần đầu đã áp dụng increment nhưng response mất, retry có thể tăng hai lần. Muốn exactly-once logical effect phải có event ID/deduplication hoặc thay đổi mô hình dữ liệu.

### 11.3. LWT

~~~cql
INSERT INTO telemetry_lab.readings_by_device_day
(device_id, event_day, event_time, reading_value)
VALUES (?, ?, ?, ?)
IF NOT EXISTS;
~~~

Nếu request timeout sau khi đã được apply, retry có thể trả `wasApplied()==false` vì row nay đã tồn tại. Điều đó **không chứng minh lần đầu thất bại**. Phải kiểm tra ID và invariant của record cùng mọi side effect.

### 11.4. DELETE/TTL

DELETE có thể tạo tombstone. Lặp lại với timestamp mới trong lúc update khác diễn ra có thể che mutation mới. TTL có thể gây thay đổi thời gian hết hạn khi retry. Những thao tác này cần quy tắc timestamp và replay rõ, không retry theo class exception duy nhất.

## 12. Retry budget, deadline và backoff

### 12.1. Các tầng retry có thể nhân tải

~~~text
Gateway retries:       tối đa 3 attempts
Application retries:   tối đa 3 attempts
Driver retries:        tối đa 2 attempts

Worst-case minh họa khi không điều phối:
  3 x 3 x 2 = 18 request attempts
  cho một logical request từ người dùng.
~~~

Không phải mọi policy tự tạo số attempt này, nhưng phép tính chỉ ra nguy cơ **retry amplification**. Nếu cluster đã quá tải, mỗi tầng thêm request có thể tạo một **retry storm**.

### 12.2. Bounded retry

~~~mermaid
flowchart TD
    A["Request failed"] --> B{"Có phải transient?"}
    B -->|Không| C["Fail fast hoặc sửa config/query"]
    B -->|Có| D{"Idempotent và còn budget?"}
    D -->|Không| E["Outcome unknown, đối soát"]
    D -->|Có| F["Backoff + jitter; giới hạn attempts"]
    F --> G["Thử lại trong deadline còn lại"]
    G --> H["Quan sát latency, error, tải replica"]
~~~

Đừng mặc định `AllNodesFailedException` luôn transient. Nếu error map cho thấy TLS/credentials sai ở mọi node, sửa config có ý nghĩa hơn retry.

### 12.3. Phối hợp với HTTP deadline

Ví dụ minh họa:

~~~text
Deadline HTTP API:          1000 ms
Auth + validation:           100 ms
Cassandra attempts:          700 ms
Mapping + response:          100 ms
Safety margin:               100 ms
~~~

Nếu mỗi attempt Cassandra timeout 3 giây, API không còn khả năng giữ deadline một giây. Cần tính **tổng deadline**, bao gồm cả backoff, số request in-flight và việc cancellation.

Không được tăng request timeout chỉ vì tỷ lệ exception giảm; phải xem **p99 end-to-end, error budget và backlog**.

## 13. Lỗi theo coordinator không phải ACK theo replica

Giả sử:

~~~text
Driver thử coordinator A: connection failed
Driver thử coordinator B: connection failed

getAllErrors():
    A -> connection failure
    B -> connection failure
~~~

Thông tin này **không** cho biết:

- Replica R1/R2/R3 có giữ partition liên quan hay không.
- Mutation từ **request trước** đã tới replica nào.
- Coordinator C ngoài query plan còn khả dụng hay không.
- Commit log trên replica nào đã fsync.
- Quorum có đạt được từ client ở mạng khác không.

Ngược lại, `WriteTimeoutException` do coordinator trả không tự có map `Node → List<Throwable>` chứa mọi replica. Các công cụ **per-node client attempts** và **per-replica consistency** đo các phạm vi khác nhau.

Muốn đánh giá replica placement, cần **RF/topology/token metadata, nodetool status và metrics/logs**. Muốn xác nhận outcome của write, cần **kiểm chứng trạng thái nghiệp vụ** hoặc cơ chế deduplication/reconciliation, không chỉ đọc Java exception.

## 14. Routing key, token, RF và local datacenter ảnh hưởng lỗi ra sao?

### 14.1. Coordinator ứng viên không đồng nghĩa replica của partition

Prepared statement có đầy đủ partition key thường giúp Java Driver suy ra **routing key** và token, từ đó ưu tiên coordinator thuộc tập replica phù hợp. Tuy nhiên:

- Token-aware load balancing là **chiến lược chọn coordinator** ở phía driver.
- Coordinator có thể nằm ngoài replica set mà vẫn thực thi request đúng.
- RF, datacenter và rack quyết định những **replica** nào giữ dữ liệu.
- CL xác định số phản hồi cần thiết để thao tác thành công.
- Lỗi kết nối tới coordinator không tự chứng minh replica thiếu dữ liệu.

Ví dụ một partition được replicate ở A, B, C nhưng Java app không thiết lập được kết nối tới **coordinator ứng viên** A/B. `AllNodesFailedException.getAllErrors()` có thể ghi A và B thất bại, trong khi bản sao dữ liệu vẫn còn trên C. Ngược lại, nếu một coordinator kết nối được và trả `ReadTimeoutException`, phải xem replica responses/CL, không chỉ driver connection pool.

### 14.2. Multi-DC và LOCAL_QUORUM

Giả sử keyspace dùng `NetworkTopologyStrategy`:

~~~cql
-- Minh họa replication ở hai DC, cần thay tên DC theo cluster thực.
CREATE KEYSPACE multi_dc_demo
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
}
AND durable_writes = true;
~~~

Nếu Java client chạy ở `dc1` và đặt local datacenter là `dc1`, load-balancing có thể ưu tiên local coordinators. Khi đường app→dc1 lỗi, `AllNodesFailedException` **không phải bằng chứng dc2 down**.

Với `LOCAL_QUORUM`, điều kiện thành công thường dựa trên quorum của **DC cục bộ** cho request. Không có nghĩa write đã được xác nhận bởi quorum ở mọi DC.

**Không sửa lỗi timeout bằng việc tự chuyển `LOCAL_QUORUM` sang `ONE`** mà không đánh giá tính đúng, dữ liệu cũ và rủi ro khi node chưa đồng bộ. Đây là quyết định về correctness/availability.

### 14.3. Topology thay đổi trong rolling upgrade

Khi bootstrap, replace hoặc rolling upgrade:

- Một node có thể `UJ`, `DN` hoặc đang restart.
- Driver metadata/query plan có thể tạm thời chưa theo kịp gossip/topology.
- Hints delivery, streaming, compaction và commit-log replay có thể gây p99 cao.
- Error map có thể đổi nhanh theo node vì pool đang tái thiết lập kết nối.

Hãy lưu **timestamp UTC, phiên bản node/driver, DC/rack và change ID**. Không hard-code danh sách coordinator ứng viên từ trước bootstrap rồi gọi mọi khác biệt là lỗi.

## 15. Đối chiếu Java exception với `nodetool`

### 15.1. Các lệnh đọc trạng thái thường dùng

~~~bash
# Trạng thái node, datacenter/rack, token ownership.
nodetool status

# Executor Active/Pending/Completed, dropped messages.
nodetool tpstats

# Pending compaction và tiến độ tác vụ.
nodetool compactionstats

# SSTable streaming khi repair/bootstrap/rebuild.
nodetool netstats

# Thống kê đọc/ghi và SSTable theo table.
nodetool tablestats telemetry_lab.readings_by_device_day

# Histogram khi phiên bản hỗ trợ.
nodetool tablehistograms telemetry_lab readings_by_device_day
~~~

Đây là nhóm lệnh để **quan sát**, nhưng output, cú pháp và scope có thể khác theo Cassandra version. Phải kiểm tra `nodetool help` và tài liệu của release. Những lệnh như `flush`, `repair` hay `compact` là **thao tác tạo tải**, không dùng tùy tiện chỉ để thu thập số liệu.

### 15.2. Ma trận đối chiếu

| Dấu hiệu phía Java | Điều cần xem ở Cassandra/hạ tầng | Giả thuyết |
|---|---|---|
| `DriverTimeoutException` tăng + read p99 tăng | ReadStage Pending, SSTables per read, disk latency | Read path quá tải/tombstone/hot partition |
| Driver timeout tăng khi backfill | Mutation/flush/compaction queue, disk free | Background work tranh tài nguyên |
| `AllNodesFailed` với TCP errors diện rộng | Firewall, DNS, network, status, native transport | Kết nối app→coordinator lỗi |
| `AllNodesFailed` với TLS failures | Cert chain, truststore, expiry, hostname | Security handshake không thành công |
| Lỗi tập trung một node | CPU/GC, disk, pool, partition hotspot | Node hoặc đường app→node cục bộ có vấn đề |
| `WriteTimeoutException` tăng | Commit-log sync latency, MutationStage, RF/CL | Replica chậm, không đủ ACK kịp |
| `ReadTimeoutException` tăng sau repair | Disk/streaming/network và replica read latency | Repair/streaming tranh I/O |
| `UnavailableException` khi node down | `nodetool status`, RF/DC, rack | Không đủ replica cho CL |
| Timeout một query, query khác khỏe | Schema, partition key, page size, LIMIT, tombstones | Query shape/phân bố dữ liệu |
| Lỗi sau deploy driver | Driver config/version, local DC, TLS, profile | Client thay đổi thay vì server hỏng |

### 15.3. Phải đo delta thay vì chỉ nhìn counter

Giả sử `tpstats` của một node cho thấy:

~~~text
Time       ReadStage Pending     Completed     READ Dropped
10:00                 80           500000                5
10:01                980           512000               65

Tốc độ completed trong 60 giây:
    (512000 - 500000) / 60 = 200 tasks/s

Pending tăng 900, READ Dropped tăng 60.
~~~

`Completed` là **counter tích lũy** trong phạm vi stage, không phải CQL QPS. `Dropped` theo message type không ánh xạ 1:1 với failed SELECT. Nếu node restart giữa hai lần đo, counter có thể reset; phải loại khoảng đo đó khỏi phép trừ.

**Một node `UN` không đồng nghĩa node đáp ứng SLO.** Nó có thể đang có pending queue hoặc disk stall khiến driver timeout.

### 15.4. `netstats` trống chưa chắc mạng khỏe

`nodetool netstats` thường tập trung **SSTable streaming**. Nó không hiển thị mọi CQL traffic, gossip, native transport, TLS failures hay connection pool. Nếu `netstats` không có stream nhưng `AllNodesFailedException` liên quan TCP, vẫn phải kiểm tra **app-to-node network**.

## 16. Logging và metrics an toàn

### 16.1. Một sự kiện log có cấu trúc

~~~text
event=cassandra_request_failure
query_id=read_device_day
outcome=driver_timeout
error_class=DriverTimeoutException
consistency=LOCAL_QUORUM
request_timeout_ms=3000
elapsed_ms=3005
routing_key_present=true
local_dc=dc1
attempt_count=unknown
~~~

Đây là **định dạng do ứng dụng đề xuất**, không phải log mặc định của Cassandra. Nếu không có instrument để đo attempts thực, ghi **unknown** thay vì đoán.

Với `AllNodesFailedException`, nên có số entry và các nhóm lỗi:

~~~text
event=cassandra_request_failure
query_id=read_device_day
outcome=all_nodes_failed
node_entries=3
node_error_family.connection=2
node_error_family.handshake=1
~~~

`node_error_family` là nhãn **do hệ thống observability phân loại**, không phải enum driver bắt buộc. Khi nhóm cause, cần lưu mapping phiên bản và không làm mất loại lỗi gốc trong kênh debug được phép.

### 16.2. Tránh rò rỉ và nổ cardinality

Không đưa những thông tin sau vào labels hoặc log công khai:

- Raw `device_id`, `tenant_id`, email, access token, password.
- Bind values, raw CQL đã nội suy dữ liệu nhạy cảm.
- Full exception message/stack trace cho **mọi** request lỗi.
- Raw routing key bytes hoặc token cho mỗi partition làm metric label.
- IP/hostname nội bộ nếu policy không cho phép chia sẻ.

Nên dùng **query ID cố định, outcome, class, node identity ở mức kiểm soát, DC và sampling**. Truy vết sâu có thể dùng log/audit giới hạn quyền và thời gian giữ.

### 16.3. Dashboard tối thiểu

| Lớp | Cần đo | Lý do |
|---|---|---|
| HTTP/Java | QPS, p50/p95/p99, timeout, 5xx, request cancellations | Biết ảnh hưởng tới người dùng |
| Driver | Lỗi theo class, retry/speculative attempts, in-flight, connection failures | Phân biệt client budget và connectivity |
| Per-node errors | Node metadata, count theo error class | Tìm pattern một node hay toàn local DC |
| Cassandra | Read/write p99, `tpstats` pending/dropped | Kiểm tra coordinator/replica quá tải |
| Storage | Disk free, fsync/write/read latency, compaction pending | Tìm I/O bottleneck |
| Network | RTT, retransmits, packet loss, TLS handshake | Phân biệt transport vs query |
| Topology | Node UP/DOWN, RF/CL, DC/rack, streaming/repair | Đánh giá khả năng đạt quorum |

**Không lấy trung bình p99 từng node để tính p99 toàn cluster.** Phân vị phải dựa trên histogram/phân bố phù hợp, và phải xem **timeout/error rate** vì request timeout có thể không xuất hiện trong histogram latency của request thành công.

## 17. Runbook A — `DriverTimeoutException` tăng nhanh

**Tình huống:** API read có p99 tăng từ 90 ms lên 1.800 ms. Driver request timeout đặt 3 giây, lỗi `DriverTimeoutException` tăng, nhiều node vẫn `UN`.

1. **Xác định phạm vi:** query ID, keyspace/table, CL, tenant/operation group, DC, thời điểm bắt đầu. Không lộ bind values trong ticket.
2. **Đo cả client và server:** read QPS, request in-flight, connection pool, p99, retries, timeout rate; `tpstats`, disk/GC và `compactionstats`.
3. **Xem query shape:** đủ partition key chưa, `ALLOW FILTERING`, số SSTable/tombstone, partition width, page size và tổng số page.
4. **Tìm background work:** repair/streaming, backfill, compaction, bootstrap, volume throttling hoặc log I/O errors.
5. **Giảm tải có kiểm soát:** pause backfill không khẩn cấp, bounded concurrency, giảm retry amplification; ưu tiên giữ API chính hoạt động.
6. **Chỉ chỉnh timeout khi có căn cứ:** nếu workload hợp lệ cần thêm thời gian và SLO cho phép, cân nhắc điều chỉnh trong budget; không lấy nó thay cho sửa hotspot/đĩa.
7. **Xác minh:** queue giảm, p99/error/timeout giảm, disk có headroom và không mất correctness của CL.

**Đừng chuyển timeout thành “không có row”.** Khi xử lý SELECT, chỉ `ResultSet.one()==null` **sau một truy vấn thành công** mới biểu thị không có row phù hợp.

## 18. Runbook B — `AllNodesFailedException` sau thay đổi certificate

**Tình huống:** Một nhóm pod Java mới deploy có `AllNodesFailedException` trên mọi request, nhưng dịch vụ cũ vẫn kết nối Cassandra được.

1. **Đọc `getAllErrors()`:** tổng hợp class lỗi theo node; chú ý handshake, connection initialization và auth.
2. **Khoanh vùng release:** chỉ pod mới, một namespace, một region hay mọi client? So truststore/secret/config của nhóm khỏe.
3. **Kiểm tra TLS:** CA chain, certificate expiry, hostname verification, protocol/cipher, rotation timeline.
4. **Kiểm tra local DC và network:** contact points, port native transport, DNS, load-balancing; `nodetool status` một mình không xác nhận app→node connectivity.
5. **Không vô hiệu hóa TLS trên production** để “test nhanh”; dùng môi trường lab và quy trình bảo mật.
6. **Rollback config nếu cần:** triển khai theo change/incident runbook và xác minh pods mới kết nối lại.
7. **Đối chiếu per-node failures:** handshake errors hết, query success tăng, p99 ổn, pool tái lập.
8. **Cập nhật preventive controls:** test cert rotation, alert sớm cert expiry và smoke test driver.

Nếu cause là auth/TLS permanent, retry vô hạn chỉ tạo log storm và tốn tài nguyên.

## 19. Runbook C — Write timeout với kết quả chưa chắc chắn

**Tình huống:** Service ghi một đơn hàng rồi nhận `DriverTimeoutException` hoặc `WriteTimeoutException`. Gateway muốn tự gọi lại `POST` ngay.

### Bước 1 — Đánh giá operation ID

Có `order_id`/`event_id` ổn định trên mọi attempt không? Có dùng counter, LWT, TTL, dynamic timestamp, email hoặc payment side effects không?

### Bước 2 — Không coi timeout là rollback

Một số replica có thể đã xử lý mutation dù client không thấy success. Ghi outcome **UNKNOWN** nếu chưa đủ bằng chứng.

### Bước 3 — Đối soát dữ liệu

Đọc theo primary key với CL phù hợp; kiểm tra status, version, ID và invariant. Nếu dùng LWT, hiểu rằng retry trả `wasApplied()==false` **có thể** chỉ vì lần đầu đã apply.

### Bước 4 — Retry an toàn khi có đủ điều kiện

Chỉ replay **cùng logical operation** nếu idempotent đã được thiết kế và còn deadline/retry budget. Không sinh UUID mới hay phát lại side effect không idempotent.

### Bước 5 — Chẩn đoán server

Xem RF/CL, mutation/flush queues, commitlog I/O, disk, network và số replica available. Phân biệt lỗi server timeout với deadline driver.

### Bước 6 — Đóng vòng nghiệp vụ

Nếu yêu cầu exactly-once logical effect, cần deduplication/event log/outbox hoặc reconciliation phù hợp. **Driver retry tự nó không bảo đảm exactly-once**.

## 20. Runbook D — Lỗi tập trung ở một node trong error map

**Tình huống:** Qua nhiều request, `getAllErrors()` thường chứa lỗi pool busy/connection closed ở node A, nhưng một số request qua B/C thành công.

1. So số lỗi theo thời gian và class, không chỉ một exception.
2. Kiểm tra A có là coordinator thường được ưu tiên do token-aware routing và hot partition không.
3. Đo in-flight/connection pool theo node ở Java client.
4. Kiểm tra disk latency, CPU/GC, `tpstats` pending/dropped, compaction, commit-log và logs của A.
5. Nếu vấn đề chỉ từ một app region, so network RTT/TCP reset từ region đó tới A.
6. Không tự pin tất cả request sang B/C; họ có thể thành hotspot mới và vẫn cần đáp ứng RF/CL.
7. Giảm load hoặc sửa network/node capacity theo runbook có rollback.
8. Xác minh error class frequency, p99, timeout, CPU/disk và replica health trở về baseline.

**Một node không xuất hiện trong map ở request cụ thể chưa chắc khỏe**. Nó có thể không thuộc query plan hoặc không được thử.

## 21. Cây quyết định xử lý nhanh

~~~mermaid
flowchart TD
    A["Cassandra exception từ Java"] --> B{"Loại lỗi?"}
    B -->|DriverTimeoutException| C["Deadline/p99/in-flight/network"]
    B -->|AllNodesFailedException| D["getAllErrors theo node/cause"]
    B -->|Read/WriteTimeout| E["Replica responses, CL, I/O"]
    B -->|Unavailable| F["RF/DC, nodes UP/DOWN, quorum"]
    B -->|Invalid/Auth| G["Sửa query/config/quyền; fail fast"]
    C --> H{"Transient? idempotent? còn budget?"}
    D --> H
    E --> H
    F --> H
    H -->|Có| I["Retry bounded + jitter + quan sát"]
    H -->|Không/unknown| J["Không retry mù; đối soát"]
    I --> K["Đo lại API SLO + backend load"]
    J --> K
~~~

Flowchart là **khung xử lý**, không thay quyết định retry policy theo version và nghiệp vụ. Một `AllNodesFailedException` chứa lỗi TLS permanent phải đi theo nhánh sửa cấu hình, không phải nhánh retry.

## 22. Bảng lỗi thường gặp khi lập trình

| Anti-pattern | Hậu quả | Cách đúng |
|---|---|---|
| Catch `RuntimeException` rồi trả `null` | Timeout bị biến thành not-found | Tách result không row và request failure |
| Catch mọi lỗi rồi retry ngay | Retry storm, hỏng semantics | Phân loại transient/idempotent/budget |
| Log mỗi `AllNodesFailed` bằng một dòng chung | Không thấy node/cause khác biệt | Dùng `getAllErrors()`, log loại lỗi/node |
| Log toàn bộ `getMessage()` ra metrics labels | Rò PII, nổ cardinality | Query ID, error type, sampling |
| Gán `setIdempotent(true)` cho counter | Có thể cộng trùng | Thiết kế dedup/không retry mù |
| Dùng `IF NOT EXISTS` rồi retry không kiểm tra row | Có thể hiểu sai `wasApplied` | Xác minh operation identity/invariant |
| Tăng driver timeout vô hạn | Request giữ queue/heap lâu | Xác định bottleneck, bounded deadline |
| Tạo `CqlSession` mới cho từng request | Connection churn và latency | Session tái sử dụng |
| Dùng `ONE` để che lỗi quorum | Thay đổi tính nhất quán | Sửa replica/topology/capacity |
| Cho gateway/app/driver retry độc lập | Nhân số attempts | Retry budget end-to-end |
| Không unwrap async `CompletionException` | Phân loại sai root exception | Mở wrapper Future đúng cách |
| Coi AllNodesFailed là toàn cluster DOWN | Sai phạm vi incident | Đối chiếu query plan/DC/node map |
| Coi per-node errors là replica ACK map | Đánh giá sai dữ liệu đã ghi | Xác minh consistency và dữ liệu nghiệp vụ |

## 23. Kiểm thử lỗi có kiểm soát trong môi trường lab

### 23.1. Trước khi thử

- Dùng **cluster Cassandra cô lập** và dữ liệu giả, không chạy fault injection trên production.
- Ghi driver/version, RF/CL, topology, request timeout và retry policy.
- Bảo đảm có thể khôi phục lab; không giữ kết nối tới cluster thật trong app test.
- Xác định phép thử muốn phân biệt **deadline client**, **node connectivity** hay **replica timeout**.
- Đặt giới hạn QPS và concurrency để thử nghiệm không trở thành tải phá hoại.

### 23.2. Kịch bản kiểm thử

| Kịch bản | Điều cần xác minh |
|---|---|
| Request có deadline thấp trong tải được kiểm soát | Ứng dụng phân loại driver timeout, không coi là missing row |
| App không kết nối được một số coordinators | `AllNodesFailedException` nếu không ứng viên nào thành công; `getAllErrors()` có thông tin node phù hợp |
| TLS truststore sai trong lab | Lỗi connection/handshake được phân loại; không retry vô hạn |
| Không đủ replica cho `LOCAL_QUORUM` | Phân biệt unavailable/server timeout với driver deadline |
| SELECT trả 0 row thành công | `one()==null` nhưng outcome=success, không đếm vào timeout |
| Counter write timeout giả định | Policy không retry mù để tránh cộng trùng |
| LWT timeout sau áp dụng | Reconciliation phân biệt request đầu đã apply với retry condition false |
| Node restart rồi phục hồi | Driver reconnect, error rate giảm; không còn log storm |
| Nhiều caller cùng retry | In-flight, QPS và retry amplification bị giới hạn |
| Async failure wrapper | Handler phân loại cause chính xác, không che exception |

Trong thực tế, chỉ thay timeout rất ngắn **không bảo đảm** tái tạo cùng một exception class ở mọi lần chạy; scheduler, network và server có thể khiến kết quả khác. Test nên kiểm chứng **hành vi phân loại và guardrails**, không phụ thuộc vào việc bắt buộc có đúng một exception type ở một mốc mili giây.

### 23.3. Kiểm thử bảo mật log

Phát request với giá trị UUID/tenant test và xác minh:

- Log ứng dụng chỉ có query template ID, không lộ bind values.
- Metrics labels không chứa raw partition key.
- Per-node failure logs không lưu secret/TLS private material.
- Error storm được sampling/rate-limited.
- Debug traces nếu bật có quyền truy cập và thời gian giữ rõ.

## 24. Câu hỏi luyện tập có đáp án

### Câu 1 — Timeout có rollback không?

Java nhận `DriverTimeoutException` sau `INSERT`. Có thể kết luận mutation không được ghi?

**Đáp án:** Không. Client hết deadline nhưng server/replica có thể đã apply mutation. Phải kiểm chứng outcome và xét idempotency trước retry.

### Câu 2 — Hai entry nghĩa mấy node DOWN?

`AllNodesFailedException.getAllErrors()` chứa node A và B, cluster có sáu node. Có nghĩa cả sáu node đều DOWN?

**Đáp án:** Không. Map chỉ mô tả node/cause mà driver ghi nhận trong query plan; không khảo sát mọi node vật lý.

### Câu 3 — Value của getAllErrors

`Map<Node,List<Throwable>>` cho biết điều gì?

**Đáp án:** Với mỗi coordinator candidate, danh sách các lỗi liên quan quá trình driver thử request. Nó không phải số replica đã ACK.

### Câu 4 — Read timeout server và driver

Coordinator không nhận đủ replica responses cho `LOCAL_QUORUM`, server trả `ReadTimeoutException`. Đây có phải `DriverTimeoutException` không?

**Đáp án:** Không. Lỗi server/coordinator và deadline client là hai tầng khác nhau.

### Câu 5 — Null từ SELECT

`ResultSet.one()==null` sau một SELECT thành công. Đây có phải timeout không?

**Đáp án:** Không. Query thành công nhưng không có row sống khớp điều kiện.

### Câu 6 — TLS

Tất cả coordinator candidates báo handshake error sau cert rotation. Có nên retry vô hạn?

**Đáp án:** Không. Kiểm tra CA/truststore/certificate/hostname, sửa security config.

### Câu 7 — Local DC

App khai báo một local DC sai và nhận `AllNodesFailed`. Có chứng minh data đã mất không?

**Đáp án:** Không. Có thể query plan không có coordinator dùng được; kiểm tra local DC và metadata.

### Câu 8 — Counter

Một lần increment counter timeout, app retry và counter tăng hai lần. Vì sao?

**Đáp án:** Lần đầu có thể đã apply dù response mất; counter increment không idempotent. Cần thiết kế dedup hoặc cách lưu khác.

### Câu 9 — LWT

Lần đầu `INSERT ... IF NOT EXISTS` timeout; retry trả `wasApplied()==false`. Có chắc lần đầu thất bại?

**Đáp án:** Không. Retry có thể thấy row đã được lần đầu tạo; đối soát ID và invariant.

### Câu 10 — Logging

Có nên ghi `device_id` hoặc full CQL với bind values trong nhãn Prometheus?

**Đáp án:** Không. Dùng query ID cố định, loại lỗi, DC và metadata được phép; tránh high cardinality và lộ thông tin.

### Câu 11 — Retry amplification

Gateway 3 attempts, app 3 attempts, driver 2 attempts, không điều phối. Worst-case minh họa là bao nhiêu?

**Đáp án:** `3 × 3 × 2 = 18` attempts cho một logical request. Cần retry budget toàn tuyến.

### Câu 12 — Không đủ quorum

RF=3, chỉ một replica còn available, CL=`LOCAL_QUORUM`. Tăng timeout lên 30 giây bảo đảm thành công không?

**Đáp án:** Không. Quorum cần hai replica; timeout không tạo thêm replica.

### Câu 13 — P99 sau tăng timeout

Tỷ lệ `DriverTimeoutException` giảm nhưng p99 API tăng gấp ba. Có chắc là cải thiện?

**Đáp án:** Không. Hệ thống có thể chỉ giữ request lâu hơn. Phải xét SLO, error budget, in-flight, queue và load.

### Câu 14 — Query invalid

CQL bị từ chối do thiếu điều kiện partition key. Retry cùng statement có giúp?

**Đáp án:** Không. Cần sửa query shape/schema hoặc access path, không retry cú pháp sai.

### Câu 15 — Một node có nhiều lỗi

Per-node error map nhiều request đều có lỗi pool busy ở A. A chắc chắn hỏng phần cứng?

**Đáp án:** Không. Có thể hotspot, quá tải, connection limit, disk, GC hoặc network. Cần kiểm tra toàn bộ bằng chứng.

### Câu 16 — Async wrapper

`join()` ném `CompletionException` bọc `AllNodesFailedException`. Handler nên làm gì?

**Đáp án:** Mở lớp wrapper Future, phân loại cause, dùng `getAllErrors()` và giữ ngữ cảnh trace phù hợp.

### Câu 17 — SELECT retry

SELECT idempotent gặp lỗi network transient. Có thể retry vô hạn nếu caller còn chờ?

**Đáp án:** Không. Cần bounded attempts, backoff, deadline và theo dõi tải; retry nhiều có thể làm nghẽn cluster.

### Câu 18 — Coordinator và replica

`getAllErrors()` cho biết A/B lỗi kết nối. Có thể khẳng định ba replica của một write trước đó chưa ghi mutation?

**Đáp án:** Không. Đây là map coordinator candidates, không phải trạng thái replica hoặc commit log.

## 25. Checklist trước khi đưa Java service vào production

### 25.1. Ứng dụng Java

~~~text
[ ] CqlSession được tái sử dụng, auth/TLS và local DC đúng.
[ ] Java Driver 4.x version, protocol và retry policy được kiểm tra.
[ ] Prepared/bound statements, partition key và CL đúng nghiệp vụ.
[ ] DriverTimeout, AllNodesFailed, Read/WriteTimeout và Unavailable
    có outcome/log/metrics riêng.
[ ] AllNodesFailed được soi getAllErrors() theo node và error class.
[ ] Không xem per-node map là per-replica ACK map.
[ ] Driver timeout nằm trong ngân sách API end-to-end.
[ ] Retry nhiều tầng có tổng budget, backoff và rate limit.
[ ] Idempotency của từng mutation được đánh giá, không gán đại trà.
[ ] LWT, counter, TTL và DELETE có logic outcome/đối soát riêng.
[ ] Async wrappers được mở đúng và lỗi được propagate.
[ ] Error logging không lộ PII, credentials hay raw query values.
[ ] Rate-limit log storm; đo p99, timeout, retry/in-flight.
~~~

### 25.2. Cluster Cassandra

~~~text
[ ] RF, NetworkTopologyStrategy, DC/rack và CL phù hợp SLO.
[ ] nodetool status/topology không có outage chưa đánh giá.
[ ] tpstats Pending/Dropped được đo theo khoảng thời gian.
[ ] compactionstats, memtable flush và commitlog I/O đủ headroom.
[ ] netstats/repair/streaming không gây nghẽn bất thường.
[ ] Storage disk free/read/write latency và CPU/GC ổn định.
[ ] App-to-node TLS/network paths được giám sát.
[ ] Node latency được đối chiếu với coordinator và replica roles.
[ ] Backup/restore, outage và rolling upgrade runbooks rõ ràng.
[ ] Không nâng timeout/concurrency để che lỗi dữ liệu hoặc disk full.
~~~

## 26. Tổng kết

Khi Java Driver báo lỗi, cần phân biệt đúng ba lớp:

1. **`DriverTimeoutException`:** hết request deadline ở driver. Không chứng minh server chưa nhận hay chưa apply mutation.
2. **`AllNodesFailedException`:** không thực thi thành công request qua các coordinator ứng viên; dùng **`getAllErrors()`** để xem lỗi theo node/cause. Không suy toàn cluster DOWN.
3. **`ReadTimeoutException`, `WriteTimeoutException`, `UnavailableException`:** thường đến từ Cassandra server, liên quan replica, CL và khả năng phục vụ.
4. **Node trong map không phải replica ACK:** per-node client error map khác với trạng thái dữ liệu ở replica và commit-log durability.
5. **Retry chỉ an toàn khi hiểu nghiệp vụ**, loại lỗi và deadline; với counter, LWT, TTL hoặc concurrent updates, outcome phải được xác minh.
6. **Chặn retry storm:** bounded attempts, exponential backoff có jitter, rate limit, circuit breaker và backpressure.
7. **Tương quan metrics nhiều tầng:** driver, coordinator, replica, disk/GC, compaction, streaming, network và query shape.
8. **Bảo vệ thông tin:** dùng query ID cố định, error class và node metadata được phép; không ghi raw bind values hoặc secrets.
9. **Dùng runbook theo bằng chứng:** xác định failure scope, khôi phục node/config/query, kiểm chứng p99, error rate và correctness.

Câu hỏi cốt lõi không phải **“gặp timeout thì retry mấy lần?”**, mà là **“deadline nào đã hết, coordinator ứng viên nào thất bại vì nguyên nhân gì, replica có thể đã xử lý mutation tới đâu, và thực hiện lại có phù hợp với tính đúng cùng ngân sách tải của hệ thống không?”**. Trả lời bằng số liệu và invariant nghiệp vụ giúp xử lý lỗi mà không biến một request chậm thành sự cố toàn cluster.
