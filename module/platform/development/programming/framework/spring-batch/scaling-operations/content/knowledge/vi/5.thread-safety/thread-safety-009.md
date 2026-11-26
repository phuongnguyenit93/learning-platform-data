# Kiểm tra thread safety của thư viện ngoài trong Spring Batch

## Mục tiêu bài học

Khi tăng mức song song cho Spring Batch, nhiều nhóm phát triển kiểm tra kỹ **ItemReader**, **ItemProcessor** và **ItemWriter** nhưng bỏ qua các thư viện mà chúng gọi: JSON/XML parser, HTTP SDK, thư viện xử lý file, mapper, formatter, client cơ sở dữ liệu, mã hóa hay bộ nhớ đệm. Một component Spring nhìn qua có vẻ stateless vẫn có thể gọi vào **một object mutable dùng chung** bên trong dependency. Khi đó chạy đúng với một thread không đủ chứng minh rằng job chạy đúng với tám thread hoặc nhiều worker.

Bài thuộc chương **An toàn luồng** của module **SPRING_BATCH_SCALING_OPERATIONS**. Phạm vi là cách **kiểm tra thread safety của thư viện ngoài** trước khi mở rộng workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và mô hình phân tán. Nội dung đồng thời xem xét tính đúng dữ liệu, bottleneck, retry/restart, hiệu năng và trách nhiệm vận hành.

Học xong bài này, bạn có thể:

- Xác định thư viện và instance nào thực sự được nhiều thread hoặc StepExecution chia sẻ.
- Đọc và kiểm chứng hợp đồng thread safety ở đúng phiên bản thư viện, thay vì suy đoán từ tên class.
- Phân biệt instance an toàn luồng, method an toàn luồng, thread confinement và resource không được dùng đồng thời.
- Tổ chức kiểm thử concurrency, stress, fault injection và đối soát dữ liệu cho dependency có mutable state.
- Chọn cách khắc phục phù hợp: immutable/stateless, instance độc lập, scope theo partition, synchronization hoặc pooling có giới hạn.
- Giải thích vì sao **@StepScope** không mặc nhiên tạo instance cho từng chunk thread của một multi-threaded step.
- Đánh giá tác động của khóa đồng bộ tới throughput, connection pool và khả năng restart của Spring Batch.

## 1. Thread safety cần được xác nhận ở cấp nào?

**Thread-safe** nghĩa là object hoặc API giữ các bất biến đã cam kết khi các thread sử dụng đồng thời **theo đúng cách mà tài liệu cho phép**. Không có khẳng định thread-safe chung áp dụng cho tất cả class, tất cả method và mọi thứ được truyền vào method.

Xem chuỗi phụ thuộc:

~~~mermaid
flowchart LR
    A["Worker chunk thread"] --> B["ItemProcessor"]
    B --> C["Spring singleton service"]
    C --> D["Third-party SDK client"]
    D --> E["Mutable parser / cache / session"]
~~~

Ngay cả khi **ItemProcessor** không khai báo field mutable, service có thể giữ SDK client ở singleton, và client lại giữ một parser/cursor không an toàn. Khi nhiều thread đồng thời gọi processor, phần được chia sẻ không chỉ có processor mà gồm **toàn bộ object graph được truy cập**.

Nên đặt câu hỏi ở nhiều cấp:

| Cấp | Câu hỏi kiểm tra |
| --- | --- |
| **Class/instance** | Một instance có cho phép nhiều thread gọi cùng lúc không? |
| **Method** | Có method đọc-only an toàn nhưng method cấu hình làm thay đổi state không? |
| **Resource** | Connection, session, parser, stream hoặc buffer có thuộc về một thread không? |
| **Configuration** | Có cần cấu hình toàn bộ object trước khi chia sẻ không? |
| **Lifecycle** | close, reset, flush, refresh token hoặc reconnect có thể xảy ra trong lúc thread khác đang dùng không? |
| **Dependency lồng nhau** | Client an toàn nhưng callback, interceptor, mapper hoặc request builder truyền vào có an toàn không? |
| **Toàn quy trình** | Hai lời gọi riêng lẻ an toàn nhưng chuỗi read–modify–write có cần atomicity không? |

Một API an toàn khi gọi **get()** đồng thời chưa chắc bảo đảm chuỗi **get() → sửa → put()** là thao tác nguyên tử. Tương tự, việc client hỗ trợ concurrent request không cho phép nhiều thread cùng dùng **một request builder mutable**.

### Ba tính chất thường bị nhầm

- **Thread-safe:** concurrent use không làm mất bất biến theo hợp đồng API.
- **Reentrant:** một thao tác có thể được gọi lại khi lần gọi trước chưa kết thúc, theo ngữ nghĩa cụ thể của implementation; reentrancy không đồng nhất với thread safety.
- **Stateless/immutable:** state không thay đổi sau khởi tạo hoặc không mang state giữa lời gọi. Đây thường là nền tảng tốt cho thread safety, nhưng thread-safe end-to-end vẫn phụ thuộc resource/callback mà đối tượng sử dụng.

**Nguyên tắc:** kiểm tra ở **instance thực tế được chia sẻ**, không chỉ tại tên kiểu dữ liệu.

## 2. Các thư viện ngoài thường xuất hiện ở đâu trong batch pipeline?

Trong batch lớn, bên thứ ba thường tham gia nhiều công đoạn cùng lúc:

| Vị trí | Ví dụ dependency | State cần kiểm tra |
| --- | --- | --- |
| **Reader** | JDBC driver, ORM session, S3/HTTP SDK, parser CSV/XML | Cursor, ResultSet, file position, pagination state, token, buffer |
| **Processor** | JSON mapper, thư viện chuẩn hóa ngày giờ, máy mã hóa, rule engine | Mutable builder, formatter, cache, context xử lý, shared model |
| **Writer** | JDBC batch API, HTTP client, search/index SDK, object storage client | Connection/session, request builder, batch accumulator, flush |
| **Cross-cutting** | Retry library, circuit breaker, rate limiter, metrics, tracing | Bộ đếm, timer, rolling window, queue và callback |
| **Hạ tầng** | Connection pool, serializer, message converter, thread pool | Pool lifecycle, thread reuse, serialization contract |
| **Framework bridge** | Adapter SDK tự viết, listener, interceptor | Mutable field, giá trị phân vùng, trạng thái giao dịch |

Đừng chỉ xem package do ứng dụng tự viết. Ví dụ một processor gọi:

~~~java
return mappingService.convert(input);
~~~

Phần code này không tiết lộ **mappingService** dùng một singleton JSON mapper được cấu hình bất biến, một parser được tạo mới mỗi lần hay một mutable **StringBuilder** dùng chung. Cần lần theo dependency injection và vòng đời của toàn bộ các object được gọi.

