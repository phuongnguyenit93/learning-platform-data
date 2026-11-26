# Unavailable, read timeout, write timeout và lỗi quá tải trong Spring Data Cassandra

Khi ứng dụng Java truy cập Apache Cassandra qua **Spring Data Cassandra** (repository, `CassandraTemplate` hoặc `ReactiveCassandraTemplate`), một yêu cầu không thành công có thể bắt nguồn từ số lượng replica, thời hạn chờ phản hồi hoặc khả năng xử lý của cụm. Bốn tình huống thường gặp là **`Unavailable`**, **`ReadTimeout`**, **`WriteTimeout`** và **`Overloaded`**. Chúng cần được xử lý khác nhau, nhất là khi ứng dụng định thử lại thao tác ghi.

Bài này tập trung vào cách Cassandra xác định lỗi, cách nhận diện lỗi trong Spring Data, cách quyết định retry và cách chẩn đoán từ góc độ thiết kế dữ liệu phân tán.

## 1. Cơ chế nền tảng: coordinator, replica và consistency level

Với mỗi partition key, Cassandra xác định các **replica** lưu dữ liệu. Một node nhận yêu cầu từ client đóng vai trò **coordinator**, gửi yêu cầu tới replica thích hợp và thu thập phản hồi theo **consistency level (CL)**. Spring Data gọi xuống Java Driver; driver gửi yêu cầu CQL tới coordinator.

~~~mermaid
flowchart LR
    A["Repository / CassandraTemplate"] --> B["Java Driver"]
    B --> C["Coordinator"]
    C --> R1["Replica 1"]
    C --> R2["Replica 2"]
    C --> R3["Replica 3"]
    R1 --> C
    R2 --> C
    R3 --> C
    C --> B
~~~

Ví dụ một keyspace có **replication factor (RF) = 3 trong một datacenter**:

| Consistency level | Số replica phản hồi tối thiểu trong ví dụ | Ý nghĩa thực tế |
| --- | ---: | --- |
| `LOCAL_ONE` | 1 | Chấp nhận phản hồi từ một replica trong datacenter cục bộ. |
| `LOCAL_QUORUM` | 2 | Cần đa số replica trong datacenter cục bộ: `floor(3 / 2) + 1 = 2`. |
| `ALL` | 3 | Cần tất cả replica của partition; dễ giảm khả dụng khi có node lỗi. |

Con số trên chỉ áp dụng cho ví dụ RF = 3 trong **một** datacenter. Trong cụm nhiều datacenter, `LOCAL_QUORUM` tính theo RF của datacenter cục bộ; không được lấy tổng số node trong cụm làm số replica cần thiết.

Có hai câu hỏi khác nhau:

- **Đủ replica đang được coordinator xem là khả dụng không?** Nếu không, yêu cầu có thể thất bại ngay bằng `Unavailable`.
- **Các replica có trả lời kịp thời, đúng loại phản hồi cần thiết không?** Nếu đã đủ replica được xem là khả dụng nhưng phản hồi không đạt yêu cầu trước hạn, có thể phát sinh `ReadTimeout` hoặc `WriteTimeout`.

**CL là yêu cầu về mức độ nhất quán của phép đọc/ghi**, không phải một tham số hiệu năng có thể tự động hạ xuống mỗi khi lỗi. Hạ từ `LOCAL_QUORUM` xuống `LOCAL_ONE` có thể thay đổi cam kết dữ liệu với nghiệp vụ.

## 2. Phân biệt nhanh bốn loại lỗi

| Lỗi | Điều kiện cốt lõi | Điều ứng dụng biết chắc | Hướng xử lý ban đầu |
| --- | --- | --- | --- |
| **`UnavailableException`** | Coordinator thấy số replica sống **ít hơn** số replica mà CL yêu cầu. | Không thể đạt CL tại thời điểm coordinator kiểm tra; yêu cầu bị từ chối trước khi tiến hành thao tác. | Kiểm tra node, RF, datacenter, CL; chỉ retry ngắn hạn khi có cơ sở. |
| **`ReadTimeoutException`** | Yêu cầu đọc đã đến coordinator nhưng chưa có đủ phản hồi hợp lệ trước hạn chờ phía server. | Chưa có kết quả đọc hoàn chỉnh để trả về; không được coi dữ liệu là “không tồn tại”. | Retry giới hạn cho truy vấn đọc an toàn; kiểm tra độ trễ, truy vấn và replica. |
| **`WriteTimeoutException`** | Coordinator không nhận đủ xác nhận ghi theo CL trước hạn chờ phía server. | **Kết quả ghi chưa xác định**: một hoặc nhiều replica có thể đã ghi thành công. | Tránh retry mù; dùng khóa thao tác/idempotency và đối soát kết quả. |
| **`OverloadedException`** | Coordinator báo không đủ khả năng nhận/xử lý thêm yêu cầu. | Yêu cầu bị từ chối do quá tải ở coordinator; cần xem cả khả năng các node khác cũng quá tải. | Backoff có jitter, giới hạn đồng thời, giảm áp lực và xử lý nút thắt. |

