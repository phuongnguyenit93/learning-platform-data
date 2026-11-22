# Phối hợp timeout, retry và phản hồi áp lực tải

> **Chương:** Bất đồng bộ và reactive  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Phạm vi:** Apache Cassandra, kiến trúc phân tán wide-column, partition key, bảng thiết kế theo truy vấn, consistency level đọc/ghi, CQL, replication, compaction, repair, xử lý sự cố và Java Driver.

## 1. Vấn đề: ba cơ chế tốt có thể kết hợp thành một sự cố

Một dịch vụ Java dùng **executeAsync** để đọc dữ liệu Cassandra. Bình thường, mỗi truy vấn hoàn tất sau vài chục mili giây. Khi một số replica chậm do compaction và disk I/O, thời gian phản hồi tăng. Ứng dụng phản ứng bằng cách tăng timeout và retry nhiều lần; đồng thời luồng reactive tiếp tục nhận thêm request từ HTTP. Kết quả: hàng đợi lớn, request đang bay tăng, retry tiếp tục gây tải, rồi Cassandra báo **Overloaded**, **ReadTimeout** hoặc **Unavailable**.

Cùng một tình huống có ba loại điều khiển khác nhau:

- **Timeout/deadline:** một thao tác được phép chiếm bao nhiêu thời gian trước khi caller không còn cần kết quả?
- **Retry:** có nên thử lại sau lỗi và thử bao nhiêu lần, với điều kiện nào để không làm sai dữ liệu?
- **Backpressure/admission:** hệ thống cho phép bao nhiêu request đồng thời hoặc bao nhiêu row được downstream yêu cầu/tiếp nhận?

Nếu điều chỉnh riêng từng yếu tố, ứng dụng có thể trông như “ít timeout hơn” nhưng thực tế **p99 cao hơn, nhiều request tồn đọng hơn và Cassandra quá tải nặng hơn**.

### Kết quả học tập

Sau bài học, bạn cần:

1. Phân biệt timeout **của caller, driver, Cassandra server và từng lần fetch page**.
2. Thiết kế **deadline end-to-end** và ngân sách retry bao gồm cả hàng đợi, backoff và thời gian xử lý downstream.
3. Phân loại các lỗi Cassandra để chỉ retry thao tác **an toàn/idempotent** và không tạo retry storm khi quá tải.
4. Dùng **CompletionStage**, scheduled retry không chặn thread và giới hạn **in-flight** ở Java.
5. Hiểu **Reactive Streams demand**, cách giữ backpressure xuyên pipeline và sự khác biệt với chỉ dùng API bất đồng bộ.
6. Tích hợp phân trang, consistency level, partition key, metrics và runbook vận hành cho các lỗi dưới tải.

> **Quy tắc an toàn:** Một timeout ở Java **không chứng minh ghi chưa được áp dụng** tại Cassandra. Một thao tác hủy future **không tự hoàn tác công việc đã gửi cho server**. Phải thiết kế idempotency và cơ chế đối soát đúng nghiệp vụ.

## 2. Ba đồng hồ và một bộ giới hạn tải

Hãy nhìn toàn bộ đường đi:

~~~mermaid
flowchart LR
    U["Caller HTTP/gRPC\nDeadline"] --> A["Java API\nAdmission/queue"]
    A --> D["Java Driver\nRequest timeout"]
    D --> C["Cassandra coordinator\nTimeout xử lý"]
    C --> R["Replica\nDisk/GC/compaction"]
    R --> C
    C --> D
    D --> A
    A --> U
    A --> B["Downstream processing\nCompletionStage / reactive demand"]
~~~

Trong thực tế có **nhiều hơn ba timeout**. Tên cụ thể tùy API/driver/version, nhưng có thể chia thành những lớp:

| Lớp | Bắt đầu/kết thúc | Ai quyết định? | Khi hết hạn, điều gì có thể xảy ra? |
|---|---|---|---|
| **Caller deadline** | Từ khi API nhận yêu cầu đến khi người gọi không còn chờ | HTTP/gRPC/API nghiệp vụ | Caller ngừng chờ; Java phải ngừng làm việc không còn hữu ích |
| **Admission/queue wait** | Từ lúc xin permit đến khi được gửi xuống driver | Java service | Có thể bị từ chối vì không đủ slot, không nên chờ queue vô hạn |
| **Driver request timeout** | Theo phạm vi request mà driver cấu hình | Java Driver | Client nhận timeout; coordinator có thể đã xử lý hoặc còn xử lý |
| **Server read/write timeout** | Khi Cassandra điều phối đọc/ghi và đợi replica | Cassandra coordinator/server | Có thể báo ReadTimeout/WriteTimeout; trạng thái ghi không chắc chắn |
| **Per-page fetch** | Từ lúc gọi fetchNextPage đến lúc trang trả về hoặc lỗi | Driver + Cassandra | Chuỗi phân trang có thể dừng giữa chừng |
| **Downstream deadline** | Khi chuyển row sang hệ khác hoặc xử lý CPU | Pipeline/consumer | Xử lý trang hoàn tất muộn, phát sinh backlog nếu vẫn fetch tiếp |
| **Retry/backoff** | Sau lần thất bại và trước lần thử kế | Chính sách driver hoặc Java | Tiêu tốn thời gian còn lại, có thể nhân số request thực |

**Timeout != deadline.** Ví dụ một request có driver timeout 1 giây, retry ba lần và hai khoảng backoff mỗi khoảng 300 ms. Tổng thời gian có thể vượt 3 giây cộng hàng đợi và xử lý downstream, dù từng attempt đều “chỉ 1 giây”.

### 2.1. Ngân sách thời gian phải được phân bổ

Đặt:

~~~text
Tổng thời gian một logical request
  = thời gian đợi admission
  + tổng thời gian các attempt tới Cassandra
  + tổng backoff
  + thời gian xử lý page và downstream
  + thời gian serialize/trả kết quả

Phải nhỏ hơn hoặc bằng deadline nghiệp vụ,
với khoảng dự phòng cho network/cleanup.
~~~

Ví dụ **giả định**:

| Thành phần | Ngân sách |
|---|---:|
| HTTP deadline | 2.000 ms |
| Admission tối đa | 100 ms |
| Xử lý CQL và các lần thử | 1.400 ms |
| Backoff nếu có | 200 ms |
| Xử lý kết quả + HTTP response | 200 ms |
| Dự phòng | 100 ms |

Đây là **phân bổ minh họa**, không phải cấu hình Cassandra mặc định. Tổng ngân sách phải xét độ trễ thực tế và SLO. Nếu một lần thử đã hết 1.300 ms, việc bắt đầu retry 1.400 ms khác thường không còn hợp lý với deadline 2 giây.

### 2.2. Đo thời gian đúng cách

- Ghi timestamp UTC để đối chiếu sự kiện giữa app, coordinator và replica.
- Với **thời lượng**, nên dùng **System.nanoTime()** hoặc đồng hồ monotonic của telemetry; không dùng cách trừ hai **currentTimeMillis()** khi đồng hồ có thể điều chỉnh.
- Theo dõi **độ trễ tổng** từ đầu API và **độ trễ từng attempt** riêng biệt.
- Tính cả thời gian chờ permit và xử lý các trang; không chỉ đo lúc **executeAsync** trả trang đầu.

## 3. Phân biệt các nhóm lỗi trước khi quyết định retry

Trong Java Driver 4.x, thông tin thất bại có thể được đưa qua **CompletionStage hoàn thành exceptionally**. Đừng xử lý mọi exception như một lỗi mạng có thể retry.

