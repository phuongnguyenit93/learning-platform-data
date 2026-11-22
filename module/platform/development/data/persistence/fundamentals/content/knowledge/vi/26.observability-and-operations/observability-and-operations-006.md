# Liên kết trace ứng dụng với thao tác lưu trữ

Một khách hàng gọi API đặt hàng và nhận phản hồi sau 2,8 giây. Log ứng dụng chỉ ghi **POST /orders 2800 ms**, trong khi dashboard PostgreSQL báo đa số truy vấn chỉ chạy vài chục mili giây. Vì sao yêu cầu chậm? Có thể ứng dụng đã đợi **connection pool** 1,5 giây, database chờ **row lock** 900 ms, một truy vấn JDBC thực thi 200 ms, còn phần còn lại nằm ở xử lý nghiệp vụ và serialization. Nếu chỉ nhìn một dòng log hoặc chỉ đo thời gian câu SQL, nhóm vận hành rất dễ tối ưu sai chỗ.

**Distributed tracing** giúp liên kết các thao tác thuộc **cùng một yêu cầu** bằng trace và span có quan hệ cha–con, cho thấy thời gian được tiêu thụ trên đường từ HTTP controller, application service, transaction, ORM/JDBC đến database và những dịch vụ liên quan. Để hữu ích, trace phải được tạo và truyền **đúng ngữ cảnh**, ghi nhận **ranh giới thực sự**, tránh thu thập dữ liệu bí mật, đồng thời phối hợp với metrics/logs và quan sát phía DB.

Bài thuộc chương **Quan sát và vận hành** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Phạm vi module là hiểu nguyên lý persistence bền vững trong Java: chọn mô hình dữ liệu, schema, truy vấn, chỉ mục, giao dịch, cô lập, kiểm soát đồng thời, xử lý kết nối, tiến hóa schema, bảo mật, sao lưu và hiệu năng. Ví dụ dùng **OpenTelemetry, Spring Boot, JDBC, JPA/Hibernate, HikariCP và PostgreSQL**. Tên thuộc tính hay hành vi tự động instrument có thể khác theo phiên bản thư viện và semantic conventions; cần kiểm tra cấu hình thực tế trước khi suy luận từ một span.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **trace ID, span ID, parent span, span event, status, context propagation và sampling**.
- Đọc cây trace để phân biệt **thời gian ứng dụng, chờ connection, thực thi JDBC, chờ khóa và commit**.
- Bổ sung instrumentation cho Java/Spring bằng **OpenTelemetry**, kết hợp span nghiệp vụ thủ công với instrumentation JDBC/HTTP có sẵn mà không tạo trùng lặp.
- Liên kết trace với **structured log, application metrics, HikariCP, pg_stat_activity và pg_stat_statements** mà không giả định hai hệ thống có cùng transaction ID.
- Nhận ra **N+1 queries**, transaction kéo dài, pool exhaustion, optimistic conflict, deadlock và retry gây chậm.
- Thiết kế **attribute, span name, error classification, sampling và retention** an toàn về dữ liệu cá nhân và cardinality.
- Phân tích được những điều trace **không chứng minh** và thiết lập playbook kiểm tra end-to-end khi persistence chậm.
- Kiểm thử việc tạo span, truyền context qua async và ghi nhận lỗi trong điều kiện ứng dụng thật.

## 2. Tracing trả lời câu hỏi nào?

Một hệ thống thường cần ba tín hiệu bổ sung cho nhau:

| Tín hiệu | Thường trả lời | Không tự trả lời đầy đủ |
| --- | --- | --- |
| **Metrics** | Tần suất, p95/p99 latency, error rate, pool saturation, xu hướng | Một request cụ thể đi qua những bước nào |
| **Logs** | Sự kiện, quyết định và lỗi có timestamp/metadata | Quan hệ thời gian cha–con nếu thiếu correlation |
| **Traces** | Đường đi và quan hệ giữa các thao tác của một request được lấy mẫu | Mọi request trên hệ thống, trạng thái DB toàn cục, nguyên nhân từ phía DB nếu không có instrumentation đủ sâu |

Ví dụ trace:

~~~text
trace_id = 9fd... (rút gọn chỉ để minh họa)

POST /orders                        2800 ms
  |
  +-- checkout.place_order          2690 ms
       |
       +-- pool.acquire             1480 ms
       |
       +-- DB INSERT orders          210 ms
       |
       +-- DB UPDATE inventory       920 ms
       |
       +-- transaction.commit         55 ms
       |
       +-- serialize/other           ...
~~~

Sơ đồ minh họa, không phải tuyên bố mọi Java agent tự sinh đúng các tên span trên. **Một instrumentation có thể không đo riêng pool.acquire hoặc transaction.commit**; khi thiếu span, chỉ biết một khoảng trống hoặc khoảng thời gian bao trùm, chưa biết chắc nó là chờ pool.

Mục tiêu của tracing là **đặt câu hỏi chính xác hơn để kiểm chứng**, không thay thế SQL execution plan, PostgreSQL statistics hoặc hồ sơ sự cố.

## 3. Các khái niệm cốt lõi

- **Trace:** biểu diễn một đường xử lý logic của request hoặc công việc có liên quan.
- **Trace ID:** định danh chung cho các span thuộc trace; được dùng để liên kết log/trace, không phải khóa xác thực.
- **Span:** một đơn vị công việc có tên, thời điểm bắt đầu/kết thúc, thuộc tính và có thể có lỗi hoặc events.
- **Span ID:** định danh của một span trong trace.
- **Parent/child:** biểu diễn quan hệ nhân quả hoặc lời gọi lồng nhau; các child spans không bắt buộc chạy hoàn toàn tuần tự.
- **Span context:** thông tin đủ để nhận diện span/trace và truyền quan hệ qua ranh giới thread, tiến trình hoặc mạng.
- **Span event:** dấu mốc bên trong span, ví dụ bắt đầu một lần retry hoặc quyết định chuyển sang đọc primary.
- **Span status:** trạng thái theo mô hình telemetry; cần phân biệt với **HTTP status** hoặc kết quả nghiệp vụ.
- **Span link:** liên hệ một span với context khác khi không có quan hệ cha–con trực tiếp, phù hợp một số quy trình hàng đợi/batch.
- **Sampling:** chọn những trace/span được thu thập, export hoặc lưu; trace không xuất hiện không có nghĩa request đã không diễn ra.

Ví dụ:

~~~text
Trace A
  Span S1: HTTP server
    Span S2: checkout service
      Span S3: JDBC execute
      Span S4: call payment service
        Span S5: HTTP client

Trace B
  Span S6: message consumer (có thể link với context producer A)
    Span S7: INSERT outbox result
~~~

**Không phải mọi event bất đồng bộ phải là child span**. Khi một message được xử lý sau nhiều giờ hoặc gom từ nhiều producer, dùng span link, correlation và context đúng semantics có thể phù hợp hơn kéo dài một trace cha qua toàn bộ thời gian chờ.

## 4. Chọn ranh giới span để giải thích persistence

Trong một request ghi đơn hàng, các mốc có ý nghĩa khác nhau:

~~~text
HTTP handler
    |
    v
Application service bắt đầu use case
    |
    v
Transaction bắt đầu / xin connection
    |
    +-- Chờ pool cấp logical connection
    |
    v
Connection được cấp, chuẩn bị PreparedStatement
    |
    +-- JDBC executeQuery/executeUpdate
    +-- ResultSet fetch / map entity
    +-- ORM dirty checking / flush
    |
    v
COMMIT hoặc ROLLBACK
    |
    v
Service trả kết quả và HTTP response hoàn tất
~~~

Các khoảng phải được đặt đúng tên:

| Khoảng thời gian | Nguồn đo có thể dùng | Thận trọng khi kết luận |
| --- | --- | --- |
| **HTTP request latency** | HTTP server span và metrics | Bao gồm filter, auth, serialization và các dependency |
| **Application service duration** | Span nghiệp vụ thủ công/auto | Có thể kết thúc trước commit nếu proxy quản lý transaction bên ngoài |
| **Connection acquisition time** | HikariCP metrics hoặc instrumentation pool | Không phải thời gian query trên server |
| **JDBC call duration** | JDBC spans/instrumentation | Bao gồm driver, mạng và có thể chờ lock; không đồng nhất với PostgreSQL executor time |
| **Result mapping/stream consumption** | Span riêng khi cần và có ranh giới đúng | Cursor fetch, ORM materialization và consumer có thể diễn ra sau execute |
| **Transaction commit time** | Span quanh transaction boundary hoặc DB instrumentation | Không mặc định bằng tổng thời gian của các câu UPDATE |
| **DB lock wait** | pg_stat_activity/pg_locks, wait events | Trace JDBC chỉ cho biết lời gọi đang chậm, không tự chứng minh chờ lock |

**Không cộng thời lượng mọi child span để ra thời lượng request.** Child có thể lồng nhau hoặc chạy song song; tổng của chúng có thể lớn hơn parent. Khi phân tích, xem **timeline, overlap và critical path**.

## 5. Trace context và W3C Trace Context

Để server A gọi server B mà vẫn thuộc một trace, A cần truyền **context** qua giao thức, thường dùng W3C Trace Context:

~~~text
Client                  Service A                   Service B
  |                         |                           |
  |-- HTTP request -------->|                           |
  |                         |-- HTTP call -------------->|
  |                         |   traceparent header       |
  |                         |                           |
  |                         |                 tạo child span
  |<------------------------|<---------------------------|
~~~

Các trường như **traceparent** mang thông tin nhận diện trace và span cha; **tracestate** cung cấp dữ liệu theo ngữ cảnh tracing tương ứng. Header này **không phải credential** và không được dùng làm bằng chứng người gọi có quyền.

Một số nguyên tắc:

1. **Extract** context ở ranh giới nhận request/message.
2. **Make current** span khi thực hiện công việc thuộc nó.
3. **Inject** context sang outbound HTTP/gRPC/message khi công nghệ và chính sách yêu cầu.
4. **Khôi phục Scope** khi kết thúc để không rò context sang request khác trên thread được tái sử dụng.
5. Không sinh trace ID tùy tiện trong mỗi repository method nếu nó đang nằm trong request đã có trace.
6. Đánh giá mức tin cậy khi nhận trace headers từ ngoài: cần validate định dạng, giới hạn baggage và áp sampling policy của hệ thống.

**Baggage** có thể truyền metadata qua nhiều dịch vụ, nên không đặt mật khẩu, token, email, SQL parameters hoặc dữ liệu nhạy cảm vào đó. Baggage còn có chi phí kích thước header và nguy cơ truyền dữ liệu quá phạm vi cần thiết.

## 6. OpenTelemetry trong ứng dụng Java

**OpenTelemetry** cung cấp API/SDK và cơ chế instrumentation cho trace, metrics và logs. Với ứng dụng Java, có hai hướng bổ sung:

- **Automatic instrumentation:** Java agent hoặc starter/instrumentation tương thích có thể tạo span cho HTTP, JDBC, framework, outbound clients và một số thư viện.
- **Manual instrumentation:** code chủ động tạo span cho **ý nghĩa nghiệp vụ hoặc ranh giới không được đo tự động**, ví dụ quyết định retry, chờ một công đoạn xử lý, hoặc thao tác import một chunk.

Một lệnh chạy **minh họa cấu hình**:

~~~text
java -javaagent:/opt/otel/opentelemetry-javaagent.jar \
  -Dotel.service.name=order-service \
  -Dotel.exporter.otlp.endpoint=http://otel-collector:4317 \
  -jar order-service.jar
~~~

Trong một số môi trường, tham số endpoint/protocol, biến môi trường và cách cấu hình exporter phụ thuộc phiên bản agent/collector; cần kiểm tra chúng tương thích. Ví dụ này không mô tả cơ chế TLS/xác thực production. **Không gửi telemetry chứa dữ liệu nhạy cảm qua HTTP không bảo vệ ở môi trường thật**.

Quy tắc triển khai:

1. Định danh dịch vụ ổn định, ví dụ **service.name=order-service** thay vì tên pod thay đổi ở mỗi lần deploy.
2. Ghi **service.version** và **deployment.environment** qua resource attributes thích hợp để so sánh các bản phát hành.
3. Kiểm tra spans thực tế xuất hiện; không mặc định agent nào cũng instrument mọi ORM/pool/version.
4. Không bật đồng thời nhiều cơ chế cùng instrument một JDBC call mà không kiểm tra, vì có thể tạo **hai spans trùng** và đếm thời lượng sai.
5. Dùng **OpenTelemetry Collector** hoặc backend tương đương để nhận, xử lý, lấy mẫu và lưu theo chính sách.
6. Theo dõi lỗi exporter và lượng telemetry bị drop, tránh để pipeline observability làm chậm đường nghiệp vụ chính.

**Instrument được thư viện** không có nghĩa đã hiểu hết nguyên nhân hiệu năng: một span ghi **db.client.operation** chậm chỉ là điểm bắt đầu để tìm vị trí chờ bên dưới.

## 7. Tạo span nghiệp vụ thủ công trong Java

Giả sử application service thực hiện thao tác tạo đơn qua **TransactionTemplate** và **JdbcTemplate**. Mục tiêu là tạo **một span bao trùm cả transaction**, trong khi JDBC instrumentation, nếu bật, sẽ tạo các child spans cho SQL thực tế:

~~~java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public final class OrderCommandService {
    private static final Tracer TRACER =
            GlobalOpenTelemetry.getTracer("order-persistence");

    private final TransactionTemplate transactions;
    private final JdbcTemplate jdbc;

    public OrderCommandService(
            TransactionTemplate transactions, JdbcTemplate jdbc) {
        this.transactions = transactions;
        this.jdbc = jdbc;
    }

    public long createOrder(long tenantId, long customerId) {
        Span span = TRACER.spanBuilder("orders.create")
                .setSpanKind(SpanKind.INTERNAL)
                .startSpan();
        span.setAttribute("app.operation", "create_order");

        try (Scope scope = span.makeCurrent()) {
            Long id = transactions.execute(status ->
                    jdbc.queryForObject(
                        """
                        INSERT INTO orders
                            (tenant_id, customer_id, status)
                        VALUES (?, ?, ?)
                        RETURNING id
                        """,
                        Long.class, tenantId, customerId, "NEW"));

            if (id == null) {
                throw new IllegalStateException("No generated order id");
            }
            return id;
        } catch (RuntimeException ex) {
            span.recordException(ex);
            span.setStatus(StatusCode.ERROR);
            throw ex;
        } finally {
            span.end();
        }
    }
}
~~~

Giả định **orders**, TransactionTemplate, JdbcTemplate và transaction manager đã được cấu hình; câu SQL **RETURNING** là cú pháp PostgreSQL. Đây là ví dụ về **ngữ cảnh telemetry**, không phải use case hoàn chỉnh: nghiệp vụ thực cần xác thực tenant, idempotency key, điều kiện tồn kho, handling lỗi và validation.

Lưu ý:

- **Scope** làm span hiện hành trong thread hiện tại; các JDBC spans tương thích có thể trở thành child của **orders.create**.
- **TransactionTemplate.execute** chỉ trả kết quả sau khi transaction manager thực hiện việc kết thúc transaction theo cấu hình, nên ranh giới span bao ngoài có thể ghi nhận lỗi ở thời điểm commit. Điều này khác với việc tự tạo span chỉ bên trong một method **@Transactional** được Spring proxy bọc.
- Gọi **recordException** và đặt **StatusCode.ERROR** khi một lỗi thật sự làm use case thất bại; không đánh dấu mọi business rejection như lỗi hệ thống nếu đó là kết quả hợp lệ của API.
- Tránh gắn **customerId**, email, số thẻ, payload hoặc SQL có literal vào attributes nếu không có chính sách bảo mật cụ thể.
- Nếu Java agent đã tạo span cấp service theo tên này, cần xem có bị trùng hay không. Manual span nên thêm ngữ nghĩa mà instrumentation tự động chưa có.

## 8. Spring @Transactional và vị trí commit trong trace

Một nhầm lẫn thường gặp:

~~~java
@Transactional
public void updateProfile(...) {
    Span span = tracer.spanBuilder("profile.update").startSpan();
    try (Scope scope = span.makeCurrent()) {
        repository.update(...);
    } finally {
        span.end();
    }
}
~~~

Với **Spring proxy-based transaction management**, transaction interceptor có thể bắt đầu transaction **trước khi vào method body** và COMMIT **sau khi method body trả về**. Do đó span thủ công bên trong method trên có thể kết thúc **trước commit**, bỏ sót phần commit latency hoặc lỗi phát hiện trong lúc flush/commit.

~~~text
Transaction interceptor
    BEGIN / mở transaction
       |
       +-- vào method service
       |     span profile.update
       |       repository UPDATE
       |     kết thúc span
       |
    COMMIT hoặc ROLLBACK
       |
    trả về controller / ném exception
~~~

Các lựa chọn:

- Tạo span ở **tầng gọi ngoài proxy** nếu cần đo cả hành vi transaction.
- Dùng **TransactionTemplate** và span bao bên ngoài như mục 7.
- Sử dụng instrumentation transaction manager/driver phù hợp nếu cần phân biệt thời gian commit.
- Quan sát **HTTP server span** và trạng thái exception mapping để không đánh dấu request thành công trước khi transaction thực sự hoàn tất.

Không sửa transaction boundary chỉ để “làm đẹp trace”. Bất biến dữ liệu, propagation và retry policy phải giữ nguyên. Ngoài ra, **Spring self-invocation** có thể bỏ qua proxy **@Transactional**, làm thời điểm commit thực tế khác với điều người viết code tưởng tượng.

## 9. Liên kết connection pool với SQL execution

Một JDBC query chậm đôi khi do **chưa có connection**:

~~~text
Application gọi DataSource.getConnection()
                |
                +-- chờ pool cấp connection 850 ms
                |
                v
Lấy được connection
                |
                +-- execute SELECT 40 ms
                |
                v
Trả kết quả
~~~

Nếu chỉ có span SQL **40 ms**, tổng request vẫn có thể vượt 900 ms. Cần kết hợp:

- **HikariCP connection acquisition metrics:** thời gian chờ mượn connection.
- **Active/idle/pending connections** của pool.
- **Connection usage duration**: thời gian một logical connection được mượn.
- **JDBC statement spans**: thời lượng thực thi được instrumentation quan sát.
- **Transaction duration**: giao dịch có giữ connection trong khi chờ dịch vụ khác hay không.

Ví dụ metrics quan trọng:

| Chỉ số | Ý nghĩa |
| --- | --- |
| **connections.active** | Connection đang được mượn |
| **connections.idle** | Connection rảnh trong pool |
| **connections.pending** | Thread đang chờ mượn |
| **connection.acquire duration** | Thời gian xin connection |
| **connection.usage duration** | Thời gian mượn rồi trả |
| **connection timeout count** | Số lần không lấy được connection trong ngưỡng |

Tên metrics cụ thể phụ thuộc Micrometer, HikariCP, exporter và cấu hình. Không gán một tên metric duy nhất cho mọi version. Một connection được pool cấp nhanh cũng không đảm bảo câu SQL nhanh; hãy đo cả hai.

**Pool exhaustion không luôn được giải quyết bằng tăng maximumPoolSize.** Có thể có transaction mở quá lâu, truy vấn giữ lock, rò connection hoặc số worker quá mức. Tăng pool có thể đẩy quá tải sang PostgreSQL khi số session tăng.

## 10. JDBC span không đồng nghĩa thời gian trên CPU của PostgreSQL

Khi nhìn thấy span:

~~~text
DB UPDATE inventory     duration = 1200 ms
~~~

1200 ms có thể bao gồm:

- Thời gian driver gửi request qua mạng.
- Chờ PostgreSQL nhận và xử lý.
- Chờ row/table lock.
- Quét index hoặc heap, đọc đĩa, tính toán, sort/hash.
- Thời gian truyền kết quả, driver xử lý response.
- Các lần fetch bổ sung khi driver/ResultSet sử dụng cursor, tùy cách đo.

Vì vậy **DB client span duration khác với server-side execution time** lấy từ database. Tương tự, statement có thể nhanh nhưng ORM ánh xạ rất nhiều entity sau đó mới tốn thời gian.

Khi cần root cause, hãy ghép trace với:

1. **PostgreSQL wait events / blockers** trong lúc lỗi xảy ra.
2. **pg_stat_statements** để thấy truy vấn mẫu nào có tổng thời gian lớn trên khoảng quan sát.
3. **EXPLAIN (ANALYZE, BUFFERS)** có kiểm soát để hiểu query plan.
4. **HikariCP và JVM metrics**, nhất là chờ pool và GC pauses.
5. **Timestamp, service version, deployment, DB instance** để loại trừ thay đổi cấu hình.

Đừng kết luận một query thiếu index chỉ vì span JDBC dài.

## 11. Semantics của span cơ sở dữ liệu

OpenTelemetry có **semantic conventions** cho database client spans. Một số khái niệm thường gặp gồm:

| Nhóm thông tin | Ý nghĩa | Ví dụ dữ liệu ít nhạy cảm |
| --- | --- | --- |
| **db.system.name** | Loại database theo semantic convention mới phù hợp | postgresql |
| **db.namespace** | Database hoặc namespace hợp lệ trong ngữ cảnh | application_db |
| **db.operation.name** | Thao tác SQL mức cao | SELECT, INSERT, UPDATE |
| **db.collection.name** | Tên bảng/collection nếu instrument được an toàn | orders |
| **db.query.summary** | Tóm tắt truy vấn được chuẩn hóa | INSERT orders |
| **server.address/server.port** | Đích kết nối ở lớp network | db-writer.internal, 5432 |
| **error.type** | Phân loại lỗi không chứa thông tin nhạy cảm | tên exception/nhóm lỗi |

Ở các phiên bản cũ có thể gặp **db.system**, **db.name**, **db.statement**, **db.operation** hoặc thuộc tính có tên khác. Không sao chép danh sách vào dashboard mà không kiểm tra dữ liệu agent đang xuất; conventions tiến hóa theo thời gian và một số instrumentation có thể chạy trong chế độ opt-in/transition.

**Tên span nên ổn định và cardinality thấp**, ví dụ:

~~~text
Đúng hướng:  "SELECT orders"
             "UPDATE inventory"
             "checkout.place_order"

Không nên:   "SELECT orders WHERE id = 831726"
             "checkout for user alice@example.com"
             "UPDATE /tenant/10012/order/987654"
~~~

Các giá trị ID động có thể làm nổ số lượng tên span và tạo rủi ro thông tin. Nếu cần correlation theo resource để điều tra, dùng log được bảo vệ và định danh có kiểm soát, không biến mọi resource ID thành tên operation.

## 12. SQL statement và bind parameters: bảo vệ dữ liệu khi tracing

Một rủi ro rõ ràng là ghi nguyên câu SQL có literal:

~~~sql
SELECT id FROM customers
WHERE email = 'someone@example.com'
  AND phone = '...';
~~~

Điều này có thể đưa dữ liệu cá nhân vào trace backend, nơi nhiều nhóm được phép xem hơn database. SQL được tham số hóa:

~~~sql
SELECT id
FROM customers
WHERE tenant_id = ?
  AND email = ?;
~~~

dễ quan sát hơn vì tách cấu trúc và giá trị. Nhưng **không mặc định mọi agent chỉ phát SQL template**: một số cấu hình/instrumentation có thể thu thập statements, parameters, exception messages hoặc trường tùy biến chứa literal.

Chính sách nên áp dụng:

- Ưu tiên **query summary/operation name** và normalized SQL khi cần.
- Mặc định **không thu thập bind values, request/response bodies, credential, token, email, số tài khoản**.
- Nếu SQL text được thu thập, có **scrubbing/redaction** theo chính sách và test trên dữ liệu giả lập.
- Xác định rõ nơi dữ liệu telemetry được export, quyền xem, mã hóa, retention và khả năng xóa theo yêu cầu.
- Cẩn thận với **SQL comments**, query hints hoặc dynamic identifiers có thể mang ID/metadata.
- Không cho PII vào exception message hoặc custom attributes chỉ để debug nhanh.

