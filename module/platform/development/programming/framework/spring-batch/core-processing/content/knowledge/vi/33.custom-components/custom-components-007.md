# Xử lý null và end of input

Trong Spring Batch, `null` có ý nghĩa đặc biệt ở ranh giới của `ItemReader`: khi `read()` trả về `null`, framework hiểu rằng reader đã hết dữ liệu và không còn item tiếp theo trong lần thực thi đó. Vì vậy, một custom reader không được dùng `null` để biểu diễn một bản ghi hợp lệ nhưng rỗng, một trường dữ liệu bị thiếu hoặc một nguồn tạm thời chưa có dữ liệu.

Ở một vị trí khác, `ItemProcessor` có thể trả về `null` để yêu cầu Spring Batch lọc bỏ item. Đây là hành vi filter, không phải end of input và cũng không phải skip do exception. Hiểu đúng các ý nghĩa này giúp tránh job kết thúc sớm, mất bản ghi hoặc báo cáo counter sai.

## 1. Hợp đồng của ItemReader.read()

`ItemReader<T>` có một phương thức chính:

```java
public interface ItemReader<T> {
    T read() throws Exception;
}
```

Hợp đồng của phương thức:

- Trả về một item khi còn dữ liệu.
- Trả về `null` khi không còn item nào để đọc.
- Ném exception khi xảy ra lỗi đọc, parse hoặc lỗi nguồn dữ liệu cần được xử lý.

Spring Batch gọi `read()` lặp lại cho đến khi nhận `null`. Khi đó reader được xem là đã đạt end of input (EOF) và step bắt đầu kết thúc phần đọc. Nếu reader trả `null` giữa file chỉ vì gặp một dòng rỗng hoặc một record không hợp lệ, các record sau đó có thể không bao giờ được xử lý.

Ví dụ một reader đơn giản:

```java
public class CustomerReader implements ItemReader<Customer> {

    private final Iterator<Customer> customers;

    public CustomerReader(List<Customer> customers) {
        this.customers = customers.iterator();
    }

    @Override
    public Customer read() {
        if (!customers.hasNext()) {
            return null; // Không còn item: end of input.
        }
        return customers.next();
    }
}
```

Reader chỉ trả `null` khi iterator không còn phần tử. Mỗi phần tử hợp lệ phải là một object khác `null`.

## 2. Ba ý nghĩa khác nhau của null

Trong một pipeline batch, cần phân biệt ít nhất ba trường hợp:

| Vị trí | Ý nghĩa của `null` | Hành vi của Spring Batch |
|---|---|---|
| `ItemReader.read()` | Không còn item tiếp theo. | Kết thúc quá trình đọc của step. |
| `ItemProcessor.process(item)` | Không muốn giữ item này trong output. | Lọc item; item không được chuyển cho writer. |
| Field bên trong domain object | Dữ liệu của một thuộc tính không có giá trị. | Vẫn là một item bình thường; processor/validator quyết định cách xử lý. |

Ví dụ một customer có email không được cung cấp:

```java
Customer customer = new Customer("C001", "Nguyen An", null);
```

Object `customer` vẫn là một item hợp lệ ở ranh giới reader. `email == null` chỉ có nghĩa field email không có giá trị. Reader không được trả `null` thay cho toàn bộ object chỉ vì một field bị thiếu.

Ngược lại, nếu `ItemProcessor` trả `null`, Spring Batch hiểu rằng item đã được lọc bỏ. Đây là một quyết định của pipeline sau khi item đã được đọc thành công.

## 3. Không dùng null để biểu diễn một record rỗng hoặc lỗi

Giả sử file đầu vào có các dòng:

```text
C001,Nguyen An,an@example.com

C002,Tran Binh,binh@example.com
INVALID-LINE
C003,Le Chi,chi@example.com
```

Nếu custom reader viết như sau:

```java
@Override
public Customer read() throws Exception {
    String line = reader.readLine();
    if (line == null || line.isBlank()) {
        return null;
    }
    return parseCustomer(line);
}
```

thì dòng trống đầu tiên khiến reader trả `null`. Spring Batch xem đó là EOF và không gọi `read()` tiếp để lấy `C002` hoặc `C003`.

Nếu một dòng không hợp lệ cũng được chuyển thành `null`, lỗi bị che giấu và toàn bộ phần còn lại của file có thể bị bỏ qua. Đây là lỗi nghiêm trọng vì job có thể kết thúc như thể đã đọc hết nguồn.

Hãy dùng `null` duy nhất cho trường hợp không còn dữ liệu. Với dòng rỗng, record không hợp lệ hoặc field thiếu, cần có chính sách riêng: bỏ qua có chủ đích, tạo item biểu diễn lỗi, hoặc ném exception phù hợp.

## 4. Bỏ qua dòng rỗng trong custom reader

Nếu dòng trống được định nghĩa là dòng không mang dữ liệu và có thể bỏ qua, reader có thể tiếp tục đọc bên trong cùng một lần gọi cho đến khi tìm thấy record hoặc EOF:

