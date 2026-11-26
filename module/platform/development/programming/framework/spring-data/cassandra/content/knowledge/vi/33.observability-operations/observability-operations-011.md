# Giới hạn chi phí tracing và dữ liệu nhạy cảm trong log của Spring Data Cassandra

Khi vận hành hệ thống sử dụng **Spring Data Cassandra**, chúng ta cần biết truy vấn CQL nào chậm, request thất bại ở đâu, partition nào bị dồn tải và nguyên nhân các lỗi như `ReadTimeout`, `Unavailable` hoặc `Overloaded`. Tuy nhiên, việc bật tracing chi tiết cho toàn bộ traffic và ghi mọi tham số truy vấn vào log có thể làm tăng CPU, I/O, độ trễ, chi phí lưu trữ và nguy cơ lộ dữ liệu.

Bài học này tập trung vào hai mục tiêu phải được thực hiện cùng lúc: **đủ thông tin để điều tra sự cố** và **kiểm soát chi phí, quyền truy cập cũng như dữ liệu nhạy cảm**. Ví dụ sử dụng Spring Data Cassandra, Java Driver 4.x, CQL, log có cấu trúc và các khái niệm OpenTelemetry/Reactor. Các mức sampling, retention và thời gian được nêu là giá trị minh họa để đo và điều chỉnh, không phải cấu hình mặc định phù hợp mọi hệ thống.

## 1. Hiểu rõ tracing và logging đang thu thập dữ liệu ở lớp nào

Một request HTTP có thể đi qua service, repository, Java Driver, coordinator và nhiều replica. Mỗi lớp cung cấp tín hiệu quan sát khác nhau.

~~~mermaid
flowchart LR
    U["HTTP / Event consumer"] --> S["Spring Service"]
    S --> R["Repository / CassandraTemplate"]
    R --> D["Java Driver"]
    D --> C["Cassandra coordinator"]
    C --> P1["Replica 1"]
    C --> P2["Replica 2"]

    S -. "log cấu trúc / trace ứng dụng" .-> O["Nền tảng observability"]
    D -. "metrics / request tracker" .-> O
    C -. "query trace chọn lọc" .-> T["system_traces"]
    P1 -. "trace events" .-> T
    P2 -. "trace events" .-> T
~~~

| Nguồn | Ghi nhận gì? | Chi phí và giới hạn cần nhớ |
| --- | --- | --- |
| **Metrics** của API, driver và Cassandra | Số request, tỉ lệ lỗi, latency p50/p95/p99, queue, timeout, load replica. | Thường thích hợp để giám sát liên tục nếu nhãn có cardinality thấp; metrics không cho biết đầy đủ diễn biến một request. |
| **Application log** qua SLF4J/Logback | Thao tác nào, kết quả, loại lỗi, thời gian, request/trace ID. | Log nhiều, stack trace dài hoặc dữ liệu nhạy cảm gây tốn tiền, khó tìm và rủi ro bảo mật. |
| **Distributed tracing** (ví dụ OpenTelemetry) | Các span từ HTTP → service → database/client, quan hệ cha-con và thời gian từng chặng. | Có chi phí tạo span, xử lý exporter, truyền dữ liệu, lưu và tìm kiếm; việc sampling phải được thiết kế có ngân sách. |
| **Cassandra query tracing** | Các sự kiện nội bộ coordinator/replica trong một truy vấn CQL cụ thể. | Phát sinh công việc và ghi thêm dữ liệu lên Cassandra; chỉ bật chọn lọc để điều tra. |
| **Driver request tracker / request logger** | Kết quả, thời gian, lỗi của các request đi qua `CqlSession`. | Có thể tạo log với CQL, bound values hoặc exception; phải kiểm soát cấu hình và quyền truy cập. |
| **Audit log** | Hoạt động theo chính sách kiểm toán/quản trị. | Có mục đích, độ đầy đủ và yêu cầu retention riêng; tracing lấy mẫu không thay thế audit logging. |

**Điểm phân biệt quan trọng:** một `trace_id` trong HTTP distributed tracing và `tracingId` do Cassandra tạo ra cho query tracing là **hai định danh khác nhau**. Có thể lưu chúng cạnh nhau để tương quan, nhưng không giả định chúng có cùng giá trị hoặc cùng cơ chế retention.

Không xem kết quả `Mono.empty()` của một phép đọc như một lỗi database. Ngược lại, `ReadTimeout` không chứng minh rằng bản ghi không tồn tại. Các log và metrics phải phân biệt ít nhất `success`, `not_found` (khi đọc thực sự hoàn tất không có hàng) và `failure`.

## 2. Vì sao bật tracing toàn bộ traffic gây quá tải?

Query tracing của Cassandra được **tắt theo mặc định**. Bật tracing cho từng CQL statement khiến Cassandra thu thập các sự kiện nội bộ của yêu cầu, rồi lưu thông tin trong các bảng hệ thống `system_traces.sessions` và `system_traces.events`. Việc đọc chi tiết trace sau đó cũng có thể phát sinh **truy vấn bổ sung**; các sự kiện trace có thể xuất hiện bất đồng bộ.

Giả sử hệ thống xử lý 4.000 yêu cầu/giây, sampling query trace là 1%. Số request được đánh dấu tracing trung bình là:

\[
4000 \times 1\% = 40\ \text{trace/giây}
\]

Trong 1 giờ, con số kỳ vọng là:

\[
40 \times 3600 = 144\,000\ \text{trace}
\]

Đây chỉ là **số request được chọn**, không phải số event hay byte lưu thực tế. Một request có thể sinh nhiều trace events, và đọc chi tiết từ `system_traces` cũng tạo thêm tải. Nếu số request tăng gấp mười, sampling theo tỉ lệ cố định sẽ tạo thêm gấp mười trace. Vì vậy **sampling phần trăm phải đi cùng giới hạn tuyệt đối**, nhất là trong sự cố traffic cao.