| Loại tín hiệu | Ý nghĩa cần nhớ | Xử lý ban đầu |
|---|---|---|
| **ReadTimeoutException** | Không đủ phản hồi đọc trước timeout của server | Xem replica, CL, partition, tombstone, tải; retry có giới hạn nếu đọc idempotent |
| **ReadFailureException** | Có thông báo xử lý đọc thất bại | Xem server log/đường đọc; retry mù dễ che lỗi hệ thống |
| **WriteTimeoutException** | Không đủ phản hồi ghi theo CL trước timeout | **Outcome có thể không rõ**; chỉ retry nếu chứng minh an toàn |
| **WriteFailureException** | Xử lý ghi thất bại theo phản hồi server | Một phần replica có thể đã ghi; cần chính sách nghiệp vụ |
| **UnavailableException** | Không đủ replica được đánh giá là khả dụng theo CL | Kiểm tra RF/DC/health; retry ngay thường không tạo thêm replica |
| **OverloadedException** | Server báo không đủ năng lực nhận/xử lý lượng công việc hiện tại | Giảm tốc, backpressure/load shedding; tránh retry tức thì |
| **Driver-side timeout** | Driver/caller chờ quá thời gian cấu hình, có thể chưa có server response | Kiểm tra driver/connection/queue; không đoán server chưa làm gì |
| **Auth/TLS/Codec/CQL syntax** | Cấu hình, quyền hoặc code sai | Sửa nguyên nhân; không retry theo vòng lặp |
| **Client admission rejection** | Java service từ chối trước khi gửi do hết permit | Giảm tải/đưa tín hiệu cho caller; không nhầm với Overloaded từ server |

Tên exception/phạm vi từng lớp phải đối chiếu với phiên bản driver/server thực tế. **ReadFailure != ReadTimeout** và **WriteFailure != WriteTimeout**; dù có thể cùng xuất hiện trong một sự cố, cách chẩn đoán không giống nhau.

### 3.1. Những outcome không rõ

Nếu client thấy **WriteTimeout** sau khi coordinator gửi mutation, một số replica vẫn có thể đã áp dụng ghi. Việc retry:

- Một **INSERT cùng primary key và cùng giá trị cố định** thường dễ chứng minh idempotent hơn.
- **Counter increment**, **list append**, thao tác dùng TTL/timestamp không nhất quán hoặc tạo event ID mới ở mỗi lần thử có thể không idempotent.
- Một **LWT IF NOT EXISTS** bị timeout có thể đã thành công; lần retry nhận **[applied] = false** không chứng minh lần đầu thất bại.
- Ghi sang Cassandra và gửi email/thu tiền ở hệ khác không trở thành exactly-once chỉ nhờ CQL idempotent.

**Quy tắc:** Xác định idempotency ở **cấp nghiệp vụ và dữ liệu** trước khi cho driver hoặc application retry. Gọi **statement.setIdempotent(true)** chỉ là khai báo cho driver, không biến thao tác không an toàn thành an toàn.

### 3.2. Vì sao quá tải cần phản ứng ngược chiều?

Khi server báo **Overloaded**, gửi lại cùng request ngay lập tức có thể:

1. Tăng số request in-flight.
2. Làm queue/GC/disk/compaction chậm hơn.
3. Kéo dài độ trễ, gây timeout cho nhiều request khác.
4. Kích hoạt thêm retry từ các client khác.
5. Dẫn đến **retry amplification** hoặc **retry storm**.

Một chính sách tốt có thể **từ chối có kiểm soát**, giảm concurrency, chặn nhóm request ít ưu tiên, áp backoff có jitter hoặc mở circuit breaker; nếu không còn năng lực thực hiện trong deadline, **trả lỗi sớm** thường tốt hơn giữ hàng đợi vô hạn.

## 4. Không có một consistency level thay thế được quản lý tải

Cassandra chọn replica từ **partition key** và replication strategy. CL quyết định điều kiện phản hồi cho request.

Giả sử keyspace RF = 3 trong **dc1**:

| CL | Điều kiện khái quát | Đánh đổi |
|---|---|---|
| **LOCAL_ONE** | Một replica tại local DC | Nhẹ hơn, có thể đọc dữ liệu ít cập nhật hơn |
| **LOCAL_QUORUM** | Đa số replica local, thường 2/3 | Nhiều phản hồi hơn, đòi hỏi đủ replica khỏe |
| **ALL** | Tất cả replica được tính | Nhạy cảm với một replica hỏng/chậm |

Với **LOCAL_QUORUM**, một node lỗi vẫn có thể phục vụ khi hai replica còn lại khỏe. Nhưng nếu một node còn lại bị quá tải, CL có thể timeout. **Hạ LOCAL_QUORUM xuống LOCAL_ONE để giảm error rate** là một thay đổi cam kết nhất quán; không được áp dụng ngầm trong retry policy.

Cần xem:

- **RF và topology thực tế:** có đủ replica ở DC mà driver xem là local không?
- **Query shape:** statement có đủ partition key hay đang quét nhiều partition?
- **Hot partition:** một tenant hoặc time bucket có dồn tải vào ít replica không?
- **Compaction/repair:** I/O, network, GC hoặc tombstone làm replica phản hồi chậm?
- **Payload/mutation:** batch quá lớn, collection tăng vô hạn hoặc nhiều SSTable không?

Tăng timeout, tăng page size hoặc đổi CL không làm một partition lớn biến thành nhiều partition nhỏ. Mô hình dữ liệu theo truy vấn vẫn là nền tảng.

## 5. Reactive backpressure khác timeout và retry

**Asynchronous** nghĩa là không cần chặn thread để đợi I/O. Nó **không tự giới hạn** số yêu cầu có thể được khởi tạo.

**Reactive Streams** thêm một hợp đồng giữa **Publisher** và **Subscriber**: subscriber phát tín hiệu **request(n)** để bày tỏ nhu cầu; publisher không nên gửi vượt nhu cầu chưa được đáp ứng. Nhưng demand chỉ hữu ích khi toàn bộ pipeline không phá vỡ nó bằng buffer/queue không giới hạn.

~~~mermaid
sequenceDiagram
    participant H as HTTP / Subscriber
    participant J as Java reactive pipeline
    participant D as Cassandra Driver
    participant C as Cassandra
    H->>J: request(1)
    J->>D: Có nhu cầu nhận thêm kết quả
    D->>C: Fetch dữ liệu khi cần
    C-->>D: Dữ liệu / trang
    D-->>J: onNext(row)
    J-->>H: Xử lý một row
    H->>J: request(1) tiếp khi sẵn sàng
~~~

Sơ đồ biểu thị **nguyên tắc demand**, không khẳng định từng **request(1)** luôn tương ứng chính xác một network round-trip đến Cassandra: driver có thể fetch theo page và giữ row tạm theo cơ chế triển khai.

| Cơ chế | Điều khiển điều gì? | Không làm được |
|---|---|---|
| **Timeout** | Mỗi request/stage được phép chờ bao lâu | Không tự giảm concurrency nguồn tải |
| **Retry** | Có thử lại sau lỗi hay không | Không sửa schema, replica lỗi hoặc server quá tải |
| **Backpressure** | Tốc độ chuyển dữ liệu theo nhu cầu của downstream | Không tự thay đổi deadline, idempotency hoặc RF |
| **Admission limit** | Bao nhiêu logical operations được phép bắt đầu/còn hoạt động | Không tự bảo đảm kết quả đúng |
| **Rate limit** | Số request/byte/đơn vị công việc trong một khoảng thời gian | Không trực tiếp giới hạn toàn bộ memory nếu queue vẫn vô hạn |
| **Circuit breaker** | Tạm từ chối đường gọi thường lỗi để bảo vệ hệ thống | Không thay thế khắc phục server/data model |

Cần **phối hợp**, không lựa chọn một cơ chế rồi bỏ các cơ chế khác.

## 6. CQL lab: hai loại thao tác có chính sách khác nhau

Để kiểm tra, tạo một bảng sự kiện và một bảng trạng thái đơn hàng. Chỉ dùng môi trường được phép thử nghiệm:

~~~sql
-- dc1 / RF = 3 chỉ phù hợp khi cluster có topology đủ replica.
CREATE KEYSPACE IF NOT EXISTS async_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS async_lab.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    happened_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), happened_at, event_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, event_id ASC);

