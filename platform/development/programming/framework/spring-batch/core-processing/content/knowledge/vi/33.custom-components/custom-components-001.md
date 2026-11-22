# Tự viết ItemReader trong Spring Batch

Trong Spring Batch, ItemReader là thành phần cung cấp từng item đầu vào cho một chunk-oriented Step. Reader có thể lấy dữ liệu từ file, API, message queue, thiết bị, định dạng riêng hoặc nguồn mà các reader có sẵn không hỗ trợ trực tiếp.

Tự viết ItemReader cho phép ứng dụng kiểm soát cách kết nối tới nguồn, chuyển dữ liệu thành object, phát hiện hết dữ liệu và lưu checkpoint để restart. Reader phải tuân thủ một hợp đồng nhỏ nhưng quan trọng: mỗi lần gọi read() trả về một item hoặc trả null khi đã hết dữ liệu. Lỗi đọc phải được biểu diễn bằng exception; không được giả vờ hết dữ liệu bằng cách trả null.

Một reader dùng trong production thường cần nhiều hơn phương thức read(). Nếu nó giữ cursor, file handle, vị trí trang hoặc trạng thái đọc, hãy triển khai ItemStream để mở resource, lưu trạng thái và đóng resource. Khi được đăng ký đúng với Step, Spring Batch có thể gọi lifecycle đó và khôi phục checkpoint trong lần restart.

Bài học này trình bày hợp đồng ItemReader, cách viết reader đơn giản và reader restartable, cách đọc file và API phân trang, cách tích hợp với StepScope, cách xử lý lỗi và resource, cùng chiến lược kiểm thử và concurrency.

## 1. ItemReader làm gì trong chunk-oriented Step?

Một chunk-oriented Step đọc item cho đến khi đạt commit interval hoặc hết dữ liệu. Mỗi item được đưa qua processor nếu có, sau đó kết quả được chuyển cho writer.

~~~mermaid
flowchart LR
    A["Nguồn dữ liệu"] --> B["ItemReader.read()"]
    B --> C["ItemProcessor"]
    C --> D["ItemWriter.write(chunk)"]
    D --> E["Commit transaction"]
    B --> F["EOF: trả null"]
    F --> G["Kết thúc đọc"]
~~~

Ví dụ Step xử lý từng Customer:

~~~java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> customerReader,
        ItemProcessor<CustomerInput, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
        .<CustomerInput, Customer>chunk(100, transactionManager)
        .reader(customerReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .build();
}
~~~

Reader cung cấp CustomerInput. Processor có thể chuẩn hóa hoặc xác thực dữ liệu rồi trả Customer. Writer nhận một Chunk<Customer> để ghi.

Reader không quyết định commit. Transaction boundary thuộc Step và transaction manager. Reader chịu trách nhiệm cung cấp dữ liệu theo đúng thứ tự và trạng thái nguồn.

## 2. Hợp đồng của ItemReader

Interface cơ bản có một phương thức:

~~~java
public interface ItemReader<T> {
    T read() throws Exception;
}
~~~

Mỗi lần gọi read():

- Trả về một item nếu còn dữ liệu.
- Trả về null khi nguồn đã hết dữ liệu.
- Ném exception nếu không thể đọc hoặc xử lý dữ liệu theo hợp đồng.

Spring Batch tiếp tục gọi read() cho đến khi nhận null. Vì vậy, null có nghĩa kết thúc nguồn đọc, không phải một item rỗng hoặc lỗi tạm thời.

### Không trả null để biểu diễn lỗi

Giả sử reader gọi API và nhận HTTP 503. Nếu reader trả null, Spring Batch hiểu batch đã hết dữ liệu và kết thúc Step bình thường. Những item còn lại có thể không bao giờ được đọc.

Cách đúng là ném exception có ý nghĩa:

~~~java
@Override
public CustomerInput read() throws Exception {
    ApiResponse response = client.fetchNext();

    if (response.isTemporarilyUnavailable()) {
        throw new TransientDataAccessException(
            "Nguồn dữ liệu tạm thời không sẵn sàng"
        );
    }

    if (response.isEndOfData()) {
        return null;
    }

    return map(response);
}
~~~

Exception có thể được xử lý bởi retry, skip hoặc failure policy của Step. Chọn loại exception phù hợp để policy phân biệt lỗi tạm thời với lỗi dữ liệu.

### Reader phải tiến triển

Mỗi lần read() phải tiến tới trạng thái tiếp theo hoặc kết thúc. Nếu reader trả cùng một item liên tục mà không thay đổi cursor, Step có thể chạy vô hạn.

Khi nguồn có dữ liệu lặp, hãy xác định khóa hoặc cursor ổn định để bảo đảm reader tiến triển.

## 3. Reader đơn giản không có state

Nếu nguồn dữ liệu nhỏ, bất biến và không cần restart, reader có thể chỉ triển khai ItemReader.

~~~java
public class ListItemReader<T> implements ItemReader<T> {

    private final Iterator<T> iterator;

    public ListItemReader(List<T> items) {
        this.iterator = items.iterator();
    }

    @Override
    public T read() {
        return iterator.hasNext() ? iterator.next() : null;
    }
}
~~~

Cách này phù hợp với test fixture nhỏ, danh sách cấu hình tĩnh hoặc nguồn đã được nạp sẵn và có giới hạn rõ.

Nhưng reader này không lưu vị trí hiện tại vào ExecutionContext. Nếu Job thất bại rồi restart, Spring Batch không biết iterator đã đọc đến đâu. Một reader mới sẽ bắt đầu lại từ đầu.

Đối với dữ liệu lớn hoặc Job cần restart, không nên nạp toàn bộ nguồn vào List chỉ để dùng iterator. Hãy đọc theo stream, cursor hoặc page và lưu checkpoint.