Công thức ước lượng khối lượng lưu trữ:

\[
\text{Bytes/ngày} \approx \text{RPS} \times \text{sample rate}
\times 86400 \times \text{bytes trung bình/trace}
\]

Ví dụ minh họa: 1.000 request/giây, lấy mẫu 0,1% và trung bình 20 KiB/trace (giả định đo được), khối lượng thô khoảng **1,65 GiB/ngày** trước replication, index, nén và metadata. Không dùng kích thước 20 KiB này như một hằng số: nội dung trace, số node tham gia, hệ thống collector và định dạng lưu trữ quyết định chi phí thực.

Ngoài storage, cần quan sát:

- **Thời gian xử lý thêm** tại coordinator/replica và độ trễ của request có tracing so với request thường.
- **Khối lượng sự kiện và dòng log** được tạo, chuyển sang collector, index và retention.
- **Chi phí truy vấn lại trace** nếu ứng dụng liên tục gọi API fetch trace chi tiết.
- **Tác động lúc sự cố**: khi node vốn đã quá tải, việc bật rộng tracing có thể làm khả năng phục hồi kém hơn.

Hạn chế cost bằng sampling **ở nguồn**, trước khi tạo span/log chi tiết hoặc bật cờ tracing của CQL. Sampling chỉ ở exporter vẫn có thể khiến ứng dụng tiêu tốn công tạo dữ liệu trước khi bị loại.

## 3. Chính sách tracing nhiều tầng với ngân sách rõ ràng

Nên bắt đầu từ **metrics có cardinality thấp** để biết tình trạng tổng thể, dùng log cấu trúc cho lỗi hoặc thao tác chậm theo quy tắc, rồi bật distributed tracing/query tracing theo mức độ cần thiết.

| Mức | Khi nào dùng? | Quy tắc gợi ý |
| --- | --- | --- |
| **Bình thường** | Hệ thống khỏe, theo dõi SLO. | Metrics thường xuyên; application trace được lấy mẫu nhỏ; Cassandra query tracing mặc định tắt. |
| **Điều tra một nhóm truy vấn** | p99 tăng ở `orders.find_by_id` hoặc lỗi tập trung ở một table. | Giới hạn theo operation, môi trường, thời lượng và ngân sách trace/phút; ưu tiên truy vấn ít nhạy cảm. |
| **Điều tra một request đã biết** | Có request/operation ID từ cảnh báo hoặc ticket. | Tạo phiên debug có hạn sử dụng và quyền truy cập phù hợp; không bật tracing toàn ứng dụng. |
| **Sự cố diện rộng** | `Overloaded`/`ReadTimeout` tăng nhanh, queue dài. | Giảm tải và thu metrics/log tối thiểu trước; bật query tracing ở tỉ lệ rất thấp nếu cluster còn đủ năng lực. |
| **Kiểm toán/bảo mật** | Cần truy vết truy cập theo chính sách. | Dùng audit logging thích hợp; không dựa vào query trace lấy mẫu làm bằng chứng đầy đủ. |

Một chính sách thực tế cần xác định:

1. **Ai được bật** tracing và được xem kết quả, trong môi trường nào?
2. **Phạm vi**: một operation đã định danh, keyspace/table hoặc nhóm API; không chọn theo toàn bộ payload người dùng.
3. **Ngân sách**: xác suất sampling, số trace tối đa/phút trên từng instance và trên toàn hệ thống, kích thước/log volume tối đa.
4. **Thời hạn**: tự tắt phiên debug sau một khoảng ngắn; có cảnh báo khi ngân sách bị vượt.
5. **Dữ liệu**: trường nào được lưu, trường nào bị cấm, thời gian giữ, cơ chế xóa và giới hạn người xem.
6. **Điều kiện dừng**: khi timeout/CPU/overloaded tăng, phải giảm hoặc tắt sampling chi tiết.

### Head sampling, tail sampling và sampling lỗi

- **Head sampling** quyết định ghi trace ngay từ đầu request. Phù hợp khi muốn tiết kiệm tài nguyên tại nguồn và đặc biệt cần thiết với **Cassandra query tracing**, vì cờ tracing phải được đặt **trước khi gửi** CQL.
- **Tail sampling** có thể quyết định giữ distributed trace sau khi biết request kết thúc chậm hoặc thất bại. Tuy nhiên span và dữ liệu cần được giữ/xử lý tạm ở upstream hoặc collector, nên vẫn có chi phí; cần giới hạn buffer, thời gian chờ và số trace xuất.
- **Error sampling** ưu tiên những request lỗi; với query trace Cassandra, không thể retroactively bật tracing cho request đã trả `ReadTimeout`. Có thể thu exception class/metrics trước, rồi **chỉ định lấy mẫu các lần chạy tiếp theo** của operation đang lỗi, có kiểm soát.

Một tỉ lệ mẫu cố định còn có thể tạo thiên lệch: 0,1% của truy vấn cực phổ biến có thể chiếm phần lớn ngân sách, trong khi truy vấn hiếm nhưng chậm gần như không xuất hiện. Thực tế nên phân bổ **quota theo operation class** như `orders.read_by_id`, `orders.page_by_customer`, `orders.write_state`, và giữ một mức chung cho lưu lượng đột biến.

## 4. Bật Cassandra query tracing theo từng statement

Ví dụ Java Driver 4.x, giả sử đã có `CqlSession` kết nối đúng keyspace với bảng `orders_by_id(order_id uuid PRIMARY KEY, state text)`. Câu CQL đọc theo partition key giúp phép đo phản ánh một access pattern rõ ràng.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import java.util.UUID;

final class TracedOrderReader {
    private static final Logger log =
        LoggerFactory.getLogger(TracedOrderReader.class);
    private final CqlSession session;
    private final QueryTraceGate traceGate;

    TracedOrderReader(CqlSession session, QueryTraceGate traceGate) {
        this.session = session;
        this.traceGate = traceGate;
    }