CREATE TABLE IF NOT EXISTS async_lab.orders_by_id (
    tenant_id uuid,
    order_id uuid,
    status text,
    created_at timestamp,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

Trong đó:

- **events_by_tenant_day** phục vụ việc đọc event trong một partition **(tenant_id, event_day)**. Có thể dùng async paging, nhưng phải giới hạn số trang và độ lớn partition.
- **orders_by_id** phục vụ tra cứu/cập nhật theo khóa **(tenant_id, order_id)**. Một thao tác **IF NOT EXISTS** cần xử lý conditional outcome, không giống SELECT idempotent.
- **LOCAL_QUORUM** cần đủ replica trong local DC; trên cluster một node phải điều chỉnh RF/CL và ghi rõ khác biệt so với production.

Một vài fixture:

~~~sql
INSERT INTO async_lab.events_by_tenant_day
    (tenant_id, event_day, happened_at, event_id, event_type, payload)
VALUES
    (11111111-1111-4111-8111-111111111111, '2026-11-21',
     '2026-11-21T08:00:00Z',
     22222222-2222-4222-8222-222222222222,
     'ORDER_CREATED', '{"source":"lab"}');

INSERT INTO async_lab.events_by_tenant_day
    (tenant_id, event_day, happened_at, event_id, event_type, payload)
VALUES
    (11111111-1111-4111-8111-111111111111, '2026-11-21',
     '2026-11-21T08:01:00Z',
     33333333-3333-4333-8333-333333333333,
     'ORDER_VALIDATED', '{"source":"lab"}');
~~~

Prepared SELECT:

~~~sql
SELECT happened_at, event_id, event_type
FROM async_lab.events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
LIMIT ?;
~~~

Conditional write:

~~~sql
INSERT INTO async_lab.orders_by_id
    (tenant_id, order_id, status, created_at)
VALUES (?, ?, ?, ?)
IF NOT EXISTS;
~~~

**Hai thao tác khác nhau về retry:**

- SELECT có thể được đánh dấu idempotent vì không thay đổi dữ liệu, nhưng retry vẫn gây thêm tải đọc.
- Conditional INSERT phải xử lý **[applied]** và timeout mơ hồ bằng đối soát trạng thái/idempotency key, thay vì tự retry vô hạn.

## 7. Cấu hình timeout và profile của Java Driver 4.x

Một dạng cấu hình HOCON trong **application.conf**:

~~~hocon
datastax-java-driver {
  basic {
    contact-points = [ "127.0.0.1:9042" ]
    load-balancing-policy.local-datacenter = dc1

    request {
      timeout = 1500 milliseconds
      consistency = LOCAL_QUORUM
      page-size = 100
    }
  }

  profiles {
    limited-read {
      basic.request.timeout = 1200 milliseconds
      basic.request.consistency = LOCAL_QUORUM
      basic.request.page-size = 64
    }

    conditional-write {
      basic.request.timeout = 2 seconds
      basic.request.consistency = LOCAL_QUORUM
    }
  }
}
~~~

Đây là **các giá trị minh họa**, không phải SLO hay mặc định của mọi Cassandra cluster. Xác minh cú pháp và options theo phiên bản driver; **timeout của driver không phải timeout ở server**.

Đặt profile trên statement:

~~~java
BoundStatement read = preparedRead.bind(tenantId, day, 200)
    .setExecutionProfileName("limited-read")
    .setIdempotent(true);

CompletionStage<AsyncResultSet> firstPage =
    session.executeAsync(read);
~~~

Driver 4.x dùng statement **immutable**, vì vậy các setter trả một **statement mới**. Giá trị tường minh ở statement có thể override cấu hình tương ứng từ execution profile. Nếu app tự override timeout/consistency theo request, phải ghi nhận chính sách hiệu lực trong observability.

**Không cấu hình retry theo cảm tính:** driver có **retry policy riêng** và một số lỗi có thể đã được retry trước khi future trả về lỗi. Nếu thêm retry ở Java service, phải tính cả số attempt trong driver để không nhân tải ngoài ý muốn.

### 7.1. Server timeout và client timeout

Khi server phát **ReadTimeout**, nó thể hiện điều kiện timeout xử lý request trong Cassandra. Khi Java hết **driver request timeout**, coordinator có thể vẫn đang thực hiện hoặc đã hoàn tất. Nếu tầng HTTP cũng có timeout và proxy/gateway retry, một logical request có thể phát sinh **nhiều request vật lý**.

Vì vậy cần theo dõi:

~~~text
Số logical requests từ HTTP
Số lần driver thực sự gửi request
Số retries theo driver policy
Số retries ở service/gateway
Số fetchNextPage nếu truy vấn phân trang
Số request bị client admission từ chối
~~~

Không dùng **application retry count = 0** làm bằng chứng hệ thống không retry; các tầng khác có thể đã thử lại.

## 8. Xử lý lỗi bất đồng bộ mà không chặn thread

Với **CompletionStage**, xử lý thành công/thất bại nên được nối bằng callback. Đừng dùng **join/get** ngay trên thread xử lý HTTP hoặc driver I/O.

~~~java
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class AsyncReadService {
    private final CqlSession session;
    private final PreparedStatement query;

    public AsyncReadService(CqlSession session) {
        this.session = session;
        this.query = session.prepare(
            "SELECT happened_at, event_id, event_type " +
            "FROM async_lab.events_by_tenant_day " +
            "WHERE tenant_id = ? AND event_day = ? LIMIT ?");
    }

    public CompletionStage<AsyncResultSet> readFirstPage(
            UUID tenantId, LocalDate day) {

        BoundStatement request = query.bind(tenantId, day, 100)
            .setPageSize(32)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true);

        return session.executeAsync(request)
            .whenComplete((page, error) -> {
                if (error != null) {
                    Throwable root = unwrap(error);
                    System.err.println(
                        "Read failed: " +
                        root.getClass().getSimpleName());
                }
            });
    }

    private static Throwable unwrap(Throwable error) {
        while (error instanceof CompletionException &&
                error.getCause() != null) {
            error = error.getCause();
        }
        return error;
    }
}
~~~

**Lưu ý:**

1. **whenComplete** quan sát kết quả, nhưng **không tự sửa lỗi** và không biến thất bại thành thành công.
2. Không log raw **BoundStatement**, customer ID, token hoặc payload. Ghi operation, query shape, CL, retry count và exception class.
3. Đoạn code trả trang đầu, **không phải tất cả các trang**. Nếu API đòi dữ liệu đầy đủ, phải tiếp tục phân trang với **hasMorePages/fetchNextPage** và ngân sách thời gian toàn chuỗi.
4. CqlSession và PreparedStatement nên được tái sử dụng theo vòng đời ứng dụng.
5. Ví dụ không cài TLS/auth để tập trung vào luồng async; production phải cấu hình xác thực/mã hóa đúng, không hạ bảo mật để tránh timeout.
6. Cần kiểm tra lỗi **driver-side timeout, network, auth/TLS và overload** ngoài các lỗi CQL server; không bắt lỗi chung rồi mặc định retry tất cả.

## 9. Đặt ngân sách retry trước khi viết retry loop

Một chính sách retry an toàn cần có **bốn điều kiện đồng thời**:

1. **Request idempotent** (hoặc có xử lý unknown outcome/idempotency business).
2. **Lỗi có thể phục hồi tạm thời** theo loại lỗi và dữ liệu quan sát.
3. **Còn deadline** sau khi trừ thời gian chờ và chi phí backoff.
4. **Hệ thống còn năng lực**: admission/circuit breaker không báo quá tải và retry budget chưa hết.

Một cách tư duy:

~~~text
if !idempotent:
    do_not_retry_automatically

if overloaded || circuit_open:
    shed_load_or_fail_fast

if attempts >= max_attempts:
    fail

if remaining_deadline <= next_delay + minimal_request_budget:
    fail

retry_with_bounded_backoff_and_jitter()
~~~

**Không phải mọi ReadTimeout đều đáng retry.** Nếu tất cả replica chậm do I/O hoặc một partition cực nóng, gửi lại thường chỉ tăng gánh nặng. Retry policy tốt cũng cần một công tắc **giảm retry khi error rate/load tăng**, và phải được đo trên staging theo workload thực.

### 9.1. Exponential backoff và jitter

Ví dụ tối đa ba attempt bao gồm lần đầu:

| Attempt | Trước khi gửi | Delay giả định |
|---|---|---|
| 1 | Chưa retry | 0 |
| 2 | Sau lỗi tạm thời | ngẫu nhiên 0–100 ms |
| 3 | Sau lỗi tạm thời tiếp theo | ngẫu nhiên 0–200 ms |