## 4. Khi nào cần triển khai ItemStream?

Spring Batch cung cấp ItemStream để reader có thể tham gia lifecycle của Step:

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
~~~

Trong thực tế, các phương thức có thể ném ItemStreamException.

- open() mở resource và khôi phục trạng thái đã lưu.
- update() ghi trạng thái hiện tại vào ExecutionContext.
- close() giải phóng resource.

Reader có state nên triển khai ItemStreamReader:

~~~java
public interface ItemStreamReader<T>
        extends ItemReader<T>, ItemStream {
}
~~~

Dùng ItemStreamReader khi reader cần mở file hoặc cursor, giữ vị trí đọc, lưu page number/offset/record ID, khôi phục vị trí khi restart hoặc đóng stream/cursor/connection.

Một reader stateless có thể chỉ cần ItemReader. Một reader có resource hoặc checkpoint nên triển khai ItemStream để framework quản lý đúng vòng đời.

## 5. Tự viết reader đọc file từng dòng

Ví dụ đầu tiên là custom reader đọc file văn bản. Mỗi dòng là một item String. Reader lưu số dòng đã trả về để restart từ vị trí tương ứng.

~~~java
public class CheckpointingLineReader
        implements ItemStreamReader<String> {

    private static final String LINE_KEY =
        "checkpointingLineReader.currentLine";

    private final Path inputPath;

    private BufferedReader reader;
    private long currentLine;

    public CheckpointingLineReader(Path inputPath) {
        this.inputPath = inputPath;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        close();

        long savedLine = executionContext.getLong(LINE_KEY, 0L);
        BufferedReader candidate = null;

        try {
            candidate = Files.newBufferedReader(
                inputPath,
                StandardCharsets.UTF_8
            );

            for (long skipped = 0; skipped < savedLine; skipped++) {
                if (candidate.readLine() == null) {
                    throw new ItemStreamException(
                        "Checkpoint vượt quá số dòng trong file: "
                            + savedLine
                    );
                }
            }

            reader = candidate;
            candidate = null;
            currentLine = savedLine;
        } catch (IOException | RuntimeException ex) {
            if (candidate != null) {
                try {
                    candidate.close();
                } catch (IOException closeException) {
                    ex.addSuppressed(closeException);
                }
            }

            if (ex instanceof ItemStreamException streamException) {
                throw streamException;
            }

            throw new ItemStreamException(
                "Không thể mở hoặc khôi phục file " + inputPath,
                ex
            );
        }
    }

    @Override
    public String read() {
        if (reader == null) {
            throw new IllegalStateException(
                "Reader chưa được mở"
            );
        }

        try {
            String line = reader.readLine();

            if (line == null) {
                return null;
            }

            currentLine++;
            return line;
        } catch (IOException ex) {
            throw new ItemStreamException(
                "Lỗi khi đọc file " + inputPath,
                ex
            );
        }
    }

    @Override
    public void update(ExecutionContext executionContext) {
        executionContext.putLong(LINE_KEY, currentLine);
    }

    @Override
    public void close() {
        BufferedReader current = reader;
        reader = null;

        if (current != null) {
            try {
                current.close();
            } catch (IOException ex) {
                throw new ItemStreamException(
                    "Không thể đóng file " + inputPath,
                    ex
                );
            }
        }
    }
}
~~~

Reader này có những đặc điểm:

- Không nạp toàn bộ file vào bộ nhớ.
- Mỗi lần read() trả về tối đa một dòng.
- EOF được biểu diễn bằng null.
- currentLine đếm số dòng đã trả về.
- update() lưu vị trí vào ExecutionContext.
- open() bỏ qua các dòng đã được checkpoint lưu.
- close() giải phóng BufferedReader và có thể được gọi nhiều lần an toàn.

Đây là ví dụ minh họa checkpoint theo số dòng. Với file rất lớn, việc đọc bỏ qua từ đầu đến checkpoint có thể tốn thời gian. Có thể dùng byte offset, index hoặc định dạng có cursor riêng nếu cần khôi phục nhanh hơn.

### Tại sao dùng key có namespace?

ExecutionContext có thể chứa state từ nhiều reader, writer và component. Key như currentLine quá chung và có thể đè lên state của thành phần khác.

Dùng prefix riêng như checkpointingLineReader.currentLine giúp tránh xung đột. Tên key cần ổn định giữa các lần restart và các phiên bản ứng dụng có thể chạy tiếp Job cũ.

## 6. Ý nghĩa của checkpoint

Checkpoint là trạng thái cho biết reader đã tiến tới đâu tại một ranh giới lưu trữ an toàn. Spring Batch dùng ExecutionContext để lưu trạng thái của StepExecution.

Ví dụ với commit interval 3:

~~~text
Nguồn: A B C D E F G H

Chunk 1:
  read A, B, C
  write A, B, C
  commit
  checkpoint sau C

Chunk 2:
  read D, E, F
  writer lỗi
  rollback chunk 2

Restart:
  khôi phục checkpoint sau C
  đọc lại D, E, F
~~~

Checkpoint cần tương ứng với dữ liệu đã commit. Nếu reader tự ghi vị trí tiến xa hơn dữ liệu đã commit, restart có thể bỏ sót item. Nếu vị trí lùi lại, một số item có thể được đọc lại và writer phải xử lý idempotency.

Spring Batch gọi ItemStream.update() trong lifecycle quản lý chunk để cập nhật ExecutionContext. JobRepository lưu context theo transaction và checkpoint của Step. Không tự ghi checkpoint vào database độc lập mà không hiểu cách nó phối hợp với commit của chunk.

### Không cập nhật checkpoint trong mọi lần read()