```java
public class CustomerCsvReader implements ItemReader<Customer> {

    private final BufferedReader reader;

    public CustomerCsvReader(BufferedReader reader) {
        this.reader = reader;
    }

    @Override
    public Customer read() throws IOException {
        String line;

        while ((line = reader.readLine()) != null) {
            if (line.isBlank()) {
                continue; // Dòng trống không phải EOF.
            }

            return parseCustomer(line);
        }

        return null; // Chỉ EOF mới trả null.
    }

    private Customer parseCustomer(String line) {
        String[] columns = line.split(",", -1);
        return new Customer(columns[0], columns[1], columns[2]);
    }
}
```

Đoạn code minh họa nguyên tắc. Reader thực tế cần validate số cột, xử lý dấu phẩy nằm trong quoted field, encoding và lỗi parse. Nếu file CSV có quy tắc quoting, nên dùng `FlatFileItemReader` với tokenizer/line mapper thích hợp thay vì tự `split`.

Việc bỏ qua dòng trống ở reader không làm tăng `filterCount` hay `skipCount`, vì dòng đó không được trả thành item. Nếu cần thống kê số dòng trống, hãy tăng một counter riêng hoặc ghi nhận qua listener/metric.

## 5. Null trong dữ liệu nguồn khác với end of input

Nguồn dữ liệu có thể biểu diễn “không có giá trị” theo nhiều cách:

- Một cột database có SQL `NULL`.
- Một field JSON có giá trị `null`.
- Một field CSV rỗng.
- Một dòng file chỉ có dấu phân cách hoặc dấu cách.
- Một record có cấu trúc nhưng thiếu field bắt buộc.

Những trường hợp này không tự động có nghĩa là nguồn đã kết thúc.

Ví dụ database:

```java
public Customer mapRow(ResultSet rs, int rowNum) throws SQLException {
    return new Customer(
            rs.getString("customer_id"),
            rs.getString("name"),
            rs.getString("email")); // Có thể null nếu SQL column là NULL.
}
```

`RowMapper` vẫn trả một `Customer` khác `null`; chỉ field `email` có thể null. Nếu `RowMapper` trả `null` cho một row, reader dựa trên cursor có thể xem giá trị đó như tín hiệu EOF theo hợp đồng `ItemReader`, dẫn đến kết thúc đọc sớm. Hãy luôn map một row thành item khác `null`, hoặc xử lý/reject row đó theo cách rõ ràng.

## 6. Xử lý JSON null trong một JSON array

Một JSON array có thể chứa phần tử `null`:

```json
[
  {"customerId":"C001","name":"Nguyen An"},
  null,
  {"customerId":"C003","name":"Le Chi"}
]
```

Đây là một phần tử trong dữ liệu JSON, không phải dấu kết thúc của array. Tuy nhiên, hợp đồng `ItemReader` dành riêng giá trị trả về `null` cho end of input. Nếu object reader deserialize phần tử JSON `null` thành Java `null`, reader không thể dùng giá trị đó như một item thông thường mà không gây nhầm lẫn với EOF.

Trước khi triển khai, hãy xác định quy tắc của nguồn:

- Nếu phần tử `null` là dữ liệu không hợp lệ, từ chối file hoặc phát sinh lỗi parse/validation.
- Nếu phần tử `null` có thể bỏ qua, custom reader có thể tiếp tục tìm object tiếp theo và ghi nhận số phần tử bị loại.
- Nếu cần giữ lại sự kiện “phần tử null” để audit, biểu diễn nó bằng một wrapper khác `null`, chẳng hạn `Optional.empty()` hoặc một record có trạng thái rõ ràng.

Ví dụ dùng wrapper:

```java
ItemReader<Optional<Customer>> reader = ...;

ItemProcessor<Optional<Customer>, Customer> processor = record ->
        record.orElse(null); // Optional.empty() trở thành filter có chủ đích.
```

Ở đây reader phải trả về `Optional.empty()` như một object item khác `null`. Processor sau đó quyết định lọc bỏ bằng cách trả `null`. Nếu cần lưu lý do bị loại, hãy ghi nhận trong processor/listener hoặc dùng một kiểu kết quả có trạng thái thay vì âm thầm filter.

## 7. ItemProcessor trả null nghĩa là filter

`ItemProcessor<I, O>` có thể trả về `null`. Trong Spring Batch, điều đó có nghĩa item đầu vào không được đưa tới writer.

Ví dụ chỉ xuất customer đang hoạt động:

```java
@Bean
ItemProcessor<Customer, Customer> activeCustomerProcessor() {
    return customer -> customer.active() ? customer : null;
}
```

Nếu `active()` là false, processor trả `null`; item bị filter. Step tiếp tục với các item khác.

Một processor có thể thực hiện mapping rồi filter:

```java
@Bean
ItemProcessor<CustomerInput, Customer> customerProcessor() {
    return input -> {
        if (input.status() == CustomerStatus.DELETED) {
            return null;
        }

        return new Customer(
                input.customerId(),
                input.name(),
                input.email());
    };
}
```