Đây là **full jitter** dựa trên trần tăng theo lũy thừa, không phải đề xuất bắt buộc về số mili giây. Nếu tài nguyên Cassandra đang bão hòa, có thể phải **không retry** hoặc trì hoãn lâu hơn theo chỉ thị hệ thống. Tính cả timeout per attempt và thời gian ở queue; không để tổng vượt deadline caller.

**Không dùng Thread.sleep trong callback** của driver hoặc reactive event loop để chờ backoff. Dùng **ScheduledExecutorService**, scheduler của framework hoặc cơ chế delay không chặn tương thích.

## 10. Ví dụ tích hợp: admission, deadline và retry có giới hạn

Class dưới đây minh họa ba cơ chế phối hợp cho **SELECT idempotent**:

- Một **Semaphore** giới hạn số **logical read operations** có thể hoạt động, bao gồm thời gian đợi backoff.
- Một **deadline monotonic** cho toàn chuỗi attempt.
- Retry tối đa **3 lần** và chỉ trong ví dụ này cho **ReadTimeoutException**, có full jitter; **Overloaded/Unavailable/ReadFailure không tự retry**.

~~~java
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException;

public final class BoundedAsyncReadGateway implements AutoCloseable {
    private final CqlSession session;
    private final Semaphore active;
    private final ScheduledExecutorService scheduler;
    private final int maxAttempts;

    public BoundedAsyncReadGateway(
            CqlSession session, int maxActive, int maxAttempts) {
        if (maxActive <= 0 || maxAttempts <= 0) {
            throw new IllegalArgumentException("positive limits required");
        }
        this.session = session;
        this.active = new Semaphore(maxActive);
        this.maxAttempts = maxAttempts;
        this.scheduler = new ScheduledThreadPoolExecutor(1);
    }

    public CompletionStage<AsyncResultSet> executeIdempotentRead(
            BoundStatement read, Duration budget) {

        if (budget.isNegative() || budget.isZero()) {
            return failed(new IllegalArgumentException(
                "budget must be positive"));
        }
        if (!active.tryAcquire()) {
            return failed(new RejectedExecutionException(
                "logical read admission limit reached"));
        }

        CompletableFuture<AsyncResultSet> outcome =
            new CompletableFuture<>();
        long startedAtNanos = System.nanoTime();

        // Giữ permit cho đến khi chuỗi attempt kết thúc.
        attempt(read, startedAtNanos, budget.toNanos(),
                1, outcome);

        // Trả dependent stage, giúp caller không cần sở hữu
        // CompletableFuture nội bộ để hoàn thành nó tùy ý.
        return outcome.whenComplete((page, error) ->
            active.release());
    }

    private void attempt(
            BoundStatement read,
            long startedAtNanos,
            long budgetNanos,
            int attemptNo,
            CompletableFuture<AsyncResultSet> outcome) {

        if (outcome.isDone()) {
            return;
        }
        long elapsed = System.nanoTime() - startedAtNanos;
        if (elapsed >= budgetNanos) {
            outcome.completeExceptionally(
                new TimeoutException("logical deadline exceeded"));
            return;
        }

        CompletionStage<AsyncResultSet> request;
        try {
            request = session.executeAsync(read);
        } catch (RuntimeException error) {
            outcome.completeExceptionally(error);
            return;
        }

        request.whenComplete((page, error) -> {
            long nowElapsed = System.nanoTime() - startedAtNanos;
            if (error == null) {
                if (nowElapsed >= budgetNanos) {
                    outcome.completeExceptionally(
                        new TimeoutException("logical deadline exceeded"));
                } else {
                    outcome.complete(page);
                }
                return;
            }

            Throwable reason = unwrap(error);
            boolean retryable =
                reason instanceof ReadTimeoutException;

            if (!retryable || attemptNo >= maxAttempts) {
                outcome.completeExceptionally(reason);
                return;
            }

            long capMillis = Math.min(
                1000L, 100L << Math.min(attemptNo - 1, 10));
            long delayMillis =
                ThreadLocalRandom.current().nextLong(capMillis + 1);

            long remainingNanos =
                budgetNanos - nowElapsed;
            long requiredNanos =
                TimeUnit.MILLISECONDS.toNanos(delayMillis + 50);

            if (remainingNanos <= requiredNanos) {
                outcome.completeExceptionally(reason);
                return;
            }

            try {
                scheduler.schedule(
                    () -> attempt(read, startedAtNanos,
                            budgetNanos, attemptNo + 1, outcome),
                    delayMillis, TimeUnit.MILLISECONDS);
            } catch (RejectedExecutionException stopped) {
                outcome.completeExceptionally(stopped);
            }
        });
    }

    private static Throwable unwrap(Throwable error) {
        while (error instanceof CompletionException &&
                error.getCause() != null) {
            error = error.getCause();
        }
        return error;
    }

    private static <T> CompletionStage<T> failed(
            Throwable error) {
        CompletableFuture<T> result = new CompletableFuture<>();
        result.completeExceptionally(error);
        return result;
    }

    @Override
    public void close() {
        scheduler.shutdown();
    }
}
~~~

Dùng với một SELECT đã prepare:

~~~java
BoundStatement read = preparedRead.bind(tenantId, day, 100)
    .setPageSize(32)
    .setIdempotent(true)
    .setConsistencyLevel(
        com.datastax.oss.driver.api.core
            .DefaultConsistencyLevel.LOCAL_QUORUM);

BoundedAsyncReadGateway gateway =
    new BoundedAsyncReadGateway(session, 40, 3);

CompletionStage<AsyncResultSet> firstPage =
    gateway.executeIdempotentRead(
        read, Duration.ofMillis(1800));

// Để gateway/session sống trong vòng đời service;
// chỉ đóng khi đã ngừng nhận request và drain công việc.
~~~

**Ranh giới của ví dụ — không phải retry framework production hoàn chỉnh:**

1. Chỉ dùng cho **SELECT đã được chứng minh idempotent**. Class không tự phân tích CQL để xác minh điều đó; caller phải chịu trách nhiệm.
2. **Không retry Overloaded, Unavailable hoặc ReadFailure** trong mẫu này. Khi có hệ thống điều tiết tải chung, có thể chính sách thực tế thậm chí **không retry cả ReadTimeout**.
3. **Deadline này là kiểm tra hợp tác** trước/sau attempt và trước khi schedule retry, không phải cơ chế cưỡng bức hủy một request đang xử lý ở Cassandra. Phải cấu hình driver timeout phù hợp để một attempt không kéo dài vô hạn.
4. **Semaphore** giữ permit cho tới khi stage kết quả hoàn thành, kể cả thời gian backoff. Nếu server đang chậm, điều này ngăn app tạo vô hạn chuỗi retry cùng lúc.
5. **ScheduledThreadPoolExecutor** ở đây chỉ có một scheduler thread. Với hệ thống thật, phải kiểm soát số timer/job, ngừng nhận request trước shutdown và theo dõi queue scheduler; có thể dùng scheduler được framework quản lý.
6. **Driver có thể đã retry riêng.** Nếu kích hoạt retry ở tầng Java này, phải xem effective driver retry policy, request budget và số attempts thực sự; tránh retry chồng lớp.
7. Ví dụ chỉ nhận **trang đầu** của một SELECT phân trang. Deadline của **toàn bộ quá trình đọc nhiều trang** phải được thiết kế riêng, không được coi stage trang đầu đã chứng minh toàn job đạt deadline.
8. Không cấu hình **TLS/auth** trong mẫu gọi dùng session sẵn có; production phải sử dụng session được khởi tạo với bảo mật đúng.
9. Thay đổi hoặc hủy stage phía caller không bảo đảm Cassandra dừng request đang bay. Cần giải phóng resource theo lifecycle và quan sát outstanding operations trong bản production.
10. Bộ đếm maxActive là **mỗi instance**, không phải quota toàn cluster. Nếu có hàng chục instance, cần capacity budgeting tổng thể.
## 11. Timeout và backpressure khi đọc nhiều trang bất đồng bộ

Với Java Driver 4.x, **executeAsync(statement)** trả **CompletionStage<AsyncResultSet>** cho trang đầu; mỗi **AsyncResultSet** cung cấp:

- **currentPage():** các row ở trang hiện tại.
- **hasMorePages():** có còn trang để yêu cầu tiếp không?
- **fetchNextPage():** lấy trang tiếp theo bằng một stage bất đồng bộ.