    String readState(UUID orderId) {
        boolean selected = traceGate.shouldTrace();
        SimpleStatement statement = SimpleStatement.builder(
                "SELECT state FROM orders_by_id WHERE order_id = ?")
            .addPositionalValue(orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true)
            .setTracing(selected)
            .build();

        ResultSet result = session.execute(statement);
        UUID cassandraTraceId = result.getExecutionInfo().getTracingId();

        // Khi không bật tracing, cassandraTraceId là null.
        // Chỉ xuất ID và tên operation đã định danh; không ghi orderId.
        if (cassandraTraceId != null) {
            recordSampledQueryTraceId("orders.read_state", cassandraTraceId);
        }
        var row = result.one();
        return row == null ? null : row.getString("state");
    }

    private void recordSampledQueryTraceId(String operation, UUID traceId) {
        // Chỉ metadata, trong kênh log nội bộ có kiểm soát quyền xem.
        log.info("event=cassandra.query_trace operation={} trace_id={}",
            operation, traceId);
        // Không tự động đọc mọi event hoặc log toàn bộ nội dung trace.
    }
}
~~~

`Statement` và builder của driver dùng cách cấu hình bất biến: gọi `.setTracing(...)` trên bản statement và sử dụng kết quả trả về. Với Spring Data repository/template, không giả định có thể bật server-side query tracing bằng một annotation Java chung cho mọi phiên bản; nếu thật sự cần tracing của một câu CQL cụ thể, nên kiểm soát statement qua cơ chế được phiên bản Spring Data và driver hỗ trợ, hoặc thực hiện lời gọi `CqlSession` có chủ đích như ví dụ.

### Giới hạn cả xác suất và số trace mỗi phút

Lớp `QueryTraceGate` minh họa cách dùng đồng thời xác suất và quota **trong một instance**. Đồng hồ được tiêm vào để dễ kiểm thử.

~~~java
import java.time.Clock;
import java.util.Objects;
import java.util.concurrent.ThreadLocalRandom;

final class QueryTraceGate {
    private final Clock clock;
    private final double sampleProbability;
    private final int maxTracesPerMinute;
    private long minuteBucket = Long.MIN_VALUE;
    private int emittedInMinute = 0;

    QueryTraceGate(Clock clock, double sampleProbability,
                   int maxTracesPerMinute) {
        this.clock = Objects.requireNonNull(clock);
        if (!Double.isFinite(sampleProbability) ||
                sampleProbability < 0 || sampleProbability > 1 ||
                maxTracesPerMinute < 0) {
            throw new IllegalArgumentException("Invalid tracing budget");
        }
        this.sampleProbability = sampleProbability;
        this.maxTracesPerMinute = maxTracesPerMinute;
    }

    synchronized boolean shouldTrace() {
        long currentMinute = clock.instant().getEpochSecond() / 60;
        if (currentMinute != minuteBucket) {
            minuteBucket = currentMinute;
            emittedInMinute = 0;
        }
        if (emittedInMinute >= maxTracesPerMinute ||
                ThreadLocalRandom.current().nextDouble()
                    >= sampleProbability) {
            return false;
        }
        emittedInMinute++;
        return true;
    }
}
~~~

Ví dụ `new QueryTraceGate(Clock.systemUTC(), 0.001, 30)` lấy mẫu xác suất 0,1% nhưng nhiều nhất 30 request query tracing/phút **trong một JVM**. Đây là bộ điều tiết tối giản:

- Quota tính theo cửa sổ phút cố định; có thể xảy ra burst ở ranh giới hai cửa sổ. Hệ thống cần hạn mức mượt hơn có thể dùng token bucket.
- Một cụm 20 pod, mỗi pod có hạn mức 30/phút, vẫn có thể tạo **600 trace/phút**. Tổng quota cần được tính ở cấp ứng dụng/cluster.
- Quyết định random không gắn với một request ID cụ thể, do đó không bảo đảm tất cả span của distributed trace cùng được chọn. Hệ thống dùng OpenTelemetry phải tuân thủ quyết định sampling và propagation của tracer riêng.
- Nếu cần bảo đảm privacy theo table/tenant, **kiểm tra allowlist và quyền** trước khi gọi `shouldTrace()`; chỉ quota không đủ.
- Khi request có nhiều attempt/retry hoặc speculative execution, một lựa chọn tracing ở mức statement có thể kéo theo nhiều tác vụ hơn dự kiến; cần đo bằng metrics.

### Lấy chi tiết query trace cũng là một thao tác tốn tài nguyên

Sau khi truy vấn thành công và có `tracingId`, Java Driver hỗ trợ `getQueryTraceAsync()` để truy xuất các sự kiện trace từ Cassandra. Các sự kiện được lưu bất đồng bộ; driver có thể thử fetch lại theo cấu hình của nó.

~~~java
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

ExecutionInfo info = result.getExecutionInfo();
UUID traceId = info.getTracingId();
if (traceId != null && authorizedForTraceDetail) {
    CompletionStage<?> details = info.getQueryTraceAsync();
    // Chỉ một luồng điều tra có quota mới xử lý 'details'.
    // Không dump toàn bộ trace events vào application log.
}
~~~

Đoạn mã này minh họa điểm gọi API trong **cùng scope có biến `result` và `authorizedForTraceDetail`**; không phải một chương trình hoàn chỉnh. Không gọi `getQueryTrace()` đồng bộ trên thread của driver, vì API này có thể chờ I/O. Không truy vấn `system_traces` theo vòng lặp vô hạn hoặc tăng số attempt lấy trace chỉ vì sự kiện chưa xuất hiện tức thì.

Các bảng `system_traces.sessions` và `system_traces.events` lưu trên Cassandra chịu chi phí replication, TTL và quyền đọc của cluster. Cần kiểm tra phiên bản Cassandra, cấu hình retention và quyền thực tế; không cho rằng dữ liệu ở đây đã được làm sạch như log ứng dụng.