Chỉ dùng `null` khi loại item là một quyết định nghiệp vụ bình thường. Không dùng nó để che giấu exception, dữ liệu sai hoặc lỗi không thể xử lý.

## 8. Filter khác với skip

Filter và skip đều có thể khiến một item không đến writer, nhưng nguyên nhân và counter khác nhau.

| Cơ chế | Cách xảy ra | Counter |
|---|---|---|
| Filter | Processor trả `null`. | `filterCount` tăng. |
| Skip | Reader, processor hoặc writer ném exception thuộc skip policy. | `readSkipCount`, `processSkipCount`, `writeSkipCount` và `skipCount` tăng theo giai đoạn. |
| EOF | Reader trả `null` vì hết nguồn. | Kết thúc đọc; không phải filter hoặc skip. |

Ví dụ filter:

```java
return customer.isActive() ? customer : null;
```

Ví dụ skip:

```java
if (customer.customerId() == null) {
    throw new InvalidCustomerException("customerId is required");
}
```

Nếu `InvalidCustomerException` được cấu hình skippable, framework có thể bỏ qua item và gọi `SkipListener`. Filter không phát sinh exception nên không đi qua skip policy.

Không trả `null` từ processor chỉ để tránh phải cấu hình skip. Khi item lỗi cần được ghi nhận như một lỗi dữ liệu, hãy ném exception phù hợp và dùng skip policy/SkipListener hoặc rejected-record store.

## 9. Empty input và end of input

Một file rỗng hoặc một JSON array rỗng có thể là input hợp lệ về mặt cú pháp nhưng không chứa item.

JSON array rỗng:

```json
[]
```

Reader sẽ trả `null` ngay lần đọc đầu tiên. Step có thể hoàn tất với `readCount` bằng 0. Đây là hành vi EOF bình thường, không tự động là lỗi.

Tuy nhiên, yêu cầu nghiệp vụ có thể quy định file phải có ít nhất một record. Khi đó cần kiểm tra riêng:

- Validate file trước khi chạy step.
- Dùng listener kiểm tra `readCount` sau khi step kết thúc và thay đổi kết quả nếu không có item.
- Dùng một tasklet/validation step xác nhận số record tối thiểu.

Không thay đổi ý nghĩa của `null` chỉ để ép empty input thành lỗi. Hãy giữ hợp đồng reader đúng và đặt quy tắc “không được rỗng” ở tầng validation của job.

## 10. Không dùng null cho nguồn tạm thời chưa có dữ liệu

Với file hữu hạn, khi đọc hết file thì trả `null` là đúng. Nhưng một số nguồn không phải tập dữ liệu hữu hạn, ví dụ queue, socket, stream sự kiện hoặc API polling.

Giả sử một queue hiện đang rỗng nhưng sẽ nhận item sau vài giây. Nếu reader gọi `poll()` rồi trả `null` khi queue tạm thời rỗng, Spring Batch hiểu là EOF và kết thúc step. Item đến sau đó sẽ không được đọc.

Không nên viết:

```java
@Override
public Message read() {
    return queue.poll(); // null có thể chỉ có nghĩa queue hiện đang rỗng.
}
```

Với nguồn bất đồng bộ, cần định nghĩa rõ tín hiệu hoàn tất. Một số lựa chọn:

- Chờ/block cho đến khi có item hoặc nhận tín hiệu kết thúc.
- Poll trong một vòng lặp có timeout và phân biệt timeout với trạng thái hoàn tất.
- Dùng sentinel/poison pill để biểu diễn kết thúc stream.
- Dùng mô hình message-driven hoặc integration phù hợp với nguồn dữ liệu thay vì giả lập một file hữu hạn.

Ví dụ dùng sentinel:

```java
public class QueueMessageReader implements ItemReader<Message> {

    private static final Object END_OF_STREAM = new Object();
    private final BlockingQueue<Object> queue;

    public QueueMessageReader(BlockingQueue<Object> queue) {
        this.queue = queue;
    }

    @Override
    public Message read() throws InterruptedException {
        Object next = queue.take(); // Chờ item hoặc sentinel.
        if (next == END_OF_STREAM) {
            return null; // Chỉ sentinel mới kết thúc reader.
        }
        return (Message) next;
    }
}
```

Trong hệ thống nhiều consumer, cần gửi đủ sentinel cho số reader/worker cần kết thúc hoặc có cơ chế điều phối hoàn tất khác. Không dùng một sentinel duy nhất nếu chỉ một worker nhận được nó trong khi các worker khác vẫn chờ.

Nếu dùng `poll(timeout)` và timeout hết, không trả `null` trừ khi timeout thực sự có nghĩa stream đã hoàn tất. Có thể tiếp tục chờ, kiểm tra completion signal hoặc ném exception phù hợp với chính sách retry/poll của ứng dụng.

## 11. Phân loại EOF, lỗi dữ liệu và lỗi nguồn