Một endpoint có deadline 2 giây nhưng phải đọc 20 trang **không thể dùng timeout của trang đầu làm bảo đảm toàn bộ kết quả hoàn tất trong 2 giây**.

### 11.1. Luồng đọc giữ một deadline chung

~~~mermaid
flowchart TD
    A["Nhận logical request, ghi startNanos"] --> B["Admission vào số pipeline hữu hạn"]
    B --> C["executeAsync: trang đầu"]
    C --> D["Xử lý currentPage/downstream"]
    D --> E{"Còn deadline?"}
    E -->|Không| X["Kết thúc INCOMPLETE; không fetch tiếp"]
    E -->|Có| F{"hasMorePages?"}
    F -->|Không| G["COMPLETE + giải phóng permit"]
    F -->|Có| H["fetchNextPage"]
    H --> D
~~~

Nếu downstream xử lý trang chậm, **chờ nó hoàn tất rồi mới gọi fetchNextPage**. Việc đọc trước hàng loạt trang vào danh sách không giới hạn sẽ phá tác dụng điều tiết tải.

### 11.2. Ví dụ đếm row với deadline toàn chuỗi

~~~java
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeoutException;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class DeadlinePagedCount {
    public static CompletionStage<Long> count(
            CqlSession session, BoundStatement statement,
            Duration budget) {

        long started = System.nanoTime();
        return session.executeAsync(statement)
            .thenCompose(first ->
                consume(first, 0L, started, budget.toNanos()));
    }

    private static CompletionStage<Long> consume(
            AsyncResultSet page, long count,
            long started, long budgetNanos) {

        long nextCount = count;
        for (Row ignored : page.currentPage()) {
            nextCount++;
        }

        if (System.nanoTime() - started >= budgetNanos) {
            CompletableFuture<Long> failed =
                new CompletableFuture<>();
            failed.completeExceptionally(
                new TimeoutException("paging deadline exceeded"));
            return failed;
        }

        if (!page.hasMorePages()) {
            return CompletableFuture.completedFuture(nextCount);
        }

        final long snapshotCount = nextCount;
        return page.fetchNextPage()
            .thenCompose(nextPage ->
                consume(nextPage, snapshotCount,
                        started, budgetNanos));
    }
}
~~~

Đoạn này giữ bộ đếm **O(1)**, không giữ mọi Row. Tuy nhiên:

1. **Không có hủy cưỡng bức** fetchNextPage đang chạy nếu deadline hết giữa chừng; stage hoàn thành thì mã mới kiểm tra.
2. Muốn giới hạn thực tế, cần **driver request timeout** và chính sách cancellation theo API/framework đang dùng.
3. Nếu currentPage lớn hoặc xử lý từng row nặng, phải kiểm tra deadline/cancel bên trong xử lý hoặc chuyển sang executor giới hạn.
4. Việc đếm mọi row vẫn tốn I/O; không nên dùng như truy vấn thống kê thường xuyên trên partition lớn.
5. Ví dụ dùng đệ quy bất đồng bộ qua **thenCompose**. Với rất nhiều page, cân nhắc processor/trampoline hoặc reactive pipeline để kiểm soát depth/bộ nhớ.
6. Deadline này dành cho **toàn query nhiều trang**, khác với retry attempt cho **trang đầu** ở mục 10. Khi phối hợp production, phải dùng **một deadline từ caller**, không khởi tạo deadline mới cho từng tầng.

### 11.3. Nếu trang thứ N lỗi?

Một pipeline đã xử lý trang 1–5 và trang 6 thất bại:

- Future toàn pipeline cần báo **thất bại/incomplete**, không báo đã lấy đủ.
- Các row trước đó có thể đã tạo side effect ở sink.
- Retry **toàn query từ đầu** có thể gửi trùng các row đã xử lý.
- Paging state không tự tạo snapshot nhất quán khi có INSERT/DELETE/TTL song song.
- Job ETL cần **checkpoint bền vững + idempotent sink/reconciliation**, không chỉ cursor trong RAM.

Nếu API chủ ý trả partial results, hợp đồng phải nêu rõ **partial=true**, phạm vi dữ liệu đã xác minh và cơ chế tiếp tục. Không trả danh sách thiếu rồi gắn nhãn thành công đầy đủ.

## 12. Phối hợp reactive demand với sink bất đồng bộ

Java Driver 4.x có API reactive theo phiên bản/dependency tương ứng. Trong ứng dụng Reactor, publisher từ driver có thể được bọc bằng **Flux** để xử lý theo demand.

### 12.1. Ví dụ Reactor với downstream bất đồng bộ

Giả sử **sink.persist(UUID)** trả **CompletionStage<Void>** khi đã hoàn tất cam kết xử lý theo hợp đồng của sink:

~~~java
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class ReactiveEventPipeline {
    interface EventSink {
        CompletionStage<Void> persist(UUID eventId);
    }

    public static Mono<Void> consume(
            CqlSession session,
            BoundStatement statement,
            EventSink sink) {

        return Flux.from(session.executeReactive(statement))
            .limitRate(16)
            .concatMap(
                row -> Mono.fromCompletionStage(
                    sink.persist(row.getUuid("event_id"))),
                1)
            .then()
            .timeout(Duration.ofSeconds(2));
    }
}
~~~

**Đặc điểm và giới hạn:**

- **executeReactive** trả publisher theo API reactive của driver 4.x. Đoạn này cần Reactor, Reactive Streams và phiên bản driver tương thích.
- **limitRate(16)** điều chỉnh demand theo cửa sổ hữu hạn; không khẳng định một request(1) tương ứng một network round-trip.
- **concatMap(..., 1)** giữ sink theo thứ tự và đặt **prefetch = 1** khi phiên bản Reactor hỗ trợ overload này.
- **then()** hoàn thành khi source kết thúc và các thao tác sink đã nối hoàn tất; lỗi sink đi theo pipeline.
- **Mono.timeout(2 giây)** đặt sau **then()** để giới hạn toàn pipeline đã chuyển thành Mono hoàn tất; khác việc đặt timeout trên Flux để giới hạn khoảng cách giữa hai phần tử.
- Timeout/cancel ở Java không có nghĩa request hoặc side effect trên Cassandra/sink được hoàn tác.
- Với ETL lâu dài phải dùng timeout/checkpoint theo loại job; 2 giây chỉ là ví dụ.
- API và overload của **concatMap**, **executeReactive** phải đối chiếu version trước khi dùng production.
- Tránh log UUID/payload thật nếu chúng là thông tin nhạy cảm.

### 12.2. Không retry toàn Flux khi sink không idempotent

~~~java
// Không an toàn nếu sink có side effect mà không chống trùng.
Flux.from(session.executeReactive(statement))
    .concatMap(row -> Mono.fromCompletionStage(
        sink.persist(row.getUuid("event_id"))))
    .retry(5);
~~~

**retry(5)** có thể subscribe lại source từ đầu, không chỉ thử row vừa lỗi. Các row đã gửi email, tăng counter hoặc thu phí có thể bị xử lý lại. Chỉ retry toàn pipeline khi **nguồn và sink hỗ trợ tái thực thi an toàn**, có checkpoint và các giới hạn retry/deadline được chứng minh.

Dùng **retryWhen(backoff)** cũng không tự giải quyết idempotency hoặc kết quả đã xử lý ở downstream.

### 12.3. Demand không thay thế admission

Một subscription reactive có thể tuân thủ request(n), nhưng hệ thống vẫn có **1.000 subscriptions đồng thời**. Cần đồng thời:

- Giới hạn **số subscription/logical query**.
- Giới hạn **demand/prefetch/buffer** của pipeline.
- Giới hạn concurrency của **flatMap** và thread pool xử lý sink.
- Có tổng deadline, retry budget và cancellation.
- Có quota **theo tenant** nếu một khách hàng có thể chiếm phần lớn capacity.

**Reactive không đồng nghĩa không bao giờ OOM.** Một collectList không giới hạn hoặc buffer không giới hạn vẫn có thể giữ toàn bộ dataset.

## 13. Admission, rate limit, load shedding và circuit breaker