Reader thường chỉ ghi state khi framework gọi update() ở ranh giới phù hợp. Nếu tự persist vị trí vào nguồn ngoài ở mỗi lần read(), reader có thể tiến quá xa so với transaction của chunk. Khi writer rollback, dữ liệu đã bị đánh dấu tiêu thụ và không thể đọc lại.

Hãy để ExecutionContext tham gia lifecycle của Spring Batch hoặc thiết kế một cơ chế nguồn có acknowledgment/transaction rõ ràng.

## 7. Cấu hình custom reader bằng Java configuration

Có thể tạo bean StepScope để nhận đường dẫn file từ JobParameters:

~~~java
@Bean
@StepScope
ItemStreamReader<String> customLineReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException(
            "Thiếu JobParameter input.file"
        );
    }

    return new CheckpointingLineReader(Path.of(inputFile));
}
~~~

Cấu hình Step:

~~~java
@Bean
Step importTextStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemStreamReader<String> customLineReader,
        ItemProcessor<String, CustomerInput> parser,
        ItemWriter<CustomerInput> writer) {

    return new StepBuilder("importTextStep", jobRepository)
        .<String, CustomerInput>chunk(100, transactionManager)
        .reader(customLineReader)
        .processor(parser)
        .writer(writer)
        .build();
}
~~~

@StepScope trì hoãn việc tạo target reader đến khi StepExecution hoạt động. Vì vậy, biểu thức jobParameters có thể lấy được đường dẫn của lần chạy hiện tại.

Reader được khai báo với kiểu ItemStreamReader nên Spring Batch nhận biết cả ItemReader và ItemStream lifecycle.

### Giữ tên và ý nghĩa state ổn định

Key ExecutionContext do ứng dụng định nghĩa cần ổn định giữa các lần restart. Nếu thay đổi ý nghĩa checkpoint, hãy version hóa hoặc có migration plan.

Nếu một JobInstance cũ restart bằng code mới nhưng reader dùng key khác, reader có thể bắt đầu lại từ đầu hoặc khôi phục sai vị trí.

## 8. Parse dữ liệu trong reader hay processor?

Reader có thể trả về raw line String rồi để processor parse thành object:

~~~java
@Bean
ItemProcessor<String, CustomerInput> customerLineParser() {
    return line -> {
        String[] columns = line.split(",", -1);

        if (columns.length != 3) {
            throw new InvalidCustomerLineException(
                "Dòng không có đủ 3 cột: " + line
            );
        }

        return new CustomerInput(
            columns[0].trim(),
            columns[1].trim(),
            columns[2].trim()
        );
    };
}
~~~

Tách parse thành processor có thể hữu ích khi reader chỉ chịu trách nhiệm lấy dữ liệu thô, quy tắc chuyển đổi là logic nghiệp vụ có thể test riêng, hoặc muốn áp dụng skip policy cho lỗi xử lý từng item.

Nếu định dạng nguồn phức tạp, parser có thể thuộc reader vì nó là một phần của giao thức đọc. Khi đó reader cần phát sinh exception có ngữ nghĩa rõ ràng và test riêng.

Không dùng String.split(",") cho CSV production nếu field có thể chứa dấu phẩy, quote hoặc newline. Dùng parser CSV chuyên dụng hoặc FlatFileItemReader nếu nó đáp ứng định dạng.

## 9. Reader đọc API theo trang

Một nguồn REST có thể trả dữ liệu theo trang:

~~~json
{
  "items": [
    {"id": 101, "name": "An"},
    {"id": 102, "name": "Binh"}
  ],
  "nextPage": 2,
  "hasMore": true
}
~~~

Custom reader có thể giữ số trang hiện tại, danh sách item của trang đang đọc, index tiếp theo trong trang, token continuation nếu API dùng cursor, và snapshot/cutoff để nguồn không thay đổi trong khi batch chạy.

~~~mermaid
flowchart TD
    A["read() được gọi"] --> B{"Trang hiện tại còn item?"}
    B -- "Có" --> C["Trả item kế tiếp"]
    B -- "Không" --> D{"API còn trang?"}
    D -- "Có" --> E["Fetch trang kế tiếp"]
    E --> B
    D -- "Không" --> F["Trả null"]
~~~

Không nên gọi API một lần rồi nạp mọi trang vào List nếu dữ liệu lớn. Giữ buffer chỉ cho trang hiện tại giúp giới hạn bộ nhớ.

### Pseudocode cho reader phân trang

~~~java
public class PagedApiItemReader
        implements ItemStreamReader<ApiRecord> {

    private static final String PAGE_KEY = "pagedApiReader.page";
    private static final String INDEX_KEY = "pagedApiReader.index";

    private final ApiClient client;
    private final String batchId;

    private List<ApiRecord> pageItems = List.of();
    private int page;
    private int index;
    private boolean noMorePages;

    public PagedApiItemReader(ApiClient client, String batchId) {
        this.client = client;
        this.batchId = batchId;
    }

    @Override
    public void open(ExecutionContext context) {
        page = context.getInt(PAGE_KEY, 0);
        index = context.getInt(INDEX_KEY, 0);
        pageItems = List.of();
        noMorePages = false;

        if (index > 0) {
            pageItems = client.fetchPage(batchId, page);
            if (index > pageItems.size()) {
                throw new ItemStreamException(
                    "Checkpoint index không hợp lệ"
                );
            }
        }
    }

    @Override
    public ApiRecord read() {
        while (true) {
            if (index < pageItems.size()) {
                return pageItems.get(index++);
            }

            if (noMorePages) {
                return null;
            }

            ApiPage<ApiRecord> response =
                client.fetchPageWithMetadata(batchId, page);

            if (response == null) {
                throw new ItemStreamException(
                    "API trả response null"
                );
            }

            pageItems = response.items();
            index = 0;

            if (!response.hasMore() && pageItems.isEmpty()) {
                noMorePages = true;
                return null;
            }

            if (pageItems.isEmpty() && response.hasMore()) {
                page = response.nextPage();
                continue;
            }

            if (pageItems.isEmpty()) {
                noMorePages = true;
                return null;
            }
        }
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(PAGE_KEY, page);
        context.putInt(INDEX_KEY, index);
    }

    @Override
    public void close() {
        pageItems = List.of();
    }
}
~~~