Một custom reader nên phân biệt ba nhóm kết quả:

| Tình huống | Hành động của reader | Ý nghĩa |
|---|---|---|
| Đã đọc hết nguồn | Trả `null`. | Kết thúc bình thường. |
| Một record không hợp lệ | Ném exception parse/validation hoặc trả một wrapper lỗi theo thiết kế. | Framework/processor áp dụng fail, retry hoặc skip. |
| Lỗi I/O hoặc nguồn tạm thời không khả dụng | Ném exception tương ứng. | Có thể retry nếu lỗi thuộc loại có thể phục hồi; nếu không, step thất bại. |

Không chuyển mọi exception thành `null`:

```java
// Không nên: biến lỗi đọc thành EOF.
try {
    return parseNextRecord();
} catch (Exception exception) {
    log.warn("Cannot read record", exception);
    return null;
}
```

Đoạn code trên có thể khiến step kết thúc thành công dù file vẫn còn dữ liệu hoặc đã bị hỏng. Hãy ném exception để Spring Batch ghi nhận lỗi và áp dụng policy đã cấu hình.

## 12. Ví dụ custom reader phân biệt dòng lỗi và EOF

Một reader có thể đọc từng dòng, bỏ qua dòng trống theo quy tắc, và ném exception khi record không đúng format:

```java
public class StrictCustomerReader implements ItemReader<Customer> {

    private final BufferedReader reader;

    public StrictCustomerReader(BufferedReader reader) {
        this.reader = reader;
    }

    @Override
    public Customer read() throws IOException {
        String line;

        while ((line = reader.readLine()) != null) {
            if (line.isBlank()) {
                continue;
            }

            String[] fields = line.split(",", -1);
            if (fields.length != 3) {
                throw new InvalidCustomerRecordException(
                        "Expected 3 fields but found " + fields.length);
            }

            return new Customer(fields[0], fields[1], fields[2]);
        }

        return null;
    }
}
```

Trong ví dụ:

- Dòng trống được bỏ qua.
- Record có số field sai tạo exception.
- Reader tiếp tục trả từng customer hợp lệ.
- Chỉ khi `readLine()` trả `null` thì reader mới trả `null` cho Spring Batch.

Nếu muốn skip record sai và tiếp tục, có thể để exception đi qua skip policy. Reader phải bảo đảm sau exception nó vẫn ở vị trí có thể đọc record tiếp theo. Với một số nguồn/parser, exception làm mất đồng bộ vị trí đọc; khi đó cần một cách phục hồi riêng hoặc dừng step.

## 13. Xử lý null trong ItemProcessor

Processor có thể nhận một item khác `null` và trả về một output khác `null`, hoặc trả `null` để filter.

Ví dụ chuyển đổi và filter:

```java
@Bean
ItemProcessor<CustomerInput, Customer> customerProcessor() {
    return input -> {
        if (input.status() == null) {
            throw new InvalidCustomerException("status is required");
        }

        if (input.status() == CustomerStatus.ARCHIVED) {
            return null; // Filter có chủ đích.
        }

        return new Customer(
                input.customerId(),
                input.name(),
                input.email());
    };
}
```

Không nên trả `null` khi `status` bị thiếu nếu thiếu status là dữ liệu lỗi cần được xử lý. Trong ví dụ, trạng thái ARCHIVED là điều kiện lọc nghiệp vụ, còn status null là lỗi dữ liệu.

Một processor có thể được thiết kế để lọc nhiều trường hợp. Hãy ghi rõ lý do filter nếu cần audit; chỉ nhìn `filterCount` không biết item nào hoặc vì sao bị loại.

## 14. Null và CompositeItemProcessor

Khi dùng `CompositeItemProcessor`, các delegate được gọi tuần tự. Nếu một delegate trả `null`, pipeline không có item đầu ra để chuyển tiếp; item được filter và các delegate sau không xử lý item đó.

Ví dụ:

```java
CompositeItemProcessor<CustomerInput, Customer> processor =
        new CompositeItemProcessorBuilder<CustomerInput, Customer>()
                .delegates(
                        validateCustomerProcessor,
                        filterArchivedCustomerProcessor,
                        mapCustomerProcessor)
                .build();
```

Nếu `filterArchivedCustomerProcessor` trả `null`, `mapCustomerProcessor` không được gọi cho item đó. Đây là hành vi cần thiết kế có chủ đích.

Không dùng `null` để báo cho delegate tiếp theo rằng “chưa xử lý được”. Nếu cần chuyển trạng thái trung gian, dùng một object wrapper hoặc kết quả có kiểu rõ ràng. Nếu delegate gặp lỗi, ném exception để retry/skip/fail được áp dụng đúng.

## 15. Null trong ItemWriter

Writer nhận một `Chunk` chứa các item đầu ra của pipeline. Trong thiết kế bình thường, chunk không nên chứa item `null`.