### 13.1. Mỗi cơ chế giải quyết một kiểu áp lực

| Cơ chế | Kiểm soát | Ví dụ |
|---|---|---|
| **Concurrency limit** | Số logical operations đang hoạt động | Semaphore 40 reads/instance |
| **Rate limit** | Số request/đơn vị công việc theo thời gian | Giới hạn ingest theo tenant và loại API |
| **Queue bound** | Số request được chờ permit | Chờ tối đa 100 rồi từ chối |
| **Retry budget** | Lượng traffic dành cho retry | Retry không được lấn át request mới |
| **Circuit breaker** | Tạm từ chối đường gọi thường lỗi | Mở circuit khi overload kéo dài |
| **Cost-based admission** | Phân biệt query nhẹ và scan đắt | Query nhiều partition dùng nhiều token hơn point read |

**Concurrency** và **rate** không thay thế nhau. Một request chậm có thể chiếm permit lâu dù QPS thấp; request rất nhanh với QPS cao vẫn có thể làm disk/network quá tải. Kết hợp theo workload.

### 13.2. Phản hồi cho caller khi không thể nhận thêm

Khi Java từ chối **trước khi gửi** vì hết permit, đó là **client admission rejection**, không phải OverloadedException từ Cassandra.

Với API HTTP:

- **429 Too Many Requests** thường phù hợp khi vi phạm quota của caller/tenant.
- **503 Service Unavailable** có thể phù hợp khi dịch vụ/nguồn phụ thuộc tạm thời thiếu capacity.
- **Retry-After** chỉ nên gửi nếu có thể nêu mốc/khoảng chờ hữu ích; không hứa chính xác khi cluster vẫn quá tải.
- Hạn chế retry tự động của gateway/proxy nếu chưa có budget tổng.
- Ghi reason code/correlation ID không chứa PII để phân biệt client shed load và server overload.

HTTP status cụ thể phụ thuộc hợp đồng API, không phải mã lỗi CQL mặc định. Trả lỗi sớm có kiểm soát có thể bảo vệ p99 cho request còn được chấp nhận.

### 13.3. Fairness theo tenant

Nếu một tenant tạo 80% traffic, semaphore toàn cục đơn thuần có thể làm các tenant khác cùng bị từ chối. Cân nhắc:

1. Quota theo tenant hoặc nhóm endpoint.
2. Ưu tiên request nghiệp vụ quan trọng hơn bulk job.
3. Rate limit riêng cho hot partition và loại query.
4. Deadline khác nhau cho interactive API và batch job.
5. Metrics theo query shape/nhóm tenant, không lộ định danh nhạy cảm.

Cũng phải tránh tạo số lượng queue/counter theo tenant không được dọn, gây memory leak khi số tenant lớn.

## 14. Vì sao concurrency cần được đo cùng latency?

Một trực giác vận hành là **định luật Little** trong trạng thái tương đối ổn định:

~~~text
L ≈ λ × W

L : số request trung bình đang nằm trong hệ thống
λ : thông lượng request/s
W : thời gian trung bình một request trong hệ thống (giây)
~~~

Ví dụ với **1.000 logical requests/s**:

| Thời gian trung bình W | Số in-flight L ước lượng |
|---|---:|
| 0,1 s | 100 |
| 0,5 s | 500 |
| 2,0 s | 2.000 |

Khi Cassandra chậm từ 100 ms lên 2 giây mà app vẫn phát 1.000 request/s, lượng request trong hệ thống có thể tăng khoảng **20 lần**. Nếu mỗi timeout làm phát thêm retry, gánh nặng còn tăng.

Đây là quan hệ trung bình trong hệ ổn định, **không phải dự báo chính xác** trong giai đoạn bão hòa, có deadline, burst hoặc drop. Nó giải thích tại sao **tăng timeout mà không giới hạn in-flight** có thể dẫn đến memory pressure và p99 xấu.

### 14.1. Kiểm thử theo hai trục

Trong bài thử có kiểm soát, thay đổi:

- **Concurrency:** 20, 40, 80 logical operations/instance.
- **Request rate:** 200, 500, 1.000 request/s ở toàn service.
- Giữ được đo lường về **row size, page size, CL, partition distribution**.
- **Retry budget:** 0 hoặc một mức nhỏ có chủ đích.

Đo **throughput thành công**, không chỉ traffic gửi đi. Nếu tăng concurrency mà throughput không tăng, p99/Overloaded lại tăng, hệ thống có thể đã vượt điểm bão hòa.

## 15. Retry policy nên phụ thuộc loại lỗi và tải

| Tình huống | Đọc idempotent | Ghi chưa được chứng minh idempotent | Áp lực tải cần giảm? |
|---|---|---|---|
| ReadTimeout | Retry rất ít nếu còn budget và server khỏe | Không áp dụng như ghi lại | Có thể |
| ReadFailure | Điều tra log/table/replica; retry tùy nguyên nhân | Không áp dụng | Tùy nguyên nhân |
| WriteTimeout | Không áp dụng | **Không retry mù**; đối soát trạng thái | Có thể |
| WriteFailure | Không áp dụng | Đánh giá write partial/unknown | Có thể |
| Overloaded | Không retry tức thì, shed load | Không retry tức thì | **Có** |
| Unavailable | Phục hồi replica/topology; chỉ thử lại khi tình trạng đổi | Cần kiểm tra dữ liệu/CL | Có thể |
| Driver timeout | Kiểm tra network/queue/driver | Outcome mơ hồ | Có thể |
| Authentication/Codec/CQL error | Không retry, sửa cấu hình/code | Không retry, sửa cấu hình/code | Retry không giúp |

Các lựa chọn phải phù hợp **retry policy thực của driver và hợp đồng nghiệp vụ**; không có quy tắc “retry 3 lần cho mọi ReadTimeout” áp dụng cho tất cả hệ thống.

### 15.1. Những điều tránh

- Retry không backoff ngay trong callback, tạo burst.
- Thread.sleep trên thread driver/reactive event loop.
- Thử lại cả POST và driver request mà không có idempotency key chung.
- Sinh UUID mới mỗi lần retry tạo event/order.
- Giảm consistency level khi timeout dù API cam kết mức cao hơn.
- Đổi coordinator liên tục như cách chữa hot partition: cùng nhóm replica vẫn chịu tải.
- Retry khi circuit đang mở hoặc caller đã hết deadline.
- Bỏ qua **[applied]** của LWT rồi coi mọi exception là ghi chưa xảy ra.
- Tăng maxAttempts trước khi xác định nguồn Overloaded/GC/disk.

### 15.2. Retry có side effect downstream

Nếu pipeline **đọc Cassandra → gửi broker → cập nhật hệ khác**, retry sau trang N lỗi có thể gửi trùng trang trước. Thiết kế:

1. Có **event_id** ổn định cho từng sự kiện.
2. Sink có idempotency/deduplication.
3. Checkpoint chỉ tiến sau khi sink xác nhận cam kết bền vững theo hợp đồng.
4. Có reconciliation để phát hiện sự kiện thiếu.
5. Không xem paging state là checkpoint vĩnh viễn bất chấp schema/version.

**At-least-once + chống trùng** thường thực tế hơn lời hứa exactly-once end-to-end không được kiểm chứng.

## 16. Timeout/cancel phía client không phải rollback

| Sự kiện | Phía Java | Phía Cassandra |
|---|---|---|
| Caller hủy HTTP request | Có thể ngừng fetch page mới | Request đã gửi có thể vẫn chạy |
| CompletableFuture timeout/cancel | Stage hoàn thành lỗi/hủy | Không chứng minh coordinator dừng mutation |
| Server WriteTimeout | Client không đủ xác nhận | Một số replica có thể đã ghi |
| Reactor subscription cancel | Subscriber không nhận tiếp | Không hoàn tác side effect đã xảy ra |
| App retry sau LWT timeout | Có thể nhận [applied]=false | Lần trước có thể đã thành công |

**Cancellation cần mang tính hợp tác**:

- Trước fetchNextPage, kiểm tra caller còn cần kết quả và deadline chưa hết.
- Dừng producer/sink nhưng không báo đã rollback database.
- Trả permit đúng vòng đời; tránh thả quá sớm nếu server vẫn còn công việc đang bay.
- Với ghi/LWT, kiểm tra trạng thái bằng khóa nghiệp vụ.
- Cân đối driver timeout và caller deadline để tránh request orphaned quá lâu.