## 3. Hiểu mô hình concurrency của Spring Batch trước khi kiểm tra

Một thư viện có thể an toàn trong mô hình này nhưng không phù hợp với mô hình khác.

| Mô hình | Đơn vị thực thi đồng thời | Điều gì có thể được chia sẻ? |
| --- | --- | --- |
| **Step tuần tự** | Một chuỗi chunk trong một StepExecution | Các singleton có thể được dùng tuần tự, nhưng vẫn có thread phụ của SDK |
| **Multi-threaded step** | Nhiều chunk threads thuộc **cùng một StepExecution** | Reader, processor, writer, singleton service và tài nguyên dùng chung |
| **Parallel steps** | Các StepExecution khác nhau chạy đồng thời | Singleton Spring bean và database/client chung giữa các step |
| **Local partitioning** | Nhiều worker StepExecution trên các thread cùng JVM | Bean singleton, cache, DataSource; các bean StepScope tách theo StepExecution |
| **Remote partitioning** | Worker StepExecution trên nhiều JVM | Không chia sẻ heap giữa JVM, nhưng chia sẻ DB, broker, API và metadata |
| **Remote chunking** | Manager gửi item/chunk cho worker JVM | Các instance trong một worker JVM vẫn có thể phục vụ nhiều message đồng thời |

Trong **multi-threaded step**, Spring Batch có thể dùng một StepExecution cho nhiều chunk threads. Điều này dẫn đến khác biệt rất quan trọng:

> **@StepScope tạo bean theo StepExecution, không tự tạo một instance cho từng thread hoặc từng chunk trong cùng StepExecution.**

Trong **partitioning**, mỗi partition thường có StepExecution riêng; vì vậy reader hoặc processor được tạo theo StepScope có thể độc lập giữa các partition. Nhưng nếu worker step lại dùng concurrency nội bộ, hoặc bean StepScope tham chiếu một **singleton SDK mutable**, state vẫn có thể bị chia sẻ.

Trong **remote partitioning**, mỗi JVM có heap riêng nên instance SDK ở các JVM khác nhau không chia sẻ object Java. Tuy nhiên hai thread trong **cùng worker JVM** vẫn có thể chia sẻ singleton; database, file đích hoặc dịch vụ ngoài cũng vẫn là tài nguyên dùng chung toàn hệ thống.

## 4. Thu thập bằng chứng thread safety từ thư viện

Đừng bắt đầu bằng stress test nếu thư viện đã tuyên bố rõ một class **không thread-safe**. Ngược lại, một test chạy qua nhiều lần không chứng minh API an toàn nếu tài liệu không cam kết.

### Thứ tự kiểm chứng được đề nghị

1. **Xác định phiên bản thực sự triển khai**: tọa độ thư viện, phiên bản driver/SDK, runtime Java và version của các module phụ thuộc.
2. **Tìm hợp đồng chính thức** của class/method đang dùng: JavaDoc, reference guide, release notes và các giới hạn về lifecycle.
3. **Kiểm tra cách khởi tạo**: client singleton có được cấu hình hoàn chỉnh trước khi chia sẻ không? Có callback, interceptor hoặc cache tùy biến không?
4. **Kiểm tra lớp resource**: client quản lý pool có thể dùng chung, nhưng connection/session/request builder được nó trả về có thể không cho phép dùng chung.
5. **Xem phiên bản và thay đổi hành vi**: nâng cấp thư viện có thể thay cách pooling, serializer, refresh token, retries hoặc concurrency.
6. **Thử nghiệm có chủ đích** trên kịch bản tương tự production, rồi bổ sung kiểm tra dữ liệu và failure mode.

Đối với một thư viện không có tài liệu rõ, ghi trạng thái **“chưa xác minh thread-safe”** thay vì suy đoán. Có thể hỏi maintainer, kiểm tra mã nguồn của đúng phiên bản khi quy trình dự án cho phép, hoặc cô lập instance để giảm rủi ro. Trong bài toán này, không cần đọc thêm tệp repository để làm mẫu phương pháp.

### Ma trận đánh giá ví dụ

| Loại API | Đánh giá ban đầu | Điều kiện cần xác nhận |
| --- | --- | --- |
| **java.time.format.DateTimeFormatter** | Immutable, phù hợp chia sẻ | Không gắn thêm state mutable từ code ứng dụng |
| **java.text.SimpleDateFormat** | Mutable, không nên dùng một instance đồng thời | Instance riêng, đồng bộ hóa, hoặc chuyển sang java.time |
| **Jackson ObjectMapper** | Thường dùng chung được **sau khi cấu hình hoàn tất** | Không đổi cấu hình sau khi bắt đầu concurrent use; custom module/deserializer có an toàn không? |
| **JDBC DataSource từ connection pool** | Thiết kế phục vụ lấy connection từ nhiều thread | Giới hạn pool, close/return connection, thread safety của pool cụ thể |
| **JDBC Connection/PreparedStatement/ResultSet** | Không giả định được chia sẻ đồng thời | Hợp đồng driver; scope theo giao dịch/reader |
| **HTTP SDK client** | Tùy SDK và version | Client pool, auth refresh, interceptors, request/response body, shutdown |
| **Parser/XML/CSV hoặc Workbook** | Phụ thuộc đối tượng và implementation | Parser instance, state vị trí, mutable document/model, callback |
| **Mã hóa/hash object có state** | Phụ thuộc API; nhiều engine giữ state | Có thể dùng instance riêng mỗi lời gọi/thread hay API concurrent chuyên biệt? |

Đây là **gợi ý cách điều tra**, không phải chứng nhận cho mọi phiên bản thư viện. Ví dụ Jackson ObjectMapper chỉ được chia sẻ an toàn theo các điều kiện cấu hình và tùy biến phù hợp; không suy diễn tính an toàn đó cho một custom serializer có mutable state.

## 5. Phân loại shared state để chọn cách kiểm tra

Cùng là “có field”, nhưng rủi ro khác nhau:

**Immutable state.** Dữ liệu xây xong không đổi, chẳng hạn cấu hình đọc-only được tạo từ giá trị immutable. Nếu toàn bộ dependency graph immutable hoặc được thiết kế concurrent, có thể chia sẻ.

**Thread-safe mutable state.** Thư viện dùng lock, atomic hoặc concurrent collection; có thể gọi đồng thời theo hợp đồng, nhưng cần hiểu mức atomicity. Một ConcurrentHashMap không tự biến logic gồm nhiều thao tác thành transaction.

**Thread-confined state.** Resource gắn với một thread, một request hoặc một StepExecution; không được chuyển instance tới thread khác. Thread confinement chỉ đúng khi lifecycle thật sự bảo đảm giới hạn đó.