Đây là pseudocode minh họa ý tưởng, cần điều chỉnh theo hợp đồng API cụ thể. Một implementation production phải xác định rõ page zero-based hay one-based, page hiện tại được lưu trước hay sau khi fetch, nextPage được cập nhật khi nào và trạng thái EOF được khôi phục ra sao.

Một cách an toàn là checkpoint bằng continuation token hoặc ID cuối cùng đã xử lý thay vì page/index nếu API hỗ trợ. Token thường ổn định hơn khi dữ liệu nguồn thay đổi.

### Cẩn thận với trang rỗng

Một trang rỗng không nhất thiết có nghĩa EOF. API có thể trả trang rỗng nhưng vẫn có next cursor do filter hoặc consistency model. Chỉ kết thúc khi metadata API xác nhận không còn trang.

Ngược lại, nếu API trả hasMore=true nhưng liên tục trả trang rỗng và không thay đổi cursor, reader có thể lặp vô hạn. Hãy phát hiện cursor không tiến triển và ném exception.

## 10. Cursor ổn định cho API và database

Khi nguồn thay đổi trong lúc Job đang chạy, offset pagination có thể làm item bị bỏ sót hoặc lặp.

Ví dụ API dùng offset:

~~~text
GET /records?offset=0&limit=100
GET /records?offset=100&limit=100
~~~

Nếu bản ghi mới được thêm vào đầu danh sách giữa hai request, offset 100 có thể trỏ đến dữ liệu khác so với lúc đầu.

Nếu API hỗ trợ cursor hoặc keyset pagination, ưu tiên dùng:

~~~text
GET /records?afterId=1000&limit=100
~~~

Sau khi đọc item cuối cùng, reader lưu lastId. Lần tiếp theo yêu cầu các item có ID lớn hơn lastId.

Điều kiện:

- ID hoặc sort key phải ổn định.
- Thứ tự sắp xếp phải xác định.
- Không có hai record cùng sort key nếu không có tie-breaker.
- Snapshot/cutoff phải cố định nếu dữ liệu mới không được đưa vào batch hiện tại.
- API phải định nghĩa rõ inclusive/exclusive cursor.

Với database, JdbcPagingItemReader thường đã giải quyết phần lớn vấn đề paging và restart. Chỉ viết custom reader khi cần nguồn hoặc quy tắc đặc biệt mà reader có sẵn không đáp ứng.

## 11. Tự viết reader cho nguồn database

Nếu cần đọc từ database bằng logic riêng, có thể dùng JdbcTemplate trong custom reader. Tuy nhiên, hãy cân nhắc reader có sẵn trước:

- JdbcCursorItemReader cho cursor.
- JdbcPagingItemReader cho paging.
- RepositoryItemReader cho Spring Data repository.

Custom database reader cần quyết định connection do ai quản lý, cursor có giữ connection qua toàn Step không, transaction manager nào quản lý resource, reader có thread-safe không, checkpoint là offset hay khóa cuối, và dữ liệu có thể thay đổi giữa các chunk không.

Ví dụ đọc theo keyset:

~~~java
public class CustomerKeysetReader
        implements ItemStreamReader<Customer> {

    private static final String LAST_ID_KEY =
        "customerKeysetReader.lastId";

    private final JdbcTemplate jdbcTemplate;
    private final int pageSize;

    private long lastId;
    private Iterator<Customer> currentPage =
        List.<Customer>of().iterator();
    private boolean exhausted;

    public CustomerKeysetReader(
            JdbcTemplate jdbcTemplate,
            int pageSize) {
        this.jdbcTemplate = jdbcTemplate;
        this.pageSize = pageSize;
    }

    @Override
    public void open(ExecutionContext context) {
        lastId = context.getLong(LAST_ID_KEY, 0L);
        currentPage = List.<Customer>of().iterator();
        exhausted = false;
    }

    @Override
    public Customer read() {
        if (currentPage.hasNext()) {
            Customer customer = currentPage.next();
            lastId = customer.id();
            return customer;
        }

        if (exhausted) {
            return null;
        }

        List<Customer> rows = jdbcTemplate.query(
            """
            SELECT customer_id, full_name
            FROM customer
            WHERE customer_id > ?
            ORDER BY customer_id
            LIMIT ?
            """,
            customerRowMapper(),
            lastId,
            pageSize
        );

        if (rows.isEmpty()) {
            exhausted = true;
            return null;
        }

        currentPage = rows.iterator();

        Customer customer = currentPage.next();
        lastId = customer.id();
        return customer;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(LAST_ID_KEY, lastId);
    }

    @Override
    public void close() {
        currentPage = List.<Customer>of().iterator();
    }
}
~~~

Đây là ví dụ về keyset paging; cần bổ sung các quy tắc của hệ thống như batch filter, tenant, snapshot, xử lý ID null và isolation. Query phải có thứ tự ổn định. Nếu có nhiều record cùng khóa sắp xếp, hãy dùng khóa phụ để phân biệt.

Vì JdbcTemplate quản lý statement/result set và tham gia transaction thông qua DataSource phù hợp, reader không giữ cursor mở. Với một custom cursor reader, cần triển khai ItemStream để mở và đóng cursor đúng lifecycle.

### Checkpoint sau item cuối của trang

