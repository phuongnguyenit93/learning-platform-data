# GC và object allocation trong Spring Batch

## 1. Mục tiêu

Một Spring Batch job có thể xử lý hàng triệu bản ghi mà vẫn chậm, dù truy vấn SQL và thuật toán nghiệp vụ tương đối đơn giản. Nguyên nhân đôi khi nằm ở **object allocation** (cấp phát đối tượng) và **garbage collection — GC** (thu gom bộ nhớ): mỗi bản ghi tạo ra nhiều đối tượng tạm; JVM phải dành CPU để cấp phát, theo dõi và thu hồi chúng. Nếu job giữ tham chiếu quá lâu, dữ liệu còn sống tăng lên và GC phải làm việc nặng hơn.

Ví dụ một bước import xử lý 5 triệu dòng CSV. Mỗi dòng được chuyển thành `InputRow`, làm sạch chuỗi, tạo DTO mới, xây dựng tham số SQL rồi ghi database. Nếu trung bình có 2 KB đối tượng được cấp phát trong quá trình xử lý mỗi dòng, tổng allocation trong một lượt có thể lên tới khoảng **10 GB** dù kích thước heap được giới hạn ở vài GB. Đây không nhất thiết là memory leak: nhiều đối tượng chỉ tồn tại rất ngắn rồi được thu gom.

Bài học thuộc nhóm **Performance** của **Spring Batch Core Processing**, tập trung vào những mục tiêu:

- Hiểu heap, vòng đời đối tượng và GC trong luồng Reader → Processor → Writer.
- Phân biệt **tốc độ cấp phát**, **bộ nhớ còn sống**, **đỉnh sử dụng heap** và **thời gian tạm dừng do GC**.
- Nhận diện vị trí tạo nhiều đối tượng và giữ tham chiếu quá lâu trong các job chunk-oriented.
- Sử dụng GC log, Java Flight Recorder (JFR), công cụ profiling và số đếm của Spring Batch để quan sát nguyên nhân.
- Cải thiện processor, reader, writer, chunk size, concurrency và cách quản lý state mà không làm sai dữ liệu hoặc mất khả năng restart.
- Thiết kế phép đo trước/sau tối ưu có thể đối chiếu, tránh dựa vào cảm giác hoặc một lần chạy tình cờ.

Ví dụ giả định Java 17+, Spring Boot 3.x và Spring Batch 5.x. Những phiên bản JVM/Batch khác có thể có hành vi GC, công cụ quan sát và API cấu hình khác.

## 2. Object allocation và GC: mô hình tư duy

**Object allocation** là việc JVM cấp phát vùng bộ nhớ cho một đối tượng mới như `String`, `ArrayList`, `BigDecimal`, DTO, mảng hoặc cấu trúc mà thư viện tạo ngầm. Phần lớn đối tượng Java thông thường nằm trên heap, mặc dù JIT có thể tối ưu để một số đối tượng không cần tồn tại vật lý nhờ escape analysis và scalar replacement.

**GC** xác định những đối tượng không còn được tham chiếu từ các GC roots và thu hồi vùng heap có thể tái sử dụng. GC không xóa ngay một đối tượng khi nó ra khỏi phạm vi biểu thức; thời điểm thu gom do collector và trạng thái heap quyết định.

Luồng xử lý minh họa:

```text
           Nguồn dữ liệu
                |
                v
       ItemReader.read()
          | tạo InputRow, String, mảng...
          v
       ItemProcessor.process()
          | tạo OutputRow, giá trị chuẩn hóa...
          v
       Chunk chứa tối đa N item đầu ra
          |
          v
       ItemWriter.write(chunk)
          | binding SQL, serialization, buffer...
          v
       Commit chunk / release references
          |
          v
       Những object hết tham chiếu trở thành
       ứng viên để GC thu hồi khi cần
```

Từ góc độ performance, cần phân biệt bốn đại lượng:

| Đại lượng | Ý nghĩa | Ví dụ vấn đề |
| --- | --- | --- |
| **Allocation rate** | Số byte đối tượng được cấp phát trên một giây | Tạo `String`/DTO mới liên tục khiến GC chạy thường xuyên |
| **Live set / retained heap** | Dữ liệu vẫn còn tham chiếu và không thể thu gom | Cache hoặc `ExecutionContext` giữ toàn bộ bản ghi |
| **Heap occupancy / peak heap** | Mức heap được dùng theo thời gian | Chunk, page, queue và cache đẩy đỉnh bộ nhớ lên cao |
| **GC overhead / pause** | CPU và thời gian tạm dừng dành cho GC | Job mất thời gian chờ thu gom thay vì đọc/ghi dữ liệu |

Một job có **allocation rate cao** chưa chắc xấu nếu đối tượng rất ngắn hạn và GC xử lý hiệu quả. Một job có allocation rate không cao vẫn có thể hết bộ nhớ nếu giữ toàn bộ dữ liệu trong một collection sống suốt job.

### Ví dụ về allocation rate

Giả sử:

- Job xử lý 20.000 item/giây.
- Trung bình mỗi item tạo 1.500 byte đối tượng trên heap.
- Không có thay đổi đáng kể về lượng dữ liệu được giữ lâu dài.

Tốc độ cấp phát xấp xỉ:

```text
20.000 item/s × 1.500 byte/item
    = 30.000.000 byte/s
    ≈ 30 MB/s (đơn vị thập phân)
```

Nếu job chạy 10 phút, tổng lượng cấp phát xấp xỉ 18 GB. Điều này **không có nghĩa cần heap 18 GB**: nếu phần lớn đối tượng chết nhanh, chúng có thể được thu gom nhiều lần trong quá trình xử lý.

Ngược lại, nếu job thêm tất cả item vào một danh sách và giữ đến cuối, live set có thể tăng gần tuyến tính với số bản ghi. Khi đó tăng heap chỉ hoãn thời điểm hết bộ nhớ.