**Unsafe mutable state.** Các lời gọi có thể chỉnh cùng một buffer, cursor, parser hoặc cấu hình mà không có đồng bộ hóa. Phải thay đổi cách sử dụng hoặc thay thư viện.

**External shared resource.** Dù Java object thread-safe, hai worker có thể ghi vào cùng một bản ghi, file hoặc API có rate limit. Đây là **concurrency safety ở cấp hệ thống**, không chỉ thread safety của client.

Một bảng quyết định nhanh:

| State | Có thể chia sẻ một instance? | Ví dụ biện pháp |
| --- | --- | --- |
| Immutable + dependency an toàn | Thường có | Singleton cấu hình bất biến |
| API có hợp đồng thread-safe rõ | Có, trong giới hạn cam kết | Shared client + request object riêng |
| Mutable không an toàn | Không khi concurrent use | Per-call, per-StepExecution, lock hoặc pool |
| Resource gắn giao dịch | Chỉ theo phạm vi giao dịch cho phép | Lấy connection từ DataSource và đóng đúng lifecycle |
| Side effect chia sẻ ngoài JVM | Phụ thuộc nghiệp vụ | Unique key, transaction, idempotency, giới hạn tải |

## 6. Ví dụ lỗi: thư viện ngoài dùng buffer mutable

Giả sử một thư viện cũ cung cấp encoder sau:

~~~java
public final class LegacyRowEncoder {
    private final StringBuilder scratch = new StringBuilder();

    public String encode(long id, String name) {
        scratch.setLength(0);
        scratch.append(id).append('|').append(name);
        return scratch.toString();
    }
}
~~~

Đây là **thư viện giả định để minh họa**, không phải API có thật của Spring Batch. Lớp dùng **một StringBuilder mutable** trên mỗi instance. Nếu hai thread gọi encode đồng thời, các thao tác xóa/ghi/đọc buffer có thể xen kẽ:

~~~mermaid
sequenceDiagram
    participant A as Chunk thread A
    participant C as Shared LegacyRowEncoder
    participant B as Chunk thread B

    A->>C: setLength(0)
    A->>C: append("101")
    B->>C: setLength(0)
    B->>C: append("202")
    A->>C: append("|Alice")
    C-->>A: Kết quả có thể sai
    B->>C: append("|Bob")
    C-->>B: Kết quả có thể sai
~~~

Trong step tuần tự, encoder có thể chạy đúng suốt nhiều năm. Khi chuyển sang multi-threaded step, singleton encoder bắt đầu bị gọi đồng thời. Hậu quả có thể là dữ liệu sai ngẫu nhiên, không chỉ exception dễ thấy.

### Vì sao chỉ quan sát exception là chưa đủ?

Race condition có thể khiến hai kết quả bị tráo hoặc nhiễm lẫn nội dung nhưng vẫn là chuỗi hợp lệ, không phát sinh exception. Với writer, dữ liệu sai có thể được commit thành công. Vì thế kiểm thử phải có **expected output theo business key** và đối soát nội dung, không chỉ kiểm tra “không ném lỗi”.

## 7. Cách 1: thay bằng API immutable/stateless khi có thể

Nếu chức năng là format ngày giờ, dùng **DateTimeFormatter** thay cho việc chia sẻ **SimpleDateFormat** là ví dụ thường gặp:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

public final class BusinessDateFormatter {
    private static final DateTimeFormatter FORMAT =
            DateTimeFormatter.ofPattern("uuuuMMdd");

    public String format(LocalDate date) {
        return FORMAT.format(date);
    }
}
~~~

DateTimeFormatter được thiết kế immutable và thread-safe. Điều này thường giúp chia sẻ một instance mà không phải lock mỗi lời gọi. Tuy nhiên toàn bộ logic bên ngoài vẫn cần an toàn, ví dụ không ghi kết quả vào shared StringBuilder hoặc cache mutable thiếu đồng bộ.

**Ưu tiên:** thư viện cung cấp API immutable, stateless hoặc concurrent được chứng nhận, thay vì tự bao bọc object không an toàn bằng nhiều lớp lock phức tạp.

### Bất biến cấu hình cũng quan trọng

Một số mapper/client có thể dùng chung sau khi cấu hình hoàn tất, nhưng không an toàn nếu thread này thay đổi module, serializer, interceptor hoặc credential trong khi thread khác đang xử lý.

Quy ước tốt:

1. Khởi tạo và cấu hình đầy đủ trước khi job/worker chạy.
2. Publish instance qua Spring bean với lifecycle rõ.
3. Không sửa cấu hình runtime trên cùng object nếu tài liệu không bảo đảm.
4. Dùng request-specific object hoặc reader/writer được tạo riêng theo lời gọi khi API yêu cầu.

## 8. Cách 2: tạo instance riêng theo phạm vi sử dụng

Nếu thư viện không thread-safe nhưng khởi tạo rẻ, có thể tạo instance mới cho mỗi item, request hoặc chunk. Cách này loại bỏ shared mutable instance, nhưng chi phí allocation/khởi tạo có thể ảnh hưởng throughput.

Ví dụ processor tạo encoder tại mỗi lời gọi:

~~~java
import org.springframework.batch.item.ItemProcessor;

public record InputRow(long id, String fullName) {}
public record EncodedRow(long id, String encoded) {}

public final class PerCallEncodingProcessor
        implements ItemProcessor<InputRow, EncodedRow> {

    @Override
    public EncodedRow process(InputRow item) {
        LegacyRowEncoder encoder = new LegacyRowEncoder();
        String value = encoder.encode(item.id(), item.fullName());
        return new EncodedRow(item.id(), value);
    }
}
~~~

Mỗi lời gọi process có instance độc lập, do đó không tranh chấp buffer của encoder. Nhưng nếu encoder thực tế khởi tạo kết nối mạng, model lớn hoặc context mã hóa tốn kém, **per-call** có thể rất chậm. Cần đo cả CPU, allocation rate và GC.

### Instance riêng theo partition với @StepScope

Nếu worker StepExecution của mỗi partition chạy một luồng, tạo dependency trong bean **@StepScope** có thể là lựa chọn cân bằng:

~~~java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
public ItemProcessor<InputRow, EncodedRow> partitionProcessor() {
    LegacyRowEncoder encoder = new LegacyRowEncoder();

    return item -> new EncodedRow(
            item.id(),
            encoder.encode(item.id(), item.fullName()));
}
~~~

Trong local/remote partitioning, các partition thường có StepExecution khác nhau, vì vậy mỗi partition có thể nhận một processor và encoder riêng theo StepScope.

**Cảnh báo quan trọng:** nếu cùng một worker StepExecution lại xử lý nhiều chunk đồng thời, encoder trong bean StepScope này **vẫn có thể bị dùng chung bởi nhiều thread**. StepScope không đồng nghĩa ThreadScope. Cần xác minh topology thực tế trước khi tin rằng instance đã được cô lập.