Tên lớp Java Driver 4.x thuộc package `com.datastax.oss.driver.api.core.servererrors`. Trong Spring Data, lớp truy cập dữ liệu có thể **dịch/wrap** exception của driver thành một `DataAccessException` của Spring; khi xử lý cần kiểm tra cả chuỗi nguyên nhân, không chỉ tên lớp exception ngoài cùng.

### `UnavailableException`: chưa đủ replica đáp ứng CL

Giả sử RF = 3, truy vấn `LOCAL_QUORUM` cần hai replica. Nếu coordinator chỉ thấy **một** replica khả dụng, nó không thể đáp ứng yêu cầu và trả `Unavailable`. Các thông tin thường dùng:

- `getRequired()`: số replica cần để đáp ứng CL.
- `getAlive()`: số replica được coordinator xem là đang sống.
- `getConsistencyLevel()`: CL của yêu cầu.

Điểm quan trọng: `Unavailable` **không có nghĩa mọi node Cassandra đều chết**. Có thể chỉ nhóm replica sở hữu partition bị ảnh hưởng, một datacenter gặp sự cố, gossip chưa hội tụ hoặc coordinator có góc nhìn trạng thái chưa cập nhật. Thử sang coordinator khác đôi khi hữu ích, nhưng lặp đi lặp lại cùng một truy vấn khi vẫn thiếu replica không giải quyết nguyên nhân.

Nếu tình huống lặp lại, kiểm tra `nodetool status`, replication strategy, các node thuộc replica set, vấn đề mạng/gossip và CL được cấu hình trên client. Không đổi CL để “cho chạy qua” khi chưa chấp nhận rõ hệ quả nhất quán.

### `ReadTimeoutException`: replica có thể sống nhưng trả lời chậm

Coordinator cho rằng có đủ replica để bắt đầu đọc. Tuy nhiên, trước hạn chờ đọc của server, coordinator không tổng hợp đủ thông tin cần thiết để trả kết quả. Ví dụ RF = 3, `LOCAL_QUORUM` cần hai phản hồi nhưng mới nhận một phản hồi hợp lệ đúng hạn.

Thông tin chẩn đoán:

- `getReceived()` và `getBlockFor()`: số phản hồi đã nhận và số cần thiết.
- `wasDataPresent()`: đã có phản hồi chứa **dữ liệu thực** hay mới nhận dạng phản hồi khác, chẳng hạn digest. Trường hợp `received >= blockFor` vẫn có thể timeout nếu thiếu phản hồi chứa dữ liệu cần thiết.
- `getConsistencyLevel()`: CL được yêu cầu.

Nguyên nhân thường gặp gồm partition quá lớn, nhiều tombstone, truy vấn đọc rộng, disk I/O chậm, compaction hoặc GC gây dừng dài, node quá tải và mạng giữa replica/coordinator có độ trễ cao.

Một lỗi đọc **không tương đương kết quả rỗng**. Ví dụ tìm đơn hàng theo `order_id` bị timeout thì không được chuyển thành HTTP `404 Not Found` hoặc lưu cache rằng đơn hàng không tồn tại. Nếu đọc theo trang, chỉ retry trang chưa nhận thành công; không bỏ qua trang đó rồi tiếp tục với trạng thái phân trang kế tiếp.

### `WriteTimeoutException`: ghi có thể đã xảy ra

Đối với phép ghi, coordinator chuyển mutation tới các replica nhưng không nhận đủ xác nhận theo CL trước hạn chờ. Ví dụ `LOCAL_QUORUM` cần hai acknowledgment, mới nhận một thì coordinator trả `WriteTimeout`. Replica thứ hai có thể đã ghi nhưng phản hồi bị trễ, hoặc có thể ghi sau khi timeout đã được báo về client.

Cassandra **không rollback toàn bộ mutation chỉ vì client nhận `WriteTimeout`**. Do đó:

~~~text
Client gửi ghi -> replica A áp dụng thành công -> client nhận WriteTimeout
                                         \
                                          -> replica B có thể áp dụng sau đó
~~~

Đặc biệt thận trọng với các thao tác:

- Tăng `counter`, thêm phần tử vào `list`, cập nhật theo trạng thái hiện tại.
- Ghi có `TTL`/timestamp tự phát sinh, nơi thực thi lại có thể thay đổi thời điểm hết hạn hoặc thứ tự thắng/thua của giá trị.
- `INSERT ... IF NOT EXISTS`/lightweight transaction (LWT): retry có thể nhận `[applied] = false` dù lần đầu đã thành công; phải đối chiếu theo định danh nghiệp vụ.
- Gọi thêm dịch vụ bên ngoài sau khi ghi: một lần retry API có thể gây **tác dụng phụ trùng lặp** ngoài Cassandra.

Java Driver còn cung cấp `getWriteType()` để phân biệt loại ghi, ví dụ `SIMPLE`, `BATCH`, `BATCH_LOG`, `COUNTER`, `CAS`. Việc diễn giải và quyết định retry cần xét loại ghi, không chỉ tên exception.

**Ví dụ nghiệp vụ:** API tạo đơn hàng dùng một `orderId` do client sinh trước và lưu cùng `requestId` duy nhất. Nếu ghi timeout, server trả trạng thái chưa xác định hoặc khởi động quy trình đối soát theo `requestId`. Yêu cầu thử lại phải sử dụng **cùng định danh**, được thiết kế chống tạo hai đơn hàng. Việc đọc lại ngay cũng có thể gặp dữ liệu cũ tùy CL và tình trạng replica; chỉ coi kết quả đối soát là cuối cùng khi đã đáp ứng điều kiện nhất quán của nghiệp vụ.

### `OverloadedException`: coordinator từ chối vì quá tải

`Overloaded` là phản hồi lỗi từ **server/coordinator**. Nó khác với:

- `DriverTimeoutException`: hạn chờ ở **phía client/driver** đã hết; không nhất thiết Cassandra trả về lỗi timeout phía server.
- `RequestThrottlingException` hoặc `NodeUnavailableException`: driver không thể/không cho phép thực thi yêu cầu trong tình huống giới hạn nội bộ hoặc không còn kết nối khả dụng.
- `ReadFailureException`/`WriteFailureException`: lỗi xử lý phía server không thuộc nhóm timeout.

Một ứng dụng tăng số luồng retry sau `Overloaded` có thể làm quá tải trầm trọng hơn. Cần kết hợp **bounded concurrency**, giới hạn số yêu cầu đang chờ, backoff tăng dần kèm jitter và cơ chế từ chối sớm khi đã quá tải. Nếu nhiều partition bị dồn vào cùng một replica, xử lý **hot partition** và phân bố tải mới là giải pháp gốc.

## 3. Phân loại lỗi trong Spring Data Cassandra

Ví dụ sau dùng Spring Data Cassandra với Java Driver 4.x. Dù gọi `CassandraRepository` hay `CassandraTemplate`, code ở biên dịch vụ nên quan sát `DataAccessException` và lần theo nguyên nhân gốc. `AllNodesFailedException` của driver có thể lưu **nhiều lỗi theo từng coordinator** trong `getAllErrors()`; chỉ duyệt `getCause()` sẽ bỏ sót tình huống đó.

~~~java
import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.servererrors.OverloadedException;
import com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.UnavailableException;
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;

import java.util.ArrayDeque;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Queue;
import java.util.Set;

enum CassandraFailureKind {
    UNAVAILABLE, READ_TIMEOUT, WRITE_TIMEOUT, OVERLOADED, OTHER
}

final class CassandraFailureClassifier {
    private CassandraFailureClassifier() {}

    static CassandraFailureKind classify(Throwable root) {
        Queue<Throwable> pending = new ArrayDeque<>();
        Set<Throwable> visited =
            Collections.newSetFromMap(new IdentityHashMap<>());
        pending.add(root);

        while (!pending.isEmpty()) {
            Throwable error = pending.remove();
            if (!visited.add(error)) {
                continue;
            }
            if (error instanceof UnavailableException) {
                return CassandraFailureKind.UNAVAILABLE;
            }
            if (error instanceof ReadTimeoutException) {
                return CassandraFailureKind.READ_TIMEOUT;
            }
            if (error instanceof WriteTimeoutException) {
                return CassandraFailureKind.WRITE_TIMEOUT;
            }
            if (error instanceof OverloadedException) {
                return CassandraFailureKind.OVERLOADED;
            }

            if (error instanceof AllNodesFailedException allNodes) {
                allNodes.getAllErrors().values()
                    .forEach(errors -> errors.forEach(pending::add));
            }
            if (error.getCause() != null) {
                pending.add(error.getCause());
            }
            for (Throwable suppressed : error.getSuppressed()) {
                pending.add(suppressed);
            }
        }
        return CassandraFailureKind.OTHER;
    }
}
~~~