## 5. Cấu hình request logging của Java Driver an toàn

Java Driver 4.x cung cấp `RequestTracker` và `RequestLogger` tùy chọn. Đây là cơ chế ghi nhận kết quả yêu cầu, **khác với Cassandra query tracing**. Khi cần bật để điều tra lỗi hoặc slow requests, cấu hình nên giảm dữ liệu ngay tại nguồn.

Ví dụ HOCON cho Java Driver 4.x, cần kiểm tra tên tùy chọn theo phiên bản đang triển khai:

~~~hocon
datastax-java-driver {
  advanced.request-tracker {
    classes = [RequestLogger]
    logs {
      success.enabled = false
      slow {
        threshold = 1 second
        enabled = true
      }
      error.enabled = true
      show-values = false
      max-query-length = 200
      show-stack-traces = false
    }
  }
}
~~~

Ý nghĩa:

- **`success.enabled = false`**: không in log cho mọi yêu cầu thành công; metrics vẫn đo tổng số request.
- **`slow.enabled` + `threshold`**: tập trung vào nhóm truy vấn chậm. Ngưỡng 1 giây chỉ minh họa; phải dựa trên SLO và độ trễ thực tế từng loại truy vấn.
- **`error.enabled = true`**: hỗ trợ điều tra lỗi, nhưng khi xảy ra sự cố diện rộng cần thêm cơ chế giới hạn tốc độ log ở pipeline.
- **`show-values = false`**: không ghi giá trị tham số bind do request logger lấy ra. Đây là **mặc định mong muốn về bảo mật** trong ví dụ.
- **`max-query-length`** và **`show-stack-traces = false`**: kiểm soát kích thước log và tránh tạo dòng log lớn; stack trace có thể được ghi có kiểm soát tại biên xử lý lỗi khác.

**Cảnh báo:** `show-values = false` không tự động xóa **literal nằm trực tiếp trong CQL**. Nếu code tự nối chuỗi như `"SELECT ... WHERE email = 'alice@example.com'"`, chính văn bản câu query đã chứa dữ liệu nhạy cảm. Hãy dùng placeholder `?` với binding và tuyệt đối không dựa vào cắt ngắn `max-query-length` như một cơ chế che dữ liệu.

~~~java
// Nên dùng binding: giá trị được gửi riêng khỏi CQL template.
SimpleStatement safeQuery = SimpleStatement.builder(
        "SELECT state FROM orders_by_id WHERE order_id = ?")
    .addPositionalValue(orderId)
    .build();

// Không dùng nối chuỗi giá trị người dùng vào CQL.
// "SELECT ... WHERE email = '" + email + "'"
~~~

Việc ghi toàn bộ stack trace và các exception message cũng có thể làm lộ keyspace, table, CQL text hoặc chi tiết hạ tầng. Mã ứng dụng chỉ nên log các thuộc tính đã được đánh giá, để lỗi gốc nằm trong kênh nội bộ có giới hạn quyền khi thật sự cần phân tích.

## 6. Quy tắc xử lý dữ liệu nhạy cảm trong log

**Log, trace span và event metadata đều là dữ liệu được lưu lại.** Bất kỳ trường nào được xuất ra collector sẽ tạo thêm một bản sao ngoài database chính. Các trường nhạy cảm không nên được đưa vào log dù chỉ là môi trường debug, trừ khi có căn cứ nghiệp vụ rõ, được kiểm soát quyền và retention.

| Nhóm dữ liệu | Ví dụ | Cách xử lý khuyến nghị |
| --- | --- | --- |
| **Bí mật xác thực** | Password, token, API key, session cookie, private key. | **Không ghi** vào log/span/metric; phát hiện và chặn ở nguồn. |
| **Dữ liệu cá nhân** | Email, số điện thoại, địa chỉ, giấy tờ, IP gắn với người dùng theo chính sách. | Không log raw; dùng tên operation, ID kỹ thuật được phép hoặc token hóa có kiểm soát. |
| **Dữ liệu nghiệp vụ nhạy cảm** | Nội dung đơn hàng, số tài khoản, giá trị thanh toán, ghi chú người dùng. | Không log payload/entity/bind values. Chỉ log outcome và trường metadata đã qua allowlist. |
| **Partition key / clustering key** | `customer_id`, `order_id`, mã giao dịch. | Không mặc định là vô hại: khóa có thể định danh cá nhân hoặc cho phép truy ngược hành vi. |
| **CQL text** | Query với literal, comment, tên bảng bí mật. | Ưu tiên tên thao tác có kiểm soát như `orders.find_by_id`; nếu buộc lưu CQL, phải bảo đảm query đã được chuẩn hóa. |
| **Stack trace / exception** | Thông tin connection, tên host, câu query, message chứa tham số. | Giới hạn nơi lưu, quyền xem, lấy mẫu và redaction; tránh gửi trực tiếp ra response công khai. |
| **Trace/correlation ID** | UUID ngẫu nhiên của một request. | Có thể dùng để nối log nếu tạo độc lập, không mã hóa thông tin khách hàng và có thời hạn lưu hợp lý. |

**Redaction theo allowlist** an toàn hơn việc tìm và thay thế bằng regex trên toàn bộ log sau khi dữ liệu đã rời ứng dụng. Regex có thể bỏ sót biến thể encoding, payload JSON lồng nhau, URL escape hoặc tên field mới. Nếu trường thật sự cần được tương quan qua nhiều request, hãy đánh giá tokenization, HMAC có khóa quản lý riêng hoặc ID ngẫu nhiên. Hash thông thường của email/số điện thoại có không gian giá trị nhỏ có thể bị đoán bằng từ điển; **hash không mặc nhiên biến dữ liệu thành ẩn danh**.

### Các điểm dễ rò rỉ khi dùng Spring Data Cassandra