## 17. Quan sát và chẩn đoán từ Java đến Cassandra

### 17.1. Metrics ở từng lớp

| Lớp | Tín hiệu | Câu hỏi |
|---|---|---|
| **HTTP/gRPC** | Arrival rate, p95/p99, deadline exceeded, 429/503 | Người gọi thấy gì? |
| **Admission** | Active permits, rejected, queue depth/wait, tenant quota | Có quá nhiều việc được nhận? |
| **Driver** | In-flight, connection pool, timeout, retry count, coordinator/DC | Retry có nhân tải? |
| **Async paging** | First-page/full-result latency, page count, failure page | Trang nào chậm/lỗi? |
| **Reactive** | Demand, consumed rows, sink latency, buffers | Downstream có theo kịp? |
| **Cassandra** | Read/WriteFailure, timeout, overload, unavailable | Replica/coordinator có lỗi gì? |
| **Storage/JVM** | Disk latency/free, heap, native RSS, GC, compaction backlog | Nút thắt ở đâu? |
| **Topology** | UP/DOWN, RF/DC/rack, repair/streaming | Có đủ replica theo CL? |

**Đừng chỉ đếm application retries.** Driver, proxy và gateway có thể retry riêng. Phân biệt **logical requests** và **physical attempts** để biết tải thực.

### 17.2. Lệnh quan sát chỉ đọc

Trên cluster được phép và theo cú pháp phiên bản:

~~~bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool netstats
nodetool tablestats async_lab.events_by_tenant_day
nodetool tablehistograms async_lab events_by_tenant_day
~~~

Kết hợp server logs ở **coordinator và replica**, metrics/JMX/Prometheus, disk I/O, GC và traffic client. Node báo **UN (Up/Normal)** vẫn có thể đang quá tải hoặc không đáp ứng kịp LOCAL_QUORUM.

Không chạy **repair, cleanup, upgradesstables** hoặc thay topology như phản xạ chữa timeout. Các thao tác có thể tạo I/O lớn và phải theo runbook. Repair đồng bộ replica, không hoàn tác DELETE sai về nghiệp vụ.

### 17.3. Log giảm dữ liệu

~~~json
{
  "event": "cassandra_async_operation_failed",
  "operation": "events_by_tenant_day.read",
  "profile": "limited-read",
  "consistency": "LOCAL_QUORUM",
  "failure_class": "ReadTimeoutException",
  "logical_attempt": 2,
  "page_index": 3,
  "deadline_remaining_ms": 180,
  "active_operations": 40,
  "admission_rejected": false,
  "request_id": "req-lab-72"
}
~~~

Đây là mẫu **log do ứng dụng định nghĩa**, không phải output mặc định của driver. Không ghi password, raw BoundStatement, customer ID thật, paging state hoặc payload. Ghi query shape, operation, CL, latency và exception class thường đủ để bắt đầu điều tra.
## 18. Hai tình huống phối hợp thực tế

### 18.1. Retry storm trong giờ bulk ingestion

**Kịch bản giả định:** có 15 instance Java, mỗi instance cho tối đa 200 request ghi đang bay. Job bulk bắt đầu, Cassandra đang chạy compaction và disk utilization tăng. Driver/app cùng có retry policy; API gateway cũng retry một số lỗi.

| Quan sát | Hệ quả |
|---|---|
| 15 instance × 200 request | Tới 3.000 request in-flight nếu mọi quota đều sử dụng |
| Cassandra báo Overloaded | Nhiều request không thể được phục vụ kịp |
| Retry ở nhiều tầng | Số physical attempts tăng ngoài dự kiến |
| Disk/compaction backlog tăng | Thêm attempts làm storage chậm hơn |
| Caller hết deadline | Request server đã gửi có thể còn xử lý |

**Hướng xử lý:** Không tự tăng timeout/maxAttempts. Tạm giảm tốc bulk, giới hạn request mới, giảm retry chồng lớp, áp backoff/jitter và shed load. Kiểm tra disk/GC/compaction, hot partition, batch/mutation size; sau khi ổn định mới mở tải theo gate p99/error rate. Đừng dự đoán số attempts chỉ bằng phép nhân các giới hạn retry; cần đo **physical attempts** thực tế tại từng tầng.

### 18.2. Reactive ETL có sink chậm

Một job đọc 500.000 row, sink chỉ xử lý 100 row/giây, nhưng pipeline dùng **flatMap concurrency cao**, buffer không giới hạn và retry toàn Flux khi một page timeout.

- Buffer tăng và gây heap pressure/GC.
- Driver vẫn fetch page dù downstream chưa xử lý xong.
- Retry toàn source làm gửi lại những row đã xử lý.
- Caller đã timeout nhưng pipeline vẫn tiêu tốn tài nguyên.

**Thiết kế lại:** giới hạn số subscriptions, demand/prefetch và concurrency; dùng concatMap hoặc bounded flatMap theo khả năng sink; có checkpoint/idempotency; dừng fetch mới khi deadline hết; đo rows/s **xử lý thành công** và full-result latency thay vì chỉ first-page latency.

## 19. Runbook xử lý timeout và quá tải

~~~mermaid
flowchart TD
    A["Timeout/ReadFailure/Overloaded tăng"] --> B["Phân loại lỗi và phạm vi"]
    B --> C{"Sai dữ liệu, mất quorum hoặc lỗi bảo mật nặng?"}
    C -->|Có| S["STOP; bảo vệ dữ liệu và xử lý incident"]
    C -->|Không| D{"Queue/in-flight hoặc overload tăng?"}
    D -->|Có| E["Shed load, limit concurrency, giảm retry"]
    D -->|Không| F["Kiểm tra timeout layer, RF/CL, network"]
    E --> G["Kiểm tra hot partition, disk/GC, compaction"]
    F --> G
    G --> H{"SLO và correctness đã ổn?"}
    H -->|Không| I["Tiếp tục chẩn đoán, giữ giới hạn"]
    H -->|Có| J["Mở tải dần với giám sát"]
~~~

Quy trình tám bước:

1. **Chốt thời điểm/phạm vi sự cố** và dừng thay đổi đang tăng tải.
2. **Phân loại exception** từ server, driver, admission hay downstream; xác định deadline nào hết.
3. **Kiểm tra topology và CL:** RF, DC, replica khỏe, partition routing.
4. **Kiểm tra query/data model:** hot key, partition lớn, tombstone, page size, LIMIT, batch và collection.
5. **Kiểm tra tài nguyên:** GC, disk, native RSS, compaction, repair, streaming, pending tasks.
6. **Đo tải khuếch đại:** retries ở driver/app/gateway, số instance, active subscriptions và queue.
7. **Giảm áp lực an toàn:** load shedding, quota, jitter/backoff, deadline; không đổi consistency cam kết.
8. **Kiểm chứng phục hồi:** p95/p99, successful throughput, lỗi theo loại, queue và dữ liệu đúng. Mở tải từ từ.

Nếu phát hiện corruption hay mất dữ liệu, không chỉ giảm retry rồi coi xong; cần bảo vệ bằng chứng và đánh giá restore/repair theo nguyên nhân.

## 20. Kế hoạch kiểm thử trên staging

### 20.1. Bộ thử tối thiểu

1. **Baseline bình thường:** p50/p95/p99, throughput, first-page/full-result latency, GC và disk.
2. **Một replica chậm:** giả lập ở lab, so LOCAL_ONE/LOCAL_QUORUM đúng theo hợp đồng.
3. **Một replica không khả dụng:** phân biệt Unavailable, ReadTimeout và timeout phía Java.
4. **Quá tải có giới hạn:** tăng rate/concurrency từng bước; xác định điểm Overloaded.
5. **Retry budget:** đo physical attempts ở các tầng, backoff và jitter.
6. **Caller timeout/cancel:** pipeline dừng fetch mới, permit không rò rỉ.
7. **Trang N lỗi:** kết quả phải INCOMPLETE; không âm thầm báo đủ.
8. **Sink chậm:** demand/buffer/concurrency không tăng vô hạn.
9. **Ghi idempotent/non-idempotent:** timeout với event ID, counter, list append và LWT.
10. **Soak test:** đủ lâu để thấy compaction, repair và GC ảnh hưởng.