### Vì sao ThreadLocal không phải lựa chọn mặc định?

Một ThreadLocal có thể tạo instance riêng cho thread, nhưng thread pool thường **tái sử dụng thread** giữa các partition hoặc job. Nếu không clear/remove theo lifecycle, state của job trước có thể tồn tại hoặc gây giữ bộ nhớ. ThreadLocal cũng không tự bảo đảm transaction/restart và khó quản lý client cần close. Ưu tiên scope/lifecycle minh bạch hoặc pool tài nguyên được thư viện hỗ trợ; chỉ dùng ThreadLocal khi có lý do rõ và kế hoạch cleanup chắc chắn.

## 9. Cách 3: đồng bộ hóa lời gọi tới thư viện không an toàn

Nếu một dependency không thể thay thế và phải chia sẻ một instance, có thể dùng một adapter đồng bộ:

~~~java
public final class LockedRowEncoder {
    private final LegacyRowEncoder delegate;

    public LockedRowEncoder(LegacyRowEncoder delegate) {
        this.delegate = delegate;
    }

    public synchronized String encode(long id, String name) {
        return delegate.encode(id, name);
    }
}
~~~

Adapter serializes các lời gọi **encode** qua cùng một instance LockedRowEncoder. Với lớp giả định trên, nó ngăn hai thread đồng thời sửa **scratch** thông qua adapter này.

Điều kiện:

- Không có code khác bypass adapter để gọi delegate trực tiếp.
- Không gọi method khác của delegate có thể sửa cùng state ngoài lock.
- Bảo đảm close/reconfigure cũng được bảo vệ nếu chúng thay đổi state dùng chung.
- Không giữ lock trong lời gọi network/I/O dài mà không đánh giá throughput và khả năng block.

**Đánh đổi:** nếu chỉ một thread được xử lý encoder tại một thời điểm, tăng 16 thread không làm giai đoạn encode nhanh 16 lần. Một lock có thể biến encoder thành **điểm tuần tự** của toàn JVM.

### Khi nào lock là lựa chọn tạm phù hợp?

Một thư viện cũ không thể thay ngay, thao tác rất ngắn, tần suất thấp và correctness quan trọng hơn throughput. Hãy đo thời gian chờ lock; nếu nó trở thành bottleneck, chuyển sang instance riêng hoặc thay API an toàn hơn.

## 10. Cách 4: pool đối tượng không thread-safe

Một số thư viện tạo đối tượng đắt đỏ nhưng cho phép **một instance được dùng bởi một caller tại một thời điểm**. Khi đó một pool giới hạn có thể phù hợp:

~~~text
Worker thread A ─┐
Worker thread B ─┼──> Pool 4 parser instance
Worker thread C ─┤     ├── parser-1: chỉ một borrower
Worker thread D ─┘     ├── parser-2: chỉ một borrower
                      ├── parser-3: chỉ một borrower
                      └── parser-4: chỉ một borrower
~~~

Một pool đúng cần:

- **Borrow/return** một instance với quyền sở hữu độc quyền.
- Reset state sau mỗi lần dùng theo hợp đồng library.
- Đóng hoặc loại bỏ instance bị lỗi/không còn hợp lệ.
- Giới hạn số object để kiểm soát CPU, heap, connection và license.
- Bảo đảm return trong **finally** hoặc cơ chế tương đương kể cả khi exception.
- Giám sát pool wait, pool exhausted và request latency.

**Không đồng nhất object pool với connection pool.** Nhiều JDBC DataSource đã có pooling, còn bản thân Connection/ResultSet thường có lifecycle gắn transaction/reader. Không tự pool đối tượng thư viện nếu nhà cung cấp đã có cơ chế pooling với lifecycle riêng.

Pool cũng không tự giải quyết lỗi logic khi response chứa tham chiếu tới buffer của instance vừa được trả về pool. Cần bảo đảm dữ liệu đầu ra đã được copy hoặc immutable theo hợp đồng.

## 11. Tạo kiểm thử concurrency có chủ đích

Kiểm thử một dependency thread-safe cần song song thật, input dễ đối soát và khả năng tái hiện lỗi. Dưới đây là ví dụ JUnit 5 kiểm tra adapter **LockedRowEncoder** khi nhiều thread đồng thời gọi encode.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

public class LockedRowEncoderTest {