Nếu processor trả `null`, item đã bị filter và không được đưa vào chunk cho writer. Nếu custom reader trả `null`, Spring Batch xem đó là EOF, không phải một phần tử null để writer ghi.

Do đó, writer không nên phải đoán `null` nghĩa là gì. Hãy bảo đảm reader chỉ trả item hợp lệ khác `null`, processor chỉ trả object hoặc `null` theo filter semantics, và writer nhận các item đã được chuẩn hóa.

Nếu định dạng output cần biểu diễn JSON `null`, hãy tạo writer/marshaller chuyên biệt hoặc dùng một wrapper biểu diễn null-value rõ ràng. Đừng cố truyền Java `null` như item bình thường qua `ItemReader`.

## 16. Empty chunk sau khi filter

Một chunk có thể đọc được nhiều item nhưng tất cả đều bị processor filter. Khi đó không có item output để ghi. Spring Batch vẫn có thể hoàn tất chunk/step và cập nhật các counter tương ứng; writer thường không có dữ liệu cần ghi.

Ví dụ:

```text
Reader:      A, B, C, D
Processor:   A -> null
             B -> null
             C -> null
             D -> null
Writer:      không có output item
```

Trong trường hợp này:

- `readCount` phản ánh các item reader đã trả.
- `filterCount` phản ánh các item processor đã lọc.
- `writeCount` không tăng cho các item bị filter.
- `skipCount` không tăng chỉ vì processor trả `null`.

Nếu nghiệp vụ không chấp nhận việc tất cả item bị filter, hãy kiểm tra counter sau step hoặc thêm validation. Không nên thay filter bằng `null` từ reader để kết thúc sớm.

## 17. End of input và empty input

Hai khái niệm có liên quan nhưng khác nhau:

- **Empty input:** nguồn không có item ngay từ đầu.
- **End of input:** reader đã đọc hết mọi item của nguồn hiện tại.

Với file rỗng, lần gọi `read()` đầu tiên trả `null`. Với file có 100 item, reader trả 100 item rồi lần gọi tiếp theo mới trả `null`.

Spring Batch không mặc định coi empty input là lỗi. Nếu job cần ít nhất một item, có thể kiểm tra `readCount` sau step:

```java
public class RequireInputListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() == BatchStatus.COMPLETED
                && stepExecution.getReadCount() == 0) {
            return ExitStatus.FAILED.addExitDescription(
                    "Input contained no records");
        }
        return null;
    }
}
```

Đoạn code minh họa việc đặt ExitStatus thất bại khi không có record. Nếu cần thay đổi BatchStatus hoặc điều khiển flow chi tiết, hãy thiết kế transition và listener phù hợp; `ExitStatus` và `BatchStatus` là hai khái niệm riêng.

Một cách khác là có step validate input trước khi xử lý. Cách đó phù hợp khi cần kiểm tra file tồn tại, kích thước tối thiểu, header hoặc số record trước khi writer bắt đầu tạo output.

## 18. ItemStreamReader và end of input khi restart

Custom reader có checkpoint thường implement `ItemStreamReader<T>`, kết hợp `ItemReader` và `ItemStream`:

```java
public interface ItemStreamReader<T> extends ItemReader<T>, ItemStream {
}
```

Lifecycle cơ bản:

- `open(ExecutionContext)`: mở resource và khôi phục vị trí đã lưu.
- `read()`: trả item tiếp theo hoặc `null` khi hết input.
- `update(ExecutionContext)`: lưu trạng thái cần thiết cho restart.
- `close()`: giải phóng resource.

EOF trong một execution không có nghĩa reader đã mất khả năng restart. Khi job được restart, một reader instance mới được mở với ExecutionContext đã lưu và tiếp tục từ checkpoint phù hợp.

Không nên lưu một cờ `eof=true` vào context nếu điều đó khiến restart bỏ qua phần chưa commit. Chỉ lưu checkpoint theo semantics của chunk/transaction và bảo đảm trạng thái được commit cùng metadata.

## 19. Ví dụ custom reader có checkpoint

Ví dụ sau dùng một danh sách bất biến để minh họa cách phân biệt EOF với state đã lưu:

```java
public class CheckpointCustomerReader implements ItemStreamReader<Customer> {

    private static final String INDEX_KEY = "checkpointCustomerReader.nextIndex";

    private final List<Customer> customers;
    private int nextIndex;

    public CheckpointCustomerReader(List<Customer> customers) {
        this.customers = List.copyOf(customers);
    }

    @Override
    public void open(ExecutionContext context) {
        nextIndex = context.getInt(INDEX_KEY, 0);
    }

    @Override
    public Customer read() {
        if (nextIndex >= customers.size()) {
            return null; // EOF, không còn item.
        }

        Customer customer = customers.get(nextIndex++);
        return Objects.requireNonNull(customer,
                "Reader source must not contain null items");
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(INDEX_KEY, nextIndex);
    }

    @Override
    public void close() {
        // Không có resource ngoài cần đóng trong ví dụ này.
    }
}
```