Trong ví dụ, lastId cập nhật khi item được trả về. Khi rollback chunk, Spring Batch quản lý ExecutionContext và reader state theo transaction/checkpoint. Không tự lưu lastId vào bảng ngoài ở mỗi lần read() vì có thể vượt trước commit.

## 12. Xử lý exception trong read()

read() có thể ném checked hoặc unchecked exception. Spring Batch chuyển lỗi vào cơ chế fault tolerance của Step.

Nên phân loại lỗi:

| Loại lỗi | Ví dụ | Hành vi thường phù hợp |
|---|---|---|
| Lỗi tạm thời nguồn | Timeout, connection reset | Retry có giới hạn |
| Lỗi dữ liệu item | Dòng sai định dạng | Skip nếu nghiệp vụ cho phép |
| Lỗi cấu hình | File path sai, thiếu credential | Fail Step |
| Lỗi document | XML malformed, file bị truncate | Thường fail nguồn/file |
| EOF | Không còn item | Trả null |

Tạo exception có ngữ nghĩa:

~~~java
public class InvalidCustomerRecordException
        extends RuntimeException {

    public InvalidCustomerRecordException(
            String message,
            Throwable cause) {
        super(message, cause);
    }
}
~~~

Khi parser phát hiện một record sai:

~~~java
@Override
public CustomerInput read() throws Exception {
    String line = readNextLine();

    if (line == null) {
        return null;
    }

    try {
        return parse(line);
    } catch (IllegalArgumentException ex) {
        throw new InvalidCustomerRecordException(
            "Record không hợp lệ tại dòng " + currentLine,
            ex
        );
    }
}
~~~

Nếu Step cho phép skip InvalidCustomerRecordException, framework có thể bỏ item lỗi theo policy. Không chuyển mọi exception thành cùng một loại vì retry và skip cần phân biệt.

## 13. Retry, skip và vị trí reader

Khi một item lỗi, reader đã có thể tiến tới vị trí tiếp theo. Framework quản lý việc rollback và buffering theo cấu hình Step. Reader custom cần giữ state nhất quán với lifecycle của Step.

Các nguyên tắc:

- Không tự commit hoặc acknowledge nguồn trong read() nếu chunk chưa commit.
- Không lưu checkpoint bền vững vượt trước commit.
- Không trả null khi gặp exception.
- Đảm bảo read() không trả cùng item vô hạn.
- Khi skip một item, checkpoint sau commit phải phản ánh item đó đã được xử lý theo policy.
- Với nguồn message, phối hợp acknowledgment/redelivery với transaction.

Nếu reader lấy dữ liệu từ API không thể rollback, có thể cần cursor bền vững hoặc idempotency ở writer. Nếu API cung cấp cursor token, giữ token tương ứng với item đã commit, không phải item chỉ vừa fetch.

### Fetch page khác với commit item

Reader có thể fetch trước cả trang 100 item nhưng Step mới commit 20 item đầu tiên. Nếu Job thất bại, 80 item còn lại trong page buffer chưa được commit. Khi restart, reader phải khôi phục từ checkpoint sau item thứ 20, không nhảy sang page tiếp theo chỉ vì page đã được tải.

Đây là lý do cần lưu index hoặc cursor đã tiêu thụ, thay vì chỉ lưu số trang đã fetch.

## 14. Reader có resource phải xử lý open thất bại

Một custom reader có thể mở nhiều resource: input stream, parser, connection hoặc cursor. Nếu open() mở được resource thứ nhất nhưng resource thứ hai lỗi, cần tự đóng resource đã mở.

~~~java
@Override
public void open(ExecutionContext context) {
    InputStream candidateStream = null;
    XMLStreamReader candidateParser = null;

    try {
        candidateStream = Files.newInputStream(inputPath);
        candidateParser = xmlInputFactory.createXMLStreamReader(
            candidateStream
        );

        this.inputStream = candidateStream;
        this.xmlReader = candidateParser;
    } catch (Exception ex) {
        closeQuietly(candidateParser);
        closeQuietly(candidateStream);

        throw new ItemStreamException(
            "Không thể mở XML source",
            ex
        );
    }
}
~~~

Khi thành công, reader giữ ownership của resource và close() phải giải phóng chúng. Khi open() thất bại, cleanup diễn ra ngay trong open() vì framework có thể chưa đăng ký hoặc chưa hoàn tất lifecycle của reader.

Đóng theo thứ tự ngược với thứ tự mở: parser trước, stream sau. Không đóng resource do component khác sở hữu.

## 15. Không chia sẻ reader có state giữa nhiều thread

Một custom reader thường chứa state mutable như current file position, page buffer, cursor, last ID hoặc end-of-source flag. Nếu bean reader là singleton và cùng được nhiều JobExecution sử dụng, state của các lần chạy có thể đè lên nhau.

Có thể dùng @StepScope để mỗi StepExecution có một target reader riêng:

~~~java
@Bean
@StepScope
ItemStreamReader<String> customerLineReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {
    return new CheckpointingLineReader(Path.of(inputFile));
}
~~~

Trong partitioning, mỗi worker StepExecution nên có reader instance và StepExecutionContext riêng. Không chia sẻ một mutable reader cho nhiều partition.

StepScope không biến reader thành thread-safe nếu nhiều thread cùng gọi một target trong một StepExecution. Với multi-threaded Step, hãy kiểm tra concurrency contract hoặc dùng reader có hỗ trợ đồng bộ phù hợp.

## 16. Đăng ký ItemStream trong Step

Khi custom reader được truyền trực tiếp vào .reader(...) và object triển khai ItemStream, Spring Batch có thể quản lý lifecycle của reader.

~~~java
return new StepBuilder("customImportStep", jobRepository)
    .<String, CustomerInput>chunk(100, transactionManager)
    .reader(customLineReader)
    .processor(customerLineParser)
    .writer(customerWriter)
    .build();