    @Test
    void concurrentCallsProduceCorrectResults() throws Exception {
        int threads = 8;
        int itemsPerThread = 300;

        LockedRowEncoder encoder =
                new LockedRowEncoder(new LegacyRowEncoder());
        ExecutorService pool =
                Executors.newFixedThreadPool(threads);

        CountDownLatch ready = new CountDownLatch(threads);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> futures = new ArrayList<>();

        try {
            for (int thread = 0; thread < threads; thread++) {
                final int threadNo = thread;

                futures.add(pool.submit(() -> {
                    ready.countDown();
                    start.await();

                    for (int i = 0; i < itemsPerThread; i++) {
                        long id = threadNo * 100_000L + i;
                        String name = "user-" + id;
                        String expected = id + "|" + name;
                        String actual = encoder.encode(id, name);

                        assertEquals(expected, actual,
                                "Corrupted value for id " + id);
                    }
                    return null;
                }));
            }

            assertTrue(ready.await(10, TimeUnit.SECONDS),
                    "Workers did not become ready");
            start.countDown();

            for (Future<?> future : futures) {
                future.get(30, TimeUnit.SECONDS);
            }
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Các lớp **LegacyRowEncoder** và **LockedRowEncoder** là ví dụ đã trình bày ở trên. Với thư viện thật, thay encoder và expected result bằng dữ liệu nghiệp vụ/contract của dependency cần kiểm tra. Bài test cần được chạy trong môi trường có JUnit 5 tương thích và cùng version thư viện với production.

**Ý nghĩa của latch:** tám task đợi cổng **start** để tăng khả năng những lời gọi đầu tiên diễn ra sát nhau. Dùng thread pool có tám thread nên cả tám task có cơ hội đạt trạng thái ready. Điều này giúp phát hiện race dễ hơn test gọi tuần tự, nhưng không bảo đảm lịch scheduling tạo đúng interleaving có lỗi.

### Các khía cạnh cần thêm ngoài test mẫu

| Khía cạnh | Cách kiểm tra |
| --- | --- |
| **Correctness** | So đúng output cho từng business key; kiểm tra không mất/trùng |
| **Shared-instance stress** | Nhiều thread gọi **cùng một instance**, không vô tình tạo mới từng task |
| **Lifecycle race** | Thử gọi close/reset/reconfigure cạnh lúc xử lý nếu ứng dụng có làm |
| **Error race** | Xen kẽ input lỗi, timeout và exception với input hợp lệ |
| **Load** | Số thread, payload và thời lượng gần production |
| **Repeated execution** | Chạy lặp nhiều lần để tăng cơ hội bắt interleaving hiếm |
| **Performance** | Đo throughput, p95 latency, lock wait, allocation, GC |
| **Real worker test** | Chạy multi-threaded step/partitioning thực với DB và transaction |

**Test pass không chứng minh hoàn toàn absence of races.** Nó chỉ cung cấp bằng chứng cho tập trường hợp đã chạy. Tài liệu API, phân tích thiết kế và thử lỗi thực tế vẫn quan trọng. Có thể cân nhắc công cụ kiểm thử concurrency chuyên biệt như **jcstress** cho những invariant phức tạp; không mặc định load test end-to-end thay thế được kiểm thử memory visibility.

## 12. Kiểm tra tính nhất quán trước và sau concurrency

Thread safety không chỉ là **không ném exception**. Một thư viện sai có thể tạo kết quả hợp lệ về mặt syntax nhưng không khớp business key.

Ví dụ batch chuẩn hóa 1 triệu địa chỉ email có thể phát sinh:

- Dữ liệu item A bị ghi sang khóa của item B.
- Parser trả về nội dung từ lời gọi trước.
- Một hàng bị đọc hai lần còn hàng khác bị bỏ sót.
- Một writer flush buffer chứa dữ liệu của nhiều chunk nhầm thứ tự.
- Hệ thống báo COMPLETED dù số record đúng không đầy đủ.

Đối soát nên gồm:

1. **Số item nguồn hợp lệ** sau filter/skip được giải thích.
2. **Số business key duy nhất** ở đích.
3. **Checksum/hash hoặc canonical representation** cho dữ liệu đầu ra có thể tái lập.
4. **Tập khóa thiếu/trùng**, không chỉ tổng số dòng.
5. **Kết quả chạy tuần tự so với song song** cho cùng snapshot và quy tắc nghiệp vụ.
6. **Kết quả sau crash/restart** so với kết quả không bị gián đoạn.

Nếu thứ tự output không phải yêu cầu nghiệp vụ, hãy so sánh như **tập dữ liệu theo business key**, không đòi thứ tự ghi giống nhau. Multi-threaded step và partitioning có thể hoàn thành chunk/partition khác thứ tự mà vẫn đúng.

### Ví dụ SQL đối soát

Giả sử có bảng **batch_result** với các cột business_key và batch_id:

~~~sql
-- Phát hiện business key bị ghi trùng trong cùng lần chạy
SELECT business_key, COUNT(*) AS occurrences
FROM batch_result
WHERE batch_id = :batchId
GROUP BY business_key
HAVING COUNT(*) > 1;
~~~

Query chỉ kiểm tra một loại duplicate; cần thêm kiểm tra missing key và giá trị output theo nghiệp vụ. Khóa duy nhất ở DB có thể ngăn ghi trùng vật lý nhưng không ngăn writer vô tình ghi **sai giá trị vào đúng key**.

## 13. Tại sao @StepScope cần được hiểu đúng?

Đây là một trong những chỗ dễ gây lỗi nhất khi mở rộng Spring Batch.

### 13.1. Multi-threaded step

Một StepExecution có thể xử lý nhiều chunk đồng thời:

~~~mermaid
flowchart TB
    SE["Một StepExecution"]
    SE --> P["Một processor @StepScope"]
    A["Chunk thread A"] --> P
    B["Chunk thread B"] --> P
    C["Chunk thread C"] --> P
    P --> SDK["Một legacy SDK mutable"]
~~~

**Kết luận:** processor **@StepScope** không tự cung cấp ba instance SDK cho ba chunk thread của cùng StepExecution. Nếu SDK không thread-safe, cần instance per-call, một adapter an toàn hoặc cách bố trí không chia sẻ instance.

### 13.2. Local partitioning

Các partition có StepExecution khác nhau:

~~~mermaid
flowchart TB
    M["Manager"]
    M --> S1["StepExecution partition-1"]
    M --> S2["StepExecution partition-2"]
    S1 --> P1["Processor @StepScope 1"]
    S2 --> P2["Processor @StepScope 2"]
    P1 --> L1["Legacy SDK instance 1"]
    P2 --> L2["Legacy SDK instance 2"]
~~~

Nếu mỗi processor tạo **một instance SDK riêng**, không có chia sẻ state của SDK giữa hai StepExecution. Nhưng nếu cả hai processor inject **cùng singleton SDK bean**, chúng vẫn dùng chung instance. Ngoài ra, worker step có thể cấu hình đa luồng nội bộ, nên tiếp tục cần kiểm tra thực tế.

**Không suy luận scope chỉ từ annotation đặt trên ItemProcessor; phải xem nơi SDK instance được tạo, inject và đóng.**

## 14. HTTP SDK: client dùng chung khác request dùng chung

Trong nhiều ứng dụng batch, writer gọi hệ thống ngoài bằng HTTP. Một SDK có thể khuyến khích **reuse client** vì client quản lý connection pool, nhưng điều đó không đồng nghĩa mọi object nó tạo ra đều thread-safe.

Các thành phần cần phân biệt:

- **HTTP client:** có thể cho phép nhiều request đồng thời, tùy thư viện và cấu hình.
- **Request builder:** thường là mutable; nên tạo riêng mỗi lời gọi nếu API yêu cầu.
- **Request body stream:** có thể chỉ đọc được một lần; retry cần khả năng tạo lại payload.
- **Response stream:** phải được tiêu thụ/đóng đúng lifecycle, không truyền bừa giữa thread.
- **Authentication provider:** refresh token có state; phải kiểm tra concurrent refresh.
- **Interceptor/retry policy:** callback tùy biến có thể dùng biến mutable hoặc cache không an toàn.
- **Rate limiter:** có thể thread-safe nhưng vẫn là giới hạn throughput toàn tài khoản/API.

### Ví dụ rủi ro với builder dùng chung

~~~java
// Mã giả: minh họa anti-pattern, không phải API của SDK cụ thể.
class UnsafeApiAdapter {
    private final MutableRequestBuilder sharedBuilder =
            new MutableRequestBuilder();

    ApiResponse send(String businessId, String payload) {
        sharedBuilder.setBusinessId(businessId);
        sharedBuilder.setBody(payload);
        return client.execute(sharedBuilder.build());
    }
}
~~~

Nếu thread A gán businessId rồi thread B thay payload trước khi A build, request có thể mang dữ liệu không tương ứng. Khắc phục thông thường là tạo request builder **mới theo mỗi lời gọi**, còn client có thể được chia sẻ **nếu tài liệu API bảo đảm**.

**Lưu ý:** ngay cả một HTTP client thread-safe vẫn có thể gửi cùng request hai lần do retry sau timeout. Đây là vấn đề **idempotency ở cấp nghiệp vụ**, độc lập với memory safety của SDK.

## 15. JDBC và ORM: pool an toàn không có nghĩa mọi handle an toàn

Với JDBC, nhiều người nhầm **DataSource pool** và **Connection** là một loại object.

Một pooled DataSource được thiết kế để cấp nhiều connection cho nhiều luồng theo hợp đồng cụ thể; nhưng **Connection**, **PreparedStatement** và **ResultSet** thường có trạng thái giao dịch/cursor và không nên dùng đồng thời giữa các chunk thread nếu driver không bảo đảm.

Ví dụ anti-pattern:

~~~java
// KHÔNG làm theo: connection và statement dùng chung giữa nhiều chunk.
class UnsafeJdbcGateway {
    private Connection sharedConnection;
    private PreparedStatement sharedStatement;

    void write(Order row) throws SQLException {
        sharedStatement.setLong(1, row.id());
        sharedStatement.executeUpdate();
    }
}
~~~

Hai thread có thể ghi tham số vào cùng statement, dùng chung transaction không mong muốn hoặc đóng resource khi thread khác đang thực hiện. Hơn nữa, lỗi DB có thể chỉ xuất hiện dưới tải thực.

Thiết kế phù hợp hơn:

- Dùng **DataSource**/transaction manager đúng lifecycle của Spring Batch.
- Để reader/writer hoặc framework sở hữu connection/statement theo phạm vi giao dịch.
- Tránh giữ Connection như mutable field singleton dùng chung.
- Kiểm tra JDBC driver và ORM session của phiên bản thực tế.
- Với **JdbcBatchItemWriter**, đánh giá behavior của writer và state truy cập khi dùng multi-threaded step.
- Với JPA/Hibernate, không dùng một persistence context/session mutable cho nhiều thread thiếu kiểm soát.

**Hiệu năng:** mỗi worker/chunk đồng thời có thể cần connection; tổng giới hạn connection pool phải phù hợp sức chịu tải DB, không chỉ số thread cấu hình.

## 16. Khi thread safety đúng nhưng kết quả vẫn sai: atomicity và ordering

Một ConcurrentHashMap hoặc HTTP client thread-safe không bảo đảm **tính nguyên tử của chuỗi nghiệp vụ**.

Ví dụ hai worker cùng đọc số dư 1.000, mỗi worker cộng 100 rồi ghi 1.100. Cả hai lời gọi SDK riêng lẻ có thể thread-safe, nhưng kết quả cuối đúng phải là 1.200 nếu cả hai giao dịch hợp lệ; đây là **lost update**.

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant DB as Database
    participant B as Worker B
    A->>DB: Đọc tổng = 1000
    B->>DB: Đọc tổng = 1000
    A->>DB: Ghi 1100
    B->>DB: Ghi 1100
    Note over A,B: SDK có thể thread-safe, nghiệp vụ vẫn sai
~~~

Giải quyết ở cấp transaction hoặc mô hình dữ liệu: atomic update, optimistic/pessimistic locking, partition ownership, unique key hoặc ghi kết quả theo từng partition rồi tổng hợp. Chỉ bọc SDK trong một synchronized block **trong mỗi JVM** không đảm bảo serializable update trên toàn hệ thống nhiều JVM.

Tương tự, nếu một thư viện có API thread-safe nhưng nghiệp vụ yêu cầu thứ tự theo khách hàng, việc các chunk hoàn thành khác thứ tự vẫn có thể gây sai. Phải xác định thứ tự và ranh giới sở hữu dữ liệu trước khi song song hóa.

## 17. Retry/restart khiến việc kiểm tra dependency khó hơn

Một thư viện có thể đúng trong điều kiện không lỗi nhưng rò state khi một lời gọi thất bại giữa chừng:

- Parser/encoder để lại buffer ở trạng thái chưa reset.
- HTTP client đánh dấu request đã gửi nhưng caller lại retry.
- Writer flush một phần dữ liệu rồi throw exception.
- Connection/session bị lỗi không được trả về pool.
- Token refresh thất bại khiến các thread cùng thử refresh liên tục.
- SDK cache giữ dữ liệu từ chunk trước sau khi worker bị retry.

Trong Spring Batch, một chunk lỗi có thể rollback và item được đọc/xử lý/ghi lại theo fault tolerance và checkpoint. **SDK phải chịu được hành vi sử dụng lại mà framework có thể thực hiện**, hoặc phải tạo instance sạch sau lỗi.

### Ma trận fault injection

| Sự cố | Điều cần kiểm chứng |
| --- | --- |
| Parser throw giữa item | Lời gọi sau có dùng nhầm buffer cũ không? |
| DB timeout giữa write | Statement/connection được xử lý đúng, dữ liệu không ghi một phần ngoài ý muốn? |
| HTTP timeout sau khi dịch vụ đã nhận request | Retry có idempotency key và không tạo side effect hai lần? |
| Worker chết giữa chunk | Checkpoint đưa job trở lại phần đúng; writer không nhân đôi dữ liệu? |
| Một partition lỗi, partition khác chạy | Shared singleton không làm lỗi lan sang partition khác? |
| Request đến đồng thời lúc refresh token | Không tạo race trong auth provider hoặc làm nghẽn hàng loạt request? |
| Shutdown trong lúc đang xử lý | close/cleanup không phá resource đang được thread khác dùng? |

Không coi việc một test concurrency pass là bằng chứng restart an toàn. **Thread safety**, **transaction correctness** và **recovery correctness** liên quan chặt nhưng là ba loại bằng chứng cần kiểm tra riêng.

## 18. Quan sát vấn đề trong production

Race condition có thể hiếm và khó tái hiện. Khi vận hành batch song song, cần đủ thông tin để liên kết output sai với thread/partition/SDK version.

| Nhóm metric/log | Mục đích |
| --- | --- |
| **JobExecution ID / StepExecution ID** | Xác định execution và trạng thái checkpoint |
| **Partition name / worker instance** | Biết dữ liệu thuộc phần việc nào |
| **Thread name** | Phát hiện nhiều chunk gọi cùng một instance |
| **SDK name/version** | Xác định hợp đồng và thay đổi hành vi |
| **Client identity** (định danh kỹ thuật, không phải secret) | Biết có một instance bị chia sẻ ngoài ý muốn |
| **Rate/latency theo thao tác** | Thấy lock/queue wait, saturation |
| **Retry/rollback/skip counts** | Nhận ra lỗi xuất hiện sau khi tăng concurrency |
| **Heap/GC, pool wait** | Đánh giá chi phí instance per-call/per-partition |
| **Business-key reconciliation** | Tìm dữ liệu sai mà không có exception |

Log ví dụ:

~~~text
jobExecutionId=9401
stepExecutionId=9430
stepName=normalizeOrders:partition-3
workerInstance=batch-worker-02
thread=batch-io-4
sdkComponent=legacy-row-encoder
sdkVersion=2.4
sharingPolicy=per-step-execution
readCount=125000
writeCount=125000
rollbackCount=0
status=COMPLETED
~~~

Giá trị hoàn toàn minh họa. Tránh log payload chứa dữ liệu nhạy cảm, token, password hoặc dữ liệu cá nhân. Với hệ thống metric có nhãn, cần tránh cardinality quá cao khi dùng ID động làm nhãn.

### Dấu hiệu thường gặp của race

- Lỗi chỉ xuất hiện khi tăng thread từ 1 lên 4 hoặc 8.
- Test unit từng item pass, integration test đa luồng thỉnh thoảng sai.
- Output sai business key nhưng trạng thái batch vẫn COMPLETED.
- Lỗi biến mất khi thêm synchronized hoặc giảm concurrency (đây là manh mối, **không phải chứng minh nguyên nhân**).
- Một số exception dạng concurrent modification, closed stream, invalid cursor hoặc parse corruption.
- Thời gian GC/lock wait tăng sau khi thêm wrapper hoặc pooling chưa phù hợp.

Không sửa race bằng cách thêm sleep ngẫu nhiên hoặc tăng retryLimit vô hạn. Phải xác định object có state nào bị truy cập ngoài hợp đồng thread safety.

## 19. Bài toán minh họa: chuẩn hóa 4 triệu giao dịch

Một hệ thống xử lý **4.000.000 giao dịch** trong cửa sổ 12 phút. Processor gọi thư viện ngoài để chuẩn hóa mô tả và phân nhóm giao dịch. Ban đầu job tuần tự đúng dữ liệu nhưng throughput chưa đạt yêu cầu.

### Giai đoạn 1 — Baseline

Giả sử throughput đã đo:

| Cấu hình | Write throughput | Đối soát business key | Nhận xét |
| --- | ---: | --- | --- |
| Một step tuần tự | 3.400 item/s | PASS | Chưa đạt SLA 12 phút |
| Bốn chunk threads, dùng singleton SDK mutable | 8.800 item/s | FAIL | Có kết quả chuẩn hóa sai |
| Bốn threads + synchronized adapter | 4.100 item/s | PASS | Lock hạn chế parallelism |
| Bốn local partitions, mỗi StepExecution có SDK riêng | 7.200 item/s | PASS | Có ích nếu DB còn dư |
| Tám local partitions, mỗi StepExecution có SDK riêng | 7.800 item/s | PASS | Lợi ích biên giảm |

Đây là **số liệu giả định** nhằm minh họa cách đánh giá. Với 4 triệu item và SLA 720 giây, throughput lý tưởng tối thiểu:

\[
R_{\mathrm{required}}=\frac{4.000.000}{720}
\approx 5.556\ \mathrm{item/s}
\]

Cấu hình **4 threads + singleton SDK mutable** có tốc độ cao nhưng **không hợp lệ** vì dữ liệu sai. **Synchronized adapter** giữ đúng dữ liệu nhưng không đạt SLA. **Bốn local partition** đạt tốc độ lý tưởng cần thiết với khoảng 7.200 item/s và có đầu ra đúng trong thí nghiệm.

### Giai đoạn 2 — Kiểm tra nguồn gây lỗi

Nhóm rà soát dependency và phát hiện encoder singleton giữ một **buffer mutable** theo object. Test nhiều thread cùng gọi một instance cho thấy output của item này chứa dữ liệu item khác. Processor bản thân không có field mutable, nhưng object graph vẫn có state chia sẻ.

### Giai đoạn 3 — Sửa thiết kế

Thay vì đặt lock duy nhất trên toàn JVM, nhóm chia input theo range ID và tạo **instance encoder riêng trong processor @StepScope** cho mỗi partition. Reader cũng được tạo riêng theo StepExecution. Mỗi partition có một thread xử lý, do đó encoder không bị dùng chung giữa các partition.

Đội ngũ vẫn phải kiểm tra các singleton dependency còn lại và đảm bảo **không bật multi-threaded chunk bên trong cùng worker step** nếu encoder theo StepScope không được thiết kế concurrent.

### Giai đoạn 4 — Kiểm tra lỗi và tải thực

- Thử kill worker giữa chunk và restart.
- Đối soát tập business key, nội dung chuẩn hóa và số record thiếu/trùng.
- Đo throughput, heap, GC, CPU, pool wait, DB lock và thời gian phân vùng cuối hoàn tất.
- Thử dữ liệu lỗi làm encoder throw exception, kiểm tra instance có còn state hỏng.
- Tăng số partition và thread từng nấc, dừng khi DB hoặc CPU bắt đầu bão hòa.

**Kết luận:** lựa chọn đúng không phải kiến trúc có throughput giả định cao nhất, mà là kiến trúc **đạt SLA, đúng dữ liệu và có thể phục hồi**. Không có thread-safe SDK thì tăng worker có thể chỉ làm lỗi dữ liệu xuất hiện nhanh hơn.

## 20. Ma trận lựa chọn cách khắc phục

| Tình huống | Ưu tiên giải pháp | Đánh đổi cần đo |
| --- | --- | --- |
| Có API immutable/thread-safe thay thế | Dùng API mới | Tính tương thích và semantics |
| SDK mutable nhưng khởi tạo rẻ | Instance per-call | Allocation, GC, khởi tạo |
| SDK mutable, một instance dùng an toàn theo partition | StepScope/per-StepExecution | Số instance, lifecycle; không tự an toàn khi worker step multi-thread |
| SDK mutable, thao tác ngắn, tải thấp | Adapter synchronized | Lock contention, throughput |
| SDK mutable, khởi tạo đắt, hỗ trợ reset | Object pool độc quyền | Pool wait, reset, leak và lỗi cleanup |
| SDK có client thread-safe, request mutable | Shared client + request builder per-call | Pool capacity, payload, timeout |
| SDK có session/connection gắn transaction | Resource per-transaction/per-step | Connection pool, close và timeout |
| API ngoài có side effect không idempotent | Bổ sung idempotency/outbox | Thiết kế giao dịch và trạng thái |
| Cần thứ tự tuyệt đối | Phân vùng theo key hoặc giữ tuần tự phần liên quan | Critical path và thiết kế business |
| Không có bằng chứng an toàn, không thể thử đủ | Cô lập/chặn concurrency cho component đó | Giảm parallelism để giữ correctness |

Không cần chọn mô hình phân tán chỉ để sửa một parser không thread-safe. Ngược lại, nếu workload phù hợp partitioning và mỗi partition có input độc lập, lựa chọn phân vùng có thể đơn giản hơn việc duy trì nhiều lock trên một reader hoặc SDK phức tạp.

## 21. Các sai lầm thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| “Bean singleton của Spring mặc nhiên thread-safe.” | Singleton chỉ nói vòng đời/số instance, không bảo đảm an toàn concurrent use. |
| “Processor không có field nên an toàn.” | Processor có thể gọi singleton service hoặc SDK mutable bên trong. |
| “@StepScope tạo object cho từng thread.” | StepScope gắn với **StepExecution**, không phải thread của chunk. |
| “Nhiều JVM nghĩa là không cần thread safety.” | Mỗi JVM vẫn có thể xử lý nhiều partition đồng thời và chia sẻ singleton. |
| “Client HTTP thread-safe thì request builder cũng thread-safe.” | Hợp đồng từng object khác nhau; builder/body thường có state riêng. |
| “DataSource pool thread-safe nên Connection có thể chia sẻ.” | Connection/statement/cursor có lifecycle khác pool và thường không nên concurrent use. |
| “Test 100 lần pass nghĩa là không có race.” | Stress test chỉ tăng mức tin cậy, không chứng minh absence of races. |
| “Thêm synchronized không tốn hiệu năng.” | Lock có thể tuần tự hóa giai đoạn nóng và giảm throughput. |
| “ThreadLocal luôn giải quyết state.” | Thread pool tái sử dụng thread; cần cleanup/lifecycle rõ. |
| “Có lỗi thì bật retry là xong.” | Retry có thể lặp lỗi hoặc nhân side effect, nhất là ngoài transaction. |
| “Kết quả đủ số dòng là đúng.” | Vẫn có thể sai giá trị, nhầm business key hoặc trùng–thiếu bù trừ. |
| “SDK an toàn thì nghiệp vụ tự đúng.” | Atomicity, ordering và idempotency ở DB/API vẫn phải được thiết kế. |

## 22. Checklist rà soát dependency trước khi tăng concurrency

- [ ] Liệt kê các thư viện được reader, processor, writer và listener gọi.
- [ ] Xác định **phiên bản đang triển khai** và hợp đồng thread safety của API cụ thể.
- [ ] Ghi lại nơi instance được tạo, scope, owner và điều kiện close/reset.
- [ ] Kiểm tra custom callback, interceptor, mapper, serializer và cache có state.
- [ ] Phân biệt client thread-safe với request/session/connection mutable.
- [ ] Xác nhận model concurrency: multi-threaded step, parallel steps hay partitioning.
- [ ] Không mặc định @StepScope tạo một object cho từng chunk thread.
- [ ] Nếu instance không an toàn, đã chọn per-call, per-step, lock hoặc pool phù hợp.
- [ ] Kiểm thử đồng thời **cùng instance** và đối soát expected output theo business key.
- [ ] Chạy stress test lặp lại với concurrency và payload đại diện.
- [ ] Thử exception, timeout, shutdown/close và retry trong lúc các thread khác chạy.
- [ ] Đã kiểm tra checkpoint, restart, side effect và idempotency.
- [ ] Đo tốc độ trước/sau biện pháp an toàn, cùng CPU, heap/GC, lock/pool wait.
- [ ] Tính giới hạn connection/API tổng cộng nếu có nhiều worker JVM.
- [ ] Có log/metric liên hệ StepExecution, partition, thread và SDK version.
- [ ] Chỉ nâng concurrency khi **kết quả đúng** và throughput/SLA được cải thiện.

## 23. Câu hỏi tự kiểm tra

**1. Một ItemProcessor không có field mutable nhưng gọi một JSON mapper singleton. Có thể kết luận processor thread-safe không?**

Chưa. Cần xem hợp đồng mapper và mọi module/deserializer/callback mà nó dùng, cách cấu hình và có thay cấu hình khi đang chạy hay không. Nếu mapper được hỗ trợ chia sẻ sau khi cấu hình hoàn tất và các dependency liên quan an toàn, mới có cơ sở sử dụng đồng thời.

**2. Vì sao @StepScope không đủ để sửa lỗi SDK mutable trong multi-threaded step?**

Vì các chunk threads của cùng StepExecution có thể cùng truy cập một bean StepScope. SDK bên trong vẫn là một instance được dùng đồng thời, trừ khi có chiến lược cô lập khác.

**3. Với local partitioning, khi nào dùng instance SDK per-StepExecution có thể an toàn?**

Khi mỗi partition có StepExecution và instance riêng, không có chia sẻ SDK sang partition khác, mỗi instance không được nhiều thread gọi đồng thời, và các dependency ngoài nó cũng tuân thủ hợp đồng thread safety.

**4. Một test chạy 1.000 lần không ném exception, đã chứng minh SDK thread-safe chưa?**

Chưa. Lỗi race phụ thuộc lịch thread và có thể chỉ làm sai giá trị. Cần hợp đồng API, test với expected output, concurrency/lifecycle/fault injection và kiểm chứng dữ liệu.

**5. Tại sao synchronized có thể làm tăng độ đúng nhưng giảm throughput?**

Nó ngăn nhiều thread vào vùng bảo vệ đồng thời nhưng cũng tạo một đoạn tuần tự. Nếu SDK nằm trên hot path, lock sẽ giới hạn tốc độ của toàn JVM.

**6. Sử dụng pooled DataSource an toàn có nghĩa có thể lưu một PreparedStatement thành field singleton rồi chia sẻ không?**

Không. DataSource và Connection/PreparedStatement có hợp đồng và lifecycle khác nhau. Statement thường gắn với connection/transaction; cần dùng theo phạm vi framework/driver cho phép.

**7. Nếu writer gọi API ngoài thành công rồi chunk bị retry, rủi ro gì xảy ra dù HTTP client thread-safe?**

API có thể nhận cùng thao tác hai lần. Cần idempotency key hoặc cơ chế tránh side effect lặp, vì tính thread-safe của client không giải quyết giao dịch qua hai hệ thống.

**8. Sau khi chuyển sang partitioning, kết quả đúng nhưng throughput giảm, nên điều tra gì?**

Đo chi phí tạo StepExecution, số partition/worker, CPU/GC khi tạo nhiều instance SDK, connection pool, lock DB, tải API và phân bố thời gian partition. Correctness là bắt buộc, nhưng mô hình song song còn phải phù hợp với tài nguyên.

---

**Ghi nhớ:** Kiểm tra thread safety của thư viện ngoài là kiểm tra **hợp đồng sử dụng đồng thời của từng instance và cả dependency graph**, trong **mô hình concurrency thực tế** của Spring Batch. Đừng suy luận rằng singleton, @StepScope, pooled client hoặc test happy path đã tự bảo đảm an toàn. Hãy kết hợp tài liệu đúng phiên bản, cô lập state, kiểm thử concurrent với expected output, fault injection và đối soát sau restart; chỉ tăng thread/worker khi **tính đúng và lợi ích throughput** đều được chứng minh.