1. **Log entity/DTO:** `log.info("order={}", order)` có thể gọi `toString()` in cả trường nhạy cảm; tránh log cả entity ánh xạ bởi `@Table`.
2. **Log bind values:** driver request logger hoặc interceptor tự viết có thể xuất tham số của `PreparedStatement`/`BoundStatement`.
3. **CQL nối chuỗi:** giá trị nhạy cảm bị chèn thẳng vào văn bản câu query nên ngay cả việc tắt `show-values` cũng không đủ.
4. **Reactive logging:** `Flux.log()`/`doOnNext(value -> log.info(...))` có thể in từng entity và làm bùng nổ log; chỉ log metadata được phép.
5. **Exception và retry:** mỗi retry có thể log cùng lỗi nhiều lần, làm tăng dữ liệu nhạy cảm, số dòng và chi phí.
6. **Distributed trace attributes:** không đặt `db.query.parameter.*`, request body, raw user ID hoặc partition key vào span nếu chúng chưa được phê duyệt.
7. **CQL paging state:** đây là token điều hướng trạng thái truy vấn và có thể chứa thông tin nội bộ; không log raw hoặc đưa vào metrics tag. Giữ trong luồng paging phù hợp và bảo vệ khi gửi qua API.

Trong xử lý dữ liệu phân tán, một partition key hợp lệ như `customer_id` là tín hiệu tốt để driver định tuyến, nhưng **không phải nhãn tốt cho metrics**: số lượng giá trị không giới hạn vừa có thể lộ danh tính vừa tạo cardinality rất cao.

## 7. Log cấu trúc: đủ thông tin để vận hành, không ghi payload

Một record log hữu ích cho thao tác Cassandra thường chỉ cần:

- `operation`: tên hữu hạn do developer định nghĩa, ví dụ `orders.find_by_id`.
- `result`: `success`, `not_found`, `timeout`, `unavailable`, `overloaded` hoặc `other_error`.
- `elapsed_ms`, `attempt_count`, `consistency_level` và tên table/keyspace **nếu được phép**.
- `request_id` hoặc `trace_id` ngẫu nhiên dùng để tương quan giữa các lớp; không dùng raw user ID.

**Ví dụ log mong muốn:**

~~~json
{
  "event": "cassandra.request",
  "operation": "orders.find_by_id",
  "table": "orders_by_id",
  "result": "timeout",
  "elapsed_ms": 832,
  "attempt_count": 1,
  "consistency": "LOCAL_QUORUM",
  "request_id": "7c3a5328-b29d-4c53-8644-2876559f9ce6"
}
~~~

Đây là ví dụ về **các field ứng dụng tự chọn**, không khẳng định Spring Data/driver tự phát đúng JSON này. Cần cấu hình encoder JSON cho Logback/Log4j hoặc pipeline logging đang sử dụng.

### Ví dụ Java với tên thao tác và outcome được giới hạn

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.data.cassandra.core.CassandraTemplate;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

final class SafeLoggedOrderReader {
    private static final Logger log =
        LoggerFactory.getLogger(SafeLoggedOrderReader.class);
    private static final String OPERATION = "orders.find_by_id";

    private final CassandraTemplate template;

    SafeLoggedOrderReader(CassandraTemplate template) {
        this.template = template;
    }

    Optional<OrderById> find(UUID orderId, UUID requestId) {
        long started = System.nanoTime();
        String outcome = "other_error";
        try {
            OrderById value =
                template.selectOneById(orderId, OrderById.class);
            outcome = value == null ? "not_found" : "success";
            return Optional.ofNullable(value);
        } catch (DataAccessException error) {
            outcome = "database_error";
            // Chỉ phân loại lỗi nội bộ; không log entity, orderId,
            // bound values, raw CQL hay exception message ở đây.
            throw error;
        } finally {
            long elapsedMs =
                TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started);
            log.info(
                "event=cassandra.request operation={} outcome={} " +
                "elapsed_ms={} request_id={}",
                OPERATION, outcome, elapsedMs, requestId);
        }
    }
}
~~~

Giả định đã có entity `OrderById` ánh xạ tới bảng có `order_id` là primary key. Ví dụ minh họa cách ghi **metadata có kiểm soát**; production có thể thêm phân loại lỗi thành nhóm hữu hạn `ReadTimeout`/`Unavailable`/`Overloaded` (lần theo cause của `DataAccessException` và driver exception) và đo metric tương ứng.

Trong dịch vụ thực, cần có nguồn tạo `requestId` tin cậy: chẳng hạn ID ngẫu nhiên do hệ thống sinh và chỉ chấp nhận các header tương quan từ client sau khi kiểm tra định dạng/giới hạn độ dài. **Không đưa nguyên văn header tùy ý của client** vào log vì có nguy cơ log injection và làm giả record. Tránh đặt toàn bộ stack trace tại mọi request khi xảy ra sự cố hàng loạt; nếu cần lưu lỗi chi tiết, sử dụng log level/limiter và hệ thống quyền xem thích hợp.

### Reactive: không giả định ThreadLocal/MDC theo request tự lan truyền

Trong Reactor, thread có thể thay đổi giữa các tín hiệu. Nếu app dùng MDC của SLF4J thuần ThreadLocal, việc đặt `MDC.put("request_id", ...)` ở thread HTTP rồi mặc nhiên cho rằng mọi `map`/`flatMap` sẽ thấy ID đó là không đáng tin cậy.

Reactor `Context` và tích hợp tracing/context propagation được hỗ trợ có thể mang correlation metadata theo subscription; logging ở `doOnError`/`doFinally` phải đọc đúng context hoặc dùng instrumentation đã cấu hình.

~~~java
import reactor.core.publisher.Mono;

Mono<OrderById> readOrder(UUID id, String requestId) {
    return repository.findById(id)
        .doOnError(error -> {
            // Log tên operation và nhóm lỗi từ bộ phân loại.
            // Không log nguyên object OrderById hoặc biến 'id'.
        })
        .contextWrite(context -> context.put("request_id", requestId));
}
~~~