**Tham số hóa truy vấn là biện pháp chống SQL injection**, còn **redaction trong observability** là biện pháp bảo vệ dữ liệu. Cần cả hai; một PreparedStatement đúng vẫn có thể bị lộ tham số nếu instrumentation được cấu hình sai.

## 13. Trace để phát hiện N+1 queries

Giả sử endpoint GET /orders cần liệt kê 50 đơn cùng tên khách hàng. Nếu ORM nạp danh sách đơn rồi truy cập lazy association từng hàng:

~~~text
GET /orders                                950 ms
  |
  +-- SELECT orders                        45 ms
  +-- SELECT customers WHERE id=?          13 ms
  +-- SELECT customers WHERE id=?          17 ms
  +-- SELECT customers WHERE id=?          16 ms
  +-- ... gần 50 câu SELECT tương tự ...
~~~

Mỗi truy vấn riêng lẻ có thể không chậm, nhưng **số round-trip lớn** làm request chậm. Trace giúp nhìn pattern, còn metrics SQL hoặc ORM statistics giúp đếm chính xác.

Hướng xử lý có thể là:

- Dùng **JOIN FETCH**, entity graph hoặc projection đúng dữ liệu cần.
- Dùng batch fetching hợp lý theo provider.
- Thiết kế truy vấn phục vụ màn hình thay vì ánh xạ quá nhiều entity/lazy associations.
- Kiểm tra trade-off: join nhiều quan hệ một-nhiều có thể tạo duplicate rows và kéo dữ liệu lớn.
- Đo lại latency, memory, số câu SQL và correctness sau tối ưu.

Không chỉ tìm “span lớn nhất”. Với N+1, **nhiều spans nhỏ có tổng chi phí đáng kể**. Đồng thời, một SELECT lặp lại không luôn là N+1 lỗi; có thể do logic nghiệp vụ yêu cầu. Cần xem cấu trúc code và mục đích dữ liệu.

## 14. Tracing transaction, commit và rollback

Một use case cập nhật nhiều bảng:

~~~text
BEGIN
  UPDATE inventory
  INSERT orders
  INSERT outbox_events
COMMIT
~~~

Thời gian của ba câu SQL chưa chắc bằng thời gian transaction:

- Có khoảng **đọc dữ liệu và kiểm tra nghiệp vụ** giữa các câu SQL.
- Database có thể **chờ khóa** khi UPDATE.
- ORM có thể trì hoãn SQL cho đến khi flush.
- **COMMIT** có chi phí WAL flush hoặc synchronous replication acknowledgement.
- Nếu lỗi, transaction có thể **ROLLBACK** với chi phí và trạng thái riêng.

Một trace có ích có thể biểu diễn:

~~~text
orders.place                           740 ms
  |
  +-- db.transaction                    720 ms
       +-- UPDATE inventory             480 ms
       +-- INSERT orders                 25 ms
       +-- INSERT outbox                 18 ms
       +-- commit                        90 ms
       +-- other in transaction         ...
~~~

Đây là **mô hình lý tưởng khi instrumentation đo đủ**, không phải cấu trúc tự sinh bắt buộc. Không tự tạo child span commit bằng cách đo code trước lệnh COMMIT rồi đặt tên sai.

**Flush không phải COMMIT.** Một ứng dụng JPA có thể gọi flush thành công nhưng commit sau đó thất bại; nếu telemetry đánh dấu nghiệp vụ thành công trước ranh giới commit, dashboard có thể sai. Đặt span/trạng thái kết quả ở tầng bao ngoài transaction.

## 15. Quan sát khóa, deadlock và isolation

Giả sử JDBC span UPDATE inventory kéo dài hơn một giây. Nếu PostgreSQL báo session đang đợi **Lock**, có thể là:

- Hai request cùng tranh cập nhật một sản phẩm.
- Một transaction giữ hàng quá lâu vì gọi dịch vụ ngoài khi chưa commit.
- Một migration/DDL giữ khóa schema.
- Transaction khác chưa commit, do lỗi hoặc đường xử lý lâu.

**Wait event** cung cấp bằng chứng khác với trace:

~~~sql
SELECT pid,
       application_name,
       state,
       wait_event_type,
       wait_event,
       clock_timestamp() - query_start AS query_elapsed,
       clock_timestamp() - xact_start AS transaction_elapsed
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
~~~

Đây là snapshot **tại thời điểm truy vấn**; những request đã kết thúc sẽ không còn hiện diện. Cần quyền quan sát phù hợp; kết quả về session khác có thể bị hạn chế bởi quyền.

Để tìm session hiện đang bị khóa chặn:

~~~sql
SELECT a.pid AS waiting_pid,
       pg_blocking_pids(a.pid) AS blocking_pids,
       a.wait_event_type,
       a.wait_event,
       clock_timestamp() - a.query_start AS waiting_duration
FROM pg_stat_activity AS a
WHERE a.wait_event_type = 'Lock'
  AND a.datname = current_database();
~~~

Lưu ý:

- **pg_blocking_pids** giúp tìm blocker ở thời điểm quan sát, không tái dựng toàn bộ lịch transaction trong quá khứ.
- **state = 'idle in transaction'** gợi ý transaction còn mở trong lúc không thực thi câu SQL; cần điều tra ranh giới ứng dụng.
- Không lập tức **pg_terminate_backend** từ một dashboard chỉ vì thấy session chờ; cần quyền/phê duyệt và phân tích tác động transaction.
- Nếu Java nhận **40P01 (deadlock detected)** hoặc **40001 (serialization failure)**, phân loại và retry **toàn transaction** khi phù hợp, không chỉ retry câu SQL bị lỗi trong transaction đã abort.
- Trace của request lỗi nên liên hệ được với metrics về conflict/retry, nhưng không mặc định trace là bản ghi đầy đủ của các row locks.

## 16. pg_stat_statements giúp nhìn truy vấn trên toàn hệ thống

Trong PostgreSQL có thể dùng extension **pg_stat_statements** nếu đã được cài đặt và cấu hình phù hợp. Ví dụ truy vấn thống kê:

~~~sql
SELECT queryid,
       calls,
       total_exec_time,
       mean_exec_time,
       rows
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Thống kê này giúp tìm những mẫu câu SQL tiêu tốn nhiều tổng thời gian hoặc có số lần gọi lớn trong một khoảng đo.

Giới hạn cần nhớ:

- Nó là **thống kê tích lũy/đã chuẩn hóa theo query**, không phải một distributed trace.
- **queryid** không phải ID toàn cục ổn định để nối thẳng với trace ID; có thể thay đổi do phiên bản/cấu hình/môi trường.
- **total_exec_time**, **mean_exec_time** là dữ liệu đo phía PostgreSQL, không đồng nhất với thời lượng JDBC client span.
- Thống kê chỉ có nếu extension/privileges và tracking đã được bật; không tự cài extension lên production trong lúc điều tra.
- Nội dung **query** nếu được truy xuất có thể chứa thông tin nhạy cảm trong một số tình huống; nên có chính sách xem/log.

Khi một trace cho thấy 60 SELECT nhỏ, **pg_stat_statements** giúp xác nhận số lần chạy và mức chi phí tổng thể của cùng mẫu query trên hệ thống, nhưng không gắn tự động từng lần chạy của một request vào những thống kê tích lũy đó.

## 17. EXPLAIN và giới hạn của việc tái hiện một trace

Khi nghi vấn query plan, hãy lấy **SQL template**, kiểu tham số, điều kiện dữ liệu, index và thống kê phù hợp. Ví dụ:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY id DESC
LIMIT 50;
~~~

**EXPLAIN ANALYZE thực sự thực thi câu SQL.** Với INSERT/UPDATE/DELETE, cần môi trường test hoặc transaction rollback được thiết kế cẩn thận; ngay cả SELECT đắt đỏ cũng có thể tạo tải production. Query example chứa giá trị giả định, không sao chép thông tin khách hàng thật vào tài liệu hay trace.