`List.copyOf` cũng từ chối phần tử null, giúp phát hiện nguồn dữ liệu chứa null ngay khi khởi tạo reader. Ví dụ này chỉ minh họa checkpoint bằng index; reader production cần checkpoint theo vị trí/record key của nguồn thật và cần nguồn bất biến giữa lần chạy đầu và restart.

Spring Batch gọi `update` theo lifecycle stream/chunk để lưu trạng thái. Với transaction-aware JobRepository, ExecutionContext được lưu cùng tiến trình commit phù hợp. Khi chunk rollback, checkpoint đã commit trước đó mới là điểm khôi phục đáng tin cậy.

## 20. Dùng AbstractItemCountingItemStreamItemReader

Spring Batch có lớp cơ sở `AbstractItemCountingItemStreamItemReader<T>` cho reader có thể theo dõi số item đã đọc. Lớp này hỗ trợ quản lý current item count và state cho restart.

Ví dụ cấu trúc:

```java
public class NumberItemReader
        extends AbstractItemCountingItemStreamItemReader<Integer> {

    private final int max;

    public NumberItemReader(int max) {
        this.max = max;
        setName("numberItemReader");
    }

    @Override
    protected Integer doRead() {
        int current = getCurrentItemCount();
        if (current >= max) {
            return null;
        }
        return current + 1;
    }

    @Override
    protected void doOpen() {
        // Mở resource nếu cần.
    }

    @Override
    protected void doClose() {
        // Đóng resource nếu cần.
    }
}
```

Lớp cơ sở quản lý item count và khôi phục state; implementation vẫn phải bảo đảm `doRead()` chỉ trả `null` khi thật sự hết dữ liệu. Khi dùng nguồn có vị trí phức tạp, chẳng hạn file variable-length hoặc API cursor, cần checkpoint phù hợp hơn số item.

Không cần tự triển khai lại cơ chế đếm/checkpoint nếu lớp cơ sở đã đáp ứng yêu cầu. Tuy nhiên, phải đặt tên reader ổn định và bật save state theo cấu hình cần thiết.

## 21. End of input với MultiResourceItemReader

Khi đọc nhiều file, end of input của một resource không nhất thiết là end of input của toàn bộ reader. `MultiResourceItemReader` quản lý danh sách resource và delegate reader.

```text
file-01.csv
   |
   +-- delegate đọc đến EOF
   |
   v
file-02.csv
   |
   +-- delegate đọc đến EOF
   |
   v
file-03.csv
   |
   +-- delegate đọc đến EOF
   |
   v
Không còn resource -> MultiResourceItemReader trả null
```

Delegate trả `null` để báo hết resource hiện tại. `MultiResourceItemReader` có thể chuyển sang resource kế tiếp và chỉ trả `null` khi đã hết tất cả resource.

Khi custom reader/decorator bọc một delegate, cần giữ đúng semantics này. Không được coi `null` từ một file con là EOF của toàn bộ tập resource nếu còn file tiếp theo.

## 22. Adapter và nguồn dữ liệu trả null

`ItemReaderAdapter` cho phép bọc một service/object có method đọc dữ liệu. Nếu method được delegate gọi trả `null`, adapter thường chuyển kết quả đó thành `null` từ `ItemReader.read()`, nghĩa là EOF.

Vì vậy, API delegate cần có hợp đồng rõ:

- Trả item khi có dữ liệu.
- Trả `null` chỉ khi nguồn đã hoàn tất.
- Nếu hiện tại chưa có dữ liệu nhưng có thể có dữ liệu sau, cần chờ/poll hoặc trả một trạng thái khác `null`.
- Nếu có lỗi, ném exception thay vì trả `null`.

Nếu API hiện tại dùng `null` cho cả “không tìm thấy”, “chưa có dữ liệu” và “đã hết stream”, hãy tạo adapter có lớp kết quả rõ ràng trước khi đưa vào Spring Batch.

## 23. Null và asynchronous processing

Trong asynchronous hoặc multi-threaded step, item có thể được chuyển giữa reader, processor và writer qua queue/future. Vẫn phải giữ nguyên hợp đồng: `null` từ reader có nghĩa là không còn item.

Không dùng `null` như tín hiệu “worker này tạm thời chưa có việc” nếu reader có thể được gọi lại sau đó. Với queue, dùng blocking wait hoặc completion marker. Với future, dùng kết quả wrapper để phân biệt “chưa hoàn tất”, “hoàn tất không có giá trị” và “có item”.

Khi có nhiều consumer, tín hiệu kết thúc phải được phân phối cho tất cả consumer cần dừng. Một poison pill có thể chỉ kết thúc một worker; các worker khác vẫn chờ vô hạn nếu không có chiến lược điều phối.

Ngoài ra, `ItemReader` thường không tự thread-safe. Nếu nhiều thread gọi cùng reader, cần bảo đảm implementation hỗ trợ concurrency hoặc dùng mô hình phân vùng với reader instance/state riêng.

## 24. Theo dõi filter, skip và EOF