Đây là bộ phân loại **phục vụ quan sát và điều hướng xử lý**, chưa phải một retry policy. Nếu `AllNodesFailedException` chứa nhiều nguyên nhân khác nhau, đoạn mã trả về loại lỗi đầu tiên nó gặp; trong hệ thống thực tế nên ghi nhận **tập nguyên nhân theo coordinator** để không đánh mất thông tin.

Ví dụ ánh xạ entity và đọc bằng `CassandraTemplate`:

~~~java
import java.util.Optional;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;
import org.springframework.stereotype.Service;

@Table("orders_by_id")
class OrderById {
    @PrimaryKey("order_id")
    UUID orderId;
    String state;
}

@Service
public class OrderReadService {
    private static final Logger log =
        LoggerFactory.getLogger(OrderReadService.class);
    private final CassandraTemplate template;

    public OrderReadService(CassandraTemplate template) {
        this.template = template;
    }

    public Optional<OrderById> find(UUID orderId) {
        try {
            return Optional.ofNullable(
                template.selectOneById(orderId, OrderById.class));
        } catch (DataAccessException ex) {
            CassandraFailureKind kind =
                CassandraFailureClassifier.classify(ex);
            log.warn("Cassandra read failed: type={}, table=orders_by_id",
                kind, ex);
            throw ex; // Để tầng API áp dụng chính sách lỗi thống nhất.
        }
    }
}
~~~

Giả sử ứng dụng kết nối đến keyspace chứa bảng `orders_by_id`, có `order_id` làm partition key. Cách lấy bằng khóa chính tương ứng với cách thiết kế bảng theo truy vấn; không dùng `ALLOW FILTERING` hoặc scan toàn bảng để tìm một bản ghi.

**Lưu ý:** Trong một số đường thực thi, driver có thể ném exception trực tiếp hoặc bọc nhiều lớp; ví dụ trên bắt `DataAccessException` tại biên Spring Data. Nếu sử dụng `CqlSession` trực tiếp, phải xử lý các exception driver tương ứng. Với luồng reactive, lỗi thường xuất hiện ở tín hiệu `onError` khi subscriber thực sự đăng ký; nên phân loại trong `onErrorMap`/`doOnError` và tránh retry toàn bộ chuỗi một cách vô điều kiện.

## 4. Quyết định retry theo tính chất thao tác

Không phải mọi lỗi tạm thời đều an toàn để thực thi lại. **Idempotent** nghĩa là thực hiện cùng thao tác nhiều lần có hiệu ứng nghiệp vụ tương đương một lần. Đối với Cassandra, cần kiểm tra cả mutation, TTL, timestamp, counter và tác dụng phụ bên ngoài.

| Tình huống | Có thể retry không? | Điều kiện và giới hạn |
| --- | --- | --- |
| `Unavailable` khi đọc | Có thể, có giới hạn. | Chỉ khi còn thời gian trong deadline; thử coordinator khác có thể hữu ích nếu trạng thái node nhìn nhận khác nhau. |
| `ReadTimeout` | Thường có thể. | Đọc không gây tác dụng phụ; giới hạn số lần, dùng backoff và theo dõi latency. |
| `WriteTimeout` với mutation không idempotent | **Không tự động retry.** | Xử lý trạng thái chưa xác định; tra cứu/đối soát theo định danh thao tác. |
| `WriteTimeout` với mutation đã thiết kế idempotent | Có điều kiện. | Đảm bảo key, giá trị, timestamp/TTL và tác dụng phụ đủ ổn định; vẫn giới hạn retry. |
| `Overloaded` | Có thể sau khi giảm áp lực. | Backoff có jitter và giới hạn đồng thời; không tạo vòng retry dồn dập. |
| `ReadFailure`/`WriteFailure` hoặc lỗi CQL không hợp lệ | Không coi là timeout thường gặp. | Tìm nguyên nhân cụ thể; lỗi schema/cú pháp/quyền truy cập cần sửa, không retry mù. |