~~~

Nếu một wrapper chỉ triển khai ItemReader nhưng giữ một delegate triển khai ItemStream, framework có thể không tự biết delegate cần open/update/close.

Ví dụ decorator không chuyển tiếp lifecycle:

~~~java
public class LoggingReader<T> implements ItemReader<T> {

    private final ItemReader<T> delegate;

    public LoggingReader(ItemReader<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public T read() throws Exception {
        T item = delegate.read();
        log.debug("Reader returned an item");
        return item;
    }
}
~~~

Nếu delegate là ItemStreamReader, wrapper trên không chuyển tiếp lifecycle. Có hai lựa chọn:

1. Làm wrapper triển khai ItemStreamReader và chuyển tiếp open/update/close.
2. Đăng ký delegate trực tiếp bằng StepBuilder.stream(delegate) khi cấu trúc Step phù hợp.

Ví dụ wrapper chuyển tiếp:

~~~java
public class LoggingStreamReader<T>
        implements ItemStreamReader<T> {

    private final ItemStreamReader<T> delegate;

    public LoggingStreamReader(ItemStreamReader<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public T read() throws Exception {
        return delegate.read();
    }

    @Override
    public void open(ExecutionContext context) {
        delegate.open(context);
    }

    @Override
    public void update(ExecutionContext context) {
        delegate.update(context);
    }

    @Override
    public void close() {
        delegate.close();
    }
}
~~~

Khi viết decorator, phải giữ nguyên cả hợp đồng đọc và hợp đồng lifecycle. Nếu không, restart có thể bị hỏng dù lần chạy đầu vẫn thành công.

## 17. Reader cho nguồn message hoặc queue

Một queue reader cần phân biệt rõ EOF với tạm thời không có message.

Với batch hữu hạn, nguồn nên có điều kiện kết thúc xác định, ví dụ chỉ xử lý message thuộc batch ID, chỉ đọc đến watermark/timestamp cutoff, API trả continuation token cuối hoặc queue được snapshot.

Nếu queue là vô hạn, read() chờ message mãi sẽ không trả null và Step không hoàn tất. Đây có thể là thiết kế streaming consumer, nhưng không còn là batch hữu hạn thông thường.

### Acknowledge và checkpoint

Nếu message bị acknowledge trước khi chunk commit, Job có thể mất item khi writer rollback. Nếu không acknowledge, broker có thể redeliver item sau khi restart.

Thiết kế cần phối hợp:

- Message ID.
- Visibility timeout hoặc lease.
- Acknowledgment mode.
- Transaction manager và broker transaction nếu hỗ trợ.
- Idempotency key của writer.
- Checkpoint lưu ID cuối đã commit.

Không coi close consumer là acknowledge. Close chỉ giải phóng kết nối/subscription; trạng thái message phụ thuộc protocol của broker.

## 18. Đặt tên và version hóa ExecutionContext key

ExecutionContext là metadata bền vững của JobRepository. Key của custom reader có thể tồn tại qua nhiều lần restart và qua lần deploy ứng dụng mới.

Dùng tên có namespace:

~~~java
private static final String CURRENT_LINE_KEY =
    "customerFileReader.currentLine";

private static final String LAST_ID_KEY =
    "customerApiReader.lastId";
~~~

Nếu cấu trúc checkpoint thay đổi, có thể lưu version:

~~~java
context.putInt("customerFileReader.stateVersion", 2);
~~~

Khi open():

- Kiểm tra version.
- Đọc key tương ứng.
- Chuyển đổi trạng thái cũ nếu có thể.
- Nếu không tương thích, ném lỗi rõ ràng và yêu cầu tạo JobInstance mới hoặc chạy migration có kiểm soát.

Không đổi key hoặc cách hiểu cursor tùy tiện trong khi JobInstance cũ còn có thể restart.

## 19. Kiểm thử custom ItemReader độc lập

Một unit test nên kiểm tra hợp đồng read() và lifecycle.

~~~java
@TempDir
Path tempDirectory;

@Test
void readsEachLineThenReturnsNull() throws Exception {
    Path input = tempDirectory.resolve("customers.txt");

    Files.writeString(
        input,
        "C001,An\nC002,Binh\n",
        StandardCharsets.UTF_8
    );

    CheckpointingLineReader reader =
        new CheckpointingLineReader(input);

    reader.open(new ExecutionContext());
    try {
        assertEquals("C001,An", reader.read());
        assertEquals("C002,Binh", reader.read());
        assertNull(reader.read());
        assertNull(reader.read());
    } finally {
        reader.close();
    }
}
~~~

Test này xác nhận reader mở được file, mỗi lần gọi trả một dòng, dữ liệu giữ đúng thứ tự, EOF trả null, gọi read() thêm sau EOF vẫn trả null và resource được đóng.

Thêm test cho file rỗng và dòng trống. Dòng trống là item hợp lệ nếu nguồn định nghĩa như vậy; không tự đổi chuỗi rỗng thành EOF.

## 20. Kiểm thử restart bằng ExecutionContext

Test restart ở mức reader có thể mô phỏng bằng cách dùng cùng ExecutionContext cho hai instance reader:

~~~java
@Test
void resumesFromSavedLineCheckpoint() throws Exception {
    Path input = tempDirectory.resolve("customers.txt");

    Files.writeString(
        input,
        "C001,An\nC002,Binh\nC003,Chi\n",
        StandardCharsets.UTF_8
    );

    ExecutionContext context = new ExecutionContext();

    CheckpointingLineReader first =
        new CheckpointingLineReader(input);

    first.open(context);
    assertEquals("C001,An", first.read());
    assertEquals("C002,Binh", first.read());
    first.update(context);
    first.close();

    CheckpointingLineReader restarted =
        new CheckpointingLineReader(input);

    restarted.open(context);
    try {
        assertEquals("C003,Chi", restarted.read());
        assertNull(restarted.read());
    } finally {
        restarted.close();
    }
}
~~~

Test chứng minh reader có thể khôi phục checkpoint đã lưu. Nó chưa chứng minh Spring Batch lưu ExecutionContext đúng theo transaction của chunk; điều đó cần Step integration test.

### Kiểm thử checkpoint không hợp lệ

Thử các trường hợp checkpoint lớn hơn số dòng file, file đã thay đổi sau checkpoint, encoding khác, file bị truncate hoặc key state cũ không có version tương thích.

Reader nên fail rõ ràng nếu trạng thái không thể khôi phục an toàn, thay vì âm thầm bỏ qua dữ liệu.

## 21. Kiểm thử với StepScope và Step integration

Nếu reader nhận JobParameters qua @Value, hãy kiểm thử trong scope thật.

Có thể dùng JobLauncherTestUtils để chạy Step với input.file:

~~~java
@SpringBatchTest
@SpringJUnitConfig(BatchTestConfiguration.class)
class CustomReaderStepTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void readsInputFromJobParameter() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
            .addString("input.file", "src/test/resources/customers.txt")
            .toJobParameters();

        JobExecution execution =
            jobLauncherTestUtils.launchStep(
                "customImportStep",
                parameters
            );

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        StepExecution stepExecution =
            execution.getStepExecutions().iterator().next();

        assertEquals(2, stepExecution.getReadCount());
    }
}
~~~