Để phân biệt job đọc hết dữ liệu, lọc item hay bỏ qua lỗi, hãy xem các counter trong `StepExecution`:

| Counter | Ý nghĩa |
|---|---|
| `readCount` | Số item được reader trả về thành công. |
| `filterCount` | Số item bị processor lọc bằng cách trả `null`. |
| `writeCount` | Số item đã được ghi theo semantics của writer/step. |
| `readSkipCount` | Số lỗi ở giai đoạn read được skip. |
| `processSkipCount` | Số lỗi ở giai đoạn process được skip. |
| `writeSkipCount` | Số lỗi ở giai đoạn write được skip. |
| `skipCount` | Tổng số item/lỗi được skip. |

EOF không phải một counter skip. Reader trả `null` để kết thúc bình thường. Nếu `readCount` thấp bất thường so với số record nguồn, hãy kiểm tra custom reader có trả `null` sớm hay không.

Có thể ghi nhận các metric bổ sung:

- Số dòng trống bị bỏ qua ở reader.
- Số JSON null element hoặc record rỗng được chuẩn hóa.
- Số record bị reject theo lý do.
- Vị trí cuối cùng của parser hoặc byte offset.
- Thời điểm reader đạt EOF.

Không nên dùng tag metric có cardinality quá cao như item ID cho mọi record. Dùng log có correlation ID hoặc bảng rejected record nếu cần truy vết chi tiết.

## 25. Kiểm thử hợp đồng end of input

Một custom reader nên có test xác nhận các trường hợp cơ bản:

1. Nguồn có một item: lần đầu trả item, lần tiếp theo trả `null`.
2. Nguồn có nhiều item: trả đủ item theo thứ tự rồi mới trả `null`.
3. Nguồn rỗng: lần đọc đầu trả `null`.
4. Dòng trống ở giữa: reader bỏ qua hoặc xử lý theo policy, nhưng vẫn đọc record sau.
5. Record không hợp lệ: reader ném exception hoặc trả wrapper lỗi; không trả `null` giả làm EOF.
6. Field null: item vẫn được trả nếu record còn hợp lệ.
7. Nguồn tạm thời rỗng: reader không kết thúc nếu stream chưa hoàn tất.
8. EOF thật: reader trả `null` ổn định sau khi hết nguồn.

Ví dụ test đơn giản:

```java
@Test
void returnsItemsBeforeEndOfInput() throws Exception {
    Customer first = new Customer("C001", "Nguyen An", null);
    Customer second = new Customer("C002", "Tran Binh", "b@example.com");
    CustomerReader reader = new CustomerReader(List.of(first, second));

    assertThat(reader.read()).isEqualTo(first);
    assertThat(reader.read()).isEqualTo(second);
    assertThat(reader.read()).isNull();
}
```

Test reader không nên chỉ kiểm tra lần đọc cuối trả null. Hãy xác nhận tất cả record trước đó vẫn được trả đầy đủ.

## 26. Kiểm thử filter khác EOF

Test processor cần chứng minh `null` output chỉ lọc một item, không kết thúc reader hoặc step.

```java
@Test
void filtersArchivedCustomer() throws Exception {
    ItemProcessor<Customer, Customer> processor = customer ->
            customer.active() ? customer : null;

    Customer active = new Customer("C001", "Nguyen An", true);
    Customer archived = new Customer("C002", "Tran Binh", false);

    assertThat(processor.process(active)).isEqualTo(active);
    assertThat(processor.process(archived)).isNull();
}
```

Integration test nên kiểm tra `filterCount` tăng, `skipCount` không tăng vì filter, và item tiếp theo vẫn được xử lý.

## 27. Kiểm thử nguồn không có dữ liệu

Nếu empty input là hợp lệ, test xác nhận step hoàn tất với `readCount == 0` và writer không ghi item. Nếu empty input không hợp lệ, test xác nhận validation step hoặc listener chuyển kết quả sang trạng thái lỗi theo thiết kế.

Không nên dùng một test chỉ khẳng định `reader.read()` trả null rồi suy ra toàn job xử lý empty input đúng. Cần kiểm tra job flow, output file rỗng/không tồn tại theo chính sách và trạng thái cuối của execution.

## 28. Kiểm thử restart và EOF

Với reader có state, cần kiểm thử:

- Một số chunk commit trước khi step thất bại.
- ExecutionContext lưu checkpoint tương ứng.
- Restart mở reader mới và khôi phục đúng vị trí.
- Các item chưa commit được đọc lại.
- EOF chỉ được trả khi nguồn thực sự hết.
- Reader không lưu cờ EOF quá sớm khiến restart bỏ qua dữ liệu.
- Input không thay đổi giữa lần chạy đầu và restart.

Đối với custom reader, test `open`, `read`, `update`, `close` qua cả hai execution. Nếu reader dùng file hoặc queue, nên test thêm trường hợp resource đóng/mở lại và checkpoint bị thiếu/không hợp lệ.