Java Driver đã có cơ chế retry của riêng nó. Một số loại yêu cầu chỉ được driver retry khi statement đánh dấu **idempotent**; driver còn có quy tắc đặc biệt theo loại lỗi và retry policy. Nếu ứng dụng thêm retry tại service hoặc HTTP client, phải tính **tổng số lượt thử qua mọi tầng**. Chẳng hạn 3 lần ở HTTP × 2 lần ở service × 2 lần ở driver có thể tạo tới 12 lượt trong trường hợp xấu.

Ví dụ chỉ đánh dấu truy vấn **đọc** là idempotent ở tầng driver:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.time.Duration;
import java.util.UUID;

SimpleStatement readById = SimpleStatement.builder(
        "SELECT state FROM orders_by_id WHERE order_id = ?")
    .addPositionalValue(UUID.fromString("31b63cc4-d1d8-4762-81df-4db4c1571ceb"))
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setIdempotent(true)
    .setTimeout(Duration.ofSeconds(2))
    .build();
// Ví dụ này dành cho CqlSession trực tiếp; entity/repository vẫn do Spring Data quản lý.
~~~

Hạn chờ ở driver (`setTimeout` hoặc cấu hình `basic.request.timeout`), hạn chờ tại coordinator (trong `cassandra.yaml`) và deadline HTTP là **các lớp khác nhau**. Điều chỉnh chúng phải dựa trên SLO/độ trễ thực tế. Tăng timeout đơn thuần thường chỉ khiến nhiều yêu cầu chiếm tài nguyên lâu hơn khi cluster đã quá tải.

Khi phát hiện lỗi, một chính sách API khả thi là:

1. Với **đọc** bị `Unavailable`/`Overloaded`: trả HTTP `503 Service Unavailable` nếu hết ngân sách retry; với timeout trả `503` hoặc `504` theo quy ước API, kèm `requestId` để tra cứu.
2. Với **ghi** bị `WriteTimeout`: không công bố ghi thành công; trả kết quả “chưa xác định/đang đối soát” theo hợp đồng API và cung cấp `operationId` hoặc `idempotencyKey` để client kiểm tra/truy vấn lại.
3. Với lỗi nghiệp vụ như không tìm thấy dữ liệu sau **một phép đọc thành công**, mới cân nhắc `404`. Không chuyển lỗi Cassandra thành “không tìm thấy”.

Không bắt mọi `DataAccessException` rồi trả mã `200`, không nuốt lỗi thành `Optional.empty()` và không trả cả CQL/bind values nhạy cảm trong HTTP error body.

## 5. Chẩn đoán theo dấu hiệu thay vì tăng timeout

Khi một trong bốn nhóm lỗi tăng đột biến, hãy thu thập đồng thời bối cảnh **request**, **cluster** và **data model**.

| Nguồn quan sát | Dữ liệu nên xem | Gợi ý tìm nguyên nhân |
| --- | --- | --- |
| Client/Spring | Tên thao tác, keyspace/table, CL, loại exception, thời gian chờ, số lần retry, trace/request ID. | Nhận biết một API bị ảnh hưởng hay tất cả; phát hiện retry khuếch đại lỗi. |
| Driver | Coordinator đã thử, connection pool, queue/throttling, timeout, kết quả `AllNodesFailedException.getAllErrors()`. | Phân biệt lỗi từng node với lỗi toàn cụm; phân biệt server timeout và client timeout. |
| Cassandra | `nodetool status`, `nodetool tpstats`, `nodetool tablestats`, `nodetool compactionstats`; latency, dropped messages, pending tasks, disk, CPU, GC. | Tìm replica xuống, queue quá dài, compaction, áp lực I/O hoặc tài nguyên. |
| Thiết kế bảng/truy vấn | Kích thước partition, phân phối partition key, tombstone, paging size, truy vấn theo khóa, pattern ghi. | Phát hiện hot partition, partition lớn, quét dữ liệu quá rộng và read amplification. |

Ví dụ dùng các lệnh **chỉ quan sát** trên node Cassandra mà người vận hành có quyền:

~~~bash
nodetool status
nodetool tpstats
nodetool tablestats
nodetool compactionstats
~~~