Cấu hình test phải cung cấp Job/Step tương ứng và output resource riêng cho test. Nếu test nhiều lần, tránh dùng cùng output file có thể bị ghi đè hoặc nối thêm.

JobLauncherTestUtils giúp xác nhận StepScope được kích hoạt, JobParameters được bind, reader được open/update/close, JobRepository lưu StepExecution và read count phản ánh số item.

Không chỉ assert BatchStatus; hãy kiểm tra output hoặc dữ liệu đích để xác nhận nội dung đúng.

## 22. Kiểm thử exception và EOF

Cần test phân biệt EOF với lỗi nguồn:

| Tình huống | Kết quả mong đợi |
|---|---|
| Đã đọc hết file | read() trả null |
| File rỗng hợp lệ theo contract | read() trả null ngay |
| File không tồn tại | open() ném lỗi |
| Không có quyền đọc | open() hoặc read() ném lỗi |
| API timeout | read() ném exception retryable |
| API xác nhận hết dữ liệu | read() trả null |
| Dòng sai định dạng | Ném exception dữ liệu hoặc trả raw item để processor xử lý |
| Reader chưa open | Ném lỗi lifecycle rõ ràng |

Không viết test chỉ kiểm tra rằng mọi lỗi đều làm Step FAILED. Nếu exception được cấu hình retry hoặc skip, trạng thái cuối có thể khác. Test policy ở cấp Step riêng.

## 23. Kiểm thử retry, skip và rollback

Một custom reader có thể ném exception khi đọc item. Step fault-tolerant có thể retry hoặc skip tùy exception policy.

~~~java
return new StepBuilder("customImportStep", jobRepository)
    .<String, CustomerInput>chunk(10, transactionManager)
    .reader(customLineReader)
    .processor(customerLineParser)
    .writer(customerWriter)
    .faultTolerant()
    .retry(TransientSourceException.class)
    .retryLimit(3)
    .skip(InvalidCustomerLineException.class)
    .skipLimit(10)
    .build();
~~~

Kiểm thử nên xác nhận lỗi tạm thời có thể retry theo giới hạn, lỗi item được skip nếu policy cho phép, lỗi cấu hình không bị retry vô ích, reader state không bỏ sót item sau rollback, skip count đúng, writer chỉ nhận item hợp lệ và resource được đóng khi Step kết thúc.

Không biến lỗi parse document hoặc lỗi kết nối toàn nguồn thành skip item nếu reader không thể tiếp tục an toàn.

## 24. Concurrency và partitioning

Một custom reader thường chứa state mutable. Vì vậy, không chia sẻ cùng một instance giữa nhiều thread hoặc partition nếu implementation không được thiết kế thread-safe.

Với partitioning:

- Mỗi worker có StepExecution riêng.
- Tạo reader riêng cho từng worker.
- Dùng StepExecutionContext để truyền partition range hoặc cursor.
- Mỗi reader lưu checkpoint riêng.
- Tên key cần ổn định và không xung đột.
- Resource path hoặc query phải giới hạn theo partition.

Ví dụ:

~~~java
@Bean
@StepScope
ItemStreamReader<Customer> partitionReader(
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {
    return new CustomerRangeReader(minId, maxId);
}
~~~

Trong multi-threaded Step, nhiều thread có thể gọi cùng reader target. StepScope không tự tạo một instance cho mỗi thread. Nếu reader không thread-safe, cần đồng bộ hóa, dùng reader hỗ trợ concurrency hoặc chọn partitioning với reader riêng cho từng worker.

## 25. Những lỗi thiết kế thường gặp

### Trả null khi nguồn tạm thời lỗi

Spring Batch hiểu null là EOF. Timeout hoặc HTTP 503 phải được ném thành exception để retry hoặc fail.

### Không triển khai ItemStream cho reader stateful

Reader vẫn có thể chạy lần đầu nhưng restart bắt đầu sai vị trí. Lưu checkpoint trong ExecutionContext.

### Cập nhật checkpoint quá sớm

Persist vị trí đã fetch thay vì vị trí đã commit có thể làm mất item sau rollback. Checkpoint phải phối hợp với chunk transaction.

### Dùng page number mà bỏ qua index trong trang

Nếu một trang được fetch nhưng chỉ một phần item đã commit, restart phải đọc tiếp từ index đúng hoặc cursor cuối đã commit.

### Không ổn định thứ tự nguồn

Paging không có ORDER BY ổn định hoặc API sort key không duy nhất có thể làm item lặp hoặc mất.

### Nạp toàn bộ dữ liệu vào bộ nhớ

Một reader custom không nên chuyển nguồn lớn thành List chỉ để đơn giản hóa code. Dùng streaming hoặc paging.

### Dùng singleton cho reader có state

Hai JobExecution có thể ghi đè cursor hoặc file handle. Dùng StepScope khi state thuộc StepExecution.

### Wrapper làm mất ItemStream

Decorator chỉ triển khai ItemReader có thể khiến delegate không được open/update/close. Chuyển tiếp lifecycle hoặc đăng ký stream riêng.

### Không cleanup khi open thất bại

Nếu mở được một phần resource rồi ném exception, tự đóng các resource đã mở trước khi thoát.

### Dùng message queue như nguồn vô hạn cho batch hữu hạn

Nếu không có cutoff hoặc điều kiện kết thúc, read() không bao giờ trả null và Step không hoàn tất.

### Không kiểm thử restart với dữ liệu nguồn thay đổi

Checkpoint có thể không còn tương ứng với nguồn. Dùng snapshot, version hoặc cursor ổn định.

### Không kiểm tra thread safety

Mutable buffer và cursor có thể bị nhiều thread truy cập đồng thời. Xác định ownership và concurrency model.

## 26. Checklist thiết kế custom ItemReader

Trước khi đưa reader vào Step, xác định:

1. **Nguồn dữ liệu:** file, database, API, queue hay nguồn riêng?
2. **Một item là gì:** một dòng, một record, một page entry hay một message?
3. **EOF:** điều kiện nào chứng minh không còn item?
4. **Exception:** lỗi nào tạm thời, lỗi nào dữ liệu, lỗi nào cấu hình?
5. **State:** reader cần lưu offset, page, token, last ID hay cursor nào?
6. **Checkpoint:** state nào tương ứng với chunk đã commit?
7. **Lifecycle:** reader mở và đóng resource ở đâu?
8. **Restart:** nguồn có ổn định giữa lần chạy và restart không?
9. **Registration:** reader và delegate ItemStream có được Step quản lý không?
10. **Scope:** reader có cần StepScope để nhận JobParameters/partition context không?
11. **Concurrency:** reader có bị gọi từ nhiều thread hoặc partition không?
12. **Memory:** buffer có giới hạn và có thể xử lý nguồn lớn không?
13. **Observability:** log có đủ batch ID, StepExecution ID và cursor để điều tra không?
14. **Tests:** EOF, error, checkpoint, restart, cleanup và Step integration đã được kiểm tra chưa?

## 27. Khi nào nên dùng reader có sẵn?

Spring Batch cung cấp nhiều reader đã xử lý các chi tiết khó như resource lifecycle, checkpoint và restart.

| Nguồn | Reader nên xem xét |
|---|---|
| File phân tách cột | FlatFileItemReader |
| XML fragment | StaxEventItemReader |
| JDBC cursor | JdbcCursorItemReader |
| JDBC paging | JdbcPagingItemReader |
| Spring Data repository | RepositoryItemReader |
| Nhiều resource file | MultiResourceItemReader |
| Danh sách trong bộ nhớ | ListItemReader |
| Nguồn đặc thù hoặc API cursor | Custom ItemReader/ItemStreamReader |

Tự viết reader khi cần giao thức hoặc semantics riêng. Nếu chỉ cần đổi cách ánh xạ field của một nguồn phổ biến, có thể dùng reader có sẵn với mapper/line mapper tùy chỉnh.

Reader có sẵn thường đã có test và xử lý các tình huống restart khó. Custom reader nên tập trung vào phần ứng dụng thực sự cần kiểm soát.

## 28. Những điểm cần nhớ

- ItemReader.read() trả một item hoặc null khi hết dữ liệu.
- null không được dùng để biểu diễn timeout, lỗi parse hoặc lỗi kết nối.
- Reader đơn giản có thể chỉ triển khai ItemReader, nhưng reader stateful nên triển khai ItemStreamReader.
- open() khôi phục resource và checkpoint; update() lưu state; close() giải phóng resource.
- ExecutionContext key phải có namespace và ổn định qua restart.
- Checkpoint phải phản ánh dữ liệu đã commit, không phải chỉ dữ liệu đã fetch.
- API pagination cần lưu cả page và index/cursor tiêu thụ; ưu tiên cursor ổn định nếu API hỗ trợ.
- Database reader cần cân nhắc keyset, thứ tự ổn định và transaction manager.
- Dùng @StepScope khi reader nhận JobParameters hoặc StepExecutionContext.
- Wrapper/decorator phải chuyển tiếp ItemStream lifecycle hoặc đăng ký delegate với Step.
- Reader có state mutable không nên dùng chung giữa partition hoặc thread nếu không thread-safe.
- Khi open() thất bại giữa chừng, tự cleanup resource đã mở.
- Kiểm thử độc lập read/EOF/checkpoint và kiểm thử Step thật với JobLauncherTestUtils.
- Ưu tiên reader có sẵn khi đáp ứng yêu cầu; custom reader chỉ nên xử lý phần nguồn đặc thù.

Tự viết ItemReader không chỉ là cài đặt một phương thức read(). Một reader đáng tin cậy phải có hợp đồng EOF rõ ràng, tiến triển ổn định, checkpoint khớp transaction, resource lifecycle đầy đủ và hành vi restart có thể kiểm thử. Khi các phần đó được thiết kế cùng nhau, reader custom có thể tích hợp tự nhiên vào chunk processing và vận hành an toàn với dữ liệu lớn.