Một sự khác biệt quan trọng:

~~~text
JDBC span chậm lúc 10:02:
  PostgreSQL chờ row lock 1,5 giây.

Chạy EXPLAIN lúc 10:10:
  Không còn blocker.
  SELECT/UPDATE trên cùng dữ liệu có thể chạy nhanh.
~~~

**EXPLAIN lúc khác không tái tạo được chính xác lịch lock tại thời điểm sự cố.** Cần phối hợp lịch sử metrics, wait events, logs đã được thu thập và test concurrency có kiểm soát.

## 18. Liên kết trace với structured logs

Log dễ tìm hơn khi mỗi event chứa **trace_id** và **span_id** của span hiện hành:

~~~text
timestamp=... level=INFO service=order-service
operation=create_order trace_id=... span_id=...
message="Order creation started"
~~~

Khi đã bật OpenTelemetry/MDC instrumentation phù hợp, framework logging có thể tự đưa trace/span IDs vào context. Nếu cần đọc context trong code Java:

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;

SpanContext context = Span.current().getSpanContext();
if (context.isValid()) {
    log.info(
            "Order operation completed trace_id={} span_id={}",
            context.getTraceId(), context.getSpanId());
}
~~~

**log** là logger do ứng dụng cấu hình; ví dụ giả định code chạy trong phạm vi span hiện hành. Đừng tự sinh một chuỗi ngẫu nhiên đặt tên là **trace_id** nếu nó không khớp trace context. Nếu dùng MDC, cần kiểm tra nó được làm sạch/restored khi thread được tái sử dụng.

Một trace ID chỉ hữu ích nếu:

- Log của các thành phần liên quan có cùng trace context.
- Dịch vụ xử lý async không làm mất context.
- Query trên log backend có chính sách quyền và retention phù hợp.
- Không biến trace ID thành token cho phép người dùng xem log riêng tư của request khác.

## 19. Kết nối trace sang PostgreSQL: điều gì có thể và không thể?

PostgreSQL **không tự biết W3C traceparent của request Java** chỉ vì client có trace. Một session có PID, application_name, thông tin DB và SQL; trace ID thuộc hệ thống observability phía ứng dụng.

Có nhiều kỹ thuật điều tra:

1. Xác định **service.name**, DB endpoint và thời gian từ trace.
2. Kết hợp **pool metrics**, thời điểm JDBC call và wait-event snapshots.
3. Dùng **application_name** ổn định để phân biệt nguồn connection, ví dụ **order-service**, không biến nó thành mỗi trace ID riêng.
4. Khi có khả năng instrument và quyền phù hợp, thu thập **backend PID/connection identity có thời hạn** để hỗ trợ correlation trong một phiên kết nối.
5. Dùng logs/tracing ở tầng database/proxy hoặc giải pháp bổ sung khi cần tương quan chính xác hơn, có đánh giá quyền và overhead.

Đặc biệt:

- **PID có thể được tái sử dụng** sau khi session kết thúc. Không coi PID là định danh vĩnh viễn.
- Connection pool tái sử dụng cùng một DB session cho nhiều request, nên **application_name hoặc backend PID không tương đương một trace ID**.
- Việc sửa **application_name** trên mỗi request có thể tạo cardinality lớn, rò thông tin hoặc rò trạng thái khi trả connection về pool nếu reset không đúng.
- Việc chèn trace ID trực tiếp vào **SQL comments** có thể ảnh hưởng log, cache/normalization và rò metadata; không dùng mặc định nếu không có kế hoạch bảo mật/hiệu năng cụ thể.
- Nếu thực sự cần correlation đến từng câu SQL, cần thiết kế instrumentation tương thích cả **client, proxy, driver và DB telemetry**, không chỉ thêm một header HTTP.

## 20. Context propagation qua async, executor và message broker

Một application service có thể gọi **CompletableFuture**, **ExecutorService**, **@Async** hoặc publish event. Context thường gắn với luồng thực thi hiện hành, nên **đổi thread mà không propagate** có thể làm mất quan hệ cha–con.

Ví dụ bao một Runnable bằng context hiện hành:

~~~java
import io.opentelemetry.context.Context;
import java.util.concurrent.Executor;

public void schedule(Executor executor, Runnable work) {
    Runnable propagated = Context.current().wrap(work);
    executor.execute(propagated);
}
~~~

Trong thực tế:

- Agent hoặc instrumentation của framework có thể đã tự propagate; kiểm tra trước khi bọc thủ công để tránh thừa.
- **Context propagation không mang theo JDBC Connection hoặc transaction của thread gốc**. Transaction gắn với thread/framework context vẫn có vòng đời riêng.
- Với **message broker**, inject/extract context vào metadata/header được hỗ trợ, đồng thời giữ message ID, attempt và correlation phù hợp.
- Một job xử lý message sau nhiều giờ có thể cần **span link** đến producer thay vì giữ một parent span logic quá lâu.
- Khi retry, cần phân biệt **attempt spans** và **một tác vụ nghiệp vụ**, tránh đếm mỗi attempt là một order thực sự được tạo.
- Không đưa bearer token, SQL text hoặc payload nhạy cảm vào baggage để “cho dễ tìm”.

Một sai lầm nghiêm trọng là tưởng có thể truyền transaction JDBC sang worker thread chỉ vì trace cùng ID. **Trace context mô tả quan sát**, không tạo atomicity, isolation hay cùng session DB.

## 21. Span links và các công việc nhiều nguồn

Ví dụ một consumer gom 100 sự kiện vào một batch INSERT. Batch có thể có **nhiều producer**:

~~~text
Producer trace A ---- message A ---+
Producer trace B ---- message B ---+--> Consumer batch trace C
Producer trace D ---- message D ---+
~~~

Khi đó, quan hệ **link** tới những source contexts có thể phản ánh nhân quả tốt hơn một parent duy nhất. Tuy nhiên, không cần link mọi hàng trong một batch hàng triệu item: chi phí telemetry và kích thước span có thể quá lớn.

Chiến lược:

- Giữ **job_id/batch_id** theo cơ chế correlation bảo vệ phù hợp, không đặt mỗi ID làm span name.
- Sử dụng **bounded number of span links** hoặc sampling theo use case.
- Tách metrics **rows processed, duplicates, conflicts, retry attempts** khỏi số span.
- Khi consumer dùng outbox/inbox, log hoặc metrics **event version và trạng thái commit** để xác minh idempotency, không dựa riêng vào trace.

## 22. Phân biệt lỗi database và lỗi nghiệp vụ trên trace

Một exception không luôn có cùng mức độ nghiêm trọng.

| Tình huống | Tín hiệu kỹ thuật | Ý nghĩa thường gặp |
| --- | --- | --- |
| **23505 unique_violation** | SQLException/exception đã dịch | Có thể là conflict đúng nghiệp vụ hoặc lỗi logic |
| **40001 serialization_failure** | Transaction bị hủy | Có thể retry toàn transaction khi an toàn |
| **40P01 deadlock_detected** | Một transaction bị DB hủy | Có thể retry giới hạn sau khi phân tích tranh chấp |
| **08xxx connection exception** | Lỗi kết nối | Tùy thời điểm có thể không rõ COMMIT đã thành công chưa |
| **57014 query_canceled** | Hủy query/timeout | Cần xem driver, statement timeout và deadline |
| **Timeout chờ Hikari pool** | Không mượn được connection đúng hạn | Không nhất thiết DB query chậm |
| **Optimistic lock conflict** | UPDATE version không khớp hoặc @Version lỗi | Có thể là xung đột dự kiến giữa hai người sửa |

**Đừng đánh dấu toàn bộ conflict nghiệp vụ là lỗi hệ thống** nếu API cố ý trả 409 và đó là hành vi hợp lệ. Mặt khác, một unique violation lặp lại với tốc độ cao có thể là dấu hiệu bug hoặc retry storm; metrics cần phân loại để điều tra.

Khi ghi nhận lỗi:

- Ghi **error.type** hoặc SQLSTATE theo chính sách, không chép nguyên SQL/payload.
- Dùng span event cho retry attempt, deadline hoặc fallback quan trọng.
- Đặt span status ERROR nếu thao tác thực sự thất bại theo semantics đã định.
- Không che lỗi transaction vì instrumentation; telemetry phải là **quan sát**, không thay đổi đường lỗi.
- Một request có thể trả HTTP 200 nhưng transaction async sau đó thất bại; phải có span/metrics cho phần công việc phía sau.

## 23. Trace được lấy mẫu: không dùng nó làm mẫu số toàn hệ thống

Không phải request nào cũng được lưu trace. Một hệ thống tải lớn thường dùng sampling để hạn chế chi phí:

~~~text
100.000 requests/minute
    |
    +-- Metrics ghi nhận tổng thể
    |
    +-- Một phần được lấy mẫu thành traces
           |
           +-- request bình thường
           +-- request chậm
           +-- request lỗi
~~~

Các hình thức phổ biến:

- **Head sampling:** quyết định từ đầu request; chi phí thấp, nhưng có thể bỏ lỡ sự cố hiếm vì lúc bắt đầu chưa biết nó sẽ lỗi.
- **Parent-based sampling:** tôn trọng quyết định từ upstream theo chính sách; cần xử lý header ngoài biên tin cậy phù hợp.
- **Tail sampling:** giữ trace sau khi biết duration/status hoặc thuộc tính; có thể bắt những request chậm/lỗi tốt hơn nhưng tốn buffer, memory và cấu hình collector.
- **Rule-based sampling:** ưu tiên một số service/endpoint/error theo mức quan trọng, cần giới hạn chi phí.

Hệ thống production thường cần **metrics có độ bao phủ rộng** cho tỷ lệ lỗi và latency, còn traces dùng điều tra một tập request. Nếu chỉ có 1% trace được lưu, không được đếm số ERROR spans rồi xem đó là **số lỗi thực tế** mà không hiệu chỉnh và hiểu sampling.

**Sampling không phải quyền truy cập.** Một trace được giữ lại vẫn cần redaction, encryption, access control và retention.

## 24. Liên kết metrics và traces qua exemplars

Một histogram latency có thể cho biết p99 truy vấn vượt một giây, nhưng nhóm cần xem **một request cụ thể** thuộc vùng đuôi đó. Một số hệ quan sát hỗ trợ **exemplars**: điểm đo metric kèm tham chiếu trace/span theo thiết kế.

~~~text
HTTP request duration histogram
  p99 = 1,8 s
      |
      +-- exemplar -> trace_id -> trace timeline
                           |
                           +-- JDBC UPDATE inventory 1,2 s
                           +-- PostgreSQL Lock wait
~~~

Điểm lưu ý:

- Không mặc định mọi exporter/backend đều hỗ trợ exemplars hoặc lưu cùng retention.
- Exemplar chỉ đưa tới **một ví dụ**, không chứng minh tất cả request chậm có nguyên nhân giống hệt.
- Bảo vệ quyền truy cập giữa metric dashboard và trace details, nhất là khi trace chứa metadata nhạy cảm.
- Metric labels cần low-cardinality; không đưa **trace_id, customer_id, order_id** vào labels của mọi timeseries.

Một **trace ID trong metric label** cho mỗi request có thể làm nổ cardinality và chi phí lưu trữ. Exemplar là cơ chế có giới hạn dành riêng cho correlation, không phải lý do đưa tất cả ID vào metrics.

## 25. Cardinality, overhead và giới hạn telemetry

Tracing bổ sung công việc:

- Tạo span/context và metadata trong JVM.
- Có thể đo từng lời gọi JDBC hoặc HTTP.
- Buffer/export qua OTLP/collector.
- Lưu và index traces ở backend.

Với một request có hàng nghìn câu SQL, thu thập mọi child span có thể rất tốn kém. Cần:

1. Đặt **span names ổn định**, không chứa user/order ID.
2. Giới hạn số attributes, events và links; không lưu các kết quả SQL cỡ lớn.
3. Đo **CPU/heap/GC/latency overhead** khi bật agent trên workload đại diện.
4. Giới hạn queue/exporter buffer, có cơ chế drop telemetry có kiểm soát thay vì treo nghiệp vụ.
5. Điều chỉnh sampling theo mục tiêu điều tra; cân nhắc metrics riêng cho tổng số SQL calls.
6. Không instrument quá sâu các helper Java nhỏ khiến trace thành nhiễu.
7. Theo dõi **dropped spans, exporter failures, collector memory và tail-sampling state**.

**Telemetry không được trở thành single point of failure của giao dịch.** Nếu collector mất kết nối, ứng dụng vẫn phải có chính sách vận hành rõ ràng về buffering/drop và resource protection, không giữ request chờ vô hạn để xuất trace.

## 26. Quan sát hệ đa tenant mà không rò dữ liệu

Trong một hệ thống nhiều tenant, việc muốn lọc trace theo tenant là nhu cầu thật. Nhưng nếu có hàng triệu tenant:

- Gắn toàn bộ tenant IDs làm **metric labels** có thể gây cardinality cao.
- Gắn email, tên người hoặc resource IDs vào **span names** vừa gây lộ dữ liệu vừa tăng chi phí.
- Ghi SQL bind parameters làm người xem trace có thể biết dữ liệu tenant khác.
- Gửi trace qua môi trường khác hoặc nhà cung cấp khác có thể vi phạm yêu cầu phân vùng dữ liệu.

Các chiến lược an toàn hơn:

1. Dùng low-cardinality attributes như **operation, outcome, dependency, environment**.
2. Chỉ dùng tenant cohort/tier hoặc mapping đã được bảo vệ nếu cần phân nhóm và được phép.
3. Dùng **incident/correlation ID** có phân quyền khi cần truy tìm một request cụ thể.
4. Tách retention và role-based access ở telemetry backend.
5. Redact exception messages và custom events có khả năng chứa payload.
6. Kiểm thử data governance bằng các input giả lập chứa thông tin nhạy cảm.

Không biến trace backend thành một đường truy cập dữ liệu bỏ qua authorization của ứng dụng.

## 27. Tracing retries, idempotency và commit không rõ kết quả

Một API tạo đơn có thể retry khi gặp deadlock hoặc lỗi kết nối:

~~~text
orders.create (logical request)
  |
  +-- attempt 1
  |     +-- INSERT orders
  |     +-- COMMIT -> timeout/connection loss
  |
  +-- reconcile request_key
  |
  +-- attempt 2 (chỉ nếu chính sách cho phép)
        +-- kiểm tra trạng thái
        +-- trả kết quả đã lưu hoặc ghi an toàn
~~~

Trace nên phân biệt:

- **Logical request**: một ý định nghiệp vụ.
- **Attempt**: từng lần thử thực thi.
- **Database transaction**: phạm vi atomicity của một lần thử.
- **Idempotency key**: khóa nghiệp vụ ổn định qua retry, nhưng không cần ghi nguyên giá trị vào trace.
- **Final outcome**: thành công, xung đột, thất bại, hoặc **chưa biết** vì mất phản hồi commit.

Không đánh dấu một SQLException ngay sau COMMIT là **chắc chắn rollback**. Nếu server đã commit nhưng phản hồi mất, hai attempt có thể không tương đương hai giao dịch được tạo mới. Cần đối soát bằng request ID và ràng buộc duy nhất.

**Trace có thể giúp thấy nhiều attempts**, nhưng không phải nguồn chứng minh mỗi lần ghi đã bền vững. Kiểm chứng trạng thái trên DB source of truth, outbox và idempotency records.

## 28. Chẩn đoán chậm do replica và cache

Không phải GET nào cũng đến PostgreSQL primary:

~~~text
GET /profile
   |
   +-- Redis cache hit -> 5 ms
   |
   +-- Cache miss
         |
         +-- PostgreSQL read replica -> 60 ms
         +-- cache fill -> 8 ms
~~~

Trace nên biểu diễn ranh giới cache/database theo cấu hình phù hợp và metadata không nhạy cảm:

- **Cache hit/miss** là tín hiệu hữu ích nếu có instrumentation, nhưng không lưu nguyên cache key có chứa PII.
- **Đọc replica** có thể nhanh mà vẫn trả dữ liệu cũ do replication lag.
- **Read-your-writes** yêu cầu kiểm tra version/LSN fence hoặc fallback primary; một span GET nhanh không chứng minh kết quả mới.
- **Fallback** từ replica sang primary nên có event/metric để điều tra chi phí và tỷ lệ.
- Nếu query đi qua proxy, phải biết endpoint trong trace đang là **proxy** hay đúng DB node để không suy diễn sai.

Quan sát **latency** và **freshness/correctness** là hai trục khác nhau. Một dashboard chỉ tối ưu response time có thể bỏ qua rủi ro trả dữ liệu stale.

## 29. Từ dấu hiệu đến nguyên nhân: playbook phân tích một request chậm

Giả sử một yêu cầu POST /orders mất 2,8 giây. Quy trình:

**Bước 1 – Chọn request đủ bằng chứng.** Lấy trace ID từ log/correlation hoặc exemplar; xác nhận endpoint, thời điểm, service version, khu vực, outcome và mức sampling.

**Bước 2 – Đọc timeline.** Xác định span HTTP parent, service span, các JDBC spans, outbound calls và phần thời gian không có span. Không cộng mù quáng các child durations.

**Bước 3 – So với pool metrics.** Nếu request có khoảng trống dài trước JDBC, kiểm tra **connection acquire p99, pending, active, usage duration**. Không kết luận thiếu index khi connection còn chưa được cấp.

**Bước 4 – Kiểm tra DB wait events và contention.** Với khoảng JDBC UPDATE chậm, điều tra **pg_stat_activity, blockers, lock waits, transaction duration** cùng thời điểm. Một snapshot sau sự cố có thể không còn blocker.

**Bước 5 – Kiểm tra query workload.** Nếu có nhiều SELECT, tìm N+1; nếu một query lớn, xem pg_stat_statements, EXPLAIN có kiểm soát, index và dữ liệu.

**Bước 6 – Kiểm tra transaction và commit.** Nếu COMMIT chiếm nhiều thời gian, xem WAL/storage flush, synchronous replication, long transactions và network. Không suy rằng DB query thời gian thấp nghĩa commit không thể chậm.

**Bước 7 – Kiểm tra error/retry.** Nhiều attempts có thể kéo dài request; xác định SQLSTATE, idempotency và chỉ retry transaction đúng điều kiện.

**Bước 8 – Kiểm chứng lại.** Sau thay đổi, so sánh metrics p95/p99, pool pending, DB workload, error rate, correctness và trace của nhiều request đại diện.

### 29.1. Ví dụ phân tích có số liệu

~~~text
HTTP request                                    2800 ms
  checkout.create                              2670 ms
    pool acquire                               1300 ms
    INSERT orders                               45 ms
    UPDATE inventory                           850 ms
    INSERT outbox                               30 ms
    commit                                      90 ms
    other intervals                            ...

Quan sát song song:
  Hikari pending connections tăng mạnh.
  PostgreSQL: UPDATE inventory chờ Lock.
  HTTP 5xx tăng khi request vượt deadline.
~~~

Khả năng tồn tại **hai vấn đề cùng lúc**: pool thiếu connection vì transaction giữ lâu, và hàng inventory đang tranh chấp. Tăng pool size đơn thuần có thể làm contention tệ hơn. Cần xác định transaction nào giữ lock, thời gian giữ transaction, tần suất cùng product và logic update có thể thu hẹp hay không.

## 30. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Có trace ID là PostgreSQL tự biết request nào.” | DB không tự nhận W3C trace context từ Java; cần correlation/instrumentation riêng |
| “JDBC span 1 giây nghĩa DB chạy CPU 1 giây.” | Có thể gồm network, chờ lock, driver và fetch |
| “Không có JDBC span nghĩa không có truy vấn.” | Instrumentation/sampling/context có thể thiếu hoặc không hỗ trợ |
| “Mọi child durations cộng lại bằng parent.” | Có lồng nhau, song song và khoảng trống chưa được instrument |
| “Service method trả về là transaction đã commit.” | Với @Transactional proxy, commit có thể xảy ra sau method body |
| “Flush thành công nghĩa ghi đã bền vững.” | Flush chưa phải commit và transaction có thể rollback |
| “SQL đã dùng PreparedStatement nên trace không lộ dữ liệu.” | Agent có thể thu thập parameters/exception messages nếu cấu hình sai |
| “Log query text đầy đủ là cách debug tốt nhất.” | Dễ lộ PII, token, SQL literal; ưu tiên query summary và redaction |
| “Hikari pool pending cao thì cứ tăng pool.” | Cần xem transaction dài, rò connection, DB capacity |
| “Một request đọc nhanh thì dữ liệu chắc chắn mới.” | Replica/cache có thể stale, cần consistency contract |
| “Trace ID nên làm label trên mọi metric.” | Cardinality tăng cực lớn; dùng exemplars/correlation phù hợp |
| “Trace 1% đủ để tính error rate chính xác.” | Metrics bao phủ rộng hơn cần được dùng làm mẫu số |
| “Đổi thread giữ được cùng transaction nhờ context.” | Context tracing không mang connection/transaction JDBC |
| “Một queryid ở pg_stat_statements là trace ID.” | Đây là identifier thống kê câu SQL, không phải request trace |
| “Có lỗi JDBC nghĩa transaction chắc chắn không commit.” | Mất kết nối lúc commit có thể gây kết quả bất định |
| “Bật tất cả spans và attributes càng nhiều càng tốt.” | Overhead, cardinality và rủi ro bảo mật có thể lớn |

## 31. Kiểm thử instrumentation thay vì chỉ nhìn dashboard

Một giải pháp tracing cần kiểm tra **ngữ nghĩa** trong test. Gợi ý các kịch bản:

1. Một HTTP request tạo **server span**, service span và JDBC span đúng quan hệ khi auto instrumentation bật.
2. **Manual business span** bao trùm transaction như thiết kế; nếu commit thất bại, lỗi được ghi ở span phù hợp.
3. Hai request độc lập có trace ID khác nhau; không rò context qua worker thread/pool.
4. Outbound HTTP/message truyền trace context theo policy, không làm mất parent/link.
5. Khi một query nhận SQLSTATE **23505/40001**, exception được phân loại đúng và transaction xử lý theo quy tắc.
6. Khi **connection acquisition timeout**, telemetry không gắn nhầm nguyên nhân thành server-side SQL execution.
7. Khi ORM tạo N+1 queries, có khả năng nhìn thấy pattern hoặc metrics đếm SQL calls.
8. Khi sampling giảm, **metrics vẫn ghi nhận tổng requests/error rate**; tracing backend thiếu request không làm mất sự kiện nghiệp vụ.
9. Input chứa email, token giả và SQL bind values không xuất hiện ở **span names/attributes/logs** ngoài phạm vi cho phép.
10. Collector tạm mất kết nối không làm API treo vô hạn hoặc OOM vì telemetry buffer.

Với unit/integration tests của OpenTelemetry Java, có thể dùng **in-memory exporter/test SDK** phù hợp phiên bản để kiểm tra span names, parent relationships, events và attributes. Nhưng test với exporter giả **không thay thế** integration test trên PostgreSQL để xem SQL/transaction thật.

Nếu kiểm thử auto instrumentation bằng Java agent, cần khởi chạy JVM test với agent hoặc môi trường test chứa đúng instrumentation; chỉ thêm OpenTelemetry API dependency không tự tạo JDBC spans. Hãy xác nhận thực tế trên hệ thống đang dùng, tránh viết assertion phụ thuộc một span name/attribute cụ thể của version khác.

## 32. Bài tập thực hành

### Bài 1. Đọc timeline

Request mất 1,6 giây. JDBC query span chỉ 80 ms, còn Hikari acquire duration khoảng 1,1 giây. Nên điều tra phần nào trước?

**Gợi ý:** Điều tra connection pool: active/pending, connection usage, transaction kéo dài hoặc rò connection. Không kết luận query thiếu index chỉ từ tổng request.

### Bài 2. Commit nằm ngoài service method