`contextWrite` cung cấp metadata cho luồng Reactor; **nó không tự động chuyển mọi key trong Context thành MDC hoặc span attributes**. Các bước tích hợp quan sát phải được thiết lập rõ và kiểm thử ở nơi có đổi scheduler.

## 8. Tracing trong Spring Data Cassandra: nên gắn span ở đâu?

Trong distributed tracing, các span hợp lý thường phản ánh:

~~~text
HTTP GET /orders/{id}              [server span]
  └─ orders.get_state              [service span]
      └─ cassandra.orders.read     [client/database span]
           + db.system = "cassandra"
           + db.operation.name = "SELECT"
           + db.collection.name = "orders_by_id"
           + outcome = "success" | "timeout" | ...
~~~

Tên attribute chỉ mang tính ví dụ cho semantic convention đang sử dụng; cần theo đúng phiên bản OpenTelemetry/instrumentation đã triển khai. Cùng một ứng dụng có thể được instrumentation tự động cho driver hoặc Spring, do đó **không tạo span thủ công trùng lặp** nếu đã có span client từ instrumentation.

Quy tắc thiết kế:

- Tên span và operation có **cardinality thấp**: `orders.read_by_id`, không tạo tên `orders.read_550e8400-...`.
- Attribute phục vụ điều tra như `db.system`, tên thao tác, trạng thái lỗi, duration, số attempt thường hữu ích hơn raw CQL.
- Không đưa partition key, bound values, user ID, request body hay access token vào span.
- Thu thập lỗi với **error class được chuẩn hóa**; kiểm soát việc ghi exception stack/message chi tiết.
- Tách rõ **cơ chế sampling distributed trace** với cờ `Statement.setTracing(true)` của Cassandra; không bật query tracing cho toàn bộ request chỉ vì parent HTTP span được sample.
- Nếu dùng trace propagation qua nhiều service, dùng định dạng context chuẩn và chỉ tin tưởng dữ liệu ở trust boundary đã kiểm soát.

### Span, log và metrics có vai trò khác nhau

Metrics tốt để biết `orders.read_by_id` có p99 cao. Span lấy mẫu giúp định vị đoạn nào trong một request chậm. Query trace Cassandra chuyên sâu giúp xem coordinator/replica làm gì bên trong một truy vấn cụ thể. Application log cung cấp các sự kiện nghiệp vụ hoặc lỗi đã chuẩn hóa. Kết hợp đúng các lớp cho tín hiệu đủ mạnh mà không cần log từng entity/row.

Không dùng một span cho **mỗi hàng** trong truy vấn Cassandra có hàng nghìn row hoặc mỗi phần tử của `Flux`; chi phí instrumentation và xuất dữ liệu có thể vượt chính tác vụ đang đo. Với paging, có thể thu `page_count`, `total_rows_bucket` hoặc duration theo truy vấn ở một nhóm nhãn hữu hạn nếu nghiệp vụ cần.

## 9. Metrics: giám sát liên tục nhưng kiểm soát cardinality

Không nên phụ thuộc hoàn toàn vào tracing vì traffic không được sample vẫn có thể gặp lỗi. Metrics với nhãn hữu hạn cho phép quan sát toàn bộ dòng yêu cầu.

| Metric gợi ý | Nhãn được phép | Tuyệt đối tránh dùng làm nhãn |
| --- | --- | --- |
| `cassandra_requests_total` | `operation`, `result`, `consistency` | `order_id`, `customer_id`, CQL query string có literal. |
| `cassandra_request_duration_seconds` | `operation`, `result` | request ID, trace ID, partition key. |
| `cassandra_driver_inflight` | `service`, `session` (tên hữu hạn) | address động không chuẩn hóa, ID mỗi request. |
| `cassandra_driver_throttled_total` | `operation`, `reason` (enum hữu hạn) | exception message thô. |
| `cassandra_query_trace_selected_total` | `operation`, `decision` | trace ID, user ID. |
| `observability_export_failures_total` | `exporter`, `reason` (enum) | full URL mang query parameters/token. |

Có thể triển khai các tên metric này bằng Micrometer hoặc framework quan sát hiện tại; chúng là **tên minh họa do ứng dụng tự định nghĩa**, không phải danh sách chắc chắn có sẵn trong Java Driver.

Giả sử metric `cassandra_requests_total` thêm nhãn `order_id` và mỗi ngày có 1 triệu đơn hàng, số time series có thể tăng lên mức rất lớn khi nhân tiếp với kết quả, method, instance... Hãy để correlation ID trong log/span có retention hợp lý; metric chỉ lưu **nhóm** hành vi.

Chỉ số vận hành quan trọng:

1. Latency p50/p95/p99 và throughput theo operation; đọc, ghi và paging nên được phân biệt khi có access pattern khác nhau.
2. Tỉ lệ `ReadTimeout`, `WriteTimeout`, `Unavailable`, `Overloaded`, `RequestThrottlingException`; không gom mọi lỗi thành `500`.
3. Số request in-flight, queue, connection pool, retry/speculative execution và timeout ở driver.
4. CPU, I/O, GC, compaction, tombstone, pending tasks và dropped messages trên các Cassandra node.
5. Traces/giây được chọn, traces bị loại do quota, lượng byte xuất, tốc độ ingest, độ trễ collector và dung lượng storage.

**Mục tiêu:** muốn giảm tracing cost thì đo **chi phí thực của tracing** và ảnh hưởng latency/CPU, không chỉ đo độ lớn của file log.

## 10. Retention, quyền truy cập và đường đời dữ liệu quan sát

Mỗi loại dữ liệu cần lifecycle rõ ràng từ lúc tạo đến khi xóa:

~~~mermaid
flowchart LR
    A["Phát sinh metric/log/span/trace"] --> B{"Allowlist + sampling + quota"}
    B -- "Loại" --> X["Không xuất"]
    B -- "Giữ" --> C["Collector / transport bảo vệ"]
    C --> D["Storage có phân quyền"]
    D --> E["TTL / retention policy"]
    E --> F["Xóa theo vòng đời"]
~~~

Những kiểm soát nên có:

- **Data minimization:** chỉ gửi trường phục vụ vận hành. Redact **trước khi rời ứng dụng** hoặc collector tin cậy; không xem retention ngắn là biện pháp thay thế.
- **Phân quyền:** giới hạn người bật tracing, người truy cập trace, log search và dashboard; kiểm toán quyền truy cập nếu cần.
- **Transport/storage:** dùng kết nối an toàn, mã hóa ở nơi lưu khi phù hợp, giữ secret của exporter bên ngoài log và cấu hình build.
- **Retention theo loại:** metrics tổng hợp có thể cần giữ khác với debug logs hoặc query traces; cấu hình theo yêu cầu pháp lý và chính sách tổ chức, không dùng một thời hạn cho mọi dữ liệu.
- **Xóa và kiểm soát bản sao:** trace/log có thể được chuyển tiếp qua queue, object storage, backup và hệ thống phân tích; xóa ở dashboard không bảo đảm mọi bản sao đã bị xóa.
- **Debug có thời hạn:** cấu hình tracing tạm phải tự hết hạn, có người chịu trách nhiệm và dấu vết thay đổi.

Đối với `system_traces`, cần kiểm tra TTL và retention do phiên bản Cassandra/cluster quản lý. Không tự sửa schema hay TTL của keyspace hệ thống để giảm dung lượng mà chưa đánh giá tác động. Dữ liệu query tracing có thể chứa metadata nội bộ nhạy cảm và chỉ nên cấp quyền đọc cho nhóm vận hành cần thiết.

### Nếu đã vô tình log thông tin nhạy cảm

Không chỉ thêm regex để che những log mới. Cần xác định **nguồn rò**, tắt đoạn instrumentation/logging gây rò, giới hạn ngay quyền truy cập bản ghi cũ, kiểm tra đường xuất/bản sao, thực hiện quy trình xử lý sự cố dữ liệu và xóa hoặc quản lý retention theo chính sách. Nếu token/secret bị lộ, cần luân chuyển hoặc vô hiệu hóa theo quy trình quản trị secret. Ghi nhận sự cố bằng metadata tối thiểu để không tiếp tục nhân bản dữ liệu nhạy cảm trong ticket.

## 11. Kiểm thử ngân sách và kiểm soát dữ liệu

Lớp `QueryTraceGate` có thể được test **không cần Cassandra** bằng JUnit và `Clock.fixed`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class QueryTraceGateTest {
    @Test
    void neverExceedsLocalBudget() {
        Clock fixed = Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC);
        QueryTraceGate gate = new QueryTraceGate(fixed, 1.0, 2);

        assertTrue(gate.shouldTrace());
        assertTrue(gate.shouldTrace());
        assertFalse(gate.shouldTrace());
    }

    @Test
    void canBeDisabled() {
        Clock fixed = Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC);
        QueryTraceGate gate = new QueryTraceGate(fixed, 0.0, 100);

        for (int i = 0; i < 100; i++) {
            assertFalse(gate.shouldTrace());
        }
    }
}
~~~

Hai test này xác minh hạn mức và khả năng tắt sampling, không kiểm thử xác suất ngẫu nhiên hay khả năng giới hạn **toàn bộ cụm ứng dụng**. Với triển khai thực tế, bổ sung test chạy đồng thời ở nhiều thread để kiểm tra hạn mức dưới cạnh tranh, kiểm thử cấu hình debug hết hạn và xác minh không có trace nào được chọn khi ứng dụng đang ở chế độ bảo vệ quá tải.

### Kiểm thử không rò dữ liệu trong log

Nên thiết kế integration test có thể **bắt log output** bằng một appender test rồi kiểm tra các chuỗi sentinel như `TEST_SECRET_TOKEN_123` không xuất hiện ở bất kỳ record nào khi:

1. Gọi query thành công với parameter chứa dữ liệu sentinel trong môi trường kiểm thử.
2. Truy vấn thất bại vì timeout hoặc lỗi schema, tạo exception từ Spring Data/driver.
3. Bật request logger ở mức thử nghiệm và kiểm tra `show-values = false`.
4. Gọi reactive pipeline có `doOnError`/`doFinally`, thay đổi scheduler và subscriber.
5. Gọi endpoint debug có quyền hạn, kiểm tra cả HTTP response, trace spans và event attributes.

Thay vì chỉ assert `log.contains("***")`, hãy bảo đảm **secret thật không xuất hiện** trong serialized JSON/log, span exporter và HTTP error body. Kiểm tra cả raw CQL literal, entity `toString()`, exception message và header độc hại chứa newline; test nên fail nếu các nguồn này thoát ra khỏi allowlist.

### Kiểm thử hiệu năng trước và sau khi bật tracing

Trong môi trường kiểm soát, chạy cùng một workload với (a) tracing tắt, (b) sampling nhỏ có quota, (c) sampling cao hơn trong phạm vi an toàn. Đo:

| Chỉ số | Điều cần xác minh |
| --- | --- |
| Throughput thành công và latency p95/p99 | Tracing không làm tăng độ trễ vượt ngân sách cho phép. |
| CPU/I/O/heap client và Cassandra | Trace events và exporter không làm quá tải node hoặc JVM. |
| Trace events, byte/giây, storage growth | Tổng lượng dữ liệu phù hợp ngân sách theo thời gian. |
| Dropped spans/logs, exporter errors | Pipeline quan sát có bị nghẽn hoặc mất dữ liệu không? |
| Số request tracing thực tế | Có giữ được giới hạn tuyệt đối và quota per-operation không? |
| Độ chính xác điều tra | Một trace được chọn có đủ ngữ cảnh để xác định coordinator, lỗi và phần chậm không? |