## 29. Các lỗi thường gặp khi xử lý null và EOF

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Step dừng giữa file | Reader trả `null` khi gặp dòng trống hoặc record lỗi. | Chỉ trả `null` khi nguồn hết; bỏ qua/throw cho record khác. |
| Record có field SQL NULL bị mất | RowMapper trả `null` cho toàn row thay vì object có field null. | Trả domain object khác null và giữ null ở field tương ứng. |
| JSON array dừng ở phần tử `null` | Null element bị ánh xạ thành Java null tại ranh giới reader. | Skip/normalize/reject bằng custom reader hoặc wrapper. |
| Filter bị tính là skip | Nhầm processor trả null với exception skippable. | Xem `filterCount` và `skipCount` riêng biệt. |
| Queue rỗng làm step kết thúc | `poll()` trả null khi tạm thời chưa có message. | Block, poll tiếp hoặc dùng completion sentinel. |
| Lỗi parse bị che giấu | Catch exception rồi trả null. | Ném exception phù hợp để fault tolerance xử lý. |
| Empty file được coi là thành công ngoài ý muốn | Spring Batch xem EOF ngay lần đầu là bình thường. | Validate `readCount` nếu nghiệp vụ yêu cầu có record. |
| Multi-resource reader dừng sau file đầu | Wrapper coi null của delegate là EOF toàn bộ. | Dùng semantics của `MultiResourceItemReader` và chuyển resource tiếp theo. |
| Restart bỏ qua item | Checkpoint lưu vị trí/EOF không nhất quán. | Lưu state theo chunk commit và test restart. |
| Writer nhận null item | Reader/processor không tuân thủ hợp đồng. | Chuẩn hóa item trước writer; không truyền null như item. |

## 30. Quy trình thiết kế xử lý null và end of input

Khi viết custom component, hãy xác định rõ từng trường hợp:

1. **Định nghĩa item boundary:** thế nào là một record hợp lệ trong nguồn?
2. **Định nghĩa EOF:** tín hiệu nào chứng minh không còn dữ liệu nữa?
3. **Phân loại null nguồn:** null field, empty record, explicit JSON null hay không có record?
4. **Chọn cách biểu diễn:** field null trong object, wrapper/Optional, filter hoặc exception.
5. **Xử lý lỗi:** phân biệt lỗi parse, lỗi dữ liệu và lỗi nguồn tạm thời.
6. **Bảo đảm reader contract:** không trả null trước EOF thật.
7. **Thiết kế filter/skip:** processor trả null cho filter; exception và skip policy cho lỗi được phép bỏ qua.
8. **Kiểm tra empty input:** xác định job có chấp nhận zero item không.
9. **Lưu checkpoint:** cập nhật state nhất quán với chunk commit và restart.
10. **Kiểm thử boundary:** item đầu/cuối, dòng rỗng, record null, lỗi giữa nguồn, empty input và nguồn tạm thời rỗng.
11. **Theo dõi counter:** phân biệt read, filter, skip và EOF.

## 31. Những điểm cần ghi nhớ

- `ItemReader.read()` trả `null` để báo end of input; đây là tín hiệu kết thúc đọc của step.
- Không trả `null` cho record hợp lệ, dòng trống ở giữa file, lỗi parse hoặc nguồn tạm thời chưa có dữ liệu.
- Null trong một field của domain object không đồng nghĩa với null ở ranh giới reader.
- `ItemProcessor.process()` trả `null` có nghĩa filter item; không phải EOF và không phải skip.
- Filter làm tăng `filterCount`; exception được skip làm tăng skip counter.
- Empty input có thể là hoàn tất bình thường; nếu nghiệp vụ yêu cầu ít nhất một item, hãy validate riêng.
- Ném exception cho lỗi đọc/parse; không catch mọi lỗi rồi trả null để kết thúc job âm thầm.
- Với JSON array có phần tử `null`, hãy normalize, skip hoặc reject bằng một biểu diễn khác null.
- Nguồn bất đồng bộ/queue phải phân biệt tạm thời không có item với tín hiệu hoàn tất; dùng blocking hoặc sentinel rõ ràng.
- `MultiResourceItemReader` có thể chuyển sang resource kế tiếp khi delegate đạt EOF; chỉ kết thúc khi mọi resource đã hết.
- Custom `ItemStreamReader` phải quản lý `open`, `read`, `update`, `close` và checkpoint đúng transaction boundary.
- Kiểm thử đủ item trước EOF, empty input, null field, record lỗi, filter và restart.

Xử lý null và end of input là một phần của hợp đồng giữa custom reader, processor và Spring Batch. Giữ `null` ở reader cho đúng ý nghĩa EOF, dùng `null` ở processor chỉ cho filter có chủ đích, và biểu diễn dữ liệu thiếu bằng object/field/wrapper phù hợp. Khi phân biệt rõ EOF, empty input, record không hợp lệ và nguồn tạm thời chưa có dữ liệu, job sẽ tránh kết thúc sớm và giữ được khả năng truy vết lỗi cũng như restart an toàn.