Không chỉ nhìn CPU trung bình: chỉ một nhóm partition/replica quá nóng cũng có thể gây timeout trong khi các node khác rảnh. Với truy vấn CQL, nên ưu tiên truy cập đúng partition key, phân trang hợp lý, tránh partition quá lớn và chủ động kiểm soát tombstone. Khi log ở ứng dụng, hạn chế ghi raw partition key, thông tin người dùng hoặc câu CQL có dữ liệu nhạy cảm; có thể dùng tên truy vấn và hash định danh đã kiểm soát.

Quy trình điều tra gợi ý:

1. **Xác định loại lỗi:** `Unavailable`, server timeout, driver timeout hay `Overloaded`; xem có bị bọc bởi `AllNodesFailedException` không.
2. **Xác định phạm vi:** một table/partition key, một datacenter, một nhóm coordinator hay toàn bộ traffic.
3. **So CL và RF:** với `Unavailable`, đối chiếu `alive/required`; với timeout đối chiếu `received/blockFor` và `dataPresent`/`writeType`.
4. **Quan sát tải và truy vấn:** latency p95/p99, queue, tombstone, compaction, GC, kết nối và retry rate.
5. **Khắc phục nguyên nhân:** khôi phục replica/mạng, giảm concurrency, thiết kế lại hot partition/truy vấn hoặc phân phối tải; sau đó kiểm tra lại tần suất lỗi.

## 6. Tình huống thực hành

**Bối cảnh:** hệ thống quản lý đơn hàng sử dụng bảng `orders_by_id(order_id PRIMARY KEY, state, ...)`, RF = 3 trong một datacenter. API đọc/ghi ở `LOCAL_QUORUM`.

| Sự kiện mô phỏng trong môi trường thử nghiệm | Lỗi dự kiến | Quyết định đúng |
| --- | --- | --- |
| Hai replica chứa partition đồng thời không khả dụng. | `Unavailable` (`alive=1`, `required=2`). | Báo dịch vụ tạm thời không khả dụng; kiểm tra replica và kết nối, không tự hạ CL. |
| Replica còn sống nhưng đọc partition nhiều tombstone quá chậm. | `ReadTimeout`. | Không trả 404; đo latency và truy vấn, cân nhắc retry đọc với ngân sách nhỏ. |
| Một replica xác nhận ghi, replica thứ hai phản hồi muộn. | `WriteTimeout` (`received=1`, `blockFor=2`). | Trạng thái ghi chưa xác định; dùng `operationId` để đối soát, tránh tạo đơn trùng. |
| Bùng nổ traffic vào cùng partition và coordinator từ chối. | `Overloaded`. | Giảm đồng thời, thêm backoff/jitter; sửa phân phối partition key nếu là nút thắt. |

Trong bài kiểm thử tích hợp có fault injection, nên khẳng định bằng **kết quả quan sát**, không chỉ bằng tên exception: client có bị nhân đôi tác dụng ghi không, timeout có bị biến thành 404 không, retry có vượt deadline không, và sau khi node phục hồi hệ thống có trở về độ trễ bình thường không. Kiểm thử gây mất node hoặc tạo tải lớn chỉ thực hiện ở môi trường được phép và cách ly.

## 7. Ghi nhớ

- `Unavailable`: chưa đủ **replica được xem là sống** cho consistency level.
- `ReadTimeout`: đọc **chưa đủ phản hồi hữu ích đúng hạn**, nên chưa có kết quả; tuyệt đối không suy ra “không tìm thấy”.
- `WriteTimeout`: **không đủ acknowledgment đúng hạn**, nhưng mutation có thể đã áp dụng; coi kết quả là chưa xác định.
- `Overloaded`: coordinator báo **quá tải**; tăng retry có thể làm sự cố nặng hơn.
- Spring Data có thể bọc lỗi trong `DataAccessException`. Quan sát nguyên nhân driver, CL và dữ liệu theo coordinator; thiết kế retry dựa trên **idempotency, deadline, backoff và số lần thử hữu hạn**.

### Tài liệu tham khảo

- [Apache Cassandra — Native Protocol: error codes và trường chẩn đoán](https://cassandra.apache.org/doc/stable/cassandra/reference/native-protocol.html).
- [Apache Cassandra — Finding misbehaving nodes và các loại timeout](https://cassandra.apache.org/doc/latest/cassandra/troubleshooting/finding_nodes.html).
- [Java Driver 4.x — Retry policies](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/retries/).
- [Apache Cassandra Java Driver — Query idempotence](https://github.com/apache/cassandra-java-driver/blob/trunk/manual/core/idempotence/README.md).
- [Spring Data Cassandra — Reference Documentation](https://docs.spring.io/spring-data/cassandra/reference/).