Một method gắn **@Transactional** tạo span trong method, gọi repository rồi kết thúc span. Sau đó Spring proxy COMMIT lỗi. Vì sao span có thể được xem là thành công dù request thất bại?

**Gợi ý:** Span thủ công kết thúc trước khi transaction interceptor commit. Tạo span bao ngoài transaction hoặc instrument đúng ranh giới commit; xử lý exception ở tầng bao ngoài.

### Bài 3. JDBC span chậm

Một span UPDATE kéo dài 2 giây. Có thể khẳng định index sai không?

**Gợi ý:** Không. Cần kiểm tra lock waits, network, DB server execution và driver. Dùng pg_stat_activity/pg_stat_statements/EXPLAIN có kiểm soát.

### Bài 4. N+1

Một GET hiển thị 100 đơn hàng, trace có 1 SELECT orders và 100 SELECT customers. Đây gợi ý vấn đề gì?

**Gợi ý:** Có thể là N+1 queries. Xem ORM lazy loading, projection, JOIN FETCH/batch fetching và đo lại số SQL calls.

### Bài 5. SQL parameters

Một nhóm bật ghi mọi bind parameter vào traces để debug. Tại sao rủi ro ngay cả khi ứng dụng dùng PreparedStatement?

**Gợi ý:** Tham số có thể chứa PII, token, dữ liệu thanh toán; tracing backend có quyền/retention riêng. PreparedStatement chống injection, không mặc định che dữ liệu khỏi telemetry.

### Bài 6. Trace context qua executor

Service tạo CompletableFuture trên thread pool và JDBC span phía sau xuất hiện như trace mới. Chỗ nào cần xem?

**Gợi ý:** Context propagation khi chuyển thread; kiểm tra auto instrumentation hoặc wrap Runnable/Callable/CompletionStage context. Không nhầm context tracing với transaction propagation.

### Bài 7. Trace và pg_stat_statements

Dashboard PostgreSQL có một queryid với mean_exec_time 200 ms. Có thể dùng queryid như trace ID để mở trực tiếp request đã gọi query đó không?

**Gợi ý:** Không. Queryid thống kê mẫu câu SQL, không phải identifier của một request. Cần timestamp, service, normalized query, instrumentation/correlation phù hợp.

### Bài 8. Trace ID trong metrics

Nhóm muốn thêm **trace_id** thành label cho histogram HTTP latency. Vì sao đây là ý tưởng tồi?

**Gợi ý:** Tạo một time series gần như cho mỗi request, cardinality cực lớn. Dùng metrics low-cardinality và exemplar hỗ trợ liên kết trace.

### Bài 9. Khác nhau giữa trace và tính đúng dữ liệu

GET profile qua replica trả nhanh trong 10 ms nhưng hiển thị giá trị cũ ngay sau PUT. Trace có giải quyết vấn đề không?

**Gợi ý:** Trace giúp xác định GET đi replica/cache và thời gian. Yêu cầu RYW cần read-primary, version/LSN fence hoặc fallback đúng hợp đồng; latency nhanh không chứng minh freshness.

### Bài 10. Retry sau COMMIT lỗi

Một JDBC span COMMIT kết thúc bằng connection exception. Có thể suy transaction rollback rồi tự gửi một lệnh tạo đơn với request ID mới không?

**Gợi ý:** Không. Commit có thể đã hoàn tất nhưng response bị mất; dùng idempotency key ổn định và đối soát trên nguồn đáng tin cậy.

### Bài 11. Sampling

Mỗi phút có 10.000 request nhưng chỉ 100 traces được lưu. Có thể đếm 2 error traces rồi báo error rate = 0,02% không?

**Gợi ý:** Không. Sampling có thể thiên lệch theo rule; dùng metrics tổng request/errors hoặc cách ước lượng đã được kiểm chứng.

### Bài 12. Chờ Lock

PostgreSQL cho biết một UPDATE đang chờ Lock, trace cùng thời điểm cũng có một JDBC span dài. Điều gì cần xác minh tiếp?

**Gợi ý:** Xác định blocker, transaction duration và thời gian giữ khóa; đối chiếu service/retry và dữ liệu. Snapshot tại một thời điểm không tự cung cấp toàn bộ lịch sử.

### Bài 13. Kiểm thử agent

Unit test thêm OpenTelemetry API nhưng không chạy Java agent, sau đó mong tự xuất hiện JDBC spans. Kỳ vọng này có hợp lý không?

**Gợi ý:** Không. API tự nó không instrument JDBC; cần agent, starter hoặc instrumentation thủ công có cấu hình phù hợp.

### Bài 14. Đo tác động tracing

Sau bật instrumentation toàn bộ SQL, JVM allocation tăng mạnh và collector thường drop spans. Nên thay đổi gì?

**Gợi ý:** Đo overhead, giảm span/attribute volume, điều chỉnh sampling, giới hạn exporter buffers và kiểm tra trùng instrumentation. Không để telemetry đe dọa giao dịch nghiệp vụ.

## 33. Checklist đưa tracing vào tầng persistence

1. **Mục tiêu:** trace giúp điều tra use case nào: chậm, timeout, tranh chấp, retry, failover hay dữ liệu stale?
2. **Service identity:** service.name/version/environment được cấu hình nhất quán và không mang ID động?
3. **Context:** HTTP/messaging/executor truyền trace context đúng mà không rò sang request khác?
4. **Span boundaries:** phân biệt business use case, transaction, pool acquisition, JDBC execution và commit?
5. **Auto/manual:** có kiểm tra agent/starter và tránh JDBC spans bị tạo trùng không?
6. **JPA/Spring:** span có bao gồm commit/rollback đúng ranh giới proxy/transaction manager không?
7. **Query:** tên và attributes SQL dùng summary/operation an toàn, không có bind values/PII?
8. **Pool:** đo active/idle/pending/acquisition/usage và connection timeouts?
9. **Database:** có pg_stat_activity, wait events, pg_stat_statements/EXPLAIN theo quyền và quy trình an toàn?
10. **Concurrency:** phân loại SQLSTATE, optimistic conflicts, deadlocks và retry attempts?
11. **Consistency:** trace đọc primary/replica/cache có hỗ trợ điều tra freshness, version fence khi cần?
12. **Errors:** xử lý failed transaction, commit unknown và business conflict đúng semantics?
13. **Sampling:** có chiến lược thu slow/error traces, metrics toàn hệ thống và quan sát dropped telemetry?
14. **Cardinality:** không đặt IDs động vào span names/metric labels; links/events được giới hạn?
15. **Privacy:** không export secrets, tokens, email, SQL literals hoặc payload; backend có access control và retention?
16. **Reliability:** collector/exporter outage không làm application treo hoặc OOM?
17. **Tests:** instrumentation, parent-child, async propagation, error status và redaction đã được kiểm chứng?
18. **Runbook:** có quy trình từ trace ID đến pool, DB waits, query plan và kiểm tra cải thiện?

## 34. Tổng kết

**Liên kết trace ứng dụng với thao tác lưu trữ** là tạo một đường quan sát nhất quán từ **HTTP request, application service, transaction, connection pool, JDBC/ORM đến PostgreSQL**, không chỉ in trace ID vào log. Trace cho biết **thứ tự và thời lượng** các thao tác của request được lấy mẫu; pool metrics, SQL statistics và wait events bổ sung bằng chứng về nguyên nhân chậm. Một JDBC span dài không tự chứng minh lỗi index, cũng như một PostgreSQL query chạy nhanh không giải thích toàn bộ request chậm.

Trong Java, hãy kết hợp **OpenTelemetry automatic instrumentation** với **manual spans mang ý nghĩa nghiệp vụ**, truyền context đúng qua thread và message, đặt span đúng ranh giới **commit/rollback** của Spring và không instrument trùng. Luôn bảo vệ **SQL parameters, dữ liệu cá nhân, credentials**, dùng tên/attributes ổn định và kiểm soát sampling/overhead. Cuối cùng, kết nối tracing với **metrics, structured logs, PostgreSQL diagnostics, kiểm thử concurrency và runbook** để xử lý sự cố persistence dựa trên bằng chứng, thay vì tối ưu theo suy đoán.