Không dùng production làm nơi thử nghiệm trace 100% khi Cassandra đã quá tải. Tốt hơn nên tạo traffic, partition distribution, page size và consistency level đại diện trong môi trường thử nghiệm, rồi dùng tính năng debug hạn chế trên production chỉ khi cần và có người chịu trách nhiệm.

## 12. Quy trình xử lý sự cố: p99 tăng và ReadTimeout xuất hiện

**Tình huống:** API đọc trạng thái đơn hàng bằng `ReactiveCassandraRepository.findById(orderId)` có p99 tăng từ 150 ms lên 2,5 giây; lỗi `ReadTimeout` tăng sau khi chạy một chiến dịch. Bảng `orders_by_id` có `order_id` làm partition key và API yêu cầu `LOCAL_QUORUM`.

Quy trình gợi ý:

1. **Xác nhận ảnh hưởng bằng metrics:** tỉ lệ request lỗi, latency p99 theo operation, mức tải coordinator/replica, queue, timeout và retry rate. Không bật tracing tất cả request để bắt đầu điều tra.
2. **Xác định phạm vi:** xem lỗi tập trung ở table, cluster/datacenter, coordinator hoặc một nhóm partition. Đối chiếu RF, CL, trạng thái replica, GC/compaction và dropped messages.
3. **Thu log tối thiểu:** `operation=orders.find_by_id`, `result=read_timeout`, `elapsed_ms` và `request_id` đã được tạo an toàn. Không log `orderId`, entity hoặc dữ liệu bind.
4. **Bật tracing chọn lọc:** ví dụ sampling 0,1% kèm quota 10 query traces/phút/instance, chỉ cho operation đang bị ảnh hưởng trong một cửa sổ ngắn. Hai con số là ví dụ; chọn theo kết quả đo và số instance. Nếu cluster rất yếu, ưu tiên metric/log hiện có và giảm tải trước.
5. **Tương quan ID:** lưu một Cassandra `tracingId` riêng từ `ExecutionInfo` và một application/distributed `trace_id` nếu được sample. Giới hạn người được phép xem chi tiết trong `system_traces`.
6. **Đọc dấu hiệu:** so thời gian coordinator/replica, số request pending, tombstone, kích thước partition và pattern query. Nếu một partition quá nóng, thay đổi mô hình dữ liệu hoặc phân phối workload; thêm tracing không sửa được hot partition.
7. **Khắc phục và tắt debug:** sửa nút thắt, kiểm tra throughput/latency/tỉ lệ lỗi trở về SLO, vô hiệu hóa phiên trace tăng cường và xác minh dữ liệu quan sát có retention đúng chính sách.

Nếu một phép **ghi** trả `WriteTimeout`, không log raw payload để đối soát và không retry mù. Có thể một số replica đã áp dụng mutation. Dùng operation ID/idempotency key phù hợp với nghiệp vụ để xác định trạng thái; observability không thay thế cơ chế xử lý trạng thái ghi chưa xác định.

## 13. Checklist trước khi triển khai

| Câu hỏi | Kết quả mong muốn |
| --- | --- |
| Query tracing có bị bật mặc định cho mọi request không? | **Không**; chỉ bật có phạm vi, quota và thời hạn. |
| RequestLogger có ghi bound values hoặc query literal chứa thông tin cá nhân không? | **Không**; dùng prepared/bound parameters, tắt `show-values` và kiểm soát CQL template. |
| Tên span, metric tag có chứa partition key/user ID/trace ID không? | **Không**; tag có cardinality thấp, dùng operation đã định nghĩa. |
| Có phân biệt Cassandra query tracing với distributed tracing không? | **Có**; biết rõ ID, chỗ lưu và chi phí từng loại. |
| Lấy chi tiết `system_traces` có được giới hạn và phân quyền không? | **Có**; chỉ fetch khi cần điều tra, không dump toàn bộ events. |
| Có deadline và phương án tự tắt debug không? | **Có**; có người chịu trách nhiệm và cảnh báo vượt ngân sách. |
| Có kiểm thử không lộ secret trong log/span và HTTP error body không? | **Có**; test có sentinel ở đường thành công và đường lỗi. |
| Có đo overhead thực khi bật sampling không? | **Có**; latency, tài nguyên, ingest, byte và tỉ lệ dữ liệu hữu ích. |

## 14. Kết luận

Quan sát tốt trong Spring Data Cassandra bắt đầu bằng **metrics và log có cấu trúc**, rồi dùng distributed tracing hoặc Cassandra query tracing có chọn lọc khi cần phân tích đường đi và hoạt động nội bộ. Bật toàn bộ tracing, xuất mọi bind value hoặc log từng entity đều làm tăng chi phí và có thể mở rộng phạm vi rò dữ liệu. Đặt sampling có quota tuyệt đối, hạn chế trace detail, chuẩn hóa tên operation, kiểm soát cardinality, dùng allowlist cho log/span và thực hiện retention cùng phân quyền rõ ràng. Khi điều tra hiệu năng, luôn quay lại những yếu tố nền tảng của Cassandra: **partition key, RF/consistency level, paging, hot partition, tombstone và tải coordinator/replica**.

### Tài liệu tham khảo

- [Apache Cassandra Java Driver 4.18 — Query tracing](https://apache.github.io/cassandra-java-driver/4.18.0/core/tracing/).
- [Java Driver 4.17 — Request tracker](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/request_tracker/).
- [Java Driver 4.17 — Reference configuration](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/configuration/reference/).
- [Spring Data Cassandra — Reference Documentation](https://docs.spring.io/spring-data/cassandra/reference/).
- [OpenTelemetry — Concepts: Sampling](https://opentelemetry.io/docs/concepts/sampling/).
- [OpenTelemetry — Semantic conventions](https://opentelemetry.io/docs/specs/semconv/).