## 3. GC của JVM tác động đến Spring Batch như thế nào?

Các JVM hiện đại sử dụng nhiều chiến lược GC; trong Java 17, G1 là lựa chọn mặc định phổ biến của HotSpot trên cấu hình server. Các collector khác như ZGC hoặc Shenandoah có các đánh đổi khác nhau về pause, CPU và bộ nhớ. Trước khi đổi collector, cần biết **điểm nghẽn thật sự**.

Một cách diễn giải đơn giản về heap của các collector theo thế hệ:

```text
            Java Heap
   +----------------------------+
   |        Vùng đối tượng      |
   |         mới tạo            |
   |   (thường được thu gom     |
   |     sau thời gian ngắn)    |
   +----------------------------+
   |        Vùng đối tượng      |
   |      tồn tại lâu hơn       |
   |   (cache, state, buffers)  |
   +----------------------------+
```

Với G1, heap được chia thành các region và các bước thu gom không đơn giản là “quét toàn bộ young rồi old” ở mỗi lần GC. Tuy vậy, mô hình **đối tượng ngắn hạn** so với **đối tượng sống lâu** vẫn hữu ích để hiểu áp lực cấp phát và giữ bộ nhớ.

### Điều gì làm job chậm?

- **Thu gom thường xuyên:** mỗi giây tạo nhiều object tạm khiến JVM phải GC liên tục.
- **Đối tượng được giữ qua nhiều chunk:** queue, cache, collection hoặc context còn giữ tham chiếu khiến live set tăng.
- **Pause cao:** collector cần các khoảng dừng để hoàn thành một số công đoạn; các pause lớn có thể kéo dài thời gian batch, timeout hoặc làm trigger sau chồng lên job trước.
- **Allocation thất bại/OOM:** không còn đủ không gian để cấp phát hoặc có áp lực bộ nhớ ngoài heap làm process bị hệ điều hành/container kết thúc.
- **CPU contention:** GC threads, application threads, JDBC/network xử lý cùng tranh CPU; tăng thread chưa chắc cải thiện throughput.

Mức heap sử dụng thường tăng rồi giảm theo hình răng cưa khi GC thu hồi đối tượng. Không nên kết luận memory leak chỉ vì heap tăng dần trước mỗi chu kỳ GC. Dấu hiệu đáng quan tâm hơn là **mức heap còn giữ lại sau GC tăng liên tục trong các giai đoạn khối lượng xử lý tương đương**, đồng thời dữ liệu đáng lẽ phải giải phóng vẫn được tham chiếu.

## 4. Vì sao Spring Batch dễ tạo nhiều object?

Chunk processing tạo nhiều đối tượng nhỏ nhưng lặp lại rất nhiều lần:

| Giai đoạn | Ví dụ đối tượng được tạo | Rủi ro thường gặp |
| --- | --- | --- |
| `ItemReader` | Row DTO, `String`, array, map, token, object do mapper tạo | Parse lại nhiều lần; đọc toàn bộ nguồn vào bộ nhớ |
| `ItemProcessor` | DTO mới, `BigDecimal`, `LocalDate`, chuỗi chuẩn hóa, regex matcher | Tạo formatter/parser hoặc clone/copy collection cho từng item |
| `ItemWriter` | SQL parameter map, mảng batch, payload JSON, buffer HTTP | Giữ output toàn bộ job; tạo JSON tree lớn trước khi gửi |
| Chunk infrastructure | Các item được gom trong chunk và trạng thái lỗi/retry | Chunk quá lớn; output object nặng tồn tại lâu |
| `ExecutionContext` | State phục vụ restart, object được serialize | Lưu cả danh sách item/tham chiếu vào context |
| Partitioning/parallel step | Queue, task, partition context, connection | Bộ đệm và số item đang xử lý tăng theo mức song song |
| Logging/observability | Chuỗi log, stack trace, tag/metric, exception | Log mỗi item, ghi payload lớn hoặc quá nhiều object không cần thiết |

Đặc biệt, dùng `ListItemReader` với một danh sách hàng triệu phần tử để mô phỏng reader trong production sẽ giữ toàn bộ nguồn từ đầu. Với dữ liệu lớn, nên ưu tiên reader có tính streaming hoặc paging thích hợp, kết hợp kiểm soát fetch size và trạng thái restart.

### Đối tượng tạm và retained object khác nhau

Ví dụ:

```java
public ProcessedRow process(InputRow item) {
    String cleaned = item.name().trim().toUpperCase();
    return new ProcessedRow(item.id(), cleaned);
}
```

Mỗi lời gọi có thể tạo object mới. Nhưng nếu writer xử lý và không còn giữ tham chiếu sau commit, chúng là đối tượng ngắn hạn; GC có thể thu hồi hiệu quả.

Ngược lại:

```java
private final List<ProcessedRow> allRows = new ArrayList<>();

public void write(Chunk<? extends ProcessedRow> chunk) {
    allRows.addAll(chunk.getItems());
}
```

Nếu writer là singleton và danh sách này tồn tại xuyên các execution, dữ liệu có thể bị giữ vô thời hạn, dễ dẫn đến heap tăng và lẫn dữ liệu giữa các job. Với writer thật, hãy ghi xuống nơi lưu trữ đích theo chunk thay vì gom toàn bộ dữ liệu vào RAM.

## 5. Nhận diện các anti-pattern cấp phát trong processor

Các lỗi dưới đây không phải lúc nào cũng nghiêm trọng ở job nhỏ, nhưng chi phí nhân lên theo số bản ghi trong job lớn.

### 5.1. Compile regex hoặc tạo formatter trong từng item

Cách gây nhiều object:

```java
public String normalize(String raw) {
    Pattern pattern = Pattern.compile("[^A-Za-z0-9]");
    String sanitized = pattern.matcher(raw).replaceAll("");
    DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("yyyy-MM-dd");
    return sanitized + formatter.format(LocalDate.now());
}
```

Đoạn trên compile lại regex và tạo formatter ở mỗi lời gọi, đồng thời dùng thời gian hiện tại nên kết quả phụ thuộc lúc xử lý.

Một cách tốt hơn nếu biểu thức và format không đổi:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.regex.Pattern;

public final class OrderNormalizer {

    private static final Pattern UNSAFE_CHARS =
        Pattern.compile("[^A-Za-z0-9]");

    private static final DateTimeFormatter DATE_FORMAT =
        DateTimeFormatter.ISO_LOCAL_DATE;

    public String normalize(String raw, LocalDate businessDate) {
        String code =
            UNSAFE_CHARS.matcher(raw).replaceAll("");

        return code + DATE_FORMAT.format(businessDate);
    }
}
```

`Pattern` đã compile và `DateTimeFormatter` là các đối tượng bất biến có thể tái sử dụng qua nhiều thread. `Matcher` mang state và không an toàn khi chia sẻ giữa các thread; tạo Matcher theo lời gọi là phù hợp.

Nếu nghiệp vụ không cần regex, một vòng quét ký tự hoặc parser chuyên biệt có thể rẻ hơn, nhưng chỉ nên thay thế sau khi profiling chỉ ra đây là điểm nóng.

### 5.2. Tạo ObjectMapper hoặc JSON parser mỗi lần xử lý

Không tối ưu:

```java
public Customer parseCustomer(String json) throws Exception {
    ObjectMapper mapper = new ObjectMapper();
    return mapper.readValue(json, Customer.class);
}
```

Nếu cấu hình cố định, nên tạo `ObjectMapper` một lần dưới dạng bean Spring, hoàn tất cấu hình trước khi sử dụng và tái sử dụng trong processor:

```java
@Component
public class CustomerProcessor
        implements ItemProcessor<String, Customer> {

    private final ObjectMapper mapper;

    public CustomerProcessor(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public Customer process(String item) throws Exception {
        return mapper.readValue(item, Customer.class);
    }
}
```

Có thể sử dụng streaming API cho tài liệu JSON lớn thay vì tải cả cây JSON vào bộ nhớ. Tuy nhiên, không nên tự động thay mọi DTO bằng streaming parser: mức phức tạp phải tương xứng với lợi ích đo được.

### 5.3. Dùng String.format và logging cho mọi item

Ví dụ:

```java
log.info(
    "Processed order {} with amount {}",
    item.id(),
    item.amount()
);
```

Ở mức hàng triệu item, việc xuất hàng triệu dòng log có thể tốn nhiều CPU, I/O và bộ nhớ hơn chi phí xử lý nghiệp vụ. Ưu tiên metric/tổng số đếm theo chunk hoặc step và log item lỗi có chọn lọc. Dùng placeholder của SLF4J cho những log cần thiết; tránh `String.format(...)` hoặc nối chuỗi đắt tiền trước khi biết level log có bật hay không.

Nếu bắt buộc ghi nhiều log chi tiết, cần đánh giá throughput của logging backend và các queue bất đồng bộ. Queue log không giới hạn cũng có thể tạo áp lực heap.

### 5.4. Copy nhiều collection và tạo wrapper không cần thiết

Ví dụ:

```java
List<Order> copy = new ArrayList<>(items);
List<Order> another = new ArrayList<>(copy);
List<Order> result = another.stream().filter(this::valid).toList();
```

Một pipeline stream không mặc định chậm, nhưng nhiều danh sách trung gian có thể tạo allocation đáng kể nếu dùng cho từng chunk. Khi profiling cho thấy vấn đề, có thể gộp thành một lần duyệt và một collection kết quả có kích thước phù hợp. Giữ tính đúng đắn, thứ tự dữ liệu và điều kiện lọc khi thay đổi.

**Không tối ưu bằng cách tái sử dụng một DTO mutable duy nhất cho mọi item.** Khi chunk giữ tham chiếu tới nhiều item, tất cả vị trí có thể trỏ tới cùng một object đã bị thay đổi bởi lần đọc sau. Điều này dẫn đến ghi sai dữ liệu khó phát hiện. Trước hết bảo đảm mỗi item mang giá trị độc lập và thread-safe; sau đó mới tối ưu allocation an toàn.

## 6. Ví dụ một ItemProcessor giảm cấp phát không cần thiết

Giả sử nguồn CSV cho biết mã giao dịch, số tiền và ngày giao dịch. Processor cần chuẩn hóa mã, kiểm tra tiền và parse ngày. Không bắt buộc giảm về “0 allocation”; mục tiêu là chỉ tạo những object phục vụ kết quả.

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

import org.springframework.batch.item.ItemProcessor;
import org.springframework.stereotype.Component;

record RawPayment(
    String paymentId,
    String amountText,
    String businessDateText
) {}

record AcceptedPayment(
    String paymentId,
    BigDecimal amount,
    LocalDate businessDate
) {}

@Component
public class PaymentProcessor
        implements ItemProcessor<RawPayment, AcceptedPayment> {

    private static final DateTimeFormatter DATE_FORMATTER =
        DateTimeFormatter.ISO_LOCAL_DATE;

    private static final BigDecimal ZERO = BigDecimal.ZERO;

    @Override
    public AcceptedPayment process(RawPayment item) {
        // Không tạo formatter mới cho mỗi item.
        String paymentId = item.paymentId().trim();
        BigDecimal amount =
            new BigDecimal(item.amountText().trim());

        // Parsing tạo kết quả cần cho dữ liệu nghiệp vụ.
        LocalDate date =
            LocalDate.parse(item.businessDateText(), DATE_FORMATTER);

        if (paymentId.isEmpty() || amount.compareTo(ZERO) <= 0) {
            return null; // Filter theo chính sách của ví dụ.
        }

        return new AcceptedPayment(paymentId, amount, date);
    }
}
```

Giải thích:

- `DateTimeFormatter` được tái sử dụng; `BigDecimal.ZERO` được tái sử dụng.
- `AcceptedPayment` mới là đối tượng đầu ra độc lập; không tái sử dụng một record mutable cho nhiều item.
- `trim()` có thể trả lại chính chuỗi cũ nếu không có ký tự cần loại bỏ, tùy triển khai JDK; không cần tạo thêm bản sao thủ công.
- `new BigDecimal(...)` và `LocalDate.parse(...)` vẫn cần tạo giá trị nghiệp vụ tương ứng. Loại bỏ chúng chỉ để giảm allocation có thể làm giảm tính đúng đắn.
- Nếu chuỗi số tiền/ngày không hợp lệ, processor có thể ném exception. Cần cấu hình skip/retry theo chính sách nghiệp vụ riêng, không mặc định cho mọi lỗi parse là lỗi tạm thời.
- Việc trả về `null` từ processor có nghĩa item được filter; nó không làm tăng skip count.

Trên thực tế, trước khi chỉnh processor, hãy đo xem bottleneck nằm ở parsing, cơ sở dữ liệu hay mạng. Nếu 90% thời gian job dành chờ database, giảm vài object của processor có thể không tạo ra cải thiện đáng kể.

## 7. Chunk size, page size và bộ nhớ

Trong chunk-oriented processing, Spring Batch gom một số item và gọi writer trong phạm vi transaction. Cấu hình ví dụ:

```java
Step step = new StepBuilder("paymentStep", jobRepository)
    .<RawPayment, AcceptedPayment>chunk(200, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .build();
```

**Chunk size** tác động tới:

- Số item/output object tồn tại đồng thời trước khi writer hoàn tất.
- Số lần gọi writer và số transaction/commit.
- Phạm vi rollback nếu lỗi xuất hiện.
- Kích thước buffer và áp lực bộ nhớ tại reader/writer.
- Thời gian một transaction giữ tài nguyên và khóa.

Giả sử một item đã xử lý cùng các đối tượng liên quan chiếm trung bình 4 KB heap trong thời điểm chunk giữ nó. Khi tăng chunk size từ 100 lên 2.000, **chỉ riêng phần item nằm trong một chunk** có thể tăng từ khoảng 400 KB lên 8 MB. Đây là phép tính minh họa, chưa kể input, buffer writer, session persistence, database driver và nhiều chunk đang chạy đồng thời.

Công thức gần đúng để định hướng:

```text
Working-set ≈
    số chunk đang hoạt động ×
    số item / chunk ×
    bytes retained / item
  + reader/page buffer
  + writer/driver buffers
  + state, cache, framework và các overhead khác
```

Không nên dùng công thức này để quyết định chính xác `-Xmx` vì footprint thực tế phụ thuộc object graph, bố trí heap, collector, concurrency và thời điểm GC. Nó giúp nhìn thấy xu hướng: chunk lớn và nhiều worker có thể cùng nhân áp lực bộ nhớ.

### Chunk size nhỏ hay lớn?

| Chunk nhỏ | Chunk lớn |
| --- | --- |
| Ít item cùng tồn tại trong chunk | Ít lần commit hơn |
| Dễ giữ đỉnh heap thấp | Có thể tăng hiệu quả batch write |
| Nhiều lần commit/gọi writer | Có thể kéo dài transaction và giữ object lâu |
| Overhead transaction có thể tăng | Khi rollback, lượng công việc có thể phải xử lý lại lớn hơn |

Không có một chunk size tốt cho mọi job. Nên thử nhiều cấu hình như 50, 200, 500, 1.000 với cùng dữ liệu, cùng tài nguyên, đo cả throughput lẫn heap/GC và bảo toàn kết quả nghiệp vụ.

Ngoài chunk size, `JdbcPagingItemReader` có **page size**, JDBC driver có **fetch size**, và writer có thể có **batch size**. Chúng là những khái niệm khác nhau. Cấu hình phối hợp hợp lý có thể giảm số lần I/O mà vẫn kiểm soát footprint.

## 8. Reader: đừng giữ toàn bộ dữ liệu trong heap

### 8.1. Danh sách trong bộ nhớ

Cách này phù hợp với test dữ liệu nhỏ:

```java
List<Order> allOrders = repository.findAll();
ItemReader<Order> reader = new ListItemReader<>(allOrders);
```

Với bảng hàng triệu dòng, `findAll()` có thể khiến application tạo và giữ toàn bộ entity cùng collection trước khi Batch bắt đầu xử lý. Đây thường là vấn đề **retained heap** nghiêm trọng hơn chi phí cấp phát object tạm.

### 8.2. Cursor/paging reader

Các reader thông dụng cho dữ liệu lớn:

- `JdbcCursorItemReader`: đọc qua JDBC ResultSet/cursor; cần quản lý kết nối, fetch size, transaction và khả năng restart.
- `JdbcPagingItemReader`: đọc theo trang; cần sort key ổn định và duy nhất để tránh thiếu/lặp bản ghi khi paging.
- `JpaPagingItemReader`: đọc bằng JPA theo trang; quan tâm lifecycle của entity và persistence context theo cấu hình.
- `FlatFileItemReader`: đọc file theo dòng và ánh xạ từng record, không cần nạp toàn bộ file vào list.
- Reader tự viết: nên tuân thủ hợp đồng `ItemReader.read()` trả `null` khi hết dữ liệu; quản lý tài nguyên bằng `ItemStream` nếu cần.

Với JDBC, `fetchSize` là một gợi ý tới driver; hành vi thực tế khác nhau theo database/driver và chế độ truy vấn. Không nên mặc định đặt fetch size lớn nhất vì còn phải xét heap và connection lifecycle.

### 8.3. JPA và persistence context

Nếu processor/writer dùng EntityManager và giữ các entity managed qua nhiều trang/chunk, persistence context có thể tăng cùng số entity được tham chiếu. Tùy reader và transaction configuration, cần quản lý `clear()`/detach phù hợp để không giữ những entity không còn cần thiết. Đừng gọi `clear()` bừa bãi giữa lúc còn các thay đổi chưa flush/commit, vì có thể làm mất dữ liệu cần ghi.

Trường hợp này cần xem cả **heap retained** và **transaction correctness**: không đánh đổi dữ liệu đúng để giảm memory usage.

## 9. Writer: batch write và tránh tích lũy output

Writer thường là nơi phát sinh nhiều object trung gian: SQL parameter maps, mảng binds, JSON payload, byte buffers hoặc object mô hình persistence.

Nếu ghi qua JDBC, cân nhắc `JdbcBatchItemWriter` để tận dụng batch operations:

```java
@Bean
JdbcBatchItemWriter<AcceptedPayment> paymentWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<AcceptedPayment>()
        .dataSource(dataSource)
        .sql("""
             INSERT INTO accepted_payment (
                 payment_id, amount, business_date
             ) VALUES (
                 :paymentId, :amount, :businessDate
             )
             """)
        .beanMapped()
        .build();
}
```

Ví dụ giả định bảng đích tồn tại và mỗi `AcceptedPayment` có getter/property được Spring nhận diện. Trong code thực tế, các Java record có thể cần cách mapping phù hợp với property accessor của phiên bản thư viện; có thể thay bằng DTO bean hoặc dùng `itemSqlParameterSourceProvider` chủ động. Yêu cầu nghiệp vụ về khóa chính, xử lý trùng và transaction vẫn phải được thiết kế.

Việc batch ghi giảm số round trip tới database trong nhiều trường hợp, nhưng không đồng nghĩa giảm mọi object allocation. Cần đo tổng thể throughput, memory và thời gian I/O.

**Tránh writer giữ tất cả output trong một danh sách rồi mới ghi cuối job**, trừ khi tập dữ liệu thực sự nhỏ và nghiệp vụ cần tính toán toàn bộ. Cũng tránh buffer HTTP/JSON không giới hạn khi gộp dữ liệu thành một request khổng lồ.

Nếu writer gửi dữ liệu ra hệ thống ngoài transaction database, hãy có idempotency key hoặc outbox thích hợp; retry/restart có thể thực hiện lại tác động đã xảy ra.

## 10. ExecutionContext và các trạng thái được giữ lâu

`ExecutionContext` là nơi Spring Batch lưu state cần cho restart, chẳng hạn vị trí reader, bộ đếm checkpoint hoặc một mã trạng thái nhỏ. Nó không phải kho lưu toàn bộ input/output.

Không nên:

```java
executionContext.put("allProcessedRows", allRows);
```

Nếu `allRows` chứa hàng triệu DTO, heap có thể giữ cả object graph rất lâu; ngoài ra việc serialize state vào metadata repository khiến việc lưu execution context tốn thời gian và có thể gây lỗi.

Nên lưu thông tin gọn:

```java
executionContext.putLong("lastCommittedOrderId", lastId);
executionContext.putString("sourceFileKey", sourceFileKey);
```

Lưu ý checkpoint phải phù hợp cơ chế reader, transaction và chính sách restart. Chỉ lưu `lastId` là chưa đủ nếu thứ tự xử lý không ổn định hoặc dữ liệu nguồn thay đổi trong lúc job chạy. Với reader chuẩn của Spring Batch, ưu tiên dùng chức năng state/restart có sẵn trước khi tự thiết kế checkpoint.

Những đối tượng lưu trong field của singleton component như cache, map, listener hay writer cũng là nguồn retained heap. Nếu không có yêu cầu chia sẻ state, hãy dùng thiết kế stateless; state riêng của một execution có thể đặt trong scope phù hợp và được giải phóng khi execution hoàn tất.

## 11. Partitioning và multithreading có thể nhân áp lực bộ nhớ

Parallel processing giúp tăng throughput nếu hệ thống chưa bị nghẽn CPU hoặc I/O, nhưng không miễn phí:

```text
               Manager step
              /     |       \
        Worker 1  Worker 2  Worker 3
          chunk     chunk     chunk
           N         N         N
              \      |       /
                Writer(s)
```

Nếu có 8 worker, mỗi worker giữ một chunk 500 item cùng buffer liên quan, lượng dữ liệu tồn tại đồng thời có thể lớn hơn đáng kể so với một worker. Ngoài ra còn có thread stack, queue công việc, kết nối database, deserialization buffer, state và các object của executor.

Các rủi ro gồm:

- Reader/writer không thread-safe bị dùng đồng thời.
- Queue không giới hạn giữ các task hoặc item chưa được xử lý.
- Database connection pool không đủ cho số worker.
- Allocation rate tăng nhanh nhưng CPU dành cho GC cũng tăng, khiến throughput không tăng tương ứng.
- Lỗi/rollback khó dự đoán hơn khi nhiều partition cùng ghi một bảng hoặc một file.

Tối ưu nên tăng concurrency từng bước và đo **items/s, CPU, GC time, heap peak, database latency** cùng kết quả nghiệp vụ. Số thread lớn không đồng nghĩa job nhanh hơn.

## 12. Quan sát GC bằng unified logging của JVM

Từ JDK 9, JVM HotSpot hỗ trợ unified logging với cú pháp `-Xlog`. Khi điều tra performance, có thể bật GC log theo chu kỳ xử lý.

Ví dụ Java 17:

```bash
java \
  -Xms512m \
  -Xmx2g \
  -Xlog:gc*,safepoint:file=/var/log/batch/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar batch-app.jar
```

Đây là lệnh minh họa cho môi trường Unix/container. Đường dẫn log phải tồn tại và process cần quyền ghi. Trên Windows hoặc nền tảng triển khai khác, thay đường dẫn theo hệ thống tệp tương ứng. Cấu hình logging chỉ nên được bật với mức chi tiết phù hợp để tránh log chiếm quá nhiều đĩa hoặc ảnh hưởng performance.

Trong GC log, cần quan tâm:

- **Tần suất GC:** trong một phút job có bao nhiêu sự kiện GC?
- **Pause duration:** mỗi lần GC khiến application bị dừng bao lâu?
- **Heap trước/sau GC:** bộ nhớ sau thu gom có trở lại mức ổn định không?
- **Old generation pressure:** dữ liệu sống lâu có tiếp tục tăng không?
- **Full GC / evacuation failure / allocation failure:** có dấu hiệu pressure nghiêm trọng không?
- **Thời gian GC so với wall-clock:** phần thời gian xử lý bị chi phối bởi việc thu gom là bao nhiêu?

Một trích đoạn dạng minh họa:

```text
[12.345s][info][gc] GC(15) Pause Young (Normal) (G1 Evacuation Pause) 850M->310M(2048M) 18.2ms
[13.102s][info][gc] GC(16) Pause Young (Normal) (G1 Evacuation Pause) 860M->315M(2048M) 17.4ms
```

Dòng log cho thấy một chu kỳ giảm heap từ khoảng 850 MB còn 310 MB và có pause khoảng 18 ms. Tuy nhiên, chỉ hai dòng không đủ kết luận job tốt hay xấu. Cần đối chiếu xuyên nhiều phút và với throughput của Spring Batch.

**GC log không chỉ ra đầy đủ object allocation đến từ dòng code nào.** Muốn biết những class/method tạo nhiều object, dùng JFR hoặc allocation profiler.

## 13. Java Flight Recorder (JFR) để tìm điểm nóng allocation

JFR là công cụ profiling nằm trong JVM, hỗ trợ thu thập sự kiện GC, CPU và allocation với overhead có thể kiểm soát tùy cấu hình. Khi dùng, ưu tiên capture trong một khoảng thời gian đại diện.

Một cách bật JFR khi khởi động:

```bash
java \
  -XX:StartFlightRecording=filename=/tmp/batch-profile.jfr,settings=profile,dumponexit=true \
  -jar batch-app.jar
```

Hoặc yêu cầu JVM đang chạy ghi trong 120 giây bằng `jcmd`:

```bash
jcmd <pid> JFR.start name=batch-sample settings=profile duration=120s filename=/tmp/batch-profile.jfr
```

Sau đó mở file bằng **JDK Mission Control (JMC)** và xem các nhóm sự kiện liên quan tới:

| Nhóm quan sát | Câu hỏi |
| --- | --- |
| Object allocation samples | Class nào được cấp phát nhiều nhất? Stack trace nào tạo object? |
| GC events | Thời gian/tần suất thu gom có tương ứng thời điểm chậm không? |
| CPU profiling | CPU nằm ở parser, mapper, converter, JDBC, GC hay logging? |
| Thread activity | Thread chờ I/O, lock hay chạy CPU? |
| Heap/object statistics khi được bật | Những object nào còn được giữ lâu? |

Không phải mọi sự kiện allocation đều được ghi đầy đủ ở mặc định; JFR thường dùng sampling để giảm overhead. Vì vậy **số sample không phải số object cấp phát chính xác**. Hãy xem tỷ lệ, stack trace nổi bật và so sánh trong cùng cấu hình thu thập.

Ví dụ profiling cho thấy nhiều allocation đến từ `Pattern.compile` trong `PaymentProcessor.process()`. Khi đó tối ưu bằng cách tái sử dụng `Pattern` có cơ sở đo lường. Nếu phần lớn allocation đến từ driver hoặc JSON parser, hướng điều tra nên khác.

Các công cụ bổ sung như async-profiler có thể tạo **allocation flame graph** để thấy call stack chiếm nhiều allocation. Heap dump và class histogram hữu ích khi nghi ngờ retained object, nhưng có thể gây pause/chiếm bộ nhớ và chứa dữ liệu nhạy cảm; phải chọn thời điểm thu thập phù hợp.

## 14. Dùng Spring Batch metadata để đối chiếu GC và throughput

Không nên tối ưu JVM riêng lẻ. Phải đặt số liệu GC cạnh số liệu xử lý thực của Spring Batch.

Các trường từ `StepExecution`:

- `getReadCount()`: số item đã được reader đọc thành công theo metadata.
- `getWriteCount()`: số item được writer ghi nhận.
- `getFilterCount()`: item processor trả về `null`.
- `getReadSkipCount()`, `getProcessSkipCount()`, `getWriteSkipCount()`: số lỗi được skip.
- `getCommitCount()`, `getRollbackCount()`: thông tin giao dịch.
- Thời gian bắt đầu/kết thúc execution dùng tính tổng duration.

Một `StepExecutionListener` có thể ghi metric/tổng kết:

```java
import java.time.Duration;
import java.time.LocalDateTime;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class BatchPerformanceListener
        implements StepExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(BatchPerformanceListener.class);

    @Override
    public ExitStatus afterStep(StepExecution step) {
        LocalDateTime started = step.getStartTime();
        LocalDateTime ended = step.getEndTime();

        Long elapsedMs = null;
        Double itemsPerSecond = null;

        if (started != null && ended != null) {
            long ms = Duration.between(started, ended).toMillis();
            elapsedMs = ms;

            if (ms > 0) {
                itemsPerSecond =
                    step.getReadCount() * 1000.0 / ms;
            }
        }

        log.info(
            "event=batch.step.performance " +
            "jobExecutionId={} step={} status={} " +
            "readCount={} writeCount={} filterCount={} " +
            "skipCount={} rollbackCount={} elapsedMs={} " +
            "itemsPerSecond={}",
            step.getJobExecutionId(),
            step.getStepName(),
            step.getStatus(),
            step.getReadCount(),
            step.getWriteCount(),
            step.getFilterCount(),
            step.getSkipCount(),
            step.getRollbackCount(),
            elapsedMs,
            itemsPerSecond
        );

        return null; // Giữ nguyên ExitStatus của step.
    }
}
```

Ví dụ tính `itemsPerSecond` dựa trên số item đọc theo metadata, không phải số lần reader được gọi vật lý. Với skip, retry và rollback, hai đại lượng này có thể khác nhau. Nên nêu rõ metric đang đo **số item đọc được / thời gian StepExecution**, không nhầm với tốc độ xử lý item duy nhất của nghiệp vụ.

Khi so sánh hai lần chạy, lấy thêm:

- CPU sử dụng trong khoảng job chạy.
- Allocation rate theo profiling hoặc metric JVM.
- Tổng thời gian GC/pause distribution.
- Heap dùng sau GC và đỉnh heap.
- Thời gian query SQL, thời gian batch write, số lần gọi API.
- Khối lượng input và output thực tế; số skipped/filtered.

Nếu throughput giảm trong khi GC time tăng, đây là hướng điều tra hợp lý. Nếu GC ổn nhưng database query chậm, tăng heap có thể không tạo ra lợi ích.

## 15. Heap tuning và lựa chọn collector

Một số tham số JVM thường gặp:

| Tuỳ chọn | Tác dụng | Lưu ý |
| --- | --- | --- |
| `-Xms` | Heap size ban đầu | Không tự động giải quyết allocation rate |
| `-Xmx` | Giới hạn heap tối đa | Phải vừa với tổng memory limit và native overhead |
| `-XX:MaxRAMPercentage` | Tỷ lệ RAM dùng làm cơ sở chọn max heap khi không đặt `-Xmx` | Hành vi phụ thuộc JVM/cấu hình container |
| `-XX:+UseG1GC` | Chọn G1 GC | Phù hợp nhiều batch workload; cần đo thực tế |
| `-XX:MaxGCPauseMillis=...` | Mục tiêu pause cho collector hỗ trợ | Là **gợi ý**, không phải cam kết pause tối đa |
| `-XX:+UseZGC` | Chọn ZGC trên JDK hỗ trợ | Hướng đến pause thấp; có đánh đổi CPU, throughput và memory |

Một cách cấu hình heap cố định:

```bash
java -Xms512m -Xmx2g -jar batch-app.jar
```

Trong container có memory limit, **-Xmx không phải toàn bộ memory mà process tiêu thụ**. JVM còn dùng metaspace, thread stacks, code cache, direct buffers, native memory của driver/thư viện và phần nhớ của GC. Ví dụ nếu container bị giới hạn 2 GB, đặt `-Xmx2g` có thể khiến process vượt tổng giới hạn và bị kill khi cộng các vùng ngoài heap.

Tăng `-Xmx` có thể làm giảm tần suất GC nhưng làm tăng footprint hoặc thay đổi độ trễ. Không dùng tăng heap như biện pháp duy nhất khi nguyên nhân là giữ hàng triệu object trong danh sách. Collector hoặc pause target nên được chỉnh **sau khi** có số liệu về allocation, live set, GC pause, CPU và throughput.

**Không gọi `System.gc()` bên trong processor hay mỗi chunk để “dọn rác”.** Đây không phải cách quản lý vòng đời object, có thể làm giảm hiệu năng và không giải quyết tham chiếu bị giữ lâu.

## 16. Quy trình đo trước và sau tối ưu

Một thử nghiệm thực tế nên giữ nguyên input, database, job configuration và tài nguyên hệ thống giữa các lần chạy.

### Bước 1: Đặt mục tiêu đo được

Ví dụ:

> Batch nhập 2 triệu dòng cần hoàn tất trong dưới 8 phút, chạy trên container 4 vCPU/4 GB RAM, không OOM, dữ liệu đầu ra chính xác và GC không chiếm quá nhiều thời gian xử lý.

Ngưỡng GC cụ thể cần được xác định từ SLA và phép đo, không có một giá trị “tốt” áp dụng cho mọi hệ thống.

### Bước 2: Chạy baseline

Ghi lại:

| Chỉ số | Baseline minh họa |
| --- | ---: |
| Input | 2.000.000 item |
| Tổng thời gian | 640 giây |
| Throughput | 3.125 item/giây |
| Peak heap | 2,6 GB |
| Allocation rate | 180 MB/giây |
| Tổng thời gian GC | 75 giây |
| GC pause cao nhất | 210 ms |
| Kết quả đầu ra | 2.000.000 item hợp lệ |

Các số trên là **giả lập để mô tả cách đọc báo cáo**, không phải benchmark của Spring Batch.

### Bước 3: Tìm điểm nóng

Mở JFR và xem allocation stack, GC events, CPU profiling. Giả sử allocation nổi bật đến từ việc compile regex ở processor và một cache giữ tất cả output trong writer. Hai vấn đề cần giải quyết khác nhau: cache gây retained heap; compile regex gây chi phí cấp phát và CPU lặp lại.

### Bước 4: Thay đổi một nhóm nguyên nhân

Ví dụ:

- Compile regex một lần và tái sử dụng.
- Ghi dữ liệu theo chunk, loại bỏ bộ nhớ giữ toàn bộ output.
- Điều chỉnh chunk size từ 500 về 200 nếu phép đo cho thấy đỉnh heap quá lớn.
- Không sửa đồng thời thuật toán nghiệp vụ, tính toán tiền và quy tắc skip nếu không cần thiết.

### Bước 5: Đo lại và so sánh

| Chỉ số | Baseline giả lập | Sau thay đổi giả lập |
| --- | ---: | ---: |
| Input | 2.000.000 | 2.000.000 |
| Tổng thời gian | 640 s | 440 s |
| Throughput | 3.125 item/s | 4.545 item/s |
| Peak heap | 2,6 GB | 1,3 GB |
| Allocation rate | 180 MB/s | 95 MB/s |
| Tổng thời gian GC | 75 s | 21 s |
| Đầu ra hợp lệ | 2.000.000 | 2.000.000 |

Cần chạy nhiều lần để giảm ảnh hưởng của warm-up JIT, cache database, CPU contention và nhiễu từ môi trường. Với job I/O, luôn kiểm tra tải của database và hệ thống ngoài. Một thay đổi chỉ được xem là cải thiện nếu **kết quả nghiệp vụ vẫn chính xác**, không mất item, không nhân đôi và không làm hỏng khả năng restart.

## 17. Những vấn đề thường gặp và cách phân tích

| Triệu chứng | Khả năng nguyên nhân | Hướng điều tra |
| --- | --- | --- |
| GC rất thường xuyên, heap sau GC ổn định | Nhiều object ngắn hạn | JFR allocation stack; kiểm tra parser, regex, DTO, log |
| Heap sau GC tăng theo số record | Object bị giữ quá lâu | Heap dump/dominator tree; kiểm tra list, cache, context |
| OOM khi tăng chunk size | Working set của chunk và buffers tăng | Giảm chunk, đo live set và writer buffers |
| OOM khi tăng thread count | Nhiều chunk/page/queue cùng tồn tại | Giảm concurrency, giới hạn queue, kiểm tra connection pool |
| Batch chậm nhưng GC ít | Bottleneck có thể ở DB, I/O hoặc lock | CPU profile, JDBC tracing, I/O latency |
| Nhiều pause dài | Heap pressure, retained objects hoặc collector config | GC logs/JFR; xem Old GC, live set, chọn GC phù hợp |
| Heap ổn nhưng container vẫn bị kill | Native memory/direct buffer/thread stacks/giới hạn container | Theo dõi RSS, native memory và cgroup limits |
| Reader giữ hàng triệu entity | Dùng `findAll()` hoặc persistence context tích lũy | Streaming/paging, quản lý EntityManager |
| Writer tăng heap theo thời gian | Gom output toàn job hoặc cache không giới hạn | Batch write theo chunk, giới hạn cache |
| Job chạy nhanh sau khi restart nhưng chậm lần đầu | JIT warm-up, cache, I/O, dữ liệu khác nhau | Đo trên input tương đương, lặp nhiều lần |
| Log quá nhiều khiến heap/CPU tăng | Log item ở INFO, async queue lớn | Aggregate log, sampling, giới hạn queue |
| Thay object allocation làm dữ liệu sai | Reuse mutable DTO hoặc buffer không an toàn | Kiểm tra độc lập item, thread safety, rollback |
| Có nhiều retry nên object tăng | Parse/serialize lại item, giữ exception stack traces | Profile fault-tolerant paths, so sánh theo retry count |

## 18. Bài tập thực hành

Tạo job `importPaymentsJob` đọc dữ liệu CSV hoặc bảng H2, xử lý 200.000 bản ghi hợp lệ, sau đó ghi bảng đích. Sử dụng chunk-oriented step và `StepExecutionListener` để thu thập duration, read/write/filter/skip counts. Tạo dữ liệu có số lượng và độ dài chuỗi ổn định để so sánh được các lượt chạy.

Thực hiện ba phiên bản processor:

1. Processor tạo regex và formatter trong mỗi item.
2. Processor tái sử dụng `Pattern`, `DateTimeFormatter` và không tạo collection trung gian không cần thiết.
3. Processor giống phiên bản 2 nhưng writer cố tình gom toàn bộ output trong bộ nhớ test để quan sát dấu hiệu retained heap. Chỉ dùng phiên bản này trong môi trường test, với dữ liệu có giới hạn để tránh làm gián đoạn máy chạy.

Bật GC log/JFR, đo throughput, allocation rate, heap sau GC và tổng thời gian GC. Thử chunk size 50, 200 và 1.000; nếu chạy nhiều worker, đo riêng tác động của concurrency. Cuối cùng xác minh số item ghi trong database, nội dung kết quả và khả năng restart sau khi cố ý gây lỗi một chunk.

Khi trình bày kết quả, phân biệt thay đổi làm giảm **allocation rate** với thay đổi làm giảm **retained heap**. Giải thích vì sao giảm allocation chưa chắc giảm wall-clock nếu job đang bị nghẽn I/O, hoặc tăng heap chưa chắc giải quyết một collection cứ lớn dần.

## 19. Kết luận

Trong Spring Batch, object allocation là chi phí tự nhiên của việc đọc, biến đổi và ghi từng item; GC giúp JVM tái sử dụng heap, nhưng có thể tiêu tốn CPU hoặc tạo pause khi allocation và live set vượt khả năng xử lý hiệu quả. Tối ưu tốt bắt đầu bằng việc **đo đúng vấn đề**: GC log cho biết tình trạng thu gom, JFR và allocation profiler chỉ ra nơi tạo object, còn metadata `StepExecution` cho biết job thực sự xử lý bao nhiêu dữ liệu và mất bao lâu.

Những thay đổi có giá trị thường gồm streaming/paging thay vì giữ tất cả input, không tích lũy output trong writer, hạn chế state trong `ExecutionContext`, tái sử dụng đối tượng cấu hình bất biến và điều chỉnh chunk size/concurrency theo số liệu. Luôn bảo toàn tính đúng đắn của dữ liệu, transaction và restart khi giảm allocation. Mục tiêu cuối cùng là **throughput ổn định, memory có giới hạn và job hoàn tất đúng SLA**.