Chỉ thực hiện fault injection/network shaping trên môi trường **cô lập và được phê duyệt**, không cố tình phá production.

### 20.2. Tiêu chí pass/fail

- Không chấp nhận sai dữ liệu hoặc invariant nghiệp vụ.
- Deadline được tôn trọng trong phạm vi rõ; partial results không thành complete.
- Retries nằm trong ngân sách, không có retry storm khi Overloaded.
- In-flight, queue và reactive buffers có giới hạn và được đo.
- Successful throughput/latency đạt SLO ở tải đại diện.
- Downstream chậm không khiến Cassandra bị fetch vô hạn.
- Khi bỏ fault, hệ thống có thể phục hồi mà không cần restart hàng loạt.
- Metrics/log đủ phân biệt lớp lỗi và không tiết lộ thông tin nhạy cảm.

Ngưỡng timeout/concurrency phải dựa trên SLO, payload, RF/DC và capacity, không có một giá trị “chuẩn” dùng cho mọi cluster.

## 21. Bài tập tình huống

### Bài 1 — Deadline và retry

HTTP deadline **2 giây**. Request chờ admission **300 ms**, attempt Cassandra mất **1,2 giây** rồi timeout, backoff dự kiến **250 ms**, attempt kế tiếp có timeout **1 giây**.

**Hỏi:** Có nên retry?  
**Đáp án gợi ý:** Không. Đã dùng 1,5 giây, sau backoff chỉ còn 0,25 giây để làm attempt và phản hồi. Không đủ ngân sách.

### Bài 2 — Counter bị timeout

Ghi **counter +1** bị WriteTimeout; developer đặt **setIdempotent(true)** rồi retry.

**Hỏi:** Vì sao nguy hiểm?  
**Đáp án gợi ý:** Khai báo driver không biến counter thành idempotent; lần đầu có thể đã áp dụng, retry có thể cộng thêm.

### Bài 3 — Overloaded và scale app

10 instance Java, mỗi instance cho 100 request in-flight; khi server Overloaded, app retry tức thì ba lần.

**Hỏi:** Cần ưu tiên gì?  
**Đáp án gợi ý:** Giảm incoming rate, giới hạn tổng in-flight/retries, backoff/jitter, shed load, điều tra disk/GC/hot partition/compaction.

### Bài 4 — thenApply và thenCompose

~~~java
CompletionStage<Void> sink(Row row);

CompletionStage<CompletionStage<Void>> nested =
    firstPage.thenApply(page -> sink(page.currentPage()
        .iterator().next()));
~~~

**Hỏi:** Vấn đề ở đâu?  
**Đáp án gợi ý:** Mapper trả CompletionStage nên thenApply sinh nested stage; dùng thenCompose, kiểm tra page rỗng và xử lý tất cả row cần thiết, không chỉ row đầu.

### Bài 5 — Không block có đủ backpressure?

Dịch vụ nhận 10.000 HTTP requests; mỗi request gọi **executeAsync** và giữ một future, không gọi sleep/join.

**Hỏi:** Có thể quá tải không?  
**Đáp án gợi ý:** Có. Async không giới hạn logical operations; cần admission, queue hữu hạn, rate limit, retry budget và kiểm soát paging.

### Bài 6 — Hủy HTTP và mutation

Client bị driver timeout sau khi một số replica đã nhận INSERT. Caller hủy HTTP request.

**Hỏi:** Có thể khẳng định DB chưa thay đổi?  
**Đáp án gợi ý:** Không. Cancel/timeout không rollback; đối soát theo primary key/idempotency key và giữ ID ổn định khi thử lại an toàn.

### Bài 7 — Retry toàn reactive source

Các row trang 1–5 đã persist; trang 6 ReadTimeout và pipeline dùng retryWhen cho toàn Flux.

**Hỏi:** Rủi ro gì?  
**Đáp án gợi ý:** Subscribe lại có thể xử lý trùng. Cần checkpoint, sink idempotent, retry có giới hạn, trạng thái incomplete và deadline.

### Bài 8 — Tính in-flight trung bình

Một hệ xử lý **400 request/s**, latency trung bình tăng từ **0,1 s** lên **1 s**.

**Hỏi:** Theo Little's law, L biến đổi thế nào?  
**Đáp án gợi ý:** Khoảng **40 → 400** request, tăng 10 lần, trong mô hình trạng thái ổn định.

### Bài 9 — Hot partition và retry

Bảng có **PRIMARY KEY ((tenant_id, event_day), happened_at, event_id)**; một tenant chiếm 95% tải trên một partition/ngày. Đội chỉ tăng timeout/page-size/retry count.

**Hỏi:** Vì sao không xử lý nguyên nhân?  
**Đáp án gợi ý:** Nhóm replica của partition vẫn quá tải; cần bucket/shard theo truy vấn, giới hạn mutation và bounded concurrency.

### Bài 10 — Reactive buffer

Nguồn phát 1.000 row/s, sink xử lý 20 row/s, Flux dùng buffer vô hạn.

**Hỏi:** Reactive có chống OOM không?  
**Đáp án gợi ý:** Không. Cần giới hạn demand/prefetch, buffer, concurrent subscriptions và có load shedding.

## 22. Checklist đưa vào production

- [ ] Có **deadline end-to-end** gồm queue, retries, paging và downstream.
- [ ] Phân biệt timeout caller, driver, server, page và sink.
- [ ] Đo thời lượng bằng monotonic clock; log thời điểm UTC.
- [ ] Phân loại ReadTimeout, ReadFailure, WriteTimeout, WriteFailure, Overloaded, Unavailable và lỗi network/auth/codec.
- [ ] Chỉ retry khi **idempotency** đã được chứng minh; write outcome unknown có cách đối soát.
- [ ] Không retry Overloaded tức thì; dùng backoff/jitter, retry budget và admission/circuit breaker.
- [ ] Không có retry chồng lớp không kiểm soát giữa driver, app, gateway.
- [ ] Không giảm consistency level ngoài cam kết nghiệp vụ.
- [ ] CompletionStage/thenCompose không chặn driver callback bằng sleep/join/get.
- [ ] Có bounded in-flight, queue hữu hạn, rate limit và load shedding.
- [ ] Reactive demand xuyên pipeline; không có buffer/collectList vô hạn.
- [ ] Paging dừng khi deadline hết, không fetch khi sink không theo kịp.
- [ ] Trang N lỗi được báo incomplete; sink có idempotency/checkpoint nếu có side effect.
- [ ] Cancellation trả resource đúng vòng đời, không coi là rollback server.
- [ ] CqlSession được tái sử dụng và đóng sau drain.
- [ ] Truy vấn bind đủ partition key; partition, batch, collection phù hợp.
- [ ] Theo dõi RF/DC/CL, replica, hot partition, tombstone, compaction, repair, disk/GC.
- [ ] Metrics có first-page/full-result latency, attempts thực, permit/rejection và sink latency.
- [ ] Đã thử tình huống lỗi trên staging đại diện, không phá production.
- [ ] Không ghi credential, raw bind values hoặc dữ liệu khách hàng vào log.

## 23. Tổng kết

**Timeout** giới hạn thời gian có ích của request, **retry** quyết định có thử lại, còn **backpressure/admission** ngăn Java và Cassandra nhận nhiều việc hơn năng lực. Trong ứng dụng bất đồng bộ hoặc reactive, không block thread **chưa đủ**: nếu vẫn phát request và fetch trang không giới hạn, hệ thống vẫn có thể quá tải.

Thiết kế vững dùng **deadline chung từ caller**, retry các thao tác an toàn trong budget, **giảm tải khi Overloaded**, giới hạn logical operations và reactive demand, đồng thời đối soát trạng thái sau timeout ghi. Với Cassandra, phải kết hợp các cơ chế này với **partition key đúng, bảng theo truy vấn, replication/consistency level, kích thước partition, compaction và repair**. Mục tiêu là **dữ liệu đúng, độ trễ trong SLO và hệ thống phục hồi được sau áp lực tải**, không chỉ làm số exception trông nhỏ đi.
